# tryLock() and Timeouts Under Lock Contention in Java

## 1. Lesson Objectives

When multiple threads need to access the same state, using `synchronized` or `Lock` can protect the critical section. However, in systems under load, **waiting for a lock forever** is not always the right choice: the caller may want to try once, wait for at most a bounded duration, fail fast, or switch to another task.

`ReentrantLock` provides two important methods:

~~~java
boolean acquired = lock.tryLock();                 // try immediately, do not wait
boolean acquired = lock.tryLock(200, TimeUnit.MILLISECONDS);
// wait up to a given duration to acquire the lock, interruptible
~~~

After this lesson, you will be able to:

- Distinguish `lock()`, `lockInterruptibly()`, `tryLock()`, and `tryLock(long, TimeUnit)` in terms of waiting behavior, timeout, interruption, and return/outcome semantics.
- Correctly identify which thread owns a `ReentrantLock`; only call `unlock()` after that same thread has successfully acquired the lock.
- Explain accurately when timed `tryLock` returns `true`, returns `false`, or throws `InterruptedException`; avoid confusing lock acquisition timeout with the timeout of the entire business operation.
- Design an intentional fallback branch when a lock is busy, instead of silently skipping important work.
- Understand the difference between a fair lock and a non-fair lock, especially the fact that `tryLock()` **does not honor the fairness setting**.
- Use time bounds, deadlines, cancellation, and appropriate logging/metrics; avoid deadlocks, double unlocks, and lost interrupts.
- Run Java 17+ programs that reproduce lock contention **deterministically**, without relying on guessing thread scheduling with `sleep()`.

**Scope:** Java SE, `java.util.concurrent.locks`, and the Java Memory Model. The examples have no external library dependencies and use Java 17 or later.

## 2. ReentrantLock and Lock Ownership

`ReentrantLock` is a mutual exclusion lock: at any given time, only **one thread** owns the lock. When a thread already holds the lock, that same thread can acquire the lock again according to **reentrancy**, and each additional acquisition must be balanced by a corresponding release.

~~~java
import java.util.concurrent.locks.ReentrantLock;

class Counter {
    private final ReentrantLock lock = new ReentrantLock();
    private int value;

    void increment() {
        lock.lock();
        try {
            value++;
        } finally {
            lock.unlock();
        }
    }

    int get() {
        lock.lock();
        try {
            return value;
        } finally {
            lock.unlock();
        }
    }
}
~~~

This is a valid Java class without a `main` method, illustrating the protocol: **every read/write path to `value` uses the same lock**. When a thread acquires the lock and exits with `unlock()`, that thread's operations have memory synchronization effects equivalent to a monitor unlock; another thread that subsequently acquires the same lock establishes visibility/ordering according to the `Lock` contract and the JMM.

Unlike `synchronized`, `ReentrantLock` is **not automatically released** when a method finishes. Forgetting `unlock()` can cause other threads to wait indefinitely. Therefore, the release must always be placed in a `finally` block, provided the current thread actually owns the lock.

`tryLock` **does not mean merely reading the lock state**: when it returns `true`, it has **acquired** the lock and created the responsibility to call `unlock()`. When it returns `false`, the caller **receives no ownership** of the lock.

## 3. Four Lock Acquisition Forms to Distinguish

| API | Waits if held by another thread? | Interruption while waiting | Result contract |
|---|---|---|---|
| `lock()` | Waits until it can be acquired | Does not throw `InterruptedException` while waiting | Returns `void` once acquired. |
| `lockInterruptibly()` | Waits, but can be cancelled by interruption | Throws `InterruptedException` (if interrupted per contract) | `void` when acquired, exception when interrupted. |
| `tryLock()` | **Does not wait** | No interruptible wait phase; does not throw `InterruptedException` | `true` if acquired immediately, `false` if held by another thread. |
| `tryLock(timeout, unit)` | Waits up to the requested duration if needed | **Yes**, throws `InterruptedException` | `true` if acquired; `false` if time expires before acquisition; exception if interrupted. |

Key point to grasp: all of the APIs above can succeed **immediately when the lock is free**; `tryLock` does not mean "wait and then give up" in every case, because the no-argument overload **does not wait**.

### Diagram of timed tryLock

~~~text
             call tryLock(timeout, unit)
                         |
           already interrupted on entry?
                  /               \
               yes                 no
                |                   |
      InterruptedException     can lock be acquired?
                                   /        \
                                 yes         not yet
                                  |            |
                                true       wait up to
                                  |        timeout
                        enter critical         |
                           section        ┌────┴────────┐
                           /              |             |
                       unlock()        acquire      interrupt
                                          |             |
                                        true        exception
                                                        |
                                                expired first
                                                        |
                                                      false
~~~

This is a logical diagram for conditions and outcomes; it **does not mandate that the scheduler wake up or complete the operation at the exact timestamp**. While waiting, multiple events can arrive nearly simultaneously. `ReentrantLock` prioritizes responding to interruption per its contract, so the application must handle that branch independently from timeout.

## 4. tryLock(): Try Once, Respond Immediately

For `ReentrantLock`, `tryLock()`:

1. If the lock is not held by another thread, acquires it immediately and returns `true`.
2. If the **current thread already owns the lock**, acquires it reentrantly, increments the hold count, and returns `true`.
3. If another thread holds the lock, returns `false` **immediately**, without registering to wait for the lock to be released.
4. Does not declare `throws InterruptedException` and does not provide an interruptible wait mechanism.

Standard pattern:

~~~java
import java.util.concurrent.locks.ReentrantLock;

class NonBlockingCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int count;

    boolean tryIncrement() {
        if (!lock.tryLock()) {
            return false; // busy: caller decides whether to skip, retry, or report an error
        }
        try {
            count++;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
~~~

**The business condition must be clear:** `false` here indicates "could not acquire the lock immediately", **not** necessarily "the operation permanently failed". If the counter records a mandatory transaction, silently skipping the increment can cause **business data loss**. The caller must decide whether to queue, perform a bounded retry, return an overload status, or use another reliable mechanism.

### Why checking isLocked() then calling lock() is wrong

~~~java
if (!lock.isLocked()) {
    lock.lock(); // can still block waiting!
    try {
        doWork();
    } finally {
        lock.unlock();
    }
}
~~~

`isLocked()` only returns a momentary observation; it does not reserve the lock. Another thread can acquire the lock between `isLocked()` and `lock()`: a **check-then-act** bug. `tryLock()` combines "check availability + acquire" into **a single atomic operation per the lock contract**. Methods like `isLocked()`, `hasQueuedThreads()`, and `getQueueLength()` are better suited for observation/monitoring, not for reliably deciding whether the next thread will succeed in acquiring the lock.

## 5. Standalone Example 1: One Thread Already Holds the Lock

This program sets up an exact scenario: `main` holds the lock while another thread tries to acquire it. Because `main` only releases the lock after the other thread finishes, the result `tryLock() = false` does not depend on thread scheduling.

Save file **ImmediateTryLockDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.ReentrantLock;

public class ImmediateTryLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        AtomicBoolean acquiredByWorker = new AtomicBoolean(true);

        lock.lock(); // main owns the lock
        try {
            Thread worker = new Thread(() -> {
                boolean acquired = lock.tryLock();
                acquiredByWorker.set(acquired);
                if (acquired) {
                    try {
                        // Shared state can be processed here.
                    } finally {
                        lock.unlock();
                    }
                }
            }, "worker");

            worker.start();
            worker.join(); // main still holds the lock while worker tries
            System.out.println("whileMainHolds=" + acquiredByWorker.get());
        } finally {
            lock.unlock(); // main releases its own ownership
        }

        boolean acquiredAfterRelease = lock.tryLock();
        try {
            System.out.println("afterRelease=" + acquiredAfterRelease);
        } finally {
            if (acquiredAfterRelease) {
                lock.unlock();
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac ImmediateTryLockDemo.java
java ImmediateTryLockDemo
~~~

Output:

~~~text
whileMainHolds=false
afterRelease=true
~~~

**Explanation:**

- `main` calls `lock.lock()` and holds the lock inside the `try` block.
- `worker` is a different thread, so `worker`'s `lock.tryLock()` must return `false` while `main` has not unlocked.
- `worker.join()` completes before `main` enters `finally` to release the lock, eliminating any chance that `worker` runs after the release.
- After releasing the lock, `main` tries again and succeeds, since there is no other contender. `AtomicBoolean` is used to store the worker's result; the result is also observed after `join()`. `AtomicBoolean` is not a mechanism for fixing lock ownership.
- The example intentionally avoids `sleep()` or guessing which thread will run before/after in wall-clock time.

The `try/finally` pattern after a successful `tryLock()` must be preserved in production code. In the `false` case, `unlock()` must not be called because the thread does not hold ownership.

## 6. tryLock(long timeout, TimeUnit unit): Bounded Waiting

The timed overload:

~~~java
boolean acquired =
        lock.tryLock(150, TimeUnit.MILLISECONDS);
~~~

Key properties:

- `timeout` is a wait duration **to acquire the lock**, not a deadline for the entire work performed after acquiring it.
- If the lock is free and there are no barriers such as a fairness queue, the method can return `true` immediately.
- If another thread holds the lock, the caller can wait **up to the requested duration** according to the lock's mechanism; if it cannot acquire before the timeout expires, it returns `false`.
- If the thread is already interrupted on entry or is interrupted while attempting to acquire, `ReentrantLock` throws `InterruptedException` and **clears the interrupted status at the time of throwing**.
- With `timeout <= 0`, the method does not wait. This is still the overload with interrupt-checking semantics; on a fair lock it also honors fairness.
- `TimeUnit` must be non-`null`; passing `null` results in a `NullPointerException`.
- The return value does not bound the total actual time the caller method takes to finish. Scheduling, GC pauses, and post-acquisition processing can make total latency differ from the timeout threshold.

Typical usage pattern:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

class BoundedCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int count;

    boolean tryIncrement(long timeout, TimeUnit unit)
            throws InterruptedException {
        if (!lock.tryLock(timeout, unit)) {
            return false;
        }
        try {
            count++;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
~~~

**Note:** This is a valid class method without a `main` method. The caller must decide what `false` means. The thread may have failed to acquire the lock due to contention rather than invalid protected data. Increasing `timeout` can reduce the number of `false` returns, but increases tail latency, the number of waiting threads, and resource pressure.

## 7. Standalone Example 2: Timeout Determined by Ownership

The following example does not rely on luck regarding which thread runs first. `main` holds the lock until `worker` finishes its timed `tryLock`. `worker` cannot acquire the lock and must return `false` when the wait time expires.

Save file **TimedTryLockDemo.java**:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.ReentrantLock;

public class TimedTryLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        AtomicReference<String> result = new AtomicReference<>();

        lock.lock();
        try {
            Thread waiter = new Thread(() -> {
                try {
                    boolean acquired =
                            lock.tryLock(40, TimeUnit.MILLISECONDS);
                    if (!acquired) {
                        result.set("timeout");
                        return;
                    }
                    try {
                        result.set("acquired");
                    } finally {
                        lock.unlock();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    result.set("interrupted");
                }
            }, "timed-waiter");

            waiter.start();
            waiter.join(); // lock is still held by main when waiter times out
        } finally {
            lock.unlock();
        }

        System.out.println("result=" + result.get());
    }
}
~~~

Run:

~~~bash
javac TimedTryLockDemo.java
java TimedTryLockDemo
~~~

Output when not externally interrupted:

~~~text
result=timeout
~~~

**Verification:**
- `main` acquires the lock first and only releases it in `finally` after calling `join()` on `waiter`.
- `waiter` cannot acquire while `main` owns the lock; after the wait duration, it receives `false`, sets `"timeout"`, and exits.
- `waiter` does not call `unlock()` when it receives `false`.
- Once `waiter` finishes, `main` releases its lock and then prints. Even if the scheduler is slower than 40ms or introduces extra delay, the logical outcome remains timeout under normal execution conditions.
- This is a **behavior** test. Do not infer that the method always returns after exactly 40ms on every OS or JVM.

## 8. Interruption Is Not a Timeout

Timed `tryLock` is **interruptible**. A waiting thread can be cancelled via `Thread.interrupt()`. Per `ReentrantLock`, if interrupted upon entering the method or while waiting, it throws `InterruptedException`. This is **not** a `false` return, and the code should not treat it like a normal timeout.

Handling pattern inside a `Runnable`:

~~~java
try {
    if (!lock.tryLock(500, TimeUnit.MILLISECONDS)) {
        handleContentionTimeout();
        return;
    }
    try {
        performProtectedWork();
    } finally {
        lock.unlock();
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Stop or propagate cancellation information up to the caller.
}
~~~

This is an **illustrative snippet**, in which `handleContentionTimeout()` and `performProtectedWork()` are application-defined methods. When it is possible to declare `throws InterruptedException` and let the caller handle it, you can also propagate the exception upward.

Why restore the flag? `InterruptedException` typically **clears the interrupted status** when thrown. If code catches it without rethrowing, `Thread.currentThread().interrupt()` lets higher layers observe the cancellation request. This does not mean every operation should keep running after restoring the flag; it should terminate or follow the task contract.

### Standalone Example 3: Interrupt While a Thread Is Contending for a Lock

Save **InterruptibleTryLockDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleTryLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch ready = new CountDownLatch(1);
        AtomicReference<String> outcome = new AtomicReference<>();

        lock.lock();
        try {
            Thread waiter = new Thread(() -> {
                ready.countDown();
                try {
                    if (lock.tryLock(10, TimeUnit.SECONDS)) {
                        try {
                            outcome.set("acquired");
                        } finally {
                            lock.unlock();
                        }
                    } else {
                        outcome.set("timeout");
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    outcome.set("interrupted");
                }
            }, "interruptible-waiter");

            waiter.start();
            ready.await();
            waiter.interrupt();
            waiter.join();
        } finally {
            lock.unlock();
        }

        System.out.println("result=" + outcome.get());
    }
}
~~~

Run:

~~~bash
javac InterruptibleTryLockDemo.java
java InterruptibleTryLockDemo
~~~

Output when no other cancellation side effects occur:

~~~text
result=interrupted
~~~

Explanation of result:
- `main` holds the lock until `waiter` finishes. `waiter` cannot acquire early.
- `ready` ensures the worker has reached at least the latch signal statement. `main` calls `interrupt()` right after; even if the interrupt signal arrives **before** the timed `tryLock` call, the timed overload still detects the interrupted state and throws `InterruptedException`.
- The `catch` block restores the flag; `"interrupted"` is recorded and `main` observes it after `join()`.
- The experiment does not need to guess how long to sleep. It distinguishes the cancellation branch from wait-time expiration.
- In a real application, a cancellation request should not be turned into an infinite retry; it must follow the task's lifecycle.

## 9. Ownership, try/finally, and Wrong Unlock Bugs

Standard pattern when timed `tryLock` can throw an exception:

~~~java
boolean acquired = false;
try {
    acquired = lock.tryLock(timeout, unit);
    if (!acquired) {
        return;
    }

    // Only the thread that acquired the lock may mutate shared state.
    updateSharedState();
} finally {
    if (acquired) {
        lock.unlock();
    }
}
~~~

This is an **excerpt inside a method** that can throw `InterruptedException`; `timeout`, `unit`, and `updateSharedState()` come from the caller. Another approach is to check the result first and put `try/finally` **inside the `true` branch**, as in the examples above. Both guarantee not unlocking without ownership.

### Do Not Do This

~~~java
try {
    if (lock.tryLock()) {
        useSharedState();
    }
} finally {
    lock.unlock(); // WRONG if tryLock() returns false
}
~~~

If the thread does not hold the lock, `ReentrantLock.unlock()` throws `IllegalMonitorStateException`; it **does not release** another thread's lock. That indicates a violation of the ownership contract, not a "guaranteed cleanup".

Related pitfalls:
- `tryLock() == true` establishes ownership for the **current thread**. It does not grant `unlock()` rights to another thread, even if that thread holds a reference to the same `ReentrantLock`.
- Reentrant lock: if the same thread calls `tryLock()` twice successfully, it must balance that with **two** `unlock()` calls. One unlock only decrements the hold count.
- Do not forget `unlock()` when code inside the critical section throws an exception.
- Do not use `synchronized(lock)` instead of `lock.lock()` and then call `lock.unlock()`; the `Lock` object's intrinsic monitor and the `Lock` API protocol are **two different locks**.
- `isHeldByCurrentThread()` and `getHoldCount()` are useful for checks/diagnostics; do not build a "guess ownership" protocol instead of keeping the boolean returned by the acquire call.

## 10. How Precise Is the Meaning of Timeout?

Suppose the caller specifies:

~~~java
lock.tryLock(100, TimeUnit.MILLISECONDS)
~~~

The 100ms bound only limits **the lock acquisition attempt phase**; it **does not** mean:

- The entire business operation must finish within 100ms.
- The caller is guaranteed to be scheduled right on time to observe the deadline.
- The lock owner will be forced to release when a waiter times out.
- A task holding the lock while doing long I/O will be automatically cut short.
- No one else is contending after the caller receives `true`.
- `false` always means the system is broken; it may simply be an intentional rejection policy.

If you need to control an **end-to-end deadline**, you must pass a time budget from the start of the operation through all steps: waiting for the lock, calling external resources, waiting in queues, and retrying. For durations measured inside the JVM, `System.nanoTime()` is suitable for computing **elapsed duration**; do not use `System.currentTimeMillis()` as a monotonic clock for deadlines because wall-clock time can shift.

### Example of sharing a time budget

~~~java
long startedAt = System.nanoTime();
long budgetNanos = TimeUnit.MILLISECONDS.toNanos(500);

// Step one happens before attempting the lock.
prepareInput();

long elapsed = System.nanoTime() - startedAt;
long remaining = Math.max(0L, budgetNanos - elapsed);

if (!lock.tryLock(remaining, TimeUnit.NANOSECONDS)) {
    throw new IllegalStateException("lock unavailable within budget");
}
try {
    applyPreparedInput();
} finally {
    lock.unlock();
}
~~~

This is an **illustrative snippet**; the methods and lock belong to the application context. It subtracts the duration of `prepareInput()` from the lock-waiting budget, **but it does not bound the duration of `applyPreparedInput()`**. A real contract must enforce a separate deadline or pass the remaining budget to any step that can block.

For long-running operations, watch out for overflow when adding nanosecond deadlines or converting overly large units. When comparing elapsed time, the pattern of subtracting from `System.nanoTime()` with durations in supported ranges is usually less error-prone than adding absolute timestamps.

## 11. Fair Locks: tryLock() Can "Barge"

Initializing `ReentrantLock`:

~~~java
ReentrantLock defaultLock = new ReentrantLock();      // non-fair
ReentrantLock fairLock = new ReentrantLock(true);     // fair
~~~

The fairness setting changes the prioritization policy for waiting threads contending for the lock, but:

**Important:** `fairLock.tryLock()` **can still acquire the lock immediately when it is free, even if other threads are already queued**. This is *barging* behavior explicitly documented by the JDK. That does not mean the program is wrong; however, you cannot use `tryLock()` and claim that all threads follow FIFO.

In contrast, `fairLock.tryLock(timeout, unit)` **honors the fairness setting** when other waiters are queued. If you need an almost-immediate try behavior that still honors fairness and checks for interruption, you can use:

~~~java
boolean acquired = fairLock.tryLock(0, TimeUnit.SECONDS);
~~~

You must still handle `InterruptedException`. If the same thread already owns the lock, reentrant acquisition is a special case and does not queue behind other threads.

### Should you always create a fair lock?

No. Lock fairness **does not guarantee thread scheduling fairness** and does not promise per-task deadlines. A fair lock can reduce wait-time variance under certain loads, but typically has lower throughput because it allows less barging; the actual cost depends on the workload. Do not choose `new ReentrantLock(true)` just because the name sounds "fair".

Choose the policy based on requirements:
- If fairness is a critical invariant, evaluate a fair lock and use acquisition APIs that honor fairness.
- If high throughput is needed and barging is acceptable, the default non-fair lock may be appropriate.
- If strict latency deadlines are required, fairness alone is not enough; you must also limit contention, lock hold time, and other blocking sources.

## 12. Avoiding Deadlocks When Multiple Locks Are Needed

When an operation needs to hold two locks A and B, a deadlock can occur:

~~~text
Thread T1: holds A ── waits for B
Thread T2: holds B ── waits for A

Both wait indefinitely if using lock() with no release path.
~~~

Timed `tryLock` allows **giving up and releasing already-held locks**, but only if the code is written with proper `finally` blocks. It does not automatically make an algorithm deadlock-free if another step still waits indefinitely or if callers retry in a way that causes livelock.

Illustrative pattern for acquiring two locks with bounded attempts:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

class TwoResources {
    private final ReentrantLock first = new ReentrantLock();
    private final ReentrantLock second = new ReentrantLock();

    boolean tryUseBoth(long timeout, TimeUnit unit)
            throws InterruptedException {
        long budgetNanos = unit.toNanos(timeout);
        long startedAt = System.nanoTime();

        if (!first.tryLock(budgetNanos, TimeUnit.NANOSECONDS)) {
            return false;
        }
        try {
            long elapsed = System.nanoTime() - startedAt;
            long left = Math.max(0L, budgetNanos - elapsed);
            if (!second.tryLock(left, TimeUnit.NANOSECONDS)) {
                return false;
            }
            try {
                // Operate on both resources under both locks.
                return true;
            } finally {
                second.unlock();
            }
        } finally {
            first.unlock();
        }
    }
}
~~~

This is an illustrative class without `main` and without real resources. Why is it safe with respect to **ownership**?
1. If `first` cannot be acquired, it returns `false` immediately without unlocking `first`.
2. Once `first` succeeds, every exit path from the outer `try` unlocks `first`.
3. If `second` cannot be acquired within the remaining budget, it returns `false` while still releasing `first` via the outer `finally`.
4. Only when `second` succeeds does execution enter the nested `try` and its `finally` block that unlocks `second`.
5. If interrupted while waiting for `second`, the exception propagates out and the outer `finally` releases `first`.

**Limitations:** If other threads do not follow the same lock protocol, invariants can still break. If there are multiple paths acquiring A/B in different orders, lock ordering or a proper timeout/retry design is needed. Retrying too aggressively between two threads can create **livelock**, so when retrying, bound the retry count/duration and consider controlled backoff. For computations that must finish within a budget, continue controlling critical-section duration after acquisition.

## 13. How tryLock Timeout Differs from Condition.await and Future Timeout

Waiting calls may all use `TimeUnit`, but they **guard different concerns**:

| Call | What is it waiting for? | On timeout |
|---|---|---|
| `lock.tryLock(t, unit)` | Lock ownership | Returns `false` if not acquired. |
| `condition.await(t, unit)` | A signal/condition while coordinating via a lock | Returns a boolean per the `await` contract; must **re-check the predicate** upon wakeup. |
| `future.get(t, unit)` | Task completion and result | Throws `TimeoutException` if not completed within the bound. |
| `semaphore.tryAcquire(t, unit)` | A permit from a semaphore | Returns `false` when no permit is available within the bound. |

Do not confuse waiting to acquire a lock with waiting for a predicate to become true. Use `Condition` when a thread needs to wait for **lock-protected state** to change; `Condition.await` is designed to release the lock while waiting and reacquire it before returning. Do not loop calling `tryLock()` repeatedly to simulate a condition queue, as that easily causes CPU spinning or starvation.

## 14. Lock Contention and Fallback Design

`tryLock()` and timed `tryLock` are useful when the application has clear behavior in all three cases:

1. **Lock acquired:** manipulate shared state inside the critical section and then release the lock.
2. **Timed out without acquiring:** return a busy code, perform a bounded retry, enqueue the work, or report a business-meaningful outcome.
3. **Interrupted:** stop or propagate the cancellation signal; never turn a cancelled request into an infinite retry.

Example business API that does not collapse all failures into `false`:

~~~java
enum ReserveResult {
    RESERVED, NOT_ENOUGH, LOCK_BUSY
}
~~~

Keep the business outcome (`NOT_ENOUGH`) separate from contention (`LOCK_BUSY`). A successful lock acquisition can still encounter data that does not satisfy the condition. Without distinguishing the two cases, the caller cannot easily decide whether to retry.

### Complete class example: reserving under a lock with timeout

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public final class InventoryCounter {
    public enum Result {
        RESERVED, NOT_ENOUGH, LOCK_BUSY
    }

    private final ReentrantLock lock = new ReentrantLock();
    private int available;

    public InventoryCounter(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("negative initial stock");
        }
        available = initial;
    }

    public Result reserve(int amount, long timeout, TimeUnit unit)
            throws InterruptedException {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        if (!lock.tryLock(timeout, unit)) {
            return Result.LOCK_BUSY;
        }

        try {
            if (available < amount) {
                return Result.NOT_ENOUGH;
            }
            available -= amount;
            return Result.RESERVED;
        } finally {
            lock.unlock();
        }
    }

    public int available() {
        lock.lock();
        try {
            return available;
        } finally {
            lock.unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        InventoryCounter inventory = new InventoryCounter(5);

        System.out.println(inventory.reserve(
                2, 100, TimeUnit.MILLISECONDS));
        System.out.println(inventory.reserve(
                4, 100, TimeUnit.MILLISECONDS));
        System.out.println("available=" + inventory.available());
    }
}
~~~

File: **InventoryCounter.java**, run:

~~~bash
javac InventoryCounter.java
java InventoryCounter
~~~

Output when `main` runs sequentially without external interruption:

~~~text
RESERVED
NOT_ENOUGH
available=3
~~~

Explanation:
- The first `reserve(2)` acquires the lock and decreases 5 to 3.
- The next `reserve(4)` still acquires the lock, but stock is insufficient; the method returns `NOT_ENOUGH` and does **not** decrement `available`.
- `LOCK_BUSY` only occurs when contention prevents acquisition within the requested duration.
- Both the `available < amount` check and the decrement are inside the same critical section, so there is no check-then-act race among callers following the same protocol.
- This is state **within a single JVM**. If inventory is updated by multiple processes or external systems, an in-process `ReentrantLock` is not enough for a distributed transaction.

### When the fallback is retry

Retries need an overall budget and a stopping condition. Do not call `tryLock()` endlessly in a `while` loop to "wait until the lock is free": that is a busy spin and can burn CPU. If waiting is required, use the timed overload or `lockInterruptibly()`. If retrying due to contention, apply a time limit, attempt limit, backoff, and cancellation support. Note that retrying an entire business operation may not be idempotent if a step outside the critical section has already produced side effects.

## 15. Reentrant Acquisition and Hold Count

The name `ReentrantLock` indicates that the thread currently owning the lock can acquire it again:

~~~java
ReentrantLock lock = new ReentrantLock();

lock.lock();                  // hold count = 1
try {
    boolean second = lock.tryLock(); // true; hold count = 2
    try {
        System.out.println(second);  // true
        System.out.println(lock.getHoldCount()); // 2
    } finally {
        lock.unlock();        // hold count = 1
    }
} finally {
    lock.unlock();            // hold count = 0; lock is released
}
~~~

This is an illustrative snippet placed inside a valid method/block. If `main` executes it with no other contender, the printed lines are `true` and `2`. It highlights that `tryLock()` **does not return `false` merely because `isLocked() == true`**: if the current thread is the owner, it can acquire again.

`getHoldCount()` indicates the number of times the **current** thread holds the lock, not the total number of waiting threads. If you miss one `unlock()` after a reentrant acquisition, the lock remains held even after code exits one call level; other workers can end up blocked.

## 16. Observing Contention Properly

When a lock cannot be acquired, instead of arbitrarily increasing timeouts, measure:

- **Lock acquisition wait time:** time from starting `tryLock` until success or timeout.
- **Timeout ratio:** how many requests receive `false` compared to total attempts; broken down by operation.
- **Critical-section duration:** how long the lock is held; whether there is I/O or a slow callback inside the lock.
- **Interrupt/cancellation:** how many lock-wait requests are cancelled, and whether the signal is properly restored/propagated.
- **Throughput and tail latency:** completed operations and p95/p99 percentiles.
- **Thread state/CPU:** `WAITING`, `TIMED_WAITING`, `BLOCKED`, CPU saturation, GC pauses.
- **Invariants:** whether data remains consistent after timeouts/retries, with no dropped operations or duplicate processing.

`ReentrantLock.getQueueLength()` only returns an **estimate** of the number of threads that may be waiting to acquire; `hasQueuedThreads()` is also volatile observational info. Do not use them as an atomic check to guarantee that the next acquisition will succeed.

Java Flight Recorder (JFR) can help investigate contention; Java thread dumps help inspect call stacks and states. Detail visibility for `java.util.concurrent.locks` depends on the JDK/tooling. Do not infer that a lock was released just because a thread dump did not record a waiting thread at the moment of capture.

## 17. Common Pitfalls to Recognize

**Pitfall 1 — Unlocking when tryLock returns false.** The thread does not own the lock; `IllegalMonitorStateException` may be thrown. Only unlock after a successful acquisition.

**Pitfall 2 — Not placing unlock in finally.** Exceptions or early returns can leave the lock held forever, hanging other threads.

**Pitfall 3 — Treating lock acquisition timeout as business timeout.** After acquiring, code inside the critical section can still run/wait for a long time. Use an end-to-end deadline if total latency is constrained.

**Pitfall 4 — Equating timeout with interrupt.** The timed overload throws `InterruptedException` when cancelled; `false` means the lock could not be acquired within the wait duration. Handling policies differ.

**Pitfall 5 — Swallowing interrupts.** Catching and retrying forever makes requests hard to cancel. Propagate the exception or restore the flag and exit per the lifecycle.

**Pitfall 6 — Calling isLocked() before lock().** Checking and acquiring are not atomic together. Use `tryLock`.

**Pitfall 7 — Assuming tryLock() obeys fairness.** On a fair `ReentrantLock`, untimed `tryLock()` can still barge. Use the timed form when fairness is required.

**Pitfall 8 — Looping tryLock() without pausing.** Busy spinning wastes CPU and worsens contention; prefer bounded waiting or backoff.

**Pitfall 9 — Locking on different lock instances.** Threads holding different `ReentrantLock` instances will not synchronize on the same state. Keep the shared lock on the object that owns the state.

**Pitfall 10 — Mixing synchronized(lock) with lock.lock().** The two mechanisms are not interchangeable; they acquire **semantically different locks**.

**Pitfall 11 — Releasing the lock from another thread.** Lock ownership is per thread. Do not hand off unlock responsibility to a callback running on another worker.

**Pitfall 12 — Acquiring multiple locks in opposite orders and forgetting to release the first when the second times out.** Use nested `try/finally` blocks and a clear lock-ordering/retry policy.

**Pitfall 13 — Assuming tryLock automatically protects all data.** Only operations following the same lock protocol have mutual exclusion. Unlocked read/write paths can break invariants.

**Pitfall 14 — Using timeouts as the sole solution to overload.** Timeouts make callers stop waiting, but do not fix the root cause of contention; examine overly long critical sections, queues, CPU/IO, and load admission.

## 18. API Selection Checklist

~~~text
Is there shared mutable state requiring exclusive access?
  |
  +-- No --> avoid locking if state is truly independent/immutable
  |
  +-- Yes
       |
       +-- Can you wait until the lock is acquired?
       |      |
       |      +-- Yes, no need to interrupt during the wait phase
       |      |       → lock() + finally unlock()
       |      |
       |      +-- Yes, but it must be cancellable
       |              → lockInterruptibly() + finally unlock()
       |
       +-- Cannot wait?
       |       → tryLock()
       |       → false: intentional fallback
       |
       +-- Can only wait for a bounded duration?
               → tryLock(timeout, unit)
               → true: enter critical section + finally unlock()
               → false: timeout/fallback
               → InterruptedException: propagate or restore + cancel
~~~

Before shipping to production, ask yourself:

1. Is the lock reference stable, associated with the right shared state, and shared by all writers/readers?
2. Are success, timeout, and interruption handled separately? Does the caller know when work was not performed?
3. Is `unlock()` guaranteed to run the exact number of times on the right thread across all return/exception paths?
4. Is the timeout a budget for the lock or for the entire operation? Do other steps have deadlines?
5. Is fairness a genuine requirement? Is using untimed `tryLock` on a fair lock intentional?
6. If retrying, is there a time/attempt cap and a mechanism to avoid spinning/livelock?
7. If using multiple locks, is there a lock-order policy, release on failure, and deadlock check?
8. Have contention, lock hold time, timeout ratio, and tail latency been measured under realistic load?

## 19. Practice Questions

**Question 1.** Thread A holds the lock, and thread B calls `tryLock()`. What will B receive?

**Answer:** B receives `false` immediately (assuming B is not the owner). It does not wait for A to release.

**Question 2.** If B calls `tryLock(100, MILLISECONDS)` and A holds the lock for over 100ms, what will B receive?

**Answer:** Assuming no interruption and B cannot acquire the lock, it returns `false` when the timeout expires. There is no millisecond-exact wall-clock latency guarantee.

**Question 3.** B is interrupted while waiting on timed `tryLock`. Should it be handled the same way as `false`?

**Answer:** No. It throws `InterruptedException` and clears the interrupted flag at the time of throwing; the code should propagate it or restore the flag and terminate according to the cancellation policy.

**Question 4.** When `tryLock()` returns `true` and an exception occurs inside the critical section, is `unlock()` still needed?

**Answer:** Yes, inside `finally` after a successful acquisition.

**Question 5.** With `new ReentrantLock(true)`, does `tryLock()` follow the fair queue?

**Answer:** Not required; the untimed overload can barge. The timed overload honors the fairness setting.

**Question 6.** What happens if the same thread already holding a `ReentrantLock` calls `tryLock()` again?

**Answer:** It returns `true` and increments the hold count. It must unlock enough times to release the lock completely.

**Question 7.** A service receives `false` from timed `tryLock` and silently returns during a mandatory state-transition task. Is that valid?

**Answer:** Not sufficient. You must decide on the handling obligation: bounded retry, enqueuing, or reporting a clear failure status. A timeout only indicates the lock was not acquired; it does not cancel the business requirement.

**Question 8.** Can you use `synchronized(myLock)` to lock with the same ownership as `myLock.lock()`?

**Answer:** No. The intrinsic monitor of the `Lock` object and the `Lock` API protocol are not equivalent.

## 20. References

- `ReentrantLock` (Java SE 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
- `Lock` interface (Java SE 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Lock.html
- `TimeUnit`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html
- `Thread.interrupt`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#interrupt()
- JLS `17.4 (Java Memory Model): https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4

**Remember:** `tryLock()` lets you decide **immediately** whether you can enter the critical section; `tryLock(timeout, unit)` allows **bounded waiting and reacting to interruption**. When acquisition succeeds, the thread must unlock in `finally`. When it fails, return a business-meaningful status; timeouts do not replace handling contention, end-to-end deadlines, or sound locking design.
