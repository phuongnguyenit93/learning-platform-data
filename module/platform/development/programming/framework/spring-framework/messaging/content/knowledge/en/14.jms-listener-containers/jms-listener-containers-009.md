# ExceptionListener and ErrorHandler at Different Error Layers

## Goals

After this lesson, you can:

- Distinguish connection errors detected by the JMS provider from errors that occur while processing a message.
- Explain the contract of `jakarta.jms.ExceptionListener` and the `onException(JMSException)` callback.
- Configure `ExceptionListener` and `org.springframework.util.ErrorHandler` on a Spring JMS listener container.
- Understand why a `JMSException` in a listener can be forwarded to both callbacks, in a deterministic order.
- Recognize the case that invokes only `ErrorHandler`, the case that invokes only `ExceptionListener`, and the case that invokes both.
- Distinguish error-reporting callbacks from rollback, acknowledgement, redelivery, and recovery mechanisms.
- Choose the appropriate configuration for `SimpleMessageListenerContainer`, `DefaultMessageListenerContainer`, and `@JmsListener`.

## 1. There are multiple error layers in a JMS flow

A Spring JMS application can encounter errors at multiple boundaries:

~~~text
Application
   |
   v
Spring MessageListenerContainer
   |
   +---- receive message and invoke listener
   |          |
   |          +---- listener throws RuntimeException
   |          |          |
   |          |          v
   |          |      Spring ErrorHandler
   |          |
   |          +---- listener / invocation infrastructure throws JMSException
   |                     |
   |                     v
   |               Spring ExceptionListener
   |                     |
   |                     v
   |               Spring ErrorHandler
   |
   v
JMS Connection
   |
   +---- provider detects a serious connection error
                |
                v
        jakarta.jms.ExceptionListener
                |
                v
        container/provider recovery
~~~

Two callback names that are easily confused:

- **`ExceptionListener`** belongs to Jakarta Messaging, receives `JMSException`, and is usually used to report connection-level issues. The Spring listener container also uses this same interface to report a `JMSException` arising during listener invocation or infrastructure.
- **`ErrorHandler`** belongs to Spring Framework, and receives a `Throwable` when an unhandled exception escapes from message processing.

Both can be invoked for the same error, but their responsibilities differ. `ExceptionListener` is not a catch-all for business errors; `ErrorHandler` is not a callback dedicated to monitoring the JMS provider's connection state.

## 2. Jakarta ExceptionListener: Connection-level errors

Interface:

~~~java
package jakarta.jms;

public interface ExceptionListener {
    void onException(JMSException exception);
}
~~~

A JMS provider invokes `onException` when the provider detects a serious problem with the `Connection` and the application has registered a listener:

~~~java
Connection connection = connectionFactory.createConnection();

connection.setExceptionListener(exception -> {
    System.err.println(
            "JMS connection problem: "
                    + exception.getErrorCode()
                    + " - "
                    + exception.getMessage()
    );
});

connection.start();
~~~

This is an asynchronous notification. It is useful for a receive-only consumer, because the application thread may be waiting for a message and there is no synchronous JMS call to return the connection error to the caller.

### What Connection-level ExceptionListener reports

Examples depending on the provider:

- The connection is lost due to a broker restart or network disconnect.
- The broker closes the connection due to a protocol error or server-side error.
- The connection is no longer available and the provider needs to notify the client.
- Other serious errors where the provider has no suitable synchronous call to return them from.

The JMS specification requires the provider to attempt to resolve connection problems on its own before notifying the client.

### What it does not report

`Connection.ExceptionListener` is not the place that receives every `JMSException`:

- If a call such as `connection.createSession()`, `session.createConsumer()`, or `producer.send()` throws a `JMSException` directly, that exception is returned to the caller of that call.
- According to the Jakarta Messaging specification, an exception already thrown from an API call must not also be delivered to `Connection.ExceptionListener`.
- Business data validation errors such as `IllegalArgumentException` are not connection failure events.
- The callback does not receive the faulty payload or business message; it receives a `JMSException` describing the connection problem.

A Connection serializes invocations of its own listener: the same connection does not run `onException` concurrently multiple times. However, if the same listener instance is registered on multiple connections, those connections can invoke the listener concurrently on multiple threads.

### What to do in the callback

Keep the callback concise:

~~~java
connection.setExceptionListener(exception -> {
    connectionHealth.markUnavailable(exception);
    metrics.increment("jms.connection.failure");
    alertPublisher.publishConnectionFailure(exception);
});
~~~

Do not run a reconnect loop or long blocking work directly inside the callback. Let the provider or listener container perform recovery according to its configured mechanism; the callback mainly records state, logs, metrics, and triggers alerts.

## 3. Spring ErrorHandler: errors while processing a Message

Spring uses the interface:

~~~java
package org.springframework.util;

@FunctionalInterface
public interface ErrorHandler {
    void handleError(Throwable t);
}
~~~

`ErrorHandler` receives any `Throwable` that is not handled by the listener and escapes from processing a message. Because it accepts `Throwable`, it can receive:

- `IllegalArgumentException`, `IllegalStateException`, or business exceptions.
- `MessageConversionException` or errors from conversion code.
- A `JMSException` thrown from the listener or invocation infrastructure.
- A runtime exception wrapped around another exception.

The Spring JMS listener container provides:

~~~java
container.setErrorHandler(error -> {
    logger.error("Uncaught error while processing a JMS message", error);
});
~~~

Common purposes:

- Write logs with stack traces.
- Count listener failures.
- Send alerts or emit operational events.
- Classify errors to support investigation.
- Record metrics by exception type.

`ErrorHandler` does not automatically retry the message, acknowledge the message, roll back the transaction, or send the message to a dead-letter queue. Those decisions belong to the container's transaction/acknowledgement and the broker's redelivery policy.

### Default when no ErrorHandler is registered

If no `ErrorHandler` is configured, the Spring listener container logs the error at warning level itself when the listener fails. By default, the container does not propagate the exception from the listener back up to the JMS provider so that the provider treats the listener as failed.

This is very important: the provider may not know that the listener threw an exception. If you need redelivery, configure an appropriate transaction/acknowledgement instead of expecting the provider to see the exception from the listener.

## 4. When is ExceptionListener invoked, and when is ErrorHandler invoked?

For `AbstractMessageListenerContainer`, Spring specifies:

- `setExceptionListener(...)`: the JMS `ExceptionListener` callback is invoked when the registered listener or invocation infrastructure throws a `JMSException`.
- `setErrorHandler(...)`: the Spring `ErrorHandler` callback is invoked for any unhandled exception escaping during the processing of a `Message`.
- If that exception is a `JMSException`, Spring invokes `ExceptionListener` first, and then invokes `ErrorHandler`.

| Scenario | Spring ExceptionListener | Spring ErrorHandler |
|---|---|---|
| Listener throws `IllegalArgumentException` | No | Yes |
| Listener throws `IllegalStateException` | No | Yes |
| Listener or invocation infrastructure throws `JMSException` | Yes, first | Yes, second |
| JMS provider reports a connection failure via the Connection callback | Can be delegated by the container | Not directly |
| Synchronous JMS call outside the listener throws `JMSException` | Not automatically | Not automatically; the caller must handle it |

A point of confusion: the Spring listener container has a `setExceptionListener` property with the same `jakarta.jms.ExceptionListener` type as `Connection.setExceptionListener`, but Spring also actively invokes this callback for `JMSException` errors from the listener/invocation infrastructure. Do not infer that every call to `onException` was made by the broker.

### Runtime exception: ErrorHandler only

~~~java
container.setExceptionListener(exception ->
        logger.error("JMSException callback: {}", exception.getMessage())
);

container.setErrorHandler(error ->
        logger.error("Message processing failed", error)
);

container.setMessageListener(message -> {
    throw new IllegalArgumentException("Invalid order payload");
});
~~~

For the `IllegalArgumentException` error, Spring invokes `ErrorHandler`. There is no `JMSException`, so `ExceptionListener` is not invoked.

### JMSException: ExceptionListener first, ErrorHandler second

`SessionAwareMessageListener` is a Spring-specific interface that allows the listener to also receive the JMS `Session` and declare `throws JMSException`:

~~~java
container.setMessageListener((SessionAwareMessageListener) (message, session) -> {
    throw new JMSException("Cannot process JMS message");
});
~~~

With a listener like the one above, Spring invokes in order:

~~~text
listener throws JMSException
          |
          v
ExceptionListener.onException(jmsException)
          |
          v
ErrorHandler.handleError(jmsException)
~~~

If `ExceptionListener` is not configured, Spring skips this callback step and still invokes `ErrorHandler` if present. If `ErrorHandler` is not configured, the container logs the error itself.

## 5. Configuring both callbacks on the listener container

You can configure them directly with `DefaultMessageListenerContainer`:

~~~java
@Bean
public DefaultMessageListenerContainer ordersContainer(
        ConnectionFactory connectionFactory,
        MessageListener ordersListener,
        ErrorHandler jmsErrorHandler,
        ExceptionListener jmsExceptionListener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();

    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.queue");
    container.setMessageListener(ordersListener);

    container.setExceptionListener(jmsExceptionListener);
    container.setErrorHandler(jmsErrorHandler);

    // Local transaction for receiving and processing the message.
    container.setSessionTransacted(true);

    return container;
}
~~~

The two callback beans can be defined as follows:

~~~java
@Bean
public ErrorHandler jmsErrorHandler() {
    return error -> {
        log.error("JMS listener processing failed", error);
        metrics.counter(
                "jms.listener.processing.errors",
                "exception",
                error.getClass().getSimpleName()
        ).increment();
    };
}

@Bean
public ExceptionListener jmsExceptionListener() {
    return exception -> {
        log.error(
                "JMS exception reported by listener/container: code={}, message={}",
                exception.getErrorCode(),
                exception.getMessage(),
                exception
        );
    };
}
~~~

Set `sessionTransacted=true` if you need rollback and redelivery when the listener fails. Configuring callbacks does not replace transactions.

### Using with @JmsListener

If the application uses annotation-driven listeners, you can set both callbacks on `DefaultJmsListenerContainerFactory`. Endpoints created from the factory will inherit this configuration:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            ErrorHandler jmsErrorHandler,
            ExceptionListener jmsExceptionListener) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setErrorHandler(jmsErrorHandler);
        factory.setExceptionListener(jmsExceptionListener);

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void handle(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        orderService.process(orderId);
    }
}
~~~

`IllegalArgumentException` in the example is sent to `ErrorHandler`. If a listener using `SessionAwareMessageListener` or the invocation infrastructure throws a `JMSException`, Spring also invokes `ExceptionListener` before ErrorHandler.

## 6. Connection ExceptionListener and Spring container ExceptionListener

An application can manage a JMS Connection itself:

~~~java
Connection connection = connectionFactory.createConnection();

try {
    connection.setExceptionListener(exception -> {
        logger.error("Provider reported a connection failure", exception);
    });

    connection.start();

    // Create Session / Consumer and perform work here.
}
finally {
    connection.close();
}
~~~

When an application uses a listener container, the container usually owns the connection, session, and consumer. Do not grab the internal connection and replace `Connection.ExceptionListener` yourself, as this can overwrite the listener used for the container's recovery.

### SimpleMessageListenerContainer

`SimpleMessageListenerContainer`:

- Registers the container as the `ExceptionListener` on the shared JMS Connection.
- When the provider reports a connection failure, the container invokes the application-configured `ExceptionListener` callback.
- By default, the container attempts to refresh the shared connection and re-initialize the session/consumer through `recoverOnException`.
- You can set `setRecoverOnException(false)` if you want to rely on the provider's recovery mechanism.

In addition to this connection callback path, when the listener/invocation infrastructure throws a `JMSException`, the superclass `AbstractMessageListenerContainer` also invokes the user-configured `ExceptionListener` and then `ErrorHandler`.

### DefaultMessageListenerContainer

`DefaultMessageListenerContainer` uses a polling model with `MessageConsumer.receive(...)`, combining a TaskExecutor, concurrency, and its own recovery mechanism. It still provides `setExceptionListener` to receive `JMSException` from the listener/invocation infrastructure and `setErrorHandler` to receive uncaught processing exceptions.

The connection recovery mechanisms of the two containers differ in implementation details. If you use a Spring-managed container, let the container own the connection and configure callbacks through the container or factory.

## 7. ErrorHandler does not decide acknowledgement and redelivery

Error-reporting callbacks and transactions are two separate mechanisms.

Spring JMS listener containers support the main acknowledgement modes:

| Configuration | Meaning when the listener fails |
|---|---|
| `AUTO_ACKNOWLEDGE` | Behavior depends on the container; with DefaultMessageListenerContainer, the message is acknowledged before the listener and there is no redelivery when the listener throws an exception |
| `DUPS_OK_ACKNOWLEDGE` | Lazy acknowledgement; user exceptions do not by themselves guarantee redelivery |
| `CLIENT_ACKNOWLEDGE` | The container acknowledges after successful processing; redelivery is best-effort when the listener fails |
| `sessionTransacted=true` | Acknowledges per transaction; listener failure triggers rollback and guarantees redelivery under the JMS transaction |

With `DefaultMessageListenerContainer`, the default `AUTO_ACKNOWLEDGE` acknowledges before the listener executes. Therefore, the message may already be acknowledged even though the listener throws an exception. With `SimpleMessageListenerContainer`, the default acknowledges after the listener, yet a user exception still does not guarantee redelivery.

When reliable processing is needed, Spring recommends using `sessionTransacted=true` if no external transaction coordinator is required:

~~~java
container.setSessionTransacted(true);
~~~

When the listener throws an exception:

1. The container rolls back the JMS transaction.
2. The exception is forwarded to the appropriate callback.
3. The broker can redeliver the message according to the transaction and redelivery policy.
4. The consumer can receive the same message again.

Because a message can be redelivered, the listener should be idempotent. Use an `eventId` or business key to detect that an event has already been processed; configure a redelivery limit, backoff, and dead-letter queue at the broker.

`ErrorHandler.handleError()` only observes the exception. Returning normally from the callback does not mean the message succeeded or was committed. The container has already decided rollback/acknowledgement according to the session and transaction.

### JMS and the database do not automatically form one transaction

`sessionTransacted=true` creates a local JMS transaction. If the listener has already committed the database while JMS rolls back, the message can be redelivered and the database operation may repeat.

To achieve consistency between JMS and the database, you need XA/JTA with a supporting provider or an Outbox/inbox design with idempotency. Do not assume ErrorHandler can synchronize commit/rollback across two systems.

## 8. Complete Java 17 example: JMSException, both callbacks, and redelivery

The example uses Java 17, Spring Framework 6.2.19, and ActiveMQ Classic 6.2.6. The broker runs embedded in the same JVM. The listener intentionally throws a `JMSException` on the first receive; the transaction rollback causes the broker to redeliver the message. On the next attempt, the listener processes it successfully.

Directory structure:

~~~text
jms-error-layer-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── JmsErrorLayerDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jms-error-layer-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.2.19</spring-framework.version>
        <activemq.version>6.2.6</activemq.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-broker</artifactId>
            <version>${activemq.version}</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>${activemq.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/demo/JmsErrorLayerDemo.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.broker.BrokerService;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.SessionAwareMessageListener;
import org.springframework.jms.listener.SimpleMessageListenerContainer;

public class JmsErrorLayerDemo {

    public static void main(String[] args) throws Exception {
        BrokerService broker = new BrokerService();
        broker.setBrokerName("jms-error-layer-demo");
        broker.setPersistent(false);
        broker.setUseJmx(false);
        broker.start();
        broker.waitUntilStarted();

        ActiveMQConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory(
                        "vm://jms-error-layer-demo?create=false"
                );

        SimpleMessageListenerContainer container =
                new SimpleMessageListenerContainer();

        CountDownLatch errorHandled = new CountDownLatch(1);
        CountDownLatch messageProcessed = new CountDownLatch(1);
        AtomicBoolean failFirstAttempt = new AtomicBoolean(true);

        try {
            container.setConnectionFactory(connectionFactory);
            container.setDestinationName("orders.error.demo");
            container.setConcurrentConsumers(1);
            container.setSessionTransacted(true);

            container.setExceptionListener(exception ->
                    System.out.println(
                            "exceptionListener="
                                    + exception.getClass().getSimpleName()
                                    + ":" + exception.getMessage()
                    )
            );

            container.setErrorHandler(error -> {
                System.out.println(
                        "errorHandler="
                                + error.getClass().getSimpleName()
                                + ":" + error.getMessage()
                );
                errorHandled.countDown();
            });

            container.setMessageListener(
                    (SessionAwareMessageListener) (Message message, Session session) -> {
                        String orderId = ((TextMessage) message).getText();

                        if (failFirstAttempt.compareAndSet(true, false)) {
                            throw new JMSException(
                                    "simulated listener failure"
                            );
                        }

                        System.out.println("processed=" + orderId);
                        messageProcessed.countDown();
                    }
            );

            container.afterPropertiesSet();
            container.start();

            JmsTemplate sender = new JmsTemplate(connectionFactory);
            sender.convertAndSend("orders.error.demo", "ORD-1001");

            if (!errorHandled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "The error callbacks were not invoked"
                );
            }

            if (!messageProcessed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "The message was not processed after redelivery"
                );
            }
        }
        finally {
            container.stop();
            container.destroy();
            broker.stop();
            broker.waitUntilStopped();
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.JmsErrorLayerDemo
~~~

stdout output produced by the program:

~~~text
exceptionListener=JMSException:simulated listener failure
errorHandler=JMSException:simulated listener failure
processed=ORD-1001
~~~

Explanation:

1. `SimpleMessageListenerContainer` registers the listener on the queue and uses a local JMS transaction.
2. `SessionAwareMessageListener` throws a `JMSException` on the first delivery.
3. Spring invokes `ExceptionListener.onException()` first.
4. Spring invokes `ErrorHandler.handleError()` afterward with the same exception.
5. The JMS transaction rolls back; the broker redelivers the message.
6. On the next delivery, the listener processes successfully and prints `processed=ORD-1001`.

This example illustrates the branch where a `JMSException` arises inside the listener. It does not simulate a broker disconnect. If the provider detects a connection failure, the connection-level callback is invoked asynchronously and `SimpleMessageListenerContainer` performs recovery according to `recoverOnException`.

## 9. How to observe and handle errors in production

### Log with sufficient context

`ErrorHandler` only receives a `Throwable`, not the JMS Message directly. Therefore, log the correlation/event ID in the listener before the exception escapes:

~~~java
public void handle(Order order) {
    try {
        orderService.process(order);
    }
    catch (RuntimeException ex) {
        log.error(
                "Order processing failed: orderId={}, eventId={}",
                order.orderId(),
                order.eventId(),
                ex
        );
        throw ex;
    }
}
~~~

In ErrorHandler, log the stack trace and exception type. Avoid logging the entire payload if the message contains sensitive data.

### Classify errors

- Connection failure: update health/metrics, observe recovery, and check the broker/network.
- Transient business error: consider bounded retry, backoff, and idempotency.
- Permanent data error: move to a DLQ/quarantine according to policy; avoid infinite redelivery.
- Configuration or authentication error: alert operations, fix configuration/secrets, and check reconnect.
- Error from ErrorHandler or ExceptionListener: keep callbacks safe; a callback throwing another exception can complicate handling the original one.

### Do not reconnect arbitrarily

The provider may already be recovering on its own. By default, `SimpleMessageListenerContainer` attempts to refresh the shared connection and consumers when the provider reports an error. If you use a wrapper such as `SingleConnectionFactory`, check the `reconnectOnException` policy and listener aggregation before attaching another listener to the connection yourself.

### Metrics to monitor

- Number of connection exceptions.
- Number of listener processing errors by exception type.
- Number of redeliveries and messages sent to dead-letter.
- Queue depth and the age of the oldest message.
- Message processing time.
- Reconnect frequency and connection recovery time.

## 10. Common mistakes

1. **Using ExceptionListener to catch business validation errors.** Runtime exceptions from the listener belong to ErrorHandler.
2. **Assuming Connection.ExceptionListener receives every JMSException.** A JMSException thrown directly from an API call is returned to the caller; the provider listener only reports asynchronous connection failures per the contract.
3. **Assuming the Spring container ExceptionListener only receives connection errors.** Spring also invokes this callback for a JMSException from the listener/invocation infrastructure.
4. **Assuming ErrorHandler only receives JMSException.** It receives the Throwable from any uncaught processing exception.
5. **Assuming a JMSException only invokes one callback.** Spring invokes ExceptionListener first and then ErrorHandler.
6. **Assuming ErrorHandler retries the message by itself.** The callback does not control acknowledgement, rollback, or redelivery.
7. **Assuming returning from the callback means processing succeeded.** The transaction may have already rolled back before the callback was invoked.
8. **Using AUTO_ACKNOWLEDGE and expecting redelivery when the listener fails.** With DefaultMessageListenerContainer, acknowledgement by default happens before the listener; use sessionTransacted when you need guaranteed redelivery.
9. **Swallowing exceptions in the listener.** The container may treat the listener as having completed normally and commit/ack the message.
10. **Calling setExceptionListener yourself on a connection managed by the container.** This can overwrite the internal listener used for recovery. Configure it through the container or factory.
11. **Doing heavy work in onException.** The connection failure callback is asynchronous; keep processing short and avoid calling back into the failing connection.
12. **Ignoring idempotency.** Redelivery can cause the same message to be processed multiple times; protect business operations with an event ID or business key.
13. **Not configuring a redelivery limit/DLQ.** Infinite retry can keep the faulty message in the queue and reduce capacity for other messages.
14. **Assuming every container recovers the same way.** SimpleMessageListenerContainer and DefaultMessageListenerContainer have different receiving models and recovery behaviors.

## 11. Implementation checklist

- [ ] Determine whether the error belongs to connection/provider or listener/message processing.
- [ ] Use `jakarta.jms.ExceptionListener` for connection-level JMSException notifications.
- [ ] Configure `setExceptionListener` on the Spring listener container when you need to receive a JMSException from the listener/invocation infrastructure.
- [ ] Configure `org.springframework.util.ErrorHandler` for all uncaught processing exceptions.
- [ ] Remember that JMSException goes through ExceptionListener first and then ErrorHandler.
- [ ] Keep callbacks concise, non-blocking, and free of new exceptions.
- [ ] Do not replace the internal listener on a container-managed connection.
- [ ] Choose `sessionTransacted=true` if you need consistent rollback/redelivery.
- [ ] Configure broker redelivery, backoff, retry limits, and a DLQ.
- [ ] Design the listener to be idempotent and record processed event markers.
- [ ] Monitor connection health, listener errors, queue depth, and redeliveries.
- [ ] Test connection failure, RuntimeException, JMSException, rollback, and redelivery separately.

## 12. Conclusion

`ExceptionListener` and `ErrorHandler` observe two different kinds of incidents. Jakarta `Connection.ExceptionListener` receives asynchronous notifications when the JMS provider detects a serious issue on the connection. The Spring listener container uses `setExceptionListener` to report a `JMSException` arising from the listener or invocation infrastructure; for this error, Spring invokes ExceptionListener first and then ErrorHandler. `ErrorHandler` receives all uncaught exceptions during message processing. Both callbacks are only points for observing/handling errors; rollback, acknowledgement, redelivery, and recovery still depend on the container, transactions, and broker policy.

## Official references

- [Jakarta Messaging 3.1 Specification, §6.1.7 ExceptionListener](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.pdf) — connection-level callback, asynchronicity, provider recovery, and the limitation of not receiving exceptions already thrown from an API call.
- [Spring Framework 6.2.19 Javadoc: AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html) — setExceptionListener, setErrorHandler, callback order, and acknowledgement behavior.
- [Spring Framework 6.2.19 Javadoc: ErrorHandler](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/util/ErrorHandler.html) — functional interface `handleError(Throwable)`.
- [Spring Framework 6.2.19 Javadoc: SimpleMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html) — registering the container as a Connection ExceptionListener and recovery.
- [Spring Framework 6.2 Reference: Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html) — choosing SimpleMessageListenerContainer and DefaultMessageListenerContainer.
- [Spring Framework 6.2 Reference: Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html) — MessageListener, SessionAwareMessageListener, and listener containers.
- [Spring Framework 6.2.19 Javadoc: AbstractJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/config/AbstractJmsListenerContainerFactory.html) — configuring ErrorHandler and ExceptionListener for @JmsListener endpoints.
