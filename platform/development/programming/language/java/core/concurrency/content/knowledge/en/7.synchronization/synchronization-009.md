# Waiting on a Monitor with wait() and Waking Up with notify()/notifyAll()

In Java, every object has an **intrinsic monitor** (intrinsic lock). The `synchronized` keyword allows a thread to hold a monitor to protect shared state. However, sometimes holding a lock and repeatedly asking "is the condition true yet?" wastes CPU or prevents another thread from updating the data. Java provides three methods on `java.lang.Object` for **condition-based coordination** on a monitor: `wait()`, `notify()`, and `notifyAll()`.

Imagine a mailbox that holds only a single message: the producer must wait when the box is full, and the consumer must wait when the box is empty. `wait()` lets a thread **release the monitor and wait**, allowing another thread to enter the `synchronized` block and change the condition. After the condition changes, the updating thread can call `notify()` or `notifyAll()` to wake up waiters.

Most importantly: **waking up does not mean the condition is true**; the waiter must reacquire the monitor and **recheck the condition**.

## 1. Three Methods Operating on an Object's Monitor

These methods reside in `Object` (not just `Thread`), and operate on the **wait set** associated with the receiving object:

| Method | Meaning | Key Notes |
|---|---|---|
| `lock.wait()` | The current thread releases the monitor **of `lock`** and enters a waiting state for a signal/interruption. | Must currently hold the monitor of `lock`; may wake up spuriously (*spurious wakeup*). |
| `lock.wait(millis)` | Similar, but with a wait timeout; may return when the time elapses. | With the `wait(long)` overload, `millis == 0` means waiting indefinitely. |
| `lock.notify()` | Selects **one** thread waiting in `lock`'s wait set (if any) to wake up. | Does not select in FIFO order, and does not guarantee selecting the right condition to handle. |
| `lock.notifyAll()` | Wakes up **all** threads waiting in `lock`'s wait set at that moment. | They still have to contend for the monitor and recheck their own condition. |

`notify()` / `notifyAll()` **do not store a signal** for threads that start waiting later. If there are no waiters when called, the notification has no recipient. A proper design stores the **condition state** in a guarded variable, then waits using a `while` loop under the same monitor.

### Monitor Ownership Requirement

A thread must own the monitor of the **exact object** on which it calls `wait()`/`notify()`/`notifyAll()`. Otherwise, Java throws `IllegalMonitorStateException`. Correct example:

```java
Object lock = new Object();

synchronized (lock) {
    lock.wait(); // The thread holds the monitor of lock.
}
```

This is a **snippet** and must be inside a method that declares or handles `InterruptedException`. Do not run it standalone as shown above because waiting with no thread to notify it will cause it to hang.

The snippet below is incorrect because it locks one monitor but calls `wait()` on a different object:

```java
Object first = new Object();
Object second = new Object();

synchronized (first) {
    second.wait(); // IllegalMonitorStateException.
}
```

Even with `synchronized`, the **exact monitor** matters. `synchronized(this)` does not grant permission to call `someLock.wait()` if the thread does not already hold `someLock`'s monitor.

## 2. Which Lock Does wait() Release, and Which Does It Keep?

When a thread holds the monitor of object `lock` and calls `lock.wait()`:

1. The JVM places the thread into `lock`'s wait set and releases the monitor of **`lock` itself** as a coordinated operation.
2. The thread suspends execution at `wait()`, allowing another thread to enter `synchronized(lock)` and update shared state.
3. When notified, interrupted, timed out, or woken up spuriously, it must **reacquire `lock`'s monitor** before `wait()` can complete or jump to exception handling.
4. After reacquiring the monitor, the thread resumes inside the `synchronized` block and checks the condition.

If the thread simultaneously holds other monitors, `lock.wait()` **does not automatically release those other monitors**. This can lead to deadlock if the updating thread needs a monitor that the waiter still holds.

Flow diagram:

```text
Consumer thread                         Producer thread
---------------                         ---------------
synchronized(lock)
  while (empty) {
    lock.wait()
       | releases lock monitor
       v                               synchronized(lock)
     WAITING                              add item
       ^                                  lock.notifyAll()
       | woken up                          | still holds lock until exiting block
       +-----------------------------------+
    waits to reacquire monitor
    rechecks empty
    takes item
  }
exits synchronized(lock)
```

There is no guarantee that the producer releases the lock immediately upon `notifyAll()`. It only releases it when exiting the `synchronized(lock)` block or via another valid monitor-release mechanism. Therefore, the claim "as soon as notify is called, the waiter runs immediately" is **false**.

## 3. Mandatory Rule: Condition Predicate + while + Same Monitor

Basic safe pattern:

```java
synchronized (lock) {
    while (!condition) {
        lock.wait();
    }
    // Perform the operation only when condition is currently true.
}
```

This is an illustrative snippet: `lock` and `condition` are assumed to be declared, and `InterruptedException` is handled in the enclosing method. To complete the protocol, the thread modifying `condition` must also use the **same monitor**:

```java
synchronized (lock) {
    condition = true;
    lock.notifyAll();
}
```

**Why not use `if`?**

- **Spurious wakeup:** Java allows `wait()` to return even without a notification in the way the application expects.
- **Multiple waiters contending for the same resource:** a newly woken thread might acquire the monitor **after** another thread; the data may already have been consumed by that other thread.
- **Wrong condition after notifyAll:** multiple threads are woken up, but only one thread has its condition satisfied.
- **Timeout or interruption:** decisions must be based on state and waiting goals; the end of a wait alone does not prove the condition is valid.

Using `while` ensures every wakeup rechecks the condition under the lock. Both the condition check and `wait()` must be placed **inside the same `synchronized` block**: if the lock is split, another thread could change the condition and notify in the gap between *check* and *wait*, causing the waiter to sleep indefinitely.

The condition must be meaningful state (for example `hasItem`, `closed`, `available > 0`), **not** "some notification happened." Notification is a reminder to recheck state; the predicate itself determines when execution may proceed.

## 4. Example 1: One Waiter and notify()

The first example demonstrates the `while` guard pattern. `CountDownLatch` only lets `main` know the worker has started; it is not used to pass the `opened` condition.

Create the file **`MonitorSignal.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class MonitorSignal {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();
        boolean[] opened = {false};
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (lock) {
                started.countDown();
                while (!opened[0]) {
                    try {
                        lock.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
            }
            System.out.println("Worker passed the gate");
        }, "worker");

        worker.start();
        started.await();

        synchronized (lock) {
            opened[0] = true;
            lock.notify();
        }

        worker.join();
        System.out.println("Main finished");
    }
}
```

```bash
javac MonitorSignal.java
java MonitorSignal
```

Output:

```text
Worker passed the gate
Main finished
```

There are two valid execution schedules:

- The worker has already entered `wait()` before `main` locks the monitor to open the gate. `main` updates `opened[0] = true` and notifies; the worker wakes up, reacquires the monitor, sees the condition is true, and proceeds.
- `main` attempts to acquire the monitor right after the worker calls `started.countDown()` but **before the worker calls `wait()`**. `main` must wait for the worker to release the monitor before entering `synchronized`; the worker sees `opened` is still false and enters `wait` (releasing the monitor), and then `main` opens the gate and notifies. If `main` opens the gate before the worker first enters `synchronized` in a variant without a latch, the worker sees the predicate is true and skips `wait`.

Both scenarios are safe because **checking the condition and waiting use the same monitor**. There is no "lost notification" causing the worker to wait forever in this protocol. The `boolean[]` data is not marked `volatile` because every read/write of `opened[0]` happens under `lock`; unlocking/locking the same monitor provides the required memory ordering.

When there is only **one waiter** to wake up and a simple condition, `notify()` is sufficient. With multiple waiters and multiple condition types, `notifyAll()` is usually easier to reason about correctly.

## 5. notify() vs. notifyAll(): Pick One or Wake All?

`notify()` chooses an arbitrary waiter from the monitor's wait set. It does not guarantee FIFO, does not prioritize threads that have waited longer, and does not know "which thread is waiting for the matching condition." If a monitor is used to wait on **multiple types of conditions** (such as *not-empty* for consumers and *not-full* for producers), `notify()` can wake a waiter whose predicate is still false. That waiter goes back to `wait()`, while another thread that needs to make progress remains asleep. Such an interleaving can cause **loss of progress**, even though all data accesses are synchronized.

`notifyAll()` wakes every waiter in the same wait set, causing each thread to contend for the lock in turn and check its own predicate. It is usually the **correctness-safe** choice for protocols using one monitor with multiple conditions, and when a state change can allow multiple waiters to proceed.

| Scenario | Consideration |
|---|---|
| Exactly one waiter, one condition | `notify()` can be sufficient. |
| Multiple waiters, state change allows all to proceed | `notifyAll()` is required so no eligible waiter is missed. |
| One monitor used with multiple different predicates | `notifyAll()` is generally safer than `notify()`, combined with a `while` loop in each waiter. |
| Very many waiters, only one can make progress | `notifyAll()` may cause heavy monitor contention (*thundering herd*); still correct, but has overhead. |
| Wanting to wake precisely one condition group | Consider `ReentrantLock` with separate `Condition` objects or a higher-level abstraction. |

**Note:** even with `notifyAll()`, not every waiter gets to proceed with its action. Each thread must recheck its predicate; any thread whose condition is still unmet will continue waiting. `notifyAll()` also **does not guarantee fairness** or lock acquisition order.

## 6. Example 2: notifyAll() Opening a Gate for Multiple Waiters

Problem: multiple threads wait for a gate to open. Once the gate opens permanently, all of them are allowed to proceed. If `notify()` were called only once, at least one waiter could fail to be woken up (if they were actually waiting); `notifyAll()` is more appropriate.

Create the file **`MonitorBroadcast.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class MonitorBroadcast {
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
    }

    public static void main(String[] args) throws InterruptedException {
        Gate gate = new Gate();
        AtomicInteger passed = new AtomicInteger();

        Runnable waiter = () -> {
            try {
                gate.awaitOpen();
                passed.incrementAndGet();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(waiter, "A");
        Thread b = new Thread(waiter, "B");
        Thread c = new Thread(waiter, "C");
        a.start();
        b.start();
        c.start();

        gate.open();

        a.join();
        b.join();
        c.join();
        System.out.println("Workers passed: " + passed.get());
    }
}
```

```bash
javac MonitorBroadcast.java
java MonitorBroadcast
```

Output when there is no external interrupt:

```text
Workers passed: 3
```

`Gate.open()` sets `open = true` and calls `notifyAll()` inside the same synchronized method. If a waiter is already waiting, it is woken up and will check `open` after reacquiring the lock. If a waiter has not yet entered `awaitOpen()`, it will see `open == true` and **not wait**. Thus, the result does not depend on whether any waiter was actually asleep when `notifyAll()` was called. `join()` ensures `main` waits for all three threads before printing.

## 7. Example 3: Producer–Consumer with a Single-Element Mailbox

A complete example using **the same monitor** to guard a single-slot box, two predicates, and a close flag. The producer waits for `notFull`, and the consumer waits for `notEmpty`. `notifyAll()` is appropriate because waiters can be waiting on **different conditions** on the same monitor.

Create the file **`MonitorMailbox.java`**:

```java
public class MonitorMailbox {
    static final class Mailbox {
        private Integer value;
        private boolean closed;

        public synchronized void put(int item) throws InterruptedException {
            while (value != null && !closed) {
                wait();
            }
            if (closed) {
                throw new IllegalStateException("mailbox is closed");
            }
            value = item;
            notifyAll();
        }

        // null means the mailbox is closed and no data remains.
        public synchronized Integer take() throws InterruptedException {
            while (value == null && !closed) {
                wait();
            }
            if (value == null) {
                return null;
            }
            int item = value;
            value = null;
            notifyAll();
            return item;
        }

        public synchronized void close() {
            closed = true;
            notifyAll();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Mailbox mailbox = new Mailbox();

        Thread producer = new Thread(() -> {
            try {
                for (int i = 1; i <= 3; i++) {
                    mailbox.put(i);
                }
                mailbox.close();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                mailbox.close();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                Integer item;
                while ((item = mailbox.take()) != null) {
                    System.out.println("Received: " + item);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        producer.start();
        consumer.start();

        producer.join();
        consumer.join();
        System.out.println("Finished");
    }
}
```

```bash
javac MonitorMailbox.java
java MonitorMailbox
```

Output:

```text
Received: 1
Received: 2
Received: 3
Finished
```

**Reading the protocol carefully:**

1. All state (`value` and `closed`) is private and accessed only inside synchronized methods of the **same Mailbox instance**.
2. The producer calls `put()`: if the slot still holds a value, it enters `wait()` and releases the monitor so the consumer can call `take()`; when the slot is empty, it writes an item and calls `notifyAll()`.
3. The consumer calls `take()`: if the slot is empty and not closed, it releases the monitor via `wait()`; when an item is present, it takes the item, empties the slot, and calls `notifyAll()` for the producer.
4. The producer sends 1, 2, 3 in sequence; because there is one producer and one consumer, the consumer receives them in that exact order. After sending all items, the producer calls `close()`.
5. `close()` sets `closed = true` and calls `notifyAll()` so all waiters recheck; the consumer still retrieves any item remaining in the slot before receiving `null` to signal completion.
6. `main` calls `join()` on both threads before printing `Finished`, so the output does not depend on a specific scheduling order during normal execution without external interrupts.

If multiple producers/consumers need to be handled, the same `while` and `notifyAll()` protocol still applies; however, you should clearly define the `close()` contract, remaining data handling, task cancellation, and avoid using `null` as real data. This is a learning example for monitors, not a full-featured production queue implementation.

In everyday Java applications, `ArrayBlockingQueue` or `LinkedBlockingQueue` provide well-designed and tested wait/notify mechanisms and capacity policies. You should generally prefer abstractions like `BlockingQueue` over hand-rolling monitors when the goal is simply passing data between producers and consumers.

## 8. InterruptedException: Waiting Can Be Interrupted

`Object.wait()` throws `InterruptedException` if the thread is interrupted while waiting (or was already interrupted before beginning to wait per the API contract). When the exception is thrown, **the thread's interrupt status is cleared**; if the method does not propagate the exception and wants callers to still know about the cancellation request, it typically needs to restore the flag via `Thread.currentThread().interrupt()`.

An important point: `wait()` must **reacquire the object's monitor** before completing due to either a wakeup or an interrupt. The `synchronized` block still provides mutual exclusion to clean up state after the call.

Example of handling interruption properly when no further waiting is needed:

Create the file **`MonitorInterrupt.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class MonitorInterrupt {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();
        CountDownLatch ready = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (lock) {
                ready.countDown();
                try {
                    lock.wait();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    System.out.println("Wait interrupted");
                }
            }
        }, "waiter");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();

        System.out.println("Interrupt restored: "
                + worker.isInterrupted());
    }
}
```

```bash
javac MonitorInterrupt.java
java MonitorInterrupt
```

Output:

```text
Wait interrupted
Interrupt restored: true
```

`ready.countDown()` signals that the worker has entered the locked region, but at the moment `main` calls `interrupt()`, the worker **may have just entered `wait()` or not yet called `wait()`**. Both interleavings lead to the `InterruptedException` branch of the `wait()` call in this example. The worker restores the interrupt flag and exits `synchronized`; `main` waits for `join()` to complete and then observes the interrupt flag is still set. Calling `worker.interrupt()` **does not mean** forcibly stopping the thread or calling `notifyAll()` on the monitor: it is a cooperative cancellation signal to the target thread.

Do not "swallow" the exception and continue as if the condition were true. You can propagate `InterruptedException`, restore the flag and finish work, or perform cleanup and pass cancellation responsibility to the caller according to the contract.

## 9. Timed Wait and Using Deadlines

`wait(long millis)` and `wait(long millis, int nanos)` allow a time limit. Returning from them **does not confirm the condition is true**: it may be due to a notification, timeout, or spurious wakeup. Therefore, the `while` guard is still necessary.

If waiting until a specific deadline, compute the **remaining time** on each iteration using an elapsed-time clock such as `System.nanoTime()`; do not call `wait(timeout)` again with the full original duration after each wakeup, because the total wait time could exceed the intended limit. Algorithm example (snippet, not a standalone runnable class):

```java
long timeoutNanos = 1_000_000_000L; // 1 second.
long deadline = System.nanoTime() + timeoutNanos;

synchronized (lock) {
    while (!condition) {
        long remaining = deadline - System.nanoTime();
        if (remaining <= 0) {
            break; // Deadline expired; check/mark failure.
        }
        long ms = remaining / 1_000_000L;
        int ns = (int) (remaining % 1_000_000L);
        lock.wait(ms, ns);
    }
}
```

Here `lock` and `condition` are assumed to be declared, and the enclosing method must handle `InterruptedException`. In systems that must guard against numeric overflow with very large timeouts, additional clamping/overflow-control policies are needed; the example uses a short timeout for illustration. `wait(0)` on the millisecond-only overload means **wait indefinitely**, so when less than 1 ms remains, you must use the overload with nanoseconds as shown above.

Avoid using `Thread.sleep()` as a replacement for `wait()`: `sleep()` **does not release any held monitor**, so another thread needing that same monitor may be unable to enter and fix the condition. `wait()` is specifically designed to release the monitor of the object it waits on.

## 10. How wait() Differs from sleep(), join(), Condition, and BlockingQueue

| Tool | Which Monitor Is Released While Waiting? | Purpose |
|---|---|---|
| `Object.wait()` | Releases **the monitor of the object receiving `wait()`**, does not release other monitors. | Wait for a predicate on state guarded by a monitor. |
| `Thread.sleep(...)` | Does not release any intrinsic monitor held by the thread. | Pause for at least a given duration; not a condition wait. |
| `Thread.join()` | Internally uses a mechanism to wait for thread completion; does not release unrelated monitors held by the caller. | Wait for a thread to terminate, not for waking on business conditions. |
| `ReentrantLock.newCondition()` | `Condition.await()` releases/reacquires the **associated lock** per `Condition`'s contract. | Structured waiting with multiple condition queues, `signal()`/`signalAll()`. |
| `CountDownLatch.await()` | Does not automatically release any intrinsic monitor held by the caller. | Wait for a count of signals to reach 0; typically one-shot. |
| `BlockingQueue.take()/put()` | Internal locking/waiting mechanism managed by the collection. | Convenient producer–consumer data exchange with an established contract. |

With `ReentrantLock`, always hold the corresponding lock when calling `Condition.await()`/`signal()` per its contract, and unlock in `finally`. `Condition` also requires checking the predicate in a `while` loop because waking up does not automatically make the condition true.

Another model is often a better fit if the need is simply waiting for an event or result:

- `CountDownLatch` for a one-time completion signal;
- `Semaphore` for a permit count;
- `CompletableFuture`/`Future` for a task result;
- `BlockingQueue` for data transfer;
- `Condition` with a lock when coordinating multiple predicates in a custom data structure.

## 11. Happens-Before and Data Visibility

The Java Memory Model specifies that **unlocking a monitor** synchronizes-with a **subsequent lock on the same monitor**. When a producer updates `value` under `synchronized(lock)`, and a waiter later reacquires the monitor and reads `value` under the same lock, the effects are visible through the appropriate happens-before relationship.

Correspondingly, `wait()` releases the monitor so another thread can modify shared state, and reacquires the monitor before the waiter rechecks it. A standalone `notify()` **is not a substitute** for protecting the predicate; the memory semantics of monitor regions and checking state under the monitor form the complete reasoning model.

Do not blindly add `volatile` to every field just because multiple threads are involved: if **every read and write path** of a field is inside the same synchronized protocol, the monitor already provides both visibility and mutual exclusion. However, if any place reads the field outside the synchronized region without additional synchronization rules, the class may no longer be thread-safe.

In a multithreaded program, `start()` publishes actions prior to starting the worker, and `join()` lets a thread wait for results after the worker finishes. Those two APIs serve a different role from monitor condition waiting: `wait()` enables **coordination while both threads are still alive**.

## 12. Common Mistakes and Consequences

| Mistake | Consequence | Fix |
|---|---|---|
| Calling `wait()`/`notify()` outside the receiving object's monitor | `IllegalMonitorStateException`. | Lock the exact object with `synchronized(lock)` or a synchronized method on `this`. |
| Using `if (!ready) wait()` | May proceed while the predicate is still false. | Use `while (!ready) wait()` and recheck under the lock. |
| Changing the condition outside the lock then calling `notify()` inside the lock | Possible race/visibility bugs. | Guard both predicate and notification with the same monitor protocol. |
| Holding the lock and calling `Thread.sleep()` to wait for a condition | The updating thread may be unable to acquire the lock. | `wait()` releases the monitor; or use an appropriate concurrent abstraction. |
| Assuming `notify()` immediately hands the lock to the waiter | The waiter still has to contend for and reacquire the monitor. | Exit `synchronized` promptly after updating state when appropriate. |
| Using `notify()` with multiple types of waiters | Can wake the wrong waiter and stall progress. | Consider `notifyAll()` or separate `Condition` objects per predicate. |
| Treating a notification as "the event has occurred" state | Notifications before any waiter exists are not stored. | Store the predicate in guarded state; check it before waiting. |
| Waiting indefinitely without a close/cancel path | Threads may wait forever. | Design proper close signals, `notifyAll`, interruption, and timeouts per contract. |
| Swallowing `InterruptedException` and continuing normally | Cancellation is ignored; may violate business logic. | Propagate it or restore the interrupt flag and terminate cooperatively. |
| Calling callbacks or long I/O inside `synchronized` | Monitor is held too long, increasing contention and deadlock risk. | Keep critical sections short; pass data via queues or higher-level abstractions. |

**Do not use `wait()` directly as a "message queue."** A wait set does not store payloads, does not count notifications, and makes no FIFO guarantees. Manage state explicitly or use concurrent data structures with suitable contracts.

## 13. How to Design a Correct Monitor Protocol

Before writing code, answer these questions:

1. **Which monitor owns the state?** Choose a stable lock object (usually `private final Object lock` or a well-encapsulated `this` instance monitor).
2. **What is the predicate?** For example `!queue.isEmpty()`, `queue.size() < capacity`, `closed`. Place all reads/writes of the predicate under the appropriate synchronization protocol.
3. **What to do when the condition is not yet met?** Inside `synchronized`, `while (!predicate) lock.wait()`, with interruption/timeout handled explicitly.
4. **Who updates the predicate and notifies?** The thread that modifies state calls `notifyAll()` (or `notify()` if proven sufficient) while holding the right monitor.
5. **Are there multiple types of waiters?** If so, `notifyAll()` is usually easier for guaranteeing progress; or use multiple `Condition` instances.
6. **Is there a close/cancel state?** Waiters that cannot proceed must be woken so they can exit, avoiding keeping the process alive indefinitely.
7. **Is there a result or data to pass?** Store it in guarded state or use `BlockingQueue`/`Future`; do not treat a notification as a payload.
8. **Are there nested monitors?** `wait()` only releases the monitor it is called on; avoid holding other locks that could prevent the notifying thread from making progress.

For small learning programs, monitors are very useful for understanding the JMM and condition synchronization. For applications dealing with queues, pools, one-shot signals, or asynchronous tasks, APIs in `java.util.concurrent` usually express intent more accurately and reduce the chance of writing buggy wait/notify protocols.

## 14. Self-Check Questions

1. **Why must `wait()` be inside `synchronized` on the exact target object?** Because it operates on that object's wait set/monitor; not holding the monitor throws `IllegalMonitorStateException`.
2. **When calling `lock.wait()`, does the thread release all locks it currently holds?** No. It releases `lock`'s monitor, not other monitors it holds.
3. **Does `notify()` guarantee the woken thread runs immediately?** No. The thread must wait to reacquire the monitor; the notifier keeps the lock until it releases it.
4. **Why use `while` instead of `if`?** Because spurious wakeups, resource contention, and state changes can leave the predicate false after waking up.
5. **Is a `notify()` called when no waiter is present saved for later?** No. You must store state/predicates rather than relying on notifications.
6. **When is `notifyAll()` usually better than `notify()`?** When there are multiple waiters, especially with multiple predicates, or when one change allows multiple threads to proceed together.
7. **Does `Thread.sleep()` release the currently held monitor?** No.
8. **Does returning from `wait(timeout)` prove the condition is true?** No; the predicate must be rechecked under the lock.
9. **How does `InterruptedException` from `wait()` affect the interrupt flag?** The flag is cleared when the exception is thrown; if not rethrown, you may need to restore the flag.
10. **Why don't the fields need `volatile` in `Mailbox`?** Because every read/write path of the state uses the same monitor, providing mutual exclusion and the appropriate happens-before relationship.

**Remember:** `wait()` = *release the monitor and wait for a predicate*; `notify()` = *wake an arbitrary waiter*; `notifyAll()` = *wake all current waiters*. Every waiter must **reacquire the monitor, recheck the condition in a `while` loop, and act only when the predicate is actually true**.
