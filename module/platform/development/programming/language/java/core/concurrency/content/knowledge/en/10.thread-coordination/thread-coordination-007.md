# Lock + Condition for Multiple Wait Conditions in Java Concurrency

In a concurrent data structure, multiple groups of threads may have to wait for **different conditions on the same shared state**. For example, producers wait for "the queue is **not full**", consumers wait for "the queue is **not empty**", while other threads may wait for "the system is **closed**". If a single shared wait queue is used and the wrong group is woken up, the program can wake many threads uselessly, or even suffer from liveness/progress bugs when `notify()` is used inappropriately.

**`ReentrantLock` + multiple `Condition`s** allow one lock to protect *the entire shared state*, while creating **separate wait queues** for each predicate (logical condition). Threads waiting on `notEmpty` are only signaled by `notEmpty.signal()` or `notEmpty.signalAll()`; threads waiting on `notFull` are signaled on `notFull`.

This lesson focuses on core Java: `java.util.concurrent.locks.Lock`, `ReentrantLock`, `Condition`, locking mechanisms, waiting/signaling, and lifecycle management.

## 1. Why Are Multiple Conditions Needed?

Consider a fixed-capacity queue:

- **Producer:** only adds when `size < capacity`; if full, it must wait.
- **Consumer:** only takes when `size > 0`; if empty, it must wait.
- **Closing the queue:** all waiting threads must wake up to check `closed` and complete/exit according to the contract.

If an intrinsic monitor and `wait()`/`notify()` are used, all groups share a single wait set. A single `notify()` might wake another producer when the queue is still full, while a consumer needs to wake up to take data. `notifyAll()` usually resolves the risk of picking the wrong group, but it can cause many ineligible threads to contend for the lock only to wait again.

With `Condition`, we express this clearly:

```java
private final ReentrantLock lock = new ReentrantLock();
private final Condition notEmpty = lock.newCondition();
private final Condition notFull = lock.newCondition();
```

This is a declaration snippet inside a class, not a standalone runnable program. **Both `Condition`s share the same lock** but have **two different condition queues**. When adding an item: `notEmpty.signal()`; when taking an item: `notFull.signal()`. When closing and all waiters need to recheck: `signalAll()` on **both**.

> Core rule: *One lock protects the state; each Condition represents a distinct reason to wait.*

## 2. Distinguishing Lock, Condition, and Predicate

| Component | Role | What It Is Not |
|---|---|---|
| `ReentrantLock lock` | Excludes concurrent access to state and establishes proper memory visibility according to the Java Memory Model. | A data queue or condition flag. |
| `Condition notEmpty` | Wait queue for threads waiting for data to become available. | A variable storing the item count or number of signals. |
| `Condition notFull` | Wait queue for threads waiting for available capacity. | A separate lock protecting `size`. |
| Predicate `!queue.isEmpty()` | Current truth determining whether a consumer may take an item. | A `signal()` notification. |
| Predicate `queue.size() < capacity` | Current truth determining whether a producer may add an item. | A "pre-reserved" permission to proceed granted by a signal. |
| `closed` | Lifecycle state allowing waiters to decide to exit or reject operations. | An automatic cancellation signal to all threads. |

**The predicate is the source of truth; Condition only supports waiting in order to recheck the predicate.** A `signal()` call carries no payload, accumulates no permits, and does not set any condition to `true` by itself.

Different `Condition`s can share the same `ReentrantLock` because the `queue/closed` state forms *a single shared invariant*: never exceed capacity, never take from an empty queue, and never accept new items after closing.

## 3. await(): Releasing the Lock While Waiting and Reacquiring Before Proceeding

For a `Condition` created by `ReentrantLock.newCondition()`, execution typically follows this cycle:

1. `lock.lock()` or `lock.lockInterruptibly()` to acquire the **associated lock**.
2. Check the predicate under the lock.
3. If the predicate is false, call `condition.await()`. `await()` releases the associated lock (including the entire hold count if reentrant) and places the thread into the condition queue.
4. Another thread acquires the lock, modifies the state, and calls `condition.signal()`/`signalAll()`.
5. The signaled waiter moves to contend for the lock; it **does not immediately resume execution**.
6. Only after reacquiring the associated lock can `await()` return (or handle the interrupt path), and the waiter **rechecks the predicate in a `while` loop**.

```text
Producer                              Consumer
--------                              --------
lock.lock()
while (queueFull) {
    notFull.await()
       | release lock
       v                              lock.lock()
     WAITING                          remove item
       ^                              notFull.signal()
       |                              lock.unlock()
       +---- contend for lock --------+
    reacquire lock
    recheck queueFull
}
add item
notEmpty.signal()
lock.unlock()
```

A common misconception is that **`signal()` immediately hands the lock to the woken thread**. The signaling thread still holds the lock until it unlocks; other threads may also contend for and acquire the lock before the waiter does.

Calling `await()` on a `ReentrantLock`'s `Condition` or calling `signal()`/`signalAll()` **without holding the associated lock** throws `IllegalMonitorStateException`. You must use the exact lock that created the Condition, not just any lock.

## 4. Standard Pattern: Multiple Conditions with Separate while Loops

The following illustrative code assumes all variables belong to the same class and every operation on `queue`/`closed` uses the same lock:

```java
// Producer: wait for available space.
lock.lockInterruptibly();
try {
    while (queue.size() == capacity && !closed) {
        notFull.await();
    }
    if (closed) {
        throw new IllegalStateException("queue closed");
    }
    queue.addLast(item);
    notEmpty.signal();
} finally {
    lock.unlock();
}
```

```java
// Consumer: wait for data or queue closure.
lock.lockInterruptibly();
try {
    while (queue.isEmpty() && !closed) {
        notEmpty.await();
    }
    if (queue.isEmpty()) {
        return null; // Convention: closed and no data remaining.
    }
    T item = queue.removeFirst();
    notFull.signal();
    return item;
} finally {
    lock.unlock();
}
```

These are **snippets**, not two standalone programs: you need to define `lock`, `notFull`, `notEmpty`, `queue`, `capacity`, `closed`, `item`, type `T`, and declare `InterruptedException` on the corresponding methods.

Key characteristics:

- **Two predicates, two Conditions**, but **one shared lock**.
- The sequence **read predicate → await or execute → modify state → signal** is performed entirely under the lock.
- `while`, not `if`, due to *spurious wakeups*, contention among waiters, and state changes after the signal.
- `finally` always unlocks after normal completion, `return`, or exception.
- The `closed` condition must be **handled explicitly** so threads do not get stuck when the queue no longer accepts new items.

## 5. Example 1: One-Slot Queue with notEmpty and notFull

This complete example uses one producer, one consumer, and a mailbox with only **one slot**. The code accurately demonstrates how `Condition` separates waiters by their reason for waiting. A production-grade queue would need timeout policies, capacity configuration, error handling, and lifecycle management; here the goal is understanding monitors/conditions.

Create file **`OneSlotConditions.java`**:

```java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class OneSlotConditions {
    static final class Channel {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();
        private Integer value;
        private boolean closed;

        void put(int item) throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (value != null && !closed) {
                    notFull.await();
                }
                if (closed) {
                    throw new IllegalStateException("closed");
                }
                value = item;
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        Integer take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (value == null && !closed) {
                    notEmpty.await();
                }
                if (value == null) {
                    return null;
                }
                int result = value;
                value = null;
                notFull.signal();
                return result;
            } finally {
                lock.unlock();
            }
        }

        void close() {
            lock.lock();
            try {
                closed = true;
                notEmpty.signalAll();
                notFull.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Channel channel = new Channel();

        Thread producer = new Thread(() -> {
            try {
                for (int i = 1; i <= 3; i++) {
                    channel.put(i);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                channel.close();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                Integer item;
                while ((item = channel.take()) != null) {
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

Commands to run on JDK 17+:

```bash
javac OneSlotConditions.java
java OneSlotConditions
```

Output when there is no external interrupt:

```text
Received: 1
Received: 2
Received: 3
Finished
```

**Why does this program work correctly regardless of whether the producer or consumer is scheduled first?**

- If the producer runs first, it can place one item; if it wants to place the next item while the slot is full, `notFull.await()` releases the lock so the consumer can take it.
- If the consumer runs first, it enters `notEmpty.await()` and releases the lock so the producer can put an item.
- The producer calls `notEmpty.signal()` when transitioning the queue from empty to having an item; the consumer calls `notFull.signal()` when freeing the slot.
- The producer finishes and calls `close()` in `finally`: all waiters on both condition queues are woken up to observe the `closed` state.
- The consumer can still take the last item **after** `closed = true`, because `take()` prioritizes returning any remaining element. Only when the queue is empty and closed does `null` signal completion.
- Main calls `join()` on both threads before printing `Finished`.

This snippet does not use `volatile` for `closed` or `value`: every read/write path to both fields is under the **same ReentrantLock**, providing mutual exclusion and the appropriate memory visibility guarantees.

## 6. Why Signaling the Right Group Matters

With a single `Condition` for both producers and consumers, a `signal()` call does not know whether the woken thread is waiting for the queue to be not-full or not-empty. A producer might wake another producer while the queue is still full, which then goes right back to waiting while consumers remain asleep: progress can be hindered.

Two `Condition`s help:

- When a producer **adds** an item, only consumers need to re-evaluate `notEmpty`; wake a waiter on `notEmpty`.
- When a consumer **takes** an item, only producers need to re-evaluate `notFull`; wake a waiter on `notFull`.
- When **closing**, both groups need to check the closed state, so call `signalAll()` on **both** queues.

This reduces unnecessary wakeups while keeping the protocol easy to prove correct. **Multiple Conditions do not mean multiple Locks**: creating two different locks to protect the same `queue.size()` can break invariants if update paths lack coordination.

### signal() and signalAll() Do Not Serve the Same Purpose

| Method | Effect | When to Use |
|---|---|---|
| `notEmpty.signal()` | Signals one waiter in the `notEmpty` queue, if any. | Just added one item and only one consumer needs to wake up to try taking it. |
| `notFull.signal()` | Signals one waiter in the `notFull` queue, if any. | Just freed one slot and only one producer needs to try placing an item. |
| `notEmpty.signalAll()` | Signals all waiters waiting on `notEmpty`. | Closing the queue or changing state that allows multiple waiters to proceed/exit. |
| `notFull.signalAll()` | Signals all waiters waiting on `notFull`. | Closing the queue or changing state that requires all producers to re-evaluate. |

`signal()` on `notEmpty` **does not wake** waiters on `notFull`. Nor does it store a signal for waiters that arrive later. If a producer places an item when no consumer is waiting, a consumer arriving later reads the **queue-not-empty predicate** and proceeds without needing to "receive" the past signal.

## 7. Why Always Use while, Even When Signaling the Right Condition?

Suppose a producer adds an item and calls `notEmpty.signal()`. Consumer C1 is woken up, but before C1 reacquires the lock, a non-waiting consumer C2 may acquire the lock, take the item, and unlock. C1 then resumes, but the queue is **empty again**.

If C1 wrote `if (queue.isEmpty()) notEmpty.await();`, it could proceed under an outdated assumption and call `removeFirst()` on an empty queue. With **`while (queue.isEmpty())`**, C1 rechecks and waits again. Additionally, `Condition.await()` is permitted to have *spurious wakeups*: waking up even though no application-level signal was sent.

Pattern to remember:

```java
lock.lock();
try {
    while (!predicate()) {
        condition.await();
    }
    actUnderSameLock();
} finally {
    lock.unlock();
}
```

This is an illustrative snippet assuming `lock`, `condition`, `predicate()`, and `actUnderSameLock()` are already declared; the enclosing method must declare or handle `InterruptedException`.

Do not use `Thread.sleep()` while holding a lock to "wait for a condition": `sleep()` **does not release the lock**, so the thread that needs the lock to update the predicate may not be able to enter. `await()` is designed to **release and reacquire the associated lock** for condition coordination.

## 8. Example 2: Two Waiter Groups for Two Different States

An application without a queue may also need multiple Conditions: group A waits for the system to be **ready**, while group B waits for the system to be **stopped**. These are two independent predicates belonging to the same state object, protected by a single lock.

Create file **`TwoConditionGate.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class TwoConditionGate {
    static final class Lifecycle {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition readyCondition = lock.newCondition();
        private final Condition stoppedCondition = lock.newCondition();
        private boolean ready;
        private boolean stopped;

        void awaitReady() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (!ready) {
                    readyCondition.await();
                }
            } finally {
                lock.unlock();
            }
        }

        void awaitStopped() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (!stopped) {
                    stoppedCondition.await();
                }
            } finally {
                lock.unlock();
            }
        }

        void setReady() {
            lock.lock();
            try {
                ready = true;
                readyCondition.signalAll();
            } finally {
                lock.unlock();
            }
        }

        void stop() {
            lock.lock();
            try {
                stopped = true;
                stoppedCondition.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Lifecycle lifecycle = new Lifecycle();
        AtomicInteger readyDone = new AtomicInteger();
        AtomicInteger stoppedDone = new AtomicInteger();

        Thread readyWaiter = new Thread(() -> {
            try {
                lifecycle.awaitReady();
                readyDone.incrementAndGet();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        Thread stoppedWaiter = new Thread(() -> {
            try {
                lifecycle.awaitStopped();
                stoppedDone.incrementAndGet();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        readyWaiter.start();
        stoppedWaiter.start();

        lifecycle.setReady();
        lifecycle.stop();

        readyWaiter.join();
        stoppedWaiter.join();

        System.out.println("Ready waiters passed: " + readyDone.get());
        System.out.println("Stopped waiters passed: " + stoppedDone.get());
    }
}
```

```bash
javac TwoConditionGate.java
java TwoConditionGate
```

Result when there is no external interrupt:

```text
Ready waiters passed: 1
Stopped waiters passed: 1
```

Two condition queues serve two different logical events; calling `setReady()` does **not** signal `stoppedCondition`. If `main` sets the state before a waiter starts waiting, the waiter observes the predicate as true in the `while` guard and proceeds, regardless of whether any waiter was present to receive the signal.

This is a minimal example of **one-way** flags (false → true). If the lifecycle allows resetting back to false, the protocol must be redesigned to avoid waiters missing event *generations*. For example, a `version` variable or state machine can be used instead of relying on a single boolean.

## 9. Multiple Producers/Consumers: Contention and Consistency

A real queue may have **multiple** producers and consumers. Calling `signal()` for one consumer when adding an item is usually appropriate because only one consumer can take that item. When a consumer takes an item, calling `signal()` for one producer when space opens up is also appropriate. However, correctness requires:

1. Every method updating `queue` and `closed` must use the same lock.
2. Every waiter uses a `while` loop around its corresponding predicate.
3. Each operation that changes a group's predicate signals **that group's condition**.
4. When closing, **all waiters on all relevant Conditions** must be woken up; a single `signal()` is not enough.
5. If cancellation/interruption occurs, avoid leaving the queue in a half-updated state; handle it at operation boundaries according to the contract.

### Example 3: Bounded Queue with Multiple Producers and Consumers

This example uses a capacity of three, three producers each emitting 100 numbers, and two consumers summing the received numbers. After all producers finish, `main` closes the queue so remaining waiting consumers can exit. Threads pick up work in a non-deterministic order, but the **sum and count** can be verified.

Create file **`MultiProducerConsumer.java`**:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class MultiProducerConsumer {
    static final class BoundedQueue {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();
        private final Deque<Integer> queue = new ArrayDeque<>();
        private final int capacity;
        private boolean closed;

        BoundedQueue(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        void put(int value) throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (queue.size() == capacity && !closed) {
                    notFull.await();
                }
                if (closed) {
                    throw new IllegalStateException("closed");
                }
                queue.addLast(value);
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        Integer take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (queue.isEmpty() && !closed) {
                    notEmpty.await();
                }
                if (queue.isEmpty()) {
                    return null;
                }
                Integer value = queue.removeFirst();
                notFull.signal();
                return value;
            } finally {
                lock.unlock();
            }
        }

        void close() {
            lock.lock();
            try {
                closed = true;
                notEmpty.signalAll();
                notFull.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        BoundedQueue queue = new BoundedQueue(3);
        AtomicInteger count = new AtomicInteger();
        AtomicLong sum = new AtomicLong();

        Thread[] consumers = new Thread[2];
        for (int i = 0; i < consumers.length; i++) {
            consumers[i] = new Thread(() -> {
                try {
                    Integer value;
                    while ((value = queue.take()) != null) {
                        count.incrementAndGet();
                        sum.addAndGet(value);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "consumer-" + i);
            consumers[i].start();
        }

        Thread[] producers = new Thread[3];
        for (int i = 0; i < producers.length; i++) {
            final int base = i * 100;
            producers[i] = new Thread(() -> {
                try {
                    for (int value = base + 1; value <= base + 100; value++) {
                        queue.put(value);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "producer-" + i);
            producers[i].start();
        }

        for (Thread producer : producers) {
            producer.join();
        }
        queue.close();
        for (Thread consumer : consumers) {
            consumer.join();
        }

        System.out.println("Count: " + count.get());
        System.out.println("Sum: " + sum.get());
    }
}
```

```bash
javac MultiProducerConsumer.java
java MultiProducerConsumer
```

Result in a normal run without external interrupts:

```text
Count: 300
Sum: 45150
```

**Why are no items lost?** Every `put` and `take` protects the same `Deque` with one lock. If full, producers wait on `notFull`; if empty, consumers wait on `notEmpty`. Each thread rechecks its predicate after waking up; therefore, it cannot take an item from an empty queue or add beyond capacity. After producers finish, `main` calls `close()`, waking any waiting consumers so they exit when no items remain. The sum of integers from 1 to 300 is `300 * 301 / 2 = 45150`, independent of how work is split between the two consumers.

**Limitations:** this example does not describe full behavior when a producer fails, when a mid-run stop is requested, or when rollback is needed; those scenarios require additional lifecycle policies. In typical applications, `ArrayBlockingQueue` already provides a well-tested bounded queue and is usually preferable to rolling your own.

## 10. Closing and Canceling: Wake All Groups That Need to Re-evaluate State

A common mistake is having a queue with two Conditions, yet calling only `notEmpty.signalAll()` inside `close()`. Producers waiting on `notFull` will never receive the close signal and may wait forever even though they will never be allowed to add another item.

Correct close pattern when **both groups** need to exit:

```java
lock.lock();
try {
    closed = true;
    notEmpty.signalAll();
    notFull.signalAll();
} finally {
    lock.unlock();
}
```

This is a snippet within a class containing `lock`, `closed`, `notEmpty`, and `notFull`; it is not a standalone program.

The `while` loops in `take()`/`put()` must also check `closed` to provide an exit path, such as `while (empty && !closed)` or `while (full && !closed)`. If the predicate is only `while (empty)`, a thread woken up by `close()` will go right back to waiting because the queue is still empty. **A signal must accompany a state change that allows waiters to make a different decision.**

In real applications, the close contract should clearly specify: whether remaining items in the queue are drained, whether producers encountering `closed` throw an exception or return a status, how waiting calls handle interrupts/timeouts, and whether errors need to be propagated to callers.

## 11. InterruptedException and lockInterruptibly()

`Condition.await()` is an interruptible operation. When interrupted while waiting, it throws `InterruptedException` per its contract; the interrupt status is typically cleared when the exception is thrown. `ReentrantLock`'s `Condition.await()` **reacquires the lock before completing the exception-throwing path**, so `finally { lock.unlock(); }` remains valid.

Two common approaches:

- **Propagate** `InterruptedException` from the method so the caller handles cancellation.
- If the method does not propagate it, **restore the interrupt flag** via `Thread.currentThread().interrupt()` and then terminate or delegate cleanup per the contract.

`lock.lockInterruptibly()` can be interrupted **while waiting to acquire the lock**, unlike `lock.lock()`, which does not throw `InterruptedException` while trying to acquire the lock. When `lockInterruptibly()` throws an exception before acquiring the lock, execution has not entered the `try/finally` block containing `unlock()`, so the pattern places `lock.lockInterruptibly();` **before** `try`.

Never swallow an interrupt and blindly assume the predicate is true. A thread woken up due to cancellation may not be permitted to proceed with taking or producing data.

## 12. Timed await: Managing Remaining Time

With `Condition`, `awaitNanos(long timeoutNanos)` allows waiting with a time budget and returns the remaining time (which can be zero or negative when expired). It can still experience spurious wakeups or be signaled when the predicate has already changed, so **the `while` loop is still mandatory**.

Pattern for a gate wait method with timeout, in snippet form:

```java
boolean awaitReady(long timeoutNanos) throws InterruptedException {
    long remaining = timeoutNanos;
    lock.lockInterruptibly();
    try {
        while (!ready) {
            if (remaining <= 0L) {
                return false;
            }
            remaining = readyCondition.awaitNanos(remaining);
        }
        return true;
    } finally {
        lock.unlock();
    }
}
```

This snippet assumes `ready`, `lock`, and `readyCondition` belong to the same class. On each iteration, use `remaining` **instead of resetting to the full timeout**, avoiding extending the wait duration due to repeated signals or spurious wakeups. A return value of **true** means the `ready` predicate was true while holding the lock; **false** means the budget expired before the predicate became true. Do not equate the return value of a single `await` call with the business state.

For bounded timeouts, handle arithmetic overflow cases for very large durations or invalid configurations; use `TimeUnit` and deadline-based wait APIs where appropriate. If custom condition logic is not needed, `BlockingQueue.poll(timeout, unit)` already handles waiting for an item with a timeout.

## 13. Memory Ordering (Java Memory Model)

Lock rules in Java establish memory synchronization semantics equivalent to monitors: an **unlock** on a lock has a *happens-before* relationship with a **subsequent lock** on the same lock per the contract. Because every thread reads/writes `queue` and `closed` under the same `ReentrantLock`, state updated before unlock is properly visible when a waiter reacquires the lock.

With multiple Conditions on the same lock:

- `Condition`s **do not own separate copies of the queue**: they only partition waiters.
- State changes are published via the lock/unlock protocol; a `signal()` call itself **does not replace** protecting the predicate.
- You do not need to add `volatile` to every field already consistently protected by the same lock.
- If a getter reads state **outside** the lock protocol, the class can lose visibility and safety guarantees.
- `Thread.start()` and `Thread.join()` establish additional relationships at thread lifecycle boundaries, but they do not replace locks/conditions when coordination is needed **while multiple threads are concurrently active**.

`signal()`/`signalAll()` only determine which threads get a chance to contend for the lock; **actual execution order is still governed by scheduling and lock contention**.

## 14. Fairness and Waking Too Many Waiters

`new ReentrantLock(true)` uses a *fair* policy when distributing the lock under contention per its contract, but that **does not guarantee strict business-level FIFO ordering**, does not eliminate spurious wakeups, and does not turn `signal()` into a reservation for an item. After a signal, the waiter still must contend according to the lock's rules.

If `signalAll()` is called for hundreds of consumers just because one item was added, all of them may wake up and contend for the lock while only one consumer ultimately gets the item — the *thundering herd* problem. Splitting waiters into `notEmpty` and `notFull`, and using `signal()` when sufficient, avoids many unnecessary wakeups.

However, **fewer signals does not mean better in every case**. For close events, version changes, or conditions where multiple waiters can make progress together, `signalAll()` is the right choice. Prioritize **safety/liveness correctness** first, then measure contention and optimize.

## 15. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Creating `notEmpty` from lock A, but holding lock B during `await()` | With `ReentrantLock.ConditionObject`, throws `IllegalMonitorStateException`. | A Condition must be used with its associated lock. |
| Using `if (empty) await()` | May wake up spuriously or find the item already taken by another thread. | Always use `while (predicate false) await()`. |
| Modifying `queue` outside the lock then signaling inside the lock | Prone to races and invariant violations. | All reads/writes of related state and signaling must use the same lock. |
| Creating two Conditions but sharing one ambiguous predicate | Fails to leverage waiter partitioning; easy to signal the wrong group. | Clearly define each predicate and waiter group. |
| Signaling `notFull` after `put` | May wake an ineligible producer while consumers stay asleep. | Signal `notEmpty` after `put`, and `notFull` after `take`. |
| Signaling only one Condition on `close` | The other waiter group may wait forever. | Call `signalAll()` on all condition queues affected by `closed`. |
| Assuming `signal()` immediately transfers the lock to the waiter | Waiter still has to wait for the notifier to unlock and contend for the lock. | Keep critical sections short; always recheck the predicate. |
| Using `Thread.sleep()` while holding the lock to wait | The thread that updates the predicate may not be able to acquire the lock. | Use `await()` or an existing concurrent abstraction. |
| Swallowing `InterruptedException` and continuing | Loses the cancellation request, potentially violating the contract. | Propagate or restore the interrupt flag and exit per policy. |
| Resetting the full timeout after every wakeup | May wait longer than the intended deadline. | Use `awaitNanos(remaining)` or a deadline. |
| Creating Conditions for unrelated fields on a shared lock | Complex design and deadlock risk. | Analyze invariants and ownership before creating queues. |
| Writing custom lock/condition logic for every queue | Higher verification and maintenance cost. | Prefer `BlockingQueue` when suitable. |

A subtle bug: code can maintain data correctness yet **fail to make progress**. For example, both producers and consumers await on accurate predicates, but nobody signals the necessary condition. Therefore, evaluate **safety** (never exceeding capacity, never taking from an empty queue) and **liveness** (appropriate waiters eventually wake up) separately.

## 16. Comparison with Object.wait/notify and High-Level APIs

| Tool | Use Case | Characteristics |
|---|---|---|
| `Object.wait()/notify()/notifyAll()` | Coordination on an intrinsic monitor. | One wait set per object; must use `synchronized` and `while`. |
| `ReentrantLock` + multiple `Condition`s | Concurrent structures with multiple predicates on one shared state. | Multiple condition queues, `lockInterruptibly`, timed wait; must use the same lock and `while`. |
| `BlockingQueue` | Producer–consumer needing a queue. | Wait/signal mechanisms and capacity management are built into the library. |
| `Semaphore` | Managing permit counts, limiting concurrent tasks. | Permits are stored; unlike `signal()`, which does not accumulate. |
| `CountDownLatch` | Waiting for a one-shot condition like "N tasks completed". | Not resettable; no need to manage a Condition manually for a one-time signal. |
| `CyclicBarrier`/`Phaser` | Multi-phase coordination. | Built-in phase protocols instead of writing complex predicates manually. |

Different Conditions **are not different locks**. The strength of the model is one lock protecting invariants while multiple queues **reflect distinct waiting reasons**. If you only need to pass items between workers, prefer `ArrayBlockingQueue` or `LinkedBlockingQueue` over writing your own to reduce risk.

## 17. Checklist When Designing Multiple Conditions

1. Identify the **shared state/invariants**: who owns `queue`, `capacity`, `closed`?
2. Choose **one appropriate lock** for all access paths to that state.
3. List independent predicates: `notEmpty`, `notFull`, `closed`, `ready`, `finished`...
4. Create a Condition only when a separate wait queue is genuinely needed for a waiter group.
5. In each waiting method: **lock → while (predicate false) await → act → unlock in finally**.
6. In each updating method: **lock → update state → signal appropriate condition → unlock**.
7. If an event affects multiple groups, especially close/cancel, notify **all relevant Conditions**; use `signalAll()` if every waiter must re-evaluate.
8. Account for spurious wakeups, another thread consuming the resource first, timeouts, and interruption.
9. Do not hold unrelated locks while awaiting: `await` only releases its associated lock, which can cause deadlock if waiting for a thread that needs another lock.
10. Clearly specify the close contract and remaining items in the queue; decide whether methods throw an exception, return a sentinel, or wait.
11. Test with multiple producers and consumers, verifying item counts and sums rather than just a single run.
12. When a problem already has a standard abstraction, prefer high-level APIs.

## 18. Self-Check Questions

1. **Why do `notEmpty` and `notFull` share one lock?** Because both predicates depend on the same queue state; invariants must be protected by one consistent mutual-exclusion protocol.
2. **After `put()`, why signal `notEmpty`?** Because the queue just gained an item; consumers waiting for an item need to wake up, not producers waiting for space.
3. **After `take()`, why signal `notFull`?** Because capacity was just freed so a producer can place the next item.
4. **On close, is calling `notEmpty.signalAll()` enough?** No, if producers are waiting on `notFull`; all relevant groups must be notified.
5. **Does `signal()` guarantee the waiter runs immediately?** No; the waiter must reacquire the lock before `await()` returns.
6. **Why is `while` mandatory even with two Conditions?** Because of spurious wakeups and the fact that the predicate may change before the waiter reacquires the lock.
7. **Does `signal()` store a permit for threads arriving later?** No; state/predicates must store the truth, or use `Semaphore` if permits are needed.
8. **Does using a fair `ReentrantLock` eliminate the need for `while`?** No. Fairness does not guarantee the condition is still true upon wakeup.
9. **Does `await()` release other locks the thread is holding?** No; it only releases the Condition's associated lock per its contract.
10. **When should you replace custom Conditions with `BlockingQueue`?** When the goal is standard producer–consumer data passing and no special coordination protocol is required.

**Key takeaway:** one `ReentrantLock` protects the **shared state**, multiple `Condition`s partition **waiter groups by predicate**, and `while` ensures every wakeup rechecks the current truth. Update state and signal the right condition under the same lock, and wake all groups that need to exit upon closing/canceling.
