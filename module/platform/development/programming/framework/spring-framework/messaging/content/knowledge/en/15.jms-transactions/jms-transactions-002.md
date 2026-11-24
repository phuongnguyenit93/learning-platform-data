# AUTO_ACKNOWLEDGE, CLIENT_ACKNOWLEDGE, and DUPS_OK_ACKNOWLEDGE

## 1. What Problem Does Acknowledgement Solve?

In Jakarta Messaging (JMS), a consumer needs to tell the provider how far a message has been received and processed. Acknowledgement (ack) is a signal on the receiving side that lets the provider decide whether it can remove the message from the pending-delivery state or must keep it for redelivery.

The three standard acknowledgement modes of a non-transacted `Session` are:

- `Session.AUTO_ACKNOWLEDGE`: the provider acknowledges automatically according to the rules of the mode.
- `Session.CLIENT_ACKNOWLEDGE`: the application explicitly calls `Message.acknowledge()`.
- `Session.DUPS_OK_ACKNOWLEDGE`: the provider acknowledges lazily to reduce overhead; the consumer must accept the possibility of receiving duplicates.

Besides these three modes, `Session.SESSION_TRANSACTED` indicates a Session with a local transaction. This is a separate commit/rollback mechanism, not a fourth acknowledgement mode equivalent to the three non-transacted modes.

The ack mode is configured at the `Session` level and affects the message consumers of that Session. It is not a property of each individual message and does not determine whether the producer sends persistent or non-persistent messages.

## 2. Distinguishing Acknowledgement, Transaction, and Delivery Mode

Three concepts that are often confused:

| Concept | Question it answers | Example |
| --- | --- | --- |
| Acknowledgement mode | When does the provider consider the message acknowledged by the consumer? | AUTO, CLIENT, DUPS_OK |
| Session transaction | Which group of receives and sends is committed or rolled back together? | `SESSION_TRANSACTED`, `commit()`, `rollback()` |
| Delivery mode | Must the broker store the sent message durably, or may it be lost if the provider fails? | `PERSISTENT`, `NON_PERSISTENT` |

`PERSISTENT` does not mean the consumer has finished processing. `AUTO_ACKNOWLEDGE` does not mean the message is stored durably. `CLIENT_ACKNOWLEDGE` does not create a transaction between JMS and the database. To understand the reliability of a flow, you must look at the producer delivery mode, the consumer acknowledgement/transaction, the broker policy, and the business transaction together.

## 3. The Three Standard Acknowledgement Modes

### 3.1. AUTO_ACKNOWLEDGE

The provider acknowledges automatically when:

- Synchronous consumer: the `receive()` call returns a message successfully.
- Asynchronous consumer: `MessageListener.onMessage(...)` finishes successfully.

With synchronous receive, the ack happens when `receive()` returns. If the application gets the message and only then updates the database, and the database fails, the provider is already allowed to consider the message received; the message does not come back on its own merely because the code that processes it afterwards failed.

With a plain Jakarta Messaging asynchronous listener, the provider acknowledges after `onMessage` returns successfully. If the listener throws a `RuntimeException`, Jakarta Messaging specifies the redelivery behavior for AUTO/DUPS_OK; the number of times the provider retries before giving up depends on the provider.

Do not mechanically apply this plain-listener rule to the Spring listener container. Spring catches and handles listener exceptions inside the container, so the provider does not see the failed callback in the same way. The ack timing of `DefaultMessageListenerContainer` and `SimpleMessageListenerContainer` also differs; section 8 explains this in detail.

AUTO is suitable when processing is simple, losing a message in some failure windows is acceptable, or the application has another recovery mechanism. For business operations that need redelivery when the listener fails, do not rely on AUTO alone.

### 3.2. CLIENT_ACKNOWLEDGE

The application calls `message.acknowledge()` after completing the work:

~~~java
Message message = consumer.receive(5_000);
if (message != null) {
    processBusinessData(message);
    message.acknowledge();
}
~~~

If processing fails before the acknowledge, the message is still not acknowledged. The application can call `session.recover()` to stop the current receive flow and begin redelivery from the first message that has not been acknowledged.

**A very important point:** in standard JMS, `Message.acknowledge()` acknowledges all messages that have been delivered by the same Session, including messages delivered before the message that is calling `acknowledge()`. It is not an individual ack for a single message.

For example, if the same Session has received M1, M2, and M3, calling `M2.acknowledge()` may acknowledge M1, M2, and M3 that have been delivered by that Session. Therefore, do not process multiple messages in parallel on the same Session and then acknowledge arbitrarily in order of completion.

`CLIENT_ACKNOWLEDGE` is suitable when the application needs to decide the moment of acknowledgement and can control the processing order within the Session. It does not group sending a response or updating the database into one atomic transaction. If you need to receive a message and send a reply as one JMS unit, use a transacted Session.

### 3.3. DUPS_OK_ACKNOWLEDGE

The provider acknowledges messages lazily and may batch multiple acknowledgements to reduce the work of managing delivery state. When the provider or the connection fails, some messages that have already been processed may be delivered again.

This mode trades lower acknowledgement cost for a higher chance of duplicates. Use it only when the consumer can tolerate repeated processing, for example updating an idempotent projection or processing data where a duplicate does not change the result.

DUPS_OK is not a "never lose a message" mode. It still has failure windows and its semantics depend on the provider. If a duplicate could cause a double charge, create a duplicate order, or emit an irreversible side effect, choose an explicit transaction/idempotency.

## 4. CLIENT_ACKNOWLEDGE: Cumulative Acknowledge and Recover

### 4.1. Acknowledge Scoped to the Session

Standard JMS does not define individual acknowledgement for an independent message within a Session. When `acknowledge()` is called on a message, the provider acknowledges all messages that have been delivered by that Session.

This has two consequences:

1. Keep receiving and processing messages in order within each Session.
2. If you need concurrency, create multiple independent Sessions/consumers instead of sharing one Session across multiple threads.

Jakarta Messaging requires a Session to be used serially by one logical thread of control at a time. Each Session has its own input stream and acknowledgement scope.

### 4.2. session.recover()

`Session.recover()` stops the current receive flow and restarts from the first message that has not been acknowledged. The provider marks redelivered messages with `JMSRedelivered=true` and increments `JMSXDeliveryCount` as specified by Jakarta Messaging.

Example:

~~~java
Message message = consumer.receive(5_000);
if (message != null) {
    try {
        processBusinessData(message);
        message.acknowledge();
    } catch (RuntimeException ex) {
        session.recover();
        throw ex;
    }
}
~~~

This is an illustrative example for a synchronous consumer, not a complete retry pattern. If the error is invalid data that cannot be processed, calling recover indefinitely can create a poison message loop. You need to limit retries and move the failing message to a dead-letter queue (DLQ) according to the broker's capabilities.

`recover()` only applies to a non-transacted Session. For a transacted Session, use `rollback()` to undo the transaction.

## 5. SESSION_TRANSACTED: Commit and Rollback

When you create a transacted Session, acknowledgement is managed automatically by the transaction:

- `commit()` acknowledges the messages received in the transaction and emits the messages sent in the transaction.
- `rollback()` discards the messages sent in the transaction and recovers the messages received so that the provider can deliver them again.

A JMS transaction groups the input and output of the same Session into one unit of work. For example, a consumer receives `OrderPlaced`, processes it, then sends `ReserveInventory` using a producer created from the same Session. If the commit succeeds, the receive and the send are committed together. If it rolls back, the input message is recovered and the output message is discarded.

~~~java
try (Connection connection = connectionFactory.createConnection();
     Session session = connection.createSession(Session.SESSION_TRANSACTED)) {

    MessageConsumer consumer = session.createConsumer(ordersQueue);
    MessageProducer producer = session.createProducer(inventoryQueue);
    connection.start();

    Message incoming = consumer.receive(5_000);
    if (incoming != null) {
        try {
            processOrder(incoming);
            producer.send(session.createTextMessage("ReserveInventory"));
            session.commit();
        } catch (RuntimeException ex) {
            session.rollback();
            throw ex;
        }
    }
}
~~~

The illustrative code requires a `ConnectionFactory`, `ordersQueue`, and `inventoryQueue` supplied by the JMS provider. In a real application, you need to handle `JMSException`, configure timeouts, and close resources according to the application lifecycle.

When the Session is already transacted, the acknowledgement mode parameter passed with `createSession(transacted, acknowledgeMode)` is ignored. Use `createSession(Session.SESSION_TRANSACTED)` to express the intent clearly.

The transaction only covers the JMS operations in the same Session. If `processOrder` updates the database via JDBC, the database is not automatically inside the JMS transaction. If the database commits but JMS rolls back, the message may be redelivered and the code may run again. Use idempotency, inbox/outbox, or XA if you need to coordinate multiple resources.

## 6. Quick Comparison of the Modes

| Mode | Who acknowledges? | When does it acknowledge? | Redelivery on processing error | Duplicate |
| --- | --- | --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | Provider | After a successful `receive()` or a successful listener return per the JMS API; the Spring container has its own semantics | Depends on receive/listener and the container | Possible in the final failure window |
| `CLIENT_ACKNOWLEDGE` | Application or Spring container | When `acknowledge()` is called; the Spring container usually acks after a successful listener | May require `recover()`; the Spring container provides best-effort redelivery when the listener fails | Possible on redelivery |
| `DUPS_OK_ACKNOWLEDGE` | Provider | Lazily, may batch acknowledgements | The provider/JMS API and the container decide; the Spring container does not redeliver on a user exception in this mode | Possible and is a characteristic that must be accepted |
| `SESSION_TRANSACTED` | Transaction manager/Session | On `commit()`; `rollback()` recovers input and discards output | Yes on rollback; the provider applies its redelivery policy | Still possible in some failure windows between the business commit and the JMS commit |

No single mode guarantees exactly-once across the whole business operation spanning the database, the broker, and external services.

## 7. Creating a Session with Each Mode in Jakarta Messaging

With the classic API, the constants are in `jakarta.jms.Session`:

~~~java
Session auto = connection.createSession(Session.AUTO_ACKNOWLEDGE);
Session client = connection.createSession(Session.CLIENT_ACKNOWLEDGE);
Session duplicates = connection.createSession(Session.DUPS_OK_ACKNOWLEDGE);
Session transaction = connection.createSession(Session.SESSION_TRANSACTED);
~~~

Or use the two-parameter overload:

~~~java
Session auto = connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
Session client = connection.createSession(false, Session.CLIENT_ACKNOWLEDGE);
Session duplicates = connection.createSession(false, Session.DUPS_OK_ACKNOWLEDGE);
Session transaction = connection.createSession(true, Session.AUTO_ACKNOWLEDGE);
~~~

On the last line, `transacted=true` means a transacted Session; `AUTO_ACKNOWLEDGE` is ignored. The Sessions in the example are alternatives for illustration; you do not need to create all four Sessions for the same consumer.

With the simplified `JMSContext` API, the corresponding modes are `JMSContext.AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, `DUPS_OK_ACKNOWLEDGE`, and `SESSION_TRANSACTED`. The Session rules and limits also apply to JMSContext.

In a Jakarta EE web/EJB container, the container may manage the transaction and the Session. Some ways of creating a local transacted or client-ack Session are not portable or are ignored when a JTA transaction is active. Follow the transaction model managed by the application server.

## 8. Acknowledgement in the Spring JMS Listener Container

The Spring listener container receives messages, invokes the listener, handles exceptions, and performs acknowledgement. Because the container controls the callback, the observable behavior can differ from a JMS client that registers a `MessageListener` directly.

### 8.1. AUTO_ACKNOWLEDGE: DMLC and SMLC Differ

`DefaultMessageListenerContainer` (DMLC) acknowledges before invoking the listener. If the listener fails or the process is interrupted during processing, the message is not redelivered under AUTO mode.

`SimpleMessageListenerContainer` (SMLC) acknowledges after the listener invocation finishes. However, the Spring container does not by default propagate the listener exception to the provider; therefore an exception thrown by the listener does not create redelivery in AUTO mode. A JVM crash while the listener is running can still lead to redelivery.

Therefore, when you need consistent redelivery, do not rely on AUTO alone, whether you use SMLC or DMLC.

### 8.2. CLIENT_ACKNOWLEDGE in the Spring Container

The Spring container acknowledges automatically after the listener processes successfully. If the listener throws an exception, the container may let the message be redelivered under best-effort semantics. This is not a local JMS transaction: other operations on the Session, such as sending a response, are not committed/rolled back together with the received message the way they are in a transacted Session.

### 8.3. DUPS_OK_ACKNOWLEDGE in the Spring Container

The Spring container acknowledges lazily during or right after listener execution. An exception thrown by the user listener does not create redelivery under the container's semantics; a process interruption can create redelivery. This mode still requires the consumer to tolerate duplicates.

### 8.4. Prefer sessionTransacted=true When You Need Rollback

To enable a local JMS transaction for each listener invocation:

~~~java
DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
factory.setSessionTransacted(true);
~~~

With `@JmsListener`, the method can be:

~~~java
@JmsListener(destination = "orders.queue")
public void handle(OrderPlaced event) {
    orderService.process(event);
}
~~~

If `orderService.process(...)` throws an exception out of the listener, the container rolls back the JMS Session; the provider may redeliver the message according to its redelivery policy. If the code catches the exception and returns normally, the container may commit; merely logging does not roll back the transaction.

In Spring, `sessionTransacted=true` is a common recommendation when you need reliable redelivery. DMLC supports participating in an external transaction when JTA/XA is configured appropriately; SMLC does not support externally managed transactions. If you use SMLC with a `TaskExecutor`, acknowledgement may happen before the listener runs; do not use that executor configuration when you rely on a transaction or client acknowledgement for rollback.

## 9. Synchronous Receive and Acknowledgement Timing

With raw JMS `AUTO_ACKNOWLEDGE`, the message is acknowledged when `receive()` returns successfully. If the application processes the payload after the `receive()` line, that processing lies outside the ack moment:

~~~java
Message message = consumer.receive(5_000);
if (message != null) {
    updateDatabase(message); // an error here does not by itself make the message redelivered under AUTO
}
~~~

With `CLIENT_ACKNOWLEDGE`, call `message.acknowledge()` after the database update succeeds. If an error occurs before the ack, use `session.recover()` or close the Session with appropriate recovery semantics so that the unacknowledged message is delivered again.

With a transacted Session, put the `receive`, the processing, and the `commit()` in the same transaction. If processing fails, roll back. When using a standalone Spring `JmsTemplate.receive()`, the template may complete the receive operation before the method returns; business processing that happens afterwards is not automatically part of the same transaction just because the template has been configured.

## 10. Redelivery, Duplicates, and Dead-Letter Queue

Redelivery is part of failure handling. The provider may redeliver a message when the Session recovers/rolls back, the connection is lost, or an acknowledgement has not completed.

JMS provides useful metadata:

- `JMSRedelivered`: a boolean indicating that the provider has marked the message as possibly delivered before.
- `JMSXDeliveryCount`: the delivery count according to the provider/Jakarta Messaging.

This is observational information, not an idempotency key. Do not rely on `JMSRedelivered` alone to skip a message: a message on its first delivery may already have produced a side effect before the process died and then been delivered again. Use a stable application `eventId`, store the processing result, or use an inbox record with a unique constraint.

Brokers typically let you configure the number of redeliveries, delay/backoff, the dead-letter address/queue, and the poison-message handling policy. These configuration names and defaults depend on the provider; the JMS API does not standardize a common DLQ policy.

A consumer design should:

1. Check or write the `eventId` in the same database transaction as the business change.
2. Acknowledge the message only after the mandatory work has completed.
3. Classify transient errors versus errors that cannot be processed.
4. Limit the number of retries; move the poison message to a DLQ for investigation.
5. Have a replay process after fixing the data or the code.
6. Monitor the redelivery count, DLQ depth, and message age.

## 11. Local JMS Transaction, Database Transaction, and XA

### 11.1. Local JMS Transaction

A transacted Session guarantees that the send/receive operations in the Session commit or roll back together. This is usually an efficient choice when the main business operation lies within JMS or when the consumer only needs to send a reply through the same Session.

Spring's `JmsTransactionManager` manages a local transaction for one `ConnectionFactory`, binding the Connection/Session pair to the thread. `JmsTemplate` can participate in the bound resource. The listener container can also open its own transaction for each listener invocation with `sessionTransacted=true`.

### 11.2. The Database Is Not Automatically Inside the JMS Transaction

If a listener both updates the database and consumes a message, the local JMS transaction and the JDBC transaction are two independent transactions. The following can happen:

- The database commits, then the JMS commit fails: the broker redelivers the message; the business operation may run again.
- The JMS commit succeeds but the database rolls back: the message has been acknowledged while the business data was not saved, if the two transactions are not coordinated.

To handle this, use an idempotent consumer/inbox, a transactional outbox, or an XA transaction coordinator when atomic commit across resources is truly needed and the provider supports XA.

### 11.3. XA/JTA

XA/JTA lets a transaction coordinator coordinate multiple resource managers, such as a database and a JMS provider with an XA-aware ConnectionFactory. With Spring JMS, DMLC can participate in an external transaction through `JtaTransactionManager` and appropriate XA resources. SMLC does not support external transactions.

XA increases operational cost, configuration effort, and processing time. Do not choose XA merely to avoid writing idempotency if an outbox/inbox meets the requirement. Even with XA, you need to understand failure recovery and the heuristic outcomes of the transaction coordinator.

## 12. Choosing a Mode by Requirement

| Requirement | Suggested choice | Reason |
| --- | --- | --- |
| A simple consumer, where losing a message in a failure window is acceptable | AUTO_ACKNOWLEDGE | Fewer operations and low cost |
| Reduce acknowledgement overhead, and the consumer tolerates duplicates | DUPS_OK_ACKNOWLEDGE | The provider can acknowledge in batches/lazily |
| The application decides the ack moment after processing | CLIENT_ACKNOWLEDGE | Can acknowledge after the business operation; remember the ack is cumulative per Session |
| Need to roll back the message when the listener fails and may send a response in the same transaction | SESSION_TRANSACTED / `sessionTransacted=true` | Commit/rollback covers the JMS input and output of the same Session |
| Need to coordinate the database and JMS in one atomic transaction | JTA/XA with DMLC and XA resources, or an outbox/inbox design | Coordinates multiple resources according to the reliability requirement |

For important business processing, the starting point is usually `sessionTransacted=true`, an idempotent consumer, bounded redelivery, and a DLQ. Then measure performance and tune according to real load.

## 13. Spring JMS Configuration Example with Transactions

Example configuration of `DefaultJmsListenerContainerFactory` using a local JMS transaction:

~~~java
package com.example.messaging;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
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

Listener:

~~~java
package com.example.messaging;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {
    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(destination = "orders.queue")
    public void handle(OrderPlaced event) {
        orderService.process(event);
    }
}
~~~

The example requires a JMS provider, a `ConnectionFactory` bean, the destination `orders.queue`, and a converter suited to the `OrderPlaced` payload. If `orderService.process` throws an exception, the listener container rolls back the local JMS transaction. If the method returns normally, the container commits. The broker decides the number of redeliveries and the DLQ according to the provider configuration.

This is a Spring integration configuration, not a standalone program with deterministic stdout; a real JMS environment is needed to observe ack/rollback. Test by deliberately throwing an exception before the commit, confirm that `JMSRedelivered`/the delivery count increases, and that after the configured number of retries the message goes to the DLQ.

## 14. Common Mistakes

- **Confusing `AUTO_ACKNOWLEDGE` with successful business processing:** with synchronous receive, the ack happens when `receive()` returns; the code afterwards may fail without the message being redelivered.
- **Assuming a raw JMS listener and the Spring listener container have the same timing:** DMLC and SMLC handle AUTO ack differently; the Spring container does not by default propagate listener exceptions to the provider.
- **Using `CLIENT_ACKNOWLEDGE` and thinking it acks only one message:** `Message.acknowledge()` acknowledges all messages delivered by the Session.
- **Processing multiple messages in parallel on the same Session:** a Session is designed for serial use; an ack can acknowledge other messages as well.
- **Forgetting to call `acknowledge()`:** the message is not acknowledged and may be redelivered when the Session recovers/closes.
- **Using `recover()` on a transacted Session:** use `rollback()` for a transaction; `recover()` is for a non-transacted Session.
- **Using DUPS_OK for non-idempotent side effects:** a duplicate can cause repeated business impact.
- **Catching the exception and returning normally in a transacted listener:** the container may commit because the listener finished successfully.
- **Assuming CLIENT_ACK sends a reply atomically with the receive:** client ack does not create a transaction covering other Session operations.
- **Assuming a JMS transaction includes JDBC:** a local JMS transaction only manages the JMS resources of the Session.
- **Assuming rollback guarantees infinite retry:** the broker may limit redelivery and move the message to a DLQ.
- **Using `JMSRedelivered` as a dedup key:** use a stable application event ID and store an inbox/dedup record.
- **Confusing acknowledgement with persistent delivery:** ack is the consumer state; persistence is the broker's policy for storing messages.

## 15. Design and Operations Checklist

1. Does the consumer receive synchronously or asynchronously? Exactly when does the ack happen?
2. Is the Session transacted? If not, is it using AUTO, CLIENT, or DUPS_OK?
3. With CLIENT_ACK, do you understand that the acknowledgement applies to all messages delivered by the Session?
4. Does the listener exception propagate out to cause a rollback, or is it caught and swallowed?
5. Is Spring using DMLC or SMLC? Is the AUTO ack timing appropriate?
6. Is a TaskExecutor used in SMLC so that acknowledgement happens before the listener?
7. Do you need to send a response in the same JMS transaction as the received message?
8. Do the database and JMS share a transaction coordinator, or do you need an outbox/inbox/XA?
9. Is the consumer idempotent and does it have a stable event ID?
10. Are the redelivery count, retry delay, and DLQ configured on the broker?
11. Are there alerts for poison messages, backlog, and DLQ depth?
12. Are crashes tested before/after the ack, the commit, the database commit, and broker recovery?

## 16. Takeaways

`AUTO_ACKNOWLEDGE` acknowledges automatically when synchronous `receive()` returns or a plain JMS listener finishes successfully; with the Spring listener container, DMLC and SMLC have different timing and listener exceptions are not propagated to the provider by default. `CLIENT_ACKNOWLEDGE` allows acknowledging after processing, but `Message.acknowledge()` applies to all messages delivered by the Session; `recover()` returns the unacknowledged messages to the receive flow. `DUPS_OK_ACKNOWLEDGE` reduces overhead through lazy acknowledgement and accepts duplicates. `SESSION_TRANSACTED` uses commit/rollback to acknowledge input and emit output in a single JMS transaction; in a Spring listener, `sessionTransacted=true` is the commonly used choice when reliable redelivery is needed. The database remains a separate resource unless XA/JTA is used; make the consumer idempotent, limit retries, and configure a DLQ.

### References

- [Jakarta Messaging 3.1 Specification — Sessions, Transactions and Message Acknowledgement](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#sessions)
- [Jakarta Messaging 3.1 — Message Acknowledgement](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#message-acknowledgment)
- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Receiving a Message and Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2.8 — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)