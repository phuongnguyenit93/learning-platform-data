# Tracking Application Dependencies, Exceptions, and Transactions

A customer clicks **Place Order** on the website. After 4.8 seconds, the browser shows an error. The Spring Boot API is still running, CPU is only 25%, and the database shows no infrastructure alerts. Where did the failure occur: the HTTP request, Azure SQL query, Redis connection, call to the payment gateway, message sent to Azure Service Bus, or an exception caught and silently ignored? If each service only writes its own separate logs, finding the answer can take hours.

**Application observability** tracks an operation's journey across every participating component. On Azure, the core toolset typically includes **Azure Monitor**, **Application Insights**, a **Log Analytics workspace**, **OpenTelemetry**, metrics, logs, and **distributed traces**. This lesson focuses on three central entities:

- **Dependency:** an outbound call leaving the process—such as HTTP, JDBC/SQL, Redis, Azure Storage, Service Bus, DNS, or a third-party service.
- **Exception:** an error thrown or recorded during execution; not every exception triggers an HTTP 500 or a business failure.
- **Application transaction:** a user- or business-meaningful operation, such as confirming an order, whose duration, outcome, and sub-steps across services need tracking.

This lesson belongs to the **Monitoring and Observability** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores the Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID through virtual networks, compute, storage, data, security, monitoring, and cost. Here, we connect **Java/Spring Boot application requests → dependency calls → exceptions → business outcomes** to diagnose incidents and govern operations with evidence.

**Scope note:** Examples use Java 17/21, Spring Boot, and Azure Monitor Application Insights. SDK names, agent versions, KQL tables, auto-instrumentation support, permissions, and pricing vary by service and resource. All data, request IDs, endpoints, and timings in this lesson are **illustrative**, not real measured telemetry. Never enable debug logging of real customer data or run fault injection in production without approval.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **request, dependency, exception, trace, span, event, metric, and log**.
2. Distinguish an **application transaction**, a **database transaction**, and a **distributed trace**.
3. Design a trace tree from an HTTP request through SQL, downstream HTTP, and Service Bus.
4. Understand **trace ID, span ID, parent span ID**, W3C **`traceparent`/`tracestate`**, and context propagation.
5. Choose between the **Azure Monitor OpenTelemetry Distro/Java agent**, SDK instrumentation, and custom spans.
6. Record dependency duration, target, outcome, and exceptions without leaking sensitive information.
7. Use **Application Insights Application Map, transaction diagnostics, Failures**, and **Log Analytics/KQL** where supported.
8. Find slow requests, failed dependencies, and exceptions for a given operation ID.
9. Handle **retries, circuit breakers, 4xx/5xx, async execution, queues, and sampling**.
10. Design meaningful alerts/SLOs while controlling telemetry volume and cost.
11. Build a lab exercise and troubleshooting runbook for Spring Boot on Azure.

## 2. Which Components Does an Operation Traverse?

Example order-creation flow:

~~~mermaid
flowchart LR
    U[Browser] --> G[API Gateway]
    G --> A[orders-api: POST /orders]
    A --> P[(Azure PostgreSQL)]
    A --> C[Redis cache]
    A --> H[payment-api HTTPS]
    A --> B[Azure Service Bus]
    B --> W[invoice-worker]
    W --> S[(Azure SQL / Blob)]
~~~

One request can trigger multiple **dependencies**. `orders-api` itself might have healthy CPU while the `payment-api` call times out—or `payment-api` succeeds while the DB commit fails. A good trace reveals **which layer is slow**, **which span failed**, **where total time went**, and **how components interact**.

### Example Timeline

~~~text
POST /orders                      4.800 ms total
  |
  +-- SQL: read cart                35 ms
  +-- Redis: get price               8 ms
  +-- HTTPS: payment-api         4.500 ms [TIMEOUT]
  |     +-- Client retry         2.200 ms
  |     +-- Client retry         2.200 ms
  +-- SQL: rollback                12 ms
  +-- Response HTTP 504             ...
~~~

These numbers are hypothetical to illustrate the reasoning. **Spans can overlap in time**, so never blindly add all child durations expecting them to equal request duration. A trace tree and critical path explain timing far more accurately than summing lines.

## 3. Three Pillars and Telemetry Data Types

| Type | Content | Example | Used For |
|---|---|---|---|
| **Metrics** | Aggregated numerical measurements over time | Request rate, error rate, p95, JVM heap | Alerts, SLOs, trends |
| **Logs** | Event records with context | Authentication denied, job finished | Detailed investigation |
| **Traces** | Span tree for an operation | `POST /orders` → SQL → payment | Path and latency breakdown |
| **Exceptions** | Error data including type, message, stack where permitted | `SocketTimeoutException` | Debugging code/dependency errors |
| **Events** | Business or operational milestones | `order_placed`, `release_promoted` | Behavior tracking and correlation |

**Lots of logs do not equal good observability.** Without correlation IDs, each service writes isolated logs that are hard to stitch together. **Traces also cannot replace metrics**: sampling drops traces, whereas metrics are far better suited to computing system-wide SLOs.

### Telemetry Concepts in Application Insights

| Concept | Example in Application Insights |
|---|---|
| Request | Incoming HTTP request or instrumented entry operation |
| Dependency | Outbound HTTP/SQL/remote call span |
| Exception | Exception telemetry or span event |
| Trace/log | Diagnostic log messages with severity |
| Custom event/metric | Business actions, counters, and latency |

**Never assume `System.out` automatically becomes a correlated trace.** You must configure the logging/telemetry pipeline and context propagation.

## 4. Application Transactions vs. Database Transactions

The word **transaction** has three easily confused meanings:

1. **HTTP/application transaction:** a user-facing operation like `POST /checkout`, spanning multiple dependency calls.
2. **Database transaction:** an ACID commit/rollback unit, such as **`@Transactional`** in Spring.
3. **Distributed trace / transaction diagnostics:** the span chain tracking a request or workflow across services.

~~~text
Application operation: PlaceOrder
    |
    +-- Validate cart
    +-- DB transaction: insert order + outbox -> COMMIT
    +-- Queue publish
    +-- Payment provider call
    +-- Response / eventual completion
~~~

An **HTTP 200** does not guarantee payment settled and the queue finished processing. Conversely, a database **COMMIT** does not mean the client received a successful response. Distributed tracing provides visibility; **it does not provide distributed ACID transactions or exactly-once semantics**.

### Business Outcomes Must Be Explicit

Suppose a system tracks:

- `request_status = HTTP 202 Accepted`;
- `order_status = PENDING_PAYMENT`;
- `payment_status = FAILED`;
- `invoice_status = NOT_STARTED`.

Watching only HTTP status codes tricks operators into thinking the transaction succeeded. Emit **domain events/metrics** or controlled custom span attributes capturing business outcomes—without raw PII.

## 5. Traces, Spans, and Span Hierarchy

In OpenTelemetry, a **trace** captures the execution graph of an operation; each **span** carries a name, start/end times, attributes, status, and optionally events and links.

~~~text
TraceId: 1234567890abcdef1234567890abcdef
|
+-- Span A: HTTP SERVER POST /orders
|     SpanId: 1111111111111111
|
|    +-- Span B: PostgreSQL SELECT
|    |     ParentSpanId: 1111111111111111
|    |
|    +-- Span C: HTTP CLIENT payment-api
|    |     ParentSpanId: 1111111111111111
|    |
|    +-- Span D: Service Bus PUBLISH
|          ParentSpanId: 1111111111111111
|
+-- Span E: invoice-worker PROCESS
      Context/links propagated per messaging semantics
~~~

### Key Fields

| Field | Meaning |
|---|---|
| **`trace_id`** | Identifies the entire trace; typically 16 bytes / 32 hex chars in W3C |
| **`span_id`** | Identifies one span; typically 8 bytes / 16 hex chars |
| **`parent_span_id`** | Parent span when a parent–child relationship exists |
| **`span.kind`** | `SERVER`, `CLIENT`, `PRODUCER`, `CONSUMER`, `INTERNAL` |
| **`name`** | Operation name, e.g., `HTTP POST /orders` |
| **`start/end/duration`** | Execution timing |
| **`attributes`** | HTTP method, DB system, destination, peer service, environment |
| **`status`** | Span error/status signal per semantic conventions |
| **`events`** | Timestamped annotations inside the span, possibly exception events |
| **`links`** | Links to other spans, useful in queue and batch workflows |

**A trace ID is not an authentication credential.** It correlates logs and traces; it never grants permission to view an order. Never use a trace ID to enforce tenant authorization.

## 6. W3C Trace Context: Connecting Services

The W3C standard uses HTTP headers:

~~~http
traceparent: 00-1234567890abcdef1234567890abcdef-1111111111111111-01
tracestate: vendor=opaque-value
~~~

`traceparent` contains version, trace ID, parent/span ID, and trace flags. Service B receives the request, starts a child span from the extracted context, and injects updated context when calling Service C.

~~~text
Browser / API gateway
  traceparent=T
       |
       v
orders-api SERVER span
  extract context T
       |
       +-- JDBC child span
       |
       +-- HTTP payment-api request
                inject traceparent=T with current client span
                     |
                     v
                payment-api SERVER child span
~~~

### Things You Must Not Confuse

- **`traceparent`** is correlation metadata, not a JWT or OAuth token.
- **`tracestate`** holds vendor-specific trace metadata—never embed PII or secrets.
- **`baggage`** propagates across process boundaries: allowlist keys strictly and never include emails, session tokens, or account numbers.
- Mixing **W3C and legacy propagation** formats or stripping headers in a proxy breaks traces.

### Correlation Across Queues

When publishing to Azure Service Bus or Event Hubs, propagate context via message application properties/headers per SDK and instrumentation support. For **batches, retries, and fan-out**, direct parent–child links may fall short; OpenTelemetry supports **span links**. Never lump unrelated queue events into one giant trace or stretch a single trace across multiple days.

## 7. Azure Observability Architecture

~~~mermaid
flowchart TD
    A[Spring Boot App Service / ACA / AKS] --> O[OpenTelemetry Java instrumentation]
    O --> M[Azure Monitor / Application Insights ingestion]
    M --> W[Log Analytics workspace]
    W --> K[KQL queries / Workbooks]
    M --> I[Application Map / transaction views]
    W --> AL[Azure Monitor alerts]
    AL --> AC[Action Groups: email / webhook / ITSM]
    A --> PM[Azure platform metrics & diagnostic settings]
    PM --> W
~~~

A **workspace-based Application Insights resource** links to a **Log Analytics workspace**. It powers Application Map, transaction search, Failures, and telemetry queries once data flows properly. Azure Monitor also offers platform metrics and resource diagnostic settings: **infrastructure telemetry** differs from **application instrumentation**.

### Three Layers to Connect

1. **Application layer:** Java requests, dependencies, exceptions, custom spans/metrics.
2. **Azure resource layer:** App Service/AKS/Container Apps CPU, memory, restarts, networking, DB metrics.
3. **Business layer:** orders completed, failed payments, queue lag, customer SLOs.

Looking only at application requests can miss a Pod **`OOMKilled`** event; looking only at node CPU can miss a payment HTTP 504. Correlate across **time ranges, service names, trace IDs, deployment versions, and resource IDs**.

## 8. Choosing a Java Instrumentation Approach

| Approach | Best Fit | Watch Out For |
|---|---|---|
| **Azure Monitor OpenTelemetry Java agent / distro** | Spring Boot/Java apps wanting fast auto-instrumentation | JDK/agent versions, dependency compatibility, agent startup |
| **OpenTelemetry Java agent + exporter/collector** | Organizations standardized on multi-backend OTel pipelines | Collector/exporter/config and operations |
| **OpenTelemetry SDK + manual instrumentation** | Custom business spans or unsupported frameworks | Context propagation, lifecycle, double instrumentation |
| **Spring Boot Micrometer Observation/Tracing** | Native Spring Boot framework observability | Bridge/exporter, sampling, auto-instrument overlap |
| **Platform diagnostics/logs** | Host-level metrics and logs | Does not replace distributed tracing automatically |

**Start with one primary instrumentation method per service.** Enabling multiple Java agents, SDK exporters, or bridges simultaneously can emit duplicate requests/dependencies, break span context, raise costs, and distort metrics.

### Decision Guidelines

- Need fast results with no separate OTel platform: start with **Azure Monitor-supported Java instrumentation**.
- Already running an OTel Collector/Tempo/Prometheus stack: follow org OTel standards and export to Azure Monitor where supported.
- Only need visibility into `"order validation"` or `"checkout stage"`: add **custom business spans** rather than rewriting HTTP/JDBC instrumentation.
- Need accurate overall SLO request rates: emit **metrics** alongside traces rather than estimating solely from sampled traces.

## 9. Configuring Java Auto-Instrumentation

A common setup uses the Microsoft-supported **Azure Monitor OpenTelemetry Java agent** for your Java version. **Illustrative** commands:

~~~bash
export APPLICATIONINSIGHTS_CONNECTION_STRING="<APPLICATION_INSIGHTS_CONNECTION_STRING>"
export OTEL_SERVICE_NAME="orders-api"

java -javaagent:/opt/observability/applicationinsights-agent.jar \
     -jar /app/orders-api.jar
~~~

**Note:** agent filenames, role/resource attribute settings, and Azure Monitor agent APIs vary across releases. Fetch the **official agent from a trusted source**, pin its version, and verify environment-variable handling and the Java support matrix before production. Paths shown here are examples, not instructions to download arbitrary binaries.

### What Is the Connection String?

An Application Insights resource provides a **connection string** specifying the ingestion endpoint and instrumentation identity. It is **not** an OAuth Bearer token proving user authorization, and depending on ingestion setup, the instrumentation key inside it is not a strong auth secret. Still, protect the configuration and restrict who can modify it to prevent telemetry pollution or routing data into the wrong resource.

### When the Agent Runs

A Spring Boot app automatically captures HTTP server/client spans, supported JDBC/database calls, logs/exceptions, and messaging dependencies per agent support. **Never assume every third-party SDK, native call, or custom executor is auto-instrumented.** Verify supported frameworks and versions.

## 10. Verifying First Telemetry in Application Insights

After instrumenting a **sandbox** app, send dummy requests:

~~~bash
curl --silent --show-error -i \
  https://<LAB_HOST>/api/health-demo

curl --silent --show-error -i \
  https://<LAB_HOST>/api/orders/demo
~~~

These are **placeholder** URLs; endpoints must exist in your lab app with the right hostname. Never put tokens or PII into shell history or CLI arguments on shared hosts.

### Where to Look?

1. Open the right **Application Insights resource** in the Azure Portal.
2. Check Live Metrics / ingestion if supported.
3. Open **Transaction search / Performance / Failures / Application Map** per Portal layout.
4. Select the matching time window and **cloud role name / environment**.
5. Locate the test HTTP request and open end-to-end transaction details.
6. Verify child SQL/HTTP dependency spans, statuses, and durations appear.
7. Run Log Analytics queries to inspect `AppRequests`, `AppDependencies`, and `AppExceptions`.

**Do not assume the agent is broken simply because data doesn't appear instantly.** Consider ingestion latency, sampling, time filters, wrong resource/connection string, outbound network policy, or permissions. Conversely, never excuse a broken configuration with "data will show up later" without checking agent logs.

## 11. Deploying Instrumentation on Azure App Service

For Spring Boot on **Azure App Service Java SE**, attach the agent per runtime instructions; for **custom containers**, bake the agent into the image or use supported instrumentation hooks.

~~~text
CI build Spring Boot JAR
         |
         v
Azure App Service Java SE
         |
         +-- Supported Java runtime / JDK
         +-- Azure Monitor Java instrumentation
         +-- Application Insights connection string in App Settings
         +-- Managed identity / Key Vault if needed
         |
         v
Log Analytics workspace
~~~

### What Must Be Verified

- Distinct Application Insights resources/connection strings for **dev, staging, and production**; never mix telemetry.
- If using a **self-managed Java agent**, confirm the JAR exists at the configured path and startup args / `JAVA_TOOL_OPTIONS` attach it to the JVM.
- If App Service provides **platform codeless auto-instrumentation**, check its version and avoid attaching a second manual agent on top.
- App egress permits reaching **ingestion endpoints** across DNS, TLS, proxies, and firewalls.
- **Application role name, role instance, environment, and release version** appear consistently in telemetry.
- Health checks are not materially degraded by instrumentation overhead.

**Never attach two Java monitoring agents just to "get more data"** without verifying compatibility; doing so duplicates telemetry and slows startup.

## 12. Deploying on Azure Container Apps

On **Container Apps**, packages typically bundle the app and an approved agent into an OCI image or use an environment-appropriate OTel/Collector setup.

**Illustrative** Dockerfile assuming the agent was downloaded, integrity-checked, and placed in an organization-controlled build context:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app

COPY --chown=10001:10001 target/orders-api.jar /app/orders-api.jar
COPY --chown=10001:10001 observability/applicationinsights-agent.jar \
     /opt/observability/applicationinsights-agent.jar

USER 10001:10001
EXPOSE 8080

ENV JAVA_TOOL_OPTIONS="-javaagent:/opt/observability/applicationinsights-agent.jar"
ENTRYPOINT ["java", "-jar", "/app/orders-api.jar"]
~~~

**This Dockerfile runs only with the right build artifacts present**, does not download the agent, and omits image/agent digest pinning for brevity. In production, pin base images and agents, scan SBOMs/CVEs, run non-root, and keep connection strings out of images.

### Application Configuration

~~~text
Container App: orders-api-prod
  APPINSIGHTS_RESOURCE: production instance
  APPLICATIONINSIGHTS_CONNECTION_STRING: injected via app configuration
  OTEL_SERVICE_NAME: orders-api
  APP_VERSION: 2.4.1
~~~

These lines are a **configuration summary**, not a deployment YAML schema. Inject environment variables via ACA secrets/env mechanisms; never commit real values into YAML or container images.

### Revisions and Role Names

When two revisions serve canary traffic simultaneously, distinguish **app version / revision** in attributes and logs. Keeping the same cloud role name lets Application Map group them into one logical service node, while adding a bounded **version/revision dimension** helps isolate regressions.

## 13. AKS and the OpenTelemetry Collector

On **AKS**, Java Pods can be instrumented with an agent exporting directly to Azure Monitor where supported, or sending OTLP to a platform-managed **OpenTelemetry Collector**.

~~~mermaid
flowchart LR
    P1[orders-api Pod] --> C[OTel Collector]
    P2[payment-api Pod] --> C
    W[worker Pod] --> C
    C --> M[Azure Monitor]
    M --> L[Log Analytics]
~~~

### When Exporting Direct

- Configure ingestion credentials/connection strings or Entra-based auth where supported by the exporter.
- Define sampling and attribute filtering on the app/agent.
- Verify egress TLS, DNS, proxies, and NetworkPolicies.
- Tag each Pod with **`service.name`, `service.version`, and `deployment.environment.name`** per supported conventions.

### When Routing Through a Collector

- Provision Collector CPU/RAM, autoscaling, and batch/retry policies.
- Filter/redact data, swap exporters, or fan out to multiple backends centrally.
- Network failures or backpressure can **drop telemetry**; a Collector is not a durable transactional store by default.
- Pick the right topology (DaemonSet, Deployment, sidecar) and secure OTLP ports.
- Never pass raw tokens or passwords through the Collector in attributes or logs.

**An OTel Collector is not mandatory for every AKS workload.** It adds operational overhead; smaller teams may find supported direct-exporting agents simpler.

## 14. Azure Functions, Background Workers, and the Functions Host

**Azure Functions Java** runs a host process alongside a Java worker process per its programming model. Telemetry from host invocations/bindings and spans emitted by Java code can travel through different pipelines.

### Configuring Function Observability

1. Verify Application Insights integration on the **Function App** and hosting plan.
2. Inspect host logs, function execution counts, retries, and failures.
3. If adding an OpenTelemetry SDK/agent to the Java worker, verify compatibility and avoid duplicating host telemetry.
4. Propagate context from Service Bus / Event Hubs messages per supported bindings/SDKs.
5. Record business outcomes and idempotency conflicts separately from host invocation success.

A **successful Function invocation** does not prove a message led to a DB commit and email delivery if the function caught exceptions and kept going or fired unawaited async work. Always verify settlement, retries, and business status.

## 15. Dependency Telemetry: Attributes to Capture

A dependency is an outbound call from a service to an **external process** or major subsystem. Capture:

| Attribute | Example | Notes |
|---|---|---|
| **Dependency type** | HTTP, SQL, Redis, Service Bus | Follow semantic conventions |
| **Name** | `GET /payments/{id}`, `SELECT orders` | Avoid names containing user IDs |
| **Target** | `payment-api.internal`, `orders-db` | Never include connection strings or passwords |
| **Duration** | 280 ms | Supports latency and critical-path analysis |
| **Result code** | HTTP 503, SQL error code | Classifies failures |
| **Success/status** | true/false or status code | Follow semantic conventions; don't mark all 4xx as server faults |
| **Trace/span context** | trace ID, parent span | Links back to the root request |
| **Retry attempt** | 0, 1, 2 | Keep cardinality bounded if added as a custom dimension |
| **Service version/environment** | `orders-api 2.4.1 prod` | Use stable attributes |

### What Never to Capture Freely

- Full SQL statements containing literal values or customer IDs.
- HTTP `Authorization` headers or `Set-Cookie`.
- Request/response bodies containing PII.
- Database connection strings or SAS tokens.
- URLs embedding emails, phone numbers, payment tokens, or access keys.
- Full Service Bus message payloads containing customer data.

**Keep dependency names low-cardinality**—such as **`GET /orders/{id}`** instead of a distinct name per order ID. This reduces costs and keeps dashboards readable.

## 16. HTTP Dependencies in Spring Boot

When Spring Boot calls **`payment-api`** via an instrumented `RestClient`, `WebClient`, or `HttpClient`, the agent creates an **HTTP CLIENT span**.

~~~text
Incoming:
  POST /api/orders
    |
    +-- HTTP CLIENT POST payment-api /charge
            duration=980 ms
            http.response.status_code=503
            status=ERROR or result logic per instrumentation
~~~

### `RestClient` Example with Timeouts

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import java.net.http.HttpClient;
import java.time.Duration;

public final class PaymentGateway {
    private final RestClient client;

    public PaymentGateway(String baseUrl) {
        HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

        JdkClientHttpRequestFactory factory =
            new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(Duration.ofSeconds(5));
        this.client = RestClient.builder()
            .baseUrl(baseUrl)
            .requestFactory(factory)
            .build();
    }

    public String charge(String requestJson) {
        return client.post()
            .uri("/charge")
            .contentType(MediaType.APPLICATION_JSON)
            .body(requestJson)
            .retrieve()
            .body(String.class);
    }
}
~~~

**This is a dependency-call skeleton, not a complete production HTTP client.** It uses **`RestClient` and `JdkClientHttpRequestFactory`** (Spring Framework 6.1+ / compatible Spring Boot), setting a 3s connect timeout and 5s read timeout on the factory without enforcing an **overall deadline** across retries or the entire business operation. Production code also needs retry/backoff, TLS, auth, cancellation, connection pooling, and version-specific client tuning.

### A Dependency Failure Isn't Automatically an Endpoint Failure

An API might receive a 503 from `payment-api` yet legitimately use a **fallback, queue, or pending status** to return HTTP 202. The dependency span should mark the call failure while the request span succeeds per business contract. Conversely, **swallowing** a timeout and returning 200 claiming "payment succeeded" is a business bug.

## 17. SQL/JDBC Dependencies

With PostgreSQL / Azure SQL and JDBC / Spring Data JPA, supported instrumentation creates dependency spans for database calls.

~~~text
POST /api/orders (SERVER)
    |
    +-- jdbc: SELECT carts (...)      15 ms
    +-- jdbc: INSERT orders (...)     31 ms
    +-- jdbc: UPDATE inventory (...)  80 ms
~~~

### Distinguishing Slow SQL from Connection Pool Wait

A 2-second request does not mean the SQL query ran for 2 seconds. Consider:

~~~text
Wait for HikariCP connection: 1.700 ms
Execute SQL query:             100 ms
Serialize response:             40 ms
--------------------------------------
Total:                        1.840 ms
~~~

If auto-instrumentation shows **JDBC SQL 100 ms**, the request is still slow due to **pool acquisition** beforehand. Monitor **Hikari active, idle, pending, and timeout** metrics alongside transaction timeouts, thread pools, and targeted custom spans.

### Safe SQL Query Text

Never enable full SQL parameter logging in production if queries touch PII. On JDBC spans, keep **DB system, operation, safe statement template, and server address** per policy—never log passwords or sensitive literals.

### `@Transactional`

~~~java
@Transactional
public Order createOrder(CreateOrderCommand cmd) {
    Order order = repository.save(...);
    outboxRepository.save(...);
    return order;
}
~~~

This is pseudo-code; **`@Transactional`** governs the database transaction only—it does not commit a Service Bus message or turn an HTTP + payment call into an atomic transaction. Application tracing tracks individual steps and transaction status separately.

## 18. Redis, Storage, and Service Bus Dependencies

A single request might call:

- **Azure Cache for Redis** for caching or locks.
- **Azure Blob Storage** for files and documents.
- **Azure Service Bus** to publish messages.
- **Event Hubs / Cosmos DB / Azure OpenAI** depending on workload.

~~~text
POST /orders
   +-- Redis GET cart          3 ms
   +-- PostgreSQL INSERT      20 ms
   +-- ServiceBus SEND        45 ms
   +-- Blob UPLOAD           150 ms
~~~

### Verify Instrumentation Support for Each SDK

OpenTelemetry Java auto-instrumentation covers many libraries, yet **does not cover every Azure SDK version or async callback identically**. If Service Bus dependencies don't appear:

1. Check the agent version and client library version.
2. Check exporter, ingestion, and correlation settings.
3. Check async context propagation.
4. If unsupported by the framework, wrap send/receive calls in a **custom span** following semantic conventions.
5. Never duplicate spans by manually instrumenting what the agent already records.

### Broker Accepted Differs from Business Processed

Service Bus **`Send` succeeded** means the broker accepted the message; it **does not prove** the worker processed it or committed to the database. To trace request → invoice created, combine consumer spans, business events, and correlation keys.

## 19. Dependency Retries, Timeouts, and Circuit Breakers

Example retried call to `payment-api`:

~~~text
GET /payment-status (SERVER) 6.3 s
   |
   +-- payment-api GET attempt 1: 2.0 s timeout
   +-- delay: 200 ms
   +-- payment-api GET attempt 2: 2.0 s timeout
   +-- delay: 500 ms
   +-- payment-api GET attempt 3: 1.6 s HTTP 200
~~~

**You may observe three dependency attempts for one request.** Looking solely at dependency success rate shows high error rates even though the end-user got HTTP 200; looking solely at request success misses early signs of overload.

### What to Measure

| Metric / Signal | Meaning |
|---|---|
| Number of attempts per request | Retry amplification |
| Retry-after / backoff time | Waiting latency |
| Final outcome | User-visible result |
| Circuit breaker state | `OPEN`/`HALF_OPEN`/`CLOSED` per implementation |
| Timeout type | Connect, read, overall deadline |
| Dependency target | Which target fails repeatedly |
| Upstream duration | Critical path |

Avoid unbounded retries or synchronized retries across replicas, which trigger **retry storms**. Use exponential backoff with jitter, bounded overall deadlines, and circuit breakers/bulkheads where appropriate.

### Span Status Is Not a Business Verdict

A retried HTTP 503 attempt may record an error while the final attempt succeeds. Crucially, **do not interpret every failed dependency attempt as a failed transaction**, and conversely do not hide abnormal retry rates just because the final attempt succeeded.

## 20. Exception Telemetry: Which Exceptions Should Be Recorded?

An **exception** can be:

- An unhandled error causing HTTP 5xx.
- A caught error triggering a retry or fallback.
- Invalid input mapped to HTTP 400/422.
- A domain rejection modeled with result types instead of exceptions.
- A swallowed async task exception never reaching the HTTP response.

| Scenario | HTTP/API Outcome | What to Observe |
|---|---|---|
| Unhandled `NullPointerException` | Usually 500 | Exception stack + request trace |
| Payment timeout with pending fallback | Potentially 202 | Dependency failure, exception, business pending state |
| `ValidationException` | 400/422 | Client error rate; full stack trace rarely needed every time |
| Authorization denied | 401/403 | Security telemetry without leaking tokens |
| Queue worker throws | No HTTP response | Consumer trace, retry/DLQ, error event |
| Exception caught and suppressed | Potentially 200 but wrong business state | Requires deliberate instrumentation/logging |

**Never log the same exception at every layer** (repository, service, controller, global handler) for one error; that inflates log volume and makes one bug look like multiple incidents. Log once at an informed boundary while setting span status/exception events where appropriate.

## 21. Handling Exceptions in Spring Boot

Spring Boot uses **`@RestControllerAdvice`** to translate exceptions into structured HTTP responses. Never leak stack traces or raw SQL errors to the frontend.

~~~java
package com.example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(PaymentTimeoutException.class)
    public ProblemDetail paymentUnavailable(PaymentTimeoutException ex) {
        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.BAD_GATEWAY);
        problem.setTitle("Payment service unavailable");
        problem.setDetail("Try again later or check order status.");
        return problem;
    }
}
~~~

**`PaymentTimeoutException` is a project-defined type**; this snippet is not a full project. On supported Spring Boot / Spring Framework versions, **`ProblemDetail`** standardizes HTTP error payloads. In production, select **502/503/504** per real semantics, log exceptions once with correlation IDs at the right boundary, and consider mapping timeouts to **`PENDING`** states rather than always failing hard.

### Handled vs. Unhandled Exceptions

Once a handler catches an exception and converts it to `ProblemDetail`, some instrumentation may **stop automatically recording an exception event** even with HTTP 502; verify behavior. If needed, record the exception once deliberately in your tracing/logging layer. Never force every expected input validation error into an ERROR span if it conforms to the business contract.

### Separate Expected Rejections from Operational Errors

- **Validation/business rejections:** return 400/409/422 per API contract with dedicated metrics; avoid noisy stack traces.
- **Transient dependency outages:** apply bounded retries/fallbacks and alert on rate and impact.
- **Programming bugs:** capture exception stacks and release versions to fix code.
- **Security failures:** keep minimal logs without access tokens or sensitive bodies.

## 22. Custom Spans for Business Steps

Auto-instrumentation sees HTTP/JDBC calls, yet misses steps like **validate voucher**, **reserve inventory**, or **calculate shipping**. Custom spans place key domain stages inside the trace.

Example using the **OpenTelemetry API**:

~~~java
package com.example.orders;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class PriceCalculator {

    private static final Tracer TRACER =
        GlobalOpenTelemetry.getTracer("orders-domain", "1.0.0");

    public long calculateCents(int itemCount) {
        Span span = TRACER.spanBuilder("order.calculate-price")
            .setSpanKind(SpanKind.INTERNAL)
            .startSpan();
        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("order.item_count", itemCount);
            if (itemCount < 0) {
                throw new IllegalArgumentException("Invalid item count");
            }
            return itemCount * 1200L;
        } catch (RuntimeException ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR);
            throw ex;
        } finally {
            span.end();
        }
    }
}
~~~

This compiles once a compatible **`io.opentelemetry:opentelemetry-api`** dependency and Java version are declared; hardcoded pricing is purely illustrative. **The API provides no exporter by itself**: a configured SDK/agent is required to send spans to Azure Monitor. If `GlobalOpenTelemetry` is uninitialized, calls act as no-ops.

### Choosing Custom Attributes Carefully

Good:

~~~text
order.item_count = 3
order.channel = "web"
order.validation_result = "accepted"
order.version = 2
~~~

Avoid:

~~~text
order.customer_email = "person@example.com"
payment.card_number = "<SENSITIVE>"
http.request.body = "<RAW_CUSTOMER_DATA>"
order.id = "<MILLIONS_OF_UNIQUE_VALUES_AS_METRIC_LABEL>"
~~~

An order ID helps troubleshooting yet easily becomes PII or a high-cardinality dimension. If needed for correlation, use an opaque ID under governance and retention rules—never as a **metric label** or in public queries.

## 23. OpenTelemetry Status and Exception Recording

In OpenTelemetry:

- **`span.recordException(exception)`** records an exception event on the span.
- **`span.setStatus(StatusCode.ERROR)`** marks the span as failed technically or business-wise.
- **`span.end()`** completes the span so the exporter can ship it.

### Three Scenarios

**A. Unhandled exception:** record the exception and set `StatusCode.ERROR` before rethrowing, or let the instrumentation boundary handle it—avoid recording twice.

**B. Caught exception with successful fallback:** the dependency span records failure, while the outer **transaction span** reflects fallback success or valid degraded state.

**C. Normal business rejection:** e.g., an expired voucher can return 409/422 with a custom event/metric rather than a programming exception.

**Never judge application quality solely by exception telemetry counts.** One app may catch errors and return wrong 200s, while another logs many cleanly handled transient exceptions.

## 24. Micrometer Observation in Spring Boot

Spring Boot supports **Micrometer Observation/Tracing** depending on version and dependencies. Using the **Observation API** records durations and context for business operations.

Conceptual example:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class OrderValidator {
    private final ObservationRegistry registry;

    public OrderValidator(ObservationRegistry registry) {
        this.registry = registry;
    }

    public boolean validate(int count) {
        return Observation.createNotStarted("order.validate", registry)
            .lowCardinalityKeyValue("order.channel", "api")
            .observe(() -> count > 0);
    }
}
~~~

**A Micrometer observation does not automatically emit an Azure span**: you need a matching tracing bridge, exporter, or agent configuration. When combining Micrometer with auto-instrumentation, test trace context and avoid emitting duplicate spans for the same step.

### Low vs. High Cardinality

- **Low cardinality:** `http.route`, `outcome`, `dependency.type`, `service.version` (bounded).
- **High cardinality:** `userId`, raw `orderId`, URLs with query strings, `messageId`.

Metric series can explode cost and memory with millions of label values. Traces can hold richer context, yet still must follow data protection and storage rules.

## 25. Context Propagation Across Threads and Async Execution

In Spring Boot apps, work often hops from the HTTP thread to:

- **`CompletableFuture` / `ExecutorService`**.
- **`@Async`**.
- **Project Reactor / WebFlux**.
- **Kafka / Service Bus listeners**.
- Batch jobs or schedulers.

Trace context often lives in **`ThreadLocal`** or an equivalent context holder. Spawning a raw thread outside a context-aware executor causes child spans to lose their parent.

~~~text
HTTP SERVER trace T
     |
     +-- @Async worker without context propagation
            |
            +-- new root trace T2 [broken correlation]
~~~

### How to Handle It

1. Prefer framework integrations supported by your agent/OTel instrumentation.
2. For custom `Executor`s, use context-wrapping / `TaskDecorator` recommended by the framework.
3. For Reactor, enable version-appropriate context propagation.
4. Never store a long-lived **`Span` or `Scope`** inside a shared singleton bean across requests.
5. For late-arriving async messages, use messaging extraction and span links per semantics.
6. Test actual trace trees, not just unit-test return values.

### A Sign of Lost Context

In Application Insights, `payment-api` shows up as an **independent root request** even though `orders-api` called it; their trace IDs differ. Causes include proxies stripping W3C headers, uninstrumented HTTP clients, lost async context, or downstream services failing to extract context.

## 26. Structured Logs and Correlation

Logs only link reliably to traces when correlation fields are present:

~~~json
{
  "timestamp": "2026-11-20T10:12:30Z",
  "level": "WARN",
  "service": "orders-api",
  "traceId": "1234567890abcdef1234567890abcdef",
  "spanId": "1111111111111111",
  "event": "payment_retry",
  "attempt": 2,
  "dependency": "payment-api",
  "errorClass": "TimeoutException"
}
~~~

This is an **illustrative log**; it does not appear automatically just by adding Actuator. Configure logging patterns, JSON encoders, and OTel log correlation. With SLF4J MDC, preserve and clear context carefully across async hops.

### Never Log Payloads by Default

A **`POST /checkout`** request can carry addresses, phone numbers, or payment fields. None of that is needed to count errors or measure latency, and logging it turns logs into an uncontrolled sensitive data store.

Keep **service, operation name, status/error category, trace ID, and deployment version**; enable redaction and restricted diagnostics only with explicit authorization, purpose, and expiration.

## 27. Sampling: Why Does a Request Have No Trace?

Sampling cuts volume and cost, meaning not every request appears in trace queries.

| Mechanism | Idea | Trade-Off |
|---|---|---|
| **Head-based sampling** | Decides early whether to keep the trace, often respecting parent flags | Low overhead; can miss rare errors |
| **Tail-based sampling** | Decides after seeing outcome/duration where supported | Collector memory, complexity, and latency |
| **Adaptive / ingestion sampling** | Adjusts rate dynamically per product capability | Raw counts skew without weighting |
| **No sampling** | Keeps all telemetry | High cost and potential overload |

### Example

If sampling retains 10% of traces across 1,000 requests, you may see roughly 100 request records in trace analytics. **Never run `COUNT()` on sampled data and claim only 100 real requests occurred.**

### `ItemCount` in Application Insights

Some Application Insights tables include **`ItemCount`** to estimate how many records a sampled row represents. When appropriate, use **`sum(ItemCount)`** for totals instead of `count()`. However:

- `ItemCount` behavior depends on the pipeline and sampling mode.
- Tail sampling or filtering may not be reconstructed accurately via simple weighting.
- Percentiles and joins over sampled traces can still skew.
- Custom metrics or standalone metrics follow separate sampling rules.

**SLOs and billing** should rely on purpose-built metrics and counters rather than reconstructing counts exclusively from sampled traces.

## 28. Log Analytics Schemas: `AppRequests` and Related Tables

In **workspace-based Application Insights**, common tables in **Log Analytics** include:

| Table | Data |
|---|---|
| **`AppRequests`** | Request telemetry, duration, result code, operation |
| **`AppDependencies`** | Outgoing dependency calls, target, duration, success |
| **`AppExceptions`** | Exception type/message/details, operation correlation |
| **`AppTraces`** | Log/trace messages and severity |
| **`AppEvents`** | Custom events if written by exporter/SDK |
| **`AppMetrics`** | Custom metrics/telemetry per pipeline |

In **Application Insights classic analytics** or older docs, you may encounter **`requests`, `dependencies`, `exceptions`, `traces`** with different column names. **Never copy an `AppRequests` query onto `requests` without updating column names.**

### Useful Columns in Workspace-Based Tables

~~~text
TimeGenerated       telemetry timestamp
OperationId         ID correlating operation/trace
Id / ParentId       span/request identity and hierarchy
AppRoleName         service/application role
Name                request/dependency name
DurationMs          duration in milliseconds
Success             true/false per telemetry
ResultCode          HTTP/SQL/result code
ItemCount           sampling weight where supported
Properties          dynamic custom fields
~~~

Available columns vary by table, SDK, and ingestion pipeline; **`ResultCode`** may be a string and **`Properties`** is dynamic. Inspect your workspace's real schema before finalizing production dashboards.

## 29. KQL: Request Rate and 5xx Errors

In workspace-based Application Insights **Logs**:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| summarize
    Requests = sum(ItemCount),
    FailedTelemetry = sumif(ItemCount, Success == false),
    ServerErrors = sumif(ItemCount,
        toint(ResultCode) >= 500 and toint(ResultCode) < 600)
  by bin(TimeGenerated, 5m)
| extend ErrorRatePct =
    iff(Requests > 0, 100.0 * ServerErrors / Requests, real(null))
| order by TimeGenerated asc
~~~

### How to Read It

- **`Requests`** is an estimated total when `ItemCount` applies.
- **`FailedTelemetry`** uses telemetry's `Success` flag, which may include non-5xx failures.
- **`ServerErrors`** counts HTTP 5xx responses.
- **`ErrorRatePct`** measures only 5xx rate in observed request telemetry, not business failures.

**Verify schemas and sampling before concluding.** Filtered telemetry, uninstrumented endpoints, or mismatched role names can leave gaps.

## 30. KQL: Slow Requests by Endpoint

~~~kusto
AppRequests
| where TimeGenerated >= ago(24h)
| where AppRoleName == "orders-api"
| summarize
    ObservedRequests = count(),
    AvgDurationMs = avg(DurationMs),
    P50Ms = percentile(DurationMs, 50),
    P95Ms = percentile(DurationMs, 95),
    P99Ms = percentile(DurationMs, 99)
  by Name
| order by P95Ms desc
~~~

**Percentiles over sampled rows reflect stored samples**, which may diverge from all traffic under biased sampling. Where built-in server duration histograms or proper metrics exist, prefer them for SLOs; KQL here shines for diagnostics.

### Avoid High Cardinality

If request **`Name`** is emitted as:

~~~text
GET /orders/1001
GET /orders/1002
GET /orders/1003
~~~

every dynamic URL creates a separate group. Instrumentation should emit **route templates** such as **`GET /orders/{id}`** for clean grouping and to avoid dimension explosion.

## 31. KQL: Which Dependency Is Slow or Failing?

~~~kusto
AppDependencies
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| summarize
    ObservedCalls = count(),
    EstimatedCalls = sum(ItemCount),
    EstimatedFailures = sumif(ItemCount, Success == false),
    P95DurationMs = percentile(DurationMs, 95)
  by Type, Target, Name
| extend FailurePct =
    iff(EstimatedCalls > 0,
        100.0 * EstimatedFailures / EstimatedCalls, real(null))
| order by EstimatedFailures desc, P95DurationMs desc
~~~

### Interpretation

If results show:

~~~text
Type=HTTP
Target=payment-api.internal
Name=POST /charge
FailurePct=18%
P95DurationMs=4200
~~~

that warrants immediate investigation. **Do not claim `payment-api` is failing 18% system-wide** if the SDK only instruments certain calls or sampling/grouping is partial. Cross-check `payment-api` logs, gateway metrics, and HTTP statuses.

### When `Target` Varies by Hostname

An API might be called via internal DNS, APIM, and a public hostname; without consistent cloud role/service naming, Application Map may split it into multiple dependency nodes. Never overwrite targets arbitrarily; preserve accurate route context and reliable service mappings.

## 32. KQL: Comparing Dependency Success with Request Success

~~~kusto
let Requests =
    AppRequests
    | where TimeGenerated >= ago(30m)
    | where AppRoleName == "orders-api"
    | summarize Requests = sum(ItemCount),
                FailedRequests = sumif(ItemCount, Success == false);
let Dependencies =
    AppDependencies
    | where TimeGenerated >= ago(30m)
    | where AppRoleName == "orders-api"
    | summarize Calls = sum(ItemCount),
                FailedCalls = sumif(ItemCount, Success == false);
Requests
| extend JoinKey = 1
| join kind=inner (Dependencies | extend JoinKey = 1) on JoinKey
| project Requests, FailedRequests, Calls, FailedCalls,
          RequestFailurePct = iff(Requests > 0,
              100.0 * FailedRequests / Requests, real(null)),
          DependencyFailurePct = iff(Calls > 0,
              100.0 * FailedCalls / Calls, real(null))
~~~

This compares **two signals with different denominators**, not a 1:1 ratio: one request can make 10 dependency calls, retries inflate call counts, and some requests make zero dependency calls. It helps spot rising dependency failures **before** end-user error rates climb.

### Interpretation Patterns

- Low request failures, high dependency failures: fallbacks/retries are absorbing or masking faults.
- High request failures, low dependency failures: look at validation, serialization, CPU/thread pools, or local code.
- Both rising: focus on the failing dependency target and critical path.

## 33. KQL: Grouping Exceptions by Type and Service

~~~kusto
AppExceptions
| where TimeGenerated >= ago(24h)
| summarize
    EstimatedOccurrences = sum(ItemCount),
    ObservedRows = count(),
    AffectedTraces = dcount(OperationId)
  by AppRoleName, Type, ProblemId
| order by EstimatedOccurrences desc
~~~

### Proper Analysis

- **`Type`:** exception class, e.g., `SocketTimeoutException`.
- **`ProblemId`:** grouping fingerprint depending on SDK.
- **`AffectedTraces`:** distinct trace IDs in **observed** data—not automatically equal to affected users.
- **`EstimatedOccurrences`:** estimate when `ItemCount` tracks sampling.

If one error cascades across services, a single trace can contain multiple exception records. **Never sum `AffectedTraces` across groups and treat the sum as unique requests.**

### When `AppExceptions` Is Empty

Possible reasons: zero exceptions occurred, agent lacks instrumentation, exceptions were caught/swallowed, pipeline filtered/sampled them, or wrong resource/time range. Cross-check **`AppRequests` 5xx, `AppTraces` ERRORs, and platform logs**, and verify with a controlled lab fault.

## 34. KQL: Finding Exceptions for a Specific Trace

If you have the **`OperationId`** from a failed request:

~~~kusto
let traceId = "1234567890abcdef1234567890abcdef";
AppExceptions
| where TimeGenerated >= ago(24h)
| where OperationId == traceId
| project TimeGenerated, AppRoleName, Type, ProblemId,
          OuterMessage, OperationId
| order by TimeGenerated asc
~~~

**`OuterMessage` can contain PII or SQL details.** Restrict queries to authorized workspaces; drop or redact this column on broad dashboards and never push raw messages into Slack or email alerts.

### When Multiple Exceptions Occur

One HTTP request might retry payment 3 times, emit 3 `SocketTimeoutException`s, and finally succeed. Inspect the timeline and dependencies for **order and final outcome**, rather than counting three exceptions as three failed orders.

## 35. KQL: Combining Requests, Dependencies, and Exceptions by Operation

Viewing the timeline for a known **trace ID**:

~~~kusto
let traceId = "1234567890abcdef1234567890abcdef";
union
(
    AppRequests
    | where TimeGenerated >= ago(24h) and OperationId == traceId
    | project TimeGenerated, Kind = "REQUEST",
              Service = AppRoleName,
              Label = Name,
              Result = ResultCode,
              DurationMs,
              OperationId
),
(
    AppDependencies
    | where TimeGenerated >= ago(24h) and OperationId == traceId
    | project TimeGenerated, Kind = "DEPENDENCY",
              Service = AppRoleName,
              Label = Name,
              Result = ResultCode,
              DurationMs,
              OperationId
),
(
    AppExceptions
    | where TimeGenerated >= ago(24h) and OperationId == traceId
    | project TimeGenerated, Kind = "EXCEPTION",
              Service = AppRoleName,
              Label = Type,
              Result = "",
              DurationMs = real(null),
              OperationId
)
| order by TimeGenerated asc
~~~

### Strengths and Limits

- Clearly shows **chronological sequence** within one trace.
- Does not fully represent **parent–child** trees when sorted only by time; add `Id`/`ParentId` or use the end-to-end trace UI.
- Spans can overlap concurrently, so `TimeGenerated` ordering does not prove causality.
- Sampling drops can leave gaps in the timeline.
- Broken trace context gives `payment-api` a different `OperationId`, hiding it from this filter.

**`OperationId` in workspace-based Application Insights** commonly correlates records within an operation. Verify against your actual pipeline before hardcoding assumptions about column layout.

## 36. KQL: Finding the Slowest Transactions to Investigate

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| where AppRoleName == "orders-api"
| where Name == "POST /api/orders"
| top 20 by DurationMs desc
| project TimeGenerated, OperationId, Name, DurationMs,
          ResultCode, Success, AppRoleName
~~~

Pick an **`OperationId`** from the results and run the query in Section 35 or open **End-to-end transaction details**.

### Critical Path Analysis

Suppose:

~~~text
HTTP SERVER POST /orders  4.8 s
  +-- SQL 0.03 s
  +-- Redis 0.01 s
  +-- Payment HTTP 4.5 s
  +-- Serialization 0.02 s
~~~

A much stronger hypothesis than "Azure SQL is slow" is that **Payment HTTP drives most of the request latency**. Still, inspect the real trace for retries, scheduling, queue waits, and overlapping spans before concluding.

## 37. KQL: Monitoring Exceptions After a Deployment

Suppose **`orders-api` v2** just rolled out and you want to track errors:

~~~kusto
AppExceptions
| where TimeGenerated >= ago(2h)
| where AppRoleName == "orders-api"
| summarize
    EstimatedExceptions = sum(ItemCount)
  by bin(TimeGenerated, 5m), Type
| render timechart
~~~

### Separating v1 vs. v2

Instrument **`service.version`** or a deployment/revision attribute mapped into Application Insights **`Properties`** per SDK support. Do not assume a fixed built-in version column name; inspect real records and add **`by Version`** accordingly.

### Do Not Look Only at Raw Exception Counts

If traffic surges 10x, exception counts climb even if the **error rate** stays flat. Compare requests, failures, latency, and business outcomes across the same deployment and time window.

## 38. KQL: Checking Correlated Traces/Logs by `OperationId`

~~~kusto
let traceId = "1234567890abcdef1234567890abcdef";
AppTraces
| where TimeGenerated >= ago(24h)
| where OperationId == traceId
| project TimeGenerated, AppRoleName, SeverityLevel,
          Message, OperationId
| order by TimeGenerated asc
~~~

Lines like **`WARN payment retry`**, **`ERROR database transaction failed`**, or **`INFO order pending`** provide context that spans alone miss.

### Distinguish Log Severity from Request Outcome

An HTTP 200 request can emit WARN logs from a successful retry; an HTTP 500 might emit zero ERROR logs if logging is misconfigured. Never compute SLOs from ERROR log line counts instead of HTTP/server metrics.

## 39. Application Map: Seeing Which Service Calls Which

**Application Map** visualizes application components and dependencies derived from correlated telemetry:

~~~text
orders-web
   |
   v
orders-api  --HTTP--> payment-api
   |
   +--SQL--> orders-db
   +--Redis-> cache
   +--Queue-> Service Bus
                |
                v
            invoice-worker
~~~

For an accurate map:

- Configure stable **cloud role/service names** per app.
- Propagate **W3C trace context** over HTTP and messaging.
- Avoid leaving every service with a shared default role name like **`app`**.
- Point connection strings/resources cleanly and check cross-resource visibility.
- Ensure viewers hold read access to all participating App Insights/workspaces.

**A disappearing map node does not prove a service was deleted or stopped.** Zero traffic, sampling, unsupported instrumentation, changed role names, or ingestion glitches can hide it.

## 40. End-to-End Transaction Diagnostics

For a failing request:

1. Open Application Insights **Failures** or **Performance / Transaction search**.
2. Filter to the target operation, time range, and status.
3. Open **End-to-end transaction details** or the Portal's distributed trace view.
4. Inspect the **waterfall** and dependency spans.
5. Locate the longest span or any span with errors/abnormal statuses.
6. Expand correlated exceptions and logs for exact causes.
7. Verify the business outcome in the database or queue (with authorization).
8. Record hypotheses, evidence, and app version—never diagnose solely from one waterfall screenshot.

### Illustrative Waterfall Shape

~~~text
Time (ms):     0       1000      2000      3000      4000  5000
               |---------|---------|---------|---------|-----|
POST /orders   [============================================]
 SQL SELECT    [=]
 Redis GET      []
 payment HTTP  [--------------------------------------------]
 exception                                             [X]
 response                                             [504]
~~~

When a waterfall contains parallel child spans, trace the **critical path** instead of summing durations. A seemingly slow DB dependency can occasionally reflect client threads waiting on a connection pool; check thread and pool metrics to tell them apart.

## 41. SLIs, SLOs, and Error Budgets

Good observability answers: **are customers getting the promised level of service?**—not just whether logs exist.

### Example SLOs

For **`POST /orders`**:

- **Availability SLO:** 99.9% of valid requests complete per API contract.
- **Latency SLO:** 95% of requests complete under 500 ms under defined conditions.
- **Correctness SLI:** rate of orders free of duplicates with consistent payment state.

**These are illustrative SLOs**, not default SLAs for Azure or every app. Define exact measurement windows, valid statuses, excluded traffic, bot traffic, client cancellations, and completion semantics.

### Illustrative Error Budget

If availability SLO = 99.9%, error budget = 0.1%. Across **1,000,000 valid requests** in the window:

~~~text
Allowed error requests = 1.000.000 × 0,001 = 1.000
~~~

These numbers are hypothetical and exclude non-HTTP business failures. In practice, **SLO error rates** should rely on full metrics/counters rather than sampled traces alone.

### Why Have an Error Budget?

When the error budget burns fast after a rollout, the team can pause releases and prioritize reliability. Conversely, alerting on every "exception exists" wakes on-call for harmless validation errors.

## 42. Purpose-Built Azure Monitor Alerts

Alert types may include:

| Alert Type | Monitors | Example |
|---|---|---|
| **Metric alert** | Existing metric time series | HTTP 5xx rate, CPU/availability |
| **Log search alert** | KQL over Log Analytics | 5-minute payment dependency failure rate |
| **Activity Log alert** | Control-plane operations | Deleting App Insights resource or changing config |
| **Smart detection / anomaly** (where supported) | Abnormal patterns | Sudden spike in exceptions or latency |
| **Application-level alert** | Custom business metrics | Orders stuck pending too long, outbox backlog |

Every useful alert needs an **owner, severity, threshold, evaluation window, suppression/dedup policy, and runbook**. Never email every `AppExceptions` row, which causes alert storms.

### Example KQL to Watch Failing Dependencies

~~~kusto
AppDependencies
| where TimeGenerated >= ago(15m)
| where AppRoleName == "orders-api"
| where Target contains "payment-api"
| summarize
    Total = sum(ItemCount),
    Failures = sumif(ItemCount, Success == false)
| extend FailureRatePct =
    iff(Total > 0, 100.0 * Failures / Total, 0.0)
~~~

**Note:** this query illustrates alert logic. In an Azure Monitor **log search alert**, configure **measure, aggregation, threshold, evaluation frequency, and time window** per alert rule capabilities. Under zero-traffic conditions, 0 failures over 0 calls does not prove health: add a dedicated alert for **absence of expected traffic** where appropriate.

### Avoid Percentages on Tiny Samples

A dependency with 1 call and 1 error hits a 100% failure rate, yet rarely merits paging. Enforce **minimum volume** and tiered severities:

- Warning when rates rise on small traffic.
- Critical when significant traffic suffers, burn rate is high, and the issue persists.
- Informational if only a single synthetic test request failed.

## 43. Action Groups and Runbook Escalation

**Azure Monitor Action Groups** route notifications to email, SMS, webhooks, ITSM, or automation per supported channels and org policy.

~~~text
Metric/log alert fired
       |
       v
Azure Monitor alert rule
       |
       v
Action Group
       |
       +-- Notify on-call engineer
       +-- Open incident ticket
       +-- Include dashboard/runbook link
       +-- Optional approved automation
~~~

### Recommended Alert Payload Content

~~~text
Alert: orders-api payment dependency failure rate high
Environment: production
Time window: last 15 minutes
Observed calls / failures: from validated query
Scope: orders-api + payment-api target
Dashboard: approved Application Insights workbook
Runbook: internal incident procedure
Owner: payments integration team
Sensitive payloads: excluded
~~~

**Never include full exception messages, parameterized SQL statements, customer emails, `Authorization` headers, or payment references** in broadly delivered emails, SMS, or webhooks. Link to access-controlled telemetry instead.

### Automation Carries Risk

An alert saying "payment errors rising" must never automatically drop databases, restart every Pod, or fail over regions in violation of data residency. Automated remediation requires approvals, rate limits, idempotency, and rollback.

## 44. Distinguishing Saturation, Latency, and Dependency Failures

Slow requests can originate in many places:

| Symptom | Dependency View | Supplementary Metrics | Investigation Direction |
|---|---|---|---|
| Slow SQL spans | High JDBC p95 | DB CPU, locks, query stats | Query plans, indexes, lock contention |
| Request slow, JDBC short | Brief SQL spans | Hikari pending connections | Connection pool exhaustion |
| HTTP 503/429 from payment | HTTP CLIENT failures | Remote rate limits, retries | Backoff, bulkheads, circuit breakers |
| Many short spans, long request | Unclear critical path | JVM GC, thread pools | CPU throttling, thread starvation |
| Service Bus SEND succeeds, invoice late | Publish span succeeds | Queue age, consumer lag | Worker scaling, DB locks |
| Exceptions rise after release | New `Type`/`ProblemId` | App version | Regression / canary rollback |

**Never blindly scale up replicas when the root cause is a DB connection limit**: adding replicas opens even more connections and worsens the outage.

### Golden Signals

A standard set covers **latency, traffic, errors, and saturation**. Pair them with **business correctness** and **dependency health** to trace from user experience down to infrastructure.

## 45. Protecting Telemetry Data and Access Permissions

Telemetry can hold far more sensitive data than expected:

- URLs/query strings with user IDs or emails.
- SQL text/log exceptions containing order details.
- HTTP headers containing JWTs, API keys, or cookies.
- Service Bus message properties carrying tenant/user IDs.
- Stack traces exposing file paths, package names, or internal topology.
- Custom span attributes logging payment references.

### Core Principles

1. **Data minimization:** collect only attributes needed for diagnosis.
2. **Redaction:** scrub secrets, PII, and regulated data before export.
3. **RBAC:** restrict who can view Application Insights and Log Analytics workspaces.
4. **Retention:** align storage lifetimes and export rights with policy.
5. **Data residency:** verify workspace/ingestion regions, geo-replication terms, and compliance rules.
6. **Access auditing:** monitor who reads or exports logs as needed.
7. **Deletion workflows:** handle data-deletion requests and privacy incidents via defined procedures.

**Never treat a correlation ID as anonymization if it joins directly back to customer records.** Pseudonymization requires governance, and log access still needs strict RBAC.

### Ingestion Authentication

Do not confuse an Application Insights **connection string / instrumentation key** with end-user identity. When your exporter supports **Microsoft Entra-authenticated ingestion** and org policy requires it, configure the documented roles and settings; never assume every Java agent version uses managed identity automatically just because it runs on App Service.

### Admin Rights Differ from Data Read Rights

Azure RBAC resource roles and Log Analytics data access span multiple scopes and models. Permission to deploy an app should not automatically grant read access to all customer-containing logs.

## 46. Application Insights and Log Analytics Costs

Telemetry provides high value while consuming resources and budget:

| Factor | Impact |
|---|---|
| Ingestion volume (GB) | More logs/traces/dependencies raise costs |
| Retention | Longer storage windows incur charges per terms |
| Sampling | Cuts trace volume, potentially affecting detail |
| High-cardinality metrics | Explodes series/dimensions, slows queries |
| Queries / workbooks / alerts | Can increase compute and rule evaluation charges |
| Cross-region telemetry | Network egress, residency, and latency impacts |
| Collectors / agents | Compute CPU/RAM and operational overhead |

### Theoretical Volume Calculation

Suppose:

~~~text
100 requests/second
× 4 telemetry records/request average
× 1 KiB/record average
= 400 KiB/second

In 1 hour:
≈ 1,373 GiB raw data under binary unit assumptions
~~~

This is a **rough estimate** before compression, metadata, ingestion accounting, retries, dynamic properties, metrics, or free allowances/commitment tiers. Never treat this math as an invoice; check **Azure Monitor pricing + workspace usage** when deploying.

### Cost-Control Practices

- Define telemetry tiers: **core metrics, sampled traces, temporary debug logs**.
- Exclude noisy health-check traffic from traces if policy permits, while retaining uptime metrics.
- Filter chatty endpoints (e.g., polling) deliberately.
- Never log full request/response JSON routinely.
- Tailor retention by environment and data classification.
- Tune sampling measurably; avoid dropping rates so low that rare errors vanish.
- Configure budgets, alerts, and daily ingestion GB tracking.

**Cutting sampling isn't always optimal**: if production errors become uninvestigable, teams waste far more time diagnosing incidents; balance cost with diagnostic value.

## 47. Measuring Java Instrumentation Overhead

A Java agent can increase **CPU, RAM, startup time, log volume, and network egress**. Before broad rollout:

1. Benchmark a no-agent baseline under the same workload.
2. Enable the agent in staging or an approved production canary.
3. Measure **p50/p95 latency, throughput, JVM RSS, GC, and startup time**.
4. Watch exporter queues, dropped spans, and ingestion failures.
5. Ramp traffic gradually, comparing against uninstrumented instances.
6. Verify instrumentation across HTTP clients, JDBC, messaging, and async frameworks.
7. Pin agent versions and keep a rollback path for incompatibilities.

### If the Agent Causes Issues

Never quietly turn off all monitoring and walk away. File an incident/change record, roll back the agent version or disable the offending instrumentation module per supported docs, keep minimal platform metrics/logs running, and run compatibility tests.

### Warning Signals

If app latency holds steady while **dropped telemetry spans** surge, diagnostic visibility is vanishing. "Zero errors in Application Insights" may simply mean the exporter stopped shipping.

## 48. Runbook: Investigating an Incident in the First 15 Minutes

**Scenario:** customers report checkout is slow and failing.

### Minutes 0–3: Confirm Scope

1. Check **user-impact SLOs**: request rate, 5xx, p95/p99, affected regions.
2. Identify recently deployed services/versions and start time.
3. Check Azure platform health and DB/service metrics where relevant.
4. Distinguish a full public endpoint outage from a single slow dependency.

### Minutes 3–8: Find the Critical Path

1. In Application Insights, filter **`POST /orders`** over the incident window.
2. Pick several representative traces, not just one request.
3. Inspect waterfalls: SQL, payment HTTP, Redis, Service Bus.
4. Check failed dependency result codes and correlated exceptions.
5. Compare against a healthy request from the same window.

### Minutes 8–12: Verify Root Cause

1. Read redacted exception types and messages.
2. Compare dependency p95 and error rates by target.
3. Check retries, circuit breakers, DB pools, and queue lag.
4. If traces break at a service, check instrumentation and context propagation.
5. Check whether a recent rollout, revision, or config change introduced a regression.

### Minutes 12–15: Mitigate Impact

1. Trigger approved rollback or feature-flag toggles when evidence supports it.
2. Dampen retry storms, scale the true bottleneck, and protect data-plane integrity.
3. Notify owners and update the incident timeline.
4. After recovery, write a postmortem covering root cause, detection gaps, and prevention.

**Never alter production based on a single uncorrelated exception log.** Evidence must connect user failures, dependency latency, and system changes.

## 49. Scenario A: Slow Requests Yet Very Fast SQL Spans

**Context:** Customers see `POST /orders` taking 3 seconds; Application Insights shows the SQL query took only 60 ms.

### Hypotheses

- HikariCP pool is exhausted; requests wait 2.5 seconds before running SQL.
- Java threads are blocked by heavy CPU work or GC pauses.
- A filter, security check, or interceptor runs slowly before reaching the repository.
- Trace instrumentation skips recording connection-pool wait time.

### How to Check

1. Compare server span duration against total dependency duration in slow traces.
2. Inspect JVM thread counts, GC pauses, and CPU throttling.
3. Graph HikariCP **active, idle, pending, and timeout** metrics over time.
4. Compare max pool size × max replicas against database connection limits.
5. Add a small custom span around connection acquisition if truly needed.
6. Run a bounded load test to confirm pool waits climb with concurrency.

### Remediation

Shorten transaction durations, tune SQL queries, size connection pools carefully, and bound upstream concurrency. **Never raise every Pod's pool size unboundedly**, which can overwhelm the DB. Healthy DB metrics can still coexist with **client-side Java pool starvation**.

## 50. Scenario B: Payment Errors Spike While API Still Returns HTTP 200

**Context:** Application Insights logs many HTTP CLIENT 503s to `payment-api`, yet `POST /checkout` reports `Success=true`. On-call watches only request error rates, so no alert fires.

### Possible Explanations

- Retries succeeded, hiding the transient error from the caller.
- The app intentionally returns a **`pending`** state.
- The app **swallowed an exception and falsely returned "success."**
- HTTP dependency instrumentation flagged 503 while the controller returned a different response.

### Analysis

1. Inspect traces to see retry attempt counts and final dependency outcomes.
2. Read application/business events, not just HTTP status codes.
3. Compare order/payment database state against the API contract.
4. Check circuit breaker and fallback semantics.
5. If HTTP 200 violates business semantics, fix the API contract and tests—never tweak telemetry to hide errors.

### Better Alerting

Set **dependency failure rate + retry counts** as warnings, **final payment failure / business pending age** as customer-impact alerts, and **request 5xx / SLO burn rate** at the product layer. Each signal answers a distinct question.

## 51. Scenario C: Trace Breaks at the Service Bus Consumer

**Context:** HTTP `POST /orders` shows a Service Bus SEND dependency, yet **`invoice-worker`** does not appear under the same operation/trace in Application Insights.

### Possible Reasons

- Messages lacked W3C trace context / diagnostic properties.
- The worker did not extract context from incoming messages.
- Consumer processing jumped onto a worker thread losing OTel context.
- Producer and consumer run incompatible instrumentation or mismatched agent versions.
- Async queue processing intentionally starts a **new root trace + span link** instead of a direct child.
- Both services report to separate resources/workspaces without cross-workspace read permissions.

### Runbook

1. Verify via broker metrics that **Service Bus messages were sent and delivered**, not just the SEND span.
2. Inspect trace context metadata without logging payloads or secrets.
3. Confirm the Java agent/OTel integration supports your Service Bus SDK version.
4. Inspect **consumer spans**, span links, and context extraction.
5. Include a consistent opaque **business event ID** alongside trace IDs for reconciliation.
6. Check `AppRoleName`, time ranges, and workspace permissions.
7. For fan-in batches, use span links instead of forcing all messages under an inaccurate single parent trace.

**Tracing is a correlation tool—not a substitute for broker `messageId`, durable state, or exactly-once contracts.** A validly processed message may belong to a new trace; document those semantics clearly.

## 52. Scenario D: Exception Swallowed Inside a Background Job

**Context:** An order is created and the HTTP API returns 202, yet an `@Async` task sending the invoice email fails. Application Insights shows a successful HTTP request with zero exceptions on the request trace.

### Why

~~~text
HTTP Controller
  |
  +-- Persist order
  +-- Submit @Async email job
  +-- Return 202

@Async job
  |
  +-- SMTP/third-party timeout
  +-- Catch(Exception) then log DEBUG or ignore
~~~

The flaw isn't merely missing exception telemetry: **the business job has no durable state or attempt tracking**. If the JVM restarts, the in-memory task vanishes.

### Fix

- Use a **transactional outbox + durable message queue** whenever email delivery is business-critical.
- Instrument consumer traces and low-cardinality custom metrics (`invoice_email_attempt`, `success`, `failure`).
- Log sanitized exceptions once with event ID and worker version.
- Apply bounded idempotent retries, moving unrecoverable errors to a DLQ and alerting.
- Build dashboards for **pending age, processing rate, and DLQ counts**, never relying solely on HTTP 202.

**Never turn on DEBUG logging of full email bodies just to debug errors**, as doing so leaks customer communications.

## 53. Scenario E: Exceptions Surge After a Canary Release

**Context:** After shifting 10% of traffic to `orders-api` v2, `AppExceptions` logs frequent **`NullPointerException`**s and p95 latency rises while total CPU stays unchanged.

### Steps

1. Pinpoint the deployment timestamp and app version in telemetry.
2. Group exceptions by `Type`, `ProblemId`, and `service.version` if instrumented.
3. Compare **v1 and v2** normalized by traffic share; never compare raw counts across mismatched volumes.
4. Open sample v2 traces to check request names and affected dependencies.
5. Inspect input shapes, DTO/schema changes, and feature flags.
6. Once regression evidence is solid, roll back or disable the feature per runbook.
7. Add regression tests and release-scoped business/exception rate alerts.

### What to Avoid

- Never condemn v2 solely from a higher raw exception count over an arbitrary 5-minute slice.
- Never inspect only one request's stack trace if multiple code paths fail.
- Never delete exception logs or mute log levels to make charts green.
- Never roll back code while ignoring potentially incompatible database/schema migrations.

## 54. Hands-On Exercise: Tracing Spring Boot Transactions in Application Insights

### Context

Build **Orders Lab**, a simple Spring Boot API. The goal is accurately diagnosing a slow dependency and an exception rather than building a generic overview chart.

Architecture:

~~~text
Lab client
   |
   v
orders-api (Spring Boot)
   |
   +-- HTTP client -> payment-stub (Spring Boot/mock HTTP service)
   +-- JDBC -> test database or H2 (per lab)
   +-- Custom span -> order.validate
   |
   v
Azure Monitor / Application Insights
   |
   +-- AppRequests
   +-- AppDependencies
   +-- AppExceptions
   +-- AppTraces
~~~

**Use only dummy customer and order IDs.** Without an Azure subscription or resource creation rights, practice instrumentation and local logging and prepare queries/ADRs—never provision production resources or fabricate measurements as "observed."

### Part A — Environment and Resources

1. Use an organization-approved **sandbox** subscription and resource group.
2. Run **`orders-api`** on App Service or Container Apps (or an authorized lab AKS cluster).
3. Create or reuse an authorized **workspace-based Application Insights resource**.
4. Record the linked Log Analytics workspace, retention, and budget.
5. Set role/service name **`orders-api`** and `environment=lab`.
6. Deploy a mock **`payment-stub`** endpoint; never call a live payment gateway.

### Part B — Dependency Instrumentation

1. Add Spring Web and Actuator if not already present.
2. Attach the **Azure Monitor OpenTelemetry Java agent** or existing OTel pipeline without duplicating exporters.
3. Confirm the app reaches the ingestion endpoint over DNS/TLS.
4. Wire an instrumented HTTP client calling **`payment-stub`**.
5. If using JDBC, populate the test database with dummy data and safe queries.
6. Add a custom **`order.validate`** span with low-cardinality attributes.
7. Emit a sanitized log inside the same trace.

### Part C — Generate Request Scenarios

| Case | Scenario | Expected Telemetry |
|---|---|---|
| **C1** | HTTP request succeeds, mock payment 200 | Request + HTTP dependency succeed |
| **C2** | Payment mock sleeps 2 seconds | HTTP dependency and request durations rise |
| **C3** | Payment mock HTTP 503, backend returns 502 | Failed dependency + failed request |
| **C4** | Payment mock 503 then retry succeeds | Failed attempts, final business success |
| **C5** | Domain validation throws exception | Exception event/stack per instrumentation |
| **C6** | Business validation caught and returns 422 | Expected client error; avoid paging as outage |
| **C7** | Offload work to `@Async` | Verify parent context or diagnostic link |
| **C8** | Send job to test Service Bus queue if available | Producer/consumer context and business event ID |

**Never flood shared services with 503/429 errors.** Use mocks/stubs or sandbox-only application flags.

### Part D — Safe Payment Stub Example

~~~java
package com.example.obslab;

import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Profile("observability-lab")
@RestController
public class PaymentStubController {

    @GetMapping("/lab/payment")
    public ResponseEntity<String> payment(
            @RequestParam(defaultValue = "ok") String mode)
            throws InterruptedException {
        if ("slow".equals(mode)) {
            Thread.sleep(2000);
        }
        if ("unavailable".equals(mode)) {
            return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body("mock dependency unavailable");
        }
        return ResponseEntity.ok("mock payment accepted");
    }
}
~~~

**Enable the `observability-lab` profile only in sandbox**; never expose a public endpoint allowing arbitrary thread sleeps in production. This code uses no payment credentials and processes no financial transactions.

### Part E — Send Dummy Requests

In an authorized Bash / Azure Cloud Shell session:

~~~bash
LAB_API="https://<LAB_ORDERS_API_HOST>"

curl --fail-with-body "$LAB_API/api/orders/lab?mode=ok"
curl --fail-with-body "$LAB_API/api/orders/lab?mode=slow"
curl -i "$LAB_API/api/orders/lab?mode=unavailable"
~~~

**`/api/orders/lab`** must be **implemented by the learner** inside `orders-api` to call `payment-stub` via an HTTP client and map statuses/exceptions; it **does not exist automatically** just from adding `PaymentStubController` above. Secure lab access, keep tokens out of CLI logs, and verify the hostname.

### Part F — Verify Traces and Correlation

1. In Application Insights, locate request C1 and record its **`OperationId`**.
2. Check whether **Application Map** shows `orders-api` and `payment-stub`.
3. Open **End-to-end transaction** for C2: is the dependency duration near 2 seconds?
4. For C3, inspect HTTP dependency status, HTTP request status, and any thrown exception.
5. For C4, count HTTP attempts and confirm the final user-visible outcome.
6. For C5, inspect exception type and span status.
7. For C7, verify trace context across the executor.
8. If running C8, compare Service Bus SEND, consumer PROCESS, and business event ID.

**Do not immediately blame application code for a missing span** if sampling dropped it or the HTTP client library isn't auto-instrumented. Check sampling and agent support first.

### Part G — Run KQL

Target the right workspace/resource, substituting service name and time window:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| project TimeGenerated, Name, OperationId, DurationMs,
          ResultCode, Success
| top 30 by TimeGenerated desc
~~~

~~~kusto
AppDependencies
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| project TimeGenerated, OperationId, Type, Target, Name,
          DurationMs, ResultCode, Success
| top 30 by TimeGenerated desc
~~~

~~~kusto
AppExceptions
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| project TimeGenerated, OperationId, Type, ProblemId
| top 30 by TimeGenerated desc
~~~

If queries return empty, check ingestion, role name, time range, KQL schema, filters, and sampling.

### Part H — Evaluate Monitoring Design

Learners should answer:

- Was C2 slow because of the HTTP dependency or app serialization / thread starvation?
- In C3/C4, how do dependency failures differ from transaction failures?
- Did any request log an exception while still returning valid success?
- Could sampling distort KQL counts or percentiles?
- Did trace context survive across Java executors or Service Bus?
- Which attributes should be removed for PII or high cardinality?
- Does monitoring alert on **end-user impact**?

### Part I — Build an Alert and Runbook

Design a **log/metric alert** for the payment dependency:

~~~text
Alert Name: payment-dependency-high-failure
Scope: orders-api production/lab per exercise
Condition: high dependency failure ratio
Min volume: sufficient calls required before paging
Evaluation: 5–15 minutes per SLO and traffic
Action Group: designated team
Runbook: check AppDependencies -> trace -> remote service
Safety: exclude secrets/customer payloads
~~~

Thresholds above are a **design skeleton**, not rules ready to deploy without checking traffic and sampling. In labs, use only **test action groups** with limited notifications.

### Part J — Evidence and Cleanup

~~~text
Artifacts:
  Commit SHA / JDK / Spring Boot / agent version
  App Service/Container Apps/AKS environment and region
  Application Insights resource + workspace (no secrets)
  Service name / deployment version
  Test cases C1..C8: observed vs expected
  Three KQL result summaries
  One correlated trace ID (opaque)
  One dependency latency explanation
  One exception explanation
  Sampling and PII policy
  Alert/runbook description
  Cleanup/cost checks
~~~

Delete only lab resources you own; never delete shared Application Insights workspaces, alerts, or dashboards. Remove mock fault-injection endpoints, revoke any exposed keys, and check Cost Management since telemetry billing updates with a lag.

## 55. Solution Selection Matrix by Operational Need

| Goal | Primary Signal | Tool / Implementation | Why |
|---|---|---|---|
| API 500s rising | Request status/rate | Azure Monitor metric alert, `AppRequests` | Measures customer impact |
| API slow | Request p95 + dependency spans | Application Insights Performance / KQL | Pinpoints critical path |
| Payment HTTP timeouts | HTTP CLIENT duration/result | `AppDependencies`, trace waterfall | Isolates remote latency |
| Slow DB queries | JDBC dependency + DB metrics | `AppDependencies` + Azure SQL/PostgreSQL Monitor | Combines client & server views |
| HikariCP exhausted | Pool pending/active/timeout | Micrometer metrics + correlated traces | SQL spans may omit pool wait time |
| New Java exception | Exception Type / `ProblemId` | `AppExceptions`, redacted stack | Catches regressions |
| Service Bus queue lag | Consumer lag / oldest age | Broker metrics + worker spans | SEND success != processing success |
| Wrong business transaction | Business event/counter + trace | Custom observation + DB facts | HTTP 200 can mask wrong outcome |
| Broken trace across services | `traceparent` / consumer spans | OTel propagation + App Map | Explains missing correlation |
| Rising telemetry costs | Ingestion GB / sampling | Log Analytics usage + Cost Management | Prevents debug log floods |

**Rule:** start with the **operational question**, then choose the matching telemetry and tool. Never scatter hundreds of custom spans before knowing who will read them and which decisions they inform.

## 56. Production Deployment Checklist

- [ ] Standardized **`service.name`/`AppRoleName`, environment, version, and resource scope** defined.
- [ ] Application Insights is **workspace-based** (or schema verified); queries target the right tables.
- [ ] Java agent, SDK, and OTel bridge versions pinned and tested.
- [ ] No overlapping exporters or Java agents causing duplicate telemetry.
- [ ] HTTP requests capture status, duration, route templates, and trace context.
- [ ] HTTP client dependencies capture target, result code, duration, and timeout/retry details.
- [ ] JDBC/Redis/Storage/Service Bus SDKs verified supported or wrapped in custom spans.
- [ ] Trace context propagates cleanly across HTTP, `@Async`, Reactor, and messaging.
- [ ] Business transaction names and outcomes are recorded without PII.
- [ ] Custom spans cover key domain steps without spamming spans for every line of code.
- [ ] Exception handling separates expected rejections from real faults.
- [ ] Same exception is not logged redundantly at every layer.
- [ ] Raw SQL parameters, customer bodies, `Authorization` headers, and keys are excluded.
- [ ] Correlation IDs appear in structured logs and are propagated/cleared cleanly.
- [ ] Sampling designed and `ItemCount`/percentile limitations understood.
- [ ] Reliable metrics back SLOs rather than relying solely on sampled trace counts.
- [ ] Dashboards track request rate, p95/p99, 5xx, dependency errors, and worker lag.
- [ ] Azure platform metrics and application traces align by timestamp and version.
- [ ] Queries exist to find slow requests and correlate exceptions by `OperationId`.
- [ ] Alerts define thresholds, minimum volume, action groups, and runbooks.
- [ ] No-data monitoring detects silent workloads expected to receive traffic.
- [ ] Application Insights / Log Analytics RBAC follows least privilege.
- [ ] Data residency, retention, and privacy reviews completed.
- [ ] Ingestion volume, retention, collector overhead, and budgets tracked.
- [ ] Startup, CPU, RAM, and latency overhead benchmarked with the agent active.
- [ ] Canary and rollback plans exist for agent/config changes.
- [ ] Tests cover dependency failures, exceptions, async context, and cross-service correlation.
- [ ] Never inject faults in production or feed real customer data into labs.
- [ ] Ownership and postmortem feedback loops continuously improve instrumentation.

## 57. Self-Check Questions

1. How do a dependency, an exception, and an application transaction differ?
2. Is a database transaction the same as a distributed trace?
3. Why does HTTP 200 not prove payment succeeded?
4. How does a trace differ from logs and metrics?
5. How do trace ID and span ID differ?
6. What main fields does W3C `traceparent` contain?
7. Why can't `traceparent` replace a JWT?
8. How can `baggage` create sensitive-data risks?
9. When should you use span links instead of parent–child relationships?
10. How do you auto-instrument Spring Boot on Azure?
11. Why can running two Java agents that both instrument JDBC cause problems?
12. What roles do Application Insights and a Log Analytics workspace play?
13. How do Azure resource metrics differ from Java application telemetry?
14. Which attributes should an HTTP dependency record?
15. Why omit user IDs from dependency names and metric labels?
16. Why can a request take several seconds even when SQL spans are short?
17. Does HikariCP connection-pool wait need its own metric?
18. If a call retries three times, how many dependency attempts can be observed?
19. What valid reasons explain high dependency failures alongside HTTP 200 responses?
20. When `@RestControllerAdvice` handles an exception, is the agent guaranteed to emit an exception event?
21. Is a `422` validation exception a 5xx application failure?
22. When should you call `span.recordException` and `setStatus(ERROR)`?
23. Does Micrometer Observation export data to Azure by itself?
24. How can context propagation break across `@Async` or `CompletableFuture`?
25. What are common errors when tracing across Service Bus?
26. Why does `SEND` success not equal consumer transaction success?
27. What are `AppRequests`, `AppDependencies`, `AppExceptions`, and `AppTraces` used for?
28. How does the `AppRequests` schema differ from the legacy `requests` table?
29. How do you use KQL to find the 20 slowest requests for `orders-api`?
30. How do you use `OperationId` to link dependencies and exceptions?
31. Why can summing durations across multiple child spans be wrong?
32. When is `ItemCount` used in Application Insights?
33. What inaccuracies can sampled traces introduce into p95 and error rates?
34. When should you use metrics/SLIs instead of sampled KQL request counts?
35. Does an Azure Monitor alert need a minimum volume threshold?
36. What should Action Group notifications include—and exclude—to avoid leaking PII?
37. How do data-plane RBAC and Log Analytics read permissions relate?
38. When you increase log verbosity, what happens to ingestion costs?
39. Which steps verify whether the agent introduces overhead?
40. When Java requests slow down, why investigate the DB connection pool before scaling Pods?
41. When a canary release increases exceptions, how should you compare across versions and traffic?
42. How do you distinguish a shared dependency outage from a local programming bug?
43. Why can message redelivery still happen even with complete distributed tracing?
44. Which timestamps and evidence should a solid incident runbook record?
45. What does the lab prove when `AppDependencies` accurately logs a payment HTTP 503?

## 58. References

- [Azure Monitor overview](https://learn.microsoft.com/azure/azure-monitor/overview) — metrics, logs, alerts, and observability.
- [Application Insights overview](https://learn.microsoft.com/azure/azure-monitor/app/app-insights-overview) — application telemetry, performance, and transaction analysis.
- [Azure Monitor OpenTelemetry for Java](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-enable?tabs=java) — OpenTelemetry instrumentation and language configuration.
- [Application Insights distributed tracing](https://learn.microsoft.com/azure/azure-monitor/app/distributed-tracing-telemetry-correlation) — correlation and distributed transactions.
- [Application Insights Application Map](https://learn.microsoft.com/azure/azure-monitor/app/app-map) — service/dependency graph.
- [Application Insights transaction diagnostics](https://learn.microsoft.com/azure/azure-monitor/app/transaction-diagnostics) — end-to-end transaction view.
- [Application Insights telemetry data model](https://learn.microsoft.com/azure/azure-monitor/app/data-model-complete) — requests, dependencies, traces, exceptions.
- [AppRequests table schema](https://learn.microsoft.com/azure/azure-monitor/reference/tables/apprequests) — workspace-based request data.
- [AppDependencies table schema](https://learn.microsoft.com/azure/azure-monitor/reference/tables/appdependencies) — outgoing dependencies.
- [AppExceptions table schema](https://learn.microsoft.com/azure/azure-monitor/reference/tables/appexceptions) — exceptions.
- [Azure Monitor KQL overview](https://learn.microsoft.com/azure/azure-monitor/logs/log-query-overview) — query language and Log Analytics.
- [Azure Monitor alerts overview](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-overview) — alert rules and action groups.
- [Azure Monitor cost/usage](https://learn.microsoft.com/azure/azure-monitor/cost-usage) — ingestion, retention, and cost controls.
- [Azure Monitor data collection privacy](https://learn.microsoft.com/azure/azure-monitor/logs/data-security) — access control and data security.
- [OpenTelemetry concepts](https://opentelemetry.io/docs/concepts/) — spans, traces, metrics, and logs.
- [OpenTelemetry Java](https://opentelemetry.io/docs/languages/java/) — instrumentation API and Java agent.
- [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/) — standard HTTP/DB/messaging attribute names.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — `traceparent`/`tracestate`.
- [Spring Boot Actuator and observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — Micrometer/Observation/Tracing.
- [Spring Boot metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — JVM/HTTP/database metrics.
- [Azure Service Bus documentation](https://learn.microsoft.com/azure/service-bus-messaging/) — retries, settlement, and messaging.
- [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/) — reliability, operational excellence, performance, and cost.

**Conclusion:** Tracking application dependencies, exceptions, and transactions on Azure requires more than turning on basic logging. Instrument Spring Boot with **OpenTelemetry / Application Insights**, propagate **trace context** across HTTP and messaging, distinguish **request success from dependency failures and business outcomes**, and use **KQL and transaction waterfalls** to pinpoint critical paths and high-impact errors. Pair traces with **JVM, database, and Azure platform metrics**, alert on SLOs, and govern sampling, costs, retention, and access permissions. A truly observable system lets operations answer **which requests are impacted, which dependency causes latency, which exception occurred, where the business transaction ended up, and which evidence supports the remediation decision**.
