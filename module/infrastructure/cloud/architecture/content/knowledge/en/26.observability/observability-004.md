# Designing Telemetry for Distributed and Asynchronous Flows

In a cloud application, a user request is rarely processed within a single process. An API gateway may forward the request to multiple services; a service writes to a database and emits an event; a broker delivers the event to consumers; consumers call a payment service, send an email, or update a search index. Work may continue after the HTTP response is returned, be retried multiple times, fan out into multiple branches, or run on workers in another region. When a step slows down or fails, individual service logs alone usually cannot answer: where did the original request go, which step consumed the time, where did the error start, and which business flow was impacted?

**Telemetry for distributed flows** must preserve relationships between operations across process, service, and time boundaries. Traces/spans describe the path and causal relationships; metrics show trends and blast radius; logs provide event details. Context propagation passes trace context across HTTP, RPC, message brokers, job queues, and asynchronous steps. Good design must also handle retries, fan-out/fan-in, batches, sampling, cardinality, privacy, and storage costs.

This lesson belongs to the **Observability** chapter of the **CLOUD_ARCHITECTURE** module. The goal is to design telemetry from operational and business requirements to support diagnostics, SLO measurement, incident response, and cloud system optimization using Well-Architected thinking.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain why standalone logs and metrics are insufficient for following a distributed workflow.
2. Model traces, spans, parent-child relationships, and links between traces.
3. Propagate trace context across HTTP/RPC, queues, events, retries, schedulers, and batches.
4. Handle tracing for fan-out/fan-in, asynchronous continuations, and long-running workflows.
5. Correlate traces, metrics, and logs using trace IDs, span IDs, and controlled attributes.
6. Choose sampling strategies, instrumentation boundaries, and semantic attributes.
7. Design telemetry that neither exposes sensitive data nor creates uncontrolled cardinality/costs.
8. Test context propagation and use telemetry to identify bottlenecks, errors, and SLOs.

## 2. Why Are Distributed Flows Hard to Observe?

### 2.1. A Request Crosses Many Boundaries

Example of a user confirming a booking:

~~~mermaid
flowchart LR
    WEB[Web / Mobile] --> GW[API Gateway]
    GW --> BOOK[Booking Service]
    BOOK --> DB[(Booking DB)]
    BOOK --> OUT[Outbox]
    OUT --> BUS[Message Broker]
    BUS --> PAY[Payment Consumer]
    BUS --> SEARCH[Search Consumer]
    PAY --> PSP[Payment Provider]
    PAY --> MAIL[Notification Service]
    SEARCH --> IDX[(Search Index)]
~~~

A business transaction can touch multiple services, databases, and providers. Each service has its own process ID, host, log format, and clock. Events may be processed seconds or hours after the initial request. Relying solely on close timestamps or grepping by user ID is usually not enough to reconstruct the flow.

### 2.2. Patterns of Distribution

- **Synchronous call chains:** sequential HTTP/gRPC calls; latency accumulates and errors can cascade.
- **Fan-out/fan-in:** one request spawns multiple parallel branches and aggregates results.
- **Asynchronous messaging:** producer emits an event; consumer processes it later without holding an HTTP connection.
- **Scheduled/batch work:** jobs triggered on a schedule processing many records.
- **Retry/redelivery:** the same message or operation may execute multiple times.
- **Long-running workflows:** a process lasting minutes or days while waiting for callbacks.
- **Cross-region/service providers:** requests traverse networks and systems outside your control.

Each pattern has different causal relationships. Telemetry must model those relationships instead of assuming every operation is a synchronous call tree.

### 2.3. Operational Questions to Answer

| Question | Required Telemetry |
|---|---|
| Where is the request slow? | Span duration and dependency breakdown |
| Which event came from which request? | Trace context or causal link in messages |
| How many times was a message processed? | Message ID, delivery/attempt metadata, and span links |
| Where did consumer lag start? | Queue age/lag metrics, publish/consume timestamps |
| Which branch caused the workflow to fail? | Parent-child spans or linked traces, status/errors |
| Are retries helping or amplifying the incident? | Attempt counts, retry delays, error rates, and queue depth |
| Which customers are impacted by the incident? | Controlled tenant-scoped attributes, never unbounded metric labels |
| Can operations reconstruct what happened? | Structured logs, trace IDs, event/job IDs, and audits |

## 3. Three Telemetry Signals and Their Roles

### 3.1. Traces

A trace describes a unit of work across multiple components. A trace typically has a unique trace ID and multiple spans. Each span represents an operation with start/end times, attributes, events, status, and relationships to other spans.

Traces answer: **what path did an operation take and where did it spend time?**

### 3.2. Metrics

Metrics are numerical data aggregated over time, such as request rate, error rate, latency histograms, queue depth, oldest-message age, and consumer throughput. Metrics fit alerting, dashboards, and SLOs because they can be queried efficiently as time series.

Metrics answer: **how well is the system performing, what is the trend, and how many users are affected?**

### 3.3. Logs

Logs are structured events or messages with timestamps and context. Logs can record validation failure reasons, provider response codes, state transitions, or retry decisions. Logs provide detail, though they tend to cost more to store and should not replace metrics for all aggregations.

Logs answer: **what happened and what details explain the outcome?**

### 3.4. Combining the Three Signals

~~~mermaid
flowchart TD
    APP[Instrumented services] --> TRACE[Traces]
    APP --> METRIC[Metrics]
    APP --> LOG[Structured logs]
    TRACE --> TQL[Trace backend]
    METRIC --> MQL[Metrics backend]
    LOG --> LQL[Log backend]
    TQL --> CORR[Correlation / investigation]
    MQL --> CORR
    LQL --> CORR
~~~

When logs include trace ID and span ID, operators can open the related trace directly from a log. When traces include appropriate service, operation, and status fields, they can be tied back to metrics by service/environment. Correlation requires consistent schemas and IDs; simply printing free-form text in logs makes reliable querying difficult.

## 4. Traces and Spans: Core Model

### 4.1. Trace

A trace represents a meaningful unit of work, such as handling an HTTP request or executing a workflow. The trace ID is propagated across components participating in or linked to the same activity.

### 4.2. Span

A span represents an operation:

- Operation name such as POST /bookings or payment.authorize.
- Trace ID and span ID.
- Parent span ID if a parent-child relationship exists.
- Start time and duration.
- Attributes such as service, route template, dependency, status code.
- Events such as retry scheduled or validation completed.
- Status/error per instrumentation conventions.

Do not create spans for every line of code. Spans should reflect boundaries with diagnostic value: inbound requests, outbound dependency calls, significant database operations, message publish/consume, and workflow steps.

### 4.3. Span Tree for a Synchronous Request

~~~text
Trace: POST /bookings
  ├── API Gateway
  ├── Booking Service
  │    ├── validate request
  │    ├── SELECT inventory
  │    ├── INSERT booking
  │    └── publish BookingCreated
  └── response
~~~

Total trace duration shows the overall request experience; child spans show which part took time. Do not add a parent span's duration to its child spans to compute total latency, because the parent span normally encompasses child execution time.

### 4.4. Status and Errors

Spans should distinguish success; expected business errors such as validation rejections or resource not found; dependency errors such as timeouts, throttling, or connection resets; unknown system errors; and cancelled/deadline exceeded.

Do not mark every HTTP 4xx as a system error. A request rejected correctly by policy may be a normal business outcome; SLIs must reflect service semantics.

## 5. Context Propagation Across HTTP and RPC

### 5.1. What Is Trace Context?

Context propagation passes identifying info and span relationships from caller to callee. With W3C Trace Context, common headers are:

- traceparent: version, trace ID, parent span ID, and trace flags.
- tracestate: bounded vendor-specific tracing state.

Illustrative example:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

The receiver extracts context to create a server span in the same trace whose parent is the client-side span per the propagation model. Instrumentation must standardize headers; never assemble trace IDs with manual string parsing in business code.

### 5.2. W3C Trace Context and OpenTelemetry

OpenTelemetry (OTel) provides APIs/SDKs and instrumentation to create, propagate, and export telemetry. W3C Trace Context is a widely supported propagation standard. Propagator configuration must be consistent across services; if one service only understands a proprietary format, traces can break.

### 5.3. Inbound and Outbound Instrumentation

A service typically needs to:

1. Extract context from inbound requests.
2. Create a server span with a route template and appropriate attributes.
3. Set the active context in the execution scope.
4. When calling another service, create a client span and inject context into the outbound request.
5. End spans across all success/error/cancel branches.

Do not put full URLs with query strings containing tokens or user data into span names/attributes. Use route templates such as /customers/{customerId} instead of concrete paths to avoid PII and high cardinality.

### 5.4. Conceptual Instrumentation Example

~~~typescript
import { trace, SpanStatusCode } from "@opentelemetry/api";

const tracer = trace.getTracer("booking-service");

async function loadBooking(bookingId: string) {
  return tracer.startActiveSpan("booking.load", async (span) => {
    try {
      span.setAttribute("app.operation", "booking.load");
      const booking = await repository.findById(bookingId);
      if (!booking) {
        span.setAttribute("app.result", "not_found");
        return null;
      }
      return booking;
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}
~~~

This example only illustrates the API. Production systems must control attribute types, exception redaction, semantic conventions, async context managers, and avoid recording sensitive IDs without clear justification.

## 6. Propagation Across Message Brokers and Events

### 6.1. HTTP Response Ends While Workflow Continues

When a producer publishes a message, the HTTP request may finish before the consumer starts processing. Context must be placed into message metadata/headers so the consumer can link causality back to the producer.

~~~mermaid
sequenceDiagram
    participant API as Booking API
    participant DB as Booking DB
    participant Q as Message Broker
    participant C as Payment Consumer
    participant PSP as Payment Provider
    API->>DB: Commit booking and outbox
    API->>Q: Publish event + trace context
    API-->>API: HTTP response completed
    Q->>C: Deliver event + context
    C->>PSP: Authorize payment
    PSP-->>C: Authorization result
~~~

### 6.2. Attaching Context to Messages

With brokers supporting headers/metadata, the producer injects propagation fields into the message. The consumer extracts context upon receipt. Do not embed context into the business payload if the broker offers dedicated metadata; if the event format requires an envelope, clearly separate application schema from tracing metadata.

Example message structure:

~~~json
{
  "eventId": "evt_913",
  "eventType": "BookingCreated",
  "tenantId": "tenant_7f31",
  "bookingId": "booking_42",
  "occurredAt": "2026-11-18T09:00:00Z",
  "traceContext": {
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
  }
}
~~~

If broker metadata is used, traceContext in the body here is only illustrative of an envelope. Do not let downstream services trust trace context supplied directly by a tenant/client unless the producer has authenticated or sanitized it.

### 6.3. Consumer Spans

Consumers typically create a span representing message processing, recording attributes such as messaging system, destination, operation, protected message ID, delivery attempt, and processing result. Record both processing duration and queue age/lag; they are distinct quantities:

- Processing duration: time the consumer spends processing the message.
- Queue age: time from when the message was created/published until processing begins.

A consumer processing in 20 ms while messages wait 30 minutes is still a business latency problem.

### 6.4. Acknowledgment and Span Lifetime

Message-processing spans normally end when the consumer finishes processing and acks/nacks per application semantics. If work continues to another worker, create a span for the new step and propagate/link context forward. Do not keep a span open for hours while a job waits on a schedule; persist correlation metadata and start a new span when resuming.

## 7. Parent-Child or Span Links in Asynchronous Flows?

### 7.1. Causal Relationships Differ from Synchronous Calls

Parent-child represents a child span created within the scope of a parent operation. For message queues, a consumer span can be a child of the producer span if semantics and trace duration fit. However, in many event systems, an event is processed independently, aggregated from multiple sources, or triggers multiple consumers. Span links can express causal relationships without forcing everything into a single tree.

### 7.2. When to Use Span Links?

- A batch consumer processes multiple messages arriving from multiple traces.
- A job is triggered by multiple events.
- Fan-in aggregates results from multiple workflows.
- A scheduled job resumes work that previously recorded a correlation ID.
- A new trace is created for a long-running process but needs a reference to the original trace.

### 7.3. Fan-Out / Fan-In Example

~~~mermaid
flowchart TD
    ROOT[Order accepted trace] --> A[Inventory event]
    ROOT --> B[Payment event]
    ROOT --> C[Notification event]
    A --> D[Inventory consumer trace]
    B --> E[Payment consumer trace]
    C --> F[Notification consumer trace]
    D --> G[Order completion workflow]
    E --> G
    F --> G
~~~

In practice, each branch can be its own trace linking back to the source event/trace; the completion workflow links to the completed branches. This prevents a single trace from living too long or containing an unbounded number of spans.

### 7.4. Choosing a Consistent Model

Define rules for each message type: does the consumer inherit the parent trace or start a new trace; when processing a batch, does it link to all producer spans or just a correlation object; do retries stay in the same trace, start a new trace, or create new spans linked to prior attempts; how long do workflow continuations retain original trace context; when an event is manually replayed, does it start a new trace linked to the original event?

There is no single optimal approach. The goal is preserving meaningful causal relationships while bounding trace size, lifetime, and cost.

## 8. Retries, Redelivery, and Idempotency

### 8.1. Every Attempt Is a Meaningful Span

Retries can occur in SDKs, services, brokers, or workflow engines. Telemetry should capture attempt number, delay, retry reason, and outcome. If the same message is redelivered multiple times, logs/traces must distinguish delivery attempts from the business operation ID.

~~~text
Trace / linked operation: payment.authorize
  ├── attempt 1: timeout
  ├── retry delay: 2s
  ├── attempt 2: provider 503
  └── attempt 3: success
~~~

Do not create an endless loop of child spans inside one trace for retries spanning many hours. Create a new trace for each delivery/attempt linked back to the original operation; retain a stable operation ID for investigation.

### 8.2. Distinguishing Request ID, Message ID, and Idempotency Key

- Request ID: identifies a single request reception at an edge/service.
- Message/event ID: identifies a specific message in a broker/event stream.
- Business operation ID: identifies a business intent across multiple attempts.
- Idempotency key: lets consumers/providers detect duplicate operations and prevent repeated side effects.
- Trace ID: identifies a unit of telemetry; should not be used as a business primary key.

These IDs serve different purposes. Never replace an idempotency key with a trace ID because retries may create new traces while still representing the same business operation.

### 8.3. DLQ and Replay

When a message exceeds its retry policy, it can be routed to a dead-letter queue. Traces/logs should record the reason, attempt count, original topic, age, and operation ID. Replays should be marked as distinct operational actions, generating new telemetry linked to the original message/trace.

Avoid logging full sensitive message payloads in spans or logs. Use message IDs, schema versions, and redacted fields.

## 9. Fan-Out, Fan-In, and Batch Processing

### 9.1. Fan-Out

A service spawns multiple parallel tasks. Child spans can be created per dependency when branch counts are bounded and diagnostically valuable. If there are thousands of items, do not create thousands of granular spans in every production trace; consider aggregate attributes, event counts, sampling, or per-chunk traces.

### 9.2. Fan-In

An aggregation step waits for multiple results. The aggregator span should record expected/completed/failed branch counts, longest wait time, timed-out/cancelled branches, aggregated outcome, and partial success policy. Use span links to connect multiple sources when branches are independent traces.

### 9.3. Batch Consumers

A consumer may pull a batch of messages from multiple traces. Do not assign the first message's parent as the parent of the whole batch, as that misrepresents causality. Create a batch-processing span and link to selected producer contexts; if link counts are very large, keep correlations in a controlled batch manifest/log and limit sampling.

### 9.4. Scheduled Jobs

Recurring jobs may have no parent request. Start a root span for each run, recording schedule name, run ID, scheduled time, start delay, batch size, and result. If the job resumes an earlier workflow, add links to source operations/events. Do not use the job name as a unique ID since individual runs must be distinguishable.

## 10. Long-Running Workflows and Context Persistence

### 10.1. Do Not Hold Execution Context Over Long Durations

A workflow may wait hours for approvals, callbacks, or partner responses. Holding thread-local/async contexts or open spans during this time causes resource leaks and excessively long traces.

Instead:

1. At start, persist the operation ID and necessary trace context in workflow state using a clear schema.
2. End the current span once that step finishes.
3. When the workflow resumes, start a new trace/span.
4. Add a span link back to the saved context if still relevant.
5. Record workflow execution ID, step name, and attempt number.

### 10.2. Selective Context Persistence

Persist only the fields needed to link telemetry, typically traceparent/tracestate or standardized trace ID/span ID along with an expiry. Do not persist full request headers, as they may contain cookies, tokens, and PII.

### 10.3. Expired Context

If the original trace has passed retention or is no longer kept by the backend, operations still need logs/metrics for the new run. A stable business correlation ID keeps executions linked even after old traces expire from the trace backend.

## 11. Correlation Across Traces, Logs, and Metrics

### 11.1. Structured Logs

~~~json
{
  "timestamp": "2026-11-18T09:00:02.120Z",
  "severity": "ERROR",
  "service.name": "payment-consumer",
  "message": "payment authorization timed out",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "operation_id": "payop_913",
  "event_id": "evt_913",
  "attempt": 2,
  "error.type": "TimeoutError"
}
~~~

This example contains placeholder IDs only. Do not log payment instruments, access tokens, or full payloads. Trace ID/span ID fields should be pulled from the active context by logging instrumentation to prevent mismatches.

### 11.2. Metrics and Trace Exemplars

Histogram metrics can link selected observations to trace exemplars. When spotting an anomalous latency bucket, operators can open a representative trace to inspect detailed spans. Exemplars require proper sampling and label policies; never attach trace IDs as metric labels on every measurement, as cardinality will grow unboundedly.

### 11.3. Correlation IDs Do Not Replace Traces

Business correlation IDs can persist long-term and connect multiple traces, such as booking IDs or workflow IDs. Trace IDs fit specific telemetry traces. Sensitive business IDs must be governed and kept out of metric labels.

## 12. Semantic Conventions and Span Attributes

### 12.1. Use Consistent Names and Attributes

OpenTelemetry semantic conventions define common attribute/operation names for HTTP, RPC, databases, messaging, and runtimes. Following conventions lets queries and dashboards work across languages, SDKs, and backends.

### 12.2. Prefer Low-Cardinality Attributes

Good attributes typically include service.name, service.version, deployment.environment, HTTP method, route template, response status code, messaging system, destination name and operation, database system and operation, error type, and outcome.

Avoid using raw URLs, user emails, request IDs, message IDs, arbitrary tenant IDs, or SQL literals as metric dimensions. Some IDs may be useful in traces/logs, subject to sampling, redaction, and access controls.

### 12.3. Do Not Capture Arbitrary Payloads

Message bodies, HTTP headers, SQL statements, and exception messages can contain PII, tokens, payment data, or secrets. Capture only necessary fields; redact headers; use attribute allowlists; enforce size limits; restrict telemetry access; and configure retention.

## 13. Sampling for Distributed Traces

### 13.1. Head Sampling

A head sampler decides whether to keep a trace at its start, before knowing the final outcome. It is cheap and reduces export/storage load, but can miss error traces if the drop decision was made at the root.

### 13.2. Parent-Based Sampling

A parent-based sampler normally inherits the sampling decision from its parent so services in the same trace make consistent choices. Inconsistent configuration produces broken traces: service A exports while service B does not, or vice versa.

### 13.3. Tail Sampling

A tail sampler decides after receiving a trace's spans, allowing retention of error traces, slow traces, or traces with notable attributes. It requires collectors to buffer trace data in memory/buffers long enough, increasing capacity, network, and operational demands. In distributed environments, spans must be routed by trace ID to the same tail-sampling decision point or equivalent mechanism.

### 13.4. Suggested Sampling Policy

| Trace Type | Policy to Consider |
|---|---|
| Normal high-volume requests | Percentage-based head sampling |
| Errors/exceptions | Tail sampling prioritizing retention |
| Latency exceeding threshold | Tail sampling or latency-aware policy |
| Security-sensitive operations | Policy-driven sampling/auditing; never replaces mandatory audit logs |
| Debugging specific tenant/operation | Temporary targeted sampling with approval and expiry |

Sampling is neither a security control nor an audit-completeness guarantee. Mandatory compliance events require separate log/audit mechanisms with guaranteed retention.

## 14. Telemetry Pipeline and OpenTelemetry Collector

### 14.1. Decoupling Instrumentation from Backends

Applications instrument with OTel APIs/SDKs and export via OTLP to a Collector or backend. The Collector can receive, batch, enrich, filter, redact, sample, and route telemetry.

~~~mermaid
flowchart LR
    S1[Service A] --> OTEL[OTel Collector]
    S2[Service B] --> OTEL
    W[Async Worker] --> OTEL
    OTEL --> PROC[Batch / filter / redact / sample]
    PROC --> TR[Trace backend]
    PROC --> ME[Metrics backend]
    PROC --> LO[Log backend]
~~~

### 14.2. Collector Deployment

- Agents/sidecars or daemonsets work well for gathering telemetry close to workloads.
- Gateway collectors can centralize batching, tail sampling, and routing.
- Multi-tenant environments require auth, tenant isolation, and quotas at the collector.
- Collectors need resource limits, queues/buffers, and export retries.
- Telemetry pipelines must observe themselves: dropped spans, queue sizes, exporter errors, and memory pressure.

### 14.3. Backpressure and Telemetry Loss

When backends slow down, collector queues can grow and fill up. Decide on in-memory vs. persistent queues; retries and exponential backoff; batch sizes and timeouts; overload drop policies; priority for critical telemetry; and alerts on dropped spans/logs/metrics.

Never let telemetry crash business workloads. Exports should be non-blocking with bounded resources; telemetry may degrade gracefully during crises, but must emit metrics indicating data is being dropped.

## 15. Security and Privacy in Propagation

### 15.1. Trace Context Is Metadata, Not Credentials

Traceparent does not prove caller identity and grants no access rights. Never use a trace ID as an access token, authorization key, or proof of user identity.

### 15.2. Baggage

Baggage can propagate key-value context across services, such as tenant tier or workflow class. Baggage can spread across many dependencies and external services, increasing header size and data exposure risk. Only propagate allowlisted, low-sensitivity fields with size limits and expiries. Never put emails, access tokens, payment IDs, or PII into baggage.

### 15.3. External Boundaries

When calling payment providers or third-party webhooks, consider omitting internal context or sensitive baggage. Create an internal outbound span, send only agreed-upon correlation headers, and use trace links when callbacks return. Sanitize inbound external context and never let callers dictate sampling priority/trust flags.

### 15.4. Multi-Tenant Telemetry

In SaaS, telemetry may carry tenant metadata. Define who may view traces/logs, whether cross-tenant queries are prevented, retention per plan, and whether tenants can export telemetry. Use tenant attributes in traces when needed for investigation, but avoid creating per-tenant metric series if tenant counts are large.

## 16. Testing Context Propagation

### 16.1. Per-Protocol Tests

- Inbound/outbound HTTP extracts/injects traceparent properly.
- RPC metadata carries context accurately across client/server.
- Message producers write context into headers/metadata.
- Consumers extract context and create spans/links.
- Retries have defined attempts and parent/link semantics.
- Batches/fan-in do not assign wrong parents.
- Scheduled jobs start root spans or link to prior operations properly.
- Context does not leak across concurrent requests within the same process.

### 16.2. Integration Tests

Create a test workflow spanning API, broker, and consumer. Verify trace IDs connect per policy; message IDs and operation IDs match; span end/status are accurate; retries are represented; and no secrets/PII appear in attributes.

### 16.3. Load and Failure Tests

Test slow collectors, broker redelivery, consumer restarts, large message batches, high trace sampling, network partitions, and down export backends. Measure CPU/memory/network overhead, dropped telemetry, and business request latency.

## 17. End-to-End Example: Booking Creating Asynchronous Payment

### 17.1. Business Flow

1. Booking API receives the request and creates a root/server span.
2. The API commits the booking along with an outbox event.
3. The publisher reads the outbox, creates a publish span, and injects trace context.
4. The broker persists the message; the HTTP request may have already completed.
5. The payment consumer receives the message, extracts context, and creates a consumer span.
6. The consumer calls the payment provider, recording a child span and outcome.
7. On transient errors, retries are recorded by attempt; the operation ID stays stable across attempts.
8. On completion, the consumer emits a PaymentAuthorized/PaymentFailed event.
9. The notification worker receives the event and sends notifications; trace links show the relationship to the payment operation.

### 17.2. Illustrative Trace Model

~~~text
Trace A: POST /bookings
  ├── booking.create
  ├── db.transaction
  └── outbox.publish
       +--> message trace context

Trace B: payment.consume (linked to Trace A)
  ├── payment.authorize attempt=1 [timeout]
  └── payment.authorize attempt=2 [success]

Trace C: notification.consume (linked to PaymentAuthorized)
  └── email.send
~~~

Independent traces bound lifetime and size. Business operation IDs and event IDs connect the workflow; span links capture causal relationships. Even if a system chooses parent-child across a broker for short workflows, it must still define trace limits and redelivery handling.

### 17.3. Accompanying Metrics

- booking_create_duration and booking_create_errors.
- outbox_publish_lag.
- payment_queue_oldest_message_age.
- payment_consumer_processing_duration.
- payment_retry_total by reason class.
- payment_authorization_success_rate.
- notification_delivery_failures.
- Collector dropped spans/export failures.

Metric labels should be service, operation, region, status class, or fixed topic. Never add bookingId/messageId as labels.

### 17.4. During an Incident

If a customer reports a booking was created without receiving payment confirmation:

1. Search by permitted booking/workflow correlation ID.
2. Open the create-booking trace to verify outbox publishing.
3. Check queue age/lag and consumer health.
4. Open the payment consume trace and attempts.
5. Query structured logs by trace/span/event ID.
6. Identify whether the failure is provider, retry, DLQ, or notification.
7. Reconcile business state in the system of record; never infer payment state from traces alone.

Telemetry aids investigation; the database/ledger remains the source of truth for transaction state.

## 18. Common Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Relying solely on timestamps to join logs | Clock skew and concurrent traffic cause wrong conclusions | Trace context and correlation IDs |
| Not injecting context into messages | Traces break at the broker | Propagation via headers/metadata |
| Attributing a consumer batch to the first producer | Wrong causal relationships | Batch spans with span links |
| One trace spanning multiple days | Huge traces, high memory usage, slow queries | New traces per execution linked to the original workflow |
| Using trace ID as an idempotency key | Retries can create duplicate operations or wrong semantics | Separate business operation ID/idempotency key |
| Logging full headers/message payloads | Leaks tokens, PII, and secrets | Allowlists, redaction, and size limits |
| Using tenant/user ID as metric labels | Unbounded cardinality growth | Aggregate metrics; detailed IDs in access-controlled traces/logs |
| Head sampling dropping error traces | No evidence for rare incidents | Tail sampling or error-aware sampling |
| Inconsistent sampler configs across services | Missing spans or inconsistent traces | Parent-based policy and shared configuration |
| Blocking collector exports | Telemetry increases latency or crashes apps | Async exports, queues, backpressure, and resource limits |
| Not measuring dropped spans | Dashboards miss data silently | Collector self-observability and alerts |
| Using tracing instead of auditing | Critical events get sampled/dropped | Separate audit logs with completeness/retention policies |

## 19. Well-Architected Review

| Pillar | Questions | Measures and Trade-Offs |
|---|---|---|
| **Operational Excellence** | Can requests/events be traced across services, retries, and workflows? | OTel conventions, trace/log correlation, runbooks; requires maintaining propagation contracts |
| **Security** | Can telemetry carry secrets, PII, or untrusted caller context? | Allowlists, redaction, access control, baggage policies, and retention |
| **Reliability** | Does collector/backend downtime impact the application? | Async exports, bounded buffers, retries, and drop alerts |
| **Performance Efficiency** | Do instrumentation and sampling have acceptable overhead? | Meaningful spans, sampling, batch exports, and cardinality control |
| **Cost Optimization** | Are too many traces/logs stored or containing high-cardinality attributes? | Intentional tail/head sampling, retention tiers, and aggregation |
| **Sustainability** | Is redundant telemetry emitted or oversized payloads transmitted unnecessarily? | Selective instrumentation, compact attributes, and sampling |

Telemetry design must balance visibility with resources and privacy. Losing traces must never halt business processing; conversely, dropped telemetry must be detected so operations teams do not misread incomplete dashboards.

## 20. Applied Exercises

### Exercise A — Trace Broken at Queue

The Booking API has complete traces, but Payment Consumer always starts a new trace unrelated to the initial request.

**Question:** What component is missing?

**Hint:** The producer has not injected trace context into message metadata or the consumer is not extracting it. Define a propagation contract for the broker and verify with an integration test.

### Exercise B — Multi-Source Batch

A worker batches 500 events from many traces and processes them together.

**Question:** Should the first event's producer span be set as the parent for the batch span?

**Hint:** No, because the events have multiple causal origins. Create a batch-processing span and link to appropriate producer contexts; cap the number of links and keep a batch manifest if needed.

### Exercise C — Multi-Hour Retries

A payment message retries over 12 hours, with each attempt adding spans to the same trace.

**Question:** What is the impact and alternative design?

**Hint:** The trace becomes too long/large, hard to retain and query. Create traces per delivery/workflow step, link to the original operation, and keep the business operation ID and attempt metadata.

### Exercise D — Metric Cardinality

A dashboard creates metric labels for bookingId and tenantId on every request.

**Question:** What is the issue and alternative?

**Hint:** Cardinality and costs explode. Use bounded labels like service, route, region, and status class; investigate specific IDs via access-controlled traces/logs.

### Exercise E — Collector Outage

The collector gateway queue fills up and exports slow down; application latency begins rising.

**Question:** What needs to be checked and changed?

**Hint:** Check whether exports are blocking, queue limits/backoff, memory pressure, and dropped telemetry. Switch to non-blocking exports, set resource limits, batch, and alert on drops.

### Exercise F — Trace Exposing Data

HTTP spans record the full URL query string, including emails and access tokens.

**Question:** At which layers should this be fixed?

**Hint:** Block capturing raw URLs/queries/headers, use route templates, apply redaction in instrumentation and collectors, review retention/access; rotate tokens if credentials were exposed.

## 21. Production Readiness Checklist for Distributed Telemetry

- [ ] Synchronous, messaging, retry, batch, fan-out, and long-running workflow flows are modeled.
- [ ] Instrumentation boundaries are clear for inbound/outbound requests, databases, publish/consume, and jobs.
- [ ] Context propagation is standardized across services using W3C Trace Context or a published contract.
- [ ] Producers inject and consumers extract context via headers/metadata; caller context is never blindly trusted.
- [ ] Parent-child and span link rules are defined for events, fan-in, batches, and workflow continuations.
- [ ] Request ID, trace ID, span ID, message ID, and business operation ID have distinct roles.
- [ ] Retries/redeliveries capture attempt, reason, delay, and trace relationships clearly.
- [ ] Long-running workflows persist minimal context with expiry and start new traces on resume.
- [ ] Logs have structured fields and trace/span correlation; payloads/secrets are redacted.
- [ ] Metrics use low-cardinality labels and cover queue age/lag, throughput, errors, and retries.
- [ ] Sampling policy is consistent; error/slow traces are retained per targets.
- [ ] Collectors have batching, queuing, retries, backpressure, resource limits, and self-observability.
- [ ] Telemetry export never blocks critical paths or crashes applications.
- [ ] Baggage and external boundaries have allowlists, size limits, and privacy reviews.
- [ ] Multi-tenant trace/log access, retention, and tenant metadata are controlled.
- [ ] Tests cover HTTP/RPC/broker propagation, fan-out/fan-in, batches, and retries.
- [ ] Failure/load tests cover collector/backend outages and measure overhead.
- [ ] Dashboards connect traces, metrics, and logs; alerts detect dropped telemetry.
- [ ] Audit/compliance events use dedicated mechanisms when completeness is required.
- [ ] Runbooks guide investigations by operation ID, event ID, trace ID, and authoritative business sources.

**Key takeaway:** telemetry for distributed systems must preserve causal relationships when work leaves the originating process. Trace context connects operations; span links express asynchronous and fan-in relationships; operation/message IDs track business flows and deliveries; metrics measure health; logs explain details. When propagation, sampling, privacy, and collectors are designed intentionally, operations teams can pinpoint bottlenecks and errors across services without turning telemetry into a performance, cost, or sensitive-data risk.
