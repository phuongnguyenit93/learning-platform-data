# Spring MVC — Choosing the Right Extension Point for Logging, Timing, and Correlation ID Propagation

## 1. Purpose

A Spring MVC application needs request observability: who called which endpoint, whether it failed, how long it took, and which logs belong to the same request. However, **logging**, **timing**, and **correlation ID propagation** do not necessarily belong in the same extension point.

If you put all logic into a `HandlerInterceptor`, you can miss requests rejected before reaching a controller. If you put all logic into a Servlet `Filter`, you may not yet know the **route template** such as `/api/orders/{id}`, or you may mismeasure an asynchronous request's duration. If you write custom timers and traces for every request while Spring Boot/Micrometer already provides instrumentation, you can end up with duplicate metrics and hard-to-correlate logs.

After this lesson, you can:

- Distinguish **Servlet Filter / OncePerRequestFilter**, **HandlerInterceptor / AsyncHandlerInterceptor**, **@ControllerAdvice / ResponseBodyAdvice**, and **Micrometer Observation/Tracing**.
- Choose the right layer for **request ID**, **MDC**, **access logs**, **handler timing**, **HTTP metrics**, **tracing**, security, and response customization.
- Explain the call sequence filter → `DispatcherServlet` → `HandlerMapping`/interceptor → controller → render/serialize → filter, and the lifecycle with async/error dispatches.
- Safely generate an `X-Request-ID` correlation ID shared across response headers, request attributes, MDC, and application logs; never blindly trust client-supplied IDs.
- Measure elapsed time with `System.nanoTime()`, distinguishing **filter dispatch**, **handler**, **overall HTTP request**, and service/downstream durations.
- Prevent data leaks when logging headers/queries/bodies; understand caching wrappers and limits of request/response payload logging.
- Write a runnable example with **Java 17+, Spring Boot 3.5.0 / Spring Framework 6.2**, along with MockMvc tests.

The context is **Spring Web MVC on the Servlet stack**, not WebFlux. Examples demonstrate common observability tools and a small runnable application; standalone fragments are noted where not complete classes.

## 2. Extension Point Selection Table by Goal

| Task | Extension Point to Consider | Why | Notes |
| --- | --- | --- | --- |
| Generate/validate correlation ID at request start, attach response header | Servlet `Filter` / `OncePerRequestFilter`, or trusted gateway | Runs before `DispatcherServlet`/handler; covers requests that never reach a controller | Must handle filter ordering, ASYNC/ERROR dispatches, MDC cleanup |
| Add request ID to current logs | Servlet Filter + SLF4J `MDC` | Needs early setup and guaranteed removal in `finally` | MDC typically relies on `ThreadLocal`, does not auto-cross to new workers |
| Log method/status/duration at Servlet boundary | Filter or container access log | Sees request/response, including pre-MVC errors | With async, `chain.doFilter` returns early, not meaning the HTTP response is done |
| Log handler name and URI **template** | `HandlerInterceptor` | Runs after handler mapping, knows route/handler | Does not cover everything rejected before mapping/filters |
| Measure duration of an MVC handler specifically | `HandlerInterceptor` + `System.nanoTime()` | Has `preHandle`, `afterCompletion`, route pattern | Must account for `AsyncHandlerInterceptor` and async lifecycle |
| Measure HTTP latency, call counts, status groups, traces | **Spring Boot Actuator + Micrometer Observation/Tracing** | Built-in instrumentation and conventions | Do not add duplicate timers; control tag cardinality |
| Measure a business/service step | `ObservationRegistry`, `Timer`, or service instrumentation | Reflects DB/business time, not whole HTTP | Choose low-cardinality names/tags and proper scope |
| Modify controller JSON response body | `ResponseBodyAdvice` or HTTP message converter | Intervenes right before MVC serializes response | Does not apply to all filter errors, files/streams/proxies |
| Standardize HTTP exception responses | `@RestControllerAdvice` / `@ExceptionHandler` / `ResponseEntityExceptionHandler` | Categorizes errors in Web MVC | Does not replace security filter exception handling |
| Authentication/authorization, CORS, certain security headers | **Spring Security filter chain** and security config | Protects early, covers before controllers | Do not use interceptors as the primary security layer |
| Access log produced by reverse proxy / servlet container | Proxy access log / container valve | Observes even when the Spring app cannot handle the request | Header/query data must be redacted properly |

**Practical rule:** use the fewest tools that still cover **the right boundaries**. Set IDs in a filter/gateway, handler-aware logs in an interceptor if genuinely needed, HTTP metrics/traces in Micrometer, business steps in services, and errors in advice. Never use `@ControllerAdvice` for end-to-end request timing or an MVC interceptor as a comprehensive security solution.

## 3. Order of Request Phases

### 3.1. Synchronous Request

~~~text
Client → Servlet container → Filter A (Request-ID/MDC)
       → Spring Security filter chain (if present)
       → DispatcherServlet / HandlerMapping
       → HandlerInterceptor.preHandle
       → HandlerAdapter invokes Controller method
       → HandlerAdapter handles return value
          ├─ REST @ResponseBody: HttpMessageConverter writes body,
          │  response MAY already be committed
          └─ View: prepares ModelAndView, NOT YET rendered
       → HandlerInterceptor.postHandle (when handler succeeds)
       → Render view if present
       → HandlerInterceptor.afterCompletion
       → Filter A finally (measures dispatch, cleans MDC)
       → HTTP response
~~~

This is a **simplified synchronous flow**, not depicting every exception/forward/async case. Filter order depends on registration. Key takeaway: when `@ResponseBody` or `ResponseEntity` is processed by the return-value handler, JSON may **already be serialized/committed before `postHandle`**; with traditional MVC views, `postHandle` runs **before** view rendering. Therefore, do not set critical headers in `postHandle` expecting them to always be sent; choose an early Filter, controller/`ResponseEntity`, or `ResponseBodyAdvice` depending on scope.

### 3.2. Filters Sit Outside MVC

Servlet filters use the Jakarta Servlet API:

~~~java
void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain) throws IOException, ServletException;
~~~

Because a filter sits in the container chain, it can perform work before/after `chain.doFilter(...)` without knowing any controller. It also runs for requests not mapped by MVC to a handler, depending on registered URL patterns and dispatcher types.

**Strengths:** early logging start, request ID, headers, wrapper/body policies, security integration. **Limitations:** may not yet know the exact route template; HTTP status and body may not yet be complete when the filter exits in async requests.

### 3.3. Interceptors Sit Inside MVC

`HandlerInterceptor` is applied by `HandlerMapping` to a matching handler:

~~~java
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception;

public void postHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        ModelAndView modelAndView) throws Exception;

public void afterCompletion(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex) throws Exception;
~~~

- `preHandle` runs before the handler; returns `false` to stop the handler chain.
- `postHandle` runs after synchronous handler execution, though it may already be too late to modify body/headers (especially JSON responses).
- `afterCompletion` runs after MVC finishes the request in normal cases, suited for cleanup/timing/logging; `ex` does not always hold the actual error if an exception was handled by a resolver.
- `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` can provide a route template like `/api/orders/{id}` after mapping, useful for low-cardinality logs/metrics.

Interceptors do not replace Spring Security: some requests or URL matching/filter paths do not traverse the same interceptor chain. Avoid using them as the sole authentication/authorization layer.

## 4. Correlation IDs: requestId, traceId, and Error Code

| Name | Example | Role |
| --- | --- | --- |
| `X-Request-ID` / `requestId` | `2f7c7b2b-f418-4297-b042-c86f86e76053` | Correlates a single request between response and logs |
| Distributed `traceId` | W3C trace context ID | Links multiple spans across services |
| `spanId` | One span within a trace | Distinguishes each operation |
| Public error code | `ORDER_NOT_FOUND` | Tells client the error category, stable across requests |
| HTTP status | 400, 404, 409, 500 | Expresses outcome per HTTP semantics |

**Request ID is not an error code.** The same `ORDER_NOT_FOUND` appears across many requests with different request IDs. If the system uses Micrometer Tracing/OpenTelemetry, do not assume `traceId == requestId`; a single trace can span multiple requests across services.

### 4.1. Generating IDs Safely

Example for a standalone application:

~~~java
String requestId = UUID.randomUUID().toString();
request.setAttribute("requestId", requestId);
response.setHeader("X-Request-ID", requestId);
~~~

Storing the ID in a request attribute lets components in the **same HTTP request** access it without relying solely on MDC. Set the header before the response can be committed; do not wait until `afterCompletion` to add headers.

Do not blindly trust `X-Request-ID` from arbitrary clients. A client-sent header can:

- Be overly long or contain invalid/log-injection characters.
- Collide with someone else's ID, causing spoofing and confusing correlation.
- Carry sensitive data inside the header value itself.

**Simple policy:** always generate the ID on the server and ignore client values. In systems behind a **trusted gateway**, you may allow the gateway to issue the ID while the backend validates length, charset, and trust source/forwarded headers. Avoid minting yet another request ID at every tier if you intentionally want to track one edge request.

### 4.2. MDC for Logs

SLF4J MDC stores context per thread in the logging backend (typically `ThreadLocal`):

~~~java
String previous = MDC.get("requestId");
MDC.put("requestId", requestId);
try {
    chain.doFilter(request, response);
} finally {
    if (previous == null) MDC.remove("requestId");
    else MDC.put("requestId", previous);
}
~~~

Restoring the previous value keeps nested scopes safe. Never place tokens, passwords, cookies, or sensitive emails in MDC because most log appenders print all MDC keys. MDC on a servlet thread **does not auto-propagate** to `@Async`, `CompletableFuture`, scheduled jobs, or other thread pools.

### 4.3. Async Context Propagation

If a request ID is needed inside `@Async`, you can:

- Pass `requestId` **explicitly** into the service/job, then set MDC inside the logging scope.
- Use a `TaskDecorator` on the specific executor: capture MDC on **submit**, install on the worker, and restore in `finally`.
- Use Micrometer Context Propagation/`ContextPropagatingTaskDecorator` when the system has observation/tracing context and properly registered accessors.

Simple scope fragment example:

~~~java
String requestId = (String) request.getAttribute("requestId");

executor.execute(() -> {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", requestId);
        service.execute();
    } finally {
        if (previous == null) MDC.remove("requestId");
        else MDC.put("requestId", previous);
    }
});
~~~

This is a fragment; `executor` and `service` must be properly configured. For background jobs outliving the request, pass an **immutable business context** to the job rather than holding `HttpServletRequest` or `ServletRequestAttributes` references long-term.

## 5. Choosing Where to Log

### 5.1. Information Worth Logging

Use structured or key-value logging:

~~~text
event=http_request_completed
requestId=2f7c7b2b-f418-4297-b042-c86f86e76053
method=GET route=/api/orders/{id} status=200 durationMs=12.4
~~~

`route` should be a template, not a path with real IDs, raw queries, or tokens. If MVC has not selected a handler yet, the filter does not know the template and can log method + status + duration + requestId without raw URLs. If routing details come from a reverse proxy, apply allowlisting/redaction.

**Do not log by default:** `Authorization`, `Cookie`, `Set-Cookie`, passwords, access tokens, raw request/response bodies, `?resetToken=...`, SQL credentials, or PII. For domains requiring auditing, separate audit logs with dedicated protection/retention policies and access controls.

### 5.2. Choosing a Filter for Dispatch Logs

~~~java
long started = System.nanoTime();
try {
    chain.doFilter(request, response);
} finally {
    long elapsed = System.nanoTime() - started;
    log.info("dispatch finished status={} elapsedMs={}",
             response.getStatus(), elapsed / 1_000_000.0);
}
~~~

Use `System.nanoTime()` (monotonic clock) for elapsed intervals; do not subtract `System.currentTimeMillis()` when accurate elapsed times are needed, since wall clocks can jump.

**Important boundary:** with Servlet async, `chain.doFilter` on the initial REQUEST dispatch may return right after MVC **starts** async, before the result is ready. Thus the measurement above is **dispatch duration**, not necessarily end-to-end HTTP latency.

### 5.3. Choosing an Interceptor When You Need the Route Template

After handler mapping succeeds:

~~~java
Object route =
        request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
String routePattern = route instanceof String s ? s : "unmapped";
~~~

When handler method names or business route metadata are needed, an interceptor sits in a more convenient spot. For metric labels, use the bounded `routePattern`, never individual concrete URLs (e.g., `/users/1234`, `/users/1235` explode cardinality).

**Caution:** the URI template attribute can vary or be absent depending on the handler mapping; always have a fallback. Interceptors do not handle requests rejected before mapping; never rely on a single interceptor as a comprehensive access log.

## 6. Measuring Time: What Are You Measuring?

A request can consist of:

~~~text
Client
  -> proxy / network
  -> Servlet Filter + Spring Security
  -> MVC mapping + interceptor
  -> controller
  -> service + database/downstream
  -> JSON serialization / view render
  -> response output
  -> client
~~~

Different measurements mean different things:

| Measurement | Typically Starts/Ends Where | Includes Network Outside the App? |
| --- | --- | --- |
| Gateway latency | Proxy receives request to proxy completes response | Can include significant network/proxy overhead |
| Server HTTP latency | HTTP server/framework observation lifecycle | Excludes full client network |
| Filter dispatch duration | Before/after `chain.doFilter` of **one dispatch** | No; may miss async waiting time |
| MVC handler elapsed | `preHandle` to lifecycle completion | Excludes stages before handler mapping |
| Service duration | Start/end of service operation | Business/service only |
| Database/client span duration | Until dependency call completes | Instrumentation-dependent, not whole request |

Never say “filter time = controller time” or “service time = HTTP time.” Do not sum nested timers because they overlap; for example, the HTTP span already includes the service span.

### 6.1. Measuring MVC with an Interceptor

Example:

~~~java
public boolean preHandle(
        HttpServletRequest request, HttpServletResponse response,
        Object handler) {
    if (request.getAttribute(START_KEY) == null) {
        request.setAttribute(START_KEY, System.nanoTime());
    }
    return true;
}

public void afterCompletion(
        HttpServletRequest request, HttpServletResponse response,
        Object handler, Exception ex) {
    Long start = (Long) request.getAttribute(START_KEY);
    if (start != null) {
        double elapsedMs = (System.nanoTime() - start) / 1_000_000.0;
        log.info("mvc_handler_done status={} elapsedMs={}",
                 response.getStatus(), elapsedMs);
    }
}
~~~

This is a fragment — `START_KEY`, `log`, and the enclosing class must be defined. Key detail for async requests: `preHandle` may be called again on the ASYNC dispatch, so set the start timestamp only when absent to avoid resetting the clock.

### 6.2. AsyncHandlerInterceptor and ASYNC Dispatches

Spring MVC supports:

~~~java
public interface AsyncHandlerInterceptor extends HandlerInterceptor {
    default void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws Exception {
    }
}
~~~

In a request that starts async processing, the initial Servlet thread returns to the pool and MVC invokes **`afterConcurrentHandlingStarted` instead of `postHandle` and `afterCompletion`** on the initial dispatch. When the result is ready, the container triggers an ASYNC dispatch and the interceptor is typically invoked again, with `afterCompletion` running at the end.

~~~text
REQUEST dispatch:
   interceptor.preHandle  -> controller returns Callable/DeferredResult
   interceptor.afterConcurrentHandlingStarted
   Servlet thread released; response not necessarily complete

Worker / callback:
   Produces async result

ASYNC dispatch:
   interceptor.preHandle (again)
   MVC processes result
   interceptor.postHandle / afterCompletion
~~~

Some timeouts, network errors, or async completions that bypass the expected redispatch can prevent `afterCompletion` from **ever firing**; when exact total durations and cleanup callbacks are required, use `CallableProcessingInterceptor`, `DeferredResultProcessingInterceptor`, `DeferredResult.onTimeout/onCompletion`, or Servlet `AsyncListener` as appropriate.

**Do not place `ThreadLocal` cleanup solely in `afterCompletion` once async has started:** the initial Servlet thread may already be reused before then. At `afterConcurrentHandlingStarted`, clean up thread-bound attributes set by the interceptor itself.

### 6.3. Filters and Dispatcher Types

Servlet dispatches include types such as `REQUEST`, `ASYNC`, and `ERROR`. `OncePerRequestFilter` has hooks:

~~~java
protected boolean shouldNotFilterAsyncDispatch();
protected boolean shouldNotFilterErrorDispatch();
~~~

Meaning:

- “Once” means once per **dispatch** and its filtering policy, not a guarantee to run strictly once across the entire HTTP request lifecycle regardless of async/error.
- To make a filter participate in ASYNC/ERROR dispatches, configure both the filter registration for the corresponding dispatcher type **and** the appropriate `shouldNotFilter*` policy.
- When the filter runs again in an async redispatch, **reuse** the request ID stored in the request attribute instead of minting a new ID for the same HTTP request.
- If the filter only runs on the REQUEST dispatch, MDC may be absent in an async redispatch; that does not prove the ID disappeared from the request attribute.

Do not count two dispatch logs as two HTTP requests; one async HTTP request can have multiple dispatches. If you want a single observation for the entire HTTP lifecycle, prefer framework-supported Micrometer instrumentation.

## 7. Micrometer Observation and Tracing: When Not to Write Your Own Timer

Spring Boot Actuator integrates Micrometer Observation for **metrics, log correlation, and tracing** based on configured dependencies/instrumentation. In Boot 3.5, HTTP server observation/metrics can be enabled with Actuator and appropriate registries/exporters.

Add dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Where applicable, the framework creates observations for HTTP requests. Use built-in conventions/tags such as method, status, and URI template for analysis instead of adding a timing interceptor if the goal is simply an **HTTP latency dashboard**.

**Do not abuse metric tags:**

- **Low-cardinality** tags have a bounded set of values (HTTP method, route template, status, outcome).
- Never attach user IDs, emails, request IDs, raw URLs, or tokens to metric tags; they create massive cardinality, raise costs, and can leak PII.
- Request IDs belong in log/tracing context, **not** as dimensions on timers/counters.

### 7.1. ObservationRegistry for a Business Step

When measuring an independent business step:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class PricingService {
    private final ObservationRegistry registry;

    public PricingService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public int computePrice(int quantity) {
        return Observation.createNotStarted("pricing.calculate", registry)
                .lowCardinalityKeyValue("kind", "standard")
                .observe(() -> quantity * 100);
    }
}
~~~

This is an illustrative in-memory computation class, not an endpoint in Section 9's project. `Observation` is only meaningful when appropriate observation handlers/metrics/tracing bridges are present in the app. For Spring Boot auto-instrumented HTTP handlers, avoid adding `@Observed` onto controllers without understanding it can produce **duplicate** observations.

### 7.2. Tracing Across Services

A `traceId` propagates via standard HTTP headers (typically W3C `traceparent`) when client instrumentation/injection is configured properly. When Service A calls Service B, a custom `MDC.put("requestId",...)` in A **does not propagate automatically to B**. HTTP client instrumentation or explicitly propagating a trusted/validated header is needed for custom IDs.

With `@Async`/thread pools, tracing context can also be lost unless propagated. Spring Boot 3.5 documents `ContextPropagatingTaskDecorator` on executors when Micrometer context propagation is needed.

### 7.3. Do Not Confuse Custom Request IDs with Official Tracing

You can keep `X-Request-ID` for support alongside Micrometer trace/span IDs. Both can appear together in logs. Define clear ownership to avoid generating competing IDs, overwriting context managed by the tracing framework, or propagating untrusted headers.

## 8. Logging Request/Response Bodies: Risks and Techniques

A frequent request: “Log the full JSON request/response for debugging.” For public APIs, this is one of the easiest ways to leak passwords, tokens, phone numbers, payment details, personal data, and operational secrets.

**Do not log bodies by default.** When diagnostics require it, use field allowlists, sampling, size caps, redaction, retention limits, and access controls. A leaked log stream can be just as dangerous as a leaked database.

### 8.1. ContentCachingRequestWrapper

Spring provides:

~~~java
ContentCachingRequestWrapper wrapped =
        new ContentCachingRequestWrapper(request, 16 * 1024);
chain.doFilter(wrapped, response);
byte[] cached = wrapped.getContentAsByteArray();
~~~

Requires importing `org.springframework.web.util.ContentCachingRequestWrapper`. The wrapper **caches only bytes read by downstream**; it does not eagerly drain the whole body before the controller runs. If the body was never read, the cache can be empty. Cache limits and overflow handling must be evaluated; do not log bytes decoded with the wrong charset, and do not assume the cache holds a complete copy of every streaming request.

### 8.2. ContentCachingResponseWrapper

When wrapping the response:

~~~java
ContentCachingResponseWrapper wrapped =
        new ContentCachingResponseWrapper(response);
chain.doFilter(request, wrapped);
// Illustrative only: if bytes must truly be inspected, enforce a redaction policy.
wrapped.copyBodyToResponse();
~~~

Requires importing `org.springframework.web.util.ContentCachingResponseWrapper`. **You must call `copyBodyToResponse()`** to flush the buffered body to the real response, otherwise the client may receive an empty body. In async/streaming flows, copying too early or too late can corrupt responses, bloat RAM, or break SSE/file downloads. Use only after understanding the lifecycle; normal JSON endpoints require adjustments when async dispatches occur.

### 8.3. Alternatives

- Log metadata (method/status/route/elapsed/request ID) instead of bodies.
- Enable sampling/structured logging in the observability layer with redaction.
- Use `RequestBodyAdvice`/`ResponseBodyAdvice` only when truly needing to inspect specific DTO types; they do not cover filter/security/proxy errors or all body types.
- Never include raw exception stack traces or request payloads in public error JSON.

## 9. Runnable Project: Filter + Interceptor + Safe Error Response

Spring Boot 3.5.0, Java 17, Maven example:

1. A Filter generates the request ID, sets the header early, saves the request attribute and MDC, logs **filter dispatch time**, and restores MDC.
2. An Interceptor logs **handler elapsed** and the route template, observing the HTTP status after MVC processing.
3. A Controller demonstrates the handler sees the same ID; advice returns safe JSON on a business conflict.
4. Tests verify consistent IDs, rejection of client-spoofed values, 409 errors, and 405/404 behavior at the HTTP boundary.
5. Actuator is included to illustrate the production path for HTTP observations; you do not need to write duplicate timers manually.

### 9.1. Project Structure

~~~text
logging-extension-demo/
├── pom.xml
├── src/main/
│   ├── java/demo/LoggingExtensionApplication.java
│   └── resources/application.properties
└── src/test/java/demo/LoggingExtensionTest.java
~~~

All main Java classes in this example are placed in one file for easy copying/running. In real projects, split each class into its own file.

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>logging-extension-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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

### 9.3. application.properties

~~~properties
# Demo only to display logs with request ID; use structured logging in production.
logging.pattern.level=%5p [rid:%X{requestId}]

# Do not automatically expose stacktraces/exception details from /error to clients.
server.error.include-stacktrace=never
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-exception=false

# Actuator exposes only safer endpoints by default; do not open * carelessly.
management.endpoints.web.exposure.include=health,info
~~~

Do not enable `management.endpoints.web.exposure.include=*` merely to view metrics; decide Actuator exposure/authentication per environment. Real instrumentation and registry exporters may require extra dependencies/configuration.

### 9.4. LoggingExtensionApplication.java

Place all code below in `src/main/java/demo/LoggingExtensionApplication.java`. There is only **one** top-level public class matching the filename; the remaining classes are package-private.

~~~java
package demo;

import java.io.IOException;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.AsyncHandlerInterceptor;
import org.springframework.web.servlet.HandlerMapping;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class LoggingExtensionApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoggingExtensionApplication.class, args);
    }
}

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class RequestCorrelationFilter extends OncePerRequestFilter {
    static final String REQUEST_ID_ATTR =
            RequestCorrelationFilter.class.getName() + ".requestId";
    static final String HEADER = "X-Request-ID";

    private static final Logger LOG =
            LoggerFactory.getLogger(RequestCorrelationFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // Demo: do not use client-supplied X-Request-ID values.
        Object existing = request.getAttribute(REQUEST_ID_ATTR);
        String id = existing instanceof String value
                ? value
                : UUID.randomUUID().toString();

        request.setAttribute(REQUEST_ID_ATTR, id);
        response.setHeader(HEADER, id);

        String previousId = MDC.get("requestId");
        long started = System.nanoTime();

        MDC.put("requestId", id);
        try {
            chain.doFilter(request, response);
        } finally {
            double dispatchMs =
                    (System.nanoTime() - started) / 1_000_000.0;

            // Do not log query/body/Authorization/raw path.
            LOG.info("filter_dispatch_done method={} status={} dispatchMs={}",
                    request.getMethod(), response.getStatus(), dispatchMs);

            // Restore because the Servlet thread may be reused.
            if (previousId == null) MDC.remove("requestId");
            else MDC.put("requestId", previousId);
        }
    }
}

@Component
class HandlerTimingInterceptor implements AsyncHandlerInterceptor {
    private static final Logger LOG =
            LoggerFactory.getLogger(HandlerTimingInterceptor.class);

    private static final String START =
            HandlerTimingInterceptor.class.getName() + ".start";

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        // When ASYNC dispatch invokes preHandle again, do not reset the start timestamp.
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
        // REQUEST pass started async; response is not yet complete.
        // Do not conclude the handler has finished here.
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {
        Object start = request.getAttribute(START);
        if (!(start instanceof Long started)) return;

        double elapsedMs = (System.nanoTime() - started) / 1_000_000.0;

        Object route = request.getAttribute(
                HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
        String pattern = route instanceof String s ? s : "unmapped";

        // Do not log exception.getMessage() or request body.
        LOG.info("mvc_handler_done route={} status={} handlerMs={}",
                pattern, response.getStatus(), elapsedMs);

        request.removeAttribute(START);
    }
}

@Configuration
class MvcLoggingConfig implements WebMvcConfigurer {
    private final HandlerTimingInterceptor interceptor;

    MvcLoggingConfig(HandlerTimingInterceptor interceptor) {
        this.interceptor = interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(interceptor)
                .addPathPatterns("/api/**");
    }
}

class OrderConflictException extends RuntimeException {
    OrderConflictException() {
        super("Synthetic internal condition: do not expose raw exception");
    }
}

record ErrorDto(
        String code,
        String message,
        String requestId) {
}

@RestControllerAdvice
class ApiErrors {
    @ExceptionHandler(OrderConflictException.class)
    ResponseEntity<ErrorDto> onConflict(
            OrderConflictException ex,
            HttpServletRequest request) {

        String requestId =
                (String) request.getAttribute(
                        RequestCorrelationFilter.REQUEST_ID_ATTR);

        // Do not return ex.getMessage() to the client.
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ErrorDto(
                        "ORDER_CONFLICT",
                        "Invalid operation in the current state.",
                        requestId));
    }
}

@RestController
@RequestMapping("/api")
class OrderController {
    @GetMapping("/orders/{id}")
    Map<String, Object> find(@PathVariable long id) {
        String requestId = MDC.get("requestId");
        // Synchronous demo: MDC is set by the filter on the Servlet thread.
        return Map.of("id", id,
                "status", "ok",
                "requestId", requestId);
    }

    @GetMapping("/orders/conflict-demo")
    Map<String, Object> conflict() {
        throw new OrderConflictException();
    }
}
~~~

**Note on mapping precedence:** `GET /api/orders/conflict-demo` has a literal mapping, so Spring MVC prioritizes that static path ahead of `/api/orders/{id}`. The route template seen in the interceptor for the detail endpoint will be `/api/orders/{id}`, avoiding one metric label per order ID.

**Note on timing:** in this code, `dispatchMs` is the filter chain duration for the current dispatch. For synchronous requests, it closely approximates in-app HTTP processing time excluding network/client rendering. `handlerMs` starts after mapping and ends at MVC `afterCompletion`; the two **must not be added together**. With async, the initial filter measurement does not capture full async waiting; the interceptor uses the `START` attribute until the final ASYNC dispatch, though if an async timeout/error skips redispatch, dedicated callbacks are required to avoid missing metrics.

### 9.5. Running and Observing Logs

Inside `logging-extension-demo`:

~~~bash
mvn spring-boot:run
~~~

Try GET:

~~~bash
curl -i 'http://localhost:8080/api/orders/42'
~~~

Example body:

~~~json
{"id":42,"status":"ok","requestId":"2f7c7b2b-f418-4297-b042-c86f86e76053"}
~~~

The `X-Request-ID` header on the HTTP response must **match** `body.requestId` **exactly**; each request gets a different UUID. Console logs look roughly like:

~~~text
INFO [rid:2f7c7b2b-f418-4297-b042-c86f86e76053]
mvc_handler_done route=/api/orders/{id} status=200 handlerMs=3.12

INFO [rid:2f7c7b2b-f418-4297-b042-c86f86e76053]
filter_dispatch_done method=GET status=200 dispatchMs=8.45
~~~

The measurements/times/IDs in this example are **illustrative only** and not fixed output; environment, JIT, templates, and JVM warm-up change timings across runs.

### 9.6. Testing Errors, Spoofed Headers, and 405

Suppose a client sends its own `X-Request-ID`:

~~~bash
curl -i 'http://localhost:8080/api/orders/42' \
  -H 'X-Request-ID: attacker-chosen'
~~~

The server generates a fresh UUID instead of using `attacker-chosen`. That reduces the risk of log spoofing/collisions from HTTP clients.

Try the domain conflict:

~~~bash
curl -i 'http://localhost:8080/api/orders/conflict-demo'
~~~

HTTP 409, response body equivalent to:

~~~json
{
  "code": "ORDER_CONFLICT",
  "message": "Invalid operation in the current state.",
  "requestId": "2f7c7b2b-f418-4297-b042-c86f86e76053"
}
~~~

The exact ID will differ and match the `X-Request-ID` response header. Tests must also confirm the string `"Synthetic internal condition"` is absent from the body.

Try an unmapped POST:

~~~bash
curl -i -X POST 'http://localhost:8080/api/orders/42'
~~~

The framework normally returns **405 Method Not Allowed**. The filter can still attach `X-Request-ID` to this request even though no handler method is invoked. Because an interceptor is not guaranteed to see all pre-mapping errors, do not use it as the sole access log.

### 9.7. MockMvc Tests: Request ID, Status, and Response Safety

Create `src/test/java/demo/LoggingExtensionTest.java`:

~~~java
package demo;

import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoggingExtensionTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void idMatchesHeaderAndJsonBody() throws Exception {
        MvcResult result = mvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andReturn();

        String id = result.getResponse().getHeader("X-Request-ID");
        assertNotNull(id);
        UUID.fromString(id);

        JsonNode body = mapper.readTree(
                result.getResponse().getContentAsString());
        assertEquals(id, body.path("requestId").asText());
        assertEquals(42, body.path("id").asInt());
    }

    @Test
    void ignoresUntrustedClientRequestId() throws Exception {
        MvcResult result = mvc.perform(get("/api/orders/42")
                .header("X-Request-ID", "attacker-chosen"))
            .andExpect(status().isOk())
            .andReturn();

        String id = result.getResponse().getHeader("X-Request-ID");
        assertNotNull(id);
        UUID.fromString(id);
        assertFalse("attacker-chosen".equals(id));
    }

    @Test
    void conflictKeepsHttpStatusAndHidesInternalMessage()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/api/orders/conflict-demo"))
            .andExpect(status().isConflict())
            .andReturn();

        String id = result.getResponse().getHeader("X-Request-ID");
        assertNotNull(id);

        String serialized = result.getResponse().getContentAsString();
        JsonNode body = mapper.readTree(serialized);

        assertEquals("ORDER_CONFLICT", body.path("code").asText());
        assertEquals(id, body.path("requestId").asText());
        assertFalse(serialized.contains("Synthetic internal condition"));
    }

    @Test
    void filterCoversMethodNotAllowedBeforeHandler()
            throws Exception {
        MvcResult result = mvc.perform(post("/api/orders/42"))
            .andExpect(status().isMethodNotAllowed())
            .andReturn();

        assertNotNull(result.getResponse().getHeader("X-Request-ID"));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

These MockMvc tests demonstrate HTTP responses and filter registration. They do not prove real latency or metric accuracy under heavy load. To test logs, use an in-memory test appender or structured log capture isolated from sensitive data; to test async, add a controller returning `Callable`/`DeferredResult` and test `asyncDispatch` + timeout callbacks.

## 10. Async and Pre-MVC Errors: Additional Design

If the system has many async or streaming endpoints, **do not rely solely on synchronous examples**. Several scenarios:

### 10.1. @Async and CompletableFuture

`@Async` methods run on another executor; `requestId` in MDC from the filter does not automatically follow to the worker. Use a `TaskDecorator`:

~~~java
public final class RequestIdTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        String requestId = MDC.get("requestId"); // Capture at submit time.
        return () -> {
            String previous = MDC.get("requestId");
            try {
                if (requestId == null) MDC.remove("requestId");
                else MDC.put("requestId", requestId);
                task.run();
            } finally {
                if (previous == null) MDC.remove("requestId");
                else MDC.put("requestId", previous);
            }
        };
    }
}
~~~

This is a Java class requiring `org.springframework.core.task.TaskDecorator` and `org.slf4j.MDC` imports. Register it via `ThreadPoolTaskExecutor#setTaskDecorator(...)` on **the exact executor** running the task. Never pass full `ServletRequestAttributes` into background jobs outliving the response.

### 10.2. @ControllerAdvice Does Not Cover Every Error

A `@RestControllerAdvice` is well suited for mapping domain exceptions from controllers/services to HTTP bodies. However:

- Spring Security authentication errors can be handled **inside the filter chain**, before `DispatcherServlet`. Configure `AuthenticationEntryPoint`/`AccessDeniedHandler` in Security.
- A JSON serialization failure can occur after the response is already committed; rewriting the error body is no longer guaranteed.
- Gateways/proxies can emit 502/503/504 themselves when upstream is unreachable; Boot error configs cannot control those.

This is why request IDs should be attached early in a filter or gateway, not solely inside advice. If a proxy also attaches an ID, define a contract for trust source, format, and propagation.

### 10.3. Exceptions Inside a Filter

If a filter calls a dependency and throws an exception before `DispatcherServlet`, `@RestControllerAdvice` usually cannot catch it because it never entered MVC handler invocation. Avoid placing complex business logic in filters. If a filter must handle errors, let the container/security error handler or a filter-boundary error policy handle it safely without exposing exception internals.

### 10.4. Filter Order and Spring Security

With `DelegatingFilterProxy`/Spring Security, the request-ID filter may run before or after the security chain depending on order. To ensure the ID appears on 401/403 responses as well, ensure the filter wraps security rejections **from outside / early enough**, or let a trusted gateway generate the ID; verify with integration tests. Never assume from a single `@Order` that every registration between Boot, servlet container, and security is right across all deployments.

### 10.5. Response Headers and Write Timing

- Set `X-Request-ID` at the **start of the filter chain** while the response is uncommitted.
- Setting `"X-Elapsed-Ms"` in `afterCompletion` may be too late: JSON may already be written or the response committed. If exposing a duration header is mandatory, use an earlier hook/suitable response wrapper and design for async/streaming; a simpler option is **not exposing a latency header** and using metrics/logs instead.
- For streaming, SSE, and file downloads, measuring “request complete” must consider when the stream/connection closes, not merely when the controller method returns.

## 11. Common Mistakes

1. **Using an interceptor as the sole authorization gate:** requests may be processed/accessed along paths not matching the interceptor; use Spring Security/filter chains.
2. **Using a filter to log route templates before handler mapping:** at that point the filter usually has only the raw URL, risking PII/cardinality issues. When handler routes are needed, log in an interceptor or MVC instrumentation.
3. **Measuring `chain.doFilter` and calling it end-to-end async latency:** the initial Servlet async dispatch can return before the request finishes.
4. **Creating the request ID inside the controller:** errors before the controller lack an ID.
5. **Trusting `X-Request-ID` from clients without validation:** invites collisions, log injection, and spoofing.
6. **Forgetting `MDC.remove`/restore in `finally`:** pooled threads can retain the previous request's ID.
7. **Assuming MDC automatically enters `@Async`:** requires explicit context or a decorator/snapshot.
8. **Putting request ID into metric labels:** one label per request explodes cardinality.
9. **Logging full queries/bodies/headers:** risks leaking tokens/PII; default to allowlisted metadata.
10. **Using `ContentCachingResponseWrapper` and forgetting `copyBodyToResponse()`:** clients may receive empty bodies.
11. **Using `ContentCachingRequestWrapper` and thinking it pre-reads the body:** the cache holds only bytes already read downstream.
12. **Setting headers in `postHandle` or `afterCompletion`:** with `@ResponseBody`, the body may already be committed.
13. **Creating a timing interceptor duplicating Micrometer instrumentation:** double-counts metrics and adds overhead.
14. **Building timers with `System.currentTimeMillis()`:** wall-clock time can jump; use `System.nanoTime()`.
15. **Ignoring ASYNC/ERROR dispatches and filter registrations:** logs one request as two or loses correlation IDs.
16. **Logging DB `exception.getMessage()` and returning it to clients:** leaks internals; use safe error DTOs and secure logs.
17. **Putting business logic in filters:** hard to test, disrupts security/lifecycles, and bypasses transaction/service boundaries.
18. **Ignoring exceptions/timeouts in async processing:** `afterCompletion` may not run on every exceptional async path.
19. **Confusing `requestId` with `traceId`:** a custom ID does not automatically create distributed spans or cross HTTP services.
20. **Assuming one MockMvc test proves full production logging:** container/gateway/security/CORS/streaming/lifecycles still require integration tests.

## 12. Implementation Checklist

- **Clear goal:** do you need request IDs, access logs, handler logs, business timing, or distributed tracing?
- **Ownership:** does the gateway or app generate request IDs? Which headers are trusted? Who manages MDC?
- **Boundaries:** choose Filter before MVC, Interceptor after mapping, Advice for exceptions, Micrometer for observations.
- **Timing:** define start/end properly for sync and async requests; never sum nested timers.
- **Privacy:** log allowlisted fields only; never print `Authorization`, `Cookie`, raw URLs/queries/bodies, or secrets.
- **Cardinality:** metric tags use route templates and HTTP method/status/outcome; never user ID or request ID.
- **Lifecycle:** restore MDC at the end of a dispatch; use context propagation on thread switches; verify registration on ERROR/ASYNC dispatches.
- **Security:** ensure 401/403 carry a request ID if policy requires it; interceptors are not an auth layer.
- **Errors:** advice never returns stack traces/SQL; filter/serializer/proxy exceptions have their own policies.
- **Overhead:** sampling, log levels, executor queues, instrumentation cost, retention, and log access controls.
- **Tests:** successful GET, 400/404/405, security denial, 500 exception, async completion/timeout, concurrent requests; verify header ID ↔ body/logs and confirm no PII leaks.
- **Operations:** latency dashboards by p50/p95/p99, 4xx/5xx rates, by route/status, traces for slow requests; clear workflow to look up logs by request ID.

## 13. Exercises

**Exercise 1 — Choosing extension points:** For each requirement, choose Filter, Interceptor, ControllerAdvice, ResponseBodyAdvice, or Micrometer: (a) generate a request ID even for 401/403, (b) log the `/orders/{id}` template, (c) standardize 409 errors, (d) measure HTTP p95, and (e) add a custom field to JSON DTOs.

**Exercise 2 — Timing:** A controller returns `Callable<ResponseEntity<?>>` taking 1 second in a worker, while the initial filter dispatch runs for only 10 ms. Why might a timer in the filter's `finally` log 10 ms instead of ~1 second? Which callbacks/instrumentation should be used to measure the complete HTTP request?

**Exercise 3 — MDC:** Two consecutive requests are processed on the same thread. If `finally` MDC restoration is omitted, which ID might appear in the second request's logs? Write a careful capture/restore block that handles exceptions thrown by the task.

**Exercise 4 — Tracing:** Service A returns an HTTP request ID to the client and calls Service B. Why doesn't B automatically see the same `traceId`? Name the trace context propagation mechanism via HTTP clients/gateways and distinguish custom request IDs from distributed traces.

**Exercise 5 — Log redaction:** A request contains `Authorization: Bearer ...`, `?resetToken=...`, and a JSON password. Design a safe log line with method/status/route template/elapsed/requestId and none of the sensitive values.

**Exercise 6 — Interceptor:** If a Controller returns JSON, is `postHandle` a safe place to set a response header? Explain when the response is already committed and choose Filter/`ResponseBodyAdvice` where needed.

**Exercise 7 — Unit/MockMvc:** Extend `LoggingExtensionTest` to verify the UUID between header and body always matches, and is never `attacker-chosen` when the client supplies its own ID.

**Exercise 8 — Metrics:** If you attach a `userId` label to every `http.server.requests` timer, what happens to the number of time series? Propose a lower-cardinality tag set.

**Exercise 9 — Async dispatch:** Write a `Callable<String>` endpoint and an `AsyncHandlerInterceptor` with a stopwatch stored in a request attribute. Observe REQUEST/ASYNC dispatch callbacks and test with `asyncDispatch`.

**Exercise 10 — Architecture:** An app has Spring Security, MVC, Actuator, 10 downstream services, and a gateway. Sketch where request IDs are created, where tracing headers are injected/extracted, where HTTP is measured, where service spans are measured, and where redaction happens. Avoid instrumenting the same thing twice.

## 14. Key Takeaways

- **Servlet Filter** is the right boundary for request IDs, MDC, and dispatch-level request logging; it operates before MVC and does not necessarily know the handler template.
- **HandlerInterceptor** fits route/handler-aware logging and MVC-scoped timing; it does not replace security filters.
- **AsyncHandlerInterceptor** must account for `afterConcurrentHandlingStarted` and redispatches; an initial filter's `chain.doFilter` does not necessarily measure full async HTTP latency.
- **Micrometer Observation/Tracing** is the best default for HTTP metrics and distributed traces; avoid duplicate custom timers/tags and high cardinality.
- **MDC** is for log correlation and must be cleaned up; propagating across threads requires a `TaskDecorator`/snapshot or explicit parameters.
- **Request IDs** should be generated/controlled by the server/trusted gateway, written to headers early, and used consistently in logs and safe error responses.
- **Measuring at the right boundaries, logging the right data, and cleaning up on the right lifecycle** matter far more than the sheer number of interceptors/filters added.

## 15. Official References

- [Spring Framework 6.2 — Servlet Filters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): filters and lifecycle characteristics.
- [Spring Framework 6.2 — Interceptors](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html): `WebMvcConfigurer` and interceptor registration.
- [Spring Framework 6.2 — Handler Interception](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html): `preHandle`, `postHandle`, `afterCompletion`, response handling.
- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): `Callable`, `DeferredResult`, `AsyncHandlerInterceptor`, ASYNC dispatch.
- [Spring Framework 6.2 — OncePerRequestFilter](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): REQUEST/ASYNC/ERROR dispatcher behavior.
- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): Micrometer Observation, metrics, tracing, context propagation.
- [Spring Boot 3.5 — HTTP Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): distributed tracing and correlation.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent`/`tracestate`.
- [SLF4J Manual — MDC](https://www.slf4j.org/manual.html): log correlation context.
