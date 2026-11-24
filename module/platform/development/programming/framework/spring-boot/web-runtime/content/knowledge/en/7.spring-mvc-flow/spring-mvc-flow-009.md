# RequestContext, ServletRequestAttributes, and Per-Request Data Scope

Within an HTTP request in **Spring MVC on the Servlet stack**, controllers, services, filters, views, and error handlers sometimes need access to data belonging strictly to the current request: locale, path, correlation ID, intermediate values, or a temporary object scoped only to that request. Spring provides abstractions to manage this data without threading `HttpServletRequest` manually through every business layer.

Three names that are easy to confuse:

1. **`org.springframework.web.servlet.support.RequestContext`** is a utility for MVC/view context—such as locale, messages, context-path-aware URLs, and binding errors. It is not a global variable holding the request.
2. **`org.springframework.web.context.request.RequestContextHolder`** is the class holding `RequestAttributes` bound to the thread currently processing a request. In MVC, `DispatcherServlet` normally binds this context.
3. **`org.springframework.web.context.request.ServletRequestAttributes`** is the Jakarta Servlet–based implementation of `RequestAttributes`, wrapping `HttpServletRequest` and optionally `HttpServletResponse`. It lets you read/write request- or session-scoped attributes.

This lesson explains how these objects cooperate, the lifecycle of **request scope**, how to use them in controllers/services, why scoped proxies are needed, and the limits when handing work off to other threads. Examples use **Spring Boot 3.3.x, Spring MVC, Java 21**, and Spring Framework 6's `jakarta.servlet.*` namespace.

## 1. Where Does a Request Travel?

Typical synchronous flow:

~~~text
HTTP client
    |
    v
Tomcat / Servlet container
    |
    v
Servlet Filter chain
    |
    v
DispatcherServlet
    |-- binds LocaleContextHolder / RequestContextHolder context
    |-- selects HandlerMapping and HandlerAdapter
    |
    v
Controller -> Service -> Repository
    |             |
    |             +--> can read current RequestAttributes
    |                  if running on a Spring context-bound thread
    |
    v
HttpMessageConverter or ViewResolver / View
    |
    v
HTTP response
    |
    v
Clean up / restore thread-bound context after dispatch
~~~

Inside `DispatcherServlet`, Spring prepares request-bound information before running the handler, then restores the previous context state after processing finishes. Different requests can be handled by the exact same **worker thread** at different times. Cleaning up context at the right lifecycle boundary is critical to avoid cross-request data leaks.

This diagram is a conceptual flow. Servlet async, async dispatches, exception handling, custom filters, and executors can trigger multiple dispatches and switch execution threads.

**Request scope differs from thread scope:** a request-scoped object has the lifetime of an HTTP request; `ThreadLocal` inside `RequestContextHolder` is merely the mechanism for looking up the active context on the current thread. Do not equate "request scope" with "thread scope."

## 2. Comparison Table of Key APIs

| Type | Package / class | Responsibility | Represents the current request? |
| --- | --- | --- | --- |
| MVC view helper | `org.springframework.web.servlet.support.RequestContext` | Locale, messages, context-path URLs, binding errors/model | Accepts request via constructor; not a thread-local holder |
| Thread-bound holder | `org.springframework.web.context.request.RequestContextHolder` | Look up/bind/reset `RequestAttributes` on the thread | Yes, if bound by Spring |
| Generic request attributes | `org.springframework.web.context.request.RequestAttributes` | Read/write attributes in request/session scope | Interface, Servlet-independent |
| Servlet implementation | `org.springframework.web.context.request.ServletRequestAttributes` | Access `HttpServletRequest`, optional `HttpServletResponse`, session, and attributes | Yes, when running on the Servlet stack |
| Jakarta request object | `jakarta.servlet.http.HttpServletRequest` | HTTP method, URI, headers, parameters, request attributes | Yes, passed/injected during request processing |
| Request-scoped bean | `@RequestScope` | Separate target bean instance per HTTP request | Lifecycle managed by Spring IoC |
| Spring MVC model | `Model`/`ModelMap` | Data passed by a handler to a view | Not a global request state store |

In REST APIs, a `HttpServletRequest` method parameter, header/path/query parameters, or a `@RequestScope` bean is usually all you need. `RequestContext` is an MVC view and i18n utility; do not treat it as arbitrary request storage.

## 3. RequestAttributes: Abstraction for Request- and Session-Scoped Data

`RequestAttributes` provides methods such as:

~~~java
Object getAttribute(String name, int scope);
void setAttribute(String name, Object value, int scope);
void removeAttribute(String name, int scope);
String[] getAttributeNames(int scope);
~~~

Two common scope constants:

- `RequestAttributes.SCOPE_REQUEST`: data belonging strictly to the HTTP request.
- `RequestAttributes.SCOPE_SESSION`: data belonging to the HTTP session, potentially persisting across multiple requests in the same session.

Example inside code with an active request context:

~~~java
RequestAttributes attrs = RequestContextHolder.currentRequestAttributes();

attrs.setAttribute(
    "demo.requestId",
    "req-123",
    RequestAttributes.SCOPE_REQUEST
);

String id = (String) attrs.getAttribute(
    "demo.requestId",
    RequestAttributes.SCOPE_REQUEST
);
~~~

This snippet illustrates code **executed inside an HTTP request-handling method**, not a standalone Java program. The value `req-123` is just an example: real systems should generate a reliable unique ID or normalize one from a trusted gateway.

Key point: writing an attribute with `SCOPE_REQUEST` does not turn the data into a singleton and does not place it into the session; once the request finishes, it is no longer state for future requests.

### 3.1. Attribute Names Are Shared Keys on the Request

Other libraries may also set attributes on the same request. Choose clearly namespaced names, such as `com.example.trace.requestId` instead of `id` or `data`, to avoid accidentally overwriting filter or framework data.

Do not store passwords, access tokens, or sensitive personal data in request attributes unless genuinely necessary; many filters, interceptors, controllers, and views can inspect the same request. Limit logging and store minimal data.

### 3.2. Session Scope Does Not Replace Request Scope

A single user can issue multiple requests within the same HTTP session, even concurrently. Writing a request-specific field into the session lets other requests observe or overwrite it. Session data also comes with its own synchronization, expiration, and storage overhead.

If you only need a correlation ID or temporary state for one request, use `SCOPE_REQUEST` instead of `SCOPE_SESSION`.

## 4. How ServletRequestAttributes Wraps Servlet Objects

`ServletRequestAttributes` implements `RequestAttributes` on top of the Servlet container's `HttpServletRequest` and `HttpSession`. Key APIs:

~~~java
HttpServletRequest getRequest();
HttpServletResponse getResponse(); // May be null
Object getAttribute(String name, int scope);
void setAttribute(String name, Object value, int scope);
void removeAttribute(String name, int scope);
~~~

Behaviorally, `SCOPE_REQUEST` maps to attributes attached to `HttpServletRequest`. Thus:

~~~java
ServletRequestAttributes servletAttrs =
    (ServletRequestAttributes) RequestContextHolder.currentRequestAttributes();

servletAttrs.setAttribute(
    "com.example.demo.flag",
    "ready",
    RequestAttributes.SCOPE_REQUEST
);

Object sameValue = servletAttrs.getRequest()
    .getAttribute("com.example.demo.flag");
~~~

`sameValue` evaluates to `"ready"` within the same request. This snippet illustrates execution inside a Servlet request; in general code, check `instanceof` before casting because `RequestAttributes` has other implementations.

### 4.1. Native Request and Response Are Not Always Available

- `getRequest()` returns the wrapped `HttpServletRequest`.
- `getResponse()` can return `null` if the `ServletRequestAttributes` instance was constructed without a response.
- Servlet-specific APIs do not apply directly to WebFlux applications running on Reactor Netty.

Do not retain `HttpServletRequest` or `ServletRequestAttributes` in static fields, mutable singleton fields, or long-running background tasks after the request completes. A Servlet request's lifecycle does not last indefinitely.

### 4.2. Request Completion Mechanism

Spring can manage destruction callbacks for request-scoped beans/attributes when a request finishes. Application code should not manually call `requestCompleted()` on a `ServletRequestAttributes` managed by `DispatcherServlet`; that is infrastructure's job. If you manually bind `RequestContextHolder` in tests or special integrations, understand your cleanup and context-restoration responsibilities.

## 5. RequestContextHolder: Reading Thread-Bound Request Context

Two common lookups:

~~~java
RequestAttributes optional =
    RequestContextHolder.getRequestAttributes();

RequestAttributes required =
    RequestContextHolder.currentRequestAttributes();
~~~

Differences:

| API | When request context exists | When no context exists |
| --- | --- | --- |
| `getRequestAttributes()` | Returns `RequestAttributes` | Returns `null` |
| `currentRequestAttributes()` | Returns `RequestAttributes` | Usually throws `IllegalStateException`, barring fallbacks like JSF |
| `setRequestAttributes(attributes)` | Binds to current thread | Requires careful handling if managed manually |
| `resetRequestAttributes()` | Clears context from current thread | Does not create a new request |

In standard Spring MVC, `DispatcherServlet` already exposes the request context. When code runs from `@Scheduled`, a custom executor, or `main()`, there is normally **no HTTP request** to read.

Safe helper example for code that may run on both request threads and background threads:

~~~java
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

public final class CurrentRequestInfo {
    private CurrentRequestInfo() {
    }

    public static String currentPathOrUnknown() {
        RequestAttributes attrs = RequestContextHolder.getRequestAttributes();
        if (attrs instanceof ServletRequestAttributes servletAttrs) {
            return servletAttrs.getRequest().getRequestURI();
        }
        return "(no servlet request)";
    }
}
~~~

This is a utility class for applications with the Spring Web dependency, not a standalone JDK-only program. It does not magically "create" a request for background threads, nor does it swallow exceptions to mask a missing context.

### 5.1. Avoid Calling setRequestAttributes in Business Code

`RequestContextHolder.setRequestAttributes(...)` is an infrastructure-level API. Manually binding a request onto a thread pool or forgetting cleanup can leave stale context on reused threads. When writing specialized adapters that must bind manually, save the previous context, restore it in `finally`, and verify the request is still alive.

Normally, you **do not need** to call the setter inside Spring MVC controllers/services. Accept `HttpServletRequest` as a method argument, inject a request-scoped collaborator, or pass explicit data directly.

### 5.2. Why Does ThreadLocal Need Cleanup?

Tomcat uses a pool of worker threads. After request A, thread T1 may process request B. If code leaves A's context behind, request B risks reading A's data by mistake. Spring's infrastructure handles bind/restore properly during dispatch; whenever an application creates its own `ThreadLocal`, the application is responsible for cleanup.

Standalone **Java 17+** example illustrating `ThreadLocal` conceptually (this is not the full implementation of Spring's request scope):

**ThreadLocalConceptDemo.java**

~~~java
public class ThreadLocalConceptDemo {
    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    public static void main(String[] args) {
        try {
            CURRENT.set("request-A");
            System.out.println("Inside: " + CURRENT.get());
        } finally {
            CURRENT.remove();
        }

        System.out.println("After cleanup: " + CURRENT.get());
    }
}
~~~

Run:

~~~bash
javac ThreadLocalConceptDemo.java
java ThreadLocalConceptDemo
~~~

Exact stdout:

~~~text
Inside: request-A
After cleanup: null
~~~

For Spring code, use this example solely to understand the principle of thread-bound context—never write a custom static `ThreadLocal` to replace the framework's request scope mechanism.

## 6. RequestContext (MVC View Helper) Is Distinct from RequestContextHolder

`RequestContext`'s full name should be stated clearly:

~~~java
org.springframework.web.servlet.support.RequestContext
~~~

It is an MVC/view helper class:

- Retrieves `WebApplicationContext` and `MessageSource`.
- Resolves `Locale` and optionally `TimeZone` from the web context.
- Looks up i18n messages by message code.
- Builds context-path-aware URLs via `getContextUrl(...)`.
- Supports binding/errors data, often useful in JSP, FreeMarker, or similar view technologies.

Example inside a Spring MVC controller given `HttpServletRequest`:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.servlet.support.RequestContext;

public String linkForCurrentApplication(HttpServletRequest request) {
    RequestContext context = new RequestContext(request);
    return context.getContextUrl("/orders");
}
~~~

If the app sets `server.servlet.context-path=/training`, the result above is typically `/training/orders`; with the default empty context path, it is `/orders`. `RequestContext` in this example uses the `request` passed as an argument rather than pulling context from `RequestContextHolder` just because the names look alike.

In most REST APIs, constructing `RequestContext` manually is unnecessary. If you only need locale, accept a `Locale` parameter; for URLs, consider `ServletUriComponentsBuilder`/an appropriate URI builder alongside reverse proxy policies; for request data, use method parameters or request scope.

**Naming note:** WebFlux also has classes named `RequestContext` in different packages. This lesson covers `org.springframework.web.servlet.support.RequestContext` in the Spring MVC/Servlet stack, not a single universal "global RequestContext" across every stack.

## 7. Data Scopes: Request, Session, Application, Singleton

| Scope | Lifetime | Good fit for | Avoid using for |
| --- | --- | --- | --- |
| Local method variable | Single method call | Intermediate DTOs, short calculations | Sharing across layers without passing arguments |
| `HttpServletRequest.setAttribute` | One HTTP request | Metadata shared across filter/interceptor/controller/view | User state spanning multiple requests |
| `@RequestScope` | One HTTP request | An object holding meaningful per-request state | System-wide caches, long-lived background tasks |
| `@SessionScope` | One HTTP session | Certain user preferences/conversational state | Correlation IDs meant for a single request |
| `@ApplicationScope` | Web application's `ServletContext` | App-wide data tied to `ServletContext` | Personal or request-specific data |
| Singleton Spring bean | One instance per bean definition/container | Stateless services, shared dependencies | Mutable fields storing `userId`/`currentRequest` of the latest request |

Distinguish two ways of storing request-specific state:

- **Request attribute:** key/value attached to the request, e.g., `request.setAttribute("traceId", id)`.
- **Request-scoped bean:** Spring manages an object per request; it can have behavior, dependencies, and lifecycle callbacks.

Both serve request scope, though they are not the same API. Spring's request scope uses the underlying `RequestAttributes` infrastructure to locate the corresponding object.

## 8. Why Request Scope Matters for Singleton Services

`@Service` is singleton by default. Suppose we have buggy code:

~~~java
@Service
public class BadAuditService {
    private String currentUserId;

    public void record(String userId) {
        this.currentUserId = userId;
        // Another request can overwrite this field while processing.
    }
}
~~~

This is an **anti-pattern example**, not recommended code. When two requests run concurrently, both share the single `currentUserId` field on the singleton, causing race conditions and data mixing.

The cleanest approach for concise data is **passing explicitly** via method arguments:

~~~java
public void record(String userId, String correlationId) {
    // Data lives strictly within this call, never written to a shared field.
}
~~~

When multiple components within the same request need a stateful collaborator, `@RequestScope` lets Spring create a separate target per request. Do not default to request scope to avoid designing clean APIs; passing explicit context remains easier to test and safer for async processing.

## 9. @RequestScope and Scoped Proxies

The `@RequestScope` annotation is a shortcut for `@Scope("request")` with `proxyMode=ScopedProxyMode.TARGET_CLASS` by default. This allows injecting into singleton beans via a proxy without needing a request-scoped target instance at startup.

Flow:

~~~text
Singleton RequestStateService created at startup
           |
           +--> holds reference to RequestState scoped proxy
                           |
Request A -> proxy -> RequestState target A
Request B -> proxy -> RequestState target B
Request A -> proxy -> still target A within request A
~~~

Understand clearly:

1. **The proxy is a long-lived reference**, while the target data lives only for the request.
2. Within one HTTP request, accesses to the target bean normally hit **the same instance**.
3. A new request gets a new target; it carries no state from previous requests.
4. Accessing the proxy when **no request scope is active** can throw `ScopeNotActiveException` or a related error.
5. `@RequestScope` defaults to class-based proxies; avoid `final` classes/`final` methods on proxied beans, or use interface-based proxies when appropriate.
6. Marking a bean merely with `@Scope("request")` and injecting it directly into a singleton may not create a proxy as expected; configure the proper proxy mode or use `ObjectProvider` to resolve the bean per request.

**A request-scoped bean is not automatically thread-safe.** If multiple async branches within the same HTTP request access mutable state concurrently, synchronization is still required. "One bean per request" does not mean "one bean per thread."

## 10. Full Example: Spring Boot + RequestContext + ServletRequestAttributes + @RequestScope

This example application proves four things:

1. The controller reads the bound context via `RequestContextHolder`.
2. `ServletRequestAttributes` and `HttpServletRequest` see the same request attribute.
3. A singleton service injects a `@RequestScope` bean via a scoped proxy; the target keeps consistent state within a request and differs across requests.
4. `RequestContext` builds a path relative to the application's context path.

Uses Spring Boot **3.3.13**, Java **21**, and Gradle **8.5+** compatible with Java 21.

Project structure:

~~~text
request-context-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/com/example/requestcontext/
    │       ├── RequestContextDemoApplication.java
    │       ├── RequestState.java
    │       ├── RequestStateService.java
    │       └── RequestDemoController.java
    └── test/
        └── java/com/example/requestcontext/
            └── RequestDemoControllerTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'request-context-demo'
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

Starter web provides Spring MVC and default embedded Tomcat; starter test provides JUnit 5, `MockMvc`, and test utilities. You do not need JSP/FreeMarker to use `RequestContext` APIs in a controller; template view rendering is a separate topic.

### 10.1. Main Class

**src/main/java/com/example/requestcontext/RequestContextDemoApplication.java**

~~~java
package com.example.requestcontext;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestContextDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestContextDemoApplication.class, args);
    }
}
~~~

Place the main class in a parent package covering the beans to scan so `@Component`, `@Service`, and `@RestController` are discovered.

### 10.2. Bean Scoped per HTTP Request

**src/main/java/com/example/requestcontext/RequestState.java**

~~~java
package com.example.requestcontext;

import java.util.UUID;

import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestState {

    private final String requestId = UUID.randomUUID().toString();
    private int touches;

    public String id() {
        return requestId;
    }

    public int nextTouch() {
        return ++touches;
    }
}
~~~

`RequestState` is created fresh for each HTTP request. `requestId` is an illustrative ID generated when the target bean initializes, not an ID from a gateway. The `touches` field is intentionally stateful to demonstrate isolation; in real systems, prefer immutable state unless mutation is genuinely needed.

### 10.3. Singleton Service Using a Scoped Proxy

**src/main/java/com/example/requestcontext/RequestStateService.java**

~~~java
package com.example.requestcontext;

import org.springframework.stereotype.Service;

@Service
public class RequestStateService {

    private final RequestState state;

    public RequestStateService(RequestState state) {
        this.state = state;
    }

    public Sample sample() {
        int first = state.nextTouch();
        int second = state.nextTouch();
        return new Sample(state.id(), first, second);
    }

    public record Sample(String id, int first, int second) {
    }
}
~~~

`RequestStateService` is a singleton, yet the `state` reference it holds is a **proxy**. When request A calls `sample()`, both accesses hit the target bean belonging to request A; request B gets its own target bean. The service never stores request-specific state directly in fields of the singleton itself.

### 10.4. Controller Using All Three APIs

**src/main/java/com/example/requestcontext/RequestDemoController.java**

~~~java
package com.example.requestcontext;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.servlet.support.RequestContext;

@RestController
@RequestMapping("/context")
public class RequestDemoController {

    private final RequestStateService service;

    public RequestDemoController(RequestStateService service) {
        this.service = service;
    }

    @GetMapping("/state")
    public Inspection state(HttpServletRequest request) {
        RequestAttributes attributes =
            RequestContextHolder.currentRequestAttributes();

        if (!(attributes instanceof ServletRequestAttributes servlet)) {
            throw new IllegalStateException("Servlet request expected");
        }

        servlet.setAttribute(
            "com.example.demo.note",
            "request-only",
            RequestAttributes.SCOPE_REQUEST
        );

        String note = (String) request.getAttribute("com.example.demo.note");

        RequestStateService.Sample sample = service.sample();

        RequestContext viewContext = new RequestContext(request);

        return new Inspection(
            servlet.getRequest().getMethod(),
            request.getRequestURI(),
            note,
            sample.id(),
            sample.first(),
            sample.second(),
            viewContext.getLocale().toLanguageTag(),
            viewContext.getContextUrl("/context/state")
        );
    }

    public record Inspection(
        String method,
        String path,
        String note,
        String requestId,
        int first,
        int second,
        String locale,
        String contextUrl
    ) {
    }
}
~~~

Specific mechanics:

- `HttpServletRequest` is supplied to the handler method by Spring MVC, not as a singleton.
- `RequestContextHolder.currentRequestAttributes()` reads the context bound during dispatch.
- `ServletRequestAttributes.setAttribute(..., SCOPE_REQUEST)` writes to the request; `request.getAttribute(...)` reads back the same value.
- `service.sample()` invokes the `@RequestScope` bean twice, yielding `first=1` and `second=2` on every fresh request.
- `RequestContext` is a separate object from the holder; the example uses it to read locale and build a context-path-aware URL.
- The HTTP response is serialized by Jackson from the Java `Inspection` record.

### 10.5. Running and Testing Manually

If Gradle and JDK 21 are installed, from the project directory:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

If the project already has a wrapper, skip `gradle wrapper`. On Windows PowerShell run `.\gradlew.bat bootRun`.

Send an HTTP request:

~~~bash
curl -i http://localhost:8080/context/state
~~~

Expected result: HTTP **200 OK** and JSON with fields like:

~~~json
{
  "method": "GET",
  "path": "/context/state",
  "note": "request-only",
  "requestId": "d1a4fb7e-6fd5-4e24-9ad4-9da397b0d216",
  "first": 1,
  "second": 2,
  "locale": "en-US",
  "contextUrl": "/context/state"
}
~~~

**This is an illustrative response, not fixed output:** `requestId` is a random UUID; `locale` depends on client language and resolver; JSON field order may vary. `method`, `path`, `note`, `first`, and `second` match the code and URL under default configuration.

Sending the request again yields a new `requestId`, while `first=1` and `second=2` still hold for the next request. Explanation: a fresh `RequestState` target is created per request; `touches` does not persist across requests.

If you add:

~~~yaml
server:
  servlet:
    context-path: /training
~~~

then the request URL becomes `http://localhost:8080/training/context/state` and the `contextUrl` generated by `RequestContext` is `/training/context/state`. The `path` value from `getRequestURI()` also includes the context path. Avoid concatenating URLs manually everywhere; behind reverse proxies, verify forwarded headers and infrastructure trust policies.

## 11. Testing That Two Requests Are Truly Isolated

When testing scope, invoking a controller method once is not enough to prove state never leaks between requests. `MockMvc` can execute multiple MVC dispatches within a test context and assert distinct IDs.

**src/test/java/com/example/requestcontext/RequestDemoControllerTest.java**

~~~java
package com.example.requestcontext;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestDemoControllerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void requestScopeIsFreshForEachRequest() throws Exception {
        MvcResult first = mvc.perform(get("/context/state"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.note").value("request-only"))
            .andExpect(jsonPath("$.first").value(1))
            .andExpect(jsonPath("$.second").value(2))
            .andReturn();

        MvcResult second = mvc.perform(get("/context/state"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.first").value(1))
            .andExpect(jsonPath("$.second").value(2))
            .andReturn();

        JsonNode body1 = mapper.readTree(
            first.getResponse().getContentAsString());
        JsonNode body2 = mapper.readTree(
            second.getResponse().getContentAsString());

        String id1 = body1.path("requestId").asText();
        String id2 = body2.path("requestId").asText();

        assertFalse(id1.isBlank());
        assertFalse(id2.isBlank());
        assertNotEquals(id1, id2);
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

The test verifies both **stability within a single request** (`first=1`, `second=2`) and **isolation between two requests** (different UUIDs). The theoretical probability of UUID collision is nonzero but negligibly small for this example.

`@SpringBootTest` boots the application and `@AutoConfigureMockMvc` configures `MockMvc` without opening a network socket. To test real Tomcat/HTTP connections, use integration tests with `webEnvironment=RANDOM_PORT` and an appropriate HTTP client—which is a separate scope.

## 12. Accessing Request Data Across Layers

| Location | Preferred approach | Notes |
| --- | --- | --- |
| Controller method | `@RequestHeader`, `@PathVariable`, `@RequestParam`, `HttpServletRequest` | Explicit dependencies, easy to test |
| Servlet Filter | `HttpServletRequest`/`ServletRequest` passed to the filter | May run before `DispatcherServlet` binds context |
| Spring MVC `HandlerInterceptor` | `HttpServletRequest` parameter in `preHandle`/`postHandle` | Mind callbacks during async dispatches |
| Singleton service | Immutable data via method arguments, or a suitable request-scoped collaborator | Avoid mutable fields holding current user/request |
| View technology | Model attributes and `RequestContext` when needed | View helper is not global storage |
| Error handler/advice | Parameter injection and details from exception/request | Must also account for errors before the handler |
| `@Async` or custom executor | Pass required immutable snapshot | Thread-bound request context normally does not propagate automatically |
| `@Scheduled`/startup task | Do not rely on request context | No active HTTP request exists |
| WebFlux/Reactive | `ServerWebExchange`/Reactor Context | Do not assume `ServletRequestAttributes` exists |

**Selection principle:** if you only need one or two values, passing them as parameters is the clearest approach with minimal infrastructure coupling. Use `RequestContextHolder` deep in code only when justified and when the implicit dependency on a web request is acceptable.

## 13. When Are RequestContextListener and RequestContextFilter Used?

In typical Spring MVC applications, `DispatcherServlet` already binds request context for processing inside dispatch. However, if code running **outside `DispatcherServlet`** needs `RequestContextHolder` or web scopes, Spring Framework provides:

- `RequestContextListener`: a Servlet listener exposing the request according to its lifecycle.
- `RequestContextFilter`: a Servlet filter binding request context in the filter chain; handles async/error dispatches per filter behavior.
- `DispatcherServlet`: exposes the request itself while dispatching MVC requests.

Do not register an extra listener or filter just because you saw it in an online snippet. Check whether your code runs inside regular servlet dispatch or outside it, what filters Boot already registers, and what filter chain ordering is required. Redundant registration complicates reasoning about context and filter order.

A realistic use case: a third-party servlet or filter handles a request without entering `DispatcherServlet`, yet wants to use Spring's request scope. In that case you may need a mechanism to expose request context outside `DispatcherServlet`, while carefully verifying lifecycle and dispatch boundaries.

## 14. Thread-Bound Context Does Not Automatically Cross to @Async or CompletableFuture

`RequestContextHolder` relies on `ThreadLocal` (or `InheritableThreadLocal` when explicitly configured). When a controller offloads work to `@Async`, `CompletableFuture.supplyAsync`, or an executor pool, the task normally runs on another thread. On that thread:

~~~java
RequestContextHolder.getRequestAttributes()
~~~

may return `null`; and:

~~~java
RequestContextHolder.currentRequestAttributes()
~~~

may throw `IllegalStateException` stating no thread-bound request is found. This is not a Spring Boot bug; it is the natural consequence of **crossing a thread context boundary**.

### 14.1. Never Retain HttpServletRequest Across Background Jobs

Do not do this:

~~~java
// Anti-pattern: avoid holding the request object across another thread.
executor.execute(() -> {
    String userAgent = request.getHeader("User-Agent");
    // The request may already be finished when this runs.
});
~~~

This snippet illustrates a design flaw, not a runnable program. Holding a reference to `HttpServletRequest` after the request finishes can violate its lifecycle; reading request data inside background tasks also risks data leaks or container coupling.

### 14.2. Safe Approach: Capture a Snapshot of Only the Needed Data

On the request thread, extract the values needed for business logic and pass an immutable DTO:

~~~java
public record RequestSnapshot(String correlationId, String localeTag) {
}
~~~

In the controller or service receiving validated/normalized parameters:

~~~java
RequestSnapshot snapshot =
    new RequestSnapshot(correlationId, locale.toLanguageTag());

backgroundService.submit(snapshot);
~~~

This snippet illustrates design structure, not a complete Java class; `correlationId`, `locale`, and `backgroundService` are assumed to be provided validly. The task receives only the snapshot, never holds the full Servlet request, and never accesses `RequestContextHolder` after the request ends.

Never treat a correlation ID taken straight from a header as proof of identity. Authentication/authorization must be enforced by dedicated security policies.

### 14.3. InheritableThreadLocal Is Not a Cure-All for Thread Pools

`RequestContextHolder.setRequestAttributes(attributes, true)` can use `InheritableThreadLocal`. This approach is **unsafe as a general solution for thread pools**, because pooled/reused threads can retain unrelated or expired contexts. Spring explicitly warns against enabling inheritance with thread pools that dynamically create worker threads.

If context propagation is needed, use a mechanism with explicit lifecycle management, pass immutable snapshots, or use framework-supported propagation tools appropriate for your version and task type. Never set/reset context manually inside every business method as a blanket rule.

### 14.4. Spring MVC Async Is Coordinated by the Framework

Spring MVC supports `Callable`, `WebAsyncTask`, `DeferredResult`, and async Servlet dispatches. For certain MVC-managed async paths, the framework can manage context during execution and re-dispatch, yet **do not assume** arbitrary worker threads automatically see the same `RequestContextHolder`.

With `DeferredResult`, the servlet request may sit in async state after the initial thread has exited `DispatcherServlet`; the framework re-dispatches when the result arrives. If code requires context inside an arbitrary callback, explicitly verify thread/dispatch boundaries and whether context propagation applies to that specific case.

## 15. Correlation IDs, Logging, and Security Responsibilities

Applications often want every log entry for an HTTP request to share a correlation ID. A correlation ID can be placed in a request attribute and/or MDC inside a filter, though the two are distinct:

- **Request attribute:** data living on the HTTP request, readable by components holding a request reference.
- **MDC:** diagnostic context typically stored per thread by the logging framework; must be cleared in `finally` and may require propagation across thread switches.
- **HTTP header:** data arriving from client/gateway; spoofable unless governed by a trust policy.
- **Trace context:** distributed tracing model with its own propagation and standards (e.g., W3C trace context); not identical to an arbitrary request attribute.

If configuring MDC manually, set and clear it inside `try/finally` around the request, and pay attention to how the filter runs on async/error dispatches. When using Micrometer Tracing / Spring Boot Actuator, prefer preconfigured instrumentation so you do not inadvertently corrupt trace IDs.

**Never use `RequestContextHolder` to fetch the "current user" by reading an unauthenticated request attribute and treating it as authorization.** Principal/Spring Security context and access control policies are separate concerns that must be verified independently.

## 16. Common Pitfalls and How to Diagnose Them

### 16.1. "No thread-bound request found"

Symptom: calling `RequestContextHolder.currentRequestAttributes()` inside `@Async`, `@Scheduled`, a unit test without an MVC context, or an off-thread callback.

Resolution: inspect the call stack and current thread; do not bind a fake request just to silence the error. Pass needed data as method parameters/immutable snapshots, or run the logic inside a framework-supported MVC dispatch.

### 16.2. "Scope 'request' is not active for the current thread"

Symptom: a request-scoped bean is accessed from startup code, a background worker, or outside an active scope.

Resolution: avoid calling the proxy outside a request; inspect singleton initialization and lifecycle code. In isolated unit tests, supply a valid request context or mock the dependency instead of reusing a real Servlet request.

### 16.3. Singleton Service Stores currentUserId in a Mutable Field

Symptom: request A sees B's data under concurrent load.

Resolution: use local variables, immutable DTO parameters, or proxy-injected request-scoped beans; never use shared mutable fields for per-request state.

### 16.4. Unsafe Cast of RequestAttributes to ServletRequestAttributes

Symptom: `ClassCastException` in non-Servlet environments or specialized tests.

Resolution: check `instanceof ServletRequestAttributes`, or depend only on the `RequestAttributes` abstraction when you just need get/set attributes.

### 16.5. Using javax.servlet When Running Spring Boot 3

Spring Boot 3 uses the Jakarta Servlet API (`jakarta.servlet.http.HttpServletRequest`). Legacy `javax.servlet.*` code from Spring Boot 2 cannot be copied directly without migration.

### 16.6. Confusing RequestContext with RequestContextHolder

`RequestContext` in `web.servlet.support` is a view helper and has no static `currentRequestAttributes()` method. That method belongs to `RequestContextHolder` in `web.context.request`. Check packages/imports when class names look similar.

### 16.7. Unexpected Mutation of a Request-Scoped Bean

If multiple async branches within **the same request** mutate a request-scoped object concurrently, it is not thread-safe by default. Use immutable state, proper synchronization, or avoid sharing mutable state.

### 16.8. Using SCOPE_SESSION to Pass Data Between Filter and Controller

Request-specific data placed into the session persists across multiple HTTP requests, mixing state and increasing memory usage. Use `SCOPE_REQUEST` to tie data strictly to the current request.

### 16.9. Request-Scoped Dependency Missing in @WebMvcTest

`@WebMvcTest` is an MVC slice and does not automatically import arbitrary services. If a controller needs a service or request-scoped bean, supply `@MockBean`/`@MockitoBean` (depending on version) or `@Import` configuration. The full example in this lesson uses `@SpringBootTest` to avoid missing application beans.

### 16.10. Reading Locale from the Wrong Source

`request.getLocale()` reflects preferences from the HTTP request; `RequestContext.getLocale()` may use the locale resolved by Spring MVC's `LocaleResolver`. In apps supporting language switching via cookies/sessions/resolvers, the two values can differ. Choose the source matching your i18n policy.

### 16.11. Mistaking MockMvc for Real Tomcat

`MockMvc` runs MVC dispatch inside a test harness without opening a network socket by default. Passing scope tests do not prove production reverse proxy, session cookie, or network timeout settings are correct.

## 17. Quick Decision Table: Which Approach Should You Choose?

| Need | Preferred approach |
| --- | --- |
| Read a header in a controller | `@RequestHeader` or `HttpServletRequest` |
| Get request path in a handler | `HttpServletRequest` method parameter or supplied MVC component |
| Share metadata between filter and controller | `request.setAttribute(...)`/`getAttribute(...)` with a namespaced key |
| Share one stateful object throughout a single request | `@RequestScope` bean |
| Use a request-scoped bean in a singleton service | Default `@RequestScope` scoped proxy or `ObjectProvider` when appropriate |
| Access `RequestAttributes` where request isn't passed directly | `RequestContextHolder.getRequestAttributes()` if implicit thread-bound coupling is acceptable |
| Build context-path URLs and i18n in MVC views | `RequestContext` or appropriate view helper |
| Run background tasks | Pass immutable snapshots / job payloads |
| Use reactive WebFlux | `ServerWebExchange` and Reactor Context; do not assume Servlet requests |
| Persist long-lived state | Controlled database/cache/session, not request scope |

A principle worth keeping in mind: **prefer explicit data, minimize implicit thread dependencies**. `RequestContextHolder` is convenient, but makes services harder to run standalone in CLIs, batch jobs, async tasks, and tests. Use it only when the trade-off and scope are clearly understood.

## 18. Self-Check Checklist

1. Have you distinguished `RequestContext` (MVC view helper) from `RequestContextHolder` (thread-bound holder)?
2. Whenever calling `RequestContextHolder`, is the code guaranteed to run inside a valid request dispatch?
3. Does the data belong to a single request, an HTTP session, or the entire application?
4. When using `ServletRequestAttributes`, have you checked for a Servlet environment and nullable responses?
5. Are request attribute keys namespaced to avoid collisions with frameworks or filters?
6. Are singleton services free of mutable fields storing current user/request IDs?
7. Are `@RequestScope` targets accessed properly via scoped proxies/`ObjectProvider`?
8. Could any request-scoped object be accessed during startup, schedulers, `@Async`, or worker pools?
9. When using async, is data passed via immutable snapshots or proper propagation?
10. Is there any risk of holding `HttpServletRequest`/`ServletRequestAttributes` after the HTTP request finishes?
11. Are you avoiding logging sensitive headers, tokens, request attributes, or session data?
12. Do tests verify that state stays consistent **within a single request** and isolated **across requests**?
13. Have you tested both normal MVC paths and error/async dispatches if your app uses them?
14. For Spring Boot 3, do all imports use `jakarta.servlet.*`?
15. If migrating to WebFlux, have you eliminated Servlet and `ThreadLocal` context assumptions?

**Summary:** In the Spring MVC flow, `RequestContextHolder` gives access to framework-managed thread-bound `RequestAttributes`; `ServletRequestAttributes` implements that abstraction on top of Servlet requests and sessions; and `RequestContext` is an MVC helper for locale, messages, and URLs/views. When data belongs strictly to one HTTP request, use request attributes or `@RequestScope` appropriately. Never store per-request state in singleton mutable fields, and never assume thread-bound context automatically follows `@Async` or thread pools: pass minimal, lifecycle-safe data and test across request boundaries.

## References

- Spring Framework — [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html), explaining request scope and scoped proxies.
- Spring Framework 6.1 — [RequestContextHolder](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html), thread-bound attributes API.
- Spring Framework 6.1 — [ServletRequestAttributes](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/web/context/request/ServletRequestAttributes.html), request/session adapter.
- Spring Framework 6.1 — [RequestContext](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/web/servlet/support/RequestContext.html), MVC view helper.
- Spring Framework — [Asynchronous Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html), async Servlet dispatch.