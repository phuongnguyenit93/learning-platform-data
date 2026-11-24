# SecurityContext in Asynchronous Requests and Cross-Thread Calls

In Spring Security for **Servlet/Spring MVC applications**, a controller can read the current user via `SecurityContextHolder.getContext().getAuthentication()`, yet a task dispatched to `ExecutorService`, `@Async`, or `CompletableFuture.supplyAsync(...)` sees an empty `Authentication`. The opposite situation is equally dangerous: a worker thread reuses the previous user's context and inadvertently executes a new user's work with old permissions.

The key point: **`SecurityContext` does not automatically follow every asynchronous task**. On the Servlet stack, `SecurityContextHolder` binds context to the **executing thread** using `ThreadLocal` by default. Spring Security provides some automatic integrations for framework-managed async requests, plus dedicated wrappers to propagate context when the application creates work on other threads. You must understand **when context is captured, who installs it on the worker, who restores/clears it, and whether permissions remain valid when the job runs**.

This lesson distinguishes Servlet async handling, Spring MVC `Callable`, `DeferredResult`, `AsyncContext.start`, `@Async`, thread pools, and `CompletableFuture`; covers `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, `DelegatingSecurityContextExecutor`, and `DelegatingSecurityContextAsyncTaskExecutor`, along with a standalone Java 17+ example and test cases preventing identity leakage. Spring snippets are based on **Spring Boot 3 / Spring Security 6.x (Servlet stack)**; WebFlux/reactive setups use a different mechanism and do not directly follow these `ThreadLocal` rules.

## 1. What Are `SecurityContext`, `Authentication`, and `SecurityContextHolder`?

The system has three related concepts with distinct responsibilities:

| Component | What does it represent? | Common access pattern |
| --- | --- | --- |
| `SecurityContext` | Container holding security info for the execution context, especially `Authentication`. | `SecurityContextHolder.getContext()`. |
| `Authentication` | Principal, authorities, and authentication-state metadata. | `context.getAuthentication()`. |
| `SecurityContextHolder` | Provides/holds `SecurityContext` for the executing thread per a `SecurityContextHolderStrategy`. | `SecurityContextHolder.getContext()` or `getContextHolderStrategy()`. |

In a typical Servlet application, the default strategy is **`MODE_THREADLOCAL`**: each thread has its own context slot. An HTTP request normally passes through the filter chain, where security context management places the appropriate context onto the handling thread; when the request finishes, Spring Security ensures the thread's context is cleared per its lifecycle.

~~~text
HTTP request: Alice
   |
   v
Servlet thread T1
   SecurityContextHolder[T1] = {Authentication=Alice}
   |
   +--- Controller -> Service runs on T1:
   |       getContext().getAuthentication() -> Alice
   |
   +--- Create job and submit to thread pool
           |
           v
        Worker thread T9
        SecurityContextHolder[T9] ?  <- not automatically Alice
~~~

Successful login **does not mean** `Authentication` is a global variable applying to the entire Java process. In a secure design, T1 and T9 are two distinct execution contexts; T9 holds Alice's permissions only if an **intentional and controlled** mechanism transfers them.

Reading context in Spring code:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication == null) {
    throw new AccessDeniedException("No authentication in this task");
}

String username = authentication.getName();
boolean allowed = authentication.getAuthorities().stream()
        .anyMatch(a -> a.getAuthority().equals("REPORT_READ"));
~~~

This is a **code snippet placed in a Spring-managed service**, requiring Spring Security imports. Do not rely solely on `authentication != null` or `isAuthenticated()` to conclude the principal is a real user: anonymous authentication has its own representation; use `AuthorizationManager`, policies, and appropriate conditions to verify permissions.

### Why Use `ThreadLocal`?

`ThreadLocal` lets functions called on the **same thread** read `SecurityContext` without passing parameters through every method. This is convenient in synchronous Servlet handling. In exchange, when tasks are dispatched to a pool, the program cannot assume workers have the request's `ThreadLocal` data.

If a worker lacks context → method security may deny, services see anonymous, or `NullPointerException` occurs when reading `getAuthentication().getName()`. If a worker retains an old context → there is risk of **cross-user data exposure** and wrong-permission execution. Both cases must be handled with an explicit propagation contract.

## 2. Distinguishing Three Different Kinds of Asynchrony

The word "async" often hides three non-identical situations:

1. **Servlet async request/dispatch**: the container keeps an HTTP request in async mode, may hand off processing work, and later re-dispatches.
2. **Spring MVC async controller**: a controller returns `Callable<T>`, `WebAsyncTask<T>`, `DeferredResult<T>`, or a result type handled by async adapters.
3. **Application-launched background tasks**: submitting jobs to `Executor`/`ExecutorService`, `@Async`, `CompletableFuture`, schedulers, or creating threads directly.

All three can originate from the same request, yet **do not share the same SecurityContext propagation mechanism**.

| Situation | Default behavior to know | How to handle when needing principal in job |
| --- | --- | --- |
| Synchronous service on request thread | Uses current context on the same thread. | No extra wrapper needed if not switching threads. |
| Spring MVC controller returns `Callable<T>` | Spring Security integrates with `WebAsyncManager` to set context on the thread running Callable. | Usually no separate wrapper needed for the Callable itself; test framework and security filter setup. |
| `DeferredResult<T>` completed by an app-used executor | **No automatic integration for arbitrary work** creating/completing DeferredResult. | Use an executor or Runnable/Callable wrapper with propagation. |
| Servlet `AsyncContext.start(Runnable)` via Spring Security request wrapper | Spring Security integrates context propagation for the Runnable. | Ensure proper async-supported/filter mapping; test in practice. |
| `@Async` invoked through Spring proxy | Spring routes method to an executor; context **depends on the configured executor**. | Choose `DelegatingSecurityContextAsyncTaskExecutor` or compatible propagation mechanism. |
| `ExecutorService.submit`, `CompletableFuture.supplyAsync` | Standard JDK executors **do not copy SecurityContext**. | Wrap executor, submit via delegating executor, or pass identity into the job safely. |
| Scheduler, job running minutes later | No live HTTP request remains to read context normally. | Design service identity or actor/permission snapshot with expiration/re-check policies. |

You cannot look at a method name containing "async" and conclude Spring propagates permissions automatically. Identify **who controls thread selection and task execution**.

## 3. Spring MVC `Callable`: The Case with Built-In Integration

With Spring MVC on the Servlet stack, Spring Security integrates with **`WebAsyncManager`**. When a controller returns a `Callable`, the framework can propagate the `SecurityContext` present at **`startCallableProcessing`** to the thread executing the Callable, and clear context once the task finishes.

Example controller in Spring Boot MVC:

~~~java
import java.util.concurrent.Callable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CallableController {

    @GetMapping("/async/callable")
    Callable<String> currentUser() {
        return () -> {
            Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
            return auth == null ? "anonymous" : auth.getName();
        };
    }
}
~~~

This **example requires Spring Boot/Spring MVC/Spring Security dependencies**; it cannot run standalone with only the JDK. When a test authenticates as Alice and Spring Security integration is configured properly, the `Callable` reads Alice's `Authentication` on the worker thread.

**Important detail:** do not describe this mechanism simply as "context is captured at `new Callable`". According to Spring Security, the context used for the Callable is tied to when processing starts in `WebAsyncManager.startCallableProcessing`. If you alter context between constructing the Callable object and the framework actually starting processing, verify exact behavior via integration tests rather than guessing from Java closures.

At the end of async computation, the Servlet container may perform an **`ASYNC` dispatch** to complete the HTTP response. Restoring security context for the dispatch and attaching context to the **Callable worker** are different links in the chain; they rely on filter registration, security context repository/strategy, and servlet configuration. Test both controller execution and response completion when using custom filters or multiple security chains.

`WebAsyncTask` relates to MVC's Callable branch, yet if you manually nest executors or `CompletableFuture` inside the Callable, those sub-tasks **do not automatically inherit all of Callable's propagation**. Only work managed by that mechanism is covered by its contract.

## 4. `DeferredResult`: No Automatic Propagation for User-Managed Work

`DeferredResult<T>` lets a controller return a "promise of a result", while arbitrary code later calls `setResult(...)` or `setErrorResult(...)`. Spring MVC cannot know which executor you submitted work to, which thread it runs on, or when it starts; hence there is **no automatic guarantee of attaching SecurityContext for work completing `DeferredResult`**.

Problematic example:

~~~java
@GetMapping("/async/deferred")
DeferredResult<String> delayed() {
    DeferredResult<String> result = new DeferredResult<>(5000L);

    // rawExecutor is a JDK/Spring Executor NOT YET wrapping security context.
    rawExecutor.execute(() -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        result.setResult(auth == null ? "anonymous" : auth.getName());
    });

    return result;
}
~~~

This is an **illustrative snippet inside a Spring-managed controller**, needing a `rawExecutor` bean and imports; not a standalone Java file. On a default pool, the result is not guaranteed to be the request user; it is often `anonymous` or an empty context. The right fix is not manually calling `SecurityContextHolder.setContext(...)` and forgetting to clear it, because pool threads will serve other users' requests afterward.

A pattern using a wrapped executor:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
class DeferredController {
    private final AsyncTaskExecutor securedTaskExecutor;

    DeferredController(
            @Qualifier("securedTaskExecutor")
            AsyncTaskExecutor securedTaskExecutor) {
        this.securedTaskExecutor = securedTaskExecutor;
    }

    @GetMapping("/async/deferred")
    DeferredResult<String> delayed() {
        DeferredResult<String> result = new DeferredResult<>(5000L);
        securedTaskExecutor.execute(() -> {
            try {
                Authentication auth =
                    SecurityContextHolder.getContext().getAuthentication();
                if (auth == null) {
                    result.setErrorResult(new IllegalStateException(
                            "Missing security context"));
                } else {
                    result.setResult(auth.getName());
                }
            } catch (Exception ex) {
                result.setErrorResult(ex);
            }
        });
        return result;
    }
}
~~~

Configuration of the `securedTaskExecutor` bean follows later. In real systems, **never return raw stack traces/exception messages to users**; an exception mapper must translate failures into safe responses. The example only demonstrates where context must be installed when the task runs, not testing the app's 500/403 status handling.

If tasks can time out, be cancelled, or experience client disconnects, define resource release and context cleanup on every path. Propagation wrappers clean the worker's context in `finally`, yet do not handle timeout/retry business logic on their own.

## 5. Why Do `new Thread` or `ExecutorService` Usually Miss the Principal?

Consider:

~~~java
Authentication inRequest =
        SecurityContextHolder.getContext().getAuthentication();

executorService.submit(() -> {
    Authentication inWorker =
        SecurityContextHolder.getContext().getAuthentication();
    // Do not assume inWorker == inRequest.
});
~~~

By default, Java's `ExecutorService` is a task scheduler and runner, **not a Spring Security mechanism**. It does not know to clone `SecurityContext`, does not know which request's principal applies, and does not automatically update context when users switch.

With a thread pool, the same worker can run Alice's job, then Bob's:

~~~text
Request Alice (T1)  -> submit(Job A) -> Worker T8
Request Bob   (T2)  -> submit(Job B) -> Worker T8 (reused)

Wrong: T8.setContext(Alice); Job A; // not cleared
       Job B keeps seeing Alice -> identity leak

Right: capture context at submit time;
       on T8 set appropriate context for Job A;
       run Job A inside try;
       finally restore/clear context;
       when Job B runs it will have Bob's context if Job B is properly wrapped.
~~~

Calling `SecurityContextHolder.setContext(context)` at the start of a task without a `finally` to clear/restore can have severe consequences if the task throws an exception. Use **`DelegatingSecurityContext...`** wrappers so the framework manages the lifecycle instead of repeating that code across services.

## 6. How Do DelegatingSecurityContextRunnable and Callable Work?

Spring Security provides `DelegatingSecurityContextRunnable` and `DelegatingSecurityContextCallable<T>`, responsible for:

1. Accepting the original task and the context to use (obtainable from `SecurityContextHolder` when creating the wrapper).
2. When running the task on the target thread, setting the corresponding context so code inside the task can read `SecurityContextHolder`.
3. Invoking the original Runnable/Callable.
4. In `finally`, clearing or restoring the worker's previous context per implementation/version, even if the task throws an exception.

Example submitting a `Runnable` with the current context:

~~~java
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.context.SecurityContextHolder;

Runnable job = () -> {
    var auth = SecurityContextHolder.getContext().getAuthentication();
    // Call authorized service, use auth in policy if needed.
};

Runnable wrapped = new DelegatingSecurityContextRunnable(job);
executorService.submit(wrapped);
~~~

This is a **Spring code snippet**; `executorService` must have its lifecycle managed (pool shutdown), not a standalone runnable file. The single-argument constructor uses the context present when the wrapper is created. If you construct the wrapper too early and keep it in a cache or long-lived queue, it may hold a **stale context**, not the principal actually triggering the task later.

If an explicit context is needed in a tightly controlled scenario:

~~~java
SecurityContext captured = SecurityContextHolder.getContext();

Runnable wrapped =
    new DelegatingSecurityContextRunnable(job, captured);

executorService.execute(wrapped);
~~~

This **does not create a deep immutable copy of SecurityContext**. `SecurityContext` and related objects can hold mutable state; if the same object is shared across threads and code mutates `Authentication`, verify thread safety, scope of use, and timing of changes. To replace `Authentication` manually, Spring Security recommends creating a **new empty SecurityContext** and calling `setAuthentication`, avoiding mutating a shared context.

**Never pass the entire HTTP request/session or raw JWT to a worker just to read a username.** If a task needs only an actor ID, passing a minimal immutable input can be a better solution, especially for long-lived jobs; data access permissions must still be checked at execution time.

## 7. Wrapped Executors: Recommended for `@Async`, DeferredResult, and Multiple Tasks

Instead of forcing every service to know about `DelegatingSecurityContextRunnable`, you can wrap the **Executor** once. Common classes:

| Spring Security class | Wraps what object? | Best used for |
| --- | --- | --- |
| `DelegatingSecurityContextExecutor` | `java.util.concurrent.Executor` | Submitting `Runnable`s via `execute`. |
| `DelegatingSecurityContextExecutorService` | `ExecutorService` | `submit` Runnable/Callable, `Future`, and `ExecutorService` APIs. |
| `DelegatingSecurityContextAsyncTaskExecutor` | Spring `AsyncTaskExecutor` | Integrating with `@Async`, Spring executors, Runnable/Callable tasks. |
| `DelegatingSecurityContextTaskExecutor` | Spring `TaskExecutor` | When only the task executor contract is needed. |
| `DelegatingSecurityContextSchedulingTaskExecutor` or dedicated scheduling classes | Scheduling executor | When integrating specifically with a scheduler under an appropriate identity. |

**There are two important context modes:**

- Constructor **without a fixed `SecurityContext`**: typical delegating executors read the **submitting thread's context at submit/execute time**, then wrap the task. Suitable for work on behalf of the current user.
- Constructor **with a fixed `SecurityContext`**: every task uses the supplied context. Use only when there is genuinely a managed **service identity** authorized for all those jobs, never accidentally pinning admin Alice's context at bean startup so everyone else inherits admin rights.

A **Spring Boot 3 + Spring Security 6** configuration example with dedicated beans for `@Async` and `DeferredResult`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
public class SecuredAsyncConfiguration {

    @Bean("rawWorkerExecutor")
    ThreadPoolTaskExecutor rawWorkerExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(50);
        pool.setThreadNamePrefix("secured-worker-");
        return pool;
    }

    @Bean("securedTaskExecutor")
    AsyncTaskExecutor securedTaskExecutor(
            @Qualifier("rawWorkerExecutor")
            ThreadPoolTaskExecutor rawWorkerExecutor) {
        return new DelegatingSecurityContextAsyncTaskExecutor(
                rawWorkerExecutor);
    }
}
~~~

When `ThreadPoolTaskExecutor` is a Spring bean, Spring manages initialization/shutdown per its lifecycle. The snippet above **requires Spring Framework and Spring Security dependencies** and cannot compile with plain JDK alone. Naming beans helps avoid confusing the raw executor with the secured one. Never run all scheduled jobs under a request user's context when there is no request.

Using it in a service:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class ReportAsyncService {

    @Async("securedTaskExecutor")
    public CompletableFuture<String> actorName() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        if (auth == null) {
            return CompletableFuture.completedFuture("anonymous");
        }
        return CompletableFuture.completedFuture(auth.getName());
    }
}
~~~

Another bean calling `reportAsyncService.actorName()` **through the Spring proxy** dispatches the method to the named executor. `@EnableAsync` enables the `@Async` mechanism; **self-invocation** like `this.actorName()` inside the same bean can bypass the proxy and run synchronously without using the executor. Also manage `@Async` exception handling and backpressure when the queue fills up.

**Avoid confusion:** `@Async` does not grant roles/permissions on its own; the wrapped executor only lets the task see the identity/authorities from submit time. If the task mutates data, policies must still check owner, tenant, and actual state.

## 8. `CompletableFuture`: Stages Can Run on Different Threads

A common mistake:

~~~java
CompletableFuture.supplyAsync(() -> {
    Authentication a =
        SecurityContextHolder.getContext().getAuthentication();
    return a == null ? "anonymous" : a.getName();
});
~~~

When no custom `Executor` is passed, `CompletableFuture.supplyAsync` uses the JDK's **default async execution facility** (typically the common ForkJoinPool). It has no knowledge of the Servlet request's `SecurityContextHolder`. You cannot rely on a test environment "happening" to run on the same thread as the request.

If you configured a context-propagating executor, specify **that exact executor** for stages that need context:

~~~java
CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> {
    Authentication a =
        SecurityContextHolder.getContext().getAuthentication();
    return a == null ? "anonymous" : a.getName();
}, securedTaskExecutor);
~~~

This snippet assumes `securedTaskExecutor` is the `AsyncTaskExecutor` bean above, which also implements `Executor`. With `CompletableFuture` stage chains:

~~~java
future.thenApply(name -> name.toUpperCase());       // no contract to switch threads
future.thenApplyAsync(name -> name.toUpperCase());  // may use common pool
future.thenApplyAsync(name -> name.toUpperCase(),
                      securedTaskExecutor);         // uses specified executor
~~~

If a subsequent stage needs `Authentication`, do not assume that because the first stage was wrapped, all following `thenApplyAsync` calls carry the same context. **Every asynchronous scheduling boundary must be verified.** When a stage is registered after the request has already finished, capturing context at registration/submit time may no longer hold the original principal; design actor context as an explicit input, or wrap properly at a trustworthy point.

Non-async stages like `thenApply` may run on the thread completing the previous stage or on the registering thread if the future is already complete; **never treat thread-scheduling assumptions as a security policy**. `CompletionStage` is not itself a security context carrier.

## 9. Servlet `AsyncContext.start` and ASYNC Redispatch

Outside Spring MVC, the Servlet API provides:

~~~java
AsyncContext async = request.startAsync();
async.start(() -> {
    Authentication a =
        SecurityContextHolder.getContext().getAuthentication();
    // Can read context when routed through Spring Security integration
    // and a properly configured Servlet async request wrapper.
    async.complete();
});
~~~

Spring Security integrates with `AsyncContext.start(Runnable)` to propagate the request's context into the Runnable. However, this **does not mean** every way of spawning threads in a Servlet is wrapped automatically. It applies only when the request passes through Spring Security's Servlet API integration with async support properly configured.

An **ASYNC dispatch** is the subsequent pass in the Servlet container after asynchronous processing. Distinguish:

- The worker thread runs a Callable or Runnable with security context via propagation.
- The request is **re-dispatched** by the Servlet container with `DispatcherType.ASYNC`, potentially passing through the filter chain depending on filter mapping and config.
- Different filters (including custom `OncePerRequestFilter`s) may apply separate rules for initial dispatches vs. subsequent dispatches.

In modern Spring Boot Servlet configurations, async support is usually auto-configured appropriately. If an older app registers `DelegatingFilterProxy` via `web.xml` or registers filters manually, ensure `async-supported` and dispatcher types—typically including **`REQUEST`** and **`ASYNC`**—match the design; otherwise context management on redispatch may behave unexpectedly.

**`AuthorizationFilter`** can evaluate multiple dispatcher types. When using `authorizeHttpRequests`, review policies for `DispatcherType.ASYNC` and `ERROR`: do not automatically `permitAll` all ASYNC dispatches just to silence 403s, as that shifts authorization boundaries on redispatches. Instead, verify the chain, matchers, and context on each pass; if a dispatcher exception is needed, declare it narrowly and ensure initial-request permissions still hold.

## 10. Do MODE_INHERITABLETHREADLOCAL and MODE_GLOBAL Solve Everything?

Spring Security allows changing `SecurityContextHolderStrategy`, for example:

- **`MODE_THREADLOCAL`**: default suitable for most Servlet apps; context is per-thread.
- **`MODE_INHERITABLETHREADLOCAL`**: a *newly created* child thread can inherit the context value at thread creation time. **Not a safe identity-propagation mechanism for pre-existing pools**.
- **`MODE_GLOBAL`**: uses a process-wide holder; **unsuitable for multi-user servers**, risking one account overwriting another account's context.

**Why is InheritableThreadLocal dangerous with thread pools?** Worker threads may have been created long ago when one user happened to initialize the pool. Later requests merely **reuse workers** rather than creating new threads, so inherited context can be **stale**, not the current request's context. Even on newly spawned child threads, inner context objects may be shared and mutated. The result can be permission leaks or tests passing locally yet failing under production load.

Changing the app-wide strategy to rescue one `@Async` missing context is usually overly broad. **Prefer per-task wrappers/executors**, inspect lifecycles, and re-verify if permissions change. Never use `MODE_GLOBAL` in a multi-user Servlet app.

## 11. Consistency and Security of Context Propagated to Workers

Having the right context on a worker **does not mean** the task's permissions are permanently valid:

1. **Capture time:** a wrapper may capture context at task submission. If queued for 20 minutes, the user may already have had permissions revoked.
2. **Execution time:** the task may need to re-check server-side permissions and resource state (tenant, owner, status, quotas) right before side effects.
3. **Mutable context:** `SecurityContext` does not automatically become a deep immutable snapshot; avoid mutating `Authentication` inside a context shared across threads.
4. **Data partitioning:** a user holding `ORDER_APPROVE` at submit time cannot approve arbitrary orders, especially across tenants.
5. **Timeouts and cancellation:** tasks may keep running after the client disconnects; enforce cancellation conditions, job ownership, and idempotency.
6. **Audit:** record valid actor, timestamp, and task reason; never treat thread name or MDC as proof of identity.
7. **Do not transport secrets:** avoid putting raw JWTs, passwords, cookies, or Servlet request objects into long-lived queues. If a task needs service credentials, use a dedicated managed service-credential/identity mechanism.
8. **Do not cross trust boundaries arbitrarily:** an in-process executor differs completely from publishing messages to Kafka/RabbitMQ or pushing jobs to another service. Spring's `ThreadLocal` **does not cross networks/processes**.

For long-running background jobs, the clean approach is usually passing **jobId + actorId + tenantId + action** as verified immutable data; the worker re-reads policy at run time or uses a least-privilege service identity. Passing an actor ID **does not replace authorization**: the receiver must verify the event/queue source, scope, and effective permissions.

### "Running with the User's Identity" Differs from "Authorized to Perform the Job"

A report-export operation may be submitted while Alice holds `REPORT_EXPORT`. When the executor propagates context, code can read Alice's `Authentication`. Yet to export all orders for a tenant, the service still must verify:

~~~text
actor.role/authority (REPORT_EXPORT)
  AND report.tenant == actor.currentTenant
  AND report.owner/sharedScope is allowed
  AND export job still eligible
  AND quota/consent/business checks are valid
~~~

An `Authentication` from submit time does not guarantee all these conditions remain true after a delay. For sensitive tasks, have an explicit way to cancel or re-check permissions before generating files, sending emails, or writing data.

## 12. Standalone Java 17+: ThreadLocal, Capture, and Cleanup with Thread Pools

The standalone example below uses no Spring Security; it simulates a **per-thread principal** with `ThreadLocal<String>` and a `Callable` wrapper capturing the value on the submitting thread. It serves to teach the principle, **not as a replacement** for Spring's `DelegatingSecurityContext...` classes.

Design:

- Alice's request sets context on the main thread.
- A single-thread pool initially does not see Alice's context.
- The wrapper captures Alice to run on the pool, then `finally` clears/restores the worker context.
- When the main thread switches to Bob, the **previously created** wrapper still holds Alice; a new wrapper carries Bob.
- A wrapped task throws an exception yet the worker afterward returns to anonymous, proving cleanup works.

Save with the exact filename **`ThreadContextPropagationDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadContextPropagationDemo {
    private static final ThreadLocal<String> ACTOR = new ThreadLocal<>();

    static String currentActor() {
        return ACTOR.get() == null ? "anonymous" : ACTOR.get();
    }

    static <T> Callable<T> capture(Callable<T> task) {
        String capturedActor = ACTOR.get();
        return () -> {
            String previousActor = ACTOR.get();
            try {
                if (capturedActor == null) ACTOR.remove();
                else ACTOR.set(capturedActor);
                return task.call();
            } finally {
                if (previousActor == null) ACTOR.remove();
                else ACTOR.set(previousActor);
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            ACTOR.set("alice");
            System.out.println("request alice: " + currentActor());
            System.out.println("plain pool: "
                    + pool.submit(ThreadContextPropagationDemo::currentActor).get());
            Callable<String> aliceTask = capture(
                    ThreadContextPropagationDemo::currentActor);
            System.out.println("wrapped alice: " + pool.submit(aliceTask).get());
            System.out.println("pool after alice: "
                    + pool.submit(ThreadContextPropagationDemo::currentActor).get());

            ACTOR.set("bob");
            System.out.println("captured before switch: "
                    + pool.submit(aliceTask).get());
            System.out.println("wrapped bob: "
                    + pool.submit(capture(
                            ThreadContextPropagationDemo::currentActor)).get());
            try {
                pool.submit(capture(() -> {
                    throw new IllegalStateException("expected");
                })).get();
            } catch (ExecutionException ex) {
                System.out.println("wrapped task failed: "
                        + ex.getCause().getMessage());
            }
            System.out.println("pool after failure: "
                    + pool.submit(ThreadContextPropagationDemo::currentActor).get());
        } finally {
            ACTOR.remove();
            pool.shutdownNow();
        }
    }
}
~~~

Compile/run with JDK 17 or higher:

~~~bash
javac --release 17 ThreadContextPropagationDemo.java
java ThreadContextPropagationDemo
~~~

Standard output:

~~~text
request alice: alice
plain pool: anonymous
wrapped alice: alice
pool after alice: anonymous
captured before switch: alice
wrapped bob: bob
wrapped task failed: expected
pool after failure: anonymous
~~~

**Reading the output:**

- `plain pool: anonymous` proves `ThreadLocal` on the thread calling `submit` does not automatically cross to the worker.
- `wrapped alice: alice` works by capturing context and installing it on the worker.
- `pool after alice: anonymous` and `pool after failure: anonymous` prove cleanup via `finally` even when the task fails.
- `captured before switch: alice` warns about snapshots bound into old wrappers: a caller Bob submitting Alice's wrapper would run as Alice. **Never reuse another user's wrapped task/context.**
- `wrapped bob: bob` shows Bob's separately wrapped task carries the right identity.

The demo's wrapper uses an immutable `String`, simpler than a real `SecurityContext`. With Spring, use framework-provided classes, follow context propagation/storage constraints, and never create a global `ThreadLocal` holding tokens.

## 13. Is Passing Authentication as a Parameter Better Than Using ThreadLocal?

There is no single right answer for every case; it depends on what the task needs context for.

### Situation A — Task Calls a Service Using Method Security

If the service is protected by `@PreAuthorize("hasAuthority('REPORT_EXPORT')")` and checks permissions via `SecurityContextHolder`, the worker needs an appropriate context **when invoking the method** or must supply a separate trusted `Authentication`. Here `DelegatingSecurityContextAsyncTaskExecutor` or `DelegatingSecurityContextExecutorService` fits short in-process jobs.

### Situation B — Task Needs Only Actor ID for Auditing

If the job has no Spring method-security requirement and only needs the actor for audit logging, passing an immutable `actorId` in the command object can be simple, easy to test, and less prone to context leaks. However, never treat that ID itself as access permission; worker policies must still be checked.

### Situation C — Task Runs Outside a Request or via a Message Queue

Scheduled jobs and event consumers have no HTTP context by nature. Use an **explicit service principal/authorization context** with managed credentials and scope, or domain-level permission checks. An empty `SecurityContextHolder.getContext()` on a worker is normal here, not a bug to fix with `MODE_GLOBAL`.

### Situation D — Long-Running Task with Frequently Changing Permissions

Saving only `SecurityContext` from submit time risks staleness. Design **execution-time authorization**, refresh/revocation, and constraints by tenant, owner, and live state. You can combine propagated context for auditing the initiating user with a decision policy reading current data. Never treat a principal snapshot as an unlimited permission token.

## 14. SecurityContext Propagation Does Not Mean Propagating Every Other Context

In web apps, besides `SecurityContextHolder` there are:

- `RequestContextHolder` and `ServletRequestAttributes`.
- Logging MDC (request ID, trace ID, tenant debug tag).
- Thread-bound transaction context from Spring Transaction.
- Locale, tracing/observation context, and other application `ThreadLocal`s.

**DelegatingSecurityContextExecutor propagates only Spring Security context per its mechanism**, not automatically MDC, transactions, request attributes, or every other `ThreadLocal`. A task having the right `Authentication` yet empty MDC does not indicate broken security propagation. Conversely, a task having MDC `user=alice` **is not proof** it holds Alice's `Authentication`.

Do not copy entire `ServletRequestAttributes` to long-lived jobs just to read tenant/request ID: requests are short-lived and may be recycled/cleaned up. Extract needed metadata into immutable commands and limit retention of sensitive data.

General context-propagation utilities or `TaskDecorator`s must be configured carefully so they do not copy security context twice or retain references too long. When an app uses both Spring Security wrappers and another context-propagation library, designate the **primary source** for authentication and add tests verifying cleanup and cross-user isolation.

## 15. Testing Properly: asyncDispatch, Concurrent Users, and Exception Cases

**Testing only synchronous controllers is insufficient.** A `SecurityContextHolder` test on the calling thread does not prove worker threads see the right context. For Spring MVC async, use `spring-security-test` and `MockMvc` to verify both the waiting phase and result dispatch.

Example test for `Callable` with a controller like section 3:

~~~java
MvcResult result = mvc.perform(
        get("/async/callable")
            .with(user("alice").roles("USER")))
    .andExpect(request().asyncStarted())
    .andReturn();

mvc.perform(asyncDispatch(result))
    .andExpect(status().isOk())
    .andExpect(content().string("alice"));
~~~

This is a **snippet inside a Spring Boot/JUnit/MockMvc test**, requiring injected `MockMvc`, Spring Security Test, corresponding static imports, the endpoint fixture, and the filter chain integrated into MockMvc. It illustrates two-phase testing, not a standalone Java program.

For `@Async` services, test invoking the method **through the Spring bean/proxy** and the `securedTaskExecutor` bean, rather than calling `new` on an instance directly. Use `CountDownLatch` or `Future.get(timeout)` in tests to control completion and avoid race conditions; never rely on `Thread.sleep(...)` as trustworthy proof.

Test matrix to include:

| Case | What to verify |
| --- | --- |
| Request Alice → MVC `Callable` | Worker reads Alice's `Authentication`; expected response. |
| Request Bob → another `Callable` | Does not see Alice even when thread pool is reused. |
| `DeferredResult` using raw executor | Do not assume request context appears on worker automatically. |
| `DeferredResult` using secured executor | Task reads right identity, result completes async response. |
| `@Async` via Spring proxy | Executor configured properly, in-task policy sees right principal. |
| `@Async` self-call in same class | Detects proxy bypass / non-async execution. |
| `CompletableFuture.supplyAsync` without executor | Do not assume context exists; test real JDK executor behavior. |
| `thenApplyAsync` after context-aware stage | Check which executor the stage uses; does not inherit from prior stage automatically. |
| Task throws before returning | Worker thread context is cleared in `finally`. |
| Alice task then Bob task on same pool | Bob cannot see Alice; prevents cross-user data leakage. |
| Long pool queue wait and permission revoked | Execution-time policy blocks sensitive job if permission is no longer valid. |
| Anonymous or insufficient permission | Fails closed or returns designed error; never assigns arbitrary service/admin context. |
| HTTP ASYNC dispatch | Right security chain/matchers and response on redispatch; do not auto-permit all ASYNC. |
| Job run from scheduler with no HTTP request | Uses explicit service identity/command, not `SecurityContextHolder` user. |

When testing pool context propagation, a strong technique is creating a **single-thread pool** and running A then B sequentially to force worker reuse, checking after each job that context is clean. With multi-thread pools, design synchronized tests to actually hit the same worker rather than concluding "no leak" merely because the scheduler picked a different thread.

If a test has `@WithMockUser`, that context is installed by the test framework on the test/HTTP request thread; it **does not** turn every `ExecutorService` used in tests into a propagating executor. Verify the real wrapper/bean classes.

## 16. Troubleshooting Common Errors

### "Controller Sees the User, Yet `@Async` Sees Null"

Check in order:

1. Is `@EnableAsync` enabled? Is the method invoked through a Spring proxy or self-invocation?
2. Which executor bean does `@Async` use? Is it `securedTaskExecutor`?
3. Was the task submitted from a thread holding a valid context **at the exact moment of submission**?
4. Is there a subsequent `CompletableFuture` stage using the common pool?
5. Did anything clear context before submit or create the wrapper too early?
6. Does a custom security context strategy or custom filter alter how context is stored?

Never fix this by setting `SecurityContextHolder.MODE_GLOBAL` or hard-coding admin credentials for workers.

### "Bob's Job Ran with Alice's Permissions"

This is a **critical bug**. Look for:

- Code calling `SecurityContextHolder.setContext(...)` without a `finally`.
- `InheritableThreadLocal` with pooled threads or custom `ThreadLocal`s left behind.
- An executor bean built with **Alice's fixed SecurityContext** instead of reading context per submission.
- A `Runnable` or `Callable` wrapped for Alice, then cached and re-submitted under Bob's request.
- A shared `SecurityContext` object mutated from another thread.
- A custom task decorator or listener leaving stale MDC/security state behind.

Halt sensitive actions and inspect blast radius, audit logs, and isolation before deploying fixes to production. Then add A→B→A regression tests on the same worker plus exception-path tests.

### "Task Finished Yet HTTP Request Never Returned"

Context propagation does not make a job send an HTTP response on its own: for `DeferredResult`, call `setResult`/`setErrorResult`; for Servlet async, complete `AsyncContext`; for MVC Callable, the framework manages completion. Check timeouts, executor rejections, deadlocks, unawaited futures, controller mappings, and ASYNC redispatches. Do not equate "having a principal" with "proper request lifecycle".

### "MDC Has Trace Yet Authentication Is Missing"

MDC and `SecurityContextHolder` are two separate contexts; frameworks or instrumentation may propagate MDC without propagating SecurityContext. Check the executor and propagation mechanism separately. Avoid using `MDC.get("user")` for authorization decisions.

### "Async Request Returns 403 on Final Dispatch Pass"

Check dispatcher type, `AuthorizationFilter`, `securityMatcher`, actual roles/authorities, and filter registration for ASYNC. If a custom filter is invoked again, inspect `shouldNotFilterAsyncDispatch()` and that filter's auth policy. Never use `requestMatchers("/**").permitAll()` just to mask async errors, as it opens every endpoint.

## 17. Secure Implementation Checklist

1. Identify the async kind: Spring MVC `Callable`, `DeferredResult`, Servlet `AsyncContext`, `@Async`, JDK executor, or scheduler.
2. Distinguish the request thread from the task-executing thread; state clearly **who creates context** and **when context is captured**.
3. For MVC `Callable`, verify `WebAsyncManager` integration and test `asyncDispatch`.
4. For app-owned tasks, use `DelegatingSecurityContextRunnable`/`Callable` or the matching **delegating executor**.
5. Choose per-submit context for work on behalf of users; use fixed context only for governed task/service identities.
6. Never use `MODE_GLOBAL` in multi-user servers and do not rely on `MODE_INHERITABLETHREADLOCAL` to propagate context on thread pools.
7. Ensure context cleanup/restoration in `finally` even on task exceptions, timeouts, or cancellation.
8. With `@Async`, enable proxying via `@EnableAsync`, call from another bean, and specify the right executor.
9. With `CompletableFuture`, pass the executor to every async stage needing context; do not rely on the default common pool.
10. Do not confuse Spring Security context propagation with MDC, request scope, transactions, or HTTP data.
11. Do not treat a context snapshot as a permanent permission grant; re-check resource, tenant, and latest permissions at execution time if business logic requires it.
12. Test the same worker serving Alice then Bob, failing tasks, long-queued tasks, anonymous, revocation, and ASYNC redispatches.
13. Use explicit actor IDs/service identities for schedulers, queues, or cross-process tasks; do not pass raw JWTs or Servlet request objects into long-lived jobs.
14. Never disable the entire security filter chain, turn off authorization, or assign default admin rights to fix missing SecurityContext errors.

**Conclusion:** On the Servlet stack, `SecurityContextHolder` by default guarantees context only on the **current thread**. Spring Security provides automatic integration for **Spring MVC Callable** and **`AsyncContext.start`** under proper conditions, yet **does not automatically propagate context to every app-scheduled task**, especially `DeferredResult`, `@Async` without an appropriate executor, and `CompletableFuture` on the common pool. Choose propagation mechanisms tailored to thread boundaries, capture context at the right moment, clean up workers even on errors, and always distinguish **carried identity** from **still-valid business permissions**.

### Official References

- [Spring Security — Servlet Authentication Architecture and SecurityContextHolder](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Security 6.5 — Spring MVC Async Integration: Callable and DeferredResult](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/mvc.html)
- [Spring Security — Servlet API Integration: AsyncContext.start(Runnable)](https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html)
- [Spring Security 6.5 — DelegatingSecurityContextAsyncTaskExecutor Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/task/DelegatingSecurityContextAsyncTaskExecutor.html)
- [Spring Security 6.5 — DelegatingSecurityContextExecutorService Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextExecutorService.html)
- [Spring Framework — Spring MVC Async Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
