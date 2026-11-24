# client.id and client identification

In Kafka, an application can create multiple Kafka clients: producers to send records, consumers to read records, and admin clients to administer the cluster. Each client can carry an identifier string called **`client.id`**. The broker uses this value to record which client sends a request; the Kafka client also uses it as a label in many metrics. This allows operators to distinguish which producer, consumer, or instance a request and its metrics originate from.

`client.id` is an identification metadata field for observability and traffic management. It is not a consumer group name, does not identify records, does not authenticate an application, and does not determine which partition a record is sent to. Understanding this boundary helps enforce consistent naming and diagnose the system when multiple instances connect to Kafka simultaneously.

## 1. What is `client.id`?

`client.id` is a string configuration on a Kafka client. An application can set this value when creating a producer, consumer, or admin client. If left unconfigured, the Kafka client can auto-generate a default ID. Auto-generated values are useful for letting the client operate, but they are often hard to read when correlating logs and metrics in a multi-service environment.

For example, an order-processing service might use:

| Component | Suggested `client.id` | Purpose |
|---|---|---|
| Producer sending order events | `order-api-producer` | Identify outbound traffic |
| Consumer updating invoices | `billing-consumer` | Identify reading client |
| Listener updating projection | `orders-projection` | Distinguish a listener stream |
| Admin client managing topics | `messaging-admin` | Identify administrative operations |

A good `client.id` indicates which application or role the client belongs to. When it is necessary to distinguish individual running replicas, you can append an instance name, pod name, or a suffix provided by the deployment platform.

## 2. Distinguishing `client.id` from other Kafka IDs

Kafka has many types of IDs because they solve different problems. You should not use a single value as a substitute for all of them:

| ID | Scope and Meaning | Example |
|---|---|---|
| `client.id` | Identifier label for a Kafka client used for observability, logging, and certain quotas | `billing-consumer-pod-2` |
| `group.id` | Consumer group name; consumers in the same group coordinate to share partitions | `billing-v1` |
| `member.id` | Consumer group member ID managed by the group coordinator during group membership | Assigned by Kafka when consumer joins |
| `group.instance.id` | Stable ID of a member when using static membership | `billing-pod-2` |
| `transactional.id` | Identifier for a producer using Kafka transactions and legacy producer fencing | `billing-tx-pod-2` |
| Producer ID | Internal ID assigned by Kafka to a producer, related to idempotence and sequence | Managed by Kafka |
| Security principal | Identity authenticated via SASL or TLS client authentication | `User:billing-service` |

Two consumers can use the same `group.id=billing-v1` to share partitions, yet each consumer should have its own `client.id` if per-instance observability is needed. Conversely, two consumers using two different group IDs will have independent reading progress, even if they use the same `client.id`.

`group.instance.id` is also not `client.id`: static membership uses a stable ID to identify members within a group. This value must be unique within the group; if two active consumers use the same value, they can fence or replace each other. `client.id` has no such member coordination role.

Similarly, `transactional.id` serves transactions and producer fencing. Do not use `client.id` in place of `transactional.id`, and do not share one transactional ID across independent producers running concurrently.

## 3. Where does Kafka use `client.id`?

### Request identification and broker logs

The Kafka protocol includes the client ID in request metadata. Brokers can record the client ID in logs or diagnostic output, helping trace requests back to the corresponding client group. When a broker has many connections, a name like `order-api-prod-consumer` is much easier to read than an auto-generated ID.

### Client and broker metrics

Kafka clients expose many metrics tagged with the client ID, such as metrics for requests, send/receive rates, bytes, errors, and latency. Specific metrics depend on the client type and Kafka version. Brokers also have request metrics and observability data that can be categorized by client ID.

Not every metric in the cluster carries the `client.id` label. Exposing Kafka metrics to a monitoring system also depends on JMX, Micrometer, or the exporter in use. When configuring dashboards, check the actual tags instead of assuming every metric shares the same label set.

### Client quotas

Kafka supports applying certain quotas by client ID, by authenticated user, or by a combination of these criteria. For example, a broker can throttle the producer byte rate of clients carrying the ID `bulk-importer` so that a data import stream does not exhaust resources.

Quotas by `client.id` are a traffic management mechanism, not an authentication mechanism. A client can declare any client ID string itself; if you need limits based on a trusted identity, combine them with authentication and quotas by the appropriate principal.

### Monitoring consumer group members

The `kafka-consumer-groups.sh --describe` command typically displays the `CLIENT-ID` column alongside consumer ID, host, and partition assignment. This allows operators to see which consumer instance holds which partitions of the group.

## 4. Configuration in Spring Boot

Spring Boot binds Kafka properties from `application.yml` into `KafkaProperties`, then uses them to create the producer factory and consumer factory. Separate client IDs can be set for producers and consumers:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092
    producer:
      client-id: order-api-prod-producer
    consumer:
      client-id: order-api-prod-consumer
      group-id: billing-v1
      auto-offset-reset: earliest
      enable-auto-commit: false
```

In this configuration:

- The producer is identified as `order-api-prod-producer`.
- The consumer uses `order-api-prod-consumer` as the default client ID from the consumer factory.
- `group.id=billing-v1` identifies the processing group and shared reading progress.
- `auto-offset-reset` and `enable-auto-commit` control the starting position and how offsets are confirmed; they are not determined by the client ID.

Exact property names should be cross-checked against the Spring Boot version in use. When creating a Kafka client or factory manually, set the native Kafka configuration using the key `ProducerConfig.CLIENT_ID_CONFIG` or `ConsumerConfig.CLIENT_ID_CONFIG`.

Example of configuring a producer and consumer using the Java Kafka client:

```java
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.producer.ProducerConfig;

Map<String, Object> producerProperties = new HashMap<>();
producerProperties.put(
        ProducerConfig.CLIENT_ID_CONFIG,
        "order-api-prod-producer"
);

Map<String, Object> consumerProperties = new HashMap<>();
consumerProperties.put(
        ConsumerConfig.CLIENT_ID_CONFIG,
        "order-api-prod-consumer"
);
```

When using Spring Boot auto-configuration, prefer configuring via `spring.kafka.producer.client-id` and `spring.kafka.consumer.client-id`. You only need to set them directly in the map when the application builds clients manually or requires a factory with a custom configuration.

## 5. Setting a dedicated client ID per `@KafkaListener`

An application may have multiple listeners sharing one `ConsumerFactory`, yet each stream needs to be identified separately. Spring Kafka allows setting `clientIdPrefix` on `@KafkaListener`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class BillingListener {

    private final BillingService billingService;

    BillingListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "billing-v1",
            clientIdPrefix = "billing-orders"
    )
    public void onOrder(OrderCreated event) {
        billingService.process(event);
    }
}
```

The prefix above helps identify the consumer of the listener processing the `orders` topic. If the listener container runs with concurrency greater than 1, Spring Kafka appends a suffix to each consumer instance so that client IDs do not collide within the container. For example, with concurrency equal to 3, the IDs look like:

| Consumer instance | Client ID |
|---|---|
| Consumer 1 | `billing-orders-0` |
| Consumer 2 | `billing-orders-1` |
| Consumer 3 | `billing-orders-2` |

When using `clientIdPrefix`, the listener's prefix is used for the consumers belonging to that listener and can override the default client ID value from the consumer factory. This is the appropriate way to distinguish multiple listeners within the same application. If separate identification is not needed, you can let the container use the factory's default configuration.

Concurrency only creates additional consumer instances within the same container. The number of partitions that a group processes in parallel is still limited by the number of partitions assigned to the group; increasing concurrency does not create more partitions.

## 6. Naming conventions in multi-instance environments

A useful convention is:

```text
<application>-<environment>-<role>-<instance>
```

Example:

| Component | Client ID |
|---|---|
| Order API producer in production | `order-api-prod-producer` |
| Billing consumer on pod 2 | `billing-prod-consumer-pod-2` |
| Projection listener on pod 2 | `projection-prod-orders-pod-2` |
| Data import consumer | `data-import-prod-consumer` |

When choosing a convention, keep in mind:

- Use clear application and role names; avoid generic names like `client-1` or `consumer`.
- If you need to trace individual replicas, add the pod name or instance ID. If you only need to distinguish roles, you can use a single stable name for the entire deployment.
- Keep the length and number of variants reasonable so dashboards, logs, and quotas remain manageable.
- Do not include user IDs, emails, access tokens, or sensitive data in the client ID.
- Do not include order IDs or request IDs in the client ID. Values that change per message create very high cardinality and make metrics hard to use.
- Keep names consistent across environments; only vary the environment or instance part as needed.

If running multiple replicas, decide clearly whether individual replicas need to be distinguished. A shared ID for a role helps aggregate metrics; a unique ID per pod helps pinpoint a faulty instance. Both levels can be combined: prefix by application and role, suffix by pod or consumer concurrency.

## 7. Observing client ID in operations

### Viewing clients participating in a consumer group

Run the following command to view the status of a consumer group:

```bash
kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 --group billing-v1 --describe
```

The output can contain the following columns:

| Column | Meaning |
|---|---|
| `CONSUMER-ID` | Member identifier managed by Kafka |
| `HOST` | Host address of the consumer |
| `CLIENT-ID` | Client ID declared by the consumer |
| `#PARTITIONS` | Number of partitions currently assigned |
| `ASSIGNMENT` | Partitions assigned to the consumer |

If the group has no active consumers, the command may not display member rows. In that case, check the group state, startup logs, and the application's connection configuration.

### Combining application and broker logs

On the application side, log the service name, client role, group ID, topic, partition, and offset at startup or error-handling points. Example:

```java
log.info(
        "Kafka record received: topic={}, partition={}, offset={}",
        record.topic(),
        record.partition(),
        record.offset()
);
```

`ConsumerRecord` provides the topic, partition, offset, and record metadata; it is not where you obtain `client.id`. Log the configured client ID during initialization or add it from the application configuration to the logging context if correlation is needed. Do not infer the client ID from the record's offset or key.

On the broker side, filtering logs by client ID helps isolate connections, request timeouts, authentication errors, or abnormal requests. When reading logs, cross-check the host, principal, timestamp, and group ID to avoid confusing two clients with the same name.

### Using metrics for the right purpose

Client metrics help compare send/receive throughput, request latency, errors, and network usage across client IDs. For consumers, combine client metrics with consumer lag per partition to distinguish a slow-reading client from a group that has not yet been assigned partitions.

You should not rely on client ID alone to conclude the root cause. A consumer can have the right client ID and still fail to read due to ACLs, group authorization, deserializers, rebalances, or broker unavailability.

## 8. client ID is not a security mechanism

`client.id` is self-declared by the client and can be changed via application configuration. Therefore, do not use it as proof of authentication or authorization. Kafka authenticates clients using mechanisms such as SASL or TLS client certificates; the broker determines the principal after authentication. ACLs decide which resources a principal is allowed to read, write, or administer.

For example, two applications can declare the same `client.id=reporting-client` yet authenticate with two different principals. The broker still differentiates permissions based on the principal, not the client ID string. Conversely, one principal can create multiple client IDs to separate the producer and consumer of the same service.

If using quotas by client ID, remember that clients with the same name can be subject to the same quota. When you need to isolate traffic by application or authenticated identity, choose a quota entity and authentication policy appropriate for your operating model.

## 9. Common errors and misconceptions

| Symptom or Assumption | Cause or Reality | How to Handle |
|---|---|---|
| Multiple consumers in a group have the same client ID | Default configuration is shared or no distinct prefix was set | Set clear client IDs; use `clientIdPrefix` for listeners and concurrency |
| Changed client ID but consumer still reads from the same position | Reading progress is stored by group ID, topic, and partition | Check `group.id` and committed offsets; client ID does not reset offsets |
| Created a new client ID but records are still sent to old partitions | Partitioning is based on key, partitioner, and partition count | Check keys and partitioner; client ID does not route records |
| Used client ID as the consumer group name | Confused client identification with subscription progress | Set `group.id` per processing flow and share it among collaborating consumers |
| Used client ID as a security identity | Client ID is client-declared metadata | Use SASL/TLS principals and ACLs |
| Dashboard has too many time series | Client ID changes per request or message | Only use labels with controlled cardinality; never embed business IDs into client ID |
| Cannot find client ID in expected metric | That metric does not carry a client ID tag or is not exported properly | Check JMX/Micrometer/exporter and actual tags |
| Quota applies to more instances than expected | Multiple clients share the same client ID and match the same quota entity | Review naming conventions and quota scope |

## 10. Client ID design checklist

1. Set separate client IDs for producers and consumers if traffic needs to be distinguished by role.
2. Set a dedicated `clientIdPrefix` for critical listeners or listeners with concurrency.
3. Use `group.id` to describe the shared processing stream; do not use client ID as a substitute.
4. Only use `group.instance.id` when intentionally designing static membership and ensuring uniqueness within the group.
5. Only use `transactional.id` for transactional producers following lifecycle and fencing rules.
6. Do not treat client ID as a security identity; configure SASL/TLS and ACLs separately.
7. Verify client IDs in broker logs, consumer group describe output, and metric systems after deployment.
8. Keep metric cardinality controlled and avoid embedding sensitive data or per-message IDs.

`client.id` helps Kafka and operators identify request sources at the client level. When clear client names are combined with group IDs, principals, and appropriate metrics, development teams can trace traffic and incidents more accurately without confusing client identification, reading progress, and security.
