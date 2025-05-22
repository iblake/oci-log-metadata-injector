# LogFusion: OCI Log Metadata Injector 
# Inspired by: oci-tag-enrichment-task v1.0 (Oracle UPL)
# Modified and extended for flexible log metadata injection with improved structure and cache control.
# Description:
#   This function receives log payloads that may include OCIDs (Oracle Cloud Identifiers),
#   and annotates them by retrieving their associated metadata (tags) using OCI Resource Search.
#   The resulting metadata is injected into a configurable part of the log payload.
#   Designed to run as an Oracle Cloud Function with Resource Principal or local config.

import os
import io
import json
import logging
from cachetools import TTLCache
import oci
from fdk import response

# -------------------------
# Configuration Parameters
# -------------------------
# These values can be configured using environment variables in OCI
config = {
    # The key name where tag metadata will be injected into the payload
    'output_field': os.getenv('TAG_OUTPUT_FIELD', 'metadata'),

    # Optional dot notation path in the input JSON where tags should be added
    # For example: "logContent.oracle" to place them inside that sub-dictionary
    'insertion_path': os.getenv('TAG_INSERTION_PATH', ''),

    # Types of tags to include (freeform, defined, system)
    'tag_types': os.getenv('TAG_TYPES', 'freeform,defined,system').split(','),

    # Include tag types even when they're empty
    'include_empty': os.getenv('INCLUDE_EMPTY_TAGS', 'false').lower() in ('true', '1', 'yes'),

    # Cache size for OCID lookups (avoids repeated API calls during batch processing)
    'cache_size': int(os.getenv('CACHE_SIZE', '512')),

    # TTL for cache in seconds (e.g. 28800 = 8 hours)
    'cache_ttl': int(os.getenv('CACHE_TTL', '28800')),

    # Optional filter to only process specific OCID keys (e.g., "resourceid")
    'attribute_filter': os.getenv('OCID_KEY_FILTER').split(',') if os.getenv('OCID_KEY_FILTER') else None
}

# Set up logging
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO').upper())
logger = logging.getLogger()

# Maps simplified tag type names to OCI SDK field names
TAG_TYPE_MAP = {
    'freeform': 'freeform_tags',
    'defined': 'defined_tags',
    'system': 'system_tags'
}

# Local in-memory cache of tag lookups
# Helps reduce redundant API calls during high-frequency processing
tag_cache = TTLCache(maxsize=config['cache_size'], ttl=config['cache_ttl'])

# Initialize OCI Resource Search Client
# Uses config file locally, or resource principal signer when running in OCI Functions
def get_oci_client():
    if __name__ == '__main__':
        return oci.resource_search.ResourceSearchClient(
            oci.config.from_file(profile_name=os.getenv('OCI_PROFILE', 'DEFAULT'))
        )
    else:
        signer = oci.auth.signers.get_resource_principals_signer()
        return oci.resource_search.ResourceSearchClient(config={}, signer=signer)

oci_client = get_oci_client()

# Extract all OCIDs from nested JSON payload
# Filters by attribute name if a filter is configured
def extract_ocids(data):
    ocids = []
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str) and value.startswith('ocid1.'):
                if not config['attribute_filter'] or key in config['attribute_filter']:
                    ocids.append(value)
            elif isinstance(value, (dict, list)):
                ocids.extend(extract_ocids(value))
    elif isinstance(data, list):
        for item in data:
            ocids.extend(extract_ocids(item))
    return ocids

# Query OCI Resource Search for a single OCID to get tag metadata
# Supports multiple tag types and caches results
def query_tags(ocid):
    if ocid in tag_cache:
        return tag_cache[ocid]

    try:
        query = f"query all resources where identifier = '{ocid}'"
        details = oci.resource_search.models.StructuredSearchDetails(
            query=query,
            type='Structured',
            matching_context_type=oci.resource_search.models.SearchDetails.MATCHING_CONTEXT_TYPE_NONE
        )
        result = oci_client.search_resources(details)

        tag_info = {}
        for item in result.data.items:
            if item.identifier == ocid:
                for tag_type in config['tag_types']:
                    field = TAG_TYPE_MAP.get(tag_type)
                    if field:
                        tags = getattr(item, field, {}) or {}
                        if tags or config['include_empty']:
                            tag_info[tag_type] = tags
        tag_cache[ocid] = tag_info
        return tag_info

    except Exception as e:
        logger.error(f"Error fetching tags for {ocid}: {e}")
        return {}

# Traverse a nested dictionary to find where to insert the tags
# Returns a reference to the sub-dict or list, or root if not found
def find_insertion_point(data):
    if not config['insertion_path']:
        return data

    path = config['insertion_path'].split('.')
    node = data
    for key in path:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return None
    return node

# Injects the tag results dictionary into the configured location in the payload
# If the location isn't found, defaults to adding at the root
def attach_metadata(data, tag_results):
    container = find_insertion_point(data)
    if isinstance(container, dict):
        container[config['output_field']] = tag_results
    elif isinstance(container, list):
        container.append({config['output_field']: tag_results})
    else:
        data[config['output_field']] = tag_results

# OCI Function entrypoint: receives payload, annotates with tag metadata, returns updated payload
# Handles both single log objects and lists of logs
def handler(ctx, data: io.BytesIO = None):
    try:
        event = json.loads(data.getvalue())
        records = event if isinstance(event, list) else [event]

        for record in records:
            ocids = extract_ocids(record)
            tag_map = {ocid: query_tags(ocid) for ocid in ocids}
            attach_metadata(record, tag_map)

        updated_payload = records if isinstance(event, list) else records[0]
        return response.Response(
            ctx,
            status_code=200,
            response_data=json.dumps(updated_payload, indent=2),
            headers={"Content-Type": "application/json"}
        )

    except Exception as err:
        logger.exception("Failed to process log annotation function")
        raise

# Enables local testing by piping a payload from stdin
# Example: cat test.json | python3 func.py
if __name__ == '__main__':
    import sys
    if not sys.stdin.isatty():
        input_data = io.StringIO(sys.stdin.read())
        result = handler(None, input_data)
        print(result.body)
    else:
        print("Provide input via stdin: cat file.json | python3 func.py", file=sys.stderr)
