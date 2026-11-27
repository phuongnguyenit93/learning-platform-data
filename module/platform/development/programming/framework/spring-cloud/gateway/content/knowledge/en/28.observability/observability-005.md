# Distributed Tracing and Propagating Trace Context Downstream

## 1. Why Does an API Gateway Need Distributed Tracing?

In a microservices architecture, **Spring Cloud Gateway** receives incoming requests, matches routes using predicates, runs filter chains, transforms paths and headers, and forwards calls to backends via fixed URLs or service discovery/load balancing. Along that same path, the Gateway may also perform authentication, rate limiting, circuit breaking, retries, TLS, and observability recording.

Consider this request flow:

~~~text
GET /api/orders/42
  -> API Gateway
  -> order-service
  -> inventory-service
  -> database
~~~

When a client receives `504 Gateway Timeout`, a single Gateway access log line usually cannot answer:

- **Which route** did the Gateway select, and which instance did it call?
- Did the failure happen before connecting upstream, or after the backend had already begun processing?
- How long did `order-service` wait on `inventory-service`?
- How many extra calls did retries generate, and how much latency did they add?
- Do logs from the Gateway and both services truly belong to the **same logical request**?

**Distributed tracing** solves the problem of correlating work spread across multiple processes, threads, and services. Each unit of work is represented as a **span**, and the entire journey belongs to a single **trace** sharing a common identifier.

The lesson **“Distributed Tracing and Propagating Trace Context Downstream”** belongs to the **Observability** chapter of the **SPRING_CLOUD_GATEWAY** module. The goal is to understand **HTTP context propagation**, configure Micrometer Tracing/OpenTelemetry, verify that the Gateway and backends join the same trace, and keep tracing secure and cost-effective in production.

After this lesson, you will be able to:

1. Distinguish `traceId`, `spanId`, `parentSpanId`, sampling, baggage, and request IDs.
2. Read W3C `traceparent`, `tracestate`, and `baggage` headers.
3. Configure trace export for Gateway Server WebFlux and Spring Boot backends, distinguishing **Boot 3.5 vs. Boot 4.x**.
4. Verify trace context is **extracted from inbound requests** and **injected into outbound requests** sent to services.
5. Understand why Reactor Context and Micrometer Context Propagation matter when reactive pipelines switch schedulers.
6. Test via mock upstreams, trace backends, and logs without relying solely on HTTP 200.
7. Diagnose broken traces caused by custom HTTP clients, sampling, header-stripping proxies, retries, or missing instrumentation.
8. Mitigate risks around sensitive data, forged headers, metric cardinality, and span storage costs.

> **Scope:** Focus is on **Spring Cloud Gateway Server WebFlux** on modern Spring Boot. Gateway Server Web MVC and Proxy Exchange MVC have different threading and filter APIs; W3C propagation principles still apply, but WebFlux snippets cannot be copied verbatim into Servlet stacks. Version-dependent configuration is explicitly noted; verify effective configuration on your deployed release train.

## 2. A Trace Is a Tree of Work, Not Just a Request ID

### 2.1. Traces, Spans, and Parent-Child Relationships

Core concepts:

| Term | Meaning | Example |
| --- | --- | --- |
| **Trace** | Entire execution flow of one logical request across systems | Order lookup request |
| **Trace ID** | Shared identifier linking spans in the same trace | 32 hex chars (128-bit in W3C) |
| **Span** | A unit of work with start, end, and attributes | Gateway receives HTTP; Gateway calls `order-service` |
| **Span ID** | Unique identifier of one span | 16 hex chars (64-bit in W3C) |
| **Parent span ID** | Links a child span to the work that invoked it | Gateway outbound span is parent of service inbound span |
| **Span kind** | Role: SERVER, CLIENT, INTERNAL, PRODUCER, CONSUMER | HTTP server/client |
| **Attributes** | Metadata describing a span | HTTP method, route ID, status |
| **Events** | Timestamped milestones within a span | Timeout, recorded exception |
| **Status** | Tracing-semantic outcome | OK/ERROR/UNSET depending on implementation |
| **Sampling** | Decision on whether to record/export trace data | 10% or parent-based policy |

A fully instrumented path **typically** looks like:

~~~mermaid
flowchart TD
    R["Trace ID = T"] --> G1["Gateway SERVER span<br/>GET /api/orders/{id}"]
    G1 --> G2["Gateway CLIENT span<br/>HTTP to ORDER-SERVICE"]
    G2 --> O1["order-service SERVER span"]
    O1 --> O2["order-service CLIENT span<br/>calls inventory"]
    O2 --> I1["inventory-service SERVER span"]
    O1 --> DB["DB span if driver is instrumented"]
~~~

Spans in this diagram share **one trace ID** while having **different span IDs**. Exact span counts and nesting depend on instrumented libraries: a Gateway version may create a Gateway outbound observation, a Netty client span, or additional internal spans. Never hardcode an integration test to require exactly five spans regardless of stack.

### 2.2. A Trace ID Is Not a User ID or Business Key

`traceId` exists primarily for **observability correlation**. It does not prove authentication, does not replace `orderId`, is not an idempotency key, and is not a credential.

One user can send many requests belonging to **different traces**. One trace can also cross multiple services and contain many spans. Logging systems may also use `X-Request-Id` or an operation ID for business reconciliation, but **must never treat them as a trace ID**.

### 2.3. How Distributed Traces Differ from Metrics and Logs

| Signal | Best-Fit Question | Example |
| --- | --- | --- |
| **Metrics** | How many requests failed; what is p95 latency? | `http.server.requests`, Gateway request timer |
| **Logs** | What specific event occurred? | `traceId`, `spanId`, route ID, error code |
| **Traces** | Which components did a request traverse, and where was it slow? | Span chain Gateway → order → inventory |

These three signals **complement** rather than replace each other. Tracing excels at debugging individual requests, yet should not be your sole source for computing total-request SLOs/SLIs: due to **sampling**, only a fraction of traffic may appear in the trace backend.

## 3. Propagating Trace Context Over HTTP with W3C Trace Context

A Gateway span cannot automatically become the parent of a backend span unless both processes **exchange context**. Over HTTP, the standard mechanism is **W3C Trace Context**.

### 3.1. Structure of the `traceparent` Header

Valid example:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

General format:

~~~text
traceparent: version-trace-id-parent-id-trace-flags
             00      32 hex   16 hex    2 hex
~~~

| Field | Meaning | In Example |
| --- | --- | --- |
| `version` | `traceparent` format version | `00` |
| `trace-id` | Identifier of the entire trace (128-bit) | `4bf92f3577b34da6a3ce929d0e0e4736` |
| `parent-id` | Span ID of the header sender | `00f067aa0ba902b7` |
| `trace-flags` | Bit flags; lowest bit indicates sampled hint | `01` |

For version `00`, **trace ID and parent ID must not be all zeros** and must match the exact standard length/format. `01` sets the sampled bit; `00` clears it. This is **not a guarantee forcing every downstream tracer to export**: actual export still depends on the sampler, tracing SDK, and backend policy.

### 3.2. What Changes Across Gateway and Backend?

Suppose a client request already carries `traceparent`. An instrumented system processes it like this:

~~~text
Client header:
  trace-id = T
  parent-id = C

Gateway receives request:
  SERVER span id = G1
  trace-id = T
  parent = C

Gateway sends request to order-service:
  CLIENT span id = G2
  trace-id = T
  header parent-id is typically G2

order-service receives request:
  SERVER span id = O1
  trace-id = T
  parent = G2
~~~

**The continuity you verify is the trace ID and valid span parenting**, not that Gateway and `order-service` share the same `spanId`. Asserting “every service has the same spanId” confuses spans with traces.

The outbound `traceparent` carries a different parent ID from the inbound header because the Gateway created a new span. Never **manually copy the inbound `traceparent` verbatim to outbound** when tracing is already instrumented: doing so breaks accurate parent-child relationships.

### 3.3. `tracestate`

A request can also include:

~~~http
tracestate: vendor1=opaque-value
~~~

`tracestate` lets tracing vendors pass supplementary state per the W3C contract. It is not a dumping ground for arbitrary JSON, bearer tokens, or customer identifiers.

Do not manually parse or overwrite `tracestate` to “force” sampling or priority unless implementing a spec-compliant propagator. Let the tracer/propagator manage extraction, injection, and header limits.

### 3.4. Baggage: Context Traveling with a Trace, Not Trace Identity

W3C Baggage is a separate mechanism:

~~~http
baggage: locale=vi,feature-flag=beta
~~~

Baggage entries can traverse multiple hops if propagators are enabled and network policies allow them. However:

- Baggage is **not** part of the trace identity.
- Baggage does **not** automatically appear as span attributes or log MDC fields.
- Baggage can travel farther than expected, even into partner services.
- Client-supplied baggage is **untrusted** for authentication, tenant selection, or rate-limit decisions.
- Never transmit passwords, access tokens, emails, phone numbers, card numbers, or sensitive user IDs.
- Cap key counts and value lengths, and enforce propagation rules at trust boundaries.

`tracestate` and `baggage` are **not synonymous**: one carries tracing-system state, while the other carries application/library-shared key-value context.

## 4. Context Propagation Flow from Gateway to Microservices

### 4.1. A Typical HTTP Chain

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Spring Cloud Gateway
    participant O as order-service
    participant I as inventory-service
    participant T as OTel Collector / Trace Backend
    C->>G: GET /api/orders/42 + traceparent(T,C)
    G->>G: Extract context, create SERVER span G1
    G->>O: GET /orders/42 + traceparent(T,G2)
    O->>O: Extract context, create SERVER span O1
    O->>I: HTTP + traceparent(T,O2)
    I->>I: Extract context, create SERVER span I1
    I-->>O: Response
    O-->>G: Response
    G-->>C: Response
    G-->>T: Export sampled spans
    O-->>T: Export sampled spans
    I-->>T: Export sampled spans
~~~

The diagram omits internal sub-spans. Exporting is usually **asynchronous and batched**; a client receiving HTTP 200 does not mean the Collector has already ingested the full trace at that instant.

### 4.2. Instrumentation on Both Ends Is Required

For a connected trace:

1. **Gateway inbound server** must extract HTTP trace context or start a new root context.
2. **Gateway outbound HTTP client** must inject the active context into upstream requests.
3. **Backend inbound server** must extract headers and start a span in the same trace.
4. Further backend HTTP calls also require **instrumented clients**.
5. Traces must be sampled and exported to a collector/backend queried by the right service/trace ID.

Having `spring-boot-starter-actuator` without a tracer/exporter can produce metrics/observations while **showing zero distributed traces in the UI**. Conversely, forwarding `traceparent` successfully does not by itself prove the backend exported its span.

### 4.3. Gateway Routes Are Not Trace Configuration

A WebFlux route like:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
~~~

only specifies receiving `/api/orders/**` and forwarding to `http://localhost:8081/orders/**`. Tracing is provided by **Micrometer Observation/Tracing and HTTP server/client instrumentation**, not automatically turned on simply because `Path` or `StripPrefix` exists.

On common **Gateway Server WebFlux 4.x** releases, the route property is `spring.cloud.gateway.routes`. On **Server WebFlux 5.x**, docs use `spring.cloud.gateway.server.webflux.routes`. Use only the single namespace matching your release—never put both into one app.

## 5. How Do Micrometer Observation, Micrometer Tracing, and OpenTelemetry Differ?

| Component | Role | Key Concepts |
| --- | --- | --- |
| **Micrometer Observation** | Models an operation that can emit metrics and/or traces | `ObservationRegistry`, conventions, key-values |
| **Micrometer Tracing** | Java facade for spans, traces, and baggage | `Tracer`, `Span`, `Baggage` |
| **OpenTelemetry SDK** | Implements tracing, propagators, and exporters | Context, span processors, OTLP |
| **OTLP** | Telemetry wire protocol from apps to Collector/backend | Not a trace ID format |
| **OpenTelemetry Collector** | Receives, processes, and forwards spans | Filters, batches, exports to Jaeger/Tempo/vendors |
| **Jaeger, Tempo, Zipkin** | Trace storage and search backends | Query/retention behavior varies by product |
| **W3C Trace Context** | HTTP header propagation format | `traceparent`, `tracestate` |
| **W3C Baggage** | HTTP key-value context propagation format | `baggage` |

When an Observation is wired with a tracing handler, it can produce a span. However, **not every Observation always produces an exported span**: the sampler, handler/tracer implementation, context, and exporter determine the final outcome.

Gateway docs also define an outbound **Gateway HTTP Client Observation**, typically named `http.client.requests`. The project's observability metadata table lists attributes such as HTTP method, status, route ID, and route URI. That is how Gateway outbound requests appear in traces; do not assume every single filter in the route chain creates its own span.

## 6. Reference Config: Gateway WebFlux with Spring Boot 3.5 and OTLP

This is the **compatible Spring Boot 3.5 + Spring Cloud Gateway Server WebFlux 4.x** variant, using the **Micrometer Tracing OpenTelemetry bridge** and **OTLP HTTP exporter**.

### 6.1. Maven Dependencies

Assuming `pom.xml` already uses matching Spring Boot parent/BOM and Spring Cloud BOM versions:

~~~xml
<!-- Gateway Server WebFlux starter for the 4.x release train -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway</artifactId>
</dependency>

<!-- Actuator and Micrometer Observation -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<!-- Observation/Tracing bridge to OpenTelemetry -->
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>

<!-- HTTP/gRPC OTLP exporter supported by OTel SDK -->
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
~~~

**Do not pin independent library versions** in examples when your project uses a BOM. If your Gateway version uses a renamed starter, choose the exact artifact documented for that release; the snippet above is **one 4.x-line configuration**, not a timeless template for all versions.

Never mix Brave, the OpenTelemetry bridge, and an arbitrary Java agent simultaneously hoping the system will pick one automatically; **choose one instrumentation/export strategy** and verify spans are not duplicated.

### 6.2. Gateway `application.yml` in a Lab

~~~yaml
spring:
  application:
    name: edge-gateway
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: http://localhost:8081
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
      observability:
        enabled: true

server:
  port: 8080

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Key points:

- `spring.application.name` identifies the service in telemetry resources and logs.
- `spring.cloud.gateway.observability.enabled` belongs to the **Gateway WebFlux 4.x namespace**, not Spring Boot's tracing properties. In matching releases, observability is often active when required dependencies are present; setting it explicitly in the lab highlights how to verify it.
- `management.tracing.sampling.probability: 1.0` fits **short-term lab/staging** visibility. **Production should not default to 100%** without a capacity and cost assessment.
- `management.otlp.tracing.endpoint` in **Boot 3.5** sets the **OTLP HTTP traces** endpoint; here a Collector/receiver is assumed listening for `POST /v1/traces` on port 4318.
- This config **does not start a Collector**. Without a running Collector or backend, the Gateway still serves requests while the exporter logs connection failures and no traces appear.
- `exposure: health,info` intentionally **avoids exposing sensitive management endpoints**; inspect traces in a dedicated backend, not a default `/actuator/traces`.

### 6.3. Corresponding Backend `order-service` Config

On a **Spring Boot 3.5** `order-service` (which may use Spring MVC), include compatible Actuator + Micrometer bridge + OTLP exporter dependencies—mirroring the three tracing dependencies above—plus the service's web starter.

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8081

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Do not configure only the Gateway and expect the backend to create a `SERVER span` automatically. Without inbound instrumentation/tracer and export on the service, the Gateway sends `traceparent` yet the backend **emits no span to join the trace**.

**Never reuse the same service name**: Gateway and `order-service` **must have distinct names** so trace UIs render hops across processes accurately.

## 7. Spring Boot 4.x / Gateway Server WebFlux 5.x Variant

Spring Boot **4.x** changes tracing packaging. Current docs introduce the dedicated starter **`spring-boot-starter-opentelemetry`** and OTLP properties under `management.opentelemetry.*`.

### 7.1. Core Dependencies

~~~xml
<!-- Gateway WebFlux app for the newer Spring Cloud release train -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
</dependency>

<!-- OpenTelemetry tracing integration and exporter in Boot 4.x -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-opentelemetry</artifactId>
</dependency>
~~~

Different release combinations may pull in or manage Actuator differently; check your actual dependency tree/auto-configuration and add `spring-boot-starter-actuator` if your project needs actuator endpoints or docs specify it. Do not copy `spring-boot-starter-opentelemetry` into **Boot 3.5** unverified, as it is a Boot 4.x dependency.

### 7.2. `application.yml` for Routes and OTLP

~~~yaml
spring:
  application:
    name: edge-gateway
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
          observability:
            enabled: true

server:
  port: 8080

management:
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    otlp:
      endpoint: http://localhost:4318
~~~

This is the **Boot 4.x variant**, not a line-for-line replacement inside Boot 3.5. Boot 4.x docs note that `management.opentelemetry.otlp.*` can specify a shared base endpoint; when exporting **traces via OTLP HTTP** using that base endpoint, the exporter appends `/v1/traces` automatically.

If you want a trace-specific endpoint, check `management.opentelemetry.tracing.export.otlp.endpoint` for your release; do not confuse Boot 3.5's `management.otlp.tracing.endpoint` with the newer properties.

### 7.3. Essential Comparison Table

| Concern | Boot 3.5 / Gateway 4.x | Boot 4.x / Gateway 5.x |
| --- | --- | --- |
| Gateway route namespace | `spring.cloud.gateway.routes` | `spring.cloud.gateway.server.webflux.routes` |
| Gateway observability setting | `spring.cloud.gateway.observability.enabled` | `spring.cloud.gateway.server.webflux.observability.enabled` |
| Sample OpenTelemetry dependencies | Actuator + `micrometer-tracing-bridge-otel` + `opentelemetry-exporter-otlp` | `spring-boot-starter-opentelemetry` per Boot 4 docs |
| Sample OTLP HTTP traces setting | `management.otlp.tracing.endpoint` | `management.opentelemetry.otlp.endpoint` or trace-specific property |
| Sampling | `management.tracing.sampling.probability` | `management.tracing.sampling.probability` |
| Context propagation | W3C propagator/instrumented clients | W3C propagator/instrumented clients |

These are **illustrative combinations**, not a claim that Gateway 4.x only runs on Boot 3.5 or that every minor release shares identical properties. When traces don't show up, start by **checking dependencies and namespaces for your exact version** instead of guessing network faults.

## 8. Demo Backend: Verifying the Trace ID Is Received Properly

A **Spring MVC** backend provides a straightforward way to inspect `Tracer.currentSpan()` on an instrumented request thread. The code below is **strictly for mock/staging**—never expose a public endpoint leaking trace metadata in production.

~~~java
package example.orders;

import java.util.LinkedHashMap;
import java.util.Map;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersTraceDebugController {
    private final Tracer tracer;

    public OrdersTraceDebugController(Tracer tracer) {
        this.tracer = tracer;
    }

    @GetMapping("/orders/{id}")
    public Map<String, String> getOrder(
            @PathVariable("id") String id,
            @RequestHeader HttpHeaders headers) {

        Span current = tracer.currentSpan();
        Map<String, String> result = new LinkedHashMap<>();

        result.put("id", id);
        result.put("traceId",
                current != null ? current.context().traceId() : "none");
        result.put("spanId",
                current != null ? current.context().spanId() : "none");
        result.put("traceparentHeader",
                headers.getFirst("traceparent") != null ? "present" : "absent");
        return result;
    }
}
~~~

**How to read the output:**

- `traceId` in the response is the **service's active span ID's trace ID**; if an inbound parent exists, it should belong to that same trace.
- The service's `spanId` is normally **different** from the Gateway's span ID.
- `traceparentHeader: present` only proves the service received the header; to verify parent-child linkage, inspect the **trace tree in the tracing backend**.
- `currentSpan() == null` can happen if tracing is disabled, the request sits outside an observation scope, or context propagation broke; the code checks for null instead of throwing.
- In a **reactive WebFlux** backend, the current span may rely on Reactor Context/scopes. Never blindly copy `Tracer.currentSpan()` calls across arbitrary async callbacks; use framework-supported propagation APIs/hooks.

**Never use a client-supplied header to grant access** simply because it carries a valid trace ID. Remove or lock down debug fields like these in production, especially if they reveal internal topology.

## 9. Testing HTTP Propagation with curl

### 9.1. Without Sending `traceparent`: Gateway Starts a New Trace

Assume Gateway on port 8080, `order-service` on 8081, and Collector on 4318.

~~~bash
curl -i "http://localhost:8080/api/orders/42"
~~~

A configured tracing pipeline normally creates a new root trace when inbound requests carry no valid context. The demo backend returns a `traceId` and `traceparentHeader: present` if the Gateway injected the header.

Seeing `HTTP 200` alone **does not prove tracing works**. Check the mock backend response, outbound headers seen by the backend, and the trace UI.

### 9.2. Sending a Controlled W3C `traceparent`

~~~bash
curl -i \
  -H "traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" \
  "http://localhost:8080/api/orders/42"
~~~

With a W3C propagator accepting inbound context and sampling enabled, the backend trace is **expected** to carry `traceId = 4bf92f3577b34da6a3ce929d0e0e4736`.

**Do not assert that outbound `traceparent` equals the inbound string verbatim.** The span ID inside the outbound header should reflect the proper parent span for the backend; verify parent-child relationships in the trace UI.

Special cases:

- A **trust-boundary** system may intentionally start a fresh trace rather than trusting external client context.
- A malformed header may be ignored, triggering a new trace.
- A client sending sampled bit `00` may prevent traces from showing up in the backend under parent-based sampling.
- A reverse proxy/ingress may alter or strip headers.
- Custom middleware/filters may accidentally overwrite context before Gateway routing.

### 9.3. Testing `tracestate` and `baggage`

~~~bash
curl -i \
  -H "traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" \
  -H "tracestate: testvendor=demo" \
  -H "baggage: locale=vi" \
  "http://localhost:8080/api/orders/42"
~~~

Use **demo values only** in an isolated environment. Whether `baggage` is forwarded depends on the propagator, SDK, framework, and policy. Do not assert that `tracestate` or `baggage` survives byte-for-byte: propagators may normalize formatting, drop invalid entries, or update vendor state.

Never paste tokens, session cookies, emails/phone numbers, or sensitive identities into test commands that get saved in shell history.

### 9.4. Even Without a Collector, You Can Test Headers

Use a mock HTTP upstream (WireMock, MockWebServer, or a mock MVC controller) to capture:

~~~text
Incoming path to mock:
  GET /orders/42

Incoming headers:
  traceparent: 00-<trace-id>-<parent-span-id>-01
~~~

Then assert:

1. Gateway selected route `orders-api`.
2. Backend received a **validly formatted** `traceparent`.
3. Given a valid inbound W3C context, the trace ID is preserved from inbound to outbound per policy.
4. Two independent requests without inbound context generally get two distinct trace IDs.
5. Gateway does not dump raw sensitive headers into logs during testing.

Header tests are **one layer proving propagation**; to verify actual spans and latency trees, check the tracer, exporter, and backend.

## 10. Never Copy `traceparent` Manually with `AddRequestHeader` or `SetRequestHeader`

An easy-to-make mistake:

~~~yaml
# ANTI-PATTERN: illustrates a wrong approach, never put in production.
filters:
  - SetRequestHeader=traceparent, 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Consequences:

- All requests share the exact same hardcoded fake trace ID and span ID.
- Parent-child relationships break; the trace UI merges unrelated requests into one tree.
- Sampling flags no longer reflect tracer policy.
- Services may reject the header as malformed or emit orphaned spans.
- Security and incident investigations get misled by false correlation.

Likewise, simply **copying the raw inbound `traceparent`** onto outbound requests skips the Gateway's new client span. The tracer/HTTP instrumentation must own **extract → create child span → inject current context**.

### 10.1. `X-Request-Id` Is Something Else

You may see:

~~~http
X-Request-Id: req-7c6a
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

`X-Request-Id` is application-defined (usually a standalone correlation identifier), whereas `traceparent` follows W3C and is managed by the tracing library. Never use `X-Request-Id` as a `spanId` or trust an unauthenticated HTTP header value as a principal.

When using `X-Request-Id` for log correlation, bound its length/format, sanitize untrusted sources, and never treat it as authorization.

## 11. Custom HTTP Clients: The Most Common Trace Breakpoint

### 11.1. Default HTTP Proxy vs. Hand-Rolled Code Calls Are Separate Paths

In Gateway, `NettyRoutingFilter` and the HTTP routing infrastructure use an internal HTTP client for upstream forwarding. Gateway WebFlux includes built-in observability for HTTP client routing; verify it is enabled and creates/injects spans as expected.

If you write a custom `GlobalFilter` or service bean that calls **an auxiliary HTTP endpoint**, that call uses a **separate outbound HTTP client**. Never assume that because Gateway proxying is traced, any `new WebClient` or raw Reactor Netty client propagates context automatically.

### 11.2. Use Spring Boot Auto-Configured Builders

Spring Boot tracing docs recommend injecting **auto-configured** `RestClient.Builder` or `WebClient.Builder` instances so observation/trace propagation is wired automatically.

Example bean creating a `WebClient` for an auxiliary lookup:

~~~java
package example.gateway.trace;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class InventoryStatusClient {
    private final WebClient client;

    public InventoryStatusClient(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("http://localhost:8082")
                .build();
    }

    public Mono<String> getAvailability(String sku) {
        return client.get()
                .uri(uriBuilder -> uriBuilder
                        .path("/inventory/{sku}")
                        .build(sku))
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

**Key point:** inject Boot's builder instead of calling `WebClient.create(...)` or `WebClient.builder()` directly and bypassing `ObservationRegistry`. On a compatible Boot version with an active context, outbound calls made through the configured builder inject tracing headers.

However, this code **does not replace Gateway's `NettyRoutingFilter`**. It illustrates a **custom outbound call**; if invoked from a filter, compose the `Mono` inside the request chain, handle timeouts and errors, and avoid unnecessary side effects.

Avoid:

~~~java
// ANTI-PATTERN: detached subscribe can lose lifecycle, context, and error propagation.
client.get()
      .uri("/inventory/sku-42")
      .retrieve()
      .bodyToMono(String.class)
      .subscribe();
~~~

A detached subscription can drop trace context, cancellation, backpressure, and error handling. In reactive apps, always **return/compose publishers** using `flatMap`, `then`, `defer`, or appropriate operators.

### 11.3. Using Raw `HttpClient` or Custom SDKs

Custom HTTP libraries, gRPC, OkHttp, Kafka producers, or vendor SDKs **do not automatically get Micrometer Tracing instrumentation just because the starter is on the classpath**. You need:

- Matching integration or agent instrumentation.
- Compatible propagators and protocol-specific injection.
- Preserved context scope across SDK calls.
- Verification on your exact library version and client setup.
- Avoiding duplicate header injection when a library already handles it.

**Do not stop after seeing matching trace IDs in a demo response**; inspect HTTP client spans and parent-child links in the trace backend to catch stale or wrongly reused contexts.

## 12. Reactor Context, Thread Switching, and MDC

### 12.1. Why `ThreadLocal` Is a Trap in Gateway WebFlux

Server WebFlux runs on a non-blocking Reactor pipeline. A single request can hop across threads via `publishOn`, `subscribeOn`, network callbacks, or third-party libraries. `ThreadLocal` binds to a physical thread, whereas trace context belongs to a **logical execution scope/subscription**.

Therefore, code like:

~~~java
MDC.put("traceId", someId);
return chain.filter(exchange);
~~~

**does not guarantee** downstream pipeline logs keep that `traceId`. Beyond losing context on thread hops, uncleaned `MDC.put` calls can leak values across unrelated requests sharing a worker thread.

### 12.2. Reactor Context Is Not an HTTP Header

`Reactor Context` is a per-subscriber key-value store. You can write:

~~~java
Mono<String> readContext = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("example.routeLabel", "unknown")));

Mono<String> result = readContext
        .contextWrite(ctx -> ctx.put("example.routeLabel", "orders-api"));
~~~

However, `example.routeLabel` is **not a W3C `traceparent`**, and `contextWrite` **never sends headers over the wire**. Tracing libraries rely on dedicated context-propagation integrations so spans flow across reactive operators and get injected when HTTP clients dispatch requests.

**Never read a `traceId` key manually from Reactor Context and build a `traceparent` string by hand.** Always use the standard tracer/propagator. For route metadata in logs, use exchange attributes, Observation conventions, or explicit method arguments.

### 12.3. Micrometer Context Propagation and Reactor

Micrometer Context Propagation bridges **ThreadLocal-based scopes** (such as tracing and MDC when registered) with Reactor Context. Modern Reactor versions include automatic context propagation support; Spring Boot/framework manages hooks and registries per version.

Avoid doing any of the following without understanding your stack:

- Calling `Hooks.enableAutomaticContextPropagation()` repeatedly inside custom filters to “fix traces.”
- Calling `tracer.currentSpan()` from a callback on another thread assuming it is always non-null.
- Calling detached `subscribe()` inside a `GlobalFilter` expecting automatic Context inheritance.
- Calling `block()` on a Reactor Netty event loop to wait for spans or collectors.
- Starting new spans on every retry without closing/scoping them properly.
- Storing a `Span` or `ServerWebExchange` in a singleton/static field shared across requests.

If log correlation disappears after a scheduler hop, inspect **Boot's context propagation integration** and tracing bridge instead of reaching for manual `ThreadLocal` hacks.

### 12.4. Defensive Null Checks When Reading the Current Span for Debugging

A hook executing **inside an instrumented request scope** can do:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;

// Illustrative snippet inside a callback with a valid tracing scope.
Span current = tracer.currentSpan();
if (current != null) {
    String traceId = current.context().traceId();
    String spanId = current.context().spanId();
    // Log only essential, redacted metadata.
}
~~~

`currentSpan()` returning `null` **does not prove the request is uninstrumented**; code may simply be executing **outside the scope** or without an active context bridge at that point.

In Gateway WebFlux, prefer framework-instrumented Observations and tracing over writing manual span/header code in every filter.

## 13. How Should Baggage and Log Correlation Be Used?

### 13.1. Logs with `traceId`/`spanId`, Without Dumping Every Header

Example sanitized log line:

~~~text
2026-11-24T05:00:00Z INFO  service=edge-gateway
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=66b4a0e9139d401a routeId=orders-api
status=200 durationMs=87
~~~

Within the same trace, `order-service` might log:

~~~text
2026-11-24T05:00:00Z INFO  service=order-service
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=8f7c9b1a02f4d125 orderId=ord-42
status=200
~~~

This is an **illustrative log format**, not captured output. Identical trace IDs correlate logs across a request; distinct span IDs identify each processing segment.

In Spring Boot, correlation IDs are typically populated through Micrometer Tracing/MDC integration when the scope is active. If customizing log patterns, verify your version's MDC key names and avoid patterns that strip correlation data.

### 13.2. Baggage Does Not Become a Log Field Automatically

Example **Boot 3.5** configuration for a reviewed baggage field:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - locale
      correlation:
        fields:
          - locale
~~~

This is an example only. **Each property has distinct semantics**:

- `remote-fields` controls propagating listed baggage fields where supported by the tracer; with W3C, baggage propagation may already run depending on the implementation.
- `correlation.fields` exposes selected fields in the logging context while a tracing scope is active.
- Not all tracers/backends emit baggage headers identically across formats like B3 and W3C.
- `locale` here can only be a **validated hint**, never a credential or security role.

**Never use baggage received from the internet to authorize tenants or select rate-limit keys.** Even if a value sits in Reactor Context or MDC, its origin may still be an untrusted client header.

### 13.3. `tracestate`, `baggage`, and Custom Span Tags Have Different Scopes

| Mechanism | Scope | Can Appear in HTTP Headers? | Automatically Becomes a Trace Tag? |
| --- | --- | --- | --- |
| `traceparent` | Trace identity/parent/sampling | Yes | Trace IDs/span links form the trace structure |
| `tracestate` | Vendor trace propagation state | Yes | Not arbitrary application tags |
| `baggage` | Context fields to propagate | Yes | **Not by default** |
| Span attribute | Metadata on **one span** | Not by default | Yes, if span is exported and not filtered by policy |
| MDC field | Logging scope/thread context | No | No, unless explicitly attached |
| HTTP `X-Request-Id` | API-contract correlation | Yes | No, unless instrumented separately |

That is why you should never solve “trace lacks tenant info” by copying all user headers into baggage or span attributes.

## 14. Sampling: Propagation Alone Does Not Mean Traces Appear in the UI

### 14.1. Sampling Probability

In Spring Boot, `management.tracing.sampling.probability` sets the root/decision sampling ratio depending on the sampler:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

`0.1` targets roughly **10%** sampling under the sampler policy—**not strictly one out of every ten requests**.

For lab debugging:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Use 100% sampling only under small, controlled traffic because:

- Exported spans and data volume grow sharply.
- Collector/backend CPU, network, and storage costs increase.
- Traces may capture sensitive metadata if not redacted.
- Multi-hop/retried traces generate more spans than raw client request counts.

### 14.2. Parent-Based Sampling

When a client sends sampled flag `00`, a **parent-based sampler** may skip exporting spans even when the app's sampling probability is high. Conversely, a trace with a sampled parent continues being sampled downstream.

Therefore, never jump from “Gateway returned HTTP 200 but trace UI is empty” to “`traceparent` wasn't propagated.” Check:

1. Was outbound `traceparent` present?
2. Do both Gateway and backend have tracers/extractors?
3. Are sampler and propagation types compatible?
4. Is the exporter healthy and the backend indexing/querying properly?

### 14.3. Sampling Decisions Must Align with SLOs

Operational guidelines:

- Low-traffic staging: temporarily use `1.0` for integration tests.
- Production: start with a small rate and measure actual cost.
- Rare errors / high latency: consider tail sampling in the Collector/backend if your architecture supports it.
- Dropped traces must never cause **business requests** to fail. Monitor dropped spans/export failures separately.
- With tail sampling, the Collector must receive all spans belonging to a trace; fan-out collector topologies must route consistently by trace ID.

**Never treat trace sampling like business request rate limiting.** They solve entirely different problems.

## 15. B3 and W3C: Not Every Service Speaks the Same Format

Legacy systems using **B3** may send `b3` or `X-B3-TraceId`/`X-B3-SpanId`. Modern systems typically use **W3C `traceparent`/`tracestate`**.

Spring Boot 3.x docs support configuring propagation formats (such as `management.tracing.propagation.type` or `consume`/`produce` depending on the release):

~~~yaml
# Example explicitly selecting W3C when all services are compatible.
management:
  tracing:
    propagation:
      type: w3c
~~~

**Never enable multiple formats assuming every client and backend handles them identically.** A service that only understands B3 paired with a Gateway emitting only W3C will start a **brand-new trace** downstream even though HTTP succeeds.

When migrating from B3 to W3C:

1. Inventory formats across every service, SDK, and sidecar.
2. During transition, configure version-supported **consume/produce** bridges.
3. Verify `traceId` continuity and parent links at every hop.
4. Avoid conflicting B3 and W3C headers in the same request without a precedence policy.
5. Never translate header IDs between formats with custom regexes.
6. Once converged, narrow formats to remove ambiguity and overhead.

When using B3, baggage behavior can differ from W3C; do not assume a `baggage` header will be parsed by a B3 backend.

## 16. Tracing Across Retries, Circuit Breakers, Load Balancers, and Network Errors

### 16.1. Retries Can Produce Multiple Upstream Attempts Inside One Trace

~~~mermaid
flowchart TD
    C["Client GET"] --> G["Gateway inbound span"]
    G --> R["Retry policy"]
    R --> A1["Attempt 1 → order-1 → 503"]
    R --> A2["Attempt 2 → order-2 → 200"]
    A1 --> T["Trace backend"]
    A2 --> T
    G --> T
~~~

One client request can trigger two HTTP attempts. **How spans appear depends on Retry filter placement and HTTP client observation**: some releases emit one client span per attempt, while other configs may not expose every attempt in default spans.

Therefore, combine:

- Traces showing Gateway → backend relationships.
- **Upstream attempt** metrics by route and exception.
- Logs with route ID, retry count, and selected instance where supported.
- Request latency and backoff timings.
- Avoiding reliance on span counts alone as an exact retry counter across all implementations.

**Never auto-retry mutating operations like payment POSTs just because traces show 503/504.** A timeout does not prove the backend failed to commit; use idempotency keys, deduplication, and reconciliation.

### 16.2. Circuit Breakers and Fallbacks

If a circuit breaker serves a fallback at the Gateway, the client may see 200/503 with **no upstream `order-service` span** for that request. That can be completely expected behavior.

During triage, check breaker state, fallback handlers, and route filters before blaming propagation for a missing downstream span.

### 16.3. Load Balancers and Service Discovery

A `lb://ORDER-SERVICE` route picks an instance via discovery/load balancing when configured. Traces typically show a client span at the Gateway and a server span on the chosen instance. **Trace context does not pick instances** and does not replace service discovery.

If a faulty instance is chosen, traces reveal the connection/response behavior, while metrics, logs, and discovery metadata together pinpoint the root cause.

### 16.4. 502/503/504 Can Occur Before Any Backend Span Exists

Common cases:

| Error | Observable Spans | Note |
| --- | --- | --- |
| No route match | Gateway inbound span, no downstream client span | Likely Gateway 404 |
| DNS / connect refused | Gateway HTTP client observation/error; no backend server span | Request never reached the service |
| TLS handshake failure | Gateway/client error; backend app received no HTTP | Check truststore/certificates |
| Timeout after backend commit | Gateway/client timeout; backend may still commit and emit a span | Never blindly replay POSTs |
| Circuit breaker short-circuit | Gateway span/fallback, no backend attempt | Inspect breaker metrics |
| Backend returns 503 | Gateway outbound + backend server spans if instrumented | May be retried |
| Sampling drop | Headers may be present while spans never reach UI | Do not conclude the request skipped the backend |

## 17. HTTP Headers and Trust Boundaries: Controlling Tracing Data

### 17.1. `traceparent` Is Untrusted Caller-Provided Input

External clients or internet partners can send arbitrary headers:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

A syntactically valid header **proves neither identity** nor authorization to access an order. Attackers can also send colliding/forged trace IDs to pollute logs or inflate contexts.

At public API boundaries, consider:

- Using a standard propagator to validate/normalize and drop malformed contexts.
- Defining a clear policy on **trusting vs. ignoring inbound trace context** from external callers.
- At untrusted boundaries, **starting a fresh root trace** (optionally linking the incoming context) rather than adopting it blindly as a parent.
- Never letting a client-supplied sampled bit bypass tracing budgets indefinitely.
- Bounding `traceparent`, `tracestate`, and `baggage` header sizes to prevent header abuse.
- Never forwarding untrusted baggage to external partners without an explicit contract.

### 17.2. Header Propagation Must Never Leak Secrets

Never store or log in span attributes:

- `Authorization: Bearer <token>`, `Cookie`, `Set-Cookie`.
- Passwords, private keys, API keys, refresh tokens.
- Card numbers/payment info, PII, raw request bodies.
- Query strings with unredacted tokens or emails.
- Baggage carrying sensitive user identities.
- Dynamic raw URIs containing customer data.

Trace backends often have broader read access and different retention than business databases. Sensitive data written to a span gets replicated across exporters, Collectors, storage, and UIs.

### 17.3. Route IDs Are Reasonable Tags; Raw Paths Often Are Not

A static route like `orders-api` has low cardinality. Attaching raw paths `/api/orders/42`, `/api/orders/43`, ... or trace IDs as metric labels creates series proportional to traffic.

Per Gateway metrics guidance, the path tag is **disabled by default** to curb cardinality. Even in span tags, raw URIs can be high-cardinality sensitive metadata; apply filtering/redaction policies. Prefer route templates like `/api/orders/{id}` over raw IDs whenever instrumentation supports them.

### 17.4. Observability Does Not Replace Security

Even when Gateway and `order-service` share a `traceId`, the backend must still authenticate the principal, verify tenant/resource ownership, and enforce authorization. Never trust client-supplied baggage like `tenant=acme` or `role=admin`, even if it appears inside the Gateway's Reactor Context.

## 18. Gateway Observability: Metrics and Traces Must Be Distinguished

Spring Cloud Gateway Server WebFlux provides specific observations/metrics:

| Type | Example Name | Purpose |
| --- | --- | --- |
| HTTP server observation | `http.server.requests` with Boot HTTP integration | Inbound Gateway latency/status |
| Gateway HTTP client observation | `http.client.requests` per Gateway metadata | Outbound HTTP routing duration |
| Gateway request metrics filter | `spring.cloud.gateway.requests` in newer docs | Route-level timer by status, outcome, route ID |
| Custom retry/route metrics | Project-defined names | Upstream attempts, breakers, fallbacks |
| Distributed tracing spans | SERVER/CLIENT spans | Cross-service execution tree |

**Never equate “having Prometheus metrics” with “having traces.”** `micrometer-registry-prometheus` exports metrics, whereas traces require a tracing bridge/tracer and exporter/backend.

An example for the newer Gateway WebFlux branch:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          observability:
            enabled: true
          metrics:
            enabled: true
            path-tags:
              enabled: false
~~~

This configures **observability/metrics**. It does not configure an OTLP span exporter, does not replace proper W3C `traceparent` propagation, and uses different property names on Gateway 4.x.

### 18.1. Why Not Treat a Metric Route ID as a Span ID?

`routeId=orders-api` is a stable route label shared across many requests. `spanId` identifies **one single unit of work** inside one trace. Using route IDs as span IDs would collapse all requests along a route together.

### 18.2. Trace UIs Can Lag Slightly

Collectors batch and export asynchronously. After a `curl` test, you may wait briefly for backend indexing/queries to catch up—but **never use a fixed sleep as proof of system latency**. In automated tests, poll with an explicit bounded timeout asserting the trace eventually appears, never polling indefinitely.

## 19. Three-Process Integration Testing: Client, Gateway, Backend

### 19.1. Lab Setup

Assume:

- **Gateway WebFlux**: `localhost:8080`, route `orders-api`.
- **`order-service`**: `localhost:8081`, with tracing dependencies and demo controller.
- **OTLP Collector**: receiving HTTP at `localhost:4318/v1/traces`.
- **Trace backend**: Jaeger/Tempo/Zipkin fed by the exporter/Collector, with a UI or query API.
- Sampling set to `1.0` in the lab when inspecting all requests, unless specifically testing parent-based sampling.
- You can substitute a mock HTTP server for `order-service` in header-only tests.

Remember **sharing an OTLP endpoint does not mean sharing a service name**: `spring.application.name` must differ between Gateway and backend.

### 19.2. Key Assertions

1. Client sends `GET /api/orders/42`.
2. Gateway matches the route and `StripPrefix` forwards `/orders/42` to the backend.
3. Backend receives a **validly structured W3C `traceparent`**.
4. Backend reports a `traceId` belonging to the same trace exported by the Gateway.
5. Gateway and backend have **distinct span IDs** with valid parent-child linkage.
6. Trace UI displays accurate service names, span timings, and HTTP statuses.
7. Requests without an incoming `traceparent` generate a new trace per policy.
8. Requests with a valid `traceparent` join/preserve the trace ID if trust policy permits.
9. With low sampling, do not treat absence in the UI as proof headers were dropped.
10. 401/403/404 responses may be rejected **before Gateway routing runs**; do not always expect an outbound client span.

### 19.3. Pseudocode for Header Testing with a Mock Upstream

~~~text
Given:
  Gateway has tracing enabled and W3C propagation.
  Mock upstream records HTTP headers.

When:
  GET /api/orders/42
  traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01

Then:
  mock receives GET /orders/42
  mock has traceparent header
  outbound trace-id equals 4bf92f3577b34da6a3ce929d0e0e4736
  outbound parent-id is valid and not all zeros
  gateway response follows mock contract
~~~

This is **pseudocode**, not a runnable standalone test class. If W3C extraction fails due to misconfiguration, the trace ID continuity check should fail loudly. If production intentionally regenerates traces at public boundaries, adjust acceptance criteria to match that policy.

### 19.4. Tracing Inside `@SpringBootTest` Requires Explicit Configuration

Spring Boot docs note that **tracing reporting components may not auto-configure in `@SpringBootTest` by default** to avoid accidentally shipping test spans to live backends. Therefore:

- Mapping/filter unit tests can run **without an exporter**.
- True propagation integration tests must explicitly enable test observation/tracing auto-configuration for your Boot version, or run via embedded servers in a full integration setup.
- Backend `MockMvc` tests and Gateway HTTP integration tests do not always produce identical span types; document expected context behavior.
- Never assume an HTTP 200 in `@SpringBootTest` proves the OTLP exporter ran.
- Never commit observability backend credentials into test source control.

## 20. Scenario Test Matrix

| Case | Action | What to Verify |
| --- | --- | --- |
| T1 | Client GET without `traceparent` | Gateway starts a trace per policy; backend receives context if instrumented |
| T2 | Client GET with valid W3C `traceparent` | Trace ID continues across Gateway/backend when trust policy allows |
| T3 | Malformed inbound `traceparent` | Does not crash; starts fresh context or rejects per policy |
| T4 | Inbound sampled bit `00` | Sampling and propagation behave properly; don't confuse with UI failure |
| T5 | Backend lacks tracing dependencies | Header may arrive, yet no backend server span is exported |
| T6 | Gateway lacks OTLP exporter | Client routing still works; Collector receives no Gateway spans |
| T7 | Collector offline | Gateway must not depend on collector availability to return 200 |
| T8 | Custom `WebClient` built outside Boot builder | Test catches missing context propagation |
| T9 | Custom `WebClient` using Boot-injected builder | Header propagation works across reactive context |
| T10 | Gateway filter calls detached `subscribe()` | Detects split trace and lifecycle bug |
| T11 | `publishOn` switches schedulers | Trace scope/MDC remains intact when context propagation is configured |
| T12 | Proxy/ingress strips `traceparent` | Backend starts a new trace; caught via header/trace tree |
| T13 | W3C on Gateway, B3-only on backend | Trace ID breaks; format migration required |
| T14 | Retry GET 503 then 200 | Trace and attempt metrics reflect two calls per policy |
| T15 | Circuit breaker short-circuits | Upstream server span is not expected |
| T16 | Rate limiter returns 429 before routing | Downstream span is not expected |
| T17 | Gateway `lb://` route has no instances | Gateway error emitted, no backend server span |
| T18 | Baggage contains caller-supplied values | Never used as auth or tenant permission |
| T19 | Request emits multiple span events | No raw tokens or PII queries logged |
| T20 | Raw path metric tags enabled | Cardinality spike detected/bounded |
| T21 | Backend service name matches Gateway | UI becomes confusing; fix resource/service names |
| T22 | HTTP 200 yet trace UI is empty | Check sampling, exporter, Collector, and backend query |

## 21. Diagnosing Broken Traces

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| No traces at all in UI | Missing exporter, wrong Collector endpoint, low sampling | Check dependencies, OTLP URL, exporter logs, sampler |
| Only Gateway spans appear | Backend lacks instrumentation or export | Check backend Actuator/tracing deps |
| Backend has a different trace ID than Gateway | Header not injected/extracted; format mismatch | Inspect outbound `traceparent`, W3C/B3 compatibility |
| `traceparent` header arrives yet backend emits no span | Missing server instrumentation or backend sampling/export failure | Check inbound tracing and Collector |
| Outbound `traceparent` identical to inbound on every request | Filter manually copying instead of propagator | Remove `SetRequestHeader`/manual copy; enable instrumentation |
| Trace ID lost in logs after async boundary | Missing context propagation/MDC bridge | Use framework integration; avoid manual `ThreadLocal` |
| Wrong request's trace ID appears in logs | Tracer/span stored in uncleaned singleton/static/ThreadLocal | Fix scoping; never share per-request state |
| W3C at Gateway, B3 at legacy service | Incompatible propagation formats | Configure version-supported consume/produce formats |
| Trace missing after testing `sampled=00` | Parent sampler honors unsampled flag | Test with `sampled=01` and lab sampler `1.0` |
| Retries add latency yet trace shows only one upstream span | Filter placement/observation doesn't wrap each attempt | Track retry attempts via dedicated metrics/logs |
| 429 lacks downstream span | Rate limiter blocked before HTTP routing | Check Gateway policy first |
| 504 while backend trace shows success | Timeout after backend committed | Do not blindly retry writes; use idempotency/reconciliation |
| Collector returns 404 | Wrong `/v1/traces` path or OTLP HTTP vs. gRPC port | Check exporter protocol and endpoint |
| Boot 4 ignores Boot 3.5 OTLP config | Property namespace changed | Use matching `management.opentelemetry.*` properties |
| WebFlux 5.x routes fail to load | Using legacy `spring.cloud.gateway.routes` prefix | Check prefix and effective routes |
| Tracing works yet metrics are missing | Different registries/exports | Check Micrometer metrics dependency and exposure |
| Logs leak excessive data | Dumping headers/baggage/raw URLs | Redact and restrict attributes |
| Trace spans missing route ID | Different observation convention or route matching | Check Gateway outbound observation/version |

### Ordered Debugging Workflow

1. **Is routing right?** Path/Method/`StripPrefix`, URI, service discovery, and response status.
2. **Is the Gateway instrumented?** Actuator/tracer/observation and version-appropriate properties.
3. **Is `traceparent` on outbound requests?** Capture headers with a mock upstream; avoid logging them in production.
4. **Does the backend read and continue the trace?** Verify trace ID/scope and backend tracing dependencies.
5. **Is sampling dropping spans?** Check the sampled flag and sampler policy.
6. **Are exporter and Collector healthy?** OTLP protocol, host, path, TLS/auth, queues/drops.
7. **Was Reactor Context lost across a thread hop?** Custom clients/filters, detached `subscribe()`, MDC bridge.
8. **Did a proxy or mesh alter headers?** Ingress, firewall, sidecar, HTTP/2 gateway.
9. **Is the trace backend querying the right service/window?** Batching lag, retention, clock skew.
10. **Is the data safe?** Audit baggage, attributes, URLs, and logs for PII before raising sampling.

## 22. Capstone Lab: Tracing a Request from Gateway to `order-service`

**Scenario:** A Gateway receives `GET /api/orders/42` and proxies it to `order-service`. `order-service` may then call `inventory-service`.

### Requirements

1. Choose **one** supported version pair: Boot 3.5 + Gateway WebFlux 4.x, or Boot 4.x + Gateway WebFlux 5.x.
2. Configure distinct `spring.application.name` values such as `edge-gateway` and `order-service`.
3. Enable Actuator, Micrometer Tracing, and the OTLP exporter using **version-accurate** dependencies and properties.
4. Start an OTLP Collector/trace backend able to receive spans; verify HTTP port 4318 if using OTLP HTTP.
5. Define route `orders-api` with `Path=/api/orders/**` and `StripPrefix=1`.
6. Create a mock backend or demo controller returning the order ID and `traceId`.
7. Set sampling to `1.0` **in the test environment**.
8. Send a `curl` without `traceparent` and verify the backend sees the outbound header and a trace ID.
9. Send a `curl` with a valid W3C `traceparent` and verify the trace ID is preserved per trust policy.
10. Query the trace UI and confirm Gateway and backend spans appear in the same tree with accurate service names.
11. Add an outbound `WebClient` call using injected `WebClient.Builder`; verify span/context propagation.
12. Disable tracing on the backend temporarily and observe the broken trace.
13. Test a request returning 401/429 at the Gateway; explain why no backend span exists.
14. Test a GET retry and compare upstream attempt counts against client request counts.
15. Lower sampling and demonstrate why a successful request may not appear in the trace UI.
16. Send a validated `baggage: locale=vi`, verify propagation policy, and confirm baggage is never treated as authorization.
17. Verify log correlation without exposing `Authorization`, cookies, personal IDs, or request bodies.
18. Write a single-request report: route ID, trace ID, spans per service, slowest span, status, and reproduction steps.

### Completion Criteria

~~~text
[PASS] Gateway route matches and upstream receives the expected path
[PASS] Outbound W3C traceparent is present when instrumentation is enabled
[PASS] Trace ID continues end-to-end per chosen propagation policy
[PASS] Gateway and order-service have distinct span IDs
[PASS] Trace backend displays a meaningful parent-child tree
[PASS] Logs include correlation IDs within valid scopes without leaking sensitive data
[PASS] Exporter/sampling issues are distinguished from routing errors
[PASS] Retries and fallbacks are distinguished across tracing and request metrics
[PASS] traceparent is never copied manually via SetRequestHeader
[PASS] Tests prevent baggage from being used as credentials or authorization
~~~

These are **expected criteria**, not test output from a live environment.

## 23. Production Checklist

- [ ] Both Gateway and backends include valid tracer/instrumentation, not just Actuator metrics.
- [ ] Compatible combination of Spring Boot, Spring Cloud Gateway, and exporter dependencies selected.
- [ ] `spring.application.name`/service identity distinguishes every process/service.
- [ ] Gateway WebFlux routing and outbound HTTP client emit observations/propagate traces.
- [ ] Custom `WebClient`/`RestClient` instances are built from auto-configured builders or instrumented explicitly.
- [ ] Any additional HTTP SDKs/gRPC/message brokers have matching propagation configured.
- [ ] W3C/B3 formats and consume/produce policies align end-to-end.
- [ ] Never manually `SetRequestHeader` or copy raw `traceparent` when instrumentation manages propagation.
- [ ] Gateway preserves context across Reactor async chains and scheduler hops.
- [ ] No `block()` on Netty event loops and no detached `subscribe()` inside filters.
- [ ] No per-request spans or trace contexts stored in uncleaned singleton/static/`ThreadLocal` fields.
- [ ] Client-supplied trace context is never used for authentication or tenant authorization.
- [ ] Baggage and `tracestate` enforce allowlists, size caps, redaction, and trust boundaries.
- [ ] Production sampling and budgets align with traffic and cost; never left at `1.0` indefinitely.
- [ ] Collector/exporter configured with TLS/auth, timeouts, queue/drop monitoring, HA, and retention.
- [ ] Collector outages never unintentionally fail business requests.
- [ ] Log correlation includes `traceId`/`spanId` where appropriate without dumping raw tokens/cookies/PII.
- [ ] Span attributes and metrics exclude raw user IDs, dynamic paths, and query secrets.
- [ ] Route IDs and service names stay stable to avoid high metric label cardinality.
- [ ] Retry attempts, circuit breakers, rate limits, and timeouts are observed alongside traces.
- [ ] Integration tests validate parent-child spans across Gateway replicas and instrumented backends.
- [ ] Migration and verification plan exists for W3C/B3 and Spring Boot/Cloud upgrades.
- [ ] Tracing is clearly separated from metrics/health, with backend UI verified beyond HTTP status codes.

## 24. Summary and References

**Distributed tracing** lets you follow a single request across the Gateway, microservices, and downstream calls. The **Trace ID** ties the entire trace together; **Span IDs** separate individual units of work. Over HTTP, propagators use **W3C `traceparent`/`tracestate`** to carry trace context; **baggage** is a separate key-value channel and never a proof of identity or authorization.

For **Spring Cloud Gateway Server WebFlux**, reliable tracing requires:

1. Micrometer Observation/Tracing with a compatible tracer and exporter.
2. Instrumented inbound HTTP server and outbound Gateway HTTP client.
3. Backends that also extract headers, create spans, and export when sampled.
4. Preserved Reactor Context/context propagation across non-blocking pipelines.
5. An OTLP Collector/trace backend configured with the right protocol, endpoint, and retention.
6. Deliberate sampling, log correlation, and security/redaction controls.

**Never add or copy `traceparent` manually as a static header**, and never treat HTTP 200 or header presence alone as sufficient: verify **trace ID continuity, parent-child spans, backend logs, and exporter health**. Combining metrics, logs, and traces lets you separate failing routes, upstream timeouts, retries, circuit breakers, and performance regressions without compromising data security.

### Official Reference Documentation

- [W3C Trace Context — traceparent and tracestate](https://www.w3.org/TR/trace-context/).
- [W3C Baggage](https://www.w3.org/TR/baggage/).
- [Spring Boot 3.5 — Tracing and OTLP](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html).
- [Current Spring Boot — Tracing, OpenTelemetry starter, and Propagating Traces](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Current Spring Boot — Observability and OTLP configuration](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
- [Spring Cloud Gateway Server WebFlux — Global Filters and Gateway Metrics Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html).
- [Spring Cloud Gateway — Configuration Properties and observability settings](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html).
- [Spring Cloud Gateway — Gateway HTTP Client Observation observability metadata](https://docs.spring.io/spring-cloud-gateway/reference/appendix.html).
- [Micrometer Tracing — Context Propagation](https://docs.micrometer.io/tracing/reference/configuring.html).
- [Project Reactor — Context and Context Propagation](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html).
