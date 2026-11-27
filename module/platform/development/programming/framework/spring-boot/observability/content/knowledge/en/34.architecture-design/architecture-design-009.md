# Inter-Service Telemetry Contract

In a system composed of multiple Spring Boot services, a request often traverses an API gateway, order service, payment service, data stores, and asynchronous consumers. Each service can emit metrics, logs, and traces on its own, yet if every team names things, propagates context, and classifies errors differently, correlating data becomes very difficult. Traces break, dashboards cannot be compared, logs cannot be found by trace ID, and an alert meaning one thing in one service means something else in another.

A telemetry contract is the shared set of conventions that services follow when producing, propagating, and exporting observability data. This contract does not replace the business API contract. It defines how services are identified, how observation context is propagated, how operations and errors are described, metrics/logs structure, sampling policies, and protocols for sending data to the collection pipeline.

A sound contract lets operators follow an execution flow across multiple services without re-learning conventions in every repository.

## Why Is an Inter-Service Telemetry Contract Needed?

Suppose `checkout-service` calls `payment-service`, and `payment-service` emits a message so `receipt-worker` generates an invoice. If each component creates traces independently, on-call operators only see three disconnected activities. If services propagate trace context properly, spans connect into one continuous flow:

~~~text
Client
└── checkout-service: HTTP server
    └── payment-service: HTTP server
        └── payment-service: database client
        └── receipt-worker: message consumer
~~~

The contract must answer the following questions:

- Which service, instance, and environment emitted this data?
- Which context must propagate across HTTP or message brokers?
- Which spans describe server, client, producer, consumer, or internal business work?
- Which metrics share the same meaning and units across services?
- Which fields do logs need in order to correlate with traces?
- Which service makes the sampling decision and how is that decision preserved across boundaries?
- How do services and collectors agree on endpoints, protocols, authentication, and export error handling?

Without these conventions, individual services may still emit data, yet the overall system lacks a shared observability language.

## Scope and Responsibilities of the Contract

The telemetry contract should be governed as a shared platform standard, with clear ownership and versioning. Platform or observability teams typically maintain the conventions; service-owning teams implement and verify compliance.

| Contract Area | Producer Service Responsibility | Downstream Context-Receiving Service Responsibility |
|---|---|---|
| Resource identity | Attach service name, version, environment, and instance ID | Preserve the service's own identity when emitting new telemetry |
| Trace propagation | Transmit trace context over supported protocols | Continue the current trace or start a new trace when no valid context exists |
| Baggage | Propagate only approved allowlisted fields | Read and use only agreed-upon fields |
| Span semantics | Use span kinds, names, and attributes with stable semantics | Create spans at request or message ingress following the same convention |
| Metrics | Use defined names, units, instrument types, and tags | Do not reinterpret the same metric under different units or meanings |
| Logs | Emit structured logs with correlation fields | Preserve trace context during processing so logs can correlate |
| Sampling | Follow the agreed trace sampling policy | Respect the sampling decision propagated via trace context |
| Export | Send via configured protocol and endpoint | Collector ingests, authenticates, routes, and reports errors per policy |

The contract must clearly separate data allowed to cross service boundaries from service-internal data. For example, `payment-provider.request.id` may be a useful span attribute inside `payment-service`, without needing to propagate across every other service. Conversely, trace context must always propagate to maintain continuity.

## 1. Resource Identity: Consistent Service Identification

Resource attributes describe the entity emitting telemetry. All services should use the same naming scheme for identifying attributes:

| Attribute | Meaning | Example |
|---|---|---|
| `service.name` | Stable logical name of the service | `checkout-service` |
| `service.namespace` | Logical group or business domain owning the service | `commerce` |
| `service.version` | Running artifact version | `2.8.1` |
| `service.instance.id` | Unique identifier of an individual instance | `checkout-7f9c8d6b5-x2k4p` |
| `deployment.environment.name` | Deployment environment | `production` |
| `cloud.region` | Infrastructure region, if applicable | `ap-southeast-1` |

These names follow OpenTelemetry resource semantic conventions. When using Micrometer or a backend with its own conventions, attribute mapping may be needed; mappings must be standardized so dashboards still distinguish service, version, and environment.

Key principles:

- `service.name` must remain stable across deployments. Do not embed pod IDs or hostnames in the service name.
- `service.instance.id` distinguishes instances of the same service. Values must be unique over an instance's lifetime.
- `service.version` should reflect the actual running artifact, not an arbitrary constant shared across all builds.
- Environments must use canonical names, such as `development`, `staging`, `production`; avoid variants like `prod`, `prd`, `live` referring to the same environment.
- Resource attributes should be attached at SDK, registry, or export pipeline initialization rather than manually repeated on every span and log.

An illustrative service identity looks like:

~~~text
service.name = checkout-service
service.namespace = commerce
service.version = 2.8.1
service.instance.id = checkout-7f9c8d6b5-x2k4p
deployment.environment.name = production
cloud.region = ap-southeast-1
~~~

In Spring Boot, `spring.application.name` is a useful starting point for setting the application name. When integrating Micrometer Tracing, the OpenTelemetry SDK, or the Java agent, inspect actual exported resources to ensure `service.name`, version, and environment are neither missing nor overwritten by other configuration.

Never place per-request varying values such as user IDs, order IDs, or session IDs into resource attributes. Those values do not describe the service; if truly needed for investigation, place them on spans/logs under data policy and never turn them into metric dimensions.

## 2. Trace Context: Connecting an Execution Flow Across Services

### W3C Trace Context

For HTTP communication, services should standardize on W3C Trace Context. The two key headers are:

- `traceparent`: carries trace ID, parent span ID, and trace flags.
- `tracestate`: carries vendor-specific information in W3C format, if used.

Example `traceparent` header:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Components in the header tell downstream services which trace the request belongs to, which span immediately preceded it, and whether the trace is marked sampled. The receiving service creates a new span for its server boundary and parents it within the current trace.

Do not invent custom headers like `X-Trace-Id` to replace `traceparent`. A system may retain legacy compatibility headers during migration, but must clearly designate the canonical source and avoid generating two competing trace IDs. Trace IDs are managed by the tracing system; never reuse a business request ID as a trace ID.

### Context Propagation in Spring Boot

When using client builders configured by Spring Boot, instrumentation can attach Observations and propagate trace context automatically if tracing is enabled and the client is supported. Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class CatalogClientConfiguration {

    @Bean
    RestClient catalogClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

Services should inject the framework-configured builder rather than instantiating standalone clients that bypass `ObservationRegistry` or tracing customizers. For `WebClient`, `RestTemplate`, or other HTTP libraries, use the configuration and instrumentation mechanism matching your Spring Boot version.

For asynchronous calls, context must be preserved across executors, schedulers, or message brokers. Never assume trace context on the current thread automatically carries over to another thread. Use the framework's context propagation mechanisms and matching library instrumentation; test both thread-pool handoffs and message consumers.

### Message Brokers and Asynchronous Processing

When a producer sends a message, trace context must be injected into message headers. The consumer extracts context from headers and creates a consumer span linked to that trace. For certain batching or fan-in patterns, span relationships may use span links rather than forcing every message into a single parent-child chain.

~~~text
order-service
└── message producer span
    └── Kafka record headers: traceparent, tracestate

invoice-worker
└── message consumer span
    └── invoice.create Observation
~~~

Do not merely pass a trace ID as an arbitrary string. Use an appropriate propagator to preserve trace ID, parent span ID, trace flags, and required state. For messages sitting in a broker for extended periods, context may be older by the time the consumer processes it; this does not invalidate correlation, though it must be factored in when analyzing end-to-end latency.

## 3. Baggage: Propagate Only Necessary Context

Baggage is a set of key-value pairs propagated alongside trace context across service boundaries. It fits small contextual metadata that has an explicit allowlist and is useful to downstream services, such as:

- `tenant-tier` if normalized into a small number of groups.
- `region` or `sales-channel` when needed for processing and investigation.
- A sanitized classification code that is not sensitive identifying data.

Baggage is not a carrier for full request payloads. Every extra field transmitted increases header size, network overhead, and data exposure scope. Never put access tokens, emails, phone numbers, payment details, session secrets, or personal data into baggage.

Also distinguish baggage from span attributes and metric tags:

| Data Type | Scope | Usage |
|---|---|---|
| Baggage | May propagate across multiple services in a trace | Holds only small, safe, allowlisted context |
| Span attribute | Attached to a specific span | Adds detail for investigating an operation |
| Metric tag/label | Creates grouping dimensions for time series | Uses only low-cardinality, controlled values |
| Log attribute | Attached to a log event | Adds searchable details per data protection policy |

A baggage attribute can be copied onto spans or logs in downstream services, but never automatically turn every baggage key into a metric tag. Doing so can generate huge numbers of time series.

With Micrometer Tracing in Spring Boot, baggage fields to propagate and fields to inject into MDC can be configured separately. Common configuration example:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - region
      correlation:
        fields:
          - region
~~~

`remote-fields` specifies fields propagated across boundaries, while `correlation.fields` specifies fields placed in MDC for logs to consume. Exact syntax and capabilities must be checked against your application's Spring Boot/Micrometer version. Add only fields approved by both service teams and security teams.

## 4. Span Semantics: Describing Work the Same Way

A span describes an operation with start time, end time, and context. The contract should standardize:

- Span kind: `SERVER`, `CLIENT`, `PRODUCER`, `CONSUMER`, or `INTERNAL`.
- Naming rules by operation and boundary.
- Mandatory or recommended attributes.
- How error status and error types are represented.
- Parent-child relationships or span links in asynchronous processing.

Span names should be stable with low variability. For HTTP, use route templates or operation names rather than full URLs with dynamic IDs. For example, `GET /orders/{orderId}` is better than `GET /orders/ORD-948201`. For business operations, names like `payment.authorize` or `inventory.reserve` clearly describe the work.

Services should follow protocol-specific semantic conventions. For HTTP, required attributes commonly include method, route, response status code, and appropriate server/client addresses. Do not invent multiple attribute names for the same concept when semantic conventions already define a standard field.

An internal business span can be created with Micrometer Observation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class PaymentService {

    private final ObservationRegistry registry;

    PaymentService(ObservationRegistry registry) {
        this.registry = registry;
    }

    PaymentResult authorize(String paymentMethod) {
        return Observation.createNotStarted("payment.authorize", registry)
                .lowCardinalityKeyValue("payment.method", paymentMethod)
                .observe(this::authorizeWithProvider);
    }

    private PaymentResult authorizeWithProvider() {
        // Call the instrumented payment gateway.
        return new PaymentResult("APPROVED");
    }
}
~~~

This example puts `payment.method` into a low-cardinality key only when values are bounded to a small list, such as `card`, `wallet`, `bank_transfer`. Never use payment ID, transaction ID, or customer ID as a low-cardinality key. If an identifier is needed to locate a transaction in a trace, consider a high-cardinality span attribute under security and retention policies; never use it as a metric label.

A single Observation can be turned into both a metric and a span via corresponding handlers. This is multiple signals from one operation, not duplicate instrumentation. Services should avoid adding manual spans for the same call if an HTTP client or agent already emits a span at that boundary.

## 5. Metrics Contract: Names, Units, and Cardinality

Metrics are valuable when services share semantics. The contract should define:

1. Metric name and exact meaning.
2. Measurement unit, such as `seconds`, `bytes`, or `requests`.
3. Instrument type: `Counter`, `Timer`/`Histogram`, `Gauge`, or `DistributionSummary`.
4. Allowed tags, data types, and value sets.
5. Histogram buckets or percentile rules when latency comparisons are needed.
6. Aggregation rules and how missing data is interpreted.

Example metric contract for payment processing:

| Logical Metric | Meaning | Unit | Allowed Dimensions |
|---|---|---|---|
| `payment.authorization.duration` | Processing duration of one authorization | seconds | `provider`, `result`, `payment_method` |
| `payment.authorization.count` | Number of authorization attempts | requests | `provider`, `result` |
| `payment.queue.depth` | Number of queued messages waiting | messages | `queue` |

Actual emitted metric names may be normalized by Micrometer or exporters according to backend naming conventions. For example, a Micrometer metric named `http.server.requests` may be converted to Prometheus or OpenTelemetry conventions upon export. What matters is that all services agree on the same meaning, units, and dimensions; never create two differently named metrics measuring the exact same quantity and sum them in dashboards.

Cardinality is a mandatory part of the contract. If a metric has an `order_id` tag, every order can spawn a new time series. If a metric has a `result` tag with values `approved`, `declined`, `error`, series counts stay manageable. Before adding a tag, ask: is the value set finite, is there an upper bound, and is it required for dashboards or alerts?

Never use these fields as metric dimensions:

- User ID, order ID, payment ID, or session ID.
- Full URLs with dynamic path parameters.
- Exception messages or SQL queries.
- Request payloads, emails, or arbitrary client-supplied data.
- Trace ID or span ID.

Trace IDs can be used in exemplars or metric-to-trace links when supported by the backend, but not as standard metric labels.

### Histogram and SLO Conventions

When comparing latency across services, services must agree on units and how histograms are read. If `checkout` measures seconds while `payment` measures milliseconds and a dashboard treats them as the same unit, results will be wrong. If services have different latency targets, bucket boundaries may differ, provided the differences are documented.

Never add percentiles from multiple services to compute an end-to-end percentile. Percentiles are not additive. To evaluate an overall flow, use traces or metrics designed directly for the end-to-end journey; for latency distributions, use histogram buckets and appropriate aggregations.

## 6. Logs Contract: Structure and Correlation

Logs should be emitted in structured format so backends can filter and aggregate them. A minimal contract should standardize these fields:

| Field | Meaning |
|---|---|
| `timestamp` | Time of the event |
| `severity` | Log level following a shared convention |
| `body` or `message` | Human-readable content |
| `service.name` | Service emitting the log |
| `service.version` | Application version |
| `deployment.environment.name` | Environment |
| `trace_id` | Current trace ID, if present |
| `span_id` | Current span ID, if present |
| `event.name` | Stable event name, if applicable |
| `error.type` | Standardized error type, if applicable |

Exact field names depend on log format and backend. The OpenTelemetry Logs Data Model defines fields like `Timestamp`, `SeverityText`, `Body`, and `TraceId`; application JSON logs can use corresponding names. The contract should document the mapping clearly so operators never have to guess.

Logs must capture the exact context active when the event occurred. When a request runs on another thread or async consumer, MDC and trace context must be restored or propagated properly. Copying a trace ID into an unmanaged `static` field or `ThreadLocal` can cause logs to carry a prior request's trace ID or lack context altogether.

Not every log is required to carry a trace ID. Startup logs, standalone health checks, or out-of-band events may not belong to a trace. When trace context exists, logs should include both `trace_id` and `span_id` so operators can open the exact span.

Avoid logging the same error with identical stack traces at every layer if intermediate logs add no information. Agree on the layer responsible for final error logging, while other layers return errors or enrich span context. Always strip secrets, tokens, and personal data from logs.

## 7. Sampling: Keeping Traces Continuous Across Boundaries

Sampling determines which traces are kept. If every service decides independently, a trace may retain spans in the first service while losing spans in downstream services. The contract should define:

- Default sampler, such as parent-based with a configured head probability.
- Downstream services must respect the sampling flag in trace context.
- Behavior when trace context is invalid or absent.
- Cases requiring sampling adjustments, such as errors or high-value investigative flows.
- If using tail sampling, which collector receives complete spans and how long the decision wait window is.

With head sampling, decisions are typically made early at trace start and propagated via trace flags. A parent-based sampler makes downstream services honor the parent's decision. This saves resources and preserves trace completeness.

Tail sampling decides whether to keep a trace after observing multiple spans—for instance, prioritizing error traces or high-latency traces. To do so, the collector must receive related spans before deciding. Splitting a trace across independent collectors or inconsistent routing can leave tail samplers with incomplete data. The contract must specify routing and memory/wait-window limits.

Do not configure independent sampling probabilities on every service without parent-based behavior. Nor should you raise sampling to 100% in production without evaluating traffic, storage cost, and data policies.

## 8. Export Contract: Protocols, Collectors, and Security

Services should send telemetry through a centrally managed collector or gateway whenever architecture allows. Collectors can ingest OTLP, add or normalize resource attributes, scrub sensitive data, route to backends, and apply batching/retries.

The export contract must specify:

- Whether OTLP uses gRPC or HTTP/protobuf.
- Per-environment endpoints and discovery rules.
- TLS, certificates, and authentication mechanisms.
- Timeouts, batch sizes, queue limits, and retry policies.
- Behavior when the collector is unavailable.
- Routing rules by tenant, environment, or data region.
- Backend access permissions and retention policies.

Conceptual environment configuration example:

~~~text
OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-collector.internal:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_SERVICE_NAME=checkout-service
~~~

These variables are common examples for the OpenTelemetry SDK or Java agent. If an application uses Spring Boot-configured Micrometer OTLP registry/tracing exporters, property names and configuration mechanisms may differ. Do not mix two export pipelines for the same signal without an explicit design, as this can send duplicate data or produce two conflicting resource identities.

Collectors need backpressure policies. When a backend slows down or disconnects, bounded queues may fill up and telemetry will be dropped. Telemetry must never fail business requests merely because a collector is temporarily unavailable; however, drop rates and exporter health must be tracked via dedicated health metrics or logs. The contract should define acceptable data loss tolerances and alerting rules.

## 9. Compatibility and Contract Versioning

A telemetry contract also needs change-management rules. Dashboards, alerts, and queries frequently depend on metric names, tags, and span attributes; arbitrary renames can silently break observability without causing compile errors.

Classify changes into categories:

| Change Type | Example | Rollout Approach |
|---|---|---|
| Additive compatible | Adding an optional span attribute or new metric | Can ship ahead; update dashboards as needed |
| Semantic change | Changing what `result=success` means or changing metric unit | Requires versioning or a new name; never alter silently |
| Field removal | Deleting a tag currently used by dashboards | Announce, run a transition period, and audit consumers |
| Propagation change | Switching headers or propagators | Support both in parallel during migration if needed |
| Resource identity change | Renaming a service or environment label | Must update dashboards, alerts, routing, and ownership |

A safe practice is favoring additive changes: introduce the new field first, update consumers/dashboards, observe during a transition window, then retire the old field. Never repurpose an old metric name with a new meaning. When replacing a metric, mark it deprecated in documentation, provide the new metric, and publish a removal date.

Each contract should specify an owner, version, effective date, applicable service list, and changelog. Not every change requires a major version bump; what matters is identifying breaking changes and communicating them clearly.

## 10. Testing the Contract Across Services

Testing a single service in isolation does not prove propagation works end-to-end. Integration tests are needed across HTTP and messaging boundaries.

Sample test flow:

1. Send a request into `checkout-service` with a known trace context.
2. Have `checkout-service` call `payment-service` via its instrumented client.
3. Have `payment-service` publish a message and let `receipt-worker` consume it.
4. Collect spans from a test exporter or test collector.
5. Verify spans share the same trace ID, sensible parent/link relationships, and accurate service identities.
6. Verify allowlisted baggage propagates while unauthorized fields do not appear.
7. Verify metrics have contract-compliant names, units, and tags.
8. Verify logs carry `traceId`/`spanId` when execution occurs inside a trace.
9. Simulate downstream errors and verify error status, error type, and sampling behavior.
10. Verify export failures do not hang business requests indefinitely.

Key assertions go beyond "spans exist." Verify that:

- An HTTP server span is created once per receiving service.
- HTTP client spans accurately reflect outbound calls.
- Business spans have stable names and do not duplicate technical spans.
- Consumer spans link to producer context.
- `service.name`, `service.version`, and environment match each service.
- Metric tags contain no dynamic IDs.
- Logs do not leak baggage or sensitive data.
- Sampling decisions remain consistent across the entire trace.

You can use a test exporter, in-memory registry, or a collector running in the test environment. For message brokers, tests should go through a real broker or a harness preserving message headers to catch context inject/extract bugs. When upgrading Spring Boot, Micrometer, OpenTelemetry instrumentation, or Java agents, re-run contract tests because instrumentation and propagation behavior can change.

## Implementation Checklist for a Spring Boot Service

Before onboarding a service into the shared observability platform, verify:

- [ ] Service sets accurate `service.name`, `service.version`, environment, and instance identity.
- [ ] Trace propagation uses the agreed standard, preferring W3C Trace Context.
- [ ] Client builders and messaging instrumentation preserve context across services and threads.
- [ ] Baggage contains only allowlisted fields, with no secrets or personal data.
- [ ] Span names, kinds, and attributes follow protocol semantic conventions.
- [ ] Metric names, units, instruments, and dimensions match the contract.
- [ ] Metric tags contain no dynamic IDs.
- [ ] Logs are structured and correlate properly with traces whenever context exists.
- [ ] Sampling policy respects parent decisions.
- [ ] Exports use environment-appropriate endpoints, protocols, TLS, and authentication.
- [ ] Collectors/exporters have suitable timeouts, queues, retries, and drop alerts.
- [ ] Contract tests verify cross-service flows and run whenever dependencies are upgraded.

A telemetry contract only delivers value when services actually adhere to it together. Embed conventions into shared configuration, platform libraries, or service templates where appropriate, and add automated tests to catch drift early. When a service renames a metric, adds baggage, or alters propagation, review that change as an architectural change impacting system-wide observability.
