# OncePerRequestFilter and REQUEST, ASYNC, ERROR Dispatch Types in Spring Boot

## 1. Learning Objectives

OncePerRequestFilter is Spring Framework's base class for building a Servlet Filter protected against repeated execution of doFilterInternal within **the same request dispatch**. Its class name is easily misunderstood: a single client HTTP request can go through multiple Servlet dispatches, such as the initial REQUEST, an ASYNC redispatch after a controller returns a Callable, and an ERROR dispatch to an error page. Consequently, one logical HTTP request can cause a OncePerRequestFilter to invoke doFilterInternal more than once if the developer explicitly enables those dispatch types.

This lesson belongs to **Filters and Interceptors** in **Spring Boot - web-runtime**. After this lesson, you will be able to:

1. Distinguish between **logical HTTP request**, **Servlet dispatch**, **FilterChain**, and **thread**.
2. Explain the **already filtered** marker and the hooks **doFilterInternal**, **shouldNotFilter**, **shouldNotFilterAsyncDispatch**, **shouldNotFilterErrorDispatch**, and **doFilterNestedErrorDispatch**.
3. Identify when **DispatcherType.REQUEST**, **DispatcherType.ASYNC**, and **DispatcherType.ERROR** occur, including nested ERROR dispatches inside REQUEST.
4. Understand the two-gate condition: **Servlet container registration of dispatcher types** and **OncePerRequestFilter not skipping the dispatch**.
5. Use **FilterRegistrationBean** with proper URL patterns, dispatcher types, asyncSupported, and filter ordering.
6. Keep a stable request ID across multiple dispatches without misusing MDC/ThreadLocal or double-counting metrics.
7. Run a sample **Java 17, Spring Boot 3.5, Spring MVC, embedded Tomcat** app with synchronous, async Callable, and sendError requests.
8. Write real HTTP tests to verify request dispatches, responses, correlation IDs, and error handling boundaries.

The examples use **Spring Boot 3.5.16 / Spring Framework 6.2 / Jakarta Servlet / Java 17**. In Boot 3.x, the Servlet package is **jakarta.servlet**, not the legacy **javax.servlet** from some Boot 2.x projects. In Spring WebFlux on Reactor Netty, the corresponding filter is **WebFilter**, which has no Servlet DispatcherType as covered in this lesson.

## 2. How Do Request and Dispatch Differ?

A single client HTTP request can be processed by the Servlet container across multiple dispatches. A dispatch is one pass in which the container sends the request into the Servlet/filter chain under the active DispatcherType.

### 2.1. The DispatcherTypes

| DispatcherType | Context | Role |
|---|---|---|
| **REQUEST** | Client sends initial request | Standard entry point for a Servlet Filter |
| **ASYNC** | AsyncContext.dispatch after async work | Brings the async result back to the Servlet to complete |
| **ERROR** | Container routes to error page/error servlet | Handles errors within the Servlet container |
| **FORWARD** | RequestDispatcher.forward | Internally forwards to another resource |
| **INCLUDE** | RequestDispatcher.include | Includes content from another resource |

This lesson focuses on REQUEST/ASYNC/ERROR, though you should not assume Jakarta Servlet only defines three values. A Filter can be registered for FORWARD/INCLUDE if needed.

### 2.2. REQUEST → ASYNC Flow

~~~mermaid
flowchart TD
    A[HTTP client sends GET /api/async] --> B[REQUEST dispatch]
    B --> C[Servlet FilterChain]
    C --> D[DispatcherServlet]
    D --> E[Controller returns Callable]
    E --> F[request.startAsync]
    F --> G[REQUEST thread exits filter chain, response stays open]
    G --> H[Callable executes on executor thread]
    H --> I[Servlet container ASYNC redispatch]
    I --> J[FilterChain if ASYNC is mapped]
    J --> K[DispatcherServlet retrieves async result]
    K --> L[Write response and complete]
~~~

**There is one client request but two Servlet dispatches.** If the Filter participates in both REQUEST and ASYNC, **doFilterInternal can be called in each phase**. The thread running the Callable is not itself a Servlet dispatch; the filter does not automatically wrap Callable execution on the executor thread.

### 2.3. REQUEST → ERROR Flow

~~~mermaid
flowchart TD
    A[REQUEST dispatch] --> B[Controller or Servlet]
    B --> C{Where is the error handled?}
    C -->|@ExceptionHandler handles and returns JSON| D[Response completes immediately inside REQUEST]
    C -->|sendError or error escapes to container| E[Container has error mapping?]
    E -->|Yes| F[ERROR dispatch to error page, possibly /error]
    F --> G[FilterChain if ERROR is registered]
    G --> H[Error controller/page returns response]
    E -->|No| I[Container handles error by its own policy]
~~~

**An HTTP 404/500/503 status does not prove an ERROR dispatch occurred.** A controller returning a ResponseEntity with an error status or an `@ExceptionHandler` resolving an exception entirely within Spring MVC may not trigger a Servlet ERROR dispatch.

### 2.4. Why Threads Matter

REQUEST, ASYNC, and ERROR can run on different threads. With a Callable, the executor thread performing the work is not the original REQUEST thread, and the ASYNC redispatch may use yet another container thread. Therefore:

- **HttpServletRequest attributes** are suitable for preserving a request ID across a logical request, given compatible request wrappers/dispatches.
- **ThreadLocal/MDC** is thread-scoped: it must be re-established on each participating thread and cleaned up in a finally block.
- A **singleton Filter field** is unsuitable for storing per-request requestId, status, or startTime.
- Avoid Thread.sleep or uncontrolled blocking logic inside the filter chain because it ties up Servlet container threads.

## 3. Mechanics of OncePerRequestFilter

Import:

~~~java
import org.springframework.web.filter.OncePerRequestFilter;
~~~

OncePerRequestFilter extends **GenericFilterBean** and implements **doFilter**. Developers typically only override:

~~~java
@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain)
        throws ServletException, IOException {

    chain.doFilter(request, response);
}
~~~

This snippet is a method inside a class extending OncePerRequestFilter, not a standalone class. Using it in Boot 3.5 requires imports from jakarta.servlet and jakarta.servlet.http.

### 3.1. The Already-Filtered Marker

Internal mechanism (logical description, not verbatim source code):

~~~text
Servlet container calls OncePerRequestFilter.doFilter(...)
  ├─ If dispatch/request is skipped: call chain, do not call doFilterInternal
  ├─ If request already has FILTERED marker:
  │    ├─ If nested ERROR: call doFilterNestedErrorDispatch(...)
  │    └─ Otherwise: just call chain, preventing repeated doFilterInternal in dispatch
  └─ If marker is not present:
       ├─ Set request attribute <filter-name>.FILTERED
       ├─ Call doFilterInternal(...)
       └─ finally: remove request attribute .FILTERED
~~~

The **getAlreadyFilteredAttributeName()** method determines the marker name, defaulting to the filter name with the **.FILTERED** suffix. Once doFilterInternal finishes, the marker is **removed in finally**, even if an exception is thrown.

Important consequences:

- The filter only guards against **duplicate execution within an active dispatch**.
- After the REQUEST dispatch exits the chain, the marker is gone. A new ASYNC dispatch can invoke doFilterInternal again if not skipped.
- A new ERROR dispatch behaves similarly; specifically, a nested ERROR while the marker still exists has its own hook.
- The marker is **different from a correlation ID**. Do not use the marker to store long-lived request state.
- If business code must guarantee an operation runs only once for an entire request or transaction, implement explicit idempotency/transaction logic. The class name alone does not provide that guarantee.

### 3.2. Hooks and Default Values

| Hook | Default in Spring Framework 6.2 | Meaning |
|---|---|---|
| **shouldNotFilter(request)** | **false** | By default, does not skip requests |
| **shouldNotFilterAsyncDispatch()** | **true** | By default, skips ASYNC redispatches |
| **shouldNotFilterErrorDispatch()** | **true** | By default, skips ERROR dispatches |
| **isAsyncDispatch(request)** | Helper | Checks whether the current dispatch is in the ASYNC phase |
| **isAsyncStarted(request)** | Helper | Indicates async processing has started and another phase remains |
| **doFilterNestedErrorDispatch** | Forwards chain | Allows handling a nested ERROR when the marker already exists |

The **shouldNotFilter** naming is negative: to **filter ASYNC**, you must **return false**:

~~~java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return false;
}

@Override
protected boolean shouldNotFilterErrorDispatch() {
    return false;
}
~~~

This override serves examples that want to observe all phases. When only REQUEST is needed, leaving both hooks at their default true is often the sensible choice.

### 3.3. Both Gates Must Allow It

**Gate A: Servlet filter registration** must map the filter to the URL or servlet and the current dispatcher type. Example:

~~~java
registration.setDispatcherTypes(
        DispatcherType.REQUEST,
        DispatcherType.ASYNC,
        DispatcherType.ERROR);
~~~

**Gate B: OncePerRequestFilter** must not skip the dispatch and must not be prevented by the marker from calling doFilterInternal.

| Registration | Skip hook | Actual ASYNC occurs? | doFilterInternal during ASYNC |
|---|---|---|---|
| REQUEST only | false | Yes | **No**, container does not invoke Filter |
| REQUEST + ASYNC | true | Yes | **No**, OncePerRequestFilter skips it |
| REQUEST + ASYNC | false | Yes | **Yes**, when the dispatch pass is invoked |
| REQUEST + ASYNC + ERROR | both async/error false | Container triggers ERROR | **Can run on ERROR**, depending on error dispatch type |

Do not merely set **setAsyncSupported(true)** and assume the filter will be invoked on ASYNC. asyncSupported enables Servlet async support, whereas **setDispatcherTypes** specifies which dispatches the container maps to the filter.

Spring Boot 3.5 has logic to infer default dispatcher types when using FilterRegistrationBean with OncePerRequestFilter; however, results can depend on version and registration path. For this lesson, **always declare dispatcher types explicitly** so the configuration is unambiguous.

### 3.4. isAsyncDispatch vs. isAsyncStarted

- **isAsyncDispatch(request)**: identifies an async redispatch currently being processed.
- **isAsyncStarted(request)**: indicates the request has entered async mode and the current dispatch is not yet the final regular completion phase.

With a controller returning Callable, at the end of the REQUEST dispatch you typically see:

~~~text
dispatcherType=REQUEST
isAsyncDispatch=false
isAsyncStarted=true
~~~

When the container redispatches to write the async result, you typically see:

~~~text
dispatcherType=ASYNC
isAsyncDispatch=true
isAsyncStarted=false
~~~

These lines describe **typical** states, not fixed stdout. Async streaming or container internals can produce different states. When exact knowledge is required, log request.getDispatcherType and the helpers in your target runtime.

## 4. REQUEST Dispatch

REQUEST is the initial pass of an HTTP request. A default OncePerRequestFilter is well suited to:

- Generate a server-side correlation/request ID or validate an ID from a trusted upstream.
- Set request attributes for controllers and downstream layers.
- Set response headers before the body commits.
- Observe method, sanitized path, status, and exceptions.
- Perform HTTP-level cross-cutting concerns per contract.

Example inside doFilterInternal:

~~~java
String requestId = UUID.randomUUID().toString();
request.setAttribute("requestId", requestId);
response.setHeader("X-Request-Id", requestId);
chain.doFilter(request, response);
~~~

This is only an illustrative snippet. **Do not unconditionally generate a new UUID like this when the Filter also runs on ASYNC/ERROR**; the complete demo will only create an ID if the request attribute is not yet present.

### 4.1. Avoid Logging or Modifying the Response Too Late

A Filter can use finally for cleanup:

~~~java
long start = System.nanoTime();
try {
    chain.doFilter(request, response);
} finally {
    long dispatchDurationNs = System.nanoTime() - start;
}
~~~

However, for async REQUEST processing, code after chain.doFilter can run **before the HTTP response completes**. The measured figure is only the duration of the current dispatch. To measure total request latency, use **AsyncListener** or built-in observability instead of mislabeling the measurement as end-to-end duration.

### 4.2. shouldNotFilter by Path

You can override:

~~~java
@Override
protected boolean shouldNotFilter(HttpServletRequest request) {
    return request.getServletPath().startsWith("/public/");
}
~~~

This snippet illustrates skipping per request. However, during an ERROR dispatch, the servlet path may be **/error**, no longer the original request URI. If you need to handle ERROR, inspect **jakarta.servlet.error.request_uri** when present instead of relying solely on servletPath.

## 5. ASYNC Dispatch and Spring MVC

Spring MVC supports **Callable**, **DeferredResult**, **WebAsyncTask**, **ResponseBodyEmitter**, and **SseEmitter**. A controller method can return a Callable so Spring MVC executes the work on an executor without holding the Servlet request thread waiting.

Callable flow:

1. REQUEST passes through Filter, DispatcherServlet, and the controller.
2. Controller returns Callable; Spring MVC calls request.startAsync and uses AsyncTaskExecutor.
3. The REQUEST thread leaves the FilterChain while the response remains open.
4. Callable runs on an executor thread and completes or errors.
5. Spring MVC asks the Servlet container for an ASYNC redispatch.
6. Container runs filters mapped to ASYNC; DispatcherServlet writes the result.
7. The response finishes, or encounters a timeout/error/cancellation.

**Important:** Overriding shouldNotFilterAsyncDispatch() to return false lets the filter participate in the **redispatch**, rather than turning the filter into a wrapper around the Callable code on the executor thread. Propagating MDC/security/request context to the Callable thread requires executor propagation mechanisms and corresponding callbacks.

### 5.1. Consistent Configuration

In FilterRegistrationBean:

~~~java
registration.setAsyncSupported(true);
registration.setDispatcherTypes(
        DispatcherType.REQUEST,
        DispatcherType.ASYNC,
        DispatcherType.ERROR);
~~~

In the OncePerRequestFilter subclass:

~~~java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return false;
}
~~~

Other involved Filters/Servlets must also have compatible async support. When configuring web.xml or an external container manually, do not look only at a single Boot bean and ignore the actual container configuration.

### 5.2. Async Lifecycle and Metrics

| Phase | Thread | What Filter Can Observe | Final Response? |
|---|---|---|---|
| REQUEST before controller | Container thread | doFilterInternal REQUEST | Not yet |
| Callable running in background | Executor thread | Not automatically wrapped by filter | Not yet |
| REQUEST finally | Container thread | isAsyncStarted may be true | Not yet |
| ASYNC redispatch | Another container thread | doFilterInternal ASYNC if enabled | May complete |
| Async timeout/error | Various cases | AsyncListener/exception dispatch depending on flow | Depends |

If you need total HTTP request duration, use **AsyncListener.onComplete/onTimeout/onError** or **Micrometer Observation/Tracing** instrumentation. If an async cycle is restarted, understand **onStartAsync** to avoid duplicate listeners or double-counting metrics. In production, configure **AsyncTaskExecutor**, timeouts, and queues intentionally.

## 6. ERROR Dispatch

**ERROR dispatch** is a Servlet container dispatch to an error page, typically targeting **/error** in Spring Boot Servlet MVC. It is not triggered simply because the final status is an error.

| Action | Guaranteed ERROR dispatch? | Notes |
|---|---|---|
| Controller returns ResponseEntity.status(404) | No | May complete directly inside REQUEST |
| @ExceptionHandler returns ProblemDetail 500 | No | Exception already handled in MVC |
| Controller calls response.sendError(503) | Possibly | Container may dispatch to error page |
| Unhandled exception escapes to container | Possibly | Depends on resolver/error mapping |
| Reverse proxy blocks request before app | No | Servlet never sees request |
| Error occurs after response committed | Not guaranteed | Status/body cannot be arbitrarily changed |

For ERROR to pass through a Filter, you need **DispatcherType.ERROR** in the registration, **shouldNotFilterErrorDispatch() returning false**, and a URL pattern matching the error dispatch target. For example, a Servlet registration for **/api/*** may not match the **/error** route. Choose **"/*"** in the demo to test both.

### 6.1. Separate ERROR

In many containers, the REQUEST dispatch ends, the already-filtered marker is removed, and then the ERROR dispatch begins through a fresh chain. With the skip flag set to false and proper ERROR mapping, **doFilterInternal** runs during that ERROR pass.

### 6.2. Nested ERROR

Some containers can initiate an ERROR dispatch **nested inside an active REQUEST dispatch**, on the same thread, while the already-filtered marker is still present. In that case, OncePerRequestFilter provides a dedicated hook:

~~~java
@Override
protected void doFilterNestedErrorDispatch(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain)
        throws ServletException, IOException {

    // Can re-apply request/response wrappers if the container replaced them.
    chain.doFilter(request, response);
}
~~~

By default, this hook forwards to the FilterChain. It is useful when a Filter wrapped HttpServletRequest/HttpServletResponse, but the nested ERROR reverted to the original wrappers. **Do not equate the nested ERROR hook with doFilterInternal for a separate ERROR dispatch.**

During a nested ERROR, the REQUEST ThreadLocal may still be active because the outer request chain has not exited yet, so do not prematurely clear shared context before the outer REQUEST completes.

### 6.3. Paths and Error Attributes

During an ERROR dispatch, the Servlet container may provide:

~~~text
jakarta.servlet.error.request_uri
jakarta.servlet.error.status_code
jakarta.servlet.error.exception
jakarta.servlet.error.message
~~~

Not every attribute is populated for every error type. request.getRequestURI may return **/error**, whereas **jakarta.servlet.error.request_uri** indicates the original URI when set by the container. Do not log raw exceptions or request bodies containing credentials or sensitive data.

### 6.4. Avoiding Double-Counting

If you increment an HTTP client request counter on every doFilterInternal invocation, a request passing through REQUEST and then ASYNC or ERROR will be counted multiple times. Two distinct metrics should be clearly named:

- **Dispatch attempts**: counts each REQUEST/ASYNC/ERROR dispatch.
- **Logical HTTP requests**: counts once per client request.

To record a final metric once, use a dedicated business marker on the request and an appropriate request completion callback, not the **.FILTERED** marker, to measure total lifecycle.

## 7. When Should All Three Dispatch Types Be Enabled?

**Choose REQUEST only** if the Filter only performs startup work needed once, such as setting a request ID attribute on the request. Enabling ASYNC/ERROR does not automatically make an app safer; it can add duplicate logs, overhead, or corrupt responses.

**Choose ASYNC** if the Filter must restore context or wrapping during redispatches, observe processing after a Callable finishes, or keep a feature working across Servlet async phases.

**Choose ERROR** if you need tracing or request/response wrappers during error page dispatches. If a filter only applies to handler routes and does not need to run on /error, leave it off.

**Choose the nested ERROR hook** when a Filter maintains complex wrappers and the container performs nested error dispatches. Do not override the hook just to count all HTTP errors, because 4xx/5xx responses do not guarantee an error dispatch.

For authentication, authorization, CORS, CSRF, and security headers, prefer the properly configured **Spring Security Servlet FilterChain** for your version. A custom OncePerRequestFilter should have a clear scope; never treat it as a comprehensive security mechanism.

## 8. Decision and Diagnostics Table

| Issue | Common Cause | Resolution |
|---|---|---|
| ASYNC does not invoke doFilterInternal | Filter mapping lacks ASYNC or skip hook returns true | Set dispatcher types + override to return false |
| ERROR does not invoke doFilterInternal | No ERROR dispatch generated, /error URL mismatch, or skipped | Verify container, mapping, skip flag |
| doFilterInternal runs twice for one client request | REQUEST followed by ASYNC/ERROR | Check dispatcherType, do not assume it is a bug |
| AsyncController returns 200 but trace shows only REQUEST | Filter only runs on REQUEST | Check setDispatcherTypes and shouldNotFilterAsyncDispatch |
| Error response 500 but trace shows no ERROR | Exception handled inside REQUEST | Do not infer ERROR from status code |
| NESTED_ERROR appears instead of doFilterInternal ERROR | Marker still present during nested dispatch | Use doFilterNestedErrorDispatch |
| Request ID changes on ASYNC | Generated new ID on every doFilterInternal | Store in a stable request attribute |
| Metrics double-counted | Counted per dispatch instead of logical request | Separate per-dispatch and per-request metrics |
| Header missing | Set after response committed | Set early before chain or at appropriate lifecycle point |
| MDC lost in Callable | Different executor thread | TaskDecorator/context propagation |
| Request body logging makes @RequestBody empty | Filter consumed input stream | Avoid consuming or use a bounded wrapper |
| Filter unexpectedly runs twice | Auto-registration plus Security chain/another bean | Register only once |
| Spring WebFlux does not use REQUEST/ASYNC | Reactive Netty has no Servlet filter chain | Use WebFilter |


## 9. Runnable Java 17 / Spring Boot 3.5 Project

This example demonstrates a stable request ID across Servlet dispatches. The project uses **spring-boot-starter-web** and embedded Tomcat, not WebFlux Netty.

### 9.1. Project Structure

~~~text
dispatch-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/dispatchdemo/
    │   │   ├── DispatchDemoApplication.java
    │   │   ├── DispatchAudit.java
    │   │   ├── TraceDispatchFilter.java
    │   │   ├── FilterConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.yml
    └── test/java/com/example/dispatchdemo/
        └── DispatchIntegrationTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>dispatch-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
~~~

For production, use a currently maintained Spring Boot branch appropriate for your organization. Version 3.5.16 is pinned here so the example has concrete dependencies.

### 9.3. DispatchDemoApplication.java

~~~java
package com.example.dispatchdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DispatchDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DispatchDemoApplication.class, args);
    }
}
~~~

### 9.4. DispatchAudit.java

~~~java
package com.example.dispatchdemo;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import jakarta.servlet.DispatcherType;
import org.springframework.stereotype.Component;

@Component
public class DispatchAudit {

    private final Queue<Entry> entries = new ConcurrentLinkedQueue<>();

    public void add(
            String requestId,
            DispatcherType dispatcherType,
            String phase,
            boolean asyncStarted) {

        entries.add(new Entry(
                requestId,
                dispatcherType,
                phase,
                asyncStarted,
                Thread.currentThread().getName()));
    }

    public List<Entry> forRequest(String requestId) {
        return entries.stream()
                .filter(e -> e.requestId().equals(requestId))
                .toList();
    }

    public record Entry(
            String requestId,
            DispatcherType dispatcherType,
            String phase,
            boolean asyncStarted,
            String thread) {
    }
}
~~~

**Explanation:** ConcurrentLinkedQueue allows Servlet threads to record events concurrently. This is an **in-memory audit for learning and testing**, not a production solution: an unbounded queue can grow RAM usage, and a public trace endpoint can leak information. In production, use bounded logging/metrics with access control.

### 9.5. TraceDispatchFilter.java

~~~java
package com.example.dispatchdemo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class TraceDispatchFilter extends OncePerRequestFilter {

    public static final String REQUEST_ID =
            TraceDispatchFilter.class.getName() + ".requestId";

    private final DispatchAudit audit;

    public TraceDispatchFilter(DispatchAudit audit) {
        this.audit = audit;
    }

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

        String id = (String) request.getAttribute(REQUEST_ID);
        if (id == null) {
            id = UUID.randomUUID().toString();
            request.setAttribute(REQUEST_ID, id);
        }

        if (!response.isCommitted()) {
            response.setHeader("X-Request-Id", id);
        }

        DispatcherType type = request.getDispatcherType();
        audit.add(id, type, "ENTER", isAsyncStarted(request));

        try {
            chain.doFilter(request, response);
        } finally {
            audit.add(id, type, "EXIT", isAsyncStarted(request));
        }
    }

    @Override
    protected void doFilterNestedErrorDispatch(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String id = (String) request.getAttribute(REQUEST_ID);
        audit.add(id == null ? "unknown" : id,
                request.getDispatcherType(),
                "NESTED_ERROR", isAsyncStarted(request));
        chain.doFilter(request, response);
    }
}
~~~

**Detailed explanation:**

- OncePerRequestFilter uses two false overrides so it can handle ASYNC and ERROR.
- **REQUEST_ID** is stored in a **separate** request attribute and is not conflated with the base class's **.FILTERED** marker.
- When a new ASYNC/ERROR dispatch runs, if the request attribute is intact, the trace ID is reused.
- Before calling the chain, the header is added if the response has not yet committed.
- The queue records **ENTER** and **EXIT** along with DispatcherType so phases can be observed.
- doFilterNestedErrorDispatch records **NESTED_ERROR** if a container dispatches ERROR directly within REQUEST while the marker is still present. If request/response wrappers need to be re-applied, implement the appropriate logic for those wrappers.
- The class **is not annotated with @Component** to avoid double registration. FilterRegistrationBean in the next file is the sole registration.
- The filter demonstrates logging/tracing and does not replace Spring Security.

### 9.6. FilterConfig.java

~~~java
package com.example.dispatchdemo;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FilterConfig {

    @Bean
    public FilterRegistrationBean<TraceDispatchFilter> traceFilter(
            DispatchAudit audit) {

        FilterRegistrationBean<TraceDispatchFilter> bean =
                new FilterRegistrationBean<>(
                        new TraceDispatchFilter(audit));

        bean.addUrlPatterns("/*");
        bean.setDispatcherTypes(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC,
                DispatcherType.ERROR);
        bean.setAsyncSupported(true);
        bean.setOrder(10);
        return bean;
    }
}
~~~

**Why use /*?** Spring Boot Servlet MVC's ERROR dispatch typically goes to **/error**, so a registration mapped only to **/api/*** might skip the error page. FilterConfig maps **"/*"** so it can observe both /api and /error.

**Why setAsyncSupported(true)?** The Servlet container requires filters/servlets on an async path to support async; this does not make a request become async if the controller does not initiate async processing.

### 9.7. DemoController.java

~~~java
package com.example.dispatchdemo;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final DispatchAudit audit;

    public DemoController(DispatchAudit audit) {
        this.audit = audit;
    }

    @GetMapping("/api/sync")
    public Map<String, String> sync(HttpServletRequest request) {
        String id = (String) request.getAttribute(
                TraceDispatchFilter.REQUEST_ID);
        return Map.of("mode", "sync", "requestId", id);
    }

    @GetMapping("/api/async")
    public Callable<Map<String, String>> async(
            HttpServletRequest request) {

        String id = (String) request.getAttribute(
                TraceDispatchFilter.REQUEST_ID);

        return () -> Map.of("mode", "async", "requestId", id);
    }

    @GetMapping("/api/fail")
    public void fail(HttpServletResponse response)
            throws IOException {
        response.sendError(503, "Demo Servlet error");
    }

    @GetMapping("/api/trace/{id}")
    public List<DispatchAudit.Entry> trace(
            @PathVariable String id) {
        return audit.forRequest(id);
    }
}
~~~

The **async** controller returns a Callable; Spring MVC runs the logic on an executor. **Do not use HttpServletRequest directly inside the Callable thread**; instead read requestId while the handler runs and capture the immutable String.

The **/api/fail** endpoint calls sendError(503), letting the embedded container handle the error page. Do not assert that ERROR always occurs for every 503; inspect the actual audit. The **/api/trace/{id}** endpoint is solely for this lesson and **must not be exposed in production**.

### 9.8. application.yml

~~~yaml
server:
  port: 8080

spring:
  mvc:
    async:
      request-timeout: 10s
~~~

The request-timeout parameter applies to Spring MVC asynchronous request handling. Production also requires a bounded AsyncTaskExecutor and monitoring of timeouts and queues.

### 9.9. Running and Testing

From the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Synchronous request:

~~~bash
curl -i "http://localhost:8080/api/sync"
~~~

Expect HTTP 200, an **X-Request-Id** header, and JSON similar to:

~~~json
{"mode":"sync","requestId":"123e4567-e89b-12d3-a456-426614174000"}
~~~

The request ID is an illustrative UUID, not fixed stdout. The X-Request-Id header and the requestId field in JSON must **match**.

Async request:

~~~bash
curl -i "http://localhost:8080/api/async"
~~~

Expect HTTP 200, JSON mode=async, and the same ID in the header. Then substitute the actual ID into:

~~~bash
curl -i \
  "http://localhost:8080/api/trace/123e4567-e89b-12d3-a456-426614174000"
~~~

In embedded Tomcat with the configuration above, you typically see **REQUEST ENTER**, **REQUEST EXIT**, and **ASYNC ENTER**, **ASYNC EXIT** entries with the same request ID. Thread names and isAsyncStarted can vary depending on runtime and timing.

Trigger error:

~~~bash
curl -i "http://localhost:8080/api/fail"
~~~

Expect **503 Service Unavailable**. If the embedded container performs an ERROR dispatch to /error, the trace will show **DispatcherType.ERROR**; if it performs a nested ERROR, the hook may record **NESTED_ERROR**. The error body can vary depending on Spring Boot error attributes and Accept headers. Do not infer from status 503 that an ERROR entry must exist.


## 10. Integration Tests over Real Embedded Tomcat

The test suite uses **@SpringBootTest(webEnvironment = RANDOM_PORT)** with **JDK 17 HttpClient**, without relying on port 8080. This uses real HTTP sockets, observing DispatcherType more faithfully to the container than MockMvc alone.

Create **src/test/java/com/example/dispatchdemo/DispatchIntegrationTest.java**:

~~~java
package com.example.dispatchdemo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.servlet.DispatcherType;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class DispatchIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    DispatchAudit audit;

    @Autowired
    ObjectMapper mapper;

    private final HttpClient client = HttpClient.newHttpClient();

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + path))
                .GET()
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    @Test
    void syncRunsThroughRequestDispatch() throws Exception {
        HttpResponse<String> response = get("/api/sync");

        assertThat(response.statusCode()).isEqualTo(200);
        String id = response.headers()
                .firstValue("X-Request-Id").orElseThrow();
        JsonNode body = mapper.readTree(response.body());

        assertThat(body.get("mode").asText()).isEqualTo("sync");
        assertThat(body.get("requestId").asText()).isEqualTo(id);

        List<DispatchAudit.Entry> entries = audit.forRequest(id);
        assertThat(entries).anyMatch(e ->
                e.dispatcherType() == DispatcherType.REQUEST
                        && e.phase().equals("ENTER"));
        assertThat(entries).anyMatch(e ->
                e.dispatcherType() == DispatcherType.REQUEST
                        && e.phase().equals("EXIT"));
    }

    @Test
    void asyncRunsThroughRequestAndAsyncDispatch()
            throws Exception {
        HttpResponse<String> response = get("/api/async");

        assertThat(response.statusCode()).isEqualTo(200);
        String id = response.headers()
                .firstValue("X-Request-Id").orElseThrow();
        JsonNode body = mapper.readTree(response.body());

        assertThat(body.get("mode").asText()).isEqualTo("async");
        assertThat(body.get("requestId").asText()).isEqualTo(id);

        List<DispatchAudit.Entry> entries = audit.forRequest(id);
        assertThat(entries).anyMatch(e ->
                e.dispatcherType() == DispatcherType.REQUEST
                        && e.phase().equals("ENTER"));
        assertThat(entries).anyMatch(e ->
                e.dispatcherType() == DispatcherType.ASYNC
                        && e.phase().equals("ENTER"));
    }

    @Test
    void sendErrorReturns503() throws Exception {
        HttpResponse<String> response = get("/api/fail");
        assertThat(response.statusCode()).isEqualTo(503);

        // If asserting DispatcherType.ERROR:
        // verify the embedded Servlet container performed an
        // ERROR dispatch (distinct from a plain error HTTP status).
    }
}
~~~

Run:

~~~bash
mvn test
~~~

When tests pass, Maven exits with code 0. **com.fasterxml.jackson.databind.ObjectMapper** is available via spring-boot-starter-web. The tests do not hardcode UUIDs or thread names, since they vary per request and environment.

### 10.1. Adding ERROR Dispatch Verification

Once you have verified that embedded Tomcat actually dispatches to Boot's **/error**, you can add to the sendErrorReturns503 test:

~~~java
String id = response.headers()
        .firstValue("X-Request-Id").orElseThrow();

assertThat(audit.forRequest(id)).anyMatch(e ->
        e.dispatcherType() == DispatcherType.ERROR
                || e.phase().equals("NESTED_ERROR"));
~~~

This is a **snippet added to the test method**, not a standalone program. If it fails, check error page mapping, container behavior, and whether the response enters an ERROR dispatch or is handled within REQUEST.

### 10.2. Trying Different Skip Flags

Restore the default:

~~~java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return true;
}
~~~

When re-running the async test, the HTTP response can still be 200, yet **doFilterInternal ASYNC is not invoked**. This demonstrates that the Servlet async lifecycle continues to work; the filter simply skipped it.

If you change the registration to **DispatcherType.REQUEST** only, even if shouldNotFilterAsyncDispatch returns false, the Servlet container **will not invoke the filter on ASYNC**. Both configuration gates must align.

### 10.3. MockMvc vs. a Real HTTP Container

MockMvc can test Callable logic with:

~~~java
MvcResult start = mockMvc.perform(get("/api/async"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(start))
        .andExpect(status().isOk());
~~~

This is an **illustrative snippet inside a test class with MockMvc and static imports**. It does not fully reproduce FilterRegistrationBean mappings, embedded Servlet container ERROR pages, or all response commit conditions. For evaluating REQUEST/ASYNC/ERROR dispatches, prefer HTTP integration tests against an embedded server.

## 11. Production Considerations

### 11.1. MDC and ThreadLocal

If setting per-request MDC in a Filter, clean it up on each thread:

~~~java
String previous = MDC.get("requestId");
try {
    MDC.put("requestId", requestId);
    chain.doFilter(request, response);
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
~~~

This snippet assumes requestId and MDC imports are already present. **A Callable running on an executor thread does not automatically inherit MDC** from the REQUEST thread. When needed, use a task decorator/context propagation and clean up the thread pool properly.

### 11.2. Request Body and Response Wrappers

Reading ServletInputStream in a filter before the controller can cause **@RequestBody** to read an empty body. **ContentCachingRequestWrapper** caches data only as it is read and does not automatically make any input stream infinitely re-readable. Avoid logging raw bodies, tokens, passwords, Cookies, or file uploads.

If a filter uses request/response wrappers, test nested ERROR, ASYNC redispatches, and response commits; doFilterNestedErrorDispatch exists to help handle containers that revert to the original request/response during nested ERRORs.

### 11.3. Security Ordering and Duplicate Registration

Spring Security Servlet uses **DelegatingFilterProxy**, **FilterChainProxy**, and **SecurityFilterChain**. If a custom Filter is both an auto-registered Spring bean and added to SecurityFilterChain, it can execute twice under different registrations. Check registrations and consider **FilterRegistrationBean.setEnabled(false)** for filters belonging solely to the Security chain.

Do not use a custom OncePerRequestFilter as primary authorization without understanding dispatcher types, URL matching, the security chain, and CSRF. Use official Spring Security policies for the Servlet stack.

### 11.4. Timeouts, Async Executors, and Error Mapping

- Configure an executor for MVC async Callables and bound concurrency/queues.
- Set explicit timeouts and monitor exceptions/timeouts/cancellations.
- Do not measure whole HTTP duration solely from the REQUEST dispatch's finally block.
- In an ERROR dispatch, the original URI may be in the **jakarta.servlet.error.request_uri** request attribute.
- Do not assume a 404/500 creates an ERROR dispatch; observe the actual DispatcherType.
- Once a response has committed, do not attempt to alter status/body/headers too late in a filter.
- When a single per-request measurement is needed, use Micrometer Observation/Tracing or an appropriate AsyncListener.

## 12. QA Checklist

- [ ] Distinguished logical request from Servlet dispatch.
- [ ] Aware that shouldNotFilterAsyncDispatch and shouldNotFilterErrorDispatch both default to true.
- [ ] If ASYNC is required, mapped DispatcherType.ASYNC and overrode skip=false.
- [ ] If ERROR is required, mapped DispatcherType.ERROR, /error URL, and overrode skip=false.
- [ ] Filter has async support enabled when the application uses Servlet async.
- [ ] Not misusing the .FILTERED marker as a request-wide business marker.
- [ ] Correlation ID is stored once in a request attribute and reused across redispatches.
- [ ] Handled doFilterNestedErrorDispatch when wrappers must be re-applied.
- [ ] Logical client requests are not counted multiple times per dispatch.
- [ ] Not confusing an error HTTP status with a container ERROR dispatch.
- [ ] MDC, ThreadLocal, and executor propagation are managed according to lifecycle.
- [ ] Not setting headers/body after commit or reading the request body twice.
- [ ] No duplicate filter registration across container and Spring Security.
- [ ] Tested sync, Callable async, sendError, error handling, and appropriate timeouts.
- [ ] Production does not expose the audit endpoint or keep an unbounded trace queue.

## 13. Official Documentation

1. **Spring Framework 6.2 OncePerRequestFilter Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
2. **Spring Framework 6.2 MVC Filters**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
3. **Spring Framework 6.2 Asynchronous Requests**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
4. **Spring Boot 3.5 Embedded Web Servers, Filter registration**: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
5. **Spring Boot 3.5 FilterRegistrationBean API**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html
6. **Jakarta Servlet 6 DispatcherType API**: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/dispatchertype
7. **Spring Security Servlet Architecture**: https://docs.spring.io/spring-security/reference/servlet/architecture.html
8. **Spring Boot 3.5.16 Maven artifact**: https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-parent/3.5.16

## 14. Conclusion

**OncePerRequestFilter** does not promise to run strictly once for an entire HTTP request. It uses an **already filtered** request attribute to prevent doFilterInternal from repeating within a single dispatch, while REQUEST, ASYNC, and ERROR can be separate dispatches of the same logical request.

In Spring Framework 6.2, the base class **skips ASYNC and ERROR** by default. To participate in these dispatches, you need both the **corresponding Servlet dispatcher mapping** and skip flags overridden to **false**. For nested ERRORs when the marker still exists, handle them via **doFilterNestedErrorDispatch** instead of assuming doFilterInternal will run a second time.

When implementing, store a stable correlation ID in a request attribute, separate per-dispatch metrics from logical-request metrics, manage ThreadLocal/async lifecycles properly, and test committed responses along with your actual Servlet container's error mapping.