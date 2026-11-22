# Running Multiple Callables and Retrieving Results in Completion Order

## 1. Practical Exercise and Expected Outcome

You need to run multiple independent tasks in Java, where each task returns a value via `Callable<T>`. The completion times of the tasks vary: some tasks are slow due to I/O, while others finish very quickly. The requirement is to **receive and process each result as soon as its task completes**, without getting blocked waiting for a task that was submitted earlier but takes longer to run.

After this exercise, you will be able to:

- Distinguish between **submission order**, **start order**, **completion order**, and **result consumption order**.
- Explain why iterating `Future.get()` over a submission list fails to meet the "first completed, first returned" requirement.
- Use `ExecutorCompletionService<T>`, `submit()`, `take()` / `poll(timeout)`, and `Future.get()` to retrieve results in completion order.
- Handle task failures, timeouts, cancellation, task counts, backpressure, and shutdown without losing results or hanging the consumer thread.
- Write a standalone Java 17+ program with deterministic output that can be tested reliably.

**Scope:** General Java concurrency (`java.util.concurrent`). Do not use Spring or framework-specific concurrency mechanisms.

## 2. Problem Statement

Suppose an application needs to aggregate three independent computations:

| Task | Assumed Input | Result | Characteristic |
| --- | --- | --- | --- |
| A | Process dataset A | `A` | Completes late |
| B | Process dataset B | `B` | Completes earliest |
| C | Process dataset C | `C` | Completes after B, before A |

The application submits them in the order **A → B → C**, but wants to read the results in the order **B → C → A** when that is the actual completion order.

Acceptance criteria:

1. Use at least three `Callable<String>` instances on a single `ExecutorService`.
2. Print/consume each result **as soon as the completion queue returns it**, without waiting for A just because A was submitted first.
3. Collect all three results (or explicitly handle failure cases) without silently ignoring task errors.
4. Each wait must be bounded by a timeout or governed by an overall deadline strategy; upon completion, the executor must be shut down and released.
5. Include a test or demo that verifies completion order **without relying on `Thread.sleep()` to guarantee scheduling**.

This is a question of **when results are collected**, not a guarantee that B will always be faster than A on every machine. In the demo, `CountDownLatch` is used to produce the exact B → C → A order deterministically so the API can be verified.

## 3. Why Using List<Future> Easily Delays Results

A common approach:

```java
List<Future<String>> futures = new ArrayList<>();
futures.add(executor.submit(taskA));
futures.add(executor.submit(taskB));
futures.add(executor.submit(taskC));

for (Future<String> future : futures) {
    System.out.println(future.get());
}
```

This is an **illustrative snippet**; in a real program you must declare `executor`, the three callables, imports, and manage the executor lifecycle.

Each `submit` returns a `Future`, but **`Future.get()` waits for that specific future**. The loop iterates through the list in A, B, C order, so if A takes 10 seconds, the consumer thread waits for A first, even if B and C have already finished. This creates **head-of-line blocking** on the result-consumption side.

`Future.isDone()` can be used to check the status of each future, but manually polling in a loop increases complexity, wastes CPU, and makes race conditions between polls hard to manage. `Future.get(timeout)` only applies a timeout to one specific future; it **does not reorder** iteration over the list.

We need a mechanism that notifies the consumer thread whenever “**any task has just completed**”.

## 4. Solution: ExecutorCompletionService

`ExecutorCompletionService<V>` implements `CompletionService<V>`, combining:

- An **executor** to run the submitted tasks.
- A **completion queue** to hold `Future<V>` instances that have completed and are ready to be retrieved.

Processing flow:

```text
Coordinator thread
   submit A ─┐
   submit B ─┼────> ExecutorService (worker threads)
   submit C ─┘              │
                            ├─ B finishes ──> completion queue ─┐
                            ├─ C finishes ──> completion queue ─┼─> take()/poll()
                            └─ A finishes ──> completion queue ─┘

Result-consuming thread:
   Future B → get() → process B
   Future C → get() → process C
   Future A → get() → process A
```

`completion.submit(callable)` submits the task and returns a `Future<V>` that you can keep if you need to cancel it or map it to an ID. When the task completes, its future is placed onto the completion queue.

- `completion.take()`: **blocks** until a completed future is available.
- `completion.poll()`: retrieves immediately if one is available, or returns `null` if none is ready.
- `completion.poll(timeout, unit)`: waits up to the specified timeout, returning `null` if the timeout elapses.
- `completedFuture.get()`: retrieves the value or exception of an **already-completed future**, so it normally does not wait for the task's computation anymore. If the task failed, `get()` throws `ExecutionException`; if it was cancelled, it throws `CancellationException`.

**Important:** “Completed” includes success, failure, and cancellation. The completion service returns futures in **the order they are placed onto the completion queue**, which typically corresponds to the order tasks finish; it does not promise a deterministic order when multiple tasks finish nearly simultaneously. Tests must not assert an arbitrary order without coordinating execution.

The completion service **does not create its own worker threads**, does not increase throughput capacity, and does not impose timeouts on task execution. You own and must manage the underlying `ExecutorService`.

## 5. Java 17+ Solution: Deterministic B, C, A Order

The example below uses three independent gate latches: A, B, and C all start and wait together; then `main` lets B finish and retrieves B's result; next it lets C finish and retrieves C; finally it lets A finish and retrieves A.

Save the entire code to **`CompletionOrderDemo.java`**:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CompletionService;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CompletionOrderDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(3);
        CompletionService<String> completed =
                new ExecutorCompletionService<>(executor);

        CountDownLatch ready = new CountDownLatch(3);
        CountDownLatch allowA = new CountDownLatch(1);
        CountDownLatch allowB = new CountDownLatch(1);
        CountDownLatch allowC = new CountDownLatch(1);

        try {
            // Submission order: A, B, C.
            completed.submit(task("A", ready, allowA));
            completed.submit(task("B", ready, allowB));
            completed.submit(task("C", ready, allowC));

            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new TimeoutException("Not all tasks started");
            }

            allowB.countDown();
            System.out.println("completed: " + nextResult(completed));

            allowC.countDown();
            System.out.println("completed: " + nextResult(completed));

            allowA.countDown();
            System.out.println("completed: " + nextResult(completed));
        } finally {
            // Open all gates even if main throws an exception.
            allowA.countDown();
            allowB.countDown();
            allowC.countDown();
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static Callable<String> task(
            String id, CountDownLatch ready, CountDownLatch allowFinish) {
        return () -> {
            ready.countDown();
            if (!allowFinish.await(5, TimeUnit.SECONDS)) {
                throw new TimeoutException("Gate timeout: " + id);
            }
            return id;
        };
    }

    private static String nextResult(
            CompletionService<String> completed) throws Exception {
        Future<String> future = completed.poll(5, TimeUnit.SECONDS);
        if (future == null) {
            throw new TimeoutException("No task completed in time");
        }
        return future.get();
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac CompletionOrderDemo.java
java CompletionOrderDemo
```

Expected output on normal execution:

```text
completed: B
completed: C
completed: A
```

### Why Is This Output Reliable?

1. The pool has three workers, enough for all three tasks to pass `ready.countDown()` and wait at their gates; `main` waits until all are ready before opening any gate.
2. When `allowB` opens, only task B is allowed to return its result; A and C remain blocked at their own gates. `poll()` retrieves B.
3. `main` **waits for and prints B** before opening `allowC`, so the next completion is C; the same applies to A.
4. `Future.get()` returns the computed `String` or propagates any exception. There are no fragile assumptions like “sleeping 100 ms means the task is definitely done”.

Because the gates are only used to produce a deterministic execution schedule for the demo, production code **does not need** to inject three latches into callables. When running real work, workers finish naturally as their computation or I/O completes, and the completion queue automatically reflects the order in which they finish. There is no guarantee of B, C, A in uncoordinated runs.

`shutdownNow()` in `finally` cleans up the demo and issues a best-effort interrupt; it does not guarantee immediate termination of all types of I/O. In a real application, you should call `shutdown()` first, then `awaitTermination(timeout)`, and `shutdownNow()` if needed, while also managing deadlines and unfinished tasks.

## 6. Real-World Application Pattern: Submit N Tasks, Collect N Completions

When you do not need to orchestrate a specific order, the general pattern is:

```java
ExecutorService executor = /* appropriately configured executor */;
CompletionService<Result> completion =
        new ExecutorCompletionService<>(executor);

int submitted = 0;
for (Callable<Result> task : tasks) {
    completion.submit(task);
    submitted++;
}

for (int i = 0; i < submitted; i++) {
    Future<Result> done = completion.take();
    try {
        Result result = done.get();
        handle(result);
    } catch (ExecutionException failure) {
        handleFailure(failure.getCause());
    } catch (CancellationException cancelled) {
        handleCancellation();
    }
}
```

This is an **integration pattern**, not a standalone Java program: `Result`, `tasks`, `handle(...)`, `handleFailure(...)`, and `handleCancellation()` are domain types/methods you must define; `ExecutionException`, `CancellationException`, and concurrency classes must be imported.

Distinguish between the two counters:

- `submitted`: the number of tasks **successfully submitted**. If `submit` is rejected because the executor is full, `RejectedExecutionException` may be thrown immediately and that task **must not be counted as submitted**.
- `received` or loop variable `i`: the number of **completed futures retrieved**, including those corresponding to failed or cancelled tasks. If you want to know the number of successes, use a separate counter.

If every task succeeds, the loop receives exactly one result per task. If there are failures, you still need to drain the remaining completions or enforce an explicit stop/cancellation policy. Do not break out of the loop as soon as you see one exception and leave the other tasks running unattended.

If you need to map each result back to its input task, return an object carrying **`taskId`**:

```java
record TaskResult(String taskId, long value) {}

Callable<TaskResult> task = () -> {
    long value = calculateValue();
    return new TaskResult("task-42", value);
};
```

`calculateValue()` is just a placeholder for your business logic in this snippet. On success, you know the ID via `result.taskId()`. On failure, since you do not receive a `TaskResult`, you can wrap the callable to throw an exception carrying the ID, or maintain a map from the `Future` returned by `submit()` to the ID. Never rely on a completion's position in the queue to infer whether it was task A, B, or C.

## 7. Timeouts: Never Let the Consumer Thread Wait Forever

`take()` waits indefinitely if no future enters the completion queue. When production code has a deadline, use `poll(timeout, unit)` and check for `null`:

```java
Future<Result> done = completion.poll(2, TimeUnit.SECONDS);
if (done == null) {
    // No task completed within the wait interval.
    // Decide whether to cancel, report a timeout, retry in a controlled way, or continue waiting.
} else {
    Result value = done.get();
}
```

This example waits at most two seconds for **the next completion**, without bounding the total time for all N completions. If each iteration allows up to 2 seconds, N iterations can spend nearly `2 × N` seconds just waiting. Enforce an **overall deadline** when an interface or operation has a fixed time budget:

```java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);

for (int i = 0; i < submitted; i++) {
    long remaining = deadline - System.nanoTime();
    if (remaining <= 0) {
        throw new TimeoutException("Overall deadline exceeded");
    }
    Future<Result> done =
            completion.poll(remaining, TimeUnit.NANOSECONDS);
    if (done == null) {
        throw new TimeoutException("Overall deadline exceeded");
    }
    consume(done.get());
}
```

This snippet plugs into a flow that already declares `submitted`, `completion`, `Result`, and `consume`. Computing with `System.nanoTime()` measures elapsed time (unaffected by wall-clock adjustments). For extremely long deadlines or overflow edge cases, design the deadline arithmetic carefully; the 5-second example is for illustration only.

**Note:** The `poll()` timeout only limits **how long the consumer thread waits**. It does not stop the running callable itself; you need separate timeouts for I/O/backend calls, or `Future.cancel(true)` if the task supports interruption and your policy allows it.

When `InterruptedException` is thrown by a blocking `poll`/`take`/`get`, do not swallow it and keep looping indefinitely. If your layer cannot propagate it, consider restoring the interrupt flag via `Thread.currentThread().interrupt()`, cleaning up, and returning according to your contract.

## 8. Failures, Cancellation, and Handling Completions Properly

A `Future` is placed onto the completion queue when a task **terminates**, including:

| State | `future.get()` | How to Handle |
| --- | --- | --- |
| Succeeded | Returns result | Process the data immediately |
| Callable threw an exception | Throws `ExecutionException` | Read `getCause()`, log/record the failure per task |
| Future was cancelled | Throws `CancellationException` | Record cancellation according to your contract |
| Consumer thread interrupted while waiting | May throw `InterruptedException` in `take`/`poll`/`get` | Stop or propagate the interrupt and clean up |

A `submit(callable)` call can be **rejected immediately** by the executor before the task is accepted. This `RejectedExecutionException` does not produce a completion to wait for in the N-task loop. Increment your counter only after submission succeeds.

**Do not blindly retry every failure immediately.** If multiple backends are slow at the same time, retrying without backoff, jitter, or a retry budget can saturate the executor and amplify load. Define which errors are retryable, the maximum number of attempts, and the overall deadline. If the system uses a fail-fast policy, cancel the remaining futures and keep track of resources in use; cancellation is only a cooperative request and does not guarantee that I/O tasks stop immediately.

**Do not treat the completion queue as an unbounded result queue independent of resources:** workers still consume CPU, memory, sockets, and threads. If you submit a million tasks to `Executors.newFixedThreadPool(10)`, the default execution queue can grow very large even though only ten tasks are running at a time. Bound your input/batches or use an executor with a bounded queue and a backpressure policy.

## 9. Controlling the Number of In-Flight Tasks

The `submit all → wait for all` pattern works fine when the task list is small. For very large or unbounded streams, limit the number of tasks whose results have not yet been consumed: for example, at most 20 tasks submitted without a collected completion.

Sliding window approach:

1. Submit up to `maxInFlight` initial tasks.
2. Retrieve the next completion using `poll(timeout)`.
3. Process the result or failure; decrement the in-flight counter.
4. If more input remains, submit one more task and increment the counter.
5. Repeat until input is exhausted **and** in-flight reaches 0.

This bounds both the task intake rate and the memory retained by pending futures. However, the completion service **does not replace** connection limits, request concurrency limits, or downstream memory limits; you still need to configure the executor and downstream resources appropriately.

When you need a bounded executor, you can use `ThreadPoolExecutor` with an `ArrayBlockingQueue` and `AbortPolicy` to reject work when capacity is exhausted. If you choose `CallerRunsPolicy`, a rejected task may run directly on the submitting thread, slowing down the producer and changing scheduling characteristics; make sure you understand this behavior beforehand.

**API note:** If you construct `ExecutorCompletionService` with a custom completion queue, the JDK documentation assumes that queue can accept every completed future. Using a bounded completion queue can cause enqueuing a completed future to fail, resulting in lost notifications. Limit in-flight tasks at the submission/executor layer rather than shrinking the completion queue arbitrarily.

## 10. Comparing with invokeAll, invokeAny, and CompletableFuture

| API | Meaning | Best Used When |
| --- | --- | --- |
| `ExecutorService.submit` + `List<Future>` | Submits tasks individually and keeps futures in the order you stored them | You need per-task future control; iterating `get()` over the list collects in submission order |
| `ExecutorService.invokeAll` | Waits for all tasks to finish (or time out), returning a list of futures **in the same order as the input collection** | You want to process the entire batch after all tasks finish |
| `ExecutorService.invokeAny` | Returns the result of **one task that completed successfully**; may cancel the others | You only need one successful answer, not all answers |
| `ExecutorCompletionService` | Queues completed futures so a consumer can retrieve them as they finish | You need to process every completion in arrival order |
| `CompletableFuture.anyOf` | A future that completes with the first completion in the group, even if exceptional | You only need the first event; does not iterate to collect all results |
| `CompletableFuture.allOf` | A future representing the completion of the entire group; does not return results in completion order | You want to wait for the whole group, then read the results |
| `CompletableFuture.whenComplete` / `thenAccept` | Registers a callback to run when each stage completes | You use a callback-driven design and do not want a dedicated thread waiting on `take()` |

**`invokeAll()` does not solve this problem:** it only returns after all tasks in the batch have finished, and the returned list matches the input order. `invokeAny()` stops at a single successful result and does not provide all results in completion order.

With `CompletableFuture`, each task's callback can process its result as soon as its stage completes, though default callbacks may run on either the completing thread or the registering thread depending on state. Avoid putting heavy blocking work inside callbacks without considering the executor or using the `Async` variants with an explicit executor. If you need callback processing serialized in completion order, you must add appropriate serialization/queueing; concurrent callbacks **do not guarantee log order**.

## 11. Testing the Exercise with CountDownLatch

Real-world task completion order depends on scheduling and I/O. A test written like “A sleeps 300 ms, B sleeps 100 ms, C sleeps 200 ms, therefore we always get B–C–A” is **unreliable** if machine load or JVM scheduling changes.

Use the gates from the main example to verify:

- **Submission order:** A, B, C.
- **Allowed completion order:** B, C, A.
- **Expected consumption order:** B, C, A.
- **Element count:** exactly 3, with no duplicates or omissions.
- **No exceptions:** every `get()` succeeds and contains the expected task ID.

To test failure handling, replace callable B with one that throws `IllegalStateException("B failed")` after its gate opens. The completion corresponding to B still arrives first, but `get()` throws `ExecutionException` with the appropriate cause; your code must handle it rather than assuming every completion carries a normal result.

Testing timeouts: leave gate A closed and call `poll(100, MILLISECONDS)` when no other completions are pending; it must return `null`. Then open the gate in `finally` and clean up the executor. If your test pool only has two workers while three tasks are waiting on the “ready” latch, the test will self-deadlock; ensure the worker count is sufficient or design the gates accordingly.

A **production-grade test** should also cover consumer interruption, cancellation, rejected submissions, a task legitimately returning `null`, empty input, no thread leaks, and overall deadlines. A `Callable<String>` can return `null`; `Future.get()` returns `null` in that case, which **does not mean `poll()` found no completion**. Only `poll()` returning `null` indicates that no future was available before the timeout.

## 12. Follow-Up Exercises You Can Try

### Exercise A — Collect Results and Failures While Continuing

Replace the three tasks with a list of five `Callable<Integer>` instances. One task throws an exception, and four return numbers. Collect all five **completions**; print the successful values in the order received, record the failure cause, and assert:

- `successes == 4`;
- `failures == 1`;
- `successes + failures == submitted`.

Do not assert a specific order unless you coordinate it with latches.

### Exercise B — Tracking an Overall Deadline

Allow a maximum total batch processing time of 3 seconds using `System.nanoTime()`. Compute the **remaining time** before each `poll`. When the deadline expires, report how many tasks completed and cancel unfinished futures according to policy; do not pass `poll(3, SECONDS)` fresh on every iteration while assuming the total maximum time is still 3 seconds.

### Exercise C — In-Flight Window

Suppose you have 100 requests but want at most 8 requests submitted and not yet collected at a time. Implement the sliding window from Section 9, measure `maxObservedInFlight`, and assert `maxObservedInFlight <= 8`. All 100 results or failures must be classified, even when the executor has a small queue limit. Clearly separate rejected-submission errors from callable execution errors.

### Exercise D — Return Results Immediately, but Store Report in Input Order

Give each task a `taskId` and an `inputIndex`. Process progress in completion order, but store each result in a structure indexed by `inputIndex` so you can produce a final report ordered A, B, C. **Consumption order** and **report presentation order** are two separate requirements that can be satisfied at the same time.

## 13. Common Pitfalls

- **Iterating `List<Future>` in submission order:** causes head-of-line blocking; use a completion queue when you need completion-order output.
- **Calling `get()` before `take()` on the first future:** inadvertently falls back to waiting for the slowest task.
- **Confusing completion with success:** failed or cancelled tasks are still completions; you must handle `ExecutionException` and `CancellationException`.
- **Unbounded waiting:** `take()` can block forever if a task never finishes or a notification never arrives; use deadlines where appropriate.
- **Counting rejected submissions:** causes the loop to wait for a completion that will never be produced for that task.
- **Submitting unbounded work:** the executor queue and retained futures can create memory pressure; use in-flight limits/backpressure.
- **Using `sleep` to prove order:** creates flaky, environment-dependent tests; use latches/barriers when you want deterministic scheduling.
- **Having more tasks wait on a gate than available workers:** causes the test to self-deadlock.
- **Forgetting to map back to the source task:** you know which result arrived first, but not which input it belongs to; attach a `taskId` or maintain a future map.
- **Forgetting to shut down the executor:** leaves threads alive after a test finishes or prevents the application from exiting.
- **Misusing a bounded completion queue:** completed futures may fail to enqueue; bound submissions upstream instead.
- **Mistaking `allOf`/`invokeAll` for completion order:** they wait for a group of tasks rather than streaming individual completions.

## 14. Self-Assessment Checklist

1. In what order did I submit the `Callable`s, and what event determines the order in which results are received?
2. Do I call `poll(timeout)` or `take()` before calling `get()` on the already-completed future?
3. Do I collect the exact number of completions for successfully submitted tasks and track successes, failures, and cancellations separately?
4. If a task never returns or throws an exception, does the consumer thread still exit cleanly and release resources?
5. Have I bounded in-flight tasks, handled rejections, and protected downstream resources for large inputs?
6. When a test requires a fixed order, did I coordinate it with synchronization primitives instead of guessing from sleep durations?
7. When a final report needs input order, did I attach an ID/index to each result instead of assuming the queue preserves submission order?

**Key takeaway:** `ExecutorCompletionService` solves the problem of **running multiple Callables and consuming each result in completion order**. Submission order does not dictate completion order; calling `Future.get()` over a list can block results that are already ready. Use `CompletionService.take()/poll()` to retrieve a completed future, then `get()` to extract its value or inspect its error, combined with appropriate deadlines, cancellation, and resource bounds.
