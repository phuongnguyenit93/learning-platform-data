# ListenerContainerFactory as a configuration template

In Spring Kafka, `@KafkaListener` only describes the message-receiving endpoint: which topic to listen to, which consumer group to use, and which method processes records. For the endpoint to actually operate, Spring must create a listener container. The container manages `KafkaConsumer`, the `poll()` loop, dispatching records to the listener, acknowledging offsets, handling rebalances, and closing the consumer when the application stops.

`KafkaListenerContainerFactory` is the component that creates listener containers for endpoints declared with `@KafkaListener`. In applications using concurrency, the commonly encountered class is `ConcurrentKafkaListenerContainerFactory`. The factory acts as a configuration template: you configure `ConsumerFactory`, concurrency, AckMode, poll timeout, error handler, and container options once; Spring uses that configuration to create containers for each listener endpoint.

Understanding the factory helps avoid repeating configuration across individual listeners, while allowing an application to have multiple listener groups with different policies—for example, single-record listeners, batch listeners, or listeners with custom retries.

## 1. Where does the factory sit in the @KafkaListener lifecycle?

Key components have distinct responsibilities:

| Component | Responsibility |
|---|---|
| `ConsumerFactory<K, V>` | Creates Kafka consumers with bootstrap servers, group, deserializers, and consumer properties |
| `KafkaListenerContainerFactory` | Creates listener containers from shared configuration and endpoint metadata |
| `ConcurrentKafkaListenerContainerFactory` | Common factory supporting creation of containers with one or more consumers |
| `KafkaMessageListenerContainer` | Container managing a single Kafka consumer and poll loop |
| `ConcurrentMessageListenerContainer` | Parent container managing multiple child containers/consumers when concurrency is enabled |
| `@KafkaListener` | Declares endpoint, topic, group ID, container factory, and handler method |

The initialization flow can be visualized as follows:

```text
ApplicationContext starts
          |
          v
Spring detects @KafkaListener methods
          |
          v
KafkaListenerAnnotationBeanPostProcessor
          |
          v
Selects KafkaListenerContainerFactory by containerFactory
          |
          v
Factory combines endpoint + ConsumerFactory + ContainerProperties
          |
          v
Creates listener container
          |
          v
Container starts -> creates KafkaConsumer -> polls -> invokes listener
```

A factory is not a running Kafka consumer. It is an object that configures and creates containers. The actual Kafka consumer is created when the container starts via `ConsumerFactory`. Therefore, one factory can serve as a shared configuration for many endpoints; each endpoint gets its own container and consumers according to its concurrency setting.

## 2. KafkaListenerContainerFactory and ConcurrentKafkaListenerContainerFactory

`KafkaListenerContainerFactory` is the abstract interface Spring Kafka uses to create listener containers. In typical applications, `ConcurrentKafkaListenerContainerFactory<K, V>` is the common choice because it can configure the number of consumers running in parallel.

Two commonly encountered container types:

- `KafkaMessageListenerContainer`: manages a single Kafka consumer, suitable when an endpoint needs one consumer.
- `ConcurrentMessageListenerContainer`: manages one or more child `KafkaMessageListenerContainer` instances; the number of children is determined by concurrency.

When concurrency is 1, the concurrent container can still manage a single child container. When concurrency is greater than 1, the factory creates a parent container with multiple consumers joining the same group. Each consumer is assigned partitions according to consumer group rules; the number of useful consumers cannot exceed the number of partitions assignable to that endpoint's group.

For example, if a topic has 6 partitions and concurrency is 3, up to three consumers can receive partitions simultaneously. If concurrency is 8, at least two consumers will not be assigned any partitions if this endpoint only subscribes to the six-partition topic and no other topic adds partition assignments.

## 3. Creating a basic factory with Spring Boot

Spring Boot can auto-configure `ConsumerFactory` and a default `ConcurrentKafkaListenerContainerFactory` named `kafkaListenerContainerFactory` when auto-configuration conditions match. If you need to customize the default factory, use `ConcurrentKafkaListenerContainerFactoryConfigurer` to apply `spring.kafka.*` properties first, then add your own settings.

Example:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean(name = "kafkaListenerContainerFactory")
    public ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        configurer.configure(factory, consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties().setPollTimeout(1000L);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
```

`configurer.configure(...)` applies consumer/listener factory settings managed by Spring Boot, including relevant configurations in `application.yml`. Afterwards, `setConcurrency(3)` and `setPollTimeout(1000L)` override or add custom policies for this factory.

If you create a factory manually without calling the Boot configurer, explicitly provide the complete `ConsumerFactory` and required container properties. Otherwise, the application may miss settings declared under `spring.kafka.listener` or auto-configuration defaults the team expects.

Example baseline configuration in `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-worker
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    listener:
      ack-mode: record
      poll-timeout: 1s
```

Property names and duration representations depend on the Spring Boot version. Cross-check configuration against the Boot/Spring Kafka version in use; if the same property is set in both YAML and Java, the value configured later during factory creation can override the earlier value.

## 4. Creating a factory without Boot configurer

In plain Spring Framework applications or when you want full control over configuration, you can create a factory directly from `ConsumerFactory`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties().setPollTimeout(1000L);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
```

The factory receives a `ConsumerFactory<String, OrderCreated>` with key/value deserializers compatible with the topic data. Consumer properties such as `bootstrap.servers`, `group.id`, `max.poll.records`, and `max.poll.interval.ms` belong to Kafka consumer configuration; properties such as `pollTimeout`, `ackMode`, and `shutdownTimeout` belong to Spring Kafka's `ContainerProperties`.

Do not confuse `ConsumerFactory` with `KafkaListenerContainerFactory`: the former creates Kafka consumers; the latter creates listener containers and connects the container with the consumer factory and listener endpoint.

## 5. Attaching a factory to @KafkaListener

If the application has a default factory named `kafkaListenerContainerFactory`, `@KafkaListener` can use that factory without declaring `containerFactory`:

```java
@KafkaListener(topics = "orders", groupId = "orders-worker")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

If there are multiple factories, specify the bean name to use:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-worker",
        containerFactory = "orderListenerContainerFactory")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

`containerFactory` references the Spring bean name, not the class name. If the bean name is wrong or the factory does not exist, the endpoint cannot be created properly and the application typically fails on context startup.

`groupId` on the annotation can override the default group ID from the consumer factory for that endpoint. If group ID is omitted on the annotation and the consumer factory has `group.id`, the container uses that group configuration. Choose a consistent convention to avoid an endpoint accidentally joining the wrong group.

## 6. ContainerProperties: configuring the poll and commit loop

The factory exposes `getContainerProperties()` to configure container behaviors. Some commonly used properties:

| Property | Meaning |
|---|---|
| `pollTimeout` | Time a single poll waits for data |
| `ackMode` | Rule for when the container acknowledges offsets after listener processing |
| `shutdownTimeout` | Time the container waits when closing consumers |
| `idleEventInterval` | Interval used to publish listener idle events when appropriate |
| `ackCount` | Record count threshold for AckMode `COUNT` |
| `ackTime` | Time threshold for AckMode `TIME` |
| `syncCommits` | Chooses synchronous or asynchronous commits when the container commits |
| `consumerRebalanceListener` | Callback when partitions are revoked/assigned |

Example of setting several properties:

```java
factory.getContainerProperties().setPollTimeout(1500L);
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);
factory.getContainerProperties().setShutdownTimeout(15_000L);
factory.getContainerProperties().setIdleEventInterval(30_000L);
```

`pollTimeout` is not `max.poll.interval.ms`. Poll timeout is the wait duration inside a single poll; `max.poll.interval.ms` is the limit between two consumer poll calls. A listener that takes too long to process a batch can still exceed `max.poll.interval.ms` even if poll timeout is only one second.

`ackMode` also does not change the number of records returned per poll. The record count is governed by the Kafka consumer's `max.poll.records` and available data. AckMode determines when the container commits offsets after listener processing.

## 7. Choosing an AckMode suited to the listener

Spring Kafka manages offset commits according to AckMode. Common modes include:

| AckMode | High-level behavior | Use case |
|---|---|---|
| `RECORD` | Commits after each record listener finishes | Want progress confirmed per record |
| `BATCH` | Commits after finishing records from a poll | Suitable for batch processing or common default |
| `TIME` | Commits when the configured interval elapses and records were processed | Group commits by time |
| `COUNT` | Commits when the configured record count is reached | Reduce commit frequency by data volume |
| `COUNT_TIME` | Combines record count and time conditions | Want thresholds on both volume and time |
| `MANUAL` | Listener calls `Acknowledgment.acknowledge()`; container commits per manual rules | Business logic explicitly chooses when to acknowledge |
| `MANUAL_IMMEDIATE` | Requests immediate commit when acknowledge is called on the consumer thread | Need immediate confirmation right after a business boundary |

Example using manual acknowledgment:

```java
@KafkaListener(
        topics = "orders",
        groupId = "orders-worker",
        containerFactory = "orderListenerContainerFactory")
public void onOrder(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    orderService.handleAndPersist(event);
    acknowledgment.acknowledge();
}
```

Acknowledge only after business work is finished or work has been durably persisted by design. If offsets are committed before saving business results, a process crash can cause records to be skipped. If processing succeeds but commit fails, records may be redelivered; consumers should be idempotent.

Exact commit timing details, especially when acknowledging from another thread, depend on AckMode and the Spring Kafka version. Do not call `acknowledge()` arbitrarily from worker threads without configuring and understanding the container's out-of-order commit mechanism.

## 8. Creating multiple factories for multiple listener styles

An application may have multiple endpoint types with different requirements. For example, a record-by-record listener needs AckMode `RECORD`, while a batch listener needs a list of records and batch mode. You can declare two separate factories:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderRecordFactory(
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
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderBatchFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setConcurrency(2);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.BATCH);
        return factory;
    }
}
```

Record listener:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-record-worker",
        containerFactory = "orderRecordFactory")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

Batch listener:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-worker",
        containerFactory = "orderBatchFactory")
public void onOrders(List<OrderCreated> events) {
    orderService.handleBatch(events);
}
```

The two listeners use different group IDs so each group receives an independent copy of the record stream. If they used the same group ID, they would split partitions between them instead of each listener receiving all data. The batch factory needs `setBatchListener(true)` so the container invokes the method with batches according to the corresponding listener configuration.

Factories can share a `ConsumerFactory` if serializers/deserializers and consumer properties match. If two groups need different isolation levels, deserializers, group behaviors, or security settings, create a separate `ConsumerFactory` for each group and attach it to the corresponding factory.

## 9. Configuring concurrency at the factory and annotation levels

`setConcurrency(n)` sets the default number of consumers for containers created from that factory. For a specific listener, the `concurrency` attribute on `@KafkaListener` can override this default:

```java
@KafkaListener(
        id = "paymentsListener",
        topics = "payments",
        groupId = "payments-worker",
        containerFactory = "orderRecordFactory",
        concurrency = "5")
public void onPayment(PaymentReceived event) {
    paymentService.handle(event);
}
```

Concurrency increases the number of consumers and parallel processing capacity across partitions. It does not allow multiple consumers in the same group to process a single partition concurrently. If a topic has only three partitions, setting concurrency to five does not create five useful consuming threads for that topic alone.

When a factory is shared across multiple listeners, each endpoint can have different concurrency. Configure concurrency based on each topic's throughput and partition count while monitoring consumer lag, CPU, DB connection pools, and downstream capacity. Setting concurrency too high can overload downstream systems without increasing actual throughput.

## 10. Configuring CommonErrorHandler on the factory

A factory can attach a shared error handler for the containers it creates. In modern Spring Kafka versions, `DefaultErrorHandler` is the common choice for configuring retries and handling failed records.

```java
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

    var errorHandler = new DefaultErrorHandler(
            new FixedBackOff(1000L, 2L));
    factory.setCommonErrorHandler(errorHandler);

    return factory;
}
```

The example configures a one-second wait between retry attempts and up to two retries after the initial processing attempt, following `FixedBackOff` semantics. Once retries are exhausted, the default error handler behavior may log and handle offsets as configured; in production, consider a recoverer that writes records to a dead-letter topic so error context is not lost.

Not every error should be retried. Transient errors such as service timeouts can be retried; invalid data errors usually need to go to dead-letter or halt processing according to policy. For batch listeners, identifying the failing record and committing processed records follow specific rules; configure an error handler compatible with the listener type.

Error handler API names have changed across Spring Kafka versions. `CommonErrorHandler`/`DefaultErrorHandler` is the modern direction; older projects may use `ErrorHandler` or `SeekToCurrentErrorHandler`. Do not mix API examples from different versions in the same configuration.

## 11. Filtering records before invoking the listener

A factory can also configure `RecordFilterStrategy` to discard records that do not need to reach the listener. Example:

```java
factory.setRecordFilterStrategy(record ->
        record.value() == null || record.value().isBlank());
```

A predicate returning `true` means the record is filtered out. Filtering fits clear skip conditions, such as dropping heartbeat events or message types outside business scope. Do not use a filter to hide deserialization errors or drop invalid data without logs/metrics.

When records are filtered, understand the offset acknowledgment policy. Spring Kafka provides options related to acknowledging discarded records; check `ackDiscarded` and AckMode in your version if precise control is needed. For important business data, record metrics for filtered records so you can explain why the listener did not process them.

## 12. Managing container lifecycle

The factory creates containers, while Spring manages container start/stop lifecycles. `@KafkaListener` endpoints usually start automatically when the application context is ready. You can control listeners via `KafkaListenerEndpointRegistry` if an endpoint needs to be stopped or started for operational reasons.

Example listener with an ID:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-worker")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

Controlling the container:

```java
@Component
public class ListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        var container = registry.getListenerContainer("ordersListener");
        if (container != null) {
            container.pause();
        }
    }

    public void resumeOrders() {
        var container = registry.getListenerContainer("ordersListener");
        if (container != null) {
            container.resume();
        }
    }
}
```

Container pause/resume is not the same as stop/start. Pause temporarily stops receiving records from partitions while the container continues polling to maintain group membership; stop stops the container and closes the consumer per lifecycle rules. Use `registry.getListenerContainer(id)` to retrieve containers created from annotations. Containers declared directly as `@Bean` beans may be managed as standalone beans and are not necessarily in the annotation registry.

Properties such as `autoStartup`, `phase`, and `shutdownTimeout` help control startup timing and shutdown duration. If a listener depends on a DB or other services, ensure dependencies are ready before the container receives records and that the application has enough graceful shutdown time to finish in-flight work.

## 13. Common configuration errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `@KafkaListener` cannot find factory | `containerFactory` name does not match bean name | Check the bean name and specify `containerFactory` accurately |
| Listener ignores YAML config | Custom-created factory bypassed Boot configurer or was overridden in Java | Call configurer before customizing or configure all properties explicitly |
| Listener receives wrong data type | ConsumerFactory uses incompatible deserializer | Check generic types, key/value deserializers, and JSON type mapping |
| High concurrency does not raise throughput | Too few partitions, downstream bottleneck, or consumers unassigned | Inspect partition assignment, lag, and downstream resources |
| Batch listener receives wrong arguments | Factory did not enable batch listener or method signature is incompatible | Use `setBatchListener(true)` and a batch parameter type supported by Spring Kafka |
| Offset commit differs from expectations | AckMode, auto-commit, or acknowledgment timing is inappropriate | Review container AckMode and `enable.auto.commit` |
| Infinite retry loop or skipped records | Inappropriate error handler/recoverer, or batch semantics overlooked | Configure bounded retries, dead-lettering, and verify commit behavior |
| Listener fails to stop in time | Shutdown timeout too short or downstream call blocked | Set timeouts on dependencies and configure graceful shutdown duration |

## 14. Process for designing factories in an application

1. Identify listener groups and processing requirements: record vs. batch, group ID, topics, and partition counts.
2. Select or create a `ConsumerFactory` for each group based on deserializers, security, and consumer properties.
3. Create a `ConcurrentKafkaListenerContainerFactory` for each listener group sharing the same policy.
4. Use `ConcurrentKafkaListenerContainerFactoryConfigurer` if inheriting Spring Boot configuration is needed.
5. Set concurrency, poll timeout, AckMode, error handler, and filters according to business requirements.
6. Attach factories to `@KafkaListener` via `containerFactory` when multiple factories exist.
7. Start the application and verify containers, consumer groups, partition assignments, and logs.
8. Test record success, processing errors, retries, dead-lettering, rebalances, and graceful shutdown.

A well-designed factory standardizes listener configuration and reduces unintended differences across endpoints. When different behaviors are required, create separate factories per policy group rather than cramming everything into one shared factory and overriding it piecemeal on individual listeners.

## Pre-production listener container checklist

- Correctly named factory beans exist and `@KafkaListener` endpoints reference the right factory.
- `ConsumerFactory` uses deserializers and consumer properties matching the topic.
- A deliberate choice was made between Boot configurer and full manual configuration.
- Concurrency matches partition counts and downstream capacity.
- `pollTimeout`, `max.poll.interval.ms`, and `max.poll.records` are balanced against processing time.
- AckMode and `enable.auto.commit` align with when business processing completes.
- Error handler has bounded retries and a clear recovery/dead-letter policy.
- Batch listeners enable batch mode properly and use compatible method signatures.
- Filters emit metrics/logs and do not silently drop important events.
- Procedures exist for pause/resume, graceful shutdown, and monitoring consumer lag/rebalances.

`ListenerContainerFactory` is the central place where Spring Kafka creates and configures listener containers. Combining `ConsumerFactory`, `ContainerProperties`, concurrency, AckMode, and error handlers properly gives `@KafkaListener` endpoints consistent, testable behavior suited to the operational needs of each event stream.
