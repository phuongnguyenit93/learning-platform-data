# Using SpEL in Annotations

## Learning Objectives

Within the **@KafkaListener** chapter, this lesson explains how to use Spring Expression Language (SpEL) inside annotation attributes to configure listeners flexibly from beans, application configuration, and deployment environments.

**SPRING_KAFKA_MESSAGING** focuses on building applications that send and receive Kafka events using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, while helping learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-lettering, transactions, exactly-once semantics, concurrency, and testing. Using SpEL in `@KafkaListener` helps resolve topics, topic patterns, or group IDs from managed configuration sources so listeners can run the same source code across multiple environments.

After this lesson, learners will be able to:

- Distinguish property placeholders `${...}` from SpEL expressions `#{...}`.
- Reference Spring beans inside `@KafkaListener` attributes.
- Use the `__listener` pseudo-bean to read configuration from the listener bean itself.
- Configure `topics`, `topicPattern`, and `groupId` using expressions.
- Understand the data types an expression must return.
- Recognize when expressions are evaluated and their impact on listener lifecycle.
- Diagnose expression, placeholder, bean-reference, and topic-subscription errors.
- Test listeners configured with SpEL.

## 1. Why Use SpEL in @KafkaListener?

A listener typically declares a topic and consumer group:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void handle(OrderCreated event) {
    // Process order event.
}
~~~

This direct declaration is easy to read, but when the same application runs across multiple environments or topics are managed centrally, hard-coding topic names in annotations makes configuration changes harder.

Spring Kafka allows property placeholders or SpEL inside `@KafkaListener` attributes. Instead of writing topic names directly, a listener can pull values from `application.yml` or a Spring bean.

Example:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.order-created}",
    groupId = "${app.kafka.consumer-groups.billing}"
)
public void handle(OrderCreated event) {
    // Process order event.
}
~~~

Or use SpEL to reference a bean:

~~~java
@KafkaListener(
    topics = "#{@kafkaTopicProperties.orderCreated}",
    groupId = "#{@consumerGroupProperties.billing}"
)
public void handle(OrderCreated event) {
    // Process order event.
}
~~~

Both approaches decouple configuration from processing logic. Property placeholders fit simple values from `Environment`; SpEL is useful when you need to read bean properties, invoke methods, or compute values via an expression.

## 2. Distinguishing Property Placeholders and SpEL

These two syntaxes often appear side by side in Spring annotations, yet serve different purposes.

| Syntax | Name | Value source | Example |
|---|---|---|---|
| `${...}` | Property placeholder | `Environment`, `application.yml`, environment variables, property sources | `${app.kafka.topics.order-created}` |
| `#{...}` | SpEL expression | Spring Expression Language, beans, and expression context | `#{@kafkaTopicProperties.orderCreated}` |

### 2.1. Property Placeholder

Suppose `application.yml` contains:

~~~yaml
app:
  kafka:
    topics:
      order-created: commerce.order.created
    consumer-groups:
      billing: billing-service
~~~

Listener directly referencing the properties:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.order-created}",
    groupId = "${app.kafka.consumer-groups.billing}"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

Spring substitutes placeholders with matching values from configuration. This is the simplest choice when values depend only on environment configuration.

If a property does not exist and has no suitable default, creating the listener endpoint may fail at application startup.

You can define a default inline inside the placeholder:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.order-created:commerce.order.created}"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

The syntax after the colon specifies the default value when the property is not declared.

### 2.2. SpEL Expression

SpEL lets you write an expression rather than merely fetching a configuration string. An expression can:

- Read a property of a Spring bean.
- Invoke a method on a bean.
- Access values in the expression context.
- Use conditional operators to choose a value.
- Access static constants via the type operator.

Example referencing a bean:

~~~java
@KafkaListener(
    topics = "#{@kafkaTopicProperties.orderCreated}"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

Where:

- `#` opens a SpEL expression.
- `@kafkaTopicProperties` references the bean named `kafkaTopicProperties`.
- `.orderCreated` reads the `orderCreated` property of the bean.

SpEL is useful when values must come from a bean or be computed. If you only need to read a simple property, a placeholder is usually easier to read and operate.

## 3. Declaring a Topic Configuration Bean

A common pattern is grouping topics into a strongly typed configuration bean.

`application.yml`:

~~~yaml
app:
  kafka:
    topics:
      order-created: commerce.order.created
      order-cancelled: commerce.order.cancelled
      payment-authorized: commerce.payment.authorized
~~~

Configuration bean:

~~~java
@Component("kafkaTopicProperties")
@ConfigurationProperties(prefix = "app.kafka.topics")
public class KafkaTopicProperties {

    private String orderCreated;
    private String orderCancelled;
    private String paymentAuthorized;

    public String getOrderCreated() {
        return orderCreated;
    }

    public void setOrderCreated(String orderCreated) {
        this.orderCreated = orderCreated;
    }

    public String getOrderCancelled() {
        return orderCancelled;
    }

    public void setOrderCancelled(String orderCancelled) {
        this.orderCancelled = orderCancelled;
    }

    public String getPaymentAuthorized() {
        return paymentAuthorized;
    }

    public void setPaymentAuthorized(String paymentAuthorized) {
        this.paymentAuthorized = paymentAuthorized;
    }
}
~~~

Spring Boot binds properties from `application.yml` into the bean. `@Component("kafkaTopicProperties")` registers the bean under the name referenced in SpEL.

Listener referencing the bean:

~~~java
@Service
public class OrderEventListener {

    @KafkaListener(
        topics = "#{@kafkaTopicProperties.orderCreated}",
        groupId = "billing-service"
    )
    public void handleCreated(OrderCreated event) {
        // Process newly created order.
    }

    @KafkaListener(
        topics = "#{@kafkaTopicProperties.orderCancelled}",
        groupId = "billing-service"
    )
    public void handleCancelled(OrderCancelled event) {
        // Process cancelled order.
    }
}
~~~

If using `@ConfigurationProperties` without registering the bean via `@Component`, enable registration via `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`.

This organization centralizes topic names and reduces the chance of multiple listeners using inconsistent strings for the same business stream.

## 4. Referencing Spring Beans with SpEL

In SpEL, the `@beanName` syntax references a bean in the `ApplicationContext`.

Example:

~~~java
@KafkaListener(
    topics = "#{@kafkaTopicProperties.orderCreated}",
    groupId = "#{@consumerGroupProperties.billing}"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

Suppose the group configuration bean is:

~~~java
@Component("consumerGroupProperties")
@ConfigurationProperties(prefix = "app.kafka.consumer-groups")
public class ConsumerGroupProperties {

    private String billing;

    public String getBilling() {
        return billing;
    }

    public void setBilling(String billing) {
        this.billing = billing;
    }
}
~~~

Configuration:

~~~yaml
app:
  kafka:
    consumer-groups:
      billing: billing-service
~~~

The expression reads the group ID from the bean instead of hard-coding a string in the annotation.

### 4.1. Calling a Bean Method

SpEL can invoke methods to retrieve values:

~~~java
@KafkaListener(
    topics = "#{@topicResolver.resolve('orders')}"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

Resolver bean:

~~~java
@Component
public class TopicResolver {

    public String resolve(String name) {
        return switch (name) {
            case "orders" -> "commerce.order.created";
            case "payments" -> "commerce.payment.authorized";
            default -> throw new IllegalArgumentException(
                "Unknown topic key: " + name
            );
        };
    }
}
~~~

The expression is evaluated to obtain configuration values when the listener endpoint is registered. Therefore, the `resolve` method should be simple, deterministic, and free of side effects.

Do not run database queries, HTTP calls, or expensive work inside an expression used to declare a listener. Load and validate configuration upfront, then let the expression simply read already-prepared values.

### 4.2. Using Conditional Operators

SpEL supports conditional operators to pick a topic based on a configuration property:

~~~java
@KafkaListener(
    topics = "#{@topicSettings.useArchive ? @topicSettings.archiveTopic : @topicSettings.liveTopic}"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

Settings bean can contain:

~~~java
@Component("topicSettings")
@ConfigurationProperties(prefix = "app.kafka.topic-settings")
public class TopicSettings {

    private boolean useArchive;

    public boolean isUseArchive() {
        return useArchive;
    }

    public void setUseArchive(boolean useArchive) {
        this.useArchive = useArchive;
    }

    public String getArchiveTopic() {
        return "commerce.order.archive";
    }

    public String getLiveTopic() {
        return "commerce.order.created";
    }
}
~~~

The value can be bound from configuration:

~~~yaml
app:
  kafka:
    topic-settings:
      use-archive: false
~~~

The expression selects one of the two topics based on configuration. This is useful when the choice is determined at startup time.

Do not overuse complex conditional expressions in annotations. If topic selection logic has many branches or business rules, move that logic into a configuration bean with a clearly named method.

## 5. Using the __listener Pseudo-Bean

Spring Kafka provides a pseudo-bean allowing SpEL to reference the bean containing the `@KafkaListener` method itself. Its default name is `__listener`.

This mechanism is useful when each listener bean has its own configuration, such as a topic injected via constructor.

Example:

~~~java
@Component
public class TenantOrderListener {

    private final String topic;

    public TenantOrderListener(
            @Value("${app.kafka.topics.tenant-orders}") String topic) {
        this.topic = topic;
    }

    public String getTopic() {
        return topic;
    }

    @KafkaListener(
        topics = "#{__listener.topic}",
        groupId = "tenant-order-service"
    )
    public void handle(OrderCreated event) {
        // Process event from configured topic.
    }
}
~~~

Here:

- The constructor receives the topic from `application.yml`.
- Getter `getTopic()` exposes the value to SpEL.
- `#{__listener.topic}` reads the `topic` property on the listener bean.
- The listener keeps the same source code when the topic varies by environment configuration.

This pseudo-bean is especially helpful when there are multiple listener beans of the same class or multiple bean instances with distinct configurations.

### 5.1. Renaming the Bean Reference

The `beanRef` attribute on `@KafkaListener` allows renaming the pseudo-bean reference. If renamed, the expression must use the new name.

Example:

~~~java
@KafkaListener(
    beanRef = "listenerBean",
    topics = "#{listenerBean.topic}"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

The default name `__listener` is usually clear enough. Rename it only for a specific reason or to avoid colliding with another bean name in the expression context.

## 6. Using SpEL for topics

The `topics` attribute accepts one or more topic names. You can use an expression to fetch topic names from a bean.

~~~java
@KafkaListener(
    topics = "#{@kafkaTopicProperties.orderCreated}"
)
public void handleCreated(OrderCreated event) {
    // Process event.
}
~~~

If the listener needs to subscribe to multiple topics, declare multiple values:

~~~java
@KafkaListener(
    topics = {
        "${app.kafka.topics.order-created}",
        "${app.kafka.topics.order-cancelled}"
    },
    groupId = "order-audit-service"
)
public void audit(Object event) {
    // Process subscribed event types.
}
~~~

Both topics above are subscribed by a single listener endpoint. Actual payloads must be deserialized or converted using a configuration compatible with the incoming event types.

If the topics carry different payload types, consider using separate listeners or a common envelope type to avoid unsafe casting.

### 6.1. Do Not Mix topics with topicPattern or topicPartitions

`@KafkaListener` supports three primary subscription styles:

- `topics`: subscribe by topic name.
- `topicPattern`: subscribe by regular expression.
- `topicPartitions`: specify exact topics and partitions.

These are mutually exclusive alternatives within a single endpoint. Do not declare multiple subscription attributes simultaneously on one listener.

## 7. Using SpEL for topicPattern

When you need to subscribe to multiple topics matching a naming rule, use `topicPattern`.

Example configuration:

~~~yaml
app:
  kafka:
    topic-patterns:
      order-events: 'commerce\.order\.(created|cancelled)'
~~~

Configuration bean:

~~~java
@Component("topicPatternProperties")
@ConfigurationProperties(prefix = "app.kafka.topic-patterns")
public class TopicPatternProperties {

    private String orderEvents;

    public String getOrderEvents() {
        return orderEvents;
    }

    public void setOrderEvents(String orderEvents) {
        this.orderEvents = orderEvents;
    }
}
~~~

Listener:

~~~java
@KafkaListener(
    topicPattern = "#{@topicPatternProperties.orderEvents}",
    groupId = "order-audit-service"
)
public void handle(String payload) {
    // Receive records from topics whose names match the pattern.
}
~~~

A pattern is a regular expression, not a concrete topic name. For instance, `commerce\.order\..*` can match topics starting with `commerce.order.`.

When a new topic is created whose name matches the pattern, the consumer can discover it through the Kafka client's metadata refresh and subscription updates.

Test regexes carefully. An overly broad pattern can cause the listener to receive data from topics outside the intended business scope.

## 8. Using SpEL for groupId

`groupId` identifies the consumer group that tracks reading progress and shares partition assignments.

You can retrieve the group ID from a bean:

~~~java
@KafkaListener(
    topics = "#{@kafkaTopicProperties.orderCreated}",
    groupId = "#{@consumerGroupProperties.billing}"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

Or use a property placeholder:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.order-created}",
    groupId = "${app.kafka.consumer-groups.billing}"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

Keep the group ID stable across restarts and deployments if you want to resume from current committed offsets. If an expression accidentally returns a new group ID containing a timestamp or random value, the application may create a brand-new group and start per `auto.offset.reset`.

### 8.1. Distinguishing id and groupId

`@KafkaListener` has an `id` attribute to identify the listener endpoint inside Spring Kafka. `groupId` is the Kafka consumer group identifier.

The two values can interact via the `idIsGroup` setting. When `groupId` is omitted, the listener's `id` may be used as the group ID by default if `idIsGroup` is enabled. Therefore, to control groups explicitly, declare `groupId` directly or configure the default intentionally.

Example:

~~~java
@KafkaListener(
    id = "order-created-listener",
    groupId = "billing-service",
    topics = "${app.kafka.topics.order-created}"
)
public void handle(OrderCreated event) {
    // Process event.
}
~~~

In this example, `id` serves listener endpoint management; `groupId` identifies the consumer group.

## 9. Which Attributes Support SpEL?

Configuration attributes of `@KafkaListener` support placeholder and expression resolution according to Spring Kafka rules. Common cases:

| Attribute | Purpose | Example |
|---|---|---|
| topics | Topic names to subscribe to | `#{@topicProperties.orderCreated}` |
| topicPattern | Topic regex | `#{@topicPatternProperties.orderEvents}` |
| groupId | Consumer group ID | `#{@groupProperties.billing}` |
| id | Listener endpoint ID | `#{@listenerSettings.orderListenerId}` |
| clientIdPrefix | Client ID prefix | `#{@listenerSettings.clientPrefix}` |
| concurrency | Number of child consumer containers | `#{@listenerSettings.concurrency}` |
| autoStartup | Whether to auto-start the container | `#{@listenerSettings.autoStartup}` |

Ensure the expression returns a value convertible to the type required by the attribute. For example, `topics` requires valid topic names; `groupId` requires a stable string; `concurrency` requires a suitable numeric value; `autoStartup` requires a boolean-convertible value.

When using expressions for `concurrency` or `autoStartup`, verify the data types and conversion rules of your Spring Kafka version. For simple config, placeholders from `application.yml` are usually easier to maintain.

## 10. When Is SpEL Evaluated?

SpEL inside `@KafkaListener` is resolved by Spring when listener endpoints are processed and registered during application startup. The resolved values are used to create and configure the listener container.

This has several consequences:

- Expressions are not re-evaluated per record.
- Changing a property or bean value after the container has initialized does not automatically make the listener subscribe to a new topic.
- Changing group ID settings does not automatically migrate a consumer to a new group inside a running container.
- To change subscriptions, manage it through container lifecycle or a controlled subscription-update mechanism.

~~~mermaid
flowchart TD
    A["Spring Application starts"] --> B["Initialize config beans"]
    B --> C["Process @KafkaListener"]
    C --> D["Resolve placeholders and SpEL"]
    D --> E["Register listener endpoint"]
    E --> F["Create listener container"]
    F --> G["Consumer subscribes and joins group"]
    G --> H["Poll and invoke listener"]
~~~

Because expressions are evaluated during endpoint initialization, referenced beans must be ready in the `ApplicationContext`. Avoid circular dependencies between listener beans and topic-configuration beans.

## 11. Combining SpEL with Multi-Environment Configuration

An application can use the same listener while consuming different topics based on profiles or environment variables.

`application-dev.yml`:

~~~yaml
app:
  kafka:
    topics:
      order-created: dev.commerce.order.created
    consumer-groups:
      billing: billing-service-dev
~~~

`application-prod.yml`:

~~~yaml
app:
  kafka:
    topics:
      order-created: commerce.order.created
    consumer-groups:
      billing: billing-service
~~~

Listener:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.order-created}",
    groupId = "${app.kafka.consumer-groups.billing}"
)
public void handle(OrderCreated event) {
    // Processing logic is identical across all environments.
}
~~~

Spring loads the property sources matching the active profile. The listener requires no source-code changes between development and production.

Note that different group IDs across environments produce independent reading progress. This is usually intentional so development workloads do not share offsets with production.

## 12. Validating Expression Values Before Creating Listeners

An expression can be syntactically valid yet return an invalid value for Kafka.

Examples of issues:

- The referenced bean does not exist.
- The topic property is null or blank.
- The expression returns the wrong data type.
- The topic name violates Kafka naming rules.
- `groupId` changes unexpectedly across deployments.
- `topicPattern` is not a valid regex.
- The configuration bean is not registered in the `ApplicationContext`.

Validate configuration at application startup:

~~~java
@Component
public class KafkaTopicPropertiesValidator {

    private final KafkaTopicProperties properties;

    public KafkaTopicPropertiesValidator(
            KafkaTopicProperties properties) {
        this.properties = properties;
    }

    @PostConstruct
    public void validate() {
        if (properties.getOrderCreated() == null
                || properties.getOrderCreated().isBlank()) {
            throw new IllegalStateException(
                "Kafka topic orderCreated must not be blank"
            );
        }
    }
}
~~~

Validation surfaces configuration errors early with clear messages, rather than waiting until consumers subscribe or receive records.

If stricter topic-name checks are needed, use a dedicated validator to verify characters, length, and organizational conventions.

## 13. Common Errors When Using SpEL

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Could not resolve placeholder | Missing property or wrong key name | Check `application.yml`, active profile, and environment variables |
| Bean reference does not exist | Wrong bean name or bean not registered | Check names in `@Component`/`@Bean` and component scanning |
| SpEL parse exception | Syntax error, unclosed quotes, or mismatched brackets | Check expression syntax and character escaping |
| Expression returns null | Property bean not bound or value unconfigured | Validate bean before listener creation |
| Listener subscribes to wrong topic | Referenced wrong property or expression picked wrong branch | Log resolved config values and inspect active profile |
| Consumer group changes after deploy | `groupId` expression depends on changing value | Use a stable group ID |
| Topic pattern matches too many topics | Overly broad regex | Restrict prefix and verify regex |
| Listener does not change topic after config edit | Expression was evaluated at endpoint registration | Recreate container or apply subscription update workflow |
| Concurrency type conversion error | Expression returns a string not convertible to a number | Verify value and return type |
| Topic not found on startup | Topic does not exist or broker disables auto-create | Check topic existence and topic creation policy |

## 14. Testing @KafkaListener with SpEL

Tests should verify both resolved configuration values and actual record-consumption behavior.

Suggested steps:

1. Initialize the Spring context with dedicated test properties.
2. Register topic and consumer group configuration beans.
3. Register the SpEL-configured listener.
4. Start test Kafka using EmbeddedKafka or Testcontainers.
5. Send a record to the topic the expression is expected to return.
6. Confirm the listener receives the expected payload.
7. Send a record to another topic to confirm the listener does not consume it erroneously.
8. If using `topicPattern`, create one matching topic and one non-matching topic.
9. Confirm the listener's group ID matches configuration.

An integration test example can use EmbeddedKafka:

~~~java
@SpringBootTest(properties = {
    "app.kafka.topics.order-created=test.commerce.order.created",
    "app.kafka.consumer-groups.billing=test-billing-group"
})
@EmbeddedKafka(
    partitions = 1,
    topics = "test.commerce.order.created"
)
class OrderEventListenerTest {

    @Autowired
    private KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @Test
    void shouldConsumeFromTopicResolvedBySpel() throws Exception {
        OrderCreated event = new OrderCreated(
            "order-10001",
            "customer-20001",
            1250000
        );

        kafkaTemplate.send(
            "test.commerce.order.created",
            event.orderId(),
            event
        ).get(10, TimeUnit.SECONDS);

        // Confirm listener processed event using a latch or test probe.
    }
}
~~~

Assertions should use `CountDownLatch`, Awaitility, or a test probe to wait for asynchronous listener processing. Do not use a fixed `Thread.sleep` as proof that the listener received a record.

When testing group ID, inspect the registered container in `KafkaListenerEndpointRegistry` or inspect the consumer group on the test broker.

## 15. Principles for Maintainable Expressions

- Prefer placeholders when simply reading a value from configuration.
- Use SpEL when referencing beans or computing simple values.
- Give configuration beans clear, stable names.
- Keep expressions short and avoid deeply nested conditional branches.
- Avoid I/O or side effects inside expressions.
- Never feed untrusted input into expressions for evaluation.
- Validate topics, group IDs, and patterns before creating listeners.
- Keep group IDs stable so new consumer groups are not created accidentally.
- Never confuse listener `id` with Kafka `groupId`.
- Test resolved values and real subscription behavior.

## 16. Pre-Production Checklist for SpEL-Configured Listeners

- [ ] Chosen placeholder vs. SpEL appropriately for the need?
- [ ] Referenced bean is registered in the `ApplicationContext`?
- [ ] Bean name in the expression is exact?
- [ ] Expression returns a type compatible with the annotation attribute?
- [ ] Topic is non-null, non-empty, and follows Kafka conventions?
- [ ] `topicPattern` is an appropriately scoped regex?
- [ ] Only one of `topics`, `topicPattern`, or `topicPartitions` is used?
- [ ] `groupId` remains stable across restarts and deployments?
- [ ] Listener `id` is clearly distinguished from `groupId`?
- [ ] Understood that expressions are evaluated at endpoint registration time?
- [ ] Not expecting bean property changes to automatically update active subscriptions?
- [ ] No I/O or side effects inside expressions?
- [ ] Validation and clear configuration error messages exist?
- [ ] Tested with real topics and the expected group ID?

## Conclusion

SpEL in `@KafkaListener` lets you pull listener configuration from Spring beans and express simple choices via expressions. Property placeholders `${...}` suit direct config values; SpEL `#{...}` fits bean references, getter/method calls, or conditional selections. The `__listener` pseudo-bean further enables a listener to reference configuration on its own enclosing bean.

Expressions are resolved during listener endpoint registration, not on every record. Therefore, configuration beans must be ready at startup, topics and group IDs must be validated upfront, and configuration changes after container startup require a controlled update procedure. Keeping expressions concise, expressive, and well-tested keeps `@KafkaListener` flexible across environments while keeping consumer groups and subscriptions stable.
