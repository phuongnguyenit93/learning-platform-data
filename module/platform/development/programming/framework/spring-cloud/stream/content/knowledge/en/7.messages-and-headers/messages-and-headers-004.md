# Event ID, Correlation ID, and Causation ID

In an event-driven system, a single business workflow can span multiple services and generate many messages. When an error occurs, you need to answer three questions: which specific message is being processed, which business workflow does that message belong to, and which message directly led to it. These three questions correspond to **event ID**, **correlation ID**, and **causation ID**.

These three identifiers have different scopes and should not be used interchangeably. An event ID identifies a single event; a correlation ID links messages belonging to the same journey; a causation ID points to the immediate cause that produced the current event. Spring Cloud Stream can carry these identifiers in message headers so downstream services can continue processing while preserving context.

## 1. Three Identifiers Solving Three Different Questions

| Identifier | Meaning | Scope | Example |
|---|---|---|---|
| Event ID (eventId) | Unique identifier for a single event emission | One specific event | evt-01H... |
| Correlation ID (correlationId) | Groups messages belonging to the same business process or request | The entire journey | corr-checkout-9001 |
| Causation ID (causationId) | Identifier of the message or command that directly caused the current event | Direct parent-child relationship | evt-order-created-9001 |

Order placement workflow example:

~~~text
OrderCreated
  eventId       = evt-100
  correlationId = corr-900
  causationId   = (none, this is the starting event)

        |
        v

PaymentRequested
  eventId       = evt-101
  correlationId = corr-900
  causationId   = evt-100

        |
        v

PaymentAuthorized
  eventId       = evt-102
  correlationId = corr-900
  causationId   = evt-101

        |
        v

OrderConfirmed
  eventId       = evt-103
  correlationId = corr-900
  causationId   = evt-102
~~~

All events belong to the same workflow `corr-900`, yet each event has its own event ID. The causation ID of `PaymentAuthorized` is the event ID of `PaymentRequested`, because that was the event that directly triggered the payment processing step. This enables tracing the causal chain backward rather than merely knowing which messages belong to the same workflow.

### Event ID

An event ID must remain stable throughout the lifecycle of an event. The producer generates the ID when the event is formed, then keeps the same ID when resending due to timeouts or connection errors. If a new event ID is generated on every retry, the consumer will struggle to recognize two messages as the same event and may execute the business action twice.

A UUID or another unique identifier format can be used. If the event ID is only unique within the scope of a single producer, combine it with the source or producer name when forming the deduplication key, such as `(source, eventId)`.

### Correlation ID

A correlation ID is usually created at the entry boundary of a workflow: the API receiving a request, the service accepting a command, or an external system emitting an event. Subsequent messages generated within the same workflow retain the same correlation ID as they flow across services.

Do not generate a new correlation ID at each service, as that breaks the link between steps. If an event initiates a new independent workflow, that workflow may receive a new correlation ID according to business conventions.

### Causation ID

A causation ID references the message or command that directly led to the current event. Under an event-to-event convention, the causation ID of a new event is usually equal to the event ID of the input event. If a command directly causes an event, the command ID can be stored as the causation ID; the key is that the whole system agrees on the definition and clearly documents what kind of entity is referenced.

A causation ID indicates only a direct relationship. To trace back multiple steps, follow the chain of causation IDs or query an event store. A correlation ID only groups messages together; it does not express ordering or causal relationships.

## 2. Where to Place the Identifiers: Payload or Headers?

Spring Messaging represents a message with a payload and headers:

~~~text
Message<T>
  ├── payload  : business data
  └── headers  : metadata accompanying the message
~~~

The payload holds business content, such as `OrderCreated` with order ID, customer ID, and total amount. Headers hold control or transport metadata for the message, such as event ID, correlation ID, causation ID, content type, and tracing information.

There are two common ways to organize them:

- Place the identifiers inside the event envelope/payload so they become part of the event contract, persisted and exchanged across multiple platforms.
- Place the identifiers in headers so middleware and message handlers can inspect metadata without decoding the business payload.

A system can use both: keep the event ID and event type in the envelope while placing necessary values in headers for routing, logging, and propagation. When using both locations, define a canonical source of truth and validate consistency. Never allow the payload to state `eventId=A` while the header states `eventId=B`.

Envelope example:

~~~json
{
  "eventId": "evt-100",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T10:15:30Z",
  "correlationId": "corr-900",
  "causationId": null,
  "data": {
    "orderId": "ord-9001",
    "customerId": "cus-2001",
    "total": 125000
  }
}
~~~

Example of the same metadata in headers:

~~~text
eventId       = evt-100
eventType     = OrderCreated
correlationId = corr-900
~~~

Do not put personal data, tokens, passwords, or secrets into these IDs. Headers are frequently recorded in logs, metrics, or broker admin tools, so treat them as metadata observable by many components.

## 3. Creating Messages and Attaching Headers in Spring

Spring Messaging provides `Message`, `MessageHeaders`, and `MessageBuilder`. You can create a message with a payload and attach metadata as follows:

~~~java
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class OrderEventFactory {

    public Message<OrderCreated> create(
            OrderCreated order,
            String correlationId) {

        String eventId = UUID.randomUUID().toString();

        return MessageBuilder.withPayload(order)
            .setHeader("eventId", eventId)
            .setHeader("eventType", "OrderCreated")
            .setHeader("correlationId", correlationId)
            .build();
    }

    public record OrderCreated(
        String orderId,
        String customerId,
        long total
    ) {}
}
~~~

This example assumes each call to `create` starts a new process. In real applications, the correlation ID is usually received from the request context or generated once at the business intake boundary. The event ID should be generated and persisted alongside the event/outbox before sending so retries reuse the exact same ID.

You can build a message from existing data using `MessageBuilder.withPayload(...)`, then set headers via `setHeader(name, value)`. Header values should be simple serializable types, most commonly strings. Avoid putting custom Java objects into headers under the assumption that every binder serializes and restores them identically.

### Using Message in a Function

If a function needs to read metadata, declare its parameter as `Message<T>` instead of receiving only payload `T`:

~~~java
import java.util.UUID;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
public class OrderEventFunctions {

    @Bean
    Function<Message<OrderCreated>, Message<OrderValidated>> validateOrder() {
        return input -> {
            OrderCreated order = input.getPayload();

            String sourceEventId =
                (String) input.getHeaders().get("eventId");
            String correlationId =
                (String) input.getHeaders().get("correlationId");

            if (sourceEventId == null || sourceEventId.isBlank()) {
                throw new IllegalArgumentException("Missing eventId header");
            }

            OrderValidated validated = new OrderValidated(
                order.orderId(),
                order.total()
            );

            MessageBuilder<OrderValidated> output =
                MessageBuilder.withPayload(validated)
                    .copyHeaders(input.getHeaders())
                    .setHeader("eventId", UUID.randomUUID().toString())
                    .setHeader("eventType", "OrderValidated");

            if (correlationId != null) {
                output.setHeader("correlationId", correlationId);
            }
            output.setHeader("causationId", sourceEventId);

            return output.build();
        };
    }

    public record OrderCreated(String orderId, long total) {}
    public record OrderValidated(String orderId, long total) {}
}
~~~

The function preserves the correlation ID of the input message, creates a new event ID for the output event, and sets the input event ID as the causation ID. `copyHeaders` forwards needed headers, after which the function overrides headers that take on new meanings. In production, control which headers are allowed to be copied; do not carelessly forward credentials or internal metadata to other services.

The snippet above illustrates metadata mapping. If the entire function can be re-executed on retry, do not generate a new event ID for the same business outcome on every attempt. Generate the ID once and persist it with the outbox record or processing state so every replay of the same event uses the same ID.

If a function receives `OrderCreated` instead of `Message<OrderCreated>`, it cannot directly access message headers. When event ID, correlation ID, or causation ID are needed in logic, accept a `Message` or pass the metadata via a well-defined business data type.

## 4. Propagating Identifiers Across Multiple Services

Each service must preserve the proper message context when emitting subsequent events:

1. Read the event ID, correlation ID, and causation ID of the input message.
2. Validate the event ID and required metadata according to the contract.
3. Execute the business logic.
4. Generate a new event ID for the output event.
5. Preserve the correlation ID of the current workflow.
6. Set the causation ID to the ID of the message or command that directly caused the new event.
7. Publish the message with consistent headers and payload.

Example of a payment service receiving `PaymentRequested` and emitting `PaymentAuthorized`:

~~~java
import java.util.UUID;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<PaymentRequested>, Message<PaymentAuthorized>> authorizePayment() {
    return input -> {
        PaymentRequested request = input.getPayload();

        // Perform validation and payment processing here.

        return MessageBuilder.withPayload(
                new PaymentAuthorized(request.paymentId(), "AUTHORIZED"))
            .copyHeaders(input.getHeaders())
            .setHeader("eventId", UUID.randomUUID().toString())
            .setHeader("eventType", "PaymentAuthorized")
            .setHeader(
                "causationId",
                input.getHeaders().get("eventId")
            )
            .build();
    };
}
~~~

This abbreviated example assumes the input event always has `eventId`. In a real application, validate required headers before processing and define how to handle messages missing metadata. Do not fabricate a causation ID from an arbitrary string or from the correlation ID; the causation ID must point to the entity that caused the event per the chosen convention.

If a single message produces multiple events, each output event gets its own event ID, the same correlation ID, and potentially the same causation ID pointing to the input message. If an event is emitted by a background process with no input message, record its origin clearly, such as a command ID, scheduler execution ID, or an identified system cause.

## 5. Standard Headers, Custom Headers, and Broker Headers

Spring Messaging defines several standard headers, such as the message ID and message creation timestamp. These headers serve the message lifecycle within the framework. They do not replace the business event ID.

| Header | Meaning | Usage |
|---|---|---|
| MessageHeaders.ID | Spring-generated ID for the message object | Used when identifying a message within the framework scope |
| MessageHeaders.TIMESTAMP | Message creation time in the framework | Helps observe when the message object was constructed |
| eventId | Business event ID | Kept stable across retries and redeliveries |
| correlationId | Business workflow ID | Preserved across services in the same journey |
| causationId | Immediate cause ID | References the message/command that caused the event |
| eventType | Event type | Assists classification and contract validation |

Do not overwrite Spring-reserved headers such as `id` and `timestamp` to store the business event ID or business time. If you need the business occurrence time, use an `occurredAt` field in the event envelope or an agreed custom header.

Spring Integration also uses the `correlationId` header for certain message-grouping flows such as aggregators. If an application uses splitters/aggregators, distinguish the business correlation ID from Spring Integration's internal message-group correlation ID. You can use a dedicated header name such as `businessCorrelationId` to avoid accidentally overwriting Spring Integration control metadata.

When a message passes through a binder, headers are mapped to broker metadata:

- Kafka stores headers as key/value bytes; the binder converts values using the header mapper and corresponding configuration.
- RabbitMQ uses AMQP message properties and headers.
- Pulsar supports key/value message properties on messages.

Mapping behavior and supported data types can vary by binder and version. For reliable interoperability across systems, prefer consistent header names and string or simple scalar values. Test actual headers after a message traverses the broker, especially when using custom headers, complex objects, or multiple languages.

Do not assume every internal Spring header is forwarded intact across every broker. Some headers may be filtered, type-converted, encoded, or unsupported. Headers critical to the event contract must be verified with integration tests.

## 6. Distinguishing Correlation ID and Distributed Trace ID

A correlation ID links messages by business workflow. A trace ID serves distributed tracing to link spans within a technical observation. Both identifiers can coexist and usually have different scopes.

| Criterion | Correlation ID | Trace ID |
|---|---|---|
| Purpose | Track a business journey | Track a single distributed execution |
| Lifecycle | Can live long across many steps and processing cycles | Follows the trace context managed by the tracing system |
| Origin | Application or business intake system | Tracing instrumentation/SDK |
| Example | corr-order-9001 | W3C trace ID in traceparent |

A business workflow can span minutes or days, whereas a technical trace may conclude after a short period. When a message is reprocessed or an asynchronous step is triggered later, the system may start a new trace while retaining the original correlation ID.

For distributed tracing, use Micrometer Tracing, OpenTelemetry, or compatible instrumentation to propagate trace context such as W3C `traceparent` and `tracestate`. Do not manually set the correlation ID as the trace ID, and do not overwrite tracing headers managed by the library. The correlation ID can be added to logs to search for operations belonging to the same workflow.

## 7. Using Identifiers to Prevent Duplicate Processing

Brokers can redeliver the same message when a consumer shuts down before acknowledging, loses connectivity, or exceeds a processing timeout. Therefore, consumers must tolerate receiving the same event multiple times.

Event ID is the appropriate key for identifying duplicates of the same event. Correlation ID is unsuitable as a deduplication key because many different events in the same workflow share the same correlation ID. Causation ID is also unsuitable because a single cause can legitimately trigger multiple events.

A table for tracking processed events might look like this:

~~~sql
CREATE TABLE processed_events (
    source       VARCHAR(200) NOT NULL,
    event_id     VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (source, event_id)
);
~~~

The consumer checks and records the `(source, eventId)` key in the same transaction as the business update:

~~~text
BEGIN TRANSACTION

1. Attempt to INSERT (source, eventId) into processed_events.
2. If the key already exists:
     skip business side effects and finish as a duplicate delivery.
3. If the insert succeeds:
     apply the business data changes.

COMMIT
~~~

The unique constraint prevents two instances from processing one event as two independent executions. Recording the event ID and updating business data must happen within the same transaction if using the same database; if separated, a failure between the two operations can still leave inconsistent state.

For side effects outside the database transaction, such as calling a payment gateway or sending an email, add an idempotency key or reconciliation mechanism with the target service. Simply storing the event ID in a table cannot automatically undo an HTTP request that already succeeded.

When a producer resends due to a timeout, resend with the exact same event ID and event content. If business logic genuinely produces a new event, generate a new event ID. Never generate a new event ID on each retry.

## 8. Storing and Emitting Metadata with the Transactional Outbox

If a service updates the database and then sends an event to the broker in two independent operations, situations can arise where the database write succeeds but sending the message fails, or the message is sent while the database transaction rolls back.

The Transactional Outbox stores the business change and the outbox record in the same transaction. The outbox record should store event ID, event type, payload, correlation ID, causation ID, and creation time. A relay process reads the outbox and publishes the message to the broker.

~~~text
Business transaction
  ├── UPDATE orders
  └── INSERT outbox_events
        event_id
        event_type
        payload
        correlation_id
        causation_id
        created_at

Outbox relay
  └── Publish event with the same eventId and metadata
~~~

If the relay publishes successfully but stops before marking the record as sent, the message may be emitted again. Consumers still need idempotency based on the event ID. The outbox coordinates writing data and recording the intent to publish an event; it does not by itself guarantee each message reaches the broker exactly once.

When replaying events from an outbox, DLQ, or archive, preserve the original event ID, correlation ID, and causation ID. You may add replay-specific metadata, such as `replayAttempt` or `replayedAt`, to distinguish the replay from when the event was originally created. Do not alter the original event's causation ID simply because an operational replay occurred.

## 9. Logging, Searching, and Protecting Metadata

Include the identifiers in structured logs so the entire journey can be searched:

~~~text
timestamp=2026-11-24T10:15:30Z
service=payment-service
eventType=PaymentAuthorized
eventId=evt-102
correlationId=corr-900
causationId=evt-101
orderId=ord-9001
result=SUCCESS
~~~

Log the identifier fields along with the service, event type, outcome, and relevant broker details such as topic, partition, offset, or message ID. Avoid logging the full payload if it contains sensitive data.

Some operational practices:

- Use correlation ID to search logs across an entire workflow.
- Use event ID to find all deliveries, retries, redeliveries, and processing attempts for the same event.
- Use causation ID to trace back to the message that directly caused an event.
- Combine event ID with source when uniqueness is only guaranteed per producer.
- Do not put high-cardinality IDs into metric labels; doing so can explode the number of time series. Detailed IDs belong in logs and traces.
- Set retention periods for logs, outbox, inbox, and deduplication tables in alignment with event retention and replay windows.
- Control access because metadata can reveal business structure and service relationships.

## 10. Testing Metadata as Messages Cross Brokers

Unit tests for factories or functions can verify that IDs are generated and passed properly. The test binder helps verify Spring Cloud Stream bindings within the application. Integration tests against a real broker must verify that headers are mapped and preserved as expected by the binder.

A test suite should cover:

1. Producer creates event ID and correlation ID; verify both are present on the message.
2. Function receives a message and emits a new event; event ID changes, correlation ID is preserved, causation ID points to the input event.
3. Two distinct events in the same workflow have different event IDs but the same correlation ID.
4. Redelivering the same event ID; consumer detects duplicate and does not repeat side effects.
5. Verify headers after traversing Kafka, RabbitMQ, or Pulsar, including any data type conversions.
6. Route a message to a DLQ and replay it; verify original metadata is preserved.
7. Test missing event ID or correlation ID cases per the contract policy.

Example test for event creation logic:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class OrderEventFunctionsTest {

    @Test
    void newEventKeepsCorrelationAndReferencesCause() {
        OrderEventFunctions functions = new OrderEventFunctions();

        Message<OrderEventFunctions.OrderCreated> input = MessageBuilder
            .withPayload(new OrderEventFunctions.OrderCreated("ord-9001", 125000))
            .setHeader("eventId", "evt-100")
            .setHeader("correlationId", "corr-900")
            .build();

        Message<OrderEventFunctions.OrderValidated> output =
            functions.validateOrder().apply(input);

        assertNotEquals("evt-100", output.getHeaders().get("eventId"));
        assertEquals("corr-900", output.getHeaders().get("correlationId"));
        assertEquals("evt-100", output.getHeaders().get("causationId"));
    }
}
~~~

The test above demonstrates three important rules: a new event gets a new ID, the correlation ID is preserved, and the causation ID references the input event. In a real project, instantiate beans or configure tests according to how the application organizes its functions.

## 11. Metadata Conventions for a Multi-Service System

Before multiple teams jointly build producers and consumers, agree on a metadata contract:

| Field | Recommended convention |
|---|---|
| eventId | Required on events; unique within source scope |
| eventType | Required; stable event type name |
| correlationId | Required for business flows needing multi-step traceability |
| causationId | Present when the event is caused by another message/command |
| source | Identifier of the service or producer emitting the event |
| occurredAt | Business occurrence timestamp, in UTC |
| schemaVersion | Payload contract version |
| traceparent | W3C-standard trace context when tracing is enabled |

The convention should also specify:

- Who generates event ID and correlation ID.
- Whether causation ID references an event or command, and how to distinguish the two.
- Which headers are required and which are optional.
- Header names and data types used across all binders.
- How to handle messages with missing or invalid metadata.
- How IDs are preserved through retries, DLQ, outbox, replay, and migrations.
- How processed event IDs are stored and how long deduplication data is retained.

For events using CloudEvents, standard attributes such as `id`, `source`, `type`, `subject`, and `time` can carry event metadata. Correlation and causation can be represented as extension attributes according to organizational conventions. Avoid creating a parallel contract that conflicts with CloudEvents if the system has adopted that standard.

## 12. Practice Sequence and Completion Criteria

| Step | Practice | Expected outcome |
|---|---|---|
| 1. Define events | Create an envelope with event ID, event type, source, and occurrence time | Distinguish event identity from business data |
| 2. Create correlation | Generate or accept correlation ID at the workflow boundary | Multiple messages in the same journey share the same ID |
| 3. Record causation | When emitting a new event, reference the direct cause's ID | Able to trace parent-child relationships backward |
| 4. Pass headers | Use MessageBuilder and Message<T> | Functions read and emit metadata properly |
| 5. Verify binder | Send through a broker and read headers back | Know which headers are preserved, type-converted, or filtered |
| 6. Deduplicate | Persist source + eventId key in a transaction | Redeliveries do not repeat side effects |
| 7. Observe | Include identifiers in logs and combine with trace context | Able to locate an event and the entire business journey |

You have completed this lesson when you can explain the difference between event ID, correlation ID, and causation ID; create and propagate them through Spring Cloud Stream; preserve correlation ID across multiple services; set causation ID to the immediate cause; and use event ID to prevent duplicate processing when a broker redelivers a message.

## 13. Official References

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html) — binding architecture, binders, and message processing.
- [Spring Messaging — Message](https://docs.spring.io/spring-framework/reference/integration/spring-integration/message.html) — payload, headers, and message abstraction.
- [Spring Messaging — MessageBuilder API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html) — creating messages and manipulating headers.
- [Spring Cloud Stream — Functional model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html) — receiving and returning messages in Supplier, Function, and Consumer.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — standard for propagating trace context across components.
- [CloudEvents Specification](https://github.com/cloudevents/spec) — standard event envelope and metadata.
- [Spring Cloud Stream — Kafka binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html) — Kafka binder configuration.
- [Spring Cloud Stream — RabbitMQ binder](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html) — mapping message properties and headers with RabbitMQ.
- [Spring Cloud Stream — Pulsar binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — connecting and message metadata with Pulsar.
