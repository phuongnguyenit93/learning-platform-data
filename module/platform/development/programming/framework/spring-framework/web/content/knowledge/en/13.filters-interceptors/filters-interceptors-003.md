# OncePerRequestFilter and Behavior with Async/Error Dispatches in Spring MVC

## 1. Why Can “Once per Request” Be Misleading?

In a Spring MVC application, we often want to record a trace ID, measure processing time, add HTTP headers, or create a logging context. Placing logic in a Servlet Filter is sensible because Filters operate before/after the servlet in the processing chain.

However, a single HTTP request can be **dispatched multiple times** by the container:

- Initial pass: `DispatcherType.REQUEST`.
- The application starts asynchronous processing and the result is dispatched back: `DispatcherType.ASYNC`.
- The Servlet container forwards to an error page/endpoint: `DispatcherType.ERROR`.

If a filter runs again for the same request, generating a new trace, counting the request, emitting business events, or wrapping the response multiple times can cause inaccuracies. Spring provides `org.springframework.web.filter.OncePerRequestFilter` to ensure the filter **executes only once within a single request dispatch on a thread**, with explicit rules for re-execution on `ASYNC` or `ERROR`.

**Do not interpret the class name as “doFilterInternal runs strictly once across the entire lifecycle of an HTTP request regardless of dispatch/thread.”** If you explicitly enable participation in `ASYNC`/`ERROR`, `doFilterInternal` may run in those separate subsequent dispatches. Furthermore, an `ERROR` dispatch nested inside a `REQUEST` chain may pass through `doFilterNestedErrorDispatch` instead of `doFilterInternal`.

### Objectives

After this lesson, you can:

1. Distinguish Servlet `Filter`, Spring MVC `HandlerInterceptor`, `OncePerRequestFilter`, and dispatch types.
2. Accurately explain the “already filtered” request attribute, setting/removing it via `try/finally`, and the consequences for multiple dispatches.
3. Analyze `shouldNotFilterAsyncDispatch()`, `shouldNotFilterErrorDispatch()`, `shouldNotFilter(HttpServletRequest)`, `isAsyncDispatch()`, `isAsyncStarted()`, and `doFilterNestedErrorDispatch()`.
4. Combine **two configuration layers**: which **dispatcher types** the Servlet container registers the filter for, and which dispatches the filter **intentionally skips**.
5. Design tracing, logging, wrapping, thread-local, security, and cleanup logic without unintended duplicate runs.
6. Write a Spring Boot 3/Java 17 demo and test with Servlet mocks; understand the limits of `MockMvc` when simulating real `ERROR` dispatches.

**Context:** Spring MVC Servlet stack, Spring Framework 6.2.x, Spring Boot 3.x, Java 17+, Jakarta Servlet API. In Spring Boot 3/Spring Framework 6, imports are `jakarta.servlet.*`, not the legacy `javax.servlet.*`.

## 2. Where Does a Filter Sit in the HTTP Flow?

Typical synchronous flow:

```text
Client
   │ HTTP request
   ▼
Servlet container (Tomcat/Jetty/Undertow)
   │
   ├─ Filter A.doFilter(...)
   │    ├─ code before filterChain
   │    ▼
   │    Filter B.doFilter(...)
   │         └─ DispatcherServlet
   │              └─ Spring MVC HandlerInterceptor
   │                   └─ Controller
   │                   └─ View/HTTP message converter
   │
   ├─ Filter B code after filterChain
   └─ Filter A code after filterChain
   ▼
HTTP response
```

A Servlet Filter belongs to the **Servlet container filter chain**, so it can see the request before Spring MVC selects a handler, including paths that never reach a controller (depending on mapping). `HandlerInterceptor` belongs to **Spring MVC's HandlerExecutionChain** and operates after handler mapping; an interceptor does not completely replace a Servlet Filter.

When a controller uses `Callable<T>`, `DeferredResult<T>`, or Servlet async mechanisms, the initial thread may return control to the container **before the response completes**. The filter chain may finish a `REQUEST` pass and then experience a new `ASYNC` pass. This affects timing, trace completion, setting headers, and thread-local cleanup.

### 2.1. DispatcherType Table

| DispatcherType | When It May Occur | Key Points |
| --- | --- | --- |
| `REQUEST` | Client sends the initial HTTP request | The most common first dispatch |
| `ASYNC` | Servlet async completes a stage and redispatches | May run on a different thread; not automatically joined by every filter |
| `ERROR` | Container performs an error-page dispatch | Can be a separate filter chain or nested inside REQUEST |
| `FORWARD` | An internal servlet forward | One request can have multiple dispatch passes |
| `INCLUDE` | Another servlet/included resource | Whether the filter is called again depends on registration |

`OncePerRequestFilter` specifically has skip APIs for `ASYNC` and `ERROR`. For `FORWARD`/`INCLUDE`, the “already filtered” mechanism and dispatcher mapping still matter; do not infer that the class only ever relates to the first three types. In Spring MVC, `forward:...` can create a `FORWARD` dispatch, but only when the Servlet container executes the corresponding dispatch.

**Do not equate an HTTP request with a Servlet dispatch:** one HTTP request can go through multiple dispatches, and a dispatch is only one stage of processing.

## 3. What Does OncePerRequestFilter Provide?

Abstract class:

```java
public abstract class OncePerRequestFilter extends GenericFilterBean {

    @Override
    public final void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        // Spring manages skipping, the marker, and calling doFilterInternal.
    }

    protected abstract void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException;
}
```

*This is an educational API excerpt, not a full copy of Spring's source code. Override `doFilterInternal`; do not override the base class's `doFilter` method.*

Simplified decision diagram from the Spring 6.2 implementation:

```text
doFilter(request,response,chain)
       │
       ├─ Request/response not HTTP?
       │      └─ ServletException error
       │
       ├─ Dispatch skipped by shouldNotFilterAsyncDispatch /
       │  shouldNotFilterErrorDispatch or shouldNotFilter?
       │      └─ chain.doFilter, DO NOT call doFilterInternal
       │
       ├─ "already filtered" marker present on request?
       │      ├─ DispatcherType.ERROR
       │      │     └─ doFilterNestedErrorDispatch(...)
       │      └─ Other type
       │            └─ chain.doFilter, do not run doFilterInternal
       │
       └─ No marker yet
             ├─ request.setAttribute(marker, true)
             ├─ doFilterInternal(...)
             │     └─ usually calls chain.doFilter(...)
             └─ finally request.removeAttribute(marker)
```

This is not a global lock or a memory of “request IDs processed in the last 24 hours.” The marker is a **request attribute** that exists for the scope of the currently executing filter pass and is cleaned up in that pass's `finally` block.

### 3.1. Already-Filtered Attribute

By default, the base class builds the attribute name from the specific filter name plus the `.FILTERED` suffix; when a full name is unavailable, it may fall back to the class name. API:

- `getAlreadyFilteredAttributeName()`: determines the marker name; can be overridden when truly needed.
- `ALREADY_FILTERED_SUFFIX`: suffix constant used for the marker.
- The marker is normally set before calling `doFilterInternal` and removed in `finally` after it completes, even if the chain throws an exception.

Illustrative example:

```text
request.getAttribute("auditFilter.FILTERED") == null
    → set TRUE
    → run doFilterInternal
        → if the chain inside causes the same filter to be called nested:
           marker is still TRUE → do not run doFilterInternal again
    → finally remove attribute
```

The exact name depends on filter registration/bean name. **Do not build application logic that depends on internal marker strings**, and do not manually set/modify the framework's marker without a verified reason.

**Consequence:** if `REQUEST` has finished its filter pass and the request later enters an `ASYNC` dispatch, the previous marker has already been removed; if the filter is registered and does not skip `ASYNC`, `doFilterInternal` can run for a new pass. This is intentional behavior.

### 3.2. What If the Filter Does Not Call the Chain?

A filter blocking a request may skip calling `filterChain.doFilter(...)` (e.g., rejecting an unauthenticated request); the controller does not run. If it did call the chain, logic after the chain may run when Servlet async has started and **the response is not yet complete**. To distinguish this, check `isAsyncStarted(request)`.

All code must uphold the Servlet contract: do not write the response twice, do not use the response after it is committed, and do not accidentally skip exceptions/cleanup.

## 4. ASYNC Dispatch: Same HTTP Request, Multiple Processing Passes

An illustrative controller:

```java
@GetMapping("/slow")
Callable<String> slow() {
    return () -> "finished";
}
```

*This is an illustrative handler body; place inside a `@RestController` with `Callable` and `GetMapping` imports. Actual execution also depends on Servlet async support.*

General sequence:

```text
Thread T1                                      Thread T2 / T3
─────────                                      ──────────────
HTTP REQUEST
  → Filter.dispatch=REQUEST
  → DispatcherServlet/controller
  → MVC starts async
  → REQUEST filter chain returns
  → marker finally removed
                                               Callable runs in executor
                                               result is saved
                                               Servlet ASYNC dispatch
                                                 → Filter.dispatch=ASYNC (*)
                                                 → DispatcherServlet completes response
                                                 → filter chain returns
Response complete
```

(*) Only when the filter **is mapped for ASYNC** and does not skip ASYNC.

### 4.1. shouldNotFilterAsyncDispatch()

By default, this method returns **true**: `OncePerRequestFilter` skips `ASYNC` passes in `doFilterInternal` logic.

```java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return false; // want doFilterInternal to participate in ASYNC dispatches
}
```

Returning `false` **is not enough if the Servlet container has not registered the filter for `DispatcherType.ASYNC`**. You also need to configure filter registration, such as `FilterRegistrationBean#setDispatcherTypes(REQUEST, ASYNC)` and `setAsyncSupported(true)` if the application uses async.

When returning `false`, the filter can run **once per participating thread/dispatch**. This is useful for:

- Setting thread-local MDC/trace context for the thread handling the ASYNC pass.
- Applying response context in the later phase.
- Cleaning up resources according to each dispatch's lifecycle.
- Adding a header once the response truly completes (if not yet committed).

However, **do not** use it to blindly send emails, create invoices, or increment an “HTTP request count” metric on every `doFilterInternal`: one HTTP request can cause those side effects multiple times.

### 4.2. isAsyncDispatch() vs. isAsyncStarted()

| API | Question Answered | Example |
| --- | --- | --- |
| `isAsyncDispatch(request)` | “Is the current pass an ASYNC dispatch?” | During the subsequent pass after async work |
| `isAsyncStarted(request)` | “Is the request in async mode, meaning the current pass is not the final one?” | After the controller returns a Callable but before the request finishes |

Usage inside a filter:

```java
boolean redispatch = isAsyncDispatch(request);
try {
    filterChain.doFilter(request, response);
} finally {
    boolean stillAsync = isAsyncStarted(request);
    if (!stillAsync) {
        // In many normal flows, this is when
        // pass-completion tasks can be performed.
    }
}
```

This is only a state-observation pattern. If a filter **does not participate in ASYNC dispatches**, it has no chance to run `finally` on the final pass; in that case, use `AsyncListener`, an MVC callback, or another appropriate mechanism to emit an “HTTP request truly completed” event.

### 4.3. AsyncListener When Full Lifecycle Tracking Is Needed

To measure end-to-end time from the initial request until async completion, options include:

- Store the start timestamp in a request attribute on the `REQUEST` pass, without resetting it on redispatch.
- If the filter participates in every ASYNC dispatch, finish measuring when the response truly completes and the lifecycle is clear; do not measure repeatedly on every dispatch.
- For special workflows, register `AsyncListener#onComplete` / `onError` / `onTimeout` and handle re-registration in `onStartAsync` when a new async cycle starts; note that attaching a listener may depend on when `request.startAsync()` is called.
- Spring MVC also offers `CallableProcessingInterceptor` and `DeferredResultProcessingInterceptor` for MVC-specific hook points.
- Avoid using a single thread-local to hold whole-HTTP-request state when the request can switch threads.

**Note on context propagation:** request attributes travel with the Servlet request object, but `ThreadLocal`/MDC **do not automatically move to executor threads**. A filter participating in an `ASYNC` dispatch does not necessarily run on the thread where the `Callable` executed either. To propagate context into worker threads, configure an appropriate executor decorator or context propagation.

## 5. ERROR Dispatch: Separate Chain vs. Nested Dispatch

The Servlet container may handle errors in one of two forms that must be distinguished.

### 5.1. Separate ERROR Dispatch After REQUEST

Common sequence:

```text
REQUEST dispatch
  → filter.doFilterInternal(REQUEST)
  → downstream signals error / sendError
  → filter cleanup/finally, marker removed

New ERROR dispatch (possibly another thread)
  → filter.doFilterInternal(ERROR), IF:
       • filter registration has DispatcherType.ERROR
       • shouldNotFilterErrorDispatch() == false
  → /error or error page
```

By default, `shouldNotFilterErrorDispatch()` returns **true**, meaning `ERROR` dispatches are not passed to `doFilterInternal`.

To participate:

```java
@Override
protected boolean shouldNotFilterErrorDispatch() {
    return false;
}
```

Even so, without a `DispatcherType.ERROR` registration, the container will not invoke the filter on the error chain. And “`doFilterInternal` runs in ERROR” does not mean the filter automatically receives every Java exception: exceptions may already have been handled in the controller by `@ExceptionHandler` without any Servlet ERROR dispatch.

### 5.2. Nested ERROR Dispatch Within the Same REQUEST Chain

On some Servlet containers, after `response.sendError(...)` or a similar situation, an ERROR dispatch may happen **nested right inside the REQUEST chain on the same thread**, while the marker is still present.

```text
Filter.doFilter(REQUEST)
  └── set already-filtered marker = TRUE
      └── doFilterInternal(REQUEST)
          └── chain.doFilter(...)
              └── container nested ERROR dispatch
                  └── Filter.doFilter(ERROR)
                      ├── marker still TRUE
                      └── doFilterNestedErrorDispatch(...)
  └── finally remove marker
```

In the nested case, Spring invokes `doFilterNestedErrorDispatch(...)` and **does not automatically invoke `doFilterInternal(...)` again**, provided the filter does not skip ERROR. By default, the nested-error hook simply forwards to `filterChain.doFilter(...)`.

Some containers may revert request/response to the original wrappers on nested ERROR. If a filter wrapped the request/response to modify input/body/headers, the subclass may need to **re-wrap inside `doFilterNestedErrorDispatch`** to preserve desired behavior.

### 5.3. Overriding doFilterNestedErrorDispatch

```java
@Override
protected void doFilterNestedErrorDispatch(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain) throws ServletException, IOException {

    // If the filter uses custom wrappers, you can re-wrap
    // request/response here after evaluating container behavior.
    filterChain.doFilter(request, response);
}
```

This hook was added in Spring Framework 5.1.9. **Do not call `doFilterInternal` again just to “get a log”** unless you genuinely want to repeat the entire logic and have proven it safe. If using wrappers, a small dedicated “wrap only” helper for nested-error may be appropriate.

### 5.4. Comparison Table

| State | Marker Still Present? | Skipped by Default? | If Not Skipped and Filter Is Mapped |
| --- | --- | --- | --- |
| Initial REQUEST | No | No | `doFilterInternal(REQUEST)` |
| Nested REQUEST, marker present | Yes | No | `chain.doFilter` only |
| Separate ASYNC dispatch after REQUEST | Usually removed | **Yes** | `doFilterInternal(ASYNC)` |
| Separate ERROR dispatch after REQUEST | Usually removed | **Yes** | `doFilterInternal(ERROR)` |
| Nested ERROR while REQUEST marker is present | Yes | **Yes** | `doFilterNestedErrorDispatch(ERROR)` |
| Nested FORWARD/INCLUDE while marker is present | Yes | No async/error flag applies | Usually `chain.doFilter` only |

Do not infer exact execution counts solely from this table: filter registration, container behavior, async cycles, and how MVC returns errors determine actual dispatches. Multiple ASYNC passes can occur for one request if the async lifecycle continues; each pass must be evaluated under container and marker semantics.

## 6. Two Decision Layers: FilterRegistrationBean and shouldNotFilter*

A common mistake is thinking overriding `shouldNotFilterAsyncDispatch() = false` **automatically registers** the filter with the servlet container. In reality, both must be considered together:

1. **Registration layer**: which URL patterns and `DispatcherType.REQUEST/ASYNC/ERROR/...` is the filter mapped to; is async allowed?
2. **OncePerRequestFilter layer**: once the filter is invoked, do `shouldNotFilterAsyncDispatch()`, `shouldNotFilterErrorDispatch()`, and `shouldNotFilter(request)` skip the logic?

Explicit registration example in Spring Boot 3:

```java
@Bean
FilterRegistrationBean<DispatchTraceFilter> traceRegistration() {
    FilterRegistrationBean<DispatchTraceFilter> reg =
            new FilterRegistrationBean<>(new DispatchTraceFilter());

    reg.setName("dispatchTraceFilter");
    reg.setUrlPatterns(List.of("/*"));
    reg.setDispatcherTypes(EnumSet.of(
            DispatcherType.REQUEST,
            DispatcherType.ASYNC,
            DispatcherType.ERROR));
    reg.setAsyncSupported(true);
    reg.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);
    return reg;
}
```

*Illustrative snippet from the full project in Section 9; requires imports for `FilterRegistrationBean`, `DispatcherType`, `EnumSet`, `List`, `Ordered`, and `@Bean`.*

If async/error are not needed, map only REQUEST to reduce side effects and overhead. If needed, set mappings and flags consistently and test on the actual Servlet container you will deploy to. `setAsyncSupported(true)` does not make every handler run async automatically; it only allows the request to transition to async when the remaining components support it.

**Avoid registering a filter twice**: annotating a class with `@Component` while also manually creating `FilterRegistrationBean<>(filter)` can lead to duplicate mappings or unpredictable behavior depending on auto-registration. Choose one clear registration strategy. The demo instantiates `new DispatchTraceFilter()` only inside the bean registration and **does not annotate the filter with `@Component`**.

### 6.1. shouldNotFilter(HttpServletRequest)

Override when certain URLs or requests do not need the filter:

```java
@Override
protected boolean shouldNotFilter(HttpServletRequest request) {
    return request.getRequestURI().startsWith("/assets/");
}
```

If the application runs with a context path, check how the path is constructed. Do not rely blindly on `getRequestURI()` and a prefix without testing when mappings involve forwarded paths, percent-encoding, or context paths. For security, prefer framework matchers with proper semantics; do not accidentally introduce vulnerabilities by skipping sensitive endpoints.

**Execution order:** `shouldNotFilter(request)` is evaluated after the filter receives the request. It does not replace Servlet URL pattern mapping or Spring Security authorization.

## 7. Using Filters for Each Purpose Without Wrong Repetition

### 7.1. Correlation/Trace ID

A request may pass through REQUEST, ASYNC, and ERROR. Generate the ID **once** and store it in a request attribute:

```java
static final String TRACE_KEY = "example.traceId";

String trace = (String) request.getAttribute(TRACE_KEY);
if (trace == null) {
    trace = UUID.randomUUID().toString();
    request.setAttribute(TRACE_KEY, trace);
}

try {
    MDC.put("traceId", trace);
    filterChain.doFilter(request, response);
} finally {
    MDC.remove("traceId");
}
```

*This is an illustrative snippet inside a filter, requiring UUID and MDC/logging API imports. It does not cover the Callable's executor thread; context propagation to workers requires separate configuration.*

Across multiple dispatches, the request attribute preserves the trace ID across passes, whereas MDC is **per-thread** and must be set/removed on entering/leaving each thread. A filter participating in ASYNC redispatches only sets MDC on the redispatch thread itself. Use an executor decorator, task wrapper, or Spring context-propagation if you want the trace inside the thread executing `Callable`.

### 7.2. Measuring Whole-Request Duration

Do not measure “total request time” using a local variable restarted inside every `doFilterInternal`:

```java
long start = System.nanoTime();
filterChain.doFilter(request, response);
long elapsed = System.nanoTime() - start;
```

With async, `elapsed` on the REQUEST pass may reflect only the async-initiation phase, not the time until the response completes.

A better design:

1. Record the start timestamp **once** in a request attribute.
2. Pick a clear “request completed” point: `AsyncListener#onComplete`, an MVC async callback, or the final stage once the lifecycle is verified.
3. Use a separate marker to ensure the summary metric is emitted exactly once, even on ERROR dispatches.
4. Use a monotonic clock (`System.nanoTime()`) to compute durations; use wall clock if a display timestamp is needed.
5. Separate the **dispatcher count** metric (which can be > 1) from the **HTTP request count** metric (target 1).

### 7.3. Security/Filter Chain

Spring Security also uses Servlet Filters, and many implementations have their own once-per-request mechanisms and async/error handling. Do not randomly apply a “skip ASYNC/ERROR” policy because it can affect context, responses, or error pages. Filter ordering and dispatcher mapping belong to security design.

Do not hand-roll authentication by checking a simple token in a demo filter and treat it as equivalent to Spring Security. Prefer full Spring Security configuration and test anonymous/authenticated states, ASYNC, and ERROR when required.

### 7.4. Request/Response Wrappers

A filter can wrap the request/response to log payloads or adjust headers. Risks:

- Reading the request body in a filter before the controller without supporting a cached/re-readable body leaves the controller unable to read it.
- Wrapping the response and forgetting to copy the buffer out to the original response.
- On a nested ERROR dispatch, the container may revert wrappers to the originals. Override `doFilterNestedErrorDispatch` to re-wrap when truly needed.
- Async requires lifecycle-compatible wrappers; never read/modify an already committed response.
- Body logging can expose passwords, tokens, and personal data; enforce size limits and mask sensitive fields.

If using `ContentCachingRequestWrapper` or `ContentCachingResponseWrapper`, read the Javadoc: the request wrapper does not pre-read the body before downstream reads it; the response wrapper requires copying the body properly. Do not assume that merely constructing a wrapper makes the response readable across every dispatch.

## 8. Normal vs. Async vs. Error Examples

### 8.1. Synchronous REQUEST

```text
Client GET /sync
  → REQUEST filter doFilterInternal: count=1
  → Controller "sync"
  → Filter complete
  → HTTP 200
```

### 8.2. REQUEST Starts Async and ASYNC Dispatch

```text
Client GET /async
  → REQUEST filter doFilterInternal: count=1
  → Callable returned / MVC starts async
  → REQUEST filter ends, marker removed
  → Servlet ASYNC dispatch
  → ASYNC filter doFilterInternal: count=2
  → MVC completes response
  → HTTP 200
```

The flow above occurs only when the filter is mapped to ASYNC and `shouldNotFilterAsyncDispatch() == false`. With the default async skip, the number of `doFilterInternal` calls in this flow would be only 1.

### 8.3. MVC-Handled Exception vs. ERROR Dispatch

Suppose a controller has:

```java
@GetMapping("/problem")
String fail() {
    throw new IllegalArgumentException("invalid");
}

@ExceptionHandler(IllegalArgumentException.class)
ResponseEntity<String> handle(IllegalArgumentException ex) {
    return ResponseEntity.badRequest().body("bad");
}
```

*Illustrative snippet; must be placed in a controller/advice with imports.*

If Spring MVC's exception resolver handles it and writes a 400 response, the Servlet container **does not necessarily perform an ERROR dispatch**. Thus `shouldNotFilterErrorDispatch() == false` does not mean the filter gets another error-handling pass for every exception. When error metrics are needed, use exception handling or observe the HTTP status/final outcome at the appropriate point.

### 8.4. Separate ERROR Dispatch

```text
REQUEST filter starts
  → Servlet/application signals error
  → REQUEST filter ends, marker removed
ERROR dispatch initiated by container
  → ERROR filter gets a new pass, if mapped and not skipped
  → error endpoint/page renders
```

### 8.5. Nested ERROR Dispatch

```text
REQUEST filter active; marker TRUE
  → downstream sendError
  → container nested ERROR (within same chain/thread)
  → filter invoked again with dispatcherType=ERROR
  → marker TRUE → doFilterNestedErrorDispatch
  → does not increment doFilterInternal count
```

**Do not write a unit test that invokes REQUEST and then invokes ERROR after REQUEST finishes and claim you tested nested behavior.** Those are two different scenarios and take different execution branches.

## 9. Runnable Spring Boot 3 + Java 17 Application

Uses Spring Boot **3.3.13**, Java 17+, Maven. The demo illustrates a filter counting how many times logic runs on the **same request object**, sync/async endpoints, and a simple error handler. Servlet mock tests verify the ASYNC/ERROR branches more reliably than expecting MockMvc to synthesize a container error-page dispatch.

Structure:

```text
once-filter-dispatch-demo/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── DispatchDemoApplication.java
    │   ├── DispatchTraceFilter.java
    │   └── DispatchController.java
    └── test/java/example/
        ├── DispatchTraceFilterTest.java
        └── DispatchControllerTest.java
```

### 9.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>once-filter-dispatch-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
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
```

### 9.2. DispatchTraceFilter.java

```java
package example;

import java.io.IOException;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class DispatchTraceFilter extends OncePerRequestFilter {

    public static final String INTERNAL_COUNT =
            "example.trace.internalCount";

    public static final String NESTED_COUNT =
            "example.trace.nestedErrorCount";

    public static final String FIRST_DISPATCH =
            "example.trace.firstDispatcherType";

    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false; // filter participates in ASYNC pass if mapped by container
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        return false; // filter participates in ERROR pass if mapped by container
    }

    private static int next(HttpServletRequest request, String name) {
        Integer current = (Integer) request.getAttribute(name);
        int updated = current == null ? 1 : current + 1;
        request.setAttribute(name, updated);
        return updated;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        int count = next(request, INTERNAL_COUNT);

        if (request.getAttribute(FIRST_DISPATCH) == null) {
            request.setAttribute(
                    FIRST_DISPATCH, request.getDispatcherType().name());
        }

        try {
            filterChain.doFilter(request, response);
        } finally {
            // When REQUEST has async-started, the response is usually not complete yet.
            // Do not set a "completed" header too early.
            if (!isAsyncStarted(request) && !response.isCommitted()) {
                response.setHeader("X-Trace-Dispatches",
                        Integer.toString(count));
            }
        }
    }

    @Override
    protected void doFilterNestedErrorDispatch(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        next(request, NESTED_COUNT);
        filterChain.doFilter(request, response);
    }
}
```

This is **educational instrumentation**, not production metrics:

- The counter is stored in a request attribute, so it is reused across dispatches of the **same request**.
- `doFilterInternal` increments `INTERNAL_COUNT` on each pass the filter actually processes.
- `doFilterNestedErrorDispatch` increments a **separate** counter; a nested error does not increment internalCount.
- `response.isCommitted()` helps avoid modifying headers once the HTTP response is committed; the demo observes the header only in applicable scenarios.
- If a separate ERROR dispatch starts on the same request after the response is committed, setting headers may no longer be possible.
- The counter is not the number of HTTP requests. A single HTTP request can have `internalCount = 2` when an ASYNC redispatch occurs.

### 9.3. DispatchDemoApplication.java

```java
package example;

import java.util.EnumSet;
import java.util.List;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;

@SpringBootApplication
public class DispatchDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DispatchDemoApplication.class, args);
    }

    @Bean
    FilterRegistrationBean<DispatchTraceFilter> traceFilterRegistration() {
        FilterRegistrationBean<DispatchTraceFilter> registration =
                new FilterRegistrationBean<>(new DispatchTraceFilter());

        registration.setName("dispatchTraceFilter");
        registration.setUrlPatterns(List.of("/*"));
        registration.setDispatcherTypes(EnumSet.of(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC,
                DispatcherType.ERROR));
        registration.setAsyncSupported(true);
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);

        return registration;
    }
}
```

`DispatchTraceFilter` is **not** annotated with `@Component`. Only `FilterRegistrationBean` registers it with the Servlet container. Even when Spring Boot auto-registers other Servlet filters, this configuration controls the dispatch types solely for the demo filter itself.

### 9.4. DispatchController.java

```java
package example;

import java.util.concurrent.Callable;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DispatchController {

    @GetMapping("/sync")
    public ResponseEntity<String> sync(HttpServletRequest request) {
        Integer n = (Integer) request.getAttribute(
                DispatchTraceFilter.INTERNAL_COUNT);
        return ResponseEntity.ok("sync-" + n);
    }

    @GetMapping("/async")
    public Callable<String> async() {
        return () -> "async-ok";
    }

    @GetMapping("/handled-error")
    public ResponseEntity<String> handledError() {
        // This error is returned directly by the controller, requiring no
        // Servlet container ERROR dispatch.
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body("bad");
    }

    @GetMapping("/unhandled-error")
    public String unhandledError() {
        throw new ResponseStatusException(
                HttpStatus.INTERNAL_SERVER_ERROR, "demo failure");
    }
}
```

`/sync` lets you observe the request attribute: the controller sees that the counter was already incremented to 1 by the filter before the method ran. `/async` uses MVC async support with `Callable<String>`; the return value in `@RestController` is written as the body upon completion. `/handled-error` returns 400 per business logic without automatically triggering an ERROR dispatch. `/unhandled-error` illustrates a server error, though **it does not guarantee every container will dispatch ERROR in an identical sequence**; that must be integration-tested on a real container.

### 9.5. Run Commands and Output

From the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

In another terminal:

```bash
curl -i http://localhost:8080/sync
curl -i http://localhost:8080/async
curl -i http://localhost:8080/handled-error
```

Expected baseline results:

- `GET /sync` → HTTP 200; body `sync-1`; header `X-Trace-Dispatches: 1` when the response is uncommitted as the filter exits.
- `GET /async` → HTTP 200; body `async-ok`. If the container performs an ASYNC redispatch through the filter and the response still permits modifying headers, `X-Trace-Dispatches` may reflect 2 passes. Commit timing and conditions should be verified with logs or an integration test; do not treat this header value as an immutable contract.
- `GET /handled-error` → HTTP 400 and body `bad`; status 400 **does not by itself prove an ERROR dispatch occurred**.

Header order and other headers depend on the Servlet container; do not treat cURL output with all headers as a fixed stdout string.

## 10. Unit Testing the Filter per Dispatcher Type

To test filter logic independently of the container, use `MockHttpServletRequest` and `MockHttpServletResponse` from spring-test. These tests **simulate `dispatcherType`** and do not claim to fully replicate how a container initiates async/error dispatches.

File `src/test/java/example/DispatchTraceFilterTest.java`:

```java
package example;

import java.io.IOException;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class DispatchTraceFilterTest {

    @Test
    void firstRequestDispatchExecutesInternalOnce() throws Exception {
        DispatchTraceFilter filter = new DispatchTraceFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        FilterChain end = (req, res) -> { };
        filter.doFilter(request, response, end);

        assertEquals(1, request.getAttribute(
                DispatchTraceFilter.INTERNAL_COUNT));
        assertEquals("REQUEST", request.getAttribute(
                DispatchTraceFilter.FIRST_DISPATCH));
        assertNull(request.getAttribute(
                filterAlreadyFilteredName(filter)));
    }

    @Test
    void asyncRedispatchCanRunInternalAgain() throws Exception {
        DispatchTraceFilter filter = new DispatchTraceFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain end = (req, res) -> { };

        // Initial REQUEST pass finished; base class marker
        // was removed in finally.
        filter.doFilter(request, response, end);

        request.setDispatcherType(DispatcherType.ASYNC);
        filter.doFilter(request, response, end);

        assertEquals(2, request.getAttribute(
                DispatchTraceFilter.INTERNAL_COUNT));
    }

    @Test
    void separateErrorDispatchCanRunInternalAgain() throws Exception {
        DispatchTraceFilter filter = new DispatchTraceFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain end = (req, res) -> { };

        filter.doFilter(request, response, end);
        request.setDispatcherType(DispatcherType.ERROR);
        filter.doFilter(request, response, end);

        assertEquals(2, request.getAttribute(
                DispatchTraceFilter.INTERNAL_COUNT));
        assertNull(request.getAttribute(
                DispatchTraceFilter.NESTED_COUNT));
    }

    @Test
    void nestedErrorUsesDedicatedHookNotInternal() throws Exception {
        DispatchTraceFilter filter = new DispatchTraceFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        FilterChain end = (req, res) -> { };
        FilterChain requestChain = (req, res) -> {
            // Simulate ERROR dispatch nested directly inside the REQUEST chain
            // while the already-filtered marker is still present.
            request.setDispatcherType(DispatcherType.ERROR);
            filter.doFilter(request, response, end);
        };

        filter.doFilter(request, response, requestChain);

        assertEquals(1, request.getAttribute(
                DispatchTraceFilter.INTERNAL_COUNT));
        assertEquals(1, request.getAttribute(
                DispatchTraceFilter.NESTED_COUNT));
    }

    @Test
    void baseDefaultsSkipAsyncAndError() throws Exception {
        class DefaultFilter extends OncePerRequestFilter {
            int calls;

            @Override
            protected void doFilterInternal(
                    jakarta.servlet.http.HttpServletRequest request,
                    jakarta.servlet.http.HttpServletResponse response,
                    FilterChain chain)
                    throws ServletException, IOException {
                calls++;
                chain.doFilter(request, response);
            }
        }

        DefaultFilter filter = new DefaultFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain end = (req, res) -> { };

        filter.doFilter(request, response, end);
        request.setDispatcherType(DispatcherType.ASYNC);
        filter.doFilter(request, response, end);
        request.setDispatcherType(DispatcherType.ERROR);
        filter.doFilter(request, response, end);

        assertEquals(1, filter.calls);
    }

    private static String filterAlreadyFilteredName(
            DispatchTraceFilter filter) {
        // In unit tests there is no full filter name set by the container.
        // Base class falls back to class name + ALREADY_FILTERED_SUFFIX.
        return filter.getClass().getName()
                + OncePerRequestFilter.ALREADY_FILTERED_SUFFIX;
    }
}
```

Run `mvn test`. The test `nestedErrorUsesDedicatedHookNotInternal` is the key point: it triggers an ERROR pass **while REQUEST is still inside the chain**. Meanwhile, `separateErrorDispatchCanRunInternalAgain` invokes ERROR **after the REQUEST filter has exited**, because the marker has already been removed.

`baseDefaultsSkipAsyncAndError` demonstrates the base class defaults. `DispatcherType` in mocks is set manually, so unit tests do not prove the Servlet container mapped the filter to the right types. Mapping must be verified separately on a running application.

### 10.1. Testing the Spring MVC Async Endpoint

File `src/test/java/example/DispatchControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DispatchControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void synchronousControllerReturnsBody() throws Exception {
        mvc.perform(get("/sync"))
            .andExpect(status().isOk())
            .andExpect(content().string("sync-1"));
    }

    @Test
    void asyncControllerRequiresAsyncDispatchInMockMvc() throws Exception {
        MvcResult pending = mvc.perform(get("/async"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(content().string("async-ok"));
    }

    @Test
    void handledErrorDoesNotRequireServletErrorDispatch()
            throws Exception {
        mvc.perform(get("/handled-error"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("bad"));
    }
}
```

In MockMvc, `asyncDispatch(pending)` simulates the MVC redispatch step to obtain the `Callable` result; **do not use this test result to assert that every Servlet container/FilterRegistrationBean configuration will invoke the filter exactly twice**. To verify `DispatcherType.ASYNC`/`ERROR` mappings in real deployments, send HTTP tests against a server started on a random port or inspect logs in the corresponding Tomcat/Jetty container.

### 10.2. When Is `@SpringBootTest(webEnvironment = RANDOM_PORT)` Needed?

Unit tests simulate `OncePerRequestFilter` states; `MockMvc` tests the MVC async pipeline; however, **only a real embedded Servlet container** gives high confidence about:

- Whether filter registration includes REQUEST/ASYNC/ERROR.
- Whether the container routes `sendError` to a separate or nested ERROR dispatch.
- Whether request/response wrappers are reverted during nested ERROR.
- Whether headers can still be written when the filter finishes or if the response is already committed.
- How Spring Security/other Servlet filters affect the filter chain.

For production, add integration tests suited to the Tomcat/Jetty/Undertow environment in use. Do not assert that all containers produce the exact same error order; the number of ERROR dispatches and error timing can differ depending on how exceptions are handled.

## 11. Configuration Checklist

Before deploying a `OncePerRequestFilter`, answer:

1. **What is the filter's goal?** Tracing/logging, security, headers, wrapping, metrics, or request inspection?
2. Does it need to participate in `ASYNC` and `ERROR`, or only `REQUEST`?
3. Have `FilterRegistrationBean` or `web.xml` mapped the exact `DispatcherType` values?
4. If async is needed, do the filter/mapping have `asyncSupported` and does the container support async?
5. Do `shouldNotFilterAsyncDispatch` and `shouldNotFilterErrorDispatch` match your goal?
6. If skipping by URL, could `shouldNotFilter` accidentally skip a critical endpoint?
7. Does the logic use request attributes for cross-dispatch state and thread-appropriate MDC/thread-locals?
8. If errors can be nested, do you need to override `doFilterNestedErrorDispatch` to re-wrap request/response?
9. When async has started, are you accidentally setting headers, writing responses, computing durations, or closing resources too early?
10. Have you prevented duplicate business side effects when REQUEST + ASYNC + ERROR pass through?
11. Do tests distinguish separate ERROR from nested ERROR?
12. Have you verified both MockMvc/Servlet mocks and an embedded container with real dispatcher mappings?

## 12. Common Mistakes

| Misconception/Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| “OncePerRequestFilter runs strictly once per HTTP request” | Wrong when async/error redispatch is enabled | Understand the per-dispatch/per-thread guarantee |
| Overriding `shouldNotFilterAsyncDispatch=false` without mapping ASYNC | Filter never sees ASYNC | Configure **both** dispatcher types and the flag |
| Overriding `shouldNotFilterErrorDispatch=false` without mapping ERROR | Does not receive error dispatches | Map ERROR in Servlet registration |
| Forgetting `setAsyncSupported(true)` when filter is in an async chain | Async may be rejected or misconfigured | Register valid async support |
| Incrementing HTTP request metrics in every `doFilterInternal` | One HTTP request gets counted multiple times | Separate dispatch counter vs request counter |
| Measuring duration as soon as the REQUEST chain returns | Misses asynchronous processing phase | Use the proper completion hook/lifecycle |
| Setting MDC without `remove()` in finally | Traces leak across requests on the thread pool | Clean up thread-local in finally |
| Thinking participating in ASYNC redispatch puts MDC into the Callable thread | Callable logs lack trace IDs | Propagate context into the executor |
| Seeing 500 and assuming an ERROR dispatch occurred | Wrong conclusions about behavior | Distinguish MVC exception handlers from container errors |
| Unit test calling ERROR after REQUEST and calling it nested ERROR | Fails to test nested branch | Trigger nested pass before the outer filter returns |
| Wrapper stops working on nested ERROR | Container may revert to original wrappers | Override nested error hook and re-wrap when needed |
| Annotating filter `@Component` and also creating a `FilterRegistrationBean` | Hard to control registration/duplicate execution | Pick a single registration mechanism |
| Using `@Order` while omitting dispatcher type mapping | Filter does not receive desired dispatch passes | Ordering and mapping are two separate layers |
| Reading request body early without proper buffering | Controller receives no body | Design an appropriate cached request wrapper |
| Modifying headers after response is committed | Header missing or exception thrown | Check lifecycle/commit state; set headers at the right time |
| Wrapping response without copying body to real output | Empty response | Copy body at the right time; handle async/error |
| Using `ThreadLocal` instead of request attribute across async | Data lost across threads | Request attribute + explicit propagation |
| Disabling filter on all ERRORs as “unimportant” | Misses desired logging/security/error handling | Decide policy by response category |
| Assuming a Servlet Filter equals an MVC interceptor | Hook not called when there is no handler or on error dispatches | Choose the right layer |

## 13. Self-Check Questions

**1.** Why might `OncePerRequestFilter` invoke `doFilterInternal` twice during a single HTTP request?  
**Answer:** A request can have separate REQUEST and ASYNC (or ERROR) dispatches; the marker was removed after the previous pass; if the filter is mapped and does not skip, the next pass can invoke it again.

**2.** What does `shouldNotFilterAsyncDispatch()` return by default?  
**Answer:** `true`, meaning async dispatches are skipped.

**3.** What does `shouldNotFilterErrorDispatch()` return by default?  
**Answer:** `true`, meaning error dispatches are skipped.

**4.** If both methods above return `false`, does the filter automatically participate in ASYNC/ERROR?  
**Answer:** Not necessarily; the Servlet registration must also map the appropriate `DispatcherType` values.

**5.** What is the purpose of the already-filtered marker?  
**Answer:** To prevent `doFilterInternal` from running in nested calls when a request attribute indicates the filter is already processing a pass; the marker is removed in `finally`.

**6.** Does the marker persist forever until the HTTP response finishes?  
**Answer:** No; it is removed when the corresponding filter invocation finishes.

**7.** How do `isAsyncDispatch()` and `isAsyncStarted()` differ?  
**Answer:** One identifies the current dispatch type, while the other indicates the request is in async mode and thus not yet finished on the current pass.

**8.** How does a separate ERROR dispatch differ from a nested ERROR?  
**Answer:** A separate ERROR typically happens after the REQUEST filter chain finishes and the marker is removed; a nested ERROR enters while the marker is still present, so `doFilterNestedErrorDispatch` is called.

**9.** When do you need to override `doFilterNestedErrorDispatch`?  
**Answer:** When handling cases where the container replaces request/response wrappers or doing specialized work during nested ERROR; avoid unnecessarily re-running full general logic.

**10.** When an `@ExceptionHandler` handles a 400 error, does a Servlet ERROR dispatch necessarily occur?  
**Answer:** No, MVC can handle it completely without an ERROR dispatch.

**11.** Does MDC automatically appear in the thread executing a `Callable`?  
**Answer:** Not guaranteed; context propagation into the executor is required.

**12.** What is wrong with measuring request latency in a REQUEST filter when a controller returns a `Callable`?  
**Answer:** The filter may exit before async processing finishes; a lifecycle completion hook is needed.

**13.** Can `MockMvc` reliably verify that the Servlet container redispatches ERROR?  
**Answer:** Not fully; use Servlet mocks for class logic and integration tests with an embedded container for registration/lifecycle.

**14.** Why shouldn't HTTP requests be counted by the number of `doFilterInternal` calls?  
**Answer:** One HTTP request can involve multiple dispatcher invocations.

**15.** Does `FilterRegistrationBean#setOrder` replace `setDispatcherTypes`?  
**Answer:** No; one controls filter ordering, and the other controls dispatch types.

## 14. Official Sources

1. [Spring Framework 6.2 — OncePerRequestFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): base class, marker, default flags, async/error/nested dispatch.
2. [Spring Framework 6.2 — Web Async](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): MVC async model, Callable, DeferredResult, async dispatch.
3. [Spring Boot 3.3 — Servlet Filters](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): registration of Servlet components/FilterRegistrationBean.
4. [Jakarta Servlet API — DispatcherType](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/dispatchertype): REQUEST, ASYNC, ERROR, FORWARD, INCLUDE.
5. [Jakarta Servlet API — AsyncListener](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/asynclistener): lifecycle callbacks.
6. [Spring Test — MockMvc](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html): testing controllers, asyncDispatch, and request/response.
7. [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.3/servlet/architecture.html): filter chain in Servlet security and ordering/dispatch issues.

**In summary:** `OncePerRequestFilter` guarantees that filter logic **does not run twice within the same request dispatch**, rather than guaranteeing only one processing pass regardless of ASYNC/ERROR. To participate in ASYNC/ERROR, configure **both dispatcher mappings and skip flags**; for nested ERROR, use the dedicated hook. Design tracing/metrics/cleanup around the **entire HTTP lifecycle** and distinguish request count from dispatch count.
