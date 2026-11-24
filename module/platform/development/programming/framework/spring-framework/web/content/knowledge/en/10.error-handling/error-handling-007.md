# Distinguishing Controller Exceptions from Filter or Servlet Container Errors

## 1. The Problem: The Same HTTP 500 Can Pass Through Three Different Mechanisms

In a Spring MVC application running on the Servlet stack, a request does not jump straight into `@RestController`. The Servlet container (Tomcat, Jetty, or Undertow depending on setup), a chain of `Filter`s, `DispatcherServlet`, `HandlerMapping`, `HandlerAdapter`, and controllers each own different responsibilities. When an error occurs, **where the error originates and the request's path** determine which component gets a chance to handle it.

Lesson objectives:

- Trace the flow `client → Servlet container → FilterChain → DispatcherServlet → controller` and the return response flow.
- Distinguish exceptions thrown **inside MVC dispatch**, exceptions thrown **before/after `chain.doFilter` in a Filter**, and errors detected directly by the **Servlet container**.
- Understand the scope of `@ExceptionHandler`, `@RestControllerAdvice`, `HandlerExceptionResolver`, `ResponseEntityExceptionHandler`, `/error`, and `ErrorController`.
- Distinguish `response.setStatus`, `response.sendError`, throwing exceptions, `forward`, and `ERROR dispatch`; do not equate every 4xx/5xx status with a Java exception.
- Explain Spring Security exceptions, Filter ordering, `DispatcherType`, committed-response failures, and async error handling.
- Build a Java 17+, Spring Boot 3.x / Spring Framework 6.x example, test with MockMvc and real HTTP, and understand the limits of each test type.

**Scope:** Spring MVC on the Jakarta Servlet stack. Spring WebFlux uses `WebFilter`/`WebExceptionHandler` and a different mechanism; this content does not apply verbatim to WebFlux.

## 2. Request Path Diagram and Three "Boundaries"

```text
Client
  |
  v
HTTP connector / Servlet container
  |   - parse request line, headers
  |   - request limits, select Servlet/filter mapping
  v
Servlet Filter A  ----> may block request / write response / throw
  |
  v
Servlet Filter B  ----> may block request / write response / throw
  |
  v
Spring Security FilterChainProxy (if enabled)
  |   - authentication, authorization, CSRF, ...
  v
DispatcherServlet
  |   HandlerMapping -> HandlerAdapter -> Controller
  |                 \-> HandlerInterceptor
  |   HandlerExceptionResolver chain when MVC dispatch fails
  v
Controller -> Service -> Repository
  |
  v
HttpMessageConverter / view rendering
  |
  +---- Response flows back through filters to container/client

If exception/status is unhandled at the current layer:
  -> Servlet container error handling / ERROR dispatch
  -> Spring Boot /error endpoint (if configured and matched)
  -> HTML/JSON/error body or container fallback depending on application
```

Simplified diagram: filters outside security and filters inside `SecurityFilterChain` do not necessarily appear in one fixed order as drawn; registration order and matching decide. `HandlerInterceptor` sits **inside** the `DispatcherServlet` lifecycle, whereas a Servlet `Filter` sits **outside** normal MVC processing.

### Three Cases to Recognize

1. **MVC exception:** `@GetMapping` calls a service which throws `OrderBlockedException`. It arises while `DispatcherServlet` is dispatching the handler; Spring MVC can select `@ExceptionHandler`/`@RestControllerAdvice`.
2. **Filter exception:** a custom Servlet Filter throws `ServletException` before calling `chain.doFilter`. MVC has not received the request yet, so `@RestControllerAdvice` **does not automatically catch the original exception**.
3. **Container-level error:** Tomcat rejects an invalid request, size limit violation, timeout/connection error, or failed Servlet dispatch; some issues occur **before a Servlet request/filter even runs**. There is no guarantee they pass through controllers or Spring MVC advice.

**Diagnostic rule:** an HTTP status only tells you the protocol result; it does not prove a Java exception occurred, nor identify which layer generated the response. For example, 403 could come from Spring Security, a filter calling `sendError`, a controller explicitly returning 403, or an upstream gateway.

## 3. Exceptions Inside DispatcherServlet: HandlerExceptionResolver

During an MVC dispatch, `DispatcherServlet` coordinates exception resolvers (`HandlerExceptionResolver`). When an exception during mapping/handling/rendering passes through the proper MVC path, a resolver can build a response, return an error view, or report that it did not handle it.

Common resolvers:

| Mechanism | Role | Notes |
| --- | --- | --- |
| `ExceptionHandlerExceptionResolver` | Looks up `@ExceptionHandler` in controllers or `@ControllerAdvice` / `@RestControllerAdvice` | Commonly used to format JSON errors |
| `ResponseStatusExceptionResolver` | Handles `@ResponseStatus` or `ResponseStatusException` and related `ErrorResponse` mechanisms | Status and error handling depend on version |
| `DefaultHandlerExceptionResolver` | Maps common Spring MVC exceptions to HTTP statuses | E.g., wrong HTTP method, media type, input |
| `ResponseEntityExceptionHandler` | Convenient base class for `@ControllerAdvice` to customize standard MVC errors | Not a global Servlet Filter |

This is a **chain of resolvers**, with precedence and customization/replacement hooks. A resolver can return `null` to defer to the next resolver, return a `ModelAndView`, or mark the exception as handled.

Example controller throwing a business exception:

```java
@GetMapping("/orders/{id}")
public OrderResponse read(@PathVariable long id) {
    if (id == 13) {
        throw new OrderBlockedException("Order blocked");
    }
    return new OrderResponse(id, "READY");
}
```

This belongs to an illustrative controller, not a standalone Java file. A `@RestControllerAdvice` with `@ExceptionHandler(OrderBlockedException.class)` can return an error JSON and `409 Conflict` for this error. Services can also throw exceptions and still be handled by advice **if the exception propagates to MVC dispatch without being caught elsewhere**.

Do not say advice only catches `throw` directly inside controller methods: exceptions arising in services, argument resolution, interceptors, or eligible MVC processing phases can also be handled by resolvers. The real boundary is **MVC dispatch and whether the exception actually passes through the resolver chain**, not merely package names or Java files.

## 4. Exceptions in Filters: Why Advice Does Not Catch Them Automatically

The Servlet API executes registered `Filter`s matching a URL and `DispatcherType`. A filter can:

- Inspect the request and **call** `chain.doFilter(request, response)` to forward.
- Inspect and **skip calling the chain**; write status/body itself, redirect, or reject.
- Throw `IOException`, `ServletException`, or unchecked exceptions before or after the chain.
- Wrap requests/responses, set headers, record metrics, decompress, enforce rate limits, or authenticate.

Example:

```java
@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain) throws ServletException, IOException {
    if (request.getRequestURI().endsWith("/blocked")) {
        throw new ServletException("Failure in outer filter");
    }
    chain.doFilter(request, response);
}
```

This is an **illustration** inside a `OncePerRequestFilter` subclass assuming imports; it does not compile alone. If an exception is thrown **before `chain.doFilter`**, `DispatcherServlet` has not been invoked and `@RestControllerAdvice` is not on the call stack to handle that exception. If an exception occurs **after `chain.doFilter` returns**, execution is back in the Filter and also outside MVC dispatch.

Notably, a filter can catch exceptions from `chain.doFilter` with `try/catch`. However, controller exceptions have usually already been handled by MVC resolvers before returning to the filter. Thus **filters do not reliably see every controller exception**, and advice does not reliably see every filter exception.

`OncePerRequestFilter` helps control execution across dispatcher types per its class contract, yet **does not mean it runs strictly once across the entire request lifecycle** under every thread/async/error dispatcher combination. Check registration details and `shouldNotFilterAsyncDispatch()`, `shouldNotFilterErrorDispatch()` hooks if re-dispatches occur.

### Do Not "Push" Exceptions into Controllers by Calling the Chain Again

After a filter encounters an error, calling `chain.doFilter` a second time can re-run handlers, trigger side effects, or double-write responses. To format filter errors as API JSON, choose one of the following **intentionally**:

1. Give the filter a dedicated **error writer** that knows the proper HTTP status/body.
2. From the filter, invoke an injected Spring MVC `HandlerExceptionResolver.resolveException(...)` **explicitly**; this requires controlling the resolver, `handler=null`, exception content, and ensuring the response is uncommitted.
3. Use `response.sendError(...)` to trigger **container error handling** (if mapped), letting `/error`/container build the response.
4. For authentication/authorization, let **Spring Security** handle them via `AuthenticationEntryPoint` and `AccessDeniedHandler` in the right place.

These approaches serve different purposes. Never wrap every filter in `catch (Exception e)` to return 200 or swallow errors, and never call `@RestControllerAdvice` like a plain Java utility class: it is a Spring MVC lifecycle component with context requirements.

## 5. setStatus, sendError, throw, and Committed Responses

Three actions have distinct semantics:

### 5.1. `response.setStatus(503)`

Sets the response status code; **does not guarantee** a container error dispatch. The application can proceed to write its own JSON/body, or finish with an empty response. A 503 status alone does not prove a Java exception occurred.

### 5.2. `response.sendError(503, "reason")`

Per the Servlet API, this signals an error status to the container to perform corresponding error handling, provided the response is not yet committed. In a Spring Boot servlet app with default error mapping, after `sendError` a real server typically uses the error page mechanism and may dispatch to `/error` with `DispatcherType.ERROR`. The exact content/body depends on the container, Boot, content negotiation, and security config.

Do not assume `sendError` always yields one identical JSON across Tomcat/Jetty/MockMvc, and never call `sendError` after writing/committing the response.

### 5.3. `throw new ServletException(...)`

Throws the exception up to whatever called the `Filter` or Servlet. If unhandled, the container may invoke an error page, log the error, and return 500. However, another filter/interceptor/container may catch it earlier; there is no guarantee Spring MVC advice will be called.

### 5.4. Response Committed

A response becomes **committed** when buffers flush, headers/body are sent, data streams out, or buffers overflow. Afterward, status and headers can generally no longer be changed as before. Calling `sendError` on a committed response can throw `IllegalStateException`; trying to write an error JSON after sending partial body bytes can produce a corrupted response or dropped connection.

Anti-pattern example:

```java
response.getWriter().write("partial data");
response.flushBuffer();
response.sendError(500, "failure"); // may throw IllegalStateException
```

This is an illustrative snippet inside a Servlet/Filter method; **never** use it in production. With streaming (`StreamingResponseBody`, `SseEmitter`, servlet output stream), if a failure happens mid-stream there is usually no chance left to switch to a standard JSON error. Design a dedicated event/error protocol or close the stream and log with appropriate telemetry.

## 6. ERROR Dispatch and Spring Boot's /error Endpoint

A Servlet container can map errors to an error page/resource. When error handling **dispatches** to an error page, the active request has `DispatcherType.ERROR` and may carry Servlet request attributes describing the original error.

Common attributes:

| Attribute | Content |
| --- | --- |
| `jakarta.servlet.error.status_code` | HTTP status that triggered error dispatch |
| `jakarta.servlet.error.request_uri` | URI of the original request |
| `jakarta.servlet.error.exception` | Exception that caused the error, if any |
| `jakarta.servlet.error.message` | Error message when present |
| `jakarta.servlet.error.servlet_name` | Originating servlet when present |

These attributes belong to **container error dispatch**. They do not necessarily appear on every 4xx/5xx response — for example, when a controller returns `ResponseEntity.status(404)` directly without error dispatch.

In Spring Boot Servlet MVC, auto-configuration typically provides the `/error` endpoint, `BasicErrorController`, and `ErrorAttributes` to produce HTML or machine-readable error responses for paths routed through error handling. This does not mean **every** exception thrown from a `@Controller` reaches `/error`: if an `@ExceptionHandler`/resolver already handled it and wrote the response, no additional error dispatch is needed.

A typical path:

```text
REQUEST dispatcher
  -> Filter
  -> response.sendError(503) or unresolved exception
  -> container processes error-page mapping

ERROR dispatcher (if configured and still handleable)
  -> Filters applying to ERROR (may differ from REQUEST)
  -> DispatcherServlet
  -> /error (Boot BasicErrorController if registered)
  -> error response
```

Spring Boot has `ErrorPageFilter` for certain WAR deployments on external Servlet containers, yet **do not confuse it with every application filter** or assume every embedded Tomcat app routes through it. Exact behavior depends on deployment packaging.

In Spring Boot 3, Servlet attribute names use the `jakarta.servlet.*` namespace, not `javax.servlet.*` from older Boot 2 projects.

## 7. Filters During ERROR Dispatch: Avoiding Duplicate Processing

`DispatcherType` in Jakarta Servlet has values `REQUEST`, `FORWARD`, `INCLUDE`, `ASYNC`, `ERROR`. The container selects filters based on their registered mappings and dispatcher types.

If a filter checks authentication or logs on `REQUEST` and is also registered for `ERROR`, it can run a second time on error dispatch. Common scenario:

- Original request `/api/payments` is rejected before MVC.
- The container creates an `ERROR` dispatch to `/error`.
- An authentication filter blocks `/error` again or a custom filter throws another exception.
- The client sees a 403/500 completely different from the original failure; logs may record duplicates or enter an error-handling loop.

Make explicit decisions:

1. Which filters apply to `REQUEST`? Which ones need `ASYNC` or `ERROR`?
2. With `OncePerRequestFilter`, override `shouldNotFilterErrorDispatch()`/`shouldNotFilterAsyncDispatch()` according to your purpose and security design.
3. If the error endpoint must serve rejected requests, configure matching security authorization; do not expose sensitive endpoints beyond scope.
4. When setting trace/correlation IDs, use request attributes or proper context propagation across dispatches; avoid accidentally minting a new ID for the same request.

**Do not enable all filters for ERROR by default**. At the same time, do not strip all security checks on ERROR dispatch if that could expose internal error details. Choose per contract and test end-to-end.

## 8. Spring Security: Exceptions Belong to Its Own Filter Chain

Spring Security Servlet is built on `FilterChainProxy` and security filters. Two critical error flows:

- **Authentication failure / unauthenticated caller:** `AuthenticationEntryPoint` typically initiates a login flow or returns 401. Depending on the scheme, it may redirect, send a Basic challenge, or write JSON; do not assume every app returns JSON 401.
- **Authenticated but unauthorized:** `AccessDeniedHandler` typically returns 403.
- `ExceptionTranslationFilter` translates `AuthenticationException` and `AccessDeniedException` from the relevant part of the **security filter chain downstream of it** into corresponding HTTP behavior.

Do not conclude that `@ExceptionHandler(AuthenticationException.class)` in controller advice will handle every Spring Security error: many errors occur **before MVC dispatch**. Conversely, a business exception in a controller can be handled by advice without `ExceptionTranslationFilter` participating.

Important specifics:

- `ExceptionTranslationFilter` does not arbitrarily catch every `RuntimeException`; it targets authentication/authorization exceptions and supported handling paths.
- Not every Filter in `SecurityFilterChain` runs **after** `ExceptionTranslationFilter`. Order matters. Earlier authentication filters may call failure handlers directly; use architecture/debug logs to verify actual flow.
- `CsrfFilter` can block POSTs before the controller; a 403 due to a missing CSRF token is not an error from `@Valid @RequestBody`.
- CORS preflight `OPTIONS` requests can be blocked in security/filters when misconfigured; do not assume the controller lacks OPTIONS support.
- Exceptions from method security in controllers/services can follow separate paths depending on proxies/advice/MVC and call sites. Diagnose via **stack traces**, filter ordering, and resolved exceptions; do not attribute every `AccessDeniedException` to one stage.
- If the API defines a uniform JSON error structure, configure `AuthenticationEntryPoint` and `AccessDeniedHandler` (or a dedicated error writer) per contract while keeping standard authentication headers.

## 9. Building a Java 17+ Example to Observe Three Error Sources

The demo application illustrates specifically:

- `GET /demo/ok` → controller returns 200.
- `GET /demo/controller-fail` → controller throws `DemoBusinessException`, `@RestControllerAdvice` catches it and returns JSON `409`.
- `GET /demo/filter-send-error` → Filter **skips MVC**, calls `sendError(503)`; container error handling may route to `/error`.
- `GET /demo/filter-throw` → Filter throws `ServletException` **before `DispatcherServlet`**; advice does not directly catch the original error; the container may return 500 under real HTTP handling.
- `GET /demo/missing` → URL has no dedicated mapping, typically 404, not necessarily involving a business exception.

Use a Spring Boot **3.x + Spring Web** Maven project, Java 17+, and starter test. On Boot 3, import Servlet classes from `jakarta.servlet.*`. Place the following classes in package `com.example.demo`.

### 9.1. Bootstrap Class

File `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 9.2. Business Exception

File `src/main/java/com/example/demo/DemoBusinessException.java`:

```java
package com.example.demo;

public class DemoBusinessException extends RuntimeException {
    public DemoBusinessException(String message) {
        super(message);
    }
}
```

This is a demo-specific error, not a standard Spring exception name. In real applications, do not decide HTTP status solely because every exception is a `RuntimeException`; define specific business error codes.

### 9.3. Controller and Response DTO

File `src/main/java/com/example/demo/DemoController.java`:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/demo/ok")
    public Result ok() {
        return new Result("OK");
    }

    @GetMapping("/demo/controller-fail")
    public Result controllerFail() {
        throw new DemoBusinessException("Order cannot be changed");
    }

    @GetMapping("/demo/filter-send-error")
    public Result filterSendError() {
        // If the Filter blocks properly, this method is never called.
        return new Result("SHOULD_NOT_REACH_CONTROLLER");
    }

    @GetMapping("/demo/filter-throw")
    public Result filterThrow() {
        // If the Filter throws before the chain, this method is never called.
        return new Result("SHOULD_NOT_REACH_CONTROLLER");
    }

    public record Result(String state) {}
}
```

### 9.4. @RestControllerAdvice for MVC Errors

File `src/main/java/com/example/demo/DemoExceptionAdvice.java`:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DemoExceptionAdvice {

    @ExceptionHandler(DemoBusinessException.class)
    public ResponseEntity<ApiError> onBusinessError(
            DemoBusinessException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "ORDER_BLOCKED",
                ex.getMessage(),
                request.getRequestURI());

        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }

    public record ApiError(
            String code,
            String message,
            String path) {}
}
```

For `/demo/controller-fail`, the JSON response displays the `ApiError` structure with status `409 Conflict`. Do not write an `@ExceptionHandler(Exception.class)` that catches everything and turns it into 400/409; doing so hides serious programming bugs and breaks proper 500 semantics.

In real applications, `ex.getMessage()` may contain internal data or user information; only use messages designed to be safely public. In the demo, the exception string is hardcoded by our code, not taken from stack traces or SQL.

### 9.5. Filter Before DispatcherServlet

File `src/main/java/com/example/demo/DemoBoundaryFilter.java`:

```java
package com.example.demo;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class DemoBoundaryFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String path = request.getRequestURI()
                .substring(request.getContextPath().length());

        if ("/demo/filter-send-error".equals(path)) {
            response.sendError(
                    HttpServletResponse.SC_SERVICE_UNAVAILABLE,
                    "Simulated failure in servlet filter");
            return;
        }

        if ("/demo/filter-throw".equals(path)) {
            throw new ServletException("Failure before MVC dispatcher");
        }

        chain.doFilter(request, response);
    }
}
```

Explanation:

- `@Component` registers a Servlet Filter bean in Spring Boot, and `@Order` sets precedence. Real applications have security/other filters; check registrations for exact ordering.
- Both error branches occur **before** `chain.doFilter`, so the controller never executes.
- With `sendError`, the Filter does not throw an exception; a real container can trigger an error dispatch to `/error`.
- With `throw`, the exception exits the Filter; MVC resolvers are not called for the original error.
- `substring(contextPath.length())` suffices for a simple demo; with multiple servlet mappings or forwarded paths, use proper path matchers/APIs rather than naive string slicing.
- `@Order(Ordered.HIGHEST_PRECEDENCE)` places the example early in the chain, **not as an unconditional recommendation** for production authentication or logging filters.
- `OncePerRequestFilter` has built-in logic deciding whether to skip async/error dispatches; app containers and test setups can have different dispatcher registrations.

## 10. Testing with curl Against a Real Servlet Container

Run the Maven Wrapper from the Boot project:

```bash
./mvnw spring-boot:run
```

On Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

The Java files above require Spring Boot Web on the classpath; `javac DemoController.java` alone will fail without dependencies. Default port is 8080 if `server.port` is unchanged.

### 10.1. Controller Success

```bash
curl -i http://localhost:8080/demo/ok
```

Expected 200 with JSON body:

```json
{"state":"OK"}
```

### 10.2. Controller Exception Handled by Advice

```bash
curl -i http://localhost:8080/demo/controller-fail
```

Expected `409 Conflict` and JSON equivalent to:

```json
{
  "code": "ORDER_BLOCKED",
  "message": "Order cannot be changed",
  "path": "/demo/controller-fail"
}
```

Field names/order serialized by Jackson may vary; compare values rather than byte-for-byte text. This is the MVC error path handled directly by `DemoExceptionAdvice`; normally no container `ERROR` dispatch occurs.

### 10.3. Filter sendError

```bash
curl -i http://localhost:8080/demo/filter-send-error
```

Expected **HTTP 503 Service Unavailable** emitted by the Filter. The body may be Boot `/error` JSON, HTML, or empty depending on config/`Accept`. Do not expect `ORDER_BLOCKED` from `DemoExceptionAdvice`: advice did not handle this original failure. When the container triggers error dispatch, error handlers can inspect `jakarta.servlet.error.status_code` and `jakarta.servlet.error.request_uri`.

### 10.4. Filter throw

```bash
curl -i http://localhost:8080/demo/filter-throw
```

Under default container settings, an unhandled exception typically produces **HTTP 500 Internal Server Error**; the body is supplied by the container or Boot error handling, if a response can still be written. Not every deployment guarantees the same error body and logs. If another Filter catches `ServletException`, the outcome can differ.

### 10.5. No Matching Route

```bash
curl -i http://localhost:8080/demo/missing
```

Usually 404, produced by MVC/resource handler/Boot error pathway. **Do not infer** that 404 always comes from `DemoBusinessException` or controller advice. If a reverse proxy intervenes, 404 can occur before the request reaches the Spring app.

## 11. MockMvc Testing: Limited Simulation Fidelity

MockMvc runs Spring MVC and filters registered in the test environment, yet **does not replicate every error dispatch mechanism of a real Servlet container listening on an HTTP port**. In particular, if a Filter calls `sendError`, MockMvc can assert the status, yet **does not automatically dispatch to Boot `/error` the way Tomcat does**. An exception thrown from a Filter may propagate straight out to the test instead of being turned into HTTP 500 by a container.

Create `src/test/java/com/example/demo/DemoBoundaryTest.java` with the `spring-boot-starter-test` dependency:

```java
package com.example.demo;

import jakarta.servlet.ServletException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DemoBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void controllerBusinessExceptionGoesThroughAdvice() throws Exception {
        mvc.perform(get("/demo/controller-fail"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("ORDER_BLOCKED"));
    }

    @Test
    void filterCanEndRequestBeforeMvc() throws Exception {
        mvc.perform(get("/demo/filter-send-error"))
                .andExpect(status().isServiceUnavailable());
        // MockMvc does not necessarily run container /error dispatch automatically.
    }

    @Test
    void rawFilterExceptionEscapesMockMvcDispatch() {
        assertThrows(ServletException.class,
                () -> mvc.perform(get("/demo/filter-throw")));
        // If another filter or custom exception handler wraps the error,
        // adjust this assertion to match your actual configuration.
    }

    @Test
    void normalRequestStillReachesController() throws Exception {
        mvc.perform(get("/demo/ok"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("OK"));
    }
}
```

Run:

```bash
./mvnw test
```

Windows:

```powershell
.\mvnw.cmd test
```

The test code above is **sample source expected to pass with default Boot 3.x/Web/Test**, not a report that it was executed on your machine. If the app uses Spring Security, custom filter registrations, async methods, or custom converters, tests must adapt accordingly.

### When You Need to Prove Container Error Dispatch

Use **real HTTP** integration tests with `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` and an HTTP client (such as `TestRestTemplate` in Boot 3 or Java `HttpClient`), or run the real app and test with `curl`. That lets you observe:

- Final status after `sendError` or an unresolved Filter exception.
- Response body/media type generated by `/error`.
- `ERROR` dispatch and actual filter registrations.
- Differences between an embedded app and a WAR on an external container.

Do not rely on a single MockMvc test to certify container forwarding/error pages in production.

## 12. Should You Manually Call HandlerExceptionResolver in a Filter?

Sometimes an API wants all filter errors to return the same JSON as MVC. A Filter can **inject** MVC's `HandlerExceptionResolver` bean and invoke it explicitly:

```java
// Illustrative code inside a custom Filter with an injected resolver.
try {
    chain.doFilter(request, response);
} catch (DomainRejectedException ex) {
    resolver.resolveException(request, response, null, ex);
}
```

This is a **pattern snippet**, not a standalone file. It only makes sense when:

1. `resolver` is the proper bean (often requiring `@Qualifier("handlerExceptionResolver")` if multiple beans exist).
2. The error type genuinely belongs to MVC handling, a compatible handler exists, and that handler works with `handler=null`.
3. The response is **uncommitted**, with no partial body written.
4. You check whether `resolveException` actually resolved it; returning `null` means still unhandled—never silently swallow exceptions.
5. You avoid duplicate logs, leaking raw exceptions, or swallowing security/system errors.

Some `@ExceptionHandler`s depend on a specific controller and cannot handle errors when `handler=null`; global advice is better suited. This approach couples the Filter to MVC, so also consider handling at the security layer, sharing a dedicated writer, or relying on container `/error`.

**Warning:** Do not wrap all of `chain.doFilter` in `catch (Exception)` and unconditionally call the resolver a second time: MVC may already have handled the error, the response may be committed, and writing again will corrupt the output. The example only shows intentional integration.

## 13. Observing Logs and Request Traces

A lone 500 response is not enough to identify its source. When debugging:

1. Verify whether the request reached the app via gateway/access logs.
2. Trace the correlation/request ID across ingress, Filters, `DispatcherServlet`, controller, and error dispatch.
3. Log **where the error is caught**: filters log their own errors; business exception handlers log at appropriate severity; containers log unresolved exceptions.
4. Compare `request.getDispatcherType()`: `REQUEST`, `ERROR`, or `ASYNC`.
5. In `ERROR` dispatch, inspect `jakarta.servlet.error.request_uri`, `jakarta.servlet.error.status_code`, and the exception (if present).
6. Check whether the response is already committed before attempting to change status/body.
7. Inspect filter registrations and ordering; `@Order` on filter beans, `FilterRegistrationBean`, and the security chain all affect order.
8. Read the stack trace carefully: where do Filter/Servlet container/MVC resolvers appear? Was the Spring controller method ever called?
9. For 401/403 responses, check authentication entry point/denied handler/CSRF first; do not rush to modify controller advice.
10. Use a reproducible test request and vary **one factor at a time** (Accept, credentials, URL, body size, dispatcher type).
11. Check whether the error body came from `/error`, `@RestControllerAdvice`, the gateway, or a reverse proxy.
12. Avoid logging tokens, cookies, Authorization headers, or raw request bodies just to debug an exception.

You can temporarily raise logging levels in a test environment to observe MVC handler mappings, the security filter chain, and controller advice, then lower them before production. Public error messages should use stable codes and safe text; keep stack traces in server-side logs.

## 14. Responsibility Comparison Table

| Error source | Reached `DispatcherServlet`? | Does `@RestControllerAdvice` catch root by default? | Component typically deciding the response |
| --- | --- | --- | --- |
| Controller/service throws exception during MVC dispatch | Yes | **Can**, if a matching handler exists | `HandlerExceptionResolver`, advice, or fallback |
| Invalid JSON in `@RequestBody` | Yes (at argument resolution) | **Can**, via MVC exception handler | Resolver/advice, usually 400 |
| Wrong HTTP method/Accept/media type in MVC mapping | Yes if reaching MVC | **Can**, depending on handler/resolver | MVC resolver, 405/406/415 common |
| Custom Filter throws before `chain.doFilter` | Not yet | **Not automatically** | Other filters, container error handling |
| Custom Filter calls `sendError` and stops chain | Not yet | **Not automatically** | Servlet container and `/error` if present |
| Custom Filter throws after downstream returns | Downstream may have finished | **Not automatically** | Filter/container; beware committed response |
| Spring Security authentication/authorization blocks before MVC | Usually not yet | **Not automatically** | EntryPoint/AccessDeniedHandler/filter |
| Container rejects malformed HTTP request before Servlet | No | No | Container/gateway |
| Container timeout/connection reset or response write failure | Depends on timing | Unlikely; body often can no longer change | Container/network |
| Async task throws after request thread leaves | Depends on how async is managed | **Depends on async mechanism** | MVC async dispatch resolver or container |

Do not read this table as claiming advice only handles exceptions thrown directly inside controller methods. The resolver chain operates within `DispatcherServlet`'s lifecycle and can handle errors from mapping, argument binding, rendering, or interceptors.

## 15. Async Errors and Deferred Processing

Spring MVC supports return types such as `Callable<T>`, `DeferredResult<T>`, `WebAsyncTask<T>`, and streaming. When a `Callable` managed by Spring MVC throws an exception, the framework can re-dispatch to the servlet with the error result and invoke MVC exception handling; this **differs** from manually spawning a thread outside the request lifecycle.

Do not assume `@RestControllerAdvice` catches every exception from an unmanaged `CompletableFuture.runAsync`, out-of-request callback, or message listener. An independent task can fail after the request has already finished; handle it with future completion hooks, executor error handlers, and separate telemetry.

Notes:

- Configure Servlet Filters for `ASYNC` dispatch if tracing/security context must be preserved, while avoiding unintended duplicate execution.
- Once a response is committed and streaming, an exception handler usually cannot replace the content with a new `ProblemDetail`.
- On async timeout, Spring MVC has dedicated timeout/interceptor/exception mechanisms; status may vary by configuration.
- Never send a new response from a background thread after the container has closed the request.
- MockMvc async tests may require `asyncDispatch` to verify the follow-up dispatch; calling `mvc.perform(...)` once alone does not cover the full lifecycle.

## 16. Designing the Error Contract: Consistent Yet Layer-Accurate

A real API may want the same error format across MVC, Security, and container layers:

```json
{
  "code": "REQUEST_REJECTED",
  "message": "Request cannot be processed",
  "traceId": "2e1d8f..."
}
```

**Having the same format does not mean one handler catches every error source.** You can use:

- **MVC layer:** `@RestControllerAdvice` or `ResponseEntityExceptionHandler` for validation, conversion, and service/business exceptions; optionally using `ProblemDetail`.
- **Security layer:** `AuthenticationEntryPoint`/`AccessDeniedHandler` for 401/403. Pay attention to `WWW-Authenticate` for Basic/Bearer per contract.
- **Filter layer:** a dedicated error writer or intentional delegation, never writing the response twice.
- **Container/error path:** configure Boot `ErrorAttributes`/`ErrorController` or server error pages for a safe fallback.

A shared writer can keep `code`, `message`, and `traceId` consistent, while explicitly passing status and avoiding coupling business layers to the Servlet API. Never turn 500 into 400, never treat 401/403 as 500, and never leak raw exceptions/stack traces to clients.

With Spring 6+, `ProblemDetail` helps express standard `type`, `title`, `status`, `detail`, `instance`, and extension fields. RFC 9457 is the modern Problem Details standard. When adopting it, ensure the outer HTTP status matches `status` and use `application/problem+json` when writing JSON. Container/Boot error pages do not automatically match every MVC-generated `ProblemDetail`.

## 17. Common Pitfalls

1. **"`@RestControllerAdvice` catches every web error":** False. It is an MVC mechanism; filters/containers can fail before or after dispatch.
2. **"Every 500 is a controller exception":** False. Containers, filters, gateways, async tasks, or serializers can also produce 500.
3. **"Throwing `ResponseStatusException` from a Filter produces MVC-style JSON":** Not by default. Exceptions thrown before `DispatcherServlet` do not automatically enter the MVC resolver chain.
4. **"`sendError` and `setStatus` are the same":** False. `sendError` triggers Servlet error handling; `setStatus` only sets the status code.
5. **"Status 404 always comes from an exception":** False. A response can have a status without any exception being thrown.
6. **"A Filter runs strictly once per HTTP request across all dispatches":** Do not assume that. Check `REQUEST`/`ERROR`/`ASYNC` and `OncePerRequestFilter` behavior.
7. **"MockMvc behaves identically to container error pages":** False. MockMvc does not replace real HTTP tests for `ERROR` dispatch.
8. **"With `ExceptionTranslationFilter`, every `RuntimeException` becomes 401/403":** False. It focuses on authentication/authorization exceptions inside the security chain.
9. **"JSON syntax errors are 500 from Jackson":** False in most standard MVC APIs; unreadable input is normally 400 when handled by the framework.
10. **"`HandlerExceptionResolver` always returns JSON":** False. Resolvers can render views, set statuses, or defer to other resolvers/containers.
11. **"Write the body first, then catch errors and return new JSON":** Unsafe once the response is committed.
12. **"A Filter can call `chain` again so the controller handles the exception":** Risks double execution/double writes; never do this.
13. **"Configuring `/error` means already-handled MVC errors still run `/error`":** Not necessarily; distinguish MVC resolver handling from container error dispatch.
14. **"Disabling security on all `ERROR` dispatches is harmless":** Assess information disclosure and policy; configure only the necessary scope.
15. **"Log every request body to find the cause":** Can leak PII/tokens; log selectively and redact sensitive data.
16. **"Setting the highest filter order is always right":** Filter order depends on purpose; wrong ordering breaks security, CORS, request wrappers, and tracing.
17. **"`ResponseEntity.status(500)` proves the container hit an exception":** False. Controllers can return any status explicitly.
18. **"`@ExceptionHandler(Exception.class)` returning 200 so clients don't error":** Breaks HTTP semantics and observability; classify statuses properly.

## 18. Practical Investigation Workflow

When receiving a "500 Internal Server Error" log or a client reporting an unexpected error body:

1. **Check whether the request entered the container** using access logs and gateway traces. If not, investigate ingress/network first.
2. **Check whether filters ran:** add safe logging with a correlation ID at the start of an observability Filter, without logging tokens/bodies.
3. **Check whether `DispatcherServlet` matched a handler:** enable appropriate mapping logs, or inspect `HandlerMapping.BEST_MATCHING_HANDLER_ATTRIBUTE` when needed and request context is available.
4. **Check whether controller/service was invoked:** a breakpoint/log at the method entry is insufficient for binding/argument conversion errors because those occur before the method runs.
5. **Check whether exception resolvers ran:** log MVC resolvers/advice; if an exception came from a Filter before the chain, they normally did not.
6. **Check `getDispatcherType()` for `REQUEST` vs. `ERROR`:** the same URL may appear in two dispatches during one failure.
7. **Check whether the response was already committed:** if committed, body/status can no longer be replaced.
8. **Check Security exception handling:** for 401/403, analyze filter order, exception translation, entry point/denied handler, CSRF, and CORS.
9. **Check `/error` fallback:** Boot `ErrorAttributes` and container error pages may decide the final body.
10. **Use both kinds of tests:** MockMvc to verify MVC advice/filter interaction, real HTTP servers to verify Servlet `ERROR` dispatch.
11. **Check deployment setup:** embedded Tomcat/Jetty vs. external WAR container; registrations and error pages can differ.
12. **Fix the root cause at the owning boundary:** validation in MVC, authentication in security, filter-specific error handling, or container limits/configs.

Remember: **where the exception occurs**, **who can see it**, and **who writes the final response** are three separate questions. Separating them prevents writing an overly broad `@RestControllerAdvice` that still misses Filter and container errors.

## 19. Self-Check Questions

**Question 1.** A `@RestController` throws `DemoBusinessException` and an advice has a matching `@ExceptionHandler`. Who handles it?

**Answer:** Typically MVC's `ExceptionHandlerExceptionResolver` invokes the advice to build the response. The controller method was called.

**Question 2.** A custom Filter throws `ServletException` before calling `chain.doFilter`. Does the advice catch it automatically?

**Answer:** No. `DispatcherServlet` has not processed the request yet, so the original error does not automatically reach MVC resolvers. Other filters or the Servlet container may handle it.

**Question 3.** A Filter calls `response.sendError(503)` and returns. Will the response always match the advice's JSON?

**Answer:** No. Container/Boot `/error` handling depends on configuration, and there is no guarantee about the body.

**Question 4.** Why does `mvc.perform` sometimes throw the Filter exception directly in tests, whereas calling HTTP via Tomcat returns 500?

**Answer:** MockMvc simulates MVC/filters but does not fully execute the Servlet container's error-page/`ERROR` dispatch mechanism. A real HTTP server handles uncaught Servlet/Filter errors.

**Question 5.** Does a 403 status before the controller guarantee `@Valid` failed?

**Answer:** No. It is usually related to security/CSRF/authorization/filters/gateways. Input validation typically causes 400, not automatically 403.

**Question 6.** Can status `200 OK` accompany a handled Java exception?

**Answer:** Yes if a custom handler wrote the wrong status or intentionally returned 200, though that is usually poor API design. Never use 200 for business errors that should be represented by appropriate error statuses.

**Question 7.** Why is calling `response.sendError` after `flushBuffer()` dangerous?

**Answer:** The response is already committed; it is no longer safe to change status/body, which can throw `IllegalStateException` or drop the connection.

**Question 8.** When can `ERROR` dispatch trigger a Filter a second time?

**Answer:** When the container dispatches to an error page and the filter is registered for `DispatcherType.ERROR`, unless the Filter logic skips that dispatch appropriately.

**Question 9.** Does `ExceptionTranslationFilter` convert every `RuntimeException` into 401?

**Answer:** No. It primarily handles `AuthenticationException` and `AccessDeniedException` from downstream in the Spring Security chain.

**Question 10.** If an API needs uniform errors across controllers, security, and filters, is writing a single `@RestControllerAdvice` sufficient?

**Answer:** Not enough. You must design response-creation points across MVC, Spring Security, filters, and container fallback, aligning error schema and statuses.

## 20. References

- Spring Framework — MVC exception resolver chain and container error pages: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Framework 6.2 — Controller Advice: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html
- Spring Framework — Error Responses and ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework — DispatcherServlet: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html
- Spring Security — Servlet FilterChainProxy and ExceptionTranslationFilter: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Exception Handling: https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-exceptiontranslationfilter
- Spring Boot — Servlet Web Error Handling: https://docs.spring.io/spring-boot/reference/web/servlet.html#web.servlet.spring-mvc.error-handling
- Spring Boot — ErrorAttributes API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/error/ErrorAttributes.html
- Spring Boot — ErrorPageFilter API (WAR/non-embedded): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/support/ErrorPageFilter.html
- Jakarta Servlet specification and DispatcherType: https://jakarta.ee/specifications/servlet/
- Jakarta Servlet 6.0 DispatcherType API: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/dispatchertype
- RFC 9457 — HTTP API Problem Details: https://www.rfc-editor.org/rfc/rfc9457.html
