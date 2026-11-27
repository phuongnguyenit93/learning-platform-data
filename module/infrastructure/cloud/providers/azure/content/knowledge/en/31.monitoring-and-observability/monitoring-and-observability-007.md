# OpenTelemetry and Distributed Tracing on Azure

A customer places an order on an e-commerce application. API Gateway routes the request to the Orders service on Azure App Service, Orders calls Pricing running on Azure Kubernetes Service (AKS), queries Azure SQL Database, and publishes a message to Azure Service Bus. A worker processes the message, stores an invoice in Azure Blob Storage, and emits a status notification. The user only sees a "Request timeout" message after 8 seconds. Which service was slow? Which connection failed? Was it the database, network, queue, or a retry policy adding latency?

**Distributed tracing** tracks **a logical operation across multiple processes and services** under a shared trace ID. **OpenTelemetry (OTel)** provides open-standard APIs, SDKs, semantic conventions, instrumentation libraries, and export protocols. On Azure, you can use **Azure Monitor Application Insights**, the **Azure Monitor OpenTelemetry Distro**, the Java agent, the OpenTelemetry Collector, and related observability tools to collect, store, query, and analyze traces.

This lesson belongs to the **Monitoring and Observability** chapter in the **CLOUD_PROVIDERS_AZURE** module: tying together subscriptions, resource groups, Entra ID, networking, App Service, AKS, Functions, data, and cost into a verifiable Azure tracing and operations workflow.

**Scope:** language-neutral tracing fundamentals, with hands-on implementation focused on Spring Boot/Java running on Azure App Service or AKS. Examples use hypothetical parameters, service names, and connection strings. Never create production Azure resources or push personal data into telemetry. Agent versions, configs, and defaults evolve; consult current Microsoft Learn / OpenTelemetry documentation before releasing to production.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **metrics, logs, and traces** and know when each signal is needed.
2. Describe **trace**, **span**, **trace ID**, **span ID**, **parent**, **attributes**, **events**, **status**, and **links**.
3. Explain distributed traces as causal relationships, not merely timestamped log lines.
4. Understand propagation via W3C HTTP headers **`traceparent`**, **`tracestate`**, and **`baggage`**.
5. Distinguish span kinds **SERVER, CLIENT, PRODUCER, CONSUMER, and INTERNAL**.
6. Design **`service.name`**, **`service.namespace`**, **`deployment.environment.name`**, **`service.version`**, and bounded attribute cardinality.
7. Understand auto-instrumentation, manual instrumentation, and the OpenTelemetry Java API/SDK.
8. Instrument a Spring Boot app with the **Azure Monitor Application Insights Java agent** without baking secrets into images.
9. Create custom spans, attributes, events, exceptions, and statuses using the Java OpenTelemetry API.
10. Propagate context across HTTP, async executors, message queues, and controlled retries.
11. Distinguish the **Azure Monitor exporter/agent** from an **OTLP Collector**, recognizing that raw OTLP cannot be pointed directly at arbitrary Azure Monitor URLs.
12. Use Application Insights Application Map, End-to-end transaction details, and KQL on **AppRequests, AppDependencies, AppTraces, and AppExceptions**.
13. Explain head sampling, parent-based sampling, tail sampling, rate-limited sampling, and their cost impact.
14. Protect PII, secrets, SAS tokens, access tokens, and multi-tenant data when collecting traces.
15. Diagnose missing spans, duplicate telemetry, broken propagation, exporter errors, clock skew, and sampling.
16. Establish SLOs, alerting, retention, capacity planning, and production tracing runbooks.

## 2. Why Isn't a Simple Correlation ID Enough?

### 2.1. Distributed Systems Have Multiple Clocks and Boundaries

~~~mermaid
flowchart LR
    U["Client"] --> GW["API Gateway"]
    GW --> OR["Orders API - App Service"]
    OR --> PR["Pricing - AKS"]
    OR --> DB["Azure SQL"]
    OR --> SB["Azure Service Bus"]
    SB --> WK["Invoice Worker - Container Apps"]
    WK --> BL["Azure Blob Storage"]
    OR --> AM["Azure Monitor / Application Insights"]
    PR --> AM
    WK --> AM
~~~

If each service logs independently, operators struggle to determine:
- Which requests belong to the same order?
- Which service initiated which child operation?
- Which operations ran in parallel?
- Did the 2-second delay happen in Pricing, SQL, or Service Bus?
- Did SDK retries trigger multiple network attempts?
- How long did the worker take before processing the message?
- Did the failure occur during the HTTP request or asynchronously after the response returned?

A homemade request ID helps filter logs, yet usually **fails to capture the parent-child tree, span durations, statuses, and asynchronous links**. Distributed tracing adds the data model needed to assemble those events into one trace.

### 2.2. Traces, Metrics, and Logs Complement Each Other

| Signal | Question Answered | Example |
|---|---|---|
| **Metrics** | Is there an incident, and how widespread is it? | p95 latency = 1.8 s; error rate 4% |
| **Logs** | What happened in detail? | `SQLException` or validation error details |
| **Traces** | Where did one specific request travel, and which part was slow? | Orders → Pricing 900 ms → SQL 30 ms |
| **Profiles** (if used) | Where are CPU/memory consumed? | Java allocations or hot methods |

Never use traces to replace all metrics; **sampling** can exclude most requests from trace storage. Never dump full raw payloads into logs to "replace tracing," as doing so risks PII leaks, bloats volume, and lacks causal structure.

### 2.3. When Distributed Tracing Is Needed

- Microservices communicating over HTTP/gRPC.
- Azure SDK clients calling Storage, Cosmos DB, Service Bus, Event Hubs, or Azure SQL.
- Async workers and serverless Functions.
- Requests fanning out across multiple child dependencies.
- Incidents with high p99 latency or intermittent timeouts.
- Multi-layer retries, circuit breakers, and queue backlogs.
- Canary deployments comparing behavior across versions.
- Multi-region routing or hybrid networking.

For a single-process app running one simple SQL query, structured logs and metrics may suffice initially without introducing a complex Collector.

## 3. OpenTelemetry Tracing Data Model

### 3.1. A Trace Is a Logical Operation

A **trace** represents a chain or directed graph of related operations. Each trace carries a **128-bit trace ID**, typically rendered as 32 hex characters, e.g.:

~~~text
traceId = 4bf92f3577b34da6a3ce929d0e0e4736
~~~

A trace ID **is not a customer ID or order number**. Avoid turning meaningful personal or business IDs into trace IDs; trace IDs should be generated randomly by the SDK.

### 3.2. A Span Is a Unit of Work

A **span** contains:
- Name: `orders.checkout`, `HTTP GET`, `db.query`, etc.
- Span ID (64-bit, typically 16 hex characters).
- Parent Span ID or parent context reference.
- Start/end timestamps and duration.
- Span kind: SERVER, CLIENT, PRODUCER, CONSUMER, INTERNAL.
- Attributes: key-value pairs for analysis.
- Events: timestamped annotations inside the span.
- Status: typically UNSET or ERROR.
- Links: associations to other spans outside a strict parent-child tree.

Spans can be very brief, and **every span must end via `span.end()`**. Forgetting to end a span can prevent export or corrupt trace visualization.

### 3.3. Parent–Child Relationships Build the Call Tree

~~~mermaid
flowchart TD
    A["SERVER: POST /orders | 1200 ms"]
    A --> B["CLIENT: Pricing HTTP | 780 ms"]
    A --> C["CLIENT: SQL INSERT | 180 ms"]
    A --> D["PRODUCER: Service Bus send | 65 ms"]
    B --> E["SERVER: Pricing GET /quotes | 700 ms"]
    E --> F["CLIENT: Redis GET | 15 ms"]
    D -. "async link / propagated context" .-> G["CONSUMER: invoice-worker process | 350 ms"]
~~~

When the same trace context propagates, **downstream spans** share the trace ID and reference their caller as parent. However, asynchronous systems often use **span links** instead of direct parent-child links; drawing a dashed arrow does not prove the exact semantics of every broker or instrumentation library.

### 3.4. Span Kinds

| Kind | Context | Example |
|---|---|---|
| SERVER | Handles an inbound request from a remote client | Spring MVC receiving `POST /orders` |
| CLIENT | Calls a remote service | Orders calling Pricing over HTTP |
| PRODUCER | Creates/sends a message | Publishing a command to Service Bus |
| CONSUMER | Receives/processes a message | Worker handling an event |
| INTERNAL | Work inside a single process | Validating an order, calculating tax |

**An INTERNAL span is not a network dependency.** Backends may map spans to requests/dependencies based on kind, integration, and instrumentation. Do not assume an INTERNAL span always shows up as an HTTP request in Application Insights.

### 3.5. Span Attributes and Events

Example:

~~~text
Span name: orders.validate
Span kind: INTERNAL
Attributes:
  order.channel = "mobile"
  order.line_count = 3
  deployment.environment.name = "staging"
Events:
  validation.started
  validation.completed
Status:
  UNSET (no error)
~~~

Attributes must stay bounded and **never contain full payment tokens, customer emails, credit cards, raw SQL with sensitive literals, or request bodies**.

### 3.6. Status and Exceptions

- A successful span normally leaves its status **UNSET** rather than setting OK on everything.
- When a diagnostic business error or technical exception occurs: record the exception event and set status ERROR as appropriate.
- An HTTP 4xx is not automatically a system failure: a `400` validation failure may be expected; set ERROR status in line with semantic conventions and agreed SLOs.
- A caught exception that is handled cleanly does not automatically turn the entire trace into an error.

Never rely on span exceptions as a substitute for application error handling or user-facing error responses.

## 4. W3C Trace Context and Context Propagation

### 4.1. The `traceparent` Header

An HTTP request can carry the header:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Structure:

~~~text
version-trace-id-parent-id-trace-flags
00 - 32 hex characters - 16 hex characters - 2 hex chars
~~~

In this example:
- **00:** `traceparent` version.
- **4bf9...4736:** trace ID.
- **00f0...02b7:** caller's span ID passed to the callee.
- **01:** sampled flag enabled.

This header carries no security guarantee. An attacker can forge `traceparent`; never treat it as **authentication, authorization, or proof of a trusted caller**.

### 4.2. `tracestate` and `baggage`

- **`tracestate`:** carries vendor-specific tracing metadata per W3C specs within size limits.
- **`baggage`:** key-value pairs propagated across service boundaries; useful for contextual propagation, but easily leaks if forwarded to third parties.
- **Attributes:** attached to individual spans, not automatically forwarded across downstream hops like baggage.
- **Log correlation:** typically injects `trace_id` and `span_id` into logs without copying all baggage.

Never put usernames, emails, `Authorization` headers, home addresses, JWTs, or sensitive tenant data into `baggage`. Treat both `baggage` and `traceparent` as **untrusted input** at inbound boundaries.

### 4.3. Inject and Extract

- **Inject:** before sending an HTTP request or message, instrumentation writes `traceparent`/`tracestate` and permitted metadata into the carrier.
- **Extract:** the receiver reads headers, reconstructs the parent context, and starts a new child span.
- **Propagate:** if continuing the trace is permitted, the child keeps the trace ID and links to its caller.
- **Trust boundary:** enforce allowlists and size limits on incoming baggage; never copy arbitrary baggage blindly into internal logs.
- **Fallback:** if no valid `traceparent` arrives, the server starts a new root span.

~~~mermaid
sequenceDiagram
    participant A as Orders API
    participant P as OTel Propagator
    participant H as HTTP Headers
    participant B as Pricing API
    A->>P: Inject current context
    P->>H: traceparent / tracestate
    H->>B: GET /price
    B->>B: Extract remote context
    B->>B: Start SERVER child span
    B-->>A: Response
~~~

### 4.4. Traces with Multiple Roots or Split Traces

If the caller fails to inject headers or the callee fails to extract them, Pricing starts a fresh trace ID. Application Map might still infer an HTTP dependency, yet **you lose the connected end-to-end trace**.

Other causes include:
- An HTTP gateway or proxy strips `traceparent`.
- An async worker loses thread-local context.
- Custom message-broker code fails to copy context into application properties.
- Two instrumentation libraries are installed simultaneously in the runtime.
- Inconsistent sampling decisions across services.
- Libraries configured with incompatible propagation formats (e.g., B3 vs. W3C).

## 5. Resource Attributes and Service Naming

### 5.1. Resources Describe the Telemetry Source

An OpenTelemetry **Resource** attaches metadata about the service, process, and cloud environment to spans, metrics, and logs.

Attributes to plan upfront:

| Attribute | Example | Purpose |
|---|---|---|
| `service.name` | `orders-api` | Stable service identifier |
| `service.namespace` | `commerce` | Group related services |
| `service.version` | `2.4.1` | Compare regressions across releases |
| `deployment.environment.name` | `production` | Separate environments |
| `cloud.provider` | `azure` | Cloud provider |
| `cloud.region` | `southeastasia` | Azure region when detected |
| `service.instance.id` | system-generated instance ID | Distinguish replicas when needed |
| `k8s.namespace.name` | `commerce-prod` | AKS context when detected |

Never embed **user IDs or order IDs** in `service.name` or high-cardinality resource attributes. Letting `service.name` vary per Pod or instance turns Application Map into thousands of unreadable nodes.

### 5.2. Cloud Role Name in Application Insights

Azure Monitor / Application Insights uses **Cloud Role Name** to group services on Application Map. When multiple Java services export to the same resource, assign **distinct, stable** role names such as `orders-api`, `pricing-api`, and `invoice-worker`.

If every service shares a generic name like `"application"`, Application Map blends them together and distorts dependency analysis. With the Application Insights Java agent, configure the role name via agent config while managing `service.name`/OTel Resource attributes per supported SDK/agent integration.

### 5.3. Span Names Must Have Low Cardinality

Avoid:

~~~text
GET /orders/8d3f5ac9-...    (one span name per order)
payment to customer@example.com
query invoices for tenant-391028
~~~

Prefer:

~~~text
GET /orders/{orderId}
orders.checkout
payment.authorize
invoice.persist
~~~

Specific IDs (when permitted) belong in logs or attributes under PII and cardinality rules—never as dynamic per-request span names or metric labels.



## 6. OpenTelemetry Architecture: API, SDK, Instrumentation, and Exporters

### 6.1. Components

~~~mermaid
flowchart TD
    APP["Application code"] --> API["OTel API: Tracer / Span / Context"]
    LIB["HTTP/JDBC/Messaging libraries"] --> INST["Auto instrumentation"]
    API --> SDK["OTel SDK: processors / sampler / resources"]
    INST --> SDK
    SDK --> EXP["Exporter"]
    EXP --> COL["OTLP Collector - optional"]
    EXP --> AZ["Azure Monitor exporter / Java agent path"]
    COL --> BACK["Supported observability backend"]
    AZ --> AI["Application Insights / Azure Monitor"]
~~~

**Core concepts:**

- **OpenTelemetry API:** interfaces to create spans, attach attributes, and manage context. Having only the API **does not export any data**.
- **OpenTelemetry SDK:** concrete implementation providing tracer providers, processors, samplers, and exporters.
- **Instrumentation:** libraries or Java agents that automatically emit spans for HTTP servers/clients, JDBC, messaging, and supported frameworks.
- **Exporter:** ships telemetry to a destination, such as an OTLP endpoint or Azure Monitor.
- **Collector:** standalone service that receives, processes, batches, filters, and exports telemetry; optional, not required in every architecture.
- **Backend:** stores, queries, and visualizes traces, such as Azure Monitor Application Insights.

### 6.2. Auto-Instrumentation vs. Manual Instrumentation

| Approach | Captures | When to Use |
|---|---|---|
| Auto-instrumentation | HTTP requests, JDBC calls, many SDKs/network clients | Fast setup with minimal code |
| Manual API spans | Domain steps: validation, pricing, fraud checks | When business operations need visibility |
| Instrumentation libraries | Specific frameworks | When supported by agent/SDK |
| Collector processing | Filtering, redaction, routing downstream | Multi-service observability governance |

Auto-instrumentation cannot understand your business domain. An outbound HTTP span `POST /payments` reveals a 3-second dependency, yet cannot explain "why the order was rejected" or "whether the invoice job was enqueued." Manual spans fill that gap.

### 6.3. Semantic Conventions

OpenTelemetry defines **semantic conventions** for HTTP, RPC, databases, messaging, and cloud metadata. Modern libraries commonly use attribute keys such as:

~~~text
http.request.method
http.response.status_code
server.address
url.scheme
db.system.name
messaging.system
messaging.operation.name
error.type
~~~

Actual key names depend on the OpenTelemetry Semantic Conventions version and instrumentation in use. Upgrading the Java agent can shift attribute keys between releases. Never build production KQL depending rigidly on a single field without a backward-compatibility plan.

### 6.4. Never Initialize Two Unintended TracerProviders/Exporters

A common mistake:

1. Attach the Application Insights Java agent via JVM args.
2. Import another OpenTelemetry SDK initializing `GlobalOpenTelemetry`.
3. Enable a Spring/Micrometer tracing exporter simultaneously.
4. All three auto-instrument Spring MVC.

The result is **duplicate spans, broken parent trees, doubled telemetry, and higher bills**. Pick **one primary tracing pipeline** and coordinate supporting libraries per documented compatibility. When using the Java agent, application code typically needs only **`opentelemetry-api`** for custom spans rather than adding a separate SDK/exporter.

## 7. Azure Monitor, Application Insights, and Log Analytics

### 7.1. Three Easily Confused Concepts

- **Azure Monitor:** overall Azure monitoring and observability service covering metrics, logs, and alerts.
- **Application Insights:** the APM capability analyzing requests, dependencies, exceptions, Application Map, and distributed transactions.
- **Log Analytics workspace:** stores and queries structured logs using **Kusto Query Language (KQL)** in workspace-based Application Insights.

Diagram:

~~~mermaid
flowchart LR
    O["OTel instrumented app"] --> AG["Azure Monitor OpenTelemetry Distro / Java agent"]
    AG --> AI["Application Insights resource"]
    AI --> LA["Log Analytics workspace"]
    LA --> KQL["KQL / Alerts / Workbooks"]
    AI --> MAP["Application Map / Transaction details"]
~~~

**Traces** are the OpenTelemetry data model; **Application Insights** is one backend and visualization layer. Not every trace concept from every vendor maps identically into the Application Insights schema.

### 7.2. Workspace-Based Application Insights

In the current model, application telemetry lands in tables such as:

| Table | Typical Telemetry |
|---|---|
| **AppRequests** | Server / inbound request telemetry |
| **AppDependencies** | HTTP/JDBC/remote dependency calls and many custom internal spans per mapping |
| **AppTraces** | Collected log/tracing messages |
| **AppExceptions** | Exception details |
| **AppEvents** | Custom events when supported by exporter/integration |
| **AppMetrics** | Selected custom/application metrics per ingestion mode |
| **AzureDiagnostics / Resource-specific tables** | Resource diagnostic logs, distinct from OTel traces |

Exact tables depend on the exporter, workspace/resource config, and timing. **Never confuse `AppTraces` (log messages) with the full span tree**: request and dependency spans normally live in `AppRequests` and `AppDependencies`.

### 7.3. `OperationId` and Data Relationships

In Application Insights, **`OperationId`** serves as the correlation key for a distributed operation and maps to the W3C trace ID under compatible instrumentation pipelines. Tables commonly include **`Id`, `ParentId`, `OperationId`, `TimeGenerated`** among other columns.

- **`OperationId`:** retrieves all telemetry records belonging to one transaction.
- **`Id`:** unique ID of an individual request or dependency item.
- **`ParentId`:** links to the parent item/span.
- **`AppRoleName`:** logical service emitting the telemetry.
- **`DurationMs`:** measured duration for that item.
- **`Success`, `ResultCode`:** outcome recorded by instrumentation.

Sharing an `OperationId` **does not prove a service succeeded**; inspect parent links, time windows, and errors.

### 7.4. Application Map and End-to-End Transaction Details

In the portal, use:

1. **Application Insights → Application Map** to inspect instrumented services, dependencies, and health/performance.
2. **Transaction search** or Logs queries to locate a specific request.
3. **End-to-end transaction details** to inspect the request and child dependencies.
4. **Failures** to examine HTTP 5xx and exception patterns.
5. **Performance** to locate slow requests and breakdowns.
6. **Live Metrics** to watch near-real-time trends where configured.
7. **Logs (KQL)** for deep analysis and cross-checking.

When three services report to one Application Insights resource, configure distinct **Cloud Role Names** so Application Map doesn't collapse them into one node. When data spans multiple resources or workspaces, cross-resource querying depends on permissions and tool support.

## 8. Choosing a Telemetry Shipping Path

### 8.1. Option A: Java Agent → Azure Monitor Application Insights

~~~mermaid
flowchart LR
    J["Spring Boot JVM"] --> AG["Azure Monitor / Application Insights Java agent"]
    AG --> ING["Azure Monitor ingestion endpoint"]
    ING --> AI["Application Insights"]
~~~

Pros:
- Little or no business code changes for server and dependency telemetry.
- Tight integration between Java auto-instrumentation and the Azure Monitor backend.
- Agent settings for role, sampling, logs, and self-diagnostics.
- Fits Azure App Service, AKS/Container Apps, and JVM workloads where supported.

Cons:
- Tied to Java agent versions and its supported library matrix.
- Requires egress security and connection string configuration.
- Adds CPU, memory, network overhead, and ingestion cost.
- Must avoid attaching a duplicate `-javaagent` if platform auto-instrumentation is already enabled.

### 8.2. Option B: OpenTelemetry Java Agent → OTLP Collector → Backend

~~~mermaid
flowchart LR
    J["Spring Boot JVM"] --> OT["OpenTelemetry Java agent + OTLP exporter"]
    OT --> C["OTel Collector"]
    C --> DBG["Debug exporter - lab only"]
    C --> B["Supported backend/exporter"]
~~~

Pros:
- Routes OTLP to multiple observability backends where supported.
- Centralizes policies for batching, filtering, redaction, and networking.
- Suits polyglot organizations with many services and vendors.

Cons:
- Must operate the Collector: capacity, TLS, authentication, queues, retries, and upgrades.
- Not every exporter preserves every signal, sampling semantic, or Azure-specific feature.
- **The Azure Monitor Application Insights ingestion endpoint is not an arbitrary OTLP receiver.** Never set `OTEL_EXPORTER_OTLP_ENDPOINT` to the App Insights ingestion URL expecting direct OTLP ingestion to work.

### 8.3. Choosing the Right Fit

| Context | Starting Point |
|---|---|
| Spring Boot on App Service wanting quick Application Map | Azure Monitor Application Insights Java agent |
| AKS with multiple JVM services targeting Azure Monitor | Java agent/auto-instrumentation or Azure-supported approach |
| Multi-language services, multiple backends | OTLP → Collector → appropriate exporters |
| App with pre-configured OpenTelemetry SDK | Integrate exporter/distro without creating duplicate providers |
| Java native image | Follow dedicated Spring Boot native / OTel Java SDK guidance |
| Legacy app with mixed agents/SDKs | Plan migration carefully to prevent duplicate telemetry |

**Each JVM should have one tested primary instrumentation/export strategy.** Never run the Azure Monitor Java agent and the upstream OTel Java agent together just to be "more thorough."

## 9. Hands-On A: Spring Boot with the Azure Monitor Java Agent

### 9.1. Lab Architecture

~~~text
Spring Boot orders-api
    ├─ GET /health (framework endpoint)
    ├─ POST /orders/{id}/confirm
    ├─ HTTP client call
    └─ Manual span "orders.validate"
           ↓
Application Insights Java agent (auto + manual spans)
           ↓
Azure Monitor / Application Insights
           ↓
Application Map + KQL
~~~

In the lab, endpoints and the Application Insights resource belong to an authorized subscription. Never send traffic to production payment systems or databases; manual spans can wrap mock business logic.

### 9.2. Safe Resource Preparation

You need:
- An authorized **workspace-based Application Insights resource**.
- Its **connection string** (avoid legacy bare instrumentation keys).
- Azure App Service or a dev machine with a compatible JVM/Spring Boot app and agent.
- Read permissions on Application Insights / Log Analytics to verify results.
- Outbound HTTPS egress to ingestion endpoints with valid DNS/TLS.
- Never commit connection strings to repositories or bake them into public Docker images.

The connection string specifies the ingestion destination; it is **not a bearer token granting read access to Log Analytics**, yet should still be handled as sensitive configuration and kept out of source code and logs.

### 9.3. Running the Azure Monitor Java Agent

Per Microsoft Learn documentation consulted when authoring this lesson, an example Java agent release was **`applicationinsights-agent-3.7.9.jar`**. That version is illustrative from the time of writing; **verify current release/JDK compatibility, provenance, and checksums** before real use.

Bash example:

~~~bash
export APPLICATIONINSIGHTS_CONNECTION_STRING="<APP_INSIGHTS_CONNECTION_STRING>"

java \
  -javaagent:"/opt/agents/applicationinsights-agent-3.7.9.jar" \
  -jar "orders-api.jar"
~~~

Notes:
- **`-javaagent`** must appear before **`-jar`**.
- The JAR path must exist and come from a trusted artifact repository.
- Never download JARs from random URLs or skip integrity checks.
- Avoid passing real connection strings in `java -D` CLI flags visible in CI logs if policy forbids it.
- Do not attach a second OpenTelemetry agent to the same JVM.
- With Azure App Service Portal auto-instrumentation, check whether **the platform already attaches a Java agent** before adding `-javaagent` manually.

### 9.4. Identifying the Service via Role Name

In a lab, an agent config file such as **`applicationinsights.json`** can sit next to the agent JAR:

~~~json
{
  "role": {
    "name": "orders-api"
  },
  "sampling": {
    "requestsPerSecond": 5
  }
}
~~~

Role name drives Application Map. **`requestsPerSecond`** is a sampling target, not an API rate limiter, and does not guarantee capturing an exact 5 requests every second across every instance.

In multi-service deployments, Pricing and Invoice Worker should declare distinct role names.

If App Service manages auto-instrumentation itself, the platform uses dedicated JSON/environment settings; never overwrite agent files in the App Service portal without checking how the agent is loaded and configured.

### 9.5. Default Java Agent Sampling

Per current Microsoft Learn documentation, starting with **Java agent 3.4.0**, rate-limited sampling is enabled by default, typically targeting around **5 requests/second** along with correlated dependencies and logs for sampled requests. This differs from older versions that captured 100% of requests.

Consequences:
- A specific request may not appear in transaction search.
- Never treat a missing trace as proof the request never ran.
- When testing a single request, sampling may hide it immediately.
- If full visibility is needed for testing, adjust sampling **only in the lab**—never disable production sampling recklessly.
- Uncorrelated logs (not tied to a request) may follow different sampling rules; startup logs are generally preserved by default.
- **Live Metrics** has its own sampling/telemetry behavior and is not an exact mirror of stored Logs.

### 9.6. Running a Smoke Test

After startup, send a few requests to an authorized **lab endpoint**:

~~~bash
curl -i "http://localhost:8080/health"
curl -i -X POST "http://localhost:8080/orders/demo-123/confirm"
~~~

These URLs are illustrative, not built-in Spring Boot routes. If your app lacks these routes, see the controller example below or substitute a real lab endpoint.

In Application Insights:
1. Verify the resource and connection string target the right destination.
2. Generate traffic from the lab environment.
3. Inspect Requests, Dependencies, and Application Map.
4. Query Logs using the appropriate UTC window.
5. If data does not show immediately, allow normal ingestion delay and check agent diagnostics, network, and sampling.
6. Never declare failure after just 1–2 seconds.



## 10. Hands-On B: Writing Custom Spans in Spring Boot Java

### 10.1. When Is Manual Instrumentation Needed?

The Java agent automatically creates SERVER spans on HTTP controllers and CLIENT spans on supported HTTP/JDBC calls. However, internal steps like **pricing calculations, quota checks, or business-rule validation** lack dedicated spans.

Add **manual INTERNAL spans** to expose internal application stages. Never create another SERVER span duplicating the one already created by Spring MVC instrumentation.

### 10.2. Dependencies

In the Spring Boot app's `pom.xml`, add the **OpenTelemetry API**, aligning its version with your Java agent and dependency policy:

~~~xml
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-api</artifactId>
    <version>${opentelemetry.version}</version>
</dependency>
~~~

`${opentelemetry.version}` is a property defined by your project's **BOM / dependency management**; not every Spring Boot project defines it out of the box. Before building, select an API version compatible with your agent/runtime per OpenTelemetry docs. Typically **you do not need to add `opentelemetry-sdk`** when the Java agent already configures the provider and exporter and your app only calls the API.

### 10.3. Illustrative Spring Boot Controller

~~~java
package com.example.orders;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public final class OrdersController {
    private static final Tracer TRACER =
        GlobalOpenTelemetry.getTracer("com.example.orders.manual");

    @PostMapping("/{orderId}/confirm")
    public ResponseEntity<String> confirm(
            @PathVariable String orderId) {
        // The HTTP SERVER span is normally created by the Java agent.
        Span span = TRACER.spanBuilder("orders.confirm")
            .setSpanKind(SpanKind.INTERNAL)
            .startSpan();

        try (Scope ignored = span.makeCurrent()) {
            // Do not attach orderId directly to the span if policy treats it
            // as PII or high-cardinality data.
            span.setAttribute("orders.action", "confirm");
            span.setAttribute("orders.validation.mode", "standard");
            span.addEvent("orders.validation.started");

            if (orderId.isBlank()) {
                throw new IllegalArgumentException("Invalid order ID");
            }

            // Lab: simulate confirmation step without touching real DB/partners.
            span.addEvent("orders.validation.passed");

            return ResponseEntity.accepted()
                .body("Order accepted in lab");
        } catch (RuntimeException ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR, "orders confirmation failed");
            throw ex;
        } finally {
            span.end();
        }
    }
}
~~~

Key points:

- **`GlobalOpenTelemetry`** is populated by the Java agent/SDK when configured properly; importing only the API does not wire an exporter.
- **`SpanKind.INTERNAL`** represents a business step inside the request.
- **`makeCurrent()`** binds the context for child calls within the active execution scope.
- **`recordException()`** attaches an exception event without replacing HTTP error handlers.
- **`setStatus(ERROR)`** marks the span as failed; it is not an HTTP status code.
- **`span.end()`** in `finally` guarantees the span closes even when requests fail.
- **`orderId`** can be a personal or business identifier; never place raw values in span names or attributes before checking policy.

With auto-instrumentation active, you should see SERVER span `"POST /orders/{orderId}"` with child INTERNAL span `"orders.confirm"`. Without an agent/SDK, the API acts as a no-op; returning HTTP 202 **does not prove telemetry was exported**.

### 10.4. Add Events Instead of Too Many Spans

If an internal step is tiny and needs no standalone timing breakdown, attach events to the active span:

~~~java
Span current = Span.current();
current.addEvent("orders.price.checked");
current.setAttribute("orders.items.count", 3);
~~~

Never spawn hundreds of child spans for trivial operations inside a loop of thousands of items. Every span adds payload size, CPU, memory, and ingestion cost. Pick granularity that aids investigation and measurement.

### 10.5. `@WithSpan` Annotation

Some instrumentation packages support annotations:

~~~java
import io.opentelemetry.instrumentation.annotations.WithSpan;

@WithSpan("orders.fraud-check")
public boolean fraudCheck() {
    return true;  // lab stub
}
~~~

This requires the annotations dependency plus a Java agent/instrumentation supporting it. **Adding the annotation library alone does not guarantee telemetry.** Watch out for Spring AOP, self-invocation, and proxies, and verify the annotation actually triggers in your setup.

### 10.6. Verifying the Span Hierarchy

Target hierarchy for a valid POST:

~~~text
SERVER  POST /orders/{orderId}     50 ms
  INTERNAL orders.confirm          5 ms
    EVENT orders.validation.started
    EVENT orders.validation.passed
~~~

If making real outbound HTTP or JDBC calls through supported instrumentation, CLIENT child spans appear underneath. Never emit fake `"payment succeeded"` business events in a lab when no payment ran: telemetry must reflect real events, never fabricated outcomes in production.

## 11. Propagating Context Across Async Executors and Reactive Code

### 11.1. Why Is Context Lost?

OTel Context normally relies on **thread-local scope** in Java. When an HTTP request starts on thread A and hands work off to executor thread B:

~~~text
Thread A: SERVER span active
    |
    | submit task
    v
Thread B: no context unless propagated
    |
    v
New spans become separate roots or lose parent
~~~

Some Java auto-instrumentation handles standard executors and frameworks automatically. However, not every custom queue, thread pool, or reactive operator is covered; always verify real traces instead of assuming.

### 11.2. Capture and Restore Context

Plain Java example with a managed `Executor`:

~~~java
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import java.util.concurrent.Executor;

public final class AsyncTaskExample {
    private final Executor executor;

    public AsyncTaskExample(Executor executor) {
        this.executor = executor;
    }

    public void scheduleInvoiceTask() {
        Context captured = Context.current();

        executor.execute(() -> {
            try (Scope ignored = captured.makeCurrent()) {
                // Any new spans created here inherit the captured parent.
                doBusinessWork();
            }
        });
    }

    private void doBusinessWork() {
        // Illustrative stub; application-specific implementation.
    }
}
~~~

Manage the lifespan of captured contexts and tasks. Never hold an untrusted-baggage `Context` indefinitely inside a shared singleton. For tasks running hours later, prefer **explicit message context propagation** over relying on the old HTTP request's thread-local context.

### 11.3. Reactor / `CompletableFuture`

In Spring WebFlux, Reactor follows a different execution model than imperative thread-per-request:

- Threads can switch after `publishOn`/`subscribeOn`.
- `Context.current()` on the running thread may lack the parent unless context bridging is enabled.
- OTel–Reactor context propagation options vary by agent, Reactor, and Micrometer versions.
- Never call `block()` or `Thread.sleep()` on Netty event loops just to "stay on the same thread."
- Verify traces with integration tests when using `CompletableFuture`, Reactor, coroutines, or custom schedulers.

Avoid manually wrapping every callback with captured `Context` if framework instrumentation already propagates it; double propagation can attach wrong parents or leak context across requests.

### 11.4. Thread-Local Is Not Message Context

If a worker receives a message 20 minutes later, the originating HTTP thread is long gone. **You cannot rely on the same thread** to hold trace context. Inject context into **message attributes/properties**, and extract it on the receiver. When processing a batch of events, use **span links** back to each producer context rather than forcing all events under a single parent.

## 12. Distributed Tracing Across Azure Service Bus

### 12.1. Participants

~~~mermaid
flowchart LR
    API["Orders API"] --> SEND["PRODUCER: Service Bus send"]
    SEND --> Q["Azure Service Bus queue"]
    Q --> RECV["CONSUMER: invoice-worker process"]
    RECV --> BLOB["CLIENT: Blob upload"]
~~~

Producer and consumer usually run in separate processes at different times. Trace context must reside in message metadata understood by both sides. Some versions of the **Azure Service Bus Java SDK** and instrumentation propagate automatically; test actual behavior before writing custom propagation code.

### 12.2. Injecting with the OpenTelemetry Propagator

Transport-neutral example preparing a **`Map<String,String>`** carrier, whose entries are then copied into message application properties via the SDK adapter:

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.context.Context;
import java.util.HashMap;
import java.util.Map;

Map<String, String> headers = new HashMap<>();

GlobalOpenTelemetry.getPropagators()
    .getTextMapPropagator()
    .inject(
        Context.current(),
        headers,
        (carrier, key, value) -> carrier.put(key, value)
    );

// For a ServiceBusMessage, when the SDK does not propagate automatically,
// copy entries into application properties:
// headers.forEach((k, v) ->
//     serviceBusMessage.getApplicationProperties().put(k, v)
// );
~~~

Do this manually **only when the SDK/instrumentation does not already inject**. If `traceparent`/`tracestate` headers are already present, do not overwrite them with a fresh context. Message application properties must respect Azure Service Bus size/type limits and never carry secrets in baggage.

### 12.3. Extracting at the Consumer

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapGetter;

import java.util.Map;

// In a real app, read the map from the message SDK:
// receivedMessage.getApplicationProperties()
Map<String, Object> messageProperties = Map.of(); // lab placeholder
Map<String, String> headers = new java.util.HashMap<>();
messageProperties.forEach((key, value) -> {
    if (value instanceof String) {
        headers.put(key, (String) value);
    }
});

TextMapGetter<Map<String, String>> getter = new TextMapGetter<>() {
    @Override
    public Iterable<String> keys(Map<String, String> carrier) {
        return carrier.keySet();
    }

    @Override
    public String get(Map<String, String> carrier, String key) {
        return carrier.get(key);
    }
};

Context remote = GlobalOpenTelemetry.getPropagators()
    .getTextMapPropagator()
    .extract(Context.root(), headers, getter);

Tracer tracer = GlobalOpenTelemetry.getTracer("com.example.invoice");

Span consumer = tracer.spanBuilder("invoice.process")
    .setParent(remote)
    .setSpanKind(SpanKind.CONSUMER)
    .startSpan();

try (Scope ignored = consumer.makeCurrent()) {
    // Process message with bounded concurrency and idempotency.
} finally {
    consumer.end();
}
~~~

**Important:** this is an **API skeleton**, not copy-paste production code: read headers from the real message, handle nulls, enforce size caps, and normalize string values per the Azure Service Bus SDK. Some messaging libraries already emit a CONSUMER span; adding a manual one on top will duplicate spans. Only fill confirmed instrumentation gaps.

### 12.4. Tracing Does Not Guarantee Exactly-Once Delivery

In queues:
- A producer may resend a message if an ACK is lost.
- A consumer may retry after doing most of the work.
- Dead-letter queues and lock renewals have their own semantics.
- A message may be picked up by another worker minutes later.
- Traces may record **multiple consumer spans** across attempts.

Traces reveal **retries, `deliveryCount`, and queue lag**, but cannot stop duplicate invoices. Use **stable message IDs, idempotency keys, database unique constraints, or transactional outboxes** per business rules.

### 12.5. Parent or Link?

When a consumer processes exactly one message, setting the extracted remote context as parent works if supported by your framework/pattern. For:
- Batches of multiple messages,
- Fan-in from multiple producers,
- Long-running workflows,
- Reprocessing or backfills,

**span links** model multi-producer relationships far better than parents. A span has at most one parent, yet can link to many contexts. Follow OpenTelemetry messaging semantic conventions and your architecture.

## 13. Hands-On C: OTLP Collector in Development

### 13.1. Why Run a Collector Lab?

To understand **standard OpenTelemetry** independently of the Azure Monitor exporter. A Collector receives OTLP from apps, batches telemetry, and prints debug logs before you choose any backend. This lab **uses no Application Insights connection string** and sends nothing to production Azure.

### 13.2. Minimal Pipeline

~~~mermaid
flowchart LR
    APP["OpenTelemetry Java agent"] -->|OTLP HTTP/gRPC| C["Collector OTLP receiver"]
    C --> ML["memory_limiter"]
    ML --> BA["batch processor"]
    BA --> DE["debug exporter - lab only"]
~~~

Sample localhost Collector config:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317
      http:
        endpoint: 127.0.0.1:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 256
  batch: {}

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [debug]
~~~

**This is a demo Collector config.** In containers or Kubernetes, bind addresses differ, and receivers must be secured with TLS, authentication, and network policies whenever exposed beyond localhost. Never expose `0.0.0.0:4317` to the public Internet. Collector components vary by distribution/release; confirm your build includes `memory_limiter`, `batch`, and `debug`.

### 13.3. Launching a Standalone OTel Java Agent

A pure OTLP setup can use the **upstream OpenTelemetry Java agent** instead of the Azure Monitor Java agent:

~~~bash
export OTEL_SERVICE_NAME="orders-api"
export OTEL_TRACES_EXPORTER="otlp"
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://127.0.0.1:4318"

java -javaagent:"/opt/agents/opentelemetry-javaagent.jar" \
  -jar "orders-api.jar"
~~~

Fetch the agent JAR from an official source, pin its version, verify checksums, and ensure JDK compatibility. Run this **instead of** the Application Insights Java agent from Section 9 when studying the OTLP pipeline—never attach both agents together.

### 13.4. OTLP Protocols and Endpoints

| Transport | Common Port | Notes |
|---|---|---|
| OTLP/gRPC | 4317 | Requires a gRPC-compatible receiver |
| OTLP/HTTP protobuf | 4318 | HTTP/protobuf; base endpoint is normally suffixed by signal path by the SDK |
| Application Insights ingestion | Per Azure Monitor connection string | **Not a generic OTLP endpoint** |

Ensure `OTEL_EXPORTER_OTLP_PROTOCOL` and `OTEL_EXPORTER_OTLP_ENDPOINT` match. A Collector listening on `4318` will not accept gRPC on that same port.

### 13.5. Production Collector Requirements

A production Collector typically needs:
- Authentication and TLS between apps and the Collector.
- NetworkPolicies, Private Endpoints, or private network paths.
- Memory limiters, bounded queues, and batch processors.
- Exporter retries and backpressure handling.
- Self-health endpoints, internal metrics, and logs.
- High-availability / replica strategy.
- Data loss/restart semantics and persistent queues where supported.
- Attribute filtering/redaction before export.
- Clear ownership, version pinning, and security patching.

Enabling `batch` in a Collector **does not make telemetry durable**. If the process crashes before flushing a batch, in-memory spans are lost. Design reliability around real exporter, queue, and storage guarantees.



## 14. Sampling: Choosing Data Intentionally

### 14.1. Why Not Keep Every Span?

A system serving 10,000 requests/second averaging 15 spans per request generates:

~~~text
10,000 requests/s × 15 spans/request
    = 150,000 spans/s

In 1 day:
    150,000 × 86,400
    = 12,960,000,000 spans/day
~~~

This is an illustrative count before factoring in logs, metrics, payload sizes, compression, and ingestion retries. Keeping 100% drives substantial CPU/memory, egress, ingestion, and retention costs.

### 14.2. Head Sampling

**Head sampling** makes the keep/drop decision when the trace/request begins—for instance, keeping ~10% of traces. It is simple and low-overhead, but **cannot tell upfront whether the request will turn out slow or fail at the end**.

Example:

~~~text
Root request enters API
Sampler decides: retain (sampled=1)
    → downstream spans inherit decision where supported

Root request enters API
Sampler decides: drop (sampled=0)
    → span tree may not be stored in backend
~~~

**Parent-based sampling** keeps decisions consistent across services for a single trace. If one service drops spans independently via random sampling, traces fragment. Conversely, if a downstream service ignores the `sampled` flag or backend policy, partial/missing traces still occur.

### 14.3. Rate-Limited Sampling in Azure Monitor Java

In the Azure Monitor Application Insights Java agent (per documentation at authoring time), rate-limited sampling became default starting in agent 3.4.0, targeting roughly **5 requests per second** plus correlated telemetry.

Illustrative config:

~~~json
{
  "sampling": {
    "requestsPerSecond": 5
  }
}
~~~

This limit is **per agent process**, not cluster-wide, and does not guarantee exactly 5 traces/sec every second. With 20 busy replicas, total sampled requests exceed 5 across the fleet. Account for replicas, regions, and autoscaling.

When hunting for a specific test request:
- Never conclude a request bypassed the service just because no trace appears.
- Cross-check logs/metrics and inspect sampling settings.
- Use higher sampling **in staging** to simplify smoke tests.
- Never turn off sampling fleet-wide in production without forecasting ingestion cost.

### 14.4. Fixed-Percentage Sampling

To retain a steady proportion, configure percentage sampling per your agent's capabilities. Statistically, 10% of 10,000 requests/s yields roughly 1,000 requests/s **before accounting for semantic or per-replica effects**.

Pros: easy proportional estimation. Cons: trace volume still scales linearly with traffic surges, and rare errors may be dropped.

**Never compute production error rates simply as failed spans / successful spans in sampled data** if sampling varies by status or route; use metric-based SLIs or weighted estimators.

### 14.5. Tail Sampling

**Tail sampling** waits to collect most or all spans of a trace before deciding whether to retain it—prioritizing errors or high-latency traces.

~~~mermaid
flowchart LR
    S["Spans from many services"] --> C["Collector tail sampler"]
    C --> Q{"Slow / Error / Selected?"}
    Q -->|Yes| B["Keep trace"]
    Q -->|No| D["Drop trace"]
~~~

Risks:
- The Collector must **buffer spans** in memory, raising RAM usage.
- Requires trace-ID-aware load balancing so all spans of one trace reach the same decision node.
- Very long or async traces may arrive after the decision window closes.
- A Collector crash drops buffered traces.
- Not every backend/exporter supports arbitrary tail sampling cleanly.
- With Application Insights, respect the **Azure Monitor sampler** and trace completeness requirements; do not blindly stick tail sampling in front of an exporter expecting identical behavior.

Tail sampling is a tested architectural decision, not a casual checkbox in the Azure Monitor Java agent.

### 14.6. Sampling Logs and Metrics

- **Traces:** commonly sampled to control volume.
- **Metrics:** aggregated rather than per-request sampled; watch cardinality limits.
- **Logs:** can be filtered/sampled, though critical security and audit logs need dedicated retention/collection rules.
- **Request-correlated logs:** some integrations inherit the trace sampling decision to preserve correlation.
- **Startup/background logs:** may follow different sampling behavior than request-bound logs.

Before altering sampling policies, balance **cost + investigative power + compliance**. Never discard all exception evidence to cut ingestion without an alternative signal.

### 14.7. Initial Selection Matrix

| Goal | Strategy to Consider | Conditions |
|---|---|---|
| Lab with 20 requests | High sampling in staging | Zero PII / prod data |
| High-RPS production | Rate-limited or percentage sampling | Backed by SLO & cost budget |
| Rare failures | Route/error overrides where supported | Preserve trace correlation |
| Long async queue traces | Propagation + collector/retention evaluation | Watch late-arriving async spans |
| Compliance audits | Dedicated logs/audit pipeline | Never rely solely on sampled traces |

## 15. KQL: Querying Distributed Traces in Application Insights

### 15.1. Do Not Mix Up Table Names

In **workspace-based Application Insights**:
- **`AppRequests`:** inbound/server request telemetry.
- **`AppDependencies`:** outbound dependency calls and many internal operations.
- **`AppTraces`:** log/tracing messages.
- **`AppExceptions`:** exception records.

Legacy experiences or classic resources may expose **`requests`, `dependencies`, `traces`, `exceptions`** with different column names. Verify your Log Analytics context before copying KQL.

### 15.2. Request Latency and Errors by Service

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize
    Requests = sum(ItemCount),
    Failures = sumif(ItemCount, Success == false),
    P95Ms = percentile(DurationMs, 95)
  by bin(TimeGenerated, 5m), AppRoleName
| order by TimeGenerated asc
~~~

**`ItemCount`** represents sampling weight, so volume estimates typically use `sum(ItemCount)` instead of `count()`. Note that `percentile()` above does not automatically weight by `ItemCount`; treat it as an initial observation over retained samples rather than an exact population percentile.

### 15.3. Finding Top Slow Dependencies

~~~kusto
AppDependencies
| where TimeGenerated > ago(1h)
| summarize
    Calls = sum(ItemCount),
    Failed = sumif(ItemCount, Success == false),
    P95Ms = percentile(DurationMs, 95)
  by AppRoleName, Type, Target, Name
| top 20 by P95Ms desc
~~~

Results highlight slow dependencies in retained data. Never declare Azure Storage permanently slow from 2 samples where 1 took 2 seconds; check volume, distribution, and sampling.

### 15.4. Finding One Trace by `OperationId`

Assuming you have an authorized trace ID from a response or log:

~~~kusto
let targetTraceId = "4bf92f3577b34da6a3ce929d0e0e4736";
union
    (
      AppRequests
      | where OperationId == targetTraceId
      | project TimeGenerated, Signal="request",
          AppRoleName, Name, Id, ParentId,
          OperationId, DurationMs, Success, ResultCode
    ),
    (
      AppDependencies
      | where OperationId == targetTraceId
      | project TimeGenerated, Signal="dependency",
          AppRoleName, Name, Id, ParentId,
          OperationId, DurationMs, Success, ResultCode
    )
| order by TimeGenerated asc
~~~

If services span multiple Application Insights resources or workspaces, querying one workspace misses downstream hops. Use cross-resource unions where supported and permitted by RBAC.

### 15.5. Inspecting Exceptions for the Same Trace

~~~kusto
let targetTraceId = "4bf92f3577b34da6a3ce929d0e0e4736";
AppExceptions
| where TimeGenerated > ago(24h)
| where OperationId == targetTraceId
| project TimeGenerated, AppRoleName,
    Type, Method, Message, ProblemId, OperationId
| order by TimeGenerated asc
~~~

In production, exception messages can contain sensitive inputs. Never paste raw KQL outputs into public issue trackers; redact and restrict access.

### 15.6. Linking Requests and Dependencies

~~~kusto
let errors =
    AppRequests
    | where TimeGenerated > ago(1h)
    | where Success == false
    | project OperationId, RequestName=Name,
        RequestRole=AppRoleName, RequestMs=DurationMs;
errors
| join kind=leftouter (
    AppDependencies
    | where TimeGenerated > ago(1h)
    | project OperationId, DependencyName=Name,
        DependencyTarget=Target, DependencyMs=DurationMs,
        DependencySuccess=Success
) on OperationId
| order by RequestMs desc, DependencyMs desc
~~~

Because one request invokes multiple dependencies, **joining multiplies rows**. Use this for investigation, never summing dependency durations to equal request duration—child spans can run in parallel or nested.

### 15.7. Verifying Log Correlation

~~~kusto
AppTraces
| where TimeGenerated > ago(30m)
| where OperationId == "4bf92f3577b34da6a3ce929d0e0e4736"
| project TimeGenerated, AppRoleName,
    SeverityLevel, Message, OperationId, ParentId
| order by TimeGenerated asc
~~~

If `AppTraces` lacks `OperationId`, the log may have been emitted outside a span context or log-correlation injection isn't enabled. Never guess by attaching background logs to whichever request happened near the same timestamp.

### 15.8. Do Not Rely Solely on KQL for Every SLO

KQL over sampled traces excels at **investigation**. Availability and latency SLOs need reliable measurement sources:
- Azure Monitor metrics or app-level counters/histograms.
- Application Insights request data with documented sampling weights and limits.
- Synthetic availability tests if configured.
- Load balancer / API gateway metrics as the source of truth for total traffic.
- Service Bus queue age/lag for background processing.

If 100% of error traces are kept while only 5% of healthy traces are retained, raw failed/total ratios in the table no longer reflect true error rates without adjustment.

## 16. Log Correlation and Real-World Failure Tracing

### 16.1. Trace IDs in Structured Logs

A useful log entry:

~~~json
{
  "timestampUtc": "2026-11-20T10:05:10Z",
  "level": "WARN",
  "service": "orders-api",
  "event": "pricing_timeout",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "error_type": "TimeoutException",
  "dependency": "pricing-api",
  "duration_ms": 2000
}
~~~

This JSON is illustrative, not every Java agent's default format. Populate fields from the **active OTel context** or log correlation bridge—never generate random trace IDs per log line.

### 16.2. Trace IDs Do Not Replace Business Request IDs

- **Trace ID:** correlates the execution path.
- **Span ID:** identifies operations inside a trace.
- **Business order ID:** domain entity stored in protected datastores and logs.
- **Message ID:** identifies queue messages/retries for idempotency.
- **Idempotency key:** prevents duplicate side effects.
- **Request ID:** gateway/service ID for a specific HTTP request.

One order can span **multiple traces** (create, retry, status poll, refund). Conversely, one trace can touch multiple orders in a batch. Never use trace ID as a database transaction unique key.

### 16.3. Spotting Retry-Induced Failures

Suppose a user request records:
- Total SERVER span: 6 seconds.
- CLIENT Pricing span: 2 seconds (failed).
- CLIENT Pricing retry span: 2 seconds.
- Final CLIENT Pricing span: 1 second (succeeded).
- SQL insert: 50 ms.

Scaling up Azure SQL DTUs will not improve p99 here: the culprit is HTTP timeouts/retries against Pricing. Note that **individual retry attempts may not appear** if instrumentation emits only a single logical dependency span; check SDK/agent settings when attempt-level detail is needed.

### 16.4. Clock Skew in Spans

Different hosts can drift by several seconds. Spans still correlate by ID, yet waterfalls may make a child span look like it started before its parent.

Check:
- NTP/clock synchronization on VMs and edge nodes.
- UTC standardization and timezones.
- Agent/SDK clock sources.
- Message enqueue time vs. processing time.
- Ingestion lag vs. event timestamps.

Never rely strictly on **downstream timestamps** to prove exact chronological order when clocks are unsynchronized.

### 16.5. Event Ordering and Asynchronous Work

An HTTP request completes at 10:00, and the invoice worker runs at 10:05. If the worker reuses the same trace ID, the trace timeline stretches across 5 minutes. Backends render this with gaps or split views; producer–consumer links vs. parent–child links depend on instrumentation.

That 5-minute trace does not mean the HTTP client waited 5 minutes for the worker. Measure HTTP SLOs and background queue processing SLOs separately.

## 17. Azure Hosting: App Service, AKS, Container Apps, and Functions

### 17.1. Azure App Service

You can enable Application Insights auto-instrumentation via App Service settings or bundle the JVM agent in your deployment. **Never enable both at once** on the same workload.

Verify:
- App Service runtime and JDK version.
- Connection string and role name.
- VNet integration / egress to ingestion endpoints.
- Startup arguments / `JAVA_TOOL_OPTIONS` where used.
- Agent diagnostics and application logs.
- Whether Portal auto-instrumentation is already turned on.
- Whether staging and production slots point to the right App Insights resources.

During slot swaps, avoid accidentally shipping staging telemetry into production resources or vice versa; separate cloud roles and environments cleanly.

### 17.2. AKS

Typical Java agent deployment steps:
- Pin the agent JAR inside the container image or mount it from a trusted source.
- Pass JVM arguments via container entrypoint or `JAVA_TOOL_OPTIONS`.
- Inject the Application Insights connection string through approved secrets/config.
- Set a stable role/service name (never Pod UID).
- Budget CPU and memory for the agent.
- Verify NetworkPolicies, outbound TLS, and DNS.
- Roll out canary pods with HPA, rate-limited sampling, and cost budgets.
- Keep OTLP Collector receivers private when running internal pipelines.

If deploying an OTel Collector in AKS, choose **sidecar, DaemonSet, or gateway** based on topology, cardinality, and ownership. Never assume a DaemonSet automatically captures spans from every Pod unless apps export OTLP or agents are configured to target it.

### 17.3. Azure Container Apps

Container Apps brings revision-based rollouts, managed identities, egress controls, and scale-to-zero behavior. Java apps can attach the agent or send OTLP to a Collector where supported. Verify:
- Revision and `service.version`.
- Scale-to-zero and cold-start telemetry.
- Container memory headroom.
- Private networking / ingestion endpoint reachability.
- Context propagation across app and worker revisions.
- Whether logs are double-collected via platform loggers and the agent.

### 17.4. Azure Functions

Functions trigger and context propagation depend on language, hosting model, and integration support. HTTP triggers typically emit server spans via auto-instrumentation; Service Bus / Event Hubs triggers require verifying producer/consumer context handoff. Never drop in a library and assume full end-to-end traces appear automatically.

Distinguish:
- Function invocation ID.
- OTel trace ID / span ID.
- Message ID / sequence number.
- Trigger retries and dead-letter/poison-message behavior.

### 17.5. Networking and Microsoft Entra ID

The telemetry export path to Azure Monitor ingestion differs from the app's data path to Key Vault, Storage, or SQL. To ensure telemetry reaches Application Insights:
- DNS/TLS resolves ingestion endpoints for the right cloud/region.
- Egress firewalls and proxies allow required traffic.
- Connection string points to the right resource.
- A managed identity used for **app data access** does not automatically alter telemetry exporter auth unless configured.
- Azure RBAC to read Log Analytics differs from permission to emit telemetry.

Never open wildcard outbound access or disable TLS certificate validation to work around exporter timeouts. Check Azure Monitor / Application Insights networking docs and verify in your actual environment.

## 18. Security, Privacy, and Multi-Tenant Observability

### 18.1. Tracing Threat Model

Tracing data can accidentally capture:
- Authorization bearer tokens, JWTs, and SAS query strings.
- Request/response bodies containing PII.
- SQL statements with literal user values.
- Customer names, emails, phone numbers, and addresses.
- Payment or medical records.
- Client-injected baggage.
- Internal service endpoints and topology.
- Stack traces carrying user input or secrets.
- Resource labels embedding customer IDs.

Traces are not an unrestricted dump for all payloads. Apply **data minimization** per laws and organizational policy.

### 18.2. Never Put Secrets into Attributes or Baggage

Bad:

~~~text
http.request.header.authorization = "Bearer ..."
user.email = "customer@example.com"
db.statement = "SELECT ... WHERE password='secret'"
baggage = "tenantPrivateKey=..."
~~~

Good:

~~~text
http.route = "/orders/{orderId}"
http.request.method = "POST"
http.response.status_code = 503
dependency.type = "database"
error.type = "timeout"
orders.channel = "mobile"
~~~

If tenant attribution is required, use an identifier vetted under data classification rules, avoiding unbounded labels and cross-tenant leaks. Never put tenant secrets into `baggage`.

### 18.3. `traceparent` Is Untrusted Input

A malicious caller can send forged `traceparent`, `tracestate`, or `baggage` headers. Proxies and agents should:
- Validate header format and size.
- Restrict baggage keys and sizes.
- Never treat the `sampled` bit as a security control.
- Start a fresh trace context when inbound headers are invalid or cross untrusted boundaries.
- Never trust user roles or tenant claims inside baggage.
- Never use trace IDs as authorization tokens.

### 18.4. Authorization to View Telemetry

Anyone reading Application Insights or Log Analytics can learn:
- Endpoint names, exception patterns, and internal topology.
- Request metadata and any values leaked by collectors.
- Release versions and resource identifiers.

Enforce least-privilege Azure RBAC, query auditing where supported, retention limits, workspace isolation, and appropriate data access modes. An ingestion connection string **does not grant read access to traces**, yet still should not be shared indiscriminately.

### 18.5. Multi-Layer Redaction

1. In the app, avoid attaching sensitive attributes in the first place.
2. In instrumentation libraries/agents, restrict header, body, and SQL parameter capture.
3. In the Collector, redact or filter where pipelines support it.
4. At the ingestion backend, enforce data governance and retention.
5. In KQL exports and incident sharing, strip PII before distributing.

Regex redaction in a Collector **cannot guarantee every secret is scrubbed** if telemetry also ships elsewhere. Source-level data minimization remains primary.

### 18.6. Protecting Test Environments

Labs can use `orderId` `"demo-123"`, fake emails, and dummy tokens. Never test tracing using live API keys, customer records, or production SQL snapshots. If reproducing production bugs, use anonymized data or tightly controlled environments with approved retention.



## 19. Performance, Cost, and Telemetry Governance

### 19.1. Instrumentation Has Real Cost

OpenTelemetry is valuable, not free. Account for:

~~~text
Total observability cost =
    Application instrumentation CPU + memory
  + Telemetry serialization/network egress
  + Agent / Collector compute and storage queues
  + Azure Monitor ingestion and data retention
  + Log Analytics querying/workspaces
  + Alerts, Workbooks and incident analysis
  + Operations, upgrades and security governance
~~~

Actual prices vary by region, pricing plan, retention, data tiers, and Azure Monitor terms. Never treat textbook examples as current billing quotes.

### 19.2. Estimating Volume

Suppose an application handles:
- 2 million requests per day.
- Average of 8 spans per request.
- Assumed average serialized span size of 500 bytes.

~~~text
Raw spans per day:
  2,000,000 × 8 = 16,000,000 spans

Approx telemetry payload:
  16,000,000 × 500 bytes
  = 8,000,000,000 bytes
  ≈ 8 GB/day (decimal units)

30 days at same level:
  ≈ 240 GB raw estimated
~~~

This is strictly a **rough estimate**; real payloads include attributes, events, stack traces, logs, wire compression, sampling, ingestion formats, and overhead. Defaulting to ~5 requests/s sampling cuts volume dramatically compared to 100% tracing, though actual bytes still vary from this simple formula.

### 19.3. Controlling Cardinality

Bad:
- Span name = `"GET /orders/12345"`.
- Metric label = per-user ID.
- Resource `service.name` = Pod UUID.
- Attribute = raw SQL query with literal values.
- Log field = per-`requestId` used in `summarize` groupings.

Better:
- Span name uses route templates.
- `service.name` stays constant per logical service.
- `service.version` tracks controlled release numbers.
- Exception types and `statusClass` stay low-cardinality.
- Trace IDs live in trace/log records, never as time-series metric labels.

### 19.4. Optimizing Span Count

Before adding custom spans everywhere:
1. Rely on built-in auto-instrumentation first.
2. Identify business steps that genuinely aid troubleshooting.
3. Add spans only for operations with meaningful latency or failure risk.
4. Use span events for lightweight milestones.
5. Trim or omit unhelpful attributes.
6. Benchmark overhead under load tests.
7. Compare app p95/p99 with and without instrumentation.
8. Preserve debugging and audit coverage per policy.

Never slash sampling so low that incidents become uninvestigable; combine sampled traces with unsampled metrics and structured logs.

### 19.5. Daily Caps and Retention

Azure Monitor / Application Insights supports capacity, daily cap, and retention controls depending on plan and config. While useful for cost control, understand their limits:

- Once a daily cap hits, telemetry stops ingesting as expected.
- Log Analytics retention governs how far back incident investigations can look.
- App metrics vs. logs/traces follow different retention and ingestion pipelines.
- Privacy or legal holds may mandate specific retention windows.
- Alert on volume surges early rather than waiting for a daily cap to drop production data.
- Duplicate instrumentation can unexpectedly double costs.

**A daily cap is not a sampling strategy and does not preserve trace completeness.**

### 19.6. Budgets, Tags, and Ownership

Every Application Insights resource, Collector, and Log Analytics workspace needs:
- Owning team.
- Environment and region.
- Governance cost center / tags.
- Data retention and classification.
- Versioned sampling policy.
- Agent/Collector version and upgrade cadence.
- Incident responder / on-call rotation.
- Query and dashboard runbooks.
- Budget and anomaly alert thresholds.
- RPO/RTO expectations for the observability pipeline where needed.

Observability needs active ownership—not merely checking an "Enable Application Insights" box in the portal.

## 20. A Repeatable Tracing Test Plan

### 20.1. Three Testing Layers

| Layer | Goal | Does Not Replace |
|---|---|---|
| Unit test | Manual span creation, attributes, error status, zero PII | Network propagation |
| Integration test | End-to-end HTTP/messaging trace context | Full production load |
| Load / fault injection | Sampling, exporter outages, p95 overhead, scalability | Business semantic correctness |

Use staging or lab subscriptions with synthetic data. Never send test faults to production payment systems or intentionally flood Application Insights to test quotas.

### 20.2. HTTP Propagation Test

An integration test can verify:
- Orders HTTP endpoint receives a request carrying a valid `traceparent`.
- Orders calls Pricing using an instrumented `HttpClient`.
- Pricing extracts `traceparent` and emits a SERVER span.
- Azure Monitor / Collector receives at least one trace sharing the trace ID.
- Parent–child relationships look consistent.
- Zero user emails or `Authorization` headers appear in attributes.

Expected shape:

~~~text
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736

orders-api  SERVER  POST /orders/{orderId}
   orders-api CLIENT GET /price
      pricing-api SERVER GET /price
         pricing-api INTERNAL calculate-price
~~~

Never assert the span count must equal exactly four; agents may add DNS, network, or SDK spans, or sampling may omit traces.

### 20.3. Async Message Test

1. HTTP handler creates a message with a stable message ID.
2. Producer injects OTel context into message metadata.
3. Worker receives and extracts context, emitting a CONSUMER span or link.
4. Worker calls Blob Storage and records the dependency.
5. Worker simulates one retry in the lab.
6. Verify only one invoice is created (separate idempotency test).
7. Confirm trace logs carry valid message IDs and correlation.
8. Inspect queue delay, delivery count, and child spans.
9. Confirm zero sensitive baggage was stored.
10. If the Service Bus SDK already auto-instruments, confirm no duplicate manual consumer span was added.

### 20.4. Sampling Tests

- Send 10–20 lab requests under configured sampling.
- Verify sampled vs. unsampled behavior.
- Verify parent `sampled` flags propagate across HTTP boundaries.
- For rate-limited sampling, exceed the threshold and confirm retained rate drops.
- Confirm uncorrelated logs follow expected agent retention rules.
- Inspect retained traces for intact span chains within instrumentation limits.
- Compare metric volume against trace volume.
- Run regression tests after agent config changes or upgrades.

### 20.5. Exporter / Collector Failure Tests

~~~text
Condition A: Collector unavailable
Condition B: DNS failure to Azure Monitor ingestion
Condition C: Proxy/TLS failure
Condition D: Exporter receives throttling/5xx
Condition E: Collector memory limit reached
Condition F: App exits before batch flush
~~~

Goals:
- **Business requests never block indefinitely** when the telemetry backend goes down.
- Agent/Collector enforces bounded buffering and retries.
- Logs/metrics expose telemetry drops and export errors.
- Diagnostic error logs never print connection strings or secrets.
- When the backend recovers, behavior matches actual buffering/loss guarantees.
- Application SLOs remain protected.

Never describe tracing as a **transactional audit log** or sole proof of financial transactions; observability telemetry can be sampled or dropped.

### 20.6. Security Tests

- Send a dummy `Authorization` header and verify it **never appears** in spans.
- Send query strings with dummy sensitive markers and verify redaction.
- Send oversized baggage or disallowed keys.
- Verify tenant A cannot query tenant B's telemetry where isolation is required.
- Audit IAM on Application Insights and Log Analytics.
- Verify raw stack traces and SQL text omit customer data.
- Verify Service Bus application properties aren't dumped raw into logs.
- Verify exported dashboards are redacted before sharing.

### 20.7. Performance Testing

Compare with tracing disabled vs. enabled:
- p50/p95/p99 request latency.
- CPU, memory, and GC pressure.
- Network bytes transmitted.
- Span volume and exporter queue depth.
- Collector CPU and memory.
- Ingestion latency.
- Effective sampling rate.
- Observability cost per million legitimate requests.
- Error rates and retry amplification.

Never cut costs by shutting off all traces before diagnosing an issue; tune spans, attributes, and sampling using measured evidence.

## 21. Troubleshooting Matrix for Common Issues

| Symptom | Possible Cause | First Check |
|---|---|---|
| App runs, zero spans appear | Agent not attached or exporter disabled | JVM args, agent self-diagnostics |
| Spring server span missing | Library/version unsupported by agent | Agent compatibility matrix |
| App Map shows only one node | Shared or missing Cloud Role Name | Agent `role.name` per service |
| Orders has trace, Pricing does not | Header stripped or sampling mismatch | W3C `traceparent` on outbound/inbound |
| Worker starts a new trace ID | Message context not injected/extracted | Application properties and instrumentation |
| Spans lack parents | Async thread-local lost | Executor/Reactor context propagation |
| Duplicate requests/dependencies | Two agents/exporters instrumenting | JVM args, platform auto-instrumentation |
| Random missing traces | Sampling rate, daily cap, export errors | Agent config and ingestion metrics |
| Huge trace duration | Async queue wait or clock skew | Queue timestamps and parent/links |
| "SQL" dependency missing | JDBC driver not auto-instrumented | Driver, agent support, manual span |
| 401/403 viewing Logs | Viewer lacks Azure RBAC | Workspace/resource roles |
| Telemetry lands in wrong resource | Wrong connection string | Environment/slot/revision settings |
| Java agent fails to start | Bad path, JDK, or agent release | Startup logs and manifest/provenance |
| OTLP Collector receives nothing | Wrong port, protocol, or bind address | 4317 gRPC vs. 4318 HTTP |
| Collector debug shows spans, Azure does not | Unsupported exporter/backend route | Exporter config and compatibility |
| DNS/TLS errors to ingestion | Egress, firewall, proxy, or private route | Runtime DNS/TLS and service endpoints |
| KQL query returns empty | Wrong workspace, table, timezone, or sampling | `TimeGenerated`, time range, RBAC |
| `OperationId` differs across services | `traceparent`/`tracestate` stripped or rewritten | Inbound/outbound headers |
| Unexpected data in baggage | Client injected arbitrary headers | Allowlists and trust boundaries |
| Tokens or PII in logs | Body/header capture or custom attributes | Redaction and security incident response |
| Ingestion costs spike suddenly | Lowered sampling drop, duplicate spans, high cardinality | Usage/cost reports, deploy diffs |
| Exporter queue full | Slow backend or undersized agent/Collector | Queue metrics, retries, drops |
| Traces vanish after rollout | Agent/BOM/instrumentation incompatibility | Version diffs and canary rollback |

## 22. Runbooks for Distributed Tracing Incidents

### 22.1. Runbook A: Request Times Out, No Trace Found

1. Record **UTC timestamp, HTTP route, service, release version**, and correlation ID if available.
2. Check metrics or logs to verify the request actually executed.
3. Confirm the right Application Insights resource, workspace, and region.
4. Check whether the Java agent attached and whether self-diagnostics logged errors.
5. Check sampling rate/overrides—the request may simply have been dropped by sampling.
6. Verify connection string and outbound Azure Monitor ingestion egress.
7. Check KQL time range, `TimeGenerated`, and ingestion lag.
8. Search by `OperationId` if logged; never search with Order ID as trace ID.
9. In staging, adjust sampling under approval and trigger a fresh test request.
10. Document findings and update the runbook; never disable production sampling indefinitely just to hunt one request.

### 22.2. Runbook B: Trace Breaks Between Orders and Pricing

1. Pick a sampled trace containing the Orders CLIENT dependency span.
2. Verify Pricing shows matching SERVER request logs/counters.
3. Confirm the HTTP client library is supported by the Java agent/instrumentation.
4. Verify outbound `traceparent`/`tracestate` headers **contain no secrets**.
5. Check whether an API gateway or proxy strips or rewrites headers.
6. Check Pricing context extraction and active span creation.
7. Verify Cloud Role Name, resource target, and sampling alignment.
8. If async processing sits in between, verify executor/reactive propagation.
9. Run an Orders → Pricing integration test in staging.
10. Verify parent IDs and correlation after fixing; never copy trace IDs manually via plain string fields.

### 22.3. Runbook C: Telemetry Doubles After Deployment

1. Compare telemetry volume before and after deployment.
2. Check App Service Portal auto-instrumentation status.
3. Check JVM startup flags and `JAVA_TOOL_OPTIONS` for `-javaagent`.
4. Check for both the Application Insights Java agent and upstream OTel agent together.
5. Check Spring/Micrometer exporters and custom SDK providers.
6. Check whether a Collector forwards the same span to two exporters targeting the same backend.
7. Disable the redundant pipeline in staging and verify counts and span hierarchy.
8. Roll out as a canary in production, monitoring ingestion cost and error rates.
9. Retain a single instrumentation owner.
10. Document the architecture and add CI checks blocking duplicate agents.

### 22.4. Runbook D: Exporter Suddenly Fails

1. Inspect Java agent / Collector logs and self-diagnostics.
2. Classify the failure: DNS, TCP connect, TLS, 401/403, 429, or 5xx.
3. Verify the Application Insights connection string or OTLP protocol config.
4. Measure queue length, dropped spans, retries, and CPU/memory.
5. Check VNet, NSGs, proxies, Azure Firewall, and ingestion hostnames.
6. Never open wildcard outbound rules or disable TLS certificate checks arbitrarily.
7. If the Collector hits memory pressure, scale capacity or trim telemetry per policy.
8. Verify business services continue meeting SLOs.
9. Recover/roll out carefully and document data gaps.
10. Report data loss transparently; never claim dropped spans will automatically replay.

### 22.5. Runbook E: Telemetry Contains Sensitive Data

1. Stop ongoing exposure; disable the offending attribute or header capture immediately.
2. Rotate/revoke credentials if raw tokens or SAS strings leaked.
3. Pinpoint the source: app code, agent, Collector, HTTP logs, or query exports.
4. Invoke data classification / incident response policies and record scope/time window.
5. Audit who accessed the workspace and exports.
6. Handle deletion, retention, and backup cleanup per governance/legal rules.
7. Fix instrumentation and add redaction tests.
8. Add CI checks blocking sensitive attribute keys.
9. Verify the fix in staging using synthetic marker data.
10. Write a postmortem; never paste raw leaked tokens into tickets or logs during investigation.



## 23. Case Study: Tracing Orders Across App Service, AKS, and Service Bus

### 23.1. Problem Statement

An e-commerce platform runs on Azure:

- **API Gateway** receives frontend requests.
- **Orders API** runs Spring Boot on App Service.
- **Pricing API** runs on AKS.
- **Azure SQL Database** stores orders.
- **Azure Service Bus** queues invoice jobs.
- **Invoice Worker** runs on Azure Container Apps.
- **Blob Storage** stores PDF invoices.
- **Azure Monitor Application Insights** and Log Analytics provide observability.

Goals:
- HTTP API maintains p95 latency below 800 ms under normal load.
- Invoice worker generates invoices within 2 minutes with healthy queue backlog.
- Sufficient evidence to identify which dependency causes timeouts.
- Zero payment tokens, JWTs, or sensitive order/customer identifiers in telemetry.
- Ability to compare before/after deployments and roll back if p99 degrades.
- Defined sampling, retention, and cost governance independent of manual portal clicks.

### 23.2. Observability Architecture

~~~mermaid
flowchart TD
    GW["Gateway"] --> API["Orders API - App Service"]
    API --> PR["Pricing API - AKS"]
    API --> SQL["Azure SQL"]
    API --> SB["Service Bus"]
    SB --> WK["Invoice Worker - Container Apps"]
    WK --> BL["Blob Storage"]
    API -. "Java agent spans" .-> AI["Application Insights"]
    PR -. "Java agent spans" .-> AI
    WK -. "Java agent spans" .-> AI
    AI --> LA["Log Analytics / KQL / Alerts"]
    SB -. "Queue metrics" .-> MON["Azure Monitor Metrics"]
    SQL -. "DB metrics" .-> MON
    MON --> ALERT["On-call notifications"]
    LA --> ALERT
~~~

Services declare Cloud Role Names **`orders-api`**, **`pricing-api`**, and **`invoice-worker`**, each tagged with release version and environment. One compatible Java agent or instrumentation pipeline runs per JVM. Application Insights resources can be separated by environment, using cross-resource querying where appropriate and permitted.

### 23.3. A Normal Trace

Illustrative timings (not an SLA):

~~~text
TraceId 4bf92f3577b34da6a3ce929d0e0e4736

Orders API: POST /orders/{orderId}             420 ms
 ├─ INTERNAL orders.validate                    12 ms
 ├─ CLIENT Pricing GET /quote                    210 ms
 │   └─ SERVER Pricing GET /quote                190 ms
 │       └─ INTERNAL pricing.calculate           35 ms
 ├─ CLIENT Azure SQL INSERT                     70 ms
 └─ PRODUCER Service Bus send                   45 ms

Invoice Worker: CONSUMER invoice.process         310 ms
 └─ CLIENT Blob Storage upload                  240 ms
~~~

A queue consumer normally runs **after** Orders API returns its HTTP response; Invoice Worker's 310 ms does not sit inside the 420 ms HTTP request. Interpret parent/link relationships and timestamps according to messaging instrumentation semantics.

### 23.4. A Failing Trace

During peak hours:
- Orders API p99 climbs from 700 ms to 6 seconds.
- Pricing API returns transient 503s.
- HttpClient SDK retries twice, each timing out around 2 seconds.
- Orders gateway returns 504.
- SQL latency stays flat.

Workflow:
1. Azure Monitor Metrics fires p99 and 5xx alerts.
2. Application Insights Performance/Failures locates slow requests.
3. KQL joins `AppRequests`/`AppDependencies` on `OperationId`.
4. The trace waterfall shows long/repeated Pricing CLIENT spans while SQL takes 30 ms.
5. Check Pricing logs, AKS HPA, dependency health, and networking.
6. Check retry amplification, `Retry-After` handling, and circuit breakers.
7. Cap retries to fit the total business deadline and scale capacity if needed.
8. Canary the fix, comparing p95/p99, error rates, attempts, and cost.
9. Write a postmortem and update runbooks.

Looking at a lone `"SQL connection failed"` log near the same timestamp could waste time scaling SQL DTUs when Pricing is the true culprit. Tracing preserves **causal relationships via `OperationId`**, rather than guessing from adjacent timestamps.

### 23.5. Never Equate Traces with Order Persistence Proof

After an HTTP timeout, Orders API might have published the Service Bus message before missing the ACK. The user retries, and the system generates two invoices. Traces show two sends, yet the fix **is not deleting a span**.

You need:
- Stable order IDs and idempotency keys.
- Database unique constraints or conditional writes.
- Outbox or transactional coordination between DB writes and message dispatch.
- Stable message IDs and worker deduplication.
- Durable business audit logs separate from OTel traces.
- Reconciliation jobs when queue or Blob processing lags.

**Tracing detects and explains failures; it does not make workflows exactly-once.**

### 23.6. Separating SLOs

| SLO/SLI | Suggested Measurement Source | What Not to Do |
|---|---|---|
| HTTP latency p95 | Request metrics / gateway counters | Rely solely on sampled traces |
| HTTP availability | Gateway / service metrics | Count unweighted failed spans |
| Background invoice lag | Service Bus age / worker processing metrics | Include queue wait inside HTTP duration |
| Trace coverage | Sampled trace counts, propagation checks | Treat 100% trace coverage as a traffic SLO |
| Dependency diagnostics | `AppDependencies` + spans | Sum all child durations blindly |
| Privacy | Redaction tests / audits | Assume defaults hide every token |
| Observability cost | Azure Monitor usage/cost metrics | Assume span count ≈ request count |

### 23.7. Phased Rollout

1. Enable instrumentation on **`orders-api`** in dev.
2. Add role, version, and environment attributes.
3. Enable **`pricing-api`** in staging and verify W3C HTTP context propagation.
4. Enable **`invoice-worker`** and verify messaging context and links.
5. Measure export drops and runtime overhead.
6. Standardize KQL queries, Workbooks, alerts, and access permissions.
7. Set sampling rates and retention budgets.
8. Canary across a subset of production instances.
9. Review p95/p99, CPU, memory, and ingestion costs.
10. Expand fleet-wide with documented runbooks, owners, and rollback plans.

## 24. Production Checklist

### Data Model and Propagation

- [ ] Team understands traces/spans, trace IDs, parent IDs, span kinds, events, and links.
- [ ] Stable `service.name` / Cloud Role Name defined per service.
- [ ] `service.version` and deployment environment metadata attached.
- [ ] Outbound/inbound HTTP and gRPC propagate W3C `traceparent` properly.
- [ ] Reverse proxies and API gateways do not strip context unexpectedly.
- [ ] Service Bus / Event Hubs messages have a tested propagation strategy.
- [ ] Async executors and Reactor contexts tested.
- [ ] Batches and fan-in flows use span links where appropriate.
- [ ] Trace IDs are never substituted for business IDs or idempotency keys.
- [ ] Root, client, producer, and consumer spans show sensible hierarchy.

### Instrumentation and Exporters

- [ ] One primary instrumentation/export strategy chosen per JVM.
- [ ] Two Java agents never auto-instrument the same service simultaneously.
- [ ] Java agent, SDK, and OTel API versions pinned and verified.
- [ ] Agent JARs sourced from trusted registries with checksum verification.
- [ ] Auto-instrumentation for HTTP, JDBC, and SDKs verified per version.
- [ ] Manual spans added only for meaningful business steps.
- [ ] Every manual span ends inside a `finally` block.
- [ ] Exceptions and statuses recorded cleanly without altering business flow.
- [ ] App Service platform auto-instrumentation checked before attaching custom agents.
- [ ] Azure Monitor ingestion and OTLP Collector pipelines clearly distinguished.
- [ ] Collector receivers enforce TLS, auth, and private access outside localhost.
- [ ] Export drops, retries, and queue metrics monitored with runbooks.

### Sampling and Data Protection

- [ ] Sampling mode and rate defined and tested.
- [ ] Parent-based consistency and downstream behavior verified.
- [ ] Team understands missing traces may reflect sampling rather than unexecuted requests.
- [ ] Error rates are never estimated from raw unweighted sampled traces alone.
- [ ] Retention for logs, metrics, and traces aligns with policy.
- [ ] Zero `Authorization` headers, SAS tokens, secrets, or raw request bodies in spans.
- [ ] W3C baggage allowlisted and size-capped.
- [ ] `traceparent` and `baggage` never trusted for authentication.
- [ ] Raw user/order IDs excluded from span names and metric labels.
- [ ] Negative tests verify PII does not leak.
- [ ] Log Analytics / Application Insights access follows least privilege.
- [ ] Incident response policy exists for secrets accidentally logged in telemetry.

### Reliability, Cost, and Operations

- [ ] Clear SLIs/SLOs defined for both HTTP and background workflows.
- [ ] p95/p99 and error rates measured from reliable sources.
- [ ] Dashboards cover Application Map, Failures, Performance, and KQL.
- [ ] KQL queries trace `OperationId` across `AppRequests` and `AppDependencies`.
- [ ] Alerts fire on exporter failures and Collector saturation.
- [ ] Business apps keep running per design if the telemetry backend stalls.
- [ ] Agent/Collector CPU, memory, and network overhead benchmarked.
- [ ] Budgets, retention, sampling, and daily cap policies established.
- [ ] Zero duplicate telemetry observed post-rollout.
- [ ] Owners, on-call rotations, and runbooks cover missing traces, 429s, DNS/TLS, and privacy.
- [ ] Fault-injection tests and canary rollouts practiced.
- [ ] Rollback plan ready if an agent upgrade degrades latency or spikes cost.
- [ ] Before/after release version and metric evidence preserved.

## 25. Self-Check Questions

1. **What problem does distributed tracing solve?** Tracking causal execution of an operation across multiple services.
2. **How do metrics differ from traces?** Metrics measure aggregated trends over time; traces explain the execution path of an individual operation.
3. **Can logs completely replace traces?** No, not when span hierarchy, parent context, and precise timings are missing.
4. **How long is a trace ID?** Typically 128-bit per W3C specs, represented as 32 hex characters.
5. **How long is a span ID?** Typically 64-bit, represented as 16 hex characters.
6. **What does a span contain?** Name, IDs, kind, start/end times, attributes, events, status, and links.
7. **What does a SERVER span mean?** Handling an inbound request from a remote caller.
8. **What does a CLIENT span mean?** Calling a remote dependency.
9. **When are PRODUCER and CONSUMER used?** Sending and receiving asynchronous messages.
10. **What is an INTERNAL span used for?** Work occurring inside a single process.
11. **How does a span link differ from a parent?** It can reference multiple contexts without forcing a single strict parent–child relationship.
12. **What does W3C `traceparent` contain?** Version, trace ID, parent span ID, and trace flags.
13. **Does `sampled=1` prove a request was authenticated?** No.
14. **What is `tracestate` used for?** Carrying vendor-specific tracing metadata.
15. **Should `baggage` carry tokens or user emails?** No.
16. **What does injecting context mean?** Writing trace context into an outbound carrier.
17. **What does extracting context mean?** Reading remote context before starting a span on the receiver.
18. **What happens if a gateway strips `traceparent`?** Downstream services start a new root trace.
19. **How should `service.name` be chosen?** Stable per logical service, never per request or per Pod.
20. **Why is Cloud Role Name needed?** To distinguish services on Application Map.
21. **Does the OpenTelemetry API export data on its own?** No, not without an SDK/exporter/agent.
22. **How does auto-instrumentation differ from manual instrumentation?** Auto captures framework/library calls; manual adds domain business spans.
23. **Why avoid running two Java agents together?** They cause duplicate spans and corrupt context.
24. **Which JVM flag attaches a Java agent?** `-javaagent` placed before `-jar`.
25. **What is the Application Insights connection string used for?** Specifying the telemetry export destination.
26. **Does the connection string grant permission to read all Log Analytics data?** No.
27. **What is the default sampling in recent Azure Monitor Java agent releases?** Rate-limited sampling targeting roughly 5 requests/s per docs.
28. **Does a missing trace prove a request never ran?** No; sampling, export failures, or drops may explain it.
29. **When does head sampling make its decision?** When the trace/request begins.
30. **When does tail sampling make its decision?** After observing spans and final trace characteristics.
31. **What are the drawbacks of tail sampling?** Memory buffering, trace-aware routing complexity, late spans, and crash data loss.
32. **What benefit does parent-based sampling provide?** Keeps sampling decisions consistent across a trace.
33. **What data does `AppRequests` contain?** Server / inbound request telemetry.
34. **What does `AppDependencies` contain?** Remote dependencies and many mapped custom spans.
35. **Does `AppTraces` store all trace spans?** No, it typically stores log and tracing messages.
36. **What is `OperationId` used for?** Correlating telemetry records belonging to one distributed operation.
37. **How does `ItemCount` help with sampling?** Estimates the represented original volume in Application Insights where applicable.
38. **Can a KQL join on `OperationId` produce multiple rows per request?** Yes, because one request can invoke multiple dependencies.
39. **Why shouldn't you sum all child durations?** Child operations can run in parallel or be nested.
40. **Are trace ID and order ID the same?** No.
41. **Why is context lost across an async executor?** `ThreadLocal` does not cross threads without explicit propagation or instrumentation.
42. **What is needed to propagate across Service Bus?** Context injection/extraction in message metadata or SDK support.
43. **Can a retried message emit multiple consumer spans?** Yes.
44. **Does the Collector debug exporter send data to Application Insights?** No.
45. **Which port does OTLP HTTP normally use?** `4318`, paired with the matching protocol/endpoint.
46. **Which port does OTLP gRPC normally use?** `4317`.
47. **Is the App Insights ingestion URL an OTLP receiver?** No.
48. **Does Java agent auto-instrumentation support every library?** No; check support matrices and versions.
49. **What should never be recorded in span attributes?** Tokens, PII, raw SQL literals, and secrets.
50. **When spans go missing in production, what should you check?** Agent, config, sampling, network, exporter, role/workspace, and propagation.
51. **When a trace splits in two, what should you check?** `traceparent`, gateways, async/message context, and sampling.
52. **When telemetry doubles after a deployment, what should you check?** Overlapping agents, exporters, or instrumentation.
53. **Does tracing guarantee exactly-once processing on Service Bus?** No.
54. **What determines safe production tracing?** Sampling, propagation, privacy, least privilege, self-monitoring, fault tests, budgets, and runbooks.
55. **Can traces serve as the sole source for financial transaction audits?** No, due to sampling, exporter loss, and retention.
56. **Are HTTP SLOs and queue worker SLOs identical?** No; separate HTTP latency from queue processing time.
57. **Where should you measure OTel latency overhead?** Compare p95/p99, CPU, and memory before and after instrumentation.
58. **Why never use trace ID as a metric label?** Excessive cardinality and cost.
59. **If Application Map merges several services into one node, what should you check?** Cloud Role Name and resource attributes.
60. **When the exporter fails, what should the application do?** Preserve business SLOs with bounded buffering/retries and alert on telemetry drops.

## 26. References

Consult these official resources matching your **actual Azure Monitor Java agent, OpenTelemetry SDK, and service client versions** before deploying to production:

- [OpenTelemetry specification](https://opentelemetry.io/docs/specs/otel/) — data model, context, API/SDK, semantic conventions.
- [OpenTelemetry concepts: traces](https://opentelemetry.io/docs/concepts/signals/traces/) — trace/span relationships, events/status.
- [OpenTelemetry context propagation](https://opentelemetry.io/docs/concepts/context-propagation/) — inject/extract context.
- [OpenTelemetry Java documentation](https://opentelemetry.io/docs/languages/java/) — instrumentation, SDK, Java agent.
- [OpenTelemetry Java agent](https://opentelemetry.io/docs/zero-code/java/agent/) — zero-code instrumentation and configuration.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — `traceparent`/`tracestate` wire format.
- [W3C Baggage](https://www.w3.org/TR/baggage/) — baggage propagation, limits, and privacy.
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/) — receivers, processors, exporters, operations.
- [OTLP specification](https://opentelemetry.io/docs/specs/otlp/) — gRPC/HTTP telemetry protocol.
- [Azure Monitor Application Insights overview](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview) — APM and application observability on Azure.
- [Enable OpenTelemetry in Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable?tabs=java) — Java agent and connection string.
- [Using Application Insights with Spring Boot](https://learn.microsoft.com/en-us/azure/azure-monitor/app/java-spring-boot) — JVM agent and Spring Boot.
- [Azure Monitor OpenTelemetry configuration](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-configuration?tabs=java) — sampling, role, Java defaults.
- [Azure Monitor OpenTelemetry sampling](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-sampling) — samplers and trace completeness.
- [Azure Monitor Java agent configuration](https://learn.microsoft.com/en-us/azure/azure-monitor/app/java-standalone-config) — `role.name`, configuration file, sampling, and diagnostics.
- [Add custom OpenTelemetry spans in Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-add-modify?tabs=java) — OpenTelemetry API, `@WithSpan`, attributes, logs.
- [Application Insights dependencies](https://learn.microsoft.com/en-us/azure/azure-monitor/app/dependencies) — dependency tracking.
- [Application Insights Java on Azure App Service](https://learn.microsoft.com/en-us/azure/azure-monitor/app/azure-web-apps?tabs=java) — platform auto-instrumentation.
- [AppRequests table schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/apprequests) — `OperationId`, `DurationMs`, sampling fields.
- [AppDependencies table schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/appdependencies) — dependency query columns.
- [AppRequests example KQL queries](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/queries/apprequests) — latency, failures, request counts.
- [Azure Monitor Logs KQL](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/log-query-overview) — querying and permissions.
- [Azure Monitor costs and usage](https://learn.microsoft.com/en-us/azure/azure-monitor/cost-usage) — ingestion, retention, and costs.
- [Azure Well-Architected operational excellence](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/) — monitoring, observability, incident response.
- [Azure Service Bus messaging documentation](https://learn.microsoft.com/en-us/azure/service-bus-messaging/) — async delivery and messaging apps.
- [Azure Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/) — budgets and cost allocation.

**Conclusion:** OpenTelemetry provides the **standard model for traces, spans, context propagation, and exporters**; distributed tracing connects a business operation across App Service, AKS, Functions, Azure SDKs, SQL, and Service Bus. On Azure, the **Application Insights Java agent** is a practical path to instrument JVM workloads quickly and investigate via **Application Map, End-to-end transaction details, and `AppRequests`/`AppDependencies`/KQL**. A reliable architecture also addresses **W3C propagation, async messages, span parents/links, sampling and data completeness, authorization, redaction, exporter failures, overhead, retention, cost, and SLOs**. Tracing pinpoints incident causes, yet never replaces business idempotency, metrics, or audit logs; test end-to-end in staging, roll out via canary, and maintain runbooks before relying on it in production.
