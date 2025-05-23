# LogFusion: OCI Log Metadata Injector

**Purpose:** Enhance incoming log payloads with metadata (tags) from OCI resources using Resource Search.

## Overview

**LogFusion** is an Oracle Cloud Function designed to enrich log events by injecting OCI resource metadata into the payload. It helps correlate logs emitted by Kubernetes clusters or OCI services (often with opaque OCIDs) with meaningful information (like tags), improving observability in tools like Datadog or Splunk.

## Features

- **Tag injection** (freeform, defined, system) from OCI.
- **Dot-path insertion** to nested payloads.
- **Cache control** to reduce OCI API calls.
- **Environment variable configuration**.
- **Flexible OCID filtering** by key name.

## Use Cases

- Annotate Kubernetes Load Balancer logs with application tags.
- Inject metadata into logs before forwarding to external tools like [Datadog](https://docs.datadoghq.com/es/integrations/oracle_cloud_infrastructure/?tab=creafvcnconormrecomendado).
- Build centralized, enriched log pipelines using OCI Service [Connector Hub](https://www.youtube.com/embed/9hPJKO-7VWo?rel=0&autoplay=1) + [Functions](https://www.youtube.com/watch?v=bbaLAC7267g).

## Integration Example: Service Connector Hub

LogFusion is ideal as a **Task Function** between:

- **Source**: Logging (e.g. Load Balancer logs)
- **Task**: LogFusion (inject metadata)
- **Target**: Stream / Object Storage / Datadog forwarding function

![Overview of Connector Hub](https://docs.oracle.com/en-us/iaas/Content/connector-hub/images/sch-all.svg)

Use Service Connector Hub to connect these components for an event-driven observability pipeline.

## Architecture

LogFusion expects a JSON payload (single or array) and returns the same payload with a new field containing tag metadata for each OCID found.

![Metadata Injector](https://github.com/user-attachments/assets/4c41c376-1e40-4dbf-91a9-556b60873af6)


## IAM Configuration
Compartment Setup
To get started, we'll work with a compartment specifically created for this purpose. Let's assume it's named log-tagging-scope.

### Required Permissions and Access
Since our Oracle Function will use the OCI SDK to access metadata (like tags) from other resources, it needs the proper identity and access management (IAM) setup.

### Dynamic Group Configuration
In OCI, functions are treated as IAM resources. To give our Function the right level of access, we must define a dynamic group — for example, log-tagging-group — that targets all Functions deployed within the log-tagging-scope compartment.

Here's a sample rule for the group:

```resource.type = 'fnfunc' and resource.compartment.id = 'ocid1.compartment.oc1..<your-compartment-ocid>'```

### Policy Definitions
Now we’ll create IAM policies to grant the function permission to query and interact with tagged resources. Depending on your scenario, you may need access to virtual networks, storage buckets, or other services. Below is a policy template you can tailor to your needs:

```bash
Allow dynamic-group log-meta-fn-group to use tag-namespaces in compartment <your-compartment-name>
Allow dynamic-group log-meta-fn-group to inspect all-resources in compartment <your-compartment-name>
Allow dynamic-group log-meta-fn-group to read instances in compartment <your-compartment-name>
Allow dynamic-group log-meta-fn-group to use search in tenancy
Allow dynamic-group log-meta-fn-group to read users in tenancy
Allow dynamic-group log-meta-fn-group to read buckets in compartment <your-compartment-name>
Allow dynamic-group log-meta-fn-group to manage objects in compartment <your-compartment-name>
```
> Adjust these permissions based on your exact use case. For example, if you only enrich logs from Load Balancers, the read instances policy may not be required.

## How It Works

1. **Input**: Receives a JSON payload containing one or more OCIDs.
2. **OCID Extraction**: Recursively walks the JSON to find all OCIDs (optionally filtered by key).
3. **Tag Query**: For each OCID, uses `oci.resource_search` to retrieve metadata.
4. **Caching**: Stores results in a TTL-based in-memory cache.
5. **Metadata Injection**: Adds tag metadata to the designated location in the payload.
6. **Output**: Returns the updated JSON.

## Function environment variables

| Variable Name           | Description                                                                 | Example                       |
|------------------------|-----------------------------------------------------------------------------|-------------------------------|
| `TAG_OUTPUT_FIELD`     | Field name to store injected tags in the payload                            | `metadata`                    |
| `TAG_INSERTION_PATH`   | Dot-separated path to nested dict where tags should be inserted             | `logContent.oracle`           |
| `TAG_TYPES`            | Comma-separated list of tag types to retrieve                               | `freeform,defined`            |
| `INCLUDE_EMPTY_TAGS`   | Whether to include empty tag types                                          | `true` / `false`              |
| `CACHE_SIZE`           | Max entries in in-memory cache                                              | `512`                         |
| `CACHE_TTL`            | Time-to-live (in seconds) for cached tag lookups                            | `28800` (8 hours)             |
| `OCID_KEY_FILTER`      | Filter only specific keys in JSON that hold OCIDs                           | `resourceId,lb_ocid`          |
| `OCI_PROFILE`          | Profile name in local `~/.oci/config` (used for local testing)              | `DEFAULT`                     |
| `LOG_LEVEL`            | Logging level                                                               | `DEBUG`, `INFO`, `ERROR`, ... |

## Sample Input

```json
{
  "datetime": 1746631634883,
  "logContent": {
    "data": {
      "backendAddr": "10.0.XX.XX:30136, 10.0.XX.X:30136",
      "backendConnectTime": "-, -",
      "clientAddr": "185.XXX.XXX.XXX:45740",
      "lbStatusCode": "502",
      "listenerName": "TCP-80",
      "sslCipher": "",
      "sslProtocol": "",
      "timestamp": "2025-05-07T15:27:14+00:00"
    },
    "id": "e475f859-9833-4e10-aac7-XXX-access-0",
    "oracle": {
      "compartmentid": "ocid1.compartment.oc1..aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX",
      "ingestedtime": "2025-05-07T15:27:22.504Z",
      "loggroupid": "ocid1.loggroup.oc1.eu-frankfurt-1.aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX",
      "logid": "ocid1.log.oc1.eu-frankfurt-1.aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX",                                     
      "resourceid": "ocid1.loadbalancer.oc1.eu-frankfurt-1.aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX",
      "tenantid": "ocid1.tenancy.oc1..aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX"
    },
    "source": "30671607-273c-4911-bad1-xxxxxxxxxxxxxxf",
    "specversion": "1.0",
    "subject": "",
    "time": "2025-05-07T15:27:14.883Z",
    "type": "com.oraclecloud.loadbalancer.access"
  },
  "regionId": "eu-frankfurt-1"
}
````

## Sample Output

```json
{
  "datetime": 1746631634883,
  "logContent": {
    "data": {
      "backendAddr": "10.0.XXX.XXX:30136, 10.0.XXX.XXX:30136",
      "backendConnectTime": "-, -",
      "clientAddr": "185.218.XXX.XXX:45740",
      "lbStatusCode": "502",
      "listenerName": "TCP-80",
      "sslCipher": "",
      "sslProtocol": "",
      "timestamp": "2025-05-07T15:27:14+00:00"
    },
    "id": "e475f859-9833-4e10-aac7-xxxxxxxxx-access-0",
    "oracle": {
      "compartmentid": "ocid1.compartment.oc1..aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX",
      "ingestedtime": "2025-05-07T15:27:22.504Z",
      "loggroupid": "ocid1.loggroup.oc1.eu-frankfurt-1.aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX",
      "logid": "ocid1.log.oc1.eu-frankfurt-1.aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX",
      "resourceid": "ocid1.loadbalancer.oc1.eu-frankfurt-1.aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX",
      "tenantid": "ocid1.tenancy.oc1..aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX"
    },
    "source": "30671607-273c-4911-bad1-xxxxxxxxxx",
    "specversion": "1.0",
    "subject": "",
    "time": "2025-05-07T15:27:14.883Z",
    "type": "com.oraclecloud.loadbalancer.access"
  },
  "regionId": "eu-frankfurt-1",
  "metadata": {
    "ocid1.compartment.oc1..aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX": {
      "defined": {
        "CCA_Basic_Tag": {
          "email": "testing@test.com"
        },
        "Oracle-Standard": {
          "CostCenter": "Example2"
        },
        "Oracle_Tags": {
          "CreatedBy": "oracleidentitycloudservice/xxxxxx.xxxxxx@oracle.com"
        }
      }
    },
    "ocid1.loggroup.oc1.eu-frankfurt-1.aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX": {
      "defined": {
        "CCA_Basic_Tag": {
          "email": "oracleidentitycloudservice/testing@test.com"
        },
        "Oracle-Standard": {
          "CostCenter": "Example2"
        },
        "Oracle_Tags": {
          "CreatedBy": "oracleidentitycloudservice/testing@test.com",
          "CreatedOn": "2025-03-20T15:47:02.927Z"
        }
      }
    },
    "ocid1.log.oc1.eu-frankfurt-1.aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX": {
      "defined": {
        "CCA_Basic_Tag": {
          "email": "oracleidentitycloudservice/testing@test.com"
        },
        "Oracle-Standard": {
          "CostCenter": "Example2"
        },
        "Oracle_Tags": {
          "CreatedBy": "oracleidentitycloudservice/testing@test.com",
          "CreatedOn": "2025-05-07T15:26:32.794Z"
        }
      }
    },
    "ocid1.loadbalancer.oc1.eu-frankfurt-1.aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX": {
      "freeform": {
        "OKEclusterName": "dgcCluster1",
        "LB_APP": "dgcDEMO"
      },
      "defined": {
        "CCA_Basic_Tag": {
          "email": "ocid1.cluster.oc1.eu-frankfurt-1.aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX"
        },
        "Oracle-Standard": {
          "CostCenter": "Example2"
        },
        "Oracle_Tags": {
          "CreatedBy": "ocid1.cluster.oc1.eu-frankfurt-1.aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX",
          "CreatedOn": "2025-05-07T15:21:44.936Z"
        }
      },
      "system": {
        "orcl-containerengine": {
          "Cluster": "ocid1.cluster.oc1.eu-frankfurt-1.aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX"
        }
      }
    },
    "ocid1.tenancy.oc1..aaaaaaaaoqn77wyhkn3crracqfaqXXXXXXXXXXXXXXXXXXXXXXXX": {}
  }
}
```
## Local Testing in CloudShell

We can test the function in CloudShell using a sample log before integrating it with the OS Connector Hub.

```bash
cat payload.json | fn invoke <app_name> <function_name>
```

## Function FlowChart

```mermaid
flowchart TD
    %% Class Definitions
    classDef startEnd fill:#e6fffa,stroke:#319795,stroke-width:2px,color:#234e52
    classDef decision fill:#fefcbf,stroke:#d69e2e,stroke-width:2px,color:#744210
    classDef process fill:#ebf8ff,stroke:#3182ce,stroke-width:2px,color:#2a4365
    classDef data fill:#fbd38d,stroke:#dd6b20,stroke-width:2px,color:#7b341e
    classDef fail fill:#fed7d7,stroke:#e53e3e,stroke-width:2px,color:#742a2a

    %% Nodes
    A([Incoming Log Payload]):::startEnd
    B{Contains OCIDs?}:::decision
    C([Extract OCIDs recursively]):::process
    D{OCID in cache?}:::decision
    E([Query OCI Resource Search]):::process
    F([Store tags in cache]):::data
    G([Retrieve tags from cache]):::data
    H([Build tag map per OCID]):::process
    I([Find insertion point in payload]):::process
    J([Inject metadata at target path]):::process
    K([Return updated payload]):::startEnd
    Z([Return original payload]):::fail

    %% Flow
    A --> B
    B -- No --> Z
    B -- Yes --> C
    C --> D
    D -- No --> E
    E --> F
    D -- Yes --> G
    F --> H
    G --> H
    H --> I
    I --> J
    J --> K
````


