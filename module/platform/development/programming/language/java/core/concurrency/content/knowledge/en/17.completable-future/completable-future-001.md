# How CompletionStage and CompletableFuture Differ from Traditional Future

## 1. Distinguishing the three abstractions before running tasks

A Java application may need a result **later**. However, there are three distinct needs: holding a handle to wait on, declaring how to process **when the result arrives**, and actively deciding when the result is published.

- **Future** is the result contract of a submitted task: `get()` can block the caller, `isDone()` indicates a terminal state has been reached, and `cancel(...)` requests cancellation according to the implementation's contract. The traditional Future interface does not allow chaining dependent callbacks via `thenApply()`.
- **CompletionStage** is an interface describing a *graph of completion stages*: transforming results, chaining dependent tasks, combining two branches, or recovering from errors. It is not synonymous with a new thread or parallelism.
- **CompletableFuture** is both a Future and a CompletionStage; this class also provides `complete(value)`, `completeExceptionally(error)`, `join()`, `getNow(...)`, `supplyAsync()`, and factories for already-completed stages.

**Distinction:** Future/CompletionStage are Java API contracts, whereas pools/threads are the resources running the computation; these two layers interact with each other but are not identical. An async API can be executed by a worker using blocking I/O; returning quickly to the caller does not prove non-blocking I/O.

| Concern | Future | CompletionStage | CompletableFuture |
| --- | --- | --- | --- |
| Waiting directly for the result | `get()` | Convert via `toCompletableFuture()` when bridging is needed | `get()`, `join()` |
| Creating dependent stages | No standard composition API | `thenApply`, `thenCompose`, `thenCombine`... | Inherits that interface |
| Manually completing with a value/error | Not available via the interface | Not available via the interface | `complete`, `completeExceptionally` |
| Checking terminal state | `isDone`, `isCancelled` | Observed through stages | Has both Future and stage APIs |
| Caller capabilities | Wait on/cancel handle per contract | Attach dependent stages | Can complete the object itself if given the real source |

## 2. Future.get and the concept of a waiting point

```java
Future<Integer> a = executor.submit(() -> 20);
Future<Integer> b = executor.submit(() -> 22);
int sum = a.get() + b.get();
```

A and B can run concurrently when the executor has resources, because both were submitted before the caller started waiting. However, `get()` is a **potentially blocking synchronization point**. If the code submits A, calls `get()` on A, and only then submits B, two independent pieces of work can be unnecessarily serialized.

CompletionStage describes dependencies upfront, and only needs to block at the result-consumption boundary:

```java
CompletableFuture<Integer> a =
        CompletableFuture.supplyAsync(() -> 20, executor);
CompletableFuture<Integer> b =
        CompletableFuture.supplyAsync(() -> 22, executor);
CompletableFuture<Integer> sum = a.thenCombine(b, Integer::sum);
```

Here, `thenCombine` only runs the BiFunction when both sources succeed. It **does not initiate** tasks a/b itself or create new CPU cores. If task B truly depends on the value of A, use `thenCompose` to start B after A; if only transforming a single value, use `thenApply`.

```text
Single source: A ──thenApply(transform)──> U
Dependent:     A ──thenCompose(startB)───> B
Independent:   A ─┐
                  ├──thenCombine(combine)──> combined result
               B ─┘
```

Subsequent lessons will cover the detailed contract of each combinator. For this foundational lesson, read the graph by **input dependencies** and **completion conditions**, rather than inferring scheduling order.

## 3. Java 17 example: traditional handle vs. pipeline

Save as `FutureAndCompletionStageDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class FutureAndCompletionStageDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> ordinary = executor.submit(() -> 20);
            int oldStyle = ordinary.get() + 22;

            CompletableFuture<Integer> pipeline =
                    CompletableFuture.supplyAsync(() -> 20, executor)
                            .thenApply(value -> value + 22);

            System.out.println("Future=" + oldStyle);
            System.out.println("CompletionStage=" + pipeline.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac FutureAndCompletionStageDemo.java
java FutureAndCompletionStageDemo
```

Deterministic stdout when the tasks succeed:

```text
Future=42
CompletionStage=42
```

With `Future`, the `main` thread retrieves 20 and then adds 22. With `CompletableFuture`, the addition is registered as a dependent stage and the `main` thread only calls `join()` at the end. There is no guarantee that the `thenApply` callback will run on a specific worker: if the source is not yet complete, the completer thread may run the callback; if the source is already done, the thread registering the callback may run it as well.

`shutdown()` rejects new tasks without removing already-accepted tasks; `awaitTermination` only waits for the executor to stop within a time limit. A production I/O task still needs its own deadline and cleanup. The example uses two workers only for code illustration, not as a safe default configuration for all workloads.

## 4. Completion state differs from execution state

A `CompletableFuture` can be pending, completed normally with a value (including `null`), completed with an exception, or canceled (a form of exceptional completion). `isDone()` can be true in normal, exceptional, and canceled states alike; **it does not prove success**.

`new CompletableFuture<>()` creates a pending promise. A producer can call `complete(result)` or `completeExceptionally(cause)`; whichever completion wins the race normally determines the terminal outcome. APIs like `orTimeout` or `completeOnTimeout` can also compete to complete it. Reaching a terminal result does not guarantee that the underlying supplier/I/O has stopped, because the Future's state and the worker's lifecycle are two separate things.

If the source completes exceptionally, normal callbacks like `thenApply` are generally not invoked; the dependent stage transitions according to the exceptional completion. `exceptionally` / `handle` can recover according to their contracts; `whenComplete` is mainly used to observe logs/metrics and does not turn an error into a success by default. An error in a dependent callback does not revert an already-succeeded source back to a failure state.

```java
CompletableFuture<Integer> value =
        CompletableFuture.<Integer>failedFuture(
                new IllegalArgumentException("invalid"))
                .exceptionally(error -> 0)
                .thenApply(number -> number + 1);
// value.join() == 1
```

`Future.get()` reports task failure via a checked `ExecutionException` and can throw `InterruptedException`; `CompletableFuture.join()` reports errors as an unchecked `CompletionException` in the general case. Cancellation requires separate handling. The lessons on exceptions will analyze the cause chain, timeouts, and callback-specific errors.

## 5. Choosing a return API without exposing completion authority

Code that **owns the producer** can keep a private `CompletableFuture` to complete after receiving an NIO callback or an external event. Callers usually only need to chain steps: `CompletionStage` is appropriate as the API type. However, **merely changing the return type to the interface does not necessarily prevent callers from casting** if the real `CompletableFuture` instance is handed out directly. `minimalCompletionStage()` and `copy()` have specific contracts regarding keeping the source private; a dedicated lesson will verify this.

Keep result data immutable or safely published if shared across threads. A stage may complete correctly, yet its payload could still be a mutable object modified concurrently by two threads. `ThreadLocal` also does not automatically propagate across stages running on different threads.

## 6. Callback execution location policies and limitations

- **Non-Async** callbacks such as `thenApply` may run on the completer thread or on the thread calling the registration after the source completes. Do not put long blocking I/O on the completion path without controlling latency.
- `thenApplyAsync(fn)` uses the default asynchronous execution facility (typically the common `ForkJoinPool` when no executor is passed); it does not promise creating a dedicated thread for the callback.
- `thenApplyAsync(fn, executor)` delegates scheduling to that executor. A custom executor may have bounded queues, limited workers, or reject callbacks when shut down or saturated; scheduling failures must also be observed.
- `CompletableFuture.cancel(true)` does not guarantee interrupting a running supplier with the semantics of `cancel` on `FutureTask`. A future's timeout does not automatically cancel I/O either. Cooperative cancellation, I/O timeouts, and explicit lifecycles are required.

A dependent callback that calls `join()` to wait for a task needing the very worker currently occupied in a single-worker pool can cause self-deadlock/starvation. Composition expresses dependencies directly and avoids holding a worker just to wait.

## 7. Decision checklist and self-study

| Design question | Approach |
| --- | --- |
| Only need a handle to wait/cancel? | `Future` when the contract does not require composition |
| Need to describe further processing when the result arrives? | `CompletionStage` and dependent stages |
| Who is allowed to complete the result? | Keep the source `CompletableFuture` inside the owning component |
| B depends on A's data? | `thenCompose` instead of a nested future or calling `join` inside a worker |
| A and B are independent, need a combined result? | `thenCombine` or an appropriate aggregator |
| Callback is CPU-intensive or blocking? | Choose executor/capacity and manage lifecycle |
| Need timeout and cancellation? | Distinguish waiting, completion, interruption, and the underlying operation |

Answer these yourself using the example content:

1. Why does traditional `Future` not have `thenApply` while `CompletableFuture` does?
2. Why does an API returning `CompletionStage` not guarantee that tasks always run in parallel?
3. What happens to a dependent mapper when the source fails?
4. When must B use `thenCompose` instead of `thenCombine`?
5. Why is `isDone` not sufficient to prove that the underlying computation has stopped?
6. What are the risks of exposing a mutable `CompletableFuture` directly in a public API?

**Key takeaway:** `Future` is a **handle to receive a result**, `CompletionStage` is a **contract for chaining dependent steps**, and `CompletableFuture` implements both with manual completion capabilities. Background work still requires independent executor, error, timeout, and ownership policies; the following lessons dive deeper into each of these contracts.
