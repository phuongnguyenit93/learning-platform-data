# invokeAny() for the First Successful Result in Java

## 1. Problem and Learning Objectives

In certain concurrency problems, we have multiple independent ways to produce **an equivalent result**, and only **one** needs to complete successfully. For example: querying multiple replicas that read the same data, calling fallback sources, or running multiple algorithms for the same normalized output. Waiting for all sources to finish can be time-consuming if one source fails or is too slow.

`ExecutorService.invokeAny(Collection<? extends Callable<T>> tasks)` executes a group of `Callable<T>` tasks and **directly returns the result of one task that completes normally**. It does not wait for all tasks to succeed. When the method completes (either normally or via an exception), **unfinished** tasks are **requested to be cancelled**.

~~~java
String response = pool.invokeAny(List.of(
        () -> readReplica("east"),
        () -> readReplica("west"),
        () -> readReplica("backup")
));
~~~

This is an **illustrative snippet**, where `pool` is an `ExecutorService` and `readReplica` is an application method; the enclosing method must declare or handle checked exceptions. If one `Callable` returns data successfully, the caller receives that value without needing `Future.get()` for each source.

After this lesson, you will be able to:

- Accurately explain `invokeAny`, its two overloads, return type, and checked exceptions.
- Understand that "success" means **completing without throwing an exception**, even when the return value is `null`.
- Distinguish between a task failing first, a task succeeding first, all tasks failing, timing out, and the caller being interrupted.
- Differentiate `invokeAny` from `invokeAll`, `submit`/`Future.get`, `ExecutorCompletionService`, and `CompletableFuture.anyOf`.
- Use interruption/cancellation and cleanup properly, without confusing "cancelled" with "thread terminated".
- Design a pool with sufficient capacity, deadline-based timeouts, business result validation, idempotency, and fan-out limits.
- Run Java 17+ examples that orchestrate execution order using `CountDownLatch` instead of guessing scheduler behavior.

**Scope:** Java SE and the Executor Framework, independent of any external framework.

## 2. API and Outcome Branches

Two standard overloads:

~~~java
<T> T invokeAny(Collection<? extends Callable<T>> tasks)
        throws InterruptedException, ExecutionException;

<T> T invokeAny(
        Collection<? extends Callable<T>> tasks,
        long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
~~~

| Case | Behavior of `invokeAny` |
|---|---|
| A task completes normally | Returns the result `T` of **one** successful task |
| One task throws an exception while others may succeed | Continues waiting/competing; **does not fail immediately on the first error** |
| All tasks fail to complete normally | Throws `ExecutionException` |
| Timed overload expires before any success | Throws `TimeoutException` |
| Calling thread is interrupted while waiting | Throws `InterruptedException` |
| Empty collection | `IllegalArgumentException` |
| Collection or a task element to be executed is `null` | `NullPointerException` |
| Executor cannot accept the tasks | May throw `RejectedExecutionException` |

The Javadoc also specifies that **upon normal or exceptional return, tasks that have not completed are cancelled**. Cancellation does not mean rolling back side effects or killing threads.

A very important point: **success** is defined as **completion without throwing an exception**, not a result with `status=200` or business-valid data. If a `Callable` does `return null`, `return Optional.empty()`, or `return Response(503)` without throwing an exception, `invokeAny` may select it as a **technical success**.

### Is the Chosen Result Truly the "Fastest"?

In casual usage, `invokeAny` is often described as "getting the first successful result." However, you should not extrapolate this into the following guarantees:
- Picking the first element in the `List`.
- Picking the task **submitted** earliest.
- Picking the task with the shortest CPU time.
- Picking the replica with the newest/most accurate data.
- Starting **all** tasks at the exact same moment.
- Always returning the same winner when re-run with the same input.

The scheduler, number of workers, queue, completion times, and how the executor observes completions can all change the winner. If two results succeed almost simultaneously, **the selection order should not be tested against a fixed sequence**.

## 3. Simulating Competition Between Tasks

~~~text
Caller: invokeAny([A, B, C])
             |
             +--- A: throws IOException -----------------X (failure)
             |
             +--- B: processes then returns "OK" ------✓ (success)
             |
             +--- C: waiting on remote I/O ----------------?
                          |
               B succeeds, invokeAny picks "OK"
                          |
               Task C is unfinished → cancel requested
                          |
               Caller may receive "OK" even if C has not finished cleanup
~~~

**An early failure is not a reason to terminate the group**, unless all candidates have failed. An eligible success is the normal termination point.

Multiple sources are run via `Callable.call()`:
- `call()` returns a value ⇒ success.
- `call()` throws an exception ⇒ failed task.
- `call()` is interrupted and throws `InterruptedException` ⇒ task failed/terminated via exception, not a success.
- A task not yet scheduled or still running when another task wins ⇒ requested to cancel per the API.

A task may have already produced external effects (writing a file, sending a request, committing to a database) before being requested to cancel. Therefore, you should prefer **equivalent/idempotent read** sources for this kind of racing.

## 4. Standalone Java Example 1: Failure, Winner, and Interrupted Loser

This example uses 3 workers so it can process 3 candidates concurrently. One candidate throws an exception, one waits on a `CountDownLatch` that is never opened, and one returns `"OK"` **after the slow candidate has started**. The final outcome is controlled **without using sleep**.

Save the file **InvokeAnyFirstSuccessDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class InvokeAnyFirstSuccessDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);

        CountDownLatch slowStarted = new CountDownLatch(1);
        CountDownLatch slowFinished = new CountDownLatch(1);
        CountDownLatch closedGate = new CountDownLatch(1);
        AtomicBoolean slowInterrupted = new AtomicBoolean(false);

        Callable<String> fail = () -> {
            throw new IllegalStateException("replica failed");
        };

        Callable<String> slow = () -> {
            slowStarted.countDown();
            try {
                closedGate.await();
                return "SLOW";
            } catch (InterruptedException e) {
                slowInterrupted.set(true);
                Thread.currentThread().interrupt();
                throw e;
            } finally {
                slowFinished.countDown();
            }
        };

        Callable<String> winner = () -> {
            slowStarted.await();
            return "OK";
        };

        try {
            String result = pool.invokeAny(
                    List.of(fail, slow, winner));

            slowFinished.await();
            System.out.println("result=" + result);
            System.out.println(
                    "slowInterrupted=" + slowInterrupted.get());
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Pool did not terminate");
            }
        }
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac InvokeAnyFirstSuccessDemo.java
java InvokeAnyFirstSuccessDemo
~~~

Output under normal conditions, with no external interrupts:

~~~text
result=OK
slowInterrupted=true
~~~

**Why is the result deterministic?**

1. The `fail` task throws an exception. It is not chosen as the winner.
2. The `slow` task signals `slowStarted` and then waits on `closedGate`. This gate is **never opened** in the example, so `slow` cannot return `"SLOW"` on its own.
3. The `winner` task only returns `"OK"` after `slowStarted.await()` completes, ensuring `slow` has started.
4. When `"OK"` is selected, `invokeAny` requests cancellation of the waiting `slow` task; `CountDownLatch.await()` responds with `InterruptedException`, and `slow` sets `slowInterrupted=true`.
5. `slowFinished.countDown()` in `finally` ensures `main` can wait for `slow` to pass through cleanup before reading the flag.
6. `pool.shutdownNow()` is in `finally` to ensure executor cleanup in case of an unexpected error, not as the primary cause of the successful result.

The `slowFinished.await()` call is **an additional observation point for the test program**. Do not assume `invokeAny` automatically waits for all losers to finish cleanup before returning: it only requests cancellation if they have not completed.

## 5. What If All Tasks Fail?

Suppose we call three sources:

~~~java
Callable<String> a = () -> {
    throw new IllegalArgumentException("bad input");
};
Callable<String> b = () -> {
    throw new IllegalStateException("source unavailable");
};
Callable<String> c = () -> {
    throw new java.io.IOException("remote read failed");
};
~~~

These are **code snippets** used inside a method with appropriate imports. No task produces a normal result, so `invokeAny(List.of(a,b,c))` throws `ExecutionException`.

**Do not assume the cause of `ExecutionException` contains all errors from every task.** Depending on the implementation and completion order, the cause may be just one of the failures. If you need to report what failed for each source, use `invokeAll` and inspect the `Future`s, or use `ExecutorCompletionService` to collect outcomes individually.

### When a Task Succeeds by Returning `null`

A `Callable<String>` can `return null` normally. By contract, that is a success; `invokeAny` can return `null`. Similarly, `Optional.empty()` or a `Response` object with `ok=false` is still considered a normal completion.

If such a result is **unusable**, validate **inside the `Callable`** before returning, or write your own coordinator to select based on a business predicate. Do not delegate validation responsibility to `invokeAny` when it has no API accepting a predicate.

## 6. Standalone Java Example 2: All Tasks Fail, but `null` Counts as Success

Save the file **InvokeAnyFailureCasesDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class InvokeAnyFailureCasesDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Callable<String>> errors = List.of(
                    () -> {
                        throw new IllegalArgumentException("A");
                    },
                    () -> {
                        throw new IllegalStateException("B");
                    }
            );

            boolean allFailed = false;
            try {
                pool.invokeAny(errors);
            } catch (ExecutionException e) {
                allFailed = true;
            }
            System.out.println("allFailed=" + allFailed);

            String result = pool.invokeAny(
                    List.<Callable<String>>of(() -> null));
            System.out.println("nullIsSuccess=" + (result == null));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac InvokeAnyFailureCasesDemo.java
java InvokeAnyFailureCasesDemo
~~~

Output:

~~~text
allFailed=true
nullIsSuccess=true
~~~

In the first call, both tasks throw; there is no normal completion, so `ExecutionException` is thrown. In the second call, the `Callable` returns `null` without throwing, so `invokeAny` returns `null`. The test does not print `e.getCause()` because you should not rely on exception ordering when multiple tasks fail together.

### Validating Data in the Right Place

~~~java
Callable<String> checked = () -> {
    String data = fetchFromReplica();
    if (data == null || data.isBlank()) {
        throw new IllegalStateException("no usable data");
    }
    return data;
};
~~~

This snippet requires `fetchFromReplica()` to be defined by the application. If an empty string means "failure," determine that before returning. However, if `null` is genuinely a valid result, do not turn it into an error just because of the chosen API; choose a coordination tool that fits the domain.

## 7. The Timeout Overload

Syntax:

~~~java
String result = executor.invokeAny(
        tasks, 300, TimeUnit.MILLISECONDS);
~~~

If **no success occurs** before the wait duration expires, the timed overload throws `TimeoutException`. Tasks that have not finished are requested to cancel when the method exits.

Distinguishing the outcomes:

| Situation | Exception/Result |
|---|---|
| At least one normal result within the deadline | Returns result `T` |
| All candidates terminate with an exception before the deadline | `ExecutionException` |
| Deadline expires with no normal result yet | `TimeoutException` |
| Caller is interrupted while waiting | `InterruptedException` |

The timeout here is **the caller's wait duration for the group of tasks**. It does not cause an in-flight remote I/O operation to time out at that exact moment, nor does it force workers to release all resources immediately.

### Standalone Java Example 3: Timed `invokeAny` Expiration

Two tasks wait on a latch that is never counted down. Because neither can complete normally, the timed call must expire unless interrupted by an external signal.

Save **InvokeAnyTimeoutDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class InvokeAnyTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch closedGate = new CountDownLatch(1);

        Callable<String> blocked = () -> {
            closedGate.await();
            return "UNREACHABLE";
        };

        boolean timedOut = false;
        try {
            try {
                pool.invokeAny(
                        List.of(blocked, blocked),
                        80, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                timedOut = true;
            }

            System.out.println("timedOut=" + timedOut);
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Pool did not terminate");
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac InvokeAnyTimeoutDemo.java
java InvokeAnyTimeoutDemo
~~~

Expected output:

~~~text
timedOut=true
~~~

The example does not rely on exact 80ms scheduling precision. Neither `Callable` can return if the latch is never opened. When timed `invokeAny` exits, the tasks waiting on `CountDownLatch.await()` have a path to respond to cancellation via `InterruptedException`.

If the latch were replaced with a blocking API that does not support interruption, the method could still throw a timeout to the caller while the worker continues holding resources. Separate timeout/close/cancel handling is required according to each API's contract.

## 8. Exception Types to Handle Separately

Caller pattern:

~~~java
try {
    return pool.invokeAny(candidates, 500, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    // No normal result within the deadline.
    logTimeout();
    throw e;
} catch (ExecutionException e) {
    // No candidate completed successfully.
    logAllFailed(e.getCause());
    throw e;
} catch (InterruptedException e) {
    // The caller thread was requested to cancel.
    Thread.currentThread().interrupt();
    throw e;
}
~~~

This is **integration code**; the enclosing method must declare or handle checked exceptions, and `logTimeout` and `logAllFailed` are application-provided. If propagating `InterruptedException` upward, you can let the upper layer decide the policy without necessarily both restoring the interrupt flag and rethrowing; restoring is typically needed when catching the exception without rethrowing it.

Business-meaningful interpretations:
- `ExecutionException`: **no candidate succeeded**; the cause is diagnostic information, not the full set of all exceptions.
- `TimeoutException`: **the wait deadline expired** before a success.
- `InterruptedException`: the **calling** thread was interrupted while waiting; do not automatically assume all workers have stopped.
- `RejectedExecutionException`: the executor rejected one or more tasks under its admission policy (shutdown/saturation or inability to create a worker).

Do not use a single `catch(Exception)` and return `null` in all cases: doing so erases the distinction between valid `null` data, all-failed, and timeout, making the system harder to recover and diagnose.

## 9. How Are Unfinished Tasks Cancelled?

The Javadoc for `ExecutorService.invokeAny` states that **upon normal or exceptional return**, tasks that have **not completed** are cancelled. In common implementations, cancellation may request interrupting the running worker, similar to `Future.cancel(true)`.

Important:
- **A cancel request is not a hard stop.** A CPU-bound loop that never checks for interrupts may keep running.
- Blocking APIs such as `sleep`, `wait`, `BlockingQueue.take`, and `CountDownLatch.await` typically respond with `InterruptedException`.
- I/O, native, or third-party APIs do not necessarily respond quickly or with `InterruptedException`; read their specific contracts.
- A task that has already completed is not "unfinished"; already-committed side effects are not automatically rolled back.
- Having an `invokeAny` result does not mean losing tasks have finished cleanup completely.
- A thread pool may keep worker threads alive after a `Callable` ends; **task finished** is different from **thread terminated**.
- Do not swallow `InterruptedException` and loop indefinitely. If the caller requests cancellation and the task does not cooperate, it can exhaust worker capacity.

Anti-pattern example:

~~~java
while (true) {
    try {
        queue.take();
    } catch (InterruptedException ignored) {
        // Ignore cancellation signal and go back to waiting.
    }
}
~~~

This is an illustration of a bug, not a production pattern. If the task policy is to stop on interrupt, rethrow `InterruptedException` or restore the interrupt flag and return, along with cleanup in `finally`.

## 10. `invokeAny` Does Not Automatically Guarantee Every Task Starts

An executor may have fewer workers than `Callable`s. Tasks may be queued or submitted by the executor according to its strategy as it collects completions. Suppose there are 2 sources:

- Task A waits indefinitely on an operation with no timeout.
- Task B can return `"OK"` as soon as it runs.
- The executor has only **one worker**, and A acquires the worker first.

In that case, B has no worker to run on, and an untimed `invokeAny` can **wait indefinitely**. Just because B "is capable of returning fast" is not enough if it is never scheduled.

~~~text
Executor: core=max=1
single worker -> A is blocking
queue -> B is waiting for a worker
caller -> invokeAny() waiting for success
=> No success if A never exits so B can start.
~~~

It is especially dangerous when a task running inside **that same pool** calls `invokeAny` on the pool and waits for child tasks: the parent worker occupies the only worker while the children are queued, creating a **thread-starvation deadlock**.

Before using:
- Does the pool have enough worker capacity for the desired number of independent I/O operations?
- Do tasks hold locks/permits that other tasks need in order to run?
- Is there a parent-child dependency on the same pool causing all workers to wait on each other?
- Are queue capacity and rejection policy appropriate for the fan-out?
- Are there timeouts, cancellation, and deadlines for slow sources?

## 11. `invokeAny` vs `invokeAll` vs `submit`

| Tool | Return | When does the caller finish? | Cancels remaining tasks? |
|---|---|---|---|
| `invokeAny(tasks)` | A single result `T` | When there is one **normal completion**, or none succeed / interrupted | Yes, unfinished tasks on exit |
| `invokeAny(tasks, timeout, unit)` | A single result `T` | Same as above, or upon timeout | Yes, unfinished tasks on exit |
| `invokeAll(tasks)` | `List<Future<T>>` | When all tasks complete (success or exception) | If the caller is interrupted, unfinished tasks are cancelled |
| `invokeAll(tasks, timeout, unit)` | `List<Future<T>>` | When all complete or the timeout expires | Unfinished tasks are cancelled on expiration |
| `submit(callable)` | `Future<T>` | Returns `Future` once submission is accepted | Does not automatically cancel other tasks |

`invokeAll` preserves the list of `Future`s in **the iteration order of the input collection**; a completed `Future` does not mean success—the caller may need `future.get()` and catch `ExecutionException`.

With multiple `submit` calls followed by calling `futureA.get()` first, the caller can get stuck on A even if B has already succeeded; `invokeAny` solves the **any-success** goal cleanly without forcing the caller to manage the winner manually. If you need **per-task errors**, use `invokeAll` or individual `Future`s instead of a single aggregate `ExecutionException`.

### Compared to `ExecutorCompletionService`

`ExecutorCompletionService<T>` lets you retrieve `Future`s in **completion order** via `take()` or `poll()`. You can inspect results one by one, record each source's exception, select by a predicate, or require multiple results. In return, you must manage the `Future` list, cancellation, timeouts, and cleanup yourself. `invokeAny` is convenient when you only need **one normal result**.

### Compared to `CompletableFuture.anyOf`

`CompletableFuture.anyOf(a,b,c)` completes when any `CompletableFuture` completes, **including exceptionally**. If the first source throws an exception, `anyOf` can complete exceptionally right away, whereas `invokeAny` can still wait for another source to succeed. `anyOf` also does not automatically cancel all losers according to the `ExecutorService.invokeAny` contract.

Therefore, **`anyOf` is not a full equivalent of `invokeAny`**. If you need first-success semantics with `CompletableFuture`, you must design your own mechanism to handle failures, the winner, and cancellation.

## 12. Timed `invokeAny` Is Not a System-Wide Hard Deadline

For example:

~~~java
String answer = pool.invokeAny(
        tasks, 250, TimeUnit.MILLISECONDS);
~~~

does not promise that:
- Remote sources stop instantaneously at 250ms.
- All sockets/connections are closed before the caller receives `TimeoutException`.
- Losers' side effects are rolled back.
- The scheduler wakes the caller at exactly 250ms by wall clock.
- Each task gets an independent 250ms budget.
- A delayed response from a cancelled source cannot produce a side effect.

When business logic has a total 300ms deadline, you must account for request creation, queueing, remote I/O, processing, and cleanup. If you need to bound remote requests, set timeouts on the I/O API itself, not only on `invokeAny`.

If an application invokes `invokeAny` thousands of times, each hitting three replicas, it can **triple downstream load**. Do not use unbounded hedged racing if the remote service has quotas or concurrency caps. For advanced needs, **delayed hedging** (waiting briefly on the primary source before firing fallback sources) can be used, though `invokeAny` does not provide delayed hedging out of the box.

## 13. Multi-Source Problems with Side Effects

Source A might write to a database and respond slowly; B might return a successful result early; then A receives a cancel request. Even though the caller only receives B, A's write **may have already committed** before cancellation.

Therefore:
- Prefer **read** tasks, pure computation, or idempotent attempts.
- If writes are required, use an idempotency key and a data store with a protocol that prevents business duplicates.
- Do not assume interruption rolls back transactions, emails, files, sockets, or remote requests.
- Every `Callable` must still be thread-safe with mutable shared objects; `invokeAny` only coordinates completion, it does not lock business state.
- If multiple replicas have different data, "the first source to respond" is not necessarily the newest or most consistent data.

If you must pick the highest version, reach a quorum, or record all results, `invokeAny` **lacks sufficient semantics**; choose a more suitable coordination API.

## 14. Do Not Confuse Completed, Cancelled, and Termination

Some states:

| Event | What can be concluded? | What cannot be concluded? |
|---|---|---|
| `invokeAny` returns `T` | One task completed normally | Losers have finished cleanup completely |
| `TimeoutException` | No success within the wait period | All workers have stopped |
| `ExecutionException` | No task succeeded | All detailed causes have been reported |
| `Future.isCancelled()` | The `Future` is in the cancelled state per contract | Side effects were reversed |
| `pool.shutdown()` | Pool accepts no new tasks per policy | All running tasks have finished |
| `pool.awaitTermination()` returns `true` | Pool has terminated | External system side effects have been rolled back |

If you need to confirm that losers have finished cleanup, design an appropriate latch/handle or separate lifecycle `await`. Do not block indefinitely in cleanup when the operation itself has timed out; set a deadline for resource release as well when the system requires it.

## 15. Executor Lifecycle Management

In Java 17, manage `ExecutorService` with `try/finally` and controlled shutdown:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(4);
try {
    String answer = pool.invokeAny(
            candidates, 1, TimeUnit.SECONDS);
    consume(answer);
} finally {
    pool.shutdown();
    try {
        if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                System.err.println("Tasks still running");
            }
        }
    } catch (InterruptedException e) {
        pool.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

This is an **integration snippet**; `candidates` and `consume` are application-defined, and the method must declare or handle `invokeAny`'s checked exceptions. If the pool is shared across multiple requests, **do not shut it down after each request**; the owner must manage its full lifecycle.

`shutdownNow` **attempts** to interrupt running tasks, rather than forcibly killing them. If a task is performing non-interruptible I/O or swallowing cancellation signals, the pool may still have active workers after the wait period. That is why you should monitor termination and write cancellation-aware code.

### Java 21+ and Virtual Threads

`Executors.newVirtualThreadPerTaskExecutor()` can help run many blocking tasks with virtual threads, but it does not automatically cap concurrent requests to a remote endpoint. Regardless of the executor, `invokeAny` preserves the semantics that **one normal completion is enough** and requests cancellation of unfinished tasks; whether cancellation is effective still depends on the specific operation. For Java 17, use a platform thread pool as shown in the example.

## 16. Common Mistakes in Code Reviews

1. **Confusing the first result with the first task in the `List`.** Collection order does not guarantee the winner.
2. **Assuming an early failing task fails the entire `invokeAny`.** `ExecutionException` is only thrown when no candidate succeeds.
3. **Forgetting that returning `null` counts as success.** Business result validation must be handled by the caller/`Callable`.
4. **Assuming `invokeAny` returns a `Future`.** It returns `T` directly.
5. **Assuming all `Callable`s run in parallel immediately.** The pool/queue and scheduling strategy decide.
6. **Assuming all losers have stopped once `invokeAny` returns.** It requests cancellation, but does not force threads to terminate immediately.
7. **Using timed `invokeAny` as a replacement for a network client timeout.** A caller-side timeout does not guarantee remote I/O has released resources.
8. **Confusing `TimeoutException` with `ExecutionException`.** Running out of time is not the same as all sources failing.
9. **Swallowing `InterruptedException` and continuing.** The worker may ignore cancellation.
10. **Using non-idempotent write tasks.** Losers may have already committed.
11. **Using a pool that is too small with a task that waits indefinitely.** Other candidates may never get scheduled.
12. **A parent task waiting on child tasks in the same pool with no free workers.** Risks a thread-starvation deadlock.
13. **Relying on `ExecutionException.getCause` to infer all source errors.** It is not a full aggregation.
14. **Modifying the `tasks` collection while `invokeAny` is running.** The Javadoc states the behavior is undefined.
15. **Ignoring rejection and lifecycle.** A shut-down executor may reject new tasks.
16. **Measuring only throughput without measuring fan-out.** Racing can amplify load and reduce overall stability.
17. **Choosing the winning replica by timing when the newest data is required.** Fastest does not mean correct/latest.
18. **Using `CompletableFuture.anyOf` as if it were first-success.** `anyOf` can complete exceptionally from the first failing source.
19. **Claiming `cancel(true)` means "kill task".** Cancellation is usually a cooperative mechanism based on interrupts.
20. **Failing to close an owned executor.** Workers/resources may be held longer than necessary.

## 17. Checklist Before Using `invokeAny`

- [ ] Are the `Callable<T>` tasks truly independent and of the same result type?
- [ ] Is a single normal result sufficient to satisfy the business requirement?
- [ ] Do `null`/empty/error-status results need to be rejected inside the `Callable`?
- [ ] Is the collection non-empty, free of `null`s, and not mutated during the call?
- [ ] Does the pool have enough workers so fast sources have a chance to run?
- [ ] Is there an overall timeout for the call when an SLA is required?
- [ ] Does each remote/I/O operation have an appropriate timeout/cancel mechanism?
- [ ] Do tasks respond to interrupts and clean up resources in `finally`?
- [ ] Do tasks cause non-idempotent side effects?
- [ ] Are `ExecutionException`, `TimeoutException`, and `InterruptedException` handled separately?
- [ ] Is `RejectedExecutionException` handled?
- [ ] Who is responsible for shutting down the executor; is it shared?
- [ ] Do you need to collect **all errors** or select by another business predicate?
- [ ] Have you tested winning-task behavior with latches/controls rather than relying on `sleep`?
- [ ] Have you measured remote fan-out, queue latency, cancellation effectiveness, and downstream load?

## 18. Self-Check Exercises

**Question 1.** Task A throws an exception after 10ms, and task B returns `"OK"` after 20ms. With an executor that has enough workers, what should `invokeAny` return?

**Answer:** `"OK"`; A's early failure is not a normal result.

**Question 2.** Both tasks throw exceptions, with no normal result. What is the outcome?

**Answer:** `ExecutionException`.

**Question 3.** Task A returns `null`, and task B returns `"data"`. Is `null` ignored?

**Answer:** No. `null` is a normal completion and can be the winner.

**Question 4.** Timed `invokeAny` expires, but one worker is blocked on a non-interruptible API. Has the worker definitely stopped?

**Answer:** No. The method requests cancellation of unfinished tasks, but the worker may continue; separate timeout/cancellation at the resource level is needed.

**Question 5.** Does `invokeAny` return `T` or `List<Future<T>>`?

**Answer:** It returns `T`. `invokeAll` returns `List<Future<T>>`.

**Question 6.** The caller is interrupted while waiting on `invokeAny`. What exception is thrown?

**Answer:** `InterruptedException`; unfinished tasks are requested to cancel. The caller needs to handle the interruption according to its lifecycle.

**Question 7.** Why can `Executors.newSingleThreadExecutor()` with a first task that blocks forever cause `invokeAny` to hang?

**Answer:** The next task may simply sit in the queue with no worker available to run it and produce a success.

**Question 8.** Does `Future.get(timeout)` automatically cancel the `Future` on timeout?

**Answer:** No. Unlike timed `invokeAny`, a `Future.get` timeout only affects the waiter; cancellation must be called separately if desired.

**Question 9.** Why should you avoid using `invokeAny` for three tasks that write the same transaction?

**Answer:** Multiple tasks may have already written before losers are cancelled, and cancellation does not roll back writes. Idempotency and a transaction protocol are needed.

**Question 10.** With `CompletableFuture.anyOf` where one future fails early and another succeeds later, is the early failure guaranteed to be ignored?

**Answer:** No. `anyOf` can complete exceptionally as soon as the first failing future finishes; it is not equivalent to `invokeAny`'s first-success semantics.

## 19. Official Documentation

- **ExecutorService, two `invokeAny` overloads — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **Callable — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html
- **Future — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- **AbstractExecutorService — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/AbstractExecutorService.html
- **ExecutorCompletionService — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html
- **CompletableFuture — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **Thread interrupt — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html

**Key takeaway:** `invokeAny` retrieves **one result from a `Callable` that completes normally**, ignores early failures while a chance of success remains, and **requests cancellation of unfinished tasks** upon returning or throwing an exception. If all tasks fail, you get `ExecutionException`; if the timed overload expires before a success, you get `TimeoutException`. A `null` result is still a technical success. To apply it correctly, you must design **business validation, executor capacity, deadlines, interruption, idempotency, and cleanup**.
