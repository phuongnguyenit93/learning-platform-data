# Interrupt Is a Cooperative Signal, Not Forced Termination in Java

## 1. Objectives and Mental Model

Suppose a thread is running a long computation, a task is waiting for a result from a queue, or a worker is waiting for a lock. When that work is no longer needed, another thread can call `interrupt()` to **request** that the worker stop or cancel the ongoing operation. However, unlike a "kill process" command, **`Thread.interrupt()` does not forcibly terminate a thread**.

In Java, interruption is a **cooperative cancellation protocol**: the caller requesting cancellation sends a signal; the code running in the target thread must actively detect the signal and finish in a safe way, or the blocking API it calls must support interruption to release the wait.

After this lesson, you will be able to:

- Distinguish between **sending an interrupt**, **interrupt status**, **throwing `InterruptedException`**, and **the thread actually terminating**.
- Correctly use `interrupt()`, `isInterrupted()`, `Thread.interrupted()`, `Thread.currentThread()`, and `join()`.
- Understand why APIs such as `sleep()`, `wait()`, `join()`, `BlockingQueue.take()`, or `ReentrantLock.lockInterruptibly()` can respond with `InterruptedException`.
- Choose between **propagating the exception**, **restoring the flag with `Thread.currentThread().interrupt()`**, and **cleaning up then exiting**.
- Design CPU-bound loops, blocking workers, and executor tasks that support cancellation without losing data or leaking resources.
- Distinguish between `Future.cancel(true)`, `shutdown()`, `shutdownNow()`, timeout, and interrupt; avoid claiming a task has stopped based solely on a request.
- Compile and run Java 17+ examples with ordering controlled by `CountDownLatch` and `join()`.

**Scope:** General Java SE/JVM concurrency; framework-independent. All complete programs in this article are compatible with **JDK 17+**.

## 2. Interrupt Is a Request, Not a Forced Stop Button

Every `Thread` has an **interrupted status** (interrupt status/flag). Another thread can call:

~~~java
worker.interrupt();
~~~

This call **does not by itself guarantee** that `worker` immediately transitions to `TERMINATED`. It signals to the worker that there is a request to stop/cancel the current operation. The actual reaction depends on what the worker is doing:

1. **Worker running a CPU calculation without checking for interruption:** it may continue running even though the flag is set.
2. **Worker actively checking `isInterrupted()`:** it can exit the loop, roll back uncommitted work, or clean up and finish.
3. **Worker waiting in an interruptible API:** the API can exit the wait state and throw `InterruptedException`; many APIs clear the flag when throwing.
4. **Worker blocked in an API that does not support interruption:** it may **not wake up solely because of** an interrupt; you must use a timeout, close the resource, or use a cancellation mechanism supported by that API.
5. **Worker has already completed:** calling interrupt does not bring it back to a running state; interrupt cannot be used to undo side effects that have already occurred.

Therefore, **three events** must be separated:

~~~text
Coordinator thread           Worker thread
      │                           │
      ├─ worker.interrupt() ──────►│  1. receives cancellation request (signal)
      │                           │
      │                           ├─ checks flag / API throws InterruptedException
      │                           │  2. detects the signal
      │                           │
      │                           ├─ cleanup / safe termination
      │                           │  3. worker actually finishes
      │                           ▼
      └─ worker.join() ◄───── TERMINATED
~~~

Calling `interrupt()` is a **request**; `join()` or another completion mechanism is what lets the caller know the thread has actually finished. They are not synonymous.

## 3. Three Commonly Confused APIs: interrupt, isInterrupted, and interrupted

| API | Target | Meaning | Does it clear the flag? |
|---|---|---|---|
| `someThread.interrupt()` | The thread referenced by `someThread` | Sends an interrupt request; depending on state, may cause blocking APIs to respond | Not a flag-checking/clearing method; blocking APIs may clear it when throwing an exception |
| `someThread.isInterrupted()` | Thread `someThread` | Checks the current interrupt status | **No** |
| `Thread.interrupted()` | **The thread calling** the static method | Checks the interrupt flag of the current thread | **Yes**, clears the flag when checked |

`Thread.interrupted()` is a **static method** and does **not** check an arbitrary thread. Even if you write `worker.interrupted()` (Java allows calling static methods via a reference, which is misleading), the method still checks the **current thread**, not `worker`. Always write `Thread.interrupted()` when you genuinely want to check **and clear** the current thread's interrupt flag.

Short example:

~~~java
Thread me = Thread.currentThread();
me.interrupt();

System.out.println(me.isInterrupted());  // true
System.out.println(Thread.interrupted()); // true; also clears the flag
System.out.println(me.isInterrupted());  // false
~~~

The snippet above is an **illustration running inside a single method**. It assumes no new interrupt arrives between calls. Do not accidentally clear the interrupt flag of a thread executing a test in a framework or a worker pool unless doing so is an intentional part of the handling protocol.

### Key Questions

**If a worker only calls `isInterrupted()` without clearing, does the flag remain set?** Yes, as long as no other operation clears or changes the status. The worker can observe the request at multiple check points.

**If code calls `Thread.interrupted()` in a loop, is the flag still set on the next iteration?** The first call may return `true` and clear it. If no subsequent interrupt arrives, the next call returns `false`; if the code does not exit immediately upon seeing `true`, it may **accidentally continue** running as if no cancellation had been requested.

## 4. Interruption During CPU-Bound Work

A computation loop that does not pass through a blocking API will **not stop on its own** when the caller invokes `interrupt()`. The task must **periodically check** the flag and stop according to its policy.

~~~java
long compute(long items) throws InterruptedException {
    long sum = 0;
    for (long i = 0; i < items; i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Calculation cancelled");
        }
        sum += i;
    }
    return sum;
}
~~~

This is an **illustrative method**, not a standalone program. Notable points:
- The worker does not wait for the JVM to "kill" it; it checks the cancellation condition itself.
- Using `isInterrupted()` to check **does not clear** the flag.
- Manually throwing `new InterruptedException(...)` **does not automatically clear** the interrupt flag. Clearing the flag is a behavior of specific blocking operations that throw `InterruptedException`, not a magic property of the exception constructor. The caller needs a clear protocol.
- If the loop runs very fast, checking on every single iteration may be unnecessary; checking in batches can reduce overhead, at the cost of higher cancellation response latency. Choose based on workload and deadline.
- The task must avoid committing partially inconsistent results. If external resources have already been modified, an interrupt does not roll back those changes.

### Standalone Example 1: CPU-Bound Loop Stopping by Checking Interrupt Itself

Save the file **CooperativeCpuDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeCpuDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean noticed = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            started.countDown();
            while (true) {
                if (Thread.currentThread().isInterrupted()) {
                    noticed.set(true);
                    return;
                }
                Thread.onSpinWait();
            }
        }, "cpu-worker");

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();

        System.out.println("noticed=" + noticed.get());
        System.out.println("alive=" + worker.isAlive());
    }
}
~~~

Compile and run:

~~~bash
javac CooperativeCpuDemo.java
java CooperativeCpuDemo
~~~

Output under normal operating conditions:

~~~text
noticed=true
alive=false
~~~

**Analysis:**

1. `started.await()` ensures the worker has started executing. It does **not** force the worker to run a certain number of iterations; it is simply a start signal.
2. Main calls `worker.interrupt()`. If the worker is inside the loop, its `isInterrupted()` will eventually observe `true`; if the interrupt arrives right after `countDown` and before the first check, the first check will also observe `true`.
3. The worker **returns on its own** from the `Runnable`; it is not forcibly terminated by `Thread.interrupt`.
4. `worker.join()` waits for the thread to finish before main prints; therefore neither line depends on execution ordering between main and worker.
5. `Thread.onSpinWait()` is only a hint for short spin loops, not a stopping or synchronization mechanism. In production, avoid long busy spins; this example is intentionally simple to highlight the interrupt flag.

**Key takeaway:** If you remove `if (isInterrupted())` and have no other exit condition, the worker can keep running forever even though main called `interrupt()`. That is why calling `interrupt` **is not a forced stop**.

## 5. InterruptedException: How Do Blocking APIs Respond?

Many waiting APIs in Java's contract respond to interruption with `InterruptedException`. Common cases:

| API | When interrupted during the wait phase | Notes |
|---|---|---|
| `Thread.sleep(...)` | Throws `InterruptedException` | Does not release any held intrinsic monitor; flag is cleared when thrown. |
| `Object.wait(...)` | Throws `InterruptedException` when interrupted per contract | `wait` uses a monitor and releases it while waiting; must reacquire it before continuing execution. |
| `Thread.join(...)` | Throws `InterruptedException` in **the joining thread** | Does not necessarily interrupt the thread being joined. |
| `CountDownLatch.await()` | Throws `InterruptedException` | Intended for waiting on the latch; does not guarantee the target task stops. |
| `BlockingQueue.take()/put()` | Throws `InterruptedException` if cancelled while waiting | Can be used for a clean producer/consumer lifecycle. |
| `ReentrantLock.lockInterruptibly()` | Throws `InterruptedException` while waiting for the lock | Unlike `lock()`, which does not throw a checked exception during the acquire phase. |
| `ReentrantLock.tryLock(timeout, unit)` | Can throw `InterruptedException` | Distinguish cancellation from returning `false` due to timeout. |
| `Future.get()` | Can throw `InterruptedException` in **the waiting caller** | Does not mean the `Future` task has been cancelled. |

**Read each API's contract:** not every blocking call is interruptible. Some I/O channels from `java.nio.channels.InterruptibleChannel` respond by closing the channel and throwing `ClosedByInterruptException` (a subclass of `IOException`), rather than `InterruptedException`. Sockets/I/O, native calls, filesystems, and third-party libraries may behave differently depending on the API and JDK version. Never promise that "interrupt always wakes up every blocking call."

### When InterruptedException Is Thrown, the Flag Is Usually Already Cleared

Example with `Thread.sleep`:

~~~java
try {
    Thread.sleep(60_000);
} catch (InterruptedException e) {
    System.out.println(Thread.currentThread().isInterrupted());
    // false in the case where sleep cleared the flag before throwing
}
~~~

This is an illustrative method snippet. Clearing the flag allows the caller to **decide what to do next**: rethrow to propagate the cancellation request upward, or restore the flag and exit when the interface does not allow throwing a checked exception.

Do not mechanically claim that "every API that throws `InterruptedException` always clears the flag at the exact same moment" without reading its contract. However, standard JDK APIs like `sleep`, `wait`, and `join` clearly specify clearing the flag upon throwing.

## 6. Handling InterruptedException: Propagate, Restore the Flag, or Exit

### Approach A — Propagate when the signature allows

~~~java
void fetchWork(java.util.concurrent.BlockingQueue<String> queue)
        throws InterruptedException {
    String item = queue.take();
    process(item);
}
~~~

This is an illustrative method; `process(item)` is application-defined logic. When `take()` is interrupted while waiting, the exception propagates to the caller. The caller can decide to cancel the task, log, or shut down; there is no need to swallow the exception and silently continue.

### Approach B — Restore the flag if a checked exception cannot be thrown

A `Runnable.run()` does not declare `throws InterruptedException`:

~~~java
@Override
public void run() {
    try {
        workQueue.take();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt(); // restore the signal
        return; // terminate the task or exit the processing loop
    }
}
~~~

This is a snippet inside a class that has `BlockingQueue<?> workQueue`. After `take()` throws the exception and clears the flag, calling `currentThread().interrupt()` preserves the cancellation information for upper layers. The `return` shows that the task **chooses to stop** rather than continue.

### Approach C — Clean up resources in finally

~~~java
void processOneTask() throws InterruptedException {
    Resource resource = acquireResource();
    try {
        performInterruptibleWork(resource);
    } finally {
        resource.close();
    }
}
~~~

The snippet above assumes `Resource`, `acquireResource`, and `performInterruptibleWork` are defined by the application and `close()` matches the signature. The idea is that acquired resources must be released even when `InterruptedException` exits the method. You need to define the behavior if cleanup itself throws an exception; `try-with-resources` can be used with resources implementing `AutoCloseable` to manage suppressed exceptions.

**Why not "catch and ignore"?**

~~~java
while (true) {
    try {
        taskQueue.take();
    } catch (InterruptedException ignored) {
        // Wrong when shutdown requires stopping: keeps looping back to wait as if no signal arrived.
    }
}
~~~

If `take` clears the flag, the loop repeats and continues waiting; the caller requested cancellation, yet the worker may **completely ignore it**. Occasionally an application has a specific reason to defer interruption to finish a mandatory operation, but it must **document the policy** and typically restore the interrupt flag before exiting the non-cancellable region. By default, do not swallow the signal.

## 7. Standalone Example 2: sleep Throws an Exception and Clears the Flag

This program actively ensures the worker has reached the point right before waiting using a latch. Main interrupts the worker. Whether the interrupt arrives **before** the worker executes `sleep` or while it is sleeping, the `sleep` call will throw `InterruptedException` under these conditions.

Save the file **InterruptedSleepDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptedSleepDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean();
        AtomicBoolean clearedInCatch = new AtomicBoolean();
        AtomicBoolean restoredInCatch = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            started.countDown();
            try {
                Thread.sleep(60_000);
            } catch (InterruptedException e) {
                caught.set(true);
                clearedInCatch.set(!Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                restoredInCatch.set(Thread.currentThread().isInterrupted());
            }
        }, "sleep-worker");

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();

        System.out.println("caught=" + caught.get());
        System.out.println("cleared=" + clearedInCatch.get());
        System.out.println("restored=" + restoredInCatch.get());
        System.out.println("alive=" + worker.isAlive());
    }
}
~~~

Compile/run:

~~~bash
javac InterruptedSleepDemo.java
java InterruptedSleepDemo
~~~

Expected output, when no external interrupt or other operation interferes:

~~~text
caught=true
cleared=true
restored=true
alive=false
~~~

Analysis:

1. The worker calls `started.countDown()` right before `sleep`, so main knows the worker has entered `Runnable`. `started` is not a signal that the worker is definitely in the `TIMED_WAITING` state.
2. If the interrupt arrives before `sleep`, the flag is already set; when `sleep` checks the interrupted status, it throws an exception. If the worker is already sleeping, the interrupt wakes it up via the exception.
3. `Thread.sleep` clears the interrupt status when throwing `InterruptedException`, so `isInterrupted()` at the start of `catch` is `false` and `clearedInCatch` is recorded as `true`.
4. The worker calls `Thread.currentThread().interrupt()` to restore the signal, and then `isInterrupted()` returns `true`.
5. Main uses `join()`, so the variables written by the worker are observed after completion. `AtomicBoolean` is chosen for readability in the illustration, not because `join()` itself lacks visibility.

**Limitation:** In production, you should not rely on a `sleep(60_000)` merely to simulate synchronization. Here the long duration is used to demonstrate the API; the program relies on latch/interrupt/join, **not** on waiting out 60 seconds.

## 8. join(), Interrupted Status, and the Waiting Thread's Actions

Suppose main calls:

~~~java
worker.join();
~~~

This asks **main to wait for worker to finish**. If another thread interrupts **main** while main is waiting in `join`, `join` can throw `InterruptedException` in main; it does not mean the worker is automatically stopped.

In orchestration code, consider:
- Do you want to cancel the worker when main is interrupted? If so, explicitly call `worker.interrupt()` or cancel the task according to your protocol.
- Do you need to wait for the worker to clean up before exiting? You can wait with a deadline, but you must handle the case where the coordinating thread itself has been interrupted.
- Can task ownership be abandoned? An unmanaged non-daemon worker can keep the process alive.
- If the caller decides to propagate `InterruptedException` from `join`, the target task may still continue unless a separate cancellation request is issued.

`join()` provides memory consistency/happens-before when the joined thread has completed, but it **is not a forced cancellation mechanism**.

## 9. Interrupt and Waiting Operations in synchronized, Lock, and Condition

### 9.1. synchronized does not support cancellation while waiting to acquire a monitor

A thread trying to enter:

~~~java
synchronized (sharedLock) {
    updateState();
}
~~~

if the monitor is held by another thread, calling `interrupt` on the thread **contending for the monitor** does not cause the JVM to throw `InterruptedException` and abandon the monitor acquisition request. The interrupted status may be recorded, but the thread still needs to acquire the monitor before executing the block per the intrinsic monitor contract.

**Do not confuse** this with `Object.wait()`: `wait` is called **inside a synchronized region** and is an interruptible waiting API; when waiting, the thread releases the monitor while waiting and must reacquire it before continuing. The two phases—"waiting to **enter** a monitor" and "holding the monitor and calling `wait`"—are different.

### 9.2. ReentrantLock supports a cancellable acquire phase

~~~java
import java.util.concurrent.locks.ReentrantLock;

void work(ReentrantLock lock) throws InterruptedException {
    lock.lockInterruptibly();
    try {
        updateState();
    } finally {
        lock.unlock();
    }
}
~~~

This is an illustrative method; `updateState()` belongs to the application. `lockInterruptibly()` allows the thread to stop **the lock-waiting phase** with `InterruptedException`. Enter `try/finally` only after the lock has been successfully acquired, so `unlock()` is not called if acquisition fails due to an interrupt.

For `tryLock(timeout, unit)`, distinguish:
- Returns `true`: the lock was acquired and must be unlocked when done.
- Returns `false`: the wait timed out without acquiring the lock.
- Throws `InterruptedException`: cancelled during the wait phase, **not** a normal timeout result.

### 9.3. Condition.await can be interrupted

With a `Condition` created from a `Lock`, `await()` is an interruptible waiting mechanism. Code must place the condition check inside a `while` loop to handle spurious wakeups and competing state changes. When `await()` returns or throws, the thread is required to reacquire the lock per the `Condition` contract before leaving `await`; specific API details should be consulted when building a protocol. Do not write a loop calling `sleep` inside a monitor as a substitute for `Condition`, because `sleep` does not release the held monitor.

## 10. Future.cancel(true): Attempting to Cancel a Task, Not Guaranteeing the Thread Is Dead

In `ExecutorService`, the caller usually does not hold a direct reference to the `Thread` running the task. Instead, the caller holds a `Future`:

~~~java
Future<?> future = executor.submit(task);
boolean requested = future.cancel(true);
~~~

Basic contract:
- `cancel(true)` **attempts to cancel** the `Future`. If the task is already running and the worker thread is known, the executor may interrupt the thread to request a stop.
- `cancel(false)` does not request interrupting a running task, though it can prevent an unstarted task from executing.
- `Future.isCancelled()` reflects that the `Future` is in the cancelled state per contract; it **does not prove** that the worker's side effects have stopped or that cleanup has finished at that exact moment.
- `future.get()` after the `Future` is actually cancelled may throw `CancellationException`; not because the task "returned" that exception as a normal result.
- `future.get(timeout, unit)` timing out while waiting for the result will throw `TimeoutException`; **timing out while waiting for a result does not automatically cancel the task**. If cancellation is desired, the caller must decide to call `cancel(...)`.
- With APIs that do not recognize interrupts, the worker may not respond in time or may continue performing side effects after the `Future` is marked cancelled.

### Code Pattern Example

~~~java
java.util.concurrent.ExecutorService pool =
        java.util.concurrent.Executors.newSingleThreadExecutor();

java.util.concurrent.Future<?> future = pool.submit(() -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            performOneStep();
        }
    } finally {
        cleanupResources();
    }
});

try {
    future.get(500, java.util.concurrent.TimeUnit.MILLISECONDS);
} catch (java.util.concurrent.TimeoutException e) {
    future.cancel(true); // request cancellation, not forced termination
} finally {
    pool.shutdown();
}
~~~

This is an **integration snippet**: `performOneStep()` and `cleanupResources()` are application functions; `InterruptedException` and `ExecutionException` from `Future.get` must be handled per the enclosing method's contract. Importantly, `performOneStep()` must have an exit strategy when interrupted or have its own timeout; the loop condition is only checked **after** it returns.

In production, after `shutdown()` you may need `awaitTermination` with a deadline and a `shutdownNow` fallback, along with reporting if tasks still have not terminated. Do not rely on a cancelled `Future` to guarantee that every file/connection has been closed.

## 11. Standalone Example 3: Cancelling a Future, Worker Handles Interrupt Itself

This example uses `CountDownLatch` to know the task has started, then calls `cancel(true)`. The worker is waiting via `Thread.sleep()`; when interrupted, it enters `catch`, records the cancellation request, and finishes. The caller does not use `Future.get()` to prove cleanup; instead, it uses a separate completion latch.

Save **FutureCancellationDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancellationDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean detected = new AtomicBoolean(false);

        try {
            Future<?> future = pool.submit(() -> {
                try {
                    started.countDown();
                    Thread.sleep(60_000);
                } catch (InterruptedException e) {
                    detected.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            started.await();
            boolean cancelled = future.cancel(true);
            finished.await();

            System.out.println("cancelled=" + cancelled);
            System.out.println("futureCancelled=" + future.isCancelled());
            System.out.println("workerDetected=" + detected.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac FutureCancellationDemo.java
java FutureCancellationDemo
~~~

Output when the task has not completed before the cancellation request and there is no external interruption:

~~~text
cancelled=true
futureCancelled=true
workerDetected=true
~~~

**Reasoning:**
1. `started.await()` tells main that the task has run up to the signal point. The worker is about to `sleep()`, and may or may not have started sleeping yet.
2. `future.cancel(true)` requests interrupting the worker while the task is running. In this scenario, `sleep` detects the interrupt whether the signal arrived before or during sleep, and throws `InterruptedException`.
3. The worker catches the exception, records `detected=true`, restores the flag, and calls `finished.countDown()` in `finally`.
4. `finished.await()` ensures the caller **waits for the cleanup logic in the `Runnable` to pass through `finally`**; this provides stable visibility for `detected`. Also distinguish `finished.countDown()` from the thread pool worker actually terminating: the pool may keep the worker alive to execute the next task.
5. `pool.shutdown()` stops accepting new tasks; `awaitTermination` bounds the wait time for the executor to close. `shutdownNow()` only attempts to interrupt running workers and does not forcibly terminate all tasks.

**Scheduling note:** If a very short task had already completed **before** the caller called `cancel(true)`, `cancel` could return `false`. The example intentionally chooses a long sleep task and a start latch so that under normal execution the task cannot finish before main requests cancellation. This is not a benchmark or an absolute timing guarantee across all environments.

## 12. Differences Between ExecutorService.shutdown and shutdownNow

| API | Meaning | Does it interrupt running tasks? |
|---|---|---|
| `shutdown()` | Stops accepting new tasks; already submitted tasks continue per executor policy | **Does not** request interrupts solely due to shutdown |
| `shutdownNow()` | Attempts to stop running tasks and prevents/drains unstarted tasks | **Typically** uses interrupts, but does not guarantee every task stops immediately |
| `awaitTermination(timeout, unit)` | Waits for the executor to terminate up to a specified timeout | Does not itself perform worker cancellation |
| `Future.cancel(true)` | Requests cancellation of **one task** and may interrupt the thread running that task | Yes, when feasible and the task is still running |
| `Future.cancel(false)` | Requests cancellation without attempting to interrupt the running thread | No |

`shutdownNow()` returns a list of waiting tasks that had not started in a compliant executor. It is **not a list of all incomplete tasks** in every business sense. Some running tasks may still continue if they do not respond to interrupts.

### A Shutdown Pattern with a Deadline

~~~java
pool.shutdown();
try {
    if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
            System.err.println("Some tasks did not terminate");
        }
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

This is a **snippet** inside a method that has `ExecutorService pool` and imports `TimeUnit`, following the standard executor shutdown pattern seen in the JDK. Preserving the coordinator thread's interrupt status when catching `InterruptedException` is important; you should also record if workers still fail to terminate. A production policy might use an overall deadline rather than two independent wait intervals.

## 13. Timeout and Interrupt Are Not the Same Thing

A thread may need to stop because of:
- **Interrupt:** another party actively sends a cancellation request.
- **Timeout:** a wait operation exceeds its time limit.
- **Business cancellation:** business state no longer requires execution.
- **Shutdown:** the executor/application lifecycle is ending.

These cases can be related, but they are not identical:
- `Future.get(100, MILLISECONDS)` throwing `TimeoutException` only indicates that **the caller waited past the deadline**; it does not mean the task was cancelled.
- `Thread.sleep(100)` completing normally because the sleep duration elapsed does not mean the thread received a cancellation request.
- `lock.tryLock(100, MILLISECONDS)` returning `false` means **the lock was not acquired within the limit**, not that the thread was interrupted. If interrupted, it can throw `InterruptedException`.
- `Future.cancel(true)` can mark the `Future` cancelled, but side effects already performed do not automatically roll back.
- `Thread.interrupt()` can send a signal even before the worker reaches a check point, and detection/stopping has latency.

To enforce an **end-to-end business** deadline, you need to propagate the time budget across steps and set corresponding timeouts on I/O, queues, locks, and necessary processing. An interrupt flag alone does not provide a wall-clock deadline.

## 14. Thread.stop Is Not a Substitute

`Thread.stop()` is an unsafe API that has been removed from modern practice and in current JDKs is marked/implemented as **unsupported**; in JDK 17+, do not use it to forcibly stop a thread. The fundamental reason is that asynchronous stopping can corrupt data invariants when code is holding resources or halfway through updating state.

`Thread.suspend()`/`resume()` are also not reliable cancellation mechanisms: they can freeze a thread holding a monitor, causing deadlock. Never build cancellation mechanisms on these dangerous/deprecated APIs.

The standard solution is **cooperative cancellation**:
1. Tasks have a cancellation condition checked at safe points.
2. Blocking operations have an appropriate interrupt/timeout/cancel path.
3. Tasks have clear cleanup and completion protocols.
4. Callers wait for completion or handle the case where a task has not stopped after the deadline.

## 15. Interrupt and Thread State Are Not a One-to-One Map

The states `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, and `TERMINATED` describe JVM-level execution/thread-lifecycle states. **Interrupted status is a separate property**. A thread can:
- Be `RUNNABLE` with interrupted status `true` while still computing.
- Be interrupted while `TIMED_WAITING` in `sleep` and exit via `InterruptedException`.
- Be waiting to acquire an intrinsic monitor (`BLOCKED`), receive an interrupt request, and still have to wait for the monitor.
- Have handled the interrupt and exited `Runnable`, transitioning to `TERMINATED` after cleanup.

`interrupt()` is not a "setState(TERMINATED)" command. When debugging, inspect the stack trace, interrupt status, wait condition, and exception handling site together; seeing `isInterrupted()==true` alone does not prove the task has finished.

### Note on Virtual Threads in Java 21+

Virtual threads are also `Thread` instances and have an interrupt status, so Java's cooperative cancellation rules still apply. However, how quickly a specific blocking operation responds/exits depends on the API and JDK version; not every I/O operation, native call, or library handles it the same way.

Virtual threads are daemon threads by design; therefore, if an application spawns many virtual threads without waiting for tasks to finish, the JVM can exit before tasks complete. Interrupts do not replace `Future.get`, `join`, structured lifecycles, or controlled executor shutdown. The examples in this article use Java 17+ platform threads to focus on the general semantics of the `Thread` API.

## 16. Cancelling at Resource Boundaries and Business Correctness

Cooperative cancellation is not simply "whenever interrupted, return immediately." You must identify **safe cancellation points**:

- **Before starting a step with side effects:** you can check the flag and skip the work if nothing has been committed yet.
- **While waiting for a resource:** use interruptible APIs and clean up ownership properly (do not unlock if not acquired; do not release a permit if not taken).
- **Inside a critical section:** preserve invariants; do not return in the middle of updating two fields and leave half-updated state.
- **After committing external side effects:** an interrupt does not automatically roll back a sent email, written file, or committed transaction. You need a separate idempotency/compensation protocol if business cancellation is required.
- **While holding a lock:** use `finally` to unlock even on exception; avoid aborting halfway without cleaning up resources.

Example with a semaphore:

~~~java
boolean acquired = false;
try {
    semaphore.acquire();       // may be interrupted before acquiring a permit
    acquired = true;
    performWork();             // application logic
} finally {
    if (acquired) {
        semaphore.release();   // only release the permit we acquired
    }
}
~~~

This is a **snippet** inside a method that has `Semaphore semaphore` and `performWork()`, and the method must declare or handle `InterruptedException`. Why use the `acquired` variable? If `acquire` throws `InterruptedException` **before a permit is granted**, the code must not release another thread's permit. The same principle applies to `ReentrantLock.lockInterruptibly()`: only unlock after acquiring.

### Do Not Force a Hard Stop on Shared Resources

In a multi-threaded system, forcing a thread to stop while it holds a monitor or is mutating state can cause other threads to observe inconsistent state or wait forever. Good cancellation design always pairs **ownership + cleanup + completion protocol**, not just a flag.

## 17. Avoiding Common Mistakes

**Mistake 1 — Treating calling `interrupt` as the worker having stopped.** There is no guarantee. The worker must cooperate, and the caller must observe completion via `join`/`Future`/latch as appropriate.

**Mistake 2 — Catching `InterruptedException` and leaving the catch block empty.** Many APIs clear the flag before throwing; swallowing the exception can cause the worker to continue indefinitely and ignore the cancellation request.

**Mistake 3 — Calling `Thread.interrupted()` instead of `isInterrupted()` during polling and continuing.** The static method clears the flag. If you do not exit immediately, the signal is lost.

**Mistake 4 — Thinking `Thread.interrupted()` checks the object before the dot.** It is a static method that checks the current thread, not an arbitrary `Thread`.

**Mistake 5 — Thinking `Thread.sleep()` stops a worker contending for a `synchronized` monitor.** `sleep` does not release held monitors and does not make intrinsic lock acquisition interruptible.

**Mistake 6 — Forgetting `finally` when a blocking method is cancelled.** Previously acquired resources may remain held, causing leaks or deadlocks.

**Mistake 7 — Calling `unlock`/`release` when `acquire` was interrupted before succeeding.** This can throw `IllegalMonitorStateException` or erroneously increment permits; track ownership properly.

**Mistake 8 — Using `Future.isCancelled` as proof that side effects have ended.** `Future` cancellation and actual worker termination are two different milestones.

**Mistake 9 — Assuming `get(timeout)` timing out cancels the task.** The timeout applies only to the caller waiting for the result. To cancel, you need `cancel` and an appropriate worker protocol.

**Mistake 10 — Retrying infinitely after an interrupt.** A task asked to cancel might never stop; check cancellation/deadlines and do not retry in a way that drops the signal.

**Mistake 11 — Using interrupt to handle an API that does not support interruption.** Read the specific contract; use timeouts, closing, or resource-appropriate cancellation hooks.

**Mistake 12 — Using `Thread.stop` or `suspend`/`resume`.** They do not guarantee state/resource safety and are not modern concurrency practices.

**Mistake 13 — Thinking `sleep`/`yield` establishes happens-before.** No. Visibility synchronization requires `Lock`/`volatile`/`latch`/`join`/`Future` or an appropriate JMM protocol.

**Mistake 14 — Thinking restoring the flag and continuing to compute forever handles cancellation.** Restoring preserves the signal, but you must still **exit or propagate the decision**. If code keeps ignoring the flag, cancellation still does not happen.

**Mistake 15 — Confusing interrupts between caller and callee.** If main is interrupted in `future.get`, the task is not automatically cancelled; if the worker is interrupted, main does not necessarily receive an `InterruptedException` of its own.

**Mistake 16 — Cancelling between multiple business updates and assuming rollback.** Interrupt is not a transaction. Invariants and compensation mechanisms must be designed separately.

## 18. Safe Cancellation Design Workflow

~~~text
Caller no longer needs the result
       |
       v
Request cancel: worker.interrupt() / future.cancel(true)
       |
       v
Does worker have check points or interruptible wait APIs?
       |                         \
      Yes                         No
       |                           |
       v                           v
Detect signal                May continue running
       |                    → needs timeout/close/cancel hook
       v
Stop at safe point, preserve invariants
       |
       v
finally/try-with-resources cleanup
       |
       v
Runnable/Callable actually finishes
       |
       v
Caller waits/records completion and checks outcome
~~~

At each step, ask further:

1. **Who owns the task?** Does the caller still hold the `Thread`/`Future` to request cancellation and observe completion?
2. **Who has permission to interrupt?** Coordinators should only issue requests according to the executor's contract and should not arbitrarily interrupt thread pool workers.
3. **Is the task doing CPU work or blocking waits?** CPU work needs periodic polling; blocking work needs APIs supporting interrupts/timeouts.
4. **What happens when `InterruptedException` is caught?** Propagate, restore the flag and return, or apply a specific documented policy?
5. **Which resources need cleanup?** Locks, permits, streams, files, connections, temporary state.
6. **Have side effects been committed?** Are idempotency, compensation, or "partial success" results needed?
7. **Who waits for completion?** Is there a deadline and logic for when the worker is still running after a cancellation request?
8. **Are there metrics and logs distinguishing timeout, cancellation, and failure?** Do not lump every outcome into "system error."

## 19. Self-Check Exercises

**Question 1.** Thread A computes in a `while(true)` loop without checking for interruption. B calls `A.interrupt()`. Must A stop?

**Answer:** No. Interrupt does not forcibly terminate CPU code. A must actively check the flag/cancellation point or call an API that responds to interrupts.

**Question 2.** When `Thread.sleep()` throws `InterruptedException`, what does `Thread.currentThread().isInterrupted()` typically return in the `catch` block?

**Answer:** `false` for `Thread.sleep` per its contract: the flag is cleared before throwing. If you want to preserve the signal when not rethrowing, call `Thread.currentThread().interrupt()`.

**Question 3.** How do `Thread.interrupted()` and `Thread.currentThread().isInterrupted()` differ?

**Answer:** Both check the current thread when called as shown above, but `Thread.interrupted()` **clears the flag**, whereas `isInterrupted()` does not.

**Question 4.** Main is interrupted while in `worker.join()`. Does this prove the worker was interrupted?

**Answer:** No. Interruption affects the thread waiting in `join`, which is main. To request cancelling the worker, main must take a separate action appropriate to the ownership/protocol.

**Question 5.** `Future.get(200, MILLISECONDS)` times out. Has the task been automatically cancelled?

**Answer:** Not yet. That is only a timeout of the wait for the result. The caller can choose `future.cancel(true)` if it wants to issue a cancellation request.

**Question 6.** When `lock.lockInterruptibly()` is interrupted before acquiring the lock, should `lock.unlock()` be called in `finally`?

**Answer:** No. Only unlock if acquired. Place `try/finally` **after** the successful acquire call or use a variable tracking ownership.

**Question 7.** Why does `shutdownNow()` not guarantee that all executor tasks have finished?

**Answer:** It only attempts to stop/interrupt workers and returns unstarted tasks within its contract. Workers that do not respond to interruption can keep running.

**Question 8.** A thread is interrupted after writing a file but before sending an event. Is the file automatically rolled back?

**Answer:** No. Interrupt is only a cancellation signal; the file write is a separate side effect. You must have a business protocol for partial completion, idempotency, and recovery.

## 20. Official Documentation

- **Thread (Java 21), Thread Interruption section:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html
- **Future (Java 21), cancel section:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html
- **ExecutorService (Java 21), shutdown/shutdownNow/awaitTermination section:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **ReentrantLock (Java 21), lockInterruptibly:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
- **BlockingQueue (Java 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- **JLS `17, Threads and Locks:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html

**Conclusion:** `interrupt()` only **sends a cancellation request**; it does not "kill" a thread. The worker must **cooperate to detect it**, choose a safe stopping point, clean up, and actually finish; the caller must observe completion. `InterruptedException` is typically how blocking APIs turn a cancellation request into control flow, while `Future.cancel(true)` and `shutdownNow()` are also only cancellation attempts. System correctness comes from **cancellation protocols, ownership, cleanup, and invariants**, not from a single interrupt call.
