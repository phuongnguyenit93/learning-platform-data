# Partition Key, Checkpoint, and Consumer Load Balancing

## 1. Why Does a Streaming Architecture Need These Three Concepts?

Imagine an e-commerce platform emitting **OrderCreated**, **OrderPaid**, and **OrderShipped** events to Azure Event Hubs. One consumer group updates revenue tables, a second runs fraud analytics, and a third exports data to an analytics warehouse. Every minute the system ingests tens of thousands of events, surging during peak hours.

When the engineering team scales consumer instances from two to six, three anomalies appear:

- Some orders have **OrderPaid** processed before **OrderCreated**.
- An event updates the database twice after a worker restarts.
- Despite adding more workers, one worker remains overloaded and consumer lag keeps growing.

The problem is not simply a lack of CPU. Three concepts govern the design:

**Partition keys** route related events into the same partition to manage ordering. **Checkpoints** record the position safely processed so far. **Consumer load balancing** distributes partition ownership across multiple consumer instances to utilize compute capacity.

This lesson belongs to the **Events and Streaming Data** chapter in the Microsoft Azure ecosystem module, connecting Event Hubs with subscriptions, resource groups, Microsoft Entra ID, virtual networks, compute, Azure Functions, AKS, Blob Storage, security, monitoring, and cost control.

> Foundational rule: **Event Hubs is a partitioned log stream, not a queue that deletes messages as soon as a consumer reads them.** Partition keys, checkpoints, and consumer groups solve three distinct problems and must be designed together.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Explain namespaces, event hubs, partitions, consumer groups, and consumer instances.
2. Distinguish partition keys, partition IDs, offsets, sequence numbers, and event times.
3. Choose partition keys aligned with the unit requiring business ordering.
4. Explain why two different keys can still land in the same partition.
5. Recognize hot partitions and skewed load distribution.
6. Choose partition counts based on parallelism, throughput, and scalability.
7. Distinguish reading an event from checkpointing that processing finished.
8. Design checkpoints strictly after durable writes without skipping processing gaps.
9. Understand partition ownership and rebalancing in EventProcessorClient.
10. Use a Java producer, Java EventProcessorClient, and Azure Blob checkpoint store.
11. Handle crashes, duplicates, retries, idempotency, retention, and replay.
12. Design Azure Functions or AKS consumers, and monitor consumer lag and costs.

## 3. Overall Architecture of Azure Event Hubs

Azure Event Hubs ingests an event stream and stores events across multiple **partitions**. Producers write data, while consumers read one or more partitions via SDKs or supported runtimes.

~~~mermaid
flowchart LR
    P1[Orders API] --> EH[Azure Event Hub]
    P2[Telemetry Gateway] --> EH
    EH --> A[Partition 0]
    EH --> B[Partition 1]
    EH --> C[Partition 2]
    EH --> D[Partition 3]
    A --> G1[Consumer group: analytics]
    B --> G1
    C --> G1
    D --> G1
    A --> G2[Consumer group: fraud]
    B --> G2
    C --> G2
    D --> G2
    G1 --> OUT1[(Analytics Database)]
    G2 --> OUT2[(Fraud Store)]
~~~

Consumer groups read from **the same data stored in the Event Hub** with independent progress and applications. Each consumer group does not create a separate physical copy of the entire log.

### 3.1. Typical layers in a real application

| Layer | Azure or Kubernetes component | Responsibility |
|---|---|---|
| Producer | Azure Functions, App Service, AKS, VMs | Send events per contract |
| Ingestion | Azure Event Hubs | Receive, partition, and retain events within retention |
| Consumer orchestration | EventProcessorClient or Event Hubs trigger | Read events and coordinate ownership |
| Checkpoint store | Azure Blob Storage | Persist progress and ownership |
| Processing | Java/Python/.NET workers | Validate, transform, aggregate, write data |
| Sink | Azure SQL, Cosmos DB, Blob, ADLS | Store results durably |
| Identity | Microsoft Entra ID, managed identity | Authorize sending, receiving, and checkpointing |
| Observability | Azure Monitor, Application Insights | Monitor lag, errors, and cost |

A producer send succeeding does not prove a consumer processed the event. A consumer reading an event does not prove the database committed.

## 4. How Does Event Hubs Differ from an Azure Service Bus Queue?

| Characteristic | Event Hubs | Typical Service Bus queue |
|---|---|---|
| Model | Append-only partitioned event log | Broker managing messages and settlement |
| After consumer reads | Events remain until retention expires | Messages are Completed/settled per receive mode |
| Progress | Consumer offsets/sequences and checkpoints | Locks, Complete, Abandon, DeadLetter |
| Multiple independent groups | Consumer groups reading the same log | Typically topic subscriptions or dedicated topologies |
| Ordering guarantee | Per partition, given proper producer/consumer design | Per entity and sessions |
| Error handling | App designs retries/quarantine | Built-in DLQ mechanism |
| Strengths | Telemetry, event streaming, high-speed ingestion | Commands/workflows, message processing, transactions |

Never apply “Complete an event to delete it from Event Hubs” thinking as in Service Bus. **Checkpointing is neither deletion nor a broker-level work ACK.**

## 5. Partition: Unit of Log and Unit of Parallelism

Each Event Hub has a number of partitions. The broker appends events into each partition in a deterministic order within that partition.

~~~text
Partition 0: seq 100 -> 101 -> 102 -> 103 -> ...
Partition 1: seq  30 ->  31 ->  32 ->  33 -> ...
Partition 2: seq 240 -> 241 -> 242 -> 243 -> ...
Partition 3: seq  80 ->  81 ->  82 ->  83 -> ...
~~~

**Sequence numbers** are scoped per partition. Sequence 100 on partition 0 did not necessarily happen before sequence 240 on partition 2.

A processor is typically assigned one or more partitions to handle. Partition count imposes a key ceiling on how many consumers can concurrently own and process independent partition streams in one consumer group.

### 5.1. Is global ordering guaranteed?

No. Event Hubs does not provide a single global order across all partitions. If event A and event B land in two different partitions, they can be processed in any relative order.

### 5.2. Per-partition order still requires proper producers

Event Hubs preserves the order of events **appended to** a partition by sequence. Yet if two uncoordinated producers send OrderPaid and OrderCreated, or a network retry causes OrderPaid to reach the broker first, the log reflects broker arrival order rather than fixing business order.

When business order matters, include event versions/sequences and serialize producer emissions appropriately.

## 6. What Is a Partition Key?

A **partition key** is a key specified by the producer so events sharing that key are routed consistently to the same partition while partition count and routing remain unchanged.

Example:

~~~text
Event A: OrderCreated, orderId=ORD-1001, key=ORD-1001
Event B: OrderPaid,    orderId=ORD-1001, key=ORD-1001
Event C: OrderShipped, orderId=ORD-1001, key=ORD-1001

Event D: OrderCreated, orderId=ORD-1002, key=ORD-1002
~~~

Under a stable partition configuration, A/B/C share the same partition key and land in the same partition. D may go to a different partition, **or it may share the same partition** because multiple keys can map to one partition.

A partition key is **routing** metadata—it is not an eventId, business operation key, unique constraint, or idempotency mechanism.

### 6.1. When should you use a partition key?

When you need events for the same aggregate/entity to stay in one partition, such as:

- **orderId** for order lifecycle state.
- **accountId** for mutations on a single account.
- **deviceId** for readings from one device.
- **customerId** if true per-customer ordering is required.
- **aggregateId** in event-sourcing models.

### 6.2. When is a key unnecessary?

If events are independent and require no per-entity ordering, omit the key so the SDK/broker distributes traffic across partitions. This helps spread load, though it provides no affinity for related events.

## 7. How Does Partition Key Differ from Partition ID?

| Attribute | Partition key | Partition ID |
|---|---|---|
| Meaning | Logical key of the data | Physical identifier of the partition |
| Who chooses? | Producer based on business domain | Created by broker; producer may specify explicitly via certain APIs |
| Example | ORD-1001 | 0, 1, 2 |
| Topology coupling | Lower | Higher |
| Suited for per-entity ordering | Usually yes | Possible, but requires manual consistent routing |
| When partition count changes | Mapping can shift | Requires topology review and migration |

Do not assume the key-to-ID formula is always **hash(key) % partitionCount** across every version. Hashing explains the concept, but internal SDK/broker hashing details should not become a business contract if the service does not guarantee that exact formula.

### 7.1. Same key does not guarantee staying on the same Partition ID forever

When partition count changes (in SKUs/features supporting it), key-to-partition mapping can change. Historical ordering for the same key across two topologies must be handled at the business layer or via a migration plan.

### 7.2. Avoid conflicting specifications

When creating batches via the SDK, you normally specify **either** a partition key **or** a partition ID per SDK rules. Never assume both can be set together on the same batch.

## 8. Choose Keys by Ordering Unit, Not Intuition

| Event type | Suggested key | Condition to verify |
|---|---|---|
| Order lifecycle | orderId | Ordering only needed within each order |
| Wallet transactions | walletId | Is strict ordering required across all wallet transactions? |
| IoT readings | deviceId | Readings from one device must follow write order |
| Customer notifications | customerId | Is there risk of a massive customer creating a hot partition? |
| Independent telemetry | May omit key | Per-entity ordering unnecessary |
| Bank ledger | accountId or dedicated design | Transactional correctness requires ordering outside the broker |

### 8.1. Keys that are too coarse

Using **tenantId** when one tenant generates 60–80% of traffic concentrates most events onto one partition.

### 8.2. Keys that are too granular

Using a distinct random UUID per event spreads load well but destroys the ability to keep OrderCreated and OrderPaid on the same partition.

### 8.3. Keys containing sensitive data

Avoid using emails, phone numbers, usernames, or card numbers directly as partition keys unless strictly necessary. Keys may appear in metadata and logs. Prefer internal IDs or tokenized values per security policy.

### 8.4. Keys that change with timestamps

Never append a timestamp to the key of every event if the same entity must stay in the same partition. That defeats stable key routing.

## 9. Hot Partitions and Key Skew

A **hot partition** is a partition receiving disproportionately more incoming events/bytes or processing work than other partitions.

~~~text
Example Event Hub with 4 partitions:

Partition 0: ████████████████████████   70%
Partition 1: ████                       10%
Partition 2: ████                       10%
Partition 3: ████                       10%
~~~

If 70% of events use partition key **tenant-giant**, they all land in partition 0. Even with four consumers, the single consumer owning partition 0 shoulders most of the load.

### 9.1. Symptoms

- Consumer lag concentrates on a single partition.
- One processor sits at high CPU while others are nearly idle.
- Adding consumer instances does not drain the backlog faster.
- A few entity keys generate disproportionate event volume.
- Processing latency on the hot partition breaches SLO.

### 9.2. Mitigations

1. Measure partition key distribution at producers/telemetry.
2. Re-evaluate how strict ordering truly needs to be.
3. Narrow the key from **tenantId** to **orderId** if business rules only require per-order ordering.
4. Optimize consumers, DB batch writes, and network I/O.
5. Consider subkeys/sharding if relaxing global-key ordering is acceptable.
6. Plan topology and partition counts within SKU capabilities and real needs.

**Never tack on a random suffix to a partition key arbitrarily** if the application depends on per-entity ordering; that improves balance at the cost of breaking business correctness.

## 10. Choosing Partition Count for an Event Hub

Partition count sets a key boundary on parallelism and key distribution.

| Partitions | Consumer instances | Approx. distribution after rebalance | Meaning |
|---:|---:|---|---|
| 4 | 1 | 4 | One consumer handles everything |
| 4 | 2 | 2 + 2 | Two processors share load |
| 4 | 3 | 2 + 1 + 1 | Distribution may be uneven |
| 4 | 4 | 1 + 1 + 1 + 1 | One partition per processor |
| 4 | 6 | 4 processors hold partitions; 2 may sit idle | Adding Pods may not increase throughput |
| 12 | 4 | Around 3 + 3 + 3 + 3 | Room to scale out consumers |

This represents typical **partition ownership** behavior under EventProcessorClient in steady state, not a hard guarantee at every instant.

### 10.1. Does adding partitions always increase throughput?

No. Event Hubs namespaces/tiers also enforce ingress/egress/capacity limits, and consumers may bottleneck on downstream databases. Extra partitions only help when they unlock real parallelism and downstream resources keep up.

### 10.2. Can you change partition count after creation?

Whether you can increase or adjust partitions depends on SKU, features, and support at creation time. Never assume you can shrink partitions or preserve existing key routing after a change. Plan capacity and migrations upfront.

### 10.3. Many partitions carry operational overhead

Every partition maintains processor context, checkpoints, ownership leases, and telemetry. Pick a sensible count rather than choosing an excessive number before workloads need it.

## 11. A Consumer Group Is an Independent Read View

Consumer groups let multiple applications process the same log with **independent progress**.

Example:

~~~text
Event Hub: order-events
├── Consumer group: analytics-prod
│   ├── analytics-worker-1
│   ├── analytics-worker-2
│   └── analytics-worker-3
├── Consumer group: fraud-prod
│   ├── fraud-worker-1
│   └── fraud-worker-2
└── Consumer group: archive-prod
    └── archive-worker-1
~~~

Analytics failing and re-reading events does not force fraud or archive to re-read. Each consumer group maintains its own configuration and read progress.

### 11.1. A consumer group is not a message copy

Event Hubs stores one log per retention settings rather than duplicating every event per consumer group.

### 11.2. Separate consumer groups per application

Distinct pipelines needing independent checkpoint policies, schemas, and ownership should use separate consumer groups. Never let an experimental dashboard write checkpoints that disrupt a production consumer.

### 11.3. Replicas of the same application typically share a group

Three AKS Pods running the same analytics pipeline should share group **analytics-prod** and the same checkpoint/ownership store to divide partitions.

### 11.4. Do not abuse $Default

If multiple independent apps share **$Default**, permissions, progress, and ownership easily collide. Use explicit names tied to each pipeline and environment.

## 12. Offset, Sequence Number, and Timestamp

Each event in a partition carries metadata:

| Attribute | Meaning | Notes |
|---|---|---|
| **Partition ID** | Partition holding the event | Do not compare IDs as chronological order |
| **Sequence number** | Broker-assigned order within partition | Not a global sequence |
| **Offset** | Position on the partition log | Used for resume/start positions |
| **Enqueued time** | Timestamp when broker accepted event | Differs from producer event time |
| **Partition key** | Routing key if set by producer | Not necessarily eventId |
| **Event ID** | Business/application identifier | Per event contract |
| **Aggregate version** | Business order for one aggregate | Enforced by the application |

Example:

~~~text
Partition 2:
  seq 150 -> OrderCreated(ORD-1001, version=1)
  seq 151 -> OrderCreated(ORD-1002, version=1)
  seq 152 -> OrderPaid(ORD-1001, version=2)
  seq 153 -> OrderShipped(ORD-1001, version=3)
~~~

Sequences 150, 152, and 153 are not contiguous for ORD-1001 because the partition also holds events for other orders.

### 12.1. Event time differs from enqueue time

A device may record an event at 10:00, lose connectivity, and send it to Event Hubs at 10:10. Business time differs from broker enqueue time; never use enqueue time to infer absolute cross-device occurrence order.

## 13. What Is a Checkpoint?

A **checkpoint** records the position a consumer has safely processed in each partition. When a processor restarts, it can resume from after the checkpoint per SDK rules.

~~~text
Partition 0: 100 -> 101 -> 102 -> 103 -> 104 -> 105
                           ^
                    checkpoint 102

Restart: resumes from after 102 per processor mechanics.
~~~

Checkpointing does not delete events from Event Hubs. Older events remain until retention expires or service data policies remove them.

### 13.1. Distinguish checkpoints from Service Bus Complete

- **Service Bus Complete:** settles and removes a message in a queue.
- **Azure Queue Storage Delete:** deletes the message.
- **Event Hubs checkpoint:** saves committed read progress; does not delete the event.
- **Kafka offset commit:** similar progress concept over the Kafka protocol, not automatically identical to the Event Hubs SDK Blob checkpoint store.

### 13.2. Checkpoints are recorded per partition

A consumer group reading multiple partitions needs progress tracked per partition. A checkpoint on partition 0 does not advance partition 1.

## 14. Why Do You Need a Checkpoint Store?

If checkpoints live only in a process's RAM, progress vanishes when the process dies. Thus, when using **Azure EventProcessorClient** with the Java SDK, apps commonly use an **Azure Blob Storage checkpoint store**.

The store holds two kinds of information:

1. **Checkpoints:** last processed position for each partition.
2. **Partition ownership:** which processor instance currently claims/coordinates each partition.

~~~mermaid
flowchart TD
    EH[(Event Hub: 4 partitions)] --> A[Processor A]
    EH --> B[Processor B]
    A <--> ST[(Azure Blob checkpoint store)]
    B <--> ST
    A --> DB[(Business database)]
    B --> DB
~~~

### 14.1. The store does not hold full event payloads

Checkpoint Blobs hold progress/ownership metadata needed by processors, not an archive of every event. For long-term event archival, use Event Hubs Capture or a dedicated archival pipeline.

### 14.2. The store requires real data-plane permissions

An application identity authorized to read Event Hubs but lacking permission to write Blob checkpoints will hit ownership/checkpoint failures. Verify permissions on **both Event Hubs and Storage**.

### 14.3. Why should checkpoint stores never be split arbitrarily?

Two processors in the same pipeline using different checkpoint stores fail to share ownership metadata and can process the same partitions concurrently. Standardize one logical store across replicas of the same pipeline.

## 15. When Should Checkpoints Be Written?

Common safe workflow:

1. Receive event from Event Hubs.
2. Parse and validate schema.
3. Execute business logic.
4. Persist results durably to database/storage.
5. Wait for transaction/operation commit to succeed.
6. Then **update checkpoint**.

~~~mermaid
sequenceDiagram
    participant EH as Event Hubs
    participant C as Consumer
    participant DB as Database
    participant CS as Blob checkpoint store
    EH-->>C: Event seq 200
    C->>C: Validate
    C->>DB: Write result with idempotency key
    DB-->>C: Commit succeeds
    C->>CS: Checkpoint seq 200
    CS-->>C: Write succeeds
~~~

**Checkpointing before DB commit** risks losing events silently after a crash. **Committing before checkpointing** risks duplicate processing after a crash, making idempotency mandatory.

### 15.1. Checkpointing does not mean “just received”

Entering the callback only proves the consumer received the event, not that business processing completed.

### 15.2. Never checkpoint past unresolved errors

If seq 201 fails and seq 202 succeeds, checkpointing 202 risks skipping seq 201 on restart. Checkpoint only up to the **highest contiguous safely processed position**.

## 16. Checkpoint Frequency: Per Event, Per Batch, or Per Time Interval?

| Strategy | Pros | Cons |
|---|---|---|
| Checkpoint per event | Fewest events reprocessed after crash | High Blob write volume/overhead |
| Checkpoint every N events | Reduces I/O and checkpoint cost | Crash may replay part of a batch |
| Checkpoint on timer | Bounds maximum gap without writing | Must still verify contiguous processed state |
| Checkpoint after durable batch transaction | Aligns with batch commit outcome | Requires compatible batch/transaction design |

Example:

~~~text
Checkpoint at sequence 500
Consumer succeeds on 501..550 without checkpointing yet
Consumer crashes
New processor resumes after 500
=> Events 501..550 may be re-read
~~~

If the consumer already wrote results to the database, duplicate replay is safe only with unique constraints, idempotent upserts, or proper transaction checks.

### 16.1. Never optimize Blob operations at the cost of losing data

Checkpointing too rarely saves writes at the expense of higher replay cost. Checkpointing past failed items drops business events—far worse than extra Blob operations.

### 16.2. Balance against RTO and idempotency

Choose frequency based on throughput, acceptable replay time, I/O cost, and downstream sink reliability.

## 17. Concurrent Processing Within One Partition and Risk of Data Loss

Suppose a consumer processes events concurrently inside one partition:

~~~text
seq 100: finished
seq 101: NOT finished
seq 102: finished
seq 103: finished
~~~

If you checkpoint 103 because it is the highest completed sequence, event 101 may never be re-read after a restart.

### 17.1. Safe high-water mark

Checkpoints should advance only to the **highest contiguous processed sequence**. In this example, since 100 finished while 101 has not, the safe checkpoint remains 100.

### 17.2. Preserve ordering when business rules require it

For OrderCreated → OrderPaid, running events from the same partition concurrently can let the later event finish first. When order matters, process sequentially per partition or coordinate safely by aggregate key.

### 17.3. Parallelism across partitions is simpler

A consumer instance can process multiple partitions concurrently, handling each partition sequentially internally. This is much easier to reason about than spinning up arbitrary thread pools inside each partition.

## 18. EventProcessorClient and Ownership Mechanics

**EventProcessorClient** in the Azure SDK helps:

- Automatically discover/read Event Hub partitions.
- Coordinate multiple processor instances in the same consumer group.
- Claim and renew partition ownership via the checkpoint store.
- Distribute partitions across processors.
- Resume from saved checkpoints at startup.
- Dispatch callbacks for events and errors.
- Allow updating checkpoints after business success.

This eliminates having to hand-roll partition management and failover logic.

### 18.1. Ownership does not mean absolute business exclusivity

One partition normally has one processor owner during steady-state coordination. However, network delays, worker crashes, or ownership handoffs can still cause brief overlapping reads. **Never replace idempotency with ownership.**

### 18.2. Checkpoint store coordinates via shared state

Each processor inspects ownership records and claims available partitions. It does not need a static list of Pod IPs.

### 18.3. Sharing a consumer group name is not enough

If processors in the same pipeline use **two uncoordinated checkpoint stores**, they can read the exact same partitions simultaneously. Ensure both the consumer group and checkpoint store align.

## 19. Rebalancing When Consumers Join or Leave

Example: an Event Hub has 6 partitions and two processors:

~~~text
Before:
  Processor A: P0 P1 P2
  Processor B: P3 P4 P5

After Processor C joins:
  A: P0 P1
  B: P2 P3
  C: P4 P5
~~~

If B dies:

~~~text
After detecting B's ownership expired:
  A: P0 P1 P2
  C: P3 P4 P5
~~~

This is an illustrative diagram. Actual rebalance algorithms and timing depend on SDK, claim intervals, checkpoint store health, and runtime conditions.

### 19.1. Handoffs can re-read a tail window

B wrote to the database without checkpointing; C claims the partition and resumes from the older checkpoint. This is normal under **at-least-once** delivery.

### 19.2. Frequent rebalancing is a red flag

If Pods crash-loop or checkpoint store calls time out, partition ownership flaps. This causes repeated re-reads, cache warm-ups, and rising lag. Monitor ownership change frequency alongside processor health.

### 19.3. Graceful shutdown helps but does not eliminate duplicates

During controlled Pod termination, stop accepting new work, finish/checkpoint in-flight events safely, and then stop the processor. Sudden node crashes can still occur.

## 20. Why Balancing Partition Count Does Not Always Balance CPU

Suppose an Event Hub has 4 partitions and 4 consumers:

~~~text
P0: 75% events -> Consumer A, CPU 95%
P1:  8% events -> Consumer B, CPU 15%
P2:  9% events -> Consumer C, CPU 18%
P3:  8% events -> Consumer D, CPU 16%
~~~

The ownership algorithm distributed partition counts evenly, yet workload remains skewed. This typically happens under **partition key skew**.

### 20.1. Measure per partition

- Incoming events/bytes per partition where available.
- Last enqueued sequence.
- Last processed/checkpointed sequence.
- Checkpoint age and consumer lag.
- CPU/memory/latency of the processor owning each partition.
- Distribution of business keys (without logging sensitive data).

### 20.2. When does adding consumers help?

When a single processor currently owns multiple busy partitions. Adding processors spreads those partitions onto other instances.

### 20.3. When does it not help?

When the bottleneck is a single hot partition or a shared database. Scaling Pods beyond the partition count only adds cost and rebalance churn.

## 21. Java Producer: Sending by Partition Key

Java example using **azure-messaging-eventhubs** and **azure-identity** to send events for the same order with a single partition key.

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventDataBatch;
import com.azure.messaging.eventhubs.EventHubClientBuilder;
import com.azure.messaging.eventhubs.EventHubProducerClient;
import com.azure.messaging.eventhubs.models.CreateBatchOptions;

public class OrderProducer {
    public static void main(String[] args) {
        String namespace = System.getenv("EVENTHUB_NAMESPACE");
        String eventHub = System.getenv("EVENTHUB_NAME");
        String orderId = "ORD-1001";

        try (EventHubProducerClient producer =
                 new EventHubClientBuilder()
                     .credential(
                         namespace, eventHub,
                         new DefaultAzureCredentialBuilder().build())
                     .buildProducerClient()) {

            EventDataBatch batch = producer.createBatch(
                new CreateBatchOptions().setPartitionKey(orderId));

            boolean first = batch.tryAdd(new EventData(
                "{\"eventType\":\"OrderCreated\",\"orderId\":\"ORD-1001\"}"));
            boolean second = first && batch.tryAdd(new EventData(
                "{\"eventType\":\"OrderPaid\",\"orderId\":\"ORD-1001\"}"));

            if (!first || !second) {
                throw new IllegalStateException("Batch size exceeded");
            }

            producer.send(batch);
            System.out.println("Sent key=" + orderId);
        }
    }
}
~~~

### 21.1. Preparing the environment properly

- **EVENTHUB_NAMESPACE**: fully qualified namespace such as **ehns-name.servicebus.windows.net**.
- **EVENTHUB_NAME**: Event Hub name, not the namespace.
- Producer identity needs **Azure Event Hubs Data Sender** or equivalent role.
- Events must fit SDK/SKU size limits.
- Use Maven/Gradle dependency versions compatible with your Java runtime.

### 21.2. Same key alone does not guarantee business order

If multiple producers send concurrently or retry without sequence control, the broker stores events in arrival order. Use **aggregateVersion** and producer coordination when strict order is required.

### 21.3. Send timeouts can create duplicates

If the broker commits an event while the network drops the acknowledgment to the producer, a send retry can append a second equivalent event. Consumers still require idempotency by eventId.

## 22. Java Consumer: EventProcessorClient and BlobCheckpointStore

Required dependencies:

- **azure-messaging-eventhubs**
- **azure-messaging-eventhubs-checkpointstore-blob**
- **azure-storage-blob**
- **azure-identity**

Illustrative example configuring a processor with an **existing Blob checkpoint container**:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.BlobContainerClientBuilder;

public class EventHubConsumer {
    public static void main(String[] args)
            throws InterruptedException {

        String namespace = System.getenv("EVENTHUB_NAMESPACE");
        String hubName = System.getenv("EVENTHUB_NAME");
        String group = System.getenv("EVENTHUB_CONSUMER_GROUP");
        String blobEndpoint = System.getenv("CHECKPOINT_BLOB_ENDPOINT");
        String container = System.getenv("CHECKPOINT_CONTAINER");

        TokenCredential identity =
            new DefaultAzureCredentialBuilder().build();

        BlobContainerAsyncClient blobClient =
            new BlobContainerClientBuilder()
                .endpoint(blobEndpoint)
                .containerName(container)
                .credential(identity)
                .buildAsyncClient();

        EventProcessorClient processor =
            new EventProcessorClientBuilder()
                .credential(namespace, hubName, identity)
                .consumerGroup(group)
                .checkpointStore(new BlobCheckpointStore(blobClient))
                .processEvent(context -> {
                    String partition =
                        context.getPartitionContext().getPartitionId();
                    long sequence =
                        context.getEventData().getSequenceNumber();

                    try {
                        // Demo: replace with durable, idempotent database write.
                        processDurably(
                            context.getEventData().getBodyAsString());

                        // Checkpoint after business logic commits.
                        context.updateCheckpoint();

                        System.out.printf(
                            "Processed partition=%s seq=%d%n",
                            partition, sequence);
                    } catch (Exception ex) {
                        System.err.printf(
                            "FAILED partition=%s seq=%d error=%s%n",
                            partition, sequence, ex.getClass().getName());

                        // Do not checkpoint failed event.
                        // Production must pause/retry/quarantine per policy.
                    }
                })
                .processError(error -> {
                    System.err.println(
                        "Processor error: " + error.getThrowable());
                })
                .buildEventProcessorClient();

        processor.start();
        Thread.sleep(60_000); // Local demo only.
        processor.stop();
    }

    private static void processDurably(String body) {
        // Placeholder: NOT a real durable storage write.
        if (body == null || body.isEmpty()) {
            throw new IllegalArgumentException("Empty event");
        }
    }
}
~~~

### 22.1. Important conditions

- **CHECKPOINT_BLOB_ENDPOINT** looks like **https://storage-name.blob.core.windows.net**.
- The Blob container must already exist and the identity needs blob data read/write permissions.
- The Event Hub consumer identity needs event receiver permissions.
- All instances of the same pipeline share the same consumer group and logical checkpoint store.
- **processDurably** is only a placeholder; replace with a real transaction/commit before production.
- Checkpointing **every event** is clear for labs but can incur high Blob write volume at scale.

### 22.2. Note on catching exceptions inside the callback

If you catch an exception, skip checkpointing the failed event, yet let the callback continue, the next event may get checkpointed and skip the failed one. In production, **halt partition progress, retry, or durably quarantine failed events** before allowing checkpoints to advance.

### 22.3. SDK version

Verify imports, methods, and dependencies against the exact Azure SDK version in your project. Illustrative snippets do not replace compiling and testing on your target version.

## 23. Designing Idempotent Consumers

Scenario:

~~~text
Event sequence 600
-> Consumer writes data successfully
-> Worker dies before checkpointing
-> New processor re-reads event sequence 600
~~~

If the consumer sends an email twice or issues two invoices, the system has a business bug.

### 23.1. Using eventId

Example event:

~~~json
{
  "eventId": "evt-600",
  "aggregateId": "ORD-1001",
  "aggregateVersion": 3,
  "eventType": "OrderPaid",
  "occurredAt": "2026-11-20T10:20:00Z"
}
~~~

In the database, enforce a unique constraint or **inbox table** on eventId / business operation key:

1. Check if the event was already processed.
2. If not, write business data and processed marker inside the same transaction.
3. Commit.
4. After commit, checkpoint.
5. If eventId already exists as completed, treat it as a valid replay and checkpoint when safe.

### 23.2. Side effects outside the transaction

Payment APIs, emails, or forwarding to another broker may not share a transaction with your database. Use **transactional outbox**, external API idempotency keys, or proper reconciliation.

### 23.3. Do not rely on Event Hubs for exactly-once

Event Hubs, consumer groups, and Blob checkpoint stores do not automatically provide end-to-end exactly-once for databases, email, or payments. Prove correctness via idempotent design.

## 24. Error Handling, Retries, and Quarantine

A schema-invalid event can cause a consumer to fail forever; unlike Service Bus, **Event Hubs has no built-in dead-letter subqueue** to shunt failed events automatically.

~~~mermaid
flowchart TD
    EV[Event] --> P{Validate and process}
    P -->|Success| DB[Commit result]
    DB --> CP[Checkpoint when safe]
    P -->|Transient error| RETRY[Bounded retry with backoff]
    RETRY --> P
    P -->|Permanent data error| Q[Quarantine to Storage/Service Bus]
    Q --> DONE{Persisted durably?}
    DONE -->|Yes| CP
    DONE -->|No| STOP[Halt partition, do not checkpoint]
~~~

### 24.1. Transient errors

Timeouts, HTTP 503, database failovers: bounded retries with exponential backoff and jitter, paired with circuit breakers to avoid retry storms.

### 24.2. Permanent errors

Unsupported schema or unrecoverable business rule violations: write the event and metadata to a controlled **quarantine store**, then checkpoint only if workflow policy accepts that the event has been classified and durably quarantined.

### 24.3. Unclassified errors

Never simply log and keep checkpointing later events. Pause/throttle the consumer appropriately, alert, and investigate the root cause.

### 24.4. Event ordering and errors

If an OrderPaid event fails and you checkpoint past OrderShipped, you lose the chance to process in order. Decide how to preserve per-aggregate ordering and handle quarantine/replay.

## 25. At-Least-Once, Duplicates, and Checkpoint Limits

Checkpointing after durable processing leads to a clear safety choice:

- **If DB commit succeeds but checkpoint fails:** event may be re-read, requiring idempotency.
- **If checkpoint succeeds but DB commit fails:** event risks being skipped, making recovery hard.

Hence standard pipelines prefer **at-least-once processing with an idempotent sink**.

### 25.1. Checkpointing is not a transaction with the database

An Azure Blob checkpoint write and a database transaction do not automatically form a distributed ACID transaction.

### 25.2. Increase safety with a processed-events table

Persist eventId and business result in the same database transaction. Upon re-reading, the consumer sees the event was already processed.

### 25.3. When strict ordering is required

If one bad event blocks all subsequent events for the same aggregate, decide explicitly: pause partition processing, quarantine with sequence-gap tracking, or use a state machine tolerant of out-of-order updates. There is no free “skip errors yet keep strict order” magic bullet.

## 26. Starting Position and Stale Checkpoints

A consumer can read from:

- Saved **valid checkpoint**.
- **Earliest event still within retention**.
- **Latest / new events** when skipping backlog.
- A **specific offset/sequence/time** per SDK and replay plan.

### 26.1. Earliest is not from when the Event Hub was created

Earliest only refers to the oldest event **still retained**. Events past retention cannot be re-read from Event Hubs even if a checkpoint still points to an older position.

### 26.2. Latest can skip backlog

If checkpoints are lost and the consumer starts at latest, existing unprocessed events are skipped. Pick starting positions according to RPO and business requirements.

### 26.3. Losing the checkpoint store

If the Blob checkpoint container is deleted, the processor loses prior progress. Never delete the store to “reset an error” without first verifying retention, archives, and a replay plan.

## 27. Retention and Event Hubs Capture

Event Hubs retains events per SKU/configuration **retention window**. Consumer pace does not extend how long events stay in the hub.

Example:

~~~text
Earliest retained ---------- Checkpoint -------- Latest retained
        |                         |                      |
   Replayable             Processed up to here       New events
~~~

When a consumer stops longer than retention, a gap of data becomes unavailable from the Event Hub.

### 27.1. Capture is not a checkpoint

**Event Hubs Capture** can export streams to Blob Storage or ADLS Gen2 where supported by SKU/features. That is a data archive, not per-consumer-group processing progress.

### 27.2. Building a replay plan

1. Identify partitions, time range, and offsets.
2. Verify whether data remains within retention.
3. If not, check whether an archive was configured beforehand.
4. Use a dedicated replay consumer group/process when isolating from production.
5. Ensure the target sink is idempotent.
6. Measure backlog, cost, and outcomes.
7. Never overwrite production checkpoints without approval.

## 28. Consumer Lag and Processing Progress

**Consumer lag** measures how far behind the latest data a consumer sits.

One sequence-based estimate per partition:

\[
\text{Lag}_{p} \approx
\text{LatestEnqueuedSequence}_{p}
-
\text{CheckpointSequence}_{p}
\]

Example:

| Partition | Latest seq | Checkpoint seq | Approx. lag |
|---|---:|---:|---:|
| P0 | 1200 | 1180 | 20 |
| P1 | 900 | 899 | 1 |
| P2 | 1400 | 980 | 420 |
| P3 | 560 | 558 | 2 |

P2 is lagging substantially compared to the other partitions.

### 28.1. Checkpoint lag differs from processing lag

If checkpointing every 100 events, a consumer may have processed 99 events since the last checkpoint without updating the store yet. Relying solely on checkpoints overestimates true unprocessed lag.

### 28.2. Time-based lag

A complementary metric is **event age**—the difference between broker enqueue time and successful processing time. It maps more naturally to SLOs than raw event counts.

### 28.3. Do not sum sequence numbers across partitions to infer order

Sequence numbers are meaningful only within a partition. Track **max per-partition lag**, consumer processing delay, and throughput individually instead of relying on a single overall average.

## 29. Consumer Group, Ownership, and Checkpoint Store Must Align

A clean production pipeline:

~~~text
Pipeline: orders-analytics-prod
Event Hub: order-events
Consumer group: analytics-prod
Blob container: analytics-prod-checkpoints

AKS Pod A -> EventProcessorClient
AKS Pod B -> EventProcessorClient
AKS Pod C -> EventProcessorClient

All pods share the same group and logical checkpoint store.
~~~

### 29.1. Why separate dev and prod?

If staging and production accidentally share a consumer group and store, staging can steal partition ownership or alter production checkpoints.

### 29.2. Can one Blob checkpoint store organize multiple pipelines?

The SDK namespaces metadata by namespace/hub/group. Even so, separating containers or permissions per pipeline/environment keeps operations cleaner. The critical rule is that **replicas of one pipeline must share the exact same store**, while independent pipelines never collide on progress or ownership.

### 29.3. Never keep business state solely in Pod memory

Partition ownership can move between Pods during rebalancing. Persist results and checkpoints in durable storage.

## 30. Azure Functions Event Hubs Trigger

With the **Azure Functions Event Hubs trigger**, the Functions runtime/extension coordinates event processing, checkpointing, and partition ownership per extension capabilities.

Logical example:

~~~text
Event Hub: telemetry, 8 partitions
Function App: processTelemetry

Instance 1: P0 P1
Instance 2: P2 P3
Instance 3: P4 P5
Instance 4: P6 P7
~~~

As instances scale in or out, ownership rebalances automatically.

### 30.1. Do you need to instantiate EventProcessorClient manually inside the handler?

Usually **no**. The Event Hubs trigger already coordinates receiving events. Manually creating another processor inside a Function handler creates redundant readers, ownership conflicts, and lifecycle bugs.

### 30.2. Host.json and extension versions

Batching, checkpoint frequency, concurrency, and scaling depend on Azure Functions runtime, Event Hubs extension version, and hosting plan. Never copy an old configuration and assume it always applies.

### 30.3. Handling function failures

Do not assume throwing an exception moves an event to a DLQ, as Event Hubs has no native DLQ like Service Bus. Verify extension retry/checkpoint behavior and implement application quarantine.

### 30.4. Scale-out remains bounded by partitions

Spinning up dozens of Function instances on four partitions does not magically create forty independent partition streams.

## 31. AKS Consumers and Autoscaling

For a Java EventProcessorClient running in AKS:

~~~mermaid
flowchart LR
    EH[(Event Hubs)] --> A[Consumer Pod A]
    EH --> B[Consumer Pod B]
    EH --> C[Consumer Pod C]
    A <--> CK[(Blob checkpoint store)]
    B <--> CK
    C <--> CK
    A --> DB[(Database)]
    B --> DB
    C --> DB
~~~

Each Pod needs:

- Event Hubs identity and receiver permissions.
- Blob checkpoint store data permissions.
- Consistent consumer group and logical store.
- Appropriate CPU/memory requests and limits.
- Startup probes and graceful shutdown hooks.
- Structured per-partition telemetry.
- Idempotent database writes.

### 31.1. What should HPA/KEDA watch?

Pod CPU alone does not reflect stream backlog. When using an AKS/KEDA Event Hubs scaler, configure the exact checkpoint store, consumer group, and identity, and understand how the scaler estimates lag.

### 31.2. Spot eviction

When running retryable workers on Spot nodes, expect Pods to be evicted abruptly. Checkpoints and idempotency enable recovery, though continuous low latency is not guaranteed.

### 31.3. Pod count exceeding partition count

HPA may scale Pod count up while excess Pods hold zero partitions. Set min/max bounds and autoscaling policies based on partition count and real downstream capacity.

## 32. Security: Event Hubs and Azure Blob Are Two Data Planes

A consumer reading Event Hubs and writing a Blob checkpoint store needs permissions across **two services**:

| Identity | Illustrative role | Responsibility |
|---|---|---|
| Producer identity | Azure Event Hubs Data Sender | Send events |
| Consumer identity | Azure Event Hubs Data Receiver | Read events |
| Consumer on Blob container | Storage Blob Data Contributor | Write checkpoints/ownership |
| Platform admin | Scoped Azure resource management permissions | Manage config; should not read all payloads by default |

### 32.1. Managed identity / Workload Identity

Azure Functions can use managed identity. On AKS, use **Microsoft Entra Workload ID** so Pods obtain tokens for Azure SDKs. Configure **DefaultAzureCredential** to resolve the intended identity.

### 32.2. Private networking

If both Event Hubs namespace and Storage account use private endpoints, consumers need DNS, routing, and outbound connectivity to **both** endpoints.

### 32.3. Never grant Owner to fix a 403

Distinguish Azure Resource Manager roles from **data-plane roles**. Azure Reader on a resource group does not grant permission to read events or write Blobs.

### 32.4. Never log secrets or PII

Partition keys, payloads, and checkpoint metadata can appear in logs. Avoid writing emails, tokens, card numbers, or raw bodies containing personal data unless protected.

## 33. Azure CLI: Creating an Event Hub for the Lab

**Use only on an authorized subscription/resource group with budget.** Verify commands against your Azure CLI version, SKU, and region.

~~~bash
az login
az account set --subscription "<subscription-id>"

az group create \
  --name rg-stream-lab \
  --location southeastasia

az eventhubs namespace create \
  --resource-group rg-stream-lab \
  --name ehns-stream-lab-unique \
  --location southeastasia \
  --sku Standard
~~~

Create Event Hub:

~~~bash
az eventhubs eventhub create \
  --resource-group rg-stream-lab \
  --namespace-name ehns-stream-lab-unique \
  --name order-events \
  --partition-count 4
~~~

Create consumer group:

~~~bash
az eventhubs eventhub consumer-group create \
  --resource-group rg-stream-lab \
  --namespace-name ehns-stream-lab-unique \
  --eventhub-name order-events \
  --name analytics-lab
~~~

Inspect metadata:

~~~bash
az eventhubs eventhub show \
  --resource-group rg-stream-lab \
  --namespace-name ehns-stream-lab-unique \
  --name order-events \
  --output json
~~~

**`ehns-stream-lab-unique`** is an illustrative name and may already be taken. Event Hubs CLI options or pricing features vary by version; never run lab commands against production resources.

### 33.1. Create the Blob checkpoint store separately

Provision an Azure Storage account and a Blob container, e.g., **analytics-lab-checkpoints**. Creating an Event Hub via Azure CLI **does not automatically create a checkpoint container** for Java EventProcessorClient. Assign Storage Blob Data Contributor accordingly.

### 33.2. Consumer groups do not imply checkpoints exist

Creating a consumer group only establishes an independent read view. The checkpoint/ownership store is a separate component when using EventProcessorClient.

## 34. Scenario: One Tenant Generates Most of the Load

Suppose an Event Hub has 8 partitions and 4 AKS consumers. Every minute 100,000 events arrive; 60% belong to a single tenant.

### Option A — Partition key is tenantId

Roughly 60% of events share one key and pile into one partition. One Pod owning that partition saturates while the other Pods sit underutilized.

### Option B — Partition key is orderId

If ordering is only needed per order, the large tenant's orders spread across multiple partitions. This improves load balance.

### When can you not change the key?

If business rules require all events for the tenant to be processed in strict global tenant sequence, switching to orderId breaks the requirement. Then you must pick a different ordering/aggregate strategy, optimize single-partition processing, or renegotiate SLOs.

### Conclusion

**Choose the key by the business unit requiring ordering first, and load spreading second.** No single key is optimal for every event type.

## 35. Throughput and Consumer Count Calculation

Suppose 6 partitions, where each partition processed sequentially completes 180 events/second in measured tests.

Theoretical throughput:

\[
6 \times 180 = 1,080\ \text{events/sec}
\]

Scaling from 3 to 6 processors helps distribute partitions evenly, yet if the per-partition ceiling is 180 events/second, scaling to 10 processors cannot exceed that ceiling.

Example of skewed distribution:

~~~text
P0: 180 events/s
P1: 180 events/s
P2: 180 events/s
P3:  60 events/s  <-- bottlenecked partition
P4: 180 events/s
P5: 180 events/s

Total = 960 events/s
~~~

If P3 receives 400 events/second, P3 accumulates lag even though aggregate capacity looks sufficient.

### 35.1. What lowers real capacity below theory?

- JSON parsing and schema validation.
- Database write latency and locks.
- Network round trips.
- Connection pooling and throttling.
- Checkpoint writes.
- Rebalancing and startup warm-up.
- Partition key skew and oversized events.

Run load tests with representative data instead of treating simple multiplication as an SLA.

## 36. Controlled Rebalance Experiment

1. Provision a 4-partition lab Event Hub.
2. Create a dedicated consumer group and dedicated Blob checkpoint store.
3. Start one EventProcessorClient instance.
4. Record which partitions it owns.
5. Start a second instance with **the same group and store**.
6. Observe partition ownership after rebalancing.
7. Continuously push events with fixed partition keys.
8. Stop one instance mid-processing.
9. Watch the remaining instance claim the orphaned partitions after ownership leases expire.
10. Verify the database contains zero duplicates even though some events were re-received.

### 36.1. Do not assume instant failover

Ownership detection and re-claiming take time depending on SDK, Blob store, and network conditions. Measure actual times rather than promising a fixed number.

### 36.2. Metrics to report

- Timestamp when worker stopped.
- Timestamp when partitions were re-claimed.
- Last checkpoint before and after failover.
- Duplicate events re-read.
- Final count of business records.
- Consumer lag spike during rebalance.

## 37. Common Issues and Investigation Paths

| Symptom | Possible causes | How to check |
|---|---|---|
| Adding Pods does not reduce lag | Too few partitions, hot partition, downstream bottleneck | Ownership, per-partition lag, DB latency |
| Events processed twice | Crash before checkpoint, replay, uncoordinated stores | EventId/inbox, checkpoint timeline |
| Consumer starts reading from beginning | Checkpoint not found, wrong group/store | Namespace/hub/group/container config |
| Consumer skips backlog | Starting position set to latest, checkpointed too early | Checkpoints, earliest/latest, retention |
| One partition has huge lag | Key skew, heavy payloads, slow handler | Partition-level metrics and key distribution |
| Checkpoint Blob returns 403 | Wrong RBAC scope/identity | Data-plane role and identity principal |
| Checkpoint Blob times out | Wrong Private DNS / route / firewall | Check endpoint and VNet config |
| Ownership flips constantly | Crash-looping Pods, network flapping, Blob errors | Processor errors and deployment events |
| Processing finishes yet checkpoint stalls | UpdateCheckpoint failing or batch checkpointing | SDK logs and store |
| Replay finds no data | Events aged past retention | Archive/Capture and RPO |
| Events out of order | Different keys, concurrent producers, app parallelism | PartitionId, business sequence, producer logs |

### 37.1. Prioritized investigation flow

1. Verify exact namespace, Event Hub, and consumer group.
2. Check partitions, ownership, and checkpoint store.
3. Compute per-partition lag.
4. Inspect producer key distribution.
5. Inspect consumer exceptions and downstream dependencies.
6. Compare checkpoint updates against durable commits.
7. Confirm retention still covers recovery needs.
8. Test fixes and rollbacks in staging first.

## 38. Monitoring with Azure Monitor and Application Telemetry

Key signals:

| Level | Metric/log to inspect | Purpose |
|---|---|---|
| Event Hubs namespace | Incoming/Outgoing messages, bytes, errors, throttling | Verify ingestion and egress |
| Partition | Last enqueued sequence/time, workload distribution | Spot hot partitions |
| Checkpoint store | Last checkpointed sequence/time, Blob errors | Spot stalled progress |
| Consumer | Processing duration, success/failure, retry count | Evaluate handler health |
| Ownership | Partitions per processor, claim/rebalance events | Understand load balancing |
| Database | Latency, timeouts, connection limits | Find downstream bottlenecks |
| End-to-end | Event age, processing latency, duplicate rate | Track SLO compliance |
| Cost | Event Hubs capacity, Blob operations, compute, logs | Control budget |

**Not every per-partition or ownership metric is available out of the box in default Azure Monitor.** You may need SDK instrumentation or custom metrics tagged by `partitionId`.

### 38.1. Suggested alerts

- Max per-partition lag breaches SLO.
- Checkpoints stall while ingress rises.
- Excessive rebalancing frequency.
- Persistent Blob checkpoint write errors.
- Event Hubs throttling.
- Database latency rising alongside consumer backlog.
- Consumer Pods scaling up while usable partition ownership stays flat.
- Retention window nearly exhausted before consumer catches up.

### 38.2. Never look only at average lag

One partition may lag by a million events while three sit at zero; averages hide the problem. Use **max lag** or per-partition charts.

## 39. Cost and Capacity Management

Cost components may include:

- Event Hubs namespace/tier, capacity/throughput, ingress/egress.
- Storage/retention and Capture capabilities per SKU.
- Azure Blob Storage checkpoint container and transaction counts.
- Azure Functions executions or AKS/VM compute.
- Networking: Private Link, firewalls, egress.
- Database and storage sinks.
- Azure Monitor / Log Analytics ingestion and retention.
- Operations and incident replay runs.

### 39.1. Per-event checkpointing has a price

Across 20 partitions handling thousands of events/second, checkpointing every event drives heavy Blob transactions. Pick a cadence balancing RTO and duplicate replay cost.

### 39.2. Multiple consumer groups consume read resources

Each pipeline reads and executes independently. Clean up unused test consumer groups per lifecycle policy.

### 39.3. More Pods is not always better

Once Pod count exceeds partition count—or most traffic hits one hot partition—adding compute rarely yields proportional throughput.

### 39.4. Retention and archival

Retention must match tolerable outage duration. For longer replay windows, use archive/Capture rather than assuming Event Hubs keeps events forever.

## 40. End-to-End Hands-On Lab

**Context:** the engineering team must process order events strictly in per-order sequence, scale across multiple consumers, and recover after a worker crash.

### Part A — Preparation

1. Confirm Azure account, lab subscription, and required permissions.
2. Create Event Hub **order-events** with four partitions.
3. Create consumer group **analytics-lab**.
4. Create a dedicated Azure Blob checkpoint container.
5. Grant receiver role to the consumer and Blob Data Contributor for checkpoints.
6. Set up Java SDK dependencies and a test environment.
7. Set cost limits and never point at a production database.

### Part B — Create and Send Events

1. Define eventId, orderId, aggregateVersion, and eventType.
2. Send OrderCreated → OrderPaid → OrderShipped for **ORD-1001** using the same partition key.
3. Send several other orders with different keys.
4. Observe partition ID, sequence number, and enqueue time.
5. Verify ORD-1001's events all landed in the same partition.
6. Do not conclude different keys always land in different partitions.

### Part C — Checkpointing

1. Start one EventProcessorClient.
2. Write test records keyed by eventId with a unique constraint.
3. Checkpoint only after transaction commit.
4. Compare processed sequence vs. checkpointed sequence.
5. Test checkpointing per event vs. every N events on synthetic data.
6. Measure how many events require reprocessing after a crash.

### Part D — Rebalance

1. Start a second processor sharing the same group and store.
2. Observe partition ownership.
3. Stop the first processor.
4. Watch the surviving processor claim the partitions.
5. Restart the first processor.
6. Record rebalance duration and lag status.

### Part E — Crash After DB Commit, Before Checkpoint

1. Send an event with a fixed eventId.
2. Let the consumer commit the DB write, then simulate a crash before checkpointing.
3. Restart the consumer.
4. Observe the event being re-read.
5. Verify the idempotent consumer does not create a second business record.
6. Document this as an at-least-once scenario.

### Part F — Hot Partition

1. Send many events with the same partition key **tenant-giant**.
2. Send events for smaller tenants/orders.
3. Compare per-partition lag and processing throughput.
4. Scale consumer instances to 4 and then 6.
5. Observe that the partition count remains 4.
6. Discuss why switching the key from tenantId to orderId is only valid if business rules allow it.

### Part G — Replay and Quarantine

1. Send a schema-invalid event.
2. Configure the consumer to safely quarantine it.
3. Checkpoint only after quarantine persistence commits.
4. Use a separate lab consumer group to test replay within retention.
5. Never delete or alter production checkpoints.
6. Verify zero duplicate side effects.

### Part H — Report and Cleanup

Record:

| Metric | Before | After / observed |
|---|---|---|
| Partition count | 4 | 4 |
| Processor count | 1 | 2, 4, 6 |
| Ownership per processor | Measured | Measured |
| Max partition lag | Measured | Measured |
| Last checkpoint | Measured | Measured |
| Duplicates after failover | Measured | Expect 0 business duplicates |
| Throughput | Measured | Measured |
| Blob checkpoint operations | Measured | Measured |
| Cost | Measured | Measured |

Stop processors and producers, then clean up only lab resources once authorized and confirmed dependency-free.

**Completion criteria:** you can explain partition routing, prove checkpoints occur after durable writes, observe rebalancing, and show idempotency prevents post-crash duplicates.

## 41. Production Readiness Checklist

- [ ] Identified the entity/aggregate requiring ordering.
- [ ] Partition key fits business rules and exposes no sensitive data.
- [ ] Analyzed hot keys and key skew.
- [ ] Partition count sized for throughput/SLO and growth.
- [ ] No reliance on global ordering across partitions.
- [ ] Producers include eventId, aggregateVersion, schemaVersion, and correlationId.
- [ ] No dependency on unguaranteed internal hashing formulas.
- [ ] Plan exists for partition count or topology changes.
- [ ] Each independent pipeline has its own consumer group.
- [ ] All replicas of a pipeline share the same checkpoint/ownership store.
- [ ] Blob checkpoint store has container, RBAC, and network configured properly.
- [ ] Checkpoints are written strictly after durable commits.
- [ ] Never checkpoint past unprocessed events.
- [ ] In-partition concurrency never breaks required ordering.
- [ ] Consumer is idempotent across crashes, rebalances, and replays.
- [ ] Transient errors use bounded retries/backoff, never infinite loops.
- [ ] Permanent errors write to a quarantine store rather than dropping silently.
- [ ] Team understands Event Hubs lacks a native Service Bus-style DLQ.
- [ ] Retention covers outage/recovery windows, with archival if needed.
- [ ] Alerts exist for per-partition lag, checkpoint age, and rebalance churn.
- [ ] Monitoring covers Blob permission/network failures.
- [ ] Metrics track downstream database latency and throughput.
- [ ] Autoscaling bounds respect partition count.
- [ ] Graceful shutdown implemented for Functions/AKS/VM workers.
- [ ] Replay runbook avoids touching live production progress.
- [ ] Budgets set for Event Hubs, Blob, compute, and telemetry.
- [ ] Tested crash after DB commit before checkpoint.
- [ ] Verified business outcomes rather than raw events read.

## 42. Self-Check Questions

1. How does an Event Hubs partition differ from a Service Bus queue?
2. How do Partition Key and Partition ID differ?
3. Are events with the same key guaranteed to land in the same partition under stable configuration?
4. Can two different keys land in the same partition?
5. Why is there no global ordering across partitions?
6. Does sharing a partition key automatically guarantee correct producer business order?
7. When should you pick `orderId` instead of `tenantId` as the partition key?
8. What is a hot partition and how do you detect it?
9. Why does adding 10 consumers to 4 partitions not increase parallelism proportionally?
10. What kind of independence do consumer groups provide?
11. Why must replicas of the same pipeline share a coordinated checkpoint/ownership store?
12. Can sequence numbers be compared across partitions?
13. How does an Event Hubs checkpoint differ from Service Bus Complete?
14. What risk arises when checkpointing before DB commit?
15. Why is idempotency required when DB commit precedes checkpointing?
16. Why should you not checkpoint event 102 if event 101 has not finished?
17. When does rebalancing happen, and why can it cause events to be re-read?
18. Does EventProcessorClient guarantee end-to-end exactly-once?
19. Does the Blob checkpoint store hold full event payloads?
20. When checkpoints are lost, what impact do `earliest` vs. `latest` starting positions have?
21. How does retention constrain replay capability?
22. Does Capture replace checkpointing?
23. At what scope should consumer lag be measured?
24. Why can checkpoint lag appear higher than actual processing lag?
25. Should an Azure Functions Event Hubs trigger manually instantiate EventProcessorClient inside the handler?
26. When scaling consumers with AKS/HPA/KEDA, what ceiling must be considered?
27. Which roles are needed to read Event Hubs and write Blob checkpoints?
28. When Blob checkpointing returns 403, what should you check?
29. Does Event Hubs have a built-in dead-letter subqueue like Service Bus?
30. Beyond Pods coming back online, what must a failover lab prove?

## 43. Summary

In Azure Event Hubs, **partition keys** govern event distribution and per-entity ordering scope; **checkpoints** record safe processing progress without deleting events from the log; and **consumer load balancing** distributes partition ownership across multiple processors in a consumer group.

Good designs recognize that **the same key can stay on one partition without guaranteeing global ordering**, **checkpointing after durable commits still allows reprocessing**, and **adding consumers cannot overcome partition limits or hot partitions**. Pairing EventProcessorClient with an Azure Blob checkpoint store coordinates ownership and post-restart recovery, yet never guarantees exactly-once semantics for external databases or APIs.

In production, combine **aggregate-scoped partition keys, eventId/aggregateVersion, contiguous progress checkpoints, idempotency, retry/quarantine workflows, per-partition lag monitoring, Microsoft Entra identity/RBAC, networking, retention/archival, and Cost Management**. The ultimate goal is not raw events read per second, but **accurate data processing, observable progress, reliable incident recovery, and controlled cost**.
