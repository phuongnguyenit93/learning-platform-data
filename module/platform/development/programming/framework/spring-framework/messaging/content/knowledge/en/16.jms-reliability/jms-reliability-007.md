# Message and Subscription Durability When the Receiver Disconnects

In JMS, a receiver temporarily disconnecting does not automatically cause every message to be retained. The outcome depends on the destination type, the subscription, the message's delivery mode, and how the consumer acknowledges processing.

There are two situations to distinguish:

- **Queue:** a queue is where messages are stored in the point-to-point model. A queue can hold messages while no consumer is connected; each message is delivered to one consumer.
- **Topic:** each subscription receives a copy of the message. A non-durable subscription only exists while the consumer is active. To retain messages published while a subscriber is offline, you must create a durable subscription.

In addition, the PERSISTENT delivery mode and a durable subscription are two separate mechanisms. PERSISTENT asks the provider to store the message durably per the JMS contract; a durable subscription retains the registration state and backlog of a subscriber on a topic. Enabling only one of the two is not enough for every disconnection scenario.

## 1. Understanding queue, topic, consumer, and subscription correctly

### 1.1. A queue holds messages for a consumer that is not ready

In the queue model, the producer sends a message to a destination. A consumer can receive messages while it is active. If there is currently no consumer, the queue can still hold the message until the next connection.

If multiple consumers read the same queue, each message is delivered to one consumer. The broker distributes work among the consumers by the provider's mechanism; JMS does not specify a particular load-balancing algorithm.

A queue is suitable when a job only needs to be processed once by one worker in a group, for example:

- Order processing.
- Sending email or creating invoices.
- Generating background reports.
- Performing a task that needs a retry when a worker fails.

A queue does not need a durable subscription. The durability of messages on a queue depends on the delivery mode, acknowledgement/transaction, expiration, and the broker's storage configuration.

### 1.2. A topic creates one copy per subscription

In the publish-subscribe model, the producer sends a message to a topic. A consumer does not read directly from a shared queue; it receives messages through a subscription.

Each matching subscription receives its own copy of the message. When one subscriber processes or acknowledges its copy, that does not acknowledge the copy in another subscription.

For example, the topic orders.events has three subscribers:

- billing-service receives a copy to create invoices.
- analytics-service receives a copy to update metrics.
- notification-service receives a copy to send notifications.

If notification-service uses a non-durable subscription and has no active consumer when the event is published, there is no subscription to receive that copy. The other two subscribers can still receive the message normally.

### 1.3. Consumer differs from subscription

A consumer is the active message-receiving object in the application. A subscription is registration state managed by the JMS provider.

With a topic:

- A non-durable subscription is deleted when the last consumer closes.
- A durable subscription persists even when no consumer is connected.
- A new consumer can reopen an existing durable subscription and continue receiving the remaining backlog.

Distinguishing these two concepts helps explain why closing a listener container does not necessarily delete a durable subscription.

## 2. Delivery mode: PERSISTENT and NON_PERSISTENT

The delivery mode describes the level of durability the producer requests for each message.

| Delivery mode | Meaning | Trade-off |
|---|---|---|
| PERSISTENT | The provider must apply durable storage per the JMS contract | Costs more storage resources and I/O |
| NON_PERSISTENT | The provider may use a lighter delivery approach, and the message may be lost if the provider fails | Usually lower overhead |

According to Jakarta Messaging, a provider must deliver PERSISTENT messages with once-and-only-once semantics at the provider level; NON_PERSISTENT messages have at-most-once semantics. However, these semantics have important exceptions such as expiration, resource limits, and an administrator deleting messages.

PERSISTENT does not mean every consumer will definitely receive the message. If a topic only has non-durable subscriptions, a message published while no subscription is active can still be missed.

### 2.1. Configuring delivery mode in Spring

JmsTemplate has a deliveryMode property, but for the template to pass the QoS it configures into the send call, you need to enable explicitQosEnabled.

~~~java
@Bean
public JmsTemplate persistentQueueTemplate(
        ConnectionFactory connectionFactory) {

    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setExplicitQosEnabled(true);
    template.setDeliveryMode(DeliveryMode.PERSISTENT);
    template.setTimeToLive(0L);

    return template;
}
~~~

In the example:

- DeliveryMode.PERSISTENT requests durable storage of the message.
- A time-to-live of 0 means the message has no expiry due to the TTL of this send.
- explicitQosEnabled ensures JmsTemplate uses the configured QoS values instead of relying only on the provider's defaults.

If you use a destination name for a topic, JmsTemplate must be configured with pubSubDomain=true or receive a Destination object representing the topic. Do not mistakenly use a queue template to resolve a topic name.

### 2.2. Expiration can still remove messages

A message may expire before the consumer returns. A TTL greater than 0 sets a limit on how long the message is kept for delivery.

For example, a message with a 10-minute TTL may expire while the service is offline for 30 minutes. A durable subscription does not turn an expired message into one that is kept indefinitely.

Choose the TTL according to business requirements:

- An event that is still valuable when processed late: a long or no-expiry TTL, while monitoring the backlog.
- Status information useful only for a short time: a short TTL.
- A stale command that is no longer safe to execute: needs expiration or an effective-time check at the consumer.

## 3. Durable and non-durable topic subscriptions

### 3.1. Non-durable subscription

A non-durable subscription only exists while the consumer is active. When the consumer closes, the subscription is deleted along with that subscription's undelivered messages.

This is a suitable choice when:

- The subscriber only needs new data while it is online.
- State can be retrieved through another API or snapshot.
- Losing some events while the application is stopped does not cause business discrepancies.
- The application does not want to maintain a separate backlog for each subscriber.

For example, a dashboard showing real-time metrics may not need a durable subscription if, when the dashboard reopens, the client loads the current snapshot from an API.

### 3.2. Durable subscription

A durable subscription is stored by the provider and continues accumulating messages for the subscription even when no consumer is active.

When the application reconnects using the same subscription identity, the new consumer continues to receive the messages retained during the offline period, provided the messages have not been acknowledged, have not expired, and have not been removed by the broker's administrative/resource policy.

A durable subscription must be created before the messages you want to receive are published. A durable subscription is not a mechanism to replay the entire history of a topic from its inception. It receives matching messages published after the subscription already exists.

### 3.3. Comparison

| Characteristic | Non-durable | Durable |
|---|---|---|
| Subscription exists when the consumer closes | No | Yes |
| Receives messages published while offline | Not guaranteed | Yes, if the subscription already exists and the message is still valid |
| Stores a separate backlog for the subscriber | No | Yes |
| Needs a stable subscription name | No | Yes |
| Needs a client ID | Not required for non-durable unshared | Required for durable unshared; shared durable may not need one |
| Broker cost | Lower | Higher due to retained state and backlog |
| Suitable for | Real-time data that can be missed | Events that must be processed after the subscriber returns |

A durable subscription can build up a large backlog if the subscriber is offline for a long time or processes slowly. You need to monitor storage size, the number of pending messages, the consumption rate, and the expiration policy.

## 4. How do PERSISTENT and durable subscription work together?

The two mechanisms solve two different layers of the problem:

- The delivery mode determines how the provider handles the durability of a single message.
- A durable subscription determines whether the provider maintains a copy of the message for a subscriber when the consumer is not active.

The following table describes the common outcomes when the subscriber is offline or the provider restarts:

| Destination / subscription | PERSISTENT message | NON_PERSISTENT message |
|---|---|---|
| Queue | The queue holds the message awaiting a consumer; the provider must apply durable semantics | May be kept while the broker is up but may be lost if the provider fails |
| Topic, non-durable subscription | There is no active subscription to receive a copy during the offline period; the message is missed | Missed while offline and may be lost if the provider fails |
| Topic, durable subscription | The backlog is kept while the subscription is inactive until acknowledged or expired | Not guaranteed if the subscription is inactive or the provider shuts down/restarts |

For an important event on a topic, the configuration usually needs both PERSISTENT and a durable subscription. For a queue, use PERSISTENT to ask the provider to store the message durably; a queue already exists independently of consumers.

Do not infer that enabling PERSISTENT on the producer will automatically create a subscription for every service. Each subscriber needs its own durable subscription if it needs to receive events while offline.

## 5. Durable subscription identity

### 5.1. Durable unshared: client ID and subscription name

A durable unshared subscription is identified by:

- The JMS Connection's client ID.
- The subscription name.

The client ID must be set and must be unique among the active Connections on the same provider. When the application restarts to continue the subscription, it must reuse the same client ID and subscription name.

Example:

~~~text
clientId          = billing-service-client
subscriptionName  = billing-events-v1
topic             = billing.events
~~~

If you change the client ID or the subscription name, JMS may treat it as a different subscription. The new consumer then does not automatically receive the backlog belonging to the old subscription.

### 5.2. A durable unshared subscription has only one active consumer

A durable unshared subscription allows only one active consumer at a time. If two application instances open the same subscription with the same client ID and subscription name, creating the second consumer is not valid.

This affects multi-replica deployments:

- Use durable unshared when you want one active consumer and the remaining instances serve only as failover.
- Use shared durable when you want multiple consumers to share one subscription, if the provider supports JMS 2.0 or later.

Do not set concurrency greater than 1 for a durable unshared subscription. If you need parallel scaling, consider a shared durable subscription or split into multiple independent subscriptions by business design.

### 5.3. Shared durable subscription

A shared durable subscription still retains the backlog when there is no consumer, but allows multiple consumers to read one subscription. Each message of the subscription is delivered to one consumer in the group; not every consumer receives its own copy.

Shared durable subscriptions are supported since JMS 2.0. The identity is the subscription name and an optional client ID. If a client ID is used when creating the subscription, subsequent consumers must use the same client ID.

For multi-instance deployments, check how the provider manages client IDs and shared subscriptions. Do not configure the same client ID on multiple active JMS Connections if the provider requires a unique client ID per connection. A common deployment approach is to use a shared durable subscription with a stable subscription name and not set a client ID if the provider allows.

## 6. Configuring a durable topic listener with Spring Framework

Spring JMS provides DefaultJmsListenerContainerFactory to configure the listener container. The default factory creates a DefaultMessageListenerContainer, which suits most applications that need connection recovery and consumer tuning.

Example of creating a durable unshared topic listener:

~~~java
@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory durableTopicFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSubscriptionDurable(true);
        factory.setClientId("billing-service-client");
        factory.setSessionTransacted(true);

        return factory;
    }
}
~~~

A listener using a stable subscription name:

~~~java
@Component
public class BillingEventListener {

    @JmsListener(
            destination = "billing.events",
            subscription = "billing-events-v1",
            containerFactory = "durableTopicFactory"
    )
    public void receive(BillingEvent event) {
        billingService.process(event);
    }
}
~~~

Key configurations:

- pubSubDomain=true indicates the listener receives from a topic.
- subscriptionDurable=true enables a durable subscription.
- clientId sets the client identity for a durable unshared subscription.
- subscription in @JmsListener is the subscription name.
- sessionTransacted=true uses a JMS transaction for receiving and processing the message.

In Spring Framework, enabling a durable subscription also switches the listener container to the pub-sub domain. Explicitly setting pubSubDomain=true helps readers of the configuration clearly understand that the destination is a topic.

### 6.1. Creating a shared durable subscription

If the broker supports JMS 2.0 or later and you need multiple consumers to read one durable subscription, configure it as shared:

~~~java
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
    factory.setConcurrency("2-6");

    return factory;
}
~~~

Listener:

~~~java
@JmsListener(
        destination = "billing.events",
        subscription = "billing-events-workers",
        containerFactory = "sharedDurableTopicFactory"
)
public void receive(BillingEvent event) {
    billingService.process(event);
}
~~~

In this configuration, multiple consumers share the subscription's backlog. Each message is distributed to one consumer in the group. The specific concurrency also depends on the container and the JMS provider.

A shared durable subscription requires the provider to support the JMS 2.0 shared subscription API. Test this capability with the broker and client library in use; do not rely only on the Spring code compiling successfully.

## 7. Configuring a durable queue listener

A queue does not need a durable subscription. It only needs the queue destination to exist and the producer to send messages with a suitable delivery mode.

~~~java
@Bean
public DefaultJmsListenerContainerFactory queueListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);

    return factory;
}
~~~

Listener:

~~~java
@JmsListener(
        destination = "orders.queue",
        containerFactory = "queueListenerFactory"
)
public void receive(OrderCommand command) {
    orderService.process(command);
}
~~~

The producer can use a JmsTemplate with persistent QoS enabled as in the earlier section. When the consumer is offline, the queue continues to hold messages awaiting processing per the broker policy.

If the queue has multiple consumers, a message is delivered to only one consumer. Which consumer receives it depends on the broker and the state of the group; JMS does not specify a particular load-balancing algorithm.

## 8. Acknowledgement and transactions determine whether a message is deleted or redelivered

Storing a message durably is only one part of reliability. After the consumer receives a message, the provider needs to know whether the message has been processed and acknowledged.

Common modes:

- AUTO_ACKNOWLEDGE: the provider acknowledges automatically per the Session's semantics. This default configuration is not enough to guarantee reliability in every scenario where the listener fails or the container stops.
- CLIENT_ACKNOWLEDGE: the application acknowledges explicitly; you need to understand the scope of acknowledgement and the Session's recover behavior.
- Transacted Session: the consumer processes the message and then commits the transaction; if it rolls back, the message is not acknowledged and may be redelivered.

Spring recommends using a transacted Session for queue and durable topic subscription processing when reliability is needed.

### 8.1. Enabling transactions in the listener container

Example:

~~~java
factory.setSessionTransacted(true);
~~~

When the listener processes successfully, the container commits the JMS Session. If the listener throws an exception and the transaction is rolled back, the provider may redeliver the message.

Do not swallow the exception and return normally if you want a rollback. If you catch the exception to log it, rethrow it or proactively mark the transaction for rollback using the transaction mechanism in use.

### 8.2. Redelivery and repeated processing

A message may be redelivered when:

- The listener throws an exception and the transaction rolls back.
- The JVM stops before committing.
- The connection is lost during processing.
- The provider has not received a successful acknowledgement/commit.

JMS provides JMSRedelivered and JMSXDeliveryCount to help recognize redelivery. The number of retries before the provider moves the message to another state or stops delivering depends on the provider's configuration.

Therefore, the consumer should be idempotent. You can use a unique eventId and an inbox/processed_events table to ensure the same event does not produce a business effect twice.

Example logic:

~~~java
@Transactional
public void process(BillingEvent event) {
    if (processedEventRepository.existsByEventId(event.eventId())) {
        return;
    }

    billingService.apply(event);
    processedEventRepository.save(
            new ProcessedEvent(event.eventId())
    );
}
~~~

This example only guarantees idempotency when the check, the business update, and the event ID storage are within the same suitable database transaction. A unique constraint on eventId is needed to handle two concurrent receipts.

## 9. Reconnecting when the broker or consumer fails

When the consumer process stops or loses its connection, the result depends on the subscription and destination:

- A queue keeps messages while there is no consumer.
- A durable topic subscription continues to hold the backlog.
- A non-durable topic subscription is closed along with the consumer and does not retain messages published during the offline period.

Spring's DefaultMessageListenerContainer can recover when the broker goes down. By default the container retries the connection on a simple BackOff cycle of about 5 seconds; you can configure a custom BackOff for operational needs.

When the connection returns, the listener container re-registers the consumer. If the durable subscription is configured with the correct topic, client ID, and subscription name, the consumer continues reading the existing subscription.

The container's automatic reconnect does not replace a durable subscription. If a topic listener uses a non-durable subscription, the container can reconnect successfully but still not receive the events published while the subscription did not exist.

### 9.1. DMLC and SMLC

Spring has two common listener containers:

| Container | Characteristics | When suitable |
|---|---|---|
| DefaultMessageListenerContainer | Capable of recovery, consumer tuning, and participating in externally managed transactions | Most production applications |
| SimpleMessageListenerContainer | Creates a fixed number of consumers at startup and lets the provider perform callbacks | Simple scenarios, a fixed number of consumers, and a suitable provider |

DefaultMessageListenerContainer is usually a good choice when you need self-recovery after a broker outage. SimpleMessageListenerContainer still supports native JMS transactions, but does not support participating in an externally managed transaction the way DMLC does.

## 10. Deleting a durable subscription when no longer in use

A durable subscription continues to exist even when the application stops. Merely closing the consumer or stopping the listener container does not mean deleting the subscription.

To delete a durable subscription, JMS provides Session.unsubscribe(subscriptionName). For a durable unshared subscription, this operation must use the exact client ID tied to the subscription.

You cannot unsubscribe while the subscription still has an active consumer or has messages not yet acknowledged/in a transaction. Stop the consumer, ensure no processing is in progress, and then delete.

Do not delete a subscription just to handle a connection error. Deleting and recreating can lose the backlog the subscriber is waiting to receive.

If you change the topic, selector, or noLocal of an existing durable subscription, you need to understand the provider's semantics. In some cases of an inactive subscription, JMS treats this change as equivalent to deleting the old subscription and creating a new one. Treat the topic, selector, and subscription name as part of a contract that needs version management.

## 11. Storage limits and backlog

A durable subscription helps avoid missing events when a subscriber is offline, but the backlog must be stored at the broker. A slow subscriber or one offline for days can consume a significant amount of storage.

Metrics to monitor:

- The number of pending messages on each queue and durable subscription.
- Storage size and the rate of backlog growth.
- The age of the oldest message.
- Publish rate versus consume rate.
- The number of redeliveries and the number of messages entering the dead-letter queue.
- Connection state and the number of listener container recoveries.
- Messages that expire or are removed by the resource policy.

The broker may limit capacity, number of messages, or retention time. JMS does not define an infinite capacity. When resources run out, the provider may apply policies such as blocking the producer, rejecting, expiring, or dropping per vendor configuration.

Therefore, you need to combine durable subscriptions with a retention policy, TTL, backlog alerts, and a procedure for handling subscribers that have been inactive for a long time.

## 12. Illustrative scenario: subscriber offline for 30 minutes

Suppose the producer publishes events E1, E2, and E3 while billing-service is disconnected.

### Case A: Topic with a non-durable subscription

While billing-service is offline, the subscription is closed. E1, E2, and E3 are not stored for this subscriber. When the service restarts, it only receives events published after the new subscription is created.

### Case B: Topic with a durable subscription

The subscription billing-events-v1 still exists. The provider stores the matching messages during the consumer's offline period. When billing-service reconnects with the same client ID and subscription name, it receives E1, E2, and E3 if they have not expired and have not been removed by policy.

### Case C: Queue with persistent messages

The producer sends E1, E2, and E3 to the queue as PERSISTENT. The queue holds them while billing-service is offline. When the consumer returns, it receives the still-valid messages in the order and per the distribution rules of the broker.

### Case D: Durable topic but NON_PERSISTENT messages

The subscription exists, but NON_PERSISTENT messages are not guaranteed if the subscription is inactive or the provider shuts down/restarts. If an important event must survive a broker failure, use PERSISTENT.

## 13. Testing durability and recovery

Unit tests can only check the application logic. You need integration tests with a real JMS provider or a broker container to confirm storage, subscription, and redelivery behavior.

Tests should include:

1. Create a durable subscription, stop the consumer, publish a message, restart the consumer, and confirm the backlog is received.
2. Repeat the experiment with a non-durable subscription to show that messages published while offline are not kept for that subscriber.
3. Send a persistent message to a queue when there is no consumer, then start the consumer and receive the message.
4. Restart the broker while a persistent message is waiting, then check that the message still exists per the provider configuration.
5. Have the listener throw an exception in a transacted Session and confirm the message is redelivered.
6. Commit successfully and confirm the message is not redelivered as an unacknowledged message.
7. Check JMSRedelivered and JMSXDeliveryCount when redelivery occurs.
8. Check that the message TTL expires while the consumer is still offline.
9. Check that the durable subscription is not deleted when the listener container stops.
10. Check that unsubscribe only succeeds after the consumer has stopped and no messages remain in a transaction.
11. Check a shared durable subscription with multiple consumers and confirm each message is delivered to only one consumer in the group.
12. Check multiple instances opening the same durable unshared subscription to detect client ID/consumer conflicts.

A reconnect test should wait for the condition that the message is received instead of sleeping for a fixed period. Use a latch, polling with a timeout, or the test's synchronization mechanism to reduce flaky tests.

## 14. Common mistakes

### 14.1. Only setting the PERSISTENT delivery mode and thinking the topic is durable

PERSISTENT does not create a subscription. A topic needs a durable subscription if the subscriber must receive events published while offline.

### 14.2. Creating a durable subscription after the event has been published

A durable subscription does not automatically replay topic history. Only messages published after the subscription is created belong to the subscription's backlog.

### 14.3. Changing the client ID or subscription name on every restart

The provider treats this as a different identity. The new consumer may create a new backlog while the old backlog remains in the old subscription.

### 14.4. Using durable unshared with multiple concurrent consumers

A durable unshared subscription has only one active consumer. Use shared durable if you need multiple consumers on the same subscription and the broker supports JMS 2.0.

### 14.5. Using AUTO_ACKNOWLEDGE for important processing

A listener failure or a container stop can cause the message to be acknowledged too early. Use a transacted Session or a suitable acknowledgement strategy.

### 14.6. Not handling duplicates

Redelivery can cause the same event to be processed again. Use a stable event ID, an idempotent consumer, and a suitable unique constraint.

### 14.7. Not setting a TTL or not monitoring the backlog

A durable subscription can accumulate messages for a very long time. Without monitoring, the broker may run out of capacity, or messages that are too old may still be processed after they have lost meaning.

### 14.8. Deleting the subscription to fix a connection error

Deleting a subscription can delete the backlog. Check the client ID, subscription name, broker connection, and recovery before performing an unsubscribe operation.

### 14.9. Using the same client ID on multiple active Connections

The client ID must meet the provider's uniqueness rule. For multiple instances that need to share load, consider a shared durable subscription and a suitable client ID configuration.

### 14.10. Thinking JMS once-and-only-once guarantees an exactly-once business effect

The provider's guarantee does not by itself make a database update, an HTTP call, or an external side effect exactly-once. Use suitable transactions and idempotency at the business layer.

## 15. Design checklist

- Is the destination a queue or a topic?
- Does the queue exist independently of consumers?
- Does the topic subscriber need to receive events while offline?
- Has the durable subscription been created before publishing?
- Does the producer use PERSISTENT for important events?
- Is the TTL appropriate for the maximum offline time?
- Are the client ID and subscription name stable?
- Is durable unshared or shared durable appropriate for the number of consumers?
- Do the broker/client support JMS 2.0 if a shared subscription is used?
- Does the listener container use a transacted Session?
- Does the listener process idempotently when a message is redelivered?
- Are the backlog, oldest message age, expiry, and DLQ monitored?
- Are the recovery/backoff settings on broker outage appropriate?
- Is there a safe procedure to unsubscribe an old subscription?
- Do the integration tests simulate a consumer going offline, a broker restart, and redelivery?

## 16. References

- [Jakarta Messaging 3.1 Specification — Topic semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta Messaging 3.1 Specification — Durable subscriptions](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#consuming-messages)
- [Jakarta Messaging 3.1 Specification — Reliability](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework 6.1 — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.1.9/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework 6.1 — JmsListener Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework Reference — Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)

For a subscriber to receive events after being offline, design both the subscription and the message correctly: a queue holds messages for a consumer that is not ready; a topic needs a durable subscription to keep a copy for the subscriber; the producer uses PERSISTENT for important data; and the listener processes within a transaction and is idempotent so it can tolerate redelivery.