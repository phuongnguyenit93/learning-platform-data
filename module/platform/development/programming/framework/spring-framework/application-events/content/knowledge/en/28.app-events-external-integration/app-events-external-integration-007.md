# Correlation Between Internal Events and Messages in Spring Framework

## 1. Goal and problem

A Spring application can use `ApplicationEventPublisher.publishEvent(...)` to notify business occurrences inside the same JVM. When the system needs to integrate with other services, a listener or outbound adapter can turn that event into a message sent via Kafka, RabbitMQ, JMS, HTTP, an outbox, or another transport. On the receiving side, a message can produce a **new internal event** so local components continue reacting.

If you transmit only the payload without correlation information, a journey breaks apart:

~~~text
HTTP checkout
   |
   +-- Spring internal event: OrderPlaced
          |
          +-- outbound message: order.placed
                    |
                    +-- consumer receives message
                            |
                            +-- Spring internal event: OrderImported
                                      |
                                      +-- update projection / notify user
~~~

When investigating failures or tracing a multi-step workflow, the question is not just “what ID does this message have?” but also:

- Which business event did it originate from?
- Which events/messages belong to the **same workflow**?
- Which actor or event **directly caused** the current work?
- Is this a resend from a retry, or a **new business event**?
- Where is the trace recorded, and does context survive thread or service hops?
- Did a listener receive a duplicate message, or just see the same correlation ID?
- Which IDs must survive across brokers, restarts, replays, DLQs, and schema upgrades?

This lesson guides **correlation between internal events and messages** under a clear contract, with a Java 17+ example using Spring Framework, Spring Messaging, and JUnit 5. It distinguishes business correlation from distributed tracing, outlines the limits of `@EventListener`, and shows how to upgrade to a transactional outbox/inbox when delivery guarantees are required.

**Key principle:** Event ID identifies a single event; correlation ID groups steps of the same workflow; causation ID points to the direct cause; message ID identifies an envelope/transport message. Never use a single field to substitute for all four roles.

## 2. Three layers to separate: event, message, and trace

### 2.1. Spring Application Event

Spring accepts plain business objects or subclasses of `ApplicationEvent`:

~~~java
publisher.publishEvent(new OrderPlaced(
        "evt-1001", "corr-9", "cmd-15", "ORD-101"));
~~~

This snippet is illustrative only; the record and publisher bean must be defined.

An `@EventListener` can receive that event directly within the same JVM. With the default multicaster, standard listeners run synchronously; with `@Async` or an executor, execution can differ. The `ApplicationEventPublisher` contract treats publishing as a **handoff** to the multicaster, without inherently guaranteeing processing completion or durable storage.

### 2.2. Integration message

A message sent across external systems has at least:

- **Payload**: data agreed upon with consumers, usually serialized.
- **Metadata/headers**: message type, schema version, identifiers, tracing context, content type, and tenant scope if permitted.
- **Transport semantics**: topic/queue/routing key, offset, ack, retry, redelivery, partition, and durability depending on infrastructure.

`org.springframework.messaging.Message<T>` is a useful abstraction for describing payloads and headers. It does not by itself turn a simple Spring Context program into a Kafka producer.

### 2.3. Distributed trace

Tracing has its own model: trace ID, span ID, and trace context, such as W3C `traceparent`/`tracestate`. Traces help observe operations spanning multiple services. Traces may be sampled, truncated at trust boundaries, or retained for a shorter period than business data.

Therefore, a **business correlation ID must not be equated with a trace ID**. A workflow lasting days or resuming after a DLQ replay may still need the same correlation ID even though the original trace ended long ago.

## 3. Four identifiers and their meanings

| Field | Question it answers | Preserved across retries? | Changes when creating a new business step? |
| --- | --- | --- | --- |
| `eventId` | “Which logical business event?” | Yes: keep unchanged if resending the same event | Yes: a new event needs a new ID |
| `messageId` | “Which envelope/message send attempt or logical outbox message?” | Depends on transport/outbox design; do not use to infer event identity | Usually yes |
| `correlationId` | “Do these steps belong to the same workflow?” | Yes within the same workflow | Usually preserved; changes when starting a new workflow |
| `causationId` | “What directly led to this event/message?” | Preserved for the same event | Usually set to the ID of the immediate parent step |

These are **application-recommended conventions**, not four built-in headers that Spring Framework automatically generates for you.

### 3.1. Event ID: stable for one logical event

For example, `evt-order-100` represents one occurrence of “OrderPlaced”. If the producer retries sending the same event because no ACK arrived, **do not generate a new event ID**. Consumers can use `(producerSource, eventId, consumerId)` as part of a deduplication key.

If “PaymentCaptured” happens later, that is a different business event and must receive a new event ID, even though it remains part of the same checkout workflow.

### 3.2. Message ID: depends on the envelope contract

One event can be fanned out into two messages sent to two different destinations. Each message has its own ID or offset/record identity. One message may retry with the same logical outbox ID while the broker assigns a new transport record ID or offset.

Spring Messaging provides `MessageHeaders.ID` (a UUID) and `MessageHeaders.TIMESTAMP`, but header IDs can change whenever a new message instance is constructed. It **must not be assumed to be a stable idempotency key across adapters, serialization, brokers, and replays**.

In our example, we define an explicit application header `message_id` for illustration. Production should agree on whether it corresponds to a **logical outbox row/message ID** or a **single transport delivery attempt ID**. Stick strictly to the defined semantics and avoid assuming all brokers share the same message ID standard.

### 3.3. Correlation ID: follows the workflow

Example checkout workflow with `corr-checkout-09`:

~~~text
Command checkout        correlation=corr-checkout-09
OrderPlaced event        correlation=corr-checkout-09
order.placed message     correlation=corr-checkout-09
OrderImported event      correlation=corr-checkout-09
PaymentRequested event   correlation=corr-checkout-09
payment.requested msg    correlation=corr-checkout-09
~~~

The correlation ID lets you find all steps belonging to one flow. It **does not prove** the order in which steps happened or which step directly caused another; that is the causation ID’s job.

Messages carrying the same correlation ID are **not duplicates** merely because they share a correlation. A single checkout can produce dozens of distinct events with the same correlation ID.

### 3.4. Causation ID: points to the immediate cause

If `OrderPlaced(evt-100)` emits `order.placed` and the consumer creates `OrderImported(evt-200)`, the convention can be:

~~~text
evt-100:
    correlationId = corr-9
    causationId   = cmd-15

message order.placed:
    event_id       = evt-100
    correlation_id = corr-9
    causation_id   = cmd-15

evt-200 (new event created by consumer):
    correlationId = corr-9
    causationId   = evt-100
~~~

Here `evt-200` is a **new** event, so it gets a new event ID, while its causation ID shows it was created because of `evt-100`. If you are **only forwarding the exact same event** without creating a new business fact, keep the old `eventId`; never assign a new ID merely because of a retry.

If a system has both commands and events, causation may reference a command ID or an event ID. To avoid namespace collisions, you can also store `causationType`/`causationSource` if the contract requires it.

## 4. Example parent–child diagram across application boundaries

~~~text
Service A / checkout
  |
  | commandId = cmd-001
  v
OrderPlaced(eventId=evt-101)
  correlationId = corr-900
  causationId   = cmd-001
  |
  | Outbound bridge
  v
Message(messageId=msg-301)
  event_id       = evt-101
  correlation_id = corr-900
  causation_id   = cmd-001
  |
  | Broker / transport
  v
Service B / inbound adapter
  |
  | publish NEW internal event
  v
OrderImported(eventId=evt-501)
  correlationId = corr-900
  causationId   = evt-101
  sourceMessage = msg-301
  |
  v
Projector / audit / notification
~~~

The IDs are fabricated data for illustration. The diagram shows **correlation logic only** and does not claim there is a real broker in the Gradle example below.

The crux: **preserve correlation, update causation to the immediate parent, and mint a new ID whenever a new event is created**. Separating `messageId` and `eventId` distinguishes multiple send attempts from a single logical event.

### 4.1. Example of multiple messages from the same event

If one event is published to `billing.events` and `analytics.events`:

~~~text
evt-101
   +--> msg-billing-1  (event_id=evt-101)
   +--> msg-analytics-1 (event_id=evt-101)
~~~

Two distinct messages, yet the same source event. Do not use `messageId` as a business deduplication key across all destinations when the business actually wants idempotency by `eventId + consumerId`.

### 4.2. Replay example

If `msg-billing-1` fails and is resent, the new transport message may have a different ID/offset, yet **`event_id=evt-101`** must remain stable for the same event. A consumer with an idempotency store avoids charging twice just because of a redelivery.

If an operator fixes data and genuinely emits a new compensating business action, that is a distinct event (new ID) with its own causation/compensation link.

## 5. Metadata placement: headers or payload?

There are two common places to put correlation:

- **Headers:** easy to integrate with tracing, middleware, routing, logs, and adapters; the broker must support forwarding/normalizing them.
- **Payload/envelope:** explicit in the event contract and outbox JSON, surviving even if a transport strips headers.

An example contract:

~~~json
{
  "eventId": "evt-101",
  "correlationId": "corr-900",
  "causationId": "cmd-001",
  "eventType": "order.placed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T01:00:00Z",
  "data": {
    "orderId": "ORD-101",
    "amountCents": 4200
  }
}
~~~

This is an **example JSON envelope**, not a format mandated by Spring. You can put metadata in broker headers and keep the business payload separate. Choose a consistent source of truth: if the same field appears in both headers and body, define which one is authoritative and how conflicts are handled.

Practical recommendation:

1. Internal events carry the minimal required metadata in an immutable record or an `EventContext`.
2. Bridges read metadata **from the event itself**, rather than hoping every `ThreadLocal` is still intact.
3. Outboxes persist metadata + serialized payload in the same business transaction.
4. Transport adapters map metadata to headers per naming/encoding contracts.
5. Inbound adapters validate schema, headers, provenance, and permissions, then create the corresponding internal event.

**You do not have to emit every field onto every topic.** Carry only what satisfies the contract, data classification, and actual transport header size limits.

## 6. Header conventions for the example

This lesson uses the following application headers:

| Header | Logical type | Rule |
| --- | --- | --- |
| `event_id` | String | Source logical event identifier |
| `message_id` | String | Illustrative envelope ID; production defines explicit lifecycle |
| `correlation_id` | String | Preserved within the same workflow |
| `causation_id` | String | Cause of the source event |
| `event_type` | String | E.g., `order.placed` |
| `schema_version` | Integer | Version of data understood by consumers |

These are not universal headers mandated by Spring Kafka or RabbitMQ. When using Kafka, header values are usually represented as `byte[]`, and consumers must agree on encoding (UTF-8, binary, or an appropriate serializer). In Spring Messaging, `MessageHeaders` can hold Java objects. **The two worlds do not map 1:1 automatically.**

When a message arrives:

- `event_id` and `correlation_id` are required under this contract.
- Check `event_type` and `schema_version` to choose the decoder/handler.
- Validate type, length, charset, and values; do not blindly trust externally supplied headers.
- Causation ID is derived from the source logical event when creating a **new internal event**.
- Message ID is kept as supporting metadata for transport investigation; never use it in place of event ID.

If a legacy system lacks a correlation ID, define a fallback policy: generate a new correlation ID at the **boundary** and note that upstream context was missing, or route the message to quarantine/invalid-message handling. **Never silently assign `event_id` as `correlation_id`** and pretend it is the original business chain.

## 7. Runnable example: Spring event → message → new Spring event

The following example uses **Java 17+, Spring Framework 6.2.15, and Spring Messaging**. A Spring event `OrderPlaced` is turned by an outbound bridge into a `Message<OrderPlacedPayload>` with metadata. A `RecordingTransport` holds the message in memory to simulate crossing out of the process. Then an inbound adapter receives the message and creates a **new `OrderImported` event** with correlation preserved and causation pointing to the source event.

**Explicit limitations:** `RecordingTransport` is not a broker, does not serialize JSON, and has no network, transactions, durability, ACKs, redeliveries, or partitions. It clarifies the **mapping contract** with a runnable program free of Kafka/RabbitMQ dependencies. Production outboxes, consumers, and retries are designed in later sections.

### 7.1. Project structure

~~~text
event-message-correlation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── CorrelationBridgeDemo.java
    └── test/
        └── java/
            └── demo/
                └── CorrelationBridgeDemoTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'event-message-correlation-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
    implementation 'org.springframework:spring-messaging:6.2.15'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.CorrelationBridgeDemo'
}

test {
    useJUnitPlatform()
}
~~~

`spring-context` provides the event publisher/listener; `spring-messaging` provides `Message`, `MessageHeaders`, and `MessageBuilder`. JUnit 5 runs integration-style tests against a real Spring context. When using Spring Boot, let Boot’s BOM manage compatible Spring dependencies.

### 7.2. Complete Java file

Save to `src/main/java/demo/CorrelationBridgeDemo.java`:

~~~java
package demo;

import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class CorrelationBridgeDemo {

    public static final class Headers {
        public static final String EVENT_ID = "event_id";
        public static final String MESSAGE_ID = "message_id";
        public static final String CORRELATION_ID = "correlation_id";
        public static final String CAUSATION_ID = "causation_id";
        public static final String EVENT_TYPE = "event_type";
        public static final String SCHEMA_VERSION = "schema_version";

        private Headers() {}
    }

    public record OrderPlaced(
            String eventId,
            String correlationId,
            String causationId,
            String orderId,
            long amountCents,
            Instant occurredAt) {}

    public record OrderPlacedPayload(
            String orderId,
            long amountCents,
            String occurredAt) {}

    public record OrderImported(
            String eventId,
            String correlationId,
            String causationId,
            String orderId,
            String sourceMessageId) {}

    public interface OutboundTransport {
        void send(Message<OrderPlacedPayload> message);
    }

    // Simulates crossing outside the JVM only; NOT a real broker.
    public static final class RecordingTransport
            implements OutboundTransport {

        private final CopyOnWriteArrayList<Message<OrderPlacedPayload>>
                messages = new CopyOnWriteArrayList<>();

        @Override
        public void send(Message<OrderPlacedPayload> message) {
            messages.add(message);
        }

        public Message<OrderPlacedPayload> last() {
            if (messages.isEmpty()) {
                throw new IllegalStateException("No message sent");
            }
            return messages.get(messages.size() - 1);
        }

        public int count() {
            return messages.size();
        }
    }

    // Outbound mapping: internal event -> message envelope.
    public static final class OutboundOrderBridge {
        private final OutboundTransport transport;
        private final AtomicInteger messageCounter = new AtomicInteger();

        public OutboundOrderBridge(OutboundTransport transport) {
            this.transport = transport;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            String messageId = String.format(
                    Locale.ROOT, "msg-%04d",
                    messageCounter.incrementAndGet());

            Message<OrderPlacedPayload> message =
                    MessageBuilder.withPayload(new OrderPlacedPayload(
                            event.orderId(),
                            event.amountCents(),
                            event.occurredAt().toString()))
                    .setHeader(Headers.EVENT_ID, event.eventId())
                    .setHeader(Headers.MESSAGE_ID, messageId)
                    .setHeader(Headers.CORRELATION_ID, event.correlationId())
                    .setHeader(Headers.CAUSATION_ID, event.causationId())
                    .setHeader(Headers.EVENT_TYPE, "order.placed")
                    .setHeader(Headers.SCHEMA_VERSION, 1)
                    .build();

            transport.send(message);
        }
    }

    // Inbound mapping: incoming message -> NEW internal event.
    public static final class InboundOrderBridge {
        private final ApplicationEventPublisher publisher;
        private final AtomicInteger eventCounter = new AtomicInteger();

        public InboundOrderBridge(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void accept(Message<OrderPlacedPayload> message) {
            String sourceEventId =
                    requiredHeader(message, Headers.EVENT_ID);
            String correlationId =
                    requiredHeader(message, Headers.CORRELATION_ID);
            String sourceMessageId =
                    requiredHeader(message, Headers.MESSAGE_ID);
            String eventType =
                    requiredHeader(message, Headers.EVENT_TYPE);

            if (!"order.placed".equals(eventType)) {
                throw new IllegalArgumentException(
                        "Unsupported event type");
            }

            Object version =
                    message.getHeaders().get(Headers.SCHEMA_VERSION);
            if (!(version instanceof Integer schemaVersion)
                    || schemaVersion != 1) {
                throw new IllegalArgumentException(
                        "Unsupported schema version");
            }

            String childEventId = String.format(
                    Locale.ROOT, "evt-consumer-%04d",
                    eventCounter.incrementAndGet());

            // correlation PRESERVED, causation = source event.
            publisher.publishEvent(new OrderImported(
                    childEventId,
                    correlationId,
                    sourceEventId,
                    message.getPayload().orderId(),
                    sourceMessageId));
        }

        private static String requiredHeader(
                Message<?> message, String name) {
            Object value = message.getHeaders().get(name);
            if (!(value instanceof String text)
                    || text.isBlank()
                    || text.length() > 128) {
                throw new IllegalArgumentException(
                        "Missing or invalid header: " + name);
            }
            return text;
        }
    }

    // Observer receives only the NEW event created on the consumer side.
    public static final class ImportedObserver {
        private final CopyOnWriteArrayList<OrderImported> received =
                new CopyOnWriteArrayList<>();

        @EventListener
        public void onImported(OrderImported event) {
            received.add(event);
        }

        public OrderImported last() {
            if (received.isEmpty()) {
                throw new IllegalStateException("No imported event");
            }
            return received.get(received.size() - 1);
        }

        public int count() {
            return received.size();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public RecordingTransport transport() {
            return new RecordingTransport();
        }

        @Bean
        public OutboundOrderBridge outboundOrderBridge(
                RecordingTransport transport) {
            return new OutboundOrderBridge(transport);
        }

        @Bean
        public InboundOrderBridge inboundOrderBridge(
                ApplicationEventPublisher publisher) {
            return new InboundOrderBridge(publisher);
        }

        @Bean
        public ImportedObserver importedObserver() {
            return new ImportedObserver();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            RecordingTransport transport =
                    context.getBean(RecordingTransport.class);
            InboundOrderBridge inbound =
                    context.getBean(InboundOrderBridge.class);
            ImportedObserver observer =
                    context.getBean(ImportedObserver.class);

            OrderPlaced source = new OrderPlaced(
                    "evt-producer-0001",
                    "corr-checkout-09",
                    "cmd-checkout-01",
                    "ORD-100",
                    4200L,
                    Instant.parse("2026-11-11T01:00:00Z"));

            context.publishEvent(source);
            Message<OrderPlacedPayload> wire = transport.last();

            // Simulate consumer receiving the message from transport.
            inbound.accept(wire);
            OrderImported received = observer.last();

            System.out.println("producer.event=" + source.eventId());
            System.out.println("message.id=" +
                    wire.getHeaders().get(Headers.MESSAGE_ID));
            System.out.println("message.event.id=" +
                    wire.getHeaders().get(Headers.EVENT_ID));
            System.out.println("message.correlation=" +
                    wire.getHeaders().get(Headers.CORRELATION_ID));
            System.out.println("message.causation=" +
                    wire.getHeaders().get(Headers.CAUSATION_ID));
            System.out.println("consumer.event.id=" + received.eventId());
            System.out.println("consumer.correlation=" +
                    received.correlationId());
            System.out.println("consumer.causation=" +
                    received.causationId());
            System.out.println("consumer.source.message=" +
                    received.sourceMessageId());
            System.out.println("transport.count=" + transport.count());
        }
    }
}
~~~

### 7.3. Running and expected stdout

Run from the `event-message-correlation-demo` directory with JDK 17+ and Gradle:

~~~bash
gradle -q run
~~~

If using the Gradle Wrapper, run `./gradlew -q run` (Linux/macOS) or `gradlew.bat -q run` (Windows).

Lines **explicitly printed by the program** in order:

~~~text
producer.event=evt-producer-0001
message.id=msg-0001
message.event.id=evt-producer-0001
message.correlation=corr-checkout-09
message.causation=cmd-checkout-01
consumer.event.id=evt-consumer-0001
consumer.correlation=corr-checkout-09
consumer.causation=evt-producer-0001
consumer.source.message=msg-0001
transport.count=1
~~~

In this example, IDs are deterministic and counters start at 0 so expected stdout can be verified by eye. When using random IDs in production, **do not expect specific ID strings**; assert relationships between IDs, uniqueness, and preservation of correlation. Gradle/logging may emit additional lines.

**Look at the relationships:** `evt-consumer-0001` is a new event, `causationId=evt-producer-0001`, and `correlationId=corr-checkout-09` is preserved. `msg-0001` is an illustrative message identifier; it does not replace the event ID.

### 7.4. Why does the demo not use a broker?

The goal is to test a **mapping contract** that is easy to understand and run on any machine with JDK/Gradle. `RecordingTransport` is a fake transport with no Kafka/RabbitMQ server, serializer, topic, partition, ACK, or durable storage. Keeping the same `Message<T>` in memory also cannot catch type-mapping errors over the network.

When switching to a real transport, integration tests are required to verify serialization, header encoding, schema evolution, retries, redelivery, and consumer idempotency. This clean mapping code can serve as the adapter core, but `transport.send(...)` succeeding on a fake must never be equated with “the message reached service B”.

### 7.5. Points to upgrade in production

- `AtomicInteger` ID generation is for demo use only. Production uses UUID/ULID/ID generators with clear contracts and uniqueness controls.
- `event_id` must remain stable across retries of a logical event, never regenerated on each resend.
- `message_id` in the demo increments on each bridge call; production attaches a stable logical outbox message ID across retries if defined per outbox record.
- `InboundOrderBridge` checks headers but lacks authentication, replay protection, or an idempotent inbox; all must be added at the boundary.
- `RecordingTransport` performs no serialization and does not prove JSON/Avro/Protobuf compatibility.
- Do not log raw PII/secrets. Use approved business IDs per system policy and authorized correlation logs.
- Do not emit the new inbound event twice if the consumer already processed the same delivery; durable deduplication must share the transaction of the side effect.

## 8. JUnit 5: testing bidirectional correlation contracts

Create `src/test/java/demo/CorrelationBridgeDemoTest.java`:

~~~java
package demo;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CorrelationBridgeDemoTest {

    private static CorrelationBridgeDemo.OrderPlaced sampleEvent() {
        return new CorrelationBridgeDemo.OrderPlaced(
                "evt-1", "corr-1", "cmd-1", "ORD-1",
                250L, Instant.parse("2026-11-11T01:00:00Z"));
    }

    @Test
    void outboundPreservesEventAndBusinessCorrelation() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             CorrelationBridgeDemo.Config.class)) {

            var transport = context.getBean(
                    CorrelationBridgeDemo.RecordingTransport.class);

            context.publishEvent(sampleEvent());

            Message<CorrelationBridgeDemo.OrderPlacedPayload> message =
                    transport.last();

            assertEquals("evt-1", message.getHeaders().get(
                    CorrelationBridgeDemo.Headers.EVENT_ID));
            assertEquals("corr-1", message.getHeaders().get(
                    CorrelationBridgeDemo.Headers.CORRELATION_ID));
            assertEquals("cmd-1", message.getHeaders().get(
                    CorrelationBridgeDemo.Headers.CAUSATION_ID));
            assertEquals("msg-0001", message.getHeaders().get(
                    CorrelationBridgeDemo.Headers.MESSAGE_ID));
            assertEquals("order.placed", message.getHeaders().get(
                    CorrelationBridgeDemo.Headers.EVENT_TYPE));
            assertEquals(1, message.getHeaders().get(
                    CorrelationBridgeDemo.Headers.SCHEMA_VERSION));
            assertEquals("ORD-1", message.getPayload().orderId());
            assertEquals(250L, message.getPayload().amountCents());
            assertEquals(1, transport.count());
        }
    }

    @Test
    void inboundCreatesNewEventWithSameCorrelationAndParentCausation() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             CorrelationBridgeDemo.Config.class)) {

            var transport = context.getBean(
                    CorrelationBridgeDemo.RecordingTransport.class);
            var inbound = context.getBean(
                    CorrelationBridgeDemo.InboundOrderBridge.class);
            var observer = context.getBean(
                    CorrelationBridgeDemo.ImportedObserver.class);

            context.publishEvent(sampleEvent());
            inbound.accept(transport.last());

            var imported = observer.last();

            assertEquals("evt-consumer-0001", imported.eventId());
            assertNotEquals("evt-1", imported.eventId());
            assertEquals("corr-1", imported.correlationId());
            assertEquals("evt-1", imported.causationId());
            assertEquals("msg-0001", imported.sourceMessageId());
            assertEquals("ORD-1", imported.orderId());
            assertEquals(1, observer.count());
        }
    }

    @Test
    void missingCorrelationHeaderIsRejectedBeforeNewInternalEvent() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             CorrelationBridgeDemo.Config.class)) {

            var inbound = context.getBean(
                    CorrelationBridgeDemo.InboundOrderBridge.class);
            var observer = context.getBean(
                    CorrelationBridgeDemo.ImportedObserver.class);

            var payload = new CorrelationBridgeDemo.OrderPlacedPayload(
                    "ORD-1", 250L, "2026-11-11T01:00:00Z");

            var message = MessageBuilder.withPayload(payload)
                    .setHeader(CorrelationBridgeDemo.Headers.EVENT_ID,
                            "evt-1")
                    .setHeader(CorrelationBridgeDemo.Headers.MESSAGE_ID,
                            "msg-1")
                    .setHeader(CorrelationBridgeDemo.Headers.EVENT_TYPE,
                            "order.placed")
                    .setHeader(CorrelationBridgeDemo.Headers.SCHEMA_VERSION,
                            1)
                    .build();

            var error = assertThrows(
                    IllegalArgumentException.class,
                    () -> inbound.accept(message));

            assertTrue(error.getMessage().contains("correlation_id"));
            assertEquals(0, observer.count());
        }
    }

    @Test
    void wrongSchemaVersionIsRejectedBeforePublishing() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             CorrelationBridgeDemo.Config.class)) {

            var transport = context.getBean(
                    CorrelationBridgeDemo.RecordingTransport.class);
            var inbound = context.getBean(
                    CorrelationBridgeDemo.InboundOrderBridge.class);
            var observer = context.getBean(
                    CorrelationBridgeDemo.ImportedObserver.class);

            context.publishEvent(sampleEvent());

            var wrongVersion = MessageBuilder
                    .fromMessage(transport.last())
                    .setHeader(CorrelationBridgeDemo.Headers.SCHEMA_VERSION, 99)
                    .build();

            assertThrows(IllegalArgumentException.class,
                    () -> inbound.accept(wrongVersion));
            assertEquals(0, observer.count());
        }
    }
}
~~~

Run:

~~~bash
gradle test
~~~

The four tests serve distinct goals:

1. Outbound bridge preserves event ID, correlation ID, causation ID, and transforms payload accurately.
2. Inbound bridge creates a **new** event; preserves correlation ID while pointing causation to the source event.
3. Missing required correlation header → no new event published.
4. Unsupported schema version → rejected before processing.

The test suite uses a real Spring context and `@EventListener`. It needs no broker to test mapping, though it **does not yet test** serialization, networking, retries, exactly-once, or durable delivery. These are expectations when running Gradle, not execution results observed in this task.

## 9. Correlation and distributed tracing: related but not identical

**Business correlation** tracks the logic of a workflow. **Distributed tracing** tracks the relationships among instrumented operations/spans, typically for investigating latency or errors.

Comparison table:

| Question | Business correlation | Trace context |
| --- | --- | --- |
| What does it identify? | A business workflow or saga | An execution trace/span |
| Lifetime | Hours/days depending on workflow | Milliseconds/seconds, subject to sampling/retention |
| On retry after DLQ | Usually keeps original correlation | May open a new trace and link to the old trace |
| When adding a business step | Correlation usually stays, causation changes | New span, parent/link per tracing |
| Storage | Event/outbox/message metadata, permitted audit logs | Telemetry backend, context propagation |
| Can serve as idempotency key? | No | No |
| Contains PII by default? | Should not | Should not |

W3C Trace Context defines `traceparent` and `tracestate` (especially for HTTP context propagation). For messaging, propagation depends on client/broker instrumentation and semantic conventions; never assume every adapter copies every header identically.

An illustrative `traceparent`:

~~~text
traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
~~~

This value represents a trace ID, parent span ID, and flags in W3C format. It is **not a business correlation ID**, and you should never set `correlationId = traceparent`. One workflow can span multiple distinct traces when events wait in an outbox or are replayed the next day.

If using Micrometer Tracing / OpenTelemetry, use standard propagators/instrumentation to inject/extract trace context. Do not hand-craft `traceparent` strings from correlation IDs or reuse a fixed span ID across steps, as that creates corrupted trace graphs.

### 9.1. Context propagation across async

`ThreadLocal` MDC, `SecurityContext`, and the publisher thread’s current trace span do not appear automatically on every worker thread. Events must carry business correlation **as explicit data**, or pass it via an immutable `EventContext`.

With `ThreadPoolTaskExecutor`, `ContextPropagatingTaskDecorator`/Micrometer Context Propagation can propagate observable context if configured properly; however, it does not turn a `ThreadLocal` JDBC transaction into a live valid transaction on another worker thread.

### 9.2. Baggage and data limits

Never put emails, tokens, ID numbers, or full payloads into tracing baggage for debugging convenience. Baggage can be forwarded to other services and exported to telemetry backends. Correlation IDs can also link personal activity, so they require appropriate data classification, retention, and access controls.

## 10. Designing an outbound bridge in Spring

An outbound listener should act as an **adapter**, rather than mixing transport schemas into domain events:

~~~text
Domain service
    |
    +--> publish DomainEvent(...)
             |
             +--> @EventListener OutboundBridge
                       |
                       +--> map event -> IntegrationMessage
                       +--> choose destination
                       +--> send via producer adapter
~~~

Advantages:

- Domain events stay unaware of Kafka topics, RabbitMQ exchanges, or header encodings.
- The bridge can version the public integration schema without forcing all internal listeners to change.
- Mapping can be tested independently of brokers, as in the section 8 test suite.
- Security/PII decisions are enforced at the outbound boundary.
- There is a single centralized place to attach correlation, causation, and validation.

### 10.1. Do not serialize raw JPA entities

Avoid:

~~~java
publisher.publishEvent(new OrderPlacedJpa(orderEntity));
~~~

and then sending the whole entity to Kafka. It can carry lazy associations, PII, proxies, or huge object graphs, and change schemas unintentionally. Use small, immutable records/DTOs with explicit versions.

### 10.2. Do not pull correlation solely from MDC

If the bridge runs after commit, on another executor, or in a retry worker, MDC may be empty or hold an unrelated request context. For business data that must stay stable, put the correlation ID directly inside the **event/outbox record**.

If you want to log correlation, an interceptor can copy a validated value from the event into MDC **within a `try/finally` scope** and clear it right after processing. Never leave global `ThreadLocal` values lingering across a thread pool, as context can leak between tasks.

### 10.3. Rules when emitting a new event

If an adapter only **translates the representation** of an existing event (domain event → integration message for the same business fact), preserve `eventId` and `correlationId`. If a consumer performs a new action and emits a new event, mint a new `eventId` and set `causationId` to the event that triggered it.

A retry worker resending an outbox record **must not create a new domain event** just to get a fresh ID; doing so breaks idempotency/deduplication.

## 11. Inbound adapter: validate before publishing an event

An inbound consumer must treat broker messages as **input crossing a trust boundary**:

~~~text
Transport listener / consumer
   |
   +--> authenticate provenance / ACL / tenant if applicable
   +--> validate headers and schema version
   +--> deserialize into versioned DTO
   +--> check duplicate / idempotency
   +--> execute business logic in transaction
   +--> publish NEW internal event with preserved correlation
   +--> ACK only when work is durably complete
~~~

Exact execution order and transaction/ack semantics depend on the broker/framework, but these logical steps are valuable for design reviews.

### 11.1. Validation

Do not merely check that a header exists; check:

- Valid data types after decoding.
- Length bounds to prevent header injection or log amplification.
- Event ID and correlation ID formats per contract.
- `eventType` and `schemaVersion` supported by the consumer.
- Source/tenant authorized to send that message type.
- Business payload within size bounds and free of disallowed fields.
- Timestamp/TTL/retention if required by business rules.
- Trace context may be spoofed; never elevate it into authorization data.

The section 7 example rejects empty correlation and unsupported schemas. That is **basic** validation, not a complete production security suite.

### 11.2. New event vs. republishing the same message

If the consumer creates a new state `OrderImported`, the new event has:

~~~text
newEventId = generateUniqueId()
correlationId = incoming.correlationId
causationId = incoming.eventId
~~~

If a consumer merely forwards the same message/event to another queue without creating a new business fact, clarify whether semantics are forward, retry, or transformation; normally preserve logical event identity and do not fabricate a new causation chain.

### 11.3. Do not blindly trust client-supplied correlation

If an external client sets `correlationId` itself, it could pollute logs or correlate across users. At trust boundaries, validate and optionally generate an internal ID per policy. Never use `correlationId` as an access token; authorization must verify the real principal, tenant, and resources.

## 12. Outbox: ensuring events and messages are not dropped in the commit window

A real risk:

~~~text
Business transaction commits successfully
       |
       +-- JVM crashes before @TransactionalEventListener(AFTER_COMMIT)
           manages to call the producer
       |
       +-- No message sent and no durable work item exists
~~~

`@TransactionalEventListener(AFTER_COMMIT)` helps choose post-commit timing, but **does not guarantee the message gets sent** if the JVM dies. Nor can an outbound listener calling Kafka roll back an already-committed business change if the broker later fails.

For critical messages, use a **transactional outbox**:

~~~text
BEGIN TRANSACTION
   INSERT/UPDATE business table
   INSERT outbox row {
       outboxId,
       eventId,
       correlationId,
       causationId,
       type,
       schemaVersion,
       payload
   }
COMMIT

Outbox worker:
   claim row
   encode headers/payload
   send to broker
   await producer acknowledgement as configured
   mark delivered or schedule retry
~~~

Business state and the outbox row commit **in the same database transaction**. On rollback, neither exists. If the worker crashes after the broker accepts the message but before the outbox row is marked delivered, the message may be sent again—so consumer design still requires idempotency.

### 12.1. Illustrative SQL schema

~~~sql
CREATE TABLE outbox_message (
    outbox_id        UUID PRIMARY KEY,
    producer_source  VARCHAR(128) NOT NULL,
    event_id         VARCHAR(128) NOT NULL,
    correlation_id   VARCHAR(128) NOT NULL,
    causation_id     VARCHAR(128),
    event_type       VARCHAR(128) NOT NULL,
    schema_version   INTEGER NOT NULL,
    payload_json     TEXT NOT NULL,
    created_at       TIMESTAMP NOT NULL,
    status           VARCHAR(24) NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (producer_source, event_id, event_type)
);
~~~

This is a **reference** schema; uniqueness on those exact three columns is not mandatory if one valid event emits multiple messages of the same type to multiple destinations. When fanning out, add `destination` or a dedicated logical message ID to the key. In principle, the unique key should represent the **unit of outbound work**, without blocking legitimate messages.

A real outbox implementation must define statuses, leases, retry/backoff, concurrency, and retention. Avoid holding DB locks across network sends by separating claiming from confirmation; design crash recovery for expired `PROCESSING` rows.

### 12.2. Metadata fields must be persisted before sending

Do not store only the payload and let the worker generate a new correlation ID at send time; on retry, correlation would change. `eventId`, `correlationId`, `causationId`, and schema version should be stored with the outbox record and remain stable across resends per contract.

**Critical distinction:** An outbox increases the durability of creating send work; it does not automatically provide end-to-end exactly-once. Without consumer-side idempotency, side effects can still duplicate.

## 13. Inbox and idempotency for consumers

Message brokers and outbox workers typically have **at-least-once** semantics when retries are configured; consumers must tolerate duplicates.

Do not use `correlationId` as a deduplication key: one workflow has many events with the same correlation. Do not use transport offset as a business deduplication key if the same event can be resent with a new offset.

An inbox table:

~~~sql
CREATE TABLE consumed_event (
    consumer_name  VARCHAR(128) NOT NULL,
    producer_source VARCHAR(128) NOT NULL,
    event_id       VARCHAR(128) NOT NULL,
    processed_at   TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, producer_source, event_id)
);
~~~

Typical workflow:

~~~text
receive message(event_id=evt-101)
   |
   +--> transaction
          |
          +--> insert inbox key (consumer, source, evt-101)
          |       |
          |       +-- conflict already processed -> skip side effect
          |
          +--> mutate business state / write audit / outbox
          |
          +--> commit
   |
   +--> ACK source according to broker contract
~~~

Atomicity is required: if the inbox insert succeeds yet the side effect rolls back, the inbox insert must also roll back, otherwise redelivery skips lost work. If the side effect is HTTP/email outside the database transaction, you need downstream idempotency keys or reconciliation; a database transaction **cannot atomically commit** external systems.

If using Kafka, JMS, or RabbitMQ, ack/retry/rebalance semantics differ. Never conclude processing succeeded solely because the consumer callback was invoked. Testing a crash between the side effect and the ACK is what proves retry design does not cause business errors.

### 13.1. New message and old event

Some outbox workers may generate a **new `messageId` on each physical send**. The consumer still deduplicates by logical `eventId`, never mistaking those message IDs for distinct business events. If one business event has independent handlers, the key may need `handlerId`/`consumerGroup` so each handler runs once within its own scope.

### 13.2. TTL and replay

When inbox retention expires and an old message is replayed, the unique key is no longer there to block duplicates. Choose retention based on replay windows, SLAs, and business risk; for financial operations, you may need domain-layer invariants/idempotency beyond inbox TTL.

## 14. Distinguishing correlation, ordering, and causality

A correlation ID **does not** cause the broker to automatically preserve message order. Two messages with the same correlation may traverse different topics/partitions, undergo retries, or run concurrently in consumers.

A causation ID helps express **relationships**, but does not guarantee parent events were processed before child events in every service. When ordering is required:

- Pick an appropriate partition/routing key, such as `aggregateId`.
- Verify the actual ordering guarantees of the transport.
- Use `aggregateVersion` or a sequence number when the domain needs to detect out-of-order arrivals.
- Design consumers to tolerate duplicate, delayed, missing, or reordered deliveries.
- Do not rely on `occurredAt` for total order across machines when clock skew can happen.

Example:

~~~text
OrderCreated:       eventId=evt-1, correlation=corr-1, version=1
OrderAddressChanged eventId=evt-2, correlation=corr-1, version=2

Consumer receives evt-2 before evt-1:
   matching correlation does not solve ordering
   must use version/ordering policy
~~~

If side effects must be recorded in strict order for an aggregate, that belongs to state-machine/consumer design, not merely adding a correlation ID header.

## 15. CloudEvents and differences from custom headers

CloudEvents is an event format specification with attributes such as `id`, `source`, `type`, `specversion`, `time`, and `data`, depending on binding/format. When using CloudEvents:

- `id` identifies the event within `source` per specification.
- `source + id` is a useful pair for identifying a source occurrence.
- `type` describes the event type.
- `specversion` is the version of the **CloudEvents specification**, not the business payload schema version.
- Business correlation/causation are typically expressed via agreed extension attributes, which are not built into every system automatically.

Conceptual example:

~~~json
{
  "specversion": "1.0",
  "source": "/orders-service",
  "id": "evt-101",
  "type": "com.example.order.placed",
  "time": "2026-11-11T01:00:00Z",
  "correlationid": "corr-900",
  "causationid": "cmd-001",
  "data": {
    "orderId": "ORD-101",
    "amountCents": 4200
  }
}
~~~

`correlationid` and `causationid` here are **illustrative extension names from an application contract**. Do not claim they are core CloudEvents attributes. If a project adopts CloudEvents, follow the transport’s exact serialization/binding rather than inventing `ce-id` and custom headers by guesswork.

CloudEvents does not provide queues, retries, or transactions on its own. It standardizes event representation, not broker/delivery architecture.

## 16. Metrics, logging, and tracing the journey

An observability system may need to locate:

~~~text
correlation=corr-900
  producer: evt-101 -> msg-301
  broker: topic=orders, partition=2, offset=724
  consumer: msg-301 -> evt-501
  handler: evt-501 -> database projection updated
~~~

This is illustrative data. In production, specify clearly which teams/systems can query these IDs and their retention period.

### 16.1. Structured logs

A useful log may include **permitted** fields:

~~~json
{
  "stage": "outbound.send",
  "eventType": "order.placed",
  "eventId": "evt-101",
  "correlationId": "corr-900",
  "messageId": "msg-301",
  "result": "acknowledged"
}
~~~

Do not include full payloads, emails, access tokens, or customer addresses in logs unless necessary. IDs can also be linkable data and require access controls and retention; never treat them as public by default.

### 16.2. Metrics tags

Never put `eventId`, `messageId`, `correlationId`, or `traceId` in Micrometer `Counter`/`Timer` tags. High-cardinality values explode time-series counts and can expose linkable info. Tags should use bounded sets such as `event_type`, `handler`, `destination`, `outcome`, and `error_kind`.

An illustrative counter:

~~~java
registry.counter(
        "event.bridge.messages",
        "event_type", "order.placed",
        "outcome", "published").increment();
~~~

This illustrative snippet requires Micrometer `MeterRegistry` and a `registry` bean; it is not in the section 7 Gradle demo.

### 16.3. Traces

Use OpenTelemetry/Micrometer Tracing to instrument producers/consumers and propagate W3C context in headers with an appropriate propagator. Never replace span IDs with business correlation IDs. When replaying hours later, open a new trace and **link** the earlier event/trace context if sampling/retention allows.

If the broker drops or the consumer fails to extract trace context, the trace breaks even though the correlation ID remains in the message. Therefore test two things separately: **business correlation correctness** and **trace propagation correctness**.

## 17. Data safety and trust boundaries

Correlation IDs can link a series of actions to the same person/order. They must be designed per data classification—not derived predictably from emails or phone numbers and assumed safe.

Data checklist:

- Use random/opaque identifiers for correlation where appropriate; never use PII as IDs.
- Validate header sizes, encoding, and characters to prevent injection/DoS.
- Do not log full message payloads containing tokens/PII.
- Never emit raw `HttpServletRequest`, `SecurityContext`, or full JPA entities into events.
- Never treat an external `tenant_id` header as sufficient authorization proof.
- Never use correlation IDs to authorize or prove identity.
- Never put user IDs or correlation IDs into high-cardinality metric tags.
- Enforce retention/deletion policies for logs, outboxes, DLQs, and inboxes.
- Quarantine malformed or suspected spoofed messages.
- Distinguish **business source identity** from trace sources and broker delivery metadata.

If a partner sends messages with self-generated correlation IDs, a gateway can replace them with internal IDs or maintain a mapping so a partner cannot spoof another tenant’s correlation. What matters is **origin authority**, not a well-formed ID string.

## 18. Common failure modes and how to diagnose them

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Event has correlation, message does not | Outbound bridge omitted header mapping | Test event→message mapping |
| Message has correlation, inbound event loses it | Consumer took payload only, dropped headers | Extract, validate, attach to new context/event |
| Correlation changes on every retry | Generated new ID inside send attempt | Persist correlation when creating event/outbox |
| `eventId` changes on retry of same event | Retry treats each send as a new event | Keep stable logical event ID |
| Deduplication fails | Keyed by message ID/offset instead of event identity | Key by `source+eventId+consumer` |
| Consumer skips all events in a workflow | Deduplicated by `correlationId` | Correlation is not an event ID |
| Inbound event lacks cause | Did not set causation ID from upstream event ID | Create new event with causation pointing to parent |
| Trace breaks across async | Missing context propagation | Use propagator/context propagation, test separately |
| Trace exists but business correlation disappears | Relied on sampled trace ID as business ID | Persist correlation in event/outbox |
| Duplicate side effects after crash | ACK and side effect are not atomic | Inbox/idempotency/reconciliation |
| Has `AFTER_COMMIT` yet messages still get lost | Crash before producer send or ACK | Transactional outbox |
| Wrong message order | Multiple partitions or retries | Aggregate version/partition key |
| Header type changes arriving in Kafka | Inconsistent codec/byte encoding | Contract for header serialization |
| `schemaVersion` missing | Producer/consumer contract mismatch | Validation + schema migration |
| Too many metric series | Correlation ID placed in metric tag | Low-cardinality tags |
| Client-supplied header abused | Trusted input without checking source/tenant | AuthN/AuthZ by origin and tenant |
| Same event sent to two destinations blocked | Outbox unique key too narrow | Add destination/logical message ID |
| Consumer sees new event yet replay duplicates | Missing durable inbox state | Idempotency + proper transaction |
| Inconsistent causation using message ID | Mixed transport attempt with domain trigger | Use upstream event ID as logical cause |
| CloudEvents `specversion` confused with business schema | Mixed event envelope standard with payload schema | Separate field for data schema version |

## 19. Integration tests needed with a real broker

The Java test suite in section 8 tests **mapping logic**; production requires testing the real boundary layer.

1. **Serialization:** record/JSON/Avro/Protobuf round-trips through codecs with exact types; verify ISO timestamps, minor currency units, and versions.
2. **Header encoding:** `event_id`, `correlation_id`, and `causation_id` survive the broker unchanged; string/binary encodings align.
3. **Schema compatibility:** consumer version N handles N-1 if required by contract, and rejects unsupported versions.
4. **Retry/redelivery:** one logical event retains a stable event ID across retries; physical message metadata may vary.
5. **At-least-once:** deliver duplicates twice; side effect applies only once per idempotency key.
6. **Crash windows:** kill workers after business commit before send, and after broker ACK before outbox ACK.
7. **Inbox atomicity:** dedup marker insert and business update commit/roll back together.
8. **Out-of-order:** consumer receives version 2 before version 1 and handles per policy.
9. **Tracing:** producer/consumer spans and context propagation work with real instrumentation.
10. **Security:** spoofed headers and cross-tenant correlation are rejected; no PII leaks into logs/DLQs.
11. **DLQ replay:** replaying old messages preserves valid correlation and causation without creating semantically wrong new events.
12. **Backpressure:** full queues, rejected tasks, metrics, and retry states remain accurate.

You can use Testcontainers with a broker, embedded brokers, or fake adapters depending on your system. Fake transports are great for mapping unit tests, but **do not replace** protocol-level integration tests.

## 20. Hands-on exercises

**Exercise 1 — Multiple messages for one event.** Replace a single `OutboundTransport` with two transports: billing and analytics. Use the same event ID, correlation ID, and causation ID, but distinct message IDs/destinations. Explain how the outbox unique key must change.

**Exercise 2 — Duplicates and inbox.** Publish two messages with the same `event_id` but different message IDs. Implement a `consumed_event` table with unique key `consumer_name + producer_source + event_id` and verify the side effect executes once. Test marker rollback when the side effect fails.

**Exercise 3 — Missing correlation.** Send a message missing the correlation header to the inbound adapter. Compare two policies: reject/quarantine vs. generating a new correlation ID flagged as missing upstream context. Why can silently reusing `event_id` as correlation cause confusion?

**Exercise 4 — Causation chain.** After `OrderImported`, emit `InventoryReserved` as a new event. Mint a new ID, keep correlation, and set causation to `OrderImported`’s ID. Draw the timeline.

**Exercise 5 — Outbox.** Write a business row and an outbox row in the same JDBC transaction; trigger a rollback and verify no outbox row exists. After commit, a worker sends the message using the stored metadata without minting a new correlation.

**Exercise 6 — Trace.** Create producer and consumer spans with Micrometer Tracing/OpenTelemetry. Propagate W3C `traceparent` per binding while keeping business correlation independent. Trigger a delayed retry and observe two trace sessions.

**Exercise 7 — Broker contract.** Replace `RecordingTransport` with an appropriate Kafka/RabbitMQ or Spring Cloud Stream adapter, and write integration tests for header encoding/string versions and retries. Never assume Spring `MessageHeaders.ID` is preserved across every transport.

**Exercise 8 — Privacy.** Remove all event/message IDs from metric labels, keeping them in structured logs with proper retention and permissions. Test a message containing a fake email and verify serializers/logging do not leak it outside policy.

## 21. Pre-production checklist

- [ ] Every domain event has a stable `eventId` preserved across retries.
- [ ] A `correlationId` exists for multi-step workflows, carried across events/messages/outboxes.
- [ ] New events generate a new `eventId` and set `causationId` to the appropriate parent step.
- [ ] Message ID has a clear definition: logical outbox message vs. transport attempt/record.
- [ ] `MessageHeaders.ID` is never implicitly substituted for stable business event identity.
- [ ] Outbound bridges map data into integration contracts; never serialize JPA entity graphs.
- [ ] Inbound adapters validate event type, schema version, headers, source/tenant, and payload.
- [ ] Client-supplied correlation IDs are never trusted as credentials or authorization proof.
- [ ] Business correlation is clearly separated from trace IDs/span IDs.
- [ ] Trace propagators work across async/brokers where needed, with sampling and data policies.
- [ ] Correlation persists even after traces end, outboxes retry, or DLQs replay.
- [ ] Critical messages are persisted via an outbox/durable job in the business transaction.
- [ ] Consumers have an inbox/idempotency mechanism and broker-appropriate ack/retry handling.
- [ ] Correlation ID is not used as a dedup key or artificial partition ordering key.
- [ ] Schema evolution, header encoding, and historical replays have been tested.
- [ ] Logs, metrics, and traces do not leak PII/tokens or cause high cardinality.
- [ ] Tests cover domain event→message and message→domain event, plus real-broker integration tests.
- [ ] Operators can trace source events, messages, consumer events, and outcomes without viewing restricted data.

## 22. References

- Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc, publish as handoff: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — Standard and Custom Events / `@EventListener`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — `SimpleApplicationEventMulticaster` and executors: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — `org.springframework.messaging.Message`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/messaging/Message.html
- Spring Framework 6.2 — `MessageHeaders`, ID and timestamp: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/messaging/MessageHeaders.html
- Spring Framework 6.2 — `MessageBuilder`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/messaging/support/MessageBuilder.html
- Spring Integration — Message headers and read-only ID/timestamp: https://docs.spring.io/spring-integration/reference/message.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework Reference — Observability Support: https://docs.spring.io/spring-framework/reference/integration/observability.html
- W3C Trace Context Recommendation: https://www.w3.org/TR/trace-context/
- CloudEvents Specification: https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md
- Micrometer Context Propagation Reference: https://docs.micrometer.io/context-propagation/reference/
- Spring for Apache Kafka Reference — sending/receiving and message headers: https://docs.spring.io/spring-kafka/reference/
- Spring AMQP Reference — listener containers, converters and headers: https://docs.spring.io/spring-amqp/reference/
