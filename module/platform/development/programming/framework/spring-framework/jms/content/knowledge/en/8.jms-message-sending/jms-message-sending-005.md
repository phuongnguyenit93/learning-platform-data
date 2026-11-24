# Setting Correlation ID and Reply Address When Sending JMS Messages

## 1. The Problem: Who Replies, and to Which Request?

In JMS / Jakarta Messaging, sending a message to a queue only specifies the **target address of the request**. For request–reply flows, the requester also needs two pieces of information: **where to receive the response** and **an identifier to match responses to the right requests**. Two standard JMS headers serve this purpose:

- **`JMSReplyTo`** holds a `jakarta.jms.Destination` object: the queue or topic where the receiver should send the reply.
- **`JMSCorrelationID`** holds a correlation key: a string used to link messages, most commonly matching a response to a request.

Because messages can arrive out of order, be redelivered, expire, or be processed by multiple consumers, these two headers cannot substitute for one another.

~~~text
Requester A                              Broker / Request queue                   Worker B
   │                                              │                                  │
   │  request body="order-42"                    │                                  │
   │  JMSReplyTo=reply-A                          │                                  │
   │  JMSCorrelationID=req-42                     │                                  │
   ├─────────────────────────────────────────────>│─────────────────────────────────>│
   │                                              │                         read JMSReplyTo
   │                                              │                         process request
   │                                              │<─────────────────────────────────┤
   │                                              │  response body="ACK:order-42"   │
   │                                              │  JMSCorrelationID=req-42        │
   │<────────────────── reply-A ──────────────────│                                  │
   │  check correlation ID                       │                                  │
~~~

**Key points:**

1. `JMSReplyTo` answers **where to send the result**.
2. `JMSCorrelationID` answers **which request this result belongs to**.
3. Neither header turns JMS into a guaranteed-success RPC by itself: applications still need a responder, timeouts, error handling, a correlation contract, retries, and idempotency.

This lesson belongs to the **Message Sending** topic in Spring JMS, so the focus is on **setting headers on requests when sending**, plus how the responder uses them and how replies are verified. Broker characteristics, transactions, and listeners are covered where needed to explain the send/receive flow, without replacing dedicated deep dives on those topics.

## 2. Distinguishing Related Headers

| Header | Value type | Who normally sets it? | Meaning |
| --- | --- | --- | --- |
| `JMSMessageID` | `String` prefixed with `ID:` per spec | JMS provider on send | Identifies a **specific message** assigned by the provider |
| `JMSCorrelationID` | `String`, or provider-native `byte[]` | Application per contract | Links a reply to a request or related messages |
| `JMSReplyTo` | `Destination` (`Queue` or `Topic`) | Requester | Suggested destination to receive replies |
| `JMSDestination` | `Destination` | Provider on send | Destination of the **current message**, not the reply target |
| `JMSType` | `String` | Application if used | Message classification, not a correlation key |
| Message properties | Supported JMS property types | Application/provider | Custom metadata such as `businessCommandId`, `schemaVersion` |

### 2.1. Why Not Use JMSMessageID for Every ID?

`JMSMessageID` is assigned by the provider at send time. In classic JMS, when `MessageProducer.send(...)` returns, the message object has been assigned an ID by the provider (unless the provider allows disabling message ID generation). This ID is useful for referencing **a single message instance**.

`JMSCorrelationID` is different: the application may specify a value to link **multiple messages**. For instance, a request and response have different `JMSMessageID`s, while the response carries a `JMSCorrelationID` matching the request's correlation.

Per the JMS specification:

- A provider-generated `JMSMessageID` carries the prefix **`ID:`**.
- An **application-set** `JMSCorrelationID` must not start with **`ID:`**, as that prefix is reserved for provider-generated message IDs.
- `JMSCorrelationID` may also reference **an actual `JMSMessageID`**, in which case the `ID:...` string is provider-originated rather than an arbitrary app-invented name.
- The `setJMSCorrelationIDAsBytes(byte[])` API is non-portable; providers are not required to support byte arrays. Prefer `setJMSCorrelationID(String)` in new designs.

**Valid** examples of application-generated correlation IDs:

~~~text
req-a4b8a169-4a0b-4a39-9b72-2d9a23c08e68
order-42-attempt-1
~~~

**Anti-pattern** example if invented arbitrarily by an application:

~~~text
ID:order-42
~~~

Do not rely on `setJMSMessageID("ID:...")` to pick your own request ID: that setter is intended for the provider.

### 2.2. JMSReplyTo Is a Destination, Not a String

`setJMSReplyTo(...)` requires an object implementing `Destination`, not a string like `"reply.queue"`. Using the classic API:

~~~java
Queue replyQueue = session.createQueue("demo.replies");
TextMessage request = session.createTextMessage("order-42");

request.setJMSReplyTo(replyQueue);
request.setJMSCorrelationID("req-order-42");
~~~

This is a **code snippet** inside a callback with `jakarta.jms.Session session`; it requires importing `Queue` and `TextMessage`, and the enclosing method must allow throwing `JMSException`. `createQueue("demo.replies")` creates an object representing the queue name. It **does not guarantee the broker creates a physical queue**; the broker may auto-create it or require prior provisioning and permissions.

Do not confuse `request.getJMSDestination()` with `request.getJMSReplyTo()`: the first identifies the queue receiving the **request**, while the second specifies the reply address.

### 2.3. Can They Be Null?

- `JMSReplyTo == null`: the message supplies no reply address. If the business operation requires no response (event, fire-and-forget), this is normal; if a response is required, the responder must have a **pre-configured** fallback or handle the error.
- `JMSCorrelationID == null`: the request supplied no application correlation ID. The responder may follow a convention based on `JMSMessageID`, provided both sides agree.
- A correlation ID does not prove authenticity by itself; callers still need broker permissions and contract-level response validation.

## 3. Two Common Correlation Conventions

### 3.1. Convention A: Application-Generated Request ID

The requester creates `correlationId` **before sending** and sets it on the request's `JMSCorrelationID`. The responder **copies this exact ID** onto the response's `JMSCorrelationID`.

~~~text
REQUEST
  JMSMessageID     = ID:provider-request-1
  JMSCorrelationID = req-abc
  JMSReplyTo       = reply.A

RESPONSE
  JMSMessageID     = ID:provider-response-2
  JMSCorrelationID = req-abc
  JMSDestination   = reply.A
~~~

Advantages: the caller knows the ID before sending; easy to populate a pending-request map, trace/log per attempt, and link with systems outside JMS. Use a sufficiently unique ID (e.g., `"req-" + UUID.randomUUID()`), never something like `"42"` when multiple services/clients could collide.

In modern request–reply designs, this is usually the clearest option **when both requester and responder adhere to the same contract**.

### 3.2. Convention B: Using the Request's JMSMessageID

The requester sends the request and obtains the provider-assigned `JMSMessageID`. The responder sets `response.JMSCorrelationID = request.JMSMessageID`.

~~~text
REQUEST
  JMSMessageID     = ID:provider-request-1
  JMSCorrelationID = null
  JMSReplyTo       = reply.A

RESPONSE
  JMSMessageID     = ID:provider-response-2
  JMSCorrelationID = ID:provider-request-1
~~~

Advantage: reuses the provider ID directly. Limitations: the requester cannot know the ID until sending completes, message ID generation must be enabled, and **retries create a new request that may receive a different `JMSMessageID`**.

### 3.3. Choose One Clear Convention

| Rule | Application-generated | JMSMessageID-based |
| --- | --- | --- |
| Requester knows ID before send | Yes | Not guaranteed |
| Responder sets reply correlation to | `request.getJMSCorrelationID()` | `request.getJMSMessageID()` |
| Tied to provider ID | No | Yes |
| Generating sufficiently unique ID | Application's responsibility | Provider generates |
| Switching providers/routing | Easy to keep custom contract | Depends on provider ID semantics |
| Retries and duplicates | Design attempt ID / business ID | Must map each attempt's message ID |

**Never let the requester follow Convention A while the responder follows B.** JMS does not automatically force both sides to agree on correlation rules. Document the convention in the contract and verify it with integration tests.

## 4. Setting JMSCorrelationID and JMSReplyTo with Spring JmsTemplate

In Spring Framework 6+ / Spring Boot 3+, JMS classes belong to `jakarta.jms.*`. Spring's `JmsTemplate` manages `Connection`, `Session`, producers, and exception translation within an operation, yet business code must still supply the destination and correlation.

### 4.1. `send(String, MessageCreator)` — Full Header Control

~~~java
import java.util.UUID;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;

// Snippet inside a service with an injected JmsTemplate:
String correlationId = "req-" + UUID.randomUUID();

jmsTemplate.send("demo.requests", session -> {
    Queue replyQueue = session.createQueue("demo.replies");
    TextMessage request = session.createTextMessage("order-42");
    request.setJMSReplyTo(replyQueue);
    request.setJMSCorrelationID(correlationId);
    return request;
});
~~~

Meaning:

1. `"demo.requests"` is the **destination where the template sends the request**.
2. `replyQueue` is the **address where the responder should send the response**.
3. `correlationId` is the **identifier the caller expects to match upon receipt**.
4. `MessageCreator` receives the `Session` supplied by the template; the callback must not retain the resource for later use.
5. This example creates no reply consumer yet: it is only a **message-sending snippet**, not a complete request–reply loop.

If you need to send to a `Destination` object rather than a String name, `JmsTemplate.send(Destination, MessageCreator)` provides the matching overload.

### 4.2. `convertAndSend` and `MessagePostProcessor`

When the payload converts easily (e.g., `String` → `TextMessage`), you can still attach headers before sending:

~~~java
import java.util.UUID;
import jakarta.jms.Queue;

Queue replyQueue = configuredReplyQueue;
String id = "req-" + UUID.randomUUID();

jmsTemplate.convertAndSend("demo.requests", "order-42", message -> {
    message.setJMSReplyTo(replyQueue);
    message.setJMSCorrelationID(id);
    return message;
});
~~~

`configuredReplyQueue` must be validly configured or injected by the service; this snippet **does not run standalone**. `MessagePostProcessor` runs after converting the payload to a JMS Message, **before the producer sends**. Do not confuse this with response handling.

**Design rule:** place correlation in the **standard header** rather than burying it solely inside a JSON body if the system wants JMS selectors, adapters, or JMS tooling to read it.

### 4.3. Plain Jakarta JMS API

~~~java
// Illustrative snippet with a configured ConnectionFactory:
try (JMSContext ctx = connectionFactory.createContext()) {
    Queue requests = ctx.createQueue("demo.requests");
    TemporaryQueue replyTo = ctx.createTemporaryQueue();
    try {
        TextMessage request = ctx.createTextMessage("order-42");
        request.setJMSCorrelationID("req-order-42");
        request.setJMSReplyTo(replyTo);
        ctx.createProducer().send(requests, request);
    } finally {
        replyTo.delete();
    }
}
~~~

This is **only an example of setting headers and sending**: the temporary reply queue is deleted immediately after sending, so **this exact snippet cannot wait for a response**. Real request–reply must create a consumer, keep the `JMSContext` and temporary destination alive through the wait window, and delete afterward. See the complete project in Section 7.

### 4.4. Note When Headers Are Configured on JMSProducer

`JMSProducer` (simplified API) also exposes `setJMSReplyTo(...)` and `setJMSCorrelationID(...)`. Producer-level settings apply at send time and can override header values on the message object. Having two places set the same header easily leads to sending the wrong reply destination or correlation ID; standardize on one approach.

## 5. The Responder Must Read Both Headers and Send the Right Reply

Responder sequence:

1. Receive the message from the request queue; validate body/schema.
2. Call `request.getJMSReplyTo()`.
3. Follow correlation Convention A or B; extract the corresponding ID.
4. Create **a new response message**.
5. Set `response.setJMSCorrelationID(id)`.
6. Send to the exact `Destination` obtained from the header.
7. Handle reply send failures, redelivery/duplicates, and log with sensitive data redacted.

Spring `@JmsListener` example using raw `TextMessage`:

~~~java
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
class ReplyWorker {
    private final JmsTemplate jmsTemplate;

    ReplyWorker(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @JmsListener(destination = "demo.requests")
    public void handle(TextMessage request) throws JMSException {
        Destination replyTo = request.getJMSReplyTo();
        String id = request.getJMSCorrelationID(); // convention A

        if (replyTo == null || id == null) {
            throw new IllegalArgumentException("Missing reply headers");
        }

        String body = request.getText();
        jmsTemplate.send(replyTo, session -> {
            TextMessage reply = session.createTextMessage("ACK:" + body);
            reply.setJMSCorrelationID(id);
            return reply;
        });
    }
}
~~~

This is an illustrative class needing a Spring project with `@JmsListener`, `ConnectionFactory`, and a broker. Spring JMS allows injecting raw `jakarta.jms.Message`/subclasses into listener methods. The method returns `void` so the framework does **not** send an extra automatic response; sending is performed explicitly.

Under Convention B, the responder instead uses:

~~~java
String id = request.getJMSMessageID();
reply.setJMSCorrelationID(id);
~~~

This is an **alternative logic snippet** inside the responder, not two standalone statements outside a callback. The requester must know the original request's message ID to compare.

### 5.1. Spring Listeners Can Auto-Send Replies from Return Values

~~~java
@JmsListener(destination = "demo.requests")
public String handle(String request) {
    return "ACK:" + request;
}
~~~

When the request carries `JMSReplyTo`, Spring's listener adapter can convert the return value into a response sent to that destination; `@SendTo` can specify a default reply destination when needed.

However, **automatically sending to the right address** does not guarantee every converter/adapter sets `JMSCorrelationID` per your application's convention. If the contract requires echoing a specific ID, test the raw JMS headers or construct the response explicitly as shown above.

## 6. Fixed Reply Queue vs. TemporaryQueue

### 6.1. Fixed Queue

The requester uses a pre-provisioned queue, such as `app.reply`:

~~~text
JMSReplyTo = Queue("app.reply")
~~~

Advantage: stable destination—replies can still arrive after a requester reconnect if the message survives and broker/TTL/persistence permit. Disadvantage: when multiple requests or instances consume from the same queue, you need **selectors, a dispatcher, or routing** so one requester does not steal another's response.

### 6.2. TemporaryQueue

The requester creates a `TemporaryQueue` via `Session.createTemporaryQueue()` or `JMSContext.createTemporaryQueue()`:

- Its lifetime is tied to the **connection that created it**; not the session or a Java variable.
- Only the **owning connection** may create consumers on that temporary destination.
- Producers on other connections **can send** to it, if broker permissions allow.
- When the owning connection closes or the queue is deleted, late replies lose their target.
- Well-suited for short-lived request–reply; incurs destination and consumer creation/deletion overhead.

For a single requester expecting a single reply, `TemporaryQueue` is usually easier than `TemporaryTopic`. `JMSReplyTo` may still be a `Topic`/`TemporaryTopic`, but publish/subscribe can deliver a reply to multiple subscribers rather than providing single-receiver semantics.

| Criterion | Fixed reply queue | TemporaryQueue |
| --- | --- | --- |
| Lifetime | Managed by broker/application | Tied to owning connection |
| Provisioning | Usually pre-configured | Created on demand by provider |
| Who can consume | Controlled by ACL/selector/concurrency | Only consumers on owning connection |
| On requester disconnect | Messages may remain if suitably persisted | Temporary queue does not persist by default |
| Concurrency | Must handle correlation/routing | Simple with one queue per request |
| Performance | Fewer new destinations created | High request rates create many destinations |

**Do not delete a temporary queue before waiting for the response finishes.** Calling `delete()` while a consumer is still open can throw `JMSException`; close the consumer first.

## 7. Runnable Demo with Java 17+, Spring Boot, and Artemis

This project clearly demonstrates both headers, both producer and consumer, timeouts, and correlation matching. The requester uses `JMSContext` (Jakarta Messaging simplified API) from Spring's factory; the responder uses `@JmsListener` and `JmsTemplate`.

### 7.1. Start the Demo Broker

~~~bash
docker run --rm -d --name jms-correlation-demo \
  -p 127.0.0.1:61616:61616 \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  apache/artemis:latest-alpine
~~~

Wait for the broker to become ready and inspect logs with `docker logs jms-correlation-demo`. These credentials are **for local labs only**. In production, use a secret store/TLS/ACLs, never sample passwords, and pin versions/image digests in pipelines.

### 7.2. Directory Structure

~~~text
jms-correlation-demo/
├── pom.xml
└── src/main/
    ├── resources/application.properties
    └── java/com/example/jms/CorrelationApplication.java
~~~

### 7.3. `pom.xml`

~~~xml
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
    <artifactId>jms-correlation-demo</artifactId>
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

### 7.4. `application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

`native` connects to a separately running Artemis broker. The demo relies on the lab broker allowing queue `demo.rpc.requests` to be created via auto-create policy; if disallowed, provision the queue/address and grant permissions. Do not use this configuration in production.

### 7.5. `CorrelationApplication.java` — Complete Source

~~~java
package com.example.jms;

import java.util.Objects;
import java.util.UUID;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class CorrelationApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorrelationApplication.class, args);
    }

    @Bean
    CommandLineRunner sendRequest(ConnectionFactory connectionFactory) {
        return args -> {
            String expectedId = "req-" + UUID.randomUUID();

            try (JMSContext context = connectionFactory.createContext()) {
                Queue requestQueue = context.createQueue("demo.rpc.requests");
                TemporaryQueue replyQueue = context.createTemporaryQueue();

                try (JMSConsumer consumer = context.createConsumer(replyQueue)) {
                    TextMessage request =
                            context.createTextMessage("order-42");
                    request.setJMSReplyTo(replyQueue);
                    request.setJMSCorrelationID(expectedId);
                    context.createProducer().send(requestQueue, request);

                    Message incoming = consumer.receive(5_000);
                    if (incoming == null) {
                        System.out.println("Reply timeout");
                        return;
                    }
                    if (!(incoming instanceof TextMessage reply)) {
                        throw new IllegalStateException(
                                "Expected TextMessage reply");
                    }

                    boolean match = Objects.equals(
                            expectedId, reply.getJMSCorrelationID());
                    System.out.println("Correlation matched: " + match);
                    System.out.println("Reply body: " + reply.getText());

                    if (!match) {
                        throw new IllegalStateException(
                                "Response correlation ID mismatch");
                    }
                } finally {
                    replyQueue.delete();
                }
            }
        };
    }
}

@Component
class OrderResponder {

    private final JmsTemplate jmsTemplate;

    OrderResponder(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @JmsListener(destination = "demo.rpc.requests")
    public void process(TextMessage request) throws JMSException {
        Destination replyTo = request.getJMSReplyTo();
        String id = request.getJMSCorrelationID();

        if (replyTo == null || id == null) {
            throw new IllegalArgumentException(
                    "Request must contain both reply headers");
        }

        String requestBody = request.getText();
        jmsTemplate.send(replyTo, session -> {
            TextMessage reply =
                    session.createTextMessage("ACK:" + requestBody);
            reply.setJMSCorrelationID(id);
            return reply;
        });
    }
}
~~~

Flow explanation:

1. Spring Boot creates `ConnectionFactory` from the Artemis starter and properties. `@EnableJms` enables annotation-driven endpoints (Boot also auto-configures infrastructure when the right starter is present).
2. `CommandLineRunner` generates a random `req-...` ID for the request without the `ID:` prefix.
3. The requester creates a `TemporaryQueue` and a **consumer on the same owning context** before sending the request. `JMSContext` auto-starts by default when a consumer is created; classic `connection.start()` is not needed here.
4. The request carries `JMSReplyTo = replyQueue` and `JMSCorrelationID = expectedId`.
5. The Spring `@JmsListener` reads both headers and sends the reply via `JmsTemplate.send(replyTo, MessageCreator)`, **copying the correlation ID**.
6. The requester receives the reply and verifies the ID matches. It does not treat a response as valid merely because a message arrived on the reply queue.
7. `try-with-resources` closes the consumer/context; `finally` deletes the temporary queue after the consumer is closed. Even on timeout, the application cleans up resources.

### 7.6. Running and Expected stdout

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

If the broker is active, the listener is ready, and the response arrives within 5 seconds, the two business output lines are:

~~~text
Correlation matched: true
Reply body: ACK:order-42
~~~

Additional Spring/Artemis logs may appear; the random UUID is not printed, so these two lines are consistent on successful runs. If the responder fails to reply in time:

~~~text
Reply timeout
~~~

After practicing:

~~~bash
docker stop jms-correlation-demo
~~~

This example **does not prove** exactly-once delivery, database atomicity, failover, or TLS. In production, requester and responder may live in separate processes; you must verify broker routing for reply destinations, timeouts, and ACLs.

## 8. JmsTemplate.sendAndReceive(): Spring Creates the Reply Address for You

`JmsTemplate.sendAndReceive(destination, MessageCreator)` provides synchronous request–reply: the template creates a temporary reply queue, sets `JMSReplyTo`, sends the request, creates a consumer to wait for the reply, and cleans up resources within the scope of the operation.

~~~java
// Snippet: requires a real responder reading "demo.rpc.requests".
Message reply = jmsTemplate.sendAndReceive(
    "demo.rpc.requests",
    session -> {
        TextMessage request =
                session.createTextMessage("order-42");
        request.setJMSCorrelationID("req-order-42");
        return request;
    }
);
if (reply == null) {
    System.out.println("Reply timeout");
}
~~~

Key points to remember:

- `sendAndReceive` typically **sets `JMSReplyTo` itself** to the call's own temporary queue; do not assume a custom `JMSReplyTo` set inside the callback will be preserved.
- If the response uses an application correlation ID, the responder must still follow the echo rule or the adapter's configured behavior.
- The caller must still check the response's `getJMSCorrelationID()` if the business logic requires verifying request matching.
- Configure a timeout, such as Boot's `spring.jms.template.receive-timeout=5s`, to avoid blocking indefinitely.
- Without a responder, `sendAndReceive` does not conjure a server. Nor does it guarantee DB rollbacks, retries/idempotency, or late-reply handling.

**When to pick which?** `sendAndReceive` fits simple, quick-to-implement request–reply; managing `JMSReplyTo`/consumers directly fits when you need a fixed reply queue, multiplexing multiple requests, or special lifetimes.

## 9. Multiple Concurrent Requests on a Shared Reply Queue

A shared queue `app.reply` can hold responses for `req-A`, `req-B`, and `req-C` in an order **different** from the request order. Simply setting `JMSReplyTo = app.reply` is not enough for a caller to know which message belongs to it.

~~~text
send req-A, corr=req-A ─┐
send req-B, corr=req-B ─┼─> request queue ──> responders
send req-C, corr=req-C ─┘                       │
                                              ▼
                                   app.reply: C, A, B
                                              │
                                    dispatcher/selector
                                              ▼
                               req-C → waiter C
                               req-A → waiter A
                               req-B → waiter B
~~~

Two strategies exist:

1. **Message selector:** create a consumer selecting responses whose `JMSCorrelationID` matches. Example JMS selector syntax: `JMSCorrelationID = 'req-123'`. Set an appropriate timeout; creating one selector consumer per request can strain broker resources.
2. **Single listener + dispatcher:** one consumer reads the reply queue, checks correlation, and completes the pending request/future in an application lookup table. Requires a concurrency-safe map, timeouts, cleanup, duplicate/unknown reply handling, and multi-replica design.

**Snippet** example with `JmsTemplate`:

~~~java
String correlationId = "req-123";
String selector = "JMSCorrelationID = '" + correlationId + "'";

Message received = jmsTemplate.receiveSelected(
        "app.reply",
        selector
);
~~~

`receiveSelected` is a synchronous receive that can block; configure a timeout. Only interpolate into a selector like this when the ID is system-generated from a **validated safe character set**; arbitrary input containing quotes/escapes must be escaped per selector syntax to avoid malformed expressions. JMS selectors filter **headers/properties**, not JSON inside the body.

With multiple instances listening on an unpartitioned reply queue, a responder sending to the shared queue may have its reply picked up by a **different** instance. If the pending `Future` lives only in the first instance's memory, you must design routing/selectors/ownership or shared state—a correlation ID alone does not route to the right replica.

## 10. Timeouts, Transactions, Retries, and Idempotency

### 10.1. Late Responses

After a requester times out, a reply may still be sent later:

- With a deleted `TemporaryQueue` or closed owning connection, the reply may fail or lack a valid target.
- With a fixed reply queue, the late response may linger until its TTL or cleanup policy removes it.
- If the requester retries with a new attempt ID, an old late reply must never be mistakenly matched as the result of the new attempt.

One way to document the contract:

~~~text
businessCommandId = create-order-42
attemptCorrelationId = req-...-1
replyTimeout = 5s
retryPolicy = exponential backoff, bounded attempts
lateReplyPolicy = discard / store / reconcile
~~~

`businessCommandId` serves business idempotency; `JMSCorrelationID` can represent an **attempt**. Never assume they are identical. Avoid creating duplicate orders just because a request was resent after a timeout.

### 10.2. Never Wait for a Reply Before Committing the Request in the Same JMS Transaction

~~~text
BEGIN JMS TRANSACTION
  send(request)      ← request not yet committed
  receive(reply)     ← wait for worker
                       worker cannot see request yet
  timeout / logic error
~~~

If a request is sent within an uncommitted **JMS transacted session**, other consumers generally cannot see the request to process it yet. Separate the transaction boundaries: commit the send before waiting for the reply, or use an async job/result design. Never hold a DB transaction open across a network wait without a clear operational reason.

### 10.3. Correlation Does Not Guarantee Exactly-Once

Consider a scenario:

1. The worker processes the business action and commits.
2. The worker sends the reply, but the requester loses connectivity before receiving it.
3. The requester times out and resends the request.
4. The worker receives a duplicate request.

Even with properly set correlation IDs, business side effects can repeat. You need idempotent handlers, deduplication by business command ID, transactional outbox where appropriate, bounded retries, DLQs, and redelivery monitoring.

### 10.4. TTL Differs from Receive Timeout

- Producer **time-to-live** governs how long a message remains deliverable under JMS expiration semantics.
- **Receive timeout** governs how long a thread waits for a response before returning `null` or timing out.
- **Business deadline** is a convention chosen by the system.

These three concepts are not automatically synchronized. A reply with remaining TTL may still arrive after the requester has timed out; conversely, a requester might keep waiting after the message has already expired.

## 11. Security, Tracing, and Testing

### 11.1. Never Treat Headers as Access Control

`JMSReplyTo` is a request-supplied destination; in multi-tenant brokers or across bridges, the responder must restrict which destinations it is willing to send to. A predictable or logged correlation ID is not an authentication token.

Essential safeguards:

- Broker authentication and least-privilege ACLs for send/consume/create destination.
- TLS, restricting client access to the broker, and protecting credentials.
- Validating message schemas and limiting sensitive payloads/metadata.
- Constraining reply destination namespaces when needed, especially for requests from less trusted sources.
- Never placing personal data, passwords, or session tokens in correlation IDs.

### 11.2. Useful Logging Without Data Leaks

~~~text
event=request_sent corr=req-... destination=demo.requests
event=reply_sent   corr=req-... result=success
event=reply_recv   corr=req-... latencyMs=18 matched=true
~~~

Do not log full bodies or secrets. Correlation IDs can connect requester/responder logs, whereas distributed tracing typically uses dedicated **trace ID / traceparent** fields via JMS properties/instrumentation. Do not use correlation IDs as per-request metrics labels: cardinality is far too high.

### 11.3. Required Tests

- Happy path: request has both `JMSReplyTo` and `JMSCorrelationID`; reply arrives at the right destination with a matching ID.
- Request missing replyTo/correlation: responder rejects or uses contract-defined fallback, never sending to a random destination.
- Timeout: requester does not hang threads forever; consumer/temporary queue is cleaned up.
- Mismatch: wrong correlation response is discarded or flagged as an error, never returned as a success.
- Concurrency: multiple requests sharing a reply queue do not cross-deliver replies.
- Redelivery: duplicate requests do not re-apply business side effects.
- Reconnect/failover: stale temporary destinations are not reused blindly after a new connection is established.
- Authorization: worker cannot send to a reply destination without permission; errors are handled and observed.
- Schema/security: forged or malformed replies are rejected even if correlation matches.

## 12. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Sending a request without `JMSReplyTo` | Responder does not know where to reply | Set `Destination` or define an explicit fallback |
| Passing a String directly to `setJMSReplyTo` | Invalid API signature | Resolve `Queue`/`Topic` first |
| App-generated ID starting with `ID:` | Violates JMS reserved ID convention | Use `req-` prefix and UUID |
| Using the response's `JMSMessageID` to identify the request | That is a different message with a new ID | Check the response's `JMSCorrelationID` |
| Responder generates a fresh correlation ID for the response | Fails to match request | Copy request correlation or request message ID per contract |
| Requester uses Convention A while responder uses B | Correlation mismatch | Standardize and run cross-service tests |
| Creating a `TemporaryQueue` then closing connection before reply | Destination lifetime ends | Keep owning connection open until timeout/response |
| Deleting `TemporaryQueue` while consumer is still open | May throw `JMSException` | Close consumer before deleting |
| Shared reply queue without selector/dispatcher | Consumers steal each other's replies | Design correlation routing / multi-instance handling |
| Omitting receive timeout | Thread can block indefinitely | Use finite timeouts and backpressure |
| Waiting for reply inside uncommitted send transaction | Responder cannot see the request | Commit send before waiting |
| Retrying without idempotency | Duplicate side effects | Business command ID and deduplication policy |
| Relying on correlation as a security token | Easily spoofed | ACL/auth/TLS; validate source and reply destination |
| Ignoring late replies | Stale responses cause bugs or queue buildup | TTL, unknown/late reply handling |
| Using JSON body instead of JMS header when selectors are needed | Selectors do not read arbitrary bodies | Write standard `JMSCorrelationID`/properties |

## 13. Practical Checklist

1. Clearly define request destination, reply destination, and message type.
2. Ensure `JMSReplyTo` is a valid `Destination` object with proper routing/ACLs.
3. Pick Convention A or B for correlation and document it on both producer and responder.
4. When app-generated, use a sufficiently unique ID without the `ID:` prefix.
5. Responder reads `replyTo` from the request and sets the response's correlation per contract.
6. Requester checks the **response's** correlation ID before accepting a reply as valid.
7. For `TemporaryQueue`, create the consumer on the owning connection and delete after closing the consumer.
8. For shared queues, implement selectors/dispatchers and handle multiple instances.
9. Configure timeouts, bounded retries, late-reply policies, DLQs, and metrics.
10. Separate correlation ID, business idempotency key, and trace ID.
11. Never wait for a reply inside a JMS transaction that has not committed the request.
12. Test broker outages, missing/wrong headers, wrong destinations, duplicates, and reconnects.

## 14. Self-Check Questions

**1. What is `JMSReplyTo`?**  
It is the `Destination` suggested by the sender for receiving replies; it may be a regular or temporary queue/topic.

**2. What is `JMSCorrelationID` used for?**  
Linking messages together—most commonly matching a response to its request.

**3. Can two requests share the same reply queue with different correlation IDs?**  
Yes. In that case, consumers/dispatchers must match the right response using correlation and ownership.

**4. Why must application-generated correlation IDs not start with `ID:`?**  
That prefix is reserved for provider-generated message IDs by the JMS specification.

**5. How do Convention A and Convention B differ?**  
A: response correlation equals `request.getJMSCorrelationID()`. B: response correlation equals `request.getJMSMessageID()`.

**6. Does calling `session.createQueue("reply")` automatically create a temporary queue?**  
No. That creates a named queue handle; use `createTemporaryQueue()` when you need a provider-allocated temporary destination.

**7. When can the requester delete a temporary reply queue?**  
After finishing response receipt or timing out, close the consumer first and then delete; never delete right after sending.

**8. Does `JmsTemplate.sendAndReceive` create a responder automatically?**  
No. The template only sends, creates a temporary reply queue, and waits; the other side must send the reply.

**9. Is every response arriving on the right queue automatically valid?**  
No. You must also verify correlation ID, message type, schema, and security conditions.

**10. Does a correlation ID guarantee exactly-once processing?**  
No. Retries and redeliveries can still create duplicates; idempotency and transaction design are still required.

## 15. Official References

1. [Jakarta Messaging 3.1 Specification — JMSCorrelationID, JMSReplyTo, JMSMessageID](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
2. [Jakarta Messaging 3.1 API — Message header methods](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message)
3. [Jakarta Messaging 3.1 API — JMSContext](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext)
4. [Jakarta Messaging 3.1 API — TemporaryQueue](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/temporaryqueue)
5. [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
6. [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
7. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
8. [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
9. [Spring Boot — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
10. [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)
