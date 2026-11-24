# SessionAwareMessageListener and Accessing Session in Spring JMS

## 1. Problem: A Listener Sometimes Needs More Than Just a Message

In Spring JMS, a listener receives messages from a queue or topic. For tasks that only log or pass the content to the business layer, the standard **`jakarta.jms.MessageListener`** interface is usually enough: the `onMessage(Message)` method receives only the message.

However, when the handler needs to **create a response** to `JMSReplyTo`, construct a special JMS message type, or use methods on `jakarta.jms.Session` **directly during processing**, a single message alone may not suffice. Spring Framework provides the **`org.springframework.jms.listener.SessionAwareMessageListener<M extends Message>`** interface, passing both the **received message** and the **JMS Session** managed by the listener container.

API signature in Spring Framework 6.x:

```java
package org.springframework.jms.listener;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Session;

@FunctionalInterface
public interface SessionAwareMessageListener<M extends Message> {
    void onMessage(M message, Session session) throws JMSException;
}
```

*This is an API signature description for learning, not a file to write yourself in the project.* `M` is the message type (e.g., `Message`, `TextMessage`); `Session` is the Jakarta Messaging object. In Spring Framework 6+ / Spring Boot 3+, imports must use `jakarta.jms.*` and never mix with legacy `javax.jms.*`.

**Most important point:** `SessionAwareMessageListener` allows **using the container-provided Session within the callback scope**; it does not mean the developer **owns** it, closes it manually, commits it manually, or retains that Session long-term. The listener container still manages lifecycle, transactions, and concurrency.

### 1.1. Processing diagram

```text
JMS Broker / requests.queue
             │
             ▼
DefaultMessageListenerContainer
   ├─ obtains Connection from ConnectionFactory
   ├─ uses Session to create MessageConsumer
   ├─ receive() a Message
   │
   ▼
SessionAwareMessageListener.onMessage(message, session)
   ├─ validates message type and schema
   ├─ executes business logic
   ├─ request.getJMSReplyTo()
   ├─ session.createTextMessage("ACK:...")
   ├─ session.createProducer(replyTo).send(reply)
   └─ returns or throws exception
             │
             ▼
Container handles commit / rollback / ack / cleanup
             │
             └──────► Broker delivers reply
```

If `sessionTransacted=true` and the listener's Session is exposed, **receiving the message and sending the reply through the same Session** occur within **one local JMS transaction**. When the callback succeeds, the container can commit; when the callback fails, the transaction is rolled back per configuration. This **does not automatically make database operations** inside the callback part of the JMS transaction.

## 2. Comparing MessageListener, SessionAwareMessageListener, and @JmsListener

| Criterion | `jakarta.jms.MessageListener` | Spring `SessionAwareMessageListener` | Spring `@JmsListener` |
| --- | --- | --- | --- |
| Origin | Standard Jakarta Messaging API | Spring-specific interface | Spring annotation + adapter |
| Handler signature | `onMessage(Message)` | `onMessage(M, Session)` | Arbitrary method, e.g., `handle(String)` |
| Receives Session directly | Not through signature | Yes, second parameter | **Yes**, when method declares `jakarta.jms.Session` |
| Checked JMSException | Not declared on standard `onMessage` | Allows `throws JMSException` | Handler method may declare exceptions |
| Automatic payload conversion | No, read raw Message manually | No, read raw Message manually | Possible via `MessageConverter` and argument resolvers |
| Automatic response sending | No | No, must send manually or use custom logic | Can auto-send from return value with `JMSReplyTo` / `@SendTo` |
| Spring dependency | No, portable interface | Yes | Yes |
| Typical scenario | Raw JMS processing needing portability | Raw JMS processing **and operating on the same Session** | Everyday business listeners |

### 2.1. Standard MessageListener

```java
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import jakarta.jms.TextMessage;

class PlainListener implements MessageListener {
    @Override
    public void onMessage(Message message) {
        try {
            if (!(message instanceof TextMessage text)) {
                throw new IllegalArgumentException("Expected TextMessage");
            }
            System.out.println(text.getText());
        } catch (jakarta.jms.JMSException ex) {
            throw new IllegalStateException("Cannot read JMS message", ex);
        }
    }
}
```

This snippet is an illustrative class, not registered with a container. `MessageListener.onMessage` **does not declare `throws JMSException`**, so the example catches checked `JMSException` and converts it to unchecked. If a response must be sent, the handler needs another `ConnectionFactory`/`JmsTemplate` source or a framework adapter to send; the signature receiving only Message does not provide a Session.

### 2.2. Spring SessionAwareMessageListener

```java
import jakarta.jms.Message;
import jakarta.jms.Session;
import jakarta.jms.JMSException;
import org.springframework.jms.listener.SessionAwareMessageListener;

class SessionAwareHandler implements SessionAwareMessageListener<Message> {

    @Override
    public void onMessage(Message message, Session session)
            throws JMSException {
        // message: the message received by the container.
        // session: the current Session provided by the container.
        // Process and optionally create a response using session.createTextMessage(...).
    }
}
```

The callback can declare `throws JMSException`; the container handles errors and ack/transaction boundaries per configuration. **Do not swallow errors and `return` as if processing succeeded** if you want the broker to redeliver on failure.

### 2.3. @JmsListener can also receive Session

Spring Framework 6.x supports `jakarta.jms.Session` as an injected argument for annotation-driven methods:

```java
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;

@JmsListener(destination = "demo.requests")
public void handle(TextMessage request, Session session)
        throws JMSException {
    // Use request and Session provided by the listener adapter/container.
}
```

This is a method fragment meant to be placed in a Spring-managed bean, **not a standalone application**. With `@JmsListener`, the underlying adapter infrastructure supplies raw Message/Session when needed; **it is not mandatory to directly implement** `SessionAwareMessageListener`. If the Session API is not needed, a `@JmsListener` method taking a DTO/String is usually cleaner.

**Which approach to choose?** Use `@JmsListener` for most modern consumers; use `SessionAwareMessageListener` when you want direct control over the raw JMS API and explicit registration with `DefaultMessageListenerContainer` or `SimpleMessageListenerContainer`. Avoid mixing two listeners consuming the same demo queue because they will become competing consumers.

## 3. What Actually Is the Passed-in Session?

`jakarta.jms.Session` in the classic JMS API is a **sequential operational context** for:

- Creating `TextMessage`, `BytesMessage`, `MapMessage`, `StreamMessage`, `ObjectMessage`.
- Creating `Queue`/`Topic` objects from names or creating `TemporaryQueue`/`TemporaryTopic` when appropriate.
- Creating `MessageProducer`/`MessageConsumer` for destinations.
- Performing operations tied to the session's transaction/acknowledgement mode.
- Preserving the ordering of operations using the same session per JMS semantics.

Commonly seen methods:

```java
// Code snippet inside a callback that has jakarta.jms.Session session:
TextMessage reply = session.createTextMessage("ACK:order-42");
MessageProducer producer = session.createProducer(replyTo);
producer.send(reply);
producer.close();
```

The methods above are Jakarta JMS API. With Spring Boot 3+, use `jakarta.jms.Session`, not `org.hibernate.Session`, not an HTTP Session, and not Spring `WebSession`.

### 3.1. Session is scoped, not a shared singleton

Each listener invocation is given an appropriate session by the container. Depending on the container/concurrency, the session may be **reused** across invocations on the same consumer thread or newly created according to caching strategy. Therefore:

- Do not store the session in a static field or singleton service.
- Do not pass the session to a `CompletableFuture`, thread pool, or reactive pipeline for use after `onMessage` returns.
- Do not use one session concurrently from multiple threads; a JMS Session is fundamentally a single-threaded context.
- Do not close the container-provided session inside the callback.
- Do not call `session.commit()` or `session.rollback()` manually if the **container** manages the transaction. Commit/rollback behavior must follow a single clear owner.
- Producers/consumers **created manually** inside the callback must be properly closed when finished, e.g., with `try-with-resources`; do not confuse closing a producer with closing the session.

### 3.2. Resource ownership table

| Resource | Who manages it in the listener? | Should you call `close()` manually? |
| --- | --- | --- |
| `ConnectionFactory` | Spring Boot/provider/application | Not from callback |
| `Connection` | Listener container / infrastructure | No |
| `Session` passed to `onMessage` | Listener container | **No** |
| Container's `MessageConsumer` | Listener container | No |
| `MessageProducer` created via `session.createProducer(...)` | Created directly by callback | **Yes**, after send |
| `TextMessage` created via `session.createTextMessage(...)` | Session creates data object | Has no separate close |
| Another standalone manually created `JMSContext` | Manually created code | Yes, if truly needed, but avoid unintentionally splitting transactions |

Even though the callback has a `Session` parameter, do not assume you are writing code that owns the raw JMS `Connection`. This session may be inside a local/JTA transaction or wrapper; improper manual closing can break container commit/rollback, redelivery, and shutdown.

## 4. Configuring the Listener Container to Expose Session

Spring Framework has at least two commonly used listener containers:

- `DefaultMessageListenerContainer` (**DMLC**): uses a `MessageConsumer.receive()` loop, offers recovery/concurrency and flexible transaction support; suitable for many production applications.
- `SimpleMessageListenerContainer` (**SMLC**): uses `MessageConsumer.setMessageListener()`; simpler structure but fewer scheduling/recovery/transaction features than DMLC.

Both support `SessionAwareMessageListener` as a direct alternative to standard `MessageListener`. **Some JCA-based endpoint containers do not support this proprietary interface in the same way**, so if maximum portability across application servers/resource adapters is required, consider standard `MessageListener` or `@JmsListener` as appropriate.

### 4.1. Configuring DMLC via Java @Bean

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.SessionAwareMessageListener;

@Bean
DefaultMessageListenerContainer sessionContainer(
        ConnectionFactory nativeConnectionFactory,
        SessionAwareMessageListener<Message> listener) {
    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(nativeConnectionFactory);
    container.setDestinationName("demo.requests");
    container.setMessageListener(listener);
    container.setExposeListenerSession(true);
    container.setSessionTransacted(true);
    container.setConcurrentConsumers(1);
    return container;
}
```

**This is a configuration method fragment**; it requires `ConnectionFactory` and listener beans to be declared and wired properly. In a Spring Boot application using `CachingConnectionFactory`, the listener container should usually receive the **native ConnectionFactory** so it has authority over its own connection/recovery management. The full project in section 8 uses `ConnectionFactoryUnwrapper.unwrapCaching(...)` to handle this.

Important settings:

- `setMessageListener(listener)` registers the raw handler; if not registered, the callback is never called.
- `setDestinationName(...)` selects the queue name (by default DMLC uses point-to-point/queue); topics require configuring the pub-sub domain.
- `setExposeListenerSession(true)` requests exposing the **listener Session** to the callback; by default Spring already sets this to `true`. Set explicitly in the demo to show its meaning.
- `setSessionTransacted(true)` enables a local JMS transaction when there is no external transaction manager.
- `setConcurrentConsumers(1)` keeps the demo to one consumer; increasing concurrency requires a thread-safe handler because the container may call the same listener bean from different threads.

### 4.2. `exposeListenerSession=true` vs `false`

According to Spring `AbstractMessageListenerContainer`:

| `exposeListenerSession` | Session passed to callback | Practical meaning |
| --- | --- | --- |
| `true` (default) | Reuses the message-receiving session | Replies sent via this session can participate in **the same local JMS transaction** |
| `false` | May provide **a new session** obtained from the same connection | Useful with certain providers that have limitations, but receipt/reply cannot be assumed to share a transaction |

If the provider requires a separate session for outbound replies, evaluate transaction behavior before setting `false`. With `JmsTemplate` invoked **inside** a listener, Spring also has a mechanism to expose thread-bound resources depending on transaction/config; to guarantee using the callback's exact session in this lesson, the simplest approach is to **use the passed-in `Session session` directly**, create a producer, and send the reply directly.

**Do not infer that `setExposeListenerSession(false)` merely "hides a parameter" without changing semantics.** It can affect transactions and resource ownership.

## 5. Sending Replies via the Provided Session: Standard Flow

One of the best-suited use cases for `SessionAwareMessageListener` is **request–reply**:

1. The producer sends a `TextMessage` to the request queue, attaching `JMSReplyTo` as a `Destination` and an application-defined `JMSCorrelationID`.
2. The container receives the request and invokes `onMessage(request, session)`.
3. The handler validates the message type, schema, `JMSReplyTo`, and correlation ID.
4. The handler processes the request.
5. Use **`session.createTextMessage(...)`** and **`session.createProducer(replyTo)`** to send the reply.
6. The handler closes the manually created producer and returns.
7. The container commits/acks or rolls back per configuration.

Example:

```java
import jakarta.jms.Destination;
import jakarta.jms.InvalidDestinationException;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageFormatException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.springframework.jms.listener.SessionAwareMessageListener;

class ReplyingListener
        implements SessionAwareMessageListener<Message> {

    @Override
    public void onMessage(Message incoming, Session session)
            throws JMSException {
        if (!(incoming instanceof TextMessage request)) {
            throw new MessageFormatException("Expected TextMessage request");
        }

        Destination replyTo = request.getJMSReplyTo();
        String correlationId = request.getJMSCorrelationID();

        if (replyTo == null) {
            throw new InvalidDestinationException("Missing JMSReplyTo");
        }
        if (correlationId == null || correlationId.isBlank()) {
            throw new MessageFormatException("Missing correlation ID");
        }

        String requestBody = request.getText();
        TextMessage response =
                session.createTextMessage("ACK:" + requestBody);
        response.setJMSCorrelationID(correlationId);

        try (MessageProducer producer = session.createProducer(replyTo)) {
            producer.send(response);
        }
    }
}
```

This is an **illustrative class that compiles when Spring JMS/Jakarta JMS dependencies are present**, but requires a container/broker/request producer to run the actual flow. `MessageProducer` is used in try-with-resources because Jakarta Messaging `MessageProducer` implements `AutoCloseable`. Closing the producer **does not close the Session**. Since `onMessage` declares `throws JMSException`, API exceptions can propagate for the container to handle.

### 5.1. Why use `JMSReplyTo` instead of guessing the queue?

`JMSReplyTo` is a header of type **`Destination`**, not a queue name string. If the request does not specify a reply destination, the responder cannot know where to reply in a standard way. A system-defined default reply destination can be chosen, but it must be a **clear business contract**.

`JMSCorrelationID` is echoed so the requester can match the response with the request. If both sides pick different conventions — e.g., the responder uses the request's `JMSMessageID` while the requester checks an application correlation ID — a mismatch occurs. Agree on this before implementation.

### 5.2. Why not create a new ConnectionFactory inside onMessage?

The following approach is **unnecessary and can be transactionally wrong**:

```java
// ANTI-PATTERN: shown to be avoided.
Connection anotherConnection = connectionFactory.createConnection();
Session anotherSession =
        anotherConnection.createSession(false, Session.AUTO_ACKNOWLEDGE);
// Sending reply on another session and closing connection.
// The send does not automatically share a transaction with the listener's receipt!
```

Each callback already has a Session from the container. Creating an independent connection/session increases overhead and may create a separate transaction; if the worker fails after sending the independent reply, the requester may observe a "successful" response while receipt is rolled back and the request is redelivered. For atomic local JMS receive+reply, use **the same transacted session**.

## 6. Transactions and Acknowledgements: Clear Boundaries

### 6.1. When `sessionTransacted=true`

With DMLC using a local JMS transaction, the flow is:

```text
Broker                      Listener container / Session                  Broker
   │                                  │                                     │
   ├── request delivery ─────────────>│                                     │
   │                            onMessage(request, session)                │
   │                                  ├─ validate / calculate reply        │
   │                                  ├─ session.createProducer(replyTo)    │
   │                                  ├─ producer.send(response) ─────────>│
   │                                  │   not visible outside txn yet       │
   │                                  └─ return normally                    │
   │                                  │                                     │
   │                          container commits local JMS transaction       │
   │                          ┌─────────────┴──────────────┐                │
   │                          ▼                            ▼                │
   │                   request is acked            reply is published       │
   │                                                                       │
   └───────────────────── on error: rollback receipt/reply ─────────────────┘
```

If `onMessage` throws `JMSException` or a runtime exception that the container treats as processing failure, the transaction is rolled back; the request can be redelivered per broker policy. The reply sent on the same session is also rolled back. This is why `SessionAwareMessageListener` is useful when you want **receive and reply in the same local JMS transaction**.

**Warning:** a local JMS transaction does not cover database or HTTP side effects. If the handler already updated the DB and then the JMS transaction rolls back, the DB may already be committed while the request is redelivered. You need an idempotency key, dedup/outbox, or properly configured JTA/XA if distributed transactions are required; adding `sessionTransacted=true` alone does not give end-to-end exactly-once semantics.

### 6.2. When the session is not transacted

In `AUTO_ACKNOWLEDGE`, the message may be acknowledged after `receive()` returns successfully or per provider/container behavior before business code completes; thus you should not assume an exception in business code always forces broker redelivery. `CLIENT_ACKNOWLEDGE` has different semantics, and calling raw `message.acknowledge()` at the wrong time can also acknowledge multiple messages received on the same session.

For critical business processing, **explicitly choose transactions and a redelivery policy** instead of relying on defaults. Spring Boot has the `spring.jms.listener.session.transacted` property, yet **if you create `DefaultMessageListenerContainer` manually as in this lesson**, calling `setSessionTransacted(true)` directly on the bean is what determines behavior for that container.

### 6.3. Who calls commit, rollback, and close?

| Operation | Where it should happen when DMLC manages the transaction |
| --- | --- |
| `session.createTextMessage(...)` | Inside the callback |
| `session.createProducer(replyTo)` | Inside the callback |
| `producer.send(reply)` | Inside the callback |
| `producer.close()` | At the end of the producer scope created by the callback |
| `session.commit()` | **Do not call manually** — the container/transaction manager coordinates it |
| `session.rollback()` | **Do not call manually** — signal failure via exception so the container rolls back |
| `session.close()` | **Do not call manually** — owned by the container |
| `connection.stop()/close()` | **Do not call manually** — owned by the container |

**Wrong** example:

```java
@Override
public void onMessage(Message msg, Session session) throws JMSException {
    // Processing...
    session.commit(); // Wrong responsibility if container already manages txn.
    session.close();  // Breaks container lifecycle / consumer.
}
```

A failing block that catches and ignores the exception can cause the container to commit/ack instead of retrying:

```java
// Do not do this:
try {
    processBusinessData();
} catch (RuntimeException ex) {
    log.warn("failed", ex);
    // Not rethrowing: the container may treat the callback as successful.
}
```

If an error is **permanent** such as an invalid schema, infinite retries also make no sense; you need a DLQ/quarantine policy and root-cause observability. Do not manually commit/rollback arbitrarily as a workaround.

## 7. Exception Handling and Concurrency

### 7.1. JMSException vs runtime exception

`SessionAwareMessageListener.onMessage` **is allowed to throw checked `JMSException`**, unlike standard `jakarta.jms.MessageListener.onMessage`. Errors may include:

- `MessageFormatException`: the message does not have the required type/format.
- `InvalidDestinationException`: the reply destination is missing/invalid.
- `JMSSecurityException`: the account lacks permission to send the reply.
- `JMSException`: provider/network/broker error.
- `IllegalArgumentException`/runtime exception: schema/business validation failure.

Do not treat all exceptions the same:

| Error category | How can it be handled? |
| --- | --- |
| Temporary network/broker error | Bounded retry + backoff per policy |
| Invalid JSON/schema or missing JMSReplyTo | Reject/quarantine/DLQ; avoid infinite retries |
| Unrecoverable business violation | Use error flow/DLQ per contract |
| Response timeout | Distinguish late replies from request retries |
| Duplicate/redelivery | Idempotent handler keyed by event/command ID |

With DMLC, the container provides exception-handling/recovery mechanisms; you still must configure broker policies, transactions, and monitoring. **Do not use unchecked exceptions as a substitute for an error strategy.**

### 7.2. Thread safety

A single listener bean can be invoked **concurrently** by DMLC if multiple consumers are configured. `SessionAwareMessageListener` does not automatically make a listener thread-safe:

- Prefer stateless handlers and inject thread-safe dependencies.
- Do not store the `Session`/`MessageProducer`/current message in shared fields.
- Do not use unsynchronized mutable `ArrayList`/counters across callbacks.
- If `concurrentConsumers` is increased, each callback gets an appropriate Session for its processing thread; do not share Sessions across threads.
- If ordering by business key is needed, design queue partitioning, `JMSXGroupID`, sequencing, or an appropriate broker policy rather than assuming a single listener bean is enough.

**Wrong** example:

```java
class UnsafeListener implements SessionAwareMessageListener<Message> {
    private Session lastSession; // Do not store callback resources in fields.

    @Override
    public void onMessage(Message msg, Session session) {
        this.lastSession = session;
        // Another thread may use the wrong session or one already out of scope.
    }
}
```

Note: configuring a single concurrent consumer **reduces** some race conditions in the lab, but does not guarantee a message will never be redelivered, never be duplicated, or preserve permanent ordering across failovers.

## 8. Runnable Demo: Spring Boot 3.5.7, Java 17+, Artemis, DMLC, and Same-Session Reply

Goal: build a **real SessionAware listener** instead of `@JmsListener` and register it with `DefaultMessageListenerContainer`; the requester uses `JmsTemplate.sendAndReceive(...)` to create a temporary reply queue and wait for the response. The handler uses **the exact Session provided by DMLC** to create a `TextMessage` and `MessageProducer`, then sends back a reply with the same application correlation ID.

Environment: Java 17+, Maven, Docker, and a local Apache ActiveMQ Artemis broker. The example uses Spring Boot 3.5.7 and the `jakarta.jms` namespace to avoid confusion with legacy APIs.

### 8.1. Start the local broker

```bash
docker run --rm -d --name jms-session-aware-broker \
  -p 127.0.0.1:61616:61616 \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  apache/artemis:latest-alpine
docker logs jms-session-aware-broker
```

Wait for the broker to become ready. These credentials are **for local lab use only**; production requires a secret manager, TLS, ACLs, and proper broker provisioning. Queue `demo.session.requests` relies on the demo broker's auto-create policy; in production, create and grant permissions explicitly.

### 8.2. Project structure

```text
session-aware-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── resources/application.properties
    │   └── java/com/example/jms/SessionAwareApplication.java
    └── test/
        └── java/com/example/jms/SessionAwareApplicationTest.java
```

### 8.3. Maven pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>session-aware-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

### 8.4. application.properties

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

# Timeout when the requester waits for a reply, not a transaction timeout.
spring.jms.template.receive-timeout=5s
```

These properties are for the Artemis lab; in production, do not commit real passwords. The example uses a non-transacted `JmsTemplate` for the requester (default), while the **DMLC responder** is explicitly configured with a local transaction in Java.

### 8.5. SessionAwareApplication.java — complete runnable code

```java
package com.example.jms;

import java.util.Objects;
import java.util.UUID;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import jakarta.jms.InvalidDestinationException;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageFormatException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.SessionAwareMessageListener;

@SpringBootApplication
public class SessionAwareApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionAwareApplication.class, args);
    }

    @Bean
    SessionAwareMessageListener<Message> responder() {
        return (incoming, session) -> {
            if (!(incoming instanceof TextMessage request)) {
                throw new MessageFormatException(
                        "Expected TextMessage request");
            }

            Destination replyTo = request.getJMSReplyTo();
            if (replyTo == null) {
                throw new InvalidDestinationException(
                        "Request has no JMSReplyTo");
            }

            String correlationId = request.getJMSCorrelationID();
            if (correlationId == null || correlationId.isBlank()) {
                throw new MessageFormatException(
                        "Missing JMSCorrelationID");
            }

            TextMessage response =
                    session.createTextMessage("ACK:" + request.getText());
            response.setJMSCorrelationID(correlationId);

            // Use the same Session provided by the container; do not create a new Connection.
            try (MessageProducer producer = session.createProducer(replyTo)) {
                producer.send(response);
            }
        };
    }

    @Bean
    DefaultMessageListenerContainer sessionAwareContainer(
            ConnectionFactory connectionFactory,
            SessionAwareMessageListener<Message> responder) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        // Boot may wrap the underlying factory in CachingConnectionFactory.
        // The listener container should manage connection/recovery itself.
        container.setConnectionFactory(
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        container.setDestinationName("demo.session.requests");
        container.setMessageListener(responder);
        container.setExposeListenerSession(true);
        container.setSessionTransacted(true);
        container.setConcurrentConsumers(1);
        container.setMaxConcurrentConsumers(1);
        return container;
    }

    @Bean
    CommandLineRunner runOnce(JmsTemplate template) {
        return args -> {
            String correlationId = "req-" + UUID.randomUUID();

            Message incoming = template.sendAndReceive(
                    "demo.session.requests",
                    session -> {
                        TextMessage request =
                                session.createTextMessage("order-42");
                        request.setJMSCorrelationID(correlationId);
                        return request;
                    });

            if (incoming == null) {
                throw new IllegalStateException("Reply timeout");
            }
            if (!(incoming instanceof TextMessage response)) {
                throw new IllegalStateException(
                        "Expected TextMessage response");
            }

            boolean matches = Objects.equals(
                    correlationId, response.getJMSCorrelationID());
            System.out.println("Reply: " + response.getText());
            System.out.println("Correlation matched: " + matches);

            if (!matches) {
                throw new IllegalStateException(
                        "Wrong response correlation ID");
            }
        };
    }
}
```

**Step-by-step breakdown:**

1. `responder()` returns a bean of type `SessionAwareMessageListener<Message>`; it receives both **JMS Message and Session** when invoked by DMLC, without using `@JmsListener`.
2. The method validates `TextMessage`, `JMSReplyTo`, and `JMSCorrelationID` before processing. If missing, it throws an exception so the listener transaction fails as configured.
3. `session.createTextMessage(...)` and `session.createProducer(replyTo)` use the exact **Session** provided by the container. `producer` is closed after sending; `session.close()` or `session.commit()` are never called.
4. `DefaultMessageListenerContainer` uses the native connection factory via `ConnectionFactoryUnwrapper.unwrapCaching(...)`, avoiding mistakenly using a cached connection wrapper as the listener lifecycle layer. This unwrapper class has been available since Spring Boot 3.4.x.
5. `setSessionTransacted(true)` ensures **receive+reply** share a local JMS transaction; `setExposeListenerSession(true)` ensures the callback receives that exact Session.
6. `CommandLineRunner` uses `JmsTemplate.sendAndReceive(...)` to automatically create a temporary reply queue, set `JMSReplyTo`, send the request, and wait for the reply. The request carries an application-generated correlation ID; the responder echoes it, and the caller verifies it.
7. DMLC is a Spring `SmartLifecycle` and starts during application context refresh before the runner in normal configuration; the broker must still be ready to process within 5 seconds.

**Do not add a `@JmsListener(destination="demo.session.requests")` to the demo project**; it would compete with DMLC for incoming requests. If you want to demonstrate annotation-driven listeners, use a separate project or replace the container rather than running two consumers on the same queue in parallel.

### 8.6. Running the application

```bash
mvn spring-boot:run
```

When the broker is ready and DMLC receives the message and sends the reply within the timeout, **the two lines printed by our code** are:

```text
Reply: ACK:order-42
Correlation matched: true
```

Spring Boot/Artemis also print startup logs; those lines are not fixed. The random UUID is not printed, only compared. If the broker is not ready or the responder fails, the program may throw `Reply timeout`, a JMS connection exception, or another broker error.

Stop the broker after the lab:

```bash
docker stop jms-session-aware-broker
```

**Example limitations:** both sending and replying occur in the same application for easy observation; in real systems, requester and responder may run in two separate JVMs. The example does not include TLS, production secret management, DB transactions, outbox, DLQ policies, or failover/duplicate testing. Expected output is derived from the code, not from an actual recorded run log.

## 9. Unit Test: Proving the Listener Uses the Passed-in Session

You can test the reply-sending logic **without a broker** using Mockito. The goal is to confirm that the listener creates the message/producer from the exact Session passed by the caller and closes its producer; this test **does not verify broker commit/rollback**, which requires an integration test with Artemis.

### 9.1. SessionAwareApplicationTest.java

```java
package com.example.jms;

import jakarta.jms.Destination;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.junit.jupiter.api.Test;
import org.springframework.jms.listener.SessionAwareMessageListener;
import jakarta.jms.Message;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class SessionAwareApplicationTest {

    @Test
    void replyUsesSuppliedSession() throws Exception {
        Session session = mock(Session.class);
        TextMessage request = mock(TextMessage.class);
        TextMessage response = mock(TextMessage.class);
        Destination replyTo = mock(Destination.class);
        MessageProducer producer = mock(MessageProducer.class);

        when(request.getText()).thenReturn("order-42");
        when(request.getJMSReplyTo()).thenReturn(replyTo);
        when(request.getJMSCorrelationID()).thenReturn("req-test");
        when(session.createTextMessage("ACK:order-42"))
                .thenReturn(response);
        when(session.createProducer(replyTo)).thenReturn(producer);

        SessionAwareMessageListener<Message> listener =
                new SessionAwareApplication().responder();
        listener.onMessage(request, session);

        verify(session).createTextMessage("ACK:order-42");
        verify(session).createProducer(replyTo);
        verify(response).setJMSCorrelationID("req-test");
        verify(producer).send(response);
        verify(producer).close();
    }
}
```

Run:

```bash
mvn test
```

The test only uses Mockito/JUnit from `spring-boot-starter-test`, creates no Spring context, and requires no broker. **Expected result:** the test passes if dependencies resolve and the code is correct. When you want to test atomic receipt/reply, implement an integration test with a real broker: trigger an exception before the callback returns and observe request redelivery and that the reply is not committed; configure retry limits and a DLQ so the test does not loop forever.

## 10. Combining with @JmsListener: Choosing the Right Interface

For new code, many applications use `@JmsListener` for concise syntax and built-in support for conversion, validation, `@Header`, `@Payload`, and return values. The handler signature can still receive a native Session:

```java
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class AnnotatedResponder {

    @JmsListener(destination = "demo.another.requests")
    public void handle(TextMessage request, Session session)
            throws JMSException {
        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            throw new IllegalArgumentException("Missing JMSReplyTo");
        }

        TextMessage reply =
                session.createTextMessage("ACK:" + request.getText());
        reply.setJMSCorrelationID(request.getJMSCorrelationID());

        try (MessageProducer producer = session.createProducer(replyTo)) {
            producer.send(reply);
        }
    }
}
```

This is a **separate illustrative class**, not part of the demo project in section 8. To use it, enable annotation endpoints (usually auto-configured by Boot, or `@EnableJms`) and an appropriate listener container factory.

Another option:

```java
@JmsListener(destination = "demo.another.requests")
public String handle(String payload) {
    return "ACK:" + payload;
}
```

The listener adapter can automatically convert the return value into a JMS reply when the request has `JMSReplyTo` (or a default reply destination/`@SendTo` per configuration). However, if you need control over raw JMS headers, reply message types, correlation conventions, or sending via **the exact Session** to join a local transaction, a Session parameter or direct callback makes the code clearer.

**Do not assume you must use the SessionAware interface whenever `Session` is needed.** The interface and the annotation are two ways of configuring a listener; the annotation ultimately can use an adapter that supports `SessionAwareMessageListener` at the framework layer.

## 11. Common Pitfalls When Accessing Session

| Pitfall | Impact | Fix |
| --- | --- | --- |
| Importing `javax.jms.Session` in Spring Boot 3 | Wrong Jakarta ecosystem, compile/compatibility errors | Use `jakarta.jms.*` |
| Using `jakarta.jms.MessageListener` and declaring `throws JMSException` | Does not match standard interface signature | Catch/translate exception or use SessionAware |
| Calling `session.close()` manually in callback | Container loses resource, consumer/transaction errors | Let the container manage Session lifecycle |
| Calling `session.commit()` manually while container manages txn | Breaks transaction boundary | Return/throw so container commits/rolls back |
| Creating another Connection to send reply | Reply may fall outside the receive transaction | Send via the supplied Session |
| Setting `setExposeListenerSession(false)` yet assuming reply shares txn | May use a new Session | Understand setting/provider; use `true` if same Session is needed |
| Sharing Session via field or another thread | Races, JMS IllegalStateException, broken lifecycle | Use only within the active callback/thread |
| Not closing manually created producer | Producer/resource leak depending on provider | Use try-with-resources for MessageProducer |
| Enabling multiple concurrent consumers with a stateful listener | Data races and unpredictable processing order | Stateless handler, idempotency, and concurrency testing |
| Swallowing exceptions after a DB error | Container assumes success, wrong ack/commit | Rethrow to roll back on retryable errors |
| Retrying malformed-schema messages forever | Poison message loop | DLQ/quarantine, classify permanent errors |
| Creating producer when `JMSReplyTo` is null | Unknown reply destination | Validate header or use fallback contract |
| Not echoing correlation ID | Requester cannot match response | Define and validate correlation convention |
| Using a fresh `JmsTemplate` inside callback assuming same Session | May obtain a different connection/session | Prefer the supplied Session directly or verify resource exposure |
| Mixing JMS local transaction with JDBC assuming atomicity | Dual-write; DB and JMS can diverge | Idempotency, outbox, or properly configured XA/JTA |

### 11.1. Why might a reply arrive while the request is redelivered?

If a reply is sent using an independent Session, the reply may commit while the request receipt rolls back. The requester receives `ACK` yet the broker redelivers the request, and the worker executes business logic again. If you want receive+reply in the same local JMS transaction, use the same Session with `sessionTransacted=true`. Even when both JMS operations commit together, **database side effects still require separate design**.

### 11.2. Why should you not retain a Session after the callback?

The container may return the Session to a pool/cache, reuse it, commit it, roll it back, or close it depending on lifecycle. An async task holding a reference could use a Session belonging to another message, already closed, or actively used by another thread. If long-running work is needed, extract the required business data into a DTO and hand it off to another async mechanism; to send a message later, use `JmsTemplate` in a **new operation** with a clearly designed transaction boundary.

## 12. Production Operations and Testing Guide

### 12.1. Production checklist

- [ ] Choose `SessionAwareMessageListener` because you actually need the **raw Session**, not merely out of habit.
- [ ] Use the correct Jakarta namespace and Spring JMS version.
- [ ] DMLC/SMLC receives the proper `ConnectionFactory`, destination, listener, concurrency, and recovery settings.
- [ ] `exposeListenerSession` has the intended semantics; do not change it accidentally and split transactions.
- [ ] Do not manually close/commit/rollback the container-provided Session.
- [ ] Manually close resources directly created in the callback such as `MessageProducer`.
- [ ] Validate `Message` type, schema/version, `JMSReplyTo`, and `JMSCorrelationID`.
- [ ] Choose `sessionTransacted` or a transaction manager intentionally.
- [ ] Implement idempotency for redelivery/duplicates; DB transactions do not automatically join JMS transactions.
- [ ] Configure broker send/consume ACLs, TLS, and credential/secret management.
- [ ] Configure a DLQ, backoff, retry policy, and poison message limits.
- [ ] Keep listeners thread-safe when increasing concurrent consumers; never store Session in fields/statics.
- [ ] Configure a requester receive timeout and handle late/unknown replies.
- [ ] Collect metrics for consumer count, connections/sessions, error rate, redelivery, DLQ size, and latency.
- [ ] Run integration tests against a real provider when commit/rollback and reply semantics matter.

### 12.2. Recommended integration tests

1. Happy path: `TextMessage` request with `JMSReplyTo`/correlation → matching `ACK:` reply within timeout.
2. Missing replyTo: listener throws an error; does not send to an arbitrary destination.
3. Wrong message type: listener rejects, message goes to retry/DLQ per policy.
4. Wrong correlation ID: requester rejects mismatched response.
5. Handler fails before `return`: when transacted, request is rolled back and reply is not committed.
6. Increase `concurrentConsumers`: verify no shared mutable Session and no improper overlapping processing.
7. Broker down/restart: DMLC recovery and shutdown do not leak resources unexpectedly.
8. DB commits before JMS rollback: verify consumer deduplication; do not claim exactly-once unless proven.
9. Temporary reply queue expires: responder handles failure/late reply safely.
10. Production ACL: worker can send to valid `JMSReplyTo` without excessive administrative privileges.

## 13. Review Questions

**1. How does SessionAwareMessageListener differ from MessageListener?**  
It is a Spring-specific interface that additionally provides `Session` in `onMessage(M, Session)` and allows `throws JMSException`.

**2. Why shouldn't you manually close the Session inside the callback?**  
Because the listener container owns the lifecycle, transaction, and consumer tied to that Session. Closing it manually can break commit/rollback and recovery.

**3. If you want to send a reply within the same JMS transaction, which Session should you use?**  
The container-provided Session with `exposeListenerSession=true` and `sessionTransacted=true` or an appropriate transaction manager.

**4. Must a `MessageProducer` created manually by the callback be closed?**  
Yes; close the producer when finished, but do not close the container-managed Session.

**5. Can Spring @JmsListener access Session?**  
Yes. In Spring 6.x, a `@JmsListener` method can declare a `jakarta.jms.Session` argument when the native JMS API is needed.

**6. Can a JMS Session be shared across multiple threads?**  
No. Use it only within the scope of the callback/thread; a singleton listener can still be invoked concurrently by multiple consumers.

**7. Does `sessionTransacted=true` make DB and JMS atomic?**  
No. It handles the local JMS transaction; the DB is a separate resource unless coordinated properly or using outbox/idempotency.

**8. When a listener throws `JMSException`, must the callback manually roll back?**  
No, let the container/transaction manager handle it. Broker redelivery depends on policy.

**9. If the callback does not need the raw Session, what should be used?**  
`@JmsListener` receiving a simple payload/DTO, or standard `MessageListener` if a portable API is required.

**10. Why can creating a separate ConnectionFactory inside onMessage be wrong?**  
Because it creates a new session/transaction, making the reply inconsistent with the receipt, wasting resources, and complicating error handling.

## 14. Official References

1. [Spring Framework 6.2 — Receiving a Message: SessionAwareMessageListener and transactions](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
2. [Spring Framework 6.2 — SessionAwareMessageListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/SessionAwareMessageListener.html)
3. [Spring Framework 6.2 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
4. [Spring Framework 6.2 — AbstractMessageListenerContainer: exposeListenerSession](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
5. [Spring Framework 6.2 — Annotation-driven Listener Endpoints and Session argument](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
6. [Spring Boot 3.5 — Artemis JMS](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
7. [Spring Boot 3.5 — ConnectionFactoryUnwrapper Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/jms/ConnectionFactoryUnwrapper.html)
8. [Jakarta Messaging 3.1 — Session and MessageProducer](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
9. [Jakarta Messaging 3.1 — MessageProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer)
10. [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)