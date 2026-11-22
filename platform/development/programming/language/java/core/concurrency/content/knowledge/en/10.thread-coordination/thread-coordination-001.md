# How do `wait()`, `notify()`, and `notifyAll()` work in a monitor?

In Java, `Object.wait()`, `Object.notify()`, and `Object.notifyAll()` are low-level thread coordination primitives tied directly to each object's **intrinsic monitor**. They allow one thread to **temporarily release the monitor and wait for a condition**, while another thread **modifies the protected state and sends a signal** so that waiting threads get a chance to re-check that condition.

These three methods are easy to misuse because there are three distinct concepts:

1. **Permission to enter the critical section:** the thread has acquired the object's monitor.
2. **The business condition is true:** for example, the queue has an element, the gate is open, or the buffer has space.
3. **The thread is woken up:** a signal, interruption, timeout, or spurious wakeup occurred; this **does not by itself prove** that the business condition is true.

A correct design must protect the **predicate (state condition)** under the **same monitor**, call `wait()` inside a **`while` loop** that checks the predicate, and update the state before calling `notify/notifyAll`. Simply calling `notify()` is not "sending a permit" that a thread that has not started waiting yet can hold onto for later.

This article belongs to the **Thread Coordination** section of **general Java concurrency**, with JDK 17+ and the core APIs of `java.lang` / `java.util.concurrent`. It does not cover Spring Framework-specific thread-handling mechanisms.

## 1. Every Java object has an intrinsic monitor

At the language level, every object has a monitor that serves `synchronized`, `wait`, and `notify` operations. When a thread runs:

```java
synchronized (lock) {
    // critical section
}
```

it must own the **monitor of the `lock` object itself**. Another thread that also wants to `synchronized (lock)` must wait until the monitor is released.

Two method forms also use monitors:

| Syntax | Associated monitor |
| --- | --- |
| `synchronized (lock) { ... }` | The object referenced by `lock` |
| `synchronized void method() { ... }` | `this` |
| `static synchronized void method() { ... }` | The `Class` object of the corresponding class |

The monitor tracks ownership and re-entry count (intrinsic monitors are **reentrant**). If a thread currently owns monitor `M`, that same thread can call another `synchronized` method using `M` without self-deadlocking solely on this lock. However, other threads still cannot own `M` simultaneously.

Synchronization here also carries **Java Memory Model** semantics: unlocking a monitor happens-before the next lock on the same monitor. Therefore, writes performed under the same locking protocol can be properly observed by another thread when it acquires the monitor.

## 2. The three methods belong to `Object`, not `Thread`

These methods are defined on `java.lang.Object`; the object used for waiting/notifying can be a private monitor created by the class:

```java
private final Object lock = new Object();
```

This is an illustrative field declaration inside a class; it is not a standalone program. The key signatures are:

```java
public final void wait() throws InterruptedException;
public final void wait(long timeoutMillis)
        throws InterruptedException;
public final void wait(long timeoutMillis, int nanos)
        throws InterruptedException;

public final void notify();
public final void notifyAll();
```

The signatures above are presented in API declaration syntax for learning, not as code to put into a new class.

- **`wait()`:** the thread currently owning the monitor of the object on which the method is called will **release that monitor** and wait until it is eligible to proceed (notified, interrupted, or otherwise woken according to the contract), and then **must reacquire the monitor** before the method returns or throws `InterruptedException`.
- **`notify()`:** chooses **one** arbitrary thread from the group of threads currently `wait`ing on the **same object**, if any. There is no guarantee of fairness, FIFO order, priority selection, or picking the exact thread whose predicate is satisfied.
- **`notifyAll()`:** wakes up **all** threads currently `wait`ing on the **same object**. They still must contend for the monitor to re-enter; they do not execute the `synchronized` section at the same time.

**Mandatory requirement:** the caller of all three methods must currently own the monitor of the **object on which the method is called**. Otherwise, `IllegalMonitorStateException` is thrown. This applies to `wait`, `notify`, and `notifyAll`.

## 3. Why must `wait()` be paired with `synchronized`?

Because the step of **checking the condition and starting to wait** must happen as an atomic protocol relative to threads that update the state.

Consider:

```java
synchronized (lock) {
    while (!condition) {
        lock.wait();
    }
    // condition is true while the thread is holding lock.
}
```

This is an illustrative pattern with `lock` and `condition` belonging to the same protection protocol; real code must declare `throws InterruptedException` or handle the exception.

Sequence:

1. Thread A acquires the `lock` monitor.
2. A checks `condition` **while owning the monitor**.
3. If false, A calls `lock.wait()`. Moving the thread into the waiting state and releasing the monitor are coordinated according to monitor semantics, avoiding the window where "false was checked, yet a valid signal slipped in between" when the writer also uses the same monitor.
4. Thread B acquires the `lock` monitor after A has released it, sets `condition = true`, and then calls `lock.notifyAll()`.
5. B exits `synchronized`, releasing the monitor.
6. A gets a chance to reacquire the `lock` monitor, returns from `wait`, **re-checks the predicate**, and only then uses the state.

**Do not place the condition in another field that is modified while bypassing the same monitor** if the protocol depends on atomic check-and-wait. Do not put `wait` outside the lock and hope that adding `volatile` elsewhere will fix the entire lost-signal race.

## 4. Waiting, notifying, and reacquiring the monitor: three separate moments

Diagram with monitor `M`:

```text
Thread A (consumer)                  Thread B (producer)
-------------------                  -------------------
lock(M)
while (queue.isEmpty()):
    wait(M)
    |  A enters M's wait set
    |  A releases monitor M
    v
  WAITING                             lock(M)
                                      queue.add(item)
                                      notifyAll(M)
                                      | wakes waiter on M
                                      | but B still holds M
                                      unlock(M)
A must reacquire monitor M <---------+
  may briefly be BLOCKED waiting for lock
re-check queue.isEmpty()
take item
unlock(M)
```

**`notifyAll` does not release the monitor immediately when called.** Thread B continues to own the monitor until it exits the `synchronized` block or executes a valid `wait` call on the same monitor. A can only continue the code after `wait` once it is permitted to wake up and has reacquired the monitor.

From the perspective of `Thread.State`, a thread in `Object.wait()` without a timeout is typically in `WAITING`; once notified and still waiting to re-enter the monitor, it may be in `BLOCKED`. `Thread.getState()` is only a transient snapshot and should not be used to coordinate the right time to call `notify`.

## 5. Standard pattern: guarded block with `while`

This pattern is the foundation to remember:

```java
final class Gate {
    private boolean open;

    synchronized void awaitOpen() throws InterruptedException {
        while (!open) {
            wait();
        }
    }

    synchronized void open() {
        open = true;
        notifyAll();
    }
}
```

`wait()` and `notifyAll()` have no explicit receiver, so the receiver is `this`. Because the methods are `synchronized` on the instance, the caller owns the `this` monitor when calling both.

Key takeaways:

- `open` is a **state predicate**, not a transient signal.
- If `open()` is called **before** `awaitOpen()`, the waiter still exits immediately because it checks `open == true`; there is no need to "remember" a notification.
- If a waiter is waiting, `open()` transitions the state and then notifies, giving the waiter a chance to re-check.
- `while` handles spurious wakeups, competing threads, and cases where the predicate becomes false again (if the design allows closing again).
- Every read/write path to `open` follows the **same monitor**.

This snippet is an illustrative class without a `main` method. The complete example immediately below can be compiled and run standalone.

## 6. Java 17+ example: gate opened with `notifyAll()`

Save as `MonitorGateDemo.java`:

```java
public class MonitorGateDemo {
    static final class Gate {
        private boolean open;

        synchronized void awaitOpen() throws InterruptedException {
            while (!open) {
                wait();
            }
        }

        synchronized void open() {
            open = true;
            notifyAll();
        }

        synchronized boolean isOpen() {
            return open;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate gate = new Gate();

        Thread worker = new Thread(() -> {
            try {
                gate.awaitOpen();
                System.out.println("Worker passed gate");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "gate-worker");

        worker.start();
        gate.open();    // May happen before or after worker.wait().
        worker.join();

        System.out.println("Gate open: " + gate.isOpen());
    }
}
```

Compile/run with JDK 17+:

```bash
javac MonitorGateDemo.java
java MonitorGateDemo
```

Stdout in a normal run:

```text
Worker passed gate
Gate open: true
```

This program **does not rely on `Thread.sleep()` to guess when the worker has started waiting**. If `main` calls `open()` before `worker` enters `awaitOpen()`, the predicate is already true and the worker proceeds; if `main` opens the gate after the worker starts waiting, `notifyAll` wakes the worker. Both paths are valid and produce the same result.

Placing `join()` after `open()` ensures `main` waits for `worker` to finish before printing the final line. Do not replace it with polling `worker.getState()` or sleeping for a fixed duration to guess progress.

An intentional limitation: the program does not force `worker` **to definitely enter WAITING**; it verifies the correctness of the "proceed after the gate is open" protocol regardless of scheduling.

## 7. How do `notify()` and `notifyAll()` differ?

Suppose three waiters are all calling `wait()` on object `lock`:

```text
wait set of lock: {T1, T2, T3}

lock.notify()
    -> wakes one unspecified waiter (e.g., T2)
    -> T1 and T3 remain waiting

lock.notifyAll()
    -> wakes all waiters in the wait set at that moment
    -> T1, T2, T3 must contend for the monitor before re-checking condition
```

**There is no FIFO guarantee** among waiters from `notify` or `notifyAll` alone. The resumption order depends on monitor acquisition, scheduling, and other implementation factors.

| Situation | `notify()` | `notifyAll()` |
| --- | --- | --- |
| A single waiter on the monitor | May be sufficient when the predicate is true | Also correct, and more general |
| Multiple waiters on the same condition, where one update allows only one consumer to proceed | Can be optimal if backed by a strict proof | Safer when there is uncertainty about which waiter is chosen |
| Multiple predicate types sharing a monitor | Risks waking a waiter that cannot proceed | Usually easier to prove correct |
| Transitioning to a terminal/close state that all waiters must observe | May miss many waiters | Usually appropriate |
| Many waiters and very frequent notifications | Fewer wakeups | Can cause many wakeups and monitor contention |

**`notifyAll()` is not "always best for performance"**, but it is usually **easier to get right** when condition sharing is complex. It can cause a *thundering herd*: many threads wake up together, only one or a few can actually make progress, and the rest go back to `wait`. When performance matters, consider `Condition` to separate waiter groups or utilities in `java.util.concurrent`.

## 8. Why can `notify()` wake the wrong kind of waiter?

A bounded buffer has two different predicates:

- Producers wait for **buffer not full**.
- Consumers wait for **buffer not empty**.

If everyone waits on the **same monitor**, the wait set can simultaneously contain both producers and consumers. A single `notify()` does not know who is waiting for which condition. It might wake a producer while the buffer is still full, or a consumer while the buffer is still empty.

That wakeup makes no progress; the thread wakes up, reacquires the monitor, sees its predicate is false, and waits again. If the thread that could actually make progress is not woken and no further signal arrives, the system can get stuck.

**`notifyAll()` gives every group of waiters a chance to check its own predicate**, though they still must use `while` and contend for the monitor. Especially with multiple conditions on the same monitor, it is usually the easier choice to prove correct in learning examples.

If you need more precise group selection, `ReentrantLock` with two `Condition`s (e.g., `notFull`/`notEmpty`) or `ArrayBlockingQueue` provides a better-suited mechanism.

## 9. Lost notification bug: notifications do not accumulate like permits

A common mistake:

```java
// Thread A:
synchronized (lock) {
    lock.notify();
}

// Thread B (starts waiting late):
synchronized (lock) {
    lock.wait();
}
```

These two snippets are independent illustrations, not a runnable class. If A notifies when **there are no waiters yet**, the notification is not stored to wake B later. B may wait forever if no other notification arrives.

The fix is **not merely reversing start/sleep order** between the two threads. There must be state representing the event, for example:

```java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
```

and:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
```

This is a correct protocol if `ready` is protected by `lock` on all relevant paths. When the signal arrives early, `ready` remains true for the reader to see. When the signal arrives late, the reader waits and is woken properly.

**State is the truth; notification is just a reminder to re-check state.** This is the most reliable way to think about monitor conditions.

## 10. Spurious wakeups: why must we use `while` instead of `if`?

`Object.wait()` is permitted to return without an explicit notification expected by the application (spurious wakeup). In addition, a waiter can be notified because of **another predicate** on the same monitor, or another thread can claim the resource before the waiter reacquires the monitor.

Wrong:

```java
synchronized (lock) {
    if (queue.isEmpty()) {
        lock.wait();
    }
    return queue.removeFirst(); // There might be no element.
}
```

This is an illustrative anti-pattern. Even if `wait()` returns, `queue` **may still be empty**.

Right:

```java
synchronized (lock) {
    while (queue.isEmpty()) {
        lock.wait();
    }
    return queue.removeFirst();
}
```

Here it is assumed that `queue` is part of the state protected by `lock`. `while` forces the waiter to re-check the predicate after every wakeup. The condition is checked **inside the monitor**, so another thread cannot simultaneously modify the queue through the same monitor right between checking and removing the element.

For public APIs, document clearly that `wait` can be interrupted and that the method can throw `InterruptedException`; do not swallow the exception and continue as if the resource were ready.

## 11. Java 17+ example: producer–consumer using `wait/notifyAll`

The example below creates a bounded queue of capacity 2 with `put` and `take` operations. Producers wait for **not full**, and consumers wait for **not empty**. This is written to learn the monitor mechanism; in real applications, `ArrayBlockingQueue` is usually a better fit than building your own queue.

Save as `MonitorQueueDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public class MonitorQueueDemo {
    static final class BoundedQueue {
        private final Deque<Integer> items = new ArrayDeque<>();
        private final int capacity;

        BoundedQueue(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        synchronized void put(int value) throws InterruptedException {
            while (items.size() == capacity) {
                wait();
            }
            items.addLast(value);
            notifyAll();
        }

        synchronized int take() throws InterruptedException {
            while (items.isEmpty()) {
                wait();
            }
            int result = items.removeFirst();
            notifyAll();
            return result;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        BoundedQueue queue = new BoundedQueue(2);
        int[] result = new int[1];

        Thread producer = new Thread(() -> {
            try {
                for (int value = 1; value <= 5; value++) {
                    queue.put(value);
                }
                queue.put(0); // Sentinel: real data is only numbers 1..5.
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                int sum = 0;
                while (true) {
                    int value = queue.take();
                    if (value == 0) {
                        break;
                    }
                    sum += value;
                }
                result[0] = sum;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        producer.start();
        consumer.start();
        producer.join();
        consumer.join();

        System.out.println("Sum: " + result[0]);
    }
}
```

Run:

```bash
javac MonitorQueueDemo.java
java MonitorQueueDemo
```

Exact stdout **on the normal path, without external interruption**:

```text
Sum: 15
```

Explanation:

1. `items` is a plain `ArrayDeque`, but every add/remove and `size/isEmpty` check is protected by **`BoundedQueue`'s monitor**. No writer may modify `items` directly outside the class.
2. When the queue is full, the producer calls `wait()` and releases the monitor, allowing the consumer to still take an element.
3. When the queue is empty, the consumer calls `wait()` and releases the monitor, allowing the producer to still add an element.
4. `notifyAll()` after each structural change gives waiters a chance to re-check their respective predicates.
5. Capacity 2 limits the number of queued elements. Sentinel `0` is valid because normal data is only 1 through 5 and there is exactly one consumer.
6. `result[0]` is written only by the consumer; `main` reads it after `consumer.join()`, so join's happens-before relationship publishes the result without needing to make the array atomic.
7. There is no guarantee on when each thread runs; the program is correct under any normal schedule that satisfies the protocol.

**Limitation of the demo:** if the producer is interrupted before sending the sentinel or the consumer fails midway, the other side can wait forever. Real applications need a **close/failure protocol**, cancellation and waiter wakeup paths, or a concurrent structure with an explicit lifecycle. Do not turn a small example into a production queue without handling those branches.

## 12. Multiple waiters and multiple predicates: why use `notifyAll`

A single monitor can protect two different conditions. When the state allows **both groups** to proceed, `notifyAll` makes sense because it does not have to guess which waiter needs to wake up.

Save as `TwoConditionsDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class TwoConditionsDemo {
    static final class Conditions {
        private boolean firstReady;
        private boolean secondReady;

        synchronized void awaitFirst(CountDownLatch ready)
                throws InterruptedException {
            ready.countDown();
            while (!firstReady) {
                wait();
            }
        }

        synchronized void awaitSecond(CountDownLatch ready)
                throws InterruptedException {
            ready.countDown();
            while (!secondReady) {
                wait();
            }
        }

        synchronized void releaseBoth() {
            firstReady = true;
            secondReady = true;
            notifyAll();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Conditions conditions = new Conditions();
        CountDownLatch entered = new CountDownLatch(2);
        AtomicInteger completed = new AtomicInteger();

        Thread first = new Thread(() -> {
            try {
                conditions.awaitFirst(entered);
                completed.incrementAndGet();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        Thread second = new Thread(() -> {
            try {
                conditions.awaitSecond(entered);
                completed.incrementAndGet();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        first.start();
        second.start();
        entered.await();
        conditions.releaseBoth();
        first.join();
        second.join();

        System.out.println("Completed: " + completed.get());
    }
}
```

```bash
javac TwoConditionsDemo.java
java TwoConditionsDemo
```

Exact stdout on the normal path:

```text
Completed: 2
```

`entered` is a separate latch solely so `main` knows both threads have entered their wait methods. Each waiter calls `countDown()` inside the monitor right before the `wait` loop. Because `main` also needs that monitor to call `releaseBoth()`, it cannot change the predicate between the step where the waiter owns the monitor and the step where the waiter releases the monitor in `wait()`; that is the key protocol of the example.

`notifyAll()` gives both waiters a chance to reacquire the monitor and observe that their respective predicates are true. Both `incrementAndGet` calls update the same atomic counter, which `main` reads after `join`. There is no guarantee which waiter finishes first.

This is a **one-shot condition-opening** example. For repeated workloads, you need rules for predicate reset, closing, and cancellation; do not reuse a latch that has reached 0 to mark a new round.

## 13. InterruptedException: a `wait`ing thread can be interrupted

`Object.wait()` is an **interruptible** blocking operation. If a waiting thread receives `Thread.interrupt()`, it can return by throwing `InterruptedException` per the API contract. When `InterruptedException` is thrown due to interruption, the interrupt status is cleared as part of throwing the exception; the caller decides whether to propagate, clean up, or restore the status when it cannot handle it immediately.

Important: the thread must **reacquire the object's monitor** before `wait()` returns or exits via exception. Therefore, `catch`/`finally` blocks surrounding `wait` execute while the thread owns the monitor again.

Standalone example, save as `WaitInterruptDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class WaitInterruptDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean();

        Thread waiter = new Thread(() -> {
            synchronized (monitor) {
                entered.countDown();
                try {
                    monitor.wait();
                } catch (InterruptedException e) {
                    caught.set(true);
                    Thread.currentThread().interrupt();
                }
            }
        }, "interruptible-waiter");

        waiter.start();
        entered.await();
        waiter.interrupt();
        waiter.join();

        System.out.println("Interrupted wait: " + caught.get());
    }
}
```

```bash
javac WaitInterruptDemo.java
java WaitInterruptDemo
```

Exact stdout:

```text
Interrupted wait: true
```

The example uses a latch to know the thread has entered the monitor block before `main` requests an interrupt. If the interrupt arrives **before** the actual `wait()` call, the thread still has its interrupt status set and `wait` will respond according to contract when called. If the interrupt arrives **while waiting**, `wait` is woken by the interruption. Both schedules produce the same result above.

In the `catch` branch, `Thread.currentThread().interrupt()` restores the interrupt status so outer call layers can know an interrupt request occurred. In APIs with `throws InterruptedException`, propagating the exception to the caller is usually clearer than catching and swallowing it.

**Do not use `Thread.stop()`** as a substitute for interruption or to build cancellation logic; that mechanism is unsuitable for preserving invariants and was deprecated because it is unsafe.

## 14. `wait(timeout)` and timed waiting

Java provides:

- `wait()` or `wait(0)`: waits **indefinitely** according to `Object`'s wait contract.
- `wait(timeoutMillis)` with a positive timeout: requests waiting at most that duration before becoming eligible to wake up due to timeout; the actual time of reacquiring the monitor may be later due to scheduling and lock contention.
- `wait(timeoutMillis, nanos)`: allows specifying additional nanosecond precision within valid parameter ranges.

**Timeout does not mean the predicate is true.** The thread may return due to timeout, an unrelated notification, interruption, or a spurious wakeup. Therefore `while` is still required.

Example using a deadline instead of waiting the full initial timeout on every wakeup:

Save as `TimedGateDemo.java`:

```java
import java.util.concurrent.TimeUnit;

public class TimedGateDemo {
    static final class Gate {
        private boolean open;

        synchronized boolean awaitOpen(long timeoutMillis)
                throws InterruptedException {
            if (timeoutMillis < 0) {
                throw new IllegalArgumentException("negative timeout");
            }

            long deadline = System.nanoTime()
                    + TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
            long remaining;

            while (!open &&
                    (remaining = deadline - System.nanoTime()) > 0) {
                TimeUnit.NANOSECONDS.timedWait(this, remaining);
            }

            return open;
        }

        synchronized void open() {
            open = true;
            notifyAll();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Gate gate = new Gate();

        System.out.println("Opened: " + gate.awaitOpen(50));
        gate.open();
        System.out.println("Opened after signal: "
                + gate.awaitOpen(50));
    }
}
```

```bash
javac TimedGateDemo.java
java TimedGateDemo
```

Exact stdout in a normal run:

```text
Opened: false
Opened after signal: true
```

Explanation: on the first call, no thread opens `Gate`, so after the deadline expires the predicate is still false. Next time, `open()` has already been called, so `awaitOpen` returns true immediately without needing `wait`.

`System.nanoTime()` is suitable for measuring elapsed intervals because it is a monotonic clock meant for elapsed time, not wall-clock time. The demo uses a short, simple timeout; production library APIs must consider overflow of the deadline addition if huge timeouts are allowed, as well as the rule when passing `0`. `TimeUnit.NANOSECONDS.timedWait` converts the nanosecond interval into an appropriate timed wait call.

If you want to return a success result **only when the predicate has been met**, do not use `wait` returning as proof; the method must read the predicate inside the monitor before returning true.

## 15. How does `wait()` differ from `Thread.sleep()`?

| Property | `Object.wait()` | `Thread.sleep(...)` |
| --- | --- | --- |
| Receiver | An object monitor | Static API on the current `Thread` |
| Must hold monitor before calling? | **Yes**, the receiver's monitor | No |
| Releases the monitor in question while waiting? | **Yes**, releases the receiver's monitor | **No**, does not automatically release any monitor |
| Used to wait for a predicate changed by another thread? | Yes, via a guarded block | Not suitable as a signaling mechanism |
| What wakes it up? | Notification, interruption, timeout, spurious wakeup per contract | Sleep duration elapsing or interruption |
| When the method returns | Must reacquire the receiver monitor | Does not automatically acquire a new monitor |
| Risk if holding other monitors | Other monitors may still remain held | Keeps holding all currently owned monitors |

If you write:

```java
synchronized (lock) {
    Thread.sleep(1_000);
}
```

then the thread **still holds the `lock` monitor while sleeping**. Another thread that needs `lock` can become `BLOCKED` even though the CPU is doing no useful work. This is not how to let another thread enter the critical section to update the condition.

Conversely:

```java
synchronized (lock) {
    lock.wait();
}
```

causes the thread to release the `lock` monitor while waiting. However, without a predicate and signaling protocol, the second snippet risks lost notifications or waiting forever. Both snippets above only illustrate monitor behavior, not complete runnable programs.

## 16. `wait()` only releases the **receiver's** monitor, not all locks

A thread can own multiple nested monitors:

```java
synchronized (outer) {
    synchronized (inner) {
        inner.wait();
    }
}
```

This is an illustrative snippet with two hypothetical `outer` and `inner` objects.

`inner.wait()` temporarily releases the **`inner` monitor**, and does not automatically release the `outer` monitor. While the thread is waiting on `inner`, it may still be holding `outer`. If another thread needs `outer` to prepare the appropriate signal, the program can deadlock.

This is why you must check **what locks are still held on the stack** before calling `wait` or any blocking operation. `Object.wait` is not an "unlock all resources" primitive.

Similarly, `Condition.await()` in `java.util.concurrent.locks` releases and reacquires **the lock bound to that Condition** per contract, and does not automatically release any other monitors/locks the caller is holding.

With reentrant intrinsic monitors, `wait` releases all re-entry counts of **that receiver monitor itself** while waiting and restores the appropriate ownership before returning; however, it does not release independent monitors.

## 17. `IllegalMonitorStateException` and common API mistakes

Wrong:

```java
Object lock = new Object();
lock.wait();        // Caller does not hold lock's monitor.
```

Similarly wrong:

```java
Object lock = new Object();
lock.notifyAll();   // Caller does not hold lock's monitor.
```

These two snippets are isolated error examples; to compile and run, the `wait` example must handle the checked `InterruptedException`. In both cases, not owning the receiver's monitor causes `IllegalMonitorStateException`.

A subtler mistake:

```java
synchronized (firstLock) {
    secondLock.wait();
}
```

If `firstLock` and `secondLock` are two different objects and the caller does not own `secondLock`'s monitor, it still fails. Simply "being inside some `synchronized` block" is not enough.

### `wait()` vs `join()`

`Thread.join()` is a higher-level API for **waiting for a thread to terminate**. It has a proper completion and memory consistency protocol. Users do not need to call `wait()` and `notify()` on a `Thread` object to coordinate completion; doing so easily collides with the library's implementation and protocol.

If you need a task's result, use `Future.get()`; if you need a one-shot signal, use `CountDownLatch`. They express intent more clearly than manipulating monitors manually.

## 18. Happens-before: what role does notification play in visibility?

When a thread changes a predicate and calls `notifyAll()` inside a monitor, then exits the monitor, a woken thread only proceeds once it has reacquired the **same monitor**.

Example:

```java
synchronized (lock) {
    data = 42;
    ready = true;
    lock.notifyAll();
} // unlock lock
```

and:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    System.out.println(data);
}
```

These two snippets illustrate a shared protocol with `data` and `ready` protected by `lock`. If there is no other conflicting writer, the reader after passing the predicate will see `42`.

JMM explanation:

1. In the writer, the updates to `data` and `ready` occur before unlocking the `lock` monitor in program order.
2. Unlocking the `lock` monitor **happens-before** the subsequent lock on the same monitor that the waiter must perform before exiting `wait`.
3. The reader checks `ready` and reads `data` while holding the monitor, so it has proper visibility/ordering guarantees.
4. `notifyAll` is part of the **coordination protocol**; **do not separate notification from the predicate and monitor** to reason that a mere notify call publishes arbitrary data.

If a third writer modifies `data` without going through the monitor, a potential data race still exists. A monitor protocol is only effective when **all conflicting access paths that need protection follow the protocol together**.

## 19. Multiple consumers: why can the condition become false again after notify?

Suppose the queue just received one item. A single `notifyAll()` wakes three consumers waiting on the same monitor.

```text
Producer:
  put 1 item
  notifyAll()
  unlock

Consumer A acquires monitor first:
  queue not empty -> take item -> unlock

Consumer B acquires monitor next:
  queue already empty -> while re-checks -> wait

Consumer C acquires monitor next:
  queue still empty -> while re-checks -> wait
```

Nothing is wrong here: **notification only grants an opportunity**, not a reserved item per waiter. A woken waiter must contend for the monitor and re-check state, because another thread may have already consumed the condition.

That is the second reason (besides spurious wakeups) why `if` is wrong when waiting for a resource that another waiter can consume.

Distinguish carefully:

- `notifyAll` wakes all waiters **currently in the wait set** of the monitor; it does not wake `BLOCKED` threads waiting to enter `synchronized`.
- A newly woken thread is not guaranteed to run before a newly arriving thread acquires the monitor.
- There is no default FIFO or fairness guarantee for intrinsic monitors.
- A waiter only advances past the `while` loop when **the predicate is true at the moment it holds the monitor**.

## 20. Closing, cancellation, and errors in a monitor protocol

A custom bounded queue needs to answer many questions beyond the happy path:

- If the producer dies before sending a sentinel, how does the consumer exit?
- If the consumer is cancelled while the queue is full, can the producer get stuck in `put`?
- If `close()` is called while many waiters are in `wait`, who wakes them up?
- After closing, does `put` throw an exception, return false, or still accept items?
- Does `take` after close drain all previously queued items or stop immediately?
- If a thread is interrupted mid-operation, is the state left half-updated?

One design approach is to also protect a **`closed` predicate** under the same monitor and call `notifyAll` when transitioning to the closed state:

```java
synchronized void close() {
    closed = true;
    notifyAll();
}

synchronized Integer take() throws InterruptedException {
    while (items.isEmpty() && !closed) {
        wait();
    }
    if (items.isEmpty()) {
        return null; // Convention: null means closed and empty.
    }
    Integer value = items.removeFirst();
    notifyAll();
    return value;
}
```

This illustrates methods in a hypothetical class that has `closed` and `items`; it is not a standalone program. The contract must forbid `null` as valid data if `null` is used as a termination sentinel. The `put` path must also check `closed` before/after its wait loop according to appropriate rules, not just modify `take`.

**Transition the state before notifying** so woken waiters do not have to guess the reason. If `close` does not wake all waiters, some threads may keep waiting forever even though the system will accept no more data.

Real applications should prefer `BlockingQueue`, futures, latches, or components with clear lifecycles if there is no reason to implement monitor conditions from scratch.

## 21. `wait/notify` vs. higher-level Java utilities

| Problem | Usually appropriate primitive | Why |
| --- | --- | --- |
| Waiting for a state predicate protected by a monitor | `synchronized` + `while` + `wait/notifyAll` | Direct control over state and monitor |
| Producer–consumer, bounded queue | `ArrayBlockingQueue` or `LinkedBlockingQueue` | Already encapsulates the not-empty/not-full protocol |
| Waiting for a group of tasks to complete | `CountDownLatch` or `Future` | Expresses completion; no need to manage a wait set manually |
| Synchronizing multiple rounds by phase | `CyclicBarrier` or `Phaser` | Has semantics for multi-round coordination |
| Limiting the number of tasks holding a resource | `Semaphore` | Permits, acquisition/release, timeout, and interruption |
| Needing multiple condition groups on one lock | `ReentrantLock` + `Condition` | Can create multiple condition queues, reducing unnecessary wakeups |
| Waiting for a thread to terminate | `Thread.join()` | Direct lifecycle and HB contract |
| Waiting for an async task result | `Future.get()` / `CompletableFuture` | Ties waiting to the task's result and failure |

`Condition.await()` must also be used with a predicate inside a `while` loop; it can experience spurious wakeups. `Condition.signal` is similar in role to `notify`, but belongs to a condition queue attached to a `Lock`, not an `Object`'s monitor wait set.

Do not use `wait/notify` just because it is "lower-level and therefore faster"; concurrent utilities usually have clearer semantics, are easier to verify, and can offer better timeout/cancellation/lifecycle support.

## 22. Callbacks or I/O while holding a monitor: deadlock risk

A thread can leave the wait set and **still fail to make progress** if another thread holds the monitor for too long:

```java
synchronized (lock) {
    condition = true;
    lock.notifyAll();
    slowNetworkCall(); // Still holding lock!
}
```

This is an illustrative anti-pattern. Calling `notifyAll` **does not release the lock**. If `slowNetworkCall` blocks indefinitely, a woken waiter still cannot reacquire the monitor to proceed.

A better pattern:

```java
synchronized (lock) {
    condition = true;
    lock.notifyAll();
}
// Monitor has been released.
slowNetworkCall();
```

You should also avoid caller-supplied callbacks, `Thread.join()`, `Future.get()`, `BlockingQueue.take()`, or potentially blocking I/O inside a critical section, especially if the awaited operation needs that very monitor to complete.

If I/O updates state after completion, **take a snapshot under the lock → perform I/O outside the lock → acquire the lock to check version/invariants and commit**. Releasing the lock before I/O does not by itself create a transaction across both the JVM and external systems.

## 23. How to test a monitor protocol reliably?

Do not test by guessing timings:

```java
worker.start();
Thread.sleep(100);
synchronized (lock) {
    lock.notifyAll();
}
```

This is an illustrative anti-pattern. `sleep` only introduces delay; it does not prove the worker has entered the wait set. Without a predicate, an early signal is still lost. With a proper predicate, there is no need to depend on sleep.

For tests, use:

1. **`CountDownLatch`/`Phaser`** to actively coordinate start and finish milestones.
2. **A predicate under the monitor** to ensure both early and late notifications are correct.
3. **Bounded timeouts** in tests that might hang on failure; do not use an unbounded `join()` for a poorly designed test.
4. **Thread dumps / `ThreadMXBean`** when diagnosing waiters, owners, and monitors.
5. **Invariant checks** after workers finish, not just checking for exceptions.
6. **Stress tests** across many schedules, while not treating the absence of observed failures as proof of safety.
7. **Shutdown/interruption tests** so waiters are not left behind indefinitely when a pipeline closes or a producer fails.

One testing note: a latch signaling "the worker reached just before `wait`" does not automatically mean the worker **has already entered `WAITING`**, unless the protocol also guarantees appropriate monitor ownership/ordering. In `TwoConditionsDemo`, sharing the monitor with `releaseBoth` lets us verify this without relying on sleep.

## 24. Common misconceptions

**1. "`notify()` gives the waiting thread permission to run immediately."** No. The waiter still has to reacquire the monitor; the notifier keeps holding the monitor until it releases it.

**2. "`notifyAll()` makes all threads run inside the monitor at the same time."** No. The monitor remains mutually exclusive; waiters contend for the lock one after another.

**3. "`wait()` can be used outside `synchronized` for speed."** Wrong. The caller must own the receiver's monitor, otherwise `IllegalMonitorStateException` is thrown.

**4. "Just being inside any `synchronized` block is enough."** No. You must own **the exact monitor of the object on which `wait/notify` is called**.

**5. "`wait` automatically releases all locks."** Wrong. It only releases the receiver's monitor, not other monitors or locks on the stack.

**6. "`sleep` also releases locks like `wait`."** Wrong. `Thread.sleep` does not release any held monitors.

**7. "`notify` is remembered if nobody is waiting yet."** Wrong. No permits accumulate; use a predicate protected inside the monitor.

**8. "After `wait` returns, the condition is guaranteed to be true."** Wrong. There are spurious wakeups, multiple waiters competing for resources, and other predicates; use `while`.

**9. "`if` is enough if there is only one producer."** Still error-prone under cancellation, spurious wakeups, or multiple consumers; the guarded block rule is `while`.

**10. "Using `notify` is always more economical while still correct."** Not when multiple predicate types share the same wait set; it can wake the wrong waiter and stall progress.

**11. "Calling `notifyAll` after releasing the monitor is correct."** The caller of notify must currently **own the monitor**; do not release first and call outside `synchronized`.

**12. "With `volatile`, you can separate checking the condition outside the lock and then `wait`."** Visibility alone does not replace atomicity between checking the predicate and releasing the monitor/waiting.

**13. "`InterruptedException` means the thread is dead."** No. It is an interruption signal; catching code can continue running.

**14. "A timeout return means the condition is true."** No. Timing out only means the thread stopped waiting; the predicate must be checked separately.

**15. "`notifyAll` solves all deadlock problems."** No. It does not release the monitor immediately, does not release other locks, and does not fix dependency cycles or resource leaks.

**16. "Calling `notify()` on a `Thread` object is how to wait for a thread to finish."** Do not do this. Use `Thread.join()` to rely on the proper lifecycle contract.

## 25. Checklist when writing `wait/notifyAll`

Before shipping code to production, check:

1. **Is the monitor fixed?** Do all waiters/notifiers use the exact same object without switching receivers mid-way?
2. **What is the predicate?** Is there an explicit state field representing the required condition, rather than relying solely on a "signal"?
3. **Do all state access paths use the same lock?** If any path bypasses the monitor, memory/invariant reasoning can break.
4. **Is `wait` inside `while (!predicate)`?** Never use `if` for a guarded wait.
5. **Is state updated before notification?** A woken thread must have a condition to check.
6. **Is `notify` really sufficient?** When multiple predicates share a wait set or close must wake multiple waiters, use `notifyAll` unless `notify` can be proven correct.
7. **Is the monitor held too long after notify?** Avoid callbacks, I/O, future waits, and unnecessary blocking operations.
8. **How is interruption handled?** Propagate or restore the flag if not handling it; cleanup must not break invariants.
9. **Is there a timeout/close/failure protocol?** Do waiters have an exit path if a producer dies or the system shuts down?
10. **Are other locks held during `wait`?** `Object.wait` only releases the receiver's monitor.
11. **Are there multiple consumers/producers?** One notification can wake the wrong waiter; multiple woken waiters can see the predicate become false.
12. **If state can reset, is there a generation lifecycle?** Avoid reusing a one-shot flag for a multi-cycle protocol without explicit reset rules.
13. **Is there a higher-level primitive alternative?** `BlockingQueue`, `CountDownLatch`, `Condition`, or `Future` usually reduce the number of bugs you have to handle yourself.

## 26. Self-check questions

**1. Why must you own the monitor to call `wait()`?**

Because the waiter needs to check the predicate and enter the waiting state under the monitor protocol. Not holding the right monitor throws `IllegalMonitorStateException` and lacks atomicity between check and wait.

**2. Can a thread just woken by `notifyAll()` be in `BLOCKED`?**

Yes. That thread may have been woken from the wait set but still has to wait to reacquire the monitor before `wait` returns.

**3. Why is `while` more correct than `if` when waiting for a non-empty queue?**

Because the thread may wake due to a spurious wakeup, a notification for another condition, or because another consumer already took the item first. The predicate must be re-checked while holding the monitor.

**4. If the producer calls `notify()` before the consumer calls `wait()`, is the notification preserved?**

No. You need a predicate such as `queue.isEmpty()` or `ready`; the consumer only waits if the condition is genuinely not met.

**5. How do `wait` and `sleep` differ regarding monitors?**

`wait` releases the receiver's monitor while waiting and reacquires it before returning; `sleep` does not release any monitors the thread is holding.

**6. When both producers and consumers wait on one monitor, why can `notifyAll` be safer than `notify`?**

Because `notify` picks a waiter without knowing which predicate is valid; waking the wrong group can stall the system. `notifyAll` gives every group a chance to re-check its own condition.

**7. If `wait` throws `InterruptedException`, does the thread still hold the monitor?**

Yes. The thread must reacquire the receiver's monitor before the method exits via exception; the application still needs to clean up/propagate the interrupt properly.

**8. Should you call `notifyAll` and then make an HTTP request before exiting `synchronized`?**

Usually no. Notified waiters still have to wait for the monitor, so a slow HTTP request extends lock hold time. Separate I/O from the critical section and design appropriate commit/state checks.

**9. In a bounded queue, why should both `put` and `take` notify when state changes?**

Because `put` can transition the buffer from empty to non-empty (waking consumers), and `take` can transition the buffer from full to having space (waking producers). With multiple predicates sharing a monitor, `notifyAll` helps both groups re-check at the right time.

**10. What should a waiter do if it wakes up but the predicate is still false?**

Keep the monitor, go back to `wait` inside the `while` loop, unless there is an interruption, timeout, close, or cancellation policy to handle.

## 27. Core summary

- **The monitor is the lock-ownership mechanism; the predicate is the business truth; notification is a signal to re-check.** Do not conflate these three concepts.
- **`wait()`** is only valid when the caller owns the receiver's monitor; it releases that monitor while waiting and reacquires it before returning or throwing `InterruptedException`.
- **`notify()`** wakes at most one arbitrary waiter, and **`notifyAll()`** wakes all waiters on the same monitor. Neither method releases the monitor immediately upon being called.
- **`while (!predicate) wait()`** is the core pattern for handling spurious wakeups, resource contention, other conditions, and early notifications via the predicate.
- **Do not rely on `Thread.sleep` or assumed schedules** to prove a signal will arrive at the right time; keep state and signaling under the same monitor.
- **Interruption, timeout, shutdown, and producer/consumer failures** are part of the coordination protocol that must be designed, not optional in real systems.
- **Avoid implementing monitor conditions manually when higher-level Java tools fit**, such as `BlockingQueue`, `CountDownLatch`, `Condition`, `Future`, or `Thread.join()`.

When looking at `wait/notify` in Java, the first question should be: **"Which predicate is protected by which monitor, and does every thread re-check the predicate after waking up?"** If you can answer that clearly, most lost-notification and wrong-condition-waiting bugs become easy to spot and fix at their root.
