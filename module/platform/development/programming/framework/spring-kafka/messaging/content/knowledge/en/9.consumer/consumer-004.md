# Subscribing to Topics by Regular Expression

In Kafka, a consumer can subscribe to read a specific topic or a set of topics whose names match a regular expression. Spring Kafka supports this subscription approach through the `topicPattern` attribute on `@KafkaListener`. This approach fits when a service needs to read multiple topics sharing a naming convention, or needs to automatically discover newly created topics after the application has already started.

For example, a consumer can subscribe to the pattern `^orders\..+$` to receive topics such as `orders.created`, `orders.updated`, and `orders.cancelled`. When a new topic `orders.refunded` is created and metadata is refreshed, the consumer subscribed by pattern can detect the new topic, participate in a rebalance, and receive the corresponding partitions.

The pattern only determines which topics the consumer subscribes to. It does not route records on the producer side, filter records by payload, or automatically create topics. Producers still send to a specific topic name; Kafka brokers store records into partitions; the consumer group receives partitions of the topics matching the pattern through the normal distribution mechanism.

This lesson belongs to the **Consumer** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building applications that send and receive events with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups; while also learning serialization, retries, dead-lettering, transactions, exactly-once, concurrency, and testing to operate reliable messaging flows.

## 1. What is subscribing to topics with a regular expression?

There are three common ways for a consumer to specify topic sources:

- Subscribe to one or more topics by explicit name.
- Subscribe with a regular expression to match multiple topic names.
- Directly assign specific partitions using topic-partition assignment.

With Spring Kafka, `@KafkaListener` provides the corresponding attributes:

| Attribute | Purpose |
| --- | --- |
| `topics` | Subscribes to one or more explicitly named topics. |
| `topicPattern` | Subscribes to topics whose names match a regular expression. |
| `topicPartitions` | Specifies the exact topics and partitions the listener receives. |

On a single listener endpoint, choose the subscription method that fits the requirement. Do not combine `topics`, `topicPattern`, and `topicPartitions` as if they were additive filters for one another.

Example subscribing by fixed names:

~~~java
@KafkaListener(
    topics = {"orders.created", "orders.updated"},
    groupId = "order-projection"
)
public void onOrderEvent(OrderEvent event) {
    orderProjection.apply(event);
}
~~~

Example subscribing by pattern:

~~~java
@KafkaListener(
    topicPattern = "^orders\\..+$",
    groupId = "order-projection"
)
public void onOrderEvent(OrderEvent event) {
    orderProjection.apply(event);
}
~~~

In the second example, the listener subscribes to every topic whose name matches the pattern. When the list of topics changes, the Kafka consumer can update its subscription upon metadata refresh and trigger a rebalance.

## 2. Commonly used regular expression syntax

`topicPattern` takes a regular expression string following Java `Pattern` syntax. The pattern is used to match topic names, so it should be written to match only the namespace that the service truly owns.

Some useful regex components:

| Token | Meaning | Example |
| --- | --- | --- |
| `^` | Start of string | `^orders` |
| `$` | End of string | `v1$` |
| `.` | Any single character | `a.b` |
| `\.` | Literal dot | `orders\.created` |
| `.*` | Zero or more characters | `orders\..*` |
| `.+` | One or more characters | `orders\..+` |
| `[0-9]+` | One or more digits | `v[0-9]+` |
| `(a|b)` | One of the branches | `(created|updated)` |

Use `^` and `$` to clearly bound the full topic name to match. Avoid overly broad patterns like `.*` unless the service genuinely needs to subscribe to every topic in the cluster.

### 2.1. Escaping dots in Java strings

In regex, a dot `.` is a wildcard character. If a topic name contains a real dot, it must be escaped as `\.` in the regex.

When writing regex inside a Java string literal, the backslash must be escaped one more time. Therefore, the annotation uses:

~~~java
@KafkaListener(
    topicPattern = "^orders\\..+$",
    groupId = "order-projection"
)
~~~

The Java string value `"^orders\\..+$"` becomes the regex `^orders\..+$`. Writing only `"^orders..+$"` means the dot is no longer a literal separator; the pattern may match unintended topic names.

When the regex is placed in YAML inside a single-quoted string, the backslash is preserved as-is:

~~~yaml
app:
  kafka:
    order-topic-pattern: '^orders\..+$'
~~~

It can then be referenced with a property placeholder:

~~~java
@KafkaListener(
    topicPattern = "${app.kafka.order-topic-pattern}",
    groupId = "order-projection"
)
public void onOrderEvent(OrderEvent event) {
    orderProjection.apply(event);
}
~~~

Distinguish between escaping in Java strings and in configuration files. When reading a pattern, determine whether it lives in Java source, YAML, or another configuration layer to avoid over- or under-escaping.

## 3. How Spring Kafka registers a pattern-based listener

When Spring creates a listener container from a method with `@KafkaListener(topicPattern = ...)`, the container uses Kafka consumer subscription by `Pattern`. The Kafka client fetches topic metadata from the cluster and matches topic names against the pattern to determine the subscription.

Execution flow:

~~~mermaid
flowchart TD
    A[Spring initializes @KafkaListener] --> B[Listener container]
    B --> C[Consumer subscribe Pattern]
    C --> D[Kafka fetches topic metadata]
    D --> E[Match topic names against regex]
    E --> F[Consumer group receives assignment]
    F --> G[Poll records from partitions]
    G --> H[Listener processes records]
    D --> I[Metadata refresh]
    I --> E
~~~

The pattern is applied on the Kafka consumer/client side when determining the topic subscription. The broker does not receive a regex to route records automatically; the broker still stores and serves records by concrete topic/partition.

Because subscription relies on metadata, the topic must exist in the cluster to be discovered. When a new topic matching the pattern appears, the consumer can detect it after the next metadata refresh. Do not assume a new topic is added to the subscription instantaneously at creation time.

## 4. Example of @KafkaListener with topicPattern

Suppose the system has several order topics:

- `orders.created`
- `orders.updated`
- `orders.cancelled`
- `orders.refunded`

These topics share the same `OrderEvent` event type and are handled by a projection service. A pattern can be used:

~~~java
@Component
@RequiredArgsConstructor
public class OrderEventListener {

    private final OrderProjection orderProjection;

    @KafkaListener(
        topicPattern = "^orders\\..+$",
        groupId = "order-projection"
    )
    public void onOrderEvent(OrderEvent event) {
        orderProjection.apply(event);
    }
}
~~~

The listener subscribes to topics matching the `orders.` namespace. If a new topic like `orders.refunded` appears, the consumer can detect it and include it in the subscription after metadata refreshes.

Using one pattern for multiple topics is only appropriate when the topics have contracts compatible with the listener. If each topic contains a completely different schema, a single method accepting the same payload type may fail to decode the data or handle business logic incorrectly.

### 4.1. Observing the source topic in the listener

When a listener receives data from multiple topics, it should know which topic each record came from. You can accept `ConsumerRecord`:

~~~java
@KafkaListener(
    topicPattern = "^orders\\..+$",
    groupId = "order-audit"
)
public void audit(ConsumerRecord<String, OrderEvent> record) {
    log.info(
        "Received event topic={} partition={} offset={} key={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key()
    );

    orderAuditService.record(record.topic(), record.value());
}
~~~

Or inject the header identifying the topic:

~~~java
@KafkaListener(
    topicPattern = "^orders\\..+$",
    groupId = "order-audit"
)
public void audit(
        OrderEvent event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic) {

    orderAuditService.record(topic, event);
}
~~~

Topic, partition, and offset information help trace events. When a listener consumes multiple topics, include the topic name in logs, metrics, or trace context to analyze incidents by source.

## 5. How are new topics matching the pattern discovered?

One benefit of pattern subscription is that the consumer does not need to redeclare its topic list every time a new topic in the same namespace is created.

For example:

1. The application is subscribed to the pattern `^orders\..+$`.
2. The cluster currently has `orders.created` and `orders.updated`.
3. A provisioning process creates the topic `orders.refunded`.
4. The Kafka consumer refreshes metadata and discovers the new topic name matching the pattern.
5. The consumer group's subscription changes; Kafka performs a rebalance to distribute partitions.
6. The consumer reads records from the newly assigned partitions according to the group's offsets.

New topic discovery depends on metadata refresh and consumer group state. Actual timing also depends on Kafka client configuration, broker behavior, and connectivity; do not write business logic that relies on a fixed wait time.

Pattern subscription is not a topic creation mechanism. New topics must be created by `KafkaAdmin`/`NewTopic`, `AdminClient`, infrastructure pipelines, or the broker's own auto-create mechanism if permitted. Auto-create configuration is a separate policy; do not rely on it to guarantee topics always have the designed partition count and replication.

## 6. Rebalance when the set of matching topics changes

A consumer group needs to distribute partitions of the topics its members subscribe to. When a new topic is discovered or a topic is deleted, the subscription's partition set can change and the group performs a rebalance.

During a rebalance:

- Partitions may be revoked from the current consumer.
- Partitions are redistributed among active consumers in the group.
- Consumers may pause record processing during the handover phase.
- Committed offsets per topic-partition remain the group's progress checkpoints.
- Unprocessed or uncommitted records may be re-read depending on stop timing and commit policy.

Rebalancing is a normal part of consumer groups. However, if topics are continuously created/deleted or the pattern is too broad causing frequent subscription changes, the system may experience more rebalances and degraded throughput.

When designing, use a stable namespace and controlled topic provisioning processes. If the system creates topics in bulk, consider the impact on metadata refreshes and the number of new partitions added to the group.

## 7. Consumer groups and offsets when subscribing to multiple topics

Pattern subscription does not alter consumer group principles. Each group keeps its own offset progress per topic-partition.

Suppose a pattern matches two topics:

~~~text
Group: order-projection

orders.created
  Partition 0 -> committed offset 120
  Partition 1 -> committed offset 85

orders.updated
  Partition 0 -> committed offset 64
  Partition 1 -> committed offset 92
~~~

These offsets belong to different topic-partitions. Offset 120 of `orders.created-0` has no ordering relationship with offset 64 of `orders.updated-0`.

If two consumer groups subscribe to the same pattern, each group can receive all records from the matching topics at its own pace:

- `order-projection` reads to update projections.
- `order-audit` reads to write audit records.

The two groups do not share committed offsets. Within each group, consumers split partitions; across the two groups, both can read the same data.

### 7.1. auto-offset-reset with new topics

When a new topic is discovered, the group usually has no committed offset for the new partitions yet. In that case, `auto.offset.reset` decides the starting position when no valid offset exists:

- `earliest`: starts from the earliest record still retained.
- `latest`: starts from the end at the time the initial offset is determined.

If the group already has a valid offset for a topic-partition, the consumer resumes from the committed offset; `auto-offset-reset` does not automatically reset every topic on each application startup.

With pattern subscription, this is especially important because new topics can appear while the service is running. Choose `earliest` or `latest` according to business requirements: whether data written before the topic was discovered must be read, or only new events from the start point are needed.

## 8. Choosing safe patterns and avoiding overly broad subscriptions

The broader the pattern, the larger the set of subscribed topics. For example, `.*` can match nearly every topic name visible to the consumer. This easily leads to reading wrong topics that do not belong to the service.

Common risks:

- Consumers unintentionally receive retry or dead-letter topics.
- The listener attempts to deserialize payloads with different schemas.
- The group is assigned many additional partitions, increasing load and lag.
- ACL permissions are insufficient for some topics matching the pattern.
- New topics created by other services accidentally slip into the subscription.

Design topic naming conventions with dedicated namespaces:

| Namespace | Purpose |
| --- | --- |
| `orders.*` | Order events |
| `payments.*` | Payment events |
| `inventory.*` | Inventory events |
| `orders.retry.*` | Retry topics for the order flow |
| `orders.dlt` | Dead-letter topic for orders |

For example, if a listener only needs primary business events, use a more specific pattern:

~~~java
@KafkaListener(
    topicPattern = "^orders\\.(created|updated|cancelled)$",
    groupId = "order-projection"
)
public void onOrderEvent(OrderEvent event) {
    orderProjection.apply(event);
}
~~~

This pattern does not match topics such as `orders.retry.1` or `orders.dlt`. If a service needs to read retry/DLT topics as well, subscribe to them intentionally and design appropriate listeners and error handling.

Do not use a catch-all pattern merely to avoid updating a topic list. The pattern should reflect the data boundary the service is permitted and responsible for handling.

## 9. Regex subscription and Kafka ACLs

A regex in `topicPattern` is a topic-name matching expression on the consumer side. It does not grant permission to read the matched topics.

In a cluster with ACLs enabled, the consumer's principal needs appropriate permissions to describe/read the topics and join the consumer group. If the pattern matches a topic for which the principal lacks permissions, the consumer may encounter authorization errors when accessing that topic.

Distinguish between the two mechanisms:

- `topicPattern` is a Java regular expression used to determine topic subscription.
- Kafka ACLs have resource pattern types such as literal or prefixed; prefixed ACLs rely on resource name prefixes, not Java regex.

For instance, a prefixed ACL for the `orders.` namespace can be appropriate when granting access to a group of topics sharing a prefix. However, ACL configuration must be performed by Kafka administrators and constrained by the principle of least privilege.

Do not treat a regex matching only a prefix as sufficient to protect data. Actual permissions are enforced by the broker based on principal and ACL; verify permissions for every topic the consumer will read.

## 10. Do multiple topics need the same schema or multiple schemas?

A listener receiving multiple topics via a pattern is simplest when all topics share a common event contract.

For example, `orders.created`, `orders.updated`, and `orders.cancelled` all contain a common envelope type:

~~~java
public record OrderEvent(
    String eventId,
    String orderId,
    String eventType,
    Instant occurredAt,
    JsonNode payload
) {}
~~~

The consumer can decode all topics into `OrderEvent` and then dispatch logic based on `eventType` or `topic`.

If topics have completely different payloads, explicit type mapping or deserialization design is needed. A `JsonDeserializer` defaulting to one class cannot automatically understand every schema simply because the topic name matches a regex.

Common options:

1. Use a common envelope with a consistent payload structure.
2. Use type headers or a schema registry to determine the event type per contract.
3. Receive `ConsumerRecord` or `byte[]` and dispatch according to registered topic and schema.
4. Split into multiple `@KafkaListener` methods with narrower patterns and matching `ConsumerFactory`/deserializers.

Do not merge all topics into a single listener if doing so blurs schema boundaries or results in unruly branching logic.

## 11. Configuring the pattern via application.yml

To vary the pattern by environment without modifying Java source, place the expression in `application.yml`:

~~~yaml
app:
  kafka:
    consumer:
      order-topic-pattern: '^orders\.(created|updated|cancelled)$'
      group-id: order-projection
~~~

The listener references the properties:

~~~java
@Component
@RequiredArgsConstructor
public class OrderEventListener {

    private final OrderProjection orderProjection;

    @KafkaListener(
        topicPattern = "${app.kafka.consumer.order-topic-pattern}",
        groupId = "${app.kafka.consumer.group-id}"
    )
    public void onOrderEvent(
            OrderEvent event,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic) {

        orderProjection.apply(topic, event);
    }
}
~~~

This separates subscription configuration from processing logic. Profiles or environment variables can be used to supply different patterns for local, test, and production.

Patterns are typically resolved when the listener endpoint/container is configured. Editing the configuration file after the container has started does not automatically update the running subscription. If you need to change the pattern at runtime, you need a listener container lifecycle mechanism to stop, reconfigure, and restart it in a controlled manner.

## 12. Testing topicPattern

Testing should verify both matching topics and non-matching topics. It can be divided into:

- Unit testing the regex with Java `Pattern` to verify naming rules.
- Integration testing with a broker to verify the listener receives records from matching topics.
- Verifying non-matching topics are not processed by the listener.
- Verifying newly created topics after the listener starts can be discovered.
- Verifying rebalances and offsets when subscriptions change.
- Verifying authorization across topics in the namespace.

Example unit test for the regex:

~~~java
@Test
void orderPatternShouldMatchOnlySupportedTopics() {
    Pattern pattern = Pattern.compile(
        "^orders\\.(created|updated|cancelled)$"
    );

    assertThat(pattern.matcher("orders.created").matches()).isTrue();
    assertThat(pattern.matcher("orders.updated").matches()).isTrue();
    assertThat(pattern.matcher("orders.cancelled").matches()).isTrue();

    assertThat(pattern.matcher("orders.dlt").matches()).isFalse();
    assertThat(pattern.matcher("payments.created").matches()).isFalse();
}
~~~

The unit test above only checks regex syntax and rules. It does not test Kafka consumer subscription or record consumption.

Integration tests can use Embedded Kafka or Testcontainers. Create two topics, one matching the pattern and one not matching; send records to both; verify the listener only receives records from the matching topic. When testing new topic discovery, create the topic after the listener is already running and wait using a condition/timeout rather than a fixed sleep.

For topic discovery, tests need enough time for the consumer to refresh metadata and the group to complete rebalancing. This timing depends on configuration and the test environment; do not treat a short fixed timeout as a Kafka guarantee.

## 13. Monitoring pattern-subscribed consumers in operations

When a listener subscribes to multiple topics, tracking status by group ID alone may not be enough. Also observe topics and partitions:

- List of topics currently matched by the subscription.
- Partition assignment per consumer.
- Consumer lag per topic-partition.
- Rebalance count and rebalance duration.
- Record rate and processing latency by topic.
- Deserialization, authorization, and listener errors by topic.
- Count of newly discovered topics and subscription changes.

In listener logs, record topic, partition, offset, and event ID. When multiple topics share a listener, these fields identify the data source and prevent confusing offsets across different topics.

A broad pattern can cause a consumer group to unexpectedly receive additional partitions when another team creates a new topic. Therefore, namespaces and topic creation processes are part of the operational contract between services.

## 14. Common errors and misconceptions

| Symptom or misconception | Cause / accurate understanding |
| --- | --- |
| Listener does not receive expected topic | Wrong regex, topic does not exist yet, metadata not refreshed, or group has no assigned partitions. |
| Listener receives unwanted topics | Pattern is too broad or lacks anchors/exclusion branches. |
| Using `topics` and `topicPattern` together | These are different subscription modes; choose one mode appropriate for the listener. |
| New topic is not received immediately | Consumer must discover it via metadata refresh and the group may have to rebalance. |
| Regex automatically creates topics | Regex only determines subscription; topic creation belongs to `KafkaAdmin`/broker provisioning. |
| Regex filters records by value | Regex matches topic names, not keys, payloads, or headers. |
| Every consumer in the group receives every record | Within the same group, consumers share partitions; each independent group has its own progress. |
| Offsets of different topics can be compared directly | Offsets are only meaningful within each topic-partition. |
| Regex grants topic read permission | ACLs are enforced by the broker; regex subscription grants no permissions. |
| One listener receiving multiple schemas automatically deserializes correctly | Requires contracts, type mapping, or deserializers supporting the payload types. |
| Pattern unintentionally matches DLT/retry topics | A broad namespace may include auxiliary topics; constrain the pattern. |

## 15. topicPattern design checklist

Before using regex subscription, verify:

1. Do the topics share a naming convention and belong to the same business boundary?
2. Does the pattern have anchors and properly escaped literal dots?
3. Could the pattern accidentally match retry, DLT, or internal topics?
4. Do all matched topics have schemas compatible with the listener?
5. Does the consumer group have the right group ID and offset policy?
6. Does the consumer principal have appropriate ACLs on all topics to be read?
7. Is the process for creating new topics managed and controlled?
8. Can the system tolerate rebalances when the topic set changes?
9. Are there metrics/logs per topic-partition to observe lag and errors?
10. Have integration tests verified matching topics, non-matching topics, and discovery of new topics?

Subscribing by regular expression lets a consumer manage a set of topics with a shared naming convention without updating a fixed topic list whenever a new topic is created. To use it safely, the pattern must tightly bound the right namespace, the topics must have contracts the listener can process, and the system must account for metadata refreshes, rebalances, offsets, and ACLs. Regex is a tool for selecting topic sources; consumer groups and partitions still govern how records are distributed and processed.

