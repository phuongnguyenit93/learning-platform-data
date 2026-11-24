# Send Confirmation Differs from Business Processing Success in Spring JMS

**Context:** Spring Framework – JMS, **Message Sending** group. This lesson explains the different levels of "success" across the producer, JMS provider/broker, consumer, transactions, and business logic. Examples apply to Java 17+, Spring Framework 6.x / Spring Boot 3.x with Jakarta Messaging (`jakarta.jms`). The illustrative broker is Apache ActiveMQ Artemis; details on retries, DLQs, persistence, and failover must always be checked against the broker version and configuration in use.

**Thesis:** `JmsTemplate.send(...)` or `convertAndSend(...)` returning normally means the JMS send operation completed within its transaction context and provider guarantees; **it is not confirmation that business processing on the consumer has completed**. If the producer needs to know whether an order was invoiced, inventory was reserved, or a payment was captured, the system must provide a **separate authoritative source of business outcomes and a notification/query mechanism**.

## 1. Two Statements That Look Similar Yet Differ Completely

In an e-commerce system, Order Service issues a `CreateInvoice` command to Billing Service.

- **"Sent successfully"**: the sender invoked the JMS API and the send completed per the JMS/provider contract (or the JMS transaction committed, if applicable). This describes **message transport**; no consumer even has to be online yet.
- **"Business processing succeeded"**: Billing Service validated the request, applied the right rules, guarded against duplicates, and recorded the invoice in a **transaction on the authoritative system of record**. This describes **business state**.
- **"The sender knows the outcome"**: the sender received a business completion event, a contract-defined reply, or queried state from a trusted source. That is **yet another step**: the outcome may already be done even if the notification back to the producer was lost.

~~~text
Order Service / Producer
  T1  build message: eventId=evt-42
  T2  JmsTemplate.convertAndSend("billing.commands", ...)
  T3  send returns                    ← publish acknowledgment
                   │
                   ▼
JMS Provider / Broker
  T4  accept / persist / route per QoS & transaction
  T5  deliver to consumer             ← delivery
                   │
                   ▼
Billing Service / Consumer
  T6  @JmsListener receives           ← listener starts
  T7  validate + deduplicate
  T8  DB COMMIT invoice               ← business transaction
  T9  JMS receive ACK / COMMIT        ← consumption acknowledgment
                   │
                   ▼
Business outcome protocol
  T10 store COMPLETED or emit InvoiceCreated
  T11 Order Service learns outcome    ← caller-visible business result
~~~

**Actual runtime order does not always match log-line order.** The consumer may start processing as soon as the broker delivers the message, even before the producer thread logs after `send`. Individual transactions and callbacks can also finish later. The diagram separates **the meaning of each milestone**, without promising the broker preserves T1–T11 by itself.

## 2. Signal Matrix: What Does Each Piece of Evidence Actually Prove?

| Signal | Valid evidence of | Must NOT be inferred |
| --- | --- | --- |
| Creating `TextMessage`/`MapMessage` | Message object constructed in JVM | Broker received it |
| `JmsTemplate.send` returns normally outside a transaction | Send completed per provider semantics and QoS | Consumer received, business succeeded |
| `JmsTemplate.convertAndSend` returns | Converter and send succeeded in JMS context | Conversion equals business processing; consumer committed |
| `MessageProducer.send(..., CompletionListener)` returns | Async send started without throwing synchronously | Async send finished |
| `CompletionListener.onCompletion` | Async send finished with sync-equivalent guarantees | Business processing finished |
| `JmsTemplate.send` returns **inside** a local JMS transaction | Send executed on transaction-participating session | JMS transaction definitely COMMITTED |
| `Session.commit` / transaction manager commit succeeds | Group of JMS operations in transaction committed | DB/consumer finished |
| Queue depth increases | Broker holds waiting messages at sample time | Message will be processed soon or won't expire |
| Consumer `@JmsListener` begins | One delivery reached the consumer | Handler finished, DB committed |
| Handler logs `DONE` before returning | Code passed a log statement | DB or JMS commit definitely succeeded |
| DB transaction commits | Business data committed in that database | JMS ACK/commit also completed |
| JMS ACK/receive commits | Broker recorded consumption per ACK/transaction config | SQL, email, or payment side effects committed atomically |
| Outcome store shows `COMPLETED` after business commit | Business work met defined completion criteria | Every external caller received notification |
| Caller receives valid completion event/reply | Caller received contract-published result from consumer | No duplicate messages or notifications exist |

**An empty queue does not equal business success:** messages may be in-flight, prematurely ACKed, expired, moved to a DLQ, consumed by another consumer, or purged by an administrator. Verify **outcomes in the business system**.

## 3. What Does `JmsTemplate` Confirm When `send` Returns?

### 3.1. Common Synchronous Send Path

~~~java
jmsTemplate.convertAndSend("billing.commands", "CreateInvoice:O-42");
System.out.println("JMS send operation returned");
~~~

Inside a Spring bean with an injected `JmsTemplate`, if no transaction is awaiting commit and `convertAndSend` throws no error, Spring executed the JMS send call through the provider. Both `send` and `convertAndSend` return `void`. `send` lets code build a JMS `Message` manually via `MessageCreator`; `convertAndSend` uses a `MessageConverter` to convert a Java object into a JMS Message. **Neither waits for Billing Service to finish creating the invoice.**

Exception handling example:

~~~java
try {
    jmsTemplate.convertAndSend("billing.commands", command);
    markPublishAttemptReturned(operationId);
} catch (org.springframework.jms.JmsException ex) {
    markPublishAttemptUncertain(operationId, ex);
    throw ex;
}
~~~

This is **Java pseudocode inside a business service**: `command`, `operationId`, and both `mark...` helpers must be defined by the application; it is not a standalone `main` class. `JmsException` can reflect network, provider, destination, or conversion errors. For certain transport errors, the broker **may have received the message even though the client sees an exception**. Thus a status like `"UNCERTAIN"` is usually more accurate than `"definitely unsent"` when responses drop at the send boundary.

### 3.2. Sending Inside a Local JMS Transaction

~~~text
@Transactional(transactionManager="jmsTransactionManager")
    ├─ JmsTemplate.send / convertAndSend → send inside JMS Session
    ├─ other code continues
    └─ method returns → transaction manager attempts to commit Session
                                      ├─ succeeds
                                      └─ exception / uncertain outcome
~~~

With `JmsTransactionManager`, `JmsTemplate` detects the session Spring bound to the thread. **The send call returning before transaction commit** is not enough to confirm the message committed. Even if the JMS commit fails, the client may not know whether the transaction committed or rolled back if the response dropped at that exact instant.

`JmsTransactionManager` coordinates **a single JMS resource**; a local JMS transaction does not automatically encompass SQL databases, HTTP APIs, or email. `@Transactional` is meaningful only when you know **which transaction manager** and which resources actually participate. Using JTA/XA requires XA-capable connection factories, a coordinator, and dedicated operations; it is not automatic.

### 3.3. JMS-Level Asynchronous Send API

`jakarta.jms.MessageProducer` can send with a `CompletionListener`:

~~~java
producer.send(message, new jakarta.jms.CompletionListener() {
    @Override
    public void onCompletion(jakarta.jms.Message sent) {
        System.out.println("Provider completed async send");
    }

    @Override
    public void onException(jakarta.jms.Message failed, Exception cause) {
        System.err.println("Async send failed: " + cause);
    }
});
~~~

This is a snippet inside a method that already has `MessageProducer producer`, `Message message`, and an appropriate session/connection. It belongs to the **classic Jakarta Messaging API**, **not** a `JmsTemplate` overload.

Right when async `send(..., listener)` returns, the operation may **not be finished**. Only after `onCompletion` fires can the send be treated as succeeding with reliability comparable to a sync send. An exception on the call or in `onException` can leave the broker state **indeterminate**. Do not read or modify the `Message` body/headers after starting an async send before the callback runs. Never call `close` or `commit/rollback` on the producer's session from inside the callback.

**Distinguish the two uses of "asynchronous":** async *send completion* concerns the send acknowledgement; independent consumer processing over time is a separate concern. Neither provides a business success event on its own.

## 4. Even After the Broker Accepts a Message, Delivery May Not Happen Yet

After a successful send, a message can wait indefinitely or fail to reach the intended consumer due to:

1. **Offline consumers**, large backlogs, low concurrency, or slow processing.
2. **Queue vs. Topic subscription differences**: queues have competing consumers; offline non-durable topic subscribers miss events; durable subscriptions are subject to retention and expiry.
3. **Delivery delay** enforced by the provider, deferring eligibility until a timestamp.
4. **Time-to-live (TTL)**: expires before delivery, even though the producer's send succeeded; TTL counts from send time, not from when a consumer becomes ready.
5. **Selectors or routing**: consumer filtering on the wrong property, wrong destination, topic-vs-queue mismatch, ACL/role restrictions, or wrong broker.
6. **Broker policies**: persistent storage, quotas, address-full policies, expiry/DLQ rules, or unsuitable HA/failover setup.

`DeliveryMode.PERSISTENT` by default requests durability against provider failures per standard/configuration. It **does not** protect senders against duplicate business execution, fix malformed schemas, complete DB transactions, or overcome misconfigured storage/retention. `NON_PERSISTENT` can provide weaker guarantees on provider crashes.

**Do not infer from message counts:** queue depth = 0 does not prove an invoice was created. Queue depth = 100 does not mean 100 invoices failed; they may simply be queued for work.

## 5. Consumer Receipt Does Not Equal Consumer Success

~~~java
@JmsListener(destination = "billing.commands")
public void onCommand(String content) {
    validateCommand(content);
    createInvoice(content);
}
~~~

This snippet illustrates the logic; `validateCommand` and `createInvoice` are application-implemented. The moment Spring invokes the listener, all we know is that **one delivery occurred**. Afterward:

- Validation may fail due to contract or schema version violations.
- The DB may be unavailable, time out, or reject unique/FK constraints.
- Outbound calls (payments/email) may fail or return uncertain outcomes.
- The handler may log `"done"`, then the actual transaction commit throws an exception.
- The message may arrive a **second time** due to rollback or producer retry, even if business data committed to the DB on the first run.

A system should separate `MESSAGE_RECEIVED`, `HANDLER_RETURNED`, `BUSINESS_COMMITTED`, and `JMS_RECEIVE_COMMITTED`. These are **distinct** events that never substitute for one another.

### ACK Modes Change What "Listener Succeeded" Means

| Listener configuration | Impact on ACK/rollback | Limitation |
| --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | Container/provider auto-ACKs per implementation semantics | With Spring's `DefaultMessageListenerContainer`, ACK can occur **before** listener execution: handler exceptions do not guarantee redelivery |
| `CLIENT_ACKNOWLEDGE` | Consumer/session explicitly ACKs, or Spring container ACKs after success | Does not combine SQL commit with JMS |
| `DUPS_OK_ACKNOWLEDGE` | Allows lazy ACKs and potential redeliveries | No business-level exactly-once |
| `sessionTransacted=true` | Listener runs in a local JMS transaction; suitable exceptions roll back for redelivery | DB/external calls remain in separate transactions without coordinated design |

Never glance at `@JmsListener` and assume retries are guaranteed. In plain Spring Framework, inspect `DefaultJmsListenerContainerFactory`. When Spring Boot 3.x auto-configures the default listener factory, it typically creates a transactional listener: JTA if a `JtaTransactionManager` exists, otherwise `sessionTransacted`. Defining a custom factory bean can alter that behavior; check the runtime bean and test failures directly.

**Note:** a consumer's ACK tells the broker about **JMS message handling**. It does not prove the database, email, or payment committed. If a handler ACKs too early and crashes before committing the DB, the message may never be redelivered even though the business work never finished.

## 6. The Most Critical Failure Window: DB Commits Before JMS Commits

Suppose a message with `eventId=evt-42` requests creating an invoice:

~~~text
t0  JMS consumer receives message M
t1  INSERT INTO invoices(...) inside DB transaction
t2  DB COMMIT succeeds
t3  Consumer crashes / loses broker connection
t4  JMS ACK/COMMIT not yet completed
t5  Broker recovers and redelivers message M
t6  Handler reprocesses the same evt-42
~~~

If code simply inserts a new invoice and commits **without duplicate protection**, two deliveries can create two invoices or two side effects. Even `sessionTransacted=true` protects only the JMS transaction. Spring Framework explicitly warns that a DB commit succeeding while the JMS commit fails leads to redelivery and the need for duplicate detection.

**What the business layer must guarantee:** for a valid business request sharing the same idempotency key, the intended business outcome is applied **once** even if the message is resent or redelivered.

Common implementation:

- Producer generates `eventId`/`commandId` **once** per business operation and preserves it across retries.
- Consumer stores that key in a `processed_inbox` table with a **unique constraint**.
- Write the key and perform the business mutation inside **the same DB transaction**.
- If the key already exists, the consumer returns normally without repeating the side effect, allowing the JMS receive to commit/ACK.
- If the key is absent yet a real error occurs, the DB rolls back and JMS rolls back/retries per provider policy.

**Never** rely solely on an in-memory `HashSet` or flag: restarts wipe state, replicas race, and check-then-insert is non-atomic.

## 7. Distinguishing "Duplicate Publish" from "Redelivery"

~~~text
Producer attempt A: eventId=evt-42 → JMSMessageID=ID:a
Producer did not receive a timely response
Producer attempt B: eventId=evt-42 → JMSMessageID=ID:b

Consumer receives A and B: two JMS Messages, one business action.
~~~

This is a **duplicate publish**. Provider-assigned `JMSMessageID`s can differ across two sends. When the broker redelivers the *same* message after a consumer rollback, the JMS message ID normally identifies that same message, while `JMSRedelivered`/`JMSXDeliveryCount` help observe repeated deliveries. Yet neither **proves** the business transaction has never committed.

Comparison table:

| ID / Flag | Assigned by | Purpose | Cannot replace |
| --- | --- | --- | --- |
| `JMSMessageID` | JMS provider on send | Traces a message inside broker/JMS | Stable business event ID across publish retries |
| `eventId` / `operationId` | Application | Idempotency, business correlation | Broker delivery/persistence policies |
| `JMSCorrelationID` | Application | Links request–reply and workflows | Business data unique constraints |
| `JMSRedelivered` | Provider prior to delivery | Hints that a message was redelivered | Proof that DB side effects never ran |
| `JMSXDeliveryCount` | Provider on receive | Observes JMS delivery attempts (limited under failures) | Count of committed invoices |

**Business invariants often beat delivery counts:** if only one invoice may exist per `(orderId, invoiceType)`, a unique constraint directly on the invoice table enforces that invariant. When an order supports multiple valid operations, scope the idempotency key properly rather than conflating distinct events.

## 8. Failure Window Matrix

| Where the error happens | Could send have succeeded? | Could business have succeeded? | What to verify |
| --- | --- | --- | --- |
| Payload fails conversion to JMS Message | Not sent on this call | No evidence | Conversion exception; fix data |
| Broker down before send | Usually no | No evidence | Network/credentials, retry policy |
| Broker accepted, send response lost | **Possibly** | **Possibly** in the future | Retry preserving event ID; inspect broker/consumer |
| `JmsTemplate` send inside uncommitted JMS tx | JMS commit unknown | Unknown | Transaction boundary outcome |
| JMS commit succeeded, consumer not running | Yes | No | Queue/topic, backlog, TTL, subscribers |
| Consumer received, validation failed | Yes | No | Rollback, retry, or DLQ by error type |
| DB committed, JMS receive commit lost | Yes | **Yes** or unconfirmed | Inbox/idempotency, DB state, redelivery |
| Consumer ACKed early, DB failed | Yes | No | Risk of lost work due to ACK mode |
| Handler finished, result reply lost | Yes | **Possibly** | Query outcome store by operation ID |
| Message moved to DLQ after retries | Possibly | Usually contract unmet | Alert, replay, and update business outcome |
| TTL expired before delivery | Send may have succeeded | Never reached this consumer | Expiry metrics, timeout contract |
| Producer and consumer restart together | Possibly | Unknown | Journal/outbox/inbox, recovery, dedupe |

**Timeouts do not automatically mean failure:** one side can miss a response even after the other finished. Design retries to tolerate both "never sent" and "sent but response lost".

## 9. Why Can Both `send` Errors and `commit` Errors Be Ambiguous?

Jakarta Messaging explicitly notes that for certain failures at the boundary of non-transacted `PERSISTENT` sends or `Session.commit()`, the client cannot tell whether the broker accepted/committed or not. For async `MessageProducer`, call exceptions or error callbacks likewise may not reveal whether the message reached the broker.

This leads to two common design mistakes:

1. **Generating a new ID on every retry:** the same business intent spawns multiple `eventId`s, preventing the consumer from recognizing one operation and causing double charges/double invoices.
2. **Abandoning retries entirely out of fear of duplicates:** if the broker truly never received the message, the business work is silently dropped.

The better approach is **bounded retries + stable idempotency keys + recoverable state persistence + idempotent consumers**. Choose backoff and alerts appropriately; never retry immutable data/schema errors infinitely.

## 10. Outbox: Ensuring Send Intent Survives DB Commit

If Order Service does:

~~~text
BEGIN DB
INSERT orders...
COMMIT DB
JmsTemplate.convertAndSend("billing.commands", event)
~~~

crashing between `COMMIT DB` and `send` leaves the order saved while the invoice command is never published. Reversing the order—sending before DB commit—risks Billing receiving a command for an uncommitted or rolled-back order.

**Transactional outbox** writes both business data and the outgoing event in a single DB transaction. PostgreSQL illustration:

~~~sql
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    status TEXT NOT NULL
);

CREATE TABLE event_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

BEGIN;

INSERT INTO orders (order_id, status)
VALUES ('O-42', 'CREATED');

INSERT INTO event_outbox (
    event_id, aggregate_id, event_type, payload
) VALUES (
    '88888888-8888-4888-8888-888888888888',
    'O-42',
    'CreateInvoice',
    '{"eventId":"88888888-8888-4888-8888-888888888888",
      "type":"CreateInvoice","orderId":"O-42","schemaVersion":1}'::jsonb
);

COMMIT;
~~~

This is a SQL model for PostgreSQL requiring a DB and table creation privileges; **Spring JMS does not create these tables automatically**.

The outbox publisher then runs:

~~~text
Read unpublished event_outbox rows (controlled claim/lock)
    → send JMS preserving eventId
    → observe JMS send/transaction completion
    → mark published_at
    → retry after restart if uncertain
~~~

If the broker accepted the message yet the publisher crashed before updating `published_at`, it will resend. Hence an outbox supports **at-least-once publish**, not exactly-once delivery on its own. Producers must preserve stable event IDs and consumers must deduplicate. With multiple outbox workers, use proper claim/lease/locking or `SKIP LOCKED`; never rely on unlocked `SELECT` loops.

**An outbox solves "DB committed but publisher forgot to send", not "Did Billing create the invoice?".** Those two questions require two distinct sources of proof.

## 11. Inbox: Processing Business Work Once Despite Duplicate Deliveries

One table to track processed events and one business table:

~~~sql
CREATE TABLE processed_inbox (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE invoices (
    invoice_id BIGSERIAL PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

A consumer-driven DB transaction:

~~~sql
BEGIN;

INSERT INTO processed_inbox (consumer_name, event_id)
VALUES ('invoice-worker', '88888888-8888-4888-8888-888888888888')
ON CONFLICT (consumer_name, event_id) DO NOTHING
RETURNING event_id;

-- If 1 row returned, this is the consumer's first processing:
-- INSERT INTO invoices(order_id) VALUES ('O-42');
-- If 0 rows returned, SKIP business insert to prevent duplication.

COMMIT;
~~~

`INSERT INTO invoices` is shown as a comment because the application must **branch on the `RETURNING` result**. In actual implementation, both the business insert and inbox insert must run in **the same transaction**; never commit the inbox first and run business work separately. A unique constraint handles races across replicas far better than an in-memory check.

When a duplicate arrives and the inbox confirms the business commit already happened, the handler should **return normally** (without re-creating the invoice) so the listener container can commit the JMS receive. Throwing an exception just for "already processed" can cause the broker to retry a valid message endlessly.

**Limitation:** a DB inbox does not make an outbound HTTP payment call atomic. When side effects live in external services, use idempotency keys on those services or proper reconciliation/compensation workflows.

## 12. How Does the Producer Know Business Processing Completed?

Distinguish **command receipt confirmation** from **command completion notification**. Three common mechanisms:

### 12.1. Querying an Outcome Store

The consumer records results in the system owning the business state, for example:

| Status | How contract should interpret it |
| --- | --- |
| `ACCEPTED` | Request durably recorded in a recoverable store |
| `PROCESSING` | In progress; not yet a final result |
| `COMPLETED` | Business transaction committed per completion definition |
| `REJECTED` | Rejected by business rules; do not retry automatically |
| `RETRYING` | Transient failure; scheduled for retry |
| `FAILED_FINAL` | Automatic handling stopped; needs human or workflow intervention |

Order Service's UI/API can poll `GET /operations/{operationId}` against an authoritative outcome source; never use queue depth to compute status. Distinguish retry attempts from final results. The outcome store must be updated within a provable transaction/design, not merely scraped from logs.

### 12.2. Completion Event

~~~text
OrderService outbox → CreateInvoice(eventId=evt-42)
                          │
                          ▼
BillingService processes + COMMITs invoice
                          │
                          ▼
Billing outbox → InvoiceCreated(eventId, invoiceId)
                          │
                          ▼
OrderService receives completion event → updates outcome
~~~

A completion event **must reflect a committed DB state**; write it to Billing's outbox in the same business transaction to avoid crashing after DB commit but before publishing. The caller receiving completion must also be idempotent: completion events can be republished or redelivered.

### 12.3. Request–Reply with JMSReplyTo and JMSCorrelationID

A request can carry `JMSReplyTo` pointing to a reply queue; the consumer sends a reply with `JMSCorrelationID` so the producer can correlate results. Still, the contract must state what the reply means:

- `REQUEST_ACCEPTED` only states the consumer or infrastructure accepted/registered the request, **not** that the invoice exists.
- `INVOICE_CREATED` must be emitted after the business outcome is committed; for critical results, consider sending replies via an outbox.
- Lost or timed-out reply ⇒ **UNKNOWN_RESULT_TO_CALLER**; never blindly create a new invoice under a new ID.
- Request and reply `JMSMessageID`s are two provider-assigned IDs; `JMSCorrelationID` links the flow and does not replace business idempotency keys.

When a workflow spans multiple steps (invoice created, email not yet sent), define "completed" precisely against the business SLA instead of collapsing `invoiceCommitted` and `emailDelivered` into an ambiguous boolean.

## 13. Spring Boot Java 17: Demo Showing Send Returns Even When Handler Will Fail

Minimal example using **Spring Boot 3.5.0** (released version), Java 17+, and an **external Apache ActiveMQ Artemis broker**. This version illustrates the API; production projects should select a currently supported release. The broker needs queue `demo.business-stages` able to accept/deliver messages (or auto-create enabled) and a user with matching permissions.

### 13.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-business-stages'
~~~

### 13.2. application.yaml

`src/main/resources/application.yaml`:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
  jms:
    pub-sub-domain: false
~~~

Supply the password via the `SPRING_ARTEMIS_PASSWORD` environment variable or a secret store; adjust user, URL, and credentials to match your real broker. Never commit passwords to source control. Boot creates `ConnectionFactory`/`JmsTemplate` when the starter and auto-configuration conditions are met; the broker does **not** appear automatically just from adding a client dependency. In standard Boot 3.x setups, the default listener factory is transactional; if your project overrides that bean, verify its actual mode before testing redelivery.

### 13.3. Single-File Java Code

`src/main/java/example/jmsstages/JmsStagesApplication.java`:

~~~java
package example.jmsstages;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

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
public class JmsStagesApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsStagesApplication.class, args);
    }

    @Bean
    ApplicationRunner sendSample(JmsTemplate template) {
        return args -> {
            String eventId = UUID.randomUUID().toString();
            System.out.println("PUBLISH_BEGIN eventId=" + eventId);

            template.send("demo.business-stages", session -> {
                TextMessage message =
                        session.createTextMessage("CreateInvoice:O-42");
                message.setStringProperty("eventId", eventId);
                return message;
            });

            System.out.println("SEND_RETURNED eventId=" + eventId
                    + " businessOutcome=NOT_VERIFIED");
        };
    }
}

@Component
class DemoInvoiceListener {

    // Demo: intentionally fail exactly once in this process.
    private final AtomicBoolean failOnce = new AtomicBoolean(true);

    @JmsListener(destination = "demo.business-stages")
    public void handle(Message message) throws JMSException {
        String eventId = message.getStringProperty("eventId");
        int count = message.getIntProperty("JMSXDeliveryCount");

        System.out.println("CONSUMER_DELIVERED eventId=" + eventId
                + " count=" + count);

        if (failOnce.compareAndSet(true, false)) {
            System.out.println("HANDLER_THROWING eventId=" + eventId);
            throw new IllegalStateException("Demo transient failure");
        }

        // Production: DB transaction + idempotency and business state.
        System.out.println("HANDLER_RETURNED eventId=" + eventId);
    }
}
~~~

### 13.4. How to Run and Observe

Once you have the Gradle wrapper, test broker, credentials, and a valid queue:

~~~bash
./gradlew bootRun
~~~

Lines like the following **can appear**, with varying IDs and ordering:

~~~text
PUBLISH_BEGIN eventId=<uuid>
SEND_RETURNED eventId=<uuid> businessOutcome=NOT_VERIFIED
CONSUMER_DELIVERED eventId=<uuid> count=1
HANDLER_THROWING eventId=<uuid>
CONSUMER_DELIVERED eventId=<uuid> count=2
HANDLER_RETURNED eventId=<uuid>
~~~

Here `<uuid>` is merely an illustrative placeholder, not literal stdout. The listener may receive **before** `SEND_RETURNED` logs; if retry delay is long or the broker routes to DLQ per policy, the second delivery may not appear immediately. The first receive throws an exception; with a transactional listener, the JMS receive rolls back. `AtomicBoolean` only simulates a single failure **in RAM**—it resets on restart and is not idempotency.

**Important:** the demo performs no SQL insert, so `HANDLER_RETURNED` is **not proof an invoice was created**. It clearly exposes three independent boundaries: send returning, listener invocation, and listener method returning. To test a real business commit, connect a database and implement the inbox pattern from Section 11.

### 13.5. With Plain Spring Framework

Without Boot auto-configuration, you must configure `ConnectionFactory`, `JmsTemplate`, `@EnableJms`, and the listener factory yourself. Snippet:

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1");
    return factory;
}
~~~

This belongs in a `@Configuration` class with `@EnableJms` and matching imports from `jakarta.jms.ConnectionFactory`, `org.springframework.jms.config.DefaultJmsListenerContainerFactory`, and `org.springframework.context.annotation.Bean`. It is not a standalone runnable program. Broker-specific retry attempts, delays, and DLQs must be configured and tested on the provider.

## 14. How Should an HTTP API Express Pending Outcomes?

If an HTTP endpoint only records a request and enqueues to JMS, the contract can return:

~~~http
HTTP/1.1 202 Accepted
Location: /operations/op-42
Content-Type: application/json

{"operationId":"op-42","status":"ACCEPTED"}
~~~

`202 Accepted` indicates the server accepted the request for further processing **per the contract definition**; it does not assert the invoice committed. Clients query `GET /operations/op-42` to inspect `PROCESSING`, `COMPLETED`, `REJECTED`, or `FAILED_FINAL`. Once the outcome store records a committed state, the response may be:

~~~json
{
  "operationId": "op-42",
  "status": "COMPLETED",
  "invoiceId": "INV-1001"
}
~~~

This is an example application-designed API, not an automatic HTTP response from JMS.

**Avoid:** returning `200 OK` with `invoiceCreated=true` immediately after `JmsTemplate.send`; or generating a new request/ID on timeout without checking the previous operation's status. A timeout means **no result received within the deadline**, not a guaranteed business failure. Reuse the same operation ID/idempotency key across HTTP retries and JMS retries.

## 15. Retries, DLQs, and Business Failures

### 15.1. Retries Are Not Proof of Success

A JMS provider may redeliver a message upon consumer rollback/failure; retry counts, delay/backoff, max attempts, and DLQ routing are **broker configurations** with no single universal default across all JMS implementations. Poison messages that repeatedly fail schema validation can trigger retry loops and build up backlogs.

A successful send followed eventually by the message landing in a DLQ means **publishing succeeded while business processing did not meet its contract**, unless another state/outcome proves otherwise. Configure DLQ alerts, error classification, stable event IDs, incomplete-outcome tracking, and controlled replay procedures.

### 15.2. Error Classification

| Error | Handling rule |
| --- | --- |
| Broker unavailable, transient timeout | Bounded retries with exponential backoff keeping `eventId`; outbox survives restarts |
| Malformed payload, unknown schema, bad permissions | Fix contract/config; never retry identical payloads endlessly |
| DB unavailable / lock timeout | Roll back transaction, retry per policy |
| Permanent business rule violation | Mark `REJECTED` or a contract-defined terminal state; never let poison messages loop forever |
| DB already processed, message redelivered | Deduplicate, skip second business mutation, return normally so JMS commits |
| External API returned unknown outcome | Query target system by idempotency key/request ID; never blindly call again |
| Completion reply never reached caller | Caller queries outcome store; never equate timeout with business failure |

**Never stop monitoring at the `"sent"` log.** Reconcile accepted operation counts against completed/rejected counts, pending age, and DLQ/retry counts.

## 16. Shared Cross-System State Model

Separating **publish status** from **business outcome** eliminates ambiguity:

| Publish status | Meaning |
| --- | --- |
| `NOT_ATTEMPTED` | Request/outbox record exists, JMS send not yet attempted |
| `SEND_IN_PROGRESS` | Send call currently executing |
| `SEND_RETURNED` | Send completed per verified provider/transaction guarantees |
| `SEND_UNCERTAIN` | Response lost; unknown whether broker accepted |
| `PUBLISH_RETRYING` | Will retry using the same business ID |

| Business status | Meaning |
| --- | --- |
| `PENDING` | No final outcome yet |
| `PROCESSING` | Consumer started or operation claimed |
| `COMPLETED` | Business transaction satisfied invariants and committed |
| `REJECTED` | Rejected by deterministic business rules |
| `FAILED_FINAL` | Automatic processing halted; needs manual intervention/reconciliation |

**Never draw an automatic arrow** `SEND_RETURNED → COMPLETED`. These two status axes update asynchronously. A business operation can even reach `COMPLETED` while the caller still sees `SEND_UNCERTAIN` due to a dropped network response.

When a workflow has multiple stages, clarify whether `"COMPLETED"` means **invoice created**, **payment collected**, or **email sent**. Never lump distinct side effects into one undefined boolean.

## 17. Observability and System Acceptance Criteria

Metrics must be separated by boundary:

| Measurement point | Metrics / Logs | Why |
| --- | --- | --- |
| Producer | `publish_attempt_total`, `send_returned_total`, `send_error_total`, latency | Shows whether the send path is healthy |
| Outbox | backlog, oldest unpublished age, retry count | DB committed yet unpublished |
| Broker | queue depth, in-flight, oldest message age, expiry/DLQ | Slowness, errors, disconnects, or expired messages |
| Consumer | received/started/handler_failed, processing duration | Workload and handler failures |
| JMS transaction | commit/rollback/redelivery, `JMSXDeliveryCount` | Evidence of consumer retries |
| Business DB | invoice_committed, rejected, dedupe hit, unique violations | Authoritative business state |
| Completion | completion event lag, unobserved outcomes | Done yet unnotified |
| End-to-end | accepted-to-completed latency | Business SLA |

Logs should include a stable `eventId`/`operationId`, `JMSMessageID` for broker tracing, `JMSCorrelationID` for linking request/reply, attempt ID, destination, and result. Never log passwords, tokens, payment details, or sensitive payloads.

`JMSTimestamp` is the send time assigned by the JMS provider, **not the business completion timestamp**. Across machines with clock skew, subtracting timestamps gives only approximate latency; use proper metrics/tracing.

### Minimum Test Matrix

1. **Broker down before publish:** verify send fails/retries and never falsely records `COMPLETED`.
2. **Consumer offline:** producer send succeeds, queue holds messages (if policy retains), business stays pending.
3. **Handler throws error:** with a transacted listener, observe rollback/redelivery/DLQ per broker config.
4. **DB error before commit:** no invoice created, no `COMPLETED` recorded, JMS can redeliver.
5. **Crash after DB commit before JMS commit:** redelivery may occur; verify DB does **not** create a second invoice.
6. **Duplicate publish:** two JMS messages with the same `eventId`; consumer deduplicates in DB transaction.
7. **Lost broker response:** producer sees `SEND_UNCERTAIN` even though broker may have received; retry with same ID.
8. **TTL expires before delivery:** send return may succeed while business work never happens.
9. **Lost reply:** caller times out, queries outcome store, and sees `COMPLETED` without submitting a new request.
10. **Outbox publisher restart:** broker accepted yet `published_at` not recorded, publisher resends; consumer deduplicates.
11. **Poison message:** bounded retries, DLQ alert, explicit business status and replay policy.
12. **Multiple consumers:** races on the same business key blocked by DB unique constraint; never rely on RAM flags.

Every experiment should record provider/version, queue/destination, listener ACK/transaction mode, business IDs, broker logs, DB rows, and final outcomes. Simply seeing "the message left the queue" is **insufficient** to declare a test passing.

## 18. Misconceptions to Eliminate

1. **"`send()` succeeded, so the customer has been invoiced."** False: the producer cannot observe the consumer's business DB.
2. **"`convertAndSend` means business conversion is done."** False: conversion only transforms a Java object into a JMS Message.
3. **"Broker ACK to the producer equals consumer ACK."** False: different parties and boundaries.
4. **"Having a `JMSMessageID` means the DB committed."** False: it is assigned by the provider for the message.
5. **"Queue depth of 0 means everything finished."** False: in-flight messages, expiry, DLQs, and early ACKs exist.
6. **"`PERSISTENT` guarantees an exactly-once invoice."** False: persistence addresses transport durability, not duplicate side effects.
7. **"Handler logged DONE, so the transaction definitely committed."** Logs can execute before commit or disappear on crash.
8. **"`sessionTransacted=true` combines JMS and SQL."** False: a local JMS transaction manages JMS only.
9. **"`@Transactional` makes JMS + HTTP + DB atomic automatically."** False: you must know the transaction manager and resource scope.
10. **"A send error means the broker definitely never received it."** False under network/commit ambiguity.
11. **"Retrying an event requires generating a new eventId."** That breaks idempotency.
12. **"`JMSRedelivered=false` means no duplicates exist."** Producers can publish two messages for one business event.
13. **"DLQ means the business operation was deleted from the system."** False: operations/outcomes may remain pending handling.
14. **"Reply timeout means business failed."** False: it only means the caller did not receive a result in time.
15. **"Adding an outbox tells you the consumer succeeded."** Outboxes protect publish intent; business outcomes are confirmed by the consumer.
16. **"Adding an inbox makes external payment APIs exactly-once."** False: target systems need idempotency/reconciliation support too.
17. **"Spring Boot `@JmsListener` always retries."** Inspect the actual factory bean and broker redelivery settings.
18. **"Using JMS request–reply eliminates uncertainty."** Replies can still be lost, delayed, or duplicated; operation IDs and outcome stores are still needed.

## 19. Decision Checklist

- [ ] Every use of "success" specifies **producer send**, **JMS transaction commit**, **consumer delivery**, **DB commit**, or **caller-observed outcome**.
- [ ] `eventId`/`operationId` stays stable across retries; `JMSMessageID` is never used as a business key.
- [ ] Understand `PERSISTENT`, TTL, queue/topic, subscribers, broker journals, redelivery, and DLQs.
- [ ] Actual listener ACK/transaction mode verified via bean configuration and fault injection.
- [ ] Business transactions enforce invariants and unique constraints/idempotency in the same DB transaction.
- [ ] Strategy exists for side effects outside the DB.
- [ ] For producer DB → JMS, consider transactional outbox; for consumer JMS → DB, apply inbox/dedupe where needed.
- [ ] Outcome store / completion events are tied to business commits.
- [ ] Callers understand timeout = unknown outcome and can query by operation ID.
- [ ] Publish metrics are separated from business completion metrics; alerts cover backlog, DLQs, and overdue pending outcomes.
- [ ] Tested broker outages, duplicate publishes, poison messages, consumer restarts, and crashes between DB commit and JMS commit.
- [ ] Never return `COMPLETED` when only `SEND_RETURNED` has occurred.

**Self-check question:** if Order Service logs `"JMS send successful"` and a user asks `"Has my invoice been created yet?"`, the accurate answer from that log alone is **cannot conclude yet**. To answer `"created"`, inspect committed invoice state or a completion message whose contract reflects the commit.

## Reference Materials

1. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — send, JMS transactions, ambiguity on failure, asynchronous completion, and redelivery.
2. [Jakarta Messaging 3.1 MessageProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer) — sync/async send semantics and `CompletionListener`.
3. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — `JmsTemplate`, `JmsTransactionManager`, and transaction resources.
4. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html) — listener transactions and the need for duplicate detection when DB and JMS commits are separate.
5. [Spring Framework 6.2 — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html) — ACK modes of listener containers.
6. [Spring Boot 3.4 — JMS Reference](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html) — Artemis, `JmsTemplate`, and transactional listener defaults.
7. [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/) — Spring Boot JMS send/receive integration.

**Key takeaway:** `SEND_RETURNED` is a **sender-side signal**; `BUSINESS_COMMITTED` is a **business data store signal**. Bridging those two milestones into a reliable commitment requires explicit transaction boundaries, stable IDs, retries/outboxes, idempotent consumers, and outcome tracking/query mechanisms.