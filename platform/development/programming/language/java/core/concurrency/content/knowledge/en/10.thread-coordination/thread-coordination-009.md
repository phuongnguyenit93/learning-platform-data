# Missed Signal and Lost Notification: Causes in Java Concurrency

When two threads coordinate, one side signals "data is available" or "the condition is true," while the other waits to proceed. A **missed signal / lost notification** bug occurs when the waiting thread fails to receive the necessary notification and may wait indefinitely even though the event it cares about has already happened. With `Object.wait()/notify()/notifyAll()`, a notification is not a message stored by the JVM to be delivered to a thread that joins later.

The core lesson is not "call `notify` more times," but rather **building a state protocol**: have a *predicate* that describes the actual condition, check it and transition to waiting **under the same monitor**, update the predicate and signal under that same monitor, and always re-check upon waking up. If the problem has a suitable higher-level primitive such as `CountDownLatch`, `Semaphore`, `BlockingQueue`, or `Future`, prefer its clearer contract instead of writing `wait`/`notify` manually.

This article covers **Thread Coordination in general Java Concurrency**, without discussing Spring-specific mechanisms.

## 1. Distinguishing "Event", "State", and "Notification"

Suppose a consumer needs to wait until a producer finishes creating a result. Three distinct concepts are involved:

| Component | Example | Role |
| --- | --- | --- |
| **Business state** | `ready == true`; non-empty queue; `remaining == 0` | The truth that the program needs to check. |
| **Predicate (wait condition)** | `ready`; `!queue.isEmpty()` | When the predicate is true, the thread can proceed. |
| **Notification** | `notify()`, `notifyAll()`, `Condition.signal()` | A hint for waiting threads to wake up and re-check the state. |

`notify()` **does not write** to the `ready` state and does not create a notification queue. `notifyAll()` also does not turn a notification into a "permit" saved for a thread that will call `wait()` in the future.

A correct protocol stores **the fact to be remembered** in state:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
~~~

The consumer reads the predicate under the same lock:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    // The ready condition is true at the moment the lock is held.
}
~~~

The two blocks above are **illustrative code snippets**, assuming `lock` and `ready` are already declared; the waiting method must handle or declare `InterruptedException`. This is the standard *guarded block* pattern.

## 2. How Object.wait/notify Works

With an intrinsic monitor, Java has a *wait set* associated with an object. Key behaviors:

1. A thread must **hold the object's monitor** when calling `wait()`, `notify()`, or `notifyAll()` on that object; otherwise, the JVM throws `IllegalMonitorStateException`.
2. Calling `wait()` places the thread into the wait set, **releases that object's monitor**, and waits for a notification, interruption, timeout (if specified), or spurious wakeup.
3. Before `wait()` returns or throws `InterruptedException`, the thread must **reacquire that monitor**. It cannot continue executing inside the critical section immediately upon being notified if the current holder has not released the lock.
4. `notify()` selects **one thread** currently in the object's wait set, if any; there is no guarantee it selects the "intended" waiter.
5. `notifyAll()` wakes up **all threads** currently waiting in the wait set; they compete one by one to acquire the monitor after it is released.
6. When **there are no waiters** in the wait set at the time of notification, the notification is not accumulated for later threads.
7. Spurious wakeups can occur, so returning from a single `wait()` call **does not prove** the predicate is true.

Saying "wake up" does not mean the waiter runs immediately. `notify` only changes eligibility to compete for the monitor; the calling thread may still hold the monitor until it exits `synchronized`. And `wait()` only releases **the monitor it is waiting on**, not any other monitors currently held.

### 2.1 Do Not Confuse with Thread.sleep

- `Thread.sleep(100)`: pauses the thread for a duration without **releasing any held monitors** and without waiting for a business event.
- `Object.wait(100)`: must hold the corresponding monitor; temporarily releases that monitor while waiting. It may return due to timeout, notification, or spurious wakeup.
- `Thread.join()`: waits for **a specific thread's lifecycle to terminate**, not for an arbitrary predicate.
- `LockSupport.park()`: a different low-level permit mechanism that can remember at most one permit in a park/unpark protocol; not equivalent to `Object.notify`.

## 3. Lost Notification When notify Occurs Before wait

Consider the timing:

~~~text
Producer                         Consumer
--------                         --------
synchronized(lock) {
    notifyAll()   // Nobody is waiting yet
}
                                 synchronized(lock) {
                                     wait() // Starts waiting after the notification
                                 }
                                 No new signal => may wait forever.
~~~

A notification before `wait()` **is not stored**. Without predicate state, the consumer has no way to know the event already happened.

### 3.1 Java 17+ Example Reproducing the Gap

Create `EarlyNotifyDemo.java`:

~~~java
public final class EarlyNotifyDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();

        synchronized (lock) {
            lock.notifyAll(); // No waiter yet; not stored.
        }
        System.out.println("Notified before wait");

        synchronized (lock) {
            lock.wait(50); // Timed wait so the demo does not hang indefinitely.
        }
        System.out.println("Wait returned; notification was not stored");
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac EarlyNotifyDemo.java
java EarlyNotifyDemo
~~~

Stdout (with no external interruption):

~~~text
Notified before wait
Wait returned; notification was not stored
~~~

The last line **does not** assert that `wait(50)` necessarily slept for exactly 50 ms: the call may return due to timeout or spurious wakeup, and scheduling also affects wall-clock time. The certain fact of the demo is that `notifyAll` happened when no waiter existed; there is no pre-stored notification for the later `wait`. `wait(50)` only allows the example program to terminate; **it does not fix the broken protocol**.

### 3.2 What Does Not Solve It?

- Replacing `notify()` with `notifyAll()` **does not** store notifications when there are no waiters.
- Calling `Thread.sleep(200)` before `notify` to "wait for the consumer to start" only makes the bug reproduce less often; the scheduler makes no guarantees.
- Using `volatile boolean ready` while still calling `wait()` unconditionally does not fix the bug; the waiter must **check `ready` before waiting**, and the check→wait relationship must be atomic.
- Waiting for a single `notify` without state cannot distinguish among "event never happened," "happened early," and "spurious wakeup."

## 4. Missed Signal Due to Non-Atomic Check-Then-Wait

Another bug pattern arises when the consumer checks the condition **outside the monitor** and then enters the monitor to wait:

~~~java
if (!ready) {
    synchronized (lock) {
        lock.wait();
    }
}
~~~

This is a **broken** snippet, not a standalone program. `ready` could even be `volatile` and still have a logic race:

~~~text
Consumer                         Producer
--------                         --------
if (!ready) => true
                                 synchronized(lock) {
                                     ready = true
                                     notifyAll()     // Nobody is waiting
                                 }
synchronized(lock) {
    wait()  // Starts waiting even though ready is already true
}
~~~

This is not necessarily a visibility bug: the consumer may have read `ready == false` **accurately at the moment of the check**. The bug is the time window between **checking** and **registering to wait**; the producer can signal in that gap.

Even putting the check in a **separate** `synchronized` block, exiting the lock, and re-entering to wait still leaves a gap:

~~~java
boolean shouldWait;
synchronized (lock) {
    shouldWait = !ready;
}
if (shouldWait) {
    synchronized (lock) {
        lock.wait();
    }
}
~~~

This code is wrong because two separate lock acquisitions **do not** form a single check-and-wait operation. The producer can change the predicate between the two critical sections.

### 4.1 Why Does a Single synchronized Block Solve the Race?

Correct pattern:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
~~~

While the consumer holds `lock` to check `ready`, the producer cannot simultaneously enter `synchronized(lock)` to modify `ready`. If the consumer sees `false`, it calls `wait()`; releasing the monitor and transitioning to the waiting state **are coordinated atomically under the monitor contract** with respect to any producer trying to acquire that lock. The producer can only acquire the lock, write `ready`, and notify after the consumer is ready to wait, or else the producer wrote `ready` before the consumer acquired the lock (in which case the consumer sees `true` and **does not wait**).

This eliminates the **check → subscribe** window of the protocol. There is no need to guess whether the consumer runs faster than the producer.

## 5. Protected Predicate Rule: State and Wait Under the Same Lock

A provably correct protocol has three rules:

1. **Define the predicate clearly:** for example, `ready == true`, `queue.size() > 0`, or `remaining == 0`.
2. **Every check/update of the predicate is under the same monitor:** the same lock object, not merely the same variable name; avoid unsynchronized writer updates.
3. **Notify after changing state:** update the predicate and call `notifyAll()` inside the same critical section; waiters use `while (!predicate) wait()`.

Writer:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
~~~

Waiter:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
~~~

This pair handles both cases:

- **Early signal:** the producer sets `ready = true` first; the consumer acquires the lock and does not enter `wait`.
- **Early waiter:** the consumer checks `false`, releases the lock via `wait`, the producer enters to change `ready` and notify; the consumer wakes up, reacquires the lock, and re-checks `true`.

### 5.1 Why Use while Instead of if?

Bug:

~~~java
synchronized (lock) {
    if (!ready) {
        lock.wait();
    }
    useResource();
}
~~~

This is a broken snippet assuming `useResource()` requires `ready` to be true. `wait()` may return due to a **spurious wakeup**, or be woken by a notification for a different condition, or multiple waiters may wake up and another waiter consumes the resource before this waiter acquires the monitor. In those cases, `ready` may still be `false`.

Using `while` always re-checks the **business predicate**, never treating a notification as proof that the condition is true.

## 6. Java 17+ Example: Guarded Block Handling Both Early Signal and Early Waiter

Create `GuardedSignalDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class GuardedSignalDemo {
    private static final class Gate {
        private final Object lock = new Object();
        private boolean open;

        void open() {
            synchronized (lock) {
                open = true;
                lock.notifyAll();
            }
        }

        void awaitOpen(CountDownLatch approachingWait)
                throws InterruptedException {
            synchronized (lock) {
                while (!open) {
                    if (approachingWait != null) {
                        approachingWait.countDown();
                    }
                    lock.wait();
                }
            }
        }

        boolean isOpen() {
            synchronized (lock) {
                return open;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        // Case 1: signal before any waiter exists.
        Gate early = new Gate();
        early.open();
        early.awaitOpen(null);
        System.out.println("Early signal observed: " + early.isOpen());

        // Case 2: waiter arrives before signal.
        Gate late = new Gate();
        CountDownLatch approachingWait = new CountDownLatch(1);

        Thread waiter = new Thread(() -> {
            try {
                late.awaitOpen(approachingWait);
                System.out.println("Late signal observed: " + late.isOpen());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "waiter");

        waiter.start();
        approachingWait.await();
        late.open();
        waiter.join();
        System.out.println("Done");
    }
}
~~~

Compile/run on JDK 17+:

~~~bash
javac GuardedSignalDemo.java
java GuardedSignalDemo
~~~

Stdout in a normal run with no external interruption:

~~~text
Early signal observed: true
Late signal observed: true
Done
~~~

**Explanation of each synchronization point:**

- `Gate.open()` stores state `open = true` **before** the notification, under the same monitor.
- `awaitOpen` uses `while (!open)` and `wait()` under that monitor.
- For the early signal, the waiter reads `open == true` and **does not need to wait**. What is remembered is the state, not the notification.
- For the late signal, the waiter calls `approachingWait.countDown()` while holding the monitor right before `wait()`. `main` waits on the latch, then calls `late.open()`. Whether `main` contends for the monitor before or after the waiter enters `wait`, no event is lost: the waiter still holds the monitor until calling `wait()`, and only then releases the monitor to the producer.
- `wait()` releases the monitor, allowing `open()` to update the state. When the waiter wakes up, it reacquires the monitor, checks the predicate, and prints the result.
- `waiter.join()` lets `main` wait for the worker to finish before printing `Done`. No `sleep()` or spin loop is needed to guess ordering.

Note: `approachingWait` is a coordination device for the **demo**, not a required component in a real guarded block. A long-lived `Gate` needs additional reset/close or cancellation rules if the API requires them. Because the state only transitions `false → true` once, this example is a **one-shot signal**.

## 7. Why notifyAll Is Usually Safer Than notify With Multiple Predicates

`Object.notify()` does not take a parameter like "wake up a thread waiting on `notEmpty`." It picks **an arbitrary waiter** from the monitor's wait set. If multiple kinds of waiters have different predicates, a notification may wake **the right monitor but the wrong group**.

For example, a bounded buffer has two conditions:

- Producers wait on `notFull` for space to insert an element.
- Consumers wait on `notEmpty` for an element to take.

If both kinds of waiters `wait()` on the same monitor, `notify()` may pick a thread whose predicate is still `false`. That thread wakes up, re-checks, and goes back to waiting. In some interleavings, the thread that needed to wake up receives no further notification, causing a **liveness failure** even though the state allows progress.

`notifyAll()` wakes up all waiters, and each thread re-checks its own predicate. This is usually **easier to prove correct** when there are multiple predicates or the number of waiters is not tightly controlled. The trade-off is a **thundering herd**: many threads wake up, contend for the monitor again, and most go back to waiting, increasing scheduling/contention overhead.

When there is only one predicate, and the waiter count and protocol are strictly controlled, `notify()` may suffice. However, you must **prove** that any arbitrarily chosen waiter can make progress under the protocol, not merely hope it is the one you wanted.

### 7.1 Condition Partitions Wait Sets

`ReentrantLock.newCondition()` lets you create separate wait sets, such as `notEmpty` and `notFull`. When a producer puts an item, it can call `notEmpty.signal()`, avoiding waking producers waiting for space. However, `Condition` still **does not automatically accumulate signals** for later waiters; the predicate remains the source of truth.

## 8. ReentrantLock and Condition: Same Bug If Checked Outside the Lock

The corresponding protocol with `Condition`:

~~~java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
} finally {
    lock.unlock();
}
~~~

Writer:

~~~java
lock.lock();
try {
    ready = true;
    condition.signalAll();
} finally {
    lock.unlock();
}
~~~

These are **illustrative code snippets**, assuming `lock` is a `ReentrantLock`, `condition = lock.newCondition()`, and `ready` is protected by `lock`. The waiting method handles `InterruptedException`.

`Condition.await()` has parallels to `Object.wait()`:

- The caller must hold the lock associated with the `Condition`.
- `await` releases the lock while waiting, then reacquires it before returning.
- It may return due to signal, spurious wakeup, or interruption; still use `while`.
- `signal()` does not store a token/permit for threads not yet awaiting.
- `signalAll()` wakes up all waiters on **that specific `Condition`**, not every `Condition` belonging to the same `ReentrantLock`.

Do not write:

~~~java
if (!ready) {              // Read outside the lock.
    lock.lock();
    try {
        condition.await(); // May wait after the signal already happened.
    } finally {
        lock.unlock();
    }
}
~~~

The broken code above creates the same lost signal window as `Object.wait`; switching to `ReentrantLock` does not by itself fix the **protocol**.

## 9. Java 17+ Example: Condition Waiting on a Predicate

Create `ConditionSignalDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class ConditionSignalDemo {
    private static final class Gate {
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

        void awaitOpen(CountDownLatch approachingWait)
                throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (!isOpen) {
                    approachingWait.countDown();
                    opened.await();
                }
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate gate = new Gate();
        CountDownLatch approachingWait = new CountDownLatch(1);

        Thread consumer = new Thread(() -> {
            try {
                gate.awaitOpen(approachingWait);
                System.out.println("Condition satisfied");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        approachingWait.await();
        gate.open();
        consumer.join();
        System.out.println("Done");
    }
}
~~~

Compile and run:

~~~bash
javac ConditionSignalDemo.java
java ConditionSignalDemo
~~~

Stdout in a normal run:

~~~text
Condition satisfied
Done
~~~

Here `CountDownLatch` lets `main` know the consumer has reached the condition-check region. `main` may be scheduled before the consumer actually enters `await()`, yet it still cannot update `isOpen` while the consumer holds the lock. Because `await()` releases the lock and transitions to waiting in coordination with the signaler acquiring the lock, there is no check→wait gap.

Unlike intrinsic monitors, `ReentrantLock.lockInterruptibly()` allows canceling a thread waiting to acquire the lock via interruption. This is useful when a task has an explicit cancellation contract; it does not eliminate the need to check the predicate with `while`.

## 10. CountDownLatch: Completion State Is Retained

When the requirement is simply "wait for an event to complete once," `CountDownLatch` is usually simpler and less error-prone than `wait`/`notify`.

~~~java
CountDownLatch done = new CountDownLatch(1);

// Producer, may be called before consumer:
done.countDown();

// Consumer, even if arriving later:
done.await();
~~~

This is an illustrative snippet. `countDown()` transitions the count from 1 to 0, and **the 0 state is retained**. Any subsequent `await()` calls return immediately once the count is 0; no signal is lost when the consumer arrives late.

Characteristics:

- A latch is **one-shot** and cannot be reset. When a new cycle is needed, create a new latch or use a multi-round primitive.
- `await()` can be interrupted; the timeout overload returns a `boolean`.
- Actions of the producer before `countDown()` *happen-before* actions of another thread after `await()` completes successfully, per the memory-consistency effects.
- A latch signals completion, but **does not itself hold a result value or exception** from the task.
- With multiple producers, the count must accurately reflect the number of completion milestones; a missing signal causes waiters to wait indefinitely.

## 11. Semaphore: Permits Are Retained for Later Acquire

`Semaphore` manages a number of permits. When a producer calls `release()` while no consumer is waiting, the permit count increases (within integer bounds per its contract), so a consumer calling `acquire()` later can use that permit.

~~~java
Semaphore permit = new Semaphore(0);
permit.release();   // Arrives before acquire.
permit.acquire();   // Takes the retained permit.
~~~

This is an illustrative snippet, requiring `import java.util.concurrent.Semaphore` and handling `InterruptedException`.

Differences:

- `Object.notify` does not accumulate notifications.
- `Semaphore.release` **increases the permit count**, retaining permits for later `acquire` calls.
- A permit is **permission/count**, not automatically a payload or event identity. If there are 10 distinct results, an appropriate data structure/queue is needed.
- When using a semaphore to bound concurrency, release the exact number of permits acquired. Over-releasing can expand the number of concurrent accessors beyond the intended limit.
- A semaphore's fairness option does not replace deadlines/cancellation and does not make business state atomic.

For one-shot completion, a latch usually expresses the intent more clearly. For resource counting or permit-style producer/consumer, a semaphore may fit well.

## 12. BlockingQueue: Holds Both Data and the "Item Available" Condition

A `BlockingQueue` is usually a better choice than hand-rolled `wait()/notify()` for producer–consumer:

~~~java
BlockingQueue<String> queue = new ArrayBlockingQueue<>(10);

// Producer:
queue.put("message");

// Consumer:
String message = queue.take();
~~~

This is an illustrative snippet, requiring imports for `BlockingQueue` and `ArrayBlockingQueue` and handling `InterruptedException`. If the producer calls `put` before the consumer calls `take`, the item is held in the queue without "losing a notification"; the consumer retrieves the actual data.

Difference from `notify`: the queue stores **elements**, not just attempts to wake a thread. It also defines blocking, timeout, capacity, rejection, or backpressure APIs depending on the implementation.

However, note:

- A queue does not automatically ensure a single consumer receives every message; multiple consumers can share the work.
- A queue can fill up; `put()` will block if there is no room, while `offer(timeout)` supports a deadline.
- If a producer mutates a mutable object **after `put`**, the consumer can race with that mutation; publish immutable messages/snapshots or establish a clear protocol.
- A queue does not automatically solve shutdown/cancellation; you can use interruption, a contracted sentinel/poison pill, or a separate lifecycle controller.
- Memory-consistency effects apply to element handoff per the concurrent collection/queue contract.

## 13. Java 17+ Example: Primitives That Remember State or Data

Create `StoredSignalDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;

public final class StoredSignalDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch done = new CountDownLatch(1);
        done.countDown();    // Signal happens before await.
        done.await();
        System.out.println("Latch: completed");

        Semaphore permits = new Semaphore(0);
        permits.release();   // Permit happens before acquire.
        permits.acquire();
        System.out.println("Semaphore: acquired");

        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(1);
        queue.put(42);       // Data arrives before take.
        System.out.println("Queue: " + queue.take());
    }
}
~~~

Compile/run on JDK 17+:

~~~bash
javac StoredSignalDemo.java
java StoredSignalDemo
~~~

Stdout:

~~~text
Latch: completed
Semaphore: acquired
Queue: 42
~~~

The three primitives store **three different kinds of information**: a latch holds completion count state, a semaphore holds permits, and a queue holds data elements. Thus all three handle the producer-before-consumer case properly, yet they cannot be substituted mechanically for one another when business semantics differ.

## 14. Future and CompletableFuture: Waiting for Completion With a Result

If the signal really means "a task has finished computing or failed," `Future` is usually more semantically accurate than a `ready` flag:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
try {
    Future<Integer> answer = executor.submit(() -> 6 * 7);
    System.out.println(answer.get());
} finally {
    executor.shutdown();
}
~~~

This is an illustrative snippet requiring imports for `ExecutorService`, `Executors`, and `Future`, plus handling the relevant exceptions. `Future.get()` waits for completion, returns the result on success, or reports failure/cancellation via the appropriate exception; the task may complete **before** the caller invokes `get`. Completion is stored in the `Future`, not lost like an empty notification.

`CompletableFuture` also provides combinators such as `thenApply`, `thenCompose`, and `allOf`. `CompletableFuture.join()` waits for completion and throws unchecked `CompletionException` on failure rather than `Future.get()`'s checked `ExecutionException`. Do not confuse `CompletableFuture.join()` with `Thread.join()`; the latter waits on a thread's lifecycle.

In multi-task systems, using a result-bearing primitive avoids manually coordinating a `ready` flag, a result slot, and an exception slot separately.

## 15. Timeouts, Interruption, and Spurious Wakeups

A wait that is notification-correct can still wait forever if the producer dies, forgets to signal, or the condition never becomes true. Design **cancellation paths and deadlines** as required.

### 15.1 Timed Wait Must Also Check the Predicate

Wrong:

~~~java
synchronized (lock) {
    lock.wait(1_000);
    if (!ready) {
        // No clear guarantee why wait returned.
    }
}
~~~

This is an illustrative snippet. A single timed wait is insufficient for the protocol because `wait` may return due to an unrelated notification or spurious wakeup before the deadline. You must use a predicate-checking loop and compute **remaining time**; otherwise, waking up and waiting another full 1,000 ms each time can extend the deadline unexpectedly.

With `Condition`, `awaitNanos` returns the remaining time per its contract and fits the checking loop well:

~~~java
boolean awaitReady(long timeout, TimeUnit unit)
        throws InterruptedException {
    long remaining = unit.toNanos(timeout);
    lock.lockInterruptibly();
    try {
        while (!ready) {
            if (remaining <= 0L) {
                return false;
            }
            remaining = condition.awaitNanos(remaining);
        }
        return true;
    } finally {
        lock.unlock();
    }
}
~~~

This is an illustrative method snippet: `lock` is a `ReentrantLock`, `condition` is a `Condition` bound to `lock`, and `ready` is the predicate. When `true` is returned, the predicate was true while the thread held the lock. When `false` is returned, the deadline expired without the predicate being observed true under the protocol; the producer might set `ready = true` **right after the method releases the lock**, so callers must handle end-of-deadline races according to their contract.

### 15.2 InterruptedException Is Not a Notification

`wait()`, `Condition.await()`, `CountDownLatch.await()`, and `BlockingQueue.take()` can throw `InterruptedException`. Interruption **does not** mean the predicate is true or the job is complete.

If the method can propagate the exception, usually let it propagate. In `Runnable.run()`, which does not declare checked exceptions, you can handle it with:

~~~java
try {
    awaitWork();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

This is a snippet inside `void run()`, assuming `awaitWork()` can throw. Calling `Thread.currentThread().interrupt()` restores the interrupt flag cleared when `InterruptedException` is thrown by standard blocking APIs; then exit or clean up appropriately.

**Do not** catch the exception and loop `wait()` indefinitely while ignoring cancellation. If the thread holds other resources/locks, design cleanup so state is not left inconsistent.

### 15.3 Spurious Wakeups

The JMM and API allow `wait()`/`Condition.await()` to wake up without a notification matching the condition. This is why **checking the predicate with `while` is mandatory**, not a quirk limited to some rare CPU. In tests, do not assert "every return from `wait` had a prior `notify`" as a Java rule.

## 16. Visibility and Happens-Before: notify Does Not Replace the Predicate

A correct coordination protocol requires both an **atomic handoff** of check→wait and **memory visibility** for the published state.

When the writer does:

~~~java
synchronized (lock) {
    result = 42;
    ready = true;
    lock.notifyAll();
}
~~~

and the reader does:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    System.out.println(result);
}
~~~

the same monitor provides mutual exclusion, and the writer's unlock *happens-before* the reader's subsequent lock on that same monitor. Thus the reader observes the state published under the protocol without needing every field to be `volatile`.

`notifyAll` by itself does not make arbitrary other application data thread-safe. Accesses that do not follow the monitor protocol can still race. Similarly, a `volatile ready` only helps when reads/writes are ordered properly; it does not keep multiple fields consistent as an atomic multi-step invariant.

With `CountDownLatch`, actions before `countDown()` *happen-before* actions after a successful `await()`; with queues/futures, the API's memory-consistency contract defines the data-publication path.

### 16.1 Warning: "Synchronizing on the Wrong Monitor"

Wrong:

~~~java
synchronized (producerLock) {
    ready = true;
    producerLock.notifyAll();
}

// Consumer:
synchronized (consumerLock) {
    while (!ready) {
        consumerLock.wait();
    }
}
~~~

This is an illustrative snippet with **two different lock objects**. The producer notifies on `producerLock`, while the consumer waits on `consumerLock`: they are in two different wait sets. Even though both use `synchronized` and `notify`/`wait` syntactically properly, the consumer can still hang.

In a simple event protocol, keep the same `lock` and predicate state together; place them under the ownership of one object rather than letting callers pass arbitrary locks.

## 17. Does Calling notify Before Releasing the Lock "Signal Too Early"?

Some people try to fix bugs by moving `notify()` **outside `synchronized`**:

~~~java
synchronized (lock) {
    ready = true;
}
lock.notifyAll(); // IllegalMonitorStateException.
~~~

This is broken code because the caller no longer holds `lock`'s monitor. `notify` must be called **inside** the `synchronized` block of the same object.

Calling `notify` before exiting the critical section is **normal**:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
    // May finish minor non-blocking work.
}
~~~

The woken waiter will wait to reacquire the monitor until the writer releases it. This lets the writer finish updating invariants before the waiter reads them. However, do not keep holding the lock for a long time after `notify` (I/O, callbacks, `sleep`), as that increases latency for the woken thread.

The right principle is **update state and signal under the lock, then release the lock promptly**, not separating the signal from the lock.

## 18. Lost Notification in Producer-Consumer and Shutdown

Signal bugs often get trickier when a system has multiple producers/consumers or needs to shut down.

### 18.1 Multiple Waiters Competing for One Item

When a producer puts **one item** into the buffer and calls `notifyAll`, multiple consumers may wake up. The first consumer takes the item; the second consumer arrives after and sees an empty queue. If `if` was used instead of `while`, the second consumer might try to take from an empty queue or return invalid data. The `while (empty) wait()` loop handles conditions that changed before the waiter reacquired the lock.

### 18.2 Shutdown Also Needs a Predicate

Suppose a consumer waits for "queue has an item," while the producer has stopped forever. Without a `closed` predicate or interruption/sentinel mechanism, the consumer can wait indefinitely. A clear pattern is:

~~~text
while queue empty AND not closed:
    await

if queue empty AND closed:
    exit
else:
    take item
~~~

This is **pseudocode**, not standalone Java. When closing the queue, update `closed = true` under the same lock and call `signalAll/notifyAll` to wake waiting threads. The wait predicate is now "queue has an item **or** the system is closed." Threads arriving after shutdown also see the stored `closed` flag and do not wait.

If using `BlockingQueue`, define how termination works because standard Java `BlockingQueue` has no universal `close()` operation across implementations; consider interruption, a contracted sentinel, or a separate lifecycle controller.

### 18.3 Repeating Event Rounds Need a Generation

A `boolean ready` only fits a one-shot `false → true` state. When a producer has multiple rounds of "finished round N," a single `true` flag cannot distinguish generations. Use a **sequence number/generation** or an appropriate primitive like `Phaser`/`CyclicBarrier` when the problem requires round-based coordination.

For example, a consumer thread records `lastSeenVersion`, then waits until `version > lastSeenVersion`. The producer increments `version` under the lock before `notifyAll`; the `version` state is stored, so an early notification does not lose the fact that "a new round occurred." Handle overflow and generation numbering if used long-term.

## 19. Deterministic Testing for Missed Signals

Lost notification bugs often "don't happen on my machine" due to rare interleavings. Tests using `sleep()` can pass thousands of times and then fail on CI. More reliable testing techniques:

1. **Force an early-signal schedule:** have the producer signal first, then let the consumer start waiting. With a correct API, the consumer must observe the predicate is already true immediately without blocking.
2. **Force an early-waiter schedule:** have the consumer check the predicate under the lock, use a latch to mark reaching the wait point, then have the producer signal. Verify completion occurs.
3. **Create contention:** multiple consumers waiting together, one producer emitting items; every woken consumer must re-check the predicate with `while` and not double-consume.
4. **Test unrelated notifications:** if a waiter wakes up while the predicate is still `false`, it must go back to waiting rather than proceeding.
5. **Test interruption:** the waiter exits the blocking operation per policy without leaving locks/state inconsistent.
6. **Test timeouts:** when no producer exists, the method does not wait forever if the contract has a deadline; upon expiration, it reports status clearly.
7. **Test shutdown:** both already-waiting consumers and consumers arriving after `close` must be handled properly.
8. **Test multiple rounds:** if the protocol has generations, generations are not missed per the contract (if every individual event must be retained, use a queue).
9. **Clean up tests in `finally`:** release latches/cancel/interrupt properly, join workers, avoid hanging tests and non-daemon threads outliving the test.

### 19.1 Test the Condition, Not Arbitrary Timing

Do not write:

~~~java
Thread.sleep(20);
producer.signal();
Thread.sleep(20);
assertTrue(consumerCompleted);
~~~

This is an illustrative broken snippet; `Thread.sleep` does not guarantee the thread has reached `wait`. Instead, use `CountDownLatch` to mark synchronization points, `Future.get(timeout)` to bound test execution time, and assert the predicate/result.

When a test times out, inspect the waiter's stack trace: is the thread `WAITING` in `Object.wait()`, `Condition.await()`, or a blocking queue? Check whether it is the same lock or the wrong lock, the order of predicate updates, whether the notification fired before `wait`, whether the wrong group was signaled, or whether another thread consumed the state first.

## 20. Distinguishing Lost Notification From Deadlock and Starvation

| Phenomenon | Root Cause | Symptom |
| --- | --- | --- |
| **Lost notification** | `notify` event occurs with no waiter, or a check→wait gap causes the waiter to miss the signal. | Waiter sleeps even though the predicate/event already occurred; no further signal arrives. |
| **Wrong waiter selection** | `notify` wakes a waiter whose predicate is still `false`. | Waiter wakes and waits again; the right waiter stays asleep. |
| **Spurious wakeup** | `wait` returns without an event satisfying the predicate. | If `if` is used instead of `while`, code behaves incorrectly. |
| **Deadlock** | Circular dependency on locks/conditions prevents participants from making progress. | Thread A waits for B, and B waits for A or corresponding monitors. |
| **Starvation** | A thread is never served while other threads continue making progress. | Overall activity continues, but a specific waiter never completes. |
| **Visibility bug** | Data reads/writes lack a proper happens-before (HB) relationship. | A thread may not see updates; adding `sleep`/logging changes the outcome. |

These bugs can occur together. For example, a writer notifying on the wrong monitor causes the waiter to wait forever, or a thread holding a lock calls `join()` on a worker needing that lock, creating a deadlock even if another part's notification protocol is correct.

Do not conclude "lost notification" just because a thread dump shows `WAITING`. That state may be completely valid when the predicate has not yet become true. Cross-check *state, signal, monitor ownership, generation, and each thread's execution path*.

## 21. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `notifyAll` before any waiter exists, without storing state. | Later waiters may wait forever. | Store predicate `ready`, or use a latch/semaphore/queue. |
| Checking `ready` outside the lock before calling `wait()`. | Producer can signal between check and wait. | Check + wait inside **the same `synchronized` block**. |
| Using `if (!ready) wait()`. | Spurious wakeup or another waiter consumes the state. | Use `while (!ready) wait()`. |
| Producer modifies predicate outside the lock but notifies inside the lock. | Protocol lacks a shared synchronization boundary. | Update state and notify under the same monitor. |
| Producer and consumer use two different lock objects. | Wait sets do not match; the right waiter is not woken. | Use the same monitor and one clear owner. |
| Using `notify()` when multiple predicates share one wait set. | Wakes the wrong group; liveness failure. | Use `notifyAll()` or multiple `Condition`s. |
| Calling `notify()` outside `synchronized`. | `IllegalMonitorStateException`. | Hold the right monitor when notifying. |
| Holding the lock for long I/O after `notify`. | Woken waiter cannot reacquire the lock. | Release the lock promptly; do I/O outside the critical section. |
| Catching `InterruptedException` and looping `wait()` indefinitely. | Cancellation has no effect. | Propagate or restore interrupt and exit safely. |
| Using `wait(timeout)` once and assuming the predicate is true. | Timeout or spurious wakeup may return without the condition. | Loop checking both predicate and deadline. |
| Using a one-shot boolean for multiple event rounds. | Cannot tell if a new generation occurred. | Use a version/generation or an event queue. |
| Producer finishes without signaling shutdown. | Consumer may wait forever. | Add a `closed`/cancellation predicate and `notifyAll` on close. |
| Using `sleep()` instead of handshake guarantees. | Race only becomes more random. | Use a synchronization primitive matching the protocol. |

## 22. Choosing a Primitive by What You Actually Need to Remember

| Goal | Reasonable Java Choice | Is a Signal Before Waiter Remembered? |
| --- | --- | --- |
| Simple state change with self-managed predicate | `synchronized` + `while` + `wait/notifyAll` | Yes, **via the predicate**, not via `notify`. |
| Waiting on multiple predicates over shared locked state | `ReentrantLock` + multiple `Condition`s | Yes, if **state** is updated/checked properly; signals themselves do not accumulate. |
| One-time completion (or N milestones) | `CountDownLatch` | Yes, count reaching 0 is retained. |
| Counting permits/access rights | `Semaphore` | Yes, released permits can be acquired later. |
| Passing a message from producer to consumer | `BlockingQueue` | Yes, item remains in the queue until taken, subject to capacity/policy. |
| Receiving a task's result or error | `Future` / `CompletableFuture` | Yes, completion/result/error is retained. |
| Waiting for a `Thread`'s lifecycle to end | `Thread.join()` | Yes, thread completion is observed via `join`. |
| Coordinating multiple recurring phases | `Phaser` / `CyclicBarrier` or generation protocol | Per each primitive's contract; handle timeouts/broken parties. |

Do not pick `notifyAll` merely because you "need to send a signal." Choose **the kind of state that must be retained**: boolean, count, permit, data, result, or generation. The closer the primitive is to the problem, the fewer race branches you have to prove yourself.

## 23. Self-Check Questions

**1.** A producer calls `notifyAll` when no waiter exists. A consumer calls `wait` afterward. Will the consumer automatically receive the old notification?  
**No.** Notifications are not queued. The consumer can only avoid waiting if predicate state indicates the work is already done.

**2.** Why can `volatile ready` still lose a notification if the consumer reads `ready` first and then enters `synchronized` to wait?  
**Because** the producer can flip `ready` and notify in the gap between those two steps. This is a check→wait race, not just a visibility race.

**3.** Why is `while (!ready) lock.wait()` more correct than `if`?  
**Because** `wait` can experience a spurious wakeup, or the condition may have changed before the waiter reacquired the lock; the predicate must be checked every time.

**4.** Does `Object.wait()` release every lock held by the thread?  
**No.** It releases only the monitor of the object being waited on, not other monitors.

**5.** Does `notifyAll()` guarantee every waiter will run immediately?  
**No.** Waiters still must reacquire the monitor; the scheduler and predicate state determine progress.

**6.** Why must updating `ready` and calling `notify` be in the same `synchronized` block?  
**So that** checking the predicate and transitioning to wait coordinate properly with the producer's state change/notification, while also establishing memory visibility via the monitor.

**7.** A consumer wakes up after the buffer has already been emptied by another consumer. What should it do?  
**Re-check the predicate in `while`** and continue waiting if the buffer is still empty.

**8.** When does `notify()` carry higher risk than `notifyAll()`?  
**When** the same wait set has multiple waiters or multiple predicates; `notify` may pick a waiter that cannot make progress.

**9.** Is a `CountDownLatch.countDown()` before `await()` lost?  
**No.** The count is retained; `await` returns immediately when the count is already 0.

**10.** How do `Semaphore.release()` and `Object.notify()` differ?  
**`release`** creates/increments a retained permit; **`notify`** only wakes a currently waiting thread and does not store an event.

**11.** Does `Condition.signal()` store a notification for a thread that calls `await()` later?  
**No.** Predicate state and check/await under the same lock are still required.

**12.** Does a single `wait(1000)` returning mean `ready` is `true`?  
**No.** It could be due to timeout, an unrelated notification, or spurious wakeup; `ready` must be checked under the lock.

**13.** If a consumer waits for a queue item while the producer has permanently shut down, what else is needed?  
**A `closed`/cancellation state and a wake-up signal** so the consumer does not wait forever.

**14.** Why can logging and `sleep` in tests hide lost notifications?  
**Because** they alter scheduling and interleaving timing; latches/barriers are needed to force specific test schedules.

**15.** What is the most important mindset when designing signal synchronization?  
**Store the truth in state**, use an atomic check→wait protocol, and treat notification purely as a wake-up mechanism to re-check state.

**Key takeaway:** In `Object.wait()/notify()`, **a notification is not a stored message**. The two most common sources of lost signals are **notifying before waiting** and **separating the predicate check from `wait`**. Fix them properly with a guarded block `synchronized(lock) { while (!predicate) lock.wait(); }`, update the predicate and call `notifyAll` under the same monitor, and handle spurious wakeups, interruption, and shutdown. When a higher-level primitive stores the exact thing you need to remember, prefer `CountDownLatch`, `Semaphore`, `BlockingQueue`, or `Future` to reduce protocol risk.