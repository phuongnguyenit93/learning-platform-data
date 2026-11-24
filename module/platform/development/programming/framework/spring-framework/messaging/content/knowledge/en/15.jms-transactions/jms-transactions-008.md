# Rollback, Redelivery, and Exceptions Escaping the Listener in Spring JMS

## 1. Why Does a Listener Exception Affect Message Redelivery?

A JMS listener typically receives a message from the broker, performs the business operation, and then finishes the processing pass. The broker needs to know whether the message was processed successfully so that it can decide whether to remove the message from the destination or deliver it again.

In Spring JMS, this outcome depends on the acknowledgement mode or the transaction of the JMS Session. When the listener completes normally, the message can be acknowledged or the transaction committed. When the listener throws an exception and the exception escapes the method, the container can roll back the transaction so that the broker redelivers the message.

Three concepts need to be kept separate:

- **Rollback:** discards the result of the current transaction. With a local JMS transaction, the message receive is rolled back so the message can be delivered again.
- **Redelivery:** the broker delivers again a message that was delivered before but was not confirmed as complete.
- **Exception propagation:** an exception from the listener method leaves the method so that the listener adapter/container recognizes that the processing pass failed.

Merely throwing an exception does not automatically guarantee redelivery in every acknowledgement mode. The listener container and the broker need to be configured appropriately.

After this lesson, you should be able to:

- Explain the transaction and acknowledgement of a listener.
- Configure sessionTransacted to roll back when the listener fails.
- Understand the differences among AUTO_ACKNOWLEDGE, CLIENT_ACKNOWLEDGE, and a transacted Session.
- Let an exception escape the listener correctly.
- Distinguish an ErrorHandler from the rollback mechanism and broker redelivery.
- Configure redelivery limits, delay, and a dead-letter queue.
- Design idempotency to tolerate duplicate messages.
- Test rollback, redelivery, poison messages, and transaction boundaries.

## 2. The Lifecycle of One Message Processing Pass

For a listener running in a local JMS transaction, one processing pass typically follows this sequence:

~~~text
Broker delivers the message
        |
        v
JMS Session begins a transaction
        |
        v
Spring calls the listener method
        |
        +----------------------------+
        |                            |
   Method succeeds            Method throws exception
        |                            |
        v                            v
     COMMIT                       ROLLBACK
        |                            |
        v                            v
Broker records the              Broker may redeliver
message as processed            the message per the redelivery policy
~~~

When the listener processes successfully, the container commits the session transaction. The broker records that the message receive has completed.

When the listener throws an exception, the container rolls back the transaction. A message received in an uncommitted transaction is not acknowledged as successful. The broker may redeliver the message according to the provider's redelivery policy.

If the method catches the exception, merely logs it, and ends normally, the container sees a successful processing pass. The transaction may be committed and the message is not redelivered. Therefore, the decision whether to catch or rethrow an exception is part of the message-processing contract.

## 3. Configuring sessionTransacted in Spring JMS

### 3.1 Using DefaultJmsListenerContainerFactory

For listeners declared with `@JmsListener`, you can enable a local JMS transaction on the factory:

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
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-6");

        return factory;
    }
}
~~~

This factory creates a listener container that uses a transacted JMS Session. Each time the listener processes a message, it lies within the message-receive transaction. If the listener completes normally, the container commits; if the listener fails, the container rolls back.

Listener:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(destination = "orders.queue")
    public void handle(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

`OrderCreated` and `OrderService` are application types. If `process` throws an unchecked exception, the exception leaves the listener method for the container to handle. With the session transaction enabled, the container rolls back the message receive.

If the application has multiple listener groups with different transaction requirements, declare separate factories and select them with the `containerFactory` attribute of `@JmsListener`.

### 3.2 Configuring the Container Manually

If you create a `DefaultMessageListenerContainer` directly, enable the same property:

~~~java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setConnectionFactory(connectionFactory);
container.setDestination(ordersQueue);
container.setMessageListener(orderListener);
container.setSessionTransacted(true);
~~~

This is a configuration snippet inside a Spring-managed bean. `connectionFactory`, `ordersQueue`, and `orderListener` need to be supplied from the application context.

### 3.3 Why Use a Transacted Session?

The Spring documentation recommends using `sessionTransacted=true` or an external transaction manager when you need reliability. With a local JMS transaction, the acknowledgement of the message is tied to the commit of the session. An exception from the listener causes the container to roll back and gives the broker a chance to redeliver.

This is a clear choice for a queue consumer or a durable topic subscriber that needs to avoid losing messages because of processing errors. However, a local JMS transaction only covers the JMS resources belonging to that session; it does not by itself include the database or HTTP services.

## 4. Acknowledgement Mode and Redelivery Capability

Do not assume that every acknowledgement mode behaves the same way when the listener throws an exception. With `DefaultMessageListenerContainer`, the modes mean the following:

| Mode | Behavior when the listener succeeds | Behavior when the listener throws an exception |
|---|---|---|
| `AUTO_ACKNOWLEDGE` | The container/provider acknowledges automatically | With DefaultMessageListenerContainer, the acknowledge happens before the listener is invoked; no redelivery because of a listener exception |
| `DUPS_OK_ACKNOWLEDGE` | Lazy acknowledge per the provider/container mechanism | Redelivery is not guaranteed when the listener throws an exception; duplicates are still possible in some situations |
| `CLIENT_ACKNOWLEDGE` | Spring acknowledges after the listener runs successfully | May be redelivered when the listener fails, but it is a best-effort mechanism |
| `sessionTransacted=true` | Commits the transaction after the listener succeeds | Rolls back when the listener fails; supports more consistent redelivery |

`AUTO_ACKNOWLEDGE` is the common default of the listener container. With `DefaultMessageListenerContainer`, Spring acknowledges the message before listener execution begins. If the method then throws an exception, the broker has already been told that the message was acknowledged; you cannot rely on that exception to request redelivery.

`CLIENT_ACKNOWLEDGE` can let Spring acknowledge only after the listener completes successfully. However, acknowledgement in JMS can apply to the messages the consumer has received on the same session, and the redelivery behavior depends on the provider. When you need a clear guarantee, prefer a transacted Session.

`sessionTransacted=true` is the direct way to tie message receipt to the listener's result. Configure it on the factory/container instead of merely hoping the exception is automatically seen by the broker.

## 5. Letting the Exception Escape the Listener

### 5.1 Rethrow When Processing Fails

Example of a service that detects a transient error:

~~~java
@JmsListener(destination = "payments.queue")
public void handle(PaymentRequested event) {
    paymentService.process(event);
}
~~~

If `paymentService.process` throws a `RuntimeException`, the listener method ends abnormally. With a session transaction, the container rolls back and the message may be redelivered.

You can throw a meaningful exception when you detect a condition that prevents continuing:

~~~java
@JmsListener(destination = "inventory.queue")
public void reserve(ReserveInventory command) {
    boolean reserved = inventoryService.reserve(command);

    if (!reserved) {
        throw new IllegalStateException(
                "Inventory reservation could not be completed");
    }
}
~~~

The example illustrates letting the error escape the method. `ReserveInventory` and `InventoryService` are application types; in production, use specific domain exceptions to distinguish transient errors from permanent errors.

### 5.2 Catch Then Rethrow

You can catch the exception to add context and then throw it again:

~~~java
@JmsListener(destination = "orders.queue")
public void handle(OrderCreated event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Could not process order event {}", event.eventId(), ex);
        throw ex;
    }
}
~~~

Rethrowing preserves the failure signal for the listener container. The transaction may roll back according to the configuration.

If you need to change the exception type, preserve the original cause:

~~~java
catch (ExternalServiceException ex) {
    throw new TemporaryOrderProcessingException(
            "Order processing must be retried", ex);
}
~~~

Do not lose the stack trace or the correlation ID when wrapping an exception. This information is needed to find the cause through logs and traces.

### 5.3 Catch and Swallow the Exception

The following snippet changes the semantics of the processing pass:

~~~java
@JmsListener(destination = "orders.queue")
public void handle(OrderCreated event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Processing failed", ex);
        // The method ends normally.
    }
}
~~~

Because the exception does not escape the listener, the container may consider the invocation successful. With a session transaction, the message may be committed and not redelivered.

Catch without rethrowing only when the application has handled the error with an accepted outcome, for example having recorded the message in a durable error store within an appropriate transaction. Merely writing a log is not durable error handling.

## 6. How Does Spring Handle a Listener's Exception?

The listener container is an intermediate layer between the broker and the business method. It manages message receipt, transactions, acknowledgement, JMS resources, and exception handling.

By default, Spring does not propagate an exception from the listener method back up to the JMS provider as though the provider's own callback failed. The container handles its acknowledgement/transaction and usually logs the exception at WARN level. You can configure an `ErrorHandler` to receive listener errors and perform logging, metrics, or alerting.

Example of registering an ErrorHandler on the factory:

~~~java
factory.setErrorHandler(error ->
        logger.error("JMS listener execution failed", error));
~~~

`logger` in the example is the logger of the configuration class.

Distinguish:

- **An exception escaping the listener:** tells the container that the method's processing pass failed; the transaction mode decides commit or rollback.
- **ErrorHandler:** the point that receives errors arising from listener execution, for observation or handling according to the application policy.
- **JMS ExceptionListener:** the JMS connection's callback for connection-level errors that the provider reports.
- **Broker redelivery policy:** decides the redelivery schedule, the number of attempts, and the dead-letter after the transaction is rolled back or the message is not acknowledged.

An ErrorHandler does not replace a transaction. If you want a rollback, let the exception escape the listener and configure an appropriate transaction. Do not catch the exception in the listener and expect the ErrorHandler to restore a transaction that has already been committed.

## 7. Broker-Managed Redelivery

### 7.1 When Does the Broker Redeliver?

After the transaction is rolled back or the message is not acknowledged through an appropriate mechanism, the broker can put the message back into a deliverable state. The next receive is a redelivery.

Influencing factors:

- The acknowledgement or transaction outcome.
- Whether the message has the persistent delivery mode.
- The broker redelivery policy.
- The delivery count and the delivery limit.
- The redelivery delay or backoff.
- Message expiration/TTL.
- The consumer selector and destination topology.
- Broker restart, persistence, and storage configuration.

Spring enables the transaction at the listener container; the broker decides the specific redelivery policy. The configuration names and behaviors differ among ActiveMQ Classic, ActiveMQ Artemis, IBM MQ, and other providers.

### 7.2 Recognizing a Redelivered Message

JMS provides the `JMSRedelivered` header to indicate that the message may have been delivered before but was not acknowledged successfully.

Example of receiving the JMS Message directly:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;

@JmsListener(destination = "orders.queue")
public void inspect(Message message) throws JMSException {
    boolean redelivered = message.getJMSRedelivered();

    if (redelivered) {
        log.warn("Receiving a redelivered message: {}",
                message.getJMSMessageID());
    }

    processMessage(message);
}
~~~

Some providers also supply a delivery count property such as `JMSXDeliveryCount`. Check the provider and the JMS version you use to learn how to read it, its initial value, and how the counter increments.

`JMSRedelivered` is only a signal for observation. Do not use it as the sole deduplication key. A message may be redelivered after a crash at an unpredictable moment, and the application needs to rely on a stable event ID or business key to deduplicate.

### 7.3 Redelivery Delay and Number of Attempts

Brokers usually let you configure:

- The maximum number of deliveries.
- The wait before a redelivery.
- Exponential delay or a multiplier.
- The maximum redelivery delay.
- The handling when the number of attempts is exceeded.

If the listener always fails and the broker redelivers immediately, one bad message can create a fast loop that consumes CPU, threads, and logs. A redelivery delay reduces the pressure and gives dependent systems time to recover.

Do not confuse a message's redelivery delay with the listener container's `recoveryInterval`. The recovery interval controls how Spring tries to re-create the connection/consumer after an infrastructure error. The redelivery policy controls when the broker redelivers an unacknowledged message.

## 8. Poison Messages and the Dead-Letter Queue

### 8.1 What Is a Poison Message?

A poison message is a message that keeps causing errors when processed. Causes may include:

- A payload with the wrong schema or missing required data.
- An invalid business value.
- A message containing a data type the consumer cannot deserialize.
- A bug that makes the same code branch always throw an exception.
- Reference data that has been deleted or no longer exists.

Infinite retry cannot fix a permanent error. That message may occupy a consumer and slow down valid messages.

### 8.2 Dead-Letter Queue

A dead-letter queue (DLQ) is a destination to which the broker moves a message after the redelivery limit is exceeded or according to the dead-letter policy conditions.

A typical process:

1. The consumer receives the message.
2. The listener throws an exception and the transaction rolls back.
3. The broker redelivers according to the redelivery policy.
4. The delivery count increases.
5. After the maximum number of attempts, the broker moves the message to the DLQ or handles it according to the configured policy.
6. The operations team investigates the cause and decides whether to fix the data, fix the code, or replay the message.

The DLQ and the maximum number of attempts are not configured the same way across all providers. You need to configure the broker, grant access to the DLQ, and have a process for monitoring the backlog.

### 8.3 Retrying Transient Errors vs. Permanent Errors

You can classify errors by nature:

- **Transient errors:** an external service timeout, the database temporarily losing its connection, a rate limit. You can retry with a delay and a limit.
- **Permanent errors:** a wrong schema, invalid data, a wrong destination mapping. Unlimited retry is usually of no use; send them to an error flow or the DLQ.
- **Unclear errors:** keep the message intact, record sufficient metadata, and limit the number of attempts while investigating.

Do not sleep inside the listener to wait for a retry. Sleep holds the consumer thread and can reduce throughput. Use the broker redelivery policy or a deliberate retry mechanism.

## 9. JMS and Database Transactions Are Not Automatically Atomic

`sessionTransacted=true` creates a local transaction for the JMS Session. It covers the message receive and JMS operations on the same session, for example sending a response through a listener API that uses that session.

It does not automatically include a database transaction, an HTTP call, or operations on an external system.

Example:

1. The listener receives an event.
2. The service writes a change to the database and the database commits.
3. A later step throws an exception.
4. The JMS session rolls back.
5. The broker redelivers the message.
6. The database may receive the same event again.

The result is that duplicate processing can occur even though the JMS transaction works correctly. Therefore, the listener should have idempotency.

Commonly used options:

- **Inbox/deduplication table:** store the processed event ID with a unique constraint in the same database transaction as the business update.
- **Idempotent service:** the same event invoked multiple times still produces the same final result.
- **Outbox pattern:** write the business change and the event to be published in the same database transaction, and then a publisher publishes the outbox.
- **JTA/XA:** coordinate multiple XA resources in one transaction when the provider, the database, and the transaction manager support it; complex configuration with operational cost.

Do not claim exactly-once just because a transacted Session is enabled. Design so that a duplicate message does not cause unintended side effects.

## 10. Distinguishing a Local JMS Transaction from an External Transaction Manager

### 10.1 Local JMS Transaction

Use `sessionTransacted=true` when you want the transaction to cover only the JMS Session. This is usually an efficient and easy-to-deploy choice for a consumer.

~~~java
factory.setSessionTransacted(true);
~~~

When the listener succeeds, the session commits. When the listener throws an exception, the session rolls back. The redelivery of the message after a rollback follows the provider's redelivery policy.

### 10.2 JmsTransactionManager

`JmsTransactionManager` manages a local transaction for one ConnectionFactory. It can coordinate JMS operations within the scope of a Spring-managed transaction, but it does not itself turn a database transaction into the same atomic transaction.

If you need the same JMS transaction to be shared among beans or templates, configure the transaction manager and the ConnectionFactory correctly, and verify that the resource is bound to the current transaction.

### 10.3 JTA/XA

When you need a transaction that coordinates JMS and the database, you can use JTA with an XA-capable ConnectionFactory and the database's XA resource. The listener container needs to participate in an external transaction manager.

Conditions:

- The JMS provider supplies an appropriate XA resource.
- The database driver/resource supports XA.
- The transaction coordinator is configured correctly.
- Timeouts, the recovery log, and crash recovery are operated.
- Downstream systems participate in the transaction according to the proper standard.

XA can provide an atomic commit among the enlisted resources, but it increases complexity and operational requirements. For many systems, an outbox/inbox and idempotency may be easier to control.

## 11. Error Handling and Logging

A production listener needs to record enough information to investigate without exposing sensitive payloads.

You should record:

- The destination and the listener ID.
- JMSMessageID and JMSCorrelationID if present.
- The business event ID or idempotency key.
- JMSRedelivered and the delivery count if the provider supports it.
- The exception type and the root cause.
- The processing time.
- The number of retries or the DLQ status.
- The transaction status to the extent observable.

Avoid logging the entire body if the message contains personal data, tokens, payment information, or secrets. You can log the event type, a masked business ID, and the correlation ID.

An ErrorHandler should send errors to logging, metrics, or alerting. If you use an error flow to move the message to an error-storage system, you must define clearly whether the original message is committed or rolled back and whether the error store is durable. An operation that merely writes a log is not enough to replace a DLQ.

## 12. Testing Rollback and Redelivery

The important behaviors need integration tests with the target JMS provider/broker:

1. Listener succeeds with sessionTransacted: the message is committed and is no longer redelivered.
2. Listener throws an exception: the transaction rolls back and the broker redelivers the message.
3. Listener catches then swallows the exception: verify the processing pass is treated as successful per the transaction flow.
4. AUTO_ACKNOWLEDGE on DefaultMessageListenerContainer: verify the exception does not by itself create redelivery.
5. CLIENT_ACKNOWLEDGE: check the specific behavior of the provider/container.
6. Redelivery delay: the message is not redelivered before the configured wait.
7. Max delivery attempts: a message exceeding the limit is handled per the DLQ policy.
8. The listener receives the message with JMSRedelivered set appropriately.
9. The database has committed but JMS rolls back: deduplication prevents repeated side effects.
10. Broker restart during processing: verify acknowledgement and redelivery after recovery.
11. The ErrorHandler receives the exception per the configuration while the transaction outcome remains correct.
12. A poison message does not indefinitely block other valid messages.

Tests should use a latch/future or a polling assertion with a timeout instead of a fixed sleep. A unit test for the service does not prove broker redelivery; you need an integration test with a real provider or an appropriate Testcontainers setup.

## 13. Common Mistakes

- **Assuming an exception always creates redelivery:** the acknowledgement mode may have already acknowledged the message before the listener ran.
- **Using AUTO_ACKNOWLEDGE for processing that needs reliability:** DefaultMessageListenerContainer acknowledges before listener execution.
- **Catching then swallowing the exception:** the container may commit the transaction because the method ends normally.
- **Merely logging and continuing:** a log does not roll back the message and does not store the message durably.
- **Confusing the ErrorHandler with a rollback:** the transaction/acknowledgement is managed by the container; the ErrorHandler mainly receives errors for observation/handling.
- **Retrying a poison message indefinitely:** one bad message can create a loop and clog the consumer.
- **Not configuring a DLQ:** a message exceeding the limit may be handled by an unsuitable default policy.
- **Confusing recoveryInterval with redelivery delay:** one restores the listener resources, the other delays redelivery of the message.
- **Assuming a local JMS transaction includes the database:** the two resources can commit/roll back independently.
- **Not being idempotent:** rollback and redelivery can make the business operation run repeatedly.
- **Trusting JMSRedelivered as a deduplication key:** it is only a status flag and does not replace a stable event ID.
- **Using XA without operating the recovery log:** a distributed transaction needs a process for handling in-doubt states.
- **Not testing on a real broker:** the redelivery limit, delay, and DLQ depend on the provider.

## 14. Implementation Checklist

Before putting a listener into production, confirm:

- Is the listener container in use DefaultMessageListenerContainer or another implementation?
- What is the current acknowledgement mode?
- Is `sessionTransacted=true` or an appropriate transaction manager enabled?
- Does the listener let the exception escape when processing fails?
- Is an exception being caught and the message accidentally committed?
- Does the ErrorHandler record the exception and the root cause?
- Does the broker redelivery policy have a reasonable delay and max attempts?
- Is the DLQ configured, monitored, and does it have a replay process?
- Do you distinguish transient errors from permanent errors?
- Is the listener idempotent and does it use a stable event ID?
- Do the database and JMS need XA or an outbox/inbox?
- Do metrics track redelivery, delivery count, rollback, and DLQ backlog?
- Have integration tests verified rollback, redelivery, poison messages, and broker restart?

## 15. References

- [Spring Framework 6.2 — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [AbstractMessageListenerContainer — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [DefaultMessageListenerContainer — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)