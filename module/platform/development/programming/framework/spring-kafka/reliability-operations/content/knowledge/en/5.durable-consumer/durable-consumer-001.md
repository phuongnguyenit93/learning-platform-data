# ConsumerFactory and Listener Container

In Spring Kafka, consumers are not typically created and controlled directly inside business processing methods. Spring Kafka provides two collaborating components to manage that lifecycle: **ConsumerFactory** creates Kafka Consumers with the appropriate configuration, while the **listener container** owns the consumer, runs the poll loop, dispatches records to the listener, and coordinates offset commits, rebalancing, errors, and application shutdown.

Understanding both components helps configure consumer groups consistently, tune concurrency to the number of partitions, choose the right offset commit strategy, and handle errors without losing messages. This is the foundation of the Durable Consumer chapter in Spring Kafka.

## 1. Roles of ConsumerFactory and the Listener Container

The two components have distinct responsibilities:

- **ConsumerFactory** is the factory that creates Kafka Consumer objects. It provides bootstrap servers, group settings, deserializers, and other Kafka client properties.
- **Listener container** manages one or more Kafka Consumers. The container initializes the consumer from the ConsumerFactory, calls poll(), delivers records to the listener, coordinates acknowledgments, and manages the consumer lifecycle.
- **Message listener** is the business code that receives a record or batch of records. The listener does not own the poll loop itself.

High-level execution flow:

    Spring application context
             |
             v
    ConcurrentKafkaListenerContainerFactory
             |
             | creates listener container
             v
    ConcurrentMessageListenerContainer
             |
             | manages child containers
             v
    KafkaMessageListenerContainer
             |
             | creates Kafka Consumer via ConsumerFactory
             v
    Kafka Consumer
             |
             | poll records
             v
    Message listener
             |
             | business processing / acknowledge
             v
    Container manages offset commits

The listener container factory and ConsumerFactory are two factories at two different layers. ConcurrentKafkaListenerContainerFactory does not create KafkaConsumer directly; it uses the configured ConsumerFactory to create a container, which then creates the consumer upon startup.

## 2. How Does ConsumerFactory Create a Kafka Consumer?

ConsumerFactory defines how Kafka Consumers are created for containers. In standard configurations, Spring Kafka uses DefaultKafkaConsumerFactory. This factory accepts a configuration map and deserializers, then creates a new Kafka Consumer whenever a container needs one.

Example of creating a ConsumerFactory for a String key and a JSON value deserialized into OrderCreated:

~~~java
@Bean
public ConsumerFactory<String, OrderCreated> consumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    JsonDeserializer<OrderCreated> valueDeserializer =
            new JsonDeserializer<>(OrderCreated.class);

    valueDeserializer.addTrustedPackages("com.example.orders");

    return new DefaultKafkaConsumerFactory<>(
            props,
            new StringDeserializer(),
            valueDeserializer
    );
}
~~~

This is an illustrative example; in production, bootstrap servers and security credentials should come from environment configuration or a secret store. Only add necessary trusted packages for the JSON deserializer. Do not widen trusted packages arbitrarily when data comes from untrusted sources.

ConsumerFactory is not a single shared Kafka Consumer across all listeners. Each container or child container creates its own consumer. A Kafka Consumer is not thread-safe; never share the same consumer instance across multiple business processing threads.

### 2.1. Important Consumer Property Groups

| Property | Purpose | Operational Notes |
|---|---|---|
| bootstrap.servers | List of brokers for initial client connection | Should configure multiple reachable broker addresses |
| group.id | Consumer group name | A listener can override the group ID at the annotation level |
| key/value.deserializer | Converts bytes into application data types | Must be compatible with the producer's serializer |
| enable.auto.commit | Enables/disables automatic offset commits by the Kafka client | Usually disabled so the container manages acknowledgments |
| auto.offset.reset | Behavior when the group has no valid offset | earliest and latest can lead to different ranges of read data |
| max.poll.records | Maximum number of records returned in a single poll | Affects processing time of a batch and commits |
| max.poll.interval.ms | Maximum interval between polls before the group considers the consumer inactive | Must accommodate the longest processing time |
| session.timeout.ms | Time to detect a disconnected consumer in the group protocol | Coordinates with heartbeat and broker configuration |
| isolation.level | How transactional records are read | read_committed skips records belonging to uncommitted transactions |
| fetch.min.bytes / fetch.max.wait.ms | Conditions for batching data during fetch | Can affect latency and throughput |

Do not copy every property from a sample configuration without understanding its impact. For example, increasing max.poll.records can increase throughput if the listener processes fast, but it also makes a poll batch take longer and increases the risk of exceeding max.poll.interval.ms.

### 2.2. Disabling Auto Commit When the Container Manages Offsets

When using a Spring Kafka listener container, let the container coordinate offset commits. Consumer configuration typically sets enable.auto.commit=false. The container's acknowledgment mode then determines when commits occur.

If auto commit is enabled, the Kafka client may commit on a schedule while the listener has not finished processing. When a consumer fails mid-way, an advanced offset can cause unprocessed records to be skipped. For systems requiring at-least-once delivery, disabling auto commit and committing after successful processing is the standard approach.

Spring Kafka containers may automatically set auto commit to false if the property is not configured, depending on the version and how ConsumerFactory is created. Even so, declaring it explicitly makes the configuration clearer and avoids relying on defaults.

### 2.3. Deserializers and Data Types

The deserializer is part of the ConsumerFactory configuration. If the producer sends JSON but the consumer uses StringDeserializer for the value, the application receives a JSON string and must parse it manually. If JsonDeserializer is used, Spring Kafka can convert the payload into the specified Java type.

Align schemas, type mappings, and trusted packages across producers and consumers. Deserialization errors occur before the listener receives a normal business object; therefore, configure ErrorHandlingDeserializer when you want to forward deserialization errors to the container's error handling mechanism.

Example of configuring ErrorHandlingDeserializer with a JSON value:

~~~java
props.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    ErrorHandlingDeserializer.class
);
props.put(
    ErrorHandlingDeserializer.VALUE_DESERIALIZER_CLASS,
    JsonDeserializer.class
);
~~~

The delegate configuration and target type must match your Spring Kafka version, serializer, and application schema. Do not assume all data errors appear as exceptions inside the listener; errors at the deserialization layer must be forwarded via the appropriate configuration.

## 3. What Does the Listener Container Do?

The listener container is the component that controls the consumer lifecycle. The container creates the consumer, subscribes to topics or assigns partitions, runs the poll loop, invokes the listener, manages acknowledgments, commits offsets, and coordinates with the consumer group during rebalances.

Spring Kafka has two basic container types:

- **KafkaMessageListenerContainer** manages a single Kafka Consumer and processes records on one consumer thread.
- **ConcurrentMessageListenerContainer** manages multiple child KafkaMessageListenerContainers. Each child container has its own consumer and thread.

ConcurrentMessageListenerContainer is typically created via ConcurrentKafkaListenerContainerFactory. When concurrency is 3, the factory creates a parent container managing three child containers; each child owns one consumer.

Diagram:

    ConcurrentMessageListenerContainer
       |
       +-- child container 1 --> Consumer 1 --> poll/listener thread 1
       |
       +-- child container 2 --> Consumer 2 --> poll/listener thread 2
       |
       +-- child container 3 --> Consumer 3 --> poll/listener thread 3

Consumers in the same group divide the topic's partitions according to the group assignment mechanism. A partition is assigned to at most one consumer in the same group at any given time. If the number of consumers exceeds the number of partitions, some consumers will have no partitions to read.

## 4. Configuring ConcurrentKafkaListenerContainerFactory

ConcurrentKafkaListenerContainerFactory is the factory commonly used with the @KafkaListener annotation. It combines ConsumerFactory with default listener container properties such as concurrency, acknowledgment mode, error handler, and batch listener.

Example of configuring a factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                CommonErrorHandler commonErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.setCommonErrorHandler(commonErrorHandler);

    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

The default bean name commonly used in @KafkaListener configuration is kafkaListenerContainerFactory. If the application has multiple types of listeners, you can create multiple factories with distinct names and select them via the containerFactory attribute on the annotation.

Example of a listener using a dedicated factory:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-service",
    containerFactory = "orderListenerContainerFactory"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

The factory is not where message processing logic is written. It defines how containers are created. The listener remains the method that receives messages and calls the business service.

### 4.1. Using Spring Boot Auto-Configuration

Spring Boot can automatically create a default ConsumerFactory and ConcurrentKafkaListenerContainerFactory from spring.kafka properties. Example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.OrderCreated
        spring.json.trusted.packages: com.example.orders
    listener:
      ack-mode: record
      concurrency: 3
~~~

The properties above are illustrative examples. Verify your Spring Boot/Spring Kafka version and actual application configuration. When declaring a factory bean manually with the same name as the default bean, the application may replace or alter the auto-configuration process. Do not manually declare a factory while assuming all auto-configured properties still apply identically.

### 4.2. Multiple Factories for Multiple Listener Types

An application may have regular record listeners, batch listeners, or listeners using separate transactions. When different policies are needed, create factories with clear names:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}

@Bean
public ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
        auditBatchListenerContainerFactory(
                ConsumerFactory<String, AuditEvent> auditConsumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, AuditEvent>();

    factory.setConsumerFactory(auditConsumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(2);

    return factory;
}
~~~

The batch listener selects the corresponding factory:

~~~java
@KafkaListener(
    topics = "audit.events",
    containerFactory = "auditBatchListenerContainerFactory"
)
public void consumeBatch(List<AuditEvent> events) {
    auditService.processBatch(events);
}
~~~

Factories can share some configuration, but ConsumerFactory must have deserializers matching the corresponding data types and topics. Do not share a single factory merely because two listeners connect to the same cluster if they require different data types or processing semantics.

## 5. @KafkaListener and the Created Container

When Spring starts up and detects a method annotated with @KafkaListener, KafkaListenerAnnotationBeanPostProcessor processes the annotation and registers the endpoint with KafkaListenerEndpointRegistry. The registry uses the specified container factory to create the listener container.

High-level process:

1. Spring creates the bean containing the @KafkaListener method.
2. The annotation processor detects the endpoint and reads topic, group ID, concurrency, containerFactory, and other attributes.
3. The endpoint is registered with KafkaListenerEndpointRegistry.
4. The registry uses the factory to create the listener container.
5. The container starts, creates the consumer via ConsumerFactory, and begins polling.
6. Records are delivered to the listener method.

Example:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "order-created-listener",
        topics = "orders.created",
        groupId = "order-service"
    )
    public void onOrderCreated(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

Here, the onOrderCreated method is the message listener. The container handles fetching records and invoking the method. There is no need to create KafkaConsumer manually or write a poll loop inside the listener.

### 5.1. Choosing a Group ID

group.id identifies the consumer group coordinating partition reads and storing offsets. Instances in the same group share partitions among themselves. Different groups read independently from the same topic and maintain separate offsets.

The group ID can be set in ConsumerFactory configuration or overridden in the @KafkaListener annotation. If a listener needs a different group from another listener, declare the group ID explicitly to avoid accidentally sharing offsets and assignments.

### 5.2. Selecting Topics, Topic Patterns, or Specific Partitions

Listeners can subscribe by topic name, pattern, or specific partition assignment. Subscribing by topic allows the Kafka group coordinator to distribute partitions. Explicit partition assignment is suitable for certain tasks with a fixed scope, but understand that this assignment style differs from standard automatic subscription and rebalancing.

Example of assigning specific partitions:

~~~java
@KafkaListener(
    topicPartitions = @TopicPartition(
        topic = "orders.created",
        partitions = { "0", "1" }
    ),
    groupId = "order-replay"
)
public void replay(OrderCreated event) {
    replayService.process(event);
}
~~~

When using explicit partition assignment, manage the partition scope and topic scalability carefully. Avoid hard-coding partitions in production applications if the partition count may change without a corresponding update process.

## 6. Tuning Concurrency to Partitions

Concurrency is the number of consumer threads managed by ConcurrentMessageListenerContainer. Each child container creates a separate Kafka Consumer. Increasing concurrency can increase parallel processing capacity, but it only helps when the topic has enough partitions and downstream systems have sufficient capacity.

Example for a topic with 6 partitions:

| Concurrency | Consumers with Partitions | Impact |
|---:|---:|---|
| 1 | 1 consumer receives 6 partitions | Single processing thread; low parallelism |
| 3 | 3 consumers share 6 partitions | Can process up to 3 streams in parallel |
| 6 | 6 consumers, each can receive 1 partition | Can utilize all partitions in parallel |
| 8 | At most 6 consumers receive partitions | At least 2 consumers have no partitions |

The number of partitions, the number of consumers in the group, and the partition assignment strategy determine actual parallelism. If one partition has slow records, the consumer handling that partition can become a bottleneck. Increasing concurrency beyond the partition count does not cause a single partition to be processed concurrently by multiple consumers in the same group.

Concurrency can be configured on the factory:

~~~java
factory.setConcurrency(4);
~~~

Or overridden for a single listener:

~~~java
@KafkaListener(
    id = "order-listener",
    topics = "orders.created",
    groupId = "order-service",
    concurrency = "4"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

The annotation's concurrency is specific to that endpoint. Check the total number of consumers across all application instances: if there are 3 instances and each instance has concurrency 4, the group can have 12 consumers in total. This consumer count must be compared against the partition count.

### 6.1. Record Ordering and Partitions

Kafka guarantees record ordering within a single partition. A consumer group assigns each partition to at most one consumer at a time, so records in a partition are delivered to a consumer in offset order.

However, if a listener processes asynchronously and returns before the work finishes, the completion order of side effects may differ from the record reception order. Similarly, increasing concurrency does not guarantee global ordering across partitions.

If business logic requires ordering by orderId, the producer should use orderId as the key so records for the same order are routed to the same partition. The consumer processes sequentially within the partition or applies version/sequence checks when processing asynchronously.

### 6.2. Rebalancing When Consumer Count Changes

When consumers join/leave the group or topic partitions change, Kafka performs a rebalance to redistribute partitions. During a rebalance, processing may be temporarily paused. The listener container coordinates with the consumer group and handles assignment callbacks/revocations according to its lifecycle.

When increasing concurrency or deploying additional instances, monitor rebalance counts, rebalance duration, and consumer lag. Starting many consumers simultaneously or misconfiguring poll settings can cause assignment churn and increase latency.

## 7. Acknowledgment Modes and Offset Commits

The container determines when to commit offsets via AckMode. This is one of the most important configurations for controlling replay behavior and the risk of message loss.

Common modes:

| AckMode | Commit Timing | Use Case |
|---|---|---|
| RECORD | After the listener successfully processes each record | Record listener, needing per-record commit boundaries |
| BATCH | After all records in the poll batch are successfully processed | Common default for record listener containers |
| TIME | When the configured time elapses and container processing conditions are met | Time-based commit batching |
| COUNT | When the configured record count is reached | Count-based commit batching |
| COUNT_TIME | Combines time and record count conditions | Balances commit frequency |
| MANUAL | Listener actively acknowledges; container coordinates commit | Application controls acknowledgment timing |
| MANUAL_IMMEDIATE | Acknowledge can commit immediately when called on the consumer thread | Requires strict control over the thread calling acknowledge |

With AckMode.RECORD, the container commits the offset after the listener completes the record successfully. With BATCH, commits happen after the records from a poll are successfully processed. If a record fails and is not recovered, the error handler decides how to proceed; do not assume the entire batch's offsets will be committed automatically.

Example configuring RECORD:

~~~java
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.RECORD);
~~~

Configuration in Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

### 7.1. Manual Acknowledgment

When the listener needs to decide when to acknowledge, it can accept an Acknowledgment parameter:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-service"
)
public void consume(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    orderService.process(event);
    acknowledgment.acknowledge();
}
~~~

Only call acknowledge() after the business task has completed durably. If the listener ACKs before the database commits and then the database transaction fails, the offset may advance and the record will not be redelivered.

With MANUAL, the container receives the acknowledgment and coordinates the commit according to that mode's semantics. With MANUAL_IMMEDIATE, the commit can occur immediately if acknowledge is called on the consumer thread. If acknowledgment is called from another thread, the action may be queued for the consumer thread to process. Therefore, do not hand off Acknowledgment to an executor arbitrarily without understanding thread constraints and commit modes.

### 7.2. Sync and Async Commits

The container can use synchronous or asynchronous commits depending on configuration. Synchronous commits wait for a broker response, making commit errors easy to observe, though they can increase latency. Asynchronous commits reduce waiting time, but commit errors must be handled via callbacks/logging and can be harder to observe.

The container's syncCommits property and commit callbacks can be used to tune how commits behave. The choice must be based on latency, throughput, and durability requirements. Regardless of the choice, consumer design must still tolerate record redelivery if side effects completed but the offset was not committed.

## 8. Record Listeners and Batch Listeners

The container can invoke the listener one record at a time or pass the entire batch of records from a poll to the listener.

**Record listener** receives a single record:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

**Batch listener** receives a list of records:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consumeBatch(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

To configure a batch listener, enable batch mode on the factory:

~~~java
factory.setBatchListener(true);
~~~

Batch listeners can reduce method invocation overhead and leverage batch processing at the database layer. In return, a batch may contain many records and take longer to process. Tune max.poll.records, max.poll.interval.ms, and batch size limits to match downstream capacity.

When a record in a batch fails, identifying the failing record and handling the rest is more complex than with a record listener. The error handler can use information about the failing index/record if the listener throws BatchListenerFailedException as supported by Spring Kafka. Design batch operations to be rollback-capable or idempotent to avoid hard-to-recover partial updates.

Do not switch to batch mode solely for throughput without evaluating error semantics, database transactions, and per-record processing capability.

## 9. Error Handler Attached to the Listener Container

The listener container is where exceptions from the listener are caught and handed to the error handling mechanism. In modern Spring Kafka, CommonErrorHandler is the general abstraction; DefaultErrorHandler is the implementation commonly used for record listeners and supports retry/backoff along with a recoverer.

Example configuring an error handler with DeadLetterPublishingRecoverer:

~~~java
@Bean
public CommonErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 3L)
            );

    handler.addNotRetryableExceptions(
            IllegalArgumentException.class
    );

    return handler;
}
~~~

Then attach the handler to the factory:

~~~java
factory.setCommonErrorHandler(commonErrorHandler);
~~~

Illustrative examples must be adjusted for your serializers, DLT topics, and Spring Kafka version. The default recoverer typically routes records to a topic suffixed with .DLT while preserving the corresponding partition; ensure the destination topic exists and has enough partitions for that routing.

The error handler can retry transient errors, skip/recover non-retryable errors, or send records to a DLT. Set limits on retry attempts and backoff. Blocking retries can hold up a partition during the wait; retry topics are suitable when longer delays are needed, though they can change processing order.

Deserialization errors occur before the listener receives a normal object. Use ErrorHandlingDeserializer to pass deserialization error details into the container's error handling mechanism. If not configured properly, deserialization errors can prevent the consumer from continuing as desired.

## 10. Container Lifecycle and KafkaListenerEndpointRegistry

Containers have their own lifecycle: start, pause, resume, and stop. With @KafkaListener, Spring typically registers the container in KafkaListenerEndpointRegistry. The registry allows the application to look up and control containers by ID.

Example of pausing and resuming a listener:

~~~java
@Component
public class ListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrderListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("order-created-listener");

        if (container != null) {
            container.pause();
        }
    }

    public void resumeOrderListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("order-created-listener");

        if (container != null) {
            container.resume();
        }
    }
}
~~~

The listener must have a corresponding id:

~~~java
@KafkaListener(
    id = "order-created-listener",
    topics = "orders.created",
    groupId = "order-service"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

Pause and resume can be useful during maintenance or when downstream needs load shedding. The container executes pause/resume safely via the consumer thread mechanism. Never call KafkaConsumer.pause(), poll(), or commitSync() directly from another business thread; Kafka Consumer is not thread-safe and the container owns the consumer lifecycle.

The autoStartup and id attributes on @KafkaListener control whether the listener starts with the application context and identify the container. For manually created containers, the application can manage the lifecycle directly. For annotation-based containers, use the registry rather than holding references to the consumer.

## 11. Container Properties and Poll Limits

Beyond acknowledgment mode, ContainerProperties provides many operational settings:

- pollTimeout: time to wait for data during each poll.
- idleBetweenPolls: pause duration between polls in certain scenarios.
- syncCommits: synchronous commit option.
- ackMode: acknowledgment policy.
- shutdownTimeout: time to wait for the container to stop completely.
- monitorInterval and noPollThreshold: help detect a container that is not polling within a configured threshold.
- missingTopicsFatal: behavior when a required topic does not yet exist, depending on version/configuration.

Example:

~~~java
ContainerProperties properties = factory.getContainerProperties();
properties.setPollTimeout(3_000);
properties.setSyncCommits(true);
properties.setShutdownTimeout(15_000);
properties.setAckMode(ContainerProperties.AckMode.RECORD);
~~~

Not every property needs customization. Keeping sensible defaults is usually easier to operate. Only change them when you have a specific, measurable goal.

### 11.1. max.poll.interval.ms and Processing Time

Kafka requires consumers to keep polling within max.poll.interval.ms. If a listener takes too long to process a batch and the container fails to poll again within this deadline, the group may consider the consumer inactive and rebalance partitions.

For example, if max.poll.records is 500 and each record takes an average of 100 ms, the theoretical processing time of a single batch can already reach 50 seconds, excluding database or network time. If max.poll.interval.ms is smaller than the actual total processing time, the consumer may repeatedly be evicted from the group.

Evaluate the distribution of processing times, not just the average time. Some records may call slow services or require retries. Tune max.poll.records, max.poll.interval.ms, concurrency, and batch design to keep poll cadence stable.

### 11.2. Consumer Lag and Processing Speed

Consumer lag is the distance between the latest offset in a partition and the offset committed by the group. Growing lag can result from producers sending faster than consumers process, slow downstream systems, low concurrency, repeated rebalances, or retry errors.

Increasing concurrency can help if there are unutilized partitions and downstream has enough processing capacity. If every partition already has a consumer, optimize processing time, fetch/batch sizing, databases, or dependent services. Increasing concurrency beyond the partition count will not automatically reduce lag.

## 12. Transactions and the Listener Container

Spring Kafka supports listener containers participating in Kafka transactions. When the container is configured with an appropriate transaction manager, record processing and sending output Kafka records can occur within a single Kafka transaction. Input offsets can be sent in the same transaction to ensure atomic consume-process-produce within the scope of Kafka.

When the transaction commits, output records and offsets are committed together. When the transaction aborts, output records are invisible to read_committed consumers and input offsets do not advance as a successful processing attempt.

Container transactions do not automatically cover databases or HTTP APIs. If the listener updates a database and then sends to Kafka, an outbox/inbox or appropriate coordination mechanism is required. If the database commits but the Kafka transaction aborts, the database side effect remains and the record may be redelivered.

Transaction manager and listener container configuration varies by Spring Kafka version and the type of transaction used. Use the exact API of your current dependency; do not copy transaction configuration from another version without verifying.

## 13. Container Customization and Observability

When a common policy needs to be applied to containers created from a factory, you can use a container customizer or corresponding extension points in your Spring Kafka version.

Conceptual example using a customizer to attach per-container properties:

~~~java
factory.setContainerCustomizer(container -> {
    log.info("Creating Kafka listener container: {}", container);
});
~~~

Depending on the version, the customizer API and callback timing may vary. Use customizers for shared infrastructure configuration such as metrics, event listeners, or container properties; do not stuff business logic into the factory.

Monitor the following signals:

| Group | Signals to Monitor |
|---|---|
| Consumer group | Lag, member count, partition assignment, and rebalances |
| Listener container | Running state, pause/resume, poll duration |
| Business processing | Throughput, processing duration, exception rate |
| Commit | Commit latency, commit failures, and redelivery count |
| Retry/DLT | Retry record count, DLT count, failed record age |
| Broker/client | Fetch latency, request errors, network, and heartbeat |

Logs should include topic, partition, offset, key, group ID, and eventId for traceability. Avoid logging sensitive payloads. A running container does not necessarily mean it is processing records; correlate lag, poll activity, and throughput.

## 14. Common Configuration Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using the wrong ConsumerFactory for a different payload type | Deserialization fails or listener receives unexpected type | Create a factory with the right deserializer |
| Thinking ConcurrentKafkaListenerContainerFactory creates KafkaConsumer directly | Misunderstanding lifecycle and thread management | The container creates consumers via ConsumerFactory |
| Setting concurrency higher than partition count | Some consumers receive no partitions | Choose concurrency based on partition and instance counts |
| Enabling auto commit while listener processing takes long | Offsets may advance before business work finishes | Disable auto commit and choose AckMode |
| ACKing before database commit | Work may be lost when the database fails | ACK after side effects are durable |
| Listener processing takes longer than max.poll.interval.ms | Rebalances and record redeliveries | Tune poll, batch, timeout, and processing |
| Calling KafkaConsumer from a thread outside the container | Violates thread-safety | Use container/registry APIs |
| Infinite retries in the error handler | Partitions can get blocked and lag grows | Finite backoff, error classification, and DLT |
| Choosing batch listener without designing per-record failure handling | Hard to determine which part was processed | Design transactions/idempotency and batch error handling |
| Unintentionally sharing a group ID | Listeners split partitions and offsets with each other | Set group ID according to processing purpose |
| Treating zero consumer lag as proof of no message loss | Offsets may have committed too early | Reconcile business outcomes against event sources |

## 15. Reference Configuration for a Production Listener

The example below combines ConsumerFactory, ConcurrentKafkaListenerContainerFactory, and a record listener. Concurrency, poll, and acknowledgment values must be tuned according to partition count, processing time, and SLA.

~~~java
@Configuration
@EnableKafka
public class OrderKafkaConfiguration {

    @Bean
    public ConsumerFactory<String, OrderCreated> orderConsumerFactory(
            KafkaProperties kafkaProperties) {

        Map<String, Object> props =
                new HashMap<>(kafkaProperties.buildConsumerProperties());

        props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);

        return new DefaultKafkaConsumerFactory<>(
                props,
                new StringDeserializer(),
                new JsonDeserializer<>(OrderCreated.class)
        );
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> orderConsumerFactory,
                    CommonErrorHandler commonErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(orderConsumerFactory);
        factory.setConcurrency(3);
        factory.setCommonErrorHandler(commonErrorHandler);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

The buildConsumerProperties method signature varies across Spring Boot versions; this example must be adjusted to match your application's dependencies. If not using KafkaProperties, you can build the configuration map manually as shown in earlier examples.

Listener:

~~~java
@Component
public class OrderCreatedListener {

    private final OrderService orderService;

    public OrderCreatedListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "order-created-listener",
        topics = "orders.created",
        containerFactory = "orderListenerContainerFactory"
    )
    public void onMessage(OrderCreated event) {
        orderService.processIdempotently(event);
    }
}
~~~

In this example, the service processes idempotently because a record may be redelivered if side effects completed but the offset was not committed. The error handler should be configured to retry transient errors and route unrecoverable errors to a DLT according to the application's policy.

## 16. Design Principles

- Use ConsumerFactory to declare how Kafka Consumers are created: connections, groups, deserializers, and client properties.
- Use the listener container to manage consumers, the poll loop, acknowledgments, commits, rebalances, and lifecycle.
- Use ConcurrentKafkaListenerContainerFactory to standardize container creation for @KafkaListener.
- Choose concurrency based on partition count, instance count, and downstream capacity.
- Disable auto commit when the container is responsible for committing offsets; choose AckMode according to required semantics.
- Only acknowledge after business work has completed durably.
- Use batch listeners when business logic supports batch processing and has a way to recover from partial batch failures.
- Attach an appropriate CommonErrorHandler, limit retries, and configure a DLT for unprocessable records.
- Tune max.poll.records and max.poll.interval.ms according to actual processing time.
- Use KafkaListenerEndpointRegistry to control listener containers; never access KafkaConsumer directly from external threads.
- Design idempotent consumers to safely handle redelivered records.
- Monitor lag, rebalances, commits, retries, and DLT to detect issues before they impact business operations.

ConsumerFactory and the listener container form the infrastructure layer governing Kafka consumption in Spring. The factory defines how consumers are created and configured; the container governs how consumers are run, polled, committed, and recovered. When both layers are properly configured to match business semantics, listeners can focus on event processing while Spring Kafka manages the lifecycle and interaction with the consumer group.
