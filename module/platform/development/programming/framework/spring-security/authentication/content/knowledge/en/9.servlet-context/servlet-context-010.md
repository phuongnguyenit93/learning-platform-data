# Propagating Identity to Background Tasks with DelegatingSecurityContext Classes

> **Scope:** Spring Security Authentication on the **Servlet stack** (Spring MVC, Java 17+). The topic is propagating `SecurityContext` from the request-processing thread to `Runnable`, `Callable`, `Executor`, `ExecutorService`, and `@Async` tasks using the `DelegatingSecurityContext...` family of classes. The lesson clearly explains **when the context is captured**, task permissions, cleanup/restoration on thread pools, how this differs from session persistence, and safety boundaries. Includes a standalone runnable Gradle + Java 17 project using **Spring Security Core 6.5.11**, with deterministic stdout and a failing-task scenario.

## 1. The Problem: HTTP Request Has a User, Background Thread Sees None

Inside a logged-in request, Spring Security normally allows:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

String username = authentication.getName();
```

This is a **snippet inside an authenticated request**, not a complete program. On the Servlet stack, `SecurityContextHolder` defaults to `ThreadLocal` to store the **current thread's** `SecurityContext`. This helps controllers, services, and methods running on the same thread: no `Authentication` parameter needs to be passed through every function.

However, a background task typically runs on a **different thread**:

```java
// Anti-pattern: do not assume this task sees the same identity as the request.
executor.execute(() -> {
    Authentication current =
            SecurityContextHolder.getContext().getAuthentication();
    // current may be null, or an unexpected identity if a thread leaked.
});
```

If a service is protected with `@PreAuthorize`, a missing context can cause the task to be denied. Worse, if a developer manually attaches `Authentication` to a thread pool **without cleaning it up**, the reused thread can carry the previous request's identity into a subsequent request.

Spring Security provides **`DelegatingSecurityContext...`** classes to solve **putting the appropriate context onto the executing thread, running the work, and then restoring/clearing state**. This is **context propagation**, not re-verifying passwords, creating sessions, or granting extra permissions.

### Learning Objectives

After this lesson, you should be able to:

1. Explain why `SecurityContextHolder` does not automatically move from the request thread to a thread pool by default.
2. Distinguish `SecurityContext`, `Authentication`, `SecurityContextHolder`, and `SecurityContextRepository`.
3. Choose the right `DelegatingSecurityContextRunnable`, `Callable`, `Executor`, `ExecutorService`, or `AsyncTaskExecutor`.
4. Know that a constructor **taking a `SecurityContext`** normally applies **a fixed context**, whereas an executor's no-context constructor normally **captures the context when the task is submitted**.
5. Recognize the difference between **wrapper creation time**, **task submission time**, and **worker execution time**.
6. Ensure cleanup/restoration when a task succeeds, fails, or when a thread pool reuses a worker.
7. Avoid putting request identities into multi-hour jobs, jobs re-running after logout, or distributed queue systems.
8. Test that the task sees the right user and subsequent tasks suffer no authority leakage.

## 2. Four Concepts That Must Not Be Merged Into One

| Component | Role | Does Not Handle |
| --- | --- | --- |
| `Authentication` | Principal, authenticated status, and authorities of an authentication | Does not travel to another thread automatically |
| `SecurityContext` | Holds the `Authentication` of an execution context | Does not save into HTTP session automatically |
| `SecurityContextHolder` | Holds/reads the context bound to the thread or chosen strategy | Does not create permissions or verify passwords itself |
| `SecurityContextRepository` | Saves/restores context across scopes such as HTTP session/request | Does not propagate context to `ExecutorService` |

The **lifecycle within a Servlet request** can be visualized as:

```text
Request thread T1:
SecurityContextHolderFilter
    ↓ loads SecurityContext from repository
Controller / service sees Authentication for "mai"
    ↓ submits work to thread pool
Request completes
    ↓ T1's holder is cleared by framework

Worker thread T2:
    if plain Runnable -> does not automatically get "mai"'s context
    if using DelegatingSecurityContext -> sets the right context for the task
    ↓ runs work
    ↓ finally: cleanup / restore previous context
```

**Important:** `SecurityContextRepository.saveContext(...)` persisting login for the **next HTTP request** is different from `DelegatingSecurityContext...` transferring context to the **thread executing a task**. One mechanism does not replace the other. If a controller logs in manually without saving the session, the wrapper can let a worker see the user during the current request; that **does not prove** the session was saved for the browser.

### Default ThreadLocal, InheritableThreadLocal, and Global

`SecurityContextHolder` supports multiple strategies, yet for typical Servlet applications, the default `MODE_THREADLOCAL` is the right choice. Two other modes require caution:

- `MODE_INHERITABLETHREADLOCAL`: child threads can inherit the value when the thread is created, which **does not mean** picking up the new user each time a thread pool accepts a task. A pool worker created during Alice's request can be reused for Bob; inheriting context this way easily causes identity confusion.
- `MODE_GLOBAL`: shares one context across the JVM; unsuitable for representing each user of a concurrent multi-request web application.

**Never enable inheritable/global just to fix an `@Async` missing-principal bug.** Use per-task wrappers, ensuring context is set and cleared with the proper lifecycle.

## 3. What Does the DelegatingSecurityContext... Family Do?

The classes below belong to Spring Security 6.5; packages vary by type:

| Class | Wrapped API | When to Use |
| --- | --- | --- |
| `DelegatingSecurityContextRunnable` | `Runnable` | A single `void run()` task |
| `DelegatingSecurityContextCallable<V>` | `Callable<V>` | Task needing a return value or checked exception |
| `DelegatingSecurityContextExecutor` | `Executor` | Call sites using only `execute(Runnable)` |
| `DelegatingSecurityContextExecutorService` | `ExecutorService` | Need `submit`, `Future`, `invokeAll`, shutdown… |
| `DelegatingSecurityContextScheduledExecutorService` | `ScheduledExecutorService` | Periodic or delayed tasks, with explicit identity policy |
| `DelegatingSecurityContextTaskExecutor` | Spring `TaskExecutor` | Using Spring Task's `execute` abstraction |
| `DelegatingSecurityContextAsyncTaskExecutor` | Spring `AsyncTaskExecutor` | Using `@Async`, submitting with `Future`/`CompletableFuture` |
| `DelegatingSecurityContextTaskScheduler` / `SchedulingTaskExecutor` | Spring Task scheduling | When using Spring's scheduler or corresponding adapters |

The `Runnable`, `Callable`, `Executor`, and `ExecutorService` classes live in `org.springframework.security.concurrent`. `DelegatingSecurityContextTaskExecutor` and `DelegatingSecurityContextAsyncTaskExecutor` live in `org.springframework.security.task`. Do not import the wrong package or assume they are general `java.util.concurrent` APIs.

### General Rules

The wrappers:

1. Obtain `SecurityContext` according to the chosen constructor/policy.
2. Place the appropriate context into the worker's `SecurityContextHolder` while the task runs.
3. Execute the delegate `Runnable.run()` or `Callable.call()`.
4. Clear or restore the prior context in `finally` per implementation/version, even when the delegate throws an exception.
5. Do not decide on their own whether the user is allowed to run the job; authorization must be designed independently.

Spring Security documentation shows a minimal model:

```java
try {
    SecurityContextHolder.setContext(securityContext);
    delegate.run();
} finally {
    SecurityContextHolder.clearContext();
}
```

This is a **conceptual model**, not code to copy instead of using the library. Javadoc for newer classes notes that if the worker already had a context prior to the task, that context may be **restored** rather than always wiped blank. What must be guaranteed is that the wrapper never lets **the just-executed task's identity** leak into a subsequent independent task.

## 4. DelegatingSecurityContextRunnable: A Single Task

### 4.1. Constructor Capturing the Current Context

```java
Runnable businessAction = () -> {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    System.out.println(auth == null ? "NONE" : auth.getName());
};

// Wrap while the appropriate SecurityContext is still present.
Runnable wrapped =
        new DelegatingSecurityContextRunnable(businessAction);

new Thread(wrapped, "background-once").start();
```

This is a **snippet**: full thread creation/cleanup, lifecycle, and tests are shown in the runnable example. The `new DelegatingSecurityContextRunnable(Runnable)` constructor uses the context in `SecurityContextHolder` **at the moment the wrapper is constructed**.

Keep these distinct:

```text
t0 - Alice's request has SecurityContext(Alice)
t1 - create DelegatingSecurityContextRunnable(delegate)
     → wrapper captures Alice's context
t2 - request thread changes/clears SecurityContextHolder
t3 - new worker starts running wrapper
     → worker uses the context captured at t1
t4 - wrapper finishes → cleanup/restore
```

Do not construct the wrapper too early under an anonymous context and reuse it after login; it can capture the wrong state. Also never keep Alice's wrapper as a **singleton** so multiple users submit the same `Runnable` later.

### 4.2. Constructor Receiving an Explicit SecurityContext

```java
SecurityContext captured = SecurityContextHolder.getContext();

Runnable wrapped = new DelegatingSecurityContextRunnable(
        () -> securedService.performOperation(),
        captured);
```

This is a **snippet depending on `securedService`**. Passing an explicit context is useful when you must specify the exact privileges for the task, yet it means **responsibility for choosing the right context and lifecycle** belongs to the application.

**Object reference note:** the wrapper receives a `SecurityContext` object, not a promise that every field of principal/authorities was immutably deep-copied. If other code mutates the same object while the task sits in a queue, results can diverge from expectations. Never mutate shared contexts; when a clean snapshot is needed, create a new context containing only required info or store the identity ID and revalidate per policy.

### 4.3. When a Wrapper Is Unnecessary

If all code runs on the **same Servlet thread**, `SecurityContextHolder` already holds the context. Adding a wrapper does not improve security by itself. Only use context propagation when **execution genuinely moves to another thread** or to a platform without automatic integration.

## 5. DelegatingSecurityContextCallable: Tasks Returning a Result

A `Callable<V>` returns a value and may throw checked exceptions. `DelegatingSecurityContextCallable<V>` serves the same purpose as the Runnable wrapper:

```java
Callable<String> lookup = () -> {
    Authentication current =
            SecurityContextHolder.getContext().getAuthentication();
    return current == null ? "NONE" : current.getName();
};

Callable<String> delegated =
        new DelegatingSecurityContextCallable<>(lookup);

Future<String> result = executorService.submit(delegated);
String username = result.get();
```

This is a **snippet**, assuming `executorService`, imports, and proper exception handling exist. When creating the delegated `Callable` during Alice's request, the task running later can see the captured context even after T1 has cleared its holder.

**Should you combine a Callable wrapper with a DelegatingSecurityContextExecutorService?** Usually **no**. If the executor already handles wrapping, callers should simply submit a normal task. Double-wrapping makes capture and cleanup logic harder to verify, especially when the outer and inner contexts are captured at **two different moments**.

## 6. DelegatingSecurityContextExecutor: Auto-Wrapping at Submission

Suppose the application owns an `Executor`:

```java
Executor rawExecutor = command -> new Thread(command).start();

Executor securedExecutor =
        new DelegatingSecurityContextExecutor(rawExecutor);

securedExecutor.execute(() -> {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    // Business code can read the submitter's auth.
});
```

This is an illustrative snippet; **never** spawn unbounded threads like this in production. Use a bounded thread pool, queue capacity, rate control, metrics, and proper shutdown.

### Two Constructors Represent Two Different Policies

**Style 1 — capture the submitter's context for each task:**

```java
Executor secured =
        new DelegatingSecurityContextExecutor(rawExecutor);
```

Each time `secured.execute(task)` runs, the wrapper reads the context currently in `SecurityContextHolder` on the **thread calling `execute`** and binds it to the task. This is the right style when Alice's request submits Alice's task and Bob's request submits Bob's task.

**Style 2 — use a fixed context for every task:**

```java
SecurityContext fixed = SecurityContextHolder.createEmptyContext();
// fixed must be built from an ALREADY trusted principal/service identity.
Executor secured =
        new DelegatingSecurityContextExecutor(rawExecutor, fixed);
```

In this style, **every** task on the executor uses **the same fixed context**, regardless of who submitted it. A valid use case is a dedicated background service account granted least privilege by policy. The risk is severe if you accidentally pass an admin/request user's context and store that executor as a singleton.

**Avoid a common bug:** creating a `DelegatingSecurityContextExecutor(delegate, SecurityContextHolder.getContext())` bean at startup expecting it to switch to each request's principal automatically. It will hold the fixed context from bean initialization time (usually anonymous/empty), not the context at submit time.

### Capture-at-Submit vs. Execute-Time

```text
Alice submits task A (attaches Alice) ──┐
Bob submits task B (attaches Bob) ──┐   │
                                    ▼   ▼
                            Thread pool queue
                                    │
                            Worker runs B/A
                                    │
            each task uses the context captured at submit,
            not the previous worker's context
```

A task may start running after the HTTP request has finished. This does not turn the captured identity into **eternal immutable privileges**: if the account is locked or a role is revoked while queued, the task can still carry the stale snapshot. For sensitive operations, re-check permissions/identity version **at execution time**, or use appropriate service-to-service authorization.

## 7. Runnable Java 17+ Example: Proving Capture, Fixed Context, and Cleanup

This example **needs no Servlet container**, isolating the ThreadLocal propagation mechanism. It constructs two **simulated identities for local testing only**, without performing username/password authentication. Never copy this manual `UsernamePasswordAuthenticationToken` construction into a real endpoint to replace `AuthenticationManager`.

The program intentionally uses **a single-thread executor** to prove:

- Tasks running on a raw pool **do not automatically have** the main thread's context.
- `DelegatingSecurityContextExecutorService(delegate)` captures **mai** or **an** at submit time.
- `DelegatingSecurityContextExecutorService(delegate, fixedContext)` always uses **service-operator**.
- After a succeeding task **and when a task throws an exception**, the pool thread retains no old identity.
- A `DelegatingSecurityContextRunnable` created while main holds `lan`, even after main clears its context, still lets the worker task see `lan`.

### 7.1. Project Structure

```text
security-context-concurrency-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SecurityContextConcurrencyDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'security-context-concurrency-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

application {
    mainClass = 'demo.SecurityContextConcurrencyDemo'
}
```

### 7.2. Complete Java File

Create `src/main/java/demo/SecurityContextConcurrencyDemo.java`:

```java
package demo;

import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.security.concurrent.DelegatingSecurityContextExecutorService;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;

public final class SecurityContextConcurrencyDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService rawPool = Executors.newSingleThreadExecutor();

        try {
            // Worker has not received any context yet.
            System.out.println("raw-before=" +
                    rawPool.submit(SecurityContextConcurrencyDemo::name).get());

            // Simulates an authenticated principal in tests only.
            setDemoIdentity("mai");
            System.out.println("main=" + name());

            // Raw thread pool does not inherit main thread's ThreadLocal.
            System.out.println("raw-during=" +
                    rawPool.submit(SecurityContextConcurrencyDemo::name).get());

            // No SecurityContext passed => captures on each submission.
            DelegatingSecurityContextExecutorService perSubmission =
                    new DelegatingSecurityContextExecutorService(rawPool);

            System.out.println("wrapped-mai=" +
                    perSubmission.submit(SecurityContextConcurrencyDemo::name).get());

            setDemoIdentity("an");

            System.out.println("wrapped-an=" +
                    perSubmission.submit(SecurityContextConcurrencyDemo::name).get());

            System.out.println("raw-after-wrapped=" +
                    rawPool.submit(SecurityContextConcurrencyDemo::name).get());

            // Explicit SecurityContext passed => fixed identity.
            SecurityContext fixed = newContext("service-operator");

            DelegatingSecurityContextExecutorService fixedExecutor =
                    new DelegatingSecurityContextExecutorService(rawPool, fixed);

            System.out.println("fixed=" +
                    fixedExecutor.submit(SecurityContextConcurrencyDemo::name).get());

            System.out.println("main-after-fixed=" + name());

            // Context must not leak after a failing task.
            Future<?> failed = perSubmission.submit(() -> {
                throw new IllegalStateException("intentional");
            });

            try {
                failed.get();
            } catch (ExecutionException expected) {
                System.out.println("failure=" +
                        expected.getCause().getClass().getSimpleName());
            }

            System.out.println("raw-after-failure=" +
                    rawPool.submit(SecurityContextConcurrencyDemo::name).get());

            // Runnable wrapped under identity lan, then main clears.
            setDemoIdentity("lan");
            Runnable wrappedOnce = new DelegatingSecurityContextRunnable(
                    () -> System.out.println("runnable=" + name()));

            SecurityContextHolder.clearContext();

            Thread once = new Thread(wrappedOnce, "example-once");
            once.start();
            once.join();

            System.out.println("main-cleared=" + name());

        } finally {
            SecurityContextHolder.clearContext();
            rawPool.shutdown();
            if (!rawPool.awaitTermination(5, TimeUnit.SECONDS)) {
                rawPool.shutdownNow();
            }
        }
    }

    private static String name() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        return authentication == null
                ? "NONE"
                : authentication.getName();
    }

    private static void setDemoIdentity(String username) {
        SecurityContextHolder.setContext(newContext(username));
    }

    private static SecurityContext newContext(String username) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();

        // Test fixture ONLY: never use to bypass real login.
        Authentication demoAuthentication =
                new UsernamePasswordAuthenticationToken(
                        username,
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_READER")));

        context.setAuthentication(demoAuthentication);
        return context;
    }
}
```

Run in the `security-context-concurrency-demo` directory:

```bash
gradle run
```

If Gradle Wrapper is present, use `./gradlew run` on macOS/Linux or `gradlew.bat run` on Windows. Requires JDK 17+ and a compatible Gradle version.

### 7.3. Expected Stdout

```text
raw-before=NONE
main=mai
raw-during=NONE
wrapped-mai=mai
wrapped-an=an
raw-after-wrapped=NONE
fixed=service-operator
main-after-fixed=an
failure=IllegalStateException
raw-after-failure=NONE
runnable=lan
main-cleared=NONE
```

**Explanation of each output group:**

1. `raw-before=NONE`, `raw-during=NONE`: a separate worker thread does not automatically receive `ThreadLocal` from main. There is no basis to expect an unwrapped pool to hold the logged-in identity.
2. `wrapped-mai=mai`: while main holds mai's context and calls `perSubmission.submit`, the wrapper captures mai for that task.
3. `wrapped-an=an`: the exact same executor wrapper **is reused**, yet the subsequent submission captures an; it does not stick to the first identity.
4. `raw-after-wrapped=NONE`: after the wrapped task, the worker's state is cleared/restored properly, leaking neither mai nor an into the next raw task.
5. `fixed=service-operator`: the constructor overload taking `SecurityContext fixed` intentionally uses a different identity from the submitter. This feature must be explicitly authorized/reviewed in production.
6. `main-after-fixed=an`: the worker does not alter the main thread's context.
7. `failure=IllegalStateException`: the task intentionally throws an exception, which `Future.get()` wraps in `ExecutionException`. Afterward `raw-after-failure=NONE` proves cleanup on error.
8. `runnable=lan`: `DelegatingSecurityContextRunnable` captures context when the wrapper is constructed, before main calls `clearContext`.
9. `main-cleared=NONE`: main's context is cleared; the wrapper running on another thread does not put the identity back onto main.

**Example conditions:** tasks are submitted and awaited in deterministic order via `Future.get()`/`Thread.join()`. Thus output does not depend on parallel thread-pool scheduling order. If you remove those synchronization steps, console line ordering can vary.

**Security:** `new UsernamePasswordAuthenticationToken(username, null, authorities)` is a **test fixture** technique. It creates a token treated as authenticated **without verifying any password**; never turn this into real login. In production applications, `Authentication` must come from `AuthenticationManager`/providers or a trusted identity source.

**Runtime limitation:** the example is designed against Spring Security 6.5.11 APIs; code and output were reviewed against documentation rather than captured from a production run. If changing versions or context strategies, re-test accordingly.

## 8. Using ExecutorService Instead of Wrapping Every Task

When an application has a shared `ExecutorService`, you can wrap the **executor** once instead of forcing every caller to know `DelegatingSecurityContextCallable`:

```java
ExecutorService rawPool = Executors.newFixedThreadPool(4);
ExecutorService securedPool =
        new DelegatingSecurityContextExecutorService(rawPool);

// Inside an authenticated user's request:
Future<String> future = securedPool.submit(
        () -> SecurityContextHolder.getContext()
                .getAuthentication().getName());
```

This is a snippet; `Future.get`, shutdown, bounded queues, and exceptions must still be handled. What matters is that callers submit ordinary tasks; the executor wrapper handles capture/set/cleanup.

**Do not do this:**

```java
// Wrong: captures a request authentication context at singleton bean startup.
SecurityContext userContext = SecurityContextHolder.getContext();
ExecutorService securedPool =
        new DelegatingSecurityContextExecutorService(rawPool, userContext);
```

A shared bean could hold an anonymous context forever or an unintended user. If you want **the submitter's identity**, use the constructor taking only `rawPool`. If you want **a fixed service identity**, build it through a trusted mechanism, restrict privileges, and never confuse it with a request principal.

### Lifecycle and Shutdown

`DelegatingSecurityContextExecutorService` wraps a real `ExecutorService`. To operate reliably:

- Choose an executor with bounded queues, thread naming, a rejection policy, and metrics; `Executors.newFixedThreadPool(...)` creates an unbounded queue by default.
- Shut down **once according to ownership** of the underlying executor; do not let multiple beans shut down a shared raw pool independently.
- If tasks wait too long, the request user may log out, change roles, or get locked before execution. The wrapper does not revoke/refresh credentials itself.
- Handle `Future` exceptions, timeouts/cancellations, and retries explicitly. Never log full `Authentication` objects or raw tokens in job logs.
- With `submit`, exceptions can sit inside `Future.get()` without surfacing on the request thread if the task is never awaited.
- Distinguish bounded local tasks from persistent job queues; passing `SecurityContext` objects across queues/networks is a boundary-design mistake.

## 9. Integrating Spring Boot @Async with DelegatingSecurityContextAsyncTaskExecutor

In a Spring application, `@Async` moves the method onto another executor. Thus an async method can lack the principal unless the executor is integrated properly.

Using `DelegatingSecurityContextAsyncTaskExecutor` with `ThreadPoolTaskExecutor`:

```java
@Configuration
@EnableAsync
class AsyncSecurityConfiguration {

    @Bean(name = "securityTaskExecutor")
    AsyncTaskExecutor securityTaskExecutor() {
        ThreadPoolTaskExecutor delegate = new ThreadPoolTaskExecutor();
        delegate.setCorePoolSize(2);
        delegate.setMaxPoolSize(4);
        delegate.setQueueCapacity(64);
        delegate.setThreadNamePrefix("security-task-");
        delegate.initialize();

        // Do not pass a fixed SecurityContext:
        // capture the identity of each task's submitter.
        return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
    }
}
```

This is a snippet **inside a Spring Boot application**: it requires imports for `org.springframework.context.annotation.Bean`, `Configuration`, `EnableAsync`, `AsyncTaskExecutor`, `ThreadPoolTaskExecutor`, and `DelegatingSecurityContextAsyncTaskExecutor`. The example omits the full authentication configuration and application main; do not treat it as a standalone project.

Another service:

```java
@Service
public class DocumentReportService {

    @Async("securityTaskExecutor")
    public CompletableFuture<String> submit() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        String username = authentication == null
                ? "NONE"
                : authentication.getName();

        // Demo: production should return a job ID rather than holding requests open indefinitely.
        return CompletableFuture.completedFuture(username);
    }
}
```

Conditions you must know:

1. `@EnableAsync` is enabled and the method belongs to a Spring bean.
2. The `@Async` method must be invoked **through the Spring proxy** (e.g., a controller calling the `DocumentReportService` bean); self-invocation such as `this.submit()` on the same object bypasses the proxy and runs synchronously.
3. `@Async("securityTaskExecutor")` selects the wrapped executor; do not assume every executor bean automatically propagates context.
4. The constructor taking only the delegate captures context at **submission time**, avoiding holding a user from application startup.
5. Tasks must have their own authorization policy; merely propagating context does not guarantee valid data/access.
6. Never write data into `SecurityContextHolder` as shared storage between a task and a request.
7. For long-running jobs, return a `jobId` and execute under stored identity with controlled revalidation instead of holding the full mutable context.

**Note on @Async exceptions:** for methods returning `CompletableFuture`, exceptions must be handled via the returned future/error handler. For `void` async methods, errors go through `AsyncUncaughtExceptionHandler`; do not expect controllers to always catch exceptions from async threads.

### Why Not Write a Custom TaskDecorator to Set the Holder?

Spring's `TaskDecorator` can propagate MDC, locale, or other context. You could write a custom decorator that sets/restores `SecurityContextHolder`, yet it is easy to omit `finally`, use the wrong context strategy, or capture at the wrong moment. When the goal is Spring Security propagation, prefer the official `DelegatingSecurityContextAsyncTaskExecutor` adapter; for tracing/MDC, add the matching propagation mechanism and avoid uncontrolled double-wrapping.

## 10. @PreAuthorize in Background Tasks: Permissions and Principals Are Not "Valid Forever"

Example with method security:

```java
@Service
public class ExportService {
    @PreAuthorize("hasAuthority('documents:export')")
    public void exportDocuments() {
        // ... query data permitted for export ...
    }
}
```

This is a snippet assuming `@EnableMethodSecurity` is active and invocation goes through a Spring proxy. If the task is submitted after Alice authenticated, `DelegatingSecurityContext...` lets the security interceptor read Alice's authorities on the worker thread.

However, note:

- **Propagation does not re-authenticate** Alice. The context may hold authorities from submission time, while roles changed before the task ran.
- `@PreAuthorize` only checks the written expression. It does not restrict tenant, owner, or per-document scope unless you define that policy.
- Method security also has proxy boundaries; internal method calls within the same bean may skip authorization advice.
- If a job accesses objects hours later, decide whether permissions are evaluated at **enqueue time or execution time**. For sensitive operations, re-checking at execution time is usually safer.
- Never use a fixed `ROLE_ADMIN` for all tasks just "to make `@PreAuthorize` pass"; that is a privilege escalation hazard.
- Never pass raw passwords, access tokens, refresh tokens, or session cookies in job payloads to reconstruct authentication.

### Long-Running and Persistent Background Jobs: Pass IDs, Not Full Context Objects

If work may wait for minutes, run after logout, retry after a server restart, or cross nodes, ThreadLocal wrappers are no longer the right identity mechanism. A cleaner design:

```text
Authenticated HTTP request
   ↓
Authorization + validate permission to create job
   ↓
Save job record: jobId, requesterAccountId, tenantId,
                 task type, requested scope, timestamp
   ↓
Message queue / worker service
   ↓
Worker uses a trusted service identity
   ↓
Load account/tenant/resource, revalidate policy and status
   ↓
Execute task, audit with requester + service actor
```

This is a **conceptual design**, not Java code. Never serialize `SecurityContext` into Kafka/SQS/Redis and treat it as a long-lived credential. Privileges from a request's `Authentication` may have expired, principals may hold sensitive data, and ThreadLocal does not survive across processes.

Record two distinct identities in audits:

- **Requester (on-behalf-of):** the initiator of the request, trusted account ID / tenant.
- **Execution identity:** the service/job principal actually running the task, with permissions granted by service policy.

Keeping the two values distinct separates "who requested" from "who executed". Avoid assigning a fixed admin context to every worker just for convenience.

## 11. Context Snapshots, Mutable State, and Cross-User Leak Risks

### 11.1. Context Can Be a Mutable Object

`SecurityContext` typically holds an `Authentication` object. When a wrapper captures a context, that does not mean the entire principal/authorities/session state was immutably deep-copied.

If a code path mutates a shared context directly, a task waiting in a queue can see unexpected results. Protections:

1. Treat a request's `SecurityContext` as request-scoped state, **not a long-lived transfer object**.
2. Never mutate a shared context in place when updating authentication; when needed, call `SecurityContextHolder.createEmptyContext()` and attach the right `Authentication`.
3. When a task only needs a few fields, **pass an immutable DTO** with verified internal ID, tenant ID, and authorization scope; do not pass the entire context.
4. For sensitive jobs, revalidate account status/permissions when running instead of relying on stale snapshots.
5. Never put full JPA entities with lazy relations or password hashes into principals or background payloads.
6. Never let a fixed wrapper retain a user's context inside a singleton longer than necessary.

### 11.2. Thread Pools Reuse Threads

Suppose a worker processes Alice's job and then Bob's job:

```text
Thread pool worker-1:
    Alice's task
       set SecurityContext(Alice)
       run
       finally restore/clear
    Bob's task
       set SecurityContext(Bob)
       run
       finally restore/clear
    Unwrapped task
       must see neither Alice nor Bob
```

If a developer writes manually:

```java
executor.execute(() -> {
    SecurityContextHolder.setContext(aliceContext);
    performWork();
    // MISSING finally -> identity can leak.
});
```

This is an anti-pattern depending on `aliceContext` and `performWork()`. If the task throws an exception or is canceled before cleanup, the worker can retain Alice's context. Because executors reuse threads, that is a severe isolation bug.

**Do not confuse "current context restored" with "user Alice still has permissions".** Restoration is ThreadLocal hygiene, not reauthorization.

### 11.3. Custom Context Strategies

Wrappers can use the `SecurityContextHolderStrategy` configured in the application. If a project uses a custom strategy, the filter's context provider and the wrapper must align; changing strategy in only one place causes "worker sees no auth". Never set a custom/global strategy arbitrarily to patch propagation. For typical Servlet apps, default ThreadLocal plus delegating wrappers are clear enough.

## 12. Spring MVC Async and Servlet Async: Built-In Integrations

Not every thread switch requires adding a wrapper yourself. Spring Security includes several **automatic integrations** on the Servlet stack.

### 12.1. Controller Returning Callable<T>

Spring MVC supports methods returning `Callable<T>` for asynchronous handling:

```java
@GetMapping("/reports/current-user")
public Callable<String> currentUserLater() {
    return () -> {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        return auth == null ? "NONE" : auth.getName();
    };
}
```

This is a controller snippet. Under standard Spring Security Servlet/MVC integration configuration, `WebAsyncManagerIntegrationFilter`/`SecurityContextCallableProcessingInterceptor` transfers `SecurityContext` into the controller's `Callable`, so this path **usually already has propagation**. Spring Security documentation notes that capture occurs when Spring MVC begins `startCallableProcessing`.

**Do not equate this** with `CompletableFuture.supplyAsync(...)` invoked manually by the application. If you submit to the common pool or an unwrapped executor yourself, Spring MVC's `Callable` integration does not automatically guarantee context for that task.

### 12.2. DeferredResult<T>

`DeferredResult` is usually completed from an application-owned thread. Spring Security cannot know where that thread was created, so it **does not have the same automatic propagation as Callable controllers**. You can use `DelegatingSecurityContextExecutor`/`AsyncTaskExecutor` to wrap the task that actually completes the result.

### 12.3. Servlet AsyncContext.start(Runnable)

Spring Security provides integration to propagate context for Servlet API's `AsyncContext.start(Runnable)` when requests pass through matching wrappers/filters. Yet that **does not mean** all `new Thread`, `CompletableFuture`, schedulers, or application queues are wrapped automatically. Always test against the exact API your code uses.

### 12.4. @Async Is Not Spring MVC Callable

`@Async` typically runs via Spring Task's `AsyncTaskExecutor`. A controller returning `Callable` is a Spring MVC async mechanism with its own integration. Check **which executor actually receives the task**, avoiding both MVC integration wrapping and arbitrary extra wrapping at another layer that captures context at the wrong time.

## 13. Async APIs Not Automatically Supported in All Cases

| Execution Style | Security Context Built-In? | How to Handle |
| --- | --- | --- |
| Synchronous code on request thread | Normally yes | Use holder normally |
| `new Thread(runnable)` | Not guaranteed | Wrap with `DelegatingSecurityContextRunnable` |
| `Executor.execute(runnable)` | Depends on executor | `DelegatingSecurityContextExecutor` |
| `ExecutorService.submit(callable)` | Depends on executor | `DelegatingSecurityContextExecutorService` or Callable wrapper |
| `@Async` | Depends on executor bean/integration | `DelegatingSecurityContextAsyncTaskExecutor` |
| `CompletableFuture.supplyAsync(...)` default common pool | Not guaranteed | Pass a wrapped executor or pass identity explicitly |
| `CompletableFuture.supplyAsync(..., executor)` | If executor is properly wrapped | Verify capture-at-submit and cleanup |
| `parallelStream()` | Not guaranteed on ForkJoinPool | Avoid relying on ThreadLocal; design explicit identity |
| Spring MVC `Callable<T>` controller | Has Spring Security integration when properly configured | Do not double-wrap if already supported |
| Spring MVC `DeferredResult<T>` | No automatic propagation equivalent to Callable | Wrap the app-submitted task |
| Servlet `AsyncContext.start(Runnable)` | Has Spring Security integration in matching flow | Verify request wrapper/filters |
| Periodic scheduler | No natural "user request" | Bounded fixed service identity or no user context |
| Message queue / another worker process | ThreadLocal does not cross processes | Pass account ID + proof/policy and revalidate |

### CompletableFuture and Downstream Stages

A common trap:

```java
CompletableFuture<String> first = CompletableFuture.supplyAsync(
        () -> currentUserName(),
        delegatingExecutor);

// thenApplyAsync without an executor can run on commonPool.
CompletableFuture<String> second = first.thenApplyAsync(
        name -> currentUserName());
```

This is a snippet assuming `currentUserName()` and `delegatingExecutor` exist. Only tasks submitted through the wrapped executor have guaranteed propagation. **There is no guarantee** that `thenApplyAsync`/`thenComposeAsync` stages running on the common pool have the right identity. Every async boundary needs an explicit executor or a design that does not depend on the holder.

### Schedulers and Fixed Identity

A `@Scheduled` job running at midnight **has no logged-in user to capture**. If a system job needs a principal, create a dedicated least-privilege service identity with a clearly managed lifecycle rather than using the identity of the last request submitted earlier. `DelegatingSecurityContextScheduledExecutorService` can wrap tasks, yet the identity itself must still be designed and controlled like any other security component.

## 14. Separating Context Propagation from Authorization and Auditing

**Having an `Authentication` in a worker does not mean every action is permitted.** Context helps an authorization mechanism locate the principal, while whether access is allowed depends on:

- Authorities genuinely granted by a trusted source, not self-assigned by the client.
- Method/endpoint/resource rules, such as `hasAuthority("documents:export")`.
- Tenant, owner, project scope, account status, token validity, and revalidation timing.
- Policy for handling accounts locked or roles revoked after enqueueing.
- Technical privileges of the background service toward databases/external resources.

If Alice submits a job while holding `documents:export`, and an admin revokes that permission before the worker runs, you must decide the business policy: "permission at submit time is enough" or "permission must still be valid at execution time". Never let ThreadLocal's technical default **accidentally decide** that policy.

### Principle of Least Privilege

- Pass request identity only to tasks that truly need to act **on behalf of the user** over a short window.
- For system jobs, prefer a **least-privilege service identity**, never an arbitrary admin user.
- Pass only permitted identity fields; never retain plaintext credentials or session cookies.
- Audit requester ID and executor/service actor ID separately.
- Never serialize the full `SecurityContext` into job payloads or logs.
- When a task calls another HTTP API, ThreadLocal SecurityContext **does not automatically become an Authorization header**. A dedicated service-to-service credential/delegation mechanism, such as designed OAuth2 token exchange, is required.
- If a task can retry, re-check permissions and idempotency instead of replaying an unexpired context snapshot indefinitely.

## 15. Testing: Right Identity, Right Moment, No Leakage

A good test does not only assert "the task sees mai". It must also guarantee **the next task on the same worker** does not see the previous user's information.

### 15.1. Minimum Cases to Test

| Case | Expected Result |
| --- | --- |
| Unwrapped raw thread pool | Does not automatically have request principal |
| Per-submit wrapper with Alice | Alice's task sees Alice |
| Same per-submit wrapper with Bob | Bob's task sees Bob |
| Raw task after Alice/Bob on same worker | Does not see Alice/Bob from leakage |
| Fixed service-context wrapper | Every task uses the configured fixed service identity |
| Delegate throws exception | Task's context is still cleared/restored |
| Wrapped Runnable created under Alice, run after caller clears | Task still sees context captured at wrapper creation |
| `@Async` through Spring proxy with secured executor | Task sees identity per-submit per policy |
| `@Async` self-invocation | May not run async/proxied; test to detect |
| `CompletableFuture` stage using default common pool | Do not assume propagation |
| User permissions revoked after enqueue | Authorization handles per defined policy |
| Scheduled system job with no request | Does not automatically pick up "last user" |
| Task on another node/process | Does not rely on ThreadLocal; dedicated identity mapping |
| Cancel/timeout/exception/retry | No context leakage; proper resource cleanup |
| Cross-request multi-tenant | Never uses tenant or authorities from prior request |

### 15.2. Integration Test Pattern with ExecutorService

Using JUnit 5, you can write a targeted test (snippet needing imports/test project):

```java
@Test
void submitCapturesIdentityAndDoesNotLeakToPool() throws Exception {
    ExecutorService raw = Executors.newSingleThreadExecutor();
    try {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        "mai", null,
                        List.of(new SimpleGrantedAuthority("ROLE_READER"))));
        SecurityContextHolder.setContext(context);

        ExecutorService secured =
                new DelegatingSecurityContextExecutorService(raw);

        assertEquals("mai", secured.submit(() ->
                SecurityContextHolder.getContext()
                        .getAuthentication().getName()).get());

        // Raw worker must not retain the previous task's authentication.
        assertNull(raw.submit(() ->
                SecurityContextHolder.getContext()
                        .getAuthentication()).get());
    } finally {
        SecurityContextHolder.clearContext();
        raw.shutdownNow();
    }
}
```

This snippet illustrates a **test fixture**, not a real login. `@WithMockUser` can prepare context on a test thread, yet **does not automatically guarantee** tasks running on an arbitrary executor receive context; you must still submit through a wrapper and verify the outcome.

### 15.3. Spring Boot @Async Integration Tests

When testing `@Async` in a Spring app:

1. Enable `@EnableAsync` and define the `securityTaskExecutor` bean per configuration.
2. Establish test identity using security testing support or a real login request as appropriate.
3. Call the public `@Async` method through another bean, never directly via `this.method()`.
4. Await the `CompletableFuture` with a bounded timeout; assert the right principal was propagated.
5. Dispatch a second task under a different identity; confirm no cross-contamination.
6. If the task has `@PreAuthorize`, test both an unauthorized user and an authorized user to verify the interceptor is active.
7. Make a task throw an exception; verify the worker thread retains no context from the prior task.
8. Check executor thread counts, bounded queues, shutdown, and error reporting.

Never use `Thread.sleep(1000)` as the sole synchronization condition in tests; use `Future.get(timeout)` or latches to avoid flakiness.

## 16. Common Mistakes

1. **Thinking `SecurityContextHolder` is a JVM-wide global variable:** by default it is thread-bound and does not move across tasks automatically.
2. **Enabling `MODE_INHERITABLETHREADLOCAL` to fix thread pools:** a worker can be created under one request and serve many users; risk of identity mix-ups.
3. **Using `MODE_GLOBAL` in a web app:** easily breaks isolation between concurrent requests.
4. **Creating `DelegatingSecurityContextRunnable` too early:** captures a different context from execution time.
5. **Creating a singleton executor with a single request's context:** accidentally runs all tasks under the same user.
6. **Forgetting the no-context constructor for per-submit capture:** fixed context does not update per request.
7. **Thinking per-submit capture is an immutable deep copy:** context/principal can be mutable, stale, or shared.
8. **Not cleaning up `SecurityContextHolder` in thread pools:** subsequent tasks can see the prior task's privileges.
9. **Not testing when the delegate throws an exception:** cleanup in `finally` is a core security invariant.
10. **Using raw `CompletableFuture.supplyAsync` on the common pool:** no guaranteed propagation.
11. **Wrapping the executor while `thenApplyAsync` uses the common pool:** identity can vanish in the next stage.
12. **Thinking Spring MVC Callable and @Async are the same mechanism:** they use different integrations.
13. **Thinking DeferredResult automatically has context like Callable controllers:** tasks completing DeferredResult are app-owned.
14. **Thinking SecurityContextRepository explicit-save replaces propagation:** session persistence differs from threading.
15. **Thinking propagation re-verifies passwords/roles automatically:** wrappers do not re-authenticate users.
16. **Keeping request context across long jobs or retry queues:** identity/roles can become stale and are unsuitable for serialization.
17. **Using a fixed admin identity for all scheduled jobs:** privilege escalation and hard-to-trace audits.
18. **Attaching client-supplied authorities and passing them to workers:** bypasses the trust boundary.
19. **Checking only `authentication.getName()` in tests:** misses cleanup and cross-user checks.
20. **Not verifying Spring proxies for `@Async`/`@PreAuthorize`:** self-invocation can bypass them.
21. **Confusing worker ThreadLocal with outbound tokens:** calling another REST API does not automatically attach an Authorization header.
22. **Granting permissions from a group snapshot while forgetting tenant/object policies:** can cross resource boundaries.
23. **Logging full contexts, credentials, or tokens:** risk of leaking sensitive data.
24. **Leaving executor queues/thread counts unbounded:** risk of resource exhaustion when users submit many tasks.
25. **Assuming canceling a Future guarantees the task stopped and context cleared immediately:** cancellation, interrupt handling, and resource lifecycle must be designed.
26. **Double-wrapping at multiple layers without understanding capture timing:** creates nested contexts that are hard to debug.
27. **Changing SecurityContextHolderStrategy in a single component:** filters and wrappers can become mismatched.
28. **Failing to define policy when permissions are revoked between enqueue and execute:** the vulnerability is in authorization design, not ThreadLocal.

## 17. Hands-On Exercises

**Exercise 1 — ThreadLocal:** run the demo and point out why `raw-during=NONE` when main holds user mai. Try switching the executor to a two-thread pool and see why synchronization is needed rather than guessing console order.

**Exercise 2 — Constructors and capture:** construct a `DelegatingSecurityContextRunnable` while Alice is logged in, switch main's context to Bob before running. Predict the user inside the task. Then create a `DelegatingSecurityContextExecutor` without a fixed context, submit under Bob, and compare.

**Exercise 3 — Fixed context:** use a `service-operator` `SecurityContext` with only `ROLE_REPORT_WORKER` and run two tasks submitted by two different users. Explain why tasks use `service-operator` and the risks of substituting `ROLE_ADMIN`.

**Exercise 4 — Cleanup on error:** create a task throwing `RuntimeException`, assert `Future.get()` throws an exception, and verify a subsequent raw task on the same pool sees no old principal. Check outcomes when the task succeeds too.

**Exercise 5 — @Async:** create a Spring Boot web app with `@EnableAsync`, a `DelegatingSecurityContextAsyncTaskExecutor` bean, and a `@Async("securityTaskExecutor")` service method. Write integration tests calling from two different users through the Spring proxy.

**Exercise 6 — CompletableFuture:** build a chain `supplyAsync(..., securedExecutor)` followed by `thenApplyAsync(...)` without passing an executor. Record the observed identity and fix it by passing a wrapped executor at each boundary or using explicit identity parameters.

**Exercise 7 — Method Security:** enable `@EnableMethodSecurity` and create `@PreAuthorize("hasAuthority('documents:export')")`. Test an authorized user and an unauthorized user via a propagated task, then check tenant policy separately.

**Exercise 8 — Revocation:** a job is enqueued while Alice has permission, then an admin revokes it before execution. Define a concrete policy, replacing pure context carrying with storing the requester ID and revalidating at execution time.

**Exercise 9 — Long-running queue:** design a payload for a report job executing hours later, including requester ID, tenant ID, job ID, and scope—without serializing `Authentication`. Describe execution service identity, authorization, and auditing.

**Exercise 10 — MVC async:** compare a Spring MVC controller returning `Callable<T>` vs. `DeferredResult<T>`. Identify where Spring Security provides automatic integration and where a custom wrapper is needed.

### Completion Criteria

Learners can clearly articulate:

- Why `SecurityContextHolder` defaults to ThreadLocal and why pooled tasks do not automatically see the user.
- When to use `DelegatingSecurityContextRunnable`, `Callable`, and `ExecutorService`.
- How the constructor without `SecurityContext` differs from the constructor with a fixed `SecurityContext`.
- Why **capture time** and **execution time** can diverge.
- How cleanup/restore in `finally` prevents cross-user leaks.
- What executor/proxy `@Async` needs and what integration Spring MVC Callable provides.
- Why context propagation is **not** authentication, authorization, or session persistence.
- Why long-running jobs or cross-process queues should pass identity IDs and revalidate instead of carrying full contexts.

## 18. Official Documentation

- [Spring Security 6.5 — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, and related concurrency classes.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContextHolder`, ThreadLocal, and `Authentication`.
- [Spring Security 6.5.11 — DelegatingSecurityContextExecutorService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextExecutorService.html): both constructors, `submit`, and lifecycle.
- [Spring Security 6.5.11 — DelegatingSecurityContextCallable API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextCallable.html): wrapping Callable.
- [Spring Security 6.5 — DelegatingSecurityContextRunnable API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/concurrent/DelegatingSecurityContextRunnable.html): capture and restoration semantics.
- [Spring Security 6.5 — Spring MVC Async Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/mvc.html): Callable and `WebAsyncManagerIntegrationFilter`.
- [Spring Security 6.5 — Servlet API Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/servlet-api.html): `AsyncContext.start(Runnable)`.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity` and `@PreAuthorize`.
- [Spring Framework — Async Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, executor selection, method proxies, and scheduling.

**Version note:** the complete example uses Java 17 / Spring Security Core 6.5.11. If a project runs Spring Security 7, WebFlux/Reactor, virtual threads, or a framework/task executor with its own context propagation, verify the matching mechanism instead of applying Servlet's ThreadLocal model directly. For reactive flows, context normally travels through Reactor Context rather than the Servlet ThreadLocal wrappers in this lesson.