# Temporary Destinations and Connection Lifecycle Scope

> **Module:** Spring Framework – JMS  
> **Topic group:** Destination  
> **Focus:** `TemporaryQueue`, `TemporaryTopic`, connection ownership, request/reply, and consequences when a connection closes.

## Learning objectives

By the end of this lesson, you should be able to:

1. Explain `TemporaryQueue` and `TemporaryTopic` in Jakarta Messaging, distinguishing them from long-lived `Queue` and `Topic` destinations.
2. Distinguish the **creating session** of a temporary destination from the **owning connection** of that temporary destination; predict what happens when closing a consumer, session, `JMSContext`, or connection.
3. Explain the security/ownership constraint: only the connection that created a temporary destination may **create a consumer** on it, whereas producers on other connections can still **send** to it.
4. Apply `JMSReplyTo` and `JMSCorrelationID` in the request/reply pattern; handle timeouts, late results, connection drops, and cleanup.
5. Use Jakarta Messaging APIs and Spring `JmsTemplate.sendAndReceive` properly, without treating temporary destinations as durable mailboxes.
6. Choose appropriately between a **temporary reply queue** and a **named durable reply queue** based on business request lifetime.

## 1. What is a temporary destination?

In Jakarta Messaging (JMS), `Destination` is the addressing interface. `Queue` and `Topic` are the two fundamental destination types. Their two **temporary** subtypes are:

```java
jakarta.jms.TemporaryQueue  // extends jakarta.jms.Queue
jakarta.jms.TemporaryTopic  // extends jakarta.jms.Topic
```

Temporary destinations have two defining properties:

- **Allocated by the provider with a unique identity**, typically an internal unique name that the application should not guess or reuse.
- **Has a lifecycle tied to the connection that created it**, unless the application deletes it earlier via `delete()`.

In an application, a client can send requests to a fixed queue `reports.requests` while creating its own temporary queue to receive replies for the current work session:

```text
                    Regular queue: reports.requests
Request client --------------------------------------> Report service
     |                                                |
     |       request.JMSReplyTo = temporaryQueue       |
     |                                                |
     |<--------------------- reply --------------------+
     |
  TemporaryQueue owned by request client's connection
```

A temporary destination does **not** mean "temporary message", "short-TTL message", "auto-deleted queue once drained", or "in-JVM-only memory". It is **a provider-managed address type** with special *ownership* and *lifecycle* semantics. The provider may need to allocate resources outside the JVM.

### Differences from regular Queue/Topic names

| Criterion | Regular `Queue` / `Topic` | `TemporaryQueue` / `TemporaryTopic` |
| --- | --- | --- |
| How object is created | `createQueue("name")`, `createTopic("name")`, or JNDI | `createTemporaryQueue()`, `createTemporaryTopic()` |
| Who chooses the name? | Application/admin and provider per config | Provider generates a private identity |
| Does standard API create physical resource? | `createQueue(String)` / `createTopic(String)` only creates a **handle**, no physical guarantee | Temporary methods **instruct the provider to create a temporary destination** |
| Lifetime | Per broker configuration and governance | Tied to owning **connection**, or until `delete()` |
| Who can create a consumer? | Consumers permitted by broker policy | **Only the owning connection** (across any session of that connection) |
| Who can send? | Producers with send permission | Producers from **other connections** can also send given the reference and permissions |
| Usable as a long-term address after client restart? | Yes, depending on destination retention policy | **No**: when the original connection closes, the destination ends |
| Typical purpose | Worker queues, event topics, stable reply queues | Ephemeral session-scoped reply in request/reply |

A temporary queue still follows queue semantics when multiple eligible consumers exist **within the same connection**. A temporary topic still carries publish/subscribe semantics, except subscribers/consumers must belong to the owning connection. Fundamental queue/topic rules still apply; "temporary" adds **lifecycle and ownership restrictions**.

## 2. Core concept: scope is **connection**, not session

This is the most important takeaway of the lesson.

Jakarta Messaging exposes temporary destination creation methods on `Session` or `JMSContext` for developer convenience. However, the temporary object does **not belong exclusively to the session that called create**; it belongs to the **underlying connection**.

```text
Connection A  [owner of TemporaryQueue Q-temp-abc]
  |
  +-- Session A1  ---> createTemporaryQueue() -> Q-temp-abc
  |
  +-- Session A2  ---> createConsumer(Q-temp-abc)    [ALLOWED]
  |
  +-- Session A3  ---> createConsumer(Q-temp-abc)    [ALLOWED]
  |
  +-- Session A1 closed                          [Q-temp remains]
  |
  +-- Connection A closed --------------------> [Q-temp is deleted]


Connection B  [non-owner]
  |
  +-- Session B1  ---> createProducer(Q-temp-abc)  [can SEND]
  |
  +-- Session B2  ---> createConsumer(Q-temp-abc)  [NOT allowed]
```

From this diagram:

- `Session.close()` closes the session and its consumers; **it does not automatically terminate the temporary destination** as long as the connection stays open.
- **Another session of the same connection** can create a consumer on the temporary destination, even if it was not the session that created the queue/topic.
- **Another connection** cannot create a consumer on a temporary destination created by connection A, even if it knows the name or receives the object reference.
- Another connection **can send** replies to A's temporary destination given the address and appropriate permissions. That is how request/reply across two services works.
- `Connection.close()` terminates connection resources, including any temporary destinations it created.
- Calling `delete()` early can terminate the temporary destination before the connection closes, once no consumers are still using it.

**Do not conflate 3 levels:** temporary destination lifetime = connection; consumer lifetime = consumer/session/connection; message content lifetime = delivery/ack/expiration rules while the destination still exists.

### 2.1. What happens if Session A1 closes?

Suppose A1 created `Q-temp`, and A2 on the same connection is listening on `Q-temp`. Closing A1 only closes A1's session resources; A2 can continue receiving from `Q-temp` while the connection remains valid. Conversely, when A2 closes, the temporary queue does not vanish just because no listener remains: you must call `delete()` or close the connection.

### 2.2. What happens if JMSContext closes?

`JMSContext` combines connection and session functionality in the simplified API. Easy-to-miss points:

- `connectionFactory.createContext(...)` creates an application-managed context with one underlying connection and one session.
- Where supported, `context.createContext(sessionMode)` creates a **new context sharing the same connection**, with a different session.
- `JMSContext.close()` closes that context's **session** and its associated producers/consumers.
- If **no other active context** shares the underlying connection, `close()` also closes the connection → temporary destinations terminate.
- If **another context still shares the connection**, closing one context **does not mean closing the connection** → temporary destinations can remain alive.

Do not oversimplify to "closing any JMSContext deletes all temporary queues." You must know whether closing the context actually closes the **underlying connection**. In Jakarta EE environments with injected/container-managed `JMSContext`, the container manages the lifecycle; the application must not call `close()` arbitrarily.

### 2.3. What if the connection is only stopped, not closed?

`Connection.stop()` or `JMSContext.stop()` pauses delivery for the connection; it is **not a destination-deletion operation**. After calling `start()` again, consumers can resume per JMS semantics. Do not use `stop()` to clean up temporary resources.

### 2.4. What if the connection drops unexpectedly?

By contract, a temporary destination lives with its connection. When the broker detects that the connection has dropped or closed, it performs cleanup per provider mechanics. Failure detection, keepalive/heartbeat, and real-time cleanup can have broker-dependent latency. **Do not use the observed time from a single crash to infer a fixed JMS-guaranteed retention duration.**

## 3. Creating and deleting TemporaryQueue/TemporaryTopic in the API

### 3.1. Simplified API: JMSContext

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TemporaryTopic;

public final class TemporaryDestinations {
    private final ConnectionFactory connectionFactory;

    public TemporaryDestinations(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public void demonstrate() throws Exception {
        try (JMSContext context =
                     connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

            TemporaryQueue replies = context.createTemporaryQueue();
            TemporaryTopic notifications = context.createTemporaryTopic();

            // Provider-assigned name, not a portable broker name.
            System.out.println("Reply queue: " + replies.getQueueName());
            System.out.println("Temporary topic: " + notifications.getTopicName());

            // Only delete when no consumers are using it.
            notifications.delete();
            replies.delete();
        } // Closes context, and underlying connection if no shared context remains.
    }
}
```

This is a **Java class running in an app with a real provider**, not a standalone JDK-only program. It requires `jakarta.jms` dependencies, a provider implementation, a broker, and a configured `ConnectionFactory`. Printed names are **non-deterministic**, so no fabricated stdout is shown.

`createTemporaryQueue()`/`createTemporaryTopic()` are commands that allocate temporary destinations. They **differ** from `createQueue(String)`/`createTopic(String)`, which only construct object handles for a provider-specific name.

### 3.2. Classic API: Session creates, Connection owns

```java
Connection connection = connectionFactory.createConnection();
try {
    Session session = connection.createSession(
            false, Session.AUTO_ACKNOWLEDGE);

    TemporaryQueue replyQueue = session.createTemporaryQueue();
    MessageConsumer replies = session.createConsumer(replyQueue);

    connection.start();

    // ... send request and receive reply ...
    replies.close();     // Close consumer first.
    replyQueue.delete(); // Delete temporary destination early.
    session.close();
} finally {
    connection.close();  // Clean up any remaining resources.
}
```

This is an illustrative classic `jakarta.jms` snippet inside a method with `connectionFactory`, requiring imports and a real broker, not runnable standalone. `createTemporaryQueue`, `createConsumer`, and `delete` can throw `JMSException`; production code needs `try/finally` or try-with-resources for closeable objects rather than relying solely on the happy path. In the example, if an operation fails before `replyQueue.delete()`, `connection.close()` remains the final cleanup safeguard.

### 3.3. delete() rules and cleanup order

`TemporaryQueue.delete()`/`TemporaryTopic.delete()` deletes an existing destination, yet **if receivers/subscribers are still using it**, the API may throw `JMSException`. Safe order for a synchronous exchange:

1. Cancel/finish receiving and close `JMSConsumer`/`MessageConsumer`.
2. Call `tempDestination.delete()` (if the application actively manages it).
3. Close session/context/connection when no longer needed; never reuse a destination object after deleting it.

```java
TemporaryQueue replyTo = context.createTemporaryQueue();
JMSConsumer replyConsumer = context.createConsumer(replyTo);
try {
    // Request/reply exchange within the connection's lifetime.
} finally {
    replyConsumer.close();
    replyTo.delete();
}
```

This snippet assumes an open `JMSContext context` and does not run standalone. `delete()` on temporary destination interfaces declares checked `JMSException`, so the enclosing method must declare or handle it appropriately. In systems auditing cleanup errors, if the `try` body already threw an exception and `delete()` throws as well, preserve the original root cause rather than masking it.

### 3.4. Should you call delete if the connection closes immediately afterward?

The spec states temporary destinations are automatically deleted when the connection closes; they may also be reclaimed when the object is garbage-collected. However, **never rely on garbage collection for timely cleanup**. Calling `delete()` early is valuable when the connection stays alive in reuse (for example in a pool/cache), because the broker could otherwise retain reply queue resources even after the exchange ends.

Never attempt to delete a destination that still has an active consumer; never keep sending/receiving on a deleted object. If cleanup fails, log it without pretending the request succeeded.

## 4. Why can another connection send yet cannot consume?

This property is what makes a temporary destination a "private reply mailbox":

```text
CLIENT A (Connection A)                 SERVICE B (Connection B)
----------------------                 ------------------------
create TemporaryQueue T
create Consumer(T)                      CANNOT create Consumer(T)

send request
  JMSReplyTo = T             ----------> receive request
                                      |
                                      +-- send reply to T  [ALLOWED]
                                               |
Consumer(T) <----------------------------------+
```

**Ownership only restricts creating consumers**, not all external producers. This design prevents the request-handling service from stealing replies meant for another client.

However, temporary destination ownership is **not a complete user-authentication mechanism**. Who may send/receive on the broker still requires access permissions, authentication/TLS, and provider policies. If a destination object leaks, do not assume nobody can inject fake messages into it; applications should validate correlation, payload, provenance/trust boundaries, and sender permissions per business needs.

### How do TemporaryQueue and TemporaryTopic differ?

- `TemporaryQueue` is a temporary queue: multiple consumers **on the owning connection** can compete to receive replies. Normal request/reply typically uses one consumer per queue to avoid routing replies across multiple callers.
- `TemporaryTopic` is a temporary topic: consumers/subscriptions must also belong to the owning connection, yet a published message can be delivered under topic semantics to active eligible subscriptions.
- You cannot establish long-lived durable topic subscriptions on a temporary topic as if it were a stable destination: this destination type ends with the connection. The spec considers creating a durable subscription on a temporary topic a programming error; providers may or may not detect it immediately.

**Choose `TemporaryQueue` for single-recipient request/reply** unless requirements specifically demand pub/sub within one connection and the provider supports that scenario.

## 5. Request/reply pattern: one connection owns the reply queue

Request/reply typically involves two destination parts:

- **Fixed request destination** (for example queue `reports.requests`): service B can listen on it long-term.
- **Temporary reply destination** created by client A (for example `temp://A/3F8...` is an illustrative string, **not standard JMS syntax**): only consumers on connection A may read from it.

### 5.1. Full sequence

```text
Client A                           Broker                         Service B
   |                                  |                               |
   |-- createTemporaryQueue(T) ------>|                               |
   |-- createConsumer(T) ------------>|                               |
   |-- send Request ----------------->|---- deliver request --------->|
   |    JMSReplyTo=T                   |                               |
   |    JMSCorrelationID=req-42        |                               |
   |                                  |<---- send Reply to T ----------|
   |<----------- receive Reply -------|     JMSCorrelationID=req-42   |
   |-- close consumer ---------------->|                               |
   |-- delete T ---------------------->|                               |
   |-- close connection -------------->|                               |
```

**Intentional ordering:** create the temporary reply queue and consumer **before sending the request**, reducing the risk of an early reply arriving before the client is ready. Sending to destination T from service B **does not** require service B to share connection A.

**JMS does not perform RPC automatically** just because you set `JMSReplyTo`. The responder must explicitly read `request.getJMSReplyTo()`, process the request, construct a reply message, and send it to that destination. `JMSCorrelationID` helps match responses to requests when multiple exchanges occur.

### 5.2. Two common Correlation ID strategies

**Client-generated correlation ID:**

1. Client generates a unique per-request ID, e.g. `req-42`.
2. Sets `request.setJMSCorrelationID("req-42")` before sending.
3. Responder copies the ID into the reply via `reply.setJMSCorrelationID(request.getJMSCorrelationID())`.
4. Client matches the reply against the awaited ID.

**Message-ID correlation:**

1. Provider assigns `JMSMessageID` to the request upon send.
2. Responder sets `reply.JMSCorrelationID = request.JMSMessageID`.
3. Client compares against the `JMSMessageID` assigned to the request after send.

Both are **application contracts**, not JMS automatically guaranteeing every response has valid correlation. Choose one consistent strategy across all clients and responders; if retries exist, consider a stable business ID independent of `JMSMessageID`.

When each exchange uses its own temporary queue, the unique address already isolates replies; correlation remains useful for validation, auditing, and detecting stray responses.

### 5.3. Timeout does not mean the request failed

Suppose the client waits 3 seconds while the service takes 10 seconds to process:

```text
t=0s      Client sends Request, creates TemporaryQueue T
t=3s      Client times out, deletes T and/or closes connection A
t=10s     Service B completes, attempts to send Reply to T
```

The reply may **fail to deliver** because destination T has vanished, or be rejected/dropped by the broker per provider policy. Yet the request **may already have succeeded in service B**. Therefore the client **must not infer "timeout means the business action never ran."**

When retrying requests with side effects (placing orders, charging money, sending emails), you need an idempotency key or status-query mechanism. The responder can persist results in durable storage, allowing the client to poll later by business request ID.

### 5.4. Other reliability boundaries

- `DeliveryMode.PERSISTENT` on a reply does not make a temporary queue survive closing connection A.
- `JMSExpiration`/TTL on a reply does not extend T's lifecycle; replies cannot be retrieved from a deleted T.
- `AUTO_ACKNOWLEDGE`/transactions govern when the provider considers a message received/committed, not creating durable reply destinations.
- `JMSMessageID` and `JMSCorrelationID` are headers; neither verifies response authorization or payload validity.
- `Connection.stop()` only pauses delivery; if the client still wants to receive replies, it must restart the connection at the appropriate time.

## 6. Complete Jakarta Messaging example on the request client side

This example uses **Java 17+**, package `jakarta.jms`, and a running provider. The file below is **a complete class in a project with dependencies and a real `ConnectionFactory`**; it cannot be run with bare `javac` alone without a broker and Jakarta Messaging dependencies.

**File `ReportRequestClient.java`:**

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;

import java.util.Objects;
import java.util.UUID;

public final class ReportRequestClient {

    private final ConnectionFactory connectionFactory;

    public ReportRequestClient(ConnectionFactory connectionFactory) {
        this.connectionFactory =
                Objects.requireNonNull(connectionFactory);
    }

    public String requestReport(String reportId) throws JMSException {
        String requestId = UUID.randomUUID().toString();

        try (JMSContext context = connectionFactory.createContext(
                JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue requests = context.createQueue("reports.requests");
            TemporaryQueue replyTo = context.createTemporaryQueue();

            // Create consumer on the same connection owning replyTo.
            JMSConsumer replyConsumer = context.createConsumer(replyTo);
            try {
                TextMessage request = context.createTextMessage(reportId);
                request.setJMSReplyTo(replyTo);
                request.setJMSCorrelationID(requestId);

                context.createProducer().send(requests, request);

                // Wait at most 3 seconds, never wait indefinitely.
                Message received = replyConsumer.receive(3_000L);
                if (received == null) {
                    throw new IllegalStateException(
                            "Report request timed out: " + requestId);
                }

                if (!(received instanceof TextMessage reply)) {
                    throw new IllegalStateException(
                            "Unexpected reply message type");
                }
                if (!requestId.equals(reply.getJMSCorrelationID())) {
                    throw new IllegalStateException(
                            "Reply correlation ID mismatch");
                }

                return reply.getText();
            } finally {
                // delete() requires no active receivers remain.
                replyConsumer.close();
                replyTo.delete();
            }
        }
    }
}
```

**Explanation:**

1. `context.createTemporaryQueue()` instructs the provider to allocate a reply queue with the lifetime of the **underlying connection**.
2. `context.createConsumer(replyTo)` is valid because the consumer is created on that connection; it also starts receiving when `autoStart` is enabled by default.
3. The client sets `JMSReplyTo` to the `replyTo` object. JMS transports the reference with the message so the responder can use it without guessing a reply queue name.
4. Correlation ID is generated by the client and attached to the request; the responder in the next section echoes it back.
5. `receive(3_000L)` can return `null` on timeout or throw a runtime exception on provider failure; never assume replies always arrive.
6. `finally` closes the consumer and deletes the temporary queue. Then the context is closed by try-with-resources. If the context shares an underlying connection with another context, keep that in mind when reasoning about lifecycle.
7. Because classic `Message` methods and `TemporaryQueue.delete` can throw checked `JMSException`, the method declares `throws JMSException`. `JMSContext`/`JMSProducer`/`JMSConsumer` methods in the simplified API typically report failures via `JMSRuntimeException`.

**Practical note:** `finally` here illustrates cleanup sequencing. In production code, an exception from `replyTo.delete()` could mask the original exception from send/receive; log cleanup exceptions while preserving the business error. Results are not guaranteed if the broker is down, queue `reports.requests` is unprovisioned, or no responder is running.

### 6.1. A responder on another connection can still send

On service B's side, after receiving a request on the **regular queue** `reports.requests`, the responder:

1. Reads `request.getJMSReplyTo()`; if null, it cannot reply under this contract.
2. Reads the request ID from `JMSCorrelationID`.
3. Processes the job and creates a reply message.
4. Sends the reply to the `Destination` object obtained from the header.
5. Sets `JMSCorrelationID` on the reply to the received request ID.

An illustrative JMS API snippet inside another session:

```java
// Assume sessionB is Service B's jakarta.jms.Session,
// and request is the TextMessage received on "reports.requests".
Destination replyTo = request.getJMSReplyTo();
if (replyTo == null) {
    throw new IllegalArgumentException("Missing JMSReplyTo");
}

TextMessage reply = sessionB.createTextMessage(
        "READY:" + request.getText());
reply.setJMSCorrelationID(request.getJMSCorrelationID());

MessageProducer producer = sessionB.createProducer(replyTo);
producer.send(reply);
producer.close();
```

This is **not a standalone file**: `sessionB` and `request` require a real JMS environment, transactions/ack, and proper error handling. Service B's producer does **not** create a consumer on T. It only sends, so service B being on **another connection** does not violate ownership rules.

### 6.2. End-to-end testing with a provider

1. Provision the `reports.requests` queue on the broker.
2. Start responder B listening on that queue.
3. Start client A and invoke `requestReport("report-42")` while B is active.
4. Confirm the broker shows a temporary queue during the exchange, and that it disappears after client cleanup.
5. Verify the actual response string, e.g., `"READY:report-42"` if the responder implements the snippet above.
6. Disconnect connection A before B replies; verify B handles late replies per policy rather than hanging or retrying forever.
7. Run multiple concurrent requests, each with its own reply destination, verifying resource limits and timeouts.

**No fixed stdout is claimed** for the JMS example because delivery timing, temporary queue names, connections, and provider policies are not determined by code alone.

## 7. Spring JMS: request/reply with JmsTemplate

In Spring Framework with Jakarta Messaging, `JmsTemplate` handles most send/receive boilerplate. Spring provides:

```java
Message sendAndReceive(
        String destinationName,
        MessageCreator messageCreator);
```

This is a **simplified illustrative signature**; the real API has overloads taking `Destination` or using the default destination. In `JmsTemplate`'s implementation, this call **creates a temporary reply queue** for the exchange, puts it in `JMSReplyTo` on the request, waits for the reply, and cleans up resources.

### 7.1. Spring client sending request, receiving reply

Assume the Spring project has configured `jakarta.jms.ConnectionFactory`, `JmsTemplate`, and a broker. Set an appropriate timeout when configuring `JmsTemplate`:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class ReportJmsClientConfig {

    @Bean
    public JmsTemplate reportRequestTemplate(
            ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        template.setReceiveTimeout(3_000L);
        return template;
    }
}
```

**File `ReportGateway.java`:**

```java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

import java.util.Optional;

@Service
public class ReportGateway {

    private final JmsTemplate template;

    public ReportGateway(
            @Qualifier("reportRequestTemplate") JmsTemplate template) {
        this.template = template;
    }

    public Optional<String> request(String reportId) throws JMSException {
        Message reply = template.sendAndReceive(
                "reports.requests",
                session -> session.createTextMessage(reportId));

        if (reply == null) {
            return Optional.empty(); // Timeout: business outcome undetermined.
        }
        if (!(reply instanceof TextMessage text)) {
            throw new IllegalStateException("Unexpected reply message type");
        }
        return Optional.of(text.getText());
    }
}
```

Both files are **code for a Spring project** with `spring-jms` dependencies and a provider, not standalone JDK programs. Calling `request("report-42")` **may** return `Optional.of("READY:report-42")` with the responder example below, or `Optional.empty()` on timeout. Always receiving a reply cannot be guaranteed.

Spring manages the temporary queue and consumer within the exchange; do not keep the temporary destination object from that call for reuse after the method returns. Spring's API allows configuring receive timeout; avoid infinite waits in synchronous requests.

### 7.2. Spring service receiving request and sending reply

**File `ReportRequestResponder.java`:**

```java
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class ReportRequestResponder {

    private final JmsTemplate jmsTemplate;

    public ReportRequestResponder(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @JmsListener(destination = "reports.requests")
    public void respond(TextMessage request) throws JMSException {
        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            throw new IllegalArgumentException("JMSReplyTo is required");
        }

        String requestId = request.getJMSCorrelationID();
        if (requestId == null) {
            requestId = request.getJMSMessageID();
        }
        final String correlationId = requestId;

        String reportId = request.getText();
        jmsTemplate.send(replyTo, session -> {
            TextMessage reply =
                    session.createTextMessage("READY:" + reportId);
            reply.setJMSCorrelationID(correlationId);
            return reply;
        });
    }
}
```

This intentionally receives a raw `TextMessage` to read `JMSReplyTo`; Spring `@JmsListener` supports raw JMS messages. `@EnableJms` and an appropriate `jmsListenerContainerFactory` (or Spring Boot auto-configuration) must be active; the `JmsTemplate` injected into the responder must point to the broker with permission to send replies.

**Why `jmsTemplate.send(replyTo, ...)`?** The argument is the `Destination` object from the header, not a String name. The responder can send the reply to the temporary queue from **another connection** (matching semantics). Do not create a new listener on the reply queue on the service side; that would violate ownership.

When the original request already has `JMSCorrelationID`, the responder preserves that ID. If the request did not set an ID (for instance in a simple `JmsTemplate.sendAndReceive` path), the responder falls back to the provider-assigned `JMSMessageID` to aid logging/correlation. This is a contract choice; when strict matching is needed, align the strategy between client and service.

**Transaction note:** if the responder updates a DB and then sends a reply, the listener's local JMS transaction does not automatically combine the DB update and another `JmsTemplate`'s send into a single atomic transaction. For critical workflows, use idempotency/outbox or an appropriate transaction coordination strategy.

### 7.3. Why should you not store a temporary reply queue in a Spring singleton?

Many Spring applications use connection caching or pooling. Calling `Connection.close()` on a **proxy** does not necessarily close the physical broker connection immediately, and a temporary destination created on a reused connection can outlive the naive intuition of "method ends, queue disappears."

- If a cache/pool returns the connection instead of physically closing it, **do not rely on closing a proxy to assume the broker cleaned up T right away**.
- Spring `JmsTemplate.sendAndReceive` manages the temporary queue per exchange, making it generally safer than manually creating thousands of queues and forgetting to delete them.
- Spring `CachingConnectionFactory` has logic to avoid caching producers/consumers for temporary destinations per its implementation, yet do not assume that eliminates all memory-leak risks in custom resolvers or caching code.
- If you want a fixed reply destination or to handle many concurrent requests on one reply consumer, design correlation and concurrency explicitly; never arbitrarily reuse a `TemporaryQueue` object that belonged to a different physical connection.

A very common bug is storing a `TemporaryQueue` as a field on a singleton bean and reusing it after a broker reconnect. The old object only represents a destination created on the old connection; once the original connection closes, it is no longer a valid reply mailbox.

## 8. Request/reply in a local transaction: an easy trap

Suppose the client uses `JMSContext.SESSION_TRANSACTED`, trying to both **send the request** and **wait for the reply** in the same transaction:

```java
// ANTI-PATTERN: transacted context, missing commit before receive.
JMSContext context =
        connectionFactory.createContext(JMSContext.SESSION_TRANSACTED);

TemporaryQueue replyTo = context.createTemporaryQueue();
TextMessage request = context.createTextMessage("report-42");
request.setJMSReplyTo(replyTo);
context.createProducer().send(requests, request);

Message reply = context.createConsumer(replyTo).receive(5_000L);
// Responder may not have received the request because send is not yet committed!
context.commit();
```

**Do not deploy the code above**: it illustrates a bug. In a local JMS transaction, an uncommitted sent request may not yet be delivered by the broker to the responder; meanwhile the client blocks waiting for a reply before committing → timeout, stalling up to timeout, or logical deadlock.

Proper organization:

1. Send the request and **commit the send** before waiting for the reply if using transactions for sending.
2. Use explicit transactions/acknowledgements for the reply-receiving step, avoiding holding an uncommitted transaction while waiting on the other side.
3. Or use a non-transacted JMS context for simple synchronous exchanges, paired with proper timeouts and idempotency.
4. Avoid synchronous transactions spanning HTTP request → JMS request → reply without planning timeouts, rollbacks, and resources.

The Jakarta EE Tutorial explicitly highlights this limitation with local transactions. The request/reply pattern must respect transactional boundaries, not assume "enabling transacted always makes it more reliable."

## 9. Temporary reply vs named fixed reply queue?

| Requirement | Temporary reply destination | Named reply Queue/Topic |
| --- | --- | --- |
| Short request, client waits directly for a few seconds | Often suitable | Usable, though requires handling multiplexing/correlation |
| Client might shut down and return hours later | **Unsuitable**; old connection disappears | Better suited when provisioning, retention, and delivery mode support it |
| Service takes minutes/hours to process task | Risk that response arrives after temporary queue was deleted | Can use stable reply queue or job state in DB/object store |
| Many concurrent requests | Each exchange can create its own reply queue; carries resource cost | Shared reply queue needs selector/dispatcher by correlation ID |
| Multiple consumers on different connections reading replies | **Not allowed** with temporary destinations | Possible if queue/topic policy/semantics permit |
| Deleted when client connection closes | Automatic by lifecycle | Not automatic; governed by broker administration |
| Consumer needs to receive after client restart | Cannot treat as the same mailbox | Can use durable queue with proper identity and retention |

### Alternative pattern for long-running processing

For example, generating a report takes 40 minutes:

1. Client sends a `CreateReport` command with a unique `jobId` to a **long-lived queue**.
2. Service records the job and returns `ACCEPTED` quickly (if needed) without holding HTTP open.
3. Worker processes and stores status `PENDING/RUNNING/DONE/FAILED` and results in durable storage.
4. Client polls status by `jobId` or receives events via a **stable** notification/queue mechanism.
5. Every retry uses the same idempotency key; results do not depend on a temporary queue staying alive.

A temporary reply queue can still be used for a **fast ACK**, but should not be the sole holder of long-lived results.

## 10. Lifecycle and cleanup: scenario table

Suppose connection A creates temporary queue T.

| Action | Does T still exist per lifecycle? | A's consumers? |
| --- | --- | --- |
| Consumer A closes | **Yes**, if `delete()` was not called and connection remains open | Closed consumer stops; a new consumer can be created on A |
| Session that created T closes | **Yes**, if connection A remains open | That session's consumers close; another session on A can create a consumer |
| Connection A calls `stop()` | **Yes** | Delivery paused, T is not deleted |
| Connection A calls `start()` again | **Yes** | Can resume receiving per provider semantics |
| One shared `JMSContext` closes while underlying connection is used by another context | **Yes** | Closed context's consumers stop; other context on same connection can create consumers |
| `delete()` succeeds when no consumers remain | **No** | Consumers no longer have a valid path to read T |
| Connection A actually calls `close()` | **No** | All sessions/consumers belonging to A close |
| Connection A drops before broker detects it | Actual cleanup state may not complete immediately | Do not treat T as a reliable mailbox after failure |
| Client restarts and opens a new connection A2 | **Not connection A**, does not reattach to previous T | Must create a new temporary destination if needed |

**Messages may still be waiting while the destination gets deleted because the connection closed.** No `PERSISTENT` setting can "save" T's lifecycle from deletion.

If the provider exposes admin logs/metrics for temporary destinations, monitor counts per connection, destinations with zero consumers, lifetimes, and post-timeout cleanup. These metrics matter under heavy request/reply loads.

## 11. Standalone runnable Java 17 illustration: connection ownership model

To distinguish session and connection, the following example runs **purely on JDK 17** and simulates some permission/lifecycle rules. This is **not a Jakarta Messaging implementation**: there is no broker, persistence, JMS headers, JMS transactions, or networking.

Create file **`TemporaryScopeDemo.java`**:

```java
public final class TemporaryScopeDemo {
    static final class TemporaryMailbox {
        private final String ownerConnectionId;
        private boolean exists = true;

        TemporaryMailbox(String ownerConnectionId) {
            this.ownerConnectionId = ownerConnectionId;
        }

        boolean canConsume(String connectionId) {
            return exists && ownerConnectionId.equals(connectionId);
        }

        boolean canSend(String connectionId) {
            return exists; // Assumes the broker granted send permission.
        }

        void closeCreatingSession() {
            // Closing a session does not delete the connection's destination.
        }

        void closeOwnerConnection() {
            exists = false;
        }

        boolean exists() {
            return exists;
        }
    }

    public static void main(String[] args) {
        TemporaryMailbox reply = new TemporaryMailbox("conn-A");

        System.out.println("Owner consume: " +
                reply.canConsume("conn-A"));
        System.out.println("Same connection / other session: " +
                reply.canConsume("conn-A"));
        System.out.println("Other connection consume: " +
                reply.canConsume("conn-B"));
        System.out.println("Other connection send: " +
                reply.canSend("conn-B"));

        reply.closeCreatingSession();
        System.out.println("After session close: " + reply.exists());

        reply.closeOwnerConnection();
        System.out.println("After connection close: " + reply.exists());
    }
}
```

Compile/run:

```bash
javac TemporaryScopeDemo.java
java TemporaryScopeDemo
```

**Exact stdout:**

```text
Owner consume: true
Same connection / other session: true
Other connection consume: false
Other connection send: true
After session close: true
After connection close: false
```

In a real JMS application, `connectionId` is not an arbitrary client-chosen string as in the simulation; connection ownership is managed by the provider. Returning true for `canSend("conn-B")` assumes the sender has permission; a real broker can reject it if access control forbids it. The demo's purpose is to reinforce **connection ownership**, not to replace testing against a provider.

## 12. Common operational mistakes and how to handle them

### Mistake 1 — "TemporaryQueue belongs to the session; closing the creating session deletes the queue"

**Wrong:** lifecycle is tied to the connection. Another session on the same connection can still consume. Check whether the underlying connection actually closed.

### Mistake 2 — "The responder must connect on the same connection as the requester"

**Wrong:** the responder only **sends**. Another connection is allowed to send to a temporary destination given the reference and permissions. It **must not** create a consumer on that destination.

### Mistake 3 — "TemporaryQueue is a durable queue because messages are sent PERSISTENT"

**Wrong:** delivery mode does not extend destination lifetime. When the owning connection closes, the temporary queue is deleted and pending replies do not persist like a fixed mailbox.

### Mistake 4 — "Reply timeout means the service did nothing"

**Wrong:** the service may have executed side effects and replied late. Retry using a business ID/idempotency; when needed, query durable state rather than re-running blindly.

### Mistake 5 — "You can keep sending to the old queue after the client reconnects"

**Do not assume that:** the old connection's temporary destination has ended. Create a new temporary queue on the new connection and advertise the new reference via `JMSReplyTo`.

### Mistake 6 — "Closing a pooled connection proxy immediately makes the broker release all temp queues"

**Uncertain:** a cache/pool may keep the physical connection alive. Focus on explicit cleanup, real lifetimes, resource metrics, and managed request/reply libraries.

### Mistake 7 — "Calling delete() while a listener is still receiving"

**May fail:** the API may throw `JMSException` if a receiver/subscriber is still using it. Close the consumer before deleting; guard against races if another thread is receiving.

### Mistake 8 — "Just setting JMSReplyTo makes the broker send the reply automatically"

**Wrong:** service B must read the header, create the reply, and send it. `JMSReplyTo` is only a desired address, not automatic RPC.

### Mistake 9 — "JMSCorrelationID is always populated properly by itself"

**Wrong:** matching rules are provided by the app/framework; align on client-generated IDs vs echoing `JMSMessageID`. With `JmsTemplate.sendAndReceive`, each exchange gets a temp queue; do not assume it sets business correlation automatically.

### Mistake 10 — "One local transaction can send the request and block on receive"

**Can deadlock/timeout:** the sent request is uncommitted so the responder has not received it. Commit the request before waiting for the reply, or choose a non-transacted exchange with sensible business boundaries.

### Mistake 11 — "Temporary topics support durable subscribers surviving restarts"

**Wrong:** temporary topics terminate when the connection closes; long-lived durable subscriptions require a stable topic and proper subscription identity.

### Mistake 12 — "No need to clean up temporary queues because Java GC will handle it"

**Dangerous:** GC cleanup has no deadline; the provider holds resources outside the JVM. Close consumers and delete proactively on long-lived connections, or use an API/framework with clear lifecycle management.

## 13. Test scenarios to run against a real broker

### Test A — Closing a session does not delete the queue

1. Create `Connection A` and `Session A1`.
2. Create `TemporaryQueue T` using A1.
3. Create `Session A2` **on the same Connection A**; create a consumer for T using A2.
4. Close A1; keep A2 and Connection A active.
5. Use a producer on Connection B to send a test message to T; verify A2 can still receive it.
6. Close consumer A2, delete T, close Connection A.

Outcome to verify: **Closing Session A1 does not delete T**. Do not predict exact broker-assigned names for T or exact routing timing.

### Test B — Another connection can send, yet cannot consume

1. A creates T and has a consumer on T.
2. B obtains reference T from the request's `JMSReplyTo`.
3. B creates a producer and sends a reply to T — valid if policy allows.
4. B tries to create a consumer on T — must be rejected per ownership rules (error reporting may vary by provider and API).
5. A receives the reply and verifies correlation.

Outcome to verify: **read restriction belongs to the connection; write permission does not require connection exclusivity**.

### Test C — Timeout and late reply

1. Set reply timeout to 2 seconds.
2. Have the responder take 10 seconds; client times out, closes consumer, deletes temporary queue.
3. Responder tries to send the reply to the old T; check provider error handling, logs, and retry policy.
4. Client queries job state by business ID to determine whether the request succeeded; do not repeat side effects.

Outcome: timeout **does not** prove the request was not processed.

### Test D — JMSContext sharing a connection

1. In Java SE, create `JMSContext primary`.
2. Use `primary.createContext(JMSContext.AUTO_ACKNOWLEDGE)` to create a child context on the same connection; provider/environment must support this.
3. Create T with primary; create consumer for T with child context.
4. Close primary while the child context stays active.
5. Verify T still exists and the child context can still consume; close the last context and observe cleanup.

Do not apply this test verbatim to injected/container-managed JMSContext inside Jakarta EE web/EJB containers, where creating extra sessions and closing contexts are restricted.

### Test E — Checking Spring caching and resource pressure

1. Use `JmsTemplate.sendAndReceive` for several hundred sequential requests, each with a finite timeout.
2. Observe the count of active temporary queues via the broker admin console, connection count, and memory/heap.
3. Trigger several consecutive timeouts; ensure resources return to normal after cleanup.
4. Enable CachingConnectionFactory or pooling per real configuration and repeat.
5. Confirm no temporary destination objects are accidentally retained beyond the exchange, no consumer leaks occur, and send/receive errors are not swallowed.

Do not set a pass criterion like "every broker reclaims in exactly 0 ms"; observe trends and provider cleanup policies.

### Test F — Stalled local transaction

1. In a test environment, configure `SESSION_TRANSACTED`, send a request, then call receive before committing.
2. Observe timeout or that the responder has not yet seen the request.
3. Fix by committing the send before receiving or separating transactions, and verify the responder receives the request.
4. Combine idempotency and timeouts when using request/reply in business workflows.

## 14. Design checklist

Before choosing temporary destinations in JMS/Spring, confirm:

- [ ] **Business lifetime:** must the reply survive restarts or outlive the caller going offline? If yes, do not use a temporary queue as the sole mailbox.
- [ ] **Connection owner:** who keeps the actual connection open until the reply finishes? Is there pooling/caching, reconnect, or failover?
- [ ] **Consumer owner:** are all consumers of the temporary destination created strictly within the owning connection?
- [ ] **External producer:** does the responder have the exact reference from `JMSReplyTo` and send permission?
- [ ] **Correlation:** is there a unique request ID, clear echo/matching rule, and business idempotency?
- [ ] **Timeout:** how long to wait, how to retry, and how are late replies handled?
- [ ] **Transaction:** is the request send committed before waiting for the reply; how do the responder's transactions interact?
- [ ] **Cleanup:** consumer closed before delete, connection closed last; are cleanup errors monitored?
- [ ] **Broker policy:** queue quotas, TTL, permissions, resource limits, and cleanup on node/network failures?
- [ ] **Observability:** temporary destination count, pending replies, timeout rate, orphan requests, redelivery, and business outcome status?

Some large-scale systems use a **stable reply queue + correlation dispatcher** to reduce per-request temporary queue allocation overhead; in return they must manage multiplexing, late replies, and concurrency themselves. There is no universally best choice—only the right lifecycle contract.

## 15. Knowledge self-check

**Question 1.** Session S1 on Connection A creates T. S1 closes, while S2 on the same Connection A remains open. Can S2 create a consumer on T?

**Answer:** Yes. A temporary destination belongs to the **connection**, not just the session that created it.

**Question 2.** Service B on Connection B receives a request with `JMSReplyTo=T` from Connection A. Can B send a reply to T?

**Answer:** Yes, if the reference is still valid and send permission exists. However, B **cannot** create a consumer on T.

**Question 3.** The client closes Connection A after sending the request but before the reply arrives. Does using `PERSISTENT` keep T alive?

**Answer:** No. Temporary destinations are deleted when the owning connection closes; persistent delivery does not change T's lifetime.

**Question 4.** A client creates two JMSContexts sharing an underlying connection. Does closing the first context always delete T?

**Answer:** No. If the second context is still active on that connection, the underlying connection has not closed; T may still exist.

**Question 5.** Does `JMSReplyTo` automatically force the JMS provider to generate a reply message?

**Answer:** No. The responder application must create and send the reply.

**Question 6.** A request times out, and later the service returns `READY`. Can we conclude the service had not executed the task at timeout?

**Answer:** No. A timeout only means the caller did not receive a reply within the wait window. You need a business ID/job state to know the true outcome.

**Question 7.** With a local transaction, the client sends a request and blocks on receive before committing: why can it stall?

**Answer:** The request is uncommitted so the responder has not been delivered it to process; no reply ever arrives for the client.

**Question 8.** Why must the consumer be closed before calling `TemporaryQueue.delete()`?

**Answer:** The API may throw `JMSException` while a receiver is still using the queue. Proper cleanup must respect active resources.

**Question 9.** Can a `TemporaryTopic` serve as the destination for a durable subscription across multiple restarts?

**Answer:** No. It is deleted with the owning connection, contradicting the durability requirement of a long-lived durable subscription.

**Question 10.** In Spring, does `JmsTemplate.sendAndReceive` create a temporary queue per exchange, and should callers store that queue in a singleton?

**Answer:** `JmsTemplate`'s implementation creates the temporary reply queue for the exchange and manages its lifecycle. Do not retain or reuse that object in a singleton after the exchange.

**Question 11.** If a physical connection in a pool has not closed, is calling `close()` on the proxy enough to claim the temporary destination was deleted?

**Answer:** No. You must understand the proxy/pool and actual cleanup; prefer explicit deletion or framework-managed lifecycles.

**Question 12.** If you need the result of a 40-minute task after the caller restarts, what should you choose?

**Answer:** A stable queue/job state/result store or a named reply queue with appropriate retention/correlation—do not depend on a previous connection's temporary destination.

## Conclusion

**A temporary destination is a JMS address with a provider-generated identity and CONNECTION-scoped ownership.** A Session or JMSContext is only where the creation API is exposed; another session on the same connection can still consume. Another connection **can send** to the temporary address, yet **cannot create a consumer** there. Closing the connection or calling `delete()` at the right time ends the temporary destination's lifecycle.

This model fits **short-lived request/reply** using `JMSReplyTo`, timeouts, and correlation. For long-running work requiring crash/restart resilience and durable results, use stable destinations or a business state store. Designing temporary destinations well is not just calling `createTemporaryQueue()`—it requires understanding **connection ownership, transactions, timeouts, cleanup, and broker resource policies**.

### Official references

1. [Jakarta Messaging 3.1 Specification — 6.2.2 Creating temporary destinations](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — connection scope, consume permissions, lifecycle, and sending from other connections.
2. [Jakarta Messaging 3.1 — JMSContext API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext) — `createTemporaryQueue()`, `createTemporaryTopic()`, `createContext()`, and `close()`.
3. [Jakarta EE Tutorial — JMS Concepts](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html) — temporary destinations, request/reply, and local transaction warnings.
4. [Jakarta Messaging — TemporaryQueue API](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/jms/temporaryqueue) — `delete()` and active-receiver constraints.
5. [Jakarta Messaging 3.1 — TemporaryTopic API](https://javadoc.io/static/jakarta.jms/jakarta.jms-api/3.1.0/jakarta.messaging/jakarta/jms/TemporaryTopic.html) — lifetime and `delete()`.
6. [Spring Framework — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/jms/core/JmsTemplate.html) — `sendAndReceive` creating temporary reply queues.
7. [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate`, `MessageCreator`, and destination resolution.
8. [Spring Framework — CachingConnectionFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html) — connection/session caching and temporary destination considerations.