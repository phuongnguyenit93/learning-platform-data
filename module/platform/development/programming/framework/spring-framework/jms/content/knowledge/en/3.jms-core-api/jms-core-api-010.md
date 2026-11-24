# Resource Management with Native API vs. JmsTemplate

## Objectives and Context

This lesson places the **native Jakarta Messaging (JMS) API** side by side with **Spring `JmsTemplate`**, focusing on one practical question: when sending or receiving a message, **who creates, owns, closes, and releases `Connection`, `Session`, `MessageProducer`, and `MessageConsumer`?** From there, you can choose the right coding style, avoid resource leaks, distinguish cleanup from commit, and accurately understand the role of transactions and caching in Spring applications.

In modern Spring Framework, the JMS API uses the `jakarta.jms` package. Legacy projects may use `javax.jms`; the two namespaces are not directly interchangeable without selecting compatible dependency versions.

## 1. Resources That Must Be Managed

In the classic JMS API, the common usage graph is:

```text
ConnectionFactory (configuration managed by application/container)
        |
        +-- createConnection() --> Connection (channel to broker)
                                       |
                                       +-- createSession(...) --> Session
                                                                    |
                                                                    +-- MessageProducer
                                                                    +-- MessageConsumer
                                                                    +-- Queue / Topic*
                                                                    +-- TextMessage / BytesMessage*
```

The `*` marks objects created to represent a destination or message payload; they do not share the same resource lifecycle as a connection, session, producer, or consumer.

| Object | Role | Key Management Notes |
| --- | --- | --- |
| `ConnectionFactory` | Configures and creates connections to the JMS provider | Typically configured/injected once. Do not create a new factory for every message. |
| `Connection` | Represents a connection to the provider; can host multiple sessions | Close when out of scope; `close()` also releases associated sessions and producers/consumers. |
| `Session` | Single-threaded context for creating messages, producers/consumers, and controlling acks/transactions | Never use concurrently from multiple threads; can be closed individually or via its connection. |
| `MessageProducer` | Sends messages to a destination | Close after use if managed manually; Jakarta Messaging 3.1 allows `try-with-resources`. |
| `MessageConsumer` | Receives messages synchronously or via a listener | Close when no longer receiving; `receive()` itself can block for long periods. |
| `JMSContext` | Simplified JMS API: combines connection + session | `AutoCloseable`; `try-with-resources` fits when created by application code. |
| `JmsTemplate` | Spring class that executes JMS operations and manages underlying resources | A shared bean once configured; call `send`/`receive`/`execute` rather than creating/closing sessions yourself. |

**Important:** `ConnectionFactory` is the shared starting point, yet **the native API and `JmsTemplate` have different ownership rules**. Inside a Spring callback, the session is lent to you by the framework; in code calling `createConnection()` directly, the application owns the resources it created. Never manually close a session passed into a `JmsTemplate` callback.

### Cleanup Is Not Commit

- `close()` releases resources; it **does not** turn business processing into a successful transaction.
- With a **transacted session**, the application must call `commit()` to confirm the local JMS transaction. When a transacted session is closed with an open transaction, that transaction rolls back.
- With **client-acknowledge**, closing a connection/session **does not** acknowledge unacknowledged messages.
- If a receiving session fails before commit/acknowledge, the broker can redeliver the message per policy. Releasing resources cleanly does not imply "exactly once" at the business level.

## 2. Classic JMS API: Creating and Closing Resources Yourself

A single send using the native API involves multiple steps: create connection, create session, obtain Queue, create producer, create message, send, and then release in reverse order.

The Java 17+ example below is a **compilable method inside an application that already has the Jakarta JMS dependency**, not a standalone program because `ConnectionFactory` must be supplied by a provider.

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

public final class ClassicJmsSender {

    public static void send(ConnectionFactory factory,
                            String queueName,
                            String body) throws JMSException {
        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             MessageProducer producer =
                     session.createProducer(session.createQueue(queueName))) {

            producer.send(session.createTextMessage(body));
        }
    }
}
```

`try-with-resources` closes `producer`, then `session`, and finally `connection`, **even if `send()` throws an exception**. `Connection`, `Session`, `MessageProducer`, and `MessageConsumer` are all `AutoCloseable` in Jakarta Messaging 3.1. No extra manual `finally` block is needed to close those same objects. If exceptions occur in both the body and during closing, Java retains the primary exception and attaches the close error as a `suppressed exception`.

When writing `finally` manually in older projects, common bugs included closing only on success, forgetting to close the producer, or letting a `close()` error mask a send error. `try-with-resources` eliminates most of those scope-management bugs.

### Why Not Call `connection.start()` When Only Sending?

`Connection.start()` begins **delivery to consumers**. Sending messages via a producer does not require calling `start()` first. For **synchronous receiving** with the classic API, `connection.start()` is required for delivery to occur.

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class ClassicJmsReceiver {

    public static String receive(ConnectionFactory factory,
                                 String queueName,
                                 long timeoutMillis) throws JMSException {
        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             MessageConsumer consumer =
                     session.createConsumer(session.createQueue(queueName))) {

            connection.start();
            Message message = consumer.receive(timeoutMillis);

            if (message == null) {
                return null; // Wait timed out, no message.
            }
            if (!(message instanceof TextMessage text)) {
                throw new IllegalArgumentException(
                        "Expected TextMessage, got " + message.getClass());
            }
            return text.getText();
        }
    }
}
```

`receive(2000)` waits at most roughly 2 seconds and returns `null` if no message arrives; `receive(0)` can wait indefinitely. On a Queue with other consumers, another consumer may take the message first. When using `AUTO_ACKNOWLEDGE`, do not assume a later database call governs the acknowledgment of this `receive`; design explicit transactions/acknowledgments when reliable processing is required.

### What Is the Cost of Manual Management?

Even a simple method must declare `JMSException`, interact with `Session`, and decide `start`, `close`, timeouts, and transactions itself. This is useful when low-level control is required, yet easily duplicates code and misses steps across multiple send/receive sites.

## 3. Simplified Native API: `JMSContext` Reduces Boilerplate

Jakarta Messaging also provides the **simplified API** (not Spring): `JMSContext` combines connection and session roles, and `JMSProducer` provides concise send operations.

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

public final class SimplifiedJmsSender {

    public static void send(ConnectionFactory factory,
                            String queueName,
                            String body) {
        try (JMSContext context =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue queue = context.createQueue(queueName);
            context.createProducer().send(queue, body);
        }
    }
}
```

Differences to remember:

- A `JMSContext` created by **calling `createContext()` directly** still must be closed; `try-with-resources` handles that.
- The simplified API primarily uses `JMSRuntimeException` (unchecked), rather than forcing every caller to declare checked `JMSException` as in the classic API.
- `JMSContext` represents a session, so it is **not safe to share and invoke concurrently across multiple threads**. Never store a manually created `JMSContext` as a singleton shared across requests.
- When creating a `JMSConsumer` from a `JMSContext`, delivery can start automatically (`autoStart`) by default—unlike the classic API, which requires `Connection.start()` for receiving.
- When `JMSContext` is managed/injected by a Jakarta EE container, its lifecycle follows container rules. Do not blindly apply manual `close()` to container-owned instances.

**Distinction:** `JMSContext` reduces API verbosity, yet **remains the native JMS API**; it does not automatically provide Spring transaction synchronization, `MessageConverter`, or `JmsTemplate` exception translation.

## 4. Spring `JmsTemplate`: Delegate Operations to the Template, Cleanup to the Framework

Spring Framework uses `org.springframework.jms.core.JmsTemplate` for **synchronous** sending and receiving. Configure the template with a `ConnectionFactory`; most business code never sees `Connection` or `Session`.

```java
import org.springframework.jms.core.JmsTemplate;

public final class TemplateSender {
    private final JmsTemplate jmsTemplate;

    public TemplateSender(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void send(String orderId) {
        jmsTemplate.convertAndSend("orders.queue", orderId);
    }
}
```

Conceptually, a `convertAndSend` call follows this chain:

```text
Business service
    -> JmsTemplate.convertAndSend(...)
        -> look up Session participating in current transaction (if any)
           or acquire/create an appropriate Connection + Session
        -> convert String to JMS TextMessage
        -> acquire/create producer and send
        -> close or return resources per Spring/ConnectionFactory policy
    <- result / unchecked Spring JmsException
```

**The template manages logical lifecycle; that does not mean every call opens a new TCP connection.** If the underlying `ConnectionFactory` is pooled or cached, logical `close` calls can return the session to the cache. Do not infer the number of `send` calls from physical connection creations.

`JmsTemplate` also handles:

1. **Message conversion:** `convertAndSend` and `receiveAndConvert` use a `MessageConverter`; by default, a `String` can be converted to a `TextMessage`.
2. **Destination resolution:** accepts Queue/Topic string names via `DestinationResolver`; you do not always have to call `session.createQueue` manually.
3. **Exception translation:** converts checked `jakarta.jms.JMSException` from operations into unchecked `org.springframework.jms.JmsException`; applications can handle errors at service boundaries instead of propagating `throws JMSException` everywhere.
4. **Transaction integration:** when paired with `JmsTransactionManager` on the **same `ConnectionFactory`**, the template can reuse the transaction-bound session.
5. **Custom callbacks:** when lower-level control than `convertAndSend` is needed, the template passes a `Session` or producer into a callback while retaining ownership of the outer resources.

`JmsTemplate` is **thread-safe once configured**. Inject a shared bean and configure `receiveTimeout`, converters, and Quality-of-Service before concurrent use; avoid mutating bean settings continuously across requests.

### With `MessageCreator` and Callbacks, Who Closes What?

When you want to construct a `TextMessage` and specific JMS properties:

```java
jmsTemplate.send("orders.queue", session -> {
    var message = session.createTextMessage("order-42");
    message.setStringProperty("source", "checkout");
    return message;
});
```

Here `session` is supplied by `JmsTemplate`. **Never** call `session.close()` inside the callback; the template still needs the session to send the message and clean up properly afterward.

For more advanced operations, `SessionCallback` provides access to the session:

```java
import jakarta.jms.MessageProducer;
import org.springframework.jms.core.SessionCallback;

jmsTemplate.execute((SessionCallback<Void>) session -> {
    try (MessageProducer producer =
                 session.createProducer(session.createQueue("audit.queue"))) {
        producer.send(session.createTextMessage("event-1"));
        producer.send(session.createTextMessage("event-2"));
    }
    return null;
});
```

In this example, **the producer was created by the callback**, so the callback closes it via `try-with-resources`. **The session was passed in by Spring**, so the callback does not close it. With `ProducerCallback`, Spring can supply a template-managed session/producer pair, avoiding manual producer creation altogether.

Two `send` calls inside the same callback share one session, yet **do not assume atomicity automatically**: to commit or roll back both sends together, enable transacted sessions or use a transaction manager properly.

### Synchronous Receiving with `JmsTemplate`

```java
// Configure during bean initialization, before concurrent use:
jmsTemplate.setReceiveTimeout(2_000L);

// Inside service:
Object payload = jmsTemplate.receiveAndConvert("orders.queue");
if (payload == null) {
    // No message received within the wait timeout.
}
```

`receiveAndConvert` is convenient for short request/reply exchanges or bounded polling. For continuous listening, use `@JmsListener` and a Spring listener container; do not write an unbounded `while(true)` loop calling `JmsTemplate.receive()` on a request thread. The template does not turn synchronous receive into an asynchronous listener.

## 5. Complete Spring Boot Example: Comparing Three Ways to Send

This example uses **Java 17+**, **Spring Boot 3.5.8**, the `jakarta.jms` API, and a **separate Apache ActiveMQ Artemis broker**. It sends three messages to the same Queue via (1) classic JMS, (2) simplified `JMSContext`, and (3) Spring `JmsTemplate`. All three share the `ConnectionFactory` supplied by Spring Boot.

**Run prerequisites:** an Artemis broker listening on `tcp://localhost:61616`, valid credentials, and Queue `demo.resources.queue` pre-created or broker auto-create enabled. Without a broker, the example throws a connection error; Maven does not start an external broker automatically.

**`pom.xml`**

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
    <artifactId>jms-resource-demo</artifactId>
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

**`src/main/resources/application.properties`**

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
# Enable if the broker requires authentication:
# spring.artemis.user=my-user
# spring.artemis.password=my-password
```

**`src/main/java/example/jms/ResourceManagementDemo.java`**

```java
package example.jms;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class ResourceManagementDemo {

    private static final String QUEUE = "demo.resources.queue";

    public static void main(String[] args) {
        SpringApplication.run(ResourceManagementDemo.class, args);
    }

    @Bean
    ApplicationRunner runExample(ConnectionFactory factory,
                                 JmsTemplate template) {
        return args -> {
            classicSend(factory, QUEUE, "from-classic");
            simplifiedSend(factory, QUEUE, "from-context");
            template.convertAndSend(QUEUE, "from-template");
            System.out.println("sent=3");
        };
    }

    static void classicSend(ConnectionFactory factory,
                            String destination,
                            String body) throws JMSException {
        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             MessageProducer producer =
                     session.createProducer(session.createQueue(destination))) {

            producer.send(session.createTextMessage(body));
        }
    }

    static void simplifiedSend(ConnectionFactory factory,
                               String destination,
                               String body) {
        try (JMSContext context =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

            context.createProducer().send(context.createQueue(destination), body);
        }
    }
}
```

**Run** in the directory containing `pom.xml` once the broker is ready:

```bash
mvn spring-boot:run
```

Stdout line printed by the program when **all three send calls finish without throwing an error**:

```text
sent=3
```

Spring Boot also prints startup logs depending on the environment. `sent=3` reports the count of send operations completed without throwing in this example; **it does not prove the broker persisted messages per desired policy or that a consumer processed each exactly once**. Each rerun sends three more messages. If another consumer reads the Queue, messages may be consumed immediately and no longer appear in the pending Queue.

Observing the code:

- `classicSend` shows the app opening and closing `Connection`, `Session`, and `MessageProducer`.
- `simplifiedSend` manages only one `JMSContext` and uses the unchecked API.
- `template.convertAndSend` specifies only the destination and payload; Spring handles the JMS lifecycle and message conversion.
- **There is no `Connection.start()`** because the example only sends; if adding receiving via a classic `MessageConsumer`, call `start()` before `receive()`.

## 6. Transactions: Understand Boundaries Before Choosing an API

### 6.1 Classic JMS with Local Transactions

When multiple messages must belong to one **JMS transaction** on the provider, use a transacted session and manage `commit/rollback` manually:

```java
static void sendTwoAtomicallyWithinJms(
        ConnectionFactory factory, String queueName) throws JMSException {

    try (Connection connection = factory.createConnection();
         Session session = connection.createSession(Session.SESSION_TRANSACTED);
         MessageProducer producer =
                 session.createProducer(session.createQueue(queueName))) {

        try {
            producer.send(session.createTextMessage("first"));
            producer.send(session.createTextMessage("second"));
            session.commit(); // Same local JMS transaction.
        } catch (JMSException | RuntimeException ex) {
            try {
                session.rollback();
            } catch (JMSException rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
            throw ex;
        }
    }
}
```

This is an **additional illustrative method**: place it in a class with the imports from the previous example to compile. `SESSION_TRANSACTED` provides transactional semantics; `AUTO_ACKNOWLEDGE` does not substitute for it. Closing a transacted session with an uncommitted transaction rolls back per the spec. If the broker disconnects right during `commit`, the outcome can be ambiguous from the client's view; the system still needs duplicate-prevention design.

With the simplified API, the same idea uses `factory.createContext(JMSContext.SESSION_TRANSACTED)` followed by `context.commit()` or `context.rollback()`; errors are primarily unchecked `JMSRuntimeException`.

### 6.2 `JmsTemplate` Does Not Automatically Group All Calls into One Transaction

If you configure `jmsTemplate.setSessionTransacted(true)` **without** an enclosing Spring transaction, each template call typically gets its own session/transaction. Two consecutive `convertAndSend` calls do not automatically form one atomic unit.

When multiple template calls must share one JMS transaction, configure `JmsTransactionManager` for **the same `ConnectionFactory`** and establish a Spring transaction boundary:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.connection.JmsTransactionManager;

@Configuration
class JmsTxConfiguration {
    @Bean
    JmsTransactionManager jmsTransactionManager(ConnectionFactory factory) {
        return new JmsTransactionManager(factory);
    }
}
```

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TwoMessagePublisher {
    private final JmsTemplate template;

    TwoMessagePublisher(JmsTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void publish() {
        template.convertAndSend("orders.queue", "order-created");
        template.convertAndSend("audit.queue", "audit-created");
    }
}
```

**These two snippets are configuration/components to wire into an existing Spring application**, not two standalone Java files with `main()`. The `publish()` method must be invoked **through a Spring proxy** (usually from another bean) so `@Transactional` advice executes under the standard proxy model; internal self-invocation does not start a new transaction. Whether two Queues commit together in JMS depends on the broker and transaction support for those destinations.

Scope warning: `JmsTransactionManager` manages **JMS resources**; it does not automatically merge SQL updates handled by `DataSourceTransactionManager` into one atomic transaction. If a message sends successfully while the database rolls back, or vice versa, data inconsistency can occur. Options such as **transactional outbox**, idempotent consumers, or XA/JTA must be evaluated based on requirements rather than inferred from `@Transactional`.

### 6.3 Never Create Raw `Connection`/`Session` Inside a Spring Transaction Expecting Auto-Participation

Inside a method annotated with `@Transactional(transactionManager = "jmsTransactionManager")`, `JmsTemplate` is designed to look up the session bound to the current transaction. By contrast, calling `connectionFactory.createConnection()` / `createSession()` directly on an ordinary factory normally creates an independent resource. Never assume raw JMS calls automatically join the active transaction.

If classic JMS must be used inside a Spring-managed transaction, understand `ConnectionFactoryUtils` and `TransactionAwareConnectionFactoryProxy`, or route operations through template callbacks; never swap factories arbitrarily or close a transaction-bound session. Recommendation in most Spring services: use `JmsTemplate` consistently in the publisher layer so transaction ownership stays predictable.

## 7. Caching, Pooling, and Practical Lifetime

A common misconception: seeing that `JmsTemplate` has no `close()` and concluding the app keeps connections open forever, or conversely believing every `send` opens and closes a physical socket. Neither is guaranteed.

`JmsTemplate` depends on `ConnectionFactory`:

- With a factory creating a new connection every time, the template may open and close a connection per operation.
- With `CachingConnectionFactory` or an appropriate pool, some returned objects are wrappers; logical `close()` may **return the session/connection to the cache** rather than closing the physical link immediately.
- During an active transaction, Spring can reuse the session bound to the thread/transaction across multiple operations.
- Optimal cache/pool levels depend on the broker, concurrent request volume, producers/consumers, transactions, prefetch, and provider connection/session limits.

Caching producers or consumers depends on configuration and the JMS provider. Never cache a first-send `Session` in a field of a Spring singleton service to "optimize", because a session has threading/lifecycle constraints and easily breaks under concurrency, timeouts, or reconnects.

**Lifecycle choice example:** An HTTP service handling hundreds of requests/second should inject **a single configured `JmsTemplate`** backed by a factory with suitable caching/pooling. That is very different from holding **one mutable `JMSContext`** across all requests: `JMSContext` wraps a session that does not support arbitrary concurrent use.

## 8. Proper Error Handling and Cleanup

| Scenario | Classic API | Simplified JMS API | `JmsTemplate` |
| --- | --- | --- | --- |
| Connection creation error | Typically `JMSException` (checked) | Typically `JMSRuntimeException` (unchecked) | Spring `JmsException` hierarchy (unchecked) |
| Sending a message | Create `Message` and producer yourself; handle errors | Concise `JMSProducer.send` | `send`/`convertAndSend`; template coordinates |
| Cleanup on success | `try-with-resources` or `finally` | `JMSContext` in `try-with-resources` | Template manages resources it owns |
| Cleanup after exception | Ensure release across every branch | `try-with-resources` auto-closes | Template cleans up and throws translated exception |
| Custom session/producer | Direct control | Via `JMSContext` | `MessageCreator`, `SessionCallback`, `ProducerCallback` |
| Multi-operation transaction | `SESSION_TRANSACTED` + `commit/rollback` | `JMSContext.SESSION_TRANSACTED` + `commit/rollback` | Use `JmsTransactionManager` / `@Transactional` boundaries as needed |
| Long-lived receiver | Manage consumer/threads/lifecycle yourself | Manage context/consumer yourself | Use `@JmsListener` + listener container for async |

Risks to address **regardless of which API you choose**:

1. **Mid-flight connection failures:** ensure errors are logged with sufficient context (destination, correlation/business ID) and paired with a sound retry policy. Clean resource release does not replace a reconnect strategy.
2. **Uncertain send outcomes on disconnect:** you may not know whether the broker received the message. Blind retries can produce duplicate business messages; use stable IDs and downstream idempotency where needed.
3. **Receive succeeds then DB processing fails:** JMS acknowledgment/transactions must be designed deliberately. `receiveAndConvert` does not hold the message open while another service processes asynchronously.
4. **Swallowing exceptions:** in a transacted listener, catching an error and returning normally can commit the JMS transaction, preventing desired redelivery.
5. **Closing the wrong resource:** callbacks must never `close()` a Spring-supplied session; manual code must never leak sessions/producers it created.
6. **Leaks in long-running receivers:** never open a new consumer inside every loop iteration without closing; prefer listener containers for continuous receiving workloads.
7. **Connection/session exhaustion:** inspect pool sizes, active sessions, idle timeouts, broker logs, and concurrent request rates rather than blindly raising connection limits.

### Broken Pattern and Fix

Resource-leaking pattern:

```java
Connection c = factory.createConnection();
Session s = c.createSession(Session.AUTO_ACKNOWLEDGE);
MessageProducer p = s.createProducer(s.createQueue("orders.queue"));
p.send(s.createTextMessage("order-42"));
// If send throws an exception, nothing guarantees closing p/s/c.
```

Fix with classic API:

```java
try (Connection c = factory.createConnection();
     Session s = c.createSession(Session.AUTO_ACKNOWLEDGE);
     MessageProducer p = s.createProducer(s.createQueue("orders.queue"))) {
    p.send(s.createTextMessage("order-42"));
}
```

In Spring, for the equivalent operation:

```java
jmsTemplate.convertAndSend("orders.queue", "order-42");
```

These three snippets are **illustrative call-site fragments assuming `factory`/`jmsTemplate` already exist**, not standalone Java files. What is omitted in the short Spring snippet (creating/closing the session) is precisely what the template takes care of.

## 9. Which API Should You Choose for Each Scenario?

| Requirement | Recommendation | Reason |
| --- | --- | --- |
| Spring service sending String, byte array, or converter-backed objects | `JmsTemplate.convertAndSend` | Concise business code; consistent lifecycle and message conversion handling. |
| Spring service needing JMS headers/properties | `JmsTemplate.send(MessageCreator)` or `convertAndSend(..., MessagePostProcessor)` | Retains Spring cleanup while customizing the message where needed. |
| Spring service needing direct `Session` / producer control for a special operation | `JmsTemplate.execute` with callback | Accesses the JMS API without losing Spring-managed transactions/lifecycle. |
| Java SE without Spring | Self-created `JMSContext` in `try-with-resources` | Concise standard API with scoped automatic resource closing. |
| Legacy/integration needing low-level API or special protocol/provider features | Classic `Connection/Session/Producer/Consumer` | Full control, in exchange for manual cleanup, threading, and transaction responsibility. |
| Long-lived async receiving in Spring | `@JmsListener` + listener container | Manages consumers, lifecycle, concurrency, and transactions for listeners. |
| Multiple JMS sends sharing commit/rollback in Spring | `JmsTransactionManager` + `@Transactional` + `JmsTemplate` | Synchronizes session and transaction boundaries cleanly. |

Never pick the classic API merely to "be faster": all APIs call into the same underlying JMS provider; real throughput depends mostly on the broker, connection/session settings, payload size, batching, persistent delivery, network, and workload. Benchmark under load before optimizing.

## 10. Checklist and Self-Check Exercises

**Before going to production:**

- Identify clearly who creates and closes `Connection`/`Session`/`JMSContext`; separate application-created resources from framework-managed ones.
- Use `try-with-resources` wherever native JMS resources are owned directly; never share `Session` or `JMSContext` unsafely across threads.
- Use a `JmsTemplate` configured before concurrent execution; set a finite `receiveTimeout` for time-bounded synchronous receives.
- Define transaction type, commit conditions, and failure handling between JMS sends and database writes.
- Set up metrics/logs for connections, producers/consumers, retry failures, transaction rollbacks, Queue backlog, and processing latency; never log broker passwords.
- Test broker restarts, consumer rollbacks, DB-commit-with-JMS-commit-failure scenarios, and concurrent threads hitting the same service.

**Ask yourself:**

1. Why is `Connection.start()` called in the classic receiver snippet, yet absent in the classic sender?
2. Inside `JmsTemplate.execute(SessionCallback)`, who closes the session? If the callback creates a producer, who closes the producer?
3. Why might two consecutive `convertAndSend` calls not share the same JMS transaction?
4. Why does returning a session to `CachingConnectionFactory` not equate to closing a physical socket?
5. Why do `try-with-resources` and `@Transactional` solve **two** different problems?

**Short answers:** (1) `start()` enables delivery to consumers; sending does not need it. (2) The template owns the session; the callback owns any producer it creates itself. (3) A shared transaction boundary and matching transaction manager are needed; `sessionTransacted` on individual operations is insufficient. (4) Caching retains resources for reuse. (5) `try-with-resources` guarantees scoped resource closing; transactions govern committing/rolling back JMS work.

## Conclusion

The decisive difference is **ownership and lifecycle**. Classic JMS grants direct control while requiring the application to close resources and handle checked exceptions; `JMSContext` streamlines the native API yet still requires closing when application-created; `JmsTemplate` delegates lifecycle, conversion, and exception translation to Spring while integrating with transaction managers when properly configured. Safe resource release is a baseline operational requirement; transactions, redelivery, and idempotency must still be designed explicitly to achieve business reliability.

## References

- Jakarta Messaging 3.1 — specification, resources, and transactions: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 — `MessageProducer` API: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer
- Jakarta Messaging 3.1 — `JMSContext` API: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext
- Spring Framework — JMS integration: https://docs.spring.io/spring-framework/reference/integration/jms.html
- Spring Framework — Sending a message and callbacks: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework — Receiving a message: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework — Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — `JmsTransactionManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html
- Spring Boot — Artemis and JMS: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html