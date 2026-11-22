# Timed invokeAll() and invokeAny(): Handling Incomplete Tasks

## 1. Setting a Deadline for a Group of Callables

`ExecutorService` allows submitting a collection of `Callable<T>` tasks to run on a pool. Sometimes we need all results; other times we only need a single successful result from multiple equivalent alternatives. In both cases, a slow or stuck task can cause the calling thread to wait too long. Two timeout overloads help set a **shared waiting budget for the entire batch**:

```java
<T> List<Future<T>> invokeAll(
    Collection<? extends Callable<T>> tasks,
    long timeout, TimeUnit unit) throws InterruptedException;

<T> T invokeAny(
    Collection<? extends Callable<T>> tasks,
    long timeout, TimeUnit unit)
    throws InterruptedException, ExecutionException, TimeoutException;
```

These are illustrative API signatures, not a standalone Java program. Non-timeout overloads also exist. The timeout applies to the entire call (including task submission and waiting), **not an individual timeout per task**. The timeout overloads use `TimeUnit` such as `MILLISECONDS` or `SECONDS`.

Distinguish between the two questions:

- `invokeAll`: "By the deadline, has each task produced a result, failed, or been cancelled?"
- `invokeAny`: "Did **one** task complete **successfully** before the deadline?"

This article covers only standard Java Concurrency in `java.util.concurrent`, independent of frameworks.

## 2. Key Contract Comparison Table

| Scenario | `invokeAll(tasks, timeout, unit)` | `invokeAny(tasks, timeout, unit)` |
| --- | --- | --- |
| Normal return value | A list of `Future<T>`, in the exact order of the input tasks | A single `T` value from one successfully completed task |
| When the deadline expires | Returns the list, requests cancellation of incomplete tasks | Throws `TimeoutException` if no task has succeeded yet |
| Task A fails, B succeeds | Future A reports `ExecutionException` at `get()`, B has a value | May return B's value |
| All tasks fail | Returns a Future for each task, each `get()` may report an error | Throws `ExecutionException` |
| When the caller is interrupted | Throws `InterruptedException`; incomplete tasks are requested to cancel | Throws `InterruptedException`; incomplete tasks are requested to cancel |
| When one task has succeeded | Still waits for the remaining tasks or until the timeout expires | May return the result and cancel the other tasks |
| Observing partial results | Yes, by iterating through the Futures | Does not return a list of Futures through this API |

`invokeAll` does not guarantee that every task **succeeds** before returning. It guarantees that upon normal return, **all Futures in the list have `isDone() == true`**: succeeded, failed, or cancelled. When the deadline expires, the executor requests cancellation of tasks that have not yet completed.

`invokeAny` only cares about one **successful result**; an early task failure is not enough to terminate the call if other candidates remain. If all tasks fail, the method throws `ExecutionException`. If no task has succeeded when the deadline expires, it throws `TimeoutException`. When a result is obtained or upon abnormal termination, unnecessary tasks are requested to cancel.

Both APIs can throw `RejectedExecutionException` if the executor refuses to accept work, depending on the configured `RejectedExecutionHandler`. That is a task acceptance failure, distinct from an execution failure of a `Callable`.

## 3. Timed invokeAll: What Happens to Incomplete Tasks?

Suppose `invokeAll` is called with A, B, and C within a 500 ms budget:

1. The `Callable` instances are converted into tasks for the executor to run. A small pool may cause some tasks to wait in the queue.
2. `invokeAll` waits for all tasks to complete or for the shared timeout to expire.
3. A may have returned a value, B may have thrown an exception, while C is still running/waiting when the deadline expires.
4. The API requests `cancel(true)` on incomplete tasks and returns the list of `Future` objects corresponding to A, B, and C.
5. The caller classifies each Future: succeeded, failed, or cancelled.

The sequence above is an illustrative example; actual execution depends on scheduling. The list of Futures is returned in **the order of the input collection**, not the order of completion. If the data has IDs, keep a list of IDs in the same order to match results accurately.

| State | `isDone()` | `isCancelled()` | `get()` |
| --- | --- | --- | --- |
| Completed successfully | `true` | `false` | Returns result `T` (which may be `null`) |
| Completed with exception | `true` | `false` | Throws `ExecutionException`; retrieve the root cause with `getCause()` |
| Cancelled | `true` | `true` | Throws `CancellationException` |

**Cancelling a Future does not mean the task has actually stopped**. `cancel(true)` only attempts to send an interrupt signal to the running thread; uncooperative code may continue holding resources or causing side effects.

### Standalone Example: Tasks Timing Out

Save as `TimedInvokeAllDemo.java`. An unopened `CountDownLatch` prevents both tasks from returning normally; even a task that has not started running yet will be cancelled when the timeout expires.

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class TimedInvokeAllDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch gate = new CountDownLatch(1);
        try {
            List<Callable<Integer>> tasks = List.of(
                    () -> { gate.await(); return 1; },
                    () -> { gate.await(); return 2; });
            List<Future<Integer>> futures =
                    pool.invokeAll(tasks, 200, TimeUnit.MILLISECONDS);

            for (int i = 0; i < futures.size(); i++) {
                Future<Integer> f = futures.get(i);
                System.out.println("task " + (i + 1)
                        + " done=" + f.isDone()
                        + " cancelled=" + f.isCancelled());
                try {
                    System.out.println("value=" + f.get());
                } catch (CancellationException expected) {
                    System.out.println("no result: cancelled");
                } catch (java.util.concurrent.ExecutionException failed) {
                    System.out.println("failure=" + failed.getCause());
                }
            }
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Workers still running");
            }
        }
    }
}
```

Run with Java 17+:

```bash
javac TimedInvokeAllDemo.java
java TimedInvokeAllDemo
```

Stdout:

```text
task 1 done=true cancelled=true
no result: cancelled
task 2 done=true cancelled=true
no result: cancelled
```

`gate` never has `countDown()` called, so a task that has started will wait at `await()` until interrupted, while a task that has not started can still be cancelled. Both Futures become `done` and `cancelled`. In this example, `await()` supports interruption so the worker can exit; that is not a property of all I/O operations.

## 4. Retaining Partial Results from invokeAll

Timed `invokeAll` is a useful choice when you want to keep the results already available before the deadline. Do not discard the entire batch just because one task did not finish, unless business logic strictly requires every result to be valid together.

The following snippet assumes `futures` is the list returned normally from timed `invokeAll`, `taskIds` matches in the exact same order, and the `record...` methods are provided by the application:

```java
for (int i = 0; i < futures.size(); i++) {
    Future<Result> f = futures.get(i);
    String id = taskIds.get(i);

    if (f.isCancelled()) {
        recordMissing(id);
        continue;
    }

    try {
        Result value = f.get(); // invokeAll return: Future is already done.
        recordSuccess(id, value);
    } catch (java.util.concurrent.ExecutionException failure) {
        recordFailure(id, failure.getCause());
    } catch (java.util.concurrent.CancellationException cancelled) {
        recordMissing(id);
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        break;
    }
}
```

This is a **fragment**, not a standalone program, because `Result` and the helper methods are not declared. Every Future in the list after a normal `invokeAll` is already `done`, so `get()` does not wait for the task to keep running, but you still have to handle exceptions per Java's method signature. If the reading thread is interrupted, restore the interrupt flag or propagate the exception to the caller according to the application's contract.

Distinguish between **execution failure** (`ExecutionException`), **timeout/cancellation** (`CancellationException`), and **invalid business result** (the Future succeeded, but the data does not meet requirements). Each result can be represented by a record containing task ID, status, value, and error to avoid index mismatches during aggregation.

If the caller is interrupted during `invokeAll` itself, the method throws `InterruptedException` and **does not return a list of Futures**; do not assume you can retrieve partial results via the return value once an error has been thrown.

## 5. Timed invokeAny: One Success Is Enough

`invokeAny` is suitable when multiple tasks perform equivalent alternatives and only **one** successful result is needed. It neither selects "the first task in the list" nor returns the first failed result as a success.

- If one task returns `T` before the deadline, `invokeAny` may immediately return `T` and request cancellation of the other tasks.
- If some tasks throw exceptions, the method continues trying other tasks as long as a successful result is still possible and time remains.
- If all tasks fail, `ExecutionException` indicates there was no success.
- If the deadline expires before any task succeeds, `TimeoutException` is thrown.
- The API **does not return the `Future`s of losing tasks**. If you need details for every task, manage Futures separately or use `ExecutorCompletionService`.

Do not use `invokeAny` arbitrarily on tasks that cause non-idempotent side effects: multiple tasks may have already started sending requests, writing files, or persisting data **before** a winner is found. Cancelling after one task wins does not undo side effects that have already occurred.

### Standalone Example: Success and Timeout

Save as `TimedInvokeAnyDemo.java`:

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TimedInvokeAnyDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch neverOpen = new CountDownLatch(1);

        try {
            String winner = pool.invokeAny(
                    List.<Callable<String>>of(
                            () -> { neverOpen.await(); return "never"; },
                            () -> "ready"),
                    5, TimeUnit.SECONDS);
            System.out.println("winner=" + winner);

            try {
                pool.invokeAny(
                        List.<Callable<String>>of(
                                () -> { neverOpen.await(); return "never"; }),
                        200, TimeUnit.MILLISECONDS);
                System.out.println("unexpected success");
            } catch (TimeoutException expected) {
                System.out.println("timed out");
            }
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Workers still running");
            }
        }
    }
}
```

Run:

```bash
javac TimedInvokeAnyDemo.java
java TimedInvokeAnyDemo
```

Stdout when the executor schedules tasks within the 5-second budget:

```text
winner=ready
timed out
```

The first task has no way to return `"never"` because the latch never opens; the second task returns `"ready"`, so that is the sole successful result of the first race. In the second race, no task can complete before the deadline, so `TimeoutException` is expected. Both branches are covered by shutdown handling in `finally`.

## 6. Timeout Does Not Guarantee Stopping Threads or Undoing Side Effects

Three distinct points in time must be separated: **the caller's deadline**, **the Future transitioning to cancelled**, and **the task code actually stopping execution / releasing resources**. The latter two do not necessarily coincide.

`cancel(true)` attempts to interrupt the running worker. `CountDownLatch.await()`, `Thread.sleep()`, and many blocking APIs can throw `InterruptedException`. A CPU loop that does not check for interruption or I/O that does not support interruption may keep running. A cancelled Future can cause `get()` to throw `CancellationException` while the worker is still performing side effects.

Example `Callable` fragment checking for interruption during iterative processing:

```java
Callable<Integer> job = () -> {
    int count = 0;
    for (Item item : items) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("cancelled");
        }
        process(item); // Needs its own I/O timeout if applicable.
        count++;
    }
    return count;
};
```

`Item`, `items`, and `process` are application-defined. If `process` invokes I/O with an overly long timeout, checking for interruption at the top of the loop may not be enough. You need to configure timeouts at the socket/client layer or use an actual cancellation mechanism supported by the dependency.

`Callable.call()` allows throwing `InterruptedException`. If a `Runnable` catches this exception, exit according to contract and typically restore the interrupt flag with `Thread.currentThread().interrupt()`; do not swallow it and continue indefinitely.

Resources inside a task should use `try/finally` or `try-with-resources`. However, a task that **never started** will not execute cleanup in its body. Resources allocated before submitting the task must have another responsible owner. Design idempotent side effects and reconciliation mechanisms if work has already been sent to an external system outside the JVM.

## 7. Overall Deadline vs. Per-Dependency Timeout

The timeout of `invokeAll`/`invokeAny` bounds **the caller's waiting time at the batch level**. It does not automatically configure socket read timeouts, query timeouts, or processing limits of external services.

For example, a request has a 2-second deadline, but a Callable waits up to 60 seconds for a network response and does not respond to interruption. After 2 seconds, `invokeAny` throws `TimeoutException` or `invokeAll` returns cancelled Futures; the worker may still occupy a thread for many seconds afterward. When this happens frequently, the thread pool becomes exhausted even though the caller code thinks it has "timed out".

The design should include:
1. A deadline for the entire request/batch.
2. Timeouts for each I/O operation aligned with **the remaining time**.
3. Cooperative cancellation at blocking boundaries.
4. A policy for late-arriving results and side effects that have already occurred.
5. Metrics for execution time, pending queue, rejections, timeouts, and stuck workers.

When multiple steps share a single deadline, avoid naively adding the full timeout to each step. `System.nanoTime()` is useful for measuring relative elapsed time instead of using a wall clock that can be adjusted; computing and propagating the remaining budget should be standardized according to application logic.

## 8. Exception Scenarios and Cleanup

| Event | API Representation | Caller Action |
| --- | --- | --- |
| `invokeAll` expires | List of Futures, some cancelled | Collect successful results, record timed-out ones |
| `invokeAll` has a failed task | `get()` on the failed Future throws `ExecutionException` | Inspect `getCause()`, do not conflate with timeout |
| `invokeAny` expires | `TimeoutException` | Report deadline exceeded, noting tasks may not have stopped immediately |
| `invokeAny` has no successful task | `ExecutionException` | Record failure, consider an appropriate business fallback |
| Caller is interrupted | `InterruptedException` | Propagate or restore the interrupt flag and exit |
| Executor rejects task | Usually `RejectedExecutionException` per handler | Admission control/backpressure, load handling |
| Task was cancelled but wrote data | Future does not roll back data | Idempotency key, verify external state |

`shutdown()` only stops accepting new tasks and lets already-accepted tasks finish; `shutdownNow()` attempts to interrupt running workers and returns waiting tasks, but does not guarantee immediate termination. Do not create a new executor per batch and abandon it; manage pool lifecycle and cleanup when the application shuts down.

## 9. When Should You Choose Another Tool?

`invokeAll` only returns results after all tasks have finished or the deadline has passed. If you want to process **each result as soon as any task completes**, `ExecutorCompletionService` provides `take()` and `poll(timeout, unit)`, though the caller must track Futures itself and cancel remaining tasks at the right time.

If non-blocking coordination is needed, `CompletableFuture` is another option. However, `CompletableFuture.anyOf(...)` completes when **any** future completes (including with an error), which is not equivalent to `invokeAny`'s "one success" semantics. `allOf(...)` also does not automatically provide timed `invokeAll`'s behavior of cancelling incomplete tasks. Timeouts, errors, and cancellation must be designed separately.

For long-running tasks or tasks that must survive JVM restarts, a durable queue/job store is more suitable than purely in-memory Future operations.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking timed `invokeAll` throws `TimeoutException` | Incorrect API handling | Read the list and classify cancelled Futures |
| Thinking each task gets a full `timeout` | Batch deadline is misunderstood | Use a shared budget |
| Treating `isDone() == true` as success | Failed or cancelled tasks are also done | Check `isCancelled()` and `get()` |
| Assuming `invokeAny` picks the first task | Defeats the purpose of picking one success | Do not rely on input order |
| Using `invokeAny` for multiple non-idempotent writes | May cause side effects multiple times | Use idempotency and coordination |
| Thinking `cancel(true)` forcibly stops Java code | Worker keeps running and holding resources | Support interruption and I/O timeouts |
| Swallowing `InterruptedException` | Fails to react to cancellation | Propagate or restore the flag and exit |
| Discarding successful results on partial timeout | Loss of useful information | Aggregate partial results by ID |
| Not shutting down the executor | Thread/resource leaks | Manage lifecycle and controlled shutdown |
| Using an unbounded queue despite batch timeouts | Tasks keep piling up with high latency | Bounded queue and admission control |

## 11. Self-Check Questions

**1. Does `invokeAll(tasks, 1, SECONDS)` throw `TimeoutException` when it expires?** No. It returns the list of Futures while requesting cancellation of incomplete tasks.

**2. Can a Future from timed `invokeAll` be not done when the method returns normally?** No. Every Future is done, though it may be cancelled or failed.

**3. Does `invokeAny` return the result of the first failed task?** No. It requires one successful task; when all tasks fail, it throws `ExecutionException`.

**4. When timed `invokeAny` expires, do we get a Future list to retrieve partial results?** No. The API only returns a `T` value on success or throws an exception. If you need per-task details, use a separate Future management mechanism.

**5. Does a successful `cancel(true)` guarantee the worker has stopped writing data?** No. Interruption is cooperative; side effects may have already occurred or may still continue.

**6. Why should I/O tasks have their own timeouts?** Because the batch timeout only bounds the caller's wait, and does not automatically set timeouts for sockets or resources outside the JVM.

**7. After `invokeAll` returns, how do you match each Future with the original request?** Use the index in the list: Futures are returned in the order of the input collection.

## References

- [ExecutorService — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Future — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Callable — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html)
- [CountDownLatch — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [ExecutorCompletionService — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html)
