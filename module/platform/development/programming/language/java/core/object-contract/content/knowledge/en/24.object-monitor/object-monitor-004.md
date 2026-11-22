# `Object.wait()`: Releases the Monitor While Waiting and Must Reacquire It Before Continuing

## 1. Core meaning

In Java, every object has an **intrinsic lock (monitor)** used by `synchronized`. When a thread owns the monitor of object `lock` and calls `lock.wait()`:

1. The thread **temporarily releases all ownership of `lock`'s monitor itself** and enters a waiting state. Another thread can thereby enter `synchronized (lock)` to modify the condition and send a notification.
2. When notified, interrupted, or waking up on its own without a notification (spurious wakeup), the thread **cannot resume immediately**. It must **reacquire `lock`'s monitor**; only after acquiring the monitor does `wait()` return normally or throw `InterruptedException`.
3. Therefore, the code immediately following `wait()` inside the same `synchronized (lock)` block always runs once the thread owns that monitor again.

The easiest point to confuse: **`notify()` / `notifyAll()` does not immediately transfer the monitor to a waiting thread**. The notifying thread keeps the monitor until it exits `synchronized` (or releases it via an appropriate mechanism).

## 2. Prerequisite: waiting on the exact monitor currently owned

The methods `wait()`, `notify()`, and `notifyAll()` belong to `java.lang.Object`. The calling thread must currently own **the monitor of the exact object receiving the call**:

```java
Object lock = new Object();

synchronized (lock) {
    lock.wait(); // Valid: currently owns lock's monitor.
}
```

This is an *illustrative snippet*, which needs to be placed inside a method that handles or declares `InterruptedException`; by itself, this snippet will wait indefinitely unless an appropriate wake-up event occurs.

Conversely:

```java
Object a = new Object();
Object b = new Object();

synchronized (a) {
    b.wait(); // IllegalMonitorStateException: does not own b's monitor.
}
```

The same rule applies to `b.notify()` and `b.notifyAll()`. `synchronized(this)` also does not grant permission to call `someOtherObject.wait()`, unless `this` is that exact object.

The monitor of an instance `synchronized` method is `this`; the monitor of a `static synchronized` method is the corresponding `Class` object. Do not confuse those two monitors.

## 3. Progression from waiting to resuming

Suppose two threads share one `lock` and one condition variable `ready`, both reading/writing `ready` only inside `synchronized (lock)`:

| Step | Thread A (waiting) | Thread B (notifying) | Monitor `lock` |
| --- | --- | --- | --- |
| 1 | Enters `synchronized (lock)`, sees `ready == false` | Has not entered yet | Owned by A |
| 2 | Calls `lock.wait()`: releases monitor and waits | Can contend to enter | Released |
| 3 | Continues waiting | Enters `synchronized (lock)`, sets `ready = true` | Owned by B |
| 4 | Woken by `notifyAll()` but cannot pass `wait()` yet | Calls `lock.notifyAll()` and remains inside the lock block | Still owned by B |
| 5 | Contends to reacquire the monitor | Exits `synchronized (lock)` | Released |
| 6 | Reacquires monitor, `wait()` returns, rechecks `ready` | Has left the lock block | Owned by A |

`notify()` selects only one thread waiting on the object (with no guarantee of which thread is chosen); `notifyAll()` wakes all threads waiting on the object. **The woken threads still must take turns contending for the monitor**, rather than running concurrently inside the same monitor. The order of monitor acquisition and timing of execution are not guaranteed.

With untimed `wait()`, Java typically represents the waiting thread as `WAITING`. With `wait(timeout)`, the thread may be in `TIMED_WAITING`. During the phase of trying to reacquire the monitor, the thread may be in `BLOCKED`. This is a mental model to understand the mechanism; programs should not rely on observing an exact `Thread.State` snapshot at any given moment.

## 4. Verifiable Java 17+ program

Save as file `MonitorWaitDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class MonitorWaitDemo {
    private static final Object MONITOR = new Object();
    private static boolean ready;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch waiterEntered = new CountDownLatch(1);

        Thread waiter = new Thread(() -> {
            synchronized (MONITOR) {
                System.out.println("waiter: before wait");
                waiterEntered.countDown();

                try {
                    while (!ready) {
                        MONITOR.wait();
                    }
                    System.out.println("waiter: resumed, owns monitor");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    System.out.println("waiter: interrupted, owns monitor");
                }
            }
        }, "waiter");

        waiter.start();
        waiterEntered.await();

        synchronized (MONITOR) {
            System.out.println("main: acquired monitor");
            ready = true;
            MONITOR.notifyAll();
            System.out.println("main: notified, still owns monitor");
        }

        waiter.join();
    }
}
```

Compile and run:

```bash
javac MonitorWaitDemo.java
java MonitorWaitDemo
```

Output when there is no external interruption event:

```text
waiter: before wait
main: acquired monitor
main: notified, still owns monitor
waiter: resumed, owns monitor
```

**Why is this order verifiable?**

- `waiter` prints the first line while holding `MONITOR`. `CountDownLatch` only ensures the `main` thread does not start competing for the monitor before the waiting thread reaches the signaled point; it does not replace the `wait/notifyAll` mechanism.
- When `main` prints `main: acquired monitor`, it has acquired the monitor that `waiter` previously held. In this code, `waiter` released the monitor via `wait()`; without releasing it, `main` could not enter.
- Even though `main` already called `notifyAll()`, the line `waiter: resumed, owns monitor` is only printed **after `main` exits the `synchronized` block** and `waiter` reacquires the monitor.
- `ready` is read/written under the same monitor. The `while` loop checks the **actual condition**, not assuming that receiving a notification always means the condition is true.
- `waiter.join()` makes `main` wait for the child thread to finish before exiting. `Thread.sleep()` is not used to guess when another thread will run.

The `InterruptedException` branch in the example only runs if the waiting thread is interrupted, so it is not part of the normal output listed above. Inside that `catch` block, `waiter` has also already reacquired `MONITOR`; the example then restores the interrupt flag using `Thread.currentThread().interrupt()`.

## 5. Why must the condition be checked with `while`?

`wait()` waits for **a condition change**, but by itself it carries no condition and does not promise the condition is true upon returning. It can wake up due to a notification intended for multiple threads, a notification unrelated to the specific thread's condition, or a *spurious wakeup*. Between being notified and reacquiring the monitor, another thread may also modify the state.

Common pattern:

```java
synchronized (lock) {
    while (!condition) {
        lock.wait();
    }

    // condition has been checked while holding monitor lock.
    useSharedState();
}
```

This is **illustrative code**, with `condition` and `useSharedState()` provided by the program; the enclosing method needs to handle `InterruptedException`. The signaling side modifies the condition inside **the same monitor**:

```java
synchronized (lock) {
    condition = true;
    lock.notifyAll();
}
```

Do not write `if (!condition) lock.wait();` as if a single wakeup is enough. Also do not call `wait()` first and check the condition afterward: if the signal already arrived earlier, the thread might wait indefinitely. Checking the condition and calling `wait()` must be inside the same synchronized region so changes cannot slip into a gap between the two operations.

A `notifyAll()` call **does not save a signal** to grant to a thread calling `wait()` in the future. The condition variable is the meaningful state; notification simply prompts threads to re-examine that state.

## 6. What gets released — and what does not

`lock.wait()` releases **only the intrinsic monitor of the `lock` object**. It does not release another monitor that the thread happens to hold, and does not automatically release a `ReentrantLock` or non-Java resources.

```java
synchronized (outer) {
    synchronized (lock) {
        lock.wait(); // Releases lock, but still holds outer's monitor.
    }
}
```

This snippet illustrates a deadlock risk: if the thread that needs to change the condition must enter `synchronized (outer)`, it may be blocked by the waiting thread. Avoid holding unrelated locks across a wait.

If a thread entered the monitor of **the same object** multiple times because the lock is reentrant, `wait()` releases **the entire hold count of that monitor** while waiting; before continuing, the thread must reacquire the monitor and restore the corresponding hold count. Thus `wait()` does not merely decrement a single lock count.

## 7. Ways `wait()` completes and the effect of interruption

| Situation | What happens |
| --- | --- |
| `notify()` or `notifyAll()` | The waiting thread is selected/woken, then **waits to reacquire the monitor** before returning from `wait()`. |
| `wait(timeout)` expires | The thread wakes up when the timeout elapses, but still must **reacquire the monitor** before returning. Returning at the exact expiration moment is not guaranteed if the monitor is still held. |
| Spurious wakeup | `wait()` may return without a signal or timeout; it still must reacquire the monitor and check the condition. |
| Thread receives `interrupt()` | The thread must reacquire the monitor before `wait()` throws `InterruptedException`. Typically the interrupt status is cleared when the exception is thrown; the catching code decides whether to handle it or reset the interrupt flag. |

Relevant overloads: `wait()` waits with no predefined time limit; `wait(long timeoutMillis)` and `wait(long timeoutMillis, int nanos)` are timed, with `timeoutMillis == 0` and `nanos == 0` meaning wait indefinitely. Actual wakeup time depends on scheduling and monitor contention. After any kind of wakeup, **the condition must be rechecked**.

Example of checking with the standard API right after `wait()` returns:

```java
synchronized (lock) {
    while (!condition) {
        lock.wait();
        assert Thread.holdsLock(lock);
    }
}
```

`Thread.holdsLock(lock)` returns `true` when the current thread holds `lock`'s intrinsic monitor. This snippet is illustrative code; Java assertions can be enabled with the `-ea` option. On the `InterruptedException` throw path, monitor ownership has also already been restored before the thread enters a `catch` block inside the same `synchronized` block.

## 8. Comparison with similar operations

| Operation | Requires owning the target object's monitor? | Releases monitor while waiting? | Point to remember |
| --- | --- | --- | --- |
| `lock.wait()` | Yes | **Yes, of `lock` itself** | Must reacquire before returning/throwing exception. |
| `lock.notify()` / `lock.notifyAll()` | Yes | **No** | Wakes waiting thread(s); the notifying thread still owns the monitor until releasing the lock. |
| `Thread.sleep(...)` | No | **No** | Only pauses the current thread; does not release monitors the thread holds. |
| `Condition.await()` with `ReentrantLock` | Must hold the lock associated with `Condition` | Releases and reacquires the **associated lock**, not `Object`'s intrinsic monitor | Mechanism of `java.util.concurrent.locks`, do not mix directly with `Object.wait()`. |

## 9. Common errors and how to avoid them

1. **Calling on the wrong object**: `synchronized (a)` while calling `b.wait()` or `b.notifyAll()` causes `IllegalMonitorStateException`. Synchronize and invoke the method on the exact same object.
2. **Thinking `notifyAll()` hands over the monitor immediately**: the waiting thread does not resume until the signaling thread releases the monitor and it reacquires it.
3. **Waiting inside `if`**: a wakeup does not guarantee the condition is true. Use `while` and protect both reads and writes of the state with the same monitor.
4. **Calling `wait()` even when the condition is already true**: signals are not queued. Check the condition before deciding to wait.
5. **Using `sleep()` to "yield the lock"**: `Thread.sleep()` still holds the monitor, easily preventing the signaling thread from entering the `synchronized` block.
6. **Holding another monitor while waiting**: `wait()` does not release remaining monitors; this can cause threads to stall in a chain.
7. **Swallowing `InterruptedException` without considering task cancellation**: choose an appropriate handling strategy; when unable to handle locally, restore the interrupt flag or propagate the exception to the caller.

## 10. Knowledge self-check

**Scenario A.** Thread A is inside `synchronized (lock)` and calls `lock.wait()`. Can thread B enter `synchronized (lock)`? **Yes**, because A released that monitor while waiting.

**Scenario B.** B has called `lock.notifyAll()` but has not exited `synchronized (lock)`. Can A print the line right after `lock.wait()`? **No**, because A still has to reacquire the monitor that B is still holding.

**Scenario C.** A holds both `outer` and `lock`, then calls `lock.wait()`. Can another thread acquire `outer`? **No**, because `wait()` only releases `lock`'s monitor.

**Scenario D.** Does `wait()` returning after a notification mean `condition == true`? **No**. The condition must be rechecked in `while` once the monitor is held.

**Key takeaway:** `wait()` **releases the exact monitor of the object being waited on so another thread has a chance to change the state**; when the wait ends, the thread **must reacquire that monitor before continuing**. This is why the `synchronized` + `while` condition + `wait/notifyAll` pattern works safely when all accesses to shared state follow the same lock.
