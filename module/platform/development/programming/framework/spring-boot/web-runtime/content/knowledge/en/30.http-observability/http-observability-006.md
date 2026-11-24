# Observing Handled Errors and Distinguishing Them from Auto-Recorded Errors

## 1. Why Can an HTTP 500 Appear with `error=none`?

Suppose a Spring Boot application encounters an error while handling a request. The controller throws `InventoryUnavailableException`; an `@ExceptionHandler` catches it and returns a `ProblemDetail` JSON response with HTTP status **503**. The user knows the request failed. Application logs may also show the exception. Yet the `http.server.requests` chart in Micrometer may show **`error=none`** for that request.

This is not necessarily a bug in the metrics system. In **Spring Framework 6.1 / Spring Boot 3.3**, HTTP server observation automatically records an exception as an **observation error** when the exception **is unhandled by the web framework** and propagates out to the instrumentation boundary. An exception handled by `@ExceptionHandler`, `@ControllerAdvice`, or a `ProblemDetail` mechanism may leave **no escaping exception** for the filter/server observer to see. The response still carries status 4xx/5xx, while the observation context remains unmarked as an error.

This lesson distinguishes four things often conflated:

1. **An exception occurring** in business/controller/handler code.
2. **A handled exception** converted into an HTTP response (e.g., 404, 422, 500, 503).
3. **The HTTP response status/outcome** actually received by the client.
4. **The observation error** recorded on Micrometer's `Observation.Context`, which drives metric tags and—when tracing is enabled—related span error markers.

We also distinguish **ERROR logs** from observation errors: writing a log line does not automatically set the `error` tag or mark a trace span as failed.

**Scope:** Spring Boot 3.3.13, Spring Framework 6.1.x, Micrometer Observation, and Java 17+. When upgrading to Spring Framework 7.x or major Micrometer/OpenTelemetry releases, verify semantic conventions and APIs for that version; this lesson intentionally stays within one version family to avoid projecting newer behaviors onto older systems.

## 2. Model: Logs, Metrics, Traces, and HTTP Responses Are Separate

```text
                         HTTP request
                              │
                    Observation starts
                              │
                     Controller / Service
                              │
                 Did an exception occur?
                      ┌───────┴────────┐
                      │                │
                     No               Yes
                      │                │
                HTTP 2xx...      Exception handling
                                       │
                     ┌─────────────────┴─────────────────┐
                     │                                   │
             Handled internally                  Escapes to the
            @ExceptionHandler/...              instrumentation layer
                     │                                   │
              HTTP 4xx/5xx                         Auto-record error
                     │                             if observed
              context.error may be null                  │
                     │                                   │
     Optional context.setError(exception)                │
                     │                                   │
                     └─────────────────┬─────────────────┘
                                       │
                              Observation ends
                                       │
                     ┌─────────────────┴─────────────────┐
                     ▼                                   ▼
              Metrics tags                         Tracing (if enabled)
           status, outcome, error                span/error association
                                       │
                                Logs are a separate channel
```

An unhandled exception can pass through instrumentation automatically, yet **how the web container, error dispatch, reactive pipeline, and filters execute** determines which observer actually sees the error. Conversely, a handled exception can legitimately return 500 without marking the observation unless explicit action is taken.

Never infer from `status >= 500` that `context.getError() != null`. Likewise, never infer from `error != none` that the status must be 500: a developer can mark a handled business exception that returned **HTTP 404**. The two signals carry **different meanings**.

### 2.1. A Counterexample Table

| Request | Behavior | HTTP status | Typical observation error | Meaning |
|---|---|---:|---|---|
| `GET /demo/ok` | No exception | 200 | `none` | Normal successful request |
| `GET /demo/not-found` | Throws exception, `@ExceptionHandler` maps to 404, unmarked | 404 | `none` | Handled client error |
| `GET /demo/handled-500` | Real exception handled into 500, unmarked | 500 | `none` | **Status 500 does not imply an error tag** |
| `GET /demo/marked-503` | Handled exception, handler calls `context.setError(ex)` | 503 | `InventoryUnavailableException` | Explicitly marked |
| `GET /demo/unhandled` | Exception escapes pipeline, seen by filter | Usually 500 | Exception type when observed | Auto-recorded per server/error dispatch |
| Handler directly returns `ResponseEntity.status(503)` | No exception thrown | 503 | `none` | HTTP failure status without Java exception |
| Handler calls `setError(ex)` then returns 200 | Success response, error context holds exception | 200 | Exception type | Can produce confusing telemetry; avoid unless justified |

These illustrative `error` values assume HTTP server instrumentation is enabled with Framework 6.1 default conventions. Custom observation conventions can alter tags; missing dependencies/registries or sampling/observation predicates can omit measurements altogether.

## 3. How Does Spring Boot 3.3 Create HTTP Server Observations?

Spring Boot Actuator integrates **Micrometer Observation** and HTTP instrumentation auto-configuration. An observation has a **name**, **lifetime**, **context**, and **key-values**. With appropriate `ObservationHandler`s registered, it feeds metrics and traces. Boot defaults the HTTP server observation name to:

```text
http.server.requests
```

In Prometheus, a Micrometer timer exports as series like `http_server_requests_seconds_count`, `..._sum`, `..._max` depending on registry/config. Names vary across backends; refer to the Java-side observation/Micrometer meter name before deciding PromQL names.

**In Servlet/MVC**, Spring Framework provides `org.springframework.web.filter.ServerHttpObservationFilter`. Boot/Actuator configures the filter to start and close HTTP request observations when instrumentation is active.

**In Spring WebFlux**, observation is wired into the reactive `HttpHandler`/`WebHttpHandlerBuilder` (not a Servlet filter) using `org.springframework.http.server.reactive.observation.ServerRequestObservationContext`. Boot configures this for reactive runtimes when observation infrastructure is present.

Same observation name, yet the **two request context types live in different packages**:

| Servlet/MVC | WebFlux/Reactive |
|---|---|
| `org.springframework.http.server.observation.ServerRequestObservationContext` | `org.springframework.http.server.reactive.observation.ServerRequestObservationContext` |
| `ServerHttpObservationFilter.findObservationContext(HttpServletRequest)` | `ServerRequestObservationContext.findCurrent(exchange.getAttributes())` |
| Servlet filter scope | Reactive HTTP exchange/pipeline |
| `HttpServletRequest` | `ServerWebExchange` |
| `@ExceptionHandler` can accept `HttpServletRequest` | `@ExceptionHandler` can accept `ServerWebExchange` |

Both expose `setError(Throwable)` on the observation context. **Never import the wrong package** or assume a WebFlux handler can inject Servlet `HttpServletRequest`, or vice versa.

### 3.1. Required Dependencies

In typical Spring Boot applications:
- `spring-boot-starter-web` or `spring-boot-starter-webflux`: web runtime.
- `spring-boot-starter-actuator`: manages and auto-configures Micrometer observations/metrics.
- `micrometer-registry-prometheus`: optional, to expose/export Prometheus metrics.
- Micrometer Tracing bridge + tracer/exporter: **only when distributed traces are desired**.

**Adding Actuator alone does not guarantee traces reach a tracing backend.** Metrics timers may exist while trace exporters are missing; conversely, logs may work while metrics instrumentation is disabled. Inspect dependencies and configuration for each signal separately.

Spring Boot 3.3 also offers `management.observations.http.server.requests.name` to rename the observation, and `management.observations.enable.*` to disable observations by prefix. If renamed, adjust meter queries accordingly.

## 4. Default Key-Values: `error`, `status`, `outcome`, `uri`

In Spring Framework 6.1, default HTTP server observation records **low-cardinality** keys:

| Key | Illustrative value | What it represents |
|---|---|---|
| `method` | `GET` | HTTP method |
| `status` | `200`, `404`, `503`, `UNKNOWN` | Response status sent/detected |
| `outcome` | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR` | HTTP 2xx/4xx/5xx status group |
| `uri` | `/demo/marked-503`, `NOT_FOUND`, `UNKNOWN` | Route pattern or low-cardinality fallback |
| `error` | `none`, `InventoryUnavailableException` | Simple class name of exception recorded on observation |
| `exception` | Similar to `error` | **Deprecated** in 6.1 conventions; avoid building new dashboards exclusively on it |

Specifically:
- `status=503` reports the **HTTP result**, not proof a Java exception passed through instrumentation.
- `outcome=SERVER_ERROR` derives from 5xx status; it does not imply `error` was set.
- `error=none` merely indicates no `Throwable` was attached to the observation—**not that business code never threw an exception**.
- `uri` holds the matched route pattern (e.g., `/orders/{id}`), keeping cardinality low.
- `http.url` is listed in Framework docs as a **high-cardinality key**. It fits tracing in some setups, whereas raw URLs/queries/user IDs must never go into metric tags that explode series counts.

**Important naming note:** Spring Framework 6.1 includes both `error` and the deprecated `exception` key per docs. Do not confuse legacy Boot 2.x `WebMvcMetricsFilter`/`exception` logic with Boot 3.x observations. Always inspect the actual tags returned by your registry and check semantic conventions for your running version.

### 4.1. Metrics, Tracing, and Logs View Requests Differently

```text
HTTP 503
  ├── Metric: http.server.requests{
  │       status="503",
  │       outcome="SERVER_ERROR",
  │       error="InventoryUnavailableException",
  │       uri="/demo/marked-503"
  │    }
  ├── Trace/span: error/event via tracing handler
  │    if bridge, sampling, and exporter are configured
  └── Log: WARN/ERROR per application logging policy
```

These three branches do not have an automatic one-to-one mapping:
- An `ERROR` log written in controller advice does not affect the Observation.
- An HTTP 500 request can have `error=none` if the exception was resolved.
- An HTTP 404 request can record a `Throwable` if the application explicitly marks it.
- Recording an error on the observation does not guarantee a tracing backend received a span (sampling or exporter may be missing).

## 5. What Does "Auto-Recorded Error" Mean in MVC?

Spring Framework explicitly documents that `ServerHttpObservationFilter` treats an exception as an error when it **is not handled by the web framework** and **bubbles up to the filter**. Visually:

```text
Controller throws Exception
         │
         ▼
DispatcherServlet
         │
         ├── @ExceptionHandler / HandlerExceptionResolver handles into ResponseEntity
         │          │
         │          └── no exception escapes outward
         │                   → filter usually never sees original Java error
         │
         └── unhandled exception
                    │
                    ▼
           reaches Servlet filter
                    │
                    ▼
           context.setError(...) automatically by instrumentation
```

**Servlet observation layer boundary:** filters operate according to filter ordering and handling downstream of them. An error handled by **Servlet container error handling** at a lower level or in a filter outside the observation scope does not automatically have an active span/context. Spring Framework notes that container-level error observation requires container-specific instrumentation (such as a Tomcat Valve), distinct from HTTP request observations.

In MVC, `@ResponseStatus`, `ResponseStatusException`, or `ResponseEntityExceptionHandler` can convert a `Throwable` into an error response **before** it reaches the filter. Thus exception counts in logs/HTTP responses can exceed the count of exceptions tagged on metrics. This stems from instrumentation placement, not "Actuator losing errors".

**Do not force every 4xx into an observation error.** A missing `/orders/123` resulting in 404 is an expected business outcome. Measure it via status/outcome/route and dedicated business metrics if needed. Marking every 404 as an exception on error dashboards creates noise.

## 6. "Handled Error" Does Not Mean "Unimportant Error"

Handled exceptions fall into three very different categories:

1. **Expected scenarios:** user requests a missing resource → 404, validation fails → 400/422; usually no need to mark an observation error.
2. **Transient dependency failures:** DB/broker/downstream unavailable → 503, circuit breaker open → 503; often worth marking the underlying cause when the request fails.
3. **Programming bugs / unknown exceptions:** `NullPointerException` or invariant violation → 500; if a custom `@ExceptionHandler` converts it into a friendly response, still consider marking the observation error so metrics/tracing don't miss it.

There is no rule saying "every 5xx must attach a `Throwable`": intentionally returning HTTP 503 during maintenance need not involve a Java exception. Measure 503 via status/outcome and availability metrics. **Never instantiate fake `Throwable`s for status codes just to populate a tag.**

Practical decision matrix:

| Case | Recommended HTTP status | Call `setError(ex)`? | Rationale |
|---|---:|---|---|
| Common invalid input validation | 400/422 | Usually no | Client needs to fix input |
| Resource not found | 404 | Usually no | Expected business absence |
| Insufficient permission | 403 | Usually no | Authorization denial is a separate signal |
| Rate limited | 429 | Usually no | Track dedicated rate-limit metrics |
| Intentional maintenance rejection | 503 | Probably no | Status reflects unavailability; may have no `Throwable` |
| Handled downstream timeout | 504/503 | Usually yes | Genuine operational failure worth attributing |
| DB exception mapped to ProblemDetail 503 | 503 | Usually yes | Avoid masking handled failure |
| Catch-all `NullPointerException` mapped to 500 | 500 | Yes | Unexpected server bug |
| Request succeeded via fallback | 200 | Consider separate observation | Marking may flag HTTP span as failed despite client success |

Align policy with your SRE/observability team: does the `error` tag mean **operational failure requiring attention** or **any `Throwable` ever thrown**? Without an explicit definition, dashboards and alerts remain ambiguous even when code runs fine.

## 7. Marking Handled Errors in Spring MVC

Spring Framework 6.1 documentation provides this API:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.filter.ServerHttpObservationFilter;

ServerHttpObservationFilter.findObservationContext(request)
        .ifPresent(context -> context.setError(exception));
```

This is a **code fragment** inside a method that already has `request: HttpServletRequest` and `exception: Exception`. `findObservationContext` returns an `Optional`; if the request has no observation context, `ifPresent` simply does nothing without throwing a `NullPointerException`.

Typical usage is inside an `@ExceptionHandler` before returning `ResponseEntity` or `ProblemDetail`. This **marks the existing observation** created for the current request—it does not start a second observation, change the HTTP status, or rethrow the exception.

**Ordering matters:** call `setError` **before the observation ends**, while request handling is still within lifecycle scope. Calling it after response completion or in a background task outside request scope may be too late or lack context.

If a handler catches multiple exception types, mark selectively per policy rather than indiscriminately marking expected/benign errors. If an exception is already auto-recorded, calling `setError` again adds no default benefit. Across multi-filter/custom error flows, ensure the same context is referenced and avoid overwriting a useful root-cause exception with a generic wrapper.

## 8. Runnable Java 17+ Example: Spring MVC and Four Scenarios

The `mvc-http-observation-demo` project uses Spring Boot 3.3.13, embedded Tomcat, and Actuator. Its controller exposes endpoints:
- `/demo/ok`: 200, no `Throwable`.
- `/demo/not-found`: handled 404, does **not** call `setError`.
- `/demo/handled-500`: handled 500, **unmarked** — proves status differs from `error`.
- `/demo/marked-503`: handled 503 and calls `setError` in `ControllerAdvice`.
- `/demo/unhandled`: throws an exception with no matching handler — used to discuss auto-recording and container error dispatches (without asserting a fixed error class).

### 8.1. Project Structure

```text
mvc-http-observation-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/observation/
    │   │   └── MvcObservationApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/observation/
            └── HttpObservationIntegrationTest.java
```

### 8.2. Gradle Build

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-actuator` provides Micrometer metrics and Observation integration. No tracing bridge/exporter is included; therefore this example **tests metrics** and makes no claim that traces export to Jaeger/Tempo.

### 8.3. Application Properties

`src/main/resources/application.properties`:

```properties
server.port=8080
spring.application.name=mvc-http-observation-demo

# Expose metrics endpoint for demo only; NOT a production configuration.
management.endpoints.web.exposure.include=health,info,metrics

# Default in Boot 3.3 is http.server.requests.
# If renamed, tests and curl queries must match the new meter name.
management.observations.http.server.requests.name=http.server.requests
```

**Actuator security:** `/actuator/metrics` exposes operational metadata. In production, restrict access via authentication/authorization, network controls, management ports, and minimal endpoint exposure; never open metrics, env/config, or prometheus indiscriminately. `management.endpoints.web.exposure.include` only controls which endpoints are **exposed**, not access authorization.

### 8.4. Controller, Exceptions, and ControllerAdvice

`src/main/java/com/example/observation/MvcObservationApplication.java`:

```java
package com.example.observation;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.ServerHttpObservationFilter;

@SpringBootApplication
public class MvcObservationApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcObservationApplication.class, args);
    }
}

@RestController
class ObservationDemoController {

    @GetMapping("/demo/ok")
    String ok() {
        return "ok";
    }

    @GetMapping("/demo/not-found")
    String notFound() {
        throw new MissingItemException("Item not found");
    }

    @GetMapping("/demo/handled-500")
    String handledWithoutMarking() {
        throw new HandledBugException("Handled bug");
    }

    @GetMapping("/demo/marked-503")
    String handledWithMarking() {
        throw new InventoryUnavailableException(
                "Inventory service unavailable");
    }

    @GetMapping("/demo/unhandled")
    String unhandled() {
        throw new IllegalStateException("Unhandled demo failure");
    }
}

@RestControllerAdvice
class ObservationDemoAdvice {

    @ExceptionHandler(MissingItemException.class)
    ResponseEntity<ProblemDetail> missing(MissingItemException ex) {
        return problem(
                HttpStatus.NOT_FOUND,
                "Missing item",
                "The requested item does not exist");
    }

    @ExceptionHandler(HandledBugException.class)
    ResponseEntity<ProblemDetail> bugWithoutMarking(
            HandledBugException ex) {
        // Intentionally DO NOT call setError to prove 500 != error tag.
        return problem(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "Handled bug",
                "An internal failure was handled");
    }

    @ExceptionHandler(InventoryUnavailableException.class)
    ResponseEntity<ProblemDetail> unavailable(
            InventoryUnavailableException ex,
            HttpServletRequest request) {

        // Core takeaway of this lesson:
        // Attach the @ExceptionHandler-handled exception
        // to the current HTTP server observation context.
        ServerHttpObservationFilter.findObservationContext(request)
                .ifPresent(context -> context.setError(ex));

        return problem(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Inventory unavailable",
                "Please retry later");
    }

    private ResponseEntity<ProblemDetail> problem(
            HttpStatus status, String title, String detail) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                status, detail);
        body.setTitle(title);
        return ResponseEntity.status(status).body(body);
    }
}

class MissingItemException extends RuntimeException {
    MissingItemException(String message) {
        super(message);
    }
}

class HandledBugException extends RuntimeException {
    HandledBugException(String message) {
        super(message);
    }
}

class InventoryUnavailableException extends RuntimeException {
    InventoryUnavailableException(String message) {
        super(message);
    }
}
```

**Runnability notes:**
- This is a **single Java file** matching `MvcObservationApplication.java`. It has one top-level `public class`, while the other controller, advice, and exception classes are package-private in the same package so component scanning finds them.
- `@RestControllerAdvice` handles three specific exception types. `IllegalStateException` is intentionally left unhandled to illustrate escaping pipeline errors.
- `ProblemDetail` has been available since Spring Framework 6, and `ResponseEntity<ProblemDetail>` serializes cleanly to the standard error response body.
- `unavailable` accepts `HttpServletRequest` and calls `ServerHttpObservationFilter.findObservationContext(request)` for the **Servlet stack**.
- `problem(...)` sets the HTTP status independently of `context.setError(ex)`.
- The app defines no custom `SecurityFilterChain` or `@EnableWebMvc`, preserving Boot's default MVC/Actuator auto-configuration.

**Usage caveat:** `HandledBugException` is intentionally left unmarked for educational demonstration. That is **not recommended policy** for unexpected server bugs in real production systems, where severe handled failures should generally be marked so metrics/traces aid investigation.

### 8.5. Running the Application

From the project directory with JDK 17+ and Gradle installed:

```bash
gradle bootRun
```

If using the Gradle Wrapper: `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` in Windows PowerShell. Runs on port 8080; requires no database or external services.

Send requests:

```bash
curl -i http://localhost:8080/demo/ok
curl -i http://localhost:8080/demo/not-found
curl -i http://localhost:8080/demo/handled-500
curl -i http://localhost:8080/demo/marked-503
curl -i http://localhost:8080/demo/unhandled
```

Expected:
- `/demo/ok` → **200**, text body `ok`.
- `/demo/not-found` → **404**, `ProblemDetail` response.
- `/demo/handled-500` → **500**, `ProblemDetail` response with **no explicit observation error set**.
- `/demo/marked-503` → **503**, `ProblemDetail` response with `InventoryUnavailableException` attached to the observation context.
- `/demo/unhandled` → **500** from standard container/error handling; `error` tag behavior can depend on error dispatch flow and servlet filter configuration.

In the demo, `ProblemDetail` bodies look like:

```json
{
  "type": "about:blank",
  "title": "Inventory unavailable",
  "status": 503,
  "detail": "Please retry later",
  "instance": "/demo/marked-503"
}
```

Spring Boot may add or omit fields depending on configuration and error; **never assert full JSON byte-for-byte** when testing status and tags. `instance` is populated by the framework when URL context applies; it is not a universal mandatory business contract across all setups.

## 9. Observing Metrics with Actuator `/actuator/metrics`

After sending each request, list available meters:

```bash
curl -s http://localhost:8080/actuator/metrics
```

Locate `http.server.requests`. Query the meter:

```bash
curl -s \
  "http://localhost:8080/actuator/metrics/http.server.requests"
```

Filter by tags using query parameters (`curl -G` URL-encodes values automatically):

```bash
curl -sG \
  "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=uri:/demo/not-found" \
  --data-urlencode "tag=error:none"

curl -sG \
  "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=uri:/demo/handled-500" \
  --data-urlencode "tag=error:none"

curl -sG \
  "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=uri:/demo/marked-503" \
  --data-urlencode "tag=error:InventoryUnavailableException"
```

Corresponding series/measurements appear once requests complete and the registry records them. `/actuator/metrics` returns JSON with `name`, `description`, `measurements`, and `availableTags`; do not assert fixed JSON field ordering or exact timing values.

**Read the output accurately:**
- `/demo/handled-500` shows `status=500`, `outcome=SERVER_ERROR`, **`error=none`**.
- `/demo/marked-503` shows `status=503`, `outcome=SERVER_ERROR`, **`error=InventoryUnavailableException`**.
- `/demo/not-found` shows `status=404`, `outcome=CLIENT_ERROR`, **`error=none`**.

If an endpoint/tag is missing, check Actuator, meter registry, observation enablement, path mapping, and request completion timing. Never pass Prometheus name `http_server_requests_seconds_count` to `/actuator/metrics`; Actuator expects the **Micrometer meter name** `http.server.requests`.

### 9.1. Adding Prometheus (Optional)

Add the optional dependency to `dependencies`:

```groovy
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

Update exposure:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
```

Then:

```bash
curl -s http://localhost:8080/actuator/prometheus
```

In Prometheus, metric names normalize to `http_server_requests_seconds_count`, `_sum`, and `_max` per registry naming and meter config. Inspect real output before hardcoding metric/label names into dashboards. In production, protect Actuator/Prometheus endpoints via network controls/authentication rather than opening them publicly just to inspect tags.

## 10. Integration Test Proving Status and Observation Error Are Independent

Use **JUnit + Spring Boot Test + Micrometer `MeterRegistry`** to send real HTTP calls and verify time series have the expected tags. Do not merely invoke `ControllerAdvice` methods directly in unit tests, as doing so **creates no HTTP server observation**.

**`src/test/java/com/example/observation/HttpObservationIntegrationTest.java`:**

```java
package com.example.observation;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpObservationIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    MeterRegistry meterRegistry;

    private HttpResponse<String> get(String path)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(
                        "http://127.0.0.1:" + port + path))
                .GET()
                .build();

        return HttpClient.newHttpClient().send(
                request,
                HttpResponse.BodyHandlers.ofString());
    }

    private void assertRecorded(
            String uri, String status, String error) {

        await().atMost(Duration.ofSeconds(5))
                .untilAsserted(() -> {
                    Timer timer = meterRegistry
                            .find("http.server.requests")
                            .tag("uri", uri)
                            .tag("method", "GET")
                            .tag("status", status)
                            .tag("error", error)
                            .timer();

                    assertThat(timer).isNotNull();
                    assertThat(timer.count()).isGreaterThan(0);
                });
    }

    @Test
    void handledNotFoundHasStatus404ButNoErrorTag()
            throws Exception {

        HttpResponse<String> response =
                get("/demo/not-found");

        assertThat(response.statusCode()).isEqualTo(404);
        assertRecorded("/demo/not-found", "404", "none");
    }

    @Test
    void handled500MayHaveErrorNone()
            throws Exception {

        HttpResponse<String> response =
                get("/demo/handled-500");

        assertThat(response.statusCode()).isEqualTo(500);
        assertRecorded("/demo/handled-500", "500", "none");
    }

    @Test
    void markedExceptionAppearsInErrorTag()
            throws Exception {

        HttpResponse<String> response =
                get("/demo/marked-503");

        assertThat(response.statusCode()).isEqualTo(503);
        assertRecorded("/demo/marked-503",
                "503", "InventoryUnavailableException");
    }

    @Test
    void successfulRequestHasNoErrorTag()
            throws Exception {

        HttpResponse<String> response =
                get("/demo/ok");

        assertThat(response.statusCode()).isEqualTo(200);
        assertRecorded("/demo/ok", "200", "none");
    }
}
```

`spring-boot-starter-test` includes AssertJ, Awaitility, and JUnit for Boot 3.3. `HttpClient` here is the JDK HTTP client in Java 17, requiring no extra library. `await()` polls boundedly for the meter series to register, avoiding timing races between network response arrival and observation completion.

**These are expected outcomes, not a claim that tests were run in this document.** Run:

```bash
gradle test
```

If a context disables observations, swaps registries, or customizes names/tags, adjust assertions accordingly. In the default Actuator setup with `SimpleMeterRegistry`, the tests are expected to locate the timers. Because concurrent tests can increment counts, assert `count() > 0` instead of exact equality with 1.

**Test limitations:**
- The four tests prove `status` and `error` dimensions are independent for the selected handlers.
- They deliberately do not assert an exact auto-recorded exception class on `/demo/unhandled`, since Servlet container/error dispatches can alter the recorded `Throwable` class and request scope.
- They do not prove a tracing backend received spans, since no tracing exporter is configured.
- Changing `management.observations.http.server.requests.name` or adding a custom `ServerRequestObservationConvention` alters names/tags.
- A `@WebMvcTest` slice may omit Actuator observation infrastructure; to test real HTTP metrics, use `@SpringBootTest(RANDOM_PORT)`.

## 11. Spring WebFlux: Same Problem, Different Context Retrieval

In WebFlux, HTTP requests flow through `HttpHandler`/reactive pipelines. An exception turned into a response by a controller or `@ExceptionHandler` may not reach the observation layer as a terminal error signal. To **explicitly mark a handled exception**, Spring Framework 6.1 uses:

```java
import org.springframework.http.server.reactive.observation.ServerRequestObservationContext;
import org.springframework.web.server.ServerWebExchange;

ServerRequestObservationContext.findCurrent(
        exchange.getAttributes())
        .ifPresent(context -> context.setError(exception));
```

This is a **code fragment** inside a handler with `ServerWebExchange exchange` and `Exception exception`. Compared to MVC:
- There is no `HttpServletRequest` or Servlet `ServerHttpObservationFilter`.
- The class shares the name `ServerRequestObservationContext` yet resides in a different package: `...http.server.reactive.observation`.
- `exchange.getAttributes()` holds the context for the HTTP exchange lifecycle; `findCurrent(...)` returns an `Optional`.
- `setError(ex)` neither alters response status nor terminates the reactive pipeline.
- Do not carry Java `ThreadLocal`/Servlet request attribute intuition into WebFlux; context propagation follows different rules.

### 11.1. Standalone WebFlux Example (Java 17+)

To run the WebFlux example separately, create a second project `webflux-http-observation-demo` without `spring-boot-starter-web`. `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`src/main/resources/application.properties`:

```properties
server.port=8081
spring.application.name=webflux-http-observation-demo
management.endpoints.web.exposure.include=health,metrics
```

`src/main/java/com/example/reactiveobservation/ReactiveObservationApplication.java`:

```java
package com.example.reactiveobservation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.observation.ServerRequestObservationContext;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveObservationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveObservationApplication.class, args);
    }
}

@RestController
class ReactiveObservationController {

    @GetMapping("/reactive/handled")
    Mono<String> handled() {
        return Mono.error(new ReactivePartnerDownException(
                "Partner did not respond"));
    }

    @GetMapping("/reactive/ok")
    Mono<String> ok() {
        return Mono.just("ok");
    }
}

@RestControllerAdvice
class ReactiveObservationAdvice {

    @ExceptionHandler(ReactivePartnerDownException.class)
    ResponseEntity<ProblemDetail> handled(
            ReactivePartnerDownException exception,
            ServerWebExchange exchange) {

        ServerRequestObservationContext.findCurrent(
                        exchange.getAttributes())
                .ifPresent(context -> context.setError(exception));

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.SERVICE_UNAVAILABLE,
                "The upstream service is temporarily unavailable");
        problem.setTitle("Partner unavailable");

        return ResponseEntity.status(
                HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }
}

class ReactivePartnerDownException extends RuntimeException {
    ReactivePartnerDownException(String message) {
        super(message);
    }
}
```

There is one top-level `public class` matching the filename; the remaining classes are package-private in the same package for component scanning. In `handled()`, `Mono.error(...)` emits an error upon subscription. The `@ExceptionHandler` receives the `Throwable` from the reactive pipeline, marks the observation context, and returns `ResponseEntity`/`ProblemDetail`.

Run the second WebFlux project:

```bash
gradle bootRun
curl -i http://localhost:8081/reactive/handled
curl -i http://localhost:8081/reactive/ok
curl -s http://localhost:8081/actuator/metrics/http.server.requests
```

`/reactive/handled` is expected to return 503 with error tag `ReactivePartnerDownException` once observations register the meter; `/reactive/ok` returns 200 with `error=none`. Filter Actuator metrics as in Section 9 with `uri=/reactive/handled` and `error=ReactivePartnerDownException`.

**WebFlux caveat:** never call `block()` inside reactive controllers or filters, as it blocks the Netty event loop. Do not assume an error caught by `onErrorResume` returning `Mono.just(...)` is automatically observed as an error—that too handles the error before the observation boundary. If business policy requires marking it, record it explicitly **while the HTTP exchange is still active**.

### 11.2. When the Handler Is a `WebExceptionHandler` Instead of `@ExceptionHandler`

In WebFlux, a `WebExceptionHandler` can also turn errors into status/body responses. When an exception is converted to a normal completion signal before observation ends, the error signal may not reach observation instrumentation. You can access `ServerWebExchange` inside the handler and retrieve `ServerRequestObservationContext.findCurrent(exchange.getAttributes())` while the lifecycle is still active.

**Do not modify every `WebExceptionHandler` to blindly "mark all errors".** Expected failures like 404, validation 400/422, and security denials typically belong in separate business/baseline metrics. Check exception handler ordering, response committed state, and error-status policy.

## 12. @ExceptionHandler, ProblemDetail, @ResponseStatus, and ResponseStatusException

These mechanisms shape HTTP responses, yet do not necessarily record an observation error:

| Mechanism | What it does | Does the exception still escape to observation? |
|---|---|---|
| `@ExceptionHandler` / `@ControllerAdvice` | Catches exceptions, maps to status/body | No, because it was handled |
| `ResponseEntity<ProblemDetail>` | Builds standard error response with status/detail | No; there may not even be a `Throwable` |
| `ResponseStatusException` | Expresses HTTP error status via exception | Framework resolvers handle it before filters |
| `@ResponseStatus` on exception/handler | Maps status via framework | Usually resolved inside MVC/WebFlux |
| Returning `ResponseEntity.status(500)` directly | Returns status 500 | No `Throwable` to auto-record |
| `DefaultErrorAttributes`/`/error` | Builds Boot/MVC error attributes | Does not automatically pass the original exception to the observation context |
| An unhandled exception | Propagates up middleware/container | Can be auto-recorded if it crosses the observation boundary |

**`ProblemDetail` is an HTTP error body model**, not a Micrometer Error Event. JSON containing `"status": 503` does not automatically populate `context.error`. Likewise, logging a stack trace inside `@ControllerAdvice` does not automatically add an error tag.

In Spring Boot 3.x, `ErrorAttributes`/`BasicErrorController` handle errors in Web MVC; Boot error metadata during an error dispatch **does not replace** Micrometer's `ServerRequestObservationContext.setError`. If correlation between the two is needed, implement it explicitly rather than assuming filters extract exceptions from every request attribute.

## 13. Distinguishing "Auto-Recorded" from "Manually Marked"

Never look solely at an HTTP status or log line and conclude an exception was captured automatically. There are three distinct levels:

**Level A — Observation context auto-records error:** the exception escapes into HTTP observation instrumentation and the framework records `context.error`. This depends on Servlet filter order, web container, and reactive pipelines. Unhandled exceptions are the clearest example.

**Level B — Application explicitly marks the HTTP observation:** calling `findObservationContext`/`findCurrent(...)` then `setError(ex)` on handled-exception paths. The goal is to **preserve the root error cause** even after mapping it to an HTTP response.

**Level C — Application records custom business observations/metrics:** e.g., `inventory.fallback`, `payment.declined`, or `downstream.timeout` when you do not want to mark a successful HTTP request as failed. These are separate signals without calling `setError` on the server request span.

Document clearly in operational policies:
- Which exceptions should mark a request error?
- Should expected 4xx cases count as errors?
- Should 5xx mapped from unexpected exceptions be marked?
- Should a successful fallback mark the HTTP request as failed?
- When observation context is absent (bypassed/disabled), which fallback metrics/logs apply?
- How to avoid duplicate alerts when both 5xx status and `error` tag trigger?
- Which details count as sensitive/PII and must stay out of tags/logs?

## 14. When a Request Needs a Custom Business Metric Instead of `setError`

Suppose an upstream inventory call times out, yet the app falls back to valid cached data and returns HTTP 200 with reliable content. Calling `context.setError(timeout)` on the HTTP server observation can cause dashboards to treat the 200 request as failed even though the client succeeded. Depending on your SLO, that may be either **intentional** or **noisy**.

Alternative: increment a dedicated business counter:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

// Code fragment inside a service injected with MeterRegistry registry.
Counter fallback = Counter.builder("inventory.fallback")
        .tag("reason", "timeout")
        .register(registry);

fallback.increment();
```

This is a **code fragment**, not a standalone class. The `reason` tag should accept only pre-bounded enum values (`timeout`, `unavailable`, `validation`), **never** error messages with URLs, user IDs, or session IDs. If the fallback yields a partial/degraded response, consider a dedicated SLO metric or controlled business response header.

Another example using a custom Micrometer Observation:

```java
Observation.createNotStarted(
        "inventory.lookup", observationRegistry)
        .lowCardinalityKeyValue("dependency", "inventory")
        .observe(() -> service.lookup());
```

This is a **conceptual fragment** with injected `observationRegistry`/`service`. If the lambda throws an exception, Micrometer Observation records the error through its instrumentation. If the lambda catches and handles the error before exiting, you face the same **handled exception** decision: marking the error requires explicit policy.

**Do not force minor dependency hiccups onto the HTTP server error tag** when a successful fallback preserved the client contract, unless your organization defines `error` as "any internal failure" and dashboards explicitly separate them.

## 15. When Status/Outcome Suffices vs. When Exception Tags Are Necessary

### 15.1. Status/Outcome for HTTP SLOs

An availability SLO usually measures HTTP 5xx ratio (with contract-specific exceptions). For a handled 500, **`status=500`/`outcome=SERVER_ERROR`** still lets the SLO detect the failed request even when `error=none`. Never build 5xx alerts solely on `error != none`.

Example separation:
- **Availability error rate:** based on HTTP status/outcome and service contract.
- **Exception class breakdown:** based on `error` tags; will miss handled exceptions unless marked.
- **Business rejection rate:** measured from business outcomes (payment declined, invalid request), not inferred from HTTP 500.
- **Trace exemplars:** depend on sampling/instrumentation/exporters; not guaranteed on every request.

### 15.2. Exception Tags for Root-Cause Diagnosis

When a 503 might stem from `SocketTimeoutException`, `DatabaseException`, or `CircuitBreakerOpenException`, the `error` tag helps group causes. Exception class names remain **low cardinality** when drawn from a finite set; dynamically generating exception classes or stuffing messages into tags explodes cardinality.

**Never place stack traces, exception messages, token-bearing URLs, or customer IDs into low-cardinality tags.** They leak secrets and multiply series. Keep rich root-cause details in redacted, retention-controlled structured logs and traces.

### 15.3. Traces When Enabled

With a `micrometer-tracing` bridge and exporter active, observations can record span error events/status via tracing handlers. However:
- Sampling may drop most traces.
- A trace can exist without a marked error event.
- `context.setError(ex)` attaches the error to the observation context; how the span records exception events/status depends on tracer/bridge/handler.
- An `ERROR` log line does not automatically mark a span as errored without dedicated integration/callbacks.
- Marking the same exception twice across layers can duplicate events or misattribute the cause if policies overlap.

**Never promise "`setError` guarantees an ERROR trace in Jaeger"** without verifying the tracing stack and sampling configuration.

## 16. HTTP Client-Side Errors Can Differ from Server-Side Errors

An application both receiving HTTP requests and calling downstream via `RestClient`/`RestTemplate`/`WebClient` exhibits:

```text
Browser → Spring Boot A → Spring Boot B
  │             │                │
  │         client observation   │
  │         http.client.requests │
  │             │                │
  │         server observation   │
  │         http.server.requests │
  │                              │
  └──── HTTP 200 or 503 ◄─────────┘
```

Suppose service A calls B, B returns 503, `RestClient.retrieve()` throws `HttpServerErrorException`, and A catches it to return a cached 200:
- A's **client-side observation** shows status 503 from B, with or without an error tag depending on client instrumentation.
- A's **server-side observation** shows status 200 because the end client succeeded.
- B's **server-side observation** shows status 503, with an error tag depending on whether B handled/marked its exception.
- A single distributed trace can span multiple spans and error markers; do not force tags across spans to match.

Spring Boot 3.3 instruments HTTP clients when built with Boot-configured builders; raw `RestClient.create()`/`WebClient.create()` skip `ObservationRegistry` by default. Before diagnosing "broken traces", inspect how each client was constructed and how trace context propagates.

**Core scope reminder:** this lesson covers **HTTP server observations** and handled exceptions; calling `setError` on the server context **does not fix** uninstrumented HTTP clients, alter downstream statuses, or mend broken trace propagation.

## 17. Async, Reactor Context, and Errors Occurring After Response Completion

Some failures occur outside the HTTP request boundary even though an HTTP request triggered the work:

- Controller returns HTTP 202, and a background job fails later.
- Controller fires off `CompletableFuture`/`Executor` and returns 200.
- Reactive pipeline is canceled after client disconnect.
- Servlet async/error dispatch runs after the response committed.
- A scheduler processes a queued event minutes after the API returned HTTP 200.
- A WebSocket session exchanges messages long after the HTTP handshake.

In all of these cases, the **HTTP server observation has already ended** or its context is no longer valid. Never hold onto the original request to call `ServerHttpObservationFilter.findObservationContext(request)` from a background thread minutes later. Create a **dedicated observation/trace span for background work**, propagate context deliberately, and pass safe correlation IDs.

In WebFlux, `ThreadLocal` does not automatically follow every operator. Spring Boot 3.3 supports:

```properties
spring.reactor.context-propagation=auto
```

This property configures automatic context propagation when required dependencies are present; it does not make arbitrary custom publishers thread-safe or guarantee background workers inherit traces automatically. Favor Reactor Context and test across actual scheduler hops.

**Cancellation ≠ error:** a user closing a browser tab, a timeout, a network drop, or a stream canceled by `take(1)` is not necessarily a server exception. Mark request errors only when policy identifies a real failure cause rather than turning every CANCEL signal into a 5xx.

## 18. Global `@ControllerAdvice`: Avoid Marking Everything Indiscriminately

You might be tempted to write:

```java
// Snippet NOT recommended as a default pattern:
@ExceptionHandler(Exception.class)
ResponseEntity<ProblemDetail> catchEverything(
        Exception ex, HttpServletRequest request) {

    ServerHttpObservationFilter.findObservationContext(request)
            .ifPresent(context -> context.setError(ex));

    return ResponseEntity.status(500)
            .body(ProblemDetail.forStatus(500));
}
```

This is an **illustrative Spring MVC snippet**; dropping it into the Section 8 app alongside the other handlers affects exception-matching order and specificity. It has several downsides:
1. Every exception reaching it maps to 500, potentially turning validation or 404 errors into 500s.
2. Error tags get attached to expected client errors, creating noise.
3. Overrides standard `ResponseEntityExceptionHandler`/`ProblemDetail` handling.
4. Errors in filters or the container never reach `@ControllerAdvice`, so coverage still isn't 100%.
5. Paired with `log.error("{}", ex)` without redaction, it easily leaks sensitive data.

**Better policy:** classify exceptions semantically, map statuses deliberately, and choose `setError` intentionally. In base exception advice, separate "expected client issues" from "unexpected operational failures". Never make `@ControllerAdvice` rethrow exceptions solely so instrumentation sees them; doing so disrupts responses and error dispatches.

## 19. Customizing Observation Conventions: Only When Needed and Low Cardinality

Spring Boot 3.3 supports:
- MVC: a bean extending `org.springframework.http.server.observation.DefaultServerRequestObservationConvention` to add low/high-cardinality key-values, or implementing `ServerRequestObservationConvention` to replace defaults.
- WebFlux: corresponding package `org.springframework.http.server.reactive.observation.DefaultServerRequestObservationConvention`.
- `ObservationFilter`: post-processes observation contexts and keys in Micrometer.
- `ObservationPredicate`: selectively excludes observations.
- `management.observations.http.server.requests.name`: renames the meter.
- `management.observations.enable.*`: enables/disables observations by prefix.

However, if your only goal is **marking a handled exception**, **there is no need to replace the entire convention**. Calling `setError(ex)` as documented by Spring Framework is clearer and preserves standard tags.

**Bad practice example:** placing `exception.getMessage()` in a low-cardinality tag `error_detail`. Messages can contain SQL, paths, PII, tokens, and millions of variants. To identify the failing stage, use a finite enum/domain category in a custom metric (e.g., `category=downstream_timeout`), keeping redacted stack traces in logs/traces.

**Default tags do not automatically encode domain semantics.** `status=404` could mean a bad URL or a missing entity, and `error=none` simply means no `Throwable` was attached to the observation. Define dashboards around clear contracts rather than over-interpreting individual tags.

## 20. Security, Logging, and Sensitive Data

During error handling, it is tempting to dump entire exceptions into responses, logs, and metrics:

```java
// Not recommended:
log.error("Failed request: {}", request.getRequestURI(), exception);
```

Logging exceptions is **sometimes necessary**, yet you must audit URLs/queries/paths and stack traces because they can leak PII, access tokens, or attacker-controlled strings. In multi-tenant systems, logs require **verified** tenant/correlation metadata and proper access filtering.

Recommendations:
- Client responses must **never expose stack traces**, SQL, passwords, or tokens.
- Use `ProblemDetail` with safe titles/details, stable error codes, and non-sensitive request/correlation IDs.
- Metric tags may carry only route templates, methods, statuses, exception **classes**, or finite categories.
- Traces may hold high-cardinality context, still subject to redaction and retention policies.
- Apply log sampling, rate limiting, and deduplication to avoid floods when a downstream fails at thousands of requests/second.
- Protect Actuator/Prometheus endpoints rather than relying on "internal only" assumptions when infrastructure changes.
- Keep raw paths out of metric tags: `/users/123` and `/users/456` should collapse to `/users/{id}` when mapped rather than spawning per-user series.
- Inside `@ExceptionHandler`, call `setError(ex)` only for **genuinely relevant exceptions** and avoid copying sensitive messages into context tags.

**Do not infer from status codes whether a request was "safe" or "unsafe".** AuthN/authZ filters return 401/403 before controllers; track dedicated security audit/access-denied metrics per security policy. HTTP server observation is only one layer of monitoring.

## 21. Troubleshooting: Why Doesn't the Error Tag Match Expectations?

| Symptom | Possible cause | Check |
|---|---|---|
| 500 response yet `error=none` | `@ExceptionHandler` handled it before observation boundary | Review advice and consider `setError(ex)` |
| 404 yet `error=none` | Expected business not-found or default handler resolved it | Usually intended; monitor status/outcome |
| 503 shows unexpected wrapper class in error tag | Wrapper exception recorded instead of root cause | Inspect stack/handler and attach representative exception |
| Missing `http.server.requests` meter | Missing Actuator/registry, observation disabled, no traffic yet | Check dependencies, registry, `management.observations.enable.*` |
| `/actuator/metrics` returns 404 | Endpoint unexposed or Actuator missing | Enable selective exposure, check management base path |
| `/actuator/metrics` returns 401/403 | Spring Security/management policy blocking | Authenticate properly; do not strip production security |
| Marked exception missing from tag | `setError` called after observation stopped or on wrong context | Call inside `@ExceptionHandler` while exchange is active, inspect stack |
| MVC code cannot find `findObservationContext` | Imported WebFlux class/package by mistake | Use `org.springframework.web.filter.ServerHttpObservationFilter` |
| WebFlux fails injecting `HttpServletRequest` | Mixing Servlet and reactive stacks | Use `ServerWebExchange` + `ServerRequestObservationContext.findCurrent(...)` |
| `@WebMvcTest` has no meters | Test slice lacks full HTTP server instrumentation | Use `@SpringBootTest(RANDOM_PORT)` + Actuator |
| Test checks metrics too early | Observation hasn't closed or registry export delayed | Use bounded async wait and check measurements |
| `exception` metric differs from older Boot | Boot 3.x observation rewrite; `exception` deprecated | Use `error` in 6.1 and version-matched semantics |
| HTTP 200 yet span shows error | Internal fallback marked on server observation | Review policy and prefer custom dependency metric |
| `ERROR` log present, trace shows no error | Logs and observation/tracing are independent channels | Check bridge/sampling and `setError` |
| Metrics work, no traces appear | Missing tracer/exporter or dropped by sampling | Check Micrometer Tracing/OTel exporter |
| Prometheus metric name doesn't match | Registry converts meter name to Prometheus series | Check `/actuator/prometheus`; Actuator uses dot names |
| URL cardinality spikes | Raw path/query/user ID used as tags | Use URI templates and fixed categories |
| Error in Tomcat filter/Valve missing | Outside `ServerHttpObservationFilter` scope | Instrument appropriate container/filter layer |
| Background job fails after HTTP 202, server shows 2xx | Request finished; job runs asynchronously | Instrument background work with its own observation |
| One failure counted multiple times | Counting server status, client status, and custom error counters together | Separate signals by layer and deduplicate alerts |

## 22. Design and Implementation Checklist

- [ ] Confirm Spring Boot/Framework versions and exact observation names.
- [ ] Distinguish HTTP `status/outcome` from observation `error/exception`.
- [ ] Identify all `@ExceptionHandler`/`@ControllerAdvice`/`WebExceptionHandler` classes catching `Throwable` and returning responses.
- [ ] Separate expected 4xx client errors from 5xx operational/bug errors in an explicit policy.
- [ ] For handled exceptions requiring visibility, call `context.setError(ex)` on the active HTTP observation context.
- [ ] In MVC use `ServerHttpObservationFilter.findObservationContext(request)`.
- [ ] In WebFlux use `ServerRequestObservationContext.findCurrent(exchange.getAttributes())`.
- [ ] Never rethrow exceptions just to get a metric tag if doing so breaks the intended HTTP response.
- [ ] Never use `error != none` as the sole signal for HTTP availability SLOs.
- [ ] Never indiscriminately turn every 404/validation/403 into an observation error.
- [ ] Evaluate 200 fallback cases: record a dedicated custom metric when the request succeeds despite a dependency failure.
- [ ] Verify Actuator/Micrometer registry is active and `http.server.requests` timers are registered.
- [ ] Test 404 + no error, 500 + no error, and 503 + marked error in integration tests.
- [ ] Run real HTTP tests so the observation lifecycle executes rather than invoking advice methods directly.
- [ ] Configure and test tracing bridge/exporter/sampling separately if spans are required.
- [ ] Secure metrics endpoints, redact logs/traces, and keep tag cardinality low.
- [ ] Measure background and downstream errors in their own layers instead of conflating them with HTTP server request errors.
- [ ] When upgrading major Boot/Framework versions, review updated semantic conventions and update dashboards.

## 23. Self-Check Questions

**1. Why can `@ExceptionHandler` return HTTP 500 while `error=none`?**  
The exception was resolved by controller advice before reaching HTTP observation instrumentation. Status 500 is recorded from the response, while the observation context has no attached error.

**2. Does `ServerHttpObservationFilter.findObservationContext(request).ifPresent(ctx -> ctx.setError(ex))` automatically change HTTP 500 to 503?**  
No. It only attaches the `Throwable` to the observation context; HTTP status must be set separately by the handler/response.

**3. Must 404 always be recorded as an observation error?**  
No. 404 can be an expected client/business outcome. `status=404` and `outcome=CLIENT_ERROR` already track it while `error` remains `none`.

**4. Does HTTP 500 always involve a Java exception?**  
No. A handler can return `ResponseEntity.status(500)` directly without throwing an exception.

**5. Which API finds the observation context in WebFlux?**  
`org.springframework.http.server.reactive.observation.ServerRequestObservationContext.findCurrent(exchange.getAttributes())`.

**6. Is a catch-all `@ExceptionHandler(Exception.class)` marking every `Throwable` a good default?**  
Usually not. It can misclassify validation/not-found as operational failures, bypass standard handling, and add alert noise; classify explicitly.

**7. Is an `ERROR` log line enough to populate the metrics error tag?**  
No. Logs are a separate channel; populating observation error requires a `Throwable` via auto-recording or explicit marking.

**8. Can `http.server.requests{status="200",error="SomeException"}` occur?**  
Yes, if an app marks an error on a request that recovered via fallback and returned 200. Define clear policies so dashboards interpret it correctly.

**9. If HTTP service B returns 503 and service A falls back to 200, what should A's server observation status be?**  
Service A's HTTP status remains 200. Record the downstream failure in A's client/dependency observation or a business fallback metric rather than confusing B's status with A's.

**10. Why avoid asserting an exact error tag for an unhandled exception in a simple default test?**  
Because Servlet filter scope, error dispatches, and wrapper exceptions can alter which class is recorded. Assert status and explicit instrumentation conditions instead of assuming every container records the exact same class.

**11. Does Spring Boot Actuator export distributed traces automatically just from adding the dependency?**  
No. You need a tracer bridge/exporter, sampling, and proper configuration. Even though both build on Observation, metrics and traces follow separate export pipelines.

**12. Why must exception messages never be placed into metric tags?**  
They leak secrets/PII and explode cardinality. Use finite exception classes/error categories in tags, keeping redacted details in logs/traces.

## 24. Official Documentation for Reference

1. Spring Framework 6.1 — **Observability Support**, HTTP Server Instrumentation (MVC and WebFlux), handled exceptions + `setError`, low-cardinality keys: https://docs.spring.io/spring-framework/reference/6.1/integration/observability.html
2. Spring Boot 3.3.13 — **Metrics**, HTTP server requests, custom conventions, handled exceptions in Spring MVC/WebFlux: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
3. Spring Boot 3.3.13 — **Observability**, Micrometer Observation, metrics/traces/logging, context propagation: https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html
4. Spring Framework 6.1 — **MVC Exceptions and HandlerExceptionResolver**: https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-servlet/exceptionhandlers.html
5. Spring Framework 6.1 — **MVC Error Responses, ProblemDetail**: https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-ann-rest-exceptions.html
6. Spring Framework 6.1 — **WebFlux Error Responses, @ExceptionHandler, ProblemDetail**: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/ann-rest-exceptions.html
7. Spring Boot 3.3.13 — **Actuator endpoints and security**: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
8. Micrometer — **Observation Documentation**: https://docs.micrometer.io/micrometer/reference/observation.html
9. OpenTelemetry — **Trace Semantic Conventions, HTTP spans**: https://opentelemetry.io/docs/specs/semconv/http/

**Conclusion:** an HTTP request carries at least **two independent signals**: response status/outcome and any `Throwable` recorded on the HTTP observation context. Exceptions handled by Spring MVC/WebFlux do not automatically reach the instrumentation boundary. When you genuinely need to attribute a handled failure cause, call `setError(exception)` within the active lifecycle using the right Servlet or WebFlux API—while keeping HTTP statuses accurate, metric cardinality low, logs/traces secure, and error-classification policies consistent.