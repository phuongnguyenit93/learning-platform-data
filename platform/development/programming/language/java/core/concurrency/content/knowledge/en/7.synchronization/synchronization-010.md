# Preserving Invariants While Waiting and After Waking Up in Java Synchronization

## Objectives and Scope

When multiple threads coordinate through shared state, a thread may have to **wait for a condition** before proceeding. For example, a consumer waits for a buffer to have data, a producer waits for available space, or a worker waits for a `ready` flag. Calling `wait()` or `Condition.await()` is only a small part of the problem: before releasing the lock, the state must be **consistent**; after being woken up and reacquiring the lock, the thread must **recheck the condition**, because a signal does not guarantee that the condition is still true.

This lesson helps you:
- Distinguish an object's **invariant** from the **condition predicate** of the waiting operation.
- Understand the protocol **acquire lock → check predicate → wait and release lock → reacquire lock → recheck → act**.
- Know why `while` must be used instead of `if` around `wait()/await()`, even when using `notifyAll()/signalAll()`.
- Avoid lost notifications, inconsistent intermediate state that violates invariants, waking the wrong group of waiters, incorrectly recalculated timeouts, and ignoring `InterruptedException`.
- Use `synchronized` monitors and `ReentrantLock` + `Condition`, and recognize when to use `BlockingQueue` or `CountDownLatch`.
- Run **Java 17+** examples yourself with clearly stated outputs, invariant reasoning, and demo limitations.

**Scope:** Java synchronization primitives and the Java Memory Model in general. Annotations, executors, or Spring-specific features are not used here, as there is a dedicated chapter on Spring.

## 1. Invariants and Predicates Are Not the Same Thing

An **invariant** describes a relationship that must hold whenever a shared object is in a state observable by other threads according to the object's protocol.

For a bounded buffer with capacity `capacity` and `size` as the number of elements:

~~~text
0 <= size <= capacity
size == number of elements currently in the buffer
elements are retrieved in strict FIFO order if the buffer guarantees FIFO
~~~

For producers and consumers, the **predicate** allowing an operation to proceed is different:

~~~text
Producer inserts an element: notFull  = (size < capacity)
Consumer removes an element: notEmpty = (size > 0)
~~~

An empty buffer **still satisfies the invariant**, but the consumer's predicate is false so the consumer must wait. A full buffer **still satisfies the invariant**, but the producer needs to wait. When threads modify the buffer, they must always keep the invariant true at points where they **release the lock, enter a wait, or publish state**; a waiting predicate can change from true to false while the invariant remains true at all times.

Example of a buffer with capacity=1, currently holding `A`:

| Point in time | `size` | Invariant | `notEmpty` | `notFull` |
| --- | ---: | --- | --- | --- |
| Before taking A | 1 | True | True | False |
| After taking A | 0 | True | False | True |
| After adding B | 1 | True | True | False |

**Rule:** the invariant protects the **validity of the state**; the predicate determines the **permission to perform the next operation**. A signal only says "the state may have changed"; it does not directly substitute for the predicate.

## 2. Why Must Checking and Waiting Happen Under the Same Locking Protocol?

Classic mistake:

~~~java
// Illustrates broken logic: check and wait are not coordinated.
if (!ready) {
    waitForSignal();
}
~~~

If thread A sees `ready=false`, thread B changes `ready=true` and sends the signal, and only then does A start waiting, the signal has already passed. A may wait forever even though the state is ready. This is a form of **missed notification / lost signal**.

With a monitor, the correct pattern is:

~~~java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    // Proceed only when the predicate is true under the monitor.
    consumeProtectedState();
}
~~~

This is an **illustrative snippet inside a method**, assuming `monitor`, `ready`, and `consumeProtectedState()` are already declared and `InterruptedException` is handled or declared. The thread modifying the state must use the **same monitor**:

~~~java
synchronized (monitor) {
    ready = true;
    monitor.notifyAll();
}
~~~

Sequence:
1. The waiting thread acquires the monitor and reads the predicate.
2. If the predicate is false, it calls `monitor.wait()` **while still holding that monitor**.
3. `wait()` places the thread in the wait set and **releases `monitor`'s monitor** so another thread can acquire the lock, change the state, and send a signal.
4. When `wait()` returns normally, the thread has **reacquired the monitor**; it loops through `while` to recheck the new predicate.
5. Only when the predicate is true does the thread perform the operation and update the entire invariant within the required lock scope.

Checking and starting to wait are coordinated through the same monitor, so the producer cannot slip into the "gap" in between and cause a valid update to be missed. If the producer updates **before** the consumer acquires the monitor, the consumer observes a true predicate and **does not wait**. We do not need to count `notify` calls already sent: **the latest state is the source of truth**.

### Which Lock Does wait() Release?

`Object.wait()` only releases the **monitor of the object on which `wait()` is called**; it does not automatically release other monitors or `ReentrantLock`s that the thread is holding. Before returning or throwing `InterruptedException`, the thread must reacquire the monitor used for waiting. If code holds another lock B while calling `wait()` on A, threads needing B can still get stuck: this is a source of deadlock to avoid.

`Thread.sleep()` **does not release the monitor**. Therefore, calling `Thread.sleep(100)` inside `synchronized` cannot substitute for a valid condition wait.

## 3. Preserving the Invariant Before Releasing the Lock

Consider a quantity `total` split into `available` and `reserved`:

~~~text
available >= 0
reserved >= 0
available + reserved == total
~~~

The following snippet is fundamentally wrong:

~~~java
synchronized (lock) {
    available--; // Invariant available + reserved == total is temporarily violated.
    lock.wait(); // Releases the lock while state is inconsistent.
    reserved++;  // May never reach here.
}
~~~

This is an **intentionally broken snippet**, only illustrating the bug, not a standalone runnable class. When `wait()` releases the monitor, other threads acquiring `lock` will be able to observe `available + reserved == total - 1`. If the thread is interrupted, the `reserved` increment may not execute. `synchronized` automatically releases the lock when exiting the block, but **does not roll back data**.

Better is to **wait before beginning to alter the invariant**, then perform the complete update under the lock:

~~~java
synchronized (lock) {
    while (available == 0) {
        lock.wait();  // State remains valid before releasing the lock.
    }

    available--;
    reserved++;       // Completes a valid transition.
}
~~~

This is also a snippet inside a method with `throws InterruptedException` and declared fields. The resource-return path must modify both fields under the **same `lock`** and then call `notifyAll()` when it can make `available > 0`.

Inside a critical section, intermediate states can exist while the thread still holds the lock, but you must be careful with callbacks, reentrant synchronized methods, and exceptions. Another method could be invoked while the state is incomplete and observe a broken invariant. It is best to **validate first, commit state concisely and atomically, and restore the invariant before any wait/unlock/return statement**.

## 4. Why Must You Use while After Waking Up?

`Object.wait()` and `Condition.await()` can stop waiting **while the predicate is still false**. There are at least three reasons:

1. **Spurious wakeup:** Java allows wait/await to return even without a signal corresponding to the predicate. Therefore, code must be written to tolerate this case.
2. **Multiple waiters competing for a resource:** Two consumers are both woken by `notifyAll()`, but the first consumer takes the only element; when the second consumer reacquires the lock afterward, the buffer is already empty.
3. **State changes after the signal:** The producer sends a signal, and then another thread may grab the lock and consume the resource before the earlier waiter.

~~~text
Two consumers C1, C2 are waiting on notEmpty.
Producer adds a single item X and calls notifyAll().

C1 acquires the monitor first --> takes X, size=0, releases the monitor.
C2 acquires the monitor next  --> size is still 0.

if (!queue.isEmpty()) { wait(); }  // WRONG: after wakeup, may remove from empty.
while (queue.isEmpty()) { wait(); } // CORRECT: recheck before removing.
~~~

The correct consumer pattern is:

~~~java
synchronized (monitor) {
    while (queue.isEmpty()) {
        monitor.wait();
    }
    return queue.removeFirst();
}
~~~

This is an illustrative snippet inside a method with `throws InterruptedException`. **The final check and `removeFirst()` are under the same monitor**. If the lock is dropped between the two steps, the check-then-act race returns.

Do not use a flag like `receivedNotify` as the source of truth and ignore the queue's predicate. `notify()/notifyAll()` carries no elements, does not guarantee resource counts, and signals do not accumulate for waiters that start waiting later.

## 5. Object.wait(), notify(), and notifyAll() Contracts

| API | Role | Key Rules |
| --- | --- | --- |
| `monitor.wait()` | Wait indefinitely | Caller must hold the monitor; releases monitor while waiting and reacquires it before returning |
| `monitor.wait(timeoutMillis)` | Wait with a timeout | `wait(0)` means wait indefinitely; timeout does not guarantee the predicate is true |
| `monitor.notify()` | Wakes **one** arbitrary waiter in the wait set | Does not choose by business logic, does not guarantee fairness; caller must hold the monitor |
| `monitor.notifyAll()` | Wakes all waiters in the wait set | Each waiter must contend for the monitor and recheck the predicate |
| `Thread.sleep(duration)` | Pause for a duration | **Does not release the monitor**, not a condition synchronization mechanism |

All of `wait`, `notify`, and `notifyAll` require the calling thread to hold **that exact monitor**. Without `synchronized(monitor)` or equivalent monitor ownership, they throw `IllegalMonitorStateException`. Holding the monitor of **another object** is invalid.

### Signaling Does Not Immediately Transfer the Lock

~~~java
synchronized (monitor) {
    ready = true;
    monitor.notifyAll();
    // Current thread still holds the monitor until it exits the block.
}
~~~

Woken waiters cannot run the code after `wait()` until they have reacquired the monitor. If the signaling thread holds the lock for a long time after `notifyAll()`, wakeup latency is also long.

### When Is notifyAll() Appropriate?

If the same monitor has multiple kinds of waiters—for example, producers waiting on `notFull` and consumers waiting on `notEmpty`—`notify()` might pick a waiter **waiting on a predicate that is not yet true**. It wakes up and goes right back to waiting, while a waiter in the group that should run stays asleep. In a shared monitor protocol, `notifyAll()` is usually easier to prove progress for. On the flip side, waking many waiters can add contention.

`Condition` with `ReentrantLock` lets each predicate have its own wait set (`notFull`, `notEmpty`), so you can `signal()` the right group. Even when signaling the right group, **the predicate must still be rechecked in a while loop**.

## 6. Runnable Example 1: Bounded Buffer Using wait/notifyAll

A bounded buffer has two predicates: `queue.size() < capacity` for the producer and `!queue.isEmpty()` for the consumer. We keep the same monitor for **checking**, **updating the queue**, **signaling**, and **taking a size snapshot**.

Create the file **`MonitorBufferDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class MonitorBufferDemo {
    static final class BoundedBuffer<T> {
        private final ArrayDeque<T> queue = new ArrayDeque<>();
        private final int capacity;

        BoundedBuffer(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        synchronized void put(T value) throws InterruptedException {
            Objects.requireNonNull(value);
            while (queue.size() == capacity) {
                wait();
            }
            queue.addLast(value);
            notifyAll();
        }

        synchronized T take() throws InterruptedException {
            while (queue.isEmpty()) {
                wait();
            }
            T value = queue.removeFirst();
            notifyAll();
            return value;
        }

        synchronized int size() {
            return queue.size();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        BoundedBuffer<Integer> buffer = new BoundedBuffer<>(2);
        List<Integer> received = new ArrayList<>();

        Thread consumer = new Thread(() -> {
            try {
                for (int i = 0; i < 6; i++) {
                    received.add(buffer.take());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        Thread producer = new Thread(() -> {
            try {
                for (int i = 1; i <= 6; i++) {
                    buffer.put(i);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        consumer.start();
        producer.start();

        producer.join();
        consumer.join();

        System.out.println("received=" + received);
        System.out.println("remaining=" + buffer.size());
    }
}
~~~

Compile and run on Java 17+:

~~~bash
javac MonitorBufferDemo.java
java MonitorBufferDemo
~~~

Stdout without interruption:

~~~text
received=[1, 2, 3, 4, 5, 6]
remaining=0
~~~

**Why is this correct?**

- One producer inserts the numbers 1–6 in order, one consumer takes six elements in order, and the queue guarantees FIFO. Order is preserved regardless of which thread runs first.
- `put()` only inserts when `queue.size() < capacity`; `take()` only removes when `!queue.isEmpty()`.
- No thread accesses `ArrayDeque` directly from outside the buffer. **Every access path** goes through the buffer object's monitor.
- `wait()` is only called while the queue is still valid; it releases the monitor so the other side can modify the queue.
- After wakeup, the `while` loop rechecks the predicate. `notifyAll()` is called **after the state changes**, allowing the opposite side to try to proceed.
- `join()` ensures `main` reads `received` after the consumer has finished. The `received` list is only written by the consumer; `main` does not read it concurrently.

**Limitations:** The demo knows the send and receive counts in advance, and has no job cancellation, abnormal shutdown, or timeouts. If the producer stops early due to an error, the consumer can wait indefinitely; production code needs an explicit `close`/end-of-stream protocol, timeouts, or cancellation. `ArrayDeque` is not thread-safe when used directly; safety here comes from the monitor protecting the buffer. For typical producer–consumer scenarios, consider standard `BlockingQueue` instead of writing one by hand.

### Invariant Analysis Across a Wait Cycle

~~~text
Consumer holds monitor:
  size == 0 => cannot take yet, invariant still holds
     |
     v
  wait() releases monitor
     |
     v
Producer acquires monitor, put(X), size == 1, notifyAll(), releases monitor
     |
     v
Consumer reacquires monitor, checks size > 0
     |
     +-- true: takes X, size == 0, invariant still holds
     |
     +-- false: keeps waiting if another consumer already took X
~~~

Between the final predicate check and the removal operation, **the monitor is not released**. Therefore, there is no interleaving that causes a remove-from-empty in that critical section.

## 7. Runnable Example 2: A Gate That Stores State Without Depending on notify

A `Gate` starts closed; any thread calling `awaitOpen()` must wait until `open()` is called. The open state is **persisted**; waiters arriving later still pass through without requiring a new notification.

Create the file **`GateInvariantDemo.java`**:

~~~java
public class GateInvariantDemo {
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
        Thread[] workers = new Thread[3];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                try {
                    gate.awaitOpen();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "waiter-" + i);
            workers[i].start();
        }

        gate.open(); // May happen before a waiter actually starts waiting.

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("open=" + gate.isOpen());
        System.out.println("completed=3");
    }
}
~~~

Run:

~~~bash
javac GateInvariantDemo.java
java GateInvariantDemo
~~~

Normal stdout:

~~~text
open=true
completed=3
~~~

Even if `main` opens the gate very early, threads that start later still check `open==true` and **do not call wait**. If a waiter is already in the wait set, `notifyAll()` wakes it up to check the predicate. `main` does not assert any execution order among workers; it only waits for them to finish with `join()`. This is a pattern for a **one-way condition**. If the gate is opened and closed multiple times or has phases, you must define a generation/phase; `CountDownLatch` (one-shot), `CyclicBarrier`, or `Phaser` is usually more appropriate.

## 8. Condition.await(): Same Principles, Multiple Wait Sets

`ReentrantLock` combined with `Condition` also follows the **predicate-under-lock** protocol. It lets you separate producer and consumer waiters into two distinct conditions.

Pattern:

~~~java
lock.lockInterruptibly();
try {
    while (!ready) {
        condition.await();
    }
    useState();
} finally {
    lock.unlock();
}
~~~

This is an illustrative snippet inside a method with `lock`, `condition`, `ready`, and `useState` already declared. Rules to keep:
- The caller must hold the exact `ReentrantLock` associated with the `Condition`.
- `await()` releases the lock while waiting, then **reacquires the lock before returning** or throwing `InterruptedException`.
- `signal()`/`signalAll()` signals the corresponding condition; the signaling thread still holds the lock until it unlocks.
- The waiter rechecks the predicate with `while`, even with signals or spurious wakeups.
- `unlock()` is always in `finally`; the lock must encompass the entire invariant modification.

### Runnable Example 3: Buffer with notFull and notEmpty

Create the file **`ConditionBufferDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionBufferDemo {
    static final class Buffer<T> {
        private final ArrayDeque<T> items = new ArrayDeque<>();
        private final int capacity;
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();

        Buffer(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity <= 0");
            }
            this.capacity = capacity;
        }

        void put(T item) throws InterruptedException {
            Objects.requireNonNull(item);
            lock.lockInterruptibly();
            try {
                while (items.size() == capacity) {
                    notFull.await();
                }
                items.addLast(item);
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        T take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (items.isEmpty()) {
                    notEmpty.await();
                }
                T result = items.removeFirst();
                notFull.signal();
                return result;
            } finally {
                lock.unlock();
            }
        }

        int size() {
            lock.lock();
            try {
                return items.size();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Buffer<Integer> buffer = new Buffer<>(2);
        List<Integer> received = new ArrayList<>();

        Thread producer = new Thread(() -> {
            try {
                for (int i = 1; i <= 5; i++) {
                    buffer.put(i);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        Thread consumer = new Thread(() -> {
            try {
                for (int i = 0; i < 5; i++) {
                    received.add(buffer.take());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        producer.start();

        producer.join();
        consumer.join();

        System.out.println("received=" + received);
        System.out.println("remaining=" + buffer.size());
    }
}
~~~

Run:

~~~bash
javac ConditionBufferDemo.java
java ConditionBufferDemo
~~~

Stdout on a normal execution path:

~~~text
received=[1, 2, 3, 4, 5]
remaining=0
~~~

The buffer uses a single `ReentrantLock` protecting **all** accesses to `items`. Producers only `await` on `notFull`; consumers only `await` on `notEmpty`. Each successful update signals the opposite side when its predicate may have become true, while the waiter still rechecks with `while`. `signal()` for a single waiter fits this buffer design; for more complex protocols, examine liveness and whether `signalAll()` is required.

**Note:** a `Condition` does not automatically make all operations on a data structure safe. If external code directly modifies `items` without holding `lock`, the invariant can still be broken.

## 9. Timeout: Waking Up Due to Expiration Does Not Mean the Predicate Is True

`Object.wait(long millis)` supports a wait duration; `wait(0)` means wait indefinitely. `Condition.await(long, TimeUnit)` returns a result indicating whether it was signaled or timed out, and `Condition.awaitNanos` returns the remaining time. But in every case, upon returning from a wait:
- A timeout **does not** turn false into true.
- A signal **does not** prove the predicate is still true when the waiter reacquires the lock.
- A spurious wakeup **does not** change the business invariant.

Wrong way:

~~~java
while (!ready) {
    monitor.wait(1000);
}
~~~

If you keep reusing a full one-second timeout on every wakeup, the total wait time can stretch to many times one second. Furthermore, if a hard deadline is truly needed, you must also account for time spent waiting to acquire the lock.

### Condition.awaitNanos Pattern for Managing Wait Budget

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

// Fields and methods inside a class, not a standalone file:
private final ReentrantLock lock = new ReentrantLock();
private final Condition changed = lock.newCondition();
private boolean ready;

public boolean awaitReady(long timeout, TimeUnit unit)
        throws InterruptedException {
    long remaining = unit.toNanos(timeout);
    lock.lockInterruptibly();
    try {
        while (!ready) {
            if (remaining <= 0) {
                return false;
            }
            remaining = changed.awaitNanos(remaining);
        }
        return true;
    } finally {
        lock.unlock();
    }
}

public void publishReady() {
    lock.lock();
    try {
        ready = true;
        changed.signalAll();
    } finally {
        lock.unlock();
    }
}
~~~

`awaitNanos` releases the lock and reacquires it before returning; each time it wakes, the thread loops to check the predicate, and `remaining` is decremented per the API contract so the full timeout is never "re-granted". On timeout, the method returns `false` without modifying state, and `finally` releases the lock.

**Limitation:** the budget above applies to the **condition wait time**; `lockInterruptibly()` at the start could wait a long time without being subtracted from `remaining`. If you need a deadline for the entire journey including lock acquisition, compute a deadline from `System.nanoTime()` and use `tryLock(remaining, unit)` or an equivalent protocol. Do not claim a standalone timed wait is an end-to-end request deadline.

## 10. Interrupts and Exceptions Must Preserve State

### 10.1. InterruptedException While Waiting

When interrupted, `Object.wait()`/`Condition.await()` can throw `InterruptedException`. With a monitor wait, the thread must reacquire the monitor before the exception is thrown according to the contract. **Interruption does not mean the condition has become true**.

In the buffer:
- `put` interrupted while waiting for space: since `addLast` was not called, that put did not insert an element.
- `take` interrupted while waiting for data: since `removeFirst` was not called, that take did not remove an element.
- Other threads may still have modified the buffer while this thread was waiting; do not interpret "no update from the interrupted operation" as "the buffer did not change".

If a method can propagate the exception, it is usually best to declare `throws InterruptedException` so the caller decides cancellation behavior. If it cannot throw upward and needs to exit:

~~~java
try {
    doInterruptibleWait();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // Restore interrupt flag.
    return;
}
~~~

This is an illustrative snippet inside a `void` method. Do not swallow the interruption and keep waiting forever if the application has a shutdown procedure.

### 10.2. Releasing a Lock Does Not Mean Changes Are Rolled Back

~~~java
synchronized (monitor) {
    available--;
    operationThatMayThrow();
    reserved++;
}
~~~

The snippet above illustrates a bug: if the method throws an exception partway through, `synchronized` automatically releases the monitor on exit, but the invariant `available + reserved == total` may be broken. You need to **validate before committing**, perform updates consistently under the lock, or roll back accurately when an exception occurs. Minimize side effects that can throw while an invariant is temporarily inconsistent.

With `ReentrantLock`, use:

~~~java
lock.lock();
try {
    // Check predicate and update invariant completely.
} finally {
    lock.unlock();
}
~~~

This is an illustrative snippet, assuming `lock` is initialized. Do not skip `unlock()` in exception paths; likewise, do not attempt to unlock if the lock was never acquired.

### 10.3. Shutdown and Conditions That Will Never Become True

If the producer stops permanently while a consumer waits indefinitely on `notEmpty`, the program can hang even though the invariant still holds. A real protocol must model a **closed/cancelled** condition and wake up waiters:

~~~java
synchronized (monitor) {
    while (queue.isEmpty() && !closed) {
        monitor.wait();
    }
    if (queue.isEmpty() && closed) {
        // Terminate per contract, e.g., return Optional.empty().
    } else {
        // Take the available element.
    }
}
~~~

This is **Java pseudocode** illustrating control flow with `monitor`, `queue`, and `closed` protected by the same lock, not a standalone runnable method. The `close` path must set `closed=true` and call `notifyAll()` while holding the monitor. When there are multiple kinds of waiters, verify whether shutdown wakes **every waiting group**. If using a standard queue, you can use a sentinel/poison pill or an appropriate cancellation protocol, ensuring the sentinel cannot be confused with valid data.

## 11. Happens-Before and Memory Visibility

The monitor protocol both prevents lost notifications and ensures visibility:

~~~java
// Producer:
synchronized (monitor) {
    data = prepared;
    ready = true;
    monitor.notifyAll();
}

// Consumer:
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    use(data);
}
~~~

These are two illustrative snippets using variables and methods declared in an enclosing scope. Under the Java Memory Model, writes before an **unlock** of a monitor happen-before subsequent actions after a **lock** on the same monitor. Thus, once the consumer reacquires the monitor, it is guaranteed to see the data published by the producer. Simply calling `notifyAll()` without protecting the predicate and shared data under a memory visibility protocol is not enough.

`Condition.await()` paired with `ReentrantLock` also releases and reacquires the lock and inherits the corresponding memory semantics. Classes such as `BlockingQueue`, `CountDownLatch`, `Semaphore`, and `Future` have their own memory consistency contracts; using the right abstraction avoids many manual proof errors.

**Do not** replace a wait loop by inspecting `thread.getState() == WAITING` or relying on `Thread.sleep`. `Thread.State` is only a snapshot at the moment it is read, cannot safely determine business conditions, and provides no mutual exclusion.

## 12. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| `if (!ready) wait()` | Spurious wakeup or another waiter can make the predicate false | Use `while (!ready) wait()` |
| Checking `ready` outside the lock before waiting | Leaves a window for lost signals | Check and wait under the same monitor |
| Calling wait/notify without holding the right monitor | `IllegalMonitorStateException` | Hold the right monitor when calling |
| Waiting while the invariant is half-broken | Releases the monitor for other threads to read invalid state | Restore the invariant before wait/unlock |
| Assuming notifyAll makes waiters run immediately | Waiters still have to reacquire the monitor | Keep critical sections short, recheck predicate |
| Using only notify with multiple waiter types | May wake a thread that cannot make progress | `notifyAll` or multiple `Condition`s |
| Using sleep inside synchronized to wait | Does not release the monitor, not tied to a predicate | `wait/await` or a higher-level primitive |
| Timed wait resetting the full timeout each iteration | Multiple wakeups extend total wait beyond target | Use a deadline or track remaining time |
| Ignoring InterruptedException | Cancellation/shutdown may hang | Propagate or restore interrupt and exit |
| Exception between two invariant-update steps | Lock releases but state does not roll back automatically | Atomic commit or structured rollback |
| Waiting forever without a close protocol | Threads may wait and never finish | Closed flag, signal, timeout/cancel |
| Reading state outside the agreed lock | Visibility issues or inconsistent snapshots | Same lock or safely published snapshot |
| Basing notify decisions on getState() | Snapshot is racy, not a predicate | Rely on lock-protected state |
| Holding another lock when calling wait | Wait does not release all locks; risk of deadlock | Control lock ordering and lock scope |

## 13. Design and Verification Guidelines

**Step 1 — Write down the invariant:** describe what must always hold whenever the object releases its lock. For a buffer: `0 <= size <= capacity`, and `size` equals the actual element count.

**Step 2 — Write down each waiter type's predicate:** producers wait for `size < capacity`, consumers wait for `size > 0`. If there is a closed state or multiple phases, incorporate it explicitly into the condition.

**Step 3 — Choose one lock to protect the state:** every read/write path related to the invariant must use the same monitor/lock, or another ownership protocol with equivalent guarantees. Do not let callbacks mutate state directly outside the lock.

**Step 4 — Check the invariant at lock-release points:** before `wait()`, `await()`, return, or an exception exits the critical section, the state must be consistent.

**Step 5 — Upon waking up, recheck the predicate:** always use `while`; never infer that the predicate is true from receiving a signal.

**Step 6 — Signal after changing state:** send signals under the right monitor/lock, to the right waiter group, and do not forget shutdown/closed. A signal does not replace the predicate.

**Step 7 — Design failure and timeout paths:** every waiter must have an exit path when the producer can no longer continue, when interrupted, or when a deadline expires; never leak half-updated state.

**Step 8 — Choose higher-level abstractions when appropriate:** `BlockingQueue` for producer/consumer, `CountDownLatch` for one-shot readiness, `Semaphore` for permits, `Phaser` for multiple phases. Write a custom monitor protocol only when the invariant is genuinely specialized.

**Step 9 — Test key interleavings:** signal arrives before waiter starts waiting; two waiters wake up and contend for one element; timeout before/after signal; interrupt during wait; exception mid-update; close while queue is empty. Use `CountDownLatch`/barriers to coordinate tests; **do not treat `Thread.sleep` as proof of ordering**.

**Step 10 — Observe liveness and performance:** verify no deadlock, no abnormal starvation, and no unbounded queue growth; measure queue wait time, lock contention, successful throughput, p95/p99 latency, and errors. A state that always satisfies the invariant while threads wait forever still fails operational requirements.

## 14. Self-Check Questions

1. Does an empty buffer violate the invariant `0 <= size <= capacity`? **No**, but the consumer's predicate `size > 0` is false.
2. Why shouldn't you call `wait` while two fields have not yet been updated together? **Because wait releases the monitor, exposing an inconsistent intermediate state to other threads.**
3. Why is `while` needed after `notifyAll`? **Spurious wakeups and contention can leave the predicate false.**
4. If a signal arrives before a waiter enters the wait set, how do you avoid a lost notification? **Write and read a predicate under the same monitor; the waiter skips waiting when it is already true.**
5. Does `Object.wait()` release every lock the thread is holding? **No, only the monitor of the object on which wait is called.**
6. Does `Thread.sleep()` inside synchronized release the monitor? **No.**
7. Why doesn't `notifyAll()` guarantee a waiter runs immediately? **Waiters still have to reacquire the monitor after the signaling thread releases it.**
8. Why doesn't `wait(0)` time out immediately? **The value 0 means wait indefinitely.**
9. When `Condition.awaitNanos()` returns and the predicate is still false, what should you do? **Check remaining time and continue the while loop or return a timeout.**
10. Can `InterruptedException` be treated as the predicate becoming true? **No**, it is a separate cancellation path.
11. When a method throws an exception mid-update, does synchronized automatically roll back? **No, it only guarantees releasing the monitor.**
12. Can a consumer wait forever if the producer stops? **Yes**, so a close, cancellation, timeout, or sentinel protocol is needed.
13. When should you use `BlockingQueue` instead of writing wait/notify yourself? **When the primary requirement is simply transferring elements from producers to consumers.**
14. Can you use `thread.getState()` to decide whether a condition is true? **No**, that is a thread snapshot, not lock-protected business state.
15. How do an invariant and a predicate differ? **An invariant states whether the object is valid; a predicate states whether an operation is allowed to proceed.**

## Conclusion

**Invariants must hold whenever access is handed off**, especially before `wait()/await()` releases the lock, and before an unlock or exception exits a critical section. **Predicates must be rechecked after a thread wakes up and reacquires the lock**. Notifications do not store business state, do not guarantee immediate execution of waiters, and do not prove that the condition is true.

A safe protocol is **acquire lock → check predicate → wait and release lock if false → reacquire lock → recheck in while → update complete invariant → signal if needed → release lock**. Exit paths for timeouts, interruptions, and shutdown must also be added, along with invariant recovery when exceptions occur.

## Java SE 17 Documentation

- [Object.wait/notify/notifyAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): monitor, wait set, spurious wakeup, interruption.
- [Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): await, awaitNanos, signal, signalAll.
- [ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock, lockInterruptibly, unlock.
- [BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): take/put/offer/poll and memory consistency.
- [Java Language Specification, Chapter 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Threads and Locks; happens-before.
