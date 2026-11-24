# Declaring topics on @KafkaListener

The `topics` attribute of `@KafkaListener` specifies one or more topics that the listener subscribes to. You can declare topic names directly, read them from Spring configuration, or use SpEL expressions to supply the list of topics. Choosing the right declaration style keeps listeners portable across environments, avoids topic-name typos, and keeps subscriptions explicit.

`topics` is a list of concrete topic names. It is not a consumer group, partition list, or wildcard expression. Kafka receives the subscription from the listener container and then assigns partitions of those topics to consumers in the group.

## 1. Declaring a Single Topic

The simplest approach is passing a topic name to `topics`:

```java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created.v1",
            groupId = "order-projection"
    )
    public void onOrderCreated(OrderCreated event) {
        // Update read model.
    }
}
```

In this example:

- `topics = "orders.created.v1"` instructs the consumer to subscribe to that exact topic name.
- `groupId = "order-projection"` identifies the consumer group. Instances sharing the same group ID divide the assigned partitions among themselves.
- `OrderCreated` is the payload type the listener receives after the Kafka deserializer and message converter finish converting.

Topic names in `topics` must match the names provisioned in Kafka, including letter casing. `orders.created.v1` and `Orders.Created.v1` are two different names.

## 2. Declaring Multiple Topics

`topics` is a string array, so you can declare multiple topic names in the same annotation:

```java
@KafkaListener(
        topics = {
                "orders.created.v1",
                "orders.updated.v1",
                "orders.cancelled.v1"
        },
        groupId = "order-audit"
)
public void onOrderEvent(OrderEvent event) {
    // Process events that share the same structure.
}
```

The listener subscribes to all three topics. Partitions across the three topics become a single subscription for the consumer group; Kafka distributes them among consumers via the partition assignor. If the combined subscription has nine partitions and the listener container has three consumers, each consumer may receive roughly three partitions, depending on actual assignment.

Multiple topics on one listener fit when they share compatible payloads and the same handling logic. If the topics have different schemas or event types, consider splitting listeners or using a common envelope with an explicit `eventType` field.

Example of splitting listeners when payload types differ:

```java
@Component
public class OrderEventListeners {

    @KafkaListener(topics = "orders.created.v1", groupId = "order-report")
    public void onCreated(OrderCreated event) {
        // Process OrderCreated.
    }

    @KafkaListener(topics = "orders.cancelled.v1", groupId = "order-report")
    public void onCancelled(OrderCancelled event) {
        // Process OrderCancelled.
    }
}
```

Two listeners can share a group ID. Kafka assigns partitions from the topics subscribed by the group; it does not mean each listener automatically receives every record from all topics. If each function needs an independent copy of all data, use separate group IDs.

## 3. Moving Topic Names into application.yml

In real applications, manage topic names through configuration instead of hard-coding them across classes. Example:

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
      orders-created: orders.created.v1
      orders-updated: orders.updated.v1
```

Listener using a property placeholder:

```java
@KafkaListener(
        topics = "${app.kafka.topics.orders-created}",
        groupId = "order-projection"
)
public void onOrderCreated(OrderCreated event) {
    // Process event.
}
```

Spring resolves `${app.kafka.topics.orders-created}` from `Environment` when creating the listener endpoint. If the property evaluates to `orders.created.v1`, the consumer subscribes to that exact topic.

You can declare a default value so local runs work when environment variables are unset:

```java
@KafkaListener(
        topics = "${app.kafka.topics.orders-created:orders.created.local}"
)
public void onOrderCreated(OrderCreated event) {
    // Process event.
}
```

Default values should only be used when the default topic genuinely fits the environment. In production, explicit configuration is usually preferable so the application never accidentally subscribes to a local or default topic.

## 4. Declaring Multiple Topics from Configuration

Because `topics` is an array, the most readable and controllable approach is putting each topic in its own annotation element:

```java
@KafkaListener(
        topics = {
                "${app.kafka.topics.orders-created}",
                "${app.kafka.topics.orders-updated}"
        },
        groupId = "order-audit"
)
public void onOrderEvent(OrderEvent event) {
    // Process events from both topics.
}
```

Corresponding YAML:

```yaml
app:
  kafka:
    topics:
      orders-created: orders.created.v1
      orders-updated: orders.updated.v1
```

Do not put two topic names in a single comma-separated string property and assume Spring will automatically split them into two elements of `topics`:

```yaml
app:
  kafka:
    topics:
      order-events: orders.created.v1,orders.updated.v1
```

If you bind this property to a single annotation element like `topics = "${app.kafka.topics.order-events}"`, the result may be interpreted as a single topic name containing a comma, rather than two topics. Use multiple placeholders as shown above or use SpEL returning a string array.

## 5. Using SpEL When a Bean Provides the Topic List

When the topic list needs to be centralized in a bean or built from application configuration, you can use a SpEL expression in `topics`.

Example bean providing the topic list:

```java
import org.springframework.stereotype.Component;

@Component("orderTopicCatalog")
public class OrderTopicCatalog {

    public String[] orderEventTopics() {
        return new String[] {
                "orders.created.v1",
                "orders.updated.v1"
        };
    }
}
```

Listener referencing the bean via SpEL:

```java
@KafkaListener(
        topics = "#{@orderTopicCatalog.orderEventTopics()}",
        groupId = "order-audit"
)
public void onOrderEvent(OrderEvent event) {
    // Receive events from the topic list provided by the bean.
}
```

The expression `#{@orderTopicCatalog.orderEventTopics()}` invokes the `orderTopicCatalog` bean and uses the returned `String[]` array as the topic list. This is helpful when the list is consolidated in a strongly typed configuration component.

SpEL is evaluated when Spring creates the endpoint. If the bean method later returns a new list, running subscriptions do not automatically update to reflect the new result. To change subscriptions at runtime, actively manage listener containers and a proper update workflow.

Avoid complex SpEL if a few property placeholders suffice. The more complex the expression, the harder it is to inspect the final values the listener registers.

## 6. Distinguishing topics, topicPattern, and topicPartitions

Spring Kafka offers three common ways to declare subscriptions:

| Attribute | Subscription style | When suitable |
|---|---|---|
| `topics` | List of specific topic names | Exact topics to read are known |
| `topicPattern` | Regex matching topic names | Want to consume topics created later following a naming convention |
| `topicPartitions` | Specifies exact topics and partitions | Explicit assignment to specific partitions is needed |

Example of `topics`:

```java
@KafkaListener(topics = {"orders.created.v1", "orders.updated.v1"})
public void onOrder(OrderEvent event) {
    // Subscribe to two specifically named topics.
}
```

Example of `topicPattern`:

```java
@KafkaListener(topicPattern = "orders\\..*")
public void onOrderTopic(ConsumerRecord<String, byte[]> record) {
    // Receive topics whose names start with orders.
}
```

Example of `topicPartitions`:

```java
@KafkaListener(
        topicPartitions = @TopicPartition(
                topic = "orders",
                partitions = {"0", "1"}
        )
)
public void onOrderPartition(ConsumerRecord<String, OrderCreated> record) {
    // Only receive assignments for partitions 0 and 1.
}
```

Do not declare `topics`, `topicPattern`, and `topicPartitions` together on the same listener endpoint. These are mutually exclusive subscription strategies, not additive filters.

Specifically, `topics = "orders.*"` is not a wildcard. `topics` treats that string as a literal topic name; to match multiple topics via regex, use `topicPattern`.

## 7. Topic Subscriptions and Consumer Groups

`topics` determines which data streams the listener wants to receive. `groupId` determines which consumer group the listener joins. These two attributes work together and do not replace each other.

Example of two services subscribing to `orders.created.v1`:

```java
@KafkaListener(
        topics = "orders.created.v1",
        groupId = "billing-service"
)
public void createBillingRecord(OrderCreated event) {
    // Process billing.
}

@KafkaListener(
        topics = "orders.created.v1",
        groupId = "analytics-service"
)
public void updateAnalytics(OrderCreated event) {
    // Update metrics.
}
```

The two groups maintain independent offsets and each group can receive every record from the topic. If two instances run listeners with `groupId = "billing-service"`, they split partitions to process the same workload.

If `groupId` is omitted from the annotation, the listener normally uses the group ID from `spring.kafka.consumer.group-id` in the consumer factory. You can set a shared default group in `application.yml` and override it on the annotation when a listener needs its own group.

## 8. Multiple Topics Do Not Mean One Record Goes to Every Listener

When a listener subscribes to multiple topics, it receives records from those topics according to the group's partition assignment. In steady state, a partition is assigned to at most one consumer in the same group; however, records may still be re-read after failures or rebalances if offsets have not been committed. Kafka does not duplicate the same record into one copy per listener in the same group.

If multiple functions must each receive every event, create separate consumer groups. Example:

```text
Topic orders.created.v1
  ├── group billing-service       -> create billing data
  ├── group order-projection      -> update read model
  └── group analytics-service     -> aggregate metrics
```

If multiple listeners share the same group ID and subscribe to the same topic, Kafka divides partitions among consumers in the group. A given consumer will not necessarily receive every record if that partition is assigned to another consumer.

## 9. Payload Types When Subscribing to Multiple Topics

A listener receiving multiple topics in a single method generally assumes records can be deserialized to a common parameter type. If the topics share a schema or envelope, this is straightforward:

```java
public record OrderEvent(
        String eventId,
        String orderId,
        String eventType) {
}

@KafkaListener(
        topics = {"orders.created.v1", "orders.updated.v1"},
        groupId = "order-search"
)
public void updateSearchIndex(OrderEvent event) {
    switch (event.eventType()) {
        case "OrderCreated" -> createDocument(event);
        case "OrderUpdated" -> updateDocument(event);
        default -> throw new IllegalArgumentException(
                "Unsupported event type: " + event.eventType());
    }
}
```

If schemas differ, you can split listeners by topic so each method receives the right type:

```java
@KafkaListener(topics = "orders.created.v1", groupId = "order-search")
public void onCreated(OrderCreated event) {
    createDocument(event);
}

@KafkaListener(topics = "orders.updated.v1", groupId = "order-search")
public void onUpdated(OrderUpdated event) {
    updateDocument(event);
}
```

Or accept raw records and route by topic:

```java
@KafkaListener(
        topics = {"orders.created.v1", "orders.updated.v1"},
        groupId = "order-router"
)
public void route(ConsumerRecord<String, byte[]> record) {
    switch (record.topic()) {
        case "orders.created.v1" -> handleCreated(record.value());
        case "orders.updated.v1" -> handleUpdated(record.value());
        default -> throw new IllegalArgumentException(
                "Unexpected topic: " + record.topic());
    }
}
```

The final example requires an extra step to deserialize bytes according to each topic's schema. Do not cast a byte array directly into a POJO; use an appropriate deserializer or converter.

## 10. Topics Must Be Provisioned and Authorized Separately

Declaring topic names in `@KafkaListener` only creates a subscription. It does not determine partition count, replication factor, retention, or topic ACLs.

In production, topics are usually pre-created via governance workflows, IaC, or `KafkaAdmin`/`NewTopic`. Example:

```java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic ordersCreatedTopic() {
        return TopicBuilder.name("orders.created.v1")
                .partitions(6)
                .replicas(3)
                .build();
    }
}
```

The application also needs a principal with permission to read the topic and use the consumer group. If the topic does not exist yet or ACLs are invalid, the listener may fail to start or receive no records depending on broker and container configuration.

Do not rely on auto topic creation to create production topics from annotation names. Auto-created topics may get default settings unsuitable for partition, replication, retention, or security requirements.

## 11. Topic Naming and Versioning

Topic names should follow a consistent convention reflecting domain, event, and version when needed:

```text
orders.created.v1
orders.updated.v1
payments.authorized.v1
inventory.stock-changed.v1
```

When an event's schema or meaning changes incompatibly, you can create a new versioned topic and update properties per environment. Do not rename the topic in the annotation and expect old data to move to the new topic automatically; a new topic is an independent log.

Kafka topic names are case-sensitive. Avoid creating names differing only by dots vs. underscores because some metrics tools normalize them identically.

## 12. Changing the Topic List While the Application Is Running

Values inside `@KafkaListener` are resolved when Spring creates the listener endpoint. If you change environment variables or config files after the application starts, existing subscriptions do not automatically re-read the annotation.

For typical configuration changes, the simplest approach is redeploying the application with the new properties. If dynamic topic changes are required, use `KafkaListenerEndpointRegistry` to stop and manage containers, or build programmatic endpoint/container registration. That workflow must manage offsets, group IDs, and stop/start timing to avoid missed or duplicate records.

Example looking up a container by listener ID:

```java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null) {
    container.stop();
    // Execute the designed subscription update procedure.
}
```

Stopping the container alone does not alter the topic list in the annotation. To change subscriptions, the application must update the endpoint or create a new container with the new topic list using APIs supported by your Spring Kafka version.

## 13. Testing Topic Lists

Integration tests should verify that the listener subscribes to the right topics and receives records from each expected topic. You can use `@EmbeddedKafka` or Testcontainers Kafka.

Example declaring an embedded broker for two topics:

```java
@SpringBootTest
@EmbeddedKafka(
        partitions = 1,
        topics = {"orders.created.v1", "orders.updated.v1"}
)
class OrderListenerIntegrationTest {

    @Autowired
    private KafkaTemplate<String, OrderEvent> kafkaTemplate;

    @Test
    void shouldPublishToConfiguredTopic() throws Exception {
        OrderEvent event = new OrderEvent(
                "event-101", "order-42", "OrderCreated");

        SendResult<String, OrderEvent> result = kafkaTemplate
                .send("orders.created.v1", "order-42", event)
                .get(10, TimeUnit.SECONDS);

        assertThat(result.getRecordMetadata().topic())
                .isEqualTo("orders.created.v1");
    }
}
```

The test above verifies that the producer sends to the right topic. To verify listener subscription, add consumer-side assertions such as a latch or Awaitility triggered when the listener receives an event. Use finite timeouts so tests do not hang if the listener receives no record.

Cases worth testing:

- The listener receives records from each topic in the list.
- The listener does not receive records from topics outside the list.
- Placeholders resolve properly per profile.
- Empty topic lists or missing properties are caught during context initialization.
- Multiple topics with compatible schemas deserialize properly.
- Missing topics or insufficient ACLs are observable in logs and container status.

## 14. Common Pitfalls When Declaring Topics

**Misspelling or wrong casing:** the consumer subscribes to a different name than the created topic. Check resolved properties and broker metadata.

**Combining multiple names with commas in one string:** a single `topics` element may become one topic name containing commas. Use multiple annotation elements or SpEL returning `String[]`.

**Using wildcards in `topics`:** `topics` does not interpret wildcards. Use `topicPattern` when regex matching is needed.

**Declaring `topics` and `topicPattern` simultaneously:** subscription strategies are mutually exclusive. Choose one attribute.

**Missing property placeholder:** Spring cannot resolve the topic name when creating the endpoint. Define properties for all profiles or provide an intentional default value.

**Topic list contains empty elements:** check configuration and SpEL output so empty or null names are never returned.

**One listener receiving multiple incompatible schemas:** deserializer or argument resolver cannot construct the parameter type. Split listeners or use explicit envelopes/routing.

**Confusing topic with group ID:** changing the topic changes which stream is read; changing the group ID changes the consumer progress scope.

**Assuming the annotation creates topics automatically:** provision topics separately and configure partitions, replication, retention, and ACLs as required.

**Changing a property without subscription changing:** annotations are resolved at endpoint registration time. Redeploy or manage containers/endpoints dynamically.

## 15. Production Readiness Checklist

- Every element in `topics` is a valid, exact topic name.
- Multi-topic lists are declared via multiple elements or SpEL returning an array, not relying on automatic CSV string splitting.
- Placeholders have values in the target deployment profile and never evaluate to empty strings.
- `topics`, `topicPattern`, and `topicPartitions` are used separately per subscription strategy.
- Topics within the same listener share compatible schemas or have explicit routing/deserialization.
- `groupId` matches the intended load-sharing or independent-consumption model.
- Total partitions and concurrency are sized for the entire subscription.
- Topics are provisioned with appropriate partitions, replication, retention, and ACLs.
- Tests verify record consumption from each topic as well as profile/configuration resolution.
- Logs/metrics exist to verify topic, partition, offset, consumer group, and lag.

Declaring `topics` on `@KafkaListener` explicitly defines the event streams an endpoint consumes. Use literal names for fixed subscriptions, property placeholders for environment-specific config, and SpEL only when a bean truly needs to supply the list. Distinguishing `topics`, `topicPattern`, `topicPartitions`, and `groupId` cleanly makes listeners easier to configure, test, and operate.
