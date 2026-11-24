# `client.id` When Using Concurrency

In Spring Kafka, a listener container can run multiple consumers concurrently via the `concurrency` property. Each consumer is a separate Kafka client and needs a sufficiently clear client ID to inspect logs, metrics, and per-consumer activity. Spring Kafka lets you set a client ID prefix and automatically appends a suffix for each child consumer.

For example, a listener with concurrency set to three and prefix `orders-listener` can create three consumers:

~~~text
orders-listener-0
orders-listener-1
orders-listener-2
~~~

`client.id` identifies a Kafka client in logs, metrics, and quota mechanisms. It does not determine the consumer group, does not decide partition assignments, and does not store offsets. Those responsibilities belong to `group.id` and Kafka's consumer group mechanism.

This lesson focuses on how Spring Kafka generates client IDs when using concurrency, how to configure them via `ConsumerFactory`, `ContainerProperties`, and `@KafkaListener`, how to name them when running multiple replicas, and how to use client IDs to monitor individual consumers.

## Learning Objectives

After this lesson, you can:

- Explain the role of `client.id` in a Kafka consumer.
- Distinguish between `client.id`, `group.id`, and the `id` of `@KafkaListener`.
- Describe how `ConcurrentMessageListenerContainer` creates child consumers.
- Explain the `-n` suffix appended by Spring Kafka to client IDs.
- Configure client IDs via `ConsumerFactory`, `ContainerProperties`, and `clientIdPrefix`.
- Understand configuration precedence when setting client IDs.
- Design client IDs when running multiple replicas or on Kubernetes.
- Observe metrics and partition assignments by client ID.
- Recognize duplicate client ID mistakes, hard-to-trace naming, and misconceptions about concurrency's effect.

## 1. What Is `client.id`?

`client.id` is a configuration property of the Kafka client. The consumer sends this value in requests to the broker so the broker can identify which client is making the request.

`client.id` is commonly used for:

- Tagging Kafka consumer metrics.
- Distinguishing requests and logs across clients.
- Applying client quotas per broker configuration.
- Naming JMX MBeans and avoiding name collisions among consumers in the same JVM.
- Operational troubleshooting when identifying which consumer instance is slow or failing.

Example:

~~~properties
bootstrap.servers=localhost:9092
group.id=order-service
client.id=orders-listener
~~~

In this example, the consumer belongs to group `order-service` and has client ID `orders-listener`. These are two different identifiers serving two different purposes.

### `client.id` Does Not Replace `group.id`

| Property | Purpose | Primary Impact |
|---|---|---|
| `client.id` | Identifies the Kafka client | Metrics, logs, client quotas, and JMX |
| `group.id` | Identifies the consumer group | Membership, partition assignment, and committed offsets |
| `@KafkaListener id` | Identifies the listener endpoint in Spring | Container management via `KafkaListenerEndpointRegistry`; can act as group ID if `idIsGroup` is enabled |
| `clientIdPrefix` | `client.id` prefix applied by Spring Kafka to the listener | Generates client ID names for child consumers |

For example, two consumers with the same `group.id` but different `client.id` values still belong to the same consumer group:

~~~text
group.id = order-service

Consumer A:
  client.id = orders-listener-0

Consumer B:
  client.id = orders-listener-1
~~~

Kafka distributes partitions between the two consumers based on group membership and subscriptions. `client.id` does not decide which consumer receives which partition.

Conversely, two consumers with the same `client.id` but different `group.id` values still belong to two independent consumer groups. However, reusing the same client ID can make metrics hard to distinguish and cause per-client-ID quotas to apply jointly.

Kafka does not require `client.id` to be unique across the entire cluster. Reusing the same value across processes does not merge consumers into the same group. Nevertheless, metrics and quotas keyed by client ID may be aggregated under the same name; within the same JVM, JMX MBean names also need to be distinct.

## 2. Why Does Concurrency Create Multiple Client IDs?

When using `ConcurrentKafkaListenerContainer`, Spring Kafka manages multiple child `KafkaMessageListenerContainer` instances. Each child container owns a separate `KafkaConsumer` and runs on its own consumer thread.

Configuration example:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    return factory;
}
~~~

If a listener subscribes to topic `orders` with concurrency set to three, Spring Kafka creates up to three child consumers:

The diagram below assumes the listener has been configured with client ID prefix `orders-listener`.

~~~mermaid
flowchart TD
    A["@KafkaListener orders"] --> B["ConcurrentMessageListenerContainer"]
    B --> C["Child container 0"]
    B --> D["Child container 1"]
    B --> E["Child container 2"]
    C --> F["KafkaConsumer: orders-listener-0"]
    D --> G["KafkaConsumer: orders-listener-1"]
    E --> H["KafkaConsumer: orders-listener-2"]
    F --> I["Kafka broker"]
    G --> I
    H --> I
~~~

Each child consumer needs a distinct client ID so metrics and JMX can tell them apart. Spring Kafka appends a suffix in the form `-n` to the client ID prefix.

Example:

~~~text
clientIdPrefix = orders-listener
concurrency    = 3

Child consumer 0 -> orders-listener-0
Child consumer 1 -> orders-listener-1
Child consumer 2 -> orders-listener-2
~~~

The suffix is zero-indexed. When concurrency is greater than 1, the suffix ensures child consumers in the same listener container have different names.

Concurrency is the number of child consumers managed by the container. How many consumers actually receive partitions also depends on the subscribed/assigned partition count and the number of consumer members in the group.

## 3. How Spring Kafka Generates Client IDs

Spring Kafka supports setting client IDs via a prefix. For a concurrent container, the prefix has a suffix appended corresponding to the child consumer index.

There are three common places to configure it:

1. `ConsumerConfig.CLIENT_ID_CONFIG` in `ConsumerFactory`.
2. `ContainerProperties.clientId` on the listener container factory.
3. `clientIdPrefix` in `@KafkaListener`.

Among these, settings on the container or annotation can override `client.id` in `ConsumerFactory`.

### Example When Configuring Only `ConsumerFactory`

~~~java
@Bean
public ConsumerFactory<String, OrderEvent> orderConsumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
    );
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
    props.put(
            ConsumerConfig.CLIENT_ID_CONFIG,
            "orders-consumer"
    );

    return new DefaultKafkaConsumerFactory<>(
            props,
            new StringDeserializer(),
            new JsonDeserializer<>(OrderEvent.class)
    );
}
~~~

If the listener container uses concurrency three, the child consumers can receive client IDs:

~~~text
orders-consumer-0
orders-consumer-1
orders-consumer-2
~~~

This sets a shared prefix at the `ConsumerFactory` level. If multiple listeners share this factory, they may share the same prefix. In that case, consider setting a dedicated prefix at the listener level for easier observability.

## 4. Configuring via `ContainerProperties.clientId`

With a custom container factory, you can set the client ID prefix on `ContainerProperties`:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties().setClientId("orders-worker");

    return factory;
}
~~~

When the factory creates a concurrent container, the prefix `orders-worker` is used to generate client IDs for child consumers:

~~~text
orders-worker-0
orders-worker-1
orders-worker-2
~~~

`ContainerProperties.clientId` acts as a prefix and overrides the `client.id` value obtained from `ConsumerFactory`. This approach is useful when a factory serves only one group of listeners with the same operational purpose.

If multiple listeners need distinct names, `clientIdPrefix` on each `@KafkaListener` is usually more flexible.

## 5. Configuring via `clientIdPrefix` on `@KafkaListener`

`@KafkaListener` provides the `clientIdPrefix` attribute to set a dedicated client ID prefix for the listener endpoint.

Example:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service",
        clientIdPrefix = "orders-consumer",
        concurrency = "3"
    )
    public void listen(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

Generated client IDs:

~~~text
orders-consumer-0
orders-consumer-1
orders-consumer-2
~~~

`clientIdPrefix` overrides the client ID prefix in `ConsumerFactory` or `ContainerProperties` used as the base configuration for this endpoint.

This is typically the easiest-to-read approach when an application has multiple listeners:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "order-service",
    clientIdPrefix = "orders-consumer",
    concurrency = "3"
)
public void listenOrder(OrderEvent event) {
    orderService.process(event);
}

@KafkaListener(
    id = "payments-listener",
    topics = "payments",
    groupId = "payment-service",
    clientIdPrefix = "payments-consumer",
    concurrency = "2"
)
public void listenPayment(PaymentEvent event) {
    paymentService.process(event);
}
~~~

Client ID names:

~~~text
orders-consumer-0
orders-consumer-1
orders-consumer-2

payments-consumer-0
payments-consumer-1
~~~

As a result, metrics and logs can distinguish consumers belonging to each listener.

`clientIdPrefix` has been supported since Spring Kafka 2.1.1. For older versions, check the corresponding API and configuration approach.

## 6. Placeholders and SpEL in `clientIdPrefix`

`clientIdPrefix` supports property placeholders and SpEL. This allows changing the prefix per profile or runtime environment.

Configuration:

~~~yaml
app:
  kafka:
    listeners:
      orders:
        client-id-prefix: orders-consumer
        concurrency: 3
~~~

Listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "order-service",
    clientIdPrefix = "${app.kafka.listeners.orders.client-id-prefix}",
    concurrency = "${app.kafka.listeners.orders.concurrency:3}"
)
public void listen(OrderEvent event) {
    orderService.process(event);
}
~~~

Each environment can use its own prefix:

~~~yaml
# application-dev.yml
app:
  kafka:
    listeners:
      orders:
        client-id-prefix: dev-orders
~~~

~~~yaml
# application-prod.yml
app:
  kafka:
    listeners:
      orders:
        client-id-prefix: prod-orders
~~~

In production, client IDs will look like:

~~~text
prod-orders-0
prod-orders-1
prod-orders-2
~~~

You can use SpEL when retrieving the prefix from a configuration bean:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    clientIdPrefix = "#{@kafkaClientSettings.ordersClientIdPrefix}",
    concurrency = "3"
)
public void listen(OrderEvent event) {
    orderService.process(event);
}
~~~

Only use expressions when genuinely needed. For standard configurations, property placeholders keep profile management and deployment simpler.

## 7. `client.id` When Running Multiple Replicas

Concurrency only creates child consumers within one application instance. When deploying multiple replicas, each replica creates a group of child consumers.

Example:

- The application has two replicas.
- Each replica has concurrency set to three.
- Both replicas share the same `group.id` of `order-service`.
- Each replica has its own `clientIdPrefix`.

Result:

~~~text
Replica A:
  clientIdPrefix = orders-pod-a

  orders-pod-a-0
  orders-pod-a-1
  orders-pod-a-2

Replica B:
  clientIdPrefix = orders-pod-b

  orders-pod-b-0
  orders-pod-b-1
  orders-pod-b-2
~~~

In total there are six consumer members in group `order-service`. Kafka distributes partitions among members based on group assignment.

### Setting Per-Instance Prefixes

You can include the instance name in configuration:

~~~yaml
app:
  kafka:
    listeners:
      orders:
        client-id-prefix: orders-${HOSTNAME:local}
~~~

Annotation:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "order-service",
    clientIdPrefix = "${app.kafka.listeners.orders.client-id-prefix}",
    concurrency = "3"
)
public void listen(OrderEvent event) {
    orderService.process(event);
}
~~~

If the environment provides a distinct `HOSTNAME` per instance, client IDs will look like:

~~~text
orders-pod-a-0
orders-pod-a-1
orders-pod-a-2

orders-pod-b-0
orders-pod-b-1
orders-pod-b-2
~~~

In Kubernetes, you can use the Pod name via an environment variable exposed by the Downward API. Do not assume every environment provides the same variable name; verify the deployment configuration.

### When Are Per-Replica Client IDs Needed?

Set per-instance prefixes when:

- You need to distinguish consumers of each pod in dashboards.
- You need to trace which consumer is experiencing latency or errors.
- You need to analyze partition assignments per instance.
- You need to apply separate quotas per client group.
- You need to correlate logs from one replica with Kafka metrics.

If you want brokers to apply a shared quota to the whole service, you can intentionally use a shared prefix and configure quotas with a matching pattern. If you want quotas separated per instance, design client ID names and quotas accordingly.

## 8. `client.id` and Partition Count

`client.id` does not create additional partitions and does not increase the number of consumers that can receive data. It only identifies each Kafka client.

For example, topic `orders` has four partitions:

~~~text
Topic orders:
P0  P1  P2  P3

Application:
  2 replicas x concurrency 3 = 6 consumers

Consumers with client IDs:
  pod-a-0
  pod-a-1
  pod-a-2
  pod-b-0
  pod-b-1
  pod-b-2
~~~

Within the same consumer group, at most four consumers can receive partitions of this topic at a time. The remaining two consumers may not be assigned partitions.

Client ID names are still generated for those consumers, but they do not increase throughput when the topic has only four partitions.

| Partitions | Total consumers | Consumers that can receive partitions |
|---:|---:|---:|
| 4 | 2 | 2 |
| 4 | 4 | 4 |
| 4 | 6 | Up to 4 |
| 12 | 6 | Up to 6 |

Choose concurrency based on partition count and downstream capacity. Good client ID naming helps observe consumers, but does not change Kafka's parallelism limits.

## 9. Client ID Suffix and `alwaysClientIdSuffix`

Spring Kafka appends the `-n` suffix to child consumers in a concurrent container. By default, the `alwaysClientIdSuffix` property is `true`. Therefore, even when concurrency is one, the client ID can still carry the `-0` suffix.

Example:

~~~text
clientIdPrefix = orders-consumer
concurrency = 1

client.id = orders-consumer-0
~~~

Since Spring Kafka 2.2.14, `ConcurrentMessageListenerContainer` provides `setAlwaysClientIdSuffix(false)` to omit the suffix when concurrency is just one.

Example with a directly created and managed container:

~~~java
ConcurrentMessageListenerContainer<String, OrderEvent> container =
        factory.createContainer("orders");

container.setAlwaysClientIdSuffix(false);
container.start();
~~~

Then, if concurrency is one, the client ID can keep the prefix `orders-consumer` without appending `-0`.

This setting only omits the suffix when concurrency is one. When concurrency is greater than one, the suffix is still required to distinguish child consumers.

For listeners auto-created from `@KafkaListener`, do not assume there is a corresponding annotation attribute to disable the suffix. If you genuinely need to change this behavior, manage the container in a way supported by your Spring Kafka version and test before deploying.

Usually, keeping the default suffix keeps consumer names consistent when concurrency changes across environments.

## 10. Observing Metrics by `client.id`

Kafka consumers expose metrics keyed by client ID. When using `ConcurrentMessageListenerContainer`, Spring Kafka aggregates child consumer metrics and groups them by client ID.

Example:

~~~text
orders-consumer-0
  records-consumed-rate
  bytes-consumed-rate
  records-lag-max
  fetch-latency-avg

orders-consumer-1
  records-consumed-rate
  bytes-consumed-rate
  records-lag-max
  fetch-latency-avg

orders-consumer-2
  records-consumed-rate
  bytes-consumed-rate
  records-lag-max
  fetch-latency-avg
~~~

When metrics are tagged with distinct client IDs, you can identify which consumer has lower throughput or higher lag than the others.

Commonly observed metrics:

| Metric | Meaning |
|---|---|
| `records-consumed-rate` | Rate at which the consumer reads records |
| `bytes-consumed-rate` | Rate of data received by the consumer |
| `fetch-latency-avg` | Average fetch latency |
| `fetch-rate` | Fetch request frequency |
| `records-lag-max` | Maximum lag recorded under the corresponding metric |
| `commit-latency-avg` | Average offset commit latency |

Metric names and tagging conventions may vary across Kafka client versions, Micrometer, and monitoring systems. Verify the actual metrics published by your exporter.

### Retrieving Metrics from the Listener Container

You can obtain the container via `KafkaListenerEndpointRegistry`:

~~~java
@Component
public class KafkaConsumerMetricsInspector {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaConsumerMetricsInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void inspectOrdersListener() {
        MessageListenerContainer listenerContainer =
                registry.getListenerContainer("orders-listener");

        if (listenerContainer instanceof
                ConcurrentMessageListenerContainer<?, ?> concurrent) {

            Map<String, Map<MetricName, ? extends Metric>> metrics =
                    concurrent.metrics();

            metrics.forEach((clientId, clientMetrics) -> {
                log.info(
                    "Kafka consumer client.id={}, metricCount={}",
                    clientId,
                    clientMetrics.size()
                );
            });
        }
    }
}
~~~

`metrics()` on a concurrent container returns metrics grouped by client ID. This structure lets the application inspect each child consumer without directly accessing `KafkaConsumer` from a business thread.

Do not invoke non-thread-safe consumer operations from a monitoring thread. Use the metrics API exposed by the container or an integrated exporter.

## 11. Inspecting Partition Assignments by Client ID

In addition to metrics, Spring Kafka provides partition assignment information by client ID in concurrent containers.

Illustrative example:

~~~text
client.id             Assigned partitions
------------------------------------------------
orders-consumer-0    orders-0, orders-1
orders-consumer-1    orders-2
orders-consumer-2    orders-3
~~~

This information is useful when:

- One consumer has unusually high lag.
- Partitions pile onto a single consumer.
- Changing concurrency or replica count.
- Investigating rebalances and assignments.
- Confirming which consumer is handling a partition under inspection.

In Spring Kafka versions that provide the corresponding API, you can use `getAssignmentsByClientId()` or the concurrent container's per-client-ID assignment property.

Do not rely on a fixed assignment layout. Results depend on the partition assignor, active member count, subscriptions, and rebalance timing.

## 12. `client.id` and JMX

Kafka clients can export metrics via JMX. MBean names typically include the client ID to distinguish clients.

When a concurrent container creates multiple consumers, distinct suffixes prevent MBean name collisions among child consumers.

Example:

~~~text
kafka.consumer:type=consumer-fetch-manager-metrics,
client-id=orders-consumer-0

kafka.consumer:type=consumer-fetch-manager-metrics,
client-id=orders-consumer-1

kafka.consumer:type=consumer-fetch-manager-metrics,
client-id=orders-consumer-2
~~~

If consumers in the same JVM shared the same client ID, MBeans could collide or fail to be distinguished as desired. This is one reason Spring Kafka automatically appends suffixes when concurrency is used.

Exact JMX ObjectNames depend on the Kafka client version and metric type. Use JConsole, VisualVM, or a JMX exporter to check actual MBean names.

## 13. `client.id` and Client Quotas

Kafka brokers can enforce quotas by client ID. For example, brokers can throttle data rate or request rate for clients matching a quota configuration.

This means client ID naming can impact operational policies.

Example:

~~~text
Client IDs:
  orders-pod-a-0
  orders-pod-a-1
  orders-pod-b-0
  orders-pod-b-1
~~~

If quotas are configured with pattern `orders-`, the consumers above may fall under the same quota group depending on broker configuration. If quotas are configured per specific client ID, each consumer can receive its own quota level.

Distinguish clearly:

- Client ID is a client identification label.
- Quota is a broker policy enforced by client ID or principal.
- Group ID still governs the consumer group and partition assignment.

Do not change client IDs arbitrarily in systems with quotas. A new prefix may stop matching existing quotas or unintentionally fall under a different quota.

## 14. `client.id`, `id`, and `groupId` in `@KafkaListener`

These three names are easily confused because all appear in the annotation.

~~~java
@KafkaListener(
    id = "orders-listener",
    groupId = "order-service",
    clientIdPrefix = "orders-consumer",
    topics = "orders",
    concurrency = "3"
)
public void listen(OrderEvent event) {
    orderService.process(event);
}
~~~

| Attribute | Example Value | Role |
|---|---|---|
| `id` | `orders-listener` | Endpoint identifier in Spring |
| `groupId` | `order-service` | Kafka consumer group |
| `clientIdPrefix` | `orders-consumer` | Client ID prefix for child consumers |
| `concurrency` | `3` | Number of child consumers managed by the container |

If `idIsGroup` is `true` and `groupId` is not declared, Spring Kafka can use `id` as the group ID. That does not make `id` the client ID.

Declare `groupId` explicitly when you want to control the consumer group independently of the listener endpoint. Use a dedicated `clientIdPrefix` to manage metrics and logs.

## 15. Naming Client IDs by Convention

A good naming convention should convey the service, listener, and instance when needed.

You can use the structure:

~~~text
<service>-<listener>-<instance>-<consumer-index>
~~~

Examples:

~~~text
order-service-orders-pod-a-0
order-service-orders-pod-a-1
order-service-orders-pod-b-0
order-service-orders-pod-b-1
~~~

Since Spring Kafka appends the consumer index suffix automatically, only configure the prefix:

~~~text
order-service-orders-pod-a
~~~

Spring generates:

~~~text
order-service-orders-pod-a-0
order-service-orders-pod-a-1
~~~

Guidelines:

- Use short, stable names that are easy to search in dashboards.
- Include service and listener names in the prefix.
- Include an instance ID when replicas need to be distinguished.
- Let Spring Kafka append the child consumer suffix.
- Avoid manually appending indices in the prefix, as it creates confusing names.
- Avoid placing sensitive information in client IDs.
- Check quota rules if brokers enforce quotas by client ID.
- Keep conventions consistent across dev, staging, and production.

Do not put emails, tokens, passwords, or personal data into `client.id`. This is operational metadata that can appear in logs, metrics, and brokers.

## 16. Complete Configuration Example

`ConsumerFactory` configuration example:

~~~java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    public ConsumerFactory<String, OrderEvent> orderConsumerFactory() {
        Map<String, Object> props = new HashMap<>();

        props.put(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092"
        );
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
        props.put(
                ConsumerConfig.CLIENT_ID_CONFIG,
                "order-service-default"
        );
        return new DefaultKafkaConsumerFactory<>(
                props,
                new StringDeserializer(),
                new JsonDeserializer<>(OrderEvent.class)
        );
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> orderConsumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(orderConsumerFactory);
        factory.setConcurrency(3);

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service",
        clientIdPrefix = "${app.kafka.orders.client-id-prefix:orders-consumer}",
        concurrency = "${app.kafka.orders.concurrency:3}",
        containerFactory = "orderListenerFactory"
    )
    public void listen(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

Configuration:

~~~yaml
app:
  kafka:
    orders:
      client-id-prefix: orders-consumer-${HOSTNAME:local}
      concurrency: 3
~~~

When `HOSTNAME` is `pod-a`, consumer client IDs can be:

~~~text
orders-consumer-pod-a-0
orders-consumer-pod-a-1
orders-consumer-pod-a-2
~~~

In this example:

- `ConsumerFactory` provides the default `client.id`.
- `clientIdPrefix` on the annotation overrides the default prefix for the orders listener.
- `concurrency` creates three child consumers.
- Spring Kafka appends suffixes to distinguish each consumer.
- `groupId` identifies the consumer group.
- `id` identifies the Spring endpoint.

## 17. Verifying Client IDs at Application Startup

When misconfigured, logs may not clearly show which consumers were created, or consumers may unexpectedly share the same prefix.

You can verify through these methods:

- Enable container configuration logging in environments needing diagnosis.
- Inspect Kafka client logs during consumer initialization.
- Read `ConcurrentMessageListenerContainer` metrics by client ID.
- Inspect Kafka consumer JMX MBeans.
- Use Kafka broker logs and client quota metrics.
- Check effective configuration from profiles and environment variables.

Spring Kafka provides an option to log container configuration at `INFO` level via `logContainerConfig` on `ContainerProperties`. Enable it only when diagnosing, as configuration logging can increase log volume and its contents should be reviewed before exposing in high-security environments.

Do not use `client.id` to infer partition assignments. To know which partition belongs to which consumer, read assignments by client ID or use consumer group administration tools.

## 18. Common Pitfalls

**Using `client.id` as `group.id`.** Client ID does not control membership or offsets. Configure `groupId` separately for the consumer group.

**Setting the same `client.id` for every listener.** Metrics and logs become hard to distinguish, and quotas may be applied jointly. Set prefixes per listener.

**Forgetting the suffix when using concurrency.** Spring Kafka automatically appends suffixes to child consumers. Do not manually append indices to the prefix.

**Using `clientIdPrefix` thinking it changes the group.** The prefix only affects the client ID. `groupId` still needs to be configured separately.

**Using the same prefix for multiple replicas expecting cluster-wide unique names.** The suffix only distinguishes child consumers within a container. Include an instance ID if per-replica identification is required.

**Increasing concurrency thinking client IDs add throughput.** Client ID is purely an identification label. Throughput depends on partitions, assigned consumers, and processing capacity.

**Putting sensitive information in client IDs.** Client IDs can appear in logs and metrics. Only use non-sensitive operational names.

**Changing prefixes causing quota changes.** Brokers may enforce quotas by client ID. Check quotas after changing naming conventions.

**Confusing `@KafkaListener id` with `clientIdPrefix`.** `id` identifies the endpoint and can relate to the group ID via `idIsGroup`; `clientIdPrefix` generates consumer client IDs.

**Disabling the suffix in containers with concurrency greater than one.** The suffix is necessary to distinguish child consumers. Only consider disabling it when concurrency is one and there is a clear reason.

## 19. Testing `client.id` with Concurrency

Tests should verify consumer count, client IDs, and assignments in an environment with a Kafka broker.

Useful scenarios:

- Create a listener with concurrency three and verify three distinct consumer client IDs exist.
- Set `clientIdPrefix` in `@KafkaListener` and confirm the prefix overrides `ConsumerFactory client.id`.
- Omit `clientIdPrefix` and confirm the base `client.id` configuration is used.
- Run two listeners with different prefixes and confirm metrics can distinguish them.
- Run two replicas with per-instance prefixes and confirm client IDs do not collide unexpectedly.
- Increase concurrency beyond partition count and confirm excess consumers receive no partitions.
- Run concurrency of one to check the default suffix.
- If managing the container directly, test `setAlwaysClientIdSuffix(false)` with concurrency of one.
- Verify metrics are grouped by client ID.
- Verify JMX MBeans do not collide in the same JVM when JMX is enabled.
- Verify quotas if brokers configure quotas by client ID.
- Restart or scale replicas and confirm new client ID names accurately reflect the instance.

When testing with `EmbeddedKafka` or Testcontainers, wait for consumer assignment to complete before asserting. Do not use short sleeps to conclude a consumer has not been created or has not received partitions.

## 20. `client.id` Configuration Checklist

- [ ] Distinguished `client.id` from `group.id` and `@KafkaListener id`.
- [ ] Identified which listeners need separate client IDs.
- [ ] Chosen prefixes that clearly identify the service and listener.
- [ ] Understood that Spring Kafka automatically appends `-n` when using concurrency.
- [ ] Checked whether `clientIdPrefix` overrides `ConsumerFactory` configuration.
- [ ] Accounted for replica count when per-instance client ID names are required.
- [ ] Avoided manually appending consumer indices to prefixes.
- [ ] Excluded sensitive data from client IDs.
- [ ] Checked client quotas if brokers enforce quotas by client ID.
- [ ] Verified metrics and JMX by client ID.
- [ ] Confirmed client ID is not used in place of group ID.
- [ ] Tested concurrency, assignments, and replica scaling.

## Conclusion

When using concurrency, Spring Kafka creates multiple child Kafka consumers inside a `ConcurrentMessageListenerContainer` and automatically appends a `-n` suffix to client IDs to distinguish each consumer. Prefixes can be configured on `ConsumerFactory`, `ContainerProperties`, or `clientIdPrefix` on `@KafkaListener`; container or annotation settings can override the base client ID. Distinguish `client.id` from `group.id` and listener `id`, include service/listener/instance in names when observing multiple replicas, and use metrics and JMX to monitor individual consumers. `client.id` aids operations and diagnostics; it does not change partition assignments, offsets, or consumer group throughput limits.

## References

- [Spring Kafka – Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka – @KafkaListener Annotation](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
- [Spring Kafka – Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)

