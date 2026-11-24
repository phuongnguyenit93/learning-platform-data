# WebAsyncManagerIntegrationFilter and Spring MVC Callable Integration in Spring Security Servlet

## 1. Problem: SecurityContext Is Thread-Bound, While Callable Runs on Another Thread

In a Spring Security **Servlet** (Spring MVC) application, the current request's login information is usually accessed via `SecurityContextHolder`:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

The snippet above is merely a **Java fragment depending on Spring Security**, not a standalone program. `Authentication` can contain the principal, authorities, and authentication status of the current request. The default storage mechanism of `SecurityContextHolder` is **`ThreadLocal`**, meaning the same holder value does not automatically appear on any other thread.

For synchronous requests, the processing chain typically stays on one Servlet thread. For a controller returning `java.util.concurrent.Callable<T>`, Spring MVC may execute the work on a different executor thread. Without a context bridge, reading `SecurityContextHolder` **inside the `Callable`** may not see the authentication from the initial request.

Spring Security provides **`WebAsyncManagerIntegrationFilter`**, bridging Spring MVC asynchronous request processing with Spring Security. In a standard filter chain configuration, this filter registers **`SecurityContextCallableProcessingInterceptor`** with the request's **`WebAsyncManager`**. The interceptor transfers the appropriate SecurityContext to the thread executing the `Callable` and clears the holder upon completion, enabling controllers/services to enforce caller-based protection.

### Usage Example

User Alice with the `REPORT_READ` authority calls:

~~~http
GET /api/async/report HTTP/1.1
Host: api.example.test
Authorization: Basic <illustrative-credentials>
~~~

The controller returns a `Callable` to run a relatively slow calculation, while the service is protected with `@PreAuthorize("hasAuthority('REPORT_READ')")`. When the `Callable` runs on a worker thread, the service needs to see Alice's identity/permissions. If context is lost, authorization checks can falsely deny access; if another user's context remains on the thread pool, a serious security bug can occur.

**Key point:** Spring Security brings the **security context** into a Spring MVC-managed `Callable`; this **does not** mean every Thread, `CompletableFuture`, `@Async`, or background job receives automatic context propagation.

## 2. Key Components to Understand

| Component | Role |
| --- | --- |
| `SecurityContextHolder` | Provides the thread-bound SecurityContext per its strategy, defaulting usually to ThreadLocal |
| `SecurityContext` | Holds the request's `Authentication`, not a request or session object |
| `SecurityContextHolderFilter` / equivalent context mechanism | Loads and sets the context for the request thread per Spring Security config, then clears it by lifecycle |
| `FilterChainProxy` | Runs the security filters matching the request |
| `WebAsyncManagerIntegrationFilter` | Registers SecurityContext integration with Spring MVC's `WebAsyncManager` |
| `WebAsyncManager` | Coordinates Spring MVC async requests, supporting `Callable` and callbacks |
| `SecurityContextCallableProcessingInterceptor` | Captures the request-side SecurityContext, sets it on the worker thread while Callable runs, and clears it afterward |
| `AsyncTaskExecutor` | Executes MVC Callables on worker threads; must be configured for system load |
| Servlet async dispatch | Allows the Servlet request to stay open while the controller returns early, then dispatches the result back into the pipeline |

Class names and filter chain details may vary by version/configuration. This lesson uses **Spring Boot 3.x, Spring Security 6.x, Spring Framework 6.x, Java 17+**. Do not hardcode filter ordering as "always position N", because the security chain also depends on other configurations.

A few common misconceptions:

- **`WebAsyncManagerIntegrationFilter` is not a "secure executor"**. It registers an interceptor for MVC; the executor is still managed by MVC.
- **`SecurityContextCallableProcessingInterceptor` does not create new permissions**. It uses the existing authentication from the request; authorization must still be enforced.
- **`WebAsyncManager` is not synonymous with `WebClient` or Reactor Context**. This is a **Spring MVC Servlet** mechanism, not Spring WebFlux reactive security.
- **Session, SecurityContext, and ThreadLocal are three distinct concepts**. Data may be persisted in the session, but when a Callable runs on a worker, the context must be set properly on that thread.
- **Being able to read the principal does not mean the operation is authorized**. If a sensitive operation needs a specific authority, policy must be enforced at the URL and/or method/service level.

## 3. Execution Flow of a Controller Returning Callable

Suppose MVC is configured to use a thread pool to run `Callable<Map<String, String>>`. The conceptual flow is as follows:

~~~text
Client HTTP GET /api/async/whoami
               │
               ▼
Servlet container: request thread T1
               │
               ▼
Spring Security FilterChainProxy
  - loads SecurityContext / authenticates user
  - WebAsyncManagerIntegrationFilter
      registers SecurityContextCallableProcessingInterceptor
               │
               ▼
Spring MVC DispatcherServlet + Controller (T1)
               │
               └─ return Callable<T> (Callable body has not run yet)
                        │
                        ▼
        WebAsyncManager starts async processing
        interceptor captures appropriate SecurityContext
                        │
                        ▼
        AsyncTaskExecutor: worker thread T2
        interceptor sets SecurityContext on T2
                        │
                        ▼
        Callable.call() reads SecurityContextHolder
        and can call authorization-protected services
                        │
                        ▼
        interceptor clears SecurityContextHolder on T2
                        │
                        ▼
        Spring MVC receives concurrent result
        Servlet async dispatch and renders HTTP response
                        │
                        ▼
                    Client receives result
~~~

**Important order:**

1. The initial request is authenticated/authorized by the security chain on T1.
2. The controller **returns** the Callable object rather than executing heavy work directly on T1.
3. When MVC starts concurrent handling, the interceptor records the SecurityContext associated with the request before T1 exits the initial dispatch.
4. On T2, the interceptor sets the context for the Callable invocation; code inside the Callable can query `SecurityContextHolder` like a properly authenticated request.
5. After the Callable finishes, Spring Security clears the context on T2, preventing thread pool reuse from leaking authentication to the next task.
6. Spring MVC performs an async dispatch to handle the result, exceptions, message conversion, and HTTP response generation.

**It is not T1 "moving the entire ThreadLocal over to T2".** It is a **capture, set, then clear** process via the interceptor. The captured context may contain object references; do not concurrently mutate an `Authentication`/`SecurityContext` used across multiple threads assuming it is an independent deep copy.

In other lifecycle paths (timeout, error, client disconnect), exact behavior depends on MVC, the Servlet container, and the executor. Sensitive operations must have explicit timeout/cancellation policies; never assume an HTTP timeout guarantees the worker has stopped all side effects.

## 4. Runnable Example in Spring Boot 3 / Spring Security 6

### 4.1. Dependencies and Structure

A Spring Boot project using Java 17+ and Spring MVC may need:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

An example file layout:

~~~text
src/main/java/com/example/demo/
  DemoApplication.java
  SecurityConfig.java
  AsyncWhoAmIController.java
  AsyncMvcConfig.java
src/test/java/com/example/demo/
  AsyncSecurityTest.java
~~~

If initialized from a Spring Boot generator, `DemoApplication.java` is the application entry point with `@SpringBootApplication` and `main()`. The following classes are **components of a Spring project**, not standalone programs compiled with plain `javac`.

### 4.2. SecurityFilterChain

File `SecurityConfig.java` illustrates an async endpoint restricted to authenticated users. It uses HTTP Basic for short tests; real applications can replace it with form login, OIDC, JWT, or another method.

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/async/whoami").authenticated()
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Key insight: Spring Security **usually registers `WebAsyncManagerIntegrationFilter` automatically** when building the filter chain for a Servlet application. **Do not manually call `addFilterBefore(new WebAsyncManagerIntegrationFilter(), ...)`** as a fix for lost context; manual misplacement or duplicate filters can cause hard-to-diagnose behavior.

`authenticated()` here protects the incoming request. In real applications, other endpoints must be protected as required; `permitAll()` in the example is **not a general production configuration**.

If a URL is completely excluded from Spring Security via `web.ignoring()` or a custom filter chain does not run through the integration filter, you cannot assume context propagation works like a standard protected MVC path.

### 4.3. Controller Returning Callable and Reading Authentication on Worker

File `AsyncWhoAmIController.java`:

~~~java
package com.example.demo;

import java.util.Map;
import java.util.concurrent.Callable;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AsyncWhoAmIController {

    @GetMapping("/api/async/whoami")
    public Callable<Map<String, String>> whoAmI() {
        // Spring MVC invokes the lambda body on a worker thread.
        // Do not take Authentication from arbitrary request bodies/headers.
        return () -> {
            Authentication auth = SecurityContextHolder
                .getContext().getAuthentication();

            if (auth == null || !auth.isAuthenticated()) {
                throw new AuthenticationCredentialsNotFoundException(
                    "No authenticated SecurityContext in worker");
            }

            return Map.of("principal", auth.getName());
        };
    }
}
~~~

When Alice has authenticated validly, **illustrative** response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"principal":"alice"}
~~~

This is an illustrative body, not output from a live server run. Other HTTP statuses/headers may be added by the container/Spring. The example only displays the principal name to the authenticated user themselves; never return tokens, full authorities, or sensitive account details in responses.

**The core point is that the read occurs inside the lambda.** If the controller reads authentication on T1 and captures the `auth.getName()` string beforehand for the lambda, that example **does not prove** SecurityContext was propagated to T2.

Do not assume "Callable always creates a new Java thread per request": Spring MVC uses an executor and can reuse worker threads. Thus **ThreadLocal cleanup** after the task is critical.

### 4.4. Configuring Executor and Timeout for Spring MVC Callable

Spring MVC allows configuring the executor via `WebMvcConfigurer#configureAsyncSupport`. Under high load, do not rely on the default executor without measuring capacity; use a bounded thread pool and an appropriate timeout.

File `AsyncMvcConfig.java`:

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AsyncMvcConfig {

    @Bean("mvcCallableExecutor")
    ThreadPoolTaskExecutor mvcCallableExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(40);
        executor.setThreadNamePrefix("mvc-callable-");
        // Spring manages @Bean lifecycle, including initialization/shutdown.
        return executor;
    }

    @Bean
    WebMvcConfigurer mvcAsyncConfigurer(
            @Qualifier("mvcCallableExecutor")
            AsyncTaskExecutor executor) {
        return new WebMvcConfigurer() {
            @Override
            public void configureAsyncSupport(
                    AsyncSupportConfigurer configurer) {
                configurer.setTaskExecutor(executor);
                configurer.setDefaultTimeout(15_000L);
            }
        };
    }
}
~~~

The numbers `4/12/40/15_000` are **demo values** only, not recommended tuning parameters for every server. Choose based on CPU/IO, queueing, SLAs, traffic, and downstream connection limits.

**Configuring the executor here does not replace the filter's role**: MVC picks the worker thread; `WebAsyncManagerIntegrationFilter` registers the interceptor so the SecurityContext is present when the Callable runs. Do not configure an unbounded thread pool to evade task rejections; under overload, enforce backpressure, timeouts, appropriate 503/429 responses, and metrics.

Spring MVC async also requires the Servlet container and involved filters to support asynchronous request processing. When writing custom Servlet Filters, check `asyncSupported` and dispatcher types per deployment configuration; do not mistake async dispatch errors for authentication errors.

### 4.5. Method Security Example Running Inside a Callable

A simple example reading the principal is a starting point. In real applications, services performing sensitive work should enforce authorization independently of the controller merely checking `authenticated()`.

With `@EnableMethodSecurity`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

And a service bean called from the lambda:

~~~java
package com.example.demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String loadReport() {
        return "ready";
    }
}
~~~

In the controller, `ReportService` can be injected and invoked **inside the Callable**:

~~~java
@GetMapping("/api/async/report")
public Callable<String> report() {
    return () -> reportService.loadReport();
}
~~~

The last snippet **illustrates a method inside a controller with an injected `reportService` field**; it is not a standalone Java class. When invoked properly through a Spring bean proxy, `@PreAuthorize` evaluates authentication on the worker thread at method execution time. If context is missing, it may be denied; if another user's context remains, that is a critical vulnerability.

Ensure the `/api/async/report` URL in practice also has an appropriate authorization policy; `SecurityConfig` above only protects `/api/async/whoami` to keep the example brief. Do not treat controller-side checks as a reason to omit method-level checks on business logic callable from multiple entry points.

**Do not self-invoke within the same bean expecting `@PreAuthorize` to apply**: proxy-based method security requires calls to pass through a Spring-managed proxy.

## 5. Testing Context Propagation with MockMvc

To test the feature properly, you must **verify data read inside the Callable**, not just a 200 status on the synchronous request. File `AsyncSecurityTest.java` uses Spring Boot Test + Spring Security Test:

~~~java
package com.example.demo;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void callableCanReadOriginalPrincipal() throws Exception {
        MvcResult pending = mvc.perform(
                get("/api/async/whoami").with(user("alice")))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("alice"));
    }

    @Test
    void anonymousRequestDoesNotReachProtectedCallable()
            throws Exception {
        mvc.perform(get("/api/async/whoami"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Test explanation:**

- `user("alice")` is a Spring Security Test post-processor that builds a mock authentication in the test environment; it **does not prove** real password validation. It verifies integration among the security filter chain, MVC async, and SecurityContext.
- `request().asyncStarted()` verifies the handler actually started Servlet asynchronous processing.
- `asyncDispatch(pending)` tells MockMvc to simulate the dispatch cycle after the concurrent result completes; only then does the test inspect the body produced by the Callable.
- It asserts 401 for anonymous requests because the example configures `httpBasic()`. Switching to form login may result in a redirect to login instead of 401.
- The test code must run inside a Boot project containing the application class, security config, controller, and stated dependencies. Do not run directly with `java AsyncSecurityTest` without a build/test runner.
- For real-environment integration tests, properly include proxy, session, cookie, JWT token, or IdP protection; MockMvc does not replace a real browser/container and does not by itself prove thread pool state outside the JVM.

When tests pass using Maven or Gradle, exact output depends on tool versions. Example commands:

~~~bash
./mvnw test
# or
./gradlew test
~~~

Maven projects need `spring-boot-starter-test`/`spring-security-test` accordingly in `pom.xml`; the dependency snippet in section 4.1 uses Gradle. On Windows, you can run `mvnw.cmd test` or `gradlew.bat test`.

### Additional Test Cases

1. Return a `Callable` reading `SecurityContextHolder` on the worker, asserting the exact principal and authorities.
2. Call from user A then user B on the **same pool**; ensure no cross-request leakage even when threads are reused.
3. Test `@PreAuthorize` in a service called from a Callable: allowed when holding the authority, denied when lacking it.
4. Test unauthenticated requests, expired sessions, invalid JWTs, or resource server auth failures right on the initial request.
5. Test timeouts and exceptions inside the Callable; status/error bodies must be safe and must not expose stack traces/tokens.
6. Test many concurrent requests, overloaded worker pools, full queues, and request cancellations; no SecurityContext leaks to subsequent tasks.
7. When customizing multiple `SecurityFilterChain`s, confirm URLs traverse the expected chain and filter integration; do not test only a single endpoint.

## 6. What Is NOT Automatically Propagated?

### 6.1. DeferredResult and CompletableFuture

Spring MVC also has a `DeferredResult<T>` return type. Unlike `Callable`, with `DeferredResult` the developer or an external system usually controls when the result arrives and which thread calls `setResult(...)`. `WebAsyncManagerIntegrationFilter` **has no contract guaranteeing automatic propagation of SecurityContext to arbitrary manually created threads used to complete a DeferredResult**.

Example (contextual illustrative code, not a standalone class):

~~~java
@GetMapping("/api/async/slow")
public DeferredResult<String> slow() {
    DeferredResult<String> result =
        new DeferredResult<>(15_000L);

    executor.execute(() -> {
        // The thread here is arranged by the application itself;
        // do not assume SecurityContextHolder contains the caller.
        result.setResult("done");
    });

    return result;
}
~~~

If code inside the task needs identity for authorization decisions, pass minimal verified data or use an appropriate wrapper/delegating executor (section 7), and **enforce business permissions at the required boundary**. Once data has been authorized in the initial request, it is sometimes better to pass only a pre-authorized command rather than keeping the entire SecurityContext alive in a long-running task.

Similarly, returning `CompletableFuture`, `CompletionStage`, using `@Async`, or calling `ExecutorService.submit(...)` can go through code outside the standard Callable interceptor. Do not apply a blanket rule that "Spring Security handles all async automatically".

### 6.2. Other ThreadLocals, Session, and RequestContextHolder

Even when SecurityContext has been transferred, **any other custom ThreadLocals are not automatically present**: transaction context, MDC/log correlation IDs, tenant resolvers, locale, request-scoped dependencies, or data source routing each have their own lifecycle.

Spring MVC has certain internal mechanisms for request context on framework-managed processing threads, yet **do not infer** that manually spawned custom threads also have `RequestContextHolder` or valid request/response objects. Never pass `HttpServletRequest`/`HttpServletResponse` into a long-running job and keep using them after the response has finished.

### 6.3. Switching ThreadLocal Strategy Is Not a "Turn On Global" Fix

Seeing lost context on an executor, a wrong fix is switching the entire application to:

~~~java
SecurityContextHolder.setStrategyName(
    SecurityContextHolder.MODE_INHERITABLETHREADLOCAL);
~~~

This line is illustrative only and **not recommended** as a general fix. `InheritableThreadLocal` passes values to *newly created threads at inheritance time*, but with a **reused thread pool** it can carry stale context, fail to reflect per-request changes, and leak users. `MODE_GLOBAL` is even more dangerous for multi-user applications. Use scoped propagation mechanisms with explicit cleanup.

## 7. When You Truly Must Run Tasks Outside Spring MVC Callable

When an application needs to run a `Callable` directly on its own `ExecutorService`, Spring Security provides **`DelegatingSecurityContextCallable`**, `DelegatingSecurityContextRunnable`, or `DelegatingSecurityContextAsyncTaskExecutor` to set and clear context around the task.

Excerpt inside a service/controller that holds an `ExecutorService executor` and runs on an authenticated thread:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.Future;
import org.springframework.security.concurrent.DelegatingSecurityContextCallable;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

// Illustrative snippet inside a method with an active SecurityContext:
// ExecutorService executor is initialized and lifecycle-managed elsewhere.
SecurityContext captured = SecurityContextHolder.getContext();

Callable<String> task = () -> {
    var auth = SecurityContextHolder.getContext()
        .getAuthentication();
    if (auth == null) {
        throw new IllegalStateException("Authentication missing");
    }
    return auth.getName();
};

Callable<String> secured =
    new DelegatingSecurityContextCallable<>(task, captured);

Future<String> future = executor.submit(secured);
~~~

This is a **Java snippet to embed in a class/logic with an executor**, not a standalone compilation unit (`import` statements belong at the top of the file). The wrapper manages setting/clearing SecurityContext when the task executes. It does not make auth stronger by itself, does not turn an executor into a safe sandbox, and provides no token revocation mechanism. Evaluate whether you truly need to **retain full identity** in the background or just pass an ID/authorized operation.

When using `@Async` or an application-managed async executor, you can wrap the appropriate `AsyncTaskExecutor` with `DelegatingSecurityContextAsyncTaskExecutor`. **Do not double-wrap the entire MVC Callable executor just to populate context** when `WebAsyncManagerIntegrationFilter` already handles it; avoid complicating capture/cleanup ordering without addressing root causes.

Pay special attention to:

- **Capture at the right time**: wrap the task while on a request with valid authentication, not at startup when SecurityContext is empty and then reused forever.
- **Never use a "superuser context" for all tasks** unless it is a deliberately designed and controlled service identity; otherwise it becomes privilege escalation.
- **Permission revocation/logout events**: a task already submitted carrying an old context can continue even if the session is invalidated. For sensitive/long-running work, revalidate permissions or cancel per policy.
- **Cleanup**: wrappers and interceptors prevent cross-task leakage; never manually write SecurityContext into a thread pool and forget `finally`/`clearContext`.
- **Error handling**: failed tasks and cancelled futures must have safe logging, bounded retry/backoff, and proper resource release.

## 8. Pure Java 17 Illustration: Why ThreadLocal Does Not Cross to Workers

Run an example without Spring dependencies before studying the interceptor. File `ThreadLocalDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadLocalDemo {
    public static void main(String[] args) throws Exception {
        ThreadLocal<String> identity = new ThreadLocal<>();
        ExecutorService executor =
            Executors.newSingleThreadExecutor();

        try {
            identity.set("alice");

            String requestThread = identity.get();
            String workerThread = executor.submit(
                () -> {
                    String value = identity.get();
                    return value == null ? "(empty)" : value;
                }
            ).get();

            System.out.println("request=" + requestThread);
            System.out.println("worker=" + workerThread);
        } finally {
            identity.remove();
            executor.shutdown();
        }
    }
}
~~~

Compile and run:

~~~bash
javac ThreadLocalDemo.java
java ThreadLocalDemo
~~~

**Exact** stdout on JDK 17+:

~~~text
request=alice
worker=(empty)
~~~

Reason: the main thread's `ThreadLocal` does not replicate onto the executor's thread. In Spring Security, `SecurityContextHolder` also relies on ThreadLocal by default; the filter and interceptor integrated with MVC Callable establish an **explicit context scope** for the worker.

This example is not how to implement Spring Security manually; it only demonstrates Java behavior. Never copy a user's principal from ThreadLocal into a static or global variable to "fix" an empty worker.

## 9. Trust Boundaries and Security Risks in Async Processing

### 9.1. Propagated Authentication Does Not Re-Verify Itself

When an MVC Callable runs, the interceptor typically carries the context authenticated during the initial request. This **does not** necessarily re-check passwords, token validity, or permission sources every millisecond. If a user's permissions are revoked or they log out between submission and job execution, a window using the stale context can occur.

For long-running work or critical side effects, define a revalidation policy, check permissions right before commit, cancel jobs, or verify session/resource state at the target service. Never treat having an `Authentication` on a worker as an immutable guarantee of authorization.

### 9.2. Do Not Confuse with Outbound API Security Context

If a request carries a Bearer JWT, SecurityContext inside the MVC Callable can inform code about the user/authorities. However, another HTTP client (`RestClient`/`WebClient`) **does not automatically** attach the inbound access token to outbound requests. Choosing tokens for downstream calls requires OAuth2 Client, token exchange, or delegated authorization per your trust model; never forward raw `Authorization` headers to untrusted URLs.

### 9.3. Timeout and Exception Handling

When a Callable throws an error, Spring MVC can perform error dispatch/exception resolution as configured. For asynchronous requests, worker errors must be observed via metrics/tracing, return safe statuses/bodies, and never expose `Authentication`, JWT/Basic credentials, or stack traces.

An HTTP timeout does not always stop I/O running inside a Callable. If the task produces side effects, enforce idempotency, downstream client deadlines, cancellation where supported, and task limits. Never carelessly hold the request thread's database connection/transaction across to a worker; transaction contexts are managed separately per thread and transaction boundary.

### 9.4. Resources and System Protection

- Thread pools must limit concurrency, queue size, and timeouts; measure task rejection rates, latency, p95/p99, and downstream errors.
- With concurrent requests from different users, ensure authentication cannot leak when the executor reuses threads.
- Never store `SecurityContext` in a singleton field for the current user, a global cache, or a static variable.
- Account for session expiry, logout, and multi-node infrastructure if async tasks still run after the client departs.
- Never log raw tokens, cookies, passwords, sensitive headers, or full SecurityContext/Authentication objects.
- Custom filters and reverse proxies may handle async/error dispatches differently; test real traffic paths, not just local development.
- When code needs a tenant ID, verify the tenant from a trusted principal and resource authorization, not merely from user-supplied headers.

## 10. Comparison Table: Which Scenarios Have Context?

| Processing Pattern | Is SecurityContext Automatically Propagated from Servlet Request? | Recommended Approach |
| --- | --- | --- |
| Synchronous controller within security chain | Yes on request thread under normal configuration | Use `SecurityContextHolder` within request scope |
| Spring MVC controller returning `Callable<T>` | **Integrated** via `WebAsyncManagerIntegrationFilter` when filter chain aligns | Use built-in interceptor; test inside Callable |
| Controller returning `DeferredResult<T>`, task run by custom executor | Not guaranteed by default for threads outside MVC Callable | Wrapper/delegating or pass minimal verified data |
| Task created via `new Thread(...)` | Not automatically propagated under default ThreadLocal | Do not spawn threads ad hoc; use executor and explicit propagation |
| `CompletableFuture.supplyAsync(...)` on common pool | Not automatically propagated under MVC Callable interceptor guarantees | Appropriate executor/wrapper, lifecycle control |
| Service method with `@Async` | Do not assume it automatically uses the request's SecurityContext | Use DelegatingSecurityContextAsyncTaskExecutor if truly needed |
| Scheduled job without a request | No request user principal to propagate | Use an explicit service identity or job authorization mechanism |
| WebFlux reactive handler | Different mechanism from Servlet Callable, relies on reactive context | Study reactive SecurityContext separately |

Depending on custom filters, async dispatch settings, and Spring versions, verify in your actual application. The table describes the **baseline of a standard configuration**, not a guarantee for every possible security chain setup.

## 11. Common Pitfalls and Troubleshooting Guide

| Symptom | Possible Cause | Investigation / Fix |
| --- | --- | --- |
| Principal present in controller, null in Callable | URL bypasses filter integration, unusual custom chain/async handling | Verify FilterChainProxy, WebAsyncManagerIntegrationFilter, real MVC Callable, and asyncDispatch test |
| Service with `@PreAuthorize` returns 403 inside Callable | Context missing on worker or caller truly lacks authority | Compare authentication on T1/T2 via sanitized logs; inspect method proxy and authorities |
| User B's async task sees user A | ThreadLocal manually set without clearing; inheritable strategy used on pool | Remove global/inheritable workarounds; use scoped interceptor/wrapper and finally cleanup |
| `Callable` succeeds, child `CompletableFuture` loses context | Subtask created on another executor, outside Callable interceptor scope | Propagate at subtask boundary or redesign work |
| Test always returns 200 without proving propagation | Reading principal before returning Callable or mock skips filter chain | Read holder **inside lambda**, assert asyncStarted/asyncDispatch |
| Request fails with 401/302 before Callable runs | Endpoint requires authentication or session expired | Verify security chain, login/Basic/Bearer config, and request auth |
| Timeout returns error, yet job still modifies database | HTTP timeout does not guarantee work cancellation | Idempotency, deadlines, cancellation, permission check before commit |
| Many async requests exhaust server resources | Unbounded executor/queue, blocking I/O, overly long timeout | Bounded pool, backpressure, and observability |
| Error "Async support must be enabled" | Custom servlet/filter does not support async or dispatcher config issue | Check asyncSupported and Servlet registration |
| After logout, job still runs with old privileges | Context was captured before revocation | Design revalidation/job cancellation at side-effect time |
| MDC/tenant/transaction lost on worker | Outside `SecurityContextCallableProcessingInterceptor` mechanism | Propagate each context per its own contract, manage cleanup |
| Manually adding the filter multiple times | Confusing integration filter with generic async wrapper | Use standard filter chain and check against duplicate registration |

## 12. Acceptance Checklist for a Secured Async Endpoint

- [ ] Endpoint lies within the expected **Spring Security Servlet filter chain**; not accidentally bypassed.
- [ ] Controller genuinely returns `Callable<T>` and identity-dependent logic executes inside the Callable.
- [ ] `WebAsyncManagerIntegrationFilter`/MVC integration works; no global ThreadLocal strategy used as a patch.
- [ ] SecurityContext on the worker holds the right principal/authorities, with no leftover data from other users on reused threads.
- [ ] Endpoint permissions and business operation permissions are checked at the right time; do not rely solely on captured authentication.
- [ ] Custom MVC executor is resource-bounded with appropriate timeouts, queue capacity, cancellation, and observability.
- [ ] Do not treat Callable integration as default propagation for `DeferredResult`, `CompletableFuture`, `@Async`, or scheduled jobs.
- [ ] When spawning subtasks outside MVC Callable, propagate explicitly with wrappers/delegating or pass minimal safe data.
- [ ] MockMvc tests exercise **asyncStarted → asyncDispatch → inspect principal on worker**.
- [ ] Test users A/B, unauthenticated requests, missing authorities, timeouts, concurrent requests, error dispatch, and logout/revocation.
- [ ] Logs/traces contain no tokens, cookies, passwords, full SecurityContext, or sensitive claims.
- [ ] Operations with side effects enforce idempotency, revalidation, and state checks once the HTTP request has ended.

**Conclusion:** `WebAsyncManagerIntegrationFilter` is the **Spring Security Servlet ↔ Spring MVC Callable** bridge. It registers `SecurityContextCallableProcessingInterceptor` to transfer the request's SecurityContext to the worker during the Callable's scope and clean up afterward. Thus, code and method security inside a Callable receive the proper authentication, though this mechanism does not replace authorization, thread pool management, timeout control, or separate propagation for other async constructs.
