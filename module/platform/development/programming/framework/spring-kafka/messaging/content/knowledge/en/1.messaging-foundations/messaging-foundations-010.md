# Spring Kafka Messaging Learning Roadmap

Within the **Messaging Foundations** chapter, this lesson charts a path from core Kafka concepts to building and operating an event flow with Spring Kafka. The focus of the **SPRING_KAFKA_MESSAGING** module is sending and receiving events using **KafkaTemplate** and **@KafkaListener**, understanding topics, partitions, offsets, and consumer groups, and then adding serialization, retries, dead letters, transactions, exactly-once, concurrency, and testing.

The roadmap is ordered by dependency: first understand how Kafka stores and distributes records, then write producers and consumers; next control errors, consistency, and operability. Each stage includes goals, key material to master, and a hands-on exercise for verification.

## Target Outcomes

After completing this roadmap, you will be able to:

- Explain Kafka brokers, topics, partitions, records, keys, offsets, and consumer groups.
- Build a Spring Boot application that sends events with `KafkaTemplate` and receives events with `@KafkaListener`.
- Choose suitable serializers/deserializers, design payloads, and manage schema changes.
- Understand offset commit timing, how consumer groups split partitions, and limits of processing order.
- Design retries, dead-letter topics (DLTs), and controlled replay of failed records.
- Distinguish Kafka transactions from database transactions, while identifying the practical scope of exactly-once.
- Configure concurrency, test messaging flows, and monitor critical operational metrics.

## 1. Understand Kafka's Messaging Model Before Using Spring

Kafka is a platform for storing and distributing record streams. Producers write records to topics; brokers store records in partitions; consumers read records by offset. Spring Kafka provides APIs and integration mechanics so Java applications work with Kafka without managing the entire protocol manually.

Concepts to distinguish:

| Concept | Meaning When Building Applications |
|---|---|
| Broker | A Kafka server that receives, stores, and serves records. A cluster usually has multiple brokers. |
| Topic | A logical stream holding records of the same type, e.g. **orders.created**. |
| Partition | An ordered log segment of a topic. Kafka distributes partitions across brokers to scale storage and processing. |
| Record | An entry consisting of key, value, timestamp, and optional headers. |
| Key | A value used to route records to partitions. Records with the same key normally land in the same partition under the default partitioner. |
| Offset | A record's position within a partition. An offset is not a global sequence number across the whole topic. |
| Consumer group | A group of consumers sharing the work of reading a topic's partitions. Kafka stores reading progress separately per group. |

A topic with multiple partitions can be read in parallel. Within the same consumer group, at any point in time, a partition is assigned to at most one consumer in that group. A partition can still be read independently by different consumer groups.

~~~mermaid
flowchart LR
    P[Producer<br/>KafkaTemplate] --> T[Topic: orders.created]
    T --> A[Partition 0]
    T --> B[Partition 1]
    T --> C[Partition 2]
    A --> G1[Consumer group: fulfillment]
    B --> G1
    C --> G1
    A --> G2[Consumer group: analytics]
    B --> G2
    C --> G2
~~~

The diagram shows two independent groups receiving the event stream. Within group `fulfillment`, consumers share partitions; group `analytics` tracks its own read progress. Thus, two business systems can react to the same event without calling each other directly.

Several important consequences:

- Kafka guarantees order within a single partition. There is no global order across partitions.
- If events for the same order must travel in sequence, use the order ID as the key so they are routed consistently.
- Increasing consumers in a group scales parallelism only up to the number of assigned partitions.
- Offsets are managed per partition and consumer group. One group finishing a record does not revoke another group's ability to read it.
- A consumer group can re-read records if offsets were not committed or if the application intentionally adjusts its read position.

**Hands-on exercise:** create a topic with three partitions, send multiple records with the same key, and observe the partition and offsets. Continue sending records with different keys to see how distribution changes. Use two consumer groups to verify each group reads the same stream independently.

## 2. Set Up the Environment and Spring Kafka Integration

Before writing code, you need a foundation in Java, Spring Boot, Maven or Gradle, JSON, and basic command-line usage. Knowing Docker makes spinning up local Kafka much easier. You should also understand configuring applications via YAML files or environment variables.

In a Spring Boot project, add the **org.springframework.kafka:spring-kafka** dependency and let Spring Boot dependency management manage compatible versions. When the application starts, Kafka configuration is used to create required components such as `KafkaTemplate`, `KafkaAdmin`, and listener container factories according to auto-configuration conditions.

Example minimal configuration in `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: orders-processor
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      auto-offset-reset: earliest
      properties:
        spring.json.trusted.packages: com.example.messaging.events
~~~

This is an illustrative configuration for development. Broker addresses, serializers, consumer groups, and trusted packages must be tuned for your application. Do not open trusted packages to all packages in production without a clear reason.

A topic can be declared using a `NewTopic` bean so Spring Kafka creates it through `KafkaAdmin`:

~~~java
@Bean
NewTopic ordersCreatedTopic() {
    return TopicBuilder.name("orders.created")
            .partitions(3)
            .replicas(1)
            .build();
}
~~~

The example uses one replica, suitable for local Kafka. Production environments must design the replication factor based on broker count and availability requirements; do not copy a single-replica setting straight to production.

**Hands-on exercise:** start Kafka, run the Spring Boot application, and verify the application connects to the broker. Create the topic, inspect its name and partition count, then stop and restart the application to understand which parts are initialized automatically and which belong to your configuration.

## 3. Build a Producer with KafkaTemplate

A producer turns an application event into a Kafka record. `KafkaTemplate` is Spring Kafka's primary API for sending records, also supporting keys, partitions, timestamps, headers, and completion callbacks.

First, define an event DTO representing the public data consumers need. For example:

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        Instant occurredAt,
        BigDecimal total
) {}
~~~

An event should describe something that happened, such as `OrderCreated`, instead of sending a JPA entity directly or an internal object coupled to database structure. `eventId` aids tracing and deduplication; `orderId` can be used as the Kafka key.

Example publisher with Spring Kafka 3.x:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {
        return kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
        );
    }
}
~~~

In this example, the key is `orderId` and the value is the event. Records for the same order are therefore normally routed to the same partition by the default partitioner, provided partition count and partitioning settings remain unchanged. This is helpful when consumers must process changes to an order in order.

The return value from `send` indicates whether the send was acknowledged by the broker or failed according to producer settings. It does not prove a consumer received, processed, or committed the offset. If business logic needs to know processing status at the target system, use a separate feedback mechanism such as a result event or persisted state.

When learning producers, explore these steps in sequence:

1. Send a simple value, then send serialized objects.
2. Send with a key and observe which partition is selected.
3. Read the asynchronous result to log success or failure.
4. Add headers like `correlation-id` or `event-type` when cross-service metadata is needed.
5. Study settings such as `acks`, `retries`, `idempotence`, `batch.size`, `linger.ms`, and `compression.type`.

**Hands-on exercise:** build an API or service that publishes `OrderCreatedEvent`. Send several orders, verify keys and payloads on Kafka, then try sending an unserializable payload to observe the error. Add logs including `eventId`, topic, key, and send result for easier tracing.

## 4. Build a Consumer with @KafkaListener

A consumer receives records from a topic and hands payloads off to business logic. With Spring Kafka, the most common way is declaring a method annotated with `@KafkaListener`.

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "fulfillment-service"
    )
    public void onOrderCreated(OrderCreatedEvent event) {
        // Invoke order processing logic here.
    }
}
~~~

Spring Kafka manages the listener container, polls records from brokers, converts payloads, and invokes the listener method. When the handler throws an exception, the container and error handler decide what happens next per configuration.

Understand three layers of behavior:

- **Receiving records:** the consumer polls data from assigned partitions.
- **Processing records:** the listener runs business logic; an invocation can succeed or throw an error.
- **Committing offsets:** Kafka records the group's progress. If the application stops before the appropriate offset is committed, the record may be read again.

A consumer group is the boundary of reading progress. Two instances in the same group share partitions; two different groups can both receive all records. Changing `group-id` also means the application is using a separate reading progress tracker.

Pay special attention to **auto-offset-reset**. `earliest` or `latest` is used when the group has no valid offset, or when the stored offset is no longer usable. `earliest` picks the oldest position still retained; `latest` starts from new records. `earliest` does not mean the application re-reads the entire topic on every restart if the group already has a valid offset.

Spring Kafka provides offset acknowledgement modes via `AckMode`, such as `RECORD`, `BATCH`, `MANUAL`, and `MANUAL_IMMEDIATE`. Pick a mode suited to how the listener processes data and understand when offsets are committed. For normal business processing, ensure listener failures do not mark progress as if the record succeeded.

**Hands-on exercise:** run two consumer instances with the same `group-id` and observe partition assignment. Next, change the `group-id` of one instance and observe the new group reading the stream independently. Stop the application mid-processing, restart it, and verify whether the record is redelivered.

## 5. Serialization and Event Contract Design

Kafka stores bytes. Producers and consumers must agree on how to turn objects into bytes and back. Serializers run on the sending side; deserializers run on the receiving side. Misconfigured settings or incompatible contracts cause conversion failures even while broker connectivity works fine.

Common choices:

| Format | When Suitable | Considerations |
|---|---|---|
| String | Simple content, plain text, or payloads parsed separately | The application owns parsing and validating data. |
| JSON | Human-readable, easy multi-language integration, great for early stages | Requires agreements on data types, optional fields, and schema evolution. |
| Avro or Protobuf | Systems with strict data contracts needing schemas and compatibility checks | Requires schema management and version release workflows. |

When designing events, favor stable fields such as `eventId`, `eventType`, `occurredAt`, `aggregateId`, and `schemaVersion` if explicit versioning is needed. Payloads should contain only data consumers need to understand the event; avoid sending passwords, tokens, sensitive details, or entire internal entities.

Contract evolution guidelines:

- Add new fields in a way older consumers can ignore or populate with defaults.
- Think carefully before renaming, deleting, or changing the meaning of existing fields.
- Distinguish missing fields, null fields, and fields with default values when business logic requires it.
- Do not use Java class names as the sole cross-service contract; packages or class structures can change during code refactoring.
- Test serialization/deserialization with representative payloads across supported versions.

With Spring Kafka's `JsonSerializer` and `JsonDeserializer`, understand type headers and trusted packages. If applications use different packages or models, configure explicit type mappings rather than blindly relying on class names sent in headers.

**Hands-on exercise:** create an event DTO with `eventId`, `orderId`, and `occurredAt`; send JSON and receive it back as an object. Add an optional field and test an older consumer. Next, send a mistyped payload or missing required field to observe deserialization errors and see whether they happen before or inside the listener.

## 6. Partitions, Offsets, Concurrency, and Processing Order

Partitions determine topic-level parallelism. Consumer groups distribute partitions across member consumers. If a topic has three partitions, a group cannot utilize more than three active consumers to read that topic simultaneously; extra consumers receive no partition assignments for this topic.

In Spring Kafka, listener container concurrency can be configured via the listener container factory or listener settings matching your version. When increasing concurrency, check partition counts, database and downstream API capacity, and per-instance resource limits.

Do not confuse concurrency with global ordering. Kafka preserves record order within each partition. If two records for the same aggregate can land on two different partitions, consumers have no basis to guarantee ordering between them. Using a stable key like `orderId` is a common way to keep related events in the same partition.

An offset is a group's reading progress on a partition. Key points:

- Offsets increment per record in a partition and do not represent timestamps or cross-partition order.
- A consumer can read ahead of its committed position; read position and committed position are distinct concepts.
- If processing succeeds yet crashes before committing, the record may be redelivered.
- If committing occurs before processing completes, a failure afterward can cause the application to skip the record on resume.
- Rebalances can occur when consumers join, leave the group, or fail to poll within configured limits.

Therefore, handlers should tolerate duplicate execution safely. A common technique is storing processed `eventId` values or enforcing a unique business key in the database. When a record is redelivered, the application recognizes the event already completed and avoids repeating business side effects.

**Hands-on exercise:** run multiple consumers with varying concurrency settings. Log topic, partition, offset, key, and `eventId` to observe partition assignments. Simulate a slow consumer to watch lag build up, then try increasing partitions or concurrency; document the system's actual bottlenecks.

## 7. Retries and Dead-Letter Topics

Errors when consuming events can be transient or unrecoverable via retries. For example, a timeout to a downstream service might clear after a few seconds; a payload missing a required field will continue failing no matter how many times it is retried.

Classify errors before designing retries:

- **Transient errors:** timeouts, interrupted connections, temporarily unavailable dependencies. Suitable for retries with backoff.
- **Unprocessable data or business errors:** malformed payloads, missing required fields, invalid state. Usually should route to an error flow after appropriate attempts.
- **Programming bugs:** unexpected nulls, mapping errors, or logic defects. Retries do not fix bugs; log, alert, and fix the root cause.

Spring Kafka supports error handlers for listener containers, such as `DefaultErrorHandler` combined with `BackOff` and `DeadLetterPublishingRecoverer`. An illustrative setup:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1000L, 2L);
    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(IllegalArgumentException.class);
    return handler;
}
~~~

In the example, records are retried with a one-second interval for the configured number of attempts; once recovery fails, the recoverer sends the record to a dead-letter topic following default or custom routing rules. Configure DLT serializers compatible with actual record types and ensure target topics exist with sufficient partitions when routing requires it.

Another approach is retry topics, configurable with `@RetryableTopic` and handling final failures with `@DltHandler`. Retry topics fit when you want to delay subsequent attempts without blocking the main partition during wait intervals. However, this can alter observed order between related events: a failing record moves to a retry topic while subsequent records continue processing on the main topic.

Choose according to business requirements:

| Approach | Advantage | Trade-Off |
|---|---|---|
| Retry in listener container | Direct setup, easier to keep partition flow aligned during retries | The partition can be blocked by a failing record. |
| Retry topic | Delays and decouples retries from the main stream | More topics to manage; processing order can change. |
| Send straight to DLT | Quickly isolates unprocessable records | Requires procedures to inspect, fix data, and replay. |

A DLT is not a place to forget data. A sound operational workflow records failure reasons, original topic, partition, offset, key, `eventId`, and error timestamp; monitors DLT record counts; assigns owners responsible for handling failures; and maintains a replay policy once root causes are fixed. Before replaying, confirm consumers handle duplicate delivery safely without creating duplicate business effects.

**Hands-on exercise:** simulate a transient error to test retry counts and backoff intervals. Send an invalid payload to route it into the DLT. Inspect the failed record's metadata, fix the cause, and replay it in a controlled manner. Try both container retries and retry topics to compare impacts on ordering.

## 8. Transactions and the Scope of Exactly-Once

Kafka transactions group multiple Kafka writes into a single unit: either records in the transaction commit, or they are discarded when the transaction aborts. In a consume-transform-produce flow, Kafka can coordinate writing output records with committing input offsets so outputs are not written without updating input offsets, or vice versa.

Spring Kafka supports transactions via producer transactions and `KafkaTransactionManager`. With Spring Boot, you can configure `transaction-id-prefix` for the producer. The prefix must be unique across running instances to avoid transactional identity collisions. Consumers reading transactional data typically need an appropriate `isolation.level`, such as `read_committed`, to see only committed transactions.

Distinguish three scopes:

1. **Kafka transactions:** protect groups of Kafka read/write operations within Kafka's supported transaction mechanism.
2. **Database transactions:** protect changes inside a database via database transactions.
3. **External side effects:** HTTP calls, sending emails, or interacting with systems that do not join a Kafka transaction.

Exactly-once in Kafka does not automatically turn an entire distributed workflow into exactly-once. If a listener writes to a database and crashes before committing the offset, the record may be redelivered and the database statement may run again. If a listener calls an external API and times out, the application may not even know whether the recipient applied the effect.

To protect business logic across system boundaries, combine:

- **Idempotency:** the same `eventId` or idempotency key produces only one business outcome.
- **Inbox pattern:** save a marker for the received event in the same transaction as business data updates.
- **Outbox pattern:** write business changes and an outbox row in the same database transaction; a separate process publishes outbox rows to Kafka.
- **Reconciliation:** detect and resolve inconsistent states that local transactions alone cannot fully eliminate.

**Hands-on exercise:** build a consume-transform-produce flow where a consumer receives `OrderCreatedEvent` and produces `InventoryReservedEvent`. Test transactions on success and on forced abort. Then add a database operation to see clearly why Kafka transactions do not cover database writes; design idempotency or outbox/inbox for that business step.

## 9. Testing Messaging Flows

A messaging application cannot merely test that a publisher method was called. You must verify that records are truly sent, deserialized, processed by consumers, offsets are managed properly, and errors route to expected targets.

Tests can be divided into layers:

| Test Layer | Verification Scope |
|---|---|
| Unit test | Business logic isolated from Kafka; use mocks for collaborators where appropriate. |
| Serialization test | Payloads serialize/deserialize properly and remain compatible with event contracts. |
| Integration test | Producer, broker, listener container, and consumer working together. |
| Failure-path test | Retries, DLT, deserialization failures, listener errors, and replay behavior. |
| Reliability test | Duplicate handling, consumer shutdowns, rebalances, and crash recovery. |

Spring Kafka supports `EmbeddedKafka` for integration tests. Testcontainers is a strong option when running a real broker in tests closer to production setups. Pick tools based on required fidelity and test execution cost.

When testing asynchronously, avoid fixed `Thread.sleep` durations to guess when a consumer finished. Wait on explicit conditions with reasonable timeouts, such as using Awaitility or equivalent synchronization primitives. Timeouts let tests fail clearly when the system does not reach expected outcomes.

Minimum scenarios to cover:

- Producer sends to the expected topic, key, headers, and payload.
- Consumer receives the right data type and executes the right logic.
- Two consumer groups independently read the same topic.
- Listener errors trigger retries or DLT per configuration.
- Redelivered records do not cause duplicate business effects.
- Incompatible payloads are handled and observed cleanly.
- Transaction commits and aborts produce expected outcomes.

**Hands-on exercise:** write integration tests for `OrderEventPublisher` and `OrderCreatedListener` using `EmbeddedKafka` or Testcontainers. Use Awaitility to wait for assertions, then add tests for retries, DLT, and duplicate processing.

## 10. Observability and Production Readiness

In production, you need to know whether producers are succeeding in sending records, whether consumers are keeping up with incoming rates, and where failing records are going. Key signals to track:

- **Consumer lag:** difference between the latest record position and the group's committed progress per partition. Steadily growing lag can indicate slow consumers or stalled consumers.
- **Send and receive rates:** records per second, payload sizes, and end-to-end latency from publish to processing.
- **Producer errors:** timeouts, metadata errors, authentication failures, serialization errors, and failed sends.
- **Consumer errors:** exceptions by type, processing duration, rebalances, retry counts, and DLT counts.
- **Resources:** CPU, memory, network connections, threads, and capacity of databases or downstream services.

Logs should include topic, partition, offset, key, `eventId`, consumer group, and `correlation-id` whenever available. Avoid logging full payloads if payloads carry personal data, secrets, or are large. Metrics and logs should help locate a specific record without exposing sensitive data.

When preparing for production, review replication factor, `min.insync.replicas`, `acks`, idempotence, retention, partition counts, record size limits, TLS/SASL security, and ACLs. Settings like `batch.size`, `linger.ms`, `compression.type`, `max.poll.records`, or `max.poll.interval.ms` should be tuned from load metrics and processing traits, never copied blindly from examples.

## 11. Capstone Exercise: Order Event Flow

After completing each stage, combine them into a small business flow:

~~~mermaid
flowchart TD
    API[Order API] --> PUB[KafkaTemplate]
    PUB --> OC[orders.created]
    OC --> INV[Consumer group: inventory]
    OC --> PAY[Consumer group: payment]
    INV --> IR[inventory.reserved]
    INV --> ID[inventory DLT on failure]
    PAY --> PA[payment.authorized]
    PAY --> PD[payment DLT on failure]
~~~

Implementation requirements:

1. Order API publishes `OrderCreatedEvent` with `eventId` and `orderId`; use `orderId` as the key.
2. Inventory service and Payment service use two separate consumer groups to both receive `OrderCreatedEvent`.
3. Inventory service emits `InventoryReservedEvent` or handles errors per retry/DLT policy.
4. Payment service emits `PaymentAuthorizedEvent` or routes failed records to DLT.
5. Each consumer records processed `eventId` markers to guard against duplicate effects.
6. Write integration tests for the happy path, transient errors, non-retryable errors, and DLT replay.
7. Log `correlation-id` to trace an order across services.
8. Monitor lag and record counts in retry topics/DLTs under test load.

You do not need to implement every transaction pattern upfront. Finish basic send/receive and foundational tests first, then layer in idempotency, retries, DLT, and transactions step by step. If database writes and event emission must be consistent, extend the exercise with the outbox pattern.

## 12. Learning Sequence and Completion Criteria

| Stage | Core Topics | Self-Verification Criteria |
|---|---|---|
| 1. Kafka Foundations | Topics, partitions, keys, offsets, consumer groups | Can explain why ordering is guaranteed only within a single partition. |
| 2. Spring Kafka Setup | Dependencies, bootstrap servers, producer/consumer config | Application connects to broker and creates topics. |
| 3. Producer | `KafkaTemplate`, keys, headers, callbacks | Can send events and verify send outcomes. |
| 4. Consumer | `@KafkaListener`, group-id, offsets, `AckMode` | Can receive events, understand commits, and verify replay behavior. |
| 5. Serialization | JSON, serializer/deserializer, schema evolution | Both sides exchange payloads cleanly and handle contract changes. |
| 6. Concurrency | Partition assignment, concurrency, ordering, lag | Can explain parallelism limits and observe partition assignments. |
| 7. Reliability | Retries, DLT, replay, idempotency | Can classify errors and handle failed records under explicit policy. |
| 8. Consistency | Kafka transactions, exactly-once, outbox/inbox | Can state exact transaction boundaries and protect business effects on redelivery. |
| 9. Testing and Operations | EmbeddedKafka/Testcontainers, metrics, logs, security | Has tests for success and failure paths; knows how to monitor lag and DLT. |

You can consider the roadmap complete when you can build an application with a producer, at least one consumer group, a clearly contracted payload, error handling with retries/DLT, deduplication safeguards, integration tests, and sufficient logs/metrics for tracing. More importantly, you should be able to explain what happens when a consumer crashes mid-processing, when partitions are reassigned, when records fail repeatedly, or when a database updates yet the Kafka offset has not committed.

Spring Kafka integrates messaging into Spring applications, while event-flow reliability depends on designing keys, data contracts, offsets, retries, idempotency, transactions, and tests. Learning these pieces in order builds a solid foundation for developing scalable, operable event-driven systems.

