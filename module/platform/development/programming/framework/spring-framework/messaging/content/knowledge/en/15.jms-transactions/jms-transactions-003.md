# Acknowledgement Timing Depends on the Mode and the Listener Container Type

## Objectives

In JMS, receiving a message and acknowledging that the message was received are two different events. The acknowledgement timing depends on the acknowledgement mode of the JMS Session, on how the application receives messages, and on how the Spring listener container implements receiving.

The same `AUTO_ACKNOWLEDGE` configuration can have different acknowledgement timing between `SimpleMessageListenerContainer` and `DefaultMessageListenerContainer`. If you look only at the mode name without considering the container type, you may misjudge the redelivery capability and the reliability of the system.

After this lesson, you can:

- Distinguish delivery, listener completion, acknowledgement, commit, and rollback.
- Explain the four ways JMS manages acknowledgement.
- Determine the ack timing of synchronous receive, provider callbacks, and the Spring listener container.
- Compare `SimpleMessageListenerContainer` (SMLC) with `DefaultMessageListenerContainer` (DMLC).
- Understand the effect of `TaskExecutor` in SMLC.
- Configure `CLIENT_ACKNOWLEDGE` or a transacted session in Spring.
- Predict when a message is redelivered and when it may be lost.
- Design appropriate idempotency, retry, and dead-letter handling.
- Run a Spring Boot + embedded Artemis example to observe AUTO ack and transactional rollback.

## 1. Distinguishing Delivery, Processing, and Acknowledgement

A message can pass through several milestones:

1. The broker picks the message and delivers it to the consumer.
2. The JMS provider passes the message to the application.
3. The listener or the business code starts processing.
4. The business operation completes or an error occurs.
5. The client acknowledges the message, or the transaction commits/rolls back.
6. The broker removes the message from the delivery flow or prepares to deliver it again.

Terminology:

| Term | Meaning |
|---|---|
| Delivery | The provider delivers the message to the consumer/session. |
| Listener completion | The message-handling method has returned. |
| Acknowledgement (ack) | The client/session confirms it has received the message according to the mode in use. |
| Commit | Completes a JMS transaction; the input messages are acknowledged and the output messages in the transaction are sent. |
| Rollback | Cancels the JMS transaction; the input messages are recovered so they can be delivered again. |
| Redelivery | The provider delivers again a message that was not acknowledged or that was recovered after a rollback/recover. |

**An ack does not by itself prove that the business operation is complete.** If the message is acked before the handler updates the database, an error in the handler can make the message disappear from the queue while the business operation has not finished running.

Conversely, if the business operation has committed the database but the JMS transaction has not committed, the process can die and the message is delivered again. The consumer may then run the side effect a second time.

## 2. Acknowledgement Modes of Jakarta Messaging

The ack mode is configured on the JMS `Session` if the session is not transacted.

### AUTO_ACKNOWLEDGE

The provider acknowledges the message automatically:

- For synchronous receive, when the `receive()` call returns successfully.
- For an asynchronous `MessageListener`, after the `onMessage()` callback processes the message and returns successfully.

With synchronous receive, the application receives the message first, and only then runs the business logic after `receive()` returns. Therefore, the ack has already happened before the business processing that lies outside the receive call.

With a plain JMS asynchronous callback, the callback returning normally is the ack milestone. However, the Spring container can change the internal order by using polling receive or by catching exceptions itself; see the following sections.

### CLIENT_ACKNOWLEDGE

The application acknowledges the message by calling:

~~~java
message.acknowledge();
~~~

An easily overlooked point: according to JMS, calling `acknowledge()` on one message acknowledges **all messages delivered by the same Session** since the previous ack. It does not acknowledge only the message in hand.

If you need to acknowledge each message independently, you must consider the provider's capabilities and the product's own individual acknowledgement mode. This is not the standard semantics of `CLIENT_ACKNOWLEDGE`.

If you want to recover the session to the first unacknowledged message, you can call `session.recover()`. The provider begins redelivery from the point after the last acknowledged message.

### DUPS_OK_ACKNOWLEDGE

The provider is allowed to acknowledge messages in a deferred way (lazy acknowledgement) to reduce overhead.

In exchange, if the provider or the client fails, some messages that were delivered may be delivered again. The consumer must accept duplicates and process idempotently.

This mode suits cases where throughput matters and the business can tolerate duplicates. It is not a good choice if every message creates a side effect that must not be repeated.

### Transacted Session

When the Session is transacted, the ack is managed by the transaction:

- `commit()`: acknowledges the input messages of the transaction and finalizes the output messages sent in the transaction.
- `rollback()`: recovers the input messages so the provider can deliver them again; the output messages in the transaction are discarded.

With the Spring listener container, configuring `sessionTransacted=true` makes each listener invocation run in a local JMS transaction. If the listener completes successfully, the container commits; if the listener throws an exception, the container rolls back.

Do not set a non-transacted acknowledgement mode and expect it to control a transacted session. A transactional session uses commit/rollback to manage the ack.

## 3. Ack Timing by Way of Receiving Messages

The JMS specification describes the ack milestone by the receive API:

~~~mermaid
flowchart TD
    A["Broker delivers the message"] --> B{"Way of receiving"}
    B -->|Synchronous| C["receive()"]
    C --> D["receive() returns"]
    D --> E["AUTO ack"]
    E --> F["Application performs business processing"]
    B -->|Asynchronous| G["Provider calls onMessage()"]
    G --> H["Listener processes"]
    H --> I["onMessage() returns successfully"]
    I --> J["AUTO ack"]
~~~

With synchronous receive, if the application does the following:

~~~java
Message message = consumer.receive();
processBusinessLogic(message);
~~~

then under `AUTO_ACKNOWLEDGE`, the ack milestone is tied to `receive()` returning. If `processBusinessLogic` fails afterwards, the message has already been acknowledged and is not automatically delivered again just because the business operation failed.

With a plain asynchronous JMS callback, the provider calls `onMessage`; if the callback returns successfully, the message is acknowledged. If the callback throws a `RuntimeException`, the redelivery behavior under the JMS spec depends on the mode. But in Spring, the listener container usually catches the exception and applies the container's policy before the provider sees the callback finish.

## 4. Spring Changes the Ack Timing by Listener Container

Spring has two standard listener containers:

- `SimpleMessageListenerContainer` (SMLC).
- `DefaultMessageListenerContainer` (DMLC).

Both manage consumers, sessions, and listeners, but they receive messages in different ways.

### SimpleMessageListenerContainer

SMLC creates a fixed number of JMS Sessions and consumers when the container starts. It registers the listener through the standard API:

~~~java
messageConsumer.setMessageListener(listener);
~~~

The provider invokes the listener when a message arrives. If no `TaskExecutor` is configured, the callback runs in the provider's message-receiving thread.

With the default `AUTO_ACKNOWLEDGE`:

- The provider invokes the listener.
- The Spring container invokes the listener.
- The listener completes.
- The ack happens after the listener callback.

However, Spring's `AbstractMessageListenerContainer` by default catches listener exceptions, logs them, and does not propagate those exceptions to the provider. Because the provider does not see a failed callback, an ordinary business exception does not make SMLC redeliver automatically in AUTO mode.

If the JVM dies while the listener is running, before the callback completes, the provider may deliver the message again because the ack has not happened. This is a different situation from the listener throwing an exception that the container has caught and handled.

SMLC supports native JMS transactions via `sessionTransacted=true`, but does not participate in an external transaction the way DMLC does.

### DefaultMessageListenerContainer

DMLC is usually the common choice in Spring applications. Instead of registering a callback directly with the provider, it actively calls receive methods such as `MessageConsumer.receive()` in a polling loop and then dispatches the message to the listener.

With the default `AUTO_ACKNOWLEDGE`:

1. DMLC calls `receive()`.
2. `receive()` returns the message.
3. JMS automatically acks the message under synchronous receive semantics.
4. DMLC invokes the listener to process the message.

Because the ack has already happened before the listener is invoked, an exception in the listener cannot cause the message to be redelivered under AUTO mode.

DMLC can adjust concurrency according to load and participate in an external transaction when configured with an appropriate transaction manager, usually JTA/XA.

### Ack Timing Comparison Table

| Configuration | Ack milestone | Listener throws an exception |
|---|---|---|
| JMS synchronous receive + AUTO | When `receive()` returns, before the post-receive processing logic | The message is already acked; no automatic redelivery because of an error in the post-receive processing |
| JMS provider callback + plain AUTO | After `onMessage()` returns successfully | Per the JMS provider semantics; a failing callback may cause the provider to redeliver |
| SMLC + AUTO, no TaskExecutor | After the listener callback | Spring catches the exception, so a user exception does not create redelivery; a JVM death in the middle of the callback may lead to redelivery |
| DMLC + AUTO | Before invoking the listener, right after the polling receive | No redelivery when the listener fails |
| SMLC + AUTO + TaskExecutor | Before the listener task runs | A task that fails after the ack does not make the message redeliver on its own |
| SMLC/DMLC + DUPS_OK | Lazy ack during or right after processing, depending on the container | No redelivery due to a user exception; duplicates are possible when the process/provider fails |
| SMLC/DMLC + CLIENT_ACKNOWLEDGE | By default the Spring container acks after a successful listener | Best-effort redelivery when the listener fails or execution is interrupted |
| SMLC/DMLC + `sessionTransacted=true` | Commit after a successful listener | Rollback when the listener fails; the message is redelivered per the provider policy |

The table above describes the default behavior of the Spring container and the JMS mode. The provider, a custom listener container, a custom acknowledgement mode, or an executor can change the details.

## 5. Why Does AUTO_ACKNOWLEDGE Not Guarantee Reliable Processing?

The name `AUTO_ACKNOWLEDGE` easily gives the impression that the message will be acked only after the business operation completes. That is not true for every way of receiving.

With DMLC, the ack milestone is right after `receive()` and before the listener. If the listener fails to write to the database, the message has already been acked.

With SMLC, the ack comes after the provider callback, but the Spring container catches the exception and does not propagate it to the provider. Therefore a business exception also does not create redelivery on its own in AUTO mode.

Example:

~~~text
Broker delivers the message
        |
        v
Listener starts
        |
        v
Database update fails
        |
        v
Listener throws an exception
        |
        +---- DMLC + AUTO: the message was acked before the listener
        |
        +---- SMLC + AUTO: Spring catches the exception, the provider does not see a failed callback
~~~

If you need redelivery when the listener fails, use a transacted session or CLIENT_ACKNOWLEDGE according to the requirements and the specific semantics. Spring recommends `sessionTransacted=true` for most use cases that need reliability.

## 6. CLIENT_ACKNOWLEDGE in the Spring Container

Under standard JMS, the client calls `Message.acknowledge()`. But when using the Spring listener container, Spring usually manages the acknowledgement after the callback.

With `sessionAcknowledgeMode=CLIENT_ACKNOWLEDGE`, the Spring container by default acknowledges the message after the listener processes successfully. If the listener throws an exception, the container does not acknowledge the message and the provider may deliver it again when the session is recovered.

Configuration:

~~~java
container.setSessionAcknowledgeMode(Session.CLIENT_ACKNOWLEDGE);
~~~

Or with a factory:

~~~java
factory.setSessionAcknowledgeMode(Session.CLIENT_ACKNOWLEDGE);
~~~

Keep in mind:

- Spring describes redelivery in this mode as best-effort.
- Under standard JMS semantics, one `acknowledge()` acknowledges all messages delivered by the same Session.
- If the container manages the ack after the listener, do not casually call `message.acknowledge()` inside the listener at the same time.
- Since Spring Framework 6.2.6, `setAcknowledgeAfterListener(false)` is provided to turn off the automatic acknowledgement after the listener in situations that need manual/vendor-specific acknowledgement. Read the provider's Javadoc carefully if you use individual acknowledgement.

For a message listener that needs reliable processing, a local transacted session is usually easier to understand than managing CLIENT_ACKNOWLEDGE yourself.

## 7. DUPS_OK_ACKNOWLEDGE and Duplicate Delivery

`DUPS_OK_ACKNOWLEDGE` allows the provider to acknowledge messages later to reduce overhead. Spring describes the lazy ack timing as depending on the container:

- DMLC: lazy ack during listener execution.
- SMLC: lazy ack right after listener execution.

Do not choose this mode if the business operation cannot handle duplicates.

Some situations that can create duplicates:

- The JVM stops before the provider completes the ack.
- The provider loses the connection while the ack is being sent.
- The message is recovered after a session error.
- The consumer receives the message again because of the broker's redelivery policy.

Check the metadata:

- `message.getJMSRedelivered()`: indicates the message may have been delivered before.
- `JMSXDeliveryCount`: the number of times the provider delivered the message, if the provider supports this standard property.

These two fields are useful for observation and diagnosis. They do not replace the business idempotency key.

## 8. Transacted Session: Ack After Commit

When configured with:

~~~java
container.setSessionTransacted(true);
~~~

Spring creates a local JMS transaction for each message the listener processes.

Success flow:

~~~text
Receive message
      |
      v
Begin JMS transaction
      |
      v
Run listener
      |
      v
Listener returns successfully
      |
      v
Commit
      |
      v
Message acknowledged
~~~

Failure flow:

~~~text
Receive message
      |
      v
Begin JMS transaction
      |
      v
Run listener
      |
      v
Listener throws exception
      |
      v
Rollback
      |
      v
Message becomes eligible for redelivery
~~~

DMLC configuration:

~~~java
@Bean
DefaultMessageListenerContainer ordersContainer(
        ConnectionFactory connectionFactory,
        MessageListener listener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.queue");
    container.setMessageListener(listener);
    container.setSessionTransacted(true);
    return container;
}
~~~

Factory configuration for `@JmsListener`:

~~~java
@Bean
DefaultJmsListenerContainerFactory reliableJmsFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-8");
    return factory;
}
~~~

Usage:

~~~java
@JmsListener(
        destination = "orders.queue",
        containerFactory = "reliableJmsFactory"
)
public void handle(String orderId) {
    processOrder(orderId);
}
~~~

If `processOrder` throws an exception, Spring rolls back the JMS session. The provider may deliver the message again according to its redelivery policy.

SMLC also supports native JMS transactions via `sessionTransacted=true`. SMLC does not participate in an external transaction the way DMLC does.

## 9. SMLC and TaskExecutor: An Important Exception

By default SMLC runs the listener in the provider's callback thread. You can configure a `TaskExecutor` to move listener execution to another thread:

~~~java
container.setTaskExecutor(taskExecutor);
~~~

This decouples the provider receiving messages from the time the listener takes to process. But it also changes the acknowledgement semantics:

- The message is acked before the listener task runs.
- The Session is reused immediately to receive the next message.
- The listener may process multiple messages received from the same Session concurrently.
- Combining this TaskExecutor with a transacted session or CLIENT_ACKNOWLEDGE leads to results that are not well specified.

Therefore, do not use the SMLC `TaskExecutor` as a simple way to increase concurrency while still expecting the transaction/ack semantics to stay the same.

If you need more consumers, configure an appropriate number of consumers on the container and balance it against the downstream's processing capacity. If you need a reliable transaction, prefer a container/session configured as transacted.

## 10. Exception Handling and Redelivery

Spring's `AbstractMessageListenerContainer` by default catches exceptions thrown by the listener, logs them at WARN level, and does not propagate those exceptions to the JMS provider. The container can be configured with an `ErrorHandler` to handle application errors.

Example:

~~~java
container.setErrorHandler(error ->
        log.error("JMS listener failed", error)
);
~~~

Do not confuse the ErrorHandler with acknowledgement:

- The ErrorHandler records or dispatches the error.
- The acknowledgement mode/transaction decides whether the message has been acknowledged.
- The provider's redelivery policy decides the number of redeliveries, the delay, and the dead-letter handling.

In DMLC's AUTO mode, the ErrorHandler is called after the message has been acked. Logging the error cannot bring the message back to life.

In a transacted session, a listener exception causes the transaction to roll back. The broker may deliver the message again. The number of redeliveries, the delay, the delivery limit, and the dead-letter queue depend on the provider.

A poison message can cause a rollback/redelivery loop. You need to configure a delivery limit, backoff, and a DLQ/quarantine according to the broker product.

## 11. Local JMS Transaction and Database Transaction

`sessionTransacted=true` manages the transaction of the JMS Session. It can group messages received and messages sent through the same session into one unit of work.

For example, a listener receives OrderCreated and then sends InventoryReservationRequested through the same session. If they use the same session and transaction, the commit acknowledges the input and finalizes the output; the rollback recovers the input and discards the output.

But an independent database transaction does not automatically participate in the local JMS transaction.

A failure window:

1. The listener updates the database successfully and the database commits.
2. The process dies before the JMS transaction commits.
3. The broker delivers the message again.
4. The listener runs again and may update the database a second time.

To handle this:

- Use an idempotency key/event ID to recognize a message that has already been applied.
- Store an inbox/processed-message record in the same database transaction as the business operation.
- Use a transactional outbox for the direction of publishing from the database to the broker.
- Use XA/JTA only when a distributed transaction is truly needed and the infrastructure supports it.

DMLC can participate in an external JTA transaction if configured with a transaction manager and an XA-capable ConnectionFactory. SMLC does not support an external transaction in that way.

## 12. Configuration Selection Table by Requirement

| Requirement | Configuration to consider | Reason |
|---|---|---|
| Simple receiving, accepting message loss when the handler fails | AUTO_ACKNOWLEDGE | Simple configuration, but you need to understand the container's timing |
| A queue that needs redelivery when the handler throws an exception | `sessionTransacted=true` | Rolls back the transaction when the listener fails |
| A durable topic subscription that needs reliable processing | `sessionTransacted=true` with a durable subscription | The message is committed/rolled back along with the transaction |
| Want to use explicit acknowledgement | CLIENT_ACKNOWLEDGE | The client/container controls the ack; you must understand ack per Session |
| Prioritize throughput and tolerate duplicates | DUPS_OK_ACKNOWLEDGE | The provider can ack lazily |
| Need to coordinate JMS and the database in one transaction | DMLC + JTA/XA | Receipt and the database work can commit/roll back together |
| Only need synchronous receiving in a piece of code | `JmsTemplate.receive(...)` | The calling thread waits for the message; AUTO ack happens when receive returns |
| Want a simple provider callback | SMLC | Close to the JMS provider callback; fixed number of consumers |
| Need scaling, recovery, and external transactions | DMLC | Has a polling loop, dynamic adaptation, and JTA support |

For most listeners that need reliable processing, start with DMLC or the appropriate default factory and `sessionTransacted=true`. Then measure throughput, latency, and redelivery to tune the concurrency.

## 13. A Runnable Java 17+ Example: Observing AUTO Ack and Transaction Rollback

This example uses Spring Boot 4.1.2 and embedded ActiveMQ Artemis. Two DMLCs receive messages from two queues:

- `auto.queue` uses the default AUTO_ACKNOWLEDGE. The listener throws an exception the very first time. Because DMLC acks after the polling receive and before the listener, the message is not delivered again.
- `tx.queue` uses `sessionTransacted=true`. The listener throws an exception the first time. Spring rolls back the transaction, the broker delivers the message again, and the listener succeeds the second time.

The example lets you directly observe that the ack timing depends on the container and the session mode.

### Project Structure

~~~text
jms-ack-timing-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          AckTimingDemoApplication.java
          AckProbe.java
      resources/
        application.properties
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>jms-ack-timing-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>

        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=auto.queue,tx.queue
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

The embedded broker uses memory for the demo. Do not use this configuration to infer the durability of a production broker.

### AckProbe.java

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.jms.JMSException;
import jakarta.jms.Message;

import org.springframework.stereotype.Component;

@Component
public class AckProbe {

    private final AtomicInteger autoAttempts = new AtomicInteger();
    private final AtomicInteger txAttempts = new AtomicInteger();
    private final AtomicBoolean txRedelivered = new AtomicBoolean();
    private final CountDownLatch completed = new CountDownLatch(2);

    public void onAutoMessage(Message message) {
        autoAttempts.incrementAndGet();

        try {
            throw new IllegalStateException("simulated AUTO listener failure");
        }
        finally {
            completed.countDown();
        }
    }

    public void onTransactedMessage(Message message) {
        int attempt = txAttempts.incrementAndGet();

        if (attempt == 1) {
            throw new IllegalStateException("simulated first-attempt failure");
        }

        try {
            txRedelivered.set(message.getJMSRedelivered());
        }
        catch (JMSException ex) {
            throw new IllegalStateException("Cannot inspect redelivery flag", ex);
        }

        completed.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return completed.await(timeout, unit);
    }

    public int autoAttempts() {
        return autoAttempts.get();
    }

    public int txAttempts() {
        return txAttempts.get();
    }

    public boolean txRedelivered() {
        return txRedelivered.get();
    }
}
~~~

### AckTimingDemoApplication.java

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@SpringBootApplication
public class AckTimingDemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(AckTimingDemoApplication.class, args)) {
            // ApplicationRunner waits for both listener outcomes.
        }
    }

    @Bean
    DefaultMessageListenerContainer autoAckContainer(
            ConnectionFactory connectionFactory,
            AckProbe probe) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("auto.queue");
        // Default mode is AUTO_ACKNOWLEDGE.
        container.setMessageListener(probe::onAutoMessage);
        return container;
    }

    @Bean
    DefaultMessageListenerContainer transactedContainer(
            ConnectionFactory connectionFactory,
            AckProbe probe) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("tx.queue");
        container.setSessionTransacted(true);
        container.setMessageListener(probe::onTransactedMessage);
        return container;
    }

    @Bean
    ApplicationRunner sendMessages(
            JmsTemplate jmsTemplate,
            AckProbe probe) {

        return args -> {
            jmsTemplate.convertAndSend("auto.queue", "AUTO");
            jmsTemplate.convertAndSend("tx.queue", "TRANSACTED");

            if (!probe.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for acknowledgement demo"
                );
            }

            System.out.println("AUTO attempts=" + probe.autoAttempts());
            System.out.println("TRANSACTED attempts=" + probe.txAttempts());
            System.out.println("TRANSACTED redelivered=" + probe.txRedelivered());
        };
    }
}
~~~

Run with Java 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

The stdout lines printed by the application (ignoring the startup logs and the WARN from the listener deliberately throwing an exception):

~~~text
AUTO attempts=1
TRANSACTED attempts=2
TRANSACTED redelivered=true
~~~

Explanation:

1. The DMLC of `auto.queue` receives the message via polling receive. The AUTO ack happens when receive returns, before the listener.
2. The AUTO listener throws an exception. The Spring container records the error, but the message has already been acked so the broker does not deliver it again. The number of times the listener is invoked is 1.
3. The DMLC of `tx.queue` receives the message in a local JMS transaction.
4. The first invocation throws an exception. The container rolls back the transaction.
5. The broker delivers the message again. The JMS redelivery flag is set to true.
6. The second invocation succeeds. The container commits the transaction and the message is acknowledged.
7. The result shows that DMLC's default AUTO can lose a message when the listener fails; a transacted session allows redelivery.

The example uses a deliberate error to observe the behavior. In production, limit redelivery, configure a DLQ, and handle poison messages to avoid infinite rollback.

## 14. Failure Window and Idempotency

Even when using a transacted session, duplicates can still appear at certain moments.

Example:

~~~text
Listener receives the message
       |
       v
Database commit succeeds
       |
       v
JVM stops before the JMS commit
       |
       v
Broker rolls back/recovers the message
       |
       v
Message is delivered again
       |
       v
Listener may update the database again
~~~

A JMS transaction only covers the JMS operations in the session. It does not automatically cover the database transaction.

An idempotent consumer should have a stable event ID or business key. Before performing a side effect, the consumer checks whether the message has already been processed; the processed state and the business change should be written in the same database transaction.

If you require atomicity between JMS and the database, DMLC can participate in JTA/XA when both the ConnectionFactory and the database support XA. XA increases operational cost and needs a transaction coordinator. For many systems, a transactional outbox/inbox and an idempotent consumer are the more practical approach.

## 15. Redelivery, Retry, and Dead-Letter Queue

Ack/rollback only decides whether the message is acknowledged or recovered. The provider/broker decides the specific redelivery policy:

- Maximum number of redeliveries.
- Redelivery delay and backoff.
- Message expiration.
- Dead-letter address/queue.
- How poison messages are handled.
- Headers or properties that track the delivery count.

Do not assume every broker has the same policy. Check the documentation and configuration of Artemis, ActiveMQ Classic, IBM MQ, or whichever provider you use.

When handling errors:

- Transient infrastructure errors: bounded retry with backoff.
- Malformed or permanently invalid data: move to the DLQ/quarantine after an appropriate number of attempts.
- Recoverable business errors: publish a status/retry event according to the contract.
- Duplicate messages: the idempotency key protects the side effect.

Monitor `JMSRedelivered`, `JMSXDeliveryCount`, queue depth, DLQ depth, listener exception rate, and processing latency.

## 16. Common Mistakes

| Symptom | Cause | How to fix |
|---|---|---|
| DMLC does not redeliver when the listener throws an exception | The AUTO ack already happened after the polling receive and before the listener | Use `sessionTransacted=true` or an appropriate mode |
| SMLC does not redeliver even though the listener throws an exception | Spring catches the exception and does not propagate it to the provider in AUTO mode | Use a transacted session if redelivery is needed |
| SMLC loses messages when a TaskExecutor is enabled | The message is acked before the listener task runs | Do not use a TaskExecutor this way if you need a transaction/client ack |
| The message is delivered again after the database has committed | The JMS commit failed or the process died before the commit | Use idempotency/inbox, or XA when needed |
| Many messages are acked at once in CLIENT_ACKNOWLEDGE | The JMS ack applies to all messages delivered by the Session | Design sessions/consumers appropriately; use the provider's individual ack if truly needed |
| DUPS_OK produces duplicates | The provider defers the ack | The consumer must be idempotent |
| The listener fails but the broker does not see the exception | The Spring container catches/logs the listener exception | Check the ErrorHandler and the transaction mode |
| The message repeats indefinitely | Rollback/redelivery has no limit | Configure retry, backoff, and a DLQ |
| The AUTO ack happens before processing even though the JMS spec says after the callback | DMLC uses synchronous polling receive internally | Understand the specific semantics of each container |

## 17. Acknowledgement Configuration Checklist

- [ ] Determine whether the application receives messages synchronously or asynchronously.
- [ ] Determine whether the container is SMLC or DMLC.
- [ ] Check whether a `TaskExecutor` is configured for SMLC.
- [ ] Do not assume AUTO_ACKNOWLEDGE always acks after the listener.
- [ ] If a failing listener must cause redelivery, prefer `sessionTransacted=true`.
- [ ] If using CLIENT_ACKNOWLEDGE, understand that the standard ack has Session-wide scope.
- [ ] If using DUPS_OK_ACKNOWLEDGE, prepare to handle duplicates.
- [ ] Configure an ErrorHandler and observe listener exceptions.
- [ ] Configure the provider's redelivery limit, backoff, and DLQ.
- [ ] The consumer has an idempotency key or a processed-message record.
- [ ] Test listener exceptions, JVM shutdown, and broker reconnect.
- [ ] If combining the database and JMS, decide clearly between a local transaction, XA/JTA, or an outbox/inbox.

## Key Takeaways

- JMS AUTO ack happens when synchronous `receive()` returns or when asynchronous `onMessage()` returns successfully.
- DMLC uses polling receive, so the AUTO ack happens before the listener executes.
- SMLC uses a provider callback so the AUTO ack happens after the callback; Spring catches the exception, so a user exception does not create redelivery on its own.
- SMLC with a TaskExecutor acks before the listener task; combining it with transacted/client ack gives results that are not well specified.
- Standard CLIENT_ACKNOWLEDGE acknowledges all messages delivered by the same Session when `acknowledge()` is called.
- DUPS_OK_ACKNOWLEDGE acknowledges lazily and allows duplicates.
- `sessionTransacted=true` commits after a successful listener and rolls back when the listener throws an exception; the provider may redeliver.
- A local JMS transaction does not automatically include the database transaction; you need idempotency or XA/outbox/inbox.
- An ack is a delivery confirmation, not proof that the business operation has completed.

## Official Documentation

- [Jakarta Messaging 3.1 Specification — Transactions and acknowledgement](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#transactions)
- [Jakarta Messaging 3.1 Specification — Message acknowledgement, section 6.2.10](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta Messaging 3.1 Specification — Receiving messages asynchronously, section 8.7](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework 7.0.10 Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/receiving.html)
- [Spring Framework 7.0.10 Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/using.html)
- [Spring Framework 7.0.10 Javadoc — AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework 7.0.10 Javadoc — SimpleMessageListenerContainer](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html)
- [Spring Framework 7.0.10 Javadoc — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework Javadoc — JmsTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
