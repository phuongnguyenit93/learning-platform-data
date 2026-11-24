# ContainerCustomizer in Spring Kafka

`ContainerCustomizer` is a hook that allows customizing a listener container after `KafkaListenerContainerFactory` creates and configures it. With this hook, an application can configure container-level operational properties without writing a custom listener container or repeating configuration in every `@KafkaListener` method.

In Spring Kafka, the factory is responsible for creating containers for endpoints. `ContainerCustomizer` receives the newly created container to add settings such as poll timeout, acknowledgment mode, or idle event interval. Because the customizer is attached to the factory, it applies to containers created by that factory.

## 1. Where does ContainerCustomizer fit in the architecture?

A `@KafkaListener` method declares a message-receiving endpoint. Spring Kafka turns the endpoint into a listener container via `KafkaListenerContainerFactory`. The factory uses `ConsumerFactory` to create Kafka consumers and applies operational settings. `ContainerCustomizer` is the extension point for adjusting the container after the factory's configuration step.

```mermaid
flowchart TD
    A[@KafkaListener endpoint] --> B[KafkaListenerContainerFactory]
    B --> C[Create listener container]
    C --> D[Apply factory and endpoint configuration]
    D --> E[ContainerCustomizer.configure(container)]
    E --> F[Configured listener container]
    F --> G[ConsumerFactory creates Kafka consumer]
    G --> H[Subscribe, poll, and invoke listener]
```

The components have distinct responsibilities:

| Component | Responsibility |
|---|---|
| `@KafkaListener` | Declares topics, group ID, listener style, and endpoint-level options |
| `ConsumerFactory` | Creates Kafka consumers with bootstrap servers, deserializers, and Kafka client properties |
| `KafkaListenerContainerFactory` | Creates listener containers and applies shared listener configurations |
| `ContainerCustomizer` | Modifies the container after the factory has created and configured it |
| `MessageListenerContainer` | Manages consumer lifecycle, polling, listener invocation, and acknowledgment |
| `ContainerProperties` | Holds container operational properties such as ack mode, poll timeout, and idle events |

`ContainerCustomizer` does not replace `ConsumerFactory`, does not create topics itself, and does not replace processing logic in the listener. It operates on the container produced by the factory.

## 2. Declaring a basic ContainerCustomizer

The `ContainerCustomizer<C extends MessageListenerContainer>` interface has a single method `configure(C container)`. You can pass a lambda directly to the factory:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);

        factory.setContainerCustomizer(container -> {
            container.getContainerProperties().setPollTimeout(2_000L);
            container.getContainerProperties()
                    .setAckMode(ContainerProperties.AckMode.RECORD);
        });

        return factory;
    }
}
```

In the example:

- `setContainerCustomizer(...)` registers the customization function with the factory.
- `container` is the listener container the factory just created.
- `getContainerProperties()` returns the container's operational configuration.
- `setPollTimeout(2_000L)` sets the maximum wait time for polling in milliseconds.
- `AckMode.RECORD` instructs the container to commit after each record is successfully processed, according to the configured acknowledgment and commit mechanism.

For a listener to use this factory, declare the bean name on the annotation:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    // Process event.
}
```

If a listener omits `containerFactory`, Spring Kafka uses the default factory by convention, usually `kafkaListenerContainerFactory`. Ensure the name in the annotation matches the registered bean name exactly.

## 3. Customizing ContainerProperties

`ContainerProperties` is where many listener container behaviors are configured. A customizer can retrieve this object from the container and adjust the required values.

Several commonly examined properties:

| Property | Meaning | Operational impact |
|---|---|---|
| `pollTimeout` | Wait time for a single poll | Affects how long the container waits for data and responsiveness on empty polls |
| `ackMode` | How the container commits offsets | Determines commit timing after listener processing |
| `idleEventInterval` | Interval for emitting idle events when the container receives no records | Helps detect listeners with little or no traffic |
| `shutdownTimeout` | Wait time when the container stops | Affects wait duration during shutdown handling |

Example adding idle event configuration:

```java
factory.setContainerCustomizer(container -> {
    ContainerProperties properties = container.getContainerProperties();
    properties.setPollTimeout(1_500L);
    properties.setAckMode(ContainerProperties.AckMode.RECORD);
    properties.setIdleEventInterval(60_000L);
});
```

Idle events can help observe a listener receiving no records over a period of time. They do not prove the consumer is failing: the topic may simply have no data. Applications should distinguish idle state from connection errors or rising consumer lag.

Setters and data types on `ContainerProperties` may vary across Spring Kafka versions. Verify the API of the version in use before applying specific settings.

## 4. Registering a customizer as a separate bean

When customization logic is long or needs reuse, you can declare `ContainerCustomizer` as a separate bean instead of an inline lambda inside the factory:

```java
@Bean
public ContainerCustomizer<ConcurrentMessageListenerContainer<String, OrderCreated>>
        ordersContainerCustomizer() {

    return container -> {
        ContainerProperties properties = container.getContainerProperties();
        properties.setPollTimeout(2_000L);
        properties.setAckMode(ContainerProperties.AckMode.RECORD);
        properties.setIdleEventInterval(30_000L);
    };
}
```

Then inject the customizer into the factory:

```java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                ContainerCustomizer<ConcurrentMessageListenerContainer<String, OrderCreated>>
                        ordersContainerCustomizer) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setContainerCustomizer(ordersContainerCustomizer);
    return factory;
}
```

The generic type of the customizer must match the container type created by the factory. For `ConcurrentKafkaListenerContainerFactory<K,V>`, the corresponding container is typically `ConcurrentMessageListenerContainer<K,V>`.

Extracting the customizer into its own bean makes configuration easier to test and read, especially when injecting a dependency solely for container setup. For a few simple configuration lines, a direct lambda inside the factory is usually easier to follow.

## 5. When is the customizer called?

The customizer is invoked by the factory during listener container creation, after the factory has applied factory and endpoint configurations. The container is customized before it begins processing records.

High-level flow:

1. Spring detects `@KafkaListener` and creates an endpoint.
2. The endpoint selects the corresponding `KafkaListenerContainerFactory`.
3. The factory creates the listener container.
4. The factory applies shared settings and endpoint options.
5. `ContainerCustomizer.configure(container)` is called.
6. The container is registered and started according to lifecycle/`autoStartup`.
7. The consumer begins subscribing and polling when the container runs.

Because the customizer runs at container creation time, it is not a callback invoked on every poll or every record. Do not place message-processing business logic, remote API calls, or heavy data queries inside `configure`.

If configuration changes after the container has been created, the customizer does not re-run automatically. To apply new settings, the application must update the container via supported APIs or recreate it through an appropriate lifecycle flow.

## 6. Scope of application: factory and listener

A `ContainerCustomizer` attached to a factory applies to listener containers created from that factory. If multiple listeners share the same factory, the customizer can affect all of them.

Example:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        sharedListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setContainerCustomizer(container ->
            container.getContainerProperties().setPollTimeout(2_000L));
    return factory;
}
```

Two listeners selecting `sharedListenerContainerFactory` will both receive this poll timeout setting:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-projection",
        containerFactory = "sharedListenerContainerFactory"
)
public void project(OrderCreated event) {
    // ...
}

@KafkaListener(
        topics = "orders.updated",
        groupId = "order-projection",
        containerFactory = "sharedListenerContainerFactory"
)
public void update(OrderUpdated event) {
    // ...
}
```

If two listener groups need different container configurations, create a dedicated factory for each group and attach the corresponding customizer. This keeps configuration scope explicit and avoids hard-to-manage conditional branches inside a shared customizer.

## 7. Distinguishing factory, annotation, and customizer configuration

Spring Kafka has several configuration layers. Pick the right place to avoid unintended overrides:

| Configuration location | Scope | Examples |
|---|---|---|
| `ConsumerFactory` | Created Kafka consumers | bootstrap servers, deserializers, `max.poll.records`, security |
| `KafkaListenerContainerFactory` | Containers created from the factory | default concurrency, common error handler, record converter |
| `@KafkaListener` | A specific endpoint | topics, group ID, auto-startup, container factory |
| `ContainerCustomizer` | Container created by the factory | extra settings on `ContainerProperties` or the container |
| Listener method | Record business logic | validate event, call service, persist data |

For instance, `max.poll.records` is a Kafka consumer property and usually belongs in `ConsumerFactory`/consumer properties. `pollTimeout` is a container property and belongs in `ContainerProperties`. `topics` is an endpoint subscription and belongs on `@KafkaListener`.

Do not use a customizer to replace all consumer configuration. Nor should you put business logic into a customizer, because this hook only prepares the container rather than processing individual records.

## 8. Configuration order and avoiding overrides

The factory may apply defaults, the annotation may provide endpoint-specific values, and the customizer can adjust the container after those configurations are applied. Because the customizer runs after the container is created, values it sets can override earlier settings on that container.

For example, if the factory sets `AckMode.BATCH`, but the customizer resets it to `AckMode.RECORD`, the final container uses the last-applied value. This can cause behavior to differ from what one expects when reading the factory or annotation.

To avoid hard-to-trace behavior:

- Pick one clearly responsible configuration source for each property.
- Use customizers for settings that genuinely need a container-level hook.
- Avoid setting the same property in the factory, annotation, and customizer without a specific reason.
- Document clearly whenever a customizer intentionally overrides a default value.
- Verify the actual container in integration tests if configuration order affects commits or lifecycle.

When upgrading Spring Kafka, re-check configuration application order in the new version, especially if the application relies on property overrides between annotations and customizers.

## 9. Splitting customizers by listener group

Because a customizer is tied to a factory, the clearest way to apply different settings to listener groups is to use separate factories. For example, a listener group needing short polls and a batch-processing listener group can use two factories:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        fastOrdersFactory(ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setContainerCustomizer(container ->
            container.getContainerProperties().setPollTimeout(500L));
    return factory;
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchOrdersFactory(ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setContainerCustomizer(container ->
            container.getContainerProperties().setPollTimeout(3_000L));
    return factory;
}
```

Each listener chooses the factory matching its needs:

```java
@KafkaListener(topics = "orders.fast", containerFactory = "fastOrdersFactory")
public void handleFast(OrderCreated event) {
    // ...
}

@KafkaListener(topics = "orders.batch", containerFactory = "batchOrdersFactory")
public void handleBatch(OrderCreated event) {
    // ...
}
```

This makes configuration scope clear right at the annotation. Some container versions may expose the listener ID so a customizer can branch, but check the actual API before relying on that capability. Avoid building multiple branches based on topic or bean name when two listener groups can simply use separate factories.

## 10. Distinguishing hooks at the container and consumer layers

`ContainerCustomizer` acts on the listener container created by the factory. It runs at the Spring Kafka container layer after the endpoint is configured.

Kafka consumers may have other hooks or configuration mechanisms to adjust the client when a consumer is created. Those mechanisms belong to the Kafka consumer layer, typically involving `ConsumerFactory` or consumer properties.

Distinguish by goal:

- Changing bootstrap servers, deserializers, security, or `max.poll.records`: configure consumer factory/properties.
- Adjusting `ContainerProperties`, lifecycle, or listener container behavior: use the factory or `ContainerCustomizer`.
- Transforming record data before/after the listener: consider an appropriate record interceptor or message converter.
- Handling business errors: configure an appropriate error handler/retry/recovery policy.

Do not use a customizer for work better managed by a dedicated component.

## 11. Integrating ContainerCustomizer with Spring Boot

Spring Boot usually creates a default `ConcurrentKafkaListenerContainerFactory` from `spring.kafka.*`. When a customizer is needed, you can declare a custom factory and select it on the listener.

Example:

```java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.setContainerCustomizer(container -> {
            ContainerProperties properties = container.getContainerProperties();
            properties.setPollTimeout(2_000L);
            properties.setAckMode(ContainerProperties.AckMode.RECORD);
        });
        return factory;
    }
}
```

The listener references the custom factory:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    // ...
}
```

If you want to customize the default factory, configure the bean in a way compatible with the auto-configuration mechanism of your Spring Boot version. Check the conditions on the default bean and avoid accidentally dropping Boot properties bound from `application.yml`.

When creating a custom factory, the application is responsible for configuring all required components such as consumer factory, converter, error handler, transaction manager, or other options the listener needs. Do not assume a self-declared factory automatically inherits every setting from the default factory.

## 12. Impact of container configuration on record processing

A customizer can indirectly influence how records are consumed. For example:

- Changing `AckMode` alters offset commit timing.
- Changing `pollTimeout` affects how long poll waits for data.
- Changing idle event interval affects how often idle events are emitted for observability.
- Changing shutdown timeout affects how long the container waits when stopping.

Do not change acknowledgment mode merely to reduce commits without assessing error handling consequences. With `RECORD`, the container commits after each successfully processed record per configured mechanics. With `BATCH`, the container commits after processing a batch per container rules. If a record fails, the error handler and recovery decide retries, recovery, and subsequent commits.

Similarly, increasing poll timeout does not increase `max.poll.records` and does not make the consumer process faster. These belong to two different layers: one is the container's poll wait duration, and the other limits how many records the Kafka client returns in a single poll.

## 13. Testing ContainerCustomizer

Verify that the customizer is attached to the right factory and container properties receive the expected values. Integration tests with a Spring context and embedded/Testcontainers broker work well here.

Example verifying container configuration via the registry:

```java
@SpringBootTest
@EmbeddedKafka(partitions = 1, topics = "orders")
class ContainerCustomizerIntegrationTest {

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @Test
    void shouldApplyContainerCustomizer() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        assertThat(container).isNotNull();
        assertThat(container.getContainerProperties().getPollTimeout())
                .isEqualTo(2_000L);
        assertThat(container.getContainerProperties().getAckMode())
                .isEqualTo(ContainerProperties.AckMode.RECORD);
    }
}
```

The test requires a listener with ID `orders-listener` using the factory registered with the customizer. When a container runs with concurrency greater than one, note that the registry returns the parent container; shared properties can be read from it, while child consumer behavior should be verified additionally when relevant.

Scenarios worth testing:

- The customizer is invoked when the factory creates the container.
- Listeners using the factory with the customizer receive the corresponding settings.
- Listeners using other factories are not unintentionally affected.
- Customizer properties override defaults as intended.
- Ack mode and error handling still yield the desired commit/retry outcomes.
- Container shutdown completes within the configured timeout.

Do not verify property values alone. For settings affecting commits, retries, or lifecycle, include integration tests proving actual listener behavior.

## 14. Common errors

**Customizer is not invoked:** the listener is using a different factory from the one with the customizer attached. Check `containerFactory` and the bean name.

**Mismatched generic types:** the customizer is declared for a different container type than the factory produces. Use the container type matching `ConcurrentKafkaListenerContainerFactory<K,V>`.

**Confused with ConsumerFactory:** `ContainerCustomizer` does not change bootstrap servers or deserializers. Move those settings to the consumer factory.

**Overridden configuration:** the factory or annotation sets one value and the customizer sets another afterward. Identify the final source of truth and test it.

**One customizer affects every listener:** multiple listeners share a factory and thus receive the same configuration. Split factories when distinct behavior is needed.

**Putting business logic in configure:** the customizer runs at container creation time, not per record. Move business logic to the listener or an appropriate interceptor.

**Performing slow I/O in the customizer:** container initialization takes longer and startup can stall. Only set properties; initialize dependencies in a separate lifecycle.

**Assuming changing the customizer updates a running container:** the customizer is called only during container creation. An update or container recreation process is required.

**Increasing poll timeout to fix consumer lag:** poll timeout does not replace `max.poll.records`, `max.poll.interval.ms`, or optimizing downstream processing.

**Testing only configuration without behavior:** right property values do not guarantee commits, retries, or shutdown work properly in practice.

## 15. Design checklist

- Does the listener genuinely need container-level customization, or are factory/consumer settings enough?
- Is the listener using the right `KafkaListenerContainerFactory` with the customizer attached?
- Does the generic type of `ContainerCustomizer` match the container type produced by the factory?
- Do the properties being customized belong to `ContainerProperties` or Kafka consumer properties?
- Does the customizer perform only fast, deterministic configuration without heavy I/O?
- Should all listeners sharing the factory receive the same settings?
- Are separate factories defined when listener groups require different configurations?
- Have conflicts between factory defaults, annotations, and the customizer been checked?
- Have ack mode changes been evaluated alongside retries, recovery, and commits?
- Do integration tests verify both the final configuration and container behavior?
- Does the Spring Kafka version in use support the APIs/setters shown?

`ContainerCustomizer` is an extension point at the listener container layer. Use it to finalize container configuration after the factory creates an endpoint, keeping consumer settings in `ConsumerFactory` and business processing in the listener. When factory boundaries are clear and overrides are tested, an application can standardize container behavior while keeping configuration easy to understand.
