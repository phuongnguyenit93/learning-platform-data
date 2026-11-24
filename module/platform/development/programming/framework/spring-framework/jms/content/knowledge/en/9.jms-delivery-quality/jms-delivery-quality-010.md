# Asynchronous Send with CompletionListener in the JMS API

## 1. Goal and Context

In JMS, sending a message is commonly written as `producer.send(message)`. In a **synchronous send**, the calling thread must wait for `send` to return; the guarantee when the call returns depends on delivery mode, broker/provider policies, and transactions.

Since JMS 2.0, Jakarta Messaging provides **asynchronous send** via `jakarta.jms.CompletionListener`. Instead of waiting for the entire send operation to finish on the calling thread, the application supplies a callback so the JMS provider can notify it of the outcome at the appropriate time. This is an **asynchronous send** API—not an asynchronous message receive API, and not Spring `@Async`.

This lesson belongs to **delivery quality** in Spring JMS, focusing on:

- How to register a `CompletionListener` on `MessageProducer` and `JMSProducer`.
- Behavior of `onCompletion(Message)`, `onException(Message, Exception)`, and cases where `send()` throws immediately.
- Exact meaning of "send succeeded" with `PERSISTENT`, transactions, acknowledgements, and potential duplicates.
- Threading, restrictions on using `Message`, callback ordering, and `close/commit/rollback` rules.
- A Spring Boot example using the **native JMS API** to send three messages asynchronously while controlling completion timing.
- Relationship to `JmsTemplate` and Spring's optimization/ownership boundaries.
- Testing, observability, timeouts, backpressure, retries, and common pitfalls.

Examples use **Java 17+, Spring Boot 3.5.8, Jakarta Messaging 3.x**, and Apache ActiveMQ Artemis. In modern Spring Framework applications, imports are `jakarta.jms.*`; older versions may use `javax.jms.*`. Specifically, Jakarta EE **web containers / Enterprise Beans containers** impose important restrictions on async send (Section 10).

## 2. Comparing Synchronous Send and Asynchronous Send

### 2.1. Synchronous Send

```java
producer.send(message);
// Thread continues after the send call returns.
```

This syntax is a snippet inside a method that already has `MessageProducer producer` and `Message message`. With many JMS providers, sending `PERSISTENT` may require waiting for broker acknowledgement before `send` returns. However, the specification also allows certain lower reliability levels not to wait for the same acknowledgement; never infer from the word "synchronous" that every call was durably fsynced on every broker.

### 2.2. Asynchronous Send with CompletionListener

```java
producer.send(message, new CompletionListener() {
    @Override
    public void onCompletion(Message sentMessage) {
        // JMS provider notifies that the send operation completed successfully.
    }

    @Override
    public void onException(Message attemptedMessage, Exception error) {
        // Error detected after send() was called.
    }
});
// Calling thread may continue before the callback runs.
```

This snippet requires imports `jakarta.jms.CompletionListener`, `jakarta.jms.Message`, and an existing `MessageProducer`. Here **`send(...)` returning does not mean `onCompletion` has been called**. The provider decides what work executes on the calling thread versus asynchronously, provided it satisfies the Jakarta Messaging contract.

### 2.3. Timeline

```text
Application thread                      JMS provider / broker
      |                                           |
      | producer.send(message, listener)          |
      |------------------------------>            |
      |          (call may return)                |
      |<------------------------------            |
      |                                           |
      | continues other work                 performs send / waits for ack if needed
      |                                           |
      |                                      success or failure
      |                                           |
      |                         provider thread invokes CompletionListener
      |                                      | onCompletion(...)
      |                                      | or onException(...)
      |                                           |
      | app updates state / observes result via thread-safe signal
```

The main benefit is **not forcing the sending thread to wait for each message to finish** before doing other work or issuing the next send. In return, the application must track pending operations, handle errors on both paths, and keep resources open long enough.

## 3. APIs Supporting Asynchronous Send

### 3.1. Classic JMS API: MessageProducer

`MessageProducer` provides the relevant overloads:

```java
// Producer bound to a destination:
void send(Message message, CompletionListener listener) throws JMSException;

void send(Message message,
          int deliveryMode,
          int priority,
          long timeToLive,
          CompletionListener listener) throws JMSException;

// Unidentified producer without a bound destination:
void send(Destination destination,
          Message message,
          CompletionListener listener) throws JMSException;

void send(Destination destination,
          Message message,
          int deliveryMode,
          int priority,
          long timeToLive,
          CompletionListener listener) throws JMSException;
```

These signatures are for learning the API, **not methods to reimplement yourself**. The `listener` parameter lets the JMS provider invoke the callback once the operation finishes. They were introduced in JMS 2.0; choose a compatible Jakarta Messaging API and supporting provider.

You can bind a producer to a Queue at creation:

```java
Queue queue = session.createQueue("orders.queue");
MessageProducer producer = session.createProducer(queue);
producer.send(session.createTextMessage("order-42"), listener);
```

Or create an unbound producer and specify the Queue on each send:

```java
MessageProducer producer = session.createProducer(null);
producer.send(
        session.createQueue("orders.queue"),
        session.createTextMessage("order-42"),
        listener);
```

Both are snippets: `session` and `listener` must exist inside a method; the application must close producers it creates.

### 3.2. Simplified JMS API: JMSContext/JMSProducer

With `JMSContext`, you can create a `JMSProducer` and attach a listener via `setAsync`:

```java
try (JMSContext context =
             connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

    Queue queue = context.createQueue("orders.queue");
    JMSProducer producer = context.createProducer()
            .setAsync(listener);
    producer.send(queue, "order-42");

    // Must handle callback result if calling logic needs to know send succeeded.
}
```

This is a snippet inside a method that already has `connectionFactory` and `listener`. `JMSContext` closes at the end of `try-with-resources`, and by specification closing must wait for any in-flight async sends/callbacks to finish before completing. Therefore this block uses an async callback, yet **you must not advertise a `try-with-resources`-wrapped method like this as returning immediately**.

API differences:

| Classic JMS API | Simplified JMS API |
| --- | --- |
| `Connection + Session + MessageProducer` | `JMSContext + JMSProducer` |
| `producer.send(message, completionListener)` | `producer.setAsync(completionListener).send(destination, body)` |
| Typically checked `JMSException` | Many operations throw unchecked `JMSRuntimeException` |
| Explicit lifecycle management for producer/session/connection | `JMSContext` bundles responsibilities and is `AutoCloseable` |
| Easy low-level customization with `Session` | Concise when the app does not need the classic API |

`JMSProducer.setAsync(null)` reverts to synchronous send behavior. Never share a mutable `JMSContext` arbitrarily across threads: it represents a session and is bound by JMS threading rules.

## 4. Exact Contract of CompletionListener

The `jakarta.jms.CompletionListener` interface has two methods:

```java
public interface CompletionListener {
    void onCompletion(Message message);
    void onException(Message message, Exception exception);
}
```

### 4.1. onCompletion: Send Completed with Equivalent Synchronous Guarantee

The provider may invoke `onCompletion(message)` only when the send succeeded with **the same level of certainty** that an equivalent synchronous `send` must provide. The exact meaning still depends on delivery mode, provider, and transactions. `onCompletion` does **not** mean a consumer received it, finished processing, committed a database, or sent a business reply.

With a **local JMS transaction** session, the send-completion callback can run **before** the application calls `session.commit()`. Messages in that transaction are not committed merely because the callback ran. `CompletionListener` signals **completion of the send operation**, not a "JMS transaction committed" callback.

When the callback succeeds, code can record metrics, complete a future, update in-memory job status, or hand off a lightweight signal to an executor for further work. If reliability across restarts is required, critical state must be durably persisted in the business design.

### 4.2. onException: Failures That Could Not Be Thrown Directly from send

If the provider detects an error **after the `send` call has returned**, it invokes `onException(message, exception)`. **You cannot be sure the message never reached the broker**; the specification notes that upon failure, whether the send succeeded may be in an indeterminate state.

For example, a mid-flight network drop: the broker may have received the message while confirmation never reached the client. Unconditional retries can produce duplicate business messages. Attach `eventId`/`orderId` and design idempotent consumers.

### 4.3. Exception Thrown Directly by send(): No Callback for That Send

If an exception occurs and is thrown **directly on the thread calling `send(...)`**, the provider **does not** invoke `onCompletion` or `onException` for that same invocation.

This matters especially when decrementing a `CountDownLatch`. If code decrements the latch only inside the callback and `send` throws synchronously, the program can hang forever. The right pattern handles both:

```java
try {
    producer.send(message, listener);
} catch (JMSException | RuntimeException immediateFailure) {
    // Do not wait for a callback for an invocation that threw synchronously.
    // Record failure and signal completion here.
}
```

`onException` receives `Exception`, not just `JMSException`. Even so, applications should not retry every error blindly; distinguish config/permission errors, payload errors, and transport errors.

### 4.4. Threading and Message Usage Rules

Per Jakarta Messaging:

- The provider invokes `CompletionListener` on a **different thread** from the thread calling async `send`. Thus the callback must be thread-safe.
- A `Session` must not be used concurrently from multiple threads. The callback **must not** access the same session while an application thread could still be using it.
- On the same `MessageProducer`, callback order matches the order of async `send` invocations. Across multiple producers/sessions/threads, never infer global callback order.
- After `send` returns and **before the callback runs**, the application must not read or modify headers, properties, or body of the in-flight `Message`. The provider may be mutating the message on another thread.
- Inside `onException`, provider-populated headers/properties have **undefined** state; do not build error workflows depending on those fields.
- Each in-flight send should use its **own `Message` object**. Do not send and then mutate the same instance for the next message before the callback runs.

Therefore, the callback should capture an **external final/effectively final `eventId`** and use that `eventId` for logging/tracking rather than reading mutable fields off the message on error.

## 5. Rules for close, commit, and rollback — The Most Misunderstood Part

Jakarta Messaging enforces two crucial rules for asynchronous sends:

1. When the application calls `close()` on `MessageProducer`, `Session`, or `Connection`, the provider must **wait for any incomplete asynchronous sends to finish and their callbacks to return** before completing `close()`.
2. On a **local transacted Session**, when the application calls `commit()` or `rollback()`, the provider must wait for incomplete asynchronous sends and their callbacks to finish before proceeding with commit/rollback.

In other words, **asynchronous send does not make `close` or `commit` non-blocking**. That is why "async send then immediately close the producer" may yield none of the expected latency gains.

A `CompletionListener` **must not** call `close()` on its own associated producer/session/connection, nor call `commit()`/`rollback()` on the associated session. The provider will throw `IllegalStateException` or `IllegalStateRuntimeException` as appropriate.

Example of **what never to write**:

```java
producer.send(message, new CompletionListener() {
    @Override
    public void onCompletion(Message ignored) {
        producer.close(); // WRONG: never close the producer inside its own callback.
    }

    @Override
    public void onException(Message ignored, Exception error) {
        // Also never commit/rollback the session inside the callback.
    }
});
```

This is an **anti-pattern example**, not runnable code. In real apps, the callback only signals completion via `CompletableFuture`, `CountDownLatch`, an internal queue, or thread-safe state. A **separate owner** closes resources after observing that callbacks returned.

**Note on timeouts:** `latch.await(10, SECONDS)` bounds only how long the application thread waits at that call; `close()` inside `finally`/`try-with-resources` still waits for pending callbacks, so the latch timeout **does not guarantee** the enclosing method returns within 10 seconds. Connection, send, and close/recovery timeouts must be configured and measured per provider.

## 6. Runnable Spring Boot Example: Sending Three Messages Asynchronously

This example is a **Spring Boot client application**, not a Jakarta EE WAR inside an application server. It lets Spring Boot create the Artemis `ConnectionFactory`, then uses the **native Jakarta Messaging API** inside `ApplicationRunner`.

Technical goals of the example:

1. Send three distinct `TextMessage` instances via `MessageProducer.send(message, CompletionListener)`.
2. Do not wait for the callback after **each** send; issue invocations sequentially on the same session.
3. Use `CountDownLatch` and `AtomicInteger` to wait for callbacks in a thread-safe way before concluding.
4. Handle both error paths separately: synchronous exceptions from `send` and `onException` callbacks.
5. Close application-opened resources per proper lifecycle; never close inside callbacks.

### 6.1. Prerequisites

- JDK 17+, Maven.
- An Apache ActiveMQ Artemis broker running at `tcp://localhost:61616`, or adjust the endpoint to your environment.
- `demo.async.queue` already exists on the broker, or the broker permits auto-creating the appropriate ANYCAST Queue.
- JMS credentials with send permission. Set `JMS_USERNAME` and `JMS_PASSWORD` in the environment; never hardcode production passwords.
- Broker/client support for Jakarta Messaging async send per dependency versions. Providers differ in buffering/optimizations, so benchmark before relying on production throughput assumptions.

### 6.2. Maven Dependency

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
    <artifactId>async-jms-completion</artifactId>
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

`spring-boot-starter-artemis` brings Spring JMS and a compatible Artemis Jakarta client through Boot dependency management. Do not add `javax.jms-api`; the example code imports `jakarta.jms`.

### 6.3. application.properties

**`src/main/resources/application.properties`**

```properties
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}
spring.jms.pub-sub-domain=false
```

`JMS_USERNAME` and `JMS_PASSWORD` have **no defaults** in the example to prevent unintentionally using a fallback account. They must be provided at startup. `spring.artemis.mode=native` requires an external Artemis broker; the app does not start an embedded broker.

### 6.4. Complete Java Code

**`src/main/java/example/jms/AsyncCompletionApplication.java`**

```java
package example.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.jms.CompletionListener;
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AsyncCompletionApplication {

    private static final String QUEUE_NAME = "demo.async.queue";
    private static final int MESSAGE_COUNT = 3;

    public static void main(String[] args) {
        SpringApplication.run(AsyncCompletionApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(ConnectionFactory factory) {
        return args -> sendMessages(factory);
    }

    static void sendMessages(ConnectionFactory factory) throws Exception {
        CountDownLatch callbacks = new CountDownLatch(MESSAGE_COUNT);
        AtomicInteger successes = new AtomicInteger();
        AtomicInteger failures = new AtomicInteger();
        AtomicInteger sendCallsReturned = new AtomicInteger();

        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             MessageProducer producer =
                     session.createProducer(session.createQueue(QUEUE_NAME))) {

            for (int i = 1; i <= MESSAGE_COUNT; i++) {
                String eventId = "event-" + i;
                TextMessage message =
                        session.createTextMessage("payload-" + eventId);
                message.setStringProperty("eventId", eventId);

                CompletionListener listener = new CompletionListener() {
                    @Override
                    public void onCompletion(Message ignored) {
                        // Provider thread; do not touch Session here.
                        successes.incrementAndGet();
                        callbacks.countDown();
                    }

                    @Override
                    public void onException(
                            Message ignored, Exception error) {
                        // Do not read mutable Message state on failure.
                        failures.incrementAndGet();
                        System.err.println(
                                "callbackFailed=" + eventId + ":"
                                + error.getClass().getSimpleName());
                        callbacks.countDown();
                    }
                };

                try {
                    producer.send(message, listener);
                    sendCallsReturned.incrementAndGet();
                } catch (JMSException | RuntimeException immediateError) {
                    // Per spec, an invocation throwing directly
                    // will not receive any callback.
                    failures.incrementAndGet();
                    System.err.println(
                            "sendFailedImmediately=" + eventId + ":"
                            + immediateError.getClass().getSimpleName());
                    callbacks.countDown();
                }
            }

            System.out.println(
                    "sendCallsReturned=" + sendCallsReturned.get());

            boolean allSignalled =
                    callbacks.await(15, TimeUnit.SECONDS);
            if (!allSignalled) {
                throw new IllegalStateException(
                        "Timeout waiting for send completion callbacks");
            }
            if (failures.get() != 0) {
                throw new IllegalStateException(
                        "Failed sends=" + failures.get());
            }

            System.out.println(
                    "callbacksSucceeded=" + successes.get());
        }
        // Connection.start() is not called since this example only sends.
        // close() waits for any incomplete async sends/callbacks.
    }
}
```

**Why is this pattern safer than a "fire-and-forget" demo?**

- `Session` is used solely by the `ApplicationRunner` thread for sequential `send` calls; callbacks update only thread-safe variables.
- Three distinct `TextMessage` instances are prepared before each invocation. Messages are never mutated after `send` returns.
- `CountDownLatch` is signaled when a callback runs **or** when `send` throws directly. Per the JMS spec, both never happen for the same invocation.
- Callbacks never call `close/commit/rollback` and never touch the session.
- Producer, session, and connection are closed outside callbacks; no resource leaks occur when sends fail.
- `sendCallsReturned` counts only `send` calls that returned normally; `callbacksSucceeded` counts successful callbacks. Those are two different quantities.
- No `@Async`, `CompletableFuture.runAsync`, or custom thread pool is used to "wrap" JMS calls; asynchrony comes from the **Jakarta Messaging provider**.

Special note: in default Spring Boot apps, `ConnectionFactory` may be a caching wrapper. `close()` on a wrapped connection/session may return it to a pool/cache, yet the JMS contract for draining incomplete async sends still must be honored properly by the provider/wrapper; verify against your deployed versions.

### 6.5. Running

Create the matching project structure:

```text
async-jms-completion/
├── pom.xml
└── src/main/
    ├── java/example/jms/AsyncCompletionApplication.java
    └── resources/application.properties
```

PowerShell:

```powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "dev-user"
$env:JMS_PASSWORD = "dev-password"
mvn spring-boot:run
```

POSIX Shell:

```bash
JMS_BROKER_URL=tcp://localhost:61616 \
JMS_USERNAME=dev-user \
JMS_PASSWORD=dev-password \
mvn spring-boot:run
```

Substitute credentials and endpoint for your real broker. When all three sends are accepted, all three callbacks report success, and no errors occur, **the two application lines printed** are:

```text
sendCallsReturned=3
callbacksSucceeded=3
```

Spring Boot/Artemis may emit additional logs; callbacks may run before, during, or after the `for` loop, while `callbacksSucceeded` prints only after the latch completes. If the provider fails to report within 15 seconds, the program throws a timeout error; **closing** afterwards may still take longer. If the broker is down, the Queue is invalid, or permissions are missing, the program logs errors or throws an exception; never assume identical output across all environments.

To build without running a broker:

```bash
mvn -q -DskipTests package
```

To verify actual messages, use integration tests or the broker console/metrics. The line `callbacksSucceeded=3` **is not proof that three consumers processed the messages** or that downstream database transactions committed.

## 7. Both Error Paths and Future/CompletionStage Design

Real applications often want to return a `CompletionStage` instead of blocking on a `CountDownLatch` in the request thread. The pattern assigns one `CompletableFuture` **per invocation**, completing it inside the callback:

```java
CompletableFuture<Void> result = new CompletableFuture<>();

CompletionListener listener = new CompletionListener() {
    @Override
    public void onCompletion(Message message) {
        result.complete(null);
    }

    @Override
    public void onException(Message message, Exception exception) {
        result.completeExceptionally(exception);
    }
};

try {
    producer.send(message, listener);
} catch (JMSException | RuntimeException ex) {
    result.completeExceptionally(ex);
}
```

This is a **snippet** with `producer` and `message` already created; requires importing `java.util.concurrent.CompletableFuture`. Never omit the `catch` path, because no callback arrives if `send` throws directly.

### Completing the Future Does Not Mean Resources May Close Mid-Block

The snippet above shows only how to bridge a JMS callback into a Future. **It is not yet a complete non-blocking function**, because `producer`, `session`, and `connection` must stay alive until sends/callbacks complete. Never write:

```java
CompletionStage<Void> sendAndReturn() {
    try (Connection c = factory.createConnection();
         Session s = c.createSession(Session.AUTO_ACKNOWLEDGE);
         MessageProducer p = s.createProducer(s.createQueue("orders.queue"))) {

        CompletableFuture<Void> future = new CompletableFuture<>();
        p.send(s.createTextMessage("event"), new CompletionListener() {
            @Override
            public void onCompletion(Message m) {
                future.complete(null);
            }

            @Override
            public void onException(Message m, Exception e) {
                future.completeExceptionally(e);
            }
        });
        return future;
    }
}
```

This is an **illustrative anti-pattern** missing imports/fields and must not be used in production. `return future` executes before exiting `try`, yet Java mandates running `close()` before returning; `close` may block waiting for the callback. You accidentally blocked the thread despite using an async API inside.

Long-lived designs need an **explicit resource owner** (a component managing connection/session/producer or pooled executors) whose lifetime covers all in-flight sends and performs cleanup on a **separate coordinator thread**, **never** inside that producer/session's `CompletionListener`. If you do not need complex long-lived resource management, the Section 6 pattern—explicitly awaiting callbacks before closing—is easier to verify.

### What If the Future Times Out or Is Cancelled?

A `CompletableFuture.orTimeout(...)`/`cancel(...)` call normally updates only the Java-layer Future state; it **does not cancel** an in-flight JMS send or roll back the broker. After timeout, the callback may still arrive. Store `eventId`, reconcile with broker/consumer state, and enforce resource cleanup rules when the request lifecycle ends.

## 8. CompletionListener, JMS Transactions, and Delivery Quality

### 8.1. Callback Success Differs from Commit Success

Suppose you use a local transacted session:

```java
try (Connection connection = factory.createConnection();
     Session session =
             connection.createSession(Session.SESSION_TRANSACTED);
     MessageProducer producer =
             session.createProducer(session.createQueue("orders.queue"))) {

    CountDownLatch latch = new CountDownLatch(1);
    AtomicReference<Exception> asyncError = new AtomicReference<>();

    producer.send(session.createTextMessage("order-42"),
            new CompletionListener() {
                @Override
                public void onCompletion(Message message) {
                    latch.countDown();
                }

                @Override
                public void onException(Message message, Exception error) {
                    asyncError.set(error);
                    latch.countDown();
                }
            });

    if (!latch.await(15, TimeUnit.SECONDS)) {
        session.rollback();
        throw new IllegalStateException("Async completion timeout");
    }
    if (asyncError.get() != null) {
        session.rollback();
        throw new IllegalStateException(
                "Async send failure", asyncError.get());
    }

    session.commit();
}
```

This is a **snippet inside a `throws Exception` method** with `factory` and JMS/`CountDownLatch`/`TimeUnit`/`AtomicReference` imports; it is not a standalone program. Technically, `session.commit()` waits for incomplete callbacks before committing the local transaction, so awaiting before `commit` is not strictly required to make the provider wait, yet it is useful when the application wants to inspect/classify errors before deciding to roll back.

**Never call `commit/rollback` from inside the callback.** Callbacks can run before transaction commit; `onCompletion` does not prove the transaction committed. If `commit` throws due to a dropped connection, the outcome can be indeterminate to the client; hence `eventId`/idempotency is essential. `rollback` can also fail if the broker disconnects.

### 8.2. When Spring Manages Transactions

If the session participates in `JmsTransactionManager` or JTA, never call `session.commit()`/`rollback()` manually. The transaction manager owns the boundary. In Spring, make sure callback results/errors feed into transaction logic **before the manager decides to commit/roll back**; if `onException` runs after a service method returned normally without marking the transaction failed, behavior will diverge from business expectations.

When an application needs multiple atomic sends in Spring, the simpler API is usually `JmsTemplate` with `JmsTransactionManager` and `@Transactional`/`TransactionTemplate`, rather than forcing `CompletionListener`. Choose async send only when it solves a clear latency/throughput requirement and lifecycles are cleanly designed.

**Important:** A local JMS transaction is not automatically atomic with a SQL transaction. If an application updates a DB and sends JMS, consider transactional outbox or true JTA/XA when consistency guarantees are required.

### 8.3. Delivery Mode and Realistic Guarantees

| Setting or Signal | What It States | What It Does Not Guarantee |
| --- | --- | --- |
| `DeliveryMode.PERSISTENT` | Requests persistent protection per JMS/provider | Does not replace replication/HA/broker backups. |
| `DeliveryMode.NON_PERSISTENT` | Allows lower protection to favor performance | Does not promise survival across broker crashes. |
| `onCompletion` | Send finished with reliability equal to synchronous send | Does not prove consumer processed or downstream DB committed. |
| `onException` | Provider detected an async failure | Does not prove the broker never received the message. |
| `JmsTransactionManager.commit` succeeded | Session's JMS transaction committed per provider | Does not mean another system's DB transaction committed. |
| `message.setJMSCorrelationID` | Adds correlation for tracing/request-reply | Does not automatically provide idempotency or deduplication. |
| `timeToLive` | Limits message lifetime per JMS | Not a callback wait timeout and does not enforce processing deadlines. |

**Dangerous confusion:** "send callback success" and "message processed exactly once" are two separate problems. Downstream can redeliver after consumer failures, messages can expire past TTL, move to DLQ, or be handled by multiple systems per policy.

## 9. Send Call Order, Callback Order, and Processing Order

Jakarta Messaging requires that when the same `MessageProducer` sends multiple messages, JMS ordering rules are respected, even when mixing synchronous and asynchronous sends. The application is **not required** to wait for the first callback before sending the next message.

On the same producer, the provider invokes callbacks in the order of the async `send` invocations. Even so:

- **Callback order** is not **business completion order** on the consumer: a Queue can have multiple concurrent consumers.
- Different sessions or different producers **have no global callback order**.
- Priority, redelivery, expiration, message grouping, and provider policies can affect actual delivery/processing order.
- Across two different Queues, there is no cross-queue business processing order merely because the app sent to them back to back.
- For a failed send, the corresponding outcome may be `onException` or **no callback at all** if an exception was thrown directly on the calling thread.

If your app requires ordering per `orderId`, combine single-consumer/partitioning/message-groups per broker support with idempotency rather than relying on callback log order.

## 10. Platform Restrictions: Jakarta EE Containers and Spring Boot

Jakarta Messaging 3.1 specifies that **asynchronous send with `CompletionListener` must not be used in a Jakarta EE web container or Enterprise Beans container**. Restricted APIs include `MessageProducer.send(..., CompletionListener)` overloads and `JMSProducer.setAsync(CompletionListener)`. Providers are permitted to throw `JMSException` or `JMSRuntimeException` in those environments.

This **does not ban all async JMS sends in standalone Spring Boot**. The Section 6 example is a Spring Boot Java application running outside a Jakarta EE web/EJB container, so it does not hit that container restriction merely by using `@SpringBootApplication`. However, if deploying Spring as a WAR **inside a Jakarta EE application server** or using resource adapters/container-managed JMS, verify container rules and infrastructure integration carefully. Never assume identical code runs unchanged across all deployment models.

For Spring apps managing resources via `JmsTemplate`:

- `JmsTemplate.send`/`convertAndSend` is normally a **call-synchronous** facade and does not natively accept `CompletionListener`.
- You can reach the underlying API via `JmsTemplate.execute(SessionCallback)` to create a producer and invoke the async overload, **but** when the callback returns and the template cleans up resources, `close` may wait for async completion. That pattern does not automatically produce a non-blocking service API.
- `@Async` or `CompletableFuture.supplyAsync` wrapping `jmsTemplate.convertAndSend` **offloads synchronous work onto an application thread pool**, fundamentally different from JMS native async send.
- `@JmsListener` handles asynchronous message **receiving**, not replacing `CompletionListener` for **sending**.

Low-level Spring integration example (not a recommended non-blocking pattern):

```java
jmsTemplate.execute((SessionCallback<Void>) session -> {
    try (MessageProducer producer =
                 session.createProducer(session.createQueue("orders.queue"))) {
        TextMessage message =
                session.createTextMessage("order-42");
        producer.send(message, completionListener);
    }
    return null;
});
```

This snippet assumes `jmsTemplate`, `completionListener`, and imports exist. `MessageProducer.close()` at the end of the callback may **wait for the callback to complete**, so never promise the caller returns before send finishes. Use only when you understand lifecycle/performance implications and ensure transaction managers are not bypassed.

## 11. Performance, Backpressure, and Load Management

Async send helps when **waiting for send acknowledgements** dominates caller latency. However, if the app can emit messages faster than the broker handles them, the in-flight queue grows continuously. No `CompletionListener` automatically bounds pending requests.

Practical principles:

1. **Bound in-flight sends:** use a `Semaphore` or bounded internal queue. Issue new sends only when in-flight count is below threshold. Release permits in thread-safe callback code upon completion.
2. **Measure callback latency:** measure from before `send` until callback; track percentiles (p50/p95/p99), not just when `send` returns.
3. **Separate two counters:** `send` invocations returned vs. `onCompletion` successes; the two counts can differ at any point in time.
4. **Monitor synchronous and async failures:** count `send` exceptions, `onException` calls, Future/latch timeouts, and broker disconnects separately.
5. **Never block long in callbacks:** avoid DB/HTTP calls or holding locks inside callbacks. Providers may serialize callbacks on the same session; slow callbacks degrade throughput and stall `close`.
6. **Measure the full lifecycle:** time `close()` and `commit()` too; fast loops that stall for ages at `close` may not improve overall throughput.
7. **Keep `eventId` immutable:** on ambiguous errors, pair retries with idempotency rather than blindly re-sending without distinguishing attempts.
8. **Optimize after measuring:** JMS persistent/non-persistent mode, batch sizes, TTL, broker paging, socket timeouts, and session caching can matter more than callback API choice.

### Backpressure Architecture Example

```text
Request / event source
      |
      +--> acquire permit (at most N in-flight)
               |
               +--> producer.send(message, listener)
                          |
                          +--> callback success: update result, release permit
                          |
                          +--> callback failure: update failure, release permit
               |
               +--> synchronous exception: release permit immediately, do not await callback
```

When using a real semaphore, guarantee **each invocation releases its permit exactly once**, even if `send` throws directly. Never release a second time in the callback if `send` threw directly; the spec guarantees no callback runs on that path. Other failures (message creation, producer creation, connection closing) must also release resources/permits cleanly.

## 12. Retries, Duplicates, and Indeterminate States

Suppose an async send emits `event-17`. The broker accepts the message, but the network drops before confirmation. `onException` may report failure even though the broker already has the message. If the producer automatically re-sends `event-17`, downstream can see two messages with the same `eventId`.

A practical design:

- Every event has a unique, durable `eventId` preserved across retries.
- Receivers maintain a dedup table/store or idempotency logic so side effects never run twice.
- Apply bounded retries, exponential backoff with jitter, and error classification.
- Track states `PENDING`, `ACKNOWLEDGED`, `FAILED`/`UNKNOWN` with reconciliation policies; never assume timeout means "definitely failed."
- If publishing is part of a database transaction, consider a **transactional outbox** with a durable background publisher.
- When events have a TTL, check the deadline before retrying; resending an obsolete message can cause unwanted side effects.

Note that `onCompletion` is not proof the consumer acked. A consumer may receive and roll back, the broker redelivers, and the app needs idempotent logic even for a single send.

## 13. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `send(..., listener)` return as send complete | Returns HTTP 200 / commits business state too early | Assert send guarantees only upon `onCompletion` or proper transaction commit. |
| Handling only `onException`, forgetting synchronous `catch` | Latch/Future never completes, requests hang | Catch `JMSException`/unchecked at `send` and signal immediately in `catch`. |
| Closing producer/session inside callback | Violates JMS; throws `IllegalStateException` or deadlock-like failure | Have an external owner outside the callback perform cleanup. |
| Closing right after `send` and calling it "fully non-blocking" | `close` may block waiting for callback, losing async benefits | Design proper resource lifetimes or accept explicit await patterns. |
| Reading/mutating `Message` right after `send` before callback | Undefined behavior, provider may throw | Use a dedicated message per in-flight send; wait for callback before reading headers. |
| Reading JMS headers in `onException` and trusting them | Provider-set header state may be undefined | Log a separately captured `eventId` instead of relying on `JMSMessageID` on failure. |
| Callback touches same `Session` while another thread uses it | Violates threading restrictions | Callback updates only thread-safe state; never touches `Session`. |
| Treating `onCompletion` as "transaction committed" | Callback can run before `commit` | Commit at the proper boundary; verify commit outcomes separately. |
| Treating `onCompletion` as "consumer processed once" | Duplicates/redeliveries/DB failures still happen | Idempotent consumers, retries/DLQ, separate business acks. |
| Sharing a mutable `JMSContext` across threads | Race/concurrency bugs on JMS session | Scope context appropriately or use proper resource managers/pools. |
| Awaiting callbacks indefinitely in requests | Thread exhaustion during broker outages | Timeouts, bounded in-flight counts, circuit breakers, and recovery policies. |
| Blocking callbacks with HTTP/DB calls | Provider callback thread stalls, hurting throughput | Keep callback minimal and offload heavy work to a bounded executor. |
| Using async send in a Jakarta EE web/EJB container | Violates JMS API restrictions | Choose APIs and send models supported by the container. |
| Treating Future timeout as cancelling the JMS send | Message may still reach the broker | Track late outcomes, reconcile, and enforce idempotency. |
| Holding large payloads with unbounded in-flight sends | High memory pressure and broker overload | Bounded queues/semaphores, monitor heap and broker paging. |

## 14. Testing Checklist

### 14.1. Happy Path

- Start an Artemis broker, create `demo.async.queue` or enable appropriate auto-create.
- Run the example with `MESSAGE_COUNT=3` and valid credentials.
- Verify `sendCallsReturned=3` and `callbacksSucceeded=3` after the latch completes.
- Verify the Queue actually holds three messages or a test consumer receives all three with `eventId` properties `event-1`, `event-2`, `event-3`. If other consumers exist, do not judge solely by pending count.
- Verify no producer/session leaks after context shutdown.

### 14.2. Exceptions Thrown Directly

- Configure an invalid provider/connection or mock `MessageProducer` in unit tests so `send` throws immediately.
- Verify no callback runs for the directly failing invocation and the latch/future still signals from `catch`.
- Verify code does not hang forever waiting for a missing callback.

### 14.3. Failures Arriving in onException

- Use an integration test environment capable of injecting transport/ack faults after `send` returns.
- Verify the listener receives the error, failure metrics increment, logs contain `eventId`, and the app does not assume the message is absent from the broker.
- Avoid assuming every network cut triggers one fixed error path; it depends on timing and provider.

### 14.4. Thread Safety and Message Lifecycle

- Send multiple distinct messages on the same producer, calling `send` from **one thread per session scope**; never run `parallelStream` on the same `Session`.
- Deliberately forbid reading messages before callback in tests/code reviews; a provider occasionally not throwing **does not** prove the usage is valid.
- Ensure callbacks never call `close/commit/rollback` on the sending resources.
- Measure callback latency and callback ordering on the same producer; never infer consumer processing order.

### 14.5. Timeout, Shutdown, and Commit

- Test callbacks arriving later than `await` timeout: the program reports timeout while `close` may still wait.
- In a separate test, use a local transacted session; verify `onCompletion` before commit does not make the message committed.
- Shut down the app while sends are in flight and verify graceful shutdown, provider timeouts, and broker state.
- Test broker restart/HA per real infrastructure and observe sends left in `UNKNOWN`/duplicate states.

## 15. Quick Comparison of Spring Approaches

| Technique | Use Case | Where Does a Thread Wait? | Who Tracks Outcomes? |
| --- | --- | --- | --- |
| `JmsTemplate.convertAndSend` | Convenient sending, normally call-synchronous | Calling thread waits for template operation | Synchronous exception from template; transaction manager if configured. |
| `MessageProducer.send(..., CompletionListener)` | JMS native async send | Sending thread may continue; `close`/`commit`/`await` can still block | `CompletionListener` + exceptions at `send`. |
| `JMSProducer.setAsync(listener)` | Simplified Jakarta Messaging API | Similar; requires managing `JMSContext` | `CompletionListener` + `JMSRuntimeException`. |
| `@Async` wrapping `JmsTemplate` | Offloads sync template work to an app executor | An executor thread may block | Spring `Future`/`CompletableFuture`; still must manage executor. |
| `@JmsListener` | Asynchronous message receiving/consumption | Listener container uses worker threads | Listener container, acks/transactions/retries. |
| `JmsTemplate` + `JmsTransactionManager` | Safe, explicit transactional JMS sends | Caller/transaction boundary waits for commit | Transaction manager, exceptions/rollbacks. |

Choose `CompletionListener` when the real goal is reducing caller wait time on send confirmations and you have solid in-flight/recovery design. If the goal is merely "do not block HTTP requests," you may need an outbox or durable background publisher rather than shifting all risk onto callbacks.

## 16. Self-Check Questions

**1.** After `producer.send(message, listener)` returns normally, can the message be considered sent with the full guarantee of a synchronous send?

**No.** You must wait for `onCompletion` for the equivalent guarantee, unless a separate provider/transaction confirmation mechanism applies.

**2.** If `send` throws `JMSException` immediately, must `onException` still be called afterwards?

**No; on the contrary, the provider must not invoke any callback for an invocation that threw directly.** The application handles the error in `catch`.

**3.** Can `producer.close()` be called inside that producer's own `onCompletion`?

**No.** That violates the contract. Another owner must close resources outside the callback.

**4.** Why does `CompletionListener` not mean the consumer processed the message exactly once?

Because the callback reports **send** completion, not consumer acknowledgement/transactions. Redeliveries and business duplicates can still occur.

**5.** In a local transacted session, once `onCompletion` runs, is the message committed?

**Not necessarily.** You still need `session.commit()` or transaction manager commit to succeed; the callback does not replace commit.

**6.** Can you reuse the same `Message`, mutate its body right after the first async send, and send a second time?

**No.** Never read or modify an in-flight `Message` before its callback; use separate objects.

**7.** Why does `CompletionListener` not automatically improve latency when called inside `JmsTemplate.execute` and immediately leaving the callback?

Because template/producer cleanup may call `close()`; per spec, `close` must wait for incomplete async sends/callbacks. You need explicit resource lifecycle design, not just the async overload.

## Conclusion

`CompletionListener` is the **Jakarta Messaging-layer asynchronous send** mechanism, allowing providers to report success or failure after the caller issues a send. Outcomes must be handled across **two paths**: direct exceptions from `send` and `onCompletion`/`onException` callbacks. A successful callback provides only the guarantee of an equivalent send—it does not prove a consumer processed the message or a downstream database transaction committed.

In Spring, you can use the native JMS API via `ConnectionFactory` or `SessionCallback`, while keeping template lifecycles and `close/commit` callback-waiting rules in mind. For production systems, add idempotency, bounded in-flight tracking, metrics/timeouts, and retry policies. Never use async send in Jakarta EE web/EJB containers where Jakarta Messaging 3.1 restrictions apply.

## References

- Jakarta Messaging 3.1 Specification — Section 7.3 *Asynchronous send*, quality of service, exceptions, ordering, threading, close/commit/rollback: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 API — `CompletionListener`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/completionlistener
- Jakarta Messaging 3.1 API — `MessageProducer`, `send(..., CompletionListener)` overloads: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer
- Jakarta Messaging 3.1 API — `JMSProducer` and `setAsync`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmsproducer
- Spring Framework — Sending a message, `JmsTemplate`, and callbacks: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework — Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — `JmsTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Boot — Artemis/JMS integration: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Apache ActiveMQ Artemis — Using JMS: https://artemis.apache.org/components/artemis/documentation/latest/using-jms