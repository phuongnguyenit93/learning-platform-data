# Distinguishing Event Routing and Event Streaming on Azure

When a customer uploads a product image to Azure Blob Storage, the system needs to know **a new file has appeared** to generate a thumbnail. When tens of thousands of devices continuously send temperature and operating status, the system instead needs to **ingest, retain, and analyze a massive sequence of data over time**. Both can be called “event processing,” but their goals, data consumption models, and suitable Azure services are very different.

**Event routing** focuses on detecting that an event has occurred and **routing notifications** to interested parties. **Event streaming** focuses on **ingesting and retaining an ordered stream of records per partition** so multiple consumers can read, analyze, and replay within the retention period. On Microsoft Azure, the two representative services for these two models are **Azure Event Grid** and **Azure Event Hubs**. There is also **Azure Service Bus**, suited for job queues and reliable business messaging.

This lesson belongs to the **Events and Streaming Data** chapter of the **CLOUD_PROVIDERS_AZURE** module: exploring Azure from subscriptions, resource groups, Microsoft Entra ID, and virtual networks to compute, storage, and data; learning how to deploy, monitor, secure, and control the cost of an application architecture.

> **Key objective:** Choose the service based on the business contract: whether you need to **notify and trigger** an action, **read an event stream over time and replay it**, or **dispatch work with completion acknowledgement**. Having the word “event” in a payload does not by itself determine whether to use Event Grid or Event Hubs.

## Learning Objectives

After this lesson, you will be able to:

1. Explain events, event notifications, event streams, and commands/messages with concrete examples.
2. Distinguish **event routing**, **event streaming**, and **enterprise messaging** by delivery direction, retention, replay, ordering, and error handling.
3. Describe the basic structure of an **Event Grid topic, event subscription, filter, and event handler**.
4. Describe an **Event Hubs namespace, event hub, partition, partition key, consumer group, offset, and checkpoint**.
5. Recognize when to choose **Azure Service Bus Queue/Topic**, Azure Queue Storage, or Azure Functions as complementary components.
6. Design a Blob Storage → Event Grid → event-driven processing pipeline and a telemetry → Event Hubs → stream processor → storage/analytics pipeline.
7. Explain at-least-once delivery, duplicates, per-partition ordering, retention, retry, dead-lettering, and replayability.
8. Design authentication, RBAC, private networking, observability, and cost estimation for each model.

## 1. What Is an Event, and Why “Event-Driven” Does Not Mean “Streaming”

An **event** represents something that has happened, usually expressed in the past tense:

- **BlobCreated**: a new blob has been created.
- **OrderPlaced**: an order has been placed.
- **PaymentSucceeded**: payment has completed.
- **DeviceTemperatureObserved**: a device has just recorded a temperature.

An event can carry metadata such as **event ID**, **event type**, **source**, **time**, **subject/resource reference**, and additional data. The producer publishes the event without necessarily knowing exactly what consumers will do with it.

### Distinguishing event notification and event record

An **event notification** is usually a brief signal: “object X changed, take a look.” It may contain a blob URI, change type, and some metadata. The actual file content or full state usually remains in the source system.

An **event record in a stream** is part of a sequence of data that consumers need to analyze over time. For example, every second a device records temperature, humidity, and battery status. Consumers want to compute windowed averages, detect anomalies, and re-read historical data within the retention period.

### Events and commands are different

| Type | Example | Meaning |
|---|---|---|
| **Event** | OrderPlaced | A business event has occurred |
| **Notification** | BlobCreated | There is a change to notify interested parties about |
| **Command/job** | GenerateInvoice | Requests a worker to perform work |
| **Stream record** | SensorReading at 14:05:01 | A data sample belonging to a time-ordered stream |

A system can turn a notification into a command: **BlobCreated** is delivered by Event Grid to a function, which validates it and sends **GenerateThumbnail** to a Service Bus Queue. These are not two names for the same mechanism.

## 2. Quick Comparison of the Three Models

| Question | Event routing | Event streaming | Enterprise messaging |
|---|---|---|---|
| Goal | Notify and route events to handlers | Ingest and distribute a continuous stream of records | Transfer jobs/messages with processing state |
| Representative Azure service | **Azure Event Grid** | **Azure Event Hubs** | **Azure Service Bus** |
| What does the receiving side typically do? | Run a handler when a notification arrives | Actively read from partitions and save checkpoints | Receive message then Complete/Abandon/Dead-letter |
| Delivery direction | Typically push to destination; Event Grid Namespaces also offer suitable pull models | Consumers pull/receive stream from broker | Receivers actively receive from queue/subscription |
| Retention/replay | Configured retry/dead-letter; do not treat push notifications as an arbitrary replayable event log | Retention per tier/configuration; consumers can re-read within the retention window | Messages wait until settlement/expiry per entity mechanism |
| Ordering | Should not assume all notifications arrive in order | Ordered within **a single partition**, no global ordering across the whole event hub | Mechanisms such as sessions when grouping and ordering are required |
| Multiple independent consumers | Multiple event subscriptions/handlers | Multiple consumer groups with independent read positions | Topic with multiple subscriptions, queue for competing consumers |
| Load observation units | Published/matched/delivered/failed events | Throughput, partitions, offset/checkpoint/consumer lag | Active messages, locks, dead-letter, delivery count |
| Best suited for | Blob-created, resource change, webhook trigger | Telemetry, clickstream, logs, IoT streams, real-time analytics | Payments, background jobs, workflows, task dispatch requiring settlement |

**This is a directional comparison, not a claim that every version of a service has only one mode.** Event Grid also has Namespaces, MQTT, and pull delivery capabilities depending on supported features. Event Hubs has Kafka integration, Capture, and multiple capacity/tier options. Always verify current requirements before deciding.

## 3. Event Routing: “What Happened, and Who Needs to Be Notified?”

Suppose a user just uploaded an image to Blob Storage. The system needs to trigger thumbnail generation, safety scanning, and audit logging.

~~~text
Azure Blob Storage
    |
    | BlobCreated event
    v
Azure Event Grid
    |
    +-- Event subscription A -> Azure Function generating thumbnail
    |
    +-- Event subscription B -> Content inspection handler
    |
    +-- Event subscription C -> Audit endpoint
~~~

Key points to note:

1. **The event source** emits information that an action has occurred.
2. **Event Grid** receives the event and applies routing/filtering rules.
3. **The event subscription** defines which subset of events to receive and the processing destination.
4. **The handler** executes logic and can query the source data by reference.
5. If the handler does not respond properly or delivery fails, Event Grid provides retry/dead-letter mechanisms depending on destination type and configured policy.

Nothing in this diagram requires Event Grid itself to download the entire image or perform OCR. It only **delivers the signal to the right places**.

### Characteristics of routing

- Event subscriptions enable **fan-out** of one event to multiple handlers.
- Filtering helps reduce irrelevant events.
- Notifications are usually smaller than the source data, reducing coupling between producer and consumer.
- Receiving destinations must implement **idempotency** because delivery can be duplicated.
- Do not assume delivery ordering across notifications.
- Do not treat routing with retries as an infinite event history store.

## 4. Core Concepts of Azure Event Grid

| Concept | Explanation |
|---|---|
| **Event source** | Resource or application that emits events, e.g., Blob Storage |
| **System topic** | Represents the event stream from a supported Azure service |
| **Custom topic** | Endpoint where a custom application publishes custom events |
| **Event Grid Namespace** | Resource model with capabilities such as namespace topics, push/pull delivery, or MQTT as supported |
| **Event subscription** | Filter, delivery policy, and handler/destination for a source |
| **Event handler** | Azure Functions, webhook, Event Hubs, Service Bus, or other supported destination |
| **Filtering** | Filtering by event type, subject, and other attributes as supported |
| **Retry policy** | How the service retries delivery within configured limits |
| **Dead-letter destination** | Destination storing notifications that fail delivery after retry conditions, if configured |

### System topic vs. custom topic

A **system topic** fits when the source is an Azure service emitting events, such as Blob Storage. An application emitting its own business events can use a **custom topic** or a supported namespace topic model.

For example, **OrderPlaced** is an event created by your application's domain; it is not necessarily an Azure system event type. Conversely, **BlobCreated** is an event from the Storage ecosystem with service-defined schema and emission conditions.

### Event Grid push and pull

In the traditional Event Grid push model, Event Grid actively sends events to the handler. A destination such as an HTTP webhook needs to handle requests, validate authenticity, and respond appropriately.

**Event Grid Namespaces** also provide pull delivery / queue-like capabilities for consumers under supported configurations. Therefore, the statement “Event Grid always pushes” is overly absolute. In this lesson's comparison, **event routing** focuses on notification routing, whereas **streaming** focuses on partitioned logs and independent consumer read positions.

## 5. Event Grid Schema and CloudEvents

Event Grid supports event schemas depending on source/destination type, including **CloudEvents**. A CloudEvent can carry:

- **specversion**: CloudEvents specification version.
- **id**: event identifier provided by the source.
- **source**: emitting source.
- **type**: event type.
- **subject**: related subject/object, when present.
- **time**: event timestamp.
- **datacontenttype**: content format.
- **data**: business data/metadata.

Example **custom CloudEvents JSON** for an order management application:

~~~json
{
  "specversion": "1.0",
  "id": "evt-order-00042",
  "source": "/sales/orders",
  "type": "com.example.sales.order.placed.v1",
  "subject": "/orders/ORD-00042",
  "time": "2026-11-20T08:00:00Z",
  "datacontenttype": "application/json",
  "data": {
    "orderId": "ORD-00042",
    "tenantId": "tenant-demo",
    "schemaVersion": 1
  }
}
~~~

This is a **hypothetical application-emitted sample event**, not an official Azure Storage schema or an existing system event. The payload intentionally excludes passwords, access tokens, or sensitive payment details.

### Event Grid schema can differ from CloudEvents

An event using the Event Grid schema has fields such as **id**, **eventType**, **subject**, **eventTime**, **data**, **dataVersion**, and **topic** depending on event type. You cannot arbitrarily replace **eventType** with **type** in the same payload and assume both schemas are equivalent.

Choose the schema matching your source and handler. Producers and consumers must agree on the contract, version, content type, and required fields.

### Pass references only when data is large

When uploading a 200 MB video, the event should carry the **Blob URI or resource identifier** plus necessary metadata, rather than embedding video bytes inside the notification. The handler uses an appropriate identity and permissions to download the data from Blob Storage.

To avoid races when a blob name is overwritten, consider using the ETag or versionId provided by the source per event type, and verify the actual data version to process. An event does not guarantee by default that the object remains unchanged if the source data changes after the event was emitted.

## 6. Event Grid Filtering: Sending Only Needed Events

An event may not be relevant to every handler. For example, a container holds images, logs, and PDFs, while the thumbnail worker only processes images.

Event Grid offers filtering mechanisms such as:

- **Event type filter**: select only types like BlobCreated.
- **Subject begins with/ends with**: filter paths or extensions on the event subject.
- **Advanced filtering**: filter selected event properties using supported operators.

~~~text
BlobCreated events:
  images/product-01.jpg
  images/product-02.png
  reports/report.pdf

Event subscription for thumbnail generation:
  event type = BlobCreated
  subject prefix = .../images/
  subject suffix = .jpg or appropriate rule for .png
~~~

A filter selecting only **.jpg** will not automatically include **.png**; multiple conditions or subscriptions may be needed depending on supported filter expressions. Do not assume glob patterns or AND/OR logic behave identically across all filtering levels.

### Filters do not replace authentication and content validation

A file named **photo.jpg** can still contain non-JPEG data. The handler must verify magic bytes, size, trusted content type, and access permissions. Filtering assists with routing; it is not a malware scanner or authorization control.

## 7. Retry, Dead-Letter, and Ordering in Routing

In Event Grid, delivery can fail when a handler times out, does not respond, or returns an error code. Depending on the endpoint type, error code, and delivery policy, the service may **retry within limits** or follow terminal delivery handling. You can configure a **dead-letter destination** where supported to retain undeliverable events.

~~~text
BlobCreated
    |
    v
Event Grid subscription
    |
    +--> Initial delivery --> HTTP endpoint error
    |
    +--> Retry per policy (if error is retryable)
    |
    +--> Undeliverable under final conditions
                  |
                  +--> Configured dead-letter destination
                  +--> If unconfigured, risk of losing notifications needing attention
~~~

**Remember:** Retry does not mean exactly-once. A handler may have written the result while its response to Event Grid was lost; Event Grid may then redeliver the same event.

Example:

~~~text
Event Grid sends evt-123 -> Function
Function creates thumbnail successfully
Function response times out
Event Grid redelivers evt-123

If Function is not idempotent:
  creates duplicate output or unwanted overwrites.
~~~

### Do not assume global ordering

BlobCreated A followed by BlobDeleted A does not guarantee consumers always observe that exact order when using event routing. Handlers must tolerate late, duplicate, or out-of-order notifications, or source data that no longer exists.

**Event Grid push retry does not replace an arbitrarily seekable event log.** If you need multi-day historical replay or multi-hour aggregations, you need a dedicated event-retention architecture such as Event Hubs with Capture, storage, or another event store.

## 8. Event Streaming: “How Does the Entire Data Sequence Change?”

In streaming, producers send **a continuous stream of records**, and consumers read and process at their own position. Example:

~~~text
10,000 devices / applications
   |       |       |
   +-------+-------+
           |
           v
       Azure Event Hubs
    +----------------------+
    | Partition 0: events  |
    | Partition 1: events  |
    | Partition 2: events  |
    | Partition N: events  |
    +----------------------+
       |              |
       v              v
 Consumer Group A   Consumer Group B
 Realtime alerts    Analytics & ETL
       |              |
       v              v
 Azure Functions/    Stream Analytics/
 custom processor    Spark/Fabric etc.
       |              |
       v              v
  Incident API       Lake/warehouse
~~~

**Event Hubs** is a high-throughput event/message ingestion service that lets consumers read data per partition and track progress. Unlike a Service Bus Queue, an event in Event Hubs **is not deleted simply because one consumer finished processing it**.

### Characteristics of streaming

- Data is **appended** to partitions.
- Consumers **read by offset/position** with independent progress.
- Multiple consumer groups can analyze the same data independently.
- Records can be **replayed** within the active retention window.
- Ordering is meaningful **within each partition**, not guaranteed globally across the whole hub.
- Can integrate with Kafka clients and stream processing systems where supported.

## 9. Core Concepts of Azure Event Hubs

| Concept | Role |
|---|---|
| **Event Hubs namespace** | Management boundary for event hubs, networking/authorization, and capacity |
| **Event hub** | Stream log with partitions and retention |
| **Partition** | Unit of data division to increase throughput and enable parallel reads |
| **Partition key** | Value used to direct related events to the same partition via distribution logic |
| **Offset** | Position of a record within a partition |
| **Sequence number** | Increasing per-partition order assigned by the broker |
| **Consumer group** | Independent consumption view over the same event hub |
| **Event processor** | Consumer coordinating partition reads, processing, and progress tracking |
| **Checkpoint** | Durable processed position enabling continuation after restart |
| **Retention** | Duration during which data remains available for consumers to read/replay |
| **Capture** | Feature that writes data from Event Hubs to Storage/Data Lake as supported |

### How an event hub differs from a queue

In a queue, a consumer receives a message and calls **Complete** so the broker knows the job is done. In Event Hubs, a consumer reads records and **saves checkpoints** via client/processor mechanisms; events remain until retention expires, so another consumer group can still read them.

Do not call **CompleteMessage** on Event Hubs as you would with Service Bus Peek-Lock. Likewise, do not use Event Hubs as a queue guaranteeing “one order is dispatched to one worker exactly once” without designing idempotency and consumer state.

## 10. Partitions, Parallelism, and Ordering

Suppose an Event Hub has four partitions:

~~~text
Partition 0: A1 -> A2 -> A3 -> A4
Partition 1: B1 -> B2 -> B3
Partition 2: C1 -> C2
Partition 3: D1 -> D2 -> D3 -> D4
~~~

Within **a single partition**, the broker preserves record order so consumers can read sequentially by position. Between Partition 0 and Partition 1, **no global ordering** is guaranteed.

### Partition key

For telemetry, you can use **deviceId** as the partition key so records from a given device are routed to the same partition according to the producer/broker distribution algorithm.

~~~json
{
  "deviceId": "sensor-23",
  "temperature": 31.7,
  "recordedAt": "2026-11-20T08:01:20Z"
}
~~~

Records sent sequentially for **sensor-23** can be grouped into the same partition, supporting **per-partition** ordered processing. However, unsynchronized concurrent producers can still complicate business logic; application-level sequence numbers or timestamps are needed to detect missing, duplicate, or late samples.

### What does partition count affect?

Partition count affects the degree of parallelism. However:

- Increasing partition count does not scale throughput infinitely; capacity units, CPU/network, and backend limits still apply.
- Too few partitions can constrain parallelism.
- Too many partitions increase state/checkpoint overhead and consumer management cost.
- Changing partition count may be restricted by tier/feature; **when increasing partitions, partition key mapping can change**, affecting long-term per-key ordering assumptions.

Choose partition count based on peak volume, number of concurrent consumers, processing rate, and future growth.

## 11. Consumer Groups and Checkpoints

A **consumer group** is a set of consumers sharing a read-progress view on an event hub. Example:

~~~text
Event Hub: device-telemetry
              |
     +--------+---------+
     |                  |
     v                  v
Consumer Group       Consumer Group
realtime-alerts      offline-analytics
     |                  |
     v                  v
P0-P3 processors     P0-P3 processors
     |                  |
     v                  v
Alerting             Data Lake/warehouse
~~~

Two consumer groups can read the same events without the producer sending them twice.

### Checkpointing is processing progress

A consumer persists a checkpoint after safely processing the corresponding data. In some SDKs, checkpoints are typically stored using Azure Blob Storage or a supported checkpoint store.

~~~text
Partition 0:
  offset 100 -> processed
  offset 101 -> processed
  offset 102 -> processed
  offset 103 -> processing

Checkpoint = 102

Consumer restart:
  resumes from checkpoint, may re-read some events
~~~

**Checkpointing does not delete events from Event Hubs.** If a consumer writes a checkpoint **before data is durably committed**, a restart may skip unfinished work. If results are committed but the checkpoint has not yet been saved, events may be re-read.

Therefore, reliable streaming designs typically require an **idempotent sink**, proper error handling, and checkpointing only after results are durably written.

### Consumers within the same group

Processors in the same consumer group can **coordinate partition ownership** to share load. A partition generally has one active processor owner under the load-balancing design, though during failover/rebalance you still must handle duplicates and protect data integrity.

A consumer group is not a “push subscription” like an Event Grid event subscription. Consumers actively read and manage their own progress.

## 12. Retention and Replay in Event Hubs

Event Hubs retains received events for a **retention window** configured per tier and feature limits. Once retention expires, records are no longer available for replay from the event hub even if a consumer has not checkpointed them.

~~~text
Day 1: producer sends events
Day 2: realtime consumer processes
Day 3: analytics pipeline fails
Day 4: pipeline recovers

If Day 1 is still within retention:
  consumer can re-read from the appropriate offset.

If data is past retention:
  cannot rely on Event Hubs to replay purged data.
~~~

### Event Hubs Capture

**Capture** (when supported and configured) writes stream data to **Azure Blob Storage or Azure Data Lake Storage** on a configured time/size interval and supported format. This creates a long-term store for analytics or reprocessing.

~~~text
Event Hubs partitions
      |
      +--> realtime consumer -> alerts
      |
      +--> analytics consumer -> dashboards
      |
      +--> Capture -> Blob/ADLS -> offline batch/reprocess
~~~

Capture and event hub retention are **two separate layers**. Capture does not by itself ensure data is cleaned, schema-compliant, or immutable-policy compliant; you must verify storage paths, permissions, lifecycle rules, cost, and reprocessing logic.

### Replay is not deleting and resending

A consumer can read from an earlier position within the retention window. Replaying can cause sinks to write duplicate data; you must distinguish the goal:

- **Recompute** an aggregate table from historical events.
- **Rebuild** a materialized view or search index.
- **Debug** a consumer with sample data.
- **Recover** when a checkpoint was updated erroneously.

When replaying, isolate new outputs or use upsert/idempotency mechanisms before running against production data.

## 13. How Event Hubs Differs from Service Bus Queue

Both services use “message/event” terminology, but their retention models differ.

| Requirement | Event Hubs | Service Bus |
|---|---|---|
| High-volume continuous telemetry ingestion | Suitable | Not primary target |
| Multiple independent consumers re-reading a record | Consumer groups and retention | Topic subscriptions keep logical copies for subscribers, not an arbitrary partitioned replay log |
| Worker receives job then ACKs completion | No equivalent Complete settlement | Peek-Lock, Complete, Abandon, Dead-letter |
| Per-key ordering with stream processors | Partition key and partition ordering | Sessions where appropriate |
| Replaying data within retention | Yes, via offset/sequence position | Cannot re-read Completed messages like a log |
| Per-consumer checkpointing | Yes | Broker-managed message state/settlement |
| Delaying work / scheduled messages | Not a primary job queue mechanism | Supports scheduled messages |
| Isolating poison messages per job | Consumer designs its own quarantine/retry | Per-entity dead-letter subqueue |

**Service Bus Topic/Subscription** also supports publish-subscribe, but it is not simply an Event Grid clone. If the goal is **delivering durable business messages to subscribers with settlement**, Service Bus fits. If the goal is **pushing notifications when Azure resources change to handlers**, Event Grid is usually the starting point.

## 14. When to Choose Azure Queue Storage

**Azure Queue Storage** is a simple job queue option integrated with a Storage Account and services such as Azure Functions. It uses a message receive / visibility timeout model where the client deletes the message once work finishes, differing from Service Bus Peek-Lock settlement.

| Service | Use when |
|---|---|
| Event Grid | You need event notification and routing to handlers |
| Event Hubs | You need high-volume stream ingestion, partitions, consumer groups, and replay |
| Service Bus | You need a job broker with settlement, DLQ, and sessions/transactions per tier |
| Storage Queue | You need a relatively simple job queue with visibility timeout |

Do not pick Queue Storage merely because data is generated “on an event.” Base the decision on locking, retry, throughput, message size, SLA, fan-out, and advanced feature requirements.

## 15. Service Selection Decision Flow by Goal

~~~text
Requirement has an event/message source
              |
              v
Need to retain a stream for multiple consumers to read by offset,
analyze over time, and support replay?
       | Yes                    | No
       v                        v
   Event Hubs             Need to notify that a source event
                          occurred and route it to handlers?
                              | Yes      | No
                              v          v
                          Event Grid  Need job dispatch,
                                      ACK, retry, DLQ
                                      for business workflows?
                                         | Yes
                                         v
                                    Service Bus
                                    or Storage Queue
~~~

This is an **initial selection heuristic**, not a mandate to use only one service. Many production architectures combine Event Grid, Event Hubs, and Service Bus so each component handles what it does best.

### Scenario Decision Table

| Scenario | Initial choice | Rationale |
|---|---|---|
| New blob appears, need to invoke a Function | **Event Grid** | Notification routing |
| Millions of sensor readings, windowed analytics | **Event Hubs** | Streaming throughput/partitions/consumer groups |
| New order needs a worker to follow workflow with settlement | **Service Bus Queue** | Job queue with retry/DLQ |
| Multiple systems receive the same Azure resource change event | **Event Grid subscriptions** | Fan-out by event type/filter |
| Clickstream needs real-time dashboard and historical store | **Event Hubs + Capture** | Multiple consumers and long-term storage |
| Producer requests thumbnail from BlobCreated then needs job retries | **Event Grid → Function → Service Bus** | Decouples notification routing from job execution |
| Devices communicate over MQTT using supported features | **Event Grid Namespaces MQTT or IoT Hub per requirements** | Evaluate protocol/device management rather than defaulting to Event Grid topic push |
| Need event-based alerts while keeping all telemetry | **Event Hubs + stream processor + notification** | Analyze stream first, then emit alert |

## 16. Hybrid Architecture: File Upload and Asynchronous Processing

A complete architecture might look like this:

~~~text
Client uploads image
         |
         v
Azure Blob Storage /incoming
         |
         | BlobCreated event
         v
      Event Grid
         |
         v
Azure Function (ingest)
  - validate event
  - deduplicate by eventId/blob version
  - check Blob URI/ETag
         |
         v
Service Bus Queue: thumbnail-jobs
         |
         v
Container Apps / AKS worker
  - idempotent job ledger
  - fetch correct Blob version
  - generate thumbnail
  - Complete/Dead-letter message
         |
         v
Blob Storage /processed
         |
         v
Monitoring + audit
~~~

### Why not run heavy work directly inside the webhook?

An image processing task can take several minutes or require multiple retries. If the handler holds the Event Grid request open too long, delivery timeouts/retries can cause duplicate notifications and put pressure on the source.

A better design is usually:

1. **The ingest handler** validates the notification.
2. It writes a **durable job** to a queue or store.
3. It returns delivery success **only after the job has been persisted**.
4. A worker executes the long-running task with retries, DLQ, and idempotency.

Even when enqueueing to a queue, Event Grid can still redeliver; the handler must avoid enqueuing duplicate jobs or the producer must set a stable MessageId/idempotency key.

### Use ETag or versionId to avoid processing the wrong version

If a blob is repeatedly overwritten, an older BlobCreated notification can arrive after the content has changed. The worker must select the exact version or verify the ETag; otherwise, it may generate a thumbnail for the new version while recording the old version as processed.

## 17. Hybrid Architecture: Telemetry Streaming and Alerting

With many devices, Event Hubs can ingest telemetry for multiple consumers to analyze:

~~~text
100,000 sensors
      |
      v
Ingestion gateway / producer
      |
      v
Azure Event Hubs (partitions)
      |
      +--> Consumer group: realtime
      |       |
      |       v
      |    Stream Analytics / custom processor
      |       |
      |       +--> Alert API / Service Bus -> Incident worker
      |       |
      |       +--> Time-series dashboard
      |
      +--> Consumer group: analytics
      |       |
      |       v
      |    Spark / Fabric / Data Explorer / data pipeline
      |
      +--> Capture -> Blob/ADLS (if enabled)
~~~

Event Hubs retains ingested data within the retention window; each consumer group maintains independent progress. If the analytics consumer goes down for two hours while data remains within retention, it can resume from its checkpoint. For longer retention, Capture or another data store is responsible.

### Alert on anomalies, not every sensor reading

A stream processor can detect excessive temperature over five minutes and send **TemperatureAnomalyDetected** to a queue or alerting system. You do not need to send millions of raw sensor readings through Event Grid just to compute rolling averages; sequence analysis is the job of stream processing.

## 18. Event Hubs and Time-Window Processing

Streaming is not just “read one event and forward it.” Some workloads require:

- **Tumbling window**: divides time into fixed, non-overlapping intervals, e.g., average per minute.
- **Hopping window**: intervals can overlap, e.g., 5-minute average updated every 1 minute.
- **Sliding window**: evaluates continuously shifting intervals whenever a new event arrives.
- **Session window**: groups events by periods of activity/inactivity as supported by the engine.

~~~text
Sensor readings (by event time)
08:00:10  31°C
08:00:30  32°C
08:00:50  33°C
08:01:20  30°C

Tumbling window 08:00:00–08:01:00:
  AVG = (31 + 32 + 33) / 3 = 32°C

Window 08:01:00–08:02:00:
  has one reading of 30°C in this example.
~~~

### Event time vs. processing time

- **Event time**: timestamp recorded by the source inside the event payload.
- **Enqueue time**: timestamp when the broker received the event per metadata.
- **Processing time**: timestamp when the consumer processes it.

A disconnected device may send old data 10 minutes later. If aggregated by processing time, that sample falls into a later window; if aggregated by event time, it belongs to its original window, requiring **late arrival / watermark** handling by the stream processing engine.

Event Hubs does not solve watermarking, aggregation, or reconciliation for the application. Those behaviors belong to engines such as Azure Stream Analytics, Spark, or custom consumers.

## 19. Event Streaming and Kafka Compatibility

Azure Event Hubs can expose an endpoint compatible with the **Apache Kafka protocol** in supported configurations/tiers, allowing some Kafka producers/consumers to connect without operating Kafka brokers.

Points to distinguish:

- **Event Hubs** remains an Azure service; not every Kafka API, broker feature, topic config, or extension is identical to a self-managed Kafka cluster.
- **Partitions**, consumer groups, and offsets are conceptually close to Kafka, but quotas, retention, security, and limits may differ.
- When migrating an application, test protocol/client versions, SASL/TLS, topic mapping, batching, ordering, and error semantics.
- Do not rely on self-managed Kafka documentation to assert that a given setting takes effect on Event Hubs.

If a project already uses Kafka clients, this integration can reduce client changes; if you only need to receive Blob events, do not introduce Kafka into the architecture.

## 20. Reliability: At-Least-Once, Duplicates, and Ordering

A common misconception is thinking both Event Grid and Event Hubs deliver “exactly once, in exact order.”

### Event Grid

- Delivery can be duplicated; handlers need **idempotency**.
- Do not rely on event arrival order.
- Delivery retries and dead-lettering depend on policy and destination type.
- There is no arbitrary consumer checkpointing model like Event Hubs in standard push flows.

### Event Hubs

- Consumers read by position within a partition.
- **Checkpoints** can be written after durable output.
- If a consumer crashes after writing output but before checkpointing, events can be re-read.
- If a consumer falls behind retention, older events are no longer on the hub for replay.
- There is no global ordering across partitions.

### Service Bus

- Peek-Lock and settlement allow re-delivery after lock timeout.
- Successful Complete removes the message from the corresponding queue/subscription.
- Redelivered messages still require idempotency.
- Dead-lettering retains failed messages in a subqueue.

| Failure scenario | How to handle |
|---|---|
| Event Grid delivers duplicate BlobCreated | Deduplicate using event ID combined with blob version/operation ID |
| Event Grid arrives late after BlobDeleted | Check blob state/version before processing |
| Event Hubs consumer crashes after DB commit | Re-read and perform idempotent upsert by event key |
| Event Hubs checkpoints before DB commit | Avoid: only checkpoint after output is durable |
| Service Bus Complete fails after DB write | New consumer checks ledger and Completes without duplicating side effects |
| Worker receives malformed schema | Quarantine/DLQ or error table per architecture, do not retry forever |

## 21. Replay and Reprocessing: Design from the Start

“Replayable” does not mean you can press a button at any time to roll the entire system back to an earlier state.

### Replay in Event Hubs

A consumer can choose a **starting position** or an older checkpoint within the remaining retention window. A new analytics team can read from the beginning of the retained window to recompute dashboards.

~~~text
Event Hub retention: a configured duration

Consumer Group realtime:
  latest checkpoint, continues live processing

Consumer Group investigation:
  reads from an older available offset/time

Does not affect the read position of the realtime group.
~~~

### Replay from Capture/Storage

If data has aged out of Event Hubs retention but was Captured to Blob/ADLS, an offline pipeline can read the stored files and **reprocess** them. This does not automatically turn Capture files back into events in Event Hubs; re-injecting them into a stream requires a separate producer/replay pipeline with duplicate controls.

### Event Grid and notification history

Event Grid push provides conditional retry/dead-letter; it is **not** meant to provide long-term event history for arbitrary consumer seeking from last week. When audit/replay is needed, proactively store events in an event store, Storage, Service Bus, or Event Hubs as appropriate.

### Replay must control side effects

When re-reading **PaymentSucceeded**, you must not automatically trigger another payment. Consumers should distinguish:

- **Rebuilding a projection/read model**: can be recomputed from events using upserts.
- **Executing new side effects**: must pass idempotency checks and approval workflows.
- **Backfilling missing events**: verify source and timestamp to avoid creating two synthetic records for one event.

## 22. Schema Design and Idempotency Keys

A solid event contract should specify:

| Field | Meaning |
|---|---|
| **eventId** | Identifier for a single event publication |
| **eventType** | Event type and corresponding version |
| **source** | Trusted emitting source |
| **subject/entityId** | Business entity |
| **occurredAt** | Timestamp when the business event occurred |
| **schemaVersion** | Payload version |
| **correlationId** | Links processing steps belonging to the same request |
| **causationId** | Preceding event/command that caused this event, if any |
| **partitionKey** | Key used to select partition if streaming requires it |
| **data** | Scoped and security-classified payload |

**EventId** helps deduplicate delivery of a single notification; a **business operation ID** may be needed to prevent two events with different IDs representing the same business action.

### Example of an order change contract

~~~json
{
  "eventId": "evt-00078",
  "eventType": "OrderPlaced",
  "schemaVersion": 2,
  "entityId": "ORD-00078",
  "occurredAt": "2026-11-20T08:12:00Z",
  "correlationId": "checkout-8f4c",
  "data": {
    "orderStatus": "PLACED"
  }
}
~~~

Do not assume this payload conforms to the CloudEvents schema; it is an **application contract**. If sending via Event Grid CloudEvents, map fields into the corresponding CloudEvents structure rather than mixing two schemas in one root JSON object.

### Schema evolution

Older consumers may keep working when a producer adds an optional field, but will break if the producer changes a type or removes a required field. You can:

1. Maintain backward compatibility during transition windows.
2. Use explicit schema versioning.
3. Use a schema registry / contract testing appropriate to your stack.
4. Define a reject/quarantine policy for unsupported events.
5. Re-test against historical events when updating consumers.

## 23. Security: Authentication Is Distinct from Network Access

Event/messaging services sit inside an Azure architecture with Microsoft Entra ID, RBAC, networking, and secrets management. Never embed account keys or connection strings in container images or source code.

### Permissions to evaluate

| Component | Typical permissions/controls needed |
|---|---|
| Application publishing custom Event Grid events | Supported publish role/credential on the appropriate topic/namespace |
| Event Grid subscription management | Azure RBAC to create/edit routing/filters and endpoints |
| Event handler | Permissions to access referenced resources, such as Blob |
| Event Hubs producer | **Azure Event Hubs Data Sender** at appropriate scope |
| Event Hubs consumer | **Azure Event Hubs Data Receiver** at appropriate scope |
| Service Bus producer | **Azure Service Bus Data Sender** |
| Service Bus worker | **Azure Service Bus Data Receiver** |
| Analytics sink | Data-plane permissions for Storage/DB/warehouse |

**Permission to receive events does not automatically grant permission to read blobs.** A Function triggered by Event Grid still needs an appropriate identity and RBAC role to download files from Storage.

### Managed identity

Azure Functions, Container Apps, AKS Workload Identity, and VMs can use **managed identity** / Microsoft Entra ID to connect to supported services, avoiding long-lived connection strings. Verify scope/role, tenant, RBAC propagation timing, and SDK support.

### Webhook endpoint validation

When Event Grid pushes to a webhook, the handler must satisfy the **subscription validation/handshake** mechanism for the schema and endpoint, or use an integrated destination such as Azure Functions under its supported model.

Beyond the handshake, authenticate incoming delivery requests using supported methods (such as Entra authentication or corresponding signing/identity mechanisms). **Do not treat an HTTP POST carrying CloudEvents-like JSON as a trusted source without verifying origin and authorization.**

### Private networking

- Event Hubs, Service Bus, and Storage may offer Private Endpoint / firewall options depending on tier/features.
- Event Grid has varying network capabilities depending on topic type, namespace, and endpoint; **do not assume every push webhook inside a VNet is reachable by Event Grid over Private Endpoint by default**.
- Workers and producers need proper DNS, routing, NSG/UDR, and outbound rules for the target endpoint.
- Data is transmitted over TLS; data-plane authorization is still required even when private network connectivity works.

Never fix a 403 error by opening public network access everywhere or granting Owner on the subscription. Separate **auth/RBAC** errors from **DNS/route/firewall/TLS** errors.

## 24. Python Example: Event Hubs Producer with Microsoft Entra ID

The example below **will send real data to an event hub** if executed. Run it only in an authorized **lab** namespace/event hub with confirmed budget and quota. Do not run directly against production.

### Prerequisites

- An Event Hubs namespace and event hub already exist.
- Local identity or managed identity has **Azure Event Hubs Data Sender** permission.
- Network path to the namespace allows connectivity.
- Python packages installed:

~~~bash
python -m pip install azure-eventhub azure-identity
~~~

Set environment variables in an appropriate terminal:

~~~bash
export EVENTHUB_FQDN="eh-demo.servicebus.windows.net"
export EVENTHUB_NAME="device-telemetry"
~~~

**FQDN is the Event Hubs namespace hostname** and event hub name is the stream entity; do not confuse it with a Service Bus Queue even though both use `servicebus.windows.net` hostnames.

### Sample producer

~~~python
import json
import os
from datetime import datetime, timezone

from azure.eventhub import EventData, EventHubProducerClient
from azure.identity import DefaultAzureCredential

fqdn = os.environ["EVENTHUB_FQDN"]
hub_name = os.environ["EVENTHUB_NAME"]
credential = DefaultAzureCredential()

try:
    with EventHubProducerClient(
        fully_qualified_namespace=fqdn,
        eventhub_name=hub_name,
        credential=credential,
    ) as producer:
        sample = {
            "deviceId": "sensor-lab-23",
            "temperature": 31.7,
            "recordedAt": datetime.now(timezone.utc).isoformat(),
        }

        # Use the same partition key to group records for one device
        # according to ordering and producer requirements.
        batch = producer.create_batch(partition_key=sample["deviceId"])
        batch.add(EventData(json.dumps(sample)))
        producer.send_batch(batch)
        print("Sent one lab telemetry event")
finally:
    credential.close()
~~~

The code creates a **batch** with a partition key and sends one event; it does not provide checkpointing or a consumer. At higher scale, check batch sizes, retries, and tier throughput limits; never leave an infinite send loop running merely to test architecture.

### A producer is not a stream processor

A producer only sends data. To compute windowed temperature averages, you need a **consumer or stream engine** reading from Event Hubs, processing by event time/window, and writing output.

## 25. Consumer and Checkpoint Example in Event Hubs

A simple consumer reading the stream without a checkpoint store:

~~~python
import os

from azure.eventhub import EventHubConsumerClient
from azure.identity import DefaultAzureCredential

fqdn = os.environ["EVENTHUB_FQDN"]
hub_name = os.environ["EVENTHUB_NAME"]
credential = DefaultAzureCredential()


def on_event(partition_context, event):
    if event is None:
        return

    print(
        "partition=", partition_context.partition_id,
        "sequence=", event.sequence_number,
        "body=", event.body_as_str(),
    )
    # Example only displays data; does not call checkpoint because
    # there is no durable sink or checkpoint store yet.


try:
    with EventHubConsumerClient(
        fully_qualified_namespace=fqdn,
        eventhub_name=hub_name,
        consumer_group="$Default",
        credential=credential,
    ) as consumer:
        # Start from the earliest retained event.
        # receive is a long-running loop; stop with Ctrl+C during testing.
        consumer.receive(
            on_event=on_event,
            starting_position="-1",
            max_wait_time=10,
        )
finally:
    credential.close()
~~~

**Limitations:** This is a **print-only lab consumer**; it does not balance partitions across multiple processes via a shared checkpoint store, does not persist results durably, does not control logging costs, and could print sensitive payloads if used on real data. Never run it on a production stream containing PII.

### Production-safe checkpoint pseudocode

~~~text
on_event(partition, event):
    validate event schema
    businessKey = event deviceId + sequence/operation identifier
    calculate result / transform data

    write output idempotently into durable store
    if durable write succeeded:
        persist checkpoint at this event position
    else:
        do not advance checkpoint
        retry/quarantine according to policy
~~~

In multi-partition/multi-consumer applications, use a compatible **event processor / checkpoint store** to coordinate ownership and progress. The SDK provides Azure Blob Storage checkpoint integrations where applicable; you must create the container and assign appropriate Blob Data permissions.

**Checkpoints generally reflect consumption position, not an atomic transaction with the target database.** Therefore, the sink must be idempotent or use a transactional processing strategy.

## 26. Read-Only Inspection with Azure CLI

The commands below **only read configuration** and do not create or publish events. Subscription/resource group/namespace names are examples; replace them with authorized resources.

### Event Grid: inspect a custom topic

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az eventgrid topic show \
  --resource-group "rg-events-lab" \
  --name "topic-order-events" \
  --output json
~~~

### Event Grid: list event subscriptions by resource

~~~bash
az eventgrid event-subscription list \
  --source-resource-id "<FULL_AZURE_RESOURCE_ID>" \
  --output json
~~~

Specify the **full resource ID** of the system topic, Storage Account, or topic per configuration. Verify exact command/parameter names against your Azure CLI/extension version when running.

### Event Hubs: inspect an event hub

~~~bash
az eventhubs eventhub show \
  --resource-group "rg-events-lab" \
  --namespace-name "eh-demo" \
  --name "device-telemetry" \
  --output json
~~~

Inspect **partitionCount**, **messageRetentionInDays** (or tier/API-specific retention fields), status, and Capture configuration if enabled. Do not infer the pipeline is healthy merely because the entity exists.

### Event Hubs: consumer groups

~~~bash
az eventhubs eventhub consumer-group list \
  --resource-group "rg-events-lab" \
  --namespace-name "eh-demo" \
  --eventhub-name "device-telemetry" \
  --output table
~~~

Listing consumer groups does not show **per-partition checkpoints** if checkpoints live in external storage. To determine consumer lag, compare current partition offsets/sequence numbers, consumer checkpoints, and pipeline metrics/telemetry.

### Service Bus: queue properties in hybrid architectures

~~~bash
az servicebus queue show \
  --resource-group "rg-events-lab" \
  --namespace-name "sb-jobs-lab" \
  --name "thumbnail-jobs" \
  --output json
~~~

In production, inspect configuration and logs before changing queue retention, lock duration, or rules; modifying these parameters can affect in-flight messages.

## 27. Architecture Lab A: BlobCreated → Event Grid → Handler

**Goal:** understand notification routing. This lab uses synthetic data and an authorized Storage resource, without handling sensitive documents.

### Preparation

1. Create or select a lab Storage Account supporting Blob events and a container named **images-lab**.
2. Select a deployed, authenticatable handler, such as an Azure Function configured with an Event Grid trigger.
3. Enable logging and a way to inspect eventId, event type, subject, and processing outcome.
4. Prepare a test PNG file containing no PII.
5. Confirm the operator has permissions to create event subscriptions and access Storage as needed.

### Steps

1. In the Azure portal, open the Events page of the Storage Account.
2. Create an **event subscription** for **BlobCreated** with a subject filter targeting only the lab container if UI options allow.
3. Select the prepared Function/handler as destination; verify authentication/validation requirements.
4. Upload the test file into **images-lab**.
5. Verify the handler receives the event and parses the URI and event ID.
6. Have the handler write an idempotent job/marker and record processed status only after completion.
7. Upload another file and verify filtering; test a non-matching file to confirm it is not routed unintentionally.

### Acceptance Criteria

| Check | Expected behavior |
|---|---|
| BlobCreated reaches handler | Handler is triggered with valid event |
| Event ID/subject | Present in safe logs |
| Non-matching file | Does not trigger target handler |
| Duplicate event | Does not produce duplicate business output |
| Transient handler failure | Retried/dead-lettered per supported configuration |
| Storage RBAC | Handler reads only the required container |

**Do not intentionally delete or modify production resources to generate test events.** To test delivery failures, use a lab handler/queue with sufficient retry policy/retention so abnormal load is avoided.

## 28. Architecture Lab B: Telemetry → Event Hubs → Two Consumer Groups

**Goal:** observe the same event stream being read independently by two consumers.

### Preparation

1. Create or use a lab Event Hubs namespace with an event hub named **device-telemetry**.
2. Check partition count, retention, and tier/quota.
3. Create consumer groups **realtime-lab** and **analytics-lab** (if authorized).
4. Assign Data Sender to the producer and Data Receiver to consumers.
5. Prepare a separate checkpoint storage container if testing durable consumption across restarts.

### Practice

1. Use the sample producer from section 24 to send a few dozen readings with deviceId and recordedAt.
2. Run a consumer in **realtime-lab** to watch records arrive per partition.
3. Run another consumer in **analytics-lab**; verify it can read the same retained data.
4. Stop one consumer, send more readings, then restart it from its chosen checkpoint/starting position.
5. Try re-reading older retained data and writing results to an isolated test store.
6. Send readings across multiple deviceIds to observe partition distribution.
7. If Capture is enabled, inspect the captured files at the destination and the reprocessing flow.

### Verification Questions

- Why do both groups receive the same event when the producer only sends it once?
- If a consumer does not checkpoint, how can a restart cause duplicate reads?
- Why are sequence numbers only meaningful for ordering within a partition?
- If backlog grows beyond retention, how is replayability lost?
- Why does Capture not imply a consumer group has processed data successfully?

Do not run a consumer that replays back into the same event hub it reads from without loop protection, as this can cause **event amplification** and spike costs.

## 29. Fault-Tolerant Design in Hybrid Pipelines

When combining Event Grid, Service Bus, and Event Hubs, define **acknowledgement/checkpoint** boundaries at every hop.

~~~text
Event source
      |
      v
Event Grid --> delivery success to ingest handler
      |
      v
Ingest handler writes job to Service Bus
      |
      v
Service Bus worker receives Peek-Lock
      |
      +--> commit output/ledger
      |
      +--> Complete message
      |
      v
Business outcome completed
~~~

**Event Grid delivery success** only proves the handler accepted the message under the delivery contract; **it does not prove OCR or invoice generation finished**. **Service Bus Complete** reflects that the worker acknowledged processing in code; you still need to verify output/ledger state.

For streaming:

~~~text
Producer sends event successfully
      |
      v
Event Hubs appends event to partition
      |
      v
Consumer receives event
      |
      +--> write durable output
      |
      +--> update checkpoint
      |
      v
Processing progress saved separately
~~~

**Producer send success** does not mean every consumer has processed the event. This is a fundamental distinction when designing SLOs, testing, and reporting.

### RPO/RTO and retention

If the business requires zero telemetry loss during prolonged downtime, configure sufficient retention/backup/Capture and verify capacity. If Event Grid push fails for an extended period, ensure appropriate dead-lettering or a mechanism to re-query the event source. Never assume enabling retries alone satisfies DR.

## 30. Model-Appropriate Observability and Monitoring

| Signal | Event Grid | Event Hubs | Service Bus |
|---|---|---|---|
| Ingress | Published events | Incoming messages/bytes | Incoming messages |
| Delivery/processing | Matched/delivered/failed/dead-letter per capability | Outgoing events/bytes, custom-calculated consumer lag | Active/locked/completed/dead-letter |
| Failure | Endpoint errors, retry/dead-letter | Throttling, failed requests, consumer errors | Lock lost, MaxDeliveryCount, DLQ |
| Progress | Handler job ledger | Per-partition/group offset/checkpoint | Settlement status and job ledger |
| Latency | Publish to handler accepted | Enqueue to processed event time | Enqueue to Complete |
| Backlog | Undelivered/retry per delivery policy | Lag and checkpoint age per pipeline | Active message count / oldest age |
| Capacity | Publish/delivery operations | Units/partitions/throughput | Broker tier/requests/message size |

Not every row in this table is a **default Azure Monitor metric name**. For example, Event Hubs consumer lag usually requires combining checkpoints with partition end offsets and application data. Thumbnail outcomes or business latency also require custom telemetry.

### Correlation ID

Minimal log example:

~~~json
{
  "eventId": "evt-00042",
  "source": "/sales/orders",
  "correlationId": "checkout-demo-42",
  "stage": "thumbnail-ingest",
  "outcome": "JOB_ENQUEUED",
  "durationMs": 125
}
~~~

Never log secrets, SAS tokens, private keys, full personal data, or payment payloads. The Event Hubs demo consumer that prints message bodies must only be run on safe lab data.

### Useful alerts

- Spike in Event Grid failed deliveries or dead-lettered events.
- High timeout/429/5xx rate at a destination.
- Event Hubs throttled requests, consumer lag, or checkpoint age exceeding SLA.
- Repeated consumer crashes/rebalances.
- Rising Service Bus Queue backlog/DLQ/MessageLockLost counts.
- Output count diverges from received event count despite normal producer metrics.
- Ingestion, capture, logging, or compute costs exceeding budget.

## 31. Cost and Sizing

Event Grid, Event Hubs, and Service Bus each have **distinct pricing and capacity models**. Never size all three solely by event count.

### Event Grid

Consider tier/namespace/topic type, publish/delivery/operations volume, retries, dead-letter destination, handler compute, and feature-dependent network traffic. One event fanned out to three destinations can generate higher delivery volume than a single destination.

### Event Hubs

Consider tier, throughput/capacity units, partitions, ingress/egress, retention, Capture, destination storage, networking, and consumer processing. Partition count is not the sole measure of capacity; tier throughput and limits must be calculated separately.

### Service Bus

Consider tier, operations, messaging units or configured capacity, queues/topics-subscriptions, traffic, DLQ, retries, and worker compute. A message retried many times increases operations even though business volume is unchanged.

### Telemetry sizing example

Suppose a system sends:

~~~text
100,000 devices
Each device sends 1 reading/minute

Daily total:
  100,000 x 60 x 24 = 144,000,000 readings/day

Average:
  100,000 / 60 ≈ 1,667 readings/second

4x peak:
  around 6,667 readings/second
~~~

This is a baseline volume calculation, **excluding bytes per event, batching, headers, retention, partition skew, throttling, or consumer count**. When sizing Event Hubs, calculate both **bytes/second and events/second**, appropriate tier/capacity, partition count, and downstream throughput.

Do not quote fixed USD prices because pricing depends on Azure region, tier, time, and configuration. Use the Azure Pricing Calculator and Cost Management to estimate and track actual spend.

## 32. Common Service Selection Mistakes

| Symptom/design | Problem | How to improve |
|---|---|---|
| Using Event Grid to retain multi-day telemetry | Push routing lacks arbitrary partitioned log/replay semantics | Use Event Hubs + retention/Capture |
| Using Event Hubs as a task queue with Complete/Abandon | Lacks per-event settlement like Service Bus | Use Service Bus / Storage Queue for worker jobs |
| Using Service Bus to ingest millions of sensor readings for windowed analytics | Not optimized for streaming throughput/partition consumption | Evaluate Event Hubs |
| Embedding an entire PDF in an Event Grid event | Notification becomes oversized and tightly coupled to payload | Send Blob reference + ETag/version |
| Not storing idempotency keys for webhooks | Event Grid retries create duplicate results | Maintain a ledger keyed by eventId/business operation |
| Consumer checkpoints before DB write | May skip unprocessed data after restart | Durable commit first, then checkpoint |
| Streaming ignores event-time lateness | Aggregates are wrong when data arrives late | Implement watermarks/reconciliation per engine |
| Sharing one consumer group between dashboard and ETL unintentionally | Processors split partitions instead of running two independent streams | Use separate consumer groups for independent goals |
| Treating Event Grid delivery success as business success | Handler may only have enqueued a job | Track job lifecycle separately |
| Opening public network access to fix a 403 | Cause may be identity/RBAC, not network | Separate auth vs. route/DNS/firewall |
| Not configuring dead-letter/quarantine | Failed events are hard to inspect after retries | Design DLQ/event store per service |
| Enabling broad fan-out without filters | Delivery volume and cost increase | Filter by type/subject/metadata |

## 33. Layered Diagnostic Workflow

When “events aren't arriving,” do not start by increasing every timeout or relaxing permissions.

### Step 1: check the source

- Did the producer actually emit the event?
- Are event type/schema and source/subject correct?
- Was the blob created/committed at the expected time?
- Did the Event Hubs producer receive 401/403/quota/throttle errors?

### Step 2: check the intermediary service

- **Event Grid:** does the subscription exist, does the filter match, is the destination valid, what do delivery success/failure/retry metrics show?
- **Event Hubs:** did the event hub/partition record the event, which offset is the consumer group reading, is data still within retention?
- **Service Bus:** is the message Active, Locked, Deferred, Scheduled, or in the DLQ?

### Step 3: check the consumer

- Did the handler receive the request and authenticate properly?
- Is the consumer running, crashing, or hitting incompatible schemas?
- Did it commit output or merely log “received”?
- Did it checkpoint/settle before saving results?

### Step 4: check data/identity/network

- Does the Function/Container App/AKS workload have RBAC at the right scope?
- Do DNS, Private Endpoint, NSG/UDR, and Azure Firewall allow the path?
- Do the blob version/ETag still match the event reference?

### Step 5: verify end-to-end

Test with a **synthetic event carrying a unique correlationId**. Record timestamps at each step and compare messageId/eventId/checkpoints or the job ledger. Mark PASS only when the target business result exists and is correct, not merely when the event was published.

## 34. Case Study: Choosing an Architecture for a Retail Platform

A retail business has four requirements:

1. Users upload product images; the system generates thumbnails.
2. The website collects roughly **5 million click events/day** for behavior analytics.
3. Each new order must be processed by a worker to generate an invoice, with a DLQ on failure.
4. The analytics team wants to re-read clickstream data from seven days ago when testing a new algorithm.

### Tasks

1. Select the appropriate service for each requirement and justify it.
2. Design the system receiving BlobCreated with container-level filtering.
3. Explain why thumbnail jobs should be decoupled into a queue if processing takes a long time.
4. Propose a partition key for the clickstream when per-user/session behavior analysis is needed without storing unnecessary PII.
5. Design separate consumer groups for real-time dashboards and analytics.
6. Explain what happens if the analytics consumer stops for two days, both within and beyond retention.
7. Choose how to protect seven-day replay and how to use Capture if retention is insufficient.
8. Outline idempotency/settlement design for the invoice worker.
9. Design RBAC/managed identity, private networking, and safe logging.
10. Define metrics/alerts proving each requirement is met.
11. List at least two failover/restore approaches if consumer checkpoints are lost.
12. Compare Event Grid fan-out costs with Event Hubs throughput/retention costs.

### Suggested Solution

~~~text
Product images:
Blob Storage -> Event Grid -> Function -> Service Bus -> thumbnail worker

Clickstream:
Web producer -> Event Hubs
                   +-> Consumer group realtime -> dashboard
                   +-> Consumer group analytics -> data lake
                   +-> Capture -> ADLS if long-term storage needed

Orders:
Order service -> Service Bus Queue -> invoice worker -> DB/Blob
~~~

Event Grid handles routing when files appear. Event Hubs fits continuous clickstream ingestion and replay within retention; if data must be studied past retention, a separate store such as Capture/ADLS is required. Service Bus handles invoice job dispatch with settlement and DLQ.

## 35. Production Readiness Checklist

| Item | What to confirm |
|---|---|
| Purpose | Notification routing, streaming analytics, or job queue clearly classified |
| Schema | Event type, source, version, correlationId, and sensitive data boundaries defined |
| Event Grid | Appropriate topic/subscription, filter, destination, retry/dead-letter |
| Event Hubs | Namespace, partitions, retention, producer/consumer groups, checkpoints |
| Service Bus | Queues/subscriptions, locks, settlement, DLQ, idempotency if used |
| Ordering | Do not assume global ordering; pick partition keys/sessions where needed |
| Replay | Retention and long-term storage/Capture match RPO and analytics needs |
| Idempotency | Consumers tolerate duplicates and side effects do not execute twice |
| Auth | Entra ID, managed identity/RBAC, or secrets with clear lifecycle |
| Networking | DNS, firewall, Private Endpoint/ingress per supported capabilities |
| Payload | Size-bounded, passing source references instead of large payloads |
| Consumer | Retries, backoff, quarantine, checkpoint/settlement at the right point |
| Revisions | Schema migration, consumer version compatibility, rollback |
| Observability | Publish/delivery, consumer lag, business outcome, failed events, DLQ |
| Cost | Estimated fan-out/ingress/egress/retention/capture/compute/logging |
| Recovery | Restore/replay drills and post-failure correctness verification |

## 36. Self-Check Questions

1. What is the core difference between event routing and event streaming?
2. Why should a BlobCreated notification not embed the entire video content?
3. What sources do Event Grid **system topics** and **custom topics** serve?
4. How does an event subscription differ from a consumer group?
5. Why should you not claim that all Event Grid deliveries are push-only?
6. What are the basic fields of CloudEvents?
7. Do Event Grid schema and CloudEvents use the exact same field names?
8. What problem does subject filtering solve? Does it verify file safety?
9. Why must Event Grid handlers be idempotent?
10. Does Event Grid guarantee notifications arrive in producer emission order?
11. Why is Event Grid push not equivalent to an arbitrarily replayable event log?
12. What is the purpose of Event Hubs partitions?
13. When should `deviceId` be used as a partition key?
14. Does Event Hubs provide global ordering across all partitions?
15. How does a consumer group differ from a Service Bus subscription?
16. Does an offset/checkpoint cause the broker to delete events from Event Hubs?
17. Why is committing to the DB before checkpointing usually safer than the reverse?
18. What happens if a consumer falls behind the retention window?
19. What problem does Capture solve? Does Capture automatically mean a consumer processed events correctly?
20. When should you use Azure Service Bus instead of Event Hubs?
21. How do Receive/Complete in Service Bus differ from checkpointing in Event Hubs?
22. Why must a stream processor care about event time vs. processing time?
23. What is the risk of replaying PaymentSucceeded if the consumer is not idempotent?
24. Does a producer granted permission to send to Event Hubs automatically have permission to read output Blobs?
25. By what signs can you distinguish an auth error from a private DNS/network error?
26. When increasing partitions, what assumption about partition key mapping must be re-evaluated?
27. Which signals tell you a real-time consumer is lagging behind the producer?
28. How can you combine Event Grid and Service Bus to avoid running long OCR inside a webhook?
29. Why does the count of published events not equal completed business outcomes?
30. Name the primary cost components of Event Grid, Event Hubs, and Service Bus.

## References

- Microsoft Learn — *What is Azure Event Grid?*: https://learn.microsoft.com/azure/event-grid/overview
- Microsoft Learn — *Event Grid event schema*: https://learn.microsoft.com/azure/event-grid/event-schema
- Microsoft Learn — *CloudEvents schema*: https://learn.microsoft.com/azure/event-grid/cloud-event-schema
- Microsoft Learn — *Event filtering*: https://learn.microsoft.com/azure/event-grid/event-filtering
- Microsoft Learn — *Event Grid delivery and retry*: https://learn.microsoft.com/azure/event-grid/delivery-and-retry
- Microsoft Learn — *Event Grid Namespaces overview*: https://learn.microsoft.com/azure/event-grid/namespace-overview
- Microsoft Learn — *What is Azure Event Hubs?*: https://learn.microsoft.com/azure/event-hubs/event-hubs-about
- Microsoft Learn — *Event Hubs features and concepts*: https://learn.microsoft.com/azure/event-hubs/event-hubs-features
- Microsoft Learn — *Event Hubs scalability*: https://learn.microsoft.com/azure/event-hubs/event-hubs-scalability
- Microsoft Learn — *Event Hubs Capture*: https://learn.microsoft.com/azure/event-hubs/event-hubs-capture-overview
- Microsoft Learn — *Event Hubs consumer/processor concepts*: https://learn.microsoft.com/azure/event-hubs/event-hubs-event-processor-host
- Microsoft Learn — *Azure Service Bus messaging*: https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview
- Microsoft Learn — *Event Hubs Python SDK*: https://learn.microsoft.com/python/api/overview/azure/eventhub-readme
- CloudEvents specification: https://github.com/cloudevents/spec
