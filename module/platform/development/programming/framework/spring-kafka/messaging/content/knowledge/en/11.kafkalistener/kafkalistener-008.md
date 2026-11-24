# Declaring topicPattern

When a listener needs to consume data from a group of topics named by convention, listing each topic in `topics` can become hard to maintain. For instance, a system may create `orders.created`, `orders.updated`, `orders.cancelled` per event type, or per-tenant topics such as `tenant-101.orders`, `tenant-102.orders`. Spring Kafka supports the `topicPattern` attribute on `@KafkaListener` to subscribe consumers using a regular expression.

With `topicPattern`, the Kafka consumer registers a pattern and automatically discovers existing or newly created topics whose names match the pattern when metadata refreshes. This approach suits systems with dynamic topics or many topics following a naming convention. Choose a pattern narrow enough that the listener only receives the exact data group it is responsible for handling.

## 1. What Is `topicPattern`?

`topicPattern` is an attribute on `@KafkaListener` that accepts a string representing a Java regular expression. Spring Kafka passes this pattern to the Kafka consumer to register a pattern subscription.

Example:

```java
@KafkaListener(
        topicPattern = "orders\\..*",
        groupId = "order-projection")
public void consume(String payload) {
    // Process events from topics whose names start with orders.
}
```

The pattern `orders\\..*` in a Java string literal represents the regex `orders\..*`:

- `orders` is the fixed prefix.
- `\.` matches an actual dot in the topic name; an unescaped `.` in regex matches any character.
- `.*` matches the remainder of the name, including an empty string.

Thus, the pattern can match `orders.created`, `orders.updated`, and `orders.audit.v2`. It could also match `orders.` if such a topic exists. A pattern does not create topics automatically; it only subscribes to matching topics discovered by Kafka.

Kafka applies the regex against the entire topic name. Therefore, the pattern `orders` matches only a topic literally named `orders`; to match topics prefixed with `orders.`, append a suffix such as `orders\..*`.

## 2. Differences Between `topics`, `topicPattern`, and `topicPartitions`

`@KafkaListener` provides three common ways to specify data sources:

| Attribute | Subscription style | When appropriate |
| --- | --- | --- |
| `topics` | Fixed list of topic names | The application knows the exact topics to read |
| `topicPattern` | Regex matching topic names | Topics are created dynamically or follow a naming convention |
| `topicPartitions` | Specifies exact topics and partitions | Manual assignment to a specific set of partitions is needed |

Example using `topics`:

```java
@KafkaListener(
        topics = {"orders.created", "orders.updated"},
        groupId = "order-projection")
public void consume(String payload) {
    // Receive data from the two declared topics.
}
```

Example using `topicPattern`:

```java
@KafkaListener(
        topicPattern = "orders\\.(created|updated)",
        groupId = "order-projection")
public void consume(String payload) {
    // Receive data from orders.created or orders.updated.
}
```

Example using `topicPartitions`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.TopicPartition;

@KafkaListener(
        topicPartitions = @TopicPartition(
                topic = "orders.events",
                partitions = {"0", "2"}),
        groupId = "order-projection")
public void consume(String payload) {
    // Receive only partitions 0 and 2 of orders.events.
}
```

These three attributes are distinct ways of registering subscriptions; do not declare `topics`, `topicPattern`, and `topicPartitions` together on the same listener. Choose the one matching your routing and partition assignment needs.

## 3. Common Regex Syntax

Useful regex building blocks for topic names:

| Regex | Meaning | Example matching topics |
| --- | --- | --- |
| `orders\..*` | Starts with `orders.` followed by anything | `orders.created`, `orders.v2.audit` |
| `orders\.(created|updated)` | Only one of the two suffixes | `orders.created`, `orders.updated` |
| `tenant-[0-9]+\.orders` | `tenant-`, one or more digits, then `.orders` | `tenant-101.orders` |
| `(orders|payments)\..*` | Starts with `orders.` or `payments.` | `orders.created`, `payments.completed` |
| `events\.v[0-9]+\..*` | Topics with numeric versions | `events.v1.orders`, `events.v2.users` |

Inside a Java annotation, regex backslashes must be escaped an extra time inside the string literal. For example, regex `orders\..*` is written as `"orders\\..*"` in Java source.

If placing the pattern in YAML, you can use a single-quoted scalar to keep backslashes intact:

```yaml
app:
  kafka:
    topic-pattern: 'orders\.(created|updated|cancelled)'
```

Do not use `.*` indiscriminately. An overly broad pattern can cause the listener to subscribe to unrelated topics, increasing partition counts, consumer lag, network traffic, and the risk of processing unintended data.

## 4. Declaring `topicPattern` in @KafkaListener

Example listener consuming all order event topics with matching suffixes:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @KafkaListener(
            id = "order-event-listener",
            topicPattern = "orders\\.(created|updated|cancelled)",
            groupId = "order-projection")
    public void onMessage(ConsumerRecord<String, String> record) {
        String topic = record.topic();
        String orderId = record.key();
        String payload = record.value();

        // Process event based on topic and payload.
    }
}
```

Here the listener subscribes to a pattern covering three topic kinds. Using `ConsumerRecord` identifies exactly which topic the record came from, allowing distinct handling for `created`, `updated`, and `cancelled`.

If all matching topics share the same schema and processing rules, the listener can accept a shared DTO. If each topic has a different schema, design an explicit deserialization and dispatch strategy; relying solely on topic names does not solve data-type differences.

## 5. Externalizing the Pattern to Configuration

You do not need to hard-code regex patterns inside annotations. Spring Kafka supports property placeholders in `topicPattern`:

```yaml
app:
  kafka:
    topic-pattern: 'orders\.(created|updated|cancelled)'

spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
```

```java
@Component
public class OrderEventListener {

    @KafkaListener(
            id = "order-event-listener",
            topicPattern = "${app.kafka.topic-pattern}",
            groupId = "${spring.kafka.consumer.group-id}")
    public void onMessage(ConsumerRecord<String, String> record) {
        // Process record.
    }
}
```

Note: in a YAML single-quoted string, only one `\` is needed for a regex escape. For instance, `orders\.` in YAML binds to the property as `orders\.` (one backslash before the dot). In a direct Java annotation string literal, two backslashes are required in source: `orders\\.`.

Externalizing the pattern lets you use different regexes per local, test, or production profile without modifying code. Verify the resolved property after Spring Boot binding and check startup logs if a pattern is invalid.

## 6. How Are Dynamic Topics Discovered?

When a consumer subscribes by pattern, the Kafka client uses cluster metadata to find topics matching the regex. When a new topic is created and metadata refreshes, the consumer can automatically subscribe to that topic's partitions.

Example:

```text
Pattern: orders\..*

Initially:
  orders.created
  orders.updated

Created later:
  orders.cancelled

Consumer pattern subscription:
  orders.created      -> subscribed
  orders.updated      -> subscribed
  orders.cancelled    -> discovered after metadata refresh
```

Discovery of new topics does not necessarily happen at the exact moment a topic is created. The Kafka client refreshes metadata according to the client version's mechanism and settings; `metadata.max.age.ms` relates to the periodic metadata refresh interval. Earlier refreshes can also occur due to client activity or metadata changes. Therefore, do not design business flows that depend on the listener receiving a new topic instantaneously right after topic creation.

When a new matching topic is discovered, the consumer group may rebalance to distribute the new partitions among consumers. During a rebalance, processing may pause briefly. Applications should process records idempotently and monitor rebalance logs/metrics if topics are created frequently.

When a topic is deleted, metadata must also refresh for the consumer to reflect updated subscriptions and assignments. Deleting topics while consumers are active requires careful coordination, especially if unprocessed records remain.

## 7. Consumer Groups When Using topicPattern

`topicPattern` defines which set of topics the consumer subscribes to; `groupId` defines which consumer group coordinates reading partitions from that set.

If three consumers use the same pattern `orders\..*` and the same `groupId=order-projection`, Kafka distributes the partitions of all matching topics across the three consumers. Within a group, each partition is assigned to only one consumer at a time.

If another consumer group, such as `order-analytics`, also subscribes with the same pattern, that group tracks its own offsets and can read the same records independently of `order-projection`.

This means:

- Same pattern and same group ID: consumers share load across matching partitions.
- Same pattern but different group IDs: each group receives its own stream copy and commits offsets independently.
- Adding a matching topic: new partitions join the group subscription and may trigger a rebalance.

Do not share a single group ID across two applications if both applications must receive every event. Sharing a group causes them to split load instead of each receiving an independent copy.

## 8. Choosing Patterns Along Business Boundaries

A good pattern reflects the exact group of topics belonging to one consumer's logic. Examples:

| Topic group | Suggested pattern | Purpose |
| --- | --- | --- |
| Order events | `orders\.(created|updated|cancelled)` | One projection handling the order lifecycle |
| Payment events | `payments\.(authorized|captured|refunded)` | One consumer aggregating payment status |
| Per-tenant topics | `tenant-[0-9]+\.orders` | Consuming order topics for numeric-ID tenants |
| Event version 2 | `events\.v2\..*` | Separating consumers for the v2 data contract |

Do not group topics together merely because they share a prefix if their schemas, access permissions, or processing logic differ. A listener consuming multiple topics still needs to distinguish data sources and validate payloads appropriately before applying business logic.

For per-tenant topics, consider total topic and partition counts. Thousands of topics with many partitions can increase metadata size, assignment count, and consumer group operational overhead. If data can be partitioned by key within a few shared topics, that model may be simpler than creating a separate topic per tenant.

## 9. Access Permissions and Data Protection

Pattern subscription only selects topic names. It does not grant permission to read topics. In clusters with authorization enabled, the application's principal must hold appropriate permissions to discover topics and read subscribed topics/partitions. Exact permissions depend on the cluster's security setup and ACL model.

An overly broad pattern can cause a consumer to attempt subscribing to topics the principal is not allowed to read. In that case, the listener may hit authorization exceptions or read only a subset of desired topics. Combine naming conventions, regexes, and ACLs to scope access accurately.

Avoid generic patterns like `.*` in production unless explicitly required. Broad patterns increase the risk of consuming out-of-scope data, including internal topics or topics owned by other teams. Do not log sensitive payloads or headers simply because a listener is shared across multiple topics.

## 10. Testing topicPattern

Integration tests should verify that the listener receives records from multiple matching topics and ignores topics outside the pattern.

Example test configuration with Embedded Kafka:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest(properties = {
        "app.kafka.topic-pattern=orders\\..*",
        "spring.kafka.consumer.auto-offset-reset=earliest"
})
@EmbeddedKafka(
        partitions = 1,
        topics = {"orders.created", "orders.updated", "payments.created"},
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class TopicPatternListenerTest {
    // Inject KafkaTemplate and test listener to send/verify records.
}
```

With pattern `orders\..*`, the listener should receive records from `orders.created` and `orders.updated`; `payments.created` does not match. In a full test, use a `BlockingQueue<ConsumerRecord<?, ?>>` or a spy bean to capture records received by the listener, then assert topic names and payloads.

If a test depends on assignment, wait until the listener container is assigned partitions before sending records, e.g., using `ContainerTestUtils.waitForAssignment(...)` with `KafkaListenerEndpointRegistry`. This avoids race conditions where the producer sends before the listener is ready.

To test dynamic discovery, create a new topic after the listener is already running, wait for metadata refresh and rebalance to complete, and then send a record to the new topic. This test needs a reasonable timeout because topic discovery is not necessarily immediate. Do not use a short fixed sleep and conclude that pattern subscription does not work.

## 11. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Listener misses expected topics | Wrong regex or unescaped dot | Verify pattern with Java regex and actual topic names |
| Pattern matches only one topic name | Literal regex used instead of wildcard | Use `.*`, groups `(a|b)`, or suitable character classes |
| Pattern in Java fails to match | Incorrect `\` escaping | Remember Java string literals require double escaping |
| New topic not consumed immediately | Client has not refreshed metadata or rebalanced yet | Check metadata refresh, logs, and consumer assignments |
| Listener receives too many topics | Overly broad pattern | Restrict prefixes, suffixes, or specific versions |
| One app misses records | Two apps share the same group ID | Use separate group IDs if each app needs an independent copy |
| Authorization exception | Principal lacks permission on a pattern-matched topic | Check ACLs, discover, and read permissions |
| Listener hits schema errors | Multiple topics carry heterogeneous payloads | Distinguish schemas/topics and configure compatible deserializers |

## 12. Conclusion

`topicPattern` on `@KafkaListener` enables Spring Kafka to subscribe consumers using a regex instead of listing every topic. It fits scenarios where topics are created dynamically or follow a stable naming convention. The Kafka client can discover new matching topics when metadata refreshes, which may trigger consumer group rebalances.

Write narrow regexes aligned with business boundaries, escape dots properly, externalize patterns to configuration when needed, and choose `groupId` according to whether consumers share load or receive independent copies. A pattern neither creates topics nor grants read access; topics must exist, principals must have proper permissions, and listeners should be tested across multiple topics including dynamic topic creation.

## References

- [Spring for Apache Kafka — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/annotation-driven.html)
- [Apache Kafka — KafkaConsumer API](https://kafka.apache.org/documentation/#consumerapi)
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
