# Connection.start(), stop(), and close() in the Core JMS API

## 1. Why Must Connection Lifecycle Be Managed?

In Jakarta Messaging (formerly Java Message Service, JMS), **`Connection`** represents the application's logical connection to a JMS provider / message broker. An application typically obtains a configured `ConnectionFactory` to create a `Connection`, and then creates `Session`, `MessageProducer`, and `MessageConsumer` objects.

This lesson focuses on the three lifecycle-control operations of the **classic JMS API**:

- **`start()`**: begins or resumes delivering messages **to consumers** belonging to the Connection.
- **`stop()`**: temporarily pauses message delivery **to all consumers** belonging to the Connection, while keeping the Connection and its resources alive so it can be restarted.
- **`close()`**: closes the Connection and its child objects, terminating its lifecycle; continuing work requires creating a new Connection.

Understanding these three operations avoids three very common mistakes: creating a consumer and forgetting to call `start()`, thinking `stop()` stops producers from sending messages, or treating `close()` like a pause that can be started again.

### 1.1. Position of Connection in the JMS API

~~~text
ConnectionFactory
    └── Connection                         (lifecycle: start / stop / close)
          ├── Session A                    (sequential processing context)
          │     ├── MessageProducer
          │     └── MessageConsumer A
          └── Session B
                ├── MessageProducer
                └── MessageConsumer B
~~~

A Connection is usually a relatively heavyweight resource because it involves authentication, network links, and provider state; a single Connection can serve multiple Sessions. **Connection supports concurrent use**, whereas **Session must adhere to a sequential usage model**; never share a single Session arbitrarily across multiple threads.

The core API centers on the Connection + Session + MessageProducer/MessageConsumer triad, with key signatures:

~~~java
Connection connection = connectionFactory.createConnection();
Session session = connection.createSession(
        false, Session.AUTO_ACKNOWLEDGE);
connection.start();
connection.stop();
connection.close();
~~~

This is an **illustrative snippet**, not a standalone runnable program: the `connectionFactory` variable must be created or retrieved from JNDI/provider. A standalone runnable example with dependencies and run commands appears in Section 5.

**Package naming:** Legacy JMS 1.x / Java EE uses `javax.jms.*`; Spring Framework 6, Spring Boot 3, and Jakarta Messaging 3.x use `jakarta.jms.*`. The three operations `start`/`stop`/`close` preserve their foundational meaning, yet do not mix both namespaces in the same program.

## 2. State Model and Actual Effects

A newly created Connection is **in the stopped state**. A link to the provider may already be established, yet the broker is not yet allowed to deliver messages to that Connection's consumers. `start()` and `stop()` toggle delivery state; `close()` terminates the resource.

~~~mermaid
stateDiagram-v2
    [*] --> Stopped: createConnection()
    Stopped --> Started: start()
    Started --> Stopped: stop()
    Started --> Closed: close()
    Stopped --> Closed: close()
    Closed --> [*]
~~~

| State | Do consumers receive new messages? | Can producers send messages? | Can it return to receiving messages? |
| --- | --- | --- | --- |
| Newly created / stopped | No; `receive(timeout)` may time out and return `null` | Yes | Yes, call `start()` |
| Started | Yes, per queue/topic and session rules | Yes | Currently receiving |
| Stopped after `stop()` | Delivery paused for all consumers on the connection | Yes | Yes, call `start()` |
| Closed | No; old sessions/consumers are no longer usable | No; old producers are no longer usable | Not on the closed connection |

**`start()` does not mean "open socket"; `stop()` does not mean "disconnect socket".** Both control **message delivery** to the receiving side of the Connection. A producer is still allowed to send messages before a Connection starts or while it is stopped. Being stopped also does not cause the broker to delete messages in a queue or remove subscriptions.

Repeated calls follow deterministic rules:

- `start()` on an already started Connection: ignored.
- `stop()` on an already stopped Connection: ignored.
- `close()` on an already closed Connection: must not throw an error merely because it is already closed.
- `start()` or `stop()` after a Connection is closed: invalid operation on a closed resource (`IllegalStateException` per the API).

Do not rely on idempotent ignore behavior to mask lifecycle management bugs. Clearly define which component owns the Connection and is responsible for closing it.

## 3. Connection.start(): Enabling Message Delivery to Consumers

### 3.1. Standard Setup Sequence

With the classic API, the typical sequence is:

1. Obtain `ConnectionFactory` and create `Connection`; initial state is stopped.
2. Create `Session` with the appropriate transaction/acknowledgment mode.
3. Create `Destination`, `MessageConsumer`, and `MessageProducer` as needed.
4. If using callbacks, register `MessageListener` via `setMessageListener(...)`.
5. **After configuration finishes**, call `connection.start()` once to permit receiving.

~~~java
Connection connection = factory.createConnection();
try {
    Session session = connection.createSession(
            false, Session.AUTO_ACKNOWLEDGE);
    MessageConsumer consumer = session.createConsumer(destination);

    // Register listener or prepare receive flow before calling start.
    connection.start();

    Message received = consumer.receive(5_000);
    // Handle received if non-null.
} finally {
    connection.close();
}
~~~

This illustrates ordering: `factory` and `destination` must be supplied before running. Calling `start()` too early and registering a listener afterward can allow messages to be delivered while the application is still setting up other objects.

### 3.2. Two Forms of Receiving Messages

**Synchronous receive:** `MessageConsumer.receive()`, `receive(timeout)`, or `receiveNoWait()` runs on the calling thread. While the Connection is stopped, `receive` may block; with `receive(timeout)`, the timer **still counts down**, so the call can return `null` on timeout even when the queue contains messages. In Jakarta Messaging, `receive(0)` means wait indefinitely; some applications accidentally pass `0` intending "do not wait" and end up stuck.

**Asynchronous receive:** `setMessageListener(...)` registers an `onMessage(Message)` callback. The provider must not deliver messages to the callback before the Connection is started. After `start()`, the listener may be invoked on a provider/container-managed thread. Do not assume one shared thread across all Sessions; sequential ordering applies within each Session's scope.

### 3.3. Producers Do Not Need `start()` to Send

An application that only sends messages can create a Connection, Session, and MessageProducer and call `send(...)` **without calling `start()`**. The `start()` call matters for the **receiving side**. Example on a stopped Connection:

~~~java
producer.send(session.createTextMessage("queued while stopped"));
// Sending a message is valid even though the connection has not started yet.
~~~

The message is accepted/stored by the broker according to destination policy, delivery mode, transactions, TTL, and provider settings; "being able to send" does not by itself promise durability across every deployment configuration.

## 4. Connection.stop(): Pausing Message Delivery

### 4.1. What Exactly Is Paused?

`connection.stop()` pauses **all consumers** belonging to that Connection, including consumers on different Sessions under the same Connection. While stopped:

- No new messages are delivered to `MessageListener.onMessage(...)` on that connection.
- Waiting `receive()` calls cannot return a new message from ongoing connection delivery; `receive(timeout)` can still expire and return `null`.
- Does not block `MessageProducer.send(...)`; does not close Sessions or `MessageConsumer`s.
- Does not delete messages on the broker, delete queues, or cancel subscriptions.
- Does not automatically commit/roll back open transactions or acknowledge messages awaiting acknowledgment.

Timeline example:

~~~text
T0: createConnection()       -> STOPPED
T1: producer.send("A")       -> sends successfully even while STOPPED
T2: consumer.receive(200)    -> null because still STOPPED
T3: connection.start()       -> STARTED
T4: consumer.receive(5000)   -> receives "A"
T5: connection.stop()        -> STOPPED
T6: producer.send("B")       -> still able to send
T7: consumer.receive(200)    -> null because STOPPED
T8: connection.start()       -> STARTED
T9: consumer.receive(5000)   -> receives "B"
~~~

This scenario has one producer and one consumer on a temporary queue as in Section 5. When multiple consumers, selectors, expirations, retries, or message priorities exist, delivery ordering cannot be reasoned about this simply.

### 4.2. `stop()` Can Block the Calling Thread

According to the specification, `stop()` **must return only after delivery has actually paused**. If any `MessageListener` is currently executing, the call must wait for those listeners to finish. During that wait, an in-flight listener must still have full access to the Connection's services to complete its work.

Consequences:

- Call `stop()` from a management/lifecycle thread when pausing consumers.
- **Do not assume `stop()` is non-blocking**; if a listener handler is slow or stuck, `stop()` can also block.
- Once `stop()` returns normally, no listener on that Connection is executing a callback; any already-received work must be handled by the corresponding application/transaction logic.
- Never call `stop()` on the same Connection from inside `onMessage()` expecting uniform behavior across providers. Jakarta Messaging allows two responses in that situation: throwing `jakarta.jms.IllegalStateException` **or** completing `stop` per spec rules. Thus such a call is **non-portable**.

**`stop()` is not a "global consumer pause".** If another instance uses its own Connection, that instance can keep receiving messages. Stopping also does not guarantee broker metrics such as queue depth change instantaneously as expected: providers may maintain internal buffers/prefetch and separate acknowledgment mechanisms.

### 4.3. When Should You Call `stop()`?

Reasonable scenarios: temporarily pausing intake for maintenance on a manual consumer; finishing setup before enabling callbacks; explicitly controlling consumption flow in a self-managed JMS program.

For graceful application-wide shutdown, you usually combine: stopping new intake, waiting/bounding time for in-flight tasks to finish, resolving transactions/acknowledgments, and then calling `close`. `stop()` alone does not replace that process.

## 5. Runnable Example with Java 17, Jakarta JMS, and Apache ActiveMQ Artemis

This example directly demonstrates the three methods in the **classic API**, without depending on a Spring container. It uses a local Artemis broker and a temporary queue created by the Session, giving each run an isolated, easily observable queue.

### 5.1. Prepare the Broker

Requires Java 17+, Maven 3.9+, Docker, and port 61616 free. Start a test broker using the official image:

~~~bash
docker run --detach --rm --name jms-lifecycle-broker -p 61616:61616 -p 8161:8161 apache/artemis:latest-alpine
~~~

Wait for the broker to listen on port 61616; the default image uses username/password `artemis`/`artemis`. These credentials are for demo use only, never for production. Use `docker logs jms-lifecycle-broker` to inspect startup if connecting fails.

Project structure:

~~~text
jms-connection-lifecycle/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── jms/
                    └── ConnectionLifecycleDemo.java
~~~

### 5.2. Maven `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jms-connection-lifecycle</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.37.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

Versions are pinned for reproducible execution. `jakarta.jms-api` provides the interfaces; `artemis-jakarta-client` provides the Artemis provider implementation. Switching libraries/providers may change factory configuration, yet the behavior of the three methods must conform to the JMS specification.

### 5.3. Complete Java Class

Place in `src/main/java/example/jms/ConnectionLifecycleDemo.java`:

~~~java
package example.jms;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ConnectionLifecycleDemo {
    private ConnectionLifecycleDemo() {}

    public static void main(String[] args) throws JMSException {
        ConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");
        Connection connection = factory.createConnection("artemis", "artemis");

        try {
            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            TemporaryQueue queue = session.createTemporaryQueue();
            MessageProducer producer = session.createProducer(queue);
            MessageConsumer consumer = session.createConsumer(queue);

            // New connection: currently STOPPED. Producer can still send.
            producer.send(session.createTextMessage("A"));
            System.out.println("Sent A before start");

            Message beforeStart = consumer.receive(200);
            System.out.println("Before start: " + describe(beforeStart));

            // Enable delivery for this connection's consumers.
            connection.start();
            Message first = consumer.receive(5_000);
            System.out.println("After start: " + describe(first));

            // Pause delivery without destroying producer/consumer.
            connection.stop();
            producer.send(session.createTextMessage("B"));
            System.out.println("Sent B while stopped");

            Message whileStopped = consumer.receive(200);
            System.out.println("While stopped: " + describe(whileStopped));

            // Re-enable on the same Connection/Session/Consumer.
            connection.start();
            Message second = consumer.receive(5_000);
            System.out.println("After restart: " + describe(second));
        } finally {
            // close() also closes all sessions/producers/consumers belonging to the connection.
            connection.close();
            System.out.println("Connection closed");
        }
    }

    private static String describe(Message message) throws JMSException {
        if (message == null) {
            return "null";
        }
        if (message instanceof TextMessage text) {
            return text.getText();
        }
        return message.getClass().getSimpleName();
    }
}
~~~

Here a single thread uses the Session and MessageConsumer; the producer sends before calling `receive`, so there is no thread contention. `TemporaryQueue` is created per Connection and automatically ends its lifecycle when the Connection closes. No static queue configuration is needed for the example.

**Line-by-line explanation:**

1. `createConnection(...)` returns a Connection in the stopped state; `createSession(...)` and `createConsumer(...)` do not auto-start in the classic API.
2. `send("A")` succeeds while stopped because `start`/`stop` affect only consumer delivery.
3. `receive(200)` receives no message; after 200 ms it can return `null`. In the demo with a healthy broker, the value is `null`.
4. `start()` lets `receive(5000)` retrieve `A`.
5. `stop()` pauses; sending `B` still works; `receive(200)` does not receive `B`.
6. Calling `start()` again lets the same consumer receive `B`.
7. `finally` always calls `close()`, even if `JMSException` is thrown; child resources managed by the Connection close with it.

If the system is slow enough that `receive(5000)` returns `null`, inspect the broker, transport, permissions, and logs. The example does not guarantee every network environment responds within 5 seconds.

### 5.4. Run the Project

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.jms.ConnectionLifecycleDemo
~~~

Expected application output with an active broker and a single consumer on the temporary queue:

~~~text
Sent A before start
Before start: null
After start: A
Sent B while stopped
While stopped: null
After restart: B
Connection closed
~~~

Additional Artemis/client logs may appear depending on logging settings; the text above shows the application's `System.out.println` lines in exact order when both `A` and `B` are received. To stop the demo container, run `docker stop jms-lifecycle-broker`.

### 5.5. Illustrating `try-with-resources`

Because `Connection` extends `AutoCloseable`, if you only need to ensure `close()` is called, you can write:

~~~java
try (Connection connection = factory.createConnection()) {
    Session session = connection.createSession(
            false, Session.AUTO_ACKNOWLEDGE);
    // Configure consumers, call start()/stop() when needed.
} // Automatically calls connection.close() even if an exception occurs.
~~~

This is an additional snippet: `factory` is created outside, and it is not a standalone runnable program. The complete program above uses `finally` to make `close()` explicit.

## 6. `close()`: Ending Lifecycle and Impact on In-Flight Messages

### 6.1. Mandatory Effects

When `connection.close()` is called:

1. The provider terminates any pending `receive` calls on the Connection's consumers. For a blocked `receive()`, termination may return **a message or `null`** depending on timing; do not assume "`null` always means the Connection closed".
2. If a listener is actively processing a message, the provider must allow that listener to finish under orderly shutdown rules; thus `close()` may **block the calling thread** until in-flight processing completes.
3. The Connection closes its associated Sessions, `MessageProducer`s, `MessageConsumer`s, and `QueueBrowser`s, releasing provider resources.
4. Once closed, operations attempting to reuse the old Connection, Session, producer, or consumer are invalid. Calling `close()` again is ignored.

Wrong example:

~~~java
connection.close();
connection.start(); // Wrong: Connection is already CLOSED, cannot restart.
~~~

Correct example if a new connection is needed:

~~~java
connection.close();
Connection next = factory.createConnection();
try {
    // Create new Session, consumer, and call next.start() when receiving.
} finally {
    next.close();
}
~~~

**`close()` is not a way to "wait for the broker to finish processing every message".** It terminates the activities of consumers belonging to that specific Connection; remaining messages in queues or durable subscriptions continue to follow the provider's storage and acknowledgment policies.

### 6.2. What Happens to Transactions and Acknowledgments?

| Session mode | `close()` impact on unfinished data |
| --- | --- |
| `SESSION_TRANSACTED` | Open JMS transactions when closing the Connection must roll back. Uncommitted sends/receives follow provider rollback rules. |
| `CLIENT_ACKNOWLEDGE` | Closing the Connection **does not force acknowledgment** of unacknowledged client messages. Do not call `message.acknowledge()` on messages from an already-closed Session. |
| `AUTO_ACKNOWLEDGE` | Ack is tied to receive/handler completion per API rules. Do not assume `close()` guarantees all tasks or external side effects completed; understand when listeners finish. |

Distinguish `close()` from `session.commit()`, `session.rollback()`, and `message.acknowledge()`. `start()`/`stop()` control delivery, **not commit or ack**. With queues or durable subscriptions, unacknowledged messages can be redelivered once a valid consumer becomes active; exact guarantees depend on delivery mode, TTL, the broker, and protocol compliance.

If an application writes DB/HTTP side effects and crashes before JMS commit/ack, the provider can redeliver. Use a business idempotency key to handle duplicates; the three lifecycle methods do not create end-to-end exactly-once semantics.

### 6.3. Avoid Calling `close()` from Inside `onMessage()`

Just like `stop()`, when a `MessageListener` calls `close()` on the Connection it is currently using, the spec permits the provider to **throw `IllegalStateException` or perform the close** per spec rules. The result is non-portable; this is not a safe shutdown pattern.

To stop a consumer on a business signal, delegate the decision to a lifecycle-management component on a coordinating thread; do not close the Connection from inside a running callback. When using a Spring container, use container lifecycle controls as in Section 8.

## 7. Distinguishing Commonly Confused Operations

| Operation | Scope | Pauses / Terminates | Can producers still send via the old Connection? |
| --- | --- | --- | --- |
| `Connection.start()` | All consumers on the Connection | Enables/resumes receiving | Yes |
| `Connection.stop()` | All consumers on the Connection | Pauses delivery | Yes |
| `Connection.close()` | Connection and child resources | Terminates | No |
| `MessageConsumer.close()` | Single consumer | Terminates that consumer | Other producers can continue if Connection stays open |
| `Session.close()` | Single Session and child resources | Terminates Session | Other Sessions can continue if Connection stays open |
| `Session.commit()` | Transaction of a transacted Session | Finalizes transaction, does not change Connection state | Yes |
| `Session.rollback()` | Transaction of a transacted Session | Aborts transaction, may trigger redelivery | Yes |

A Session must not be used concurrently from arbitrary threads. A Connection supporting multiple Sessions does not make operations sharing a single Session thread-safe. In particular, when a `MessageListener` is attached to a Session, the provider thread dispatching callbacks manages that Session's delivery sequence.

### Two Timelines Comparing `stop()` and `close()`

~~~text
PAUSE:
producer send -> queue holds message -> stop() -> no delivery to consumers
                                        |
                                        +-> start() -> consumer receives again

SHUTDOWN:
producer send -> consumer processing -> close() waits for in-flight work
                                        |
                                        +-> session/consumer/connection close
                                        +-> to start over: createConnection()
~~~

If the goal is "stop taking new jobs while letting already-received jobs finish", `stop()` can be one piece of an application-side drain flow; remember that it affects **the entire Connection** and may wait on listeners. Do not overlook timeout policies and how unacknowledged work is handled.

## 8. Connection to Spring Framework JMS

### 8.1. When Using Spring, Who Owns the Connection?

In typical Spring applications, `JmsTemplate` and listener containers create and manage Connections/Sessions through `ConnectionFactory`. Consequently, business code calling `jmsTemplate.convertAndSend(...)` or using `@JmsListener` **normally never calls `Connection.start/stop/close` directly**. Manually closing a framework-managed Connection can break other listeners and producers sharing that resource.

Example Spring-managed listener:

~~~java
@Component
class OrderListener {
    @JmsListener(id = "ordersListener", destination = "orders")
    public void handle(String body) {
        // Process message according to the container's transaction/ack configuration.
    }
}
~~~

This is a snippet inside a Spring application with JMS dependencies and `@EnableJms` or equivalent configuration; it is not a standalone class compiled solely with `javac`. Spring sets up the container, creates consumers, and manages start/stop alongside the application lifecycle.

### 8.2. Want to Pause a Spring Listener?

Control the **listener container** via `JmsListenerEndpointRegistry` or Spring's lifecycle infrastructure, for example:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");
if (container != null) {
    container.stop();   // Stop the container with the matching id.
    // ...
    container.start();  // Resume the container when permitted.
}
~~~

This is a snippet: `registry` must be injected and the listener must have id `ordersListener`. The difference is stopping/starting **a specific listener container** and its management policy; do not assume a raw `Connection.stop()` call is the right way to control a Spring endpoint. Containers may share a connection or manage multiple connections/sessions, so choose framework-level control points.

Operational notes: containers can auto-start with the application; configure `autoStartup` when manual start is required; ensure shutdown does not cut off transactions or exceed timeouts unexpectedly; resources are reclaimed by Spring when `ApplicationContext` closes according to container lifecycle.

### 8.3. Classic Connection vs. `JMSContext`

Jakarta Messaging provides the **simplified API** with `JMSContext` combining Connection and Session roles. One especially important difference: by default `JMSContext` **auto-starts when the first consumer is created**, whereas a newly created classic `Connection` remains stopped until `start()` is called explicitly.

To wait until setup finishes before receiving in the simplified API:

~~~java
try (JMSContext context = factory.createContext()) {
    context.setAutoStart(false);
    JMSConsumer consumer = context.createConsumer(destination);
    // Complete setup...
    context.start();
    // ...
    context.stop();
}
~~~

This is a snippet; `factory` and `destination` must exist beforehand, and because `JMSContext` belongs to the simplified API, exception and lifecycle behavior differ (e.g., `IllegalStateRuntimeException`), so do not copy classic `Connection` default-start assumptions directly here.

## 9. Common Errors and How to Diagnose Them

| Symptom | Cause to Check | How to Fix |
| --- | --- | --- |
| Queue has messages yet consumer receives nothing | Forgot `connection.start()` in classic API; connection was stopped | Check lifecycle and call `start()` after creating consumers. |
| Called `stop()` yet broker keeps getting new messages | `stop()` does not block producers | Pause producers separately per policy if sending really must stop. |
| `stop()` takes long to return | Listener is running; `stop()` must wait for callback completion | Inspect processing time, thread dumps, transactions, and timeouts. |
| After `stop()`, `receive(timeout)` returns `null` | Timer still expires while delivery is paused | Distinguish timeout from empty queue; call `start()` when ready to receive. |
| After `close()`, `start()`/`send()`/`receive()` fail | Resource is already closed | Create a new Connection and child objects. |
| App exits yet messages remain on broker | Unacked/uncommitted or broker keeps queue/durable subscription | Inspect transactions, acks, delivery mode, and retention. |
| Stopping one listener stops another listener too | Consumers share the same Connection; `stop` affects the whole connection | Separate ownership/connections or control individually via Spring containers. |
| Callback tries to `stop`/`close` its own Connection | Provider-dependent behavior, possible `IllegalStateException` | Move shutdown operations to an external lifecycle manager outside the listener. |

### Investigation Checklist

1. Determine whether the program uses a **classic Connection**, `JMSContext`, or a **Spring-managed listener**.
2. Identify who creates and owns the Connection, and who is permitted to call `start`/`stop`/`close`.
3. Log application state around lifecycle calls and exceptions; avoid assuming JMS `Connection` exposes a standard `isStarted` method to read directly.
4. Check destination, selectors, message expiration, permissions, transactions, and acknowledgments; do not treat `start`/`stop` as the cure for every "no messages received" issue.
5. During pause/shutdown, track active callbacks, in-flight message counts, redeliveries, and wait times.
6. When testing on a different broker/provider, verify whether assumptions about connection pooling, prefetch, and listener containers hold for that implementation.

## 10. Self-Check Questions

**1. Does a newly created Connection automatically deliver messages to consumers?** No. A classic Connection starts stopped by default; `start()` must be called to enable delivery.

**2. Does `stop()` prevent a producer on the same Connection from sending to a queue?** No. It only controls incoming delivery to the Connection's consumers.

**3. Can `start()` be called after `stop()` on the same Connection?** Yes, as long as the Connection has not been closed.

**4. Can `start()` be called after `close()` on the same Connection?** No; a new Connection must be created.

**5. Does `stop()` return immediately while a listener is running, or after in-flight callbacks finish?** By standard, it must wait for currently running listeners to complete before returning, ensuring message delivery has paused.

**6. Does `close()` automatically commit a transacted Session?** No. Open JMS transactions must roll back when the Connection closes.

**7. Does `close()` automatically acknowledge messages of a `CLIENT_ACKNOWLEDGE` Session?** No. Applications must manage acknowledgments and handle redelivery according to the mode.

**8. When using `@JmsListener` in Spring Boot, should you call `Connection.stop()` directly?** Usually not; control the lifecycle of the Spring-managed listener container.

**9. What is the default start difference between `Connection` and `JMSContext`?** Classic `Connection` requires an explicit `start()`; `JMSContext` auto-starts by default when creating a consumer, unless `setAutoStart(false)` is called.

**10. Why can `stop()` make multiple consumers stop receiving?** Because `stop()` applies to the entire Connection, which may span multiple Sessions and consumers.

### Extended Exercises

- Run the program in Section 5 without the first `connection.start()`. Explain why `receive(5000)` cannot receive `A` even though the producer sent it.
- Switch to two Sessions on the same Connection, each creating a consumer on its own temporary queue; verify `stop()` affects both.
- Register a `MessageListener` with a long task on one Session, call `stop()` from a separate management thread, and measure how long it waits for the callback; do not call `stop()` inside `onMessage()` itself.
- Replace `AUTO_ACKNOWLEDGE` with `SESSION_TRANSACTED`; experiment with `commit`/`rollback` in the Session and observe redelivery independently of `start`/`stop`.

## 11. Authoritative Sources

- [Jakarta Messaging 3.1 Specification, §6.1.4–6.1.8](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): Connection state, `start`, `stop`, `close`, waiting on listeners, and rollback/ack on close.
- [Jakarta Messaging 3.1 API: Connection](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/connection): signatures and contracts of each method.
- [Apache ActiveMQ Artemis: Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): official image, ports, and demo credentials.
- [Spring Framework: JMS reference](https://docs.spring.io/spring-framework/reference/integration/jms.html): `JmsTemplate`, listener containers, and Spring resource management.
