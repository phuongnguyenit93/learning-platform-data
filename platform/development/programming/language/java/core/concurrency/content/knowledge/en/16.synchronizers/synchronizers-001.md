# CountDownLatch: Waiting for a Completion Milestone in Java

## 1. What Problem Does CountDownLatch Solve?

In multithreaded programming, there are many situations where a thread must **wait for an event or a group of tasks to reach a completion milestone** before continuing. For example:

- A coordinator thread submits three independent tasks to an executor and aggregates the results only after all three have finished.
- A test suite wants to wait for workers to finish preparing and then signal them all to start together.
- A thread must wait for an initialization step to signal success before starting to read data.
- Multiple threads need to wait for the same "configuration ready" event.

`CountDownLatch` in the `java.util.concurrent` package is a **one-shot synchronizer**. It manages a non-negative count set at construction time. Threads can call `await()` to wait until the count reaches **0**; threads signaling completion call `countDown()` to decrement the count.

One way to visualize it:

```text
CountDownLatch(3)

Worker A completes → countDown(): 3 → 2
Worker B completes → countDown(): 2 → 1
Worker C completes → countDown(): 1 → 0

Coordinator thread calls await() ──waiting──► proceeds when count = 0
```

This is a **synchronization milestone**, not a data queue; it does not create threads, does not execute tasks on its own, and does not guarantee task success. The count reaching 0 only indicates that the signals occurred according to the contract designed by the developer.

This lesson focuses on **pure JDK Java Concurrency**, without using Spring-specific APIs.

## 2. Core APIs

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

CountDownLatch latch = new CountDownLatch(3);

// Thread signals that an event/unit of work has reached the milestone:
latch.countDown();

// Thread that needs to wait for the milestone:
latch.await();

// Thread that needs to bound the wait time:
boolean reached = latch.await(500, TimeUnit.MILLISECONDS);

// Observe the count, mainly for diagnostics:
long count = latch.getCount();
```

The snippet above illustrates the API; the two `await` calls are alternative ways of using it, not a standalone program.

| API | Behavior | Key Points to Remember |
| --- | --- | --- |
| `new CountDownLatch(n)` | Creates a latch with an initial count of `n` | `n` must not be negative; `n == 0` means the latch is already open |
| `countDown()` | Decrements the count by 1 if still positive | Non-blocking; once at 0, it does not go negative |
| `await()` | Waits until the count reaches 0 | May throw `InterruptedException` |
| `await(long, TimeUnit)` | Waits for at most the specified duration | Returns `true` if count reaches 0, `false` if timed out; can also be interrupted |
| `getCount()` | Returns the current count | For monitoring/debugging, not a substitute for synchronization |

The constructor `new CountDownLatch(-1)` throws `IllegalArgumentException`. A value of `0` is valid and causes `await()` to return immediately, unless the thread is interrupted according to the API contract.

**There is no `reset()`.** Once it reaches 0, the latch remains open permanently. Subsequent `await()` calls no longer wait; subsequent `countDown()` calls have no effect. To wait for a new phase, create a new `CountDownLatch` or choose a reusable synchronizer when appropriate.

## 3. Waiting and Signaling Mechanism

Suppose we have a latch with count 2:

1. Thread M calls `latch.await()` when the count is 2. M will wait rather than continuously polling in a busy-spin loop.
2. Worker 1 calls `countDown()`: the count changes 2 → 1; M is **not** unblocked yet because one signal has still not arrived.
3. Worker 2 calls `countDown()`: the count changes 1 → 0; M becomes eligible to continue.
4. Thread N, calling `await()` on this latch afterward, can proceed immediately because the milestone has been reached.

Notes:

- **`countDown()` does not wait for `await()`**. A worker can signal completion even when no thread is waiting yet.
- **Multiple threads calling `await()` concurrently** is allowed. When the count reaches 0, all of them become eligible to be woken up; the actual order in which they resume is decided by the scheduler.
- `await()` does not "acquire" or "consume" a permit. Once the count reaches 0, it opens the way for all awaiters, unlike `Semaphore.acquire()` which acquires a permit.
- `CountDownLatch` does not automatically know how many tasks were actually submitted or executed. If the count is configured incorrectly, the latch may open too early or never open.

A milestone reaching 0 does not equate to "all tasks succeeded." If a worker throws an exception but still calls `countDown()`, the latch still opens; the caller must read a `Future`, error state, or a separate mechanism to know the outcome.

## 4. Standalone Java 17 Example: Wait for Three Tasks and Aggregate

The program creates three `Callable<Integer>` tasks running in an `ExecutorService`. Each worker signals the completion milestone by calling `countDown()` inside `finally`. Main waits for the latch to reach 0, then uses `Future.get()` to check execution and retrieve values. Because printing happens **after the synchronization milestone**, stdout does not depend on the order in which workers are scheduled.

Save to `CountDownLatchDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CountDownLatchDemo {
    public static void main(String[] args) throws Exception {
        int taskCount = 3;
        CountDownLatch completed = new CountDownLatch(taskCount);
        ExecutorService pool = Executors.newFixedThreadPool(taskCount);
        List<Future<Integer>> futures = new ArrayList<>();

        try {
            for (int i = 1; i <= taskCount; i++) {
                final int number = i;
                Callable<Integer> work = () -> {
                    try {
                        return number * 10;
                    } finally {
                        completed.countDown();
                    }
                };
                futures.add(pool.submit(work));
            }

            completed.await();
            System.out.println("All tasks signalled completion.");

            int sum = 0;
            for (Future<Integer> future : futures) {
                // If a task fails, get() throws ExecutionException.
                sum += future.get();
            }

            System.out.println("Results count: " + futures.size());
            System.out.println("Total: " + sum);
            System.out.println("Latch count: " + completed.getCount());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Run with Java 17 or later:

```bash
javac CountDownLatchDemo.java
java CountDownLatchDemo
```

Stdout:

```text
All tasks signalled completion.
Results count: 3
Total: 60
Latch count: 0
```

**Explanation of the correctness conditions:**

- The count is set to the exact number of tasks expected to signal.
- Each `Callable` calls `completed.countDown()` **only once**, in `finally`.
- `finally` runs once the task's `call()` invocation has started and reaches an exit path, even if an exception occurs during computation.
- Main prints the results only after `completed.await()`. The sum from the three tasks is `10 + 20 + 30 = 60`.
- `Future.get()` is still important: the latch does not store results and does not carry task exceptions. If a task throws an error before completing normally, `get()` will throw `ExecutionException`; the latch is only a milestone signal.
- `CountDownLatch` does not guarantee worker execution order; the program does not print from workers, so the displayed output has a deterministic order.

**Boundary of the example:** If `pool.submit(work)` fails before accepting a task (for instance, the executor is shut down or rejects it), the corresponding worker will have **no opportunity** to call `countDown()`. In that case, waiting indefinitely with `await()` is unsafe. In real applications, admission/rejection handling and timeouts are needed; the following sections explain this in detail.

## 5. Why Should countDown Be in finally?

Unsafe code:

```java
Runnable task = () -> {
    doWork();       // If it throws an exception, the next line will not run.
    latch.countDown();
};
```

This is a fragment: `doWork` and `latch` are declared elsewhere. If `doWork()` throws a `RuntimeException`, the latch is not decremented, risking waiting threads hanging forever.

A better pattern:

```java
Runnable task = () -> {
    try {
        doWork();
    } finally {
        latch.countDown();
    }
};
```

Placing the signal in `finally` clarifies the contract: **"The task has exited the wrapped unit of work"**, not **"the task necessarily succeeded."** You still need to ensure that every task counted toward the latch actually starts executing. If a task is canceled before starting, rejected, or never submitted, the `finally` block inside the task does not run; missing-task signaling must be handled at the orchestration layer.

Another design is calling `countDown()` only when a task succeeds to model "N successes achieved." In that case, if a task fails, waiting may never finish; a deadline or a separate error path is mandatory. Therefore, when the requirement is **waiting for all tasks to finish**, placing `countDown()` in `finally` is usually clearer and safer.

## 6. Two Latches Coordinating Start and Completion Times

A concurrency testing technique is using **two or three separate latches**:

- `ready`: workers confirm they have reached the preparation point.
- `start`: main opens a shared starting gate with a single `countDown()`.
- `done`: workers signal they have finished their work.

This reduces reliance on `Thread.sleep()` in tests. It does not mean all workers run **simultaneously in absolute terms**; the scheduler still decides which worker gets CPU time first.

Standalone illustrative example, save to `StartTogetherDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class StartTogetherDemo {
    public static void main(String[] args) throws InterruptedException {
        int workers = 3;
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(workers);
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        int[] results = new int[workers];

        try {
            for (int i = 0; i < workers; i++) {
                final int index = i;
                pool.execute(() -> {
                    ready.countDown();
                    try {
                        start.await();
                        results[index] = (index + 1) * 10;
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                    } finally {
                        done.countDown();
                    }
                });
            }

            ready.await();
            start.countDown();
            done.await();

            System.out.println("Results: "
                    + results[0] + "," + results[1] + "," + results[2]);
            System.out.println("All done: " + (done.getCount() == 0));
        } finally {
            start.countDown(); // Open the gate if main is interrupted.
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Workers did not terminate");
            }
        }
    }
}
```

Run:

```bash
javac StartTogetherDemo.java
java StartTogetherDemo
```

Stdout on a normal run:

```text
Results: 10,20,30
All done: true
```

Each worker writes to a different array index, avoiding contention on the same slot. `done.await()` returns only after all three have signaled the milestone, so main can read the written values. If a task is interrupted before writing, the program can still open `done` because `finally` runs; in systems that need to distinguish success from failure, you must add a `Future` or result status. The demo uses `shutdownNow()` in `finally` after completion, which is not how you cancel a normally running workload.

**A common test deadlock:** using `newFixedThreadPool(2)` when three workers must all wait at `start.await()`, while main waits for `ready` with count 3. Two workers are blocked at the start gate, the third sits in the queue unable to report ready, and main never opens the gate. To avoid this, never have more workers blocked at the gate than the thread pool's capacity, or design a protocol that does not require all tasks to occupy workers simultaneously.

## 7. await(timeout): Do Not Wait Indefinitely on Unexpected Failures

`await()` without a timeout can wait forever if there are not enough `countDown()` calls. In software with latency requirements, consider:

```java
boolean reached = latch.await(2, TimeUnit.SECONDS);
if (!reached) {
    // Deadline expired: log tasks that have not signaled yet,
    // request cancellation, return an error, or switch to a fallback.
    handleTimeout();
}
```

This is a fragment; `latch` and `handleTimeout()` are defined by the application.

| Result | Interpretation |
| --- | --- |
| `true` | The count reached 0 within the wait time |
| `false` | The wait time elapsed and the count still had not reached 0 |
| `InterruptedException` | The waiting thread was interrupted during the wait operation |

If the timeout is 0 or negative, `await(timeout, unit)` does not wait for the count to change; it checks the state and returns the corresponding result, unless the thread is already interrupted.

**A timeout does not decrement the count, does not cancel tasks, and does not shut down the executor.** Workers may continue running after `await(timeout)` returns `false`. To stop them, the caller must manage `Future.cancel(true)`, executor lifecycle, interruption, and cleanup according to its own contract. Do not assume immediate cancellation stops all side effects of a running task.

A deterministic example independent of machine speed:

```java
CountDownLatch neverOpened = new CountDownLatch(1);
boolean reached = neverOpened.await(0, TimeUnit.MILLISECONDS);
System.out.println(reached); // false
```

Here, no thread calls `countDown()`, so the non-waiting check returns `false`. This snippet is a fragment and needs the appropriate `import` statements.

## 8. InterruptedException and Cancellation While Waiting

Both `await()` and `await(timeout, unit)` are **interruptible** operations. If the waiting thread is interrupted, they throw `InterruptedException`. If the thread already has its interrupt status set upon entering `await`, the API may also throw immediately per its contract.

In a method that can propagate the exception, the simplest approach is to let `InterruptedException` propagate:

```java
void waitForReady(CountDownLatch ready) throws InterruptedException {
    ready.await();
}
```

If you need to catch it inside a method that does not declare checked exceptions, handle the interruption per contract and usually **restore the interrupt flag**:

```java
try {
    ready.await();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return; // Example void method; stop processing instead of continuing blindly.
}
```

This is a fragment; `ready` must be declared beforehand. When `await` throws `InterruptedException`, the interrupt status may have been cleared by the interrupt-checking mechanism. Calling `interrupt()` again allows higher layers to observe the stop request.

**Do not continue using data as if the milestone were reached** after `await` is interrupted. Similarly, if `await(timeout)` returns `false`, code should not read results being written by workers under the assumption they are complete, unless another synchronization mechanism is in place.

## 9. Data Visibility Guarantee: happens-before

An important property of `CountDownLatch` is its **memory consistency effects**. According to the API contract:

> Actions in a thread prior to calling `countDown()` *happen-before* actions following a successful return from a corresponding `await()` in another thread.

Example:

```java
final int[] result = new int[1];
CountDownLatch ready = new CountDownLatch(1);

// Worker thread:
result[0] = 42;
ready.countDown();

// Waiting thread, running on another thread:
ready.await();
System.out.println(result[0]); // Has a visibility relationship with the write before countDown.
```

This example illustrates snippets running on **two different threads**, not a standalone program. If the worker truly writes `result[0] = 42` and then calls `countDown()`, and another thread waits for `await()` to succeed before reading, the change is published under the happens-before relationship.

Note the limitations:

- Data writes **after** `countDown()` do not automatically receive the same guarantee from the latch.
- If `await(timeout)` returns `false` or `await` throws `InterruptedException`, you must not assume the synchronization relationship of a **successful** await.
- A latch does not make arbitrary operations on a mutable object thread-safe. If two workers concurrently update the same `HashMap` or increment a variable with an unprotected read-modify-write, data races and lost updates still occur.
- When collecting results from multiple workers, each worker should write to a non-contended slot, use concurrent collections, or use appropriate synchronization; the latch primarily guarantees **the milestone has been reached and actions prior to the milestone are published**.

This is what makes a latch more useful than a `while (flag == false)` loop on a non-`volatile` variable. Such a loop both wastes CPU and lacks visibility guarantees without a proper synchronization relationship.

## 10. CountDownLatch Is Not a Future and Does Not Carry Errors

A latch can reach 0 even if all workers failed, as long as each worker still calls `countDown()` in `finally`. It does **not** return per-task results, does not store stack traces, and does not distinguish success from failure.

Comparison:

| Tool | What Does It Wait For? | Results / Errors | Cancellation Capability |
| --- | --- | --- | --- |
| `CountDownLatch` | N signals | Count and milestone state only | No task cancel API |
| `Future<T>` | A single task with a result | `get()` returns `T` or reports error/cancellation | `cancel(...)` for the task |
| `ExecutorService.invokeAll(...)` | A group of Callables to complete or time out | List of Futures per task | API can cancel incomplete tasks on some paths |
| `CompletableFuture.allOf(...)` | Multiple CompletableFutures to complete | Must inspect each future for results | Cancellation semantics must be designed separately |

When the problem is "wait for N tasks and then collect results and errors," `Future` or `invokeAll` may require less coordination code. `CountDownLatch` shines when the awaited event **is not necessarily tied to a Future**, or when multiple threads need to be released at the same milestone.

For example, if you use `ExecutorService.submit(Callable)` and `Future.get()` for each task, waiting on each Future sequentially still ensures all tasks' results are processed; adding a separate latch is not mandatory unless there is another coordination requirement.

## 11. Common Sources of Program Hangs

### 11.1. Initializing with the Wrong Count

```java
CountDownLatch done = new CountDownLatch(4);
// But only 3 tasks will call done.countDown() once each.
done.await(); // May wait forever.
```

To wait for three tasks, set count = 3. If the number of tasks is unknown or tasks spawn additional tasks, a fixed latch may be unsuitable; consider `Phaser` or a dynamic task-tracking mechanism.

### 11.2. Forgetting finally

If a task throws an exception before `countDown()`, the latch misses a signal. Use `try/finally` on the task execution path and design a clear error path.

### 11.3. Tasks Rejected or Canceled Before Starting

For example, the executor invokes `RejectedExecutionHandler` and does not accept a task, or `Future.cancel(...)` cancels a task that has not started yet. The `finally` block inside the task **does not execute**. If it was already included in the count, the latch may never open. You must bind admission and signal count precisely; you can adopt a protocol of "finalizing the list of accepted tasks before creating the latch," or use another structure when admission changes dynamically.

### 11.4. Thread Pool Lacking Enough Workers to Pass the Gate

Using 5 tasks that all wait on a start gate while the pool has only 2 workers, and main waits for all 5 tasks to report ready before opening the gate. Two workers hold the threads, while the remaining three sit in the queue: the system deadlocks. Do not use a latch as a starting barrier for more tasks than the number of workers that can run concurrently, unless the protocol is changed to avoid circular wait.

### 11.5. Signaling Too Early

Calling `countDown()` before writing data or before finishing critical updates allows awaiters to proceed while state is still being modified. Place `countDown` **after** the actions that awaiters need to observe. In `finally`, if resources must be cleaned up and the milestone means "cleanup finished," arrange for cleanup to happen **before** `countDown`.

### 11.6. Calling countDown Multiple Times for One Task

`CountDownLatch` does not know the source of a signal. One worker calling `countDown()` twice can open the latch prematurely, even though another worker has not finished. Each signal must have clear ownership and meaning; extra calls after reaching 0 are simply ignored.

### 11.7. Reusing an Already-Opened Latch

A latch that has reached 0 cannot be "closed again." `getCount()` will continue returning 0; `await()` on it will not wait for a second phase. Create a new latch for the next milestone or choose a multi-phase mechanism.

## 12. Comparison with CyclicBarrier, Phaser, Semaphore, and Condition

| Synchronizer | When to Use? | Difference from CountDownLatch |
| --- | --- | --- |
| `CountDownLatch` | Waiting for a milestone of N signals, one or more waiting threads | One-shot; signalers do not have to wait |
| `CyclicBarrier` | A group of threads meet at a barrier and proceed together across **multiple rounds** | Reusable barrier; participants all call `await()`; can become broken |
| `Phaser` | Multiple synchronization phases where participants can register/deregister | Supports phase advancement and dynamic party counts |
| `Semaphore` | Limiting concurrent operations using permits | `acquire` takes a permit and `release` returns it; not a one-time countdown milestone |
| `Condition` | Waiting for a state condition under a `Lock` and being notified via `signal`/`signalAll` | Must hold the associated lock, typically waited on in a predicate-checking loop |
| `Thread.join()` | Waiting for a specific `Thread` to terminate | Tied to thread lifecycle; a latch can represent N events or tasks without needing a dedicated thread per signal |

Choose based on the business contract:

- "Wait for three steps to complete and proceed once": `CountDownLatch(3)`.
- "Ten workers must meet at the end of each computation round and reuse the barrier": `CyclicBarrier(10)` or `Phaser`.
- "Allow at most five requests to access a resource concurrently": `Semaphore(5)`.
- "Wait for a queue state to transition from empty to non-empty": `BlockingQueue` or `Condition` is more appropriate than a one-shot latch.

`CountDownLatch` **does not count running tasks by arbitrarily incrementing and decrementing**. It only counts down to 0, so it is unsuitable as a counter of outstanding tasks that can increase again after a previous phase ends.

## 13. Proper Design with Timeouts and Cancellation

In systems with deadlines, a waiting protocol may need to:

1. Choose **which milestone** must occur before the deadline (all tasks exited, at least some tasks succeeded, or part of a pipeline is ready).
2. Store `Future<?>` references if actual task cancellation needs to be requested.
3. Use `await(timeout, unit)` and handle `false` explicitly.
4. On timeout, call `cancel(true)` on tasks that need to stop, **but do not assume every task stops immediately**.
5. Design tasks to support interruption and I/O timeouts; use `try/finally` for cleanup.
6. If you need to prove resources have been released, use a separate completion/cleanup milestone; a Future may be marked cancelled before the task actually stops.
7. Ensure logs/metrics capture slow tasks, missing signal counts, and deadlines.

Fragment pattern:

```java
if (!completed.await(2, TimeUnit.SECONDS)) {
    for (Future<?> future : futures) {
        future.cancel(true);
    }
    reportTimeout(completed.getCount());
}
```

`completed`, `futures`, and `reportTimeout` are provided by the application. `getCount()` at timeout is only the currently observed state; it may change immediately afterward as another worker calls `countDown()`. Do not use this number as an atomic transaction to compute the exact set of tasks that have not run yet.

**Caution with task dispatch failures:** If a task is rejected before a Future is created, you cannot request its cancellation via the Future list. The counting contract must be designed so that unaccepted tasks are not waited on indefinitely.

## 14. Concurrency Testing with CountDownLatch

`CountDownLatch` is widely used in tests because it creates deterministic milestones instead of relying on `Thread.sleep()`:

- `ready` ensures workers have reached the preparation point.
- `start` lets the test control when to open the gate.
- `done` lets the test wait for work to finish.
- Assertions are performed **after** `await()` succeeds to avoid reading intermediate results.

However, tests can also hang if the count is misconfigured or the pool lacks workers. Use `await(timeout)` and fail with specific diagnostics:

```java
boolean allReady = ready.await(3, TimeUnit.SECONDS);
if (!allReady) {
    throw new AssertionError("Workers not ready: " + ready.getCount());
}
start.countDown();
```

This is a fragment; `ready` and `start` are initialized in the test. When a test fails, ensure `start.countDown()` is called in `finally` or appropriate cleanup to avoid leaving workers stuck while the test suite tries to shut down.

`CountDownLatch` helps establish ordering between **deterministically related milestones**, but it does not guarantee the ordering of every instruction among workers once released. If a test needs to detect race conditions, you still need to run sufficient scenarios, check invariants, and use other concurrency testing tools or techniques.

## 15. CountDownLatch Usage Checklist

- [ ] The initial count reflects the **exact number of signals** the logic will emit.
- [ ] Each signal source calls `countDown()` exactly once at a **meaningful point**.
- [ ] For task completion, use `finally` to signal when a task has started and exited, even on error.
- [ ] Handle **rejected** tasks and tasks **canceled before running**; do not rely on their `finally` blocks.
- [ ] Use `await(timeout)` when there is a deadline; distinguish `true`/`false` outcomes.
- [ ] Handle `InterruptedException` and do not treat an interrupted thread as having reached the milestone.
- [ ] Do not read state written by workers after a failed await without other synchronization.
- [ ] If you need to know whether a task succeeded or failed, combine with `Future` or result status.
- [ ] If there is a start gate, ensure the pool has enough capacity for all workers that must report ready to actually start.
- [ ] Do not reuse a latch that has reached 0; create a new latch for a new phase.
- [ ] Do not hold critical locks while calling `await()` if workers need those locks to complete.
- [ ] When you must measure "cleanup completely finished," place `countDown` after cleanup or use a separate completion signal.

## 16. Self-Check Questions

**1. After `new CountDownLatch(3)` and calling `countDown()` twice, does `await()` return normally?**  
Not yet, because the count is still 1. Only the third `countDown()` brings it to 0.

**2. Once a latch reaches 0, does calling `countDown()` again make the count negative?**  
No, the count stays at 0.

**3. Can multiple threads wait on the same latch concurrently?**  
Yes. When the milestone reaches 0, all awaiters become eligible to proceed, though no resumption order is guaranteed.

**4. Does `await(timeout)` returning `false` cancel the workers?**  
No. It only indicates the wait time expired before the count reached 0.

**5. Does placing `countDown()` in `finally` prove a task succeeded?**  
No. It only signals that the task body passed through the exit path containing `finally`; errors may still have occurred.

**6. Does a task canceled before being run by a worker execute the `finally` block inside the task?**  
No. Because the body never started, that `finally` block has not executed; missing signals must be handled on the coordinator side.

**7. Why does waiting for `await()` to succeed make data written before `countDown()` visible?**  
Because `CountDownLatch` provides a memory consistency guarantee: actions before `countDown()` happen-before actions after the corresponding successful `await()`.

**8. When repeated synchronization across multiple rounds is needed, should you reuse a `CountDownLatch` that has reached 0?**  
No. Use a new latch for each round or choose `CyclicBarrier`/`Phaser`.

**9. Why can `CountDownLatch(5)` with a fixed thread pool of 2 and five tasks all waiting on `start` deadlock?**  
If main waits for all five `ready` signals before opening `start`, only the first two tasks hold worker threads; the remaining three stay in the queue unable to report ready, while the first two workers do not exit to free up threads.

## References

- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)
- [Java SE 17 — Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html)
