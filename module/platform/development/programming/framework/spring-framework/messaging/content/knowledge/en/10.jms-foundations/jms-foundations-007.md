# Durable, Non-Durable, and Shared Topic Subscriptions

In the JMS publish/subscribe model, publishers send messages to a Topic and subscribers receive messages through a subscription. The subscription determines which messages are retained and which consumers can receive them. Therefore, you must distinguish between Topic, subscription, and consumer before choosing a subscription type.

Jakarta Messaging defines two independent axes for subscriptions:

- **Durable / non-durable:** whether the subscription continues to exist and accumulate messages when no consumer is active.
- **Shared / unshared:** whether a subscription allows one or multiple consumers to operate concurrently.

Combining these two axes yields four types: unshared non-durable, unshared durable, shared non-durable, and shared durable. This lesson explains their lifecycles, identification, Jakarta Messaging API usage, and listener configuration in Spring Framework.

## 1. Topic, Subscription, and Consumer

These three concepts have distinct roles:

**Topic** is the destination to which publishers send messages. A Topic represents an event stream, such as orders.events or inventory.updates.

**Subscription** is the message-receiving state managed by the messaging provider. It defines which Topic a consumer or group of consumers is interested in, optionally with a message selector and other attributes.

**Consumer** is the object inside the application used to receive messages from a subscription. Consumers can be created, closed, and recreated; the subscription's lifecycle depends on its registration type.

Visualizing this:

~~~text
Publisher
    |
    | publish M1, M2, M3
    v
  Topic: orders.events
    |
    +--------------------------+
    |                          |
    v                          v
Subscription A             Subscription B
    |                          |
    v                          v
Consumer A                 Consumer B
    |                          |
    v                          v
Receives M1, M2, M3       Receives M1, M2, M3
~~~

Each independent subscription receives a copy of messages matching that subscription. If there are two different subscriptions on the same Topic, each subscription can receive the same message.

If a subscription is shared and has multiple consumers, each message belonging to that subscription is delivered to only one consumer in the group. Those consumers share the work of processing a single subscription's messages.

This is the key point: **multiple subscriptions on the same Topic create multiple independent receiving streams; multiple consumers on the same shared subscription split one receiving stream.**

## 2. Two Subscription Classification Axes

### Durable and non-durable

A **non-durable subscription** exists only while it has an active consumer. Messages sent to the Topic when no consumer belongs to the subscription are not retained for a later registration. When the last consumer closes, the non-durable subscription is deleted along with any remaining undelivered messages.

A **durable subscription** is retained by the messaging provider even when no consumer is active. Messages sent to the Topic while the subscriber is offline can accumulate for delivery when the consumer reconnects. The subscription persists until the application removes it via an unsubscribe operation, or per provider administrative policies.

Durable subscriptions fit consumers that must continue receiving events after application pauses, redeployments, or connection drops.

### Shared and unshared

An **unshared subscription** allows only one active consumer at a time. If another consumer attempts to open the same unshared subscription while the current consumer is still open, the provider rejects it.

A **shared subscription** allows multiple consumers to join a single subscription. The provider distributes each message of the subscription to one consumer in the group. The specific distribution mechanism among consumers depends on the provider; the Jakarta Messaging specification does not mandate a specific load-balancing algorithm.

Shared subscriptions are useful when you need to scale processing capacity with multiple consumers while maintaining one logical subscription.

## 3. Four Topic Subscription Types

| Type | Identity | Concurrent consumers | When the last consumer closes |
|---|---|---:|---|
| Unshared non-durable | No subscription name | 1 | Subscription and undelivered messages are deleted |
| Unshared durable | Client ID + subscription name | 1 | Subscription remains and accumulates messages |
| Shared non-durable | Subscription name and optional client ID | Multiple | Subscription and undelivered messages are deleted |
| Shared durable | Subscription name and optional client ID | Multiple | Subscription remains and accumulates messages |

### 3.1. Unshared non-durable

This is the simplest registration type. The application creates a consumer on the Topic; the provider creates a private subscription for that consumer.

Characteristics:

- No subscription name required.
- Only one consumer attached to the subscription.
- Messages are only added to the subscription while the consumer is active.
- Closing the consumer deletes the subscription and undelivered messages.

Suitable for live monitoring screens, transient notifications, or clients that only care about events while connected.

If a user reopens the application after being offline, the application does not receive messages published while no consumer was active.

### 3.2. Unshared durable

The application creates a named subscription and associates it with a client identifier. The provider persists subscription state when the consumer closes.

Characteristics:

- Requires a stable subscription name.
- Client ID must be set before creating the consumer.
- Only one active consumer on the subscription at a time.
- Closing the consumer does not delete the subscription.
- Messages sent while no consumer is active are retained according to retention policies, expiration, and provider capacity.
- The application must call unsubscribe to delete the subscription when no longer used.

This is a good fit for an audit service or an application that needs to catch up on events emitted during service downtime.

The subscription name must remain stable across restarts. If the application generates a random name on every startup, the provider treats it as a new subscription; the old subscription may keep accumulating messages and consuming resources.

### 3.3. Shared non-durable

This type allows multiple consumers to read from one subscription, but the subscription exists only while at least one consumer is active.

Characteristics:

- Has a subscription name.
- Client ID can be omitted; if used when creating the subscription, subsequent consumers must use the same client ID.
- Can have multiple concurrent consumers.
- Each message belonging to the subscription is delivered to one consumer in the group.
- When the last consumer closes, the subscription and undelivered messages are deleted.

This type fits when load sharing is needed while the application is running, without needing to store messages when all consumers stop.

### 3.4. Shared durable

This combines offline subscription persistence with load sharing across multiple consumers.

Characteristics:

- Has a subscription name.
- Client ID is optional per Jakarta Messaging; if the subscription was created with a client ID, subsequent consumers must use the same client ID.
- Multiple consumers can operate concurrently on the same subscription.
- Each message is delivered to only one consumer in the group.
- When all consumers close, the subscription persists and continues accumulating messages until unsubscribed or messages expire.

Shared durable fits a group of workers that need to jointly process an event stream while also retaining backlog if the whole group temporarily stops.

## 4. Distinguishing Broadcast from Load Sharing

A Topic can have multiple independent subscriptions. Each subscription receives a copy of matching messages:

~~~text
                    Topic: orders.events
                       |
             +---------+---------+
             |                   |
             v                   v
       Subscription A      Subscription B
       Audit service        Analytics service
             |                   |
             v                   v
        Consumer A           Consumer B
        Receives M1, M2      Receives M1, M2
~~~

If Subscription A is shared among three consumers, the three consumers do not receive three copies of each message. They split the messages belonging to Subscription A:

~~~text
               Subscription A (shared)
                         |
              +----------+----------+
              |          |          |
              v          v          v
          Consumer 1 Consumer 2 Consumer 3
              \          |          /
               \         |         /
                M1, M2, M3 are
                distributed across the group
~~~

The specification does not mandate which message must go to which consumer. Do not rely on a specific consumer always receiving a fixed partition or subset of the stream unless the provider offers a specific guarantee.

## 5. Subscription Identity: Client ID and Subscription Name

### Client identifier

Client ID identifies a JMS client at the Connection level. For unshared durable subscriptions, a client ID is mandatory and must be set before creating the consumer.

A Client ID should be:

- Unique among active Connections on the same provider.
- Stable when the application wants to reopen an existing durable subscription.
- Set before creating the associated session/consumer.
- Not duplicated by preconfigured settings on the ConnectionFactory.

A Connection that already has a client ID cannot arbitrarily switch to a different ID. When using a Spring listener container, client ID can be configured on the container factory or container.

### Subscription name

Subscription name is a logical name chosen by the application. For unshared durable subscriptions, identity is formed from client ID plus subscription name. For shared subscriptions, identity is based on subscription name and an optional client ID.

Good naming practices:

- Use stable, business-meaningful names.
- Distinguish separate consumer groups, e.g., orders-audit-v1 and orders-workers-v1.
- Never generate random names on each restart.
- Avoid letting two applications accidentally share an identity when they need independent delivery.
- Change names intentionally when creating a new subscription or changing the receiving contract.

A durable subscription can continue accumulating messages after the application stops. When it is no longer needed, stop consumers and delete the subscription properly.

## 6. Jakarta Messaging API for Creating Consumers

Jakarta Messaging 3.1 provides methods for all four subscription types. Corresponding methods exist on both JMSContext and Session.

| Subscription type | JMSContext API |
|---|---|
| Unshared non-durable | createConsumer(topic) |
| Unshared durable | createDurableConsumer(topic, name) |
| Shared non-durable | createSharedConsumer(topic, name) |
| Shared durable | createSharedDurableConsumer(topic, name) |

The shared methods were added in JMS 2.0. The broker/provider must support shared subscriptions. If a provider only supports JMS 1.1 or does not implement shared features, these methods will not work.

### 6.1. Creating an unshared non-durable consumer

~~~java
try (JMSContext context = connectionFactory.createContext()) {
    JMSConsumer consumer = context.createConsumer(topic);
    // Consumer only receives messages while active.
}
~~~

No subscription name. Closing the consumer deletes the subscription.

### 6.2. Creating an unshared durable consumer

~~~java
try (JMSContext context =
        connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

    context.setClientID("orders-audit-service");

    try (JMSConsumer consumer =
            context.createDurableConsumer(topic, "orders-audit-v1")) {

        Message message = consumer.receive(5000);

        if (message instanceof TextMessage textMessage) {
            System.out.println(textMessage.getText());
        }
    }
}
~~~

Client ID is set before creating the consumer. If the application closes the consumer and restarts, it must use the same client ID and subscription name to reopen the durable subscription.

The example uses AUTO_ACKNOWLEDGE for brevity. For business processing requiring high reliability, consider appropriate transactions and acknowledgement.

### 6.3. Creating a shared non-durable consumer

~~~java
try (JMSContext context = connectionFactory.createContext()) {
    JMSConsumer consumer =
            context.createSharedConsumer(topic, "orders-live-workers");

    // Additional consumers can be created using the same subscription name.
}
~~~

Other consumers can use the same Topic and subscription name to join the subscription. Each message belonging to the subscription will be delivered to one consumer in the group.

### 6.4. Creating a shared durable consumer

~~~java
try (JMSContext context = connectionFactory.createContext()) {
    JMSConsumer consumer =
            context.createSharedDurableConsumer(topic, "orders-workers-v1");

    // Other consumers can join the same shared durable subscription.
}
~~~

A shared durable subscription can be reopened after all consumers have closed. Client ID may be unnecessary per the specification; if the application/provider uses a client ID when creating the subscription, the same value must be reused.

These are illustrative API snippets. They require a ConnectionFactory and Topic configured by the JMS provider. They are not standalone programs runnable without a broker.

## 7. Configuring Subscriptions in Spring Framework

Spring JMS provides JmsTemplate to send messages and listener containers to receive messages. For annotation-driven listeners, you can use @JmsListener and DefaultJmsListenerContainerFactory.

Relevant properties:

- pubSubDomain: specifies that the listener works with Topics.
- subscriptionDurable: enables durable subscriptions.
- subscriptionShared: enables shared subscriptions.
- clientId: client identifier for the Connection used by the listener container.
- subscription: subscription name on @JmsListener.
- concurrency: number of concurrent consumers created by the listener container.

Spring configuration example:

~~~java
@Configuration
@EnableJms
public class TopicMessagingConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory durableTopicFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSubscriptionDurable(true);
        factory.setClientId("orders-audit-service");
        factory.setSessionTransacted(true);

        return factory;
    }

    @Bean
    public DefaultJmsListenerContainerFactory sharedDurableTopicFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSubscriptionDurable(true);
        factory.setSubscriptionShared(true);
        factory.setSessionTransacted(true);

        return factory;
    }

    @Bean
    public DefaultJmsListenerContainerFactory sharedNonDurableTopicFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSubscriptionShared(true);
        factory.setSessionTransacted(true);

        return factory;
    }

    @Bean
    public JmsTemplate topicJmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);
        return template;
    }
}
~~~

Subscription names are declared on the listeners:

~~~java
@Component
public class OrderTopicListeners {

    @JmsListener(
            destination = "orders.events",
            subscription = "orders-audit-v1",
            containerFactory = "durableTopicFactory"
    )
    public void audit(OrderEvent event) {
        System.out.println("[audit] " + event.orderId());
    }

    @JmsListener(
            destination = "orders.events",
            subscription = "orders-workers-v1",
            containerFactory = "sharedDurableTopicFactory",
            concurrency = "3-8"
    )
    public void process(OrderEvent event) {
        System.out.println("[worker] " + event.orderId());
    }

    @JmsListener(
            destination = "orders.events",
            subscription = "orders-live-workers",
            containerFactory = "sharedNonDurableTopicFactory",
            concurrency = "2-4"
    )
    public void updateLiveView(OrderEvent event) {
        System.out.println("[live] " + event.orderId());
    }
}
~~~

The example above illustrates three independent subscriptions on the same Topic:

- orders-audit-v1 is unshared durable, with a stable client ID and a single consumer.
- orders-workers-v1 is shared durable, allowing multiple consumers to share load.
- orders-live-workers is shared non-durable, with multiple consumers sharing load while the group is active.

Each independent subscription can receive a copy of the same event. Consumers inside a shared subscription only split messages belonging to that group's subscription.

The application must supply a ConnectionFactory compatible with Jakarta Messaging 3.1 or JMS 2.0+ for shared features. Specific broker, destination, and connection configuration depend on the provider. The Spring snippet above is integration configuration; it does not start a broker on its own.

Events can be sent to the Topic via JmsTemplate:

~~~java
topicJmsTemplate.convertAndSend(
        "orders.events",
        new OrderEvent("ORD-1024")
);
~~~

Example DTO:

~~~java
public record OrderEvent(String orderId) {
}
~~~

Spring uses MessageConverter to convert Java payloads into JMS Messages and back at the listener. Configure an appropriate converter if the provider or application uses a specific JSON format.

## 8. Acknowledgement, Transactions, and Data Durability

Durable subscriptions and message delivery modes are two different concepts.

**Durable subscription** determines whether the subscription persists and accumulates messages when no consumer is present.

**DeliveryMode.PERSISTENT / NON_PERSISTENT** determines the provider's storage durability guarantee in case of failures. A durable subscription does not automatically make every message persistent.

Additionally, messages can expire based on time-to-live or be affected by storage limits, retention policies, and broker administration. Therefore, durable should not be interpreted as a guarantee to retain messages indefinitely.

Acknowledgement determines when the provider considers a message processed:

- AUTO_ACKNOWLEDGE: provider automatically acknowledges per session rules.
- CLIENT_ACKNOWLEDGE: application explicitly acknowledges messages.
- DUPS_OK_ACKNOWLEDGE: allows provider to acknowledge lazily/in batches and may redeliver messages.
- SESSION_TRANSACTED: receiving and acknowledgements fall inside a JMS session transaction.

With a Spring listener container, configuring sessionTransacted=true causes exceptions in the listener to roll back the session and allow the provider to redeliver the message per its policy.

Do not rely on durable subscriptions as a substitute for transactions, acknowledgement, or idempotency. Consumers must still tolerate message redelivery after errors or rollbacks.

## 9. Selectors and Subscription Attributes

A subscription can use a message selector to receive only messages with matching properties.

Example:

~~~java
JMSConsumer consumer = context.createDurableConsumer(
        topic,
        "priority-orders-v1",
        "priority = 'HIGH'",
        false
);
~~~

Selectors filter on message properties, not by arbitrarily querying Java payloads. Publishers must set the corresponding properties on the JMS Message.

When recreating a consumer on an existing durable subscription, the application must adhere to the attributes defining the subscription such as Topic and selector. Do not assume you can arbitrarily change the selector on an existing subscription.

Some unshared APIs also support noLocal to prevent a consumer from receiving messages published from its own connection. noLocal is not a universal parameter across all shared subscription variants; check the corresponding Jakarta Messaging API overloads.

## 10. Lifecycle and Deleting a Durable Subscription

Closing a consumer and deleting a durable subscription are two different operations.

- Closing a consumer only releases the consumer object.
- The durable subscription remains and continues accumulating messages.
- Unsubscribing deletes the durable subscription along with its undelivered message state.

Example deleting an unshared durable subscription:

~~~java
try (JMSContext context = connectionFactory.createContext()) {
    context.setClientID("orders-audit-service");
    context.unsubscribe("orders-audit-v1");
}
~~~

Before unsubscribing:

1. Stop the listener container or close all consumers using the subscription.
2. Ensure no related transactions or unacknowledged messages remain.
3. Use the exact client ID and subscription name.
4. Delete only when the business no longer needs the subscription's backlog.

If the subscription currently has active consumers or messages in incomplete transactions, the provider may reject the deletion.

Shared durable subscriptions also require intentional lifecycle management. When a subscription is no longer needed, stop all consumers in the group and unsubscribe using the identity used by the provider.

## 11. Choosing a Subscription Type by Requirement

| Need | Suitable type | Reason |
|---|---|---|
| Client only receives events while open | Unshared non-durable | Simple, retains no offline backlog |
| A service must receive missed events after restart | Unshared durable | Subscription persists while consumer is offline |
| Multiple workers share load while system is active | Shared non-durable | Multiple consumers on one subscription, no backlog kept when group stops |
| Multiple workers share load and need backlog when whole group is offline | Shared durable | Combines load sharing and subscription persistence |

Some practical examples:

**Audit service:** use unshared durable if there is only one logical consumer and it needs to receive events after redeployment.

**Notification dashboard:** use non-durable if updates are only needed while clients are connected. Users reopening the dashboard do not necessarily need all historical events.

**Image processing workers:** use shared durable if multiple workers need to share load and messages must be kept while all workers pause.

**Live telemetry processors:** use shared non-durable if multiple consumers share load during an active session, but old data does not need replay after the group stops.

## 12. Common Mistakes

**Confusing Topic with subscription:** a Topic is the message-publishing destination; a subscription is the receiving state. Multiple subscriptions on one Topic can receive the same message independently.

**Thinking shared means broadcast to all consumers:** false. A shared subscription delivers each message to one consumer in the group. To have multiple independent groups receive events, create multiple subscriptions.

**Thinking durable means retaining messages indefinitely:** false. Messages can expire or be constrained by capacity limits or broker policies. Durable subscriptions still require backlog management.

**Using the same durable subscription name with a different client ID:** for unshared durable, identity includes both client ID and subscription name. A different client may accidentally create a separate subscription instead of resuming the old one.

**Generating a random subscription name on every run:** the provider treats each name as a new subscription. Old subscriptions may linger and accumulate messages.

**Opening multiple consumers on an unshared durable subscription:** only one active consumer is permitted. To share load, use a shared durable subscription.

**Increasing concurrency on a Topic without a shared subscription:** can create independent subscriptions/consumers or violate subscription constraints, causing duplicate message delivery or startup errors. Increase concurrency only when shared subscriptions are configured and supported by the provider.

**Assuming Spring creates the broker automatically:** Spring JMS only provides templates, listener containers, and adapters. The application still needs a JMS ConnectionFactory and provider.

**Assuming durable subscriptions guarantee exactly-once processing:** messages can be redelivered. Use transactions, acknowledgement, and idempotent processing as required by business logic.

**Forgetting to delete obsolete subscriptions:** durable subscriptions do not disappear when consumers close. Unused subscriptions can keep accumulating messages and consuming broker resources.

## 13. Pre-Deployment Checklist

- Are Topic and subscription clearly distinguished in the design?
- Does data need to be retained while consumers are offline?
- Does a subscription need one consumer or multiple consumers sharing load?
- Is the subscription name stable and unique per identity?
- Is Client ID set properly and free of collisions with active Connections?
- Does the provider support shared durable/shared non-durable subscriptions?
- Are message selectors and subscription attributes consistent across consumers?
- Are delivery mode, expiration, acknowledgement, and transactions configured?
- Can consumers handle message redelivery?
- Are metrics in place for durable subscription count, backlog, message age, and active consumers?
- Is the procedure for stopping consumers and unsubscribing defined?

## 14. Takeaways

- A Topic is where publishers emit messages; a subscription is the receiving state; a consumer is the object reading messages.
- A durable subscription continues existing and accumulating messages without active consumers until unsubscribed or messages expire.
- A non-durable subscription exists only while active consumers are present.
- An unshared subscription allows only one active consumer at a time.
- A shared subscription allows multiple consumers; each message is delivered to one consumer in the group.
- Unshared durable is identified by client ID and subscription name; shared subscriptions use subscription name and an optional client ID per specification.
- Jakarta Messaging 2.0+ provides APIs for creating shared consumers; the provider must support this feature.
- Spring JMS supports configuring durable/shared subscriptions via listener containers and @JmsListener.
- Durable subscriptions do not replace persistent delivery mode, transactions, acknowledgement, or idempotency.
- Closing a consumer does not delete a durable subscription; unsubscribe when it is no longer needed.

## References

- [Jakarta Messaging 3.1 Specification — Topic subscriptions](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta EE Tutorial — Messaging concepts](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html)
- [Spring Framework 6.2 — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework 6.2 — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
