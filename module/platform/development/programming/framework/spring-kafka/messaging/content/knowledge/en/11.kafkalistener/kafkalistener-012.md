# Using Property Placeholders in Annotations

Spring Kafka allows using property placeholders inside `@KafkaListener` attributes to pull topics, consumer groups, concurrency, and listener settings from external configuration. This lets the same codebase run across local, test, staging, and production environments with different configuration values.

Placeholders take the form `${property.name}`. Spring reads the value from `Environment` and substitutes it into the annotation when creating the listener endpoint. You can supply a default value with `${property.name:default}`. When expressions or bean references are needed, Spring supports SpEL with `#{...}`; these two mechanisms serve different purposes and should not be confused.

## Learning Objectives

After this lesson, you will be able to:

- Explain how Spring resolves property placeholders in annotations.
- Use placeholders for `topics`, `topicPattern`, `groupId`, `concurrency`, and `containerFactory`.
- Declare multiple topics and safe default values.
- Distinguish `${...}` placeholders from `#{...}` SpEL expressions.
- Organize configuration across `application.yml`, profiles, environment variables, and command-line arguments.
- Understand the relationship between `id`, `groupId`, and `group.id` in `@KafkaListener`.
- Recognize missing-placeholder, type-mismatch, and empty-configuration errors.
- Test listeners with different configuration values.
- Understand why changing external config at runtime does not automatically update running endpoints.

## 1. How Do Property Placeholders Work?

A property placeholder is a reference to a value in the Spring `Environment`. Instead of hard-coding a topic or group ID in the annotation, you specify a property name:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.orders}",
    groupId = "${app.kafka.consumer.group-id}"
)
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Suppose configuration contains:

~~~yaml
app:
  kafka:
    topics:
      orders: orders.v1
    consumer:
      group-id: order-service
~~~

When Spring registers the listener endpoint, the values resolve to:

- topics = orders.v1
- groupId = order-service

High-level processing flow:

~~~mermaid
flowchart TD
    A["application.yml / environment / profile"] --> B["Spring Environment"]
    B --> C["Resolve property placeholders"]
    C --> D["@KafkaListener endpoint"]
    D --> E["Listener container factory"]
    E --> F["Consumer and listener container"]
    F --> G["Register with Kafka"]
~~~

Resolution happens during application context initialization and listener endpoint registration. The listener container receives the resolved values to create consumers and subscribe to the matching topics.

Placeholders are purely a configuration lookup mechanism. They do not create topics in Kafka, validate message schemas, or replace serializer/deserializer settings.

## 2. Externalizing Topic and Group ID Outside Annotations

A common organization places application-used values in `application.yml`:

~~~yaml
app:
  kafka:
    topics:
      orders: orders.v1
      refunds: refunds.v1
      audit: audit.events
    consumer:
      group-id: order-service
    listener:
      concurrency: 3
      auto-startup: true
~~~

Listener using those properties:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        id = "orders-listener",
        topics = "${app.kafka.topics.orders}",
        groupId = "${app.kafka.consumer.group-id}",
        concurrency = "${app.kafka.listener.concurrency:1}",
        autoStartup = "${app.kafka.listener.auto-startup:true}"
    )
    public void onOrder(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

Attributes commonly externalized from annotations:

| Annotation attribute | Suitable property placeholder |
|---|---|
| topics | Topic name or separately declared topics |
| topicPattern | Regex to match topics |
| groupId | Listener's consumer group |
| clientIdPrefix | Client ID prefix for consumer observability |
| concurrency | Number of child consumers in the listener container |
| containerFactory | Name of the listener container factory |
| autoStartup | Enable/disable automatic container startup |

Externalize values that vary by environment or require operational tuning. Stable listener identifiers such as `id` can usually remain in source code for consistent lifecycle management and logging.

## 3. Using Placeholders for Multiple Topics

The `topics` attribute of `@KafkaListener` takes an array of topic names. When listening to multiple topics, declare each placeholder as a separate array element:

~~~java
@KafkaListener(
    id = "order-domain-listener",
    topics = {
        "${app.kafka.topics.orders}",
        "${app.kafka.topics.refunds}"
    },
    groupId = "${app.kafka.consumer.group-id}"
)
public void onDomainEvent(Object event) {
    domainService.handle(event);
}
~~~

Configuration:

~~~yaml
app:
  kafka:
    topics:
      orders: orders.v1
      refunds: refunds.v1
    consumer:
      group-id: order-domain-service
~~~

Declaring each topic explicitly shows readers every data source the listener uses. Do not assume a comma-separated string in a single property will always be split into multiple annotation array elements; conversion behavior depends on position and binding mechanics. For array-typed `topics`, the clearest pattern is one placeholder per element.

If the topic list changes frequently or is managed as a configurable list, consider `@ConfigurationProperties` and programmatic endpoint/container creation rather than cramming dynamic lists into static annotations.

## 4. Placeholders for topicPattern

If a listener needs to subscribe to topics by regex, use `topicPattern`:

~~~yaml
app:
  kafka:
    topics:
      order-pattern: "orders\\..*"
~~~

~~~java
@KafkaListener(
    id = "all-order-topics-listener",
    topicPattern = "${app.kafka.topics.order-pattern}",
    groupId = "${app.kafka.consumer.group-id}"
)
public void onOrderTopicEvent(OrderEvent event) {
    orderService.process(event);
}
~~~

The example regex matches topics such as `orders.created`, `orders.updated`, or `orders.cancelled`. The pattern is applied when the consumer registers the topic pattern and metadata refreshes.

Keep these distinct:

- `topics` declares specific topic names.
- `topicPattern` declares a regular expression to select topics.
- `topicPartitions` specifies exact partitions.

These are distinct subscription/assignment strategies. Do not declare them simultaneously expecting the listener to merge all lists.

## 5. Placeholders for concurrency and containerFactory

Concurrency determines how many child consumers `ConcurrentMessageListenerContainer` creates for the listener endpoint. It can be configured per environment:

~~~yaml
app:
  kafka:
    listener:
      concurrency: 3
      container-factory: orderListenerContainerFactory
~~~

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "${app.kafka.topics.orders}",
    groupId = "${app.kafka.consumer.group-id}",
    concurrency = "${app.kafka.listener.concurrency:1}",
    containerFactory = "${app.kafka.listener.container-factory:kafkaListenerContainerFactory}"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

If a topic has six partitions, concurrency three allows up to three child consumers to receive partitions of that topic. If concurrency exceeds partition count, some child consumers will not be assigned partitions.

The concurrency value must be a valid positive integer. If the property holds a string that cannot be parsed as a number, the listener endpoint may fail to initialize. Validate deployment config values and pick intentional defaults.

When different listeners have different requirements, you can create multiple container factories. A `containerFactory` placeholder lets you switch factories by environment, provided the property points to an actual factory bean registered in the application context.

## 6. Default Values with Colon Syntax

Spring supports default values inside placeholders:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.orders:orders}",
    groupId = "${app.kafka.consumer.group-id:order-service}",
    concurrency = "${app.kafka.listener.concurrency:1}"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

The syntax is:

~~~text
${property.name:defaultValue}
~~~

If the property does not exist, Spring uses the value after the colon. This is handy for local setups or safe defaults.

However, defaults should not mask production configuration mistakes. For example, if production requires per-tenant topics or per-service group IDs, a shared default could cause multiple instances to read from the same group or write to the wrong topic unintentionally.

Also distinguish a missing property from a property that exists with an empty value. A default typically applies when the property cannot be resolved; an explicitly declared empty value may remain an empty string. Validate required configuration rather than relying solely on placeholder defaults.

### When Should You Set a Default?

| Property | Set a default? | Reason |
|---|---|---|
| concurrency | Usually yes | Can pick a safe low level for local runs |
| autoStartup | Possibly yes | Can default to true per app behavior |
| groupId | Depends on environment | A shared default may cause multiple services to share a group unintentionally |
| Mandatory production topic | With caution | A default could cause data to be sent/read on the wrong topic |
| containerFactory | Possibly yes | Only when the default factory is guaranteed to exist |

## 7. Distinguishing Placeholders from SpEL

Spring supports two syntaxes inside annotations:

| Syntax | Mechanism | Purpose |
|---|---|---|
| ${property.name} | Property placeholder | Read values from Spring `Environment` |
| #{expression} | Spring Expression Language (SpEL) | Evaluate expressions, invoke beans, or access properties/methods |

Placeholders suit simple configuration values:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.orders}",
    groupId = "${app.kafka.consumer.group-id}"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

SpEL suits values that must come from a bean or be computed:

~~~java
@KafkaListener(
    topics = "#{@kafkaTopicSettings.ordersTopic}",
    groupId = "#{@consumerSettings.groupId}"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

Example bean providing values:

~~~java
@Component("kafkaTopicSettings")
public class KafkaTopicSettings {

    public String getOrdersTopic() {
        return "orders.v1";
    }
}
~~~

In SpEL, `@beanName` accesses a bean in the application context. The expression is evaluated in the SpEL context supplied by Spring Kafka when creating the endpoint.

Do not switch to SpEL merely because a placeholder is not working yet. Check the property source and property name first. Conversely, if you need to call a bean or compute a value, SpEL expresses that intent more cleanly.

Both mechanisms can be combined inside a SpEL expression, though nested syntax is hard to read and error-prone. Use nesting only when strictly necessary; for standard config, keeping `${...}` for properties and `#{...}` for expressions is much easier to maintain.

## 8. Property Sources: application.yml, Profiles, and Environment Variables

The Spring `Environment` can load properties from multiple sources. In Spring Boot, common sources include:

- `application.yml` or `application.properties`.
- Profile-specific files such as `application-dev.yml`, `application-prod.yml`.
- Runtime environment variables.
- Java system properties.
- Command-line arguments.
- Other external configuration sources integrated by the application.

Default configuration example:

~~~yaml
# application.yml
app:
  kafka:
    topics:
      orders: orders.local
    consumer:
      group-id: order-service-local
~~~

Production configuration:

~~~yaml
# application-prod.yml
app:
  kafka:
    topics:
      orders: orders.production
    consumer:
      group-id: order-service
~~~

Activating a profile:

~~~bash
java -jar messaging-service.jar --spring.profiles.active=prod
~~~

Overriding via environment variables:

~~~bash
APP_KAFKA_TOPICS_ORDERS=orders.production-v2
APP_KAFKA_CONSUMER_GROUPID=order-service-v2
~~~

Or via command line:

~~~bash
java -jar messaging-service.jar \
  --app.kafka.topics.orders=orders.canary \
  --app.kafka.consumer.group-id=order-service-canary
~~~

Spring Boot applies binding and precedence rules across property sources. When multiple sources declare the same key, the higher-precedence source wins. Inspect the effective configuration of the target deployment environment rather than reading only `application.yml` in the repository.

## 9. Using Placeholders with @TopicPartition

When a listener needs static assignment, topic and partition values can also be configured via placeholders on the corresponding annotation attributes.

Example:

~~~yaml
app:
  kafka:
    topics:
      orders: orders.v1
    partitions:
      orders: "0"
~~~

~~~java
@KafkaListener(
    id = "orders-partition-listener",
    groupId = "${app.kafka.consumer.group-id}",
    topicPartitions = @TopicPartition(
        topic = "${app.kafka.topics.orders}",
        partitions = {"${app.kafka.partitions.orders:0}"}
    )
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

In this example, the listener is assigned partition 0 of the configured topic. The partition index is a string in the annotation; the value must resolve to a valid partition and that partition must exist on the topic.

When using `partitionOffsets` and `@PartitionOffset`, `initialOffset` can also be read from a property:

~~~java
@KafkaListener(
    id = "orders-replay-listener",
    groupId = "${app.kafka.replay.group-id}",
    topicPartitions = @TopicPartition(
        topic = "${app.kafka.topics.orders}",
        partitionOffsets = @PartitionOffset(
            partition = "0",
            initialOffset = "${app.kafka.replay.initial-offset:0}"
        )
    )
)
public void replay(OrderEvent event) {
    replayService.handle(event);
}
~~~

Distinguish initial offset from the group's committed offset. A replay job should use a separate group ID to avoid shifting the read position used by production consumers. Initial seek and committed offset handling can be affected by Spring Kafka version and container configuration; verify behavior against your actual library version.

## 10. Relationship Between id and groupId in @KafkaListener

These two attributes serve different purposes:

- `id` identifies the listener endpoint/container in Spring Kafka. You can use this ID to look up the container in `KafkaListenerEndpointRegistry`, and to stop, start, or pause the listener.
- `groupId` identifies the consumer group used to divide partitions and store offsets.
- `idIsGroup` controls whether `id` is used as the group ID when `groupId` is not declared. By default `idIsGroup` is `true` in Spring Kafka versions supporting this attribute.

Example declaring both explicitly:

~~~java
@KafkaListener(
    id = "orders-listener",
    idIsGroup = false,
    topics = "${app.kafka.topics.orders}",
    groupId = "${app.kafka.consumer.group-id}"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

When `groupId` is declared, the group ID comes from that property. Setting `idIsGroup=false` clarifies that `id` is strictly for endpoint management. If `groupId` is omitted and `idIsGroup=true`, `id` may be used as the group ID instead of the shared `group.id` setting.

This matters when multiple listeners exist in the same application: each listener may need its own group ID even if they live in the same class or read the same topic.

## 11. Common Placeholder Resolution Errors

| Error | Possible cause | How to check |
|---|---|---|
| Could not resolve placeholder | Property not declared or file/profile not loaded | Check property name, active profile, and config sources |
| Empty topic | Property exists with an empty value | Validate required values and check environment variables |
| Invalid concurrency | Property is not a positive integer | Check resolved value |
| Container factory not found | Placeholder points to a wrong bean name | Check `@Bean` factory names in the context |
| Listener uses wrong group | `groupId` overridden or `idIsGroup` caused confusion | Declare `groupId` explicitly and check effective config |
| Listener subscribes to wrong topic | Another property source overrode the value | Check active profiles and effective config |
| File changed but listener unchanged | Endpoint already created and container running | Restart or update container via management mechanism |

When a required placeholder cannot be resolved, Spring typically fails during application context creation or listener registration. Treat this as a startup error to fix early; do not suppress it by ignoring unresolved placeholders globally if the listener needs that value to run properly.

## 12. Validating Configuration Before Creating Listeners

For applications with many topics and listeners, consolidate configuration into a dedicated class using `@ConfigurationProperties`. Annotations can still use placeholders for needed fields while complex settings are validated centrally.

Example:

~~~java
@ConfigurationProperties(prefix = "app.kafka")
@Validated
public class KafkaApplicationProperties {

    @NotBlank
    private String ordersTopic;

    @NotBlank
    private String consumerGroupId;

    @Min(1)
    @Max(20)
    private int concurrency = 1;

    // getters and setters
}
~~~

The configuration above illustrates validating required values and capping concurrency. If using nested YAML structures such as `topics.orders` and `consumer.group-id`, define matching nested classes instead of forcing properties into flat names.

You can inject the properties bean into services or factories. For annotations, property placeholders remain a simple way to read values at endpoint registration time. For configurations requiring cross-field validation or structural changes, `@ConfigurationProperties` is easier to organize and test.

## 13. Testing Listeners with Different Configuration Values

Tests must verify that the endpoint actually uses the intended topic and group ID after resolution, not merely that a YAML file contains the property.

Properties can be overridden in tests:

~~~java
@SpringBootTest(properties = {
    "app.kafka.topics.orders=orders-test",
    "app.kafka.consumer.group-id=order-test-group",
    "app.kafka.listener.concurrency=1"
})
class OrderListenerTest {
    // Integration test with a Kafka broker or EmbeddedKafka.
}
~~~

Useful test scenarios:

- Boot the application context with valid properties and verify the listener endpoint is created.
- Override the topic in tests to ensure the listener reads the test topic instead of a real environment topic.
- Override the group ID and confirm the consumer belongs to the right group.
- Omit a required property to confirm the application fails fast with a clear message.
- Set an invalid concurrency to verify the error is caught during initialization.
- Verify `dev`/`prod` profiles select the right topic and group.
- Test placeholder defaults when a property is absent.
- Test `topicPattern` and `topicPartitions` if the application uses those endpoint styles.

In integration tests, synchronize on listener/container state and actually received messages. Do not rely on short sleeps to conclude an endpoint has subscribed or completed assignment.

## 14. When Do Property Changes Take Effect?

Placeholders in `@KafkaListener` are resolved when Spring creates the endpoint. Therefore, modifying `application.yml` or environment variables after the listener starts does not automatically update the running container's topic, group ID, or concurrency.

To apply configuration changes, you can:

1. Restart the application so endpoints are recreated with the new properties.
2. Manage the container via `KafkaListenerEndpointRegistry` and stop/restart it according to updated config.
3. For truly dynamic changes, create and manage listener containers programmatically rather than relying solely on static annotations.

Do not mutate `Environment` directly expecting running annotations to re-resolve automatically. Placeholders are not a listener hot-reload mechanism.

Even if a system uses Spring Cloud refresh or a config server, refreshing configuration beans does not automatically re-register listener endpoints. Explicit lifecycle logic and thorough testing of assignment/topic changes are required before rollout.

## 15. Checklist for Using Placeholders in @KafkaListener

- [ ] Topic and group ID properties are declared in the appropriate config sources.
- [ ] Placeholder names are accurate and free of profile mismatches.
- [ ] Required values are non-empty.
- [ ] Defaults are used only where genuinely safe.
- [ ] Multiple topics are declared explicitly per array element.
- [ ] `topicPattern` and `topicPartitions` are used for their intended purposes.
- [ ] `concurrency` is a positive integer matching partition counts.
- [ ] `containerFactory` points to a registered bean.
- [ ] `id` and `groupId` are clearly distinguished.
- [ ] SpEL is used only when expressions or bean access are required.
- [ ] Tests can override properties without touching production topics.
- [ ] A restart or container-update procedure exists when configuration changes.

## Conclusion

Property placeholders decouple `@KafkaListener` configuration from source code. Use `${...}` to read topics, group IDs, concurrency, and container factories from Spring `Environment`; use `${...:default}` for intentional defaults. SpEL `#{...}` fits when expressions or bean references are required. Keep `id` distinct from `groupId`, verify property sources per environment, validate values before creating listeners, and remember that post-startup configuration changes do not automatically update running endpoints. This structure makes Spring Kafka straightforward to deploy across environments and reduces errors caused by hard-coding topics or consumer groups.

