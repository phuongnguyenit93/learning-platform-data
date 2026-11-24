# Testing Against Identity Leakage When Threads Are Reused

**Scope:** Spring Security **Servlet/Spring MVC**, Java 17+, Spring Boot 3.x, and Spring Security 6.x. This lesson focuses on a subtle asynchronous bug: **a thread pool reuses a worker from an earlier task while the `SecurityContext` holding the previous user's identity was never cleared**, leading to resource access or audit entries under the wrong user. We will design deterministic reproducible tests, demonstrate both the bug and the fix, and then verify `ExecutorService`, `@Async`, `Callable`, and exception-throwing tasks.

## 1. Why Does Thread Reuse Cause Identity Leakage?

In Spring Security Servlet, `SecurityContextHolder` provides access to the current thread's `SecurityContext` and `Authentication`:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
String name = authentication == null
    ? null : authentication.getName();
```

Spring Security Servlet's default strategy is **`MODE_THREADLOCAL`**. Context lives inside ThreadLocal; it **does not automatically become per-job data**, does not automatically propagate to every async thread, and does not automatically vanish merely because a business method returned.

During a normal Servlet request lifecycle, the **Spring Security filter chain** manages when the security context is set/saved and cleared. However, when an application uses `ExecutorService`, `CompletableFuture`, `@Async`, or custom callbacks directly, code must clearly understand who **propagates** and who **clears** `SecurityContext` on the worker thread.

```text
Alice's request                    ExecutorService (1-thread pool)
       │                                     │
       ├── submit task A ──────────────────> │ worker-1
       │                                     │ setContext(alice)
       │                                     │ execute A
       │                                     │ FORGOT clearContext()
       │                                     │
Bob's request                       ────────> │ worker-1 reused
       ├── submit task B ──────────────────> │ getContext() still == alice
       │                                     │ may write/audit/access
       │                                     │ data under Alice's rights
```

This is **cross-request/cross-task identity leakage**. It can cause reading someone else's data, wrong authorization decisions, misattributed audit logs, or wrong tenant access. Merely testing "does the async task see a username?" is **insufficient**.

Distinguish two situations:

- **Missing context propagation:** a task running on a new thread sees `null` authentication, causing principal-dependent features to fail. This is a **context propagation** problem.
- **Residual context:** a task granted no identity still reads the previous user's authentication, such as Alice. This is **identity leakage**.

The greatest danger occurs when a new task executes on the **exact thread** that previously processed a different principal, so tests using multi-thread pools with random scheduling can miss it.

## 2. Security Invariants That Must Be Tested

| Invariant | Test Case | Expected Result |
| --- | --- | --- |
| Right identity | Alice task, then Bob task | Alice sees only Alice, Bob sees only Bob. |
| No unintended inheritance | Subsequent task without context | Sees neither Alice's nor Bob's Authentication. |
| Cleanup on completion | Task with context returns normally | Raw worker holds no principal afterward. |
| Cleanup on failure | Task with context throws an exception | Raw worker still holds no principal afterward. |
| Deliberate thread reuse | Two tasks on the same worker | Test does not rely on random scheduler thread selection. |
| No shared mutable context | Concurrent jobs, caller swaps Authentication | Job A does not suddenly become Bob. |
| No leaks in other holders | MDC/tenant/locale/request context | Each holder has its own cleanup rules. |

**Where to measure?** When inspecting a **raw executor worker** directly after `clearContext()`, `SecurityContextHolder.getContext().getAuthentication()` is normally `null`. When inspecting a **Servlet request** that passed through `AnonymousAuthenticationFilter`, an `AnonymousAuthenticationToken` may appear rather than `null`; this is **not** a logged-in user. Always define expected state by context, never using `isAuthenticated()` alone to distinguish anonymous from real users.

## 3. Standalone Java 17: Reproducing the ThreadLocal Bug

First observe the mechanism in plain Java SE, without Spring yet:

**`ThreadLocalReuseDemo.java`**

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ThreadLocalReuseDemo {

    private static final ThreadLocal<String> CURRENT_USER =
        new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            String first = pool.submit(() -> {
                CURRENT_USER.set("alice");
                // Intentionally broken: missing CURRENT_USER.remove().
                return CURRENT_USER.get();
            }).get();

            String leaked = pool.submit(() -> {
                return CURRENT_USER.get();
            }).get();

            // Must remove on the WORKER, not the caller thread.
            pool.submit(CURRENT_USER::remove).get();

            String after = pool.submit(() -> {
                return String.valueOf(CURRENT_USER.get());
            }).get();

            System.out.println("first=" + first);
            System.out.println("withoutCleanup=" + leaked);
            System.out.println("afterCleanup=" + after);
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run with JDK 17:

```bash
javac ThreadLocalReuseDemo.java
java ThreadLocalReuseDemo
```

**Exact stdout:**

```text
first=alice
withoutCleanup=alice
afterCleanup=null
```

Explanation: `newSingleThreadExecutor()` runs tasks sequentially on one worker; each `Future.get()` waits for the prior task to finish. Task B receives no username yet still reads Alice due to the leftover ThreadLocal. `CURRENT_USER.remove()` cleans the right worker. **This is only a Java SE ThreadLocal demo**, not a Spring Security program or safe implementation pattern.

## 4. JUnit 5 Test Suite for SecurityContextHolder

When using Spring Security Core, tests can live in a Spring Boot project that already includes **Spring Security** and **Spring Boot Starter Test** (JUnit Jupiter). Three essential tests: (1) controlled reproduction of the leak, (2) verifying `finally` cleanup on success/failure, (3) verifying a wrapper propagates identity per submission without leaving residue.

**`src/test/java/com/example/threadsecurity/SecurityContextReuseTest.java`**

```java
package com.example.threadsecurity;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutorService;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.*;

class SecurityContextReuseTest {

    @AfterEach
    void cleanupCallerThread() {
        SecurityContextHolder.clearContext();
    }

    private static SecurityContext contextFor(String username) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();

        context.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                username, "not-used",
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            )
        );
        return context;
    }

    private static String nameOnCurrentThread() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        return auth == null ? null : auth.getName();
    }

    @Test
    void reproducesLeakIfSomeoneForgetsCleanup() throws Exception {
        ExecutorService raw = Executors.newSingleThreadExecutor();
        try {
            long before = raw.submit(
                () -> Thread.currentThread().getId()
            ).get();

            raw.submit((Runnable) () ->
                SecurityContextHolder.setContext(contextFor("alice"))
            ).get();

            String leaked = raw.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get();

            long after = raw.submit(
                () -> Thread.currentThread().getId()
            ).get();

            assertEquals(before, after);
            // Educational test: PASSES when proving the deliberately created leak.
            assertEquals("alice", leaked);
        } finally {
            // Clean directly on the worker, even if an assertion failed.
            try {
                raw.submit(SecurityContextHolder::clearContext).get();
            } finally {
                raw.shutdownNow();
            }
        }
    }

    @Test
    void cleanupWorksEvenWhenTheDelegateThrows() throws Exception {
        ExecutorService raw = Executors.newSingleThreadExecutor();

        try {
            Future<String> first = raw.submit(() -> {
                SecurityContextHolder.setContext(contextFor("alice"));
                try {
                    return nameOnCurrentThread();
                } finally {
                    SecurityContextHolder.clearContext();
                }
            });

            assertEquals("alice", first.get());
            assertNull(raw.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());

            Future<?> failed = raw.submit((Runnable) () -> {
                SecurityContextHolder.setContext(contextFor("bob"));
                try {
                    throw new IllegalStateException("boom");
                } finally {
                    SecurityContextHolder.clearContext();
                }
            });

            ExecutionException exception = assertThrows(
                ExecutionException.class, failed::get
            );
            assertInstanceOf(
                IllegalStateException.class, exception.getCause()
            );

            assertNull(raw.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());
        } finally {
            raw.shutdownNow();
        }
    }

    @Test
    void delegatingExecutorScopesAliceBobAndAnonymous()
            throws Exception {

        ExecutorService raw = Executors.newSingleThreadExecutor();
        ExecutorService guarded =
            new DelegatingSecurityContextExecutorService(raw);

        try {
            SecurityContextHolder.setContext(contextFor("alice"));
            assertEquals("alice", guarded.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());

            // Probe the raw worker directly, bypassing the wrapper.
            assertNull(raw.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());

            SecurityContextHolder.setContext(contextFor("bob"));
            assertEquals("bob", guarded.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());

            assertNull(raw.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());

            SecurityContextHolder.clearContext();
            assertNull(guarded.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());

            assertNull(raw.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());
        } finally {
            SecurityContextHolder.clearContext();
            raw.shutdownNow();
        }
    }
}
```

**Interpreting test results accurately:**

- `reproducesLeakIfSomeoneForgetsCleanup` **deliberately** reproduces the bug and **PASSES** when detecting residual Alice. It demonstrates the cause; it does **not** prove a production app is safe.
- `cleanupWorksEvenWhenTheDelegateThrows` protects the invariant that no principal remains after both normal completion and exception-throwing tasks.
- `delegatingExecutorScopesAliceBobAndAnonymous` verifies Alice/Bob/no-user propagation while **probing the raw executor after each task** to catch residual identity.
- `SecurityContextHolder.clearContext()` in `@AfterEach` only cleans the **JUnit caller thread**. It does not clear ThreadLocals on worker threads; tests must use `finally`/wrappers on the worker.
- Each `contextFor(...)` builds a fresh context. Avoid sharing one mutable `SecurityContext` and swapping Authentication after submission.

**Watch out for red–green testing:** real application regression tests must assert **no authentication remains** after a task. Placing `assertNull(raw.submit(...).get())` right after the task that deliberately leaves Alice behind in the first test would make the test **FAIL**. After fixing the task with `try/finally` or a wrapper, that assertion must **PASS**. Never use "the leak-reproduction test is green" as proof that the bug was fixed.

## 5. Preventing Leaks at the Task Execution Layer

### 5.1 Using try/finally When Explicitly Setting SecurityContext

If a worker is completely application-owned, you can scope context like this:

```java
SecurityContext scoped = SecurityContextHolder.createEmptyContext();
scoped.setAuthentication(authenticationForThisTask);

try {
    SecurityContextHolder.setContext(scoped);
    performWork();
} finally {
    SecurityContextHolder.clearContext();
}
```

This is a **snippet inside a task**, not a standalone class. Never place `clearContext()` after `performWork()` without `finally`, as exceptions will skip cleanup. If an adapter framework already holds a valid context that must be preserved, use an appropriate scoped wrapper that **restores the prior state** rather than arbitrarily wiping someone else's context.

### 5.2 Using Spring Security Wrappers When Propagation Is Needed

Key wrappers:

- `DelegatingSecurityContextRunnable` / `DelegatingSecurityContextCallable`: runs a single task within a pre-selected context scope, handling appropriate cleanup/restoration.
- `DelegatingSecurityContextExecutor` / `DelegatingSecurityContextExecutorService`: wraps tasks upon submission to the executor; single-arg constructors can use the caller's context at submission time.
- `DelegatingSecurityContextAsyncTaskExecutor`: wraps `AsyncTaskExecutor` for `@Async` in Spring.

**Beware of fixed contexts:** some constructors accept a fixed `SecurityContext`. If initialized at startup with Alice's context, every task may run as Alice, even when submitted by Bob. For multi-user web apps, you normally need **per-submission** context capture, not an accidental fixed identity.

**Not every task should inherit a user.** Scheduled jobs, queue consumers, and background services may have no browser principal; in those cases choose an explicit service identity/authorization rather than borrowing "the last user".

### 5.3 MODE_INHERITABLETHREADLOCAL and MODE_GLOBAL Are Not Fixes

`MODE_INHERITABLETHREADLOCAL` copies values **when creating a child thread**, not when a new task is submitted. A pooled worker created during Alice's request can still carry Alice when processing Bob's task. Using inheritable mode to "make `@Async` see the user" can make the risk worse.

`MODE_GLOBAL` uses an application-wide context instead of per-thread and is unsuitable for concurrent multi-user requests. Keep the default `MODE_THREADLOCAL` strategy in Servlet apps and use lifecycle-scoped wrappers when genuinely needed.

### 5.4 SecurityContext Can Be Mutable

`SecurityContext` is a mutable object. If a caller invokes `SecurityContextHolder.getContext().setAuthentication(bobAuth)` on an object currently referenced by task A, task A may unexpectedly see Bob. Understand capture timing, create isolated contexts when needed, avoid storing `Authentication`/`SecurityContext` in shared static fields, and avoid mutating a context object passed to multiple concurrent tasks.

## 6. @Async Example Using a Safe Pooled Executor

Spring Boot Servlet example using a **single-worker** `ThreadPoolTaskExecutor` to make reuse easy to observe and a `DelegatingSecurityContextAsyncTaskExecutor` to propagate SecurityContext in the right scope.

**`src/main/java/com/example/asyncsecurity/AsyncConfig.java`**

```java
package com.example.asyncsecurity;

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

    @Bean("rawWorkerExecutor")
    ThreadPoolTaskExecutor rawWorkerExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(16);
        pool.setThreadNamePrefix("identity-worker-");
        pool.initialize();
        return pool;
    }

    @Bean("securityExecutor")
    AsyncTaskExecutor securityExecutor(
            @Qualifier("rawWorkerExecutor") ThreadPoolTaskExecutor raw) {
        return new DelegatingSecurityContextAsyncTaskExecutor(raw);
    }
}
```

**`src/main/java/com/example/asyncsecurity/IdentityJobService.java`**

```java
package com.example.asyncsecurity;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class IdentityJobService {

    @Async("securityExecutor")
    public CompletableFuture<String> currentUserName() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        String name = auth == null ? null : auth.getName();
        return CompletableFuture.completedFuture(name);
    }
}
```

**`src/main/java/com/example/asyncsecurity/AsyncSecurityApplication.java`**

```java
package com.example.asyncsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncSecurityApplication.class, args);
    }
}
```

To run as a Spring Boot project, you need Spring Boot 3.x, Spring Web, Spring Security, and Java 17+, running via `./gradlew bootRun` in a Gradle wrapper project (Windows `.\gradlew.bat bootRun`). These classes depend on Spring on the classpath and **do not compile with plain javac**.

`@Async` normally works through a Spring proxy. Calling `this.currentUserName()` from the same class can **bypass the proxy** and fail to run asynchronously. Call through a Spring-managed bean to ensure the `securityExecutor` executor is used.

### 6.1 Integration Test: Alice → Bob → No Principal

**`src/test/java/com/example/asyncsecurity/AsyncIdentityIsolationTest.java`**

```java
package com.example.asyncsecurity;

import java.util.List;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class AsyncIdentityIsolationTest {

    @Autowired IdentityJobService service;

    @Autowired
    @Qualifier("rawWorkerExecutor")
    ThreadPoolTaskExecutor raw;

    private void loginAs(String name) {
        SecurityContext ctx = SecurityContextHolder.createEmptyContext();
        ctx.setAuthentication(new UsernamePasswordAuthenticationToken(
            name, "not-used",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        ));
        SecurityContextHolder.setContext(ctx);
    }

    private String readRawWorker() throws Exception {
        return raw.submit(() -> {
            Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
            return auth == null ? null : auth.getName();
        }).get(5, TimeUnit.SECONDS);
    }

    @AfterEach
    void cleanupCaller() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void propagatesEachPrincipalAndLeavesWorkerClean() throws Exception {
        loginAs("alice");
        assertEquals("alice",
            service.currentUserName().get(5, TimeUnit.SECONDS));
        assertNull(readRawWorker());

        loginAs("bob");
        assertEquals("bob",
            service.currentUserName().get(5, TimeUnit.SECONDS));
        assertNull(readRawWorker());

        SecurityContextHolder.clearContext();
        assertNull(service.currentUserName().get(5, TimeUnit.SECONDS));
        assertNull(readRawWorker());
    }
}
```

With a `ThreadPoolTaskExecutor` configured as `corePoolSize=maxPoolSize=1`, the test deliberately reuses the same worker. `readRawWorker()` bypasses the wrapper and checks raw state after task completion. If the test fails, check the executor bean name, Spring `@Async` proxy, context capture at submission, mutable context, and other code calling `setContext` manually without cleanup.

## 7. Async in Spring MVC: Callable and DeferredResult

Not all async constructs share the same semantics.

**Controller returning `Callable<T>`:** Spring Security integrates with Servlet async processing (including `WebAsyncManagerIntegrationFilter`) to transfer security context into `Callable` execution and manage the lifecycle per the filter chain. Integration tests are still needed to verify business endpoints and principals.

**`DeferredResult<T>` or custom callbacks:** result-completing code may run on an application-managed thread. There is **no default guarantee** that the request's security context exists in arbitrary callbacks/producers. If identity is needed, choose an appropriate wrapper/context scope or pass verified **account ID/authorization intent** as validated data rather than relying on arbitrary ThreadLocals.

**`CompletableFuture.supplyAsync(...)`:** when using the common pool or another executor, caller context is **not automatically guaranteed**. Explicitly specify the executor used and add tests for that executor, rather than inferring CompletableFuture safety from `Callable` succeeding.

### 7.1 Callable Controller

**`src/main/java/com/example/asyncsecurity/AsyncController.java`**

```java
package com.example.asyncsecurity;

import java.util.concurrent.Callable;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AsyncController {

    @GetMapping("/api/whoami-async")
    public Callable<String> whoami() {
        return () -> {
            Authentication a =
                SecurityContextHolder.getContext().getAuthentication();
            return a == null ? "no-user" : a.getName();
        };
    }
}
```

**`src/main/java/com/example/asyncsecurity/WebSecurityConfig.java`**

```java
package com.example.asyncsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

### 7.2 MockMvc Testing with Two Users

Test dependencies (Gradle):

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**`src/test/java/com/example/asyncsecurity/CallableIsolationTest.java`**

```java
package com.example.asyncsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class CallableIsolationTest {

    @Autowired MockMvc mvc;

    @Test
    void twoRequestsSeeTheirOwnPrincipals() throws Exception {
        MvcResult alice = mvc.perform(
            get("/api/whoami-async").with(user("alice"))
        ).andExpect(request().asyncStarted()).andReturn();

        mvc.perform(asyncDispatch(alice))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

        MvcResult bob = mvc.perform(
            get("/api/whoami-async").with(user("bob"))
        ).andExpect(request().asyncStarted()).andReturn();

        mvc.perform(asyncDispatch(bob))
            .andExpect(status().isOk())
            .andExpect(content().string("bob"));
    }
}
```

This test verifies identity via **Servlet Callable**, yet **does not prove** both requests ran on the same physical thread. The `newSingleThreadExecutor()` check above is what forces worker reuse and deterministically catches residual identity. For `DeferredResult`, `CompletableFuture`, schedulers, and queue consumers, test against **the actual executor used in practice**.

## 8. Common Testing Mistakes

| Symptom | Why It Happens | Fix / Test |
| --- | --- | --- |
| No-leak test passes inconsistently | Scheduler picks two different workers. | Use a single-thread pool and `Future.get()`. |
| Task B sees Alice | Missing cleanup, wrapper unused, or inheritable context. | Probe raw worker after Alice, Bob, anonymous. |
| Failing task leaves user behind | `clearContext()` sits outside `finally`. | Inject an exception and assert worker is empty after failure. |
| `@Async` runs synchronously | Self-invocation/proxy bypass or missing `@EnableAsync`. | Call via Spring bean and specify the right executor. |
| `@Async` sees null authentication | Caller context not propagated. | Use `DelegatingSecurityContextAsyncTaskExecutor` if user context is truly needed. |
| Worker tasks always see the same user | Fixed SecurityContext wrapped for all submissions. | Use constructor/wrapper capturing context per submission. |
| Context changes while job is running | Sharing a mutable SecurityContext then changing Authentication. | Create separate contexts; never mutate after submit. |
| MDC logs still print Alice | MDC is a separate ThreadLocal. | Clean MDC separately in TaskDecorator/`finally`. |
| Servlet Callable works yet DeferredResult fails | Different propagation mechanisms. | Test DeferredResult's executor/callbacks. |
| Enabling MODE_INHERITABLETHREADLOCAL worsens leaks | Worker created under Alice and reused. | Keep MODE_THREADLOCAL; use propagation wrappers. |
| Cleaned on request thread yet worker still tainted | ThreadLocal is per-thread. | Clean on the worker itself inside the task. |
| Audit logs Alice in Bob's job despite clean SecurityContext | Custom tenant holder/actor ThreadLocal/cache still holds old state. | Test every context carrier, not just Spring Security. |

`MDC`, `RequestContextHolder`, `LocaleContextHolder`, and custom `ThreadLocal`s must be cleaned/managed independently. `DelegatingSecurityContextExecutorService` only handles **Spring Security context**; it does not clean MDC/tenant context. When using tracing, task decorators, or request attributes, verify the order in which contexts are set and restored; never leak identity into loggers or cross-tenant caches.

## 9. Regression Cases to Include in CI

| Test Case | Task A | Task B on Same Worker | Desired Assertion |
| --- | --- | --- | --- |
| Deliberate bug demo | Set Alice, omit clear. | Task without identity. | Detects leftover Alice to demonstrate root cause. |
| Normal cleanup | Scope Alice with `finally`. | Task without identity. | `Authentication == null`. |
| Failure cleanup | Scope Alice, throw `RuntimeException`. | Task without identity. | `Authentication == null`. |
| Principal switch | Alice wrapper. | Bob wrapper. | Alice right, Bob right; raw worker empty after each task. |
| Anonymous after multiple users | Alice → Bob. | Task without principal. | Sees neither Alice nor Bob. |
| Right context at submit time | Submit A then caller switches to B. | Job A runs afterward. | Does not unexpectedly become B from shared mutable object. |
| Servlet Callable | HTTP Alice. | HTTP Bob. | Endpoint returns each respective principal. |
| DeferredResult/custom callback | Alice task. | Bob/no-user task. | No leak; verify actual executor. |
| Cancellation/timeout | Task interrupted or fails. | Subsequent task. | No residual context. |
| Tenant/MDC | Actor Alice + tenant A. | Actor Bob + tenant B. | No actor/tenant/logging context leakage. |

**Red → green practice:** write tests asserting the raw pool has no Authentication after a task. If an implementation intentionally drops `finally`, the test **must fail**. Fix with cleanup or a Spring wrapper, then re-run until green. A leak-reproduction test where `assertEquals("alice", leaked)` passes is **not** a security acceptance test.

**Preventing flaky tests:** explicitly use a single-thread executor, await each `Future`, avoid sharing mutable contexts, isolate pools per test, set timeouts in integration tests, and clean up on both caller and worker. Also test exceptions/cancellations/rejected tasks matching your real executor. Never conclude risk is gone from a brief stress test.

## 10. Investigation and Implementation Checklist

1. Identify which executor runs the task: Servlet Callable, `@Async`, `CompletableFuture`, scheduler, queue consumer, or a third-party library pool.
2. Check the `SecurityContextHolder` strategy: default `MODE_THREADLOCAL`, or changed to `MODE_INHERITABLETHREADLOCAL`/`MODE_GLOBAL`.
3. Locate every `SecurityContextHolder.setContext`, `getContext().setAuthentication`, custom principal/tenant ThreadLocal, and cleanup site.
4. Separate requirements: does the job need to impersonate the user as of submission time, or should it use a service identity with verified actor data?
5. If propagation is needed, use the right `DelegatingSecurityContext*` wrapper and verify **per-submission** context rather than an unintended fixed identity.
6. Write a single-worker test: Alice, anonymous, Bob, anonymous, exception, anonymous. Assert the raw worker has no stale user.
7. Test Servlet async separately: `Callable` has built-in security context integration, while `DeferredResult`/custom executors need explicit configuration.
8. Never place mutable `SecurityContext` in static/global fields, and never enable inheritable/global as a "quick fix".
9. Cover MDC/tenant/locale/request-scoped state and logging/auditing. Clean state in one holder does not prove all other contexts are clean.
10. If evidence of an actual leak exists, audit data access, audit logs, and background job systems and conduct a security incident review before closing the issue.

## 11. Key Takeaways

**Thread-local identity is not permanently bound to a request: it is bound to a thread, and thread pools reuse threads.** Bob's task must never see Alice's `Authentication` just because it reused an old worker. To test reliably, **force reuse of the same worker**, run sequences of multiple principals and identity-less tasks, exercise exception paths, and inspect **raw worker state** after every task. When propagation is required, use Spring Security wrappers with proper lifecycles; when setting context manually, guarantee `try/finally`. Always check other carriers like MDC/tenant too, because cleaning `SecurityContextHolder` does not clean them automatically.
