# Do Not Infer Asynchronous Task Completion Time from When a Method Returns `Future`

> **Context:** Java Advance → Instrumentation → **Probe Design**. A method returning `Future` or `CompletionStage` may only **hand over a handle to a future result**. If a Java agent places the end mark right at the `areturn` opcode or at the moment the interceptor receives the handle, the measurement usually reflects the **invocation/dispatch time** rather than the **completion time of the asynchronous work**. This article is based on Java 17+, with runnable examples and verified output on OpenJDK 21.

## 1. Distinguishing Return Time from Completion Time

Consider an API:

~~~java
CompletableFuture<String> fetchAsync() {
    return CompletableFuture.supplyAsync(() -> loadRemoteData(), executor);
}
~~~

If an agent measures:

~~~java
long start = System.nanoTime();
CompletableFuture<String> future = fetchAsync();
long end = System.nanoTime();
recordDuration(end - start); // Only the time to call fetchAsync and receive the handle
~~~

then `end - start` measures **the time to enter and return from `fetchAsync()`**. It does **not** necessarily include queueing time in the executor, running the task, network connection, retries, exception handling, or completing the stage. In this case, the method may return almost immediately while the task is still waiting for a free thread.

Conversely, do not state that every `Future` is *incomplete* at return time. A method can return `CompletableFuture.completedFuture(value)`, `failedFuture(error)`, a future that already completed early on another thread, or even perform substantial synchronous work before creating the handle. **What is true is: you must not infer completion state solely from the method return event.** You must rely on the future's contract and the completion mark of the exact stage to be measured.

### Useful Time Marks

~~~text
Caller thread                       Worker/executor thread
─────────────                       ─────────────────────
t0: call fetchAsync()
    ├─ prepare, schedule work -------> [queue ...]
t1: method returns Future              t2: task actually starts
    │                                   ├─ CPU / IO / retry ...
    │                                   └─ t3: worker completes work
    │                                                │
    │                                        t4: Future terminal
    │                                                │
    └── callback observing Future <------------------+
         t5: observer records SUCCESS / FAILURE / CANCELLED
~~~

The diagram illustrates **a typical async case**, not an invariant chronological order for every API. The task may start or even finish **before `t1`**; a `CompletableFuture` may be completed from any thread; many futures only represent one part of a pipeline.

| Mark | What does it measure? | Where is it usually available? |
|---|---|---|
| `t0` — invocation start | Invocation begins | Method entry / interceptor / bytecode probe |
| `t1` — method returns future | Synchronous part of the API ends, handle obtained | Method exit after obtaining return value |
| `t2` — work starts | Task begins executing on executor/thread | `Runnable`/`Callable` wrapper or hook inside producer |
| `t3` — actual work completes | Producer's processing path reaches its end | `try/finally` inside worker, after finishing the defined work |
| `t4` — Future terminal | Future transitions to terminal state: success, failure, or cancellation | Completion mechanics of Future/CompletionStage |
| `t5` — observer records mark | Instrumentation code receives completion notification | `whenComplete`, listener, `FutureTask.done()`, or appropriate hook |

Measurements should be **named differently**:

- **Method/dispatch latency:** `t1 - t0` — synchronous time of the method.
- **Queue delay:** `t2 - t_schedule` — time from when the task is accepted/queued until execution starts (requires hooking into the executor).
- **Task execution:** `t3 - t2` — time the worker actually runs (requires instrumenting the producer).
- **Observed future latency:** `t5 - t0` — time from invocation until the observer sees the Future become terminal. This is often a reasonable measurement for an asynchronous API, but **is not necessarily equal to the exact time physical work completes**.
- **Business completion:** may be even later than `t4`, for example a subsequent callback needing to commit, publish an event, or receive confirmation from another system. Only conclude this once the business contract is properly identified.

If you only record `method.duration` at `t1` and name it `task.duration`, dashboards will report very fast speeds even when the executor backlog is huge or downstream is hung. That is a **measurement boundary** error, not merely a unit conversion error.

## 2. What Do `Future` and `CompletableFuture` Actually Guarantee?

### `Future<V>` Only Guarantees the Ability to Check/Wait/Retrieve the Result

With `java.util.concurrent.Future<V>`:

- `isDone()` indicates whether the Future **has terminated** at the time of the call. Termination may be due to success, failure, or cancellation; **it does not mean success**.
- `isCancelled()` distinguishes the cancelled state recorded by the Future.
- `get()` may block the thread until the Future terminates, returning a result or throwing `ExecutionException`/`CancellationException`; `get(timeout, unit)` may also throw `TimeoutException` when **the wait itself** times out. A `get` timeout does not mean the Future is terminal.
- `cancel(...)` **attempts to cancel**; cancelling a Future does not guarantee that all background operations or external systems have stopped. For example, ongoing I/O may not cancel immediately, depending on the implementation and interruption mechanism.

The classic `Future` interface on Java 17 **does not provide a standard completion callback like `whenComplete`**. Therefore, a Java agent that only sees a method returning a `Future<?>` usually **cannot know on its own the exact time the Future completes** without adding probes to the producer/executor or an appropriate observer mechanism.

**Do not call `future.get()` in a method-exit interceptor just to measure!** That operation can block the caller, change API behavior from non-blocking to blocking, and cause thread starvation and deadlock when the task waits on the very thread being blocked.

### `CompletableFuture<T>` Is Both a `Future` and a `CompletionStage`

`CompletableFuture` allows registering a completion action:

~~~java
future.whenComplete((result, error) -> {
    // error == null usually indicates normal completion
    // error != null indicates abnormal completion, including cancellation cases
});
~~~

By the `CompletionStage.whenComplete` contract, the callback receives the outcome of the observed stage when that stage completes. It **returns a new dependent stage** having the result/exception of the source stage if the observer does not cause an error. If the callback itself throws an exception, the dependent stage may complete with that exception when the original stage succeeded. Therefore, instrumentation code must be defensive so that logging/metrics do not alter the state of the stage **returned to the caller**.

Note three nuances:

1. **Stage already completed before attaching listener:** the callback may run immediately upon registration; do not assume the callback always arrives on a worker thread.
2. **Stage not yet completed:** a non-async callback may run on the thread completing the stage or another caller participating in completion; the callback is not an "interrupt" with an absolutely precise timestamp.
3. **`whenCompleteAsync`:** running the observer must also go through an executor, so `t5` may be much later than `t4`; latency measured by an async callback includes the observer's queue delay.

To keep timing skew low, record `System.nanoTime()` right at the **start** of a non-async callback and keep the callback work lightweight. Even then, it is still a **terminal observation mark**, not an internal JVM timestamp at the instant of state transition.

### Cancelling a `CompletableFuture` Differs from Stopping a Worker

According to the Javadoc, `CompletableFuture.cancel(boolean)` completes the future with `CancellationException`; the `mayInterruptIfRunning` parameter **is not used to control running processing in this implementation**. Thus `isDone() == true` and `isCancelled() == true` can occur while producer code or I/O is still running. If instrumentation needs **the time work actually stops**, it must hook directly into the worker and the actual cancellation mechanism, not just listen for future cancellation.

## 3. Attaching Probes to the Right Lifecycle Without Changing the API Contract

Suppose a Java agent/interceptor observes a method and its return value. There are two paths:

**Synchronous path:**

~~~text
method entry → execute original method → normal return / synchronous throw
             → record method.duration
~~~

**Asynchronous path when the return value is a `CompletionStage`:**

~~~text
method entry → original method returns stage
             → record method/dispatch.duration
             → attach listener to that exact stage
             → return the EXACT original return value to caller
             → when stage is terminal → record future.observed.duration + outcome
~~~

Example pattern for Java 17+; this is an **illustrative helper**, called after the original method returns, not a standalone agent:

~~~java
import java.util.concurrent.CompletionStage;

final class AsyncMetrics {
    static Object observeReturnedValue(String operation, long startNanos,
                                       Object originalReturn) {
        long returnedAt = System.nanoTime();
        recordMethodTime(operation, returnedAt - startNanos);

        if (originalReturn instanceof CompletionStage<?> stage) {
            stage.whenComplete((value, failure) -> {
                long observedAt = System.nanoTime();
                try {
                    recordFutureTime(operation, observedAt - startNanos,
                                     failure == null ? "SUCCESS" : "FAILURE_OR_CANCEL");
                } catch (RuntimeException telemetryFailure) {
                    // Avoid throwing telemetry errors into the dependent stage.
                    // The internal logging channel should be independent and not block the completion path.
                }
            });
        }
        return originalReturn; // Preserve return-value identity/caller contract.
    }

    private static void recordMethodTime(String name, long nanos) {
        // Emit cardinality-bounded metric in a real application.
    }

    private static void recordFutureTime(String name, long nanos, String outcome) {
        // Emit metric/tracing; do not block the completing thread.
    }
}
~~~

**Why return `originalReturn`?** `whenComplete` creates **a new dependent stage**. You should not replace the returned Future with the new stage just to insert logging unless there is a design requirement: you could alter identity, the ability to call `cancel`, how libraries observe exceptions, or the concrete type of the return value. The code above only attaches an observer and returns the original handle.

The helper snippet uses the `FAILURE_OR_CANCEL` outcome to avoid lumping every `failure != null` into a business error. When distinction is needed, define a clear classification policy for `CancellationException`, `CompletionException`, and the original Future (if it implements `Future`). Do not rely on unstandardized exception messages.

**Synchronous throw:** if the original method throws an exception **before returning a Future**, no handle exists to attach a callback. The interceptor must record a separate `METHOD_THROW` event on the exception path; do not wait for a `whenComplete` that will never occur.

**Common pitfall with AOP/bytecode:** attaching a listener only after receiving the return value can miss information about when the task actually started. If the work already finished before the method returned, the observer may run immediately on the caller thread. When queue time or actual execution time is needed, add probes at the executor/worker, rather than trying to deduce them from a method-exit callback.

## 4. Java 17+ Hands-On: Proving with `CountDownLatch`

This experiment creates **two** tasks in an `ExecutorService`: one completes normally, one throws `IllegalArgumentException`. Each worker waits at a latch, so the method has already returned a `CompletableFuture` while the work is **definitely not yet complete** at the moment `main` prints the mark. `main` only lets the work finish after logging the return; the listener prints the completion mark.

Using latches to control ordering instead of `Thread.sleep(100)` makes the results less dependent on scheduling. **The stdout lines below were verified when compiled with `--release 17` and run on OpenJDK 21.**

### 4.1 File `FutureTimingDemo.java`

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicLong;

public final class FutureTimingDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newSingleThreadExecutor();
        try {
            runCase(workers, "ok", false);
            runCase(workers, "bad", true);
        } finally {
            workers.shutdownNow();
        }
    }

    private static void runCase(ExecutorService workers, String name, boolean fail)
            throws InterruptedException {
        CountDownLatch taskStarted = new CountDownLatch(1);
        CountDownLatch releaseTask = new CountDownLatch(1);
        AtomicLong completionObservedAt = new AtomicLong();

        long invokedAt = System.nanoTime();
        CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> {
            taskStarted.countDown();
            try {
                releaseTask.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted", e);
            }
            if (fail) {
                throw new IllegalArgumentException("boom");
            }
            return "OK";
        }, workers);
        long returnedAt = System.nanoTime();

        taskStarted.await();
        System.out.println("[RETURN] " + name + " done=" + future.isDone());
        CompletableFuture<String> observed = future.whenComplete((value, error) -> {
            completionObservedAt.set(System.nanoTime());
            System.out.println("[COMPLETE] " + name + " outcome="
                    + (error == null ? "SUCCESS" : "FAILURE"));
        });

        System.out.println("[CONTROL] " + name + " release");
        releaseTask.countDown();
        try {
            System.out.println("[RESULT] " + name + " value=" + observed.join());
        } catch (CompletionException e) {
            System.out.println("[RESULT] " + name + " cause="
                    + e.getCause().getClass().getSimpleName());
        }
        System.out.println("[CHECK] " + name + " returnedBeforeCompletion="
                + (completionObservedAt.get() > returnedAt));
        if (invokedAt > returnedAt) {
            throw new AssertionError("non-monotonic clock");
        }
    }
}
~~~

Compile and run commands from the directory containing the file:

~~~bash
javac --release 17 FutureTimingDemo.java
java FutureTimingDemo
~~~

On Windows PowerShell, use the exact same two commands. The class declares no package and the public class name matches the file name, so no separate `-cp` is needed if you are in the directory containing the `.class` file.

### 4.2 Verified Stdout on OpenJDK 21

~~~text
[RETURN] ok done=false
[CONTROL] ok release
[COMPLETE] ok outcome=SUCCESS
[RESULT] ok value=OK
[CHECK] ok returnedBeforeCompletion=true
[RETURN] bad done=false
[CONTROL] bad release
[COMPLETE] bad outcome=FAILURE
[RESULT] bad cause=IllegalArgumentException
[CHECK] bad returnedBeforeCompletion=true
~~~

**Exact explanation:**

- `future` is returned while the worker is still waiting on `releaseTask`. Therefore `isDone()` at the check mark is `false` in both cases.
- `[CONTROL] ... release` appears before the task can return a result or throw an exception. The `[COMPLETE]` line comes from `whenComplete` **after the future has completed**.
- `observed.join()` is used **only in the test program** to wait for the observer stage and establish log ordering. Do **not** put `join` into a production method-exit interceptor. For the failure case, `join` on the dependent stage throws `CompletionException` with cause `IllegalArgumentException`.
- `returnedBeforeCompletion=true` compares the timestamp right after the Future is returned with the timestamp recorded in the callback. Both cases print `true` because the callback cannot run before `main` releases the latch.
- `System.nanoTime()` is used as a monotonic clock to compute differences within the **same JVM**. The example only prints a boolean to avoid hard-coding a millisecond number dependent on CPU speed/scheduling.

**Scope of proof:** this is a controlled asynchronous computation model. It shows that method return cannot be treated as completion. It does not promise that every future is incomplete upon return: another API may return an already completed future.

## 5. If You Only Receive `Future<?>`, How Do You Capture Completion Marks?

Example:

~~~java
Future<String> submitted = executor.submit(() -> {
    return doWork();
});
~~~

`Future<String>` only has `isDone`/`get`/`cancel`; it is not required to support callbacks. There are three appropriate strategies, depending on your level of control:

| Instrumentation point | Mark actually observed | Pros and limitations |
|---|---|---|
| Wrapper around `Runnable`/`Callable` before `ExecutorService.submit` | When the task **starts** and **leaves the worker body** | Knows queue/run time; `finally` runs even on exception; must wrap the right task and avoid double-probing |
| `FutureTask.done()` if **you own the FutureTask implementation** | Notification when FutureTask transitions to terminal, including cancellation | Useful for Future state, but cancellation may arrive before the physical worker stops |
| Completion listener/callback provided by the framework | Mark when the framework's observer receives completion | Matches the framework's contract; must read thread and cancellation rules |
| Caller's `Future.get()` | When the caller **receives** the result after waiting | May be later than terminal and blocks; do not use as an absolute completion mark |

Do not spawn a thread just to call `get()` for **every Future**. This creates thread/wait overhead, can exhaust system resources, and still only measures when the observer receives the result. If the framework has no callback and you cannot instrument the worker, record a metric named "return latency" and document its limitations, rather than assigning a fake "completion latency".

### Producer Wrapper, When You Control the Task

**Illustrative snippet inside a method that already has `executor`, `task`, and `metrics`**, not a standalone program:

~~~java
long submittedAt = System.nanoTime();
Future<Result> future = executor.submit(() -> {
    long startedAt = System.nanoTime();
    try {
        return task.call();
    } finally {
        long finishedAt = System.nanoTime();
        metrics.recordQueueWait(startedAt - submittedAt);
        metrics.recordExecution(finishedAt - startedAt);
    }
});
~~~

The `submittedAt`, `startedAt`, and `finishedAt` marks measure **the wrapped task**, not automatically the time when all system-wide side effects complete. If work inside `task.call()` triggers new async work and returns early, you are only measuring **one async layer**. Similarly, if cancellation prevents the task from running at all, the `Callable` body is never invoked, so there are no `startedAt/finishedAt` marks; Future state must be measured separately.

## 6. Why Must "Future Complete" Also Be Defined Properly?

### Chained Stages Have Multiple End Points

~~~java
CompletableFuture<String> fetched = fetchAsync();
CompletableFuture<String> processed = fetched.thenApplyAsync(this::process, executor);
CompletableFuture<Void> persisted = processed.thenAcceptAsync(this::save, executor);
return persisted;
~~~

This is **pseudocode inside an instance method** with `fetchAsync`, `process`, `save`, and `executor`; it is not a self-compiling Java file. If the API returns **`persisted`**, measuring the completion of `fetched` will **miss processing and persistence**. You must attach the observer to **the stage matching the API's promise**. Conversely, if the API returns `fetched`, do not automatically include `persisted` in the measurement because that may be independent work outside the API's contract.

`thenApply`, `thenApplyAsync`, `thenCompose`, and `thenComposeAsync` have different semantics regarding scheduling/flattening. With `thenApply` returning another nested future inside, the outer stage may complete once it has created the inner Future without waiting for the inner one to complete; when the final result is needed, `thenCompose` is the API used to compose/flatten.

### `allOf`, `anyOf`, Timeout, and Cancellation

- `CompletableFuture.allOf(a, b)` describes **an aggregate stage** and waits for the constituent stages to complete according to contract. Record the aggregate outcome separately from each component's outcome.
- `CompletableFuture.anyOf(a, b)` completes when **one** component completes; do not infer that all remaining work has stopped.
- `orTimeout(...)` can make a `CompletableFuture` terminal with `TimeoutException` even when background work has not actually stopped. Similarly, `completeOnTimeout(...)` can provide a fallback value; future completion does not mean the original task succeeded.
- `cancel(...)` on `CompletableFuture` primarily changes promise state; it does not implicitly interrupt or roll back side effects.

Therefore, clearly distinguish between the **promise/stage lifecycle** and the **physical lifecycle of running work**, especially when measuring latency for RPCs, message queues, batch jobs, streaming, or retries.

### Some APIs Are Lazy or Have Multiple Completion Sources

A method returning `CompletionStage` usually represents work that has already been started or completed, but the interface does not require all implementations to share the same scheduling behavior. Other reactive APIs, such as publishers, may only trigger work upon **subscribe**. Do not apply the "attach `whenComplete` for `Future`" recipe to other return types without reading their contracts.

For an async HTTP client or database, ask "when does the future complete?": when headers are received, when the entire body is received, when the write succeeds, when committed, or only when the request is accepted? Name metrics after **meaningful events** rather than using a generic "finished" label.

## 7. Designing Instrumentation in an Agent: Before/After Method Return

An agent can use Byte Buddy, ASM, or an AOP interceptor to record `t0` at method entry and `t1` at method exit. For methods returning `CompletionStage`, an observer must also be added to compute `t5 - t0` later.

~~~text
METHOD ENTRY
    record t0, operation identity, trace context
      |
      v
METHOD EXIT
    if synchronous throw:
        record method.error + method latency
    else:
        record method return latency (t1 - t0)
        if return instanceof CompletionStage:
            attach lightweight completion observer
        return original return object
      |
      v
COMPLETION CALLBACK
    record t5 and outcome of EXACT returned stage
    emit async completion latency (t5 - t0)
    release tracing references/resources safely
~~~

### What the Agent Must Preserve

1. **Do not block the caller:** do not call `get()` or `join()` to "wait for the full duration" right inside Advice/MethodExit.
2. **Do not alter the return object:** attach the observer, return the original reference; `whenComplete` returns a different stage that can alter exception/cancellation semantics if inadvertently used as the return value.
3. **Do not assume `returnValue` is always non-null:** the method may return `null`; handle according to contract rather than dereferencing.
4. **Also record synchronous throws:** if the method throws an error before returning a future, no observer will exist.
5. **Classify terminal outcomes:** success, failure, cancellation, timeout, and business-specific cases may need separate metrics. `error != null` is not necessarily a system error.
6. **Keep observer execution lightweight and safe:** a non-async callback may run on the thread completing the business task. Do not block, do not perform heavy synchronous I/O; do not let a telemetry exception affect the dependent stage.
7. **Manage trace context across threads:** do not rely on the caller's `ThreadLocal` automatically appearing in the worker. Capture a bounded correlation ID/span context in the callback or use the framework's context propagation mechanism.
8. **Keep cardinality reasonable:** do not attach user IDs, URLs containing sensitive parameters, or unique IDs to metric labels. Use stable operation names and statuses.
9. **Mind liveness:** a Future that never completes will retain observers/references; monitor pending items, business timeouts, and memory retention.
10. **Avoid recursive instrumentation:** if the agent itself calls logging/executors that are also instrumented, there must be self-instrumentation filters, class loader guards, and reentrancy handling.

With sampled instrumentation, ensure the same invocation shares the sampling decision between the method mark and the future mark; otherwise, dashboards may show completion metrics without a corresponding entry or vice versa.

### Case Where the Future Is Already Complete at Method Exit

If a method returns a `CompletableFuture.completedFuture("cached")`, a listener attached after method return may run **immediately inside the listener-attaching code**. In that situation:

~~~text
invocation → completedFuture(...) → method returns already-completed stage
                                    → attach whenComplete → observer runs immediately
~~~

If `t5 - t0` is recorded, the value includes the overhead of moving from method return to observer registration. Do not infer precisely that "the task finished at t5"; that is the observation time. If the system needs completion time accurate to the microsecond, instrument **right at the producer completion point** or within a controllable pipeline, while documenting probe overhead.

## 8. Measurement Accuracy Checklist

| Review question | Reasonable way to check |
|---|---|
| Where does the "async duration" metric start? | Choose invocation, enqueue, or producer start and name consistently |
| Where does the metric end? | The exact stage returned to the caller becoming terminal, or an explicitly defined business event |
| Is `t_return` confused with `t_complete`? | With a latch-blocked task, return still occurs before completion |
| Can the method return an already-finished future? | Test `completedFuture`/`failedFuture` and check callback registration after completion |
| Are both exceptions and cancellations recorded? | Test normal, exceptional, cancelled, timeout, and synchronous throw |
| Does `get(timeout)` throwing `TimeoutException` mean the future is terminal? | Not necessarily; re-check `isDone`, do not treat a wait timeout as completion |
| Is the right pipeline stage being measured? | If the API returns `thenCompose/thenApplyAsync/allOf`, attach the observer to the returned stage |
| Can the real task continue after cancellation/timeout? | Yes; producer-side probes are needed if you want actual work stop |
| Does multi-threaded execution affect measurements? | `nanoTime` differences within the same JVM are used for duration; scheduler/observer latency adds overhead |
| Does instrumentation alter the API? | Return the exact instance; do not block threads; telemetry does not throw exceptions across business stages |

### An Example of a Misleading Dashboard

Suppose a call returns a `CompletableFuture` after 2 ms, while processing finishes after 480 ms. If the agent records `request.duration=2ms` at `areturn` and groups it under "async end-to-end latency", the dashboard will report 2 ms. Meanwhile, the caller waited about 480 ms for the data. These are **illustrative numbers**, not a measured benchmark. A more accurate way to record it:

~~~text
method_return_latency = 2 ms
observed_future_completion_latency = ~480 ms
outcome = SUCCESS
~~~

If the underlying worker continues after the future times out or is cancelled, add a `worker_execution_duration` metric instead of asserting that `observed_future_completion_latency` is the entire physical runtime.

## 9. Self-Check Questions

1. **Why does method exit not prove an async task has completed?** Because the return value may just be a handle; the producer may still be queued or running.
2. **Is a Future always incomplete when returned?** No; it may already be completed, failed, or cancelled beforehand. The specific state must be observed.
3. **Does `isDone() == true` mean success?** No; it could be failed/cancelled.
4. **Can a plain `Future` be instrumented with `whenComplete`?** No; `whenComplete` belongs to `CompletionStage`/`CompletableFuture`, not Java 17 `Future`.
5. **Is waiting on `get()` in an interceptor okay?** No; it breaks non-blocking behavior and can cause deadlocks.
6. **Can `whenCompleteAsync` delay the completion timestamp?** Yes; the observer is scheduled separately.
7. **Should the callback be attached to `fetched` or `persisted`?** To the stage matching the method's contract; if `persisted` is returned, measure `persisted`.
8. **Does a cancelled Future mean the remote operation has stopped?** Not necessarily; cancellation may only change the promise state.
9. **What is the effect of an observer callback throwing an exception?** The dependent stage created by `whenComplete` may complete abnormally; keep the observer non-throwing and do not replace the caller's return value.
10. **What is the appropriate clock for measuring duration within the same JVM?** `System.nanoTime()`; do not use wall-clock time as the sole source for short differences, and do not compare `nanoTime()` values directly across JVMs.

## 10. Authoritative References

- [Java SE 21 — `Future`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): `get`, `isDone`, cancellation, when the result can be retrieved.
- [Java SE 21 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion, `whenComplete`, cancellation semantics, `join`, chaining.
- [Java SE 21 — `CompletionStage`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionStage.html): dependent stage contract, callbacks, and error handling.
- [Java SE 21 — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, queue, asynchronous execution, and shutdown.
- [Java SE 21 — `FutureTask`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/FutureTask.html): `done()` and terminal states in the FutureTask implementation.
- [Java SE 21 — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()): measuring elapsed time based on differences within the same JVM.
