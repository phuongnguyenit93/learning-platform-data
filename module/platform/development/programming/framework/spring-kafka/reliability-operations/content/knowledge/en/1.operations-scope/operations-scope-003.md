# Producer, Broker, Consumer, and Listener Flow

## 1. Overall Picture

In Spring Kafka, a message flows through four primary layers of responsibility:

- **Producer** creates and sends records to Kafka. In a Spring application, business code typically sends via `KafkaTemplate`; `ProducerFactory` manages Kafka producer creation.
- **Broker** receives records, appends them to topic partitions, and replicates data to replicas according to cluster configuration.
- **Consumer** reads records from partitions by offset. Consumers sharing the same group ID coordinate to divide up the topic's partitions.
- **Listener** is the application code that processes consumed records. With `@KafkaListener`, Spring manages the consumer, poll loop, payload conversion, listener method invocation, and offset handling.

Basic flow:

1. The application creates an event and invokes the producer.
2. The producer serializes key/value, selects a partition, batches records, and sends a request to the broker acting as partition leader.
3. The broker writes the record to its log; replicas in the ISR receive copies via replication.
4. The broker responds to the producer according to the `acks` configuration.
5. A consumer belonging to a consumer group fetches records from its assigned partitions.
6. The Spring listener container dispatches the record to the listener method.
7. Upon successful processing, the container commits the offset per the configured acknowledgement mode. If processing fails, the error handler decides whether to retry or route the record to a recovery flow.

The diagram below illustrates the typical flow. Offset committing happens on the consumer side after listener processing, independent of the producer's send acknowledgement.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant KT as KafkaTemplate
    participant P as Producer
    participant B as Broker leader
    participant R as Replica
    participant C as Consumer group
    participant LC as Listener container
    participant L as @KafkaListener

    App->>KT: send(topic, key, event)
    KT->>P: serialize and select partition
    P->>B: Produce request
    B->>R: Replicate record
    R-->>B: Replica response
    B-->>P: Acknowledgment per acks
    P-->>KT: SendResult or error
    C->>B: Fetch from current offset
    B-->>C: Record and offset
    C->>LC: Deserialized record
    LC->>L: Invoke listener method
    L-->>LC: Success or exception
    LC->>B: Commit offset at commit point
~~~

One crucial point: the broker only knows that the record was written and replicated per Kafka's mechanism. The broker does not know whether the business logic inside the listener updated the database or finished its work. A consumer offset is a consumer group's read checkpoint, not a business processing state inferred by the broker.

## 2. Producer: From Application Event to Kafka Record

### 2.1. Spring Kafka Components

`KafkaTemplate<K, V>` is the messaging API commonly used in business code. It works with `ProducerFactory<K, V>` to obtain a configured Kafka producer. The Kafka producer performs serialization, partitioning, batching, and network communication with brokers.

Example of publishing an event:

~~~java
@Service
@RequiredArgsConstructor
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public void publish(OrderCreated event) {
        kafkaTemplate.send("orders", event.orderId(), event)
            .whenComplete((result, error) -> {
                if (error != null) {
                    log.error("Cannot publish order event {}", event.orderId(), error);
                    return;
                }

                var metadata = result.getRecordMetadata();
                log.info(
                    "Published order {} to partition {} at offset {}",
                    event.orderId(),
                    metadata.partition(),
                    metadata.offset()
                );
            });
    }
}
~~~

This example uses the Spring Kafka 3.x API, where the send result is a `CompletableFuture`. In older Spring Kafka versions, the future type may differ. Verify against your application's dependency version when applying sample code.

`send()` typically returns immediately with a future; actual sending happens asynchronously. The callback lets the application observe success or failure after the broker responds. If you ignore the future, send failures may go unrecorded at the business layer. Avoid blocking threads with `get()` on high-throughput send paths; if business logic requires synchronous confirmation, evaluate wait timeouts and throughput impact.

### 2.2. How Does the Producer Choose Where to Write?

A Kafka record has a topic, partition, key, value, timestamp, and headers.

- **Topic** identifies the logical data stream, such as `orders`.
- **Partition** is the unit of storage and parallel consumption. Each partition has its own log and monotonically increasing offsets.
- **Key** is typically used to select the partition. With the default partitioner, the same key normally routes to the same partition as long as the partition configuration does not change.
- **Value** holds the payload, such as a JSON event.
- **Headers** can carry a correlation ID, trace ID, schema metadata, or processing context.

If events for the same order must stay ordered, use the order ID as the key so they are written to the same partition. Kafka guarantees ordering only within a partition; there is no global ordering across partitions. When increasing partition count, key-to-partition mapping can change, so account for the impact on per-key ordering.

The producer serializes key and value using the configured serializers, then groups records into batches. Batches can be compressed before sending. `batch.size`, `linger.ms`, and `compression.type` are settings commonly used to balance latency, throughput, and network overhead.

### 2.3. Send Acknowledgements, Retries, and Durability

The `acks` setting determines the acknowledgement level the producer waits for from the broker:

| Value | Meaning | Trade-off |
|---|---|---|
| `acks=0` | Producer does not wait for broker acknowledgement | Lower latency, but hard to know whether the record was written |
| `acks=1` | Wait for the leader to write the record and respond | Records may be lost if the leader fails before replicas catch up |
| `acks=all` | Wait for replicas currently in the ISR to acknowledge per the Kafka protocol | Higher durability; may increase latency or reject writes when ISR is insufficient |

`acks=all` is usually combined with `min.insync.replicas`. For example, a topic with replication factor 3 and min ISR 2: the producer is acknowledged only when at least two replicas in the ISR satisfy the write requirement. If the ISR drops below the threshold, the broker may reject the write request rather than accepting a record with lower replication than policy requires.

The producer can retry on transient errors. Distinguish between two mechanisms:

- **Kafka producer retries** handle transient transport or broker errors within a producer session.
- **Application resends** of an event after a timeout, restart, or uncertainty over whether a previous send succeeded. This can be a new business send and may create a duplicate record.

Enabling an idempotent producer helps Kafka detect and eliminate duplicates arising from internal producer retries within the producer ID and sequence number mechanism. This mechanism does not automatically eliminate duplicate application resends after a restart, nor does it make consumer database operations exactly-once.

A producer configuration worth considering for flows requiring durability:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
~~~

Timeout values must match your SLA and system recovery times. `delivery.timeout.ms` caps the total time the producer waits for delivery completion, including retries; a timeout does not always prove the broker failed to write the record. When the send outcome is ambiguous, a stable event ID and idempotent consumer processing keep duplicates under control.

### 2.4. Producer Transactions

Kafka transactions allow writing a group of records atomically within Kafka. Consumers configured with the appropriate isolation level can avoid seeing records belonging to aborted transactions.

Transactions are especially useful in consume-process-produce flows: the application reads input records, produces output records, and commits input offsets within the same Kafka transaction. If the transaction aborts, output records are not treated as committed and input offsets do not advance as a successful processing run.

Kafka transactions do not include operations on databases, HTTP services, or external systems. If a listener updates a database and then sends a Kafka event, a coordinating design such as a transactional outbox or inbox/idempotency is needed; enabling Kafka transactions alone does not create a distributed transaction with a database.

## 3. Broker: Storing Logs and Distributing Records

### 3.1. Topics, Partitions, Offsets, and Replicas

A topic is divided into one or more partitions. Each partition is an append-only log: new records are appended to the end of the log and receive a specific offset within that partition.

Example:

| Partition | Offsets |
|---|---|
| `orders-0` | 0, 1, 2, 3, ... |
| `orders-1` | 0, 1, 2, 3, ... |
| `orders-2` | 0, 1, 2, 3, ... |

Offsets are meaningful only within their respective partition. Offset 12 in `orders-0` is not the same position as offset 12 in `orders-1`.

With a replication factor greater than 1, each partition has one leader and follower replicas. Producers write to the leader; followers replicate the log from the leader. Consumers also fetch from the leader under the standard Kafka protocol. When a leader fails, Kafka can elect an eligible replica from the ISR as the new leader.

**ISR (in-sync replicas)** is the set of replicas keeping up with the leader according to Kafka's criteria. The combination of replication factor, ISR, `acks`, and `min.insync.replicas` determines write fault tolerance. A high replication factor alone is insufficient if the producer uses weak acknowledgements or ISR settings are inappropriate.

### 3.2. Brokers Do Not Delete Records When Consumers Finish Processing

Kafka retains records according to retention policies, typically based on time or size. A consumer reading and committing offsets does not immediately delete records. Multiple consumer groups can read the same topic independently, each maintaining its own offsets.

This enables:

- One group handling payment processing.
- Another group building a read model.
- Another group serving analytics.

Each group tracks its own read progress. If one group falls behind, records remain in Kafka as long as retention has not expired or they have not been removed by the topic's storage policy.

### 3.3. Broker/Topic Settings to Review Together

- **Replication factor**: number of copies of each partition.
- **min.insync.replicas**: minimum number of replicas in the ISR required to accept writes with `acks=all`.
- **retention.ms / retention.bytes**: time or size limit for retaining log data.
- **cleanup.policy**: log cleanup policy, typically `delete` or `compact` depending on data type.
- **Partition count**: affects parallelism, load distribution, active consumer count, and per-key ordering.

Choosing partition count requires factoring in expected throughput, cluster size, consumer count, and ordering requirements. Creating too many partitions also increases metadata, file, memory, and replication overhead.

## 4. Consumer: Reading Partitions by Consumer Group

### 4.1. Consumer Groups and Partition Assignment

A consumer group is a set of consumers sharing a group ID. Kafka distributes the topic's partitions across consumers in that group. At any given time, a partition is assigned to at most one consumer within the same group, while different groups can read the same partition independently.

Example of a topic with 6 partitions:

- A group with 1 consumer: that consumer can receive all 6 partitions.
- A group with 3 consumers: partitions are distributed across the 3 consumers.
- A group with 8 consumers: at most 6 consumers have partitions to read; the remaining consumers may sit idle.

In Spring Kafka, the listener container's `concurrency` property can create multiple consumer threads. This is the number of consumers in the container, not automatic multi-threaded processing of a single record. How many consumers have useful work still depends on how many partitions are assigned to the group.

When consumers are added/removed or partitions change, Kafka performs a rebalance. Partitions may be revoked from an old consumer and assigned to another. Applications must handle graceful shutdown, avoid unbounded long-running work, and tolerate record redelivery during failures or rebalances.

### 4.2. Poll, Fetch, and Offsets

A Kafka consumer uses a `poll()` loop to retrieve records from the broker. The Spring listener container manages this loop; the `@KafkaListener` method is not where you call poll manually.

Each consumer group stores committed offsets per partition. The committed offset represents the next position the group will read. For example, successfully processing record offset 7 typically results in a committed offset of 8.

Two highly significant settings:

- `enable.auto.commit=false`: lets the Spring listener container coordinate commits per the acknowledgement mode. This is usually the right choice for listeners that must tie commits to processing outcomes.
- `auto.offset.reset`: determines the starting position when the group has no valid committed offset yet. `earliest` starts from the earliest retained record; `latest` starts from new records written after initialization. This setting does not automatically rewind a group that already has a valid offset to the beginning of the topic.

If auto commit is enabled, offsets may be committed on poll intervals without accurately reflecting whether the listener finished business processing. If the application crashes after an offset is committed but before processing completes, the record may be skipped on the next read. Therefore, listener containers are usually run with auto commit disabled to control commit timing.

### 4.3. Processing Time and Rebalances

The consumer must continue polling within configured limits. If processing a record or an entire batch takes longer than `max.poll.interval.ms`, the consumer may be treated as no longer active in time and its partitions rebalanced to another consumer. This can lead to duplicate processing when older records have not yet been committed.

Several mitigation approaches:

- Limit work per poll using `max.poll.records` so processing duration stays appropriate.
- Set timeouts on calls to databases or external services.
- Avoid running unbounded tasks directly on the listener thread.
- Tune `max.poll.interval.ms` based on actual processing time while monitoring rebalances and consumer lag.
- Use concurrency aligned with partition count and downstream capacity.

Do not merely increase timeouts to mask a stalled listener. Identify which work is holding the poll thread too long and its impact on commits, retries, and processing order.

## 5. Listener: Where Business Code Receives and Processes Records

### 5.1. Listener Container and @KafkaListener

`@KafkaListener` marks a message-receiving method. Spring creates a listener endpoint and listener container based on configuration; the container manages the consumer, polling, payload conversion, invoking the listener method, applying error handlers, and committing offsets.

Example:

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
        topics = "orders",
        groupId = "billing-service"
    )
    public void onOrderCreated(
        OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset
    ) {
        log.info(
            "Received order {} from partition {} at offset {}",
            event.orderId(),
            partition,
            offset
        );

        // Validate event and execute an idempotent business operation.
    }
}
~~~

Spring can convert the deserialized payload into the listener parameter type. Headers such as partition, offset, key, timestamp, and topic aid logging, diagnostics, and tracing. If the application needs access to full metadata or manual control over acknowledgement, use the corresponding listener parameters such as `ConsumerRecord` or `Acknowledgment`.

`groupId` on the annotation can specify the group for the endpoint. If omitted, the listener may use the group ID configured on the consumer factory. When an application has multiple listeners, clearly define which listeners share a group and which need separate groups.

### 5.2. When Is the Offset Committed?

Spring Kafka provides acknowledgement modes for listener containers. Exact names and configuration details should be checked against your Spring Kafka version, though common meanings are:

| Ack mode | Commit Timing |
|---|---|
| `RECORD` | After each individual record is successfully processed by the listener |
| `BATCH` | After finishing processing all records from a single poll |
| `TIME` / `COUNT` / `COUNT_TIME` | When configured time or count thresholds are met |
| `MANUAL` | Application calls acknowledge; container commits per the mode's mechanism |
| `MANUAL_IMMEDIATE` | Commits immediately when acknowledge is called under appropriate thread conditions |

`BATCH` is a common default mode for listener containers. `RECORD` is suitable when you want commit progress closely tied to each record and are using a record listener. For batch listeners, choose a mode aligned with how the listener processes the entire batch.

Example of manual acknowledgement:

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrderCreated(
    OrderCreated event,
    Acknowledgment acknowledgment
) {
    processOrder(event);
    acknowledgment.acknowledge();
}
~~~

Acknowledge only after the required work has completed. If you acknowledge before the business operation succeeds, the application may commit the offset and lose the chance to reprocess the record. With asynchronous processing, configure and use `Acknowledgment` strictly according to the container's threading contract; do not hold onto `Acknowledgment` and invoke it arbitrarily from background threads.

### 5.3. Exceptions and Error Handlers

If the listener method throws an exception, the container can route the error to an error handler. If the listener catches and swallows the exception, the container usually treats that invocation as successful and proceeds per the acknowledgement mode. Therefore, catch errors only when application code has an explicit way to handle them; if you want retries or DLT routing, let the error propagate to the corresponding mechanism.

In Spring Kafka, `DefaultErrorHandler` is commonly used to retry with backoff and recover after a defined number of attempts. `DeadLetterPublishingRecoverer` can publish failed records to a dead-letter topic (DLT). Configure the DLT producer/serializer to match the payload types, especially when failures occur during deserialization and the original payload remains only as a byte array.

A recovery strategy should define:

1. Which errors are likely transient, such as database timeouts or unavailable services.
2. Retry count and backoff between attempts.
3. Which errors cannot be resolved by retrying, such as schema-invalid payloads or data rule violations.
4. Which DLT receives records after recovery fails.
5. Who monitors, classifies, and replays records in the DLT.

Infinite retries can stall a partition and drive up consumer lag. Backoff must be bounded; DLTs need alerts, retention, and handling procedures. If the recoverer routes records to the DLT preserving the source partition, the DLT topic must have enough partitions to support that mapping.

### 5.4. Retry Topics and Processing Order

Spring Kafka also supports the non-blocking retry topic model, such as via `@RetryableTopic`. Failed records are moved to retry topics with appropriate delays and then reprocessed. This lets the main partition continue processing other records in certain scenarios.

In return, retry topics can alter observed ordering: later records may be processed before an earlier record waiting in retry. If business logic strictly requires per-key ordering, carefully evaluate retry strategies and partition design before adopting a non-blocking model.

### 5.5. Deserialization Errors

Deserialization happens before the listener receives the payload. If JSON is malformed or schema-incompatible, the listener method may never be invoked. `ErrorHandlingDeserializer` wraps the delegate deserializer to feed deserialization errors into Spring Kafka's error-handling pipeline so the container/error handler can recover or route the record to a DLT.

With JSON, align the serializer, deserializer, and type-resolution strategy. `JsonDeserializer` can use type headers written by the serializer; if type headers are not used, configure an explicit default type or type mapping. Trust only the packages actually needed rather than opening trusted packages overly broadly.

## 6. Delivery Semantics and Handling Duplicates

### 6.1. At-Most-Once, At-Least-Once, and Exactly-Once

| Semantics | High-Level Behavior | Consequence |
|---|---|---|
| At-most-once | Commit offsets beforehand or decouple from business processing | Records may be lost if the application fails after commit |
| At-least-once | Process first, commit offset after success | Potential reprocessing if an error occurs after the side effect but before commit |
| Exactly-once in Kafka | Kafka transaction coordinates output records and input offsets in the same transaction | Prevents partial output/offset commits in Kafka-to-Kafka flows |

At-least-once is typically the practical choice for business-processing listeners. For example: a listener updates the database successfully, but the application crashes before committing the Kafka offset. After a rebalance or restart, the record is redelivered and the database operation may execute again.

Therefore, listeners should be idempotent. Common techniques include:

- Each event has a stable event ID; the database stores processed IDs with a unique constraint.
- Use upserts or conditional state transitions so the same event cannot apply a side effect a second time.
- Use an inbox table to record accepted events in the same transaction as business updates.
- Use a transactional outbox when updating a database and publishing subsequent events without leaving a gap between the two operations.

Producer idempotence handles duplicates from retries at the Kafka producer layer. Consumer idempotency handles the same event being redelivered or republished from the application layer. These are two distinct layers of protection.

### 6.2. Exactly-Once When Consuming and Producing in Kafka

In Kafka-to-Kafka flows, Spring Kafka can coordinate a transaction-capable producer factory, listener container, and Kafka transaction manager to send output records and commit input offsets within the same transaction. Downstream consumers typically use the `read_committed` isolation level to read only records from committed transactions.

This mechanism fits examples like reading `orders` and writing `billing-events`. It does not cover database updates or REST API calls. If a listener both writes to a database and publishes to Kafka, design an outbox/inbox or idempotent coordination mechanism to handle failures between the two systems.

## 7. Illustrative Baseline Configuration

The following YAML example illustrates a producer sending JSON and a consumer group receiving JSON via a listener container. Real-world configurations also depend on Spring Boot version, Spring Kafka version, schemas, and cluster security policies.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000

    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.events

    listener:
      ack-mode: record
~~~

Notes when applying:

- `bootstrap-servers` specifies bootstrap addresses for clients to discover brokers in the cluster; this need not be the full broker list.
- `acks: all` and `enable.idempotence: true` improve send reliability; broker/topic settings still require appropriate replication and min ISR.
- `enable-auto-commit: false` lets the container tie commits to processing outcomes.
- `auto-offset-reset: earliest` takes effect only when the group has no valid offset yet.
- `ErrorHandlingDeserializer` uses `JsonDeserializer` as its delegate so deserialization errors pass through the error-handling pipeline.
- `spring.json.trusted.packages` should be restricted to packages containing permitted event classes. If the producer omits type headers or services use different classes, configure explicit default types or type mappings.
- `ack-mode: record` commits per record after the listener succeeds; if the listener consumes batches, choose the corresponding acknowledgement mode.

Settings such as replication factor and min ISR belong to broker or topic configuration and cannot be substituted by application-side producer configuration. An example topic policy is replication factor 3 and min ISR 2, provided the cluster has sufficient brokers and appropriate topology.

## 8. Observing and Diagnosing the Flow

To pinpoint whether an issue lies in the producer, broker, consumer, or listener, monitor metrics at every stage.

| Area | Metrics or Info to Track | Signals Requiring Investigation |
|---|---|---|
| Producer | Send success/errors, retries, request latency, timeouts, buffer exhaustion | Rising timeouts, continuous retries, or send failures |
| Broker | Offline partitions, under-replicated partitions, ISR shrinks, disk and network | Replicas falling behind, frequent leader changes, low disk space |
| Consumer group | Consumer lag per partition, rebalance count, fetch rate | Sustained lag growth or partitions repeatedly changing owners |
| Listener | Processing duration, exception rate, retry count, DLT rate | A record type causing repeated errors or listener taking too long |
| Business | Event ID, correlation ID, idempotency outcomes, outbox/inbox status | Duplicate events, missing events, or inconsistent side effects |

Consumer lag is the distance between the latest record offset and the group's committed offset; inspect it per partition to spot bottlenecked partitions. Rising lag alone does not pinpoint the cause: the producer might have increased load, the consumer might have slowed down, or the listener might be retrying a failing record.

Logs should include topic, partition, offset, key or event ID, and correlation ID to connect processing steps. Avoid logging full payloads if they contain sensitive data. For the DLT, track newly added record counts, exception types, source topic/partition/offset, and replay outcomes.

## 9. Common Operational Scenarios

| Scenario | How the Flow Reacts | What to Check |
|---|---|---|
| Producer timeout | Send result may be uncertain: the broker may have written the record while the response was lost | Check broker/network and retries; use a stable event ID with consumer idempotency |
| Partition leader failure | Kafka elects a new leader from eligible replicas in the ISR | Check replication factor, ISR, under-replicated partitions, and `acks` config |
| Listener throws transient exception | Error handler retries with backoff; may route to DLT after exhausting attempts | Check downstream health, timeouts, retry counts, and DLT |
| Payload fails deserialization | Listener may not be called; error flows through ErrorHandlingDeserializer/error handler | Check serializer, schema, type headers, trusted packages, and raw payload |
| Consumer processes too slowly | May exceed max poll interval and trigger a rebalance | Measure processing duration, reduce work per poll, or offload long tasks |
| Event processed twice | Can occur when side effect succeeded but offset was not yet committed | Use event ID, unique constraint, inbox, or idempotent operations |
| Consumer lag increases | Publish rate exceeds processing rate or specific partitions are bottlenecked | Compare producer rate, consumer throughput, per-partition lag, retries, and listener duration |

When investigating a specific record, trace the same event ID across producer logs, send-success metadata, topic/partition/offset, consumer group, and listener logs. This trace distinguishes between a record never published, a record sitting on the broker unread by the group, a record undergoing retries, and a record processed without an offset commit.

## 10. Principles for Designing a Reliable Flow

- Choose keys based on the entity requiring ordering, while sizing partition count for realistic parallelism.
- Use `acks=all`, idempotent producer, and replication/min ISR matching data criticality.
- Disable auto commit when offsets must be tied to listener outcomes; choose record or batch acknowledgement mode intentionally.
- Design listeners to be idempotent since redelivery is normal under at-least-once semantics.
- Classify retryable vs. non-retryable errors; configure bounded backoff, a monitored DLT, and a replay process.
- Keep processing times within poll limits, enforce downstream timeouts, and monitor rebalances.
- Use Kafka transactions for Kafka-to-Kafka flows requiring atomicity; use outbox/inbox or idempotency across database and external system boundaries.
- Track producer errors, replication status, consumer lag, listener duration, and DLT rates as a connected chain of signals.

When these components are configured consistently, the producer knows delivery outcomes, brokers maintain replicas per policy, consumers track progress per partition, and listeners recover cleanly from processing errors. End-to-end flow reliability depends on how the layers coordinate, especially the relationship between business processing and offset commits.
