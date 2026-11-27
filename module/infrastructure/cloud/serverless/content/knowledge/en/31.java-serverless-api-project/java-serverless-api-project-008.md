# Adding Telemetry and Evaluating Cost per Request

## Learning Objectives

After this lesson, you will be able to:

- Explain why a Java serverless API needs to measure requests, dependencies, retries, bytes transferred, and execution duration.
- Distinguish metrics, structured logs, and distributed traces; choose the right signal for each operational question.
- Design route- and outcome-based telemetry with controlled cardinality.
- Instrument Java handlers and use cases with Micrometer and OpenTelemetry.
- Track cold starts, latency, errors, concurrency, downstream calls, payload bytes, and retries.
- Build a per-request cost model covering function compute, invocations, API gateway, database, networking, and observability.
- Allocate shared costs to services or workloads using explainable drivers.
- Calculate cost per attempted request and cost per successful request, and use those metrics to prioritize optimizations.
- Design dashboards, alerts, and workflows to reconcile telemetry against billing exports.

## 1. Why Do Serverless APIs Need Telemetry and Unit Economics?

A serverless API scales automatically with requests, but scaling alone does not explain what happens inside each request. An endpoint may be slow due to cold starts, database queries, partner API calls, retries, or serializing large payloads. Bills can rise even when request volume stays nearly flat because execution duration grew, downstream calls multiplied, data transfer increased, or logging became overly verbose.

Telemetry provides the data to answer:

- Is the API meeting latency targets?
- Which routes generate the most errors or retries?
- How much time does the function spend in cold starts versus warm executions?
- Which dependency accounts for most of a request's duration?
- How many bytes does each request transfer?
- Did costs rise due to traffic, errors, or an architectural change?
- How much does one successful business transaction actually cost?

Unit economics translates total spend into a unit meaningful to the product. For an API, that unit might be an accepted request, a successfully completed request, a created order, or a processed task.

### 1.1. Invocation Does Not Equal Business Request

One HTTP request can trigger multiple function invocations if the system retries or fans out. Conversely, one function invocation may process a batch of multiple messages or operations.

Distinguish clearly between:

| Concept | Meaning | Example |
|---|---|---|
| Client request | Call from a client to the API | Client sends POST /orders |
| Function invocation | One runtime execution of a function | Lambda/function handler runs |
| Attempt | One try at processing an operation | Initial attempt and subsequent retries |
| Dependency call | Outbound call from the function to another service | Database query or payment API call |
| Successful operation | Business outcome completed properly | An order created and committed |
| Billable unit | Unit metered by the provider | Request, GB-second, GB transferred, or log ingestion |

Never use invocation count as the sole denominator for every measurement. If one invocation processes a batch of 100 messages, cost per invocation and cost per message answer two different questions.

### 1.2. Telemetry Must Align with Business Behavior

Measuring HTTP status codes alone is insufficient. For instance, an API may return 200 while queuing part of the business work for later processing. In that case, distinguish an accepted request from a completed operation.

Define explicit outcome names:
- `accepted`: the API confirmed receipt of the request.
- `succeeded`: business processing completed.
- `rejected`: request was invalid or unauthorized.
- `failed`: processing failed.
- `retrying`: operation is being retried.

Names and definitions must stay consistent across metrics, logs, traces, and dashboards. Never label an accepted state as success if the product needs to track asynchronous outcomes through the end of the workflow.

### 1.3. Full-Request Observability Model

~~~mermaid
flowchart LR
    A[Client] --> B[API Gateway]
    B --> C[Java Function]
    C --> D[Database]
    C --> E[Payment API]
    C --> F[Queue]
    C --> G[Logs / Metrics / Traces]
    G --> H[Dashboard and Cost Model]
~~~

A single request can incur charges at multiple points. Telemetry must capture the request at the entry point, key dependencies, and final outcome. Billing exports report actual cost by SKU/resource; application telemetry explains which workload drove that usage.

## 2. The Three Core Signals: Metrics, Logs, and Traces

The three telemetry signals complement one another; they do not replace one another.

| Signal | Question Answered | Examples |
|---|---|---|
| Metrics | What is trending up or down over time? | Request rate, error rate, p95 latency |
| Structured logs | What happened during a single execution? | Validation failed, payment timeout |
| Distributed traces | Where did time go across components? | Gateway → function → database → payment API |

### 2.1. Metrics

Metrics are numerical measurements aggregated over time. For a serverless API, foundational metrics include:

- Request count by route, method, and outcome.
- Request duration histograms and p50/p95/p99.
- Error count by error category or dependency.
- Concurrent executions and throttled requests.
- Cold start count/duration when provided by the platform.
- Downstream latency, timeouts, and retry counts.
- Request/response payload bytes.
- Queue age, batch size, and redeliveries when the API triggers async work.

Use histograms/distributions to observe percentiles. Average latency can hide a subset of very slow requests. Choose buckets aligned with SLOs—for example 50 ms, 100 ms, 250 ms, 500 ms, 1 s, and 2 s—and tune them to real targets.

### 2.2. Structured Logs

JSON-formatted logs simplify querying and aggregation. A record can contain:

~~~json
{
  "timestamp": "2026-11-17T10:15:30.125Z",
  "level": "INFO",
  "service": "orders-api",
  "environment": "production",
  "route": "POST /orders",
  "outcome": "succeeded",
  "status_code": 201,
  "duration_ms": 84,
  "request_id": "req-7f21",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "dependency_calls": 2,
  "retry_count": 0,
  "request_bytes": 420,
  "response_bytes": 180
}
~~~

This is a structural example, not a mandatory schema. Logs must aid investigation while avoiding tokens, passwords, secrets, payment data, or personal payloads. Log only approved identifiers with appropriate retention windows.

### 2.3. Distributed Traces

Traces follow a request across multiple components. Each span represents a unit of work: receiving the HTTP request, reading the database, calling the payment API, or publishing a message.

~~~mermaid
flowchart TD
    A[HTTP server span] --> B[Validate and map]
    B --> C[CreateOrder use case]
    C --> D[Database span]
    C --> E[Payment API span]
    C --> F[Publish event span]
~~~

Traces separate function execution time from downstream wait time. If a function takes 900 ms while the database span is 40 ms and the payment span is 700 ms, the team has a clear investigative lead.

Use W3C Trace Context (`traceparent`) or a platform-supported propagation format to carry trace context across HTTP and messages. When a message is processed asynchronously, the consumer can start a new trace linked to the original trace via a span link if the relationship is not a standard parent-child call.

### 2.4. Do Not Turn Every Telemetry Dial to Maximum

Logs and traces incur costs too. Logging full payloads, running continuous debug logs, or tracing 100% of traffic can inflate bills rapidly. Choose telemetry levels by investigative value:

- Metrics can be collected continuously with controlled cardinality.
- Logs record meaningful events with sampling or per-environment retention.
- Traces are sampled strategically, increasing sampling for errors or slow requests if the backend supports tail sampling.
- Debug logs are enabled only temporarily, with an explicit owner and turn-off time.

## 3. Designing Telemetry for a Java Serverless API

Before writing instrumentation, define a consistent set of metrics and attributes. Use route templates instead of full URLs so each resource ID does not spawn a separate time series.

### 3.1. Suggested Metric Catalog

| Metric | Type | Safe Attributes | Purpose |
|---|---|---|---|
| `api.server.requests` | Counter | route, method, outcome | Request volume |
| `api.server.duration` | Histogram | route, method, outcome | Latency and SLOs |
| `api.server.request.bytes` | Distribution | route | Inbound payload size |
| `api.server.response.bytes` | Distribution | route | Outbound payload size |
| `api.dependency.duration` | Histogram | dependency, operation, outcome | Downstream latency |
| `api.dependency.calls` | Counter | dependency, outcome | Fan-out and errors |
| `api.retry.attempts` | Counter | dependency, reason | Retry amplification |
| `api.cold_start` | Counter | runtime, function | Cold start frequency |
| `api.concurrent.executions` | Gauge/provider metric | function, environment | Capacity |
| `api.business.operations` | Counter | operation, outcome | Business outcomes |

Metric names are illustrative. If adopting OpenTelemetry semantic conventions or your organization's Micrometer conventions, standardize on one convention instead of emitting two overlapping sets.

### 3.2. Label Cardinality

Every unique combination of labels can create a distinct time series. Never use unbounded values as labels:

- Never use `request_id`, `trace_id`, email, user ID, or order ID as metric labels.
- Never use full URLs containing path parameters.
- Never use free-form exception messages.
- Never use raw SQL or tenant-varying hostnames.

Use route templates like `/orders/{orderId}` or route names like `orders.get`. Unique identifiers belong in controlled traces or logs, not metric labels.

### 3.3. Consistent Outcome Classification

Avoid lumping all 4xx and 5xx responses into a single outcome if you need diagnostic clarity. Use low-cardinality buckets:

- `success`
- `client_error`
- `server_error`
- `timeout`
- `throttled`

Depending on the API, `401` or `403` may be expected security outcomes while `429` requires separate tracking. Define SLOs around product behavior, not solely HTTP status classes.

### 3.4. Measuring the Request Lifecycle

Start a timer at the entry point and stop it once the response or invocation outcome is determined. Also measure major segments:
- Authentication and authorization.
- Parsing and validation.
- Application use case.
- Database queries and transactions.
- External APIs.
- Serialization and response writing.

Never sum parallel span durations as if they were sequential. Request wall-clock duration and total dependency duration are distinct quantities.

### 3.5. Measuring Bytes and Call Counts

Payload bytes reveal oversized requests, response bloat, and rising egress. Counting dependency calls catches N+1 queries and growing fan-out.

Application-layer measurements capture logical payloads; billing may add headers, protocol overhead, retransmissions, or other traffic classes. Reconcile application byte metrics with network/billing metrics rather than assuming they are identical.

### 3.6. Cold Starts and Warm Executions

Cold starts typically encompass runtime initialization, artifact loading, framework startup, and client creation. Platforms may expose dedicated metrics; prefer provider metrics as the canonical source when available.

You can track the first invocation inside an execution environment using diagnostic state, but never treat it as an exact billing definition. A static flag observes only the lifecycle of the instance visible to your code; platforms may meter initialization differently.

### 3.7. Retries and Fan-Out

Record attempt counts inside dependency adapters or retry wrappers, not solely at the function handler. If an SDK retries automatically, enable instrumentation/interceptors to count real attempts.

For a request calling multiple dependencies, record:
- Normalized dependency name.
- Operation name.
- Attempt count.
- Outcome.
- Duration.
- Payload bytes if available.
- Timeout/throttle classification.

Never put credentials, full URLs with secret query parameters, or sensitive content into span attributes.

## 4. Instrumenting Java Code with Micrometer and OpenTelemetry

Prefer runtime/framework auto-instrumentation where available, then add custom telemetry for business concepts auto-instrumentation cannot know. Avoid instantiating a separate tracer or metric exporter if a platform agent already supplies a standard SDK or collector.

### 4.1. Measuring Requests with Micrometer

The example below shows request measurement in an application adapter. Metric tags include only low-cardinality route templates, methods, and outcomes.

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.util.function.Supplier;

public final class ApiTelemetry {

    private final MeterRegistry registry;

    public ApiTelemetry(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T recordRequest(
            String route,
            String method,
            long requestBytes,
            Supplier<T> operation) {

        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return operation.get();
        } catch (ClientInputException exception) {
            outcome = "client_error";
            throw exception;
        } catch (RuntimeException exception) {
            outcome = "server_error";
            throw exception;
        } finally {
            sample.stop(Timer.builder("api.server.duration")
                    .tag("route", route)
                    .tag("method", method)
                    .tag("outcome", outcome)
                    .register(registry));

            registry.counter(
                    "api.server.requests",
                    "route", route,
                    "method", method,
                    "outcome", outcome).increment();

            DistributionSummary.builder("api.server.request.bytes")
                    .tag("route", route)
                    .register(registry)
                    .record(requestBytes);
        }
    }

    public void recordResponseBytes(String route, long responseBytes) {
        DistributionSummary.builder("api.server.response.bytes")
                .tag("route", route)
                .register(registry)
                .record(responseBytes);
    }
}
~~~

Exception classes here are illustrative application types. In production applications, exception classification must follow the API contract. Never collapse every exception into `server_error`: validation, authorization, throttling, and dependency timeouts may need distinct outcomes.

Measure response bytes after the serializer builds the payload or at the HTTP adapter where actual transmitted bytes are known. Never substitute Java String length for byte length when encoding is UTF-8 or payloads are compressed.

### 4.2. Measuring Dependency Calls and Retries

Wrap outbound ports or HTTP clients with a decorator:

~~~java
public final class TimedPaymentGateway implements PaymentGateway {

    private final PaymentGateway delegate;
    private final MeterRegistry registry;

    public TimedPaymentGateway(
            PaymentGateway delegate,
            MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    @Override
    public PaymentResult charge(PaymentCommand command) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return delegate.charge(command);
        } catch (PaymentTimeoutException exception) {
            outcome = "timeout";
            throw exception;
        } catch (RuntimeException exception) {
            outcome = "error";
            throw exception;
        } finally {
            sample.stop(Timer.builder("api.dependency.duration")
                    .tag("dependency", "payment")
                    .tag("operation", "charge")
                    .tag("outcome", outcome)
                    .register(registry));

            registry.counter(
                    "api.dependency.calls",
                    "dependency", "payment",
                    "operation", "charge",
                    "outcome", outcome).increment();
        }
    }
}
~~~

If retries happen inside an HTTP client or SDK, an outer decorator may see only one logical call. Instrument retry interceptors or wrappers to count every attempt. You can emit `api.retry.attempts` with `dependency` and `reason` tags such as `timeout`, `throttle`, or `connection_reset`.

Enforce explicit retry limits and timeouts. Unbounded retries multiply request counts, function duration, dependency charges, and network usage. When clients, gateways, function SDKs, and message brokers all retry, configure each layer deliberately to avoid unintended attempt amplification.

### 4.3. Creating Spans with OpenTelemetry

The OpenTelemetry Java API can create manual spans for use cases or dependencies not covered by auto-instrumentation:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class CreateOrderTracing {

    private final Tracer tracer;
    private final CreateOrderUseCase useCase;

    public CreateOrderTracing(
            Tracer tracer,
            CreateOrderUseCase useCase) {
        this.tracer = tracer;
        this.useCase = useCase;
    }

    public CreateOrderResult execute(CreateOrderCommand command) {
        Span span = tracer.spanBuilder("orders.create")
                .setSpanKind(SpanKind.INTERNAL)
                .startSpan();

        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("app.operation", "create_order");
            span.setAttribute("app.item_count", command.items().size());

            return useCase.create(command);
        } catch (RuntimeException exception) {
            span.recordException(exception);
            span.setStatus(StatusCode.ERROR);
            throw exception;
        } finally {
            span.end();
        }
    }
}
~~~

This creates an internal span for the use case. HTTP server instrumentation usually creates the server span already. Never manually create a duplicate server span when auto-instrumentation already emits one, as traces will double-count.

### 4.4. Propagating Trace Context

- Preserve W3C Trace Context or your chosen standard format.
- Propagate context across HTTP clients and message metadata.
- When consumers run asynchronously, link traces according to message semantics.
- Include `trace_id` and `span_id` in structured logs if the backend does not correlate them automatically.
- Never use trace IDs as metric labels.
- Never generate a brand-new correlation ID at every layer when a valid request/trace context already exists.

If a request calls a service outside your organization, propagate trace context only when security policies and partner agreements allow it. Trace context can reveal internal topology or link activity across services.

### 4.5. Measuring Cold Starts

Prefer platform metrics such as initialization duration, cold start count, or startup latency. If the runtime lacks a metric, you can record the execution environment's first invocation using an observability-only flag:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class RuntimeLifecycleMetric {

    private static final AtomicBoolean FIRST_INVOCATION =
            new AtomicBoolean(true);

    public boolean markFirstInvocation() {
        return FIRST_INVOCATION.compareAndSet(true, false);
    }
}
~~~

This flag marks only the first invocation observed by the current Java instance. It is not an authoritative cold-start measurement across all platforms, does not represent every provider initialization event, and must not be used for billing calculations. Never store request-specific data in static fields.

### 4.6. Safe Logging in Java

Use structured logging or a JSON encoder. A log event should include service, environment, route, outcome, duration, request ID, and trace ID. Use an allowlist for logged fields.

Never log:
- Authorization headers, cookies, API keys, or secrets.
- Full request/response bodies by default.
- Payment card data, account credentials, personal identifiers, or sensitive data.
- SQL bind values when they contain user data.
- URLs with query parameters carrying tokens.

If payload inspection is required for debugging, use controlled sampling, masking, and time-boxed activation. Check both application and platform logs because a single request can be logged twice.

## 5. From Telemetry to Dashboards and SLOs

Dashboards must answer operational questions. A dashboard packed with hundreds of metrics that fails to pinpoint routes, dependencies, or cost drivers adds little value.

### 5.1. API Overview Dashboard

Include panels for:
- Request rate by route.
- Success/rejection/error rates.
- p50, p95, and p99 duration.
- Throttled requests and concurrency.
- Cold start count/duration.
- Request/response bytes.
- Dependency latency and error rates.
- Retry attempts and queue age.
- Estimated cost per request and cost per successful operation.

Keep filters for service, environment, region, and version. Add tenant or customer filters only if cardinality is small, permitted, and necessary; for high cardinality, rely on log queries or dedicated cost reports.

### 5.2. SLOs and Error Budgets

Sample SLOs:
- 99.9% of valid requests complete in under 500 ms over a 30-day window.
- 99.95% of order-creation operations complete successfully within 24 hours.
- Dependency-induced error rate stays below an agreed threshold.

SLOs must specify the exact population, excluded request types, and calculation formula. Do not count client-cancelled requests as server errors unless the contract specifies otherwise. For async workflows, measure from accepted until terminal outcome, not merely the HTTP 202 response time.

### 5.3. Symptom-Based and Cause-Based Alerts

Prioritize alerts on:
- Rising error rates.
- p95/p99 breaching SLOs.
- Throttling or concurrency saturation.
- Queue age exceeding thresholds.
- Spiking retry ratios.
- Dependency timeouts.
- Rising cost per successful operation.
- Abnormal surges in NAT, data transfer, or log ingestion.

Symptom alerts tell you users are impacted; cause alerts help localize the culprit. Avoid paging on single isolated exceptions when rates and impact remain below thresholds.

### 5.4. Separating Platform and Application Metrics

Platform metrics report invocations, duration, memory, throttling, and concurrency. Application metrics report routes, business outcomes, dependencies, and payloads. Maintain both perspectives to avoid inferring product behavior solely from runtime metrics.

For example, a successful function invocation does not mean payment was captured. Conversely, a function returning a validation error may be behaving correctly and should not be counted as a server failure.

## 6. Per-Request Cost Model

Serverless billing typically spans multiple line items. Exact pricing structures depend on provider, runtime, region, tier, and attached services. The model below serves for analysis and cost allocation; obtain real prices from your billing export or the provider's official pricing calculator.

### 6.1. Direct Cost Categories

| Component | Common Driver | Example |
|---|---|---|
| Function requests/invocations | Invocation or request count | 1 handler invocation |
| Function compute | Memory × duration or provider compute units | 512 MiB running for 180 ms |
| Provisioned/minimum capacity | Duration capacity is held warm | Provisioned concurrency or minimum instances |
| API gateway | Requests, data processed, or tier | 1 request through API Gateway |
| Database/cache | Queries, reads/writes, capacity, or compute | One read and one write |
| External APIs | Requests, transactions, or licenses | One payment provider call |
| Networking | GB egress, NAT processing, cross-zone/region transfer | 20 KB response and downstream payloads |
| Logs/traces/metrics | Ingestion, retention, queries, or sample volume | 1 KB of logs and several spans |
| Queues/events | Requests, messages, operations, or data transfer | Publishing and consuming an event |
| Retries | Extra attempts at functions and dependencies | One retried request |

Function compute may be metered by memory/duration, vCPU-seconds, requests, execution time, or other models. Some providers bill by GB-seconds plus requests; some plans include free grants or minimum charges. Never apply a single formula blindly across every platform.

### 6.2. Direct Costs vs. Shared Costs

Separate into:

\[
C_{\text{total}} =
C_{\text{direct}} + C_{\text{shared}}
\]

Where:

- `C_direct`: costs directly attributable to the API/service, such as functions, gateway, database requests, and measured egress.
- `C_shared`: costs of shared infrastructure, such as NAT Gateways, VPC connectors, private endpoints, observability platforms, shared database baselines, or shared provisioned capacity.

A NAT Gateway shared across multiple services should not be billed entirely to one API that uses only a fraction of it. Define an explainable allocation rule and apply it consistently.

### 6.3. General Formula

This can be modeled as:

\[
C_{\text{direct}} =
C_{\text{invocation}} +
C_{\text{compute}} +
C_{\text{gateway}} +
C_{\text{dependency}} +
C_{\text{network}} +
C_{\text{observability}} +
C_{\text{retry}}
\]

\[
C_{\text{service}} =
C_{\text{direct}} + \alpha C_{\text{shared}}
\]

\[
C_{\text{per successful operation}} =
\frac{C_{\text{service}}}{N_{\text{successful operations}}}
\]

Where \(\alpha\) is the share of shared costs allocated to the service. Allocations across all services must sum to total shared costs for the same scope and billing period.

### 6.4. Estimating Function Compute

Under a GB-second model, conceptually:

\[
GBs = Memory_{GB} \times Duration_{seconds} \times Invocations
\]

\[
C_{\text{compute}} = GBs \times Price_{\text{GB-second}}
\]

Convert memory to GB using the pricing table's unit convention. Use provider-billable duration, which may apply rounding rules or minimums. Some runtimes/plans meter CPU, memory, requests, and concurrency differently.

For provisioned concurrency or minimum instances, account separately for capacity held even when no requests arrive. This can be substantial for low-traffic APIs requiring consistent latency.

### 6.5. Accounting for Retry Costs

If a request averages \(a\) attempts, function and dependency executions can exceed original request volume:

\[
N_{\text{attempts}} = N_{\text{requests}} \times a
\]

This approximation holds when average attempts are measured over the same population. With nested retries across clients, gateways, function SDKs, and message brokers, measure each layer separately; never multiply retry ratios mechanically when populations differ.

Retries can increase:
- Invocations and compute duration.
- Database reads and writes.
- External API transactions.
- Network bytes and NAT processing.
- Log and trace volume.
- Queue operations and redeliveries.

### 6.6. Cost per Request vs. Cost per Successful Operation

Useful unit metrics:

\[
C_{\text{per attempt}} =
\frac{C_{\text{service}}}{N_{\text{attempts at the measured boundary}}}
\]

\[
C_{\text{per accepted request}} =
\frac{C_{\text{service}}}{N_{\text{accepted client requests}}}
\]

\[
C_{\text{per successful operation}} =
\frac{C_{\text{service}}}{N_{\text{successful business operations}}}
\]

When a request is accepted but the workflow fails, it still consumes compute and networking. Consequently, cost per successful operation rises above cost per accepted request whenever success rates drop or retries climb.

The denominator of cost per attempt must specify its boundary: function invocations, message deliveries, or dependency calls. Never compare two figures computed over different populations. If an API returns 202 and processes work via a queue, include both acceptance costs and workflow completion costs. Do not divide total workflow cost by HTTP 202 counts alone if you want the cost to complete an operation.

## 7. Example Calculation of Cost per Successful Operation

Suppose a Java API runs for one month with the aggregated metrics below. These are hypothetical figures to illustrate the methodology, not a price quote from any cloud provider.

### 7.1. Volume and Assumptions

| Driver | Assumed Value |
|---|---:|
| Client requests accepted by the API | 5,000,000 |
| Function invocations after retries | 5,200,000 |
| Successfully completed business operations | 4,850,000 |
| Average memory | 512 MiB = 0.5 GiB |
| Average billable duration | 180 ms = 0.18 seconds |
| Illustrative compute price | 0.00001667 USD/GB-second |
| Illustrative invocation price | 0.20 USD/1 million invocations |
| Illustrative API gateway price | 1.00 USD/1 million requests |

### 7.2. Estimating Compute and Invocations

GB-seconds:

\[
0.5 \times 0.18 \times 5,200,000
= 468,000\ GB\text{-}seconds
\]

Compute cost:

\[
468,000 \times 0.00001667
\approx 7.80\ USD
\]

Invocation cost:

\[
5.2 \times 0.20 = 1.04\ USD
\]

Gateway processing 5 million client requests:

\[
5 \times 1.00 = 5.00\ USD
\]

### 7.3. Aggregating Cost Line Items

Suppose the billing export and internal cost allocation show:

| Cost Line Item | Monthly Cost |
|---|---:|
| Function compute | 7.80 USD |
| Function invocations | 1.04 USD |
| API gateway | 5.00 USD |
| Database/cache | 20.00 USD |
| Variable network egress and request-driven data processing | 4.00 USD |
| Logs, metrics, and traces | 2.50 USD |
| Allocated share of shared NAT/endpoints for this API | 120.00 USD |
| Allocated share of shared observability platform | 30.00 USD |
| **Total allocated cost** | **190.34 USD** |

In this example, the two shared items reflect internal allocations assigned to this API—not the organization's entire shared infrastructure bill. The 4 USD network line covers directly attributed variable usage; the 120 USD line covers the allocated baseline/shared NAT and endpoint share without double-counting any SKU.

Cost per accepted request:

\[
190.34 / 5,000,000
= 0.000038068\ USD
\]

Roughly 0.0381 USD per 1,000 accepted requests.

Cost per successful business operation:

\[
190.34 / 4,850,000
\approx 0.000039245\ USD
\]

Roughly 0.0392 USD per 1,000 successful operations.

The gap between the two metrics reflects accepted requests that failed to complete successfully. When success rates fall or retries climb, cost per successful operation rises even if cost per accepted request barely moves.

### 7.4. Interpreting the Results

In this example, function compute accounts for only a small share of total cost. Shared networking and observability dominate. Tuning function memory may yield far less impact than allocating NAT accurately, reducing traffic routed through NAT, or trimming log ingestion.

Never draw conclusions from a single month. Compare multiple periods, adjust for volume and request mix, and check whether unit rates or pricing tiers changed.

## 8. Shared Cost Allocation and FinOps

Billing exports typically record charges at the account, project, subscription, resource, or SKU level. One API may share NAT Gateways, databases, gateways, log workspaces, and tracing backends with many services. Allocation rules help teams understand the costs their workloads generate.

### 8.1. Tags and Labels

Attach metadata to resources that support tagging:

- `service`: service or API name.
- `team`: owning team.
- `environment`: dev, staging, production.
- `cost-center`: cost center code.
- `region`: deployment region.
- `managed-by`: repository or IaC owner.
- `version`: deployment version where useful.

Not every managed service supports full tagging. When tags are unavailable, correlate via resource IDs, projects/accounts, subnets, routes, log groups, and deployment metadata.

### 8.2. Choosing Allocation Drivers

| Shared Resource | Suitable Drivers | Notes |
|---|---|---|
| NAT Gateway | Bytes processed per service/subnet | Use flow logs or network telemetry |
| Private endpoint | Bytes or requests hitting the endpoint | Hourly fees may need splitting by consumer count |
| Shared database | Query units, reads/writes, storage, or connection usage | Do not rely solely on request count if query weights differ |
| Log workspace | Ingested bytes per service/log group | Separate debug logs from audit logs |
| Trace backend | Span count or ingested GB | Sampling rate directly affects volume |
| Shared gateway | Request count and data processed | Routes carry varying payload sizes |
| Provisioned capacity | Reserved capacity or peak concurrency share | May need combining baseline and peak usage |

### 8.3. Usage-Based Allocation Formula

A straightforward formula:

\[
C_{\text{service}} =
C_{\text{shared pool}} \times
\frac{Usage_{\text{service}}}{Usage_{\text{all consumers}}}
\]

For example, a shared NAT Gateway processes 1,000 GB in a month. API A drives 300 GB, API B drives 500 GB, and API C drives 200 GB. Allocating processing fees by bytes assigns 30% to API A, 50% to API B, and 20% to API C.

Hourly fees can follow the same driver if your organization adopts that rule and documents it clearly. If a service mandates an always-on NAT even with zero traffic, baseline capacity fees may be allocated by capacity/ownership rather than bytes alone.

### 8.4. Showback and Chargeback

- **Showback:** reporting to teams what resources they consume and what costs they drive.
- **Chargeback:** charging allocated costs directly against a team's budget or cost center.

Before enabling chargeback, verify resource mappings, owners, usage drivers, and handling of late-arriving billing data. Never treat internal allocations as literal provider invoices for a team.

### 8.5. Reconciling Billing Against Application Telemetry

Use billing exports to determine actual spend by SKU/usage type. Use metrics, logs, and traces to explain the underlying workload. Reconcile over the exact same time window and scope:

1. Select the account/project/subscription, region, and service.
2. Filter SKUs related to functions, gateways, networking, databases, and observability.
3. Pull invocations, duration, memory, bytes, and request counts from provider/application metrics.
4. Compare measured volumes against billed quantities, watching GB/GiB conversions and rounding rules.
5. Identify shared resources and allocation drivers.
6. Document discrepancies—such as log ingestion or NAT traffic not directly metered by the application.
7. Update the unit cost model and explain variances.

Billing data can arrive late and undergo end-of-period adjustments. Label reports as estimated or finalized to avoid comparing preliminary numbers against final invoices.

## 9. Differences Across Cloud Providers

Providers use different service names and billing mechanics. Map your common application telemetry to each provider's metrics and billing export.

### 9.1. AWS Lambda and API Gateway

Drivers to inspect:
- Lambda requests and duration/memory GB-seconds.
- Architecture/runtime and associated pricing multipliers.
- Provisioned concurrency if enabled.
- Ephemeral storage beyond included capacity if applicable.
- API Gateway requests/data processing and caching if enabled.
- CloudWatch Logs ingestion, retention, and custom metric charges.
- X-Ray or OpenTelemetry trace exports.
- NAT Gateway, VPC endpoints, and data transfer.
- Downstream DynamoDB, RDS, SQS, EventBridge, or external APIs.

Lambda platform metrics report invocations, duration, errors, throttles, and concurrency. Application telemetry adds route, business outcome, and dependency breakdowns. Never infer cost per business operation solely from Lambda duration.

### 9.2. Google Cloud Functions / Cloud Run Functions

Drivers to inspect:
- Requests, CPU/memory allocation, and duration by execution model and region.
- Minimum instances or minimum capacity if configured.
- Networking via VPC connectors or Direct VPC egress.
- Cloud Logging ingestion and retention.
- Cloud Trace/Monitoring and sampling rates.
- Cloud NAT, Private Service Connect, and data transfer.
- Database, Pub/Sub, Eventarc, and downstream service costs.

Cloud Run functions execute on the Cloud Run platform. Check the exact generation, region, CPU/memory model, concurrency, and billing tier rather than applying one uniform rate across all functions.

### 9.3. Azure Functions

Drivers to inspect:
- Consumption executions and execution time/memory per hosting plan.
- Flex Consumption, Premium, or Dedicated plans if used.
- Always-ready instances or prewarmed capacity if configured.
- Application Insights/Log Analytics ingestion and retention.
- NAT Gateway, Private Endpoints, VNet integration, and egress.
- Storage accounts, queues, and downstream services.

Azure Functions offers multiple hosting plans. Moving a workload from Consumption to Premium can substantially change fixed/minimum capacity charges. Compare costs using the actual plan and region.

### 9.4. Standardizing the Model Rather Than Unit Prices

Maintain a unified internal schema for:
- Requests accepted/succeeded/failed.
- Function invocations and attempts.
- Compute quantities.
- Gateway request counts.
- Database/dependency operations.
- Network bytes and transfer classes.
- Log/trace ingestion.
- Shared resource allocations.

Map each provider's SKUs and billing quantities into this schema. Never compare raw GB-second unit rates directly across platforms when runtimes, CPU allocations, concurrency models, rounding, and included free grants differ.

## 10. Optimizing Costs Using Telemetry

Optimize only after identifying the real cost driver. A change might lower compute while increasing retries or network egress.

### 10.1. Reducing Useful Duration

- Optimize queries and add appropriate indexes.
- Reduce round trips to databases and external APIs.
- Reuse HTTP clients and connection pools when the runtime permits.
- Avoid initializing heavy SDKs or frameworks per request.
- Eliminate unnecessary serialization/deserialization.
- Batch or cache where semantics allow.
- Trim response payloads.

Measure before and after across the same route, volume, payload mix, and success rate. Faster duration is meaningless if error rates climb or requests are processed incompletely.

### 10.2. Tuning Memory and CPU

Increasing memory may also increase CPU or network throughput depending on the provider. A function can finish faster and consume fewer total GB-seconds despite higher allocated memory. Benchmark several configurations and compare:
- p50/p95 duration.
- Memory utilization.
- GB-seconds or billable compute.
- Error/timeout rates.
- Cold starts.
- Cost per successful operation.

Never tune memory based on average duration alone.

### 10.3. Reducing Downstream Fan-Out and Retries

- Eliminate N+1 database calls.
- Consolidate API calls when bulk endpoints exist.
- Set per-dependency timeouts.
- Retry with budgets, backoff, and jitter.
- Use circuit breakers for unstable dependencies.
- Cap concurrency to prevent retry storms.
- Offload work that can run asynchronously to queues/DLQs.
- Guarantee idempotency on redeliveries.

When a downstream API slows down, raising function concurrency can escalate both cost and downstream pressure simultaneously. Monitor concurrency, retry ratios, and dependency latency before scaling up.

### 10.4. Controlling Logs and Traces

- Eliminate redundant logging across layers.
- Never log large payloads unless explicitly required.
- Set retention per environment and log category.
- Sample successful traces while retaining error and slow-request traces per policy.
- Avoid exporting the same trace through multiple agents or collectors.
- Verify log levels after every deployment.
- Set observability ingestion budgets.

Never cut telemetry so aggressively that incident investigation or audit trails break. Retain mandatory security/audit logs and optimize high-volume diagnostic logs.

### 10.5. Evaluating Fixed Capacity

Provisioned concurrency or minimum instances reduce cold starts and stabilize latency, at the cost of idle capacity. Enable them only when SLOs or traffic patterns justify it. Compare:
- Share of requests actually benefiting.
- Reduction in p95/p99 latency and cold starts.
- Idle capacity cost.
- Cost per successful operation.
- Low-traffic periods during the day.

### 10.6. Optimizing Networking by Destination

Classify traffic to managed services, public APIs, private databases, and cross-region destinations. Private endpoints can cut NAT usage and public exposure, though they carry hourly endpoint charges. Use signed URLs with object storage for large files instead of proxying bytes through functions. Colocate functions near primary dependencies when aligned with latency, data residency, and DR goals.

## 11. Cost Attribution by Route and Product

An API may serve routes with vastly different resource footprints. A health-check route may hit zero dependencies; an order-creation route may hit the database, payment gateway, and event bus. Dividing total cost evenly across request counts distorts unit costs whenever payloads, durations, and fan-out vary.

### 11.1. Drivers for Route-Level Allocation

You can construct per-route weights from:
- Function compute per route or request duration × memory.
- Dependency operations and database usage.
- Network bytes per route/dependency.
- Log bytes and trace spans.
- Retry attempts.
- Gateway request counts.

An internal weighting model:

\[
Weight_{\text{route}} =
w_c Compute_{\text{route}} +
w_d Dependency_{\text{route}} +
w_n Network_{\text{route}} +
w_o Observability_{\text{route}}
\]

\[
C_{\text{route}} =
C_{\text{service}} \times
\frac{Weight_{\text{route}}}{\sum Weight_{\text{all routes}}}
\]

Coefficients \(w_c, w_d, w_n, w_o\) are internal weights. Whenever billing exports already report direct costs per resource or SKU, use those actual figures first; weights primarily allocate shared or unattributed costs.

### 11.2. Avoiding False Precision

Not every cloud bill breaks down costs by HTTP route. Some SKUs report only at the function, gateway, log group, or network-resource level. Therefore:
- Attribute direct costs wherever the provider supports it.
- Allocate shared portions using published drivers.
- Clearly label actual figures versus estimates.
- Retain an unallocated bucket when reliable drivers are lacking.
- Never force every dollar onto a route using arbitrary ratios.

Cost attribution is a governance model. It must be explainable and reconcile back to the total bill.

### 11.3. Tracking Unit Economics by Release Version

Tag logs, traces, and cost windows with the deployment version. Compare pre- and post-release metrics:
- Cost per successful operation.
- Duration and memory.
- Dependency calls per operation.
- Retry ratio.
- Payload bytes.
- Success rate.

Never use version numbers or commit hashes as metric labels if they create excessive cardinality. Use deployment metadata, log queries, or dashboard annotations to filter by version.

## 12. Investigating Cost Spikes

When costs spike, identify which bill line item rose first. Then correlate billed quantities with telemetry and recent changes around that timeframe.

### 12.1. Investigation Workflow

1. Identify the SKU, usage type, and resource showing the increase.
2. Compare billed quantity against unit price to separate volume growth from price/tier shifts.
3. Inspect request counts, function invocations, duration, and memory.
4. Check retry ratios, downstream calls, timeouts, and queue redeliveries.
5. Check bytes transferred, NAT processing, and cross-zone/cross-region traffic.
6. Check log ingestion, trace sampling, and retention.
7. Review recent deployments, concurrency settings, routing, or VPC changes.
8. Allocate shared portions by driver and identify owners.
9. Propose optimizations, then re-measure SLOs and cost per successful operation.

### 12.2. Common Warning Signs

| Symptom | Possible Cause | Data to Inspect |
|---|---|---|
| Invocations grow faster than client requests | Retries, batch splitting, or event redeliveries | Attempt counts, trigger metrics |
| Duration rises while request count stays flat | Slow downstream dependency or cold starts | Trace spans, dependency latency |
| Network cost rises while response bytes stay flat | Retries, NAT hairpinning, or downstream payloads | NAT metrics, flow logs, dependency bytes |
| Log costs spike abruptly | Debug logging, duplicate loggers, or payload logging | Ingestion bytes, log levels, deployments |
| Cost per success climbs | Dropping success rate, rising retries, or shifting route mix | Outcomes, retries, route mix |
| Gateway costs rise | Higher request counts or data processing volume | Gateway metrics and access logs |
| Database costs rise | N+1 queries, heavy queries, or retries | Query metrics, calls/request, connection counts |

### 12.3. Budgets and Anomaly Alerts

Configure budgets or alerts for:
- Total service/environment cost.
- Cost per 1,000 accepted requests.
- Cost per 1,000 successful operations.
- Function compute quantity and invocations.
- NAT and data transfer.
- Log and trace ingestion.
- Retry ratios and dependency operations.

Set trend- and threshold-based alerts tailored to the workload. For batch jobs or seasonal traffic, use calendar-aware forecasts. Never page an incident solely because total spend rose with expected traffic growth; inspect unit cost first.

## 13. Production Checklist

- [ ] Clear definitions exist for client requests, invocations, attempts, and successful business operations.
- [ ] Request counts, duration histograms, and outcomes are metered by route template.
- [ ] Platform metrics cover invocations, duration, memory, concurrency, and throttling.
- [ ] Dependency latency, call counts, timeouts, and retry attempts are instrumented.
- [ ] Request/response bytes and network usage are tracked where relevant.
- [ ] Structured logs include request IDs and trace IDs.
- [ ] Logs exclude secrets, credentials, sensitive payloads, and unnecessary personal data.
- [ ] Distributed tracing and context propagation work across HTTP and messages.
- [ ] Metric labels avoid high-cardinality values.
- [ ] Manual spans do not duplicate auto-instrumentation spans.
- [ ] Dashboards track p50/p95/p99, error rates, retries, and queue age.
- [ ] SLOs distinguish accepted requests from successful business operations.
- [ ] The cost model includes functions, gateway, dependencies, networking, and observability.
- [ ] Shared costs have explicit allocation drivers and any unallocated share is disclosed.
- [ ] Cost per accepted request and cost per successful operation use explicit denominators.
- [ ] Billing exports are reconciled with telemetry over matching time windows.
- [ ] Illustrative rates are never confused with current provider pricing.
- [ ] Budgets/anomaly alerts exist with assigned owners.
- [ ] A process exists to compare cost and SLOs before and after deployments.
- [ ] Sampling, retention, and log levels are governed per environment.

## 14. Self-Check

**Question 1.** How do metrics, logs, and traces differ?

**Suggested Answer:** Metrics show trends and magnitudes such as request rate, error rate, and latency. Logs describe specific events from an individual execution. Traces show which components a request traversed and how long each span took.

**Question 2.** Why should request IDs not be used as metric labels?

**Suggested Answer:** Request IDs are nearly unique per request, creating massive cardinality and inflating metric storage and query costs. Request IDs belong in controlled logs or traces.

**Question 3.** Why can cost per successful operation increase even when cost per accepted request stays nearly flat?

**Suggested Answer:** A lower success rate means fewer operations complete while failed requests still consume resources. Extra retries and dependency work can also drive costs higher.

**Question 4.** Why can application byte metrics differ from network billing quantities?

**Suggested Answer:** Applications measure payloads at the application layer. Billing may include headers, protocol overhead, retransmissions, additional traffic directions, or provider-specific metering rules. Always reconcile rather than assuming both numbers match.

**Question 5.** Is allocating shared NAT charges evenly by request count always fair?

**Suggested Answer:** No. Different routes transfer vastly different byte volumes. Allocating by bytes/subnet or flow telemetry reflects actual usage better; baseline fees may require separate capacity/ownership drivers.

**Scenario Exercise:** A Java API serves 5 million requests per month. After a release, client request volume barely changes, yet function invocations jump 18%, p95 latency rises from 220 ms to 800 ms, network costs increase 35%, and log ingestion doubles. Propose an investigation plan and how to update cost per successful operation.

**Guidance:** Compare client requests against invocations/attempts to detect retries or event redeliveries. Use traces to pinpoint slow dependency spans and check concurrency/throttling. Reconcile NAT/flow logs against dependency bytes to find higher traffic or fan-out. Check log levels, duplicate loggers, and payload logging. Pull the billing export to separate quantity changes from unit rates, then recompute cost over successful operations. Only ship optimizations when their SLO impact is measured over the same request mix.

## Conclusion

Telemetry for a serverless API combines platform metrics, application metrics, structured logs, and distributed traces. Metrics reveal trends; logs and traces explain individual requests, dependencies, retries, and payloads. Cost per request must account for functions, gateways, databases, networking, retries, and observability, with transparent allocation drivers for shared infrastructure. Cost per successful operation ties cloud spend directly to product outcomes, letting teams prioritize optimizations based on evidence. Reconcile billing exports with telemetry and track SLOs before and after every change so cost savings never degrade service quality.
