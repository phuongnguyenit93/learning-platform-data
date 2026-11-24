# JMSDestination, JMSReplyTo, and JMSCorrelationID

**Topic:** Spring Framework - jms → Message Model

These three fields belong to the **standard message headers** of Java Message Service (JMS), now standardized in **Jakarta Messaging**. They appear together in request/reply flows yet serve distinct responsibilities: identifying **where a message is sent**, **where replies are expected**, and **the link between a request and its reply**. Distinguishing these three fields cleanly helps resolve bugs such as replies going to the wrong queue, clients consuming the wrong response, and timeouts despite the broker receiving the request.

## 1. Where Do Message Headers Live in JMS?

A JMS message has three logical parts:

- **Header:** standard fields such as `JMSMessageID`, `JMSDestination`, `JMSReplyTo`, `JMSCorrelationID`, `JMSPriority`, and `JMSTimestamp`. Some fields are assigned by the provider on send; others may be set by the client.
- **Properties:** name–value metadata such as `orderId` or `traceId` declared by the application, alongside JMS-defined/provider-specific properties.
- **Body:** the payload, such as a JSON string, plain text, or binary data depending on the message type.

All three headers in this lesson have getters/setters on `jakarta.jms.Message`; they are **not** three body slots or three application properties. In Spring Framework 6+ and Spring Boot 3+, JMS code uses `jakarta.jms.*`. Legacy documentation and applications may use `javax.jms.*`; choose drivers and APIs matching the same namespace.

| Header | Question answered | Java type | Who is responsible for the value? |
| --- | --- | --- | --- |
| `JMSDestination` | **Which destination** does this message go to? | `jakarta.jms.Destination` | Set by provider from the send operation's target |
| `JMSReplyTo` | If the consumer wants to reply, **where should it send**? | `jakarta.jms.Destination` or `null` | Specified by producer/requester |
| `JMSCorrelationID` | **Which request** does this reply belong to? | `String`, plus a provider-specific `byte[]` form | Convention agreed upon by applications |

**Example:** a system sends a request to process `order-42` to queue `orders.requests` and expects the answer on `orders.responses`:

~~~text
REQUEST
  JMSDestination   = orders.requests     (assigned by provider on send)
  JMSReplyTo       = orders.responses    (set by requester)
  JMSCorrelationID = corr-a42           (set by requester)
  Body             = order-42

REPLY
  JMSDestination   = orders.responses    (assigned by provider on reply send)
  JMSCorrelationID = corr-a42           (copied by responder per convention)
  Body             = accepted:order-42
~~~

The request's `JMSDestination` is **not** `orders.responses`. Setting `JMSReplyTo` on a request does not make the broker generate a reply automatically. `JMSCorrelationID` does not route a message to a queue by itself; it helps applications match related messages.

## 2. JMSDestination: Where the Message Was Actually Sent

### 2.1. The JMS Contract

`Message.getJMSDestination()` returns a `Destination` object reflecting where the message was sent. Under Jakarta Messaging, when sending a message:

1. The application selects a destination via the `MessageProducer` or the `send(destination, message)` parameter.
2. The provider performs the send and assigns `JMSDestination` to match that destination.
3. Any `JMSDestination` value the application tried to pre-set before sending **is ignored during the send operation**.
4. The consumer receives the message with `JMSDestination` matching the destination used when sending.

Classic JMS API example, **an illustrative snippet with `session` already initialized from a valid connection**:

~~~java
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

Queue destination = session.createQueue("orders.requests");
TextMessage msg = session.createTextMessage("order-42");

try (MessageProducer producer = session.createProducer(destination)) {
    producer.send(msg);
    System.out.println(msg.getJMSDestination() != null);
}
~~~

After synchronous send succeeds, `System.out.println` prints:

~~~text
true
~~~

On the receiver, if you are certain the destination is a queue, you can read its name via `Queue.getQueueName()`; if it is a topic, use `Topic.getTopicName()`. Do not rely on `Destination.toString()` as a stable format across providers.

~~~java
import jakarta.jms.Destination;
import jakarta.jms.Queue;
import jakarta.jms.Topic;

Destination destination = message.getJMSDestination();
if (destination instanceof Queue q) {
    System.out.println("Queue name: " + q.getQueueName());
} else if (destination instanceof Topic t) {
    System.out.println("Topic name: " + t.getTopicName());
}
~~~

The snippet above also assumes `message` is a received `jakarta.jms.Message`. It does not create resources or a broker by itself.

### 2.2. Do Not Use JMSDestination for Manual Routing

A common mistake:

~~~java
message.setJMSDestination(queueA);
producer.send(queueB, message);
~~~

If `send(queueB, message)` succeeds, the provider sets **queueB** as `JMSDestination`. To send a message to a queue, pass that destination into the send call or create a producer bound to the right destination. You can create an anonymous producer with `session.createProducer(null)` and pass a destination on each send.

In Spring:

~~~java
jmsTemplate.convertAndSend("orders.requests", "order-42");
~~~

Here `JmsTemplate` resolves the queue name and asks the JMS provider to send the message. `JMSDestination` is set by the provider to that destination. Creating a JMS `Queue` object from a name does not guarantee the physical queue already exists in the broker: queue auto-creation/provisioning depends on provider configuration.

### 2.3. One Destination Does Not Tell the Whole Business Path

`JMSDestination` can be a queue or topic, yet it does not reflect all internal routing, broker network addresses, subscriptions, tenants, or the actual consumer instance. A queue can have multiple competing consumers while every message still has the same `JMSDestination` for that queue. To know **which application** processed it, use proper operational observability and business logs rather than inferring from the header.

## 3. JMSReplyTo: Reply Destination Suggested by the Requester

`Message.setJMSReplyTo(Destination replyTo)` indicates where **the responder should send its reply message**. After receiving the request, the responder reads `getJMSReplyTo()`, runs business logic, creates a **new message**, and sends it to the destination obtained.

~~~text
Requester -------------------> request queue ------------------> Responder
   ^                                 |                               |
   |                                 | JMSReplyTo = reply queue      |
   |                                 v                               |
   +------------------------ reply queue <---------------------------+
                   (responder sends new reply message)
~~~

Core snippet:

~~~java
// Requester, with request/producer/requestQueue/replyQueue prepared:
request.setJMSReplyTo(replyQueue);
producer.send(requestQueue, request);

// Responder, with incoming/replyProducer/reply already created:
if (incoming.getJMSReplyTo() != null) {
    replyProducer.send(incoming.getJMSReplyTo(), reply);
}
~~~

These are **two excerpts from two sides**, not a standalone program. Both sender and responder need valid sessions/connections and destinations.

**Important points:**

- `JMSReplyTo` can be a `Queue` or a `Topic`; the usual type for request/reply is a reply queue.
- `JMSReplyTo=null` does not make a JMS message invalid. A message can be a one-way event requiring no reply.
- `JMSReplyTo != null` **does not guarantee** a reply will arrive, does not guarantee a deadline, and does not guarantee business processing succeeded.
- The broker **never** uses `JMSReplyTo` to change the request's destination. Only when the responder sends a reply does that destination become the new message's destination.
- The consumer must have permission to send to the reply destination; having the object in the header grants no extra access rights.

### 3.1. Fixed Reply Queue

For example, multiple requesters send to `orders.requests` and all specify `orders.responses`. The advantage is that the destination exists independently of the requester, making it easy to monitor and operate. The trade-off is needing a way to route replies back to the right requester. If two clients consume from the same queue without selectors, a reply meant for client A can be taken by client B because queue semantics are **competing consumers**.

Solutions include: a single dispatcher managing all replies; selectors keyed by correlation/owner; or a dedicated reply queue per instance. Choose based on concurrent request volume, consumer cost, broker quotas, and late-reply retention requirements.

### 3.2. TemporaryQueue

JMS supports `Session.createTemporaryQueue()` (or `JMSContext.createTemporaryQueue()`) to create a temporary queue with a provider-assigned name/identity. This queue is often set as `JMSReplyTo`.

~~~java
import jakarta.jms.TemporaryQueue;

// session is a valid jakarta.jms.Session.
TemporaryQueue replyQueue = session.createTemporaryQueue();
request.setJMSReplyTo(replyQueue);
~~~

**Important scope rule:** a temporary queue is bound to the **connection** that created it; only that connection is allowed to create a consumer to **receive** from the temporary queue. Other connections are allowed to **send** messages to it. The temporary queue is cleaned up when the connection closes, and should be deleted earlier once no longer needed.

~~~text
Requester: Connection A                 Responder: Connection B
  createTemporaryQueue() -> Temp-A
  receive(Temp-A) allowed                  receive(Temp-A) not allowed
                                           send(Temp-A, reply) allowed
~~~

If the requester closes its connection right after sending the request, replies to the temporary queue may fail or have no receiver. For replies that must survive requester restarts, consider durable destinations and tracking mechanisms instead of relying solely on temporary queues.

## 4. JMSCorrelationID: Linking a Reply to the Right Request

`Message.setJMSCorrelationID(String)` lets the client attach a correlation ID. When the receiver reads `getJMSCorrelationID()`, it can tell which request a reply references **according to the application contract**. JMS does not automatically pick or copy correlation IDs across every request/reply pattern.

### 4.1. Distinguishing JMSCorrelationID from JMSMessageID

| Field | JMSMessageID | JMSCorrelationID |
| --- | --- | --- |
| Purpose | Identifies **this message** | Links this message to another message/request |
| Source | Generated by provider on send per JMS rules | Chosen and set by application per convention |
| Typical form | `ID:...` (provider-generated) | `corr-...` or a copy of the request's `JMSMessageID` |
| Reply vs. request | Both messages have distinct IDs | Both messages can share the same correlation |
| Automatically identical? | No | Only if the reply sender sets it that way |

Per the specification, provider-generated IDs use the **`ID:`** prefix. If **the application generates its own String correlation**, do not use the `ID:` prefix; use something like `corr-` plus a UUID. The `JMSCorrelationIDAsBytes` form is used by certain provider/native clients and is not portable; when there is no specific integration need, prefer `String`.

### 4.2. Two Common Correlation Conventions

**Convention A: requester creates an application correlation ID before sending.**

~~~text
Request:
  JMSMessageID      = ID:producer-001   (assigned by provider)
  JMSCorrelationID  = corr-7f20         (set by requester)
Reply:
  JMSMessageID      = ID:responder-888  (assigned by provider)
  JMSCorrelationID  = corr-7f20         (copied by responder)
~~~

Advantage: the requester knows the ID upfront and can set up its tracking map/selector before sending. This is the convention used in the Spring example in section 6.

**Convention B: use the request's `JMSMessageID` as the correlation on the reply.**

~~~text
Request after send:
  JMSMessageID      = ID:producer-001
  JMSCorrelationID  = null              (optional)
Reply:
  JMSMessageID      = ID:responder-888
  JMSCorrelationID  = ID:producer-001    (copy request JMSMessageID)
~~~

Advantage: the application does not need to generate a separate request correlation ID. Disadvantage: the requester only learns `JMSMessageID` after sending completes; with asynchronous sends it must wait for the completion callback. In addition, producers may disable `JMSMessageID` depending on provider capabilities, so confirm the policy before choosing Convention B.

**Never mix the two conventions.** If the requester expects `corr-7f20` while the responder sends `ID:producer-001`, the response may arrive at the right reply queue yet be rejected as unmatched.

### 4.3. Correlation Does Not Replace a Business Request ID

A message may carry:
- `JMSCorrelationID = corr-d138` to pair the current request/reply.
- Application property `orderId = order-42` to refer to the same order across multiple requests.
- Application property `traceId = trace-e91a` to trace the full flow across multiple services.

Retries can generate new correlation IDs while still representing **the same `orderId` or business request ID**. To prevent duplicate processing, use an appropriate business/request identity and persist idempotency state; relying solely on a single send's `JMSCorrelationID` is insufficient.

## 5. A Complete Request/Reply Setting All Three Headers

Sample workflow:

1. Requester picks destination queue `orders.requests`.
2. Requester creates or obtains a reply destination and sets it in `JMSReplyTo`.
3. Requester picks a correlation ID under Convention A (or plans to use request `JMSMessageID` under Convention B).
4. Requester sends the request. The JMS provider populates `JMSDestination` from the actual queue.
5. Responder receives the request; reads `JMSReplyTo` and correlation info.
6. Responder runs business logic, creates a **new** reply, and attaches the correlation ID per the agreed convention.
7. Responder sends the reply to the destination in the request's `JMSReplyTo`. The provider populates `JMSDestination` on the reply.
8. Requester receives and verifies correlation + payload/status; if expired, handles timeout per business policy.

~~~text
                              [BROKER]
Requester                         |                       Responder
   |-- Request -----------------> orders.requests ---------->|
   |   JMSDestination=orders.requests                        |
   |   JMSReplyTo=reply.destination                           |
   |   JMSCorrelationID=corr-123                             |
   |                                                          |
   |<-- Reply <---------------- reply.destination <------------|
   |    JMSDestination=reply.destination                      |
   |    JMSCorrelationID=corr-123                             |
   |                                                          |
   +-- Check correlation + result
~~~

**Two separate checks:**
- *Right address?* Check that the producer sent to the right queue and the provider recorded the matching `JMSDestination`.
- *Right answer?* Check that `JMSCorrelationID` on the reply matches the waiting request.

A message arriving at the right queue **can still have the wrong correlation**. A message carrying the right correlation **can still be sent to the wrong destination** and never reach the intended consumer.

## 6. Runnable Example: Spring Boot + Artemis Request/Reply

This example uses **Java 17+**, Spring Boot **3.x**, Jakarta JMS, and Apache ActiveMQ Artemis. A requester sends `order-42`, and a responder processes it and sends back `accepted:order-42`. To keep focus on headers, both components live in the same JVM while communicating through a **real broker**.

The requester uses `JmsTemplate.sendAndReceive()`, a Spring method that creates a temporary reply queue and sets `JMSReplyTo` on the request. The responder explicitly sets `JMSCorrelationID` on the reply. We also read `JMSDestination` from the received request to prove the provider populated it.

### 6.1. Preparation

Create a Maven project from [Spring Initializr](https://start.spring.io/), Java 17+, Group `com.example`, Artifact `jms-headers-demo`, dependency **Spring for Apache ActiveMQ Artemis** (artifact `org.springframework.boot:spring-boot-starter-artemis`). Start an external Artemis broker at `tcp://localhost:61616` with send and receive permissions on queue `demo.header.requests`. The queue must be provisioned or allowed to auto-create on the broker.

Set two environment variables `ARTEMIS_USER` and `ARTEMIS_PASSWORD`. Create `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=10s
# Demo disables session caching to easily observe temporary destination lifecycle.
spring.jms.cache.enabled=false
~~~

`spring.artemis.mode=native` requires an externally running broker; it does not start a broker automatically. `spring.jms.template.receive-timeout=10s` bounds how long to wait for a reply. Disabling cache is for the demo; production can re-enable it after validating connection/session pooling and temporary destination lifetimes.

Create `src/main/java/com/example/JmsHeadersDemoApplication.java`:

~~~java
package com.example;

import java.util.UUID;
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsHeadersDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsHeadersDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner requester(JmsTemplate jmsTemplate) {
        return args -> {
            // Convention A: generate correlation before sending request.
            String correlationId = "corr-" + UUID.randomUUID();

            Message reply = jmsTemplate.sendAndReceive(
                    "demo.header.requests",
                    session -> {
                        TextMessage request =
                                session.createTextMessage("order-42");
                        request.setJMSCorrelationID(correlationId);
                        return request;
                    });

            if (reply == null) {
                System.out.println("TIMEOUT");
                return;
            }

            if (!(reply instanceof TextMessage textReply)) {
                throw new IllegalStateException(
                        "Expected TextMessage as reply");
            }

            System.out.println("REPLY=" + textReply.getText());
            System.out.println("CORRELATION_MATCH="
                    + correlationId.equals(
                            textReply.getJMSCorrelationID()));
        };
    }
}

@Component
class HeaderResponder {

    private final JmsTemplate jmsTemplate;

    HeaderResponder(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @JmsListener(destination = "demo.header.requests")
    public void onRequest(Message request) throws JMSException {
        if (!(request instanceof TextMessage textRequest)) {
            throw new IllegalArgumentException(
                    "Expected TextMessage as request");
        }

        // Provider assigns JMSDestination based on where request was sent.
        System.out.println("REQUEST_DESTINATION_PRESENT="
                + (request.getJMSDestination() != null));

        // Requester (via Spring) specified where to receive the reply.
        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            throw new IllegalArgumentException(
                    "Missing JMSReplyTo on request");
        }

        String correlationId = request.getJMSCorrelationID();
        if (correlationId == null) {
            throw new IllegalArgumentException(
                    "Missing JMSCorrelationID on request");
        }

        String payload = textRequest.getText();
        jmsTemplate.send(replyTo, session -> {
            TextMessage reply =
                    session.createTextMessage("accepted:" + payload);

            // Responder copies correlation per Convention A.
            reply.setJMSCorrelationID(correlationId);
            return reply;
        });
    }
}
~~~

Spring supports accepting a raw `jakarta.jms.Message` parameter in `@JmsListener`, so the responder method can read all three headers directly. Spring Boot with the Artemis starter, a `ConnectionFactory` bean, and valid listener configuration handles connection/resource provisioning.

### 6.2. Run and Observe

In the Maven project root directory:

~~~bash
mvn spring-boot:run
~~~

If using the Maven wrapper on Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

With the broker ready, proper permissions, existing queue, and no stale interfering messages, the three business lines on the happy path are:

~~~text
REQUEST_DESTINATION_PRESENT=true
REPLY=accepted:order-42
CORRELATION_MATCH=true
~~~

Other Spring and broker startup logs will also appear. If no reply arrives within 10 seconds, the requester prints `TIMEOUT` instead of the two reply lines. This is a **conditional expected result**, not evidence the program was executed against a broker in the authoring environment.

**Explanation:**

1. `sendAndReceive("demo.header.requests", ...)` sends a message to the request queue; the request's `JMSDestination` is assigned by the provider.
2. `sendAndReceive` creates a temporary queue, sets it as `JMSReplyTo`, and waits for a reply; the requester does not manually set `ReplyTo` in the callback.
3. The requester sets `JMSCorrelationID` to a `String` starting with `corr-`. The actual value has a different UUID on each run.
4. The responder retrieves `request.getJMSReplyTo()`, creates a new `TextMessage`, and sets the same correlation as the request.
5. `jmsTemplate.send(replyTo, ...)` sends the reply to the temporary queue. The reply's `JMSDestination` is the destination used to send the reply.
6. The requester receives the message and checks `correlationId.equals(reply.getJMSCorrelationID())`.

You can also have `@JmsListener` return a value and use `@SendTo` so Spring manages replies; when fine-grained control over correlation/headers is needed, manual sending as in this example makes the contract clearer.

## 7. Setting Headers Manually in Classic JMS API and Simplified JMS API

### 7.1. Classic API with Message

With a valid `Session`, you can create request/reply destinations and set both client-owned headers before sending:

~~~java
import java.util.UUID;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;

// session created via ConnectionFactory/Connection.
Queue requestQueue = session.createQueue("orders.requests");
TemporaryQueue replyQueue = session.createTemporaryQueue();
String correlationId = "corr-" + UUID.randomUUID();

TextMessage request = session.createTextMessage("order-42");
request.setJMSReplyTo(replyQueue);
request.setJMSCorrelationID(correlationId);

try (MessageProducer producer = session.createProducer(requestQueue)) {
    producer.send(request);
}
~~~

This snippet is **not standalone** because it needs a connection/session from a provider. To receive from `replyQueue` with the classic API, the consumer must belong to the **connection that created the temporary queue** and `connection.start()` must be called before waiting with `receive(timeout)`. A responder from another connection can **send** to that temporary queue.

### 7.2. Simplified API with JMSProducer

In the `JMSContext` API, the producer allows setting headers fluently:

~~~java
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TemporaryQueue;

// context is a valid JMSContext.
Queue requests = context.createQueue("orders.requests");
TemporaryQueue replies = context.createTemporaryQueue();

context.createProducer()
       .setJMSReplyTo(replies)
       .setJMSCorrelationID("corr-42")
       .send(requests, "order-42");
~~~

`JMSProducer.setJMSReplyTo(...)` and `JMSProducer.setJMSCorrelationID(...)` apply to messages sent by that producer. Header values set on `JMSProducer` **override** corresponding values set directly on `Message`. Do not confuse this with `JMSDestination`: that field is still assigned by the provider from the send operation's destination.

### 7.3. Using Spring MessagePostProcessor

To send a converted payload and attach an application correlation ID (e.g. one-way send):

~~~java
import java.util.UUID;
import org.springframework.jms.core.JmsTemplate;

// jmsTemplate is an injected bean.
String correlationId = "corr-" + UUID.randomUUID();

jmsTemplate.convertAndSend(
        "orders.requests",
        "order-42",
        message -> {
            message.setJMSCorrelationID(correlationId);
            return message;
        });
~~~

This is an **illustrative service snippet**, requiring a `JmsTemplate` bean. It **does not create a reply destination**, because `convertAndSend` is not a full request/reply pattern. You can set `JMSReplyTo` in the post-processor when you already have a `Destination` and a matching reply-waiting mechanism, or use `sendAndReceive` so Spring manages a temporary destination.

## 8. Correlation ID and Message Selectors

When multiple requesters share a **fixed reply queue**, one strategy is creating a consumer with a selector for the desired `JMSCorrelationID`. Example with classic JMS API:

~~~java
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;

// session, sharedReplyQueue, correlationId already exist.
// correlationId generated from UUID so it contains no single quotes.
String selector = "JMSCorrelationID = '" + correlationId + "'";
MessageConsumer consumer =
        session.createConsumer(sharedReplyQueue, selector);
~~~

This is a non-standalone excerpt: `consumer.receive(10_000)` requires a started connection, and the consumer/selector resources must be closed promptly.

**Crucial limitation:** in a JMS selector, the standard headers that may be referenced are `JMSDeliveryMode`, `JMSPriority`, `JMSMessageID`, `JMSTimestamp`, `JMSCorrelationID`, and `JMSType`. **You cannot treat `JMSDestination` or `JMSReplyTo` as standard selector headers.**

~~~text
JMSCorrelationID = 'corr-123'     -- potentially valid selector
JMSReplyTo = 'orders.responses'   -- not a standard selector header
JMSDestination = 'orders.req'     -- not a standard selector header
~~~

These lines are **selector syntax illustrations**, not database SQL statements. Selecting the queue/topic happens when creating the consumer on a destination. If a selector incorporates values from untrusted input, prevent malformed expressions or selector injection by generating safe correlation IDs yourself or properly escaping string literals.

Note: using per-request selectors can increase consumer counts and broker overhead under high traffic. With many concurrent requests, consider a single dispatcher on the shared reply queue, one temporary queue per requester, or tracking pending requests via a correlation map with resource bounds.

## 9. Common Real-World Request/Reply Issues

### 9.1. Timeout Does Not Mean the Responder Did Not Process

A requester successfully sending a request yet timing out waiting for a reply may happen because the responder is slow, the reply was lost, the reply destination is gone, the consumer is down, or routing failed. Do not retry unconditionally because the responder may have already committed business state. Use a stable **business request ID** and idempotent processing to avoid duplicate actions on redelivery/retry.

### 9.2. Transactions Can Block a Request Until Commit

If a request is sent inside an uncommitted transaction, it may not be delivered to consumers yet. A caller holding that transaction open while **waiting for a reply before committing** can cause its own timeout. Keep transaction boundaries clear: commit the send operation before waiting for a reply, or use asynchronous orchestration.

A JMS transaction does not automatically combine the responder's database write and reply send into a single atomic transaction across two systems. Consider outbox/inbox patterns, compensating actions, or JTA/XA only when truly required and supported by the environment.

### 9.3. Late or Duplicate Replies

If a requester times out and discards a pending request, yet a reply arrives later, the correlation ID only tells you it belonged to that old request; the application must decide whether to keep, discard, log, or compensate. If the responder redelivers a request and sends multiple replies, the requester must know how to deduplicate. `JMSCorrelationID` by itself **does not guarantee exactly-once business processing**.

### 9.4. Security and Provider Compatibility

- Do not place tokens, passwords, or sensitive personal data into correlation headers or header logs.
- Verify send/consume ACLs for both request queues and reply destinations; a `JMSReplyTo` header is not proof of authorization.
- Do not let untrusted parties arbitrarily force a responder to send sensitive data to an unauthorized destination.
- `Destination` objects can be provider-specific; JMS does not automatically guarantee cross-broker protocol interoperability. When bridging messages across providers, verify how `JMSReplyTo` and `JMSCorrelationID` are mapped. In particular, providers are not required to preserve incompatible foreign `Destination` objects.

## 10. Troubleshooting Table

| Symptom | Check first | Conclusion / action |
| --- | --- | --- |
| Requester sends, responder never receives | Actual target queue/topic, permissions, destination name, listener status | Check `JMSDestination` and broker queues; do not edit `JMSReplyTo` to fix request routing |
| Responder receives request, doesn't know where to reply | Is `request.getJMSReplyTo()` null? | Decide one-way vs. request/reply contract; supply reply destination if needed |
| Reply never reaches requester | Where did responder send? Does reply destination still exist? | Compare request's `JMSReplyTo` with reply's `JMSDestination` |
| Reply lands in right queue, app reports mismatch | Request vs. reply `JMSCorrelationID` values | Verify both sides follow the same Convention A or B |
| Requester A receives B's response | Shared reply queue, competing consumers, selector | Use temp queue, selector, or dispatcher with proper ownership |
| Selector rejected | Are `JMSReplyTo`/`JMSDestination` used in expression? | Use only selector-supported headers/properties |
| Client stops, temporary reply queue disappears | Lifetime of connection that created temp queue | Use a durable reply queue if replies must survive restarts |
| Random timeouts, duplicate processing | Redelivery, retries, transactions, backlog | Inspect logs/metrics; implement business idempotency and deadlines |
| App-generated correlation header starts with `ID:` | Confusing application ID with JMSMessageID | Use `corr-...` for application correlation; copy `ID:...` only under Convention B |
| `JmsTemplate.sendAndReceive()` blocks indefinitely | Receive timeout not configured properly | Set a finite receive timeout and handle `null` replies |

## 11. Common Misconceptions

1. **"JMSDestination and JMSReplyTo are both destinations, so they are interchangeable."** False. One is the current send target; the other is an optional reply address.
2. **"setJMSDestination() chooses the queue."** False. The `send(...)` operation specifies the queue/topic being sent to.
3. **"The broker sees JMSReplyTo and sends a reply itself."** False. The responder or a configured application/framework layer must create the reply.
4. **"Correlation auto-generates and auto-matches."** False. Applications must explicitly define the ID creation/copy convention.
5. **"A reply has the same JMSMessageID as the request."** False. Request and reply are two separate messages; use correlation to link them.
6. **"Having the right correlation means the message reaches the right client automatically."** False. Destinations and consume/dispatch mechanics still have to be right.
7. **"With a shared reply queue, any client can receive and ignore messages not meant for it."** Dangerous. Consuming a message removes it from the queue, potentially starving the rightful requester.
8. **"A temporary queue belongs to a session, so another connection can receive from it."** False. Consumption is bound to the connection that created the temporary destination.
9. **"Non-null JMSReplyTo means a response is guaranteed and always succeeds."** False. It is a hint for where to reply, not a business guarantee.
10. **"TIMEOUT = processing definitely failed."** False. Distinguish delivery, processing, and response arrival.

## 12. Self-Check Questions

**1.** A request is sent to `orders.requests` while declaring `JMSReplyTo=orders.responses`. What is the request's `JMSDestination`?

**Answer:** `orders.requests`. Only the **new reply message** goes to `orders.responses` if the responder chooses to send one.

**2.** A reply has `JMSMessageID=ID:reply-9`; the request had `JMSCorrelationID=corr-12`. Under Convention A, what does the responder set as the reply's correlation?

**Answer:** `corr-12`, not `ID:reply-9`.

**3.** Under Convention B (copying request `JMSMessageID`), when does the requester know which ID to match?

**Answer:** After sending the request completes (or after the completion callback fires for asynchronous send).

**4.** Can you use selector `JMSReplyTo = 'my-replies'` in standard JMS?

**Answer:** No. Only a subset of headers is standardized for selectors; `JMSCorrelationID` is supported, whereas `JMSReplyTo`/`JMSDestination` are not.

**5.** Why is a temporary queue convenient for request/reply yet prone to failure when the requester restarts?

**Answer:** It is tied to the creating connection and cleaned up with the connection lifecycle; it is not a long-lived reply destination independent of the requester.

**6.** When a response has a matching correlation yet its payload reports a business error, is the transaction considered successful?

**Answer:** No. Correlation is only a link; success/failure state must be verified in the payload, contract, and business transaction.

## References

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — sections 3.4 message headers, 2.16 request/reply, 6.2.2 temporary destinations, 7.6 setting message headers.
- [Jakarta Messaging 3.1 API: Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message) — `getJMSDestination`, `getJMSReplyTo`, `getJMSCorrelationID`, and setters.
- [Jakarta EE Tutorial: Messaging Concepts](https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html) — request/reply, reply destination, and correlation examples.
- [Spring Framework: Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate` and `MessageCreator`.
- [Spring Framework: Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — receiving raw JMS Messages and response handling.
- [Spring Framework 6.2 Javadoc: JmsTemplate.sendAndReceive](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html) — creating temporary reply queues and setting `JMSReplyTo`.
- [Spring Boot 3.4: JMS](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html) — native Artemis mode and JMS auto-configuration.
