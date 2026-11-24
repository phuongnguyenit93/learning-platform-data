# alwaysClientIdSuffix in Spring Kafka

`alwaysClientIdSuffix` is a property on `ConcurrentMessageListenerContainer` that determines whether to always append a suffix to the child consumer's `client.id` when the container runs with a concurrency of 1.

When a concurrent container manages multiple consumers, Spring Kafka needs to generate a distinct `client.id` for each child consumer to make metrics, logs, and broker-side activity easy to identify. The suffix typically takes the form `-0`, `-1`, `-2` by consumer index. When concurrency is greater than 1, the suffix is added so child consumers have distinct IDs. `alwaysClientIdSuffix` controls the special case where concurrency is only 1: whether to keep the `-0` suffix or omit it.

This property serves consumer identification and observability. It does not increase consumer count, create more partitions, change the consumer group, or determine how Kafka distributes partitions.

## 1. Why Is a Client ID Suffix Needed?

A `ConcurrentMessageListenerContainer` can manage multiple child `KafkaMessageListenerContainer` instances. Each child container creates and controls its own Kafka consumer.

Suppose a listener is configured with:

- `clientIdPrefix = "orders-consumer"`
- `concurrency = 3`

Spring Kafka creates three consumers. To distinguish them, the client IDs can be:

| Child consumer | Client ID |
|---:|---|
| 0 | `orders-consumer-0` |
| 1 | `orders-consumer-1` |
| 2 | `orders-consumer-2` |

With separate IDs, operations teams can see which consumer has lag, which consumer is processing which partitions, and which consumer shows abnormal metrics.

Without suffixes, child consumers might share the same client ID prefix. This reduces the ability to distinguish them in logs and metrics, and can make client-ID-based quota policies harder to control.

## 2. Distinguishing client.id from group.id

These two properties often appear side by side in consumer configurations, yet serve different purposes.

| Property | Role | Primary impact |
|---|---|---|
| `group.id` | Identifies the consumer group | Group membership, partition assignment, committed offsets |
| `client.id` | Identifies a Kafka client | Broker logs, metrics, and quotas by client ID |
| `clientIdPrefix` | Prefix Spring Kafka uses to build client IDs | Client ID names of container-created consumers |
| `alwaysClientIdSuffix` | Controls whether to keep the suffix when concurrency is 1 | Client ID formatting of child consumers |

For example:

- Two consumers with the same `group.id` can join the same consumer group and share partition-reading responsibilities.
- Two consumers with the same `client.id` do not belong to the same consumer group because of that.
- Changing `alwaysClientIdSuffix` does not change `group.id`, committed offsets, or partition assignment rules.

Kafka uses `group.id` to coordinate consumers in the same group. `client.id` is the client identifier at the broker communication layer. Do not use client ID in place of group ID when designing consumer groups.

## 3. How Does alwaysClientIdSuffix Work?

`alwaysClientIdSuffix` is a property on `ConcurrentMessageListenerContainer`. In current Spring Kafka documentation, the default value is `true`. When concurrency is 1, `true` still appends the `-0` suffix; setting `false` omits the suffix in this case.

When concurrency is greater than 1, Spring Kafka still appends suffixes to distinguish individual child consumers, even when `alwaysClientIdSuffix` is `false`.

| Concurrency | alwaysClientIdSuffix | Client IDs generated from prefix `orders-consumer` |
|---:|---|---|
| 1 | `true` | `orders-consumer-0` |
| 1 | `false` | `orders-consumer` |
| 3 | `true` | `orders-consumer-0`, `orders-consumer-1`, `orders-consumer-2` |
| 3 | `false` | `orders-consumer-0`, `orders-consumer-1`, `orders-consumer-2` |

You can remember the rule as follows:

- Concurrency equal to 1: the property decides whether `-0` is appended.
- Concurrency greater than 1: suffixes are still added so each child consumer has a unique ID.
- Concurrency is the maximum number of child consumers managed by the concurrent container; the suffix is not a partition number.

The `setAlwaysClientIdSuffix(boolean)` property has been available since Spring Kafka 2.2.14. When deploying on older versions, check the corresponding API before using it.

## 4. Configuring with @KafkaListener

For listeners created by `ConcurrentKafkaListenerContainerFactory`, you can use a `ContainerCustomizer` to configure the concurrent container after the factory creates it.

The following example sets concurrency to 1 and keeps the suffix on the client ID:

```java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersListenerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(1);

        factory.setContainerCustomizer(container ->
                container.setAlwaysClientIdSuffix(true)
        );

        return factory;
    }
}
```

Listener declaring the prefix:

```java
@Component
public class OrdersListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "orders-service",
        clientIdPrefix = "orders-consumer",
        containerFactory = "ordersListenerFactory"
    )
    public void onOrderCreated(OrderCreated event) {
        // Process event
    }
}
```

With concurrency equal to 1 and the suffix enabled, the consumer's client ID is `orders-consumer-0`.

`ContainerCustomizer` allows modifying the container after the factory has created and configured it. This API has been available since Spring Kafka 2.3.4. If using a version from 2.2.14 up to before 2.3.4, configure it directly on a `ConcurrentMessageListenerContainer` created by the application.

If the application has multiple listener factories, the customizer applies only to the configured factory. Verify that the listener declares the right `containerFactory`.

## 5. When Should the Suffix Be Disabled?

The default `true` is usually helpful because it maintains a consistent naming convention between listeners running with concurrency 1 and listeners with concurrency greater than 1.

You can disable the suffix if a monitoring system, quota rule, or operational convention relies on an unsuffixed client ID when there is only one consumer.

Example:

```java
factory.setContainerCustomizer(container ->
        container.setAlwaysClientIdSuffix(false)
);
```

With concurrency equal to 1 and prefix `orders-consumer`, the client ID will be `orders-consumer`.

If concurrency is later increased to 3, the client IDs still carry suffixes:

```text
orders-consumer-0
orders-consumer-1
orders-consumer-2
```

Therefore, setting `false` does not mean disabling the suffix in all cases. It only suppresses the suffix when concurrency is 1.

Do not disable the suffix merely for shorter client ID names if operations relies on suffixes to separate metrics or quotas. Before changing it, identify everything that depends on the current client ID.

## 6. Configuring the Container Directly

If not using `@KafkaListener` and constructing the container directly, call the setter directly on the concurrent container:

```java
ContainerProperties containerProperties =
        new ContainerProperties("orders.created");

containerProperties.setClientId("orders-consumer");

ConcurrentMessageListenerContainer<String, OrderCreated> container =
        new ConcurrentMessageListenerContainer<>(
                consumerFactory,
                containerProperties
        );

container.setConcurrency(1);
container.setAlwaysClientIdSuffix(true);
container.setMessageListener(
        (MessageListener<String, OrderCreated>) record -> {
            orderService.process(record.value());
        }
);
```

In this example:

- `ContainerProperties.setClientId("orders-consumer")` sets the prefix for `client.id`.
- `setConcurrency(1)` creates one child consumer.
- `setAlwaysClientIdSuffix(true)` keeps the `-0` suffix.
- The listener is attached directly to the container.

The container must be registered and lifecycle-managed appropriately in Spring, such as declaring it as a bean so Spring manages start/stop. Do not manually instantiate a container inside a request method and forget to stop it.

## 7. Where Does clientIdPrefix Come From?

Spring Kafka can obtain the prefix from multiple configuration locations. Standardize on one source to avoid confusion when inspecting actual client IDs.

### 7.1. Prefix on @KafkaListener

`@KafkaListener` supports the `clientIdPrefix` attribute:

```java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "orders-service",
    clientIdPrefix = "orders-consumer"
)
public void listen(OrderCreated event) {
    // ...
}
```

This is a clear approach when each listener has its own prefix.

### 7.2. Prefix on ContainerProperties

For directly constructed containers, the prefix can be set on `ContainerProperties`:

```java
ContainerProperties properties =
        new ContainerProperties("orders.created");

properties.setClientId("orders-consumer");
```

According to Spring Kafka documentation, `ContainerProperties.clientId` serves as the prefix for the consumer `client.id` property and can override the `client.id` value provided by `ConsumerFactory`.

### 7.3. Prefix in the Consumer Factory

A Kafka consumer factory can also receive `ConsumerConfig.CLIENT_ID_CONFIG` in its properties. If the container has its own client ID prefix, the container's prefix is used to construct client IDs according to listener container rules.

Avoid configuring multiple different prefixes for the same listener without clearly knowing precedence. When diagnosing, inspect the actual client ID from consumer metrics or logs.

## 8. Relationship with Concurrency and Partition Assignment

`alwaysClientIdSuffix` is commonly discussed in the concurrency chapter because each child consumer needs a distinguishable client ID. However, the suffix does not determine concurrency.

For example, the `orders.created` topic has 4 partitions:

```text
Topic: orders.created
Partitions: 0, 1, 2, 3
Concurrency: 3

orders-consumer-0  -> one or more partitions
orders-consumer-1  -> one or more partitions
orders-consumer-2  -> one or more partitions
```

Actual partition assignment is decided by the group coordinator and partition assignor. You cannot conclude that consumer `-0` always gets partition 0; the suffix index is a child container index, not a partition number.

If concurrency exceeds the partition count, some child consumers may receive no partitions. Those consumers still have distinct client IDs, but do not process records from that topic under the current assignment.

Example:

| Partition count | Concurrency | Consumers able to receive partitions |
|---:|---:|---:|
| 6 | 3 | Up to 3 |
| 3 | 3 | Up to 3 |
| 2 | 4 | Up to 2 |
| 1 | 4 | Up to 1 |

The table above assumes a single topic and a single consumer group; specific assignments also depend on subscriptions, the assignor, and any other topics the consumers subscribe to.

Changing `alwaysClientIdSuffix` does not alter these numbers. To increase parallel processing capacity, evaluate partition count, concurrency, processing capability, and dependency limits.

## 9. Using Client ID for Observability and Operations

Client ID is useful when operations teams need to identify which consumer generates metrics or broker requests.

Use cases:

- Distinguishing metrics of individual child consumers.
- Locating the corresponding consumer in broker logs.
- Tracking request rate and latency per client.
- Enforcing or investigating quotas by client ID.
- Correlating child consumers with partition assignments when investigating lag.
- Comparing behavior across child containers within the same listener.

`ConcurrentMessageListenerContainer.metrics()` exposes child consumer metrics grouped by client ID. This allows operations teams to distinguish metrics between `orders-consumer-0`, `orders-consumer-1`, and other consumers.

Client ID is only one piece of observability. When investigating a consumer, combine client ID with group ID, topic, partition, offset, host/pod, listener ID, and incident timestamp.

### Client ID and Quotas

Kafka can enforce quotas by client ID. When changing the suffix, the actual client ID name changes as well. If brokers configure quotas for a specific client ID, verify whether quota rules still match the new IDs.

For example, a quota applied to `orders-consumer` may not apply the same way to `orders-consumer-0` if the broker matches exact client ID names. Check actual quota configuration and cluster matching rules before making changes.

### Client ID and Multiple Application Instances

The suffix only distinguishes child consumers within a single concurrent container. If an application runs across multiple pods and every pod uses the same prefix, each pod can still produce identical IDs like `orders-consumer-0`.

If you need to distinguish clients per instance, include a stable deployment-instance value in the prefix, for example:

```text
orders-consumer-pod-a-0
orders-consumer-pod-b-0
```

You can use pod name or an instance identifier suited to your deployment platform. Ensure the prefix value does not change unexpectedly and frequently, as that fragments metrics across many different client IDs.

## 10. Verifying Actual Client IDs

Do not merely infer client IDs from configuration. Confirm the actual value used when consumers are created.

### 10.1. Enable Container Configuration Logging

You can enable container configuration logging to assist startup verification:

```java
factory.getContainerProperties().setLogContainerConfig(true);
```

This log is useful for confirming container settings, though it does not replace checking Kafka consumer metrics.

### 10.2. Inspect Metrics by Client ID

With a concurrent container, metrics are grouped by client ID:

```java
Map<String, Map<MetricName, ? extends Metric>> metrics =
        container.metrics();

metrics.forEach((clientId, clientMetrics) -> {
    log.info(
        "Kafka client id={}, metric count={}",
        clientId,
        clientMetrics.size()
    );
});
```

The exact return type may vary by Kafka client/Spring Kafka version. This example illustrates the idea of reading the metrics map; when compiling, use the exact generic types for your dependency version.

### 10.3. Cross-Check with Broker Metrics and Logs

Once clients connect to brokers, inspect metrics or logs tagged with client ID. Confirm:

- Prefix matches listener configuration.
- Suffix is present or absent according to concurrency and `alwaysClientIdSuffix`.
- Child consumers in the same container have distinct IDs when concurrency exceeds 1.
- Client IDs do not accidentally collide with another listener if operations needs per-listener metrics.
- Client-ID-based quotas still apply properly after changes.

## 11. Common Mistakes and Misconceptions

**Thinking alwaysClientIdSuffix is a property on ContainerProperties.** This property resides on `ConcurrentMessageListenerContainer`. For factory-created listeners, use `ContainerCustomizer` or the corresponding container customization hook.

**Setting false and expecting suffixes to disappear when concurrency is greater than 1.** The setter only suppresses the suffix when concurrency equals 1. With concurrency greater than 1, suffixes remain necessary to distinguish child consumers.

**Assuming the suffix is a partition number.** The suffix denotes the child container index, not a Kafka-assigned partition. Partition assignment can change after a rebalance.

**Assuming the suffix creates additional consumers.** `alwaysClientIdSuffix` only alters client ID naming. Consumer count is governed by concurrency.

**Confusing client.id with group.id.** Client ID handles client identification; group ID controls consumer group membership and offsets. Changing one does not automatically alter the other.

**Using the same prefix across multiple listeners.** Two listeners can generate identical client IDs if their prefix and suffix indices collide. Choose distinct prefixes when per-listener observability is needed.

**Assuming the suffix distinguishes pods.** The suffix only distinguishes child consumers within one container. Pods running identical configs can still create identical client IDs; add an instance identifier to the prefix if needed.

**Changing the suffix without checking quotas.** Broker quotas may rely on client ID. After renaming, quota matching and limit distribution can change.

**Configuring a customizer on a factory not used by the listener.** Verify the factory name in `@KafkaListener` and inspect runtime client IDs.

## 12. Testing alwaysClientIdSuffix

Test both concurrency equal to 1 and concurrency greater than 1. Merely confirming that a listener receives messages does not prove the suffix is generated properly.

An integration test scenario:

1. Start a Kafka broker for testing.
2. Create a topic with enough partitions for the test concurrency.
3. Create a listener container factory with a defined `clientIdPrefix`.
4. Configure concurrency to 1 and enable `alwaysClientIdSuffix`.
5. Start the container, wait for the consumer to be created, and read metrics.
6. Confirm the client ID ends with `-0`.
7. Switch to `alwaysClientIdSuffix=false`, restart the container, and confirm the suffix is omitted while concurrency remains 1.
8. Set concurrency to 3 and confirm child consumers still carry suffixes `-0`, `-1`, `-2` even when the property is false.
9. Inspect partition assignments separately to demonstrate that the suffix does not represent a partition.
10. If brokers enforce client-ID quotas, verify quota matching against the updated client ID names.

Expected results table:

| Test | Concurrency | alwaysClientIdSuffix | Expected result |
|---|---:|---|---|
| A | 1 | true | One client ID with suffix `-0` |
| B | 1 | false | One client ID without suffix |
| C | 3 | true | Three client IDs with suffixes `-0`, `-1`, `-2` |
| D | 3 | false | Three client IDs still with suffixes `-0`, `-1`, `-2` |

When reading metrics, wait for the consumer to start and connect to the broker. Do not inspect the metrics map immediately upon factory creation because consumers may not have been created yet at that moment.

## 13. Choosing the Right Production Configuration

Keep the suffix enabled when you want consistent client IDs that are easy to distinguish across child containers. This is also the default value described in current Spring Kafka documentation.

Only disable the suffix at concurrency 1 when there is a specific operational reason, such as an existing quota rule or dashboard relying on an unsuffixed client ID. Before changing, check broker quotas, dashboards, alerts, and logging conventions.

If you need to identify individual consumers across multiple pods, combine the prefix with an instance identifier. Do not expect internal suffixes to guarantee cluster-wide uniqueness on their own.

When concurrency changes due to load or deployment configuration, check both actual client IDs and partition assignments together. Suffixes help observe individual consumers; they do not guarantee a consumer keeps the same partitions after a rebalance.

## 14. Summary of Rules to Remember

- `alwaysClientIdSuffix` belongs to `ConcurrentMessageListenerContainer`.
- The property governs whether to append a suffix when concurrency is 1.
- The default value in current Spring Kafka is `true`.
- When concurrency is greater than 1, suffixes are still appended to distinguish child consumers.
- `clientIdPrefix` provides the prefix for `client.id`.
- `client.id` serves identification, metrics, logs, and quotas; `group.id` controls the consumer group.
- Suffixes are not partition IDs and do not alter partition assignment.
- Use `ContainerCustomizer` on the factory to apply the setting to listeners created by `@KafkaListener`.
- Include an instance identifier in the prefix if consumers must be distinguished across pods.

## 15. Version-Specific References

When implementing, cross-check documentation for your exact Spring Kafka and Kafka client versions:

- Spring for Apache Kafka Reference — Listener Container Properties: describes `clientId`, `clientIdSuffix`, and `alwaysClientIdSuffix`.
- Spring for Apache Kafka Reference — Container Factory: describes `ContainerCustomizer` and customizing factory-created containers.
- Spring Kafka Javadoc — `ConcurrentMessageListenerContainer`: APIs `setAlwaysClientIdSuffix(boolean)`, `setConcurrency(int)`, and child consumer metrics.
- Apache Kafka documentation — Consumer Config: `client.id`, `group.id`, and consumer properties.

`setAlwaysClientIdSuffix(boolean)` has been provided since Spring Kafka 2.2.14; `ContainerCustomizer` has been provided since 2.3.4. Prefer the Spring Kafka version managed by Spring Boot dependency management and check the corresponding Javadoc if the application runs an older version.
