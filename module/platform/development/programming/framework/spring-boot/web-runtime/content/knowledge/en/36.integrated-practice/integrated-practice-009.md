# Observing Requests Through Server and HTTP Client with Safe Tracing, Metrics, and Logging

When a Spring Boot API fails or slows down, you need to know which request is running, which step took time, and which downstream endpoint the HTTP client called. **Metrics** reveal error rates and aggregate latency; **distributed traces** map the tree of steps within a request; **logs** supply meaningful event details. Dumping full request/response bodies or `Authorization` headers for debugging risks leaking secrets, cookies, and personal data. This lesson shows how to emit all three signals while logging strictly allowlisted information.

This lesson belongs to **Spring Boot - web-runtime → Integrated Practice**, covering **Observing requests through server and HTTP client with safe tracing, metrics, and logging**. Stack: **Java 17, Spring Boot 3.3.13, Spring MVC/Tomcat, RestClient, Micrometer Observation, Micrometer Tracing Brave, Spring Boot Actuator, Prometheus registry, and Maven**. The demo runs without an external DB or HTTP server: inbound **`GET /api/quote`** calls outbound `RestClient` to **`GET /partner/price`** in the same JVM over the live bound port. Self-calling over localhost HTTP is strictly for lab demonstration—not recommended for internal in-process calls in production.

## 1. Learning Outcomes

1. Distinguish **metric, log, trace, span, traceId, spanId, parent span, and correlation ID**.
2. Use **`ObservationRegistry`** to instrument custom operations inside a Spring MVC request.
3. Understand **`http.server.requests`**, **`http.client.requests`**, and custom business metrics.
4. Use **Boot-managed `RestClient.Builder`, `RestTemplateBuilder`, and `WebClient.Builder`** so HTTP clients gain tracing and metrics.
5. Follow **W3C `traceparent`** from the inbound server to the outbound client and downstream server.
6. Read **`/actuator/metrics`** and **`/actuator/prometheus`**, understanding naming and label differences.
7. Locate correlated logs by `traceId`; distinguish trace IDs from auth tokens or idempotency keys.
8. Control **sampling, high-cardinality metrics, PII, secrets, log injection, and exporter privacy**.
9. Run the Maven project and **`@SpringBootTest(RANDOM_PORT)`** tests over real HTTP.
10. Understand why context drops across **`ExecutorService`, `@Async`, `CompletableFuture`, and Reactor**.
11. Export traces to Zipkin/OTLP when needed without confusing propagation with export.
12. Follow a consistent runbook to debug latency spikes or 5xx errors.

## 2. The Three Pillars of Observability

| Signal | Answers | Does Not Answer |
| --- | --- | --- |
| **Metrics** | Request rate, 5xx count, p95/p99 latency, saturation | Which specific spans a single request traversed. |
| **Traces** | Tree of steps, parent-child links, per-span duration | Every single request when sampling is active. |
| **Logs** | Detailed events and error categories linked by `traceId` | Traffic-wide latency distribution like a histogram. |

A **trace** represents an execution flow potentially spanning multiple services. Each **span** has its own `spanId` and shares a **`traceId`** within the trace. For a server calling downstream:

~~~text
External HTTP CLIENT
  |
  v
SERVER span: GET /api/quote         traceId=T
  |
  +-- custom observation: quote.price.lookup  traceId=T
       |
       +-- CLIENT span: GET /partner/price     traceId=T
            |
            +-- SERVER span: GET /partner/price traceId=T
~~~

This span tree is **illustrative**; instrumentation may emit additional spans, and sampling may hide unsampled traces in a UI. In this demo both HTTP server endpoints share the same service name because they run in one JVM. Once downstream moves to a separate service, trace propagation preserves `traceId` while distinguishing service names.

A **Correlation ID** in Boot 3.3 is commonly formatted from `traceId-spanId` in Logback MDC when Micrometer Tracing is active. A gateway-supplied **`X-Request-ID`** differs from `traceId`; **`Idempotency-Key`** prevents duplicate business POSTs and must never be replaced by `traceId`. Never use trace IDs for authentication or authorization.

## 3. Micrometer Observation and HTTP Instrumentation

### 3.1. ObservationRegistry

Boot Actuator provides `ObservationRegistry` and corresponding handlers. A custom observation:

~~~java
Observation.createNotStarted("quote.price.lookup", registry)
        .lowCardinalityKeyValue("flow", "price-lookup")
        .observe(() -> {
            // Business step.
        });
~~~

This is a snippet requiring imports `io.micrometer.observation.Observation` and `ObservationRegistry`. With a metrics handler, the observation creates a `Timer`; with a tracing bridge, it also opens a span. There is no need to generate manual UUIDs to fake tracing.

### 3.2. HTTP Server Metrics

Spring Boot 3.3 auto-instruments Spring MVC handlers under **`http.server.requests`**. Tags typically include **method, uri template, status, outcome, and exception** depending on the request. Paths should appear as templates like **`/orders/{id}`**, never raw order IDs or query strings.

Do not assume every exception caught by an `ExceptionHandler` populates the `exception` tag; inspect `status`/`outcome` and verify at runtime.

### 3.3. HTTP Client Metrics and Propagation

Spring Boot auto-configures **`RestClient.Builder`, `RestTemplateBuilder`, and `WebClient.Builder`** with observation customizers. Injecting the Boot-managed builder instruments outbound HTTP under **`http.client.requests`** and lets Micrometer Tracing inject trace context.

Instantiating a client manually:

~~~java
RestClient client = RestClient.create();
~~~

bypasses Boot's builder instrumentation. Never try to fix that by manually copying inbound `traceparent` to every outbound call: that corrupts parent-child span trees, blurs trust boundaries, or drops active span context.

### 3.4. W3C traceparent

Example header:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

It carries version, traceId, parent spanId, and trace flags. Spring Boot 3.3 supports **`management.tracing.propagation.consume/produce`**, defaulting to W3C outgoing. When two services mix B3 and W3C formats, align gateway/library settings rather than hardcoding trace IDs.

Incoming **`traceparent`/`tracestate`/`baggage` are untrusted inputs**. Never put `Authorization`/JWT/cookies/emails into baggage, never use `traceId` as a metric label or filename, and never treat trace headers as authentication. Tracer libraries should validate header syntax.

### 3.5. Sampling and Export

Boot 3.3 defaults trace sampling to **10%**. In the lab we set **`management.tracing.sampling.probability: 1.0`** so traces are always observable. **Sampling does not turn off HTTP metrics for unsampled requests.** You can see `traceId` in logs without seeing spans in Zipkin if no reporter is configured, the collector is down, or export fails.

## 4. Metric Cardinality and Logging Safety

**Low cardinality**: `method=GET`, `status=200`, `flow=price-lookup`, `partner=demo`, `outcome=success`.

**High cardinality (unsuitable for metric labels)**: `userId`, `email`, `UUID`, `traceId`, `sessionId`, raw URLs with order numbers. Each label combination creates a new time series, bloating memory/storage and leaking data. Micrometer's **`lowCardinalityKeyValue`** attaches tags to both metrics and traces; **`highCardinalityKeyValue`** attaches only to traces. Still, trace attributes get exported too, so high-cardinality tags must never contain PII.

**Never log directly:** `Authorization`, Basic/Bearer tokens, `Cookie`, `Set-Cookie`, CSRF tokens, passwords, OTPs, JWT claims, request/response bodies, emails, phone numbers, payment cards, raw URLs/queries containing tokens, multipart files, or stack traces holding sensitive payloads.

**Safe to log:** fixed event names, HTTP method/route template, status/outcome, controlled error category, bounded retry count, non-sensitive service/environment tags, and MDC trace IDs. Log user-controlled fields only after validation, sanitization, and allowlisting; attackers can inject newlines to perform **log injection**.

Safe pattern:

~~~java
log.info("quote_started operation=price_lookup");
log.info("partner_price_lookup tier={}", "book");
log.warn("partner_call_failed category=http_client");
~~~

Risky pattern:

~~~java
log.info("headers={}, body={}", headers, requestBody);
log.error("auth=" + bearerToken);
~~~

Never rely solely on regex redaction after logs hit a collector; **avoid emitting sensitive data at the source**. Enforce retention, access control, encryption/network security, and audits on log/trace backends, and never expose Actuator endpoints to the Internet unprotected.

## 5. Complete Project: Inbound Server → RestClient → Downstream Server

### 5.1. Project Tree

~~~text
observability-flow-demo/
  pom.xml
  src/main/java/com/example/obs/
    ObservabilityFlowApplication.java
    PartnerPriceResponse.java
    QuoteResponse.java
    PartnerClient.java
    PartnerController.java
    QuoteController.java
    ClientErrorAdvice.java
  src/main/resources/application.yml
  src/test/java/com/example/obs/FlowHttpIntegrationTest.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>observability-flow-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
            <artifactId>micrometer-tracing-bridge-brave</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
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

`starter-web` provides Tomcat and Spring MVC/RestClient; `starter-actuator` provides `ObservationRegistry`/metrics; the Brave bridge handles tracing context/MDC; the Prometheus registry exposes scrape metrics; `starter-test` brings JUnit and `TestRestTemplate`. The Spring Boot BOM manages compatible versions. No Zipkin reporter is included in this POM so the lab needs no external collector.

### 5.3. ObservabilityFlowApplication.java

~~~java
package com.example.obs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObservabilityFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ObservabilityFlowApplication.class, args);
    }
}
~~~

### 5.4. PartnerPriceResponse.java

~~~java
package com.example.obs;

public record PartnerPriceResponse(
        String sku,
        long priceCents,
        boolean traceparentPresent) {
}
~~~

### 5.5. QuoteResponse.java

~~~java
package com.example.obs;

public record QuoteResponse(
        String status,
        long unitPriceCents,
        boolean downstreamTraceContextPresent) {
}
~~~

Both Java records hold simulated data. The boolean `traceparentPresent` signals whether downstream **received the header**, without exposing the raw header or claiming spans were exported to a backend.

### 5.6. PartnerController.java — Server Endpoint Called by RestClient

~~~java
package com.example.obs;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class PartnerController {

    private static final Logger log =
            LoggerFactory.getLogger(PartnerController.class);

    @GetMapping("/partner/price")
    public PartnerPriceResponse price(
            @RequestParam String sku,
            @RequestHeader(
                name = "traceparent",
                required = false) String traceparent) {

        if (!sku.matches("[A-Z]{2,12}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid sku format");
        }

        String tier = sku.equals("BOOK")
                ? "book"
                : "standard";

        // tier is from a finite allowlist; never log raw SKU/headers.
        log.info("partner_price_lookup tier={}", tier);

        long cents = sku.equals("BOOK") ? 1599L : 999L;

        return new PartnerPriceResponse(
                sku, cents,
                traceparent != null && !traceparent.isBlank());
    }
}
~~~

**Safety note:** logs record only an allowlisted `tier`, never the `traceparent` string, raw SKU, tokens, or response body. In real domains, SKUs or product metadata may also be sensitive. Never treat boolean trace propagation as authentication.

### 5.7. PartnerClient.java — Instrumented Outbound RestClient

~~~java
package com.example.obs;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.web.servlet.context.ServletWebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PartnerClient {

    private final RestClient http;
    private final AtomicInteger port = new AtomicInteger(-1);

    public PartnerClient(RestClient.Builder builder) {
        // Builder is customized by Boot/Actuator for HTTP observation.
        this.http = builder.build();
    }

    @EventListener
    public void serverStarted(
            ServletWebServerInitializedEvent event) {
        port.set(event.getWebServer().getPort());
    }

    public PartnerPriceResponse fetchPrice(String sku) {
        int actualPort = port.get();

        if (actualPort < 1) {
            throw new IllegalStateException(
                    "HTTP server not ready");
        }

        return http.get()
                .uri(
                    "http://127.0.0.1:{port}/partner/price?sku={sku}",
                    actualPort, sku)
                .retrieve()
                .body(PartnerPriceResponse.class);
    }
}
~~~

**Explanation:**
1. Inject Boot-configured **`RestClient.Builder`**; do not call `RestClient.create`.
2. Use URI templates with `{port}` and `{sku}`; never concatenate raw input into URL strings.
3. **`ServletWebServerInitializedEvent`** captures the real bound port, including `RANDOM_PORT` tests.
4. The demo has no separate `management.server.port`, so the event port is the main web server port.
5. The HTTP client emits outbound client observations and injects W3C `traceparent` whenever tracing is active.
6. Production requires controlled service URLs, HTTP timeouts, connection pooling, retry policies, and avoiding loopback self-calls within the same JVM when unnecessary.

### 5.8. QuoteController.java — Server + Business Observation

~~~java
package com.example.obs;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class QuoteController {

    private static final Logger log =
            LoggerFactory.getLogger(QuoteController.class);

    private final PartnerClient partner;
    private final ObservationRegistry registry;

    public QuoteController(
            PartnerClient partner,
            ObservationRegistry registry) {
        this.partner = partner;
        this.registry = registry;
    }

    @GetMapping("/api/quote")
    public QuoteResponse quote(
            @RequestParam(defaultValue = "BOOK") String sku) {

        if (!sku.matches("[A-Z]{2,12}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid sku format");
        }

        log.info("quote_started operation=price_lookup");

        return Observation
                .createNotStarted("quote.price.lookup", registry)
                .lowCardinalityKeyValue("flow", "price-lookup")
                .observe(() -> {
                    PartnerPriceResponse price =
                            partner.fetchPrice(sku);

                    log.info(
                        "quote_completed outcome=success "
                        + "partner=demo");

                    return new QuoteResponse(
                            "OK",
                            price.priceCents(),
                            price.traceparentPresent());
                });
    }
}
~~~

**Why this instrumentation works:** Spring MVC already opens the HTTP server observation; custom `quote.price.lookup` is a nested **sub-operation**, not a duplicate server span. The client call executes inside that observation scope so tracing parents the client span cleanly underneath it. **`flow=price-lookup`** is a low-cardinality metric tag; never pass `sku`, `userId`, or `traceId`. Logs never print headers, raw input, or tokens. If downstream fails, the observation records the exception path and advice controls the HTTP response.

### 5.9. ClientErrorAdvice.java — Log Only Error Taxonomy

~~~java
package com.example.obs;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.RestClientException;

@RestControllerAdvice
public class ClientErrorAdvice {

    private static final Logger log =
            LoggerFactory.getLogger(ClientErrorAdvice.class);

    @ExceptionHandler(RestClientException.class)
    public ResponseEntity<Map<String, String>> clientFailed(
            RestClientException exception) {

        // Do not log exception.getMessage() or upstream body/URL.
        log.warn("partner_call_failed type={}",
                exception.getClass().getSimpleName());

        return ResponseEntity.status(
                HttpStatus.BAD_GATEWAY)
                .body(Map.of("error", "PARTNER_UNAVAILABLE"));
    }
}
~~~

502 represents an upstream HTTP failure in this lab; production may map to 503 or 504 depending on error type and contract. Never catch all `RuntimeException`s as 502, or internal bugs get masked. Use timeouts and metrics to separate upstream timeouts from 5xx responses.

### 5.10. application.yml

~~~yaml
spring:
  application:
    name: observability-flow-demo

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
  tracing:
    sampling:
      probability: 1.0
  observations:
    key-values:
      environment: "lab"

logging:
  level:
    com.example.obs: INFO
~~~

- `sampling=1.0` is **for the lab only**, not a blanket recommendation for production.
- `environment=lab` is a bounded-value common observation tag.
- `/metrics` and `/prometheus` reveal operational metadata; production needs a private management network and auth/TLS/RBAC.
- Boot 3.3 + Micrometer Tracing automatically attaches correlation IDs to logs; you do not need to manually extract `traceId` from request headers per log statement.
- Avoid enabling DEBUG/TRACE wire logging without auditing whether bodies or auth headers are printed.

## 6. Running the Project and Inspecting Output

### 6.1. Build and Start

Linux/macOS:

~~~bash
mvn clean package
java -jar target/observability-flow-demo-0.0.1-SNAPSHOT.jar
~~~

Windows:

~~~text
mvn.cmd clean package
java -jar target/observability-flow-demo-0.0.1-SNAPSHOT.jar
~~~

Send HTTP requests:

~~~bash
curl -i "http://localhost:8080/api/quote?sku=BOOK"
curl -i "http://localhost:8080/api/quote?sku=PEN"
curl -i "http://localhost:8080/api/quote?sku=bad123"
~~~

Expected HTTP 200 JSON for `BOOK`:

~~~json
{
  "status": "OK",
  "unitPriceCents": 1599,
  "downstreamTraceContextPresent": true
}
~~~

`PEN` returns `unitPriceCents=999`; `bad123` fails the uppercase regex and returns 400. `downstreamTraceContextPresent` is **expected to be true** with Boot's tracing bridge and `RestClient.Builder`; do not assume true if you alter tracing configuration.

### 6.2. Log Correlation

Check the console for:

~~~text
quote_started operation=price_lookup
partner_price_lookup tier=book
quote_completed outcome=success partner=demo
~~~

When tracing is active, these lines share the same `traceId` in MDC correlation, while `spanId` differs across the business, server, and downstream spans. **Never hardcode trace IDs or log timestamp ordering.** If MDC `traceId` is missing, inspect the bridge and context propagation before adding manual trace header logging.

### 6.3. Actuator Metrics

After running requests:

~~~bash
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/metrics/http.server.requests
curl -i http://localhost:8080/actuator/metrics/http.client.requests
curl -i http://localhost:8080/actuator/metrics/quote.price.lookup
~~~

- **`http.server.requests`** covers both `/api/quote` and `/partner/price`, since the demo handles two inbound HTTP requests per quote.
- **`http.client.requests`** tracks outbound `RestClient` calls.
- **`quote.price.lookup`** tracks the custom business observation.
- `COUNT`/`TOTAL_TIME`/`MAX` and tags reflect your active meters and registry.
- Do not expect a fixed `COUNT` if prior requests or Actuator scrapes ran.

Filter by tags when present:

~~~bash
curl -G \
  --data-urlencode "tag=method:GET" \
  --data-urlencode "tag=status:200" \
  http://localhost:8080/actuator/metrics/http.server.requests
~~~

### 6.4. Prometheus

~~~bash
curl -i http://localhost:8080/actuator/prometheus
~~~

Typical series names include:

~~~text
http_server_requests_seconds_count
http_client_requests_seconds_count
quote_price_lookup_seconds_count
~~~

Exact names and suffixes depend on the Micrometer Prometheus registry version; inspect actual output. Actuator metrics use dotted names in code, while Prometheus normalizes names with underscores and unit suffixes like `_seconds`. **Never expose the scrape endpoint publicly without security/network isolation.**

## 7. Real HTTP Integration Test

This test uses **`@SpringBootTest(RANDOM_PORT)`** rather than `MockMvc`, and `PartnerClient` captures the live port from `ServletWebServerInitializedEvent`. It verifies the HTTP server, outbound client, custom observation, and downstream `traceparent` arrival.

### 7.1. FlowHttpIntegrationTest.java

~~~java
package com.example.obs;

import io.micrometer.core.instrument.MeterRegistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FlowHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    MeterRegistry metrics;

    @Test
    void serverAndHttpClientAreObserved() {
        var response = http.getForEntity(
                "/api/quote?sku=BOOK",
                QuoteResponse.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(200);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().status())
                .isEqualTo("OK");
        assertThat(response.getBody().unitPriceCents())
                .isEqualTo(1599L);
        assertThat(response.getBody()
                .downstreamTraceContextPresent()).isTrue();

        assertThat(metrics.find("http.server.requests")
                .timers()).isNotEmpty();
        assertThat(metrics.find("http.client.requests")
                .timers()).isNotEmpty();
        assertThat(metrics.find("quote.price.lookup")
                .timers()).isNotEmpty();
    }

    @Test
    void invalidSkuReturns400() {
        var response = http.getForEntity(
                "/api/quote?sku=bad123",
                String.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Test notes:** `TestRestTemplate` returns 4xx responses cleanly for assertions; `RANDOM_PORT` binds a real Tomcat network connector. `true` proves the **`traceparent` header arrived** on the downstream request, not that an exporter shipped spans to a collector. `MeterRegistry.find(...).timers()` verifies server, client, and business timers registered once the operation finished. Never assert on random IDs or exact global counts. No Zipkin Docker container is needed to run this test.

## 8. Exporting Distributed Traces to Zipkin or OTLP

### 8.1. Propagation Is Not Export

| Observation | Proved | Not Proved |
| --- | --- | --- |
| `http.client.requests` appears | Outbound HTTP metrics instrumented | Whether `traceparent` or export works |
| `downstreamTraceContextPresent=true` | Outbound HTTP carried `traceparent` | Whether Zipkin received sampled spans |
| Zipkin displays span tree | Reporter/collector received spans | Whether 100% of requests are sampled |

### 8.2. Brave + Zipkin Reporter

The main POM includes only the bridge so the lab works standalone. To view spans in a UI, add:

~~~xml
<dependency>
    <groupId>io.zipkin.reporter2</groupId>
    <artifactId>zipkin-reporter-brave</artifactId>
</dependency>
~~~

Merge into your **existing `management` section**:

~~~yaml
management:
  zipkin:
    tracing:
      endpoint: "http://localhost:9411/api/v2/spans"
~~~

This is a YAML snippet—**never place two duplicate top-level `management` keys** in the actual file. If Docker is permitted:

~~~bash
docker run --rm -d --name zipkin-lab \
  -p 9411:9411 openzipkin/zipkin:latest
~~~

`latest` is for labs only; pin image versions in production. If the app runs in another container, `localhost` inside the app container does not point to the Zipkin container; use container networking/DNS. Open **http://localhost:9411** for the Zipkin UI, send requests, and filter by service **`observability-flow-demo`**.

**A trace may be missing** due to sampling, exporter network errors, collector auth/TLS, queue drops, or shutdown flushing. Never log raw request headers/bodies to troubleshoot an exporter.

### 8.3. OpenTelemetry and OTLP

Spring Boot 3.3 also supports **`micrometer-tracing-bridge-otel`** with **`opentelemetry-exporter-otlp`** configured under **`management.otlp.tracing.*`**, exporting to an OTel Collector, Jaeger, or Tempo. **Never combine the Brave and OTel bridges at once** trying to "cover everything"; pick one tracing stack to avoid double instrumentation.

## 9. Context Propagation Across Async and Reactive Boundaries

### 9.1. ExecutorService and @Async

Servlet request MDC and trace context do not automatically follow **`new Thread`, `CompletableFuture.commonPool`, or custom `ExecutorService`**. Worker logs can lose `traceId`, and outbound HTTP client spans can split into detached root traces. Spring Framework 6.1 supplies **`ContextPropagatingTaskDecorator`**:

~~~java
@Bean
ThreadPoolTaskExecutor observedExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(50);
    executor.setThreadNamePrefix("observed-");
    executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator());
    executor.initialize();
    return executor;
}
~~~

Place inside a Spring `@Configuration`, importing:
- `org.springframework.context.annotation.Bean`;
- `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`;
- `org.springframework.core.task.support.ContextPropagatingTaskDecorator`.

Task decoration adds overhead, especially for tiny jobs—apply it at the right boundaries. Never copy ThreadLocal MDC manually between threads without guaranteed cleanup, or old request context leaks across tasks.

### 9.2. Reactor/WebFlux

Spring Boot 3.3 supports automatic Reactor context propagation:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

For reactive clients, inject Boot's **`WebClient.Builder`** and verify context across `publishOn`, `subscribeOn`, and `flatMap`. Never call `block()` on Netty event loops. Enabling context propagation does not make JDBC or blocking `RestClient` non-blocking.

### 9.3. RestClient, RestTemplate, and WebClient Compared

| Client | Style | How Boot Instruments It |
| --- | --- | --- |
| `RestClient` | Fluent synchronous | Inject `RestClient.Builder`. |
| `RestTemplate` | Legacy synchronous | Inject `RestTemplateBuilder`. |
| `WebClient` | Reactive | Inject `WebClient.Builder`. |
| Raw JDK `HttpClient` | JDK HTTP | Needs explicit instrumentation for Boot-style tracing. |
| Raw Apache `HttpClient` | Low-level | Requires integration/agent; raw calls aren't traced by default. |

A Spring MVC app can use `WebClient` for outbound HTTP **without switching the web server to WebFlux**. When both starters are on the classpath in Boot 3.3, Servlet/MVC wins by default; check your active runtime stack during refactors.

## 10. Dashboards and Investigation Runbook

### 10.1. Minimum Dashboard

~~~text
Service: observability-flow-demo
  - HTTP RPS by uri template + method
  - HTTP 5xx ratio and outcome
  - p50/p95/p99 latency (when histograms are enabled)
  - Outbound http.client.requests by target/status
  - quote.price.lookup COUNT/duration
  - JVM heap, GC, CPU, threads, and connection pools
  - Trace UI filtered by service/time/status
  - Logs filtered by traceId and fixed event names
~~~

p99 cannot be derived accurately from averages; enable Micrometer distribution histograms or SLO buckets and query via Prometheus. Avoid enabling histograms on every metric unnecessarily due to series cardinality and storage cost.

### 10.2. Incident Investigation Workflow

1. Identify the service, deployment version, route template, HTTP method, and time window.
2. Inspect **`http.server.requests`**: when did errors or latency spike, and on which route?
3. Inspect **`http.client.requests`**: did downstream status codes or latency rise at the same time?
4. Pull a slow or failing trace to inspect the server span, business span, and client span durations.
5. Filter safe log events by `traceId`: `quote_started`, `partner_price_lookup`, `quote_completed`, `partner_call_failed`.
6. If client spans are missing, check `RestClient.Builder`, tracer bridge, propagation config, sampling, and exporter.
7. If spans break across async executors, verify task decorators and Reactor propagation.
8. Cross-check CPU, GC, DB, and pools against latency; never assume a slow client span is always downstream's fault.
9. Verify no secrets or PII leaked into logs, traces, or metric labels.
10. Fix the root cause, add a regression/integration test, and update dashboards and runbooks.

### 10.3. Sampling Bias

Sampled traces do not represent 100% of traffic. At 0.1 probability, a rare 5xx may produce zero sampled traces in a short window. **Metrics** measure total error rates accurately; **traces** explain step-by-step execution. If using tail-based or error sampling in a collector, evaluate cost, privacy, and alignment with application sampling.

## 11. Troubleshooting

| Symptom | Cause | Check / Fix |
| --- | --- | --- |
| Missing `http.client.requests` | Used `RestClient.create` or client not invoked yet | Inject Boot `RestClient.Builder`, trigger quote, re-check |
| Server metrics exist, `traceparentPresent=false` | Missing bridge, propagation config, or builder | Check POM, W3C config, client construction |
| Logs missing `traceId` | No active span or MDC context | Check Micrometer bridge and log correlation pattern |
| Downstream `traceId` changes | Gateway stripped header or async context dropped | Check `traceparent`, B3/W3C alignment, and async boundaries |
| Zipkin UI empty | Missing reporter, collector failure, or sampling | Check exporter endpoint, network, and queue drops |
| `/actuator/prometheus` returns 404 | Missing registry or exposure setting | Add `micrometer-registry-prometheus` and management exposure |
| Metric series explosion | Raw URI, ID, or PII tag | Use URI templates and finite tags |
| HTTP 502 on `/api/quote` | `RestClient` exception | Check safe log category and network/downstream status |
| 400 creates no client metric | Invalid SKU rejected before outbound call | Expected behavior |
| Server COUNT exceeds quote count | Demo also handles inbound `/partner/price` | Filter by `uri` template |
| `@Async` loses `traceId` | Thread context not propagated | Add `ContextPropagatingTaskDecorator` |
| WebFlux spans disconnect | Reactive context propagation off or wrong builder | Enable Boot property and use `WebClient.Builder` |
| p99 missing | Histograms / SLO buckets disabled | Enable distribution config on key timers |
| Actuator returns 401/403 | Security enabled on endpoints | Authenticate via management access—never expose publicly |
| User token appears in logs | Wire logging or request body dump enabled | Disable dangerous logging; allowlist/redact at source |
| Duplicate spans | `@Observed` overlaps HTTP auto-instrumentation or agent | Remove duplicate instrumentation |
| Tracing backend missing a request | Unsampled or exporter dropped | Never claim the request never ran |

## 12. Anti-Patterns

1. **Logging `Authorization`, `Cookie`, or request bodies** to debug errors — severe data-leak risk.
2. **Using `userId`, `traceId`, `UUID`, or raw URIs as metric labels** — explodes cardinality.
3. **Calling `RestClient.create()` manually** and expecting Boot auto-instrumentation.
4. **Logging raw `traceparent`/`baggage`** to debug propagation — unnecessary.
5. **Using `traceId` for authentication or as an idempotency key** — wrong semantics.
6. **Putting `@Observed` on an HTTP controller already auto-instrumented** without noticing duplicate observations.
7. **Running 100% tracing in high-volume production without bounds** — overloads collectors and storage.
8. **Inferring p99 from averages** — statistically invalid.
9. **Logging `exception.getMessage()` containing raw URLs/queries/bodies** — privacy risk.
10. **Exposing all Actuator endpoints to the Internet** — leaks operational internals.
11. **Concluding "no trace means no request happened"** — sampling drops traces.
12. **Copying MDC `ThreadLocal` across threads without cleanup** — leaks context between requests.

## 13. Exercises

### Exercise 1 — Trace Tree
Sketch the 4 sample spans, distinguish `traceId` from `spanId`, and explain why both client and downstream emit observations.

### Exercise 2 — Server/Client Metrics
Call 10 valid quotes and 3 invalid SKUs, then compare `COUNT` for inbound, outbound, and custom observations. Explain why client `COUNT` excludes requests rejected before the outbound call.

### Exercise 3 — Safe Logging
Send a dummy `Authorization` header in the lab and verify logs omit the token. Define an allowed log-field list and describe how to prevent newline log injection.

### Exercise 4 — Broken Propagation
Temporarily replace Boot-managed `RestClient.Builder` with `RestClient.create` in a copy of the lab and inspect metrics/`traceparent`. Restore the builder and re-test.

### Exercise 5 — Sampling
Enable Zipkin and lower sampling from `1.0` to `0.1`. Compare exported trace counts against total metrics; do not expect small samples to match exactly 10/100.

### Exercise 6 — @Async
Submit a task to an executor without a context decorator and inspect log `traceId`. Then add `ContextPropagatingTaskDecorator` and compare.

### Exercise 7 — WebClient
Use Boot-managed `WebClient.Builder` inside a Spring MVC app and verify HTTP client metrics. Never block on a WebFlux event loop if switching the server to reactive.

### Exercise 8 — Observability Incident
Simulate a controlled downstream 503; verify advice returns 502 and logs only the error class. Walk from metric → trace → log to pinpoint the failing hop.

### Exercise 9 — Histogram Budget
Pick 2 critical endpoints and design p95/p99 histogram/SLO buckets with bounded labels. Calculate how many time series a new label multiplies.

### Exercise 10 — Privacy
List data that must never enter baggage, logs, traces, or metrics; define reader access and retention. Never test with real customer data.

## 14. Pre-Production Checklist

- [ ] `http.server.requests` emitted for inbound requests.
- [ ] `http.client.requests` emitted for outbound calls via Boot-managed builders.
- [ ] `traceparent` propagation tested over real HTTP.
- [ ] Custom observations have stable names and low-cardinality tags.
- [ ] No `userId`, `traceId`, `email`, `session`, or raw URLs in metric labels.
- [ ] Logs contain zero `Authorization`, `Cookie`, `Set-Cookie`, API keys, tokens, bodies, or PII.
- [ ] Logs emit error taxonomy and fixed event names, not raw exception messages.
- [ ] Trace/span IDs used strictly for correlation, never auth.
- [ ] Zipkin/OTLP exporter secured with TLS/auth, monitoring queues and dropped spans.
- [ ] Sampling policy tuned to traffic/cost/privacy—not 100% everywhere.
- [ ] `/actuator/metrics` and `/actuator/prometheus` restricted to protected management networks.
- [ ] Histograms/SLO buckets enabled selectively for key endpoints.
- [ ] Async/Reactor context propagation tested without duplicate spans.
- [ ] `@SpringBootTest(RANDOM_PORT)` verifies metrics and HTTP propagation.
- [ ] Logs and traces enforce retention and access controls.
- [ ] Dashboards, alerts, and a metric → trace → safe log runbook exist.
- [ ] Regression tests run on Spring Boot, Micrometer, or HTTP client upgrades.

## 15. Self-Check

**Do metrics contain individual `traceId`s?** No; metrics aggregate counts/timings and must avoid high-cardinality IDs as labels.

**What do two spans in the same trace share?** The `traceId`, while each has its own `spanId`.

**Why can `RestClient.create` lack tracing?** It bypasses Boot-managed builders and customizers.

**Does 0.1 sampling drop 90% of HTTP metrics?** No; trace sampling is separate from metrics.

**Does successful propagation mean Zipkin received the trace?** No; exporters, collectors, and sampling also matter.

**Can `WebClient` be used inside an MVC app?** Yes, via Boot's `WebClient.Builder`; that does not switch the web server to WebFlux.

**Do async threads inherit MDC automatically?** Not always; propagate context explicitly across async boundaries.

**Why avoid logging `Authorization`/cookies?** It leaks credentials, sessions, and personal data.

**Why avoid using user IDs as metric tags?** High-cardinality time-series explosion and privacy risk.

**What should you do when p99 spikes?** Narrow the scope via metrics, locate the slow hop via traces, and explain it with traceId-correlated safe logs.

## 16. Official References

1. [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html): `ObservationRegistry`, cardinality, Reactor context.
2. [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html): `http.server.requests`, `http.client.requests`, managed HTTP client builders.
3. [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html): Brave/OTel bridges, sampling, MDC, propagation, exporters.
4. [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): metrics/prometheus and security.
5. [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `RANDOM_PORT`/`TestRestTemplate`.
6. [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html): custom observation APIs.
7. [Micrometer Metrics](https://docs.micrometer.io/micrometer/reference/concepts.html): labels, meters, `Timer`.
8. [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): spans/tracers.
9. [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent`, `tracestate`.
10. [OpenTelemetry Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): distributed context.
11. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): safe logging, injection, sensitive data.
12. [Prometheus Metric Naming](https://prometheus.io/docs/practices/naming/): labels and cardinality.

**Conclusion:** To observe Spring Boot requests end to end across server and HTTP clients, rely on **`http.server.requests`** for inbound traffic, **`http.client.requests`** for outbound calls, **`ObservationRegistry`** for business steps, **`traceId`** to link spans and log events, and **allowlisted safe logging** to explain failures. Never dump headers/bodies or put user/trace IDs into metric tags. During incidents, move from **metric → trace → correlated safe log → root cause**, then add regression tests and enforce telemetry privacy policies.