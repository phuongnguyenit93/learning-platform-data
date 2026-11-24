# ThreadLocal Boundaries When Work Moves to Another Thread in Spring Security Servlet

## 1. Problem: Authenticated Request, Missing User in Async Task

In a Spring Security **Servlet** application, authentication information for the request being processed is normally accessed via `SecurityContextHolder`. Its default strategy is `MODE_THREADLOCAL`: the `SecurityContext` is bound to the **current Java thread**, not automatically bound to every task spawned from the request. Therefore, a controller may see Alice's `Authentication`, while work running in an `ExecutorService`, `@Async`, or another callback sees `null` or an empty security context.

Conceptual example:

```text
HTTP request (Thread servlet-1)
  SecurityContextHolder -> Authentication("alice")
  |
  +-- submit task to thread pool
        |
        v
     Thread worker-7
       SecurityContextHolder -> its own context, usually empty
       Does not automatically receive Authentication("alice")
```

The problem is even more dangerous than "losing the principal": if code manually calls `setContext(...)` on a thread pool and forgets to restore/clear it in `finally`, Bob's request may run on a worker that still holds Alice's context. This is a risk of **cross-task identity and authorization leakage**.

Lesson objectives:
- Understand the scope of `ThreadLocal`, `SecurityContextHolder`, `SecurityContext`, and `Authentication`.
- Grasp the differences between normal request processing, Spring MVC `Callable`, `DeferredResult`, `CompletableFuture`, `ExecutorService`, `@Async`, schedulers, and virtual threads.
- Properly use `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextExecutorService`, and `DelegatingSecurityContextAsyncTaskExecutor`.
- Know when **not** to propagate the full security context: long-running work, events, message queues, scheduled jobs, or business logic requiring a dedicated service identity.
- Test propagation, cleanup, account isolation, and error handling without relying on arbitrary thread pool timing.

**Foundational rule:** A `ThreadLocal` carries data belonging to a **thread**, not to a "business task" or a "user". Crossing onto another thread means entering a different data scope unless a component designed to propagate the context is in place.

## 2. What Does SecurityContextHolder Actually Store?

In Spring Security, two key objects are involved:

- **`Authentication`**: the authentication result, typically including the principal, authorities, and authenticated status. For example, `UsernamePasswordAuthenticationToken` or `JwtAuthenticationToken`.
- **`SecurityContext`**: the container holding `Authentication`, accessed via `SecurityContextHolder` when authorization, a service, or a controller needs the current identity.

Common access code:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null && authentication.isAuthenticated()) {
    String username = authentication.getName();
    // Use username for authorization-controlled business logic.
}
```

This is a **snippet inside a Spring Security application**, not a standalone runnable Java file. Note that `getContext()` can provide an **empty** context, so `getAuthentication()` can be `null`. Do not assume that the existence of a context object means the request is authenticated.

### 2.1. The Default MODE_THREADLOCAL Strategy

In typical Servlet configurations, `SecurityContextHolder` uses `MODE_THREADLOCAL`. Conceptually, each thread has its own slot:

```text
Thread A --> ThreadLocal<SecurityContext> = Alice
Thread B --> ThreadLocal<SecurityContext> = null / empty
Thread C --> ThreadLocal<SecurityContext> = Bob
```

All of them call `SecurityContextHolder.getContext()`, yet each reads **the slot of the currently running thread**, not a shared global variable. Security filters set the appropriate context during request processing and clear it when the processing scope ends.

Spring Security 6 includes components such as `SecurityContextHolderFilter` and `SecurityContextRepository`. The repository loads/saves the context according to the request/session policy; this is **different** from `SecurityContextHolder` temporarily holding the value in the current thread. Do not confuse "persisting the SecurityContext in the session for subsequent requests" with "propagating the SecurityContext across a worker thread within the same operation".

### 2.2. Thread Pools Make the Issue More Apparent

Both servlet containers and worker executors **reuse threads** to process multiple requests/tasks. These threads have no durable parent–child relationship with a logical request. A task submitted from request A is not guaranteed to run on thread A, and task B may reuse the thread that previously ran task A.

A dangerous mistake:

```java
// ANTI-PATTERN: never copy into production
SecurityContextHolder.setContext(capturedContext);
doWork();
// Missing restore or clearContext -> may leak to the next task.
```

If the task fails partway through, the situation becomes even worse. Standard protection is to use Spring Security's wrappers or restore the state in `finally`, rather than merely calling `clearContext()` after a line that could throw an exception.

## 3. Standalone Java 17: ThreadLocal Does Not Automatically Propagate Across an Executor

The pure JDK example below illustrates this boundary using a `ThreadLocal<String>`. It **does not use Spring Security**, serving only to clarify the verifiable underlying principle. File `ThreadLocalBoundaryDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ThreadLocalBoundaryDemo {
    private static final ThreadLocal<String> ACTOR = new ThreadLocal<>();

    private static String show(String value) {
        return value == null ? "<none>" : value;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            ACTOR.set("alice"); // Simulate the request thread.
            System.out.println("request=" + show(ACTOR.get()));

            String before = worker.submit(() -> ACTOR.get()).get();
            System.out.println("worker-before=" + show(before));

            // Capture explicit data on the request thread and pass it upon submission.
            String capturedActor = ACTOR.get();
            String during = worker.submit(() -> {
                String previous = ACTOR.get();
                try {
                    ACTOR.set(capturedActor);
                    return ACTOR.get();
                } finally {
                    if (previous == null) {
                        ACTOR.remove();
                    } else {
                        ACTOR.set(previous);
                    }
                }
            }).get();
            System.out.println("worker-with-scope=" + during);

            String after = worker.submit(() -> ACTOR.get()).get();
            System.out.println("worker-after=" + show(after));
        } finally {
            ACTOR.remove();
            worker.shutdown();
        }
    }
}
```

Compile and run on JDK 17+:

```bash
javac ThreadLocalBoundaryDemo.java
java ThreadLocalBoundaryDemo
```

Exact stdout:

```text
request=alice
worker-before=<none>
worker-with-scope=alice
worker-after=<none>
```

Explanation:
1. The thread running `main` has `ACTOR="alice"`.
2. `newSingleThreadExecutor` has its own worker thread, so the worker's `ThreadLocal` slot is initially empty.
3. We capture the **explicit value** when submitting the task and bind it for the duration of the task execution, without depending on any thread name.
4. `finally` restores the previous value or calls `remove()`; the subsequent task does not see Alice.

This is a practical demonstration of the **lifecycle of a ThreadLocal**. With Spring Security, there is no need to hand-roll a wrapper copy like this: use the `DelegatingSecurityContext*` wrappers to avoid forgetting propagation and cleanup.

## 4. What Happens with Each Type of Async?

| Technique | Context on Calling Thread | Context on Executing Thread | What to Do |
| --- | --- | --- | --- |
| Synchronous controller/service on the same servlet request thread | May have Authentication | Same thread, usually still sees context | No separate propagation needed |
| `new Thread(runnable)` | Has Authentication | With default `MODE_THREADLOCAL` **does not automatically inherit** | Avoid manually creating threads in web apps; if truly needed, use controlled wrapper/capture |
| `ExecutorService.submit(...)` | Has Authentication when submitting | Task runs on a separate worker thread pool | Use `DelegatingSecurityContextExecutorService` or wrap the task |
| `CompletableFuture.supplyAsync(...)` without passing an executor | Has Authentication when calling | Usually runs on the ForkJoin common pool | Supply an executor configured for propagation; do not trust the default |
| `@Async` | Caller has Authentication | Method runs on a Spring executor | Configure `DelegatingSecurityContextAsyncTaskExecutor` / context propagation mechanism |
| Spring MVC returning `Callable<T>` | Security filter processes the request | MVC invokes the Callable on an executor | Spring Security integrates `WebAsyncManagerIntegrationFilter` for standard `Callable` |
| Spring MVC `DeferredResult<T>` | Initial request-handling thread has context | App completes the result manually from another thread | **No guarantee** of automatic context propagation to app-managed threads |
| Scheduler / message listener | Not necessarily an HTTP request | Scheduler/consumer thread | Use an explicit service identity; do not guess the user from ThreadLocal |
| Manually managed Servlet async `AsyncContext` | Request has context | Callback/dispatch may run on another thread | Check lifecycle and integration of each API/filter; do not assume automatic propagation |
| Newer Java virtual threads | Each virtual thread has its own ThreadLocal | New thread differs from request thread | Must propagate context deliberately; virtual threads do not turn ThreadLocal into task context |

**Do not confuse Spring MVC's `Callable` with every Java `Callable`.** Spring Security's automatic integration applies to a specific MVC flow; if you manually call `ExecutorService.submit(Callable)`, you do not get that integration by default.

### 4.1. Spring MVC Callable

Example:

```java
@GetMapping("/whoami")
public Callable<String> whoAmI() {
    return () -> {
        Authentication a =
            SecurityContextHolder.getContext().getAuthentication();
        return a == null ? "<none>" : a.getName();
    };
}
```

This snippet is an **illustrative controller method**, not a standalone Java class. When Spring Security Servlet integrates properly with Spring MVC async, `WebAsyncManagerIntegrationFilter` can supply the appropriate context to the thread executing the `Callable`. Testing in an application without Spring Security filters, or using a custom MVC executor/misordered filters, can produce different results.

This **does not mean** you can keep spawning other threads inside the `Callable` and always see the same context. When a `Callable` in turn calls `CompletableFuture.supplyAsync`, that is a **new** thread boundary.

### 4.2. DeferredResult and CompletableFuture

`DeferredResult` allows another thread to supply the result after the initial servlet request has already left its thread. Spring Security does not automatically know which tasks you submit to complete the `DeferredResult`. If the callback needs identity, pass the required business data or use a configured wrapper executor.

`CompletableFuture` can also switch threads between stages: `thenApply` sometimes runs on the thread that completed the previous stage, whereas `thenApplyAsync` may use a different executor. Do not let authorization code implicitly call `SecurityContextHolder` in a stage whose executor and context you do not control. Instead, authorize **before scheduling**, then pass the minimal required IDs/claims; for operations with delayed execution privileges, **re-verify** at execution time.

## 5. Why MODE_INHERITABLETHREADLOCAL Is Not a Universal Cure

Besides `MODE_THREADLOCAL`, `SecurityContextHolder` has other strategies:

- `MODE_INHERITABLETHREADLOCAL`: uses `InheritableThreadLocal` so newly created child threads can inherit the creating thread's context via inheritance.
- `MODE_GLOBAL`: a single JVM-wide shared context, **unsuitable for multi-user web servers**.

Neither is a safe shortcut for requests running on thread pools.

**Risks with `MODE_INHERITABLETHREADLOCAL`:**

1. Threads in a pool are usually created **before** the request, or created by a pool-management thread rather than Alice's thread.
2. Thread pools are long-lived and reused. If a worker inherits a context at creation time, Alice logging out or switching users does not necessarily update that state per request.
3. Inheritance can carry a **reference to a mutable SecurityContext**, not an independent immutable snapshot.
4. It is easy to accidentally leak identity across requests if relying on inherited context without cleanup.
5. There is no explicit control over **when** and **which object** is allowed to carry the context.

`MODE_GLOBAL` is even more dangerous for web applications because a single shared context can misrepresent the user across different requests. Do not change the JVM-wide strategy to patch a single `@Async` bug. Calling `SecurityContextHolder.setStrategyName(...)` in a running application also affects the entire system and must not be treated as local task configuration.

**The right solution:** choose propagation at the **task handoff boundary** (task submission) or use framework integration, paired with cleanup.

## 6. DelegatingSecurityContextRunnable and Callable

Spring Security provides wrappers to set the appropriate `SecurityContextHolder` while the task runs and then restore the pre-existing context on the worker thread.

Example **snippet belonging to a Spring Security application**, not a separately compilable file:

```java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;

SecurityContext capturedContext = SecurityContextHolder.getContext();

Runnable originalTask = () -> {
    String name = SecurityContextHolder.getContext()
        .getAuthentication().getName();
    performWorkFor(name); // Hypothetical business method of the application.
};

Runnable securedTask =
    new DelegatingSecurityContextRunnable(originalTask, capturedContext);

executor.execute(securedTask);
```

For `Callable<T>`, there is an analogous wrapper `DelegatingSecurityContextCallable<T>`. Constructors/factory methods can accept an explicit context or capture the context at **wrapper creation time** depending on how they are invoked. The capture must happen within the caller's scope where a valid Authentication is present; letting the wrapper grab the context after the request finishes risks capturing an empty or wrong context.

**Important note on mutable references:** `capturedContext` above is a **reference** to the existing `SecurityContext`. Passing a shared reference across threads can lead to races and unintended changes to Authentication if code mutates the context concurrently. When a relatively independent "snapshot" is needed, you can create `SecurityContextHolder.createEmptyContext()` and set the selected `Authentication`. However, `Authentication`/principal/credentials themselves may be mutable objects; this is not automatically a deep copy. Consider passing **only the user ID and required permissions** and re-checking authorization at execution time.

### 6.1. Handling Propagation Manually When No Wrapper Is Available

When framework integration requires a specialized callback, the principle is:

```java
SecurityContext previous = SecurityContextHolder.getContext();
try {
    SecurityContextHolder.setContext(contextForThisTask);
    doWork(); // Snippet: doWork is a business method.
} finally {
    // Restore the worker thread's state if one existed.
    SecurityContextHolder.setContext(previous);
}
```

Note, however, that `getContext()` can **initialize an empty context** if none exists yet. The restore pattern above is only an outline; a real application must determine when to call `clearContext()` instead of reattaching an empty context, and review the active strategy. **Prefer `DelegatingSecurityContext` wrappers**, which already handle lifecycle boundaries.

Never set a context without guaranteeing cleanup in `finally`, even if the callable times out, throws a runtime exception, is cancelled, or the thread pool continues processing other work.

## 7. DelegatingSecurityContextExecutorService: Preserving Context on Task Submission

When you have many tasks, instead of wrapping each `Runnable`/`Callable` individually, you can wrap an `ExecutorService` with `DelegatingSecurityContextExecutorService`.

Illustrative Spring config file `SecureExecutorConfig.java` (requires Spring Security dependencies):

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutorService;

@Configuration
public class SecureExecutorConfig {
    @Bean(destroyMethod = "shutdown")
    ExecutorService securityContextExecutor() {
        ExecutorService delegate = Executors.newFixedThreadPool(4);
        return new DelegatingSecurityContextExecutorService(delegate);
    }
}
```

Using it from a service or controller with a current `SecurityContext`:

```java
Future<String> task = securityContextExecutor.submit(() -> {
    Authentication a =
        SecurityContextHolder.getContext().getAuthentication();
    return a == null ? "<none>" : a.getName();
});
String resolved = task.get();
```

This is a snippet: `securityContextExecutor` must be injected from the bean above; imports for `Future`, `Authentication`, and `SecurityContextHolder` are required. When using the wrapper constructor **without passing a fixed SecurityContext**, Spring Security can capture the context of the thread **submitting** the task and set it on the worker when it runs. Do not construct the wrapper on another thread after authentication is lost and expect it to pick up the right user automatically.

**Warning:** the constructor has an overload that accepts a **fixed** `SecurityContext`. That mode fits certain tasks with an explicit service identity, but it is **not** the default choice if the pool serves multiple users. If a shared executor is pinned to Alice's context, every task Bob submits risks running under Alice's identity.

### 7.1. Pool Sizing and Cancellation

Context propagation does not solve performance and task-queue safety issues:
- A pool that is too small can bottleneck or starve; never call `Future.get()` on the same worker where it could self-deadlock.
- A pool that is too large can exhaust resources; bounded queues and rejection policies are needed.
- Long-queued tasks can still hold references to Authentication/claims; minimize retention and bound timeouts.
- When a task runs late, the user's permissions may have changed; do not treat "authenticated at submission time" as perpetual authorization.
- On application shutdown, cancel/await tasks according to product rules and clean up resources.

## 8. @Async with DelegatingSecurityContextAsyncTaskExecutor

Spring `@Async` routes method calls through a proxy and an executor. Without proper propagation, `SecurityContextHolder.getContext().getAuthentication()` in the async thread can be `null` even though the request thread is authenticated.

### 8.1. Configuring a Safe Async Executor

File `AsyncSecurityConfig.java`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
public class AsyncSecurityConfig {
    @Bean("secureTaskExecutor")
    AsyncTaskExecutor secureTaskExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("secure-task-");
        pool.initialize();

        return new DelegatingSecurityContextAsyncTaskExecutor(pool);
    }
}
```

`ThreadPoolTaskExecutor` is the Spring executor; `DelegatingSecurityContextAsyncTaskExecutor` wraps it and performs propagation within the task's scope. With this constructor, **no fixed Alice context is pinned in the singleton bean**; the wrapper captures the appropriate context when the task is submitted.

Pool size/queue/rejection/metrics decisions should be based on the real system. The example bean does not yet include custom shutdown/drain mechanics; in production, manage executor lifecycle and context startup/shutdown appropriately. In Spring Boot applications, executor beans must be designed to avoid name collisions with the auto-configured default executor.

### 8.2. Service and Controller Calling @Async

File `AsyncIdentityService.java`:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class AsyncIdentityService {
    @Async("secureTaskExecutor")
    public CompletableFuture<String> currentUsername() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        String username = authentication == null
            ? "<none>"
            : authentication.getName();

        return CompletableFuture.completedFuture(username);
    }
}
```

File `IdentityController.java`:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {
    private final AsyncIdentityService service;

    public IdentityController(AsyncIdentityService service) {
        this.service = service;
    }

    @GetMapping("/api/async-name")
    public CompletableFuture<String> asyncName() {
        return service.currentUsername();
    }
}
```

Explanation:
- The controller is invoked on the HTTP request thread; Spring Security has already set the `SecurityContext`.
- The controller calls **another service bean** through a Spring proxy.
- `@Async("secureTaskExecutor")` causes the service to execute on the worker executor, with the wrapper propagating the context present at scheduling time.
- The service simply reads Authentication and returns the username; upon completion, the wrapper restores/clears the context on the worker.
- The controller returns `CompletableFuture<String>`, and Spring MVC can process the result under the async lifecycle. The illustrative response body for Alice is `alice`, but only when the route is protected and the request was genuinely authenticated as Alice.

**Self-invocation pitfall:** if an `@Async` method is called from another method **within the same object** (for example `this.currentUsername()`), the `@Async` proxy can be bypassed and the method runs synchronously. A test saying "the principal is still visible" is then a **false positive**, because no real thread boundary was crossed. Invoke through a Spring-managed proxy from another bean and verify the thread name when diagnosing.

### 8.3. Illustrative Spring Security Chain

File `SecurityConfig.java`:

```java
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
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

This is a **demo configuration for clear authentication**; a real Resource Server might use `oauth2ResourceServer(...jwt(...))`, while a web login might use sessions/cookies depending on architecture. Propagating `SecurityContext` across a thread boundary **does not change** CSRF or endpoint authorization rules. If using cookies/sessions, continue applying appropriate CSRF protection; if it is a pure Bearer API, CSRF decisions depend on how credentials are sent, not on the executor.

The classes above are code **inside a Spring Boot 3/Spring Security 6 project with Java 17+**, requiring `spring-boot-starter-web`, `spring-boot-starter-security`, and `spring-boot-starter-aop` when using `@Async` proxies depending on project/dependencies. They will not compile standalone with `javac` without Spring libraries, a `@SpringBootApplication` startup class, and build configuration.

## 9. Testing Propagation, Isolation, and Cleanup

### 9.1. Real @Async Test with Mock SecurityContext

Test file `AsyncSecurityContextTest.java` in a Spring Boot project:

```java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class AsyncSecurityContextTest {
    @Autowired
    AsyncIdentityService service;

    @Test
    @WithMockUser(username = "alice")
    void contextIsAvailableInAsyncService() throws Exception {
        String name = service.currentUsername()
            .get(5, TimeUnit.SECONDS);
        assertEquals("alice", name);
    }

    @Test
    @WithMockUser(username = "bob")
    void nextTaskUsesItsOwnSubmittersContext() throws Exception {
        String name = service.currentUsername()
            .get(5, TimeUnit.SECONDS);
        assertEquals("bob", name);
    }
}
```

This test uses Spring Test and `spring-security-test`. `@WithMockUser` sets an Authentication on the **test thread**, and the wrapper transfers the context to the `@Async` worker. In practice, the two tests can run in any order; each independent test expects its own user. It proves propagation through the Spring async executor; it does **not** prove JWT signature verification or the HTTP filter chain end-to-end.

Run in a Maven project:

```bash
mvn -Dtest=AsyncSecurityContextTest test
```

With Gradle depending on project structure:

```bash
./gradlew test --tests AsyncSecurityContextTest
```

To verify `@Async` is not bypassed, you can add a thread-name assertion in the test environment or use a `CountDownLatch` to verify asynchronous invocation. Do not rely on `Thread.sleep` with a fixed duration and assume deterministic results.

### 9.2. Testing Missing Propagation to Avoid False Confidence

A separate test can invoke a **raw** `Executors.newSingleThreadExecutor()` from a test thread annotated with `@WithMockUser`, then call `SecurityContextHolder.getContext().getAuthentication()` on the worker. Under the default `MODE_THREADLOCAL`, the worker will not automatically receive the test thread's `Authentication`. When using the shared wrapper, the same task will see the properly propagated context.

Do not misuse this test if the application intentionally changes the JVM-wide strategy; tests must establish the `MODE_THREADLOCAL` baseline and clean up properly.

### 9.3. Testing Against User Leakage Between Two Tasks

Have an integration test following the sequence **Alice → Bob → Anonymous** on a **reused worker thread**:
1. Submit a task from Alice's context; assert the worker sees Alice.
2. Submit a task from Bob's context; assert the worker sees Bob.
3. Submit a task from an empty context; assert the worker no longer holds Alice/Bob.
4. Throw an exception in Alice's task, then submit Bob's task and confirm it is unaffected.
5. Test cancellation, timeout, and error dispatch if the product has those flows.

Using `newSingleThreadExecutor` or a single-worker pool makes reuse of the same thread explicit. A propagation test that only checks Alice sees Alice without verifying cleanup is insufficient to prove there is no identity leakage.

### 9.4. SecurityContext Propagation Is Not Authorization

Another crucial test: user Alice submits a task while authorized, and her permission is revoked before the task runs. If the task writes sensitive data relying solely on the `Authentication` captured at submission time, it may perform an action the user is **no longer permitted** to perform. For critical business operations, **re-check authorization at execution time**, using domain user ID/tenant ID and clearly scoped service credentials rather than trusting a stale snapshot.

## 10. ThreadLocal Is Not the Place to Store Every Async Context

### 10.1. MDC and Tracing Are Separate Scopes

`MDC` (logging correlation IDs) also commonly uses `ThreadLocal`, yet it is **not SecurityContext**. Wrapping tasks with `DelegatingSecurityContextAsyncTaskExecutor` does not mean trace IDs, locale, transactions, or MDC are automatically propagated. Conversely, a `TaskDecorator` copying MDC does not mean `Authentication` has been safely propagated.

If both are needed, define each separate context explicitly, use framework-supported propagation for your version, and test cleanup for each type. **Never** put bearer tokens or full credentials into MDC.

### 10.2. Transactions and EntityManager

A `@Transactional` on the request thread does not automatically "cross over" into `@Async`. Transaction state and persistence context/JPA `EntityManager` are usually bound to their own thread or scope. An async worker should open its own transaction if needed; do not pass lazy-loading entities or resources tied to a closed transaction without evaluating consistency.

### 10.3. Reactor and the Reactive Stack Are Different

In WebFlux/Reactor, the security context is propagated through the **Reactor Context** rather than assuming standard `ThreadLocal`. This lesson applies to **Spring Security Servlet**. When Servlet calls a reactive pipeline or reactive code calls a thread pool, you must understand the intersection of the context models and use the corresponding integration; do not call `SecurityContextHolder.getContext()` in arbitrary reactive callbacks expecting it to always be right.

### 10.4. Virtual Threads and Structured Concurrency

Java virtual threads are real threads with their own `ThreadLocal` semantics, so a task running on a new virtual thread **does not automatically have the servlet request thread's SecurityContext**. ThreadLocals in carrier/worker threads are not a solution for carrying user context across virtual threads. Use supported propagation and limit retention; avoid using `InheritableThreadLocal` to "spread" privileges to every child thread.

If using newer Java features such as structured concurrency or scoped values, check the API rules and framework integration for your actual version. They do not automatically replace Spring Security 6 Servlet's `SecurityContextHolder` mechanism.

## 11. When to Pass a Principal ID Instead of the Entire SecurityContext?

There is a significant difference between **short, in-request** tasks and **long-running, post-request** jobs.

### Short, Synchronous-to-Async Tasks

For example, reading several pieces of data in a few milliseconds, offloading computation from a controller and awaiting the result. If the task genuinely needs authorization/current principal within the same security scope, `DelegatingSecurityContext*` wrappers can be used, with performance measured and cleanup tested.

### Long-Running Background Jobs or Queues

For example, end-of-day invoice generation, image processing, sending emails, financial reconciliation, or processing messages minutes later. **Never** serialize, enqueue, or indefinitely retain a user's `SecurityContext`/bearer token:
- The token may expire or be revoked before the job runs.
- Principal/Auth objects may contain sensitive data unsuitable for queues/logs.
- Tasks may be retried on another machine that has no HTTP request `ThreadLocal`.
- Permissions may change after the user submitted the command.

A better design:
1. In the HTTP request, **authenticate + authorize the job submission action**.
2. Persist `jobId`, `requesterUserId`, `tenantId`, operation type, validated input, and audit metadata; do not store raw tokens.
3. Workers run under a **service identity** granted the exact required business permissions.
4. If the job executes an action requiring the user's current permissions, re-check permissions/ownership at runtime.
5. Audit logs distinguish the **initiator** from the **executing service**, rather than impersonating the SecurityContext of a logged-out user.

### Calling Downstream APIs on Behalf of the User

If a task must call another service **on behalf of** the user, propagating `SecurityContext` alone does not automatically obtain a valid downstream access token. Use an OAuth2 Client/Authorized Client/token exchange solution matching your architecture, with proper scopes/audience and safe token handling. Never copy `Authentication.getCredentials()` arbitrarily, never log Authorization headers, and never use expired tokens.

## 12. Common Mistakes and How to Diagnose Them

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| Controller sees principal, `@Async` sees `null` | Async thread does not inherit ThreadLocal | Use `DelegatingSecurityContextAsyncTaskExecutor`; test the `@Async` proxy |
| `CompletableFuture.supplyAsync` sees no Authentication | Runs on common pool/another worker | Provide an executor with propagation or safely pass user ID |
| `@Async` test still runs on the same thread | Self-invocation bypasses the proxy | Call through another Spring-managed bean; test actual thread switching |
| Bob sees Alice's principal in background worker | Context not cleared or fixed context used in shared executor | Restore in `finally`; fix wrapper; test Alice/Bob/anonymous |
| Tried `MODE_INHERITABLETHREADLOCAL` and it still fails | Pool was pre-created or reuses threads | Use wrapper at submission time instead of relying on inheritance |
| `SecurityContextHolder.setStrategyName(MODE_GLOBAL)` "worked" | Shares one context across the entire JVM | **Never use in multi-user web apps** |
| MVC `Callable` works, `DeferredResult` does not | Different framework integrations | Manage scoped callback executor/capture explicitly |
| After logout, job still runs with old privileges | Context was captured without revalidation | Use domain IDs + re-check permissions/service identity |
| MDC has trace ID, but principal is still empty | MDC and SecurityContext propagate independently | Configure propagation for each context type |
| Spring Security context disappears when request finishes | Expected lifecycle cleanup | Do not rely on the request thread after response completion |
| `SecurityContext` saved in HttpSession, yet async task is empty | Repository and ThreadLocal solve two different problems | Propagate context explicitly across thread boundaries |

Debugging procedure:
1. Record **thread names** where the task is submitted and where it executes (do not log tokens/PII).
2. Inspect the active `SecurityContextHolderStrategy` and how filters set/clear context.
3. Determine whether the task is submitted **before or after** the request thread loses its context.
4. Verify the actual wrapper/`@Async` executor bean being used; distinguish direct self-calls from proxied calls.
5. Run a single-worker pool reuse test to detect context leaks.
6. Check business permissions, session/token expiry, transactions, and downstream trust boundaries as well.
7. Add propagation only at the exact boundaries required; do not change the JVM-wide strategy as a quick fix.

## 13. Practical Checklist

- [ ] Understand that `SecurityContextHolder` defaults to `MODE_THREADLOCAL` in Spring Security Servlet.
- [ ] Do not expect `ThreadLocal` to automatically follow `ExecutorService`, `@Async`, `CompletableFuture`, or new threads.
- [ ] Do not switch to `MODE_GLOBAL` or `MODE_INHERITABLETHREADLOCAL` as a general fix for thread pools.
- [ ] For short async tasks needing current Authentication, use `DelegatingSecurityContextRunnable/Callable/ExecutorService/AsyncTaskExecutor` in the proper scope.
- [ ] Create wrappers while the caller holds a valid context; never pin a single user's context in a shared executor.
- [ ] Restore/clear worker context in `finally`, even when the task throws an exception.
- [ ] Verify Spring MVC `Callable` integration and handle `DeferredResult`/custom callbacks separately.
- [ ] Maintain integration tests for Alice → Bob → Anonymous and exception cases on the same worker.
- [ ] Do not treat propagation as perpetual authorization; delayed tasks must re-check authorization.
- [ ] Background jobs pass user/tenant/job IDs and use a service identity; avoid serializing tokens or full SecurityContext.
- [ ] Keep SecurityContext propagation separate from MDC, transactions, and Reactor Context.
- [ ] Never log raw tokens, credentials, or sensitive principals when debugging async behavior.

**Conclusion:** In Spring Security Servlet, `SecurityContextHolder` is not a "business-request global variable"; with `MODE_THREADLOCAL`, it lives inside the **executing thread**. Switching to `@Async`/executor/`DeferredResult` crosses a new boundary that requires controlled propagation or passing minimal business data. Use `DelegatingSecurityContext*` wrappers for short-lived work, always clean up context after the task, and never use a captured context as a substitute for authorization at actual execution time.
