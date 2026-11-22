# Spurious Wakeups and Re-checking Invariants in Java

## 1. The Problem: Being Woken Up Does Not Mean the Condition Is True

When coordinating multiple threads, a thread often has to wait for a **business condition**: a queue has an element, a buffer has free space, a task has completed, or a state has transitioned to `READY`. Java provides `Object.wait()`/`notify()`/`notifyAll()` and `Condition.await()`/`signal()`/`signalAll()` for waiting and signaling between threads.

A **spurious wakeup** is a case where a wait call can **return even without a notification, interrupt, or timeout sufficient to explain the return**, as permitted by the Java specification. A correct program must not assume that every time `wait()` or `await()` returns, the desired condition is satisfied.

More importantly, **even without spurious wakeups**, the condition can still be false when the thread is woken up:

- Another thread calls `notifyAll()`/`signalAll()`, but only some waiters can consume the resource.
- The signal is related to a different kind of state change, not the condition this thread is waiting for.
- The thread has been signaled but must **reacquire the lock**; another thread may change the state before it reacquires.
- The waiter is woken up after an event, but the predicate is changed back before it continues.
- There is a timeout or interrupt; each wakeup reason must be handled according to its corresponding contract.

**Fundamental rule: every conditional wait must be inside a `while` loop that re-checks the predicate under the same lock that protects the state.**

~~~java
// Correct pattern, not a standalone program.
// The thread must currently hold the monitor of lock.
synchronized (lock) {
    while (!conditionSatisfied()) {
        lock.wait();
    }
    // Here the predicate is true and we still hold the right monitor.
    consumeOrUpdateState();
}
~~~

For `Condition`:

~~~java
// Correct pattern, not a standalone program.
// state is protected by the same ReentrantLock.
lock.lock();
try {
    while (!conditionSatisfied()) {
        condition.await();
    }
    consumeOrUpdateState();
} finally {
    lock.unlock();
}
~~~

Do not replace `while` with `if` just because "we are sure the signaler called notify". **A notification signal is a hint that the state may have changed; the predicate under the lock is the source of truth.**

This article is within the scope of **general Java thread coordination**, using built-in JDK APIs. Framework-specific mechanisms are outside the scope of this article.

## 2. What Are Invariants and Condition Predicates?

### 2.1. Distinguishing Invariant, Predicate, and Signal

An **invariant** is a property that must always hold true at points protected by the synchronization protocol. For example, a buffer with `capacity` elements must maintain:

~~~text
0 <= size <= capacity
~~~

To wait to read, a consumer uses the **predicate** `!queue.isEmpty()`. To wait to write, a producer uses the predicate `queue.size() < capacity`. These predicates are derived from the state protected by the lock, not from the number of times `signal()` has occurred.

A **signal** only allows one or more waiters to be woken up to re-check the condition. It does not by itself "grant an element", reserve a slot in the queue, or guarantee that the predicate remains true when the waiter runs.

| Concept | Question | Buffer Example |
| --- | --- | --- |
| Invariant | What must the system always preserve? | `0 <= size <= capacity` |
| Predicate | What specific condition must the waiter check? | `size > 0` to take |
| State transition | What event can cause the predicate to change from false to true? | Producer adds an element |
| Signal | Who needs to be woken up to re-check? | `notEmpty.signal()` |
| Lock | What protects checking and modifying the state? | A shared monitor/`ReentrantLock` |

Using the **same lock** for reading the predicate, modifying the state, and entering wait prevents the situation of checking the state outside the lock and missing a notification while transitioning into wait.

### 2.2. Why Must You Use `while`?

Suppose the queue is initially empty, and two consumers C1 and C2 are both waiting. The producer adds **one** element and calls `signalAll()`:

~~~text
Initially: queue = []
C1: await() because queue is empty
C2: await() because queue is empty

Producer: put(X), signalAll(), unlock()
C1: reacquire, sees X, takes X, unlock()
C2: reacquire, queue is empty again
~~~

C2 **was validly signaled**, but when it reacquires, the predicate `!queue.isEmpty()` is **false**. If it only used `if (empty) await()` and then proceeded to `remove()`, C2 could read from an empty queue and fail. With `while`, C2 goes back to waiting for another element.

This is an example of **the predicate no longer being true after a signal**, not necessarily a spurious wakeup. They are two different reasons that both lead to the requirement of using `while`.

## 3. `Object.wait()`: Mechanism and Usage Conditions

### 3.1. `wait` Belongs to the Object Monitor

`Object.wait()`, `notify()`, and `notifyAll()` operate on the **monitor** of that exact object. The calling thread must hold the corresponding monitor; the clearest way is to use `synchronized(lock)`.

~~~java
// Pattern for using the monitor properly; not a standalone program.
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
~~~

When `lock.wait()` is called validly:

1. The thread **temporarily releases the monitor of `lock` itself** and moves into the wait set associated with that monitor.
2. The thread may be woken up due to notify/notifyAll, interrupt, or spurious wakeup; with timed variants, there is also timeout.
3. Before `wait()` returns normally or throws `InterruptedException`, the thread must **reacquire the monitor of `lock`**.
4. The thread resumes inside the `synchronized` block and can check the predicate while holding the monitor.

`wait()` does not release **any other locks** that the thread owns. If a thread also holds monitor B and calls `lockA.wait()`, it may still hold B while waiting, causing a deadlock when the thread that wants to change the predicate also needs B.

Calling `wait()` or `notify()`/`notifyAll()` **without holding the monitor** of the receiver throws `IllegalMonitorStateException`. Do not use `Thread.sleep(...)` as a replacement for `wait()`: sleep **does not release the lock**, does not wait for a predicate, and does not create coordination notifications.

### 3.2. `notify`, `notifyAll`, and the Number of Waiters

- `notify()` selects **one** thread from the wait set on the monitor to wake up, if any. There is no guarantee you will pick the right kind of waiter for the current predicate.
- `notifyAll()` wakes up **all** waiters in the corresponding set. They still have to compete to reacquire the monitor and check the predicate.
- Simply calling `notify`/`notifyAll` while holding the monitor does not mean the waiter runs immediately: the thread holding the monitor still has to release it, and the scheduler decides when the waiter resumes.
- If there are **no waiters**, notify does not save a "credit" to be received later. This is why you need to keep state like `ready` or `queue.size()` and always check before entering wait.

In simple examples, `notifyAll()` easily avoids picking the wrong kind of waiter, but waking up many threads can cause a **thundering herd** (many waiters waking up only to find the predicate is still false). When there are multiple types of predicates, `Condition` with separate condition queues is sometimes clearer.

### 3.3. Example 1 — Safe Gate with `while` (Java 17+)

Create the file `ObjectWaitGateDemo.java`:

~~~java
public class ObjectWaitGateDemo {
    static final class Gate {
        private boolean open;

        synchronized void awaitOpen()
                throws InterruptedException {
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

    public static void main(String[] args)
            throws InterruptedException {
        Gate gate = new Gate();

        Thread worker = new Thread(() -> {
            try {
                gate.awaitOpen();
                System.out.println("worker passed");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "gate-waiter");

        worker.start();
        gate.open();
        worker.join();

        System.out.println("open = " + gate.isOpen());
    }
}
~~~

Compile and run:

~~~bash
javac ObjectWaitGateDemo.java
java ObjectWaitGateDemo
~~~

Stdout when there is no unexpected interrupt:

~~~text
worker passed
open = true
~~~

Important race scenario: if `gate.open()` happens **before** the worker enters `awaitOpen()`, the worker sees `open == true` as soon as it acquires the monitor and does not need to wait. If the worker enters wait first, `open()` changes the state and calls `notifyAll` under the same monitor, so the worker will re-check and proceed.

With a spurious wakeup while `open` is still false, `while` forces the worker back into `wait()`; there is no erroneous "worker passed" line. The result does not depend on whether the scheduler runs the worker first or the main thread first.

This snippet uses `synchronized` on all read/write paths of `open`, so it also provides visibility/happens-before guarantees through the monitor. `join()` makes main wait for the worker to finish before printing the last line.

## 4. Distinguishing Spurious Wakeups from Irrelevant Notifications

### 4.1. A Spurious Wakeup Is Not a "Wrong Notify"

A spurious wakeup is the ability for wait/await to return **without the required notification/timeout/interrupt cause**. It is permitted by the specification. You should not write code or tests that rely on expecting the JVM to **definitely** produce a spurious wakeup in a given run.

On the other hand, a thread can be woken by `notifyAll()` **completely validly**, yet its predicate is still false. This case can be reproduced in a controlled way in Java to prove that `if` is insufficient, without **pretending that an actual spurious wakeup was generated**.

### 4.2. Example 2 — `if` Bug with a Notification That Does Not Change the Predicate (Java 17+)

The following example is **intentionally wrong**, used to understand why it must be fixed with `while`. A thread is notified, but the `ready` condition is still false, so it must not continue its work.

Create the file `WrongIfWaitDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public class WrongIfWaitDemo {
    static final class Gate {
        private boolean ready;
        private final CountDownLatch aboutToWait =
            new CountDownLatch(1);

        synchronized boolean awaitOnce()
                throws InterruptedException {
            if (!ready) { // WRONG: must be while (!ready).
                aboutToWait.countDown();
                wait();
            }
            return ready;
        }

        void waitUntilEntered() throws InterruptedException {
            aboutToWait.await();
        }

        synchronized void unrelatedNotify() {
            notifyAll(); // Does not change ready.
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Gate gate = new Gate();

        Thread worker = new Thread(() -> {
            try {
                boolean result = gate.awaitOnce();
                System.out.println("predicate = " + result);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "incorrect-waiter");

        worker.start();
        gate.waitUntilEntered();
        gate.unrelatedNotify();
        worker.join();
    }
}
~~~

Compile and run:

~~~bash
javac WrongIfWaitDemo.java
java WrongIfWaitDemo
~~~

Stdout when the worker is not interrupted:

~~~text
predicate = false
~~~

Why is the result deterministic?

1. `aboutToWait.countDown()` happens **inside Gate's monitor**, right before `wait()`.
2. The main thread only calls `unrelatedNotify()` after the latch opens; `unrelatedNotify()` must also acquire **Gate's monitor**.
3. If the worker has not yet called `wait()`, main cannot acquire the monitor to notify. Therefore, when main enters `unrelatedNotify()`, the worker has either already released the monitor to wait, or has woken up on its own and proceeded.
4. `unrelatedNotify()` wakes up the waiter if it is still waiting, but **does not set `ready = true`**.
5. Because the code uses `if`, the worker does not re-check the predicate after `wait()` returns and prints `false`.

This example does not depend on spurious wakeups: a real, albeit irrelevant, notification exposed the bug. If `if (!ready)` is replaced with `while (!ready)`, the worker will **keep waiting**, because no code sets `ready` to true. When fixing this into a real application, a valid state transition and notify must be added so the worker can complete, rather than just changing `if` and letting the test hang.

## 5. `Condition.await()`: Same Principle, More Flexible API

`java.util.concurrent.locks.Condition` is typically created from `ReentrantLock.newCondition()`. One lock can create **multiple condition queues**, such as `notEmpty` and `notFull`, helping separate types of waiters.

Correct skeleton:

~~~java
// Condition pattern, not a standalone program.
lock.lock();
try {
    while (!predicate()) {
        condition.await();
    }
    processSharedState();
} finally {
    lock.unlock();
}
~~~

When `await()` is called while the thread holds the appropriate lock:

- It **releases the lock associated** with the condition while waiting; with `ReentrantLock`, the hold count state is managed during release and reacquisition.
- It can return due to `signal()`/`signalAll()`, spurious wakeup, or interruption according to the overload's contract.
- Before returning normally, the waiter **reacquires the lock**, then resumes inside the same state-protected region.
- `signal()` does not immediately transfer lock ownership to the waiter; the signaling thread still holds the lock until it unlocks.
- With a `ConditionObject` created by `ReentrantLock`, calling `await()` or `signal()` without holding the appropriate lock is invalid and may throw `IllegalMonitorStateException`.

### 5.1. A Condition Is Not a Boolean Variable

A `Condition` does not itself store the "ready" predicate. It contains the queuing and wakeup mechanism. The actual state needs to be kept in data fields protected by the lock: `count`, `queue`, `closed`, `ready`, etc.

It is wrong to reason: "`signal()` was called, so a later waiter will receive that signal." A signal does not accumulate credit for a waiter that has not started waiting yet. If you need to store events or permits, use explicit state or primitives with accumulating semantics such as `Semaphore` or `BlockingQueue`, when appropriate.

### 5.2. `Condition` Can Have Spurious Wakeups

According to the `Condition` API, implementations allow spurious wakeups and programmers **must always assume they can occur**. A particular implementation might rarely or never produce spurious wakeups in practice; that does not change the coding contract.

The `while` loop also handles another thread acquiring the lock and changing the predicate before the waiter. With or without spurious wakeups, the condition must still be checked **inside the locked region**.

## 6. Example 3 — Bounded Buffer with Two Predicates (Java 17+)

A bounded-capacity buffer needs two conditions:

- The consumer waits for `!queue.isEmpty()` before taking an element.
- The producer waits for `queue.size() < capacity` before adding an element.

Both are protected by **one `ReentrantLock`**, but have **two separate `Condition`s** to signal the right group of waiters.

Create the file `BoundedBufferConditionDemo.java`:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class BoundedBufferConditionDemo {
    static final class Buffer {
        private final Deque<Integer> queue = new ArrayDeque<>();
        private final int capacity;
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();

        Buffer(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException(
                    "Capacity must be positive"
                );
            }
            this.capacity = capacity;
        }

        void put(int value) throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (queue.size() == capacity) {
                    notFull.await();
                }
                queue.addLast(value);
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        int take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (queue.isEmpty()) {
                    notEmpty.await();
                }
                int result = queue.removeFirst();
                notFull.signal();
                return result;
            } finally {
                lock.unlock();
            }
        }

        int size() {
            lock.lock();
            try {
                return queue.size();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Buffer buffer = new Buffer(1);

        Thread producer = new Thread(() -> {
            try {
                buffer.put(10);
                buffer.put(20);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        producer.start();

        System.out.println("taken = " + buffer.take());
        System.out.println("taken = " + buffer.take());
        producer.join();
        System.out.println("remaining = " + buffer.size());
    }
}
~~~

Compile and run:

~~~bash
javac BoundedBufferConditionDemo.java
java BoundedBufferConditionDemo
~~~

Stdout when there is no unexpected interrupt:

~~~text
taken = 10
taken = 20
remaining = 0
~~~

**Why is the result deterministic?**

- The producer only writes elements 10 then 20 in order within the same thread.
- The buffer uses a FIFO `ArrayDeque`, so the consumer will receive 10 before 20.
- Capacity is 1, so when the producer wants to write 20 while 10 is still present, it enters `while (queue.size() == capacity)` to wait.
- When the consumer takes 10, it calls `notFull.signal()`; the producer reacquires the lock, re-checks that there is space, and adds 20. The consumer may have to wait on `notEmpty` before or after, but this does not affect the data order.
- `size()` and all read/write paths of `queue` use the same lock; `join()` makes the final read run after the producer finishes.
- There are no print statements in the producer, so scheduler ordering between threads does not change main's stdout order.

**No absolute fairness scheduling guarantee:** `notEmpty.signal()` wakes up one waiter, but does not guarantee that waiter will get CPU time immediately or receive the element ahead of every other thread. With multiple producers/consumers, the `while` loops protect the invariant when multiple threads contend.

### 6.1. Why Not Use `if` in the Buffer?

If a consumer only checked `if (queue.isEmpty()) notEmpty.await();` and did not re-check, it could proceed to `removeFirst()` when the queue is already empty because another waiter consumed it. For a producer, `if (queue.size() == capacity) notFull.await()` could allow exceeding capacity after another producer adds an element before it reacquires. Use `while` on **both sides**.

### 6.2. Avoid Signaling Too Early or Outside the Lock

State needs to be modified while holding the lock, then the corresponding waiters signaled before releasing. With `ReentrantLock`'s `Condition`, calling `signal()` outside the lock is not only logically wrong, it can also throw `IllegalMonitorStateException`.

Note that a real-world application will also need to design **buffer closing**, handling cancelled producers/consumers, shutdown capability, and reporting errors to waiters waiting indefinitely. If you only need a standard queue, `ArrayBlockingQueue` or `LinkedBlockingQueue` can reduce hand-written condition management and coordination bugs.

## 7. Timeouts: Waking Up on Expiration Still Requires Checking the Invariant

An overload like `Condition.awaitNanos(long nanosTimeout)` returns an estimate of the remaining nanoseconds. Inside the loop, you must **update the remaining budget**, not wait for the full timeout again on every wakeup.

Correct pattern:

~~~java
// Java pattern, not a standalone program.
long remaining = unit.toNanos(timeout);
lock.lockInterruptibly();
try {
    while (!ready) {
        if (remaining <= 0L) {
            return false;
        }
        remaining = readyChanged.awaitNanos(remaining);
    }
    return true;
} finally {
    lock.unlock();
}
~~~

Reasons:

1. Each `awaitNanos` call can return due to signal/spurious wakeup, while `ready` is still false.
2. If you repeat the full original timeout after each wakeup, total wait time can exceed the initial budget many times over.
3. Return `false` when the budget is exhausted **and the predicate is still false**; if the predicate is already true, return `true` even if you just went through a long wait.
4. Acquiring the lock itself can also take time. If the deadline must be **measured from the start of the call**, you must include lock acquisition time in the calculation, for example using `tryLock(timeout, unit)` and a unified deadline.
5. A timeout does not automatically change business state or cancel an active producer. The caller must decide how to handle the timeout explicitly.

### Example 4 — Timeout and Predicate Already True (Java 17+)

Create the file `TimedConditionDemo.java`:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class TimedConditionDemo {
    static final class Gate {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition changed = lock.newCondition();
        private boolean ready;

        boolean awaitReady(long timeout, TimeUnit unit)
                throws InterruptedException {
            long remaining = unit.toNanos(timeout);
            lock.lockInterruptibly();
            try {
                while (!ready) {
                    if (remaining <= 0L) {
                        return false;
                    }
                    remaining = changed.awaitNanos(remaining);
                }
                return true;
            } finally {
                lock.unlock();
            }
        }

        void open() {
            lock.lock();
            try {
                ready = true;
                changed.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Gate gate = new Gate();

        System.out.println(
            "before = " + gate.awaitReady(0, TimeUnit.NANOSECONDS)
        );

        gate.open();

        System.out.println(
            "after = " + gate.awaitReady(0, TimeUnit.NANOSECONDS)
        );
    }
}
~~~

Compile and run:

~~~bash
javac TimedConditionDemo.java
java TimedConditionDemo
~~~

Exact stdout:

~~~text
before = false
after = true
~~~

The 0-nanosecond limit makes the first wait return `false` immediately because the predicate is not yet true. After `open()`, the predicate is true so the second call returns `true` immediately, **without waiting or relying on a signal emitted in the past**. The example illustrates true state checking; it is not meant to benchmark wait times of contending threads.

## 8. Interrupts: Do Not Lump All Wakeup Cases Together

### 8.1. `InterruptedException` Is a Separate Channel

Regular `Object.wait()` and `Condition.await()` can throw `InterruptedException` if the thread is interrupted. This is **not** a successful return from `await`. The caller must handle it according to its contract: propagate the exception, cancel the task, or return an explicitly designed failure status.

When a thread is interrupted during a wait that throws `InterruptedException`, the interrupt flag is typically cleared in the process of throwing. If you cannot propagate the exception, a common pattern is to **restore** the flag with `Thread.currentThread().interrupt()` before exiting the task.

~~~java
// Handling pattern in Runnable; not a standalone program.
try {
    gate.awaitOpen();
    doUsefulWork();
} catch (InterruptedException error) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Never catch `InterruptedException` and proceed as if the predicate were true. At the same time, do not assume that interrupting a waiting thread will automatically roll back all of its resources and side effects.

### 8.2. `awaitUninterruptibly` and the Wait Loop

`Condition.awaitUninterruptibly()` waits without throwing `InterruptedException` in the same way `await()` does. However, it **still allows spurious wakeups**, so it must also be placed inside `while (!predicate)`. It is not suitable if the application needs to honor cancellation/interrupts promptly; usually `await()` with proper interrupt handling is preferred.

### 8.3. `Object.wait` with Timeout

`Object.wait(long timeoutMillis)` and `wait(long millis, int nanos)` allow timed waiting. The `while` rule and deadline recalculation still apply. Be careful with the meaning of `wait(0)`: for the `wait(long)` overload, 0 means **wait indefinitely**, not return immediately. That differs from some 0-timeout APIs like the `awaitReady` example above.

## 9. Visibility and Happens-Before: Why Must the Lock Be Consistent?

The Java Memory Model specifies that **releasing the monitor** of an object and **subsequently acquiring that monitor** establishes the appropriate synchronizes-with/happens-before relationship. Similarly, `Lock` and `Condition` by their contract ensure that state updates are published when another thread reacquires the same lock.

The correct mechanism typically follows this sequence:

~~~text
Producer:
  lock
  update state (predicate may transition false -> true)
  notify/signal the right condition
  unlock

Consumer:
  lock
  while (!predicate) wait/await (temporarily unlocks)
  reacquire lock
  check predicate again
  read/update state
  unlock
~~~

A signal is not "magic that makes all variables freshly visible". **Accessing state under the same lock** is what provides the synchronization needed for read/write paths. If a producer modifies a normal variable **outside** the locking protocol while a consumer reads it under the lock, the guarantees may be insufficient.

### 9.1. Why Is Checking Outside the Lock Then Waiting a Bug?

~~~java
// Wrong if ready is updated in another thread without a shared protocol.
if (!ready) {
    synchronized (lock) {
        lock.wait();
    }
}
~~~

There is a gap between checking `ready` and actually waiting. Another thread can set `ready = true` and notify in that gap. Notifications are not saved for the future, so the waiter can enter wait **after the signal is already lost**, and then wait forever even though the state is ready.

The right approach is to **check the predicate and enter wait inside the same critical section**. `wait()` atomically releases the monitor with respect to the wait-set mechanism, allowing the state-changing thread to acquire the lock and signal in the right order.

### 9.2. Do Not Use `Thread.sleep` to "Wait for a Signal"

`Thread.sleep(...)` does not temporarily release a held monitor, does not by itself establish happens-before, and does not respond to `notify`/`signal`. If you hold a lock and sleep while waiting for another thread to make the predicate true, you may prevent that very thread from acquiring the lock needed to change the state.

`Thread.yield()` and `Thread.onSpinWait()` also cannot replace condition waiting or synchronization protocols; they only influence scheduling/optimization hints.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `if (!ready) wait()` | Wakes up but `ready` is still false; proceeds erroneously | `while (!ready) wait()` |
| `if (queue.isEmpty()) await()` | Multiple consumers contend; one consumer may read an empty queue | Check with `while` under the lock |
| Calling `notifyAll()` and assuming each waiter gets an item | One signal does not correspond to a number of permits/items | Store state and re-check the predicate |
| Reading `ready` outside `synchronized` | Data race; may miss notifications | Use the same monitor for check, wait, and update |
| Calling `wait()` outside the monitor | `IllegalMonitorStateException` | Synchronize on the exact receiver object |
| Calling `Condition.signal()` outside the associated lock | Violates contract; may fail at runtime | Signal while holding the corresponding lock |
| Using `Thread.sleep` instead of wait | Does not release the monitor or wait for a signal | Use monitor/Condition/queue |
| Not handling `InterruptedException` | Loses cancellation or proceeds erroneously | Propagate or restore the flag and exit |
| Repeating timed wait with the full initial duration | Total time can exceed the deadline | Recalculate remaining budget |
| Looping `await()` while checking the predicate elsewhere | Does not guarantee the predicate is true on resume | Check in the `while` loop under the same lock |
| Trying to trigger spurious wakeups by calling `notify` | Confuses real signals with spurious wakeups | Use an irrelevant notification to demo buggy `if`; understand the spurious wakeup contract separately |
| Believing `signal()` immediately hands the lock to the waiter | Wrong ordering assumptions | The waiter must reacquire the lock |
| Using `notify()` with multiple predicate types on the same wait-set | May wake up the wrong kind of waiter | Use `notifyAll` when needed or separate `Condition`s |
| Holding another lock B during `lockA.wait()` | Still holds B, risking deadlock | Avoid waiting while holding multiple locks; redesign lock ordering |
| Holding a lock during I/O or uncontrolled callbacks | Contention/deadlock/latency | Narrow the critical section |
| Using `awaitUninterruptibly` and forgetting to check the predicate | Spurious wakeups can still occur | Still use `while` |

## 11. From `wait/notify` to Higher-Level Primitives

In application code, not every problem requires hand-writing `wait/notify` loops. `java.util.concurrent` primitives can express the corresponding protocol more clearly:

| Purpose | Usually Appropriate Choice | Reason |
| --- | --- | --- |
| Wait for an item from a producer | `BlockingQueue.take()` | Queue manages empty/non-empty state itself |
| Limit the number of tasks entering a resource | `Semaphore.acquire()` | Permits are stored/granted by contract |
| Wait for a number of tasks to complete | `CountDownLatch.await()` | Count is an explicit coordination state |
| Threads reaching repeated synchronization points together | `CyclicBarrier` or `Phaser` | Phase protocol instead of hand-rolled flags |
| Wait for a task result | `Future.get()` / `CompletableFuture` | Includes both result/exception and completion |
| Wait for a complex predicate in a synchronized object | `Condition.await()` | Still must use a predicate loop under the lock |
| Exercise on basic monitor mechanics | `Object.wait/notifyAll` | Clearly illustrates principles, though many details are error-prone |

Even when using higher-level primitives, you still need to understand cancellation, timeouts, liveness, and invariants. For example, `BlockingQueue` solves waiting for elements, but does not by itself define a rule for "the producer has closed and no more items will arrive"; closing/termination still needs its own protocol if the application requires it.

## 12. Testing Correctness Without Relying on Random Spurious Wakeups

Because spurious wakeups may not appear on some JVMs or runs, a test that merely loops `wait()` many times hoping for a spurious wakeup is not a reliable proof.

### 12.1. Scenarios to Test

1. **Signal arrives before waiter:** state is already true; a waiter entering later must **not wait**. The Gate example above handles this.
2. **Signal does not make the predicate true:** the waiter must **keep waiting**; the `WrongIfWaitDemo` example shows buggy `if` code using a real notify.
3. **Many waiters, scarce resource:** when there is one item and multiple consumers are woken up, only the consumer that gets the item proceeds; the others go back to waiting.
4. **Predicate changes back before reacquire:** a signal happens, another thread consumes the resource before the waiter, and the waiter must re-check.
5. **Interrupt while waiting:** the task propagates the error/interrupt per contract, without executing business logic when the predicate is false.
6. **Timeout:** the task returns a timeout result properly when the budget runs out, without extending the overall deadline across multiple wakeups.
7. **Shutdown/cancellation:** every waiter knows when to terminate instead of waiting forever on a predicate that can never become true.
8. **Data invariant:** in a buffer, `size` is always between 0 and `capacity`; never take an element when the queue is empty or add when full.

### 12.2. Testing Techniques

- Use `CountDownLatch` or `CyclicBarrier` to orchestrate the interleavings to test, rather than `Thread.sleep(...)` as guesswork.
- Every test that can block needs a timeout and thread dump collection on failure, to avoid hanging the test suite indefinitely.
- Use futures/exception channels so worker errors are not silently ignored; `Thread.join()` only tells you the thread finished, not that the business logic succeeded.
- Run stress tests with multiple producers/consumers and compare produced vs. consumed item counts; passing tests are supporting evidence, not a substitute for reasoning about the protocol.
- When debugging a `WAITING` thread, check whether it is in `Object.wait`, `Condition.await`, or another primitive; many threads being `WAITING` is normal if they are genuinely waiting for unavailable resources.

### 12.3. Do Not Turn Test Failures into Wrong Conclusions About Spurious Wakeups

If a test demonstrates that `if` is wrong because we intentionally call `notifyAll` while state is still false, state clearly that this is a **real irrelevant signal**. It proves the `while` loop is necessary, but **is not** evidence that the JVM generated a spurious wakeup.

If a timeout test occasionally fails because the machine is overloaded, investigate the deadline, scheduling, and wait conditions; do not automatically conclude the cause is a spurious wakeup.

## 13. Pre-Production Review Checklist

- Does every waiter have a **clear predicate** tied to shared state?
- Are predicate checking and `wait/await` inside the **same lock/monitor**?
- Is every predicate wait placed inside **`while (!predicate)`**, even when there is only one waiter?
- After waking up, does the thread reacquire the lock and **re-check the invariant** before using the data?
- Does the writer update state under the lock before calling the appropriate notify/signal?
- Can a signal arrive before the waiter? Is the state sufficient so a later waiter does not miss the event?
- Are there multiple waiters or different predicate types? Does a single `notify` or `signal` risk picking the wrong group?
- Are there timeout, interrupt, and shutdown mechanisms to avoid waiting indefinitely when the condition is no longer achievable?
- Is there any path that holds multiple locks and calls `wait/await`, risking deadlock?
- Are there tests for irrelevant notifications, consumer contention, timeouts, and interrupts?
- If using `Condition`, does the code properly release the lock in `finally` and avoid long blocking I/O inside the critical section?
- Can hand-written coordination be replaced with `BlockingQueue`, `Semaphore`, or `CountDownLatch` for simplicity?

### Self-Check Questions

**1.** A thread just returned from `Object.wait()` after `notifyAll()` was called. Can we immediately infer `queue.isEmpty() == false`?

No. Another waiter may have consumed the item before this thread reacquired the monitor; or the notification may not correspond to that predicate. It must be re-checked under the lock.

**2.** Is a spurious wakeup caused by an "untimely" `notify()` call?

No. `notify()` is a **real signal**. A spurious wakeup is the possibility for a wait/await to return without the required notification/timeout/interrupt event. Both show that `while` must be used.

**3.** If the producer notifies before the consumer calls wait, is the notification saved?

No. Monitor notifications do not store permits for later waiters. The predicate must be kept in state protected by the same monitor; the consumer checks the state before waiting.

**4.** After `condition.signal()`, does the waiter immediately own the `ReentrantLock`?

Not yet. It must reacquire the lock after the signaling thread releases it; the predicate may change during that time.

**5.** An `awaitNanos` timeout returns, but the predicate is still false. Can we execute the work as if the predicate were true?

No. You must check the predicate and the wait budget; if time has expired and the condition is not met, return a timeout result.

**6.** Does calling `Object.wait()` release all locks the thread is holding?

No. It releases the monitor of the receiver object used for waiting; other held locks are not automatically released.

**7.** Why must the `while` loop be **inside** the lock rather than checking once outside and then calling wait?

So that checking the predicate and entering wait are coordinated atomically with the state-modifying side, avoiding the "checked, notification happened, then went to sleep" gap that causes a lost notification.

**Key takeaway:** Waking up **does not** mean the condition is true. Whether due to a spurious wakeup, an irrelevant signal, contention among multiple waiters, or a timeout, a correct program must **hold and check the predicate under the same lock**, loop with `while` when unsatisfied, and only use the state after the invariant is confirmed.
