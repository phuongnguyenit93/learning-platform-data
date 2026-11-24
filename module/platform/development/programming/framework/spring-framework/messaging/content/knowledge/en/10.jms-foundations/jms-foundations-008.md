# clientId, Subscription Name, and Receiver Lifecycle in Spring JMS

## 1. The Big Picture

In JMS, a receiver can consume messages from a queue or subscribe to a topic. With a queue, a message is typically distributed to one suitable consumer according to provider semantics. With a topic, each subscription is a separate receiving stream; multiple subscriptions can receive copies of the same publication.

When using a **durable topic subscription**, the broker needs to identify the subscription via a stable identity so it can continue retaining messages while the consumer is temporarily offline. Two key concepts are:

- **clientID:** JMS client identifier at the connection level. It helps the provider identify the client and participates in the identity of a durable subscription per JMS/provider rules.
- **subscription name:** logical name of the durable subscription. It identifies the subscription the application wants to resume across connections.

In classic JMS, a durable subscription is not merely an open consumer. The subscription can remain on the broker after the consumer closes, so messages are retained during the consumer's absence according to broker policies.

After this lesson, you should be able to:

- Distinguish clientID, subscription name, and destination name.
- Explain durable and non-durable topic subscriptions.
- Manage start, stop, close, and unsubscribe for their proper purposes.
- Configure a durable listener in Spring JMS.
- Understand shared and unshared durable subscriptions in JMS 2.0.
- Avoid clientID conflicts when deploying multiple instances.
- Design permissions, selectors, storage, and backlog handling when a consumer resumes.

## 2. Queue, Topic, and Subscription

### 2.1 Queue

Queues are typically used for the point-to-point model. A message in a queue is delivered to one consumer for processing according to the provider's distribution mechanism. If multiple workers read from one queue, they typically compete for work.

Queues do not require a durable topic subscription name to retain messages. Whether messages remain when no consumer is present depends on delivery mode, queue policies, expiration, broker persistence, and provider configuration.

### 2.2 Topic

Topics use the publish-subscribe model. Publishers send a publication to a topic; matching subscriptions can receive copies of that publication.

Each subscription has its own receiving state. If two different applications subscribe to the same topic using two independent subscriptions, each subscription can receive a copy of the message. This differs from multiple consumers reading the same queue.

### 2.3 Non-durable subscription

A non-durable subscription exists while the consumer/subscription is active. When the consumer closes, the subscription is destroyed. Publications emitted while the subscriber is offline are not retained for that subscription.

Use a non-durable subscription when the application only needs events while running and can tolerate missing events while offline, or when the application has its own state synchronization mechanism after reconnecting.

### 2.4 Durable subscription

A durable subscription is recorded by the broker as a subscription with a stable identity. When the consumer stops, the broker can retain matching messages for delivery when the consumer re-subscribes to the same durable subscription, subject to retention, expiration, quotas, and policies.

Durable subscriptions fit when a subscriber needs to catch up on publications emitted during temporary offline periods. It does not mean messages are kept forever or guaranteed delivery if the broker runs out of space, messages exceed TTL, or the subscription is deleted.

## 3. clientID and Subscription Name

### 3.1 clientID is the JMS client identifier

clientID is an attribute of a JMS connection or JMSContext. It is typically set before the connection is used to create consumers or start receiving messages.

For an unshared durable subscription, client identifier and subscription name combine to identify the subscription. Therefore, the application must keep clientID stable across restarts if it wants to continue using the same subscription.

A clientID currently in use by another connection generally cannot be claimed simultaneously by a second connection. Exact rules and uniqueness scope are enforced by the provider; check the documentation of the broker in use.

clientID is not a username, password, or end-user identity. Connection authentication still uses credentials or provider security mechanisms. Do not use clientID as an authorization mechanism.

### 3.2 subscription name is the logical name of the subscription

Subscription name is the application-assigned name for a durable subscription. It should:

- Remain stable across deployments if resuming the old subscription.
- Be meaningful for the receiving purpose, e.g., `orders-projection-v1`.
- Not change arbitrarily on every startup.
- Be managed as part of deployment configuration.

Changing the subscription name typically means creating a different durable subscription. The old subscription may remain on the broker along with its backlog until unsubscribed or removed by an administrator per broker policy.

### 3.3 Distinguishing the three names

| Value | Meaning | Example |
|---|---|---|
| Destination/topic name | Where publishers send publications | `orders.events` |
| clientID | JMS client/connection identifier | `orders-projection-node-01` |
| Subscription name | Logical identity of the durable subscription | `orders-projection-v1` |

Do not use the destination as the subscription name. One topic can have multiple durable subscriptions with different purposes and receiving states.

## 4. Creating a Durable Subscription with JMS 2.0

JMS 2.0 provides the `JMSContext` and `JMSConsumer` APIs. For an unshared durable topic consumer, you can create a consumer via `createDurableConsumer`.

The example below illustrates the basic lifecycle. `ConnectionFactory` is supplied by the JMS provider or Spring configuration; the example requires the Jakarta Messaging API dependency and the corresponding broker implementation.

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSConsumer;
import jakarta.jms.Message;
import jakarta.jms.Topic;

public class DurableTopicReceiver {

    public void receiveOne(ConnectionFactory connectionFactory) {
        try (JMSContext context = connectionFactory.createContext()) {
            // Set clientID before creating consumers or starting delivery.
            context.setClientID("orders-projection-node-01");

            Topic topic = context.createTopic("orders.events");

            try (JMSConsumer consumer = context.createDurableConsumer(
                    topic,
                    "orders-projection-v1")) {

                context.start();

                Message message = consumer.receive(1_000);

                if (message == null) {
                    System.out.println("No message within timeout");
                    return;
                }

                System.out.println("Received a durable topic message");
            }
        }
    }
}
~~~

Execution flow:

1. Create JMSContext from ConnectionFactory.
2. Set clientID before creating the durable consumer.
3. Create or reconnect the durable subscription with the topic and subscription name.
4. Start receiving messages.
5. Close consumer and context when finished.

Closing consumer/context terminates the active consumer. With a durable subscription, closing the consumer does not delete the subscription on the broker. The subscription can continue existing to capture publications while the client is offline.

The example uses the `jakarta.jms` package, suited for Jakarta Messaging in modern Spring generations. Legacy Spring Framework 5 and older JMS projects may use the `javax.jms` package; do not mix the two namespaces in the same application.

## 5. Shared and Unshared Durable Subscriptions

JMS 2.0 added shared subscriptions so multiple consumers can consume from one subscription together.

### 5.1 Unshared durable subscription

An unshared durable subscription is designed for one active consumer at a time on that subscription. If multiple consumers attempt to open the same unshared durable subscription simultaneously, the provider may reject them.

This fits when one logical subscriber must receive all publications in a single stream, and the application enforces having only one active consumer for that subscription.

### 5.2 Shared durable subscription

A shared durable subscription allows multiple consumers to join a single durable subscription as supported by JMS 2.0 and the provider. Within the consumer group sharing the subscription, each message is distributed to one eligible consumer in the group rather than broadcasting copies to all consumers.

This can be used to scale processing capacity for a single subscription. However, verify how the provider supports shared durable subscriptions, clientID restrictions, selectors, ordering, and concurrency.

### 5.3 Do not confuse shared subscriptions with multiple separate subscriptions

Suppose there are three instances:

- If each instance uses its own clientID/subscription identity, they create separate durable subscriptions. Each subscription can receive a copy of every matching publication.
- If the instances join a single shared durable subscription, they compete to receive messages within that same subscription; each publication is delivered to one consumer in the group.

The two models serve different goals. Creating a separate subscription per replica does not automatically create competing consumers; it can cause every replica to process the same event.

## 6. Configuring a Durable Topic Listener in Spring JMS

Spring JMS provides listener containers to manage connections, sessions, consumers, and listener lifecycles. For annotation-driven listeners, you can configure a dedicated `DefaultJmsListenerContainerFactory` for durable topic subscriptions.

Example:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class DurableJmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory durableTopicListenerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setClientId("orders-projection-node-01");
        factory.setSubscriptionDurable(true);
        factory.setConcurrency("1");

        return factory;
    }
}
~~~

Listener:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    @JmsListener(
            destination = "orders.events",
            subscription = "orders-projection-v1",
            containerFactory = "durableTopicListenerFactory")
    public void handle(OrderEvent event) {
        // Invoke business service to update projection.
    }
}
~~~

Meaning of the settings:

- `setPubSubDomain(true)` configures the listener container for the topic model.
- `setClientId(...)` sets the client identifier used for the durable subscription.
- `setSubscriptionDurable(true)` requests a durable subscription.
- `subscription` in `@JmsListener` provides the subscription name.
- `setConcurrency("1")` keeps a single consumer for the unshared durable subscription in this example.

This is an illustrative configuration for an unshared durable listener. Each listener container using a clientID must be managed so it does not conflict with another active connection. Do not arbitrarily reuse the same clientID across multiple independent containers.

If a shared durable subscription is needed, use the shared subscription configuration supported by your Spring and JMS provider versions, and test against the real broker. Do not merely increase concurrency while ignoring shared/unshared semantics.

`OrderEvent` is an application DTO and requires appropriate message conversion configuration. The listener method should only invoke business services; clientID and subscription lifecycle belong to the infrastructure layer.

## 7. Consumer Lifecycle and Durable Subscription Lifecycle

Distinguish between the lifecycle of the running consumer and the lifecycle of the durable subscription stored by the broker.

### 7.1 Start

When the listener container starts, Spring creates or starts the required JMS resources, sets the configured clientID, creates the consumer, and begins receiving messages.

For a durable subscription, the broker locates the existing subscription or creates a new one if absent. Subscription name and client identity must be consistent to reconnect to the right subscription.

### 7.2 Stop

When the container stops, the consumer stops receiving messages and active consuming resources are halted according to the container lifecycle.

For a durable subscription, stopping the listener does not delete the subscription. The broker can continue retaining publications for the subscription while the subscriber is offline, per broker policies and limits.

This is useful during maintenance or redeployment: temporarily halt the consumer while preserving the subscription identity to resume after startup.

### 7.3 Close

Closing a JMSConsumer or JMSContext releases client resources. With a durable subscription, the subscription can remain on the broker after the consumer closes.

With a non-durable subscription, closing the consumer ends that temporary subscription.

### 7.4 Unsubscribe

Unsubscribing deletes the durable subscription from the broker. In JMS 2.0, `JMSContext.unsubscribe(subscriptionName)` provides the corresponding API; older JMS APIs provide `Session.unsubscribe(subscriptionName)`.

Only unsubscribe when the application genuinely wants to remove the subscription and its associated backlog. Providers usually require no active consumer on the subscription at unsubscribe time.

Unsubscribe is not a routine cleanup step on every application shutdown. Calling unsubscribe when you only want a restart can wipe out the backlog the broker retained for the subscriber.

## 8. Message Backlog While Consumer Is Offline

While a durable subscriber is offline, the broker can retain matching publications. When the consumer reconnects with the same subscription, the broker resumes delivering pending messages per policy.

Consider:

- **Message expiration / TTL:** expired messages may be discarded before the consumer returns.
- **Persistent delivery mode:** determines the durability level of message storage per provider.
- **Broker quota:** large backlogs can hit storage capacity limits.
- **Subscription selector:** only messages matching the selector are delivered to the subscription.
- **Acknowledgement:** delivered but unacknowledged messages can be redelivered per session/acknowledgement semantics.
- **Dead-letter policy:** unprocessable messages may be routed elsewhere per broker configuration.
- **Unsubscribe:** deleting the durable subscription can lose the subscription's backlog state.

A durable subscription does not itself guarantee all messages are always kept. Verify delivery mode, TTL, persistence, quotas, retention, and redelivery policies on the broker.

## 9. Multi-Instance Deployment and Avoiding clientID Conflicts

clientID should be managed as an infrastructure identifier with clear scope.

### 9.1 Single unshared durable subscriber

If there is only one logical consumer for the subscription, use a stable clientID and ensure no two connections simultaneously claim that clientID. During rolling updates, coordinate stopping the old instance's consumer before the new instance connects with the same identity if the provider does not permit takeover.

### 9.2 Each instance has its own subscription

If each instance uses its own clientID and its own subscription name, each instance gets its own durable subscription. When a publisher emits a message to the topic, every matching separate subscription can receive a copy. This fits when each instance represents an independent subscriber system, but not when the goal is merely load sharing of the same work.

### 9.3 Shared durable subscription

If multiple consumers need to process one subscription together, use a shared durable subscription per JMS 2.0 and broker capabilities. Consumers join the same logical subscription and compete to receive messages.

Verify:
- The provider supports shared durable subscriptions.
- How the provider resolves client identity and subscription name.
- Whether there are limits on concurrent consumers.
- Within what scope ordering is guaranteed.
- How selectors and acknowledgements behave with multiple consumers.
- How the Spring listener container version in use configures shared subscriptions.

Do not assume scaling replicas or increasing concurrency automatically produces a valid shared subscription model.

## 10. Selectors and noLocal

Durable subscriptions can be scoped with a message selector to receive only messages with headers/properties matching a condition. Selectors must stay stable across reconnects; changing a selector may be rejected by the provider if the existing subscription was created with a different selector, or require unsubscribing and recreating the subscription per provider rules.

The JMS durable consumer API also offers a `noLocal` option to avoid receiving messages published from the same connection/client in cases supported by JMS. Understand provider and connection identity semantics before enabling it.

Selectors and noLocal are delivery filters. They do not replace authorization. Do not use selectors as a tenant or user access-control mechanism if the server has not verified routing data.

## 11. Acknowledgement, Redelivery, and Idempotency

When a consumer receives a message, acknowledgement and transactions determine when the broker considers the message processed. If the consumer fails before acknowledgement or the transaction rolls back, the message can be redelivered.

Therefore, listeners must handle repeated messages safely:

- Use a stable event ID or business key to identify messages.
- Record processing results inside an appropriate transaction.
- Design idempotent services.
- Distinguish transient retryable errors from invalid data that should go to a dead-letter queue.
- Monitor redelivery counts if provided by the provider.
- Do not treat durable subscriptions as an exactly-once guarantee for overall business logic.

Durability retains messages while a subscriber is offline. Acknowledgement/transactions control delivery. Idempotency protects side effects when a message is reprocessed. These are distinct layers of guarantees.

## 12. Lifecycle Testing

Write integration tests with a real JMS provider or appropriate Testcontainers to verify durable subscription semantics.

Key scenarios:

1. Create a durable subscription for the first time and receive publications.
2. Stop the consumer while keeping the subscription; publish messages while the consumer is offline.
3. Restart with the same clientID and subscription name; verify non-expired messages are received.
4. Start with a different clientID; verify the provider creates a separate identity or behaves as configured.
5. Attempt two connections with the same clientID and confirm the provider's conflict behavior.
6. Test shared durable subscriptions with multiple consumers if the system uses this mode.
7. Close the consumer and verify the durable subscription still exists.
8. Unsubscribe when no consumer is active and verify the subscription is deleted.
9. Test TTL expiration, selectors, and redelivery.
10. Verify shutdown/restart does not accidentally unsubscribe.

Unit tests for business services do not need a broker. However, lifecycle, durable identity, shared subscriptions, and backlogs are JMS provider behaviors, requiring integration tests on the target broker.

## 13. Common Pitfalls

- **Confusing clientID with subscription name:** one identifies the client connection, the other names the durable subscription.
- **Confusing subscription name with topic name:** a topic can have multiple subscriptions.
- **Changing clientID or subscription name on every restart:** can create a new subscription and leave the old subscription plus its backlog orphaned.
- **Using the same clientID for multiple concurrent connections:** the provider may reject the connection.
- **Using multiple separate subscriptions for load sharing:** each subscription can receive a copy of the same publication, causing every instance to process the same event.
- **Confusing shared durable with broadcast:** a shared subscription distributes messages across consumers; it does not send every message to every consumer in the group.
- **Assuming stop/close deletes a durable subscription:** the subscription usually persists until unsubscribed or removed by an administrator.
- **Unsubscribing when only a restart is intended:** can delete the subscription and its backlog.
- **Assuming durable retains messages forever:** TTL, quotas, persistence, and broker policies still apply.
- **Increasing concurrency on unshared durable:** can conflict with the single-active-consumer rule on the subscription.
- **Lacking idempotency:** redelivery can produce duplicate side effects.
- **Not testing on the real broker:** shared subscription and clientID semantics can vary across providers.

## 14. Operational Checklist

Before deploying a durable JMS listener, confirm:

- Is the destination a queue or a topic?
- Does the consumer need non-durable, unshared durable, or shared durable?
- Is clientID stable and not used concurrently by another connection?
- Is the subscription name stable and clearly versioned?
- Is the Spring listener container configured with the right pub-sub domain and durable subscription settings?
- Is concurrency compatible with shared/unshared mode?
- Do stop and close preserve the subscription when needed?
- Is unsubscribe only invoked when the subscription truly needs deletion?
- Have TTL, persistence, quotas, selectors, and dead-letter policies been checked?
- Is the listener idempotent and safe against redelivery?
- Do rolling deployments coordinate clientID to avoid conflicts?
- Have integration tests verified offline backlog, reconnect, shared mode, and unsubscribe on the target broker?

When clientID, subscription name, and lifecycle are managed properly, a Spring JMS application can preserve message-receiving state across restarts, avoid orphaned subscriptions, and scale consumers in line with provider semantics.