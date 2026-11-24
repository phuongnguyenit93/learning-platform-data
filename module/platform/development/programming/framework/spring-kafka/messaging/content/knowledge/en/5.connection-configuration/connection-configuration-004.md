# Basic consumer configuration in Spring Kafka

A consumer is the component that reads records from Kafka and passes them to the application's processing logic. In Spring Kafka, consumer configuration is typically declared via `spring.kafka.consumer` in `application.yml` or `application.properties`; `@KafkaListener` uses that configuration to create a listener container and manage the Kafka consumer lifecycle.

A basic configuration needs to specify brokers, consumer group, deserializers, the starting policy when no valid offset exists, and how offsets are committed after processing. Poll and concurrency parameters help tune consumption capacity as load increases.

## 1. Initialization and record reception flow

When a Spring Boot application starts, Spring Kafka creates a `ConsumerFactory` from the consumer configuration. A listener container is created for each `@KafkaListener` method; the container uses a consumer from the factory to join the group, receive assigned partitions, and invoke the listener method when records arrive.

```mermaid
flowchart TD
    A[application.yml] --> B[Spring Boot Kafka properties]
    B --> C[ConsumerFactory]
    C --> D[Listener container]
    D --> E[Kafka consumer]
    E --> F[Join consumer group]
    F --> G[Receive partitions and poll records]
    G --> H[Deserializer creates Java key/value]
    H --> I[Record converter and listener adapter]
    I --> J[@KafkaListener]
    J --> K[Business processing]
    K --> L[Commit offset per AckMode]
```

The Kafka client handles communication with brokers, polling records, and managing read positions. Spring Kafka manages the listener container, dispatches records to application methods, and coordinates acknowledgments/commits according to configuration. Distinguishing these two layers helps identify the right place for a configuration property.

## 2. Minimal configuration in application.yml

The following example uses strings as keys and values to focus on basic consumer properties:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    listener:
      ack-mode: record
      concurrency: 3

app:
  kafka:
    topics:
      orders: orders
```

Key properties:

| Property | Meaning |
|---|---|
| `bootstrap-servers` | Address of one or more brokers for the client to locate the Kafka cluster and fetch metadata |
| `consumer.group-id` | Consumer group identifier; consumers in the same group share partitions and maintain a shared reading progress per partition |
| `key-deserializer` | Converts key bytes into a Java type |
| `value-deserializer` | Converts value bytes into a Java type |
| `auto-offset-reset` | Policy when the group has no valid offset or the offset is no longer available |
| `enable-auto-commit` | Enables/disables the Kafka client's automatic commit mechanism |
| `listener.ack-mode` | How the listener container determines when to commit offsets |
| `listener.concurrency` | Number of child consumer containers for the listener within one application instance |

`bootstrap-servers` should be externalized via environment variables so the same build can run in local, staging, and production environments with different Kafka clusters. A broker in the list is only a starting point; the client fetches metadata to connect to the required brokers.

## 3. Consumer groups and group-id

`group.id` defines the logical identity of a group of consumers. Consumers with the same group ID and the same subscription participate in partition assignment. Each partition is assigned to at most one consumer within the same group in a steady state; different groups can read the same topic with independent offsets.

For example, an `orders` topic can be read by separate groups:

```text
Topic: orders
  ├── orders-service       -> updates read model
  ├── billing-service      -> creates billing data
  └── analytics-service    -> aggregates metrics
```

A group name should reflect an application or a logical processing stream. If two instances of the same service need to share load, they typically share the same group ID. If two applications need to receive all events independently, they need different group IDs.

You can set the group ID in shared configuration:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
```

Or specify it on the listener:

```java
@KafkaListener(
        topics = "${app.kafka.topics.orders}",
        groupId = "orders-audit"
)
public void audit(String value) {
    // Process independently in the orders-audit group.
}
```

`groupId` on `@KafkaListener` sets the group for that listener and can override the globally configured group ID. If not specified separately, the listener uses the group ID from the consumer factory. Avoid accidentally setting a different group ID per instance when the goal is horizontal scaling; doing so causes each instance to behave as an independent group and read the entire stream.

## 4. Deserializers: converting bytes into application data types

Kafka stores records as bytes. The consumer needs deserializers matching how the producer serialized the data.

| Data | Producer-side Serializer | Consumer-side Deserializer |
|---|---|---|
| String | `StringSerializer` | `StringDeserializer` |
| Byte array | `ByteArraySerializer` | `ByteArrayDeserializer` |
| 32-bit integer | `IntegerSerializer` | `IntegerDeserializer` |
| 64-bit integer | `LongSerializer` | `LongDeserializer` |
| JSON object via Spring Kafka | `JsonSerializer` | `JsonDeserializer` |

The listener's generic/parameter type must match the type returned by the deserializer. If the consumer uses `StringDeserializer`, the listener should accept `String` or `ConsumerRecord<K, String>`. If the consumer uses `JsonDeserializer<OrderCreated>`, the listener can accept `OrderCreated` or `ConsumerRecord<K, OrderCreated>`.

### Configuring JSON deserializer

For structured events, you can use Spring Kafka's JSON deserializer:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.OrderCreated
        spring.json.trusted.packages: com.example.orders
```

`spring.json.value.default.type` specifies the default type for the value when the deserializer needs a target type and cannot obtain a suitable type from type headers. For systems with multiple event types, use type mapping or a clear multi-type deserialization strategy. Do not force all events into a single class if the topic contains different schemas.

`spring.json.trusted.packages` restricts the packages that the JSON deserializer is allowed to use when interpreting type metadata. Only trust packages belonging to your application or sources controlled by your system. Do not open it up to `*` arbitrarily.

If the producer does not use Spring Kafka's `JsonSerializer` or does not send type headers, configure a default type or converter according to the agreed schema. Consumers and producers must agree on byte format, schema, and event version; simply calling both payloads JSON is not enough to guarantee compatibility.

## 5. auto-offset-reset and starting read position

Kafka stores committed offsets per group and partition. When a group has no valid offset yet, or the committed offset is no longer within the readable data range, `auto.offset.reset` determines how the consumer starts.

Commonly used options:

| Value | Behavior |
|---|---|
| `earliest` | Start from the earliest offset still retained in the partition |
| `latest` | Start from new data at the end of the partition |
| `none` | Throw an error if no valid offset is found |

Example:

```yaml
spring:
  kafka:
    consumer:
      auto-offset-reset: earliest
```

Important point: `auto-offset-reset` is **not** a rewind command for a group that already has a valid offset. If the group has already committed offsets, the consumer resumes from that offset. Changing `latest` to `earliest` does not automatically make the group re-read the entire topic.

To re-read data, you can use a new group ID, or explicitly reset offsets using Kafka administrative tools when the consumer group is in an appropriate state. Resetting offsets is an operational action that impacts processing progress; clearly identify the target partitions and offsets before executing it.

Choose the policy by purpose:

- `earliest` fits new consumers that need to rebuild state from still-retained history.
- `latest` fits consumers that only care about events produced after they start running.
- `none` fits cases where a missing offset is a configuration or operational error that must be caught explicitly.

## 6. Committing offsets and acknowledgment modes

Committing an offset records the next position the group needs to read. If processing the record at offset `25` succeeds, committing `26` means the next read starts from `26`.

With Spring Kafka, let the listener container manage commits and set `enable-auto-commit: false` to prevent the Kafka client from auto-committing on a timer while business logic may not yet have finished.

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
```

Common acknowledgment modes:

| AckMode | Commit timing managed by container |
|---|---|
| `RECORD` | After each record is processed successfully by the listener |
| `BATCH` | After all records from a single poll are processed successfully |
| `MANUAL` | Application calls `Acknowledgment.acknowledge()`; container handles commit via manual mechanism |
| `MANUAL_IMMEDIATE` | Requests immediate commit when the application calls acknowledge, depending on thread context and configuration |

`RECORD` is straightforward for listeners processing one event at a time. `BATCH` can reduce commit frequency when processing in batches. Manual modes are useful when the application needs to decide the acknowledgment timing, but require a clear understanding of processing order and container commit behavior.

Example of a listener processing a single record:

```java
@Component
public class OrderListener {

    @KafkaListener(topics = "orders")
    public void onOrder(OrderCreated event) {
        // Business processing. If the method exits normally,
        // the container can commit according to the configured AckMode.
    }
}
```

If the listener throws an exception, the outcome of retries, recovery, and commits depends on the error handler and container configuration. Do not assume failed records will always be retried infinitely or automatically moved to a dead-letter topic; those behaviors must be configured explicitly.

### Why is idempotent processing needed?

If the application finishes processing but stops before committing, the record may be delivered again. Therefore, consumers should generally tolerate receiving the same event multiple times. You can use a unique `eventId`, a database unique constraint, or an inbox table to prevent duplicate business effects.

Committing before finishing processing can cause the group to skip records after a failure; committing after processing typically prioritizes avoiding missed processing at the cost of allowing duplicates. Kafka commits and database transactions do not automatically form a single atomic transaction without dedicated coordination design.

## 7. Poll configuration and processing limits

The Kafka consumer calls `poll()` to retrieve records. Several important properties control how much data is fetched per call and how long a consumer is allowed to go without polling.

| Kafka client property | Meaning | When to adjust |
|---|---|---|
| `max.poll.records` | Maximum number of records returned in a single poll | When batches are too large or too small relative to processing capacity |
| `max.poll.interval.ms` | Maximum interval between poll calls before the consumer is considered no longer making progress | When batch processing takes a long time and processing duration needs reassessment |
| `session.timeout.ms` | Time the broker waits for heartbeats before considering the consumer disconnected | When tuning dead-consumer detection and network conditions |
| `heartbeat.interval.ms` | Interval at which the consumer sends heartbeats | When tuning together with session timeout per client requirements |
| `fetch.min.bytes` | Minimum amount of data the broker tries to accumulate for a fetch | When optimizing throughput and read latency |
| `fetch.max.wait.ms` | Maximum time the broker waits to satisfy the minimum fetch size | When balancing latency against data batching |

You can set Kafka client properties that lack dedicated Spring Boot properties under `spring.kafka.consumer.properties`:

```yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.records: 100
        max.poll.interval.ms: 300000
        session.timeout.ms: 15000
        heartbeat.interval.ms: 5000
```

The values above are only examples to illustrate declaration syntax, not a universal optimal configuration. If a batch takes longer than `max.poll.interval.ms`, the consumer may leave the group and trigger a rebalance. You can lower `max.poll.records`, optimize processing, or increase the poll interval in line with SLAs and actual processing times.

`session.timeout.ms` and `max.poll.interval.ms` address two different situations. Session timeout detects lost heartbeats; max poll interval detects a consumer not calling poll frequently enough. Do not mechanically increase both because doing so can prolong failure detection time.

## 8. Concurrency and partition count

Spring Kafka allows configuring the number of child consumers for a listener container:

```yaml
spring:
  kafka:
    listener:
      concurrency: 3
```

If an application instance runs a listener with concurrency equal to three, the container can create three consumers in the group. With a six-partition topic, the three consumers can split the partitions. If the topic only has two partitions, at most two consumers receive partitions in steady state; the remaining consumer has no partitions to read for that topic.

When running multiple instances, the total number of consumers created is the sum of concurrency across instances for that listener. Useful parallelism for a group is capped by the number of partitions the group subscribes to. Adding consumers beyond this limit does not increase throughput.

Higher concurrency also consumes more connections, threads, and processing resources. Choose concurrency based on partition count, processing speed, application resources, and measured lag. If a listener subscribes to multiple topics, count the total partitions across the subscription rather than looking at a single topic in isolation.

## 9. Listeners receiving payload and metadata

After deserializers convert bytes into Java types, `@KafkaListener` can receive the payload directly:

```java
@Component
public class OrderListener {

    @KafkaListener(topics = "${app.kafka.topics.orders}")
    public void onOrder(OrderCreated event) {
        // Process the deserialized event.
    }
}
```

If you need topic, partition, offset, or key, accept `ConsumerRecord`:

```java
@KafkaListener(topics = "${app.kafka.topics.orders}")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    OrderCreated event = record.value();
    String orderId = record.key();
    String topic = record.topic();
    int partition = record.partition();
    long offset = record.offset();

    // Log record coordinates when tracing is needed.
}
```

Or receive the payload along with the needed headers:

```java
@KafkaListener(topics = "${app.kafka.topics.orders}")
public void onOrder(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    // Process event with metadata.
}
```

Choose parameter types according to the data the listener actually needs. If only the payload is needed, a POJO parameter keeps the method clean and less coupled to Kafka. If metadata is needed for tracing, use `ConsumerRecord` or `@Header`.

## 10. Separating configuration by environment

Do not hardcode broker addresses or credentials in source code. Use environment variables and Spring profiles to vary connections across environments.

Example `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP:orders-service}
```

The production environment can supply `KAFKA_BOOTSTRAP_SERVERS` and `KAFKA_CONSUMER_GROUP` via the deployment system. Never commit passwords, tokens, private keys, or JAAS configs containing secrets to Git.

If the Kafka cluster requires SASL or TLS, declare the corresponding client properties in Spring Kafka configuration or the deployment platform's secret store. For example, `security.protocol`, `sasl.mechanism`, `sasl.jaas.config`, and `ssl.*` belong to Kafka client configuration; secret values must be injected at runtime. Only enable `security.protocol: SASL_SSL` when brokers and accounts have been configured accordingly.

Separate profiles can be used:

```yaml
# application-local.yml
spring:
  kafka:
    bootstrap-servers: localhost:9092

---
# application-prod.yml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
```

Activate a profile via `SPRING_PROFILES_ACTIVE=prod` or equivalent runtime configuration. Ensure the production profile includes complete broker, group ID, deserializer, and security information.

## 11. Isolation configuration when producers use transactions

If producers send records inside a Kafka transaction and consumers must only see committed records, set the isolation level to `read_committed`:

```yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
```

`read_committed` ensures the consumer only reads records belonging to committed transactions and stops at the last stable offset while transactions are still open. `read_uncommitted` allows reading records from uncommitted or aborted transactions as well; this is the Kafka client's default behavior. This isolation level applies only to Kafka transactions and does not make external database writes automatically exactly-once.

If the application does not use Kafka transactions or has no requirement to read committed-only records, do not add this configuration merely expecting consumer stability.

## 12. Verifying the consumer at runtime

After the application starts, verify:

- The consumer connects to the right bootstrap servers and joins the right group ID.
- Topics exist, subscriptions are correct, and partitions have been assigned.
- Key/value deserializers produce the exact types the listener expects.
- Starting offsets match the chosen policy.
- Listeners process successfully and commit according to the acknowledgment mode.
- Lag does not grow continuously beyond expectations.
- Repeated rebalances do not occur due to slow processing or lost heartbeats.

Kafka CLI can describe the consumer group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service
```

The output helps inspect partitions, consumer IDs, committed offsets, log end offsets, and lag. If the group does not appear, verify whether the application initialized the listener, whether the group ID is right, and whether the consumer subscribed to the topic.

When checking a topic:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Application logs should include topic, partition, offset, and event ID when handling errors. Avoid logging full payloads or sensitive information. Useful metrics include consumer lag, rebalance count, processing rate, listener error count, and processing time per record/batch.

## 13. Common configuration errors

**Wrong bootstrap servers:** the application cannot connect to brokers or fetch metadata. Check DNS, ports, network policies, and advertised listener addresses published by brokers.

**Missing group ID:** the consumer lacks a valid group identifier while the listener needs group-based offset management. Explicitly set `spring.kafka.consumer.group-id` or `groupId` on the listener.

**Different group IDs across instances:** each instance can become a separate group and receive all data. If the goal is load sharing, instances must share the same group ID.

**Deserializer mismatch with serializer:** deserialization errors or `ClassCastException` occur before or during listener parameter resolution. Check producer configuration, consumer configuration, and payload schemas.

**Misunderstanding auto-offset-reset:** changing to `earliest` while the group still continues from committed offsets. Use a new group or a controlled offset-reset procedure if re-reading is required.

**Committing too early:** the application may skip records if a failure occurs after commit but before business logic completes. Let the container manage post-processing commits and design idempotent handlers.

**Concurrency greater than partition count:** some consumers are not assigned any partitions and add no useful parallelism.

**Batch processing takes too long:** the consumer may exceed `max.poll.interval.ms`, leave the group, and trigger a rebalance. Adjust batch size, processing time, and poll interval based on actual measurements.

**Security configuration mismatch with brokers:** authentication or TLS errors often occur even when bootstrap servers are reachable. Check protocol, mechanism, certificates, credentials, and topic/group permissions.

## 14. Pre-production consumer checklist

- Bootstrap servers are injected per environment and reachable from the application.
- Group ID is set intentionally and shared across instances that need to divide load.
- Key/value deserializers are compatible with the format sent by producers.
- `auto-offset-reset` reflects requirements when the group has no valid offset yet.
- `enable-auto-commit` and `AckMode` are chosen according to how the listener processes data.
- Listeners are idempotent to tolerate redelivered records.
- Concurrency matches partition count and application resources.
- Poll settings fit actual record/batch processing times.
- Security settings and secrets are managed via the deployment environment.
- Metrics/logs exist to monitor lag, rebalances, deserialization errors, and listener failures.

A well-configured consumer must know which cluster to read from, which group it belongs to, how to convert bytes to data types, and when to commit progress. Once those four decisions are clear, concurrency, polling, security, and observability parameters can be added based on actual operational load.
