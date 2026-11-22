# Waiting for a Thread to Finish Without Busy Waiting in Java

When a thread starts work on another thread, the calling thread sometimes needs to **wait for a result or wait for the work to finish** before proceeding to the next step. A common beginner approach is to repeatedly check `isAlive()`, a flag variable, or a task state in a loop. That style of waiting can waste CPU, make latency hard to control, and easily introduce synchronization bugs.

Java provides **coordinated waiting (blocking wait)** mechanisms such as `Thread.join()`, `CountDownLatch.await()`, `Future.get()`, and `ExecutorService.awaitTermination()`. They allow the waiting thread to yield execution while the condition is not yet met, instead of continuously running a polling loop.

This lesson belongs to **Thread lifecycle in general Java Concurrency**. The focus is on knowing how to **wait for a thread to terminate properly**, understanding visibility, timeouts, interruption, and knowing when to use a different primitive. Spring-specific mechanisms are outside the scope of this lesson.

## 1. What is busy waiting and why should it be avoided?

*Busy waiting* (spin waiting) occurs when a thread continuously performs a check while waiting for a condition to change, typically without intentionally yielding the CPU:

```java
Thread worker = new Thread(() -> doWork());
worker.start();

while (worker.isAlive()) {
    // Repeatedly polling state: doing no useful work.
}
consumeResult();
```

This is **illustrative code**, assuming `doWork()` and `consumeResult()` exist. The loop can run millions of times while the worker is doing its job. `Thread.isAlive()` indicates whether the thread has been started and has not yet terminated; it is not an optimal waiting API.

The consequences:

- **Wasted CPU:** the waiting thread keeps running, competing for processing time with the worker and other tasks.
- **Wasted energy:** especially harmful when waiting on I/O, long-running work, or waiting for multiple threads.
- **Unpredictable latency:** `Thread.yield()` does not guarantee yielding the CPU; putting `Thread.sleep(10)` inside the loop merely turns it into *polling with an interval*, which can add nearly a full wait cycle and still requires handling flags/interruption.
- **Hard to determine the termination condition correctly:** a plain boolean variable shared between threads can lack a *happens-before* relationship, leading to visibility bugs. Using `volatile` for a flag can partially address visibility, but it does not make polling a suitable choice for long waits.
- **Hard to handle errors:** if the worker throws an exception and terminates, the loop may stop without indicating whether the work succeeded or failed.

For the need to "wait for thread A to finish", replace `while (worker.isAlive())` with:

```java
worker.join();
```

`join()` can block **the calling thread**, not the worker. When the worker finishes, the call completes. The calling thread must be prepared to handle `InterruptedException` while waiting.

> There are low-level synchronization algorithms that intentionally use very short spins when the probability of waiting is low and context-switching cost is high. `Thread.onSpinWait()` (Java 9+) is a performance hint for that case, **not** a replacement for `join()` when work can take a long time. This lesson chooses blocking wait for general thread completion tracking.

## 2. `Thread.join()`: waiting for the exact thread termination event

`join()` is an instance method of `Thread`. When the `main` thread calls `worker.join()`, `main` waits until `worker` completes. The basic relationship:

```text
Thread main                                Thread worker
    |                                           |
    |-- worker.start() ------------------------>|
    |                                           | run() executes
    |-- worker.join() ---- waits ...............|
    |                                           | run() finishes
    |<-------------- join() returns ------------|
    | main processes result                     |
```

Commonly used overloads:

| Call | Meaning | Return value |
| --- | --- | --- |
| `worker.join()` | Waits until the worker terminates, unless the calling thread is interrupted. | `void` |
| `worker.join(long millis)` | Waits at most the specified duration in milliseconds; **`0` means wait forever**. | `void` |
| `worker.join(long millis, int nanos)` | Waits with valid millisecond/nanosecond arguments per the API contract; precision may be adjusted by the implementation. | `void` |

The overloads above can throw `InterruptedException` if **the waiting thread** is interrupted. Invalid time arguments can cause `IllegalArgumentException`. With the timed versions, returning **does not by itself tell you** whether the thread finished or timed out. Check `worker.isAlive()` if you need to distinguish between the two.

**Typical usage order:**

1. Create a `Thread` with the appropriate `Runnable`.
2. Call `start()` to launch the thread (only once).
3. When the logic actually needs to wait, call `join()` or `join(timeout)`.
4. After confirming the thread has terminated, read the state/result published by the worker and handle errors according to the chosen mechanism.

Do not call `worker.run()` to "run a thread": that is just a normal method call on the current thread. Do not call `join()` before `start()` and treat that as having waited for the task: a thread that has never started has nothing to wait for, so `join()` can return immediately.

## 3. Java 17+ example: waiting for a result with `join()`

Create the file `JoinResultDemo.java`:

```java
public final class JoinResultDemo {
    public static void main(String[] args) throws InterruptedException {
        int[] result = {0};

        Thread worker = new Thread(() -> {
            int sum = 0;
            for (int i = 1; i <= 5; i++) {
                sum += i;
            }
            result[0] = sum;
        }, "sum-worker");

        worker.start();
        worker.join();

        System.out.println("Thread finished: " + !worker.isAlive());
        System.out.println("Sum: " + result[0]);
    }
}
```

Run:

```bash
javac JoinResultDemo.java
java JoinResultDemo
```

Exact stdout:

```text
Thread finished: true
Sum: 15
```

**Analysis:**

- `worker.start()` begins executing the `Runnable` on a new thread.
- `main` calls `join()` and waits until the worker terminates. `join()` requires no manual polling loop.
- The worker writes `result[0] = 15`. After `join()` completes because the worker has terminated, `main` can read that result.
- `!worker.isAlive()` is `true` because the thread has terminated and cannot be started again.

`int[] result` is only used to illustrate **publishing a result after join**. It is not a thread-safe structure for multiple workers to update arbitrarily. If multiple workers write to a shared result, you need additional coordination rules, atomic operations, or `Future`/an appropriate result type.

Declaring `main throws InterruptedException` keeps the example short and clear: if `main` is interrupted while waiting, the exception is propagated to the caller. In a real application, the control flow needs a clear cancellation and cleanup policy.

## 4. Why is reading the result after `join()` safe for visibility?

The Java Memory Model provides *happens-before* relationships tied to the thread lifecycle:

- Actions that occur before `worker.start()` in the calling thread **happen-before** actions performed by the worker after it starts.
- All actions of the worker **happen-before** another thread successfully detecting that the worker has terminated, such as via `worker.join()` or `worker.isAlive()` returning `false`.

Therefore, in the example:

```text
worker writes result[0] = 15
              |
              | worker terminates
              v
main calls join() and detects termination
              |
              v
main reads result[0] == 15
```

If you only use `Thread.sleep(100)` on `main`, there is **no** guarantee that the worker has finished or that the read relies on a sufficiently clear synchronization relationship. Fast/slow machines, work duration, and scheduling can all vary. `sleep` pauses for a duration; `join` synchronizes on the **termination event**.

**Important note:** `join(timeout)` returning because the timeout expired while the worker is still alive **does not** provide a guarantee that "all writes by the worker are visible". If `isAlive()` subsequently returns `false`, you have detected thread termination, and the termination happens-before relationship is established. If the worker is still alive, you must not assume that all results are ready; exchanging partial results requires synchronization, `volatile`, locks, or an appropriate concurrent mechanism.

Happens-before guarantees **observation order and visibility under the memory model**, not that the business algorithm has correct logic. For example, if the worker computes a wrong result, `join` only helps `main` observe *that wrong result* consistently.

## 5. Timed join: bounded waiting while still checking termination

A task can hang due to I/O, deadlock, or waiting for an event that never arrives. `join(timeout)` lets the calling thread stop **waiting any longer** after the specified duration, but it **does not automatically stop the worker**.

Suppose you want a deterministic outcome without relying on `sleep()`: use a `CountDownLatch` to keep the worker from terminating while testing a timed join.

Create the file `TimedJoinDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public final class TimedJoinDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finishGate = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                finishGate.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "gated-worker");

        worker.start();
        try {
            worker.join(100);
            System.out.println("Still alive after timeout: "
                    + worker.isAlive());
        } finally {
            finishGate.countDown();
        }

        worker.join();
        System.out.println("Finished after gate opened: "
                + !worker.isAlive());
    }
}
```

Compile/run with Java 17 or later:

```bash
javac TimedJoinDemo.java
java TimedJoinDemo
```

Stdout under normal program execution, with no external interruption:

```text
Still alive after timeout: true
Finished after gate opened: true
```

**Why does this not depend on the worker's sleep schedule?** The worker cannot terminate before `finishGate.countDown()` (barring external interruption), because it is waiting on the latch. `main` only opens the gate in `finally`, after attempting `join(100)`. The second `join()` waits for the work to actually finish. No busy-waiting loop is used.

**Be careful with timeouts:**

- `join(100)` takes milliseconds and only specifies a waiting time bound per the API contract; measured wall-clock time is also subject to scheduling delays. Do not interpret it as an absolute real-time deadline.
- `join(0)` means wait indefinitely; it does **not** mean "do not wait".
- After `join(timeout)`, `worker.isAlive()` helps determine whether the worker is currently still alive. A `true` check can become stale immediately afterward if the worker finishes; if you need the final completion result, you still have to coordinate/wait further.
- Timeout expiration does not kill the worker. You must decide whether to let it keep running in the background, request cancellation via interruption, record a "timeout" status, or abandon the result.
- If `main` is interrupted during the timed join, `InterruptedException` is thrown; `finally` still opens the gate, avoiding leaving the worker stuck forever at the latch due to the error path.

For tasks that do not cooperate with interruption, calling `worker.interrupt()` also does **not** guarantee immediate termination. Do not use `Thread.stop()`; this method is unsafe and has been removed from recommended ways to stop threads.

## 6. Interruption: who gets interrupted during `join()`?

`join()` throws `InterruptedException` when **the thread performing the join** is interrupted while waiting. For example, thread A calls `worker.join()`; thread B interrupts A. As a result, A exits the wait call with an exception; the worker is **not automatically canceled** just because A was interrupted.

When `InterruptedException` is thrown by standard blocking methods, **the interrupted flag of the thread catching the exception is cleared**. You need to choose a policy:

- At a layer that can declare `throws InterruptedException`, usually **propagate the exception upward** so the caller handles cancellation.
- In `Runnable.run()`, which cannot declare checked exceptions, usually catch the exception, call `Thread.currentThread().interrupt()` to **restore the interruption flag**, and then exit the task or perform cleanup.
- If canceling the worker as well is required, decide whether to call `worker.interrupt()` according to the task contract; do not assume interrupt means kill.

Example snippet for handling inside a `Runnable`:

```java
try {
    worker.join();
} catch (InterruptedException e) {
    worker.interrupt();                     // Only if you want to request worker cancellation.
    Thread.currentThread().interrupt();     // Restore the flag on the waiting thread.
    return;                                 // Exit the running task.
}
```

This is a **non-standalone** snippet, assuming `worker` is already declared and started, and `return` is inside a `void` method. A common mistake is catching `InterruptedException` and then continuing an infinite join loop, rendering cancellation ineffective.

If the application needs to **wait for the worker to clean up after being canceled**, establish an independent deadline and clear ownership rules. Do not try to wait indefinitely on an already-interrupted thread just to "ensure" the task finishes; the worker might be stuck or uncooperative.

## 7. How `join()` differs from `sleep()`, `wait()`, and `yield()`

| API | What does it wait for? | Is it a direct replacement for `join()`? |
| --- | --- | --- |
| `Thread.join()` | A specific thread to terminate. | Yes — it is the direct API for this purpose. |
| `Thread.sleep(duration)` | A duration of time to elapse. | **No**: it does not know whether the worker has finished. |
| `Object.wait()` | Notification or wait/timeout event on a monitor, checking a predicate under a `synchronized` protocol. | Only appropriate when designing a shared condition yourself; more error-prone than `join()` for waiting on thread termination. |
| `Thread.yield()` | Hints to the scheduler to give other threads a chance to run. | **No**: no guarantee of yielding the CPU, task completion, or visibility. |
| `Thread.onSpinWait()` | Processor optimization hint for a spin loop. | **No** for long tasks; it is still busy waiting if called in a polling loop. |
| `LockSupport.park()` | Waits for a permit / unparking or interruption/spurious return. | Low-level primitive requiring its own protocol; should not replace `join()` when merely waiting for thread termination. |

`Object.wait()` differs from `join()` in that it is tied to a **condition** and a monitor. It must be called while holding the corresponding monitor; it usually requires a `while (!predicate) wait()` loop to tolerate *spurious wakeups*. Using `wait()/notify()` to reimplement waiting for thread termination can suffer from lost notifications if designed incorrectly.

`Thread.join()` in some JDKs may be implemented using internal wait/notification on the `Thread` object. That is an **implementation detail**; your code should rely on the public `join()` contract and not call `notify()` on a `Thread` object hoping the task will finish faster.

## 8. Waiting for multiple threads: join each thread or `CountDownLatch`?

If you need to wait for a group of threads to terminate, you can call `join` on each thread:

```java
for (Thread worker : workers) {
    worker.join();
}
```

This snippet assumes `workers` is a collection of already-started threads. The workers still **run concurrently**; sequential joining only determines the order in which `main` waits to observe completion. If the last worker finishes before the first worker, `main` still waits for the first worker first, and the subsequent joins may then return immediately.

Distinguish between two things:

- **All threads have terminated**: joining all threads matches the goal.
- **Some logical operations have completed** while threads still stay alive/wait for other tasks: using a completion signal (latch, `Future`, queue, condition) is more appropriate.

### 8.1 `CountDownLatch` for multiple work items completing

A `CountDownLatch` is initialized with the number of events to wait for. Each task calls `countDown()` when it finishes; the waiting side calls `await()`. The waiting thread **does not** need to poll and does not keep the CPU busy. A latch is a **one-shot** mechanism; the counter counts down to 0 and cannot be reset for another round.

Create the file `CompletionLatchDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class CompletionLatchDemo {
    public static void main(String[] args) throws InterruptedException {
        int taskCount = 3;
        CountDownLatch completed = new CountDownLatch(taskCount);
        AtomicInteger successful = new AtomicInteger();

        Thread[] threads = new Thread[taskCount];
        for (int i = 0; i < taskCount; i++) {
            threads[i] = new Thread(() -> {
                try {
                    successful.incrementAndGet();
                } finally {
                    completed.countDown();
                }
            }, "task-" + i);
            threads[i].start();
        }

        completed.await();
        System.out.println("Completed signals: " + taskCount);
        System.out.println("Successful tasks: " + successful.get());

        // If you need to ensure the Threads themselves are TERMINATED,
        // you can join each thread after receiving the completion signal.
        for (Thread thread : threads) {
            thread.join();
        }
    }
}
```

Compile and run:

```bash
javac CompletionLatchDemo.java
java CompletionLatchDemo
```

Stdout:

```text
Completed signals: 3
Successful tasks: 3
```

**Why use `finally`?** If the body throws an exception, the latch still decrements, preventing `main` from waiting forever due to a missing signal. However, `await()` completing **does not prove that every task succeeded**; store and inspect errors separately. In this program, incrementing an atomic integer has no expected exceptions, so `Successful tasks: 3` is predictable.

The `countDown()` call happens right before the end of `run()`. `await()` returns when the count reaches 0, but a thread may **not yet have fully transitioned to TERMINATED** at that moment; if you truly must wait for the thread lifecycle to end, join as shown in the example.

According to the Java Memory Model, actions in a thread before `countDown()` happen-before actions following a successful return from the corresponding `await()`. Thus `main` can read updates published before `countDown()` under proper synchronization. In the example, `AtomicInteger` also allows accurate concurrent increments.

### 8.2 Timed await

```java
boolean finished = completed.await(2, TimeUnit.SECONDS);
if (!finished) {
    // Wait timed out; determine retry/cancellation/timeout-reporting policy.
}
```

This is an illustrative snippet, assuming `completed` and `TimeUnit` are available. Unlike `Thread.join(timeout)` which returns `void`, `CountDownLatch.await(timeout, unit)` returns `boolean`: `true` if the count reached 0, `false` if the timeout elapsed. `await()` can also be interrupted.

**Do not** call `countDown()` in place of actually finishing the work. If called before writing results or closing resources, the waiting side may proceed too early. Conversely, if a task is never started, the counter will be short a signal; you must design for submit/start failures and cancellation paths.

## 9. Waiting for a result: `Future` instead of managing `Thread` directly

In most programs that process multiple tasks, you need the **return value and exceptions** of the work, not the worker's `Thread` name/object. `ExecutorService.submit()` returns a `Future`; `Future.get()` waits for completion **without busy waiting** and provides error reporting.

Create the file `FutureCompletionDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class FutureCompletionDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> answer = executor.submit(() -> 6 * 7);

            int value = answer.get();
            System.out.println("Answer: " + value);
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Run with JDK 17 or later:

```bash
javac FutureCompletionDemo.java
java FutureCompletionDemo
```

Stdout:

```text
Answer: 42
```

Key differences to understand:

- `Thread.join()` tells you **the thread has terminated**. It does not directly return a value, nor does it automatically rethrow errors encountered by the worker in `run()`.
- `Future.get()` tells you **the task has completed**, returning the result or throwing `ExecutionException` wrapping the underlying cause; the task can finish on a worker thread that stays alive and runs other tasks.
- `Future.get(timeout, unit)` can throw `TimeoutException`. Wait expiration does not automatically cancel the task; if cancellation is needed, consider `future.cancel(true)` with a cooperative interruption policy.
- `Future.get()` can throw `InterruptedException` if the waiting thread is interrupted and `CancellationException` if the task was canceled. Catch the appropriate exceptions when real tasks need to distinguish states.

In the example, `awaitTermination(5, ...)` waits for **the executor to terminate all workers after `shutdown()`**, not for a single arbitrary task. The `boolean` return value of `awaitTermination` indicates whether the executor terminated or the timeout elapsed. `shutdownNow()` attempts to interrupt running work; it does not force uncooperative tasks to stop immediately.

### 9.1 `CompletableFuture` and a different `join()` method

`CompletableFuture<T>.join()` is **not** `Thread.join()`:

```java
CompletableFuture<Integer> value =
        CompletableFuture.supplyAsync(() -> 21 * 2);
System.out.println(value.join());
```

This snippet requires importing `java.util.concurrent.CompletableFuture`. `CompletableFuture.join()` waits for **completion of the future**, returns `T`, and if the task completes exceptionally, throws an unchecked `CompletionException` (or `CancellationException` if canceled); it does not declare checked `InterruptedException`. Do not confuse the absence of checked interruption with automatic task cancellation or deadlines.

If you need to wait for multiple `CompletableFuture`s, `CompletableFuture.allOf(...)` creates a future that completes when all source futures complete. You still need to inspect the errors/results of each future according to your business goals; do not assume "allOf completed" means every task succeeded.

## 10. Waiting for an entire executor to terminate

Once `shutdown()` has been called, the executor stops accepting new tasks, though already-submitted tasks may still be running. Use `awaitTermination()` to wait for the executor's **terminated** state:

```java
executor.shutdown();
try {
    if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
            System.err.println("Executor did not terminate");
        }
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

This illustrative snippet assumes `executor` is an `ExecutorService` and `TimeUnit` is imported. It **does not guarantee** that stuck tasks will stop: cancellation/interruption is a cooperative mechanism. Shutdown design must also account for workers performing I/O without timeouts, holding locks, or waiting on other tasks.

**Do not** call `awaitTermination()` before `shutdown()` expecting the executor to stop on its own: the pool can keep accepting work and keeping workers alive. `Thread.join()` does not replace the executor shutdown sequence; worker threads may be long-lived or replaced, and their lifecycle belongs to the executor.

If you are managing a few `Thread`s directly (without an executor), you are responsible for telling them to stop, delivering appropriate cancellation signals, and joining the necessary threads.

## 11. When waiting causes the program to hang

`join()` does not burn CPU like polling, but it is **still blocking** and can wait indefinitely if dependencies are designed incorrectly.

### 11.1 Waiting on yourself

```java
Thread.currentThread().join();
```

A running thread cannot terminate before `join()` returns, so unless interrupted, it waits forever. Never call `join` on the current thread.

### 11.2 Dependency cycle between two threads

Thread A joins B, while B joins A: both can wait forever if there is no timeout/interruption. This bug is a form of deadlock at the completion-dependency level, and is not necessarily reported by monitor deadlock detectors.

### 11.3 Calling `join` while holding a lock the worker needs

This is **illustrative buggy code**:

```java
Object lock = new Object();
Thread worker = new Thread(() -> {
    synchronized (lock) {
        // Work requiring lock.
    }
});

synchronized (lock) {
    worker.start();
    worker.join(); // main holds lock; worker cannot enter synchronized.
}
```

Assuming `InterruptedException` is declared/handled in the enclosing method. `main` holds `lock` while waiting for termination; the worker needs that same `lock` to finish. Without external interruption, both get stuck. `join()` **does not release any locks held by the waiting thread**. The fix is not to `join` inside the critical section:

```java
Thread worker = new Thread(() -> {
    synchronized (lock) {
        // Brief work on shared data.
    }
});

worker.start();
worker.join(); // Do not hold the lock needed by the worker.
```

The fixed snippet assumes `lock` is declared and the method handles `InterruptedException`. If you must hold the lock to check state, design a proper protocol with `Condition`/completion notifications instead of creating a lock wait cycle.

### 11.4 Pool starvation

A task running in a small pool calls `future.get()` or `join()` to wait for another task **that is also queued in the same pool**, while no free worker remains to run that queued task. As a result, all workers are busy waiting, and the awaited task never starts. The solution lies in the task dependency graph, executor capacity, avoiding arbitrary blocking inside workers, and coordination structure—not in replacing a busy loop with `join()`.

### 11.5 Waiting indefinitely when a worker never finishes

A worker can get stuck due to I/O, a bug, a deadlock, or a missing signal. `join()` will also wait indefinitely unless interrupted. Use timeouts and error/cancellation policies when the system requires bounded time. Resource management and shutdown must be handled separately; `join`'s timeout only bounds **how long the caller waits**, not the worker's runtime.

## 12. Choosing a waiting primitive based on the real condition

| Problem | Preferred API | Condition actually waited on |
| --- | --- | --- |
| Wait for a `Thread` you created to finish. | `Thread.join()` / `join(timeout)` | Thread lifecycle termination. |
| Wait for an entire group of `Thread`s to finish. | Join each started thread. | All threads are terminated. |
| Wait for N tasks/milestones to signal completion. | `CountDownLatch.await()` | Signal counter reaches 0; threads may still be alive. |
| Wait for a task with a return value/error. | `Future.get()` / `get(timeout)` | Task completion, result, or error. |
| Coordinate results of multiple async tasks. | `CompletableFuture.allOf(...)` or combinators. | Completion of the futures; inspect errors separately. |
| Wait for an executor to finish shutting down. | `ExecutorService.awaitTermination()` | Executor transitions to terminated. |
| Wait for a data condition inside a lock region. | `Condition.await()` with a predicate check loop, or a suitable concurrent structure. | Predicate satisfied under proper synchronization. |
| Wait for an element from a queue. | `BlockingQueue.take()` / `poll(timeout)` | Element available (or timeout elapsed), not necessarily producer thread termination. |

**Selection rule:** identify whether you need to wait for **a thread to terminate**, **a task to finish**, **a result to be ready**, **N signals**, or **an executor to stop**. Use the API tied to that condition. Avoid managing `Thread`s manually just to retrieve a task's value when an executor/`Future` already supports it.

## 13. Testing and observing waiting behavior

To verify that code does not spin CPU and handles completion properly:

1. **Define the completion event.** For example, worker terminated, latch reached 0, future completed, or executor terminated. Do not use "slept for 200 ms" as the criterion.
2. **Test the success path.** Create a worker doing deterministic work, start, join, and assert the result. For example, `JoinResultDemo` produces fixed stdout.
3. **Test the timeout path.** Use a latch to hold the worker to create a deterministic wait condition rather than relying on `Thread.sleep()` and scheduler luck; then release all threads in `finally`.
4. **Test interruption.** Create a thread waiting on a controlled blocked worker; interrupt the waiting thread, verify it exits the blocking wait, and verify it still performs cleanup.
5. **Test task failures.** `Thread.join()` does not rethrow exceptions from `Runnable`; if you want to capture errors, test `Future.get()` and separate error handlers/storage.
6. **Inspect thread dumps when hung.** A thread waiting in `join` typically shows a waiting state (`WAITING` or `TIMED_WAITING` depending on the join type/JDK). Trace the stack trace and dependencies of the target thread; a thread in `WAITING` alone is not enough to conclude deadlock.
7. **Measure CPU and wait time.** A busy loop can saturate a core; a blocking wait typically yields the CPU. Even so, many blocked tasks can still cause resource contention or pool exhaustion.
8. **Always reclaim test resources.** Workers held by a latch must have their gate opened; executors must be shut down; do not leave non-daemon threads hanging and preventing tests/JVM from exiting.

Example of an anti-pattern in tests:

```java
Thread.sleep(100);
assertEquals(42, result[0]);
```

This snippet *assumes* the worker finishes within 100 ms. On a slow CI machine or under heavy load, the test can fail even when the code is correct; on a fast machine, passing does not establish a clear synchronization relationship. Change it to `worker.join(timeout)` and verify `!worker.isAlive()` before checking the result, or use a latch/future for the exact completion event.

## 14. Self-check questions

**1.** Why is `while(worker.isAlive()) {}` worse than `worker.join()` when waiting on long tasks?  
The `while` loop continuously consumes CPU; `join` blocks the calling thread until the worker terminates (or the caller is interrupted).

**2.** Does `worker.join(500)` returning mean the worker has terminated?  
No. It may return because of a timeout. Check `worker.isAlive()` if you need to distinguish.

**3.** If `join()` throws `InterruptedException`, does the worker stop automatically?  
No. **The waiting thread** was interrupted; the worker may continue running. Worker cancellation policy is a separate decision.

**4.** If `main` reads a value written by the worker after `join()` completes, is there a happens-before relationship?  
Yes, the worker's actions happen-before another thread detects that the worker has terminated via a successful `join`.

**5.** Why shouldn't you call `worker.join()` inside `synchronized(lock)` if the worker needs that lock?  
`main` holds the lock while waiting for the worker, while the worker must acquire the lock to finish; this can deadlock.

**6.** If you want to wait for 10 executor tasks to return results/errors, should you keep 10 `Thread`s to join?  
Usually no. Keep the `Future`s and call `get()`, or use `CompletableFuture` combinators; pool workers can process multiple tasks.

**7.** Does `CountDownLatch.await()` returning prove that all signaling threads have terminated?  
No. It only proves that enough `countDown()` calls have occurred; threads may still be executing code after the signal.

**8.** Does putting `Thread.sleep(10)` inside a state-checking loop turn it into a proper synchronization approach?  
No. That is polling with an interval, which still introduces latency and requires solving visibility, timeout, and interruption; use a waiting primitive suited to the condition.

**9.** Are `CompletableFuture.join()` and `Thread.join()` the same?  
No. One waits for a `Future` to complete and can return a result/throw an unchecked exception, while the other waits for a `Thread`'s lifecycle and returns `void`.

**10.** Does `awaitTermination(timeout)` when the executor has not been shut down guarantee the pool will stop?  
No. You must call `shutdown()`/`shutdownNow()` according to your policy; `awaitTermination` only waits for the terminated condition.

**Key takeaway:** When you need to wait for a thread to finish, **`Thread.join()` is the direct choice**. Choose timed join with a status check when you have a deadline; handle `InterruptedException` explicitly; do not wait while holding a lock the worker needs. When the problem calls for a **task result, N signals, or shutdown**, switch to `Future`, `CountDownLatch`, or `ExecutorService` respectively. Blocking waits avoid wasting CPU, while data safety and completion guarantees still have to be designed explicitly.
