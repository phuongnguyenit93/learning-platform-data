# Partitions, Consumer Groups, and Ordering in Event Hubs

Azure Event Hubs is designed to ingest and distribute event streams at high throughput. To scale the system, Event Hubs divides an event hub into multiple **partitions**. Each consuming application selects a **consumer group** as its own logical reading cursor, then tracks progress using **offsets** and **checkpoints**. These three concepts determine how data is distributed, the level of parallelism achievable, the scope of ordering guarantees, and how recovery works after a consumer failure.

In the **Azure Events** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, this lesson helps learners integrate Spring Boot with Azure Event Hubs through the Azure SDK and appropriate Spring Cloud Azure libraries. The focus is on choosing partition keys, organizing consumer groups, managing partition ownership, checkpointing at the right time, protecting identities and permissions, handling duplicate or out-of-order events, testing scale-out, and evaluating throughput/latency/cost.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the roles of **partitions**, **partition keys**, **consumer groups**, **offsets**, **sequence numbers**, **checkpoints**, and **partition ownership**.
- Distinguish a consumer group from a queue, a topic subscription, and a single consumer instance.
- Design partition keys to distribute load while preserving order for a business key.
- Estimate effective parallelism based on the number of partitions and instances.
- Understand how the Event Processor Client distributes partitions across multiple instances in the same consumer group.
- Design safe checkpointing, resume, and replay when a process crashes or loses connectivity.
- Handle duplicates, poison events, hot partitions, out-of-order events, and partition count changes.
- Integrate Event Hubs producers/consumers with Spring Boot, Managed Identity, a Blob checkpoint store, and Azure RBAC.
- Test ordering, rebalancing, checkpoint recovery, throughput, and access permissions in an isolated environment.

## 2. The Event Hubs Data Model

An event hub is an event stream partitioned into **partitions**. Each partition acts as an append-only log ordered within that partition. Producers write events to partitions; consumers read sequentially by position in the log. Event Hubs retains events for the configured retention period, so multiple consumers can read the same data at different times.

~~~mermaid
flowchart TD
    P1["Producer: orders API"] --> H["Event Hub: order-events"]
    P2["Producer: payment service"] --> H
    H --> A["Partition 0<br/>E0, E1, E2, ..."]
    H --> B["Partition 1<br/>E0, E1, E2, ..."]
    H --> C["Partition 2<br/>E0, E1, E2, ..."]
    A --> CGA["Consumer group: analytics"]
    B --> CGA
    C --> CGA
    A --> CGF["Consumer group: fraud"]
    B --> CGF
    C --> CGF
~~~

Each consumer group maintains its own reading position per partition. The analytics consumer group can re-read a slice of history without affecting the progress of the fraud consumer group. Within the same consumer group, instances coordinate to share partitions, avoiding having every instance read and process the entire stream like independent consumer groups.

### 2.1. A Partition Is the Unit of Load Distribution and Ordering

Each partition has its own sequence of events, with corresponding sequence numbers and offsets. An event is written to a specific partition; the next event in the same partition is appended to that log. Partitions are the primary unit for:
- Distributing data and parallel processing.
- Maintaining the relative order of events within the same partition.
- Assigning ownership to consumer instances within a consumer group.
- Persisting reading progress/checkpoints independently.

There is no automatic global ordering across partitions. For example, event A in partition 0 and event B in partition 1 may be processed concurrently; you cannot conclude which event "came first" merely by comparing sequence numbers across two partitions.

### 2.2. A Consumer Group Is an Independent Reading View

A consumer group is not a Spring Boot instance. It is a **logical reading group** with its own progress. Multiple instances of the same logical application typically share one consumer group to divide partitions. A different logical application that needs to read the entire stream independently should use a different consumer group.

For example:
- `order-analytics`: processes metrics and reports.
- `fraud-detection`: inspects suspicious transactions.
- `order-archive`: stores events in a data lake.
- `order-projection`: builds a read model for an API.

Each group can read the same event hub while maintaining separate checkpoints. Event Hubs' default consumer group is typically named `$Default`; for production workloads, use explicit names reflecting the logical application, environment, and purpose. Do not use a separate consumer group name per pod if your intent is for pods to share partitions with each other.

### 2.3. Offsets and Sequence Numbers

A **sequence number** is an incrementing number assigned to events within a partition. An **offset** is the position of an event in the partition log, typically represented by the SDK as a string. Both are scoped **per partition**, not as a global numbering across the entire event hub.

An event context typically provides:
- Partition ID.
- Sequence number.
- Offset.
- Enqueued time.
- Event body and properties.

Use the sequence number to track ordering within a partition or detect gaps according to appropriate logic. Use the offset/sequence number as a starting point for re-reading when needed. Do not compare sequence numbers between partition 0 and partition 1 as if they belonged to a single global counter.

## 3. How Does a Producer Choose a Partition?

Producers can route events in several ways:

1. **Partition key:** events with the same key are routed to the same partition by the service's mechanism, assuming a stable partition layout. This is the common choice when ordering per entity such as `orderId` is required.
2. **Partition ID:** the producer directly specifies the target partition. This gives explicit placement control but couples the application to the partition topology.
3. **No key/ID specified:** the service/SDK distributes events using its default mechanism, suitable when per-entity ordering is unnecessary and load distribution is desired.

Do not compute hashes yourself to guess a partition ID. Use the API/SDK to supply a partition key or partition ID according to the supported contract.

### 3.1. Choosing a Partition Key for Entities Requiring Order

Suppose an order emits these events:
- `OrderCreated`
- `PaymentAuthorized`
- `InventoryReserved`
- `OrderShipped`

If events for the same `orderId` must be observed in order, use `orderId` as the partition key. Different orders can go to different partitions and be processed in parallel.

~~~mermaid
flowchart TD
    E1["orderId=1001<br/>OrderCreated"] --> K1["Partition key: 1001"]
    E2["orderId=1001<br/>PaymentAuthorized"] --> K1
    E3["orderId=1001<br/>OrderShipped"] --> K1
    K1 --> P0["Partition 0"]
    E4["orderId=2002<br/>OrderCreated"] --> K2["Partition key: 2002"]
    E5["orderId=2002<br/>PaymentAuthorized"] --> K2
    K2 --> P1["Partition 1"]
~~~

You must choose a key with reasonably even distribution. If one key accounts for most traffic, its partition becomes a **hot partition**. For example, using `countryCode` as the key when most orders come from one country can overload a single partition. Using `orderId` usually distributes better if order volume is high enough and load is not heavily skewed.

### 3.2. Partition Key vs. Partition ID

| Attribute | Partition Key | Partition ID |
|---|---|---|
| Purpose | Group related events into the same partition | Send an event to a specific partition |
| Selection | Producer supplies a business key | Producer specifies the partition ID |
| Flexibility | Service routes the key | Application depends on partition topology |
| Best suited for | Ordering by order/customer/device | Pre-partitioned flows with explicit partition ID management |
| Risk | Hot keys, skewed distribution | Topology changes can make routing logic hard to maintain |

Avoid arbitrarily mixing partition keys and partition IDs in the same stream unless producer routing rules are clearly defined. A partition key is not a transaction lock and does not replace database concurrency control.

### 3.3. Partition Ordering Is Not Absolute Business Ordering

Event Hubs preserves append order within a partition. However, if multiple producers send events with the same partition key, order is determined by when the service ingests/writes the event, not necessarily by the business occurrence time in the payload. Producer clocks can skew; requests can be delayed by the network; one producer may retry after another producer.

If you need to guarantee business ordering:
- Use an ordered single source of emission or a business-assigned sequence/version mechanism.
- Attach `aggregateId` and `aggregateVersion`/sequence to events.
- Have consumers check the next expected version before updating state.
- Handle late-arriving or missing versions with buffering, bounded retries, or quarantine.
- Do not sort solely by client timestamps, as timestamps do not guarantee commit order.

## 4. Consumer Groups and Multiple Consumer Instances

### 4.1. One Consumer Group, Multiple Instances

Within the same consumer group, the Event Processor Client coordinates through a **checkpoint store** to distribute ownership. A partition at any given time is owned by one processor instance within that consumer group. Different instances can own different partitions.

For example, an event hub with 6 partitions:
- 1 instance can own all 6.
- 2 instances can split 3 + 3.
- 3 instances can split 2 + 2 + 2.
- 6 instances can have 1 partition per instance.
- 10 instances do not create 10 independent partition-reading streams; maximum concurrency is still bounded by the 6 existing partitions, and extra instances may own no partitions.

~~~mermaid
flowchart TB
    subgraph Hub["Event Hub: 6 partitions"]
      P0["P0"]
      P1["P1"]
      P2["P2"]
      P3["P3"]
      P4["P4"]
      P5["P5"]
    end
    subgraph Group["Consumer group: order-projection"]
      C1["Instance A"]
      C2["Instance B"]
      C3["Instance C"]
    end
    P0 --> C1
    P1 --> C1
    P2 --> C2
    P3 --> C2
    P4 --> C3
    P5 --> C3
~~~

The diagram illustrates a balanced split; the actual load-balancing algorithm and when ownership changes are managed by the SDK. Do not rely on a static diagram to assume which pod will always process which partition.

### 4.2. Multiple Consumer Groups, Each with Its Own Reading Progress

If both analytics and fraud detection need every event, create two consumer groups. Each group reads all partitions independently; within each group, instances split partitions among themselves.

~~~mermaid
flowchart LR
    H["Event Hub"] --> P0["Partition 0"]
    H --> P1["Partition 1"]
    P0 --> A["Group: analytics"]
    P1 --> A
    P0 --> F["Group: fraud"]
    P1 --> F
    A --> AI["Analytics instances"]
    F --> FI["Fraud instances"]
~~~

A consumer group is a **reading progress** boundary, not a security mechanism or strict cost isolation boundary. Groups sharing an event hub/namespace still share capacity and are subject to related limits/quotas. RBAC permissions and namespace/event hub scopes must be configured separately.

### 4.3. Scaling Out Does Not Always Increase Throughput

Partition count caps read parallelism within a consumer group. Adding instances when all partitions are already owned may not increase throughput. If a partition is hot, adding instances also cannot split a single partition across multiple concurrent owners in the same consumer group.

Ways to increase capacity:
- Increase partition count if the service/tier allows it and you have a partition key plan.
- Improve partition key distribution to reduce hot partitions.
- Speed up per-event processing and avoid synchronous I/O inside callbacks.
- Use appropriate batching and avoid checkpointing too frequently.
- Optimize the Blob checkpoint store and network.
- Separate consumer groups per independent workload, accounting for additional read capacity/cost.
- Evaluate Event Hubs tier/capacity and regional quotas.

**Do not increase partitions just to add more pods.** Partition count affects ordering, key distribution, ownership, checkpoints, and cost; topology changes require testing.

## 5. Partition Ownership and Load Balancing

The Event Processor Client uses a checkpoint store to persist ownership and checkpoint information. Processor instances in the same consumer group exchange information through the store to know which partitions are owned and when rebalancing is needed.

An instance can:
- Claim partition ownership on startup.
- Resume reading from the latest checkpoint or the initial position if no checkpoint exists.
- Lose ownership when another instance needs to balance load or the current instance stops.
- Relinquish partitions during controlled shutdown.
- Take over partitions after another instance fails.

Ownership can change during scale-out, scale-in, restarts, or network disconnects. During rebalancing, there may be a brief processing pause and events may be re-read from the latest checkpoint. Consumers must be **idempotent** and never assume a callback runs only once.

### 5.1. What Does the Checkpoint Store Do?

The checkpoint store maintains at least two critical groups of state:
- **Partition ownership/lease:** which instance owns a partition in the consumer group.
- **Checkpoint:** the last reading position the consumer recorded as processed.

With EventProcessorClient, Blob Storage is commonly used as the checkpoint store via BlobCheckpointStore. The container must exist and the workload needs appropriate data-plane permissions, typically **Storage Blob Data Contributor** on the container or designated scope. If the checkpoint storage is unreachable, the processor may fail to balance ownership or save progress as expected.

The checkpoint store is not where the entire event stream is stored; events remain in Event Hubs according to retention. It is also different from Event Hubs Capture:
- **Checkpoint:** how far the consumer has processed.
- **Capture:** writes a copy of stream data to Blob Storage/ADLS for archival or batch processing as configured.

### 5.2. Consumer Groups Do Not Share Partitions Across Different Groups

Two consumer groups have independent checkpoints and ownership. For example:
- `orders-projection` has 3 instances.
- `orders-analytics` has 2 instances.

Analytics does not "give up" partitions to projection just because projection is short on instances; each group balances within its own scope. This keeps logical applications independent in progress, but increases total read work and may increase capacity/throughput usage.

## 6. Offsets, Checkpoints, and Initial Reading Position

### 6.1. Offsets vs. Checkpoints

An offset is the position of an event in a partition; a checkpoint is the durable progress record saved by the consumer. An event having an offset does not mean the consumer has processed it. Consumers should only update the checkpoint **after the required side effects are durable**.

~~~mermaid
sequenceDiagram
    participant EH as Event Hubs partition
    participant C as Consumer
    participant DB as Database
    participant CP as Blob checkpoint store
    EH->>C: Event offset 100
    C->>DB: Process and commit event
    DB-->>C: Commit succeeded
    C->>CP: Update checkpoint = 100
    CP-->>C: Checkpoint saved
~~~

If you update the checkpoint before committing to the database, the consumer can crash after the checkpoint but before the commit; on restart it skips the event and loses processing. If it commits to the DB and crashes before checkpointing, the event can be re-read; this is why idempotency is required.

### 6.2. Checkpoint Frequently or in Batches?

| Strategy | Advantage | Risk / Cost |
|---|---|---|
| Checkpoint every event | Small replay window after failure | Many checkpoint operations, higher I/O and latency |
| Checkpoint every N events | Fewer checkpoint operations | May replay multiple already-processed events |
| Checkpoint on a time interval | Easy to budget replay window by duration | Number of replayed events varies with throughput |
| Checkpoint after a durable processing batch | Ties checkpoint to batch commit | Must ensure the batch does not skip events on mid-batch failure |

No single frequency fits every system. Choose based on event rate, Blob Storage cost, acceptable processing RPO, processing time, and deduplication capability. If processing events in batches, only checkpoint up to the last event in the batch **after all prior side effects are committed or durably isolated**.

### 6.3. Initial Position and Replay

When a consumer group has no checkpoint yet, the application needs to specify where to start reading, such as:
- **Earliest/earliest available:** read from the earliest event still in retention.
- **Latest:** only read new events from the moment the consumer starts.
- **Enqueued time:** start from a chosen enqueue timestamp.
- **Offset/sequence number:** start from a specific position if supported by the SDK/API and still valid.

When a checkpoint already exists, the processor normally resumes from the checkpoint rather than using the initial position. To replay:
- Use a new consumer group with an appropriate initial position; or
- Adjust the checkpoint in a controlled manner following a supported procedure; or
- Use a dedicated reader/processor to reprocess a time range.

Do not reset production checkpoints while consumers are running without understanding ownership and impact. A new consumer group may re-read all data still in retention and spike load; throttle replay rates and protect side effects.

### 6.4. Retention Limits Replay Capability

Event Hubs only retains events for the retention period of its configuration/tier. If a consumer is stopped longer than the retention period, old positions may no longer have data to read. Saving an offset in a checkpoint does not extend event retention. If you need long-term history or multi-month replay, use Event Hubs Capture or a pipeline that archives events to Blob Storage/ADLS/a data lake with its own retention policy.

## 7. Ordering: At What Scope Should Order Be Preserved?

### 7.1. Ordering Within a Partition

Within a partition, events are appended in the order Event Hubs records them. Consumers read the partition in log order. This is the foundational guarantee for key-based event processing if producers route consistently.

There is no global ordering across multiple partitions. For example:
- `OrderCreated(1001)` in P0.
- `OrderCreated(2002)` in P1.
- `PaymentAuthorized(1001)` in P0.

A consumer may process P1's event before P0's event. That violates neither partition's ordering.

### 7.2. Ordering in Callbacks and Parallel Processing

Even when events in the same partition are read in order, an application can break ordering itself if the callback dispatches each event to an async executor without limiting concurrency. For example, event version 2 writes to the DB before version 1 because version 1 took longer to process.

If ordering must be preserved:
- Process sequentially per partition or per aggregate key.
- If using parallel processing, only parallelize across independent entities and keep execution sequential per key.
- Check sequence/version in the database before applying changes.
- Only checkpoint up to a position where all preceding events have completed or been isolated per policy.
- Prevent a slow task from letting the checkpoint advance past incomplete events.

### 7.3. Need Global Ordering?

A single partition can create one shared log for the whole event hub, but it limits throughput and concurrency to one partition. If global ordering seems necessary, ask:
- Can it be modeled as per-aggregate/per-entity ordering instead of system-wide?
- Can a business-assigned sequence number be used and validated by the consumer?
- Can events be split by domain and only require ordering within each domain?
- If a single stream is mandatory, what throughput limits and failure bottlenecks are acceptable?

Global ordering usually reduces scalability. Define the **narrowest ordering scope that satisfies business requirements**.

## 8. Hot Partitions and Load Distribution

A hot partition occurs when one or a few partitions receive significantly more events than the rest. Common causes include:
- Low-cardinality partition keys such as `country`, `eventType`, or one huge tenant value.
- A single tenant/device/entity generating most of the traffic.
- Producers specifying a hardcoded partition ID.
- One consumer processing a CPU/I/O-heavy event type while other partitions are light.
- Extreme variance in event sizes.

Aggregate event hub metrics may look healthy while one partition is bottlenecked. Inspect per-partition incoming bytes/messages, consumer lag, and processing behavior where telemetry supports it. Choose partition keys by the entity needing ordering while still evaluating real-world distribution; you cannot simultaneously funnel all events for one entity into one partition and spread that same entity across many partitions while keeping natural ordering.

### 8.1. Mitigations

- Choose a key with suitable cardinality and distribution, e.g. `orderId` instead of `countryCode` if ordering is needed per order.
- Avoid fixed partition IDs without a clear reason.
- Reduce payload size and avoid sending unnecessary data.
- Speed up per-event processing and avoid unnecessary sequential DB/HTTP calls.
- Split domains/streams when workloads have different profiles.
- Evaluate increasing partition count when supported by the tier and test its impact on key mapping.
- Do not split an aggregate across multiple partitions if the business requires ordering unless you have application-level sequencing/merging.

### 8.2. Changing the Partition Count

Partition count is an architectural decision, not a harmless autoscale knob. Whether partition count can be changed depends on namespace type/tier and service limits; some configurations allow increasing but not decreasing. Changing the partition count can alter how partition keys map to partitions, which can affect observed ordering when the same key is routed differently before and after the change.

Before changing:
1. Check tier capabilities and current limits.
2. Evaluate key distribution and ordering requirements.
3. Determine consumer group/checkpoint behavior.
4. Test producers and consumers on a test event hub.
5. Plan the cutover, monitor duplicates/replays, and prepare a viable rollback.

Do not hardcode partition IDs across multiple services if topology may change; prefer business-contract partition keys.

## 9. EventProcessorClient in Java

### 9.1. Why Use EventProcessorClient?

Azure SDK for Java provides **EventProcessorClient** to simplify:
- Partition ownership distribution across multiple instances.
- Load balancing and reclaiming partitions when other instances stop.
- Reading events by consumer group.
- Persisting checkpoints and ownership in a checkpoint store.
- Handling errors through callbacks.

If you use EventHubConsumerClient directly, the application must manage partition enumeration, ownership, checkpointing, load balancing, and recovery itself. For Spring Boot workers running multiple replicas, EventProcessorClient is typically the right choice when you need a distributed consumer group.

### 9.2. Components to Configure

| Component | Purpose | Notes |
|---|---|---|
| Fully qualified namespace | Event Hubs namespace address | Example: `orders-dev.servicebus.windows.net` |
| Event hub name | Stream to read | Each consumer group reads a specific event hub |
| Consumer group | Logical reading cursor | Instances of the same workload share a group |
| TokenCredential | Workload identity | Managed Identity / DefaultAzureCredential |
| Blob container | Ownership/checkpoint store | Container must exist and have proper permissions |
| Process event callback | Handles each event | Commit side effects before checkpointing |
| Process error callback | Observes processor errors | Log partition, exception, and correlation; never log secrets |
| Initial position | Starting point when no checkpoint exists | Choose earliest/latest/time/offset per business rules |

### 9.3. Spring Boot Properties Configuration

The example below uses **custom application-defined properties**, not default keys applicable to every Spring Cloud Azure version:

~~~yaml
app:
  event-hubs:
    namespace: orders-dev.servicebus.windows.net
    event-hub-name: order-events
    consumer-group: order-projection
    checkpoint-container-url: https://ordersdevstore.blob.core.windows.net/eventhub-checkpoints
~~~

Values are illustrative. Production should use separate namespaces, hubs, consumer groups, and checkpoint containers per environment. Do not share a checkpoint container/consumer group between two different logical applications; doing so can cause ownership and reading progress conflicts.

### 9.4. Creating a Processor with Managed Identity

Illustrative skeleton using the Azure SDK directly; dependencies must include compatible artifacts for:
- `azure-messaging-eventhubs`
- `azure-messaging-eventhubs-checkpointstore-blob`
- `azure-storage-blob`
- `azure-identity`
- Spring Boot configuration support

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.BlobContainerClientBuilder;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@ConfigurationProperties(prefix = "app.event-hubs")
record EventHubConsumerProperties(
        String namespace,
        String eventHubName,
        String consumerGroup,
        String checkpointContainerUrl) {}

@Configuration
@EnableConfigurationProperties(EventHubConsumerProperties.class)
class EventHubConsumerConfiguration {

    @Bean
    DefaultAzureCredential azureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean
    BlobContainerAsyncClient checkpointContainer(
            EventHubConsumerProperties properties,
            DefaultAzureCredential credential) {
        return new BlobContainerClientBuilder()
                .endpoint(properties.checkpointContainerUrl())
                .credential(credential)
                .buildAsyncClient();
    }

    @Bean(destroyMethod = "stop")
    EventProcessorClient eventProcessorClient(
            EventHubConsumerProperties properties,
            DefaultAzureCredential credential,
            BlobContainerAsyncClient checkpointContainer) {

        return new EventProcessorClientBuilder()
                .consumerGroup(properties.consumerGroup())
                .credential(
                        properties.namespace(),
                        properties.eventHubName(),
                        credential)
                .checkpointStore(new BlobCheckpointStore(checkpointContainer))
                .processEvent(context -> {
                    // 1. Validate schema and eventId.
                    // 2. Perform idempotent business processing.
                    // 3. Durably commit to database/quarantine.
                    processEventIdempotently(context.getEventData());

                    // Only checkpoint after side effects are durable.
                    context.updateCheckpoint();
                })
                .processError(error -> {
                    // Log exception and partition ID; do not log payload/secrets.
                    System.err.println(
                            "Event processor error: " + error.getThrowable());
                })
                .buildEventProcessorClient();
    }

    @Bean
    ApplicationRunner startEventProcessor(EventProcessorClient processor) {
        return args -> processor.start();
    }

    private static void processEventIdempotently(
            com.azure.messaging.eventhubs.EventData event) {
        // Replace with a processing service that uses transactions and deduplication by eventId.
    }
}
~~~

This is an **illustrative integration skeleton**; verify method signatures against the Azure SDK version managed by your BOM. In real applications:
- Use a structured logger instead of `System.err`.
- Move business processing into a dedicated Spring service for transactions, testing, and metrics.
- Explicitly configure the initial position for consumer groups without a checkpoint yet.
- Manage start/stop lifecycle and graceful shutdown.
- Ensure the checkpoint container exists before the processor starts.
- If processing fails, do not checkpoint past an event that has not been processed or durably quarantined.
- Consider checkpointing per batch/interval instead of per event for high throughput; measure replay window size and cost.

### 9.5. Producer Using a Partition Key

Example producer creating a batch with a partition key based on order ID:

~~~java
import com.azure.messaging.eventhubs.CreateBatchOptions;
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventDataBatch;
import com.azure.messaging.eventhubs.EventHubProducerClient;

public class OrderEventPublisher {
    private final EventHubProducerClient producer;

    public OrderEventPublisher(EventHubProducerClient producer) {
        this.producer = producer;
    }

    public void publish(String orderId, String eventJson) {
        CreateBatchOptions options =
                new CreateBatchOptions().setPartitionKey(orderId);

        EventDataBatch batch = producer.createBatch(options);
        if (!batch.tryAdd(new EventData(eventJson))) {
            throw new IllegalArgumentException(
                    "Event does not fit in an empty Event Hubs batch");
        }
        producer.send(batch);
    }
}
~~~

When using the same partition key, events for an order can be routed to the same partition under stable topology. Producers should:
- Use the exact same key rule for all events of the same aggregate.
- Never let one service use order ID and another use customer ID for the same event type if shared ordering is required.
- Include event ID and aggregate version in the payload.
- Handle send timeouts idempotently; a lost response does not prove the event was not received.
- Create a reusable producer client tied to the bean lifecycle rather than instantiating per request.

### 9.6. Role of Spring Cloud Azure

Spring Cloud Azure provides starters and auto-configuration for Spring Boot, though supported abstraction levels/annotations can vary across major versions. Before choosing a starter:
- Check the compatibility matrix between Spring Boot and the Spring Cloud Azure BOM.
- Confirm the API supports consumer groups, checkpoint stores, manual processing, and required callbacks.
- If fine-grained control over partition ownership/checkpointing is needed, use the Azure SDK EventProcessorClient directly inside a Spring-managed bean.
- Do not instantiate two processor clients simultaneously for the same workload/consumer group in one instance unless intentional.
- Configure Managed Identity/DefaultAzureCredential per environment; local developer credentials are not the same as runtime identity on Azure.

## 10. Checkpoints, Duplicates, and Error Handling

### 10.1. Commit First, Checkpoint After

The common safety rule is **process durable side effects first, then checkpoint**. This yields at-least-once semantics at the consumer layer: events may be reprocessed, but they will not be skipped because the checkpoint advanced before the commit.

| Order | Failure | Consequence |
|---|---|---|
| Checkpoint → DB commit | Process crashes between steps | Checkpoint moved past event, DB not written: processing may be lost |
| DB commit → Checkpoint | Process crashes between steps | DB written, old checkpoint: event is re-read |
| DB commit + dedup → Checkpoint | Process crashes between steps | Event is re-read, but dedup prevents duplicate side effects |
| Durable quarantine → Checkpoint | Invalid-schema event cannot be processed | Event is isolated, stream continues per policy |

### 10.2. Consumer Idempotency

Use a unique event ID and an inbox/processed-event table:
- Write the event ID and business changes within the same database transaction.
- Place a unique constraint on event ID or `(consumerName, eventId)`.
- If the event was already processed, skip repeating side effects.
- If the same event ID arrives with a different payload, record a conflict for investigation.
- Retain deduplication records at least as long as replays/duplicates can occur per business policy.

Do not rely solely on offsets for deduplication. After switching consumer groups or replaying, the same event may be read under different circumstances; the event ID is a more durable business identifier.

### 10.3. Poison Events and Checkpointing

Events with invalid schemas or data violating invariants can cause callbacks to fail repeatedly. Event Hubs does not provide a queue-style built-in DLQ like Service Bus. You can:
- Save the raw event/required metadata to a **quarantine store** or a separate error-handling queue.
- Record partition ID, offset, sequence number, event ID, and failure reason.
- Only checkpoint past that event after quarantine storage succeeds and policy allows skipping.
- If durable storage fails, do not checkpoint past the event; halt/put the partition into an intervention state per operational strategy.
- Provide a replay tool after fixing the schema/handler.

Do not log full sensitive payloads to the console or Application Insights. Quarantined data also requires RBAC, retention, encryption, and cleanup.

## 11. Application-Level Ordering and Concurrency

A partition has only one owner in a consumer group, yet that does not guarantee all external side effects finish in order if your code processes them in parallel.

For example:
1. Callback receives `OrderStatusChanged(version=1)`.
2. Next callback receives `version=2`.
3. Application submits both events to an executor.
4. Version 2 commits before version 1.
5. DB state regresses if version 1 overwrites later.

Protections:
- Process sequentially within each partition if partition order matters.
- Use a per-key serial executor when a partition holds many independent entities but per-entity ordering is needed.
- Use optimistic concurrency with aggregate version.
- Only checkpoint up to the last event in a safely processed contiguous prefix.
- Bound the number of in-flight events and apply backpressure to avoid unbounded internal queues.

If a partition has a very slow event, sequential processing can increase partition lag. You can hand heavy work off to a queue/worker after durably recording the event, provided ordering/version contracts are preserved where business execution happens.

## 12. Security and Authorization

Event Hubs and checkpoint Blob Storage are two separate resources; workloads typically need permissions on both:
- **Event Hubs Data Receiver** on the event hub/namespace to read events.
- **Storage Blob Data Contributor** on the checkpoint container to create/update ownership and checkpoints.
- Producers need **Event Hubs Data Sender**.
- Never grant **Owner/Contributor** namespace management roles just to send/receive events.
- Use Managed Identity or workload identity; restrict long-lived SAS/connection strings.
- Isolate namespaces, event hubs, consumer groups, and checkpoint containers per environment.
- Do not share a checkpoint container across different logical consumers if there is any risk of name/ownership and progress collision.
- Verify private endpoints, DNS, firewalls, TLS, and network paths from the runtime.

A consumer group is not a security boundary. If a principal has broad namespace read permissions, changing consumer groups does not restrict data access. RBAC scopes must be attached to the appropriate namespace/event hub and role.

### 12.1. Verifying Runtime Identity

Local developers may use Azure CLI credentials via DefaultAzureCredential, whereas apps on App Service/AKS use Managed Identity/Workload Identity. Therefore:
- Identify the actual principal running in dev, staging, and production.
- Assign data roles at the right scope.
- Grant Blob checkpoint permissions separately.
- Never copy production SAS tokens for local testing.
- Log sanitized tenant/principal/resource context, never access tokens.

## 13. Monitoring and Capacity Planning

Key metrics:

| Category | Metrics | Why Monitor |
|---|---|---|
| Ingestion | Incoming messages/bytes, requests, throttled requests | Detect producers exceeding capacity |
| Consumer | Outgoing messages, consumer lag, event age | Know whether consumers keep up with the stream |
| Partition | Per-partition throughput and lag, ownership changes | Detect hot partitions or continuous rebalancing |
| Checkpoint | Last checkpoint timestamp, checkpoint errors, Blob latency | Detect reading progress failing to save |
| Processing | Event processing duration, failure count, duplicates suppressed | Find slow callbacks and business errors |
| Runtime | CPU, memory, thread pools, network, connections | Identify bottlenecks inside workers |
| Quarantine | Poison event count, replay count, backlog | Track isolated events |
| Capacity/cost | Throughput/capacity units, tier, storage, networking | Plan scaling and costs |

Consumer lag can be measured by the gap between the partition tail and the checkpoint/consumer position, or by the age of unprocessed events. Distinguish between:
- **Ingestion lag:** producers have not sent or events have not entered the hub.
- **Processing lag:** events entered the hub, but consumers process slowly.
- **Checkpoint lag:** consumers processed events, but checkpoints have not been saved.
- **Business lag:** events were read, but business side effects have not completed.

Adding partitions only partially helps if the bottleneck is the DB, Blob checkpoint store, network, or processing logic. Per-partition monitoring helps identify whether hot partitions exist.

## 14. Testing Partitions, Consumer Groups, and Ordering

Use dedicated test namespaces/event hubs, consumer groups, and Blob checkpoint containers. Never reset production checkpoints or alter production partition counts for experimentation.

| Scenario | How to Test | Expected Result |
|---|---|---|
| Stable partition key | Send multiple events with the same orderId | Events with the same key route to the same partition under stable topology |
| Multiple keys | Send events across many orderIds | Load is distributed without one abnormally hot partition |
| Multiple consumer instances | Scale from 1 to 3 instances in the same group | Ownership is redistributed; not every instance reads the entire stream |
| Multiple consumer groups | Analytics and fraud read the same event hub | Both groups maintain independent progress |
| Instance crash before checkpoint | Stop worker after side effect but before checkpoint | Events may replay; dedup prevents duplicate side effects |
| Checkpoint store unavailable | Block permissions/network to test Blob | Processor reports errors; does not assume checkpoints were saved |
| Poison event | Send invalid-schema payload | Quarantined or halted per policy; does not checkpoint past without durable save |
| Hot partition | Send most events with one key | Metrics show skewed lag/throughput; key skew identified |
| Business out-of-order events | Send aggregate versions out of order | Consumer detects version gap/stale event |
| Replay from older checkpoint | Use a new test consumer group or target position | Events are reprocessed safely |
| Retention expiration | Simulate consumer stopped longer than retention on test | Alerts fire and recovery runbook uses archive if available |
| Cross-environment access | Use dev identity to access prod event hub | Denied by RBAC/network |

### 14.1. Testing Ordering with Event ID and Sequence

A test payload can include:
~~~json
{
  "eventId": "evt-1001-v2",
  "aggregateId": "order-1001",
  "aggregateVersion": 2,
  "eventType": "OrderPaid"
}
~~~

Send version 1 and 2 with the same partition key. The consumer records partition ID, sequence number, offset, event ID, and aggregate version. Verify:
- Whether the same key lands in the same partition.
- Whether enqueue order matches expectations.
- Whether consumer processing preserves order when concurrency is enabled.
- Whether replay/duplicates cause duplicate side effects.
- Whether changing partition count affects routing.

Do not rely solely on system timestamps as proof of ordering. Record business sequence/version alongside Event Hubs metadata.

## 15. Real-World Scenarios and How to Handle Them

### Scenario A: Scaling Pods Does Not Increase Throughput

An event hub has 4 partitions; the application scales from 4 to 12 pods in the same consumer group. Only 4 pods can own partitions in a steady state; extra pods do not create extra partitions. Check partition count, ownership, and consumer lag. If partitions are saturated, evaluate increasing partitions when supported, choosing better keys, or optimizing handlers before adding instances.

### Scenario B: One Customer Creates a Hot Partition

The producer uses `tenantId` as the partition key; one large tenant generates 70% of traffic. All events for that tenant go to one partition, making that partition's consumer lag even though other partitions are idle. If ordering is only needed per `orderId`, switching the key to order ID can distribute load better. If per-tenant ordering is truly required, consider sharding the tenant logically with sequencing/merging, accepting the extra complexity.

### Scenario C: Events Are Reprocessed After a Pod Restart

The consumer commits to the DB, then the pod crashes before updating the checkpoint. When the processor restarts, events are read from the older checkpoint. Event Hubs did not lose anything; that is consumer at-least-once semantics. Add an inbox table/unique event ID to skip already-committed side effects, then advance the checkpoint.

### Scenario D: Event Version 3 Arrives Before Version 2

Multiple producers send concurrently or the application processes in parallel, causing version 3 to finish before version 2. Partition ordering only reflects append order, not guaranteed arrival of business versions. Consumers need aggregate versions, gap checks, and buffering/quarantine; never overwrite state merely in callback completion order.

### Scenario E: A New Consumer Reads from the Beginning and Causes Heavy Load

A new consumer group is created with initial position earliest, causing it to re-read the entire retention window. This can spike outgoing throughput, Blob checkpoint I/O, DB writes, and costs. Throttle replay rates, run in an isolated environment or from an archive, ensure side effects are idempotent, and monitor backlog.

## 16. Quick Comparison with Other Messaging Models

| Concept | Event Hubs | Service Bus | Kafka (General Concept) |
|---|---|---|---|
| Distribution unit | Partition | Queue/topic subscription | Topic partition |
| Consumer group | Consumer group | Receiver/subscription and competing consumers | Consumer group |
| Progress | Offset + checkpoint | Settlement/Complete/lock | Offset commit |
| Replay | Within retention by offset | Not a replay log; DLQ/resubmit per lifecycle | By retention and offset |
| Ordering | Within a partition | Sessions to group ordered messages | Within a partition |
| Consumer scaling | Partition ownership in group | Multiple receivers competing for messages | Partition assignment in group |
| Best suited for | Streaming/ingestion | Commands/workflows | Distributed event log/streaming |

Event Hubs provides a Kafka-compatible endpoint for certain clients, but do not assume every Kafka configuration, API, offset behavior, or feature behaves identically. Using the Azure SDK EventProcessorClient vs. a Kafka client are two integration approaches with different operational models; pick one consistently and manage consumer groups/offsets/checkpoints coherently.

## 17. Pre-Production Design Checklist

- **Partition count:** matches throughput, number of consumer groups, instance count, and scalability; includes a plan if changes are needed.
- **Partition key:** reflects the entity needing ordering, distributes well, avoids hot keys; all producers use the same contract.
- **Consumer group:** one group per logical application; instances of the same workload share a group.
- **Ownership:** uses EventProcessorClient and an appropriate checkpoint store; rebalancing and partition-bounded parallelism are understood.
- **Checkpoint:** updated only after durable side effects or quarantine; frequency chosen per replay budget.
- **Idempotency:** stable event ID, unique constraint/inbox, handles duplicates and replays.
- **Ordering:** distinguishes partition order from business order; includes aggregate version/sequence if needed.
- **Retention/replay:** clear initial position, retention, archive/Capture, and replay procedures.
- **Security:** Managed Identity, Event Hubs Data Receiver/Sender, Blob Data Contributor, least-privilege scope, no exposed secrets.
- **Operations:** per-partition metrics, lag, checkpoint age, rebalances, throttling, poison events, and Blob checkpoint health.
- **Testing:** scale-out/in, crash before/after checkpoint, hot partitions, out-of-order events, replay, and cross-environment denial.
- **Cost:** capacity/tier, retention, Capture, checkpoint storage, networking, logs, and number of consumer groups.

## 18. Summary

**Partitions** are the unit of log storage, load distribution, and local ordering. A **consumer group** is an independent logical reading cursor; instances in the same group coordinate to share partitions. **Offsets** identify event positions, while **checkpoints** persist processing progress for resume/replay. These three concepts cannot replace one another.

When integrating Event Hubs with Spring Boot, choose partition keys based on your business ordering scope, size partition counts for throughput and concurrency, use EventProcessorClient to manage ownership, save checkpoints after durable side effects, and make consumers idempotent. Testing rebalancing, hot partitions, duplicates, replays, and out-of-order events on a dedicated namespace will help your system scale cleanly while preserving data correctness.
