# ExecutorCompletionService Receiving Results in Completion Order in Java

When submitting multiple independent tasks to an `ExecutorService`, they may start, finish, fail, or be cancelled at different times. If the program collects the `Future` objects and calls `get()` one by one in **submission order**, it can get stuck on the first slow task even though tasks submitted later have already finished. `ExecutorCompletionService<V>` solves this exact problem of **collecting results in the order tasks complete and are placed into the completion queue**, rather than submission order.

For example: three queries A, B, and C are submitted in the order A→B→C, but B finishes first, C finishes second, and A finishes last. With `ExecutorCompletionService`, a consumer can retrieve results B, C, and A and process each one as soon as it is ready. There is no need to wait for A before inspecting result B.

This Knowledge article belongs to **Future & Scheduling in general Java Concurrency**. Its content covers the API model, comparing ways to use `Future`, deterministic-stdout Java 17+ examples, handling errors/cancellation/timeouts, choosing executor configurations, and operational considerations. Spring-specific integration APIs are out of scope.

## 1. The Head-of-Line Blocking Problem When Iterating Futures in Submission Order

A common approach is to submit multiple tasks and store the Futures in a list:

~~~java
List<Future<String>> futures = new ArrayList<>();
futures.add(executor.submit(taskA));
futures.add(executor.submit(taskB));
futures.add(executor.submit(taskC));

for (Future<String> future : futures) {
    System.out.println(future.get());
}
~~~

This is an **illustrative snippet**, assuming `executor` and the three `Callable<String>` instances already exist; the enclosing method must handle `InterruptedException` and `ExecutionException`.

The loop reads Futures in list order. When `taskA` is slow:

~~~text
Submit:         A --------> B --------> C
Actual finish:  B --------> C --------> A
get(list):      wait A................................
                [print A] [print B] [print C]
~~~

Tasks B and C may have already finished, yet their results have not been consumed. This is **head-of-line blocking at the result-processing layer**: the caller imposes an unnecessary consumption order on itself. It is not that the executor forces tasks to run in that order.

If the problem requires processing results as soon as each task completes (independent fan-out/fan-in), a completion service is the right tool. If results must be output in their **exact original position** according to the request, submission order may still be a valid requirement and should be sorted at the presentation layer.

## 2. What Is ExecutorCompletionService?

`java.util.concurrent.ExecutorCompletionService<V>` implements the `CompletionService<V>` interface. It combines:

1. **An existing Executor:** responsible for executing tasks, defining the number of workers, queue, rejection policy, lifecycle, and resources.
2. **A completion queue:** holds the `Future<V>` instances of tasks that have finished according to the completion service protocol.
3. **Submission and result-retrieval APIs:** `submit(...)` submits work; `take()` or `poll()` retrieves a completed Future from the queue.

Creating an instance:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(3);
CompletionService<String> completion =
        new ExecutorCompletionService<>(executor);
~~~

This is an illustrative snippet; it requires importing `ExecutorService`, `Executors`, `CompletionService`, and `ExecutorCompletionService`. `ExecutorCompletionService` does not create a hidden worker pool. It uses the executor passed to it.

### 2.1 Data Flow Diagram

~~~text
Producer / submitter
       |
       | submit(callable A)
       | submit(callable B)
       | submit(callable C)
       v
+----------------------------+
| Executor / worker threads  |
|    A: slow                 |
|    B: fast                 |
|    C: medium               |
+----------------------------+
       |
       | each task completes -> completed Future
       v
+----------------------------+
| Completion queue           |
|  [Future(B)] [Future(C)]   |
|                   ... [A]  |
+----------------------------+
       |
       | take()/poll()
       v
Consumer -> Future.get() -> value or exception
~~~

**Do not confuse this:** the completion queue contains **completed Futures**, not necessarily successful values. A task that throws an exception still produces a completed Future for the consumer to retrieve; business/execution errors are discovered when calling `get()`.

Also do not confuse the completion queue with the **work queue of `ThreadPoolExecutor`**. The work queue holds tasks that have not yet been picked up by a worker to run; the completion queue holds Futures that have finished, waiting for the consumer to retrieve them. The two queues have different roles and resource limits.

## 3. Core API and Blocking Contract

| API | Meaning | Does it wait? |
| --- | --- | --- |
| `submit(Callable<V>)` | Submits a task returning a value or throwing an exception, returning a `Future<V>` used to track/cancel that specific task. | Submission itself does not wait for completion; may be rejected by the executor. |
| `submit(Runnable, V result)` | Submits a Runnable, using the predefined result if the Runnable completes normally. | Does not wait for completion. |
| `take()` | Retrieves and removes from the completion queue **one completed Future**. | **Waits indefinitely** if the queue has no elements yet, unless interrupted. |
| `poll()` | Attempts to retrieve a completed Future immediately. | Does not wait; returns `null` if the queue is currently empty. |
| `poll(timeout, unit)` | Waits up to a bounded time to retrieve a completed Future. | Waits until an element is available or the deadline expires; returns `null` on timeout. |
| `Future.get()` | Retrieves the value or exception of the retrieved Future. | For a completed Future from the queue, normally does not need to wait for the task to run; still must handle errors/cancellation/interruption. |
| `Future.cancel(true)` | Requests cancellation of a task via the saved Future. | Not a synchronous kill command; outcome/timing still depends on the task and executor. |

`take()` and timed `poll()` can throw `InterruptedException`. `Future.get()` can throw `ExecutionException` if the callable failed, or `CancellationException` if the Future was cancelled; these must be distinguished from `InterruptedException` of the waiting consumer.

### 3.1 Returns Completions Only, No Submission-Order Guarantee

If A finishes after B, B's Future normally appears in the completion queue before A's. However, when multiple tasks finish nearly simultaneously, there is **no global nanosecond/log-line ordering contract** for users to predict tie-breaking. The order the consumer observes is the order in which the Futures are enqueued for retrieval.

In particular, the scheduler may change execution order between runs. A program must never hard-assert that "B is always faster than A" when only using `Thread.sleep` to simulate speeds.

### 3.2 Does Not Automatically Know When the Entire Group Is Done

`CompletionService` **has no method** like `closeSubmissions()` or `takeAll()` that knows the exact number of tasks in a batch. The consumer must manage:

- How many tasks were **successfully submitted**;
- How many completions have been received;
- When to stop submitting or move on to a new batch;
- How to handle rejected, cancelled, or timed-out tasks, or a producer that stops midway.

The common pattern is to count `n` submissions and then call `take()` **exactly `n` times**, provided all tasks were accepted and will actually complete according to contract. If a callable blocks forever, `take()` can block forever; a timeout/cancellation policy is needed.

## 4. Java 17+ Example: Proving Results Are Received in Completion Order

To avoid scheduler nondeterminism, the example uses `CountDownLatch` as three gates. Main **submits in order A→B→C**, then opens gates B, C, and A one by one, receiving **one completion before opening the next gate**. This makes stdout deterministic without needing `sleep()`.

Create the file `CompletionOrderDemo.java`:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.CompletionService;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class CompletionOrderDemo {
    private static Callable<String> job(
            String name, CountDownLatch started, CountDownLatch gate) {
        return () -> {
            started.countDown();
            gate.await();
            return name;
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        CompletionService<String> cs = new ExecutorCompletionService<>(pool);
        CountDownLatch allStarted = new CountDownLatch(3);
        CountDownLatch a = new CountDownLatch(1);
        CountDownLatch b = new CountDownLatch(1);
        CountDownLatch c = new CountDownLatch(1);

        try {
            cs.submit(job("A", allStarted, a));
            cs.submit(job("B", allStarted, b));
            cs.submit(job("C", allStarted, c));
            allStarted.await();

            b.countDown();
            System.out.println("Completed: " + cs.take().get());

            c.countDown();
            System.out.println("Completed: " + cs.take().get());

            a.countDown();
            System.out.println("Completed: " + cs.take().get());
        } finally {
            a.countDown();
            b.countDown();
            c.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac CompletionOrderDemo.java
java CompletionOrderDemo
~~~

Normal output, with no external interruption:

~~~text
Completed: B
Completed: C
Completed: A
~~~

### 4.1 Why Can No Other Order Occur?

- The pool has **three workers**, so all three tasks can reach `allStarted.countDown()` and then wait on their own gate.
- `allStarted.await()` in main waits until all three tasks have reached that milestone.
- B is allowed to pass its gate first; A and C remain blocked. `cs.take()` can only receive completion B at this step.
- Only **after** main has retrieved B does it open gate C; A is still blocked, so the next completion is C.
- Similarly, gate A is opened last.
- `cs.take()` returns the completed Future; `get()` returns the value A/B/C. `finally` opens all gates in case of an error in main, then requests executor shutdown to avoid leaving workers waiting indefinitely in the example.

**`allStarted` and the gates are only for testing order:** real-world applications usually run independent I/O/CPU tasks and do not actively force completion order. The benefit is that the consumer can process *whichever task completes first*, without being forced to wait for the first task in the list.

## 5. Reading Results in Submission Order vs. Completion Order

Two different consumer styles:

### 5.1 Submission Order

~~~java
List<Future<Result>> futures = new ArrayList<>();
for (Request request : requests) {
    futures.add(executor.submit(() -> call(request)));
}

for (Future<Result> future : futures) {
    consume(future.get());
}
~~~

This is an **illustrative code snippet** requiring `Request`/`Result` classes, `call`, `consume`, and appropriate imports. A slow `get()` on the first Future will make the consumer wait, even if the second Future has already completed.

### 5.2 Completion Order

~~~java
CompletionService<Result> cs =
        new ExecutorCompletionService<>(executor);
int submitted = 0;

for (Request request : requests) {
    cs.submit(() -> call(request));
    submitted++;
}

for (int i = 0; i < submitted; i++) {
    Future<Result> completed = cs.take();
    consume(completed.get());
}
~~~

This is also an illustrative snippet. The difference is that the consumer waits on `cs.take()` to retrieve **any completed Future**, independent of which request was submitted first.

### 5.3 When Must Input Order Still Be Preserved?

For example, a result list displayed strictly by request line index. Completion order can still be used for **internal processing**, but it must carry an ID/index:

~~~java
record IndexedResult(int index, String value) {}

cs.submit(() -> new IndexedResult(index, query()));
~~~

This is a code snippet assuming `cs` has generic type `IndexedResult`, `index` is an effectively final local variable for each task, and `query()` exists. The consumer stores each result into its corresponding slot and then outputs them in order. **Completion order and presentation order are two separate decisions**.

## 6. Exceptions Do Not Suppress a Completed Future

A task may throw an exception, but that does not mean the completion service "only returns successes." `submit(Callable)` normally holds the exception inside the Future; the consumer retrieves the Future and only learns whether the task succeeded or failed when calling `get()`.

Create the file `CompletionFailureDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CompletionService;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class CompletionFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CompletionService<String> cs = new ExecutorCompletionService<>(pool);
        CountDownLatch allowSuccess = new CountDownLatch(1);

        try {
            cs.submit(() -> {
                throw new IllegalStateException("source unavailable");
            });
            cs.submit(() -> {
                allowSuccess.await();
                return "OK";
            });

            // Success task is still waiting on gate: failure should be received first.
            for (int i = 0; i < 2; i++) {
                Future<String> completed = cs.take();
                try {
                    System.out.println("Success: " + completed.get());
                } catch (ExecutionException e) {
                    System.out.println("Failure: "
                            + e.getCause().getClass().getSimpleName());
                    allowSuccess.countDown();
                }
            }
        } catch (ExecutionException e) {
            throw new AssertionError(e);
        } finally {
            allowSuccess.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Run on JDK 17+:

~~~bash
javac CompletionFailureDemo.java
java CompletionFailureDemo
~~~

Stdout in the normal case:

~~~text
Failure: IllegalStateException
Success: OK
~~~

**Why?** The succeeding task must wait on `allowSuccess`; the failing task needs no gate, so the failed Future appears first. The consumer gets the failed Future via `take()`, and `get()` throws `ExecutionException` containing `IllegalStateException` in `getCause()`. After catching the failure, main opens the gate for the remaining task.

Note: this is a teaching example focused on exceptions. In production code, there should be a **per-task error-handling branch**, rather than wrapping the entire loop in a single `ExecutionException` catch that skips remaining completions. If a task can get stuck indefinitely, `take()` can also wait forever, so a deadline/cancellation is needed.

### 6.1 Do Not Confuse Exceptions at `submit` and Exceptions at `get`

- **RejectedExecutionException** can occur right at `submit()` if the executor does not accept the task; in that case there is no corresponding accepted submission for the consumer to wait on.
- **ExecutionException** occurs at `get()` if the task ran and threw an exception.
- **CancellationException** occurs at `get()` when the Future is in the cancelled state.
- **InterruptedException** occurs on the consumer while waiting in `take()`/`get()`; this is the caller's cancellation path, not a callable error.

The counter of completions to wait for should only be incremented for **accepted** submissions. If you count input requests when some requests were rejected, the consumer may wait for a "completion that was never registered."

## 7. `take()`, `poll()`, and Timed `poll()`: Choosing by Waiting Requirements

`take()` is suitable when you know at least one task was accepted and is expected to complete within a finite time. It **blocks indefinitely** if the completion queue is empty; that can happen due to slow tasks, stuck tasks, or no tasks having been submitted.

`poll()` is used when the consumer must do other work immediately if no result is available yet:

~~~java
Future<String> ready = cs.poll();
if (ready != null) {
    use(ready.get());
}
~~~

This is an illustrative snippet, assuming `cs`/`use` exist and the method handles `InterruptedException` and `ExecutionException`.

`poll(timeout, unit)` supports bounding the wait time for a completion:

~~~java
Future<String> ready = cs.poll(200, TimeUnit.MILLISECONDS);
if (ready == null) {
    onTimeout();
} else {
    use(ready.get());
}
~~~

This is also an illustrative snippet. Returning `null` means **no completion was retrieved within the waiting window**, not proof that all tasks are dead or the executor is inactive. A timed poll **does not automatically cancel** still-running tasks.

### 7.1 Collector Timeout vs. Per-Task Timeout

A consumer may wait at most 2 seconds for **the entire batch**, while each task has a different processing time. If you call `poll(2, SECONDS)` **repeatedly for each result**, the total time can exceed 2 seconds many times over.

Choose an **overall deadline** and compute the remaining time on each poll. Do not reset the full timeout on every iteration.

### 7.2 Overall Deadline Illustration

~~~java
long deadline = System.nanoTime() + timeoutNanos;

for (int received = 0; received < submitted; received++) {
    long left = deadline - System.nanoTime();
    if (left <= 0L) {
        break;
    }
    Future<Result> result = cs.poll(left, TimeUnit.NANOSECONDS);
    if (result == null) {
        break;
    }
    handle(result.get());
}
~~~

This is an illustrative snippet, assuming `timeoutNanos` has a reasonable value, `submitted` is the number of accepted tasks, and `cs`/`handle` have the right types. `System.nanoTime()` is suitable for measuring elapsed time, not wall-clock timestamps. For deadlines near `long` limits, design the arithmetic to avoid overflow; here it only illustrates not granting the full timeout again on every iteration.

When the deadline expires, the program **must have a policy for handling the remaining tasks**: let them continue running and clean up later, request cancellation, or return partial results. Simply breaking out of the poll loop without knowing who owns the still-running tasks is a lifecycle bug.

## 8. First Successful Result: Getting the First Useful Outcome

A real-world scenario: send the same request to multiple data sources and need the **first successful result**, not the first submitted Future. `CompletionService` is useful because you can:

1. Submit all candidate tasks.
2. Receive the earliest completed Future.
3. If `get()` fails, continue waiting for another completion.
4. If it succeeds, save the result and **request cancellation of the remaining tasks**.
5. If all tasks fail, return a clearly defined failure.

**Never assume "first completion" is always "first success"**. A fast-failing task can arrive before any succeeding task.

### 8.1 Java 17+: Runnable First-Success Pattern

Create the file `FirstSuccessCompletionDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletionService;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class FirstSuccessCompletionDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        CompletionService<Integer> cs = new ExecutorCompletionService<>(pool);
        CountDownLatch blocker = new CountDownLatch(1);
        List<Future<Integer>> submitted = new ArrayList<>();

        try {
            submitted.add(cs.submit(() -> {
                throw new IllegalStateException("source A failed");
            }));
            submitted.add(cs.submit(() -> 42));
            submitted.add(cs.submit(() -> {
                blocker.await();
                return -1;
            }));

            Integer answer = null;
            int failures = 0;
            for (int i = 0; i < submitted.size(); i++) {
                Future<Integer> completed = cs.take();
                try {
                    answer = completed.get();
                    break;
                } catch (ExecutionException e) {
                    failures++;
                }
            }

            if (answer != null) {
                System.out.println("First success: " + answer);
            } else {
                System.out.println("All failed: " + failures);
            }
        } finally {
            for (Future<Integer> future : submitted) {
                future.cancel(true);
            }
            blocker.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Compile/run:

~~~bash
javac FirstSuccessCompletionDemo.java
java FirstSuccessCompletionDemo
~~~

Normal stdout:

~~~text
First success: 42
~~~

Here one task fails, one task returns 42, and one task is blocked on a latch. Regardless of whether the failing task or the 42 task completes first, the consumer continues past the error and stops as soon as it gets the value 42. `finally` requests cancellation of unfinished tasks and opens the blocker so threads do not leak.

**Limitations:** `future.cancel(true)` is a cancellation request; if a real task ignores interruption, it may keep running. In real systems, an overall deadline is needed so first-success does not wait indefinitely when no source succeeds, along with handling `CancellationException` if a candidate is cancelled externally.

If "first result" means **first response including errors**, do not loop looking for success. The business contract must decide.

## 9. Task Cancellation and the Completion Queue: Common Misconceptions

`ExecutorCompletionService.submit` returns a `Future<V>` for the caller to retain and proactively cancel. `Future.cancel(true)` can mark the Future as cancelled, and calling `get()` on that Future will throw `CancellationException`.

However, distinguish between:

- **Whether the Future is in the cancelled state**;
- **Whether the callable has actually stopped running**;
- **Whether the Future has been placed into the completion queue yet**.

These state transitions do not necessarily happen instantaneously at the same time. In particular, `ExecutorCompletionService` uses a wrapper to enqueue the completed task when the wrapper finishes; do not assume that calling `cancel()` on one thread immediately produces a completion ready via `take()` across all races/executor implementations.

When the caller wants to stop early and no longer consume every completion, keep the list of Futures it submitted for cancellation/cleanup, rather than relying on the number of elements in the completion queue to infer that all user tasks have stopped.

### 9.1 Handling `CancellationException` on `get`

~~~java
try {
    Result value = completed.get();
    consume(value);
} catch (CancellationException e) {
    recordCancelled();
} catch (ExecutionException e) {
    recordFailure(e.getCause());
}
~~~

This is an illustrative snippet inside a method that already handles `InterruptedException`; `Result` and the helpers are user-defined. `CancellationException` is unchecked and is **not** wrapped in `ExecutionException`. Do not use a generic `catch (Exception)` and label every case as "task failed"; cancellation has its own semantics.

### 9.2 Do Not Block the Consumer with Long-Running Processing

`take()` returns completions in queue order, but if the consumer spends a long time processing each result on the same thread, other completed Futures will pile up. The completion service does not automatically parallelize **consumer logic**. If heavy parsing/aggregation is needed, consider another pipeline or a separate executor, while controlling backpressure and ordering.

## 10. Default Completion Queue and Bounded Queue Risks

The common constructor:

~~~java
CompletionService<Result> cs =
        new ExecutorCompletionService<>(executor);
~~~

Uses a default `LinkedBlockingQueue` completion queue with no practical bound for a small batch of tasks; be mindful when submitting many tasks quickly if the consumer does not consume them.

There is an overload that accepts a caller-provided queue:

~~~java
new ExecutorCompletionService<Result>(executor, completionQueue);
~~~

However, **do not pass a small `ArrayBlockingQueue` by default** to "add backpressure." By the API contract, the completion queue is assumed to be **unbounded** with respect to enqueuing completed Futures; when a task finishes, the service uses `add` rather than blocking `put`. If a caller-provided queue has finite capacity and is full, adding the completed task can fail, making the completed Future **no longer retrievable through the completion service** even though the task finished running. This is a major failure mode.

If you truly need backpressure, do the following:

- **Limit the number of submitted/in-flight tasks**, for example using a `Semaphore` with clear ownership.
- Consume results fast enough or use appropriate consumer workers.
- Configure a bounded input queue on `ThreadPoolExecutor` with an intentional rejection policy, remembering this is the **work queue**, distinct from the completion queue.
- Do not arbitrarily replace the completion service's queue with a bounded queue.

**Distinguish the two resource-limit layers:** the work queue limits how many tasks are waiting to run; the in-flight limit caps how many tasks have not yet had their completions collected; the completion queue holds finished Futures. Limiting only the work queue does not guarantee completed results will be consumed fast enough.

## 11. Choosing an `ExecutorService` and Thread Pool

`ExecutorCompletionService` does not provide a new scheduling policy. It uses the executor passed to it:

| Executor | Characteristics | Suitability / Limitations |
| --- | --- | --- |
| `newFixedThreadPool(n)` | Up to `n` active workers; excess tasks are queued. | Easy to demonstrate and control concurrency, but the default work queue can grow practically unbounded. |
| Custom-configured `ThreadPoolExecutor` | Has core/max size, work queue, thread factory, rejection policy. | Suitable when explicit concurrency, queue, and saturation policy limits are needed. |
| `newSingleThreadExecutor()` | One worker executes tasks sequentially from the queue. | Completion order usually matches task execution order; no parallel fan-out benefit. |
| `newCachedThreadPool()` | Can create additional workers on demand. | Easy to exhaust resources when submitting many blocking tasks; load must be bounded. |
| `newVirtualThreadPerTaskExecutor()` (Java 21+) | One virtual thread per task. | Can suit I/O-waiting tasks, but external request/resource counts must be controlled; not a Java 17 API. |

The Java 17 examples in this article use a fixed pool to avoid depending on newer APIs. `newVirtualThreadPerTaskExecutor()` is only available in **Java 21+**; do not run that line in Java 17 examples.

### 11.1 The Pool Starvation Problem

If tasks in the same small pool **wait for completions of other tasks queued to run in that very same pool**, thread-pool starvation can occur. For example, if a pool has only one worker, task A submits B to the same pool and calls `Future.get()` waiting for B while occupying the worker. B has no worker to run on.

`CompletionService` does not cure task dependency deadlocks/starvation. It only collects completions. Designing the dependency graph and pool capacity remains the user's responsibility.

## 12. `CompletionService` and `ExecutorService.invokeAll()`

`ExecutorService.invokeAll(collection)` is useful when you need to run a set of tasks and wait for **the entire set** to finish or time out, then receive the Futures in **input iterator order**. `invokeAny(collection)` is useful when you want one early successful result and do not need to manage a completion loop manually.

| Requirement | Commonly Suitable API |
| --- | --- |
| Collect results **one by one as soon as they finish** | `ExecutorCompletionService.take()/poll()` |
| Run a set of tasks, wait for all results, return Futures in input order | `ExecutorService.invokeAll()` |
| Need one early successful result | `ExecutorService.invokeAny()` or `CompletionService` for custom policy |
| One task with one Future | `ExecutorService.submit()` + `Future.get()` |
| Compose asynchronous pipelines and transformations | `CompletableFuture` combinators |
| Complex nonblocking stream/event-driven results | `CompletableFuture` or a framework/reactive API with a suitable contract |

`invokeAll` does not return results in completion order just because the Futures may already be done. `CompletionService` is advantageous when the caller needs to process **partial results continuously**.

`invokeAny` includes logic to cancel remaining candidates per its API contract and returns one successful result; if that is the exact requirement, it can be simpler than writing the whole algorithm yourself. `CompletionService` fits when you need extra metrics, per-error handling, fallbacks, partial collection, or custom deadlines.

### 12.1 Compared to `CompletableFuture`

`CompletableFuture.anyOf(...)` completes when **any future** completes, including exceptional completion; it is not necessarily *first success*. Handling a stream of multiple completions with state, ordering, and backpressure requires designing an appropriate pipeline/callback structure.

`CompletionService` provides a **blocking pull-based** API: the consumer actively calls `take()`/`poll()`. `CompletableFuture` leans toward callbacks/composition. Choose based on orchestration needs and how the application handles waiting threads.

## 13. Memory Consistency and Thread Safety

Primitives in `java.util.concurrent` have documented **memory-consistency effects**. With `ExecutorService`, actions in a thread **prior to submitting** a task *happen-before* actions in the task; actions in the task *happen-before* actions **following the caller retrieving the result via `Future.get()`** according to contract.

This matters when a task computes a result or updates state before finishing. However:

- `CompletionService.take()` retrieves a completed Future; `get()` is the explicit way to obtain the value/error and establish the Future's memory-consistency contract.
- A mutable object passed into a task and then **mutated further by the caller while the task is running** can still race. Submitting does not freeze the object.
- A mutable result object published and then mutated unsynchronized by another worker/thread after completion still needs separate ownership/synchronization.
- Completion order does **not** make tasks sharing mutable state thread-safe.
- If tasks update the same invariant, `synchronized`, atomic aggregates, or concurrent data structures at the right scope are required; the completion service only manages result collection.

### 13.1 Pure Tasks and Immutable Snapshots

A simple way to reduce races is to pass immutable/snapshot inputs into each callable and return immutable/result values, then aggregate results on a single consumer thread. If results are processed across multiple consumer threads, protect the aggregated state according to contract.

## 14. Collecting Multiple Result Types and Attaching Metadata

Because the completion queue only returns a Future, the caller might not immediately know which request a result belongs to if the Callable returns only a bare value. **Wrap metadata into the result**:

~~~java
record QueryResult(String sourceId, long elapsedNanos, String value) {}

cs.submit(() -> {
    long start = System.nanoTime();
    String value = fetchFromSource();
    return new QueryResult(
            sourceId, System.nanoTime() - start, value);
});
~~~

This is an illustrative snippet, assuming `cs` accepts `QueryResult`, `sourceId` is effectively final, and `fetchFromSource` exists. With metadata, the consumer can:

- Log which source finished first;
- Store results by ID in a map;
- Compute per-source latency;
- Retry selectively;
- Aggregate partial successes/failures.

If a task fails before returning a result, the metadata inside the result does not exist. To associate errors with specific requests, you can maintain a `Future<?> → RequestId` mapping on the submitter side (using a thread-safe map if the collector runs on another thread), or have the callable return an `Outcome` containing success/error instead of throwing an exception. **Do not silently turn every failure into a success**; the contract must distinguish the two states.

### 14.1 Retrieval Order vs. Display Order

The consumer can process completion B before A to update progress, yet ultimately return the result list in A, B, C order. Separating **order of processing** from **order of presentation** optimizes early responsiveness while keeping the interface/contract intact.

## 15. Limiting Outstanding Tasks and Backpressure Design

A system with millions of requests cannot always submit all of them at once before starting to collect completions. It could hold too many Futures/callables, fill up the work queue, or cause memory pressure.

The **sliding window** model:

~~~text
MAX_IN_FLIGHT = 20
submit up to 20 tasks
each time a completion is received:
    handle outcome
    if more input remains, submit 1 more task
repeat until:
    all input is exhausted and all in-flight completions have been received
~~~

This is **pseudocode**, not standalone runnable Java. You must accurately manage the `inFlight` counter and the submit-failure/cancellation branches:

1. Increment `inFlight` after a **successful** submission.
2. When retrieving a completed Future via `take`/`poll` and determining its outcome, decrement `inFlight`.
3. Only submit more when input remains and the limit is not exceeded.
4. On cancellation/timeout, request cancellation of unfinished tasks and manage ownership/lifecycle.
5. If there are multiple producer or consumer threads, use synchronization to keep the in-flight count accurate.

Using a bounded completion queue is not necessary to control outstanding tasks; it is usually safer to let the **completion queue accept every completed Future**, while bounding the in-flight window **before submission**.

## 16. Interrupt, Cancel, and Shutdown Properly

A collector calling `take()` can be interrupted. If the method can declare `throws InterruptedException`, it is common to propagate it so the caller decides cancellation. In a top-level `Runnable.run()` worker, you can restore the interrupted status and exit:

~~~java
try {
    Future<Result> future = cs.take();
    consume(future.get());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Request cancellation of outstanding tasks and exit according to policy.
}
~~~

This is an illustrative code snippet; `Result` and helpers are assumed. If the consumer stops early, tasks still running must have an **owner** managing them. Do not discard all Future references and leave the executor running indefinitely with no shutdown policy.

### 16.1 Cleanup Pattern

~~~java
List<Future<Result>> futures = new ArrayList<>();
try {
    // Submit/collect according to the batch contract.
} finally {
    for (Future<Result> future : futures) {
        if (!future.isDone()) {
            future.cancel(true);
        }
    }
    executor.shutdownNow();
}
~~~

This is an illustrative code snippet. `shutdownNow()` is best effort and does not guarantee all tasks stop immediately; if the executor belongs to another component, **do not shut down a shared executor yourself**. Establish clear lifecycle ownership: whoever creates the pool is normally responsible for closing it, whereas a library receiving an executor from a caller should not secretly shut it down.

A task that ignores interruption or is stuck on I/O without a timeout may refuse to stop. Proper timeouts, resource-specific cancellation, and observability are required.

## 17. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Submitting via ECS but saving Futures and calling `get` in input-list order. | Still suffers head-of-line blocking. | Use `take()/poll()` on the completion service to collect in completion order. |
| Assuming completion order is always exact real-time order. | Flaky assertions under near-simultaneous completion. | Do not predict tie-breaks; use latches in tests requiring deterministic order. |
| Assuming a completed Future is a success. | `get()` can throw `ExecutionException`/`CancellationException`. | Handle the outcome of each Future. |
| Calling `take` more times than tasks were successfully submitted. | Can block forever waiting for a nonexistent completion. | Count accepted submissions; handle rejections. |
| Having no deadline when tasks can hang. | Collector blocks indefinitely. | Use timed `poll`/deadline/cancellation. |
| Calling timed `poll` N times with the full timeout. | Overall deadline is stretched N times. | Compute remaining time using a monotonic clock. |
| Using a bounded `completionQueue` that is too small. | Adding a completed Future can fail, making the completion unretrievable. | Limit in-flight tasks before submission; do not block completion enqueueing. |
| Forgetting to shut down an owned executor. | Non-daemon workers can keep the process alive; resource leak. | Manage lifecycle in `finally` with appropriate `shutdown`/`awaitTermination`. |
| Shutting down a caller-provided executor. | Disrupts shared subsystems. | Keep ownership clear; only cancel tasks you own. |
| Cancelling a Future and assuming the worker died immediately. | The task may not cooperate to stop. | Check lifecycle, timeouts, and cleanup policies. |
| Consumer processes results too slowly. | Completion queue and memory can grow. | Monitor backlog, limit in-flight tasks, or separate processing stages. |
| Using a single-worker pool where a task waits on another task in the same pool. | Pool starvation/deadlock. | Fix the dependency graph and executor configuration. |
| Tasks mutate the same plain map/list without synchronization. | Data race / broken invariants. | Use immutable input/output or appropriate synchronization. |
| Writing an overly complex loop just to get one successful result. | Hard-to-control error/cancellation branches. | Consider `invokeAny()` when the contract fits. |

## 18. Checklist for Applying in Real Applications

Before using `ExecutorCompletionService`, answer:

1. **Which results are needed first?** Do you need to receive any completion as soon as it finishes, or must you still output in input order?
2. **Are the tasks independent?** If tasks wait on each other, completion order does not solve dependencies.
3. **Who owns the executor?** Should it be shut down when the workflow ends?
4. **What is the task limit?** Is there a risk of submitting too many tasks or building up a backlog?
5. **How many completions will be collected?** Is the counter based on accepted submissions or expected input?
6. **How are failures handled?** Throw exception, partial success, retry, fail-fast, or first success?
7. **Cancellation of leftovers?** Are Future handles saved to request cancellation on timeout or once enough results are collected?
8. **Where is the deadline?** Per task, whole batch, or both? Is remaining time calculated?
9. **How is data published?** Do callables take immutable inputs, does `Future.get` publish results, and does aggregated state have proper thread safety?
10. **What performance metrics are observed?** Per-task latency, error rate, completion queue backlog, in-flight count, pool saturation, shutdown latency?
11. **Handling rejected tasks?** Do not wait for completions of tasks that were never accepted.
12. **Avoiding misuse of the completion queue for backpressure?** Limit in-flight tasks or the work queue at the right layer.
13. **Are deterministic-order tests written with latches?** Do not use sleep to guess finish order.

If the requirements above only amount to "wait for everything to finish and then process together," `invokeAll()` or `CompletableFuture.allOf()` may be cleaner. If you need **incremental processing as tasks complete**, ECS expresses that intent very clearly.

## 19. Self-Check Questions

**1.** Submit A, B, C; B and C finish before A. Why does iterating the Future list in submission order cause a slowdown?  
**Answer:** `get()` on A blocks the consumer even though results B and C are already complete; this is head-of-line blocking at the result layer.

**2.** Does `ExecutorCompletionService.take()` return a value or a Future?  
**Answer:** It returns a completed `Future<V>` and removes it from the completion queue; `get()` is needed to retrieve the value or exception.

**3.** Can a task that throws an exception be retrieved via `take`?  
**Answer:** Yes, an exceptionally completed Future is still enqueued; `get()` throws `ExecutionException`.

**4.** Does `poll()` returning `null` mean all tasks have failed?  
**Answer:** No. It only means the queue had no completed Future at the moment `poll` was called.

**5.** Does an expired `poll(timeout)` automatically cancel still-running tasks?  
**Answer:** No. A separate cancellation policy is required.

**6.** Why does completion order not guarantee tie-breaking when two tasks finish very close together?  
**Answer:** It reflects the order in which completions are enqueued by the runtime/scheduler; there is no global clock used to enforce a deterministic historical order.

**7.** A batch submits 10 tasks, and 2 are rejected. How many completions should the collector wait for?  
**Answer:** Wait only for the number of **accepted submissions**, not the two rejected tasks.

**8.** Should you pass `ArrayBlockingQueue(2)` as the completion queue for 100 tasks?  
**Answer:** No, unless you can guarantee the queue always has space when enqueueing: `add` can fail and lose the completed Future from the collection service.

**9.** If you want an overall 5-second deadline, why not call `poll(5s)` 100 times?  
**Answer:** It could wait many times 5 seconds in total; you must compute the remaining time from a shared deadline.

**10.** Does `Future.cancel(true)` guarantee a task stops immediately?  
**Answer:** No; it is a cancellation/interruption request, depending on task cooperation and blocking APIs.

**11.** When can `invokeAny()` be simpler than a custom ECS loop?  
**Answer:** When you only need one early successful result and do not need custom policies or partial progress.

**12.** If you want to display results A, B, C in input order while still processing them as soon as they finish, how should you do it?  
**Answer:** Include a request ID/index in the result, process in completion order, and then sort or place them into slots by input order.

**13.** Does a completion service automatically shut down the executor?  
**Answer:** No. Lifecycle belongs to the executor owner; shutdown/cleanup must be managed separately.

**14.** Does ECS make callables mutating the same plain list thread-safe?  
**Answer:** No. ECS only collects completions; shared state still needs ownership, synchronization, or an immutable design.

**15.** Why can a single-worker pool deadlock when task A waits on the Future of task B submitted to the same pool?  
**Answer:** The worker is occupied by A while B has no worker to run on; ECS does not resolve such dependency starvation.

**16.** When should you choose ECS over retrieving Futures directly?  
**Answer:** When you need to **collect and process results as each task completes**, without being locked into submission order.

**Remember:** `ExecutorCompletionService` organizes **task fan-out via an Executor** and **completed-Future fan-in via a completion queue**. `take()/poll()` lets the consumer process whichever task completes first, while `Future.get()` yields the value or exception. Correctness still requires counting accepted submissions, deadlines/cancellation/cleanup, thread safety of state, and bounding in-flight tasks; a completion service does not replace executor lifecycle, transactions, or backpressure policies.
