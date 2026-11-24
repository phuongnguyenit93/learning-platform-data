# Queue, Topic, and Message Receiving Models

## Objectives

Jakarta Messaging (formerly known as JMS) provides two primary destination types: Queue for point-to-point and Topic for publish/subscribe. When using Spring JMS, an application can receive messages synchronously by calling methods on `JmsTemplate` or let a listener container receive them asynchronously via `@JmsListener`.

After this lesson, you will be able to:

- Distinguish between Queue and Topic by how messages are distributed.
- Understand regular subscriptions, durable subscriptions, and shared subscriptions.
- Choose between synchronous receive and asynchronous listeners.
- Use `JmsTemplate`, `@JmsListener`, and listener containers in Spring.
- Configure destinations, selectors, concurrency, and transactions appropriately.
- Avoid common mistakes regarding destination types, acknowledgement, and duplicate processing.

## 1. Where Does JMS Fit in the Architecture?

JMS is Java's standard messaging API. Starting with Jakarta EE 9, the API namespace moved from `javax.jms` to `jakarta.jms`; Spring Framework 6 and later use Jakarta Messaging. Some older libraries still use the `javax.jms` namespace, so check versions when integrating.

A JMS application typically has these components:

| Component | Role |
|---|---|
| ConnectionFactory | Creates connections to the JMS provider/broker |
| Connection or JMSContext | Represents an active connection to the provider |
| Session | Context for creating producers, consumers, and messages; manages acknowledgement/transactions |
| Destination | Send/receive target, usually a Queue or Topic |
| MessageProducer | Sends messages to a destination |
| MessageConsumer | Receives messages from a destination or subscription |
| Message | Envelope containing body, headers, and properties |

Spring adds supporting classes such as `JmsTemplate`, `DefaultMessageListenerContainer`, `@JmsListener`, and `MessageConverter`, freeing the application from manually managing the Connection, Session, and consumer lifecycle for every operation.

Queue and Topic are both types of `jakarta.jms.Destination`. They define how messages are distributed; they do not dictate whether the application must receive synchronously or asynchronously. Those are two independent choices.

## 2. Queue: Point-to-Point

A Queue represents the point-to-point (PTP) model. Producers send messages into a queue; one or more consumers can listen on that queue. For each delivery attempt, a message is distributed to only one consumer on the queue.

Example: an ordering system sends jobs to `orders.queue`. Three workers listen to the queue. The broker distributes each message to one worker for processing. The three workers share the load rather than each worker receiving a copy of every order.

~~~text
                 +------------------+
Producer ------> |   orders.queue   |
                 +------------------+
                    |      |      |
                    v      v      v
                 Worker  Worker  Worker
                    1      2      3

Each message is delivered to one worker in the consumer group.
~~~

Characteristics:

- Multiple consumers on the same queue can process concurrently to increase throughput.
- Each message is delivered to one consumer at a given delivery attempt.
- If a message is not acknowledged or the transaction is rolled back, the broker may redeliver the message.
- Consumers can use a message selector to receive only messages with matching properties; non-matching messages may be received by other consumers or remain in the queue.
- Jakarta Messaging does not mandate the distribution algorithm across multiple consumers on the same queue.

A Queue fits when each job needs to be processed by a single worker, such as generating an invoice, sending an email, processing an image, or updating a record. Having multiple workers does not mean every worker receives the same message.

**Note:** "A message goes to only one consumer" describes distribution for a single delivery attempt, not an exactly-once guarantee. If a consumer finishes processing but the acknowledgement is not recorded, the message can still be redelivered. Critical business logic should include idempotency or a mechanism to detect already-processed messages.

## 3. Topic: Publish/Subscribe

A Topic represents the publish/subscribe (pub/sub) model. Producers publish messages to a Topic; subscribers register to receive messages from the Topic via subscriptions.

Each independent subscription receives a copy of the message. Therefore, if three systems have three separate subscriptions, all three systems can receive the same event.

Example: when an order is paid, the producer publishes an event to `orders.events`. Billing, Analytics, and Notification have separate subscriptions:

~~~text
                         +----------------------+
Publisher --------------> |    orders.events    |
                         +----------------------+
                           |          |         |
                           v          v         v
                       Billing    Analytics  Notification
                     subscription subscription subscription
                         A          B          C

Each subscription receives a copy of the message.
~~~

Characteristics:

- The publisher does not need to know how many subscribers are interested.
- Each subscription has its own message stream.
- Acknowledgement by one subscription does not acknowledge the message for other subscriptions.
- Consumers can filter messages with a selector.
- A subscription can be durable or non-durable; it can be shared or unshared.

Topics fit events that multiple independent systems need to observe, such as `OrderPaid`, `CustomerUpdated`, or `InventoryChanged`.

## 4. Subscriptions: Durable, Non-Durable, and Shared

Distinguish between a Topic and a subscription. A Topic is where publishers send messages; a subscription is the registration state managed by the JMS provider. A consumer is the object in the application used to receive messages from the subscription.

### 4.1. Non-durable subscription

A non-durable subscription only exists while the consumer is active. If the application is not running or has closed its consumer when a message is published, the subscription does not retain the message for a later run.

Use a non-durable subscription when the application only cares about messages produced while it is active and can tolerate missing messages while offline, such as a live-updating dashboard.

### 4.2. Durable subscription

A durable subscription is retained by the provider even while the consumer is temporarily inactive. When the consumer reconnects with the same subscription, it can receive the messages retained during its offline window.

Example: the Billing service must process every payment event. The service may pause for maintenance yet still needs to receive events produced during that time. A durable subscription fits this requirement.

Points to remember:

- The subscription must be created before publish time to receive subsequent messages.
- The subscription is identified by name; a durable subscription is not a temporary consumer.
- The provider retains messages according to policy until delivered/acknowledged or expired.
- Durable does not mean retained indefinitely: TTL, capacity, retention, and broker policies can still apply.
- For unshared durable subscriptions, Jakarta Messaging requires a client identifier; shared durable subscriptions have different identification rules.

### 4.3. Shared subscription

A shared subscription allows multiple consumers to read from the same subscription to share load. Each message belonging to that subscription is delivered to one of the consumers sharing the subscription.

Distinguish two cases:

- Two independent subscriptions on the same Topic: each subscription receives a copy of the message.
- Multiple consumers on one shared subscription: the consumers split the messages belonging to that subscription's copy.

A shared subscription can be durable or non-durable. This is a Jakarta Messaging 2.0+ feature; specific support must be verified with the JMS provider and version in use.

| Subscription type | Offline consumer | Delivery within subscription |
|---|---|---|
| Unshared non-durable | Messages sent when no consumer is active can be missed | Single consumer |
| Shared non-durable | Subscription is not retained after all consumers close | Multiple consumers share; each message goes to one consumer |
| Unshared durable | Messages retained when subscription has no consumer, per provider policy | Single consumer at a time |
| Shared durable | Subscription persists while consumers are offline | Multiple consumers share; each message goes to one consumer |

## 5. How Do Queue and Topic Differ?

| Criterion | Queue | Topic |
|---|---|---|
| Model | Point-to-point | Publish/subscribe |
| Message distribution | One consumer in the group receives each delivery | Each subscription receives a copy |
| Multiple consumers | Share load on the same queue | Consumers sharing a shared subscription split load; independent subscriptions receive separate copies |
| Offline consumer | Messages usually remain in the queue per broker policy | Non-durable subscriptions may miss messages; durable subscriptions retain messages per provider policy |
| Use cases | Work queue, job processing, command | Domain event, broadcast, fan-out |
| Example | `orders.queue` | `orders.events` |

A quick guide to choosing:

- If a job needs to be processed by one worker, choose a Queue.
- If multiple systems need to independently receive the same event, choose a Topic with a separate subscription per system.
- If a single subscription needs multiple instances sharing load, consider a shared subscription.
- If a subscriber must receive events even when offline, use a durable subscription and configure appropriate retention/TTL.

Do not choose a Topic just because there are multiple instances of the same service. If the instances need to share load and only one instance should process each message, use a Queue or a shared subscription. Conversely, do not use a single Queue if every independent system must receive a copy of the event.

## 6. Message Selectors

A message selector is a filter expression based on JMS message properties. A consumer only receives messages whose properties satisfy the selector condition.

For example, the publisher sets properties:

~~~java
jmsTemplate.convertAndSend("orders.queue", "order-42", message -> {
    message.setStringProperty("region", "APAC");
    message.setStringProperty("eventType", "OrderCreated");
    return message;
});
~~~

The consumer can receive only messages for the APAC region:

~~~java
@JmsListener(
    destination = "orders.queue",
    selector = "region = 'APAC'"
)
public void receiveApacOrder(String orderId) {
    // Process APAC region order.
}
~~~

A selector reads properties and JMS-allowed header fields in the expression. It is not a query over a JSON body or object payload. If you want to filter by a field inside the payload, promote that field to a JMS property when publishing or handle the condition inside the consumer.

Selectors help with logical routing within the same destination, but they do not replace authorization or validation. The producer must still set properties with the right types and the consumer must still validate payloads.

## 7. Two Message Receiving Models

Queue/Topic describes how messages are distributed. Synchronous/asynchronous describes how the application retrieves messages. You can receive messages from either a Queue or a Topic using either approach, provided the destination and subscription are configured appropriately.

### 7.1. Synchronous receive: the application actively pulls messages

With synchronous receive, an application thread calls a receive method and waits for a message. In Spring, `JmsTemplate` provides methods such as `receive` and `receiveAndConvert`.

~~~java
import org.springframework.jms.core.JmsTemplate;

public final class QueuePoller {

    private final JmsTemplate jmsTemplate;

    public QueuePoller(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void pollOnce() {
        Object payload = jmsTemplate.receiveAndConvert("orders.queue");

        if (payload == null) {
            System.out.println("No message available");
            return;
        }

        System.out.println("Received: " + payload);
    }
}
~~~

Configure `receiveTimeout` to bound the wait time. If no message arrives within the timeout, the receive method can return `null`. If waiting indefinitely, the calling thread can be held for a long time.

Synchronous receive fits tasks that need to pull messages on their own schedule, such as a batch poller or administrative tool. It is usually not a good choice for a service that needs to continuously process messages at high throughput.

### 7.2. Asynchronous receive: listener invoked when a message arrives

With asynchronous receive, the application registers a listener; the JMS provider and Spring listener container invoke the listener when a message arrives. This is the usual model for services that process messages continuously.

Spring supports:

- `jakarta.jms.MessageListener`: JMS interface with the `onMessage(Message)` method.
- `@JmsListener`: marks a method in a managed bean as a message-receiving endpoint.
- `MessageListenerAdapter`: adapts a plain POJO into a listener and can convert the payload before invoking the method.
- `DefaultMessageListenerContainer` and `SimpleMessageListenerContainer`: manage listeners, connections, sessions, and consumers.

In Spring Framework, `@EnableJms` enables registration of `@JmsListener` endpoints. Each endpoint is served by a listener container created from a `JmsListenerContainerFactory`.

## 8. Using @JmsListener in Spring

A POJO can receive payloads directly without implementing `MessageListener` itself:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumers {

    @JmsListener(destination = "orders.queue")
    public void consumeQueue(String orderId) {
        System.out.println("Queue received: " + orderId);
    }

    @JmsListener(
        destination = "orders.events",
        containerFactory = "topicListenerContainerFactory"
    )
    public void consumeTopic(String event) {
        System.out.println("Topic received: " + event);
    }
}
~~~

The first listener receives from a Queue via the default container. The second listener uses a factory configured for Topics. Method arguments can be the converted payload, the JMS `Message`, or other parameter types supported by Spring.

If the listener bean is a singleton and the container has multiple consumers/threads, the method can be called concurrently. Shared mutable state in the listener must be protected in a thread-safe way or moved to a service with proper synchronization.

## 9. Configuring Queue and Topic Separately

With Spring JMS, the destination type is chosen by the configuration of the template or listener container. `JmsTemplate` defaults to the queue domain when creating a destination from a name. If using a Topic, configure `pubSubDomain` on both the sending template and the receiving listener container.

Example configuring two listener factories and two templates:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false); // Queue
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-6");
        return factory;
    }

    @Bean
    DefaultJmsListenerContainerFactory topicListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true); // Topic
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    JmsTemplate queueJmsTemplate(ConnectionFactory connectionFactory) {
        var template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        return template;
    }

    @Bean
    JmsTemplate topicJmsTemplate(ConnectionFactory connectionFactory) {
        var template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);
        return template;
    }
}
~~~

Sending messages:

~~~java
queueJmsTemplate.convertAndSend("orders.queue", "order-42");
topicJmsTemplate.convertAndSend("orders.events", "OrderCreated:order-42");
~~~

This is a Spring integration configuration, not a standalone program runnable with `javac` alone. The application needs the Spring JMS dependency, a Jakarta Messaging provider, a ConnectionFactory, and destinations supported by the provider or configured via a DestinationResolver.

If using Spring Boot, check the auto-configuration of both `JmsTemplate` and the listener container. The property `spring.jms.pub-sub-domain=true` switches the default configuration to Topic; sender and receiver must use the same destination domain. If the application uses both Queues and Topics, creating separate templates/factories is clearer.

## 10. Durable Topic Subscriptions with Spring

For a subscriber that needs to receive messages while the application is temporarily offline, configure a durable subscription. The Spring listener endpoint has a `subscription` attribute; the listener container factory needs durable subscriptions enabled. For unshared durable subscriptions, configure a stable client ID.

Example factory configuration:

~~~java
@Bean
DefaultJmsListenerContainerFactory durableTopicListenerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("billing-service");
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Listener:

~~~java
@JmsListener(
    destination = "orders.events",
    subscription = "billing-subscription",
    containerFactory = "durableTopicListenerFactory"
)
public void consumeBillingEvent(String event) {
    // Process event retained for billing-subscription.
}
~~~

The subscription name and client ID must remain stable across restarts. Do not run multiple independent consumers on the same unshared durable subscription; if load sharing is needed, check shared durable subscriptions and provider support. Manage the subscription lifecycle: an abandoned subscription can keep accumulating messages until it is unsubscribed or messages expire.

Persistent delivery mode and durable subscriptions solve two different problems. A persistent message asks the provider to store the message according to delivery mode; a durable subscription retains a copy for a registered subscriber even when the subscriber is offline. Setting a message as persistent does not automatically create a durable subscription.

## 11. Listener Container, Concurrency, and Thread Safety

The listener container is the Spring layer sitting between the JMS provider and the handler method. It manages connections, sessions, consumers, listener lifecycle, concurrency, and certain transaction/recovery policies.

Two common containers:

- `DefaultMessageListenerContainer`: used in most cases; supports runtime adjustment, recovery when the broker is interrupted, and participation in externally managed transactions.
- `SimpleMessageListenerContainer`: simpler structure, suitable for cases with few dynamic adjustment requirements.

The factory can configure concurrency:

~~~java
factory.setConcurrency("2-6");
~~~

This value asks the container to maintain a number of consumers/sessions within the configured range supported by the container. For a Queue, multiple consumers typically share load. For a Topic, separate subscriptions each receive a copy; to have multiple consumers share load on a single copy, a shared subscription must be used.

A JMS Session is not an object meant for arbitrary concurrent use from multiple threads. The listener container manages a session/consumer per processing thread. Do not manually share a single Session or MessageConsumer across application threads.

When increasing concurrency:

- Throughput can increase if processing is independent and the broker has sufficient capacity.
- Processing completion order may differ from initial receive order.
- The listener bean may be called concurrently and must be thread-safe.
- Database pools, downstream services, and broker limits must have enough capacity.
- Retries or rollbacks can cause messages to be redelivered.

Do not set concurrency overly high just to increase thread count. Measure actual throughput, latency, backlog depth, and processing time.

## 12. Acknowledgement and Transactions

Acknowledgement informs the provider that a message has been confirmed. Common JMS modes:

- `AUTO_ACKNOWLEDGE`: the provider automatically acknowledges after the listener finishes according to JMS semantics.
- `CLIENT_ACKNOWLEDGE`: the client explicitly acknowledges; acknowledgement may apply to messages previously received by the same session.
- `DUPS_OK_ACKNOWLEDGE`: the provider may acknowledge lazily to improve performance; the application must tolerate duplicates.
- Transacted Session: message receipt and send operations within the same JMS Session are committed or rolled back together under the transaction.

With a Spring listener container, `setSessionTransacted(true)` enables a local transaction for each listener invocation. If the listener throws an exception before the transaction commits, message receipt is rolled back and the message can be redelivered.

~~~java
factory.setSessionTransacted(true);
~~~

This makes error handling safer, but a local JMS transaction does not automatically encompass an independent database transaction. A situation can occur where the database commits but the JMS transaction rolls back; the message is redelivered and business logic runs again. Use an idempotency key, inbox/deduplication table, or XA/JTA if a distributed transaction is truly required and its operational cost is acceptable.

Do not assume by default that `AUTO_ACKNOWLEDGE` is always reliable enough for critical business logic. Read the semantics of the listener container and provider, configure transacted sessions appropriately, and check the broker's redelivery and dead-letter policies.

## 13. Ordering, Redelivery, and Dead-Letter Handling

A Queue does not mean all messages are always processed sequentially when there are multiple consumers. Each session has its own processing order, but multiple consumers running concurrently may finish in a different order. Topics also have ordering within a subscription/consumer according to provider rules, rather than global ordering across all subscribers.

When a listener fails:

1. If the session is transacted and the listener throws an exception, the transaction can roll back.
2. The provider may redeliver the message.
3. The message may be delivered multiple times; the listener should be idempotent.
4. After a configured number of redeliveries or provider condition, the message may be moved to a dead-letter queue.

Dead-letter queues, redelivery limits, and backoff depend on the JMS provider/broker; Jakarta Messaging does not define a single uniform policy for all brokers. Configure and monitor according to the broker in use.

Headers/properties such as `JMSRedelivered` or `JMSXDeliveryCount` can help detect redelivered messages. Do not rely on them as a substitute for a stable event ID and business-layer idempotency.

## 14. Choosing a Receiving Model by Scenario

| Scenario | Destination | Receiving model |
|---|---|---|
| Multiple workers processing different orders | Queue | `@JmsListener` with concurrency |
| A service actively pulling a batch of jobs | Queue | Synchronous `JmsTemplate.receive` |
| Billing, Analytics, and Notification all need to know about an event | Topic with separate subscriptions | Asynchronous listener per subscription |
| Subscriber must receive events while offline | Topic durable subscription | Asynchronous listener container |
| One subscription has multiple instances sharing load | Shared Topic subscription or Queue | Multiple consumers on the same subscription/queue |
| Admin tool needs to inspect messages without removing them | Queue | `QueueBrowser` if supported by provider |

Decisions should stem from business semantics: whether one message needs one worker or multiple independent systems; whether the application can miss messages while offline; whether parallel processing is needed; and what guarantees are required when a listener fails.

## 15. Common Pitfalls

- **Using a Topic while expecting only one service instance to receive each message:** multiple independent subscriptions will receive copies. Use a shared subscription or a Queue if the goal is load sharing.
- **Using a Queue while expecting multiple systems to receive the same message:** competing consumers on a queue do not each receive a copy. Use a Topic with separate subscriptions.
- **Using a non-durable Topic for a subscriber that must receive all events:** an offline subscriber can miss messages. Create a durable subscription.
- **Thinking persistent messages automatically make a Topic durable:** persistent delivery and durable subscriptions are two different configurations.
- **Configuring the sender as Topic but the listener container as Queue:** the two sides do not use the same destination domain. Use templates and factories with matching `pubSubDomain`.
- **Using synchronous receive in a thread requiring fast response:** the thread blocks while waiting for a message. Set a receive timeout or use a listener container.
- **Increasing concurrency when the listener uses non-thread-safe mutable state:** can cause race conditions or corrupted data.
- **Acknowledging a message before business logic completes:** a failure after acknowledgement can lose the chance for redelivery.
- **Retrying without idempotency:** the same message can cause repeated business side effects.
- **Assuming JMS guarantees global ordering:** concurrency, multiple sessions, multiple subscriptions, and broker policies affect actual ordering.

## 16. Implementation Checklist

- [ ] Chose Queue or Topic based on single-worker vs. multiple independent subscribers.
- [ ] If using a Topic, determined whether the subscription is durable or non-durable.
- [ ] If load sharing on a Topic is needed, verified provider support for shared subscriptions.
- [ ] Sender and listener container use the same destination domain.
- [ ] Chose synchronous receive or asynchronous listener based on processing needs.
- [ ] Configured receive timeout for synchronous receive.
- [ ] Configured listener container and appropriate concurrency.
- [ ] Listener is safe under concurrent invocations.
- [ ] Configured acknowledgement/transactions and verified redelivery behavior.
- [ ] Consumer has idempotency or deduplication.
- [ ] Configured message selectors on properties if filtering is needed.
- [ ] Monitoring is in place for queue depth, subscription backlog, processing latency, and dead-letters.
- [ ] Tested broker restarts, offline consumers, listener exceptions, and message redelivery.

## 17. References

- [Jakarta Messaging 3.1 Specification — Queue semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#queue-semantics)
- [Jakarta Messaging 3.1 Specification — Topic semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#topic-semantics)
- [Jakarta Messaging 3.1 Specification — Creating a consumer on a topic](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#creating-a-consumer-on-a-topic)
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
