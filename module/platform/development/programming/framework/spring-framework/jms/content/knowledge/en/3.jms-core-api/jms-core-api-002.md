# Connection and Connection Lifecycle in JMS

> **Topic:** Core JMS API in Spring Framework. This lesson explains `ConnectionFactory`, `Connection`, its relationship with `Session`, the `start/stop/close` states, resource management in Jakarta Messaging, and how Spring JMS manages connections on behalf of the application.

## 1. Why Does the Connection Lifecycle Matter?

JMS (Jakarta Messaging) provides a standard API for Java applications to send and receive messages through a **messaging provider/broker**, such as ActiveMQ Artemis. A `Connection` represents a logical connection from the JMS client to the provider. The provider may use one or more network resources, authentication sessions, and internal resources to implement that connection. You should not equate a single `Connection` object with strictly one TCP socket across all providers.

If connections are opened continuously without being released, the application can exhaust resources, incur connection handshake latency, consume threads/sockets, and cause the broker to hit connection limits. If you close or stop a connection currently shared by another listener, message delivery can be disrupted.

Three concerns must be distinguished:
1. **Resource lifecycle:** creating, reusing, and closing `Connection` and its `Session`/producer/consumer objects.
2. **Delivery lifecycle:** `start()` and `stop()` control the ability to *deliver messages to consumers*.
3. **Business lifecycle:** a message being sent/received/acknowledged does not automatically prove that all database operations or external system calls have completed.

Goals after this lesson: understand the JMS API structure, accurately explain `start()`/`stop()`/`close()`, use `try-with-resources` safely, and distinguish manual connection management from `JmsTemplate`/`@JmsListener` in Spring.

## 2. Related Objects

| API | Role | Lifecycle and Responsibilities |
| --- | --- | --- |
| `jakarta.jms.ConnectionFactory` | Configuration/factory object for creating connections to the provider | Usually configured once and reused; supplied by Spring Boot, JNDI, or provider initialization code |
| `jakarta.jms.Connection` | Logical connection to the provider; creates `Session`; controls delivery of messages to consumers | Newly created in the **stopped** state; call `start()` to receive, `stop()` to pause, and `close()` to release |
| `jakarta.jms.Session` | Working context that creates destinations/producers/consumers/messages and manages acknowledgment or local transactions | Belongs to a `Connection`; used sequentially on one thread at a time; closed when no longer needed |
| `jakarta.jms.MessageProducer` | Sends messages to a destination | Created from a `Session`; closed when finished if managed manually |
| `jakarta.jms.MessageConsumer` | Receives synchronously via `receive` or asynchronously via `MessageListener` | Created from a `Session`; requires the connection to be started for messages to be delivered |
| `jakarta.jms.Destination` | Target for sending/receiving, such as a `Queue` or `Topic` | Represents the target name/identifier; whether the destination exists or is auto-created depends on the broker |
| `jakarta.jms.JMSContext` | Simplified API combining Connection and Session (`JMS 2.0+`) | `AutoCloseable`; auto-starts by default when a consumer is created, which can be changed with `setAutoStart(false)` |

**Object relationships (classic API):**

~~~text
ConnectionFactory (provider configuration)
    |
    +-- createConnection() --> Connection
                                  |
                                  +-- createSession() --> Session A
                                  |                       |
                                  |                       +--> MessageProducer
                                  |                       +--> MessageConsumer
                                  |
                                  +-- createSession() --> Session B
                                                          |
                                                          +--> MessageConsumer

Connection.start()/stop() -> controls message delivery to consumers belonging to the connection
Connection.close()        -> releases the connection and child resources
~~~

One connection can serve **multiple sessions**. This is useful when each thread/worker has its own session, while the provider or pooling/caching layer can reuse the underlying physical connection. **Do not share a single Session concurrently across multiple threads**: a Session is designed for sequential access. The same rule applies to `JMSContext` because it encapsulates a session.

In Spring Boot 3.x / Spring Framework 6.x code, import **`jakarta.jms.*`**. Many older JMS / Spring 5 articles use **`javax.jms.*`**; do not mix both namespaces in the same example without verifying dependency compatibility.

## 3. Connection States and State Transitions

The diagram below is an **explanatory model**, not a public JMS state enum:

~~~text
     ConnectionFactory.createConnection()
                    |
                    v
             CREATED / STOPPED
                    |
           start()  |    send() can still work
                    v
                 STARTED <---------------------+
                    |                          |
              stop()|                          | start()
                    v                          |
                 STOPPED ----------------------+
                    |
              close() from any open state
                    v
                 CLOSED
               (terminal)
~~~

### 3.1. `createConnection()` — Creating a Connection

~~~java
Connection connection = connectionFactory.createConnection();
~~~

The JMS provider may authenticate, open a transport link, and allocate resources when creating the connection (details depend on the provider). The connection **starts in the stopped state by default**, allowing the application to create sessions/consumers/listeners before message delivery begins.

Successfully creating a `Connection` does not mean the broker will always stay healthy or that every subsequent send/receive will succeed. Errors can arise in `createConnection`, `send`, `receive`, transactions, or inside listeners.

### 3.2. `start()` — Enabling Message Delivery to Consumers

~~~java
connection.start();
~~~

Once a connection is started, JMS can deliver messages to the `MessageConsumer` instances belonging to that connection. With `receive(timeout)`, this is a prerequisite for receiving messages normally. With `setMessageListener(...)`, callbacks are likewise not invoked while the connection remains stopped.

**Common pitfall:** `start()` is **not a prerequisite for sending**. According to the Jakarta Messaging specification, a producer can still `send()` before a connection is started or after it is stopped. Calling `start()` repeatedly on an already started connection is ignored.

### 3.3. `stop()` — Pausing Message Delivery to Consumers

~~~java
connection.stop();
~~~

`stop()` **pauses delivery to consumers** without closing the connection, destroying sessions, deleting queues, or discarding messages waiting on the broker. A subsequent `start()` call can resume delivery.

Important details:
- Sending messages can still work while stopped.
- Calling `receive(timeout)` can time out and return `null` while the connection is stopped; do not use an unbounded `receive()` just to "test whether stop has taken effect".
- `stop()` must coordinate with any currently running message listener and may **wait for the current callback to finish** before returning; do not treat it as an instantaneous switch.
- Do not call `stop()` from inside a listener currently executing on the same connection: depending on the provider and specification-compliant behavior, this may throw an exception or disrupt execution. Manage lifecycle from an independent management component.

Some brokers perform internal prefetching/buffering. What JMS guarantees here is that **no messages are delivered to consumer code while the connection is stopped**; do not reason about individual network packets.

### 3.4. `close()` — Terminating the Connection

~~~java
connection.close();
~~~

`close()` releases resources owned by the connection and also closes sessions, producers, and consumers belonging to it. It may wait for an in-progress receive or listener execution to complete in an orderly way. After `close()`, that connection **cannot be restarted**; to continue operating, you must create another valid connection (or acquire a new handle from the pool/cache layer).

`close()` is not a "business commit": closing a **session with an uncommitted transaction** rolls back that transaction; closing a connection does not automatically acknowledge unacknowledged messages in a `CLIENT_ACKNOWLEDGE` session. Actual redelivery behavior is affected by the broker, destination type, transaction, and consumer configuration.

**Rule:** for JMS resources created directly by your code, close them in the reverse order of acquisition; Java `try-with-resources` ensures release even when an exception occurs. For connections managed by the **Spring container/pool**, follow the container's contract and do not manually close the underlying "shared connection".

## 4. Runnable Example: Observing Send Before Start, Stop, and Restart

This example uses **Java 17+, Spring Boot 3.3.5, and the Artemis JMS client**. Spring Boot creates `ConnectionFactory` from configuration, while the code below **uses the Jakarta JMS API directly** to make the lifecycle explicit. Run it against an Artemis broker at `tcp://localhost:61616` with user `demo` / password `demo`, a queue named `demo.lifecycle`, and send/receive permissions; if the broker permits auto-creating queues, the client can let it create the destination.

In this educational example, **Spring JMS session caching is disabled** so the API interacts with the provider's connection rather than a resource-sharing proxy; do not treat that setting as a default production recommendation.

**Structure:**

~~~text
jms-connection-lifecycle/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/LifecycleApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-connection-lifecycle'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    cache:
      enabled: false
~~~

`src/main/java/demo/LifecycleApplication.java`:

~~~java
package demo;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleApplication implements ApplicationRunner {

    private final ConnectionFactory connectionFactory;

    public LifecycleApplication(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public static void main(String[] args) {
        SpringApplication.run(LifecycleApplication.class, args);
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        try (Connection connection = connectionFactory.createConnection();
             Session session = connection.createSession(Session.AUTO_ACKNOWLEDGE)) {

            Queue queue = session.createQueue("demo.lifecycle");

            try (MessageProducer producer = session.createProducer(queue);
                 MessageConsumer consumer = session.createConsumer(queue)) {

                connection.setExceptionListener(error ->
                    System.err.println("Asynchronous JMS error: "
                        + error.getMessage()));

                // Connection is still stopped, but the producer is allowed to send.
                producer.send(session.createTextMessage("before-start"));
                System.out.println("sent-before-start");

                connection.start(); // Allow the consumer to receive messages.
                System.out.println("received-1=" + readText(consumer.receive(5000)));

                connection.stop(); // Pause delivery without closing.
                producer.send(session.createTextMessage("while-stopped"));
                System.out.println("sent-while-stopped");

                connection.start(); // Allow delivery again.
                System.out.println("received-2=" + readText(consumer.receive(5000)));
            }
        } // Close consumer, producer, session, and connection in reverse order.
    }

    private static String readText(Message message) throws JMSException {
        if (message instanceof TextMessage text) {
            return text.getText();
        }
        if (message == null) {
            throw new IllegalStateException("Timed out waiting for message");
        }
        throw new IllegalStateException("Expected TextMessage, got "
                + message.getClass().getName());
    }
}
~~~

Run in the project directory with Gradle / JDK 17+:

~~~bash
gradle bootRun
~~~

With an initially **empty** queue, no competing consumers, an available broker, and valid configuration, the program's output lines in order are:

~~~text
sent-before-start
received-1=before-start
sent-while-stopped
received-2=while-stopped
~~~

Spring Boot may print additional log lines during startup and shutdown. The program does not demonstrate timeout behavior while stopped because it **does not call `receive` while stopped**; it only proves the producer can still send, and the consumer receives after `start()`. If the broker is not running, credentials are wrong, the queue does not exist and auto-create is disabled, or the queue already holds old messages, the output will differ or the program will throw an error. Do not turn demo output into an ordering guarantee across multiple consumers.

**Why use `try-with-resources` here?** `Connection`, `Session`, `MessageProducer`, and `MessageConsumer` all extend `AutoCloseable` in Jakarta Messaging. They are closed even if `send`/`receive` throws an exception, preventing resource leaks. This example manages a **dedicated** connection for a short-lived task; creating a new connection per message is not recommended in high-throughput services.

## 5. Simplified API: `JMSContext` and Auto-Start

Jakarta Messaging 2.0+ adds `JMSContext` to combine the common responsibilities of `Connection` and `Session`. It creates producers/consumers directly and uses runtime exceptions. Unlike the classic `Connection` API, `JMSContext` by default **automatically calls start when the first consumer is created**. To finish configuring consumers before receiving, you can disable auto-start:

~~~java
// Additional illustration; place inside a method with a valid connectionFactory.
try (var context = connectionFactory.createContext()) {
    context.setAutoStart(false);
    var queue = context.createQueue("demo.lifecycle");
    try (var consumer = context.createConsumer(queue)) {
        context.createProducer().send(queue, "hello-context");
        context.start();
        String body = consumer.receiveBody(String.class, 5000);
        System.out.println(body);
    }
}
~~~

This is a **snippet** using the same configured `ConnectionFactory`; it is not a standalone Java file. Ensure the queue is empty / has matching content if you expect to receive `hello-context`.

`JMSContext.close()` closes the context's session and child resources; the underlying connection is only closed when no other active context is sharing it. `JMSContext` **must not be shared concurrently across threads** as if it were automatically thread-safe. If parallel processing is needed, allocate a separate valid context/session per worker thread.

## 6. How Does Spring JMS Manage Connections Differently from Plain JMS?

A Spring application normally **does not need** to call `createConnection()`, `start()`, and `close()` for each operation. Spring provides abstractions with clear resource ownership:

### 6.1. `JmsTemplate` — Operation-Scoped Send/Receive

~~~java
// Spring integration snippet: inject the Boot-configured JmsTemplate.
@Service
public class NotificationPublisher {
    private final JmsTemplate jmsTemplate;

    public NotificationPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String body) {
        jmsTemplate.convertAndSend("notifications.queue", body);
    }
}
~~~

In the snippet above, you need to import `org.springframework.stereotype.Service` and `org.springframework.jms.core.JmsTemplate`. `JmsTemplate` manages acquiring/returning the JMS resources needed for the call and translates JMS exceptions into appropriate Spring exceptions. Depending on the `ConnectionFactory`, "returning/closing a handle" may release an actual resource or **return it to a cache/pool**. Do not create a manual connection just to send one message and leave it unmanaged.

### 6.2. `@JmsListener` — Container Owns the Consumer Lifecycle

~~~java
// Spring snippet; enable @EnableJms on an appropriate @Configuration.
@Component
public class NotificationConsumer {
    @JmsListener(id = "notifications", destination = "notifications.queue")
    public void onMessage(String body) {
        System.out.println("Processed: " + body);
    }
}
~~~

The snippet above requires importing `org.springframework.stereotype.Component` and `org.springframework.jms.annotation.JmsListener`. With `@EnableJms` and an appropriate listener factory, Spring creates a listener container for the method. The container is responsible for initializing the consumer, starting/stopping message intake, assigning sessions/workers, and cleaning up resources on application shutdown. Do not call `Connection.stop()` directly from a listener method just to "pause a queue".

When runtime control over a listener is needed, use `JmsListenerEndpointRegistry` and `MessageListenerContainer` by the configured ID:

~~~java
// Administrative snippet, not a standalone file.
MessageListenerContainer container =
        registry.getListenerContainer("notifications");
if (container != null) {
    container.stop();  // Stop this listener via Spring's lifecycle.
    // When recovery conditions are met: container.start();
}
~~~

Import `org.springframework.jms.listener.MessageListenerContainer` and inject `org.springframework.jms.config.JmsListenerEndpointRegistry`. Define administrative authorization and in-flight work handling procedures before allowing runtime operations to stop a listener.

### 6.3. `SingleConnectionFactory`, `CachingConnectionFactory`, and Pooling

| Layer | Purpose | Key Points to Remember |
| --- | --- | --- |
| Native `ConnectionFactory` | Provider directly creates/closes connections | Creating too many connections is usually expensive; errors and reconnect depend on the provider |
| Spring `SingleConnectionFactory` | Shares a single underlying connection; handles may ignore physical `close()` | Useful for testing/standalone apps; **do not treat every `createConnection` as a new physical connection** |
| Spring `CachingConnectionFactory` | Extends `SingleConnectionFactory` and additionally caches sessions/producers/consumers | `sessionCacheSize` controls how many sessions per type are retained; close logical Sessions to return them to the cache |
| Native/JMS connection pool (e.g., pooled-jms) | Manages multiple connections/sessions within configured limits | Carefully review configuration, borrow/return rules, idle/eviction settings, and transactions |

Spring Boot 3.x typically configures a `CachingConnectionFactory` wrapping the provider factory and exposes tuning via `spring.jms.cache.*`. For example, `spring.jms.cache.session-cache-size: 5` can suit concurrent operations, but **is not an optimal formula for every system**. Caching and pooling solve different problems; do not stack multiple layers merely to "boost performance".

Spring also distinguishes **connections used by producers/templates** from **listener containers**. With `DefaultMessageListenerContainer`, acquiring, retaining, and refreshing connections/sessions/consumers depends on `cacheLevel`, the transaction manager, concurrency, and recovery mechanisms. In environments with an external transaction manager, the appropriate cache level may differ from standalone JMS; verify against your actual configuration and broker.

**Ownership rule:** if you only inject `JmsTemplate` or use `@JmsListener`, let Spring manage the lifecycle. When you deliberately call plain Jakarta JMS APIs on a provider factory, you are responsible for closing the resources your code opens. Do not call `resetConnection()` or `destroy()` on a shared bean as a quick fix for transient errors without accounting for all affected consumers.

## 7. How Do Connection, Session, and Transactions Differ?

`Connection.start()` only enables message delivery to consumers. It **does not** start a database transaction and **does not** replace session acknowledgment/commit. Consider:

~~~java
try (Connection connection = connectionFactory.createConnection();
     Session session = connection.createSession(Session.SESSION_TRANSACTED)) {

    Queue queue = session.createQueue("orders.queue");
    try (MessageProducer producer = session.createProducer(queue)) {
        producer.send(session.createTextMessage("order-created"));
        session.commit(); // Commit the local JMS transaction.
    }
}
~~~

This snippet illustrates a **JMS local transaction**. If `commit()` does not run or a transaction remains open when `Session.close()` occurs, the uncommitted JMS transaction is rolled back. Committing JMS does not automatically commit a separate database transaction. If you must ensure "write order to DB + publish event" consistency, consider the transactional outbox pattern or a dedicated coordinated transaction setup suited to your infrastructure.

For a consumer in `AUTO_ACKNOWLEDGE`, acknowledgment is applied by the JMS runtime according to the receive style and corresponding callback. In `CLIENT_ACKNOWLEDGE`, the application must acknowledge explicitly; **closing the Connection does not turn unacknowledged messages into acknowledged ones**. A closed session cannot be used to continue receiving, committing, rolling back, or acknowledging.

Standard production principles are: handle duplicates safely with an idempotency key, manage redelivery/DLQ, and design transactions explicitly. **Do not use whether a connection was started or closed to infer that a message was processed exactly once.**

## 8. Handling Disconnections and Recovery

A connection can become invalid due to broker restart/failover, network errors, authentication expiration, quotas, timeouts, DNS issues, or misconfigured TLS. Symptoms include exceptions during session creation/send/receive, consumers stopping intake, the broker reporting client disconnects, or rising queue backlog.

With plain JMS:
- `setExceptionListener(...)` lets you receive certain asynchronous connection-level errors. It **does not replace** handling `JMSException` on `createConnection`/`send`/`receive`/`commit` calls and does not guarantee callbacks for every failure.
- After an error, determine whether the connection is still valid according to the provider; clean up broken resources and recreate them using a controlled recovery strategy.
- Avoid infinite retries and tight reconnect loops: apply backoff, attempt limits, jitter, and alerting when recovery is exhausted.
- Check the reconnect/failover policies of Artemis or your actual provider; the JMS spec does not mandate one universal reconnect algorithm across all brokers.

With Spring:
- `DefaultMessageListenerContainer` provides recovery mechanisms for listener setup and connection failures, governed by `recoveryInterval`/`BackOff` and resource cache configuration.
- `CachingConnectionFactory` has options for handling errors/reconnecting the underlying connection, but does not guarantee automatic recovery of **all** business state, session transactions, subscriptions, or in-flight messages.
- When the application shuts down, the container shuts down listeners following the framework lifecycle. Set a shutdown wait timeout suited to task duration; if killed abruptly, uncommitted/unacknowledged messages may be redelivered.

**Do not treat the mere presence of a `Connection` object on the heap as "connected" status.** To know whether the system is healthy, combine broker checks and observable end-to-end send/receive health rather than checking only that a bean exists.

## 9. Common Project Mistakes

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| Producer sends successfully but consumer never receives | Connection not `start()`ed; wrong queue; consumer/selector mismatch | Check destination, connection state, selector, and queue depth |
| `receive()` hangs | Calling receive without timeout while connection is stopped or queue is empty | Use `receive(timeout)`, check `start()`, and isolate receiving threads properly |
| Broker has too many connections | Creating a new connection per message without closing or pooling | Reuse `ConnectionFactory` and `JmsTemplate`/pool; close manual resources |
| Hard-to-reproduce errors under multithreading | Sharing one `Session`/`JMSContext` concurrently | Create a dedicated session/context per worker thread |
| `close()` stops other listeners from receiving | Closing the framework/pool's shared connection | Never manually close the physical connection managed by Spring |
| Listener fails to recover after broker restart | Misconfigured caching/recovery/failover | Check listener container settings, backoff, broker HA, and logs |
| Messages reappear after restart | Uncommitted transaction or unacknowledged message | Ensure proper commit/ack and idempotent consumers |
| Listener stopped yet a task still finishes | A callback had already started before stop and was allowed to complete | Distinguish "stop taking new messages" from "cancel in-flight tasks" |

These issues should be evaluated alongside the current broker and transaction configuration rather than "fixed" by arbitrarily increasing `sessionCacheSize` or thread counts.

## 10. Configuration and Operations Checklist

When configuring JMS in Spring, verify:
- **Ownership:** is the connection owned by application code, the Spring container, an application server, or a pool?
- **Start/stop:** which listeners auto-start; which consumers should be paused during maintenance; do in-flight tasks need to drain?
- **Concurrency:** maximum number of consumers and sessions; one session is never shared across workers; fits within broker/database limits.
- **Resources:** physical connection count, session cache, idle timeout, and shutdown closing behavior.
- **Availability:** broker endpoints, TLS/auth, failover/reconnect, backoff, quotas, and alerts when connections cannot be established.
- **Reliability:** transaction/acknowledgment mode, retries, DLQ, duplicate handling, idempotency, and message retention.
- **Observability:** connection count, active consumers, send/receive errors, recovery time, queue depth/age, redelivered message count, and DLQ size.

### Self-Check Questions

1. Why is creating a `Connection` not enough for `MessageConsumer.receive(...)` to return messages?
2. If a connection has been `stop()`ped, can a producer still `send()`? Does `stop()` delete messages sitting on the broker?
3. After `Connection.close()`, can you call `start()` on that same object to keep using it?
4. Why is passing one `Session` to multiple threads simultaneously a bug, even when those threads share one `Connection`?
5. How do `JmsTemplate` and `@JmsListener` change the developer's responsibility for managing `Connection`?
6. Why are `Session.commit()` or `Connection.close()` not equivalent to "all business work in the database is committed"?

**Remember:** `ConnectionFactory` provides connections; `Connection.start()/stop()` controls **message delivery to consumers**; `Connection.close()` terminates resources; `Session` controls JMS acknowledgment/transactions; and in Spring, templates and listener containers usually take over lifecycle responsibility from application code.

## References

- Jakarta Messaging 3.1 Specification (sections Connections, Sessions, JMSContext): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 API – Connection: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/connection
- Spring Framework – Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework – Annotation-driven JMS Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Boot – JMS & ActiveMQ Artemis: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
