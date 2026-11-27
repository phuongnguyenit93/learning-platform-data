# API Observability and Cross-Service Error Tracing

A user sends a payment request to an API and receives HTTP 502 after a few seconds. In front sits Azure Front Door or Application Gateway, followed by Azure API Management (APIM), a Java API on Azure Container Apps/AKS, an Azure Function handling async jobs, Service Bus, and finally Azure SQL Database. Each component keeps its own logs. Looking only at the API gateway logs tells operations that the request failed—but not **at which hop**, or whether it was caused by the database, networking, timeouts, retries, or a recent deployment.

**API observability** is the ability to infer a system's internal state from telemetry—**metrics, logs, and distributed traces**—combined with release, topology, identity, and business context. The goal is not just building pretty dashboards, but quickly answering:

- Which API is impacting users, over what time window and region?
- Where did the request start, which services did it traverse, and at which step did it fail?
- Does the error belong to the client, gateway, backend, dependency, or network?
- Can a specific request be traced by trace ID/correlation ID without exposing sensitive data?
- Should we alert, roll back, cap retries, or scale resources?
- Does observability stay within budget and data-governance policies?

This lesson belongs to the **API and Workflow Integration** chapter of the **CLOUD_PROVIDERS_AZURE** module. It connects subscriptions/resource groups, Microsoft Entra ID, virtual networks, API Management, Java services, Functions, Service Bus, Azure Monitor, Application Insights, and Log Analytics with security, deployment, and cost control.

> **Scope:** KQL table names, log fields, metric types, and telemetry integrations depend on the Azure resource, workspace-based Application Insights mode, SDK/agent, and version. The examples below use common schemas to teach investigation methodology; before using in production, verify real schemas and metric definitions on resources in your subscription.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish monitoring from observability; understand the three signals: metrics, logs, and traces.
2. Select realistic API SLIs/SLOs: availability, latency, error rate, throughput, and business correctness.
3. Explain W3C Trace Context, **trace ID**, **span ID**, parent/child spans, **`traceparent`**, **`tracestate`**, and correlation IDs.
4. Design context propagation across APIM, HTTP services, Azure Functions, and message brokers.
5. Configure telemetry collection pipelines with **Azure Monitor**, **Application Insights**, **Log Analytics**, and **OpenTelemetry**.
6. Write **KQL** queries to find failed requests, slow dependencies, correlate by `OperationId`/trace ID, and spot post-deployment regressions.
7. Distinguish 4xx, 5xx, 429, 502/503/504, timeouts, dependency failures, and business errors that do not surface as HTTP 5xx.
8. Design actionable alerts and executable incident/rollback procedures.
9. Design sampling, retention, redaction, RBAC, and telemetry cost controls.
10. Implement a multi-service API lab and trace the path of a failing request.

## 2. How does monitoring differ from observability?

**Monitoring** collects known signals and alerts when thresholds cross: errors per minute, CPU utilization, request success rate.

**Observability** goes further: from captured data, engineers can ask new questions to deduce root causes without having to predict every failure mode in advance.

Example:

| Question | Traditional monitoring | Observability |
|---|---|---|
| Is the API failing? | HTTP 5xx chart | Error chart + per-request execution path |
| When did errors start? | Alerts and per-minute charts | Correlation with releases, scaling, dependencies |
| Where did it fail? | Manually inspect each service | Traces pinpoint which span stalled or failed |
| Who is impacted? | System-wide error count | Breakdown by API route, region, environment, safe tenant group |
| What action is needed? | Scale instances if CPU is high | Fix the exact dependency/policy, avoiding misguided changes |

No single tool makes an entire system observable on its own. You need **consistent instrumentation, context propagation, naming, access controls, synchronized clocks, and an incident response process**.

## 3. Three telemetry pillars and shared context

### Metrics

Metrics are time-aggregated measurements: request counts, response times, CPU, connection failures, queue backlogs. They fit dashboards and alerts well because storage/query costs are usually more predictable than detailed per-request logs.

Common types:

- **Counter:** request counts, errors, timeouts, retries.
- **Histogram:** latency and payload-size distributions; powers p50/p95/p99.
- **Gauge:** queue depth, open connections, healthy instances, memory.
- **Up/down counter:** concurrent in-flight requests at a point in time.

Avoid metric labels with high-cardinality unique values like **`userId`**, **`orderId`**, **raw URLs**, or **`traceId`**. Excessive cardinality drives up costs and degrades aggregation.

### Logs

Logs record structured events/details: workflow start, database error codes, rejected requests, retry outcomes. Logs shine when inspecting **specific values** or sequences inside a component.

Example safe structured log:

~~~json
{
  "timestamp": "2026-11-20T08:16:32Z",
  "level": "ERROR",
  "service": "payment-api",
  "environment": "production",
  "operation": "capturePayment",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "errorCode": "PAYMENT_PROVIDER_TIMEOUT",
  "attempt": 2,
  "durationMs": 2800
}
~~~

Never log card numbers, bearer tokens, session cookies, passwords, full request/response bodies, or unnecessary personal data.

### Distributed traces

A trace captures one logical journey across multiple services. Each step is a **span** with timestamps, status, attributes, and parent/child relationships or links.

~~~mermaid
flowchart LR
  C["Client"] --> F["Front Door / App Gateway"]
  F --> A["API Management"]
  A --> J["Java Orders API"]
  J --> P["Payments API"]
  P --> SQL["Azure SQL"]
  J --> SB["Service Bus"]
  SB --> FN["Azure Function worker"]
~~~

Each arrow **does not automatically create a span**; instrumentation and propagation must work at every hop. Traces can develop **gaps** if a gateway does not export spans, an agent is disabled, or sampling drops data.

### Additional context

To pinpoint root causes, combine telemetry with:

- Release/commit hash and deployment timestamp.
- Region/zone and hosting plan type.
- API name, route template, and environment.
- Normalized request paths and dependency types.
- Health/restart events and node-pool upgrades.
- Incidents, change records, and maintenance windows.
- Business outcome: did the order succeed or fail?

## 4. Designing SLIs/SLOs before picking dashboards

An **SLI (Service Level Indicator)** measures user experience; an **SLO (Service Level Objective)** is the target for that indicator over a time window.

Illustrative example for an ordering API:

| SLI | Suggested definition | Illustrative SLO |
|---|---|---|
| Availability | Successful valid requests / total valid requests | 99.9% over 30 days |
| Latency | p95 duration close to client experience | Under 800 ms for eligible GETs |
| Error rate | 5xx and defined system errors / eligible requests | Below published threshold |
| Async completion | Jobs completed on time / jobs accepted | 99% within 10 minutes |
| Data correctness | Transactions without duplicates or lost effects | Per business invariants |

These numbers are **only for learning how to set targets**, not Azure service SLAs or copy-paste recommendations for every application.

### Choosing the right denominator

If a login endpoint returns 401 for a wrong password, that is expected behavior, not a system outage. Conversely, if an API returns 403 because misconfigured RBAC blocks every valid user, that is an incident.

Therefore:

- **Do not mechanically count every 4xx as an availability failure.**
- **Do not treat every 200/202 as a successful business transaction** if background jobs fail afterward.
- Account for valid requests, business outcomes, and critical API routes.
- Separate SLOs for fast GETs, checkouts, and background jobs with distinct profiles.

### Percentiles vs. averages

Average latency can look fine while 5% of users endure painfully slow requests. Track **p50, p95, and p99** when request volume is large enough to be statistically meaningful.

Watch which request set percentiles cover: per region/route, sampled vs. full, successes only vs. including errors. Averaging across endpoints with vastly different durations hides severe regressions.

## 5. Standardizing endpoint, error, and service names

A telemetry model should standardize:

| Element | What to record | What to avoid |
|---|---|---|
| Service name | `payment-api`, `orders-api` | Pod/VM hostnames that change every deploy |
| Environment | `dev`/`staging`/`production` | Ambiguous aliases like `test2` |
| HTTP route | `GET /orders/{orderId}` | `GET /orders/1024`, `GET /orders/1025` creating separate series |
| Region | Standardized Azure region | Ad-hoc names with no mapping |
| Release | Commit SHA or version | Just `latest` |
| Error code | `DB_TIMEOUT`, `UPSTREAM_503` | Uncategorized raw exception logs |
| Trace context | `traceId`, `spanId`, parent span | Minting a brand-new correlation ID at every hop |
| Business ID | Safe `orderId` in logs per policy | Using IDs as high-cardinality metric labels |

An HTTP 502 at APIM alone does not explain the fault. You need **backend status**, policy/gateway error details, backend timeouts, or upstream connection failure reasons. Telemetry must clearly capture **observation point and error classification**.

### Trace ID differs from business correlation ID

- **Trace ID:** one trace of a single request journey.
- **Span ID:** one specific step within a trace.
- **Correlation ID:** an application/operations-standardized ID tying business steps or requests together; can span multiple traces.
- **Order ID / job ID:** ID of a business entity appearing across multiple requests and traces.

Do not collapse all of these into a single ID. When retrying an async job, the **job ID stays stable** while trace/span IDs may differ; store clean links rather than forcing every invocation onto an old trace ID.

## 6. W3C Trace Context and the `traceparent` header

**W3C Trace Context** is the widely adopted standard for propagating trace context over HTTP. Key header:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Structure:

~~~text
version - trace-id (32 hex) - parent-id (16 hex) - trace-flags (2 hex)
00      - 4bf92f3577b34da6a3ce929d0e0e4736 - 00f067aa0ba902b7 - 01
~~~

- **`trace-id`:** kept consistent across hops in the same journey.
- **`parent-id`:** caller's span ID, establishing causal parentage; **changes at every hop**.
- **`trace-flags`:** holds flags such as sampled; not an access token or guarantee that every service recorded spans.
- **`tracestate`:** optional; carries vendor-specific tracing metadata per standard rules.

If a service starts a fresh trace without reading incoming `traceparent`, the trace **breaks**. If two services log the same trace ID without parent/child links, diagnosis remains harder.

### Proper propagation

1. Gateway receives request, preserves/normalizes trace context per policy.
2. Java backend extracts context to start a server span.
3. When calling HTTP dependencies, client instrumentation **injects** context into outgoing requests.
4. Downstream services **extract** context and create child spans.
5. When sending messages, attach trace context in **message application properties/headers**.
6. Consumers extract context and create spans or span links preserving causality.

Never hardcode a static `traceparent` across requests. **Never treat `traceparent` as an authentication token**; external clients can send arbitrary headers, so gateways/receivers must define trust boundaries and sanitization policies.

### Tracestate and baggage

**Baggage** can carry extra key/value pairs across services; it differs from span attributes and travels over the network. Never put emails, card numbers, secrets, bearer tokens, or sensitive data into baggage. Not every header metadata item from the Internet should be copied blindly into private systems.

## 7. Distributed tracing across HTTP and queues

An asynchronous API flow can proceed as follows:

~~~mermaid
sequenceDiagram
  participant C as Client
  participant G as API Management
  participant A as Orders API
  participant Q as Service Bus
  participant W as Function Worker
  participant D as Database
  C->>G: POST /orders (traceparent)
  G->>A: Forward request + trace context
  A->>D: Save order + outbox
  D-->>A: Commit
  A->>Q: Publish message + trace context
  A-->>G: 202 Accepted + jobId
  G-->>C: Response
  Q-->>W: Deliver message
  W->>D: Apply work idempotently
  D-->>W: Result
~~~

Trace propagation over HTTP is fairly direct via W3C headers. **Across queues/brokers**, context does not automatically turn into HTTP headers: SDK/instrumentation libraries must pass it via message metadata, or the app must inject/extract it deliberately.

Example message containing:

~~~json
{
  "jobId": "job-1024",
  "orderId": "order-1024",
  "schemaVersion": 1
}
~~~

Alongside dedicated **application properties** such as `traceparent` and `tracestate` when needed. Context does not belong in the JSON business body; keep the body focused on the business contract while tracing metadata rides in broker headers/properties.

### Span links and async boundaries

A consumer processing a batch of messages—or a message retried hours later—may need **Span Links** instead of forcing long-lived parent-child hierarchies. The choice follows OpenTelemetry semantic conventions and messaging SDK capabilities. What matters is having a trail back to the producer/job ID and understanding each retry as a separate invocation.

### At-least-once delivery

Traces reveal duplicate runs, **but do not prevent duplicate business effects**. With Queue Storage, Service Bus, Event Grid, and event-driven systems, you still need idempotency keys, retry policies, and DLQ/poison-message runbooks. Telemetry should distinguish:

- Producer message ID / event ID.
- Delivery attempt or dequeue/delivery count.
- Stable job ID / business key.
- Trace ID of each processing attempt.
- Complete/abandon/dead-letter outcome and business result.

## 8. Azure observability stack: what does each component do?

| Azure component | Responsibility | Notes |
|---|---|---|
| **Azure Monitor** | Platform for collecting/evaluating metrics, logs, alerts | Verify exact data sources and retention |
| **Application Insights** | Application telemetry: requests, dependencies, exceptions, traces, availability | Workspace-based resources store data in Log Analytics |
| **Log Analytics workspace** | KQL querying and table-based log storage | RBAC, retention, and ingestion incur costs |
| **API Management diagnostics** | Tracks gateway traffic and errors from APIM | Does not automatically include full backend traces |
| **Azure resource diagnostic settings** | Streams supported resource logs/metrics to destinations | Each resource/category has distinct schemas and costs |
| **Azure Monitor alerts** | Alerts on metrics, log queries, or supported signals | Design action groups, noise control, and recipients |
| **OpenTelemetry** | Standard instrumentation, semantic conventions, exporters | Choose compatible pipelines/exporters/agents |
| **Azure Service Health / Resource Health** | Platform service/resource health signals | Does not replace application tracing |
| **Cost Management** | Tracks platform and telemetry spend | Does not prove application SLOs |

### Application Insights is not a Log Analytics workspace

Application Insights is the application monitoring resource/experience; a Log Analytics workspace provides the underlying log store/query engine in workspace-based mode. **Azure Monitor Metrics** maintains its own metric store as well. One dashboard can combine metrics and logs, **yet they do not share identical retention, schemas, pricing, or capabilities**.

### Platform sources vs. application sources

- APIM/gateway logs show gateway responses, backend responses, and policy errors.
- Application Insights in Java/Functions shows server requests, dependency calls, and exceptions.
- AKS Container Insights / managed Prometheus show pod/node/container health.
- Service Bus metrics/logs show backlogs, dead-letter queues, and broker errors.
- SQL/Storage diagnostics distinguish backend throttling and timeouts.
- Deployment change records reveal version-correlated regressions.

**Do not enable only APIM diagnostics and expect full distributed tracing across Java/SQL/Service Bus.** Instrument every valuable component and verify propagation and sampling end to end.

## 9. Observation points at API Management

Azure API Management typically sits between clients and backends. Key questions:

1. Did the client call the right API/operation?
2. Did the gateway admit the request, or fail before reaching the backend?
3. Did authentication, rate limits, quotas, or policies reject the request?
4. Which backend URL did the gateway forward to (sanitized/redacted)?
5. Did the backend return a status, or did the gateway time out?
6. How much did gateway duration differ from backend duration?
7. Are errors isolated to one region, revision, subscription, or route?

### Gateway status differs from backend status

For instance, APIM returns HTTP 504 to the client due to an **upstream timeout**. The backend might still be processing. If the client retries immediately, the business action could execute twice. Traces must distinguish:

~~~text
Client HTTP 504
  -> APIM gateway timeout at 30s
  -> Backend /orders keeps running, finishes later
  -> Client retries with the same job/order ID
~~~

This illustrates the failure mechanism, not a fixed default APIM timeout setting.

### APIM diagnostics and Application Insights

APIM provides diagnostics/integration capabilities to emit gateway telemetry to supported destinations. Configure at the right scope and control:

- Logger/diagnostic settings per resource and API.
- Sampling rates and captured request/response metadata.
- Which headers may be logged; exclude `Authorization`, `Cookie`, `Set-Cookie`.
- Restrict or disable body logging per data policy.
- Assess client IP, tenant/user IDs, and query parameters for privacy compliance.
- Permissions and connectivity to Application Insights / Log Analytics.

### Never use unauthorized debug traces in production

APIM request-tracing/debug features have permission requirements and behavior that vary by version and tier. Never assume any client can trigger verbose APIM tracing via an old header. In production, rely on controlled diagnostics, redaction, least privilege, and approved investigation workflows.

## 10. Azure Application Insights: requests, dependencies, exceptions

When a Java app is instrumented, typical telemetry groups include:

| Group | Content | Question |
|---|---|---|
| Requests | Endpoint, duration, status, success, operation context | Which API is slow or failing? |
| Dependencies | Supported HTTP/SQL/Storage/messaging calls | Which dependency causes latency/failures? |
| Exceptions | Error type, stack trace, and context | Why did the request fail? |
| Traces (logs) | Application logs with severity and context | What steps did the handler run? |
| Custom events/metrics | Business milestones or custom measurements | Did the order finish on time? |
| Availability | Synthetic tests if configured | Is the endpoint reachable externally? |

**Do not confuse the `AppTraces` table with a distributed trace tree**: `AppTraces` stores correlated log messages, whereas trace trees connect request and dependency spans.

### Limits of automatic instrumentation

A Java agent can auto-capture many HTTP, JDBC, messaging calls, and exceptions depending on agent/library versions. However, it does not know the **business step “reserve inventory”** unless you add spans, metrics, or logs. To see whether reserving inventory took 1.8s vs. a 1.2s DB query, add **custom spans** at meaningful boundaries.

## 11. OpenTelemetry and Java: getting started

**OpenTelemetry (OTel)** provides APIs, SDKs, auto-instrumentation, and semantic conventions for metrics, traces, and logs. For Java services, typical choices are:

1. **Azure Monitor OpenTelemetry Java distribution/agent** in a supported version, exporting directly to Azure Monitor / Application Insights.
2. **OpenTelemetry Java agent** paired with a configured and secured exporter/pipeline (OTLP collector or compatible exporter).
3. Manual instrumentation via OTel API/SDK for business spans, combined with auto-instrumentation where needed.

Never run two Java tracing agents instrumenting HTTP/JDBC simultaneously in the same JVM without testing; it easily produces **duplicate spans, context conflicts, and overhead**.

### Conceptual pipeline options

~~~text
Java API on Container Apps / AKS / App Service
  -> OTel instrumentation/agent
  -> (option A) Azure Monitor exporter / supported distribution
  -> Application Insights + Log Analytics workspace

Java API
  -> OTel Java agent (OTLP)
  -> Managed OTLP collector
  -> Supported exporter/ingestion endpoint
  -> Azure Monitor / corresponding store
~~~

These two approaches are not **1:1 drop-in equivalents**. Verify the exact agent, exporter, environment variables, auth, and Azure support matrix at deployment time.

### Java agent injection — conceptual example

Once an **organization-approved Java agent** has been downloaded and verified, start the app with:

~~~bash
java -javaagent:/opt/telemetry/approved-agent.jar -jar orders-api.jar
~~~

The path is a placeholder; exporter settings, service name, version, environment, connection strings/credentials, and sampling must be configured separately per agent type. Never download agents from arbitrary URLs on production startup or pass secrets on the command line.

### Useful resource attributes

- `service.name` = `orders-api`
- `service.version` = `2.3.7` or commit hash
- `deployment.environment.name` = `production` (per active semantic conventions/SDK)
- `cloud.region` = `southeastasia` when sourced accurately
- `k8s.namespace.name` / `k8s.pod.name` when running on AKS

Never place specific customer identities or tokens in resource attributes. Semantic convention attribute names can evolve across versions; standardize internally and verify against exported telemetry.

## 12. Java: adding custom spans for business steps

Example using the **OpenTelemetry API** inside a Java service whose tracing provider is configured by an agent/SDK. The snippet illustrates a span for a business step:

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class InventoryTracing {

    private static final Tracer tracer =
        GlobalOpenTelemetry.getTracer("commerce.orders", "1.0");

    public void reserve(String orderId) {
        Span span = tracer.spanBuilder("inventory.reserve").startSpan();
        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("business.operation", "reserveInventory");

            // Call the real inventory service using an instrumented client.
            reserveInInventoryService(orderId);

        } catch (RuntimeException ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR);
            throw ex;
        } finally {
            span.end();
        }
    }

    private void reserveInInventoryService(String orderId) {
        // Replace with actual idempotent business logic and HTTP/SDK call.
        throw new UnsupportedOperationException("Example only");
    }
}
~~~

**This illustrates instrumentation structure, not a runnable business class**: the implementation method is stubbed and placeholders must be replaced before running. Ensure a compatible OpenTelemetry API dependency version and an initialized tracer provider/exporter from the agent/SDK.

Notes:

- **Span names** should be low-cardinality and meaningful—never embed `orderId` in the span name.
- **Attributes** must not contain PII or secrets; if a business ID is needed for investigations, follow sensitivity, retention, and sampling policies.
- **`recordException` + `setStatus(ERROR)`** mark failures clearly in supported SDKs.
- **`finally span.end()`** guarantees the span closes even when exceptions occur.
- `Scope` sets the span as current context inside the block so client instrumentation creates proper child spans.
- Preserve real exception propagation—never swallow failures just to make metrics look green.

## 13. Propagating context from a Java HTTP client

With Java `HttpClient`, compatible auto-instrumentation often injects context automatically. For custom clients or unsupported SDKs, inject W3C context using the OTel propagator.

**Abbreviated snippet** inside a request handler with an active span:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.context.Context;

HttpRequest.Builder builder = HttpRequest.newBuilder()
    .uri(URI.create("https://inventory.internal.example/api/reserve"))
    .POST(HttpRequest.BodyPublishers.noBody());

GlobalOpenTelemetry.getPropagators()
    .getTextMapPropagator()
    .inject(Context.current(), builder,
        (carrier, key, value) -> carrier.header(key, value));

HttpRequest outgoing = builder.build();
// Send using an appropriately configured HttpClient and policy.
~~~

This is a **snippet**, not a complete program. The tracer provider must enable W3C propagation and the request must execute inside the right active scope. Do not combine auto-injection and manual injection blindly without verifying client behavior.

**Never blindly copy all incoming headers** from external Internet clients to downstream services. Forward only approved required headers; `Authorization` and cookies must not cross trust boundaries automatically.

### Test cases

- Valid incoming `traceparent` → server span joins the same trace.
- Outgoing HTTP call → downstream span shares the trace ID with proper parent ID.
- HTTP call timeout/retry → each attempt emits distinguishable spans/attributes.
- Client disconnects → backend may finish work; verify business idempotency.
- Gateway rewrites route or proxies → trace context is not stripped unexpectedly.

## 14. Propagation across Service Bus and Azure Functions

A request may accept an order, publish a message, and have a worker process it seconds or minutes later. The HTTP trace must correlate with background execution despite the asynchronous boundary.

### Producer

- Construct messages with a **stable `jobId`/`orderId`**.
- Store or inject **`traceparent`/`tracestate`** into message application properties per supported SDK/instrumentation.
- Log/span an “enqueued” event on the producer side.
- Return HTTP **202 Accepted** once the job is durably accepted per API contract.

### Consumer

- Read the message and extract trace context.
- Use SDK instrumentation or explicit extraction to build a consumer span / span link.
- Record attempt number, queue/topic, worker service, and processing status per conventions.
- On error, log exceptions without dumping sensitive message bodies.
- Complete/abandon/dead-letter per broker and business semantics.
- Mark the job succeeded only after outputs are durably persisted.

### Do not assume span linkage is automatic

Azure Functions and Service Bus instrumentation vary by runtime, extension, and SDK; some versions link traces automatically while others do not. Inspect **actual traces from a test message**. If consumer spans are disconnected, propagate via application properties or span links supported by your agent.

### Separate retry invocations

If a message is redelivered 3 times, emit **3 processing spans**, each carrying its attempt count and shared job ID. That visibility is desirable: retries carry operational meaning. Never merge retries into one infinite span or report a fake **business success** after an earlier failure.

## 15. Workspace-based Application Insights and KQL

When Application Insights connects to a Log Analytics workspace, application telemetry typically lands in tables such as:

| Telemetry type | Common workspace-based table |
|---|---|
| Server requests | **`AppRequests`** |
| Outbound dependencies | **`AppDependencies`** |
| Application exceptions | **`AppExceptions`** |
| Application log/trace messages | **`AppTraces`** |
| Custom events | **`AppEvents`** |

In classic Application Insights environments/schemas, tables may be named **`requests`**, **`dependencies`**, **`exceptions`**, and **`traces`**. The KQL queries below assume **workspace-based `App*` tables** and matching fields; inspect your workspace's actual schema and adapt if needed.

### Query 1 — 5xx failed requests in the last hour

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where toint(ResultCode) >= 500 and toint(ResultCode) < 600
| project TimeGenerated, OperationId, Name, ResultCode,
          DurationMs, Success, Url
| order by TimeGenerated desc
| take 100
~~~

Use this to grab the **`OperationId`** of a failed request and correlate timelines. Protect access carefully since `Url` may contain sensitive query parameters; on broadly shared dashboards, project only route templates or mask URLs.

### Query 2 — Error rate and p95 by route

~~~kusto
AppRequests
| where TimeGenerated >= ago(6h)
| summarize
    Requests = count(),
    Failed = countif(Success == false),
    P95Ms = percentile(DurationMs, 95)
  by bin(TimeGenerated, 5m), Name
| extend ErrorRatePct =
    iff(Requests == 0, 0.0, 100.0 * todouble(Failed) / Requests)
| order by TimeGenerated asc
~~~

**Note:** `Success` as defined by the SDK may differ from business outcomes. This query measures errors in captured telemetry, not a normalized availability SLI. When sampling or ingestion transforms are active, account for sampling weights before treating counts as exact totals.

### Query 3 — Dependency failures

~~~kusto
AppDependencies
| where TimeGenerated >= ago(2h)
| where Success == false
| summarize Failures = count()
  by Name, Target, ResultCode
| top 20 by Failures desc
~~~

If a SQL or HTTP dependency is missing despite request failures, check instrumentation coverage, sampling, unsupported client libraries, or non-instrumented calls. Never conclude a dependency succeeded merely because no failure log exists.

### Query 4 — All records sharing an OperationId

~~~kusto
let chosenTrace = "4bf92f3577b34da6a3ce929d0e0e4736";
union withsource=SourceTable
    AppRequests, AppDependencies, AppTraces, AppExceptions
| where TimeGenerated >= ago(24h)
| where OperationId == chosenTrace
| project
    TimeGenerated,
    SourceTable,
    OperationId,
    SpanOrParentId = tostring(column_ifexists("ParentId", "")),
    ItemName = tostring(column_ifexists("Name", "")),
    MessageText = tostring(column_ifexists("Message", "")),
    ResultCode = tostring(column_ifexists("ResultCode", ""))
| order by TimeGenerated asc
~~~

`OperationId` in Application Insights is commonly used for correlation and maps to the W3C trace ID when integrated properly. **Do not assume APIM/Service Bus platform diagnostic logs automatically share the exact same `OperationId`**: each source uses its own schema/context. Verify mappings, trace exports, and correlation ID/`traceparent` propagation per component.

### Query 5 — Exception spikes after a release

~~~kusto
AppExceptions
| where TimeGenerated >= ago(4h)
| summarize Errors = count()
  by bin(TimeGenerated, 10m),
     ExceptionType = tostring(column_ifexists("ExceptionType", "unknown"))
| order by TimeGenerated asc
~~~

Join release/version metadata when real telemetry carries that attribute. Never invent a `deploymentVersion` column in KQL unless your schema defines it; custom attributes typically reside in dynamic property bags or resource metadata depending on the pipeline.

## 16. Multi-layer failure investigation: HTTP 502 example

Suppose clients receive HTTP 502 calling **`POST /orders`**.

### Step 1 — Start from the symptom

Collect:

- Exact UTC timestamp and region.
- Route template, HTTP method, and client outcome.
- Trace ID / correlation ID if safely returned in the response.
- 5-minute 502 rate and before/after trend.
- Recent releases, incidents, or changes around the onset.

You do not need payloads containing payment cards or tokens to begin investigating.

### Step 2 — Check the gateway layer

In Front Door / Application Gateway / APIM, locate matching requests by timestamp/ID in configured logs. Distinguish:

- Did the backend return 502?
- Did the gateway receive 503 from the backend and map it to 502?
- Did the gateway emit 502 itself because the upstream connection reset?
- Did an authentication/transformation/timeout policy fail?
- Was there a WAF block, rate limit, or health-probe failure?

### Step 3 — Follow traces in the backend

In Application Insights, look up **`AppRequests`** by `OperationId`/correlation and inspect dependency spans:

~~~text
Client: 502 in 3.2s
  APIM: upstream call failed
    Orders API: duration 2.9s, status 500
      Inventory API: 200 in 60ms
      Payment API: 503 in 2.4s
        Third-party gateway: timeout/retry
~~~

This is an **illustrative synthetic trace**, not live output from a running environment. If an API/backend has no matching span, check instrumentation and context propagation before assuming the request never arrived.

### Step 4 — Inspect dependencies and platform

- Did Payment API restart, exhaust connection pools, hit DNS errors, or fail SSL handshakes?
- Did Azure SQL/Storage experience throttling, timeouts, or quota exhaustion?
- Did Service Bus accumulate backlogs, DLQ growth, or consumer crashes?
- Did a deployment alter endpoints, secrets, or certificates around that time?
- Were node pools, HPA, CPU/memory, or connection pools saturated?
- Was there an Azure Service Health incident or Resource Health degradation?

### Step 5 — Mitigate and verify

If caused by a recent release, roll back or toggle the feature flag per runbook. If caused by a slow dependency, tune retry caps, timeout budgets, circuit breakers, or capacity while weighing business impact. After mitigation:

1. Re-test the primary endpoint.
2. Monitor 5xx/p95 across a traffic-appropriate window.
3. Verify business success—not merely HTTP 200.
4. Ensure queued backlogs and poison messages are drained safely.
5. Document root cause, blast radius, and preventive actions.

## 17. Classifying error codes and avoiding false alerts

| Code / signal | Common meaning | What to investigate |
|---|---|---|
| **400** | Client sent invalid input | Validation, version/schema mismatch |
| **401** | Unauthenticated | Token/credentials, clock skew, auth gateway |
| **403** | Insufficient permissions or policy block | Entra RBAC, app authorization, Storage firewall |
| **404** | Resource missing or route mismatch | URL/template, deployment routing |
| **409** | State conflict or duplicate operation | Idempotency / business locks |
| **429** | Rate limit / throttling | APIM policy, downstream quota, `Retry-After` |
| **500** | Unhandled server error | Exceptions, dependencies, code regressions |
| **502** | Gateway received invalid upstream response | Backend reset, policy/mapping, TLS |
| **503** | Service temporarily unavailable | Capacity, unhealthy backend, throttling |
| **504** | Gateway timeout | Deadlines, networking, service latency |
| **Client timeout** | Caller stopped waiting before response | Do not assume the backend stopped running |
| **Job DLQ** | Message failed processing per policy | Retries, poison payloads, schemas, business errors |

**HTTP codes are symptoms, not root causes.** A 403 from Storage might be data-plane RBAC, an invalid SAS, disabled public network access, or a firewall rule; inspect error codes/messages and logs.

### Business errors that never appear as 5xx

An API returns HTTP 202 after enqueuing a job. Later, the worker fails and the message lands in the DLQ. Monitoring only request 5xx makes the system appear spotless while orders go unfulfilled. Track **end-to-end completion metrics**: accepted → started → completed/failed, keyed by stable job ID and deadline.

## 18. Retries, timeouts, circuit breakers, and telemetry

In distributed systems, retries help survive transient faults—but can also amplify outages.

### Cross-service timeout budgets

If a client waits at most 5 seconds while an API calls two downstream services sequentially with 5-second timeouts each, total latency can exceed the client's budget. Allocate an **end-to-end deadline** and per-hop timeouts:

~~~text
Client deadline: 5s
  API handling & validation: < 0.5s
  Inventory dependency: < 1s
  Payment dependency: < 2s
  DB/serialization/margin: remainder
~~~

Numbers are illustrative budget allocations, not universal timeouts for every transaction.

### Retries with backoff and jitter

- Retry transient errors such as eligible HTTP 429/503/timeouts when operations are safe to retry.
- Honor `Retry-After` when provided.
- Use exponential backoff + jitter to avoid thundering herds.
- Cap attempt counts and overall deadlines.
- Log attempt counts and outcomes so “succeeded on attempt 4” remains visible as cost/latency.
- Never retry 400/401/403 or permanent business failures.

### Idempotency

A timeout on `POST /payments` **does not prove the transaction never happened**. When retrying, use idempotency keys and downstream query/reconciliation endpoints. Traces reveal two HTTP attempts, **but never replace transaction or idempotency logic**.

### Circuit breakers

When a dependency fails persistently, a circuit breaker fails fast to avoid exhausting connection/thread pools. Telemetry must distinguish “short-circuited” from “downstream timeout,” otherwise operators might misread fast errors as dependency recovery.

## 19. Structured logging for Java APIs

Logs should be machine-readable and easily filterable by service, route, error code, and trace context. Conceptual example:

~~~json
{
  "time": "2026-11-20T09:12:30Z",
  "severity": "WARN",
  "service": "orders-api",
  "route": "POST /orders",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "f36b6d1935c1a055",
  "operation": "reserveInventory",
  "errorCode": "UPSTREAM_429",
  "retryAttempt": 1,
  "durationMs": 1150,
  "release": "2.3.7"
}
~~~

### Correlating logs and traces

In Java, many logging frameworks support **MDC (Mapped Diagnostic Context)**; instrumentation can auto-inject trace/span IDs into MDC or log attributes per configuration. Never assume installing an OpenTelemetry dependency automatically puts trace IDs into every log line.

Verify by:

1. Sending a test request to the API.
2. Grabbing the trace ID from logs/spans.
3. Searching all logs matching that trace ID.
4. Confirming context survives downstream calls.
5. Checking async thread pools / reactive pipelines preserve context; thread hops often need explicit instrumentation.
6. Confirming secrets and PII are absent from logs.

### Do not dump stack traces for every valid user error

Routine 400 validation errors rarely need giant stack traces. Reserve full exception details for infrastructure/500 bugs in access-restricted stores. Proper error classification reduces alert fatigue and log storage costs.

## 20. Observability in Azure Functions, Container Apps, and AKS

### Azure Functions

- Use Application Insights / agent / extension per supported runtime.
- Track invocations, durations, exceptions, and dependencies.
- For Queue/Service Bus triggers, link **message ID, delivery attempt, trace context, and business outcome**.
- Do not rely only on function execution success: if a handler swallows an exception and returns normally, the broker may complete the message even though business logic failed.
- Cold starts and runtime scaling affect latency.

### Azure Container Apps

- Monitor revisions, replica counts, ingress requests, container logs, and metrics per service capabilities.
- Connect Java app instrumentation to the supported Azure Monitor/OTel pipeline.
- Compare errors by **revision** to spot regressions.
- Configure proper health probes; a `Running` container that is `NotReady` cannot serve traffic.

### Azure Kubernetes Service

- Application tracing runs inside pods; cluster/node metrics add infrastructure context.
- Attach `service.name`, namespace, pod, node, and version via resource attributes per policy.
- Correlate request failures with HPA, node restarts, `OOMKilled` pods, ingress controllers, and rollouts.
- Distinguish service-level 503 caused by **zero ready endpoints** from 503 caused by upstream dependencies.
- Check network policies, DNS/private endpoints, and cross-node latency during incidents.

### APIM/Frontend with backend

Inspect both sides:

1. **Gateway telemetry:** client-facing statuses, throttling, policies, backend calls.
2. **Application telemetry:** handlers, dependencies, DB, and business outcomes.

Only by joining both sides via trace/correlation IDs and timestamps can teams reliably pinpoint cross-layer root causes.

## 21. Azure CLI: inspecting configuration without exposing secrets

Read-only example commands in **Azure Cloud Shell Bash** or a configured Azure CLI. Use the exact authorized subscription and never print connection strings or API keys.

~~~bash
az account show \
  --query "{subscription:name,id:id,tenant:tenantId}" \
  --output table
~~~

Inspect an existing Application Insights resource:

~~~bash
RG="rg-observability-lab"
APPINSIGHTS="appi-orders-lab"

az monitor app-insights component show \
  --resource-group "$RG" \
  --app "$APPINSIGHTS" \
  --query "{name:name,location:location,workspaceId:workspaceResourceId}" \
  --output json
~~~

Requires the proper Azure CLI/extension and an existing resource; command availability and query fields vary by API version. If `workspaceResourceId` is absent, inspect **non-sensitive** resource properties rather than guessing.

### Check diagnostic settings on a resource

~~~bash
RESOURCE_ID="<EXISTING_RESOURCE_ID>"

az monitor diagnostic-settings list \
  --resource "$RESOURCE_ID" \
  --output json
~~~

Diagnostic settings **are not application auto-instrumentation**: a resource may emit platform logs while lacking Java application spans.

### Check alert rules

~~~bash
az monitor metrics alert list \
  --resource-group "$RG" \
  --output table
~~~

Environments may also use log search alerts, activity log alerts, or newer alert rule types. Never assume zero alerts exist after running only `metrics alert list`.

### Guard Application Insights connection strings

A connection string configures telemetry ingestion/routing; **it is not a credential granting data-read access**. Avoid scattering it across source files and logs, manage it through config pipelines, and secure resources with RBAC and supported ingestion access controls. Do not confuse it with APIM subscription keys or Storage account keys.

## 22. Designing alerts tied to SLOs and actions

A good alert tells the on-call engineer **what to check or do**. Examples:

| Alert | Reference condition | Action |
|---|---|---|
| Rising error rate | 5xx/error SLI exceeds baseline over window | Inspect routes, traces, recent releases |
| Degraded p95 latency | p95 exceeds SLO under meaningful traffic | Find slow dependencies or saturation |
| Dependency 503/429 | Rising failure/throttle rate | Check quotas, backoff, downstream health |
| Queue backlog/age | Oldest job exceeds deadline | Scale workers, check DLQ/poison messages |
| API succeeds but business fails | Job completion ratio drops | Inspect async workflows and idempotency |
| Missing telemetry | Service loses heartbeats/telemetry | Check exporter, ingestion, networking |
| Cost spike | Unusual surge in log ingestion/retention | Adjust debug level/sampling, check loops |

### Do not rely solely on static percentage thresholds

A route receiving only a handful of requests overnight hits 100% failure from a single error, which may not warrant paging the entire team. Conversely, a payment route handling 100,000 requests/hour suffers major impact from even a 1% error spike.

Combine:

- Error rate AND **absolute error count**.
- Time window and traffic volume.
- Endpoint criticality.
- SLO/error budget and burn rate if using SRE practices.
- Region/service/version.
- Separating synthetic tests from real user traffic.
- Clear actionability.

### Action groups and incident response

Define recipients/on-call rotations, severity, escalation, dashboard links, runbooks, maintenance windows, and initial investigation hints. Never send sensitive payloads over alert emails/SMS. Afterward, record incident timelines and outcomes to refine alert rules.

## 23. Sampling, cardinality, and telemetry costs

Capturing 100% of requests and dependency spans can drive high ingestion, storage, and query costs while burying critical signals in noise.

### What is sampling?

**Sampling** selects a subset of traces/telemetry to retain. It cuts cost at the expense of omitting some individual requests from detailed trace storage.

- **Head sampling:** decides early at trace start based on context, service/route/rules.
- **Tail sampling:** decides after collecting spans so errors/high-latency traces are kept; requires compatible collector pipelines and carries overhead.
- **Adaptive sampling:** adjusts rates dynamically with load per SDK/agent/pipeline features.

**Never mix uncoordinated sampling across gateway, apps, and collectors**: keeping disjoint subsets of spans creates broken, incomplete traces.

### Counting requests when sampled

If you capture only 10% of requests, `count()` over telemetry tables does not reflect true traffic. Account for **sampling weights** (such as `ItemCount` in some schemas) or use **platform metrics** for accurate SLI counts. For error rates, head sampling can skew results if routes/outcomes are sampled unevenly.

### Cardinality

Metric tags containing `orderId`, `userId`, full URLs with IDs, or `traceId` explode into millions of time series. Use:

- Route templates instead of full paths.
- Fixed service names instead of ephemeral hostnames when aggregating.
- Error codes from a bounded taxonomy.
- Standardized environments, regions, methods, and status codes.

Specific IDs belong in **access-controlled logs/traces**, not per-request metric dimensions.

### Retention

Set log/trace retention based on investigation needs, compliance, and budget. Retaining raw telemetry forever is not an observability requirement. Keep aggregated metrics longer and detailed traces shorter per policy. For security/audit logs with legal requirements, maintain separate compliant retention rather than trimming arbitrarily.

## 24. Privacy and security of observability systems

Telemetry can reveal routes, tenants, table names, database errors, hostnames, and even personal data. When enabling auto-tracing, inspect **what fields agents collect by default**, not just custom log lines written by your team.

### Data that normally should NOT be collected

- `Authorization` headers, access/refresh tokens, API keys.
- Cookies, session IDs, or passwords.
- Raw credit card or payment details.
- HTTP request/response bodies and message payloads containing PII unless explicitly approved.
- Full URLs with query strings carrying emails, tokens, or sensitive IDs.
- SQL queries containing sensitive data literals.
- Baggage carrying customer details or tenant secrets.

### Safeguards

1. **Redact before ingestion** wherever possible; do not rely solely on query-time masking.
2. Standardize route templates and error-code taxonomies.
3. Enforce least-privilege Azure RBAC on workspaces, App Insights, and APIM.
4. Separate production telemetry from dev/staging per permissions.
5. Manage networking/Private Link, ingestion endpoints, and export targets per supported features.
6. Review data residency, cross-region replication, and retention.
7. Review sampling/collection policies with security/compliance teams.
8. Audit enabling verbose tracing or querying sensitive data.

### Trace context does not authenticate callers

External actors can forge `traceparent` or correlation IDs to pollute telemetry. Enforce AuthN/AuthZ via Entra ID, tokens/managed identities, or approved mechanisms. Treat incoming tracing metadata as **untrusted client input** at the perimeter: validate format, bound length, and never use it for access decisions.

## 25. Cross-service incident diagnostic flowchart

~~~mermaid
flowchart TD
  A["Alert: 5xx / p95 / job deadline"] --> B["Identify route, region, time, release"]
  B --> C["Locate request in APIM/gateway"]
  C --> D{"Backend trace/correlation present?"}
  D -->|Yes| E["Inspect server spans + dependencies"]
  D -->|No| F["Check propagation, sampling, instrumentation"]
  E --> G{"Which dependency failed?"}
  G -->|HTTP/DB| H["Check timeouts, 429/503, health, network"]
  G -->|Queue/worker| I["Check backlog, DLQ, attempts, business status"]
  G -->|Application| J["Exceptions, config, resource saturation, release"]
  H --> K["Mitigate / roll back / fail over per runbook"]
  I --> K
  J --> K
  F --> K
  K --> L["Verify SLO + business outcomes"]
  L --> M["Post-incident: action items, telemetry gaps, cost"]
~~~

Key principle: **failures in the tracing pipeline must never break the primary API**, unless the organization has strict mandatory audit-halt requirements. Exporters should generally run asynchronously with bounded buffers; dropped telemetry should trigger alerts without blocking business requests.

## 26. Case study: payment API failing after deployment

### Context

An ordering application includes:

- Azure Front Door at the edge.
- APIM handling auth/quotas/routing.
- Java Orders API on Azure Container Apps.
- Java Payments API on AKS.
- Service Bus publishing `PaymentConfirmed` jobs.
- Azure Functions updating order status.
- Azure SQL Database and Storage.
- Workspace-based Application Insights consolidating application telemetry.

After releasing `payments-api v2.3.7`, customers see rising HTTP 503/504 errors. High-level dashboards show low CPU, so “not enough CPU” lacks evidence.

### Investigation

1. Slice error rates by route/region/5m; isolate that only `POST /payments` is impacted.
2. Gateway logs confirm most failures are backend timeouts, not APIM throttling.
3. Look up a failing request by `OperationId`/trace ID.
4. Distributed traces show 70ms in APIM, 120ms in Orders API, 2.7s in Payments API, and 2.5s in the SQL dependency.
5. Compare releases: Payments API `v2.3.7` introduced a missing-index SQL query or N+1 queries (hypothesis verified via query telemetry/plan), absent in `v2.3.6`.
6. Check SQL metrics (duration/throttling/connection pool), logs, and app version.
7. Once regression is confirmed, roll back or toggle feature flag per runbook while preparing a tested index/query fix.
8. Verify 5xx and p95 drop and payment completion rates recover.
9. Audit retried/DLQ messages to avoid duplicate charges during replay.

### Required fields in the incident report

| Field | Example content |
|---|---|
| Incident start/end | UTC timestamps and how determined |
| Impact | Failed valid request count, impacted regions, and customers |
| Trace evidence | Access-controlled trace ID, failing span/dependency |
| Root cause | Proven code, config, or query change |
| Mitigation | Approved rollback, retry cap, capacity, or circuit breaker |
| Recovery validation | SLOs, business completion, backlog/DLQ, data reconciliation |
| Prevention | Regression tests, telemetry gaps closed, alerts, load tests |
| Cost impact | Retry compute, Log Analytics ingestion, downstream usage |

This is a **learning scenario**, not an actual Azure incident extracted from a live customer system.

## 27. Designing dashboards for operations teams

A useful dashboard hierarchy spans three tiers:

### Tier 1 — Executive/SLO overview

- Request volume across critical APIs.
- Availability SLI and error budget.
- p95/p99 latency and 5xx rates.
- Business completion rates for async workflows.
- Active incidents and deployment status.

### Tier 2 — Service ownership

- Service name/version/region.
- Top routes by latency/failures.
- Dependency map, target latencies/exceptions.
- Pod/revision health, CPU/memory/GC, throughput.
- Queue backlogs, retry counts, and DLQ depth.
- Links to traces and log queries.

### Tier 3 — Incident drill-down

- Filters by UTC window/region/route.
- Trace ID, service, version, span tree/timeline.
- Gateway vs. backend status.
- Redacted exception stacks.
- Dependency errors and retry attempts.
- Deployment/change timeline.
- SLO recovery and mitigation decisions.

Dashboards must never display raw request bodies or tokens. Ensure drill-down links respect workspace RBAC and environment boundaries.

## 28. Hands-on lab: tracing API errors across three services

### Objective

A lab consisting of:

- Gateway or entry API (APIM lab if permitted).
- Java Orders API.
- Java Inventory API.
- Queue/Function worker or mock downstream.
- Application Insights/Log Analytics or an approved OTel collector/viewer.

Run on **dedicated lab resources**; creating Azure resources may incur charges.

### Part A — Telemetry design

1. Diagram the call chain from client through gateway to both Java services.
2. Choose `service.name`, environment, version, and route templates for each service.
3. Define availability and p95 SLIs for `POST /orders`.
4. Define an error-code taxonomy such as `INVENTORY_TIMEOUT`, `PAYMENT_UNAVAILABLE`.
5. Plan W3C `traceparent` propagation over HTTP; explain trace IDs vs. span IDs.
6. Choose a job ID for asynchronous steps if present.
7. Specify which headers/body fields require redaction.
8. Choose sampling and retention suited to lab scale.

### Part B — Instrumentation

1. Enable Application Insights or a supported OpenTelemetry exporter for Java services.
2. Confirm every incoming HTTP request creates a server span.
3. Add a custom span for `inventory.reserve`.
4. Enable dependency instrumentation for HTTP/SQL in the lab.
5. Emit structured logs with `traceId`/`spanId` and `errorCode`.
6. If using a queue, pass trace context in message properties and link the consumer.
7. Verify version/resource attributes when deploying a new revision.
8. Send a successful HTTP request and inspect the end-to-end trace.

### Part C — Controlled fault injection

In a **test environment with zero real data**:

1. Have Inventory API return HTTP 503 on selected test requests.
2. Introduce slow dependency responses to observe timeouts.
3. Trigger a 400 validation error to contrast with a 500 server error.
4. Call through the gateway and record UTC timestamps and trace IDs.
5. Locate the request in `AppRequests` or your tracing backend.
6. Inspect matching `AppDependencies` and `AppExceptions`.
7. Write a KQL query summarizing failure rates/p95 over 30–60 minutes.
8. Verify logs across both services share the same trace ID.
9. Test a retry showing attempt metadata without duplicate side effects.
10. If using a queue, observe backlog/DLQ and verify business outcomes.

### Part D — Alerting and recovery

1. Configure a test alert for failure rate or latency with minimal thresholds.
2. Link the alert to a dashboard/query/runbook.
3. Trigger the fault in the lab and confirm alert firing/resolution.
4. Fix the service/mock dependency and verify recovery.
5. Audit any incomplete traces caused by sampling or broken propagation.
6. Write an incident summary: symptom, root cause, mitigation, lessons learned.
7. Check telemetry costs and clean up lab resources per approved procedure.

### Self-check questions

**Question 1.** What different kinds of questions do metrics, logs, and distributed traces answer?

**Question 2.** How do trace ID and span ID differ? Which W3C header carries parent context over HTTP?

**Question 3.** If a request succeeds at APIM but an Azure Function fails processing the queue 10 minutes later, does the HTTP SLI detect the business failure?

**Question 4.** When seeing an APIM HTTP 502, why must you inspect both backend status and policy/gateway logs?

**Question 5.** Does adding a Java agent to Orders API automatically create spans inside Payments API? What is needed downstream?

**Question 6.** When a message is redelivered, is a new trace ID valid, and which ID must remain stable to prevent duplicate processing?

**Question 7.** Why shouldn't metric names or labels contain `orderId` or full URLs with IDs?

**Question 8.** With 10% sampling, can `count()` alone yield exact production request totals?

**Question 9.** How do Application Insights and a Log Analytics workspace differ?

**Question 10.** If a user receives 504 while the backend commits later, what must happen before retrying payment?

**Question 11.** Is an HTTP 401 from an incorrect password automatically an availability SLO breach?

**Question 12.** How do you tell whether an error spike came from a deployment rather than merely higher traffic?

**Question 13.** Which data must never enter tracing headers, baggage, or application logs?

**Question 14.** Why isn't low CPU on a dashboard enough to rule out database or dependency bottlenecks?

**Question 15.** How can an alert based solely on overall p95 latency without route/region splits mislead operators?

**Completion criteria:** learners define SLIs/SLOs, explain context propagation, design Java instrumentation across gateway/services/queues, write KQL queries to isolate errors, build an incident runbook, and evaluate telemetry sampling, security, and cost.

## Conclusion

**API observability and cross-service error tracing** require connecting gateway, application, dependency, queue, and platform signals into one causal picture. **Metrics** show trends and SLOs; **logs** provide event detail; and **distributed traces** using W3C Trace Context reveal where a request traveled and which hop slowed down or failed.

On Azure, **Azure Monitor, Application Insights, Log Analytics, API Management diagnostics, and OpenTelemetry** provide the building blocks, provided they are configured consistently across service names, routes, trace IDs, releases, and data policies. By combining **KQL, actionable alerts, idempotency/retry budgets, telemetry security, sampling/retention, and incident runbooks**, operations teams can isolate root causes faster, cut time to recovery, and protect both user experience and Azure infrastructure spend.
