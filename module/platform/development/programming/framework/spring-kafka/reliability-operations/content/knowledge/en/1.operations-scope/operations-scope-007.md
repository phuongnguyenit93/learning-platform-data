# When to Use Spring Kafka Instead of the Plain Client

Spring Kafka fits when a Java application built with Spring needs to publish and consume Kafka messages using common patterns while integrating message consumption into Spring's lifecycle, configuration, and operational model. The plain Kafka client fits when a program needs direct control over producers or consumers, minimal dependencies, or does not use Spring.

Both options use the same Kafka Java Client at the broker communication layer. Spring Kafka provides an integration layer and abstractions on top of that client. Therefore, choosing Spring Kafka is primarily a decision about abstraction level, application organization, and code maintenance cost; using Spring Kafka does not by itself make a system more reliable.

## 1. Distinguishing the Two Options

### Plain Kafka Client

The plain Kafka client consists of direct Java APIs such as `KafkaProducer`, `KafkaConsumer`, and `AdminClient` in the `kafka-clients` library.

For producers, the application builds configuration, creates `ProducerRecord` instances, sends records, and handles send results itself. For consumers, the application manages its own `poll()` loop, subscriptions or partition assignments, record processing, offset commits, rebalances, and consumer shutdown on exit.

This option provides fine-grained, low-level control. In return, the application must build and maintain substantial operational plumbing.

### Spring for Apache Kafka (Spring Kafka)

Spring Kafka provides Spring-integrated components, most commonly:

- `KafkaTemplate` for sending messages.
- Listener containers and `@KafkaListener` for receiving messages.
- Management of consumer lifecycle, concurrency, acknowledgement, and offset commits.
- Configurable error handling, retries, dead-letter topics (DLT), and transactions.
- Integration points with Spring's dependency injection, application configuration, logging, metrics, tracing, and testing ecosystem.

Spring Boot can auto-configure many components from `spring.kafka.*` properties. The application must still decide critical settings such as bootstrap servers, serializers/deserializers, consumer groups, acknowledgement, retries, and transactions.

### Quick Comparison Table

| Aspect | Spring Kafka | Plain Kafka Client |
|---|---|---|
| Sending messages | Uses `KafkaTemplate` and Spring configuration | Calls `KafkaProducer.send()` directly |
| Receiving messages | Listener container, typically declared with `@KafkaListener` | Hand-written `poll()` loop |
| Offsets and acknowledgement | Container manages per `AckMode`; configurable manual ack | Manually decides when and how to commit |
| Error handling | Built-in error handlers, backoff, DLT, and retry topics | Self-designed retry, pause/resume, DLT, and commits |
| Lifecycle | Integrates with Spring bean and application lifecycle | Manually initializes, closes, and coordinates lifecycle |
| Configuration | Beans, properties, and Spring Boot auto-configuration | `Properties` or application-specific configuration |
| Testing | Spring Kafka test utilities and Spring Test integration | Sets up producers/consumers and test harness manually |
| Level of control | High for common use cases; lower-level APIs accessible when needed | Most direct and granular |
| Dependencies | Requires the Spring Kafka/Spring ecosystem | Requires only Kafka client and application-needed libraries |
| Code maintenance effort | Typically less infrastructure boilerplate in Spring apps | More lifecycle and error-handling responsibility in app code |

## 2. When Should You Choose Spring Kafka?

### 2.1. The Application Already Runs on Spring or Spring Boot

This is usually the clearest reason. If the application already uses Spring, Spring Kafka lets you configure Kafka the same way the application manages databases, HTTP clients, services, and other components.

For example, a billing service consuming order events can declare a listener as a bean. Spring manages the listener container alongside the application lifecycle; business dependencies are injected directly into the listener. The development team does not have to write a dedicated `poll()` thread, implement shutdown hooks manually, or coordinate consumer startup with the application.

Spring Kafka is especially well suited when multiple services in the same system need a consistent way to configure and operate Kafka.

### 2.2. Standard Message Publishing and Consumption Flows

Applications commonly share needs such as:

- Publishing an event after a business operation completes.
- Consuming events within a consumer group.
- Processing single records or batches of records.
- Scaling listener threads relative to partition counts and processing capacity.
- Routing failing messages to retries or a DLT.
- Monitoring listener errors and state during operations.

Spring Kafka already provides abstractions for these tasks. Teams can focus on business logic and operational policies instead of maintaining a custom consumer framework.

### 2.3. Requiring Explicit, Configurable Acknowledgement and Commit Mechanics

For consumers, offset commit timing determines whether messages can be reprocessed after an incident. Spring Kafka provides `AckMode` options to define whether the container commits offsets per record, per batch, periodically, or upon explicit acknowledgement.

For instance, a listener can acknowledge only after business processing succeeds. This supports at-least-once semantics: if the application crashes before committing, the record can be redelivered. Consequently, handlers must still be idempotent to avoid duplicate side effects.

Spring Kafka organizes acknowledgement and commits more consistently, yet the designer must still select the right `AckMode` and clearly define the boundary between successful processing and commit.

### 2.4. Needing Retries, Backoff, and Dead-Letter Topics

A message may fail due to a transient fault such as a dependency outage, or an unrecoverable error such as a schema-invalid payload. These two error categories require different policies.

Spring Kafka provides mechanisms like error handlers, backoff, `DeadLetterPublishingRecoverer`, and retry topics. Depending on the model, the application can:

- Retry a bounded number of times with increasing delays for transient errors.
- Route unprocessable messages to a DLT for investigation and replay.
- Emit logs, metrics, and error metadata to support operations.
- Classify exceptions to decide which errors are retried and which go straight to the recoverer.

These mechanisms reduce custom code and make error policies more visible. They do not replace defining retry counts, wait durations, retention limits, DLT access permissions, replay procedures, and how poison or invalid messages are handled.

Consider message ordering when using retry topics. When a message is moved to a separate retry topic, later messages in the source partition may continue being processed ahead of the retrying message. If aggregate or per-key ordering is a business requirement, pick an appropriate retry and partitioning strategy and test actual ordering behavior.

### 2.5. Needing Transaction Integration in Kafka Flows

Spring Kafka supports configuring Kafka transactions and coordinating transactions with listener containers. This is helpful for consume-process-produce flows that write one or more downstream Kafka records and must ensure those Kafka writes occur in a single transaction.

However, Kafka transactions do not automatically create an atomic transaction between Kafka and an external database. If a listener updates a database and then commits a Kafka offset, a failure between the two steps can still leave inconsistent state. For flows involving databases, consider outbox/inbox, idempotency keys, or an appropriate coordination design.

### 2.6. Standardizing Observability and Testing

In a Spring application, listeners and producers integrate with existing logging, metrics, tracing, and testing setups. Spring Kafka also provides utilities in its test module to spin up test brokers or test listeners against an appropriate Kafka environment.

This helps when multiple teams operate many consumers: configuration, listener naming conventions, exception handling, and latency measurement can be standardized at the application level.

## 3. When Should You Use the Plain Kafka Client?

### 3.1. The Program Does Not Use Spring

If the application is a CLI tool, a small Java process, a library reused across multiple frameworks, or a non-Spring service, adding Spring Kafka introduces unnecessary dependencies and configuration overhead.

Using the Kafka client directly keeps the architecture simple and avoids forcing library consumers to pull Spring into their applications.

### 3.2. Needing Fine-Grained Control Over Consumer Lifecycle

The plain consumer fits when the algorithm needs direct control over operations such as:

- Manual partition assignment instead of consumer group subscription.
- Custom reactions to rebalances.
- Pausing/resuming specific partitions based on system state.
- Driving polls, processing, and commits via a custom state machine.
- Coordinating multiple data sources or multiple consumers within a custom loop.
- Managing offsets or recovery workflows with specialized requirements.

Spring Kafka offers many hooks and extension APIs, so using Spring does not eliminate control. Still, if most of the design works around the listener container or intervenes deeply in the consumer lifecycle, the plain client can make architectural intent clearer.

### 3.3. Needing a Framework-Agnostic Library

A Kafka integration library might be consumed by Spring applications, Jakarta EE applications, standalone Java programs, or other systems. If the library only needs to create producers or consumers behind a custom interface, depending directly on the Kafka client usually keeps public APIs cleaner and easier to integrate.

In this case, do not force library users to bootstrap a Spring `ApplicationContext` just to send or read a record.

### 3.4. Having Specialized Resource or Latency Requirements

The plain client can reduce overhead from the Spring context, listener containers, and integration layers. It also allows finer control over thread allocation, batching, polling, and record processing.

Still, Spring Kafka uses the Kafka Java client underneath. Do not assume the plain client is always faster or higher throughput simply because it has fewer abstractions. If performance is the deciding factor, benchmark on realistic workloads with identical producer/consumer settings, partition counts, payloads, acknowledgement levels, processing latencies, and commit strategies. Measure CPU, heap, GC, p95/p99 latency, and throughput before choosing.

### 3.5. Consumers with Specialized Processing Algorithms

Some consumers are built as dedicated coordination processes where polling, processing, checkpointing, pausing/resuming, and partition recovery are core parts of the algorithm. In those cases, a plain consumer loop can express all state and operation ordering more clearly.

This is a reasonable choice when the team genuinely needs low-level capabilities and is prepared to own rebalance handling, commits, shutdown, retries, metrics, and monitoring code.

## 4. Scenario-Based Decision Matrix

| Scenario | Typically Appropriate Choice | Reason |
|---|---|---|
| Spring Boot service publishing events with a standard producer | Spring Kafka | `KafkaTemplate` integrates with Spring configuration and lifecycle |
| Spring Boot service consuming events via a consumer group | Spring Kafka | Listener container manages polling, concurrency, and commits |
| Needing retries, DLT, and error handlers under shared policies | Spring Kafka | Built-in abstractions and mechanisms available |
| Needing Kafka transactions for consume-then-produce Kafka flows | Spring Kafka is usually convenient | Integrates transactions with templates and listener containers |
| Scheduled Java CLI without Spring | Plain client | Fewer dependencies, lightweight lifecycle |
| Kafka library that must remain framework-agnostic | Plain client | Avoids forcing Spring onto library consumers |
| Needing custom coordination of partitions, rebalances, and poll loop | Plain client or Spring Kafka with custom integration | Decide based on the degree of intervention required |
| Needing performance optimization without measurements yet | Undecided | Benchmark both under identical workloads |
| Spring app where one consumer has specialized control needs | Evaluate per consumer | Can use Spring Kafka for standard flows and the plain client where low-level control is truly required |

Both can coexist in the same system when each component has clear boundaries—for example, most services use Spring Kafka while one specialized process uses the plain Kafka client. Avoid having two components share ownership of one consumer or drive the same offset stream without explicit coordination design.

## 5. Implementing the Same Use Case Both Ways

Suppose the Billing service needs to consume `orders.created` events to create payment records. Payloads already have consistent JSON serializers/deserializers configured.

### 5.1. Using Spring Kafka

The producer can use `KafkaTemplate`:

```java
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
```

The consumer can be declared with an annotation:

```java
@Component
public class BillingOrderListener {

    private final BillingService billingService;

    public BillingOrderListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "billing-service"
    )
    public void onOrderCreated(OrderCreated event) {
        billingService.createPendingPayment(event);
    }
}
```

The example above assumes matching serializers/deserializers and a listener container configured with appropriate acknowledgement and error-handling policies. In production, the producer must observe asynchronous send results and handle send failures; never treat calling `send()` as proof the broker acknowledged the message.

When using manual acknowledgement, configure the listener with the matching `AckMode`. The example below illustrates only the acknowledgement boundary:

```java
@KafkaListener(topics = "orders.created", groupId = "billing-service")
public void onOrderCreated(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {

    billingService.createPendingPayment(record.value());
    acknowledgment.acknowledge();
}
```

Acknowledge only after the business operation succeeds. If the business method writes to a database, ensure it is safe to re-invoke, as the record may be redelivered if the application stops before the offset is committed.

### 5.2. Using the Plain Kafka Client

With the plain client, the program must manage the consumer loop itself:

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ConsumerConfig.GROUP_ID_CONFIG, "billing-service");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
          StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
          OrderCreatedDeserializer.class);

try (KafkaConsumer<String, OrderCreated> consumer =
         new KafkaConsumer<>(props)) {

    consumer.subscribe(List.of("orders.created"));

    while (!Thread.currentThread().isInterrupted()) {
        ConsumerRecords<String, OrderCreated> records =
            consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, OrderCreated> record : records) {
            billingService.createPendingPayment(record.value());
        }

        // Commit after all records in the poll have been processed successfully.
        consumer.commitSync();
    }
}
```

This is a condensed example to illustrate application responsibilities, not a complete production consumer. For real deployments, implement shutdown and wakeup handling, per-record exception handling, a rebalance listener, processing duration bounds relative to `max.poll.interval.ms`, safe offset commits, and consumer observability. `KafkaConsumer` is not thread-safe; one consumer must be owned and driven by a single thread per Kafka client rules.

Both examples solve the same business need. With Spring Kafka, business code centers on the listener; the container handles most of the loop and lifecycle. With the plain client, application code directly sees polling and commits, gaining tighter control alongside greater responsibility.

## 6. Reliability Does Not Come Automatically from the Framework

Whichever option is chosen, reliability depends on Kafka configuration, message-processing design, and how the system recovers from failures. The following decisions still must be made explicit.

### 6.1. Producers Must Know When the Broker Has Acknowledged

For critical messages, evaluate `acks`, idempotent producer settings, retries, replication factor, and `min.insync.replicas`. Producer properties govern acknowledgement criteria and producer-side duplicate suppression; replication and ISR settings belong to the broker/topic.

Spring Kafka puts producer settings into Spring properties or a producer factory. The plain client sets the same properties directly on the producer. Neither option replaces checking actual configuration and cluster health.

### 6.2. Consumers Need Commit Policies Aligned with Side Effects

If a consumer commits before finishing processing, a crash can cause messages to be skipped. If processing finishes without committing, a crash can cause messages to be redelivered. Hence, at-least-once typically requires idempotent handlers: reprocessing the same event must not create extra payments, orders, or unintended side effects.

In Spring Kafka, configure `AckMode` and error handlers. With the plain client, define explicitly which offsets are committed and under what conditions. In both cases, avoid leaving auto commit enabled casually when commits must reflect business processing outcomes.

### 6.3. Retries Must Be Bounded with a Terminal Path

Infinite retries can stall partitions, inflate latency, and exhaust resources. Specify retry counts, backoff, retryable error groups, DLT, alerts, and replay procedures. DLTs must also be monitored; moving a message to a DLT does not mean the incident is resolved.

### 6.4. Preserving Ordering per Partition

Kafka guarantees ordering within a partition. If events for the same order must be processed sequentially, use a stable key like `orderId` so they route to the same partition. Increasing concurrency does not create global ordering; multiple consumer threads process different partitions in parallel.

Retry topics, parallel processing, and partition count changes can all affect ordering observed at the business layer. Test with realistic event streams instead of assuming a listener annotation guarantees ordering on its own.

### 6.5. Transactions Have Clear Scope Boundaries

Kafka transactions are useful when atomically writing multiple Kafka records or combining consume and produce within a Kafka flow. They do not automatically cover database operations, HTTP calls, or external systems. For side effects outside Kafka, idempotency or outbox/inbox designs remain essential.

## 7. Common Mistakes When Choosing

**Choosing Spring Kafka expecting the framework to guarantee exactly-once automatically.** The framework provides transaction and acknowledgement mechanisms, but end-to-end semantics depend on configuration, transaction scope, and external systems. Explicitly document what is guaranteed and what can re-execute.

**Choosing the plain client simply assuming it is always faster.** Both options use the same Kafka Java client. Measure actual overhead before accepting the cost of owning the poll loop, rebalances, commits, and shutdown yourself.

**Using manual acknowledgement but acknowledging before processing completes.** This can commit offsets too early and forfeit reprocessing when business logic fails.

**Retrying every exception the same way.** Invalid-data errors usually are not resolved by repeated retries. Classify errors and bound retries.

**Increasing concurrency without considering partition count.** Consumer threads receive partitions only up to the partitions assigned to the group. Concurrency higher than partition count adds no useful parallelism for that topic.

**Running both a listener container and a hand-rolled consumer for the same responsibility without clear ownership.** This easily causes confusion around consumer groups, partition assignments, and offsets. Every consumer needs a single lifecycle owner and clear commit policy.

## 8. Selection Process for a New Service

Before implementing, answer these questions in order:

1. Does the service already use Spring Boot or Spring Framework? If yes, start by evaluating Spring Kafka.
2. Is the use case standard event publishing and consumer-group consumption? If yes, Spring Kafka usually cuts infrastructure boilerplate substantially.
3. Are there special requirements around partition assignment, rebalances, pause/resume, poll loop, or offset commits? If yes, verify whether Spring Kafka's hooks satisfy them; if most of the design requires managing the consumer directly, consider the plain client.
4. Is this component a framework-independent library or utility? If yes, the plain client typically keeps public APIs and dependencies leaner.
5. Is performance or resource usage the reason for choosing the plain client? If yes, build a repeatable benchmark before deciding.
6. Have delivery semantics, idempotency, retries, DLT, ordering, transactions, and monitoring been defined? If not, complete the reliability design before picking an abstraction.

A practical rule is to use Spring Kafka for standard Kafka flows inside Spring applications, since it reduces repetitive plumbing and standardizes integration. Choose the plain Kafka client when a concrete technical reason demands low-level control, framework independence, or minimal dependencies. Combining both at the system level works well, provided ownership of each producer/consumer, consumer group, and offset stream is unambiguously defined.

## 9. Documentation to Reference During Implementation

When implementing on a specific version, consult the version-matched documentation for:

- Spring for Apache Kafka: listener container configuration, `AckMode`, error handling, retry topics, DLT, and transactions.
- Spring Boot: `spring.kafka.*` properties and the Spring Kafka version managed by dependency management.
- Apache Kafka Java Client: producer configuration, consumer configuration, offset commits, rebalances, and transactions.
- Kafka broker and topic: replication, ISR, retention, partition count, and access permissions.

Prefer letting Spring Boot manage compatible dependency versions. If overriding Spring Kafka or Kafka client versions manually, verify the compatibility matrix before upgrading.
