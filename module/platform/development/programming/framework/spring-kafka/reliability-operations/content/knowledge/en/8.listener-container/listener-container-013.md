# Shared container factories and configuration isolation

In Spring Kafka, `KafkaListenerContainerFactory` is where you define how listener containers are created and operated. One factory can be shared across multiple `@KafkaListener` methods when they share the same processing policies. When a listener needs a different batch mode, acknowledgment mode, concurrency, or error handling, the application can create a specialized factory to isolate configuration.

An important distinction is that **a container factory is not a running Kafka consumer**. The factory is an object that configures and creates containers. Each `@KafkaListener` endpoint registered by Spring gets its own listener container; that container creates and manages its own Kafka consumers according to its concurrency count. Multiple listeners can share a factory without sharing the same `KafkaConsumer` object.

## 1. Three components to distinguish

A listener configuration typically has three layers:

1. `ConsumerFactory`: creates Kafka consumers and supplies Kafka client-level properties such as deserializers, security, `max.poll.records`, `auto.offset.reset`, and `isolation.level`.
2. `ConcurrentKafkaListenerContainerFactory`: defines how Spring creates listener containers, such as concurrency, acknowledgment mode, record/batch listener, error handler, and container properties.
3. Listener container: the component executing a `@KafkaListener` endpoint, calling `poll()`, passing records to the listener method, coordinating retries, and committing offsets.

```text
Spring application context
       |
       +------------------------------+
       |                              |
       v                              v
ConsumerFactory                 Container factory
       |                              |
       | creates KafkaConsumer        | creates listener container
       |                              |
       +---------------+--------------+
                       |
                       v
              Listener container
                       |
                       v
                Kafka consumer
                       |
                       v
                 @KafkaListener
```

In practice, the container factory takes a `ConsumerFactory` to create consumers. One container can manage one consumer or multiple consumer threads depending on concurrency configuration. When multiple endpoints use the same factory, Spring creates a separate container for each endpoint and each container manages its own consumers.

## 2. When should you share a container factory?

Share a common factory when listeners have the same operational requirements, such as:

- Same record listener or batch listener mode.
- Same acknowledgment mode and offset commit policy.
- Same retry/backoff and error handler.
- Same default concurrency and container properties.
- Same transaction policy if using Kafka transactions.

For example, listeners processing `orders`, `payments`, and `shipments` all receive individual records, perform synchronous business processing, commit per record, and use the same error handler. One default factory can create containers for all three listeners.

Spring Boot typically auto-configures a default factory named `kafkaListenerContainerFactory` if the application has suitable Kafka configuration and has not declared a corresponding factory. Listeners can use the default factory without specifying the `containerFactory` attribute:

```java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrder(OrderCreated event) {
    billingService.process(event);
}

@KafkaListener(topics = "payments", groupId = "payment-service")
public void onPayment(PaymentRequested event) {
    paymentService.process(event);
}
```

The two listeners have separate group IDs so they maintain separate reading progress. They can still use the same container factory if container policies match. `group.id` can be set at the endpoint or consumer configuration; sharing a factory does not mean two listeners share a consumer group.

## 3. Configuring the default factory in Spring Boot

If you need to customize the default factory while preserving settings applied by Spring Boot, you can use `ConcurrentKafkaListenerContainerFactoryConfigurer`. The configurer applies settings from `spring.kafka.*` to the factory and consumer factory passed in.

```java
@Configuration
@EnableKafka
public class KafkaListenerConfiguration {

    @Bean(name = "kafkaListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<Object, Object>
    kafkaListenerContainerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<Object, Object> kafkaConsumerFactory) {

        ConcurrentKafkaListenerContainerFactory<Object, Object> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        configurer.configure(factory, kafkaConsumerFactory);
        return factory;
    }
}
```

The factory above retains common configuration provided by Spring Boot. Basic properties can be placed in `application.properties`:

```properties
spring.kafka.bootstrap-servers=localhost:9092

spring.kafka.consumer.group-id=default-service
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties[spring.json.trusted.packages]=com.example.events

spring.kafka.listener.ack-mode=record
spring.kafka.listener.concurrency=2
```

These values are examples for a development environment. For production, bootstrap servers, security, trusted packages, group ID, and offset reset must be chosen per environment and business stream. Do not widen trusted packages unnecessarily when using JSON deserialization.

If the application needs no factory customization, let Spring Boot create the default factory. When declaring a bean with the same name `kafkaListenerContainerFactory`, the application explicitly provides the factory in place of the auto-configured bean; therefore, use the configurer or configure all required properties so Boot settings are not accidentally lost.

## 4. Creating a specialized factory for listeners needing different policies

When a group of listeners needs its own policy, create an additional `ConcurrentKafkaListenerContainerFactory` bean with a clear name. For example, an audit listener processes single records, uses higher concurrency, and has a dedicated error handler:

```java
@Bean(name = "auditKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<Object, Object>
auditKafkaListenerContainerFactory(
        ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
        ConsumerFactory<Object, Object> kafkaConsumerFactory,
        DefaultErrorHandler auditErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<Object, Object> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    // Inherit common Kafka configuration from Spring Boot.
    configurer.configure(factory, kafkaConsumerFactory);

    // Override only policies specific to the audit group.
    factory.setConcurrency(4);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);
    factory.setCommonErrorHandler(auditErrorHandler);

    return factory;
}
```

A listener selects this factory by bean name:

```java
@KafkaListener(
        topics = "audit-events",
        groupId = "audit-archive",
        containerFactory = "auditKafkaListenerContainerFactory")
public void archive(AuditEvent event) {
    auditArchive.store(event);
}
```

Other listeners continue using the default factory:

```java
@KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        containerFactory = "kafkaListenerContainerFactory")
public void bill(OrderCreated event) {
    billingService.process(event);
}
```

`containerFactory` points to a bean name in the Spring context. The name must match exactly. When there is only one default factory, this attribute can usually be omitted; when multiple factories exist, declaring it explicitly shows readers which policy each listener uses and prevents picking the wrong factory.

In the example, both factories share `ConsumerFactory` because they share connection and deserializer settings. They differ only in concurrency, acknowledgment mode, and error handler at the container level. This is appropriate isolation when differences lie in how containers operate.

## 5. When do you also need to split ConsumerFactory?

Not all differences belong to the container factory. Some properties are Kafka consumer client settings. If two listener groups need different client settings, separate `ConsumerFactory` instances may be needed and attached to their respective container factories.

| Configuration | Belongs to | Example reason to split |
|---|---|---|
| Key/value deserializers | `ConsumerFactory` | One topic uses JSON, another uses Avro or byte arrays |
| `auto.offset.reset` | `ConsumerFactory` | One new group needs `earliest`, another stream needs `latest` |
| `max.poll.records` | `ConsumerFactory` | Large batch processing needs its own poll limit |
| `max.poll.interval.ms` | `ConsumerFactory` | One workload type has longer processing durations |
| `isolation.level` | `ConsumerFactory` | Stream must read only committed transactional data |
| Security, client ID, and network settings | `ConsumerFactory` | Listener group connects to a different cluster or security identity |
| Concurrency | Container factory/container | Listener groups need different consumer thread counts |
| Ack mode | Container factory/container | Listener groups have different offset commit requirements |
| Batch listener mode | Container factory | One listener receives individual records, another receives batches |
| Common error handler | Container factory/container | Different retry, backoff, and recovery rules |

Example of a separate factory for an archive stream that needs to read historical data, poll fewer records, and use a dedicated deserializer:

```java
@Bean
ConsumerFactory<String, AuditEvent> auditConsumerFactory(
        @Value("${app.kafka.archive.bootstrap-servers}") String bootstrapServers) {

    Map<String, Object> props = new HashMap<>();
    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "audit-archive");
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 50);
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            JsonDeserializer.class);
    props.put(JsonDeserializer.TRUSTED_PACKAGES, "com.example.audit");

    return new DefaultKafkaConsumerFactory<>(props);
}
```

Attach the dedicated consumer factory to a container factory:

```java
@Bean(name = "archiveKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
archiveKafkaListenerContainerFactory(
        ConsumerFactory<String, AuditEvent> auditConsumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, AuditEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(auditConsumerFactory);
    factory.setConcurrency(2);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);

    return factory;
}
```

This is an illustrative configuration. In real applications, include appropriate security settings, schema/deserializer, trust configuration, and bootstrap servers. If you want a custom consumer factory to inherit Spring Boot settings, build it from `KafkaProperties` or centralized application configuration; avoid copying settings while missing critical details like TLS/SASL, metrics, client ID, and interceptors.

One `ConsumerFactory` can be shared to create multiple Kafka consumers because the factory manages client creation, not a single consumer actively reading data. If the only difference is `group.id` per endpoint, `@KafkaListener(groupId = "...")` usually suffices; there is no need to create a new `ConsumerFactory` just to change group ID.

## 6. Isolating batch listeners and record listeners

An important container-level distinction is whether a listener receives individual records or an entire batch from a poll.

Record listener:

```java
@KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        containerFactory = "kafkaListenerContainerFactory")
public void handle(OrderCreated event) {
    billingService.process(event);
}
```

Batch listener:

```java
@KafkaListener(
        topics = "audit-events",
        groupId = "audit-archive",
        containerFactory = "auditBatchKafkaListenerContainerFactory")
public void handleBatch(List<ConsumerRecord<String, AuditEvent>> records) {
    auditArchive.storeBatch(records);
}
```

The factory for a batch listener must enable batch mode:

```java
@Bean(name = "auditBatchKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
auditBatchKafkaListenerContainerFactory(
        ConsumerFactory<String, AuditEvent> auditConsumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, AuditEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(auditConsumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(2);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.BATCH);

    return factory;
}
```

Do not use the same factory for record listeners and batch listeners if `batchListener` causes the adapter to invoke listeners with incompatible parameter shapes. Creating a dedicated factory makes listener type and commit policy clearer. Batch listeners also need explicit design for handling a failing record in a batch: retry the whole batch, handle partial success, or route failing records to a DLT. Never assume batch listeners share identical semantics with record listeners.

## 7. Isolating error handlers and recovery policies

Business streams may need different retry policies. For example, transient errors writing orders might retry with short backoff; errors from an archive system might use longer backoff; invalid data errors need early routing to a DLT.

You can create separate error handlers per factory:

```java
@Bean
DefaultErrorHandler billingErrorHandler(
        DeadLetterPublishingRecoverer billingRecoverer) {
    return new DefaultErrorHandler(
            billingRecoverer,
            new FixedBackOff(500L, 3L));
}

@Bean
DefaultErrorHandler archiveErrorHandler(
        DeadLetterPublishingRecoverer archiveRecoverer) {
    return new DefaultErrorHandler(
            archiveRecoverer,
            new FixedBackOff(5_000L, 5L));
}
```

Bind each handler to its matching container factory. Do not share one handler if it needs per-stream state or different retry/recovery policies. When sharing a handler, ensure the handler and recoverer are designed safely for concurrent calls from multiple containers.

Error handlers do not replace exception classification. Configure non-retryable exceptions for data errors unfixable by retrying, while bounding retries for transient errors. If using a DLT, ensure publish results are checked, the DLT has enough partitions, and a replay process exists.

## 8. Factories and concurrency

`setConcurrency(n)` determines how many consumer threads each listener container can use. With `ConcurrentMessageListenerContainer`, Spring creates child containers to manage separate consumers. Actual active consumer counts also depend on partition assignments and group membership.

For example, a topic has six partitions and two endpoints share a factory with concurrency 3. Each endpoint has its own container, and each container can create three consumers. If the two endpoints join two different groups, total consumer clients can be six and each group independently distributes the topic's six partitions. If both endpoints share the same group, they are members in the same group and split partitions according to that group's assignment.

When raising concurrency, check:

- Partitions assignable to the group.
- Application CPU, memory, and thread counts.
- Connection counts and load on brokers.
- Connection pools, throughput, and limits of downstream databases or APIs.
- Record/batch processing time and `max.poll.interval.ms`.
- Rebalance frequency during rolling deployments or autoscaling.

Higher concurrency does not automatically produce higher throughput. If downstream is already saturated, adding consumers can increase contention and retries. Measure processing rate and latency before changing values.

## 9. Managing bean names and multiple factories

When an application has multiple container factories, name them by purpose instead of generic names like `factory1`, `factory2`. Example:

| Bean name | Purpose |
|---|---|
| `kafkaListenerContainerFactory` | Default factory for standard record listeners |
| `auditKafkaListenerContainerFactory` | Audit listener with dedicated retries and concurrency |
| `auditBatchKafkaListenerContainerFactory` | Batch listener for archiving |
| `transactionalKafkaListenerContainerFactory` | Listener using Kafka transactions |

Each `@KafkaListener` should explicitly specify `containerFactory` when needing a specialized factory. If a bean depends on multiple `ConsumerFactory` instances of the same generic type, use `@Qualifier` so Spring injects the right bean. Use `@Primary` only when there is a genuine default factory suitable for most of the application; do not rely on bean declaration order to select factories.

Example using qualifier:

```java
@Bean(name = "archiveKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
archiveFactory(
        @Qualifier("auditConsumerFactory")
        ConsumerFactory<String, AuditEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, AuditEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();
    factory.setConsumerFactory(consumerFactory);
    return factory;
}
```

Consistent bean naming and references reduce runtime errors such as missing container factories, injecting the wrong consumer factory, or listeners unexpectedly running with default configuration.

## 10. Settings that should not be accidentally shared

Sharing factories prevents duplicate config, yet only genuinely identical policies should be shared. Certain differences must be intentionally separated:

| Difference | Design direction |
|---|---|
| One listener processes records, another processes batches | Create separate container factories with corresponding `setBatchListener` |
| One stream needs `RECORD`, another needs `MANUAL_IMMEDIATE` | Split container factories so acknowledgment modes do not cross-affect |
| Different retry/backoff and DLT | Use separate error handlers/recoverers and attach to appropriate factories |
| Consumers use different deserializers or schemas | Split `ConsumerFactory` and corresponding container factory |
| Different `isolation.level`, `max.poll.records`, or `max.poll.interval.ms` | Split Kafka client settings in `ConsumerFactory` |
| Connecting to different clusters or security principals | Split `ConsumerFactory` with separate connection and security configs |
| Transactional vs. non-transactional listeners | Split factories, transaction managers, and producer/consumer configs by transaction model |

Do not modify properties on a shared factory after listener containers have initialized and expect running containers to update in sync. Factory configuration should be finalized before endpoints start. Runtime changes require controlled container management and verification of your Spring Kafka version's behavior.

## 11. Observing factories and listener containers

When a listener runs with the wrong policy, trace from the endpoint back to the factory and consumer factory:

1. Verify the `containerFactory` name on `@KafkaListener`.
2. Verify the actual factory bean registered in Spring under that name.
3. Verify the factory is bound to the expected `ConsumerFactory`.
4. Inspect `batchListener`, concurrency, acknowledgment mode, error handler, and transaction configuration.
5. Inspect group ID, topic subscriptions, deserializers, and Kafka consumer properties.
6. Cross-check container startup logs, partition assignments, rebalances, and committed offsets.

Metrics to monitor include consumers per group, assigned partition counts, consumer lag, rebalance count, poll latency, processing latency, commit failures, retry rates, and DLT publish rates. Attach bounded tags such as application, listener ID, group ID, and topic; avoid using event ID as a metric label.

One shared factory can create multiple containers, so logs should identify listener ID or container ID. Logging only group ID when multiple listeners share a group makes pinpointing the failing container harder. Setting an explicit `id` on `@KafkaListener` improves traceability.

## 12. Common mistakes when configuring multiple factories

| Symptom | Cause | Fix |
|---|---|---|
| `NoSuchBeanDefinitionException` for container factory | Name in `containerFactory` does not match bean name | Check `@Bean` name and annotation |
| Listener uses wrong concurrency | Listener is using default factory or another factory | Specify `containerFactory` explicitly, check `setConcurrency` |
| Batch listener receives wrong parameter type | Factory lacks batch mode or listener points to wrong factory | Create separate batch factory and check method signature |
| Two streams share the wrong group | Default group ID shared unintentionally | Set explicit `groupId` on each listener |
| Deserialization exception on one topic | `ConsumerFactory` uses incompatible deserializer | Create separate `ConsumerFactory` or configure deserializer for needed types |
| Error handler applies to wrong listener | Multiple factories share an incompatible handler | Split handlers/recoverers and attach to right factories |
| Spring cannot choose which `ConsumerFactory` | Multiple beans of same type without qualifier | Use `@Qualifier` or define a sensible `@Primary` bean |
| Increased concurrency does not reduce lag | Insufficient partitions or downstream saturated | Check partition assignment and downstream capacity before scaling |

When adding a new factory, inspect all related listeners and bean dependencies. A specialized factory has no effect if listeners still point to the default factory name.

## 13. Procedure for rolling out a new configuration

When splitting a listener group out of a shared factory, follow these steps:

1. Pinpoint the exact difference: container behavior or Kafka consumer client properties.
2. If the difference is only concurrency, ack mode, batch mode, or error handler, create a new container factory and optionally reuse `ConsumerFactory`.
3. If the difference is deserializers, security, isolation level, or consumer poll settings, create a dedicated `ConsumerFactory`.
4. Name beans by function and use `@Qualifier` when injecting among multiple factories of the same type.
5. Specify `containerFactory` on each listener requiring specialized configuration.
6. Test record/batch signatures, offset commits, retries, DLT, rebalances, and startup/shutdown.
7. Roll out gradually while watching lag, throughput, poll intervals, and consumer errors.
8. Keep a rollback configuration so listeners can revert to the previous factory if changes cause issues.

Splitting factories should reflect genuine operational needs. Do not create a separate factory for every listener if they share identical policies; too many duplicate factories make configuration hard to track and raise the risk of configuration drift.

## 14. Production design principles

An easily operable container factory structure typically follows these rules:

1. Use `kafkaListenerContainerFactory` as the default factory for listeners sharing common policies.
2. Create specialized factories when there are clear differences in batching, ack mode, concurrency, error handling, or transactions.
3. Share `ConsumerFactory` when Kafka client properties are compatible; split when deserializers, security, clusters, or poll behaviors differ.
4. Remember that each listener endpoint has its own container; sharing a factory does not mean sharing a Kafka consumer.
5. Name beans clearly and reference them accurately via `containerFactory`.
6. Use `@Qualifier` when multiple beans of the same type exist; avoid relying on declaration order.
7. Do not raise concurrency beyond assignable partitions or downstream capacity.
8. Test offset commits, retries, DLT, and rebalances on the actual target factory.
9. Observe each listener/container individually to isolate faults.
10. Finalize configuration before containers start and make runtime changes through controlled procedures.

Shared container factories centralize common listener policies. Specialized factories establish clear boundaries for streams with different needs. By properly separating container factory and `ConsumerFactory` responsibilities, a Spring Kafka application can keep configuration consistent while isolating operational behavior for each consumer group.
