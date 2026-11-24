# Subscribing to Topics by Name in Spring Kafka

A consumer must subscribe to receive data from one or more topics before Kafka assigns partitions to it. In Spring Kafka, the most common way is declaring `@KafkaListener(topics = "...")`. Topic names can be specified directly or resolved from Spring configuration so they can vary by environment without modifying source code.

Subscribing to topics by name lets a service explicitly specify the event streams it consumes. Distinguish between topic name, consumer group, and partition: a topic identifies the data stream, a group identifies the set of consumers sharing reading progress, and Kafka assigns partitions of the topic to consumers in the group.

## 1. How does topic subscription work?

When the listener container starts, Spring Kafka creates a Kafka consumer and invokes the `subscribe` mechanism with the declared list of topics. The consumer joins the group, receives partition assignments from Kafka, and invokes the listener when records are polled.

```mermaid
flowchart TD
    A[application.yml: topic names] --> B[@KafkaListener topics]
    B --> C[Spring listener container]
    C --> D[Kafka consumer subscribe]
    D --> E[Join consumer group]
    E --> F[Kafka assigns partitions]
    F --> G[Consumer poll records]
    G --> H[Deserializer]
    H --> I[Listener method]
```

When declaring `topics = "orders"`, the consumer subscribes to the topic whose exact name is `orders`. It does not subscribe to a specific partition. Kafka assigns that topic's partitions to consumers in the same group based on the partition assignor and group membership state.

For example, topic `orders` has six partitions and group `order-projection` has three consumers. Kafka can assign two partitions to each consumer. If another instance in the same group starts, Kafka can rebalance to redistribute partitions. Assignment details depend on partition count, consumer count, subscriptions, and the assignor.

## 2. Subscribing to a single topic with @KafkaListener

Example listener receiving order events from topic `orders`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-projection"
    )
    public void onOrderCreated(OrderCreated event) {
        // Update the order read model.
    }
}
```

Attributes in the example:

- `topics`: list of topic names the listener subscribes to.
- `groupId`: consumer group of the listener. Instances using the same group ID share partitions among themselves.
- `onOrderCreated`: method invoked by Spring Kafka when the consumer receives and converts a record.
- `OrderCreated`: payload type, which must be compatible with the configured deserializer.

`groupId` is the consumer group identity, not the topic name. A topic can be subscribed to independently by multiple groups. For example, `order-projection`, `billing-service`, and `analytics-service` can all subscribe to `orders`; each group maintains its own offsets and reads the stream independently.

If `groupId` is not set on the annotation, the listener uses the group ID from the consumer factory configuration, typically `spring.kafka.consumer.group-id`. Choose one clear place for configuration to avoid confusion across listeners.

## 3. Placing topic names in application.yml

In real applications, place topic names in configuration instead of hardcoding them across multiple classes. Example:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: order-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.OrderCreated
        spring.json.trusted.packages: com.example.orders

app:
  kafka:
    topics:
      orders: orders.v1
```

The listener references the property:

```java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "${app.kafka.topics.orders}"
    )
    public void onOrderCreated(OrderCreated event) {
        // Process the event.
    }
}
```

Spring resolves the placeholder `${app.kafka.topics.orders}` when creating the listener endpoint. If the property has value `orders.v1`, the consumer subscribes to the exact topic `orders.v1`.

Benefits of configuring topic names:

- Change topics across local, staging, or production without editing Java code.
- Centralize topic naming conventions in one place.
- Avoid typos or using different names for the same stream.
- Easily manage topic versions, such as `orders.v1` and `orders.v2`.

The property name is an application convention. `app.kafka.topics.orders` is not a Kafka client property; it is simply a configuration value that Spring injects into the annotation.

## 4. Subscribing to multiple topics by name

A listener can subscribe to multiple topics using the array form of the `topics` attribute:

```java
@KafkaListener(
        topics = {"orders.created", "orders.updated"},
        groupId = "order-audit"
)
public void onOrderEvent(OrderEvent event) {
    // Handle events with the same structure.
}
```

Each name can be resolved from configuration:

```java
@KafkaListener(
        topics = {
                "${app.kafka.topics.order-created}",
                "${app.kafka.topics.order-updated}"
        },
        groupId = "order-audit"
)
public void onOrderEvent(OrderEvent event) {
    // Handle events from both topics.
}
```

```yaml
app:
  kafka:
    topics:
      order-created: orders.created.v1
      order-updated: orders.updated.v1
```

Kafka assigns partitions of all subscribed topics across the consumer group. The total number of partitions in the subscription determines the usable level of parallelism. If a listener has three consumers but the subscription only has two partitions in total, at most two consumers are assigned partitions in steady state.

### When multiple topics share the same event type

A single listener method receiving multiple topics is convenient when the topics have compatible payloads, such as both using `OrderEvent`:

```java
@KafkaListener(
        topics = {"orders.created", "orders.updated"},
        groupId = "order-search-index"
)
public void updateIndex(OrderEvent event) {
    // Update the search index.
}
```

If the topics have different schemas or payload types, do not force them all into an incompatible POJO. You can use separate listeners with matching payload types, or receive `ConsumerRecord<String, byte[]>` or a common envelope and route by topic and event type.

Example splitting listeners when schemas differ:

```java
@KafkaListener(topics = "orders.created", groupId = "order-report")
public void onCreated(OrderCreated event) {
    // Handle OrderCreated.
}

@KafkaListener(topics = "orders.cancelled", groupId = "order-report")
public void onCancelled(OrderCancelled event) {
    // Handle OrderCancelled.
}
```

Two listeners can share the same group ID. When the same group subscribes to the respective topics, Kafka distributes the partitions of the topics in the subscription under that group. Check concurrency settings and total partitions to avoid creating redundant consumers.

## 5. Topic names and naming conventions

A topic name is an exact identifier in Kafka. Topic names are case-sensitive, so `orders`, `Orders`, and `ORDERS` are treated as different names.

Common Kafka topic naming rules:

- Length from 1 to 249 characters.
- Only ASCII letters, digits, dots (`.`), underscores (`_`), and hyphens (`-`).
- Do not use names consisting only of `.` or `..`.
- Use a consistent convention to make management by domain, event, and version easier.

Examples:

```text
orders.created.v1
payments.authorized.v1
inventory.stock-changed.v1
customer-profile.updated.v2
```

Avoid creating multiple topics that differ only by a dot and an underscore, such as `orders.created` and `orders_created`. Some metric systems normalize these two characters identically, making metrics hard to distinguish.

Topic names should express the domain and event, along with a versioning strategy when schemas or event semantics change incompatibly. Do not embed environment names into topic names if the same application can select topics via environment configuration.

## 6. Topic name vs. topicPattern

`topics` uses specific topic names. `topicPattern` uses a regular expression to subscribe to any topic whose name matches the pattern. These two approaches serve different purposes.

Subscribing by specific name:

```java
@KafkaListener(topics = "orders.created.v1")
public void onOrder(OrderCreated event) {
    // Only receives topic orders.created.v1.
}
```

Subscribing by pattern:

```java
@KafkaListener(topicPattern = "orders\\..*")
public void onAnyOrderEvent(ConsumerRecord<String, byte[]> record) {
    // Receives topics matching the expression orders\..*.
}
```

In Java code, the pattern uses two backslashes to create a regex that escapes the dot; it matches topic names starting with orders.

Do not use `topics = "orders.*"` expecting it to act as a wildcard. In `topics`, that is treated as a literal topic name; the `*` character is also invalid in Kafka topic names. If you need to subscribe to a set of topics that changes over time, use `topicPattern` and tightly control the regex.

Do not declare `topics`, `topicPattern`, and `topicPartitions` simultaneously on the same listener endpoint. Choose the single subscription mechanism suited to your needs.

## 7. When to use topicPartitions instead of subscribing by name?

`topics` and `topicPattern` use Kafka-managed subscription within a consumer group. `topicPartitions` is used when the application wants to directly assign specific partitions to the listener.

Example:

```java
@KafkaListener(
        groupId = "orders-partition-reader",
        topicPartitions = @TopicPartition(
                topic = "orders",
                partitions = {"0", "1"}
        )
)
public void onPartitionRecord(ConsumerRecord<String, OrderCreated> record) {
    // Only processes partitions 0 and 1.
}
```

With this approach, the listener receives an explicit assignment for the selected partitions. The application is responsible for splitting partitions across listeners/instances to prevent multiple consumers from trying to read the same partition unintentionally. This approach is less flexible when partition counts change and does not take full advantage of automatic subscription distribution.

In most business applications, use `topics` by name and let Kafka manage partition assignment. Only use `topicPartitions` when there is a clear requirement for partition ownership, processing a fixed set of partitions, or controlling initial offsets per partition.

## 8. Subscription does not automatically create topics

Declaring `@KafkaListener(topics = "orders")` means the consumer subscribes to read that topic. It is not an administrative command to create the topic with a desired partition count or replication factor.

Some brokers may enable `auto.create.topics.enable`; in that case, a topic may be created automatically when a client references a non-existent topic. However, you should not rely on this mechanism in production because the topic may be created with default settings unsuitable for partition, replication, retention, or security requirements.

Create topics in advance through an administrative process or use `KafkaAdmin` with `NewTopic`:

```java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
                .partitions(6)
                .replicas(3)
                .build();
    }
}
```

`KafkaAdmin` requires valid bootstrap servers and topic-creation permissions. In production systems, a platform team may manage topics separately via IaC or deployment pipelines; in that case, the application only needs to subscribe to provisioned topics.

If the topic does not exist yet, the consumer may not receive records, and startup behavior depends on Spring Kafka and broker configuration. You can enable missing-topic checks using the listener container's `missingTopicsFatal` property if you want the application to fail fast; the default for this property varies by version and configuration, so verify against the exact version you use.

## 9. Multiple listeners and multiple consumer groups

An application can declare multiple listeners for different topics:

```java
@Component
public class OrderListeners {

    @KafkaListener(
            id = "orderProjectionListener",
            topics = "${app.kafka.topics.orders}",
            groupId = "order-projection"
    )
    public void project(OrderCreated event) {
        // Update the read model.
    }

    @KafkaListener(
            id = "orderAuditListener",
            topics = "${app.kafka.topics.orders}",
            groupId = "order-audit"
    )
    public void audit(OrderCreated event) {
        // Write audit independently.
    }
}
```

The two listeners subscribe to the same topic but use two different group IDs. Therefore, each group can receive all records from the topic and maintain its own offsets. The `id` attribute identifies the listener endpoint in Spring; it does not replace `groupId`.

If two listeners need to share the load of the same task, use the same group ID and design an appropriate partition assignment. If they are two independent business functions that need to receive all events, use separate group IDs.

## 10. Resolving topics from strongly typed configuration

For applications with many topics, you can group topic names into a configuration class to reduce typos and make configuration easy to validate at startup:

```java
@ConfigurationProperties(prefix = "app.kafka.topics")
public record KafkaTopicProperties(
        String orders,
        String payments,
        String inventory) {
}
```

Enable binding:

```java
@Configuration
@EnableConfigurationProperties(KafkaTopicProperties.class)
public class KafkaPropertiesConfiguration {
}
```

With `@KafkaListener`, the annotation typically uses `${...}` placeholders to resolve configuration values directly. If you want to use a SpEL expression to get a list from a bean, ensure the bean is registered and the expression returns the exact type expected by the annotation. For topics that are static per environment, simple placeholders are usually easier to read and less complex.

Note that annotations are processed when Spring creates the endpoint. Changing external configuration files after the application has started does not automatically change running subscriptions. To change topics at runtime, you need a listener container management mechanism or an application restart via the deployment process.

## 11. Environment-specific configuration

Local, staging, and production can use different topics:

```yaml
# application-local.yml
app:
  kafka:
    topics:
      orders: orders.local

---
# application-prod.yml
app:
  kafka:
    topics:
      orders: orders.v1
```

Activate the appropriate profile with `SPRING_PROFILES_ACTIVE`. The listener still uses a single placeholder:

```java
@KafkaListener(topics = "${app.kafka.topics.orders}")
public void onOrder(OrderCreated event) {
    // Logic does not depend on a specific topic name.
}
```

When deploying, verify that the property is loaded for the right profile and that the corresponding topic exists. You can inspect resolved configuration via startup logs or the Spring Actuator environment endpoint if that endpoint is properly secured.

Avoid accidentally running the same consumer group across two environments that share a Kafka cluster while subscribing to unintended topics. Group IDs and topic naming need clear environment scoping when environments share brokers.

## 12. Verifying subscription and partition assignment

After the application starts, verify that the consumer subscribed to the right topic, in the right group, and received the expected partition assignments.

Inspect topic details:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Inspect consumer group status:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection
```

Consumer group output shows topic, partition, consumer ID, committed offset, and lag. If the topic does not appear in the group, check whether the listener was initialized, whether the topic property resolved properly, whether the group ID is right, and whether the consumer has permission to read the topic.

Inside the application, you can log topic, partition, and offset fields in the listener to confirm actual data:

```java
@KafkaListener(topics = "${app.kafka.topics.orders}")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    log.info(
            "Received Kafka record: topic={}, partition={}, offset={}",
            record.topic(), record.partition(), record.offset());

    // Process record.value().
}
```

Do not log the entire payload or sensitive data. In multi-topic systems, add an event ID or correlation ID to trace across services.

## 13. Common errors when subscribing by name

**Wrong topic name:** Kafka is case-sensitive. Check the resolved configuration value and the topic name on the broker.

**Wrong property reference:** the listener points to `${app.kafka.topic.orders}` while YAML declares `app.kafka.topics.orders`. An incorrect placeholder can prevent endpoint initialization or resolve to an unintended value.

**Confusing topic with group ID:** changing the group ID changes independent read progress; changing the topic changes the subscribed data stream. The two attributes are not interchangeable.

**Multiple instances using different group IDs:** each instance may receive all data instead of sharing partitions. Ensure group IDs match if the goal is scaling the same consumer group.

**Topic does not exist yet:** subscribing does not replace topic creation. Provision the topic first and verify access permissions.

**Using wildcards in topics:** `topics` accepts literal names; use `topicPattern` if regex is needed.

**Using one listener for incompatible schemas:** the deserializer may fail or the listener may fail to bind the payload. Split listeners or use a common envelope with a clear routing strategy.

**Changing a property and expecting the listener to switch immediately:** subscriptions are created when the endpoint starts. Configuration changes require container update procedures or a restart.

**Using topicPartitions while expecting Kafka to auto-balance partitions:** specifying partitions directly changes the assignment mechanism. Choose `topics` for normal subscriptions.

**Missing read permissions on the topic:** check ACLs of the consumer principal for the topic and group, as well as the security protocol and credentials.

## 14. Pre-production listener checklist

- Topic names are accurate, follow conventions, and are placed in proper configuration.
- Placeholders in `@KafkaListener` point to the right properties and resolve under the deployment profile.
- Topics are provisioned with appropriate partitions, replication, retention, and security settings.
- `groupId` accurately reflects load sharing vs. independent consumption.
- The listener's payload type is compatible with the key/value deserializers.
- Multiple topics on a single listener share compatible schemas or have a clear routing strategy.
- `topicPattern` is used only when regex subscription is genuinely needed; `topicPartitions` is used when explicit assignment is required.
- Concurrency matches the total number of partitions in the subscription.
- The consumer has ACLs to read the topic and join the group.
- Logs/metrics exist to verify topic, partition, offset, lag, and listener errors.

Subscribing by name lets a listener clearly declare the event streams an application needs to receive. By separating topics, group IDs, and partition assignments while managing topic names through configuration, a Spring Kafka application can deploy consistently across environments and scale consumer groups without changing event-processing logic.
