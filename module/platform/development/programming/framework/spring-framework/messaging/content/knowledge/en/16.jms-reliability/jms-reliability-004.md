# JMSRedelivered, Delivery Counts, and Repeatedly Failing (Poison) Messages

## Objectives

In JMS, a message can be delivered to a consumer without yet being acknowledged as complete. When a transaction rolls back, a session recovers, or the connection runs into trouble, the provider may deliver the message again. This phenomenon is called redelivery.

Jakarta Messaging provides two pieces of information that help a consumer recognize redelivery:

- `JMSRedelivered`: a boolean header set by the provider to report that the message is being redelivered.
- `JMSXDeliveryCount`: an integer property indicating how many times the provider has delivered the message.

When a message keeps failing because of an invalid payload or a fixed business error, it can become a poison message (a repeatedly failing message). If the consumer keeps rolling back and receiving it again indefinitely, a single message can hog resources, reduce throughput, and cause an error loop.

After this lesson, you can:

- Distinguish redelivery from a producer sending the same event twice.
- Read and interpret `JMSRedelivered` together with `JMSXDeliveryCount`.
- Understand acknowledgement, rollback, and the `sessionTransacted` configuration in Spring JMS.
- Classify transient errors and errors that cannot be fixed by retrying.
- Design bounded retry, a dead-letter queue (DLQ), quarantine, and idempotency.
- Monitor redelivery counts and investigate the messages causing failures.

## 1. What is redelivery?

Redelivery happens when the provider has delivered a message to a consumer but the message has not yet been acknowledged as complete. Depending on the acknowledgement mode and the transaction, the message can be delivered again after a rollback, a recover, or an incident that prevents the acknowledgement from completing.

Example with a Queue:

~~~text
orders.queue
     |
     v
Consumer receives OrderCreated
     |
     v
Processing fails
     |
     v
JMS transaction rollback
     |
     v
Broker redelivers the message
     |
     v
Consumer receives the same message again
~~~

Common causes:

- The listener throws an exception inside a JMS transaction and the container rolls back the session.
- The application calls `Session.rollback()` or `Session.recover()` according to the corresponding acknowledgement mode.
- The process or the connection fails before the acknowledgement is confirmed.
- The transaction commit fails after the business logic has already partly executed.
- The consumer is stopped while the message has not been acknowledged.

Redelivery does not mean the producer has sent a new message. It is usually another delivery attempt of a message that is already in the broker.

## 2. JMSRedelivered

`JMSRedelivered` is a boolean header in `jakarta.jms.Message`. The provider sets this header before delivering the message to the consumer.

~~~java
boolean redelivered = message.getJMSRedelivered();
~~~

Meaning:

- `false`: the provider does not mark the current delivery as a redelivery.
- `true`: the provider indicates the message is being redelivered; the consumer should guard against the possibility that earlier processing already ran but the acknowledgement did not complete.

According to Jakarta Messaging, when the provider redelivers a message, it generally must set `JMSRedelivered=true`. The value `true` indicates the message was likely delivered before and was not acknowledged; the header does not tell you the cause, the exception, or the previous consumer.

This header is managed by the provider. The application must not use `setJMSRedelivered()` to mark an outgoing message itself. The header has no meaning when set by the client at send time.

**Do not use this flag as the sole idempotency mechanism.** A business event may be resent by the producer as a new JMS message; the new message can have `JMSRedelivered=false` even though the same event was processed earlier. The consumer still needs a stable event ID and deduplication.

## 3. JMSXDeliveryCount

`JMSXDeliveryCount` is a standard property set by the provider when the message is received. In Jakarta Messaging 2.0 and later, this property is mandatory.

~~~java
int deliveryCount = message.getIntProperty("JMSXDeliveryCount");
~~~

Convention under Jakarta Messaging:

| Value | Meaning |
|---:|---|
| `1` | First delivery |
| `2` | The message has been redelivered at least once |
| `3` or more | The message has gone through multiple deliveries |

If `JMSRedelivered=true`, `JMSXDeliveryCount` must have a value of 2 or more.

This property is useful for detecting messages that are redelivered many times, logging and metrics, analyzing messages that tend to become poison messages, and supporting operational decisions when combined with the broker's retry policy.

### 3.1. Delivery count is not an absolute historical counter

Jakarta Messaging does not guarantee that `JMSXDeliveryCount` is always absolutely accurate. A provider is not required to record this value durably across every failure; after some kinds of failure or broker recovery, the count may not fully reflect every earlier delivery.

Therefore:

- Use the count to observe and to support retry decisions.
- Do not use the count as an exact number of business executions for billing or quotas.
- Do not use the count as proof that an event was never processed.
- Use an application event ID and an inbox table/unique constraint to protect the business logic from duplicates.

This property is set by the provider on receive. Jakarta Messaging does not define portable behavior when this property is used in a message selector; do not rely on a selector on the delivery count to build a retry limit. Configure maximum redelivery attempts with the broker's policy, or perform controlled quarantine.

## 4. How does redelivery differ from duplicate publication?

Two situations can produce the same business event multiple times but have different causes:

| Situation | Nature | Common signs |
|---|---|---|
| Redelivery | The broker redelivers a message because the previous delivery was not acknowledged | `JMSRedelivered=true`, count of 2 or more |
| Duplicate publication | The producer resends the same business event as a new message | The new message may have count = 1 and redelivered = false |
| Consumer processing repeated due to internal retry | The listener calls the business logic again by itself without receiving a new message | Delivery metadata may be unchanged |

`JMSMessageID` is issued by the provider for each message sent. If the producer retries by resending the payload, the new message may have a different `JMSMessageID`. Therefore, add a stable application event ID, for example `eventId`, to the payload or a property.

~~~java
jmsTemplate.convertAndSend(
    "orders.queue",
    orderCreated,
    message -> {
        message.setStringProperty("eventId", orderCreated.eventId());
        return message;
    }
);
~~~

If the producer resends the same event, it must keep the same `eventId`. The consumer uses that ID to recognize the same business operation even though the provider created a new message.

## 5. Acknowledgement and rollback determine redelivery

Redelivery depends on how the consumer acknowledges messages.

### 5.1. AUTO_ACKNOWLEDGE

With a Spring listener container, do not assume `AUTO_ACKNOWLEDGE` is reliable enough for business processing. The container's acknowledgement behavior can cause the message to be acknowledged before the listener completes. When the listener fails, the message may not be redelivered.

Spring warns that this default mode does not provide suitable reliability guarantees for listeners that need reliable processing. For those cases, use a transacted session.

### 5.2. CLIENT_ACKNOWLEDGE

In client acknowledgement mode, the application or the container acknowledges messages according to configuration. `Session.recover()` can request redelivery of unacknowledged messages.

Acknowledgement applies under the Session's semantics; it is not a transaction automatically coordinated with a database. Sending a response message and other operations on the Session also do not have the same atomic scope as a transacted Session.

### 5.3. Transacted JMS Session

With a Spring listener container, set `sessionTransacted=true` so each listener invocation runs in a local JMS transaction:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-6");
    return factory;
}
~~~

When the listener completes normally, the container commits the JMS transaction. When listener execution fails, Spring rolls back the receipt of the message; the broker may redeliver the message.

~~~text
Listener receives message in a JMS transaction
             |
             v
       Perform processing
          /       \
         /         \
      Success      Exception
         |            |
         v            v
      COMMIT        ROLLBACK
         |            |
         v            v
   Message is      Broker may
   acknowledged    redeliver message
~~~

This is a local JMS transaction. If the listener also updates a database, the database transaction is a separate resource unless the application uses XA/JTA. The database may have committed while the JMS transaction rolls back; therefore idempotency or an inbox/deduplication is needed.

## 6. Reading redelivery metadata in @JmsListener

If the method only receives the payload such as a `String` or a domain object, the code cannot directly access all the JMS headers and properties. When you need to read redelivery metadata, receive `jakarta.jms.Message`:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderProcessor processor;

    public OrderListener(OrderProcessor processor) {
        this.processor = processor;
    }

    @JmsListener(destination = "orders.queue")
    public void consume(Message message) {
        try {
            boolean redelivered = message.getJMSRedelivered();
            int deliveryCount = message.getIntProperty("JMSXDeliveryCount");
            String eventId = message.getStringProperty("eventId");

            if (!(message instanceof TextMessage textMessage)) {
                throw new IllegalArgumentException("Expected TextMessage");
            }

            String payload = textMessage.getText();

            System.out.printf(
                "eventId=%s redelivered=%s deliveryCount=%d%n",
                eventId, redelivered, deliveryCount
            );

            processor.process(eventId, payload);
        }
        catch (JMSException ex) {
            throw new IllegalStateException("Cannot inspect JMS message", ex);
        }
    }
}
~~~

This is an integration snippet within a Spring application; `OrderProcessor` is a business service. When `processor.process` throws a runtime exception, the exception is propagated so the container handles it according to the transaction policy. Do not catch the exception and merely log it and return if you want the broker to retry, because a normal return lets the container commit the message.

If you need to process an automatically converted payload, you can use a converter and a suitable method argument. However, keep a way to access the JMS `Message` when you need metadata set by the provider.

## 7. Spring ErrorHandler is not the broker's retry policy

A Spring listener container can be configured with an `ErrorHandler` to receive exceptions not otherwise handled during listener execution:

~~~java
factory.setErrorHandler(error ->
    System.err.println("JMS listener failed: " + error.getMessage())
);
~~~

`ErrorHandler` is useful for logging, alerts, and integration with error observation. It does not by itself define how many times the broker redelivers a message, the delay between deliveries, or the DLQ.

You need to distinguish three layers:

| Mechanism | Responsibility |
|---|---|
| Listener exception + transacted Session | Causes the message-receipt transaction to roll back |
| Spring `ErrorHandler` | Observes/handles exceptions not handled by the listener |
| Broker redelivery policy | Decides the number of redeliveries, the delay, and handling after attempts are exhausted |

A Spring listener container may catch an exception and log it instead of propagating the exception directly to the JMS provider. With a transacted session, the container still rolls back according to its listener-failure handling policy. Therefore, do not rely on the broker seeing a Java exception to decide on retry; configure the transaction and the broker policy explicitly.

## 8. Poison messages (repeatedly failing messages)

A poison message is a message that makes the consumer fail repeatedly each time it is delivered. The causes are usually fixed in nature:

- A payload with the wrong schema or missing required fields.
- An enum value or version that the consumer does not support.
- Referenced data that does not exist and cannot appear on its own.
- A message that exceeds the size limit or is of the wrong type.
- A business error that cannot be fixed by retrying.
- A bug in the code that makes the same message always trigger an exception.

If every exception causes a rollback, the broker may continuously redeliver the poison message. Consequences:

- One consumer keeps processing the same message.
- Valid messages behind it are slowed or starved, depending on the broker and concurrency.
- Logs and alerts repeat at high speed.
- CPU, the database, and downstream services are drained.
- The queue backlog grows and the processing time of valid messages lengthens.

Not every error is a poison message. A database timeout or a temporarily unavailable dependency can usually be fixed by retrying. An invalid payload or a fixed logic error usually needs quarantine or manual handling.

## 9. Classify errors before retrying

| Error type | Example | Suitable action |
|---|---|---|
| Transient | Flaky broker or database, HTTP 503, short timeout | Roll back and retry with a delay |
| Recoverable later | A referenced service is starting up, a resource is not yet ready | Bounded retry with backoff |
| Cannot be fixed by retrying | Malformed JSON, missing event ID, payload with the wrong schema | Move to quarantine/DLQ and alert |
| Programming error | Wrong null handling, mapping bug | Fix the code; limit redelivery so it does not loop indefinitely |
| Business duplicate | The event was already applied earlier | Deduplicate, then complete the message normally |

Do not retry every exception the same way. Retrying a permanent error only prolongs processing time and adds load. Conversely, sending a transient error to the DLQ too early can interrupt business processing unnecessarily.

## 10. Redelivery limits and the dead-letter queue

Jakarta Messaging does not standardize a common policy for:

- The maximum number of redeliveries.
- The delay or backoff between deliveries.
- The dead-letter queue and the name of the dead-letter destination.
- The rules for moving a message when attempts are exhausted.
- The policy for retaining, expiring, and replaying messages in the DLQ.

These policies depend on the JMS provider/broker. You need to configure them through the broker console, CLI, management API, or configuration file corresponding to the product in use.

A policy typically has these components:

1. Maximum delivery attempts: the maximum number of deliveries, by the broker's way of counting.
2. Redelivery delay: the wait before a redelivery.
3. Backoff: progressively increasing the wait on continuous failure.
4. Dead-letter destination: where the broker moves a message after attempts are exhausted.
5. Expiry/retention: how long messages are kept in the DLQ.
6. Alert/monitoring: alerting when the DLQ receives new messages or grows abnormally.

Check how the broker counts attempts: whether it counts the first delivery or only retries. Do not assume `JMSXDeliveryCount` and the broker's maximum attempts configuration always count the same way or always match exactly.

### 10.1. Dead-letter queue and quarantine

The DLQ is where messages that can no longer continue through the normal processing flow are held after the broker applies the redelivery policy. A quarantine queue can be a destination designed by the application or the operations team to hold messages that need inspection.

When moving a message to the DLQ/quarantine, you need to preserve metadata:

- The application event ID.
- The source destination.
- The time of the first and the most recent failure.
- The exception type or error code.
- The observed redelivery count.
- The consumer/service that processed it.
- The correlation ID or trace ID.

Do not write the full sensitive payload into logs unless necessary. The DLQ often contains real business data and needs suitable access control, retention, and auditing.

## 11. Safely moving a poison message to quarantine

There are two common approaches:

**Broker-managed dead lettering:** the broker automatically moves the message when the redelivery limit is reached. This is usually the easiest option to manage because the broker coordinates redelivery and moving to the DLQ according to policy.

**Application-managed quarantine:** the listener classifies a permanent error and then sends the message to a quarantine destination. If the application does this itself, sending the quarantine copy and acknowledging the original message must be coordinated safely. If the two operations are not in the same JMS transaction or a supported atomic mechanism, a crash midway can lose or duplicate the message.

A quarantine procedure should:

1. Determine that the error is permanent, not a transient infrastructure error.
2. Record the event ID, message ID, the necessary payload, and the error information.
3. Send the message to the quarantine destination or call a broker-supported dead-letter mechanism.
4. Only complete the original message after the quarantine operation is confirmed safe.
5. Create an alert so an operator can inspect, fix the data, or replay.

Do not catch the exception and return normally without saving/quarantining the message. In a transacted listener, a normal return can commit the receipt and remove the message from the retry flow.

## 12. Retry with backoff

Continuous retry without a delay can create a hot loop: the consumer receives a message, fails, rolls back, and receives it again immediately, repeating rapidly while the cause has not changed.

Backoff slows the retry rhythm. A commonly used strategy:

| Attempt | Example wait |
|---:|---:|
| 1 | 1 second |
| 2 | 2 seconds |
| 3 | 4 seconds |
| 4 | 8 seconds |
| 5 | Move to DLQ/quarantine per policy |

These values are only design examples, not JMS defaults. Configure them according to the SLA, the broker's load tolerance, and the dependency's expected recovery time.

**Distinguishing Spring BackOff from the message redelivery policy:** `DefaultMessageListenerContainer.setBackOff(...)` controls the wait between attempts by the container to recover a connection or set up a listener that failed. It does not by itself set the number of retries for a poison message. Message-level redelivery delay and maximum attempts are usually configured at the broker/provider.

## 13. Idempotency when a message is redelivered

A reliable listener must assume the same event may be processed multiple times. Redelivery can occur after the business logic has completed but the acknowledgement/commit has not.

Use a stable application event ID:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void apply(OrderCreated event) {
    boolean firstDelivery = inboxRepository.tryInsert(event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderProjection.apply(event);
}
~~~

This is a service fragment. `tryInsert` must rely on a unique constraint or an atomic insert-if-absent statement. Writing the inbox and updating the business data must be in the same database transaction.

If the same event arrives again:

- The inbox insert is rejected by the unique constraint or reports that it already exists.
- The listener skips the business effect that was already applied.
- The listener returns normally.
- The JMS transaction can commit so the message is not retried further.

Idempotency protects the business logic from redelivery and duplicate publication. It does not replace the retry policy or the DLQ; a permanently failing message still needs to be quarantined.

## 14. Distinguishing message-processing errors from broker connection errors

Spring's `DefaultMessageListenerContainer` has a recovery mechanism for when the connection or listener setup fails. You can configure a recovery interval or a `BackOff` to adjust how long the container waits before trying to reconnect.

This is a different kind of retry:

| Situation | Responsible component |
|---|---|
| The broker is down, the container cannot create a consumer | Spring listener container recovery |
| The listener processes a message and throws an exception in a transacted session | JMS rollback and broker redelivery |
| A repeatedly failing message exceeds the maximum attempts | Broker redelivery policy and DLQ |
| A business event is resent as a new message | Producer retry/idempotency |
| The same event is processed again after redelivery | Consumer inbox/deduplication |

In operations, do not increase the connection-recovery BackOff to handle a poison message. The two mechanisms have different triggers and purposes.

## 15. Observing and investigating redelivery

You should record the following fields when the listener starts processing:

- `JMSMessageID`: the ID the provider issued for the message.
- `JMSCorrelationID`: the ID linking request/reply or a business flow.
- `JMSRedelivered`: the redelivery flag.
- `JMSXDeliveryCount`: the delivery count reported by the provider.
- `eventId`: the stable ID generated by the application.
- The destination and the consumer/service.
- Processing time, result, and error code.

Metrics to track:

- The total number of messages received.
- The rate of redelivered messages.
- The distribution of `JMSXDeliveryCount`.
- The number of messages in the DLQ/quarantine.
- The age of the oldest message.
- The processing success/failure rate.
- The number of rollbacks per listener.
- The number of broker connection recoveries.

Alert when the delivery count rises abnormally, new messages appear in the DLQ, or one event ID repeats continuously. Logs should carry the correlation ID so the producer, the consumer, and the attempts can be linked.

## 16. Common mistakes

- **Only reading `JMSRedelivered` and assuming duplicates are prevented:** the flag only reports redelivery; the producer can still resend the same event as a new message.
- **Using `JMSXDeliveryCount` as the event ID:** the delivery count is not unique and may not be absolutely accurate after a failure.
- **Assuming a count of 2 means the listener definitely processed the business logic:** it only says the provider delivered the message multiple times; it does not prove that the earlier processing committed.
- **Assuming count = 1 proves the event was never processed:** the producer may send the same event as a new message.
- **Using AUTO_ACKNOWLEDGE for a listener that needs reliability without checking the container semantics:** the message may be acknowledged before listener execution.
- **Catching the exception and returning normally when you want a retry:** the container may commit the message.
- **Infinite retry on a permanent payload error:** creates a poison-message loop and grows the backlog.
- **Moving to the DLQ immediately on a transient timeout error:** the message may be removed from the processing flow even though the dependency would soon recover.
- **Assuming Spring `setBackOff` is the maximum message retry:** it serves listener container recovery, not the broker delivery policy.
- **Sending to quarantine and then acking the original message with two non-atomic operations:** a crash between the two operations can lose or duplicate the message.
- **Deleting messages from the DLQ without keeping a trace:** loses investigation data and the ability to replay.
- **Logging the entire sensitive payload:** can expose business data or personal information.

## 17. Implementation checklist

- [ ] The listener can read `JMSRedelivered` and `JMSXDeliveryCount` when needed.
- [ ] Understand that the first delivery has count = 1; 2 or more is redelivery.
- [ ] Do not use the delivery count as an ID or as exact evidence of how many times the business logic ran.
- [ ] The producer creates a stable application event ID and keeps it unchanged on retry.
- [ ] The consumer has an inbox/deduplication or idempotent processing.
- [ ] Listeners that need reliability use a transacted JMS Session or a suitable transaction.
- [ ] Exceptions that need a retry are propagated so the container rolls back.
- [ ] Transient and permanent errors are classified separately.
- [ ] The broker has suitable maximum redelivery attempts and delay/backoff.
- [ ] There is a DLQ/quarantine destination and a handling/replay procedure.
- [ ] The broker redelivery policy has been distinguished from the Spring connection recovery BackOff.
- [ ] Moving to quarantine and acknowledging the original message are coordinated safely.
- [ ] There are metrics and alerts for redelivery, rollback, backlog, and the DLQ.
- [ ] Listener exceptions, rollback, broker restart, redelivery, poison messages, and duplicate publication have been tested.

## 18. References

- [Jakarta Messaging 3.1 — JMSRedelivered](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#jmsredelivered)
- [Jakarta Messaging 3.1 — JMSXDeliveryCount](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#jmsxdeliverycount)
- [Jakarta Messaging 3.1 — Receiving messages asynchronously](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#receiving-messages-asynchronously)
- [Jakarta Messaging 3.1 — Reliability](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#reliability)
- [Spring Framework 7 — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework 7 — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework 7 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework 7 — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
