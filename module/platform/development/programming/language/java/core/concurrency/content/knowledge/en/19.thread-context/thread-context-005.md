# Propagating Context Across Runnable, Callable, and Executors in Java

## 1. The problem: does context belong to the task or to the thread?

In a concurrent program, **context** is the data that must travel along to process a unit of work correctly: `requestId` / `traceId`, initiator, locale, data partitioning info (tenant), processing deadline, or data for logging. This is *task data*, not inherently data of the thread running the task.

For example: the thread receiving request A has `requestId="req-A"` and calls:

```java
executor.submit(() -> processRequest());
```

`processRequest()` usually runs on a different thread. If it reads a `ThreadLocal` set by the thread that received request A, by default it **does not see thread A's value**. With an executor backed by a thread pool, workers are reused; leftover `ThreadLocal` values from a previous task can even cause a new task to read **the wrong context** if not cleaned up.

Three concepts need to be separated:

| Concept | Question answered | Impact |
| --- | --- | --- |
| **Context payload** | What data does the task need? | Defines the data fields, immutability, and access permissions |
| **Context capture** | At what point is the data captured? | Usually at task creation/submission time, before switching to another thread |
| **Context activation/cleanup** | When the task actually runs, which thread receives the context and how is it restored? | Ensures code inside reads the right data and does not leak to subsequent tasks |

**Priority principle:** whenever possible, pass an immutable context object as an **explicit parameter** to the function/task. Only use an implicit context mechanism (`ThreadLocal`, logging library MDC, ...) when you must serve APIs deep in the call stack that do not accept parameters.

The scope of this article is standard Java concurrency: `Runnable`, `Callable`, `Executor`, `ExecutorService`, `Future`, and `ThreadLocal`. Each library that manages its own context may require its own adapter.

## 2. What do Runnable, Callable, and ExecutorService change?

`Runnable` has the method `void run()`; it does not return a result and does not declare checked exceptions. `Callable<V>` has the method `V call() throws Exception`, allowing it to return a result or report a checked error.

| Submission method | Return value | Observing completion/errors |
| --- | --- | --- |
| `Executor.execute(Runnable)` | `void` | No `Future`; errors depend on the executor/handler |
| `ExecutorService.submit(Runnable)` | `Future<?>` | `get()` returns `null` on success; task errors are reported via `ExecutionException` |
| `ExecutorService.submit(Runnable, V result)` | `Future<V>` | `get()` returns the provided `result` value when the task succeeds |
| `ExecutorService.submit(Callable<V>)` | `Future<V>` | `get()` returns the result from `call()`; errors are wrapped in `ExecutionException` |
| `ExecutorService.invokeAll(Collection<Callable<V>>)` | List of `Future<V>` | Each element must be wrapped with context before submission |

The APIs above **transfer work across an asynchronous execution boundary**. They do not automatically copy any `ThreadLocal` from the caller to the worker. `submit()` may queue the work; the task executes later, at a time when the caller's context may have already been modified or cleared.

There are two guarantees to distinguish:

- With `ExecutorService`, actions prior to submitting a task *happen-before* the task's actions; the task's actions *happen-before* another thread reading the result via `Future.get()`.
- **Happens-before** ensures proper data publication under the Java Memory Model, but **does not mean the JVM transfers entries in `ThreadLocal` to the thread executing the task**. These are two different mechanisms.

## 3. The simplest and safest approach: context as an explicit parameter

Suppose each request's information is encapsulated using a `record` (Java 16+):

```java
record RequestContext(String requestId, String actor) {}

static String handle(RequestContext context) {
    return context.requestId() + "/" + context.actor();
}
```

When creating the task, pass the context directly into the lambda:

```java
RequestContext snapshot = new RequestContext("req-42", "alice");
Future<String> future = executor.submit(() -> handle(snapshot));
String answer = future.get();
```

This is an **illustrative snippet placed inside a method that has an `executor` variable**, not a standalone runnable file. `Runnable` applies the same way:

```java
RequestContext snapshot = new RequestContext("req-43", "bob");
executor.execute(() -> audit(snapshot));
```

Advantages: the data source is visible right in the signature, easy to test, independent of the thread pool, and requires no `ThreadLocal` cleanup. With an async chain, each stage can receive `snapshot` via its lambda regardless of where it runs.

**Note on “snapshot”:** a `record` only makes references to its component fields immutable in the sense that they cannot be reassigned; if a field is a `Map` / `List` or a mutable object, that object itself can still be mutated. Defensively copy mutable fields at the task-creation boundary if you need a stable snapshot, for example `Map.copyOf(attributes)`. Avoid passing objects containing short-lived information that a worker would retain after the request finishes.

## 4. When implicit context is needed: ThreadLocal is state of the executing thread

`ThreadLocal<T>` holds an independent value for **each thread** that accesses it. Within the same thread, functions deep in the call stack can read the context without passing parameters through every layer.

```java
private static final ThreadLocal<RequestContext> CURRENT =
        new ThreadLocal<>();
```

Typical mistake when using a pool:

```java
CURRENT.set(new RequestContext("req-101", "alice"));
executor.submit(() -> log(CURRENT.get()));  // worker may read null
CURRENT.remove();                           // only clears the caller's value
```

The caller's `CURRENT.remove()` **does not clean up the worker's ThreadLocal**. If the worker previously had another context, the worker's `get()` may even return an old value.

To propagate context across a thread-pool executor, you must **capture the context on the submitting thread**, then **install it on the thread running the task**, and **restore the exact prior state before returning the worker to the pool**:

```text
Caller thread                 Worker thread
  CURRENT = context-A
          |
   snapshot = CURRENT.get()
          |
     submit(wrapper) ----->  previous = CURRENT.get()
                             CURRENT.set(snapshot)
                             try { task.run()/call(); }
                             finally {
                                 restore(previous)
                             }
          |
   Caller manages its own       Worker is ready for another task
   context lifecycle
```

When the worker starts running, you should not call the worker's `CURRENT.get()` to “capture” the caller's context: by then you are already on the **wrong thread**. Nor should you hold a reference to a mutable object across the queue wait time and call it an immutable snapshot.

## 5. Two correct wrappers: Runnable and Callable

You can encapsulate the same context-scope rule for both interfaces. The design below assumes `null` means no context and `CURRENT` is `new ThreadLocal<>()` with no initial value defined:

**Wrapper for `Runnable`:**

```java
static Runnable withContext(Runnable task, RequestContext snapshot) {
    return () -> {
        RequestContext previous = CURRENT.get();
        if (snapshot == null) CURRENT.remove();
        else CURRENT.set(snapshot);

        try {
            task.run();
        } finally {
            if (previous == null) CURRENT.remove();
            else CURRENT.set(previous);
        }
    };
}
```

**Wrapper for `Callable<V>`:**

```java
static <V> Callable<V> withContext(
        Callable<V> task, RequestContext snapshot) {
    return () -> {
        RequestContext previous = CURRENT.get();
        if (snapshot == null) CURRENT.remove();
        else CURRENT.set(snapshot);

        try {
            return task.call();
        } finally {
            if (previous == null) CURRENT.remove();
            else CURRENT.set(previous);
        }
    };
}
```

These are **two method snippets**; they need to be placed in a class that has `CURRENT` and the appropriate `Runnable` / `Callable` imports. The standalone program example in the next section puts all the pieces together.

Why is each step needed?

1. `previous = CURRENT.get()`: records the context already present on the **worker**, which could belong to an outer scope in a nested call.
2. `CURRENT.set(snapshot)` or `remove()`: applies the new task's context; a `null` snapshot must mean “no context”, avoiding reusing an old value.
3. `try`: runs the work, whether it returns a result or throws an exception.
4. `finally`: always restores the old value. If there was no prior value, use `remove()` to avoid retaining leftover state for the lifetime of the thread pool.

**Why restore instead of always calling remove?** If a task calls another function that also activates a temporary context on the same thread, the inner wrapper must restore the outer wrapper's context. And for a pool worker whose initial context is empty, restoring leads to `remove()`.

Do not share a single `ThreadLocal` for mutable data across multiple requests and mutate the same object directly. Setting an object on two threads does not make that object thread-safe; concurrency safety of the data is still required.

## 6. Complete Java 21 example with deterministic output

The following program uses **a single platform worker** (`newFixedThreadPool(1)`) to prove that both task types can receive their own context, and afterward the worker returns to having no context. The example intentionally waits with `Future.get()` before each print so stdout does not depend on scheduling order.

Create the file **ContextPropagationDemo.java**:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

public class ContextPropagationDemo {
    record RequestContext(String requestId, String actor) {}

    private static final ThreadLocal<RequestContext> CURRENT =
            new ThreadLocal<>();

    static Runnable withContext(Runnable task, RequestContext snapshot) {
        return () -> {
            RequestContext previous = CURRENT.get();
            if (snapshot == null) CURRENT.remove();
            else CURRENT.set(snapshot);
            try {
                task.run();
            } finally {
                if (previous == null) CURRENT.remove();
                else CURRENT.set(previous);
            }
        };
    }

    static <V> Callable<V> withContext(
            Callable<V> task, RequestContext snapshot) {
        return () -> {
            RequestContext previous = CURRENT.get();
            if (snapshot == null) CURRENT.remove();
            else CURRENT.set(snapshot);
            try {
                return task.call();
            } finally {
                if (previous == null) CURRENT.remove();
                else CURRENT.set(previous);
            }
        };
    }

    static String describe() {
        RequestContext c = CURRENT.get();
        return c.requestId() + "/" + c.actor();
    }

    public static void main(String[] args) throws Exception {
        RequestContext a = new RequestContext("req-101", "alice");
        RequestContext b = new RequestContext("req-202", "bob");

        try (ExecutorService executor = Executors.newFixedThreadPool(1)) {
            Future<String> call = executor.submit(
                    withContext(() -> "Callable: " + describe(), a));
            System.out.println(call.get());

            AtomicReference<String> output = new AtomicReference<>();
            Future<?> run = executor.submit(
                    withContext(
                            () -> output.set("Runnable: " + describe()), b));
            run.get();
            System.out.println(output.get());

            Future<Boolean> cleared =
                    executor.submit(() -> CURRENT.get() == null);
            System.out.println("Context cleared: " + cleared.get());
        }
    }
}
```

Compile/run with **JDK 21+**:

```bash
javac ContextPropagationDemo.java
java ContextPropagationDemo
```

**Exact stdout:**

```text
Callable: req-101/alice
Runnable: req-202/bob
Context cleared: true
```

Analysis:

- `call` is a `Callable<String>`. Snapshot `a` is passed along with the wrapper from the caller; the data is installed on the worker when `call()` starts, then cleaned up in `finally`.
- `run` is a `Runnable`. It writes the result string into `AtomicReference`, and `main` waits on `Future.get()` before printing. There is no need to force `Runnable` to have a return type.
- The example uses a single-worker pool to ensure the verification task gets to observe **the exact worker that ran the previous two tasks**; `Context cleared: true` confirms cleanup in this case.
- `try (ExecutorService ...)` requires JDK 19+ because `ExecutorService` supports `AutoCloseable` starting in Java 19; JDK 21 is a stable choice for this program.
- `Future.get()` both waits for completion and allows observing exceptions in the task. If a task throws an error, `finally` still runs before `get()` throws `ExecutionException`.

The example demonstrates how to install/restore context; it is not intended as a benchmark for executor throughput or latency.

## 7. Capturing context at the right time

The easiest place to go wrong is **capturing too late**. Compare:

**Wrong: capturing inside the task running on the worker**:

```java
executor.submit(() -> {
    RequestContext snapshot = CURRENT.get(); // reads the worker's ThreadLocal
    handle(snapshot);
});
```

**Right: capturing before submit**:

```java
RequestContext snapshot = CURRENT.get(); // on the caller
executor.submit(withContext(() -> handle(CURRENT.get()), snapshot));
```

Both snippets above assume `executor`, `CURRENT`, and `handle(...)` are already in scope; they illustrate the capture boundary, not standalone compilable files.

Details that affect correctness:

- **Queue delay**: a task may start running seconds or minutes later; capturing at `submit` brings the right data associated with the original task.
- **Mutable context**: a reference-type snapshot can still have its contents mutated; create an immutable object or copy the relevant values before submitting.
- **Cancellation**: if a task has not started yet and is cancelled, the wrapper has not activated the context; there is no worker state to restore. If it is already running and gets interrupted, `finally` remains a reliable cleanup point.
- **Rejected submission**: `RejectedExecutionException` happens before the wrapper executes. The caller's context must be managed according to the caller's scope; do not expect worker cleanup.
- **Nested submission**: if a task currently has `context-A` and submits another task, you must capture `A` again at submission time; the new executor does not automatically inherit the parent task's context.
- **Timeout**: a `future.get(timeout, unit)` timeout only affects the waiting caller; the task itself **does not stop automatically**. You must decide on cancellation/interruption and consistency of the context data.

## 8. Wrapping Executor.execute and decorator limits

If your code calls `execute(Runnable)` in many places, you can wrap at the `Executor` level so every command is captured automatically:

```java
static Executor contextAware(Executor delegate) {
    return command -> {
        RequestContext snapshot = CURRENT.get(); // on the caller
        delegate.execute(withContext(command, snapshot));
    };
}
```

This is an **illustrative method**; it requires importing `java.util.concurrent.Executor` and using the same `CURRENT`/`withContext` defined earlier. Place the wrapper when configuring dependencies:

```java
Executor decorated = contextAware(underlyingExecutor);
decorated.execute(() -> performWork());
```

Here `snapshot` is taken **on each `execute` call**, not once when creating `decorated`. If you captured it when creating the wrapper, tasks from different requests would share the wrong context.

**Very important limitation:** `Executor` only has `execute`. The wrapper above **does not automatically carry the APIs** `submit`, `invokeAll`, `schedule`, or `CompletableFuture.supplyAsync` of other interfaces. Do not cast the wrapper to `ExecutorService`. There are three options:

1. With `ExecutorService`, wrap each `Runnable`/`Callable` directly before `submit` or before building the collection for `invokeAll`.
2. If you need to “decorate the entire service”, implement a complete `ExecutorService` adapter covering all task-submission paths, shutdown, exceptions, and scheduling (if it is a `ScheduledExecutorService`). A wrapper that only overrides `execute` may miss specialized methods on the delegate.
3. If you can modify the business API, continue to prefer passing `RequestContext` as a parameter; this approach needs no decorator.

Using `CompletableFuture`:

```java
RequestContext snapshot = CURRENT.get();
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(() -> handle(snapshot), executor);
```

The snippet above **explicitly passes** the snapshot into the lambda; `supplyAsync` does not automatically carry the caller's `ThreadLocal`. With a `thenApplyAsync` / `thenComposeAsync` chain, you must check **which executor each stage runs on**, where it is triggered from, and whether it reads implicit context. Do not assume a chain will inherit context just because the previous stage had the right value.

## 9. Common mistakes when propagating context through executors

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Setting `ThreadLocal` on the caller and expecting the worker to read it | Worker sees `null` or another task's data | Pass as a parameter or capture/activate properly on the worker |
| Reading `CURRENT.get()` for the first time inside the lambda on the worker | Captures at the wrong time and on the wrong thread | Capture **before submit** |
| Calling `set()` without `remove()`/restore in `finally` | Context leaks to subsequent tasks, especially dangerous for trace/user/tenant | Restore the previous value in `finally` |
| Always calling `remove()` without saving `previous` | Breaks outer scope when wrappers are nested | Save/restore worker state |
| Keeping a mutable `HashMap` as a snapshot across requests | Data race or information changes while queued | Immutable copy / limit ownership |
| Wrapping `execute` and assuming `submit`, `invokeAll`, `schedule` are covered | Other task-submission paths bypass propagation | Wrap each API of the appropriate type or build a full adapter |
| Not calling `Future.get()` when error detection is needed | Exceptions in `submit` can stay inside `Future` unreported | Observe `Future` and handle `ExecutionException` |
| Using `InheritableThreadLocal` with a pool and expecting each task to inherit | Values only apply when creating a child thread, not on each task submission | Intentional propagation at the task boundary |
| Retaining context with secrets/heavy objects across long-running tasks | Increases data exposure risk and holds unnecessary references | Pass only minimal fields and limit lifetime |

### Distinguishing InheritableThreadLocal, virtual threads, and ScopedValue

- `InheritableThreadLocal` transfers initial values at **child thread creation time** according to Java's rules; pre-created thread-pool workers do not automatically receive new values on each `submit`. Moreover, mutable values inherited by reference can still share state unintentionally.
- A virtual thread is still a Java `Thread` and still supports `ThreadLocal`. The “one virtual thread per task” model reduces some thread-pool reuse risks, but **does not turn an arbitrary executor's task into a logical child that automatically inherits all context**. Do not conflate thread lifecycle with request boundaries.
- `ScopedValue` was finalized in **JDK 25** (JEP 506) and is useful for passing read-only data within a **dynamic scope**. When submitting arbitrary tasks to an executor, you still have to explicitly define how the binding is created on the thread running the task; a caller's binding does not automatically propagate to every executor. This is an additional option in modern Java, not a requirement to run the Java 21 example above.

JDK 25+ example with `ScopedValue` (illustrative snippet, not standalone):

```java
static final ScopedValue<RequestContext> CTX =
        ScopedValue.newInstance();

RequestContext snapshot = currentContext;
executor.execute(() ->
        ScopedValue.where(CTX, snapshot).run(() -> performWork()));
```

`ScopedValue.where(...).run(...)` creates a binding only for the duration of `run`. Rules for accessing and propagating to child tasks in structured concurrency must follow the documentation for the corresponding JDK version.

## 10. Testing and observing context propagation

You should test both **having the right data** and **having no leftover data**:

1. Run two tasks with different contexts sequentially on the **same worker**; verify task B does not accidentally read context A.
2. Have a task throw an exception after activating context; after `Future.get()` reports the error, submit a task to check that the ThreadLocal is empty.
3. With nested wrappers, confirm the outer context is **restored** after the inner scope closes.
4. With a multi-worker thread pool and tasks with mixed `requestId`s, add concurrent/stress tests to catch improperly shared mutable references.
5. With queue delay, change the context on the caller after `submit` and confirm the task still uses the captured snapshot.
6. Test `RejectedExecutionException`/cancellation branches, and ensure no unnecessary context is retained.

For logging, attach the context's `requestId` to log records when the task runs; each task must observe its own ID. If using a logging library's MDC, MDC is usually backed by its own thread-local: propagating a `CURRENT` variable **does not automatically propagate the entire MDC**. Each context system has its own snapshot, restore, and cleanup mechanism.

Do not log sensitive authentication data just to debug propagation. IDs used for correlation may be logged depending on policy; credentials/tokens should have their own separate handling path.

## 11. Which strategy to choose?

| Need | Recommended strategy | Reason |
| --- | --- | --- |
| You control the business method signature | `handle(context)`, lambda captures an immutable value | Readable, easy to test, no implicit state |
| Deep legacy API needs “current context” | `Runnable`/`Callable` wrapper with `ThreadLocal`, restore in `finally` | Compatible with existing call stack, prevents context leaks |
| Many `execute` calls | Decorate `Executor` with a snapshot at each `execute` call | Reduces boilerplate at call sites |
| Using `submit`, `invokeAll`, scheduling | Wrap tasks at each API or build a full adapter | Leaves no execution path uncovered |
| Async chain across multiple executors | Pass context explicitly to each stage or use a decorator with verified coverage | Does not rely on assumptions of implicit chain inheritance |
| Java 25+ needing read-only context in a dynamic scope | Consider `ScopedValue`, still making the task boundary explicit | Clearer scope, avoids long-lived mutable thread-locals |

Self-check questions:

1. **Why is setting `ThreadLocal` in the caller before `submit` not enough?** Because `ThreadLocal` is bound to each thread and the task may run on a different worker.
2. **When should the snapshot be created?** When the caller builds/submits the task; activation happens later, on the worker when the task executes.
3. **Why restore `previous` instead of just calling `remove`?** Because wrappers can be nested on the same thread; the outer scope must keep its own context intact.
4. **Can you infer that `ThreadLocal` is transferred via `Future.get()` happens-before?** No. Happens-before guarantees memory visibility order, not copying per-thread state.
5. **Does an `Executor.execute` wrapper automatically support `ExecutorService.submit`?** No. `Executor` only exposes `execute`, and other APIs must be handled separately.

## 12. Official references

- [Java SE 21 — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `invokeAll`, `Future`, and memory consistency guarantees.
- [Java SE 21 — Runnable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runnable.html) and [Callable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Callable.html): task execution contracts.
- [Java SE 21 — ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html): per-thread values, `get`/`set`/`remove`.
- [Java SE 21 — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html): inheritance limits at thread creation time.
- [Java SE 25 — ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html) and [JEP 506](https://openjdk.org/jeps/506): scoped context binding in modern Java.
