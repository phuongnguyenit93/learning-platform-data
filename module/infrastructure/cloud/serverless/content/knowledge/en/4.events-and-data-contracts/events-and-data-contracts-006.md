# Correlation ID, Causation ID, and Event Chain Tracing

In a serverless application, a single HTTP request may trigger multiple functions, travel through an event bus, sit in a queue, and continue across multiple consumers. A business operation therefore rarely lives inside a single invocation. When an error occurs, the operational question is not only which function failed, but also: what was the original operation, which event led to this execution, which steps have completed, and which steps are still pending?

Correlation ID and causation ID answer two distinct business questions. **Correlation ID** groups messages belonging to the same workflow or business request. **Causation ID** identifies the message that directly caused the current message. When combined with event IDs, distributed traces, and structured logs, operations teams can trace a processing chain from the HTTP gateway through functions, databases, event buses, and consumers.

This topic belongs to Cloud Serverless: functions can be triggered by HTTP, messages, or events; workflow state and history must exist outside the lifetime of a single function invocation. Identifiers must be propagated across the right boundaries so workflows remain observable even when each step executes on a different runtime.

## 1. Why Are Multiple Identifier Types Needed?

Consider an order placement flow. A client submits a request to create an order. A function saves the order and emits `OrderSubmitted`. A consumer reserves inventory and emits `InventoryReserved`. A payment consumer receives that event and emits `PaymentAuthorized`. Finally, a shipping consumer receives the payment event to create a fulfillment preparation order.

Each step may execute in a different function, at different times, and even across different cloud regions or services. Logs containing only function names and timestamps are insufficient to stitch the steps together. Using a single ID for every purpose also prevents the system from distinguishing a business workflow from a single message delivery or a technical span.

Each of the following identifiers has a distinct role:

| Identifier | Question Answered | Scope and Lifecycle |
|---|---|---|
| `eventId` | Which event emission is this? | Unique to one event envelope; preserved when the same message is redelivered |
| `correlationId` | Which business workflow does this event belong to? | Kept stable across all steps belonging to the same workflow |
| `causationId` | Which direct message produced this message? | Typically equals the parent event's `eventId` or the ID of the causing command/request |
| `traceId` | Which distributed trace do these technical operations belong to? | Managed by the tracing system; may change when starting a new trace or splitting a long workflow |
| `spanId` | Which specific technical operation is being recorded? | Unique to one span within a trace |
| `requestId` | Which inbound call into this system is this? | Typically tied to one request or invocation at a specific boundary |
| `aggregateId` | Which business entity is changing? | Stable across the entity's lifecycle, e.g., `order-1052` |

Do not use these identifiers interchangeably. `eventId` identifies a message, `correlationId` groups a workflow, `causationId` expresses direct cause-and-effect, and `traceId` and `spanId` serve technical observability. `aggregateId` identifies a business entity, not a processing attempt.

## 2. Distinguishing Correlation ID from Causation ID

**Correlation ID** answers: "Which activities belong to the same business journey?" For example, every step from receiving an order to preparing it for shipment can share the same `correlationId`. When an order spawns multiple branches such as payment, notification, and analytics, those branches can still share the same correlation ID.

**Causation ID** answers: "Which direct message caused this message to be created?" When a consumer receives `OrderSubmitted` and emits `InventoryReserved`, the new event has a `causationId` equal to the `eventId` of `OrderSubmitted`. If another consumer receives `InventoryReserved` and emits `PaymentAuthorized`, the payment event's causation ID points to the inventory reservation event.

Example relationship:

```text
HTTP request
  requestId = req-01
  correlationId = flow-77
  |
  +-- OrderSubmitted
  |     eventId = evt-100
  |     causationId = req-01
  |     correlationId = flow-77
  |     |
  |     +-- InventoryReserved
  |     |     eventId = evt-110
  |     |     causationId = evt-100
  |     |     correlationId = flow-77
  |     |     |
  |     |     +-- PaymentAuthorized
  |     |           eventId = evt-120
  |     |           causationId = evt-110
  |     |           correlationId = flow-77
  |     |
  |     +-- CustomerNotified
  |           eventId = evt-130
  |           causationId = evt-100
  |           correlationId = flow-77
```

Both `InventoryReserved` and `CustomerNotified` share the same correlation ID because they belong to the same order workflow. Both have a causation ID equal to `evt-100` because both were created directly from `OrderSubmitted`. `PaymentAuthorized` carries the same correlation ID, while its causation ID is `evt-110`, reflecting the immediate parent-child link.

Never set `causationId` equal to the correlation ID. Doing so only tells you that two events belong to the same workflow, not which event directly produced which. Nor should causation ID be set to the aggregate ID: a single order can emit hundreds of events over its lifetime.

## 3. Relationship Between Business Correlation and Distributed Tracing

Correlation IDs and distributed traces frequently appear together in logs, yet they serve two different layers.

- Correlation ID is business metadata. It can be stored in outboxes, event journals, workflow state, and audit records to retrieve the full history of a workflow over days or weeks.
- Trace ID is technical observability metadata. It connects spans within a trace, such as an HTTP server span, function span, database client span, and message consumer span. Trace backends may sample or expire data based on retention limits.
- Span ID identifies a specific operation. A span can have a parent span or links to multiple other spans.

A trace does not necessarily span the entire business lifetime. A workflow can last several days, outlive trace retention, or traverse a scheduled step. In such cases, the correlation ID must still be preserved even though each leg may start a new technical trace. Conversely, a single trace may contain many technical operations that do not map one-to-one with business events.

W3C Trace Context defines propagation fields such as `traceparent` and `tracestate`. Over HTTP, they are typically passed in headers. For messages or events, they are passed in transport metadata/headers when supported by the platform. Do not put `traceparent` into the business payload by default: trace context is observability metadata with its own lifecycle and policies. If the system needs a durable business identifier, store the correlation ID in the event envelope or a standardized business metadata field.

| | Correlation ID | Trace ID |
|---|---|---|
| Purpose | Groups steps of a business workflow | Connects technical operations in a distributed trace |
| Where stored | Event envelope, workflow state, audit records, logs | Trace context in headers/transport metadata and trace backend |
| Retention | Follows business and audit retention | Follows tracing system sampling and retention |
| Can change between steps? | Typically no, while within the same workflow | May change when splitting a new trace or spanning long-lived workflows |
| Used for deduplication? | No | No |

## 4. Rules for Generating and Propagating Identifiers

For services to coordinate, teams must agree on where IDs are created and how they propagate across each trigger type.

### When Receiving an HTTP Request

The edge API gateway or edge function generates a new correlation ID when starting a new business workflow. If a client supplies a request ID or correlation ID, treat it as untrusted external input: validate format, enforce length limits, reject control characters, and apply appropriate namespacing rules. Never treat an arbitrary client-supplied value as proof of authentication or authorization.

You can preserve the client-supplied ID in a `clientRequestId` field for reconciliation while the system generates an internal `correlationId`. If an API allows clients to continue an existing workflow, verify the caller is authorized to access that workflow before accepting an existing correlation ID.

Each HTTP invocation can have its own `requestId`. If a client retries the same operation with the same idempotency key, the request ID of each call may differ, while the correlation ID of the accepted operation and its idempotent result should be linked according to API rules. An idempotency key is a distinct mechanism and does not replace a correlation ID.

### When a Function Emits Events

When a function creates the first event from a request, the event carries the workflow's correlation ID and a causation ID pointing to the command or request that triggered the operation, if that command/request has a stable identifier. Every new event always receives a new event ID.

When a consumer processes an event and emits a downstream event:

1. Preserve the correlation ID from the input event.
2. Generate a new event ID for the output event.
3. Set the output event's causation ID to the event ID of the event directly processed.
4. Preserve the aggregate ID and increment the aggregate version per domain rules if the event reflects a mutation of that aggregate.
5. Propagate trace context via transport metadata according to tracing standards.

### When Calling Another HTTP Service

Propagate the correlation ID in an agreed business header, such as `X-Correlation-ID`, if the target API supports it. Propagate trace context via `traceparent`/`tracestate` using an OpenTelemetry propagator or HTTP client instrumentation. Never hand-craft `traceparent` by concatenating arbitrary strings; formatting and trace/span ID generation belong to the tracing library.

### When Publishing to an Event Bus or Queue

Place the event ID, correlation ID, and causation ID in the envelope or standardized message attributes. Place trace context in transport metadata so consumers can extract it. Verify message size limits and attribute count/length limits imposed by your platform.

### When Running on a Schedule or Starting an Independent Workflow

An independent scheduled run typically starts a new correlation ID. If the schedule resumes a stored workflow, load the correlation ID from the workflow state. Never reuse a fixed correlation ID across every run of a cron job, as doing so collapses distinct runs into one.

## 5. Designing the Event Envelope

The event envelope should provide the minimum fields needed to identify and trace an event. Field names must be standardized system-wide; consumers should never have to infer a correlation ID from a queue name or aggregate ID.

Example JSON envelope:

```json
{
  "eventId": "evt-110",
  "eventType": "InventoryReserved",
  "schemaVersion": 1,
  "occurredAt": "2026-11-17T12:05:12Z",
  "correlationId": "flow-77",
  "causationId": "evt-100",
  "aggregate": {
    "type": "Order",
    "id": "order-1052",
    "version": 2
  },
  "data": {
    "orderId": "order-1052",
    "reservationId": "reservation-501"
  }
}
```

In this example, `eventId` identifies the current event; `causationId` points to `OrderSubmitted`; `correlationId` preserves the link to the order creation workflow; `aggregate.version` helps detect stale or out-of-order events. `occurredAt` is when the business fact occurred, distinct from when the consumer received or processed the message.

When using CloudEvents, standard fields such as `id`, `source`, `type`, `subject`, and `time` carry most of the core metadata. Correlation ID and causation ID can be represented using extension attributes with consistent names, such as `correlationid` and `causationid`. Whether using CloudEvents or a custom envelope, document compatibility rules and keep field semantics consistent across all producers.

Do not dump every piece of technical metadata into the business payload. Trace context belongs in transport metadata; retry counts or worker details also belong in message attributes or logs. The event payload should focus on the business event and metadata that must persist long-term.

## 6. Java Example: Creating a Child Event with Correlation and Causation

The following example illustrates a cloud-vendor-neutral metadata contract. `EventEnvelope` is a shared application-layer type; the event bus adapter handles serialization and mapping to platform message attributes.

```java
import java.time.Instant;
import java.util.UUID;

public record EventMetadata(
        String eventId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String correlationId,
        String causationId,
        String aggregateId,
        long aggregateVersion) {}

public record EventEnvelope<T>(EventMetadata metadata, T data) {}

public record OrderSubmitted(String orderId, String customerId) {}
public record InventoryReserved(String orderId, String reservationId) {}

public final class EventFactory {

    public EventEnvelope<InventoryReserved> inventoryReserved(
            EventEnvelope<OrderSubmitted> cause,
            String reservationId,
            long nextAggregateVersion) {

        EventMetadata parent = cause.metadata();
        EventMetadata metadata = new EventMetadata(
                "evt-" + UUID.randomUUID(),
                "InventoryReserved",
                1,
                Instant.now(),
                parent.correlationId(),
                parent.eventId(),
                parent.aggregateId(),
                nextAggregateVersion);

        InventoryReserved data = new InventoryReserved(
                cause.data().orderId(), reservationId);
        return new EventEnvelope<>(metadata, data);
    }
}
```

The key lies in three operations: the new event gets a new ID, the correlation ID is preserved from the parent event, and the causation ID equals the parent event's event ID. In production applications, inject a `Clock` for testable time, use an appropriate ID generator, determine the aggregate version within the same transaction as the data change, and ensure the event and outbox record are committed atomically.

If a consumer receives a command rather than an event, the causation ID may point to the command ID. The contract must state clearly what kind of entity that ID refers to, or use a reference structure with `kind` and `id`, avoiding cases where a consumer assumes every causation ID is an event ID.

## 7. Propagating Trace Context with OpenTelemetry in Java

OpenTelemetry provides APIs to inject trace context into a carrier before sending a message and extract context upon receipt. A carrier can be a header map, an HTTP request builder, or message attributes depending on the adapter. The example below uses `Map<String, String>` to clarify the flow; in production, prefer automatic instrumentation of HTTP clients, messaging clients, and runtimes where supported.

### Injecting on Publish

```java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapPropagator;
import java.util.HashMap;
import java.util.Map;

public final class TraceHeaders {
    private final TextMapPropagator propagator;

    public TraceHeaders(OpenTelemetry openTelemetry) {
        this.propagator = openTelemetry.getPropagators()
                .getTextMapPropagator();
    }

    public Map<String, String> injectCurrentContext() {
        Map<String, String> carrier = new HashMap<>();
        propagator.inject(Context.current(), carrier, Map::put);
        return carrier;
    }
}
```

`injectCurrentContext()` populates propagation fields according to the configured propagator, typically `traceparent` and optionally `tracestate` or baggage if enabled. The publish adapter transfers this map into message attributes. Never substitute `traceId` for correlation ID as a business field.

### Extracting on Consume

```java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapPropagator;
import java.util.Map;

public final class TraceContextExtractor {
    private final TextMapPropagator propagator;

    public TraceContextExtractor(OpenTelemetry openTelemetry) {
        this.propagator = openTelemetry.getPropagators()
                .getTextMapPropagator();
    }

    public void process(Map<String, String> messageAttributes,
                        Runnable businessHandler) {
        Context extracted = propagator.extract(
                Context.root(), messageAttributes, Map::get);

        try (Scope scope = extracted.makeCurrent()) {
            businessHandler.run();
        }
    }
}
```

This snippet illustrates restoring context on the active processing thread. In a function runtime, ensure the scope is closed even if the handler throws an exception; never retain `Context` in a static variable for subsequent invocations. If the framework already extracts context automatically, do not create a duplicate parent span.

In a complete application, a consumer typically creates a `CONSUMER` span for message processing. That span can use the extracted context as its parent when the relationship is a linear chain. When a consumer aggregates multiple independent messages, consider span links to the input contexts rather than arbitrarily picking one message as the sole parent.

## 8. Fan-Out, Fan-In, and Multi-Cause Workflows

Fan-out occurs when a single event spawns multiple processing branches. Child events typically retain the shared correlation ID and share the parent event as their causation ID. Each child event gets its own event ID. This makes it possible to locate all branches of a workflow and identify which branch originated from which event.

Fan-in occurs when a step requires results from multiple events—for instance, emitting `OrderReady` only after both `PaymentAuthorized` and `InventoryReserved` have completed. A single `causationId` cannot fully express multiple direct causes. In this case:

- Preserve the workflow's correlation ID.
- Store each incoming event in workflow state or a dependency table.
- When emitting the aggregated event, use an extension field such as `causationIds` if the contract permits, or record references to the input events in workflow history.
- In distributed tracing, use span links to connect the aggregated span to multiple input spans.

Never pick one arbitrary input event and treat it as the sole cause of the aggregated result. Doing so loses the true causal graph and complicates incident investigation.

## 9. Retry, Redelivery, and Dead-Letter Queue

Retries are where many systems accidentally corrupt the meaning of their IDs.

**When a queue redelivers the same message:** keep the event ID, correlation ID, and causation ID unchanged. A redelivery is not a new business event. You may record `deliveryAttempt`, `receiveCount`, retry timestamp, or invocation ID in operational metadata or logs. These fields must never replace the event ID.

**When the application emits a new retry event:** if the system emits `OrderProcessingRetryScheduled` or `PaymentRetryRequested`, that is a new event and requires a new event ID. The correlation ID is preserved if it still belongs to the original workflow; the causation ID points to the event or command that requested the retry. You can add `retryOfEventId` to identify the original event being retried.

**When redriving from a DLQ:** if returning the original message to the queue, preserve the original event ID and business metadata so consumers recognize it as the same event. Record the redrive action in an audit log or separate operational metadata. If an operational tool creates a new command requesting reprocessing, that command gets its own ID and can act as the causation of a new retry event.

Idempotency must rely on the event ID or an appropriate business key, combined with the consumer name when needed. Do not use correlation ID as an idempotency key: one workflow can legitimately emit multiple distinct events, each of which must be processed once per consumer policy. Nor should trace ID be used as an idempotency key, since traces can change across retries or when a new trace starts.

## 10. Querying History and Diagnosing Incidents

For effective tracing, every event-processing log entry should include a consistent set of fields:

| Log Field | Purpose |
|---|---|
| `timestamp` | When the log was recorded |
| `service` / `function` | Component performing the processing |
| `eventType` | Type of event being processed |
| `eventId` | Locate all processing attempts for a single event |
| `correlationId` | Locate all activities belonging to a workflow |
| `causationId` | Locate the direct parent event |
| `traceId` / `spanId` | Open the corresponding distributed trace and span |
| `aggregateId` / `aggregateVersion` | Track the history of the business entity |
| `outcome` / `errorCode` | Identify the outcome and error classification |
| `deliveryAttempt` | Distinguish message delivery attempts when investigating retries |

An investigation workflow can start with correlation ID to retrieve all events and logs. Then use causation ID to reconstruct parent-child links, event ID to find redeliveries, aggregate ID/version to verify update ordering, and trace ID to inspect latency across technical spans.

Example SQL query assuming an event journal with metadata columns:

```sql
SELECT event_id,
       event_type,
       correlation_id,
       causation_id,
       aggregate_id,
       aggregate_version,
       occurred_at
FROM event_journal
WHERE correlation_id = :correlation_id
ORDER BY occurred_at, aggregate_version;
```

Querying by causation ID locates direct child events:

```sql
SELECT event_id, event_type, occurred_at
FROM event_journal
WHERE causation_id = :parent_event_id
ORDER BY occurred_at;
```

In large systems, index by correlation ID, event ID, causation ID, and aggregate ID depending on access patterns. If retaining an event journal long-term, define retention, data partitioning, and deletion policies per legal and business requirements. Trace backends are typically optimized for short-term technical debugging; an event journal or workflow history is better suited for durable business history.

## 11. Observing Fan-Out and Long-Running Workflows

With a correlation ID, you can aggregate the number of emitted events, completed consumers, failed branches, and elapsed time from first to last event. These figures reveal stuck workflows even when individual functions report no errors.

Key metrics to track:

- Number of open workflows and age of the oldest open workflow.
- Elapsed time from the initiating event to each business milestone.
- Number of events without consumer completion or terminal state.
- Redelivery counts, retries, and message counts in DLQs.
- Latency from when an event is emitted to when consumers start and finish processing.
- Events skipped as duplicates or rejected due to schema/missing-metadata errors.

Never use correlation ID, event ID, user ID, or aggregate ID as high-cardinality metric labels. Those values belong in logs and controlled trace attributes. Metrics should use bounded labels such as `eventType`, `consumer`, `outcome`, `region`, and `errorClass`.

For workflows spanning hours or days, you do not need to keep a single trace open across the entire workflow. Create a new trace per phase and add span links to the prior context if supported by your tracing system. Correlation ID alongside workflow state maintains the business link. This avoids depending on trace backend retention and trace size limits.

## 12. Security and Privacy of Identifiers

Correlation IDs and causation IDs are routinely written to logs, dashboards, and support tools, so never embed personal data or secrets inside them. Use random values or non-inferable IDs; never build IDs by concatenating emails, phone numbers, access tokens, or sensitive data.

A client-supplied correlation ID can be forged to pollute logs or intentionally make unrelated requests look like a single workflow. Systems should generate internal IDs or store sanitized external IDs separately. Never use correlation ID, trace ID, or causation ID as an authorization mechanism. Workflow access permissions must be enforced via identity, tenant, and business policies.

When logging IDs, avoid logging full payloads "for easier tracing." Log only necessary metadata, mask or strip sensitive fields, and restrict log read access. If a correlation ID can be used by a user to query status, it must be an unguessable token and still require authorization checks on the status endpoint.

## 13. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using one ID for correlation, event, and trace | Cannot distinguish workflows, messages, and spans | Use separate fields and document semantics and origin |
| Every function generates a new correlation ID | Event chain breaks across async boundaries | Inherit correlation ID from the input message |
| Setting causation ID equal to correlation ID | Direct parent-child causality is lost | Point causation to the event/command that directly caused the new event |
| Generating a new event ID on each queue redelivery | Idempotency fails to recognize duplicate messages | Preserve the original message's event ID across redeliveries |
| Using correlation ID as idempotency key | Legitimate distinct events in the same workflow are treated as duplicates | Use event ID or operation-specific business keys |
| Propagating only traceparent without saving correlation ID | Links are lost when traces are sampled or expire | Persist correlation ID in event/workflow metadata |
| Putting IDs into metric labels | High cardinality degrades metric cost and performance | Keep IDs in logs/traces; use low-cardinality labels on metrics |
| Logging client-supplied IDs without validation | Log injection or false grouping of requests | Validate, enforce length limits, and generate internal IDs |
| Picking one arbitrary parent for a fan-in event | Causal model omits contributing inputs | Record multiple causation references and use span links |

## 14. Event Contract Checklist

- [ ] Every event has a unique event ID that remains stable across redeliveries.
- [ ] Correlation ID is created at the workflow entry point and preserved across all steps in that workflow.
- [ ] Causation ID points to the command/event that directly produced the current event.
- [ ] Event envelope includes event type, schema version, occurred time, and aggregate identity/version when needed.
- [ ] Trace context is propagated using standard propagation mechanisms over HTTP and message transports.
- [ ] Business correlation metadata is persisted durably without relying solely on the trace backend.
- [ ] Retries, redrives, and idempotency define clear rules for event IDs and attempt metadata.
- [ ] Fan-out preserves causal links; fan-in records multiple input causes.
- [ ] Logs include correlation ID, causation ID, event ID, and trace/span ID when available.
- [ ] Metrics do not use high-cardinality IDs as labels.
- [ ] IDs contain no personal data or secrets and are never used for authorization.
- [ ] Event journals or workflow history can be queried by correlation ID and causation ID.

## 15. Conclusion

Correlation ID indicates which activities belong to the same business workflow. Causation ID indicates which direct event or command created the current message. Event ID identifies a specific event; trace ID and span ID connect technical operations; aggregate ID tracks a business entity. By keeping each field true to its meaning and propagating it across HTTP, functions, outboxes, event buses, queues, and consumers, teams can reconstruct event chains, diagnose retries, detect stuck workflows, and reconcile business history without depending on a single function invocation.
