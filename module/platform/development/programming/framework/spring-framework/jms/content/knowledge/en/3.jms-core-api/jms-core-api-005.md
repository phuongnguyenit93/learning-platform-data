# MessageProducer and Sending Operations in JMS

## 1. The Role of MessageProducer: What Does "Send" Actually Do?

In **Jakarta Messaging (JMS)**, `MessageProducer` is the **producer-side** API used to send a `Message` object to a `Destination` (a queue or topic). The application creates the message via a `Session`, configures metadata and delivery policies, and calls `send(...)`. The provider/broker is responsible for accepting, routing, and storing the message according to the JMS contract and actual configuration.

~~~text
Publisher application
  ├─ ConnectionFactory → Connection → Session
  │                                     ├─ create Message (body + properties)
  │                                     └─ createProducer(destination)
  └─ MessageProducer.send(message) → JMS provider/broker → Queue/Topic
                                                            ↓
                                                        consumer
~~~

Three milestones must be distinguished:

1. **Preparing the message:** the application has a `Message` object in memory; this does not yet mean the broker has seen the message.
2. **Send operation completes:** the synchronous send method returns successfully or the asynchronous send callback signals completion. Exact guarantees depend on delivery mode, transactions, and the provider.
3. **Business work processed:** a consumer receives, processes, acknowledges/commits, and persists the business outcome. **A successful `send(...)` does not prove the consumer has processed the message.**

This lesson focuses on the **classic JMS API `MessageProducer`** (`jakarta.jms.MessageProducer`), used with `Connection` and `Session`. **`JMSProducer`** is a separate simplified API used with `JMSContext`; **Spring `JmsTemplate`** is a framework-level abstraction. Understanding `MessageProducer` helps accurately read how higher-level abstractions perform sends.

> **Version note:** Examples use Java 17+, Spring Framework 6+/Spring Boot 3+ where Spring is mentioned, and Jakarta Messaging 3.1 (`jakarta.jms`). In older Java EE/JMS code, the package may be `javax.jms`; do not mix the two package families in the same project without verifying provider compatibility.

## 2. Creating a Producer: Fixed Destination vs. Choosing Destination at Send Time

### 2.1. Objects Preceding MessageProducer

| Component | Responsibility | Created By |
| --- | --- | --- |
| `ConnectionFactory` | Factory for obtaining connections to the JMS provider; endpoint, auth, and TLS/pooling depend on configuration | Container, DI, or application bootstrap |
| `Connection` | Represents the JMS connection; can serve multiple sessions per provider rules | `connectionFactory.createConnection()` |
| `Session` | Context of **a single logical thread of control**; creates messages, producers, and manages local JMS transactions | `connection.createSession(...)` |
| `Destination` (`Queue`, `Topic`) | Logical target where the provider receives messages | Looked up via JNDI/DI or created as a destination object via session |
| `MessageProducer` | Sends messages to a bound destination, or to a destination supplied on each send | `session.createProducer(...)` |

For example:

~~~java
// The connection and session variables here are created and managed
// by the same thread in the enclosing code.
Queue orders = session.createQueue("orders.events");
MessageProducer producer = session.createProducer(orders);
~~~

`session.createQueue("orders.events")` creates a **queue handle object**, not a guarantee that the broker has provisioned that queue with the desired policies. The broker may allow auto-creation or require an administrator to create it beforehand. For production, explicitly determine queue/topic settings, permissions, durability, retention, DLQ, and auto-create policies per provider.

### 2.2. Identified Producer vs. Unidentified Producer

**Identified producer** (bound to a destination):

~~~java
MessageProducer producer = session.createProducer(orders);
producer.send(session.createTextMessage("one"));
~~~

`send(Message)` uses `orders`, which was bound when creating the producer. Calling `send(destination, message)` on an identified producer is an API misuse; that form is reserved for **unidentified** producers.

**Unidentified producer** (not bound to a destination):

~~~java
Queue orders = session.createQueue("orders.events");
Queue audit = session.createQueue("orders.audit");

try (MessageProducer producer = session.createProducer(null)) {
    producer.send(orders, session.createTextMessage("created"));
    producer.send(audit, session.createTextMessage("audit-record"));
}
~~~

When using `createProducer(null)`, every `send` must pass a `Destination`. Calling `send(message)` without a destination is prohibited. Each style fits a different need:

- Sending many messages to **one fixed destination**: an identified producer is explicit and reduces the chance of sending to the wrong destination.
- Sending to **multiple destinations** from the same session, such as replying to `JMSReplyTo`: an unidentified producer can be useful.

Do not treat a `MessageProducer` as safe for arbitrary sharing across threads just because it can target multiple destinations: a classic JMS `Session` is a single-logical-thread context and must obey threading restrictions.

## 3. The `send` Method: Understanding Signatures and Parameter Order

Most important **synchronous** overloads:

| API | When to Use |
| --- | --- |
| `send(Message message)` | Producer has a fixed destination; uses the producer's default QoS |
| `send(Message message, int deliveryMode, int priority, long timeToLive)` | Producer has a fixed destination; overrides QoS for **this send** |
| `send(Destination destination, Message message)` | Unidentified producer; supplies the destination for this send |
| `send(Destination destination, Message message, int deliveryMode, int priority, long timeToLive)` | Unidentified producer with per-send QoS override |

The order of the three QoS parameters is always **delivery mode → priority → TTL**. Example:

~~~java
producer.send(
    message,
    DeliveryMode.PERSISTENT, // request persistent delivery
    7,                       // priority from 0 to 9
    60_000L                  // TTL = 60 seconds; unit is milliseconds
);
~~~

This is the **classic MessageProducer API**. Asynchronous overloads accept an additional `CompletionListener` at the end, explained later. There is no `deliveryDelay` parameter in classic `send(...)` overloads: if delay is needed, set it via `producer.setDeliveryDelay(milliseconds)`.

### 3.1. Default Values and Configuration Scope

~~~java
producer.setDeliveryMode(DeliveryMode.PERSISTENT);
producer.setPriority(4);
producer.setTimeToLive(300_000L);
producer.setDeliveryDelay(2_000L);
producer.send(message); // uses defaults set above
~~~

These setters configure the **producer's defaults**; they do not rewrite payloads. `send(message, mode, priority, ttl)` overrides only those three properties **for that specific send**, without altering the producer's defaults. Delivery delay remains a producer property.

- `DeliveryMode.PERSISTENT`: the provider applies persistence per the spec and configuration. **The JMS default is PERSISTENT**, though actual durability during broker failure depends on broker policies, transactions, storage, clustering, TTL, and operational state.
- `DeliveryMode.NON_PERSISTENT`: generally lower overhead, but messages may be lost if the provider fails; use only when that trade-off fits business requirements.
- **Priority:** integer **0–9**, default **4**. The provider makes a best effort to prioritize higher levels; this is not an exact execution schedule or latency SLA.
- **Time-to-live (TTL):** milliseconds; **0** means no expiration time from TTL. With a positive TTL, `JMSExpiration` is calculated from **send time** plus TTL, even when sent inside a transaction (not recalculated at commit time).
- **Delivery delay:** non-negative milliseconds; default **0**. The provider must not deliver the message before the minimum wait measured from **send time**, even inside a transaction. This is **not** a scheduler guaranteeing an exact delivery timestamp.

**Relationship between TTL and delay:** if delay = 10 seconds and TTL = 5 seconds, the message can expire before it ever becomes eligible for delivery. Design TTL to exceed delay plus your desired processing/buffer window, and verify on the real broker.

The setters `setDisableMessageID(true)` and `setDisableMessageTimestamp(true)` are only **hints allowing the provider to skip ID/timestamp generation for optimization**; the provider may reject or ignore the hint. Do not enable them when the application needs `JMSMessageID` for tracing or uses timestamps; this is not a guaranteed performance switch.

## 4. Building Messages Properly Before Sending

`Session` can create message types such as `TextMessage`, `BytesMessage`, `MapMessage`, `StreamMessage`, and `ObjectMessage`. For cross-system integration, JSON text or schema-backed byte payloads are usually easier to version than Java object serialization. `ObjectMessage` carries risks when deserializing untrusted data.

A message contains:

| Data Area | Example | Who Sets It |
| --- | --- | --- |
| **Body** | Order JSON | Application |
| **Application properties** | `eventType`, `eventId`, `schemaVersion` | Application via `setStringProperty`, `setIntProperty`, … |
| **Applicable application headers** | `JMSCorrelationID`, `JMSReplyTo`, `JMSType` | Application when a clear usage pattern applies |
| **Provider-assigned headers** | `JMSMessageID`, `JMSTimestamp`, `JMSDestination`, `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration` | Updated by provider upon sending |

Example creating payload and metadata **before** `send`:

~~~java
TextMessage message = session.createTextMessage("""
        {"type":"OrderCreated","orderId":"O-42","schemaVersion":1}
        """.strip());
message.setStringProperty("eventType", "OrderCreated");
message.setStringProperty("eventId", "evt-42");
message.setIntProperty("schemaVersion", 1);
message.setJMSCorrelationID("request-42");
producer.send(message);
~~~

In this example, `eventId` is a **business** ID assigned by the producer; it should remain stable across retries of the same event and serve as a deduplication key at the consumer. `JMSMessageID` is assigned by the provider per send attempt and typically differs across producer retries. `JMSCorrelationID` mainly links workflows / request–reply pairs; it does not automatically replace `eventId`. `JMSReplyTo` is appropriate when the consumer needs to know where to send a response.

**Do not predict or pre-assign header values owned by the provider.** After a synchronous send succeeds, you can read `message.getJMSMessageID()` (unless IDs are disabled); for an asynchronous send, wait for the callback before reading fields the provider may modify. JMS message selectors evaluate **headers and properties**, and do not inspect inside a JSON body automatically.

## 5. Complete Java Example at the JMS API Layer: Sending an Event

File `src/main/java/com/example/jms/OrderMessageSender.java`:

~~~java
package com.example.jms;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class OrderMessageSender {
    private final ConnectionFactory connectionFactory;

    public OrderMessageSender(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public String sendOrderCreated(String eventId) throws JMSException {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId must not be blank");
        }

        try (Connection connection = connectionFactory.createConnection();
             Session session = connection.createSession(
                     false, Session.AUTO_ACKNOWLEDGE)) {

            Queue orders = session.createQueue("orders.events");
            try (MessageProducer producer = session.createProducer(orders)) {
                producer.setDeliveryMode(DeliveryMode.PERSISTENT);
                producer.setPriority(4);
                producer.setTimeToLive(300_000L); // 5 minutes

                TextMessage message = session.createTextMessage(
                        """
                        {"type":"OrderCreated","orderId":"O-42","schemaVersion":1}
                        """.strip()
                );
                message.setStringProperty("eventType", "OrderCreated");
                message.setStringProperty("eventId", eventId);
                message.setIntProperty("schemaVersion", 1);

                producer.send(message);
                return message.getJMSMessageID();
            }
        }
    }
}
~~~

**Run conditions:** This example is a complete class that compiles under Java 17+ with `jakarta.jms-api` 3.1 and a compatible **JMS provider**. The class **has no `main` method**, because the application must supply a `ConnectionFactory` connected to a broker (via Spring DI, JNDI, or custom bootstrap). It cannot be run directly via `java OrderMessageSender` without a provider and bootstrap code. The `orders.events` destination must also be accepted/provisioned by the broker according to its configuration.

Reading the example step by step:

1. `ConnectionFactory.createConnection()` acquires a connection; `createSession(false, Session.AUTO_ACKNOWLEDGE)` creates a **non-transacted** session. `AUTO_ACKNOWLEDGE` relates to receiving messages and does not mean the producer waits for a consumer ack.
2. `session.createQueue(...)` creates the queue handle; `session.createProducer(orders)` creates a producer bound to that destination.
3. `session.createTextMessage(...)` builds the body; properties are set **before** sending.
4. `setDeliveryMode`, `setPriority`, and `setTimeToLive` configure QoS. `send` is synchronous by default; upon returning successfully, `getJMSMessageID()` lets you inspect the provider-assigned ID if generated.
5. `try-with-resources` closes the producer, session, and connection. These JMS interfaces extend `AutoCloseable`; closing the session/connection also cleans up child resources.

**Note:** You do not need `connection.start()` just to **send**; that method primarily starts **delivering** messages to consumers. Nor should you open and close a new connection/session for every message in high-throughput applications when the provider/framework offers safe caching/pooling; the example creates/closes full resources to illustrate the lifecycle of one send operation.

**No fixed stdout:** the method returns the broker-assigned `JMSMessageID` (which may be `null` if the provider suppresses ID generation by configuration). The result depends on the provider, so no synthetic ID or log output is fabricated.

## 6. Sending Multiple Messages: Per-Send Policy Choices

The snippet below assumes a valid `session` and `producer` bound to a queue:

~~~java
TextMessage normal = session.createTextMessage("normal");
producer.send(normal); // producer's default QoS

TextMessage urgent = session.createTextMessage("urgent");
producer.send(
        urgent,
        DeliveryMode.PERSISTENT,
        8,
        30_000L
);
~~~

The `urgent` message uses the explicit QoS for this send; the producer's defaults remain intact for subsequent sends. Do not equate priority 8 with "guaranteed to be processed first": multiple consumers, broker policies, redelivery, and concurrency can alter observed order.

With an unidentified producer, pass the destination before the message:

~~~java
try (MessageProducer producer = session.createProducer(null)) {
    Queue billing = session.createQueue("billing.tasks");
    Topic events = session.createTopic("orders.events");

    producer.send(billing, session.createTextMessage("invoice:O-42"));
    producer.send(events, session.createTextMessage("created:O-42"));
}
~~~

These two calls send to **two separate destinations** and do **not** form an atomic transaction when the session is non-transacted. In particular, using an unidentified producer does not turn a queue into a topic or vice versa. Each message should correspond to a clear event/command and a specific send contract; typically create a new `Message` for each business event so stale headers/properties are never accidentally reused.

## 7. When `send` Succeeds, When `send` Fails, and "Unknown Outcomes"

### 7.1. Synchronous Send

~~~text
Producer calls send
   ├─ Returns successfully → send completes per JMS provider/QoS guarantees
   │                      → does not yet prove the listener has processed it
   └─ Throws JMSException  → operation failed
                          → cannot be certain whether the broker received it
~~~

Synchronous `MessageProducer.send(...)` can throw `JMSException` or subtypes like `InvalidDestinationException` and `MessageFormatException`. For a network failure right as the broker receives the message before the acknowledgment reaches the client, the application may **not know for sure** the actual outcome; retrying can produce a duplicate send. Never assume "an exception means the message definitely never reached the broker".

Send retry design should classify failures:

- **Non-recoverable immediately:** payload violates contract, invalid/unauthorized destination, invalid name or configuration; fix input or configuration.
- **Transient:** broker unavailable, timeout, dropped connection; retry with limits, backoff, and alerting.
- **Unknown outcome:** timeout or lost response near broker receipt; retry using a stable business identifier paired with an idempotent consumer.

JMS does not replace a **transactional outbox** when requirements state "the DB records the event and the message is guaranteed to be published" in the same business operation. If you commit the DB first and then send via JMS and the process crashes in between, the message may never be sent; if you send first and the DB rolls back, the message may describe a state that never existed. Outbox solves this by writing business state and the event record in the **same DB transaction**, then having a publisher dispatch safely; consumers must still tolerate duplicate deliveries.

### 7.2. Delivery and Processing Are Two Different Scopes

| Signal | What You Know | What You Cannot Conclude |
| --- | --- | --- |
| Synchronous `send` returns normally | The provider completed the send operation per QoS contract | That the consumer received/committed it |
| `message.getJMSMessageID()` is non-null | The provider assigned a JMS message ID | That the business event occurred only once |
| Broker queue depth increases | The broker is holding messages awaiting processing, as of that moment | That consumers will process accurately or immediately |
| Consumer reports success | The handler completed one execution path | That external side effects have an exactly-once guarantee |
| `eventId` inserted into DB with unique constraint | Rejects reapplying the same event within that designed transaction scope | That external systems outside the DB are also automatically deduplicated |

For critical messaging, monitor both the publisher side (send success/error/latency, retry/outbox backlog) and broker/consumer side (queue depth, message age, DLQ, redeliveries, processing time), rather than concluding success from a "send called" log alone.

## 8. Local JMS Transactions: Send Both Messages or Neither

In a **Java SE or Jakarta EE application-client environment**, a transacted JMS session can group multiple sends into a single local transaction. The provider commits those JMS operations only when `session.commit()` is called; `session.rollback()` cancels uncommitted sends. Example:

~~~java
package com.example.jms;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

public final class TransactionalSender {
    public static void publishPair(ConnectionFactory factory)
            throws JMSException {

        try (Connection connection = factory.createConnection();
             Session session = connection.createSession(
                     true, Session.SESSION_TRANSACTED)) {

            Queue queue = session.createQueue("orders.events");
            try (MessageProducer producer = session.createProducer(queue)) {
                try {
                    producer.send(
                            session.createTextMessage("order-created:O-42"));
                    producer.send(
                            session.createTextMessage("audit-created:O-42"));
                    session.commit();
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
    }
}
~~~

**Scope:** This is a local JMS transaction example; the provider and broker must support it accordingly. Inside a Jakarta EE web/EJB container or a container-managed JTA transaction, session creation and `commit/rollback` rules differ from Java SE; let the container transaction manager coordinate rather than calling `commit()` directly.

**Expected result:** both sends in the same session/transaction are committed as one JMS unit, or rolled back together if an error occurs before commit. However, if the network drops right during `commit`, the producer still might not know for sure whether the broker committed; unique event IDs and retry logic remain valuable.

**Critical limitation:** a local JMS transaction **does not automatically encompass** SQL database transactions, HTTP calls, or email sends. To coordinate DB → JMS, prefer outbox/idempotency per application requirements; distributed transactions require dedicated design, infrastructure, and trade-offs.

## 9. Asynchronous Send with CompletionListener

Since **JMS 2.0** (and Jakarta Messaging 3.x), `MessageProducer` provides asynchronous send overloads. Syntax:

~~~java
producer.send(message, new CompletionListener() {
    @Override
    public void onCompletion(Message completedMessage) {
        System.out.println("JMS send completed");
    }

    @Override
    public void onException(Message failedMessage, Exception cause) {
        System.err.println("JMS send failed: " + cause.getMessage());
    }
});
~~~

This snippet is **part of a method** that already has a valid `producer` and `message` and imports `jakarta.jms.CompletionListener` and `jakarta.jms.Message`; it is not a standalone `main` program. The lifecycle owner must keep resources alive long enough for the callback to run and track outcomes inside the callback.

Key rules:

1. **Returning from `send(..., CompletionListener)` does not mean the send is finished.** Only when the provider calls `onCompletion` does the application have confidence equivalent to a successful synchronous send. `onException` reports an error, yet it may still be **uncertain whether the broker received the message**.
2. If an error is detected and thrown directly **inside the `send` call**, do not expect the callback to also be invoked for that send. When the error cannot be thrown synchronously, the provider calls `onException`.
3. **Do not read/modify headers, properties, or body of that `Message` after `send` returns until the callback fires**: the provider may be using and mutating the object on another thread. After `onException`, provider-set header values may be undefined.
4. The callback **must not call `close()` on its own producer/session/connection or `commit()/rollback()` on its owning session**. Do not use the session from the callback concurrently with another application thread.
5. The provider guarantees callback ordering matching the sends on the same producer and does not invoke callbacks on the thread calling `send`. **The session remains a single-logical-thread context**; callbacks do not make it thread-safe.
6. When `close` is called on a producer/session/connection, or `commit/rollback` on a transacted session, the provider must wait for pending async sends and their associated callbacks to finish. Understand the shutdown impact and prevent hanging callbacks.
7. Async send methods have usage restrictions inside Jakarta EE web/EJB containers; check environment and provider rules. Standalone Spring Boot apps can use them, but must manage lifecycle and errors carefully.

**When should you use async?** When throughput or broker round-trip latency is a proven bottleneck and the system genuinely manages callbacks, backpressure, shutdown, and retry/outbox. Do not choose async merely to make the API "non-blocking": it complicates confirmation boundaries and error handling.

## 10. MessageProducer in Spring JMS: What Does JmsTemplate Help With?

In Spring applications, `JmsTemplate` manages acquiring a session, creating messages/producers, sending, and releasing resources according to the configured `ConnectionFactory` and transaction context. Application code normally **does not hold `MessageProducer` as a singleton**; instead, use `JmsTemplate.send(...)` when building a `Message` manually and `convertAndSend(...)` when letting a converter build the message from a Java object.

Example of two classes that can live in the same file `src/main/java/com/example/jms/JmsOutboundConfiguration.java` of a Spring Boot 3.x app connected to a JMS provider:

~~~java
package com.example.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.TextMessage;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Configuration
public class JmsOutboundConfiguration {
    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(4);
        template.setTimeToLive(300_000L);
        return template;
    }
}

@Component
class OrderEventPublisher {
    private final JmsTemplate jmsTemplate;

    OrderEventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String eventId) {
        jmsTemplate.send("orders.events", session -> {
            TextMessage message = session.createTextMessage(
                    "{\"type\":\"OrderCreated\",\"orderId\":\"O-42\"}");
            message.setStringProperty("eventId", eventId);
            message.setStringProperty("eventType", "OrderCreated");
            return message;
        });
    }
}
~~~

**Easy-to-miss detail:** `JmsTemplate.setDeliveryMode/ setPriority/ setTimeToLive` do not necessarily take effect unless **`setExplicitQosEnabled(true)`** is enabled. By default, Spring may let the provider use QoS administered on the `ConnectionFactory`. Always verify actual values on the broker rather than just reading bean properties. Spring also supports `JmsTemplate.setDeliveryDelay(...)` with JMS 2.0+; set it only when the provider supports it.

The example above is **code inside a Spring Boot application** (requiring starter/provider, broker, destination, package scanning, and configuration). It has no fixed stdout and is not a standalone program run directly with `javac`/`java`. When publish outcomes must be tracked, handle exceptions at the business layer and add outbox/retry where consistency is required.

**Quick comparison:**

| Send Style | Main Objects | Best Suited For |
| --- | --- | --- |
| Classic JMS | `Session` + `MessageProducer` | Learning lifecycle/QoS/async/transactions; low-level integration |
| Simplified JMS | `JMSContext` + `JMSProducer` | Convenient, fluent API with less boilerplate |
| Spring JMS | `JmsTemplate` + `MessageCreator` or converter | Integrating DI, configuration, resource management, and transactions with Spring |

`JMSProducer` is a **different interface** from `MessageProducer`. Simplified API example:

~~~java
try (var context = connectionFactory.createContext()) {
    Queue queue = context.createQueue("orders.events");
    context.createProducer()
            .setTimeToLive(60_000L)
            .send(queue, "OrderCreated:O-42");
}
~~~

`JMSProducer.send(Destination, String)` belongs to the simplified API and creates an appropriate message; this signature is **not** an overload of `MessageProducer`. `JMSContext` owns the session/connection lifecycle in the example. Exceptions in the simplified API are typically `JMSRuntimeException` (unchecked) rather than the checked `JMSException` of the classic API.

## 11. Publisher-Side Design Decisions

### 11.1. Sending a Command vs. Publishing an Event

- **Command** such as `CreateInvoice`: usually sent to a queue dedicated to one task type. The message must carry enough data for a worker to execute; consider timeouts, retries, and idempotency.
- **Event** such as `OrderCreated`: can be published to a topic for independent subscriptions to receive. If offline subscribers must catch up, design proper durable subscriptions/retention; that is a destination/subscriber setting, **not a property of a `MessageProducer`**.
- **Request–reply**: `JMSReplyTo` and `JMSCorrelationID` route replies and correlate requests; timeouts, cleanup, and duplicate response handling are still needed.

### 11.2. What Does a Safe Send Retry Strategy Need?

1. **Stable business key**: the `eventId` must stay unchanged across retries; do not generate a new ID on every attempt if it represents the same event.
2. **Recoverable state**: if publishing is tied to a DB transaction, use an outbox; the publisher can retry when the broker is unavailable or when a send result is unknown.
3. **Backoff and limits**: avoid tight loops that overwhelm the broker. Separate permanent errors (payload/permission) from transient errors.
4. **Idempotent consumer**: messages may be sent or delivered more than once; the consumer applies business changes keyed by a unique identifier / transaction.
5. **Observability**: measure send failure rate, retry count, publish latency, outbox lag, queue depth, and message expiration, rather than concluding success from a "send called" log.

### 11.3. Resources, Performance, and Safety

- **Never share a `Session` across multiple threads**; a `Connection` can support multiple sessions, but each session has its own ownership/lifecycle. A `MessageProducer` tied to that session is not an arbitrarily thread-safe shared singleton publisher.
- Opening/closing a connection on every send can be very expensive. Use Spring/provider-managed caching/pooling under load; do not write a custom `Session` pool that ignores transactions and closing rules.
- Define **payload size** and sensitive-data policies; avoid logging credentials or secrets. Restrict publish permissions per destination.
- **PERSISTENT** usually carries higher storage overhead than NON_PERSISTENT; reduce durability only when business requirements allow. High-throughput producers must also account for broker capacity and backpressure.
- Retries, priority, and delay do not replace consumer-side error handling: a **DLQ** primarily handles messages that cannot be consumed successfully; publish failures before reaching the broker need separate publisher-side mechanisms.

## 12. Hands-On Exercises in Order

**Exercise 1 – Fixed destination:** Create a non-transacted `Session`, a queue, and a `MessageProducer`, and send a `TextMessage` containing `eventId`. Inspect `JMSMessageID` after synchronous `send` and inspect the message on the broker. Ask: which step has been verified, and which has not?

**Exercise 2 – Unidentified producer:** Call `session.createProducer(null)` and send two different `TextMessage` instances to two destinations. Try calling `send(message)` without a destination and observe the API exception. Do not test errors directly against a production broker.

**Exercise 3 – QoS:** Send messages with `PERSISTENT`/`NON_PERSISTENT`, priority 4/8, and a 5-second TTL. Restart the broker in a test environment and observe what survives, actual ordering, and expiration. Do not assume every broker behaves identically.

**Exercise 4 – Delay vs. TTL:** Set `deliveryDelay` to 10 seconds and `TTL` to 5 seconds; check whether the message reaches the consumer. Then change TTL to 30 seconds. Explain why "send succeeded" can still lead to no delivery.

**Exercise 5 – Atomic JMS send:** Use a transacted session to send two messages, intentionally throw an exception before `session.commit()`, and call `rollback()`; verify the broker does not expose the two uncommitted messages. Repeat with a successful `commit()`. Contrast with a DB operation outside the JMS transaction.

**Exercise 6 – Async completion:** Use `CompletionListener` and log exact timestamps when calling `send`, when `send` returns, and when the callback arrives. Do not read the `Message` object before the callback. Test with an unavailable broker and distinguish synchronous exceptions from `onException` callbacks.

**Exercise 7 – Lost send response:** In a broker/network test, simulate a communication failure right as a send completes, retry with **the same `eventId`**, and verify consumer idempotency. Record the "unknown outcome" case rather than forcing the answer to "sent" or "not sent".

### Self-Assessment Checklist

- I can distinguish `MessageProducer`, `JMSProducer`, and `JmsTemplate`, and know which object owns the `Session`.
- I remember the signature of `send(message, deliveryMode, priority, timeToLive)` and that TTL/delay units are milliseconds.
- I know when to use `createProducer(destination)` vs. `createProducer(null)` and choose the matching `send` overload.
- I build body/properties before `send`, understand provider-assigned headers set upon sending, and do not misuse `JMSMessageID` as a business event ID.
- I can explain sync return, async callback, unknown-outcome failures, JMS transactions, and boundaries with separate DB transactions.
- I can design experiments to test message expiry, broker failure, retries, and deduplication with concrete observable evidence.

## References

1. [Jakarta Messaging 3.1 – MessageProducer Javadoc](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer): full `send` overloads, QoS, delivery delay, lifecycle, and async completion.
2. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): sections on producing, threading, delivery mode, TTL, delay, transactions, and exception semantics.
3. [Jakarta Messaging 3.1 – Session Javadoc](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session): session factory, `createProducer`, local transactions, and resource lifecycle.
4. [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate` and explicit QoS configuration.

**Key takeaway:** `MessageProducer` handles **the send operation** and message delivery options; applications must still design transactions, retries, business identifiers, deduplication, and end-to-end observability to achieve real reliability.