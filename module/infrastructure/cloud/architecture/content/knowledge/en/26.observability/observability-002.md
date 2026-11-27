# Correlation IDs and Context Propagation Across APIs and Queues

A business request in a cloud system is rarely processed by a single service. A create-booking request might traverse an API gateway, booking service, inventory service, payment service, database, message broker, and notification worker. Part of the work executes synchronously over HTTP/gRPC; the rest continues asynchronously via queues or event streams. When an error occurs, each component's logs often live in different places and are written at different times. Without a way to link them, operations teams struggle to determine which logs, traces, and messages belong to the same business journey.

A **Correlation ID** is an identifier passed across components to link related activities together. **Context propagation** is the process of passing necessary contextual information across process, service, protocol, and message broker boundaries so downstream components continue observing and processing with the right context. Both concepts support incident investigation, workflow tracking, auditing, and measuring end-to-end latency; they must also be designed carefully to avoid identifier spoofing, leaking sensitive data, or causing uncontrolled cardinality growth.

This lesson belongs to the **Observability** chapter of the **Cloud Architecture** track. The curriculum covers designing cloud applications from business requirements through networking, compute, data, and deployment models, balancing reliability, security, scalability, cost, and operations. In this topic, the goal is to make a multi-service journey traceable and explainable while preserving trust boundaries and per-protocol semantics.

After this lesson, you will be able to:

- Distinguish between correlation ID, request ID, trace ID, span ID, message ID, and business ID.
- Design context contracts for HTTP/gRPC, message queues, and event envelopes.
- Propagate context across synchronous calls, fan-out, async workflows, retries, and DLQs.
- Combine correlation IDs with distributed tracing and structured logging.
- Define trust boundaries, and regenerate or validate client-supplied IDs.
- Propagate tenant context and causation metadata without exposing sensitive data.
- Handle batches, message redelivery, replays, and long-running workflows.
- Set testing and operational standards for context propagation.

## 1. What Problem Does a Correlation ID Solve?

Suppose a customer submits a request to create a booking. The API gateway logs receiving the request, the booking service logs creating the booking, the inventory service logs holding the slot, the payment service logs authorizing payment, and the notification worker logs sending the email. If each log only has a timestamp and service name, investigating requires correlating timestamps, payloads, and user details; this is error-prone when many requests run concurrently.

If all activities share a correlation ID, operators can search by that ID and see which components processed that journey.

~~~mermaid
flowchart LR
    C["Client request"] --> G["API Gateway"]
    G --> B["Booking service"]
    B --> I["Inventory service"]
    B --> P["Payment service"]
    B --> Q["Booking event queue"]
    Q --> N["Notification worker"]
    G -. "same correlation ID" .-> B
    B -. "same correlation ID" .-> I
    B -. "same correlation ID" .-> P
    Q -. "propagated context" .-> N
~~~

Correlation IDs are especially useful when:

- A request traverses multiple services and multiple runtimes.
- Work continues after the HTTP response has been returned.
- An event is processed by a consumer seconds or hours later.
- A business flow generates multiple messages or retries.
- An incident affects a specific group of requests/tenants.
- Audit records, application logs, and distributed traces need to be linked.

A correlation ID helps locate related activities, but by itself it does not capture parent-child relationships between steps and does not replace traces/spans.

## 2. Distinguishing Identifier Types

Systems often use several IDs simultaneously. If everything is named requestId or correlationId without clear semantics, observability tools become hard to interpret.

| ID Type | Scope and Purpose | Typical Behavior |
| --- | --- | --- |
| Correlation ID | Links a journey or group of related business activities | Can be preserved across multiple services and messages |
| Request ID | Identifies a single request reception/handling at a boundary | New requests typically get a new ID |
| Trace ID | Identifies a distributed trace composed of multiple spans | Stays the same within the trace; tracing standards define its format |
| Span ID | Identifies a single operation/span in a trace | Each span has its own ID |
| Parent span ID | Points to the span that directly created the current span | Builds parent-child relationships |
| Message ID | Identifies a specific message | Preserved across redeliveries of the same message |
| Causation ID | Points to the command/event/message that directly caused the current activity | Often the ID of the preceding message |
| Business ID | Identifies a domain entity such as bookingId or paymentId | Has its own business lifecycle |
| Idempotency key | Identifies retries of the same operation to prevent duplicate execution | Preserved across retries per contract |

An example:

- Correlation ID: the entire rental booking journey.
- Trace ID: a technical trace representing a call graph that may include gateway, booking, and inventory.
- Request ID: a single HTTP delivery to the booking API.
- Message ID: the BookingCreated event stored by the broker.
- Causation ID: the CreateBooking command that led to that event.
- Booking ID: the booking entity in the domain.

A workflow spanning hours or days may consist of multiple separate traces while still sharing the same correlation ID. This preserves business linkage when a trace ends or resumes in another process.

## 3. Correlation ID Is Not Trace ID

Distributed tracing models operations as traces and spans, typically with parent-child relationships, timing, attributes, and status. A correlation ID is usually a simple linking key at the application or business layer.

Both IDs can coexist:

- Correlation ID answers: "Which journey does this activity belong to?"
- Trace ID answers: "Which technical operations are in this trace and how are they related as parent-child?"
- Span ID answers: "Which specific operation is this span?"

For example, an API receives a request, calls inventory over HTTP, and publishes an event. The HTTP trace may end after publishing. A consumer running later picks up the message context and starts a new trace or a span linked to the producer's trace. The correlation ID still connects producer and consumer into a single business journey.

### 3.1. When to Use Links Instead of Parent-Child?

A message may be generated from multiple activities or a batch of multiple messages. There is not always a single parent span. Tracing APIs can support span links to relate to one or more other spans without forcing them into an artificial parent-child tree.

For a batch of hundreds of messages, a batch-processing span can link to the originating contexts or record message IDs in bounded metadata. Avoid stuffing unbounded lists into span attributes.

## 4. Where Should Correlation IDs Be Generated?

A correlation ID can originate from the client, the gateway, or the first service that understands the journey boundary. Agree on who issues it and under what conditions external IDs may be trusted.

### 4.1. Requests from the Internet or Untrusted Clients

A client may send an X-Correlation-ID header. That value is helpful for supporting users in finding their requests, but it should not be assumed unique, valid, or trustworthy by default. A client could intentionally reuse the same ID, send a huge string, or include characters that break logs.

A safe policy:

1. The gateway validates format, length, and charset for inbound headers.
2. If valid and allowed by contract, record it as an external correlation reference.
3. The gateway generates an internal ID with sufficient entropy for the platform-managed journey.
4. Log the mapping between external reference and internal correlation ID if needed for support.
5. Internal services only trust context propagated by trusted gateways/service identities.
6. Never use a correlation ID to grant permissions, identify tenants, or authenticate callers.

In internal systems with authenticated callers and clear trust contracts, upstream IDs can be continued. However, public ingress boundaries should enforce validation and anti-spoofing.

### 4.2. Generating IDs

An ID should:

- Have bounded length and charset.
- Have sufficiently low collision probability for the system's scale.
- Not contain emails, phone numbers, customer names, or identifying data.
- Not encode authorization info or tenant secrets.
- Not contain overly granular timestamps unless needed.
- Never replace security tokens or idempotency mechanisms.

A random UUID or random ID with adequate entropy is usually a simple choice. There is no need to pack all business information into the ID since that belongs in controlled log/trace fields.

## 5. Context Contract for HTTP

For HTTP, context is typically carried in request headers. Standardize header names, formats, lengths, trusted proxy behavior, and handling when headers are missing or malformed.

Example internal contract:

~~~http
POST /v1/bookings
X-Correlation-ID: 01JCV8MZ6X2B7R6A0F5M6K8N2P
X-Request-ID: req-gateway-7f31
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
Content-Type: application/json
~~~

The X-Correlation-ID header here is an application-specific example. traceparent belongs to the W3C Trace Context standard and has its own grammar/semantics; do not manually construct or modify its fields using correlation ID rules.

### 5.1. Header Allowlist

Do not forward all inbound headers to every downstream service. Explicitly allowlist headers permitted for propagation, for example:

- Gateway-validated correlation ID.
- W3C trace context via tracing instrumentation.
- Authenticated tenant context under an internal contract.
- Locale or request deadline if supported.
- Idempotency key only to operations requiring those semantics.

Do not forward Authorization, Cookie, secrets, or privileged internal headers to services that do not need them. Proxies/gateways must strip or overwrite headers that clients could spoof.

### 5.2. Calling Downstream

When the booking service calls inventory, it keeps the journey's correlation ID but creates an appropriate request ID/span for the new call. Do not copy the same request ID across all outbound calls because request IDs should represent a specific boundary.

## 6. W3C Trace Context and OpenTelemetry

W3C Trace Context defines standard headers to carry trace context between tracing-aware systems. Two common headers are:

- traceparent: carries version, trace ID, parent ID, and trace flags per the standard grammar.
- tracestate: carries vendor-specific tracing state.

OpenTelemetry provides APIs/SDKs and instrumentation to create, extract, and inject trace context. Business correlation IDs can be recorded as log fields or span attributes according to organizational naming conventions.

Do not write a naive traceparent parser and trust arbitrary inbound values. Use tested tracing SDKs/instrumentation to validate, propagate, and handle sampling flags.

### 6.1. Do Not Turn Baggage into a Sensitive Data Store

W3C Baggage can carry key-value context across services, but it propagates across many boundaries and may be logged or forwarded to third parties. Never place passwords, access tokens, emails, payment data, or PII in baggage.

Only propagate small, necessary, non-sensitive metadata, such as an evaluated routing hint or context version. Limit total size and allowlist keys/values.

## 7. Context Contract for gRPC

gRPC typically uses metadata to propagate context alongside RPCs. Client/server interceptors can inject/extract correlation IDs and tracing context.

Requirements:

- Standardize metadata keys and charsets per gRPC rules.
- Limit metadata size.
- Use shared interceptors instead of having each service roll its own.
- Propagate deadlines/cancellations.
- Preserve trace context via supported instrumentation.
- Do not pass secrets or full user tokens if downstream does not need them.
- Validate tenant/user identity at an authoritative boundary.

If one RPC fans out into multiple parallel downstream RPCs, all can share the correlation ID but must have separate span/request contexts for each call.

## 8. Context in Message Envelopes

HTTP headers disappear when work turns into a message. Brokers may support message headers/properties, though some systems also need a standard envelope in the payload or metadata layer.

Example envelope:

~~~json
{
  "messageId": "msg-92317",
  "messageType": "BookingCreated",
  "schemaVersion": 2,
  "occurredAt": "2026-11-18T05:20:00Z",
  "correlationId": "corr-7a92",
  "causationId": "cmd-81b3",
  "traceParent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "tenantRef": "tenant-482",
  "data": {
    "bookingId": "booking-1005"
  }
}
~~~

This example only illustrates structure. Tenant reference should only be included when consumers need it and are authorized. Do not pass PII, credentials, or access-permission claims merely for logging convenience.

### 8.1. Broker Metadata and Payload Envelopes

If the broker supports message headers, correlation ID, traceparent, message ID, and causation ID can live in metadata while the payload holds domain data. Choose a clear source of truth and avoid cases where headers specify correlation ID A while the payload specifies ID B.

Some self-describing event formats have corresponding fields such as id, type, source, subject, time, and extensions. When using a standard envelope, its mapping to broker metadata must be defined so consumers do not have to guess.

## 9. Producer: Creating and Injecting Context into Messages

The producer receives context from the current request, processes the command, and creates an event/message. Context must be embedded into the outgoing message along with the business payload and schema version.

~~~text
handle CreateBooking:
    context = currentRequestContext

    event = BookingCreated(
        messageId = newMessageId(),
        correlationId = context.correlationId,
        causationId = context.requestOrCommandId,
        traceContext = currentTraceContext,
        bookingId = result.bookingId
    )

    publish(event)
~~~

This is conceptual pseudocode. If the producer writes to a database and publishes a message, a transactional outbox or equivalent mechanism is needed so a transaction cannot commit while the event is lost. Context propagation does not solve atomicity between database and broker.

### 9.1. Preserving Context for Asynchronous Publishing

A background job may run after the HTTP request has finished. When saving a job/outbox record, persist the allowed context metadata so the worker can maintain the link. Do not store the entire request object or Authorization header just to reconstruct context later.

## 10. Consumer: Extracting Context and Starting a New Operation

The consumer reads the message, validates the format, and extracts context per the contract. It creates a new request/processing span while retaining the original correlation ID.

~~~mermaid
sequenceDiagram
    participant P as Producer service
    participant Q as Message broker
    participant C as Consumer
    participant D as Downstream service

    P->>Q: Publish message + correlation/trace context
    Q-->>C: Deliver message
    C->>C: Extract and validate context
    C->>D: Call with propagated correlation and new span
    D-->>C: Response
    C->>Q: Ack after durable processing
~~~

Consumers must distinguish:

- Message ID: identifies the message being received.
- Delivery attempt: the broker's current delivery attempt for the message.
- Correlation ID: the associated business journey.
- Trace context: observational relationship between producer/consumer.
- Causation ID: direct cause that produced the message.

If a message lacks context, the consumer should generate a new correlation ID per policy and clearly mark the source as legacy/missing context. Do not reject every valid message just because context is missing if the contract permits compatibility; at the same time, track metrics to phase out legacy producers.

## 11. Fan-Out and Fan-In

A single event can trigger multiple consumers: notification, analytics, audit, and search indexing. Consumers may run concurrently, finish at different times, and emit child messages.

### 11.1. Fan-Out

Branches can keep the original correlation ID to tie back to the same journey. Each consumer has its own trace/span; child messages receive a new message ID and a causation ID pointing to the event processed.

~~~mermaid
flowchart TB
    E["BookingCreated<br/>corr-123 / msg-1"] --> N["Notification consumer<br/>msg-2"]
    E --> A["Analytics consumer<br/>msg-3"]
    E --> S["Search consumer<br/>msg-4"]
    N --> M["Email delivery<br/>msg-5"]
~~~

Do not use a correlation ID as a way to count completed branches. Workflows need dedicated state/aggregation to determine whether all branches succeeded or timed out.

### 11.2. Fan-In

When multiple branches produce results for a workflow to aggregate, a correlation ID helps group related activities, but a business key and expected participant set are still required. Grouping solely by correlation ID can cause duplicate messages or stray branches to terminate the workflow prematurely or wait forever.

## 12. Retries, Redelivery, and Idempotency

Brokers can frequently deliver the same message multiple times, for instance if a consumer finishes processing but crashes before acking. A redelivered message keeps the same message ID per contract, while delivery attempt changes.

When retrying a downstream operation:

- Keep the journey's correlation ID.
- Keep the business idempotency key if it is still the same command/side effect.
- Generate an attempt ID or record a separate attempt number.
- Retain the source message ID and causation ID.
- Do not generate a new correlation ID on each retry if you want to search the full history.
- Do not use correlation ID for deduplication; it often spans multiple messages/operations.

~~~text
messageId = msg-92317
correlationId = corr-booking-1005
attempts:
    1 -> timeout
    2 -> transient database error
    3 -> processed and acknowledged
~~~

Idempotency must be enforced at the consumer/business boundary using a dedup store, unique constraint, or suitable mechanism. Correlation metadata only helps observe which retry attempt belongs to which journey.

## 13. Dead-Letter Queues and Replays

Messages land in a dead-letter queue (DLQ) after exceeding the retry policy or failing unrecoverably. When re-injecting a message from a DLQ for processing, retain the original metadata so investigative linkage is not lost.

A DLQ record should preserve per policy:

- Original message ID.
- Original correlation ID and causation ID.
- Original trace context if still relevant.
- Source queue/topic and partition/offset if applicable.
- Sanitized failure reason/error category.
- Attempt count, first/last delivery times.
- Replay operator/job ID and replay timestamp.
- Schema version and processing version.

A replay is a new operational execution yet still tied to the original journey or message. You can generate a separate replay execution ID, keep the original correlation ID, and attach replay causation metadata. Do not alter the original message ID if you need to trace the exact failed record.

Before replaying, verify the root cause is fixed, schemas are compatible, consumers are idempotent, and side effects will not dangerously repeat. A correlation ID does not automatically make a replay safe.

## 14. Long-Running Workflows and Sagas

A saga or process manager can span several days. The original HTTP trace no longer exists when subsequent steps run. A correlation ID can connect events/commands throughout the workflow while each execution starts a new trace.

Example booking requiring slot reservation, payment, and handover waiting:

1. CreateBooking command starts correlation.
2. BookingCreated emits event.
3. ReservationRequested goes to inventory.
4. ReservationAccepted triggers the next step.
5. PaymentRequested calls the payment provider.
6. PaymentAuthorized continues the workflow.
7. BookingConfirmed completes.

If payment fails, the saga may emit ReleaseReservation. The causation ID points to the event/command that directly triggered the compensating action; the correlation ID links the entire saga.

### 14.1. Correlation Does Not Replace Workflow State

To know which step a saga is on, persist workflow state, timeouts, retry counts, and participant statuses. Searching logs by correlation ID aids investigation; it is not a reliable state database for the saga.

## 15. Tenant Context and Authorization Boundaries

Multi-tenant SaaS often needs a tenant reference to log and route messages to the right tenant. However, context metadata does not by itself prove access authorization.

A message bearing tenantRef tenant-A could still be spoofed if the producer is untrusted or broker ACLs are misconfigured. Consumers must verify producer identity, topic/queue permissions, and resource ownership per contract.

Principles:

- Tenant identity is established at an authenticated boundary.
- Producers only emit verified tenant context.
- Consumers check message origin and policy before accessing resources.
- Correlation IDs must not contain tenant secrets or direct identifying data.
- Tenant IDs in logs are classified and masked/hashed if policy requires.
- Cache keys, idempotency scopes, and dedup keys must respect tenant boundaries.
- Never use a correlation ID as an authorization token.

## 16. Security and Limiting Context

Context travels across many systems, so it may be logged, exported, persisted in brokers, or forwarded to third-party services. A context contract must define allowlists and data classifications.

Should NOT propagate:

- Passwords, API keys, access tokens, refresh tokens, or private keys.
- Raw Authorization headers/Cookies.
- Payment card data or sensitive data unnecessary for the operation.
- Full user payloads.
- PII solely for search convenience.
- Internal privilege claims that downstream has no mechanism to verify.

Should propagate:

- Random correlation ID.
- Standard trace context.
- Necessary request/message/causation IDs.
- Verified tenant reference when required.
- Permitted deadline or locale.
- Schema/context version.
- Operation type and source service.

### 16.1. Log Injection and Header Abuse

Client-supplied correlation IDs must be bounded in length, charset, and format. Do not inject raw control characters/newlines into logs. Structured loggers must encode values per field rather than concatenating strings arbitrarily.

For headers or message metadata, enforce max sizes and reject/normalize per contract. An attacker sending huge IDs or thousands of baggage entries can spike CPU, memory, and telemetry costs.

## 17. Structured Logging

Each log event should be a record with explicit fields rather than plain text alone. At minimum, include:

- timestamp.
- severity.
- service.name/service.version.
- environment/region/cell.
- correlation_id.
- request_id or message_id as appropriate.
- trace_id and span_id if tracing is active.
- operation/event name.
- status/error category.
- duration and retry attempt.
- tenant reference per policy.

Example:

~~~json
{
  "timestamp": "2026-11-18T05:20:01.240Z",
  "severity": "ERROR",
  "service": "booking-service",
  "environment": "production",
  "correlation_id": "corr-7a92",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "message_id": "msg-92317",
  "operation": "reserve_inventory",
  "error_code": "DEPENDENCY_TIMEOUT",
  "attempt": 2
}
~~~

This example contains no request bodies, tokens, or PII. Field names should be consistent across services so log searches, queries, and dashboards do not require complex mapping.

### 17.1. Cardinality and Cost

Correlation IDs have very high cardinality because each journey typically has its own value. This field is suited for log/trace search, but generally unsuitable as a metric label/tag in time-series metrics. Creating a time series per ID can rapidly blow up metric store cardinality and cost.

Metrics should use bounded dimensions like service, operation, status class, region, or queue. Correlation IDs are used to drill down from metrics/alerts into logs and traces.

## 18. Propagating Context Through Batch and Scheduled Jobs

A batch job may process records belonging to many different business journeys. Do not assign a single correlation ID to the entire batch and lose the original linkage of each record.

You can use:

- A batch/job execution ID for the entire run.
- Each item's original correlation ID if available.
- A parent job ID or causation ID to record relationships.
- Trace links or spans per batch/sub-batch.
- An item ID for independent error handling and retries.

For example, a settlement batch processing 10,000 payments: each payment has its own correlation; the job execution ID links all of them to a single run. This supports finding both the whole run and tracing an individual payment.

## 19. Context in Schedules and Callbacks

A scheduled task may execute after the schedule-creation request has ended. Decide whether the correlation ID binds to the schedule creation, the execution run, or the long-running workflow. All three values may differ.

Example:

- Workflow correlation ID: retained throughout the rental booking lifecycle.
- Schedule ID: identifies the payment reminder schedule.
- Job execution ID: identifies a single worker execution of the schedule.
- Trace ID: a new trace for the execution.

Callbacks from external providers also require the provider-returned correlation/reference and the internal operation ID. Do not trust correlation headers from callbacks before webhook signatures/authentication are verified. Authenticate the source first, then link the event to the workflow.

## 20. Context Propagation Across Third Parties

Not all external providers support custom headers or metadata. If they do not preserve correlation IDs, store a mapping between the provider request/reference ID and the internal ID.

Principles:

- Only send correlation references if the integration contract permits.
- Do not send internal trace baggage or unnecessary tenant metadata.
- Record provider request IDs/transaction references when available.
- Verify callback signatures before trusting references.
- Store mappings with clear access control and retention.
- On callback arrival, start a new trace and link to the original operation.
- Do not assume external providers will propagate traceparent.

## 21. Context Versioning and Compatibility

Context contracts evolve over time: adding causation IDs, renaming fields, moving from headers to envelopes, or adopting new tracing standards. Versioning or compatibility rules are required.

Recommendations:

- New metadata fields should be optional initially.
- Consumers must handle missing fields per policy.
- Producers emit new versions only after downstream services are compatible.
- Unknown fields are handled per schema/format contracts.
- Never change the semantics of an active correlation ID.
- Maintain telemetry for legacy consumers that do not yet support context.
- Distinguish payload/event versions from context versions if their lifecycles differ.

When migrating from X-Correlation-ID to a new internal standard header, temporarily read both, emit a single canonical source, and measure legacy client rates before removing the alias.

## 22. Observability: From Metrics to Logs and Traces

A correlation ID is often the pivot point when an alert or metric highlights abnormal behavior.

An investigation workflow:

1. Dashboards show rising booking timeout rates.
2. Metric dimensions point to booking operations in region A.
3. Traces show the booking service waiting too long on inventory.
4. Log searches by trace/correlation ID reveal retry attempts.
5. Looking up the message ID in queue telemetry identifies backlogged events.
6. Causation ID links the message back to the originating command.
7. Business ID verifies the final booking state.
8. Reconciliation confirms whether the operation committed.

Not every request is traced due to sampling. Correlation IDs in logs can help locate operations without full traces, provided log retention and sampling policies are aligned.

### 22.1. Sampling and Correlation

If a producer trace is sampled out, a consumer may receive trace context with the sampled flag turned off. Instrumentation must respect tracing semantics; do not force the sampled flag on just because a correlation ID is needed for investigation. Retain correlation IDs in logs per policy and use tail-based sampling/error-focused capture if infrastructure supports it.

## 23. Testing Context Propagation

Context propagation must be tested at every boundary, especially across queue retries or services using different frameworks.

- **HTTP contract test:** missing/malformed/oversized inbound IDs are handled properly; downstream receives the canonical ID.
- **gRPC interceptor test:** metadata is injected/extracted accurately and deadlines propagate.
- **Trace propagation test:** valid traceparent is continued; invalid context is handled per SDK policy.
- **Message envelope test:** context serializes/deserializes without dropping or altering IDs.
- **Fan-out test:** branches keep the shared correlation ID while generating separate message/request IDs.
- **Retry test:** correlation/message IDs remain stable, attempt increments, and idempotency is enforced.
- **DLQ/replay test:** original IDs are preserved and replay metadata is added.
- **Tenant isolation test:** context cannot cause a consumer to access another tenant.
- **Security test:** tokens/PII do not appear in headers/logs/baggage.
- **Batch test:** job ID and per-item correlations are not conflated.
- **Legacy compatibility test:** messages missing fields are handled and measured.
- **Load/cardinality test:** long IDs or large metadata do not cause abnormal resource growth.

## 24. Common Design Mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Each service generates a new correlation ID | Loss of linkage across steps | Generate/validate at boundaries and propagate canonical ID |
| Using correlation ID as trace ID | Loss of span relationships and tracing semantics | Keep the two concepts separate |
| Using correlation ID for deduplication | Valid messages in the same journey get dropped | Use appropriate message IDs/idempotency keys |
| Trusting client headers without validation | Spoofed IDs, log injection, or intentional collisions | Validate, bound, and generate internal IDs at ingress |
| Not propagating across queues | Consumer logs cannot be tied to producers | Envelope/metadata contracts and interceptors |
| Generating a new ID on every retry | Hard to group failed attempts | Keep correlation; create a separate attempt ID |
| Using one request ID for all downstream calls | Cannot distinguish individual call boundaries | New request/span ID per child operation |
| Copying all HTTP headers into messages | Leaks tokens/cookies and redundant metadata | Allowlist context fields |
| Putting PII/secrets into baggage | Leakage across services/third parties | Data minimization and classification |
| Using correlation ID as a metric label | Cardinality and cost explode | Use IDs in logs/traces; keep metric dimensions bounded |
| Relying solely on correlation to understand workflows | Missing full state/parent-child relationships | Trace spans, causation, and durable workflow state |
| Dropping IDs during DLQ/replay | Loss of error-handling history | Preserve original metadata and attach replay execution ID |
| Blindly trusting tenant ID in context | Cross-tenant data access | Authenticate producers and authorize consumers |
| Propagating context without versioning | Old consumers parse incorrectly or drop metadata | Contract compatibility and phased rollouts |
| Oversized context | Header/message size, memory, and log costs spike | Allowlists, size limits, and minimal necessary metadata |

## 25. Design and Implementation Process

1. **Map the journey:** identify requests, service calls, messages, callbacks, and jobs involved in the use case.
2. **Choose ID semantics:** correlation, request, trace, span, message, causation, business, and idempotency.
3. **Define ingress policy:** who issues IDs, which headers are validated, and which boundaries are trusted.
4. **Standardize HTTP/gRPC contracts:** headers/metadata, trace context, deadlines, and allowlists.
5. **Define message envelopes:** message ID, correlation, causation, trace context, schema version, and required tenant reference.
6. **Implement middleware/interceptors:** centralized injection/extraction at gateways, clients, servers, producers, and consumers.
7. **Design async lifecycles:** fan-out, retries, DLQs, replays, scheduled jobs, and sagas.
8. **Protect trust boundaries:** authenticate producers, tenant context, callbacks, and strip secrets/PII.
9. **Standardize telemetry:** structured log fields, trace attributes, and bounded metric dimensions.
10. **Test:** contracts, propagation, retries, batches, tenant isolation, security, and load.
11. **Roll out:** measure rates of missing context, legacy consumers, and propagation failures.
12. **Operate:** dashboards, search workflows, retention, ownership, and investigation runbooks.

## 26. Well-Architected Review

| Pillar | Design Questions |
| --- | --- |
| **Reliability** | Is context preserved across retries, queues, DLQs, and replays? Does missing context halt workflows improperly? Can operations be traced after an incident? |
| **Security** | Are inbound IDs validated? Is tenant context authenticated? Are tokens/PII propagated or logged? |
| **Performance Efficiency** | Are headers/envelopes size-limited? Do context lookups/caches add latency? Does metadata bloat messages? |
| **Cost Optimization** | Are correlation IDs used as metric labels causing high cardinality? Are log/trace retention and sampling appropriate? |
| **Operational Excellence** | Is field naming consistent? Are there dashboards, search, trace links, DLQ metadata, and runbooks? |

### Acceptance Checklist

- [ ] Correlation ID, request ID, trace ID/span ID, message ID, causation ID, and idempotency key are clearly distinguished.
- [ ] A canonical correlation ID exists per journey with ingress generation/validation rules.
- [ ] HTTP/gRPC propagation has contracts, allowlists, and shared middleware/interceptors.
- [ ] W3C trace context is handled by SDKs; semantics are not manually parsed/overwritten incorrectly.
- [ ] Message envelopes/metadata retain correlation, message, and causation IDs.
- [ ] Fan-out retains a shared correlation ID while assigning distinct operation/message IDs.
- [ ] Retries preserve appropriate IDs and enforce idempotency for side effects.
- [ ] DLQ/replays store original metadata and replay execution context.
- [ ] Long-running workflows have durable state; correlation does not replace the state machine.
- [ ] Tenant context is authenticated and authorized at consumers.
- [ ] Tokens, secrets, or unnecessary PII are never propagated.
- [ ] Logs have consistent structured fields; IDs are not used as metric labels.
- [ ] Headers, baggage, and envelopes have size/cardinality limits.
- [ ] Context contracts are versioned and compatible with legacy messages.
- [ ] Tests cover HTTP, gRPC, queues, retries, batches, DLQs, replays, and third-party callbacks.
- [ ] Dashboards/alerts exist for missing context, propagation failures, and trace/log correlation gaps.

## 27. Applied Exercise

A SaaS equipment-rental platform receives create-booking requests through an API gateway. The booking service calls inventory synchronously, writes to the database, and publishes BookingCreated to a broker. Three consumers handle notifications, analytics, and auditing. The notification worker calls an external email provider; the broker may redeliver messages and route failed messages to a DLQ. Workflows occasionally need to be retried hours later.

Design:

1. Which ID types are needed and who generates each?
2. How does the gateway handle X-Correlation-ID from clients to prevent spoofing or log injection?
3. How does the booking service propagate context over HTTP/gRPC to inventory?
4. Which fields does the message envelope need so consumers preserve correlation and causation?
5. Do the three fan-out consumers share the same correlation ID or trace ID? Why?
6. When a notification message is redelivered, which IDs/attempts stay the same or change?
7. How should a DLQ replay hours later preserve original metadata and add replay metadata?
8. How is tenant reference verified at the producer and consumer?
9. Which fields must never go into baggage, headers, or logs?
10. How do you investigate from a booking timeout metric to logs, traces, messages, and the final business state?

A well-grounded design generates a canonical correlation ID at the gateway; uses the tracing SDK to propagate traceparent; assigns each HTTP request/message its own ID; keeps the correlation ID on child messages while setting causation ID to the triggering message; preserves message/idempotency semantics on retries while incrementing attempt; preserves original context on DLQ and adds a replay execution ID. Consumers still authenticate producers/tenants and never use correlation IDs to grant permissions.

**Key takeaway:** a correlation ID links a business journey across components; traces/spans capture relationships and timings of technical operations; message/request/idempotency IDs carry their own semantics. Context propagation is only reliable with clear contracts, validation, allowlists, shared middleware, and testing across both HTTP and queues. When combined with structured logs, distributed traces, and workflow state, operations teams can trace a journey without turning observability metadata into a data leak or security vulnerability.