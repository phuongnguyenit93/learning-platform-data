# @KafkaListener API Changes

## Lesson Objectives

In the **Upgrades and Compatibility** chapter, this lesson summarizes the important changes to the `@KafkaListener` API across Spring Kafka generations. The focus is on how the annotation controls the listener container, changes in determining the consumer group, subscriptions, batch mode, acknowledgments, asynchronous processing, and container customization.

**SPRING_KAFKA_MESSAGING** focuses on building Kafka event-sending and receiving applications using Spring Kafka, KafkaTemplate, and @KafkaListener; it also helps learners understand topics, partitions, offsets, consumer groups, serialization, retry, dead-letter handling, transactions, exactly-once semantics, concurrent processing, and testing. When upgrading Spring Kafka, changes in the annotation can alter the group ID, how listeners receive records, when offsets are committed, or how containers are created. Always check the dependency version before applying new syntax.

After this lesson, learners can:

- Understand the role of @KafkaListener in registering listener endpoints and creating containers.
- Identify important annotation attributes and the version milestones when they were added.
- Distinguish id, groupId, and idIsGroup.
- Choose subscriptions using topics, topicPattern, or topicPartitions.
- Use placeholders and SpEL in the right places.
- Choose a record listener, batch listener, or asynchronous listener.
- Use filter, info, containerPostProcessor, and ackMode when supported by the version.
- Update method signatures and header APIs during upgrades.
- Plan a migration from Spring Kafka 2.x to 3.x or 4.x.
- Test compatibility before releasing.

## 1. What does @KafkaListener do?

`@KafkaListener` marks a method or class as an entry point for receiving Kafka messages. Spring detects the annotation during application context initialization, creates a listener endpoint, and registers a container to manage the Kafka consumer.

At the method level, each listener method usually has its own listener container. At the class level, a single container can serve multiple `@KafkaHandler` methods; Spring selects the appropriate method based on the payload type.

~~~mermaid
flowchart TD
    A["@EnableKafka / Spring configuration"] --> B["KafkaListenerAnnotationBeanPostProcessor"]
    B --> C["Detect @KafkaListener"]
    C --> D["Create listener endpoint"]
    D --> E["Select KafkaListenerContainerFactory"]
    E --> F["Create listener container"]
    F --> G["Kafka consumer poll"]
    G --> H["MessagingMessageListenerAdapter"]
    H --> I["Invoke listener method"]
~~~

The annotation is not where every detail of the Kafka consumer is configured. The factory remains the place to define shared configuration such as `ConsumerFactory`, error handler, converter, default concurrency, default acknowledgment mode, and other container properties. The annotation allows overriding specific values per listener.

To use annotation-based listeners in plain Java configuration, `@EnableKafka` is required; Spring Boot usually auto-configures the listener infrastructure when the appropriate dependencies and configuration are present.

## 2. Core attributes

| Attribute | Role |
|---|---|
| `id` | Listener container identifier; can also be used as the group ID depending on `idIsGroup` |
| `groupId` | Overrides `group.id` for the listener |
| `idIsGroup` | Determines whether `id` is used as `group.id` when `groupId` is not declared |
| `topics` | Subscribes to one or more topics |
| `topicPattern` | Subscribes to topics matching a regex |
| `topicPartitions` | Manually assigns topics/partitions, optionally with initial offsets |
| `containerFactory` | Selects the `KafkaListenerContainerFactory` bean |
| `clientIdPrefix` | Prefix for the Kafka client ID |
| `concurrency` | Overrides the container factory's concurrency |
| `autoStartup` | Overrides whether the container starts automatically |
| `properties` | Overrides specific consumer properties for the listener |
| `batch` | Selects record or batch listener on the method |
| `filter` | Selects a dedicated `RecordFilterStrategy` |
| `info` | Adds static information into the `KafkaHeaders.LISTENER_INFO` header |
| `containerPostProcessor` | Customizes the container after creation |
| `ackMode` | Overrides the factory's acknowledgment mode in supported versions |

Not every attribute exists in every version. The milestones below help determine when a configuration can be used.

## 3. Timeline of notable changes

| Version | Listener-related changes |
|---|---|
| 2.0 | `id` is used as the default `group.id` if `groupId` is not specified; `idIsGroup=false` restores taking the group ID from the consumer factory; added listener-level `errorHandler` |
| 2.1.1 | Added `clientIdPrefix` |
| 2.1.2 | SpEL supports the `__listener` pseudo bean and the `beanRef` attribute to rename the token |
| 2.2 | Annotation can override `concurrency` and `autoStartup`; supports `@KafkaListener` as a meta-annotation |
| 2.2.4 | Added `properties` to override consumer properties per listener |
| 2.3.5 | Added `splitIterables` to control how Iterables are returned in request-reply |
| 2.5 | Can receive `ConsumerRecordMetadata` instead of multiple separate headers; received key header is no longer added when key is null |
| 2.5.5 | `@PartitionOffset` supports wildcard `*` for all declared partitions |
| 2.6.4 | `@TopicPartition` supports declaring partitions as a list/range |
| 2.7.1 | Added `contentTypeConverter` |
| 2.8 | Added `batch` to select batch listener directly on the method |
| 2.8.4 | Added `filter` and `info` |
| 3.1 | Added `containerPostProcessor` |
| 3.2 | `@PartitionOffset` supports `seekPosition`; listener supports asynchronous return types such as `CompletableFuture`, `Mono`, and Kotlin suspend |
| 4.1 | Added `ackMode` to override the acknowledgment mode directly on the annotation |

These milestones are representative changes that affect application code. When upgrading, always check the Javadoc and change history of the exact version in use; do not assume a new attribute from 4.x documentation existed in 2.x or 3.x.

## 4. Major change to id and groupId in 2.0

Before Spring Kafka 2.0, `id` primarily identified the endpoint/container. Starting in 2.0, if `id` is declared and `groupId` is not declared, the `id` value is also used as the Kafka consumer `group.id`, overriding the group ID configured in the consumer factory.

Example:

~~~java
@KafkaListener(
    id = "billingOrders",
    topics = "commerce.order.created"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

With the 2.0+ behavior, the consumer group will be `billingOrders` if no separate `groupId` is given.

If you want to keep the group ID from the consumer factory, use `idIsGroup = false`:

~~~java
@KafkaListener(
    id = "billingOrders",
    idIsGroup = false,
    topics = "commerce.order.created"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

A clearer approach when the application needs a fixed group ID is to declare both:

~~~java
@KafkaListener(
    id = "billingOrdersListener",
    groupId = "billing-service",
    topics = "commerce.order.created"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Distinguish:

- `id` is the listener container identifier in Spring.
- `groupId` is the consumer group identity in Kafka.
- `idIsGroup` determines the default relationship between the two values.

When upgrading from an older version to 2.x, audit listeners that declare only `id` while relying on `spring.kafka.consumer.group-id` or `ConsumerFactory` for the group ID. Without auditing, the consumer may switch to a new group and start using separate offsets.

## 5. clientIdPrefix and concurrency

Since 2.1.1, you can set the client ID prefix directly on the annotation:

~~~java
@KafkaListener(
    id = "ordersListener",
    groupId = "billing-service",
    clientIdPrefix = "billing-orders",
    topics = "commerce.order.created",
    concurrency = "3"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

When concurrency is greater than one, Spring appends a suffix to create a distinct client ID for each consumer container, such as `billing-orders-0`, `billing-orders-1`.

`concurrency` has been available since 2.2 and overrides the factory setting. The value can be a literal, property placeholder, or SpEL:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    concurrency = "${app.kafka.orders.concurrency:3}"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

The number of useful consumers is still bounded by the number of assigned partitions. Increasing concurrency does not allow a single partition to be processed in parallel by multiple consumers in the same group.

## 6. autoStartup and startup timing

`autoStartup` was added to override the factory configuration starting in version 2.2:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    autoStartup = "${app.kafka.orders.auto-startup:true}"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

This value is evaluated during application context initialization. It is not a runtime toggle to turn a listener on/off after the application is already running. For runtime control, use `KafkaListenerEndpointRegistry` to retrieve the container and call `start()` or `stop()`.

One detail to note: endpoints registered after the application context has refreshed may start immediately regardless of `autoStartup`, unless the registry's `alwaysStartAfterRefresh` behavior is changed. Do not rely on `autoStartup=false` as a guarantee that late-registered endpoints will always remain stopped.

## 7. Placeholders, SpEL, and the __listener pseudo bean

Most annotation attributes support property placeholders or SpEL:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "${app.kafka.orders.topic}",
    groupId = "${app.kafka.orders.group}",
    concurrency = "${app.kafka.orders.concurrency:2}"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Since 2.1.2, SpEL supports the `__listener` pseudo bean, pointing to the bean declaring the listener itself:

~~~java
@Component
public class TenantOrderListener {

    private final String topic;

    public TenantOrderListener(
            @Value("${app.kafka.tenant-topic}") String topic) {
        this.topic = topic;
    }

    @KafkaListener(
        topics = "#{__listener.topic}",
        groupId = "#{__listener.topic}.billing"
    )
    public void listen(OrderCreated event) {
        billingService.process(event);
    }

    public String getTopic() {
        return topic;
    }
}
~~~

If the application has an actual bean named `__listener`, you can rename the pseudo bean token using the `beanRef` attribute:

~~~java
@KafkaListener(
    beanRef = "__current",
    topics = "#{__current.topic}"
)
~~~

Use placeholders for simple configuration and SpEL when dynamic expressions are needed. Do not put complex business logic inside annotations; that makes configuration harder to test and observe.

## 8. properties only overrides appropriate consumer properties

Since 2.2.4, `properties` allows overriding certain Kafka consumer properties at the listener level:

~~~java
@KafkaListener(
    id = "slowOrdersListener",
    groupId = "billing-service",
    topics = "commerce.order.created",
    properties = {
        "max.poll.interval.ms=60000",
        "max.poll.records=100"
    }
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Properties in the annotation override same-named properties from the consumer factory if the factory supports property overrides. However, do not put `group.id` or `client.id` in `properties`; those values are ignored. Use `groupId` and `clientIdPrefix` instead.

Do not repeat the entire consumer configuration on every listener. Keep common settings in the factory and only override values that truly differ.

## 9. topics, topicPattern, and topicPartitions

The three subscription mechanisms are mutually exclusive. A listener must choose exactly one.

### 9.1. Subscribe by topic

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = {
        "commerce.order.created",
        "commerce.order.cancelled"
    }
)
public void listen(OrderEvent event) {
    orderService.process(event);
}
~~~

The Kafka group coordinator distributes partitions across the consumer group.

### 9.2. Subscribe by regex

~~~java
@KafkaListener(
    id = "tenantEventsListener",
    topicPattern = "^tenant\\..*\\.events$"
)
public void listen(TenantEvent event) {
    tenantService.process(event);
}
~~~

Patterns are useful when topics are created dynamically following naming conventions. The Kafka client refreshes metadata periodically and the subscription picks up matching topics.

### 9.3. Manual partition assignment

~~~java
@KafkaListener(
    id = "ordersPartitionListener",
    topicPartitions = @TopicPartition(
        topic = "commerce.order.created",
        partitions = { "0", "1" }
    )
)
public void listen(ConsumerRecord<String, OrderCreated> record) {
    orderService.process(record.value());
}
~~~

With manual assignment, the application explicitly determines which partitions the listener receives. Do not use `topics` or `topicPattern` together with `topicPartitions`.

Since 2.5.5, the wildcard `*` in `@PartitionOffset` can apply an initial offset to all declared partitions. Since 2.6.4, lists or ranges such as `0-5,7,10-12` can be declared. Since 3.2, `@PartitionOffset` supports `seekPosition` with values such as `BEGINNING`, `END`, and `TIMESTAMP`.

Example of seeking by timestamp:

~~~java
@KafkaListener(
    id = "ordersFromTimestamp",
    topicPartitions = @TopicPartition(
        topic = "commerce.order.created",
        partitionOffsets = {
            @PartitionOffset(
                partition = "0",
                initialOffset = "1735689600000",
                seekPosition = "TIMESTAMP"
            )
        }
    )
)
public void listen(ConsumerRecord<String, OrderCreated> record) {
    orderService.process(record.value());
}
~~~

`initialOffset` means a timestamp when `seekPosition=TIMESTAMP`. When using `BEGINNING` or `END`, the numeric offset is no longer interpreted as an absolute offset. Thoroughly test seek behavior before deploying.

## 10. Method signature and record metadata

A listener method can accept a plain payload, `ConsumerRecord`, `Message<?>`, `Acknowledgment`, `Consumer<?, ?>`, and supported headers.

Since 2.5, you can accept `ConsumerRecordMetadata` instead of multiple separate headers:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void listen(
        OrderCreated event,
        ConsumerRecordMetadata metadata) {

    log.info(
        "topic={}, partition={}, offset={}",
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );

    billingService.process(event);
}
~~~

`ConsumerRecordMetadata` contains the record's metadata, but not its key and value. If you need the raw record, use `ConsumerRecord<K,V>`.

A minor change since 2.5: `KafkaHeaders.RECEIVED_KEY` is no longer added when a record has a null key. If a method parameter receives this header, mark it `required=false` or use a suitable nullable type.

## 11. Meta-annotations and configuration reuse

Since 2.2, `@KafkaListener` can be used as a meta-annotation to create custom domain annotations:

~~~java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public @interface BillingOrderListener {
}
~~~

`@AliasFor` can be used to let callers customize selected attributes of the underlying annotation:

~~~java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@KafkaListener
public @interface DomainKafkaListener {

    @AliasFor(annotation = KafkaListener.class, attribute = "topics")
    String[] topics();

    @AliasFor(annotation = KafkaListener.class, attribute = "groupId")
    String groupId() default "";
}
~~~

This approach is helpful when many listeners share conventions for groups, topics, or containers. Keep meta-annotations simple; avoid nested layers of annotations that make it hard for readers to tell where final values come from.

## 12. Batch listener: the batch attribute from 2.8

Before 2.8, choosing between a record listener and a batch listener was usually configured on the container factory. Starting in 2.8, `batch` can override `batchListener` directly on the method:

~~~java
@KafkaListener(
    id = "ordersBatchListener",
    topics = "commerce.order.created",
    containerFactory = "ordersListenerContainerFactory",
    batch = "true"
)
public void listen(List<OrderCreated> events) {
    billingService.processBatch(events);
}
~~~

The same factory can be used for both record listeners and batch listeners. If `batch` is not specified, the container factory decides.

The value of `batch` must be the literal `true` or `false`; property placeholders or SpEL are not supported because the listener type must be determined when creating the endpoint. A batch method typically accepts `List<?>`, not a single payload like a record listener.

Since 2.9.6, the factory has separate setters for `recordMessageConverter` and `batchMessageConverter`; previously a single `messageConverter` was shared for both types. When upgrading converter configurations, verify whether the application relies on the shared converter.

## 13. filter and info from 2.8.4

`filter` lets a listener choose a dedicated `RecordFilterStrategy`, overriding the filter on the factory:

~~~java
@KafkaListener(
    id = "priorityOrdersListener",
    topics = "commerce.order.created",
    filter = "priorityOrderFilter"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

`info` attaches static information to the `KafkaHeaders.LISTENER_INFO` header:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    info = "billing-order-consumer"
)
public void listen(
        OrderCreated event,
        @Header(KafkaHeaders.LISTENER_INFO) String listenerInfo) {
    log.debug("listenerInfo={}", listenerInfo);
    billingService.process(event);
}
~~~

This information can be used by a `RecordInterceptor`, `RecordFilterStrategy`, or the listener method. The listener info header is stripped when creating outbound records from input record headers, preventing internal metadata from accidentally leaking to other messages.

## 14. contentTypeConverter and splitIterables

`contentTypeConverter` was added in 2.7.1. It specifies a `SmartMessageConverter` bean to work with the `MessageHeaders.CONTENT_TYPE` header when converting the payload to the type required by the method.

Example of selecting the converter:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    contentTypeConverter = "orderContentTypeConverter"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

`splitIterables` has existed since 2.3.5 and applies to listeners whose return value is used as a reply. By default (`true`), an `Iterable` is split into multiple reply records. Set it to `false` to send the entire Iterable as the value of a single reply record:

~~~java
@KafkaListener(
    topics = "commerce.order.lookup",
    splitIterables = "false"
)
@SendTo("commerce.order.lookup.replies")
public List<OrderSummary> lookup(OrderLookup request) {
    return orderService.findSummaries(request);
}
~~~

Only change `splitIterables` when the reply contract requires a single record containing a collection. Verify the serializer/deserializer and reply consumer before changing this behavior.

## 15. Annotation errorHandler vs. container error handler

The `errorHandler` attribute on `@KafkaListener` takes a `KafkaListenerErrorHandler` bean name. It handles exceptions at the message listener adapter layer.

~~~java
@Bean
public KafkaListenerErrorHandler orderListenerErrorHandler() {
    return (message, exception) -> {
        log.error("Listener failed for message {}", message, exception);
        throw exception;
    };
}

@KafkaListener(
    topics = "commerce.order.created",
    errorHandler = "orderListenerErrorHandler"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Distinguish:

- `KafkaListenerErrorHandler`: attached on the annotation, at the listener method/message adapter layer.
- `CommonErrorHandler`: configured on the listener container factory, controlling retry, seek, recovery, and container-level error handling.

The return value of `KafkaListenerErrorHandler` is usually ignored; it is only used as a reply when the listener method has `@SendTo`. The handler can rethrow the exception so the container continues applying its error handling policy.

Do not use `errorHandler` as the attribute to configure `DefaultErrorHandler`. If you want container-level retry/DLT, configure `CommonErrorHandler` on the factory according to the Spring Kafka version.

## 16. containerPostProcessor from 3.1

`containerPostProcessor` lets you specify a `ContainerPostProcessor` bean to customize the container after it has been created and configured:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    containerPostProcessor = "ordersContainerPostProcessor"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Bean example:

~~~java
@Bean
public ContainerPostProcessor<String, OrderCreated,
        ConcurrentMessageListenerContainer<String, OrderCreated>>
        ordersContainerPostProcessor() {

    return container -> {
        container.getContainerProperties()
            .setShutdownTimeout(15_000L);
    };
}
~~~

`ContainerPostProcessor` applies to the current listener container. It runs after any `ContainerCustomizer` configured on the factory. Use it when only one listener needs bespoke adjustments; use `ContainerCustomizer` when you want to apply changes across all containers created by the factory.

## 17. Asynchronous return types from 3.2

Since 3.2, `@KafkaListener` and `@KafkaHandler` support asynchronous return types such as `CompletableFuture<?>`, `Mono<?>`, and Kotlin suspend functions.

~~~java
@KafkaListener(
    id = "asyncOrdersListener",
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public CompletableFuture<Void> listen(OrderCreated event) {
    return billingService.processAsync(event);
}
~~~

When the framework detects an asynchronous return type, the acknowledgment mode is automatically set to `MANUAL` and out-of-order commits are enabled; acknowledgment happens when the async operation completes. If the future completes with an error, retry/recovery depends on the container error handler.

There are three things to pay attention to:

1. Exceptions thrown before creating the future must be handled and returned as an appropriate async result; otherwise, the container cannot track completion via the async mechanism.
2. Invocations can run concurrently; side effects of a record with a later offset may complete before an earlier offset on the same partition.
3. If strict processing order is required, use a synchronous listener or design serialization by key. If async processing is required, side effects must be idempotent and have appropriate ordering controls.

Example of converting a synchronous error into a failed future so the container handles it via the error handler:

~~~java
@KafkaListener(topics = "commerce.order.created")
public CompletableFuture<Void> listen(OrderCreated event) {
    try {
        return billingService.processAsync(event);
    } catch (RuntimeException exception) {
        return CompletableFuture.failedFuture(exception);
    }
}
~~~

Do not merely change the method return type from `void` to `CompletableFuture` and assume commit behavior remains the same as a synchronous listener.

## 18. ackMode directly on the annotation from 4.1

Before 4.1, making a listener use a different acknowledgment mode from the factory usually required creating a separate container factory. Since 4.1, `ackMode` allows overriding it directly:

~~~java
@KafkaListener(
    id = "manualOrdersListener",
    topics = "commerce.order.created",
    groupId = "billing-service",
    ackMode = "MANUAL"
)
public void listen(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    billingService.process(event);
    acknowledgment.acknowledge();
}
~~~

`ackMode` is a String matching the `ContainerProperties.AckMode` enum name, case-insensitive. Property placeholders or SpEL can be used:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    ackMode = "${app.kafka.orders.ack-mode:RECORD}"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

This attribute is only available starting in Spring Kafka 4.1. Do not use it in 3.x or older applications because it will not compile. When using `MANUAL` or `MANUAL_IMMEDIATE`, the method signature can accept `Acknowledgment`; for other modes, do not expect this parameter to be provided.

`ackMode` only changes acknowledgment behavior. It does not create a transaction, nor does it make database side effects and Kafka offsets an atomic transaction unless an appropriate transaction manager is configured.

## 19. containerGroup and legacy compatibility changes

The `containerGroup` attribute previously created a collection bean containing listener containers for group control. Since 2.7.3, legacy Collection-typed beans were deprecated and replaced by a `ContainerGroup` bean named `containerGroup + ".group"`; the old Collection beans were removed in 2.8.

If legacy applications directly inject `Collection<MessageListenerContainer>` by group name, switch to `ContainerGroup` or use `KafkaListenerEndpointRegistry` to manage containers by ID.

Do not confuse `containerGroup` with `groupId`: one is a group of containers in the Spring context, the other is a Kafka consumer group.

## 20. Adjacent changes when upgrading to 3.x

Several changes are not attributes of `@KafkaListener` itself, yet directly affect listener code.

### 20.1. KafkaHeaders constants

In 3.0, constants deprecated since 2.9 were removed:

| Old constant | Replacement constant |
|---|---|
| `KafkaHeaders.MESSAGE_KEY` | `KafkaHeaders.KEY` |
| `KafkaHeaders.PARTITION_ID` | `KafkaHeaders.PARTITION` |
| `KafkaHeaders.RECEIVED_MESSAGE_KEY` | `KafkaHeaders.RECEIVED_KEY` |
| `KafkaHeaders.RECEIVED_PARTITION_ID` | `KafkaHeaders.RECEIVED_PARTITION` |

If method signatures use `@Header` with the old constants, update imports and constant names before upgrading.

### 20.2. KafkaTemplate future

Starting in 3.0, the future returned by `KafkaTemplate` and `ReplyingKafkaTemplate` changed from `ListenableFuture` to `CompletableFuture`. Listeners that call a producer or reply template may need to update callbacks and return types.

### 20.3. Spring Kafka 4.0

4.0 upgrades the Kafka client to 4.0 and removes ZooKeeper-based infrastructure in the Kafka test framework; this is more of an ecosystem/testing change than a rewrite of `@KafkaListener`. Check the broker, embedded Kafka, dependencies, and test setup separately when upgrading major versions.

## 21. API selection table by version

| Need | Notable minimum version |
|---|---|
| `id` as default group ID | 2.0 |
| `clientIdPrefix` | 2.1.1 |
| `__listener` in SpEL | 2.1.2 |
| Override concurrency/autoStartup | 2.2 |
| Meta-annotations | 2.2 |
| Consumer `properties` per listener | 2.2.4 |
| `splitIterables` | 2.3.5 |
| `ConsumerRecordMetadata` | 2.5 |
| Wildcard initial offset | 2.5.5 |
| Partition ranges | 2.6.4 |
| `contentTypeConverter` | 2.7.1 |
| Method-level batch | 2.8 |
| `filter` and `info` | 2.8.4 |
| `containerPostProcessor` | 3.1 |
| Async return types | 3.2 |
| `seekPosition` on `@PartitionOffset` | 3.2 |
| `ackMode` on annotation | 4.1 |

This table shows the minimum milestones for the mentioned APIs, not a complete compatibility matrix for Spring Boot, Spring Framework, and the Kafka client.

## 22. Migration workflow when upgrading

Perform the upgrade in order:

1. Record the current Spring Kafka, Spring Boot, Spring Framework, and Kafka client versions.
2. Find all `@KafkaListener`, `@KafkaHandler`, meta-annotations, and related custom annotations.
3. Audit listeners with only `id` to determine their actual group ID under 2.0+ semantics.
4. Check `containerFactory`, `concurrency`, `autoStartup`, `properties`, and `batch`.
5. Search for deprecated/removed `KafkaHeaders` constants.
6. Check method signatures using key/partition headers and nullable keys.
7. Check whether listeners return `CompletableFuture`, `Mono`, or use manual acknowledgment.
8. Only use `containerPostProcessor` from 3.1+ and `ackMode` from 4.1+.
9. Update the test broker and test framework according to the new Kafka client version.
10. Run integration tests with old records, new records, batches, retry, DLT, and transactions.
11. Monitor consumer groups, committed offsets, lag, and deserialization errors after rollout.

Do not upgrade Spring Kafka in isolation while ignoring dependency alignment. Use the appropriate Spring Boot dependency management/BOM or check the official compatibility table before overriding versions.

## 23. Testing @KafkaListener upgrades

There should be tests for each category of changes:

| Category | What to confirm |
|---|---|
| `id`/`groupId` | Listener joins the right consumer group and preserves expected offsets |
| `topics`/`topicPattern` | Subscribes to the right topics and discovers new topics matching the pattern |
| `topicPartitions` | Assignment and initial offsets are correct |
| `concurrency` | Consumer count and partition assignment are correct |
| `autoStartup` | Container starts at the expected time |
| `batch` | Method receives the expected list payload type |
| `filter` | Records are discarded according to the strategy |
| `info` | Listener info header is present and does not leak outbound |
| `ackMode` | Offsets commit according to the mode |
| Async return | Ack occurs only after completion; errors route through the error handler |
| `containerPostProcessor` | Specific container is customized after the factory customizer |
| Header migration | Method receives the right key, partition, topic, and offset |
| Retry/DLT | Exceptions are classified, retried, and recovered according to policy |

Use EmbeddedKafka or Testcontainers to test against a real broker. For async listeners, use futures/latches to wait for completion; do not use fixed `Thread.sleep()`. For group IDs, verify committed offsets rather than only asserting the method was invoked.

## 24. Common issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| After upgrade, listener reads different offsets | `id` became `group.id` under 2.0 semantics | Explicitly declare `groupId` or set `idIsGroup=false` |
| Annotation does not compile | Using a newer attribute on an older version | Check the version milestone of the attribute |
| `Acknowledgment` is null | Factory/listener is not in manual ack mode | Use an appropriate manual mode; 4.1 can override `ackMode` |
| `batch=true` but method accepts single payload | Method signature does not match batch listener | Accept `List<?>` or remove batch |
| `properties` does not change group/client ID | Those two properties are ignored inside annotation `properties` | Use `groupId` and `clientIdPrefix` |
| Listener starts despite autoStartup false | Endpoint registered after context refresh | Check registry lifecycle and registration timing |
| Async listener commits early or side effects out of order | Misunderstanding async acknowledgment/parallel completion | Follow the async contract properly, enforce idempotency, and handle ordering |
| KafkaHeaders constant not found | Constant was removed in 3.0 | Use the replacement constant |
| Filter does not run with ConsumerRecords listener | Record filter does not support that listener shape | Use `List<?>` if batch filtering is needed |
| `containerPostProcessor` does not exist | Running on a version prior to 3.1 | Customize via factory/ContainerCustomizer |
| `ackMode` does not exist | Running on a version prior to 4.1 | Create a separate factory and set ContainerProperties AckMode |

## 25. Pre-release checklist

- [ ] Confirmed the exact target Spring Kafka version?
- [ ] Audited `id`, `groupId`, and `idIsGroup`?
- [ ] Verified subscriptions choose only one of `topics`, `topicPattern`, or `topicPartitions`?
- [ ] Placeholders and SpEL resolve properly?
- [ ] `properties` does not contain `group.id` or `client.id`?
- [ ] Batch methods accept the right signature?
- [ ] `Acknowledgment` is only used when the ack mode supports it?
- [ ] Async listeners handle completion, errors, and ordering?
- [ ] `filter`, `info`, `containerPostProcessor`, `ackMode` are available in the running version?
- [ ] Replaced removed KafkaHeaders constants?
- [ ] Verified group IDs and committed offsets after upgrading?
- [ ] Tested retry, DLT, transactions, and shutdown?
- [ ] Aligned Spring Boot, Spring Framework, and the Kafka client?
- [ ] Have a rollback plan if consumers cannot read records after rollout?

## Conclusion

The `@KafkaListener` API has expanded steadily across Spring Kafka versions. The most impactful changes are the relationship between `id` and `groupId` since 2.0, overriding concurrency/autoStartup since 2.2, per-listener properties since 2.2.4, batch/filter/info in 2.8, container post-processor since 3.1, asynchronous returns and seek position since 3.2, and `ackMode` directly on the annotation since 4.1.

When upgrading, identify the target version and audit each attribute and method signature. Pay special attention to group IDs because they determine the offset namespace, async listeners because they affect acknowledgment and side-effect ordering, and `ackMode` because it is only available in 4.1 and above. Keep shared configuration in the container factory, override on the annotation only when a listener truly has bespoke needs, then verify via integration tests with a Kafka broker and monitor committed offsets/consumer lag during rollout.

## References

- Spring Kafka Reference — @KafkaListener Annotation: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html
- Spring Kafka Reference — Change History: https://docs.spring.io/spring-kafka/reference/appendix/change-history.html
- Spring Kafka API — KafkaListener Javadoc: https://docs.spring.io/spring-kafka/docs/4.1.2/api/org/springframework/kafka/annotation/KafkaListener.html
- Spring Kafka Reference — Asynchronous @KafkaListener Return Types: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/async-returns.html
