# Selectors and Broker-Side Filtering in JMS

## 1. What Problem Do Message Selectors Solve?

In a JMS system, a destination can carry many kinds of messages. For example, the queue orders.queue might receive orders from multiple countries, multiple priority levels, and multiple business types. A consumer that only processes orders shipped to the EU can use a message selector to ask the provider to deliver only matching messages.

A **message selector** is a String conditional expression attached to a consumer or topic subscription. The Jakarta Messaging provider evaluates the expression against headers and message properties before delivering the message. The consumer only receives messages for which the expression evaluates to TRUE.

The goal is to offload filtering from application code to the messaging provider:

- Reduce irrelevant messages transferred to the application.
- Avoid having every listener receive all messages only to inspect and discard them.
- Allow multiple consumers to read from the same destination while receiving distinct subsets of messages.
- For topics, allow each subscription to receive only the subset of events that subscriber cares about.

A selector is not a full SQL query, does not read body content, and does not replace destination access authorization.

## 2. What Data Can a Selector Read?

A selector only references:

1. Certain JMS header fields permitted by the specification.
2. Message properties set by the application or provider.

A selector **cannot access the message body**. If you need to filter on information inside a JSON, XML, or Java object payload, promote the field to filter on into a message property before sending.

For example, the producer sends a TextMessage whose body is an order ID and whose properties are set as follows:

~~~java
message.setStringProperty("region", "EU");
message.setIntProperty("priority", 7);
message.setStringProperty("orderType", "EXPRESS");
~~~

The consumer can use the selector:

~~~sql
region = 'EU' AND priority >= 5 AND orderType = 'EXPRESS'
~~~

The provider can evaluate the selector without invoking the listener to read the body. This is why routing properties should be designed right when the producer constructs the message.

### 2.1. JMS headers permitted for reference

Jakarta Messaging restricts the header fields that may appear directly in a selector:

| Header | Common type/meaning |
| --- | --- |
| JMSDeliveryMode | Persistent delivery mode; in selectors use the values PERSISTENT or NON_PERSISTENT |
| JMSPriority | Numeric priority level |
| JMSMessageID | Message identifier |
| JMSTimestamp | Send timestamp, in milliseconds |
| JMSCorrelationID | Request/reply or business flow correlation identifier |
| JMSType | Application-defined message type |

Not every JMS header can be used in a selector. For example, do not assume you can reference JMSDestination, JMSReplyTo, or JMSRedelivered as a regular selector identifier.

Properties starting with JMSX are defined by Jakarta Messaging. Properties starting with JMS_ are reserved for providers. Application properties should use custom names not starting with JMS, such as region, orderType, or tenantCode.

## 3. Selector Syntax: A Subset of SQL-92

A selector is a String expression with syntax based on a subset of SQL-92 conditional expressions. It is not a SQL query: there is no SELECT, FROM, JOIN, subquery, or access to fields inside the body.

### 3.1. Comparison and logical operators

Common comparison operators:

| Operator | Meaning | Example |
| --- | --- | --- |
| = | Equal | region = 'EU' |
| <> | Not equal | status <> 'CANCELLED' |
| >, >= | Greater than, greater than or equal | priority >= 5 |
| <, <= | Less than, less than or equal | amount < 1000 |

Logical operators are NOT, AND, and OR. Precedence follows NOT first, then AND, then OR. Use parentheses to keep expressions clear:

~~~sql
region = 'EU' AND (priority >= 8 OR orderType = 'EXPRESS')
~~~

Keywords and operators are case-insensitive, whereas identifier names are case-sensitive. Thus region and Region are two different property names.

### 3.2. Literals and data types

Selectors support:

- String literals enclosed in single quotes, e.g., 'EU'.
- Exact numeric literals (integers), e.g., 7 or -3.
- Approximate numeric literals, e.g., 10.5 or 7E3.
- Booleans TRUE and FALSE.

If a string literal needs to contain a single quote, write that single quote as two consecutive single quotes:

~~~sql
customerName = 'O''Reilly'
~~~

Properties must be set with a data type compatible with the comparison. Selectors do not automatically coerce strings into numbers the way some JMS getter APIs might.

For example, if the producer uses:

~~~java
message.setStringProperty("priority", "7");
~~~

The following selector is not a valid comparison for the intended data type:

~~~sql
priority >= 5
~~~

The priority property is a String, while the literal 5 is numeric. Use setIntProperty("priority", 7) if you want numeric comparison.

Only compatible types can be compared. String and Boolean only support equality or inequality; integers and approximate numbers can be compared according to Java numeric promotion rules.

### 3.3. BETWEEN and IN

BETWEEN tests whether a numeric value falls within a range, inclusive of both endpoints:

~~~sql
priority BETWEEN 3 AND 7
~~~

The expression above is equivalent to:

~~~sql
priority >= 3 AND priority <= 7
~~~

IN tests whether a String property is in a list of values:

~~~sql
region IN ('EU', 'UK', 'SG')
~~~

You can use NOT BETWEEN and NOT IN to negate conditions. IN/NOT IN in selectors applies to String or NULL identifiers, not arbitrary numeric list syntax.

### 3.4. LIKE and ESCAPE

LIKE performs pattern matching on strings:

- % matches zero or more characters.
- _ matches any single character.
- ESCAPE declares a character used to escape the special meaning of % or _.

Example:

~~~sql
customerCode LIKE 'VIP-%'
~~~

Selects customer codes starting with VIP-.

~~~sql
phone LIKE '84_123%'
~~~

Selects phone numbers starting with 84, followed by one character, then 123 and any remaining characters.

If you need to match a literal % or _, use ESCAPE with an appropriate escape character. Do not assume LIKE supports regex; it only supports the two wildcards % and _ per specification.

### 3.5. IS NULL and IS NOT NULL

If a property does not exist on a message, its value is treated as NULL when the selector is evaluated:

~~~sql
campaignCode IS NULL
~~~

Selects messages without campaignCode or where the header/property value evaluates to NULL.

~~~sql
campaignCode IS NOT NULL
~~~

Selects only messages where campaignCode is non-NULL.

Do not use equality against NULL:

~~~sql
campaignCode = NULL
~~~

Use IS NULL or IS NOT NULL instead.

## 4. Three-Valued Logic: TRUE, FALSE, and UNKNOWN

Selectors follow SQL NULL rules. When a property does not exist, a comparison against that property typically yields UNKNOWN rather than TRUE or FALSE.

For example, for a message without a region property:

~~~sql
region = 'EU'
~~~

The expression evaluates to UNKNOWN, so the message does not match the selector. Only a TRUE result counts as a match; both FALSE and UNKNOWN are not delivered.

AND, OR, and NOT also apply three-valued logic:

| A | B | A AND B | A OR B |
| --- | --- | --- | --- |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

NOT UNKNOWN remains UNKNOWN.

This matters when writing negated selectors. For example:

~~~sql
NOT (region = 'EU')
~~~

Does not automatically select messages missing region, because the inner expression is UNKNOWN and NOT UNKNOWN is still UNKNOWN. If you want to receive all messages outside the EU, including messages without region, write it explicitly:

~~~sql
region <> 'EU' OR region IS NULL
~~~

## 5. Where Is Filtering Applied?

A selector is created together with a consumer or subscription. The provider evaluates the selector before delivering a message to the consumer. What happens to non-matching messages depends on whether the destination is a queue or a topic.

### 5.1. Queue: competing consumers on the same queue

In the point-to-point model, multiple consumers can read from the same queue, yet each message is delivered to only one consumer.

If a consumer has a selector, only matching messages are delivered to that consumer. Non-matching messages remain in the queue or may be delivered to another consumer with a matching selector.

For example, with two consumers:

| Consumer | Selector |
| --- | --- |
| Consumer EU | region = 'EU' |
| Consumer US | region = 'US' |

Messages with region = 'EU' only match Consumer EU. If no consumer matches, messages can stay in the queue and build up a backlog.

Selectors do not turn a queue into pub/sub. A message in a queue is not copied to all consumers; it is delivered to one matching consumer.

### 5.2. Topic: selectors belong to each subscription

In the publish/subscribe model, each topic subscription receives its own copy of a message. If a subscription has a selector, only matching messages are added to that subscription.

For example, two subscribers registered on the order-events topic:

| Subscription | Selector | Messages received |
| --- | --- | --- |
| EU reports | region = 'EU' | EU orders |
| High priority alerts | priority >= 8 | Orders with priority 8 or higher |

A single message can match multiple subscriptions and be delivered as multiple copies. Acknowledging in one subscription does not acknowledge copies in other subscriptions.

### 5.3. Durable topic subscriptions

A durable subscription is retained by the provider even when consumers are temporarily inactive. The provider keeps holding messages matching the subscription until they are received and acknowledged or expire.

The selector is part of the subscription configuration:

- While a durable subscription has an active consumer, you cannot open another consumer with the same identity but a different selector; the provider can throw JMSException or JMSRuntimeException.
- When a durable subscription has no active consumer, recreating the subscription with the same identity but a different selector is equivalent to deleting the old subscription and creating a new one.
- When changing the selector, pending messages in the old subscription may be discarded along with the old subscription. Evaluate the impact before changing it.

Therefore, a topic selector should be treated as part of the subscription contract, not a temporary filter that can be changed arbitrarily without affecting state.

## 6. Setting Selectors with the Jakarta Messaging API

In the simplified API, the selector is passed when creating the consumer:

~~~java
JMSContext context = connectionFactory.createContext();
Queue queue = context.createQueue("orders.queue");

JMSConsumer consumer = context.createConsumer(
    queue,
    "region = 'EU' AND priority >= 5"
);
~~~

The consumer only receives messages matching both conditions. You can use the equivalent classic API via Session.createConsumer(destination, selector).

The selector is syntax-checked when the consumer is created. If the expression has invalid syntax, the provider throws InvalidSelectorException in the classic API or the corresponding runtime exception in the simplified API.

For example, the producer must set properties before sending:

~~~java
context.createProducer()
    .setProperty("region", "EU")
    .setProperty("priority", 7)
    .send(queue, "order-42");
~~~

Here region is a String and priority is an integer. The message body is order-42; the selector only reads the two properties, not the body string.

## 7. Using Selectors in Spring JMS

Spring JMS provides two common ways to configure selectors:

1. The selector attribute on the @JmsListener annotation.
2. The setMessageSelector method on a listener container, such as DefaultMessageListenerContainer.

Spring passes the selector to the JMS consumer created by the container. Filtering is still performed by the Jakarta Messaging provider under the JMS contract.

### 7.1. @JmsListener(selector = ...)

Example listener receiving only EU orders with priority 5 or higher:

~~~java
@Component
public class EuOrderListener {

    @JmsListener(
        destination = "orders.queue",
        selector = "region = 'EU' AND priority >= 5"
    )
    public void receive(String orderId) {
        System.out.println("Accepted order: " + orderId);
    }
}
~~~

Annotation-driven listeners must be enabled with @EnableJms and a default JmsListenerContainerFactory must be configured, or containerFactory specified on the annotation.

The selector here is a JMS expression, not a Java expression and not SpEL. Do not write conditions referencing method parameters or accessing payload fields.

### 7.2. Sending properties with JmsTemplate

The producer uses MessagePostProcessor to add properties after Spring converts the payload to a JMS Message:

~~~java
@Component
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String orderId, String region, int priority) {
        jmsTemplate.convertAndSend(
            "orders.queue",
            orderId,
            message -> {
                message.setStringProperty("region", region);
                message.setIntProperty("priority", priority);
                return message;
            }
        );
    }
}
~~~

With the producer calling:

~~~java
publisher.publish("order-42", "EU", 7);
publisher.publish("order-43", "US", 9);
publisher.publish("order-44", "EU", 2);
~~~

The EU listener in the previous section only receives order-42. The remaining two messages do not match the selector.

### 7.3. Configuring a listener container in Java

If you want to configure a selector on the container rather than on the annotation, you can use AbstractMessageListenerContainer.setMessageSelector. Example:

~~~java
@Bean
public DefaultMessageListenerContainer euOrdersContainer(
        ConnectionFactory connectionFactory,
        Destination ordersQueue,
        MessageListener euOrderMessageListener) {

    DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

    container.setConnectionFactory(connectionFactory);
    container.setDestination(ordersQueue);
    container.setMessageListener(euOrderMessageListener);
    container.setMessageSelector("region = 'EU' AND priority >= 5");
    return container;
}
~~~

The selector in the example only applies to the consumer created by the euOrdersContainer container. For @JmsListener endpoints, place the selector on the annotation; the shared factory is used to configure container properties such as ConnectionFactory and concurrency.

The example above assumes ConnectionFactory is already configured by the JMS provider or application infrastructure. JmsTemplate and the listener container must use the right destination domain. For queues, pubSubDomain defaults to false; if switching to topics, configure both template and listener container for topics.

## 8. Spring JMS Integration Example: Required Components

A real application needs the following components:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("1-4");
        return factory;
    }
}
~~~

ConnectionFactory is the adapter connecting to a specific broker such as ActiveMQ Artemis or another JMS provider. You need to configure endpoints, credentials, destinations, and the provider client dependencies in the application.

This example illustrates Spring JMS configuration; to run in practice, there must be a running broker and a ConnectionFactory bean supplied by the provider. There is no fixed stdout across all providers because asynchronous delivery, concurrency, acknowledgement, and scheduling are coordinated by the container/broker.

## 9. Selectors and Performance

Selectors can reduce the number of messages delivered to the application, though actual performance depends on the provider, destination configuration, and number of consumers/subscriptions.

Some principles:

- Put only properties genuinely needed for routing into selectors.
- Set properties right when the producer creates the message; avoid relying on consumers reading the body to classify messages.
- Use consistent data types between producers and selectors.
- Keep expressions simple; avoid overly complex branching logic that is hard to test.
- Test selectors against the actual JMS provider in production; internal optimization and property indexing are not standardized by JMS.
- Monitor queue depth, unmatched message counts, delivery rates, latency, and redelivery counts.
- If no consumer matches a queue's messages via selectors, messages can sit in the queue for a long time. Alert on backlog and provide a fallback consumer if business requirements demand it.

Selectors help the provider filter before delivering messages; they do not themselves guarantee high throughput or message durability. Persistence, acknowledgement, transactions, retries, and dead-letter queues still require separate configuration.

## 10. Limitations and Security Considerations

A selector is purely a message-delivery selection mechanism. Do not use it as a security boundary.

- Destination read permissions must be configured on the broker/provider.
- Clients can create their own consumer with a different selector if they have access to the destination.
- Do not put sensitive data into properties thinking a selector will hide it from other consumers.
- Do not allow end users to pass arbitrary selector strings if the application must restrict data scope.
- Validate properties and payloads on the server; selectors do not replace business validation.
- Use authenticated tenant identity to determine destination and subscription access permissions.

Selectors also do not replace dead-letter queues, retries, or transactions. A message excluded from a consumer by a selector does not mean the message has been acknowledged or processed successfully.

## 11. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Listener does not receive messages | Property missing or condition evaluates to FALSE/UNKNOWN | Inspect actual properties set by the producer |
| Numeric comparison does not match | Property was set as a String | Use setIntProperty/setLongProperty with the right type |
| Selector cannot read fields in JSON body | Selectors do not support body fields | Promote the field to filter on into a JMS property |
| InvalidSelectorException | Syntax error, wrong operator type, or missing quotes | Check selector syntax and recreate consumer |
| Queue consumer keeps a backlog | No consumer has a matching selector | Inspect all consumers' selectors and add a fallback handler |
| Topic subscriber misses events | Subscription selector excludes those events | Check the selector bound to the subscription, especially for durable subscriptions |
| Changing durable subscription selector fails | Old subscription has an active consumer or incompatible identity | Stop consumers, manage subscription lifecycle, and plan changes carefully |
| Selector LIKE does not behave like regex | LIKE only supports % and _ | Use proper JMS wildcards or filter in application code |
| Property name case mismatch | Identifiers are case-sensitive | Standardize property names between producer and consumer |
| Using selectors for tenant isolation | Another consumer can still create its own selector if allowed to read the destination | Enforce authorization at the broker and authenticate in the application |

## 12. Selector Design Checklist

- [ ] Determine whether the selector applies to a queue consumer or a topic subscription.
- [ ] Identify the exact properties needed for filtering and set them before sending.
- [ ] Choose the right String, numeric, or Boolean type for each property.
- [ ] Do not reference the message body in selectors.
- [ ] Verify permitted JMS header names; prefer application properties for business conditions.
- [ ] Use IS NULL/IS NOT NULL when handling missing properties.
- [ ] Use parentheses to keep AND/OR expressions clear.
- [ ] Test FALSE and UNKNOWN selector cases.
- [ ] For durable subscriptions, manage selectors as part of long-lived subscription configuration.
- [ ] Monitor backlog and messages not selected by any consumer.
- [ ] Use broker authorization and application authorization for security; do not rely on selectors.

## 13. References

- [Jakarta Messaging 3.1 Specification — Message Selector](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#message-selector)
- [Jakarta Messaging 3.1 Specification — Queue Semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#queue-semantics)
- [Jakarta Messaging 3.1 Specification — Topic Semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#topic-semantics)
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework API — JmsListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [Spring Framework API — AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework API — JmsTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
