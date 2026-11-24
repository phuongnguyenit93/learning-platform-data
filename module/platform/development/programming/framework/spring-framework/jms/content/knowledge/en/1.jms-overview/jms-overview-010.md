# Foundations and Learning Order: From Message to Reliability in JMS

**Scope:** The JMS big picture in Spring Framework. This lesson builds a mental model and learning roadmap from the very first message to the question "has it been processed safely?". Broker-specific settings must be verified against the documentation of the broker in use.

## 1. Starting from the Problem: Why Do We Need Messages?

In a synchronous HTTP call, the caller normally waits for the receiver to finish or return an error. With messaging, a sender (**producer**) sends a **message** to a **destination** managed by the messaging system; a receiver (**consumer**) can process it at another time. Producer and consumer do not need to run at the same time or know each other's network address directly. This helps decouple processing timing, absorb traffic spikes, and distribute tasks across multiple processes.

~~~text
Order application (producer)
    → JMS API / Spring JMS library
    → JMS provider / broker
    → Queue or Topic (destination)
    → Consumer / @JmsListener
    → Validate data → business logic → record result
~~~

Example: after recording an order, the system emits an "order created" message so another service can prepare shipping. **Successfully sending a message does not mean shipping work is done.** Distinguish at least three milestones: (1) sender requests a send; (2) broker accepts/stores or routes the message per configuration; (3) consumer processes and confirms success.

**JMS** is the familiar name of Java Message Service; the modern API is standardized under **Jakarta Messaging** (the `jakarta.jms` package in Jakarta Messaging 3.x). JMS is an **API/programming contract**, not a specific broker. Apache ActiveMQ Artemis, IBM MQ, and compatible products supply implementations/providers. **Spring JMS** adds a support layer to send, receive, convert payloads, and manage listeners. Do not equate Spring JMS, the JMS standard, and broker-specific mechanics.

## 2. Master a Message Before Talking About Reliability

A JMS message has three important parts:

| Part | Content | Examples / Usage |
| --- | --- | --- |
| **Standard headers** | Fields defined by JMS, some set by the provider | `JMSMessageID`, `JMSDestination`, `JMSTimestamp`, `JMSDeliveryMode`, `JMSExpiration`, `JMSRedelivered` |
| **Properties** | Key–value metadata used for filtering/routing | `eventType=OrderCreated`, `tenantId`; `JMSXDeliveryCount` is a JMS-defined property |
| **Body** | Business payload | JSON text in `TextMessage`, bytes in `BytesMessage`, etc. |

An event contract might use a JSON body:

~~~json
{
  "eventId": "evt-1001",
  "type": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "O-42",
  "occurredAt": "2026-10-30T01:00:00Z"
}
~~~

`eventId` is a **business identifier** managed by the application to recognize repeated events; `JMSMessageID` is a JMS-layer message identifier assigned by the provider per API rules. Do not substitute one ID for the other arbitrarily. `JMSCorrelationID` is commonly used to pair requests–replies or processing chains; `JMSReplyTo` can point to a reply destination. `JMSRedelivered` indicates the message may be a redelivery, while `JMSXDeliveryCount` is typically 1 on the first delivery and 2+ on redeliveries. Do not rely solely on them for business idempotency.

Common body types include `TextMessage`, `BytesMessage`, `MapMessage`, `StreamMessage`, and `ObjectMessage`. When exchanging across applications, prefer formats with explicit schemas and language independence (such as JSON or Avro) along with versioning rules. Be cautious with `ObjectMessage` because deserializing Java objects from untrusted sources carries security risks and classpath coupling.

**A message contract must answer:** who emits, who consumes, event type name, schema/version, identifier key, required fields, behavior on missing fields, sensitive data, TTL, and duplicate-handling capability. JMS message selectors filter on **headers/properties**, not by querying JSON fields inside the body.

## 3. Distinguish Queue and Topic by Asking "Who Receives a Copy?"

| Criterion | Queue – point-to-point | Topic – publish/subscribe |
| --- | --- | --- |
| Purpose | Divide work among consumers on the same queue | Distribute events to multiple independent subscriptions |
| When multiple consumers exist | One message is delivered to **one** consumer in the competing group, excluding redeliveries | Each eligible subscription receives a copy of the message; multiple consumers can serve one shared subscription |
| When a consumer is temporarily offline | Messages can wait in the queue if unexpired and the broker can retain them | Non-durable subscriptions typically miss events while offline; durable subscriptions retain unread messages under configured conditions |
| Example | Processing an invoice-generation task | Notifying inventory, shipping, and analytics of an order |

Do not infer "topics always store every event indefinitely": **subscriptions** (non-durable/durable/shared), delivery mode, TTL, resource limits, and broker policies determine what data is retained. With a queue, two consumers do not mean both receive every message. With a topic, two independent subscriptions can receive two separate copies of the same event.

**Choose by business intent:** "one unit processes this task" usually points to a queue; "multiple independent systems need to know about this event" usually points to a topic. If each system needs its own backlog, design corresponding subscriptions or queues rather than expecting a shared queue to duplicate messages automatically.

## 4. Matching API and Spring Pieces

- **`ConnectionFactory`** creates connections/contexts to the provider; endpoint address, authentication, TLS, and pooling/caching configuration typically go with it.
- **`Connection` / `Session` / `JMSContext`** represent connections and working contexts. Classic `Session` manages send/receive, acknowledgment, and local transactions; do not share a single session across multiple threads arbitrarily. `JMSContext` is the simplified API in Jakarta Messaging.
- **`Destination`** represents a queue or topic; the destination name alone does not fully determine broker administration policies.
- **`MessageProducer` / `MessageConsumer`** are low-level APIs for sending/receiving. Receiving can be synchronous (blocking via `receive`) or asynchronous via listeners.
- **Spring's `JmsTemplate`** simplifies resource creation, conversion, and send/receive. **`@JmsListener`** binds a consumer to an application method; Spring's listener container manages lifecycle, connections, consumer count, and error handling.
- **`MessageConverter`** defines how Java objects convert to JMS messages and vice versa; both sides must agree on body type, content type, and schema.

A basic processing chain: producer calls `JmsTemplate.convertAndSend(...)` → broker accepts message → listener container receives from destination → Spring converts payload into `@JmsListener` parameter → business code runs → container executes ack/commit or rollback per configuration. **That final step** connects "receiving a message" to "reliable processing".

## 5. Reliability Is Not an On/Off Switch

To judge whether a system is "reliable", examine each layer and failure scenario:

| Mechanism | Helps With | Does Not Guarantee by Itself |
| --- | --- | --- |
| `PERSISTENT` delivery | Asks provider to use more durable storage to survive provider failures | Consumer succeeded; message did not expire TTL or get evicted by resource limits |
| Queue / durable topic subscription | Retains unconsumed messages within storage policy limits | Zero message loss across all errors/operations; exactly-once processing |
| Acknowledgment (ack) | Tells provider a delivery has been confirmed | DB side effects committed at the exact same moment |
| Local JMS transaction | Groups reception and JMS operations in the same session into commit/rollback | Automatically joining non-JMS database commits |
| Redelivery/retry | Provides a chance to reprocess after failure | No duplicate processing; no queue clogging from poison messages |
| DLQ / quarantine | Isolates repeatedly failing messages for investigation | Automatically fixing bad data or recovering business state |
| Idempotency | Reprocessing the same event preserves the desired business outcome | Broker stops sending duplicates; external actions are inherently idempotent |

**Delivery mode differs from acknowledgment.** `PERSISTENT`/`NON_PERSISTENT` relates to how the provider protects messages against failures. Ack/transactions relate to whether consumption has been recorded. TTL sets a useful lifespan: a message can expire even after a successful send. Priority, selectors, multiple consumers, and redelivery can also affect delivery order.

### Ack Modes to Understand Before Configuring

- `AUTO_ACKNOWLEDGE`: provider/container acknowledges automatically per the receive lifecycle. With **Spring's `DefaultMessageListenerContainer`**, this default mode can acknowledge **before the listener executes**, so an exception in the listener does not guarantee redelivery; do not leave it as an unconscious default for critical tasks.
- `CLIENT_ACKNOWLEDGE`: consumer explicitly acknowledges per JMS session semantics; Spring's container can manage ack on behalf of the listener method. Session-level ack behavior should be studied before calling the API manually.
- `DUPS_OK_ACKNOWLEDGE`: allows delayed acks and potential redeliveries; not an "exactly-once guarantee" mechanism.
- **Transacted session** (`sessionTransacted=true`): listener success commits JMS; failure rolls back JMS and the message can be redelivered per provider policy. This is a reasonable starting point when reliability is needed with Spring listeners.

**Conditions on guarantees:** returning messages, retry counts, delay/backoff, DLQ, persistence, and failover partly depend on the broker and configuration. Never document "JMS retries 3 times by default" or "every exception is always redelivered": those are not universal rules.

### Three Common Interpretation Levels

- **At-most-once:** prioritizes avoiding redelivery; some scenarios may lose processing.
- **At-least-once:** allows redelivery when completion is uncertain; the application must handle duplicates.
- **Exactly-once business effect:** business outcome is applied only once even though messages may be redelivered. This is an **end-to-end** goal, usually requiring transactions/idempotency in business data (and sometimes outbox/inbox, or a purpose-built distributed transaction protocol), not inferred from a single JMS setting.

## 6. Spring JMS Example: From Message to a Listener with a Local Transaction

The example below uses **Java 17+**, **Spring Boot 3.x / Spring Framework 6.x**, the `jakarta.jms` package, and a configured JMS provider (such as Artemis). In a Spring Boot project you need dependencies supporting Spring JMS and a compatible provider, e.g., `org.springframework.boot:spring-boot-starter-artemis`, plus a reachable broker. This is application source code, **not a standalone `javac` program**; file path: `src/main/java/com/example/jmsdemo/MessagingDemoApplication.java`.

~~~java
package com.example.jmsdemo;

import java.util.UUID;
import jakarta.jms.ConnectionFactory;
import org.springframework.boot.ApplicationRunner;
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
public class MessagingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessagingDemoApplication.class, args);
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    ApplicationRunner sendExample(JmsTemplate jmsTemplate) {
        return args -> {
            String eventId = UUID.randomUUID().toString();
            String json = """
                    {"eventId":"%s","type":"OrderCreated","orderId":"O-42"}
                    """.formatted(eventId).strip();
            jmsTemplate.convertAndSend("orders.created", json);
        };
    }
}

@Component
class OrderListener {
    @JmsListener(destination = "orders.created")
    public void handle(String json) {
        System.out.println("Received: " + json);
        // In a real app: validate schema and perform idempotent business processing.
    }
}
~~~

**Read in order:**

1. `ConnectionFactory` is the connection config provided by Spring Boot/the provider; the example assumes it is already working. With Boot 3 and native Artemis, settings such as `spring.artemis.mode=native`, `spring.artemis.broker-url`, and credentials must match the real broker.
2. `JmsTemplate.convertAndSend` with a default `String` uses an appropriate converter to create a JMS text message sent to queue `orders.created` in the example. `ApplicationRunner` emits only **one sample on application startup**, and does not represent production event publishing tied to an order-placement transaction.
3. `@JmsListener` receives the body as a `String`. The factory bean named `jmsListenerContainerFactory` is picked up by the listener infrastructure; `setSessionTransacted(true)` causes the JMS receive to commit when the method exits normally and roll back on error.
4. With the broker ready and the message delivered, you may see a line like `Received: {"eventId":"...","type":"OrderCreated","orderId":"O-42"}`. When this line appears is **non-deterministic** because the listener runs asynchronously; if the broker is disconnected, no successful receive outcome can be claimed.

**Controlled failure test:** make the listener throw `IllegalStateException` before finishing, observe rollback/redelivery and actual retry policy, then restore the listener. If it throws every single time, it is a **poison message**: retry limits and a DLQ per broker documentation are needed to avoid infinite loops. Do not interpret "printed once" as proof of exactly-once across process restarts, multiple consumers, or network errors.

## 7. When JMS Succeeds Yet Business State Still Breaks

Consider this chronological sequence:

~~~text
Consumer receives M → updates DB → DB commits successfully
                 → app crashes before JMS commit/ack
                 → broker redelivers M → consumer receives M a second time
~~~

A local JMS transaction rolls back **JMS**, while the DB already committed independently. The redelivery can deduct money, add stock, or send an email a second time if logic does not prevent duplicates. Common approach:

1. Each event has a stable `eventId`; define an **idempotency key** by business function and consumer, e.g., the pair (`consumerName`, `eventId`).
2. Within the **same DB transaction** as the business mutation, insert the key into a processed-events table with a **unique constraint**. Execute side effects only when the key is newly inserted. When the event arrives again, recognize it as already processed and exit normally so JMS can commit.
3. For side effects in external systems (email/payment/API), use an idempotency key supported by the target system or a recoverable state workflow; a unique constraint in your own DB cannot undo a completed external request.
4. For the **DB transaction → publish JMS** direction, consider a **transactional outbox**: write the event to an outbox table in the same transaction as business data, then have a separate publisher send to the broker and update status. The publisher may send duplicates on retry, so consumers still need idempotency.
5. Coordinate distributed transactions (XA/JTA) only when truly required and after understanding cost, provider compatibility, and operational limits; do not treat it as Spring JMS's default setup.

**Outcomes must be proven at the business data layer**, not merely by counting listener invocations.

## 8. Recommended Learning Order: Each Layer Answers One Question

| Step | Question to Answer | Small Exercise / Evidence to Observe |
| --- | --- | --- |
| **1. Message contract** | What event or command are we transmitting? | Write a payload with `eventId`, type, version, entity key; state owner/schema and validation rules |
| **2. Queue vs Topic** | Who needs to receive a copy? | Send one message to a queue with two consumers, contrast with two independent topic subscriptions |
| **3. JMS API** | Who creates connections, sessions, producers, consumers? | Trace the path from `ConnectionFactory` to destination, noting resource ownership |
| **4. Spring JMS** | Where does Spring remove boilerplate? | Use `JmsTemplate` and `@JmsListener`, verify converters, destinations, and receive logs |
| **5. Headers/selector/correlation** | How do we route and trace? | Set custom properties, test property selectors, inspect `JMSCorrelationID` |
| **6. Ack + transaction** | When a listener fails, where does the message go? | Enable `sessionTransacted=true`, throw an exception, observe commit/rollback/redelivery |
| **7. Persistence + lifetime** | What if the broker or subscriber stops? | Compare `PERSISTENT`/`NON_PERSISTENT`, TTL, queues, and durable topics under controlled conditions |
| **8. Retry + DLQ** | When a message keeps failing, how does the system handle it? | Configure retry/backoff/max attempts per broker, inspect DLQ and safe replay |
| **9. Idempotency + DB consistency** | Can a side effect complete twice? | Crash the process after DB commit, redeliver the event, and prove the DB changes only once |
| **10. Observability + operations** | How do we know the system is actually healthy? | Monitor queue depth, oldest message age, consumer lag, redeliveries/DLQ, latency, and alerts |

Do not jump into DLQs before understanding ack/rollback, and do not claim "exactly once" before testing a **crash after DB commit**. From step 6 onward, write a hypothesis before each experiment ("rollback will allow the broker to redeliver"), measure, and record results by **provider/version/config**; retry behavior and storage limits are not identical across all brokers.

## 9. Failure Experiments You Must Run

| Failure Injection Point | Outcomes to Verify | Control Strategy |
| --- | --- | --- |
| Producer fails to send due to broker disconnect | Did send fail? Did app retry? Was the same event sent multiple times? | Bounded retries, outbox when DB consistency is required, deduplication key |
| Broker restarts after accepting a message | Does the message survive under current delivery mode/TTL/resources? | Persistence, storage/HA config, and broker-specific recovery testing |
| Consumer throws exception before JMS commit | Does it roll back and redeliver? How do `JMSRedelivered`/`JMSXDeliveryCount` change? | Transacted listener, retry policy, and classified error handling |
| Consumer dies after DB commit but before JMS commit | DB changed; was the message redelivered and did side effects duplicate? | Idempotency with a unique constraint in the same DB transaction |
| Message fails data validation on every attempt | Does it block the queue or loop infinitely? | DLQ/quarantine, log root cause, fix payload/handler, and controlled replay |
| Topic subscriber offline | Upon returning, does it receive events sent while absent? | Right subscription type, matching policy/TTL |
| Multiple consumers and burst traffic | Does processing order shift? | Avoid assuming global FIFO; design keys/ordering, limit concurrency, or use provider-supported grouping |

**Minimum observability:** log `eventId`, `JMSMessageID`, `JMSCorrelationID` when present, destination, delivery attempt, processing status, and errors; do not indiscriminately log credentials or sensitive payloads. Also measure **queue depth**, **oldest-message age**, throughput, connection errors, rollback/redelivery counts, DLQ size, and **end-to-end latency**, because "consumer is running" alone does not prove backlog is draining properly.

## 10. Common Misconceptions

1. **"JMS is a broker."** JMS is an API; concrete persistence, retries, DLQ, HA, grouping, and admin tools are determined by the provider.
2. **"Send succeeded means business succeeded."** Send, broker acceptance, consumer ack, and DB commit are distinct milestones.
3. **"Queues send every message to every consumer."** Multiple consumers on the same queue normally compete; for multiple independent copies, design topics/subscriptions or separate flows.
4. **"Topics come with an infinite backlog."** Non-durable subscribers can miss messages; durable subscriptions are still subject to expiry, resources, and broker policies.
5. **"Persistent means never lost."** TTL, misconfiguration, resource limits, and administrative actions can prevent delivery.
6. **"Exceptions in `@JmsListener` retry by default."** You cannot ignore listener container and acknowledgment semantics; with `DefaultMessageListenerContainer`, default `AUTO_ACKNOWLEDGE` does not satisfy redelivery guarantees when handlers fail.
7. **"A JMS transaction automatically commits alongside the DB."** Local JMS transactions and DB transactions are separate scopes; consistency and idempotency must be designed.
8. **"JMS guarantees business-level exactly-once."** Provider delivery semantics do not cover side effects outside the broker; replay can trigger business logic a second time.
9. **"Adding consumers still preserves strict ordering."** Concurrency, priorities, selectors, retries, and multiple subscriptions alter observed order; define required ordering by business key.
10. **"DLQ is a dumping ground to forget errors."** It needs an owner, alerts, diagnostic context, retention policies, and a replay procedure that avoids re-triggering side effects.

## 11. Self-Check Before Moving to Advanced Lessons

- Can describe the path producer → broker/destination → consumer → ack/commit, clearly naming who owns each step.
- Can choose queue vs. topic from distribution requirements, explaining competing consumers and durable subscriptions.
- Can distinguish headers, properties, and body; knows why `eventId` is needed alongside `JMSMessageID`.
- Can explain the effects of `AUTO_ACKNOWLEDGE`, `sessionTransacted`, redelivery, persistence, and TTL without conflating them.
- Can prove via a failure experiment that a DB side effect still executes only once when JMS delivers duplicates.
- Can describe the retry → DLQ → observe → fix → replay loop; identifies broker-dependent parts instead of making assumptions.

**Learning destination:** moving from "received a message" to "we know what happens during send, processing, acknowledgment, retry, or crash", backed by evidence at both the broker **and** business state.

## Reference Sources

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): message model, headers, queues/topics, acknowledgment, and delivery semantics.
- [Spring Framework – Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, listener containers, and factories.
- [Spring Framework – Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): asynchronous receiving and transactional processing.
- [Spring Guide – Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): send/receive examples and Spring Boot integration.

Consult the documentation of **the specific broker and version in deployment** before deciding retry counts, redelivery schedules, DLQ, persistent storage, HA, and resource-exhaustion policies.