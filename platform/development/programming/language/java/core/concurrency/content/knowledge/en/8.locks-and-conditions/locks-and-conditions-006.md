# Condition await(), signal(), signalAll() in Java Concurrency

> **Context:** Java SE Locks & Conditions, focusing on `java.util.concurrent.locks.Condition`, how threads coordinate with `ReentrantLock`, condition state (*predicate*), the wait/notify protocol, interruption, timeouts, and Java Memory Model guarantees. This article does not use Spring-specific concurrency APIs.

## 1. The problem: needing to wait for a state, not just acquire a lock

A **Lock** lets threads take turns entering a critical section, but it does not directly answer questions like “is data available yet?”, “is there still space in the buffer?”, or “has the work been logically unlocked yet?”. A thread can acquire the lock while the **business condition is not yet satisfied**. If it holds the lock and keeps checking in a loop, other threads cannot enter to change the state; if it releases the lock and calls `Thread.sleep()`, detecting the change is delayed and there is no reliable notification protocol.

`Condition` is a *condition queue / wait set* mechanism attached to a `Lock`. It allows a thread to:

1. **Hold the lock** and inspect the protected state.
2. If the predicate is not yet true, call `await()` to **release the lock and wait**.
3. Another thread acquires the lock, **modifies the state**, and calls `signal()` or `signalAll()`.
4. The waiter wakes up, **must reacquire the lock**, and checks the predicate again before acting.

**Most important takeaway:** `Condition` does not store the “true/false value” of a condition, does not automatically remember every signal, and does not replace state variables. The actual condition is the **predicate defined by the program**, for example `!queue.isEmpty()` or `count < capacity`. The `await/signal` calls only help coordinate when that predicate changes.

## 2. Which Lock does a Condition belong to?

A `Condition` is created via `Lock.newCondition()`, most commonly `ReentrantLock.newCondition()`:

```java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

final class SimpleGate {
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition opened = lock.newCondition();
    private boolean isOpen;

    void open() {
        lock.lock();
        try {
            isOpen = true;
            opened.signalAll();
        } finally {
            lock.unlock();
        }
    }

    void awaitOpen() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            while (!isOpen) {
                opened.await();
            }
        } finally {
            lock.unlock();
        }
    }
}
```

This is a **complete compilable class** in `SimpleGate.java`. One thread calls `awaitOpen()` to wait until `isOpen` is set to true; another thread calls `open()`. If `open()` runs **before** `awaitOpen()`, the waiter sees the predicate is true under the lock and **does not need to wait**, so it does not miss the state change.

Key points from this code:

- `lock` protects **every** read/write of `isOpen`.
- `opened` is a Condition created **from that exact `lock`**.
- `await()` releases the lock while waiting and reacquires it before returning.
- `signalAll()` notifies waiters that they can re-check the predicate; it does not release the calling thread's lock by itself.
- `finally { lock.unlock(); }` guarantees the lock is released whether exiting normally or via an exception.

**One lock can create multiple distinct Conditions.** For example, a buffer can have one Condition for “not empty” and another Condition for “not full”. This is an important difference compared to a single monitor wait set via `Object.wait()/notifyAll()`.

## 3. Separating three concepts: lock, predicate, condition queue

Suppose we have a single-slot buffer:

- **Lock:** protects `item` and the operations that modify `item`.
- **Predicate notEmpty:** `item != null`; a consumer needs this predicate to be true before taking an item.
- **Predicate notFull:** `item == null`; a producer needs this predicate to be true before putting an item.
- **Condition notEmpty:** where consumers can sleep when the buffer is empty.
- **Condition notFull:** where producers can sleep when the buffer is full.

The two predicates are opposite logical states; the two Conditions are **two separate waiter queues** so the right group is notified. Neither Condition **knows on its own** whether `item` is null or not; the programmer must update the state and then notify.

Several bugs come from confusing them:

- Calling `notEmpty.signal()` **without writing an item**: the awakened consumer still sees an empty buffer.
- Placing an item **without signaling** when a relevant producer/consumer is waiting: the waiter can sleep indefinitely even though the predicate is true.
- Putting a consumer on `notFull.await()`: the consumer is waiting on the wrong event and may never make progress.
- Using `if` instead of `while`: after waking up, the condition may have been invalidated again by another thread.
- Modifying `item` outside `lock`: the predicate and the signal are no longer a consistent synchronized protocol.

## 4. What does `await()` do to the lock?

For a Condition created by `ReentrantLock.newCondition()`, a thread must **currently own the ReentrantLock** before calling `await()`. If it does not hold the lock, it throws `IllegalMonitorStateException`.

The typical flow is:

```text
Consumer thread                         Producer thread
------------------------------------    ------------------------------------
lock.lock()
check predicate: false
condition.await():
    enqueue self into condition wait queue
    release lock
    wait for signal/interrupt/spurious wakeup
                                        lock.lock()
                                        update state
                                        condition.signal()
                                        ... still holding lock ...
                                        lock.unlock()
    compete to reacquire lock
    lock has been reacquired
check predicate with while
process data when predicate is true
lock.unlock()
```

**`await()` releases the lock associated with the Condition, not any other locks the thread happens to hold.** With a reentrant `ReentrantLock`, the `newCondition()` implementation saves the hold count, releases the lock completely before waiting, and restores the ownership depth upon reacquire. If a thread holds both lock A and lock B, `conditionOfA.await()` does not automatically release B; holding B while waiting can cause a deadlock.

When `await()` returns normally, the thread **holds the lock again** and only then proceeds to the statement after `await()`. If interrupted, with `ReentrantLock.ConditionObject`, the thread must also reacquire the lock before `await()` throws `InterruptedException` per the implementation contract. Therefore, a `try/finally` block around `await()` properly releases the lock and leaves no path where unlock is skipped.

### Do not misunderstand `WAITING` and `BLOCKED`

In a thread dump, a thread waiting on `Condition.await()` on a `ReentrantLock` is typically observed as `WAITING (parking)`, or `TIMED_WAITING` for timed overloads. It is not necessarily `Thread.State.BLOCKED`, because `BLOCKED` is for waiting on an **intrinsic monitor**. After a signal, the waiter may still be waiting to reacquire the `ReentrantLock`; there is no guarantee it runs immediately.

## 5. What does `signal()` mean?

`condition.signal()` notifies **one waiter** waiting on the corresponding Condition. With a `ReentrantLock` Condition, an eligible waiter is moved from the condition queue to **compete to reacquire the associated lock**.

Example:

```java
lock.lock();
try {
    queue.add(item);       // predicate !queue.isEmpty() becomes true
    notEmpty.signal();     // notify one waiting consumer
} finally {
    lock.unlock();         // waiter only continues after reacquiring the lock
}
```

This is an **illustrative snippet inside a method** where `lock`, `queue`, `item`, and `notEmpty` are declared externally.

Three things to remember:

1. **Signal does not mean handing over lock ownership immediately.** The thread calling `signal()` still holds the lock until `unlock()`; the waiter must contend to reacquire it afterward.
2. **Signal does not “set the predicate to true”.** The state was changed by `queue.add(item)`; the signal only announces the possibility of progress.
3. **Signal is not a permit stored indefinitely.** If there is no waiter yet, calling `signal()` does not create a “saved wakeup” for a waiter that arrives later. Therefore, waiters must always **check the predicate first** to avoid lost signals.

With `ReentrantLock`, `ConditionObject` signals waiters in FIFO order on the condition queue; **the actual order of lock reacquisition** still depends on the lock policy and other contending threads. For the `Condition` interface in general, do not assume every implementation has the same ordering.

## 6. What does `signalAll()` mean?

`condition.signalAll()` notifies **all current waiters** on **that Condition**; each waiter must still reacquire the associated lock and check the predicate for itself.

`signalAll()` is appropriate when:

- A state change allows **multiple waiters** to proceed at once, such as a gate opening permanently for everyone.
- Multiple waiters are waiting on different detailed conditions on **the same Condition**, and you cannot tell which specific waiter to pick.
- There is an important state transition such as shutdown/cancellation where **all waiters** must wake up, check a shared flag, and exit.
- You cannot prove that signaling a single arbitrary waiter guarantees system progress.

The downside is **thundering herd**: many waiters are moved to contend for the same lock, yet only one thread can hold the lock at a time; many waiters wake up, find the predicate false, and go back to waiting. This can increase context switching, lock contention, and latency.

`signalAll()` **does not turn one item into N items**. If only one element is added to a queue, even if N consumers are awakened, only one consumer gets the element; the others must return to `await()` via the `while` loop.

Comparison table:

| API | Who does it wake? | Does it make the predicate true? | Does it release the caller's lock immediately? |
|---|---|---|---|
| `signal()` | One waiter on the corresponding Condition (if any) | No | No |
| `signalAll()` | All waiters on the corresponding Condition (if any) | No | No |
| `await()` | Does not wake other waiters; current thread waits | No | **Yes**: temporarily releases the associated lock and reacquires before returning |
| `unlock()` | Releases lock ownership; may let a contender acquire the lock | No | Yes: releases the lock per contract |

**There is no fixed waiter count that determines** when to use `signalAll()`. Look at the predicate and invariant: does one update allow exactly one waiter to make progress, or multiple waiters? Do multiple kinds of waiters share a Condition? Is there a shutdown or permanent state transition?

## 7. Why is `while` mandatory?

Standard pattern:

```java
lock.lock();
try {
    while (!predicate()) {
        condition.await();
    }
    performOperationWithPredicateTrue();
} finally {
    lock.unlock();
}
```

This is an **illustrative method skeleton**, with `lock`, `condition`, `predicate()`, and `performOperationWithPredicateTrue()` defined elsewhere; the method must declare or handle `InterruptedException`.

There are at least four reasons to re-check:

1. **Spurious wakeup:** `await()` may return even without a corresponding `signal()`, per the `Condition` contract. This is permitted behavior of waiting primitives; never rely on “it never happens on my machine”.
2. **Contention after signal:** a signaled waiter must **reacquire the lock**. Meanwhile, another thread may acquire the lock and consume the data first, making the predicate false again.
3. **SignalAll wakes multiple waiters:** perhaps only one waiter is actually eligible, and the remaining waiters must keep waiting.
4. **Notification is not a business outcome:** a state change might not satisfy all conditions, or a waiter may need to check more factors than just “an event occurred”.

Using `if (!predicate) await()` is a bug because after `await()` returns once, the thread could proceed while the predicate is false, reading an empty queue, writing past capacity, or violating an invariant.

**Nor may you call `await()` unconditionally and check the predicate afterward**: a producer may have finished its work and signaled **before** the waiter started waiting; if the waiter still enters `await()` despite the data already being present, it may sleep forever when no further signal arrives. The predicate is the **source of truth**.

## 8. Producer–consumer with two Conditions: `notEmpty` and `notFull`

A bounded buffer has two kinds of threads that need to wait for **two different reasons**:

- Producers wanting to put an item when the buffer is full ⇒ wait on `notFull`.
- Consumers wanting to take an item when the buffer is empty ⇒ wait on `notEmpty`.

Use **one lock** to protect the shared state and **two Conditions** to avoid waking the wrong group.

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

// Placed inside a BoundedBuffer<T> class with capacity > 0.
private final ReentrantLock lock = new ReentrantLock();
private final Condition notEmpty = lock.newCondition();
private final Condition notFull = lock.newCondition();
private final Deque<T> queue = new ArrayDeque<>();
private final int capacity;

void put(T item) throws InterruptedException {
    lock.lockInterruptibly();
    try {
        while (queue.size() == capacity) {
            notFull.await();
        }
        queue.addLast(item);
        notEmpty.signal();
    } finally {
        lock.unlock();
    }
}

T take() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        while (queue.isEmpty()) {
            notEmpty.await();
        }
        T item = queue.removeFirst();
        notFull.signal();
        return item;
    } finally {
        lock.unlock();
    }
}
```

This is a **member snippet of a generic class**, **not a standalone program**: it needs a constructor initializing `capacity` and must enforce `item != null` if `ArrayDeque` is chosen, since `ArrayDeque` does not accept null.

Tracing each operation:

- When the queue is full, the producer holds the lock but cannot add; `notFull.await()` temporarily **releases the lock**, allowing a consumer to enter `take()` and remove an item.
- When a consumer removes an item, the “has space” state may now be true, so it calls `notFull.signal()`.
- When the queue is empty, the consumer calls `notEmpty.await()` and releases the lock; a producer can now put an item.
- When a producer puts an item, the “has item” state may now be true, so it calls `notEmpty.signal()`.
- Checking the predicate, mutating the queue, and signaling all happen under **the same `lock`**, preventing races between checking and waiting.
- `signal()` is usually appropriate here because each `put/take` enables progress for at least one waiter in the opposite group; when designs modify multiple items, support shutdown, or have complex predicates, the `signal` vs `signalAll` choice must be re-evaluated.

In Java SE applications, if you only need a bounded producer-consumer queue, **`ArrayBlockingQueue` or `LinkedBlockingQueue`** is usually preferable and battle-tested. Building your own buffer helps you understand `Condition`, but also introduces potential bugs around timeouts, cancellation, capacity, shutdown, and exception safety.

## 9. Standalone Java 17+ example: await, signal, and signalAll

This program demonstrates two coordination patterns:

- **OneSlot** is a single-slot buffer. `put` waits on `notFull` when the slot is occupied, `take` waits on `notEmpty` when the slot is empty; each side uses `signal()` to notify the other.
- **Gate** has the predicate `isOpen`. Once opened, all waiters can proceed, so `signalAll()` is appropriate.
- `Future.get()` lets `main` wait for results, avoiding `Thread.sleep()` to guess when workers have finished.

Create **`ConditionLab.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionLab {
    static final class OneSlot {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();
        private String item;

        void put(String value) throws InterruptedException {
            if (value == null) throw new IllegalArgumentException("null not allowed");
            lock.lockInterruptibly();
            try {
                while (item != null) notFull.await();
                item = value;
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        String take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (item == null) notEmpty.await();
                String result = item;
                item = null;
                notFull.signal();
                return result;
            } finally {
                lock.unlock();
            }
        }
    }

    static final class Gate {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition opened = lock.newCondition();
        private boolean isOpen;

        void awaitOpen() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (!isOpen) opened.await();
            } finally {
                lock.unlock();
            }
        }

        void open() {
            lock.lock();
            try {
                isOpen = true;
                opened.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            OneSlot slot = new OneSlot();
            Future<String> received =
                pool.submit(() -> slot.take() + "," + slot.take());
            slot.put("alpha");
            slot.put("beta");
            System.out.println("received=" + received.get());

            Gate gate = new Gate();
            Future<Boolean> first = pool.submit(() -> {
                gate.awaitOpen();
                return true;
            });
            Future<Boolean> second = pool.submit(() -> {
                gate.awaitOpen();
                return true;
            });
            gate.open();
            System.out.println("gate=" + first.get() + "," + second.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run in the directory containing the source file:

```bash
javac --release 17 ConditionLab.java
java ConditionLab
```

**Verified stdout:**

```text
received=alpha,beta
gate=true,true
```

### Explaining the correctness of the example

1. `OneSlot.item` is read and written only while holding `OneSlot.lock`. `null` represents an empty slot; null input is rejected so it cannot be confused with the “empty” state.
2. `put("alpha")` and `put("beta")` are called sequentially by `main`. If the slot is still full when the second `put` starts, `main` waits on `notFull.await()`, releasing the lock so the consumer can take `alpha` and signal. The received order is always `alpha,beta`.
3. The consumer receives via two `take()` calls. If it runs before the producer, it waits on `notEmpty`. If the producer runs first, the consumer checks the predicate and takes immediately. It does not depend on a signal having happened before the waiter arrived.
4. `received.get()` ensures the consumer task has completed and returned the string; thus the first line is always `received=alpha,beta` on normal completion.
5. The two tasks in the Gate section may enter `awaitOpen()` before or after `gate.open()`. If they wait beforehand, `signalAll()` notifies both. If they enter afterward, they observe `isOpen == true` and **do not need to wait**.
6. `Gate.opened.signalAll()` does not make both waiters run concurrently inside the critical section; each waiter must reacquire the lock before returning from `await()`. Each task then returns `true`.
7. `first.get()` and `second.get()` establish a completion boundary before `main` prints the second line, so the output is determined by the predicate rather than CPU scheduling.

**Demo scope:** this is an educational example and does not implement close/shutdown semantics for the buffer, work timeouts, telemetry, or error propagation per an application contract. The pool has two workers so both Gate waiters can run concurrently; if the gate opens before both actually call `await`, the program is still correct, though such a run **does not prove** both were in the condition queue when `signalAll()` was called. To test the “waiting” state more precisely, proper orchestration and instrumentation are required; Gate's correctness must rely on the predicate/lock protocol, not scheduler assumptions.

`Future.get()` can throw `ExecutionException` if a task fails or `InterruptedException` if the caller is interrupted; `main` in the demo declares `throws Exception` to keep the focus on `Condition`. In real applications, handle errors, task cancellation, deadlines, and clean shutdown.

## 10. Signal and signalAll do not replace state

A **lost signal** often happens when code assumes calling `signal` is enough without a predicate:

```java
// This is an INCORRECT illustration, not a complete waiting protocol.
lock.lock();
try {
    condition.signal(); // no waiter -> signal is not accumulated
} finally {
    lock.unlock();
}

// Much later: another thread calls condition.await()
// there is no predicate already true to let it skip waiting.
```

This snippet illustrates the bug; `lock`/`condition` are declared elsewhere and `await` must be called while holding the associated lock. Fix it by maintaining **persistent condition state**:

```java
// Fields inside a class:
private boolean ready;
private final ReentrantLock lock = new ReentrantLock();
private final Condition changed = lock.newCondition();

void publishReady() {
    lock.lock();
    try {
        ready = true;
        changed.signalAll();
    } finally {
        lock.unlock();
    }
}

void waitUntilReady() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        while (!ready) {
            changed.await();
        }
    } finally {
        lock.unlock();
    }
}
```

These are **illustrative members of a class** that imports `Condition`/`ReentrantLock`. If the signal happens first, `ready` remains true so a late waiter proceeds. If the waiter arrives first, it waits and then re-checks `ready` after being notified. This is a logical protocol and does not require signals to exist as permits.

**If you need a stored permit that a later-arriving thread can consume**, a primitive like `Semaphore` has a different model. `Condition` is not a semaphore or an event counter; choose the primitive that matches the required semantics.

## 11. Interruptible waiting: how to handle work cancellation

`Condition.await()` is an **interruptible** method and declares `throws InterruptedException`. With `ReentrantLock.newCondition()`, when an interrupt occurs while waiting, the implementation can exit the wait with `InterruptedException` and reacquire the lock before throwing the exception. Per the Javadoc, when this exception is thrown due to an interrupt, **the interrupt status is cleared**; the caller must decide whether to propagate it, cancel work, or restore the flag.

Common pattern if the method lets the caller handle it:

```java
void awaitReady() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        while (!ready) {
            readyCondition.await();
        }
        useReadyState();
    } finally {
        lock.unlock();
    }
}
```

This is an **illustrative method** requiring fields `lock`, `ready`, `readyCondition` and method `useReadyState()` declared in its enclosing class.

- `lock.lockInterruptibly()` allows the **lock-acquisition phase** to be canceled by interruption as well.
- `await()` allows the **predicate-waiting phase** to be interrupted.
- `finally` ensures release once the lock has been acquired; placing `lockInterruptibly()` **before** `try` avoids calling `unlock()` when acquisition fails and the thread does not own the lock.
- If the caller receives `InterruptedException`, it can propagate it up the stack or stop the task according to the application's policy.

If code at the end of a pipeline must catch it and cannot rethrow:

```java
try {
    awaitReady();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // restore flag
    return;                              // void method, stop processing
}
```

This is an **illustrative snippet inside a void method**, where `awaitReady()` is a method that can throw the exception. Do not “swallow” `InterruptedException` and continue an infinite wait loop if the application expects cancellation.

### `awaitUninterruptibly()`

`Condition.awaitUninterruptibly()` waits without throwing `InterruptedException`; an interrupt may be recorded and the interrupt status is preserved/restored upon return according to the API semantics. It **can still wake up spuriously**, so always use a predicate-checking loop. Do not choose it by default for applications needing graceful shutdown/cancellation, because it makes it harder to ask a waiter to stop promptly.

### Why can't an interrupt be treated as a business signal?

Interruption is a thread cancellation/interruption coordination mechanism; a signal is a notification that a predicate **may** have changed. A waiter can be interrupted while waiting or while reacquiring; the `Condition` contract allows implementations to prioritize reacting to an interrupt in certain races with a signal (while still handling signal transfer under appropriate constraints). Do not assume both events are always processed in one source-mandated order. Build APIs that are explicit about cancellation, state, and retries.

## 12. Timed await variants and deadlines

`Condition` provides several overloads for timing requirements:

| API | Primary behavior | Return value |
|---|---|---|
| `await()` | Interruptible wait, no deadline | `void` |
| `awaitUninterruptibly()` | Wait without throwing InterruptedException | `void` |
| `await(long time, TimeUnit unit)` | Wait at most a relative duration | `boolean`: typically `false` if time elapsed before signal |
| `awaitNanos(long nanosTimeout)` | Wait in nanoseconds, for retry loops | `long`: estimate of remaining nanoseconds; ≤ 0 means time has elapsed |
| `awaitUntil(Date deadline)` | Wait until an absolute point in time | `boolean`: false if the deadline passed before notification |

In **every** timed await, the predicate must still be checked in a `while` loop. Do not infer that the predicate is true just because `await(time, unit)` returned true: the return value can be affected by a signal or spurious wakeup, and another thread may change the predicate while the waiter is reacquiring the lock.

### Timeout pattern using `awaitNanos()`

```java
import java.util.concurrent.TimeUnit;

// Method of a class containing lock, notEmpty, queue:
boolean awaitNotEmpty(long timeout, TimeUnit unit)
        throws InterruptedException {
    long remaining = unit.toNanos(timeout);
    lock.lockInterruptibly();
    try {
        while (queue.isEmpty()) {
            if (remaining <= 0L) return false;
            remaining = notEmpty.awaitNanos(remaining);
        }
        return true; // queue is non-empty while still holding the lock
    } finally {
        lock.unlock();
    }
}
```

This is an **illustrative method inside a class**; `lock` and `notEmpty` are created from the same `ReentrantLock`, and `queue` is a collection protected by that lock. Returning `true` here is only a snapshot of the predicate **before releasing the lock**; another caller acquiring the lock later may find the queue empty again, so if you want to take an item, you should normally **perform the removal inside the same critical section** instead of returning a boolean and calling another method.

Important notes:

- Use the `remaining` value returned by `awaitNanos()` to avoid **resetting the full timeout** after each spurious wakeup.
- If you use `await(time, unit)` inside a loop and pass the full timeout every time, the total wait time can stretch past the desired deadline.
- With absolute deadlines based on `Date`/wall-clock time, be mindful of clock adjustments; relative deadlines measuring elapsed intervals generally align with monotonic `System.nanoTime()`.
- A timeout is a **limit on the wait request**, not a guarantee that the scheduler will run the thread at that exact instant.
- In a timed version of a bounded buffer, you must return “could not put/could not take” per contract on timeout, and **must not** leave the state half-modified.

## 13. Comparing `Condition` and `Object.wait/notify`

The two mechanisms are conceptually similar but have **different attached locks and APIs**:

| Aspect | `Object.wait()/notify()/notifyAll()` | `Condition.await()/signal()/signalAll()` |
|---|---|---|
| Attached to | Intrinsic monitor of an object | A `Lock`, typically `ReentrantLock` |
| Ownership required before wait/signal | Must be inside `synchronized(object)` on that object | With `ReentrantLock.newCondition()`, must hold the associated lock |
| Wait | `object.wait()` | `condition.await()` |
| Notify one waiter | `object.notify()` | `condition.signal()` |
| Notify all waiters | `object.notifyAll()` | `condition.signalAll()` |
| Grouping waiters | One wait set per object monitor | Can create **multiple separate Conditions** from one Lock |
| While waiting | Temporarily releases that object's monitor | Temporarily releases the lock attached to the Condition |
| Waking up | Must reacquire the monitor before `wait` returns | Must reacquire the associated lock before `await` returns |
| Interrupt/timeout | Corresponding overloads | Multiple overloads, `awaitNanos` and `awaitUninterruptibly` |
| Typical state | `WAITING (on object monitor)` | `WAITING (parking)` depending on JVM/implementation |

**Do not mix them up:** `condition.await()` cannot be replaced with `monitor.wait()` just because you see the variable name `lock`. A `ReentrantLock` object is not an owned intrinsic monitor when you call `lock.lock()`; calling `lock.wait()` without synchronizing on the *intrinsic monitor* of the `lock` object is still wrong.

`Condition` is an interface, and other implementations may define additional semantics; the table describes the standard `ReentrantLock.newCondition()` case. When you need specific fairness/ordering or exact interrupt semantics, read the implementation's Javadoc.

## 14. Common mistakes to avoid

### 14.1. Calling await/signal without holding the associated lock

```java
ReentrantLock lock = new ReentrantLock();
Condition changed = lock.newCondition();

// Wrong for a Condition created by ReentrantLock:
changed.signal();
changed.await();
```

This snippet **illustrates the error**, not a standalone program; `await()` also requires handling or declaring `InterruptedException`. With `ReentrantLock`, both calls without owning the lock throw `IllegalMonitorStateException`. Correct pattern:

```java
lock.lock();
try {
    changed.signalAll();
} finally {
    lock.unlock();
}
```

The snippet above assumes `lock`/`changed` already exist in the same method/class.

### 14.2. Calling await inside an `if`

```java
if (queue.isEmpty()) {
    notEmpty.await();
}
T item = queue.removeFirst(); // may be empty after spurious wakeup/reacquire
```

This is an **erroneous snippet** inside a critical section of a generic class with `queue`, `notEmpty`, `T`. Fix it with `while (queue.isEmpty()) notEmpty.await();`; with multiple consumers, a `signal` or `signalAll` does not guarantee the running thread still sees an item.

### 14.3. Signaling before updating the predicate

```java
// Illustrates a misleading order if the condition must go from false to true:
lock.lock();
try {
    condition.signal();
    // changing state afterward while still holding the lock...
    ready = true;
} finally {
    lock.unlock();
}
```

This is an **illustrative snippet**. Under the same lock, the waiter cannot reacquire until `unlock`, so this order is **not necessarily wrong for correctness** if the final predicate is true and there are no exceptions or abnormal exit branches. However, the clearer and less error-prone style is **update the predicate first, signal afterward**, because it ties the notification to the completed change and scales better as code grows. The real bug is **failing to update the predicate**, updating it outside the lock, or having control flow where a signal occurs without a valid state.

### 14.4. Overusing `signalAll()`

A producer adds a single item yet wakes thousands of consumers: all consumers contend for the lock, and most see an empty queue and go back to `await()`. You can use `signal()` if you can prove notifying one waiter is sufficient for progress. Conversely, using `signal()` for a shutdown where many waiters must all exit is insufficient; in that case `signalAll()` and checking a shutdown flag are required.

### 14.5. Multiple Conditions but waiting/signaling on the wrong queue

If consumers wait on `notEmpty` while producers only signal `notFull`, consumers will never wake up. Name each Condition after **the predicate waiters are waiting for**, not just the method calling `signal`; write tests for empty/full buffers, multiple producers/consumers, interruption, and shutdown.

### 14.6. Forgetting `finally` or unlocking too early

`ReentrantLock` does not automatically release when a method throws an exception the way a `synchronized` block does; you must write `lock.lock(); try { ... } finally { lock.unlock(); }`. However, you must also not call `unlock()` if `lockInterruptibly()` or `tryLock` failed to acquire the lock. Only wrap the region where the lock is actually owned in `try/finally`.

### 14.7. Holding another lock while calling await

`conditionOfA.await()` releases A, not B. If another thread needs B to signal the condition on A, both sides can deadlock. Avoid nested locks if unnecessary; when needed, establish a clear lock acquisition and release order, and do not wait on an event while holding resources that prevent the event from occurring.

### 14.8. Using `Thread.sleep()` to wait for a condition

Sleeping does not release held locks, produces no signal, and does not guarantee the predicate will become true within the chosen duration. Use `await`, a queue, a latch, or a future matching your business semantics.

### 14.9. Equating a signal with waiter completion

`signalAll()` only gives waiters a chance to make progress. If the caller needs all waiters to **finish processing** before continuing, use `Future.get()`, `CountDownLatch`, `Phaser`, or a dedicated completion protocol—never infer completion from a single signal.

## 15. Liveness, fairness, and performance

**Mutual exclusion** guarantees only one thread holds the `ReentrantLock` at a time. It does not guarantee that a specific thread will acquire the lock after a signal within a fixed time.

- With a **non-fair ReentrantLock** (the default), a newly arriving thread can acquire the lock ahead of a signaled waiter. Choosing a fair lock can help prioritize long-waiting threads under contention, though it does not guarantee absolute scheduler fairness; untimed `tryLock()` also has barging semantics to watch out for.
- With `ReentrantLock.ConditionObject`, a signal moves a waiter from the condition queue to the lock queue, but **the waiter cannot run** until it successfully reacquires the lock.
- `signalAll()` can cause a thundering herd, increasing lock contention.
- If the predicate can never become true, `await()` can wait forever even without any data race. Design shutdown, timeouts, and error propagation.
- If the thread holding the lock performs slow I/O or heavy CPU work after `signal()`, the waiter must wait longer for the lock. Keep critical sections small enough to protect invariants, without splitting steps that must be atomic.
- With a bounded queue, a producer faster than consumers creates backpressure and increases wait time. Distinguish intentional predicate waiting from starvation caused by the scheduler or a lock bottleneck.

Not every problem requires writing a `Condition` yourself. For producer-consumer pipelines, `BlockingQueue` provides a standard waiting protocol, capacity management, and memory consistency out of the box. For a “one-shot gate”, `CountDownLatch` may be a better fit. For a permit count, `Semaphore` is a better fit. `Condition` is especially useful when you **already have a shared invariant under a Lock** and need predicate-dependent wait groups.

## 16. Diagnosing with thread dumps and JFR

When a program hangs or has high latency, look for:

1. Which thread **holds the ReentrantLock**, and which threads are waiting on which Condition?
2. Which predicate is still false? Who is responsible for making it true?
3. Does the thread changing the predicate **signal the right Condition**?
4. Is a waiter holding another lock, preventing the producer from making progress?
5. Is there a shutdown/cancellation that forgot to call `signalAll` to wake long-waiting threads?
6. Is a timeout being reset after every wakeup?
7. Did an exception cause a thread to miss `unlock` or miss a required signal?

You can capture thread dumps with:

```bash
jcmd <PID> Thread.print -l
```

Replace `<PID>` with the running Java process PID. For `Condition.await()` on a `ReentrantLock`, the stack may go through `AbstractQueuedSynchronizer.ConditionObject.await` and `LockSupport.park`. This is typically `WAITING (parking)`, not `WAITING (on object monitor)` from `Object.wait()`.

JFR (when supported by the JVM) can provide `jdk.ThreadPark` events and timing/stack details for waiting threads:

```bash
jcmd <PID> JFR.start name=condition-profile settings=profile duration=60s filename=conditions.jfr
jfr summary conditions.jfr
jfr print --events jdk.ThreadPark conditions.jfr
```

The absence of events does not prove there is no waiting: a recording that is too short, event thresholds, profiling settings, or an unexercised workload can leave events unrecorded. Thread dumps and JFR are observational evidence and **do not replace verifying the predicate and lock protocol**.

## 17. Code review checklist for Condition usage

When reviewing an implementation that uses `Condition`, explicitly answer:

1. **How is the Lock shared?** Do all readers and writers of the state use the exact same `ReentrantLock`?
2. **What is the predicate?** Is it expressed as a logical expression checked under the lock?
3. **Do waiters always use `while`?** Is it re-checked after signals, spurious wakeups, and contention?
4. **Is `await` called while holding the lock?** Is the associated lock temporarily released while waiting?
5. **Is state updated before signaling?** Are all reads/writes of the predicate inside the same critical section?
6. **`signal` or `signalAll`?** Does waking one vs. multiple waiters match the state change and shutdown requirements?
7. **Is `unlock` always in `finally`?** Is there any exception/cancellation path that misses `unlock` or unlocks without acquiring?
8. **Interrupt policy?** Does the API propagate `InterruptedException`, restore the flag, or support cancellation properly?
9. **Do timeouts use a proper deadline?** Can spurious wakeups extend the total wait time?
10. **Are other locks held?** Could waiting on a condition block the thread responsible for making the predicate true?
11. **Does the system have a separate completion check?** Signals must not replace `Future.get()` or a latch when task completion confirmation is needed.
12. **Is a higher-level primitive more suitable?** Do not reimplement `BlockingQueue`/`CountDownLatch` if no custom predicate is needed.
13. **Tested for races/close/interrupt?** Do not test only a single happy-path schedule; stress-test with multiple producers, consumers, timeouts, and shutdown.

## 18. Self-check questions and answers

**Q1.** Thread A calls `condition.await()` while holding the associated `ReentrantLock`. Does it still hold the lock while waiting?  
**Answer:** No. For a `ReentrantLock` Condition, `await` releases the corresponding lock while waiting and reacquires it before returning or completing via interruption.

**Q2.** Thread B calls `signal()` and then keeps holding the lock for another 5 seconds. Can A immediately enter the critical section right after the signal?  
**Answer:** No. A must reacquire the lock. As long as B has not unlocked, A cannot continue executing the protected code.

**Q3.** A producer signals before a consumer arrives; can the notification be lost?  
**Answer:** Signals are not stored as permits, so a standalone notification may have no waiter to receive it. A correct protocol relies on a **stored predicate**: a consumer arriving later checks the state, sees it is true, and does not call `await`.

**Q4.** Why is `if (!ready) condition.await()` unsafe?  
**Answer:** `await` can return after a spurious wakeup or the predicate can change back before reacquire; use `while (!ready)`.

**Q5.** When adding one item to an empty buffer, should you call `signal()` or `signalAll()`?  
**Answer:** If consumers all wait on the same “has item” predicate and only one item is added, `signal()` is usually enough; multiple predicates sharing a Condition, broad state changes, or shutdown may require `signalAll`. Evaluate the specific invariant and progress guarantee.

**Q6.** Does `signalAll()` make all waiters run concurrently inside the locked region?  
**Answer:** No. They compete to reacquire the lock; only one thread owns the lock at a time.

**Q7.** Can `notFull.await()` be replaced by `notEmpty.await()` in a producer?  
**Answer:** No, if the two Conditions correspond to different waiter groups. Producers must wait on the “has space” condition, whereas consumers wait on “has item”.

**Q8.** When `InterruptedException` is thrown by `await()`, can you ignore it and keep waiting indefinitely?  
**Answer:** You should not if the thread needs to support cancellation. Propagate the exception, cancel the task, or restore the interrupt flag if catching at an appropriate boundary.

**Q9.** In a timeout loop, why must you update the remaining time via `awaitNanos()`?  
**Answer:** Because the thread may wake up multiple times while the predicate is still false. If you reset the full timeout each time, total wait time can exceed the requested deadline.

**Q10.** A thread holds lock B and calls `conditionOfA.await()`; does `await` automatically release B?  
**Answer:** No. It only releases the associated lock A; B remains held, which can stall the producer and cause a deadlock.

**Q11.** Does `Condition` store the value of `ready` itself?  
**Answer:** No. `Condition` only manages waiting/notification; the boolean `ready` or other predicate must be managed under the lock.

**Q12.** If everyone only needs to wait for a single “completed once” event, is `Condition` required?  
**Answer:** No. `CountDownLatch` usually expresses this more clearly. `Condition` is useful when you need to wait on custom predicates under the same lock.

## 19. References

- [Java SE 17 — Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): `await()`, `awaitNanos()`, `awaitUntil()`, `signal()`, `signalAll()`, spurious wakeups, and interruption.
- [Java SE 17 — ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): `newCondition()`, associated lock, fairness, and ownership.
- [Java SE 17 — Lock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): `lock()`, `lockInterruptibly()`, `unlock()`, and memory synchronization.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): producer-consumer waiting, bounded queue APIs, and memory consistency.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): one-shot gate and completion waiting rules.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): waiting for task results and memory consistency.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model and happens-before.

**Final reminder:** **the predicate decides whether to proceed; the lock protects the predicate; `await()` releases and reacquires the lock; `signal()`/`signalAll()` only notify of an opportunity to re-check.** Write `while`, hold the right associated lock, update state before signaling, use `finally` to unlock, and design cancellation/timeouts explicitly. When these are proven, the execution schedule can be nondeterministic and the program will still be correct.