# ConcurrentKafkaListenerContainerFactory

## Lesson objectives

In the **Listener container** chapter, this lesson explains the role and configuration of `ConcurrentKafkaListenerContainerFactory` in Spring Kafka. The factory is where listener containers are created for endpoints declared with `@KafkaListener`; it connects consumer configuration with how listeners receive records, handle offsets, manage concurrency, and deal with errors.

**SPRING_KAFKA_MESSAGING** focuses on building applications that send and receive Kafka events using Spring Kafka, KafkaTemplate, and @KafkaListener; it also helps learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-letter topics, transactions, exactly-once semantics, concurrency, and testing. In that architecture, the factory determines how listener containers are created and operated.

After this lesson, learners will be able to:

- Distinguish between `ConcurrentKafkaListenerContainerFactory`, `ConcurrentMessageListenerContainer`, `KafkaMessageListenerContainer`, and `ConsumerFactory`.
- Understand how `@KafkaListener` is wired to a factory.
- Configure the consumer factory, concurrency, and acknowledgment mode.
- Create dedicated factories for record listeners and batch listeners.
- Configure error handlers, converters, and container properties at the right level.
- Manage listener container lifecycles through the registry.
- Choose an appropriate factory for each group of listeners and test the configuration.

## 1. What is ConcurrentKafkaListenerContainerFactory?

`ConcurrentKafkaListenerContainerFactory<K, V>` is a Spring Kafka factory used to create `ConcurrentMessageListenerContainer<K, V>` instances for listener endpoints, typically declared via `@KafkaListener`.

The factory gathers settings to apply when creating containers, such as:

- The `ConsumerFactory` used to create Kafka consumers.
- The number of child consumer containers via concurrency.
- Record or batch consumption mode.
- How offsets are acknowledged and committed.
- The error handler used when a listener fails to process a message.
- The message converter and other container customizations.

The factory does not directly poll Kafka and is not a consumer. It creates containers with the chosen configuration; the container itself manages the consumer lifecycle and invokes the listener method.

~~~mermaid
flowchart TD
    A["@KafkaListener endpoint"] --> B["ConcurrentKafkaListenerContainerFactory"]
    B --> C["ConcurrentMessageListenerContainer"]
    C --> D["KafkaMessageListenerContainer 1"]
    C --> E["KafkaMessageListenerContainer 2"]
    C --> F["KafkaMessageListenerContainer 3"]
    D --> G["Kafka Consumer 1"]
    E --> H["Kafka Consumer 2"]
    F --> I["Kafka Consumer 3"]
    G --> J["Kafka Broker"]
    H --> J
    I --> J
~~~

In the diagram, the factory creates a concurrent container. That container manages child containers; each child container creates and manages its own Kafka consumer.

## 2. Distinguishing related components

These classes have similar names but different responsibilities.

| Component | Responsibility |
|---|---|
| `ConcurrentKafkaListenerContainerFactory<K, V>` | Creates concurrent listener containers from configuration |
| `ConcurrentMessageListenerContainer<K, V>` | Manages one or more child containers for concurrent consumption |
| `KafkaMessageListenerContainer<K, V>` | Manages a single Kafka consumer and its poll/listener loop |
| `ConsumerFactory<K, V>` | Creates Kafka consumers with configuration, deserializers, and corresponding settings |
| `@KafkaListener` | Declares a listener endpoint and handler method |
| `KafkaListenerEndpointRegistry` | Manages the lifecycle of containers created from annotated endpoints |

You can remember this through the flow:

1. The application declares `@KafkaListener`.
2. Spring processes the annotation and creates a listener endpoint.
3. The endpoint selects a container factory.
4. The factory creates a concurrent message listener container.
5. The container creates child containers according to concurrency.
6. Each child container creates a Kafka consumer from ConsumerFactory.
7. The consumer subscribes to topics, joins the group, polls records, and invokes the listener.

### 2.1. A factory is not ConsumerFactory

These two factories serve two different layers:

- `ConsumerFactory` creates Kafka client consumer objects.
- `ConcurrentKafkaListenerContainerFactory` creates Spring listener containers to manage those consumers.

A listener factory can use a ConsumerFactory matching the key/value types and consumer settings. If different listener groups need different deserializers, groups, or security settings, you can declare multiple ConsumerFactory and container factory beans.

### 2.2. A factory is not a container

A factory is an object that configures and creates containers. A container is the runtime object in the application that performs start, stop, pause, resume, and consumer management.

One factory can create multiple containers for multiple `@KafkaListener` methods. Each endpoint has its own container, even though endpoints can share a factory.

## 3. Why does Spring Kafka need a container factory?

Without a factory, every listener would have to handle many details about consumers, polling, offset commits, errors, and lifecycle on its own. A container factory standardizes these settings so listeners can share one configuration.

For example, a Billing application might have listeners that:

- Receive `commerce.order.created`.
- Receive `commerce.payment.captured`.
- Receive `commerce.order.cancelled`.

Listeners can share one factory if they have the same data types, deserialization, acknowledgment, and error policies. If one listener needs batching, different concurrency, or a custom retry policy, a separate factory should be considered.

A factory helps:

- Centralize consumer container configuration.
- Reuse settings across listeners.
- Separate listener groups by processing style.
- Reduce boilerplate configuration code.
- Control concurrency and acknowledgment consistently.
- Simplify testing endpoint configuration.

Sharing a factory does not mean listeners share a single consumer. Each endpoint gets its own container and consumer. If two endpoints subscribe to the same topic and use the same group ID, their consumers join the same group and share partitions; they do not each receive an independent copy of every record. If each listener needs to read the entire stream independently, separate group IDs must be used.

## 4. Default factory name and custom factories

Spring Kafka uses the default name `kafkaListenerContainerFactory` if the `containerFactory` attribute of `@KafkaListener` is not specified.

Example of a listener using the default factory:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

If the application has a factory bean named `kafkaListenerContainerFactory`, the endpoint can use that factory by default.

When declaring a custom-named factory, specify its name with the `containerFactory` attribute:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

The name in `containerFactory` must match the Spring bean name exactly. If the name is wrong or the bean is not registered, the endpoint cannot create its container properly.

### 4.1. Spring Boot and Spring Framework

In plain Spring Framework configuration, you must enable listener annotation infrastructure, typically via `@EnableKafka`, and declare the factory bean.

With Spring Boot, auto-configuration can provide a default consumer factory and listener container factory when conditions match. When declaring a custom factory bean, check auto-configuration conditions and the bean names in use so you do not accidentally override the default configuration.

Do not declare multiple beans with the same name or rely on initialization order to determine which factory is used. Give them clear names and specify `containerFactory` explicitly when the application has multiple configurations.

## 5. Configuring a basic ConcurrentKafkaListenerContainerFactory

Suppose the application receives `OrderCreated` events from the `commerce.order.created` topic.

Declare the event:

~~~java
public record OrderCreated(
    String orderId,
    String customerId,
    long total
) {
}
~~~

Configure ConsumerFactory and container factory:

~~~java
@Configuration
@EnableKafka
public class KafkaListenerConfiguration {

    @Bean
    public ConsumerFactory<String, OrderCreated> orderConsumerFactory() {
        Map<String, Object> properties = new HashMap<>();

        properties.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "billing-service"
        );
        properties.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest"
        );

        return new DefaultKafkaConsumerFactory<>(
            properties,
            new StringDeserializer(),
            new JsonDeserializer<>(OrderCreated.class, false)
        );
    }

    @Bean(name = "ordersKafkaListenerContainerFactory")
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> orderConsumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(orderConsumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Key points to understand:

- `ConsumerFactory<String, OrderCreated>` creates consumers with String keys and OrderCreated values.
- `StringDeserializer` converts keys from bytes to String.
- `JsonDeserializer` converts JSON values into OrderCreated.
- `setConsumerFactory(...)` attaches the ConsumerFactory to the container factory.
- `setConcurrency(3)` requests each concurrent container created from the factory to manage three child consumer containers.
- `AckMode.RECORD` selects committing after the listener finishes processing each record according to the container's mechanism.

The example uses a JSON deserializer with a fixed value type. In real applications, align producer-side serializer settings, consumer-side deserializer settings, trusted packages, or type mappings according to the system's JSON strategy.

In plain Spring Framework, `@EnableKafka` activates `@KafkaListener` processing. In Spring Boot, verify whether annotation infrastructure is already auto-configured for the version in use before adding manual enabling configuration.

### 5.1. Listener selecting a factory

~~~java
@Service
public class OrderEventListener {

    @KafkaListener(
        topics = "commerce.order.created",
        groupId = "billing-service",
        containerFactory = "ordersKafkaListenerContainerFactory"
    )
    public void handle(OrderCreated event) {
        // Billing business processing.
    }
}
~~~

When Spring registers the endpoint, it looks up the factory bean named `ordersKafkaListenerContainerFactory`, creates the container, and starts the consumers according to the application lifecycle.

## 6. Configuring concurrency

Concurrency is the number of child containers/consumers managed by one `ConcurrentMessageListenerContainer`. Each child container uses its own Kafka consumer.

Concurrency can be set on the factory:

~~~java
factory.setConcurrency(3);
~~~

When set there, endpoints using this factory receive a default concurrency of 3 unless overridden by an endpoint-specific configuration.

Concurrency can also be set directly on the listener:

~~~java
@KafkaListener(
    id = "order-created-listener",
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "ordersKafkaListenerContainerFactory",
    concurrency = "5"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

The annotation's `concurrency` attribute is a String to support placeholders or expressions. When declared, this value is used for that endpoint instead of the default concurrency from the factory.

### 6.1. Concurrency is limited by partitions

Within the same consumer group, a partition at any given time is assigned to at most one consumer.

Example for a topic with 4 partitions:

| Concurrency | Consumers created | Maximum consumers assigned partitions | Outcome |
|---:|---:|---:|---|
| 1 | 1 | 1 | One consumer receives all 4 partitions |
| 2 | 2 | 2 | Two consumers can split the 4 partitions |
| 4 | 4 | 4 | Up to one consumer per partition can be achieved |
| 6 | 6 | 4 | At least 2 consumers have no partitions |

If the application runs multiple instances, the total number of consumers in the group equals the sum of concurrency across instances. For example, two instances with concurrency 3 each create 6 consumers in total in the group.

Increasing concurrency beyond the partition count does not increase useful parallelism for that topic. Consider processing time, CPU, database connection pools, and downstream load before increasing the consumer count.

### 6.2. Concurrency and ordering

Kafka preserves ordering within a single partition. When partitions are processed by different consumers, there is no global ordering across partitions.

If events for the same order must be processed in order, the producer should use the order ID as the key so related events are routed to the same partition by the appropriate partitioner.

Do not offload record processing to another thread pool and acknowledge immediately if business logic requires preserving order and ensuring processing finishes before commit. When processing asynchronously, the application must design corresponding synchronization, error handling, and acknowledgment mechanisms.

## 7. Configuring acknowledgment and offset commits

The container factory provides access to `ContainerProperties`, including the acknowledgment mode.

Example:

~~~java
factory.getContainerProperties()
    .setAckMode(ContainerProperties.AckMode.RECORD);
~~~

Some common AckModes:

| AckMode | High-level behavior |
|---|---|
| RECORD | Commits after the listener finishes processing each record |
| BATCH | Commits after finishing processing a polled batch |
| TIME | Commits when the configured time interval elapses and related records have been processed |
| COUNT | Commits when the configured record count is reached |
| COUNT_TIME | Combines time and record count conditions |
| MANUAL | Listener explicitly acknowledges; the container commits according to the mode's semantics |
| MANUAL_IMMEDIATE | Requests an immediate commit when acknowledge is called on the consumer thread |

`RECORD` fits record listeners. For batch listeners, choose an acknowledgment mode compatible with batch semantics, typically `BATCH` or an appropriate manual mode.

To let the container manage commits, configure the consumer with `enable.auto.commit=false`. Spring Kafka listener containers usually disable auto-commit by default in modern versions, but configuring it explicitly makes the application's intent clearer.

### 7.1. Manual acknowledgment

Example of a listener receiving an acknowledgment:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "manualAckListenerContainerFactory"
)
public void handle(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    billingService.process(event);

    acknowledgment.acknowledge();
}
~~~

The factory used here must configure AckMode.MANUAL or MANUAL_IMMEDIATE accordingly.

Acknowledge only after the required business work has completed. If offsets are committed before the database write succeeds, the consumer may not receive the record again after a restart. If processing succeeds without committing, the record may be redelivered; therefore listeners should be idempotent.

## 8. Creating a factory for batch listeners

By default, listeners typically receive one record at a time. To process multiple records in a single listener invocation, create a separate factory and enable batch listener mode:

~~~java
@Bean(name = "batchOrdersListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchOrdersListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> orderConsumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(orderConsumerFactory);
    factory.setConcurrency(2);
    factory.setBatchListener(true);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

The listener receives a list of events:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-batch-service",
    containerFactory = "batchOrdersListenerContainerFactory"
)
public void handleBatch(List<OrderCreated> events) {
    for (OrderCreated event : events) {
        // Process event in batch.
    }
}
~~~

The actual batch size depends on the number of records the consumer receives in a poll and settings such as `max.poll.records`. `setBatchListener(true)` changes the listener invocation style; it does not guarantee every batch always has a fixed number of records.

### 8.1. When should you use batching?

A batch listener can be suitable when:

- The database supports batch inserts/updates.
- Multiple records can be processed in a single operation.
- You want to reduce listener invocation overhead and transaction overhead.
- Business requirements allow batch processing and have a clear error strategy.

Batching also increases complexity when one record in the batch fails. You must decide whether to retry the whole batch or only the failing element, how to commit offsets, and how to avoid reprocessing elements that already succeeded.

Do not use batching solely to increase throughput. Measure poll time, batch size, processing time, consumer lag, and downstream load.

## 9. Configuring an error handler on the factory

Listeners created from the same factory typically share the same error handler. Therefore, the factory is the right place to configure a shared error handling policy for a group of listeners with the same requirements.

Example using `DefaultErrorHandler` with backoff:

~~~java
@Bean
public DefaultErrorHandler kafkaListenerErrorHandler() {
    return new DefaultErrorHandler(
        new FixedBackOff(1_000L, 2L)
    );
}
~~~

Attach the handler to the factory when creating the bean:

~~~java
@Bean(name = "ordersKafkaListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler kafkaListenerErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaListenerErrorHandler);

    return factory;
}
~~~

This example illustrates fixed-interval retries. Tune the retry count and backoff according to the exception types, processing duration, and capacity of dependent systems.

If a dead-letter topic is needed, combine `DefaultErrorHandler` with `DeadLetterPublishingRecoverer` and a KafkaTemplate with appropriate serializers. Ensure the DLT exists, has enough corresponding partitions when preserving source partitions, and has appropriate retention, ACLs, and a replay process.

### 9.1. When do you need a separate factory for error policy?

Suppose the application has two listeners:

- An invoicing listener that needs short retries and routes final failures to a DLT.
- An analytics listener that can skip certain invalid records under its own policy.

If both listeners share one factory, a shared error handler may not satisfy both needs. Create two factories with separate error policies, then specify the appropriate factory on each `@KafkaListener`.

Do not mutate a shared factory's error handler while containers are running and expect all endpoints to update synchronously. Configuration should be decided before endpoints are created.

## 10. Message converters and listener data types

Consumer deserializers convert bytes from Kafka into Java keys and values. Spring Kafka message converters can further convert records into listener parameter types and map headers.

When a JSON deserializer already returns `OrderCreated`, the listener can receive it directly:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void handle(OrderCreated event) {
    // event has already been deserialized into OrderCreated.
}
~~~

If conversion at the Spring Message level is needed, configure a record message converter on the factory:

~~~java
factory.setRecordMessageConverter(messageConverter);
~~~

For batch listeners, use an appropriate batch message converter if the application needs batch-level payload/header conversion.

Distinguish clearly:

- Deserializers operate at the Kafka consumer layer, converting bytes into keys/values.
- Message converters operate at the Spring Kafka layer, converting records into the message/argument form used by the listener.

Do not configure a converter to compensate for a mistyped deserializer. Both layers must be compatible with the payloads sent by the producer.

## 11. Multiple factories for different listener needs

An application can declare multiple container factories. For example:

| Factory | Listener style | Concurrency | AckMode | Error policy |
|---|---|---:|---|---|
| ordersRecordListenerContainerFactory | Record | 3 | RECORD | Standard retry |
| ordersBatchListenerContainerFactory | Batch | 2 | BATCH | Batch retry |
| paymentsListenerContainerFactory | Record | 1 | MANUAL | Custom retry and DLT |

Each factory can use the same or different ConsumerFactory depending on data types and consumer configuration.

Example of two listeners choosing different factories:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "ordersRecordListenerContainerFactory"
)
public void handleOrder(OrderCreated event) {
    // Process each order.
}

@KafkaListener(
    topics = "commerce.payment.captured",
    groupId = "reconciliation-service",
    containerFactory = "paymentsListenerContainerFactory"
)
public void handlePayment(PaymentCaptured event) {
    // Reconcile payment.
}
~~~

Splitting factories should be based on genuine differences in deserializers, concurrency, batching, acknowledgment, transactions, or error handling. There is no need to create a new factory for every listener if they share the same policies and settings.

## 12. Configuring container properties

Beyond factory-level settings, you can access `ContainerProperties` to configure container behavior.

Example:

~~~java
factory.getContainerProperties()
    .setAckMode(ContainerProperties.AckMode.RECORD);

factory.getContainerProperties()
    .setPollTimeout(3_000L);
~~~

Some commonly examined properties:

| Property | Purpose |
|---|---|
| AckMode | How the container acknowledges and commits offsets |
| pollTimeout | Wait timeout for a single poll as configured on the container |
| syncCommits | Selects synchronous or asynchronous commits in cases where the container manages commits |
| ackCount | Number of records triggering commit for AckMode.COUNT/COUNT_TIME |
| ackTime | Time interval triggering commit for AckMode.TIME/COUNT_TIME |
| missingTopicsFatal | Determines behavior when a declared topic does not exist, depending on configuration and version |
| idleEventInterval | Interval for publishing idle events when the consumer receives no data |

API names and availability may differ across Spring Kafka versions. Check the Javadoc for the dependency version in your project before adopting new properties or deprecated APIs.

Do not put all consumer client configuration into ContainerProperties. Properties such as `max.poll.interval.ms`, `max.poll.records`, deserializers, and group ID belong to Kafka consumer configuration; container properties control how Spring manages the listener container.

## 13. Managing container lifecycle via the registry

Containers created from `@KafkaListener` are managed by Spring through `KafkaListenerEndpointRegistry`.

You can assign an ID to a listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

Then access the container via the registry:

~~~java
@Service
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControlService(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.stop();
        }
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.start();
        }
    }
}
~~~

The registry helps the application control listener endpoints by ID. Containers also support pause/resume in scenarios where consumption needs to be temporarily paused or load controlled.

Distinguish:

- `id` on @KafkaListener is the endpoint identifier in Spring.
- `groupId` is the consumer group identifier on Kafka.
- `clientIdPrefix` is the client ID prefix for Kafka consumers.

These three values serve different purposes and should not be used interchangeably.

## 14. Integrating transactions with listener containers

When a listener needs to participate in Kafka transactions, the factory/container must be configured with a transaction manager and a transaction-capable producer factory.

With Spring Kafka, transactions are typically enabled on the producer factory via a transaction ID prefix; the container uses a Kafka-aware transaction manager appropriate for the Spring Kafka version.

A transactional listener processing flow can include:

1. The container starts a Kafka transaction.
2. The consumer receives records and invokes the listener.
3. The listener performs business processing and may send output records using a KafkaTemplate participating in the transaction.
4. Consumer offsets are sent into the transaction.
5. The transaction commits or aborts.

Transactions can help ensure output records and offsets are committed atomically within the scope of a Kafka transaction. They do not automatically create an atomic transaction between Kafka and an external database.

When configuring transactions, verify:

- The ProducerFactory has an appropriate transaction ID prefix.
- Transaction IDs are unique across active producers.
- The KafkaTemplate uses the transactional producer factory.
- The container uses the corresponding transaction manager.
- The listener handles exceptions with an appropriate rollback/retry policy.
- Downstream consumers use an appropriate isolation level if they need to read only committed transactions.

Transaction manager configuration APIs have changed across Spring Kafka generations. Use the correct API for your project's version and avoid copying old examples with deprecated methods.

## 15. Spring Boot and application.yml configuration

You can place Kafka client properties in application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
~~~

Then create a factory using the Spring Boot-configured ConsumerFactory or declare a custom ConsumerFactory if finer control is needed.

Example of a factory bean receiving ConsumerFactory from the context:

~~~java
@Bean(name = "ordersKafkaListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

When an application has multiple value types, ensure the ConsumerFactory generics and deserializers match. Do not use a ConsumerFactory that deserializes into OrderCreated for a listener receiving PaymentCaptured unless an appropriate converter or envelope type is in place.

## 16. Common configuration errors

| Symptom | Possible cause | What to check |
|---|---|---|
| Container factory not found | Wrong bean name in containerFactory or bean not registered | Check bean name and annotations |
| Listener does not start | Missing ConsumerFactory or invalid consumer configuration | Check factory wiring and startup logs |
| ClassCastException in listener | Mismatched generic types, deserializer, or listener method | Check key/value types and converter |
| Increasing concurrency does not increase throughput | Too few partitions or downstream bottleneck | Check assignment, lag, and processing time |
| Batch listener receives wrong type | setBatchListener not enabled or incompatible method signature | Check factory and listener parameters |
| Offset commit behaves unexpectedly | Inappropriate AckMode or auto-commit setting | Check ContainerProperties and enable.auto.commit |
| Retries do not apply | Error handler not attached to the factory used by the listener | Check containerFactory and common error handler |
| DLT publish fails | Inappropriate producer template, serializer, or DLT partition count | Check DLT, serializer, and partition count |
| Changing factory does not affect running container | Container was already created from the previous configuration | Stop/recreate the container via the appropriate procedure |
| Listener endpoint starts/stops unexpectedly | Uncontrolled autoStartup or lifecycle registry | Check endpoint ID and registry |

## 17. Testing ConcurrentKafkaListenerContainerFactory

Integration tests should verify that the factory creates containers with the expected configuration and that the listener actually processes records.

Basic steps:

1. Start a test broker using EmbeddedKafka or Testcontainers.
2. Declare ConsumerFactory and ConcurrentKafkaListenerContainerFactory in the Spring context.
3. Create a listener with an explicit ID and specify containerFactory.
4. Send records to the topic.
5. Verify the listener receives the expected payload.
6. Verify the container is registered in KafkaListenerEndpointRegistry.
7. Test concurrency or batch behavior when needed.
8. Test acknowledgment, error handlers, and retries in separate tests.

Example of verifying container registration:

~~~java
@SpringBootTest
@EmbeddedKafka(
    partitions = 3,
    topics = "commerce.order.created"
)
class OrderListenerContainerTest {

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @Test
    void shouldRegisterOrdersListenerContainer() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        assertThat(container).isNotNull();
        assertThat(container.isRunning()).isTrue();
    }
}
~~~

To verify a specific concurrency setting, check that the created container is a `ConcurrentMessageListenerContainer` and inspect its concurrency configuration using the API of the version in use.

To test a batch listener, send multiple records to partitions and verify the listener receives a collection. Do not assume batches always have a fixed size because record counts depend on polling and available data.

When testing retries and DLT, assert the listener invocation count, that the record is published to the DLT, and that offsets are handled according to the expected policy. Do not check only exception logs.

## 18. Pre-production factory checklist

- [ ] Is the factory registered as a bean with a clear name?
- [ ] Does @KafkaListener reference the right containerFactory?
- [ ] Does ConsumerFactory have matching key/value generics and deserializers?
- [ ] Is concurrency aligned with partition count and instance count?
- [ ] Is record vs. batch listener mode chosen appropriately?
- [ ] Does AckMode match the listener type and commit requirements?
- [ ] Is enable.auto.commit configured appropriately for the container?
- [ ] Are the error handler and retry policy attached to the right factory?
- [ ] Does the DLT have appropriate serializers, partitions, and retention?
- [ ] Are converter and deserializer responsibilities properly separated?
- [ ] Are separate factories created when listeners have distinct policies?
- [ ] Are listener IDs and group IDs managed separately?
- [ ] Is the lifecycle controlled via the registry when needed?
- [ ] Are transaction manager and producer factory compatible if transactions are used?
- [ ] Are endpoints, concurrency, batching, errors, and offsets covered by tests?

## Conclusion

`ConcurrentKafkaListenerContainerFactory` is the component that configures and creates concurrent listener containers for `@KafkaListener` endpoints. The factory ties a ConsumerFactory together with settings such as concurrency, record/batch mode, acknowledgment, error handling, and message conversion. The created container is what actually manages consumers, polls records, and invokes listeners.

An application can use one shared factory for listeners with the same requirements or declare multiple factories for listener groups with different deserializers, concurrency, batching, transactions, or error policies. Choosing factories deliberately, keeping consumer configuration consistent, monitoring partition assignments, and testing container lifecycles will keep your Spring Kafka system scalable and operationally stable.
