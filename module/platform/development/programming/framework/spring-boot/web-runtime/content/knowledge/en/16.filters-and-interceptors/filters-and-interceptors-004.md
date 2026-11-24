# Interceptors Before Handler, After Handler, and After Request Completion

In Spring MVC, an HTTP request can pass through **Servlet Filters** and multiple **HandlerInterceptors** before the controller method is invoked. An interceptor also gets opportunities to run after the controller executes or once the request has completed. These callbacks are useful for recording timestamps, adding information to view models, instrumenting requests, preparing and cleaning up request-lifecycle data, or diagnosing execution flow.

The three key callbacks of `org.springframework.web.servlet.HandlerInterceptor`:

- **`preHandle(...)`:** before the handler; return `true` to continue or `false` to stop.
- **`postHandle(...)`:** after the handler executes successfully, before `DispatcherServlet` renders the view.
- **`afterCompletion(...)`:** when request processing finishes, used for cleanup and recording results; applies only to interceptors whose `preHandle` returned `true` in that dispatch pass.

The most common mistakes are not syntactic, but involve **callback ordering with multiple interceptors**, **behavior when preHandle returns false**, **handled exceptions**, and **async requests**. In particular, with `@ResponseBody`/`ResponseEntity`, the response may already be written/committed inside `HandlerAdapter` before `postHandle`, making `postHandle` an unreliable place to add headers or alter JSON.

This lesson belongs to **Filters and Interceptors**, using **Spring Boot 3.3.x / Spring Framework 6.1 / Spring MVC Servlet / Java 21**. Spring WebFlux has `WebFilter` and its own reactive handling; do not apply Servlet MVC's `HandlerInterceptor` directly to WebFlux.

## 1. Where Does HandlerInterceptor Sit in the Request Pipeline?

Diagram for a synchronous HTTP request where a controller is matched:

~~~text
HTTP client
    |
    v
Embedded Tomcat / Servlet container
    |
    v
Servlet Filter chain (Servlet API)
    |
    v
DispatcherServlet
    |
    +-- HandlerMapping selects handler + HandlerExecutionChain
    |        |
    |        +-- Interceptor A.preHandle()
    |        +-- Interceptor B.preHandle()
    |        +-- Interceptor C.preHandle()
    |        |
    |        v
    |     HandlerAdapter -> @Controller/@RestController
    |        |
    |        +-- Handler returns result
    |        |
    |        +-- C.postHandle()
    |        +-- B.postHandle()
    |        +-- A.postHandle()
    |        |
    |        v
    |     View rendering / appropriate response handling
    |        |
    |        +-- C.afterCompletion()
    |        +-- B.afterCompletion()
    |        +-- A.afterCompletion()
    |
    v
Servlet Filter chain completes
    |
    v
HTTP response
~~~

The diagram shows the conceptual callback order when **all three `preHandle` methods return `true`**, the handler succeeds, and synchronous request processing is used. In practice, exceptions, async dispatches, CORS preflight, static resources, or custom `HandlerMapping` implementations may occur; do not assume every request goes through the full chain.

### 1.1. Distinguishing the Three Infrastructure Components

- **`HandlerMapping`** decides which handler matches the URL/HTTP method/conditions and prepares the interceptor chain.
- **`HandlerAdapter`** executes the matching handler, resolves arguments, and handles the return value.
- **`HandlerExecutionChain`** holds the handler along with the applicable list of interceptors and coordinates their callbacks.

An interceptor runs after the framework **has already selected a handler**. Therefore, it is not an absolute outer wrapper over every HTTP request like a properly mapped Servlet Filter.

## 2. The HandlerInterceptor Contract in Spring Framework 6.1

Abbreviated API shape:

~~~java
package org.springframework.web.servlet;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.ModelAndView;

public interface HandlerInterceptor {

    default boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws Exception {
        return true;
    }

    default void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            ModelAndView modelAndView) throws Exception {
    }

    default void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) throws Exception {
    }
}
~~~

This is an **illustrative method-signature listing**; the real interface already exists in Spring Framework with nullability annotations and Javadoc. Do not create a duplicate interface in the same package in your project.

| Callback | Timing | Return | Typical Tasks |
| --- | --- | --- | --- |
| `preHandle` | After handler is selected, before invocation | `boolean` | Start timer, attach request attributes, decide whether to proceed |
| `postHandle` | After handler succeeds, before view render | `void` | Add data to `ModelAndView` for MVC views |
| `afterCompletion` | After MVC processing finishes in sync/completed dispatch | `void` | Clean up resources, stop timer, logging/metrics |
| `afterConcurrentHandlingStarted` (on `AsyncHandlerInterceptor`) | When async starts and initial thread is about to exit MVC dispatch | `void` | Clean up thread-bound state from the initial async pass |

There is no callback named `aroundHandle` in `HandlerInterceptor`. To wrap the entire Servlet chain, see `Filter`; to wrap an arbitrary Java method, see Spring AOP, which has a different scope and semantics.

### 2.1. What Is the handler Parameter?

`handler` may be a `HandlerMethod` when the request maps to an annotated controller method, though not every mapping type provides a `HandlerMethod`. You can check:

~~~java
if (handler instanceof HandlerMethod method) {
    String methodName = method.getMethod().getName();
    Class<?> controllerType = method.getBeanType();
}
~~~

This fragment is used inside `preHandle` or a corresponding callback; it requires importing `org.springframework.web.method.HandlerMethod`. Never cast directly to `HandlerMethod` without checking, as functional, static-resource, or custom handlers can differ.

## 3. preHandle: Continue or Stop the Chain?

Signature:

~~~java
boolean preHandle(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler
) throws Exception;
~~~

- Return **`true`**: Spring proceeds to the next interceptor; if at the end of the chain, it invokes the handler.
- Return **`false`**: Spring **skips all remaining interceptors and skips invoking the handler**. The framework assumes the interceptor has already handled the response or determined how to terminate appropriately.
- Throw an exception: MVC's error-handling path is triggered; this is not equivalent to returning `false`.

Example fragment used inside an interceptor:

~~~java
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) {

    if (request.getRequestURI().endsWith("/demo-stop")) {
        response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
        return false;
    }
    return true;
}
~~~

This is only an **illustration of short-circuiting**, not a way to enforce authorization: a URI suffix check does not fully account for routing, context path, proxy rewrites, or security policy.

### 3.1. Returning false Does Not Automatically Emit an Error Status

If `preHandle` returns `false` without setting a status or writing a response, the client may receive an unexpected response, even an empty 200. To reject by policy, set the response/status/body explicitly **before returning false**, while ensuring no other component writes to the same response.

If requests require a consistent JSON error payload, consider handling them via `ResponseStatusException`/exception mapping in controllers, `@ControllerAdvice` for appropriate exceptions, or a dedicated security/filter layer. Avoid duplicating JSON error body construction across every interceptor.

### 3.2. Stopping Conditions Do Not Replace Access Control

Spring Framework warns that interceptors are not an ideal security layer because their path matching can diverge from annotated controller matching. Authentication and authorization must be configured in the **Spring Security filter chain** or an appropriate equivalent, never relying on an interceptor inspecting URL strings.

## 4. postHandle: Runs After a Successful Handler

Signature:

~~~java
void postHandle(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler,
    ModelAndView modelAndView
) throws Exception;
~~~

It is called after `HandlerAdapter` executes the handler successfully and before `DispatcherServlet` renders the view, during **normal synchronous execution**. If the controller throws an exception handled by a `HandlerExceptionResolver`, `postHandle` on the original handler chain is normally **not invoked**.

### 4.1. Adding Shared Data to MVC Views

Example callback snippet:

~~~java
@Override
public void postHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        ModelAndView modelAndView) {

    if (modelAndView != null) {
        modelAndView.addObject("supportEmail", "support@example.test");
    }
}
~~~

If the controller returns a logical view name with a model and view rendering happens after the callback, the `supportEmail` attribute can be used by the view. This is an appropriate use case for `postHandle`. Conversely, `modelAndView` may be `null` for REST handlers that write the body directly, so always null-check before using it.

### 4.2. With @RestController, It Is Too Late to Modify the Body or Headers

Spring MVC can serialize `@ResponseBody`/`ResponseEntity` into the response **inside `HandlerAdapter`**, i.e., before `postHandle`. Therefore:

~~~java
@Override
public void postHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        ModelAndView mav) {
    response.setHeader("X-Demo", "late"); // Unreliable
}
~~~

this is an **anti-pattern**: the header may never be sent if the response is already committed. To add headers before a REST body is written, consider:

- `preHandle` for metadata already known before the controller runs.
- `ResponseEntity` in the controller when the header depends on business results.
- `ResponseBodyAdvice` when you need to intercept the body/response handled by a message converter.
- `Filter`/response wrappers when logic must genuinely wrap the Servlet response and commit lifecycle is well understood.

Never assume `postHandle` succeeded in writing a header simply because the code threw no exception.

## 5. afterCompletion: Cleanup When Request Processing Completes

Signature:

~~~java
void afterCompletion(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler,
    Exception ex
) throws Exception;
~~~

Meaning:

- Runs after MVC processing finishes, including after view rendering in a normal synchronous flow.
- Used to clean up request-related resources, finish measurements, and observe the final status.
- With multiple interceptors, callbacks run in **reverse order of `preHandle`**.
- **Only called for interceptors whose `preHandle` completed and returned `true`.**
- `ex` may be `null`; it **does not include exceptions already handled by a `HandlerExceptionResolver`**. Do not use `ex == null` as proof of "no error" for every request.

Example timing logic:

~~~java
private static final String START_NS = "com.example.startNano";

@Override
public boolean preHandle(
        HttpServletRequest req,
        HttpServletResponse res,
        Object handler) {
    req.setAttribute(START_NS, System.nanoTime());
    return true;
}

@Override
public void afterCompletion(
        HttpServletRequest req,
        HttpServletResponse res,
        Object handler,
        Exception ex) {
    Object value = req.getAttribute(START_NS);
    if (value instanceof Long start) {
        long elapsedNs = System.nanoTime() - start;
        // Record metrics with bounded-cardinality tags.
    }
    req.removeAttribute(START_NS);
}
~~~

This is an interceptor fragment, not a standalone class. `System.nanoTime()` measures **elapsed duration**, not a timestamp for database storage. For elapsed time, subtracting two monotonic values is appropriate. For production apps, Micrometer Observation/Tracing may be preferable to custom metrics.

### 5.1. afterCompletion Is Not Servlet Filter finally

`afterCompletion` does not necessarily execute along every path before `DispatcherServlet`: a request can be blocked by a Filter before MVC, fail to match a handler, not invoke the interceptor, or have incomplete async work. When cleaning up resources created at the Servlet Filter level, use `try/finally` in the Filter aligned with async dispatches rather than expecting `afterCompletion` to wrap the entire HTTP lifecycle.

## 6. Multiple Interceptors: Inbound Order and Outbound Order

Suppose three interceptors are registered with orders:

~~~text
A (order 0)
B (order 1)
C (order 2)
~~~

All `preHandle` methods return true and the controller returns successfully. Callback sequence:

~~~text
A.preHandle
B.preHandle
C.preHandle
Controller
C.postHandle
B.postHandle
A.postHandle
View/response completion
C.afterCompletion
B.afterCompletion
A.afterCompletion
~~~

This follows the **enter in order, exit in reverse order** principle, similar to nested middleware layers. Do not read `order=0` as "runs first in every callback"; it only enters first in pre, whereas outermost post/after callbacks run last.

### 6.1. InterceptorRegistry and Ordering

Common configuration:

~~~java
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new FirstInterceptor())
            .addPathPatterns("/api/**")
            .order(0);

        registry.addInterceptor(new SecondInterceptor())
            .addPathPatterns("/api/**")
            .order(1);
    }
}
~~~

This is an **illustrative skeleton**; `FirstInterceptor` and `SecondInterceptor` must be defined. Use `.order(...)` to express ordering explicitly rather than relying on incidental code order. Note that ordering is also affected by interceptors automatically registered by the framework or custom `HandlerMapping` beans.

### 6.2. Early Stop at B

Suppose `A.preHandle` returns true and `B.preHandle` returns false:

~~~text
A.preHandle -> true
B.preHandle -> false
           -> controller DOES NOT run
           -> C.preHandle DOES NOT run
           -> no postHandle for A/B/C
A.afterCompletion
~~~

**B.afterCompletion does not run** because B returned false; **C.afterCompletion does not run** because C never entered the chain. This is a critical detail to avoid placing B's cleanup logic in a callback B may never receive.

If B allocated resources **before deciding to return false**, B must clean them up immediately before returning false or redesign around an abstraction with appropriate cleanup guarantees. Likewise, if B's `preHandle` throws an exception, B never completed returning true, so do not expect B.afterCompletion to run.

### 6.3. When an Exception Occurs

If the controller throws an exception:

~~~text
A.preHandle -> true
B.preHandle -> true
Controller -> throws Exception
HandlerExceptionResolver / @ControllerAdvice handles it
B.afterCompletion
A.afterCompletion
~~~

`postHandle` is normally skipped because the handler did not complete successfully. `afterCompletion` still runs for interceptors where pre=true if MVC finishes handling accordingly. In `afterCompletion`, `ex` can be `null` once a resolver has handled the exception. If the exception goes unhandled, the outcome can differ and the exception propagates further.

## 7. Standalone Java Example to Remember Callback Order

This is a **standalone Java 17+ program** simulating the ordering principle. It is **not the implementation of Spring's HandlerExecutionChain**; it demonstrates entry/exit logic and mid-chain termination.

**ChainOrderDemo.java**

~~~java
import java.util.ArrayList;
import java.util.List;

public class ChainOrderDemo {

    public static void main(String[] args) {
        run(false);
        System.out.println("---");
        run(true);
    }

    private static void run(boolean stopAtB) {
        List<String> entered = new ArrayList<>();

        for (String name : List.of("A", "B", "C")) {
            System.out.println(name + ".pre");

            if (stopAtB && name.equals("B")) {
                // B did not return true, so it is not added to entered.
                after(entered);
                return;
            }
            entered.add(name);
        }

        System.out.println("handler");

        for (int i = entered.size() - 1; i >= 0; i--) {
            System.out.println(entered.get(i) + ".post");
        }

        after(entered);
    }

    private static void after(List<String> entered) {
        for (int i = entered.size() - 1; i >= 0; i--) {
            System.out.println(entered.get(i) + ".after");
        }
    }
}
~~~

Run:

~~~bash
javac ChainOrderDemo.java
java ChainOrderDemo
~~~

Exact stdout:

~~~text
A.pre
B.pre
C.pre
handler
C.post
B.post
A.post
C.after
B.after
A.after
---
A.pre
B.pre
A.after
~~~

Key takeaway: `B.pre` in the early-stop case **does not imply `B.after`**. Neither the controller nor post callbacks run on the stopped branch. These properties are verified with a real Spring Boot app below.

## 8. Configuring Interceptors in Spring Boot via WebMvcConfigurer

For annotated Spring MVC controllers, the standard configuration approach is implementing `WebMvcConfigurer#addInterceptors(InterceptorRegistry)`.

~~~java
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new TraceInterceptor())
            .addPathPatterns("/api/**")
            .excludePathPatterns("/api/public/**")
            .order(0);
    }
}
~~~

This is a skeleton: `TraceInterceptor` is not yet defined. The patterns share MVC infrastructure path matching (especially in Spring Framework 6), though you should not assume the exact same pattern covers Servlet Filter paths or Security matchers identically.

### 8.1. addPathPatterns and excludePathPatterns

- `addPathPatterns("/api/**")`: applies the interceptor only to matching mapping paths.
- `excludePathPatterns("/api/public/**")`: excludes matching routes, even when they match the include pattern.
- When no include patterns are configured, the interceptor may apply broadly across handlers belonging to that HandlerMapping.

Do not assume an interceptor applies only to `@RestController`: it can apply to static resources, view controllers, or other handler types depending on registration. Test the exact URLs and selected handler types.

### 8.2. An Interceptor Lives Across Many Requests

An interceptor instance is normally reused across many requests. **Never store per-request mutable currentUser, currentRequestId, or startTime in an interceptor instance field**:

~~~java
public class BadTimingInterceptor implements HandlerInterceptor {
    private long startedNanos; // Wrong under concurrent requests
}
~~~

Two concurrent requests will overwrite `startedNanos`. Use local variables, `HttpServletRequest.setAttribute(...)`, Micrometer Observation, or a properly lifecycle-scoped context.

### 8.3. @Component and Manual Registration

If an interceptor is a Spring bean needing injected services/config, you can annotate it with `@Component` and inject the bean into `WebMvcConfigurer` to register it once. Avoid letting the framework auto-register the same interceptor while also calling `registry.addInterceptor(...)` indiscriminately without knowing which `HandlerMapping` beans hold which instances.

In the runnable example below, `new LifecycleInterceptor(...)` is instantiated inside the config so the demo's order and state are transparent; it has no dependencies to inject.

## 9. Runnable Project: Recording Spring MVC pre, post, and after

Complete example using **Spring Boot 3.3.13 + Java 21 + Gradle 8.5**, with three interceptors named `outer`, `inner`, and `gate`. Trace data is stored in an **HttpServletRequest attribute** so requests do not share mutable trace state.

Demo routes:

| URL | Result | Purpose |
| --- | --- | --- |
| `GET /api/ok` | 200 JSON | Order pre → handler → post → after |
| `GET /api/blocked` | 403 empty body | `gate.preHandle` returns false, chain stops early |
| `GET /api/boom` | 500 JSON from advice | Exception handled, post skipped |
| `GET /api/async` | 200 JSON via `Callable` | Observe `afterConcurrentHandlingStarted` and async redispatch |

**Security note:** `gate` merely simulates chain termination on a test path. Never use this demo interceptor for real authentication or authorization.

Project structure:

~~~text
interceptor-lifecycle-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/interceptors/
    │   ├── InterceptorDemoApplication.java
    │   ├── RequestTrace.java
    │   ├── LifecycleInterceptor.java
    │   ├── WebConfig.java
    │   ├── DemoController.java
    │   └── DemoExceptionAdvice.java
    └── test/java/com/example/interceptors/
        └── InterceptorLifecycleTest.java
~~~

### 9.1. Gradle

**settings.gradle**

~~~groovy
rootProject.name = 'interceptor-lifecycle-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 9.2. Main Application

**src/main/java/com/example/interceptors/InterceptorDemoApplication.java**

~~~java
package com.example.interceptors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InterceptorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(InterceptorDemoApplication.class, args);
    }
}
~~~

### 9.3. RequestTrace: Recording Events on the Exact HTTP Request

**src/main/java/com/example/interceptors/RequestTrace.java**

~~~java
package com.example.interceptors;

import java.util.ArrayList;
import java.util.List;

import jakarta.servlet.http.HttpServletRequest;

public final class RequestTrace {

    private static final String KEY =
        RequestTrace.class.getName() + ".events";

    private RequestTrace() {
    }

    @SuppressWarnings("unchecked")
    private static List<String> events(HttpServletRequest request) {
        Object existing = request.getAttribute(KEY);

        if (existing instanceof List<?>) {
            return (List<String>) existing;
        }

        List<String> created = new ArrayList<>();
        request.setAttribute(KEY, created);
        return created;
    }

    public static void record(
            HttpServletRequest request, String event) {
        events(request).add(event);
    }

    public static List<String> snapshot(
            HttpServletRequest request) {
        return List.copyOf(events(request));
    }
}
~~~

This is a demo utility rather than putting events into an application-wide static `List`. Each HTTP request gets its own list; tests can read the list after the MVC dispatch to verify order.

The example **does not record events from multiple async threads concurrently**. In production, if multiple concurrent branches mutate a request attribute, `ArrayList` is not thread-safe by default; design for thread safety or use an appropriate tracing library.

### 9.4. LifecycleInterceptor: Three Callbacks and Async Callback

**src/main/java/com/example/interceptors/LifecycleInterceptor.java**

~~~java
package com.example.interceptors;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.servlet.AsyncHandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;

public final class LifecycleInterceptor
        implements AsyncHandlerInterceptor {

    private final String name;
    private final boolean blocksDemoRoute;

    public LifecycleInterceptor(
            String name, boolean blocksDemoRoute) {
        this.name = name;
        this.blocksDemoRoute = blocksDemoRoute;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        RequestTrace.record(request, name + ".pre");

        if (blocksDemoRoute
                && request.getRequestURI().endsWith("/api/blocked")) {
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            // Gate has not returned true: gate's afterCompletion will not run.
            return false;
        }

        return true;
    }

    @Override
    public void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            ModelAndView modelAndView) {

        RequestTrace.record(request, name + ".post");
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {

        RequestTrace.record(request, name + ".after");
    }

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        RequestTrace.record(request, name + ".async-started");
    }
}
~~~

`blocksDemoRoute` is strictly for testing the false branch. In real products, never rely on `endsWith(...)` to protect routes or enforce permissions.

### 9.5. Registering the Three Interceptors in Order

**src/main/java/com/example/interceptors/WebConfig.java**

~~~java
package com.example.interceptors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {

        registry.addInterceptor(
                new LifecycleInterceptor("outer", false))
            .addPathPatterns("/api/**")
            .order(0);

        registry.addInterceptor(
                new LifecycleInterceptor("inner", false))
            .addPathPatterns("/api/**")
            .order(1);

        registry.addInterceptor(
                new LifecycleInterceptor("gate", true))
            .addPathPatterns("/api/**")
            .order(2);
    }
}
~~~

For `/api/ok`:

~~~text
pre:   outer -> inner -> gate
post:  gate  -> inner -> outer
after: gate  -> inner -> outer
~~~

For `/api/blocked`, gate returns false and does not record `gate.after`, whereas outer and inner are cleaned up in reverse order because they returned true.

### 9.6. Controller Simulating Success, Stop, Error, and Async

**src/main/java/com/example/interceptors/DemoController.java**

~~~java
package com.example.interceptors;

import java.util.concurrent.Callable;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    public record Message(String message) {
    }

    @GetMapping("/ok")
    public Message ok(HttpServletRequest request) {
        RequestTrace.record(request, "handler");
        return new Message("ok");
    }

    @GetMapping("/blocked")
    public Message blocked(HttpServletRequest request) {
        RequestTrace.record(request, "handler.blocked");
        return new Message("must-not-run");
    }

    @GetMapping("/boom")
    public Message boom(HttpServletRequest request) {
        RequestTrace.record(request, "handler.boom");
        throw new IllegalStateException("demonstration failure");
    }

    @GetMapping("/async")
    public Callable<Message> async(HttpServletRequest request) {
        RequestTrace.record(request, "handler.async");

        // Do not read HttpServletRequest inside the Callable;
        // return an immutable value ready for serialization on redispatch.
        return () -> new Message("async-ok");
    }
}
~~~

The `/api/blocked` route has a controller handler to prove it **does not** run when `gate.preHandle` returns false. No database is needed and no mutable state is shared across requests.

### 9.7. Advice to Handle Errors with a Deterministic Body

**src/main/java/com/example/interceptors/DemoExceptionAdvice.java**

~~~java
package com.example.interceptors;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DemoExceptionAdvice {

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<Map<String, String>> handle(
            IllegalStateException exception) {

        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(Map.of("error", "demo-failure"));
    }
}
~~~

An `@ExceptionHandler` can translate `IllegalStateException` into HTTP 500. In the test, `postHandle` of the original handler interceptor chain is not invoked after the exception, while `afterCompletion` still runs for those where pre=true. `ex` in afterCompletion will not necessarily contain the exception already handled by the resolver.

### 9.8. Running the Application

With JDK 21 and an appropriate Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

If creating the project fresh without a Gradle wrapper yet, using an installed Gradle supporting Java 21:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Test:

~~~bash
curl -i http://localhost:8080/api/ok
curl -i http://localhost:8080/api/blocked
curl -i http://localhost:8080/api/boom
curl -i http://localhost:8080/api/async
~~~

Expected outcomes:

| Request | HTTP status | Meaningful Body |
| --- | --- | --- |
| `/api/ok` | 200 | `{"message":"ok"}` |
| `/api/blocked` | 403 | No body from controller |
| `/api/boom` | 500 | `{"error":"demo-failure"}` |
| `/api/async` | 200 | `{"message":"async-ok"}` |

**Note:** the callback event list stays in a request attribute for the MockMvc test and is not serialized in the client response body. Having `curl` show only the JSON/status is intentional so event traces are not confused with response content.

## 10. Verifying Exact Callback Order with MockMvc

**src/test/java/com/example/interceptors/InterceptorLifecycleTest.java**

~~~java
package com.example.interceptors;

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
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class InterceptorLifecycleTest {

    @Autowired
    MockMvc mvc;

    @Test
    void normalRequestRunsAllCallbacksInExpectedOrder()
            throws Exception {

        MvcResult result = mvc.perform(get("/api/ok"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("ok"))
            .andReturn();

        assertEquals(List.of(
            "outer.pre",
            "inner.pre",
            "gate.pre",
            "handler",
            "gate.post",
            "inner.post",
            "outer.post",
            "gate.after",
            "inner.after",
            "outer.after"
        ), RequestTrace.snapshot(result.getRequest()));
    }

    @Test
    void preHandleFalseStopsHandlerAndSkipsItsOwnCleanup()
            throws Exception {

        MvcResult result = mvc.perform(get("/api/blocked"))
            .andExpect(status().isForbidden())
            .andReturn();

        assertEquals(List.of(
            "outer.pre",
            "inner.pre",
            "gate.pre",
            "inner.after",
            "outer.after"
        ), RequestTrace.snapshot(result.getRequest()));
    }

    @Test
    void handledExceptionSkipsPostButRunsAfterCompletion()
            throws Exception {

        MvcResult result = mvc.perform(get("/api/boom"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.error").value("demo-failure"))
            .andReturn();

        assertEquals(List.of(
            "outer.pre",
            "inner.pre",
            "gate.pre",
            "handler.boom",
            "gate.after",
            "inner.after",
            "outer.after"
        ), RequestTrace.snapshot(result.getRequest()));
    }

    @Test
    void asyncHasSpecialInitialPhaseAndLaterRedispatch()
            throws Exception {

        MvcResult started = mvc.perform(get("/api/async"))
            .andExpect(request().asyncStarted())
            .andReturn();

        List<String> initial =
            RequestTrace.snapshot(started.getRequest());

        assertTrue(initial.contains("handler.async"));
        assertTrue(initial.contains("outer.async-started"));
        assertFalse(initial.contains("outer.post"));

        MvcResult completed = mvc.perform(asyncDispatch(started))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("async-ok"))
            .andReturn();

        List<String> finalEvents =
            RequestTrace.snapshot(completed.getRequest());

        assertTrue(finalEvents.contains("outer.after"));
        assertTrue(finalEvents.contains("inner.after"));
        assertTrue(finalEvents.contains("gate.after"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

Test breakdown:

- **`normalRequest...`** verifies the callback order of the three interceptors.
- **`preHandleFalse...`** verifies the controller does not run, `gate.after` does not run, and only interceptors with pre=true are cleaned up.
- **`handledException...`** verifies the advice handles the error and no post callbacks run for the failed handler.
- **`asyncHasSpecial...`** verifies the initial async phase receives its dedicated callback without `postHandle` when the thread leaves the dispatch; once async redispatch completes, after callbacks execute.

The code snippets have been reviewed against Spring MVC APIs; the test outcomes above represent **expected behavior from the source**. Only claim "Gradle tests ran successfully" if you actually execute the build tool and observe a successful exit code.

`@SpringBootTest` + `@AutoConfigureMockMvc` exercises the MVC request chain typically without listening on a real HTTP socket. To test Servlet container async timeouts, proxies, or dispatch types, add integration tests with a real server.

## 11. Async Requests: AsyncHandlerInterceptor Differs from Synchronous Flow

Spring MVC supports `Callable`, `WebAsyncTask`, `DeferredResult`, and Servlet async dispatches. When a handler starts async processing, DispatcherServlet can exit the initial thread **without invoking `postHandle` and `afterCompletion` at that point** because the result is not yet ready.

With `AsyncHandlerInterceptor`, the framework invokes:

~~~java
void afterConcurrentHandlingStarted(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler
) throws Exception;
~~~

It takes the place of `postHandle`/`afterCompletion` for the **initial dispatch**. Once the async result is produced and the request is redispatched, the callback chain can run again on another thread, including pre/post/after along the appropriate flow.

~~~text
Initial dispatch thread:
  preHandle
  handler returns Callable / DeferredResult
  async processing begins
  afterConcurrentHandlingStarted
  thread leaves DispatcherServlet

Concurrent computation:
  produces async result on worker/event callback

Async redispatch:
  preHandle invoked again
  adapter processes completed async result
  postHandle
  afterCompletion
~~~

**Do not treat the entire async flow as a simple sequence with one `preHandle` and one `afterCompletion`.** Depending on the number of dispatches and framework/container behavior, an interceptor may receive callbacks multiple times within the same HTTP request.

### 11.1. Timeouts or Network Errors

If an async request times out, encounters a network disconnect, or errors after the client has left, the expected redispatch/completion flow of a successful request may not occur. Do not base critical thread-local/resource cleanup solely on the async path's `afterCompletion`.

For real async workloads, examine `WebAsyncManager`, `CallableProcessingInterceptor`, `DeferredResultProcessingInterceptor`, or related async-lifecycle callbacks; timeouts, errors, and cancellations must be handled deliberately. `afterConcurrentHandlingStarted` is the right place to clear thread-bound state that the initial thread should not retain.

### 11.2. Never Hold ThreadLocals Across a Thread Pool

With code such as:

~~~java
private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();
~~~

`CURRENT` data on a Servlet worker thread does not automatically appear on an executor thread. Conversely, if you forget to call `remove()` on a reused worker thread, subsequent requests can see stale data.

Prefer passing immutable snapshots such as correlation IDs, verified authenticated principals, locales, or needed request metadata via framework propagation APIs. Never pass the raw `HttpServletRequest` into a long-running task after the request may have ended.

## 12. How Do HandlerInterceptor and Servlet Filter Differ?

| Criterion | `HandlerInterceptor` | Servlet `Filter` |
| --- | --- | --- |
| Integration level | Spring MVC handler mapping | Servlet filter chain |
| Runs before handler selection? | No; handler is already mapped | Usually can run before `DispatcherServlet` |
| Knows the selected handler? | Yes, `Object handler` parameter | Usually not directly |
| Pre-processing callback | `preHandle` | Code before `chain.doFilter(...)` |
| Post-processing callback | `postHandle`/`afterCompletion` with MVC semantics | Code after `chain.doFilter` and `finally` with dispatch semantics |
| Covers static resources/404 outside MVC? | Depends on `HandlerMapping` and registration | Depends on filter URL patterns and dispatcher types |
| Request/response wrapping | Not its primary purpose | Better suited via `HttpServletRequestWrapper`/`HttpServletResponseWrapper` |
| Authentication/authorization | Not recommended as primary security layer | Spring Security integrates via Servlet filter chain |
| Async handling | `AsyncHandlerInterceptor`, MVC redispatch | Dispatcher types `ASYNC`/`ERROR`, async-aware filter design |

### 12.1. Filters Can Wrap DispatcherServlet

Example fragment:

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    long start = System.nanoTime();
    try {
        chain.doFilter(request, response);
    } finally {
        long elapsed = System.nanoTime() - start;
        // Record metrics/cleanup appropriate for the Servlet dispatch.
    }
}
~~~

In a Filter, `chain.doFilter` continues the chain. Code in `finally` runs when that call returns or throws, yet **never assume it always means the entire Servlet async request has completed**: the thread can leave the dispatch before the async computation finishes. When measuring until async completion, handle the async lifecycle explicitly.

### 12.2. Which Layer Should You Choose?

- **Spring Security**: authentication/authorization/CSRF and security policies.
- **Servlet Filter**: inbound/outbound HTTP concerns needing early coverage, request/response wrapping, request ID at the Servlet boundary.
- **HandlerInterceptor**: handler-aware metadata, MVC-specific timing, view model adjustments, controller-route tracking.
- **ControllerAdvice/ResponseBodyAdvice**: error response schemas, customizing body/headers during REST response serialization.
- **AOP**: cross-cutting concerns across Java services/methods, not a replacement for the HTTP lifecycle.

Avoid having multiple layers handle the same concern without a clear owner. A correlation ID can be established in a Filter, read in controllers/interceptors, and linked with Micrometer Tracing, provided there is a single clear rule for propagation and cleanup.

## 13. Using an Interceptor for Timing and Attaching Request Metadata

An interceptor can capture the start time in `preHandle` and compute elapsed duration in `afterCompletion`:

~~~java
public final class TimingInterceptor implements HandlerInterceptor {

    private static final String START =
        TimingInterceptor.class.getName() + ".started";

    @Override
    public boolean preHandle(
            HttpServletRequest req,
            HttpServletResponse resp,
            Object handler) {
        req.setAttribute(START, System.nanoTime());
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest req,
            HttpServletResponse resp,
            Object handler,
            Exception ex) {
        Object started = req.getAttribute(START);
        try {
            if (started instanceof Long ns) {
                long duration = System.nanoTime() - ns;
                // Record safe metric/trace without sensitive input.
            }
        } finally {
            req.removeAttribute(START);
        }
    }
}
~~~

This example is an illustrative class that compiles in a Spring MVC project with the corresponding imports (omitted to focus on logic). With **async redispatches**, `preHandle` can run again and overwrite the start time, causing duration to cover only the final dispatch. To measure from HTTP request start through **all async work**, use Filter/observation infrastructure or only set the request attribute if absent, and handle timeouts/errors appropriately.

### 13.1. Metric Labels and Cardinality

Avoid using full URL paths containing IDs like `/users/123456`, header values, or userIds as metric labels; label cardinality can grow unboundedly. If you need tags for controller routes, use **route templates** such as `/users/{id}` and bound label values. Spring Boot Actuator/Micrometer provides built-in observations and metrics; a custom timing interceptor is not always necessary.

### 13.2. Logging and MDC

MDC in most logging frameworks is thread-local based. If a Filter/Interceptor puts a correlation ID into MDC, clean it up on the same thread and avoid misunderstanding the async lifecycle. An `MDC.put(...)` call in `preHandle` does not automatically propagate into a `Callable`'s worker thread or an arbitrary executor.

Generally, for standard instrumentation and tracing, use Micrometer Observation and configured logging context propagation rather than duplicating tracing logic across multiple interceptors.

## 14. Exception Handling and afterCompletion.ex

A subtle point in Spring MVC:

~~~java
@GetMapping("/error")
public String error() {
    throw new IllegalArgumentException("invalid");
}
~~~

If an `@ExceptionHandler` catches the exception and produces a response, `afterCompletion(..., ex)` **may receive `null`** because the exception has already been handled by the resolver. The `HandlerInterceptor` Javadoc notes that the `ex` parameter **excludes exceptions already handled by a HandlerExceptionResolver**.

Therefore, never write:

~~~java
if (ex == null) {
    log.info("All good"); // Wrong: request may have returned 4xx/5xx.
}
~~~

Combine HTTP status, exception recording/observation, and your error-handling policy instead. An HTTP 500 returned by advice is still an error outcome even when `ex` in afterCompletion is absent.

### 14.1. Exceptions in preHandle

If an interceptor throws an exception before returning true, it has not yet been marked as having "entered" successfully. Its own cleanup in `afterCompletion` is not guaranteed. Use a local `try/finally` if resources are allocated before code that could throw prior to preHandle finishing.

### 14.2. Exceptions in postHandle

Throwing an exception from `postHandle` also sends the request into exception resolution, while `afterCompletion` for interceptors that returned pre=true can still execute as MVC finishes processing. Keep `postHandle` simple; errors here can interfere with an error response or view the controller already prepared.

## 15. Interceptors and Response Body/View Processing

### 15.1. MVC View Responses

For `@Controller` methods returning a view name, `postHandle` can modify `ModelAndView` before the view engine renders HTML. This is the classic use case for interceptor post-processing.

### 15.2. REST JSON Responses

For `@RestController`:

~~~java
@GetMapping("/hello")
public Map<String, String> hello() {
    return Map.of("message", "hello");
}
~~~

Jackson/message converters can write JSON inside `HandlerAdapter`. To modify JSON objects globally, look at `ResponseBodyAdvice`, API DTOs, or Jackson serialization policies—**do not add or edit JSON in `postHandle`**.

### 15.3. Committed Responses

Once headers/body have been committed, you cannot reliably change the HTTP status or add headers. Interceptor `afterCompletion` should be viewed as an observation/cleanup stage, not a stage for writing a new HTTP response. When an exception occurs after commit, even an error handler cannot retroactively turn a 200 already sent into a 500.

### 15.4. CORS Preflight

An HTTP OPTIONS preflight may be handled by framework/proxy CORS configuration before reaching the controller; do not assume custom interceptors will always run just like GET/POST requests. Configure CORS through Spring MVC CORS support, Spring Security, or your gateway according to your topology—never try to solve CORS with `preHandle` inspecting a few headers.

## 16. Interceptors and Spring Security: Do Not Mix Roles

Security vulnerabilities occur when controller path matchers and interceptor path matchers disagree—especially with encoded URLs, reverse proxy prefixes, request dispatches, and multi-mapping conditions. If you enforce authorization in an interceptor by comparing strings on `request.getRequestURI()`, a request may take another route and still reach a protected controller.

When access control is needed:

- Use **Spring Security SecurityFilterChain**, authorization matchers, and method security appropriately.
- Base policies on genuinely authenticated roles/scopes/ownership, never on unvalidated client-supplied headers.
- Test both allowed and denied endpoints across HTTP methods and path variants.
- Verify `ERROR`/`ASYNC` dispatches, CORS, CSRF, and gateway path rewriting across your architecture.
- Never treat returning false/403 in the demo `preHandle` as a substitute for authentication/authorization.

Interceptors excel at **timing and knowing the handler name**, whereas security enforcement requires earlier, stricter request coverage.

## 17. How Is WebFlux Different?

In native reactive Spring WebFlux:

- `DispatcherHandler` coordinates handlers/reactive results, not `DispatcherServlet`.
- `WebFilter` is the cross-cutting choice at the reactive web chain level.
- `WebFilter.filter(ServerWebExchange, WebFilterChain)` returns `Mono<Void>`.
- Spring MVC's `HandlerInterceptor` requires `jakarta.servlet.http.HttpServletRequest` and does not run natively on Reactor Netty request handling.
- Reactive context data is typically propagated through Reactor Context/appropriate instrumentation, not Servlet ThreadLocals.

Illustrative WebFlux fragment:

~~~java
@Component
public class LogWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return chain.filter(exchange)
            .doFinally(signal ->
                System.out.println("Reactive request finished: " + signal));
    }
}
~~~

This is a **fragment**; it requires importing `WebFilter`, `WebFilterChain`, `ServerWebExchange`, and `Mono`. In real applications, do not log every request directly with `System.out` or write personal data into logs. `doFinally` can receive completion/error/cancel signals; it does not mean the client has finished reading the entire response body over the network.

If a project includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot usually selects Servlet MVC by default; verify your active runtime before choosing a Servlet interceptor or a WebFilter.

## 18. Common Mistakes When Using HandlerInterceptor

### 18.1. Assuming postHandle Always Runs

False when `preHandle` returns false, the handler throws an exception, or an initial async dispatch has not completed. Never place mandatory cleanup solely in postHandle.

### 18.2. Assuming afterCompletion Always Runs If the Interceptor Was Created

False: the callback only runs for interceptors whose `preHandle` returned true in that flow, plus other MVC/async boundaries apply.

### 18.3. Using Instance Fields for Request-Specific State

Interceptors are shared across requests; mutable shared fields cause races/leaks. Use request attributes, immutable contexts, or an observation framework.

### 18.4. Using postHandle to Modify JSON Headers

`@ResponseBody`/`ResponseEntity` may already be committed before postHandle. Place the logic at the right layer or use `ResponseBodyAdvice`.

### 18.5. Returning false Without Setting a Response

Clients may receive an unintended status/body. When short-circuiting intentionally, take ownership of the response before returning false.

### 18.6. Using an Interceptor as a DIY Security Firewall

Not recommended; use Spring Security FilterChain and test real URL matching.

### 18.7. Ignoring Async Dispatches

An async HTTP request can trigger multiple rounds of interceptor callbacks, initial `afterConcurrentHandlingStarted`, and redispatches. Do not assume each request has strictly one pre/post/after.

### 18.8. Relying on ex != null to Detect All Errors

Exceptions handled by a resolver may not appear in `afterCompletion.ex`. Use HTTP status and observation policies.

### 18.9. Misconfiguring excludePathPatterns

For example, including only `/api/**` when a public endpoint lives under `/v1/**` means the interceptor will not run there. Write contract tests for path includes/excludes, context paths, and proxy behavior.

### 18.10. Confusing HandlerInterceptor with ClientHttpRequestInterceptor

`ClientHttpRequestInterceptor` is for **outbound HTTP clients** like `RestTemplate`; `HandlerInterceptor` is for **inbound Spring MVC handler dispatches**. Similar names, different lifecycles.

### 18.11. Trying to Handle 404 in an Interceptor When No Handler Maps

If no matching handler is found, the expected HandlerExecutionChain may not exist to run the interceptor. Use Spring MVC error handling, `@ControllerAdvice`/Boot error handling, or a Filter if you need to observe every request at a lower level.

### 18.12. Registering the Same Interceptor Multiple Times

This can duplicate callbacks, logs, and metrics. Check `WebMvcConfigurer`, custom HandlerMappings, and Spring bean registrations instead of guessing the framework executes each object once.

### 18.13. Misunderstanding order as Applying Identically to All Callbacks

Pre runs in ascending order, post/after run in reverse. Earlier interceptors can still receive cleanup when a later interceptor returns false.

### 18.14. Using afterCompletion to Write a New Response

This is a post-completion callback, not a response-building phase. Committed headers/status can no longer be modified.

## 19. Code Review and Operations Checklist

1. Is the interceptor using the correct `org.springframework.web.servlet.HandlerInterceptor` package?
2. Have interceptors been clearly distinguished from Servlet Filters and Spring Security?
3. Does `preHandle` return true/false with clear semantics?
4. When preHandle returns false, is the response properly populated with status/body?
5. Are resources created by an interceptor before returning false/throwing cleaned up immediately?
6. With multiple interceptors, is `.order(...)` explicitly specified?
7. Have forward pre order and reverse post/after order been tested?
8. Is `postHandle` being misused to alter already-committed REST response headers/bodies?
9. Since `modelAndView` can be null, is it checked before use?
10. Does code avoid falsely assuming `afterCompletion` runs when pre did not return true?
11. Is `ex == null` mistakenly treated as "request succeeded" even when a resolver handled an exception?
12. For async `Callable`/`DeferredResult` requests, has `AsyncHandlerInterceptor` been considered?
13. Could async redispatches cause `preHandle` to run a second time?
14. Are timeouts, cancellations, and cleanups handled properly beyond the happy path?
15. Are request attributes/ThreadLocal/MDC managed according to lifecycle?
16. Are there any mutable instance fields sharing data across concurrent HTTP requests?
17. Do include/exclude paths align with controller mappings and gateway prefixes?
18. Is there a need to process requests before DispatcherServlet? If so, would a Filter fit better?
19. Is there a dependency on REST body shape? If so, would `ResponseBodyAdvice`/DTOs fit better?
20. Is authentication/authorization handled in Spring Security rather than a custom interceptor?
21. Are metric labels based on route templates, avoiding high cardinality and sensitive data?
22. Do tests cover success, early false, handled exceptions, and async dispatches?
23. Has Spring MVC Servlet been distinguished from WebFlux runtime prior to configuration?
24. Do HTTP responses and logs include correlation ID/trace metadata without leaking secrets?

**Conclusion:** `preHandle` is the gate before the controller; `postHandle` runs after a successful handler and suits augmenting MVC view models; `afterCompletion` is the cleanup/observability callback upon completion, **only for interceptors whose `preHandle` returned `true`**. With multiple interceptors, **execution enters in order and exits in reverse order**. When `preHandle` returns false, the controller and subsequent interceptors do not run; when an exception occurs, `postHandle` is usually skipped; under async processing, `afterConcurrentHandlingStarted` replaces the initial dispatch's completion callbacks and redispatches may follow. Pick the right abstraction: Filter/Security at the outer boundary, HandlerInterceptor at the MVC mapping layer, ResponseBodyAdvice for REST bodies, and observation tools for metrics/tracing.

## References

- [Spring Framework 6.1 — HandlerInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/HandlerInterceptor.html): pre=true condition, reverse order, exceptions handled by resolvers.
- [Spring Framework 6.1 — AsyncHandlerInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/servlet/AsyncHandlerInterceptor.html): `afterConcurrentHandlingStarted`, async dispatch.
- [Spring Framework — MVC Interception](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-interceptor.html): pre/post/after, REST commits, and security caution.
- [Spring Framework — MVC Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html): `WebMvcConfigurer.addInterceptors`, mapping patterns.
- [Spring Framework — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): `Callable`, `DeferredResult`, and Servlet async lifecycle.
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): filter chain and wrappers.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): Servlet stack and web configuration.