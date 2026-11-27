# Telemetry Ingestion with Event Hubs and Stream Processing Lab

Thousands of sensors emitting temperature, humidity, and status continuously can generate millions of records per day. If every device writes directly to an application database, the database easily saturates when devices burst-send after a network outage; time-window analytics or letting multiple downstream systems read independently also becomes difficult. **Azure Event Hubs** provides a scalable event-stream ingestion layer that decouples emission rates from processing rates.

In the **Architecture and Capstone Labs** chapter of the **CLOUD_PROVIDERS_AZURE** track, this lesson ties together subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, storage, data, monitoring, security, and cost control. We build a pipeline: **Java producer → Event Hubs → Azure Stream Analytics → Blob Storage**, while also running an independent **Java EventProcessorClient** consumer with checkpointing.

A reliable pipeline does not stop at successfully sending one JSON message. It must handle late arrivals, duplicate deliveries, invalid schemas, throughput limits, consumer lag, connection failures, and retention windows—alongside acceptance evidence and safe resource teardown.

> **Scope:** Resource names, numbers, and costs in this lesson are illustrative or lab examples, not fixed Azure pricing or quotas. SDKs, CLIs, SKUs, permissions, and features vary by region, tier, and version. Resource-creation commands can incur charges; run only in an authorized subscription. This lesson does not claim to have deployed or tested directly on the learner's Azure account.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish Event Hubs, Azure Service Bus, IoT Hub, Stream Analytics, and Blob Storage.
2. Explain namespaces, event hubs, partitions, partition keys, consumer groups, offsets, sequence numbers, retention, and checkpoints.
3. Design telemetry events containing event ID, device ID, event time, sequence, and schema version.
4. Provision lab resources via Azure CLI and use Microsoft Entra ID/RBAC to authorize producers and consumers.
5. Write a Java producer sending events with a partition key and understand batching, retries, and duplicates.
6. Write a Stream Analytics query aggregating temperature over one-minute windows.
7. Use `EventProcessorClient` and `BlobCheckpointStore`, and design an idempotent sink.
8. Monitor ingestion, throttling, lag, late events, output errors, and cost.
9. Execute end-to-end testing, recovery drills, and safe cleanup.

## 2. Capstone Scenario: Smart Cold-Storage Warehouse

A company operates three cold-storage warehouse zones, each with multiple temperature sensors. Reliable gateways collect device readings and send them to Azure. Operations requires:

- Continuous telemetry ingestion capable of absorbing catch-up bursts.
- Computing **average, maximum temperature, and sample count per device every minute**.
- Allowing analytics consumers to read the same stream without blocking alerting consumers.
- Replaying events within retention; storing raw archives for long-term traceability when needed.
- Detecting duplicates, invalid payloads, sequence gaps, and silent devices.
- Tracking throughput, latency, backlog, errors, security, and cost.

~~~mermaid
flowchart LR
    DEV["Devices / synthetic data"] --> GW["Java producer / gateway"]
    GW --> EH["Azure Event Hubs namespace + hub"]
    EH --> ASA["Azure Stream Analytics"]
    ASA --> OUT["Blob Storage: aggregates"]
    EH --> PROC["Java EventProcessorClient"]
    PROC --> SINK["Custom sink / alerting"]
    PROC --> CP["Blob checkpoint store"]
    EH -. "Optional Capture" .-> RAW["Blob/ADLS: raw events"]
    EH -. "Metrics" .-> MON["Azure Monitor"]
    ASA -. "Job metrics" .-> MON
~~~

The two downstream branches act as **independent consumers** when configured with separate consumer groups and independent read positions. Stream Analytics aggregates by event time; the Java consumer demonstrates custom processing and checkpointing. One branch reading an event does not remove it from the other branch.

For physical devices needing per-device identity, provisioning, device management, or bidirectional commands, evaluate **Azure IoT Hub** or an appropriate gateway. Never distribute namespace-level SAS keys to untrusted devices.

## 3. Distinguishing the Services

| Service | Role | Do not confuse with |
| --- | --- | --- |
| **Event Hubs** | High-throughput stream ingestion with independent multi-consumer reads | A queue with per-message Complete/Abandon |
| **Service Bus** | Queue/pub-sub for transactional work, settlement, and service-level dead-lettering | A telemetry firehose needing offset replay |
| **IoT Hub** | Manages IoT device connectivity, identities, and device communication | A general-purpose time-window aggregator |
| **Stream Analytics** | SQL-like streaming, windowing, event time, and outputs | An unbounded raw event archive |
| **Blob Storage / ADLS** | Outputs, checkpoints, archives | An automatic event-time processor |
| **`EventProcessorClient`** | Custom consumer with checkpointing and partition ownership | Exactly-once transactions across any sink |
| **Azure Monitor** | Metrics, logs, alerts | Proof that a business sink committed valid data |

If an order must be completed or dead-lettered per message by a worker, consider Service Bus. For multi-consumer telemetry and retention-based replay, Event Hubs is a strong fit to evaluate.

## 4. Namespaces, Partitions, Consumer Groups, and Retention

### 4.1. Namespaces and Hubs

A **namespace** manages event hubs, networking, authentication, and tier throughput capacity. An **event hub** is a logical stream inside a namespace. Data is stored across **partitions**, each maintaining its own ordered sequence of events and metadata.

~~~mermaid
flowchart TB
    P["Producers"] --> H["telemetry-events"]
    H --> A["Partition 0: e1 → e2 → e3"]
    H --> B["Partition 1: e4 → e5"]
    H --> C["Partition 2: e6 → e7"]
    H --> D["Partition 3: e8 → e9"]
    A --> CA["Consumer group ASA"]
    B --> CA
    C --> CA
    D --> CA
    A --> CJ["Consumer group Java"]
    B --> CJ
    C --> CJ
    D --> CJ
~~~

**Ordering is guaranteed within a single partition, not across the entire hub.** Events in two different partitions can be processed interleaved even if produced at different times.

### 4.2. Partition Keys

Producers can set **partition key = deviceId** so events from the same device route consistently per service hashing. This is convenient for preserving per-device order. However, if one `deviceId` emits far more events than others, it can create a **hot partition**. Never assume a `deviceId` → partition ID mapping is immutable across configuration changes or if partition counts change where supported.

### 4.3. Consumer Groups

A **consumer group** provides an independent logical read view. The Stream Analytics job and the Java application must use **separate consumer groups**. Multiple replicas of the same processor app share one consumer group and one checkpoint store to coordinate partition ownership. Consumer groups are not strong tenant isolation security boundaries: use RBAC, separate resources, and networking instead.

### 4.4. Time and Position Concepts

| Concept | Meaning | Common mistake |
| --- | --- | --- |
| **Sequence number** | Event order within a single partition | Comparing sequence numbers across two partitions |
| **Offset** | Byte/stream position within a partition | Treating offset as a namespace-wide ID |
| **Enqueued time** | Timestamp when Event Hubs received the event | Confusing with device measurement time |
| **Event time** | Timestamp when the event occurred at the source | Ignoring clock skew |
| **Processing time** | Time when the consumer actually processes it | Using processing time instead of event time in reports |
| **Checkpoint** | Consumer progress confirmed as processed | Saving checkpoint before durable sink write |
| **Retention** | Duration events remain stored and replayable | Treating Event Hubs as an infinite archive |

Reading an event **does not delete it**. If a processor falls behind past the retention period, unread events expire and can no longer be replayed. For long-term raw history, configure **Event Hubs Capture** where tier/config supports it, or run a dedicated archiver consumer writing to Blob/ADLS.

## 5. Evolvable Telemetry Schema

Sample JSON event:

~~~json
{
  "schemaVersion": 1,
  "eventId": "7f02e2ac-0e89-4e8a-88c3-59c584b663d4",
  "deviceId": "device-101",
  "siteId": "warehouse-north",
  "eventTime": "2026-11-20T08:15:30.000Z",
  "temperatureC": 6.4,
  "humidityPercent": 68.2,
  "batteryPercent": 93,
  "sequence": 1051
}
~~~

| Field | Role | Validation |
| --- | --- | --- |
| `schemaVersion` | Data contract version | Requires evolution policy |
| `eventId` | Logical ID for one reading | Preserve the same ID across retries |
| `deviceId` | Identifier and partition key | Non-empty, contains no secrets |
| `siteId` | Warehouse/zone | Valid allowed value |
| `eventTime` | ISO 8601 UTC timestamp | Parseable, check clock skew |
| `temperatureC` | Temperature in Celsius | Finite number, consistent unit |
| `humidityPercent` | Relative humidity percentage | Within valid bounds |
| `batteryPercent` | Remaining battery | 0–100 |
| `sequence` | Per-device monotonic counter when supported | Check duplicates and gaps |

**Most important retry rule:** the same measurement must keep the same `eventId`. Generating a new `eventId` on every retry prevents downstream systems from reliably deduplicating the logical event.

### 5.1. Event Time vs. Enqueued Time

A device measures at **08:15:30Z**, loses connectivity, sends at **08:17:00Z**, and the consumer processes it at **08:17:03Z**. Event time is 08:15:30Z; enqueued time is ~08:17:00Z; processing time is ~08:17:03Z. A report for "temperature during minute 08:15" must rely on event time and late-arrival rules, not simply consumer receipt time.

### 5.2. Schema Evolution

Adding optional fields is usually far easier to keep compatible than renaming or changing units of required fields. Switching `temperatureC` to Fahrenheit or a string without versioning breaks queries. Enforce versioning, producer/consumer compatibility testing, type validation, quarantine for malformed events, and keep unnecessary PII/tokens/passwords out of telemetry.

## 6. Sizing and SLOs

| Parameter | Example | Meaning |
| --- | --- | --- |
| Device count | 10,000 | Event sources |
| Frequency | 1 event / 10 seconds / device | Arrival rate |
| Size | 500 bytes / event | Byte rate |
| Burst | 3× for several minutes | Headroom for catch-up bursts |
| Partitions | 4 for lab | Parallelism and key distribution |
| Retention | 1 day for lab | Replay window |
| Latency objective | e.g., p95 output within 2 minutes | End-to-end processing target |
| Sink | Blob aggregates and custom consumer | Downstream write capacity |

Events per second:

\[
\lambda=10.000/10=1.000\ \text{events/s}
\]

Raw payload throughput:

\[
1.000\times500=500.000\ \text{byte/s}\approx0{,}5\ \text{MB/s}
\]

Daily volume:

\[
1.000\times500\times86.400=43.200.000.000\ \text{byte}
\approx43{,}2\ \text{GB}
\]

A 3× burst equals **3,000 events/s** and roughly **1.5 MB/s**, before protocol overhead, retries, and payload variance. Check **both event count rate and byte rate**, along with partition skew and sink capacity.

Event Hubs tiers use different capacity models, such as **Throughput Units** on some tiers, or **Processing Units** or dedicated capacity on others. Quotas, auto-inflate behavior, and pricing vary by tier and region, so verify exact numbers rather than picking fixed values blindly.

## 7. Security and Lab Resource Preparation

Prerequisites: a subscription permitting Event Hubs, Storage, and Stream Analytics; Azure CLI/Cloud Shell; JDK 17+; Maven/Gradle; and policy-compliant infrastructure and data-plane permissions.

| Component | Role / mechanism to evaluate |
| --- | --- |
| Java producer | Azure Event Hubs Data Sender |
| Java processor | Azure Event Hubs Data Receiver |
| Azure Stream Analytics input | Event Hubs Data Receiver or connector-supported auth |
| Blob checkpoint | Storage Blob Data Contributor |
| Stream Analytics Blob output | Blob write permission via supported auth method |
| Infrastructure creator | Approved resource management permissions |

**Management-plane roles do not grant data-plane Send/Receive automatically.** Likewise, a local developer's permissions do not automatically apply to a Stream Analytics job's managed identity. In production, prefer Microsoft Entra ID / managed identity where supported by connectors, following least privilege. Enforce TLS, network controls, private endpoints/DNS, and never commit broad SAS connection strings into source code.

### 7.1. Resources to Provision

| Type | Illustrative name | Purpose |
| --- | --- | --- |
| Resource group | `rg-telemetry-lab` | Isolates the lab |
| Namespace | `eh-telemetry-[suffix]` | Event Hubs scope |
| Event hub | `telemetry-events` | Ingestion stream |
| Consumer group A | `telemetry-asa-cg` | Stream Analytics |
| Consumer group B | `telemetry-java-cg` | Java processor |
| Storage Account | `sttelemetry[suffix]` | Outputs and checkpoints |
| Blob container A | `telemetry-aggregates` | Window aggregates |
| Blob container B | `telemetry-checkpoints` | Checkpoints |
| Stream Analytics job | `asa-telemetry-lab` | Window processing |

Choose a **valid unique suffix** without literal brackets. Namespaces and Storage Accounts have strict naming and uniqueness rules; Storage Account names allow lowercase letters and digits only.

## 8. Step 1 — Create Event Hubs and Blob Storage

Examples are for **Bash/Azure Cloud Shell**, not PowerShell. Replace subscription ID and suffix, and verify permissions and pricing before running:

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --query "{id:id,name:name,tenant:tenantId}" -o json

RG="rg-telemetry-lab"
LOC="southeastasia"
SUFFIX="<unique-lowercase-alphanumeric>"
NS="eh-telemetry-$SUFFIX"
HUB="telemetry-events"
CG_ASA="telemetry-asa-cg"
CG_JAVA="telemetry-java-cg"
ST="sttelemetry$SUFFIX"
OUT="telemetry-aggregates"
CK="telemetry-checkpoints"

az group create --name "$RG" --location "$LOC"

az eventhubs namespace create \
  --resource-group "$RG" --name "$NS" \
  --location "$LOC" --sku Standard

az eventhubs eventhub create \
  --resource-group "$RG" --namespace-name "$NS" \
  --name "$HUB" --partition-count 4 --message-retention 1

az eventhubs eventhub consumer-group create \
  --resource-group "$RG" --namespace-name "$NS" \
  --eventhub-name "$HUB" --name "$CG_ASA"

az eventhubs eventhub consumer-group create \
  --resource-group "$RG" --namespace-name "$NS" \
  --eventhub-name "$HUB" --name "$CG_JAVA"

az storage account create \
  --resource-group "$RG" --name "$ST" \
  --location "$LOC" --sku Standard_LRS --kind StorageV2

az storage container create \
  --account-name "$ST" --name "$OUT" --auth-mode login

az storage container create \
  --account-name "$ST" --name "$CK" --auth-mode login
~~~

**Note:** the CLI must include the `eventhubs` command group matching your installed version; if the retention flag differs in your CLI version, check CLI help instead of ignoring errors. Creating containers via `--auth-mode login` requires Storage data-plane permissions. Standard namespaces, Stream Analytics, and other resources can incur ongoing charges even after the producer stops.

Verify the setup:

~~~bash
az eventhubs namespace show \
  --resource-group "$RG" --name "$NS" \
  --query "{name:name,location:location,sku:sku.name}" -o json

az eventhubs eventhub show \
  --resource-group "$RG" --namespace-name "$NS" --name "$HUB" \
  --query "{name:name,partitionCount:partitionCount}" -o json

az eventhubs eventhub consumer-group list \
  --resource-group "$RG" --namespace-name "$NS" \
  --eventhub-name "$HUB" -o table
~~~

## 9. Step 2 — Grant Read/Write Permissions

Example assigning roles to the signed-in Azure CLI user, **only when authorized to self-assign roles in the lab**:

~~~bash
SUB_ID=$(az account show --query id -o tsv)
USER_OID=$(az ad signed-in-user show --query id -o tsv)
EH_SCOPE="/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.EventHub/namespaces/$NS"
ST_SCOPE="/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.Storage/storageAccounts/$ST"

az role assignment create \
  --assignee-object-id "$USER_OID" --assignee-principal-type User \
  --role "Azure Event Hubs Data Sender" --scope "$EH_SCOPE"

az role assignment create \
  --assignee-object-id "$USER_OID" --assignee-principal-type User \
  --role "Azure Event Hubs Data Receiver" --scope "$EH_SCOPE"

az role assignment create \
  --assignee-object-id "$USER_OID" --assignee-principal-type User \
  --role "Storage Blob Data Contributor" --scope "$ST_SCOPE"
~~~

If you lack role assignment rights or use a service principal instead of a user, ask an administrator to assign roles per policy. Scopes can be narrowed further to the specific event hub or container. Wait for RBAC propagation after assignment. The Stream Analytics job requires its own **separate** credential/identity and permissions.

## 10. Step 3 — Java Producer Sending Telemetry

Core Maven dependencies (choose compatible SDK versions):

~~~text
com.azure:azure-messaging-eventhubs
com.azure:azure-identity
~~~

Environment variables per lab convention:

~~~bash
export AZURE_EVENTHUBS_FQDN="$NS.servicebus.windows.net"
export AZURE_EVENTHUB_NAME="$HUB"
~~~

**TelemetryProducer.java** (JDK 17+):

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventDataBatch;
import com.azure.messaging.eventhubs.EventHubClientBuilder;
import com.azure.messaging.eventhubs.EventHubProducerClient;
import com.azure.messaging.eventhubs.models.CreateBatchOptions;

import java.time.Instant;
import java.util.Locale;
import java.util.UUID;

public class TelemetryProducer {
    public static void main(String[] args) throws InterruptedException {
        String fqdn = requiredEnv("AZURE_EVENTHUBS_FQDN");
        String hub = requiredEnv("AZURE_EVENTHUB_NAME");

        try (EventHubProducerClient producer = new EventHubClientBuilder()
                .credential(
                    fqdn, hub, new DefaultAzureCredentialBuilder().build())
                .buildProducerClient()) {

            String[] devices = {"device-101", "device-202", "device-303"};

            // Lab: 3 devices, 1 event/sec each for 90 seconds.
            // Production should buffer/batch per target throughput and latency.
            for (int second = 0; second < 90; second++) {
                for (int i = 0; i < devices.length; i++) {
                    String deviceId = devices[i];
                    double temp = 4.0 + 2 * i + (second % 10) * 0.1;

                    String json = String.format(Locale.ROOT, """
                        {
                          "schemaVersion": 1,
                          "eventId": "%s",
                          "deviceId": "%s",
                          "siteId": "warehouse-north",
                          "eventTime": "%s",
                          "temperatureC": %.2f,
                          "humidityPercent": 68.0,
                          "batteryPercent": 90,
                          "sequence": %d
                        }
                        """, UUID.randomUUID(), deviceId,
                        Instant.now(), temp, second + 1);

                    EventDataBatch batch = producer.createBatch(
                        new CreateBatchOptions().setPartitionKey(deviceId));

                    if (!batch.tryAdd(new EventData(json))) {
                        throw new IllegalStateException(
                            "Event exceeds batch size limit");
                    }

                    producer.send(batch);
                    System.out.printf(
                        "Sent device=%s sequence=%d%n",
                        deviceId, second + 1);
                }
                Thread.sleep(1_000L);
            }
        }
    }

    private static String requiredEnv(String key) {
        String v = System.getenv(key);
        if (v == null || v.isBlank()) {
            throw new IllegalArgumentException("Missing env: " + key);
        }
        return v;
    }
}
~~~

**Expect 270 events** if all sends succeed. Sending one event per batch is intentional for easy observation, though suboptimal at high throughput. Whether the three `deviceId` values land on three distinct partitions is **not guaranteed**.

### 10.1. Batching, Retries, and Duplicates

In production, create a batch with an appropriate partition key, add events via `tryAdd`, and when full, send the current batch, allocate a new batch, and retry adding the event. If a single event cannot fit in an empty batch, it exceeds max size and must be handled/quarantined separately rather than arbitrarily splitting JSON unless consumers support reassembly.

**A send timeout does not prove the service never received the event.** Retrying can deliver an event more than once. Preserve the same `eventId` per logical reading, design an idempotent sink, and avoid stacking unbounded retry loops on top of the SDK's retry policy.

## 11. Step 4 — Azure Stream Analytics: One-Minute Aggregation

In Azure Portal:

1. Create a **Stream Analytics job** in the lab resource group with an appropriate region and capacity.
2. Add an **Event Hubs input**, alias **eh-telemetry-input**, hub **telemetry-events**, consumer group **telemetry-asa-cg**, JSON/UTF-8.
3. Add a **Blob Storage output**, alias **blob-aggregates-output**, container **telemetry-aggregates**, JSON output.
4. Configure the job's identity/credentials and input-read/output-write permissions per supported connector capabilities.
5. Configure out-of-order and late-arrival policies; save the query and start the job before running the producer.

Stream Analytics query:

~~~sql
SELECT
    deviceId,
    siteId,
    System.Timestamp() AS windowEnd,
    COUNT(*) AS sampleCount,
    AVG(temperatureC) AS avgTemperatureC,
    MAX(temperatureC) AS maxTemperatureC
INTO [blob-aggregates-output]
FROM [eh-telemetry-input] TIMESTAMP BY eventTime
GROUP BY
    deviceId,
    siteId,
    TumblingWindow(minute, 1)
~~~

**`TIMESTAMP BY eventTime`** selects the source measurement timestamp. **`TumblingWindow(minute, 1)`** creates contiguous, non-overlapping one-minute windows. **`COUNT/AVG/MAX`** compute sample count, mean, and max per `deviceId`/`siteId`. **`System.Timestamp()`** emits the window-end logical timestamp.

An **illustrative output shape** (not live execution output):

~~~json
{
  "deviceId": "device-101",
  "siteId": "warehouse-north",
  "windowEnd": "2026-11-20T08:16:00Z",
  "sampleCount": 60,
  "avgTemperatureC": 4.45,
  "maxTemperatureC": 4.9
}
~~~

Actual sample counts and emission timing depend on event-time policies, job start position, event timestamps, window closing, and input/output settings. If no Blob appears immediately after the first event, check **job Running state, Input Events, Output Events, watermarks, aliases, query, and Blob permissions** before assuming the job is broken.

## 12. Handling Event Time, Watermarks, and Late Arrivals

| Phenomenon | Example | Risk |
| --- | --- | --- |
| **Late arrival** | Offline device sends readings from 2 minutes ago | Window already closed or data dropped/adjusted |
| **Out-of-order** | Reading at 08:15:10 arrives after 08:15:20 | Misordered relative to measurement time |
| **Duplicate** | Producer retries same `eventId` | `COUNT`/`AVG` skewed if un-deduplicated |
| **Clock skew** | Device clock runs 10 minutes fast | Event assigned to future windows |
| **Missing event** | Device offline and drops readings | Sequence gaps while aggregates look normal |

Azure Stream Analytics lets you configure out-of-order and late-arrival tolerance windows. A wider tolerance captures more delayed events at the cost of higher output latency; a narrow window drops or timestamp-adjusts late events per policy. **Never assume very old events always re-update already emitted windows.**

| Window | Principle | Example |
| --- | --- | --- |
| Tumbling | Contiguous non-overlapping windows | Per-minute report |
| Hopping | Sliding overlapping windows by hop size | 5-minute average updated every minute |
| Session | Grouped by inactivity gaps | Active device sessions |

Never sum `COUNT` across hopping windows to compute unique event totals: a single event contributes to multiple windows.

## 13. Step 5 — Java Consumer and BlobCheckpointStore

Stream Analytics excels at windowed queries. When an application needs custom business rules, use **`EventProcessorClient`** to read raw events. The processor coordinates partition ownership within a consumer group and persists checkpoints to Blob Storage.

### 13.1. Libraries and Configuration

Required Maven coordinates (align versions with your project's Azure SDK BOM):

~~~text
com.azure:azure-messaging-eventhubs
com.azure:azure-messaging-eventhubs-checkpointstore-blob
com.azure:azure-storage-blob
com.azure:azure-identity
~~~

Environment variables for the lab consumer:

~~~bash
export AZURE_EVENTHUBS_FQDN="$NS.servicebus.windows.net"
export AZURE_EVENTHUB_NAME="$HUB"
export AZURE_EVENTHUB_CONSUMER_GROUP="$CG_JAVA"
export AZURE_STORAGE_ACCOUNT_NAME="$ST"
export AZURE_CHECKPOINT_CONTAINER="$CK"
~~~

The consumer needs **Data Receiver** on Event Hubs and **Storage Blob Data Contributor** on the checkpoint container or account. When deployed to Azure, replace the local Azure CLI user with a managed identity.

### 13.2. TelemetryProcessor.java

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.BlobContainerClientBuilder;

public class TelemetryProcessor {
    public static void main(String[] args) throws InterruptedException {
        String fqdn = requiredEnv("AZURE_EVENTHUBS_FQDN");
        String hub = requiredEnv("AZURE_EVENTHUB_NAME");
        String group = requiredEnv("AZURE_EVENTHUB_CONSUMER_GROUP");
        String account = requiredEnv("AZURE_STORAGE_ACCOUNT_NAME");
        String checkpointContainer =
            requiredEnv("AZURE_CHECKPOINT_CONTAINER");

        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();

        BlobContainerAsyncClient container =
            new BlobContainerClientBuilder()
                .endpoint("https://" + account + ".blob.core.windows.net")
                .containerName(checkpointContainer)
                .credential(credential)
                .buildAsyncClient();

        EventProcessorClient processor = new EventProcessorClientBuilder()
            .credential(fqdn, hub, credential)
            .consumerGroup(group)
            .checkpointStore(new BlobCheckpointStore(container))
            .processEvent(context -> {
                String partition =
                    context.getPartitionContext().getPartitionId();
                long sequence = context.getEventData().getSequenceNumber();
                String payload =
                    context.getEventData().getBodyAsString();

                // Demo only with non-sensitive synthetic data.
                System.out.printf(
                    "partition=%s sequence=%d payload=%s%n",
                    partition, sequence, payload);

                // Lab: demonstrates the checkpoint API only.
                // Production must durably commit to the sink before checkpointing.
                context.updateCheckpoint();
            })
            .processError(errorContext -> {
                System.err.printf(
                    "Processor error: %s%n",
                    errorContext.getThrowable().getMessage());
            })
            .buildEventProcessorClient();

        processor.start();
        try {
            Thread.sleep(120_000L);
        } finally {
            processor.stop();
        }
    }

    private static String requiredEnv(String key) {
        String v = System.getenv(key);
        if (v == null || v.isBlank()) {
            throw new IllegalArgumentException("Missing env: " + key);
        }
        return v;
    }
}
~~~

**Important:** Console output is not a durable sink. Use this example solely to observe synthetic events and checkpointing calls. In production, process strictly in order: **validate → deduplicate → commit sink durably → checkpoint**. Checkpointing before durable persistence risks silently losing events on crash; crashing after sink commit and before checkpoint causes redelivery.

Checkpointing too often increases Blob Storage operations; checkpointing too infrequently increases replay volume after crashes. Choose an interval balancing throughput, processing cost, idempotency, and recovery objectives.

### 13.3. Creating a New Consumer Group Does Not Guarantee Reading from the Beginning

The initial read position when no checkpoint exists depends on **the SDK/processor's API and start-position configuration**. Do not assume events always read from the start of retention. For replays, configure explicit start positions or use a dedicated app/consumer group/checkpoint store per SDK capabilities while events remain within retention.

Never delete production checkpoints just to re-run a demo: doing so can reprocess the entire retained stream and cause side effects if sinks lack idempotency.

## 14. Checkpoints, At-Least-Once Delivery, and Idempotent Sinks

Event Hubs stores streams and `EventProcessorClient` tracks checkpoints, but **writing to a target database** and **saving a Blob checkpoint** typically do not share an atomic cross-system transaction.

Suppose a consumer:

1. Reads an event with `eventId = evt-1001`.
2. Writes successfully to the target database.
3. Crashes before updating the checkpoint.
4. Restarts and re-reads `evt-1001`.
5. If it executes an unchecked `INSERT`, it writes a duplicate record.

Therefore, the architecture must anticipate **duplicates** and enforce idempotency at the sink.

~~~mermaid
flowchart TD
    A["Receive event from partition"] --> B["Validate schema and eventId"]
    B --> C{"Payload valid?"}
    C -->|"No"| D["Write durably to quarantine"]
    C -->|"Yes"| E{"eventId already committed?"}
    E -->|"Yes"| F["Skip duplicate side effects"]
    E -->|"No"| G["Upsert/transaction keyed by eventId"]
    G --> H{"Sink commit succeeded?"}
    H -->|"No"| I["Do not checkpoint; retry/alert"]
    H -->|"Yes"| J["Checkpoint per policy"]
    F --> J
    D --> K{"Quarantine write succeeded?"}
    K -->|"Yes"| J
    K -->|"No"| I
~~~

### 14.1. Sink Design

- Key uniquely on **`eventId`** or **`(deviceId, sequence)`** if the source strictly guarantees uniqueness.
- Use upserts or transactional deduplication in the target database/store.
- Distinguish same `eventId` + identical payload from same `eventId` + conflicting payload: the latter is a data integrity bug to investigate.
- For windowed aggregates, use a logical key like **`(deviceId, windowEnd, aggregationVersion)`** and an appropriate merge/upsert strategy rather than assuming `eventId` suffices.
- Checkpoint only after durable sink or quarantine persistence; when the sink fails, keep replay possible.

### 14.2. Quarantine Is Not an Automatic DLQ

**Event Hubs has no per-message Complete, Abandon, or built-in Dead-letter Queue like Service Bus.** When receiving an invalid-schema event, the processor can write a quarantine record to Blob Storage or a dedicated error queue:

~~~json
{
  "reason": "INVALID_EVENT_TIME",
  "source": "telemetry-events",
  "partitionId": "2",
  "sequenceNumber": 18842,
  "eventId": "unknown",
  "observedAt": "2026-11-20T08:19:01Z",
  "payloadReference": "quarantine/2026-11-20/18842.json"
}
~~~

Protect quarantine blobs with RBAC, retention, and encryption. Never dump sensitive raw payloads into logs. Checkpoint the bad event only after quarantine persistence is confirmed per business rules.

## 15. Consumer Lag and Parallelism Limits

A consumer group reading **N partitions** can have at most N active partition-owning workers at once. Scaling from 4 to 20 consumer processes in the same group when only 4 partitions exist does not create 20 partitions.

Monitor consumer lag **per partition**: latest sequence/offset, processed or checkpointed sequence, processing rate, errors, and time lag. An approximation:

\[
\text{Lag events} \approx
\text{latest sequence} - \text{last processed sequence}
\]

Always compare numbers **within the same partition**; note that the saved checkpoint may trail the most recently processed event.

### 15.1. Backlog Example

Producer emits **1,000 events/s**, while consumer processes only **800 events/s**:

\[
\Delta backlog=1.000-800=200\ \text{events/s}
\]

After 10 minutes, theoretical backlog grows by:

\[
200\times600=120.000\ \text{events}
\]

If the producer later drops to 700/s and the consumer runs at 900/s, drain rate is 200/s. Under ideal conditions it takes roughly **600 seconds** to drain 120,000 events. Real-world drain time also depends on bursts, restarts, retries, and sink latency.

If the consumer fails to catch up before retention expires, unread events become unrecoverable from Event Hubs. Alert on lag, scale capacity proactively, or archive raw events from day one.

### 15.2. Hot Partitions, Throttling, and Backpressure

- **Hot partition:** skewed `deviceId`/key distribution; inspect per-partition throughput and key skew.
- **Ingress throttling:** insufficient namespace/tier capacity, quotas, or service limits; adding consumers will not fix ingress throttling.
- **Sink throttling:** database/Storage cannot keep up; adding producers only worsens backlog.
- **Backpressure:** bound concurrency and in-memory buffers so RAM queues never grow unboundedly.
- **Retries:** use backoff, jitter, and overall deadlines rather than stacking infinite retry layers.

Data durability depends on retention, gateway buffering, and archiving. A gateway that must survive network outages needs a **bounded durable local buffer with an explicit overflow strategy**, not just an in-memory queue.

## 16. Observability with Azure Monitor and Application Insights

| Area | Metrics / signals to watch | Purpose |
| --- | --- | --- |
| Event Hubs ingestion | Incoming Messages/Bytes | How much data actually reaches the hub |
| Event Hubs read | Outgoing Messages/Bytes | Whether consumers are actively reading |
| Event Hubs errors | Throttled Requests, server/user errors per available metrics | Capacity, networking, or auth issues |
| Stream Analytics | Input Events, Output Events, watermark/latency, input/output errors | Whether the job is processing properly |
| Java producer | Attempted/sent events, retries, batch size, latency | Detects SDK/gateway issues |
| Java consumer | Processed events, duplicates, checkpoint age, lag | Tracks delay, replays, stalled progress |
| Blob | Transactions, authorization failures, output growth | Verifies checkpoint/output health |
| Business | Silent devices, sequence gaps, threshold breaches | Measures operational business health |

Metric names vary by tier, resource type, version, and Azure Monitor scope. **`IncomingMessages` does not equal transactions committed by the sink**: events can fail schema checks, duplicate, filter out, or wait in queues.

### 16.1. Sample KQL When Metrics Are Exported to Log Analytics

~~~kusto
AzureMetrics
| where TimeGenerated >= ago(1h)
| where MetricName in (
    "IncomingMessages",
    "OutgoingMessages",
    "ThrottledRequests")
| summarize total = sum(Total)
    by MetricName, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

This example follows the **`AzureMetrics`** schema. Azure Monitor metrics **are not stored in Log Analytics by default**. Configure diagnostic settings to export them, and verify exact metric names, columns, and aggregations. If your workspace lacks these rows, use **Metrics explorer** or supported APIs rather than assuming no data was recorded.

### 16.2. Alert Design

- Ingestion drops abnormally relative to the same-hour baseline.
- Throttled requests and send errors exceed operational thresholds.
- Stream Analytics job stops, logs input/output errors, or stops emitting on schedule.
- Consumer lag or checkpoint age grows continuously.
- Schema/quarantine failure rates spike after a release.
- Devices go silent past business thresholds.
- Log Analytics, Storage, or capacity costs spike unexpectedly.

Never alert on **`OutgoingMessages == IncomingMessages` every minute**, because multiple consumer groups, replays, and aggregations naturally create different counts across layers.

### 16.3. Correlation and Safe Telemetry

Include `eventId`, policy-compliant `deviceId`, `eventTime`, and partition/sequence for traceability. Never put `eventId` as a high-cardinality metric label. Never log raw payloads containing PII, tokens, or sensitive fields; govern trace/log retention, sampling, and viewer access.

## 17. Production Security, Networking, and Governance

For production:

1. Grant only **Data Sender** to producers, **Data Receiver** to consumers, and separate Blob roles for checkpoints/outputs.
2. Use managed identities where supported, minimize shared SAS keys, and enforce rotation plans.
3. Verify TLS, firewalls, private endpoints, DNS, outbound paths, and region settings.
4. Classify data; omit secrets, credentials, and unnecessary PII.
5. Set separate retention policies for Event Hubs, raw archives, outputs, and quarantine.
6. Enforce policies/auditing on changes to namespaces, consumer groups, jobs, RBAC, and schemas.
7. Monitor network/cross-region transfer costs and data residency compliance.
8. Test backup/DR or multi-region recovery against RTO/RPO instead of relying solely on retention.

**Consumer groups are not multi-tenant security boundaries.** To strongly isolate customer data, evaluate separate hubs/namespaces and separate downstream stores per security model.

## 18. Failure Scenarios and Recovery

| Incident | Likely behavior | Protection |
| --- | --- | --- |
| Gateway offline | Events fail to reach hub | Durable buffer, retry/backoff, bounded storage |
| Producer send timeout | Unclear if hub received event | Keep `eventId`, downstream dedup |
| Stream Analytics job stops | Aggregates stop updating | Alert, restart, replay within retention |
| Consumer crashes after sink write | Event redelivered | Idempotent sink, checkpoint after commit |
| Prolonged consumer lag | Unread events risk expiring retention | Capacity/alerts and raw archive |
| Invalid JSON schema | Parser/query fails or drops event | Validation, quarantine, metrics |
| Hot partition | One consumer overloaded | Inspect key distribution and partition capacity |
| Storage checkpoint 403 | Processor cannot save progress | Check RBAC/network; never fake success |
| Database sink throttling | Backpressure and lag | Bound concurrency, batch, retry budgets |
| Regional outage | Ingestion/processing disrupted | Dedicated DR/multi-region design, test RTO/RPO |

**Event Hubs does not provide end-to-end exactly-once guarantees** across producer, stream, processor, and database. Reliability relies on bounded retries, retention-based replayability, idempotent sinks, durable checkpoints, and structured error paths.

### 18.1. Controlled Replay

When an aggregation logic bug is discovered:

1. Identify the affected time window, consumer group, and sources still within retention or archive.
2. Run a dedicated processor/consumer group so production progress is unaffected.
3. Output the fixed logic to a **new output version** or staging target.
4. Reconcile counts, unique keys, window outputs, and diffs against old reports.
5. Swap official results only after approval with a rollback plan.

If data expired past retention with no archive, **never assume it can still be replayed**.

## 19. End-to-End Pipeline Costing

| Component | Cost drivers | Controls |
| --- | --- | --- |
| Event Hubs namespace/capacity | Tier, throughput/capacity per offer | Right-size and alert on throttling |
| Event Hubs retention/Capture | Raw event storage, Capture/Storage per tier | Appropriate retention/lifecycle |
| Stream Analytics | Capacity/job runtime and configuration | Stop lab jobs when done |
| Blob outputs/checkpoints | Stored bytes and operations | Tune batch/checkpoint intervals, clean up |
| Consumer compute | VMs/containers/App Service/Functions | Scale on lag and SLOs |
| Monitoring | Ingestion, retention, workspace features | Avoid logging every payload unnecessarily |
| Networking | Egress/cross-region transfers | Co-locate topology/regions thoughtfully |

A **43.2 GB/day** payload rate does not mean your bill covers only 43.2 GB of storage. The pipeline also incurs throughput/capacity, processor runtime, outputs, checkpoints, monitoring, and potential network transfer fees.

### 19.1. Hypothetical Cost Example

| Item | Illustrative amount |
| --- | ---: |
| Event Hubs capacity | 8.00 USD |
| Stream Analytics runtime | 5.00 USD |
| Blob output/checkpoint | 0.80 USD |
| Monitoring | 0.70 USD |
| Network / other | 0.50 USD |
| **Hypothetical total** | **15.00 USD** |

This is **not Azure pricing or a default budget**. Use the Pricing Calculator, contract rates, live tiers/configs, and Cost Management to estimate. Watch for resources that keep billing even after the producer stops.

## 20. End-to-End Testing Plan

A strong capstone needs a test matrix with inputs, expected outcomes, and evidence:

| Test | Condition | Expected outcome | Evidence |
| --- | --- | --- | --- |
| Ingestion | Producer sends 270 events | Metrics rise, zero send errors | Producer logs, Event Hubs metrics |
| Partition key | Three `deviceId`s | Per-device ordering within partition per rules | Partition ID, sequence |
| Aggregation | Send across minute boundary | Outputs grouped by device/site/window | Blob outputs, Stream Analytics metrics |
| Invalid JSON | Missing/bad `eventTime` or `temperatureC` | Flagged/dropped/quarantined per policy | Diagnostics and error sink |
| Duplicate | Resend same `eventId` | Sink does not duplicate business effect | Unique key / dedup checks |
| Late event | `eventTime` shifted back significantly | Handled per late-arrival policy | Watermarks / data errors / outputs |
| Consumer restart | Stop/start processor | Resumes from checkpoint; replays uncheckpointed tail | Checkpoint blobs, sequence |
| Independent consumers | Run ASA and Java concurrently | Both groups read independently | Consumer group configs |
| Throttling | Burst test with guardrails | No infinite retries or OOM | Error metrics, retry/lag |
| Authorization | Producer lacks Sender | Rejected per policy | Error and role scope |
| Cleanup | Delete after acceptance | No stray lab resources left | Inventory and Cost Management |

### 20.1. Testing Late Events

Send events with current `eventTime`, then `eventTime` **2 minutes** in the past, then **20 minutes** in the past in the lab only. Observe outputs, data errors, and out-of-order/late-arrival behavior. Record exactly which events were dropped, timestamp-adjusted, or accepted into which windows. Do not treat dropped old events as a service bug if your policy specifies dropping them.

### 20.2. Testing Restarts and Duplicates

Let the consumer write a batch to the sink, then intentionally terminate the process before checkpointing in a test environment. After restart, check which events reprocessed and verify unique-key/upsert logic prevented duplicates. Never run chaos tests in production or alter production checkpoints without approval.

### 20.3. Acceptance Criteria

- Producer sends valid events and Event Hubs ingests them per verified metrics.
- Stream Analytics writes outputs with sensible device/site/window values, sample counts, and aggregates.
- Java consumer reads independently in its own group with checkpointing and error handling.
- Duplicate events produce zero duplicate side effects in durable sinks.
- Invalid events are caught/quarantined without stalling the pipeline indefinitely.
- Consumer lag, watermarks, throttling, and output errors are monitored.
- Calculations for throughput, retention, replayability, and cost explicitly list assumptions.
- Permissions and cleanup procedures leave non-lab resources untouched.

## 21. Resource Cleanup After the Lab

1. Stop the Java producer/processor, and **Stop the Stream Analytics job**.
2. Archive non-secret acceptance evidence and retain raw/aggregate outputs per policy if needed.
3. Verify the resource group contains strictly lab resources authorized for deletion.
4. Check costs and any lingering billing sources (namespaces, jobs, Storage, logs).
5. Only with owner approval, delete lab resources and revoke temporary role assignments.

Command strictly to **inspect** before deleting:

~~~bash
az resource list --resource-group "$RG" -o table

# DANGEROUS: deletes the entire resource group. Run only after approval
# and confirming no shared resources exist:
# az group delete --name "$RG" --yes
~~~

Never assume deleting a resource group stops all charges from commitments or out-of-scope resources. Even when zero events arrive, namespaces and jobs can continue accruing charges per service model.

## 22. Common Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Producer 401/403 | Wrong credential, missing Sender role, RBAC propagation | Check tenant, role, scope, endpoint |
| Producer timeout | DNS, firewall, TLS, network, or throttling | SDK diagnostics, FQDN, network rules |
| Stream Analytics gets no events | Wrong hub/group, job stopped, start position | Input config, job status, metrics |
| Job Running yet Blob empty | Window hasn't closed, output permissions/query error | Watermark, Output Events, Blob auth |
| `AVG` is null/empty | `temperatureC` sent as string | Schema validation / typing |
| Old events missing in aggregates | Late-arrival policy or start position | Event time, enqueued time, policy |
| Java checkpoint 403 | Missing Storage Blob Data Contributor or network block | Checkpoint container, token, and RBAC |
| Consumer restart causes duplicates | Checkpoint trails sink commit | Unique keys, idempotent sink |
| Hot partition | Skewed partition key distribution | Per-key/partition metrics, partitioning strategy |
| Lag growing | Slow CPU/sink, throttling, or under-provisioned consumers | Per-partition lag, sink latency, errors |
| Replay finds no events | Retention expired with no raw archive | Check retention and Capture |
| Bill grows after producer stops | Namespace/job/storage/logs still active | Inventory and Cost Management |
| No metrics in KQL | Azure Monitor Metrics not exported to Logs | Diagnostic settings or Metrics explorer |

Never fix issues by granting subscription-wide Owner, committing SAS keys to Git, or disabling production network security. Pinpoint the exact failing layer and make minimal, reversible changes.

## 23. Capstone Exercises

### Exercise A — Architecture and Data Contract

Redraw the Event Hubs → Stream Analytics → Blob and `EventProcessorClient` → checkpoint/sink diagram. Label Sender/Receiver/Blob Contributor roles, consumer groups, event time, partition key, dedup key, and raw archive storage. Explain why two independent applications must not share a consumer group.

**Deliverable:** diagram showing data paths, security boundaries, event types, and observability plan.

### Exercise B — Build the Pipeline

Provision resources via CLI, configure Stream Analytics input/output, run the Java producer, inspect Event Hubs metrics, inspect Blob aggregates, and run `EventProcessorClient`. Record namespace/hub and consumer group names (no secrets), query, event counts, JSON outputs, and checkpoint status.

**Deliverable:** evidence with real lab environment data, explicitly noting any unverified items.

### Exercise C — Capacity

With **10,000 devices**, each sending 1 event/10 seconds, 500-byte payload:

1. Compute total **1,000 events/s**.
2. Compute raw ingress **0.5 MB/s**.
3. Compute daily raw payload **43.2 GB**.
4. Under a 3× burst, compute **3,000 events/s**.
5. List at least four additional limits to verify: tier event/byte rates, partition skew, retention, sink/consumer throughput, and storage/network costs.

**Deliverable:** sizing table with assumptions and limits, not just a single Throughput Units number.

### Exercise D — Duplicates and Invalid Events

Abbreviated events:

~~~json
{"eventId":"evt-1","deviceId":"device-101","eventTime":"2026-11-20T10:00:01Z","temperatureC":5.2}
{"eventId":"evt-1","deviceId":"device-101","eventTime":"2026-11-20T10:00:01Z","temperatureC":5.2}
{"eventId":"evt-3","deviceId":"device-101","eventTime":"not-a-time","temperatureC":"hot"}
~~~

Answer: which events are duplicates, which have invalid types/times, why quarantine before checkpointing, and which required fields from the full Section 5 schema are missing?

**Guidance:** the first two share `eventId`; the third has invalid `eventTime`/temperature; all three are abbreviated samples missing required fields from the full schema. Either define an abbreviated schema version or supply all required fields before production ingestion.

### Exercise E — Crash and Checkpointing

A consumer wrote 100 events to the database while its checkpoint was still at event 80, then crashed:

1. Which events can be re-read after restart?
2. Why does the database need unique keys/upserts?
3. Should checkpoints be saved per event or per batch/interval, and why?
4. If events past the checkpoint have already expired retention, how do you recover?

**Guidance:** events after the checkpoint can replay if still within retention; the sink must be idempotent; tune checkpointing by throughput, cost, and acceptable replay size; use raw archives to recover expired events.

### Exercise F — Operational Analysis

Choose three scenarios: hot partition, delayed ASA outputs due to watermarks, and rising Storage costs from raw capture. For each, document metrics, hypotheses, verification steps, SLO impact, and a change plan with rollback.

## 24. Self-Check Questions

**Q1.** Does Event Hubs delete an event after one consumer reads it?  
**Answer:** No. Events remain for the retention period; consumer groups read independently.

**Q2.** Why use `deviceId` as the partition key?  
**Answer:** It routes consistently and preserves per-device order within a partition, though skew must be watched.

**Q3.** Does Event Hubs guarantee global ordering across partitions?  
**Answer:** No. Ordering is per partition.

**Q4.** How does a checkpoint differ from retention?  
**Answer:** Checkpoints track consumer progress; retention governs how long events stay available to replay.

**Q5.** Why can a send timeout lead to duplicates?  
**Answer:** The service may have accepted the event before the acknowledgment was lost; the producer retries.

**Q6.** How does event time differ from enqueued time?  
**Answer:** Event time is when the source measured it; enqueued time is when the hub received it.

**Q7.** What does `TIMESTAMP BY eventTime` do in Stream Analytics?  
**Answer:** Uses the source measurement timestamp to assign processing windows.

**Q8.** Is an event arriving 20 minutes late guaranteed to update a closed window?  
**Answer:** No. It depends on late-arrival/out-of-order policies, watermarks, and job settings.

**Q9.** What happens if a consumer crashes after writing to the database but before checkpointing?  
**Answer:** Events may be re-read; the sink needs idempotency.

**Q10.** Does Event Hubs have per-event DLQs like Service Bus?  
**Answer:** No. You must design custom quarantine storage when needed.

**Q11.** With 4 partitions and 20 consumer instances in one group, do 20 partitions process in parallel?  
**Answer:** No. Partition count caps parallelism under partition ownership.

**Q12.** How many events/s do 10,000 devices sending every 10 seconds produce?  
**Answer:** 1,000 events/s, before bursts and retries.

**Q13.** Why is it normal for Stream Analytics output to have fewer records than input?  
**Answer:** Window aggregation combines many raw events into single summary records.

**Q14.** Does granting Sender to the job creator automatically grant Receiver to Stream Analytics?  
**Answer:** No. The job uses its own identity/credential.

**Q15.** What is needed to replay data once Event Hubs retention expires?  
**Answer:** A pre-configured raw archive and a controlled replay plan.

## 25. Acceptance Checklist

- [ ] Architecture diagram covers Event Hubs → Stream Analytics → Blob and the independent Java consumer branch.
- [ ] Schema includes `eventId`, `deviceId`, UTC `eventTime`, units, version, and validation.
- [ ] Namespace/hub, partitions, retention, tier, and region verified.
- [ ] Producers/consumers/jobs have appropriate roles and network access with zero exposed secrets.
- [ ] Java producer sends synthetic events cleanly with ingress metrics visible.
- [ ] Stream Analytics uses its own consumer group, one-minute query, and verified outputs.
- [ ] Distinguishes event time, enqueued time, processing time, and late-arrival policies.
- [ ] Java `EventProcessorClient` uses Blob checkpoints and a durable sink design.
- [ ] Duplicate events cause no duplicate side effects; invalid events are properly quarantined.
- [ ] Restarts, duplicates, invalid payloads, late events, and bursts tested in the lab.
- [ ] Metrics/alerts cover ingress, throttling, lag, processing errors, outputs, and business data.
- [ ] Capacity estimates cover events/s, bytes/s, partitions, bursts, retention, and throughput.
- [ ] Cost estimates cover Event Hubs, Stream Analytics, Storage, networking, and monitoring.
- [ ] Cost limits, owners, and a cleanup plan protecting production are documented.
- [ ] Final report distinguishes verified facts from remaining assumptions.

**Conclusion:** Azure Event Hubs provides a scalable telemetry ingestion layer enabling independent multi-consumer reads by partition and consumer group. Azure Stream Analytics handles time-window aggregations, while `EventProcessorClient` enables custom processing with checkpoints. A reliable pipeline requires **clean schemas, proper permissions, duplicate and late-event handling, idempotent sinks, lag monitoring, capacity planning, and cost control**. Once all these are verified, your team has a solid foundation to scale this lab into a production streaming system on Azure.
