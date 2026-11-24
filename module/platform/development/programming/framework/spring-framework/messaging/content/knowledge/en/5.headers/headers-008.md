# Distinguishing Message IDs, Business IDs, and Trace IDs

## 1. Why Are Multiple Types of IDs Needed?

In a message-driven system, a single message may pass through multiple channels, brokers, consumers, and services. One business transaction can also emit multiple messages; a message may be redelivered multiple times; and a request may traverse multiple service spans in a distributed trace. Consequently, a single identifier rarely expresses every concept accurately.

Example: a customer places order `ORD-2048`. The system emits an `OrderPlaced` event, then dispatches an inventory reservation command, a payment request, and an email notification. These messages relate to the same order, yet each message is a separate unit of exchange. They may belong to one workflow and be observed in one trace, yet each concept has a distinct lifecycle.

Properly distinguishing IDs helps:

- Prevent duplicate processing without dropping distinct events for the same entity.
- Link logs, messages, and processing steps within a workflow.
- Trace requests across multiple services and downstream calls.
- Investigate retry, redelivery, replay, and out-of-order processing failures.
- Design stable payloads and headers when producers and consumers are deployed independently.

## 2. Types of IDs and Their Scopes

| ID type | What does it identify? | Typical lifecycle | Primarily used for |
| --- | --- | --- | --- |
| Framework message ID | A message object/envelope created by Spring | Tied to the message object; may change when a new message is created | Identifying a message within framework scope |
| Application message ID / event ID | A specific logical message or business event | Stable across retries/replays of the same logical message | Deduplication, auditing, and correlating deliveries |
| Business ID / aggregate ID | A business entity such as an order, payment, or customer | Exists throughout the entity's lifecycle | Looking up data and applying business rules |
| Correlation ID | A multi-step request or workflow | Can span multiple messages/services | Linking steps of the same business flow |
| Trace ID | A distributed trace | Tied to one execution recorded by tracing | Grouping spans within a trace |
| Span ID | A specific operation/span in a trace | Usually new for each span | Identifying a call or processing step |
| Causation ID | The message/event that directly caused the current message | Points to the immediate parent message | Building causal relationships between messages |
| Broker delivery tag/offset | Position or delivery attempt within a broker | Tied to queue, partition, consumer session, or delivery | Acking, committing offsets, and managing read position |
| Idempotency key | An intent/operation that must avoid repeated execution | Stable across retry attempts of the operation | Protecting commands/APIs from duplicate side effects |

Names like `messageId`, `eventId`, `correlationId`, or `traceId` do not automatically carry consistent semantics just because they share a name. Clearly define who creates each ID, what scope it is unique within, whether it stays constant across retries, and what consumers use it for.

## 3. Message IDs: Identifying an Envelope or Logical Message

### 3.1. Framework Message ID in Spring

`org.springframework.messaging.Message<T>` has a payload and `MessageHeaders`. Spring manages standard headers such as ID and timestamp; you can read the message ID via `message.getHeaders().getId()` and creation time via `message.getHeaders().getTimestamp()`.

The framework message ID identifies a message object per Spring's mechanism. When building a new message with `MessageBuilder`, converting, copying, or reconstructing a message, the ID may be regenerated depending on the path and configuration. Do not use this ID as a business key or assume it remains stable across every broker, adapter, serialization, and replay.

For example, a producer creates `Message<OrderPlaced>` and sends it over a channel. If a consumer subsequently creates a new message to forward to the next step, the new message may have a different framework ID even though it processes the same order.

### 3.2. Application Message ID or Event ID

An application message ID is an application-defined identifier for a logical message unit. For events, the name `eventId` is usually clearer. This ID should be generated once when the event is formed and kept unchanged when that same event is retried, redelivered, or replayed.

For example, a `PaymentCaptured` event has `eventId=evt-pay-9001`. If the broker redelivers the event because the consumer failed to ack, the redelivery still carries `evt-pay-9001`. The consumer can recognize that this is the same event encountered earlier.

If a new event is produced for the same order, it must have a new event ID. `OrderPlaced`, `PaymentCaptured`, and `OrderShipped` may all carry `orderId=ORD-2048`, yet they must never share an `eventId` merely because they concern the same order.

For non-event messages, `appMessageId` or `commandId` can be used. Avoid generic names if the system has multiple identifier types; the contract documentation should specify which logical message it represents.

### 3.3. Broker-Assigned IDs

Some brokers provide a message ID, delivery tag, sequence number, or offset. These values serve delivery and storage within the broker's scope:

- A RabbitMQ delivery tag is tied to a channel/consumer delivery and used for acknowledgement; it is not a stable business ID.
- A Kafka offset is a record's position within a partition; it is not a global event ID and differs across partitions.
- A broker message ID may be set by the producer or generated by the broker depending on protocol and adapter.

Do not use a delivery tag or offset as a cross-system idempotency key. When a message is republished or moved to another broker, delivery positions can change. Keep an application event/message ID in the payload or header to identify the logical message.

## 4. Business IDs: Identifying Domain Entities

A business ID identifies an entity of interest to the business, for example:

- `orderId`: order.
- `paymentId`: payment or payment attempt.
- `customerId`: customer.
- `invoiceId`: invoice.
- `shipmentId`: shipment.
- `aggregateId`: the aggregate described by an event in domain-driven design.

Business IDs are usually placed in the **payload**, since they are data needed for the consumer to apply business rules. A value may be copied to a header if an adapter needs it for routing or filtering, but a single canonical source of truth must be designated and consistency between copies verified.

A business entity can produce many messages over its lifecycle. Therefore, a business ID does not replace a message/event ID. Example:

| Event | `eventId` | `orderId` |
| --- | --- | --- |
| `OrderPlaced` | `evt-001` | `ORD-2048` |
| `PaymentRequested` | `evt-002` | `ORD-2048` |
| `PaymentCaptured` | `evt-003` | `ORD-2048` |
| `OrderShipped` | `evt-004` | `ORD-2048` |

Here `orderId` links events pertaining to the same order; each `eventId` identifies a distinct event.

Do not use `orderId` as the deduplication key for all messages of an order. If you do, after `OrderPlaced`, the consumer might mistake `PaymentCaptured` and `OrderShipped` for duplicates simply because they share `orderId`.

A business ID does not have to be a database primary key either. Opaque/UUID public IDs can be used instead of exposing internal sequential numbers. Avoid embedding sensitive details such as emails, phone numbers, or personal identifiers into IDs just for lookup convenience.

## 5. Correlation ID and Causation ID

### 5.1. Correlation ID

`correlationId` links multiple requests/messages belonging to the same workflow or business journey. For instance, a single checkout creates messages to check inventory, request payment, and send an email. Those messages can share `correlationId=checkout-2048` so logs and dashboards group them together.

Correlation ID is usually propagated across downstream steps of the same workflow, even when each step creates a new logical message. It is not necessarily equal to a business ID: an order can be modified, retried for payment, or shipped multiple times across different workflows.

Correlation ID is not necessarily equal to trace ID either. A long-running business workflow may span multiple requests or traces; conversely, one trace may encompass multiple technical steps within one request. Keep a correlation ID when you need to track a workflow longer than a single trace's lifetime.

### 5.2. Causation ID

`causationId` indicates which message/event directly caused the current message. Example:

- `OrderPlaced` has `eventId=evt-001`.
- The consumer processes it and emits `ReserveInventory` with `causationId=evt-001`.
- When inventory emits `InventoryReserved`, the event can record `causationId` pointing to the command or message that triggered that outcome, per the system's convention.

Correlation ID answers “which messages belong to the same workflow?”; causation ID answers “which message directly gave rise to this message?”. These two fields complement each other.

## 6. Trace ID and Span ID in Distributed Tracing

Distributed tracing models a request or technical execution flow as a trace consisting of multiple spans. Each trace has a `traceId`; each operation has a `spanId`; child spans have a parent relationship with the span that invoked them.

- **Trace ID:** groups spans belonging to the same trace, often across multiple services.
- **Span ID:** identifies an operation such as an HTTP client call, consumer handler, or database call.
- **Parent span ID:** links the current span to the span that created it.

W3C Trace Context defines the `traceparent` header to propagate trace context across service boundaries. The header contains version, trace-id, parent-id, and trace-flags. In production systems, let OpenTelemetry/Micrometer Tracing and framework/client/broker instrumentation manage context creation and propagation.

Do not invent arbitrary `traceparent` values or copy only the trace ID while dropping parent/span semantics. When a consumer begins processing a message, instrumentation can create a new consumer span linked to the injected context. How traces are stitched depends on the transport and instrumentation; messages crossing a broker may be modeled with producer/consumer spans or links depending on the integration.

Trace ID serves technical observability and should not be used as a business key, idempotency key, or long-term order identifier. Sampling, retention, and tracing backends may make traces unqueryable after some time. Business IDs and event IDs still need to exist independently in persisted data/allowed logs.

## 7. Lifecycle Rules: Which IDs Stay Constant, Which Are Regenerated?

| Scenario | Framework message ID | Event/app message ID | Business ID | Correlation ID | Trace/span |
| --- | --- | --- | --- | --- | --- |
| Creating a new message object for the same event | May be new | Keep unchanged | Keep unchanged | Keep unchanged if same workflow | Context managed by instrumentation |
| Broker redelivers the same logical message | Do not assume stability | Keep unchanged | Keep unchanged | Keep unchanged | Context restored by adapter/instrumentation if supported |
| Creating a new event for the same order | New | New | Keep orderId | Can keep if same workflow | New span; trace follows execution flow |
| Starting a new workflow for the same order | New | New when there is a new message | Keep orderId | Usually newly generated | Usually a new trace for the new request |
| Consumer processes a downstream step | New message if creating a new envelope | New ID for new message/event | Keep related entity ID | Keep if same workflow | New span in appropriate trace/context |
| Replaying event history | Message/delivery metadata may be new | Keep original event ID | Keep original business ID | Keep original metadata if meaningful | Replay may run in a new trace; store replay link separately |

Practical rule: a business entity's ID stays constant as long as it remains the same entity; an event ID stays constant as long as it remains the same logical event; a correlation ID stays constant within the defined workflow; trace/span follow the observability lifecycle of a single execution; framework/broker IDs serve their respective technical mechanisms.

## 8. Using IDs to Prevent Duplicate Processing

At-least-once delivery can cause a consumer to receive the same message multiple times. Deduplication must rely on an ID representing **the same logical operation or event**.

### 8.1. Event Consumer

A common pattern is an inbox/dedup table with a unique constraint on `(consumer_name, event_id)`:

1. Consumer receives an event and reads the stable `eventId`.
2. Within the same database transaction, attempt to insert an inbox record with the consumer name and event ID.
3. If the insert succeeds, apply business changes and commit.
4. If the unique constraint reports that the event was already processed, skip the duplicate side effect and confirm the message per the acknowledgement policy.

The inbox record and business changes must be persisted in the same transaction. If the inbox record is written first and the business transaction rolls back, redelivery could be skipped even though the side effect never completed. If business changes commit first and the inbox write fails in a crash, duplicate side effects can occur.

### 8.2. Command/API Idempotency

For client-initiated operations, use an idempotency key for the **intent to execute an operation**. For example, a client sends a payment creation request with `Idempotency-Key: pay-attempt-77`; if the request times out and the client retries with the same key, the server returns the stored result instead of creating another payment.

`orderId` is not always sufficient as an idempotency key. An order may have multiple legitimate payment attempts. The key should distinguish individual operations, be scoped by client/tenant, and be retained for a duration matching the retry policy.

### 8.3. Do Not Deduplicate by Trace ID

Trace ID often groups multiple operations within the same request. Using trace ID as a deduplication key can cause distinct messages in the same workflow to be mistaken for duplicates. Trace ID can also change when retrying in a new request, so it is not a stable idempotency key.

## 9. Propagating IDs in Spring Messaging

In Spring, payload and headers serve different roles:

- Put business IDs inside the payload DTO/record for consumers to use in business logic.
- Put `eventId`, `correlationId`, `causationId`, and `schemaVersion` in custom headers if they are envelope metadata and the adapter can transmit them.
- Framework ID and timestamp are already in `MessageHeaders`; read them via the API instead of defining custom headers with colliding names.
- Trace context should be injected/extracted by tracing instrumentation or adapters supporting trace context standards.

Do not define a custom header named `id` and assume it equals `MessageHeaders.ID`. Use specific, meaningful names such as `eventId`, `correlationId`, or `causationId` to avoid colliding with standard framework or broker headers.

When creating a new message, decide on each header explicitly:

1. Keep `correlationId` if still belonging to the same workflow.
2. Generate a new `eventId` if this is a new logical event; keep the old event ID if merely retrying/redelivering the same event.
3. Set `causationId` pointing to the message that directly caused the new message.
4. Let the framework generate a new message ID for the new envelope.
5. Let tracing instrumentation create spans and propagate context appropriately.

Do not copy all headers from an old message mechanically. Internal headers such as reply channel, error channel, routing metadata, or transport-specific fields may be inappropriate when forwarding to another destination.

## 10. Java 17 + Spring Messaging 6.2 Example

The example creates a `PaymentCaptured` message. The payload carries business IDs; custom headers carry event/workflow metadata; Spring manages the framework message ID automatically. `traceparent` in the example merely illustrates an already-injected W3C Trace Context value. In production applications, let tracing instrumentation generate and propagate this header.

Create a Maven project with the structure:

~~~text
message-id-demo/
  pom.xml
  src/main/java/com/example/messaging/MessageIdDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>message-id-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.8</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring.version}</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/MessageIdDemo.java`:

~~~java
package com.example.messaging;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

public final class MessageIdDemo {
    private MessageIdDemo() {
    }

    public record PaymentCaptured(
            String paymentId,
            String orderId,
            BigDecimal amount,
            Instant capturedAt) {
    }

    public static void main(String[] args) {
        PaymentCaptured event = new PaymentCaptured(
                "PAY-9001",
                "ORD-2048",
                new BigDecimal("125.50"),
                Instant.parse("2026-11-07T03:00:00Z"));

        Message<PaymentCaptured> message = MessageBuilder
                .withPayload(event)
                .setHeader("eventId", "evt-pay-9001")
                .setHeader("correlationId", "checkout-2048-run-1")
                .setHeader("causationId", "cmd-capture-9001")
                .setHeader("schemaVersion", 1)
                .setHeader("traceparent",
                        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
                .build();

        MessageHeaders headers = message.getHeaders();
        PaymentCaptured payload = message.getPayload();

        System.out.println("frameworkMessageIdPresent=" + (headers.getId() != null));
        System.out.println("eventId=" + headers.get("eventId"));
        System.out.println("paymentId=" + payload.paymentId());
        System.out.println("orderId=" + payload.orderId());
        System.out.println("correlationId=" + headers.get("correlationId"));
        System.out.println("causationId=" + headers.get("causationId"));
        System.out.println("traceparent=" + headers.get("traceparent"));
    }
}
~~~

Compile and run from the directory containing `pom.xml` using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.MessageIdDemo
~~~

Stdout:

~~~text
frameworkMessageIdPresent=true
eventId=evt-pay-9001
paymentId=PAY-9001
orderId=ORD-2048
correlationId=checkout-2048-run-1
causationId=cmd-capture-9001
traceparent=00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

The framework message ID does not print a concrete value because it is auto-generated by the framework and can differ across runs. The example shows each ID's distinct role: `eventId` identifies the event; `paymentId` and `orderId` identify business entities; `correlationId` groups the workflow; `causationId` indicates the causing message; `traceparent` carries trace context.

## 11. Logging, Metrics, and Security

Structured logs should record appropriate IDs for investigation:

- `eventId` or `appMessageId` to track a logical message across retries.
- `orderId`/`paymentId` to trace a business entity's history, subject to access-control policies.
- `correlationId` to group steps of a workflow.
- `traceId` and `spanId` to open the trace in the observability system.
- Broker partition/offset or delivery metadata when investigating delivery issues.

It is unnecessary to log every ID on every log line. Choose a consistent field set and avoid logging sensitive payloads. Do not put tokens, secrets, personal data, or payment details into headers/logs merely for search convenience.

For metrics, avoid using `orderId`, `eventId`, or `traceId` as high-cardinality labels. Each ID can spawn a separate time series, inflating memory usage and operational complexity. Metrics should use bounded dimensions such as service, destination, outcome, message type, or consumer group; use logs/traces to look up specific IDs.

IDs are not proof of authentication. A consumer must never trust `customerId`, `tenantId`, or routing headers simply because they appear in a message. Authenticate the sender, access permissions, and entity ownership via the system's security mechanisms.

## 12. Common Pitfalls

- **Using orderId as message ID:** multiple distinct events for the same order are treated as duplicates.
- **Using framework message ID as idempotency key:** a new message or conversion step may carry a new ID even for the same logical event.
- **Using trace ID as correlation/business ID:** tracing lifecycles do not align with business lifecycles.
- **Using correlation ID for deduplication:** multiple valid messages in the same workflow get wrongly dropped.
- **Using Kafka offset or RabbitMQ delivery tag as a global ID:** values are meaningful only within their respective broker/partition/channel scope.
- **Generating a new event ID on each retry:** consumers fail to recognize redeliveries as the same event.
- **Reusing an event ID for a new event:** two distinct events get falsely deduplicated.
- **Copying all headers when building a new message:** routing/reply/error metadata or stale IDs can carry over into the wrong context.
- **Putting sensitive business IDs into logs/metrics:** increases data exposure risk and cardinality.
- **Assuming trace context propagates automatically across every broker:** adapters and instrumentation supporting context injection/extraction are required.

## 13. Checklist for Designing IDs in Message Contracts

1. Which ID identifies the logical message? When does the producer create it, and is it preserved across retries/replays?
2. Which ID identifies the business entity? Is it in the payload and stable across the domain lifecycle?
3. Is a `correlationId` needed for a workflow spanning more than one request?
4. Is a `causationId` needed to construct parent-child event/command relationships?
5. Which instrumentation creates and propagates trace context? Do broker adapters inject/extract it?
6. Does the idempotency key distinguish multiple valid operations on the same business object?
7. Does the consumer store the deduplication record in the same transaction as business changes?
8. Is broker delivery metadata being confused with application IDs?
9. Which IDs are permitted in logs, metrics, or user-facing displays?
10. Are rules for regenerating vs. preserving each ID documented in the message contract?

## 14. Key Takeaways

Framework message ID identifies the Spring-managed envelope/message object; application message ID or event ID identifies a logical message and must stay stable when retrying the same message; business ID identifies a domain entity and can appear across many events; correlation ID groups steps in a workflow; causation ID points to the message that directly spawned the current message; trace ID/span ID serve observability of a distributed execution; broker offset/delivery tag serve delivery only within broker scope. Choose the ID matching the question to answer, define its lifecycle, and pass it consistently via payload/headers. Do not use one type of ID as a substitute for all others.