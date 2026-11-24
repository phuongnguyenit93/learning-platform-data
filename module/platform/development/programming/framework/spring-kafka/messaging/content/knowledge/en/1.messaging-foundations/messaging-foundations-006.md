# Data Flow from Producer to Consumer

In an application using Kafka, the producer creates and sends an event, Kafka stores the event in a topic partition, and the consumer reads the event from that partition to perform downstream work. Spring Kafka provides components such as `KafkaTemplate` and `@KafkaListener` to connect Spring applications to this data flow.

To operate reliable messaging, you need to understand a record's complete journey: where data is created, how it is converted to bytes, how Kafka selects a partition, when the broker acknowledges the write, how consumer groups distribute partitions among consumers, and how offsets are persisted after processing. These steps are interconnected yet carry distinct meanings. A successful send by the producer does not mean the consumer has finished processing; reading a record by the consumer does not mean its offset has been committed.

After this lesson, the reader will be able to:

- Describe the path of an event from the producer application to the listener in the consumer application.
- Distinguish topic, partition, record, key, offset, and consumer group in the processing flow.
- Explain the roles of the serializer, partitioner, broker, deserializer, `KafkaTemplate`, and `@KafkaListener`.
- Read metadata from a send operation and determine a record's location in Kafka.
- Explain why a consumer may receive a record again and why ordering is guaranteed only within a single partition.

## 1. Big Picture of the Data Flow

A basic Kafka flow can be viewed in the following stages:

1. The producer application creates an event representing something that has happened in the business domain.
2. The producer sends the event using the Kafka client. In a Spring application, this is typically done via `KafkaTemplate`.
3. The producer serializer converts key and value into bytes. The partitioner selects the target partition based on an explicitly specified partition, the key, or the default partitioning strategy.
4. The Kafka broker receives the record and appends it to the partition's log. The broker returns the send result according to the producer's acknowledgement configuration.
5. A consumer belonging to a consumer group is assigned partitions and uses `poll()` to fetch new records.
6. The consumer deserializer converts bytes into an object the application can use. Spring Kafka passes the record to the method annotated with `@KafkaListener`.
7. The listener processes the event. After processing according to the configured acknowledgement policy, the consumer commits the offset to record the position from which reading can resume.

```mermaid
flowchart LR
    A[Producer application] --> B[KafkaTemplate.send]
    B --> C[ProducerRecord]
    C --> D[Serializer and partitioner]
    D --> E[Broker: append to topic partition]
    E --> F[Producer receives send result]
    E --> G[Consumer group]
    G --> H[Consumer poll]
    H --> I[Deserializer and message conversion]
    I --> J[@KafkaListener]
    J --> K[Business processing]
    K --> L[Commit offset]
    L -. store position per group .-> G
```

The producer's send result and the consumer's processing are two separate branches after the record is accepted by the broker. The producer can receive an acknowledgement while the consumer is not yet running, is still processing an earlier record, or has not even started. This is a key characteristic of the log-based storage and reading model: producers and consumers do not need to be online at the same time.

## 2. Record, Topic, Partition, Key, and Offset

Kafka transmits and stores records. A record typically consists of the following components:

| Component | Meaning |
| --- | --- |
| Topic | Logical data stream name to which records are sent, e.g. `order-events`. |
| Partition | Physical log segment of a topic. Each partition has its own record order. |
| Key | Value used to route records to partitions and commonly used to keep events for the same entity in the same partition. |
| Value | Event payload, such as `OrderCreated` data. |
| Timestamp | Timestamp attached to the record; exact meaning depends on producer and broker timestamp settings. |
| Headers | Additional key/value pairs carrying metadata such as correlation ID or event type. |
| Offset | Ascending position of a record within a partition. An offset is not a topic-wide or cluster-wide sequence number. |

For example, topic `order-events` has three partitions. A record may reside at `order-events-1`, offset `42`. The complete way to identify a record's location is topic, partition, and offset. Saying only offset `42` is insufficient because another partition can also have a record at offset `42`.

```text
Topic: order-events

Partition 0:  [offset 0] [offset 1] [offset 2] [offset 3] ...
Partition 1:  [offset 0] [offset 1] ... [offset 42] ...
Partition 2:  [offset 0] [offset 1] [offset 2] ...
```

A topic can have multiple partitions to increase parallel processing capacity and distribute load. Each partition is an append-only ordered log. Kafka does not merge all records from all partitions into a single global order.

Reading a record by a consumer does not remove the record from the topic. Records remain stored according to the topic or cluster retention policy, such as by time or size. A consumer group's offset only indicates how far the group has confirmed reading progress; it is not a delete command.

## 3. Producer Stage: Creating and Sending Events

### 3.1. From Business Event to Kafka Record

A producer should send an event describing what happened, rather than sending a command asking a consumer to perform something. For example, after an order is successfully created, the order service emits `OrderCreated`. The payment, inventory, or notification service can subscribe to this event according to its needs.

A simple event can be represented as a Java record:

```java
public record OrderCreated(
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}
```

`orderId` is the business identifier of the order. `total` and `occurredAt` describe data at the moment the event occurred. In real systems, the event contract should be stable and have a compatibility strategy when adding, changing, or removing fields. Producers and consumers may be deployed and released at different times, so you should never assume both sides always upgrade simultaneously.

When sending, the producer creates a record containing topic, key, value, and optionally timestamp, headers, or a specific partition. With Spring Kafka, `KafkaTemplate` performs this operation without requiring manual lifecycle management of a Kafka producer on every call.

```java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "order-events",
            event.orderId(),
            event
        );
    }
}
```

In this example:

- `String` is the key type before serialization.
- `OrderCreated` is the value type before serialization.
- `event.orderId()` is used as the key so events for the same order normally go to the same partition.
- `send()` executes an asynchronous send and returns a `CompletableFuture` in Spring Kafka 3.x.

In older versions of Spring Kafka, the returned future type may differ. When applying to a project, verify the API signature against the dependency version in use.

### 3.2. Asynchronous Sending and Send Results

Calling `KafkaTemplate.send()` must not be interpreted as the application waiting for the consumer to process the event. The producer sends data over the network to the broker and completes the future when a result arrives according to the producer's acknowledgement configuration. The application can attach a callback to log, update metrics, or handle send failures:

```java
public void publishAndObserve(OrderCreated event) {
    kafkaTemplate.send("order-events", event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Failed to send OrderCreated: {}", event.orderId(), exception);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                "Sent orderId={} topic={} partition={} offset={}",
                event.orderId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
```

`SendResult` contains information about the sent record, and `RecordMetadata` describes the position where the broker recorded it, including topic, partition, offset, and timestamp. This metadata is very useful when troubleshooting failures or tracing a specific event.

Because sending is asynchronous, failures may surface after the business method has already returned. If the application needs to report to the caller that the event was acknowledged by the broker, it must explicitly decide whether to wait on the future and how to handle timeouts, send failures, and retries. Never ignore the future and assume every send succeeded.

### 3.3. Serializers Convert Objects into Bytes

Kafka brokers store bytes, not Java objects directly. The producer serializer converts the key and value into bytes before sending. For example:

- `StringSerializer` converts strings into bytes.
- `IntegerSerializer` converts integers into bytes using the serializer's format.
- Spring Kafka's `JsonSerializer` converts objects into JSON bytes and can add type information in headers per configuration.
- Avro, Protobuf, or custom serializers can be used when the system manages schemas in a different format.

Producer and consumer must agree on the data format. If the producer writes JSON but the consumer tries to decode an incompatible format, errors will occur during deserialization or message conversion even though the record is already in Kafka.

Example serializer configuration in Spring Boot:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

`bootstrap-servers` supplies broker addresses for the client to initiate connections and fetch cluster metadata. A producer can connect to one or more bootstrap addresses; after obtaining metadata, the Kafka client communicates with the broker owning the target partition.

### 3.4. The Partitioner Selects the Target Partition

Once a record is constructed, the producer must determine the target partition. There are three common cases:

1. The application specifies an explicit partition in `ProducerRecord`; the producer uses that partition if valid.
2. The application provides a key; the partitioner uses the serialized key to select a partition according to its partitioning algorithm.
3. The record has no key and no explicit partition; the default partitioner distributes the record using the Kafka client's strategy, which may optimize batching and load balancing.

Using a key makes sense when events related to the same entity must stay in the same partition. For example, using `orderId` as the key allows status changes for one order to be read sequentially in the same partition, provided the partitioner configuration and partition count do not change the mapping.

Do not treat keys as a system-wide ordering mechanism. Two orders with different keys may go to two different partitions and be processed concurrently by consumers. If you increase the partition count, key-to-partition mapping may change; therefore, evaluate the impact on per-key ordering before modifying topic topology.

## 4. Broker Stage: Appending the Record to a Partition

The producer sends the record to the broker acting as the leader of the target partition. The broker appends the record to the partition's log and assigns the next offset. When a partition has replication, follower brokers replicate data from the leader according to Kafka's replication protocol.

Kafka uses an append-only log model: new records are added to the end of the log. Reading is typically offset-based, so consumers can resume from a saved position without producers and consumers being online at the same time.

### 4.1. What Level of Acknowledgement Does the Producer Receive?

The producer's acknowledgement level is controlled primarily by the `acks` setting:

| Configuration | General Meaning | Trade-off |
| --- | --- | --- |
| `acks=0` | Producer does not wait for broker acknowledgement that the record was written. | Lower latency, but the producer cannot easily detect lost sends. |
| `acks=1` | Leader acknowledges after appending the record to its local log. | Records may be lost if the leader fails before followers replicate the data. |
| `acks=all` | Leader waits for replicas currently in the ISR to acknowledge according to the replication protocol. | Better durability, but may increase latency and depends on ISR health. |

`acks=all` is often considered for critical data. However, it must be paired with proper replication settings, especially `min.insync.replicas`. If the ISR has fewer replicas than required, the broker can reject writes instead of silently lowering durability guarantees.

When the `KafkaTemplate.send()` future completes successfully, that reflects the producer's chosen acknowledgement level. It does not prove the consumer has read or processed the record. Consumer processing happens independently and is tracked via consumer group offset progress.

### 4.2. Retention and Record Lifecycle

A record is not deleted right after a consumer finishes reading it. Kafka keeps records according to the topic's retention policy, such as retaining for a period of time or up to a storage limit. Therefore:

- Multiple consumer groups can read the same topic independently.
- A consumer group can replay historical data if its offsets are reset and records are still within retention.
- A consumer stopped for a long period may miss records that were deleted due to retention before it comes back.

This is a major difference between Kafka and a queue where receiving a message is tied to removing the message from the queue. In Kafka, reading progress belongs to each group, while record lifecycle belongs to the topic's retention policy.

## 5. Consumer Stage: Reading Data with Consumer Groups

### 5.1. Consumer Groups Distribute Partitions

Consumers typically join a named consumer group. Kafka manages assigning a topic's partitions to active consumers in that group. At any point in time, a partition is assigned to at most one active consumer in the same group, though a single consumer can be assigned multiple partitions.

Suppose a topic has three partitions and group `billing-service` has two consumers:

```text
Topic order-events
  Partition 0 ───────────────┐
  Partition 1 ───────────────┼──> group billing-service
  Partition 2 ───────────────┘

One possible assignment:
  Consumer A: Partition 0, Partition 1
  Consumer B: Partition 2
```

This is only an illustrative assignment; the actual assignment depends on the assignor and group state. If a group has more consumers than assigned partitions, some consumers will have no partitions to read. Therefore, increasing `concurrency` does not automatically increase throughput if there are not enough partitions.

Consumer groups enable parallel scaling. If there are two different groups, such as `billing-service` and `notification-service`, each group maintains its own offset progress and can read the same topic. This lets multiple services receive the same event without producing duplicate copies of records to separate per-service topics.

### 5.2. Polling for Records

A Kafka consumer uses a `poll()` loop to fetch data from assigned partitions. With Spring Kafka, the listener container manages this loop and invokes the application's listener method. Application developers typically do not need to write a manual `KafkaConsumer.poll()` loop when using `@KafkaListener`.

General processing flow:

1. The consumer joins the group and receives partition assignments.
2. The consumer fetches records from the broker starting at the group's next offset to read.
3. The Kafka client returns a batch of records to the listener container.
4. The container dispatches each record or batch to the listener depending on listener type and configuration.
5. The listener processes the record; the container manages acknowledgement and commits according to the configured `AckMode` and error handler.

A consumer can fetch multiple records in a single poll. Settings such as `max.poll.records`, `fetch.min.bytes`, `fetch.max.wait.ms`, and `max.poll.interval.ms` affect batch size, fetch wait times, and processing cadence. If the application takes too long between polls, the consumer may exceed `max.poll.interval.ms`, causing the group to consider the consumer stalled and trigger a rebalance.

### 5.3. Deserializer and Message Conversion

The consumer receives bytes from the broker. The deserializer converts bytes into a data type the application can process. For JSON, Spring Kafka provides `JsonDeserializer`; for strings, there is `StringDeserializer`.

```yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.orders.events
        spring.json.value.default.type: com.example.orders.events.OrderCreated
```

The values in `spring.json.trusted.packages` and `spring.json.value.default.type` must match the actual package and event type in the application. Do not open trusted packages wider than necessary. If producer and consumer use type headers to identify payload types, align how those headers are produced and read; if type headers are not used, the consumer must configure a default type or corresponding type mapping.

Serializers/deserializers only solve converting between bytes and data types. They do not guarantee that an event has all business fields, valid state, or semantic compatibility. Those checks belong to application validation and business logic.

## 6. Spring Kafka Connects Consumers with `@KafkaListener`

`@KafkaListener` marks a message-receiving method. Spring Kafka creates a listener container to manage the consumer, poll data, invoke the annotated method, and coordinate offset commits and error handlers.

Example listener receiving the `OrderCreated` event:

```java
@Component
public class OrderEventListener {

    @KafkaListener(
        topics = "order-events",
        groupId = "billing-service"
    )
    public void onOrderCreated(
            OrderCreated event,
            @Header(KafkaHeaders.RECEIVED_KEY) String key,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
            @Header(KafkaHeaders.OFFSET) long offset) {

        log.info(
            "Received OrderCreated orderId={} key={} partition={} offset={}",
            event.orderId(), key, partition, offset
        );

        billingService.startBilling(event);
    }
}
```

Injected headers help observe the origin of the record. In real processing, log at least the topic, partition, offset, and an appropriate correlation ID so producer logs can be linked with consumer logs. Avoid logging full payloads if payloads contain sensitive data or are overly large.

A listener can receive the converted payload, `ConsumerRecord<K,V>` if full metadata access is needed, or a batch if configured as a batch listener. Choose the parameter style based on business requirements and error-handling policy. When a listener receives a batch, success/failure decisions can affect the entire batch depending on container configuration.

### 6.1. Listener Concurrency

Spring Kafka lets you configure concurrency so a listener container runs multiple consumer threads. For example, a listener container with concurrency set to three can create three consumers belonging to the same group. Kafka then distributes the subscribed partitions among these consumers.

Concurrency is useful when processing can run in parallel and the topic has enough partitions. However, concurrency does not create additional partitions and does not allow multiple consumers in the same group to process a single partition simultaneously. If a topic has only one partition, setting concurrency to five for a group still will not create five parallel reading streams for that partition.

When a listener processes asynchronously inside the application, pay attention to completion order and offset commits. If records are processed asynchronously yet offsets are committed ahead of unfinished records, processing can be lost if the process crashes. Concurrency design must be paired with a matching acknowledgement strategy.

## 7. Offsets and When Processing Is Confirmed

An offset is a record's position within a partition. A consumer group stores committed offsets separately per partition. The committed offset represents the next position the group will read upon resuming, so if the record at offset `42` has been processed and progress is committed past it, the normal resume position is `43`.

An offset is not business state. Kafka knows how far the group has committed, but it does not know whether the application sent an email, deducted money, updated a database, or completed a workflow. Applications must design processing and commit order to suit side effects outside Kafka.

### 7.1. Auto Commit and Container-Managed Commit

The Kafka client has an auto-commit offset mechanism. However, when using a Spring Kafka listener container, it is usually recommended to let the container manage commits and disable Kafka consumer auto-commit so commits are tied to listener processing outcomes. Actual configuration must be verified because behavior depends on version and application settings.

Spring Kafka provides common acknowledgement modes (`AckMode`):

| Mode | General Commit Timing |
| --- | --- |
| `RECORD` | After the listener successfully processes each individual record. |
| `BATCH` | After successfully processing all records in a poll batch. This is the common default mode of listener containers. |
| `TIME` | When a configured commit time interval elapses. |
| `COUNT` | When a configured number of records has been processed. |
| `MANUAL` | Application calls acknowledge; the container performs the commit according to this mode's rules. |
| `MANUAL_IMMEDIATE` | Requests an immediate commit when the application acknowledges, subject to execution thread and container settings. |

The mode name only describes commit timing; to understand full behavior when a listener throws an error, check the error handler, retries, transactions, and container setup. Never look solely at `AckMode` and conclude the entire application has exactly-once or at-least-once semantics.

### 7.2. Why Can a Consumer Receive a Record Again?

Suppose a consumer reads record offset `42`, finishes the business task, and then crashes before committing the offset. When the consumer restarts, the group may resume from the older offset and read record `42` again. This is the classic duplicate scenario of at-least-once processing.

Conversely, if the application commits the offset before the business task completes, the process may crash after committing but before persisting business data. Upon restart, the group has moved past that record, so the task may be skipped. Therefore, for typical processing, committing after the listener succeeds is the safer choice.

Because duplicates can occur, business handlers should be idempotent where appropriate. For example, when handling `OrderCreated`, the system can use `eventId` or `orderId` together with business state to detect that an event was already applied. Distinguish business idempotency from Kafka offset commits: the two mechanisms solve different problems.

### 7.3. `auto-offset-reset` Is Not a Restart-Rewind Setting

`auto-offset-reset` specifies the starting position when a group has no valid committed offset for a partition, such as a brand-new group or when the old offset is no longer in the log. Two common values:

- `earliest`: start from the earliest record still retained in the partition.
- `latest`: start from the latest record at the time the consumer determines its starting position.

If a group already has a valid offset, the consumer resumes from its committed offset; `auto-offset-reset` does not automatically rewind the group to the start of the topic on every restart. To replay data, perform an intentional offset reset and understand its impact on running groups.

## 8. Ordering, Parallelism, and Delivery Semantics

### 8.1. Ordering Is Guaranteed Within a Partition

Kafka preserves append order within a single partition. A consumer reads a partition in offset order. If events for the same order are sent with the same key and consistently routed to the same partition, the consumer can process that order's sequence of events in that partition's order.

Kafka does not provide global ordering across multiple partitions. For example, `OrderCreated` in partition 0 may be processed after `OrderCancelled` in partition 2 even if the producer sent the first event earlier. If business logic depends on ordering, choose keys and partitioning by business entity and avoid asynchronous handoffs that scramble completion order.

### 8.2. At-Most-Once, At-Least-Once, and Exactly-Once

Delivery semantics describe the relationship between reading a record, processing it, and confirming progress:

| Semantics | Behavior | Primary Risk |
| --- | --- | --- |
| At-most-once | Commit before processing or without waiting for processing to finish. | Processing can be lost if the process crashes after committing. |
| At-least-once | Process first, commit after processing succeeds. | Duplicate processing can occur if crashing before committing. |
| Exactly-once | Combine suitable mechanisms so observable results are not duplicated within the guaranteed scope. | Requires explicit configuration and transaction boundaries; does not appear automatically just by using Kafka. |

In typical consumer flows, at-least-once is usually the practical starting point because it prioritizes not skipping records that have not been successfully processed. In exchange, the application must handle duplicates. Exactly-once in Kafka can coordinate Kafka reads, Kafka writes, and offset commits inside a Kafka transaction when properly configured; that does not automatically make database writes or external HTTP calls part of the Kafka transaction.

If a consumer updates a database and then commits a Kafka offset, the two operations belong to two separate systems and face a gap if the process crashes between them. For strict consistency requirements, evaluate designs such as idempotency keys, transactional outbox/inbox, or coordination mechanisms suited to the system. These are separate reliability designs and should not be assumed simply because a listener returns normally.

## 9. When a Stage in the Flow Fails

Failures can occur at many points, and each type requires a different investigation path:

| Stage | Failure Examples | Signals to Inspect |
| --- | --- | --- |
| Event creation | Missing fields, bad data, or event does not reflect committed state. | Business logs, validation, and event emission timing. |
| Producer send | Unreachable broker, timeout, authorization error, or missing topic per cluster config. | Future exceptions, bootstrap servers, ACLs, metadata, and topic settings. |
| Serialize | Unsupported data type or incompatible serializer. | Serializer stack trace, key/value types, and serializer configuration. |
| Broker append | Insufficient ISR, quota exceeded, or broker error. | Producer exceptions, broker logs, replication state, and `acks`. |
| Consumer poll | Consumer not assigned partitions, group continuously rebalancing, or no new records. | Group state, assignment, lag, heartbeats, and poll interval. |
| Deserialize | Malformed bytes or target type cannot be instantiated. | Deserializer exceptions, schema, type headers, and trusted packages. |
| Listener | Business error, timeout, unavailable external dependency. | Listener logs, error handler, retry policy, and processing duration. |
| Offset commit | Commit failure or committed progress does not match processing result. | Commit exceptions, ack mode, auto-commit setting, and group state. |

### 9.1. Retries and Dead-Letter Topics Are Error-Handling Branches

When a listener throws an exception, Spring Kafka can route the error through an error handler. Depending on configuration, the record can be retried, sought for re-reading, skipped per policy, or routed to a dead-letter topic (DLT). Retries and DLTs are not part of the happy path; they are policies for handling stage failures.

Retries are only suitable when errors are likely to resolve on their own, such as a temporarily unreachable dependency. Invalid data errors usually never resolve by retrying repeatedly. With delayed retries, consider ordering: a failing record can block subsequent records in the same partition depending on the handling strategy. A DLT isolates records needing investigation, but requires monitoring and a workflow for fixing and replaying data.

Sending a record to a DLT should never be treated as having resolved the business error. The system still needs to know which record was moved, why, how many attempts occurred, where the payload is stored, and who owns follow-up remediation.

### 9.2. Rebalances and Their Impact on Processing

A rebalance occurs when group membership changes or metadata/assignments must be recomputed—for example, when a consumer starts, stops, loses connection, or exceeds poll limits. During a rebalance, partitions can be revoked from one consumer and assigned to another.

If a listener is mid-processing when a partition is revoked, the application must coordinate shutdown, in-flight work, and offset commits according to container settings. A rebalance can increase latency and create conditions for duplicates if a record was processed but its offset was not committed yet. Tracking rebalance counts and listener processing duration helps detect issues early.

## 10. Example Configuration Putting the Stages Together

The following example demonstrates a producer emitting `OrderCreated` and a consumer in group `billing-service` receiving the event. Topic, group, and package names are sample values; replace them with your actual application configuration.

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.orders.events
        spring.json.value.default.type: com.example.orders.events.OrderCreated
```

Event contract:

```java
package com.example.orders.events;

public record OrderCreated(
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}
```

Producer:

```java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send("order-events", event.orderId(), event);
    }
}
```

Consumer:

```java
@Component
@RequiredArgsConstructor
public class BillingOrderListener {

    private final BillingService billingService;

    @KafkaListener(topics = "order-events", groupId = "billing-service")
    public void onOrderCreated(
            OrderCreated event,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
            @Header(KafkaHeaders.OFFSET) long offset) {

        log.info(
            "Processing orderId={} partition={} offset={}",
            event.orderId(), partition, offset
        );
        billingService.startBilling(event);
    }
}
```

When running the example, trace a specific `orderId`:

1. Confirm business logic created `OrderCreated` with valid data.
2. Observe the `KafkaTemplate.send()` future and any exception if sending fails.
3. If sending succeeds, record the topic, partition, and offset from `RecordMetadata`.
4. Confirm group `billing-service` holds partition assignments for topic `order-events`.
5. Check that the listener receives the expected `orderId`, partition, and offset.
6. Observe the group's committed offset progress after the listener succeeds.

If the producer reports success yet the listener does not receive the record, inspect the topic and cluster both applications connect to, group name, assignments, committed offsets, application filters/conditions, and deserialization errors. If the listener receives the record but processes it repeatedly, inspect commit timing, retries, rebalances, and idempotency of the business operation.

## 11. Observing Data Flow Health in Production

When investigating a Kafka flow, inspect each stage rather than merely checking whether the consumer application is running.

- **Producer:** sent record count, send failure count, send latency, timeouts, and retry rate.
- **Broker/topic:** partition count, replication factor, ISR, log disk usage, and retention.
- **Consumer group:** group state, members, partition assignments, committed offsets, and consumer lag.
- **Listener:** succeeded/failed record count, processing duration, retries, DLT count, and exceptions by type.
- **Offset:** compare a partition's latest offset with the group's committed offset to understand the backlog waiting to be processed.

Consumer lag is commonly expressed as the difference between the partition's latest position and the group's committed read progress. Continuously growing lag can indicate that producers emit data faster than consumers process it, consumers have no partition assignments, listeners process too slowly, or errors are causing records to be retried repeatedly. Zero lag at a given instant also does not prove the system has no errors; combine lag with error metrics and end-to-end latency.

A correlation ID or event ID carried across the producer, Kafka headers, and listener logs helps trace an event across multiple services. When logging metadata, use the topic/partition/offset tuple alongside a business identifier to avoid confusing records that happen to share the same offset in different partitions.

## 12. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| `send()` returning successfully means the consumer processed it. | It only reflects the send result at the configured `acks` level; consumer processing is independent. |
| Offset is a sequence number for the entire topic. | Offset only has meaning within a single partition. |
| A consumer group can let multiple consumers read the same partition simultaneously. | Within the same group, a partition at any time is assigned to at most one active consumer. |
| Increasing concurrency always increases throughput. | Parallelism is still bounded by partition count and processing capacity. |
| Using the same key guarantees ordering across all partitions. | Keys only assist routing related records to the same partition; ordering exists only within that partition. |
| Once a consumer reads a record, it gets deleted. | Records are kept per retention; offsets are managed separately per group. |
| `auto-offset-reset: earliest` makes consumers always read from the beginning. | It applies only when the group has no valid offset. |
| A listener not throwing an exception means data was committed. | Commits depend on ack mode, container, transactions, and actual configuration. |
| Kafka provides exactly-once by default for every operation. | Exactly-once has specific scope and configuration prerequisites; side effects outside Kafka require separate design. |

## 13. End-to-End Event Tracing Checklist

When an event does not reach its intended destination, walk through this verification sequence:

1. Did the producer create the right event and target the right topic?
2. Are key/value serializers compatible with the actual data?
3. Did the producer receive a send acknowledgement; if not, what exception did the future report?
4. Which partition and offset was the record written to?
5. Is the consumer subscribed to the right topic and part of the right group?
6. Is the partition assigned to an active consumer?
7. From what committed offset is the group reading; is the record still within retention?
8. Can the deserializer construct the event type expected by the listener?
9. Was the listener invoked and did it succeed; did the error handler retry or route to the DLT?
10. Under which mode are offsets committed, and do they accurately reflect processing outcomes?

Answering these questions pinpoints whether the event stalled at the producer, broker, consumer assignment, deserialization, listener, or commit stage. That forms the foundation for learning deeper topics in serialization, retries, dead-lettering, transactions, exactly-once, concurrency, and testing in Spring Kafka.
