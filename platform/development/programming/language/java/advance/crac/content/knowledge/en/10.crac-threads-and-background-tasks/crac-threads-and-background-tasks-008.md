# ThreadLocal and Data Tied to Finished Requests

In Java applications, ThreadLocal allows each thread to hold its own value without passing that value through every method call. This approach is commonly used to store contextual information such as request ID, current user, tenant, locale, transaction context, or data for logging.

The problem arises when threads are reused. In a web server or executor, a worker thread typically handles many requests or tasks over the lifetime of the process. When a request finishes, the thread remains alive to handle the next request. If ThreadLocal data is not cleared, a subsequent request can see data from the previous request. Stale data can also hold references to large objects, credentials, EntityManager, or expired resources.

With CRaC (Coordinated Restore at Checkpoint), thread state and objects attached to threads can be part of the checkpointed process state. If the process is checkpointed while a worker still holds data from a finished request without cleanup, stale state can persist after restore. Therefore, ThreadLocal must be managed right at request or task completion boundaries, while ensuring the application has drained work and reached a stable state before checkpointing.

## 1. How Does ThreadLocal Work?

ThreadLocal<T> is a Java API that lets each thread have an independent value associated with the same ThreadLocal object. When thread A calls get(), it receives the value belonging to thread A; when thread B calls get() on the same ThreadLocal, it receives thread B's own value.

Example:

```java
private static final ThreadLocal<String> CURRENT_USER =
        new ThreadLocal<>();

void handleRequest(String user) {
    CURRENT_USER.set(user);
    try {
        process();
    } finally {
        CURRENT_USER.remove();
    }
}

void process() {
    String user = CURRENT_USER.get();
    System.out.println("Current user: " + user);
}
```

Each thread can hold a different value:

```text
ThreadLocal object
       |
       +---- Thread A: "alice"
       |
       +---- Thread B: "bob"
       |
       +---- Thread C: "carol"
```

ThreadLocal does not create a new thread and does not automatically propagate data between threads. It only provides a way to access state attached to the currently executing thread.

Basic methods:

| Method | Meaning |
|---|---|
| set(value) | Sets the value for the current thread |
| get() | Retrieves the current thread's value; may invoke initialValue or Supplier if absent |
| remove() | Removes the current thread's value from the ThreadLocal |
| withInitial(supplier) | Creates a ThreadLocal with a default value initializer function |

A ThreadLocal object is usually declared static final so components across the same application access the same ThreadLocal key. However, that does not make the value shared data: each thread still has its own entry.

## 2. Where Are ThreadLocal Values Stored?

In OpenJDK's implementation, each Thread object has its own ThreadLocalMap to store entries for the ThreadLocals used by that thread. Each entry associates a ThreadLocal key with its corresponding value.

You can visualize it as:

```text
Thread A
  ThreadLocalMap
    key: CURRENT_USER  -> value: "alice"
    key: REQUEST_ID    -> value: "req-101"

Thread B
  ThreadLocalMap
    key: CURRENT_USER  -> value: "bob"
    key: REQUEST_ID    -> value: "req-102"
```

This describes the common OpenJDK implementation; applications should rely on the ThreadLocal API contract rather than depending on internal ThreadLocalMap structure.

An important point is that the value is attached to the thread, not to a specific request. If the thread stays alive after the request finishes, the value can remain until replaced or removed via remove(). ThreadLocal has no concept of when a request starts or ends.

Therefore, calling set() does not mean the value will automatically expire when the request-handling method returns. The application must proactively define cleanup boundaries.

## 3. Why Do Thread Pools Expose ThreadLocal Bugs?

If an application creates a new thread for every request and that thread exits immediately afterward, ThreadLocal values are no longer held by that thread once it ends. Yet modern servers use thread pools to avoid the cost of continually creating and destroying threads.

A worker thread can process multiple requests sequentially:

```text
Worker-1
   |
   +--> Request A: set user = "alice"
   |       |
   |       +--> request ends
   |
   +--> Request B: get user
   |       |
   |       +--> if not removed: may see "alice"
   |
   +--> Request C
           |
           +--> worker is still the same thread
```

Suppose a filter puts user information into a ThreadLocal when a request begins yet fails to remove it when the request ends. When the worker thread is reused, the next request may read the stale data. This is a *context leakage* bug.

Buggy example:

```java
private static final ThreadLocal<String> CURRENT_TENANT =
        new ThreadLocal<>();

void handle(String tenant, Runnable action) {
    CURRENT_TENANT.set(tenant);
    action.run();

    // Bug: fails to remove the value after the request completes.
}
```

If tenant A is processed before tenant B on the same worker and code path B does not overwrite the value due to a special branch, B can see tenant A. Similarly, if a request fails before updating ThreadLocal, the leftover value from the previous request may be used.

Minimal fix:

```java
void handle(String tenant, Runnable action) {
    CURRENT_TENANT.set(tenant);
    try {
        action.run();
    } finally {
        CURRENT_TENANT.remove();
    }
}
```

finally ensures cleanup runs both when action returns normally and when it throws an exception.

## 4. What Data Is Commonly Placed in ThreadLocal?

ThreadLocal is commonly used for data meaningful only within a single synchronous execution flow:

- Request ID or correlation ID for correlating logs.
- Security principal or authentication info of the current user.
- Tenant ID in a multi-tenant application.
- Locale, timezone, or per-request formatting configuration.
- Context for tracing and metrics.
- Transaction context or EntityManager proxy managed by a framework.
- Temporary data serving processing within a single unit of work.

Not all of the data above should be stored manually in ThreadLocal by the application. Frameworks may already provide their own context management mechanisms. For example, Spring Security, transaction managers, logging frameworks, and tracing libraries may provide APIs to set, get, and clear context. Prefer using the framework's API instead of creating a parallel ThreadLocal holding the same data.

Sensitive data must also be considered. Principals, tokens, session objects, or tenant information can affect access permissions. If data leaks into another request, the bug can become a security vulnerability rather than just a log display error.

## 5. remove() Matters More Than Just set(null)

The following two approaches are not completely equivalent:

```java
CURRENT_USER.set(null);
```

and:

```java
CURRENT_USER.remove();
```

set(null) sets the current value to null, yet the ThreadLocal entry may still remain in ThreadLocalMap. remove() deletes the entry for the current thread.

For post-request cleanup purposes, call remove():

```java
try {
    CURRENT_USER.set(user);
    process();
} finally {
    CURRENT_USER.remove();
}
```

remove() only affects the calling thread. Calling remove() from a management thread or checkpoint thread cannot remove values in the ThreadLocalMaps of other worker threads. This is why cleanup must happen on the very thread owning the context, typically in a filter/interceptor or task wrapper.

If you need nested temporary values, you can save the previous value and restore it rather than always calling remove():

```java
String previous = CURRENT_USER.get();
CURRENT_USER.set(user);
try {
    process();
} finally {
    if (previous == null) {
        CURRENT_USER.remove();
    } else {
        CURRENT_USER.set(previous);
    }
}
```

This pattern is useful when a function runs inside an existing context and needs to temporarily alter the context. However, clearly define nesting rules and how to distinguish "no value" from "null value" if null is a valid state in the application.

## 6. Cleanup at Request Boundaries

In a web application, the request boundary is the right place to set and clear request context. A filter or interceptor can:

1. Read the request ID, user, or tenant from an authenticated request.
2. Put the required values into the context.
3. Allow the rest of the pipeline to process.
4. In finally, clear the entire context owned by the filter.

Example simple servlet filter:

```java
public final class RequestContextFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest http = (HttpServletRequest) request;
        String requestId = resolveRequestId(http);

        RequestContext.setRequestId(requestId);
        try {
            chain.doFilter(request, response);
        } finally {
            RequestContext.clear();
        }
    }

    private String resolveRequestId(HttpServletRequest request) {
        String value = request.getHeader("X-Request-ID");
        return value == null || value.isBlank()
                ? UUID.randomUUID().toString()
                : value;
    }
}
```

The RequestContext class should clear every ThreadLocal it owns:

```java
public final class RequestContext {
    private static final ThreadLocal<String> REQUEST_ID =
            new ThreadLocal<>();
    private static final ThreadLocal<String> TENANT_ID =
            new ThreadLocal<>();

    private RequestContext() {}

    public static void setRequestId(String value) {
        REQUEST_ID.set(value);
    }

    public static String requestId() {
        return REQUEST_ID.get();
    }

    public static void setTenantId(String value) {
        TENANT_ID.set(value);
    }

    public static String tenantId() {
        return TENANT_ID.get();
    }

    public static void clear() {
        REQUEST_ID.remove();
        TENANT_ID.remove();
    }
}
```

In a real application, the filter must be placed at the right position in the security chain. Do not extract tenant or user from an unauthenticated header and use it directly to make access control decisions. Request context should contain only verified data from trusted sources.

If using Spring MVC, cleanup can be implemented in a Filter, HandlerInterceptor, or context mechanism provided by Spring. Choose a place that covers normal execution, exceptions, and early returns. Ensure cleanup occurs after synchronous processing finishes.

## 7. ThreadLocal and Logging Context (MDC)

Logging frameworks often provide a Mapped Diagnostic Context (MDC) to attach request ID, user ID, or correlation ID to logs without passing parameters through every call.

Example with SLF4J MDC:

```java
try {
    MDC.put("requestId", requestId);
    MDC.put("tenantId", tenantId);

    service.handle();
} finally {
    MDC.clear();
}
```

MDC implementations typically use thread-bound state or an equivalent context mechanism, so cleanup is still needed when workers are reused. Specific APIs may vary across logging providers; read the documentation of the active provider.

Do not blindly call MDC.clear() if the application has other context set by an external component that needs to be preserved. In nested cases, you can save the previous MDC context map and restore it, or use scoped/closeable APIs provided by the library.

A common bug is that the synchronous request ends and MDC is cleaned up properly, yet an async task submitted to an executor does not receive the context. Conversely, if you copy context into a task without clearing it after the task finishes, the worker can carry the old task's context to the next task.

## 8. InheritableThreadLocal Does Not Solve Context Propagation for Thread Pools

InheritableThreadLocal allows a child thread to inherit values from the parent thread at the time the child thread is created. This is an important difference compared to regular ThreadLocal.

Example:

```java
private static final InheritableThreadLocal<String> USER =
        new InheritableThreadLocal<>();

USER.set("alice");
Thread child = new Thread(() ->
        System.out.println(USER.get()));
child.start();
```

The child thread is created while the parent thread holds "alice", so it can receive the inherited value.

However, thread pools usually create workers before requests submit tasks. If a worker was already created earlier, setting InheritableThreadLocal when a request starts does not cause that worker to automatically receive the new value. If a worker is created while a context is set, it can inherit the context at creation time and retain that value longer than the original request.

Therefore, InheritableThreadLocal is not a general solution for passing context to tasks in an executor. It can cause unpredictable bugs when threads are reused or created asynchronously relative to requests.

Also note that the default value-copying behavior does not necessarily make a deep copy. If the value is a mutable object, the parent thread and child thread may reference the same object depending on how childValue() is implemented.

## 9. Passing Context Across an Executor Explicitly

ThreadLocal only returns values on the current thread. When offloading work to an executor, the task usually runs on a different thread and does not automatically see the submitting thread's ThreadLocal.

A safer approach is to capture the context at submission time, set it on the worker while the task runs, and restore or clear the context in finally.

Example simple wrapper:

```java
public final class RequestContext {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();
    private static final ThreadLocal<String> TENANT_ID = new ThreadLocal<>();

    private RequestContext() {}

    public record Snapshot(String requestId, String tenantId) {}

    public static Snapshot capture() {
        return new Snapshot(REQUEST_ID.get(), TENANT_ID.get());
    }

    public static void restore(Snapshot snapshot) {
        setOrRemove(REQUEST_ID, snapshot.requestId());
        setOrRemove(TENANT_ID, snapshot.tenantId());
    }

    public static void clear() {
        REQUEST_ID.remove();
        TENANT_ID.remove();
    }

    private static void setOrRemove(
            ThreadLocal<String> local, String value) {
        if (value == null) {
            local.remove();
        } else {
            local.set(value);
        }
    }
}

public final class ContextAwareExecutor {
    private final Executor delegate;

    public ContextAwareExecutor(Executor delegate) {
        this.delegate = delegate;
    }

    public void execute(Runnable task) {
        RequestContext.Snapshot captured = RequestContext.capture();

        delegate.execute(() -> {
            RequestContext.Snapshot previous = RequestContext.capture();

            try {
                RequestContext.restore(captured);
                task.run();
            } finally {
                RequestContext.restore(previous);
            }
        });
    }
}
```

The example uses an immutable snapshot to capture context on the submitting thread. The worker saves the old snapshot, applies the passed context, runs the task, and restores the old snapshot in finally. Here null is treated as having no value and triggers remove(). In a real system, if null is a valid value that needs to be distinguished from an unset state, the snapshot must store an additional presence flag for each field. The snippet uses record and therefore requires Java 16 or above; record can be replaced with an immutable class if the project uses an older JDK.

Principles:

- Pass only the fields genuinely needed by the task.
- Do not pass request objects, EntityManager, Session, or transaction objects to another thread unless the framework explicitly supports it.
- Context snapshots should be immutable to prevent the submitting thread and worker from mutating shared data.
- Restore the context before running the task.
- Always clean up or restore the old context in finally.
- Handle cases where a task is canceled before starting or the executor rejects submission.
- Do not retain a request's context longer than the business lifecycle of the task.

If a task continues running after the HTTP response has been returned, it is no longer part of synchronous request handling. Determine which data is allowed to live for background work and the lifetime of that data. Do not retain the entire request context merely because the task was initiated from a request.

## 10. ThreadLocal in Async, CompletableFuture, and Reactive Pipelines

With CompletableFuture, callbacks may run on a thread from another executor or the common ForkJoinPool. You cannot assume a callback will run on the thread that called supplyAsync() or thenApply().

Example:

```java
CompletableFuture.supplyAsync(() -> loadData())
    .thenApply(data -> enrich(data))
    .thenAccept(result -> save(result));
```

Stages can run on multiple different threads depending on the executor and completion state. The original request's ThreadLocal does not automatically propagate along the stage chain.

You can pass an explicit context snapshot into each stage or use a supported context propagation library/framework. With Spring, Reactor, or a tracing framework, use that platform's own context mechanism. Reactive pipelines can switch threads many times; ThreadLocal is not an appropriate place to keep reactive context across a pipeline.

In Reactor, Reactor Context is designed to attach data to the subscriber sequence rather than the physical thread. Integrating with ThreadLocal/MDC requires using supported hooks or bridges and requires attention to cleanup. Do not manually read ThreadLocal in one operator and assume every subsequent operator runs on the same thread.

## 11. ThreadLocal Holding Resources and Large Objects

ThreadLocal values are not only Strings or request IDs. Some applications store large objects or resources in ThreadLocal, for example:

- EntityManager or Hibernate Session.
- JDBC Connection.
- Request objects or security contexts.
- Large buffers or parser state.
- Formatters, serializers, or object caches.
- Native handles or wrappers to OS resources.

Without remove(), long-lived worker threads can hold onto those objects longer than expected. This can cause memory retention or resource leaks.

Some ThreadLocalMap implementations use weak references for the ThreadLocal key, yet the value remains strongly referenced by the entry until stale entries are cleaned up. If the ThreadLocal key is no longer referenced while the worker thread stays alive, the value can still be retained temporarily. Stale entry cleanup is an implementation detail; do not rely on it in place of intentional remove().

If a ThreadLocal holds a JDBC Connection or EntityManager, clearing the reference does not replace closing the resource properly. Call close/cleanup via the owner first, then remove the ThreadLocal. Do not leave the connection pool or transaction manager unable to manage the resource simply because the reference was removed from the context.

## 12. ThreadLocal and CRaC Checkpoints

Checkpointing saves process state, including thread state and memory per the mechanisms supported by the CRaC JDK and platform. ThreadLocal is bound to threads and must therefore be considered part of the runtime state that may exist at checkpoint time.

Suppose a worker processed request A:

```text
Worker-7
  CURRENT_USER = "alice"
  TENANT_ID = "tenant-blue"
  REQUEST_ID = "req-A"
```

Request A finishes yet cleanup was forgotten. Worker-7 returns to the pool waiting for a new task. If checkpointing occurs now, request A's data may be saved along with thread state. After restore, the worker may continue existing with the old context depending on restored state. A new request could mistakenly read the old user, tenant, or request ID.

This creates three risk groups:

1. **Cross-request data leakage:** new requests see old requests' context.
2. **Incorrect security scope:** an old tenant or principal can affect data access decisions.
3. **Resource or memory retention:** ThreadLocal can retain EntityManager, connections, request objects, or buffers that are no longer needed.

CRaC does not automatically know which request a ThreadLocal value belongs to or whether that request has finished. Frameworks also cannot automatically clean up every ThreadLocal created manually by applications and libraries without corresponding integration.

The primary measure is cleaning up properly at request/task boundaries from the start. Before checkpoint, stop accepting new work and drain in-flight requests/tasks so all finally blocks and cleanup hooks execute. After restore, reopen ingress only once thread pools and context components are in a valid state.

## 13. You Cannot Clear Every Thread's ThreadLocal with One remove() Call

ThreadLocal.remove() only deletes the entry on the current thread. If the checkpoint coordinator runs on a dedicated thread, calling CURRENT_USER.remove() on the coordinator does not delete values on worker-1, worker-2, or worker-3.

Do not attempt to use reflection to access Thread.threadLocals or modify internal ThreadLocalMaps. This approach is implementation-dependent, can be blocked by module encapsulation, and risks corrupting library state.

Instead:

- Clean up in a filter/interceptor on the request-handling thread.
- Wrap tasks in executors to set and clear context on the worker thread.
- Stop ingress and wait for workers to finish tasks.
- Use cleanup APIs of the framework or library owning the context.
- For application-managed ThreadLocals, keep a centralized clear() API so all code paths follow the same rule.
- Use CRaC callbacks only for lifecycle parts that the owner can control and verify.

If a background thread lives continuously and holds context for a lifecycle longer than a single task, design a dedicated lifecycle for that thread. Do not arbitrarily delete data that libraries need to operate; clearly distinguish which values are temporary task context and which are valid long-lived state.

## 14. Using a CRaC Resource to Coordinate Workers and Context

A CRaC Resource has two main callbacks: beforeCheckpoint(...) and afterRestore(...). For ThreadLocal, callbacks should not try to scan and clear every thread's ThreadLocals. A more appropriate role is coordinating ingress, task lifecycles, and worker pools.

The example below illustrates a simple coordinator. The methods RequestGate and WorkerLifecycle are hypothetical application-built APIs, not standard CRaC APIs.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class WorkerCheckpointResource implements Resource {
    private final RequestGate requestGate;
    private final WorkerLifecycle workers;

    public WorkerCheckpointResource(
            RequestGate requestGate,
            WorkerLifecycle workers) {
        this.requestGate = requestGate;
        this.workers = workers;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        requestGate.stopAcceptingNewWork();
        requestGate.awaitInFlightWorkToFinish();
        workers.awaitTasksToDrain();
        workers.verifyTaskContextCleanup();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        workers.restoreOrRestartIfRequired();
        workers.verifyReady();
        requestGate.allowNewWork();
    }

    public interface RequestGate {
        void stopAcceptingNewWork() throws Exception;
        void awaitInFlightWorkToFinish() throws Exception;
        void allowNewWork() throws Exception;
    }

    public interface WorkerLifecycle {
        void awaitTasksToDrain() throws Exception;
        void verifyTaskContextCleanup() throws Exception;
        void restoreOrRestartIfRequired() throws Exception;
        void verifyReady() throws Exception;
    }
}
```

In a real application, clearly identify who owns executors and thread pools. Some frameworks manage thread pools under their own lifecycles; do not manually shut down container-managed executors without guidance. Some executors can continue being used after restore; some executors or environment-dependent threads need reinitialization. Use supported integrations and test against the target CRaC JDK.

The verifyTaskContextCleanup() method should rely on an observability mechanism controlled by the application, such as a task wrapper recording that context was cleared or a metric of active tasks. Do not rely on reflection to read all internal JVM ThreadLocals.

## 15. Distinguishing Request Context from Background Thread Context

A background thread may need some long-lived information, yet that does not mean it should retain the entire request context that spawned it.

For example, a worker dedicated to sending emails may need SMTP configuration and service account info throughout its lifetime. These values are worker or application configuration. Meanwhile, a specific request's request ID, user principal, and tenant ID should only exist within the scope of work explicitly passed to it.

Classify them:

| Data | Appropriate scope | Cleanup or refresh |
|---|---|---|
| Request ID | One request or task spawned from a request | Remove when task finishes |
| User principal | One authenticated unit of work | Remove when task finishes; pass only when justified |
| Tenant ID | One tenant-scoped request/job | Remove after task; verify permissions before use |
| Locale | One request or job needing formatting | Remove after task |
| Service configuration | Application/worker lifecycle | Refresh via configuration mechanism |
| Database transaction context | One transaction | End or roll back with transaction |
| EntityManager/Session | One persistence context | Close when unit of work finishes |
| Metrics registry | Application lifecycle | Not request context |
| Worker-local cache | Worker lifecycle, with clear policy | Invalidate or recreate on demand |

Do not place the entire RequestContext onto a background thread and keep it indefinitely. Snapshot only the genuinely needed fields and define the snapshot's lifetime.

## 16. Virtual Threads and ThreadLocal

Virtual threads change how Java organizes concurrency: many virtual threads can be scheduled onto a small number of carrier threads. ThreadLocal remains bound to virtual threads under the API model, yet memory cost and characteristics can differ from platform threads.

An application using virtual threads should not assume ThreadLocal is free. If many virtual threads are created and each holds large objects, total memory still grows. Resources like JDBC Connections or EntityManagers should also not be kept in ThreadLocal simply because virtual threads can run many concurrent tasks.

Some modern frameworks and APIs provide alternative context mechanisms, such as ScopedValue in supporting JDK versions. ScopedValue targets data bound to an execution scope and cannot be mutated arbitrarily after binding, though availability and feature status depend on the Java version. Check the target JDK before choosing.

Whether using platform threads or virtual threads, the principle remains defining context scope, preventing stale request data from living outside that scope, and avoiding carrying non-thread-safe resources across tasks.

## 17. Common Mistakes

**Setting ThreadLocal yet forgetting remove().** Worker threads are reused so old values can bleed into new requests. Put cleanup in finally at request/task boundaries.

**Calling only set(null).** The entry may still exist. Use remove() when the goal is removing the value from the current thread.

**Calling remove() on the coordinator thread.** The operation affects only the calling thread. Cleanup must run on the thread owning the context.

**Using InheritableThreadLocal for thread pools.** Values are inherited at thread creation, not on every task submission. Reused workers can retain stale context.

**Expecting ThreadLocal to propagate automatically across CompletableFuture.** Callbacks can run on different threads. Pass context explicitly or use supported context propagation.

**Storing EntityManager, Session, or Connection in ThreadLocal without lifecycle management.** Removing the reference does not close the resource. End the transaction and close the resource via the proper owner.

**Clearing context too early.** If cleanup happens before logging, tracing, or final processing completes, logs can lose correlation IDs. Place cleanup at the appropriate end of the pipeline.

**Cleaning up only on the happy path.** Exceptions, timeouts, cancellation, and early returns can all skip cleanup if finally or equivalent hooks are not used.

**Using a mutable ThreadLocal across multiple async requests.** Tasks can mutate the shared context object or read stale data. Use immutable snapshots and clear scopes.

**Checkpointing while tasks are still running.** finally has not executed yet and context may still be attached to workers. Quiesce and drain tasks before checkpoint.

**Trying to clear all ThreadLocals via reflection.** This is implementation-dependent and can break frameworks. Clean up at owners and lifecycle boundaries.

## 18. Procedure for Testing ThreadLocal with CRaC

Tests must prove that context from a finished request does not appear in the next request, even after checkpoint/restore.

### Testing Reuse of the Same Worker

1. Use an executor with only one worker thread.
2. Submit task A, setting request ID and tenant ID.
3. Finish task A and run cleanup.
4. Submit task B on the same executor.
5. Verify task B cannot read task A's request ID or tenant ID.
6. Repeat when task A throws an exception, is canceled, or times out.

Using a single worker guarantees both tasks run on the same thread, clearly reproducing stale ThreadLocal bugs.

### Testing Missing Cleanup

In a dedicated test environment, intentionally omit remove() in task A. Run task B on the same worker and verify the test detects stale context. Do not ship this intentional bug to production.

### Testing Context Propagation

Submit an async task from a request that has context. Verify only the selected fields are propagated to the worker, and after the task completes, the worker does not retain that context for the next task.

### Testing Checkpoint/Restore

1. Launch the application with a compatible CRaC JDK.
2. Send a request and verify cleanup occurred once the request ended.
3. Quiesce ingress and drain the executor.
4. Create a checkpoint in a state where no request tasks are active.
5. Restore the process.
6. Send a new request on the restored worker or a new worker.
7. Verify the new request does not see old context and logs/tracing carry the right request ID.
8. Also test scenarios where callbacks or task draining fail; the application must not report ready while worker state is unsafe.

Metrics to monitor:

- Number of running tasks and pending tasks.
- Number of times context cleanup was invoked.
- Number of times tasks ended with exceptions or cancellation.
- Number of stale context detections in tests.
- Executor drain duration before checkpoint.
- Number of worker or context propagation errors after restore.
- Request ID/tenant ID in per-request logs, subject to data protection policy.

Do not write tokens or sensitive data to logs solely to verify cleanup. Use dummy identifiers in tests and log only context presence/absence or a safe test ID.

## 19. ThreadLocal Management Checklist

- [ ] Does every ThreadLocal have a clear purpose and owner?
- [ ] Have you separated which data is request context and which is worker/application state?
- [ ] Does every request/task that sets context have cleanup in finally?
- [ ] Does cleanup use remove() or restore the previous context properly per nesting?
- [ ] Does cleanup run on the very thread owning the ThreadLocal?
- [ ] Does the thread pool have a wrapper to propagate and clear context between tasks?
- [ ] Is InheritableThreadLocal being misused as a context propagation mechanism for executors?
- [ ] Do CompletableFuture/reactive tasks have explicit context propagation?
- [ ] Does any ThreadLocal hold EntityManager, Session, Connection, or large objects?
- [ ] Are resources closed by the proper owner before removing the reference?
- [ ] Are request ingress and worker tasks drained before checkpoint?
- [ ] Are you avoiding using reflection to scan internal thread ThreadLocalMaps?
- [ ] After restore, are workers and context propagation verified before readiness?
- [ ] Tested subsequent requests on the same worker after both success and exception?

## Conclusion

ThreadLocal binds values to threads, not to request lifecycles. In applications using thread pools, a worker thread can handle many consecutive requests so stale data will persist if the application does not clean up. remove() only affects the current thread; therefore cleanup must run on the worker itself at request or task completion boundaries.

With CRaC, thread state and thread-bound data must be accounted for in checkpoint planning. Applications should stop accepting new work, drain running requests and tasks, ensure finally blocks and cleanup hooks have completed, and only then checkpoint. After restore, reopen ingress only once workers and context propagation mechanisms are ready. Using well-scoped ThreadLocal, intentional cleanup, and explicit context propagation across async boundaries prevents cross-request data leakage, reduces resource retention, and preserves correctness after restore.