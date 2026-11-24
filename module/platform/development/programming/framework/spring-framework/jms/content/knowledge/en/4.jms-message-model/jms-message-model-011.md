# JMSRedelivered, JMSXDeliveryCount, and Redelivery Traces in JMS

## Learning Objectives

This lesson focuses on the **Message model in Jakarta Messaging (JMS)**, specifically two indicators attached by the JMS provider when a consumer receives a message again:

- **`JMSRedelivered`**: a boolean header accessed via `Message.getJMSRedelivered()`. It shows that the provider marked the message as being redelivered.
- **`JMSXDeliveryCount`**: an `int` property read via `Message.getIntProperty("JMSXDeliveryCount")`. The first delivery has value `1`; subsequent redeliveries typically have `2`, `3`, ...
- **Redelivery trace**: combining these two signals with message ID, event/business ID, correlation ID, destination, timestamps, consumer instance, and processing outcomes to investigate *why the same message appeared multiple times*.

After this lesson, you will be able to detect redelivery; distinguish a delivery attempt from a business processing attempt; understand accuracy boundaries; configure Spring JMS so failures genuinely trigger rollback/redelivery; write Java 17 code to inspect metadata; and design appropriate logging, idempotency, retry, and DLQ practices.

> **Principle:** `JMSRedelivered` and `JMSXDeliveryCount` are **delivery diagnostic information**, not guarantees of how many times business logic ran or that duplicate processing cannot occur.

## 1. What Is Redelivery?

A JMS message can be delivered by the broker to a consumer yet **not successfully acknowledged/committed**. If the consumer rolls back, recovers the session, loses its connection, or the provider suffers a failure before receipt is confirmed, the message may be delivered again. The same payload appears on the new delivery, while metadata reflects the redelivery.

~~~text
Producer                 JMS broker                  Consumer
   │ send(OrderCreated)      │                           │
   ├─────────────────────────►│                           │
   │                          │ first delivery             │
   │                          ├───────────────────────────►│
   │                          │ JMSRedelivered=false       │
   │                          │ JMSXDeliveryCount=1        │
   │                          │                            │ process → error/rollback
   │                          │◄───────────────────────────┤
   │                          │                            │
   │                          │ redelivery                 │
   │                          ├───────────────────────────►│
   │                          │ JMSRedelivered=true        │
   │                          │ JMSXDeliveryCount=2        │
   │                          │                            │ process → commit
   │                          │◄───────────────────────────┤
~~~

This is the **typical** behavior of a Jakarta Messaging–compliant provider. Ordering, wait delays, attempt counts, routing to a dead-letter queue (DLQ), and counter durability across crashes depend on the provider and broker configuration.

### Three Concepts Easily Confused

| Concept | Question it answers | Example |
|---|---|---|
| **Delivery attempt** | How many times has the broker tried to deliver this message to a consumer? | `JMSXDeliveryCount=3`: provider reports the third delivery attempt. |
| **Processing attempt** | How many times did business code actually begin running? | The consumer could crash **before** the callback starts, despite a delivery occurring. |
| **Business effect** | How many times did the external transaction outside JMS actually take effect? | The DB might have saved the order once even though the callback ran twice. |

These three counts are not necessarily equal. Therefore **never** count payments, emails sent, or DB writes using `JMSXDeliveryCount`.

## 2. `JMSRedelivered`: Header Warning of Possible Redelivery

### 2.1. Reading in Java

~~~java
// Code snippet inside a method that received jakarta.jms.Message.
boolean redelivered = message.getJMSRedelivered();
System.out.println("JMSRedelivered=" + redelivered);
~~~

`getJMSRedelivered()` returns `boolean` and can throw `JMSException`. This is a **JMS standard header**, not an application-defined property. The Java API name is `getJMSRedelivered()`, not `getBooleanProperty("JMSRedelivered")`.

When a producer sends a message, this header **carries no application meaning**; the provider sets redelivery state upon delivery. `setJMSRedelivered(boolean)` exists on the interface so providers can manipulate message implementations, **not** for producers to declare or control retry policies.

### 2.2. Exact Meaning of `true` and `false`

- `true`: the provider indicates the message **was likely** delivered previously without being acknowledged. The specification uses cautious wording: likely, **with no guarantee** that application code actually processed the message the first time.
- `false`: you cannot conclude that *business logic definitely never ran*. A producer might republish a logical event as a new message; upstream data might be duplicated; or a failure might prevent delivery tracking from reflecting full history.
- When the provider redelivers due to session recovery or system failures, the JMS specification requires setting the redelivered flag and incrementing the delivery count under specified conditions. Still, the flag itself is only broker-side metadata.

For example: the broker delivers a message to a consumer, yet the JVM is killed before the listener method runs. Next time the header is `true`, even though business logic never started. Conversely, if the producer sends the same event ID a second time, that is a **new JMS message** whose flag may be `false`.

### 2.3. This Header Does Not Control ACK

`JMSRedelivered` is purely for **observation and safe handling**. It does not mean the message will automatically roll back or move to a DLQ. Ack/commit/rollback behavior is determined by the session, listener container, and broker policy.

Incorrect pattern:

~~~java
// Wrong: skipping every redelivered message can lose business work.
if (message.getJMSRedelivered()) {
    return;
}
~~~

If the first delivery died before saving data, the second delivery is the chance to complete the work. Instead of skipping based on the flag, use a **business idempotency key** paired with durable recording of processed state.

## 3. `JMSXDeliveryCount`: Provider Delivery Attempt Count

### 3.1. This Is a Mandatory Standard Property

Since JMS 2.0 (and in Jakarta Messaging 3.x), **the provider must set** `JMSXDeliveryCount` on a message when the consumer receives it. It is an `int` property in the `JMSX...` group, not a header with a dedicated getter.

~~~java
// Snippet inside a method receiving jakarta.jms.Message.
int deliveryCount = message.getIntProperty("JMSXDeliveryCount");
System.out.println("deliveryCount=" + deliveryCount);
~~~

| Delivery count | Common interpretation |
|---:|---|
| `1` | Provider is delivering the message for the first time. |
| `2` | Message has been redelivered at least once. |
| `3` | Message is on its third delivery according to the provider counter. |
| `5` | Repeated delivery history; inspect retries, errors, DLQ, and policies. |

**Specification constraint:** if `JMSRedelivered=true`, `JMSXDeliveryCount` must be **2 or greater**. Conversely, if metadata violates that constraint, inspect the provider, client version, bridge, or test setup.

### 3.2. No Guarantee the Counter Is Always Strictly Exact

Jakarta Messaging specification section **3.5.11** explicitly states that `JMSXDeliveryCount` **is not guaranteed to be accurate in all situations**. Providers are not required to persist the counter durably across every broker failure.

Practical consequences:

- `JMSXDeliveryCount=3` is useful diagnostic evidence, **not** absolute audit proof of three business executions.
- Broker restarts/failovers, bridges, or DLQ moves/re-drives can cause observed sequences to differ from clean increments of `1` in every environment.
- The counter measures provider **deliveries**, without distinguishing whether the consumer read headers, ran logic, or committed side effects.
- Never build **payment deduction logic, business execution caps, or exactly-once guarantees** solely on the delivery count.

### 3.3. Never Filter with a JMS Selector on Receive-Time Properties

`JMSXDeliveryCount` is attached by the provider **at receive time**; the specification states that the effect of a message selector referencing properties set by the provider on receive is **undefined**. Therefore do not configure consumers to filter messages using:

~~~sql
JMSXDeliveryCount > 3
~~~

This is strictly an **anti-pattern selector example**, not SQL to run. Instead: read delivery count **inside the consumer**, use broker retry/DLQ policies to cap attempts, and monitor via logging/metrics.

### 3.4. Do Not Overwrite with `setIntProperty`

Do not have producers set `JMSXDeliveryCount` as an application property to substitute for the provider counter. Only the provider decides the standard value at delivery time; producers wishing to carry a **business-level** attempt counter should use a distinct property such as `appAttempt` and document its meaning. Never invent custom properties starting with `JMSX`, as that prefix is reserved by the JMS specification.

## 4. Distinguishing Headers/Properties for Accurate Trace Reading

| Field | Kind | Access from `jakarta.jms.Message` | Purpose |
|---|---|---|---|
| `JMSRedelivered` | Standard header, boolean | `getJMSRedelivered()` | Shows the provider marked a redelivery. |
| `JMSXDeliveryCount` | Standard provider property, int | `getIntProperty("JMSXDeliveryCount")` | Tracks delivery attempts per broker. |
| `JMSMessageID` | Standard header, String | `getJMSMessageID()` | Distinguishes/correlates physical messages assigned by provider. |
| `JMSCorrelationID` | Standard header, String | `getJMSCorrelationID()` | Links request/response or workflow steps if set by application. |
| `JMSTimestamp` | Standard header, long | `getJMSTimestamp()` | Timestamp associated with provider send; **not** the latest retry time. |
| `JMSDestination` | Standard header, Destination | `getJMSDestination()` | Records send/receive destination. |
| `JMSExpiration` | Standard header, long | `getJMSExpiration()` | Expiration timestamp per TTL; `0` typically means no expiration. |
| `eventId` | App property, String | `getStringProperty("eventId")` | Identifies the **business event**, used for idempotency. |
| `traceparent` | App property, String | `getStringProperty("traceparent")` | Propagates trace context across services for observability. |

A JMS message has **headers**, **properties**, and **body**. `JMSRedelivered` is a header; `JMSXDeliveryCount` is a property; `eventId` is an application-chosen name. In Spring, you can access metadata via raw `jakarta.jms.Message` or mapped Spring message headers, provided namespaces are kept clear.

### 4.1. `JMSMessageID` and `eventId` Have Different Roles

Suppose a producer emits a business event `OrderCreated(order-84)`. The JMS provider generates `JMSMessageID=ID:abc`. If the broker redelivers **the same JMS message**, the ID normally stays the same to identify that message. If the producer sends *a new message* because it was unsure whether the first send succeeded, the provider may issue `ID:def` even though the logical event is still `order-84`.

~~~text
A. Redelivery due to rollback:
   first  → JMSMessageID=ID:abc, eventId=evt-84, count=1
   retry  → JMSMessageID=ID:abc, eventId=evt-84, count=2

B. Producer sends duplicate logical event:
   send 1 → JMSMessageID=ID:abc, eventId=evt-84, count=1
   send 2 → JMSMessageID=ID:def, eventId=evt-84, count=1
~~~

IDs in the diagram are illustrative only; real formats depend on the JMS provider. When messages cross bridges, move to a DLQ and get re-driven, or are recreated, IDs/headers can change depending on the implementation. **Use a durable `eventId`** (or well-defined unique business key) for business deduplication; use `JMSMessageID` to correlate JMS deliveries and broker logs.

### 4.2. Correlation ID and Trace ID Are Not Attempt Counters

`JMSCorrelationID` is usually set by clients to link requests to responses or messages in a workflow, not as a redelivery counter. In distributed tracing, `traceparent`/trace ID links spans across services; a redelivery can produce a **new consumer span** while `eventId` remains unchanged. Preserving trace context when sending events helps investigate event chains; do not use correlation ID instead of event uniqueness if one workflow emits multiple events sharing the same correlation ID.

## 5. When Does Metadata Change?

### 5.1. Consumer Rollback in a Transacted Session

~~~text
Queue ─► consumer receives M (count=1, redelivered=false)
                 │
                 ▼
          processing error
                 │
            session.rollback()
                 │
                 ▼
       broker prepares to redeliver M
                 │
                 ▼
       consumer receives M (count=2, redelivered=true)
                 │
                 ▼
            session.commit()
~~~

In a session with local transactions enabled, `commit()` confirms receipt under the transaction and `rollback()` rejects receipt and requests redelivery per provider policy. In Spring's `DefaultMessageListenerContainer`, `sessionTransacted=true` lets throwing an exception from a listener trigger container rollback; you do **not** need to call `session.rollback()` manually inside a normal `@JmsListener` method.

### 5.2. `CLIENT_ACKNOWLEDGE` and `Session.recover()`

In a **non-transacted** session using `CLIENT_ACKNOWLEDGE`, the client calls `message.acknowledge()` to confirm receipt. Per the JMS specification, a single acknowledge call confirms **all messages delivered by that session**, not just the message on which it was called.

To request redelivery of unacknowledged messages on this session, the application can call `session.recover()`; the specification requires setting `JMSRedelivered` and incrementing `JMSXDeliveryCount` for messages redelivered due to recovery.

**Note:** `recover()` is a session operation, not `rollback()` in a local transacted session. Never acknowledge a message first and then expect `recover()` to bring back an already-confirmed message.

### 5.3. Connection Failure or Consumer Crash

If a consumer received M without acking/committing, the broker can redeliver M to a new consumer once connections/sessions recover. The prior delivery **may** never have invoked the listener. If the DB already committed before JMS ack, the new listener can duplicate side effects. That is why idempotency is necessary.

### 5.4. `AUTO_ACKNOWLEDGE` and `DUPS_OK_ACKNOWLEDGE`

- `AUTO_ACKNOWLEDGE`: acknowledgment timing is governed by the JMS API/provider depending on how messages are received. In synchronous receive, a successful receive auto-acks; in pure JMS callbacks, callback completion ties to ack. It does not let applications arbitrarily roll back by throwing exceptions inside a Spring container.
- `DUPS_OK_ACKNOWLEDGE`: permits lazy acknowledgment; duplicate deliveries can occur under failures. Understand its semantics and provider behavior before choosing it.
- **Especially important in Spring:** `DefaultMessageListenerContainer` with default `AUTO_ACKNOWLEDGE` auto-acknowledges before invoking the listener; if the listener method throws an exception, **there is no redelivery from that exception alone**. To test and run controlled redelivery, use a transacted session or an appropriate transaction manager.

| Event | Can redeliver? | Expected trace |
|---|---|---|
| `session.rollback()` on a JMS transacted session | Yes, subject to retry limits and policy | Next delivery has `JMSRedelivered=true`, count increases. |
| `session.recover()` after unacked delivery on non-transacted session | Yes | Flag true, count increases for redelivered messages. |
| JVM/network dies before ack/commit | Yes | Inspect message ID, count, consumer instance; counter may be imprecise after failures. |
| Listener throws exception in Spring container with `sessionTransacted=true` | Yes | Container rolls back; provider applies redelivery policy. |
| Listener throws exception in Spring `DefaultMessageListenerContainer` default AUTO_ACK | Not reliably from that exception | Message may already be acked before processing. |
| Producer sends a new message with duplicate payload | This is **not** redelivery of the same JMS message | New `JMSMessageID`; count usually starts back at 1. |
| Consumer receives and commits successfully | Same message not redelivered by normal retries | Should not see a redelivery once ack is confirmed. |

## 6. Scenarios That Must Not Be Misinterpreted

### 6.1. `JMSRedelivered=true` Does Not Prove Business Logic Ran

The broker may write the message onto the socket and then the connection dies before the callback starts. The next delivery is marked as a redelivery, yet business logic **never executed**. Never skip M simply because the flag is true.

### 6.2. `JMSRedelivered=false` Does Not Prove It Is the First Business Execution

A logical message can be published twice by a producer, HTTP retry, outbox relay, or upstream system. Each new JMS message can have `count=1` despite sharing the same `eventId`. Idempotency must rely on a stable event/business ID.

### 6.3. Increasing Count Does Not Prove the Bug Is in the Business Handler

A message may be rolled back due to database timeouts, message converter exceptions, transaction timeouts, container shutdowns, or infrastructure errors. Logs should distinguish **received**, **processing_started**, **processing_failed**, **rollback**, and **commit** when observable at the application layer. Never assign root cause solely from the count.

### 6.4. Count Does Not Always Increment Forever

When a broker moves a message to a DLQ, an admin re-drives it, or a consumer bridges/forwards by creating another JMS message, the counter may reset or metadata may change depending on the broker. `JMSXDeliveryCount` cannot serve as a universal attempt counter across multiple queues and brokers.

### 6.5. Never Use `JMSRedelivered` as a "Process Only When False" Condition

Code like this is dangerous:

~~~java
// Anti-pattern. If the first attempt rolled back before finishing,
// the message is permanently skipped on subsequent deliveries.
if (!message.getJMSRedelivered()) {
    chargeCreditCard();
}
~~~

The same flaw remains if you swap the flag for `JMSXDeliveryCount == 1`. To guarantee no duplicate charge, you need a business-defined idempotency key and durable state persistence.

## 7. Capturing Redelivery Traces in Java

### 7.1. Reading Metadata in Spring `@JmsListener`

Spring Framework permits raw `jakarta.jms.Message`/`TextMessage` parameters in `@JmsListener` methods. That lets code read the original fields directly:

~~~java
// Snippet inside a bean configured with Spring JMS.
@JmsListener(destination = "orders.queue")
public void handle(TextMessage message) throws JMSException {
    boolean redelivered = message.getJMSRedelivered();
    int deliveryCount = message.getIntProperty("JMSXDeliveryCount");

    String jmsMessageId = message.getJMSMessageID();
    String correlationId = message.getJMSCorrelationID();
    String eventId = message.getStringProperty("eventId");
    String payload = message.getText();

    // Log structured metadata; do not log sensitive payloads to production logs.
    log.info("jms_received eventId={} jmsMessageId={} correlationId={} "
                    + "redelivered={} deliveryCount={}",
            eventId, jmsMessageId, correlationId,
            redelivered, deliveryCount);

    process(payload, eventId); // Business layer needs idempotency.
}
~~~

**This is a snippet, not a standalone Java class:** it assumes logger `log`, `TextMessage`/`JMSException` imports, and a `process(...)` method. In production, if `process` throws an exception, whether the broker redelivers **depends on the listener container/transaction configuration**, not the annotation alone.

### 7.2. What Should Be Logged?

A log record for **each delivery** can include:

| Log field | Source | Diagnostic meaning |
|---|---|---|
| `eventId` / `businessKey` | Application-set property/header | Groups attempts for the same logical event. |
| `jmsMessageId` | `getJMSMessageID()` | Distinguishes physical JMS messages. |
| `jmsCorrelationId` | `getJMSCorrelationID()` | Traces a flow/request. |
| `jmsRedelivered` | `getJMSRedelivered()` | Provider redelivery marker. |
| `jmsDeliveryCount` | `getIntProperty("JMSXDeliveryCount")` | Observes delivery count. |
| `destination` | `getJMSDestination()` or listener config | Queue/topic being processed. |
| `service`, `instanceId`, `consumerName` | Service config | Which consumer received the message. |
| `receivedAt`, `processingMs`, `outcome` | Application log | Timestamp, latency, processing outcome. |
| `exceptionType` / `errorCode` | Error handling | Diagnoses failure cause without leaking secrets. |
| `traceId` / `spanId` | Observability context | Links consumer attempt to cross-service trace. |

Illustrative structured log example (sample IDs are intentional):

~~~json
{
  "event": "jms_message_received",
  "service": "billing-worker",
  "instanceId": "billing-02",
  "eventId": "evt-84",
  "jmsMessageId": "ID:abc",
  "jmsCorrelationId": "order-84",
  "destination": "billing.queue",
  "jmsRedelivered": true,
  "jmsDeliveryCount": 2,
  "receivedAt": "2026-10-30T01:15:20Z"
}
~~~

On the subsequent step, emit `processing_completed` or `processing_failed` with the **same `eventId`, `messageId`, and attempt**, plus processing duration. Never dump full payloads containing PII, bearer tokens, secrets, or payment data just for debugging.

### 7.3. Signals When Events Are Missing from Logs

Missing logs do not prove the broker never delivered: the connection may have died before the callback, app logs may be flushed away on process crash, or the listener failed during conversion before entering the method. Combine broker metrics, DLQ counts, container error handlers, transaction logs, and tracing to close the investigation loop.

## 8. Runnable Demo with Java 17, Spring Boot, and ActiveMQ Artemis

The demo intentionally triggers **one processing error on the first delivery** so the JMS transaction rolls back. When the broker redelivers, the listener reads `JMSRedelivered=true` and `JMSXDeliveryCount=2` and then completes. This is a controlled local demonstration, not a simulation of all production retry/HA policies.

### 8.1. Prepare the Local Broker

Requires **Docker**, **JDK 17+**, and **Maven 3.9+**. Open a terminal and start the official broker:

~~~bash
docker run --detach --rm --name jms-redelivery-demo \
  -p 61616:61616 -p 8161:8161 apache/artemis:latest-alpine
~~~

The default Artemis container image creates user/password `artemis` and accepts messages on port `61616`. Wait until broker startup finishes; the dashboard is normally at `http://localhost:8161`. Ensure no other broker occupies these ports. Test on an empty broker; never reuse production queues.

Project layout:

~~~text
redelivery-demo/
├── pom.xml
└── src/main/
    ├── java/example/RedeliveryDemoApplication.java
    └── resources/application.properties
~~~

### 8.2. `pom.xml`

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
  <artifactId>redelivery-demo</artifactId>
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

### 8.3. `application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

Use these sample credentials only on a local learning machine; production must fetch credentials from a secret manager and enable TLS and proper permissions.

### 8.4. `src/main/java/example/RedeliveryDemoApplication.java`

~~~java
package example;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class RedeliveryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedeliveryDemoApplication.class, args);
    }

    @Bean
    DefaultJmsListenerContainerFactory redeliveryFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    CommandLineRunner publishOneMessage(JmsTemplate jmsTemplate) {
        return args -> jmsTemplate.send("lesson.redelivery.demo", session -> {
            TextMessage message = session.createTextMessage("order-42");
            message.setStringProperty("eventId", "evt-42");
            message.setJMSCorrelationID("order-42");
            return message;
        });
    }
}

@Component
class RedeliveryListener {

    // DEMO ONLY: do not use an in-memory variable as
    // a deduplication / retry state mechanism in production.
    private final AtomicBoolean failOnce = new AtomicBoolean(true);

    @JmsListener(destination = "lesson.redelivery.demo",
                 containerFactory = "redeliveryFactory")
    public void onMessage(TextMessage message) throws JMSException {
        String eventId = message.getStringProperty("eventId");
        boolean redelivered = message.getJMSRedelivered();
        int count = message.getIntProperty("JMSXDeliveryCount");

        System.out.printf(
                "received eventId=%s redelivered=%b deliveryCount=%d%n",
                eventId, redelivered, count);

        // Broker/provider assigned ID. Read to correlate with broker logs:
        String jmsId = message.getJMSMessageID();
        if (jmsId == null) {
            throw new IllegalStateException("JMSMessageID absent");
        }

        // A single intentional failure in the running process.
        if (failOnce.compareAndSet(true, false)) {
            throw new IllegalStateException("Simulated first-attempt failure");
        }

        System.out.println("processed eventId=" + eventId);
        // Method succeeds -> container commits local JMS transaction.
    }
}
~~~

This is a **single Java file** containing one public class and one package-private component; the filename must match `RedeliveryDemoApplication.java`. Spring Boot auto-configures `JmsTemplate` and `ConnectionFactory` from the starter, while `redeliveryFactory` manages the listener session. Default Artemis brokers normally auto-create addresses/queues; if your organization disables auto-create, create `lesson.redelivery.demo` beforehand.

### 8.5. Run and Verify

~~~bash
mvn spring-boot:run
~~~

With an empty queue, a single demo instance running, a healthy broker, default policy permitting redelivery, and no stale messages, the **three lines printed by the demo code** are typically:

~~~text
received eventId=evt-42 redelivered=false deliveryCount=1
received eventId=evt-42 redelivered=true deliveryCount=2
processed eventId=evt-42
~~~

The console will also show Spring/Artemis startup logs and the stack trace from the intentional failure. This is the expected result under demo conditions; **do not claim the entire process stdout contains only those three lines**. If the broker applies a redelivery delay, the second line may appear later.

**Why did redelivery happen?**

1. `publishOneMessage` uses `JmsTemplate.send` to create a `TextMessage` with `eventId`/`JMSCorrelationID`.
2. The listener reads headers/properties upon arrival. `failOnce` flips from `true` to `false` and intentionally throws an exception on the first attempt.
3. `DefaultJmsListenerContainerFactory.setSessionTransacted(true)` makes the listener exception trigger a **JMS transaction rollback**, allowing the broker to redeliver the message.
4. On the next delivery, the provider attaches redelivery metadata; the method succeeds, prints `processed`, and the container commits.
5. A JVM restart between attempts resets `failOnce=true`; this example uses RAM solely for demonstration, **not** as production retry/idempotency.

Do not switch the example to default `AUTO_ACKNOWLEDGE` expecting exceptions to trigger redelivery automatically: Spring's `DefaultMessageListenerContainer` has different auto-ack semantics from a transacted listener.

Stop the application with `Ctrl+C`, then stop the broker:

~~~bash
docker stop jms-redelivery-demo
~~~

## 9. Build Idempotent Processing Instead of Relying on Both Flags

### 9.1. Common Failure Window

~~~text
Consumer receives M
    │
    ▼
DB write succeeds (DB COMMIT)
    │
    ▼
JVM crashes before JMS COMMIT
    │
    ▼
Broker redelivers M
    │
    ▼
Without dedup → writes DB / sends external call again!
~~~

A JMS session transaction and a database transaction **do not automatically form one distributed transaction**. Relying only on `JMSRedelivered` or the count cannot close this failure window.

### 9.2. Idempotency Key Pattern with a Database

Suppose the producer attaches a stable `eventId` and the application has a `processed_events(event_id)` table with a **unique constraint**. Inside the **same DB transaction** as the business update:

~~~sql
BEGIN;

INSERT INTO processed_events(event_id)
VALUES ('evt-42')
ON CONFLICT (event_id) DO NOTHING;

-- Only when INSERT actually inserts 1 row, execute the business update
-- inside this same DB transaction.
UPDATE orders
SET status = 'PROCESSED'
WHERE order_id = 'order-42';

COMMIT;
~~~

**Note on the SQL pattern:** `ON CONFLICT` is PostgreSQL syntax; the comments describe the program branch. Real application code must check the row count affected by INSERT: **if INSERT conflicted, skip the UPDATE**, whereas if INSERT succeeded, execute UPDATE within the **same DB transaction**. Table and status names here are illustrative; never blindly copy and run both SQL statements without the branching check.

When the same `eventId` arrives again, the consumer detects it was already processed and returns normally so JMS commits. If the DB transaction rolls back before succeeding, the dedup row also rolls back, allowing the next redelivery to process cleanly.

If the business effect calls a payment gateway or sends an email outside the DB, a DB unique constraint **does not automatically guarantee** once-only external effects. You need an idempotency token supported by the target service or consistent saga/outbox state.

### 9.3. Do Not Use `JMSMessageID` as the Sole Business Dedup Key

Message IDs normally suffice to recognize when a broker redelivers **the same JMS message**, yet a producer can publish a logical duplicate with a **new message ID**. Use a stable `eventId`/business key to protect business state, and store `JMSMessageID` alongside it for technical tracing. If a producer only sets `JMSCorrelationID`, verify whether that correlation ID is actually unique per event.

### 9.4. Decision Flow for a Listener

~~~text
Receive message
  │
  ├─ Log JMSMessageID, eventId, JMSRedelivered, JMSXDeliveryCount
  │
  ├─ Validate schema + business key
  │
  ├─ DB transaction:
  │    ├─ eventId already processed? ──► skip business effect
  │    └─ not yet processed ──────────► write dedup + business changes, commit DB
  │
  ├─ Listener completes → JMS commit
  │
  └─ If it fails before JMS commit:
       rollback JMS → redelivery per broker policy → safe retry
~~~

If a data error cannot be healed by retrying (bad schema, invalid ID, permanent authorization error), route to quarantine/DLQ under control rather than retrying endlessly.

## 10. Retries and DLQ: The Broker's Role

JMS defines how messages are received, acknowledged, and transacted; it **does not standardize** a universal API across all brokers to configure retry delays, exponential backoff, max attempts, dead-letter addresses, and replay UIs. For example, ActiveMQ Artemis provides **redelivery delay**, **max-delivery-attempts**, and **dead-letter-address** in address settings; other brokers use different names and mechanisms.

Questions to answer during design:

1. How many attempts? Does the limit include the first delivery or only redeliveries? Read your broker's exact policy semantics.
2. What delay/backoff? Is there jitter to avoid thundering herds or tight loops hammering the DB?
3. On permanent failure, where do messages go? Does the DLQ have retention, read access controls, alerts, failure reasons, and re-drive tooling?
4. When re-driving, are `eventId`/correlationId preserved? Are `JMSMessageID` and `JMSXDeliveryCount` altered/reset by the broker?
5. Is the consumer idempotent? If not, manual re-drives can re-execute business side effects.
6. When `JMSXDeliveryCount` grows abnormally high, are metrics/alerts firing while an independent broker policy terminates the retry loop?

**Do not build server-side retries by manually calling `send()` with a new message inside `catch` without understanding the consequences:** doing so can mint a new message ID, multiply logical copies, reset the count to 1, and erase the original redelivery trail.

### Practical Rules

- **Transient errors:** typically allow rollback and redelivery with delay/backoff.
- **Permanent/poison messages:** move to DLQ/quarantine, record error reason, support investigation and re-drive after fixes.
- **Side effect already happened:** rely on idempotency state; do not re-execute merely because the provider reported `count=2`.
- **Broker crash/failover:** observe multiple signals; accept that delivery counts may not be strictly exact.

## 11. Investigating Incidents from Real Logs

### Scenario A — Count climbs 1 → 2 → 3, error is always DB timeout

Likely cause: consumer is rolling back repeatedly due to a slow dependency. Inspect timeouts, connection pools, transactions, and broker redelivery delay; avoid tight retry storms. `JMSRedelivered=true` confirms broker redelivery state, yet cannot reveal the DB timeout cause without error logs/traces.

### Scenario B — Count=1 on both deliveries, yet `eventId` is identical

Likely cause: **two distinct JMS messages** carrying the same event. Compare `JMSMessageID`: if IDs differ, check upstream producer retries, outbox relays, or duplicate scheduler/HTTP triggers. If IDs match while metadata looks strange, inspect broker failover/bridges and client versions. Regardless of cause, idempotency must deduplicate by event ID.

### Scenario C — `redelivered=true`, `count=2`, yet no log of the first attempt

The broker may have delivered the message before the listener logged; the app crashed, an exception happened in the converter, logs were lost, or another consumer instance took it. Check broker consumer/connection events, instance IDs, startup/shutdown timestamps, and error logs. Never conclude for certain "it was processed once".

### Scenario D — Listener throws an exception, yet the message vanishes from the queue

Check whether the Spring listener container is running in **AUTO_ACK or transacted** mode, whether an exception was swallowed/caught and returned, or whether the broker already acked or moved the message to the DLQ. With Spring `DefaultMessageListenerContainer`'s default AUTO_ACK, exceptions do not automatically trigger redelivery.

### Scenario E — `count=7`, DLQ still hasn't received the message

Check broker configuration: `max-delivery-attempts` may be higher than 7, DLQ may not be configured, retries may still be in progress, or the message may be in a different queue. `JMSXDeliveryCount` is not a command forcing DLQ movement; DLQ is a broker policy.

### Scenario F — Identical payload, different message IDs

This may be a retry at the **publish layer** (two sends) rather than JMS redelivery. Distinguish using `eventId`, `JMSMessageID`, producer logs, and outbox records. Do not use `JMSRedelivered` to count duplicate upstream publishes.

## 12. Common Anti-Patterns

| Anti-pattern | Why is it dangerous? | Fix |
|---|---|---|
| `if (message.getJMSRedelivered()) return;` | Can drop a message whose first delivery was never processed. | Use a durable idempotency store. |
| `if (count >= 3) acknowledge();` | Ack may mark completion even though business logic failed; count is not strictly reliable. | Broker retry/DLQ policies and classified error handling. |
| `getBooleanProperty("JMSRedelivered")` | Confuses a standard header with a property. | Use `getJMSRedelivered()`. |
| `getJMSXDeliveryCount()` | JMS `Message` has no such dedicated getter. | Use `getIntProperty("JMSXDeliveryCount")`. |
| Assuming `count=1` guarantees no prior side effect | Producer may have sent a duplicate new event. | Use event IDs / unique constraints. |
| Re-sending a copy in every `catch` block | Creates new messages, changes IDs/resets counters, multiplies duplicates. | Roll back transaction so broker redelivers. |
| Logging only payload and stack trace | Cannot correlate attempts; risks leaking sensitive data. | Log structured IDs, count, flag, consumer instance, and outcome. |
| Creating selector `JMSXDeliveryCount > 3` | Selector behavior on provider-on-receive properties is undefined. | Read count on receive; configure broker max attempts. |
| Catching exceptions and always returning success | Listener container may commit, losing redelivery opportunity. | Swallow errors only after safely handling/quarantining. |
| Using in-RAM `AtomicBoolean` for production dedup | State is lost on restart or across scaled instances. | Durable DB dedup transactions or idempotency service. |

## 13. Checklist for Spring JMS Production

- **Receiving messages:** use raw `jakarta.jms.Message` or mapped headers when tracing is needed; always verify `jakarta.jms` compatibility with your Spring Boot/Framework version.
- **Message identity:** producers generate durable `eventId`s and attach correlation IDs if workflows require them; brokers assign `JMSMessageID`.
- **Receive metadata:** log `JMSRedelivered` and `JMSXDeliveryCount` alongside `messageId`, `eventId`, destination, consumer instance, timestamp, and trace ID.
- **Transactions:** clearly define listener container `sessionTransacted`, acknowledgment mode, and DB transaction manager. Test failures before and after DB commit.
- **Idempotency:** sufficiently scoped unique keys (`tenant + eventId` in multi-tenant systems) and business updates in the same DB transaction where possible.
- **Policies:** enable sensible retry delay/backoff, max attempts, DLQ, retention, and alerts; ensure re-drive procedures do not recreate duplicate effects.
- **Observability:** measure received counts, redelivery rates, failures/rollbacks, DLQ depth, processing latency, and consumer lag; do not rely solely on the counter.
- **Drills:** test first-attempt failures, broker restarts, consumer crashes, and producer double-sends to see how the flag, count, `messageId`, and `eventId` differ.

## 14. Self-Check Questions

**1. Does `JMSRedelivered=true` prove the business handler ran previously?** No. The provider may have delivered the message and the consumer crashed before code ran.

**2. Where is `JMSXDeliveryCount=2` read from?** From `Message.getIntProperty("JMSXDeliveryCount")` on the received message, not a setter or dedicated JMS header getter.

**3. Is `JMSXDeliveryCount` mandatory in Jakarta Messaging 3.x?** Yes. Since JMS 2.0 providers must attach this `int` property on receive. However, the spec does not guarantee exact counts after every failure.

**4. Is `JMSRedelivered=true` with `count=1` compliant?** It violates Jakarta Messaging section 3.5.11, since a `true` flag requires a count of 2 or higher. Inspect the provider/client/bridge.

**5. If a producer sends two different JMS messages sharing the same `eventId`, can both have `count=1`?** Yes. That is a logical event/producer-level duplicate, not necessarily broker redelivery.

**6. With Spring `DefaultMessageListenerContainer` on default AUTO_ACK, does a listener throwing an exception guarantee the broker redelivers?** No. The container may ack before invoking the listener. Use a transacted session/appropriate transaction manager for rollback/redelivery.

**7. Why shouldn't you use selector `JMSXDeliveryCount > 5`?** Because this property is set by the provider on receive; the JMS specification states selector behavior on provider-on-receive properties is undefined.

**8. Does `count=3` mean a payment was charged three times?** No. It indicates broker delivery attempts, not how many times business effects committed successfully.

**9. How do you investigate the same payload being received twice?** Cross-check `JMSMessageID`, `eventId`, `JMSRedelivered`, delivery count, producer logs, consumer instance, transaction outcomes, and broker events.

**10. What mechanism protects business results even when DB commits and then JMS rolls back?** Durable idempotency keys, unique constraints/transactions for DB side effects; for external side effects, add target-side idempotency/transactional outbox/sagas as appropriate.

## 15. Official References

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `3.4.7 JMSRedelivered`, `3.5.9 Jakarta Messaging-defined properties`, `3.5.11 JMSXDeliveryCount`, `6.2.10 Message acknowledgement`, `6.2.11 Duplicate delivery of messages`. Authoritative reference for the semantics and limits of both signals.
- [Jakarta Messaging 3.1 API: Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): header and property getters, `acknowledge()`, `JMSMessageID`/`JMSCorrelationID`.
- [Spring Framework: Annotation-driven listener endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): raw `jakarta.jms.Message`, listener parameters, and mapped headers.
- [Spring Framework: Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener containers and JMS transactions/rollback.
- [Spring Framework: Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate` and listener/transaction configuration rules.
- [Spring Boot: JMS and ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): `spring-boot-starter-artemis` and `spring.artemis.*`.
- [Apache Artemis: Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): official broker container used in the example.
- [Apache Artemis: Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): redelivery, dead-letter, and per-broker queue/address settings.

**Key takeaway:** `JMSRedelivered` provides a **boolean signal**; `JMSXDeliveryCount` provides a provider-reported **delivery attempt estimate**. To pinpoint *the exact source of duplicates and prevent repeated business side effects*, store a **stable `eventId`/business key**, observe **`messageId`, `correlationId`, attempt/outcome**, and coordinate **transactions, idempotency, retries, and DLQs**.
