# Propagating Context Across Thread Boundaries, @Async, and Background Execution

> **Parent Topic:** Security Context. This document targets Java 17+, Spring Boot 3.x, and Spring Security 6.x on **Servlet/Spring MVC**. Focus: why `SecurityContextHolder` has an identity on the HTTP request thread yet loses it when switching to a worker thread; how to propagate deliberately via `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, and `DelegatingSecurityContextAsyncTaskExecutor`; how to use `@Async`, `CompletableFuture`, Spring MVC `Callable`, and scheduled work; and how to avoid identity leaks, stale permissions, or "forged" principals.

## 1. The problem: Alice is present in the controller, yet null inside @Async

Suppose an authenticated endpoint processes a request from Alice:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String username = authentication.getName(); // alice in this example
~~~

Then the code calls an `@Async` method:

~~~java
@Async
public void generateReport() {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

    // May be null because the method runs on a different worker thread.
}
~~~

**Common cause:** `SecurityContextHolder` in the Servlet stack uses `ThreadLocal` by default. It stores `SecurityContext` per **current thread**, rather than keeping a JVM-wide global variable or automatically following every task submitted to an executor.

~~~text
Servlet thread A                              Worker thread B
  |
  +--> SecurityContextHolder                    SecurityContextHolder
  |       Authentication(Alice)                     Authentication=null
  |
  +--> @Async / executor.submit(task) ----------> Task runs on B
                                                  |
                                                  +--> Does not automatically have identity A
~~~

That **does not mean Alice lost her login**. On the request thread, Spring Security already authenticated Alice. The worker thread is a separate execution, so it does not automatically inherit the context. When the task is genuinely allowed to act **on behalf of Alice**, an appropriate context propagation mechanism must be chosen. When the task is a **system job** or runs for hours, the right approach is usually **service identity + reauthorization**, not copying Alice's entire session.

### 1.1. Objects not to confuse

| Object | Role | Does not automatically do |
| --- | --- | --- |
| `Authentication` | Holds principal, authorities, authentication state, and optionally credentials/details | Does not prove ownership of every resource |
| `SecurityContext` | Wraps a current Authentication | Is not a database or token revocation store |
| `SecurityContextHolder` | Accesses SecurityContext for the current execution | Does not automatically share context across all threads |
| `Executor`/`ExecutorService` | Manages running tasks on threads | Does not authenticate identity by itself |
| `AsyncTaskExecutor` | Spring Task interface for asynchronous work | Does not guarantee propagation by default in every setup |
| `DelegatingSecurityContextRunnable` | Puts context onto the worker around a `Runnable`, then cleans up | Does not refresh roles from the database |
| `DelegatingSecurityContextCallable` | Same for `Callable<T>` | Does not replace Future timeout/error handling |
| `DelegatingSecurityContextExecutor` | Wraps tasks on `execute`; can capture context at submit time | Does not enforce domain permissions by itself |
| `DelegatingSecurityContextAsyncTaskExecutor` | Wrapper integrating Spring `@Async`/`AsyncTaskExecutor` | Does not turn long-lived jobs into permanent delegation |

**Propagating SecurityContext means carrying existing information**, not creating new authentication proof. If the caller is unauthenticated or the context is stale, a wrapper does not fix that by itself.

## 2. Java 17: proving ThreadLocal does not cross threads automatically

Create a standalone file **`ThreadLocalDemo.java`**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadLocalDemo {

    private static final ThreadLocal<String> CURRENT =
        new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool =
            Executors.newSingleThreadExecutor();

        try {
            CURRENT.set("alice");

            System.out.println(
                "request=" + CURRENT.get()
            );

            String fromWorker = pool.submit(
                () -> CURRENT.get()
            ).get();

            System.out.println(
                "worker=" + fromWorker
            );
        } finally {
            CURRENT.remove();
            pool.shutdown();
        }

        System.out.println(
            "after=" + CURRENT.get()
        );
    }
}
~~~

Run with JDK 17+:

~~~bash
javac ThreadLocalDemo.java
java ThreadLocalDemo
~~~

**Exact stdout:**

~~~text
request=alice
worker=null
after=null
~~~

The main thread puts `"alice"` in ThreadLocal. The executor creates a different worker thread, so `CURRENT.get()` on the worker does not see Alice. `CURRENT.remove()` in `finally` cleans up the main thread's context. This is a plain Java example to understand **per-thread isolation**; Spring Security has its own context and cleanup mechanisms and does not directly use `ThreadLocal<String>` like the demo code.

### 2.1. Why not use a static field to share the user?

~~~java
// WRONG in a multi-user server:
static Authentication CURRENT_AUTHENTICATION;
~~~

A static field is shared across all requests. Alice and Bob could overwrite each other's identity, causing data leaks or privilege escalation. The right solution is per-execution context, controlled context propagation, or passing a **trusted account ID** as a business parameter.

### 2.2. Three SecurityContextHolder modes

| Strategy | Meaning | Risk |
| --- | --- | --- |
| `MODE_THREADLOCAL` | Context bound to the current thread; Servlet default | Needs a handoff mechanism when switching to a worker |
| `MODE_INHERITABLETHREADLOCAL` | Child threads can inherit context when the thread is created | Unsuitable automatically for reused thread pools; can leak stale/mixed users |
| `MODE_GLOBAL` | Context shared JVM-wide | Never use in multi-user web servers |

A thread pool is typically created at startup and reused across thousands of requests. `InheritableThreadLocal` **does not re-copy context each time a task is submitted**. Therefore, do not fix `@Async` issues by changing the JVM-wide strategy to `MODE_GLOBAL` or assuming `MODE_INHERITABLETHREADLOCAL` is always right.

## 3. Proper lifecycle when passing context to a worker

~~~text
Alice's HTTP request
    |
    v
Spring Security Authentication Filter
    |
    +--> Authentication(Alice) verified
    |
    v
SecurityContextHolder on servlet thread
    |
    +--> context holds Alice
    |
    v
Submit task at T1 via wrapper
    |
    +--> Captures submitting thread's context
    |
    v
Worker thread receives wrapped Runnable/Callable
    |
    +--> Sets captured context into worker's holder
    +--> Executes task/authorization if appropriate
    |
    v
finally
    |
    +--> Clears/restores context per wrapper implementation
    |
    v
Worker thread returns to pool for other tasks
~~~

**The two most critical factors are capture timing and cleanup.** If captured too late, the request context has already been cleared. If not cleaned up, Bob's task on the same worker thread may accidentally read Alice's identity.

### 3.1. Cleanup even when a task throws an exception

Spring Security's `DelegatingSecurityContextRunnable` sets the context for the worker, calls `Runnable.run()`, and cleans up the holder in `finally`. Thus an exception does not leave identity stuck on the pool thread under that wrapper mechanism.

Simplified model:

~~~java
// Illustrates the principle only, not a copy of library source code.
try {
    SecurityContextHolder.setContext(capturedContext);
    delegate.run();
} finally {
    SecurityContextHolder.clearContext();
}
~~~

The actual library may use `SecurityContextHolderStrategy` and an appropriate restore mechanism; **prefer built-in wrappers over rolling your own**. Cleanup does not automatically observe or handle business errors; the caller must still handle Future exceptions, timeouts/cancellations, and retries.

### 3.2. "Capture" is not necessarily a deep copy

`SecurityContext` and `Authentication` can be mutable objects. When a wrapper is constructed with a context, it **does not promise a deep immutable snapshot** of all objects and authorities. If two threads hold the same object and one thread mutates Authentication, a race condition can occur.

Do not treat SecurityContext as an "unchangeable permission ticket" for a long-running task; permissions can be revoked in the database while the task is still waiting in a queue. For sensitive actions, store a trusted account ID/job ID and check current permissions at execution time.

## 4. Approach 1: DelegatingSecurityContextRunnable

`org.springframework.security.concurrent.DelegatingSecurityContextRunnable` wraps a Runnable with a chosen context.

~~~java
SecurityContext context =
    SecurityContextHolder.getContext();

Runnable action = () -> {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

    if (current == null) {
        throw new IllegalStateException("Missing security identity");
    }

    System.out.println("worker=" + current.getName());
};

Runnable wrapped =
    new DelegatingSecurityContextRunnable(action, context);

rawExecutor.execute(wrapped);
~~~

This is a **service snippet**: `rawExecutor` must be a managed `Executor`; imports are needed. It assumes the caller thread holds an Authentication already verified by the framework. Never construct a fake `context` from a client-supplied userId or role.

### 4.1. Single-argument constructor without explicit context

~~~java
Runnable wrapped =
    new DelegatingSecurityContextRunnable(action);
~~~

This shortcut constructor uses the current context **when the wrapper is created**. If the wrapper is created from a scheduler thread with no user or after the request has ended, it will not magically query the logged-in user on another thread.

### 4.2. Callable returning a result

~~~java
Callable<String> action = () -> {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

    return current == null ? "none" : current.getName();
};

Callable<String> wrapped =
    new DelegatingSecurityContextCallable<>(
        action, SecurityContextHolder.getContext()
    );

Future<String> future = executorService.submit(wrapped);
~~~

`Callable` can return a result or throw an exception. `Future.get()` is a blocking operation; when calling it from an HTTP thread, set an appropriate timeout to avoid blocking indefinitely. For conciseness with Java concurrent APIs, you can use `DelegatingSecurityContextExecutorService`.

## 5. Approach 2: DelegatingSecurityContextExecutor

Instead of wrapping every task, wrap the `Executor`:

~~~java
Executor securedExecutor =
    new DelegatingSecurityContextExecutor(rawExecutor);

securedExecutor.execute(() -> {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

    // Use authenticated principal if the action is allowed.
});
~~~

With the **delegate-only** constructor, the wrapper captures the caller's SecurityContext at **`execute` call time**, then wraps the task. This suits short-lived work submitted from an authenticated request.

### 5.1. One argument vs. two arguments creates different security policies

| Constructor | Context applied |
| --- | --- |
| `new DelegatingSecurityContextExecutor(delegate)` | Context at the time **each task is submitted** |
| `new DelegatingSecurityContextExecutor(delegate, fixedContext)` | **Same fixedContext for every task** |

**Dangerous trap:** If a singleton `Executor` bean is constructed with **admin Alice's** context on the first request, every task submitted later by Bob could run as admin Alice. That is an impersonation/privilege escalation vulnerability.

A fixed context is only appropriate when the application **genuinely** intends to use a provisioned, controlled system identity. Never let an arbitrary user's context turn into a "system account".

### 5.2. CompletableFuture.supplyAsync

`CompletableFuture.supplyAsync(supplier)` without an executor typically runs on the common pool, which does not carry the request's SecurityContext by default.

~~~java
Executor secured =
    new DelegatingSecurityContextExecutor(rawExecutor);

CompletableFuture<String> result =
    CompletableFuture.supplyAsync(() -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        return auth == null ? "none" : auth.getName();
    }, secured);
~~~

So that subsequent stages also run with the right policy:

~~~java
CompletableFuture<String> normalized =
    result.thenApplyAsync(String::toUpperCase, secured);
~~~

However, **do not assume every stage always captures the initial user**: a stage may be submitted from a completion thread rather than the request thread. If a stage needs security context, carefully assess **who is submitting at capture time**. For multi-step pipelines, it is often cleaner and safer to pass a verified account ID/tenant ID as data and reauthorize at execution rather than relying on ThreadLocal across every callback.

`thenApply` without `Async` also does not guarantee running on the servlet thread; it can run on whichever thread completed the preceding stage. Never treat a stage's ThreadLocal as unconditional proof for authorization.

### 5.3. ExecutorService, scheduling, and fixed context

Spring Security also provides:
- `DelegatingSecurityContextExecutorService`
- `DelegatingSecurityContextScheduledExecutorService`
- `DelegatingSecurityContextTaskExecutor`
- `DelegatingSecurityContextSchedulingTaskExecutor`
- `DelegatingSecurityContextTaskScheduler`

Pick the wrapper matching the interface you need. If you need `submit(Callable)` or shutdown, a plain `Executor` lacks those methods. **Repeating scheduled tasks must not hold the creator's privileges indefinitely**; see the section on long-running jobs.

## 6. Approach 3: @Async + DelegatingSecurityContextAsyncTaskExecutor

Spring Framework `@Async` uses a proxy mechanism to run a method on another executor. It **does not mean** a `ThreadLocal` follows to the worker automatically. With Spring Security Servlet, you can use `DelegatingSecurityContextAsyncTaskExecutor`.

~~~text
Controller (request thread, Alice)
    |
    +--> Spring proxy intercepts @Async
    |
    +--> AsyncTaskExecutor.submit(...)
           |
           +--> If raw executor:
           |      worker lacks Alice
           |
           +--> If DelegatingSecurityContextAsyncTaskExecutor:
                  captures context at submit
                  -> sets Alice on worker
                  -> runs method
                  -> cleans up
~~~

You must clearly configure **which executor bean** `@Async("beanName")` selects.

### 6.1. Creating two executors for learning

~~~java
@Configuration
@EnableAsync
class AsyncConfig {

    @Bean("rawAsyncExecutor")
    ThreadPoolTaskExecutor rawAsyncExecutor() {
        ThreadPoolTaskExecutor pool =
            new ThreadPoolTaskExecutor();

        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("worker-");
        return pool;
    }

    @Bean("securityAsyncExecutor")
    AsyncTaskExecutor securityAsyncExecutor(
            @Qualifier("rawAsyncExecutor")
            ThreadPoolTaskExecutor raw) {

        return new DelegatingSecurityContextAsyncTaskExecutor(raw);
    }
}
~~~

This is a **snippet**; full imports appear in the demo below. `rawAsyncExecutor` is an ordinary pool; `securityAsyncExecutor` wraps it to propagate context. Spring manages the lifecycle of `ThreadPoolTaskExecutor` beans; do not allocate a new pool per request.

**Do not construct the wrapper with Alice's fixed SecurityContext in bean configuration**, because this bean must serve multiple users. The `DelegatingSecurityContextAsyncTaskExecutor` constructor takes only the delegate so it captures the caller's context upon task submission.

### 6.2. @Async public method on a Spring bean

~~~java
@Service
class UserJobService {

    @Async("securityAsyncExecutor")
    public CompletableFuture<String> getCallerName() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        return CompletableFuture.completedFuture(
            auth == null ? "none" : auth.getName()
        );
    }
}
~~~

If a controller injects `UserJobService` from Spring and calls `getCallerName()` through the proxy, the method body executes on a worker thread with the proper context. Calling `CompletableFuture.completedFuture` **inside** the method does not make the method synchronous; the invocation is intercepted by the proxy beforehand.

### 6.3. Self-invocation: @Async may not run asynchronously

~~~java
@Service
class ReportService {

    public void launch() {
        generateAsync(); // Internal call on same object, may bypass proxy.
    }

    @Async("securityAsyncExecutor")
    public void generateAsync() {
        // Under self-invocation, may run immediately on the request thread.
    }
}
~~~

If a test simply sees Alice in Authentication inside the method, the method **might never have switched threads**. To test genuine propagation, invoke through another Spring-managed bean, inspect the executor/thread name, or use MockMvc `asyncStarted` with a suitable return type.

Private/final methods and instantiating objects manually with `new` instead of injecting beans can also prevent the proxy from intercepting the annotation depending on configuration.

### 6.4. Executor selection and error handling

`@Async` without specifying an executor name may use the framework/Boot default executor. If a project has multiple executors, always verify which bean receives the task. Methods returning `void` report errors via `AsyncUncaughtExceptionHandler`; methods returning `Future`/`CompletableFuture` must handle completion failures, timeouts, cancellations, and rejections.

**Propagating SecurityContext does not automatically propagate transactions or MDC**. Transaction-bound contexts have their own lifecycle; `@Transactional` on the request thread does not carry that transaction onto the worker. If a worker needs a DB transaction, establish an appropriate transaction boundary inside the worker/service itself.

## 7. Spring Boot 3 / Java 17 demo: raw executor vs. secured executor

The demo exercises three requests:

- `GET /probe/direct`: request thread reads Alice's Authentication.
- `GET /probe/secure`: `@Async("securityAsyncExecutor")` uses the wrapper; worker reads Alice.
- `GET /probe/raw`: `@Async("rawAsyncExecutor")` does not propagate; worker reads `"none"`.

Additionally `GET /public` is open. Both `/probe/secure` and `/probe/raw` **still require an authenticated user** before the controller lets them submit tasks. The raw endpoint is strictly for technical observation and **performs no sensitive business actions**.

The application uses **HTTP Basic + STATELESS** so every HTTP request is independent; there is no server-side session "holding onto" identity between requests. Demo Basic credentials are for localhost only.

### 7.1. Dependencies and files

Create a Spring Boot 3.x, Spring Security 6.x, Java 17+ project with Gradle plugins/repositories/Wrapper. In your existing `build.gradle`, add the dependencies block:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

These are **dependencies**, not a standalone `build.gradle`.

~~~text
src/main/java/com/example/asyncidentity/
  AsyncIdentityApplication.java
  SecurityConfig.java
  AsyncConfig.java
  IdentityProbeService.java
  IdentityController.java

src/test/java/com/example/asyncidentity/
  SecurityContextAsyncTest.java
~~~

### 7.2. AsyncIdentityApplication.java

~~~java
package com.example.asyncidentity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncIdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(AsyncIdentityApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig.java

~~~java
package com.example.asyncidentity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/probe/**")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }
}
~~~

Basic requests pass through the Spring Security filter/AuthenticationManager; users with valid passwords get an Authentication, while invalid/missing credentials are rejected on protected endpoints. `STATELESS` does not mean a request has no SecurityContext: **within each request** the user's context still exists once credentials are verified.

### 7.4. AsyncConfig.java

~~~java
package com.example.asyncidentity;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfig {

    @Bean("rawAsyncExecutor")
    ThreadPoolTaskExecutor rawAsyncExecutor() {
        ThreadPoolTaskExecutor pool =
            new ThreadPoolTaskExecutor();

        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("identity-worker-");
        return pool;
    }

    @Bean("securityAsyncExecutor")
    AsyncTaskExecutor securityAsyncExecutor(
            @Qualifier("rawAsyncExecutor")
            ThreadPoolTaskExecutor raw) {

        return new DelegatingSecurityContextAsyncTaskExecutor(raw);
    }
}
~~~

In a production application, size the executor for load, configure queue capacity/rejection policies, monitoring, graceful shutdown, and bound task volume. Do not use an unbounded thread pool or unbounded queue just to avoid rejection errors.

### 7.5. IdentityProbeService.java

~~~java
package com.example.asyncidentity;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class IdentityProbeService {

    @Async("securityAsyncExecutor")
    public CompletableFuture<String> propagated() {
        return CompletableFuture.completedFuture(currentName());
    }

    @Async("rawAsyncExecutor")
    public CompletableFuture<String> withoutPropagation() {
        return CompletableFuture.completedFuture(currentName());
    }

    private String currentName() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        return auth == null ? "none" : auth.getName();
    }
}
~~~

Both methods run the same logic on different executors. For Alice's request:
- `propagated()` is expected to see `"alice"`;
- `withoutPropagation()` is expected to see `"none"` because the raw pool thread has no request ThreadLocal.

If a custom TaskDecorator or JVM-wide `SecurityContextHolderStrategy` is installed, results can differ; the demo assumes standard Spring Security Servlet configuration.

### 7.6. IdentityController.java

~~~java
package com.example.asyncidentity;

import java.util.concurrent.CompletableFuture;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    private final IdentityProbeService service;

    public IdentityController(IdentityProbeService service) {
        this.service = service;
    }

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/probe/direct")
    public String direct(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/probe/secure")
    public CompletableFuture<String> secure() {
        return service.propagated();
    }

    @GetMapping("/probe/raw")
    public CompletableFuture<String> raw() {
        return service.withoutPropagation();
    }
}
~~~

The controller injects `IdentityProbeService` as a **separate Spring bean**, ensuring `@Async` invocations go through the proxy. The controller returns CompletableFuture so Spring MVC handles asynchronous responses without blocking the request thread via `join()`.

### 7.7. Running and observing HTTP

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Open another terminal on localhost:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/probe/secure
curl -i -u alice:alice123 http://localhost:8080/probe/direct
curl -i -u alice:alice123 http://localhost:8080/probe/secure
curl -i -u alice:alice123 http://localhost:8080/probe/raw
curl -i -u admin:admin123 http://localhost:8080/probe/secure
curl -i -u admin:admin123 http://localhost:8080/probe/raw
~~~

| Request | Expected HTTP | Expected Body | Meaning |
| --- | --- | --- | --- |
| `/public` anonymous | 200 | `public` | Public |
| `/probe/secure` anonymous | 401 | Per Basic entry point | Disallows submitting when unauthenticated |
| Alice `/probe/direct` | 200 | `alice` | Request thread has Alice |
| Alice `/probe/secure` | 200 | `alice` | Worker receives propagated context |
| Alice `/probe/raw` | 200 | `none` | Raw worker lacks Alice |
| Admin `/probe/secure` | 200 | `admin` | Captured per submission |
| Admin `/probe/raw` | 200 | `none` | Does not automatically inherit Alice/admin |

These statuses/bodies are **code expectations**, not logs from an executed Gradle run. Demo commands containing passwords are for localhost only; production requires TLS and avoiding passwords in shell history/traces.

## 8. MockMvc testing: propagating the right user without leaking to another

Create `src/test/java/com/example/asyncidentity/SecurityContextAsyncTest.java`:

~~~java
package com.example.asyncidentity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityContextAsyncTest {

    @Autowired
    MockMvc mvc;

    private String callAsync(
            String path, String username, String password)
            throws Exception {

        MvcResult initial = mvc.perform(get(path)
                .with(httpBasic(username, password)))
            .andExpect(request().asyncStarted())
            .andReturn();

        MvcResult completed = mvc.perform(asyncDispatch(initial))
            .andExpect(status().isOk())
            .andReturn();

        return completed.getResponse().getContentAsString();
    }

    @Test
    void asyncWrapperPropagatesIdentityPerUser()
            throws Exception {
        assertEquals(
            "alice",
            callAsync("/probe/secure", "alice", "alice123")
        );
        assertEquals(
            "admin",
            callAsync("/probe/secure", "admin", "admin123")
        );
    }

    @Test
    void rawExecutorHasNoRequestIdentity()
            throws Exception {
        assertEquals(
            "none",
            callAsync("/probe/raw", "alice", "alice123")
        );
    }

    @Test
    void oneUsersContextDoesNotLeakToTheNextTask()
            throws Exception {
        assertEquals(
            "alice",
            callAsync("/probe/secure", "alice", "alice123")
        );
        assertEquals(
            "none",
            callAsync("/probe/raw", "admin", "admin123")
        );
        assertEquals(
            "admin",
            callAsync("/probe/secure", "admin", "admin123")
        );

        assertNull(
            SecurityContextHolder.getContext().getAuthentication()
        );
    }

    @Test
    void directControllerUsesRequestThreadAuthentication()
            throws Exception {
        mvc.perform(get("/probe/direct")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void anonymousCannotScheduleAProtectedProbe()
            throws Exception {
        mvc.perform(get("/probe/secure"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }
}
~~~

Run tests:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

**Why use `request().asyncStarted()` + `asyncDispatch`?** The controller returns `CompletableFuture`. Spring MVC uses an asynchronous request lifecycle; the initial dispatch may not yet have the final response. `asyncDispatch(initial)` simulates completing async processing before asserting status/body.

**Why test Alice and then admin?** Testing only Alice could miss a fixed-context executor bug; running two accounts catches wrappers that capture the first user and reuse them for every subsequent task.

**Why `.with(httpBasic(...))` instead of only `@WithMockUser`?** Basic tests send the request through the Spring Security authentication filter/provider, whereas mock users fabricate an Authentication for tests without proving password validation. Domain permission/owner/tenant rules still require separate tests.

**This test suite was only statically reviewed.** You need to run Gradle in a real project with matching versions/dependencies to confirm build/test execution.

## 9. Spring MVC Callable is not the same as @Async or DeferredResult

Spring Security 6.x has dedicated integration with Spring MVC asynchronous request processing.

### 9.1. Controller returning Callable

~~~java
@GetMapping("/mvc/callable")
public Callable<String> callable() {
    return () -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        return auth == null ? "none" : auth.getName();
    };
}
~~~

When the application uses the Spring Security filter chain properly, `WebAsyncManagerIntegrationFilter` integrates with Spring MVC to **propagate context to the thread executing the Callable**. Spring Security docs describe context being attached to the Callable based on the SecurityContext present at `startCallableProcessing`.

That is **a specific integration**, not a guarantee that every `new Thread()`, `CompletableFuture`, `@Async`, scheduler, or thread-pool library receives Authentication automatically.

### 9.2. DeferredResult completed by the application

A controller returning `DeferredResult` can be completed later by code running on an application-managed thread. There is no automatic mechanism equivalent to MVC Callable ensuring every completion site holds the context. You must use a wrapper/managed executor if identity is truly needed inside the completion callback, or pass a trusted account ID instead of context.

### 9.3. CompletableFuture stages

~~~java
@GetMapping("/mvc/future")
public CompletableFuture<String> future() {
    return CompletableFuture.supplyAsync(() -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        return auth == null ? "none" : auth.getName();
    });
}
~~~

This is an **anti-pattern**: the overload without an executor typically uses the common pool, which does not guarantee the servlet request's SecurityContext. You need a wrapped executor **right at the submission site**, and must continue evaluating each stage. If a task only needs the user ID, passing the trusted user ID can be simpler and safer.

### 9.4. AsyncContext.start and custom dispatch

Spring Security integrates with several Servlet Async APIs, including `AsyncContext.start(Runnable)`. Behavior depends on servlet security filters and container configuration. Never infer that all callbacks outside request-managed async flows are propagated. Test the specific mechanism in use.

### 9.5. WebFlux is a different model

Reactive Spring WebFlux uses Reactor Context and `ReactiveSecurityContextHolder`, rather than taking Servlet ThreadLocal as the right identity source across all operators in a reactive stream. Never copy this lesson's Servlet guidance verbatim into a `SecurityWebFilterChain`/Reactor pipeline.

## 10. @Scheduled, message queues, and long-running background jobs

In `@Scheduled` tasks or queue consumers, **there is no HTTP request user** when the task runs. An empty context can be an entirely valid state.

### 10.1. Do not turn a job creator's session into permanent authority

Example:

~~~text
09:00: Alice has ROLE_ADMIN and submits an export request.
       App captures SecurityContext(Alice, ROLE_ADMIN).

09:05: An admin locks Alice and revokes ROLE_ADMIN.

10:00: Worker starts processing the export.
       The old context may still contain ROLE_ADMIN.
~~~

Wrappers do not automatically refresh permissions when the database changes. A `hasRole("ADMIN")` check based on captured Authentication can yield stale results. For sensitive resources, reauthorize against current policies, account enabled/locked state, owner, tenant, and action.

### 10.2. Job commands instead of serialized Authentication

A durable job should store minimal information:

~~~java
public record ExportJob(
    String jobId,
    String requestedByAccountId,
    String tenantId,
    String reportId
) {}
~~~

This data **does not become Authentication by itself**. Production workflow:

1. Upon receiving the job-creation request, the framework authenticates the user.
2. The service checks that the user is allowed to create the job under owner/tenant/domain policy.
3. Persist the job ID and immutable account/tenant IDs from the verified source, never a client-supplied userId.
4. Workers run using a **service/workload identity** granted least-privilege scopes.
5. When a worker starts, re-verify account status, current permissions, and the target resource (if policy requires).
6. Audit both **requestedBy** and **executedBy**, object, timestamp, and outcome.
7. Address idempotency, retries, cancellation, timeouts, and revocation of delegated authority.

**Never serialize raw SecurityContext/Authentication into Kafka, RabbitMQ, or a database queue**. The object may contain credentials/details, stale authorities, session metadata, and implementation classes creating version coupling.

### 10.3. Schedulers should use a service identity

Scheduled jobs needing to authenticate to other APIs can use OAuth2 `client_credentials`, workload identity, mTLS, or another trusted service-to-service mechanism. Never pin ROLE_ADMIN from an old HTTP request onto a scheduler "so the job has enough permissions".

If a task genuinely must act on behalf of a user in the future, establish an explicit delegated authorization contract: scopes, expiration, consent/audit, revocation rights, and revalidation as required.

## 11. Dangerous security and concurrency mistakes

### 11.1. Context presence does not equal permitted action

~~~java
Authentication a =
    SecurityContextHolder.getContext().getAuthentication();

boolean flag =
    a != null && a.isAuthenticated();
~~~

`flag` is insufficient for authorization: anonymous authentication can report true, a role snapshot can be stale, and a resource has its own owner/tenant. Use Spring Security authorization/method security and concrete domain policies; for sensitive jobs, check current permissions close to execution time.

### 11.2. Never forge trusted tokens from client data

~~~java
// Unsafe anti-pattern:
Authentication forged =
    UsernamePasswordAuthenticationToken.authenticated(
        userIdFromRequest,
        "not-verified",
        AuthorityUtils.createAuthorityList("ROLE_ADMIN")
    );
~~~

Clients have no right to self-assert ADMIN and turn it into trusted authentication. Only AuthenticationManager, an IdP, or a controlled system mechanism can mint principals/authorities per policy. If a forged Authentication is propagated to a worker, the wrapper cannot fix the privilege escalation bug.

### 11.3. Never share a mutable SecurityContext and mutate concurrently

A context shared across multiple threads can cause races when calling `setAuthentication`. If an immutable identity is needed for a job, use a small business object or fetch information from a trusted source at execution time. Never assume a wrapper constructor performs a deep copy.

### 11.4. Do not confuse this with transaction propagation

`@Transactional` on an HTTP request typically binds the transaction/session to the current thread. `@Async` runs on another thread and does not automatically carry the old transaction over. Workers need their own transaction boundary and should not hold transactions open while waiting in a queue.

SecurityContext propagation is **not equivalent** to database transaction propagation, request-scoped bean transfer, or MDC/tracing propagation. Each context has a different mechanism and lifecycle.

### 11.5. MDC/tracing also does not prove Authentication

TaskDecorator/Micrometer integrations can carry trace IDs across threads. Yet trace baggage or client-sent headers are **not proof of login**. Never infer a task has SecurityContext simply because logs share a trace ID; test each context and its cleanup separately.

### 11.6. Failure paths, task cancellation, and rate limits

Be sure to test:
- A task throws an exception and the worker thread is cleaned up.
- The executor queue is full, tasks are rejected, yet HTTP status/observability remain clear.
- A Future is canceled or times out; verify whether the task continues side effects.
- An account is locked after submission but before execution.
- Two users submit concurrently without mixing identities.
- Shutdown cleans up the pool without retaining sensitive data.
- Authorization still executes against real resources, rather than merely checking `getName()`.

## 12. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using static Authentication | Mixes users across requests | Keep SecurityContext per execution |
| Switching to MODE_GLOBAL to fix @Async | Shares identity JVM-wide | Keep ThreadLocal, use wrappers |
| Using MODE_INHERITABLETHREADLOCAL with pools | Wrong inheritance timing / stale context | Capture per task |
| `CompletableFuture.supplyAsync` without executor | Common pool lacks request context | Pass a properly wrapped managed executor |
| Forgetting `@Async("securityAsyncExecutor")` | Uses default executor without propagation | Specify the right bean |
| Calling `this.asyncMethod()` | Self-invocation bypasses proxy | Call through an injected Spring bean |
| Fixed context captured from first user | Bob may run as Alice | Capture on each submit |
| Missing cleanup in custom worker | Subsequent task sees previous user | Use DelegatingSecurityContext* wrappers |
| Putting `Authentication` into long-lived queues | Stale permissions, credential leaks | Job command + fresh authorization |
| Using `@Scheduled` with an old user context | Over-scoped privileges | Service identity and bounded delegation |
| Checking only `isAuthenticated` | Anonymous/stale role/tenant bypass | AuthorizationManager/domain policies |
| Treating MVC Callable like DeferredResult | Missing context in callback | Read each API's specific integration |
| Forgetting `asyncDispatch` in MockMvc | Asserts response before completion | `request().asyncStarted()` + `asyncDispatch` |
| Treating `@WithMockUser` as E2E login | Does not verify passwords/tokens | Test through real filters/login |
| Testing only one user | Misses fixed-context/leak bugs | Test alternating Alice/admin/anonymous |

## 13. Debugging when @Async cannot see the user

Check across each boundary in order:

1. On the request thread, does Authentication actually exist and is it verified? Is it anonymous?
2. Which SecurityFilterChain did the request hit? Was a URL/dispatcher matched wrongly?
3. Did the `@Async` method execute through a Spring proxy, or did self-invocation run it synchronously on the caller thread?
4. Which executor bean did `@Async` select? Is it wrapped with `DelegatingSecurityContextAsyncTaskExecutor`?
5. At submission time, was Alice's context present? Or had the request already finished and cleared the holder?
6. Does the worker thread see the same user or null? Is there a misconfigured fixed-context wrapper?
7. Does a raw executor have a TaskDecorator or custom strategy accidentally retaining identity?
8. In `CompletableFuture`, which stage uses which executor, and from which thread was it submitted?
9. Is `DeferredResult` completion programmed by the application with the right context policy?
10. Does Spring MVC `Callable` have `WebAsyncManagerIntegrationFilter`/async support properly configured?
11. Does a job running an hour later still hold current permissions? Are account, roles, and owner/tenant revalidated?
12. When a task throws an exception, is the context cleared on the pool thread?
13. Are queue capacity, timeouts, cancellations, and exception handlers observed?
14. Are MODE_GLOBAL or InheritableThreadLocal leaking identities?

Example logging config for development:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.aop.interceptor.AsyncExecutionInterceptor=DEBUG
~~~

Log correlation ID, job ID, endpoint, principal type, or safe account ID; **never log raw passwords, Authorization headers, access tokens, session cookies, full SecurityContext dumps, authentication credentials, or sensitive JWT claims**.

## 14. Self-check exercises

**Question 1.** The controller sees Alice in SecurityContext, but the `@Async` worker returns null. Is `UserDetailsService` definitely wrong?

**Answer:** No. Most likely it is a ThreadLocal boundary issue where context has not been propagated to the executor thread.

**Question 2.** Is `SecurityContextHolder.MODE_GLOBAL` suitable so every async job can see the user?

**Answer:** No. It shares context across the entire JVM and is dangerous in multi-user applications.

**Question 3.** When does `DelegatingSecurityContextExecutor(delegate)` capture context?

**Answer:** Each time the caller submits a task via `execute()`.

**Question 4.** What about the `(delegate, fixedContext)` constructor?

**Answer:** Every task uses the supplied context; avoid accidentally pinning a fixed user context onto other users' requests.

**Question 5.** Why must wrappers clear the holder in finally?

**Answer:** To prevent leaking identity to the next task on the pool thread, even if the task fails.

**Question 6.** Does calling an `@Async` method on `this` reliably run asynchronously?

**Answer:** No. It can bypass the proxy. Call through another injected bean and test the handoff.

**Question 7.** Does `CompletableFuture.supplyAsync(...)` without specifying an executor carry the current Authentication?

**Answer:** Not guaranteed; the common pool typically lacks the request ThreadLocal.

**Question 8.** Does Spring MVC Callable have built-in context propagation support?

**Answer:** Yes, via Spring Security/`WebAsyncManagerIntegrationFilter` when configured properly.

**Question 9.** Is DeferredResult automatically propagated to every callback thread like Callable?

**Answer:** No. You need a wrapper or to pass trusted business info explicitly.

**Question 10.** Should a worker running a scheduled job reuse Alice's session from last week?

**Answer:** No. Use a service identity or bounded delegated authorization with revalidation.

**Question 11.** ROLE_ADMIN was revoked after a job was queued. Does the captured context update automatically?

**Answer:** No. Re-check current permissions when the task runs if policy requires it.

**Question 12.** Should you put the raw Authentication object into a queue?

**Answer:** No. Use a job command with account ID/tenant ID and minimal metadata, never credentials.

**Question 13.** Does propagation automatically carry transactions from `@Transactional` into `@Async`?

**Answer:** No. Transaction contexts have separate thread boundaries.

**Question 14.** If Bob's task sees Alice, what should you check?

**Answer:** Fixed-context executors, broken cleanup, shared static auth, or MODE_GLOBAL/INHERITABLETHREADLOCAL.

**Question 15.** Does having Authentication in a worker mean you can skip owner/tenant checks?

**Answer:** No. Authentication does not replace authorization, and permissions may be stale.

**Question 16.** Should WebFlux follow this Servlet ThreadLocal guidance verbatim?

**Answer:** No. WebFlux uses Reactor Context/`ReactiveSecurityContextHolder` and its own propagation mechanisms.

## 15. Official references

- Spring Security 6.5 — **Concurrency Support**: https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html
- Spring Security — **Servlet Concurrency**: https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- Spring Security — **Spring MVC Integration**: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/mvc.html
- Spring Security — **Authentication Architecture & SecurityContextHolder**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — **Method Security**: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — **DelegatingSecurityContextExecutor API**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/concurrent/DelegatingSecurityContextExecutor.html
- Spring Security — **DelegatingSecurityContextAsyncTaskExecutor API**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/task/DelegatingSecurityContextAsyncTaskExecutor.html
- Spring Framework — **Task Execution, Scheduling and @Async**: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — **Async Requests in Spring MVC**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html

**Remember:** In Spring Security Servlet, `SecurityContextHolder` uses **ThreadLocal** by default. When moving a task to another thread, only pass `SecurityContext` when there is a valid reason and authorization, using a `DelegatingSecurityContext*` wrapper: **capture right at submission, set temporarily on the worker, and clean up afterward**. For `@Async`, wrap the executor and invoke via a Spring proxy. For schedulers, queues, and long-running jobs, prefer **service identities, minimal data commands, and live permission checks** rather than holding onto an old HTTP request's Authentication forever.
