# Message ID, timestamp, and correlation metadata in Spring Integration

In **Message system**, a message carries not only the data to be processed (*payload*) but also **metadata** so the system knows when the message was created, which processing flow it belongs to, and which other messages it relates to. This is the foundation for implementing **Enterprise Integration Patterns** with Spring Integration: Gateway, Router, Filter, Transformer, Splitter, Aggregator, retry, and error channels.

Imagine an order consisting of three line items split into three messages for independent processing. Each child message needs its own identity, yet all three must be recognized as belonging to the same group so an `Aggregator` can assemble the results. `id`, `timestamp`, and `correlationId` address different needs in that problem.

## 1. Structure of a Message

Spring Messaging represents a message via `org.springframework.messaging.Message<T>`, consisting of two parts:

- **Payload**: business data, such as an order, line item, or validation result.
- **Headers** (`MessageHeaders`): metadata used for routing, correlation, observability, error handling, and flow management.

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder.withPayload("ORDER_ACCEPTED")
        .setHeader("businessOrderId", "ORD-204")
        .setHeader("eventId", UUID.randomUUID().toString())
        .build();

UUID messageId = message.getHeaders().getId();
Long timestampMillis = message.getHeaders().getTimestamp();

System.out.println("Message ID: " + messageId);
System.out.println("Created at: " + Instant.ofEpochMilli(timestampMillis));
System.out.println("Order ID: " + message.getHeaders().get("businessOrderId"));
```

In typical message construction configurations, the framework generates `id` and `timestamp`. The application adds business headers such as `businessOrderId` without having to supply values for those two system headers itself.

Headers to distinguish:

| Metadata | Meaning | Scope of use |
| --- | --- | --- |
| `id` (`MessageHeaders.ID`) | Identifier of a Message object; typically a `UUID` | Tracking a specific message |
| `timestamp` (`MessageHeaders.TIMESTAMP`) | Time the Message was created, in milliseconds since the Unix epoch | Observing when the Message was emitted |
| `correlationId` (`IntegrationMessageHeaderAccessor.CORRELATION_ID`) | Key linking Messages belonging to the same processing group | Splitter, Aggregator, and flows needing result assembly |
| `sequenceNumber` | Position of an element in a sequence, usually starting at `1` | Determining logical order of child Messages |
| `sequenceSize` | Total number of expected elements in the sequence, if known | Aggregator group completion condition |
| `businessOrderId` / `eventId` | Application-defined business headers | Order lookup, reconciliation, and deduplication |
| `traceparent` / `traceId` | Distributed observability context, if a tracing system is configured | Tracing a request across services |

**Note:** `correlationId`, `sequenceNumber`, and `sequenceSize` are Spring Integration headers; they do not necessarily appear on every Message. Do not infer `correlationId` from `id` if a component has not actually set it.

## 2. Message ID: identity of a message

`MessageHeaders.ID` helps identify a Message in logs, test assertions, or when a component reports an error. For example, a Router receives a Message with `id=M0`; a Splitter produces three child Messages `M1`, `M2`, `M3` and can use `M0` as the `correlationId` for the entire group.

```text
Original message:  id=M0, payload=[A, B, C]
                     |
                  Splitter
                     |
         +-----------+-----------+
         |           |           |
      id=M1       id=M2       id=M3
      corr=M0     corr=M0     corr=M0
      seq=1/3     seq=2/3     seq=3/3
         |           |           |
         +-----------+-----------+
                     |
                 Aggregator
```

The diagram shows a **logical relationship** and does not require the Messages to be processed sequentially. In an asynchronous branch, Message `3` can very well finish before Message `1`.

Points to remember:

1. `id` is the identity of a **Message**, not automatically the identifier of an order, event, or transaction.
2. When a component keeps the same Message or constructs a new Message, how `id` is preserved/regenerated depends on the message-building API and configuration. Do not rely on the assumption that ID always stays the same or always changes after a Transformer.
3. A retry may redeliver the same Message, while re-receiving from a broker may create a new Message. Therefore **do not use `id` alone as an idempotency key across services**; use `eventId`, `commandId`, or a business key with a stable convention.
4. `MessageHeaders` is designed to be accessed as immutable metadata. To add headers, use `MessageBuilder` to create a Message instead of mutating the headers map directly.

Example adding a business tracking key to an existing Message:

```java
Message<String> enriched = MessageBuilder.fromMessage(message)
        .setHeader("businessCorrelationId", "ORD-204")
        .build();
```

In this example, `businessCorrelationId` is an **application-specific header**; it does not automatically replace the `correlationId` key used by Spring Integration's Aggregator.

## 3. Timestamp: Message creation time differs from business event time

`MessageHeaders.TIMESTAMP` is typically a `Long` storing milliseconds since `1970-01-01T00:00:00Z`. Use `Instant` to read the time in UTC:

```java
Long createdAtMillis = message.getHeaders().getTimestamp();
if (createdAtMillis != null) {
    Instant createdAt = Instant.ofEpochMilli(createdAtMillis);
    System.out.println(createdAt);
}
```

In a multi-tier processing flow, distinguish:

| Time type | Question answered | Suggested representation |
| --- | --- | --- |
| Message timestamp | When was the current Message created? | Framework-managed `timestamp` header |
| Event time | When did the business event occur? | Payload `occurredAt` or a stable business header |
| Received time | When did the current component receive the Message? | Value measured at the receiving point |
| Processed/completed time | When did the processing step or entire pipeline finish? | Metric, span, or result record |

For example: a customer places an order at 10:00, the event enters the queue at 10:01, and it is re-read at 10:05. These three timestamps serve three different purposes. If a new Message is constructed when reading from the queue, the new Message's `timestamp` does not substitute for when the customer placed the order.

Do not manually overwrite the `timestamp` header to express *event time*. Explicitly declare an `occurredAt` field (for example ISO-8601 UTC), while measuring receive and processing times to compute latency. In distributed systems, clocks across servers can drift; timestamp is a useful marker, not absolute proof of execution order.

## 4. Correlation metadata for grouping Messages

**Correlation** is identifying messages belonging to the same task or result group. In Spring Integration, standard headers are often directly related to Splitter and Aggregator:

- `correlationId`: every item in the same group shares the same key.
- `sequenceNumber`: logical order of the item within the group.
- `sequenceSize`: expected number of items when the group is split into a sequence of known length.

They can be read via `IntegrationMessageHeaderAccessor`:

```java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

void inspectFragment(Message<?> fragment) {
    Object correlationId = fragment.getHeaders().get(
            IntegrationMessageHeaderAccessor.CORRELATION_ID);
    Integer sequenceNumber = fragment.getHeaders().get(
            IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER, Integer.class);
    Integer sequenceSize = fragment.getHeaders().get(
            IntegrationMessageHeaderAccessor.SEQUENCE_SIZE, Integer.class);

    System.out.printf("group=%s, sequence=%s/%s%n",
            correlationId, sequenceNumber, sequenceSize);
}
```

With a typical Splitter, Spring Integration can set sequence metadata on child Messages, usually linking them using the input Message's ID. The Aggregator uses the correlation key to identify the group and a *release strategy* to decide when enough data has arrived for the aggregated result.

Do not manually assign a fixed `correlationId` to all orders: independent groups would risk getting mixed together. Conversely, if each child Message has a different `correlationId`, the Aggregator cannot combine them.

### Two types of correlation that should not be conflated

**Technical correlation** for the Aggregator: an internal key used to collect the parts of one Splitter run. **Business correlation**: a key such as `businessOrderId` to trace an order across Gateway, Router, Filter, and other services.

An order may pass through multiple split/aggregate stages. Sub-groups can then use different technical correlations while still carrying the same `businessOrderId`. Similarly, a trace ID following a distributed journey can span many Messages and many Aggregator groups.

## 5. Hands-on example: Splitter → WireTap → Aggregator

The following example receives a list of three line items. `Splitter` emits each line as a separate Message; `WireTap` copies messages to an audit channel; `Aggregator` collects the items and sends the result to the output channel.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderLineFlowConfig {

    @Bean
    public DirectChannel orderLinesInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel splitAudit() {
        return new QueueChannel();
    }

    @Bean
    public QueueChannel orderLinesOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow orderLineFlow() {
        return IntegrationFlow.from("orderLinesInput")
                .split()
                .wireTap("splitAudit")
                .aggregate()
                .channel("orderLinesOutput")
                .get();
    }
}
```

You can send a Message and inspect the records in `splitAudit` using the following code in a test or a component injected with the channel beans:

```java
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

void exercise(DirectChannel orderLinesInput,
              QueueChannel splitAudit,
              QueueChannel orderLinesOutput) {

    Message<List<String>> order = MessageBuilder
            .withPayload(List.of("item-A", "item-B", "item-C"))
            .setHeader("businessOrderId", "ORD-204")
            .setHeader("eventId", UUID.randomUUID().toString())
            .setHeader("occurredAt", Instant.now().toString())
            .build();

    orderLinesInput.send(order);

    for (int i = 0; i < 3; i++) {
        Message<?> part = splitAudit.receive(1_000);
        if (part == null) {
            throw new IllegalStateException("Did not receive enough child Messages");
        }
        System.out.printf(
                "id=%s, corr=%s, seq=%s/%s, order=%s, ts=%s%n",
                part.getHeaders().getId(),
                part.getHeaders().get(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID),
                part.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER),
                part.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE),
                part.getHeaders().get("businessOrderId"),
                part.getHeaders().getTimestamp());
    }

    Message<?> aggregated = orderLinesOutput.receive(1_000);
    if (aggregated == null) {
        throw new IllegalStateException("Aggregator has not produced a result");
    }
    System.out.println("Aggregated payload: " + aggregated.getPayload());
}
```

When running in the synchronous flow of this example, the expected output is:

1. There are three Messages in `splitAudit`, each with its own `id` and the same `correlationId`.
2. The three `sequenceNumber` values are `1`, `2`, `3` respectively; `sequenceSize` is `3`.
3. The child Messages carry the business header `businessOrderId=ORD-204`.
4. The Aggregator emits one Message containing the list of collected payloads. With the example's default configuration, the result is the list of line items.

Specific `UUID` and `timestamp` values will differ across runs. If adding an `ExecutorChannel` or connecting a broker, do not assume Message **arrival** order matches `sequenceNumber` order.

> When using Splitter/Aggregator, let the framework manage correlation headers via the default mechanism unless you have special requirements. Only configure custom correlation and release strategies once you clearly understand the group lifecycle.

## 6. How does metadata flow through Enterprise Integration Patterns?

| Pattern / component | Role of metadata | What to verify |
| --- | --- | --- |
| **Gateway** | Brings requests from Java calls into the Message flow; manages reply/error channels per gateway contract | Are business headers injected or forwarded properly? |
| **Router** | Selects one or more output channels based on payload/headers | Do branches preserve the business keys needed for lookup? |
| **Filter** | Lets Messages continue or discards them by condition | Could discarding an item leave an Aggregator group waiting for a missing part? |
| **Transformer** | Creates a different payload or a new Message | Are required headers preserved/set properly across the transformation step? |
| **Splitter** | Turns one Message into multiple child Messages | Are appropriate `correlationId`, `sequenceNumber`, `sequenceSize` present? |
| **Aggregator** | Collects Messages with the same key into a group result | Are correlation strategy, release strategy, timeout, and message store suitable? |
| **Retry** | Retries a failing step according to policy | Is a retry distinguished from a new business event? |
| **Error channel** | Routes failures into the error-handling flow | Can the failed Message and corresponding business keys be traced back? |

Some endpoints forward the exact input Message, whereas some create a new Message. Therefore, when writing a Transformer or custom service, check the **actual metadata at the output**. Using `MessageBuilder` to forward needed headers should follow a clear convention; do not blindly copy system headers onto independent business events.

### When a group is incomplete

Suppose a Splitter creates three items, but a Filter drops the second item. If the Aggregator still waits for `sequenceSize=3`, the group may never complete under default conditions. Depending on requirements, design one of the following approaches: filter before splitting, update emission logic, define a release strategy for partial results, or configure timeout/expired-group handling for incomplete messages.

For long-running flows or broker-backed flows, consider an appropriate **MessageGroupStore** to persist groups, handle restarts, handle late arrivals, and clean up expired groups. `correlationId` is only a grouping key; by itself it does not guarantee exactly-once processing, durability, or arrival ordering.

## 7. Designing metadata across services

An application typically needs three parallel layers of identification:

```text
traceId                  --> Traces a journey across services
businessOrderId / eventId--> Tracks business entities and events
correlationId            --> Groups Messages within an integration flow
message.id               --> Identifies one specific Message
```

For example, when processing order `ORD-204`, all steps can attach the same `businessOrderId`, yet each Message can carry its own `id`, each Splitter group its own `correlationId`, and each distributed request its own trace context. Do not use a single value for every purpose unless it is a controlled design decision.

When crossing HTTP, Kafka, AMQP, or external systems, headers are not preserved by default: adapters/header mappers, serialization settings, and protocol rules decide what passes through. Explicitly list required metadata at boundaries, especially `eventId`, business keys, `occurredAt`, and trace context. Avoid relying on an internal Spring Integration `correlationId` if the external service does not share the same convention.

To prevent duplicate processing, store a stable idempotency key (such as `eventId`) alongside processing status in a data store capable of atomic checks. A replayed occurrence of the same event must keep this key; a new Message ID does not turn it into a new business event.

## 8. Logging, monitoring, and troubleshooting

A structured log can record the following fields at endpoint entry/exit:

```json
{
  "stage": "aggregate-input",
  "messageId": "<message-uuid>",
  "messageTimestamp": "<epoch-millis>",
  "correlationId": "<group-key>",
  "sequenceNumber": 2,
  "sequenceSize": 3,
  "businessOrderId": "ORD-204",
  "eventId": "<event-key>",
  "outcome": "accepted"
}
```

Logs should include endpoint name, outcome, processing duration, and lookup keys. Instead of logging the entire payload, pick only needed fields and avoid logging sensitive data. Metrics should measure total Messages, errors, retries, Aggregator wait time, incomplete group count, and expired group count; tracing records processing branches when tracing infrastructure is enabled.

| Symptom | Common cause | Where to check |
| --- | --- | --- |
| Aggregator waits forever | Missing item, wrong `sequenceSize`, Filter dropped an item, or release strategy mismatch | Compare `correlationId`, `sequenceNumber` sequence, timeouts, and stored groups |
| Aggregated results mix orders | Fixed `correlationId` used or colliding keys | Check correlation key source and uniqueness scope of each group |
| Related Messages fail to aggregate | `correlationId` altered or lost across Transformer/adapter | Inspect headers at each boundary and the correlation strategy |
| Logs cannot link flows across services | Business key or trace context not propagated across adapters | Check header mapper, format, and context restoration point |
| Duplicate business processing | Using Message ID as dedup key; re-receiving same event with new Message ID | Check idempotency key and atomic result-write operation |
| Timestamps show unexpected ordering | Messages created at different instants, concurrent execution, or clock skew | Distinguish event time, message time, receive time, and trace spans |

When handling errors, if receiving a `MessagingException`, you can inspect `getFailedMessage()` when available to trace back `id`, `correlationId`, and business keys. Do not assume every error carries the full original Message; this depends on where the error occurred and how it was wrapped.

## 9. Testing metadata behavior

A meaningful test for the flow in Section 5 should verify both content and metadata:

1. **Initial Message:** `getHeaders().getId()` and `getHeaders().getTimestamp()` have values; `eventId`, `businessOrderId`, and `occurredAt` are attached properly.
2. **After Splitter:** receives exactly three Messages, each with an ID; all share one `correlationId`; the set of `sequenceNumber` equals `{1, 2, 3}` and every `sequenceSize` equals `3`.
3. **After Aggregator:** receives one group result with exactly three line items, not mixed with a second order's group.
4. **Missing-item scenario:** intentionally drop one Message and verify the application handles incomplete groups according to the chosen policy.
5. **Reprocessing scenario:** replay the same `eventId` via another Message and verify the idempotency mechanism does not create duplicate business side effects.
6. **Cross-adapter scenario:** verify required headers remain preserved when crossing to another service or broker.

Do not hardcode specific UUID or timestamp values in tests, because this metadata is generated at runtime. Assert data types, presence, relationships across Messages, and end-to-end flow outcomes.

## 10. Principles to apply when designing flows

- Use **Message ID** to track a specific Message; use a stable **eventId/commandId** for deduplication and idempotency.
- Use **Message timestamp** to observe when the Message was created; use a separate **event time** for business time.
- Use **correlationId** consistently within a group an Aggregator needs to collect; maintain a **business correlation key** when tracing the entire transaction.
- When using **Splitter, Filter, Router, Transformer, Aggregator**, verify the impact of each step on headers and expected item counts.
- With concurrency, retries, and brokers, explicitly design **group completion, timeout, persistence, and duplicate handling**; correlation metadata alone does not solve these issues.
- Log and test end-to-end using clear correlation keys so every Message and business task can be traced.

Understanding the proper boundary between `id`, `timestamp`, `correlationId`, and `sequenceNumber` makes a Spring Integration flow easier to scale, observe, and troubleshoot—especially when Messages are split, travel through multiple branches, and are reassembled into results.
