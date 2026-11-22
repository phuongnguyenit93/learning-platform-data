# `lockInterruptibly()` and Cancellation Support When Waiting for a Lock in Java

## 1. The Problem: A Thread Needs a Lock but Cannot Wait Forever

In a concurrent Java program, multiple threads may need to access a shared resource. `Lock` and `ReentrantLock` help protect critical sections, but there are situations where a thread **has not yet acquired the lock** because another thread is holding it.

If you only call `lock.lock()`, the thread will keep waiting until it acquires the lock, even if an `interrupt()` request arrives while waiting. This may be unsuitable for tasks that require **timely cancellation**: the user canceled the operation, the request expired, the service is shutting down, or a computation branch is no longer needed.

`Lock.lockInterruptibly()` is a lock acquisition method that **can be interrupted while waiting**. It allows a thread to respond to `Thread.interrupt()` with an `InterruptedException` instead of continuing to wait for the lock to be released.

Example scenario:

- Worker A holds the lock on a data structure and performs a relatively long task.
- Worker B needs the same lock, so it must wait.
- The system requests cancellation of B before B acquires the lock.
- If B uses `lockInterruptibly()`, the interrupt request can cause B to exit the waiting step without entering the critical section.
- If B uses `lock()`, the interrupt request **does not automatically end the lock wait**; B may only acquire the lock after A releases it, and subsequent code must check the interrupt status itself.

**Scope:** behavior of lock APIs and the interrupt mechanism of **Java concurrency in general**, independent of any framework. This article clearly explains **cancellation while waiting for a lock**, rather than equating an interrupt with the JVM forcibly terminating a thread.

## 2. Core API and Contract

`java.util.concurrent.locks.Lock` defines:

```java
void lock();
void lockInterruptibly() throws InterruptedException;
boolean tryLock();
boolean tryLock(long time, TimeUnit unit)
        throws InterruptedException;
void unlock();
```

These are **abbreviated API signatures for illustration**, not a standalone Java class. `TimeUnit` belongs to `java.util.concurrent`.

With the common implementation `ReentrantLock`:

1. `lockInterruptibly()` attempts to acquire the lock. If it can be acquired and there is no pending interrupt to handle, it returns normally and the caller **now owns the lock**.
2. If the lock is held by another thread, the caller waits according to the lock's mechanism; when the waiting thread is interrupted, it can exit the wait queue with an `InterruptedException`.
3. If the thread already has its interrupted status set when calling `lockInterruptibly()`, it throws `InterruptedException` even if the lock is available; this operation prioritizes responding to the interrupt over normal acquisition/reentrancy per `ReentrantLock`'s contract.
4. If `lockInterruptibly()` throws `InterruptedException` during lock acquisition, the caller **must not assume it acquired the lock from that call**; never call `unlock()` unconditionally.
5. If `lockInterruptibly()` returns normally, the caller must **always release the lock** after the critical section, typically using `try/finally`.

Standard pattern:

```java
lock.lockInterruptibly();    // May throw InterruptedException before acquiring the lock.
try {
    // Only reaches here once the lock has been acquired.
    updateSharedState();
} finally {
    lock.unlock();
}
```

This is an illustrative snippet inside a method that declares or handles `InterruptedException`; `lock` and `updateSharedState()` are defined by the application. Note that `try` only begins **after** `lockInterruptibly()` succeeds. If you place `lockInterruptibly()` inside a `try/finally` block that calls `unlock()` unconditionally, an exception could cause the code to attempt releasing a lock it never owned and throw `IllegalMonitorStateException`.

## 3. Comparing `lock()`, `lockInterruptibly()`, and Both Forms of `tryLock()`

| API | If the lock is busy | Response to interrupt while waiting | Timeout | Result |
| --- | --- | --- | --- | --- |
| `lock.lock()` | Waits until the lock is acquired | With `ReentrantLock`, continues waiting; preserves/restores interrupt status upon return | No | `void`; returning means the lock is acquired |
| `lock.lockInterruptibly()` | Waits for the lock with interruption support | Throws `InterruptedException` and exits the wait | No | `void`; returning normally means the lock is acquired |
| `lock.tryLock()` | **Does not wait**, returns immediately | Not an interruptible waiting API | No | `true` if acquired, `false` otherwise |
| `lock.tryLock(timeout, unit)` | Waits up to the requested duration | Throws `InterruptedException` while waiting or if already interrupted before calling | Yes | `true` if acquired; `false` if the deadline expires |

**Do not confuse:** `lockInterruptibly()` **does not set a timeout on its own**. If no one calls `interrupt()` and no one releases the lock, the thread can still wait indefinitely. To enforce a time limit, use `tryLock(timeout, unit)` and handle both `false` and `InterruptedException`.

With `ReentrantLock`, `lock()` is an uninterruptible lock acquisition method *during the lock-waiting phase*. If interrupted while waiting, it may still wait until the lock is acquired; the interrupt status is preserved/restored for subsequent code to observe. This **does not mean** `interrupt()` has no effect at all: the interrupt call is a cooperative signal that other APIs or code after acquiring the lock can handle.

With `synchronized(monitor)`, **waiting to enter a monitor** also has no overload that can be canceled via `InterruptedException` or a deadline. You cannot directly replace `synchronized` with an "interruptible" syntax. When lock-wait cancellation is required, `ReentrantLock` has an API advantage.

## 4. `Thread.interrupt()` Is a Cooperative Request, Not a Forced Stop

`Thread.interrupt()` sets the interrupt status or causes certain interruptible waiting operations to throw `InterruptedException`. It **does not** force the thread to stop immediately, does not roll back updates already made, and does not automatically release locks the thread is holding.

Distinguish three moments in time:

### 4.1. Interrupt Before Acquiring the Lock

If a worker is waiting at `lockInterruptibly()`, an interrupt request allows it to throw `InterruptedException` and leave the wait queue. The worker does not enter the lock-protected processing section.

### 4.2. Interrupt After Acquiring the Lock

Once `lockInterruptibly()` has **returned normally**, the worker owns the lock. A subsequent interrupt **does not automatically release the lock** and does not automatically stop the critical section. The worker must cooperate: check the signal, handle `InterruptedException` from other blocking methods, preserve data invariants, and then exit `try/finally` to release the lock.

### 4.3. Interrupt While Waiting on Other APIs

`Thread.sleep()`, `Object.wait()`, `Thread.join()`, `Condition.await()`, and other interruptible waiting methods have their own interrupt contracts. Every exception exit path out of a critical section must be managed so that `finally` releases the acquired lock.

**Important example:** a worker has entered the critical section and is calling `Thread.sleep()`. If interrupted, `sleep` throws `InterruptedException`; execution must exit through `finally` to call `unlock()`. Using `lockInterruptibly()` at the start only solves **waiting to acquire the lock**; it does not replace designing cancellation logic inside the critical section.

## 5. Deterministic Example: Canceling a Worker Waiting on `lockInterruptibly()`

The program below uses `CountDownLatch` for coordination: **main holds the lock**, the worker prepares to acquire the lock, main issues an interrupt request, the worker exits the wait path, and main verifies that it still holds the lock. It does not rely on `Thread.sleep` to guess when the worker is actually blocked.

Create the file `InterruptibleLockDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch attempting = new CountDownLatch(1);

        lock.lock(); // Main intentionally holds the lock when worker starts.
        try {
            Thread worker = new Thread(() -> {
                attempting.countDown();

                try {
                    lock.lockInterruptibly();
                } catch (InterruptedException e) {
                    System.out.println("worker: bị hủy khi xin khóa");
                    Thread.currentThread().interrupt();
                    return;
                }

                try {
                    System.out.println("worker: đã vào vùng bảo vệ");
                } finally {
                    lock.unlock();
                }
            }, "worker");

            worker.start();
            attempting.await();
            worker.interrupt();
            worker.join();

            System.out.println("main giữ khóa: "
                    + lock.isHeldByCurrentThread());
        } finally {
            lock.unlock();
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac InterruptibleLockDemo.java
java InterruptibleLockDemo
```

Output when there is no external interrupt request for main:

```text
worker: bị hủy khi xin khóa
main giữ khóa: true
```

Step-by-step reasoning:

1. Main calls `lock.lock()` before creating the worker and **does not release the lock before `worker.join()`**.
2. The worker signals `attempting.countDown()` and then calls `lock.lockInterruptibly()`.
3. Main receives `attempting.await()` and calls `worker.interrupt()`.
4. If the worker has not yet called `lockInterruptibly()`, the interrupted flag is already set and the upcoming call throws an exception. If the worker is already waiting for the lock, the interrupt wakes the wait operation and causes it to throw an exception. **In both cases, the worker cannot acquire the lock from main.**
5. The worker prints the cancellation line, restores the interrupt status, and exits the runnable. `join()` ensures main prints after the worker.
6. Main continues holding the lock until `finally`. Therefore, the line “worker: đã vào vùng bảo vệ” cannot appear on this execution path.

**Why is `lock.unlock()` in the worker not called on cancellation?** Because the releasing `try/finally` block is placed **after** `lockInterruptibly()` returns successfully. When `InterruptedException` occurs, the worker exits from the catch branch; it does not own the lock, so it must not call `unlock()`.

The example calls `Thread.currentThread().interrupt()` before `return` so that calling layers (if any) do not lose the cancellation information. For a method that allows `throws InterruptedException`, a cleaner approach is often to **propagate the exception** rather than catching and restoring the flag at every layer.

## 6. Comparison by Example: `lock()` Still Waits Despite Interrupt

In the next example, main continues to hold the lock when sending the interrupt. The worker uses `lock()`, so the interrupt **does not cause the lock acquisition step to return via an exception**. Only after main releases the lock can the worker enter the critical section and check the interrupt flag.

Create the file `NonInterruptibleLockDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class NonInterruptibleLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch attempting = new CountDownLatch(1);

        lock.lock();
        Thread worker = new Thread(() -> {
            attempting.countDown();
            lock.lock();
            try {
                System.out.println("worker đã lấy khóa, interrupted="
                        + Thread.currentThread().isInterrupted());
            } finally {
                lock.unlock();
            }
        }, "worker");

        try {
            worker.start();
            attempting.await();
            worker.interrupt();

            System.out.println("main: sẽ nhả khóa");
        } finally {
            lock.unlock();
        }

        worker.join();
        System.out.println("main: worker đã xong");
    }
}
```

```bash
javac NonInterruptibleLockDemo.java
java NonInterruptibleLockDemo
```

Output with `ReentrantLock`, when main is not interrupted externally:

```text
main: sẽ nhả khóa
worker đã lấy khóa, interrupted=true
main: worker đã xong
```

Explanation:

- Main still holds the lock when calling `worker.interrupt()`, so the worker cannot acquire the lock early.
- The worker uses `lock()`, so it does not throw `InterruptedException` from the lock acquisition operation.
- With `ReentrantLock`, if interrupted while waiting, the method continues waiting and then returns with the interrupt status preserved/restored. The flag is visible to code after the lock has been acquired.
- Main prints before releasing the lock in `finally`, so the order of the three lines is deterministic thanks to `join()` and the lock.

**Do not misinterpret:** because the worker already has the interrupted status after `lock()` returns, a subsequent `Thread.sleep()` call may throw `InterruptedException` immediately. Code must not ignore this if it requires safe cancellation.

If the business logic genuinely forbids cancellation during lock acquisition, `lock()` may be appropriate. However, if a task waits for a long time or is blocked by another resource, choosing `lockInterruptibly()` makes the system respond better to cancellation requests.

## 7. When to Use `tryLock(timeout, unit)`?

`lockInterruptibly()` has no built-in deadline. A task that only needs to wait **for at most a certain duration** can use:

```java
boolean acquired = lock.tryLock(250, TimeUnit.MILLISECONDS);
if (!acquired) {
    // Timed out, lock not acquired.
    return;
}
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

This is an illustrative snippet inside a method that handles `InterruptedException`, with `lock` and `updateSharedState()`. Unlike `lockInterruptibly()`, this API can return `false` when the deadline expires. It **still supports interruption** while waiting and can throw `InterruptedException`.

### Example Not Dependent on Timeout Luck

Create the file `TimedTryLockDemo.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class TimedTryLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();

        lock.lock();
        try {
            Thread worker = new Thread(() -> {
                boolean acquired;
                try {
                    acquired = lock.tryLock(100, TimeUnit.MILLISECONDS);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    System.out.println("worker: bị ngắt");
                    return;
                }

                if (!acquired) {
                    System.out.println("worker: hết thời gian chờ");
                    return;
                }

                try {
                    System.out.println("worker: đã lấy khóa");
                } finally {
                    lock.unlock();
                }
            }, "worker");

            worker.start();
            worker.join(); // Main continues holding the lock until worker finishes.
        } finally {
            lock.unlock();
        }

        System.out.println("main: hoàn thành");
    }
}
```

```bash
javac TimedTryLockDemo.java
java TimedTryLockDemo
```

Output when there is no unexpected interrupt:

```text
worker: hết thời gian chờ
main: hoàn thành
```

Because main holds the lock throughout `worker.join()`, the worker is guaranteed not to acquire the lock within the deadline and must receive `false`. This is a test demonstrating a deadline; **you should not model real system architecture by holding a lock while waiting for a worker that cannot make progress**. For work involving shared resources, avoid holding locks longer than necessary.

One subtlety: the timeout measures **a maximum wait duration per the API contract, subject to scheduling and system time**; application code should not treat `100 ms` as an exact hard boundary. Avoid using `sleep(100)` to verify concurrency logic in tests.

### Non-Timed `tryLock()` Is Another Option

`lock.tryLock()` attempts to acquire the lock immediately and returns `true` or `false`. If the application has an immediate fallback path, this may be the clearest API:

```java
if (lock.tryLock()) {
    try {
        doWork();
    } finally {
        lock.unlock();
    }
} else {
    doSomethingElse();
}
```

This is an illustration, not a standalone program. `tryLock()` does not wait for an interrupt. Furthermore, on a `ReentrantLock` configured as fair, `tryLock()` does not fully participate in the queue fairness policy; it can "barge" when the lock is free. If queue fairness is required, you need to understand the specific contract of `tryLock(timeout, unit)`.

## 8. Distinguishing Interrupt While Waiting for a Lock vs. Interrupt Inside a Critical Section

Do not write:

```java
lock.lockInterruptibly();
try {
    performLongRunningTask();
} finally {
    lock.unlock();
}
```

and conclude that `performLongRunningTask()` is guaranteed to stop immediately when `Thread.interrupt()` is called. Once the lock has been acquired, the task's cancellation behavior depends on **the contents of that method**.

If CPU-bound work loops many times, consider checking the interrupt status at safe points:

```java
lock.lockInterruptibly();
try {
    for (int i = 0; i < batches.size(); i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("cancelled during work");
        }
        processBatch(batches.get(i));
    }
} finally {
    lock.unlock();
}
```

This is illustrative code inside a method declaring `throws InterruptedException`; `batches` and `processBatch` represent application data/logic. Throwing an exception inside `try` still executes `finally` and releases the lock.

However, **do not abandon a multi-step data modification in an invalid state** just because the thread was interrupted. In critical sections that maintain invariants, design one of the following approaches:

- Check for interrupts **before starting an internal transaction**;
- Complete or roll back an atomic unit of change before responding to cancellation;
- Split the work into smaller parts with consistent commit points;
- Use appropriate transactions/compensation if external non-JVM resources are involved.

`ReentrantLock` only provides mutual exclusion and memory visibility relationships; it does not roll back in-progress changes when an exception or interrupt occurs.

### The Interrupt Flag Is Also Control Data

`Thread.currentThread().isInterrupted()` reads the thread's status **without clearing the flag**. `Thread.interrupted()` is a static method that reads and **clears the flag** of the current thread. They are not arbitrarily interchangeable.

For example:

```java
if (Thread.currentThread().isInterrupted()) {
    // Cancellation signaled, flag remains set.
}
```

Conversely, calling `Thread.interrupted()` multiple times without a new interrupt may return `true` the first time and `false` thereafter. Without a clear reason, do not inadvertently consume the interrupt status before another component has a chance to handle it.

## 9. `InterruptedException` and Restoring the Interrupt Status

When an interruptible waiting API throws `InterruptedException`, the thread's interrupt status is typically **cleared when the exception is thrown** according to that API's contract (including `ReentrantLock.lockInterruptibly()`). This avoids propagating the same signal through two different mechanisms unintentionally.

There are two common ways to handle it:

**Approach A — propagate the exception to the caller** when the method signature permits:

```java
void transfer() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        updateBalances();
    } finally {
        lock.unlock();
    }
}
```

**Approach B — restore the flag and exit the work** when the exception cannot be declared at the current layer:

```java
void runTask() {
    try {
        lock.lockInterruptibly();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
    try {
        updateBalances();
    } finally {
        lock.unlock();
    }
}
```

These are **two illustrative snippets**, with `lock` and `updateBalances()` declared in the appropriate class. Approach B restores the flag because `Runnable.run()` cannot declare the checked exception `InterruptedException`.

Common mistake:

```java
try {
    lock.lockInterruptibly();
} catch (InterruptedException ignored) {
    // Ignoring it and continuing as if lock were held: WRONG.
}
updateBalances(); // May access state without holding the lock.
```

Do not catch the exception and **proceed as if you had acquired the lock**. When interrupted while acquiring the lock, you must exit the task, propagate the exception upward, or have a clearly designed retry mechanism. If you retry indefinitely regardless of interrupts, you defeat the cancellation capability that was the reason for choosing `lockInterruptibly()`.

Additionally, catching and restoring the flag *is not enough* if the code continues running and unexpectedly invokes other blocking APIs. Clearly define the "canceled" state and the task's exit path.

## 10. Canceling an `ExecutorService` Task with `Future.cancel(true)`

In Java, many tasks are submitted to an `ExecutorService` rather than creating individual `Thread`s manually. To cancel a running task, `Future.cancel(true)` **requests an interrupt on the thread executing the task** (when supported by the executor per its contract). When the task is waiting at `lockInterruptibly()`, the interrupt request can cause it to leave the wait step.

Create the file `FutureLockCancellationDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.locks.ReentrantLock;

public class FutureLockCancellationDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch attempting = new CountDownLatch(1);
        CountDownLatch taskExited = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        lock.lock(); // Main intentionally holds the lock when the task is submitted.
        try {
            Future<?> future = executor.submit(() -> {
                try {
                    attempting.countDown();
                    lock.lockInterruptibly();
                    try {
                        System.out.println("task: đã lấy khóa");
                    } finally {
                        lock.unlock();
                    }
                } catch (InterruptedException e) {
                    System.out.println("task: dừng chờ khóa");
                    Thread.currentThread().interrupt();
                } finally {
                    taskExited.countDown();
                }
            });

            attempting.await();
            boolean cancelled = future.cancel(true);
            taskExited.await();
            System.out.println("future cancelled=" + cancelled);
        } finally {
            lock.unlock();
            executor.shutdown();
        }
    }
}
```

```bash
javac FutureLockCancellationDemo.java
java FutureLockCancellationDemo
```

Output when there is no external interrupt request for main:

```text
task: dừng chờ khóa
future cancelled=true
```

Why the output is deterministic:

1. Main already holds `lock`, so the task cannot acquire the lock before cancellation.
2. `attempting.countDown()` ensures main only calls `cancel(true)` after the task's runnable has started.
3. `future.cancel(true)` marks the cancellation request and sends an interrupt to the thread executing the task. The task responds at `lockInterruptibly()`, enters `catch`, and exits the wait path.
4. `taskExited.await()` forces main to wait for the task's `finally` block to execute, so the task's message prints before the result line.
5. Main only releases the lock and calls `executor.shutdown()` after those steps.

**Warning:** `Future.isCancelled() == true` or `cancel(true)` returning `true` **does not mean the task has actually stopped and finished cleaning up** in all programs. The Future may transition to the canceled state before the worker finishes cleanup; if the task ignores the interrupt, it may even continue running. In the example, `taskExited` is used to confirm a specific cleanup point. Do not rely solely on `Future.get()` after cancellation to wait for cleanup to finish, because calling `get()` on a canceled Future throws `CancellationException`.

`cancel(false)` does not request interrupting a running task; therefore, it cannot be expected to wake up a task blocked at `lockInterruptibly()`. `ExecutorService.shutdownNow()` also sends interrupt signals to the best of the executor's ability, but does not guarantee every task stops immediately. Designing tasks to **cooperate with interrupts** is the responsibility of application code.

## 11. Does `lockInterruptibly()` Help Avoid Deadlock?

**It can help a thread exit a lock wait when canceled**, but it does not automatically detect or prevent all deadlocks.

Consider two resources with two `ReentrantLock`s:

```text
Thread A: giữ lock X ───> chờ lock Y
Thread B: giữ lock Y ───> chờ lock X
```

If the second lock acquisition steps both use `lockInterruptibly()`, the system can **deliberately send an interrupt** to one of the waiting threads. That thread catches `InterruptedException` and exits its `finally` blocks to release the locks it already acquired, thereby breaking the wait cycle.

However, several conditions must be met:

- There must be a component that detects timeouts, receives cancellation requests, or decides which thread to interrupt. `lockInterruptibly()` itself **does not detect deadlock**.
- Every acquired lock must be released in `finally`, even if the next lock acquisition step is interrupted.
- A task must not remain holding a lock elsewhere due to improper exception handling or because it is waiting on an operation that **does not support interruption**.
- Invariants must not be broken when exiting from the middle of a multi-step update operation.

Pattern for acquiring two locks with a clear cleanup path:

```java
first.lockInterruptibly();
try {
    second.lockInterruptibly();
    try {
        changeBothResources();
    } finally {
        second.unlock();
    }
} finally {
    first.unlock();
}
```

This is an illustrative snippet assuming `first` and `second` are `Lock`s and `changeBothResources()` is defined in the application. If interrupted while waiting for `second`, only `first` has been acquired, so the outer `finally` releases it. If interrupted while waiting for `first`, neither `try` block has been entered, so `unlock()` is not called.

**The primary deadlock prevention measure remains consistent lock ordering** (for example, always locking in ascending order of resource ID) and minimizing nested lock holding. Interruptible acquisition is a supporting layer for cancellation/recovery, not a substitute for proper lock design.

## 12. `ReentrantLock` Contract, Fairness, and Reentrancy

`ReentrantLock` is a reentrant implementation of `Lock`. A thread that already holds the lock can reacquire the same lock (incrementing the hold count), and must release it the same number of times it was acquired. With `lockInterruptibly()`, **if the thread is already interrupted**, the call may throw `InterruptedException` immediately rather than reentering the lock, following the contract that prioritizes interrupt handling. Do not write code assuming this call is guaranteed to succeed just because the current thread already holds the lock.

With `ReentrantLock(true)` (a fair lock), lock waiting in `lock()` and `lockInterruptibly()` generally follows a policy of favoring longer-waiting threads under contention. However:

- Fairness does not guarantee CPU scheduling order or maximum latency.
- Non-timed `tryLock()` can acquire the lock immediately if it is free, even if other threads are waiting, per `ReentrantLock`'s contract.
- Fair locking typically carries a throughput tradeoff; choose based on measurements and application requirements.
- Reentrancy does not change the requirement to call `unlock()` the exact number of times and from the exact thread holding the lock.

`isLocked()` only indicates whether some thread holds the lock at the moment of the check. It **does not** mean the current thread is allowed to release it. `isHeldByCurrentThread()` helps diagnose ownership by the current thread, but you should design acquire/release branches properly rather than relying on status checks to patch a broken locking protocol.

## 13. Thread State When Waiting on `ReentrantLock`

When a thread waits on `ReentrantLock`, the Java implementation typically blocks via `java.util.concurrent.locks` synchronization mechanisms (such as `LockSupport.park`). The state observed via `Thread.getState()` may be `WAITING`, or `TIMED_WAITING` when a timeout is used.

**Do not assume every thread waiting on a lock is in `BLOCKED`.** By definition of `Thread.State`, `BLOCKED` is for threads waiting to enter a `synchronized` monitor. A thread waiting on `ReentrantLock` does not necessarily appear like a thread waiting for an intrinsic monitor.

Although `getState()` is useful for diagnostics, it is only a snapshot. Do not check `worker.getState() == WAITING` and infer that the worker has definitely called the right API. To write deterministic tests, use `CountDownLatch`/`Phaser`/appropriate coordination, and then assert the expected behavior via results, as shown in the examples in this article.

The difference between platform threads and virtual threads (Java 21+) does not change **the contract of `Lock.lockInterruptibly()`**: a waiting thread can respond to an interrupt. How the JVM manages carrier threads when a virtual thread parks is a scheduling detail; it should not be used as a reason to skip cancellation checks or lock-release logic. Actual interruptibility and blocking behavior should still be verified against the libraries, JDK, and workload in use.

## 14. Relationship with `Condition.await()`

`ReentrantLock` is often combined with `Condition` to wait for a **data condition**, not just to wait for lock acquisition. These two actions are different:

1. **`lock.lockInterruptibly()`:** waits for **lock** ownership.
2. **`condition.await()`:** the caller **already holds the lock**, temporarily releases it, and waits for the condition to be signaled; upon returning, the caller reacquires the lock before continuing per the Condition contract.

Illustrative example:

```java
lock.lockInterruptibly();
try {
    while (!ready) {
        condition.await();
    }
    consumeReadyData();
} finally {
    lock.unlock();
}
```

This is an illustrative snippet where `lock` and `condition` are created from `lock.newCondition()`, while `ready` and `consumeReadyData()` are defined by the application.

`Condition.await()` is also typically interruptible and throws `InterruptedException`. Therefore, whether an interrupt occurs during **the lock acquisition phase** or **the condition-waiting phase after acquiring the lock**, the code must handle the contract properly:

- If `lockInterruptibly()` throws an exception, **there is no lock** to release.
- If `condition.await()` throws an exception, the caller had previously acquired the lock; per the appropriate `Condition` contract, the wait manages releasing/reacquiring the lock before returning/throwing; the outer `finally` block must still call `unlock()`.
- Check the condition inside a `while` loop rather than just an `if`, because a wakeup does not guarantee the condition is true.

Do not use `Thread.sleep()` while holding a `ReentrantLock` to wait for another thread to modify `ready` under the same lock: `sleep` does not release the lock, preventing the other thread from updating the data. `Condition.await()` is the appropriate condition-waiting mechanism for `ReentrantLock`.

## 15. Responsible Cancellation: Resource Cleanup and Consistency

Supporting fast cancellation is an important goal, but **do not trade away valid data state for it**.

### 15.1. Place Cancellation Points at Safe Boundaries

If a task only reads or performs independent work, it can check for interrupts frequently. If a task holds a lock to update multiple related fields, define a business-atomic unit (an in-memory transaction or a batch) and only cancel at points that do not break invariants.

### 15.2. Do Not Release a Lock That Was Never Acquired

Lock-release code must only run on the successful acquisition path:

```java
try {
    lock.lockInterruptibly();
    try {
        doWork();
    } finally {
        lock.unlock();
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
}
```

This snippet illustrates how to nest `try/finally`. It is valid with respect to unlocking because the inner `finally` is only entered after `lockInterruptibly()` has returned. If after catching the exception the task still has work requiring the lock, it must stop rather than proceeding into the protected data region without the lock.

### 15.3. Do Not Hold Locks During Uncontrolled I/O

If a critical section wraps network calls, waiting on Futures, slow file operations, or arbitrary callbacks, other threads may wait for the lock for a very long time. This increases the need for cancellation and can cause wait cycles. Whenever possible, perform computation or I/O outside the critical section, then acquire the lock briefly to check/commit data. However, **do not split a critical section in a way that violates invariants**.

### 15.4. Cancellation Policy Should Be Clearly Documented

In the API of a worker or service, answer:

- Through which channel do cancellation requests arrive: `Future.cancel(true)`, `Thread.interrupt()`, or a dedicated token?
- If the lock has not been acquired yet, is the task aborted completely?
- If the lock is currently held, is there a safe rollback/commit point?
- If a deadline expires, what status is returned and who is responsible for retrying?
- Is the exception propagated or translated into a structured error response?
- Is resource/lock cleanup confirmed before reporting "stopped"?

Never use `Thread.stop()` to forcibly terminate a thread holding a lock; it is an unsafe API and has been deprecated for a long time.

## 16. Common Mistakes

### Mistake 1 — Calling `unlock()` Even When `lockInterruptibly()` Threw an Exception

```java
try {
    lock.lockInterruptibly();
    update();
} finally {
    lock.unlock();  // May not have acquired the lock!
}
```

**Wrong.** Place the `lockInterruptibly()` call outside the `try/finally` that guards the critical section, or use a carefully managed `acquired` flag.

### Mistake 2 — Catching `InterruptedException` and Swallowing the Signal

```java
try {
    lock.lockInterruptibly();
} catch (InterruptedException ignored) {
    // Neither propagates nor restores the interrupt flag.
}
```

**Wrong if the application requires cancellation.** Propagate the exception to the caller, or restore the flag and exit the work when propagation is not possible. Do not proceed with lock-protected operations without holding the lock.

### Mistake 3 — Thinking `lockInterruptibly()` Will Stop All Code After Acquiring the Lock

This method only addresses the acquisition phase. Once the lock is acquired, the task itself must cooperate with interrupts, maintain invariants, and unlock.

### Mistake 4 — Using `lock()` and Expecting `Future.cancel(true)` to Stop Immediately

A task waiting on `ReentrantLock.lock()` can keep waiting even after being interrupted. If you need cancellation while waiting, use `lockInterruptibly()` or a timed `tryLock` with the appropriate contract.

### Mistake 5 — Failing to Distinguish Timeout from Interrupt

`tryLock(timeout, unit)` returns `false` when the time expires, whereas it **throws `InterruptedException`** when interrupted. These two situations may require different business outcomes; do not collapse both into a single generic state and lose information.

### Mistake 6 — Guessing Thread Ordering with `sleep()`

CPU scheduling is not guaranteed. In concurrency unit tests, use latches/phasers/coordination to prove preconditions and completion. Avoid writing tests based on "sleep 50 ms so the worker is probably waiting on the lock."

### Mistake 7 — Assuming `cancel(true)` Means the Task Has Cleaned Up Resources

A `Future` may be marked canceled before the task actually finishes cleanup. When cleanup verification is needed, use a dedicated signal or monitoring mechanism such as a `CountDownLatch` in the task's `finally` block.

### Mistake 8 — Using `lockInterruptibly()` While Threads Acquire Multiple Locks in Reverse Order

A thread can exit a wait cycle when interrupted, but **deadlock can still occur** if no interrupt arrives or if code fails to release held locks. Enforcing a consistent lock acquisition order remains the primary rule.

### Mistake 9 — Canceling in the Middle of a Multi-Field Update

Even if `finally` releases the lock properly, data can be left in an invalid state if half of a transaction has already executed. Complete or roll back the unit of update before leaving the critical section.

## 17. Self-Check Exercises

**Question 1.** Main holds a `ReentrantLock`, and a worker calls `lockInterruptibly()` and waits. Main calls `worker.interrupt()` without releasing the lock. Must the worker wait until main releases the lock?

**Answer:** Not necessarily. With `ReentrantLock.lockInterruptibly()`, the interrupt causes the worker to throw `InterruptedException` and exit the wait without acquiring the lock. The worker must exit the task properly; it must not call `unlock()` if it never acquired the lock.

**Question 2.** Replace `lockInterruptibly()` with `lock()` in the scenario above. Does `interrupt()` immediately cancel the wait?

**Answer:** No. With `ReentrantLock.lock()`, the worker can continue waiting until it acquires the lock. The interrupt status is preserved/restored so subsequent code can handle it.

**Question 3.** Can `lockInterruptibly()` throw `InterruptedException` even if the lock is currently free?

**Answer:** Yes. If the thread was already interrupted before the call, `ReentrantLock.lockInterruptibly()` can prioritize responding to the interrupt and throw the exception instead of acquiring the lock.

**Question 4.** A worker has acquired the lock and is updating three related fields. Main sends an interrupt. Is the lock automatically released and the data automatically rolled back?

**Answer:** No. An interrupt is a cooperative signal. The worker must handle it at a safe point, complete/roll back the updates, and exit through `finally` to release the lock.

**Question 5.** Does `tryLock(100, TimeUnit.MILLISECONDS)` returning `false` mean the worker was interrupted?

**Answer:** No. `false` means the lock was not acquired within the time limit. If the operation was interrupted while waiting, the method can throw `InterruptedException`.

**Question 6.** Why is `Future.cancel(true)` not guaranteed proof that a task has finished cleaning up?

**Answer:** Marking the Future as canceled and sending the interrupt can happen before the task actually stops. The task may ignore the interrupt or need time to release resources; a cleanup confirmation mechanism should be used if the contract requires it.

**Question 7.** A thread has acquired lock A, then calls `B.lockInterruptibly()` and is interrupted. Which lock(s) must be released?

**Answer:** It does not hold lock B because the call was interrupted. It must release lock A (which was already acquired) in `finally`; it must not call `B.unlock()` without having acquired B.

**Question 8.** With `ReentrantLock` and `Condition`, how does `lockInterruptibly()` differ from `condition.await()`?

**Answer:** `lockInterruptibly()` waits to **acquire lock ownership**. `await()` is used when the caller **already holds the lock**, temporarily releasing the lock to wait for a condition and reacquiring it before returning per the contract. Both can respond to interrupts, but they serve different phases.

**Question 9.** An application always needs to cancel if waiting for a lock takes more than 2 seconds without any thread calling `interrupt()`. Should you use `lockInterruptibly()` alone or `tryLock(2, TimeUnit.SECONDS)`?

**Answer:** Timed `tryLock` provides the required timeout while still being interruptible. `lockInterruptibly()` does not time out on its own without an interrupt request.

## 18. Summary

`lockInterruptibly()` enables **cooperative cancellation during the lock-waiting phase**, making it suitable for tasks whose lifecycle requires cancellation, shutdown, or responsiveness to interrupts. Unlike `lock()`, a thread waiting on `ReentrantLock.lockInterruptibly()` can throw `InterruptedException` without waiting for the lock to be released.

Four practical rules must always go together:

1. **Only call `unlock()` after successfully acquiring the lock.**
2. **Do not swallow `InterruptedException`**: propagate it or restore the flag and exit the task.
3. **Do not confuse cancellation while waiting for a lock with cancellation while doing work**: the body of the critical section must still check the signal at safe points and preserve invariants.
4. **Choose the API according to the waiting policy**: `lock()` if uninterruptible waiting at acquisition is genuinely required, `lockInterruptibly()` if interrupt responsiveness is needed, and `tryLock(timeout, unit)` if both a deadline and interruption are needed.

By combining proper interrupt handling, `try/finally`, deadlock-avoiding locking protocols, and task management mechanisms, a Java application can cancel work waiting on resources without leaking locks or corrupting shared data.
