# Redelivery and dead-letter queues in JMS

## 1. Problem: failed messages must not clog the whole system

A Spring Integration service receives `OrderPaid` events from the JMS queue `orders.paid.in` and updates PostgreSQL. At 10 AM, the database loses connectivity for 30 seconds: the consumer needs to **retry** unprocessed messages. Yet if a message carries permanently malformed JSON, repeatedly rolling back and redelivering it creates a **poison-message loop**, burning CPU, filling logs, and potentially blocking valid events from advancing.

Two mechanisms must work together:

- **Redelivery:** the JMS provider/broker **redelivers** a message that was not acknowledged successfully, such as when the receive transaction rolled back.
- **Dead-letter queue (DLQ):** a destination holding messages that broker policy decides should no longer be delivered from the original queue/subscription, typically after repeated processing failures.

In the **SPRING_INTEGRATION_ADAPTERS** module, inbound/outbound adapters, gateways, pollers, and `MessageChannel`s move data between Spring Integration and files, SFTP, HTTP, JMS, AMQP, Kafka, or databases. For **JMS Adapters**, the *Redelivery and dead-letter queues* topic helps design message contracts, error paths, transactions, and consumer lifecycles so transient errors recover while permanent errors are isolated.

**After this lesson, you should be able to:**

1. Explain when JMS redelivery happens and distinguish it from a producer resending a new message.
2. Interpret `JMSRedelivered` and `JMSXDeliveryCount` within their true guarantees.
3. Configure a **JMS message-driven inbound adapter** with transacted sessions and exception propagation.
4. Set retry delays, max delivery attempts, and dead-letter addresses/queues on the target broker.
5. Distinguish `errorChannel`, broker DLQ, application-level quarantine, and expiry queues.
6. Design idempotent consumers, investigation workflows, safe replays, and failure tests.

## 2. Lifecycle diagram: receive, process, commit, rollback, DLQ

~~~mermaid
flowchart TD
    A["Producer sends JMS message"] --> B[("Broker: orders.paid.in")]
    B --> C["JMS listener receives message"]
    C --> D["Spring Integration: parse + process"]
    D --> E{"Completed?"}
    E -->|"Yes"| F["JMS commit/acknowledge"]
    E -->|"Error and exception propagates"| G["JMS rollback / recover"]
    G --> H{"Broker redelivery limit reached?"}
    H -->|"No"| I["Wait redelivery delay"]
    I --> B
    H -->|"Yes"| J[("Dead-letter destination")]
    J --> K["Investigate, fix, controlled replay"]
~~~

This is the **typical model** with a transacted listener and a DLQ-configured broker. If the listener uses `AUTO_ACKNOWLEDGE` or an error flow absorbs the exception, the broker may **never receive a rollback signal**; in that case, the error-to-redelivery path in the diagram **will not happen**.

### Three outcomes not to conflate

| Outcome | Meaning | Note |
|---|---|---|
| Handler completes | A business branch finished running | JMS may still not be committed yet |
| JMS commit/acknowledge succeeds | Broker considers receipt complete at the protocol level | Does not prove DB, HTTP, or Kafka committed atomically with JMS |
| Message enters DLQ | Broker or application isolated the message per policy | Does not mean data was fixed or business work completed |

A DLQ is an **isolation mechanism**, not a sign of successful processing. Messages in a DLQ still require human or dedicated workflow resolution.

## 3. When does JMS redelivery happen?

Under Jakarta Messaging, a consumer can see a message again whenever the previous delivery was **not acknowledged**. Typical situations:

1. A **transacted** session receives a message, then `rollback()` is called after a handler error.
2. The connection/session terminates before the receive transaction commits successfully.
3. With `CLIENT_ACKNOWLEDGE`, the consumer calls `Session.recover()` or fails before acknowledgment.
4. A consumer/broker crash leaves the previous delivery's acknowledgment status uncertain; the provider may redeliver upon recovery.

**Redelivery is not producer retry.**

~~~text
Redelivery:
  Producer sends JMS message ID:101
    -> Consumer receives ID:101 -> rollback
    -> Broker redelivers ID:101

Producer retry:
  Producer sends eventId=evt-101 -> JMS message ID:101
  Producer unsure of send outcome, resends same eventId=evt-101
    -> New JMS message ID:205
~~~

In this example, `eventId` is the **stable business key**, whereas the provider-assigned `JMSMessageID` can differ when the producer resends the same event. Therefore, **never rely solely on `JMSRedelivered` or `JMSMessageID` for business deduplication**.

### At-least-once and transaction limits

With appropriate JMS broker, persistence, transaction, and configuration settings, a flow can aim for **at-least-once**: when transient failures occur, uncommitted messages can arrive again. That is **not** exactly-once business processing.

For example, suppose a handler commits to the DB and the JVM crashes before JMS commit. The broker redelivers the message; if the handler blindly re-executes `UPDATE balance=balance+amount` without idempotency, the business could credit or debit money twice even though the broker behaved properly.

## 4. JMS headers/properties used to identify redelivery

Standard JMS defines key metadata:

| Metadata | Source | Meaning | Can it serve as a business key? |
|---|---|---|---|
| `JMSMessageID` | Generated by JMS provider on send | Provider-managed identifier for one JMS message | **No**: producer may resend the same event under a new message ID |
| `JMSRedelivered` | Set by JMS provider on delivery | Hints the message was delivered previously and may not have been acked | **No** |
| `JMSXDeliveryCount` | Set by JMS provider on receive | Delivery count from the provider; first delivery is normally **1** | **No**: only aids protocol-level observation/retries |
| `JMSCorrelationID` | Per request-reply contract | Matches JMS replies to requests | Does not replace `eventId` |
| `eventId` in JSON | Created by producer app | Identifies a business event across retries | **Yes**, when designed stably and enforced unique |

**Jakarta Messaging 3.1 detail:** `JMSXDeliveryCount` is a required property on received messages; `JMSRedelivered=true` corresponds to a delivery count of 2 or higher. However, the specification also notes that **delivery count may not be strictly accurate across failures**, because providers are not forced to persist every count increment before delivery. Thus, never treat an app-side count threshold as an absolute source of truth for business workflows.

### Reading raw JMS metadata during testing

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;

public static void logDeliveryMetadata(Message message) throws JMSException {
    String jmsMessageId = message.getJMSMessageID();
    boolean redelivered = message.getJMSRedelivered();
    int deliveryCount = message.propertyExists("JMSXDeliveryCount")
            ? message.getIntProperty("JMSXDeliveryCount")
            : -1;

    System.out.printf(
            "jmsMessageId=%s, redelivered=%s, deliveryCount=%d%n",
            jmsMessageId, redelivered, deliveryCount);
}
~~~

This is a **JMS API helper** for test environments or callbacks with access to the raw JMS message. In Spring Integration, when an inbound adapter extracts payloads, handlers typically receive a Spring Message rather than `jakarta.jms.Message`; metadata may be copied into Spring headers by the header mapper depending on config/version. **Do not cast a Spring `String` payload to a JMS Message** to read metadata if the endpoint already converted it. Configure the mapper or boundary instrumentation instead.

### Why should the application never set `JMSRedelivered` itself?

`JMSRedelivered` is delivery metadata controlled by the **provider**. Producers should not set this flag to "mark" a resend. If you need to represent a **business retry**, use `eventId` and an explicit business field such as `attemptReason` in the contract or appropriate metadata.

## 5. Acknowledgment, transactions, and when redelivery occurs

| Receive mode | When handler throws an exception | Realistic expectation |
|---|---|---|
| `DefaultMessageListenerContainer` with `AUTO_ACKNOWLEDGE` | Container may already have acknowledged before the handler ran | **No guarantee** of broker redelivery |
| `CLIENT_ACKNOWLEDGE` | May recover/redeliver depending on container/provider | Best effort; not a substitute for a JMS transaction |
| `sessionTransacted=true` | Exception escaping to the container can trigger rollback | Broker has grounds to redeliver per policy |
| `JmsTemplate.receive()` with its own local transaction | Transaction may commit as soon as `receive()` returns | Downstream Spring flow errors afterward **cannot roll back** |
| **Transactional poller** using `JmsTransactionManager` | Synchronous poll/dispatch share the same transaction | Synchronous downstream exceptions can trigger JMS rollback |

### Message-driven adapters differ from polling adapters

**Message-driven** uses a listener container that stays ready for JMS messages; **no Spring Integration poller is needed**. **Polling inbound** calls `JmsTemplate.receive()` on a poller schedule. Enabling `sessionTransacted=true` on the polling template is **not enough** to protect downstream handlers if the transaction already committed right after `receive()`.

Since **Spring Integration 4.2**, when a JMS message-driven adapter **creates its own listener container**, its default acknowledge mode is `transacted`. If you supply an **external `DefaultMessageListenerContainer`**, you must configure `sessionTransacted` or a transaction manager on that container yourself; do not assume it is protected automatically.

### The synchronous boundary is a critical condition

~~~mermaid
flowchart TD
    A["JMS listener, transacted session"] --> B["Inbound adapter"]
    B --> C{"Spring MessageChannel"}
    C -->|"DirectChannel"| D["Synchronous handler"]
    D --> E["Exception propagates -> JMS rollback"]
    C -->|"ExecutorChannel / QueueChannel"| F["Message handoff succeeds"]
    F --> G["Listener exits -> JMS may commit"]
    G --> H["Handler on another thread fails: cannot roll back original JMS"]
~~~

**`errorChannel` also alters exception flow.** If an error flow catches the error and exits normally, the listener may commit the message even though the handler or converter failed. Section 7 examines this in detail.

## 6. Java DSL: rollback-capable JMS inbound channel adapter

The example uses Spring Integration 6+, Spring Framework 6+, and Java 17+ with `jakarta.jms`. The app needs `spring-integration-jms`, a JMS driver for the broker, a valid `ConnectionFactory`, and the `orders.paid.in` queue created with proper permissions.

~~~xml
<!-- Versions managed by Spring Boot BOM if the project uses Spring Boot. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Add JMS provider/starter and broker appropriate for your environment. -->
~~~

### 6.1. Synchronous inbound flow, transacted session

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class PaidOrderJmsConfig {

    @Bean
    public IntegrationFlow paidOrderInbound(
            ConnectionFactory connectionFactory,
            PaidOrderConsumer paidOrderConsumer) {

        return IntegrationFlow
                .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                        .destination("orders.paid.in")
                        .configureListenerContainer(listener ->
                                listener.sessionTransacted(true)
                                        .concurrentConsumers(2)
                                        .maxConcurrentConsumers(4)))
                .handle(String.class, (json, headers) -> {
                    paidOrderConsumer.consume(json);
                    return null;
                })
                .get();
    }
}
~~~

This is server-side configuration: a JMS `TextMessage` is typically turned into a `String` Spring payload by the default converter. Example service:

~~~java
public interface PaidOrderConsumer {
    // Parse/validate and process on the same listener thread;
    // throw an unchecked exception if JMS rollback is required.
    void consume(String json);
}
~~~

**Why does the example set `sessionTransacted(true)` explicitly?** So we do not rely silently on defaults and so readers see clearly that exceptions in the synchronous handler propagate to the listener container. Two baseline consumers scaling up to four allow processing multiple **distinct** messages concurrently; each consumer/session has its own transaction.

If the service throws an unchecked exception and the error **is not caught and swallowed by an error flow**, the callback fails and the JMS transaction can roll back. **After rollback, the broker decides when to redeliver or move to a DLQ.** The Spring Integration adapter does not create a DLQ on its own just because `sessionTransacted(true)` is set.

### 6.2. Equivalent XML namespace

~~~xml
<int:channel id="paidOrdersInput"/>

<int-jms:message-driven-channel-adapter
        id="paidOrdersInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.paid.in"
        channel="paidOrdersInput"
        acknowledge="transacted"
        concurrent-consumers="2"
        max-concurrent-consumers="4"/>

<int:service-activator
        input-channel="paidOrdersInput"
        ref="paidOrderConsumer"
        method="consume"/>
~~~

This is a **fragment** requiring `int`/`int-jms` namespaces and the `jmsConnectionFactory` and `paidOrderConsumer` beans. If supplying an externally created container via the `container` attribute, configure transactions on that container itself.

### 6.3. When the source is a polling adapter

When scheduled JMS polling is required, use a transactional poller if synchronous downstream steps must participate in the transaction:

~~~java
import org.springframework.jms.connection.JmsTransactionManager;

@Bean
public IntegrationFlow paidOrderPolling(
        ConnectionFactory connectionFactory,
        JmsTransactionManager jmsTransactionManager,
        PaidOrderConsumer paidOrderConsumer) {

    return IntegrationFlow.from(
            Jms.inboundAdapter(connectionFactory)
                    .destination("orders.paid.in")
                    .configureJmsTemplate(template ->
                            template.receiveTimeout(-1)),
            endpoint -> endpoint.poller(poller ->
                    poller.fixedDelay(5000)
                            .maxMessagesPerPoll(5)
                            .transactional(jmsTransactionManager)))
            .handle(String.class, (json, headers) -> {
                paidOrderConsumer.consume(json);
                return null;
            })
            .get();
}
~~~

`JmsTransactionManager` must be declared as a bean using the same `ConnectionFactory`:

~~~java
@Bean
public JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

**The two inbound flows in sections 6.1 and 6.3 are alternatives**; do not register both simultaneously on the same queue for one workload. `receiveTimeout(-1)` makes a single receive non-blocking, while `fixedDelay(5000)` is the poll interval—unrelated to broker redelivery policy.

## 7. `errorChannel`: handle the error or ask the broker to retry?

Spring Integration's JMS message-driven inbound adapter supports `errorChannel`. When a handler or message-conversion step throws an exception, the failure can be wrapped in a Spring `ErrorMessage` and sent to the error channel.

**Key takeaway:** an error reaching the error flow **does not automatically mean** the JMS transaction rolls back. If the error flow handles it and returns normally, the listener may treat the callback as successful and commit the JMS transaction. To trigger rollback-based redelivery, the error must **propagate back to the container**, typically by rethrowing an exception from the error flow.

~~~mermaid
flowchart TD
    A["JMS listener receives message, transacted"] --> B["Convert + send to Spring channel"]
    B --> C{"Error?"}
    C -->|"No"| D["Callback succeeds -> JMS commit"]
    C -->|"Yes"| E["ErrorMessage -> errorChannel"]
    E --> F{"Error flow rethrows exception?"}
    F -->|"Yes"| G["Container rollback -> broker redelivery"]
    F -->|"No"| H["Listener may commit -> no redelivery"]
~~~

Since Spring Integration 4.2, **JMS inbound conversion errors** can also be routed through `errorChannel`. Do not rely only on `try/catch` inside business handlers: if a `TextMessage` fails conversion, the business handler may **never have been invoked**.

### 7.1. Configuring an error channel (XML fragment)

~~~xml
<int:channel id="paidOrdersErrors"/>

<int-jms:message-driven-channel-adapter
        id="paidOrdersInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.paid.in"
        channel="paidOrdersInput"
        error-channel="paidOrdersErrors"
        acknowledge="transacted"/>

<int:service-activator
        input-channel="paidOrdersErrors"
        ref="jmsErrorHandler"
        method="handle"/>
~~~

This fragment supplements/replaces the XML endpoint in section 6; declare `paidOrdersInput` and the corresponding beans. This handler only **decides** whether an error should roll back or be recorded/quarantined; it does not magically become a broker DLQ.

### 7.2. Example error handler that explicitly rethrows

~~~java
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component("jmsErrorHandler")
public class JmsErrorHandler {

    public void handle(ErrorMessage error) {
        Throwable cause = error.getPayload();
        // Emit metrics/logs omitting sensitive payload details if needed.
        throw new IllegalStateException(
                "JMS processing failed; propagate for transaction rollback",
                cause);
    }
}
~~~

When this handler is invoked **synchronously** on the listener's error path, the exception can propagate back to the container, causing rollback and redelivery per broker policy. This example **rolls back all errors** to observe the mechanics in a lab; in production, never infinitely retry permanent errors.

**Another strategy:** when an event is determined unprocessable, the app can durably persist a rejection/quarantine state and then let the listener commit. Never treat writing a normal log/error message as safe quarantine. If persisting quarantine state and committing JMS span two different resources, you must still handle the failure window between commits and idempotency.

### 7.3. What happens when no error channel is configured?

In a message-driven adapter without an error channel, conversion/handler errors normally propagate to the listener container; when the container is transacted, rollback can happen. However, if handler code catches the exception and does not rethrow it, no error channel can rescue that situation:

~~~java
try {
    paidOrderConsumer.consume(json);
} catch (Exception ex) {
    log.error("Order failed", ex);
    // Swallowed error: listener may commit despite business failure.
}
~~~

Conversely, for transient failures worth retrying:

~~~java
try {
    paidOrderConsumer.consume(json);
} catch (org.springframework.dao.TransientDataAccessException ex) {
    log.warn("Temporary DB issue; let JMS listener roll back", ex);
    throw ex;
}
~~~

Both snippets are fragments inside a service that already has `log`, not standalone classes. Classify exceptions and bound retries; never assume every `RuntimeException` should be redelivered repeatedly.

## 8. Classifying errors before designing retries

| Error category | Examples | Can retrying the raw JMS message help? | Typical appropriate handling |
|---|---|---|---|
| **Transient infrastructure** | DB disconnect, brief network timeout | Potentially yes | Rollback, bounded exponential backoff |
| **Overload/throttling** | Exhausted connection pool, HTTP 429 | Potentially after load subsides | Backoff, concurrency limits, circuit breaker |
| **Permanent contract** | Malformed JSON syntax, unsupported `schemaVersion` | No, unless data changes | Minimal/zero retries or early DLQ; fix data then replay |
| **Business rejection** | Non-existent `orderId`, rule rejection | Usually no if outcome is final | Record rejection state; intentional commit or quarantine |
| **Duplicate event** | Already processed `eventId` | No need to redo | Idempotent handler returns success so JMS commits |
| **Unknown outcome** | DB may have committed while JMS ack failed | Retries may occur, causing duplicates | Idempotency and durable result lookup |

An intentional business rejection is **not necessarily an infrastructure failure**. For instance, an already-processed `OrderPaid` event in the DB should not roll back to force endless broker redeliveries; an idempotent handler should recognize the duplicate and exit normally.

### Spring-layer retries or broker retries?

There are at least three mechanisms often confused:

1. **In-method/service retry or Spring Retry advice:** retries **within the same JMS delivery/callback** before deciding whether to throw back to the listener. Bound attempt counts and total duration; tying up a consumer too long stalls the queue.
2. **Broker redelivery:** the handler throws, the JMS session rolls back, and the broker decides to **redeliver the message** after a delay up to max delivery attempts.
3. **Replay from DLQ:** once the root cause is fixed or payload corrected under governance, an operator/workflow **re-emits** the message into processing. This is a managed operational action, not a normal automatic delivery.

Since Spring Integration 6.3, certain JMS message-driven endpoints support `RetryTemplate` and `RecoveryCallback` at the listener/dispatch layer. This feature is **version-dependent** and does not replace broker redelivery/DLQ. If both Spring Retry and broker retries are enabled, **total business attempts can multiply**, e.g., 3 in-callback attempts × 5 broker deliveries = up to 15 handler invocations for the same event. Set a unified time budget, backoff, and metrics.

## 9. Broker DLQ: Apache ActiveMQ Artemis example

**Jakarta Messaging does not standardize a common `deadLetterQueue` property** across all JMS providers. Most **DLQ behavior is broker configuration**, not created by `JmsTemplate` or Spring Integration when a handler throws an exception.

For example, in **Apache ActiveMQ Artemis**, an `address-setting` might configure:

~~~xml
<!-- Fragment inside <address-settings> of Artemis broker.xml. -->
<address-setting match="orders.paid.in">
    <dead-letter-address>DLA</dead-letter-address>
    <max-delivery-attempts>5</max-delivery-attempts>
    <redelivery-delay>1000</redelivery-delay>
    <redelivery-delay-multiplier>2.0</redelivery-delay-multiplier>
    <max-redelivery-delay>15000</max-redelivery-delay>
    <auto-create-dead-letter-resources>true</auto-create-dead-letter-resources>
</address-setting>
~~~

**This is Artemis broker configuration, NOT Spring Boot `application.yml` and NOT Spring Integration XML.** Administrators place it in the broker config, define address/queue mappings, and grant access permissions. `DLA` is only an example name; when auto-creation of DLQ resources is enabled, Artemis can create DLQ addresses/queues using prefix/suffix conventions and filters per original address.

Settings breakdown:

- `redelivery-delay=1000`: first redelivery waits roughly 1 second instead of firing immediately.
- `redelivery-delay-multiplier=2`: grows the wait interval after subsequent failures.
- `max-redelivery-delay=15000`: caps exponential backoff delay at the configured ceiling.
- `max-delivery-attempts=5`: Artemis enforces the broker's **delivery attempts** limit; once exceeded, the message moves to the configured **dead-letter-address**.
- `auto-create-dead-letter-resources=true`: allows Artemis to auto-create DLQ resources when allowed; do not assume identical features on other brokers.

**If `dead-letter-address` is omitted in Artemis and a message hits `max-delivery-attempts`, the broker may discard the message instead of keeping it in a DLQ.** Verify actual address settings; a policy that "tries 5 times" with nowhere to store failed messages can silently drop data needing investigation.

### Illustrative backoff

| Delivery attempt | Assuming handler keeps failing | Delay before next attempt |
|---:|---|---:|
| 1 | First failure | 1 second |
| 2 | Still failing | 2 seconds |
| 3 | Still failing | 4 seconds |
| 4 | Still failing | 8 seconds |
| 5 | Still failing | Moved per DLQ policy; no further retries on source queue |

These figures assume no jitter/collision avoidance and strict policy adherence by the broker. In practice, broker delivery accounting, delay calculation, failover, and concurrency can affect observed timings.

### DLQ in Artemis and accompanying metadata

Artemis can attach metadata for **original address/queue** and reason when moving a message to a dead-letter address, such as provider-specific property `_AMQ_ORIG_ADDRESS`. These properties are **not portable Jakarta JMS standards**; only read them after checking documentation for your running Artemis version.

Do not simply inspect `JMSDestination` on a message already sitting in a DLQ and assume it shows the original queue. After dead-lettering, the current destination may be the DLQ itself; preserve original destination and contract metadata in monitoring/quarantine tooling.

## 10. Comparison with ActiveMQ Classic: same concepts, different configuration

**Apache ActiveMQ Classic** configures redelivery/DLQ differently from Artemis. Per Classic documentation:

- Redelivery policy can be controlled from `ActiveMQConnectionFactory`/connection; depending on broker/client, default policies are propagated or overridden.
- After exceeding `maximumRedeliveries`, the client can send a **Poison ACK** so the broker moves the message to the DLQ.
- ActiveMQ Classic's default DLQ is named `ActiveMQ.DLQ`; `individualDeadLetterStrategy` can segregate DLQs per source destination.

| Aspect | Artemis | ActiveMQ Classic |
|---|---|---|
| Primary config | `address-setting` in broker | Broker destination policy and client redelivery policy |
| Attempt limit | `max-delivery-attempts` | `maximumRedeliveries` in redelivery policy |
| Failed message target | `dead-letter-address` and bound queues | Default `ActiveMQ.DLQ` or individual DLQ |
| Backoff | `redelivery-delay`, multiplier, max delay, etc. | `initialRedeliveryDelay`, multiplier, and client/broker options |
| Overriding via Spring Integration | Does not set broker policy itself | Error channel alone does not set broker/client policy |

**Never copy the number "5" from Artemis `max-delivery-attempts` into Classic `maximumRedeliveries` and assume the same callback count.** Classic counts *redeliveries*, whereas Artemis counts total *delivery attempts*; test against your actual broker to confirm how many times the consumer sees the message.

## 11. Broker DLQ differs from `errorChannel`, retry queues, and expiry addresses

Message-driven systems have several "places where failed messages go", serving distinct purposes.

| Mechanism | Who controls it? | When to use? | Automatically retries business logic? |
|---|---|---|---|
| **Broker redelivery** | JMS provider/broker and ack/transaction state | Reprocessing after rollback | Yes, when the broker redelivers the message |
| **Broker DLQ** | Broker redelivery/DLQ policy | Message could not be delivered/processed after limit | **No**: requires operator/workflow replay |
| **Spring `errorChannel`** | `IntegrationFlow` and `ErrorMessage` | Observe, classify, handle exceptions | Does not cause broker redelivery by itself |
| **Application quarantine** | Dedicated service/DB table/queue | Retain failed messages with metadata and status | Only with a corresponding workflow |
| **Retry queue/delayed queue** | App or broker architecture | Defer retry timing off the source queue | Yes when a consumer/forwarder is configured |
| **Expiry address/queue** | Broker TTL/expiry policy | JMS message expired | Usually no; does not imply processing failure |

### Why is DLQ not `errorChannel`?

An `ErrorMessage` is an in-JVM **Spring Message** holding an exception and failed input context. A DLQ is a **JMS destination** on the broker. `errorChannel` does not configure max delivery attempts or move JMS messages to a broker DLQ. The broker normally only knows a message was not committed/acked and must be redelivered; once policy limits are exceeded, the broker dead-letters it.

If the app deliberately publishes a message to a quarantine queue from `errorChannel` and then commits the source message, design a **durable handoff**. Sending to quarantine over a separate connection/transaction and then committing the source JMS creates a failure window (quarantine succeeds but source rolls back → duplicate; source commits before quarantine persists → lost trace). Never assume a regular error-channel send is atomic with JMS receive.

### DLQ is not an expiry queue

A message whose `timeToLive` expires because the server was too slow or consumers were offline too long can be moved by the broker to an **expiry address** or discarded, depending on provider. It was not necessarily attempted and failed by a consumer. In Artemis, `expiry-address` is separate from `dead-letter-address`.

Example: `OrderPaid` has a 60-second TTL while accounting is down for 4 hours: the message can expire **even if the converter/handler was never called**. Enabling durable subscriptions or DLQ will not negate TTL. Align retention times with business SLAs.

## 12. Idempotency: safe processing when messages arrive again

### 12.1. Boundary between JMS transaction and DB transaction

~~~mermaid
sequenceDiagram
    participant Broker as JMS broker
    participant Listener as JMS listener
    participant DB as PostgreSQL

    Broker->>Listener: Deliver evt-1201
    Listener->>DB: BEGIN; insert eventId; update order
    DB-->>Listener: COMMIT succeeded
    Note over Listener: Failure before JMS commit
    Broker-->>Listener: Redelivery evt-1201
    Listener->>DB: Check whether eventId was processed
    DB-->>Listener: Already exists, skip duplicate side effect
    Listener->>Broker: JMS commit
~~~

A local JMS transaction can span JMS receives/sends on the same resource/session, yet is **not automatically atomic with a PostgreSQL transaction**. Thus, **at-least-once delivery + idempotent consumer** is an essential design.

### 12.2. Storing the processed key in the same DB transaction

PostgreSQL example:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sales_order (
    order_id VARCHAR(100) PRIMARY KEY,
    paid BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Java service:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaidOrderService {
    private final JdbcTemplate jdbc;

    public PaidOrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "orderDbTxManager")
    public void applyPayment(String eventId, String orderId) {
        int inserted = jdbc.update(
                "INSERT INTO processed_event(event_id) VALUES (?) "
                + "ON CONFLICT DO NOTHING", eventId);

        if (inserted == 0) {
            return; // Already processed duplicate: make no further updates.
        }

        int updated = jdbc.update(
                "UPDATE sales_order SET paid = TRUE WHERE order_id = ?",
                orderId);
        if (updated != 1) {
            throw new IllegalStateException("Unknown order: " + orderId);
        }
    }
}
~~~

Assume `orderDbTxManager` is an existing PostgreSQL transaction manager and the method is called via a Spring proxy. The `processed_event` row and order update sit in the **same DB transaction**; if the update fails, both roll back. When the broker redelivers the same event, the unique constraint safely ignores the duplicate insert.

Production code must expand on this sample: validate `eventId`/`orderId` and schema beforehand, consider race conditions/isolation levels, distinguish benign duplicates from conflicting payloads sharing an event ID, and define retention for deduplication records. **Never use `JMSXDeliveryCount` to decide whether the DB was already updated.**

### 12.3. From DB to JMS: transactional outbox

When business logic must **write to the database and then emit a JMS event**, do not assume `@Transactional` on the DB makes the JMS send commit together. Write the event into an **outbox table** in the same DB transaction as the business change; a separate publisher sends to JMS and marks it sent. If the publisher crashes after sending but before marking sent, the event may appear twice, so consumers must remain idempotent.

### 12.4. Delivery counts do not solve producer-side duplicates

An event can re-enter a queue in two ways:

1. **Broker redelivery:** source message was not JMS-committed so it is delivered again.
2. **Producer duplicate:** producer timed out/was uncertain whether the broker accepted the send and resent **a brand-new JMS message** with the same business `eventId`.

Both scenarios require idempotency. Likewise, DLQ/replay workflows must preserve or record the stable `eventId` when replaying.

## 13. Topic subscriptions, concurrency, and ordering after redelivery

DLQs do not apply only to queues. A topic can have multiple independent subscriptions; each subscription has its own receive/ack/redelivery state per provider. An `OrderPaid` message may succeed in warehouse while failing repeatedly in accounting. Never infer from one subscription's success that all subscriptions processed the message.

| Scenario | Risk | Considerations |
|---|---|---|
| Queue with 4 competing consumers | Redelivered event may land on a different consumer; completion out of order | Idempotency, versioning, message grouping if broker-supported |
| Topic with 3 independent subscriptions | Three logical copies, independent failure outcomes | Monitor backlog/DLQ per subscription |
| Shared durable subscription | Multiple consumers split events within one subscription | Correctness on retries, ordering, and client ID |
| Non-durable topic subscriber offline | Events published while offline may not be saved | Consider durable subscriptions and TTL |
| Broker delays redelivery of one message | Later event may be processed earlier | Check `aggregateVersion` or ordering strategy |

When an aggregate requires strict ordering, **rollbacks and delayed redelivery can alter observed processing order**, especially with multiple consumers on a queue. Use message groups/partitioning by `orderId` if supported by the provider, or optimistic locking/version checks in the database.

**Concurrency increases the number of concurrent JMS transactions**, rather than placing four messages into one shared transaction. Rolling back event A does not roll back event B committed by another consumer.

## 14. Investigation and safe DLQ replay workflow

Sending a message to a DLQ is only the **beginning** of incident resolution. Replaying all DLQ messages immediately upon app restart can spread bad data, overload downstream systems, and trigger duplicate business side effects.

### 14.1. Recommended runbook

1. **Contain the incident:** identify source queue/subscription, DLQ count, growth rate, and current errors. Do not replay while the root cause is still failing.
2. **Classify the error:** transient DB outage, incompatible schema, missing data, business rejection, or regression from a recent deploy. Record `firstSeen`/`lastError`/`failureReason` in tracking tools.
3. **Trace origin:** inspect broker-provided original destination metadata, `eventId`, `JMSMessageID`, publish timestamp, and producer version. Do not blindly trust provider-specific properties from another environment.
4. **Verify safety:** did the event already mutate the DB? Is `eventId` already in the inbox? Are TTL and data contracts still valid?
5. **Fix before replaying:** deploy support for the new schema, restore DB health, or produce a corrected message via an audited/approved workflow. Never manually edit monetary/financial payloads without business controls.
6. **Replay in small batches:** rate-limit messages/second, keep business `eventId` stable, monitor failures, and prevent self-looping replays.
7. **Verify results:** reconcile replayed count, succeeded count, remaining errors, DB state, and any newly generated DLQ items.
8. **Close incident:** archive evidence, update dashboards/alerts, and ensure the workflow neither lost nor leaked sensitive data.

~~~mermaid
flowchart TD
    A[("DLQ holds failed messages")] --> B["Classify + inspect metadata"]
    B --> C{"Root cause fixed?"}
    C -->|"No"| D["Keep isolated, alert"]
    C -->|"Yes"| E{"Event already processed by eventId?"}
    E -->|"Yes"| F["Mark duplicate, do not replay business effect"]
    E -->|"No"| G["Controlled replay to source destination"]
    G --> H["Monitor status + throughput + new DLQ"]
    H --> I{"Succeeded?"}
    I -->|"Yes"| J["Audit outcome"]
    I -->|"No"| D
~~~

### 14.2. Replay and transaction boundaries

If a tool consumes messages from a DLQ and sends them back to the original queue, check:

- Are both destinations on the same JMS broker/resource so they can share **the same local JMS transaction**?
- Are receiving from DLQ and sending to source committed together or separately? If separate, tolerate duplicate/lost handoffs.
- Will the replayed message keep the same `JMSMessageID`, `JMSXDeliveryCount`, and `JMSRedelivered`? **Never assume** they stay identical; business `eventId` should be the stable correlation key.
- Are original payload, `contentType`, `schemaVersion`, event timestamp, correlation, and authorization context preserved per contract?
- DLQ messages may contain PII or secrets; who is authorized to read, edit, and replay them?

During hands-on exercises, **inspect and replay only on a test broker**. In production, replays require rate limits, authorization checks, and organizational auditing.

## 15. Observability: measuring where failures happen

| Metric/event | Source | Abnormal signal |
|---|---|---|
| `source queue depth` | Broker | Backlog growing steadily |
| `oldest message age` | Broker | SLA being breached |
| `redelivery rate` | Broker/client metrics | Repeated errors or unstable downstream |
| `JMSXDeliveryCount` distribution | Message metadata | Many messages with high counts |
| `DLQ depth` and growth rate | Broker | Poison messages or buggy new release |
| `DLQ age` | Broker | Messages left uninvestigated too long |
| `listener error count` by exception | Spring Integration | Distinguish conversion vs. DB timeout vs. business rules |
| `consumer count` / concurrency | Container and broker | Container failed to recover or DB saturated |
| `DB deduplication hits` | Business DB | Heavy duplicates from replay, producer retry, or JMS redelivery |
| `retry total duration` | App + broker | Single message tying up resources, causing cascading timeouts |
| `replay success/failure` | Re-drive workflow | Replay failing to drain backlog or creating new DLQ entries |

**Recommended logging:** `eventId`, source destination, JMS message ID, correlation ID, redelivery flag/count when available, error class, application version, protected tenant key, and processing time. Never log raw bodies containing tokens, personal data, or account numbers. When retaining payloads for investigation, use secure storage with proper retention and access controls.

### Alerts worth having

- New messages landing in the DLQ for critical financial/order events.
- `oldest message age` breaching SLA or queue depth rising despite active consumers.
- Redelivery rate and DB timeouts rising together (downstream outage signal).
- One message repeatedly failing conversion across all instances (poison-message loop).
- Rapid DLQ growth or elevated `eventId` duplicates right after a replay.

**A pretty dashboard cannot replace verifying business state correctness.** For critical events, reconcile DB/business system records alongside broker metrics.

## 16. Hands-on lab: intentionally triggering errors to understand redelivery and DLQ

**Environment:** Java 17+, Spring Integration/JMS, a test **ActiveMQ Artemis** JMS broker, `orders.paid.in` queue, PostgreSQL or a test database, and a separate JMS producer. Use the `sessionTransacted(true)` listener configuration from section 6 paired with the broker redelivery/DLQ policy from section 9.

Valid message example:

~~~json
{
  "eventId": "evt-1201",
  "schemaVersion": 1,
  "eventType": "OrderPaid",
  "orderId": "ORD-1201",
  "amountMinor": 250000,
  "currency": "VND"
}
~~~

Permanently invalid message example:

~~~json
{
  "eventId": "evt-1202",
  "schemaVersion": 999,
  "eventType": "OrderPaid",
  "orderId": "ORD-1202"
}
~~~

In the consumer, treat `schemaVersion=999` as unsupported and **throw an unhandled exception**. Do not just log and return success when testing redelivery. The test producer can send:

~~~java
// Producer JmsTemplate bean connected to Artemis.
jmsTemplate.convertAndSend(
        "orders.paid.in",
        "{\"eventId\":\"evt-1202\",\"schemaVersion\":999,"
        + "\"eventType\":\"OrderPaid\",\"orderId\":\"ORD-1202\"}");
~~~

### Lab A — Happy path and JMS commit

1. Send `evt-1201` with `schemaVersion=1` and let the service process normally.
2. Verify the handler runs, the database updates successfully, and the queue drains.
3. Verify `JMSXDeliveryCount` on first receipt is normally 1.
4. Confirm an event does not go to the DLQ merely for having `JMSReplyTo` or `JMSCorrelationID` headers; DLQ routing depends on delivery/processing failures, not request-reply headers.

### Lab B — Transient infrastructure failure and redelivery

1. Have the handler throw an exception simulating a brief database outage.
2. Observe JMS rollback and `JMSRedelivered`/`JMSXDeliveryCount` across subsequent attempts.
3. Measure delay intervals and compare with Artemis `redelivery-delay` and multiplier.
4. Restore the database before exceeding the threshold; verify the message succeeds without entering the DLQ.
5. Inspect the DB to ensure only one business side effect occurred.

### Lab C — Poison message and dead-letter address

1. Send `evt-1202` with unsupported `schemaVersion=999`.
2. Ensure conversion/validation errors propagate to the transacted listener.
3. Observe redeliveries; verify the broker stops delivering from the source after `max-delivery-attempts`.
4. Open the Artemis DLQ queue and verify the message appears with `eventId` and source metadata.
5. Place a valid event `evt-1203` behind the broken message and verify the consumer continues processing valid work per broker queue/ordering policy.

### Lab D — Difference between error channel and DLQ

1. Configure `errorChannel` with an error handler that logs and **returns normally**. Resend the failing event in a new JMS message; observe that the listener can commit and drain the source queue without incrementing the DLQ.
2. Change the handler to **rethrow the exception** and test with a new event ID; observe redelivery followed by DLQ per broker policy.
3. Explain why a Spring `ErrorMessage` does not automatically become a JMS DLQ message.
4. Add exception-classification metrics so schema errors are never confused with DB timeouts.

### Lab E — Transactions, duplicates, and idempotency

1. Use `PaidOrderService.applyPayment` and the `processed_event` table.
2. Let DB commit succeed, then simulate a failure preventing JMS commit (in a controlled test environment).
3. When the event arrives again, verify unique `eventId` makes the handler return normally without a second update.
4. Have the producer resend **the same `eventId` in a new JMS message**; verify idempotency still works even though `JMSRedelivered` does not reflect a business duplicate.
5. Insert an `ExecutorChannel` before the DB handler and explain why async errors do not automatically roll back the original JMS receive.

### Lab F — Replay from DLQ

1. Update code to support `schemaVersion=999` in the test environment, or prepare a valid payload under controlled procedures.
2. Pick one message from the DLQ and record original destination, `eventId`, relevant content, and failure reason.
3. Replay one message and verify the source consumer processes it successfully.
4. Replay the same event a second time; `processed_event` must prevent duplicate business side effects.
5. Ramp replay rate from 1 to 10 msg/s in test while watching DB pool, queue age, and new DLQ entries; stop if error rate climbs.

### Minimum test matrix

| Scenario | Expected observation |
|---|---|
| Handler succeeds | Source message commits; does not enter DLQ |
| Transacted handler throws transient exception | Rollback, redelivery, succeeds after recovery |
| Permanent converter failure without swallowing error | Bounded retries then DLQ per broker policy |
| Error flow handles without rethrowing | Message may commit, **no** broker retry |
| Two JMS consumers on same queue | Duplicates/redeliveries may land on different consumers; do not assume strict order |
| DB commits yet JMS rolls back | Event arrives again without duplicating business side effects |
| Producer retries with new message ID | `eventId` still catches duplicate |
| Message exceeds TTL | Inspect expiry policy; do not assume processing DLQ |
| Replay a DLQ message | Preserves business ID, audited, no DLQ loop |
| Broker restart/failover | Recovery and delivery counts match provider/version behavior |

**You must use a real broker or matching test container to verify transactions, rollbacks, redelivery, DLQ, and metadata.** Mocking `JmsTemplate`, `MessageChannel`, or services only proves local logic and does not simulate full broker delivery policies.

## 17. Self-check questions

1. How does redelivery differ from a producer resending the same event in a new JMS message?
2. Why does `JMSRedelivered=false` not prove a business event has never been processed?
3. What value does `JMSXDeliveryCount` start from? Why should it not be used as an idempotency key?
4. Under what conditions does a handler exception trigger rollback in a JMS message-driven listener?
5. If `errorChannel` swallows an exception, how can broker behavior change?
6. Why does `JmsTemplate.sessionTransacted=true` on a polling source not protect downstream handlers automatically?
7. What are the differences among **Spring Retry inside the same callback**, **broker redelivery**, and **DLQ replay**?
8. Where are Artemis `dead-letter-address` and `max-delivery-attempts` configured?
9. If Artemis has no dead-letter address configured and a message hits its limit, what is the risk?
10. Why can you not assume `maximumRedeliveries=5` in ActiveMQ Classic produces the same callback count as `max-delivery-attempts=5` in Artemis?
11. How does a DLQ differ from an expiry address in cause and purpose?
12. Why should a DLQ not be bulk-replayed immediately after deploying a fix?
13. When the DB commits but JMS commit fails, how do you prevent duplicate data writes?
14. How does switching from `DirectChannel` to `ExecutorChannel` affect rollback and redelivery?
15. If multiple subscriptions share a topic, does a failure in one subscription force all other subscriptions to redeliver?
16. Which metrics distinguish broker backlog, transient downstream failure, and a poison-message loop?

## 18. References

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): transacted default for message-driven adapters, polling adapter transactions, `errorChannel`, and conversion errors.
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): `DefaultMessageListenerContainer`, `sessionTransacted`, JMS transactions, and limitations with DBs.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate`, listener containers, acknowledgments, and transactions.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `JMSRedelivered`, `JMSXDeliveryCount`, redelivery, and acknowledgment semantics.
- [Apache ActiveMQ Artemis — Message Redelivery and Undelivered Messages](https://artemis.apache.org/components/artemis/documentation/latest/undelivered-messages): `redelivery-delay`, `max-delivery-attempts`, `dead-letter-address`, and delivery count persistence.
- [Apache ActiveMQ Artemis — Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html): broker DLQ config, auto-creating dead-letter resources, and expiry addresses.
- [ActiveMQ Classic — Message Redelivery and DLQ Handling](https://activemq.apache.org/components/classic/documentation/message-redelivery-and-dlq-handling): redelivery policies, Poison ACK, `ActiveMQ.DLQ`, and individual DLQs.
- [ActiveMQ Classic — Redelivery Policy](https://activemq.apache.org/components/classic/documentation/redelivery-policy): `maximumRedeliveries`, initial delay, and backoff properties.

**Remember:** redelivery is the broker's ability to resend an unacknowledged JMS message, while a DLQ is where messages are isolated once failure policies take effect. In Spring Integration, getting broker redelivery requires setting the proper **JMS transaction/acknowledgment boundary** and not accidentally swallowing exceptions via `errorChannel`. Retry delays, max attempts, DLQs, and expiry are **broker/provider-specific configurations**; `eventId`-based idempotency, monitoring, and controlled replays are what protect business correctness across failures and retries.
