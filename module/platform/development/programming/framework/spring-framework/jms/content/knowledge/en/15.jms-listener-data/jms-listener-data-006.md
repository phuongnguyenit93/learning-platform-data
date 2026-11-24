# Receiving Session to Send Custom Replies in @JmsListener — Spring Framework JMS

## 1. Learning Objectives

A typical `@JmsListener` only receives a payload and executes business logic:

~~~java
@JmsListener(destination = "orders.requests")
public void handle(String payload) {
    System.out.println(payload);
}
~~~

When the system needs to **create replies using the native JMS API**, Spring lets you declare an additional **`jakarta.jms.Session`** parameter on the method. This is the Session currently used by the listener container to process the request, allowing the responder to create a `MessageProducer`, various `Message` types, and send to the original message's `JMSReplyTo`.

This lesson helps you:

1. Declare a `@JmsListener` receiving **raw `jakarta.jms.Message`/`TextMessage` and `Session`**.
2. Distinguish the listener's `Session` from `ConnectionFactory`, `JmsTemplate`, producer, JMS message, and destination.
3. Read `JMSReplyTo`, handle null cases, create replies with `Session.createTextMessage(...)`, and send with `Session.createProducer(...)`.
4. Preserve `JMSCorrelationID` according to the request-reply protocol; know when to use the request's `JMSMessageID`.
5. Customize the body, headers/properties, delivery mode, priority, and TTL without altering request consumption.
6. Understand local JMS transactions: **request ACK and reply send can commit/roll back together** when using one transacted Session.
7. Know why you **must not** call `commit()`, `rollback()`, `close()`, or store the Session in a field inside a container-managed listener.
8. Distinguish manual sending from return value/`@SendTo`/`JmsResponse`, avoiding **double replies**.
9. Run a **Java 17, Spring Boot 3.5, Artemis** example: requester uses `JmsTemplate.sendAndReceive(...)`, responder uses injected Session.
10. Diagnose request timeouts, lost replies, duplicates, wrong correlation, expired temporary queues, transaction errors, and DLQ.

> **Core takeaway:** The `Session` injected into an annotated listener is a resource **owned by the listener container**. Use it **directly inside the callback** to create and send replies; let the container/transaction manager handle commit, rollback, close, and recovery.

## 2. How Does Request-Reply Work?

~~~text
Requester                             Responder / @JmsListener
     |                                         |
     | 1. create request TextMessage           |
     |    JMSReplyTo = temporary queue Q       |
     |    JMSCorrelationID = "req-42"          |
     |                                         |
     +------ send(request) ---> requests.queue +
                                               |
                                 2. receive Message + Session
                                               |
                                 3. process payload
                                               |
                                 4. create reply TextMessage
                                    with same Session
                                               |
                                 5. attach correlation, headers
                                               |
    <---- receive(reply) <--- reply queue Q ----+
     |                                         |
     | 6. check correlation/status             |
     v                                         v
~~~

Three special headers:

| Header | Who sets it? | Purpose |
|---|---|---|
| `JMSReplyTo` | Requester, before send | The `Destination` address where the requester wants to receive replies |
| `JMSCorrelationID` | Application, usually on both request and reply | Correlates messages belonging to the same exchange |
| `JMSMessageID` | JMS provider on send | Identifies a JMS message; can serve as correlation key under an alternative protocol |

**Do not conflate** these three fields: `JMSReplyTo` is a `Destination`, whereas correlation is a `String`/provider-native value. The reply usually gets a **new `JMSMessageID`** assigned by the provider; the responder must not set the reply's `JMSMessageID` to the request's ID.

### 2.1. How the Requester Receives Replies

- **TemporaryQueue**: convenient for short-lived request-reply; the owning connection creates a consumer to await replies, while responders on other connections can send to it.
- **Fixed reply Queue**: can survive requester restarts, but requires handling correlation selectors, permissions, and orphaned messages/TTL.
- **Topic reply**: requires managing subscription lifecycles; an offline non-durable subscriber can miss replies.

`JMSReplyTo` can hold a Queue, Topic, or TemporaryQueue; do not guess the type from a name string. A provider-managed `TemporaryQueue` has a special identity: **do not reconstruct it from an arbitrary String**.

## 3. Why Can @JmsListener Receive Session?

Spring's annotation infrastructure creates a listener container for annotated endpoints. `MessagingMessageListenerAdapter` exposes the raw incoming `Message` and native `Session` as **additional arguments** that `DefaultMessageHandlerMethodFactory`/argument resolvers can pass into the method.

Parameter types supported by Spring include:

- Raw `jakarta.jms.Message` or a subclass like `TextMessage`, when matching the incoming type.
- **`jakarta.jms.Session`**, for accessing the native JMS API.
- Regular Java payloads (`String`, DTO, etc.) via a message converter.
- `org.springframework.messaging.Message<T>` containing payload and mapped headers.
- `@Header(...)` for a single header and `@Headers Map<...>` for multiple headers.

This is an official feature of **Spring Framework 6+**; no custom resolver is needed just to receive `Session`.

### 3.1. Minimal Example

~~~java
import jakarta.jms.Message;
import jakarta.jms.Session;
import jakarta.jms.JMSException;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class NativeResponder {

    @JmsListener(destination = "orders.requests")
    public void onRequest(Message request, Session session)
            throws JMSException {

        System.out.println(
                "incomingMessageId=" + request.getJMSMessageID());
        System.out.println(
                "sessionTransacted=" + session.getTransacted());
    }
}
~~~

This class **is not standalone runnable**: it needs a Spring context, `@EnableJms`, a JMS connection factory, a listener container, and a broker. However, the `Message request, Session session` signature is valid.

### 3.2. Receiving TextMessage Directly

~~~java
@JmsListener(destination = "orders.requests")
public void handle(TextMessage request, Session session)
        throws JMSException {

    String orderId = request.getText();
    Destination replyTo = request.getJMSReplyTo();
}
~~~

Spring passes a raw `TextMessage` into the parameter if the request is indeed a TextMessage. If the sender sends a `BytesMessage`, `MapMessage`, or mismatched type, the listener must adjust its signature or convert appropriately. Never assume every message is a `TextMessage`.

### 3.3. Payload and Session Together

~~~java
@JmsListener(destination = "orders.requests")
public void handle(String payload, Session session) throws JMSException {
    // payload is converted.
    // session is injected independently of payload.
}
~~~

This is a simple option when a **fixed reply destination** is already known. To access `request.getJMSReplyTo()` directly or raw provider headers, add raw `Message` or switch the signature to raw `Message` + `Session`.

### 3.4. Jakarta Namespace and Java 17

With Spring Framework 6.x and Spring Boot 3.x:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
~~~

Do not mix `javax.jms` (common in legacy Spring 5 projects) into Spring 6 JMS configuration.

## 4. Sending a Manual Reply Inside a Listener

### 4.1. Minimal Example Handling Missing Destination

~~~java
@JmsListener(destination = "orders.requests")
public void onRequest(TextMessage request, Session session)
        throws JMSException {

    Destination replyTo = request.getJMSReplyTo();
    if (replyTo == null) {
        throw new IllegalArgumentException(
                "Request has no JMSReplyTo destination");
    }

    TextMessage reply = session.createTextMessage(
            "accepted:" + request.getText());

    String correlationId = request.getJMSCorrelationID();
    if (correlationId == null || correlationId.isBlank()) {
        throw new IllegalArgumentException(
                "Missing JMSCorrelationID");
    }

    reply.setJMSCorrelationID(correlationId);
    reply.setStringProperty("statusCode", "ACCEPTED");

    try (MessageProducer producer = session.createProducer(replyTo)) {
        producer.send(reply);
    }
    // Do not commit, roll back, or close the container-provided Session.
}
~~~

This is a **method snippet**, which can live inside a Spring-scanned `@Component` class. Main steps:

1. Read `request.getJMSReplyTo()`.
2. Validate the destination per contract.
3. Use the **injected Session** to create a **new message**.
4. Copy the correlation chosen by the requester.
5. Attach a status code via a JMS property.
6. Create a producer from the same Session; send the reply.
7. Close the **producer created by the method**, not the Session.
8. Let the method return normally or throw an error for the container to handle the transaction.

### 4.2. Why Not Resend the Incoming Message?

~~~java
// Anti-pattern:
producer.send(request);
~~~

The incoming Message carries body/headers/properties belonging to the request, potentially including provider-managed fields and sensitive data. The provider may also reset ID/timestamp on send. Resending the original message blurs semantics. Creating a fresh reply clearly defines:

- Message type (`TextMessage`, `BytesMessage`, etc.).
- Body and schema.
- Status/result headers.
- Correlation ID.
- TTL and delivery mode.
- Data security rules.

### 4.3. Creating an Unbound Producer

~~~java
try (MessageProducer producer = session.createProducer(null)) {
    producer.send(replyTo, reply);
}
~~~

The classic JMS API allows creating a producer with `Destination=null` and specifying the destination per send call. This is useful when sending multiple messages to different destinations in the same Session. Do not emit multiple replies for a single request unless the protocol explicitly dictates it.

### 4.4. Do You Need to Call Session.createQueue(...)?

No, if `JMSReplyTo` already holds a valid `Destination`:

~~~java
Destination replyTo = request.getJMSReplyTo();
MessageProducer producer = session.createProducer(replyTo);
~~~

If you try `session.createQueue(replyTo.toString())`, you may construct an invalid reference, especially for a TemporaryQueue. Always use **the exact Destination object carried on the request**.

## 5. Handling a Null JMSReplyTo

`JMSReplyTo` is an optional header; not every message expects a response. There are three valid policies, which must be chosen by the **business contract**:

| Policy | Purpose | Action |
|---|---|---|
| Reply required | Request-reply RPC/command | Reject the request if `JMSReplyTo` is missing |
| Reply to default queue | System defines a stable fallback | Send to a pre-provisioned Queue known to the requester |
| No reply needed | Event/fire-and-forget | Process and return normally |

Fixed fallback example:

~~~java
Destination replyTo = request.getJMSReplyTo();
if (replyTo == null) {
    replyTo = session.createQueue("orders.responses");
}
~~~

This is only a **snippet**. `Session.createQueue(name)` creates a **Queue object reference**, **without guaranteeing physical queue provisioning** on the broker; provisioning or proper auto-create policy is required.

If missing `JMSReplyTo` is an **unrecoverable** error, infinite rollback only causes a poison loop. Route the request to a DLQ/quarantine or report the error through a managed channel; never construct physical queue names from user input.

### 5.1. A TemporaryQueue Can Disappear When the Requester Closes Its Connection

Per Jakarta Messaging, temporary destinations are scoped to the owning connection. Only that connection may create a consumer on the temporary destination, **though other connections can send to it** if they hold the destination reference and appropriate permissions.

Scenario:

~~~text
Requester creates TemporaryQueue Q
   |
   +-- sends request containing JMSReplyTo=Q
   |
   +-- waits for reply 3s
   |
   +-- timeout, closes connection → Q is deleted
                                |
Responder processes slowly 10s -+
   |
   +-- send reply to Q → may fail
~~~

JMS does not guarantee a TemporaryQueue survives after the requester connection closes. Therefore, design deadlines/timeouts/late-reply policies. If a responder takes minutes and the requester may go offline, a fixed reply Queue or async callback workflow may be more appropriate.

### 5.2. Reply Destinations and Security

Do not treat `JMSReplyTo` as blindly trustworthy. If an application receives messages from untrusted sources and uses a principal permitted to send to any Queue, an attacker could supply an unintended reply destination. In multi-tenant systems:

- Broker ACLs must restrict `send` by account/namespace.
- Where the contract permits, validate destination names/types and reply policies.
- Never log full sensitive payloads/headers.
- Use quotas/TTLs to bound temporary resources.
- Never create physical Queues arbitrarily from `JMSReplyTo.toString()`.

## 6. Designing Correlation IDs

### 6.1. Two Widely Used Patterns

**Pattern A — requester generates the ID upfront:**

~~~text
Request:
  JMSCorrelationID = req-42
  JMSMessageID = ID:provider-request-1

Reply:
  JMSCorrelationID = req-42
  JMSMessageID = ID:provider-reply-2
~~~

The responder echoes the request correlation onto the reply. This is the pattern used in the demo.

**Pattern B — reply uses the request's JMSMessageID as correlation:**

~~~text
Request:
  JMSCorrelationID = null
  JMSMessageID = ID:provider-request-1

Reply:
  JMSCorrelationID = ID:provider-request-1
~~~

The two patterns are not equivalent on the requester side. If the consumer on the reply queue uses selector `JMSCorrelationID = 'req-42'`, a Pattern B response **will not match**. Agree on one protocol before implementing.

### 6.2. When a Fallback Policy Applies

~~~java
String correlation = request.getJMSCorrelationID();

if (correlation == null || correlation.isBlank()) {
    // Only do this if the protocol allows using the request ID.
    correlation = request.getJMSMessageID();
}

if (correlation == null || correlation.isBlank()) {
    throw new IllegalArgumentException("Cannot derive correlation ID");
}

reply.setJMSCorrelationID(correlation);
~~~

Fallback itself is not wrong, but it is only appropriate when the requester genuinely accepts Pattern B. `JMSMessageID` can be null if the provider honors an ID-disable hint. Consequently, **if the contract requires an application correlation ID, do not fall back automatically**; reject requests missing the header.

### 6.3. Using the Right Getter/Setter

~~~java
String receivedCorrelation = request.getJMSCorrelationID();
reply.setJMSCorrelationID(receivedCorrelation);
~~~

Do not call `reply.setJMSMessageID(request.getJMSMessageID())`: the reply's ID is assigned by the provider upon sending. `JMSCorrelationID` is the application-set field linking request and response.

### 6.4. Correlation ID Does Not Replace Event ID

`JMSCorrelationID` may represent an entire workflow spanning multiple events. For retries/redeliveries, a **stable business request ID/event ID** is required to ensure idempotency. `JMSXDeliveryCount` and `JMSRedelivered` also do not prove the business handler succeeded on a prior delivery attempt.

## 7. Customizing the Reply Body and Application Properties

`Session` provides message factory methods:

~~~java
TextMessage text = session.createTextMessage("ok");
BytesMessage bytes = session.createBytesMessage();
MapMessage map = session.createMapMessage();
ObjectMessage object = session.createObjectMessage();
~~~

These are native Jakarta JMS types, not Spring Messaging Messages. In practice:

- `TextMessage`: JSON/text if the requester expects text.
- `BytesMessage`: binary payload with a clear format/schema.
- `MapMessage`: key-value data restricted to JMS-supported types.
- `ObjectMessage`: Java serialization; carries security/class-compatibility risks. Do not use arbitrarily across services.

### 7.1. Creating a Text Reply with Metadata

~~~java
TextMessage reply = session.createTextMessage(
        "{\"status\":\"ACCEPTED\",\"orderId\":\"42\"}");

reply.setJMSCorrelationID("req-42");
reply.setStringProperty("statusCode", "ACCEPTED");
reply.setStringProperty("schemaVersion", "1");
reply.setStringProperty("requestEventId", "evt-42");
~~~

The JSON here is a fixed example. In real applications, do not concatenate user input to build JSON; use a serializer and schema validation. `JmsTemplate`'s `MessageConverter` **does not run automatically** when you create a raw `TextMessage` via `Session`.

### 7.2. Headers and Properties Should Not Be Copied Blindly

JMS has provider-owned headers like `JMSMessageID`, `JMSTimestamp`, `JMSExpiration` and app-set fields like `JMSCorrelationID`. **Do not copy all headers** from request to reply; select only the minimal fields required by the contract, such as correlation, `schemaVersion`, `eventId`, and `statusCode`.

JMS properties starting with `JMSX` or `JMS_` have special provider/spec rules. Create application properties like `statusCode` and `requestEventId`; do not arbitrarily place fields into reserved namespaces.

### 7.3. QoS Per Reply: Delivery Mode, Priority, and TTL

You can use the producer `send` overload:

~~~java
import jakarta.jms.DeliveryMode;

try (MessageProducer producer = session.createProducer(replyTo)) {
    producer.send(
            reply,
            DeliveryMode.PERSISTENT,
            4,
            10_000L);
}
~~~

- `DeliveryMode.PERSISTENT` requests persistent delivery per spec/provider; it does not make a TemporaryQueue outlive connection closure.
- Priority ranges from 0 to 9, with 4 as the usual default; it is not an absolute ordering SLA.
- TTL of 10,000 ms; once expired, the broker may avoid delivering the message.
- These producer options apply to that reply send and do not alter the requester's `JmsTemplate` configuration.

You do not need `JmsTemplate.setExplicitQosEnabled(true)` when using **`MessageProducer` directly**. The `explicitQosEnabled` property configures how `JmsTemplate` invokes send.

### 7.4. Requester Timeout Differs from Reply TTL

A requester may wait 5 seconds; reply TTL may be 10 seconds; the request business deadline may be 3 seconds. Those three mechanisms differ:

| Parameter | Who applies it? | Meaning |
|---|---|---|
| Receive timeout | Requester | Maximum time to wait |
| Reply TTL | Producer and broker | How long the reply stays alive/deliverable |
| Business deadline | Application | Whether the request still holds business validity |

If the requester times out, a late reply can become orphaned. With a temporary queue, closing the requester connection prevents the reply from being received as before. Design late-reply handling, DLQ, logging, and retries.

## 8. Lifecycle of Listener-Container-Owned Session

### 8.1. What Can Be Used Inside the Callback?

~~~java
@JmsListener(destination = "orders.requests")
public void handle(Message request, Session session) throws JMSException {
    Destination replyTo = request.getJMSReplyTo();
    // Create Message, MessageProducer, and send reply here.
}
~~~

Do:

- Read incoming headers/payload.
- Create native JMS Messages using the container-supplied Session.
- Create a producer, send the reply, and close the producer you created.
- Return normally or throw an appropriate exception so the container manages the transaction.

Do not:

~~~java
session.commit();   // Container/transaction manager owns commits.
session.rollback(); // Do not inject your own transaction boundary.
session.close();    // Do not close container-owned resources.
~~~

If the listener factory uses a transacted Session, commit/rollback is controlled by the container **after the callback finishes**. In JTA-managed sessions, transaction rules belong to the JTA manager, making manual commits even more inappropriate.

### 8.2. Do Not Store Session in a Singleton Field

~~~java
// Anti-pattern: unsafe regarding lifecycle and concurrency.
private Session savedSession;

@JmsListener(destination = "orders.requests")
public void onMessage(Message request, Session session) {
    savedSession = session;
}
~~~

A Session is sequential and must only be driven by one thread at a time. After the callback, the container may return the Session to a cache, commit, roll back, or close it. Using `savedSession` from another thread can cause races, provider errors, or sending messages in the wrong transaction.

### 8.3. Do Not Pass Session to an Executor

~~~java
// Anti-pattern:
executor.submit(() -> sendReplyLater(session, request));
~~~

The callback may return before the task executes; the Session has already left the method's lifecycle. If asynchronous processing is needed, copy **immutable data** such as `requestId`, payload, and destination per contract; then start a new JMS operation via `ConnectionFactory`/`JmsTemplate` with its own transaction and error handling. However, that reply send **no longer participates in the request's JMS transaction**.

### 8.4. Close the Producer You Created

~~~java
try (MessageProducer producer =
             session.createProducer(replyTo)) {
    producer.send(reply);
}
~~~

Classic JMS `MessageProducer` implements `AutoCloseable`; closing the producer does not close the Session. If a producer's lifecycle is managed differently by a pool/provider, follow that mechanism, yet the general rule holds: **the listener never closes the container's Session**.

## 9. Transactions: Receiving Request and Sending Reply in the Same Session

### 9.1. With a Transacted Factory

If the listener container is configured with:

~~~java
factory.setSessionTransacted(true);
~~~

then, within a local JMS transaction, the listener receives request M and sends reply R through **that exact same Session**:

~~~text
JMS Transaction T
    |
    +-- receive request M
    |
    +-- process payload
    |
    +-- producer.send(reply R) on same Session
    |
    +-- listener method returns
    |
    +-- container COMMITS T
             |
             +-- ACK request M
             +-- publish reply R
~~~

If the method throws an exception causing the container to roll back:

~~~text
JMS Transaction T
    |
    +-- receive request M
    +-- producer.send(reply R)
    +-- exception
    |
    +-- container ROLLS BACK T
             |
             +-- M may be redelivered
             +-- uncommitted R is discarded
~~~

**This is local JMS atomicity**, not a guarantee that every database update or external API call automatically rolls back. Once the requester sees the reply, the responder's JMS transaction has allowed the reply to be delivered; yet non-JMS business state still requires careful design.

### 9.2. Why Not Arbitrarily Use Another JmsTemplate?

~~~java
// Inside listener:
jmsTemplate.convertAndSend("orders.responses", "accepted");
~~~

This is a valid way to send, but you must **not automatically assume** it runs in the same Session/transaction that received the request. `JmsTemplate` may acquire a different Session from `ConnectionFactory`/wrappers; with `JmsTransactionManager` or JTA, resource binding follows specific rules. If the goal is protecting **request ACK + reply send within the same local JMS transaction**, using the **injected Session** is the clearest approach in this lesson.

### 9.3. What If the Factory Is Non-Transacted?

In `DefaultMessageListenerContainer`, default `AUTO_ACKNOWLEDGE` may acknowledge the message **before the callback finishes** (or without transaction rollback). If sending the reply fails, the request may already be ACKed and not redelivered by the broker. Thus, when business reliability is required, configure a transacted listener and test send failures, exceptions, and broker restarts.

Do not treat `throws JMSException` on the method as sufficient on its own to guarantee retries under all ack modes.

### 9.4. Do Not Swallow Send Errors

~~~java
try {
    producer.send(reply);
} catch (JMSException ex) {
    logger.error("Cannot reply", ex);
    // WRONG if the method returns as if successful:
    // the container may commit the request.
}
~~~

If failure should trigger rollback, let `JMSException` propagate or throw a runtime exception:

~~~java
try {
    producer.send(reply);
} catch (JMSException ex) {
    throw new IllegalStateException("Reply send failed", ex);
}
~~~

Retry/backoff, max attempts, and DLQ handling must be explicitly designed across broker and container. A request missing a reply destination cannot be fixed by endless retries, so it needs quarantine or a protocol error policy.

### 9.5. Database and HTTP Side Effects Outside the Local JMS Transaction

Example:

~~~text
receive request
     |
     +-- DB update + DB COMMIT succeeds
     |
     +-- send reply in JMS transacted Session
     |
     +-- JMS COMMIT loses network, outcome unknown
     |
     +-- broker may redeliver request
~~~

A committed DB transaction **does not automatically roll back**. When the request is redelivered, the handler may update data a second time if idempotency is missing. Attach a stable `requestId`/`eventId` and use a unique constraint/idempotency record inside the same DB transaction as the business update, or use outbox/JTA/XA if the architecture demands it. External APIs/payments must also be handled idempotently.

### 9.6. Requester Transactions and Deadlock

A requester can accidentally do:

~~~text
requester transacted Session:
    send(request) uncommitted
    receive(reply) waiting
    commit() only called after reply
~~~

The responder cannot see the uncommitted request yet, so it cannot reply; the requester times out or logically deadlocks. For `JmsTemplate.sendAndReceive` in the demo below, we use a **non-transacted requester template** and do not wrap the call in an outer JMS transaction.

## 10. When to Use @SendTo or JmsResponse Instead of Session?

Spring supports automatic replies; choose the simplest approach that satisfies the contract.

### 10.1. Return Value and @SendTo

~~~java
@JmsListener(destination = "orders.requests")
@SendTo("orders.responses")
public String process(String orderId) {
    return "accepted:" + orderId;
}
~~~

Spring wraps the return value into a JMS Message and sends it to the request's `JMSReplyTo` if present, or to the default reply destination configured by `@SendTo`/listener. This is a great choice when the reply is just a simple payload.

### 10.2. JmsResponse for Runtime Destinations

~~~java
@JmsListener(destination = "orders.requests")
public JmsResponse<String> process(String orderId) {
    return JmsResponse.forQueue(
            "accepted:" + orderId,
            "orders.status");
}
~~~

`JmsResponse` belongs to `org.springframework.jms.listener.adapter`. This snippet illustrates returning a reply via return value while still selecting the destination at runtime. There is no need to touch a native Session directly when you want the framework to handle converters/replies.

### 10.3. Manual Session When Deep Control Is Needed

Use injected `Session` if you need to:

- Build a specific native `TextMessage`/`BytesMessage`.
- Inspect the exact `JMSReplyTo` object, especially a TemporaryQueue.
- Set correlation IDs and JMS properties precisely per protocol.
- Control per-send QoS on a native producer.
- Send the reply inside the listener's own local JMS transaction.
- Perform multiple sends in one transaction for a specific requirement.

### 10.4. Avoiding Double Replies

~~~java
// Anti-pattern: sending manually AND returning a String.
@JmsListener(destination = "orders.requests")
@SendTo("orders.responses")
public String handle(Message request, Session session)
        throws JMSException {
    sendReplyManually(request, session);
    return "accepted";
}
~~~

The framework may automatically send a reply from the return value, producing **two replies** for one request. When using `MessageProducer` to send a manual reply, the method should normally return `void` and should not use `@SendTo` to emit an extra reply.

## 11. End-to-End Demo: Java 17 + Spring Boot 3.5 + ActiveMQ Artemis

This example illustrates **the exact topic**:

- Requester calls `JmsTemplate.sendAndReceive(...)`.
- Spring `JmsTemplate` creates a **TemporaryQueue** and sets it as the request's `JMSReplyTo`.
- The request has app-defined `JMSCorrelationID="req-42"` and `eventId="evt-42"`.
- `@JmsListener` receives `TextMessage request` and `Session session`.
- The handler creates a reply using **that Session** and sends it to **`request.getJMSReplyTo()`**.
- The listener factory runs a local JMS transacted Session.
- Requester receives the reply and verifies **body, correlation, and statusCode**.

### 11.1. Prerequisites

- Java 17+, Maven 3.9+, Docker.
- Ports `61616` (messaging) and `8161` (console) free.
- No other consumer reading the demo queue.
- Use a dedicated test broker only; never send messages to production.

Run Artemis using the official image:

~~~bash
docker run --detach --rm --name jms-session-reply-demo \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Check broker logs:

~~~bash
docker logs jms-session-reply-demo
~~~

Demo Artemis normally enables queue auto-creation; environments with auto-create disabled must provision `lesson.session.reply.requests` and grant send/consume permissions. TemporaryQueues must also be supported by the broker with appropriate account permissions. Credentials here are for an isolated lab only.

### 11.2. Project Structure

~~~text
jms-session-reply-demo/
├── pom.xml
└── src/main/
    ├── java/example/SessionReplyApplication.java
    └── resources/application.properties
~~~

### 11.3. pom.xml

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
  <artifactId>jms-session-reply-demo</artifactId>
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

### 11.4. application.properties

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

### 11.5. SessionReplyApplication.java — Complete Java File

Create `src/main/java/example/SessionReplyApplication.java`:

~~~java
package example;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class SessionReplyApplication {

    private static final String REQUEST_QUEUE =
            "lesson.session.reply.requests";

    public static void main(String[] args) {
        SpringApplication.run(SessionReplyApplication.class, args);
    }

    @Bean
    JmsTemplate requesterTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        template.setSessionTransacted(false);
        template.setReceiveTimeout(10_000L);
        return template;
    }

    @Bean("replyListenerFactory")
    DefaultJmsListenerContainerFactory replyListenerFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        factory.setPubSubDomain(false);
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    ApplicationRunner runRequestReply(JmsTemplate requesterTemplate) {
        return args -> {

            Message reply = requesterTemplate.sendAndReceive(
                    REQUEST_QUEUE,
                    session -> {
                        TextMessage request =
                                session.createTextMessage("order-42");
                        request.setJMSCorrelationID("req-42");
                        request.setStringProperty("eventId", "evt-42");
                        return request;
                    });

            if (!(reply instanceof TextMessage response)) {
                throw new IllegalStateException(
                        "No TextMessage reply within 10 seconds");
            }

            String body = response.getText();
            String correlationId = response.getJMSCorrelationID();
            String status = response.getStringProperty("statusCode");

            if (!"accepted:order-42".equals(body)) {
                throw new IllegalStateException(
                        "Unexpected reply body: " + body);
            }
            if (!"req-42".equals(correlationId)) {
                throw new IllegalStateException(
                        "Correlation mismatch: " + correlationId);
            }
            if (!"ACCEPTED".equals(status)) {
                throw new IllegalStateException(
                        "Unexpected status: " + status);
            }

            System.out.println("replyBody=" + body);
            System.out.println("correlationId=" + correlationId);
            System.out.println("statusCode=" + status);
            System.out.println("verified=true");
        };
    }

    @Component
    public static class ReplyListener {

        @JmsListener(
                destination = REQUEST_QUEUE,
                containerFactory = "replyListenerFactory")
        public void onRequest(TextMessage request, Session session)
                throws JMSException {

            Destination replyTo = request.getJMSReplyTo();
            if (replyTo == null) {
                throw new IllegalArgumentException(
                        "JMSReplyTo is required");
            }

            String correlationId = request.getJMSCorrelationID();
            if (correlationId == null || correlationId.isBlank()) {
                throw new IllegalArgumentException(
                        "JMSCorrelationID is required");
            }

            String eventId = request.getStringProperty("eventId");
            if (eventId == null || eventId.isBlank()) {
                throw new IllegalArgumentException("eventId is required");
            }

            TextMessage reply = session.createTextMessage(
                    "accepted:" + request.getText());
            reply.setJMSCorrelationID(correlationId);
            reply.setStringProperty("statusCode", "ACCEPTED");
            reply.setStringProperty("requestEventId", eventId);

            try (MessageProducer producer =
                         session.createProducer(replyTo)) {
                producer.send(reply);
            }

            System.out.println("replySendInvoked=true");
            // Do not commit/roll back/close Session.
        }
    }
}
~~~

### 11.6. Code Explanation

1. **`JmsTemplate` on requester**: `sendAndReceive` uses the request queue as the send destination; automatically creates a TemporaryQueue for the reply and sets it on `JMSReplyTo`.
2. **Non-transacted requester**: if the request were sent in an uncommitted JMS transaction and waited for a reply in the same transaction, the responder would not see the request, causing deadlock/timeout.
3. **Listener factory**: uses `DefaultJmsListenerContainerFactoryConfigurer` to keep Boot defaults, then sets `sessionTransacted=true` and `concurrency=1`. No external JTA transaction manager is configured in this lab.
4. **`TextMessage request, Session session`**: Spring injects the two container-provided special objects.
5. **`JMSReplyTo`**: the exact TemporaryQueue created by `JmsTemplate`; no need to recreate queue names in the responder.
6. **Correlation**: request sets `req-42`, reply echoes the exact value; requester verifies it.
7. **Reply**: `session.createTextMessage`, set properties, `session.createProducer(replyTo).send(reply)`.
8. **Transaction**: reply send uses the same listener Session; the container commits both request and reply after the method succeeds.
9. **`void` method**: returns no value, avoiding Spring creating a second automatic reply.
10. **No DB**: the demo does not imply exactly-once business effects or distributed transactions.

### 11.7. Running

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

With a clean broker, no network/ACL errors, and no other consumers on the request queue, output from the application itself typically includes:

~~~text
replySendInvoked=true
replyBody=accepted:order-42
correlationId=req-42
statusCode=ACCEPTED
verified=true
~~~

The order between listener logs and requester logs depends on scheduling (although the reply can only be delivered after the listener's transaction commits in the transacted model). Spring Boot also logs startup and JMS infrastructure messages. If a timeout or wrong reply type occurs, the runner throws an exception and does not print `verified=true`.

In the Artemis console at `http://localhost:8161`, inspect the request queue depth and consumer count. The temporary reply queue may already be deleted automatically once the operation completes, so do not expect it to persist long-term.

Stop the app with `Ctrl+C`, then stop the broker:

~~~bash
docker stop jms-session-reply-demo
~~~

The image runs with `--rm` and no persistent volume, so demo data does not survive stopping; never use this configuration in production.

## 12. Replying with Request-Specific Custom QoS

When a reply only remains valid briefly, you can use the send overload:

~~~java
@JmsListener(
    destination = "orders.requests",
    containerFactory = "replyListenerFactory")
public void handle(TextMessage request, Session session)
        throws JMSException {

    Destination replyTo = request.getJMSReplyTo();
    if (replyTo == null) {
        throw new IllegalArgumentException("Missing JMSReplyTo");
    }

    String correlationId = request.getJMSCorrelationID();
    if (correlationId == null || correlationId.isBlank()) {
        throw new IllegalArgumentException("Missing correlation");
    }

    TextMessage reply = session.createTextMessage("ACCEPTED");
    reply.setJMSCorrelationID(correlationId);
    reply.setStringProperty("statusCode", "ACCEPTED");

    try (MessageProducer producer = session.createProducer(replyTo)) {
        producer.send(
                reply,
                jakarta.jms.DeliveryMode.PERSISTENT,
                6,
                3_000L);
    }
}
~~~

This is a snippet, not a standalone runnable file. A 3-second TTL may cause the reply to expire before the requester receives it if the broker/network is slow. `PERSISTENT` does not extend a temporary queue's lifetime past connection closure. Choose QoS based on SLAs and real benchmarks.

### 12.1. Sending an Error Reply When Business Validation Fails

If a request is protocol-valid yet violates a business rule (e.g., an already cancelled order), you can **send an error reply as a valid outcome**:

~~~java
TextMessage reply = session.createTextMessage("rejected:cancelled");
reply.setJMSCorrelationID(correlationId);
reply.setStringProperty("statusCode", "REJECTED");
reply.setStringProperty("reasonCode", "ORDER_CANCELLED");

try (MessageProducer producer = session.createProducer(replyTo)) {
    producer.send(reply);
}
// If policy defines this as a business outcome,
// the callback can return and the JMS transaction commits.
~~~

Do not turn every `JMSException`/database timeout into `REJECTED` and commit the request; infrastructure errors generally require rollback/retry rather than faking a business rejection.

### 12.2. When JMSReplyTo Is Permanently Missing

If a request is sent without `JMSReplyTo` when the contract requires it, repeated rollbacks can lead to a poison loop. Configure a retry limit, DLQ/quarantine, telemetry, and a process to fix the producer. Do not let one malformed request block the queue forever.

## 13. Requester Managing TemporaryQueue Directly (Classic JMS API)

`JmsTemplate.sendAndReceive` is convenient, though not the only option. If the requester needs custom selectors/consumers:

~~~java
// Snippet inside a method with a valid ConnectionFactory.
try (Connection connection =
             connectionFactory.createConnection();
     Session session = connection.createSession(
             Session.AUTO_ACKNOWLEDGE)) {

    Queue requests = session.createQueue("orders.requests");
    TemporaryQueue replyQueue = session.createTemporaryQueue();

    try (MessageProducer producer = session.createProducer(requests);
         MessageConsumer consumer =
                 session.createConsumer(replyQueue)) {

        connection.start();

        TextMessage request =
                session.createTextMessage("order-42");
        request.setJMSReplyTo(replyQueue);
        request.setJMSCorrelationID("req-42");

        producer.send(request);

        Message reply = consumer.receive(5_000L);
        if (reply == null) {
            throw new IllegalStateException("Reply timed out");
        }
        if (!"req-42".equals(reply.getJMSCorrelationID())) {
            throw new IllegalStateException("Wrong correlation");
        }
    }
}
~~~

This is a Java SE/standalone snippet requiring `jakarta.jms` imports and a broker. The TemporaryQueue is created by the requester session; the reply consumer also uses **the connection owning the temporary queue**, satisfying Jakarta Messaging's restriction. `connection.start()` is required for the consumer to receive.

**Do not replace the requester's `Session.AUTO_ACKNOWLEDGE` with `SESSION_TRANSACTED` while still waiting for a reply before committing**, because the uncommitted request may not be processed by the responder.

### 13.1. Fixed Reply Queue and Selector

If multiple requesters share a reply Queue, a consumer can filter by `JMSCorrelationID`:

~~~java
MessageConsumer consumer = session.createConsumer(
        replyQueue,
        "JMSCorrelationID = 'req-42'");
~~~

`replyQueue` in this snippet must be an appropriately provisioned `Queue`. Never concatenate raw user input into a JMS selector without validating/escaping; selectors have specific syntax and can fail or misroute. Generate correlation IDs with fixed charsets/formats and enforce permissions/namespaces across requesters.

## 14. Important Failure Modes

### 14.1. Producer Reports Send Success Yet Requester Times Out

Check:

1. Does `JMSReplyTo` point to the exact destination the requester is listening on?
2. Is the TemporaryQueue still alive? Did the requester close its connection?
3. Was the reply committed in the listener's transacted Session?
4. Does `JMSCorrelationID` match the contract and selector?
5. Does the broker allow send/consume permissions and proper destination routing?
6. Did the reply's TTL/expiration expire?
7. Is another consumer competing on a fixed reply queue?
8. Did the listener throw before sending, hit a conversion error, or move to DLQ?
9. Is the requester's receive timeout shorter than processing latency?
10. Did a failover or broker restart drop the subscription?

A `producer.send(reply)` log line inside the callback **does not prove** the requester received the reply.

### 14.2. Reply Sent Twice

Causes: listener sends manually via Session **and** returns a value causing Spring to send an automatic reply, or the request was redelivered and code lacks idempotency. Check whether the method is `void`, has `@SendTo`, and check correlation/eventId and transaction logs.

### 14.3. Correlation Mismatch

Responder returns `request.getJMSMessageID()` while requester expects application-defined `request.getJMSCorrelationID()`, or generates a fresh UUID per reply. Agree on one protocol and write regression tests.

### 14.4. Session Errors After Callback Return

Code may have saved the Session for another thread or manually closed/committed it. Review lifecycle and transaction ownership. Use Session **strictly inside the callback**.

### 14.5. Reply Appears Sent Yet Request Is Redelivered

If the listener transaction rolls back after an uncommitted send, the reply is not published (when sent on the same Session) and the request may be redelivered. If a requester still saw a reply from a previous attempt, duplicate logical requests may exist; rely on `eventId` and transaction outcomes.

### 14.6. JMS Transaction Commits Yet DB Side Effect Duplicates

A JMS transaction does not encompass a local DB transaction. If the DB commits first and the JMS commit fails, the broker may redeliver the request. Use an idempotency table/unique constraint, transactional outbox, saga, or JTA/XA according to requirements and infrastructure.

### 14.7. Provider Does Not Support or Permit TemporaryQueue

Requester fails creating a temporary reply queue due to ACL/quota/provider settings. Provision a fixed reply Queue with correlation selectors and its own lifecycle if suitable. Never infinitely retry the same configuration failure.

### 14.8. Unanswerable Poison Message

Request lacks `JMSReplyTo`, has a bad ID, or fails schema validation. Rolling back every time creates a poison message, inflating delivery attempts and DLQ volume. Build an error taxonomy, max retries, and quarantine; do not fabricate a meaningless reply destination just to satisfy code.

### 14.9. Multiple Requesters Share a Correlation ID

If requesters generate non-unique IDs or reuse them across concurrent requests, reply selectors can cross-match. Use IDs with well-defined uniqueness scope, sufficient entropy, and no sensitive information leakage.

## 15. Observability, Testing, and Security

### 15.1. Useful Logging

| Field | Why needed? |
|---|---|
| `requestId`, `eventId` | Idempotency and business tracking |
| Request `JMSMessageID` | Tracking JMS delivery |
| Request/reply `JMSCorrelationID` | Matching exchanges |
| `JMSReplyTo` type | TemporaryQueue/Queue/Topic |
| `JMSRedelivered`, `JMSXDeliveryCount` | Retry/redelivery signals |
| `replyStatusCode`, `reasonCode` | Business outcome |
| `listenerId`, `brokerIdentity` | Identifying processing instance |
| `sendAttempt`, `transactionOutcome` | Distinguishing send from commit |
| `requestLatencyMs`, `replyLatencyMs` | SLA tracking |
| `timeout`, `expired`, `dlq` | Investigating lost replies |

Never write full bodies containing private data to production logs. Delivery count does not prove the business method completed that many times, and a `JMSMessageID` may change if a producer retries creating a new message.

### 15.2. Minimum Tests

- Requester sends a TextMessage with `JMSReplyTo` and correlation; reply carries expected body/properties.
- `@JmsListener` method receives injected `Session` without creating its own `Connection`.
- Request missing `JMSReplyTo` is handled per policy.
- Wrong correlation ID is detected on the requester.
- Test `sessionTransacted=true` and a producer send failure to observe rollback.
- Test `AUTO_ACKNOWLEDGE` if needed to demonstrate ack mode limitations.
- Requester times out before reply; temp queue closes and late replies are handled.
- Duplicate logical `requestId`: only one business side effect.
- Broker restart, redelivery, DLQ, and reply send failure.
- Topic/Queue routing, ACLs, and resource quotas.
- No double reply caused by combining `@SendTo` and manual send.

### 15.3. Securing Reply Destinations

- JMS broker must authenticate and enforce `send`/`consume` ACLs per principal.
- Never use raw user input as a reply queue name.
- If a service has permission to send across multiple tenants, enforce allowlists/prefixes/tenant isolation.
- Prevent abuse via temporary queue quotas and per-request deadlines.
- Never treat a JMS selector as an authorization boundary replacing ACLs.
- Headers like correlation IDs may enter logs/traces, so never put passwords, tokens, or PII in them.
- Validate message schemas before touching DB/payments; avoid arbitrary `ObjectMessage` deserialization.

## 16. Pre-Production Checklist

- [ ] `@JmsListener` is a method in a Spring-managed bean, with JMS annotation processing enabled.
- [ ] Method receives the right `jakarta.jms.Message`/subclass and `jakarta.jms.Session`.
- [ ] `JMSReplyTo` is checked for null/type and conforms to contract.
- [ ] When replies are required, requester and responder agree on a correlation protocol.
- [ ] A **new** reply message is created; the request message is never reused.
- [ ] Only necessary business properties/headers are copied.
- [ ] The injected `Session` creates the producer and sends, preserving the local JMS transaction when the factory is transacted.
- [ ] Close the method-created producer; never close/commit/roll back the container's Session.
- [ ] Never store Session in a field or pass it to an executor/another thread.
- [ ] When sending replies manually, the method returns `void`, avoiding double replies.
- [ ] Listener factory has explicit ack/transaction mode, tested with exceptions and rollbacks.
- [ ] Requester does not send a transacted request and wait for a reply before committing.
- [ ] Receive timeout, reply TTL, business deadline, and late-reply policy are aligned.
- [ ] Broker permits creating/using reply destinations, especially TemporaryQueues.
- [ ] Stable business `requestId`/`eventId` and idempotency exist for retries/redeliveries.
- [ ] DB/external API side effects have separate consistency policies.
- [ ] Retry/backoff, DLQ, quarantine, and re-drive procedures are clearly defined.
- [ ] Metrics/logs correlate requests, replies, and transaction outcomes.
- [ ] Tested broker restarts, missing headers, duplicates, timeouts, and security ACLs.
- [ ] Demo credentials/queues/data are never used in production.

## 17. Self-Check Questions

**1. Can a `@JmsListener` receive `Session`?** Yes, by declaring `jakarta.jms.Session` as a Spring-supported parameter.

**2. Is that Session a brand-new Session created by the method itself?** No. It is provided by the listener infrastructure for the current delivery.

**3. To send a reply to the destination requested by the caller, what do you read?** `request.getJMSReplyTo()`, which returns a `Destination`.

**4. Is `JMSReplyTo` always present?** No, it is an optional header; a policy is needed when it is null.

**5. Should you call `session.commit()` inside the listener?** No, when the listener container/transaction manager manages the transaction.

**6. Should you save Session in a field to reply later?** No; lifecycle and thread ownership belong to the callback/container.

**7. Why use the same Session for request ACK and sending the reply?** In a transacted listener, both JMS operations commit/roll back together.

**8. Does calling `JmsTemplate.convertAndSend` from another bean automatically join the same transaction?** Not by default; you must check resource binding and factory/manager configuration.

**9. Should the reply's `JMSMessageID` be copied from the request?** No. The provider assigns its own ID; use `JMSCorrelationID` for linking.

**10. If the requester supplies `JMSCorrelationID=req-42`, what does the responder do?** Echo `req-42` into the reply's `JMSCorrelationID` per contract.

**11. When is `JMSMessageID` fallback appropriate?** When the protocol defines reply correlation using the request's `JMSMessageID` and the provider generates IDs normally.

**12. Why shouldn't you send manually and also return a `String` with `@SendTo`?** Spring may send a second reply from the return value.

**13. Does a TemporaryQueue survive after the requester connection closes?** No; its lifecycle is tied to the owning connection.

**14. Does a successful reply send prove the requester received it?** No; commit, routing, selector, TTL, and timeouts also matter.

**15. Can a local JMS transaction roll back a database?** No. Use idempotency/outbox or explicitly designed distributed transactions.

**16. Can a failed business validation return a `REJECTED` reply and commit?** Yes, if that is a valid protocol outcome rather than an infrastructure failure.

**17. Does message redelivery mean the previous handler completed?** No; the broker may have delivered it before the process crashed prior to finishing.

**18. Why can sending a request inside an uncommitted transaction and waiting for a reply deadlock?** The responder may not see the request yet to process it and reply.

## 18. Official References

- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): Spring confirms `jakarta.jms.Session` is a valid parameter supporting custom replies; `@Header`, `@SendTo`, `JmsResponse`.
- [Spring Framework 6.2 — JmsListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html): method signatures, destination/container factory, and transaction caveats.
- [Spring Framework 6.2 — MessagingMessageListenerAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/adapter/MessagingMessageListenerAdapter.html): native Message/Session passed into invocation.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener containers, `SessionAwareMessageListener`.
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): transaction management, `ConnectionFactory`, request-reply.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `sendAndReceive(...)` automatically creates a temporary reply queue.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `JMSReplyTo`, `JMSCorrelationID`, `JMSMessageID`, temporary destinations, send/transaction semantics.
- [Spring Boot 3.5 — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): broker/configuration and JMS starter.
- [Spring Boot 3.5 — Messaging How-to](https://docs.spring.io/spring-boot/3.5/how-to/messaging.html): listener factory transaction configuration.
- [ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): broker used in the demo.

**Summary:** In `@JmsListener`, **`Session` is a special Spring-injected method argument**. Use that same Session to create `TextMessage`/`MessageProducer`, read `JMSReplyTo` from the incoming request, and attach correlation per protocol. Let the callback return or throw; **never manually commit/roll back/close the Session**. For simple replies, `@SendTo` can be more concise; when you need native JMS metadata, QoS, and atomic receive+reply, `Session` directly is the right tool.
