# Testing Rollback, Redelivery, Selectors, and Durable Subscriptions

## Objectives

After this lesson, you will be able to design integration tests for Spring JMS flows to prove that:

- Listeners execute inside a JMS transaction and messages are rolled back when processing fails.
- The broker redelivers messages after rollback; the application recognizes the redelivery attempt.
- Message selectors filter solely on JMS headers/properties without reading the message body.
- Durable topic subscriptions still receive messages sent while the consumer was offline.
- Tests do not confuse JMS rollback with database rollback and do not rely on arbitrary wait times.

The examples use Spring Framework 6+/Spring Boot 3+ and Jakarta Messaging (`jakarta.jms`). With Spring Framework 5 / Spring Boot 2, JMS APIs typically use the `javax.jms` package; do not mix the two package families in the same application.

## 1. Messaging Tests Require a Real Broker

JMS is a protocol and API for communicating with a messaging provider. Spring's `JmsTemplate`, `@JmsListener`, and listener containers are integration layers; they do not replace the broker. Therefore, unit tests that only mock `JmsTemplate` or invoke listeners directly cannot prove broker rollback, redelivery, selector, or durable subscription behavior.

Tests should be divided into three layers:

1. **Business handler unit tests:** verify payload processing logic, validation, idempotency, and business outcomes without a broker.
2. **Spring integration tests:** initialize the Spring context, listener container, and a real JMS provider; send messages and observe outcomes through the broker.
3. **Broker-specific tests:** verify retry delay, maximum delivery attempts, dead-letter queues, persistence across restarts, and provider-specific characteristics of ActiveMQ Artemis, IBM MQ, Azure Service Bus, or whichever provider is used.

Tests should use the same provider type as production when proving provider-specific behavior. Spring Boot can run embedded ActiveMQ Artemis with the appropriate server dependency and `spring.artemis.mode=embedded`; this is useful for fast tests. To verify persistence across broker restarts, failover, or cluster configurations, you need a broker with storage and topology matching production.

## 2. How Do Rollback and Redelivery Work?

With a JMS session configured for transactions, message reception proceeds as follows:

1. The broker delivers the message to the consumer.
2. The listener executes processing inside a JMS transaction.
3. If the listener completes normally, the container commits the transaction and the message is acknowledged.
4. If the listener throws an exception out of the method, the container rolls back the transaction.
5. The broker can redeliver the message; the redelivery attempt is marked with redelivery metadata.

In Jakarta Messaging, with a transacted session, commit handles acknowledgement; rollback recovers messages received within the transaction. The provider sets the `JMSRedelivered` header and increments `JMSXDeliveryCount` when redelivering a message.

### Enabling Transactions for the Listener Container

Configure `sessionTransacted=true` on the factory used by `@JmsListener`:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory transactedFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }
}
~~~

`DefaultJmsListenerContainerFactory` creates a `DefaultMessageListenerContainer`, suitable for most Spring listeners. `sessionTransacted=true` requires each message processing invocation to use a local JMS transaction. Setting concurrency to 1 in tests makes ordering and invocation counts easier to observe; production can use higher concurrency if logic and message ordering allow.

Example of a listener that intentionally fails on the first attempt:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.jms.JMSException;
import jakarta.jms.Message;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class RedeliveryProbe {

    final AtomicInteger attempts = new AtomicInteger();
    final AtomicReference<Boolean> redelivered = new AtomicReference<>();
    final AtomicInteger deliveryCount = new AtomicInteger(-1);
    final CountDownLatch completed = new CountDownLatch(1);

    @JmsListener(
        destination = "qa.rollback",
        containerFactory = "transactedFactory"
    )
    public void receive(Message message) throws JMSException {
        int attempt = attempts.incrementAndGet();

        if (attempt == 1) {
            throw new IllegalStateException("Simulated processing failure");
        }

        redelivered.set(message.getJMSRedelivered());

        if (message.propertyExists("JMSXDeliveryCount")) {
            deliveryCount.set(message.getIntProperty("JMSXDeliveryCount"));
        }

        completed.countDown();
    }
}
~~~

The exception must be thrown out of the listener for the transaction to roll back. If code catches the exception and only logs it without rethrowing, the container may treat processing as successful and commit the message.

### Integration Test Verifying Redelivery

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jms.core.JmsTemplate;

@SpringBootTest
class JmsRedeliveryIT {

    @Autowired
    JmsTemplate jmsTemplate;

    @Autowired
    RedeliveryProbe probe;

    @Test
    void rollsBackAndReceivesMessageAgain() throws Exception {
        jmsTemplate.convertAndSend("qa.rollback", "message-1");

        assertTrue(probe.completed.await(10, TimeUnit.SECONDS));
        assertEquals(2, probe.attempts.get());
        assertEquals(Boolean.TRUE, probe.redelivered.get());
        assertTrue(probe.deliveryCount.get() >= 2);
    }
}
~~~

This is an integration test that requires a running broker and the configuration beans above. Reset the probe before each test if the test class runs multiple times or shares a Spring context. The 10-second timeout is merely a test wait bound; choose a value appropriate for the CI environment, and do not use `Thread.sleep` to guess when the message will be redelivered.

`JMSRedelivered=true` indicates that the message has been delivered previously. `JMSXDeliveryCount` indicates the delivery count according to the provider. Tests should check an appropriate minimum count rather than assuming every broker has the same retry schedule or delay.

## 3. Rollback Does Not Mean Infinite Retries

Rollback returns the message to an unacknowledged state within the transaction; subsequent redelivery is coordinated by the broker. The broker may apply:

- Redelivery delay to prevent the listener from immediately receiving the message again.
- Increasing backoff between redelivery attempts.
- Maximum delivery attempts.
- Dead-letter address/queue after exceeding retry limits.
- Expiration or message-discard policies.

The JMS specification does not mandate a single retry schedule across all providers. Therefore, broker-specific configurations must be tested separately. With ActiveMQ Artemis, options are typically configured in `address-setting`, for example:

~~~xml
<address-setting match="orders">
    <redelivery-delay>1000</redelivery-delay>
    <max-delivery-attempts>5</max-delivery-attempts>
    <dead-letter-address>DLQ</dead-letter-address>
</address-setting>
~~~

This is ActiveMQ Artemis-specific configuration, not portable JMS configuration. Declare the DLQ address/queue and verify that the broker applies `address-setting` to the right address. After exceeding the maximum failed delivery attempts, the message is moved to the dead-letter address according to broker policy.

A message that consistently fails is called a poison message. Without a cap on redelivery attempts, it can monopolize consumers continuously, trigger log/error storms, and degrade throughput for other messages. Test both flows: a message processed successfully after redelivery, and a message routed to the DLQ after exceeding limits.

### Duplicate Delivery and Idempotency

Redelivery is part of the at-least-once delivery model. Applications must tolerate observing the same business event multiple times.

For example: a listener writes a record to the database and then the process terminates before the JMS transaction commits. The broker redelivers the message; the second attempt can create duplicate records if the application lacks deduplication.

Common safeguards include:

- Using a stable business key or event ID to identify messages.
- Storing an inbox/processed-message record with a unique constraint in the same database transaction as the business update.
- If the event was already processed, returning successfully so the JMS transaction commits without repeating side effects.
- Using an outbox to publish messages after the database transaction commits.
- If atomicity between database and JMS is required, considering XA/JTA with XA-capable resources while understanding operational overhead and provider limits.

`sessionTransacted=true` manages only the local JMS transaction. It does not automatically roll back independent JDBC/JPA transactions. Spring's `JmsTransactionManager` manages a single `ConnectionFactory`; it does not turn two separate resources (JMS and database) into a distributed transaction. Do not write a test that only verifies listener rollback and conclude that the database rolled back too.

## 4. Testing Message Selectors

A message selector is a filter expression based on JMS headers and message properties. Its syntax is a subset of SQL-92 conditional expressions. Selectors cannot access the message payload/body.

Example selector:

~~~sql
eventType = 'PAYMENT' AND priority >= 5
~~~

The consumer receives only messages whose `eventType` property is the string `PAYMENT` and numeric `priority` property is greater than or equal to 5.

### Attaching a Selector to @JmsListener

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class PaymentListener {

    @JmsListener(
        destination = "qa.events",
        selector = "eventType = 'PAYMENT' AND priority >= 5"
    )
    public void receive(String payload) {
        // Process payload converted by the converter.
    }
}
~~~

The selector is sent to the JMS provider when the consumer is created. The provider filters messages before delivering them to the listener; Spring does not download all messages and filter bodies itself.

### Sending Messages with Properties

~~~java
import org.springframework.jms.core.JmsTemplate;

public class EventPublisher {

    private final JmsTemplate jmsTemplate;

    public EventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publishPayment(String payload) {
        jmsTemplate.convertAndSend("qa.events", payload, message -> {
            message.setStringProperty("eventType", "PAYMENT");
            message.setIntProperty("priority", 7);
            return message;
        });
    }
}
~~~

This snippet uses a `MessagePostProcessor` to attach properties to the JMS message before sending. The selector sees only the properties set here, not fields inside a JSON payload string.

### Selector Tests Must Include Both Matching and Non-Matching Messages

A meaningful test should send at least three cases:

| Message | eventType | priority | Expected Outcome |
|---|---|---:|---|
| M1 | PAYMENT | 7 | Listener receives |
| M2 | PAYMENT | 2 | Listener ignores |
| M3 | ORDER | 9 | Listener ignores |

With a queue, messages not matching the selector remain in the queue and can be received by another consumer with a matching selector. With a topic, the selector is part of the subscription; only matching messages are added to that subscription. A subscriber with a selector does not receive all topic messages.

### Common Selector Mistakes

- Placing filter criteria in the JSON body and expecting the selector to read it: selectors cannot access the message body.
- Sending a property as a String while comparing it numerically: selectors do not automatically cast property types to the expected type.
- Misspelling property names or mismatched casing: property identifiers are case-sensitive.
- Comparing a non-existent property: its value is treated as NULL; the expression may evaluate to UNKNOWN rather than TRUE.
- Using double quotes for string literals: selectors use single quotes, e.g., `eventType = 'PAYMENT'`.
- Changing the selector while an old durable subscription still exists: this may cause the subscription to be rejected or replaced depending on state and provider.

To test a selector properly, assert both the listener invocation count and the received message contents. Do not only verify that a matching message was received, because that fails to catch cases where non-matching messages are also delivered.

## 5. Durable Subscriptions for Topics

JMS has two primary models:

- **Queue (point-to-point):** messages are stored on the queue and distributed to a single eligible consumer. Queues do not use durable subscriptions.
- **Topic (publish/subscribe):** messages are distributed per subscription. Each subscription gets its own logical copy.

A non-durable subscription exists only while the consumer is active; when the consumer closes, the subscription and its pending messages may be discarded. A durable subscription is persisted by the broker and continues accumulating messages while no consumer is connected, until messages are received/acknowledged, expire, or the subscription is removed per policy.

Durable subscriptions do not mean every message is kept forever. Delivery mode, message expiration, broker persistence, storage limits, quotas, and subscription administration policies must be considered.

### Configuring a Durable Topic Listener in Spring

For an unshared durable subscription, configure the topic domain, a stable client ID, and a stable subscription name:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class DurableTopicConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory durableTopicFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setClientId("billing-consumer");
        factory.setSubscriptionDurable(true);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }
}
~~~

The listener declares the subscription name and selector:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class BillingEventsListener {

    @JmsListener(
        id = "billingEventsSubscription",
        destination = "billing.events",
        subscription = "billing-events-v1",
        selector = "eventType = 'BILLING'",
        containerFactory = "durableTopicFactory"
    )
    public void receive(String payload) {
        // Process billing event.
    }
}
~~~

In this example:

- `setPubSubDomain(true)` selects topic mode instead of queue mode.
- `setClientId(...)` sets the JMS connection's client identifier. The value must remain stable across restarts for the same subscription and be unique per broker rules.
- `setSubscriptionDurable(true)` enables durable subscriptions.
- `subscription = "billing-events-v1"` specifies the subscription name.
- `selector` filters messages by JMS properties.
- `concurrency = "1"` suits an unshared durable subscription, allowing only one active consumer at a time.

Topic name, client ID, subscription name, and selector must remain consistent when reconnecting to an existing subscription. If deploying multiple instances consuming the same subscription, use a shared durable subscription and verify that the broker supports JMS 2.0/Jakarta Messaging accordingly. In a Spring factory, you can configure `setSubscriptionShared(true)`; then each message on the subscription is delivered to one consumer in the group rather than broadcast to all consumers.

### Selectors Are Part of a Durable Subscription

With a durable subscription, the selector is not just a temporary filter for a single listener run. The provider stores the selector alongside the subscription. When creating a new consumer on an existing subscription, the client must use the same topic, subscription name, client ID (if set), and selector.

Jakarta Messaging specifies that if an unshared durable subscription has no active consumer and the application recreates it with the same name/client ID but a different topic, selector, or `noLocal`, that operation is equivalent to unsubscribing the old subscription and creating a new one. This can drop pending backlog. If you need to change a selector while preserving old messages, design an explicit migration—for example, create a new versioned subscription name, move consumers over, and drain the old backlog before deleting the old subscription.

## 6. Testing Durable Subscriptions While the Consumer Is Offline

A proper test must prove that messages published while no consumer is active are still received once the consumer returns.

Test flow:

1. Start the broker and the durable listener with a predefined client ID, subscription name, topic, and selector.
2. Verify the broker has created the subscription. Checking only that the Spring context started or a bean exists is insufficient; verify subscription state via the broker management API/JMX or a meaningful readiness signal.
3. Stop the listener container so the consumer becomes inactive, while keeping the broker running and without unsubscribing the durable subscription.
4. Publish a message with properties matching the selector to the topic, using PERSISTENT delivery mode if also testing durable message storage.
5. Publish another message that does not match the selector.
6. Restart the listener using the same client ID, subscription name, topic, and selector.
7. Wait using a bounded-timeout latch/queue and verify that only the matching message is received.
8. Verify the backlog is acknowledged; if the listener fails, verify the message is redelivered per transaction/policy.

You can control the container via `JmsListenerEndpointRegistry`:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;

MessageListenerContainer container =
    registry.getListenerContainer("billingEventsSubscription");

container.stop();
// Publish message while consumer is offline and broker remains running.
container.start();
~~~

This is a snippet for controlling the listener container and requires injecting `JmsListenerEndpointRegistry` and `JmsTemplate` in the test. Before publishing, verify that the subscription was created and the consumer has completely stopped. After starting, use a `CountDownLatch`, `BlockingQueue`, or Awaitility to wait for messages rather than a fixed `Thread.sleep`.

To test that a durable subscription survives a broker restart, real broker persistence must be enabled and messages must use an appropriate delivery mode. A test that merely stops and restarts the listener container within the same broker process proves consumer offline recovery; it does not yet prove recovery after the broker process or host shuts down.

### What to Verify When Testing Durable Subscriptions

- Messages published before the subscription is created are not automatically replayed to the newly created subscription.
- Only messages sent while the durable subscription is inactive accumulate for that subscription.
- Messages that do not match the selector are not added to the subscription.
- Persistent messages and broker storage must be configured if survival across broker restarts is required.
- Messages with expiration may expire before the consumer returns.
- Broker quotas or policies may limit backlog size.
- Unsubscribing deletes the durable subscription; do not call unsubscribe in routine cleanup if a test needs to keep the subscription for a subsequent check.
- The same unshared durable subscription cannot have two simultaneously active consumers.

## 7. Combining Rollback, Selectors, and Durable Subscriptions in One Test Plan

These behaviors are independent, yet they can appear together on a single listener. Separate tests so failures are easy to diagnose:

| Test | Setup | Action | Assertion |
|---|---|---|---|
| Rollback | Transacted listener factory | Listener throws exception on first attempt | Next attempt receives same message; `JMSRedelivered=true` |
| Redelivery limit | Broker with max attempts and DLQ | Listener always throws exception | Message eventually appears in DLQ |
| Selector match | Consumer with selector | Send matching properties | Listener receives message |
| Selector mismatch | Consumer with selector | Send non-matching properties | Listener does not receive message |
| Durable offline | Subscription already created | Stop consumer, publish topic message, restart | Consumer receives backlog |
| Durable selector | Durable subscription with selector | Publish one matching and one non-matching message while offline | Only matching message is retained for subscription |
| Durable identity | Existing subscription | Reconnect using same identity | Consumer continues consuming backlog |
| Selector migration | Old durable subscription inactive | Create consumer with same identity but different selector | Test verifies provider behavior; migration uses new subscription name if backlog must be kept |

Each test should use its own destination and subscription name so messages from an earlier test do not affect a later test. When sharing a broker/context, cleanup must remove temporary queues and manage durable subscriptions intentionally.

## 8. Observing and Diagnosing Test Failures

When a redelivery test times out, check in order:

1. Is the listener's factory actually using `sessionTransacted=true`?
2. Does the annotation reference the right `containerFactory`?
3. Does the listener throw the exception out of the method?
4. Did the broker receive the rollback and increment the delivery count?
5. Does the broker have a redelivery delay longer than the test timeout?
6. Did the message expire or move to the DLQ before the test received it again?
7. Is the test using the same broker, destination, and transaction configuration as the listener?

When a selector test receives the wrong messages:

1. Verify the property is set on the JMS message, not only inside the JSON body.
2. Verify the property type (String, integer, boolean) matches the expression.
3. Check property names and single quotes around string literals.
4. Inspect the actual selector on the listener container, not just in the source annotation.
5. Check whether the destination is a queue or a topic to understand where non-matching messages remain.

When a durable test fails to receive its backlog:

1. Verify the subscription was created before the consumer stopped.
2. Verify the destination is a topic.
3. Check whether client ID, subscription name, selector, and `noLocal` match the original subscription.
4. Verify the broker did not auto-unsubscribe when the container stopped or test cleanup ran.
5. Check that messages have not expired and delivery mode/storage are configured properly.
6. Inspect broker management tools to confirm whether the backlog actually exists.

Logs should record message ID, correlation ID, delivery count, redelivered flag, destination, consumer ID, and processing outcome. Avoid logging full sensitive payloads. Metrics should track redelivery counts, DLQ message counts, selector mismatches if supported by the broker, inactive subscription counts, and backlog depth.

## 9. Common Mistakes

- **Mocking the broker and concluding rollback works:** mocks do not execute JMS transaction or redelivery semantics.
- **Using AUTO_ACKNOWLEDGE for listeners requiring reliability:** Spring warns that listener errors may cause messages to be acknowledged and lost.
- **Catching exceptions without rethrowing:** the container may commit instead of rolling back.
- **Assuming JMS rollback automatically rolls back the database:** local JMS transactions and JDBC/JPA transactions are two separate resources.
- **Not bounding redeliveries:** poison messages can loop indefinitely; backoff and a DLQ are required.
- **Only asserting the listener was called twice:** verify the message was actually redelivered via `JMSRedelivered` or `JMSXDeliveryCount`.
- **Using selectors to inspect JSON bodies:** selectors read only headers/properties.
- **Sending properties with the wrong type:** numeric expressions will not evaluate as intended if the property is sent as a string.
- **Using durable subscriptions on queues:** durable subscriptions are a topic feature.
- **Changing client ID or subscription name across runs:** the provider may create a different subscription or reject the connection.
- **Changing the selector of an existing durable subscription:** this can replace the old subscription and lose the backlog.
- **Testing durability by restarting the listener without verifying the subscription:** the test might pass due to a new subscription or messages sitting on a different queue.
- **Assuming durable means stored forever:** message expiration, quotas, and broker storage policies still apply.

## 10. Pre-Merge Checklist

- [ ] Integration tests run against a real JMS provider, not just mocks.
- [ ] Listener factory sets `sessionTransacted=true` for flows requiring rollback.
- [ ] Tests trigger an exception on the first attempt and verify redelivery.
- [ ] Tests verify `JMSRedelivered` and/or `JMSXDeliveryCount`.
- [ ] Broker has appropriate redelivery delay, maximum attempts, and DLQ settings.
- [ ] Listeners handle duplicates safely using idempotency/inbox patterns.
- [ ] Selectors use only headers/properties; tests include both matches and mismatches.
- [ ] Property types and names are checked accurately.
- [ ] Durable subscriptions use stable topic, client ID, name, and selector.
- [ ] Tests publish while the consumer is offline after the subscription has been created.
- [ ] Tests verify the backlog is received and non-matching messages are excluded from the subscription.
- [ ] Separate tests cover broker restarts if persistence across restarts is required.
- [ ] Cleanup does not accidentally unsubscribe subscriptions that need to be retained.
- [ ] Tests use timeouts/latches instead of arbitrary sleeps.
- [ ] Logs/metrics are sufficient to investigate redeliveries and DLQs.

## References

- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): listener containers, transactions, and acknowledgment.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): synchronous receive and message-driven POJOs.
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, factories, and endpoint registry.
- [Spring Framework — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): configuring listener containers.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): transactions, acknowledgement, selectors, redelivery, and durable subscriptions.
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): integration example with `JmsTemplate`, `@JmsListener`, and embedded Artemis.
- [ActiveMQ Artemis — Documentation](https://activemq.apache.org/components/artemis/documentation/): redelivery delay, maximum delivery attempts, and dead-letter addresses.
