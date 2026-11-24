# Propagating Correlation IDs and Measuring Per-Request Duration in Spring Boot

## 1. Why Do We Need a Correlation ID and a Reliable Duration Measurement?

When a client calls `GET /api/orders/42`, multiple components can participate in handling it: API gateway, Servlet Filter or WebFlux WebFilter, Spring Security, DispatcherServlet or DispatcherHandler, interceptors, controllers, services, databases, and outbound HTTP clients calling other services. If a request fails or runs slowly, a single isolated log line is rarely enough to tell the full story.

Two requirements go hand in hand:

1. **Correlation ID:** ties related logs and downstream calls together into one interaction for lookup, user support, and incident investigation.
2. **Request duration:** measures a clearly defined interval—for instance, from when the application's HTTP layer receives the request until the response completes—to monitor latency, SLOs, and bottlenecks.

These two concepts are independent: a correlation ID is an **identifier**; duration is a **measurement**. A correlation ID is not a timestamp, does not replace a distributed trace ID, and does not indicate speed. A duration measurement does not automatically trace work across multiple services.

This lesson sits in **Filters and Interceptors**, so the focus is picking the right interception point, managing the ID lifecycle, deciding start/end boundaries for timing, and propagating context downstream. Both Spring MVC/Servlet and Spring WebFlux/reactive are covered; the business goal is identical, while the APIs and context propagation mechanisms differ.

### 1.1. A Single Request Has Multiple Distinct Durations

| Interval | Start | End | Interpretation |
|---|---|---|---|
| Client end-to-end latency | Client prepares/sends request | Client receives full response | Includes network, possible DNS/TLS, proxies, server, and body transfer |
| Gateway latency | Gateway receives request | Gateway finishes sending response | Includes gateway routing, upstream time, and gateway-side network |
| HTTP server duration | Server observation receives request | Server completes HTTP exchange per instrumentation | Aligns with `http.server.requests`, depending on tooling/runtime |
| Servlet Filter synchronous duration | Before `filterChain.doFilter` | After that call returns/throws | **Does not automatically cover full async time** |
| MVC HandlerInterceptor duration | `preHandle` | `afterCompletion` when invoked | Typically measures MVC handler processing; has async/error limits |
| Controller method duration | Before invoking method | When Java method returns | Does not necessarily include time for returned Publisher/Callable to finish |
| Downstream HTTP client duration | Outbound exchange starts | Response exchange ends | Measures a single upstream call only |
| Database query duration | Before query | After query | Covers one segment of server processing |

Never add these metrics together as independent quantities: intervals can **nest**, double-count the same span, or use different sampling rules. Before naming a field `durationMs`, define exactly which boundary it measures.

### 1.2. Example Request Journey

~~~text
Browser / Mobile Client
   |
   | X-Correlation-ID (if trusted/permitted)
   | traceparent (if using distributed tracing)
   v
API Gateway / Trusted Ingress
   |
   v
HTTP Server: Tomcat or Reactor Netty
   |
   +-- Filter/WebFilter: resolve correlationId, attach response header
   |
   +-- Security filter chain / authentication
   |
   +-- DispatcherServlet / DispatcherHandler
   |
   +-- HandlerInterceptor (MVC), controller/router
   |
   +-- Service
   |      |
   |      +-- HTTP client -> Downstream service
   |      |      same correlation policy / W3C trace context
   |      |
   |      +-- Database / cache
   |
   +-- Response; record duration + status + route + correlationId
   |
   v
Client receives status/body and X-Correlation-ID
~~~

Each arrow shows logical processing flow; it does not imply every segment runs synchronously on one Java thread. In WebFlux and async MVC, a request can cross multiple threads and dispatches before completing.

## 2. Correlation ID, Request ID, Trace ID, Span ID, and Idempotency-Key

| Concept | Purpose | Scope | Used as a Business Key? |
|---|---|---|---|
| Correlation ID | Groups logs/calls tied to one interaction | Organization-defined; can span one request or a multi-request workflow | No |
| Request ID | Identifies a single HTTP request | Typically one hop/request, issued by gateway/server | No |
| W3C trace ID | Identifies one distributed trace | Multiple services/spans within one trace | No |
| Span ID | Identifies a single operation/span | One unit within a trace | No |
| Idempotency-Key | Deduplicates a side-effecting operation on retries | Scoped by API contract, actor, operation, payload, and TTL | **Has its own semantics**, not correlation |

A system may deliberately reuse a request ID as its correlation ID, or use a trace ID as the lookup key when instrumentation is unified. Still, never conflate them by default: a business workflow can span multiple HTTP requests, a trace holds many spans, and a retried request generates multiple attempts.

Example W3C `traceparent`:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Here, trace-id is 32 hex digits, parent-id is 16 hex digits, and trace flags follow the spec. **Never overwrite `traceparent` to act as a custom correlation ID.** When using Micrometer Tracing/OpenTelemetry, let instrumentation generate, extract, and propagate W3C trace context. An application header like `X-Correlation-ID` can coexist alongside it.

### 2.1. Header Names Require a Shared Contract

Some systems use `X-Correlation-ID`, others use `X-Request-ID` or an internal name. Standardize on one name across gateways, Java services, mobile/web clients, log exporters, and support tooling.

Illustrative response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Correlation-ID: req-example12345

{"message":"ok"}
~~~

This is an **illustrative** response, not something Spring Boot generates automatically without a Filter/WebFilter or gateway config. Values must be syntactically valid for HTTP headers and contain no control characters or sensitive data.

### 2.2. Where Should IDs Be Generated?

Prefer generating IDs at a **trusted ingress** such as the API gateway and forwarding them to backends. If an application is called directly, the app itself can generate the ID. A common policy:

1. Accept incoming headers only from trusted sources, or validate and enforce a clear verification policy.
2. Cap length and character set, rejecting/stripping CR/LF, Unicode control characters, or oversized strings.
3. If no valid ID is provided, generate a fresh one, such as a random UUID.
4. Store the ID in the request context before logging components execute.
5. Echo the ID in the response header; when returning a `ProblemDetail` error, you can also include a `correlationId` extension field.
6. Forward the ID on downstream calls per contract.
7. Clear/restore thread-local state after the request so IDs never bleed across requests.

The Java demo uses `[A-Za-z0-9._-]{8,64}` as an allowlist example. This **is not a universal standard**, just an illustrative policy. On public APIs, format validation alone **does not make an incoming ID trustworthy**. You may prefer always generating an internal ID and recording any untrusted external ID separately.

### 2.3. Never Use Correlation IDs for Access Control

Never use an ID to authenticate, identify a tenant, identify a user, grant permissions, or confirm payment. A correlation ID is not a security token; any client can forge the header. Never embed emails, phone numbers, passwords, tokens, or account numbers inside the ID.

### 2.4. Correlation IDs Are Not Metric Tags

A unique ID per request has nearly infinite cardinality. Adding `correlationId` as a tag on a Prometheus or Micrometer Timer/Counter causes time-series explosion. **Keep IDs in logs/traces; use bounded dimensions like route template, method, status, outcome, and error category in metrics.**

## 3. Choosing the Right Extension Point: Filter vs. HandlerInterceptor

In the Spring MVC Servlet stack, two APIs are commonly used:

| Criterion | Servlet Filter / OncePerRequestFilter | HandlerInterceptor |
|---|---|---|
| Layer | Servlet container filter chain | Spring MVC handler execution chain |
| Runs before DispatcherServlet? | Yes, if registered properly | No; only after MVC resolves a handler |
| Can cover other Servlets? | Yes, with matching URL/dispatcher mapping | No, MVC handlers only |
| Knows MVC handler/controller? | Lacks full handler info at chain entry | Receives handler object and mapping metadata |
| Add correlation response header early | Very suitable | Possible, but misses routes/errors outside MVC |
| Populate MDC before security/dispatcher | Yes, depending on Filter order | Runs later and usually after security |
| Measure handler execution | Cannot directly distinguish methods | Well suited via `preHandle`/`afterCompletion` |
| Accurately time full async HTTP request | Not via `try/finally` around `doFilter` alone | Not guaranteed by `afterCompletion` alone |
| Handle ERROR/ASYNC dispatches | Controlled by registration and flags | Controlled by MVC handler lifecycle |
| Errors right inside security/filter | Visible when Filter runs earlier | May never enter the interceptor |

**Practical rule:** establish the correlation ID in a sufficiently early Filter; use `HandlerInterceptor` when handler metadata or MVC-specific handling is needed; and use **Spring Boot/Micrometer HTTP server observations** to measure full-exchange latency when Actuator is enabled instead of duplicating built-in instrumentation.

### 3.1. OncePerRequestFilter Does Not Mean Once Across the Entire Async Lifecycle

The class name can mislead. `OncePerRequestFilter` guarantees single execution **within a single request dispatch thread** per its rules, not a promise of a single invocation across all ASYNC/ERROR dispatches and Java threads of the same HTTP request.

Two hook methods:

- `shouldNotFilterAsyncDispatch()` defaults to `true`, skipping subsequent ASYNC dispatches.
- `shouldNotFilterErrorDispatch()` defaults to `true`, skipping ERROR dispatches.

You can override both to return `false` when MDC must be restored on those dispatches. However, **FilterRegistrationBean or the Servlet container must also map the Filter to `DispatcherType.ASYNC`/`ERROR`**; overriding the hook alone is insufficient.

In an ERROR dispatch nested inside a REQUEST dispatch, `OncePerRequestFilter` may enter `doFilterNestedErrorDispatch` rather than `doFilterInternal`. For complex security/logging flows, verify actual container behavior.

### 3.2. HandlerInterceptor with Async Requests

With MVC async processing like `Callable` or `DeferredResult`, a `HandlerInterceptor` may follow this sequence:

~~~text
REQUEST dispatch:
    preHandle
    controller returns Callable/DeferredResult
    afterConcurrentHandlingStarted
    -> Filter chain exits; async work continues elsewhere

ASYNC redispatch once result is ready:
    preHandle (may be invoked again)
    Spring MVC writes the result
    afterCompletion
~~~

Consequently, if you overwrite `startNanos` every time `preHandle` runs, you reset the clock at redispatch and **lose the async wait time**. Only set `startNanos` if the request attribute is not already present.

Do not treat `afterCompletion` as guaranteed for every async failure: timeouts or network disconnects can happen without an async redispatch or `afterCompletion` callback. If building custom instrumentation for those cases, use `WebAsyncManager`/`CallableProcessingInterceptor`/`DeferredResultProcessingInterceptor` callbacks, or prefer framework-integrated server observations.

## 4. Measuring Time: System.nanoTime Instead of Wall-Clock Time

Measure elapsed duration with a **monotonic time source** like `System.nanoTime()` within the same JVM:

~~~java
long startNanos = System.nanoTime();

// Execute an operation...

long durationNanos = System.nanoTime() - startNanos;
double durationMs = durationNanos / 1_000_000.0;
~~~

This is a snippet. `System.nanoTime` does not represent calendar time and is solely for computing differences. It is superior to `System.currentTimeMillis` for latency because the system wall clock can jump during NTP sync or manual adjustments; subtracting two wall-clock timestamps can even go negative.

Use `Instant.now()` or UTC timestamps when recording **when** a request occurred, not for high-precision elapsed duration. A log entry can include both timestamp and duration, serving different roles.

### 4.1. Units and Precision

- `nanoTime` returns values in nanosecond units at the API level, though actual resolution/accuracy depends on the platform.
- `TimeUnit.NANOSECONDS.toMillis` truncates to integer milliseconds, returning `0` for fast operations; `0` does not prove zero duration.
- Dividing `durationNanos / 1_000_000.0` reports fractional milliseconds.
- Never compare `nanoTime` values taken on two different JVMs: their origins are unrelated.
- Never sum latencies across components without verifying whether they ran in parallel or nested.
- Never treat the time a controller method takes to return a `Mono`/`Flux` as the total reactive response duration.

### 4.2. Reading Status at the Right Moment

In a Servlet Filter, `response.getStatus()` right after `filterChain.doFilter` can be a **provisional** status if the request went async. In WebFlux, `response.getStatusCode()` may still be null when a filter runs. Log status at the proper completion callback when the response/pipeline ends; if status is still unset, log a neutral marker rather than guessing 200.

### 4.3. From Duration to SLOs

Operational targets typically track error rates, P50/P95/P99 latency, throughput, and saturation per route. You need distributions/histograms, not averages alone, because a few very slow requests easily hide inside an average.

Never register a custom `Timer` under the exact name `http.server.requests` when Spring Boot Actuator already auto-instruments it, or you risk double-counting or competing time series. Use observation conventions/customizers when adding safe low-cardinality tags.

## 5. Spring Boot 3.x / Java 17+ Example: Correlation Filter in MVC

This example uses Spring MVC/Servlet with standard embedded Tomcat, Java 17+, and Spring Boot 3.3.x as the baseline. The layout matches a Spring Initializr project; Java classes use Boot 3.x's Jakarta Servlet API.

### 5.1. Gradle Dependencies

In a Gradle project configured with the Spring Boot plugin and Maven Central:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Actuator is included for the metrics section; Filter/Interceptor themselves do not depend on Actuator. In Maven, declare the corresponding starters.

Project structure:

~~~text
src/main/java/dev/example/correlationmvc/
    CorrelationMvcApplication.java
    CorrelationIdFilter.java
    HttpPipelineConfig.java
    MvcTimingInterceptor.java
    DemoController.java
src/main/resources/application.yml
src/test/java/dev/example/correlationmvc/
    CorrelationMvcTest.java
~~~

### 5.2. Main Class

File `src/main/java/dev/example/correlationmvc/CorrelationMvcApplication.java`:

~~~java
package dev.example.correlationmvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorrelationMvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorrelationMvcApplication.class, args);
    }
}
~~~

Place all classes in this package so Spring Boot component scanning detects the configuration and controller.

### 5.3. A Filter Preserving the ID Across Dispatches

File `src/main/java/dev/example/correlationmvc/CorrelationIdFilter.java`:

~~~java
package dev.example.correlationmvc;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public class CorrelationIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Correlation-ID";
    public static final String ATTRIBUTE = "correlationId";

    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{8,64}");

    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false;
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        return false;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        Object existing = request.getAttribute(ATTRIBUTE);
        String id;

        if (existing instanceof String saved) {
            id = saved;
        } else {
            String candidate = request.getHeader(HEADER);

            id = candidate != null
                    && SAFE.matcher(candidate).matches()
                    ? candidate
                    : UUID.randomUUID().toString();

            request.setAttribute(ATTRIBUTE, id);
        }

        response.setHeader(HEADER, id);

        String previous = MDC.get(ATTRIBUTE);
        MDC.put(ATTRIBUTE, id);

        try {
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(ATTRIBUTE);
            } else {
                MDC.put(ATTRIBUTE, previous);
            }
        }
    }
}
~~~

Design notes:

1. **Request attribute** preserves the request's ID across dispatches; no new ID is generated on ASYNC redispatches.
2. **Response header** is set early so normal and most error responses share a consistent ID.
3. **MDC** is populated only while the Filter chain executes on the current thread; `finally` restores the prior state to prevent ID leakage.
4. For ASYNC/ERROR dispatches, the Filter is allowed to run again to repopulate MDC on the dispatch thread if Servlet registration permits it.
5. This code **does not automatically propagate MDC** onto threads of `Callable`, `@Async`, `CompletableFuture`, or background executors outside the Filter.
6. The demo policy accepts inbound IDs matching the regex; on public APIs, enforce trusted ingress or generate internal IDs to prevent spoofing.

The class intentionally **omits `@Component`**, since we register an explicit `FilterRegistrationBean` below to control dispatcher types and filter ordering. Adding both `@Component` and another registration bean risks duplication or unexpected ordering.

### 5.4. FilterRegistrationBean and Ordering

File `src/main/java/dev/example/correlationmvc/HttpPipelineConfig.java`:

~~~java
package dev.example.correlationmvc;

import java.util.EnumSet;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class HttpPipelineConfig implements WebMvcConfigurer {

    @Bean
    FilterRegistrationBean<CorrelationIdFilter> correlationRegistration() {
        FilterRegistrationBean<CorrelationIdFilter> bean =
                new FilterRegistrationBean<>(
                        new CorrelationIdFilter());

        bean.setName("correlationIdFilter");
        bean.addUrlPatterns("/*");
        bean.setDispatcherTypes(EnumSet.of(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC,
                DispatcherType.ERROR));
        bean.setAsyncSupported(true);
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE);

        return bean;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new MvcTimingInterceptor());
    }
}
~~~

This configuration pairs with `CorrelationIdFilter` in Section 5.3 and `MvcTimingInterceptor` in Section 6. In real apps with Spring Security, CORS, observations, and other filters, review exact ordering rather than placing every filter at `HIGHEST_PRECEDENCE`.

Both conditions must hold for the Filter to run again on ASYNC/ERROR dispatches: `OncePerRequestFilter` must not skip the dispatch, and the registration must include those dispatcher types. Never register the same Filter twice.

## 6. HandlerInterceptor Measuring MVC Handler Duration

A `HandlerInterceptor` provides access to the **route template** from `HandlerMapping` for logging and MVC tracking. This measurement is instructive for learning, though it does not replace built-in server observations for measuring total request time across all error/async lifecycles.

File `src/main/java/dev/example/correlationmvc/MvcTimingInterceptor.java`:

~~~java
package dev.example.correlationmvc;

import java.util.concurrent.TimeUnit;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.servlet.AsyncHandlerInterceptor;
import org.springframework.web.servlet.HandlerMapping;

public class MvcTimingInterceptor implements AsyncHandlerInterceptor {

    private static final Logger LOG =
            LoggerFactory.getLogger(MvcTimingInterceptor.class);

    private static final String START =
            MvcTimingInterceptor.class.getName() + ".startNanos";

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        if (request.getAttribute(START) == null) {
            request.setAttribute(START, System.nanoTime());
        }

        return true;
    }

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        // Keep the request attribute: async work has not finished yet.
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {

        Object value = request.getAttribute(START);
        if (!(value instanceof Long started)) {
            return;
        }

        request.removeAttribute(START);

        long nanos = System.nanoTime() - started;
        double milliseconds = nanos / 1_000_000.0;

        Object matched = request.getAttribute(
                HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

        String route = matched == null
                ? "UNMAPPED"
                : matched.toString();

        Object id = request.getAttribute(
                CorrelationIdFilter.ATTRIBUTE);

        LOG.info(
                "mvc_request method={} route={} status={} durationMs={} "
                + "correlationId={} exception={}",
                request.getMethod(),
                route,
                response.getStatus(),
                milliseconds,
                id,
                exception == null
                        ? "none"
                        : exception.getClass().getSimpleName());
    }
}
~~~

`WebMvcConfigurer` in Section 5.4 registers this interceptor. When MVC locates a handler, `preHandle` sets the start mark once. If the request goes async and redispatches, the start mark is preserved instead of overwritten.

**Demo limitations:**
- `HandlerInterceptor` runs only on requests with a matching MVC handler chain; it misses errors originating earlier in Servlet Filters, Spring Security, or gateways.
- On async timeouts or network errors without a redispatch, `afterCompletion` may not run. Use dedicated callbacks or server observations for full coverage.
- The logged response status is the status at callback time, not guaranteed to reflect final network write outcomes.
- Never put unbounded raw request URIs into metric tags; the route from `BEST_MATCHING_PATTERN_ATTRIBUTE` is normally a template, suitable for grouping per endpoint.
- Never log `error.message` or rejected values containing sensitive information.

### 6.1. Do Filter and Interceptor Compute the Same Duration?

Not necessarily. A Filter wraps the Servlet chain and can run for requests that match no MVC handler. An interceptor runs only after handler selection and measures from before the handler until `afterCompletion`. A Filter timing in `doFilter`'s `finally` versus an interceptor timing in `afterCompletion` can differ due to filter ordering, dispatches, serialization, and async behavior.

When building P95/P99 dashboards for **HTTP server latency**, rely on one consistent source such as Micrometer's `http.server.requests`. Interceptor logs serve as supplementary debugging data, not values to mix directly with server-level metrics.

## 7. Demo Controller: Normal, Error, and Async Requests

File `src/main/java/dev/example/correlationmvc/DemoController.java`:

~~~java
package dev.example.correlationmvc;

import java.util.Map;
import java.util.concurrent.Callable;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DemoController {

    @GetMapping("/api/hello")
    public Map<String, String> hello(HttpServletRequest request) {
        Object id = request.getAttribute(
                CorrelationIdFilter.ATTRIBUTE);

        return Map.of(
                "message", "hello",
                "correlationId", String.valueOf(id));
    }

    @GetMapping("/api/async")
    public Callable<Map<String, String>> asyncHello(
            HttpServletRequest request) {

        String id = String.valueOf(request.getAttribute(
                CorrelationIdFilter.ATTRIBUTE));

        return () -> Map.of(
                "message", "async",
                "correlationId", id);
    }

    @GetMapping("/api/fail")
    public void fail() {
        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Invalid demo request");
    }
}
~~~

On normal requests, the controller returns a JSON body with `message` and `correlationId` read from the request attribute. On `/api/async`, it returns a `Callable` handled by Spring MVC's async mechanism. This code strictly demonstrates behavior without heavy blocking work or database calls.

In `/api/fail`, Spring MVC returns HTTP 400. The error response body depends on error-handling configuration, while the Filter has already set `X-Correlation-ID` on the header. Standardizing full JSON error payloads belongs to a dedicated `ControllerAdvice`/`ErrorController` design.

## 8. application.yml and Running the MVC Demo

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,metrics

logging:
  pattern:
    level: "%5p [correlationId:%X{correlationId:-}]"
~~~

The `logging.pattern.level` setting suits standard Boot/Logback setups, injecting MDC `correlationId` into log lines. If your app also uses Micrometer Tracing, Boot automatically adds `traceId`/`spanId` to the logging correlation pattern; verify how they combine rather than accidentally overriding an important pattern.

Run from the Gradle project directory:

~~~bash
./gradlew bootRun
~~~

In Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Send a request with a valid ID:

~~~bash
curl -i -H "X-Correlation-ID: req-test12345" \
  http://localhost:8080/api/hello
~~~

Primary outcome: HTTP 200, response header `X-Correlation-ID=req-test12345`, and body:

~~~json
{"message":"hello","correlationId":"req-test12345"}
~~~

JSON field/header order may vary. The conceptual interceptor log line looks like:

~~~text
mvc_request method=GET route=/api/hello status=200 durationMs=3.42 correlationId=req-test12345 exception=none
~~~

**`durationMs=3.42` is purely illustrative**: each actual run differs. Never write tests asserting on a fixed millisecond latency.

Send without the header:

~~~bash
curl -i http://localhost:8080/api/hello
~~~

The server generates a fresh UUID and uses the same value in both response header and body. Send an invalid header such as one containing spaces, and the demo replaces it with a UUID. Public APIs should enforce clearer trust boundaries than regex validation alone.

Test async:

~~~bash
curl -i http://localhost:8080/api/async
~~~

The typical body contains `message="async"` and `correlationId`. The Servlet container performs an ASYNC redispatch; the filter and interceptor are designed not to regenerate the ID or start timestamp on redispatch. In production, timeouts, disconnects, or async errors require dedicated handling as explained earlier.

Test error:

~~~bash
curl -i http://localhost:8080/api/fail
~~~

Expect HTTP 400 with `X-Correlation-ID` still present across standard MVC error paths. Do not assume a specific JSON error body without an explicit error contract in the project.

## 9. MockMvc Tests for Headers, IDs, and Async Dispatches

File `src/test/java/dev/example/correlationmvc/CorrelationMvcTest.java`:

~~~java
package dev.example.correlationmvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorrelationMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void preservesAllowedCorrelationId() throws Exception {
        mvc.perform(get("/api/hello")
                .header("X-Correlation-ID", "req-test12345"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Correlation-ID", "req-test12345"))
                .andExpect(jsonPath("$.correlationId")
                        .value("req-test12345"));
    }

    @Test
    void generatesNewIdWhenHeaderMissing() throws Exception {
        MvcResult result =
                mvc.perform(get("/api/hello"))
                        .andExpect(status().isOk())
                        .andExpect(header().exists("X-Correlation-ID"))
                        .andReturn();

        String id = result.getResponse().getHeader(
                "X-Correlation-ID");

        assertNotNull(id);
        assertEquals(36, id.length());
    }

    @Test
    void rejectsUnsafeHeaderFormat() throws Exception {
        MvcResult result =
                mvc.perform(get("/api/hello")
                        .header("X-Correlation-ID", "bad id"))
                        .andExpect(status().isOk())
                        .andReturn();

        assertNotEquals(
                "bad id",
                result.getResponse().getHeader("X-Correlation-ID"));
    }

    @Test
    void asyncRedispatchKeepsId() throws Exception {
        MvcResult started =
                mvc.perform(get("/api/async")
                        .header("X-Correlation-ID", "req-async12345"))
                        .andExpect(request().asyncStarted())
                        .andReturn();

        mvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Correlation-ID", "req-async12345"))
                .andExpect(jsonPath("$.correlationId")
                        .value("req-async12345"));
    }

    @Test
    void expectedErrorStillHasCorrelationHeader()
            throws Exception {
        mvc.perform(get("/api/fail"))
                .andExpect(status().isBadRequest())
                .andExpect(header().exists("X-Correlation-ID"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

MockMvc verifies HTTP requests across the MVC/filter setup, though it does not prove event-loop latencies or real error dispatch behavior across every Servlet container. For real async verification, add `RANDOM_PORT` integration tests with a real HTTP client, and test timeouts/cancellations separately.

### 9.1. Never Test Against a Fixed Duration

Latency depends on CPU, GC, JIT, thread scheduling, and OS load. Unit tests must never assert `"GET /api/hello always < 10ms"` on CI runners, as that makes tests flaky. Instead verify that the start mark is set once, the interceptor never logs negative durations, metrics register under the expected name, and routes are normalized.

Use load tests or integration tests on controlled environments to evaluate P95/P99 or SLOs. In production, monitor trends over time rather than single isolated requests.

## 10. Micrometer Observation and http.server.requests in Spring Boot

In Spring Boot 3.3, Actuator automatically instruments HTTP server requests for both Spring MVC and Spring WebFlux. The default logical observation/meter name is **`http.server.requests`**; it can be customized via `management.observations.http.server.requests.name`. Your metrics registry/exporter determines how the name is formatted in backends like Prometheus.

Advantages over hand-rolled Timers:

- Observes broad parts of the HTTP exchange through framework infrastructure.
- Provides low-cardinality tags such as method, status, outcome, and route template depending on instrumentation.
- Uses a unified model across MVC and WebFlux.
- Produces both metrics and tracing spans when a tracing bridge is configured.
- Avoids reinventing measurements whenever a team adds new handlers.
- Offers observation conventions to attach safe metadata cleanly.

When Actuator is enabled and the metrics endpoint is exposed, try:

~~~bash
curl -i http://localhost:8080/actuator/metrics/http.server.requests
~~~

This requires the right management port/base-path and security configuration. If no HTTP requests have been recorded yet, the endpoint may not return data for that metric name. Never expose metrics endpoints publicly on the Internet just for debugging.

### 10.1. Configuration Guide

Example `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics

  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

This configuration is **optional** for histograms on `http.server.requests` in supported Boot/Micrometer versions; it increases time-series counts and storage cost. Before enabling broadly in production, evaluate route/tag counts, metrics backend capacity, and percentile-aggregation requirements.

To export to Prometheus, add the corresponding registry (such as `micrometer-registry-prometheus`) and expose the endpoint appropriately. Never assume Actuator's default starter automatically provides `/actuator/prometheus` without the registry dependency and exposure config.

### 10.2. Low-Cardinality Tags vs. High-Cardinality Context

Recommended tags:
- HTTP method: GET/POST/PUT...
- Status: 200/404/500...
- Route template: `/api/orders/{id}`, not `/api/orders/42`.
- Outcome or a bounded error code group if cataloged.

Never use as metric tags:
- correlationId/traceId/spanId.
- Raw full URI, paths containing random IDs, query strings.
- Email, userId, orderId, API keys, JWTs, session IDs.
- Exception messages carrying dynamic input values.

Micrometer Observation separates low-cardinality and high-cardinality key-values. High-cardinality metadata can belong in traces under security controls, **never** as unbounded metric tags.

### 10.3. Log Durations and Metric Durations Have Different Scopes

A log line from `HandlerInterceptor` might report 12 ms while `http.server.requests` reports a slightly different number. The difference can be completely valid due to start/end boundaries, filter order, async dispatches, or response body writes. Document each measurement's exact semantics instead of forcing them to match and labeling valid discrepancies as "measurement bugs."

## 11. Spring MVC: Propagating Correlation IDs to HTTP Clients

The Filter stores the ID in the Servlet request attribute and the active thread's MDC. When a controller calls downstream services with `RestClient`/`RestTemplate`, an HTTP client interceptor can attach `X-Correlation-ID`.

In Spring Boot 3.3, Boot's auto-configured `RestClient.Builder` can be injected. Illustrative `@Configuration` snippet:

~~~java
@Bean
RestClient partnerRestClient(RestClient.Builder builder) {
    return builder.requestInterceptor((request, body, execution) -> {
        RequestAttributes attributes =
                RequestContextHolder.getRequestAttributes();

        if (attributes instanceof ServletRequestAttributes servlet) {
            Object value = servlet.getRequest()
                    .getAttribute(CorrelationIdFilter.ATTRIBUTE);

            if (value instanceof String id) {
                request.getHeaders().set(
                        CorrelationIdFilter.HEADER, id);
            }
        }

        return execution.execute(request, body);
    }).build();
}
~~~

This illustrative `@Bean` method requires importing `org.springframework.web.client.RestClient`, `org.springframework.web.context.request.RequestAttributes`, `RequestContextHolder`, `ServletRequestAttributes`, and `@Bean`. It works when the client is invoked on a thread carrying those request attributes.

**Does not work automatically with `@Async`, `CompletableFuture.supplyAsync`, scheduled jobs, or arbitrary executor threads**: `RequestContextHolder` uses `ThreadLocal` by default and does not automatically hop across threads. When crossing threads, pass the ID as a method argument/immutable context or configure `TaskDecorator`/context propagation on your executor.

### 11.1. Using TaskDecorator on Spring-Managed Executors

If using an application-configured `ThreadPoolTaskExecutor`, attach a `TaskDecorator` to copy MDC from the submitting thread. Safe conceptual pseudocode:

~~~java
TaskDecorator decorator = task -> {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();

        try {
            if (captured == null) MDC.clear();
            else MDC.setContextMap(captured);

            task.run();
        } finally {
            if (previous == null) MDC.clear();
            else MDC.setContextMap(previous);
        }
    };
};
~~~

This snippet requires importing `java.util.Map`, `org.slf4j.MDC`, and `org.springframework.core.task.TaskDecorator`, and passing it to the executor via `setTaskDecorator`. It **only** affects tasks submitted through that executor; it does not automatically make `CompletableFuture`'s `commonPool`, Reactor schedulers, or external libraries inherit MDC.

Copy only necessary metadata, restore/clear in `finally`, and avoid letting long-lived background tasks retain references to HTTP request objects. If Micrometer Context Propagation/Tracing is configured, prefer the standard mechanism over duplicating or conflicting with a custom decorator.

### 11.2. Using WebClient Inside Spring MVC

A Spring MVC app can still use `WebClient`, which does not switch the server to WebFlux. When `WebClient` runs on a Reactor pipeline, MDC and `RequestContextHolder` will not automatically follow every callback thread. Extract the correlation ID while still on the Servlet thread and pass it explicitly into the `WebClient` request header; for deeper propagation, use Reactor Context and supported instrumentation.

## 12. Spring WebFlux: WebFilter + Reactor Context + doFinally

In a reactive WebFlux server, Servlet Filters and MVC HandlerInterceptors **are not** default extension points on Reactor Netty. Spring WebFlux uses `WebFilter`, `ServerWebExchange`, and the reactive chain.

A WebFilter can:

1. Extract or generate a correlation ID.
2. Store it in `ServerWebExchange` attributes.
3. Set `X-Correlation-ID` on the response.
4. Put the ID into Reactor Context for downstream reactive operations.
5. Measure duration from subscription start until Publisher completion, error, or cancellation.
6. Log status/route when available.
7. Never block event-loop threads and never rely on `ThreadLocal` MDC surviving across every callback.

### 12.1. Reactor Context Is Not MDC

MDC is typically `ThreadLocal`-based (in standard SLF4J). A reactive pipeline can switch event-loop threads or schedulers; wrapping a `Mono`-returning method in `try/finally` MDC does not preserve the ID across operators. Reactor Context travels with the subscription and is read via `Mono.deferContextual` or `Flux.deferContextual` inside the pipeline.

**Never call `.subscribe()` inside a WebFilter** to start timing, as that detaches execution from the HTTP exchange and breaks cancellation/error handling. Return the chain's `Mono<Void>`, compose operators on it, and let the runtime subscribe.

### 12.2. Java 17+ WebFlux Example

In a **separate Spring Boot WebFlux project** with `spring-boot-starter-webflux` and `spring-boot-starter-test`, create the main class in package `dev.example.correlationrx`:

~~~java
package dev.example.correlationrx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveCorrelationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveCorrelationApplication.class, args);
    }
}
~~~

This is `ReactiveCorrelationApplication.java`. Next, create `src/main/java/dev/example/correlationrx/RequestContextWebFilter.java`:

~~~java
package dev.example.correlationrx;

import java.util.UUID;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestContextWebFilter implements WebFilter {

    private static final Logger LOG =
            LoggerFactory.getLogger(RequestContextWebFilter.class);

    public static final String HEADER = "X-Correlation-ID";
    public static final String KEY = "correlationId";

    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{8,64}");

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return Mono.defer(() -> {
            String incoming = exchange.getRequest()
                    .getHeaders().getFirst(HEADER);

            String id = incoming != null
                    && SAFE.matcher(incoming).matches()
                    ? incoming
                    : UUID.randomUUID().toString();

            long startNanos = System.nanoTime();

            exchange.getAttributes().put(KEY, id);
            exchange.getResponse().getHeaders().set(HEADER, id);

            return chain.filter(exchange)
                    .doFinally(signal -> {
                        long nanos = System.nanoTime() - startNanos;
                        double durationMs = nanos / 1_000_000.0;

                        Object mapping = exchange.getAttribute(
                                HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

                        String route = mapping == null
                                ? "UNMAPPED"
                                : mapping.toString();

                        HttpStatusCode status = exchange
                                .getResponse().getStatusCode();

                        LOG.info(
                                "rx_request method={} route={} status={} "
                                + "durationMs={} correlationId={} signal={}",
                                exchange.getRequest().getMethod(),
                                route,
                                status == null
                                        ? "UNSET"
                                        : status.value(),
                                durationMs,
                                id,
                                signal);
                    })
                    .contextWrite(context -> context.put(KEY, id));
        });
    }
}
~~~

Properties:

- `Mono.defer` defers ID extraction and start timing until subscription time.
- `ServerWebExchange.attributes` holds the ID for handlers and error handlers on the same exchange.
- `contextWrite` places the ID into Reactor Context for the downstream reactive chain.
- `doFinally` executes when the chain emits complete, error, or cancel; `signal` distinguishes `COMPLETE`, `ERROR`, and `CANCEL`.
- Uses route templates from `HandlerMapping` when present instead of high-cardinality raw URIs.
- Does not fabricate `status=200` when status is still null.
- This measures **the Publisher/handler chain wrapped by WebFilter**, not necessarily end-to-end client network latency or socket flush completion.
- If an error occurs outside the WebFilter or the connection drops before processing, response headers/body are not guaranteed to reach the client; logs and metrics still require proper error handling.

### 12.3. Reactive Controller

Create `src/main/java/dev/example/correlationrx/ReactiveDemoController.java`:

~~~java
package dev.example.correlationrx;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class ReactiveDemoController {

    @GetMapping("/api/hello")
    public Mono<Map<String, String>> hello(
            ServerWebExchange exchange) {

        String id = exchange.getAttribute(
                RequestContextWebFilter.KEY);

        return Mono.just(Map.of(
                "message", "hello",
                "correlationId", id == null ? "missing" : id));
    }

    @GetMapping("/api/reactor-context")
    public Mono<Map<String, String>> context() {
        return Mono.deferContextual(view -> {
            String id = view.getOrDefault(
                    RequestContextWebFilter.KEY, "missing");

            return Mono.just(Map.of("correlationId", id));
        });
    }
}
~~~

Both endpoints let you inspect the ID from exchange attributes and from Reactor Context. Never call `block()` or `subscribe()` inside controllers; WebFlux subscribes to the Publisher and serializes JSON.

Run the WebFlux project via `./gradlew bootRun` and test:

~~~bash
curl -i -H "X-Correlation-ID: req-rx123456" \
  http://localhost:8080/api/hello

curl -i -H "X-Correlation-ID: req-rx123456" \
  http://localhost:8080/api/reactor-context
~~~

When running standalone on port 8080, the first response contains `message=hello`, `correlationId=req-rx123456`, and the second contains `correlationId=req-rx123456`. The `X-Correlation-ID` header matches per demo rules. Do not run the earlier MVC demo and this WebFlux demo simultaneously on the same port without changing `server.port` on one of them.

### 12.4. WebTestClient

Create `src/test/java/dev/example/correlationrx/ReactiveCorrelationTest.java`:

~~~java
package dev.example.correlationrx;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ReactiveCorrelationTest {

    @Autowired
    WebTestClient client;

    @Test
    void headerAndBodyUseSameId() {
        client.get().uri("/api/hello")
                .header("X-Correlation-ID", "req-rx123456")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-Correlation-ID", "req-rx123456")
                .expectBody()
                .jsonPath("$.correlationId")
                .isEqualTo("req-rx123456");
    }

    @Test
    void reactorContextHasRequestId() {
        client.get().uri("/api/reactor-context")
                .header("X-Correlation-ID", "req-ctx123456")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.correlationId")
                .isEqualTo("req-ctx123456");
    }
}
~~~

This test uses the WebFlux mock web environment and Spring Boot test auto-configuration, which does not directly exercise Reactor Netty network sockets. In projects with authentication, additional WebFilters, or exceptions, add appropriate test configs/integration tests. To test socket disconnects, network timeouts, or real streaming cancellations, use `RANDOM_PORT` and a real HTTP client.

## 13. WebFlux: Propagating Correlation IDs via WebClient

To call downstream services from a WebFlux pipeline, use an `ExchangeFilterFunction` on `WebClient` that reads Reactor Context at reactive subscription time.

Snippet inside `@Configuration`:

~~~java
@Bean
WebClient downstreamClient(WebClient.Builder builder) {
    return builder.filter((request, next) ->
            Mono.deferContextual(context -> {
                String id = context.getOrDefault(
                        RequestContextWebFilter.KEY, "");

                ClientRequest.Builder changed =
                        ClientRequest.from(request);

                if (!id.isBlank()) {
                    changed.headers(headers ->
                            headers.set("X-Correlation-ID", id));
                }

                return next.exchange(changed.build());
            }))
            .build();
}
~~~

This is a **method snippet** needing imports for `WebClient`, `ClientRequest`, `Mono`, `Bean`, and an enclosing configuration class. Inject Boot's `WebClient.Builder` to preserve Boot's customizations whenever available.

Remember that **context only flows along a properly composed reactive chain**. If a controller creates a Publisher and calls a detached `subscribe()`, context can be lost and request lifecycle tracking breaks. Return the Publisher from the controller or compose with `flatMap`/`then`; never rely on a fire-and-forget side effect to "propagate headers."

W3C trace context should be propagated separately by Micrometer/OpenTelemetry instrumentation. Never synthesize `traceparent` from `correlationId`; they differ in format and semantics.

## 14. Async Issues, Errors, and Response Streaming

### 14.1. Servlet Async

When a controller returns `Callable`, `DeferredResult`, or `ResponseBodyEmitter`, work continues after the Servlet Filter's `REQUEST` dispatch exits. Therefore:

- Do not treat the `REQUEST` dispatch filter `finally` block as guaranteed response completion.
- Request attributes are safer storage for IDs and start timestamps than bare `ThreadLocal`s.
- MDC must be restored on each involved thread/dispatch when logging is required.
- `HandlerInterceptor` can receive `preHandle` multiple times on redispatches; do not overwrite the start mark.
- Timeouts, closed connections, and network errors can bypass `afterCompletion`.
- Prefer framework HTTP observations or dedicated async callbacks when complete end-to-end timing is needed.

### 14.2. WebFlux Streaming

When a controller returns a `Flux` or long-lived SSE stream, WebFilter duration measures until Publisher complete/error/cancel, not just the first item. Long-lived streams spanning hours will skew percentile distributions; consider separating streaming endpoints into their own metric group.

Once the response commits, late errors cannot always change the HTTP status or write a fresh JSON error body. Never set correlation headers after streaming begins; set them before the chain or via `beforeCommit`.

### 14.3. Error Dispatches and /error

A Filter registered for the `ERROR` dispatcher can restore MDC/ID when the container dispatches to `/error`. However, error responses may be generated by `BasicErrorController`, Spring Security, or the Servlet container without invoking your intended MVC handlers. Verify actual status and headers. Having `correlationId` in a request attribute does not automatically add a `correlationId` field to every error JSON body.

In WebFlux, errors from `WebFilter`, annotated controllers, and `WebExceptionHandler` follow distinct paths. A timing `WebFilter` can observe an `ERROR` signal before an outer error handler determines the final status. Thus, log `UNSET` if status is still null in `doFinally`, and rely on server observations/error handlers for the final status.

### 14.4. Client Disconnects

When a client closes the connection mid-request, the server may log an I/O exception or a reactive `CANCEL`. The client will not necessarily receive the status/headers even if the server already populated them on the response object. Keep internal logs/traces keyed by correlation ID for investigation. Never treat "the server called `setHeader`" as proof the client received it.

## 15. Security, CORS, and Log Hygiene

A setup optimized for debugging can become a security vulnerability without proper controls.

- Never log `Authorization`, session `Cookie`s, passwords, or raw bodies just to extract an ID.
- Never derive IDs from emails, userIds, or tenantIds, as they leak PII and become predictable.
- Validate incoming correlation headers; prevent CR/LF log injection and oversized headers.
- Ensure client-supplied IDs are never treated as authentication or access-control proof.
- When users contact support, ask only for the correlation ID and timestamp—never access tokens.
- Never attach IDs as metric labels or unbounded span attributes that overload telemetry backends.
- Restrict log access and enforce appropriate retention periods.
- Never record raw URLs containing sensitive query strings in logs or metrics.
- When using OpenTelemetry/Micrometer, avoid creating conflicting custom trace contexts.
- Across retries or batch jobs, clearly define whether to issue a new ID or reuse one per transaction scope.
- Include `service.name`, `environment`, and `timestamp` in structured logs so ID searches stay distinct across services.

### 15.1. Expose X-Correlation-ID via CORS When Frontends Need It

In cross-origin browser requests, JavaScript cannot read custom response headers unless exposed by CORS. Configure `Access-Control-Expose-Headers: X-Correlation-ID` in Spring Security/gateway CORS policies. Do not confuse seeing the header in browser DevTools network tabs with JavaScript being permitted to read it.

Never open permissive wildcard CORS with credentials simply to let frontends read a correlation ID. Configure origins, credentials, and exposed headers strictly per security policy.

### 15.2. Structured Logging Beats Manual String Concatenation

Conceptual log entry:

~~~json
{
  "timestamp": "2026-11-07T12:00:00Z",
  "level": "INFO",
  "service": "orders-api",
  "httpMethod": "GET",
  "route": "/api/orders/{id}",
  "httpStatus": 200,
  "durationMs": 24.7,
  "correlationId": "req-order12345",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "message": "HTTP request completed"
}
~~~

This is an illustrative log event, not live system data. Avoid logging raw order IDs or query strings unless justified and controlled. Use separate fields for querying rather than forcing operators to parse free-form messages.

## 16. Knowing When to Write a Custom Timer

Writing a custom `Timer` makes sense when measuring **a business operation** invisible to built-in HTTP instrumentation—such as `reserveStock`, `calculateShipping`, or a domain transaction step. Name the metric distinctly, e.g., `order.reservation.duration`, with bounded tags like `outcome=success/failure`.

For HTTP server duration, Spring Boot already provides `http.server.requests`. Before creating a new Filter that records and publishes metrics, check your actual goal:

| Goal | Preferred Approach |
|---|---|
| Find all logs for one request | Correlation ID + logs + traces |
| Measure P95 server HTTP latency | Built-in `http.server.requests` |
| Time a specific controller/MVC handler for debugging | Scoped `HandlerInterceptor` or custom observation |
| Time SQL queries | Database instrumentation / query timer |
| Time outbound `WebClient` calls | Built-in `http.client.requests` / client observation |
| Time a business step | Custom `Observation`/`Timer` with dedicated name/tags |
| Follow multi-service requests | Distributed tracing + correlation |
| Measure frontend end-to-end | Browser/mobile telemetry; cannot be inferred solely server-side |

### 16.1. Sample Micrometer Timer for a Business Step

When a custom metric is genuinely needed:

~~~java
public String runBusinessOperation(MeterRegistry registry) {
    Timer.Sample sample = Timer.start(registry);

    String outcome = "success";
    try {
        return calculateResult();
    } catch (RuntimeException ex) {
        outcome = "failure";
        throw ex;
    } finally {
        sample.stop(Timer.builder("business.operation.duration")
                .tag("outcome", outcome)
                .register(registry));
    }
}
~~~

This **snippet** requires importing `io.micrometer.core.instrument.MeterRegistry`, `Timer`, and defining `calculateResult()`. It times a synchronous method. If `calculateResult()` returns a `Mono`/`Flux`, stopping the sample in the method's `finally` only measures **Publisher assembly**, not actual reactive execution. For reactive methods, create the Observation/Timer inside `Mono.defer` and stop it on completion/error/cancel.

Never attach `correlationId` to `Timer.builder(...).tag(...)`, and never use user/product/transaction IDs as tags.

### 16.2. Be Careful with Statuses on Exceptions

A domain-layer Timer may classify an exception as `outcome=failed`, while an HTTP controller translates that exception into 409 or 404. Business outcomes and HTTP statuses do not map 1:1; define metrics explicitly rather than collapsing every failure into a server 500.

## 17. Troubleshooting by Symptom

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Response has ID but logs lack it | MDC not set before logging, different thread, missing log pattern | Filter order, MDC propagation, logging config |
| Single request shows two correlation IDs | Filter/gateway generates a new ID per dispatch/hop | Request attribute persistence, trusted ingress policy |
| Async endpoint logs lose correlationId | `Callable`/`@Async` runs on another thread | `TaskDecorator`, tracing/context propagation |
| Normal requests log duration, async timeouts do not | `afterCompletion` skipped without redispatch | Async callbacks or Boot observations |
| One request counted twice in custom metric | Counted per REQUEST/ASYNC dispatch | Start attribute + single completion hook or built-in observation |
| P95 rises while handler logs stay short | Latency outside handler (downstream, queuing, network) | Compare HTTP server/client observations and traces |
| Filter logs 200 yet client gets 500 | Status logged too early before error dispatch | Log at the proper completion boundary |
| CORS frontend cannot read ID | Custom header not exposed | `Access-Control-Expose-Headers` |
| WebFlux loses ID after `publishOn` | Relied on `ThreadLocal` MDC | Reactor Context + context propagation |
| WebFlux stream stops without `COMPLETE` | Publisher cancelled/errored | `doFinally` signal, network logs |
| Metric series cardinality spikes | Tag contains raw path/ID | Route templates, low-cardinality tags |
| 401/403 lacks expected JSON error body | Spring Security handles before MVC advice | `AuthenticationEntryPoint`/`AccessDeniedHandler` |
| `/error` lacks `correlationId` in body | Container error handling differs from advice | `ErrorController`/`ErrorAttributes` and ERROR dispatch |
| Client has ID but downstream lacks it | HTTP client does not propagate header/context | `RestClient`/`WebClient` instrumentation/interceptors |
| `traceId` exists without `X-Correlation-ID` | Tracing enabled without custom header contract | Define explicit header contract or adopt `traceId` intentionally |
| Logged latency always 0ms | Truncated to integer milliseconds | Log fractional ms (`double`) or nanoseconds |
| Negative/anomalous duration | Used wall clock or compared across machines | `System.nanoTime` within one JVM, matched start/end |
| Missing HTTP metrics | Missing Actuator/registry or endpoint uncalled/unexposed | Dependencies, actuator exposure, metrics config |
| Filter runs twice | Both `@Component` and separate `FilterRegistrationBean` | Audit bean registrations and order |
| Client attacks with huge IDs | Unbounded header accepted | Validate length/charset at ingress/filter |

## 18. Pre-Production Checklist

- [ ] Chosen a single correlation header name and trusted-ingress policy.
- [ ] Enforced length limits, character allowlist, and duplicate-header handling; rejected CR/LF.
- [ ] Generated fresh IDs when missing/invalid without embedding PII.
- [ ] Stored ID in request attributes or `ServerWebExchange` attributes appropriately.
- [ ] Attached response header before response commits.
- [ ] Scoped MDC strictly to valid threads with proper cleanup/restoration.
- [ ] Tested async dispatches, `@Async`, `CompletableFuture`, and Reactor schedulers explicitly.
- [ ] Configured propagation to `RestClient`, `RestTemplate`, `WebClient`, or message brokers.
- [ ] Left W3C `traceparent` to tracing instrumentation when tracing is enabled.
- [ ] Structured logs include `correlationId`, `traceId`, `route`, `method`, `status`, and `duration`.
- [ ] Never attached `correlationId`, `traceId`, or raw URIs as high-cardinality metric tags.
- [ ] Used `http.server.requests` for HTTP server latency when Actuator is active without double-counting.
- [ ] Configured P95/P99 histograms/SLIs with verified scope and acceptable storage cost.
- [ ] Covered 400/401/403/404/500 paths, `/error`, and gateways under the correlation policy.
- [ ] Tested async completion, timeouts, disconnects, cancellations, and streaming.
- [ ] In WebFlux, tested `contextWrite`/`deferContextual` and avoided detached self-subscriptions.
- [ ] In MVC, verified filter dispatcher types and `shouldNotFilter...` hooks consistently.
- [ ] Configured CORS to expose the header only if browser frontends truly require it.
- [ ] Kept secrets/rejected values out of logs; enforced log retention and access control.
- [ ] Never used correlation IDs as idempotency keys or security principals.
- [ ] Documented the exact boundary measured by each duration metric.

## 19. Self-Check Questions

**Q1. Why should `System.currentTimeMillis` not be used to measure latency?**  
Because the wall clock can shift via clock adjustments or NTP, whereas `System.nanoTime` is suited for measuring elapsed duration within the same JVM.

**Q2. Does `OncePerRequestFilter` guarantee running strictly once across an entire async lifecycle?**  
No. It guards per request dispatch and thread; ASYNC/ERROR passes depend on hook overrides and Servlet registration.

**Q3. Why can `preHandle` be invoked twice for a `Callable`?**  
Because MVC can redispatch once the async result completes; keep the start timestamp in a request attribute so it is not reset.

**Q4. Does `HandlerInterceptor` measure the whole request when a client disconnects?**  
Not guaranteed. `afterCompletion` may not run if a timeout or network failure skips redispatch; use observations or appropriate async callbacks.

**Q5. Does MDC automatically follow WebFlux Reactor Context?**  
No. Reactor Context and `ThreadLocal` MDC are separate mechanisms; use an appropriate bridge/instrumentation.

**Q6. Should metrics be tagged with `correlationId` to find slow requests?**  
No. Cardinality is far too high. Look up individual requests in logs/traces; keep metrics to low-cardinality dimensions.

**Q7. Are Trace ID and Correlation ID always identical?**  
No. They can be intentionally unified, yet they often differ in format, scope, and origin.

**Q8. Are Filter response headers enough to cover Spring Security and gateway errors?**  
No. A Filter can cover security paths depending on order/mapping; errors returned by a gateway before reaching the backend must have the ID attached by the gateway.

**Q9. Why must `doFinally` in a WebFilter account for `CANCEL`?**  
Because client disconnects or cancellations terminate the Publisher abnormally, and should be logged as cancelled rather than reported as success.

**Q10. To time a business step inside a `Mono`, should you stop the `Timer` as soon as the method returns the `Mono`?**  
No. A `Mono` generally has not executed yet when constructed; time inside the reactive subscription and stop on completion/error/cancel.

## 20. Summary

**Correlation IDs** link logs and calls belonging to a single interaction; **request duration** tracks latency. In Spring Boot, establish the correlation ID early in a Servlet Filter or WebFlux WebFilter, propagate it via the right context, and return it in response headers under an explicit contract.

In Servlet MVC, `OncePerRequestFilter` can attach the ID and MDC before controllers run, while `HandlerInterceptor` reads route metadata and records handler duration. However, ASYNC/ERROR dispatches, timeouts, and network errors easily break naive custom timers: define callbacks and ownership clearly instead of assuming Filter `finally` or `afterCompletion` always marks the end of the HTTP request.

In WebFlux, use `ServerWebExchange` attributes, Reactor Context, and operators like `defer`/`contextWrite`/`doFinally`; never rely on `ThreadLocal` or manual `.subscribe()` calls for metadata propagation. For distributed tracing, let Micrometer/OpenTelemetry manage W3C trace context rather than crafting `traceparent` manually.

For production HTTP server SLOs, prefer **Micrometer's `http.server.requests`** instrumented by Spring Boot Actuator, paired with structured logging and distributed traces. Keep high-cardinality IDs in logs/traces and bounded dimensions in metrics. With clear rules defining who issues IDs, how they travel, what each duration measures, and who closes the measurement, your system stays traceable and reliable under load, async execution, and errors.

## 21. References

- Spring Framework 6.1 — OncePerRequestFilter Javadoc: https://docs.spring.io/spring-framework/docs/6.1.9/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Framework — AsyncHandlerInterceptor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/AsyncHandlerInterceptor.html
- Spring Framework — Asynchronous Requests in Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — WebFlux WebHandler API & WebFilter: https://docs.spring.io/spring-framework/reference/web/webflux-web-handler-api.html
- Spring Framework — WebClient Context: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-context.html
- Spring Boot 3.3 — Metrics and HTTP server observations: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot — Observability: https://docs.spring.io/spring-boot/reference/actuator/observability.html
- Spring Boot — Distributed Tracing: https://docs.spring.io/spring-boot/reference/actuator/tracing.html
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- Micrometer — Observation Concepts: https://docs.micrometer.io/micrometer/reference/observation/introduction.html
- Project Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html