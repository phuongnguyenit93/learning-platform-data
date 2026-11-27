# Event Hubs Namespace, Partition, and Consumer Group

A company has 50,000 IoT devices continuously sending temperature, coordinates, and operational status. The data needs to flow into a near-real-time analytics system, while another team archives raw data for historical analysis and operations monitors anomaly alerts. If every device called each processing application directly, the dependency web would grow complex and easily overload during traffic spikes.

**Azure Event Hubs** is a high-throughput **event streaming ingestion and distribution** platform. Producers write events to an Event Hub; data is organized into **partitions**, each with its own order. Downstream applications use **consumer groups** to read the same stream independently according to their own per-partition progress.

This lesson belongs to the **Events and Streaming Data** chapter of the `CLOUD_PROVIDERS_AZURE` module. The module introduces the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID through virtual networks, compute, storage, and data; it then guides deploying, monitoring, securing, and controlling costs for Azure application architectures. Here, the goal is designing the three levels—**namespace – partition – consumer group**—properly while understanding the implications for **ordering, scaling, retention, checkpointing, replay, access permissions, and cost**.

> Examples use synthetic names and data. SKUs, networking features, retention, throughput, partition/consumer group limits, and Azure CLI syntax can vary by tier, API, and region. Verify features on an actual namespace and run resource-creation commands only in an approved subscription/lab.

## 1. Learning Objectives

Upon completing this lesson, you will be able to:

1. Describe **Event Hubs namespace**, **Event Hub**, **partition**, **consumer group**, and **event producer/consumer**.
2. Trace the path of events from devices to multiple analytics consumers reading the same Event Hub.
3. Distinguish an **Azure subscription** from an **Event Hubs consumer group**.
4. Explain **partition key**, partition ID, offset, sequence number, and enqueued time.
5. Know why you should expect **ordering only within a partition**, not across the entire Event Hub.
6. Choose a partition count based on parallelism, partition keys, and long-term requirements.
7. Design multiple independent consumer groups and understand how partitions are shared among consumers in the same group.
8. Distinguish Event Hubs **retention** from application **checkpoints**, and run replays while data remains retained.
9. Choose throughput capacity models across Basic/Standard/Premium/Dedicated at a conceptual level.
10. Use Azure Portal, Azure CLI, and Python SDK to create/inspect Event Hubs and send/receive events in a lab environment.
11. Apply Microsoft Entra ID / managed identity, Azure RBAC, private networking, and monitoring.
12. Diagnose common issues such as consumer lag, hot partitions, misordered checkpoints, throttling, and events missing downstream.

## 2. When Do You Need Event Hubs?

An event can be a sensor reading, clickstream action, application log, device state change, or transaction record for analytics.

Example:

```json
{
  "deviceId": "sensor-1024",
  "eventType": "TemperatureMeasured",
  "occurredAtUtc": "2026-11-20T09:00:00Z",
  "temperatureCelsius": 27.4,
  "site": "factory-hcm"
}
```

Characteristics of streaming:

- Producers emit events continuously, often at high frequency.
- Consumers can process immediately or re-read from a historical position still within retention.
- One data stream serves multiple uses: analytics, archival, anomaly detection.
- A producer successfully sending an event **does not mean** a downstream consumer has processed it.
- Consumers can pause and catch up upon resuming, provided data has not aged out of retention.

Event Hubs fits **telemetry, clickstream, log ingestion, analytics pipelines, stream processing**, and high-volume data flows. If the workload requires queues, dead-lettering, settlement/locks, per-command retries, special business ordering, or transaction-based messaging, evaluate **Azure Service Bus**. The two services have different processing models.

## 3. Four Concepts You Must Distinguish

| Component | Nature | Purpose |
|---|---|---|
| **Namespace** | Event Hubs resource boundary: region, tier, endpoint, auth, and networking | Contains one or more Event Hubs; manages permissions, cost, and capacity |
| **Event Hub** | Logical event stream written into the service | Producers send events to the hub name; consumers read from the hub |
| **Partition** | An ordered log within an Event Hub | Distributes read/write load and provides per-partition sequence/offset |
| **Consumer group** | Independent consumption view over the same Event Hub | Lets applications read the same data at their own pace |

An illustrative layout:

```text
Azure subscription: Production
└── Resource group: rg-streaming-prod
    └── Event Hubs namespace: evh-platform-prod
        ├── Event Hub: device-telemetry
        │   ├── Partition 0: E0, E4, E9, ...
        │   ├── Partition 1: E1, E5, ...
        │   ├── Partition 2: E2, E6, ...
        │   └── Partition 3: E3, E7, E8, ...
        │
        │   Consumer group: realtime-analytics
        │   Consumer group: raw-archiver
        │   Consumer group: alert-engine
        │
        └── Event Hub: application-events
            ├── Partition 0
            ├── Partition 1
            └── Consumer group: diagnostics
```

**Never confuse** an Azure subscription—an Azure billing and governance scope—with an Event Hubs consumer group. A consumer group only organizes how **one Event Hub** stream is read; it is neither an Azure subscription nor a physical copy of the events.

## 4. Namespace: Entry Point and Governance Boundary

An Event Hubs namespace has a name and endpoint shaped like:

```text
<namespace-name>.servicebus.windows.net
```

The namespace defines key policies:

1. **Pricing tier, region, and capacity:** SKU and resource level to meet send/receive rates.
2. **Authentication/authorization:** Microsoft Entra ID / managed identity and/or SAS per configuration.
3. **Networking:** public access, network rules, Private Endpoint where supported by SKU.
4. **Service limits:** throughput, number of Event Hubs, consumer groups, partitions, connections, event size, etc.
5. **Monitoring:** metrics, diagnostic settings, alerts, resource logs.
6. **Environments and blast radius:** should Production and Development use separate namespaces?
7. **Recovery:** availability requirements, DR, regional dependencies, and historical data retention plans.

### A namespace is not an Event Hub

Creating a namespace **does not automatically create a default telemetry stream** for applications. You must create an **Event Hub entity** with the desired partition count and retention. A producer connecting to the right namespace with a nonexistent Event Hub name will still fail.

### Separating namespaces by environment

Example:

```text
evh-iot-dev       → simulated devices, dev logs, and sandbox permissions
evh-iot-staging   → load / schema / consumer deployment testing
evh-iot-prod      → live data, strict logging, budget, and access controls
```

You do not have to create one namespace per microservice. Decide based on shared quota/capacity, security boundaries, ownership, data residency, cost, and blast radius. If multiple teams share a namespace, measure aggregate ingress/egress and control how an overloaded producer impacts other streams.

## 5. Event Hub Entity: Data Stream, Not a Job Queue

An Event Hub is a set of append-only partitions with streaming semantics. Each new event is appended to one partition and assigned that partition's **sequence number** and **offset**, plus the service's enqueue timestamp.

```text
Producer A ─────┐
                │
Producer B ─────┼──> Event Hub: device-telemetry
                │         |
Producer C ─────┘         +-- Partition 0: [event][event][event]
                          +-- Partition 1: [event][event]
                          +-- Partition 2: [event][event][event]
                          +-- Partition 3: [event]
```

Producers do not send separately to each consumer group. **One copy of the event is appended to the stream**, and groups read the retained data from their own positions.

### Is an event deleted after a consumer reads it?

**No, not like a work-item queue.** One consumer group reaching the latest offset does not remove events from the Event Hub. Other groups can still read those events while **retention** remains active.

This is a major difference from a Service Bus Queue:

- Queue / Peek-Lock: consumer processes then calls Complete to remove the message from the queue.
- Event Hubs: consumer reads a stream position; events stay until retention expires, with no Service Bus Queue-style Complete/Abandon/DeadLetter per individual event.

Event Hubs does not automatically create a per-consumer-group DLQ like Service Bus. If you need to isolate schema-invalid events, design a **separate quarantine stream, Storage location, or error-handling pipeline** with proper security and replay policies.

## 6. What Is a Partition?

A **partition** is the unit of data sharding and parallel scaling within an Event Hub. Within each partition, accepted events have a **deterministic order**.

Example with two devices:

```text
Partition 0:
  seq=0 device-A 08:00
  seq=1 device-A 08:01
  seq=2 device-A 08:02

Partition 1:
  seq=0 device-B 08:00
  seq=1 device-B 08:01
```

In this diagram, sequence numbers are shown starting at 0 in each partition; actual numbers are broker-assigned and should not be guessed. **Sequence numbers in partition 0 and partition 1 do not form a single hub-wide sequence.**

### Partitions affect three things

- **Write distribution:** events from producers are spread across partitions.
- **Read parallelism:** an application can process multiple partitions concurrently.
- **Ordering scope:** order is preserved among events in **the same partition**, with no global ordering guaranteed across partitions.

Avoid claiming “Event Hubs always preserves the order of events sent from all producers.” That is false across multiple partitions, concurrent producers, retries, or concurrent downstream processing.

## 7. Partition Key: Routing Related Events to the Same Partition

A producer can specify a **partition key** so events sharing that key are typically hashed/routed to the same partition by the service's distribution logic.

Example requiring per-device ordering:

```text
Event(deviceId="sensor-101", sample=1) ─┐
Event(deviceId="sensor-101", sample=2) ─┼──> same partition
Event(deviceId="sensor-101", sample=3) ─┘

Event(deviceId="sensor-205", sample=1) ────> another partition,
                                             or potentially the same partition
```

**A partition key does not create a dedicated partition per `deviceId`.** Many distinct keys can hash into the same partition.

### How to choose a key

| Partition key | When useful | Risks |
|---|---|---|
| `deviceId` | Preserve per-device reading order | Very “chatty” devices can create a hot partition |
| `customerId` | Analyze per-customer action sequences | Certain customers generate disproportionately high traffic |
| `orderId` | Process events for one order in partition order | An unusual order emitting huge event bursts |
| No key specified | Need load spreading without key affinity | No guarantee related events land in the same partition |
| Direct partition ID | Very specialized workloads needing explicit mapping | Tightly couples topology, hard to scale, prone to imbalance |

Do not expect a partition key to solve every ordering problem. Applications must still emit events in proper sequence when it matters; a late retry can append an event **after** subsequent events despite having an older business timestamp.

### Pitfall when changing partition count

If partition count increases (where supported by tier/service), the hash mapping of partition keys **can change**. Events with the same key before and after the change will not necessarily stay on the same partition. Evaluate risks to key-ordered workflows, replays, and consumer checkpoints before increasing partition counts.

## 8. Hot Partition: Why Can Many Partitions Still Be Slow?

A **hot partition** occurs when most events land in one or a few partitions instead of distributing relatively evenly.

Example:

- Event Hub has 8 partitions.
- About 80% of events carry partition key `global`.
- Events sharing that key pile into a single partition.
- The other partitions sit mostly idle while the single reader on the hot partition bottlenecks.

Adding more consumer instances **does not** let dozens of consumers in the same consumer group read the same partition concurrently; typically one partition has one owner at a time under balanced processor models. A hot partition is fundamentally a **key distribution and per-partition processing throughput** issue.

Mitigations:

1. Measure event count, bytes, and lag per partition where tooling allows.
2. Inspect top partition keys and load skew.
3. If strict ordering on the current key is unnecessary, pick a higher-cardinality key.
4. For an ultra-hot key, consider controlled key sharding **only if losing strict whole-key ordering is acceptable** or if downstream reorders records.
5. Optimize consumer processing, batching, and vectorization.
6. Increase partition count only after reviewing feature limits, capacity, and mapping impact.

**Do not use a random key** if the business requires per-device or per-order ordering; randomization balances load at the cost of breaking required ordering boundaries.

## 9. Offset, Sequence Number, Enqueued Time

Three fields commonly seen in metadata of events ingested by Event Hubs:

| Field | Meaning | Scope |
|---|---|---|
| **Partition ID** | Partition holding the event | Within the Event Hub |
| **Sequence number** | Monotonically increasing integer assigned by the broker per partition | **Per partition** |
| **Offset** | Position in the partition log, exposed as service metadata | **Per partition** |
| **Enqueued time** | Timestamp when Event Hubs accepted the event | Event metadata; distinct from business timestamp in body |

Example:

```text
Event Hub: device-telemetry
Partition 2:
  [seq 304, offset X] sensor-101 at 08:00
  [seq 305, offset Y] sensor-205 at 08:01
  [seq 306, offset Z] sensor-101 at 08:02
```

Offsets `X/Y/Z` are illustrative placeholders. In code, always use the offset/sequence number returned by the SDK rather than computing them manually from payload byte lengths.

### Enqueued time differs from occurredAtUtc

A device may generate an event at 08:00 but, due to a network outage, only deliver it to Event Hubs at 08:15.

- `occurredAtUtc = 08:00` is the timestamp placed in the payload by the device/app.
- `enqueued_time = 08:15` is when the service accepted the event.
- The consumer processes it at 08:17.

These timestamps measure different things: network/producer delay, queueing/processing lag, and event-time watermarks. Do not blindly substitute enqueued time for event time when analyzing late-arriving events.

## 10. Retention: Data Persists for a Time Window

Azure Event Hubs retains events for a configurable **retention window** depending on tier and settings. Events are not deleted immediately when a consumer reads them, but old events drop out of readable range once retention expires.

```text
Time  ──────────────────────────────────────────────>
             |<------ retention window ------>|
             Old events                Newest events
             |
             +-- Once past retention, replay can no longer
                 read purged events from the source stream
```

### Key takeaways

- Consumer group A can lag behind group B without directly affecting B's read position.
- If group A stops too long and its unread offsets fall outside retention, **Event Hubs alone cannot replay those events**.
- Retention is an Event Hub storage property, **not a deadline for a consumer group**.
- Increasing retention buys more recovery time, subject to cost/tier limits, and does not restore data already purged before the change.
- Systems requiring months or years of retention should **export/archive data** to a suitable long-term store.

### Capture and historical storage

**Event Hubs Capture**, where supported by tier and config, can automatically write incoming streams to Azure Blob Storage or ADLS Gen2 in supported formats/destinations (commonly Avro). This helps build a raw data lake and support historical replay from Storage.

**Capture does not create a new consumer group** nor change how applications read offsets. You must design a separate workflow to re-read captured data when older than stream retention or when re-ingesting into the pipeline.

## 11. Consumer Group: Multiple Views Over One Stream

A **consumer group** represents a set of consumers cooperating to read an Event Hub under a single **logical view**.

Example:

```text
Event Hub: device-telemetry
   P0 ─ P1 ─ P2 ─ P3
    |    |    |    |
    +----+----+----+--> Consumer group: realtime-analytics
    |    |    |    |       Worker A / Worker B
    |    |    |    |
    +----+----+----+--> Consumer group: raw-archiver
    |    |    |    |       Worker C
    |    |    |    |
    +----+----+----+--> Consumer group: anomaly-detector
                           Worker D / Worker E / Worker F
```

Each group can read the same events at a different pace:

- `realtime-analytics` reads near the head of the stream to power dashboards.
- `raw-archiver` reads and writes events to Storage, safely lagging by a few minutes.
- `anomaly-detector` analyzes a different window and may replay within retention.

### Does a consumer group copy messages?

**No, not in the sense of physically duplicating data per group like a Service Bus topic subscription.** Groups are read views over **partitions holding the same underlying data**. Multiple groups can read independently while the data lives once in the Event Hub for its retention period.

Each group still adds **read operations, egress, and downstream compute cost**, so extra groups are not completely “free.” Access permissions and consumer group limits depend on tier and config.

## 12. One Consumer Group, Multiple Consumers: Partition Sharing

Within a group using an EventProcessor-style SDK with ownership/checkpoint coordination, active consumers in the **same group** divide partitions for parallel processing.

Example for a 4-partition Event Hub:

| Active consumer instances in same group | Expected logical assignment | Effect |
|---:|---|---|
| 1 | One instance handles all P0–P3 | Simple to operate; parallelism limited to one instance |
| 2 | Each instance holds ~2 partitions | Increases parallel processing |
| 4 | Each instance holds ~1 partition | Maximizes 4-partition ownership parallelism |
| 6 | At most 4 instances hold partitions at once; 2 sit idle without partitions | Extra instances do not increase partition parallelism |

This distribution is an **expected pattern**; actual balancing depends on SDK, partition ownership, liveness, rebalance duration, and processing speed. Simpler clients or different protocols coordinate differently; never assume every receiver auto-balances merely by sharing a consumer group name.

### What if two consumers share a group but use separate checkpoint stores?

This can cause **duplicate processing, ownership contention, out-of-sync positions**, or unexpected behavior depending on SDK and protocol. When using EventProcessorClient / Blob checkpoints, ensure:

- Instances of the **same application group** share the coordinated checkpoint store.
- **Different consumer groups** use separate checkpoint scopes/containers or explicit SDK isolation so environments never collide.
- An application does not accidentally run two versions sharing one consumer group and checkpoint store in unintended contention.
- Rollouts account for rebalance time, status visibility, and idempotency.

## 13. What Is a Checkpoint and Where Does It Live?

A **checkpoint** records **how far a consumer has processed** in each partition so that after a restart or rebalance it can resume from an appropriate position.

```text
Event Hub P0:  [100][101][102][103][104][105][106]
                               ^
                               |
Consumer processed through 103, checkpoint at 103

Restart → resumes per SDK/checkpoint position,
          avoiding re-reading the entire partition
```

Event Hubs **does not automatically store checkpoints for every consumer app** as built-in business state. With the **Azure Event Hubs SDK event processor**, a common pattern uses an **Azure Blob Storage checkpoint store** for partition ownership and checkpoints. Other engines (Spark, Kafka compatibility, Stream Analytics, etc.) manage state with their own stores.

### Distinguishing offset and checkpoint

- **Offset / sequence number:** assigned by Event Hubs to each event in a partition.
- **Checkpoint:** written by the **consumer/application**, marking where it can safely resume.
- **Consumer lag:** distance between the partition's latest position and observed consumption/checkpoint progress, depending on measurement method.

**Checkpointing does not delete events** from the Event Hub. Nor does it guarantee all application side effects committed.

### When should you write a checkpoint?

Typical safe order:

1. Receive an event or batch from a partition.
2. Process and durably write business/analytics output.
3. Only then persist the corresponding checkpoint.
4. If processing fails, retain retry capability and avoid checkpointing past unprocessed data.
5. On restart, the app may re-read a few events near the checkpoint; handlers must be idempotent.

If you checkpoint **before writing output** and the process crashes, data gets marked processed even though it was never written downstream. If you checkpoint too infrequently, restarts re-read more events and take longer to recover.

## 14. A Consumer Group Is Not an Exactly-Once Mechanism

A consumer reads event X, writes to the database successfully, and crashes before checkpointing. On restart, event X may be read again.

```text
Read X → Write DB success → crash → no checkpoint
                                      |
                                      v
                                  Restart
                                      |
                                      v
                                  Read X again
```

Therefore, a reliable consumer needs:

- **Idempotent processing**: no duplicate side effects when re-read.
- Stable **event ID or business key**, backed by unique constraints on database writes.
- **Checkpointing after committing** critical outputs.
- **Retry/backoff** for transient errors.
- **Quarantine** for unparseable or schema-invalid events.
- **Reconciliation** to catch missing records or incorrect totals.

Never treat a consumer group as equivalent to a queue subscription with Complete or an exactly-once guarantee for external transactions. Consumer groups organize **stream reads**; they do not solve end-to-end distributed transactions.

## 15. Starting Read Position: Earliest, Latest, Offset, Time

When an app has no checkpoint yet or performs a controlled replay, SDKs typically let you choose a starting position:

| Intent | Direction | Consequence |
|---|---|---|
| Read from start of retained data | Earliest / beginning of retained partition | May process large volumes and older events |
| Read only new events going forward | Latest | May miss events emitted before consumer started |
| Replay from an offset/sequence | Pick explicit position per API/SDK | Only works if offset is still within retention |
| Replay from a timestamp | Pick enqueued time / time offset if SDK supports | Based on broker enqueue time, not necessarily business event time |
| Resume with checkpoint | EventProcessor reads from saved checkpoint | Configured starting position usually applies only when no valid checkpoint exists |

**If the consumer already has a checkpoint**, setting `starting_position="-1"` in code may **not rewind the app to the start**: processors generally prioritize existing checkpoints per SDK behavior. To replay from the start, use a **dedicated replay consumer group/checkpoint store or a controlled offset reset workflow** designed to avoid duplicate side effects.

### Be careful when resetting

Deleting checkpoints or renaming a checkpoint container to “re-read everything” can cause:

- The entire group to reprocess days of data.
- Duplicate writes into databases/lakes.
- Spiking egress throughput and costs.
- Unintended alerts or business triggers.

Only reset after verifying retention, scope, downstream effects, idempotency, and budget.

## 16. How Consumer Groups Differ from Service Bus Topic Subscriptions

| Aspect | Event Hubs consumer group | Service Bus topic subscription |
|---|---|---|
| Primary goal | Multiple independent apps reading the same stream | Delivering pub/sub messages to each subscription with settlement |
| Data storage | Shared stream in partitions per retention | Each subscription holds its own logical backlog per filters |
| Progress | Consumer manages checkpoints/offsets | Broker manages message state, locks/settlement per entity |
| After reading | Events remain until retention expires | Messages can be Completed and removed from subscription |
| Ordering | Per partition | Per sessions and Service Bus mechanics |
| Retry/poison | App/processor builds its own workflow | Built-in Abandon, DeadLetter, and DLQ subqueue |
| Replay | Re-read offsets within retention | Cannot replay Completed messages automatically |
| Scaling | Parallelism bounded by partition count in group | Competing consumers, locks/sessions, and broker semantics |

A single system can use **Event Hubs for high-throughput telemetry** and **Service Bus for business commands**—you do not have to force one service into every role.

## 17. Choosing Partition Count During Design

Partition count is a pivotal decision because it governs parallelism and ordering scope.

Ask these questions:

1. How many consumer instances need to process in parallel per group?
2. What are expected ingress/egress rates in events/s and MB/s?
3. Do any keys require ordering?
4. Is key cardinality diverse enough to distribute load evenly?
5. Does payload size or consumer logic slow down a single partition?
6. Do we need headroom for 6–12 months of growth?
7. Do the tier/region allow creating or increasing partition counts, and what are the limits?
8. Can the application tolerate partition-key mapping changes if scaled later?

### Illustrative example

An Event Hub expects 40,000 events/second. Each consumer instance can handle ~8,000 events/second **in realistic benchmarks**, and keys are evenly distributed.

```text
Minimum instances by processing rate ≈ 40,000 / 8,000 = 5
```

Yet that is only a compute estimate. To run at least 5 workers in a consumer group with each holding partition ownership, the Event Hub needs enough parallel partitions and throughput capacity; 8 or 12 partitions might be chosen **if the tier supports it and testing confirms the need**. Never claim “8 partitions automatically handle 64,000 events/s”: throughput is also bounded by namespace capacity, ingress bytes, SDK, network, serialization, key skew, and downstream sinks.

### Is increasing partitions always safe?

No. Even in tiers that allow raising partition counts, consider:

- Changes to **partition-key → partition-ID mapping**.
- Checkpointing and rebalancing behavior.
- Ordering for existing keys.
- Maximum caps, and the fact that most SKUs do not allow reducing partition counts after creation.
- Rollout impact on downstream tools expecting fixed partition counts.
- Raising partition count does not automatically raise namespace throughput/processing units.

**Pick a partition count with sensible headroom at initial design**, without over-creating partitions needlessly, as coordination and monitoring complexity also increase.

## 18. Throughput Capacity Differs from Partition Count

A common architectural error is equating **partition count = throughput units**. They are two separate dimensions.

| Component | Determines | Does not determine |
|---|---|---|
| **Partition count** | Logical parallelism, ordering scope, key distribution | Automatically scaling total namespace capacity |
| **Throughput Units (TU)** on applicable tiers | Ingress/egress capacity per billing/quota model | Creating more partitions |
| **Processing Units (PU)** or dedicated resources on applicable tiers | Dedicated processing capacity | Guaranteeing fast downstream apps |
| **Capacity Units (CU)** on Dedicated | Cluster/dedicated tier capacity | Replacing real benchmarks |
| **Consumer instances** | Parallel execution via partition ownership | Exceeding partition count under one-instance-per-partition |

Across Event Hubs tiers, compare **Basic/Standard, Premium, and Dedicated** models and capabilities. Throughput caps, auto-inflate support, and partition limits differ; never apply a single TU figure across all tiers.

### Auto-inflate

Some namespace tiers/models support **Auto-inflate** to scale throughput capacity at configured thresholds. However:

- It does **not** automatically increase **partition count**.
- It does not guarantee consumers or downstream sinks can keep up.
- It does not guarantee zero throttling under every sudden spike.
- It increases cost as throughput capacity scales up.
- Verify limits and scale-down behavior for your tier.

For strict latency SLAs, benchmark actual throughput with real payloads and batch sizes rather than relying on Auto-inflate settings alone.

## 19. Event Batching and the Producer Model

Producers can send individual events or group multiple events into a **batch** within SDK size limits and APIs.

```text
Sensors
   |
   +-- E1 E2 E3 E4
   |
   v
Producer SDK
   |
   +-- EventDataBatch [E1 E2 E3 E4] (within size limit)
   |
   v
Event Hub → partition(s) per routing/partition key
```

Benefits of batching include lower network overhead and higher throughput. However:

- Batches must obey tier/API **size limits**.
- Events in a batch share partition routing per SDK/producer configuration.
- When specifying a partition key for a batch, all events in that batch route to the same partition.
- A producer blasting oversized or overly frequent batches can hit throttling.
- SDK retries can resend on ambiguous failures; apps need event IDs and idempotent downstream sinks.

**Never cram thousands of JSON records into one giant single event** without checking size limits, per-record replay needs, and downstream parsers. SDK-level batching and stuffing multiple business events into one payload are two very different designs.

## 20. Azure Portal: Creation and Verification Workflow

### Phase A — Create the namespace

1. Open the [Azure Portal](https://portal.azure.com/) and confirm tenant/subscription.
2. Search for **Event Hubs** and select **Create** to provision a namespace.
3. Choose resource group, region, globally unique namespace name, and appropriate tier.
4. Select capacity/throughput aligned with real workload needs and budget.
5. Review networking and private access requirements; note tier-dependent features.
6. Create the namespace and verify its endpoint and provisioning status.

### Phase B — Create the Event Hub

1. Open the new namespace and go to **Event Hubs** → **Create Event Hub**.
2. Name it `device-telemetry`.
3. Pick a partition count sufficient for expected parallelism.
4. Set retention based on tolerable outage duration and replay requirements.
5. Review Capture and schema/feature settings if applicable and supported.
6. Create and verify partition count, retention, and health.

### Phase C — Create consumer groups

1. Inside Event Hub `device-telemetry`, open **Consumer groups**.
2. Reserve `$Default` appropriately or create dedicated groups per application.
3. Create `realtime-analytics`, `raw-archiver`, and `anomaly-detector`.
4. Connect each application with its corresponding group name; never share `$Default` casually across apps.
5. Verify all apps observe new events at their own independent pace.
6. Verify checkpoint stores and partition ownership per group.

### Phase D — Operations

1. Assign least-privilege Sender/Receiver roles to identities.
2. Configure public/private networking, TLS, and DNS.
3. Enable metrics, diagnostic logs, and alerts.
4. Set budgets for Event Hubs capacity, Storage checkpoints/Capture, and processing compute.
5. Run restart, rebalance, and retention tests in a lab before scaling Production.

## 21. Azure CLI: Inspecting Namespaces, Hubs, Partitions, and Groups

The commands below are **read-only**. Replace placeholders with approved names.

### Check subscription and tenant

```bash
az account show \
  --query "{Name:name,Subscription:id,Tenant:tenantId}" \
  --output table
```

### View namespace

```bash
az eventhubs namespace show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<NAMESPACE_NAME>" \
  --query "{Name:name,Location:location,Sku:sku.name,State:provisioningState}" \
  --output json
```

### List Event Hubs in a namespace

```bash
az eventhubs eventhub list \
  --resource-group "<RESOURCE_GROUP>" \
  --namespace-name "<NAMESPACE_NAME>" \
  --output table
```

### View Event Hub configuration

```bash
az eventhubs eventhub show \
  --resource-group "<RESOURCE_GROUP>" \
  --namespace-name "<NAMESPACE_NAME>" \
  --name "device-telemetry" \
  --output json
```

In the output, inspect fields such as `partitionCount`, `messageRetentionInDays` (or equivalent API retention fields), and entity status/name. **ARM output does not replace runtime partition metrics**; to inspect partition begin/end sequence numbers, use Event Hubs SDK runtime partition properties with appropriate permissions.

### List consumer groups

```bash
az eventhubs eventhub consumer-group list \
  --resource-group "<RESOURCE_GROUP>" \
  --namespace-name "<NAMESPACE_NAME>" \
  --eventhub-name "device-telemetry" \
  --output table
```

This only verifies **the groups exist**; it does not prove consumers are running, checkpoints are saving properly, or consumers are keeping up with the stream.

## 22. Azure CLI: Creating Lab Resources

**The following commands create resources and may incur charges.** Run only in an authorized lab resource group, never directly against Production. Namespace names must be globally unique per Azure rules.

### Standard namespace

```bash
az eventhubs namespace create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --name "<UNIQUE_NAMESPACE_NAME>" \
  --location southeastasia \
  --sku Standard
```

### Event Hub with four partitions

```bash
az eventhubs eventhub create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --name device-telemetry \
  --partition-count 4
```

After creation, inspect actual retention in the Portal/CLI and adjust via supported parameters as needed; **never carry lab retention defaults blindly into Production**.

### Consumer groups for three applications

```bash
az eventhubs eventhub consumer-group create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --eventhub-name device-telemetry \
  --name realtime-analytics

az eventhubs eventhub consumer-group create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --eventhub-name device-telemetry \
  --name raw-archiver

az eventhubs eventhub consumer-group create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --eventhub-name device-telemetry \
  --name anomaly-detector
```

Once created, re-run `consumer-group list` and check tier, group count, and access permissions. You do not need to send live events yet to verify resources.

### Warning about $Default

Event Hubs typically includes a default consumer group named `$Default`. In Unix shells, `$` can be expanded as an environment variable if quoted improperly. Whenever passing `$Default` in CLI or scripts, preserve it literally (for example using single quotes in Bash). Never let multiple Production applications share `$Default` without a checkpoint/ownership plan.

## 23. Python SDK: Sending Events with Identity

In runtimes supporting Microsoft Entra authentication, use the SDK with `DefaultAzureCredential` instead of embedding connection strings with keys in source code.

Install packages in a test environment:

```bash
python -m pip install azure-eventhub azure-identity
```

Producer example:

```python
import json
import os
from datetime import datetime, timezone

from azure.eventhub import EventData, EventHubProducerClient
from azure.identity import DefaultAzureCredential

namespace = os.environ["EVENTHUB_NAMESPACE"]
hub_name = "device-telemetry"

credential = DefaultAzureCredential()

producer = EventHubProducerClient(
    fully_qualified_namespace=f"{namespace}.servicebus.windows.net",
    eventhub_name=hub_name,
    credential=credential,
)

with producer:
    batch = producer.create_batch(partition_key="sensor-1024")

    event = EventData(json.dumps({
        "deviceId": "sensor-1024",
        "temperatureCelsius": 27.4,
        "occurredAtUtc": datetime.now(timezone.utc).isoformat(),
    }))
    event.properties = {"eventType": "TemperatureMeasured"}
    batch.add(event)
    producer.send_batch(batch)

print("Sent lab event to Event Hubs.")
```

### Explanation

- `fully_qualified_namespace` is the FQDN `<name>.servicebus.windows.net`.
- `eventhub_name` selects the entity inside the namespace.
- `DefaultAzureCredential` acquires tokens from the runtime's available identity source.
- `partition_key="sensor-1024"` routes events sharing that key to the same partition per service mapping policy.
- `create_batch()` tracks batch size limits; `batch.add()` raises an error if an event does not fit.
- `send_batch()` confirms broker acceptance per SDK, **not** that downstream consumers processed the event.

Run with a **secret-free** environment variable:

```bash
export EVENTHUB_NAMESPACE="<UNIQUE_NAMESPACE_NAME>"
python send_event.py
```

`export` is for Unix shells; on Windows PowerShell, use PowerShell environment variable syntax. The producer requires the **Azure Event Hubs Data Sender** role at the appropriate scope plus network reachability to the namespace.

### When a batch is too large

Instead of forcing an oversized batch, follow this pattern:

1. Create a new batch.
2. Try adding an event.
3. If it no longer fits, send the current batch.
4. Create the next batch and add the rejected event.
5. If **a single event** exceeds the limit, adjust schema/payload or store the large object externally and send a reference.

Never truncate JSON strings arbitrarily to fit a batch, as that corrupts business data.

## 24. Python SDK: Consumer Group Reading Events

A consumer can read from the beginning of retained data or from the latest events, depending on starting position and checkpoints.

Simple example:

```python
import os
from azure.eventhub import EventHubConsumerClient
from azure.identity import DefaultAzureCredential

namespace = os.environ["EVENTHUB_NAMESPACE"]
hub_name = "device-telemetry"
group_name = "realtime-analytics"

def on_event(partition_context, event):
    if event is None:
        return

    print(
        "partition=", partition_context.partition_id,
        "sequence=", event.sequence_number,
        "offset=", event.offset,
        "enqueued=", event.enqueued_time,
    )
    # Do not print the full body if it contains personal/sensitive data.
    # This sample only observes; it does not process or checkpoint durably.

credential = DefaultAzureCredential()

with EventHubConsumerClient(
    fully_qualified_namespace=f"{namespace}.servicebus.windows.net",
    eventhub_name=hub_name,
    consumer_group=group_name,
    credential=credential,
) as client:
    # "@latest": watch only new events arriving after start;
    # does not replay older retained events.
    client.receive(on_event=on_event, starting_position="@latest")
```

This is a **continuous consumer** that runs until terminated; never run it in a Production terminal without knowing how to stop it cleanly. It lacks a checkpoint store, scale coordination, retries, and graceful shutdown, so it is **not a Production processor template**.

### Reading from the beginning of retained data

Some SDK APIs use `starting_position="-1"` to start at the earliest retained position in each partition. However:

- Check your SDK/API version and `EventPosition` semantics.
- You cannot read events past retention.
- When a checkpoint store is attached, processors usually prioritize checkpoints over starting position.
- Re-reading can trigger duplicate side effects; use a separate lab consumer group.

### Why use separate groups?

If the analytics app and an ad-hoc test script share the same consumer group without coordinated ownership and checkpointing, results become unpredictable and cause duplicate processing or stalls. Practice scripts should use a dedicated consumer group and appropriate permissions rather than stealing partitions from Production workloads.

## 25. Event Processor and Blob Checkpoint Store

When running multiple consumers in the same Production group, use a processor model with **partition ownership and checkpointing**.

Reference design:

```text
Event Hub: device-telemetry
    |
    +-- P0 ----┐
    +-- P1 ----┤
    +-- P2 ----┤
    +-- P3 ----┘
           |
           v
Consumer group: realtime-analytics
    |
    +-- Consumer instance A
    |      ├── processes P0, P1
    |      └── writes checkpoints / ownership
    |
    +-- Consumer instance B
           ├── processes P2, P3
           └── writes checkpoints / ownership
                   |
                   v
          Azure Blob Storage
          container: checkpoints-analytics
```

### Why a Blob checkpoint store?

Several Azure Event Hubs Event Processor libraries use Azure Blob Storage to persist:

- Partition ownership claims across instances.
- Last processed position / checkpoint.
- Metadata needed for partition rebalancing.

**Blob Storage here stores consumer application state**, not a full copy of the stream. Deleting the checkpoint container forces the application back to its starting position or full reprocessing depending on config.

### Operational requirements

- Storage account/container must exist and be reachable over the network from consumers.
- Managed identity needs appropriate Blob data-plane permissions, typically **Storage Blob Data Contributor** for checkpoint stores requiring lease/write operations.
- Isolate checkpoint containers per application/consumer group per SDK conventions so environments never collide.
- Do not place the checkpoint store across high-latency regions or unreliable paths.
- Monitor Storage/permission/lease errors and post-rebalance lag.
- Persist checkpoints only after data is processed according to application semantics.

### Handler pseudocode

```text
on_event(partition_context, event):
    if event is None:
        return

    event_id = extract_business_id(event)
    if not already_processed(event_id):
        persist_result_and_dedupe_marker(event_id, event)

    partition_context.update_checkpoint(event)
```

This is **pseudocode**, not complete Python. In the real SDK, `update_checkpoint` requires a configured checkpoint store and may be async in the async client. Check the exact signature for your library version.

**Do not mechanically checkpoint every single event if throughput is very high and Storage checkpoint writes become a bottleneck.** You can checkpoint per batch, event count, or time interval, accepting a bounded replay window on crashes.

## 26. Retention, Checkpoints, and Replay: Real-World Scenario

Suppose an Event Hub retains data for **5 days** per illustrative config. The Analytics consumer processes up to Monday 12:00 and then stops for 2 days. When restarted on Wednesday:

- If its checkpoints still point to events within retention, the consumer resumes from saved positions and catches up.
- If the consumer stayed down past retention, checkpoints point to purged positions no longer in the stream.
- If checkpoints are corrupt or lost, starting behavior depends on SDK/starting position, risking heavy reprocessing or skipped events.
- If critical data aged out of retention, you need an external history store such as Capture/Storage or an event archive.

### Replaying to recompute results

Suppose the ML team needs to recompute statistics from 09:00 to 10:00:

1. Confirm the events are still within retention.
2. Create a **separate replay consumer group** or isolated checkpoint scope safely.
3. Start from the target time or offset.
4. Read events and write output to a **new dataset/version** instead of overwriting Production immediately.
5. Compare record counts, checksums, schemas, and business metrics.
6. Once verified, switch downstream consumers to the validated dataset.
7. Clean up lab consumer groups/checkpoints per procedure.

Never reset checkpoints on a group powering a live Production dashboard just to run an offline experiment when you can isolate a separate group.

## 27. Event Hubs Capture and Long-Term Data Architecture

Streaming architectures often balance two opposing needs:

- **Fast analytics** on fresh events.
- **Long-term retention** of raw data for reprocessing, model training, or auditing.

Reference architecture:

```text
IoT devices / App logs / Producers
             |
             v
       Event Hubs namespace
             |
       Event Hub: telemetry
       P0 | P1 | P2 | P3
             |
       +-----+----------+
       |                |
       v                v
CG: realtime        Capture / archival
    analytics           |
       |                v
       v           Blob Storage / ADLS
Dashboard / Alerts      |
                        v
                 Batch analytics / ML
```

When Event Hubs Capture is enabled, data is written into files by configured time/size windows to supported destinations and formats. Never assume Capture is an automatic **exactly-once transactional data lake**: inspect late files, duplicate records during pipeline re-ingestion, Storage partitioning, and data validation.

### Does Capture replace checkpoints?

No. Capture is a long-term archival path; consumer group / processor checkpoints track each application's read progress. An analytics worker still manages its own offsets/checkpoints even when Capture is enabled.

## 28. Azure Event Hubs and Kafka Compatibility

Azure Event Hubs supports the **Apache Kafka protocol** on supported tiers/settings so Kafka clients can connect to Event Hubs endpoints with compatible configuration. This is **protocol compatibility**, meaning users do not get every single feature or operational semantic of a self-managed Kafka cluster.

Conceptual mapping:

| Event Hubs | Closest Kafka term |
|---|---|
| Event Hub | Topic |
| Partition | Topic partition |
| Consumer group | Kafka consumer group |
| Offset | Read position in partition |
| Namespace endpoint | Broker endpoint in compatibility layer |

Use caution:

- Not all Kafka APIs or admin operations work identically to a standalone Kafka cluster.
- SASL/TLS/auth, broker endpoints/ports, and namespace settings differ from standard Kafka setups.
- Never share one consumer group between a Kafka client and the Event Hubs SDK to manipulate offsets/checkpoints arbitrarily without understanding both models.
- Kafka offset commits work differently from the Event Hubs SDK Blob checkpoint store.
- When migrating from Kafka, test producer acknowledgments, retries, ordering, topic settings, and retention.

**A Kafka consumer group does not automatically use an Event Hubs SDK Blob Storage checkpoint store** like a Python EventProcessorClient app. Build according to the active protocol/library and never mix two offset-tracking models.

## 29. Microsoft Entra ID, Managed Identity, and Azure RBAC

Applications sending to or receiving from Event Hubs require **data-plane permissions** on the appropriate namespace or Event Hub.

| Azure role | Purpose |
|---|---|
| **Azure Event Hubs Data Sender** | Allows producers to send events |
| **Azure Event Hubs Data Receiver** | Allows consumers to receive events |
| **Azure Event Hubs Data Owner** | Broader data-plane rights; grant only when corresponding administration is genuinely required |

Use **managed identity** for VMs, AKS, Functions, or Container Apps where supported. For local labs, `DefaultAzureCredential` can use an authorized Azure CLI/IDE session identity.

### Example role assignment

```bash
az role assignment create \
  --assignee-object-id "<PRODUCER_PRINCIPAL_ID>" \
  --assignee-principal-type ServicePrincipal \
  --role "Azure Event Hubs Data Sender" \
  --scope "<EVENT_HUB_RESOURCE_ID>"
```

**This command modifies Azure RBAC permissions**; run only with authorization. Client ID and principal/object ID of a managed identity are not the same value. When creating a role assignment, verify the exact principal, role, and scope.

### Management permissions differ from data plane

Someone with Azure RBAC to manage a namespace (control plane) **does not automatically** have permission to read event payloads via SDK. Conversely, a Data Receiver cannot automatically change SKU or delete the Event Hub.

When using a **Storage checkpoint store**, the consumer identity also needs separate **Blob Storage permissions**; Azure Event Hubs Data Receiver alone does not permit writing Blob checkpoints.

## 30. SAS Keys and Reducing Credential Risk

Some Event Hubs clients use **Shared Access Signatures (SAS)** or connection strings. While supported, access rights and key lifecycles must be tightly restricted.

Principles:

- Never put connection strings, SAS tokens, or primary/secondary keys into Git, plaintext manifests, or logs.
- Never grant overly broad policies to apps that only need Send or Listen.
- Prefer Microsoft Entra ID / managed identity wherever feasible.
- Store mandatory credentials in Azure Key Vault or an approved secret manager.
- Rotate keys periodically or upon suspected exposure; monitor all producers/consumers before revoking old keys.
- Restrict permissions to list keys and modify authorization rules.
- Enable alerts on policy/role changes and review audit logs.

**A namespace-wide SAS policy with Listen rights should never become a shared credential for dozens of teams.** Broad scope makes revoking a compromised app painful and widens blast radius.

## 31. Networking: TLS, Firewall, and Private Endpoint

To connect to Event Hubs, a client needs:

1. Proper DNS resolution of the namespace hostname.
2. Routing and outbound connectivity to the endpoint.
3. TLS and an SDK-supported transport protocol.
4. Accepted credentials/tokens.
5. Send or Listen permissions on the target Event Hub.

Some Azure Event Hubs SDKs use **AMQP over TLS** (typically port 5671) or **AMQP over WebSockets** (typically port 443). Kafka-compatible clients have their own endpoint/TLS/port requirements, commonly port 9093 for Kafka TLS setups. **Do not assume every client automatically falls back from 5671 to 443** when a firewall blocks a port—transport must be configured in the SDK.

### Private Endpoint

Where supported by tier and configuration:

- Private Endpoint routes namespace access over a private IP inside your VNet per service model.
- Private DNS must resolve the namespace hostname to the private IP.
- NSGs, firewalls, UDRs, and return paths must still allow traffic.
- Microsoft Entra authorization or SAS remains mandatory.
- On AKS / Container Apps, test DNS from **actual Pods/runtime**, not merely an admin laptop.

**Private Endpoint does not magically order data, extend retention, or grant unauthorized event access.** It only changes the network path and exposure surface.

## 32. Metrics, Lag, and Alerts

Azure Monitor supports metrics and diagnostic logs for Event Hubs per feature/config capabilities. Common namespace/entity signals include:

| Signal | Meaning | Action needed |
|---|---|---|
| **Incoming messages** | Events sent during interval | Compare with expected rate; detect stalled producers |
| **Incoming bytes** | Inbound data volume | Compare against capacity, payload size, and budget |
| **Outgoing messages / bytes** | Volume read by consumers | Does not automatically mean business processing succeeded |
| **Throttled requests** | Requests hitting tier capacity/throughput limits | Check TU/PU/CU, batching, retries, and quotas |
| **Server errors** | Service/connection-side errors per metric | Cross-check Azure status, client SDK logs, and blast radius |
| **User errors** | Client config, auth, entity name, or size errors | Inspect code, config, RBAC, and network |
| **Active connections** | Connection count per available metric | Detect client churn or connection leaks |
| **Capture/archival errors** | Capture pipeline failing on Storage destination/permissions | Check destination, identity, and logs |
| **Consumer lag** | Gap between stream head / ingress rate and consumer progress | Measure per group/partition using processor metadata and checkpoints |

### Lag is not always a built-in namespace metric

A namespace may report healthy total incoming/outgoing metrics while **one specific consumer group** falls behind. To measure true lag for that group:

1. Fetch **latest sequence/offset** per partition via supported runtime properties/APIs.
2. Fetch **checkpoint / last processed position** for the consumer group.
3. Compute per-partition sequence/offset delta (where representation matches).
4. Measure **age** of the event currently being processed, or elapsed time from enqueued time to processed time.
5. Set thresholds aligned with SLOs, error rates, and backlog recovery time.

Never add offsets across partitions as a single hub-wide number, or treat namespace-level outgoing/incoming message ratios as exact consumer lag for each group.

### Recommended alerts

- Producer suddenly stops sending events during expected traffic hours.
- Persistent rise in throttled requests.
- Consumer lag or processing delay for critical groups exceeds thresholds.
- Frequent checkpoint failures or partition ownership churn.
- Severe partition skew or hot partition slowing delivery.
- Capture failing to write to Storage or output files overdue.
- Unauthorized errors, token expirations, and network connection failures.
- Spending exceeding budgets for Event Hubs throughput, Capture, checkpoints, or compute.

## 33. Troubleshooting: Events Send Fine, Yet a Group Does Not Process

“Missing events” issues require layered triage:

| Symptom | Likely cause | Check |
|---|---|---|
| `EventHubNotFound` / entity not found | Wrong hub/namespace name or uncreated entity | ARM listing, client FQDN, and `eventhub_name` |
| `Unauthorized` | Identity lacks Sender/Receiver or invalid SAS | Role/scope, token, permissions |
| Connection timeout | DNS, firewall, Private Endpoint, TLS/transport | Client network path and SDK errors |
| Sends throttled | Exceeded throughput capacity/quota | Incoming bytes, throttling, tier, and batching |
| Producer succeeds yet consumer sees nothing | Wrong group/hub, started at `@latest` after send, checkpoint ahead of event | Timeline, starting position, checkpoint store |
| One group works, another fails | Group-specific app, identity, processor, or checkpoint error | Compare groups, receiver logs, Blob permissions |
| Only one partition has high lag | Hot partition or slow consumer on that partition | Key distribution, partition owner, processing time |
| Two consumers process duplicates | Retries, replay, ownership conflict, or bad checkpoints | Event ID, checkpoints, handler idempotency |
| Old data reprocessed on restart | Starting at earliest or stale checkpoint | Starting position, checkpoint store, and retention |
| Old events cannot be replayed | Aged past retention | Retention settings, Capture/Storage archive |
| Kafka consumer not committing offsets | Protocol/client config, permissions, group offset management | Kafka client logs, compatibility support |
| Consumer reads yet sink lacks data | App crashed post-read, sink write failed, wrong checkpoint order | App logs, DB/storage transactions, checkpoint position |
| Capture produces no new files | Destination config, storage network/permissions, capture window, platform issue | Capture config, Storage destination, logs/metrics |

### Investigation workflow

1. **Right subscription/resource group/namespace/hub?** Never rely on similar-looking environment names.
2. **Did the broker accept the producer's event?** Record Message ID / application event ID and UTC timestamp.
3. **Which partition received the event?** Check runtime metadata or producer logs if captured.
4. **Does the consumer group exist and match?** Verify `consumer_group` and permissions.
5. **Where does the checkpoint sit relative to the event?** Determine actual starting position.
6. **Is partition ownership stable?** Look for rebalances or competing apps.
7. **Did the application finish processing?** Check logs and output sinks, not just SDK callbacks.
8. **Are there sink errors?** DB, Blob, Spark job, schema, or quota errors.
9. **Is data still within retention for replay?** If not, use your designed archive/source.
10. **Can you recover safely?** Isolate replay groups, version outputs, and reconcile.

Never delete a consumer group or checkpoint container in Production to “start fresh” without a duplicate-prevention plan.

## 34. Scenario A: New Consumer Group Misses Older Events

**Context:** the Audit team creates consumer group `audit-review` at 15:00. They want to read an event from 14:00 and report “Event Hub lost messages” because their app only receives new events.

Two possibilities:

- The 14:00 event is **still within retention**, but the app uses `starting_position="@latest"` and starts near current time.
- The event **aged out of retention** or the producer sent to a different hub/namespace.

Workflow:

1. Verify whether the event was accepted and which Event Hub received it.
2. Check retention and broker enqueue timestamp.
3. Inspect consumer group, SDK starting position, and checkpoint store.
4. If still within retention, run a **controlled replay** with the right starting position.
5. If past retention, inspect Capture/raw archive.
6. Isolate replay output and prevent duplicate side effects before merging into Production.

**Lesson:** creating a consumer group later **does not block reading older retained data**, nor does it automatically rewind the app; starting position and checkpoints govern where reading begins.

## 35. Scenario B: Consumer Lag Keeps Growing After Adding Instances

**Context:** an Event Hub has 4 partitions; the analytics team scales from 4 instances to 10 instances. Lag still climbs.

Investigation:

1. A group on 4 partitions **cannot have 10 independent partition owners** under EventProcessor's one-owner-per-partition model.
2. Check which partition has high lag: perhaps only P2.
3. Check partition keys: the producer uses `partition_key="global"` for most traffic.
4. The consumer on P2 is blocked waiting on a slow database sink.
5. The namespace may have plenty of throughput while downstream cannot keep pace.

Remediation:

- Adjust keying strategy consistent with ordering requirements.
- Optimize batching and DB writes instead of merely adding worker instances.
- Introduce safe internal concurrency within processing without breaking required ordering.
- Evaluate partition count and capacity if truly bottlenecked, planning key-mapping migration carefully.
- Monitor per-partition lag and cost per event.

**Lesson:** scaling consumer instances beyond the number of partitions does not increase partition-level parallelism.

## 36. Scenario C: Analytics Writes Duplicates After Restart

**Context:** an analytics processor writes thousands of rows to SQL, then one node crashes. On restart, recent events are re-read and revenue reports double.

Root cause:

- The worker wrote to SQL successfully **without checkpointing**.
- On restart, the processor resumed from the older checkpoint.
- The sink lacked idempotent event handling.

Remediation:

1. Stop further corruption; preserve logs and event IDs.
2. Determine the last checkpoint before the crash and the replay window.
3. Reconcile results using business IDs / event IDs.
4. Add unique constraints / inbox markers and proper transactions.
5. Checkpoint only after durable persistence succeeds.
6. Replay into a test output to verify; repair Production data under approval.
7. Add alerts for checkpoint failures and duplicate events.

**Lesson:** checkpoints enable resumption, **not** exactly-once guarantees for data outside Event Hubs.

## 37. Hands-On Exercise: Telemetry for Multiple Processing Teams

**Context:** a factory has 6,000 sensors sending temperature events; the business wants a per-minute dashboard, raw archival, and anomaly detection.

| Component | Illustrative value |
|---|---|
| Resource group | `rg-stream-lab` |
| Namespace | `evh-factory-lab-unique` |
| Event Hub | `device-telemetry` |
| Lab tier | Standard |
| Partitions | 4 |
| Partition key | `deviceId` |
| Consumer group 1 | `realtime-analytics` |
| Consumer group 2 | `raw-archiver` |
| Consumer group 3 | `anomaly-detector` |
| Checkpoints | Separate Azure Blob Storage container per group |
| Retention | Per exercise window and tier limits |
| Producer permission | Azure Event Hubs Data Sender |
| Consumer permissions | Azure Event Hubs Data Receiver |

### Practice Tasks

1. Draw the diagram: namespace → Event Hub → 4 partitions → 3 consumer groups.
2. Distinguish an Azure subscription from a consumer group.
3. Explain how partition key `deviceId` affects ordering.
4. State why different sensor IDs **can** land in the same partition.
5. Estimate maximum ownership-based parallelism with 2, 4, and 6 consumer instances.
6. Provision lab resources (if authorized) and inspect config via CLI.
7. Send 10 synthetic events using the Python SDK with application property `eventType`.
8. Run a consumer in `realtime-analytics` to observe event metadata.
9. Run a consumer in `raw-archiver` and confirm it reads the **exact same event IDs**.
10. Set up a checkpoint store and explain required Blob Storage permissions.
11. Stop a consumer, send new events, restart it, and observe resume/replay.
12. Compare starting at latest vs. earliest on a separate lab group; explain the difference.
13. Suppose one partition receives 90% of events; propose how to detect and mitigate the hot partition.
14. Suppose the analytics group stays down longer than retention; propose how to recover historical data.
15. Design 3 alerts: throttling, consumer lag, and checkpoint failures.
16. Estimate cost drivers across Event Hubs, checkpoint/Capture Storage, and processing compute.
17. Describe how to clean up lab resources without deleting a shared namespace.

### Guided Solution

**Architecture:**

```text
6,000 sensors
     |
     v
Event Hubs: device-telemetry
     |
P0 -- P1 -- P2 -- P3
 |     |     |     |
 +-----+-----+-----+------> CG realtime-analytics → dashboard
 |     |     |     |
 +-----+-----+-----+------> CG raw-archiver     → Blob archive
 |     |     |     |
 +-----+-----+-----+------> CG anomaly-detector → alerts
```

**Ordering:** with partition key `deviceId`, events sharing a key route to one partition per active mapping; ordering holds within that partition log, not across the entire Event Hub. Multiple keys share the same partition.

**Parallelism:** with 4 partitions, 2 instances hold roughly 2 partitions each; 4 instances hold 1 partition each; 6 instances leave 2 instances without partitions under the ownership model.

**Groups:** each group reads the same events without “consuming away” events from other groups, provided events stay within retention and starting positions/checkpoints are configured appropriately.

**Checkpoints:** persist progress externally, typically via a Blob checkpoint store; Event Hubs does not auto-store checkpoints for every app. Separate Blob permissions are required alongside Event Hubs Data Receiver.

**Recovery:** if events aged out of retention, recover from archive/Capture or the original data source if available; never reset checkpoints expecting the broker to hold infinite history.

**Acceptance:** all consumer groups receive expected events and can stop/resume via checkpoints; no duplicate writes occur on replay; monitoring catches errors and spend stays within lab bounds.

## 38. Self-Check Knowledge Quiz

**Question 1.** How do a namespace and an Event Hub differ?

**Answer:** A namespace governs endpoint, tier, permissions, networking, and capacity; an Event Hub is the entity holding the partitioned stream.

**Question 2.** When one consumer finishes reading an event, is it deleted from Event Hubs immediately?

**Answer:** No. Events remain in the stream until retention expires or per service policy; other groups can read independently.

**Question 3.** Can global ordering be guaranteed across all partitions of an Event Hub?

**Answer:** No. Event Hubs provides per-partition ordering; there is no guaranteed single global order across different partitions.

**Question 4.** Does partition key `deviceId` create a dedicated partition for every device?

**Answer:** No. Many `deviceId`s hash into the same finite set of partitions.

**Question 5.** Does increasing partition count automatically increase namespace throughput capacity?

**Answer:** No. Partition parallelism and throughput capacity (TU/PU/CU depending on tier) are separate dimensions.

**Question 6.** There are 4 partitions and 10 worker instances in one consumer group. Can all 10 hold partition ownership simultaneously under EventProcessor?

**Answer:** No. Under the one-owner-per-partition model, at most 4 owners actively process the 4 partitions at once; extra instances remain unassigned.

**Question 7.** Does a consumer group hold its own physical copy of data like a topic subscription queue?

**Answer:** No. Consumer groups read the same underlying Event Hub partitions with independent progress.

**Question 8.** Does creating a new group automatically replay every event from the beginning of time?

**Answer:** No. Starting position and checkpoints decide where reading begins, and only events within retention are readable.

**Question 9.** Does Event Hubs automatically save checkpoints for every consumer group/app?

**Answer:** No. Applications/SDKs manage checkpoints through their respective store, such as an Azure Blob checkpoint store for Event Processor.

**Question 10.** Why can checkpointing before writing output lose results?

**Answer:** If the app crashes after checkpointing but before committing output, resuming skips the unfinished event.

**Question 11.** If SQL writes succeed but the app crashes before checkpointing, what issue can happen?

**Answer:** The event is re-read on restart, causing duplicate writes unless the sink is idempotent.

**Question 12.** How does `occurredAtUtc` differ from `enqueued_time`?

**Answer:** `occurredAtUtc` is the timestamp recorded by the device/app in the payload; `enqueued_time` is when Event Hubs accepted the event.

**Question 13.** Does Event Hubs have an automatic per-consumer-group dead-letter queue like Service Bus?

**Answer:** No. Downstream systems must design appropriate error handling and quarantine flows.

**Question 14.** If you want to replay data from 6 months ago while retention is only a few days, what do you do?

**Answer:** Rely on an archive, Storage, Capture, or another designed source; Event Hubs does not retain data beyond retention.

**Question 15.** Why can a hot partition cause lag even with many workers?

**Answer:** One partition receives most of the traffic and under the ownership model typically has only one processor owner at a time in a group; extra workers cannot split that single partition.

**Question 16.** Does Azure RBAC Data Sender automatically allow reading events?

**Answer:** No. Send and receive roles are separate; consumers need Data Receiver.

**Question 17.** Does Private Endpoint replace Microsoft Entra or SAS permissions?

**Answer:** No. Private Endpoint governs network path; authentication and authorization remain mandatory.

**Question 18.** Does a Kafka consumer group automatically use the Event Hubs SDK Blob checkpoint store?

**Answer:** No. Kafka clients manage offsets via their own protocol mechanism in the compatibility layer; never mix them arbitrarily with EventProcessor checkpoint stores.

**Question 19.** Why must consumer lag be monitored per group and per partition?

**Answer:** Namespace-level Incoming/Outgoing totals hide when a specific group falls behind; lag may also be concentrated on a single hot partition.

**Question 20.** Does successfully sending an event mean analytics computed the right result?

**Answer:** Not yet. Producer success only confirms Event Hubs ingested the event; consumers, checkpoints, sinks, and validation determine downstream accuracy.

**Question 21.** Should full payment card details or access tokens be included in telemetry events?

**Answer:** No. Events can reside in retention, Capture, logs, and analytics; minimize, mask/encrypt data appropriately, and enforce access control.

**Question 22.** If a consumer group fails to checkpoint while still reading events, what risks arise?

**Answer:** After restarts or rebalances, it may re-read many events, write duplicates, or fail partition handoff; monitor and fix the checkpoint store.

**Question 23.** Can increasing partition count change partition key routing?

**Answer:** Yes. Depending on tier and mapping behavior, the same key can route to a different partition afterward, affecting ordering assumptions.

**Question 24.** Does Event Hubs Capture replace application consumer checkpoints?

**Answer:** No. Capture archives stream data to Storage, whereas application checkpoints track each consumer's processing progress.

**Summary:** An **Event Hubs namespace** defines the resource, permission, network, and capacity boundary; **partitions** govern stream distribution and ordering scope; and **consumer groups** let multiple applications read the same data at independent paces. Operating reliably requires **well-chosen partition keys, sufficient partition parallelism, post-processing checkpoints, planned retention/replay, least-privilege permissions, and per-group lag monitoring**. Reliable streaming is not just sending events—it is **knowing which partition received each event, how far each consumer has processed, and how to recover accurate results when failures happen**.
