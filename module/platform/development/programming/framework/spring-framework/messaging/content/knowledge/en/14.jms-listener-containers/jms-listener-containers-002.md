# SimpleMessageListenerContainer and the Provider Callback Model

## 1. What is SimpleMessageListenerContainer?

`org.springframework.jms.listener.SimpleMessageListenerContainer` (SMLC) is a message listener container in Spring JMS. It connects the application to the JMS provider, creates `Session`s and `MessageConsumer`s, registers the listener, and lets the provider invoke the listener when a message arrives.

The defining characteristic of SMLC is that it uses the standard JMS callback: `MessageConsumer.setMessageListener(...)`. The provider manages receiving messages and invoking the callback. Spring manages the container configuration, the number of consumers, resource lifecycle, transaction/acknowledgement, exception handling, and recovery.

SMLC suits standalone applications or environments where the provider allows registering a `MessageListener` directly. It has a simple structure, a fixed number of consumers, and supports local JMS transactions. SMLC does not support dynamic scaling or participating in externally managed transactions; in Jakarta EE, it is generally not suitable given some of the container's JMS restrictions.

## 2. How does the provider callback model work?

SMLC does not run a `receive()` loop to actively fetch each message. On initialization, the container creates the JMS resources and registers the listener with each consumer. After that, the JMS provider invokes the listener when a message arrives.

General flow:

~~~text
Spring Application Context
          |
          v
SimpleMessageListenerContainer
          |
          +--> shared JMS Connection
          |
          +--> Session 1 --> MessageConsumer 1
          |                      |
          |                      +--> setMessageListener(listener)
          |
          +--> Session 2 --> MessageConsumer 2
                                 |
                                 +--> setMessageListener(listener)

JMS Provider receives a message
          |
          v
Provider invokes MessageListener.onMessage(message)
          |
          v
SMLC handles the callback and invokes the application listener
          |
          v
Complete acknowledgement or commit/rollback
~~~

With the default single-consumer configuration, the container creates one `Session` and one `MessageConsumer`. If three consumers are configured, the container creates three Session/Consumer pairs on the shared connection. Each consumer receives callbacks from the provider according to the provider's own mechanism.

During processing, SMLC invokes the listener through the internal pipeline of `AbstractMessageListenerContainer`. This pipeline handles exposing the session if configured, translating exceptions into the Spring mechanism, and applying acknowledgement/transaction according to the selected mode.

### 2.1. Who owns the thread that invokes the listener?

By default, SMLC does not configure a `TaskExecutor`. The listener runs directly on the JMS provider's message-receiving thread. While the listener executes, the provider's receiving endpoint is occupied until the callback finishes.

This means listener processing time directly affects the corresponding consumer's ability to receive the next message. A long-running listener can reduce that consumer's throughput. You can increase the number of consumers to process in parallel, but you must weigh message ordering and the load on the broker.

### 2.2. Connection, Session, and Consumer

SMLC always uses one shared JMS `Connection` for the container. It creates a fixed number of `Session`s and `MessageConsumer`s according to the concurrency configuration. A Session is tied to its corresponding consumer and is used throughout that consumer's lifecycle.

A JMS `Session` is not designed for arbitrary threads to operate on it concurrently. SMLC's default model keeps the relationship between callback and Session clear: the provider invokes the listener for a consumer, and the container processes the message with the corresponding Session. If a `TaskExecutor` is enabled, the thread and acknowledgement rules change significantly; read the dedicated section on the executor carefully.

## 3. The listener types SMLC can invoke

### 3.1. Jakarta JMS MessageListener

`jakarta.jms.MessageListener` is the standard JMS callback:

~~~java
public interface MessageListener {
    void onMessage(Message message);
}
~~~

The provider invokes `onMessage` when the consumer receives a message. The listener receives a JMS `Message` such as `TextMessage`, `BytesMessage`, `MapMessage`, or `ObjectMessage`, then reads the payload and performs the business logic.

This is a simple choice when the listener only needs the message content and does not need to operate directly on the `Session`.

### 3.2. Spring's SessionAwareMessageListener

Spring provides `org.springframework.jms.listener.SessionAwareMessageListener<M>` so that the listener receives both the message and the JMS `Session`:

~~~java
public interface SessionAwareMessageListener<M extends jakarta.jms.Message> {
    void onMessage(M message, jakarta.jms.Session session)
            throws jakarta.jms.JMSException;
}
~~~

The listener can use the Session passed in to create a response or perform related JMS operations. When `sessionTransacted=true`, sending a response through that same Session can be part of the same local JMS transaction as receiving the message.

Do not hold on to the Session after the callback ends and do not share the Session with other threads. In particular, do not combine `SessionAwareMessageListener` with dispatching callbacks concurrently through a `TaskExecutor` if the listener performs work on the Session passed in.

### 3.3. POJO listener via adapter

If you want the listener to be an ordinary business class instead of implementing a JMS interface, you can use `MessageListenerAdapter`. The adapter receives the JMS callback, converts the payload via the converter, and then invokes a method on the delegate object. You need to distinguish this adapter from the provider callback: the provider still invokes the listener that the container registered; the adapter is only a forwarding layer to the POJO method.

## 4. SMLC configuration and important properties

SMLC can be configured with Java, XML, or the Spring container. The properties that usually need consideration:

| Property | Default/meaning | When to adjust? |
| --- | --- | --- |
| `connectionFactory` | The JMS `ConnectionFactory` supplied by the provider/server | Always must be configured correctly for the provider and environment |
| `destinationName` or `destination` | The name or object of the Queue/Topic to listen on | Choose the correct provisioned destination |
| `messageListener` | The listener invoked by the provider | Use a `MessageListener`, `SessionAwareMessageListener`, or an appropriate adapter |
| `concurrentConsumers` | Default `1`; the fixed number of consumers created | Increase for a queue when you need throughput and accept parallel processing |
| `sessionTransacted` | Default `false` | Set to `true` when you need rollback and redelivery via a local JMS transaction |
| `sessionAcknowledgeMode` | Default `AUTO_ACKNOWLEDGE` | Choose an appropriate ack mode; `sessionTransacted=true` is usually preferred for reliability |
| `taskExecutor` | Default none; the listener runs on the provider thread | Use only when you clearly understand the changes to ack, Session, and concurrency |
| `connectLazily` | Default `false`; connects early during the initialization phase | Enable if you want to defer connecting until the container's start phase |
| `recoverOnException` | Default `true` | Disable when you deliberately rely on the provider's automatic recovery mechanism |
| `errorHandler` | No dedicated handler by default | Configure to record uncaught listener exceptions according to the application's policy |

`SimpleMessageListenerContainer` also accepts the `concurrency` string configuration, but it always creates a number of consumers equal to the upper bound and does not scale between the two bounds. With SMLC, you should use `setConcurrentConsumers(int)` directly to make the fixed number of consumers explicit.

### 4.1. Starting and stopping the container

SMLC implements the Spring lifecycle (`SmartLifecycle`). When the Spring context starts, the container is initialized and starts automatically under the default lifecycle configuration. You can control `start()`/`stop()` if you need to pause message reception.

On initialize, SMLC creates the shared connection and the corresponding Sessions/Consumers. On shutdown, the container closes the registered consumers and Sessions. Let Spring manage the bean's lifecycle instead of closing the Session or Consumer yourself inside the listener.

`connectLazily=true` defers establishing the connection, Sessions, and Consumers until the container's start phase. This property changes when the connection is made; it does not replace the retry/recovery mechanism when the broker loses its connection.

## 5. Concurrency: a fixed number of consumers

`setConcurrentConsumers(int)` specifies the number of consumers SMLC creates. The default is `1`. The consumers are created when the container initializes and stay fixed for the container's lifetime; SMLC does not increase or decrease the number of consumers according to the backlog.

With a queue, multiple consumers can receive messages from the same destination at the same time. This increases parallel processing capacity, but the overall processing order is no longer guaranteed. For example, the second message may finish being processed by consumer 2 before the first message at consumer 1.

With a topic, increasing the number of consumers can cause each consumer to receive the same publication. Therefore, do not increase `concurrentConsumers` for a topic unless you actually want multiple consumers/subscriptions to process copies of the publication.

Initial selection rules:

- Low-load queue, or one that needs to preserve processing order as closely as possible: start with one consumer.
- Queue that needs high throughput: increase consumers gradually and measure latency, backlog, DB load, and parallel-processing capacity.
- Topic: usually keep one consumer per subscription/container unless there is a clear reason to create multiple subscriptions receiving the same publication.

Container concurrency does not replace idempotency. The broker can redeliver the same message after a rollback or connection error; multiple consumers can also update related data at the same time. Concurrent processing and deduplication need to be designed at the business layer.

## 6. Acknowledgement and transactions

This is the section that needs the most careful configuration. By default SMLC uses `AUTO_ACKNOWLEDGE`. With SMLC, acknowledgement happens after the listener executes. If the listener throws a user exception, the message is not redelivered by default; redelivery is still possible if the JVM dies while the listener is running.

By default, Spring does not propagate the listener exception to the JMS provider as a failure callback. The container logs the exception and can invoke the configured `ErrorHandler`. Therefore, do not expect the provider to redeliver on its own just because the listener method throws an exception while `AUTO_ACKNOWLEDGE` is in use.

| Mode | Behavior in SMLC | Notes |
| --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | Acknowledges after listener execution | A business exception does not guarantee redelivery; a message can be lost if the listener fails or the container stops at an unfortunate moment |
| `DUPS_OK_ACKNOWLEDGE` | Lazily acknowledges right after listener execution | Does not guarantee redelivery when the listener throws an exception; duplicates can occur in some failure windows |
| `CLIENT_ACKNOWLEDGE` | The container acknowledges after the listener succeeds; redelivery on exception is best effort | Does not create a local transaction for other operations on the Session |
| `sessionTransacted=true` | Acknowledges/commits via the local JMS transaction after the listener succeeds; rolls back when the listener fails | Usually the recommended choice when you need reliability and consistent redelivery |

### 6.1. Local JMS transaction with sessionTransacted

Enable transactions for the Session:

~~~java
container.setSessionTransacted(true);
~~~

Each time the listener processes a message, it runs in a local JMS transaction. If the listener completes normally, the container commits the transaction. If the listener throws an exception out, the container rolls back; the provider can redeliver the message according to the broker's redelivery policy.

Do not catch an exception and ignore it if the business operation has not completed. For example, if the listener catches a `RuntimeException`, only logs it, and returns, the container sees the callback end normally and may commit the message. Let errors that need a rollback propagate out, or deliberately mark the transaction rollback-only using an appropriate mechanism.

### 6.2. CLIENT_ACKNOWLEDGE

`CLIENT_ACKNOWLEDGE` can provide best-effort redelivery when the listener throws an exception, but the Session is not a transacted Session. Other JMS operations on the Session, such as sending a reply, are not grouped into the same transaction protocol as with `sessionTransacted=true`.

If you need to receive a message, process it, and send a response as an atomic JMS unit, a local transacted Session is a better fit.

### 6.3. Database and JMS are two resources

`sessionTransacted=true` only manages the JMS Session's transaction. If the listener updates a database through JDBC, the database transaction is a different resource and does not automatically commit/roll back together with JMS.

For example, if the database commit succeeds but the JMS commit fails, the message can be redelivered; the consumer needs idempotency. Conversely, if the message is committed but the database rolls back because the transaction configuration is not coordinated, the business data may not reflect the processing result.

When you need to coordinate the database and JMS, you can consider a transactional outbox/inbox or a JTA/XA transaction manager with a supporting provider. SMLC does not participate in externally managed transactions; if you need an externally managed transaction/XA, see `DefaultMessageListenerContainer` and an appropriate XA configuration.

## 7. TaskExecutor: changing threads and acknowledgement

SMLC can accept a `TaskExecutor` to run the listener on an application-managed thread:

~~~java
container.setTaskExecutor(taskExecutor);
~~~

When there is no executor, the provider invokes the listener on the message-receiving thread, and that thread is occupied until the listener completes. When there is an executor, the provider callback hands the work to the executor so that the listener runs on a different thread.

This setup has a special consequence: the message is acknowledged before the listener executes, and the underlying Session is reused immediately to receive the next message. Combining a `TaskExecutor` with `sessionTransacted=true` or `CLIENT_ACKNOWLEDGE` leads to behavior that is undefined under SMLC's contract. Do not use that configuration when you need rollback/redelivery based on a listener exception.

An executor can also cause multiple messages received on the same Session to be processed concurrently. An ordinary `MessageListener`-style listener is usually more suitable; do not use `SessionAwareMessageListener` to operate on the Session in such concurrent callbacks.

If you use an executor, set limits for threads/queue, a rejection policy, and shutdown behavior. An unbounded executor can accumulate tasks when the producer is faster than the consumer, causing growing memory use and latency.

## 8. Exceptions, ErrorHandler, and connection recovery

You need to distinguish two groups of errors:

- **Message-processing errors:** the listener cannot parse the payload, violates a business rule, or a database call fails. `setErrorHandler(...)` can record uncaught exceptions during processing.
- **JMS connection/provider errors:** the provider reports a `JMSException` through an `ExceptionListener`. SMLC implements `ExceptionListener` and registers itself on the shared connection to detect connection errors.

By default `recoverOnException=true`: when the connection passes an exception to the listener, SMLC refreshes the shared connection and re-initializes the Sessions/Consumers. You can set it to `false` if you want to rely on the provider's automatic recovery and keep the existing handles; choose this only after verifying the recovery mechanism of the specific provider.

The container can be configured with an `ErrorHandler` to write logs or raise alerts:

~~~java
container.setErrorHandler(error ->
        logger.error("Uncaught exception in JMS listener", error));
~~~

The ErrorHandler serves observation and handling of errors at the application layer; it does not configure retry, redelivery, or a dead-letter queue by itself. Those policies belong to acknowledgement/transactions and the broker/provider.

For a message that cannot be processed (a poison message), you need a redelivery limit and a dead-letter queue at the broker. If it rolls back indefinitely, the same message can keep coming back and occupy the consumer. When resending or replaying, the consumer still needs idempotency.

## 9. How do SMLC and DefaultMessageListenerContainer differ?

Spring has two standard JMS listener containers. Both manage the listener, resources, and transaction/acknowledgement, but their receiving models differ.

| Criterion | SimpleMessageListenerContainer | DefaultMessageListenerContainer |
| --- | --- | --- |
| Receiving method | Registers `MessageConsumer.setMessageListener()`; the provider invokes the callback | A `MessageConsumer.receive()` loop coordinated by Spring |
| Consumers/sessions | A fixed number created at startup | Can be cached and adjusted according to configuration |
| Dynamic scaling | No | Yes |
| Receiving thread | The provider's callback thread by default | Task/invoker threads managed by Spring |
| Local JMS transaction | Yes, via `sessionTransacted=true` | Yes |
| External transaction/JTA | Not supported | Can participate when an appropriate transaction manager and resources are configured |
| Level of complexity | Simple, minimal requirements on the provider | More features and more configurability |
| Jakarta EE environment | Generally not suitable given some JMS restrictions | Usually more suitable |

Choose SMLC when you need a simple provider callback model, a fixed number of consumers, and a local JMS transaction is enough. Choose DMLC when you need scaling, recovery/polling coordinated by Spring, participation in an external transaction, or Jakarta EE environment integration.

## 10. Java 17 + Spring Framework 6.2 example

The example configures SMLC to receive text messages from a queue. The listener reads the content, checks the message type, and lets the exception propagate out so that the local JMS transaction rolls back.

This example needs a running JMS provider and a `ConnectionFactory` supplied from the provider/JNDI. Spring does not create the broker or queue by itself.

Project structure:

~~~text
simple-listener-container-demo/
  pom.xml
  src/main/java/com/example/messaging/JmsListenerConfiguration.java
  src/main/java/com/example/messaging/OrderMessageListener.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>simple-listener-container-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
        <jakarta.jms.version>3.1.0</jakarta.jms.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>${jakarta.jms.version}</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/JmsListenerConfiguration.java`:

~~~java
package com.example.messaging;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.listener.SimpleMessageListenerContainer;

@Configuration
public class JmsListenerConfiguration {

    @Bean
    public SimpleMessageListenerContainer ordersListenerContainer(
            ConnectionFactory connectionFactory,
            OrderMessageListener listener) {
        SimpleMessageListenerContainer container =
                new SimpleMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.queue");
        container.setMessageListener(listener);
        container.setConcurrentConsumers(2);
        container.setSessionTransacted(true);
        container.setRecoverOnException(true);
        return container;
    }
}
~~~

`src/main/java/com/example/messaging/OrderMessageListener.java`:

~~~java
package com.example.messaging;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import jakarta.jms.TextMessage;

import org.springframework.stereotype.Component;

@Component
public class OrderMessageListener implements MessageListener {

    @Override
    public void onMessage(Message message) {
        try {
            if (!(message instanceof TextMessage textMessage)) {
                throw new IllegalArgumentException(
                        "Expected TextMessage but received "
                                + message.getClass().getName());
            }

            String body = textMessage.getText();
            if (body == null || body.isBlank()) {
                throw new IllegalArgumentException("Order message body is empty");
            }

            System.out.println("received=" + body);
            processOrder(body);
        } catch (JMSException ex) {
            throw new IllegalStateException("Cannot read JMS message", ex);
        }
    }

    private void processOrder(String body) {
        // Perform the business logic; throw a RuntimeException if the JMS transaction must roll back.
    }
}
~~~

Spring manages the lifecycle of the container bean itself. The application needs to register an appropriate `ConnectionFactory` and make sure the queue `orders.queue` exists or the provider allows creating a queue by name.

When the provider delivers a text message, the listener writes a line of the form `received=OrderPlaced: ORD-2048`. The timing and number of lines depend on the actual messages, concurrency, and broker; the example does not give a fixed stdout because no specific broker is included.

In this configuration, two consumers can process in parallel. If `processOrder` throws a `RuntimeException`, `sessionTransacted=true` lets the container roll back the JMS transaction so the broker redelivers according to the redelivery policy. Configure a DLQ/redelivery limit at the provider and make `processOrder` idempotent.

## 11. Testing and observability

Testing SMLC needs to verify both the callback model and the failure semantics:

1. When the container starts, does the provider show the configured number of consumers?
2. Does a message arriving at the queue trigger `MessageListener.onMessage` without calling `receive()`?
3. With one consumer, does the callback run on the provider receive thread under the default configuration?
4. With multiple consumers, does the queue process in parallel and does the completion order change?
5. With `sessionTransacted=true`, does a successful listener commit and a listener that throws an exception roll back?
6. With `AUTO_ACKNOWLEDGE`, is SMLC's redelivery limitation correctly confirmed?
7. When the broker disconnects, do `ExceptionListener` and `recoverOnException` re-initialize the consumers?
8. When the context stops, are the consumers and Sessions closed?
9. If a `TaskExecutor` is used, is it confirmed that acknowledgement happens before the listener and that transacted/client ack is not used?
10. Is a poison message retried indefinitely or moved to the DLQ according to the broker policy?

Production observability should include the number of active consumers, receive/processing rate, listener time, exception count, redelivery count, DLQ depth, connection recovery, backlog, and the age of the oldest message. Do not log the entire payload if it contains sensitive data.

## 12. Common mistakes

- **Assuming SMLC polls with `receive()` by itself:** SMLC registers a `MessageListener` through `setMessageListener`; the provider invokes the callback.
- **Expecting the number of consumers to scale up and down automatically:** SMLC creates a fixed number of consumers; `setConcurrency("2-8")` does not create a dynamic scaling mechanism.
- **Increasing consumers on a topic without understanding the subscription:** each consumer may receive the same publication.
- **Using AUTO_ACKNOWLEDGE for processing that needs redelivery:** a listener exception does not guarantee the message comes back.
- **Catching and swallowing exceptions when using a transacted Session:** a normal callback return can cause the transaction to commit.
- **Expecting the database to roll back together with JMS:** a local JMS transaction does not automatically enlist a JDBC transaction.
- **Using TaskExecutor together with sessionTransacted or CLIENT_ACKNOWLEDGE:** the acknowledgement/session semantics are undefined.
- **Sharing a Session across multiple threads:** a JMS Session is not thread-safe; each consumer should work on its own Session.
- **Assuming ErrorHandler retries by itself:** ErrorHandler only handles uncaught exceptions at the application level; retry/DLQ is decided by the transaction and provider policy.
- **Using SMLC when JTA/XA is needed:** SMLC does not participate in an external transaction; consider DMLC.
- **Not configuring recovery or DLQ:** connection failure and poison messages can cause the listener to stop working or loop indefinitely.
- **Closing the ConnectionFactory/Session inside the listener:** the container owns the lifecycle of the resources it creates and manages.

## 13. Checklist for choosing and configuring SMLC

1. Does the JMS provider support the `MessageConsumer.setMessageListener` callback in the deployment environment?
2. Does the application need a fixed consumer count or dynamic scaling?
3. Is the destination a queue or a topic? Does the number of consumers fit the subscription semantics?
4. Does the listener run on the provider thread or does it need an executor? Is the acknowledgement caveat understood?
5. Is redelivery needed when the listener fails? If so, has `sessionTransacted=true` been enabled or an appropriate acknowledgement mode chosen?
6. Does the listener let exceptions that need a rollback propagate out?
7. Do the database and JMS need an outbox/inbox or JTA/XA?
8. Is `recoverOnException` appropriate for the provider's automatic recovery?
9. Are there a clear ErrorHandler, retry policy, and DLQ?
10. Does shutdown close the consumers/sessions and stop receiving messages correctly?
11. Are consumer count, processing latency, redelivery, and DLQ monitored?
12. Is the consumer idempotent so it can handle duplicates after a crash/retry?

## 14. Key takeaways

`SimpleMessageListenerContainer` creates a fixed number of JMS Sessions and MessageConsumers, registers the listener with `MessageConsumer.setMessageListener()`, and lets the JMS provider invoke the callback. By default the callback runs on the provider receive thread; a `TaskExecutor` can split off the thread but changes acknowledgement and is not suitable for transacted/client-ack Sessions under SMLC's contract. SMLC supports local JMS transactions via `sessionTransacted=true`, but does not support external transactions/JTA or dynamic scaling. `AUTO_ACKNOWLEDGE` does not guarantee redelivery when the listener throws an exception; for reliability requirements, prefer a transacted Session, configure redelivery/DLQ at the broker, and make the consumer idempotent. Choose `DefaultMessageListenerContainer` when you need Spring-managed polling, dynamic scaling, or participation in an external transaction.

### References

- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2.x — SimpleMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html)
- [Spring Framework 6.2.x — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework 6.2.x — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)