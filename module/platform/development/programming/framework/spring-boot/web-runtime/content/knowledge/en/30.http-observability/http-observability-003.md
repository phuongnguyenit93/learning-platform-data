# Correlation IDs, Trace IDs, and Linking Requests to Downstream Service Calls

**Context:** Spring Boot → web-runtime → HTTP Observability. When an HTTP request passes through a gateway, service A, service B, a database, and a message queue, you need to know whether logs across those components belong to the same request, which hop took the time, and where errors originated. This lesson distinguishes **request/correlation ID**, **trace ID**, **span ID**, **W3C traceparent**, MDC log context, and distributed tracing; and shows how to automatically propagate traces through Spring Boot-instrumented HTTP clients alongside explicit request ID propagation.

**Lab environment:** Java 17+, Maven, Spring Boot **3.5.16**, Servlet/Spring MVC, Micrometer Tracing + OpenTelemetry bridge. A single application is launched as **two JVM processes** on ports 8080/8081 to demonstrate real outbound HTTP propagation. Includes buildable Java code, curl commands, expected JSON, JUnit HTTP tests, collector/async/WebFlux guidance, security, and a runbook.

**Version note:** 3.5.16 is the final Spring Boot 3.5 release under OSS support (06/2026), pinned only to study stable APIs in the 3.5 line; production should use a branch or maintenance channel receiving security patches. Do not assume Boot 3.5 dependencies or properties match Boot 4.x.

## 1. Why Logs Alone Cannot Automatically Stitch an End-to-End Request

Suppose a browser calls `GET /orders/42`; the API Gateway forwards the request to Order Service; Order Service calls Inventory Service, which queries a database. Meanwhile, thousands of concurrent requests share thread pools across multiple service replicas.

~~~text
Browser                    Gateway                 Order Service A             Inventory B            DB
   │                          │                           │                      │                   │
   ├── GET /orders/42 ───────►│                           │                      │                   │
   │                          ├── GET /orders/42 ─────────►│                      │                   │
   │                          │                           ├── GET /stock/42 ──────►│                   │
   │                          │                           │                      ├── SQL query ──────►│
   │                          │                           │                      │◄──────────────────┤
   │                          │                           │◄─────────────────────┤                   │
   │                          │◄──────────────────────────┤                      │                   │
   │◄─────────────────────────┤                           │                      │                   │
   │                          │                           │                      │                   │
   │  requestId: r-123  ───────────────────────────────────────────────────────────►│ (custom header)
   │  traceId:   T      ───────────────────────────────────────────────────────────►│ (trace context)
   │                          │   span A-server=S1 ─┐                            │
   │                          │                      ├─ span A-client=S2 ─┐       │
   │                          │                      │                    ├─ B-server=S3
~~~

An `INFO Calling inventory` line and a `WARN Inventory timeout` line do not prove they came from the same request. Timestamps, URLs, and thread names are **not enough** when concurrency, retries, and async tasks exist.

Two complementary tools solve this:
- **Log correlation:** attaches IDs to every log record so related lines can be searched across one or more log streams.
- **Distributed tracing:** creates multiple spans, carries parent/trace context across the network, and displays latency waterfalls, parent-child relationships, and per-hop errors.

Having IDs in logs does not mean you have a trace UI; having a trace UI does not guarantee your log pipeline indexes fields to query by ID. Design logs, metrics, and traces together.

## 2. Vocabulary: Request ID, Correlation ID, traceId, and spanId

| Name | Typical shape | What does it identify? | Changes across HTTP hops? |
| --- | --- | --- | --- |
| **Request ID** (e.g., `X-Request-ID`) | UUID or length-bounded opaque string | One inbound edge request or transaction per custom convention | **Preserved only with intentional custom propagation** |
| **Correlation ID** (`X-Correlation-ID` or logging key) | Org-defined ID | General correlation term requiring an internal contract | Depends on contract |
| **Trace ID** (`traceId`) | W3C: 32 hex digits, 128-bit | One distributed trace | **Normally preserved** across spans in one trace |
| **Span ID** (`spanId`) | W3C: 16 hex digits, 64-bit | One unit of work: HTTP server/client/DB... | **Normally distinct** for each span |
| **Parent span ID** | 16 hex | Links current span to its caller/parent span | Changes with the span tree structure |
| **Logging correlation field** | `[traceId-spanId]` or `requestId` | How the formatter injects MDC fields into logs | Depends on log config and context |

**One trace contains multiple spans.** Sharing the same `traceId` while having different `spanId` values is normal and expected. `Request ID` does not replace `traceId`, because tracing frameworks **do not automatically convert** an `X-Request-ID` header into a W3C trace context.

**Business IDs** like `orderId` or `paymentAttemptId` have a different lifecycle: a single order can span many HTTP requests, jobs, and traces over several days. Keep business IDs as domain keys and `traceId`/`requestId` as operational observability keys. Never use `traceId` as a primary database key or default idempotency key.

### 2.1. Defining the Correlation Contract Explicitly

For `X-Request-ID`, specify:
1. Who generates it: edge gateway, ingress, or the first application?
2. When a client sends an ID, do you accept, validate, or **strip/overwrite** it?
3. What format (UUID/ULID/opaque string), max length, charset, and canonical case?
4. Is it propagated to downstream HTTP services, message queues, and scheduled jobs?
5. Is it echoed in the HTTP response for support lookup?
6. What are the MDC/log field name and log retention/access controls?
7. On retries, redirects, or fan-out, is the ID preserved, and is an attempt ID also needed?
8. When a request crosses a trust boundary between tenants/organizations, is a new ID generated?

There is no universal HTTP standard forcing every system to use `X-Request-ID` or `X-Correlation-ID`. Header names are agreed upon by teams and infrastructure.

## 3. W3C Trace Context: traceparent and tracestate

Standard W3C trace context travels via HTTP headers:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=opaque-example
~~~

`traceparent` version 00 format:

~~~text
00 - 4bf92f3577b34da6a3ce929d0e0e4736 - 00f067aa0ba902b7 - 01
│                   │                               │              │
│                   └── trace-id: 32 hex            │              └── trace-flags: 2 hex
└── version: 2 hex                                  └── parent-id: 16 hex
~~~

- **Trace ID** represents the entire trace; all-zero is invalid.
- **Parent ID** is the span ID set by the **sender** in the header (usually A's HTTP client span). B receives that context and creates a **new HTTP server span**, so B's span ID is **not equal** to the received parent-id.
- **Flags** hold the sampled bit, e.g., `01`. This is a suggestion, not a mandate for downstream to export every span; sampling policies can shed load.
- **Tracestate** holds vendor tracing metadata; avoid sensitive info, enforce limits, and validate.
- **Baggage** is cross-service data context, distinct from tracestate and log MDC. Never stuff raw JWTs, session cookies, or emails into baggage.

Correct parent-child relationship example:

~~~text
traceId = T  (preserved)
└── A HTTP server span: S1
    └── A HTTP client span: S2  → outbound traceparent has parent-id = S2
        └── B HTTP server span: S3  → parent = S2, spanId = S3
            └── B DB span: S4
~~~

Comparing only two JSON fields `A.spanId` and `B.spanId` **cannot prove parent-child lineage**; to inspect the actual `parentId`, open exported spans in your trace backend (Jaeger, Tempo, Zipkin). Comparing trace IDs only confirms they belong to the same trace, not the topology.

### 3.1. HTTP Headers Are Not Interchangeable

| Header | Scope | Added automatically by Spring Boot tracing? |
| --- | --- | --- |
| `traceparent` | W3C trace context | **Yes**, with instrumented HTTP client/propagator |
| `tracestate` | W3C vendor state | When propagatable vendor state exists |
| `baggage` | Propagated application context per baggage spec | If tracer/baggage config enables it |
| `b3`/`X-B3-TraceId` | Legacy B3/Zipkin tracing | When configured to consume/produce B3 |
| `X-Request-ID` | Custom application request ID | **No**, requires custom injector/interceptor/gateway |
| `X-Correlation-ID` | Custom app correlation ID | **No**, unless a custom contract is implemented |

Spring Boot 3.5 offers `management.tracing.propagation.consume`, `produce`, and `type`. In Boot 3.5.16 properties, the default **produces W3C** and consumes **W3C/B3/B3_MULTI**; configuring `type` overrides granular choices. Verify both services use compatible formats; you cannot have "A sends B3, B only accepts W3C" and expect a single connected trace.

### 3.2. Trace Context Is Untrusted Input

Public clients can craft valid `traceparent` headers with arbitrary trace IDs and sampled flags. Tracers must parse/validate per spec, and gateways may choose to **restart the trace** at security boundaries. Do not concatenate strings into headers yourself and assume tracing works; never treat `traceparent` as a credential or authorization decision. Use the tracer SDK/propagator instead of hand-rolled parsers for hex/all-zero/flags/tracestate.

## 4. Spring Boot Actuator, Observation, and Micrometer Tracing

Spring Boot provides:
- **Micrometer Observation**: abstraction for recording HTTP/server/client and instrumented operations. Observations can emit both metrics and traces.
- **Micrometer Tracing**: facade over OpenTelemetry or Brave that creates/reads spans, binds MDC correlation automatically, and propagates context through client instrumentation.
- **Actuator**: auto-configuration and metrics/tracing integration; having Actuator does **not mean all endpoints or collectors are exposed**.
- **OTLP/Zipkin exporter**: sends spans to collectors/backends when dependencies and configuration are present.
- **Logback/SLF4J MDC**: holds field mappings in the current logging scope so formatters print `traceId`, `spanId`, and custom `requestId`.

Two common dependency stacks in Boot 3.5:
- OpenTelemetry: `spring-boot-starter-actuator` + `micrometer-tracing-bridge-otel` + `opentelemetry-exporter-otlp` (or Zipkin exporter).
- Brave: `spring-boot-starter-actuator` + `micrometer-tracing-bridge-brave` + compatible reporter.

**Choose only one primary tracing stack** per application. Mixing an OTel agent, OTel starter, and uncontrolled custom Micrometer instrumentation can produce duplicate spans. For HTTP handlers already instrumented by Spring, do not add `@Observed` on every controller just to "get traces", or you will create double observations.

### 4.1. Processing Order When a Request Enters Spring MVC

~~~text
HTTP inbound ──► Servlet container
                   ├── observation/tracing instrumentation
                   │      creates/restores server span context
                   ├── application Request-ID filter (custom MDC)
                   │
                   └── DispatcherServlet → Controller → Service
                                            │
                                            └─ RestClient (Boot Builder)
                                                 creates client observation/span
                                                 injects outbound traceparent
                                                 injects custom X-Request-ID
                                    ▼
                                 HTTP service B
                                    └─ extracts traceparent → new server span
~~~

Actual filter ordering depends on Boot/context/filter order. The goal is for the **controller and outbound client to execute inside an active trace scope** and for `requestId` MDC to be set before logs/business logic run; do not infer exact ordering strictly from the diagram. Avoid registering the same filter twice in both the container and Spring Security chain, or adding a duplicate server observation filter when Boot already provides one.

### 4.2. Builders Determine Automatic HTTP Trace Propagation

Boot 3.5 docs recommend building clients with auto-configured builders:
- `RestClient.Builder`
- `RestTemplateBuilder`
- `WebClient.Builder`

**Easy way to lose instrumentation:**

~~~java
RestClient raw = RestClient.create();
// Does not automatically receive Boot customizers / ObservationRegistry.
~~~

**Correct approach when outbound traceparent is needed:**

~~~java
@Bean
RestClient myClient(RestClient.Builder builder) {
    return builder.baseUrl("http://127.0.0.1:8081").build();
}
~~~

This is an **illustrative configuration fragment**; the full project in Section 6 includes a request-ID-propagating interceptor. `RestClient.Builder` must be injected by Spring Boot rather than manually calling `RestClient.builder()` without attaching an observation registry. For reactive `WebClient`, likewise inject Boot-managed `WebClient.Builder`.

### 4.3. Log Correlation and Sampling

When Micrometer Tracing is active, Spring Boot prints correlation IDs from MDC `traceId` and `spanId` by default. You can customize it:

~~~properties
logging.pattern.correlation=[${spring.application.name:},trace=%X{traceId:-},span=%X{spanId:-},req=%X{requestId:-}] 
logging.include-application-name=false
~~~

Notice `logging.pattern.correlation` above **ends with a trailing space** after `]` so it does not run directly into the logger name. `logging.include-application-name=false` prevents printing the application name twice. This formats text logs, not default JSON structured logging.

Spring Boot 3.5 `management.tracing.sampling.probability` defaults to around **0.1**; the lab uses **1.0** for visibility. **A `traceId` in logs does not guarantee the span was exported**: sampling might drop it, the exporter might be off, the collector unreachable, the backend might drop it, or ingestion might lag.

## 5. Lab Architecture: One JAR, Two JVMs, One Trace

To keep setup simple while verifying propagation over real sockets, run one Maven project as two processes:
- `frontend` on port `8080`, `GET /entry` as the main entry point.
- `backend` on port `8081`, `GET /internal` as the downstream API.
- Both run the same code, differing in `spring.application.name` and port.
- `frontend`'s `RestClient.Builder` automatically propagates W3C `traceparent`.
- A custom interceptor copies `X-Request-ID` from MDC to the outbound header.
- A filter in each JVM extracts/validates `X-Request-ID` or generates a new UUID, echoes the response header, and sets/cleans up MDC.
- Endpoints return JSON containing `service`, `traceId`, `spanId`, `requestId` **strictly for lab verification**.

~~~text
curl ──► frontend:8080/entry ── RestClient GET ──► backend:8081/internal
           │ traceId=T, spanId=A                     │ traceId=T, spanId=B
           │ requestId=R                             │ requestId=R
           └────── HTTP JSON caller + downstream ◄──┘
~~~

**No collector is needed to verify both IDs in JSON** because the lab keeps the tracing bridge active while disabling export. To inspect the full span tree and latency waterfall, Section 8 enables the exporter and collector. Both endpoints lack authorization solely for local practice: they bind to `127.0.0.1` by default—**do not expose them to the Internet**.

## 6. Complete Java 17 / Maven Project

Directory tree:

~~~text
http-correlation-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/correlation/
    │   │   ├── CorrelationApplication.java
    │   │   ├── RequestIdFilter.java
    │   │   ├── HttpClientConfiguration.java
    │   │   └── CorrelationController.java
    │   └── resources/application.properties
    └── test/java/com/example/correlation/
        └── RequestIdHttpTest.java
~~~

### 6.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>http-correlation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-otel</artifactId>
        </dependency>
        <dependency>
            <groupId>io.opentelemetry</groupId>
            <artifactId>opentelemetry-exporter-otlp</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The Spring Boot BOM manages compatible transitive versions. You do not need `spring-boot-starter-webflux` to use `RestClient` because this is Servlet MVC. Reactive `WebClient` configuration is covered in Section 10.

### 6.2. CorrelationApplication.java

~~~java
package com.example.correlation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorrelationApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorrelationApplication.class, args);
    }
}
~~~

### 6.3. RequestIdFilter.java

~~~java
package com.example.correlation;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public final class RequestIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Request-ID";
    private static final String MDC_KEY = "requestId";
    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{8,64}");

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {

        String candidate = request.getHeader(HEADER);
        String id = candidate != null && SAFE.matcher(candidate).matches()
                ? candidate
                : UUID.randomUUID().toString();

        // Restore previous value to avoid leaking IDs across requests/threads.
        String previous = MDC.get(MDC_KEY);
        MDC.put(MDC_KEY, id);
        try {
            response.setHeader(HEADER, id);
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(MDC_KEY);
            } else {
                MDC.put(MDC_KEY, previous);
            }
        }
    }
}
~~~

**Key points to understand:**
- `@Component` causes Boot to register the filter with the Servlet container; **do not** also pass the same instance to `HttpSecurity.addFilterBefore` in a Spring Security chain.
- The regex bounds characters and length, **not trustworthiness of the header source**. A public client can still send a fake ID matching the regex. In production, a secure edge should **strip/overwrite** incoming IDs or services should trust only a trusted proxy per policy.
- `OncePerRequestFilter` does not guarantee a single execution across async/ERROR dispatches in every circumstance; this lab uses synchronous MVC.
- Scoped `MDC.put` with `finally` cleanup prevents an earlier request's ID from appearing in a subsequent request's logs. Never use request IDs for authorization.
- Fall back to UUID when no valid ID is provided, and never store tokens or PII in correlation IDs.

### 6.4. HttpClientConfiguration.java

~~~java
package com.example.correlation;

import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class HttpClientConfiguration {

    @Bean
    RestClient downstreamRestClient(
            RestClient.Builder builder,
            @Value("${demo.downstream.base-url:http://127.0.0.1:8081}")
            String baseUrl) {

        // Spring Boot-managed builder retains HTTP tracing instrumentation.
        return builder
                .baseUrl(baseUrl)
                .requestInterceptor((request, body, execution) -> {
                    // X-Request-ID is custom propagation, separate from traceparent.
                    String id = MDC.get("requestId");
                    if (id != null) {
                        request.getHeaders()
                                .set(RequestIdFilter.HEADER, id);
                    }
                    return execution.execute(request, body);
                })
                .build();
    }
}
~~~

The interceptor propagates only the **request ID**, without manually building or overriding `traceparent`. Span/client context is added by Spring/Micrometer instrumentation when using the Boot-provided `RestClient.Builder`. Using `RestClient.create()` in application code loses auto-propagation and causes B to start a new trace.

### 6.5. CorrelationController.java

~~~java
package com.example.correlation;

import java.util.Objects;
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class CorrelationController {
    private static final Logger log =
            LoggerFactory.getLogger(CorrelationController.class);

    private final Tracer tracer;
    private final RestClient client;
    private final String serviceName;

    public CorrelationController(
            Tracer tracer,
            RestClient downstreamRestClient,
            @Value("${spring.application.name:trace-demo}")
            String serviceName) {
        this.tracer = tracer;
        this.client = downstreamRestClient;
        this.serviceName = serviceName;
    }

    // Localhost lab only; production endpoints must be secured.
    @GetMapping("/entry")
    public EntryResult entry() {
        TraceInfo caller = currentInfo();
        log.info("entry received, requestId={}", caller.requestId());

        TraceInfo downstream = Objects.requireNonNull(
                client.get()
                      .uri("/internal")
                      .retrieve()
                      .body(TraceInfo.class),
                "Downstream returned no response body");

        log.info("backend answered, service={}", downstream.service());
        return new EntryResult(caller, downstream);
    }

    @GetMapping("/internal")
    public TraceInfo internal() {
        TraceInfo info = currentInfo();
        log.info("internal received, requestId={}", info.requestId());
        return info;
    }

    private TraceInfo currentInfo() {
        Span span = tracer.currentSpan();
        String traceId = span == null ? "missing"
                : span.context().traceId();
        String spanId = span == null ? "missing"
                : span.context().spanId();

        return new TraceInfo(serviceName, traceId, spanId,
                             MDC.get("requestId"));
    }

    public record TraceInfo(String service, String traceId,
                            String spanId, String requestId) {
    }

    public record EntryResult(TraceInfo caller,
                              TraceInfo downstream) {
    }
}
~~~

Each process exposes both endpoints since they share one JAR, but in the lab **only call `/entry` on frontend** and **`/internal` on backend**. The nested records are public so Jackson serializes/deserializes them to/from JSON. `"missing"` is a diagnostic marker when no current span exists, not a valid trace ID.

**Do not expose raw `traceId`/`spanId` in public production response bodies.** They are returned here solely to test equality/inequality. For end users and support, returning `X-Request-ID` is usually more appropriate; logs and trace stores have separate access controls.

### 6.6. application.properties

~~~properties
# Restrict demo to loopback; never expose unauthenticated endpoints.
server.address=127.0.0.1
server.port=8080
spring.application.name=trace-demo
demo.downstream.base-url=http://127.0.0.1:8081

management.tracing.enabled=true
management.tracing.sampling.probability=1.0

# Both JVMs use W3C; Boot 3.5 defaults to producing W3C already.
management.tracing.propagation.produce=W3C
management.tracing.propagation.consume=W3C

# Demo requires no collector; disable export, DO NOT disable tracing.
management.otlp.tracing.export.enabled=false

# Logback MDC fields: Micrometer traceId, spanId, custom requestId.
logging.pattern.correlation=[${spring.application.name:},trace=%X{traceId:-},span=%X{spanId:-},req=%X{requestId:-}] 
logging.include-application-name=false

# Expose only health to avoid opening all Actuator endpoints.
management.endpoints.web.exposure.include=health
~~~

**Distinctions:**
- `sampling.probability=1.0` suits a lab, not high-scale production best practice.
- `management.otlp.tracing.export.enabled=false` only disables sending spans to a collector; trace contexts are still generated and propagated.
- `management.tracing.propagation.produce/consume=W3C` is the standard format. For legacy B3 interoperability, configure compatibility carefully.
- `logging.pattern.correlation` is a log format pattern and does not create distributed spans without tracing dependencies.
- `X-Request-ID` is outside W3C properties; the custom interceptor forwards it.

### 6.7. Running Two Real JVMs

With all files in place at the project root:

~~~bash
java -version
mvn clean package
~~~

**Terminal B** (backend, start first):

~~~bash
java -jar target/http-correlation-demo-0.0.1-SNAPSHOT.jar \
  --server.port=8081 \
  --spring.application.name=backend
~~~

**Terminal A** (frontend):

~~~bash
java -jar target/http-correlation-demo-0.0.1-SNAPSHOT.jar \
  --server.port=8080 \
  --spring.application.name=frontend \
  --demo.downstream.base-url=http://127.0.0.1:8081
~~~

On PowerShell, use a single line or PowerShell backtick line continuation; Bash's trailing `\` is not a line continuation in PowerShell. Both services bind to loopback; note that inside Docker/Kubernetes, `127.0.0.1` in one **container** does not reach another container.

**Terminal C**:

~~~bash
curl -i -H 'X-Request-ID: lab-request-12345' \
  http://127.0.0.1:8080/entry
~~~

### 6.8. Expected JSON and How to Read It

JSON **illustrates the shape**; IDs change on every call and Jackson may emit a single compact line rather than pretty-printed JSON:

~~~json
{
  "caller": {
    "service": "frontend",
    "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
    "spanId": "00f067aa0ba902b7",
    "requestId": "lab-request-12345"
  },
  "downstream": {
    "service": "backend",
    "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
    "spanId": "12ab34cd56ef7890",
    "requestId": "lab-request-12345"
  }
}
~~~

Frontend headers include:

~~~http
X-Request-ID: lab-request-12345
Content-Type: application/json
~~~

**Expected assertions when tracing/propagation works:**
- `caller.service == frontend`, `downstream.service == backend`.
- `caller.traceId == downstream.traceId`, both 32 hex characters, neither `"missing"`.
- `caller.spanId != downstream.spanId`, each 16 hex characters, neither `"missing"`.
- `caller.requestId == downstream.requestId == lab-request-12345`.
- Response header `X-Request-ID` matches `requestId`.
- Logs in both JVMs can be searched by `req=lab-request-12345` and share the same `traceId`.

**Note:** B's server span parent is normally **A's client span**, not A's server span; viewing only the two controller JSON objects does not show that intermediate client span. To verify parent-child lineage and the waterfall, enable the exporter/collector in Section 8.

### 6.9. When No Request ID Is Sent

~~~bash
curl -i http://127.0.0.1:8080/entry
~~~

Frontend generates a UUID and forwards it to B; the response header and both JSON objects share that new ID. When an ID is too short:

~~~bash
curl -i -H 'X-Request-ID: bad' \
  http://127.0.0.1:8080/entry
~~~

The filter replaces it with a UUID because `bad` fails the 8-character minimum regex. **This is input sanitation, not full anti-spoofing**: an attacker-chosen ID matching the regex is still accepted in the lab. Production must enforce trusted edge overwrites or origin validation.

### 6.10. When a Client Sends a W3C traceparent

~~~bash
curl -i \
  -H 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' \
  -H 'X-Request-ID: lab-tracing-0001' \
  http://127.0.0.1:8080/entry
~~~

Without a gateway resetting trace context, the W3C tracer can continue the incoming `traceId` through A and B. **This is a local propagation test**, not a production policy: external callers could manipulate flags or IDs, so evaluate trace restarts/sampling at trust boundaries.

### 6.11. Testing Equality with jq (Optional)

~~~bash
curl -sS \
  -H 'X-Request-ID: lab-request-12345' \
  http://127.0.0.1:8080/entry |
jq '{
  sameTrace: (.caller.traceId == .downstream.traceId),
  differentSpan: (.caller.spanId != .downstream.spanId),
  sameRequestId: (.caller.requestId == .downstream.requestId),
  caller: .caller.service,
  downstream: .downstream.service
}'
~~~

Expected logical output:

~~~json
{
  "sameTrace": true,
  "differentSpan": true,
  "sameRequestId": true,
  "caller": "frontend",
  "downstream": "backend"
}
~~~

These `true` values are the **expected** result when the project works properly, not a claim that it ran on the reader's machine. If any field is `false`, consult the troubleshooting table in Section 14.

## 7. HTTP Integration Test with Embedded Container

Tests under `@SpringBootTest` have different tracing-reporting auto-configuration than runtime. Therefore, the JUnit test below **only verifies the custom `X-Request-ID` HTTP contract**, without assuming a running collector or asserting random span IDs. To test real traces, use `@AutoConfigureObservability` and a test tracer/exporter setup, or run the two-JVM test above.

File `src/test/java/com/example/correlation/RequestIdHttpTest.java`:

~~~java
package com.example.correlation;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RequestIdHttpTest {
    @LocalServerPort
    int port;

    String endpoint() {
        return "http://127.0.0.1:" + port + "/internal";
    }

    @Test
    void safeRequestIdIsEchoed() {
        ResponseEntity<CorrelationController.TraceInfo> r =
            RestClient.create().get()
                .uri(endpoint())
                .header("X-Request-ID", "lab-test-00001")
                .retrieve()
                .toEntity(CorrelationController.TraceInfo.class);

        assertEquals("lab-test-00001",
                     r.getHeaders().getFirst("X-Request-ID"));
        assertNotNull(r.getBody());
        assertEquals("lab-test-00001", r.getBody().requestId());
    }

    @Test
    void unsafeShortIdIsReplacedByUuid() {
        ResponseEntity<CorrelationController.TraceInfo> r =
            RestClient.create().get()
                .uri(endpoint())
                .header("X-Request-ID", "bad")
                .retrieve()
                .toEntity(CorrelationController.TraceInfo.class);

        String id = r.getHeaders().getFirst("X-Request-ID");
        assertNotNull(id);
        assertTrue(id.matches(
            "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"));
        assertNotNull(r.getBody());
        assertEquals(id, r.getBody().requestId());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Both tests are expected to PASS** when source files match. The test hits `/internal` directly on `RANDOM_PORT`, so process B is unnecessary. In the **test client**, `RestClient.create()` is intentional since it only tests raw HTTP request-ID handling; the **main application** uses the injected Boot `RestClient.Builder` to retain tracing. This test does not itself prove cross-process parentage; that is the purpose of the two-JVM smoke test plus collector/test exporter.

## 8. Exporting Spans and Inspecting the Trace Tree

To **view the latency waterfall**, you need a running OpenTelemetry Collector/Tempo/Jaeger with an OTLP HTTP receiver. Enable the exporter in both A and B:

~~~properties
management.otlp.tracing.export.enabled=true
management.otlp.tracing.endpoint=http://127.0.0.1:4318/v1/traces
~~~

`4318/v1/traces` is the OTLP/HTTP convention, while **4317** is typically OTLP/gRPC. In containers, `127.0.0.1` points to the container itself rather than an external collector; use a managed DNS/Service URL instead. Enforce TLS/auth, rate limits, and tenant authorization in production.

After enabling the exporter and calling `/entry`, the trace backend ideally displays:

~~~text
Trace T
└── frontend HTTP server /entry          S1
    └── frontend HTTP client GET         S2
        └── backend HTTP server /internal S3
~~~

Additional instrumentation may also emit business/DB spans. **The parent of S3 is S2** in the standard HTTP client/server model. Do not equate `trace ID generated` with `trace successfully exported`:
- exporter off → logs/JSON show IDs while UI stays empty;
- low sampling → individual traces may not be stored;
- collector unreachable → exporter logs errors and drops spans;
- backend ingestion/indexing delay or wrong tenant query → span not yet searchable;
- misconfigured log MDC parsing → trace UI works, but trace-to-logs links fail.

Log correlation, trace export, and metrics are **three distinct telemetry pipelines**. Do not expose all Actuator endpoints publicly, and never send raw tokens/PII inside span attributes or baggage.

## 9. Request ID, Baggage, and Downstream Headers

In this code, `requestId` is a **custom HTTP header**. The interceptor reads MDC and calls `set("X-Request-ID", id)` before executing the HTTP exchange. W3C `traceparent` does **not** automatically do that for you.

An alternative pattern uses Micrometer baggage:

~~~java
// Illustrative snippet inside a Spring-managed class with injected Tracer.
try (BaggageInScope scope =
         tracer.createBaggageInScope("support-key", "demo-123")) {
    // Call instrumented downstream client here.
}
~~~

Imports are `io.micrometer.tracing.BaggageInScope` and `Tracer`. With W3C baggage propagation enabled, baggage entries can travel via the `baggage` header. Spring Boot provides `management.tracing.baggage.remote-fields` to allowlist remote fields and `management.tracing.baggage.correlation.fields` to mirror selected fields into MDC. **Baggage is not a place to store secrets/PII.**

**Never blindly forward all inbound headers** to service B: `Authorization`, `Cookie`, baggage, or correlation metadata can cross trust boundaries and leak data. Define an explicit allowlist and enforce service-specific security policies.

## 10. With @Async, Reactor, and Message Queues

### 10.1. MDC Is a Scoped ThreadLocal Context

In synchronous MVC, requests normally enter controllers with an active trace scope. However:

~~~java
// Anti-pattern: spawning a raw thread without restoring context.
new Thread(() -> log.info("background processing")).start();
~~~

The new thread will lose MDC and the current span. **Do not use a static/global map** to share request context across threads: concurrent requests will overwrite each other. To propagate context, use Micrometer Context Propagation or explicit parameters.

### 10.2. ContextPropagatingTaskDecorator

Spring Boot 3.5 Observability docs recommend `ContextPropagatingTaskDecorator` for `@Async` and `AsyncTaskExecutor`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

@Configuration(proxyBeanMethods = false)
class ContextPropagationConfig {
    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }
}
~~~

When configuring a `ThreadPoolTaskExecutor` manually:

~~~java
@Bean
ThreadPoolTaskExecutor applicationTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
    executor.initialize();
    return executor;
}
~~~

This is a **code fragment** requiring specific imports/config and is not part of the main lab project. `TaskDecorator` captures and restores **contexts that have registered accessors**; it does not automatically guarantee propagation for every arbitrary custom MDC key. If a request ID must persist in a long-running background job, store/pass it explicitly in job metadata/parameters rather than relying indefinitely on HTTP thread-locals.

### 10.3. WebFlux and Reactor Context

Reactive WebFlux/Netty does not guarantee a request stays on the same Java thread. Spring Boot 3.5 supports:

~~~properties
spring.reactor.context-propagation=auto
~~~

to enable automatic context propagation with Micrometer. Inject Boot's `WebClient.Builder`, not `WebClient.create()`. When writing custom `WebFilter`s or using `publishOn`/`subscribeOn`, test MDC/`traceId` under concurrency; you may need Reactor Context and tracing scopes instead of calling `MDC.put` directly inside callbacks.

**A Servlet `OncePerRequestFilter` does not automatically act as a WebFlux `WebFilter`.** When an app includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Boot typically chooses MVC/Servlet unless overridden; verify the actual runtime.

### 10.4. Kafka/RabbitMQ/SQS

HTTP `traceparent` does not cross a message broker automatically unless the producer is instrumented and injects headers. For async messaging:
- Producers inject trace context into **message headers** via client/binder instrumentation.
- Consumers extract context and create a consumer span or **span link** depending on causal semantics.
- Messages can retry, redeliver, or execute hours later; do not hold an HTTP request scope open indefinitely.
- Business IDs (like order ID) link workflows spanning longer than a single trace's lifetime.
- Verify Spring Kafka/AMQP/cloud SDK instrumentation separately rather than assuming `RestClient.Builder` covers MQ.

## 11. Sampling, Cardinality, and Observability Costs

**Sampling** controls what fraction of traces are recorded/exported. `management.tracing.sampling.probability=1.0` works well in a lab but can overwhelm production collectors and storage. Design sampling around traffic, error signals, critical flows, and compliance; never treat `sampled=1` from a public client as a mandatory command to burn resources.

**Metric cardinality** is a separate hazard:
- Suitable low-cardinality tags: `service=frontend`, `method=GET`, `route=/orders/{id}`, `status=200`.
- Unsuitable per-request metric labels: `traceId`, `requestId`, email, session token, raw `orderId`, or URLs with arbitrary IDs.
- In distributed traces, high-cardinality attributes can be useful, provided privacy and retention are enforced.
- Do not annotate every auto-instrumented MVC controller with `@Observed`, as it creates duplicate observations; add custom observations around **new business operations** only when valuable.

Illustrative snippet for a business step:

~~~java
Observation.createNotStarted("inventory.reserve", observationRegistry)
    .lowCardinalityKeyValue("result", "accepted")
    .observe(() -> {
        // Business logic not already auto-instrumented by the framework.
    });
~~~

This snippet needs `io.micrometer.observation.Observation` and `ObservationRegistry` injected into a Spring-managed service. Do not pass `requestId` into `lowCardinalityKeyValue`; doing so creates nearly one label value per request.

## 12. Retries, Timeouts, and Non-1:1 Span Trees

If A calls B twice due to a retry:
- A may create two **HTTP client spans** for the attempts (depending on where retry sits relative to instrumentation).
- B may create two **server spans**, even though the user clicked only once.
- `traceId` can remain identical if retries occur within the same active context.
- `requestId` typically stays the same per contract; add an attempt counter/ID if individual attempts must be distinguished.
- If a circuit breaker rejects before hitting the network, there may be **no span from B**.
- If B processed a POST but A timed out and retried, you need a business **Idempotency-Key**—never rely on `traceId` or `X-Request-ID` to guarantee exactly-once execution.

~~~text
Trace T
└── A-server span S1
    ├── A-client attempt 1 S2 (timeout)
    │   └── B-server S3
    └── A-client attempt 2 S4 (success)
        └── B-server S5
~~~

This shows a possible topology, not a promise that every library emits these exact spans. Seeing B log twice does not automatically mean a filter was registered twice; check retries, proxies, and request IDs.

## 13. Security and Privacy

Public clients can forge IDs/context. Enforce **trust boundaries**:
1. The edge generates a fresh request ID or strips/overwrites untrusted client values.
2. Backends trust metadata only from verified proxies over protected networks/identities.
3. The tracing runtime parses standard W3C headers and applies policies to restart traces across boundaries/tenants; cap header sizes for `tracestate`/`baggage`.
4. Never grant authorization simply because a caller knows a `traceId` or `requestId`.
5. Never allow arbitrary users to query logs/traces by ID without authorization/tenant checks.
6. Never log raw `Authorization`, `Cookie`, JWTs, passwords, payment cards, or sensitive query strings.
7. Validate/escape header fields against CRLF/log injection and enforce size limits/truncation.
8. Redact/enforce retention on span attributes, baggage, and structured logs per data policy.
9. Use TLS/mTLS, ingress policies, and service identities between hops.
10. Do not expose the lab's `/entry` or `/internal` endpoints beyond localhost without authentication.

**MDC cleanup** is part of data security: request A must never leave its `requestId` on a pooled thread used by request B. The demo filter restores/removes it in `finally`. Let the tracer manage `traceId`/`spanId` in MDC; do not manually run `MDC.put("traceId", request.getHeader("traceparent"))`, which violates semantics and trusts unvalidated headers.

### 13.1. Response Headers and Browser CORS

In browsers, the response header:

~~~http
X-Request-ID: lab-request-12345
~~~

appears in the Network tab, yet cross-origin JavaScript **cannot read it** unless the server exposes custom response headers. Within an allowed CORS policy, you can add:

~~~http
Access-Control-Expose-Headers: X-Request-ID
~~~

Do not enable permissive CORS solely for debugging; evaluate allowed origins and credentials carefully. CORS is neither authorization nor proof that trace context is trustworthy.

### 13.2. Structured Logs with traceId/spanId/requestId

An **illustrative** JSON log schema, not Spring Boot's default format:

~~~json
{
  "timestamp": "2026-11-08T04:30:00Z",
  "level": "INFO",
  "service": "frontend",
  "message": "downstream answered",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "requestId": "lab-request-12345",
  "http.route": "/entry"
}
~~~

Producing real JSON requires a logging encoder or structured logging setup matching your Boot version. Trace backends store **spans**, not every application log line by default. Configure ingestion and indexed fields properly so you can pivot from a trace UI to logs via `traceId`, and from a support ticket `requestId` to the trace.

## 14. Troubleshooting Matrix

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| A and B have different `traceId` | Uninstrumented client, B does not consume W3C, proxy stripped `traceparent` | Use Boot `RestClient.Builder`, verify outbound/inbound W3C |
| A/B share `requestId` but differ in `traceId` | Custom header forwarded, tracing context lost | Check `traceparent`, bridge, sampler, and client auto-config |
| A/B have same `traceId`, different `spanId` | **Normal** | Inspect span tree to verify parent-child relationship |
| B lacks `requestId` while `traceId` matches | `X-Request-ID` is not part of W3C propagation | Add interceptor/baggage per contract |
| `traceId` is `missing` in controller | Tracer has no current span or tracing is disabled | Check dependencies/config/active observation/HTTP stack |
| Logs lack `traceId` while controller JSON has it | Log pattern/MDC scope or formatter omits MDC | Check `logging.pattern.correlation` and scope |
| Logs have `traceId` but trace UI is empty | Exporter off, sampling, collector unreachable, ingest/index delay | Check exporter/sampling/backend separately |
| `@Async` loses trace fields | Thread context not propagated | Add `ContextPropagatingTaskDecorator` + tests |
| WebFlux loses trace after scheduler hop | Reactor context propagation misconfigured | Set `spring.reactor.context-propagation=auto`, instrumented `WebClient` |
| Earlier client's `requestId` appears in later logs | Missing MDC cleanup | `try/finally` restore/remove |
| B shows multiple spans for one user action | Retries, async, redirects, multiple real HTTP calls | Check client attempts, traces, proxies |
| Span count doubled after adding `@Observed` | HTTP framework already instruments controllers | Remove duplicate annotations or tune `ObservationPredicate` |
| Trace ID propagates but parentage is wrong | Multiple propagators/tracestate or manual header injection | Let SDK inject; inspect HTTP client spans |
| Performance drops at 100% sampling | Trace data volume surge | Adjust sampling and collector sizing |
| Prometheus/Loki labels explode | Using unique `traceId`/`requestId` as metric tags | Use low-cardinality route/method/status |
| Browser cannot read `X-Request-ID` | Header not exposed by CORS | Add `Access-Control-Expose-Headers` in CORS policy |
| ID changes at proxy | Edge overwrite/trust policy differs from contract | Check each hop and ingress rules |
| `RestClient.create()` used in controller | Skips Boot customizers | Inject auto-configured `RestClient.Builder` |
| Trace splits across MQ | Broker producer/consumer missing context propagation | Instrument message headers, use span links |
| B returns 401/403 despite matching `traceId` | IDs are not authentication | Check authN/authZ; never authorize based on ID knowledge |
| ID matches format but is spoofed | Only syntax validated | Strip at edge, restrict trusted upstream |
| `SpringBootTest` lacks runtime exporter | Test tracing auto-config differs from production | `@AutoConfigureObservability`/test exporters |
| OpenTelemetry exporter logs connection errors | Wrong collector URL or collector not running | Verify HTTP/gRPC endpoint and network/auth |

### 14.1. Runbook for Investigating Lost Correlation

1. Obtain the **`requestId`** from the response header or support ticket. Identify route, timestamp, and frontend instance.
2. Search frontend logs by `requestId` and check if `traceId`/`spanId` were present in the controller.
3. Confirm A called B using an injected instrumented `RestClient.Builder` or `WebClient.Builder`.
4. Inspect outbound `traceparent` and `X-Request-ID` on the hop in **staging/authorized environments**; never dump secrets.
5. Inspect headers received by B, selected endpoint, source port/proxy rewrites, tracer bridge, and propagation consume settings.
6. If A/B `traceId` values differ, debug W3C/B3 compatibility, active tracing scope, and gateway header stripping.
7. If trace IDs match but the collector lacks spans, inspect sampling, exporter, collector, and trace backend ingestion separately.
8. If an async hop drops context, check `TaskDecorator`, Reactor context, and scheduled jobs/queues.
9. Check retries, circuit breakers, timeouts, 401/403 responses, and business IDs if a request spawned multiple attempts.
10. Lock in automated tests, standardize structured log schemas, disable sensitive debug flags, and secure observability systems.

## 15. Production Checklist

- **Contract:** agree on `X-Request-ID`/`X-Correlation-ID`, format, owner, response echo, and hop forwarding.
- **Boundary:** strip/override spoofed IDs at ingress; define clear `traceparent`/`tracestate`/`baggage` policies.
- **Instrumentation:** Actuator + tracer bridge, without duplicate tracer stacks or double observations.
- **HTTP clients:** Boot-injected `RestClient.Builder`/`WebClient.Builder`; avoid raw clients missing tracing.
- **Correlation:** `traceId`/`spanId` in logs, custom `requestId` in MDC with request-scope cleanup.
- **Async/reactive:** context propagation across executors/Reactor; test child tasks.
- **Sampling/Export:** authenticated/TLS collectors, sampling cost/PII retention, error-rate monitoring.
- **Metrics:** never use unique IDs as metric tags.
- **Downstream:** selectively propagate `traceparent` and `requestId`; manage retries/timeouts and idempotency separately.
- **Browser:** expose response `X-Request-ID` via CORS only where permitted.
- **Ops:** pivot from support request ID to logs, from log `traceId` to span tree, and from spans to failing downstream calls.
- **Security:** never perform authN/authZ using `requestId`/`traceId`; protect logs, traces, Actuator, and collectors.

## 16. Exercises and Answers

1. How does Request ID differ from `traceId` in contract?
2. How many hex characters are in a W3C `traceId`? How many in `spanId` and `parent-id`?
3. If two services share `traceId` but have different `spanId`, is propagation broken?
4. Should B's server span receive `parent-id` from A's server span or A's client span?
5. Why doesn't `X-Request-ID` propagate automatically alongside W3C `traceparent`?
6. Why does `RestClient.create()` miss automatic tracing compared to Boot's `RestClient.Builder`?
7. Why can a `traceId` appear in logs while being absent from the tracing UI?
8. Is 100% sampling always appropriate for production?
9. Why must `traceId`/`requestId` never be used as Prometheus labels?
10. Why must Java MDC be restored/removed in a `finally` block?
11. Does an `@Async` method automatically receive trace context from the Servlet thread?
12. Which property helps enable Reactor Context propagation?
13. Is `baggage` the same as `MDC` or span attributes?
14. Can a client-sent `requestId` be treated as trusted solely because it matches a regex?
15. If an HTTP client retries twice, will there always be only one B-server span?
16. In a cross-origin browser call, why might JavaScript fail to read the `X-Request-ID` response header?
17. Can `traceId` replace a JWT for authorization checks?
18. With a message queue, does trace context automatically travel inside a plain JSON body?
19. How does Trace UI parent-child inspection differ from simply comparing two JSON `traceId` fields?
20. Should you add `@Observed` to every already auto-instrumented MVC controller?
21. How does a business order ID help connect multiple traces?
22. When `traceId` prints as `missing`, what should you check?
23. Can `X-Request-ID` be used by default as a payment idempotency key?
24. Why disable the OTLP exporter in the demo when no collector exists, rather than disabling tracing?
25. If A/B logs share `requestId` but have different `traceId`s, where do you investigate first?

**Summary answers:** (1) Custom per-request ID vs. distributed trace ID. (2) Trace 32 hex; span/parent 16 hex. (3) No, that follows the span model. (4) Usually A-client. (5) Custom headers need an interceptor or baggage. (6) It bypasses Boot's auto-configured builder customizers. (7) Sampling/exporter/backend are separate from logs. (8) No, high cost. (9) Excessive cardinality. (10) Prevent request ID leaks across pooled threads. (11) Not by default; needs context propagation. (12) `spring.reactor.context-propagation=auto`. (13) No. (14) No, requires a trusted edge. (15) No, each attempt can produce a span. (16) Missing `Access-Control-Expose-Headers`. (17) No. (18) No, broker headers must be instrumented. (19) UI verifies parentage and timing; JSON equality only checks same trace. (20) Avoid double observations. (21) Business IDs persist across multiple events. (22) Tracing bridge, observation scope, and config. (23) No, idempotency requires its own contract. (24) Avoids collector connection errors while IDs still work. (25) Outbound `RestClient` builder and W3C propagation/extraction.

## 17. Official Documentation

- Spring Boot 3.5, **Tracing, Logging Correlation IDs, Propagating Traces, Baggage**: https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html
- Spring Boot 3.5, **Observability, Micrometer, Context Propagation, AsyncTaskExecutor**: https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html
- Spring Boot 3.5, **Common Application Properties**: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Boot 3.5, **Using Tracing in Tests**: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- W3C, **Trace Context Recommendation**: https://www.w3.org/TR/trace-context/
- W3C, **Baggage Specification**: https://www.w3.org/TR/baggage/
- Micrometer, **Tracing Reference**: https://docs.micrometer.io/tracing/reference/
- Micrometer, **Context Propagation Reference**: https://docs.micrometer.io/context-propagation/reference/
- OpenTelemetry, **Context Propagation**: https://opentelemetry.io/docs/concepts/context-propagation/
- Spring Framework, **RestClient and REST Clients**: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Spring Boot 3.5.16 release/OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/