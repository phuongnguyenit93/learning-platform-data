# ScopeNotActiveException When a Scope Is Not Active in Spring Framework

## 1. Context: A Scoped Bean Without an Active Context

The Spring Core Container can manage beans belonging to `singleton`, `prototype`, and web-bound scopes such as `request`, `session`, and `application`. A bean being **registered** successfully does not mean its scope is **active at all times and on every thread**.

For example, `@RequestScope` requires a current HTTP request. When a singleton service invokes a method on a request-scoped proxy from an `ApplicationRunner` at application startup, from `@Scheduled`, or from a background thread without a request context, Spring usually cannot find the target request bean and throws `ScopeNotActiveException`.

Lesson objectives:

- Understand precisely when `ScopeNotActiveException` occurs and at which layer it is raised.
- Distinguish a **registered scope** from an **active scope**; distinguish scope, bean definition, target bean, and scoped proxy.
- Trace `Caused by` to diagnose missing request context, premature bean invocation, thread switching, or improper web configuration.
- Reproduce the error with a runnable Spring Boot/Java 17 example, contrasting access outside an HTTP request versus inside a controller.
- Apply fixes tailored to the cause: adjust invocation timing, extract data inside the request and pass it to background tasks, use `ObjectProvider` in the right place, or configure `RequestContextListener`/`RequestContextFilter` when genuinely needed.
- Avoid wrong fixes such as manual `ThreadLocal` hacks, copying servlet requests onto arbitrary threads, or switching beans to singleton just to silence the error.

The primary focus is **Spring Framework Servlet/MVC** with web scopes and cross-lifecycle bean dependencies. Spring WebFlux uses a separate reactive context model, noted at the end.

## 2. What Is `ScopeNotActiveException`?

`org.springframework.beans.factory.support.ScopeNotActiveException` is a subtype of `BeanCreationException`, introduced in Spring Framework 5.3 to report that **a bean's target scope is not active**, such as request/session scope. When Spring requests a target bean from a registered scope that cannot operate in the current context, this exception can be thrown.

A stack trace typically resembles:

~~~text
org.springframework.beans.factory.support.ScopeNotActiveException:
Error creating bean with name 'scopedTarget.requestToken':
Scope 'request' is not active for the current thread;
consider defining a scoped proxy for this bean if you intend
to refer to it from a singleton

Caused by: java.lang.IllegalStateException:
No thread-bound request found: Are you referring to request
attributes outside of an actual web request, or processing a
request outside of the originally receiving thread?
~~~

This is an **abbreviated, illustrative example**. Exact message wording, bean names, and stack frames can vary across Spring versions and configurations.

Clues to read:

- `ScopeNotActiveException`: Spring is requesting the target bean of an inactive scope.
- `scopedTarget.requestToken`: when a scoped proxy is present, the actual target bean may be named by Spring with the `scopedTarget.` prefix; the exact name depends on the bean definition.
- `Scope 'request' is not active for the current thread`: at lookup time, the current thread has no valid request attributes for request scope.
- `Caused by: No thread-bound request found`: the direct cause typically lies at `RequestContextHolder.currentRequestAttributes()`, not a missing Java dependency.
- The phrase "consider defining a scoped proxy" is a generic hint in the exception; **even when a proxy already exists**, you can still receive that message if the proxy is invoked outside a request.

**Do not blindly catch the exception and return a default value**. If business logic truly requires HTTP request data, this error usually indicates that the execution flow is using the wrong context or has outlived the request lifecycle.

## 3. A Registered Scope Differs from an Active Scope

Two independent conditions must be satisfied:

| Condition | Meaning | When missing |
| --- | --- | --- |
| **Registered scope** | `BeanFactory` knows how to obtain beans belonging to `request`, `session`, or a custom scope | Can report `IllegalStateException: No Scope registered for scope name 'request'` |
| **Active scope** | At lookup time a valid context exists, e.g. `RequestAttributes` bound to the thread handling an HTTP request | Can report `ScopeNotActiveException` with root cause "No thread-bound request found" |

`@RequestScope` or `@Scope("request")` declares **the bean's scope**; it does not create an HTTP request or activate a request context for background code.

Example scenarios:

| Execution location | Is request scope available? | Notes |
| --- | --- | --- |
| Spring MVC controller handling a request via `DispatcherServlet` | Typically **yes** | `DispatcherServlet` provides request attributes |
| Singleton service called synchronously by a controller on the same request thread | Typically **yes** | Scoped proxy/lookup uses the active request |
| Singleton constructor or `@PostConstruct` at startup | Typically **no** | Creating a singleton does not mean an HTTP request exists |
| `ApplicationRunner`/`CommandLineRunner` | Typically **no** | Even though the embedded server has started |
| `@Scheduled` | Typically **no** | Task runs on a scheduler thread |
| `@Async` or `CompletableFuture.supplyAsync` | **Not available by default** | Execution may switch to an executor thread |
| Controller instantiated directly with `new` in a unit test | No automatic request context | Bypasses Spring MVC test infrastructure |
| Servlet/filter outside `DispatcherServlet` | Depends on configuration | May require `RequestContextFilter`/`RequestContextListener` |

"Typically" here reflects standard Spring MVC configuration; custom scopes, custom thread binding, and asynchronous dispatch can alter details. Do not infer an active scope merely from being in the same JVM or application.

### Difference Between "Not Active" and "Not Registered"

In a non-web `AnnotationConfigApplicationContext`, if you define a bean in `request` scope and try to retrieve it, the container may report that the scope is **not registered**. That is a container configuration issue.

In a Servlet web application, `request` scope may be fully registered yet still **not active on a worker thread**. That is an access-time context issue.

The two situations need different fixes: use an appropriate context to **register the scope**, or perform lookups within a context where the scope is active.

## 4. Mechanism: From Scoped Proxy to Exception

Suppose a request-scoped bean is injected into a singleton:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestToken {
    public String value() {
        return "Token for the current request";
    }
}
~~~

~~~java
import org.springframework.stereotype.Service;

@Service
public class TokenService {
    private final RequestToken token;

    public TokenService(RequestToken token) {
        this.token = token;
    }

    public String inspect() {
        return token.value();
    }
}
~~~

These are **two illustrative class files** in a Spring MVC application with component scanning. The `@RequestScope` annotation defaults to creating a `TARGET_CLASS` scoped proxy in Spring Framework 6.x, so the singleton `TokenService` holds a proxy rather than pinning one request's target.

Sequence when calling `TokenService.inspect()`:

~~~text
Singleton TokenService
       |
       | token.value()
       v
Request-scoped proxy
       |
       | look up target bean in "request" scope
       v
Spring RequestScope
       |
       +-- RequestAttributes bound to thread?
               |
               +-- Yes --> target bean of current request
               |                |
               |                '--> value() succeeds
               |
               '-- No --> IllegalStateException
                                  |
                                  v
                         ScopeNotActiveException
~~~

Key point: **the proxy defers lookup until invocation time**, but the proxy **does not create a request context**. When accessed from a thread without a request, the proxy fails as well.

If `@RequestScope` is replaced with `@Scope("request")` without enabling a proxy, the singleton may try to resolve the target during construction; the result can still be `ScopeNotActiveException` occurring **earlier**, such as at startup. With `@RequestScope` having a proxy, startup can succeed and the error only appears when a method needing the target is called outside a request.

## 5. Complete Spring Boot Example: Reproducing the Error and Valid Access

The example below runs on **Java 17+**, **Spring Boot 3.3.5** (Spring Framework 6.1.x), using Servlet/Spring MVC. An `ApplicationRunner` deliberately accesses the request-scoped bean outside an HTTP request and catches the exact exception to illustrate it. The same singleton service succeeds when an actual HTTP request reaches the controller.

### 5.1. Project Structure

~~~text
scope-not-active-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── scope/
                        └── ScopeNotActiveDemo.java
~~~

### 5.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>scope-not-active-demo</artifactId>
    <version>1.0.0</version>

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
~~~

### 5.3. `ScopeNotActiveDemo.java`

~~~java
package com.example.scope;

import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.support.ScopeNotActiveException;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.annotation.RequestScope;

@SpringBootApplication
public class ScopeNotActiveDemo {

    public static void main(String[] args) {
        SpringApplication.run(ScopeNotActiveDemo.class, args);
    }

    @Component
    @RequestScope
    public static class RequestToken {
        private final String id = UUID.randomUUID().toString();

        public String id() {
            return id;
        }
    }

    @Service
    public static class TokenService {
        private final RequestToken token;

        public TokenService(RequestToken token) {
            this.token = token; // Request-scoped proxy is injected.
        }

        public String tokenId() {
            return token.id(); // Target is resolved on actual invocation.
        }
    }

    @Component
    public static class StartupProbe implements ApplicationRunner {
        private final TokenService service;

        public StartupProbe(TokenService service) {
            this.service = service;
        }

        @Override
        public void run(ApplicationArguments args) {
            try {
                service.tokenId();
                System.out.println("outside-request: unexpected success");
            } catch (ScopeNotActiveException ex) {
                System.out.println(
                    "outside-request: ScopeNotActiveException");
            }
        }
    }

    @RestController
    public static class TokenController {
        private final TokenService service;

        public TokenController(TokenService service) {
            this.service = service;
        }

        @GetMapping("/token")
        public Map<String, Object> token() {
            String first = service.tokenId();
            String second = service.tokenId();

            return Map.of(
                "sameWithinRequest", first.equals(second),
                "tokenId", first
            );
        }
    }
}
~~~

All nested bean classes are `public static` so Spring component scanning can detect them independently in a single source file. `TokenService` is a default singleton; `RequestToken` is the request-scoped target. `StartupProbe` runs after the application boots, **outside any HTTP request**, so accessing `service.tokenId()` has no request target.

### 5.4. Running the Application

Install JDK 17+ and Maven 3.9+, and in the directory containing `pom.xml` run:

~~~bash
mvn spring-boot:run
~~~

In the logs when `ApplicationRunner` runs, the stdout line printed by the program itself:

~~~text
outside-request: ScopeNotActiveException
~~~

Spring Boot/Maven logs appear around that line depending on configuration and environment. If the environment were customized to bind request attributes to runners, behavior could differ, but in standard Servlet Boot configuration runners have no HTTP request.

In another terminal, call:

~~~bash
curl -s http://localhost:8080/token
~~~

The JSON response looks like:

~~~json
{
  "sameWithinRequest": true,
  "tokenId": "UUID-generated-for-request"
}
~~~

**This is a format example, not a JSON literal with a fixed UUID.** The `tokenId` value is a real UUID and JSON field order may vary; `sameWithinRequest` is `true` because both calls within the same request share the same target.

Call the endpoint again:

~~~bash
curl -s http://localhost:8080/token
~~~

The next request receives a new `tokenId` (barring an astronomically small UUID collision). Thus **the same singleton service behaves differently depending on where it is called**, because request scope is resolved according to the HTTP request on the current thread.

### 5.5. Why Catch the Exception in the Runner so the Application Keeps Running?

The example deliberately catches `ScopeNotActiveException` in `StartupProbe` so the application continues serving `/token`. In a real program, leaving an exception uncaught in a startup runner can cause Spring Boot startup to fail. Catching here is **for illustration only**; catching and ignoring exceptions in normal business flows is not recommended.

## 6. Common Causes

### 6.1. Using a Request/Session Bean Too Early During Singleton Initialization

~~~java
@Service
public class EarlyService {
    public EarlyService(RequestToken token) {
        // Inside a singleton created at startup:
        // Even with a scoped proxy, the call below needs a target right away.
        System.out.println(token.id());
    }
}
~~~

This is **illustrative code** depending on `RequestToken` from section 5. When the singleton is created before an HTTP request exists, the constructor calls `token.id()` and triggers scoped proxy lookup while the scope is inactive. `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and other bean initialization callbacks can cause the same issue.

Fix: keep the proxy reference in a field, but **only call methods requiring request state when actually handling a request**. If startup tasks do not need request info, decouple them from request-specific dependencies.

### 6.2. Missing Scoped Proxy When Injecting a Short-Lived Dependency into a Singleton

~~~java
@Component
@Scope("request")
class RawRequestState {
}
~~~

With this declaration, there is no default proxy creation like `@RequestScope`. When a singleton injects the bean directly, the container may try to instantiate the target at startup and fail with an inactive-scope error.

Fix: use `@RequestScope`, or declare explicitly:

~~~java
@Component
@Scope(
    value = "request",
    proxyMode = ScopedProxyMode.TARGET_CLASS
)
class RequestState {
}
~~~

These are two **separate example bean definitions** (do not put both on the same class); imports for `Component`, `Scope`, and `ScopedProxyMode` are required. Enabling a proxy solves **injection timing**, not the validity of calling the target outside a request.

### 6.3. Calling Inside Background Tasks, Schedulers, or Startup Events

Common entry points:

- `@Scheduled` in a singleton service.
- `ApplicationRunner`/`CommandLineRunner` or `ApplicationReadyEvent` listeners.
- Queue job workers.
- Message listeners outside a Servlet request.
- Executors running deferred work after an HTTP response finishes.

Do not inject `@RequestScope` beans into such tasks and call them as though a request context were always present. Decouple request-only dependencies; pass the needed business data into the job as an ordinary DTO/record.

### 6.4. Thread Switching via `@Async` or `CompletableFuture`

Request attributes in Servlet MVC are typically bound to the thread handling the request. An independent executor thread does not automatically inherit `RequestAttributes` from the request thread.

~~~java
// Illustrative code placed inside an HTTP request-handling method.
CompletableFuture<String> future = CompletableFuture.supplyAsync(
    () -> requestToken.id()
);
~~~

Even though the closure captures a reference to `requestToken`, that reference is usually a **scoped proxy**, and when the task executes in the common pool, the proxy must look up the target on the **task's thread**, where no request may exist. The result can be `ScopeNotActiveException`.

Do not assume that "still being inside the request when creating the future" makes the future valid. `@Async` also requires inspecting the specific executor/propagation setup; there is no default guarantee of inheriting web request scope.

### 6.5. Servlet Requests Not Passing Through `DispatcherServlet`

Spring MVC's `DispatcherServlet` normally binds request attributes for the request-handling thread. However, a Servlet application may receive requests via a servlet/filter or other integration **outside `DispatcherServlet`'s path**. If that code needs to access Spring web-scoped beans, an appropriate mechanism to expose the request context is needed.

Spring provides `RequestContextListener` and `RequestContextFilter` for this case. Register them depending on the environment; do not add both out of habit when a standard Spring MVC application already works.

### 6.6. Tests Not Creating an HTTP Request Context

In a plain unit test:

~~~java
TokenService service = /* singleton initialized in the test */;
service.tokenId(); // Can fail if no request scope is active.
~~~

This is illustrative code, not standalone runnable. Creating a bare `ApplicationContext` is not equivalent to an HTTP request. To test real behavior in Spring MVC, use `MockMvc` with a web test context, or set up `MockHttpServletRequest`/`RequestContextHolder` in a controlled manner when unit-testing a service that uses request context. Clean up afterward to avoid leaking `ThreadLocal` state into other tests.

## 7. Fixing Properly Based on Where Code Executes

### Case A: Logic Belongs to an HTTP Request

For synchronous controllers/services inside a Spring MVC request, keep `@RequestScope` (or `@SessionScope`) and use the target only on the request-processing flow:

~~~java
@RestController
class RequestController {
    private final TokenService service;

    RequestController(TokenService service) {
        this.service = service;
    }

    @GetMapping("/inspect")
    String inspect() {
        return service.tokenId();
    }
}
~~~

This snippet only illustrates controller design; do not add it to the application in section 5 unless you want the `/inspect` endpoint. It relies on `TokenService` already registered with Spring.

### Case B: Logic Runs in the Background — Extract Data Before Switching Threads

Instead of letting an async task access a scoped proxy, read the required data **inside the HTTP request**, then pass an immutable snapshot to the task.

~~~java
// Java 17 record: contains only data needed for the background job.
public record JobContext(String requestId, String operation) {
}
~~~

~~~java
// Inside a method invoked from a valid HTTP request:
String requestId = requestToken.id();
JobContext snapshot = new JobContext(requestId, "export");

// Worker uses the snapshot, not the RequestToken scoped proxy.
CompletableFuture<String> future = CompletableFuture.supplyAsync(
    () -> snapshot.operation() + ":" + snapshot.requestId()
);
~~~

These two snippets are **illustrative code**, requiring importing `CompletableFuture`, an injected `requestToken` variable, and an application-appropriate thread executor. `JobContext` can be a standalone record and does not need to be a Spring bean.

Advantages:

1. The worker receives only explicit values without looking up request attributes.
2. Independent of which thread executes it.
3. The DTO can be persisted or enqueued as needed.
4. Easy to audit what data is allowed to cross the request/background boundary.

Snapshot only the data genuinely needed and safe to retain. Never place raw `HttpServletRequest`, `HttpSession`, or mutable request-scoped beans into a queue for use after the request ends.

### Case C: Only Wanting to Defer Bean Retrieval — Use `ObjectProvider`

~~~java
@Service
class RequestReadingService {
    private final ObjectProvider<RequestToken> provider;

    RequestReadingService(ObjectProvider<RequestToken> provider) {
        this.provider = provider;
    }

    String inspect() {
        return provider.getObject().id();
    }
}
~~~

This is an illustrative class; it requires `import org.springframework.beans.factory.ObjectProvider;` and matching Spring imports. `ObjectProvider` is useful because the container does not have to fetch the target when the singleton is created. However, **`provider.getObject()` still requires an active request scope** at call time.

**Important misconception:** `ObjectProvider.getIfAvailable()` is not a cure-all for scope errors. It handles the absence of a matching bean according to the API's semantics, rather than guaranteeing a `null` return instead of an exception when the scope exists but is inactive. If a request-scoped target is accessed outside a request, the context issue must still be fixed properly.

### Case D: Having to Handle Servlet Requests Outside Spring MVC

In a Servlet application with valid requests handled outside `DispatcherServlet`, you can configure one of two options:

**RequestContextListener** — example registration via Servlet `web.xml`:

~~~xml
<listener>
    <listener-class>
        org.springframework.web.context.request.RequestContextListener
    </listener-class>
</listener>
~~~

**RequestContextFilter** — example configuration via Spring Boot Servlet registration:

~~~java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.filter.RequestContextFilter;

@Configuration(proxyBeanMethods = false)
public class RequestBindingConfig {
    @Bean
    FilterRegistrationBean<RequestContextFilter> requestContextFilter() {
        FilterRegistrationBean<RequestContextFilter> bean =
            new FilterRegistrationBean<>(new RequestContextFilter());
        bean.addUrlPatterns("/*");
        return bean;
    }
}
~~~

The `RequestBindingConfig` snippet is a standalone Spring Boot Servlet configuration; add it **only when genuinely needed** to process requests outside the default path. This is not a way to make a job without an HTTP request magically have a request context. Filter/listener registration must match servlet mappings, dispatch types, and your actual environment.

**In standard Spring MVC**, `DispatcherServlet` already exposes request attributes; before registering an extra filter/listener, confirm whether binding is actually missing during a valid request.

## 8. Why Shouldn't You Arbitrarily "Copy Request Context" to a New Thread?

Some workarounds circulating online grab:

~~~java
RequestAttributes attrs = RequestContextHolder.getRequestAttributes();
~~~

and then call `RequestContextHolder.setRequestAttributes(attrs)` inside an executor thread. This approach carries risks:

- Request objects/attributes managed by the Servlet container have finite lifetimes; the background task may run **after the request has ended**.
- Many request attributes, session attributes, and related objects are **not designed for concurrent access** from arbitrary threads.
- Failing to reset `RequestContextHolder` in a thread pool can leak one request's values into another request.
- `RequestContextHolder.setRequestAttributes(..., true)` uses an inheritable thread-local in some cases, yet thread pools reuse threads and can inherit stale contexts improperly. Do not use it as a default fix.
- A copied context does not extend the real request lifetime, guarantee thread-safety, or automatically establish proper transactional/security contexts.

If the framework provides an official async request model, use the mechanism supported within that lifecycle; for independent, longer-running background work, **explicitly passing the needed data** is usually much safer to control.

## 9. Session Scope Can Also Fail Without an HTTP Request

`@SessionScope` manages beans per `HttpSession`. Having a session in the browser **does not mean** a background thread has the context to access the current request's session.

~~~java
@Component
@SessionScope
public class SessionPreferences {
    private String language = "vi";

    public String getLanguage() {
        return language;
    }
}
~~~

This is an illustrative class requiring `Component` and `SessionScope` imports. If a background task invokes the scoped proxy of `SessionPreferences` on a thread lacking request attributes, it can also encounter `ScopeNotActiveException`. `@SessionScope` does not turn the HTTP session into a global data store accessible at will from any thread.

If a background task needs a preference, extract `language` when receiving the request, validate it, and pass the value to the job. If data needs long-term or cross-server access, use a proper storage backend (DB/session store) with appropriate identifiers and access control.

`@ApplicationScope` has `ServletContext` lifetime and usually depends less on request threads, though it still requires a suitable web application context. Never switch a request/session state bean to application scope just to silence an error: doing so can cause **cross-user data sharing**.

## 10. Testing the Failure and the Fix Without Fragile Log Parsing

Two testing layers should be distinguished:

1. **Out-of-request test:** verify that accessing the scoped target in a requestless context genuinely fails as expected.
2. **In-HTTP-request test:** verify that the same scoped proxy reaches its target when routed through web request infrastructure.

Integration test example with the Maven dependency `spring-boot-starter-test`, placed in `src/test/java/com/example/scope/ScopeNotActiveDemoTest.java`. Add the test dependency to `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Test class:

~~~java
package com.example.scope;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.ScopeNotActiveException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.request.RequestContextHolder;

@SpringBootTest
@AutoConfigureMockMvc
class ScopeNotActiveDemoTest {

    @Autowired
    private ScopeNotActiveDemo.TokenService service;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void outsideHttpRequest_failsToResolveRequestScopedTarget() {
        RequestContextHolder.resetRequestAttributes();

        assertThatThrownBy(service::tokenId)
            .isInstanceOf(ScopeNotActiveException.class);
    }

    @Test
    void insideHttpRequest_resolvesTargetAndReusesIt() throws Exception {
        mockMvc.perform(get("/token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sameWithinRequest").value(true))
            .andExpect(jsonPath("$.tokenId").isNotEmpty());

        assertThat(service).isNotNull();
    }
}
~~~

The test uses `MockMvc` to simulate a web request environment so the controller runs and verifies the target. The first test intentionally ensures no request context exists before calling `service.tokenId()`; the second test goes through `MockMvc`. In a real test suite, ensure test isolation and clean up request attributes if any other code sets them manually.

Run command:

~~~bash
mvn test
~~~

This is an integration test example for the application in section 5, using JUnit Jupiter/AssertJ/MockMvc provided by `spring-boot-starter-test`. The observable outcome is **two passing tests**; no fixed Maven stdout line is guaranteed because test runner output varies by plugin and environment.

## 11. Diagnostic Workflow for `ScopeNotActiveException`

When encountering this exception in a real application, answer in order:

**Step 1 — Identify the bean and scope.** Find the bean name in the exception, noting any `scopedTarget.` prefix; locate the corresponding `@RequestScope`, `@SessionScope`, `@Scope(...)`, or programmatic bean definition.

**Step 2 — Read down to the root cause.** `No thread-bound request found` usually indicates missing request attributes. If you see `No Scope registered for scope name ...`, the bean factory context has not registered the scope at all, which differs from a request lost across threads.

**Step 3 — Identify where the call starts.** Controller via `DispatcherServlet`? Singleton constructor? `@PostConstruct`? `ApplicationRunner`? `@Async`? Scheduler? Message listener? Event handler? One controller calling a service does not guarantee calls to that service from other entry points have a request.

**Step 4 — Locate thread switches.** Trace `CompletableFuture`, `ExecutorService`, `@Async`, reactive publishers, or delayed callbacks. Pay attention to where **methods are called on** the bean proxy, not just where the proxy is injected.

**Step 5 — Inspect the proxy or provider.** If the exception happens at startup, check whether a request-scoped dependency is being resolved directly before any request. If startup succeeds but runtime fails, inspect **the moment the proxy/provider looks up the target**.

**Step 6 — Choose a fix based on business semantics.** Request-only logic stays inside the request; background logic receives an immutable snapshot/ID/data; requests outside `DispatcherServlet` configure proper binding; non-web contexts need container changes or dependency redesign.

**Step 7 — Write tests reproducing the exact behavior.** One out-of-request test and one HTTP request test prevent "fixed startup, still broken in background."

### Error Differentiation Table

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `ScopeNotActiveException` when `ApplicationRunner` calls a service | No HTTP request at startup | Avoid accessing request targets in runners |
| `ScopeNotActiveException` in `@Async` | Executor thread has no request attributes | Copy needed data before submitting the task |
| `ScopeNotActiveException` in a singleton constructor | Request target resolved too early, or scoped proxy called too early | Use scoped proxy/provider and defer **target calls** until a request |
| "No thread-bound request found" in a special Servlet request | Bypassed `DispatcherServlet`'s binding path | Evaluate `RequestContextFilter`/`RequestContextListener` |
| "No Scope registered for scope name 'request'" | Plain Java container has not registered web scopes | Use an appropriate web-aware context |
| Job accesses `@SessionScope` and fails | Having a session ID does not mean request binding exists on the thread | Pass preferences/IDs into the job |
| Still fails at runtime after enabling proxy | Proxy resolves injection, but target still needs an active scope | Check method call sites and which thread runs them |
| Data leaks across users after changing scope | Picked singleton/application to silence request-scope error | Restore data boundaries; put state in the proper scope/storage |

## 12. Common Misconceptions to Avoid

### Scoped Proxies Do Not Create a New Context

`@RequestScope` defaults to `ScopedProxyMode.TARGET_CLASS`. Proxies allow a long-lived bean (such as a singleton) to hold a stable reference to a short-lived bean, but cannot turn a background thread into an HTTP request thread.

### `ObjectProvider` Defers Lookup; It Does Not Exempt Scope Rules

`ObjectProvider<RequestToken>` can be injected into a singleton successfully; calling `getObject()` outside a request can still throw `ScopeNotActiveException`. Merely deferring lookup is **not enough** if no scope is active at that later moment either.

### `@Lazy` Does Not Turn Request Scope into Singleton

`@Lazy` can defer initialization or create a lazy proxy at certain injection points, yet does not remove the requirement for a request context when the target belongs to `request` scope. Do not use `@Lazy` as a universal workaround for missing scopes.

### Not Every Bean Exception Is Caused by Scope

`NoSuchBeanDefinitionException` reports a missing matching bean definition; `UnsatisfiedDependencyException` usually indicates dependency assembly failure; `BeanCurrentlyInCreationException` can involve circular dependencies. `ScopeNotActiveException` is identified by **an inactive scope** and its corresponding root cause. It is a subtype of `BeanCreationException`, so read the entire cause chain.

### Do Not Apply Servlet `ThreadLocal` Assumptions Directly to WebFlux

Spring WebFlux uses a reactive pipeline that can switch threads and manages context via Reactor Context. Patterns that attach servlet requests to threads via `RequestContextHolder` are not a general-purpose mechanism for carrying metadata through reactive chains. When using WebFlux, follow `ServerWebExchange`/reactive context mechanisms and the scopes/capabilities supported by your application instead of copying MVC fixes verbatim.

## 13. Check Questions

**Question 1:** Why does injecting a `@RequestScope` bean into a singleton succeed, yet calling a method on it from `ApplicationRunner` throws `ScopeNotActiveException`?

**Answer:** Specialized annotations typically create a proxy, so no real target is needed at injection time. When the runner invokes a method, the proxy must resolve the target; the runner has no current HTTP request, so request scope is not active.

**Question 2:** Does switching from injecting `RequestToken` to injecting `ObjectProvider<RequestToken>` guarantee that `getObject()` works inside `@Scheduled`?

**Answer:** No. The provider defers lookup, yet the scheduler thread still typically lacks a request context. You must redesign the data/job flow or lookup site.

**Question 3:** Can you create a `@RequestScope` bean inside a plain Java `AnnotationConfigApplicationContext` and use it like an ordinary web bean?

**Answer:** Not out of the box. A plain application context does not register default web scopes. An unregistered-scope error differs from a web-aware context that has registered request scope while the current thread lacks request attributes.

**Question 4:** In a service called by a controller, if you want to run a report export after returning the HTTP response, should you keep the `HttpServletRequest` or pass a DTO containing the needed info?

**Answer:** Pass a DTO/data snapshot of what is needed while the request is still valid. Background workers should not depend on the lifecycle of a servlet request or scoped proxy.

**Question 5:** Why can changing `RequestToken` from `@RequestScope` to `@ApplicationScope` to silence the error be dangerous?

**Answer:** It changes the data boundary from per-HTTP-request to shared across the entire web application. Request/user-specific data can be shared across requests/users, violating business requirements.

## 14. Official Documentation for Cross-Reference

- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): web-aware application contexts, enabling request binding, scoped proxies, and `ObjectProvider`.
- [`ScopeNotActiveException` Javadoc (Spring Framework 6.1)](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/beans/factory/support/ScopeNotActiveException.html): relationship to `BeanCreationException` and exception semantics.
- [`RequestScope` Javadoc (Spring Framework 6.1)](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/context/request/RequestScope.html): need for thread-bound `RequestAttributes` and provisioning mechanism.
- [`RequestContextHolder` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html): how Spring stores current request attributes; distinction between `getRequestAttributes()` and `currentRequestAttributes()`.
- [`@RequestScope` Annotation Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/context/annotation/RequestScope.html): default `proxyMode`.
