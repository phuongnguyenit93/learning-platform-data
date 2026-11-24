# Thread Lifecycle and the Limits of `ThreadLocal` in Web Applications

> **Context:** Servlet foundation, Java 17+, web applications using Spring Security on the Servlet stack. This lesson focuses on the relationship between an **HTTP request**, a **Servlet container thread**, and **thread-bound context**. Examples using only Java SE are noted explicitly; snippets using Spring/Spring Security require the corresponding libraries and application lifecycle.

## 1. Three Lifecycles to Distinguish

- **HTTP request:** begins when the server receives the request and ends when processing/writing the response finishes (in asynchronous cases, it can outlive the initial thread leaving the filter chain).
- **Processing thread:** an execution resource managed by the Servlet container or an executor. One thread can serve many requests sequentially; one asynchronous request can be processed across multiple threads.
- **`ThreadLocal` value:** belongs to the **executing thread**, persisting until overwritten, cleared via `remove()`, or the thread itself terminates. It does not vanish simply because a request returned a response.

Therefore, the equation “one request = one thread = one isolated memory slot” is only an approximation during a **synchronous processing segment**, and is not a Servlet API guarantee. This is the root cause of cross-request data leaks, reading the wrong user, and losing context in async execution.

### Typical synchronous Servlet flow

~~~text
Client sends HTTP request
  -> Servlet container accepts and assigns thread T1 from pool
  -> Servlet Filter chain (including Spring Security filters)
  -> DispatcherServlet -> Controller -> Service -> returns result
  -> Filter chain finishes; bound contexts are cleaned up in finally
  -> T1 returns to the pool and can serve another request
~~~

During that pass, a security filter can provide `SecurityContext` for the current thread; controllers/services access it via `SecurityContextHolder`. When leaving the chain, cleanup of thread-bound state must occur even if an exception is thrown. **The thread remains alive** in the pool, so leftover values can show up in a subsequent request.

## 2. What Does `ThreadLocal<T>` Actually Do?

`ThreadLocal<T>` is a key that lets each `Thread` store its own value. With the same `ThreadLocal` object, thread T1 can see `alice`, while T2 sees `bob`. A `static ThreadLocal<?>` variable is a **shared key**, which does not mean the stored value is shared across all threads.

Primary operations:

| API | Meaning |
| --- | --- |
| `set(value)` | Sets the value for the **current thread**. |
| `get()` | Reads the value on the current thread; defaults to `null` if unset and no `initialValue` is defined. |
| `remove()` | Unbinds the current thread's value so future reuse starts clean. |
| `ThreadLocal.withInitial(supplier)` | Supplies an initial value per thread; does **not** eliminate the need for per-request cleanup. |

`ThreadLocal` does not automatically carry data onto threads of `ExecutorService`, `CompletableFuture`, or Servlet async. Nor is it a place to store sessions, long-lived business data, or an inter-thread communication channel.

### Why do thread pools easily cause bugs?

Containers keep threads for reuse. If request A binds `alice` onto T1 and forgets `remove()`, a later request B scheduled onto the same T1 can read `alice` again. If T2 happens to handle request B, the bug can “disappear”, hiding it from low-load tests. Calling `set(null)` does not clearly express unbinding and can leave an entry behind; prefer `remove()`.

## 3. Java 17 Experiment: Leaks Across Reused Threads

Create **`ThreadLocalLifecycleDemo.java`**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ThreadLocalLifecycleDemo {
    private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            pool.submit(() -> {
                CURRENT_USER.set("alice");
                System.out.println("A: " + CURRENT_USER.get());
                // Intentionally omit CURRENT_USER.remove().
            }).get();

            pool.submit(() ->
                System.out.println("B: " + CURRENT_USER.get())
            ).get();

            pool.submit(() -> {
                CURRENT_USER.set("carol");
                try {
                    System.out.println("C: " + CURRENT_USER.get());
                } finally {
                    CURRENT_USER.remove();
                }
            }).get();

            pool.submit(() ->
                System.out.println("D: " + CURRENT_USER.get())
            ).get();
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac ThreadLocalLifecycleDemo.java
java ThreadLocalLifecycleDemo
~~~

Exact output:

~~~text
A: alice
B: alice
C: carol
D: null
~~~

`newSingleThreadExecutor()` guarantees all four tasks run sequentially on the same worker thread; `Future.get()` waits for each task to finish. Task B **did not set** a user yet still saw `alice` because task A skipped cleanup. Task C set a new value and cleaned up in `finally`, so D saw `null`. This example simulates thread reuse, **not** a full Servlet container or Spring Security.

Lesson: any code managing a `ThreadLocal` itself must follow **bind → work → remove in finally**. When using a framework-managed context, let the appropriate framework component handle cleanup.

## 4. Safe Usage Pattern in a Servlet Filter

The example below illustrates a custom context (request ID) in a Jakarta Servlet app using `jakarta.servlet-api`. This is an **integration class**, not a standalone Java SE program.

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import java.io.IOException;
import java.util.UUID;

public final class RequestIdFilter implements Filter {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    public static String currentRequestId() {
        return REQUEST_ID.get();
    }

    @Override
    public void doFilter(ServletRequest request,
                         ServletResponse response,
                         FilterChain chain)
            throws IOException, ServletException {
        REQUEST_ID.set(UUID.randomUUID().toString());
        try {
            chain.doFilter(request, response);
        } finally {
            REQUEST_ID.remove();
        }
    }
}
~~~

The filter must be registered in the application via proper Servlet/Spring configuration. Regardless of whether the controller returns normally or throws an exception, `finally` cleans up the binding on the **thread running the filter**. If logic before `try` could throw after binding, move it inside the protected block; for example, generating `UUID.randomUUID()` before `set` avoids that case.

**Important limitation:** `finally` on the current dispatch pass does not mean the entire HTTP request is over if async is enabled; this `ThreadLocal` value will not automatically exist on the async worker thread. If you only need an ID across the request, consider a **request attribute** and pass the ID explicitly into background work instead of expecting `ThreadLocal` to survive across threads. You must also handle nested invocations or filter re-dispatch: setting a new value and calling `remove()` will not restore a thread's previous value. For potentially nested code, define an explicit save/restore policy rather than applying this pattern mechanically.

Example of a thread-independent request attribute:

~~~java
String requestId = UUID.randomUUID().toString();
request.setAttribute("requestId", requestId);
chain.doFilter(request, response);
~~~

The second snippet is code inside a filter having `request`, `response`, `chain`, and matching imports; request attributes belong to `ServletRequest`, so downstream steps holding the same request object can read them. Do not use it after the request lifecycle ends.

## 5. What Changes When an HTTP Request Is Asynchronous?

In Servlet async, one request can go through multiple execution phases:

~~~text
T1: receives request -> filter/controller -> startAsync() or MVC starts async
T1: exits initial dispatch, returned to pool (request is not finished yet)
T2: executor runs asynchronous work
T3: container may ASYNC-dispatch to complete the response
     (T1, T2, T3 may be the same or different threads; do not assume)
~~~

- Values bound to T1 via `ThreadLocal` **do not automatically transfer** to T2/T3.
- Trying to keep values on T1 “until async finishes” risks leaking to other requests because T1 has already been returned to the pool for reuse.
- `InheritableThreadLocal` only lets **newly created** threads inherit values from the parent thread at thread creation time (usually sharing the same reference for mutable objects). It does not safely update tasks running on an already existing thread pool; therefore, never use it as a request identity propagation mechanism.
- Servlet `AsyncContext.start(...)`, `CompletableFuture.supplyAsync(...)`, `@Async`, and custom executors each require checking **their own context-propagation mechanism**. By default, `CompletableFuture` may use the common pool, which has no caller request context.

There are three sound ways to control this: **(1)** pass minimal data explicitly as task parameters, **(2)** use framework-provided wrappers/context propagation, or **(3)** store data on the request and retrieve it from the request in valid dispatches. Never casually copy the entire request object or security context into long-lived storage.

### Passing values explicitly

If a task only needs a customer identifier, capture it in a variable before submitting and pass it as an argument, for example:

~~~java
String customerId = currentCustomerId; // Already authenticated/authorized in the request.
executor.execute(() -> processCustomer(customerId));
~~~

This is an **illustrative snippet** inside a service that has `currentCustomerId`, `executor`, and `processCustomer`; it does not run standalone. The parameter makes the dependency explicit and decouples business logic from any specific thread. At the new execution/authorization boundary, you must still enforce authorization per application policy; carrying an ID into a task does not by itself grant permission.

## 6. How Does Spring Security Use `ThreadLocal`?

On the **Servlet stack**, `SecurityContextHolder` uses the `MODE_THREADLOCAL` strategy by default. It provides the current thread's `SecurityContext`, typically holding `Authentication`. Thus, during **synchronous** processing inside the Spring Security filter chain, a component can call:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

This is a **Spring Security snippet**, requiring imports for `org.springframework.security.core.Authentication` and `org.springframework.security.core.context.SecurityContextHolder`. `Authentication` may be `null` or an anonymous authentication; **do not rely on `isAuthenticated()` alone to make access decisions**. Prefer Spring Security's authorization mechanisms (HTTP security, method security, authorization managers) for security decisions.

In a typical Servlet setup, security-context-managing filters (such as `SecurityContextHolderFilter` in modern setups, or `SecurityContextPersistenceFilter` in other setups) supply the context to the chain and **clear it from the thread when the chain exits**. How context is loaded/saved into `SecurityContextRepository` depends on configuration and version; persisting context for subsequent requests is distinct from clearing `ThreadLocal` after the request. **Clearing context from the thread does not log the user out or destroy the session.**

Do not call `SecurityContextHolder.clearContext()` mid-way in a controller/service if downstream code still relies on the current authentication. When manually setting context inside an **independent task you manage yourself**, use a safe set/restore/clear cycle, ideally via Spring Security's wrappers. Never enable `MODE_GLOBAL` in a multi-user server: that mode shares one context across the entire JVM. Nor does `MODE_INHERITABLETHREADLOCAL` safely handle thread pool reuse.

### Integrating async execution with Spring Security

- **Spring MVC `Callable`:** Spring Security integrates via `WebAsyncManagerIntegrationFilter` to propagate `SecurityContext` onto the thread running a Spring MVC-managed `Callable`, provided the filter chain is integrated properly. Do not extend that guarantee to arbitrary self-submitted tasks.
- **`DeferredResult` / custom callbacks / `CompletableFuture`:** completing on an external thread does not automatically inherit the security context from the initiating request. You must explicitly pass data or wrap the executor/task.
- **`@Async`:** you can configure `DelegatingSecurityContextAsyncTaskExecutor` for an appropriate executor; check capture and cleanup timing in your actual configuration.
- **ExecutorService:** `DelegatingSecurityContextExecutorService` can wrap an executor to transfer context to tasks upon submission and restore/clear context around task execution.

Example **integration snippet** in a service that already has a long-lived `ExecutorService delegate`:

~~~java
ExecutorService securedExecutor =
        new DelegatingSecurityContextExecutorService(delegate);

securedExecutor.submit(() -> {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    // Use auth only within the verified scope and policy.
});
~~~

This requires importing `java.util.concurrent.ExecutorService`, `org.springframework.security.concurrent.DelegatingSecurityContextExecutorService`, `org.springframework.security.core.Authentication`, and `org.springframework.security.core.context.SecurityContextHolder`. The wrapper cannot replace authorization checks, does not address tasks running after an identity changes or loses permissions, and its lifecycle must match the underlying executor (bean/shared executor, shut down when the app closes). Avoid creating a new pool per request. When using constructors that accept an explicit context, distinguish a **fixed context** from context captured at submission time; never accidentally run every task under a single user's identity.

### Where is the trust boundary?

`SecurityContextHolder.getContext()` reflects the context bound to the thread **at the moment of the call**, not independent proof that all downstream work remains authorized. Business logic running via message queues, schedulers, event listeners, or separate thread pools must explicitly design identity and permissions for **each execution**. Never put a shared “super-user” in a `ThreadLocal` to paper over missing-context bugs.

## 7. `OncePerRequestFilter` and Async Dispatch

The name `OncePerRequestFilter` can be misleading: the notion of “once” depends on **a single dispatch pass**, how the filter is registered, and async/error dispatch policies. When an async dispatch occurs, another thread may enter the filter chain depending on dispatcher type and configuration. Hooks like `shouldNotFilterAsyncDispatch()` control whether a custom filter participates in async dispatches.

Therefore, if you bind context yourself inside a filter:
1. Identify which dispatcher types the filter runs on (`REQUEST`, `ASYNC`, `ERROR` as applicable).
2. Bind context cleanly for **each thread/dispatch that needs it**, and clean up in `finally` for that pass.
3. To preserve data across an async request, use request-scoped storage or pass it explicitly; **never leave bindings on a thread that has exited a dispatch**.

There is no default rule that a custom filter runs only once across the entire asynchronous HTTP lifecycle.

## 8. Common Bugs, Root Causes, and Fixes

| Symptom | Root cause | Fix direction |
| --- | --- | --- |
| Request B occasionally sees A's user/request ID | Thread pool reuses a worker still holding stale values | Bind explicitly at scope start, `remove()` in `finally`; test multiple requests on one executor. |
| Async task sees `null` in `SecurityContextHolder` | Task runs on another thread without the corresponding context | Pass minimal identity explicitly or use Spring Security's executor wrappers. |
| Works in simple tests, fails under heavy load | Depends on pool scheduling and submission timing | Test sequentially on a single-thread pool, then run concurrently across multiple users. |
| `InheritableThreadLocal` still yields wrong identity | Pool threads were created before the request; inheritance is not per-task | Do not rely on thread inheritance; propagate context per task. |
| After an exception, another request “sticks” to old context | Cleanup placed after code that can throw, outside `finally` | Wrap context-binding scope in `try/finally`. |
| Memory growth or resources pinned on redeploy | ThreadLocal values retain long-lived objects on worker threads, potentially pinning classloaders | Clear all bindings; avoid storing request/response/entity graphs or large objects. |
| Clearing context in a service loses authentication | Clearing framework-managed context too early in the request | Let security filters manage lifecycle; only clear contexts you bound independently. |

Each thread's `ThreadLocalMap` holds references to values; `ThreadLocal` keys use weak references, yet values can remain until the entry is cleared or the thread dies. Never rely on GC as a cleanup mechanism for per-request data. In a multi-user application, leftover values cause **wrong identity and data leakage**, not merely memory leaks.

## 9. Choosing Storage by Required Lifecycle

| Need | Usually appropriate choice | Why |
| --- | --- | --- |
| Read principal during a synchronous Servlet request managed by Spring Security | `SecurityContextHolder` / Spring Security authorization APIs | Framework binds and cleans up security context within the proper scope. |
| Data surviving across multiple dispatches of the **same** Servlet request | `ServletRequest.setAttribute/getAttribute` | Data lifecycle is tied to the request, not pinned to a thread. |
| Passing correlation ID / user ID to an async task | Task parameter, immutable context object, or controlled context-propagation utility | Explicit at thread handoff boundaries and limits carried data. |
| Access rights, sessions, or cross-request data | Session/repository/database or standard auth mechanisms per requirements | Outlives threads/requests; provides concurrency and security controls. |
| Temporary data genuinely needed only within one processing block on one thread | `ThreadLocal` with `try/finally` and `remove()` | Suitable for thread confinement, provided scope is tightly bounded. |

`ThreadLocal` does not make objects thread-safe: if two threads reference **one mutable object** passed or shared from elsewhere, they can still race on its data. It only isolates the **per-thread variable binding**.

## 10. How to Verify When Building Web Apps

Tests should cover boundaries where threads are reused or switched:

1. Send two sequential requests for two different identities on a single-thread executor; verify the second request does not see data from the first.
2. Intentionally throw an exception mid-filter/service and verify cleanup.
3. Compare `Thread.currentThread().getName()` and correlation ID logs across synchronous controllers, Servlet async/Spring MVC `Callable`, and `CompletableFuture` tasks. Thread names aid observation, **not** as an identity guarantee.
4. With Spring Security, test authenticated, anonymous, and background tasks; verify the right principal/permissions at the execution point.
5. Inspect filter registration, dispatcher types, and async policies when redispatches or errors occur.
6. Never log tokens, credentials, or the entire `SecurityContext`; log safe, non-sensitive IDs.

An especially useful test is serializing tasks onto the **same** worker thread, as in the Java example above. It exposes missing-cleanup bugs that are easily masked when a pool happens to route requests to different threads.

## 11. Review Questions

**Q1. Why can a new request read the previous request's `ThreadLocal` value?** Because container/executor threads are reused and the old binding was never removed. `ThreadLocal` is bound to the thread, not automatically tied to the HTTP request lifecycle.

**Q2. Why should `remove()` be inside `finally`?** Because both success and exception paths must clean up bound data before the thread returns to the pool.

**Q3. Why does `InheritableThreadLocal` not fix async bugs?** Because inheritance happens when creating a new thread, not on every task submitted to an existing thread pool; mutable references can also be shared unintentionally.

**Q4. Where does Spring Security store `Authentication` on the Servlet stack by default?** Inside `SecurityContext` accessed via `SecurityContextHolder` using the thread-local strategy. Filter chains manage context scope; session/login persistence is a separate mechanism.

**Q5. If using `CompletableFuture` or `DeferredResult`, what must you do?** Identify which thread actually executes the task; pass needed data explicitly or use an executor/wrapper configured to propagate the right context and clean it up afterward. Never assume the full Servlet context automatically exists on every thread.

**Key takeaway:** `ThreadLocal` has a **thread** lifecycle; securing a request requires a **request and per-execution** lifecycle. Whenever a thread pool or thread handoff is involved, define explicitly when context is bound, propagated, and cleaned up.
