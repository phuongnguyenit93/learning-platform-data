# Propagating Context Across Executors, Callbacks, and Asynchronous Tasks

## 1. The Problem: Context Does Not Automatically Follow Tasks

In a plugin and runtime-extensible system, an invocation may begin on a request-handling thread and then flow through an executor, callback, or `CompletableFuture`. Information associated with the invocation—`requestId`, tenant, authenticated user, trace context, deadline, locale, and the plugin's class loader—is commonly referred to collectively as the **execution context**.

Java **does not automatically copy all context from the calling thread to the task-executing thread**. In particular, values stored in a `ThreadLocal` belong to the thread, not to the `Runnable` or `CompletableFuture` object. Executor pools also reuse threads across different requests. Consequently, two opposite bugs can occur:

- **Context loss:** an asynchronous task no longer has the `requestId`, security principal, or tenant it needs.
- **Context leakage:** a pooled thread retains values from a previous request, causing a subsequent request to read the wrong data, write inaccurate logs, or access the wrong tenant.

Solutions must begin by identifying **which context truly needs propagation**, who owns it, when it is captured, where it is installed, and when the previous state must be restored.

## 2. Distinguishing Different Kinds of Context

| Context | Examples | Appropriate Propagation Approach |
|---|---|---|
| Business context | `tenantId`, `requestId`, campaign code | Explicit parameter or immutable context |
| Security context | Principal, verified permissions | Framework-supported propagation mechanism; never blindly trust plugin-supplied data |
| Tracing/logging | Trace ID, span, MDC | Dedicated instrumentation/context wrapper |
| Locale/time zone | `Locale`, `ZoneId` | Explicit passing or scoped wrapper |
| Deadline/cancellation | Deadline, cancel token | Shared coordination object with explicit timeout policy |
| Thread context class loader (TCCL) | Loader seeing the plugin's resources/services | Set and restore around the task when truly required |

**Execution context is not synonymous with Java's `ThreadContextClassLoader`.** The TCCL is merely one kind of thread-associated state, primarily affecting service discovery and resource loading. Nor should a context snapshot be equated with a transaction: transactions, JDBC connections, and many request-scoped objects cannot be arbitrarily transferred to another thread.

## 3. Preferred Approach: Explicit Context Passing

An immutable value describing the information needed for the work is usually the easiest solution to test and control.

```java
record RequestContext(String requestId, String tenantId) {}

String process(RequestContext context, String payload) {
    return context.tenantId() + ":" + payload;
}
```

When submitting a task to an executor:

```java
// Integration snippet; assumes executor, context, and payload are already created.
CompletableFuture<String> future =
    CompletableFuture.supplyAsync(
        () -> process(context, payload),
        executor
    );
```

The lambda captures a reference to `context`; the needed data remains available when the task runs on another thread. To minimize races, `context` should be immutable and its fields should also be immutable. If the context holds a `Map`, `List`, or mutable object, a `record` **does not automatically make those objects immutable**. You can use `Map.copyOf` or defensive copying.

Benefits of explicit passing: the API contract makes dependencies visible; minimal reliance on threads; easy to use across queues, process boundaries, tests, and structured tasks. The downside is threading context through multiple calls, which is why some frameworks use scoped context propagation mechanisms to reduce boilerplate.

**Do not pass all request data.** Carry only the information truly required, follow data-minimization policies, and never copy credentials/tokens to unauthorized plugins.

## 4. ThreadLocal: Convenient, Yet Scoped to a Thread

`ThreadLocal<T>` stores a separate value per thread:

```java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();
```

When setting `REQUEST_ID.set("req-123")` on thread A, a task running on thread B normally receives `null`, unless B already has a value of its own. With a pooled thread being reused, B could even carry an old value if prior code failed to call `remove()`.

**Core rule:** if you set a `ThreadLocal` inside a task scope, use `try/finally` to restore or clear the value. This applies even when a callback throws an exception.

```java
String previous = REQUEST_ID.get();
try {
    REQUEST_ID.set(currentRequestId);
    performWork();
} finally {
    if (previous == null) {
        REQUEST_ID.remove();
    } else {
        REQUEST_ID.set(previous);
    }
}
```

Why restore the previous value instead of always calling `remove()`? A thread might be executing nested scopes; an inner wrapper needs to return the outer caller's context. If the contract guarantees the thread belongs exclusively to the task with no nesting, `remove()` is still essential at completion.

### InheritableThreadLocal Does Not Solve Executor Pools

`InheritableThreadLocal` can copy initial values to a **child thread at thread creation time**. With a thread pool, threads may have already been created beforehand and reused; thus it **does not propagate context per task**. Copying context at thread creation time can also inadvertently expose request data. Do not use `InheritableThreadLocal` as a general solution for asynchronous propagation.

## 5. Runnable Java 17+ Example: Capturing and Restoring Context

The example below reproduces losing a `ThreadLocal` when switching to an executor, then uses a wrapper to propagate `requestId` more safely. The program uses a single worker thread so the output is deterministic.

Create **`ContextPropagationDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ContextPropagationDemo {
    private static final ThreadLocal<String> REQUEST_ID =
            new ThreadLocal<>();

    static Runnable wrap(Runnable task) {
        // Capture on the submitting thread, before the executor runs it.
        String captured = REQUEST_ID.get();

        return () -> {
            String previous = REQUEST_ID.get();
            try {
                if (captured == null) {
                    REQUEST_ID.remove();
                } else {
                    REQUEST_ID.set(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    REQUEST_ID.remove();
                } else {
                    REQUEST_ID.set(previous);
                }
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            REQUEST_ID.set("req-42");

            Future<?> plain = executor.submit(() ->
                    System.out.println("plain: " + REQUEST_ID.get()));
            plain.get();

            Future<?> wrapped = executor.submit(wrap(() ->
                    System.out.println("wrapped: " + REQUEST_ID.get())));
            wrapped.get();

            Future<?> after = executor.submit(() ->
                    System.out.println("after: " + REQUEST_ID.get()));
            after.get();
        } finally {
            REQUEST_ID.remove();
            executor.shutdown();
        }
    }
}
```

Run:

```bash
javac ContextPropagationDemo.java
java ContextPropagationDemo
```

Output:

```text
plain: null
wrapped: req-42
after: null
```

Here `wrap` takes a snapshot of `REQUEST_ID` **when submitting the task**. Before invoking `task.run()`, the wrapper temporarily attaches the context on the worker; in `finally`, it restores the worker's prior state. Because the executor uses a single thread and `Future.get()` waits sequentially, the example shows that the subsequent task does not receive `req-42` again.

The example only propagates a single string. In practice, encapsulate a structured context and limit the data to copy. If additionally using MDC, security context, or TCCL, build wrappers with explicit policies for each type and restore all of them in `finally`.

## 6. With Callable, Future, and CompletableFuture

A `Runnable` wrapper does not automatically cover `Callable<T>` or every callback in an asynchronous pipeline.

Example wrapper for `Callable<T>`:

```java
// Integration snippet; REQUEST_ID is an already-defined ThreadLocal<String>.
static <T> java.util.concurrent.Callable<T> wrapCallable(
        java.util.concurrent.Callable<T> action) {
    String captured = REQUEST_ID.get();
    return () -> {
        String previous = REQUEST_ID.get();
        try {
            if (captured == null) REQUEST_ID.remove();
            else REQUEST_ID.set(captured);
            return action.call();
        } finally {
            if (previous == null) REQUEST_ID.remove();
            else REQUEST_ID.set(previous);
        }
    };
}
```

With `CompletableFuture`, pay attention to **where the callback actually runs**:

- `thenApply`, `thenAccept`, and `whenComplete` without the `Async` suffix may run on the thread that completes the preceding stage, or on the thread registering the callback if the stage is already complete. Never assume they run on the request thread.
- `thenApplyAsync` and `Async` variants use the specified executor; if unspecified, default behavior typically uses `ForkJoinPool.commonPool()` per `CompletableFuture` rules. Never rely on threads in that pool having the request context.
- A callback may be created in context A's scope and then execute when the stage completes from a thread in context B. Therefore, decide to **capture at callback registration time**, rather than arbitrarily reading whatever `ThreadLocal` happens to be present when the callback runs.

Explicit propagation example:

```java
// Integration snippet; context is an immutable RequestContext.
CompletableFuture<String> result =
    CompletableFuture.supplyAsync(() -> fetchData(context), executor)
        .thenApplyAsync(data -> transform(context, data), executor)
        .thenApply(data -> format(context, data));
```

Each lambda uses the same `context` via closure. This is usually clearer than relying on thread-locals across multiple stages.

If you must use `ThreadLocal`, wrap **each entry point/callback** requiring context; wrapping only `Executor.execute` is insufficient if callbacks are not submitted through that executor. A `ContextAwareExecutor` can capture during `execute(command)` and forward the wrapped task to a delegate, but verify whether non-`Async` callbacks actually pass through that wrapper.

## 7. Plugin-Registered Callbacks: Capture and Ownership

When the host lets plugins register callbacks:

```java
eventBus.subscribe("order-created", event -> handle(event));
```

The callback may execute long after registration, on an event bus thread. You should not capture the entire context of the **registration request** and reuse it forever for every event. Distinguish two kinds:

1. **Plugin/subscription context:** plugin identifier, version, granted capabilities, and lifecycle information. Can be bound to the long-lived subscription.
2. **Per-event/request context:** correlation ID, tenant, tracing span, and deadline. Must travel with the specific event or be created at dispatch time.

A controllable design represents the event as an envelope:

```java
// Structural illustration snippet, excluding EventBus.
record EventEnvelope<T>(
    String eventId,
    String tenantId,
    String correlationId,
    T payload
) {}
```

The dispatcher passes `EventEnvelope` into the callback. Before execution, the host can attach the corresponding context to logging/tracing frameworks with scoped lifecycle, then restore state afterward. Do not accept a `tenantId` or principal from an untrusted plugin as authorization without checking against the host's security policy.

For unregistered callbacks, ensure listeners, queues, and context snapshots do not retain references to old plugins/class loaders that prevent hot unload from completing.

## 8. Thread Context Class Loader in a Plugin System

`Thread.currentThread().getContextClassLoader()` (TCCL) is a different mechanism from application-defined `ThreadLocal`s. Some service discovery APIs or libraries use the TCCL to locate classes/resources.

In a plugin system with multiple class loaders, callbacks running on a host thread pool may carry the host's TCCL rather than the plugin's loader. When code genuinely needs to run with the plugin's TCCL, the host can set the TCCL temporarily and **always restore it**:

```java
// Integration snippet; pluginLoader and task are defined by the host.
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    task.run();
} finally {
    thread.setContextClassLoader(previous);
}
```

Do not set the plugin TCCL once on a thread pool and leave it there permanently: doing so causes tasks from other plugins to use the wrong loader and can keep the plugin loader alive after deactivation. Nor should the TCCL be treated as a sandbox measure; a separate class loader does not create a trustworthy security boundary for untrusted code.

When using `ServiceLoader.load(ServiceType.class)`, the TCCL can influence which loader is chosen. If the host needs precise control, consider the overload accepting a `ClassLoader` or the corresponding module-layer API, and ensure shared APIs are defined by a stable loader.

## 9. Integrating Logging, Tracing, and Security Context

In real frameworks, do not arbitrarily copy internal state yourself. Leverage supported APIs:

**MDC (Mapped Diagnostic Context).** Many logging frameworks attach log metadata to thread-locals. When submitting a task to an executor, MDC usually does not propagate automatically. If a wrapper copies MDC, take a snapshot at submit time, install the snapshot when running, and restore the previous snapshot in `finally`. Be careful with keys containing personal data and do not let MDC persist across requests.

**Distributed tracing.** Tracing context includes more than a trace ID: span hierarchy, baggage, and scoping rules. Use the tracing solution's context propagation API/instrumentation (e.g., OpenTelemetry) rather than inventing span IDs by copying a string. Baggage should be filtered when crossing trust boundaries.

**Security context.** With Spring Security or similar frameworks, use built-in executor/decorator mechanisms designed to propagate and clear security context. Authentication, permissions, and expiration must still be checked at the execution site. Copying a principal across threads does not automatically grant permissions to a plugin. Do not share high-privilege credentials with untrusted code merely for convenience of context propagation.

**Request-scoped resources.** JDBC transactions, servlet requests/responses, entity managers, and request-lifecycle objects are generally unsafe to retain and replay on another thread. Pass only minimal data or open a fresh scope per framework rules at the execution site.

## 10. Timeouts, Cancellation, and Asynchronous Context

A deadline is contextual information that can be passed as an immutable value, such as an `Instant` or timeout budget. Yet propagating a deadline **does not automatically stop** a running task. The task must support checking the deadline or the corresponding cancellation mechanism.

With `Future.cancel(true)`, Java only requests interrupting the thread if the task is running; it does not guarantee the task stops immediately. With `CompletableFuture.cancel(...)`, completion cancellation does not necessarily interrupt the underlying computation. Therefore, a context wrapper cannot replace rules for task, resource, timeout, and rollback management.

Good patterns include:

- Capture deadline/correlation context before dispatch.
- Check the deadline at key steps and before executing side effects.
- Propagate cancellation signals to stages and dependencies that support them.
- Restore `ThreadLocal`, MDC, and TCCL even on timeout, exception, or interrupt.
- Close resources and avoid retaining context snapshots longer than the work's lifecycle.

## 11. Common Mistakes

1. **Relying on ThreadLocal across an executor:** `ThreadLocal.set` on the caller thread does not guarantee the worker sees the value.
2. **Not cleaning up ThreadLocal:** thread pool reuse causes previous request data to leak into subsequent requests.
3. **Using InheritableThreadLocal in a pool:** inheritance happens at thread creation time, not at task submission time.
4. **Capturing too early:** a long-lived registered callback retains the `tenantId` of the initial request.
5. **Capturing too late:** reading context from the thread running the callback instead of the proper event/request context.
6. **Not distinguishing Async and non-Async callbacks:** non-Async callbacks can run on whichever thread completes the stage.
7. **Passing shared mutable context:** multiple tasks mutating the same map leads to races or data corruption.
8. **Failing to restore TCCL/MDC:** subsequent plugin tasks get the wrong loader or wrong trace.
9. **Carrying transactions/request objects across threads:** breaks resource lifetimes and thread affinity.
10. **Letting untrusted plugins dictate security context:** propagated context data is mistaken for authorization proof.
11. **Ignoring lifecycle:** live tasks and callbacks retain replaced class loaders/plugins.
12. **Treating propagation as cancellation:** having a deadline does not mean the task will stop on its own.

## 12. Design Checklist

Before putting a task/callback into a runtime-extensible system, answer clearly:

- **What needs propagation?** `requestId`, tenant, trace, locale, deadline, security principal, or TCCL; strip all unnecessary fields.
- **Where is the source of truth?** Validated context from the host or self-declared values from a plugin?
- **When to capture?** At submission, callback registration, or per-event dispatch?
- **Where to install and clean up?** Every new thread entry point and callback that genuinely needs the scope?
- **How about ordering and errors?** On exception, timeout, or cancel, is the previous state always restored?
- **Is mutable state shared?** Are immutable snapshots, ownership, and synchronization clear?
- **What happens when a plugin is removed?** Are in-flight tasks, listeners, loaders, and resources drained/closed properly?
- **Have thread-hopping paths been tested?** Test normal tasks, failing tasks, interleaved requests, immediately completing callbacks, hot reload, and cleanup.

**Remember:** context must be tied to the **work to be done** and trust boundaries, not bound by default to a thread. Prefer **explicit passing via immutable context**; when using `ThreadLocal`, MDC, security context, or TCCL, **capture at the right time → install within scope → restore in `finally`**.