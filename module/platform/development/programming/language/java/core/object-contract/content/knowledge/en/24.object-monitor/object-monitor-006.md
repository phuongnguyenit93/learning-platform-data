# Use a `while` Loop to Check the Condition Before and After `wait()`

## 1. The problem to solve

When multiple threads access an object concurrently, one thread may have to **wait for shared state to satisfy a condition** before continuing. For example:

- A consumer may only take data when the buffer is **not empty**.
- A producer may only add data when the buffer is **not full**.
- A processing thread may only run once a status flag has changed to `ready == true`.

In Java's **intrinsic monitor** mechanism, a thread can call `Object.wait()` to pause and yield the monitor, while another thread uses `notify()` or `notifyAll()` to signal that the state may have changed. However, **being woken up does not mean the condition is already true**.

The critical rule is:

> **Always check the condition in a `while` loop when using `wait()`.** The loop checks before the first wait and rechecks after every return from `wait()`.

```java
synchronized (lock) {
    while (!conditionIsTrue()) {
        lock.wait();
    }
    // Still holding lock's monitor; the condition has just been rechecked.
    performOperationThatRequiresCondition();
}
```

This is a template illustration: `lock`, `conditionIsTrue()`, and `performOperationThatRequiresCondition()` must be defined in a real program.

## 2. How does `while` protect the condition?

A `wait()` call on object `lock` has these key characteristics:

1. The thread **must currently own the monitor of `lock` itself**, typically via `synchronized (lock)` or a `synchronized` method of `lock`. Otherwise, Java throws `IllegalMonitorStateException`.
2. When actually waiting, `lock.wait()` places the thread in `lock`'s wait set and **releases `lock`'s monitor**, giving other threads a chance to change the state. It does not automatically release other monitors that the thread holds.
3. A waiting thread can be woken by `notify()`, `notifyAll()`, interruption (`interrupt`), timeout expiration for `wait(timeout)`, or a **spurious wakeup** (waking up without a corresponding notification).
4. Before `wait()` finishes, the thread must **reacquire `lock`'s monitor**. By that time, another thread may have modified the state again.
5. Therefore, upon returning from `wait()`, `while` re-reads the condition **under the same monitor**. If not yet satisfied, the thread waits again; if satisfied, the thread performs the operation right inside that synchronized region.

Be clear on the distinction: `notifyAll()` makes waiting threads eligible to contend for the monitor; **the thread calling `notifyAll()` still holds the monitor until it exits the `synchronized` block/method**. A notification is a signal to *recheck*, not a promise that *you are guaranteed permission to proceed*.

### Why is `if` unsafe?

```java
synchronized (lock) {
    if (queue.isEmpty()) {
        lock.wait();
    }
    return queue.removeFirst(); // Can fail if queue is still empty.
}
```

Suppose consumers A and B are both waiting for data. A producer adds **one** element and calls `notifyAll()`. A acquires the monitor first and takes the element; B acquires the monitor afterward. With `if`, B goes straight to `removeFirst()` even though `queue` is already empty. With `while`, B sees the condition is not satisfied and goes back to `wait()`.

Even with only a single consumer, a spurious wakeup is enough to make `if` incorrect. Thus, turning `if` into `while` is a requirement for **logical correctness**, not merely a precaution against rare bugs.

## 3. Java 17+ example: single-element buffer

The buffer holds at most one integer. The producer must wait when the slot already has data; the consumer must wait when the slot is still empty. Both use **the monitor of the `Slot` object itself** because the methods are `synchronized`; calls to `wait()` and `notifyAll()` here are equivalent to `this.wait()` and `this.notifyAll()`.

Save the following into file **`WaitWhileDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WaitWhileDemo {
    static final class Slot {
        private Integer value; // null means the slot is empty.

        public synchronized void put(int next) throws InterruptedException {
            while (value != null) {
                wait(); // Release Slot's monitor when waiting for an empty slot.
            }

            value = next; // Modify state while still holding the monitor.
            notifyAll(); // Notify waiting threads to recheck.
        }

        public synchronized int take() throws InterruptedException {
            while (value == null) {
                wait(); // Release Slot's monitor when waiting for data.
            }

            int result = value;
            value = null; // Free the slot for the next put.
            notifyAll();
            return result;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Slot slot = new Slot();
        List<Integer> received = new ArrayList<>();

        Thread producer = new Thread(() -> {
            try {
                for (int n = 1; n <= 3; n++) {
                    slot.put(n);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                for (int n = 0; n < 3; n++) {
                    received.add(slot.take());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        producer.start();
        consumer.start();
        producer.join();
        consumer.join();

        System.out.println(received);
    }
}
```

Compile and run with Java 17 or later:

```bash
javac WaitWhileDemo.java
java WaitWhileDemo
```

Output when no thread is unexpectedly interrupted:

```text
[1, 2, 3]
```

The scheduling order of producer/consumer may vary, yet values are passed through `Slot` in order `1, 2, 3`. The program prints the result **only after both `join()` calls**, so the output does not depend on notification order or individual thread execution timing. The `received` list is written only by the consumer and read by `main` after `join()`.

**Analysis of guarding conditions:**

| Method | Condition requiring wait | Condition to proceed | State change |
| --- | --- | --- | --- |
| `put(next)` | `value != null` | `value == null` | `value = next` |
| `take()` | `value == null` | `value != null` | `value = null` |

In both methods, **checking the condition → reading/modifying state → sending notification** happens under the same monitor. If the condition is read outside `synchronized` before calling `wait()`, a change can slip into the gap between the two operations, causing the thread to miss the signal and wait forever.

The demo restores the interrupt flag in the `Runnable` lambdas because `Runnable.run()` does not declare `throws InterruptedException`. In real applications, a shutdown and error-propagation mechanism for workers must be designed; the example intentionally focuses on the wait loop rather than modeling task cancellation.

## 4. How does the loop behave before and after waiting?

Consider the consumer calling `take()`:

1. The consumer acquires the monitor and checks `value == null`. If data is already present, **it does not call `wait()`**.
2. If empty, the consumer calls `wait()`, releases the monitor, and enters a waiting state.
3. The producer enters `put()`, sets `value`, and calls `notifyAll()` while holding the monitor.
4. The producer exits the method; only then can the consumer reacquire the monitor so `wait()` can return.
5. The consumer executes **the `value == null` condition again at the top of `while`**. If another thread already took the data, it continues waiting. If data is present, it retrieves the value, sets `value = null`, notifies, and returns.

Key point: **there is no need to write two separate `while` loops**. A single `while` loop wrapping `wait()` checks both *before* the first wait and *after* every wakeup.

Threads are not guaranteed to acquire the monitor in the order they started waiting. `notifyAll()` does not create fairness, does not directly transfer monitor ownership to a specific consumer, and does not replace checking the predicate.

## 5. How do `notify()` and `notifyAll()` relate to `while`?

- `notify()` selects **one** thread in the monitor's wait set, but does not guarantee picking a thread waiting for the specific condition that just became true.
- `notifyAll()` wakes **all** threads waiting on that monitor. Each thread must contend again to enter `synchronized`, and then `while` decides which thread can actually proceed.
- When multiple kinds of threads wait on the same monitor, such as producers waiting for **not-full** and consumers waiting for **not-empty**, using `notifyAll()` is usually the simpler and safer choice. `notify()` picking the wrong thread group can leave the system stalled even though an operation is possible.
- Using `notifyAll()` **does not** allow replacing `while` with `if`: multiple threads can wake up together while only one thread finds the condition suitable at the moment it acquires the monitor.

To avoid waking unnecessary threads in complex systems, separate `Condition` instances with `ReentrantLock` can be used; even so, the rule of **waiting inside a predicate-checking loop** still holds.

## 6. Interruption, timeouts, and conditions that are never satisfied

### Interruption (`InterruptedException`)

`wait()` can throw `InterruptedException` when the thread is interrupted. When this exception is thrown, the interrupt status is cleared; you should usually **propagate the exception** with `throws InterruptedException`, or restore the flag with `Thread.currentThread().interrupt()` at a boundary where it cannot be propagated. Do not catch and silently ignore it, because the caller will lose the stop request.

An interrupted `wait()` does not mean the condition became true; code right after the loop **must not run** if waiting ended due to an exception.

### Timed waiting

When using `wait(timeout)`, the thread can also wake up due to **expiration**; the condition must be rechecked identically. You should not pass the same full timeout again after every wakeup, because repeated early wakeups could extend the total wait time indefinitely.

The method example below is an **illustrative snippet placed inside a class with shared `lock` and `ready`**; this is not a standalone program:

```java
boolean awaitReady(long timeoutNanos) throws InterruptedException {
    if (timeoutNanos < 0) {
        throw new IllegalArgumentException("timeoutNanos < 0");
    }

    long started = System.nanoTime();
    synchronized (lock) {
        long remaining = timeoutNanos;
        while (!ready) {
            if (remaining <= 0) {
                return false; // Timed out and the condition is still false.
            }
            java.util.concurrent.TimeUnit.NANOSECONDS.timedWait(lock, remaining);
            remaining = timeoutNanos - (System.nanoTime() - started);
        }
        return true;
    }
}
```

Here, all reads/writes of `ready` must be protected by `lock` itself. `System.nanoTime()` is used to measure elapsed time; `TimeUnit.NANOSECONDS.timedWait` converts the wait duration into the appropriate `Object.wait` call. If extremely long deadlines are needed, timeout policy and overflow handling must be designed explicitly.

Note that `wait(0)` means **wait indefinitely**, not check and return immediately. With `wait(long millis, int nanos)`, arguments must lie within the range allowed by the API.

### Unsatisfiable conditions

If no thread updates the state or sends the appropriate signal, `while` can wait forever. Design additional termination conditions, cancellation mechanisms, or deadlines when the problem requires them. The `while` loop guarantees **not proceeding while the condition is false**; by itself it does not guarantee progress.

## 7. Common mistakes and how to fix them

| Mistake | Why it is wrong | How to handle |
| --- | --- | --- |
| Using `if` instead of `while` | Spurious wakeups or another thread alters state before monitor reacquisition | Check the predicate with `while` |
| Calling `wait()` outside `synchronized` of the same object | Does not own the monitor, hits `IllegalMonitorStateException` | Lock the exact object receiving `wait()` |
| Reading the condition outside the lock | State can change between checking and waiting, causing lost signals | Protect both the predicate and the operation with the same monitor |
| Calling `notifyAll()` before updating state or forgetting to signal | Woken thread does not see a suitable state; may wait forever | Update state then notify while still holding the monitor |
| Assuming `notifyAll()` hands over the monitor immediately | Signaling thread still holds the lock; notified thread must wait to contend | Account for monitor reacquisition timing |
| Ignoring `InterruptedException` | Cancellation request is swallowed, making the thread hard to stop cleanly | Propagate or restore the interrupt flag appropriately |
| Holding another lock while calling `wait()` | `wait()` only releases the receiving object's monitor; other locks stay held | Design lock ordering and wait regions to avoid deadlock |
| Replacing `wait()` with `Thread.sleep()` while holding a monitor | `sleep()` **does not release the monitor**, so another thread may be unable to change the condition | Use `wait()` properly or higher-level synchronization utilities |

**Further distinction:** `Object.wait()` is not the same as `Thread.join()`, `Thread.sleep()`, or `LockSupport.park()`. They have separate mechanisms and usage conditions. This lesson discusses only condition waiting with `Object`'s intrinsic monitor.

## 8. Self-check checklist

For each waiting point based on `Object.wait()`, ask yourself:

1. **What is the predicate?** For example: "queue is not empty", not "notify was received".
2. **Who protects the predicate?** All related read/write paths must obey the same monitor.
3. **Does `while` wrap `wait()`?** The condition is checked before waiting and after each wakeup.
4. **Who changes the state and signals?** Modify state first, then `notifyAll()` while holding the right monitor.
5. **Are there interruption, timeout, and termination paths?** The thread must never silently use invalid data or wait forever unintentionally.

When using common concurrent data structures in real applications, prefer APIs that encapsulate the waiting protocol such as `BlockingQueue.put()`/`take()`. When learning, reviewing, or building a monitor yourself, the **`while (conditionNotSatisfied) wait()`** loop is the foundation for preserving invariants under all valid thread schedules.
