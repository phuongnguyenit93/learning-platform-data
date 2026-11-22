# Timeout When Waiting for Data or Resources in Java

## 1. What Problem Does a Timeout Solve?

In a multithreaded program, a thread often has to **wait for an event**: data appearing in a queue, a lock being released, a permit becoming available, a worker completing, or a state condition becoming true. If it waits indefinitely, a hung task, a dead producer, or a continuously contended resource can cause the thread to wait forever.

A **timeout** is the time limit a thread is **willing to spend on a waiting operation**, allowing the application to continue processing when the event has not yet occurred. It is not a guarantee that the work will complete within that time limit.

For example: a consumer is only allowed to wait at most 200 ms to retrieve data. If none is available yet, it can return a “no data yet” result, record a retry, or move on to another task. You **must not** assume the producer has stopped, data will never arrive, or the queue is broken just because `poll(timeout)` expired.

Two requirements need to be separated:

- **Bounded waiting:** not waiting forever for a condition or resource.
- **Task cancellation / deadline:** requesting that running work stop or not start after a deadline. A timeout when *waiting for a result* usually **does not automatically cancel** the task providing the result.

This lesson focuses on Java concurrency in general, using JDK APIs (Java 17+), without being tied to any framework.

## 2. Four Things to Distinguish: Timeout, Deadline, Interruption, Cancellation

| Concept | Meaning | Example |
| --- | --- | --- |
| **Timeout** | The maximum amount of time you want to spend on a single waiting operation | `queue.poll(200, MILLISECONDS)` |
| **Deadline** | A shared end point across multiple stages; each stage only uses the **remaining time** | Waiting for both a queue and a lock using the same 500 ms budget |
| **Interruption** | A cooperative signal sent to a thread to request exiting a waiting operation/stopping work | `waitingThread.interrupt()` |
| **Cancellation** | The decision not to continue a task; its effectiveness depends on the API and task code | `future.cancel(true)` sends an interrupt when appropriate |

A thread can stop waiting because of **success**, **timeout**, **interrupt**, or **another error**. Proper design must distinguish those cases via return values/exceptions and not turn every failure into a “timeout”.

### Does a Bounded Wait End at the Exact Specified Time?

**Millisecond-level precision is not guaranteed.** The scheduler, timers, and CPU load affect when a thread wakes up. Methods with timeouts generally provide guarantees about how the wait budget is used according to the API contract, not hard real-time responsiveness. Code execution after waking up can also be delayed by the scheduler.

Furthermore, a thread that has already acquired a lock/permit or received data **before the point of checking the result** must still handle it, even if the application's overall deadline has just passed. Timeout is part of the protocol, not a substitute for checking state and handling contention cases.

## 3. Receiving Data with `BlockingQueue.poll(timeout, unit)`

`BlockingQueue` is well-suited for producer–consumer patterns. Common APIs:

- `take()`: waits until an element is available, with no timeout; may throw `InterruptedException`.
- `poll()`: checks immediately without waiting; if empty, returns `null`.
- `poll(long timeout, TimeUnit unit)`: waits at most the timeout duration when the queue is empty; returns the element if available, or `null` if time expires without receiving anything.
- `put(element)`: waits if the queue is bounded and currently full.
- `offer(element, timeout, unit)`: waits a bounded amount of time to insert into a full queue; returns `boolean`.

**Meaning of `null`:** for standard `BlockingQueue` implementations, null elements are not allowed to be inserted. Therefore, `poll(timeout) == null` is a signal that no data could be retrieved within the wait period, not that a “null record was read”.

### Java 17+ Example: Attempting to Retrieve Data with a Time Limit

Create the file `TimedQueueDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

public class TimedQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        ArrayBlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

        String missing = queue.poll(0, TimeUnit.MILLISECONDS);
        System.out.println("Initially empty: " + (missing == null));

        queue.put("job-1");
        String received = queue.poll(1, TimeUnit.SECONDS);

        System.out.println("Received: " + received);
        System.out.println("Queue empty: " + queue.isEmpty());
    }
}
```

Compile/run:

```bash
javac TimedQueueDemo.java
java TimedQueueDemo
```

Output:

```text
Initially empty: true
Received: job-1
Queue empty: true
```

In this example, `poll(0, ...)` is called when the queue is guaranteed to be empty so it returns null immediately, while `poll(1, SECONDS)` executes after `job-1` has already been placed, so it retrieves the element without waiting. The example intentionally produces **deterministic** output without pretending that scheduling or latency is always fixed.

If a real producer/consumer runs on different threads, `poll(200, MILLISECONDS)` may return data immediately, after part of the wait period, or return null. No ordering or timing is guaranteed unless another synchronization mechanism is used.

### A Full Queue Is Also a “Waiting for Resource” Problem

With a bounded queue, the producer needs **available capacity**, just as the consumer needs data. Use `offer(element, timeout, unit)` to prevent the producer from hanging indefinitely if the consumer has stopped taking data.

`offer` returns `false` when it cannot insert within the allowed time. That does **not** prove the queue is permanently full. The application must have a clear strategy: bounded retries, backpressure, returning an overload signal, or controlled rejection; do not silently drop important records.

## 4. Waiting for a Lock with `ReentrantLock.tryLock(timeout, unit)`

`ReentrantLock.lock()` waits until the lock is acquired, with no timeout. The no-arg `tryLock()` **only tries immediately**. `tryLock(long timeout, TimeUnit unit)` waits at most the given duration for the lock to become available and returns `true` if acquired, or `false` if not acquired within the limit.

**Crucial rule:** only call `unlock()` when you have **actually acquired the lock**. If `tryLock` returns `false` or throws `InterruptedException` before acquiring, that thread is not the owner.

Usage pattern:

```java
// Snippet: lock is already a ReentrantLock.
boolean acquired = lock.tryLock(200, TimeUnit.MILLISECONDS);
if (!acquired) {
    return; // Depends on the enclosing method's contract.
}
try {
    // Process state protected by the lock.
} finally {
    lock.unlock();
}
```

The snippet above is **not a standalone program**: `lock` and the enclosing method are not declared.

### Java 17+ Example: Timeout When the Lock Is Held

Create the file `TimedLockDemo.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class TimedLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        lock.lock(); // Main thread holds the lock while the worker tries.

        try {
            Thread worker = new Thread(() -> {
                boolean acquired = false;
                try {
                    acquired = lock.tryLock(50, TimeUnit.MILLISECONDS);
                    System.out.println("Worker acquired: " + acquired);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    System.out.println("Worker interrupted");
                } finally {
                    if (acquired) {
                        lock.unlock();
                    }
                }
            }, "worker");

            worker.start();
            worker.join(); // Main still holds the lock; worker only waits 50 ms.
        } finally {
            lock.unlock();
        }

        System.out.println("Main released lock");
    }
}
```

Run:

```bash
javac TimedLockDemo.java
java TimedLockDemo
```

Output if no external thread interrupts the worker:

```text
Worker acquired: false
Main released lock
```

Main intentionally holds the lock while waiting for the worker to finish. The worker **cannot** acquire the lock held by main, so `tryLock(50, MILLISECONDS)` returns false after the wait period expires (not necessarily at exactly 50 ms). Because the worker **has a timeout**, main's `join()` can complete. If the worker used `lock()` without a timeout, the sample program would deadlock: main waiting for the worker, the worker waiting for the lock held by main.

This is an example of controlling wait time, **not** a recommended pattern of “holding a lock while joining a worker” in real applications. In practice, avoid holding a lock while waiting for other work that needs that lock.

### Fairness and Interruption

`ReentrantLock`'s `tryLock(timeout, unit)` can be interrupted and throw `InterruptedException`. With a fair lock, the waiting mechanism respects the lock's policy of prioritizing long-waiting threads, but fairness does not guarantee absolute scheduler fairness. The no-timeout `tryLock()` has differences regarding barging on fair locks; do not use lock acquisition outcomes to prove business ordering.

## 5. Waiting for a Permit with `Semaphore.tryAcquire(timeout, unit)`

`Semaphore` typically represents a number of slots/resources that can be used concurrently, such as a maximum of 4 connections. `acquire()` waits for a permit when none are available; `tryAcquire(timeout, unit)` allows bounded waiting.

```java
// Snippet: permits is a declared Semaphore.
if (!permits.tryAcquire(100, TimeUnit.MILLISECONDS)) {
    // No permit available within the wait budget.
    return;
}
try {
    // Use the resource slot.
} finally {
    permits.release();
}
```

Unlike `ReentrantLock`, `Semaphore` does not tie a permit to an owner thread under the same model; the code must be designed to define who is responsible for releasing. **Do not release when acquisition did not succeed**, as this can artificially inflate the permit count and break the resource limit.

### Java 17+ Example: Limiting to Two Resources

Create the file `TimedSemaphoreDemo.java`:

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class TimedSemaphoreDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore slots = new Semaphore(2);

        boolean first = slots.tryAcquire(0, TimeUnit.MILLISECONDS);
        boolean second = slots.tryAcquire(0, TimeUnit.MILLISECONDS);
        boolean third = slots.tryAcquire(0, TimeUnit.MILLISECONDS);

        System.out.println("First acquired: " + first);
        System.out.println("Second acquired: " + second);
        System.out.println("Third acquired: " + third);

        if (first) {
            slots.release();
        }
        if (second) {
            slots.release();
        }
        System.out.println("Available permits: "
                + slots.availablePermits());
    }
}
```

Run:

```bash
javac TimedSemaphoreDemo.java
java TimedSemaphoreDemo
```

Output:

```text
First acquired: true
Second acquired: true
Third acquired: false
Available permits: 2
```

There is no scheduling contention in the example, so the result is deterministic. The code only illustrates permits; in practice you must also account for the **lifecycle of the physical resource**. If a permit is acquired but opening the connection fails, `finally` must still release the permit when appropriate; if the connection was opened, it must be closed according to its own contract.

## 6. Waiting for a Signal with `CountDownLatch.await(timeout, unit)`

`CountDownLatch` waits for an **event milestone**, not a queue value. APIs:

- `await()`: waits indefinitely until the count reaches 0 or the thread is interrupted.
- `await(timeout, unit)`: returns **`true`** if the latch reaches 0 before the wait ends, **`false`** if it times out while the count has not yet reached 0.
- `countDown()`: decrements the count if greater than 0; once a latch reaches 0 it stays open and cannot be reused to count another cycle.

```java
// Snippet: latch is declared as CountDownLatch.
boolean ready = latch.await(300, TimeUnit.MILLISECONDS);
if (!ready) {
    // Completion event not observed within the allowed wait time.
}
```

**Common mistake:** calling `await(timeout)` and assuming subsequent code has the right to use the prepared data. You must check `true/false`. `false` does not mean the producer will never finish; another thread may call `countDown()` immediately afterward.

Use a latch to represent “all workers have reached the ready milestone”, “configuration has finished loading”, or “N pieces of work have completed”. However, if a worker dies before calling `countDown()`, the latch may never reach 0; put `countDown` in `finally` if the latch's semantics are “the worker has finished whether it succeeded or failed”, or publish a separate error state if you need to distinguish success.

## 7. `Condition.awaitNanos` and the Condition Loop

When managing a queue/condition yourself using `Lock` and `Condition`, you must be careful about:

1. **Spurious wakeups:** an `await` call may wake up even when the condition is not yet true.
2. **A signal does not guarantee the condition is still true:** multiple threads may be waiting, and another thread may have already consumed the data.
3. **Total timeout:** after a wakeup, you must **not reset** the wait budget back to the initial value if the caller only granted one shared wait duration.

`Condition.awaitNanos(long nanosTimeout)` returns an **estimate of the remaining nanoseconds**; it may be non-positive when expired. To handle this properly, you must hold the lock when checking the predicate, wait inside a `while` loop, and pass the remaining time into the next wait.

### Java 17+: Single-Element Mailbox with Timeout

Create the file `TimedMailbox.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class TimedMailbox {
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition hasMessage = lock.newCondition();
    private String message;

    public void put(String value) {
        lock.lock();
        try {
            if (message != null) {
                throw new IllegalStateException("Mailbox full");
            }
            message = value;
            hasMessage.signal();
        } finally {
            lock.unlock();
        }
    }

    public String receive(long timeout, TimeUnit unit)
            throws InterruptedException {
        long remaining = unit.toNanos(timeout);
        lock.lockInterruptibly();
        try {
            while (message == null) {
                if (remaining <= 0L) {
                    return null;
                }
                remaining = hasMessage.awaitNanos(remaining);
            }

            String received = message;
            message = null;
            return received;
        } finally {
            lock.unlock();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        TimedMailbox box = new TimedMailbox();
        System.out.println("Empty: "
                + (box.receive(0, TimeUnit.MILLISECONDS) == null));
        box.put("hello");
        System.out.println("Received: "
                + box.receive(1, TimeUnit.SECONDS));
    }
}
```

Compile/run:

```bash
javac TimedMailbox.java
java TimedMailbox
```

Output:

```text
Empty: true
Received: hello
```

**Explanation:**

- `message` is only accessed while holding the **same lock**; there are no unsynchronized reads/writes.
- `while (message == null)` re-checks the predicate after every wakeup, including spurious wakeups.
- `remaining` is updated from `awaitNanos` so that if it wakes up multiple times, the wait time **does not restart from the beginning**.
- `lockInterruptibly()` allows the thread to be interrupted while waiting to acquire the lock; `awaitNanos` can also be interrupted.
- `finally` ensures the lock is released whether data is received, a timeout occurs, or an exception is thrown.
- The demo calls `receive` first with timeout 0 (empty mailbox), and next after data has been placed in the mailbox, so it does not depend on another thread's timing.

**An intentional limitation:** `put` here rejects when the mailbox is full instead of waiting for a slot; the goal of the example is **waiting for data with a Condition**. If the producer also needs to wait until the mailbox is empty, you must design an additional `notFull` condition, predicate, and appropriate timeout, or use the built-in `ArrayBlockingQueue` to avoid writing a full concurrent queue yourself.

### Timeout When Acquiring the Lock vs. Waiting on the Condition

`receive()` above uses `lockInterruptibly()`, meaning **the time spent waiting to acquire the lock is not counted toward `awaitNanos`'s timeout**. If the business API promises that **the entire receive call does not exceed a budget**, you need to use `tryLock(remaining, unit)` to account for the lock wait time as well, and then pass the **remaining time** to `awaitNanos`.

This is an important distinction between the “timeout of **a single wait step**” and the “deadline of **the entire operation**”.

## 8. `Future.get(timeout, unit)`: Waiting for a Result Does Not Mean Cancelling the Task

When submitting a `Callable` through `ExecutorService`, you can wait for the result with `Future.get(timeout, unit)`. If the task has not finished when time expires, it throws `TimeoutException`. **The future may still be running.** Only `cancel(...)` according to application policy sends a cancellation request, and even `cancel(true)` does not guarantee the task stops immediately if the code does not cooperate with interrupts.

### Java 17+: Controlled Timeout Reproduction

Create the file `FutureTimeoutDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch gate = new CountDownLatch(1);

        try {
            Callable<String> task = () -> {
                gate.await();
                return "done";
            };
            Future<String> future = executor.submit(task);

            try {
                future.get(20, TimeUnit.MILLISECONDS);
                System.out.println("Unexpected completion");
            } catch (TimeoutException expected) {
                System.out.println("Timed out while waiting");
            }

            gate.countDown(); // Allow the task to actually finish.
            System.out.println("Result after release: " + future.get());
        } finally {
            gate.countDown(); // Prevent worker hang if main exits try early.
            executor.shutdown();
        }
    }
}
```

Compile/run:

```bash
javac FutureTimeoutDemo.java
java FutureTimeoutDemo
```

Output when there is no external interrupt and the executor operates normally:

```text
Timed out while waiting
Result after release: done
```

Because `gate` is not open during the first wait period, the task **cannot** return a result before main calls `gate.countDown()`. Therefore the first `get(20, MILLISECONDS)` must time out; after opening the gate, the subsequent `get()` retrieves the result. Calling `get` does not automatically cancel the task.

Other scenarios:

- Task throws an exception: `get` may throw `ExecutionException` wrapping the task's cause.
- Task is cancelled: `get` throws `CancellationException`.
- Thread calling `get` is interrupted: `get` may throw `InterruptedException`.
- Time expires while the task is still running: `get` throws `TimeoutException`; the caller must decide whether to retry, cancel, or proceed with other handling.

If you use `cancel(true)`, make the task **cooperate with interrupts**, such as exiting when a blocking operation throws `InterruptedException` or checking the interrupt flag in an appropriate processing loop. Do not use `Thread.stop()` to force cancellation.

## 9. `Thread.join(timeout)`: Bounded Wait for a Thread to Finish

`Thread.join()` without a timeout waits for the target thread to finish. `Thread.join(long millis)` or the nanosecond overload allows waiting for a bounded duration, but **returns `void`**, not true/false. After a timed join, you must check `worker.isAlive()` if you want to know whether the worker is still running.

Pitfalls:

- `join(0)` **waits forever**, it is not an immediate check.
- `join(100)` does not cancel the worker when 100 ms elapses.
- `join(timeout)` can return either because the worker finished or because the wait time expired.
- `worker.isAlive()` is a state snapshot; right after checking, the worker might finish.
- `join` can throw `InterruptedException` when **the waiting thread** is interrupted; it does not interrupt the worker itself.

Using `Future` is usually more natural when you need to manage a task's result, exceptions, timeout, and cancellation, rather than working directly with the `Thread` lifecycle.

## 10. A Shared Deadline Across Multiple Waits

Suppose an API grants **500 ms to retrieve data and acquire a lock**. If you call `queue.poll(500ms)` and then `lock.tryLock(500ms)`, the total time **can far exceed 500 ms**, because each call receives its **own budget**. If you keep retrying with 500 ms each time, the total time can stretch indefinitely.

You need to compute the **remaining time**:

```java
long budgetNanos = TimeUnit.MILLISECONDS.toNanos(500);
long started = System.nanoTime();

// After each stage:
long elapsed = System.nanoTime() - started;
long remaining = budgetNanos - elapsed;

if (remaining <= 0L) {
    // Budget exhausted; do not start another long wait.
}
```

This is a snippet showing how to calculate the budget; no processing method is declared. `System.nanoTime()` is suitable for measuring **elapsed time** within a single JVM, because it is a monotonic relative clock for measuring intervals, not for deriving actual wall-clock date/time.

**Why not use `System.currentTimeMillis()`?** The wall clock can be adjusted by NTP, administrators, or time synchronization; its difference is not the right choice for measuring relative deadlines.

**Note on overflow:** subtracting `now - start` with `nanoTime` works properly for measuring intervals when the budget is less than about 2^63 ns (roughly 292 years). For very large timeouts, apply reasonable bounds and avoid overflowing `start + timeout` addition. Use `TimeUnit` and `Duration` APIs consistently for units; do not manually multiply milliseconds × 1_000_000 when values could be large enough to overflow.

### Java 17+: Sharing One Budget Across Queue and Lock

Create the file `SharedDeadlineDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class SharedDeadlineDemo {
    static boolean processWithinBudget(
            ArrayBlockingQueue<String> queue,
            ReentrantLock lock,
            long budget,
            TimeUnit unit) throws InterruptedException {
        long allowed = unit.toNanos(budget);
        long start = System.nanoTime();

        if (allowed <= 0L) {
            return false;
        }

        String message = queue.poll(allowed, TimeUnit.NANOSECONDS);
        if (message == null) {
            return false;
        }

        long remaining = allowed - (System.nanoTime() - start);
        if (remaining <= 0L) {
            return false;
        }

        if (!lock.tryLock(remaining, TimeUnit.NANOSECONDS)) {
            return false;
        }

        try {
            System.out.println("Processed: " + message);
            return true;
        } finally {
            lock.unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ArrayBlockingQueue<String> queue =
                new ArrayBlockingQueue<>(1);
        ReentrantLock lock = new ReentrantLock();

        System.out.println("Empty: " + !processWithinBudget(
                queue, lock, 1, TimeUnit.MILLISECONDS));

        queue.put("task-1");
        boolean processed = processWithinBudget(
                queue, lock, 1, TimeUnit.SECONDS);
        System.out.println("Success: " + processed);
    }
}
```

Run:

```bash
javac SharedDeadlineDemo.java
java SharedDeadlineDemo
```

A possible output:

```text
Empty: true
Processed: task-1
Success: true
```

**What is guaranteed?**

- The first call handles an empty queue: `poll` times out and returns null, so it prints `Empty: true`.
- The second call has data ready and an uncontended lock, yet **a successful outcome still depends** on whether the thread experiences unusual scheduler delays between `poll` and the `remaining` calculation. Under normal load it will usually succeed; you must not assert that `Processed`/`Success: true` is inevitable under every schedule.
- If the budget expires before acquiring the lock, the method returns false. **In this example, the element has already been removed from the queue** before attempting the lock: if processing fails, there is a risk of losing data. This is an **important business limitation**, not a complete production queue-processing pattern.

**Design-level fix:** if taking data means “taking responsibility for processing it”, there must be an acknowledgment mechanism, controlled requeueing, lease/visibility timeout, or a design that acquires the resource **before** dequeuing so items are not lost. Resource acquisition ordering must also avoid deadlocks and bottlenecks. Do not treat a method returning false as sufficient if it has already caused partial side effects.

### A “Hard Deadline” for the Entire Job Is Even Harder

Sharing a single time budget across **blocking** calls still does not turn arbitrary code into hard real-time. The CPU can delay the thread after acquiring the lock; task processing or I/O that does not support timeouts can exceed the limit. You need to propagate deadlines down through each layer, set timeouts on APIs that support them, and define rules for checking results once the deadline has passed.

## 11. Handling `InterruptedException` Properly

Blocking operations such as `queue.poll(timeout, unit)`, `lock.tryLock(timeout, unit)`, `latch.await(timeout, unit)`, `Condition.awaitNanos`, and `Future.get(timeout, unit)` can throw `InterruptedException`.

There are two common ways to handle it:

1. **Propagate:** declare `throws InterruptedException` so the caller decides to stop the work and release related resources.
2. **Catch at a layer that cannot propagate:** perform necessary cleanup, call `Thread.currentThread().interrupt()` to restore the interrupt status if not rethrowing, and return an appropriate result.

```java
// Snippet: worker is another Thread, returns false if interrupted.
static boolean waitUntilDone(Thread worker) {
    try {
        worker.join();
        return true;
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return false;
    }
}
```

The snippet is a helper inside another class, not a standalone program. `false` only indicates **the wait did not complete**, not that the worker has finished or been cancelled.

Do not swallow `InterruptedException` and keep waiting indefinitely under the same policy without explanation. When a timed API returns `false` or `null`, that is different from `InterruptedException`: one means the wait budget expired, the other is an interrupt signal; the system may need to handle them differently.

## 12. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Using `Thread.sleep(100)` to “wait for data” | Does not verify data is present; establishes no synchronization protocol | Use an appropriate `BlockingQueue`, latch, Future, or Condition |
| Concluding the producer is dead when `poll(timeout) == null` | Timeout only means no element was received during the wait period | Monitor producer status/errors through a separate channel |
| Calling `unlock()` even when `tryLock` returned false | Lock is not owned; may throw `IllegalMonitorStateException` | Use an `acquired` flag, unlock only in the success branch |
| Calling `release()` even when `Semaphore.tryAcquire` failed | Incorrectly increases permits, breaking the resource limit | Release only the exact number of permits successfully acquired |
| Assuming the task is cancelled when `Future.get(timeout)` expires | The task may still be running | Define a cancellation policy, call `cancel(true)` if appropriate |
| Treating `Thread.join(0)` as non-blocking | `join(0)` waits indefinitely | Use `isAlive()` to observe state, or a positive timed join |
| Using `if` instead of `while` around `Condition.await` | Spurious wakeups exist and signals do not guarantee the predicate | Check the predicate inside a `while` loop |
| Resetting the timeout after every wakeup | Total wait time can exceed the budget | Use `awaitNanos` or compute the remaining time |
| Giving two wait steps the full timeout each | Total wait time can nearly double | Pass a shared deadline/remaining time |
| Using `currentTimeMillis` to measure elapsed time | Wall clock can jump or be adjusted | Use `System.nanoTime()` for elapsed intervals |
| Treating a timeout as a data error | It may be temporary contention/load | Design appropriate retries, backpressure, and alerting |
| Dropping the item on timeout after dequeuing it | Causes data loss or inconsistent processing | Design proper ownership, ack, and rollback/requeue |
| Swallowing an interrupt | The thread may fail to stop when requested | Propagate or restore the interrupt status |
| Treating a small timeout as a hard real-time guarantee | Scheduling and other non-blocking steps still take time | Design SLAs, measure tail latency and end-to-end deadlines |

## 13. Choosing an API Based on What You Are Waiting For

| What Are You Waiting For? | Common JDK API | Result on Timeout |
| --- | --- | --- |
| A **data element** in a queue | `BlockingQueue.poll(timeout, unit)` | `null` |
| **Available capacity** in a queue | `BlockingQueue.offer(e, timeout, unit)` | `false` |
| A **lock** | `ReentrantLock.tryLock(timeout, unit)` | `false` |
| One or more **permits** | `Semaphore.tryAcquire(timeout, unit)` | `false` |
| A **synchronization milestone** | `CountDownLatch.await(timeout, unit)` | `false` |
| A **predicate under a lock** | `Condition.awaitNanos(remaining)` | Non-positive remaining estimate if expired; always check predicate |
| A result from a **task** | `Future.get(timeout, unit)` | Throws `TimeoutException` |
| A **Thread** to finish | `Thread.join(timeout)` | Returns `void`; check `isAlive()` |
| Asynchronous pipeline result | `CompletableFuture.orTimeout(...)` / `completeOnTimeout(...)` | Completes the future per the API's timeout policy; does not automatically stop underlying side effects |

**Note on `CompletableFuture`:** `orTimeout` completes the future exceptionally if not finished on time; `completeOnTimeout` completes it with a fallback value when time expires. Both apply to **the future's state**, not as a way to forcibly stop any underlying executing task. `CompletableFuture.get(timeout, unit)` is a separate timeout for the caller's wait operation and does not turn the future itself into a timed-out result.

## 14. Checklist for Designing with Timeouts

1. **Identify the real condition:** do you need data, a permit, a lock, a signal, a thread to finish, or a task result?
2. **Choose the corresponding timed API:** `poll`, `tryLock`, `tryAcquire`, `await`, `Future.get`, or timed join.
3. **Interpret the result correctly:** `null`/`false`/`TimeoutException`/`void` each have different meanings.
4. **Define the total budget:** is it a timeout for one operation or a deadline for the entire workflow? Pass the **remaining** time across steps.
5. **Use `nanoTime` for elapsed time**, avoiding wall-clock calculations for relative deadlines whenever possible.
6. **Account for spurious wakeups:** check predicates in a `while` loop; do not reset the budget indefinitely.
7. **Release resources accurately:** use `finally` for locks, permits, and acquired resources; do not release on failure.
8. **Distinguish timeout from cancellation:** if the result is not received, is the task/producer still running? Should a cooperative cancellation signal be sent?
9. **Protect already-taken/already-written data:** when a later step times out, prior items or side effects must be handled properly, not silently lost.
10. **Handle interrupts separately:** propagate or restore the flag if caught; avoid swallowing.
11. **Test both success and expiration:** create controlled test conditions using latches/locks rather than relying on coincidental sleeps.
12. **Measure under real load:** timeout rate, queue latency, lock contention, tail latency, retry counts, and system recovery after overload.

**Remember:** a timeout only **bounds the effort spent waiting** for a condition; it does not guarantee that the source task has finished or been cancelled. Java provides timed waiting APIs for queues, locks, semaphores, latches, conditions, futures, and threads. Using return values/exceptions properly, sharing a single time budget when needed, cleaning up in `finally`, and applying appropriate cancellation/ownership protocols will help prevent infinite hangs without compromising the correctness of concurrent programs.
