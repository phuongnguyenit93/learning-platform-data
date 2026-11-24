# DelegatingSecurityContextRunnable and DelegatingSecurityContextCallable — Propagating SecurityContext Across Async Threads

## 1. Objective

In a **Spring Security Servlet (Spring Boot 3.x, Spring Security 6.x, Java 17+)** application, the current caller's information normally resides in `SecurityContextHolder`, managed by default with **`ThreadLocal`**. When work runs on another thread—for instance via an `ExecutorService`, a thread pool task, `@Async`, or a `CompletableFuture` callback—the worker thread **does not automatically receive the request's SecurityContext**.

`DelegatingSecurityContextRunnable` and `DelegatingSecurityContextCallable` provide a way to **wrap a task** so it sets a `SecurityContext` on the task-executing thread, invokes the real work, and restores the prior security state in `finally`.

After this lesson, you can:

1. Distinguish `SecurityContext`, `Authentication`, `GrantedAuthority`, and the `ThreadLocal` mechanism.
2. Wrap `Runnable`/`Callable` to propagate context when a task executes on another thread.
3. Understand the difference between an **explicit context passed by the caller** and the **context active when the wrapper is created**.
4. Verify that context is **restored or cleared** after the task runs, even when an exception occurs.
5. Choose `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextExecutorService`, or `DelegatingSecurityContextAsyncTaskExecutor` when handling many tasks.
6. Recognize risks of cross-task privilege leakage in thread pools, stale contexts, expired sessions, and post-request execution.

This lesson covers **Spring Security Servlet and Java tasks on other threads** only. Do not apply this `ThreadLocal`-copying pattern verbatim to Spring Security WebFlux/Reactor, where the security context is normally carried via **Reactor Context**.

## 2. Why Does Async Lose Login Information?

### 2.1. SecurityContextHolder Is Not a Global Variable Across All Threads

In the standard model:

- `SecurityContext` holds the current `Authentication`.
- `Authentication` describes the principal, credentials, authority list, and authenticated status.
- `SecurityContextHolder.getContext()` looks up the context **of the currently running thread** via `SecurityContextHolderStrategy`.
- In Spring Security Servlet, the default strategy is normally `MODE_THREADLOCAL`.

Once a servlet request has been authenticated, the filter chain sets `SecurityContext` for the request-processing thread. After the request finishes, Spring Security performs appropriate cleanup so the previous request's Authentication is not retained on a reused container thread.

If the same request submits a task to an `ExecutorService`:

```text
Servlet thread (request A)                 Worker thread in thread pool
---------------------------------          --------------------------------
SecurityContext: alice
submit(task)  ------------------------->    SecurityContext: usually empty
                                           task reads getContext()
                                           authentication == null
<--------------------------------------    task finishes
```

This is a **thread boundary** issue, not necessarily a login failure: `alice` was authenticated on the request thread, yet a worker thread has an independent `ThreadLocal`.

### 2.2. Why Not "Fix" It with MODE_GLOBAL or InheritableThreadLocal?

`SecurityContextHolder.MODE_GLOBAL` shares one context across the entire JVM: extremely dangerous for multi-user applications because one request can see another request's privileges.

`MODE_INHERITABLETHREADLOCAL` copies ThreadLocal values when **creating a child thread**, not per invocation when reusing an existing worker thread. With a thread pool, threads are pre-created and reused many times, making this approach both **unreliable for passing the right caller** and risky for retaining stale privileges. Never enable it globally just to fix one async task.

The solution here is to **bind the SecurityContext to the execution scope of the exact task**, rather than changing the application-wide strategy.

## 3. Mechanics of the Two Wrappers

### 3.1. DelegatingSecurityContextRunnable

This class implements `Runnable`. It holds:

- `delegate`: the `Runnable` that actually performs the work.
- `delegateSecurityContext`: the context intended for use while the delegate runs.

Conceptual model (pseudocode, **not verbatim framework source code**):

```java
SecurityContext previous = SecurityContextHolder.getContext();
try {
    SecurityContextHolder.setContext(delegatedContext);
    delegate.run();
} finally {
    // Restore previous, or clear context if previous was empty.
    restoreOrClear(previous);
}
```

Preserving the **previous context** and handling cleanup in `finally` is crucial. A worker thread may execute thousands of tasks; without cleanup, user A can leave authorities behind for user B's task or an unauthenticated job.

Spring Security performs set/restore/clear through `SecurityContextHolderStrategy`; do not copy pseudocode into a production `Runnable` and drop details around empty contexts, exceptions, or custom strategies.

### 3.2. DelegatingSecurityContextCallable<V>

`Callable<V>` returns a value of type `V` and may throw checked exceptions. `DelegatingSecurityContextCallable<V>` performs the **same propagation and cleanup mechanism** while returning the result from `delegate.call()`.

| Criterion | `DelegatingSecurityContextRunnable` | `DelegatingSecurityContextCallable<V>` |
| --- | --- | --- |
| Wrapped interface | `Runnable` | `Callable<V>` |
| Delegate method | `void run()` | `V call() throws Exception` |
| Result | No direct business return value | Returns result of type `V` |
| Submission to `ExecutorService` | `submit(Runnable)` | `submit(Callable<V>)` |
| Propagates SecurityContext | Yes | Yes |
| Cleans/restores context | In `finally` | In `finally` |
| Exceptions | Unchecked errors; when submitted, may wrap in `ExecutionException` | Checked/unchecked; `Future.get()` may throw `ExecutionException` |

Both only **bring the SecurityContext to where the work runs**. They do not grant new authorities, create login sessions, fetch access tokens, or replace authorization decisions.

## 4. Two Ways to Construct the Wrappers and Capture Timing

### 4.1. Capturing the Current Context at Wrapper Creation

```java
Runnable wrapped =
    new DelegatingSecurityContextRunnable(originalRunnable);

Callable<String> wrappedCall =
    new DelegatingSecurityContextCallable<>(originalCallable);
```

In constructors without an explicit context parameter, Spring Security uses the context of the **calling thread at wrapper instantiation time**, keeping that context for when the task runs. Create the wrapper **while on a thread holding the right Authentication**, typically the request thread after Spring Security authenticates.

Never create a single wrapper at application startup when no user is logged in and reuse it for all users' tasks; it will not automatically pick up the new per-request Authentication.

### 4.2. Passing an Explicitly Chosen Context

```java
SecurityContext context = SecurityContextHolder.getContext();

Runnable wrapped =
    new DelegatingSecurityContextRunnable(originalRunnable, context);

Callable<String> wrappedCall =
    new DelegatingSecurityContextCallable<>(
        originalCallable, context);
```

This is an **API usage snippet inside a method that already has delegate variables**, not a standalone Java class. Explicit context is useful when:

- You want exact control over which context is used.
- Context was collected at the request boundary and the task is constructed in another layer.
- A **controlled, authorized service identity** must be established for a system task, with clear auditing and bounds.

**Warning:** passing a fixed context with `ADMIN` privileges to a wrapper/executor serving multiple users causes every task going through that wrapper to run under those privileges. Only use a service identity when architecture and audit allow it; never "borrow" another user's Authentication.

### 4.3. Capture Does Not Mean Deep-Copy

`SecurityContext` is a mutable object. Wrapper constructors normally **hold a reference** to the context rather than creating an immutable snapshot of the entire principal, authorities, or credentials. If other code replaces `Authentication` inside the same object before the worker runs, the worker may observe that change.

If information needs to be frozen for the work:

- Consider creating a new `SecurityContext` containing a controlled Authentication with a defined lifecycle.
- Understand that assigning the same `Authentication` to a new context is still a **shallow copy**, not cloning all principals/credentials.
- Better for long-lived jobs: turn **authorized identity/tenant/source ID** into minimal command data, then re-verify permissions in the service at execution time instead of retaining a session context for hours.

## 5. Runnable Java 17+ Example: Losing Context and Restoring Context

The example uses **Spring Security Core** and a single-threaded `ExecutorService`. You can create a new Gradle project with the two files below. No servlet container is needed to demonstrate the ThreadLocal boundary; the wrapper logic is the exact logic used in Servlet applications.

### 5.1. File `build.gradle` (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.4.1')
    implementation 'org.springframework.security:spring-security-core'

    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.SecurityContextPropagationDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use a Spring Boot 3.x BOM to manage compatible Spring Security 6.x and JUnit versions. In a Spring Boot project with existing dependency management, use the project-managed versions instead of forcing another BOM. The Gradle sample requires Java 17 and a Gradle version compatible with Java/toolchains.

### 5.2. File `src/main/java/demo/SecurityContextPropagationDemo.java`

```java
package demo;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.security.concurrent.DelegatingSecurityContextCallable;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public final class SecurityContextPropagationDemo {

    static String currentUser() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();
        return authentication == null ? "none" : authentication.getName();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            SecurityContext aliceContext =
                SecurityContextHolder.createEmptyContext();

            aliceContext.setAuthentication(
                new UsernamePasswordAuthenticationToken(
                    "alice",
                    "not-a-real-password",
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))
                )
            );

            SecurityContextHolder.setContext(aliceContext);

            System.out.println("main=" + currentUser());

            // The worker thread does not automatically inherit the main thread's context.
            String raw = pool.submit(
                (Callable<String>) SecurityContextPropagationDemo::currentUser
            ).get();
            System.out.println("raw=" + raw);

            Runnable delegate = () ->
                System.out.println("runnable=" + currentUser());

            // 1-arg constructor captures context when wrapping the task.
            Runnable securedRunnable =
                new DelegatingSecurityContextRunnable(delegate);
            pool.submit(securedRunnable).get();

            // 2-arg constructor accepts an explicit context.
            Callable<String> securedCallable =
                new DelegatingSecurityContextCallable<>(
                    SecurityContextPropagationDemo::currentUser,
                    aliceContext
                );

            System.out.println(
                "callable=" + pool.submit(securedCallable).get());

            // If the wrapper cleans up properly, the worker again has no Authentication.
            String after = pool.submit(
                (Callable<String>) SecurityContextPropagationDemo::currentUser
            ).get();
            System.out.println("workerAfter=" + after);

        } finally {
            SecurityContextHolder.clearContext();
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```bash
gradle --quiet run
```

If the project already has a Gradle Wrapper generated, use `./gradlew --quiet run` on Bash/macOS/Linux or `.\gradlew.bat --quiet run` on Windows PowerShell.

**Expected stdout in a standard startup environment (with no other process modifying ThreadLocal):**

```text
main=alice
raw=none
runnable=alice
callable=alice
workerAfter=none
```

**Why is the output deterministic?**

1. `SecurityContextHolder` on the main thread holds `alice`, so `main=alice`.
2. `Executors.newSingleThreadExecutor()` uses a separate worker; the worker's ThreadLocal is not set yet, so `raw=none`.
3. `DelegatingSecurityContextRunnable` is created **on the main thread while `aliceContext` is active**, so the wrapper attaches that context to the worker during execution and prints `runnable=alice`.
4. `DelegatingSecurityContextCallable` receives `aliceContext` directly, returning `"alice"` via `Future.get()`.
5. After both wrapped tasks, the wrapper restores/clears the prior context; the next plain task runs on the **same single-threaded pool** yet does not see `alice`, so `workerAfter=none`.

`Future.get()` here waits for the prior task to finish, making output line ordering deterministic. **Never use `Thread.sleep()` to "wait for context propagation"**: propagation occurs when the wrapper runs on the worker, independent of sleep durations. Multi-threaded apps must test synchronization/correlation properly.

### 5.3. `Callable` and Return Values

When a task produces a result, the generic type is preserved:

```java
Callable<String> delegate = () ->
    SecurityContextHolder.getContext().getAuthentication().getName();

Callable<String> secured =
    new DelegatingSecurityContextCallable<>(delegate);

String username = pool.submit(secured).get();
```

This snippet assumes execution in a scope with `pool` and a valid Authentication, like the program above. If `delegate.call()` throws an exception, `Future.get()` throws `ExecutionException` (or `InterruptedException` if the waiting thread is interrupted); the root error is in `getCause()`. The wrapper still cleans up in `finally`.

Never catch exceptions and return a "success" result if the task was actually denied for lacking permissions; propagate the error or map it to an explicit business error.

## 6. Testing: Verifying Zero Context Leakage Between Tasks

A bug more dangerous than `authentication == null` is **user A remaining on the worker and user B receiving A's privileges**. Therefore, tests must verify not only that context appears inside the delegate, but also **the context after the task**.

File `src/test/java/demo/ContextPropagationTest.java`:

```java
package demo;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextCallable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class ContextPropagationTest {

    @Test
    void callablePropagatesThenCleansWorkerContext() throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(
                new UsernamePasswordAuthenticationToken(
                    "alice",
                    "unused",
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))
                )
            );

            SecurityContextHolder.setContext(context);

            Callable<String> action = () ->
                SecurityContextHolder.getContext()
                    .getAuthentication().getName();

            Callable<String> wrapped =
                new DelegatingSecurityContextCallable<>(action);

            assertEquals("alice", pool.submit(wrapped).get());

            Authentication workerAuthentication = pool.submit(
                (Callable<Authentication>) () ->
                    SecurityContextHolder.getContext().getAuthentication()
            ).get();

            assertNull(workerAuthentication);
        } finally {
            SecurityContextHolder.clearContext();
            pool.shutdownNow();
        }
    }
}
```

Run:

```bash
gradle --quiet test
```

This test verifies **propagation and cleanup on a worker pool**; it does not prove a user is authorized to call a specific API. To verify authorization, add Spring MVC/Method Security tests with `hasAuthority` or `@PreAuthorize` on a real service.

### 6.1. Testing the Exception Path

A correct wrapper must restore/clear context **even when the delegate throws an error**. You can swap the task for a `Callable` that throws `IllegalStateException("demo")`, call `.get()` with `assertThrows(ExecutionException.class, ...)`, then submit an unwrapped task to verify Authentication on the worker is null. Do not swallow test errors; if `finally` fails to run, the test must fail.

### 6.2. Testing with Multiple Users

On the same single-threaded executor, sequentially:

1. Set `alice`'s SecurityContext, create wrapper A, and submit.
2. Replace the caller's context with `bob`'s context, create wrapper B, and submit.
3. Verify A sees `alice`, B sees `bob`, and a subsequent unwrapped task sees `null`.

Crucial: **create separate wrappers inside each user's respective context**; never pre-create wrapper A and reuse it for B. Do not test with `SecurityContextHolder.MODE_GLOBAL`, as it masks real thread boundaries.

## 7. Why Must Context Be Restored, Not Merely Cleared?

Consider two scenarios:

- The worker initially had **no** Authentication. The wrapper sets user A's context, runs the task, and clears it. The right outcome is that the worker once again has no Authentication.
- The worker initially held a valid context **from another controlled scope**. The wrapper temporarily swaps in context A, runs the task, and **restores the original context** so as not to corrupt the outer caller's state.

Hence the accurate statement is **"restore the previous context or clear when previously empty"**, not "the wrapper always calls clearContext in every case". This matters even more when wrappers are nested.

```text
Worker starts: context X
  └─ Runnable wrapper A: context A
       └─ Callable wrapper B: context B
            └─ call() finishes -> back to A
       └─ run() finishes -> back to X
```

In real applications, wrappers are commonly used to attach context to an initially empty worker thread; restore logic remains an important part of the safety contract.

## 8. When Many Tasks Exist: Wrap the Executor Instead of Individual Runnables/Callables

Manual wrappers fit a few tasks. When every submission in a subsystem requires propagation, you can wrap the entire executor with Spring Security:

- `org.springframework.security.concurrent.DelegatingSecurityContextExecutor`
- `org.springframework.security.concurrent.DelegatingSecurityContextExecutorService`
- `org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor`

With an `ExecutorService`:

```java
ExecutorService underlying = Executors.newFixedThreadPool(4);

// ExecutorService wrapper automatically wraps submitted Runnables/Callables.
ExecutorService secured =
    new DelegatingSecurityContextExecutorService(underlying);

try {
    // Call submit within the caller's SecurityContext scope.
    Future<String> result = secured.submit(() ->
        SecurityContextHolder.getContext()
            .getAuthentication().getName());

    String username = result.get();
} finally {
    secured.shutdown();
}
```

This snippet belongs inside a method with imports for `ExecutorService`, `Executors`, `Future`, `DelegatingSecurityContextExecutorService`, and `SecurityContextHolder`; it must execute in a scope with Authentication to avoid null. A `DelegatingSecurityContextExecutorService` **without an explicit context** normally captures the caller's context at **submission** time, which is better than holding a pre-built wrapper from startup.

If the constructor is passed a **fixed SecurityContext**, all tasks on that wrapper use that same context. This suits controlled service accounts, **not** executors serving multiple users with distinct permissions. When using a wrapped executor, avoid redundantly double-wrapping tasks, which makes tracking context and lifecycle harder to follow.

### 8.1. ExecutorService Does Not Turn a Task into a New Request

If `Future.get()` waits long on the request thread, the request remains held; even though the work uses an executor, the caller may still delay the HTTP response. Consider timeouts, queue capacity, cancellation, and splitting long duties into independent jobs.

Propagating `SecurityContext` only solves **identity inside the task**. It does not automatically preserve JPA transactions, persistence contexts, MDC tracing, request attributes, or the servlet request's locale. Those contexts require dedicated mechanisms if genuinely needed; do not treat a SecurityContext wrapper as "copying the whole request".

## 9. Combining with Spring `@Async` in Servlet Applications

`@Async` typically uses a `TaskExecutor` and runs the method in a thread pool. An `@Async` method is **not automatically** guaranteed to receive the request's Authentication merely because the annotation is present. You can use `DelegatingSecurityContextAsyncTaskExecutor` to wrap a delegate `ThreadPoolTaskExecutor`.

### 9.1. Configuring the `AsyncTaskExecutor` Bean

Assume a Spring Boot 3 application already has `spring-boot-starter-security`, `spring-boot-starter-web`, method security if using `@PreAuthorize`, and dependencies for Spring `@Async`.

Illustrative file `AsyncSecurityConfig.java`:

```java
package com.example.web;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
public class AsyncSecurityConfig {

    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("secured-async-");
        executor.initialize();
        return executor;
    }

    @Bean("securityTaskExecutor")
    AsyncTaskExecutor securityTaskExecutor(
            @Qualifier("applicationTaskExecutor")
            ThreadPoolTaskExecutor delegate) {

        return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
    }
}
```

`AsyncTaskExecutor` wraps the delegate using the **caller's context at submission time**, so the worker sees the corresponding Authentication and the wrapper cleans up the context after execution. `ThreadPoolTaskExecutor` is managed as a bean with explicit pool/queue settings; never spin up a new pool per request.

In real environments, choose pool size/queue/timeout according to load and configure graceful shutdown. Async tasks carrying user context must be protected during logging, on failure, and upon job cancellation.

### 9.2. Async Service and Caller

Illustrative file `AuditService.java`:

```java
package com.example.web;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class AuditService {

    @Async("securityTaskExecutor")
    public CompletableFuture<String> currentActor() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        String actor = authentication == null
            ? "none"
            : authentication.getName();

        return CompletableFuture.completedFuture(actor);
    }
}
```

If a controller/service in **another bean** calls `auditService.currentActor()` from an authenticated request thread, the task is dispatched via `securityTaskExecutor`, captures the caller's context, and returns `CompletableFuture<String>`. Do not call `this.currentActor()` from inside the same bean expecting the `@Async` proxy to apply: **self-invocation** can bypass the proxy and run synchronously.

This is an example inside a Spring Boot application, **not a single-file program compilable directly with `javac`**, because it needs the framework, application context, and security configuration. In real APIs, before the task performs a sensitive action, enforce authorization checks at the proper execution site; the mere presence of Authentication does not equal permission.

### 9.3. CompletableFuture.supplyAsync

The following **does not** automatically propagate SecurityContext:

```java
CompletableFuture<String> task =
    CompletableFuture.supplyAsync(() ->
        SecurityContextHolder.getContext()
            .getAuthentication().getName());
```

Omitting an executor usually defaults to `ForkJoinPool.commonPool()`; the worker lacks the servlet thread's context and may throw `NullPointerException`. Use an executor **wrapped for propagation**:

```java
CompletableFuture<String> task =
    CompletableFuture.supplyAsync(
        () -> SecurityContextHolder.getContext()
            .getAuthentication().getName(),
        securedExecutor
    );
```

Here `securedExecutor` is an `Executor` wrapped with `DelegatingSecurityContextExecutor` or another compatible executor provisioned for the right scope. Any subsequent async stages (`thenApplyAsync`, `thenComposeAsync`...) may switch to a different executor; any stage needing Authentication must use an executor with proper propagation. Do not assume context automatically "follows along" the entire `CompletableFuture` chain.

## 10. Spring MVC Async and Other Mechanisms

### 10.1. Controller Returning Callable

Spring Security Servlet includes built-in support for **Spring MVC asynchronous `Callable`** via `WebAsyncManagerIntegrationFilter` and Spring's integration mechanism. In standard Spring Security setups, the request's context can be established appropriately when the `Callable` runs on MVC's thread.

This differs from calling `executor.submit(...)` directly in an arbitrary service. Do not indiscriminately double-wrap an MVC `Callable` when the framework integration already manages it. Test in practice with your exact Spring Security version and async executor configuration.

### 10.2. DeferredResult, ResponseBodyEmitter, Custom Threads

With `DeferredResult`, `ResponseBodyEmitter`, `SseEmitter`, servlet callbacks, or manually created threads, developers may need to actively manage context at **the exact code where execution happens**. Never extrapolate that `Callable` integration means every MVC async construct automatically propagates authentication.

### 10.3. WebFlux/Reactor

In **Spring WebFlux**, `ReactiveSecurityContextHolder` relies on Reactor Context. Using `DelegatingSecurityContextRunnable` to capture `ThreadLocal` is not the standard model for an entire reactive pipeline. If a system uses both Servlet and Reactive, distinguish concurrency models clearly before picking a security context propagation approach.

## 11. Security Boundaries: Propagation Is Not Authorization

### 11.1. The Current SecurityContext May Be Anonymous

On certain filter chains, `SecurityContextHolder.getContext().getAuthentication()` may be an `AnonymousAuthenticationToken` instead of null. **Do not treat `authentication != null` as proof that a real user is logged in**.

When authorization is needed, use `AuthorizationManager`, `hasAuthority`, `@PreAuthorize`, or Spring Security's authentication trust resolver per your actual config. `isAuthenticated()` on certain Authentication types also differs from "verified interactive user"; test security policies at the business layer rather than relying solely on `getName()`.

### 11.2. Stale Context Remains Stale Context

For instance, a user submits a task at 10:00, then logs out or loses permissions before the task runs at 10:30. Wrapping `SecurityContext` **does not automatically revalidate** the session, password, database roles, or access token at runtime. If a job mutates data or calls critical services after a delay, define permission checks **at execution time**, deadlines, and cancellation mechanisms.

For long-lived background jobs, use a verified `jobId`, `subjectId`, `tenantId`, and an explicit execution policy instead of persisting `SecurityContext` objects in a durable queue. Avoid serializing Authentication with credentials into a message broker.

### 11.3. Never Leak One User's Context to Another User

A shared pool may serve many callers, yet each task must capture the **right caller's** context. If you create a singleton:

```java
SecurityContext adminContext = ...; // demo: privileged context
Runnable wrapped = new DelegatingSecurityContextRunnable(task, adminContext);
```

then every call to `wrapped.run()` uses **adminContext**, regardless of which user enqueued the task. This snippet is intentionally **not standalone runnable Java**: it illustrates an anti-pattern to avoid in multi-tenant/multi-user applications. Never use a static privileged principal to "fix" a null context error.

### 11.4. Do Not Arbitrarily Retain Request-Scoped Objects

`HttpServletRequest`, transactions, Hibernate sessions, `RequestContextHolder`, MDC logging, tracing baggage, and locale have different lifecycles/transports than `SecurityContext`. Security propagation does not guarantee those objects remain valid when the task runs.

If a task needs request data, extract only the minimal immutable values required, enforce authorization before and at the point of use, and pass them as parameters to the task. Never hold references to the request or response for use after the HTTP request ends.

## 12. Common Issues and Troubleshooting Table

| Symptom | Possible Cause | Diagnosis and Fix |
| --- | --- | --- |
| Request thread has user, worker has `authentication == null` | `ThreadLocal` does not cross Executor | Wrap task with DelegatingSecurityContextRunnable/Callable or appropriate executor |
| First task has right user, later task has wrong user | Worker retained old context or wrapper misused | Verify cleanup, new wrapper per caller, test one pool with multiple users |
| `@Async` method sees no principal | Executor unwrapped or `@Async` proxy not applied | Use `DelegatingSecurityContextAsyncTaskExecutor`, `@EnableAsync`, call via bean proxy |
| Context still wrong after adding wrapper | Wrapper created at startup or on another thread lacking Authentication | Verify **wrapper creation/capture time**, not just submission time |
| All tasks always run under one user | Fixed-context constructor used on multi-user pool | Switch to per-submit/per-caller capture; remove unauthorized fixed service principal |
| `Callable` throws error on `.get()` | Delegate threw exception, Future wraps in `ExecutionException` | Inspect `getCause()`; verify wrapper cleanup in finally |
| Worker still holds `alice` after task | Code manually called setContext without restoring, or task bypassed wrapper | Use standard wrapper and test workerAfter; inspect nested wrappers |
| Later `CompletableFuture` stage loses user | Stage moved to common pool or unwrapped executor | Supply wrapped Executor for **every async stage** needing context |
| Auth lost after logout, yet job still has user | Job captured old context before logout | Re-authorize at job runtime; enforce timeout/revocation as required |
| Authentication exists, yet access is denied | Anonymous principal, missing GrantedAuthority, or different policy | Verify actual authentication and policy; do not grant extra permissions via wrapper |
| `hasAuthority` inside worker not enforced | Only reading principal, not passing through security guard | Place method/authorization guard on executing service |
| Thread pool leaks data across tenants | Stale context, shared mutable context, or missing tenant check | Wrap per caller, restore context, verify tenant on every resource |
| Spring MVC `Callable` works, custom executor does not | MVC has built-in integration, self-managed executor does not | Evaluate each async boundary and choose appropriate wrapper |
| Used `MODE_INHERITABLETHREADLOCAL` yet still broken | Thread pool reuses existing threads | Do not use that strategy to replace per-task propagation |
| Trying to send SecurityContext to another service over HTTP | `ThreadLocal` exists only inside the JVM | Use network authentication/token delegation mechanisms; do not serialize context |

### 12.1. Safe Logging Recommendations

When debugging in controlled environments, log minimally:

- Thread name, task ID, and correlation ID.
- Authentication type (or **non-sensitive principal name** permitted by logging policy).
- Authorized/denied status and policy name.
- Capture, submit, execute, and finish timestamps.
- Whether context was restored/cleared after the task (tests or debug-only).

Never log raw passwords, Bearer tokens, session cookies, private keys, or credentials inside `Authentication`. Never dump the entire `SecurityContext` object to centralized logs.

## 13. Safe Implementation Checklist

- [ ] Identify exact thread boundaries: servlet request → executor, `@Async`, `CompletableFuture`, or Spring MVC async.
- [ ] For single tasks, choose `DelegatingSecurityContextRunnable` or `DelegatingSecurityContextCallable` matching the return type.
- [ ] Capture the **right caller's** context when creating the wrapper, or use explicit context only under clear policy.
- [ ] For many tasks, use `DelegatingSecurityContextExecutor(Service)` or `DelegatingSecurityContextAsyncTaskExecutor`; avoid rewriting ThreadLocal logic.
- [ ] Guarantee the wrapper restores the previous context or clears on task completion, **even on exceptions**.
- [ ] Test multiple users on the same worker pool, and verify subsequent unwrapped tasks see no leftover Authentication.
- [ ] Never use `MODE_GLOBAL` or `MODE_INHERITABLETHREADLOCAL` as a default solution for multi-user web apps.
- [ ] Never treat context propagation as a substitute for authorization, CSRF, token validation, or tenant/resource checks.
- [ ] For delayed jobs, enforce TTL/timeout policies and re-check permissions at execution time.
- [ ] Do not assume request/transaction/MDC follow from SecurityContext propagation; use dedicated mechanisms.
- [ ] Never transmit SecurityContext across the network or message brokers as a reusable credential.
- [ ] Clearly separate Spring Security Servlet from Reactor/WebFlux when designing async pipelines.

**Conclusion:** `DelegatingSecurityContextRunnable` and `DelegatingSecurityContextCallable` are **task-level adapters** that set the caller's SecurityContext on the task-executing thread and **clear/restore** state so thread pools do not leak privileges. When many tasks need this, wrap the executor instead of wrapping each task manually; with `@Async` or async stages, verify the exact executor and capture timing. Having Authentication on a worker does **not** by itself prove the user is still permitted to perform a sensitive action at execution time: authentication, authorization, and session lifecycles must still be controlled independently.
