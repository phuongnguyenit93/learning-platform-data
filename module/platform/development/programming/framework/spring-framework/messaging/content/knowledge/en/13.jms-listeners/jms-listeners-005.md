# destination, selector, subscription, concurrency, and containerFactory in a Spring JMS Listener

## 1. The Role of the Attributes in @JmsListener

Spring JMS lets a Java method receive messages through the `@JmsListener` annotation. The annotation describes where to receive messages and some consumer options; Spring creates a listener endpoint and then uses a listener container to manage the connection, session, consumer, and lifecycle.

Five attributes to understand together:

- **destination:** the name of the queue or topic from which the listener receives messages.
- **selector:** an expression that filters messages by JMS headers and properties.
- **subscription:** the subscription name, typically used to identify a durable topic subscription.
- **concurrency:** the number of consumers, or the range of consumers, that the listener container is allowed to run.
- **containerFactory:** the name of the factory bean that creates the listener container with the corresponding connection and operational configuration.

A listener typically looks like this:

~~~java
@JmsListener(
        destination = "orders.queue",
        selector = "priority >= 5",
        concurrency = "2-6",
        containerFactory = "ordersQueueFactory")
public void receive(OrderCommand command) {
    // Process the message.
}
~~~

These attributes belong to Spring JMS. They are not attributes of a Spring Messaging channel or STOMP. Spring JMS uses a JMS provider and a ConnectionFactory to connect to the broker.

After this lesson, you should be able to:

- Choose the correct queue or topic for the destination.
- Write a selector using JMS syntax and distinguish a selector from a Java condition.
- Configure a durable subscription and a stable subscription name.
- Choose concurrency suited to the queue, topic, and subscription type.
- Create multiple listener container factories for different groups of listeners.
- Understand how Spring creates and manages listener containers.
- Test routing, filtering, subscription identity, and consumer load.

## 2. destination: Where Does the Listener Receive Messages?

### 2.1 Queue and Topic

A destination is a queue or topic managed by the JMS provider. The same destination name can be resolved to a queue or a topic depending on the resolver and the listener container configuration.

With a common Spring JMS configuration:

- `pubSubDomain = false`: uses the queue domain.
- `pubSubDomain = true`: uses the topic domain.

A queue is usually suitable for work where one consumer in a group handles each message. A topic is suitable for a publication that multiple independent subscriptions can each receive a copy of.

A destination name is not the broker URL, the clientID, or the subscription name. The broker URL determines where to connect; the destination determines where to send/receive inside the broker.

### 2.2 Destination as a String

`@JmsListener(destination = "orders.queue")` takes the destination name as a string. The listener container uses a `DestinationResolver` to resolve that name into a JMS Destination.

Spring JMS typically uses the default `DynamicDestinationResolver`. This resolver creates or looks up the queue/topic according to the container's domain mode. If the application uses JNDI or needs its own resolution rules, you can configure the corresponding resolver on the listener container factory.

The destination name can be externalized through an application property. When using a placeholder in the annotation, make sure the property is declared for each environment and is resolved by Spring when processing the annotation. Queue/topic names should be managed consistently across the publisher, the listener, and broker provisioning.

### 2.3 The Destination Must Exist and Be Accessible

Some brokers auto-create a destination when the application references a name that does not yet exist; other brokers require an administrator to create it beforehand. Do not assume auto-create behavior is the same across providers.

The listener needs permission to consume on the destination. The publisher needs permission to send. A successful connection does not mean the application has permission to read every queue or subscribe to every topic.

## 3. selector: Filtering Messages at the Broker

### 3.1 How Does a Selector Work?

The `selector` of `@JmsListener` is a JMS message selector. It is an expression in JMS selector syntax, based on JMS-defined headers and application properties of supported types.

Example:

~~~java
@JmsListener(
        destination = "orders.queue",
        selector = "priority >= 5 AND eventType = 'OrderCreated'")
public void receive(OrderCommand command) {
    // Only receives messages that satisfy the selector.
}
~~~

The broker only delivers to the consumer messages for which the selector evaluates to TRUE. Messages that do not satisfy the condition may remain in the queue or be delivered to another consumer with a matching selector, depending on the topology and provider.

A selector is not a Java expression, SpEL, or a SQL database query. Do not call methods, access DTO fields, or use lambda syntax in a selector.

### 3.2 A Selector Reads JMS Headers and Properties

Some JMS headers commonly usable in a selector include:

- `JMSPriority`: priority level.
- `JMSMessageID`: message identifier.
- `JMSCorrelationID`: correlation ID.
- `JMSType`: message type.
- `JMSDeliveryMode`: delivery mode per JMS convention.
- `JMSRedelivered`: redelivery status.

In addition, a selector can read JMS properties set by the publisher, for example `eventType`, `tenantCode`, or `priority` if those values are set as valid properties.

**A selector does not read the message body directly.** If you want to filter by a business attribute, the publisher must set that value as an appropriate JMS property. For example, a `priority` field inside the JSON body does not automatically become the JMS property `priority`.

### 3.3 Commonly Used Selector Syntax

A JMS selector supports a limited set of SQL-style expressions, typically including:

| Syntax | Example |
|---|---|
| Comparison | `priority >= 5` |
| AND / OR / NOT | `eventType = 'Created' AND priority > 2` |
| IS NULL | `region IS NULL` |
| IN | `eventType IN ('Created', 'Updated')` |
| BETWEEN | `priority BETWEEN 3 AND 8` |
| LIKE | `tenantCode LIKE 'vn-%'` |

String literals use single quotes. Property names and data types must conform to the JMS selector rules. A selector can evaluate to UNKNOWN when a property does not exist or its value is null; only messages with a TRUE result are selected.

Check the syntax and the support of the target broker. A complex selector can increase the filtering cost at the broker.

### 3.4 Setting Properties for the Selector to Use

A publisher can set JMS properties using a `MessagePostProcessor`:

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        orderCommand,
        message -> {
            message.setStringProperty("eventType", "OrderCreated");
            message.setIntProperty("priority", 7);
            return message;
        }
);
~~~

A listener using the selector:

~~~java
@JmsListener(
        destination = "orders.queue",
        selector = "eventType = 'OrderCreated' AND priority >= 5")
public void receive(OrderCommand command) {
    // Process the selected order.
}
~~~

The body still contains the payload according to the configured converter. The two properties are set separately so the broker can evaluate the selector before delivering the message.

Do not put sensitive data such as tokens or passwords into JMS properties. Properties can appear in broker administration tools, logs, or monitoring systems.

## 4. subscription: The Identity of a Topic Subscriber

### 4.1 Subscription Name Differs from Destination

When a listener uses a topic, the destination determines the topic being subscribed to. With a durable subscription, the subscription name identifies the receiving stream that the broker must maintain across the consumer's offline periods.

Example:

~~~java
@JmsListener(
        destination = "orders.events",
        subscription = "billing-projection-v1",
        containerFactory = "durableTopicFactory")
public void receive(OrderEvent event) {
    // Update the projection.
}
~~~

Here:

- `orders.events` is the topic.
- `billing-projection-v1` is the durable subscription name.
- `durableTopicFactory` must configure the topic domain and the durable subscription.

The `subscription` attribute does not by itself make the listener durable. The listener container factory must enable the durable subscription and configure the required identity.

### 4.2 Configuring a Durable Subscription

For an unshared durable subscription in classic JMS, the container needs a stable clientID along with a stable subscription name. The clientID belongs to the JMS connection; the subscription name belongs to the durable topic subscription.

Example factory:

~~~java
@Bean
public DefaultJmsListenerContainerFactory durableTopicFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("billing-projection-client");
    factory.setConcurrency("1");

    return factory;
}
~~~

A listener using the subscription name:

~~~java
@JmsListener(
        destination = "orders.events",
        subscription = "billing-projection-v1",
        containerFactory = "durableTopicFactory")
public void receive(OrderEvent event) {
    // Process the publication.
}
~~~

The factory and the listener must use the same topic, client identity, and subscription name across restarts. If you change the subscription name, the broker may treat it as a new subscription and leave the old subscription with its backlog.

### 4.3 Durable and Non-Durable

- **Non-durable subscription:** exists for the time the subscriber is active; publications made while the subscriber is offline are typically not retained for that subscriber.
- **Durable subscription:** the broker retains the subscription state and can store suitable messages while the consumer is offline, according to the provider's persistence, expiration, quota, and policy.

Stopping or closing the listener container does not mean deleting the durable subscription. Deleting a subscription is a deliberate unsubscribe operation; do not perform it on every shutdown if you want to keep the backlog.

### 4.4 Shared Durable Subscription

JMS 2.0 supports shared durable subscriptions so that multiple consumers can take part in one subscription. In that case, the consumers compete to receive messages within the same subscription; each message is delivered to one suitable consumer in the group.

The ability to configure a shared subscription depends on the Spring version, the JMS provider, and the broker. Spring JMS supports configuring shared subscriptions on the corresponding versions of the listener container. Verify APIs such as `setSubscriptionShared(true)` and the semantics of the provider you use before increasing concurrency.

Distinguish the two models:

- Multiple separate durable subscriptions: each subscription can receive a copy of the publication.
- Multiple consumers on the same shared durable subscription: the consumers divide the messages within the same subscription.

Do not use multiple separate subscriptions expecting to achieve competing consumers.

## 5. concurrency: The Number of Concurrent Consumers

### 5.1 Configuring at the Factory or the Annotation

`concurrency` specifies the number of consumers the listener container can run. With `DefaultMessageListenerContainer`, you can use a fixed number or a min-max range.

Example:

~~~java
factory.setConcurrency("2-8");
~~~

Or override at the listener:

~~~java
@JmsListener(
        destination = "orders.queue",
        concurrency = "3-6",
        containerFactory = "ordersQueueFactory")
public void receive(OrderCommand command) {
    // Process the message.
}
~~~

Concurrency on the annotation lets a specific listener override the factory's concurrency configuration. If it is not set on the annotation, the container uses the value from the factory or the implementation's default.

### 5.2 Queue Concurrency

With a queue, multiple consumers typically act as competing consumers. The broker distributes messages to the consumers according to the provider's mechanism, acknowledgement, prefetch, and load state.

Increasing concurrency can increase throughput when handlers process independently, but it can also:

- Increase the number of connections/sessions or the broker resources needed.
- Increase the load on the database and downstream services.
- Change the order in which messages complete.
- Increase the number of messages that have been delivered but not yet acknowledged.
- Expose race conditions if the handler uses shared mutable state.

Choose concurrency according to downstream processing capacity and measure in practice. Do not assume that more consumers always make the system faster.

### 5.3 Topic Concurrency

With a non-durable topic, each consumer is typically a separate subscription. Increasing concurrency can cause multiple consumers to receive the same publication, leading to the same event being processed multiple times within one application.

With an unshared durable subscription, the provider typically allows only one active consumer on the subscription at a time. Configuring concurrency greater than one can cause conflicts or consumer-initialization errors.

If you need to scale a durable subscription, use a shared durable subscription when the JMS provider and the Spring listener container support it. Check ordering, selector, acknowledgement, and load distribution on the target broker.

### 5.4 Choosing the Min-Max Range

The range `2-8` lets the container start with the minimum number of consumers and grow when needed, according to the listener container's capability. Concurrency can be adjusted through configuration suited to the workload.

Start low, measure throughput, p95/p99 latency, queue depth, the number of sessions, and database load, and then increase gradually. For listeners that must preserve processing order, evaluate carefully before increasing the number of consumers.

## 6. containerFactory: Choosing How the Listener Container Is Created

### 6.1 The Role of the Factory

`containerFactory` is the name of the bean that creates the listener container for a method annotated with `@JmsListener`.

A factory typically configures:

- ConnectionFactory.
- Queue or topic domain.
- Durable/shared subscription and clientID.
- Concurrency.
- Transaction and acknowledgement.
- MessageConverter.
- ErrorHandler.
- DestinationResolver.
- Recovery interval and other container settings.

An application can have multiple factories for different kinds of listeners. For example, a work-processing queue has high concurrency; a durable topic projection uses a single consumer; an audit listener uses its own converter and transaction policy.

If `containerFactory` is not specified, Spring looks for the default factory by the name `jmsListenerContainerFactory`. A bean with this default name is needed if the application does not provide a different factory through the configuration mechanism in use.

### 6.2 Creating a Queue Factory

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory ordersQueueFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setConcurrency("2-8");
        factory.setSessionTransacted(true);

        return factory;
    }
}
~~~

This factory creates a listener container in the queue domain. Session transactions let the container commit or roll back the receive operation according to the transaction configuration. A JMS transaction does not by itself make the database and JMS commit atomically unless there is an appropriate transaction coordination mechanism.

### 6.3 Creating a Topic Factory

~~~java
@Bean
public DefaultJmsListenerContainerFactory eventsTopicFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setConcurrency("1");

    return factory;
}
~~~

This factory uses the topic domain and a single consumer. If you need a durable subscription, add the durable configuration and client identity according to the subscription type. For a shared durable subscription, enable the corresponding shared option only when the provider and the Spring version support it.

### 6.4 Using Multiple Factories in the Same Application

~~~java
@Component
public class OrderListeners {

    @JmsListener(
            destination = "orders.queue",
            selector = "priority >= 5",
            concurrency = "3-6",
            containerFactory = "ordersQueueFactory")
    public void processPriorityOrder(OrderCommand command) {
        // Process work from the queue.
    }

    @JmsListener(
            destination = "orders.events",
            subscription = "billing-projection-v1",
            containerFactory = "durableTopicFactory")
    public void updateProjection(OrderEvent event) {
        // Update the read model from the topic.
    }
}
~~~

In the example, `ordersQueueFactory` and `durableTopicFactory` are two separately configured factory beans. The durableTopicFactory bean needs to be declared as in the durable subscription example in the earlier section.

Splitting the factories lets each group of listeners have suitable domain, transaction, concurrency, and converter configuration. There is no need to repeat the whole configuration in each annotation.

## 7. Other Notable Listener Container Properties

Besides the five main attributes, factory configuration usually needs to consider:

| Property | Meaning |
|---|---|
| `setConnectionFactory` | The factory that connects to the JMS provider |
| `setPubSubDomain` | Selects queue or topic |
| `setSessionTransacted` | Uses a transaction for the JMS session |
| `setMessageConverter` | Converts the JMS Message into a Java payload |
| `setErrorHandler` | Handles errors arising from the listener |
| `setDestinationResolver` | Resolves the destination name |
| `setRecoveryInterval` | The recovery wait interval in containers that support it |
| `setClientId` | Sets the JMS client identifier |
| `setSubscriptionDurable` | Enables a durable topic subscription |
| `setSubscriptionShared` | Enables a shared subscription when the version/provider supports it |

API names and configurability depend on Spring Framework/Spring Boot and the JMS provider. Cross-check the documentation for the exact version, especially for shared durable subscriptions, XA, and provider-specific options.

## 8. How Do Selector, Destination, and Subscription Interact?

A durable topic listener can combine destination, selector, and subscription:

~~~java
@JmsListener(
        destination = "orders.events",
        selector = "eventType = 'OrderCreated' AND region = 'APAC'",
        subscription = "apac-order-projection-v1",
        containerFactory = "durableTopicFactory")
public void updateProjection(OrderEvent event) {
    // Only processes publications chosen by the selector.
}
~~~

Meaning:

1. The destination selects the topic `orders.events`.
2. The selector filters publications by the JMS properties `eventType` and `region`.
3. The subscription sets the durable subscription's identity.
4. The factory determines the topic domain, client identity, durable mode, concurrency, and transaction.

The selector of a durable subscription needs to be stable. The provider may refuse when the application reconnects with the same subscription identity but the selector or certain fixed properties have changed. If you need to change the selector contract, plan a subscription migration following the broker's guidance, rather than silently changing the production configuration.

## 9. The Listener Container Lifecycle

Spring manages the listener container according to the application context:

1. When the context starts, listener endpoints are detected from `@JmsListener`.
2. The endpoint registrar uses the specified containerFactory to create the container.
3. The container creates the connection/session/consumer from the ConnectionFactory.
4. The consumer starts receiving messages and calls the listener method.
5. On a connection failure, the container/provider can perform recovery according to configuration.
6. When the context stops, the container stops receiving messages and releases resources according to the lifecycle.

Do not create a new consumer inside each listener invocation. Do not close a connection/session that the container is managing. If you need to pause or restart a listener, use the container's lifecycle API or an appropriate endpoint management mechanism.

A durable subscription typically still exists after the container stops. To delete a subscription, you must perform an unsubscribe according to the JMS/provider rules.

## 10. Common Mistakes

- **Confusing destination with subscription:** the destination is the queue/topic; the subscription name identifies the durable topic subscriber.
- **Using a selector to read a field in the body:** a JMS selector only evaluates supported headers and properties.
- **Setting a property after sending:** the broker has already evaluated the selector before the message is delivered; the property must be set before send.
- **Forgetting pubSubDomain:** the listener intends to open a topic but the factory uses the queue domain, or vice versa.
- **Assuming a subscription is automatically durable:** you need to enable the durable subscription at the factory/container and configure an appropriate identity.
- **Changing the subscription name on every deployment:** can create a new subscription and leave the old backlog behind.
- **Increasing concurrency for an unshared durable topic:** can conflict because multiple consumers open the same unshared subscription.
- **Increasing concurrency for a non-durable topic:** multiple consumers can create multiple separate subscriptions and process duplicate publications.
- **Using multiple factories with the same name or the wrong containerFactory:** the listener may receive unexpected configuration or fail to start.
- **Using a selector with the wrong property type:** the selector may not match because the property does not exist or has an incompatible data type.
- **Using concurrency that is too high:** increases load on the broker and downstream systems, reducing stability.
- **Assuming sessionTransacted covers the database:** a local JMS transaction does not by itself create a distributed transaction.
- **Not testing on the target broker:** selectors, shared subscriptions, destination provisioning, and recovery can differ by provider.

## 11. Testing the Listener Configuration

You should have integration tests that verify the actual configuration:

1. The queue listener receives messages from the correct destination.
2. The listener only receives messages that satisfy the selector.
3. Messages that do not satisfy the selector are still handled according to the expected topology.
4. The topic listener receives publications according to the pub-sub domain.
5. A durable subscription receives still-valid messages again after the consumer goes offline and reconnects.
6. The subscription name and clientID are kept stable.
7. Queue concurrency creates a number of consumers within the configured range.
8. An unshared durable topic does not accidentally create multiple conflicting consumers.
9. A shared durable subscription works correctly when the system uses it.
10. The factory is chosen correctly by containerFactory.
11. A transaction rollback leads to redelivery according to the broker policy.
12. Shutdown stops the container and releases resources.

Unit tests can check the listener service by calling the method directly. But destination resolution, selector, subscription, concurrency, and broker delivery semantics need integration tests with the target JMS provider/broker.

## 12. Design Checklist

Before deploying @JmsListener, check:

- Is the destination a queue or a topic?
- Is the destination name managed in configuration and broker provisioning?
- Does the selector only use valid JMS headers/properties, and is the property set before sending?
- Does the listener need a durable subscription?
- If durable, are the subscription name and client identity stable?
- Is a shared durable subscription needed to scale multiple consumers?
- Is the concurrency suitable for the queue/topic and the subscription type?
- Is containerFactory the correct bean with the correct ConnectionFactory?
- Are the transaction, converter, error handler, and recovery appropriate?
- Have the consume/subscribe permissions been granted on the broker?
- Are there integration tests for the selector, durable reconnect, concurrency, and shutdown?

When destination, selector, subscription, concurrency, and containerFactory are coordinated correctly, each listener receives the right group of messages with a suitable number of consumers and lifecycle, while the broker configuration is managed centrally and is easy to test.