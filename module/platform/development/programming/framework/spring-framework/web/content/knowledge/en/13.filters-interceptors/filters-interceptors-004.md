# preHandle, postHandle, afterCompletion, and Callback Conditions in Spring MVC

## 1. Purpose and Use Cases

A request passing through Spring MVC can be observed or intercepted before/after controller execution by multiple `HandlerInterceptor` instances. The three common callbacks are:

- `preHandle(request, response, handler)`: before `HandlerAdapter` invokes the handler; returns `true` to continue or `false` to stop the chain.
- `postHandle(request, response, handler, modelAndView)`: after the handler executes **successfully along the synchronous path**, before the view is rendered; not a reliable place to modify an already-written JSON response.
- `afterCompletion(request, response, handler, exception)`: at the end of dispatch completion to clean up resources/record telemetry, **only for interceptors whose `preHandle` completed and returned `true`**, with an important exception for asynchronous processing.

After this lesson, you will know:

1. Where `HandlerInterceptor` sits inside `DispatcherServlet` and how it differs from a Servlet Filter.
2. Callback ordering with **multiple interceptors**, when returning `false`, when a controller throws an exception, on view rendering errors, and on async requests.
3. The exact meaning of `postHandle`, why `ModelAndView` can be null, `afterCompletion`, and the `Exception ex` parameter.
4. When `AsyncHandlerInterceptor.afterConcurrentHandlingStarted` is called instead of the two normal callbacks and when a second dispatch occurs.
5. How to write, register, and test two interceptors with **Java 17+, Spring Framework 6.x / Spring Boot 3.x, MockMvc**, including response body and error cases.
6. How to avoid common mistakes: implicitly relying on interceptors for security, setting headers too late, cleaning up `ThreadLocal` at the wrong time, or writing two responses.

**Scope:** Spring MVC on the Servlet stack, not Spring WebFlux. Interface names and callback semantics apply to Spring MVC 6.x; for Spring 7/Boot 4, verify the API against the version in use. In the example, both interceptors are registered specifically on `/trace/**`; they do not apply to all servlet requests by default.

## 2. Where Do They Sit in the Processing Flow?

```text
Client
  |
  v
Servlet container
  |
  v
Servlet Filters (CORS, compression, security, tracing ...)
  |
  v
DispatcherServlet
  |
  +-- HandlerMapping selects handler
  |      -> HandlerExecutionChain(handler, [Interceptor A, Interceptor B])
  |
  +-- A.preHandle(request, response, handler)
  |      -> true
  +-- B.preHandle(request, response, handler)
  |      -> true
  |
  +-- HandlerAdapter invokes controller/handler
  |
  +-- B.postHandle(...)             \
  +-- A.postHandle(...)              } successful synchronous path
  |
  +-- render ModelAndView if view exists
  |
  +-- B.afterCompletion(...)         \
  +-- A.afterCompletion(...)          } post-dispatch cleanup
  |
  v
Servlet Filters after chain.doFilter -> container -> client
```

**Do not confuse Filter with HandlerInterceptor:**

| Question | Servlet Filter | Spring MVC HandlerInterceptor |
| --- | --- | --- |
| Where does it sit? | Before/outside `DispatcherServlet` in the Servlet filter chain | After `HandlerMapping` finds the handler, inside MVC |
| API surface | `Filter#doFilter`, `FilterChain` | `preHandle`, `postHandle`, `afterCompletion` |
| Aware of MVC handler? | Not by default | Receives `handler`, which may be a `HandlerMethod` |
| Intercepts requests not mapped to a controller? | Usually yes, depending on URL/dispatcher registration | Only when the request reaches a `HandlerExecutionChain` with the interceptor |
| Early security for all requests? | Spring Security sits on the filter chain and is better suited | Should not serve as the primary security layer |
| Intervening after JSON response body is written? | A Filter can wrap the response with an appropriate wrapper, still minding commit | `postHandle` is usually too late for `@ResponseBody`/`ResponseEntity` |

Spring Framework recommends **Spring Security or filter-chain security** rather than using an interceptor as the primary security barrier, because interceptor mappings and security boundaries may not be equivalent. Interceptors are well suited for cross-cutting logic **tied to MVC handlers**, such as timing observation, adding model attributes for views, auxiliary business-rule checks, or tracking.

## 3. The Three Callbacks: Signatures and Semantics

The `org.springframework.web.servlet.HandlerInterceptor` interface has default methods:

```java
boolean preHandle(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler) throws Exception;

void postHandle(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler,
    ModelAndView modelAndView) throws Exception;

void afterCompletion(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler,
    Exception ex) throws Exception;
```

This is an **API signature excerpt**, requiring Jakarta Servlet, `ModelAndView`, and `HandlerInterceptor` imports in real source. In modern Spring Framework, methods have default implementations so you only override what you need. `preHandle` returns `true` by default.

### 3.1. preHandle: Deciding Whether to Proceed

`preHandle` runs after `HandlerMapping` selects `handler` and before `HandlerAdapter` invokes it. `true` means MVC proceeds to the next interceptor or the handler. `false` means the interceptor has handled/intentionally terminated the response and Spring **does not invoke the handler**.

```java
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception {
    if (request.getHeader("X-Feature") == null) {
        response.sendError(400, "Missing X-Feature");
        return false;
    }
    return true;
}
```

This is a snippet inside a class implementing `HandlerInterceptor`. When returning `false`, you must ensure the response is properly resolved: set a status, body/redirect, `sendError`, or another mechanism. **Returning `false` without setting anything** can produce an empty response with an unintended default status.

Subtle point: `false` is not a Java exception. `@RestControllerAdvice` does not automatically catch an `Exception` merely because an interceptor returned false. With `sendError`, container error handling may proceed according to configuration, unlike writing the body directly.

### 3.2. postHandle: After Handler Success, Before View Rendering

`postHandle` receives `ModelAndView` and can add metadata for the view if a model/view is still being processed:

```java
@Override
public void postHandle(HttpServletRequest request,
        HttpServletResponse response, Object handler,
        ModelAndView mav) {
    if (mav != null) {
        mav.addObject("renderedBy", "spring-mvc");
    }
}
```

**With `@ResponseBody`/`ResponseEntity`, the HTTP response has usually already been written and possibly committed inside `HandlerAdapter` before `postHandle`.** Therefore, do not use `postHandle` to “guarantee” adding a JSON property, changing status/headers, or writing an error body. For REST JSON output, use `ResponseBodyAdvice` at the right serialization stage, controller/`ResponseEntity` to set status/headers, or a filter/response wrapper for specialized requirements.

`mav == null` is normal when a handler returns a response body, writes directly, returns null, or for certain other handler types; it is not automatically an error.

### 3.3. afterCompletion: Cleanup After Full Processing

`afterCompletion` typically runs after the view has finished rendering (if any). Good uses include closing resources owned by the interceptor itself, measuring overall latency, marking completion, clearing thread-local state created by the interceptor, and logging success/failure with controlled details.

```java
@Override
public void afterCompletion(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex) {

    // Clean up only data owned by this interceptor.
    // Do not try to change status/body when the response may already be committed.
}
```

**Exact condition:** called only for interceptors whose `preHandle` **completed successfully and returned `true`** in that chain. An interceptor that returned `false` does not get its own `afterCompletion` called; if `preHandle` threw before returning `true`, its own callback is not guaranteed either.

The `ex` parameter is not “every error that occurred.” An exception already handled by `HandlerExceptionResolver` may **not appear** in `afterCompletion(ex)`. If a controller returned a 409 response normally, `ex` can be null. Do not use `ex == null` to conclude the HTTP status is always 2xx; inspect `response.getStatus()` and application signals.

## 4. Ordering When Registering Multiple Interceptors

Suppose two interceptors A then B are registered, both matching the URL. Successful synchronous timeline:

```text
A.pre
B.pre
controller
B.post
A.post
view rendering if any
B.after
A.after
```

Rule:

- **Before handler**: `preHandle` in registration order A → B.
- **After handler**: `postHandle` in reverse order B → A.
- **Completion**: `afterCompletion` also in reverse order B → A.

This order resembles a nested structure:

```text
A {
    B {
        handler
    }
}
```

Actual ordering depends on the `HandlerExecutionChain` built by `HandlerMapping`, not merely the list of `@Component` beans in the application context. Spring Boot may have framework- or library-added interceptors; when debugging, inspect the **actual interceptor chain** for the handler.

### 4.1. B Returns false

If A returns true and B returns false:

```text
A.pre -> true
B.pre -> false, writes response itself
A.after
(stop: controller, B.post, A.post, B.after do not run)
```

Spring invokes `afterCompletion` in reverse order for interceptors **that succeeded `preHandle` before B**. B does not receive its own `afterCompletion`. Therefore, if B allocates resources/sets a `ThreadLocal` **before deciding to return false**, B must clean up along the `false` branch itself or restructure its design; do not “wait for `afterCompletion`” to clean up.

### 4.2. A Returns false Immediately

```text
A.pre -> false
(stop: B.pre, controller, and any post/after of A/B do not run)
```

A is responsible for sending the response. Because no interceptor has completed `preHandle=true`, no `afterCompletion` runs from this chain.

### 4.3. B Throws an Exception in preHandle

```text
A.pre -> true
B.pre -> throws exception
(normally no B.after)
A.after may run during MVC exception handling flow
```

Preceding interceptors that already returned true may be cleaned up as `DispatcherServlet` handles the error; do not generalize that B's callback always runs. If B allocates resources and then throws in `preHandle`, place cleanup in B's own `catch/finally` or move resource allocation to a place with guaranteed cleanup.

### 4.4. B Returned true, but the Controller Throws an Exception

```text
A.pre -> true
B.pre -> true
controller -> throws
(no A.post or B.post for failed handler execution)
exception resolvers / @ControllerAdvice
B.after
A.after
```

Normally `postHandle` is not called after a handler throws an exception. `afterCompletion` can still run because both A/B returned true. Afterward, if MVC advice handled the exception, `ex` observed in completion may be null; do not rely on `ex` to count business errors.

## 5. Callback Scenario Table: Practical Takeaways

| Scenario | preHandle | postHandle | afterCompletion |
| --- | --- | --- | --- |
| Synchronous handler succeeds, A/B both true | A → B | B → A | B → A |
| A true, B false | A → B (B stops) | None | A only |
| A false | A only | None | None |
| Handler throws exception, advice handles | A → B | Usually none | B → A; `ex` may be null |
| Handler returns JSON `@ResponseBody` successfully | A → B | B → A, `mav` usually null; body may already be written | B → A |
| Handler view rendering fails | A → B | May already have run before render | Completion for active interceptors; error depends on resolver |
| MVC handler starts async | A → B on first dispatch | Not on first dispatch | Not on first dispatch; use async callbacks |
| Async completes and redispatches | Usually A → B on ASYNC dispatch | When result is processed appropriately | When ASYNC dispatch finishes appropriately |
| Filter rejects before `DispatcherServlet` | No MVC chain | None | None |
| No matching `HandlerExecutionChain` found | No MVC interceptors in chain | None | None |

Do not interpret this table as a rule that “every 404 skips interceptors”: in some configurations, a 404 request may match another handler (such as a resource handler) before deciding the resource is missing, and that handler has its own interceptors. Likewise, exceptions during mapping before the chain is built follow a different path than exceptions after `preHandle`.

## 6. ModelAndView, View Rendering, and REST Responses

Controller returning a view:

```java
@Controller
class PageController {
    @GetMapping("/pages/home")
    String home(Model model) {
        model.addAttribute("title", "Home");
        return "home";
    }
}
```

The code above is a **class excerpt in a Spring MVC project** and renders only when a matching `home` template exists. `postHandle` can inspect `ModelAndView` and add attributes before view rendering. `afterCompletion` runs after the view finishes processing.

REST controller:

```java
@RestController
class ApiController {
    @GetMapping("/api/health")
    Map<String, String> health() {
        return Map.of("status", "ok");
    }
}
```

This is an illustrative snippet requiring Java/Spring imports and a Spring Web project. JSON is typically written inside `HandlerAdapter` by `HttpMessageConverter`. `postHandle` may still run, but `ModelAndView` is usually null and modifying the HTTP body/headers then may already be too late.

**If setting an important response header is required**, prefer:

- `ResponseEntity.ok().header("X-...", "...").body(dto)` when the controller owns the header.
- `ResponseBodyAdvice` when modifying the response body during serialization per MVC policy.
- A Servlet Filter when the requirement applies to non-MVC requests too or requires a Servlet-level response wrapper.
- Do not use `postHandle` as a mechanism to guarantee security headers in all cases: view/REST/error paths and response commit timing follow different execution paths.

## 7. AsyncHandlerInterceptor: When Three Callbacks Are Not Enough

When a controller returns `Callable`, `DeferredResult`, or initiates Spring MVC-managed Servlet async processing, **the initial dispatch may exit before the handler result is ready**. In that case, `DispatcherServlet` does not call `postHandle` and `afterCompletion` on the initial dispatch as usual.

`AsyncHandlerInterceptor` extends `HandlerInterceptor` by adding:

```java
@Override
public void afterConcurrentHandlingStarted(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception {
    // Clean up thread-bound state of the first dispatch.
}
```

This callback is invoked **instead of** `postHandle`/`afterCompletion` on the dispatch that started async processing. It is useful if the interceptor placed MDC or a `ThreadLocal` on the request thread and must clean it up before returning the thread to the Servlet container.

Typical flow of an async request (both A/B true):

```text
REQUEST dispatch:
    A.pre
    B.pre
    controller returns Callable/DeferredResult -> MVC starts async
    B.afterConcurrentHandlingStarted
    A.afterConcurrentHandlingStarted
    (no B.post/A.post, no B.after/A.after on the first dispatch)

When async result completes:
ASYNC dispatch:
    A.pre
    B.pre
    MVC processes the available async value/exception
    B.post
    A.post
    B.after
    A.after
```

Some details depend on the adapter, return type, async timeout, and filter setup. When a MVC-managed `Callable` throws an exception, the exception may be handled on the subsequent dispatch through resolvers. **Do not equate a manually spawned `CompletableFuture` outside MVC with the controller's Servlet async lifecycle.**

### 7.1. Timeout or Network Error May Have No Completion Dispatch

If an async request times out or the client disconnects, the container may not redispatch along the path you expect; `postHandle`/`afterCompletion` may then **never be called**. For stronger lifecycle callbacks, Spring provides `WebAsyncManager.registerCallableInterceptor`, `registerDeferredResultInterceptor`, and `DeferredResult` callbacks such as `onTimeout`/`onCompletion`. Use the right mechanism, check framework/version behavior, and always ensure thread-specific cleanup.

### 7.2. Do Not Use ThreadLocal as Request-Wide Storage

A `ThreadLocal` is bound only to the current thread. If `A.pre` stores `System.nanoTime()` in a `ThreadLocal` on the request thread, the ASYNC dispatch may arrive on a different thread; the value will not appear automatically. For a start time measured across multiple dispatches, use a request attribute or an explicitly propagated context, while keeping in mind the request may complete abnormally.

Safe timing example:

```java
request.setAttribute("startNanos", System.nanoTime());

// In a callback for the same request, read the attribute using a namespaced key.
Long started = (Long) request.getAttribute("startNanos");
```

This is an illustrative snippet, not a full program; avoid generic attribute names in large apps to prevent collisions. If using MDC, remember to remove/restore MDC on each thread and have dedicated callbacks when async starts.

## 8. Complete Java 17+ Example: Two Interceptors A and B

Spring Boot 3.x example:

- A and B are registered only for `/trace/**`.
- Request `/trace/ok`: `A.pre`, `B.pre`, `controller`, `B.post`, `A.post`, `B.after`, `A.after`.
- Request `/trace/blocked`: B blocks with 403; `A.after` still runs, `B.after` does not run.
- Request `/trace/fail`: controller throws `DemoFailure`, advice returns 409, `postHandle` is not called, completion runs for both A/B.
- Request `/trace/async`: returns `Callable<String>`; initial dispatch invokes `afterConcurrentHandlingStarted`, and after async dispatch runs the appropriate callbacks.

Use Spring Initializr Maven, Java 17+, dependencies `spring-boot-starter-web` and `spring-boot-starter-test`. Use package `com.example.demo` for all classes. No database needed.

### 8.1. DemoApplication.java

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

### 8.2. TraceEvents.java

File `src/main/java/com/example/demo/TraceEvents.java`:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import java.util.ArrayList;
import java.util.List;

public final class TraceEvents {
    private static final String KEY =
            TraceEvents.class.getName() + ".events";

    private TraceEvents() {}

    @SuppressWarnings("unchecked")
    public static List<String> of(HttpServletRequest request) {
        Object value = request.getAttribute(KEY);
        if (value instanceof List<?>) {
            return (List<String>) value;
        }
        List<String> events = new ArrayList<>();
        request.setAttribute(KEY, events);
        return events;
    }

    public static void add(HttpServletRequest request, String event) {
        of(request).add(event);
    }
}
```

`TraceEvents` uses a **request attribute** instead of a singleton global list. As a result, each request has an independent trace without mixing user data. This serves only for demo/testing callbacks on the dispatch flow; in production, async concurrency/telemetry may require thread-safe collections and a proper tracing framework. Do not expose these events in responses as part of an API contract.

### 8.3. TraceInterceptor.java

File `src/main/java/com/example/demo/TraceInterceptor.java`:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.AsyncHandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;

public class TraceInterceptor implements AsyncHandlerInterceptor {
    private final String name;

    public TraceInterceptor(String name) {
        this.name = name;
    }

    @Override
    public boolean preHandle(HttpServletRequest request,
            HttpServletResponse response, Object handler)
            throws Exception {

        TraceEvents.add(request, name + ".pre");

        if ("B".equals(name)
                && request.getRequestURI().endsWith("/trace/blocked")) {
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            response.setContentType("text/plain;charset=UTF-8");
            response.getWriter().write("BLOCKED");
            return false;
        }
        return true;
    }

    @Override
    public void postHandle(HttpServletRequest request,
            HttpServletResponse response, Object handler,
            ModelAndView mav) {
        TraceEvents.add(request, name + ".post");
        // REST response body may already be written: do not modify body/headers here.
    }

    @Override
    public void afterCompletion(HttpServletRequest request,
            HttpServletResponse response, Object handler,
            Exception ex) {
        TraceEvents.add(request, name + ".after");
    }

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response, Object handler) {
        TraceEvents.add(request, name + ".concurrent");
    }
}
```

B short-circuits the `/trace/blocked` route. Because B returns false, B **does not receive** `afterCompletion`; the demo allocates no extra resources, so no further cleanup is needed. If an interceptor uses a `ThreadLocal` in `preHandle`, remember to handle the false/throw path directly in the interceptor rather than depending on `afterCompletion` afterward.

### 8.4. InterceptorConfig.java

File `src/main/java/com/example/demo/InterceptorConfig.java`:

```java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class InterceptorConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new TraceInterceptor("A"))
                .addPathPatterns("/trace/**");
        registry.addInterceptor(new TraceInterceptor("B"))
                .addPathPatterns("/trace/**");
    }
}
```

A is registered before B in the same `InterceptorRegistry` and both match the demo routes. `excludePathPatterns` can be used for exceptions. Do not attach an Interceptor globally too broadly without checking which static resources/error endpoints or other frameworks might match.

### 8.5. DemoFailure.java

File `src/main/java/com/example/demo/DemoFailure.java`:

```java
package com.example.demo;

public class DemoFailure extends RuntimeException {
    public DemoFailure() {
        super("Simulated controller failure");
    }
}
```

### 8.6. TraceController.java

File `src/main/java/com/example/demo/TraceController.java`:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import java.util.concurrent.Callable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TraceController {

    @GetMapping("/trace/ok")
    public String ok(HttpServletRequest request) {
        TraceEvents.add(request, "handler");
        return "OK";
    }

    @GetMapping("/trace/blocked")
    public String blocked() {
        return "SHOULD_NOT_RUN";
    }

    @GetMapping("/trace/fail")
    public String fail(HttpServletRequest request) {
        TraceEvents.add(request, "handler");
        throw new DemoFailure();
    }

    @GetMapping("/trace/async")
    public Callable<String> async() {
        return () -> "ASYNC";
    }
}
```

The controller only processes requests that B allows through. `blocked()` exists intentionally to demonstrate a handler **that is mapped yet blocked by `preHandle` before invocation**; it is not a 404 error.

### 8.7. TraceAdvice.java

File `src/main/java/com/example/demo/TraceAdvice.java`:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class TraceAdvice {

    @ExceptionHandler(DemoFailure.class)
    public ResponseEntity<String> handleDemo(
            DemoFailure ex, HttpServletRequest request) {
        TraceEvents.add(request, "advice");
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body("HANDLED");
    }
}
```

`DemoFailure` is handled by MVC advice as 409. `afterCompletion` still runs for interceptors that returned true, whereas `postHandle` is not called along the handler-throws path. The `ex` parameter of `afterCompletion` **may be null** if the exception has already been handled; therefore, do not write tests expecting `ex` to necessarily be `DemoFailure`.

### 8.8. Running the Application

In a project with Maven Wrapper from Initializr:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

The project uses port 8080 by default unless `server.port` is configured otherwise. The files require Spring MVC and Servlet/Jakarta dependencies; you cannot run `javac TraceInterceptor.java` standalone outside the Maven project classpath.

## 9. curl: Status and Body

### 9.1. Success Flow

```bash
curl -i http://localhost:8080/trace/ok
```

Expected **200 OK**, body:

```text
OK
```

Although `TraceEvents` collects `A.pre → B.pre → handler → B.post → A.post → B.after → A.after`, the client sees only the body `OK`; the trace is kept in a request attribute for testing. Spring does not automatically append the event list to the HTTP body.

### 9.2. B Blocks

```bash
curl -i http://localhost:8080/trace/blocked
```

Expected **403 Forbidden**, body:

```text
BLOCKED
```

`TraceController.blocked` does not run; B explicitly writes the response and returns false. Do not infer that the system performed real authorization: this is only a short-circuit demo, not a production security architecture.

### 9.3. Controller Error

```bash
curl -i http://localhost:8080/trace/fail
```

Expected **409 Conflict**, body:

```text
HANDLED
```

`TraceAdvice` mapped the simulated business exception. `postHandle` does not run for the throwing handler; completion of active interceptors is still triggered after MVC error resolution.

### 9.4. Async

```bash
curl -i http://localhost:8080/trace/async
```

Expected **200 OK**, body:

```text
ASYNC
```

One HTTP request can go through two internal servlet dispatches, so callback/trace logs show multiple `preHandle` calls. Do not infer from a single `curl` call that the callback ran only once.

## 10. MockMvc: Testing Exact Ordering

Create `src/test/java/com/example/demo/TraceInterceptorTest.java` with the `spring-boot-starter-test` dependency:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TraceInterceptorTest {

    @Autowired
    MockMvc mvc;

    private static List<String> events(MvcResult result) {
        return TraceEvents.of(result.getRequest());
    }

    @Test
    void successfulHandlerHasReversePostAndCompletion() throws Exception {
        MvcResult result = mvc.perform(get("/trace/ok"))
            .andExpect(status().isOk())
            .andExpect(content().string("OK"))
            .andReturn();

        assertEquals(List.of(
            "A.pre", "B.pre", "handler",
            "B.post", "A.post",
            "B.after", "A.after"
        ), events(result));
    }

    @Test
    void falseShortCircuitsOnlyPreviouslyCompletedInterceptors()
            throws Exception {
        MvcResult result = mvc.perform(get("/trace/blocked"))
            .andExpect(status().isForbidden())
            .andExpect(content().string("BLOCKED"))
            .andReturn();

        assertEquals(List.of("A.pre", "B.pre", "A.after"),
                events(result));
    }

    @Test
    void resolvedControllerExceptionDoesNotCallPostHandle()
            throws Exception {
        MvcResult result = mvc.perform(get("/trace/fail"))
            .andExpect(status().isConflict())
            .andExpect(content().string("HANDLED"))
            .andReturn();

        assertEquals(List.of(
            "A.pre", "B.pre", "handler", "advice",
            "B.after", "A.after"
        ), events(result));
    }

    @Test
    void asyncUsesConcurrentCallbackBeforeRedispatch()
            throws Exception {
        MvcResult first = mvc.perform(get("/trace/async"))
            .andExpect(request().asyncStarted())
            .andReturn();

        List<String> before = List.copyOf(events(first));
        assertTrue(before.contains("A.concurrent"));
        assertTrue(before.contains("B.concurrent"));
        assertFalse(before.contains("A.post"));
        assertFalse(before.contains("B.post"));

        MvcResult finalResult = mvc.perform(asyncDispatch(first))
            .andExpect(status().isOk())
            .andExpect(content().string("ASYNC"))
            .andReturn();

        List<String> after = events(finalResult);
        assertTrue(after.contains("A.post"));
        assertTrue(after.contains("B.post"));
        assertTrue(after.contains("A.after"));
        assertTrue(after.contains("B.after"));
    }
}
```

Run:

```bash
./mvnw test
```

On PowerShell:

```powershell
.\mvnw.cmd test
```

These tests are **sample source code**, not a claim that they were run in a specific repository. If a project enables Spring Security or has other custom interceptors, filters, or exception resolvers, adjust the setup/expected results accordingly. `MockMvc` simulates servlet requests/MVC async, not full network/container error-page behavior.

### Why Place the Trace on HttpServletRequest?

If a singleton `List<String>` were used to record events from multiple requests, concurrent requests would interleave. A request attribute scopes the trace to the request and allows MockMvc to read it after dispatch. In production, use a metrics/tracing framework with correlation IDs and proper cleanup; avoid exposing an event list that users might inadvertently access.

### What Does the Failing Controller Assertion Prove?

It confirms:

- The handler ran and threw an exception.
- `@RestControllerAdvice` resolved it to HTTP 409.
- Neither A nor B's `postHandle` was called.
- Both A and B's `afterCompletion` still ran because both `preHandle` calls returned true.

If `TraceAdvice` were removed, the exception might exit via another error resolver/container path, without making `postHandle` reappear.

## 11. Choosing Where to Place Tracing, Cleanup, and Response Information

### 11.1. Metrics/Latency

An interceptor can measure duration between `preHandle` and `afterCompletion` using `System.nanoTime()`. Use a namespaced request attribute:

```java
@Override
public boolean preHandle(HttpServletRequest request,
        HttpServletResponse response, Object handler) {
    request.setAttribute("metrics.startedNanos", System.nanoTime());
    return true;
}

@Override
public void afterCompletion(HttpServletRequest request,
        HttpServletResponse response, Object handler, Exception ex) {
    Long began = (Long) request.getAttribute("metrics.startedNanos");
    if (began != null) {
        long elapsed = System.nanoTime() - began;
        // Send elapsed to the appropriate metric registry.
    }
}
```

These are **two method excerpts** inside an interceptor. With async, `afterCompletion` runs on the final dispatch and the request attribute usually persists, though on timeouts/network errors completion may not occur as expected; use dedicated async callbacks. If multiple interceptors write attribute names, use namespaced keys or dedicated objects.

### 11.2. ThreadLocal and MDC

An interceptor sometimes calls `MDC.put("requestId", id)` in `preHandle` and `MDC.remove` in `afterCompletion`. This has pitfalls when:

- `preHandle` returns false → the interceptor's own completion does not run.
- `preHandle` throws an exception before returning true → its own completion is not guaranteed.
- Async starts → `afterCompletion` does not run on the initial dispatch; thread-bound state must be cleaned in `afterConcurrentHandlingStarted`.
- The async worker thread may differ from the initial thread. Do not assume MDC propagates across all executors automatically.
- A Filter may also own MDC; an interceptor should only restore the previous value it replaced, rather than unconditionally clearing another layer's context.

Safe design: do not open a scope until cleanup is accounted for; once opened, close it across every false/throw branch and async callback. For distributed tracing, prefer observability frameworks with standard propagation over overly complex custom `ThreadLocal` code.

### 11.3. Response Headers

If you just need to add a header in a `@ResponseBody` handler, set it in the controller/`ResponseEntity` or hooks before the response commits. `postHandle` runs after `HandlerAdapter`, so modifying headers there is not guaranteed. Spring documentation emphasizes using `ResponseBodyAdvice` for modifying REST bodies at the right stage.

When applying global security headers like HSTS/CSP, a Filter or Spring Security header configuration has a more appropriate scope than an interceptor matching only MVC handlers. If setting a header before the handler, it can be done in `preHandle`, provided error branches and non-MVC requests are still covered by policy; interceptors do not replace filters.

## 12. Exceptions at Different Points in Time

### Handler Throws Before Returning a Response

`preHandle` returned true → handler throws → `postHandle` does not run; MVC `HandlerExceptionResolver` attempts to resolve; `afterCompletion` typically runs for active interceptors. If the exception is handled by a resolver, completion's `ex` may be null. Use `response.getStatus()` to observe the final status rather than relying solely on the exception argument.

### postHandle Itself Throws an Exception

An interceptor can throw inside `postHandle`. MVC may enter exception handling, and completion is still triggered for interceptors that passed `preHandle=true`. However, a JSON response may already be committed; exception handlers may not be able to change the body/status. Avoid risky side effects in `postHandle`.

### View Rendering Fails

With MVC templates, `postHandle` may have already run before rendering; if view rendering fails afterward, `afterCompletion` may be invoked during cleanup/exception flow. Do not claim `postHandle` only runs when the entire HTML response succeeds: it runs after the handler, before rendering.

### preHandle false Is Not an Exception

If an interceptor returns false without throwing an exception, that is an intentional short-circuit. It does not trigger `@ExceptionHandler` merely because the HTTP status was set to 403. Do not equate `setStatus(403)` with `sendError(403)`: the latter can trigger container error handling when the response is uncommitted.

### Filter Exception Before DispatcherServlet

If a Filter throws an exception before calling `chain.doFilter`, MVC interceptors have not run; there is no `preHandle`/`postHandle`/`afterCompletion` for the original request. The container or another filter determines the response. `@RestControllerAdvice` does not automatically handle initial exceptions outside the `DispatcherServlet` lifecycle either.

## 13. Configuration and Technical Pitfalls

1. **Believing `postHandle` can always modify JSON:** a REST handler may already have written the body before the callback.
2. **Assuming `postHandle` always receives a `ModelAndView`:** for REST it is usually null.
3. **Thinking an interceptor returning false still receives its own `afterCompletion`:** incorrect.
4. **Failing to build a response when returning false:** leads to ambiguous status/body.
5. **Cleaning `ThreadLocal` only in `afterCompletion`:** misses false/throw branches and async start.
6. **Treating `ex != null` as the sole measure of failure:** resolved exceptions can yield a null `ex` while status is 4xx/5xx.
7. **Forgetting reverse order:** `post`/`after` execute in B → A order.
8. **Calling the controller manually after B returns false:** breaks short-circuiting.
9. **Using an interceptor as primary security:** fails to cover Filter/Servlet/gateway boundaries; use Spring Security.
10. **Attaching interceptors to `/**` without checking resource/error handlers:** behavior can become confusing.
11. **Equating one HTTP request with one MVC dispatch:** async can trigger a second dispatch.
12. **Assuming async requests run `post`/`after` on the first dispatch:** the right callback is `afterConcurrentHandlingStarted`.
13. **Neglecting async timeouts:** there may be no completion dispatch; dedicated async callbacks are required.
14. **Storing traces in a singleton field:** concurrent requests mix data.
15. **Writing the response both in `preHandle` false and in the controller:** the controller does not run, yet miswired chain/hook logic can double-write.
16. **Skipping error branch tests:** happy-path tests do not prove cleanup.
17. **Using `@ControllerAdvice` to catch all filter exceptions:** advice is scoped to MVC.
18. **Mistaking a servlet filter HTTP status for an exception handler:** a 403 response may involve no Java exception.
19. **Logging rejected values/sensitive headers in interceptors:** risks exposing PII/tokens.
20. **Ignoring context path in manual URI checks:** use `addPathPatterns` instead of ad-hoc URI string checks whenever possible.
21. **Ignoring `response.isCommitted()`:** setting headers/status in `afterCompletion` is usually too late.
22. **Treating `HandlerInterceptor` as the only request lifecycle hook:** filters and Servlet async lifecycles need separate mechanisms.
23. **Assuming every handler is always a `HandlerMethod`:** resource handlers can match too; use `instanceof HandlerMethod` when inspecting annotations.
24. **Using `ThreadLocal` cross-thread for async metrics:** pass request attributes or proper context instead.

## 14. Debugging When a Callback Does Not Run as Expected

When a breakpoint in `postHandle`/`afterCompletion` is not hit:

1. **Did the request enter `DispatcherServlet`?** Check gateway, Servlet Filters, Spring Security, and request logs.
2. **Did `HandlerMapping` find the expected handler?** It may be a 404 or static resource handled elsewhere.
3. **Does the interceptor pattern match?** Inspect `addPathPatterns`/`excludePathPatterns`, context path, and matching strategy.
4. **Did an earlier interceptor return false?** Subsequent interceptors are not called.
5. **Did this interceptor itself return false?** Do not expect its own `afterCompletion`.
6. **Did `preHandle` throw an exception?** The interceptor's own cleanup must be on the error path.
7. **Did the controller throw an exception?** Do not expect `postHandle` after a handler throws.
8. **Did MVC async start?** Expect `afterConcurrentHandlingStarted` on the first dispatch, and `post`/`after` on the final dispatch if any.
9. **Is the response `@ResponseBody` or a view?** A null `mav` and committed response alter what can be modified.
10. **Was the exception already handled by advice?** `ex` may be null even with HTTP status 409/500.
11. **Has view rendering completed?** `postHandle` runs before rendering; `afterCompletion` runs after processing.
12. **Is there another filter/container error handler?** Not every error enters the MVC interceptor chain.
13. **Is there a custom `HandlerAdapter`/`HandlerMapping`?** Some apps use different chains.
14. **Are virtual threads/async wrappers involved?** Do not assume callback threads are identical; manage state safely.
15. **Is it a `MockMvc` test or real HTTP?** MockMvc verifies the MVC lifecycle, while container async error dispatches/connection resets need real integration tests.

## 15. Self-Check Questions

**Question 1.** A is registered before B; on a synchronous success, what is the call order?

**Answer:** `A.pre`, `B.pre`, handler, `B.post`, `A.post`, `B.after`, `A.after`.

**Question 2.** `A.pre` returns true, `B.pre` returns false; which callbacks continue?

**Answer:** Spring skips the handler and all `postHandle` calls; it invokes `A.after` and does not invoke `B.after`. B must produce a valid response and clean up its own resources.

**Question 3.** What if `A.pre` returns false immediately?

**Answer:** Neither B nor the handler runs; `A.after` does not run because A never returned true.

**Question 4.** The controller throws an exception and `@RestControllerAdvice` handles it?

**Answer:** `postHandle` does not run along the throwing handler path; `afterCompletion` of interceptors that returned true still normally runs. `ex` may be null since the exception was resolved.

**Question 5.** Why is `postHandle` unsuitable for modifying a JSON body?

**Answer:** `@ResponseBody`/`ResponseEntity` has usually already been serialized/written by `HandlerAdapter` before `postHandle`, and the response may be committed. Use `ResponseBodyAdvice` or controller response contracts.

**Question 6.** If a controller returns `Callable`, which callback replaces `post`/`after` on the first dispatch?

**Answer:** `AsyncHandlerInterceptor.afterConcurrentHandlingStarted`.

**Question 7.** What can happen after async processing completes successfully?

**Answer:** The container initiates an ASYNC dispatch, and MVC invokes `preHandle`, `postHandle`, and `afterCompletion` again during the result-handling lifecycle. Timeouts/network errors can prevent a normal final dispatch.

**Question 8.** Does `afterCompletion(ex == null)` guarantee the response is 200?

**Answer:** No. It could be 403 from another short-circuit or an exception already resolved to 409; check response status and context.

**Question 9.** Does a Filter rejecting before `DispatcherServlet` trigger `preHandle`?

**Answer:** No. The request never reaches the MVC `HandlerExecutionChain`.

**Question 10.** Where should a `ThreadLocal` set in `preHandle` be cleaned up?

**Answer:** Across every branch (false/throw, normal completion, async start), restoring any previous value as needed; relying solely on `afterCompletion` is incomplete.

## 16. Design Checklist

- [ ] Interceptor matches only appropriate routes and has a clear purpose.
- [ ] `preHandle=false` sets an intentional status/body/redirect.
- [ ] Every interceptor owning resources cleans up properly on false/throw branches too.
- [ ] `ModelAndView` is checked for null before adding attributes.
- [ ] No attempts to modify JSON body/headers in `postHandle` after commit.
- [ ] `ex==null` is never treated as absolute request success.
- [ ] Interceptors are not used as the primary security boundary.
- [ ] Registration order and reverse `post`/`after` ordering have been verified.
- [ ] Normal requests, blocked requests, controller exceptions, and async are all tested.
- [ ] For async, `afterConcurrentHandlingStarted` and timeout cleanup plans are in place.
- [ ] Per-request state never uses a shared mutable singleton.
- [ ] Tracing/logging never exposes tokens, cookies, or PII.
- [ ] Aware that Servlet Filters and error dispatches sit outside the full interceptor lifecycle.
- [ ] Behavior verified on the actual Spring MVC version in use.

## 17. References

- Spring Framework 6.2 — Interception: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html
- Spring Framework 6.2 — MVC Interceptors config: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html
- Spring Framework 6.2 — HandlerInterceptor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/HandlerInterceptor.html
- Spring Framework 6.2 — AsyncHandlerInterceptor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/AsyncHandlerInterceptor.html
- Spring Framework 6.2 — Asynchronous Requests: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
- Spring Framework 6.2 — ResponseBodyAdvice: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseBodyAdvice.html
- Spring Framework — @ControllerAdvice and error responses: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html
- Jakarta Servlet Specification — request and async lifecycle: https://jakarta.ee/specifications/servlet/
