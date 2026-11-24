# Limiting Detailed Diagnostic Logs in Production Environments

**Module:** Spring Boot - web-runtime  
**Parent Topic:** HTTP Observability

## 1. Context: Diagnosing HTTP Without Making the System Worse

A Spring Boot API handles 1,000 requests/second. When some requests start returning **401**, **403**, **500**, or p99 latency climbs, operations tries setting **`logging.level.root=TRACE`** to see what is happening. The outcome backfires: logs flood, collectors back up, CPU and I/O spike, and real errors drown in thousands of noisy lines. Worse still, HTTP headers, Cookies, JWTs, raw query strings, JSON bodies, or SQL bind parameters can land in logging infrastructure with completely different retention and access controls than your database.

**Rule:** production needs *continuous observability*, not *full-HTTP content recording*. Emit **minimal, structured, correlated signals**, enforce **privacy/security boundaries**, rely on metrics and traces for statistics, and raise `DEBUG` only narrowly with approval and a strict time limit.

This lesson covers **Spring Boot 3.x Servlet Spring MVC** under **HTTP Observability**. It includes:

1. Differences among **application logs**, **access logs**, **Spring MVC/Security diagnostics**, **audit logs**, **metrics**, **tracing**, and Actuator.
2. Proper log level configuration with **`logging.level.*`**, profiles, and **`spring.mvc.log-request-details=false`**.
3. Why you must avoid logging `Authorization`, `Cookie`, queries, payloads, or raw exceptions—even at `DEBUG`.
4. Tomcat access log patterns, path-variable hazards, and timestamp units.
5. Impact and protection of **`/actuator/loggers`** and **`/actuator/httpexchanges`**.
6. A **runnable Java 17+ example**: request ID, MDC, and an HTTP summary that never logs secrets.
7. JUnit tests with **`OutputCaptureExtension`** and secret canaries.
8. Sampling, log volume, performance, OpenTelemetry/Micrometer, proxies, Kubernetes, and multi-replica concerns.
9. A production runbook for short-window `DEBUG` enablement and rollback.

## 2. Logs, Metrics, Traces, and Audits Serve Different Roles

| Signal | Purpose | Examples to keep | Risks of excessive detail |
| --- | --- | --- | --- |
| **Application log** | Explain app events and errors | `errorCode`, operation, duration, correlation ID | Dumping DTOs/passwords/bodies, repeated stack traces. |
| **HTTP access log** | Know request method/route/status/time | `GET /api/items/{id} 200 16ms` | Raw paths, query strings, and PII-bearing IPs. |
| **Spring MVC DEBUG/TRACE** | Handler mapping and framework behavior | Mapping/exception handling | Headers, parameters, form data if request-details logging is enabled. |
| **Spring Security DEBUG/TRACE** | Auth, authorization, CSRF, filter chain | Security decision, status 401/403 | Huge volume; can log sensitive context. |
| **Audit** | Mandatory security/business transaction records | Authenticated subject ID, action, outcome | Must never rely on sampled `DEBUG` logs. |
| **Metrics** | Request rate, error rate, p95/p99 | `http.server.requests`, status, templated route | Raw URLs/`userId` in tags cause high cardinality. |
| **Distributed tracing** | Locate slow hops across services | `traceId`/`spanId`, dependency operation, timing | Span attributes containing tokens/PII. |
| **Actuator httpexchanges** | View recent exchanges when enabled | Method, status, timing | Exposes request history and sensitive metadata. |
| **Proxy/CDN logs** | Routing/edge/WAF/TLS issues | Routing outcome, status, edge latency | Copies of tokens/queries right before Spring. |

**Always-on signals** should be cheap and safe. Metrics with low-cardinality labels reveal trends; appropriately sampled tracing isolates slow hops; structured log events explain failures; and dedicated audit pipelines satisfy compliance. Never cram all four roles into a single `DEBUG` logger.

**Log volume is a resource budget**, not free capacity. Excessive logging adds request latency, saturates stdout/disks, stalls collectors, increases network egress, and inflates indexing bills. Manage log bytes/second and retention like any supporting SLO.

## 3. Classifying Which Data May Be Logged

The strongest rule is **allowlisting fields**, never dumping everything hoping regex redaction cleans up afterward.

| Field | Recommendation | Rationale |
| --- | --- | --- |
| Method, HTTP status, sanitized `errorCode` | Log as needed | Useful for grouping errors. |
| Route template, operation ID | Prefer | E.g., **`/api/users/{id}`**, not raw user IDs. |
| Duration, service, instance | Log with controls | Measures performance and isolates pods. |
| Request ID/`traceId`/`spanId` | Safe to log | Used for correlation, not auth. |
| `Authorization`, `Proxy-Authorization` | **Never log values** | Tokens, API keys, Basic credentials. |
| `Cookie`, `Set-Cookie` | **Never log values** | Session/refresh/CSRF cookies. |
| Request/response body | **Do not log by default** | Passwords, OTPs, PII, financial data, binary content. |
| Raw query string | **Do not log** | Emails, tokens, free-text searches. |
| Raw URI path | Restrict | Can hold tokens, emails, order/customer IDs. |
| Full headers | Do not dump | `User-Agent`/`Referer` hold PII; custom headers hold secrets. |
| SQL bind parameter values | Do not log in production | Leaks raw database data directly. |
| Uploaded filename/content | Do not log raw | Filenames contain PII or control characters. |
| Exception message/stack trace | Conditional | Messages can echo URLs/queries/SQL/PII. |
| Remote IP / Geo / `User-Agent` | Only with clear justification | May qualify as private data. |

Unsafe code:

~~~java
// Illustrative ANTI-PATTERN inside a component with Logger log.
log.debug("request headers={} body={}", requestHeaders, body);
log.error("remote call failed: {}", remoteResponseBody);
~~~

Safer code:

~~~java
// Illustrative event with controlled fields.
log.info("http.request route={} method={} status={} elapsedMs={}",
        "/api/orders/{id}", "GET", 200, 18);
log.warn("upstream.timeout dependency={} reasonCode={}",
        "inventory", "CONNECT_TIMEOUT");
~~~

These are two illustrative snippets, not a standalone Java program. Real systems obtain method/status/duration from the HTTP lifecycle. When recording a user identifier for auditing, authenticate the identity and follow your separate **audit log** schema, access rules, and retention.

### Why Post-Write Redaction Is Not Enough

Suppose the server logs a body and relies on the collector to mask `password` with a regex. Before that regex even runs, the raw body may already sit in:

- container stdout/stderr;
- JVM/appender files;
- sidecar agent buffers;
- staging log-shipping queues;
- backups/snapshots;
- crash reports or support tickets.

Regexes also miss newly added field names, nested JSON, URL-encoded values, exception messages, and non-standard token keys. The true fix is **never emitting secrets into log events in the first place**; collector sanitization is strictly defense-in-depth.

### Log Injection / Forging

A client can send CR/LF and control characters inside paths or headers. If an app concatenates raw input into text logs, one request can spoof multiple fake log lines. Use **structured encoders with escaping**, length limits, and allowlisted values instead of trusting client-supplied `Origin`, `User-Agent`, `X-Request-Id`, or query strings.

**JSON logs do not automatically equal safety**: encoders escape control characters yet faithfully persist a raw Bearer token if a developer puts it into a field.

## 4. Spring Boot 3.3: Log Levels and Key Properties

Spring Boot uses Logback by default with standard starters. Common levels:

| Level | Intent | Recommendation |
| --- | --- | --- |
| **ERROR** | Abnormal server failures | Log code/correlation; curb repeated stack traces. |
| **WARN** | Degraded state or notable condition | Pair with counters/rate limiting. |
| **INFO** | Lifecycle and major operational events | Production baseline. |
| **DEBUG** | Extra code-path detail | Enable briefly for narrow classes/packages only. |
| **TRACE** | Deep internal detail, high volume | Avoid broadly across production traffic. |
| **OFF** | Disables logger | Never disable mandatory audits. |

Configuration:

~~~properties
spring.application.name=http-logging-demo
logging.level.root=INFO
logging.level.com.example.httplog=INFO
logging.level.org.springframework.web=INFO
logging.level.org.springframework.security=INFO

# Prevent MVC from logging full headers/parameters at DEBUG/TRACE
spring.mvc.log-request-details=false

# Applies to reactive HTTP codecs when using WebClient/WebFlux
spring.codec.log-request-details=false

# Keep exception details/stack traces out of default HTTP error responses
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never
~~~

**`spring.mvc.log-request-details=false`** is a **Spring MVC Servlet** property. By default, Spring Framework masks request headers and parameters in framework `DEBUG`/`TRACE` logs because they may be sensitive. **`spring.codec.log-request-details=false`** governs reactive codec logging and does not replace the MVC property.

Neither property **stops custom Servlet Filters, outbound HTTP logging, Tomcat access logs, or application code explicitly printing bodies**. Never treat a single property as proof that data is safe across every layer.

### Never Enable `debug=true` / `trace=true` Fleet-Wide in Production

Spring Boot `--debug`, `debug=true`, `--trace`, and `trace=true` elevate logging on a broad set of core loggers. While they don't set literally every logger to `DEBUG`/`TRACE`, they still widen logging far beyond the target investigation scope.

Avoid:

~~~properties
# Production anti-pattern
logging.level.root=TRACE
logging.level.org.springframework=TRACE
logging.level.org.springframework.security=TRACE
~~~

Spring Boot includes `web` and `sql` logging groups spanning multiple packages, yet `logging.level.web=DEBUG` can still enable more loggers than needed. When investigating a class, target that specific logger; when debugging Security 403s, prefer staging/canary runs with reviewed logs.

### Do Not Log Every 4xx as `ERROR`

HTTP 400/401/403/404/429 can be normal outcomes of validation, security rules, or rate limiting. Track statuses via metrics and sanitized reason codes. Logging full stack traces on every 404/401 lets an attacker trigger a log storm with invalid traffic.

## 5. Tomcat Access Logs and Path/Query Risks

**Tomcat access logs** are separate from SLF4J application logs; pattern, rotation, and files are managed by the Tomcat container via **`server.tomcat.accesslog.*`**. Example suitable only for local/staging environments with safe routes:

~~~properties
server.tomcat.basedir=./tomcat-work
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=%t %m %U %s %D
server.tomcat.accesslog.rotate=true
server.tomcat.accesslog.max-days=3
~~~

Tomcat pattern explanation:

- **`%t`**: timestamp.
- **`%m`**: HTTP method.
- **`%U`**: request path, excluding query string.
- **`%s`**: status.
- **`%D`**: processing duration in **microseconds** in Tomcat.
- **`%r`**: HTTP request line, which can include the query string.
- **`%q`**: query string.
- **`%{Authorization}i`**: inbound `Authorization` header—do not log.
- **`%{Cookie}i`** or **`%{Set-Cookie}o`**: sensitive cookies—do not log.

**`%U` is still not completely safe!** For routes like `/password/reset/superSecretToken` or `/users/alice@example.test`, Tomcat records the concrete raw path rather than a route template. In production APIs with sensitive dynamic path segments, disable Tomcat path logging and use Spring HTTP summaries with **normalized route/operation keys**, or enforce redacted access logs at the edge.

With `basedir` above, files land under **`./tomcat-work/logs/`**. Leaving Tomcat on its default temp `basedir` can cause logs to vanish unexpectedly. Configure retention, volumes, file permissions, and log shipping; in Kubernetes, local files vanish when pods restart.

**Do not log the same request five times** across CDN, ingress, Tomcat, Servlet Filter, and WebClient without clear justification. Use correlation IDs to link necessary records and enforce a data budget.

## 6. Actuator `loggers` and Runtime Log-Level Changes

**`/actuator/loggers`** is a Spring Boot Actuator management endpoint that reads and modifies configured logger levels at runtime when enabled, exposed, and authorized. It is invaluable for temporary `DEBUG` without restarting, yet remains a **sensitive control plane**.

Per Boot 3.3 docs, **only `health` is exposed over HTTP/JMX by default**. Having the Actuator dependency does not expose `loggers`, `env`, `heapdump`, or `httpexchanges` automatically.

Example **strictly for local labs or a management plane secured with authentication/TLS/network isolation**:

~~~properties
management.endpoints.web.exposure.include=health,metrics,loggers
~~~

**Never place this on an unprotected public API.** When using Spring Security with a custom `SecurityFilterChain`, review rules covering Actuator because Boot's default security backs off. `POST` requests to `loggers` may receive **403** from default CSRF/security—never disable CSRF app-wide to work around it.

The commands below **illustrate localhost testing with zero real data**:

~~~bash
curl -sS \
  http://localhost:8080/actuator/loggers/com.example.httplog
~~~

~~~bash
curl -i -X POST \
  -H 'Content-Type: application/json' \
  -d '{"configuredLevel":"DEBUG"}' \
  http://localhost:8080/actuator/loggers/com.example.httplog
~~~

After investigating, clear the override:

~~~bash
curl -i -X POST \
  -H 'Content-Type: application/json' \
  -d '{"configuredLevel":null}' \
  http://localhost:8080/actuator/loggers/com.example.httplog
~~~

**Proper rollback:** `null` clears the configured override so the logger inherits its effective parent level—it does not automatically restore a previous explicit `configuredLevel`. Before changing anything, record the exact prior `configuredLevel`/`effectiveLevel` and restore that value; runtime changes apply only to **one instance/pod** and disappear on restart.

Never let operators leave `DEBUG` turned on: require an incident ticket, approval, owner, time window, TTL, log-volume monitoring, explicit rollback, and verification across all instances.

## 7. Actuator `httpexchanges`: Does Not Record Everything Automatically

**`/actuator/httpexchanges`** displays recent HTTP exchanges when an **`HttpExchangeRepository`** bean is present and the endpoint is enabled/exposed. Spring Boot ships **`InMemoryHttpExchangeRepository`**, retaining up to 100 exchanges by default with configurable capacity.

Illustrative Boot 3.3 API snippet (**omit from the main demo unless explicitly needed**):

~~~java
@Bean
HttpExchangeRepository httpExchangeRepository() {
    InMemoryHttpExchangeRepository repository =
            new InMemoryHttpExchangeRepository();
    repository.setCapacity(50);
    return repository;
}
~~~

Imports are **`org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository`**, **`InMemoryHttpExchangeRepository`**, and **`org.springframework.context.annotation.Bean`**. Place inside a scanned Spring `@Configuration`.

**Limitations:**

- It is not a full-body packet capture.
- Metadata can still include URIs, remote addresses, and headers/cookies depending on recording config; conduct a privacy review.
- In-memory records vanish on restart, do not aggregate across pods, and are not an audit store.
- A capacity of 50 only bounds record count, without sanitizing contents inside each entry.
- Exposing the endpoint to the Internet leaks metadata; lock down security if used.
- Metrics, traces, and safe event logs are better suited for long-term observability.

## 8. Metrics and Tracing Reduce the Need for `DEBUG`

With **Spring Boot Actuator + Micrometer** and an appropriate registry, HTTP server observations populate **`http.server.requests`**. HTTP client instrumentation populates **`http.client.requests`** when clients are built via managed builders/observability setup.

Questions answered without full request dumps:

- What are the request rate and 5xx rate by route/status?
- What is each route's p50/p95/p99 latency when histograms are enabled?
- Is an inventory or payment downstream timing out?
- Does one pod show higher errors than the rest?
- Are threads, connection pools, or GC saturating?
- Is time spent in ingress, Spring controllers, or upstream?

**Metric tags must stay low cardinality**: method, status/outcome, and route template/operation name. Never attach raw URLs, customer IDs, emails, JWTs, IPs, or `requestId` as tags, which bloat time series and risk data leaks.

**Traces** join hops via `traceId`/`spanId`. Tracing is not automatically leak-free either: raw SQL, baggage, or HTTP headers in span attributes can expose PII/secrets. Enforce allowlists and evaluated sampling.

**Never assume adding Actuator enables end-to-end tracing automatically.** You need a Micrometer Tracing bridge/exporter, instrumentation, and context propagation. Mandatory audit events must be stored separately so trace sampling or log sampling never drops them.

## 9. Runnable Demo: Java 17 + Spring Boot 3.3

We build an API receiving a POST body containing a **synthetic secret canary** while logging only **allowlisted route, method, status, duration, and a server-generated request ID**.

The project uses Spring Boot **3.3.13**, Java 17+, Maven, and embedded Tomcat. For new production apps, select a currently maintained Spring Boot branch; this example demonstrates logging policy only and adds no authentication to the demo API.

~~~text
http-logging-demo/
  pom.xml
  src/main/java/com/example/httplog/
    HttpLoggingDemoApplication.java
    SafeRequestSummaryFilter.java
    DiagnosticDemoController.java
  src/main/resources/
    application.properties
    application-local.properties
    application-prod.properties
  src/test/java/com/example/httplog/
    SafeHttpLoggingIntegrationTests.java
~~~

### 9.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>http-logging-demo</artifactId>
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

### 9.2. application.properties

~~~properties
server.port=8080
spring.application.name=http-logging-demo

logging.level.root=INFO
logging.level.com.example.httplog=INFO

spring.mvc.log-request-details=false
spring.codec.log-request-details=false

server.error.include-stacktrace=never
server.error.include-message=never
server.error.include-binding-errors=never

# Default public Actuator surface exposes only health.
management.endpoints.web.exposure.include=health

# Print requestId from Logback MDC on the request thread.
logging.pattern.level=%5p [req:%X{requestId}]
~~~

**MDC** (Mapped Diagnostic Context) provides thread-bound context, not request-body storage. Forgetting to clear MDC inside a Servlet thread pool causes subsequent requests to carry the previous request's ID.

### 9.3. application-local.properties

~~~properties
# Use locally with synthetic data only.
logging.level.com.example.httplog=DEBUG

# Local/staging or protected management environments only.
management.endpoints.web.exposure.include=health,metrics

server.tomcat.basedir=./tomcat-work
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=%t %m %U %s %D
server.tomcat.accesslog.rotate=true
server.tomcat.accesslog.max-days=3
~~~

### 9.4. application-prod.properties

~~~properties
logging.level.root=INFO
logging.level.com.example.httplog=INFO
logging.level.org.springframework.web=INFO
logging.level.org.springframework.security=INFO
logging.level.org.apache.catalina=INFO

spring.mvc.log-request-details=false
spring.codec.log-request-details=false
server.tomcat.accesslog.enabled=false

management.endpoints.web.exposure.include=health
~~~

The `prod` profile avoids default path-level access logs in this demo and hides `metrics`/`loggers` from the public API. Production systems often serve metrics over a private network with authentication—the rule is not "disable metrics everywhere", but "protect them properly".

### 9.5. Main Class

Create **`src/main/java/com/example/httplog/HttpLoggingDemoApplication.java`**:

~~~java
package com.example.httplog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpLoggingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpLoggingDemoApplication.class, args);
    }
}
~~~

### 9.6. SafeRequestSummaryFilter

Create **`src/main/java/com/example/httplog/SafeRequestSummaryFilter.java`**:

~~~java
package com.example.httplog;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class SafeRequestSummaryFilter extends OncePerRequestFilter {

    private static final Logger log =
            LoggerFactory.getLogger(SafeRequestSummaryFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();
        String oldRequestId = MDC.get("requestId");
        long started = System.nanoTime();

        request.setAttribute("safeRequestId", requestId);
        response.setHeader("X-Request-Id", requestId);
        MDC.put("requestId", requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            try {
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - started);

                String route = switch (request.getRequestURI()) {
                    case "/api/demo" -> "/api/demo";
                    default -> "other";
                };

                String method = switch (request.getMethod()) {
                    case "GET" -> "GET";
                    case "POST" -> "POST";
                    default -> "OTHER";
                };

                log.info(
                    "http.request route={} method={} status={} elapsedMs={}",
                    route, method, response.getStatus(), elapsedMs);
            } finally {
                // Prevent MDC requestId from leaking onto a reused thread.
                if (oldRequestId == null) {
                    MDC.remove("requestId");
                } else {
                    MDC.put("requestId", oldRequestId);
                }
            }
        }
    }
}
~~~

**Why is this safer than raw request logging?**

- Server generates a UUID `requestId`, never trusting an arbitrary client `X-Request-Id` as an identity.
- Never reads query strings, request bodies, `Authorization`, `Cookie`, or response bodies.
- Route key allows only **`/api/demo`** and **`other`**; PII inside arbitrary paths never prints verbatim.
- Method is also allowlisted to prevent strange client inputs in logs.
- Duration is in milliseconds, unlike Tomcat `%D` microseconds.
- MDC is always restored/cleared via nested `finally`, even if logging or the appender throws.
- The filter provides an **HTTP summary for synchronous requests**, not a full tracing solution.

**Limitations:** Servlet **async dispatches**, **SSE/`DeferredResult`**, and error dispatches follow different lifecycles. The initial filter `finally` may run before final response completion, and `response.getStatus()` may not reflect the final status if a container/error handler handles an exception later. Use **Micrometer HTTP server observations**, Tomcat connector metrics, or async-aware logging for SLOs and final latency. This demo demonstrates data safety, not complete coverage of every request type.

### 9.7. DiagnosticDemoController

Create **`src/main/java/com/example/httplog/DiagnosticDemoController.java`**:

~~~java
package com.example.httplog;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo")
public class DiagnosticDemoController {

    private static final Logger log =
            LoggerFactory.getLogger(DiagnosticDemoController.class);

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> get(HttpServletRequest request) {
        log.debug("demo GET handler selected");
        return Map.of(
                "message", "ok",
                "requestId", request.getAttribute("safeRequestId"));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> post(
            @RequestBody Map<String, Object> body,
            HttpServletRequest request) {

        // NEVER log input.toString(), headers, or body.
        log.debug("demo POST accepted fieldCount={}", body.size());

        return Map.of(
                "accepted", true,
                "fieldCount", body.size(),
                "requestId", request.getAttribute("safeRequestId"));
    }
}
~~~

**Filenames match public classes**, and root package `com.example.httplog` keeps scanning consistent. The controller persists no data; it simply shows POST JSON works cleanly without dumping bodies into logs. `fieldCount` is the top-level key count; in real APIs verify whether even returning that metadata is appropriate.

## 10. Running the Demo with Maven and curl

In the directory containing `pom.xml`, with Java 17+:

~~~bash
mvn clean test
mvn spring-boot:run -Dspring-boot.run.profiles=local
~~~

Open a second terminal:

~~~bash
curl -si http://localhost:8080/api/demo
~~~

Response JSON includes **`message=ok`** and the server-generated **`requestId`**. Because `requestId` changes per call, there is no fixed literal stdout. Header **`X-Request-Id`** carries the same UUID.

Send a POST using **synthetic canaries—never real secrets**:

~~~bash
curl -si \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer DEMO_TOKEN_NOT_REAL' \
  -H 'Cookie: JSESSIONID=DEMO_SESSION_NOT_REAL' \
  --data '{"comment":"hello","secret":"CANARY_SECRET_9D2F"}' \
  http://localhost:8080/api/demo
~~~

Expected logical response (`requestId` is generated at runtime):

~~~json
{
  "accepted": true,
  "fieldCount": 2,
  "requestId": "server-generated-uuid"
}
~~~

**`server-generated-uuid`** is an illustrative placeholder, not literal output. Application logs look similar to:

~~~text
INFO ... [req:UUID] ... SafeRequestSummaryFilter : http.request route=/api/demo method=POST status=200 elapsedMs=5
DEBUG ... DiagnosticDemoController : demo POST accepted fieldCount=2
~~~

Timestamps, UUIDs, thread log order, and `elapsedMs` vary. **None of** `CANARY_SECRET_9D2F`, `DEMO_TOKEN_NOT_REAL`, or `DEMO_SESSION_NOT_REAL` may appear in the demo's stdout/stderr.

Stop the local server and try the `prod` profile:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=prod
~~~

Under `prod`, the **`DEBUG demo POST accepted`** line disappears while the `INFO` summary still logs. Avoid running two processes on the same port. Never expose an unauthenticated/non-TLS demo to the Internet.

**Tomcat access logs** in the `local` profile write to **`./tomcat-work/logs/`** rather than the console. Do not conclude logs are missing just because stdout is silent; check the file path and `basedir`.

## 11. Automated Testing with Secret Canaries

Add integration test **`src/test/java/com/example/httplog/SafeHttpLoggingIntegrationTests.java`**:

~~~java
package com.example.httplog;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@ExtendWith(OutputCaptureExtension.class)
class SafeHttpLoggingIntegrationTests {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();

    @Test
    void canaryNeverAppearsInApplicationOutput(
            CapturedOutput output) throws Exception {

        String bodyCanary = "CANARY_SECRET_9D2F";
        String tokenCanary = "DEMO_TOKEN_NOT_REAL";
        String cookieCanary = "DEMO_SESSION_NOT_REAL";

        String json = "{\"comment\":\"hello\","
                + "\"secret\":\"" + bodyCanary + "\"}";

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + "/api/demo"))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + tokenCanary)
                .header("Cookie", "JSESSIONID=" + cookieCanary)
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.headers()
                .firstValue("X-Request-Id").isPresent());

        String logs = output.getAll();
        assertFalse(logs.contains(bodyCanary));
        assertFalse(logs.contains(tokenCanary));
        assertFalse(logs.contains(cookieCanary));
        assertTrue(logs.contains(
                "http.request route=/api/demo method=POST status=200"));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The test launches Spring Boot on **`RANDOM_PORT`**, sends a real POST with Java 17 **`HttpClient`**, verifies `X-Request-Id`, locates the summary log, and asserts none of the canaries appear in **`OutputCaptureExtension`** output.

**Clear limitations:** `OutputCaptureExtension` does not inspect CDNs, Nginx, collectors, sidecars, JVM agents, or separate Tomcat access log files. It covers only in-process console logging across tested scenarios. Supplement with code audits, sink-level canary tests, and formal log governance.

**Never put real tokens or passwords into tests.** Pair synthetic canaries with static code reviews, redaction checks, penetration testing, and alerts scanning logs for secret patterns.

## 12. MDC, Structured Logging, and Correlation

A production event can be shaped like:

~~~json
{
  "timestamp": "2026-11-08T08:30:00Z",
  "service": "catalog-api",
  "environment": "prod",
  "level": "INFO",
  "event": "http.request",
  "route": "/api/orders/{id}",
  "method": "GET",
  "status": 200,
  "duration_ms": 17,
  "request_id": "example-correlation-id"
}
~~~

This is an **illustrative schema**, not Boot 3.3's default JSON output. Use an appropriate Logback/Log4j2 structured encoder; do not copy newer Spring Boot 4.x properties assuming they exist in 3.3.

**MDC is thread-local**: when requests cross `@Async`, `CompletableFuture`, `Executor`, or Reactor/WebFlux, add proper context propagation. Never forward all baggage/MDC fields across trust boundaries indiscriminately, as they may carry sensitive data. With Micrometer Tracing/Observation configured, `traceId`/`spanId` appear in logs; never assume Actuator alone gives distributed tracing.

**Request IDs do not authenticate users.** If accepting `X-Request-Id` from a gateway, validate allowed characters and length (e.g., 8–64 ASCII letters/digits/hyphens/underscores) and enforce trust boundaries. The demo always generates a server-side UUID.

## 13. Servlet Async/Error Dispatches Change Measurements

Common Servlet dispatch types:

- **REQUEST**: initial HTTP dispatch.
- **ASYNC**: resumed processing for `DeferredResult`/`Callable`/streaming.
- **ERROR**: dispatch to error handler after an exception.
- **FORWARD/INCLUDE**: internal Servlet routing.

In the demo, **`OncePerRequestFilter`** logs during the initial synchronous dispatch. With SSE or `DeferredResult`, the filter can exit before the response truly ends. For exceptions unhandled by resolvers, status in `finally` may not yet be the final status. Therefore:

1. Rely on metrics and container instrumentation for final HTTP duration and status.
2. If writing a full custom filter, handle `asyncSupported`, dispatcher types, completion callbacks, MDC propagation, and cleanup.
3. Avoid unintentionally logging multiple dispatches as separate requests.
4. Test async endpoints, timeouts, and exception paths—not only synchronous GETs.
5. Never confuse initial HTTP dispatch time with end-to-end SSE/WebSocket connection lifetime.

For SLOs, **`http.server.requests`** and server connector metrics are far more reliable than a simple demo filter.

## 14. Sampling, Rate Limiting, and Log Budgets

Illustrative math:

- 1,000 requests/second.
- 10 log lines/request.
- 500 bytes/line.

That equals roughly **5 MB/second**, or **432 GB/day** before compression and indexing. Even one line/request is ~**43.2 GB/day**. These are theoretical capacity estimates, not live measurements.

Controls:

- **Sample** a fraction of success events without ever sampling away mandatory audits.
- **Rate-limit/deduplicate** repeated stack traces and warnings while retaining total counters.
- **Eliminate body logging and `DTO.toString()`**, capping max bytes/event.
- **Use bounded-queue async appenders** when throughput demands it; monitor dropped events and full-queue blocking behavior.
- **Enforce rotation, retention, storage quotas**, encryption, and IAM restrictions on log viewers.
- **Set metric alerts** on ingestion bytes/s, collector lag, disk pressure, CPU, and p99.
- **Audit how many layers** emit access logs simultaneously to eliminate needless duplication.
- **Enforce TTLs** on `DEBUG` overrides instead of leaving them permanently in production config.
- **Never flip `TRACE` fleet-wide** when 5xx spikes, or you risk causing a log storm right during an incident.

Logging slows APIs beyond disk I/O alone: formatting large JSON, serializing stack traces, buffering bodies, and stringifying complex objects all burn CPU and memory before reaching the appender.

## 15. Exceptions, Spring Security, and Outbound HTTP

### Spring Security

Spring Security `DEBUG`/`TRACE` helps diagnose **401, 403, CSRF, and filter chain** behavior. Enable only targeted loggers/packages with reviewed inputs, ideally on one pod or in staging. Never equate 401/403 with `ERROR`: many are expected security policy enforcements.

### Exceptions and Responses

**`exception.getMessage()` can be unsafe**: messages can contain SQL bind values, raw URLs, client input, or upstream response snippets. Emit sanitized error codes, permitted exception classes, correlation IDs, and rate-limited stack traces. Error responses returned to browsers must omit stack traces and exception messages.

### Outbound HTTP Clients

**RestClient, RestTemplate, WebClient, Reactor Netty, Apache HttpClient, and OkHttp** have their own interceptors/filters/wire loggers separate from inbound Servlets. Beware **`wiretap`** and `TRACE` when outbound calls carry `Authorization`, `Cookie`, or sensitive data. `spring.mvc.log-request-details=false` does not protect outbound client loggers.

When using **`http.client.requests`** metrics, set labels to logical dependency, templated route, and status—never raw URLs with query tokens.

### Database Logging

SQL query shapes can aid debugging, yet `TRACE` bind parameters leak PII and secrets; avoid enabling Hibernate/JDBC parameter logging across production just to debug one HTTP request.

## 16. Proxies, Containers, and Multi-Pod Topologies: Every Hop Has Its Own Policy

A request can be logged at:

~~~text
Browser
  |
  v
CDN / WAF / API Gateway
  |
  v
Nginx / Ingress / Service Mesh
  |
  v
Tomcat connector
  |
  v
Spring MVC Filter -> Controller
  |
  v
Logback -> stdout -> Collector -> SIEM
~~~

**Log masking inside Spring never scrubs data already logged by Nginx or a CDN.** A proxy recording raw request lines captures query tokens even if the backend logs only status and route. Audit every collection point, access control, retention limit, forwarding rule, and redaction rule.

**`Forwarded`/`X-Forwarded-For`** can be spoofed unless the edge strips untrusted headers. Never log or trust raw forwarded IPs for identity or authorization by default. IP addresses may also constitute personal data under privacy policy.

In Kubernetes:

- `stdout`/`stderr` are typically handled by the container runtime and collector.
- Tomcat file logs sit on the container filesystem and vanish on pod restarts.
- Runtime Actuator logger level changes affect only the single targeted pod behind a load balancer.
- Collector backpressure and log volume can throttle request throughput.
- Correlation IDs, service/instance labels, and UTC timestamps aid multi-pod correlation.
- Never place raw logs containing secrets into public buckets, ConfigMaps, image layers, or support tickets.

## 17. Runbook for Enabling `DEBUG` During an Incident

Suppose p99 latency on **`POST /api/payments`** rises. Follow a disciplined workflow:

1. **Form a specific hypothesis** (slow inventory gateway, exhausted pool, or auth filter?).
2. **Use metrics and traces first** to narrow down the failing dependency, pod, or route.
3. **Target the narrowest logger** along the suspect code path—never `root` or `org.springframework` `TRACE`.
4. **Audit the logger's messages** first to confirm it never prints bodies, headers, queries, or sensitive exception text.
5. **Obtain approval, incident ID, and owner**, setting a TTL (e.g., 5–10 minutes) on a specific subset of pods/traffic.
6. **Record the prior `configuredLevel`**, prepare a rollback plan, and audit the change.
7. **Apply via a secured management channel**, never a public Actuator endpoint.
8. **Watch log volume, CPU, and p99**, rolling back immediately if a log storm or leak begins.
9. **Restore exact original levels** across every affected instance and confirm output returns to baseline.
10. **Govern collected logs** (retention/quarantine if needed) and add safe sanitized events/metrics so the next incident needs `DEBUG` even less.

The 5–10 minute TTL is an operational policy example, not a Spring default.

## 18. Quick Diagnostic Table

| Symptom | Possible cause | Action |
| --- | --- | --- |
| Disk filling with logs | Broad `TRACE` / duplicate access logs | Lower level, rate limit, rotate, set quotas. |
| Many 401s, opaque Security logs | Missing context or generic entry point | Enable narrow Security `DEBUG` on synthetic/canary traffic; audit policy. |
| `Authorization` appears in logs | Custom filter/interceptor/wiretap or details logging | Stop collection, isolate/purge logs, handle secret leak. |
| App logs clean yet CDN leaks queries | Edge access logs record raw URI | Audit proxy log fields and retention. |
| `requestId` repeats on new requests | Missing MDC cleanup in thread pool | `finally` cleanup; test concurrency and async paths. |
| Filter logs 200 yet client receives 500 | Error dispatch / async lifecycle | Use lifecycle observations or final connector status. |
| `/actuator/loggers` returns 404 | Unexposed/disabled or blocked by security | Inspect management config; do not open publicly. |
| `POST loggers` returns 403 | AuthN/authZ or CSRF | Use authorized management flow; never disable CSRF app-wide. |
| `httpexchanges` is empty | Missing `HttpExchangeRepository` | Decide if needed; protect strictly if enabled. |
| High metrics cardinality | Raw URI/`userId`/`requestId` tags | Use route templates and low-cardinality labels. |
| WebClient `TRACE` leaks bodies | Wiretap / `ExchangeFilterFunction` logs | Disable and switch to sanitized events. |
| One pod has a different level | Actuator runtime change isn't cluster-wide | Update and roll back per instance. |
| Canary test passes yet prod leaks | Proxy, agent, or uncovered code path | End-to-end audit across collectors. |

## 19. Production Checklist

- [ ] Data classification and field allowlists exist for logs, metrics, traces, and audits.
- [ ] Root level is `INFO`/`WARN` matching SLOs, with no broad `TRACE`.
- [ ] **`spring.mvc.log-request-details=false`** and **`spring.codec.log-request-details=false`** set for the stack.
- [ ] `Authorization`, `Cookie`, `Set-Cookie`, API keys, JWTs, passwords, and raw bodies are never logged.
- [ ] Raw query strings are never logged, and path variables in Tomcat `%U` are audited.
- [ ] Safe `requestId`/`traceId` correlate requests without ever serving as authentication.
- [ ] MDC cleanup runs in `finally`, and async/reused threads are reviewed.
- [ ] Route templates or operation keys are used in HTTP summaries.
- [ ] Actuator exposure is minimized, especially `loggers`, `logfile`, `httpexchanges`, `env`, and `heapdump`.
- [ ] Every prod `DEBUG` session has an owner, approval, TTL, narrow scope, rollback, and log-volume monitoring.
- [ ] Log collectors enforce quotas, rotation, retention, encryption, and access controls.
- [ ] Sampling never drops mandatory audit events.
- [ ] Safe error codes are used, and HTTP responses never expose raw stack traces.
- [ ] Logging across gateways, Nginx, Tomcat, HTTP clients, databases, and tracing agents is reviewed.
- [ ] Canary secret tests run in CI, complemented by out-of-app layer audits.
- [ ] Log bytes/s, dropped events, CPU, disk, and p99 are monitored during level changes.
- [ ] Across Boot/Framework migrations, property names and defaults are re-verified.

## 20. Self-Check Questions

**1. Why is root `TRACE` unsuitable as a production baseline?**  
Because it creates massive log volume, burns CPU/I/O, and risks leaking sensitive data.

**2. Which MVC property keeps request details masked at `DEBUG`/`TRACE`?**  
**`spring.mvc.log-request-details=false`**.

**3. Does that property stop a custom Servlet Filter from logging the body?**  
No. Custom logging code must enforce allowlists itself.

**4. Does `%U` in Tomcat access logs automatically turn IDs into route templates?**  
No. It still logs the concrete path, which may contain PII.

**5. Should you log `Authorization` to debug a 401?**  
No. Rely on sanitized codes, correlation, and narrowly scoped security diagnostics.

**6. Should `/actuator/loggers` be exposed publicly?**  
No. It is an administrative control plane requiring authentication, authorization, and network protection.

**7. Does setting `configuredLevel` to `null` always restore the exact prior state?**  
No. It clears the override so the logger inherits its parent; save and restore any previous explicit level manually.

**8. Does `httpexchanges` automatically record requests just from having the Actuator dependency?**  
No. You need an `HttpExchangeRepository` bean plus proper enablement and exposure.

**9. Why does `requestId` not authenticate a user?**  
It exists purely for correlation; if accepted from clients, it can also be spoofed.

**10. Does the demo Filter measure accurate final elapsed time for SSE or `DeferredResult`?**  
Not guaranteed. It measures only the initial synchronous dispatch.

**11. Does a passing canary test prove the CDN isn't leaking data?**  
No. In-process tests do not see CDNs, agents, or external collectors.

**12. Should raw URIs be attached to `http.server.requests` tags?**  
No. Use route templates to avoid high cardinality and PII exposure.

**13. Is Micrometer tracing enabled automatically just by importing Spring Web?**  
No. Tracing requires instrumentation/bridge dependencies and backend configuration.

**14. Can you sample away security audits to save storage?**  
No, not when policy mandates retaining complete audit trails.

**15. When an incident affects only one upstream call, which logger should you enable?**  
The smallest relevant class/package logger with safe messages, a TTL, and a rollback plan.

## 21. Official Reference Sources

- **Spring Boot 3.3 – Logging:** https://docs.spring.io/spring-boot/3.3/reference/features/logging.html — `logging.level.*`, log groups, `DEBUG`/`TRACE`, MDC.
- **Spring Boot 3.3 – Application Properties:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/ — `spring.mvc.log-request-details`, `spring.codec.log-request-details`, `server.error.*`, Tomcat access logs.
- **Spring Framework – MVC Logging:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/logging.html — masking headers and request parameters.
- **Spring Security – Servlet Architecture:** https://docs.spring.io/spring-security/reference/servlet/architecture.html — logging for 401/403, filter chain.
- **Spring Boot 3.3 – Actuator Endpoints:** https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html — `loggers`, `httpexchanges`, exposure, and CSRF.
- **Spring Boot 3.3 – Observability:** https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html — Micrometer Observation, metrics/traces, cardinality.
- **Spring Boot 3.3 – Embedded Web Servers:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html — Tomcat accesslog config, directory, and time units.
- **Spring Framework – Servlet Filters:** https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html — filter lifecycle and forwarded header trust.
- **OWASP – Logging Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html — data exclusions, log injection, retention, and security.