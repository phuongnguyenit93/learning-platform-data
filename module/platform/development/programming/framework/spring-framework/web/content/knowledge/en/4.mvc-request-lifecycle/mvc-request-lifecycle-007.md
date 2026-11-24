# Dispatch Types: REQUEST, FORWARD, INCLUDE, ERROR, and ASYNC

In a **Spring Framework Web application using Spring MVC on the Servlet stack**, a single HTTP request can pass through **multiple dispatches** at the Servlet layer before the response completes. Each dispatch is tagged with a value from the `jakarta.servlet.DispatcherType` enum: `REQUEST`, `FORWARD`, `INCLUDE`, `ERROR`, or `ASYNC`.

These are **Jakarta Servlet concepts**, not names of five HTTP request methods nor five types of Spring controllers. They determine how the Servlet container routes a request to a Servlet/resource and which Servlet Filters run during a given dispatch. Spring MVC's `DispatcherServlet` is **one specific Servlet** that can receive those dispatches if its mapping matches.

Understanding dispatcher types explains why a filter sometimes runs twice, sometimes does not run at all, why server-side forwarding differs from redirects, why an HTTP 500 does not necessarily go through an `ERROR` dispatch, and why an async request can re-enter `DispatcherServlet` after the initial thread has left.

## 1. Foundation: One Request Can Have Multiple Dispatches

Suppose a client sends strictly **one** request:

```http
GET /forward HTTP/1.1
Host: localhost:8080
```

Target Servlet `/forward` uses `RequestDispatcher.forward(...)` to pass the same request to `/target`. On the network, the browser **does not send a second HTTP request** just because of forwarding. Yet on the container side there are two phases:

```text
Client -- HTTP GET /forward -->
    Servlet container
      └── dispatch REQUEST → Servlet /forward
                               │ RequestDispatcher.forward("/target")
                               ▼
                           dispatch FORWARD → Servlet /target
                                              │
                                              └── response → Client
```

The value of `request.getDispatcherType()` changes per **active dispatch**. Do not confuse it with `request.getMethod()` (`GET`, `POST`...), nor with **threads** or **URLs**. One dispatch does not equal one thread; one thread can execute nested dispatch calls, while an async dispatch can run on a different thread.

**Three layers to keep separate:**

| Layer | Question answered | Example |
| --- | --- | --- |
| HTTP | Which method and resource did the client request? | `GET /forward` |
| Servlet dispatch | Under which scenario is the container dispatching the request? | `DispatcherType.FORWARD` |
| Spring MVC routing | Inside `DispatcherServlet`, which handler matches the request? | `@GetMapping("/target")` |

`DispatcherType` can be queried via `ServletRequest.getDispatcherType()`. Filters are registered for specific dispatcher types; the container selects filters with **matching URL/Servlet mapping** and **matching dispatcher type** on each dispatch pass.

## 2. Table Distinguishing All Five Types

| DispatcherType | What triggers it? | Receiving resource | Key traits to remember |
| --- | --- | --- | --- |
| `REQUEST` | Container receives an initial client request and selects a web component | Servlet/resource matching initial mapping | The first type for a request; **not synonymous with HTTP GET** |
| `FORWARD` | Server code calls `RequestDispatcher.forward(request,response)` | Target resource of the forward | Transfers control server-side; browser URL does not change; response must be uncommitted |
| `INCLUDE` | Server code calls `RequestDispatcher.include(request,response)` | Resource embedded into caller's output | Included resource contributes body; cannot alter status/headers of the outer response |
| `ERROR` | Container executes dispatch to a configured error page | Target error page/handler | Occurs when container error dispatch is actually triggered, **not for every 4xx/5xx status** |
| `ASYNC` | Request in async mode is redispatched via `AsyncContext.dispatch(...)` or framework equivalent | Target resource of the async dispatch | May arrive after the initial processing thread ends; response remains open |

**Lifecycle precision:** `ASYNC` applies only to the **redispatch pass** when dispatched; calling `startAsync()` initially does not turn the currently running dispatch into `ASYNC`. Similarly, `sendError(500)` does not make subsequent statements in the current servlet immediately see `ERROR`; the container's error-page mechanism governs dispatching to the error resource.

Examples in this lesson use Spring Boot 3.x / Spring MVC with Jakarta APIs (`jakarta.servlet.*`), matching Spring Framework 6.x. Legacy Spring 5.x projects typically use `javax.servlet.*`; do not mix the two namespaces.

## 3. REQUEST — The Initial Entry

When a browser or HTTP client sends a request directly to a web application, the Servlet container performs an initial **REQUEST dispatch**. Example:

```java
@Override
protected void doGet(HttpServletRequest request,
                     HttpServletResponse response)
        throws IOException {
    response.setContentType("text/plain;charset=UTF-8");
    response.getWriter().print(request.getDispatcherType());
}
```

If the servlet is mapped to `/direct` and a client calls `GET /direct` normally, the body is:

```text
REQUEST
```

`GET`, `POST`, and `PUT` remain **HTTP methods**, while `REQUEST` is a **dispatcher type**. If the same servlet supports `POST`, an initial HTTP POST also has dispatcher type `REQUEST`.

The standard default when declaring a Servlet filter mapping **without specifying dispatcher types** in `web.xml` is `REQUEST`. However, programmatic registration APIs and frameworks can set their own dispatcher types, so to know where a filter actually runs, inspect the runtime registered configuration.

Spring MVC's `DispatcherServlet` receives `REQUEST` dispatches when its mapping matches the URL. Inside it, `HandlerMapping`/`HandlerAdapter` locate and invoke the controller. `REQUEST` does not mean every request enters `DispatcherServlet`: some URLs are handled by other Servlets or default resource handling.

## 4. FORWARD — Full Server-Side Transfer of Control

### 4.1. Mechanism

A Servlet can hand off to another Servlet/JSP/resource in the same web application via:

```java
RequestDispatcher dispatcher =
        request.getRequestDispatcher("/target");
dispatcher.forward(request, response);
```

`/target` is the path of a resource within the web application context per how `ServletRequest` obtains dispatchers. The container performs a dispatch of type **FORWARD** to the target resource. The caller must forward before the response is committed; if already committed, `forward()` can throw `IllegalStateException`. Any uncommitted content remaining in the response buffer is cleared before forwarding.

The request/response continue passing server-side (potentially via wrappers). Request attributes can travel along with the request. The target sees path information per forward semantics and can access original request details through attributes defined by the Servlet specification such as `jakarta.servlet.forward.request_uri`.

### 4.2. Forward Differs from Redirect

**Forward:** one external HTTP request; the browser keeps displaying the original URL. The target renders/processes on the server:

```text
Browser GET /old → server forward("/new") → target /new → response
Browser URL: /old
```

**Redirect:** the server returns HTTP 3xx status with `Location`; the client **may send a new request** to the new URL:

```http
HTTP/1.1 302 Found
Location: /new
```

```text
Browser GET /old → response 302 → Browser GET /new → new REQUEST dispatch
Browser URL after navigation: /new
```

A new HTTP request after a redirect is a **new REQUEST dispatch** on the target server, not a `FORWARD` of the old request. Do not use redirect instead of forward when you need to preserve request attributes; they do not automatically carry over to a new HTTP request.

In Spring MVC with view-serving controllers, you may see:

```java
@GetMapping("/old")
String oldPage() {
    return "forward:/new";
}
```

This is an **illustrative snippet** in an MVC controller using appropriate view resolution. `forward:` is interpreted as a forward instruction for the view, not an HTTP redirect. In a `@RestController`, a returned string is typically a response body, so you cannot assume `"forward:/new"` there will perform a forward.

### 4.3. Filters/Interceptors on Forward

A filter mapped only to `REQUEST` may run on `/old` but **not run again for FORWARD** on `/new`. To observe/protect the forward target as well, the filter mapping must include `FORWARD` and match the target resource. However, adding `FORWARD` can cause a single request to pass through the same filter multiple times; audit logging, rate-limiting, or mutation logic must know whether it wants per-dispatch or per-logical-HTTP-request execution.

**Security correctness:** do not rely solely on "the path cannot be called directly" to protect a resource. When auth filters have differing dispatcher mappings, evaluate both direct requests and forwards along with the actual authorization enforcement point.

## 5. INCLUDE — Embedding Another Resource's Output

### 5.1. Mechanism

Servlet A is building a response and wants to embed output produced by Servlet/JSP B:

```java
response.getWriter().print("Before|");
request.getRequestDispatcher("/fragment")
       .include(request, response);
response.getWriter().print("|After");
```

When `/fragment` is called via `include(...)`, its dispatcher type is **INCLUDE**. Suppose `/fragment` prints `Middle`; the final response body can be:

```text
Before|Middle|After
```

Unlike forward, caller A **resumes** after the included part returns. An included resource mainly contributes content to the response; it **cannot alter the HTTP status or response headers** of the outer response. Calls to change status/headers inside an included resource are ignored by the container per Servlet rules.

### 5.2. Request Paths and Attributes During INCLUDE

Here is a common pitfall: during `INCLUDE`, the request's path elements may retain the caller's request values; information about the included resource is exposed via attributes such as:

- `jakarta.servlet.include.request_uri`
- `jakarta.servlet.include.context_path`
- `jakarta.servlet.include.servlet_path`
- `jakarta.servlet.include.path_info`
- `jakarta.servlet.include.query_string`

Only some attributes are populated/meaningful depending on the mapping. Therefore, if you debug an included resource using only `request.getRequestURI()`, you may misidentify which resource is running. Inspect the dispatcher type and the corresponding include attributes as well.

`INCLUDE` commonly appears when assembling page fragments in Servlets/JSPs. For modern JSON APIs, it is usually simpler for Java code to call services and build a unified response; do not force `include` into every API because composing responses imposes status/header/body constraints.

### 5.3. Filters During INCLUDE

A filter registered only for `REQUEST` **does not automatically re-run** for included resources. A filter mapped for `INCLUDE` can run if the corresponding URL/servlet mapping matches. Keep in mind that response headers set by an included resource will have no effect; a filter running during an include cannot rely on setting headers itself to enforce outer response policies.

## 6. ERROR — Dispatching to the Container's Error Page

### 6.1. Trigger Conditions

`ERROR` occurs when **the Servlet container transfers processing to an error resource** per error page mappings, for instance when:

- A Servlet calls `response.sendError(404)` or `response.sendError(500)` and the container uses its error-page mechanism;
- An unhandled exception escapes and the container executes configured error handling.

Traditional `web.xml` example:

```xml
<error-page>
    <error-code>500</error-code>
    <location>/errors/internal</location>
</error-page>
```

When the container dispatches to `/errors/internal`, the target resource sees `request.getDispatcherType() == DispatcherType.ERROR`. The final HTTP code, body, and ability to write to the response depend on the scenario, commit timing, mapping, and container.

**Do not equate "HTTP 500" with `ERROR` dispatch**. A controller can directly return:

```java
return ResponseEntity.status(500).body("Unable to process");
```

This sets status/body inside the MVC pipeline; it does not by default trigger an error-page dispatch. Likewise, `@ExceptionHandler` or `@ControllerAdvice` can resolve exceptions directly inside `DispatcherServlet` without an additional `ERROR` dispatch. Spring Boot's standard setup provides an `/error` endpoint in certain configurations, though you must check the actual path in your application.

### 6.2. Error Request Attributes

During an error dispatch, the container supplies metadata for the error handler to diagnose, typically including standard attributes:

| Attribute | Meaning |
| --- | --- |
| `jakarta.servlet.error.status_code` | HTTP status associated with the error |
| `jakarta.servlet.error.exception` | Exception causing the error, if any |
| `jakarta.servlet.error.exception_type` | Class of the exception, if any |
| `jakarta.servlet.error.message` | Error message provided by the container |
| `jakarta.servlet.error.request_uri` | URI of the request that caused the error |
| `jakarta.servlet.error.servlet_name` | Related Servlet, if any |

Java code retrieving attributes without assuming types are always present:

```java
Object status =
        request.getAttribute(RequestDispatcher.ERROR_STATUS_CODE);
Object originalUri =
        request.getAttribute(RequestDispatcher.ERROR_REQUEST_URI);
```

Import `jakarta.servlet.RequestDispatcher`. Never return stack traces, filesystem paths, tokens, or sensitive information directly to clients. Log safely on the server and return a stable error response suited to your API requirements.

### 6.3. Filters During ERROR Dispatch

If you need audit/error correlation or request context handling on error pages, the filter must map `ERROR` if expected to run on that dispatch. However, the response may already be committed or error processing may nest in some containers. Do not arbitrarily alter response status/body from every error filter. With `OncePerRequestFilter`, also inspect `shouldNotFilterErrorDispatch()` and handle nested errors when necessary.

## 7. ASYNC — Request Leaves the Initial Thread and Is Dispatched Again

### 7.1. Servlet Async Lifecycle

Servlet 3.0+ supports async so the initial handling thread does not have to block waiting for slow results on the same call stack. When the Servlet/mapping/filter supports async, code can call `startAsync()`:

```text
HTTP request arrives
  ↓
REQUEST dispatch into Servlet
  ↓
startAsync()                         → request placed in async mode
  ↓
REQUEST thread returns to container  → response remains open
  ↓
background task finishes / data ready
  ↓
AsyncContext.dispatch("/target")     → ASYNC dispatch
  ↓
Servlet /target completes response
```

Key distinction: the incoming request still starts with type **REQUEST**; `startAsync()` only initiates the async cycle. `AsyncContext.dispatch(...)` creates the redispatch of type **ASYNC**. Calling `AsyncContext.complete()` instead can end the response **without** an `ASYNC` redispatch.

Async does not mean "the request is guaranteed to execute on a single dedicated thread forever." Schedulers, executors, containers, and Spring MVC may use multiple threads across stages. Any state relying on `ThreadLocal`, transaction context, MDC/log correlation, or security context must be managed across async boundaries per framework policy; do not assume they automatically follow onto another thread.

### 7.2. ASYNC in Spring MVC

When a controller returns `Callable<T>` or `DeferredResult<T>` in the Spring MVC Servlet stack, the framework can initiate Servlet async handling, release the initial Servlet thread, and **dispatch back** into the container once the result is ready. `DispatcherServlet` can be invoked again in the `ASYNC` phase to finish mapping/serialization and exception handling per the MVC pipeline.

Illustrative Spring MVC controller example:

```java
@RestController
class AsyncGreetingController {

    @GetMapping("/slow-greeting")
    Callable<String> greeting() {
        return () -> "Hello from Callable";
    }
}
```

This is a **Spring MVC snippet**, requiring imports for `org.springframework.web.bind.annotation.*` and `java.util.concurrent.Callable`, placed in an application with MVC dependencies. It is not a standalone Java file compiled with bare `javac`.

In practice, for `Callable`, Spring MVC uses an `AsyncTaskExecutor`; for `DeferredResult`, the application can supply the result from another callback/task. Configure executors and timeouts appropriately for real load. Returning `Callable` does not turn blocking I/O into non-blocking I/O; if the task still performs blocking I/O, the thread running that task still blocks.

**Distinguish Spring's `@Async`** (triggers asynchronous method invocation via proxy/executor under matching conditions) from **Servlet async dispatch**. Annotating a method with `@Async` does not automatically mean `DispatcherType.ASYNC` occurred for an HTTP request.

### 7.3. Interceptors in the Async Cycle

In Spring MVC, `AsyncHandlerInterceptor` provides the `afterConcurrentHandlingStarted(...)` callback. When a handler begins async processing:

- `preHandle(...)` may already have run on the initial dispatch;
- instead of the normal synchronous `postHandle(...)`/`afterCompletion(...)`, the framework calls `afterConcurrentHandlingStarted(...)` so the interceptor can clean up thread-bound context;
- when the result is dispatched back, the framework can invoke `preHandle`, then `postHandle` and `afterCompletion` in the completion phase.

If a timeout or network error terminates the lifecycle without a normal redispatch, **do not assume** `afterCompletion`/`postHandle` will be invoked. Use `DeferredResult` callbacks, `WebAsyncManager`, and appropriate async processing interceptors for cleanup/metrics when needed.

## 8. Filter Dispatcher Mappings Decide What Runs Again

Servlet filters run at the container layer, **before or after** the target Servlet in the filter chain; Spring MVC interceptors run **inside `DispatcherServlet`** for MVC-managed handlers. On each dispatch, the container builds/selects a chain based on dispatcher types and URL/Servlet mappings.

### 8.1. Mapping via web.xml

Example if you want a filter to run on initial requests and forwards, but not on includes, errors, or async:

```xml
<filter-mapping>
    <filter-name>auditFilter</filter-name>
    <url-pattern>/*</url-pattern>
    <dispatcher>REQUEST</dispatcher>
    <dispatcher>FORWARD</dispatcher>
</filter-mapping>
```

Without `<dispatcher>`, the standard deployment-descriptor default for a filter mapping is `REQUEST`. To map `ERROR` or `ASYNC`, declare them explicitly. For async, you must also ensure Servlets/Filters along the path support async (`async-supported`), otherwise calling `startAsync()` can fail with `IllegalStateException`.

### 8.2. Mapping via Java/Spring Boot

With Spring Boot MVC, filters and dispatcher types can be registered explicitly via `FilterRegistrationBean`:

```java
@Bean
FilterRegistrationBean<MyFilter> myFilter() {
    FilterRegistrationBean<MyFilter> registration =
            new FilterRegistrationBean<>(new MyFilter());

    registration.addUrlPatterns("/*");
    registration.setDispatcherTypes(
            DispatcherType.REQUEST,
            DispatcherType.FORWARD,
            DispatcherType.INCLUDE,
            DispatcherType.ERROR,
            DispatcherType.ASYNC);
    registration.setAsyncSupported(true);
    return registration;
}
```

This is an **illustrative configuration snippet**: it requires imports for `org.springframework.context.annotation.Bean`, `org.springframework.boot.web.servlet.FilterRegistrationBean`, `jakarta.servlet.DispatcherType`, and a `MyFilter implements Filter` class. Section 9 provides a complete project.

`setDispatcherTypes(...)` determines which dispatch types the filter applies to; `setAsyncSupported(true)` states that the filter allows Servlet async cycles through. **The two options solve two different problems.** Selecting all five types is not always best: it can cause duplicate logging or re-run authentication/authorization/response wrappers at the wrong time.

### 8.3. `OncePerRequestFilter` Does Not Guarantee "Once Across the Entire HTTP Lifecycle"

Spring provides `OncePerRequestFilter` to support filtering once **per request dispatch / active request flow per the class's semantics**, based on a marker attribute. One logical request can have `REQUEST`, `ASYNC`, and `ERROR` dispatches, so do not read the class name and assume the entire HTTP request executes the filter strictly once.

In Spring Framework 6.x, by default:

- `shouldNotFilterAsyncDispatch()` usually returns `true`: skips subsequent async dispatches.
- `shouldNotFilterErrorDispatch()` usually returns `true`: skips error dispatches.
- You can intentionally override them to `false` to participate in async/error, **but the container's Servlet filter mapping must also include the corresponding dispatcher type**.
- On some Servlet containers, `ERROR` can nest inside `REQUEST`; `doFilterNestedErrorDispatch(...)` is a dedicated hook when request/response wrappers need special handling.

If you need to log a **logical HTTP request** strictly once, define an explicit policy using a request ID or request attribute, and decide whether to log at start, at completion, or in both phases. If you need to count **each dispatch**, count by type rather than treating a filter's "once" as a business metric rule.

### 8.4. `DispatcherServlet` and Servlet Dispatcher Types Are Separate Concepts

`DispatcherServlet` is Spring MVC's Front Controller; `DispatcherType` is a Servlet API enum. Correct or incorrect dispatcher mappings can prevent a filter from running during a forward/error/async dispatch, **even when the Spring MVC controller handles the request properly**.

A forward may target a JSP or another Servlet and never enter an MVC controller. A Servlet ERROR dispatch may hit an error page outside `DispatcherServlet`. Similarly, an error already handled by `@ExceptionHandler` inside MVC does not necessarily pass through a container ERROR dispatch.

## 9. Full Hands-On: Observing All Five Types in One App

The example uses **Java 17+ and Spring Boot 3.5.7**, `spring-boot-starter-web` (Servlet MVC), run with Gradle. Instead of relying on browsers or guessing from logs, the program prints `request.getDispatcherType()` directly from the Servlet receiving the dispatch and from the filter. This is a **Spring Boot application using Servlet APIs directly to demonstrate Servlet container behavior**, not a REST controller template for production API design.

### 9.1. Structure and Dependencies

Structure:

```text
dispatch-demo/
  build.gradle
  settings.gradle
  src/main/java/demo/dispatch/DispatchDemoApplication.java
```

`settings.gradle`:

```groovy
rootProject.name = 'dispatch-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
}
```

Requires Gradle Wrapper or a compatible Gradle installation. If you generated a Spring Initializr project with the same dependencies and versions, keep that project's configuration files and add the Java class below.

### 9.2. A Single Java File Runnable with Spring Dependencies

`src/main/java/demo/dispatch/DispatchDemoApplication.java`:

```java
package demo.dispatch;

import java.io.IOException;
import java.util.EnumSet;

import jakarta.servlet.AsyncContext;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.server.ErrorPage;
import org.springframework.boot.web.server.ErrorPageRegistrar;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;

@SpringBootApplication
public class DispatchDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DispatchDemoApplication.class, args);
    }

    @Bean
    ServletRegistrationBean<EntryServlet> entryServlet() {
        var bean = new ServletRegistrationBean<>(
                new EntryServlet(),
                "/direct", "/forward", "/include", "/fail", "/async");
        bean.setName("entry");
        bean.setAsyncSupported(true);
        return bean;
    }

    @Bean
    ServletRegistrationBean<TargetServlet> targetServlet() {
        var bean = new ServletRegistrationBean<>(
                new TargetServlet(), "/target", "/fragment");
        bean.setName("target");
        bean.setAsyncSupported(true);
        return bean;
    }

    @Bean
    ServletRegistrationBean<ErrorServlet> errorServlet() {
        var bean = new ServletRegistrationBean<>(
                new ErrorServlet(), "/error-page");
        bean.setName("errorPage");
        bean.setAsyncSupported(true);
        return bean;
    }

    @Bean
    ErrorPageRegistrar exampleErrorPage() {
        return registry -> registry.addErrorPages(
                new ErrorPage(HttpStatus.INTERNAL_SERVER_ERROR,
                        "/error-page"));
    }

    @Bean
    FilterRegistrationBean<DispatchLogFilter> logFilter() {
        var bean = new FilterRegistrationBean<>(
                new DispatchLogFilter());
        bean.addUrlPatterns("/*");
        bean.setDispatcherTypes(EnumSet.allOf(DispatcherType.class));
        bean.setAsyncSupported(true);
        return bean;
    }

    static final class DispatchLogFilter implements Filter {
        @Override
        public void doFilter(ServletRequest request,
                             ServletResponse response,
                             FilterChain chain)
                throws IOException, ServletException {
            System.out.println("FILTER " + request.getDispatcherType());
            chain.doFilter(request, response);
        }
    }

    static final class EntryServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws IOException, ServletException {
            response.setContentType("text/plain;charset=UTF-8");

            switch (request.getServletPath()) {
                case "/direct" ->
                    response.getWriter().print(
                            "TYPE=" + request.getDispatcherType());

                case "/forward" ->
                    request.getRequestDispatcher("/target")
                           .forward(request, response);

                case "/include" -> {
                    response.getWriter().print("before|");
                    request.getRequestDispatcher("/fragment")
                           .include(request, response);
                    response.getWriter().print("|after");
                }

                case "/fail" ->
                    response.sendError(500);

                case "/async" -> {
                    AsyncContext context = request.startAsync();
                    context.start(() -> context.dispatch("/target"));
                }

                default -> response.sendError(404);
            }
        }
    }

    static final class TargetServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws IOException {
            response.getWriter().print(
                    "TYPE=" + request.getDispatcherType());
        }
    }

    static final class ErrorServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws IOException {
            response.getWriter().print(
                    "TYPE=" + request.getDispatcherType());
        }
    }
}
```

**Explanation of mechanisms affecting results:**

- `ServletRegistrationBean` registers specific Servlet URLs in the embedded Servlet container. Spring Boot can still provide `DispatcherServlet` for MVC, while these demo URLs are served by **separately registered Servlets**.
- `entryServlet()` creates entry points `/direct`, `/forward`, `/include`, `/fail`, `/async`.
- `targetServlet()` serves `/target` or `/fragment`; it prints the dispatcher type **at the target itself**, after container dispatch.
- `ErrorPageRegistrar` routes status 500 errors to `/error-page`, allowing `ErrorServlet` to observe `ERROR`. Changing error configuration or committing the response early can alter the result.
- The filter sets `EnumSet.allOf(DispatcherType.class)` to log **every dispatch type** passing URL pattern `/*`; `asyncSupported=true` avoids blocking Servlet async startup on the test path.
- `context.start(...)` uses the container's async mechanism to call `dispatch("/target")`. The initial Servlet does not write a body after starting async; the response completes at the redispatch target.
- `System.out.println` in the filter is for observation and can interleave under concurrent requests; do not treat it as proof of global ordering across requests.

### 9.3. Running and Reading Output

From the project directory with Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

In a second terminal, call each URL:

| Command | Expected response body | Meaning |
| --- | --- | --- |
| `curl -s http://localhost:8080/direct` | `TYPE=REQUEST` | Initial dispatch from client |
| `curl -s http://localhost:8080/forward` | `TYPE=FORWARD` | Target receives server-side forward |
| `curl -s http://localhost:8080/include` | `before\|TYPE=INCLUDE\|after` | Caller resumes after include |
| `curl -s http://localhost:8080/fail` | `TYPE=ERROR` | Error page target receives ERROR dispatch |
| `curl -s http://localhost:8080/async` | `TYPE=ASYNC` | Target receives async redispatch |

In the response cell for `include`, the actual pipe characters are `|` (the Markdown table uses `\|` to escape column separators). For `/fail`, use `curl -i` to see HTTP **500**; `-s` only silences progress output and does not change the status.

In the application console, expected filter logs per **single isolated request**:

```text
GET /direct   → FILTER REQUEST
GET /forward  → FILTER REQUEST, FILTER FORWARD
GET /include  → FILTER REQUEST, FILTER INCLUDE
GET /fail     → FILTER REQUEST, FILTER ERROR
GET /async    → FILTER REQUEST, FILTER ASYNC
```

This is the expected log pattern when the app is registered properly without interference from other filters; actual lines can interleave across concurrent requests, and some containers differ on error dispatch timing. Do not treat exact log ordering across concurrent clients as invariant.

**Challenge:** change the filter's mapping from `EnumSet.allOf(DispatcherType.class)` to `EnumSet.of(DispatcherType.REQUEST)` and rerun. The target bodies of forward/include/error/async still show the new types, yet the filter **does not log** the additional dispatches; that directly proves filter mappings control whether the filter runs, not the target's dispatcher type.

Next try letting the filter run only on `REQUEST` and `ASYNC`. Call `/async` and observe two log lines. If you remove `setAsyncSupported(true)` from a filter along a path where a servlet calls `startAsync()`, the request can fail because the entire chain must support async.

## 10. Complex Cases and Boundaries to Know

### 10.1. One Request Can Have a Dispatch Chain Different from the Illustration

There is no rule saying "one request has at most two dispatches." Code can forward through multiple resources, nest includes, trigger error handlers from another path, and perform multi-stage async. The Servlet specification and container enforce valid limits; do not create infinite forward/include loops. Abnormal cycles easily lead to stack errors, repeated logs, and hard-to-analyze failures.

If the goal is **once-only business logic execution**, enforce it at the service/transaction/idempotency layer rather than relying solely on filter invocation counts.

### 10.2. Dispatcher Type Does Not Represent the Full Outcome

`ERROR` only indicates an **error-page dispatch**; it does not guarantee final status 500 or a specific exception. `ASYNC` only indicates a redispatch; it does not guarantee the prior task succeeded. `FORWARD` and `INCLUDE` describe how the container routed to another resource; they do not imply that resource belongs to Spring MVC.

To diagnose accurately, correlate multiple signals:

- `request.getDispatcherType()`;
- method, URI, servlet path, and attributes `jakarta.servlet.forward.*`, `jakarta.servlet.include.*`, `jakarta.servlet.error.*`;
- final response status;
- Servlet/filter mappings and `asyncSupported`;
- Spring MVC handler mappings, interceptors, exception handlers, and async callbacks when the request passes through `DispatcherServlet`.

Never log raw cookies, Authorization headers, session IDs, or sensitive data just to debug dispatches.

### 10.3. Filters Running Multiple Times: Common Pitfalls

Several bugs arise when a filter inadvertently assumes a single dispatch:

1. **Double counting** request metrics: `REQUEST` and `ERROR` both increment a counter representing *one* HTTP request.
2. **Double wrapping** request/response: a filter wraps during `REQUEST` and applies another wrapper during `FORWARD`, `INCLUDE`, or nested `ERROR`.
3. **Duplicate audit logs**: a single user action gets logged twice because `REQUEST` is followed by an `ASYNC` redispatch.
4. **MDC/ThreadLocal leaks**: context set on the initial thread is not cleaned up when the request goes async or when container threads are reused.
5. **Authorization gaps**: a filter is mapped only to URLs or dispatcher types that fail to cover paths to sensitive resources.
6. **Wrong status inside INCLUDE**: an included resource tries to set status/headers, and the changes are silently ignored.
7. **Confusing redirect with FORWARD**: the client gets 3xx and makes a new HTTP request, so logs showing a new `REQUEST` are correct.
8. **Misinterpreting 500**: a controller returns `ResponseEntity.status(500)` with no `ERROR` dispatch because it did not go through error-page dispatch.

### 10.4. Ordering Rules for Filters and MVC Interceptors

One way to visualize it:

```text
Servlet container:
    Filter chain matching dispatcher type
        ↓
    Target Servlet being dispatched to
        ↓
    if Spring MVC's DispatcherServlet:
        HandlerMapping → HandlerInterceptor → Controller → View/Body
        ↑                                   ↓
        └──────── MVC lifecycle callbacks ──┘
```

If there is a `FORWARD` to an MVC-managed resource, the container may rebuild the filter chain for type FORWARD and `DispatcherServlet` then selects a different handler. If forwarding to a JSP or custom Servlet, the controller's Spring MVC interceptors **do not automatically run there**.

For async controllers, interceptor callbacks on the initial dispatch and completion async dispatch differ from the synchronous path, as in Section 7.3. Authentication/authorization enforcement should use stack-wide security components rather than assuming every Servlet/resource goes through MVC interceptors.

## 11. Design Checklist and Self-Check

**When adding a Servlet Filter:**

1. Decide whether the filter operates **per HTTP request** or **per dispatch**.
2. Register the appropriate dispatcher types (REQUEST, FORWARD, INCLUDE, ERROR, ASYNC).
3. Verify URL/servlet mappings and filter chain ordering.
4. If using async, verify `asyncSupported` across all involved components.
5. If using `OncePerRequestFilter`, explicitly check `shouldNotFilterAsyncDispatch`/`shouldNotFilterErrorDispatch`.
6. Test normal, forward/include, error, and async cases; confirm no `ThreadLocal` leaks or double-counted metrics.

**Answer for yourself:**

1. Why can both `GET /direct` and `POST /direct` have `DispatcherType.REQUEST`?
2. Why does `forward("/target")` leave the browser URL unchanged, while `sendRedirect("/target")` usually triggers a new `REQUEST` dispatch?
3. In `INCLUDE`, why cannot an included servlet change the outer response's status or headers?
4. When an MVC controller returns HTTP 500 directly, why is that insufficient evidence that an `ERROR` dispatch occurred?
5. At which step do `startAsync()` and `AsyncContext.dispatch(...)` differently affect the request lifecycle?
6. Will a filter mapped only to `REQUEST` re-run during `ASYNC`/`ERROR`? What must be configured for it to run?
7. Does `OncePerRequestFilter` strictly mean once across all dispatches of a single HTTP request?
8. When a Spring MVC `Callable` completes and redispatches, at which stage should interceptors handle cleanup?
9. In the runnable example, why does the body of `/include` contain `TYPE=INCLUDE` even though the external request began as `REQUEST`?
10. Why must `DispatcherServlet` be distinguished from `DispatcherType` when reading traces?

**Target outcome:** Be able to identify the type of each dispatch within a request, predict which filters participate based on dispatcher mappings, choose `forward`/`include`/`sendError`/`startAsync` for the right purpose, and explain Spring MVC callbacks during the async cycle. This is a key foundation for understanding MVC processing flows and diagnosing hard-to-reproduce filter, error-page, and async bugs.

## References

- Jakarta Servlet Specification: https://jakarta.ee/specifications/servlet/6.1/
- Jakarta Servlet API, `ServletRequest.getDispatcherType()`: https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/ServletRequest.html
- Jakarta Servlet API, `RequestDispatcher`: https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/RequestDispatcher.html
- Spring Framework — Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework API — `OncePerRequestFilter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
