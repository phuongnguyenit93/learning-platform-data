# Request-Scoped Context and Task Lifecycle Boundaries in Java

> **Scope:** Java SE 21 and general Java concurrency. "Request" refers to a logical unit of processing (a network request, CLI command, message, or job execution pass). The examples do not rely on Spring or any specific framework.

## 1. What is a request context?

A **request context** is the set of information that travels with a logical unit of work: `requestId` (for log/tracing correlation), `actorId` (the initiator), `tenantId`, locale, deadline, verified authorization details, etc. A request typically passes through multiple methods and may split into multiple concurrent tasks.

~~~text
Request R-42
  │
  ├── Task A: call data service ───── worker/thread 1
  │
  └── Task B: compute secondary result ── worker/thread 2
                  │
            combine results A and B
                  │
           end request R-42
~~~

**A request is not synonymous with a thread; a task is not synonymous with a thread either.** A thread is an execution resource, a task is a unit of work submitted for scheduling, and a request is a business/logical relationship containing one or more tasks. A worker in a thread pool can sequentially run tasks from many different requests. The same request can execute across multiple threads.

There are two independent yet related questions:

- **Propagation:** Which tasks or callbacks receive the context data from the request-handling step, and through what mechanism?
- **Lifetime/ownership:** Who owns creating, awaiting, finishing, canceling, and cleaning up tasks; when a request becomes invalid or expires, what are child tasks still allowed to do?

Propagation bugs can cause a task to lose its `requestId` or mistakenly see the `actorId` from a previous request. Lifetime bugs can cause a task to keep operating on closed resources or write data after the request has timed out.

## 2. Distinguishing lifecycle scopes

| Scope | From where to where? | Example |
|---|---|---|
| **Request** | Receipt → success, error, timeout, or cancellation per application rules | R-42 starts, spawns A/B, aggregates, returns result |
| **Task** | Created/submitted for execution → completion, error, or actual termination after a cancellation signal | `Callable` passed to `ExecutorService.submit` |
| **Thread** | Thread created → terminated | Fixed worker of `newSingleThreadExecutor` |
| **Context binding** | Context attached → binding detached/restored | `ThreadLocal.set/remove`; dynamic binding of `ScopedValue` |

Worker reuse example:

~~~text
Time ───────────────────────────────────────────────────────────────▶
Request R1:  [receive ─ submit task T1 ───── done]
Task T1:                       [run ─ finish]
Worker W:    idle ─────────────[ T1 ]── idle ────[ T2 ]── idle
Request R2:                                  [receive ─ T2 ─ finish]

If T1 leaves ThreadLocal = R1 without calling remove:
Worker W:                      [R1]──────────────[T2 sees R1: WRONG]
~~~

A thread pool does not automatically clear context for each task. Similarly, `Future.get()` lets the caller wait for a task, but it does not define cleanup, timeout, side-effect, or propagation rules on its own.

## 3. Designing a safely shareable request context

A good approach is to use an **immutable snapshot** that carries only the fields a task actually needs:

~~~java
// Illustrates a Java 21 data type, not a standalone program.
record RequestContext(
        String requestId,
        String actorId,
        String tenantId
) {}
~~~

A `record` creates `final` fields, but **does not perform a deep copy**: if a component is a mutable `Map`/`List`, threads holding the same reference can still mutate it. For collection data that must remain immutable, consider `Map.copyOf`/`List.copyOf` and check the elements inside.

Key principles:

1. **Keep it as small as possible:** hold identifiers and required data; do not capture the entire request object, open streams, connections, sessions with their own lifecycles, or large object graphs.
2. **Trusted data:** actor/tenant used for authorization must be verified at a trust boundary; arbitrary headers from a caller do not automatically become permissions.
3. **Do not confuse context with thread safety:** an immutable context can be shared; a mutable object stored in a `ThreadLocal` can still suffer from data races if multiple threads hold references to it.
4. **Clear expiration:** a snapshot outliving a request inside a task does not mean the task is still allowed to perform side effects based on expired permissions or state.
5. **Context does not replace cancellation or transactions:** having a `requestId` does not propagate timeouts and does not automatically roll back any operations.

For APIs you control, the simplest and clearest approach is to pass the context as a parameter:

~~~java
// Illustration: methods defined in the application.
Result process(RequestContext ctx) {
    Data data = load(ctx);
    return transform(ctx, data);
}
~~~

Every dependency is explicit in the signature; the task does not depend on which thread runs it.

## 4. `ThreadLocal` binds values to a thread, not to a request

`ThreadLocal<T>` gives **each thread** its own value slot. Given the declaration:

~~~java
private static final ThreadLocal<RequestContext> CURRENT =
        new ThreadLocal<>();
~~~

Basic operations:

- `CURRENT.set(ctx)`: assigns the value on the **calling** thread.
- `CURRENT.get()`: reads from the **calling** thread; with `new ThreadLocal<>()`, if unset it typically returns `null`.
- `CURRENT.remove()`: removes the value on the **calling** thread, not on other workers.
- `ThreadLocal.withInitial(supplier)`: initializes a thread-specific value on demand; it does not tie itself to the request lifecycle.

Three important limitations:

**Does not automatically propagate across executors.** `executor.submit(task)` does not copy the caller's ordinary `ThreadLocal` to the worker; a task may receive `null` even though the caller called `set`.

**Can leak across reuse.** Workers outlive a single request. If task A forgets to call `remove`, task B running on the same worker can see A's context. This is both a data bug and a potential data-isolation vulnerability.

**Cleanup must happen on the right thread and in the right scope.** Calling `remove()` on the caller after `submit` does not clear the binding on the worker. A `finally` block must wrap the work on the exact thread that called `set`. For nested scopes, the outer value must be restored.

## 5. Runnable example: a later task mistakenly reads the previous task's context

Create the file **`RequestContextDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class RequestContextDemo {
    private record RequestContext(String requestId, String actor) {}

    private static final ThreadLocal<RequestContext> CURRENT =
            new ThreadLocal<>();

    private static String currentId() {
        RequestContext ctx = CURRENT.get();
        return ctx == null ? "none" : ctx.requestId();
    }

    // Use only when the wrapper owns the binding at the outermost task boundary.
    private static <T> Callable<T> bound(
            RequestContext context, Callable<T> body) {
        return () -> {
            CURRENT.set(context);
            try {
                return body.call();
            } finally {
                CURRENT.remove();
            }
        };
    }

    public static void main(String[] args) throws Exception {
        try (ExecutorService pool =
                     Executors.newSingleThreadExecutor()) {

            // Intentionally WRONG: set context without calling remove.
            System.out.println("unsafe-1=" + pool.submit(() -> {
                CURRENT.set(new RequestContext("req-1", "alice"));
                return currentId();
            }).get());

            // New task on the same worker sees the stale value.
            System.out.println("unsafe-2=" +
                    pool.submit(RequestContextDemo::currentId).get());

            // Clear the leftover state on the worker itself to continue the demo.
            pool.submit(() -> {
                CURRENT.remove();
                return null;
            }).get();

            // CORRECT at the task boundary: bind, then clean up in finally.
            System.out.println("safe-3=" + pool.submit(
                    bound(new RequestContext("req-3", "bob"),
                            RequestContextDemo::currentId)).get());

            System.out.println("after-3=" +
                    pool.submit(RequestContextDemo::currentId).get());
        }
    }
}
~~~

Run on **JDK 21**:

~~~bash
javac --release 21 RequestContextDemo.java
java RequestContextDemo
~~~

Output when there are no errors:

~~~text
unsafe-1=req-1
unsafe-2=req-1
safe-3=req-3
after-3=none
~~~

`newSingleThreadExecutor` guarantees that a single worker processes tasks sequentially. The two `get()` calls wait for each task, so the output always appears in the order shown. The first task intentionally leaves `req-1` behind; the second task reads the stale value even though it does not belong to that request. After clearing the leftover state, the task wrapped with `bound` sets `req-3` and calls `remove` in `finally`. The next task sees `none`.

**`bound` is designed for the outermost task**, where it owns the binding and must guarantee the worker is clean after the task finishes. If you nest this wrapper inside code on the same thread that already has a valid context in an outer scope, `remove` will wipe out that outer scope's binding as well. Therefore, you must distinguish outermost boundary cleanup from nested scopes.

## 6. Handling nested scopes properly

Suppose a request already has context X and a nested call wants to temporarily execute under context Y on the **same thread**. Once the nested call exits, X must be restored:

~~~java
// Illustration inside a class with CURRENT; not a standalone program.
RequestContext previous = CURRENT.get();
CURRENT.set(innerContext);
try {
    executeInnerWork();
} finally {
    if (previous == null) {
        CURRENT.remove();
    } else {
        CURRENT.set(previous);
    }
}
~~~

This is the **save/restore** policy for nested scopes. It does not replace cleaning up the worker at the outermost boundary: if the thread already carried leaked data beforehand, save/restore simply puts that leaked data back. At the task boundary, you must proactively ensure no context from another request remains attached after the task ends.

`remove` is clearer in intent than `set(null)` because it deletes the binding rather than just storing a null value. Exceptions must also be handled: if `executeInnerWork()` throws an error, the `finally` block still restores the state.

## 7. Passing context across `ExecutorService` and `CompletableFuture`

**Passing a snapshot explicitly** is the preferred solution whenever the API allows it:

~~~java
// Illustrative code: ctx is already verified, executor and work are provided.
RequestContext ctx = currentRequestSnapshot;
Future<Result> future = executor.submit(() -> work(ctx));
Result result = future.get();
~~~

The lambda captures the same immutable `ctx`; it does not require the worker thread to inherit an ambient context. If a legacy API only knows how to read from `ThreadLocal`, wrap **each task** with the wrapper from section 5 or a save/restore wrapper matching the ownership model.

With `CompletableFuture`:

~~~java
// Illustration: lookup and format receive RequestContext explicitly.
CompletableFuture<String> pipeline =
        CompletableFuture.supplyAsync(
                () -> lookup(ctx), ioExecutor)
        .thenApply(value -> format(ctx, value));
~~~

Common pitfalls:

- `supplyAsync(..., executor)` runs the supplier on the specified executor; it does not automatically copy ordinary `ThreadLocal` values from the caller.
- `thenApply` is not guaranteed to run on the same worker or the caller thread; the executing thread depends on the completion state of the stage.
- `thenApplyAsync` without an executor typically runs in `ForkJoinPool.commonPool()` per the Java 21 contract, with an exception when the default parallelism level is too low.
- `thenCompose`, `whenComplete`, `exceptionally`, and timeout callbacks can execute across different boundaries. Any callback that needs context must receive it explicitly or be bound in the appropriate scope.
- `get()/join()` only wait for or retrieve the result; they do not automatically synchronize all child tasks and do not automatically clean up any `ThreadLocal` on the executing thread.

If context is tied to access control, avoid assuming that logging the right `requestId` means authorization is correct; tasks must receive the verified principal/tenant according to application policy.

## 8. `InheritableThreadLocal` is not a per-request propagation mechanism

`InheritableThreadLocal` allows **a child thread to receive an initial value from its parent at the moment the child thread is created** (with optional inheritance control). It is not a fresh copy made every time a task is submitted to an executor.

~~~text
Request A sets context=A
  └─ Creates worker W → W may inherit A
Request B sets context=B
  └─ Submits task to existing W → W does not automatically update to B
~~~

If the initial value is a mutable object, default inheritance usually passes the same reference, not a deep copy. You can override `childValue` to transform the child's value, but you still have to manage data and ownership.

Therefore, do not use `InheritableThreadLocal` as the default solution for requests in thread pools. Inheritance also does not replace cleanup rules when a request finishes.

## 9. Virtual threads on JDK 21 and task lifetime

Virtual threads (JEP 444) are a standard feature in Java 21. They are still `java.lang.Thread`; a `ThreadLocal` is bound to the **virtual thread**, not to the JVM's carrier thread.

~~~java
// Illustrative example in a class with process(ctx); requires importing java.util.concurrent.
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> future = executor.submit(() -> process(ctx));
    System.out.println(future.get());
}
~~~

`newVirtualThreadPerTaskExecutor()` creates a new virtual thread for each task, so unlike a fixed platform-thread pool it does not attempt to reuse one worker for subsequent tasks. However:

- An ordinary `ThreadLocal` on the caller is **not automatically** propagated to the new task.
- A new virtual thread can receive `InheritableThreadLocal` depending on thread creation configuration; inheritance still does not equate to request lifetime.
- A `ThreadLocal` holding large caches/objects per virtual thread can consume significant memory if the number of virtual threads is very large.
- A task running in a virtual thread can still outlive the request if there is no explicit join/cancellation/ownership decision.
- Sharing mutable objects across multiple virtual threads still requires thread safety as usual.

**Thread-per-task** only describes how threads are allocated; it does not automatically turn disjoint tasks into a parent–child structure whose lifecycle ends with the request.

## 10. `ScopedValue` in Java 21: dynamically scoped context (preview)

JDK 21 introduces `ScopedValue` (JEP 446) as a **preview** feature. Instead of a mutable `set/get/remove` variable, you bind a value for a **dynamic scope** of a call. When the scope exits, the binding is automatically restored, even if an exception occurs. It is suited for one-way, mostly read-only information.

Create the file **`ScopedContextDemo.java`** on **JDK 21**:

~~~java
public class ScopedContextDemo {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(REQUEST_ID, "req-42").run(() -> {
            System.out.println("inside=" + REQUEST_ID.get());

            ScopedValue.where(REQUEST_ID, "req-inner").run(() -> {
                System.out.println("nested=" + REQUEST_ID.get());
            });

            System.out.println("restored=" + REQUEST_ID.get());
        });

        System.out.println("outside=" + REQUEST_ID.isBound());
    }
}
~~~

Run with preview enabled on **JDK 21**:

~~~bash
javac --enable-preview --release 21 ScopedContextDemo.java
java --enable-preview ScopedContextDemo
~~~

Output:

~~~text
inside=req-42
nested=req-inner
restored=req-42
outside=false
~~~

Explanation:

- `ScopedValue.newInstance()` creates a key, initially unbound.
- `ScopedValue.where(KEY, value).run(body)` binds the value during the execution of `body` and synchronous methods called within it that have access to the key.
- An inner scope can temporarily rebind it; upon exit, the outer scope sees `req-42` again.
- After exiting the outer scope, `isBound()` returns `false`. Calling `get()` when unbound will not return a valid requestId.
- `ScopedValue` does not automatically propagate across **arbitrary executor tasks**. When used together with `StructuredTaskScope`, bindings are inherited by child threads managed by the task scope according to the API's rules.
- The bound value can be a reference to a mutable object; `ScopedValue` itself does not make that object immutable.

**Version note:** both `ScopedValue` and `StructuredTaskScope` are still preview APIs in JDK 21. APIs/syntax in newer JDKs may differ; do not compile JDK 21 snippets by guessing from a newer JDK without verifying.

## 11. Parent–child task boundaries: Structured Concurrency (preview in Java 21)

A request often forks two tasks and then needs both results:

~~~text
Request (parent)
  ├─ create immutable context
  ├─ open task scope
  │   ├─ fork A → succeed or fail
  │   ├─ fork B → succeed or fail
  │   ├─ join / handle errors, cancel if needed
  │   └─ close, finish child tasks
  └─ aggregate, end request
~~~

`StructuredTaskScope` (JEP 453) aims to tie the lifecycle of child tasks to the scope owned by the caller. In Java 21, this is a preview API with policies such as `ShutdownOnFailure` and `ShutdownOnSuccess`. When a task scope is created within an appropriate `ScopedValue` binding, tasks forked by that scope can inherit bindings in a structured way.

Key points:

1. **Forking is not completion.** The caller must join, read results/errors, and close the scope.
2. **Cancellation is only a request.** `shutdown` can send an interrupt to unfinished subtasks; code that does not cooperate with interrupts or native I/O may keep running. On `close`, the scope waits for child threads to finish according to the API contract.
3. **Side effects are not automatically rolled back.** A task that has already written a file, sent a message, or called an external service before being canceled requires its own compensation/idempotency protocol.
4. **Not every task is a child of the request.** A job allowed to outlive the request must have its own independent owner, deadline, retry, and cleanup; do not hold references to a request object whose lifecycle has ended.

In a Java 21 application that does not use preview features, you can still apply these **structural principles** using `ExecutorService` and `Future`: maintain a list of task futures, wait for all required results, handle errors, cancel remaining tasks, and close the executor/resources. However, you must write that policy explicitly.

## 12. Deadlines, timeouts, and cancellation must be handled separately

For example, a request has a 300 ms deadline; A takes 100 ms, while B is making a 2-second I/O call:

~~~text
T0  Request R-42 starts, deadline = T0 + 300 ms
T1  Fork task A and task B
T2  Task A finishes; B is still waiting
T3  Request times out; caller sends cancel signal to B
T4  When does B actually stop and clean up resources? Depends on the API/code
~~~

Do not conflate three distinct events: **caller stops waiting**, **cancellation is requested**, and **the task has actually terminated**. For instance, `Future.get(timeout, unit)` may throw `TimeoutException` without automatically canceling the underlying future. `Future.cancel(true)` requests an interrupt if the task is running; it does not guarantee that I/O or native calls stop immediately or that side effects have not already occurred.

A sound design should:

- Compute the deadline at entry, pass the deadline or remaining budget through the API; set explicit timeouts on I/O so it does not wait indefinitely.
- Cancel child tasks that are no longer needed and ensure code cooperates with interruption where appropriate.
- Use `try/finally` or `try-with-resources` to release resources and context bindings.
- Only publish results while the request is still valid; for side effects that cannot be cleanly canceled, define idempotency or compensation mechanisms.
- If handing off to a background job, pass only a minimal snapshot and establish a separate lifecycle; do not hold onto closed request streams or transactions.

**Context propagation is not cancellation propagation**: carrying a `requestId` does not make a task understand deadlines on its own.

## 13. Tool selection table

| Approach | Best suited when | Main limitations |
|---|---|---|
| **Pass `RequestContext` as a parameter** | APIs you control, tasks/callbacks across multiple threads | Needs forwarding through several method layers |
| **`ThreadLocal` + bind/cleanup** | Legacy APIs requiring ambient context on the current thread | Easy to miss cleanup and leak on worker reuse |
| **`InheritableThreadLocal`** | You genuinely need to pass values when creating a child thread | Does not follow task submissions; mutable references can be shared |
| **`ScopedValue` (21 preview)** | Immutable, one-way read-only context with clear scope | Preview; does not cross arbitrary executors automatically |
| **`StructuredTaskScope` (21 preview)** | Tasks A/B are logical children of a request needing unified join/error/cancel | Preview; interrupt does not stop all work and does not roll back side effects |
| **Virtual thread per task** | Many I/O-bound tasks wanting a simple blocking model | Does not manage request context or parent–child relationships by itself |

Most pipelines can start with **an immutable context + explicit parameter passing**. Only use ambient state when a library/API or call structure gives a concrete reason and ownership is clearly defined.

## 14. Testing and common pitfalls

### Boundary testing

1. **Worker reuse:** use `newSingleThreadExecutor`; run R1 then R2 sequentially, verifying R2 does not see R1's context.
2. **Thread switching:** submit from caller to worker; check which fields are captured and which do not propagate automatically.
3. **Nested scopes:** bind X, temporarily bind Y, intentionally throw an exception; then verify X is restored.
4. **Concurrent tasks:** have two tasks read an immutable context concurrently; try replacing one field with a mutable collection to expose shared-state races.
5. **Cancellation:** test timeouts while a task is sleeping or waiting on I/O; distinguish the time cancellation is requested from the time resources actually close.
6. **Request ends early:** ensure child tasks do not become orphaned, or are handed off as background jobs with a new owner.

### Misconceptions to eliminate

| Misconception | Accurate understanding |
|---|---|
| "One request always has one thread." | A request can use multiple tasks/threads; a worker can process multiple requests. |
| "`ThreadLocal.set` on the receiving thread will be present on the executor worker." | Ordinary `ThreadLocal` does not propagate across `submit`. |
| "`remove()` on the parent thread cleans up the worker's context." | It only clears the value on the calling thread. |
| "`InheritableThreadLocal` follows each task." | It applies at **thread creation** time, not on each submission. |
| "`finally { remove(); }` is always right in every scope." | Nested scopes must restore the outer binding; outermost tasks need full cleanup. |
| "A `record` containing a `Map` is automatically thread-safe." | A `record` does not deep-copy mutable objects. |
| "`thenApply` always runs on a fixed thread." | A completion stage may run on a different thread depending on state and how it completes. |
| "Virtual threads automatically inherit the entire request context." | Thread-locals, inheritance, and lifetime still follow their own rules. |
| "`ScopedValue` automatically crosses all executors." | Binding follows dynamic scope; structured child inheritance happens via `StructuredTaskScope`. |
| "`cancel(true)` has stopped the task." | It is a cancel/interrupt request, depending on the executing code and I/O. |
| "Once the response is returned, all child tasks disappear." | Tasks may keep running unless joined/canceled or handed to a separate owner. |

## 15. Takeaways

**Request-scoped context is data and authorization tied to the logical lifecycle of a request, not an attribute of an OS thread.** When tasks cross `ExecutorService`, `CompletableFuture`, or virtual threads, context must be passed intentionally; when a task finishes, cleanup must happen on the right thread/scope. For groups of child tasks, clearly define who joins, handles errors, cancels, and closes resources.

Java 21 provides stable `ThreadLocal`, stable virtual threads, and preview options `ScopedValue`/`StructuredTaskScope`. Start with an immutable context, explicit passing, and bounded task lifetimes before reaching for ambient mechanisms.

## References

- [Java SE 21 — ThreadLocal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java SE 21 — InheritableThreadLocal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html)
- [Java SE 21 — CompletableFuture API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [JEP 446 — Scoped Values (Preview)](https://openjdk.org/jeps/446)
- [Java SE 21 — ScopedValue.Carrier API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ScopedValue.Carrier.html)
- [JEP 453 — Structured Concurrency (Preview)](https://openjdk.org/jeps/453)
- [Java SE 21 — Structured Concurrency](https://docs.oracle.com/en/java/javase/21/core/structured-concurrency.html)
