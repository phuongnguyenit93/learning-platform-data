# Error Handling and Resource Cleanup When Filter/Interceptor Chains Short-Circuit in Spring Boot

## 1. The Problem

An HTTP request in Spring Boot MVC typically flows through **Servlet FilterChain → DispatcherServlet → HandlerInterceptor → Controller → response handling**. Any link in that chain can halt the normal flow:

- A Filter **does not call** `chain.doFilter(...)` because it returned HTTP 401, 403, 429, etc.
- A Filter throws `IOException`, `ServletException`, or `RuntimeException`.
- `HandlerInterceptor.preHandle(...)` returns `false` or throws an exception.
- The controller or service fails; Spring MVC uses `HandlerExceptionResolver` or `@RestControllerAdvice` to build an error response.
- The client disconnects, the response has already committed, or the request enters an **ASYNC/ERROR dispatch**.

If errors are mishandled, the application can leak **MDC/ThreadLocals**, locks, permits, file handles, connections, or memory; write a response twice; mask the original exception; or prevent the security chain from executing as expected. No single `afterCompletion` or single `try/finally` solves every case on its own.

This lesson targets **Spring Boot 3.5.x, Spring MVC Servlet stack, Java 17+**, with a complete project using Boot **3.5.16** and integration tests against a real embedded HTTP server. It differs from Spring WebFlux `WebFilter`/Reactor because WebFlux does not use a Servlet `FilterChain` for its reactive request pipeline.

**Goal:** after this lesson, you will be able to identify *who owns each resource*, *which callback is guaranteed to run on each branch*, *which layer should produce HTTP errors*, and *how to prove cleanup runs even when the chain is interrupted*.

## 2. Understanding the Lifecycles: Filters vs. Interceptors Differ

~~~text
HTTP client
    |
    v
Servlet container
    |
    +-- Filter A: before
    |     |
    |     +-- Filter B: before
    |     |     |
    |     |     +-- DispatcherServlet
    |     |             |
    |     |             +-- Interceptor X: preHandle
    |     |             +-- Interceptor Y: preHandle
    |     |             +-- Controller / exception resolver
    |     |             +-- postHandle (if applicable)
    |     |             +-- afterCompletion (only preHandle=true interceptors)
    |     |
    |     +-- Filter B: finally
    |
    +-- Filter A: finally
    |
    v
HTTP response
~~~

A **Servlet Filter** implements `doFilter(request,response,chain)`. It has no `preHandle(): boolean`; a filter stops a request by **not calling** `chain.doFilter`. Once execution enters `try`, its `finally` block runs upon leaving that block, whether via early `return` or exception.

**Spring MVC HandlerInterceptor** has `preHandle`, `postHandle`, and `afterCompletion`:

- `preHandle(...)` returns `true`: the chain proceeds; the interceptor becomes eligible for `afterCompletion` in synchronous execution.
- `preHandle(...)` returns `false`: Spring skips the handler and subsequent interceptors. The interceptor that just returned `false` **does not** have its own `afterCompletion` invoked.
- `preHandle(...)` throws an exception **before returning `true`**: do not expect that interceptor's own `afterCompletion` to run.
- **Earlier interceptors that already returned `preHandle=true`** in the same chain can still receive `afterCompletion` when the chain stops or errors.
- `postHandle` runs only on applicable paths when the handler finishes successfully; never rely on it for mandatory cleanup.
- `afterCompletion(request,response,handler,ex)` may receive `ex == null` when a `HandlerExceptionResolver` handled the exception. Never infer from `ex == null` that the controller never failed.
- Async MVC has a different lifecycle: the initial dispatch can exit without calling `postHandle`/`afterCompletion`; see Section 10.

The `HandlerInterceptor.afterCompletion` Javadoc explicitly states it is called only if that interceptor's `preHandle` completed successfully and returned `true`. This is a critical invariant for resource management.

## 3. Scenario Matrix: Which Callback Cleans Up What?

| Scenario | Initial Dispatch Filter `finally` | Active Interceptor `afterCompletion` | Who Must Clean Up Resources? |
|---|---|---|---|
| Controller returns 200 synchronously | Yes, once inside `try` | Yes, if `preHandle=true` | Clean thread context in filter; clean interceptor resources in `afterCompletion` |
| Filter returns 429 early without calling chain | Yes | Never enters MVC interceptors | Filter cleans up everything it created |
| Filter throws exception | Yes | Usually never enters MVC if error occurs before `DispatcherServlet` | Filter cleans up; appropriate container/error handling builds HTTP error |
| `preHandle` returns `false` | Yes, when chain returns | **No** for the interceptor returning false | Interceptor releases resources before returning false; filter cleans its own |
| `preHandle` throws error | Yes | **No** for the interceptor throwing before returning true | Interceptor cleans up in `preHandle`'s `catch/finally` |
| A later interceptor returns `false` | Yes | Yes for earlier interceptors that returned true | Each resource owner cleans up its own |
| Controller throws error and `@ExceptionHandler` handles it | Yes | Yes if `preHandle=true` | MVC builds response; each owner cleans up per lifecycle |
| Controller throws unhandled error | Yes | Yes if `preHandle=true` in sync dispatch | Exception may reach container; never write again to committed response |
| Async request begins | Yes when initial dispatch exits | Not called on initial dispatch | Clean `ThreadLocal` per **thread/dispatch**; request-lifetime resources wait for async completion |
| ERROR redispatch | Can trigger a **separate filter invocation** if mapped | Depends on error handler mapping | Avoid double cleanup or double counting |

This matrix assumes execution entered the respective `try` blocks; if an exception occurs **before entering `try`**, that block's `finally` does not protect resources acquired beforehand. Scope acquisition and cleanup tightly.

## 4. Filter: Proper Cleanup via try/finally

### 4.1. Basic Safe Pattern

~~~java
@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain) throws ServletException, IOException {

    String previous = MDC.get("requestId");
    String requestId = UUID.randomUUID().toString();

    try {
        MDC.put("requestId", requestId);
        request.setAttribute("requestId", requestId);
        response.setHeader("X-Request-Id", requestId);

        if (isRateLimited(request)) {
            response.sendError(429, "Too many requests");
            return;
        }

        chain.doFilter(request, response);
    } finally {
        if (previous == null) {
            MDC.remove("requestId");
        } else {
            MDC.put("requestId", previous);
        }
    }
}
~~~

This is a **method excerpt** for a `OncePerRequestFilter` subclass, requiring Servlet/JDK/SLF4J imports and an `isRateLimited` implementation. The project in Section 8 contains complete Java files with equivalent logic.

Key points to remember:

1. `return` in the rate-limiting branch **still executes `finally`**.
2. If `chain.doFilter` throws `IOException`, `ServletException`, or an unchecked exception, `finally` still runs before the error propagates.
3. Restore the previous MDC value instead of blindly calling `clear()`, which would wipe keys set by other frameworks/libraries.
4. `requestId` is **per-request** data; never place it in a mutable field on a singleton filter.
5. `try/finally` protects the **thread-local MDC** for the current execution pass; it **does not** mean an async response has finished.
6. When auto-closing resources are needed, open them in `try-with-resources` matching their *lifetime*. Never close a Servlet response output stream owned by the container just because the filter returns.

### 4.2. Mistake: Cleanup Only After chain.doFilter

~~~java
MDC.put("requestId", id);
chain.doFilter(request, response);
MDC.remove("requestId"); // Skipped if downstream throws an exception!
~~~

If downstream fails, the Servlet container worker thread returns to the pool still holding the previous request's context. This causes corrupted log correlation or cross-request data leaks. Use `finally` to prevent it.

### 4.3. Mistake: Returning Before Entering try

~~~java
MDC.put("requestId", id);
if (blocked) {
    response.sendError(403);
    return; // Cleanup below is skipped.
}
try {
    chain.doFilter(request, response);
} finally {
    MDC.remove("requestId");
}
~~~

Put both short-circuit branches and throwing operations **inside the protected `try` block**.

### 4.4. Never Swallow Exceptions Just to Keep Responses Pretty

Do not do this:

~~~java
try {
    chain.doFilter(request, response);
} catch (Exception ex) {
    response.setStatus(200);
}
~~~

This hides server failures, returns a fake HTTP 200, drops failure signals, and can corrupt an already committed response. Let errors reach the proper handler, or intentionally translate them into a documented error status/schema **before the response commits**.

**Checked exceptions note:** `FilterChain.doFilter` declares `IOException` and `ServletException`. Standard servlet filters may propagate them per the method signature. Unhandled errors outside `DispatcherServlet` are not automatically handled by `@RestControllerAdvice`.

### 4.5. Committed Responses: Never Write a Second Time

Before generating a fallback error body, check `response.isCommitted()`. Once headers or body bytes have been flushed, `sendError`, `setStatus`, `resetBuffer`, or writing fresh JSON may have no effect, throw `IllegalStateException`, or produce a corrupted response.

When an exception happens after commit: clean up resources, log safely, and let the container manage the connection; never attempt to "fix the status" belatedly. Be especially careful with streaming/SSE, large downloads, and client disconnects.

## 5. Interceptor: False or Throw Means No Own afterCompletion

### 5.1. Common Resource-Holding Mistake

~~~java
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception {

    Permit permit = acquirePermit();
    request.setAttribute("permit", permit);

    if (!allowed(request)) {
        response.sendError(403);
        return false;
    }
    return true;
}

@Override
public void afterCompletion(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex) throws Exception {

    Permit permit = (Permit) request.getAttribute("permit");
    permit.close();
}
~~~

This is **illustrative Java pseudocode** with hypothetical `Permit`, `acquirePermit`, and `allowed`, not part of the demo project. The bug is on the `return false` branch: Spring does not call this interceptor's `afterCompletion`, so the permit leaks. If `sendError` throws an exception, the resource leaks too.

### 5.2. Writing Cleanup Both in preHandle and After Handler Completion

~~~java
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception {

    Permit permit = acquirePermit(); // Hypothetical type in pseudocode.
    boolean handedOff = false;

    try {
        if (!allowed(request)) {
            response.sendError(403);
            return false;
        }

        request.setAttribute("my.permit", permit);
        handedOff = true;
        return true;
    } finally {
        if (!handedOff) {
            permit.close(); // Closes on both false and throw before preHandle=true.
        }
    }
}

@Override
public void afterCompletion(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex) throws Exception {

    Permit permit = (Permit) request.getAttribute("my.permit");
    try {
        if (permit != null) {
            permit.close();
        }
    } finally {
        request.removeAttribute("my.permit");
    }
}
~~~

This is also **pseudocode** requiring an `AutoCloseable` `Permit` and full imports when adapted. When `preHandle` returns `true`, resource ownership transfers to `afterCompletion`. On `false` or a thrown exception, `preHandle`'s `finally` cleans up immediately.

Consider one design caveat: if `preHandle` returns `true` and the handler **initiates async processing**, `afterCompletion` may not run during the initial dispatch. If the permit cannot wait until redispatch or request completion—or must be released on timeout/disconnect—use dedicated async lifecycle callbacks (Section 10) rather than forcing synchronous logic.

### 5.3. Order With Multiple Interceptors

Suppose A and B are registered with A before B:

| `preHandle(A)` Result | `preHandle(B)` Result | Controller Runs? | `afterCompletion` |
|---|---|---|---|
| true | true | Yes | B then A, when sync request completes |
| true | false | No | A is called; B is **not** called |
| false | not run | No | No callback for A |
| true | throws exception | No | A can be called; B must clean up inside `preHandle` |
| throws exception | not run | No | A must clean up itself |

This table describes synchronous Servlet MVC. Never use `postHandle` for resource release, as it is skipped on many error and short-circuit paths.

### 5.4. Interceptors Are Not Complete Security Filters

When rejecting a request in an interceptor, you must choose the status (`401`/`403`/`429`...), any response body, and return `false`. However, Spring MVC interceptor path matching does not cover every Servlet path, forward, or error dispatch the way a Filter does. For authentication/authorization, prefer a properly configured **Spring Security FilterChain** rather than a manual MVC interceptor.

## 6. Exception Handling: Handle Errors at the Layer Where They Arise

### 6.1. Controller/Service Errors and HandlerExceptionResolver

If a controller throws an exception, `DispatcherServlet` can invoke a `HandlerExceptionResolver`, such as an `@ExceptionHandler` method in `@RestControllerAdvice`. The API can return `ResponseEntity`, `ProblemDetail`, or an appropriate status. Once the error is resolved, outer filters still unwind through `finally` along the normal return path.

Example:

~~~java
@RestControllerAdvice
class ErrorAdvice {
    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<Map<String, String>> handle(IllegalStateException ex) {
        return ResponseEntity.status(503)
                .body(Map.of("code", "SERVICE_UNAVAILABLE"));
    }
}
~~~

This is an illustrative class snippet; the complete project in Section 8 has full imports. Never expose `ex.getMessage()` in public response bodies if it could reveal secrets or internal details.

**Important:** `afterCompletion(..., ex)` can receive **null** when a Spring MVC exception resolver handled the error. Track error statuses/logs/metrics intentionally; never gate cleanup on `ex != null`.

### 6.2. Errors Raised by a Filter Before DispatcherServlet

If a Filter throws an exception **before** calling `chain.doFilter`, `@RestControllerAdvice` does not handle it by default because the exception occurs outside MVC's exception resolver. The Servlet container may handle it or dispatch to `/error` depending on config.

When a Filter intentionally blocks a request, call `response.sendError(429)` **if uncommitted**, then return. Never `throw new IllegalStateException` just to return an ordinary HTTP 429.

When a unified custom error schema is required across both MVC and filters, build a dedicated error writer checking `isCommitted`, content type, encoding, and dispatcher semantics, or use Boot's error controller mechanisms. Never try to invoke an MVC `@ExceptionHandler` directly from a Filter.

### 6.3. Errors Inside HandlerInterceptor

`preHandle` executes while `DispatcherServlet` runs the handler chain. Exceptions thrown there **can** be handled by Spring MVC exception resolvers, yet `afterCompletion` for an interceptor that has not yet returned `true` is still **not** guaranteed as a cleanup hook. "Building the HTTP error response" and "closing allocated resources" are **two independent responsibilities**.

### 6.4. Exceptions and Cleanup Order

When Filter B sits inside Filter A and both use `try/finally`, on error:

~~~text
A.before
  B.before
    Controller / DispatcherServlet throws
  B.finally
A.finally
container/error handling continues
~~~

In practice, if `DispatcherServlet` resolves the exception into a response, the chain may return normally; either way, B and A both clean up in `finally`. If a `finally` block itself throws, it can mask the original exception. Keep cleanup safe, idempotent where needed, and log close errors deliberately. With Java `try-with-resources`, close failures are attached as suppressed exceptions, preserving the primary exception.

## 7. Resources Have Different Lifetimes

| Resource | Appropriate Lifetime | How to Clean Up |
|---|---|---|
| `MDC`, ThreadLocal tenant/context | **One thread or one dispatch** | `finally` in Filter/Interceptor; restore prior value |
| Files/`InputStream` opened in sync method | Scope using the stream | `try-with-resources`; never close container-owned Servlet streams |
| Locks/semaphore permits | Until protected work finishes | `try/finally` or well-defined terminal callback |
| Manually opened JDBC Connection | One transaction/operation | `try-with-resources` if app directly owns it |
| Connection/`EntityManager` managed by Spring Transaction | Spring transaction scope | Let Spring manage it; never close manually in a Filter |
| Servlet response writer/output stream | Container-owned | Never close arbitrarily; avoid double writes |
| Async `DeferredResult`/SSE resources | **Until request completes, times out, errors, or disconnects** | `onCompletion`, `onError`, `AsyncListener`, and one-time cleanup |
| Metrics timers/correlation IDs | Depends on definition: per dispatch vs. whole request | Pick one terminal point; avoid double-counting REQUEST+ERROR |

**Ownership rule:** only close resources you created or explicitly received ownership of. Never close a shared `DataSource` or singleton bean per request. Never spin up and tear down an executor or connection pool per HTTP request.

### Sync Java try-with-resources Pattern

~~~java
try (InputStream input = Files.newInputStream(path)) {
    return process(input);
}
~~~

This is an illustrative method snippet where `path` is a validated `Path` and `process` is an existing method; Java closes `input` on block exit. For resources meant to live across async boundaries, placing `try-with-resources` around async setup **closes the resource too early**; move cleanup to the end-of-lifecycle callback.

## 8. Complete Demo: Filter finally + Interceptor preHandle + MVC Error Handling

This Maven application uses:

- `RequestScopeFilter extends OncePerRequestFilter` with `MDC`, request ID, `try/finally`, and an `activeScopes` counter to verify cleanup.
- `GuardInterceptor` returning `false` for `/api/interceptor-deny`, throwing before returning true for `/api/interceptor-throw`, and tracking `afterCompletion` for synchronous requests.
- `@RestControllerAdvice` handling MVC `IllegalStateException` as 503 with a safe error code.
- `FilterRegistrationBean` mapping the Filter to Servlet `/api/*` and `DispatcherType.REQUEST`; the interceptor mapped to Spring MVC `/api/**`.
- Tests via `@SpringBootTest(RANDOM_PORT)` and **JDK 17 HttpClient**, asserting statuses and active scope counts after every request.

These counters are strictly **teaching instrumentation**. In production, use bounded metrics/tracing and never accumulate unbounded request events in singleton lists.

### 8.1. Project Structure

~~~text
chain-cleanup-demo/
  pom.xml
  src/main/java/com/example/cleanup/
    ChainCleanupApplication.java
    RequestScopeFilter.java
    GuardInterceptor.java
    WebPipelineConfiguration.java
    DemoController.java
    ErrorAdvice.java
  src/test/java/com/example/cleanup/
    ChainCleanupIntegrationTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>chain-cleanup-demo</artifactId>
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

### 8.3. ChainCleanupApplication.java

~~~java
package com.example.cleanup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChainCleanupApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChainCleanupApplication.class, args);
    }
}
~~~

### 8.4. RequestScopeFilter.java

~~~java
package com.example.cleanup;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public final class RequestScopeFilter extends OncePerRequestFilter {
    private final AtomicInteger activeScopes = new AtomicInteger();

    public int activeScopeCount() {
        return activeScopes.get();
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String id = UUID.randomUUID().toString();
        String previousMdcValue = MDC.get("demo.requestId");

        activeScopes.incrementAndGet();
        try {
            MDC.put("demo.requestId", id);
            request.setAttribute("demo.requestId", id);
            response.setHeader("X-Request-Id", id);

            String path = request.getServletPath();

            if ("/api/filter-deny".equals(path)) {
                response.sendError(429, "Rate limited");
                return;
            }

            if ("/api/filter-exception".equals(path)) {
                throw new IllegalStateException("Filter failure");
            }

            chain.doFilter(request, response);
        } finally {
            try {
                if (previousMdcValue == null) {
                    MDC.remove("demo.requestId");
                } else {
                    MDC.put("demo.requestId", previousMdcValue);
                }
            } finally {
                activeScopes.decrementAndGet();
            }
        }
    }
}
~~~

How the Filter handles each branch:

1. `activeScopes` increments **right before `try`**; every statement that can return or throw by business logic sits **inside** `try`, and `finally` decrements the counter.
2. `/api/filter-deny` sends HTTP **429** and skips `chain`, yet `finally` still cleans up MDC and the counter.
3. `/api/filter-exception` throws `IllegalStateException` **before `DispatcherServlet`**, so MVC advice is not the default handler for it.
4. Other paths call downstream; whether handled or unhandled, they still unwind through the filter's `finally`.
5. `MDC` is restored rather than clearing the entire MDC map, avoiding wiping keys owned by logging/security/observability frameworks.
6. With async, this counter measures **active filter dispatches**, not requests waiting for completion; this demo uses synchronous requests only.

Never use `activeScopes` as a production rate limiter. Real rate limiting requires per-subject counters/permits, multi-instance coordination, timeouts, fairness, and request-lifecycle release logic.

### 8.5. GuardInterceptor.java

~~~java
package com.example.cleanup;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public final class GuardInterceptor implements HandlerInterceptor {
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger completed = new AtomicInteger();

    public int activeCount() {
        return active.get();
    }

    public int completedCount() {
        return completed.get();
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws Exception {

        String path = request.getServletPath();

        if ("/api/interceptor-deny".equals(path)) {
            response.sendError(403, "Denied");
            return false; // This interceptor itself gets no afterCompletion.
        }

        if ("/api/interceptor-throw".equals(path)) {
            throw new IllegalStateException("preHandle failed");
        }

        active.incrementAndGet();
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {

        try {
            completed.incrementAndGet();
        } finally {
            active.decrementAndGet();
        }
    }
}
~~~

Because `GuardInterceptor` increments `active` **only after passing every deny/throw branch**, it does not have to release a resource on `preHandle=false`. In applications holding real permits/locks, follow the `preHandle` `try/finally` cleanup pattern from Section 5 rather than treating this simple counter as a template for complex resource ownership.

`afterCompletion` may receive `ex == null` after Spring translates an exception into a response; the code does not rely on that parameter to perform cleanup.

### 8.6. WebPipelineConfiguration.java

~~~java
package com.example.cleanup;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebPipelineConfiguration implements WebMvcConfigurer {
    private final GuardInterceptor guard;

    public WebPipelineConfiguration(GuardInterceptor guard) {
        this.guard = guard;
    }

    @Bean
    FilterRegistrationBean<RequestScopeFilter> requestScopeRegistration() {
        FilterRegistrationBean<RequestScopeFilter> registration =
                new FilterRegistrationBean<>(new RequestScopeFilter());

        registration.setName("requestScopeFilter");
        registration.addUrlPatterns("/api/*");
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        registration.setOrder(20);
        return registration;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(guard).addPathPatterns("/api/**");
    }
}
~~~

**Two separate path-matching systems:**

- `addUrlPatterns("/api/*")` is a Servlet prefix pattern mapping the Filter on `/api/...` URLs.
- `addPathPatterns("/api/**")` is a Spring MVC interceptor path pattern.
- `DispatcherType.REQUEST` restricts the Filter to initial request dispatches in the demo; ERROR dispatches to `/error` will not double-increment `activeScopes`.
- The Filter is constructed directly inside `FilterRegistrationBean` and **not** annotated with `@Component`, avoiding an extra auto-registered filter bean mapped to `/*`.

### 8.7. DemoController.java

~~~java
package com.example.cleanup;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/api/ok")
    public String ok() {
        return "ok";
    }

    @GetMapping("/api/handled-failure")
    public String failed() {
        throw new IllegalStateException("Simulated service failure");
    }

    @GetMapping("/api/interceptor-deny")
    public String denied() {
        return "unreachable";
    }

    @GetMapping("/api/interceptor-throw")
    public String thrownByInterceptor() {
        return "unreachable";
    }

    @GetMapping("/public/ping")
    public String publicPing() {
        return "public";
    }
}
~~~

`/api/filter-deny` and `/api/filter-exception` **need no controller** because the Filter handles/throws before `DispatcherServlet`. For MVC `/api/interceptor-deny` and `/api/interceptor-throw`, controller mappings exist so Spring selects a handler and calls the interceptor's `preHandle`.

### 8.8. ErrorAdvice.java

~~~java
package com.example.cleanup;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ErrorAdvice {
    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<Map<String, String>> serviceFailure(
            IllegalStateException exception) {

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("code", "SERVICE_UNAVAILABLE"));
    }
}
~~~

In the demo, exceptions from controllers and interceptors inside `DispatcherServlet` are translated by Spring MVC into **503**. Exceptions thrown directly by a Filter outside MVC go to the Servlet container and typically become **500**, bypassing this handler.

The project includes no Spring Security; status 403 in the interceptor merely illustrates short-circuiting, not a production authentication/authorization policy.

### 8.9. Running with Maven and Testing with curl

Requires JDK 17+ and Maven. In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Once the server listens on port 8080, run:

~~~bash
curl -i http://localhost:8080/api/ok
curl -i http://localhost:8080/api/interceptor-deny
curl -i http://localhost:8080/api/filter-deny
curl -i http://localhost:8080/api/handled-failure
curl -i http://localhost:8080/api/filter-exception
curl -i http://localhost:8080/public/ping
~~~

Expected logical results:

| URL | HTTP | Meaning |
|---|---|---|
| `/api/ok` | 200 | Filter `finally` + interceptor `afterCompletion` |
| `/api/interceptor-deny` | 403 | `preHandle=false`, controller never runs |
| `/api/filter-deny` | 429 | Filter returns early yet still runs `finally` |
| `/api/handled-failure` | 503 | Controller fails, advice handles it |
| `/api/interceptor-throw` | 503 | `preHandle` throws before true; advice handles it, no interceptor `afterCompletion` |
| `/api/filter-exception` | 500 | Exception before `DispatcherServlet`; does not go through MVC advice by default |
| `/public/ping` | 200 | Outside both filter and interceptor scopes |

403/429/500 error bodies can vary depending on the Servlet container and Spring Boot error config, so do not treat default error JSON/HTML as a fixed contract. Only the 503 generated by `ErrorAdvice` is expected to contain `"code":"SERVICE_UNAVAILABLE"`. `X-Request-Id` appears on requests inside the filter scope if the response/dispatch preserves headers; on some container error dispatches, final headers can change, so cleanup tests should not rely solely on headers during errors.

## 9. HTTP Integration Tests Proving Cleanup on Interruption

Do not rely solely on `MockMvc` to verify `Servlet` registration behavior: test mocks can differ from embedded container mappings and dispatcher lifecycles. The test suite below sends real HTTP requests over TCP, asserting **status**, active counters, and callbacks.

File `src/test/java/com/example/cleanup/ChainCleanupIntegrationTest.java`:

~~~java
package com.example.cleanup;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.servlet.FilterRegistrationBean;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ChainCleanupIntegrationTest {
    @LocalServerPort
    int port;

    @Autowired
    FilterRegistrationBean<RequestScopeFilter> registration;

    @Autowired
    GuardInterceptor guard;

    private final HttpClient client = HttpClient.newHttpClient();

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();

        return client.send(request,
                HttpResponse.BodyHandlers.ofString());
    }

    private void assertNoActiveScopes() {
        assertEquals(0, registration.getFilter().activeScopeCount());
        assertEquals(0, guard.activeCount());
    }

    @Test
    void synchronousSuccessCleansFilterAndInterceptor() throws Exception {
        int before = guard.completedCount();
        HttpResponse<String> result = get("/api/ok");

        assertEquals(200, result.statusCode());
        assertEquals("ok", result.body());
        assertTrue(result.headers().firstValue("X-Request-Id").isPresent());
        assertEquals(before + 1, guard.completedCount());
        assertNoActiveScopes();
    }

    @Test
    void interceptorFalseDoesNotCallOwnAfterCompletion() throws Exception {
        int before = guard.completedCount();
        HttpResponse<String> result = get("/api/interceptor-deny");

        assertEquals(403, result.statusCode());
        assertEquals(before, guard.completedCount());
        assertNoActiveScopes();
    }

    @Test
    void filterShortCircuitStillRunsFinally() throws Exception {
        int before = guard.completedCount();
        HttpResponse<String> result = get("/api/filter-deny");

        assertEquals(429, result.statusCode());
        assertEquals(before, guard.completedCount());
        assertNoActiveScopes();
    }

    @Test
    void mvcHandledExceptionStillCleansBothLayers() throws Exception {
        int before = guard.completedCount();
        HttpResponse<String> result = get("/api/handled-failure");

        assertEquals(503, result.statusCode());
        assertTrue(result.body().contains("SERVICE_UNAVAILABLE"));
        assertEquals(before + 1, guard.completedCount());
        assertNoActiveScopes();
    }

    @Test
    void preHandleThrowDoesNotGetItsOwnAfterCompletion() throws Exception {
        int before = guard.completedCount();
        HttpResponse<String> result = get("/api/interceptor-throw");

        assertEquals(503, result.statusCode());
        assertEquals(before, guard.completedCount());
        assertNoActiveScopes();
    }

    @Test
    void filterExceptionStillRunsFinally() throws Exception {
        int before = guard.completedCount();
        HttpResponse<String> result = get("/api/filter-exception");

        assertEquals(500, result.statusCode());
        assertEquals(before, guard.completedCount());
        assertNoActiveScopes();
    }

    @Test
    void outsideApiScopeIsUnaffected() throws Exception {
        HttpResponse<String> result = get("/public/ping");

        assertEquals(200, result.statusCode());
        assertEquals("public", result.body());
        assertFalse(result.headers().firstValue("X-Request-Id").isPresent());
        assertNoActiveScopes();
    }
}
~~~

**Java 17 compatibility:** `java.net.http.HttpClient` in JDK 17 does not implement `AutoCloseable`, so the example uses standard `HttpClient.newHttpClient()` **without** wrapping it in try-with-resources. Tests run sequentially by default; if configured for parallel JUnit execution, avoid asserting a global active counter equals 0 while another test request is in flight—isolate state per request instead.

Run:

~~~bash
mvn test
~~~

This test suite was **not** pre-executed inside this document; outputs describe expected Java and Spring MVC/Servlet behavior. In your project CI, run it directly to verify startup, dependency versions, and container behavior. Even if an `ERROR` dispatch hits another URL, the tests assert only statuses and resource counters without pinning default error JSON/HTML payloads.

## 10. Async MVC: Initial Dispatch finally Does Not Mean Request Completion

Spring MVC `Callable`, `DeferredResult`, `WebAsyncTask`, `ResponseBodyEmitter`, `SseEmitter`, and reactive return types can initiate Servlet async processing:

~~~text
REQUEST dispatch:
  Filter.before
    Interceptor.preHandle
      Controller returns DeferredResult
      request.startAsync()
    AsyncHandlerInterceptor.afterConcurrentHandlingStarted
  Filter.finally              <-- initial thread exits; response remains open

Worker/event thread:
  setResult(...) or setErrorResult(...)

ASYNC dispatch:
  (Filters mapped to ASYNC with matching policy)
    DispatcherServlet finishes rendering response
    Interceptor callbacks per async lifecycle
  completion callback          <-- request actually completes
~~~

On the initial dispatch, `postHandle` and `afterCompletion` **are not necessarily invoked**; Spring Framework provides `AsyncHandlerInterceptor.afterConcurrentHandlingStarted` to clean up thread-bound context on the initial thread when async begins. This callback is distinct from `afterCompletion` on the final dispatch.

### 10.1. ThreadLocal/MDC: Clean Up Per Thread

If a filter populates MDC on a container thread, `finally` should clean MDC for **that thread** as soon as the filter dispatch ends, even though the async response stays open. That thread may be reused immediately for another request. Never leave MDC in the initial thread's `ThreadLocal` waiting for `DeferredResult.onCompletion` on another thread; cleaning up on another thread cannot clear the initial thread's `ThreadLocal`.

When MDC is needed on async workers or async redispatches, **propagate context deliberately** and clean up on each thread. With `OncePerRequestFilter`, configure `shouldNotFilterAsyncDispatch()`, `shouldNotFilterErrorDispatch()`, and Servlet `DispatcherType.ASYNC`/`ERROR` registration. Setting `asyncSupported=true` alone does not make the Filter run on `ASYNC` dispatches.

### 10.2. Request-Lifetime Resources: Clean Up on onCompletion

Illustrative pseudocode for a resource dedicated to an async operation:

~~~java
DeferredResult<String> result = new DeferredResult<>(5000L);
AutoCloseable resource = acquireResource(); // Illustrative; needs real method.
AtomicBoolean closed = new AtomicBoolean();

Runnable cleanup = () -> {
    if (closed.compareAndSet(false, true)) {
        try {
            resource.close();
        } catch (Exception ex) {
            // Log safely; never write to a committed HTTP response.
        }
    }
};

result.onCompletion(cleanup);
result.onTimeout(() -> result.setErrorResult(
        new IllegalStateException("Timed out")));
result.onError(error -> {
    // Record/cancel background work; never expose secrets.
});
return result;
~~~

This is an **illustrative snippet**, not a standalone method; it requires importing `DeferredResult`, `AtomicBoolean`, and defining `acquireResource`. `onCompletion` is a terminal callback triggered by normal completion, timeouts, or network errors. `AtomicBoolean` keeps cleanup idempotent alongside any other cleanup paths. If async setup fails **before registering callbacks**, clean up immediately on that setup failure branch.

When using raw Servlet APIs, `AsyncListener.onComplete/onError/onTimeout/onStartAsync` can be used, provided listener registration and lifecycle are exact. In Spring MVC, prefer `DeferredResult` callbacks or `CallableProcessingInterceptor`/`DeferredResultProcessingInterceptor` over directly manipulating `AsyncContext`.

### 10.3. Client Disconnects and Streaming

With `ResponseBodyEmitter` or `SseEmitter`, an IO error when the client closes the connection does not mean code can write an error JSON payload. Spring MVC/the container signals async errors and completes the request. Avoid calling `emitter.complete()` or writing further data after a write failure once the framework is handling it, and release business resources via appropriate callbacks.

An already-committed response cannot be switched from a streaming HTTP 200 to a clean 500 JSON response merely by catching an exception. Monitor disconnects, cancel background work, and close resources idempotently.

## 11. Distinguishing Cleanup Categories and Error Policies

### 11.1. Thread-Bound Cleanup

Examples include `MDC`, custom `ThreadLocal`s, tenant context, and manually initialized tracing contexts. If set inside a filter, **clean up in `finally` on the same thread**. Never clear `SecurityContext`, `RequestContextHolder`, or framework-managed `ThreadLocal`s you do not own.

### 11.2. Per-Request Resource Cleanup

Connections, semaphore permits, or request-scoped locks must close **exactly when the work actually finishes**. For sync methods, `try-with-resources` fits well. For async, use terminal callbacks. When handing off a resource downstream, explicitly define where ownership transfers.

### 11.3. Error Responses

- **Intentional Filter rejection:** specific status such as 429/403/401 while uncommitted; skip calling chain.
- **Intentional Interceptor rejection:** set status/`sendError`, return `false`, and clean up resources before returning.
- **Controller/service failure:** `@ExceptionHandler`, `ResponseEntityExceptionHandler`, `ProblemDetail`, and contract-compliant statuses.
- **Unhandled Filter exception:** let container/Servlet error pipeline handle it or use a dedicated error writer; `@RestControllerAdvice` does not cover everything.
- **Response already committed:** prioritize cleanup and logging; never attempt to overwrite body/status.
- **Client disconnect:** treat as a cancellation/transport error signal, not automatically as a business bug or public HTTP 500.

### 11.4. Logging and Observability

Record exception class, status, request/correlation ID, duration, and failure stage. Never dump `Authorization`, cookies, raw bodies, query strings with tokens, or exception causes containing PII. If a request goes through both `REQUEST` and `ERROR`/`ASYNC` dispatches, decide whether metrics count **logical HTTP requests** or individual dispatches to prevent double counting.

## 12. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Previous user's MDC appears on next request | Not cleaned in `finally`, or cleanup placed only after chain | Restore/remove in `finally` on the same thread |
| Filter blocks request yet active counter stays >0 | `return` placed outside `try` | Move short-circuit branches inside `try/finally` |
| Interceptor permit leaks on returning `false` | Released only in `afterCompletion` | Release immediately on the `preHandle` false path |
| Interceptor throws and skips cleanup | `preHandle` never returned true | Use `catch/finally` inside `preHandle` before throwing |
| Controller returns 503 yet `afterCompletion` `ex` is null | Exception already handled by MVC resolver | Never use `ex != null` as sole condition |
| 500 from Filter bypasses `RestControllerAdvice` | Error occurred before `DispatcherServlet` | Handle in filter/container/error pipeline |
| Error occurs while response partially streamed | Response already committed | Never call `sendError` or write JSON a second time |
| Using `postHandle` to release resources | `postHandle` skipped on errors and short-circuits | Use `finally`/`afterCompletion` per ownership |
| Async response times out while permit stays held | Cleaned only on initial dispatch or missing terminal callback | Use `DeferredResult.onCompletion`/`AsyncListener` + idempotent release |
| MDC lingers on async worker | Missing thread context propagation/cleanup | Set/restore per worker/dispatch |
| Async metrics double-counted | Counted both `REQUEST` and `ASYNC`/`ERROR` as 2 requests | Choose one terminal point per logical request |
| Filter runs twice | Auto-registered Filter bean + Security chain | Remove redundant registration or disable container registration |
| Catch `Exception` and return 200 | Swallowing errors | Preserve proper status and propagate unexpected failures |
| Client disconnect causes second body-write error | Caught `IOException` and tried writing again | Log safely and clean up without double-writing |
| Manually closing Spring-managed JDBC/`EntityManager` | Wrong ownership | Let the transaction manager handle it |
| Cleanup callback throws and masks root error | Unprotected close | Guard close, log secondary error, use `try-with-resources` where fitting |
| Tests check only 200 and skip failure paths | Leaks hide on rare branches | Test 403/429/500/503, `preHandle` false/throw, async timeouts |

## 13. Production Implementation Checklist

1. **Classify the layer:** did the error originate before or after `DispatcherServlet`? Filter, Interceptor, Controller, container, or async callback?
2. **Define resource ownership:** who creates, holds, transfers ownership, and closes each resource?
3. **Scope cleanup properly:** `ThreadLocal` in dispatch `finally`; request-scoped permits in sync `afterCompletion` or async terminal callbacks; self-opened streams/connections via `try-with-resources`.
4. **Never rely on `afterCompletion` when `preHandle=false/throw`.** Clean up inside `preHandle`.
5. **Never rely on `postHandle` for exception cleanup.**
6. **Preserve the root exception:** never swallow errors, return fake 200s, or let cleanup errors mask the root cause.
7. **Check `response.isCommitted()` before writing error responses** and avoid double writes.
8. **Distinguish intentional rejections from programming failures**, returning semantically accurate statuses.
9. **Control dispatcher types** and `OncePerRequestFilter` async/error policies, preventing double registration.
10. **Keep sensitive data out of logs/correlation/headers**; keep `requestId` safe.
11. **Test on a real embedded server** for `FilterRegistrationBean` URLs/order/short-circuiting, complemented by MVC MockMvc tests where appropriate.
12. **Write async lifecycle tests** including timeouts and disconnects if using `DeferredResult`/SSE/streaming.
13. **Watch HTTP connection pools and threads:** broken cleanup exhausts pools and hangs requests; monitor metrics and alerts.
14. **Audit Spring Boot/Framework version:** Servlet vs. WebFlux, API packages, starters, and version-specific error/async behavior.
15. **Verify error dispatches in real deployment topologies**, especially behind reverse proxies or running as a WAR outside an embedded container.

**Conclusion:** an HTTP chain can terminate at many layers. For **Filters**, place per-dispatch cleanup in `try/finally` covering every early return. For **HandlerInterceptors**, `afterCompletion` is reliable only when that interceptor's `preHandle` returned `true` in synchronous flows; any resource acquired before returning `false` or throwing must be released right inside `preHandle`. For **async**, separate thread-context cleanup from request-lifetime completion. Translate errors into responses at the proper layer, and never swallow exceptions or write again to an already committed response.

## Official Documentation

- Spring Framework 6.2 — HandlerInterceptor lifecycle / afterCompletion condition: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/HandlerInterceptor.html
- Spring Framework 6.2 — Handler Interception: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html
- Spring Framework 6.2 — Asynchronous Requests, Callable/DeferredResult/AsyncHandlerInterceptor: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
- Spring Framework 6.2 — OncePerRequestFilter Javadoc, async/error dispatch: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Framework — MVC @ExceptionHandler semantics: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — MVC Exceptions / HandlerExceptionResolver: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Framework — RFC 9457 Error Responses: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Boot 3.5 — Servlet Web Applications, FilterRegistrationBean: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Embedded Servlet Container/dispatcherTypes: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5 API — FilterRegistrationBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html