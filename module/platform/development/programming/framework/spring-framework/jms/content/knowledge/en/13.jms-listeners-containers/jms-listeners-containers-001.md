# Asynchronous Receiving with MessageListener in Spring Framework JMS

## 1. Lesson Objectives

In JMS, there are two basic ways for a consumer to retrieve messages: **synchronous receiving** using `MessageConsumer.receive(...)` (the calling thread waits for a message) and **asynchronous receiving** by registering a `MessageListener`. With the second approach, the client registers a handler method in advance; when the broker has a matching message, the JMS provider or Spring listener container proactively **invokes `onMessage(Message)`** on the receiving thread, instead of business code having to loop on `receive` itself.

This topic belongs to **Listeners and containers** in Spring Framework JMS. We will connect concepts from the Jakarta Messaging specification to how Spring organizes consumers, lifecycles, and error handling.

After this lesson, you will be able to:

1. Write a class or lambda implementing `jakarta.jms.MessageListener` and register it via `MessageConsumer.setMessageListener(...)`.
2. Understand the roles of `Connection.start()`, `Session`, the callback thread, resource lifecycle, and why `receive()` and a listener must not be mixed on the same session.
3. Configure a **Spring `DefaultMessageListenerContainer`** to receive messages using a plain `MessageListener`, without code that manually opens/closes sessions.
4. Distinguish between `SimpleMessageListenerContainer`, `DefaultMessageListenerContainer`, `@JmsListener`, `SessionAwareMessageListener`, `CompletionListener`, and `ExceptionListener`.
5. Design acknowledgement, local transactions, rollback, retry/DLQ, concurrency, and idempotency properly for production.
6. Run a Java 17+ / Spring Boot 3.5.x / Apache ActiveMQ Artemis example and understand the output, environment requirements, and failure scenarios.

**Scope:** this lesson covers **asynchronous receiving**, not asynchronous send. Wherever JMS uses `jakarta.jms.*`, it refers to Jakarta Messaging 3.x / Spring Framework 6.x; legacy JMS libraries using `javax.jms.*` are not automatically compatible with the new namespace.

## 2. What is MessageListener?

`jakarta.jms.MessageListener` is a functional interface in Jakarta Messaging:

```java
package jakarta.jms;

@FunctionalInterface
public interface MessageListener {
    void onMessage(Message message);
}
```

This is a **simplified signature for explanation**, not an interface you need to create yourself in your project. The `onMessage` method:

- Is invoked by the JMS provider when a `Message` is dispatched to a consumer with a registered listener.
- Returns `void`; the application processes the body, headers, properties, and business tasks inside the callback.
- Does not declare `throws JMSException`, so errors when reading `TextMessage.getText()` must be caught and translated into an unchecked exception or handled according to policy.
- Executes under the provider/container dispatch mechanism, **not on the thread that calls `setMessageListener`**.
- May receive `TextMessage`, `BytesMessage`, `MapMessage`, `ObjectMessage`, or other message types. Do not cast every message to `TextMessage` without checking.

Minimal callback example:

```java
MessageListener listener = message -> {
    if (!(message instanceof TextMessage text)) {
        throw new IllegalArgumentException("Expected TextMessage");
    }
    try {
        System.out.println("body=" + text.getText());
    } catch (JMSException e) {
        throw new IllegalStateException("Cannot read JMS text", e);
    }
};
```

This is a **snippet**; it requires importing `jakarta.jms.MessageListener`, `TextMessage`, and `JMSException`. It only creates a Java object and **has not yet registered it with a JMS consumer**; no messages will arrive until you configure a consumer and start delivery.

### 2.1. Asynchronous receiving timeline

```text
Application                      JMS client / broker
   |
   | createConnection()
   | createSession()
   | createConsumer(queue)
   | consumer.setMessageListener(listener)
   | connection.start()
   |----------------------------------------> start receiving messages
   |
   | do other work / wait for signal
   |                                      broker has a message
   |                                           |
   |                              provider selects matching consumer
   |                                           |
   |                           invoke listener.onMessage(message)
   |                                           |
   |                           run processing + ack/tx per configuration
   |
   | on shutdown: stop/close resources on coordinator thread
```

**Asynchronous does not mean unbounded parallel processing.** Jakarta Messaging guarantees that callbacks belonging to **a single Session are invoked sequentially**. To process multiple messages concurrently, you need multiple sessions/consumers as appropriate or a container scale-out model.

### 2.2. How does MessageListener differ from other listener types?

| Mechanism | Communication side | Callback / API | Responsibility |
| --- | --- | --- | --- |
| `MessageListener` | **Receiving** JMS messages | `onMessage(Message)` | Process incoming messages. |
| `CompletionListener` | **Sending** JMS asynchronously | `onCompletion` / `onException` | Report status of a send operation. |
| `ExceptionListener` | JMS **connection** | `onException(JMSException)` | Notify about connection errors that have no normal call path to report through. |
| Spring `@JmsListener` | **Receiving** JMS, at POJO method level | Annotated method | Container creates listener adapter/converter for you. |
| Spring `SessionAwareMessageListener` | **Receiving** JMS with `Session` access | `onMessage(Message, Session)` | Process and optionally send a reply on the container-provided session. |

Do not use `CompletionListener` to wait for messages from a Queue: the name is similar, but it is a **producer-side** callback. Do not mistake `ExceptionListener` for a place to catch every exception thrown by `onMessage` logic.

## 3. Asynchronous Receiving with the Native Jakarta Messaging API

### 3.1. Five basic steps

With Classic Jakarta Messaging:

1. Obtain a `ConnectionFactory` suitable for the broker.
2. Create a `Connection` and a `Session`.
3. Create a `MessageConsumer` bound to a Queue/Topic.
4. Call `consumer.setMessageListener(listener)`.
5. Call `connection.start()` to allow delivery to begin.

The order of **registering the listener first and then starting the connection** avoids messages arriving before the application finishes setting up the callback.

```java
try (Connection connection = connectionFactory.createConnection();
     Session session =
             connection.createSession(Session.AUTO_ACKNOWLEDGE);
     MessageConsumer consumer =
             session.createConsumer(session.createQueue("orders.queue"))) {

    consumer.setMessageListener(message -> {
        System.out.println("received type=" + message.getClass().getName());
    });

    connection.start();

    // Keep the application/lifecycle alive so the provider can still invoke onMessage.
}
```

This is a snippet inside a method that has a `connectionFactory` variable; it illustrates the order but **does not keep the application alive long enough** if the code immediately exits the `try` block. Exiting the block closes the consumer/session/connection, and it will no longer continue receiving messages. A complete pattern with `CountDownLatch` is shown below.

### 3.2. Complete Java 17+ example of native JMS logic

This class has a method that receives **one message** asynchronously while sending a test message on a **different session**, waits for the listener to respond, and finally closes resources.

```java
package example.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class RawMessageListenerExample {

    private RawMessageListenerExample() {
    }

    public static boolean runOnce(ConnectionFactory factory)
            throws JMSException, InterruptedException {

        CountDownLatch observed = new CountDownLatch(1);

        try (Connection connection = factory.createConnection();
             Session receiveSession =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             Session sendSession =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             MessageConsumer consumer = receiveSession.createConsumer(
                     receiveSession.createQueue("learning.listener.queue"));
             MessageProducer producer = sendSession.createProducer(
                     sendSession.createQueue("learning.listener.queue"))) {

            consumer.setMessageListener(message -> {
                if (!(message instanceof TextMessage text)) {
                    throw new IllegalArgumentException(
                            "Expected TextMessage");
                }

                try {
                    System.out.println("rawReceived=" + text.getText());
                    observed.countDown();
                } catch (JMSException error) {
                    throw new IllegalStateException(
                            "Cannot read TextMessage", error);
                }
            });

            // Listener is registered; now open delivery.
            connection.start();

            // Send from a separate Session; do not use receiveSession from this thread.
            producer.send(
                    sendSession.createTextMessage("hello-raw-listener"));

            // Demo has a deadline. In a real service, the container manages the lifecycle.
            return observed.await(10, TimeUnit.SECONDS);
        }
    }
}
```

This is **a Java 17+ class that compiles when the Jakarta Messaging API/provider is present**, but **not a standalone `main`**: you need to pass a `ConnectionFactory` created by Artemis or the application when calling `RawMessageListenerExample.runOnce(...)`. The example in section 5 provides a complete Spring Boot application using existing infrastructure for actual execution.

Notable technical points:

- `receiveSession` is used by the provider to invoke the listener. A **different** `sendSession` is used from the application thread to send the message; no two threads operate on the same `Session`.
- `CountDownLatch` only keeps the demo method alive until the callback observes one message. `observed.await(...)` is a wait operation on the **demo** thread, not `MessageConsumer.receive(...)`.
- `observed.countDown()` inside the listener proves the callback executed up to that line; it **does not by itself prove that all downstream transactions/acknowledgements have completed**.
- `try-with-resources` keeps the connection, sessions, consumer, and producer alive within scope, then closes them in reverse order when the method finishes. Do not close them from business logic on every received message.
- If the Queue has old messages or other consumers, the output may differ. Use a dedicated Queue for integration tests and isolate publishers/consumers.
- If the callback processes a message of the wrong type and throws an error before `countDown`, the demo may time out; redelivery behavior depends on the ack mode/provider.

### 3.3. Why not use receive() concurrently on the same Session?

A `Session` is a **single-threaded context for processing one logical stream at a time**. Once an asynchronous listener is set and the connection is started, the provider owns the delivery thread of that session. Calling `consumer.receive()` from an application thread on the same `Session` at the same time violates the JMS model. Jakarta Messaging specifies not sharing a single session for both asynchronous delivery and synchronous receive.

**Correct:** thread A configures a listener on session A; thread B uses session B for separate send or receive operations. **Wrong:** setting a listener on session A while another thread continues calling `receive()`/`commit()` on session A while the callback is running.

If you need to pause all delivery, JMS provides `Connection.stop()` at the connection layer; use it on a **lifecycle coordinator thread** instead of calling it arbitrarily inside a callback. When multiple consumers/sessions share a connection, calling stop affects more than one listener.

### 3.4. JMSContext/JMSConsumer

The Simplified API also allows:

```java
try (JMSContext context =
             connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

    JMSConsumer consumer = context.createConsumer(
            context.createQueue("orders.queue"));

    consumer.setMessageListener(message -> {
        System.out.println("async message received");
    });

    // Must keep the context alive so the callback continues receiving messages.
}
```

This is a snippet inside a method that has `connectionFactory`; because the scope ends immediately, it is **not a complete server listener**. `JMSContext` normally auto-starts the connection when creating a consumer because `autoStart=true`, unlike the Classic API where you must call `connection.start()`. If you need to configure the listener and resources before delivery starts, you can call `context.setAutoStart(false)` before `createConsumer` and then `context.start()` after the listener is set up.

`JMSContext` is still subject to the threading rules of the underlying session and is not a thread-safe singleton to be shared arbitrarily across workers.

## 4. Resource Lifecycle and Threading in Callbacks

### 4.1. One Session, one sequential callback stream

The specification states that when multiple `MessageListener` instances are registered on consumers belonging to the **same Session**, `onMessage` invocations for that session are serialized: no second callback runs on that session until the previous callback has finished. That simplifies programming, but also has consequences:

- A long-running callback blocks subsequent delivery on the same session.
- Increasing the number of listener objects on the **same session** does not automatically increase throughput.
- To achieve true concurrent processing, use **multiple sessions**; in a Spring container, adjust the number of concurrent consumers and application instances.
- A single listener bean can be called concurrently by different sessions if the Spring container has concurrency greater than 1. **Thread-safe state in the bean is mandatory.**

Incorrect example when a singleton bean is shared by multiple consumers:

```java
public final class UnsafeCounterListener implements MessageListener {
    private int handled;

    @Override
    public void onMessage(Message message) {
        handled++; // Race if multiple Sessions invoke the same instance.
    }
}
```

Replace with `LongAdder`, `AtomicLong`, immutable state, or move state into a database with an appropriate concurrency mechanism. Note that an in-memory counter is not a durable transaction log.

### 4.2. Do not abuse the callback thread

An ideal callback:
- Validates the message type and required metadata.
- Performs time-bounded business logic.
- Lets exceptions propagate **if the container is managing a transaction and you want a rollback**.
- Logs with a correlation ID, updates metrics, and returns.

You should not block the callback for minutes on an HTTP endpoint without a timeout, nor spawn thousands of arbitrary threads from each `onMessage`. If you merely offload work to an executor and return from `onMessage` immediately, the container may **ack/commit the message before the work in the executor succeeds**. That loses processing guarantees if the executor/task or JVM dies. For durable background processing, design a proper job queue, outbox/inbox, or dedicated transaction.

### 4.3. Graceful shutdown

In native JMS, the owner must stop/close the connection, sessions, and consumers when the application shuts down. `close` may wait for an actively executing listener to finish; avoid arbitrarily closing your own session from inside a callback because it is not portable.

In Spring, let `DefaultMessageListenerContainer` be a Spring-managed bean. It has start/stop lifecycle management and resource recovery. When the application shuts down, Spring stops receiving and cleans up resources; you do not call `connectionFactory.close()` inside each `onMessage`.

Before deploying, verify maximum processing time, in-flight message draining, restart/rolling deployments, prefetch settings, and whether shutting down too early could cause the broker to redeliver.

## 5. Practical Spring Boot Example: MessageListener + DefaultMessageListenerContainer

In a Spring application, manually creating connections/sessions in every service is rarely optimal. Instead, declare **a `MessageListener` bean** and a **`DefaultMessageListenerContainer`**, letting Spring proactively own the consumer lifecycle.

The example below uses:

- Java 17+.
- Spring Boot **3.5.8** (Spring Framework 6.x).
- An **externally running** Apache ActiveMQ Artemis broker.
- `spring-boot-starter-artemis`.
- `DefaultMessageListenerContainer` performing asynchronous receiving from the perspective of business code, invoking `MessageListener.onMessage`.
- A JMS **local transaction** per message, configured via `sessionTransacted=true`.
- An `ApplicationRunner` that sends a test message and waits for the callback signal using `CountDownLatch`.

**Good to know upfront:** Spring's `DefaultMessageListenerContainer` differs from `SimpleMessageListenerContainer` in how it receives underneath. DMLC normally uses worker threads calling `receive` and then dispatches to the listener, rather than necessarily registering a provider callback via `MessageConsumer.setMessageListener`. From the business code's point of view, both are still **asynchronous receiving via MessageListener**; this point is explained in depth in section 7.

### 5.1. Project structure

```text
async-message-listener/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── jms/
        │           └── AsyncMessageListenerApplication.java
        └── resources/
            └── application.properties
```

### 5.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>async-message-listener</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
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
```

`spring-boot-starter-artemis` provides the matching Jakarta Messaging client and Spring JMS via Boot's dependency management. Do not add legacy `javax.jms-api` to avoid namespace conflicts.

### 5.3. application.properties

```properties
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}

# The container manages connection/session/consumer itself in this example.
spring.jms.cache.enabled=false

# The sender uses a Queue, not a Topic.
spring.jms.pub-sub-domain=false
```

Explanation:
- `spring.artemis.mode=native` uses an **external Artemis broker**. It does not start a broker automatically.
- Username/password are read from environment variables, **not hardcoded** production credentials; both variables must have real values at runtime.
- `spring.jms.cache.enabled=false` avoids wrapping the listener container with an outer `CachingConnectionFactory` in the demo, since DMLC has its own caching/recovery. In complex systems, separate factories/pools for publishers and listeners can be used after measuring in practice.
- The Queue will be `learning.listener.queue`. The broker must pre-provision the Queue **or** support auto-creating Queues per its security/routing policy.
- The demo producer uses `JmsTemplate`; the consumer uses a **plain JMS `MessageListener`** invoked by the container.

### 5.4. Complete Java file

**`src/main/java/example/jms/AsyncMessageListenerApplication.java`**

```java
package example.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@SpringBootApplication
public class AsyncMessageListenerApplication {

    private static final String QUEUE = "learning.listener.queue";

    public static void main(String[] args) {
        SpringApplication.run(AsyncMessageListenerApplication.class, args);
    }

    @Bean
    DemoOrderListener orderMessageListener() {
        return new DemoOrderListener();
    }

    @Bean
    DefaultMessageListenerContainer ordersContainer(
            ConnectionFactory connectionFactory,
            DemoOrderListener orderMessageListener) {

        var container = new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName(QUEUE);
        container.setMessageListener(orderMessageListener);
        container.setSessionTransacted(true);
        container.setConcurrency("1-2");
        container.setRecoveryInterval(5_000L);
        return container;
    }

    @Bean
    ApplicationRunner publishSample(
            JmsTemplate jmsTemplate,
            DemoOrderListener listener) {

        return args -> {
            jmsTemplate.convertAndSend(QUEUE, "event:demo-001");

            boolean invoked = listener.await(10, TimeUnit.SECONDS);
            System.out.println("listenerInvoked=" + invoked);

            if (!invoked) {
                throw new IllegalStateException(
                        "Listener did not receive a message in 10 seconds");
            }
        };
    }

    public static final class DemoOrderListener implements MessageListener {
        private final CountDownLatch observed = new CountDownLatch(1);

        @Override
        public void onMessage(Message message) {
            if (!(message instanceof TextMessage textMessage)) {
                throw new IllegalArgumentException(
                        "Expected TextMessage");
            }

            try {
                String body = textMessage.getText();
                if (!"event:demo-001".equals(body)) {
                    throw new IllegalArgumentException(
                            "Unexpected payload: " + body);
                }

                System.out.println("listenerBody=" + body);
                observed.countDown();
            } catch (JMSException error) {
                throw new IllegalStateException(
                        "Cannot read JMS text", error);
            }
        }

        public boolean await(long timeout, TimeUnit unit)
                throws InterruptedException {
            return observed.await(timeout, unit);
        }
    }
}
```

**This is a complete Java program**, with one public class and one nested class, using Spring Boot and an available Artemis broker. There is no need to add `@EnableJms` because we **create the `DefaultMessageListenerContainer` bean directly**, rather than registering `@JmsListener` annotation endpoints.

**What happens step by step:**

1. Boot builds `ConnectionFactory` and `JmsTemplate` from the starter/properties.
2. Spring creates `DemoOrderListener` and configures `DefaultMessageListenerContainer` to receive on Queue `learning.listener.queue`.
3. The container is lifecycle-managed by Spring, automatically opens sessions/consumers when starting to receive messages, and recovers automatically when the broker is temporarily unavailable.
4. `ApplicationRunner` uses `JmsTemplate.convertAndSend(...)` to send a `TextMessage`.
5. The container retrieves the message and invokes `DemoOrderListener.onMessage(message)` on a container worker thread.
6. The callback checks the type, reads the body, prints to stdout, and signals `CountDownLatch`.
7. `ApplicationRunner` observes the latch and prints the status. When the callback returns normally, the local JMS transaction is committed by the container; when the callback throws an error, the container rolls back.
8. When the Spring context closes, the container stops receiving and cleans up its resources.

**Meaning of the latch:** `observed.countDown()` happens **inside the callback**, before the framework finishes handling the transaction. Therefore `listenerInvoked=true` only proves the callback reached the point of signaling logical success; it **is not confirmation that the JMS commit completed**. To test commit/redelivery, you need an integration test and observation of broker state.

### 5.5. Running and observing

Assume an Artemis broker is running on `tcp://localhost:61616`, the account has send/consume permissions, and the dedicated demo Queue has no old messages. In PowerShell:

```powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "dev-user"
$env:JMS_PASSWORD = "dev-password"
mvn spring-boot:run
```

With a POSIX shell:

```bash
JMS_BROKER_URL=tcp://localhost:61616 \
JMS_USERNAME=dev-user \
JMS_PASSWORD=dev-password \
mvn spring-boot:run
```

Replace `dev-user`/`dev-password` with actual broker credentials. Note that the Spring Boot application keeps running by default after `ApplicationRunner` because of the listener container; stop it with Ctrl+C to verify graceful shutdown.

**Two lines explicitly printed by the code when the demo conditions succeed:**

```text
listenerBody=event:demo-001
listenerInvoked=true
```

Spring/Artemis logs also appear. The order of the two lines printed by the code in this example is synchronized by `CountDownLatch` (the listener prints the body before calling countDown), but **framework logs can still interleave**. If the Queue contains other messages, the listener may throw an error and trigger redelivery; if other consumers are running, the message may go to another consumer and the demo may time out. Do not treat stdout in a non-isolated environment as invariant.

Build to verify compilation without running a broker:

```bash
mvn -q -DskipTests package
```

Compiling does not prove broker connectivity, Queue permissions, or transaction behavior. To verify end-to-end, you need to run against a real broker or an integration test environment with a compatible Artemis instance.

## 6. Why Use a Listener Container in Spring?

If every Spring service had to manually call `ConnectionFactory.createConnection()`, `Session.createConsumer()`, and `setMessageListener(...)` at startup, the application would have to solve on its own:

- Connection/session lifecycle, shutdown, and cleanup.
- Retry/reconnect when the broker loses connectivity.
- Threading model, concurrency, health/recovery.
- Transactions and acknowledgements.
- Queue/Topic configuration, message selectors, durable subscriptions.
- Logging, monitoring, and resource limits.

A **message listener container** solves most of this infrastructure. You pass in a `ConnectionFactory`, destination name, and listener; Spring actively manages consumers/threads/transactions and invokes the callback when a message arrives.

There are two important containers:

| Criterion | `SimpleMessageListenerContainer` | `DefaultMessageListenerContainer` |
| --- | --- | --- |
| Underlying receive mechanism | Registers `MessageConsumer.setMessageListener(...)`; provider dispatches callbacks. | Usually uses worker tasks calling `receive`/polling and then invokes the listener. |
| Consumer management | Fixed number of sessions/consumers from startup. | Supports core/max concurrency levels and scales with load. |
| Recovery when broker is down | Fewer recovery features, not as flexible as DMLC. | Has recovery/retry mechanisms on connection errors with configurable backoff. |
| External/JTA transaction | Does not support participating in externally managed transactions the way DMLC does. | Can participate in an external transaction manager, including JTA when configured. |
| Local JMS transaction | Yes, via `setSessionTransacted(true)`. | Yes, via `setSessionTransacted(true)`. |
| Best suited for | Simple applications wanting behavior close to native JMS callbacks. | Most production Spring applications needing manageability and reliability. |

**Common misconception:** `DefaultMessageListenerContainer` has "listener" in its name and calls `MessageListener.onMessage`, yet it **does not require the provider to have `setMessageListener` called**. Spring polls on task threads itself. Therefore, do not blindly project exact callback/ack semantics of a raw JMS provider onto every Spring container. Check the specification and Javadoc for the specific container class.

### 6.1. When to configure SimpleMessageListenerContainer?

This is an **alternative** to DMLC in the main example; do not register both containers on the same Queue in the same demo:

```java
@Bean
SimpleMessageListenerContainer simpleListenerContainer(
        ConnectionFactory factory,
        MessageListener listener) {

    var container = new SimpleMessageListenerContainer();
    container.setConnectionFactory(factory);
    container.setDestinationName("orders.queue");
    container.setMessageListener(listener);
    container.setConcurrentConsumers(2);
    container.setSessionTransacted(true);
    return container;
}
```

This snippet belongs to a `@Configuration` class and requires importing `@Bean`, `ConnectionFactory`, `MessageListener`, and `org.springframework.jms.listener.SimpleMessageListenerContainer`. It uses provider callbacks via `MessageConsumer.setMessageListener`. With concurrency 2, the container holds multiple sessions; the shared listener bean must be thread-safe. This is not the default choice for every deployment, especially when JTA or dynamic recovery is needed.

**Do not install both** the `SimpleMessageListenerContainer` example and `DefaultMessageListenerContainer` on the Queue at the same time if you want every message to always be received by the main demo listener, because the two containers become competing consumers.

## 7. Transactions and Acknowledgements: Can a Received Message Be Lost or Redelivered?

This is the most critical part for reliability. **The callback being invoked does not mean the message was definitely processed and committed.** Behavior depends on the JMS session/ack mode **and** the listener container.

### 7.1. Classic JMS native MessageListener

In the native Jakarta Messaging API:

- `AUTO_ACKNOWLEDGE`: the provider automatically acknowledges after `onMessage` returns normally. If the callback throws a `RuntimeException`, the specification has redelivery rules depending on the ack mode, while also treating a listener throwing an unchecked exception as a programming error that applications should avoid.
- `DUPS_OK_ACKNOWLEDGE`: the provider may delay acknowledgement, so the application must tolerate possible redelivery.
- `CLIENT_ACKNOWLEDGE`: the application must call `message.acknowledge()` appropriately; calling acknowledge typically acknowledges **all messages delivered on the same Session**, not just a single message.
- `SESSION_TRANSACTED`: receipt is confirmed by commit and recovered by rollback.

**Easily overlooked fact:** With a **raw provider `MessageListener` on a transacted session**, throwing a `RuntimeException` from `onMessage` **does not automatically force the provider to roll back the transaction**. The specification states that the session still needs to be properly committed or rolled back. Do not copy the expectation that "throwing an exception auto-rolls back" from a Spring container to raw JMS code without configuring ownership.

### 7.2. How Spring listener containers change error coordination

In `DefaultMessageListenerContainer` with `setSessionTransacted(true)`, Spring manages a local JMS transaction for each delivery. If the listener completes normally, the container commits; if the listener throws an exception that propagates out to the container, Spring rolls back and the broker can redeliver according to policy.

**Warning with default AUTO_ACKNOWLEDGE:** Spring documentation notes that `DefaultMessageListenerContainer` typically **acknowledges before running the listener** in this mode, so if business code throws an exception, there is no reliable redelivery via exceptions alone. `SimpleMessageListenerContainer` has different timing due to provider callbacks, yet you still should not rely on AUTO_ACK when reliable delivery/recovery is required. For Queues carrying important work, consider **`sessionTransacted=true`**.

### 7.3. What happens if the listener throws an exception?

Suppose you have:

```java
@Override
public void onMessage(Message message) {
    throw new IllegalStateException("Processing failed");
}
```

This snippet simulates a business failure inside the listener. With a **transacted Spring container**, the framework sees the exception, rolls back receipt, and the broker can redeliver the message. Retry count, delay interval, dead-letter address, and redelivery order depend on the broker (e.g., Artemis) and policy configuration.

Do not do this:

```java
@Override
public void onMessage(Message message) {
    try {
        doBusinessWork(message);
    } catch (Exception ex) {
        log.error("Processing failed", ex);
        // returning normally = the container may COMMIT.
    }
}
```

This is an **illustrative anti-pattern**, not standalone runnable code because `doBusinessWork`/`log` are undefined. In a transacted listener, if you **swallow the exception and return normally**, the container can commit and the message will not be redelivered even though business work failed.

When the business logic decides an error is "non-retryable", explicitly design a DLQ/parking queue or durable error record instead of merely logging and returning.

### 7.4. A JMS local transaction does not span the database

If `onMessage` writes SQL and then returns, the following can happen:

```text
SQL commit succeeds
    |
JMS commit fails / JVM crashes before commit
    |
Broker redelivers the same message
    |
Business action is executed a second time if not idempotent
```

`setSessionTransacted(true)` applies only to the local JMS transaction. It does **not** automatically bring JDBC/HTTP/partner APIs into the same transaction. Practical solutions are usually an idempotent consumer + inbox/dedup table keyed by `eventId`, or outbox/JTA/XA when truly required and supported by infrastructure.

### 7.5. Inspecting redelivery information

When a message is redelivered, JMS provides:

- `message.getJMSRedelivered()`: header indicating whether the message is marked as redelivered.
- `message.getIntProperty("JMSXDeliveryCount")`: the number of times the provider has delivered the message per specification, if the property is present on a supporting provider.

Example:

```java
try {
    String messageId = message.getJMSMessageID();
    boolean redelivered = message.getJMSRedelivered();
    int attempts = message.propertyExists("JMSXDeliveryCount")
            ? message.getIntProperty("JMSXDeliveryCount")
            : -1;
    System.out.printf(
            "id=%s redelivered=%s deliveries=%d%n",
            messageId, redelivered, attempts);
} catch (JMSException e) {
    throw new IllegalStateException("Cannot read headers", e);
}
```

The snippet above uses `message` from the callback and requires `JMSException`; it is a snippet, not a standalone app. This information helps with debugging, but should **not** be used as the sole basis for idempotency: a single event could be re-sent by a publisher with a different JMSMessageID. Create a durable business event ID.

## 8. Concurrency and Message Processing Ordering

### 8.1. Each session serializes callbacks; multiple sessions can run in parallel

With Spring DMLC:

```java
container.setConcurrency("1-4");
```

This means the container normally keeps a minimum of one consumer/worker and can scale up to four under load, depending on configuration and implementation. It does not mean callbacks always process four messages simultaneously in every situation.

Points to remember:
- A Queue has **competing consumers**: one message is normally delivered to one consumer at a time.
- Multiple consumers on a Queue can process in parallel, so **the completion order of business work differs from the order messages were sent**.
- With a Topic, multiple subscribers can each receive a copy; do not mechanically apply the "increase concurrent consumers like a Queue" idea to a Topic.
- A listener bean can be shared across multiple worker threads: unsynchronized mutable fields easily cause races.
- If the business requires ordering by `orderId`, consider provider-supported message grouping/partitioning or appropriate concurrency.

### 8.2. Thread-safe counter example

```java
import java.util.concurrent.atomic.LongAdder;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;

public final class CountingListener implements MessageListener {

    private final LongAdder processed = new LongAdder();

    @Override
    public void onMessage(Message message) {
        // Execute business logic here.
        processed.increment();
    }

    public long processedCount() {
        return processed.sum();
    }
}
```

This is Java 17+ code demonstrating a thread-safe in-memory counter. **The counter is not atomic with the JMS transaction**; if `onMessage` increments it and then the container rolls back, the counter still increases. For business audit/deduplication, store state durably with a consistent mechanism.

### 8.3. Avoid holding a global lock in the listener

If all four concurrent consumers call `synchronized` on a singleton listener for the entire long-running operation, you accidentally serialize them at the application layer, losing the benefit of concurrency. Use per-business-key locking or fine-grained thread-safe handling, and measure latency under load.

## 9. Queue, Topic, Selectors, and Choosing Destinations

`MessageListener` only defines **how to process a message once delivered**; the destination and subscription are determined by the `MessageConsumer` or Spring container.

| Scenario | How to configure | Notes |
| --- | --- | --- |
| Receive Queue | `session.createQueue("orders.queue")` / `setDestinationName("orders.queue")` with Queue domain | Has competing consumers; more consumers increase throughput but lose global processing order. |
| Receive Topic | `session.createTopic("events.topic")` / `setPubSubDomain(true)` on container | Each subscription has its own semantics; durable/shared requires appropriate extra configuration. |
| Filter messages | JMS selector e.g. `eventType = 'ORDER_CREATED'` | Selectors filter on JMS headers/properties, not by parsing a JSON body. |
| Durable Topic | Durable subscription with client ID / subscription name per provider | Requires managing subscription lifecycle and client ID uniqueness. |
| Request/reply | Use `JMSReplyTo`/`JMSCorrelationID` | Destination names and correlation must be consistent; do not turn callbacks into an ad-hoc reply protocol. |

**Selector example** as a snippet added to the DMLC bean **before startup**:

```java
container.setMessageSelector("eventType = 'ORDER_CREATED'");
```

The sender must set the matching property, for example:

```java
jmsTemplate.send("orders.queue", session -> {
    var msg = session.createTextMessage("order-1");
    msg.setStringProperty("eventType", "ORDER_CREATED");
    return msg;
});
```

This is a snippet inside a Spring component that has `jmsTemplate`; it is not a standalone class. If the selector does not match, the listener is not invoked even if the Queue has messages of other types. That is not a `MessageListener` bug.

## 10. MessageListener, SessionAwareMessageListener, and @JmsListener

### 10.1. Plain MessageListener

`MessageListener` uses the standard JMS contract:

```java
public void onMessage(Message message)
```

There is no `Session` parameter. Suitable when you need portable code across Spring and JMS providers or want direct access to headers/body inside receiving logic.

### 10.2. Spring SessionAwareMessageListener

Spring provides the extension `org.springframework.jms.listener.SessionAwareMessageListener<Message>`:

```java
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.springframework.jms.listener.SessionAwareMessageListener;

public final class ReplyingListener
        implements SessionAwareMessageListener<Message> {

    @Override
    public void onMessage(Message request, Session session)
            throws JMSException {

        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            return;
        }

        try (MessageProducer producer = session.createProducer(replyTo)) {
            TextMessage reply =
                    session.createTextMessage("processed");
            reply.setJMSCorrelationID(request.getJMSCorrelationID());
            producer.send(reply);
        }
    }
}
```

The Java class above requires Spring JMS and the Jakarta API; when deployed, it must be registered with a suitable Spring listener container. With a local transacted container, the reply is sent using the **same JMS Session** within the receiving transaction, so it can commit/roll back together with the received message. However, SQL or HTTP APIs called inside the callback **do not automatically become atomic**.

`SessionAwareMessageListener` is a **Spring** interface, not `jakarta.jms.MessageListener`. When you want maximum portability or use a listener container that does not support the extension, choose standard `MessageListener`.

### 10.3. @JmsListener: writing POJOs without implementing MessageListener

The familiar approach in Spring Boot:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListenerService {

    @JmsListener(destination = "orders.queue")
    public void handleOrder(String body) {
        System.out.println("order=" + body);
    }
}
```

The annotation infrastructure creates a container and uses an adapter/converter to invoke the `handleOrder` method. This method **does not implement `MessageListener`**, yet still receives asynchronously from the application's perspective.

If declaring the factory manually:

```java
@Bean(name = "jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1-3");
    return factory;
}
```

This snippet belongs to a configuration class importing `@Bean`, `DefaultJmsListenerContainerFactory`, and `ConnectionFactory`. With plain Spring Framework, `@EnableJms` must be enabled. Spring Boot normally auto-enables the annotated JMS listener infrastructure when the corresponding starter is on the classpath.

**Do not register both `@JmsListener` and the manual container from section 5's example on the same destination** if the demo goal is exclusive reception by one consumer; that would create two consumers competing for messages.

### 10.4. When to use MessageListenerAdapter?

`org.springframework.jms.listener.adapter.MessageListenerAdapter` is suitable when you want a POJO to receive messages via another method, such as `handleMessage(String body)`, without using annotations. The adapter converts the payload and invokes the configured method. It sits midway between raw `MessageListener` and `@JmsListener`.

In modern Spring applications, `@JmsListener` is usually more concise, while plain `MessageListener` is useful when you need control over JMS fields and want to reuse the contract directly.

## 11. Errors and Redelivery: Designing Safe Callbacks

A production listener should never assume incoming data is always valid. Separate three error categories:

1. **Unprocessable payload errors**: invalid schema, missing required fields, unsupported message type. Can be handled via a DLQ/parking queue after a defined number of attempts; infinite retries rarely help.
2. **Transient errors**: database/HTTP unavailable, lock timeout, temporary broker disconnect. Requires bounded retry/backoff and a redelivery policy.
3. **Programming errors**: `NullPointerException`, race conditions, improper session/lifecycle usage. Log thoroughly, fix the code, and avoid "swallowing" exceptions and committing the message.

### 11.1. Do not treat onMessage as an automatic transaction

The JMS provider delivers messages via callbacks, but reliability is not determined solely by the word "async". You must know which `sessionTransacted` setting, acknowledge mode, and broker policy the container uses.

A listener can be invoked multiple times for the **same business event** due to redelivery or publisher retry. Therefore you need an idempotent handler; for example, using an `eventId` key as a unique constraint in the database, checking whether it has already been processed before causing side effects.

### 11.2. Why catching and logging is not enough

```java
@Override
public void onMessage(Message message) {
    try {
        saveOrder(message);
    } catch (RuntimeException e) {
        logger.error("Cannot process order", e);
        // returning normally -> Spring container may commit.
    }
}
```

This is an **illustrative anti-pattern** because `saveOrder` and `logger` are undefined. If using a transacted `DefaultMessageListenerContainer`, propagate errors that cannot be completed or record a controlled error-handling path to durable storage. If a poison message loops repeatedly, a broker DLQ/retry limit is the right mechanism to prevent infinite retries.

### 11.3. Observing processing status

Minimum metrics:
- `jms_listener_received_total`.
- `jms_listener_processed_total` and `jms_listener_failure_total`.
- `jms_listener_processing_seconds` by destination/type.
- Broker queue depth, in-flight/unacknowledged, consumer count, redelivery count, and DLQ count.
- Number of listener container restarts/reconnects and recovery latency.
- Business-level duplicates eliminated by idempotency.

Do not use raw `onMessage` log line counts alone to measure "exactly once per event": one event may be received again due to rollback, or multiple events may share the same payload.

## 12. Testing: Proving Correctness Beyond Reading stdout

### 12.1. Happy path integration

1. Start a dedicated Artemis broker for testing, create Queue `learning.listener.queue` or enable auto-create.
2. Run a Spring context with exactly **one test listener container**.
3. Send a message with a distinct `eventId` via `JmsTemplate`.
4. Wait for the listener to receive using `CountDownLatch` or Awaitility with a finite timeout.
5. Verify the listener was invoked with the expected body/properties and no exceptions.
6. To verify **commit**, inspect broker receive/ack state after the callback (the latch only shows the callback ran).

### 12.2. Rollback and redelivery

1. Configure `setSessionTransacted(true)`.
2. Create a test listener that throws `RuntimeException` on the first attempt and succeeds on the next.
3. Send one message.
4. Verify the broker redelivers per policy and `JMSXDeliveryCount`/`JMSRedelivered` change as expected.
5. Verify the business handler does not cause duplicate side effects.

Do not assume the broker always redelivers immediately: redelivery delay, max delivery attempts, and dead-letter address depend on Artemis configuration. With an application-managed transacted raw `MessageListener`, **throwing an exception does not automatically roll back**; tests must reflect the actual commit/rollback mechanism.

### 12.3. Concurrency

- Send multiple messages with distinct IDs; enable `setConcurrency("2-4")`.
- Ensure the shared listener bean is thread-safe and loses no state updates.
- Do not assert that completion order matches producer send order when competing consumers are present.
- Measure throughput, latency, actual consumer count, and work distribution rather than only checking that each message "logged".

### 12.4. Broker outage, reconnect, and shutdown

- Stop the broker, confirm the container logs errors and performs recovery/backoff.
- Restart the broker, verify consumers reconnect and process pending messages.
- Stop the Spring application while a callback is running, verify graceful shutdown within the wait timeout.
- Ensure no persistent producer/consumer/session leaks occur across multiple restarts.

### 12.5. Unit testing the listener without a broker

`DemoOrderListener.onMessage` accepts the `Message` interface, so it can be unit tested with a mocked `TextMessage` or test provider instance. With Mockito:

```java
// Illustrative snippet inside a JUnit test with Mockito.
TextMessage message = mock(TextMessage.class);
when(message.getText()).thenReturn("event:demo-001");

AsyncMessageListenerApplication.DemoOrderListener listener =
        new AsyncMessageListenerApplication.DemoOrderListener();

listener.onMessage(message);
assertTrue(listener.await(1, TimeUnit.SECONDS));
```

This is not a complete test class; it requires JUnit/Mockito dependencies and imports. It tests callback logic, **not** broker delivery, ack, or Spring container transactions; those require integration tests.

## 13. Troubleshooting — Most Common Pitfalls

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `onMessage` is never called in raw JMS | `connection.start()` not called, listener not set, or method exits/closes resources too early | Register listener before `start`, keep connection/consumer alive. |
| `onMessage` does not run in Spring | Container bean not scanned/started, wrong Queue, broker unavailable | Check `@Bean`, context lifecycle, Queue/address, logs/recovery. |
| `ClassCastException` from `TextMessage` | Producer sent BytesMessage/ObjectMessage or used another converter | Check `instanceof` and schema/payload conventions. |
| `JMSException` when reading text | Provider/message error | Catch and rethrow as unchecked or handle per policy. |
| Message processed yet remains on Queue / redelivered | Transaction rolled back, JVM crashed before ack, redelivery policy | Check JMS transaction/ack mode, JMSRedelivered, JMSXDeliveryCount. |
| Listener fails yet message does not retry in DMLC | `AUTO_ACKNOWLEDGE`, or exception caught and swallowed | Set `sessionTransacted=true` and propagate errors appropriately. |
| Processed twice when DB write succeeded | JMS commit failed / JVM crashed and message was redelivered | Use idempotent consumer/inbox/unique event ID. |
| Running with concurrency 4 yet only one callback runs at a time | Few messages in Queue, shared lock, scaling config, or provider prefetch | Measure actual consumers/tasks, state/locks, and real load. |
| Messages do not reach listener due to selector | Properties do not match selector expression | Check JMS property names and selector syntax. |
| Using Topic but wanting Queue competing consumers | Different subscription model | Configure `pubSubDomain` and durable/shared appropriately. |
| Added `@JmsListener` and demo stops receiving | Another competing consumer took the message | Use only one consumer mechanism in an isolated demo. |
| `MessageListener` uses session from multiple threads | Violates Jakarta Messaging session rules | Separate sessions or let the Spring container manage them. |
| Infinite retries on poison message | No max delivery / DLQ | Set broker policy and handle poison messages separately. |
| Broker down causes app to keep retrying | Recovery interval/backoff inappropriate | Adjust backoff, alerts, readiness, and broker health checks. |
| Closing JMS factory inside `onMessage` | Destroys shared resource and lifecycle | Let the container stop/close on shutdown. |
| Confusing `CompletionListener` with `MessageListener` | Used wrong producer/consumer callback | Choose the right API: receiving vs sending. |

## 14. Production Checklist

- Choose Queue or Topic and define subscription semantics before registering a listener.
- With native Jakarta Messaging: create consumer, call `setMessageListener`, then `connection.start()`; keep connection/session alive for the proper lifecycle.
- Do not mix synchronous `receive` and an async listener on the same active `Session`.
- With Spring: let the listener container manage resources; prefer `DefaultMessageListenerContainer` for most cases needing flexible recovery/transactions.
- Verify `sessionTransacted=true` if the Queue holds important data; understand acknowledgement differences between raw JMS and each container.
- Do not swallow exceptions and let the container commit; use retry/DLQ to handle transient errors and poison messages.
- Ensure listener beans are thread-safe when using multiple concurrent sessions, and do not require global ordering when concurrency > 1.
- Attach an `eventId` and implement an idempotent consumer, especially when performing database/HTTP work outside the JMS transaction.
- Monitor processing latency, rollback/redelivery, backlog, broker reconnects, and shutdown.
- Test against a real broker; do not infer transaction results from an "onMessage invoked" log.
- Distinguish standalone Spring Boot environments from Jakarta EE containers when choosing JMS APIs and resource factories.
- Use secrets/TLS and least-privilege send/consume permissions; never print broker passwords.

## 15. Knowledge Self-Check

**1. How does MessageListener free an application from writing a `receive()` loop?**

The consumer registers `onMessage`; the provider or Spring listener container proactively dispatches messages to the callback when a matching message is available.

**2. If you register a listener without calling `connection.start()` in Classic JMS, what happens?**

Delivery may not have started yet, so the callback is not invoked even though the broker has messages.

**3. Why does a single `Session` with three MessageConsumers not automatically process three messages in parallel?**

Jakarta Messaging serializes listener callbacks belonging to the same `Session`. True parallelism requires multiple sessions.

**4. Does `DefaultMessageListenerContainer` require calling `consumer.setMessageListener` to provide async receiving to the app?**

No. DMLC normally uses worker threads calling `receive` and then invokes the listener. `SimpleMessageListenerContainer` is the one closer to native provider callbacks via `setMessageListener`.

**5. With Spring DMLC `sessionTransacted=true`, what is the effect of the callback throwing an exception?**

The container rolls back the local JMS transaction, and the broker can redeliver according to policy. Conversely, swallowing the exception and returning normally may cause the container to commit.

**6. With a raw transacted `MessageListener`, does throwing RuntimeException automatically guarantee a rollback?**

No. Per Jakarta Messaging, session commit/rollback must be controlled through the proper mechanism; do not assume Spring container behavior applies to raw JMS.

**7. Does increasing concurrency from 1 to 4 guarantee preserving business completion order?**

No. Multiple consumers can process concurrently, so completion order is no longer guaranteed to match send order on a Queue.

**8. When executing SQL and then the JMS message is redelivered, what prevents updating SQL twice?**

Designing an idempotent consumer/inbox/dedup using a business `eventId`, or true transaction coordination where appropriate. A local JMS transaction does not include the SQL transaction.

## Conclusion

`jakarta.jms.MessageListener` is the core interface for **receiving JMS messages asynchronously**: define `onMessage(Message)` and register it with a `MessageConsumer`. In native Jakarta Messaging, the provider dispatches callbacks, each `Session` serializes processing, and `Connection.start()` opens delivery.

In Spring Framework, this same interface can be supplied to `SimpleMessageListenerContainer` or `DefaultMessageListenerContainer`. The container takes responsibility for connections, consumers, threads, recovery, acknowledgements, and transactions. `@JmsListener` is a higher-level abstraction for POJOs, not a different API for sending messages. For critical systems, combine **local JMS transactions, redelivery/DLQ policies, idempotency, and operational observability**; never equate "`onMessage` ran" with "all business work committed exactly once".

## References

- Jakarta Messaging 3.1 — `MessageListener` Javadoc: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messagelistener
- Jakarta Messaging 3.1 — Specification, sections 6.2.5, 6.2.13–14, and 8.7 (*Receiving messages asynchronously*): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework 6.2 — *Receiving a Message* and *Asynchronous Receipt: Message-Driven POJOs*: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework 6.2 — *Message Listener Containers*: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — *Annotation-driven Listener Endpoints*: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — `DefaultMessageListenerContainer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.2 — `SessionAwareMessageListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/SessionAwareMessageListener.html
- Spring Boot 3.5 — JMS and Artemis: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring Guide — *Messaging with JMS*: https://spring.io/guides/gs/messaging-jms/
- Apache ActiveMQ Artemis — *Using JMS*: https://artemis.apache.org/components/artemis/documentation/latest/using-jms