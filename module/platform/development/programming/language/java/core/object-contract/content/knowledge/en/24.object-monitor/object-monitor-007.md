# `notify()` Does Not Immediately Transfer the Lock to the Woken Thread

When a thread calls `notify()` on an object in Java, **a waiting thread may be selected to wake up, but it is not immediately handed the monitor lock**. The thread calling `notify()` keeps the lock until it actually releases the monitor. Only after reacquiring that monitor can the woken thread finish `wait()` and continue executing the code protected by `synchronized`.

This is an essential point to grasp when coordinating threads using `Object.wait()`, `Object.notify()`, and `Object.notifyAll()`.

## 1. Monitor, wait set, and the meaning of "waking up"

Every Java object has a **monitor** (the lock used for `synchronized`) and a **wait set** (the set of threads waiting via `wait()` on that exact object).

- `synchronized (lock) { ... }` requires a thread to acquire `lock`'s monitor before entering the block. While a thread holds the monitor, another thread cannot concurrently enter a `synchronized` region using the same monitor.
- `lock.wait()` may only be called when the thread holds `lock`'s monitor. It puts the thread into the wait set and **releases `lock`'s monitor** while waiting. Upon returning from `wait()`, the thread has reacquired that monitor. If the thread had previously acquired the monitor multiple times (reentrant), `wait()` releases and later reacquires the corresponding hold count according to the specification.
- `lock.notify()`, which must also be called while owning `lock`'s monitor, arbitrarily selects **one** thread in this object's wait set to allow it to proceed toward acquiring the lock. If no thread is waiting, the call has no effect stored for the future.
- `lock.notifyAll()` removes all waiting threads from the wait set. This **does not** let them all run concurrently inside the `synchronized` region: at any moment only one thread can own that monitor.

Core distinction: **`wait()` releases the monitor when starting to wait; `notify()` does not release the monitor when signaling**. Saying a thread "woke up" only means that thread is eligible to continue the process of returning from `wait()`, not that it has already passed `wait()` or is executing.

## 2. Exact sequence when `notify()` is called

Suppose two threads share the `lock` object: W (waiter) waits for a condition, N (notifier) changes the condition and signals.

1. **W enters `synchronized (lock)`**, sees the condition is not satisfied, and calls `lock.wait()`. W is placed in the wait set and simultaneously releases the monitor so other threads can enter.
2. **N acquires the monitor**, updates shared state, and calls `lock.notify()`. The JVM picks one thread in the wait set (say W). **N remains the monitor owner** right after the call.
3. **N continues running** the remaining statements inside the `synchronized` region. W cannot finish `wait()` yet because it cannot reacquire the monitor held by N. If N performs slow processing inside the locked region, W must wait longer.
4. **N releases the monitor**, typically when exiting the `synchronized` block/method. From this point onward, W can contend for the monitor with other threads.
5. **Once W reacquires the monitor**, `wait()` can return normally (assuming no interruption), and W rechecks the condition and continues processing.

`notify()` makes no guarantees about when execution resumes, priority order, fairness, or that W will be the next thread to acquire the lock. If multiple threads are waiting, `notify()` does not guarantee which one is picked. Observable `Thread.State` values are only momentary snapshots; you may often see a thread blocked waiting for the monitor, but you should not rely on an exact sequence of states across all JVMs.

You can visualize the mandatory ordering with the same monitor:

```text
W: holds lock → wait() and releases lock ───────┐
N:                    acquires lock → notify() → continues work → releases lock
W:                                                                contends for lock → wait() returns
```

Notification makes W eligible to continue, **not a "lock handoff" operation** from N to W.

## 3. Runnable Java 17+ program with stable output order

Save as `NotifyMonitorDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class NotifyMonitorDemo {
    private static final Object MONITOR = new Object();
    private static final CountDownLatch WAITER_READY = new CountDownLatch(1);
    private static boolean canProceed = false;

    public static void main(String[] args) throws InterruptedException {
        Thread waiter = new Thread(() -> {
            synchronized (MONITOR) {
                WAITER_READY.countDown();
                try {
                    while (!canProceed) {
                        MONITOR.wait();
                    }
                    System.out.println("waiter: reacquired monitor");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "waiter");

        waiter.start();
        WAITER_READY.await();

        synchronized (MONITOR) {
            canProceed = true;
            MONITOR.notify();
            System.out.println("notifier: notify done, still holding monitor");
            System.out.println("notifier: about to exit synchronized");
        }

        waiter.join();
    }
}
```

Compile and run:

```bash
javac NotifyMonitorDemo.java
java NotifyMonitorDemo
```

Expected output (all three lines always appear in this order when the program runs normally without external interruption):

```text
notifier: notify done, still holding monitor
notifier: about to exit synchronized
waiter: reacquired monitor
```

**Why the output order is stable:**

- `WAITER_READY.countDown()` happens **inside** the waiter's locked region. `main` waits on the latch before trying to acquire `MONITOR`; by the time `main` enters the `synchronized` block, `waiter` has already released the monitor via `wait()` (or temporarily woken up and waited again). The latch only coordinates the example's setup, not replacing the monitor in the main mechanism.
- `canProceed` is read and written while holding the same `MONITOR`. The `while` loop also handles wakeups without notifications (spurious wakeups); `volatile` is unnecessary for this variable in this example.
- After `MONITOR.notify()`, `main` is still inside the `synchronized` block and therefore prints **both** notifier lines before `waiter` has any chance to reacquire the monitor and print its own line. The program does not use `sleep()` or guess thread scheduling to produce this order.
- `waiter.join()` ensures `main` waits for the child thread to finish before ending the program; `join()` is not a monitor handoff at the `notify()` site.

If you replace `MONITOR.notify()` with `MONITOR.notifyAll()`, with only one waiter in the example, the "does not release the lock immediately" property still holds.

## 4. Why placing slow work right after `notify()` can cause delays

Consider an **illustrative code snippet inside a method with `throws InterruptedException`**, using an already-declared monitor object and condition variable:

```java
synchronized (monitor) {
    condition = true;
    monitor.notify();
    Thread.sleep(500); // The signaling thread still holds the monitor while sleeping.
}
```

`Thread.sleep(500)` pauses the calling thread but **does not release the monitor**. Even though a waiter has been selected by `notify()`, it still cannot return from `wait()` until the signaling thread leaves the `synchronized` block (and the waiter reacquires the lock). The actual sleep duration is not an exact wait-time guarantee.

Similarly, performing I/O, expensive computation, or waiting for other resources inside the locked region after `notify()` can prolong wait times. Keep the protected section short, update state and signal under the monitor, and do work that does not need the lock outside.

If the notifier itself calls `wait()` on the same monitor, then the notifier's `wait()` operation **does** release the monitor; that is the behavior of `wait()` itself, not because `notify()` transferred the lock. Exiting `synchronized` normally or via an exception also releases the monitor according to block rules.

## 5. Relationship with data visibility

Requiring the waiter to reacquire the monitor also ensures an important part of correctness:

- N writes `canProceed = true` while holding the monitor, then releases the monitor when exiting `synchronized`.
- N's unlock **happens-before** W's subsequent lock acquisition on the same monitor. Therefore, after W reacquires the lock, it observes the updates in accordance with Java Memory Model rules.
- The specification also defines synchronization rules between a notification action and a return from a notified `wait()`; however, **no rule turns `notify()` into an immediate lock release**.

Do not rely on calling `notify()` to omit `synchronized` around checking and updating shared state. Both sides must agree on the lock object and condition.

## 6. Proper condition-coordination pattern

The two snippets below are **template code inside appropriate methods**, with `monitor` being the same object and `condition` being shared state always protected by the monitor:

**Waiting thread:**

```java
synchronized (monitor) {
    while (!condition) {
        monitor.wait();
    }
    // Condition is satisfied, and the thread holds the monitor.
}
```

**Signaling thread:**

```java
synchronized (monitor) {
    condition = true;    // Update state before notifying.
    monitor.notifyAll(); // Waiting thread still must reacquire the monitor.
}
```

Remember that `wait()` can return due to notification, interruption, expiration on `wait(timeout)`, or a **spurious wakeup**. Therefore, the condition must be checked in **`while`**, not just in `if`. Untimed `wait()` can still suffer `InterruptedException`; enclosing code must handle or declare that exception. If a waiter wakes up and the condition is no longer true because another thread handled it first, the `while` loop puts the waiter back into waiting.

A `notify()` signal **is not saved**: if called when the wait set is empty, a thread starting `wait()` afterward will not receive the old signal. Placing the condition check and the `wait()` call inside the same `synchronized` region prevents a check–wait gap that could cause missed signals in a properly locked model.

Choose `notify()` when you can prove that waking an arbitrary waiter is sufficient and correct; choose `notifyAll()` when there are multiple waiters or multiple wait conditions, because `notify()` might wake a thread that does not match the condition needed to make progress. `notifyAll()` has the cost of waking extra threads yet still does not allow concurrent execution inside the same monitor.

## 7. Common errors and how to fix them

| Misconception / pattern | What actually happens | How to handle |
| --- | --- | --- |
| "Calling `notify()` makes the waiter run right away." | The notifier keeps holding the monitor; the waiter must wait and reacquire the lock. | Rely only on shared conditions, not assumptions about immediate execution order. |
| Calling `monitor.notify()` outside `synchronized (monitor)`. | Throws `IllegalMonitorStateException` due to not holding the right monitor. | Lock **the same object** when calling `wait/notify/notifyAll`. |
| Using `if (!condition) monitor.wait();`. | Spurious wakeups or condition contention cause the thread to proceed erroneously. | Recheck the condition using `while`. |
| Changing the condition outside the lock, then notifying. | Can cause races or data-visibility bugs and break the wait protocol. | Protect updating, checking, and signaling with the same monitor. |
| Calling `notify()` on a different object than the one the waiter calls `wait()` on. | Wait sets belong to each object; the waiter is not woken by that notification. | Use the exact same actual monitor object. |
| Holding the monitor to do I/O or `sleep()` after `notify()`. | The waiter can be blocked for a long time even though notified. | Shorten the locked section; move lock-free work outside. |
| Assuming `notifyAll()` gives the lock to all waiters simultaneously. | Every waiter becomes eligible to proceed, but each must acquire the lock exclusively. | Write accurate conditions, accept contention, and recheck. |
| Ignoring `InterruptedException` or assuming only `notify()` makes `wait()` return. | Waiting thread can be interrupted; program may hang or drop stop requests. | Have a clear interruption-handling strategy and a condition-checking loop. |

## 8. Check questions

**Question:** After `notify()`, the notifier executes 100 more statements inside the same `synchronized` block. Can the waiter proceed past `wait()` during that time?

**Answer:** No, if both operations use the same monitor. The waiter must reacquire the monitor before `wait()` finishes, so it must wait for the notifier to release the lock. The number of statements does not matter; the monitor ownership boundary decides.

**Question:** As soon as the notifier exits `synchronized`, is the waiter guaranteed to run before a third thread trying to acquire the lock?

**Answer:** No. Java does not guarantee that a waiter selected by `notify()` will acquire the monitor next; threads may contend.

**Question:** What happens if no waiter is in `wait()` when `notify()` is called?

**Answer:** No pending notification is stored. A waiter appearing later can proceed only if the condition permits, if signaled in the future, or due to another wakeup cause.

## 9. Key takeaways and primary references

**Memory formula:** `wait()` = wait and release monitor; `notify()` = signal one waiter while **still holding the monitor**; waiter returning from `wait()` = **has reacquired the monitor**.

- [Java Language Specification §17.1: Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1)
- [Java Language Specification §17.2.1–17.2.2: Wait and Notification](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.2)
- [Java Language Specification §17.4.5: Happens-before](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5)
- [Java SE 17 API: `Object`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)
