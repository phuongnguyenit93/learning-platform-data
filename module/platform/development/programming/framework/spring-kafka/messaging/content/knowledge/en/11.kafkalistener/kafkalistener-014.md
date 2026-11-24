# Setting clientIdPrefix for Listeners

When a Spring Kafka application has multiple `@KafkaListener` methods, logs and metrics need to show which consumer is issuing requests, reading partitions, or hitting errors. Kafka provides the `client.id` property to identify clients in logs and monitoring metrics. Spring Kafka allows setting this prefix directly on a listener via the `clientIdPrefix` attribute of `@KafkaListener`.

`clientIdPrefix` helps assign intentional names to the Kafka consumers created by a listener container. When a listener runs with concurrency greater than one, Spring Kafka appends a numeric suffix to the prefix so each child consumer gets its own client ID. This attribute serves client identification and observability; it does not determine consumer groups, partition assignments, or offset progress.

## 1. What Is `client.id` Used For?

`client.id` is an optional identifier sent by Kafka clients in requests to brokers. This value is useful for:

- Distinguishing requests and logs from different applications or consumers on the broker side.
- Grouping Kafka client metrics per consumer instance.
- Correlating application logs with metrics when investigating slow consumers, connection errors, or uneven load.
- Identifying which consumer generates read traffic in a system with many listeners.

For example, two services reading Kafka might use client IDs like:

| Service | `client.id` |
|---|---|
| Order projection service | `orders-projection-consumer` |
| Analytics aggregation service | `orders-analytics-consumer` |

Kafka does not use `client.id` as consumer group member identity. Changing a client ID does not create a new group, alter group offsets, or change how partitions are distributed.

## 2. Setting `clientIdPrefix` on `@KafkaListener`

Spring Kafka provides the `clientIdPrefix` attribute on `@KafkaListener`. This prefix serves as the base for generating `client.id` for Kafka consumers managed by the listener container.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderProjectionListener {

    @KafkaListener(
            id = "orders-projection-listener",
            topics = "orders.events",
            groupId = "order-projection",
            clientIdPrefix = "orders-projection"
    )
    public void consume(String payload) {
        process(payload);
    }

    private void process(String payload) {
        // Process order event.
    }
}
```

For a listener with concurrency one, the created consumer uses the prefix as its client ID, e.g., `orders-projection`. The listener's `id` attribute identifies the endpoint in Spring Kafka; `clientIdPrefix` is the prefix for the Kafka client ID. The two values can look similar yet serve different purposes.

If `clientIdPrefix` is omitted, consumers may use the `client.id` configured on `ConsumerFactory` or the Kafka consumer config. When each listener needs clear identification, setting the prefix right on the annotation makes configuration easier to read and correlate.

## 3. Suffixes When the Listener Uses Concurrency

A listener can create multiple concurrent consumers via the `concurrency` attribute. When concurrency is greater than one, Spring Kafka appends a `-n` suffix to the prefix, where `n` starts at `0`.

```java
@KafkaListener(
        id = "orders-projection-listener",
        topics = "orders.events",
        groupId = "order-projection",
        clientIdPrefix = "orders-projection",
        concurrency = "3"
)
public void consume(String payload) {
    process(payload);
}
```

With concurrency three, the child consumers receive client IDs:

```text
orders-projection-0
orders-projection-1
orders-projection-2
```

Each child consumer may be assigned one or more partitions depending on partition count and the partition assignor. The suffix only distinguishes clients; it does not mean consumer `-0` always reads partition 0 or consumer `-1` always reads partition 1.

For instance, a six-partition topic with concurrency three may assign two partitions per consumer. If a topic has only two partitions while concurrency is three, one consumer may receive no partitions. Setting `clientIdPrefix` neither increases partition count nor adds parallel read capacity beyond assignment limits.

## 4. Using Placeholders for Environment-Specific Prefixes

Client names should reflect the service and listener role. When running multiple instances, you can append a pod name or instance identifier so logs and metrics distinguish processes.

`@KafkaListener` supports property placeholders in configuration attributes. Example:

```java
@KafkaListener(
        id = "orders-projection-listener",
        topics = "orders.events",
        groupId = "order-projection",
        clientIdPrefix = "${spring.application.name:orders}-projection-${HOSTNAME:local}",
        concurrency = "${app.kafka.orders.concurrency:3}"
)
public void consume(String payload) {
    process(payload);
}
```

For applications running on Kubernetes, `HOSTNAME` typically reflects the pod name. You can also use a dedicated environment variable like `POD_NAME` if configured in the deployment. The resolved prefix is used by Spring Kafka to generate client IDs; concurrency three still appends `-0`, `-1`, `-2`.

Choose a stable, searchable naming convention free of sensitive data. Example:

```text
orders-service-projection-pod-a-0
orders-service-projection-pod-a-1
orders-service-projection-pod-b-0
orders-service-projection-pod-b-1
```

Kafka does not require every `client.id` to be cluster-wide unique the way static member IDs must be unique. However, if multiple instances share the same client ID, metrics or logs tagged by client ID become hard to distinguish. Adding an instance name improves observability across multi-replica deployments.

## 5. Distinguishing Client ID from Other Identifiers

Kafka identifier properties have similar names yet different meanings:

| Property | Role | Affects partition assignment? |
|---|---|---|
| `client.id` / `clientIdPrefix` | Identifies the Kafka client in requests, logs, and metrics | No |
| `group.id` | Identifies the consumer group and offset-storage namespace | Yes, via group membership and assignment |
| `group.instance.id` | Stable identifier for static members in a group | Yes, affects membership and static membership mechanics |
| `member.id` | Consumer member identifier managed by the group coordinator | Yes, tied to current membership |
| `@KafkaListener(id = ...)` | Identifies the listener endpoint in the Spring Kafka registry | Not directly |

For example, two consumers can share `group.id=order-projection` while having distinct client IDs:

```text
group.id = order-projection

Consumer A: client.id = orders-projection-pod-a-0
Consumer B: client.id = orders-projection-pod-b-0
```

Both consumers belong to the same group, so Kafka distributes partitions between them. Different client IDs merely distinguish each consumer in logs and metrics.

Do not use `clientIdPrefix` in place of `group.instance.id`. If static membership is needed to reduce rebalances on restarts, configure `group.instance.id` properly and ensure every static member in the group has a unique ID. Setting a unique client ID does not enable static membership.

## 6. Configuring a Default Client ID in Spring Boot

If you want to set a base client ID for consumers created from shared config, Spring Boot supports `spring.kafka.consumer.client-id`:

```yaml
spring:
  application:
    name: orders-service
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
      client-id: orders-service-consumer
      enable-auto-commit: false
```

This value translates to the `client.id` setting for consumers. For listeners needing distinct names, `clientIdPrefix` on `@KafkaListener` assigns a dedicated prefix to consumers created by that container. When both are configured, the listener's prefix is used for that listener's consumers; consumers without a listener prefix can still fall back to the default `ConsumerFactory` setting.

Example application with two listeners:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders.events",
        groupId = "order-projection",
        clientIdPrefix = "orders-projection"
)
public void consumeOrder(String payload) {
    processOrder(payload);
}

@KafkaListener(
        id = "payments-listener",
        topics = "payments.events",
        groupId = "payment-projection",
        clientIdPrefix = "payments-projection"
)
public void consumePayment(String payload) {
    processPayment(payload);
}
```

When inspecting logs or metrics, the two reading streams have distinct prefixes and are easy to tell apart. The listeners still keep independent group IDs and assignments according to their configuration.

## 7. Observing Client IDs in Operations

`client.id` is most valuable when used consistently across application logs, broker logs, and metrics systems. When investigating a slow consumer, correlate the client ID with group ID, topic, partition, and incident timestamps.

A structured log line might include:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderConsumerLogging {

    private static final Logger log =
            LoggerFactory.getLogger(OrderConsumerLogging.class);

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection",
            clientIdPrefix = "orders-projection"
    )
    public void consume(ConsumerRecord<String, String> record) {
        log.info(
                "Kafka consumer activity: groupId={}, topic={}, partition={}, offset={}",
                "order-projection",
                record.topic(),
                record.partition(),
                record.offset()
        );
    }
}
```

In this example, application logs supply the group ID and record coordinates; Kafka client metrics and broker logs supply the actual client ID. With concurrency, the actual client ID carries a child consumer suffix; if you need to log the exact runtime client ID, obtain it from Kafka consumer metrics or container/consumer configuration rather than assuming the prefix itself is the final ID.

Kafka client metrics commonly include a `client-id` tag, helping break down request rate, fetch rate, bytes consumed, latency, and other consumer metrics per client. Exact metric names depend on the Kafka client version and metrics instrumentation in use. Spring Boot Actuator/Micrometer can export these metrics when enabled and instrumented appropriately.

To make client IDs effective for observability:

- Use a prefix describing the service and listener role, e.g., `orders-projection`.
- Append an instance name when distinguishing multiple replicas.
- Keep the naming convention stable across deployments for metric comparison.
- Never embed user IDs, access tokens, or sensitive data in client IDs.
- Combine client ID with group ID and partition when diagnosing lag or rebalances.

## 8. Common Misconceptions

1. **Assuming `clientIdPrefix` creates a new consumer group.** Groups are determined by `group.id`; client ID only identifies the Kafka client.
2. **Assuming `-0`, `-1` suffixes are partition numbers.** They are child consumer indices created by concurrency, not partition IDs.
3. **Using a shared prefix and expecting metrics to distinguish pods automatically.** If multiple instances share the same prefix and concurrency, client IDs collide; add an instance identifier when distinction is needed.
4. **Using client ID instead of `group.instance.id`.** These two properties serve different goals; a unique client ID does not enable static membership.
5. **Thinking raising concurrency only requires changing the prefix.** Concurrency controls child consumer count; prefix only names them. Parallelism still depends on partition count and assignments.
6. **Changing client ID to fix offset or rebalance errors.** Client ID does not alter group membership, offset commits, or poll intervals. Inspect the actual property causing the issue.

Setting `clientIdPrefix` gives each `@KafkaListener` stream a clear identity in logs and metrics. Combine role-descriptive prefixes, Spring Kafka's concurrency suffixes, and appropriate instance identifiers while keeping `client.id`, `group.id`, and `group.instance.id` cleanly separated so consumer configuration stays clear and accurate in operations.
