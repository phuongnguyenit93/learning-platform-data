# Scope of Responsibility of Spring Kafka

## Lesson Objectives

Within the **Messaging Foundations** chapter, this lesson defines which layer Spring Kafka is responsible for in a system using Apache Kafka, the capabilities the library provides to Spring applications, and which parts still belong to the Kafka broker, the operational platform, or business code.

**SPRING_KAFKA_MESSAGING** focuses on building applications that send and receive events using Spring Kafka, especially `KafkaTemplate` and `@KafkaListener`. While studying this module, you need to understand topics, partitions, offsets, and consumer groups; serialization; retries and dead letters; transactions and exactly-once; concurrency; and testing so you can operate reliable messaging flows.

After this lesson, the learner will be able to:

- Place Spring Kafka accurately within application architecture and distinguish it from Apache Kafka.
- Identify the tasks Spring Kafka supports when sending, receiving, converting, and error-handling messages.
- Explain the boundaries between Spring Kafka APIs, the Kafka client, the Kafka broker, and business logic.
- Recognize guarantees that the system must design additionally, such as business idempotency and coordination with external databases.

## 1. Where Does Spring Kafka Fit in the Architecture?

Apache Kafka is a distributed event streaming platform. A Kafka cluster stores records in topics, splits topics into partitions, distributes partitions across consumers in consumer groups, and manages offsets. Producers and consumers communicate with the Kafka cluster through the Kafka client.

Spring Kafka is a library that integrates Kafka into the Spring ecosystem. It provides APIs, configuration, and lifecycle management so Spring applications can use the Kafka client more conveniently. Spring Kafka does not replace the Kafka broker, nor does it abstract away Kafka's core concepts.

A typical flow can be pictured as follows:

~~~mermaid
flowchart LR
    A["Spring business code"] --> B["Spring Kafka"]
    B --> C["Apache Kafka Client"]
    C --> D["Kafka Broker Cluster"]
    D --> C
    C --> B
    B --> E["Listener / business handler code"]
~~~

On the sending side, business code calls Spring Kafka APIs. The library translates calls into operations on the Kafka producer client; the client performs serialization and sends records to brokers. On the receiving side, the Kafka consumer client fetches records from brokers; Spring Kafka coordinates polling, message conversion, and invoking the application's listener method.

Spring Boot can auto-configure many components based on properties in application configuration and existing beans. That is Spring Boot's configuration convenience layer; the core messaging integration is still provided by Spring Kafka.

## 2. Primary Responsibilities of Spring Kafka

### 2.1. Integrating the Kafka Client with Spring Applications

Spring Kafka bridges Spring abstractions with Apache Kafka's producer, consumer, and admin clients. Applications can declare configuration via properties, beans, or Java configuration, such as:

- Bootstrap server addresses and connection properties.
- Serializers for outgoing data and deserializers for incoming data.
- Consumer groups, consumer properties, and offset management strategies.
- Security settings supported by the Kafka client.
- Transaction, timeout, client-side retry settings, and related limits.

Spring Kafka makes configuring and using clients fit Spring's container and dependency injection model. Connection authentication, authorization, TLS/SASL setup, and Kafka cluster operations still need proper design on both client and infrastructure sides.

### 2.2. Sending Records with KafkaTemplate

`KafkaTemplate` is the primary abstraction for applications to send records to Kafka. It frees business code from manually managing the `KafkaProducer` lifecycle on every operation.

`KafkaTemplate` supports common sending patterns:

- Sending to a topic, optionally with key and value.
- Sending records targeting a specific partition or timestamp when business logic requires it.
- Sending with headers to pass metadata.
- Receiving asynchronous results to know whether the send succeeded or failed.
- Participating in Kafka transactions when the producer is configured and managed transactionally.

For example, an order service emits an event when an order is created:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );
    }
}
~~~

In the example, the topic is where the event is stored; `orderId` is the key so the Kafka partitioner selects a partition per the default strategy or chosen partitioner. Using the same key usually routes related entity events to the same partition, allowing ordering to be preserved within that partition.

Calling `send` only initiates an asynchronous send operation. If business logic needs to react to the send result, the application must observe the future/callback and handle errors accordingly. Calling `send` without checking the result must not be treated as proof that the broker recorded the event.

### 2.3. Receiving and Dispatching Processing with @KafkaListener

Spring Kafka provides `@KafkaListener` to mark record-receiving methods. Behind this annotation sits the listener container: the container creates and manages Kafka consumers, runs polling, dispatches records to listeners, and manages offset commits according to configuration.

~~~java
@Service
public class OrderEventListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "billing-service"
    )
    public void handle(OrderCreated event) {
        // Validate and process the event according to billing business logic.
    }
}
~~~

Applications can configure listeners to receive one record at a time or in batches. Listener containers also expose settings for concurrency, acknowledgements, error handlers, pause/resume, and container lifecycle.

Several critical boundaries:

- `@KafkaListener` is the bridge between a Kafka consumer and a Java method; it does not turn message handling into an automatic distributed business transaction.
- The listener container coordinates polling and offsets; commit behavior depends on acknowledgment mode, container settings, and how the listener handles execution.
- Consumer groups and partitions still obey Kafka's distribution model. Increasing concurrency cannot yield useful parallelism beyond the number of partitions assigned to consumers in the group.
- Record ordering is guaranteed within a single partition, not across an entire topic or multiple topics.

### 2.4. Managing Topics on the Application Side

Spring Kafka provides `KafkaAdmin` so applications can declare or request creation of needed topics, typically via `NewTopic` beans. This mechanism is useful for environment initialization or managing topics tied to the application lifecycle.

However, `KafkaAdmin` does not replace platform governance responsibilities. Decisions regarding partition counts, replication factor, retention, quotas, access permissions, disk capacity, and operational policies must be aligned with the team managing the Kafka cluster. Topic creation capability also depends on the connecting principal's permissions and broker configuration.

### 2.5. Data and Metadata Conversion

Kafka stores keys and values as bytes. Spring Kafka combines Kafka serializers/deserializers with message converters to map between bytes, Java objects, and Spring's `Message` abstraction.

These components help applications:

- Send and receive Java objects without converting bytes manually in every method.
- Use headers to pass metadata such as correlation IDs, event types, or tracing context.
- Map Kafka headers to Spring message headers and vice versa.
- Select data types, converters, and serializers matching the event contract.

Serializers and deserializers on both sides must be compatible. With JSON or schema-based formats, development teams must clearly define data structures, backward/forward compatibility rules, and versioning strategy. Spring Kafka assists with conversion, but does not define an organization's data contracts on its own.

### 2.6. Error Handling, Retries, and Dead Letters

In practice, listeners can fail due to invalid data, temporarily unavailable dependencies, timeouts, or programming bugs. Spring Kafka provides error handler and recovery mechanisms so applications can define how to handle these situations.

Common options include:

- Retries with backoff for errors likely to self-recover.
- Exception classification to decide which errors are retried and which go straight to recovery.
- `DeadLetterPublishingRecoverer` to publish unprocessable records to a dead-letter topic (DLT).
- Retry topic mechanisms, such as `@RetryableTopic`, for cases where delayed retries should be offloaded to dedicated topics.

Retries must have clear limits and policies. Infinite retries can keep a consumer stuck on a single record, overload downstream dependencies, or prolong processing delays. When routing a record to a DLT, retain enough metadata to trace the root cause, fix data, and decide on replay.

Retry topics can alter observed ordering between related events because failed records are reprocessed on another topic at a later time. If ordering is a business requirement, carefully evaluate retry strategies and data partitioning.

### 2.7. Transactions and Exactly-Once Within Kafka Scope

Spring Kafka integrates Kafka transactions so applications can send multiple records as an atomic unit and build consume-transform-produce flows that coordinate writing outputs with input offsets. Depending on configuration, consumers can read only committed records using an appropriate isolation level.

This forms the basis for exactly-once semantics within Kafka's scope. However, this concept has concrete boundaries:

- It does not automatically bring an HTTP call or relational database write into the Kafka transaction.
- It does not automatically eliminate all duplicate side effects in business logic.
- It requires proper producer/consumer configuration, transaction manager, and offset handling.
- Applications must still design recovery when processes crash mid-step or dependencies fail.

For flows needing to coordinate Kafka and a database, consider the Outbox Pattern, Inbox Pattern, or idempotent processing depending on consistency requirements. Never claim a system is end-to-end exactly-once solely because transactions are enabled in Spring Kafka.

### 2.8. Concurrency and Listener Control

Spring Kafka allows configuring listener container concurrency to process multiple partitions in parallel. It also provides container management mechanisms, pause/resume, and batch listeners to adapt to real workloads.

Useful parallelism is bounded by the number of partitions assigned to consumers in a group. If a topic has few partitions, adding more consumers or concurrency may not increase throughput. If processing one partition is slow, that partition can still become a bottleneck.

Choosing concurrency requires considering:

- Partition counts and how keys distribute records.
- Average and variance of listener processing times.
- Load capacity of databases and downstream services.
- Application resource limits, connection counts, and batch sizes.
- Poll timing, heartbeats, rebalances, and ordering requirements.

Spring Kafka provides coordination tools; applications and operations teams must tune settings to match load, resources, and business rules.

### 2.9. Testing and Operational Observability

Spring Kafka includes testing utilities to test producers, listeners, and integration flows with Kafka. `EmbeddedKafka` can be used in tests needing an embedded broker, or dedicated Kafka environments such as Testcontainers when testing closer to real deployment setups.

In operations, both the application and the Kafka cluster must be observed. Useful signals include:

- Send/receive rates and error rates.
- Consumer lag by group and partition.
- Listener processing duration.
- Retry counts, DLT record counts, and age of pending records.
- Rebalance counts, consumer state, and connection errors.
- Transaction health, timeouts, and serialization/deserialization errors.

Spring Kafka integrates with Spring's observability ecosystem and Kafka client metrics. However, setting alert thresholds, storing metrics, building dashboards, and establishing incident response procedures remain operational responsibilities.

## 3. Responsibility Boundaries Across Layers

| Component | Primary Responsibilities | Examples |
|---|---|---|
| Business application | Decide which events to emit, validate content, and decide what to do upon receiving events | Create `OrderCreated`, check permissions, update order status |
| Spring Kafka | Provide Spring APIs, configuration and coordination of producer/consumer/listener, message conversion, error handling, and transaction integration | `KafkaTemplate`, `@KafkaListener`, listener container, `KafkaAdmin` |
| Apache Kafka client | Implement broker communication protocol and producer/consumer/admin operations | Partition assignment, poll, send records, serializer/deserializer |
| Kafka broker cluster | Store records, manage topics/partitions, replication, leaders, and offsets per Kafka mechanics | Retention, replication factor, ISR, logs |
| Operational platform | Provision and secure the cluster, manage storage capacity, access control, monitoring, and recovery | TLS/SASL, ACLs, quotas, backup/DR, alerting |
| Event and data contracts | Define structure, semantics, and compatibility rules of events | Schema versioning, compatibility, event naming conventions |

This table helps prevent two common misconceptions. First, using Spring Kafka does not mean an application can ignore topics, partitions, offsets, and consumer groups. Second, Spring Kafka provides technical mechanisms to send and receive records, yet cannot decide whether an event is valid in business terms or whether an operation is safe to repeat.

## 4. Tracing an Event Through Spring Kafka

Suppose the Order service emits an `OrderCreated` event and the Billing service consumes that event.

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant S as Spring Kafka
    participant P as Kafka Producer
    participant K as Kafka Broker
    participant C as Kafka Consumer
    participant B as Billing Listener

    O->>S: KafkaTemplate.send(topic, key, event)
    S->>P: Send record
    P->>K: Serialize and publish
    K-->>P: Send result
    P-->>S: Send result
    K-->>C: Record from assigned partition
    C->>S: Poll record
    S->>B: Convert and invoke @KafkaListener
    B->>B: Execute business logic
    S->>C: Manage acknowledgment/offset per configuration
~~~

On the producer side, the key influences which partition is chosen. The send result indicates whether the publish succeeded according to the Kafka client's response. If the application must ensure business state is only confirmed after the event is sent, it must design an appropriate update-and-publish sequence, such as the Outbox Pattern when a database is involved.

On the consumer side, the listener container polls records and invokes the method annotated with `@KafkaListener`. The offset tracks the consumer's read position within the partition. Commit timing must match processing completion: committing too early can skip records after a crash; committing late can redeliver records and require business logic to tolerate duplicate processing.

This example shows that Spring Kafka handles technical orchestration around the messaging flow. Final outcomes still depend on Kafka settings, how the container manages offsets, and the correctness of business code.

## 5. Things the Application Must Still Design Explicitly

When building systems with Spring Kafka, the development team still needs to make the following decisions:

1. **Event design:** define events reflecting business facts that happened, with stable names and payloads, avoiding sending internal objects overloaded with implementation details.
2. **Key and partition selection:** choose keys according to entities needing ordering; determine partition counts based on throughput, parallelism, and scalability.
3. **Schema management:** align data types, versioning, and compatibility rules between producers and consumers.
4. **Idempotency design:** handle safely when the same event is redelivered, e.g., storing processed event IDs or enforcing unique database keys.
5. **Retry policy:** distinguish transient failures from data failures, set retry limits, backoff, and DLT handling procedures.
6. **Offset decisions:** select an acknowledgment/commit strategy suited to listener side effects and tolerance for lost or duplicate messages.
7. **Coordinating non-Kafka systems:** use transactions or appropriate integration patterns when a flow writes to a database, calls APIs, or publishes events.
8. **Operations and security:** prepare access permissions, encrypted connections, consumer lag monitoring, DLT alerting, and recovery runbooks.

## 6. Choosing the Right Abstraction

| Need | Common Spring Kafka Component |
|---|---|
| Send an event from business code | `KafkaTemplate` |
| Declare an event-receiving method | `@KafkaListener` |
| Customize lifecycle, concurrency, acknowledgment, and batching | `ConcurrentKafkaListenerContainerFactory` / listener container |
| Declare topics to create from the application | `KafkaAdmin` and `NewTopic` |
| Convert objects, keys, values, and headers | Serializer, deserializer, and message converter |
| Handle errors, retries, and route records to DLT | Error handler, recoverer, and retry-topic support |
| Send/receive within Kafka transactions | Transactional producer and Kafka transaction manager |
| Test messaging flows | Spring Kafka testing utilities, `EmbeddedKafka`, or Kafka in Testcontainers |

Start with the simplest abstraction that satisfies the need. `KafkaTemplate` fits explicit sends in services; `@KafkaListener` fits consumers whose lifecycle is managed by Spring. Customize containers, retries, transactions, or batching only once throughput, ordering, reliability, and recovery requirements are clear.

## 7. Misconceptions to Avoid

- **"Spring Kafka is a Kafka broker."** False. Spring Kafka is an application-side integration library; data is stored and distributed by the Kafka cluster.
- **"Using @KafkaListener automatically gives once-only processing."** False. Redelivery, offset commits, and business side effects still require deliberate design.
- **"Increasing concurrency always boosts throughput."** False. Assigned partitions, downstream load, and processing latency limit concurrency gains.
- **"Retries solve every error."** False. Data errors or logic bugs may never self-resolve; error classification and DLT/recovery are needed.
- **"Kafka transactions include databases and HTTP."** False. Kafka transactions are scoped to Kafka; external systems require separate coordination.
- **"Having a JSON serializer gives schema governance."** False. JSON conversion does not define versioning or guarantee producer-consumer compatibility.

## 8. Responsibility Scope Evaluation Checklist

Before promoting a messaging flow to production, verify:

- [ ] The application clearly defines event, topic, key, and consumer group.
- [ ] Producer and consumer use compatible serialization/deserialization settings.
- [ ] Send results are tracked if business logic depends on publish success.
- [ ] Listeners use an acknowledgment/commit strategy aligned with business processing.
- [ ] Consumers tolerate receiving the same event again.
- [ ] Retries have limits, backoff, and exception classification.
- [ ] DLTs have designated owners or procedures for inspection and reprocessing.
- [ ] Concurrency matches partition counts and downstream system capacity.
- [ ] Transactions are configured with the right scope; not mistaken for end-to-end guarantees.
- [ ] Metrics, logs, tracing, and alerts cover both processing errors and consumer lag.
- [ ] Topics, access permissions, retention, and cluster resources are properly governed.

## Conclusion

Spring Kafka handles the integration layer between Spring applications and Apache Kafka: providing send/receive APIs, managing listener containers, converting messages, assisting topic management, handling errors, retries, transactions, concurrency, testing, and observability. Kafka remains responsible for storing and distributing records by topic, partition, offset, and consumer group. Applications remain responsible for event semantics, business correctness, idempotency, and coordination with external systems.

Understanding this boundary is the foundation for using `KafkaTemplate` and `@KafkaListener` effectively, while designing messaging flows that are scalable, resilient, and reliably operated.
