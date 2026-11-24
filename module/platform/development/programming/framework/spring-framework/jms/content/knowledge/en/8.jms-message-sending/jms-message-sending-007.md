# Sending Multiple Operations via SessionCallback in Spring JMS

## 1. Purpose and Use Cases

In many applications, a single business request emits more than one JMS message. For instance, when an order is accepted, a service needs to send a **business message** to an order-processing Queue and an **audit message** to a tracking Queue. Writing each operation as a separate `jmsTemplate.convertAndSend(...)` call is simple, yet it does not make explicit that they must share **the same JMS `Session`** or **commit/rollback together**.

Spring JMS provides `org.springframework.jms.core.SessionCallback<T>`. When calling `JmsTemplate.execute(SessionCallback<T>)`, Spring lends the callback a `jakarta.jms.Session` to perform multiple operations: create `Message` instances, create `MessageProducer`s, send to one or more `Destination`s, set headers/properties, and return a result.

Key principle to grasp firmly:

> **Multiple operations sharing a `Session` do not automatically form an atomic transaction.** `SessionCallback` is a session-scoped API; to achieve "all succeed or all roll back", you must configure an appropriate **JMS transaction boundary**, such as `JmsTransactionManager` combined with `TransactionTemplate` or `@Transactional`.

After this lesson, you will be able to:
- Understand the signature, lifecycle, ownership, and usage of `SessionCallback<T>`.
- Send multiple `TextMessage`s inside one callback, targeting multiple Queues or a single Queue.
- Distinguish session reuse from transactions/atomicity, JMS batching, and message ordering behavior.
- Build a Java 17+ / Spring Boot / Apache ActiveMQ Artemis example with explicit JMS commits.
- Know when to prefer `ProducerCallback`, `MessageCreator`, or multiple `convertAndSend` calls; avoid resource and transaction mistakes.

Examples use **Jakarta Messaging** (`jakarta.jms.*`) and **Spring Framework 6.x** (via Spring Boot 3.5.x). Legacy Spring projects using `javax.jms` require their own compatible dependency set; never mix the two namespaces.

## 2. What Is SessionCallback?

`SessionCallback<T>` is a functional interface in `org.springframework.jms.core`. At its core, it declares one method:

```java
@FunctionalInterface
public interface SessionCallback<T> {
    T doInJms(jakarta.jms.Session session)
            throws jakarta.jms.JMSException;
}
```

This is an **illustrative signature**, not code you need to redeclare since Spring already provides the interface. `T` is the result type returned by the callback. The callback may return an integer, a result object, or `null` if no value is needed.

Application code invokes it as:

```java
T result = jmsTemplate.execute(
        (SessionCallback<T>) session -> {
            // Perform JMS operations within the same session.
            return resultValue;
        });
```

This snippet merely illustrates the callback shape (variables `jmsTemplate`, `resultValue`, and type `T` must exist in the surrounding context).

### What Does JmsTemplate Do Before and After the Callback?

```text
Service
   |
   +--> JmsTemplate.execute(SessionCallback)
              |
              +--> Find Session already bound to a Spring transaction (if any)
              |    or open/obtain an appropriate Connection + Session
              |
              +--> call doInJms(session)
              |      |
              |      +--> createQueue / createTopic
              |      +--> createTextMessage / set properties
              |      +--> createProducer / send 1
              |      +--> send 2 / ... / send n
              |      +--> callback returns T
              |
              +--> clean up/release template-managed resources
              +--> translate checked JMSException into Spring JmsException
   |
   +--> use result T
```

`JmsTemplate` coordinates acquiring and releasing the connection and session. If a `JmsTransactionManager` is managing a transaction, it uses the thread-bound session and the **transaction manager** commits or rolls back at the right moment. Without a transaction, the template manages the session lifecycle as a standalone operation.

**Important:** `execute(SessionCallback)` is normally meant for sending operations and therefore **does not require `Connection.start()`**. The overload `execute(SessionCallback, boolean startConnection)` lets you start message delivery if the session is genuinely used to receive. For regular message consumption, prefer `@JmsListener`; for simple synchronous receives, use `JmsTemplate.receive(...)`.

### Who Owns Which Resource?

| Object | Who creates/owns it? | Rules inside callback |
| --- | --- | --- |
| `Connection` and `Session` supplied by template | Spring/template or transaction manager | Do not `close()` the session; do not retain a reference after the callback finishes. |
| `MessageProducer` created via `session.createProducer(...)` | The callback itself | Close via `try-with-resources`/`finally`. |
| `Message` created via `session.createTextMessage(...)` | Created within the session | Used within the send scope; not a closeable resource. |
| `Destination` created via `session.createQueue(...)` | Provider handle representing Queue/Topic | Normally has no `close`; physical Queues on the broker are a separate matter. |
| Transaction opened by `JmsTransactionManager` | Spring transaction manager | Do not manually call `session.commit()`/`rollback()` inside a callback participating in a managed transaction. |

`Session` is not an object safe for arbitrary concurrent sharing across threads. **Never** use `parallelStream`, `CompletableFuture.runAsync`, or spawn threads to share the same `Session` passed into the callback.

## 3. Minimal Example: Sending Two Messages in One execute Call

Suppose `JmsTemplate` is configured with a `ConnectionFactory` pointing to a broker and a Queue named `orders.queue`.

```java
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.SessionCallback;

public final class TwoMessages {
    private final JmsTemplate template;

    public TwoMessages(JmsTemplate template) {
        this.template = template;
    }

    public int publish(String orderId) {
        Integer count = template.execute((SessionCallback<Integer>) session -> {
            Queue queue = session.createQueue("orders.queue");

            try (MessageProducer producer = session.createProducer(queue)) {
                var placed = session.createTextMessage("placed:" + orderId);
                placed.setStringProperty("orderId", orderId);
                producer.send(placed);

                var confirmed = session.createTextMessage("confirmed:" + orderId);
                confirmed.setStringProperty("orderId", orderId);
                producer.send(confirmed);
            }
            return 2;
        });

        return java.util.Objects.requireNonNull(count);
    }
}
```

This is a **class used inside an application that already has `JmsTemplate` and a JMS broker**, not a program with `main()`. Both `producer.send(...)` calls run inside **the same callback, the same JMS Session, the same producer, and the same Queue**. The return value `2` represents **the number of sends executed by the callback without throwing an exception**, not how many times a consumer succeeded in processing them.

Why use `try-with-resources`? Because the callback **itself created** the producer via `session.createProducer`, so the callback itself must close it. Closing the producer **does not close the session**; the session belongs to `JmsTemplate`'s lifecycle.

### Switching to Two Queues

Inside one `SessionCallback`, you can create two `Destination`s from the same session and send each message to its target:

```java
Integer count = jmsTemplate.execute((SessionCallback<Integer>) session -> {
    Queue orders = session.createQueue("orders.queue");
    Queue audit = session.createQueue("audit.queue");

    try (var orderProducer = session.createProducer(orders);
         var auditProducer = session.createProducer(audit)) {

        orderProducer.send(session.createTextMessage("order-created"));
        auditProducer.send(session.createTextMessage("order-audited"));
    }
    return 2;
});
```

This is a snippet inside a service with a `jmsTemplate` bean and imports for `SessionCallback` and `Queue`, not a standalone Java file. It illustrates that **a single session can use multiple producers and multiple destinations**.

**Do not infer that the two sends are atomic just because they share a session:** if the session is non-transacted, the first send may succeed while the second fails. When you need a single JMS transaction covering both, use the configuration in Section 5.

## 4. Comparison with Ordinary Sending

```java
jmsTemplate.convertAndSend("orders.queue", "order-created");
jmsTemplate.convertAndSend("audit.queue", "order-audited");
```

These are two separate invocations. Without an enclosing Spring transaction, they may use separate logical sessions/transactions, and the success of the first does not depend on the second. It is more concise than a callback, yet you cannot access a single shared session across both calls merely by writing them back-to-back.

`SessionCallback` is useful when you:
1. Want to work **directly** with the Jakarta Messaging API and perform multiple `send` calls on one session.
2. Want to reuse one or a few `MessageProducer`s within a short scope instead of creating a producer per send.
3. Want to construct different message types/headers/properties or send to multiple Queues/Topics with the same session.
4. Want to return an aggregate result (number of prepared/sent messages, generated IDs, control info) from the callback.
5. Want tight control over resource boundaries and to bind that session to an **actively managed JMS transaction**.

**What `SessionCallback` does not do automatically:** it is not a special broker-side message batching API, it does not guarantee a single network round-trip, it does not eliminate all overhead, and it does not create a transaction by itself. Sending `n` messages usually remains `n` JMS send operations; brokers/providers may optimize internally depending on configuration, but performance claims must be measured.

## 5. Complete Spring Boot Example with a JMS Transaction

To make two message sends commit or roll back together, the example uses:

- Java 17+.
- Spring Boot **3.5.8**, compatible with Spring Framework 6.x and Jakarta Messaging.
- Apache ActiveMQ Artemis client via `spring-boot-starter-artemis`.
- `JmsTransactionManager` managing a **local JMS transaction**.
- `TransactionTemplate` establishing the transaction boundary programmatically; this keeps the example straightforward because it does not depend on `@Transactional` proxy invocation rules.
- `JmsTemplate.execute(SessionCallback<Integer>)` sending two messages sequentially within the same transaction-bound JMS session.

**Prerequisites to run:** an external Artemis broker listening on `tcp://localhost:61616`, valid credentials, and Queues `demo.orders` and `demo.audit` existing or allowed by the broker's auto-create policy. Maven only starts the client application; it does **not** start the broker.

### 5.1. Project Structure

```text
session-callback-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── jms/
        │           ├── SessionCallbackApplication.java
        │           ├── JmsTransactionConfiguration.java
        │           └── MultiSendService.java
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
    <artifactId>session-callback-demo</artifactId>
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

`spring-boot-starter-artemis` brings in Spring JMS and the Jakarta-compatible Artemis client under Spring Boot dependency management. Do not add legacy JMS 1.x libraries using `javax.jms` to the same application; mixing namespaces causes compile errors or `ClassCastException`s.

### 5.3. application.properties

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}

# Publisher uses Queues, not Topics:
spring.jms.pub-sub-domain=false

# Illustrative value: session caching can reduce overhead under high load.
spring.jms.cache.session-cache-size=5
```

`JMS_USERNAME` and `JMS_PASSWORD` must be supplied from the environment before running and must match the broker account. Never commit real passwords into source control. If the broker uses TLS, HA, or failover, configure the URL/transport per Artemis documentation rather than copying the local URL above verbatim.

**Note:** Spring Boot's cache setting is not an automatic multi-socket connection pool. `CachingConnectionFactory` can cache connections/sessions at the Spring layer; do not mistake "session cache size 5" for "5 JMS connections".

### 5.4. Configuring JmsTransactionManager and TransactionTemplate

**`src/main/java/example/jms/JmsTransactionConfiguration.java`**

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.connection.JmsTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration(proxyBeanMethods = false)
public class JmsTransactionConfiguration {

    @Bean(name = "jmsTransactionManager")
    JmsTransactionManager jmsTransactionManager(ConnectionFactory connectionFactory) {
        return new JmsTransactionManager(connectionFactory);
    }

    @Bean(name = "jmsBatchTransactionTemplate")
    TransactionTemplate jmsBatchTransactionTemplate(
            @Qualifier("jmsTransactionManager") JmsTransactionManager manager) {
        return new TransactionTemplate(manager);
    }
}
```

`JmsTransactionManager` manages a `ConnectionFactory`. In this example there is one factory auto-configured by Spring Boot; both the sending template and the transaction manager share that bean. **If your application has multiple `ConnectionFactory` beans**, verify that the template and manager point to **the exact same bean/wrapper**, not merely two separate factories connecting to the same broker.

When a transaction begins, the manager acquires/binds a `Connection` and `Session` to the current thread. `JmsTemplate` detects the bound session and reuses it inside the callback. When `TransactionTemplate` completes normally, the manager commits the JMS transaction. If the callback throws an exception, the manager rolls it back.

### 5.5. Service Performing Both Sends

**`src/main/java/example/jms/MultiSendService.java`**

```java
package example.jms;

import java.util.Objects;

import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.SessionCallback;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class MultiSendService {

    private final JmsTemplate jmsTemplate;
    private final TransactionTemplate transactionTemplate;

    public MultiSendService(
            JmsTemplate jmsTemplate,
            @Qualifier("jmsBatchTransactionTemplate")
            TransactionTemplate transactionTemplate) {
        this.jmsTemplate = jmsTemplate;
        this.transactionTemplate = transactionTemplate;
    }

    public int publishOrder(String orderId) {
        Integer published = transactionTemplate.execute(status ->
            jmsTemplate.execute((SessionCallback<Integer>) session -> {
                Queue orderQueue = session.createQueue("demo.orders");
                Queue auditQueue = session.createQueue("demo.audit");

                try (MessageProducer orderProducer =
                             session.createProducer(orderQueue);
                     MessageProducer auditProducer =
                             session.createProducer(auditQueue)) {

                    TextMessage order = session.createTextMessage(
                            "order-created:" + orderId);
                    order.setStringProperty("orderId", orderId);
                    orderProducer.send(order);

                    TextMessage audit = session.createTextMessage(
                            "audit-created:" + orderId);
                    audit.setStringProperty("orderId", orderId);
                    auditProducer.send(audit);
                }
                return 2;
            })
        );

        return Objects.requireNonNull(published, "Transaction returned null");
    }
}
```

**Reading from the outside in:**

1. `transactionTemplate.execute(...)` opens a JMS transaction via `JmsTransactionManager`.
2. `jmsTemplate.execute(SessionCallback<Integer>)` receives the session bound to the active transaction.
3. The callback creates two `Queue` handles and two `MessageProducer`s from **the same session**.
4. Each message has a distinct body while sharing the business property `orderId`. Avoid reusing one `TextMessage` and mutating its content before sending to the second Queue; separate messages keep logs and traces clear.
5. `producer.send` is called twice. The callback explicitly closes **both producers it created** via `try-with-resources`. It **never** closes the session supplied by the template.
6. The callback returns `Integer 2`, which propagates out through `TransactionTemplate`.
7. When the callback and transaction body finish normally, `JmsTransactionManager` commits. Only after `transactionTemplate.execute` returns does `publishOrder` return `2`.
8. If either send or the commit fails, the exception propagates outward; the transaction rolls back if still possible. If connectivity drops right at commit time, the broker state may be **ambiguous** to the client, so the business layer still requires idempotency.

**Why not call `session.commit()` inside the service?** Because the session belongs to a **Spring-managed** transaction. Calling commit/rollback manually inside the callback can break transaction boundaries, especially if other operations also participate.

### 5.6. Main and ApplicationRunner

**`src/main/java/example/jms/SessionCallbackApplication.java`**

```java
package example.jms;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SessionCallbackApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionCallbackApplication.class, args);
    }

    @Bean
    ApplicationRunner sendOnStartup(MultiSendService service) {
        return args -> {
            int count = service.publishOrder("demo-001");
            System.out.println("committedJmsMessages=" + count);
        };
    }
}
```

All three Java classes reside in package `example.jms` so Spring component scanning discovers `@Configuration` and `@Service`. `ApplicationRunner` calls the service bean **through the Spring container**, though using `TransactionTemplate` means this example does not depend on AOP proxy behavior for transactions.

With the broker running, both Queues valid, correct credentials, and a successful transaction commit, the line **explicitly printed by the application** is:

```text
committedJmsMessages=2
```

Spring Boot and Artemis client startup logs will also appear. The program **does not print consumer-received output**, as the example focuses on the producer; to verify the Queues received the messages, inspect the broker console/metrics or write a dedicated consumer integration test. Re-running the application sends two additional new messages with the same payloads—it is not an exactly-once delivery mechanism.

### 5.7. How to Run

On PowerShell:

```powershell
$env:JMS_USERNAME = "dev-user"
$env:JMS_PASSWORD = "dev-password"
mvn spring-boot:run
```

On POSIX shells:

```bash
JMS_USERNAME=dev-user JMS_PASSWORD=dev-password mvn spring-boot:run
```

Adjust credentials to match your broker. If the broker disallows Queue auto-creation, pre-provision `demo.orders` and `demo.audit` with Artemis ANYCAST routing. If the broker runs on another host, update `spring.artemis.broker-url` to the right endpoint. Without a broker, valid credentials, or existing Queues, the program may compile cleanly yet fail at send time; do not confuse integration failures with Java syntax errors.

To build without running:

```bash
mvn -q -DskipTests package
```

Running against a broker constitutes a real integration test. Never claim runtime verification in an environment where no broker was provided.

## 6. Core Principle: SessionCallback Does Not Automatically Guarantee Commit

This is the most critical concept when sending multiple operations.

### 6.1. Shared Session Without a Transaction

Suppose the default template does not enable `sessionTransacted`, and no Spring/JTA transaction is active:

```java
jmsTemplate.execute((SessionCallback<Void>) session -> {
    Queue first = session.createQueue("demo.orders");
    Queue second = session.createQueue("demo.audit");

    try (var p1 = session.createProducer(first);
         var p2 = session.createProducer(second)) {
        p1.send(session.createTextMessage("order-1"));
        p2.send(session.createTextMessage("audit-1"));
    }
    return null;
});
```

If `p1.send` succeeds and `p2.send` throws an error, the callback and template raise an exception, yet **the first message may already have been accepted by the provider**. Even though both operations shared a session, there is no local transaction to roll them back together.

### 6.2. JmsTemplate.setSessionTransacted(true) and a Major Pitfall

`JmsTemplate` can be configured with `setSessionTransacted(true)` to create transacted sessions in unmanaged environments. However, **do not assume `execute(SessionCallback)` automatically calls `session.commit()` after the callback**.

In Spring Framework 6.x, `JmsTemplate.execute(SessionCallback)` acquires the session → invokes the callback → releases the session. It **does not contain a generic commit call at the end of the callback** unlike certain convenience send/receive methods that have dedicated commit logic. If you create a local transacted session and the callback merely calls `producer.send(...)` and exits **without a transaction manager and without committing**, closing the session may roll back the uncommitted sends.

Therefore, never try to "fix atomicity" by flipping `sessionTransacted=true` while leaving the callback unchanged without deciding who commits.

### 6.3. Three Clear Models

| Model | Condition | Who decides commit? | Atomicity of two sends |
| --- | --- | --- | --- |
| `SessionCallback` on regular session | No transaction, e.g., default | No shared transaction | All-or-nothing is not guaranteed. |
| Callback on **unmanaged** local transacted session | `sessionTransacted=true` and callback controls it | Code must call `session.commit()`/`rollback()` properly | Local JMS transaction if provider supports it. |
| `SessionCallback` participating in `JmsTransactionManager` | Transaction boundary via `TransactionTemplate` or `@Transactional` | Spring transaction manager | Sends inside the same JMS transaction commit/roll back together. |

**Never have two controllers issuing commits simultaneously.** In Section 5's example, the manager owns the transaction, so the callback does not commit or roll back itself.

### 6.4. Manual Local Transaction Example — Only Without a Manager

When running standalone code without `JmsTransactionManager`/JTA and intentionally wanting a transaction **committed by the callback itself**, use a dedicated template:

```java
JmsTemplate localTemplate = new JmsTemplate(connectionFactory);
localTemplate.setSessionTransacted(true);

localTemplate.execute((SessionCallback<Void>) session -> {
    try {
        Queue queue = session.createQueue("demo.orders");
        try (var producer = session.createProducer(queue)) {
            producer.send(session.createTextMessage("first"));
            producer.send(session.createTextMessage("second"));
        }

        session.commit(); // Only in self-managed local sessions.
        return null;
    } catch (jakarta.jms.JMSException | RuntimeException ex) {
        try {
            session.rollback();
        } catch (jakarta.jms.JMSException rollbackFailure) {
            ex.addSuppressed(rollbackFailure);
        }
        throw ex;
    }
});
```

This is a **snippet** assuming `connectionFactory`, imports for `JmsTemplate`/`SessionCallback`, and a ready broker. It must not be nested inside an existing Spring/JTA transaction. Errors occurring during `close()` after commit must also be logged/monitored; if `commit` throws due to a dropped connection, the client cannot always know whether the broker committed. In Spring services, **prefer the manager-managed boundary in Section 5** for clear ownership and easy composition across multiple template calls.

### 6.5. @Transactional as an Alternative for the Same Goal

You can replace `TransactionTemplate` with `@Transactional` if the application has AOP/proxy support properly configured:

```java
import org.springframework.transaction.annotation.Transactional;
import org.springframework.jms.core.SessionCallback;

@Transactional(transactionManager = "jmsTransactionManager")
public int publishWithAnnotation(String id) {
    Integer count = jmsTemplate.execute((SessionCallback<Integer>) session -> {
        try (var producer =
                     session.createProducer(session.createQueue("demo.orders"))) {
            producer.send(session.createTextMessage("event-1:" + id));
            producer.send(session.createTextMessage("event-2:" + id));
        }
        return 2;
    });
    return java.util.Objects.requireNonNull(count);
}
```

This is an **additional illustrative method** inside a Spring-managed service that already has `jmsTemplate`, not a standalone Java file. It requires `@EnableTransactionManagement` or equivalent transaction infrastructure, and calls must pass **through the Spring proxy**. If another method in the same class calls `this.publishWithAnnotation(...)` under default proxy-based AOP, that internal self-invocation bypasses transaction advice. Never stack both transaction boundaries on top of each other "just to be safe".

When using a local `JmsTransactionManager` transaction, JDBC/database operations are **not automatically** atomic with it. If you require reliable combined DB persistence and JMS publishing, consider transactional outbox or genuinely configured XA/JTA rather than just adding `@Transactional`.

## 7. Comparing SessionCallback and ProducerCallback

Beyond `SessionCallback<T>`, `JmsTemplate` also offers `ProducerCallback<T>`:

```java
Integer count = jmsTemplate.execute(
        "demo.orders",
        (session, producer) -> {
            producer.send(session.createTextMessage("one"));
            producer.send(session.createTextMessage("two"));
            return 2;
        });
```

In `execute(destinationName, ProducerCallback)`, **`JmsTemplate` creates and closes the `MessageProducer`**; the callback receives both session and producer ready to use. This cuts boilerplate when sending multiple messages to the same destination.

| Scenario | Better fit |
| --- | --- |
| Send one message without low-level JMS APIs | `convertAndSend` or `send(MessageCreator)`. |
| Send multiple messages to **one Queue** with one producer | `ProducerCallback` can be more concise. |
| Send to multiple Queues/Topics, create multiple producers, need custom session logic | `SessionCallback`. |
| Adjust headers/properties on a single message before send | `MessageCreator`/`MessagePostProcessor`. |
| Multiple template calls in one transaction, not necessarily one callback | `JmsTransactionManager` + `TransactionTemplate` or `@Transactional`. |

**Neither `ProducerCallback` nor `SessionCallback` creates an atomic transaction on its own.** Picking a callback determines resource access level; the transaction boundary is a separate responsibility.

### Using an Unbound Producer

Jakarta Messaging allows a producer **not bound to a fixed destination**:

```java
jmsTemplate.execute((SessionCallback<Void>) session -> {
    var firstQueue = session.createQueue("demo.orders");
    var secondQueue = session.createQueue("demo.audit");

    try (var producer = session.createProducer(null)) {
        producer.send(firstQueue, session.createTextMessage("first"));
        producer.send(secondQueue, session.createTextMessage("second"));
    }
    return null;
});
```

This illustrates `MessageProducer.send(Destination, Message)`: creating an anonymous producer and specifying the destination on each send. It can be shorter than two separate producers, though QoS settings and optimizations depend on the provider. For portability or explicit conventions, creating two Queue-bound producers as in the main example is equally valid.

## 8. Headers, Properties, and Quality of Service Inside Callbacks

A major reason to use `SessionCallback` is full control over `Message`:

```java
jmsTemplate.execute((SessionCallback<Void>) session -> {
    Queue queue = session.createQueue("demo.orders");
    try (var producer = session.createProducer(queue)) {
        producer.setDeliveryMode(jakarta.jms.DeliveryMode.PERSISTENT);
        producer.setPriority(4);
        producer.setTimeToLive(60_000L);

        var message = session.createTextMessage("order-created");
        message.setStringProperty("eventType", "ORDER_CREATED");
        message.setStringProperty("orderId", "o-123");
        message.setJMSCorrelationID("corr-o-123");

        producer.send(message);
    }
    return null;
});
```

This snippet assumes an existing `jmsTemplate` and imports for `SessionCallback` and `Queue`. Because **the callback invokes `producer.send` directly**, do not assume `JmsTemplate` convenience settings such as explicit QoS, delivery delay, or message conversion automatically apply the way they do in `jmsTemplate.convertAndSend(...)`. You are using the **raw JMS API** inside the callback; set producer QoS, headers, and properties explicitly when needed.

Points of caution:

- `PERSISTENT` requests the JMS persistent delivery mode; actual durability guarantees depend on broker persistence, replication, HA, and commit policies.
- `timeToLive` governs message lifetime, not send confirmation timeout. Once expired, the provider/broker handles expiration per policy.
- `priority` is a priority hint; actual delivery ordering also depends on the provider, concurrent consumers, and configuration.
- `JMSCorrelationID` links request/reply or traces; it does not create a business idempotency key on its own.
- JMS property names you set must be valid identifiers; business properties like `eventType` and `orderId` can be used in JMS selectors.
- When using `BytesMessage`/`MapMessage`/`ObjectMessage` instead of `TextMessage`, pay attention to serialization compatibility and security. Never deserialize untrusted arbitrary objects.

## 9. Does Sending Multiple Operations Guarantee Ordering?

**The `send` call order** within the same thread and session follows program execution order:

```text
producer.send(message-1)
producer.send(message-2)
producer.send(message-3)
```

However, **business processing order at consumers** cannot be deduced from those three lines alone:

- On **one Queue**, multiple competing consumers may receive and process concurrently, so the second message can finish processing before the first.
- Priority, redelivery, expiration, and provider mechanics can change actual delivery order from expectations.
- Across two different Queues, there is no global ordering between the two destinations, even when both messages commit in the same JMS transaction.
- A transaction committing two sends guarantees the JMS commit/rollback boundary, **not** that two downstream consumers process atomically or simultaneously.
- When ordering per `orderId` is required, consider grouping/partitioning by key or dedicated per-group consumers per broker design, while also checking retry semantics.

When business rules require audit to run only after order processing completes, **sending order and audit in the same transaction does not create that dependency**. You may need workflows, message chaining, or explicit orchestration rather than inferring order from send sequence.

## 10. Proper Error Handling and Retries

### 10.1. Failure Between Two Sends

Suppose `orderProducer.send(order)` succeeds, then `auditProducer.send(audit)` throws `JMSException`:

- In a non-transacted session, the order message may already have reached the broker; `SessionCallback` cannot undo it.
- With `JmsTransactionManager` from Section 5, a checked `JMSException` escaping the callback is translated by Spring into the unchecked `JmsException` hierarchy. `TransactionTemplate` catches the error and rolls back the active session.
- If **commit** already ran and an exception occurred afterward due to other work or a network drop right as the response returned, the client may be uncertain whether the transaction committed. Retrying can introduce duplicate messages at the business level.

**Never swallow exceptions just so the service returns `2`.** If you catch `JMSException` or Spring `JmsException` and return normally inside the transaction body, Spring treats it as success and commits earlier sends. To roll back, let the exception propagate or explicitly call `status.setRollbackOnly()` in `TransactionTemplate`.

### 10.2. Retry the Entire Unit of Work, Not Arbitrary Individual Sends

If you want "either both messages or neither", retry logic must wrap **the entire transaction**. Never do:

```text
send(order) succeeds
send(audit) fails
retry send(audit) independently
```

when business logic expects both messages tied to a single event to stay consistent. Instead:
- Distinguish retryable errors (transient connection drops) from configuration, permission, or bad payload errors.
- Enforce bounded attempts, exponential backoff, and safeguards against retry storms.
- Attach an **immutable `eventId`/`orderId`** to every message so consumers can be idempotent.
- Monitor DLQs, redeliveries, and transaction rollbacks on the broker; the sender alone cannot guarantee consumer-side exactly-once processing.

### 10.3. Do Not Naively Combine Database and JMS

`JmsTransactionManager` is a transaction manager **for JMS resources**. SQL statements under `DataSourceTransactionManager` **do not automatically join** a single atomic transaction merely because both appear in a `@Transactional` method.

Dangerous example:
1. Write order row to database; DB transaction commits.
2. Send two JMS messages; JMS commit fails.
3. Database has the order, yet no notification messages exist.

Or the reverse: messages commit while the DB rolls back. For systems requiring consistency between DB and JMS, common solutions are the **transactional outbox** paired with an idempotent publisher, or JTA/XA when infrastructure genuinely supports it and justifies operational cost.

## 11. Performance, Session Scope, and Batch Limits

`SessionCallback` helps **define a clear session scope**. Used properly, it reduces repeated producer creation/closing or groups multiple sends into one transaction. However, do not equate it with JDBC batching or an API that packs 1,000 messages into one network packet.

**When sending a large batch:**
- Cap the message count and byte size per transaction. Overly large transactions hold resources longer, increase memory usage, raise commit latency, and increase rollback work.
- Consider splitting into smaller per-transaction batches if business rules allow; each batch needs clear IDs and retry semantics.
- Do not open a new producer for every single message when all go to the same Queue inside the same callback; reuse one producer within that short scope.
- When targeting multiple Queues, either create one producer per Queue or use one unbound producer; measure on the actual provider.
- Never retain a `Session` or `MessageProducer` in a singleton service for reuse across requests. To optimize across callbacks, let `ConnectionFactory` caching/pooling and Spring lifecycle handle it.
- `Session` is thread/context-scoped; do not run parallel Java Streams inside the callback against the same session.
- Tune delivery mode, persistence, message size, session cache, and transaction size based on benchmarks; never claim callbacks are automatically orders of magnitude faster than `convertAndSend` within a shared transaction.

Consider batch sizing carefully: if one transaction holds hundreds of events, a failure on the very last event rolls back and forces resending the whole batch. Balance throughput against blast radius rather than blindly cramming as many messages as possible into one callback.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking `SessionCallback` = transaction | Message 1 sent while message 2 fails, non-atomic | Configure `JmsTransactionManager` and an explicit transaction boundary. |
| Enabling `sessionTransacted=true` without committing in unmanaged session | Pending local transaction rolls back on session close | Use a manager-managed transaction or commit/rollback manually in proper scope. |
| Calling `session.commit()` inside a Spring-managed transaction | Breaks manager boundaries, may commit prematurely | Let the manager commit after the transaction body. |
| Calling `session.close()` inside callback | Template still needs session; resource lifecycle errors | Never close the session supplied by Spring. |
| Failing to close self-created producers | Provider-side resource leak | Use `try-with-resources` for any self-created `MessageProducer`. |
| Sharing one `Session` across threads | Violates JMS concurrency rules | Execute sequentially in callback; give each thread its own session. |
| Nesting `jmsTemplate.send(...)` inside callback expecting same session | May create/enlist resources differently, unpredictable without tx | Use `session` directly or define an outer Spring transaction clearly. |
| Catching and ignoring `JmsException` | Transaction manager sees normal return and partially commits | Propagate exceptions or mark rollback-only. |
| Using `@Transactional` via self-invocation | Annotation bypassed by proxy | Call through a Spring bean/proxy or use `TransactionTemplate`. |
| Assuming two Queues committing together means consumers run together | Consumers run independently with different ordering/acks | Design downstream workflows and idempotency. |
| Growing batch size without limit | Huge transactions, costly rollbacks | Split batches per SLA and provider limits. |
| Confusing Queue/Topic, domain, and destination | Messages go to the wrong place or provider rejects send | Resolve destinations per JMS provider; check `pubSubDomain` when using template names. |

## 13. Testing and Observability

A thorough testing approach separates **callback unit tests**, **broker integration tests**, and **transaction failure tests**.

### 13.1. Testing the Happy Path

- Start an appropriate Artemis test broker and provision `demo.orders` and `demo.audit`.
- Invoke `publishOrder("case-001")` exactly once.
- Verify each Queue contains one new message with the matching body and property `orderId=case-001`; if other consumers exist, verify via test consumers/records rather than only checking Queue depth.
- Output `committedJmsMessages=2` must appear **after** the transaction manager returns normally.
- Use a unique `eventId` per test run to distinguish messages from prior runs.

### 13.2. Testing Rollback

Deliberately trigger a failure on the second message before commit—for instance, in a test environment, via a broker policy denying sends to `demo.audit` or a provider setup allowing fault simulation. Expectations:
- The service throws an exception.
- The transaction rolls back unless an ambiguous commit-time failure occurs.
- The broker shows no **newly committed** messages from that transaction.
- Logs record `orderId`, error type, destination, and transaction rollback—never passwords.

**Do not** simulate this by throwing an exception after `TransactionTemplate` has already completed and committed, because rollback cannot retract already-committed sends.

### 13.3. Testing Retries and Broker Restarts

- Stop the broker mid-send; observe error messages and reconnect behavior.
- Restart the broker; resend with **the same `eventId`** to test consumer idempotency.
- Simulate connection loss right during commit if your test environment supports fault injection; never infer commit certainty solely from a timeout error.
- Measure connection/session/producer counts on the broker across many sends to ensure no unbounded resource leaks.

### 13.4. Metrics to Monitor

- Successful/failed `publishOrder` calls and full transaction latency.
- JMS commit/rollback counts, rollback reasons, connection errors, and timeouts.
- Backlog, in-flight counts, consumer counts, redeliveries, and DLQs per Queue.
- Average messages sent per transaction; message/transaction sizes.
- Duplicate `eventId` counts or duplicate skips by consumer idempotency.

**Note:** publisher counters measure client-side actions and cannot prove downstream consumers finished processing; downstream metrics and tracing are required.

## 14. Production Readiness Checklist

- Clarify whether the goal is **session sharing** or **atomic sending**. For atomicity, configure an explicit transaction manager and boundary.
- Use the exact same `ConnectionFactory` for both template and `JmsTransactionManager`, especially with caching/pooling wrappers.
- Issue all intended operations from **the same session**; keep callbacks short, sequential, and batch-bounded.
- Close producers created by the callback; never close template-managed sessions/connections or leak the session outside the callback.
- Let checked `JMSException` convert to Spring `JmsException` or propagate; never swallow errors inside a transaction.
- When using `@Transactional`, verify proxy invocation and the right transaction manager name.
- Attach `orderId`/`eventId` for tracing/idempotency; consider transactional outbox if a database transaction is involved.
- Verify send permissions to all Queues and destination existence policies before deploying.
- Never promise global processing order solely from sending inside the same callback.
- Benchmark against a real broker before concluding callbacks/batching improve throughput.

## 15. Self-Check Questions

**1.** Why are two `producer.send(...)` calls inside one `SessionCallback` not automatically all-or-nothing?

Sharing a `Session` only defines resource scope. Atomicity requires a transacted session and an explicit commit/rollback boundary.

**2.** Inside the callback, should you close `MessageProducer` or `Session`?

Close any `MessageProducer` created by the callback itself. Never close the `Session` supplied by `JmsTemplate`.

**3.** When using `JmsTransactionManager`, when does the transaction commit?

When the Spring transaction boundary (e.g., `TransactionTemplate.execute`) finishes normally, **after** the callback has returned.

**4.** Is `JmsTemplate.setSessionTransacted(true)` enough for `execute(SessionCallback)` to auto-commit?

Do not assume so. For an unmanaged local transacted session, you must commit/rollback explicitly at the right spot; better yet, use an explicit transaction manager in Spring services.

**5.** When is `ProducerCallback` more convenient than `SessionCallback`?

When sending multiple messages to one destination and wanting the template to create and close the producer for you.

**6.** If a JMS transaction commits two messages to two Queues, will two consumers always process them simultaneously, exactly once, and in order?

No. Publish atomicity is distinct from consumer concurrency, processing order, and idempotency.

## Conclusion

`JmsTemplate.execute(SessionCallback<T>)` is the right tool when you need **multiple JMS operations on the same `Session`** while still letting Spring manage session and connection acquisition/release. You can build multiple messages, create multiple producers, send to one or more Queues/Topics, set properties/headers, and return an aggregate result.

To enforce "either all messages are sent, or none are", wrap the callback **inside a JMS transaction** managed by `JmsTransactionManager`/`TransactionTemplate` or properly configured `@Transactional`. Never equate sharing a session with sharing a transaction; never manually commit when Spring owns the transaction; and never confuse publish atomicity with downstream exactly-once processing.

## References

- Spring Framework — Sending a Message, `SessionCallback` and `ProducerCallback`: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- Spring Framework — Using JMS and transaction management: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework — `JmsTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework — `SessionCallback` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/SessionCallback.html
- Spring Framework — `JmsTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html
- Spring Framework — TransactionTemplate: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Boot 3.5 — JMS / ActiveMQ Artemis: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Jakarta Messaging 3.1 — specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 — `MessageProducer` API: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer