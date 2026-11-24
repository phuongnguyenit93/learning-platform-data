# MessageConsumer and Receiving Operations in Jakarta JMS / Spring JMS

## 1. Lesson Objectives

`MessageConsumer` is the Jakarta Messaging (JMS) interface used to **receive messages from a destination** (`Queue` or `Topic`). A consumer is created within a `Session`, bound to a destination, and can receive in two modes:

- **Synchronous:** code explicitly calls `receive()`, `receive(timeout)`, or `receiveNoWait()`.
- **Asynchronous:** registers a `MessageListener` so the JMS provider invokes `onMessage(Message)` when a message arrives.

In Spring Framework, you still need to understand `MessageConsumer` to grasp delivery mechanics, wait timeouts, connection lifecycle, acknowledgment, and transactions accurately. However, business code typically uses `JmsTemplate` for synchronous receiving or `@JmsListener` for asynchronous receiving; Spring manages many JMS resources on the application's behalf.

This lesson focuses on the **message-receiving API** and the conditions under which a message is delivered, acknowledged, redelivered, or not received immediately. Examples use **Jakarta Messaging 3.x, Java 17+, and Spring Boot 3.5.x**; the Java package is `jakarta.jms`, not the legacy Java EE/JMS `javax.jms`.

## 2. Where Does MessageConsumer Sit in JMS Architecture?

A typical receiving flow:

~~~mermaid
flowchart LR
    P["MessageProducer"] --> D[("Queue / Topic")]
    D --> C["MessageConsumer"]
    C --> R{"Receive mode"}
    R --> S["receive(...) in the calling thread"]
    R --> A["MessageListener.onMessage(...)"]
    C --- SE["Session"]
    SE --- CO["Connection"]
    CO --- F["ConnectionFactory"]
~~~

- **`ConnectionFactory`** creates connections to the JMS provider/broker.
- **`Connection`** represents the JMS connection and holds message delivery start/pause state. `connection.start()` enables message delivery to consumers; merely creating a consumer is not enough.
- **`Session`** is a single-logical-thread context for creating messages, producers, and consumers; it also holds acknowledgment mode and transaction state.
- **`Destination`** is a `Queue` or `Topic`. `Session.createQueue("orders.queue")` creates an object representing the target name; **it does not necessarily create a physical queue on the broker**. Provisioning/auto-creation depends on the provider.
- **`MessageConsumer`** subscribes to a destination, optionally with a message selector. The consumer receives a `Message` and processes its data and metadata.

Queue example: if there are multiple independent consumers on the same queue, they compete for message deliveries. Topic example: separate subscriptions can each receive corresponding copies. `MessageConsumer` works for both, though message retention, subscriptions, and fan-out differ.

A consumer is bound to the `Session` that created it; do not treat it as an independent object that can be shared arbitrarily across threads or applications.

## 3. Creating a MessageConsumer Properly

In the classic API (still a standard API in Jakarta Messaging 3.x):

~~~java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

// Illustrative snippet inside a method that already has ConnectionFactory factory:
try (Connection connection = factory.createConnection();
     Session session = connection.createSession(
             false, Session.AUTO_ACKNOWLEDGE)) {

    Queue queue = session.createQueue("orders.queue");
    try (MessageConsumer consumer = session.createConsumer(queue)) {
        connection.start();
        // Call consumer.receive(...) or register a MessageListener.
    }
}
~~~

The snippet above requires an initialized `factory` and an existing queue on the broker, so it is **not a standalone Java program**. It illustrates initialization order, starting delivery, and closing resources.

Overloads to know:

| `Session` Call | Purpose |
| --- | --- |
| `createConsumer(destination)` | Receive messages from the destination without a selector. |
| `createConsumer(destination, selector)` | Receive only messages matching the selector expression on headers/properties. |
| `createConsumer(destination, selector, noLocal)` | Adds the option to ignore messages published by the same connection; **`noLocal` is meaningful for Topics**, not for filtering a Queue by sending app. |
| `createDurableConsumer(topic, name)` | Consumer for a durable Topic subscription, subject to subscription/client ID requirements. |
| `createSharedConsumer(topic, name)` / `createSharedDurableConsumer(...)` | Shared Topic subscription, allowing multiple consumers to share one subscription. |

Do not confuse `session.createConsumer(queue)` with `connection.createConsumer(...)`: classic consumers are created by **`Session`**. With the simplified API, `JMSContext` creates a **`JMSConsumer`** — a different interface, see Section 10.

### 3.1. When to Call `connection.start()`

Typical order:

1. Create `Connection`.
2. Create `Session`.
3. Create `MessageConsumer` and, if needed, `setMessageListener`.
4. Call `connection.start()`.
5. Receive/process messages; finally close resources.

A newly created connection starts in the **stopped** state for message delivery. Producers can still send before `connection.start()`; calling `start()` enables the flow **delivering to consumers**, rather than being a "connect to server" step. `connection.stop()` pauses delivery and `start()` resumes it; `close()` releases the connection.

For listeners, complete consumer creation and listener registration **before calling start**, especially when multiple listeners share a session. Sessions have strict threading constraints (Section 7).

## 4. Three Synchronous Receive Methods

`MessageConsumer` returns a `jakarta.jms.Message` object or `null` according to API conditions:

| Method | Behavior | When to Use |
| --- | --- | --- |
| `receive()` | Waits indefinitely until a message arrives or the consumer is closed. | Dedicated worker waiting actively with a design-level shutdown/interrupt mechanism. |
| `receive(5000)` | Waits up to roughly 5,000 ms. Returns `null` if the timeout expires or the consumer closes before receiving. | Bounded polling, scheduled jobs, deadline-based processing. |
| `receive(0)` | **Also waits indefinitely**, not non-blocking. | Avoid using by mistake when intending an immediate check. |
| `receiveNoWait()` | Returns a message immediately if available; otherwise returns `null`. | Non-blocking check; does not guarantee a message will not arrive right afterward. |

The `timeout` unit of `receive(long)` is **milliseconds**. `null` indicates *this call did not receive a message*; it does not mean the queue is permanently empty, no producer ever sent, or a message was lost. On a Queue with multiple consumers, a message may have just been delivered to another consumer.

Example handling `null` and payload types properly:

~~~java
// Fragment inside a method that already has MessageConsumer consumer:
Message message = consumer.receive(2_000);

if (message == null) {
    System.out.println("No message within 2 seconds");
} else if (message instanceof jakarta.jms.TextMessage text) {
    System.out.println("Received: " + text.getText());
} else {
    System.out.println("Other message type: "
            + message.getClass().getSimpleName());
}
~~~

`receive()` and `receive(timeout)` are **blocking** operations on the calling thread; never call them without bounds on an HTTP server request thread. `receiveNoWait()` does not block waiting for a message, but calling it continuously in a tight loop becomes *busy polling*. For continuous event-driven processing, prefer asynchronous listeners.

### 4.1. Reading Body and Metadata

A received message has a specific type: `TextMessage`, `BytesMessage`, `MapMessage`, `ObjectMessage`, etc. You can use `message.getBody(String.class)` for compatible content (such as `TextMessage`). If the body type is incompatible, the API may throw `MessageFormatException`; do not force every message into a string.

Useful fields for diagnostics include:

- `getJMSMessageID()`: identifier assigned by the JMS provider upon sending (if enabled).
- `getJMSCorrelationID()`: links a message to a request/response or related workflow.
- `getJMSRedelivered()`: flag indicating the message may have been delivered previously.
- `getJMSReplyTo()`: destination that may be used for sending a reply.
- `getJMSTimestamp()`, `getJMSExpiration()`, `getJMSPriority()`, `getJMSDeliveryMode()`: timing and delivery policy metadata.
- `getStringProperty("region")`, `getIntProperty("attempt")`, `getIntProperty("JMSXDeliveryCount")`: reads custom or JMS-defined properties if present.

**Do not use `JMSMessageID` as an absolute substitute for a business deduplication key.** A producer may resend the same business event in a new message with a brand-new JMS ID. Maintain a business-stable `eventId`.

## 5. Runnable Example: Synchronous and Asynchronous Receive with MessageConsumer

This example uses **Spring Boot only to configure `ConnectionFactory` and start an embedded ActiveMQ Artemis broker**; creating `Session`, `MessageProducer`, and `MessageConsumer` is done directly via the **Jakarta JMS API**, making the real lifecycle visible.

Requirements: **Java 17+, Maven 3.6.3+**. Structure:

~~~text
message-consumer-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jmsconsumer/
    │   └── MessageConsumerDemoApplication.java
    └── resources/application.properties
~~~

### 5.1. Maven

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>message-consumer-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
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

Spring Boot manages the Artemis version from its dependency BOM. The starter provides the JMS client and auto-configuration; `artemis-jakarta-server` provides the embedded broker.

### 5.2. Configuration

`src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.sync,demo.async
spring.artemis.embedded.persistent=false
spring.main.banner-mode=off
~~~

Two independent queues prevent the synchronous consumer from "stealing" messages meant for the asynchronous section. Persistence is intentionally disabled for practice; **do not use this demo as evidence of message survival across broker restarts**.

### 5.3. Complete Java Code

`src/main/java/com/example/jmsconsumer/MessageConsumerDemoApplication.java`:

~~~java
package com.example.jmsconsumer;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

@SpringBootApplication
public class MessageConsumerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessageConsumerDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(ConnectionFactory factory) {
        return args -> {
            receiveSynchronously(factory);
            receiveAsynchronously(factory);
        };
    }

    private static void receiveSynchronously(ConnectionFactory factory)
            throws JMSException {

        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(false, Session.AUTO_ACKNOWLEDGE)) {

            Queue queue = session.createQueue("demo.sync");

            try (MessageProducer producer = session.createProducer(queue);
                 MessageConsumer consumer = session.createConsumer(queue)) {

                producer.send(session.createTextMessage("HELLO-SYNC"));
                connection.start();

                Message message = consumer.receive(5_000);
                if (message == null) {
                    throw new IllegalStateException("Timeout waiting for demo.sync");
                }

                System.out.println("sync: " + message.getBody(String.class));

                Message other = consumer.receiveNoWait();
                System.out.println("no-wait empty: " + (other == null));
            }
        }
    }

    private static void receiveAsynchronously(ConnectionFactory factory)
            throws JMSException, InterruptedException {

        CountDownLatch delivered = new CountDownLatch(1);
        AtomicReference<JMSException> callbackError = new AtomicReference<>();

        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(false, Session.AUTO_ACKNOWLEDGE)) {

            Queue queue = session.createQueue("demo.async");

            try (MessageProducer producer = session.createProducer(queue);
                 MessageConsumer consumer = session.createConsumer(queue)) {

                // Register callback BEFORE starting message delivery.
                consumer.setMessageListener(message -> {
                    try {
                        System.out.println(
                                "async: " + message.getBody(String.class));
                    } catch (JMSException exception) {
                        callbackError.set(exception);
                        throw new IllegalStateException(exception);
                    } finally {
                        delivered.countDown();
                    }
                });

                producer.send(session.createTextMessage("HELLO-ASYNC"));
                connection.start();

                if (!delivered.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Timeout waiting for async callback");
                }
                if (callbackError.get() != null) {
                    throw new IllegalStateException(
                            "Callback failed", callbackError.get());
                }
            }
        }
    }
}
~~~

**Detailed explanation:**

1. Spring Boot's `ConnectionFactory` is injected into `ApplicationRunner`.
2. Each method uses its **own Connection + Session** and a consumer, then closes them via `try-with-resources`.
3. `producer.send(...)` executes before `connection.start()` to ensure the message is placed in the queue before receiving begins.
4. `receive(5_000)` includes a timeout so the application does not hang indefinitely if configuration/broker fails.
5. `receiveNoWait()` immediately checks `demo.sync` after consuming the single message.
6. The async example registers `setMessageListener` and then calls `start()`. The provider invokes the callback on the session's delivery thread; the calling thread does not run a `receive` loop itself.
7. `CountDownLatch` makes the demo wait up to five seconds for the callback before closing the consumer. Callback completion and broker delivery acknowledgment are two related logical points, not a single business commitment measurement.
8. Callback errors are captured and reported back to the demo runner thread. Production applications require explicit error-handling, transaction, and redelivery strategies.

Run in the `message-consumer-demo` directory:

~~~bash
mvn spring-boot:run
~~~

Alongside Spring/Artemis startup logs, on a fresh demo broker with no other producers, the application will output:

~~~text
sync: HELLO-SYNC
no-wait empty: true
async: HELLO-ASYNC
~~~

These are **the lines printed by application code**, not the entirety of Maven/Spring Boot stdout. The `async` line is printed from inside the callback; `CountDownLatch` only coordinates demo termination timing and does not turn the callback into a synchronous JMS call.

## 6. Asynchronous Receiving with MessageListener

`setMessageListener(MessageListener listener)` instructs the provider to deliver messages to `listener.onMessage(Message)` once the connection permits delivery. When the listener is no longer needed, close the consumer or its enclosing resources. `getMessageListener()` retrieves the registered listener; `getMessageSelector()` retrieves the selector in use by the consumer.

### 6.1. How Does a Callback Differ from a Receive Loop?

| Synchronous Receive | Asynchronous Receive |
| --- | --- |
| Application calls `receive` to pull messages. | JMS provider calls `onMessage` when a message arrives. |
| Calling thread may block waiting for a message. | Calling thread is free for other work; callback runs in the provider's delivery context. |
| Easy to build "fetch one message and return result" flows. | Ideal for workers reacting continuously to events. |
| Application must explicitly organize polling loops. | Provider/container coordinates delivery; application manages lifecycle. |

**Do not mix `receive()` and a listener on the same `Session`.** The JMS spec treats `Session` as a single-logical-thread context: once an async listener is attached, the session is dedicated to the delivery thread and must not be used concurrently for synchronous receives. Changing a listener while a consumer is actively receiving also has undefined behavior; configure it before `connection.start()`.

If a callback performs slow work, other messages **on the same session** must wait because the session serializes listener invocations. Parallel processing requires multiple sessions/consumers; one connection can hold multiple sessions, provided each session's threading restriction is respected. Spring listener containers offer built-in concurrency instead of spawning manual threads.

### 6.2. Handling Callback Errors

`MessageListener.onMessage` does not declare `throws JMSException`, so checked errors while reading a message must be caught. **Do not simply catch an exception, log it, and return normally** if doing so causes the provider/container to treat the message as successfully processed.

Distinguish behavior between plain Jakarta JMS and a Spring container:

- In **plain JMS**, throwing a `RuntimeException` from `onMessage` has effects depending on the acknowledgment mode; notably, a **transacted Session does not automatically roll back solely because `onMessage` throws a RuntimeException**. The application must manage `commit()/rollback()` according to session context.
- In **Spring `DefaultMessageListenerContainer` configured with session transacted**, an exception escaping the listener normally causes the container to roll back the JMS transaction and the broker to redeliver per policy.
- With `AUTO_ACKNOWLEDGE`, acknowledgment occurs when `receive` returns normally or the listener **completes successfully**; do not equate this with external operations (DB, HTTP) having committed.
- For slow or unstable callbacks, use timeouts, processing observability, DLQ, and idempotency. Retry count and delay policies belong to the broker.

### 6.3. What Does `Consumer.close()` Do?

`consumer.close()` stops delivery to the consumer and releases provider resources. If another thread is blocked inside `receive()`, closing waits for that receive to finish; a waiting receive may return `null` when the consumer closes. If a listener is currently executing, closing waits for that callback to finish. `close()` is the only method on `MessageConsumer` specified to allow concurrent invocation in this way.

Closing a consumer **does not automatically commit a JMS transaction and does not automatically acknowledge unacknowledged messages**. Acknowledgment/transaction state belongs to the `Session`. When finished, also close the session/connection or let the Spring container manage them. Avoid closing the connection/session from inside a callback in ways that cause deadlocks or unpredictable provider behavior.

## 7. Session, Acknowledgment, and Transactions When Receiving

`MessageConsumer` does not independently decide that a message is "processed". That decision belongs to the **`Session`**, its mode, and its transaction state.

| `Session` Mode | When Is a Message Acknowledged? | Consequence |
| --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | After `receive` returns normally or after `onMessage` returns normally. | Simple; if a DB update after `receive` fails, the message may already be acked. |
| `CLIENT_ACKNOWLEDGE` | Application calls `message.acknowledge()`. | A single ack can acknowledge **all messages delivered in the same session**. |
| `DUPS_OK_ACKNOWLEDGE` | Provider may defer acknowledgment. | Reduces overhead in some scenarios but accepts higher chance of redelivery. |
| `SESSION_TRANSACTED` | `session.commit()` acknowledges received messages in the transaction; `rollback()` aborts the JMS work and permits redelivery. | Appropriate when controlling receive/process boundaries; does not automatically enlist an external DB transaction. |

### 7.1. Why Can `AUTO_ACKNOWLEDGE` Be Too Early?

In **synchronous** receiving, right after `consumer.receive(...)` returns successfully, JMS may have already acknowledged delivery. If subsequent code fails while writing to a database, the broker may no longer hold the message for retry. In **asynchronous** receiving, acknowledgment generally happens at the end of a successful callback, yet it still does not fold a database transaction into the JMS transaction.

For workloads requiring reliable retries, consider a transacted session, a Spring transacted listener container, or proper transaction coordination instead of defaulting to `AUTO_ACKNOWLEDGE`.

### 7.2. `CLIENT_ACKNOWLEDGE`: Ack Scope Is the Entire Session

Illustrative example inside a method that already owns a session and queue; **fragment, not a standalone program**:

~~~java
Session session = connection.createSession(
        false, Session.CLIENT_ACKNOWLEDGE);
MessageConsumer consumer = session.createConsumer(queue);

// After connection.start() at the right time:
Message first = consumer.receive(3_000);
if (first != null) {
    // Complete business processing successfully first.
    first.acknowledge();
}
~~~

If the session has received multiple unacknowledged messages, calling `acknowledge()` on one message can acknowledge **all messages consumed by that session**, not only `first`. To request redelivery of unacknowledged messages in a non-transacted session, the API provides `session.recover()` (subject to threading/listener context rules).

### 7.3. Transacted Receive: Commit or Rollback

Fragment example showing transaction placement:

~~~java
// Illustrates steps inside a method that already created Connection connection
// and Queue queue, with business handler process(message).
Session tx = connection.createSession(true, Session.SESSION_TRANSACTED);
MessageConsumer consumer = tx.createConsumer(queue);
connection.start();

Message message = consumer.receive(5_000);
if (message != null) {
    try {
        process(message);   // Application-defined business handler.
        tx.commit();        // Acknowledge message receipt in the JMS transaction.
    } catch (Exception exception) {
        tx.rollback();      // Allow redelivery according to provider policy.
        throw exception;
    }
}
~~~

This snippet is **not standalone** because `connection`, `queue`, and `process` are provided by the application and outer scopes must handle resource closing. In a transacted session, the acknowledgment mode argument is normally ignored; `commit()`/`rollback()` alone governs acknowledgment.

Key point to remember: **a local JMS transaction does not automatically include JDBC writes, REST calls, email sends, or payments**. For example, if a consumer writes to the DB successfully and crashes before JMS commit, the broker can redeliver the message, requiring an idempotent consumer keyed by business `eventId`; when sending messages from a DB transaction, consider an outbox.

## 8. Message Selectors: Conditional Receiving

`Session.createConsumer(destination, selector)` creates a consumer that receives only messages whose **headers/properties match** a JMS selector expression (a SQL-92 subset), without reading JSON/text bodies directly.

Example where producer sets properties and consumer filters:

~~~java
// Fragment: producer, session, and queue have been created.
TextMessage order = session.createTextMessage("ORDER-101");
order.setStringProperty("region", "VN");
order.setIntProperty("amount", 120);
producer.send(order);

// Create consumer before connection.start().
MessageConsumer selected = session.createConsumer(
        queue, "region = 'VN' AND amount >= 100");
~~~

In a real Java file, import `jakarta.jms.TextMessage` and the related APIs. This consumer will not receive messages with `region='US'` or properties failing the condition. Non-matching messages remain waiting for other consumers; a selector does not "delete" messages.

Distinguish clearly:

- `region = 'VN'` reads the **string property** `region`.
- `amount >= 100` reads the **numeric property** `amount`.
- `NULL`/missing properties and type rules can cause expressions not to match.
- To filter by a JSON field like `customer.region`, promote the needed filter fields into JMS properties when the producer builds the message, or design dedicated queues/routes.
- When one queue has consumers using different selectors, ensure every important message category has a matching consumer to prevent unbounded buildup.
- Selectors **do not replace authorization or protection of sensitive data**.

`consumer.getMessageSelector()` returns the configured expression or `null` if no selector is set.

## 9. Constraints on Ordering, Parallelism, and Redelivery

### 9.1. One Session Does Not Yield Parallel Processing

A session serializes delivery to all listeners in that session. Two consumers on the **same session** do not mean two callbacks run concurrently. Increasing throughput requires **multiple sessions** (typically a dedicated session per listener/worker), or Spring `@JmsListener` combined with listener container concurrency settings.

For Queues, two concurrent consumers can finish out of arrival order. For Topics, each subscription has its own semantics; which messages a consumer receives also depends on subscription type (shared/durable/unshared), consumer lifetime, and selectors.

### 9.2. Redelivery Does Not Mean "Exactly-Once Processing"

Situations that can produce redeliveries or business duplicates:

1. A consumer receives a message without committing/acking, then loses its connection.
2. A transaction is rolled back.
3. The application writes to the DB and fails before JMS commit.
4. The producer retries sending a business action as a new message because it could not verify whether the first send succeeded.

Inspect `JMSRedelivered` and `JMSXDeliveryCount` for observability, but **do not rely solely on these flags/counts to skip business processing**. Design idempotent consumers: stable `eventId`, unique constraints, transactional inbox, or equivalent mechanisms.

### 9.3. Common Resource and Threading Mistakes

- Sharing one `Session` across multiple threads calling `receive` concurrently: **violates the threading model**; use separate sessions.
- Registering `setMessageListener` and still calling `receive` on that same session: **invalid**.
- Calling `receive(0)` expecting non-blocking behavior: it actually waits indefinitely.
- Using `AUTO_ACKNOWLEDGE` and updating a DB after synchronous `receive` returns, expecting the broker to retry on DB failure: the retry opportunity may already be lost.
- Forgetting `connection.start()`: the consumer is created, yet no messages are delivered.
- Forgetting to close consumer/session/connection: leaks broker resources and threads.
- Creating an extra consumer just to "peek whether messages exist": it can **consume messages off the queue**. To inspect without consuming, use `QueueBrowser` or broker admin metrics; a browser is a separate API reflecting only a non-atomic snapshot.
- Catching errors in a listener and returning as if successful: may cause the message to be acked instead of retried as intended.
- Assuming `createQueue("name")` always creates a physical queue: provisioning behavior belongs to the provider.

## 10. From Plain Jakarta JMS to Spring Framework

Spring provides abstractions that eliminate lifecycle and error-handling boilerplate:

| Need | Direct Jakarta JMS | Spring JMS |
| --- | --- | --- |
| Synchronous receive | `MessageConsumer.receive(timeout)` | `JmsTemplate.receive(...)`, `receiveAndConvert(...)` |
| Receive with selector | `session.createConsumer(queue, selector)` | `JmsTemplate.receiveSelected(...)` or `@JmsListener(selector=...)` |
| Asynchronous receive | `consumer.setMessageListener(...)` | `@JmsListener(destination=...)` |
| Session/connection management | Application closes resources and manages concurrency | `JmsTemplate` / listener container manages most lifecycle |
| Listener transactions | Code calls `commit()/rollback()` on local JMS session | Configure transacted container or appropriate transaction manager |
| Payload conversion | Manually read `Message`/body | `MessageConverter` and listener parameter binding |

### 10.1. `JmsTemplate` for Synchronous Receiving

Example in a Spring bean with `JmsTemplate` injected:

~~~java
// Fragment inside a Spring-managed bean:
jmsTemplate.setReceiveTimeout(2_000);
Object payload = jmsTemplate.receiveAndConvert("orders.queue");
if (payload == null) {
    System.out.println("No message received yet");
}
~~~

`setReceiveTimeout(2_000)` limits waiting to about 2 seconds. In `JmsTemplate`, **0 means wait indefinitely; negative values like `-1` mean no-wait**. `JmsTemplate` defaults to waiting indefinitely, so configure it explicitly when running on time-bounded threads. `receive(...)` returns a raw `jakarta.jms.Message`; `receiveAndConvert(...)` converts the payload via the converter and may return `null`.

**Transaction note:** `JmsTemplate.receiveAndConvert` receives and converts the message, yet commit/ack may occur before subsequent business logic runs. When business work must share a transaction boundary with receiving, wrap the logic in an appropriate transaction configuration or use a transacted listener.

### 10.2. `@JmsListener` for Asynchronous Receiving

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue", concurrency = "2")
    public void onOrder(String orderId) {
        System.out.println("Received " + orderId);
    }
}
~~~

This is a **Spring-managed class**, requiring enabled JMS listener infrastructure (such as `@EnableJms`) and a valid `ConnectionFactory`. Spring creates consumers inside a listener container; you do not manually call `connection.start()` or `MessageConsumer.receive()`.

`concurrency="2"` lets two listener consumers/sessions compete for messages when the destination is a Queue; parallel processing can alter completion order. In production applications, configure transactions/acknowledgment and retry/DLQ on the listener container and broker; this example only demonstrates the API.

### 10.3. `JMSConsumer` in the Simplified API

Jakarta Messaging 2.0+ also provides `JMSContext` and `JMSConsumer`, reducing checked-exception boilerplate and generally auto-starting delivery when the context has auto-start enabled:

~~~java
// Fragment when jakarta.jms.ConnectionFactory factory is already available.
try (jakarta.jms.JMSContext context = factory.createContext()) {
    jakarta.jms.Queue queue = context.createQueue("orders.queue");
    jakarta.jms.JMSConsumer consumer = context.createConsumer(queue);
    String body = consumer.receiveBody(String.class, 2_000);
    if (body != null) {
        System.out.println(body);
    }
}
~~~

`JMSConsumer` and `MessageConsumer` are distinct interfaces, both serving the receiving role. `JMSContext` still wraps a session and enforces **similar threading restrictions**; auto-start does not mean it can be invoked arbitrarily from multiple threads. On Spring Boot 3.x, both use the `jakarta.jms` package.

## 11. Diagnosing Failures When Messages Are Not Received

| Symptom | First Check | Next Step |
| --- | --- | --- |
| `receive(timeout)` always returns `null` | Is the queue/topic name right? Was `connection.start()` called? Does the selector match? | Verify destination name, connection state, headers/properties, and broker metrics. |
| `receive()` hangs | No matching message; or connection not started | Use a finite timeout on interactive threads; check logs and queue depth. |
| `receiveNoWait()` returns `null` right after sending | Delivery not yet ready at check time; message may be in-flight or taken by another consumer | Do not assume no-wait observes messages immediately; use a short timeout where appropriate. |
| Listener is never invoked | Not registered, not started, listener container inactive, wrong selector | Check lifecycle and destination configuration. |
| Duplicate processing after failures | Rollback, dropped connection, producer retry | Inspect redelivery counters and implement idempotent consumers. |
| Low throughput | Slow callback, single session, slow DB, prefetch/flow control | Measure processing latency; tune session/consumer counts and downstream capacity. |
| Callback ran yet message reappears | Missing ack/commit; callback threw error; provider redelivery | Check acknowledgment mode, commit/rollback, and DLQ/retry policies. |
| Queue grows while service is online | Consumer has mismatched selector, is hung, downstream bottleneck, transaction failure | Check queue depth, in-flight count, consumer count, oldest message age, and handler errors. |

When investigating a specific message, log the **business event ID**, JMS message ID, correlation ID, `JMSRedelivered`, `JMSXDeliveryCount` if available, message type, destination name, and processing duration. Do not log payloads containing sensitive data outside authorized administrative contexts.

## 12. Practice Questions and Answers

1. **Why can `receive(0)` cause an HTTP request to hang?** Because JMS defines a timeout of 0 as waiting indefinitely. Use a positive timeout or an async design.
2. **Does `receiveNoWait() == null` prove a queue is permanently empty?** No. It only indicates no message was available to that consumer at the moment of the call.
3. **Can `setMessageListener` and `receive()` be used side-by-side on the same session?** No. A session follows a single-logical-thread model; the two modes cannot be combined like that.
4. **When does `AUTO_ACKNOWLEDGE` acknowledge a message?** When `receive` returns normally, or when a listener finishes processing and returns normally.
5. **Does `CLIENT_ACKNOWLEDGE` acknowledge one message or the entire session?** Calling ack on a message acknowledges the messages consumed by that session within that ack scope; never assume it always covers strictly one message.
6. **Does throwing a `RuntimeException` from a raw transacted `MessageListener` automatically roll back?** No. The application must manage the JMS transaction; a Spring listener container configured as transacted can roll back when the listener fails.
7. **Why does increasing consumers from 1 to 4 not guarantee processing order?** Sessions execute concurrently with varying processing durations and redeliveries.
8. **When should you choose `@JmsListener` over creating consumers manually?** When you need a long-lived asynchronous worker with lifecycle, concurrency, converters, and transactions managed by Spring.
9. **What should you use to inspect queue contents without removing messages?** `QueueBrowser` or broker management tools; `MessageConsumer.receive` is a destructive consume operation.
10. **What happens when closing `MessageConsumer`?** It stops delivery and releases consumer resources; ack/transaction state remains managed by the session.

## 13. Authoritative References

- [Jakarta Messaging 3.1 — MessageConsumer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageconsumer).
- [Jakarta Messaging 3.1 — Session API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session), especially acknowledgment, transactions, and threading.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html), sections on synchronous/asynchronous delivery, receive, and closing consumers.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html).
- [Spring Framework — Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Boot 3.5 — JMS/ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html).

**Core takeaway:** `MessageConsumer` is the point of message intake, yet **`Session` defines ack/transactions and threading limits**, and `Connection.start()` controls when delivery is allowed to run. Choose `receive(timeout)` when actively pulling with a deadline; choose listeners and Spring containers when building long-lived asynchronous consumers.
