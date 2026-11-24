# Session and Single-Threaded Send/Receive Context in JMS

## Objectives

After this lesson, you should understand:

1. `Session` is a stateful context for creating, sending, and receiving messages in **Jakarta Messaging (JMS)**.
2. The **one thread of control at a time** rule applies to `Session`, `MessageProducer`, `MessageConsumer`, and `JMSContext`; a `Connection` can manage multiple independent sessions.
3. Why listeners on the **same Session** execute serially, whereas multiple sessions enable concurrent processing.
4. Acknowledgments and local transactions are scoped to the **Session**, so sharing a session improperly can break processing correctness.
5. Spring `JmsTemplate` and listener containers manage sessions so application code can operate multithreaded without storing a `Session` in a singleton.

**Key takeaway:** *Single-threaded Session* does not mean the entire JMS application has only one thread. It means **each session may be used by only one thread of control at a time**. To increase concurrency, use multiple appropriate sessions/consumers; in Spring, let the container manage them.

## 1. Where Does Session Sit in the API Hierarchy?

JMS is also known as Java Message Service. In Jakarta Messaging 3.x, the interfaces belong to the `jakarta.jms` package; older examples prior to the namespace transition may use `javax.jms`. Because this module covers Spring Framework JMS, we examine both the underlying API and Spring's integration layer.

~~~text
ConnectionFactory
  └─ Connection (logical connection to the JMS provider)
      ├─ Session A — one thread of control at a time
      │    ├─ MessageProducer A1 ──send()──► Queue/Topic
      │    └─ MessageConsumer A1 ◄─receive()/onMessage()── Queue/Topic
      ├─ Session B — can operate concurrently with A
      │    └─ MessageConsumer B1 ◄── Queue
      └─ Session C — can operate concurrently with A, B
           └─ MessageProducer C1 ──► Topic
~~~

| Object | Role | How can it be shared? |
|---|---|---|
| `ConnectionFactory` | Creates connections/contexts per provider configuration | Typically supplied via DI and called from multiple threads; pooling/caching behavior depends on the implementation. |
| `Connection` | Manages connection to the provider, creates multiple sessions, starts/stops delivery | One connection can have **multiple Sessions** active concurrently. Do not assume sessions on the same connection must run sequentially. |
| `Session` | Creates producers, consumers, destinations, and messages; holds delivery, ack, and local transaction state | **Must not be used concurrently** from multiple threads of control. |
| `MessageProducer` / `MessageConsumer` | Sends/receives messages; bound to the session that created them | Subject to the owning session's sequential rule; avoid sharing producers/consumers across threads. |
| `MessageListener` | Callback `onMessage(Message)` when messages are delivered asynchronously | Within **one session**, callbacks are serialized; across multiple sessions they can run in parallel. |
| `JMSContext` | Simplified API combining an underlying connection and session | Also subject to session threading restrictions. |

A `Session` also provides operations such as `createQueue`, `createTopic`, `createTextMessage`, `createProducer`, `createConsumer`, `commit`, `rollback`, and `recover` (depending on mode). A session can serve multiple producers/consumers, but **does not turn them into independently concurrent resources**.

### Session Is a Context, Not a Thread

- Creating a `Session` **does not mean** you have created a `java.lang.Thread` or a dedicated executor.
- "Single-threaded" is an **access contract**, not a guarantee that a session can only ever be touched by one OS thread over its entire lifetime. In synchronous mode, sequential hand-off of usage rights can occur, but writing custom hand-off logic is error-prone; best practice is explicit ownership management.
- When a session has an asynchronous listener and the connection is started, the provider-managed message delivery thread holds control of that session. At that point, you **must not** manipulate the session arbitrarily from application threads.
- This concept is **not equivalent** to `ThreadLocal`, Spring request scope, or a database transaction. A session has its own JMS state and its own lifecycle.

## 2. Core Rule: One Thread of Control per Session

The Jakarta Messaging specification, section `6.2.5 Threading restrictions on a session`, defines a session for **sequential use by one thread at a time**. Aside from resource-closing operations intended for shutdown, applications must avoid concurrent access.

### 2.1. Valid Usage: Each Worker Owns Its Own Session

~~~text
Thread-1 ─► Session-1 ─► Consumer-1 ─► process order #101
Thread-2 ─► Session-2 ─► Consumer-2 ─► process order #102
Thread-3 ─► Session-3 ─► Producer-3 ─► send event

           May share the same Connection.
~~~

With multiple workers processing the same queue, each session/consumer is an independent message-receiving unit. While one worker is processing a message, another worker can proceed because it owns a **different session**.

### 2.2. Invalid Usage: Multiple Workers Sharing One Session

~~~text
Thread-1 ─┐
          ├─► same Session ─► same MessageConsumer/Producer  ❌
Thread-2 ─┘

Thread-1 is calling consumer.receive(10_000) while
Thread-2 calls session.createProducer(...), commit(), recover(), or receive().
~~~

This violates the API contract. Symptoms can include exceptions, hangs, race conditions, unexpected delivery behavior, or one thread's transaction/ack affecting another thread's messages. There is no guarantee every provider will detect and report the error: code that seems to run fine under light load is still invalid.

**Distinguish two situations:**

- `Thread A` finishes sending completely, and then `Thread B` uses the session *with no listener driving the session*: with respect to the "one thread at a time" rule, this differs from concurrent use, but requires very careful hand-off, lifecycle, and state management. It should not be used as a default design.
- `Thread A` and `Thread B` overlap in access, or an application thread touches a session currently driven by an asynchronous listener: **wrong**. Wrapping only part of the code in `synchronized` does not resolve asynchronous callbacks, lifecycle, acks, and transactions.

### 2.3. One Session Can Have Multiple Consumers, Yet Remains Sequential

~~~text
                    Session S
             ┌────────────────────┐
Queue A ────►│ Consumer A         │
Queue B ────►│ Consumer B         │──► same callback thread of control
             └────────────────────┘
                  onMessage(A1)
                  onMessage(B1)
                  onMessage(A2)
                   (non-overlapping within the same S)
~~~

If multiple `MessageListener` instances are registered on consumers of the **same session**, the provider must serialize callback invocations. While `onMessage(A1)` has not finished, another callback in the same session cannot execute in parallel. This is a session-scoped guarantee; it **does not mean** JMS guarantees global ordering across different queues/topics or different producers.

To process callbacks in parallel, create multiple sessions. When doing so, the **processing completion order** across workers may differ from the order in which messages entered the broker.

## 3. Synchronous `receive()` and Asynchronous `onMessage()`: Choose One Model per Session

### 3.1. Synchronous Receive

A thread calls `MessageConsumer.receive(timeout)`; it waits until a message arrives or the timeout expires. `receive(0)` waits indefinitely per the JMS API; in real applications, set an intentional timeout. `receiveNoWait()` returns immediately if no message is available.

~~~text
Thread T:
  create Session S and MessageConsumer C
  connection.start()
  C.receive(5_000) ──(block)──► Message
  process Message
  ack/commit if needed
  call receive again or close resources
~~~

While `receive()` is blocking, do not pass that session to another thread. Do not let two threads call `receive()` concurrently on two consumers of the same session.

### 3.2. Asynchronous Listener

A thread configures the consumer and calls `consumer.setMessageListener(listener)`. When the connection starts, the provider delivers messages via the `listener.onMessage(message)` callback. A session with an active listener is dedicated to the **message delivery thread of control**.

Recommended sequence when writing plain JMS:

1. Create the connection but do **not** `start()` it yet.
2. Create the session, destination, producer, consumer, and register the relevant listeners.
3. Finish configuring any state that the callbacks will use.
4. Call `connection.start()` so the provider begins delivery.
5. Do not call synchronous `receive()` on that same session; do not invoke session methods from another application thread.
6. When shutting down, let the lifecycle management layer close consumers/sessions/connections in an orderly manner.

Registering a listener after starting can allow messages to arrive before setup is complete, causing a race. JMS specifies some exceptions and detailed rules around registering additional listeners, but initializing everything before `start()` remains the clearest and safest choice.

**Do not mix** `consumer.receive()` and `consumer.setMessageListener(...)` on the same active session. Those two models drive the session from two different threads of control, violating JMS rules.

### 3.3. Producer Inside a Listener

Sometimes a listener needs to create and send a reply message. In the plain JMS API, you can create the producer before starting the connection and let **the same callback that owns the session** use that producer sequentially. Do not hand that producer to an external worker pool for concurrent sending.

If processing the message and sending the response must belong to the same local JMS transaction, they can run in the **same transacted session**; the transaction still covers only the corresponding JMS resources and does not automatically include an external database.

### 3.4. Exceptions Around `close()`

The specification allows certain resource-closing operations (`Connection.close`, `Session.close`, `MessageConsumer.close`, and the corresponding methods of the simplified API) from another thread to support orderly shutdown. However, this exception **does not permit** arbitrary concurrent send/receive/commit/rollback from multiple threads. Calling `close()` on the session itself from inside `onMessage()` has behavior that is not completely portable and should be avoided; let the container or lifecycle management thread decide when to close.

## 4. Scope of Session-Bound Acknowledgment

A session holds more than producers/consumers. It also holds **the sequence of delivered messages**, acknowledgment state, and, if enabled, **a local transaction sequence**. This explains why session races have business consequences.

| Session Mode | When is a message acknowledged? | Key Points to Remember |
|---|---|---|
| `AUTO_ACKNOWLEDGE` | The JMS API auto-acks when `receive()` succeeds or when the listener finishes per provider/API rules | The application does not explicitly control per-message ack timing; in a Spring listener container, behavior also depends on how the container receives and invokes the listener. |
| `CLIENT_ACKNOWLEDGE` | The application calls `message.acknowledge()` | Per the JMS standard, **acknowledges all messages delivered by that session**, not just the message on which the method is called. |
| `DUPS_OK_ACKNOWLEDGE` | Provider may acknowledge lazily | Reduces overhead in some cases, but the application must tolerate potential redelivery. |
| `SESSION_TRANSACTED` | `session.commit()` acknowledges received messages and finalizes sends in the local JMS transaction; `rollback()` undoes them | A separate acknowledgment mode has no effect in a transacted session. |

### 4.1. Example of the `CLIENT_ACKNOWLEDGE` Trap

A session receives `M1` and then `M2`. When code calls `M2.acknowledge()`, **both M1 and M2 delivered by that session are acknowledged** (even if the application has not finished processing M1). Therefore, you should not pull multiple messages from the same session and hand them off to multiple independent threads that acknowledge out of order.

To manage independent units of work, each worker should have its own session, or use one sequential worker with clear ack/commit boundaries. If you want "per-message ack" with specialized semantics, verify the API/vendor; JMS `CLIENT_ACKNOWLEDGE` does not mean per-message ack.

### 4.2. Local Transactions Also Live Within the Session

With a transacted session:

~~~text
Session S:
  receive message X
  validate business logic
  send message Y (if using the same Session S)
  commit()
     ├─ ack X
     └─ complete sending Y in the same local JMS transaction
~~~

If an error occurs before commit, `rollback()` cancels sends in the transaction and causes received messages to be recovered according to JMS rules. Once committed, the session advances to the next transaction.

**Critical boundary:** `Session.commit()` does not commit a PostgreSQL, MongoDB, or HTTP call transaction. If a database write succeeds but JMS rolls back, X may be redelivered and DB side effects duplicated. Use an idempotency key/unique constraint or the transactional outbox pattern; when true distributed transactions are required, design JTA/XA with provider support.

### 4.3. Recovery and Redelivery

- In a **non-transacted** session, `session.recover()` returns the receiving session to the state after the last acknowledgment and requests redelivery of unacknowledged messages.
- In a **transacted** session, use `rollback()` instead of `recover()` for messages in the active transaction.
- Redelivery can cause a message to be processed multiple times if the application has not guarded side effects. Use `JMSMessageID`, `JMSCorrelationID`, or a business idempotency key for tracing/deduplication as appropriate; `JMSMessageID` does not replace a business key in all workflows.

## 5. Session and Resource Lifecycle

The plain JMS sequence is typically:

~~~text
ConnectionFactory.createConnection()
  → Connection.createSession(mode)
    → Session.createQueue()/createTopic()
    → Session.createProducer()/createConsumer()
      → producer.send(...)
      → connection.start()
      → consumer.receive(...) / listener.onMessage(...)
    → ack/commit/rollback according to mode
  → close Session
→ close Connection
~~~

**Note:** Sending is valid before `connection.start()`; `start()` primarily enables **receiving** messages. Registering listeners before starting helps avoid receiving messages before setup is complete. `Session.createQueue("name")` creates a destination-name reference object; it is **not a JMS administrative standard for physically creating queues on the broker**. Whether the broker auto-creates queues depends on configuration.

In Java 17+, `Connection`, `Session`, `MessageProducer`, and `MessageConsumer` all implement `AutoCloseable`; use `try-with-resources` when your application owns them. Closing a session closes its child resources; closing a connection also closes its associated sessions. With Spring, never manually close a session managed by `JmsTemplate` or a listener container.

### 5.1. Errors When Closing Mid-Callback

If currently executing `onMessage`, avoid calling `session.close()` directly from within the callback itself. The resource may be managed by the provider/container, and closing before the callback returns can have implementation-dependent results. Let the container stop intake, wait for running tasks, and close resources per the configured lifecycle.

### 5.2. Connections Can Be Reused; Sessions Must Have Ownership

A service may share a `ConnectionFactory`, and sometimes share connections managed by the provider/pool, but each session must be treated as **an exclusive unit of ownership** while in use. Pooling/caching only reuses a session after it has been returned; it never hands the same active session to two threads simultaneously.

## 6. `JMSContext`: Simplified API Still Enforces Threading Limits

Jakarta Messaging 2.0+ adds the simplified API. `JMSContext` implicitly combines creating a connection and a session, offering `createProducer()`, `createConsumer()`, `commit()`, `rollback()`, `acknowledge()`, and `close()`.

~~~java
// Illustrative code inside a method with a valid ConnectionFactory.
// Use context exclusively in the current thread; requires broker to provide the queue.
try (JMSContext ctx = connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
    Queue q = ctx.createQueue("lesson.context");
    try (JMSConsumer consumer = ctx.createConsumer(q)) {
        ctx.createProducer().send(q, "hello");
        String payload = consumer.receiveBody(String.class, 5_000);
        if (payload == null) {
            throw new IllegalStateException("Timed out waiting for message");
        }
        System.out.println(payload);
    }
}
~~~

This is a **snippet inside a method with `jakarta.jms.*` properly configured/imported**, not a standalone program. By default, `JMSContext` automatically starts the connection when a consumer is created under the simplified API; therefore calling `ctx.start()` is not mandatory in the example above.

Do not store `JMSContext` in a singleton for concurrent HTTP request threads to share. Each unit of work should have its own context/session owned by it or allocated by the framework.

**Specification exception:** `JMSContext.createContext(...)` creates another context without using the current context's underlying session; therefore that method is not subject to the same threading restriction as session operations. Resource-closing methods for the context/consumer also have exceptions to support shutdown. These are narrow exceptions, **not** a general thread-safety guarantee for `JMSContext`.

## 7. Mapping to Spring Framework JMS

Spring JMS lets applications focus on business logic and manages acquiring/releasing resources automatically. However, Spring **does not change the JMS Session threading rules**.

### 7.1. `JmsTemplate` Can Be a Thread-Safe Singleton

`JmsTemplate` is designed to be **thread-safe once configured**. It holds a reference to `ConnectionFactory` and its settings; each operation acquires the proper JMS resources and closes/returns them according to context.

~~~java
// Inside a Spring bean with JmsTemplate injected:
jmsTemplate.convertAndSend("lesson.queue", "payload");
~~~

Multiple threads can call `jmsTemplate.convertAndSend(...)` concurrently. This **does not mean** multiple threads share an active `Session`: the template, container, and transaction manager are responsible for supplying appropriate sessions.

Template callbacks must also respect proper scoping:

~~~java
// Spring manages the Session for the duration of this callback.
jmsTemplate.execute(session -> {
    Queue queue = session.createQueue("lesson.queue");
    try (MessageProducer producer = session.createProducer(queue)) {
        producer.send(session.createTextMessage("inside-callback"));
    }
    return null;
});
~~~

This is illustrative code inside a class with `JmsTemplate` injected and `jakarta.jms.Queue`, `jakarta.jms.MessageProducer` imported. **Do not** store `session` in a field or static variable, pass it across a work queue, or use it after the callback ends. Spring may close the session or return it to a cache/pool.

### 7.2. `@JmsListener` and Listener Containers

`@JmsListener` is placed on a message-handling method. `DefaultMessageListenerContainer` and Spring's other listener containers are responsible for creating consumers and sessions, managing workers, handling errors, and managing lifecycle.

~~~text
DefaultMessageListenerContainer (concurrency = 3, queue example)
   ├─ invoker #1 / Session #1 → listenerBean.handle(M1)
   ├─ invoker #2 / Session #2 → listenerBean.handle(M2)
   └─ invoker #3 / Session #3 → listenerBean.handle(M3)
                                 ^
             The same listener bean can be invoked concurrently!
~~~

An often overlooked point: within one session, callbacks are sequential; **the same bean instance** (singleton by default) can receive calls from **multiple sessions** simultaneously. Therefore the listener method must be **thread-safe with respect to application state**: prefer local variables, thread-safe dependencies, properly scoped transactions, and avoid shared mutable fields.

Wrong example:

~~~java
// Wrong if the listener runs concurrently: shared field is overwritten.
private String currentOrderId;

@JmsListener(destination = "lesson.orders", concurrency = "3")
public void handle(String orderId) {
    currentOrderId = orderId;
    process(currentOrderId);
}
~~~

Fix:

~~~java
// Each invocation immediately processes its own parameter.
@JmsListener(destination = "lesson.orders", concurrency = "3")
public void handle(String orderId) {
    process(orderId);
}
~~~

These two snippets are **abbreviated examples**, assuming the bean has a `process(String)` method. They illustrate bean thread-safety, not standalone Java files.

**Note on increasing concurrency:** For queues, multiple consumers are typically used to distribute load. For a non-shared Topic, increasing consumers/subscriptions may create duplicate deliveries on the same node; verify topic semantics, shared/durable subscriptions, and provider behavior before increasing `concurrency`.

### 7.3. Spring `SessionAwareMessageListener`

When a listener needs to send a reply in the **same session** used for receiving, Spring provides the `SessionAwareMessageListener` interface with `onMessage(Message message, Session session)`. The provided session is strictly for use **inside the callback that owns it**; do not hand it off to an executor and do not close it manually.

Using `SessionAwareMessageListener` is appropriate when fine-grained JMS operations are needed, while `@JmsListener` suits most payload-receiving business logic.

### 7.4. Transactions Bound to the Current Thread

`JmsTransactionManager` manages local transactions for a `ConnectionFactory`, binding a JMS session to **the thread participating in the transaction** so `JmsTemplate` can reuse the same transactional session. When finished, the resource is released/returned. It **does not automatically propagate the transaction** to a new thread when you call `CompletableFuture.supplyAsync`, `new Thread`, or another executor.

A listener container with `sessionTransacted = true` can roll back receipt if the listener throws an exception, after which the broker redelivers according to policy. A JMS transaction **does not automatically cover a database**. If cross-resource atomicity is required, design properly configured JTA/XA or an outbox with idempotency.

**Do not assume** `@Transactional` with an arbitrary transaction manager automatically covers both JMS and JDBC. Know specifically which transaction manager is selected and which resources participate.

### 7.5. Caching and Pooling

`CachingConnectionFactory` can cache `Connection`, `Session`, `MessageProducer`, and `MessageConsumer` to avoid repeated creation overhead; this is **sequential reuse when resources are idle**, and does not make a Session thread-safe. Listener containers also have their own caching depending on settings. Do not stack redundant caching layers without understanding ownership, recovery, transactions, and session cache size.

If optimization is needed, observe active sessions, concurrent consumers, processing times, redeliveries/DLQ, and backlog before increasing pool sizes. A single session with multiple consumers still will not yield parallel callbacks.

## 8. Complete Example: Java 17 + Spring Boot + Artemis

The following example demonstrates three distinct patterns:

1. One thread owning a **plain JMS Session** to send and then receive synchronously.
2. One thread owning a **`JMSContext`** inside `try-with-resources`.
3. Spring `JmsTemplate` sending a message while a listener container manages **multiple sessions** and invokes a bean method.

The demo project uses **Java 17**, **Maven**, and **Spring Boot 3.5.5**. It requires a **running ActiveMQ Artemis broker on `localhost:61616`** that permits creating/accessing the example queues; adjust username/password to match your broker. This application runs once the provider is prepared; it is not a brokerless JMS demo.

Structure:

~~~text
session-thread-demo/
├── pom.xml
└── src/main/
    ├── java/example/SessionThreadDemoApplication.java
    └── resources/application.properties
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>session-thread-demo</artifactId>
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
~~~

`src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

These are merely illustrative settings for a local broker; update credentials to match your real broker and use secret management in production environments.

`src/main/java/example/SessionThreadDemoApplication.java`:

~~~java
package example;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SessionThreadDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionThreadDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ConnectionFactory connectionFactory,
                           JmsTemplate jmsTemplate) {
        return args -> {
            // 1. A Session is used only by the current thread.
            try (Connection connection = connectionFactory.createConnection();
                 Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE)) {

                Queue queue = session.createQueue("lesson.session.sync");

                try (MessageProducer producer = session.createProducer(queue);
                     MessageConsumer consumer = session.createConsumer(queue)) {

                    producer.send(session.createTextMessage("hello-session"));
                    connection.start(); // Required for receiving messages.

                    Message received = consumer.receive(5_000);
                    if (!(received instanceof TextMessage text)) {
                        throw new IllegalStateException(
                            "Did not receive JMS TextMessage within 5 seconds");
                    }
                    System.out.println("Session: " + text.getText());
                }
            }

            // 2. JMSContext is also used only within the current thread.
            try (JMSContext context = connectionFactory.createContext(
                    JMSContext.AUTO_ACKNOWLEDGE)) {

                Queue queue = context.createQueue("lesson.context.sync");
                try (JMSConsumer consumer = context.createConsumer(queue)) {

                    context.createProducer().send(queue, "hello-context");
                    String text = consumer.receiveBody(String.class, 5_000);

                    if (text == null) {
                        throw new IllegalStateException(
                            "Did not receive JMSContext message within 5 seconds");
                    }
                    System.out.println("JMSContext: " + text);
                }
            }

            // 3. JmsTemplate can be reused across multiple Spring beans/threads.
            jmsTemplate.convertAndSend("lesson.spring.listener", "hello-spring");
        };
    }

    @Bean
    DefaultJmsListenerContainerFactory lessonListenerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("2");
        factory.setSessionTransacted(true);
        return factory;
    }

    @JmsListener(destination = "lesson.spring.listener",
                 containerFactory = "lessonListenerFactory")
    public void handle(String payload) {
        // Do not use shared mutable fields; each invocation uses only the payload.
        System.out.println("Spring listener: " + payload);
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

With a fresh broker / empty queues, the three lines printed by the program typically look like:

~~~text
Session: hello-session
JMSContext: hello-context
Spring listener: hello-spring
~~~

Spring Boot also prints startup logs; the thread executing the Spring listener is container-managed, so **absolute ordering relative to other logs is not guaranteed**. If a queue holds leftover messages, another consumer is attached, or the broker does not auto-create queues, the output may differ or the demo may fail to receive the expected message. Use dedicated destinations for exercises when testing.

**Part-by-part explanation:**

- `connection.createSession(Session.AUTO_ACKNOWLEDGE)` supplies a session. `producer` and `consumer` share the session, but the runner operates **sequentially** on a single thread.
- Calling `producer.send(...)` before `connection.start()` is valid; `start()` enables receiving.
- `consumer.receive(5_000)` waits at most ~5 seconds and returns `null` on timeout; the program checks both null and unexpected message type cases.
- `JMSContext` combines connection+session, and `context.createConsumer(...)` enables connection auto-start per the simplified API.
- `JmsTemplate` acquires appropriate resources for the send call; it does not turn into a shared `Session` stored in a field.
- `factory.setConcurrency("2")` lets the container run two listener consumers/sessions for the queue; they can process concurrently. `setSessionTransacted(true)` enables rollback/redelivery when the listener fails according to provider configuration.
- `handle` holds no mutable state on the bean. If two messages arrive close together, invocations on the same bean instance can run in parallel.

**What the example does not demonstrate:** It does not prove business exactly-once delivery, does not automatically create a DB transaction, does not automatically handle retries/DLQ, and does not guarantee both listener instances stay busy on a single message. To observe concurrency clearly, send multiple messages and log thread names with timestamps, while **not relying on stdout ordering** to infer global system processing order.

## 9. Anti-Patterns to Avoid

### 9.1. Storing a Session as a Field in a Spring Singleton

~~~java
// BROKEN OWNERSHIP CODE — for error identification only.
@Service
class UnsafeSender {
    private final Session sharedSession;

    UnsafeSender(Session sharedSession) {
        this.sharedSession = sharedSession;
    }

    void send(String text) throws JMSException {
        MessageProducer producer = sharedSession.createProducer(
            sharedSession.createQueue("orders"));
        producer.send(sharedSession.createTextMessage(text));
    }
}
~~~

When two requests call `send` simultaneously, the session is used concurrently. This snippet illustrates the anti-pattern (assuming a Session bean were supplied), not a standalone program. Replace it with a singleton `JmsTemplate` calling `convertAndSend`, or create a dedicated session per owning thread.

### 9.2. Handing Off a Session from a Listener to an Executor

~~~java
// WRONG CODE — do not pass Session to a worker thread.
public void onMessage(Message message, Session session) {
    executor.submit(() -> {
        session.commit(); // Wrong: using Session from another thread.
    });
}
~~~

If time-consuming work must run asynchronously, design an explicit job/task structure. Do not ack/commit a message before knowing the outcome, and do not let the listener return while expecting a callback on another worker thread to still have valid rights over the same session. For broker-driven concurrency, increasing the number of sessions managed by the listener container is usually simpler and semantically sound.

### 9.3. Keeping a Message or Producer After the Session Closes

Producers and consumers are owned by the session. After the session/connection closes, do not reuse previously created producers/consumers. Some message contents may remain readable after closing, but calling `acknowledge()` on a message belonging to a closed session is invalid.

### 9.4. Treating `synchronized` as a Default Fix

~~~java
synchronized (sharedSession) {
    sharedSession.commit();
}
~~~

A lock only serializes threads that **also acquire that same lock**. It does not control provider callbacks, does not fix ownership of a listener-managed session, and does not prevent a commit from affecting messages received for other work. The proper design is one owner per session or one session per worker, rather than arbitrarily sharing JMS state.

### 9.5. Assuming `@JmsListener(concurrency = "5")` Guarantees Ordering

Multiple sessions can process concurrently and finish out of order. For per-`accountId` or per-`orderId` requirements, check whether the broker supports partitioning/grouping, message groups, consumer count constraints, business locks, or explicit sequencing. JMS does not define global ordering across multiple concurrent sessions.

### 9.6. Believing AUTO_ACK and Transactions Guarantee Every Side Effect Runs Once

A listener may call an external service successfully and then the JVM crashes before JMS commits. The message can be redelivered; without idempotency, the system sends duplicate emails, charges twice, or saves duplicate data. Design around the failure window rather than relying solely on acknowledgment mode.

## 10. Quick Decision Table

| Need | Appropriate Session Usage | Why |
|---|---|---|
| One thread sending multiple messages sequentially | One session owned for the scope of the work, or `JmsTemplate` | Avoids overhead and improper resource management. |
| Many HTTP requests concurrently sending JMS messages | Configured singleton `JmsTemplate` | The template is thread-safe; acquires/returns sessions automatically. |
| One consumer pulling messages with `receive()` | Dedicated session for the polling thread; set a sensible timeout | No overlapping method calls on the session. |
| Parallel processing of many messages from a queue | Multiple listener invokers, each using its own session | Enables concurrency while respecting session boundaries. |
| Listener needs to send a reply in the same JMS transaction | Use the current session **inside the callback** or configure Spring JMS transactions | Shares the JMS transaction; do not hand the session to another thread. |
| Combining JMS with a database | Idempotency/outbox, or JTA/XA where appropriate | Session local transactions cover only JMS. |
| Reusing resources to reduce overhead | Properly configured container/pool/cache | Sessions are reused only when no longer in active use. |
| Keeping all messages in business order | Define ordering scope, limit concurrency, or use broker grouping mechanisms | Ordering across multiple sessions is not preserved automatically. |

## 11. Production Design and Observability Checklist

Before putting a JMS consumer into production, verify:

1. **Ownership:** who creates the session, who closes it, and which listener/container holds it? Are there any static/singleton fields storing `Session`, `JMSContext`, `MessageProducer`, or `MessageConsumer` directly?
2. **Thread model:** can a session be touched by an executor, virtual thread, request thread, or out-of-context callback? Does any listener bean have mutable shared fields?
3. **Delivery model:** are you using polling `receive()`, provider `MessageListener`, or Spring `@JmsListener`? Are modes accidentally mixed on the same session?
4. **Ack/transaction:** which mode is active? Could `CLIENT_ACKNOWLEDGE` unintentionally acknowledge multiple messages in the same session? Which local transactions guarantee atomicity, and which resources lie outside the transaction?
5. **Failure/replay:** if processing succeeds but ack/commit fails, are side effects duplicated? How are retry/backoff/DLQ configured on the broker and container?
6. **Concurrency and ordering:** how many active sessions does each listener have? Does instance count alter processing order? Do Queue/Topic and durable/shared subscription semantics fit?
7. **Lifecycle:** on application shutdown, can callbacks be mid-flight or `receive()` blocking? Does the container perform graceful stop and avoid closing resources from the wrong thread?
8. **Observability:** collect backlog/queue depth, active consumers, processing duration, listener errors, redelivery counts, transaction rollbacks, and DLQ counts; do not monitor only successful send counts.

### How to Reproduce Issues Yourself

- Run a listener container with concurrency 1, send multiple messages, and make the listener slow: within the same invoker/session, callbacks will not overlap.
- Increase concurrency to 2 or 3 on a **queue**, send enough messages, and observe multiple invokers running in parallel: the invokers use different sessions; stdout order can change.
- Create an isolated test with `CLIENT_ACKNOWLEDGE`: receive two messages in the same session, ack the second message, and observe the ack effect across the entire session. Never test this on a production queue because it alters real delivery state.
- Force a listener to throw an exception with `sessionTransacted=true` to observe rollback/redelivery; configure retry/DLQ and an attempt limit to prevent infinite loops.

## 12. Self-Check Questions

**1. A Connection has two Sessions; can they receive messages in parallel?** Yes. The single-thread rule applies **per session**, not forcing all sessions on a connection onto one thread.

**2. A Session has two MessageConsumers with two MessageListeners; do their callbacks run concurrently?** No. Callbacks delivered through the same session must be serialized.

**3. With a singleton `JmsTemplate`, do concurrent requests calling `convertAndSend` violate the rule?** No, provided the template is properly configured; Spring manages JMS resources per operation.

**4. Can a singleton `@JmsListener` bean configured with concurrency 4 be invoked concurrently?** Yes. Four distinct sessions/invokers can call the same bean in parallel, so bean state must be thread-safe.

**5. Why is `message.acknowledge()` in CLIENT_ACKNOWLEDGE not a per-message ack?** Because acknowledgment is defined per **session**, covering all messages delivered in that session.

**6. Can `JMSContext` be shared across threads because its API looks simpler than Session?** No. It wraps an underlying session and is subject to the same threading restrictions, except for specific methods explicitly noted by the specification.

**7. Why should a listener callback not submit `session.commit()` to an executor?** The session has ownership and transaction state bound to the control thread processing the message; another executor thread has no right to use it concurrently.

**8. Does a JMS rollback undo an independent DB INSERT statement?** No. Proper transaction coordination or an idempotency/outbox design is required.

## 13. Official References for Verification

- [Jakarta Messaging 3.1 specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — especially sections **6.2.5** (threading restrictions on Session), **6.2.6** (JMSContext), **6.2.7** (transactions), **6.2.10** (acknowledgement), and **6.2.13–14** (serial/concurrent delivery).
- [Jakarta JMS Session API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session) — resources, ack modes, and lifecycle.
- [Jakarta JMS MessageListener API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messagelistener) — session-serialized callbacks.
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — thread-safe `JmsTemplate`, caching, and transaction managers.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html) — listener containers, `SessionAwareMessageListener`, and local transactions.
- [Spring Boot — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/) — Spring Boot configuration, `JmsTemplate`, and `@JmsListener`.

**Core takeaway:** `Session` is a *delivery and transaction state unit* with sequential ownership. **One session → one thread of control at a time; multiple sessions → concurrent processing capability.** Spring provides templates and listener containers to enforce this rule without business code having to share sessions manually.
