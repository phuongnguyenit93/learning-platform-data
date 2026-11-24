# Requirements for a Web-Aware Context Supporting Web Scopes in the Spring Framework

## Objective

Understand when `request`, `session`, `application`, and `websocket` scoped beans can function; distinguish a **web-aware Spring `ApplicationContext`** from the **current HTTP request**; configure properly for Spring MVC and for requests handled outside `DispatcherServlet`; use web-scoped beans safely inside singletons; and diagnose common errors.

## 1. What does "a context supporting web scopes" mean?

Spring IoC manages beans in an `ApplicationContext`. Basic scopes such as `singleton` and `prototype` work in plain Java applications. The four web scopes require a container capable of interacting with web infrastructure:

| Scope | Bean Sharing Unit | Requirements |
| --- | --- | --- |
| `request` | An HTTP request | A web-aware `ApplicationContext` and a request recognized by Spring at access time |
| `session` | An HTTP session | A web-aware context and an appropriate HTTP session/request |
| `application` | A `ServletContext` | A servlet-aware application context bound to the `ServletContext` |
| `websocket` | A WebSocket session under Spring's supported mechanism, typically STOMP over WebSocket | Active WebSocket/STOMP infrastructure and corresponding session scope |

`application` **differs from** `singleton`: a `singleton` bean belongs to **one** Spring IoC container, whereas an `application` bean belongs to **one** `ServletContext` (which can be visible across multiple Spring web contexts in the same application as a `ServletContext` attribute).

A web-aware context does not simply mean "the project has the `spring-web` dependency", "I put `@RequestScope`", or "it runs in a JVM with an HTTP port". Spring must initialize the right context type and register the corresponding `Scope`s. For web requests/sessions, the execution thread must also be able to access the current request's `RequestAttributes`.

### Two independent conditions to distinguish

1. **At container startup:** the web-aware context is set up, registers web scopes, and links to the corresponding web runtime. For example, in a Servlet MVC application this is a `WebApplicationContext` (which may have a root context and a `DispatcherServlet` child context).
2. **At bean access time:** for `request`/`session`, there must be a valid HTTP request that Spring has bound to the current processing context. If a background job invokes a scoped bean with no request present, the web container may still exist yet **the request scope is not currently active**.

Diagram:

```text
Servlet container
  └─ ServletContext
      ├─ WebApplicationContext (registers web scopes)
      │   └─ bean definitions: singleton, request, session, application, ...
      └─ HTTP request → DispatcherServlet / RequestContextFilter / RequestContextListener
                           └─ RequestAttributes bound to processing thread
                               ├─ current request-scoped target
                               └─ session-scoped target of the HTTP session
```

Specifically: having a **bean definition** of a web-scoped bean in the container does not mean the target bean has already been created. The target may only be created when an active request/session exists and an actual call reaches it.

## 2. Minimal container and infrastructure

### 2.1. Choosing the right ApplicationContext

In the Jakarta Servlet-based Spring MVC model:

- `WebApplicationContext` is the `ApplicationContext` interface with access to the Servlet environment; web-configured implementations such as `AnnotationConfigWebApplicationContext` and `XmlWebApplicationContext` are created with the proper lifecycle.
- `DispatcherServlet` uses a `WebApplicationContext`; there may be a root context managed by `ContextLoaderListener` and a servlet-specific child context. Not every application needs to configure both manually.
- With Spring Boot running a **Servlet web application** (e.g., with `spring-boot-starter-web` and `SpringApplication.run`), Boot automatically sets up the servlet web context and registers the needed MVC dispatcher. You typically only need to declare beans with `@RequestScope`, `@SessionScope`, or `@ApplicationScope`.

Example of a standalone context:

```java
// Illustrates a context WITHOUT a web environment, not an HTTP-serving application.
try (var context = new org.springframework.context.annotation.AnnotationConfigApplicationContext()) {
    context.registerBean("greeting", String.class, () -> "hello");
    context.refresh();
    System.out.println(context.getBean("greeting"));
}
```

The container above is suitable for ordinary beans; it does not automatically provide request/session web scopes. If you register a bean with `@Scope("request")` and ask Spring to instantiate the target through this kind of context, you will encounter an error related to an **unregistered scope name** (possibly wrapped in `BeanCreationException`).

Do **not** work around this by arbitrarily registering a `SimpleThreadScope` under the name `request`: "per thread" does not mean "per HTTP request"; servlet containers reuse threads, and asynchronous processing can switch threads.

### 2.2. Ensuring the HTTP request is exposed by Spring

In Spring MVC, `DispatcherServlet` already exposes the request and required state. Requests passing through it **do not need** an extra `RequestContextListener` or `RequestContextFilter` just to activate scopes.

If an HTTP request is processed **outside** `DispatcherServlet` (such as a plain servlet or another MVC framework that needs Spring web-scoped beans), configure **one** of the two:

- `RequestContextListener`: a Servlet API listener that binds and cleans up request context for listener callbacks.
- `RequestContextFilter`: a servlet filter that binds the request context when the filter chain runs; appropriate when URL/dispatcher type mappings are needed or a listener cannot be used.

Example `web.xml` **choosing the listener** (traditional Servlet application):

```xml
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         version="6.0">
    <listener>
        <listener-class>org.springframework.web.context.request.RequestContextListener</listener-class>
    </listener>
</web-app>
```

Example **alternative using a filter**, not something you must add alongside the listener:

```xml
<filter>
    <filter-name>requestContextFilter</filter-name>
    <filter-class>org.springframework.web.filter.RequestContextFilter</filter-class>
</filter>
<filter-mapping>
    <filter-name>requestContextFilter</filter-name>
    <url-pattern>/*</url-pattern>
</filter-mapping>
```

The filter snippet above is only a **configuration fragment placed inside a valid `web.xml`**, not a standalone XML document. Check URL/dispatcher type mappings when error/async dispatch support is needed. On Spring Framework 6+/Spring Boot 3+, the Servlet API is `jakarta.servlet.*`; do not mix it with `javax.servlet.*` from older versions.

## 3. How Spring identifies the current request/session

During Servlet processing, Spring represents HTTP request data with `ServletRequestAttributes` and accesses it via `RequestContextHolder`. `DispatcherServlet`, `RequestContextFilter`, or `RequestContextListener` binds that data to the thread serving the request, then cleans up the binding per lifecycle.

When a `request`-scoped bean is requested, the scope implementation looks up the corresponding request attributes, creates or retrieves the bean's target in the request, and registers a cleanup callback when the request finishes. For `session`, the target is bound to the corresponding session, persisting across multiple requests in the same session until the session is no longer valid (depending on lifecycle/session management).

Timing notes:

- **The container having started** does not mean every thread has an HTTP request.
- **Obtaining a proxy** at startup can be valid; **invoking the proxy to resolve the target** outside a request is what fails.
- Two requests from two different clients have separate `request` targets. Two requests in the same HTTP session normally share the `session` target, provided the cookie/session ID is maintained.
- A new HTTP request served by the same thread pool worker must still get a new `request` target; the scope is not tied to thread identity.

You can inspect the current context when diagnosing:

```java
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;

RequestAttributes attributes = RequestContextHolder.getRequestAttributes();
if (attributes == null) {
    // This thread currently has no Spring-bound request attributes.
}
```

This is an **illustrative snippet placed inside a method**, not a standalone Java file. `getRequestAttributes()` returns `null` if there is no binding, whereas `currentRequestAttributes()` can throw `IllegalStateException`. Do not use `RequestContextHolder` as an arbitrary business state store or long-lived cache.

## 4. Complete Example: `@RequestScope` working with Spring Boot MVC

The following example uses **Java 17+**, Spring Boot 3.3.13 (Servlet MVC), and Maven. Create the directory:

```text
web-scope-demo/
├── pom.xml
└── src/main/java/demo/
    ├── DemoApplication.java
    ├── RequestToken.java
    └── ScopeController.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>web-scope-demo</artifactId>
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

**src/main/java/demo/DemoApplication.java**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**src/main/java/demo/RequestToken.java**

```java
package demo;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestToken {
    private static final AtomicLong SEQUENCE = new AtomicLong();
    private final long id = SEQUENCE.incrementAndGet();

    public long id() {
        return id;
    }
}
```

**src/main/java/demo/ScopeController.java**

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ScopeController {
    private final RequestToken requestToken;

    public ScopeController(RequestToken requestToken) {
        this.requestToken = requestToken;
    }

    @GetMapping(value = "/scope", produces = MediaType.TEXT_PLAIN_VALUE)
    public String scope() {
        long first = requestToken.id();
        long second = requestToken.id();
        return "first=" + first + ",second=" + second;
    }
}
```

Run in the `web-scope-demo` directory:

```bash
mvn spring-boot:run
```

Open a **second terminal** and call sequentially (freshly started app, no prior requests to the endpoint):

```bash
curl -s http://localhost:8080/scope
curl -s http://localhost:8080/scope
```

Each command receives a plain-text body, **without a trailing newline**:

```text
first=1,second=1
first=2,second=2
```

The output lines above represent **two consecutive responses**, one logical line per response; when printed directly with `curl -s` in the same terminal, the two bodies may run together if the terminal does not insert a newline. The counter values assume a freshly started app and that these two requests are the first two creating `RequestToken`.

Why does the code work even though `ScopeController` is a singleton by default?

- `@RequestScope` declares the `request` scope and uses a **class-based scoped proxy** (`ScopedProxyMode.TARGET_CLASS`) by default.
- Spring injects a **proxy** into the singleton controller; the proxy does not hold a fixed `RequestToken`.
- Each time `requestToken.id()` executes during an HTTP request, the proxy resolves the target for the **current request**. Two calls within the same request use the same target; the next request gets a new target.
- When the request completes, the request-scoped target reaches the end of its request lifecycle; the singleton controller remains alive.

**Verification experiment:** if you replace `@RequestScope` with `@Scope("request")` without configuring a proxy and still constructor-inject into an eager singleton, Spring will normally try to resolve the target too early when initializing the controller, causing an error because request scope is not yet active. You can fix that by using `@Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)`, keeping `@RequestScope`, or injecting `ObjectProvider<RequestToken>` and fetching the target when a request is active.

## 5. Properly injecting web-scoped beans into singletons

Two common approaches:

### A. Scoped proxy

```java
@Component
@RequestScope
class RequestState {
    public String value() {
        return "per-request";
    }
}

@Service
class BusinessService {
    private final RequestState state;

    BusinessService(RequestState state) {
        this.state = state; // Receives proxy safely during singleton initialization.
    }

    String handle() {
        return state.value(); // Target is resolved within the active request.
    }
}
```

This is a **two-class illustrative snippet**, placed in a package of a Spring MVC application. Do not assume `handle()` works properly from a scheduler or a singleton's `@PostConstruct`: the proxy still requires an active request at call time.

### B. ObjectProvider (lazy lookup)

```java
@Service
class BusinessService {
    private final org.springframework.beans.factory.ObjectProvider<RequestState> states;

    BusinessService(org.springframework.beans.factory.ObjectProvider<RequestState> states) {
        this.states = states;
    }

    String handle() {
        return states.getObject().value();
    }
}
```

`ObjectProvider` defers fetching the bean until needed; calling `getObject()` still requires the scope to be active. When using `@Scope("request")` without a proxy, this approach is useful if you do not want to create a scoped proxy. The examples in this section require the matching Spring imports and belong inside a configured web application; the full runnable example is in section 4.

Do not hold references to the web-scoped bean **target** or `HttpServletRequest` inside static fields, shared caches, or singletons beyond the request/session lifetime. With class-based proxies, keep in mind standard limitations with `final` or `private` classes/methods; consider an interface proxy or `ObjectProvider` where appropriate.

## 6. What else do session, application, and websocket scopes require?

### HTTP session

```java
@Component
@org.springframework.web.context.annotation.SessionScope
class Cart {
    private final java.util.List<String> items = new java.util.ArrayList<>();

    public void add(String item) {
        items.add(item);
    }

    public java.util.List<String> items() {
        return java.util.List.copyOf(items);
    }
}
```

The bean exists per **HTTP session**, not per system-wide user account. The client must maintain the session identifier (typically a cookie); once the session is invalidated/expired, the same instance is no longer present. With multiple concurrent requests in the same session, the bean can be accessed concurrently: thread-safe synchronization is required if it holds mutable state. In distributed systems, session sharing/persistence strategies and serialization of session objects depend on deployment infrastructure; web scope itself does not solve clustering.

### Servlet application

```java
@Component
@org.springframework.web.context.annotation.ApplicationScope
class AppPreferences {
    public String localeDefault() {
        return "vi-VN";
    }
}
```

The bean belongs to the web application's `ServletContext`. It suits true Servlet application-level state, yet requires caution if multiple Spring contexts share the same `ServletContext` or mutable data is updated concurrently. The `application` scope **does not automatically turn the bean into a global variable across all JVMs/replicas**.

### WebSocket

`websocket` scope in Spring is bound to a WebSocket session (especially within messaging/STOMP over WebSocket infrastructure). A matching connection/session and message processing infrastructure must exist. Declaring a `@Scope("websocket")` bean in an application handling only HTTP REST is **not enough** to activate WebSocket scope. The initial HTTP handshake request and the WebSocket session lifecycle are two different scopes.

## 7. Confusing situations

| Situation | Result/Measure |
| --- | --- |
| `new AnnotationConfigApplicationContext(...)` then using `@RequestScope` | Plain Java context has no web scopes; use a web-aware context when actually running a Servlet web app |
| Spring Boot app configured in non-web mode (e.g., `WebApplicationType.NONE`) | No active servlet request; do not use request/session-scoped targets as in MVC |
| `WebApplicationContext` exists, yet a `request` bean is called from `@Scheduled` or a background thread | Scope is not active on that thread; pass needed data as parameters/job payload |
| MVC request goes through `DispatcherServlet` | `DispatcherServlet` already exposes the request; adding listener/filter is unnecessary |
| Servlet/JSF request bypasses `DispatcherServlet` | Needs properly mapped `RequestContextListener` or `RequestContextFilter` |
| Directly injecting unproxied `@Scope("request")` into an eager singleton | Target may be resolved before any request exists; use `@RequestScope` with proxy or `ObjectProvider` |
| Storing a mutable session bean with two parallel HTTP requests in the same session | Same instance can be accessed concurrently; prevent race conditions |
| Launching a background task from a request and using a scoped proxy after the response ends | Cannot rely on the old request context; pass immutable data needed into the task |
| Test creates a plain Spring context and calls a request bean | Use `MockHttpServletRequest` + `ServletRequestAttributes` for controlled unit tests, or integration tests with proper Spring MVC infrastructure |
| Using reactive Spring WebFlux | Do not copy Servlet thread-binding assumptions; use context and bean lifecycle mechanisms suited to WebFlux/Reactor |

### Watch out for thread pools, async, and ThreadLocal

`RequestContextHolder` typically binds request attributes to the processing thread. Spring MVC supports various async dispatch flows with mechanisms to re-establish context appropriately, yet **do not infer that every `CompletableFuture`, `ExecutorService`, scheduler, or new thread automatically carries the request context**.

`RequestContextFilter` has a `threadContextInheritable` option; it defaults to `false`. Setting it to `true` indiscriminately is especially dangerous with thread pools that reuse threads: request data from one job can be retained or leaked into another job. Instead of passing a request-bound bean across threads, pass a DTO/needed values; if context propagation is required, choose a Spring-supported mechanism matching the async model.

### One error with two different root causes

**Unregistered scope error** (such as `No Scope registered for scope name 'request'`) means you are using a context/bean factory where web scopes have not been set up.

**Registered yet inactive scope error** (such as `Scope 'request' is not active for the current thread`) means the scope is known, yet request attributes are missing at the access time/thread. Both can surface as `BeanCreationException` when Spring creates a bean; read the **root cause** to choose the right fix.

## 8. Implementation and testing checklist

1. Determine whether the app is **Servlet MVC** or **reactive WebFlux**; this lesson focuses on Servlet MVC.
2. Confirm the container uses a web-aware `ApplicationContext` and the Servlet environment is validly configured.
3. Choose `@RequestScope`, `@SessionScope`, or `@ApplicationScope` matching the desired lifetime; use `websocket` only with corresponding support.
4. For requests via `DispatcherServlet`: use the built-in setup. For processing paths outside the dispatcher: register and map `RequestContextListener` or `RequestContextFilter` with the right scope.
5. When injecting web-scoped beans into singletons: use a scoped proxy or provider/lazy lookup; do not resolve targets in init constructors/schedulers lacking a request.
6. Test two independent HTTP requests, two requests in the same session, and a request from a client without cookies; observe instances reused per their scopes.
7. Test paths outside the dispatcher, async jobs, and thread pools; handle missing context or pass required data properly.
8. If it fails, check **whether the right context registered the scope**, then **whether the right thread/request has request attributes**.

## 9. Self-check questions

**Question:** Can a `@RequestScope` bean be created using `AnnotationConfigApplicationContext`?  
**Answer:** The annotation does not activate web scopes by itself. A plain Java context has no basis for creating a request-scoped target bean; you must use a web-aware environment or configure an appropriate `Scope` in isolated tests.

**Question:** When running Spring MVC, must you always add `RequestContextListener`?  
**Answer:** No. `DispatcherServlet` automatically binds the request context for requests it handles. A listener/filter is considered when handling Servlet requests outside the dispatcher.

**Question:** Why can a singleton controller still inject a request bean?  
**Answer:** Because `@RequestScope` uses a scoped proxy by default. The singleton holds the proxy, while the target is resolved when invoked during the current request.

**Question:** Does successful startup guarantee that a request bean can be called from everywhere?  
**Answer:** No. Request scope is only active inside an appropriate request-processing environment, not automatically active in schedulers, background workers, or during startup.

**Question:** Does `application` mean shared across pods/JVMs?  
**Answer:** No. This scope is tied to the `ServletContext` of one web application, not a distributed store.

## Official References

- Spring Framework Reference – [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html), especially the "Request, Session, Application, and WebSocket Scopes" and "Initial Web Configuration" sections.
- Spring Framework Reference – [DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html).
- Spring Framework Javadoc – [RequestContextFilter](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/filter/RequestContextFilter.html).

