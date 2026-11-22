# Contended monitor and the risks of holding locks too long in Java

When multiple threads want to enter the same `synchronized` block, only one thread can hold the **monitor** at a time; the remaining threads may have to wait. This is **monitor contention**. Waiting is a normal part of synchronization, but if the thread owning the monitor holds the lock for too long, a seemingly small piece of code can become a bottleneck for the entire application: latency increases, throughput drops, waiting threads pile up, and even deadlock or starvation can occur.

This lesson focuses on **Java Concurrency in general**: intrinsic monitors, thread lifecycle, the Java Memory Model, how to design critical sections, and observability tools on the JVM. Spring-specific integration mechanisms belong to other topics.

## 1. What is a monitor and when does contention occur?

Every Java object can be used as an **intrinsic lock/monitor** for a `synchronized` code region. Once a thread has entered the block:

~~~java
synchronized (lock) {
    // Access shared state protected by lock.
}
~~~

other threads wanting to enter `synchronized (lock)` must wait until the monitor is released. If each thread uses a different lock object, they **do not** contend for the same monitor; choosing the right lock identity determines both mutual exclusion and visibility guarantees.

A thread that owns a monitor can re-enter `synchronized` on the same monitor because Java monitors are **reentrant**. Each entry must have a corresponding exit; when exiting synchronized blocks, the JVM releases the monitor even if an exception is thrown. This does not mean business operations automatically roll back after an exception.

### 1.1 Distinguishing three types of situations

| Situation | Outcome | Example |
| --- | --- | --- |
| **Uncontended** | Thread acquires the monitor and runs the critical section, usually quickly. | Only one thread uses a counter. |
| **Normal contention** | Some threads wait briefly, then enter the critical section one by one. | Multiple threads update a shared queue or counter. |
| **Prolonged contention** | The thread owning the lock waits for I/O, sleeps, performs long computations, or invokes callbacks; other threads queue up. | A worker holds the lock while calling a network service or processing a large file. |

**Contention does not mean deadlock.** If the holder releases the monitor in finite time and other threads are scheduled CPU time, they can make progress. Deadlock is a circular dependency where a group of threads cannot make progress; it may involve multiple monitors or different kinds of waiting.

**Contention also does not by itself prove a correctness bug.** A lock may protect invariants completely correctly while causing poor performance. Conversely, removing a lock to increase throughput without replacing the protocol can cause data races and corrupted data.

## 2. `synchronized` controls ownership and memory visibility

`synchronized` provides two guarantees that must be distinguished:

1. **Mutual exclusion:** at any point in time, only one thread can own a monitor for critical sections on that same monitor.
2. **Happens-before:** an unlock on a monitor **happens-before** a subsequent lock on the same monitor. Updates performed under a proper protocol are observed by other threads according to Java Memory Model rules.

Example:

~~~java
private final Object lock = new Object();
private int balance;

void deposit(int amount) {
    synchronized (lock) {
        balance += amount;
    }
}

int balance() {
    synchronized (lock) {
        return balance;
    }
}
~~~

This is an **illustrative class snippet**, not a complete file with `main`. Both the writer and the reader use the **same `lock`**, so not only is the addition protected from interleaving, but the read also receives proper visibility.

If only the writer is synchronized while the reader reads `balance` outside the lock, it cannot be assumed that all access paths follow the same protocol. If two different monitors are used, having the `synchronized` keyword in both places still does not create shared mutual exclusion.

A monitor does not by itself determine fairness; Java **does not guarantee FIFO** for contenders acquiring a monitor. A thread that has been waiting longer may still be bypassed by another contender depending on the execution schedule.

### 2.1 Which object does a `synchronized` method lock?

| Syntax | Monitor used |
| --- | --- |
| `synchronized (mutex) { ... }` | The `mutex` object reference itself. |
| `public synchronized void update() { ... }` | `this` of the instance executing the method. |
| `public static synchronized void reset() { ... }` | The `Class` object of the class declaring the method, e.g. `Counter.class`. |

Two synchronized instance methods belonging to **two different instances** do not lock each other. A synchronized instance method and a static synchronized method also use **two different monitors**. When protecting shared state, you must design lock identity and ownership appropriately.

Avoid `synchronized ("literal")`, `synchronized (Integer.valueOf(...))`, or locking on an object that external code might accidentally share. Interned strings and reused boxed values can cause unintended contention. Typically, choose:

~~~java
private final Object lock = new Object();
~~~

and allow state access only through the owner's methods.

## 3. Differences between `BLOCKED`, `WAITING`, and `TIMED_WAITING` threads

When inspecting a thread dump, the word "waiting" can describe several different mechanisms. In Java, `Thread.State` helps distinguish the cause.

| State | Common meaning | Example |
| --- | --- | --- |
| `RUNNABLE` | Executing or ready for the JVM to execute; not necessarily occupying a CPU at the exact moment of observation. | Computing inside a method. |
| `BLOCKED` | Waiting to acquire an intrinsic monitor to enter or re-enter a `synchronized` region. | A contender before `synchronized(lock)` while the holder has not released it. |
| `WAITING` | Waiting indefinitely for a condition or completion operation. | `Object.wait()` without timeout, `Thread.join()` without timeout, `CountDownLatch.await()`. |
| `TIMED_WAITING` | Waiting with a timeout. | `Thread.sleep(100)`, `Thread.join(100)`, timed `Object.wait()`. |
| `TERMINATED` | The thread has finished. | `run()` returned or exited via an exception. |

**Important:** a thread waiting on a `ReentrantLock` may appear as `WAITING` or `TIMED_WAITING` based on the lock's park primitive, not necessarily `BLOCKED`. `BLOCKED` in `Thread.State` refers specifically to an **intrinsic monitor**.

In addition, a thread in `WAITING` can still **be holding another monitor**. A thread's state does not indicate that it holds no locks. You must read the stack trace and the "locked monitors" section in the thread dump.

### 3.1 Contention picture

~~~text
Thread A                            Thread B                       Thread C
--------                            --------                       --------
synchronized (lock)                synchronized (lock)            synchronized (lock)
       |                                   |                              |
       v                                   v                              v
owns monitor                         BLOCKED waiting                BLOCKED waiting
       |
long critical section
       |
unlock() on exiting synchronized
                                           |
                                           v
                                    a contender acquires the monitor
~~~

There is no mandatory FIFO rule in intrinsic monitors to determine whether B or C wins. What we can rely on is that **only one holder** runs inside the same critical section at a time.

## 4. Java 17+ example: observing two threads contending for the same monitor

This example uses latches so the holder keeps the monitor until `main` allows it to release. That way, message ordering is deterministic and does not depend on whether `sleep()` is long enough.

Create `MonitorContentionDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class MonitorContentionDemo {
    public static void main(String[] args) throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch holderEntered = new CountDownLatch(1);
        CountDownLatch releaseHolder = new CountDownLatch(1);
        CountDownLatch contenderApproaching = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            synchronized (monitor) {
                System.out.println("Holder entered");
                holderEntered.countDown();
                try {
                    releaseHolder.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                System.out.println("Holder leaving");
            }
        }, "holder");

        Thread contender = new Thread(() -> {
            contenderApproaching.countDown();
            synchronized (monitor) {
                System.out.println("Contender entered");
            }
        }, "contender");

        holder.start();
        holderEntered.await();
        contender.start();
        contenderApproaching.await();

        releaseHolder.countDown();
        holder.join();
        contender.join();
        System.out.println("Finished");
    }
}
~~~

Run on JDK 17 or later:

~~~bash
javac MonitorContentionDemo.java
java MonitorContentionDemo
~~~

Stdout when there is no external interruption:

~~~text
Holder entered
Holder leaving
Contender entered
Finished
~~~

**Analysis:** `holder` acquires the monitor before signaling `holderEntered`. `contender` cannot print "Contender entered" before `holder` exits `synchronized`. `main` calls `releaseHolder.countDown()` to let `holder` finish and then joins both threads.

`contenderApproaching.countDown()` only indicates that the thread has reached just before the synchronized statement; it **does not prove that `contender` had already reached the `BLOCKED` state** before `main` opened the gate. To capture the `BLOCKED` state accurately, `holder` must keep the monitor while you take a thread dump or observe `Thread.getState()` when `contender` is actually waiting. Do not treat a single run printing in order as proof that contention was measured.

An intentional detail in the demo: `holder` calls `CountDownLatch.await()` **while still holding the monitor**. Awaiting on a latch does not release that intrinsic monitor, so contenders can be blocked while `holder` waits. This is a way to reproduce **holding a lock too long** for learning purposes, not a pattern to apply in business logic.

## 5. Why are long critical sections harmful?

Critical section length is the duration a thread holds a lock from entry to exit. When multiple threads contend, this duration contributes to the latency of all contenders.

Conceptual example: 20 requests contend for the same monitor; each holder holds the monitor for 50 ms just to process work inside the lock. In an ideal sequential schedule, 20 critical sections already take about 1,000 ms of total lock-hold time, excluding scheduling and overhead; later requests may have to wait for many turns. This is only an **illustrative estimate**, not a formula for measuring actual JVM latency.

Common consequences:

- **Lock convoy:** threads line up one after another behind a slow holder. A few prolonged operations create a large latency tail.
- **Reduced throughput:** work that could run in parallel outside is serialized inside the monitor.
- **Increased tail latency:** the average may still look fine, but p95/p99 of requests needing the lock spikes sharply.
- **Thread exhaustion:** in a thread pool with a finite number of workers, many workers waiting on a lock leaves fewer workers free to do other work.
- **Priority inversion:** a lower-priority thread holds a lock needed by another thread; the higher-priority thread must wait. Java thread priorities do not provide a guaranteed portable solution for this situation.
- **Sensitivity to failures:** slow I/O, unintended retries, or a callback throwing an exception can turn a small critical section into a major bottleneck.

For every lock, look for the **slowest execution path**, not just the average code path. A rare branch that makes a network call, processes a file, awaits a latch, or calls a method of unknown duration can still cause the queue behind it to surge.

## 6. Operations that are very dangerous inside a monitor

### 6.1 I/O, network, database, and remote calls

~~~java
synchronized (lock) {
    updateLocalState();
    remoteClient.send(payload); // Can be slow, retry, or never return.
}
~~~

This is an illustrative snippet, not a runnable file; `remoteClient`, `payload`, `updateLocalState`, and `lock` are hypothetical components. All other contenders on the same lock must wait **for the entire duration of the remote call**, even if they only need to read a value.

One design approach is to prepare data/snapshots under the lock, release the lock, and perform I/O outside. However, if the I/O result determines how state is modified, you must design re-validation/commit logic to avoid a **stale snapshot**. Do not just move the call outside the lock while ignoring correctness.

### 6.2 `Thread.sleep()` and other waits

~~~java
synchronized (lock) {
    Thread.sleep(500);
}
~~~

This snippet assumes the method declares/handles `InterruptedException`. `sleep()` **does not release the held monitor**. For 500 ms, contenders can be `BLOCKED` even though the holder thread is doing no useful work.

Similarly, `CountDownLatch.await()`, `Future.get()`, and `Thread.join()` do not automatically release **unrelated monitors** held by the thread. Calling them while holding a lock can cause a lock convoy or a deadlock if the awaited task itself needs that same lock.

In contrast, `Object.wait()` called while holding the monitor of **that exact object** releases that monitor and waits under the wait/notify protocol; upon waking up, the thread must reacquire the monitor before returning. `wait()` **does not release other monitors** held by the thread. It also requires a `while` loop checking the predicate because spurious wakeups can occur.

**Do not arbitrarily replace `sleep()` with `wait()`**: wait/notify is a condition protocol requiring monitor ownership, signaling, and predicate checking. For task completion, prefer `Future`/latches; for producer–consumer, consider `BlockingQueue`.

### 6.3 Callbacks and uncontrolled external code

~~~java
synchronized (lock) {
    state = next;
    listener.onChanged(state);
}
~~~

This is an illustrative snippet with `state`, `next`, and `listener` already declared. A callback can call back into the current object, acquire another lock, wait on I/O, or throw an exception. Even though Java monitors are reentrant, a callback acquiring locks in a different order can create a wait cycle across multiple threads.

Consider copying a snapshot and the listener list inside the lock, then invoking callbacks **after releasing the lock**. If callbacks must reflect exact event ordering, design an event queue/sequence version rather than assuming reordering statements preserves all semantics.

## 7. Reducing monitor hold time while still protecting invariants

The goal is to **do as little work as possible while owning the monitor**, while still keeping data conditions that must be updated atomically together.

For example, suppose you need to compute a checksum of a large payload and then update a counter. Computing the checksum on **local/immutable** data can be done before acquiring the lock. Only add the result to shared state inside the monitor.

~~~java
int checksum = calculateChecksum(immutableInput); // No lock needed.
synchronized (lock) {
    aggregateChecksum += checksum;
    processedCount++;
}
~~~

This is an illustrative snippet, not a standalone method/class. It assumes `immutableInput` is not modified by another thread during calculation, and the checksum does not depend on shared state that has changed. Both `aggregateChecksum` and `processedCount` are updated under the **same lock**, so there is still a proper atomic boundary with respect to readers that also use the lock.

### 7.1 The Prepare → Lock → Commit pattern

A common workflow:

1. **Prepare:** validate parameters, parse input, perform pure computations, create candidate value objects; do not access mutable shared state without a valid snapshot.
2. **Lock:** acquire the monitor of the invariant's proper owner.
3. **Validate:** re-check preconditions **that depend on current state** inside the critical section.
4. **Commit:** update the group of fields that must change atomically; do not perform I/O or callbacks in between.
5. **Unlock:** exit the synchronized block early, giving other threads a chance.
6. **Post-commit:** emit events/send I/O after the lock, with clear idempotency/ordering protocols if needed.

This pattern keeps critical sections shorter. However, if preparation uses a snapshot that can go stale, compare versions/re-check inside the lock before committing.

### 7.2 Optimizations must not break snapshots

Suppose we must do `available--` and `reserved++` to preserve `available + reserved == capacity`. We can precompute parameters that depend only on input, but reading `available`, checking the condition, and modifying **both fields** must be in the same critical section.

~~~java
boolean reserveOne() {
    synchronized (lock) {
        if (available == 0) {
            return false;
        }
        available--;
        reserved++;
        return true;
    }
}
~~~

This is an illustrative method snippet with hypothetical fields and lock. If a reader needs to observe the total, the reader must use the same lock and **read both fields in a single lock acquisition**. Two separate synchronized getters can return two different snapshots if a writer interleaves between them.

## 8. Java 17+ example: small critical section, accurate updates

Create `SmallCriticalSectionDemo.java`:

~~~java
public final class SmallCriticalSectionDemo {
    private static final class Totals {
        private final Object lock = new Object();
        private int processed;
        private long sum;

        void record(int contribution) {
            synchronized (lock) {
                processed++;
                sum += contribution;
            }
        }

        Snapshot snapshot() {
            synchronized (lock) {
                return new Snapshot(processed, sum);
            }
        }
    }

    private record Snapshot(int processed, long sum) {}

    private static int prepareWork(int input) {
        // Simulate pure computation using local data.
        return input * 2;
    }

    public static void main(String[] args) throws InterruptedException {
        Totals totals = new Totals();
        Runnable task = () -> {
            for (int i = 1; i <= 1_000; i++) {
                int contribution = prepareWork(i);
                totals.record(contribution);
            }
        };

        Thread a = new Thread(task, "worker-a");
        Thread b = new Thread(task, "worker-b");
        a.start();
        b.start();
        a.join();
        b.join();

        Snapshot snapshot = totals.snapshot();
        System.out.println("Processed: " + snapshot.processed());
        System.out.println("Sum: " + snapshot.sum());
    }
}
~~~

Compile/run on JDK 17+:

~~~bash
javac SmallCriticalSectionDemo.java
java SmallCriticalSectionDemo
~~~

Stdout:

~~~text
Processed: 2000
Sum: 2002000
~~~

**Why is this correct?** Each thread processes 1,000 values, totaling 2,000 records. `prepareWork(i)` returns `i * 2` and touches no shared state, so it runs outside the monitor. `Totals.record()` holds the lock only for the two updates. `snapshot()` reads both fields under the same monitor. One thread's total contribution is `2 × (1 + 2 + ... + 1000) = 1,001,000`; two threads produce `2,002,000`.

You cannot conclude from a small example that this change is always faster than every long-lock version; reducing lock scope generally pays off when the prepare step is expensive. If every calculation depends directly on shared state, you must balance correctness against contention levels.

## 9. Lock scope and correctness trade-offs

A change that looks like an "optimization" can break atomicity guarantees:

~~~java
// Wrong if the check depends on shared state.
boolean canReserve;
synchronized (lock) {
    canReserve = available > 0;
}

// Another thread can reserve all remaining quota here.
if (canReserve) {
    synchronized (lock) {
        available--;
        reserved++;
    }
}
~~~

This is a buggy snippet, not a standalone program. The check and the commit are split into **two separate critical sections**, so another thread can interleave in between. Correctness requires re-checking the precondition **within the same lock acquisition** as the update.

You also need to consider error handling and exception safety: `synchronized` releases the monitor if an exception is thrown, but **does not automatically roll back** writes already performed before the exception. If a method updates three fields and then calls code that may throw in the middle, the monitor is released with potentially inconsistent state. Design **prepare/calculate all → validate → commit safe assignments**, or implement verified rollback.

### 9.1 Snapshot/version when computing outside the lock

If a heavy computation depends on current state, you can apply an optimistic pattern:

~~~text
lock:
    snapshot = copy(state, version)
unlock

heavyComputation(snapshot)  // may take a long time

lock:
    if (version has changed) retry or reject
    else commit(candidate), increment version
unlock
~~~

This is **pseudocode**, not runnable Java. The snapshot must be complete and must not contain references to mutable objects that can continue changing outside the lock. If the version has changed, the prepared result may be stale; do not commit blindly.

If the computation has side effects that cannot be safely repeated (sending money, calling an external service), retries require an idempotency mechanism or switching to an explicit transaction workflow. Do not put side effects inside a section that can be re-executed without control.

## 10. Deadlock patterns from holding a monitor while waiting

A particularly dangerous bug: the holder keeps a monitor and waits for a thread/task that needs that very monitor to complete.

~~~java
Object lock = new Object();

Thread worker = new Thread(() -> {
    synchronized (lock) {
        // Worker needs lock to finish.
    }
});

synchronized (lock) {
    worker.start();
    worker.join(); // Caller still holds lock.
}
~~~

This is a **bug illustration snippet**; the enclosing method must handle `InterruptedException`. The caller holds `lock` during `join()`; the worker cannot enter the monitor and therefore cannot finish; the caller waits for the worker, creating a wait cycle. `join()` **does not arbitrarily release locks** held by the caller.

One fix:

~~~java
worker.start();
worker.join(); // Wait without holding the lock the worker needs.
~~~

This is also a snippet, assuming `worker` is already constructed and the method handles interruption.

Deadlock with two monitors can occur when:

~~~text
Thread A: owns lock1, waits lock2
Thread B: owns lock2, waits lock1
~~~

If multiple locks are genuinely needed, use a **global lock ordering** by a stable ID, consistently across all call paths, and avoid callbacks that might acquire another lock in reverse order. For state belonging to the same invariant, a single owner lock may be simpler.

**Distinctions:**

- Contended monitor: contenders can make progress once the holder eventually releases the lock.
- Deadlock: participants form a dependency cycle; no participant in the cycle can release its wait on its own.
- Starvation: a thread is denied service for an unbounded time even though other threads progress; intrinsic monitors have no FIFO guarantee.
- Livelock: threads keep running/reacting without completing useful work.

Measuring high or low CPU usage alone is not enough to distinguish these cases; you need data on thread states, lock ownership, and wait protocols.

## 11. Intrinsic monitors lack timed or interruptible acquisition

With standard `synchronized`, a thread waiting to **acquire a monitor** has no API to wait at most N milliseconds or cancel waiting via `InterruptedException` like `lockInterruptibly()`. If `interrupt()` is called on a thread while it is `BLOCKED` trying to acquire a monitor, it does not immediately abandon the lock request; the interrupted flag may be recorded for code to handle once it proceeds.

This differs from `Object.wait()` when a thread has already entered the monitor and explicitly releases it to wait on a condition: `wait()` is interruptible and requires owning the monitor of that exact object.

If you need a bounded lock-acquisition time or cancellation handling while waiting, consider `ReentrantLock`:

- `tryLock()`: tries to acquire the lock immediately; returns `true/false`.
- `tryLock(timeout, unit)`: waits up to a timeout, can throw `InterruptedException`.
- `lockInterruptibly()`: allows interruption while waiting for the lock.
- `lock()`: waits to acquire the lock without the same cancellation semantics as `lockInterruptibly()`.

Note: `ReentrantLock` provides exclusion and memory effects similar to a monitor when used properly; it **does not** automatically make critical sections shorter. If you still perform slow I/O while holding a `ReentrantLock`, contention remains.

## 12. Java 17+ example: `ReentrantLock.tryLock` with timeout

This example holds a lock in one thread and has another thread try to acquire the lock within a short timeout. Latches ensure the holder does not release before the contender finishes trying.

Create `TimedLockDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public final class TimedLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch holderHasLock = new CountDownLatch(1);
        CountDownLatch releaseHolder = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            lock.lock();
            try {
                holderHasLock.countDown();
                releaseHolder.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                lock.unlock();
            }
        }, "holder");

        Thread contender = new Thread(() -> {
            try {
                boolean acquired = lock.tryLock(100, TimeUnit.MILLISECONDS);
                System.out.println("Acquired: " + acquired);
                if (acquired) {
                    try {
                        // Protect state if lock was acquired.
                    } finally {
                        lock.unlock();
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "contender");

        holder.start();
        holderHasLock.await();
        contender.start();
        contender.join();
        releaseHolder.countDown();
        holder.join();
    }
}
~~~

Compile/run:

~~~bash
javac TimedLockDemo.java
java TimedLockDemo
~~~

Stdout when there is no external interruption:

~~~text
Acquired: false
~~~

**Why is this deterministic?** `holder` does not release the lock until `main` calls `releaseHolder.countDown()`. `main` only opens the gate **after `contender` finishes**, so `contender` must time out without being able to acquire the lock. Even if `contender` is scheduled late, `holder` still holds the lock until `contender` completes.

`tryLock(100, TimeUnit.MILLISECONDS)` bounds the **time spent waiting to acquire the lock**, not the entire task or the work after acquiring the lock. In real code, do not use an arbitrary small timeout in place of an SLA; define request-level deadlines and handle the lock-acquisition-failure branch. Ensure every branch that acquires the lock calls `unlock()` in `finally`.

**Note:** the example illustrates the success/failure path when not interrupted externally. In real programs, design shutdown/cancellation so latches are released and threads are joined according to a clear policy.

## 13. Proper condition waiting: `Object.wait()` and `Condition.await()`

Sometimes a thread holds a lock but needs to wait for **a data condition** changed by another thread. If it waits while still holding the monitor, the thread changing the condition may not be able to enter the locked region to signal.

Use monitor wait properly:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    // ready is true under the monitor lock.
}
~~~

This snippet assumes `lock` and `ready` exist and the method handles `InterruptedException`. `wait()`:

1. Requires the thread to own the monitor of `lock`.
2. **Releases the `lock` monitor** while waiting so other threads can enter and change the predicate.
3. Upon waking up, must reacquire the monitor before returning from `wait()`.
4. Can wake up spuriously (*spurious wakeup*), so **always** check the predicate in a `while` loop, not just an `if`.
5. Does not automatically release other monitors held by the thread.

The thread changing the state must use the same monitor and notify according to the protocol:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
~~~

This is an illustrative snippet. `notifyAll()` wakes up waiters so they can compete to reacquire the monitor; it does not immediately hand over the CPU or let waiters enter the critical section right away. If the state involves multiple complex conditions, consider `java.util.concurrent.locks.Condition` with `ReentrantLock`, or use `BlockingQueue`/`CountDownLatch`/`Semaphore` if they fit the problem better.

Do not replace all `wait/notify` with `sleep` and polling; that loses predicate semantics and makes response time hard to control.

## 14. Observing contention with thread dumps and JVM tooling

When a Java application experiences rising latency, check whether multiple threads are waiting on the same monitor. Available tools depend on the JDK/JVM and environment, but the observation mindset is consistent:

### 14.1 Thread dump

You can generate a thread dump using an appropriate JDK tool, for example on HotSpot:

~~~bash
jcmd <pid> Thread.print -l
~~~

`<pid>` is a **placeholder for the Java process PID**, not a literal command to run verbatim. Output varies by JDK, but typically shows thread names, states, and current stack frames. Look for:

- Multiple `BLOCKED` threads at the same method/monitor.
- Lines indicating a thread is "waiting to lock" a monitor and the corresponding object/owner when the JVM prints that information.
- The holder thread and its stack: is there `Thread.sleep`, I/O, an external method call, heavy data processing, or waiting on another task while holding the lock?
- Signs of a wait cycle between lock A/B, or a thread holding a lock while waiting for completion of a worker that needs that lock.

Do not conclude from **a single** `BLOCKED` thread that there is a deadlock. Brief contention can be normal; examine the number of contenders, duration, frequency, and progress over time.

### 14.2 ThreadMXBean

`java.lang.management.ThreadMXBean` can help inspect thread states, locked monitors, deadlocks, and some contention statistics (depending on the JVM and configuration). For example:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
long[] deadlocked = bean.findDeadlockedThreads();
~~~

This is an illustrative snippet requiring imports for `java.lang.management.ManagementFactory` and `java.lang.management.ThreadMXBean`. The API returns `null` when no deadlocks within its detection scope are found; an empty result **does not prove** there is no starvation, livelock, I/O wait, or task dependency cycle.

`isThreadContentionMonitoringSupported()` indicates whether the JVM supports blocked/waited time statistics. When supported, it can be enabled via `setThreadContentionMonitoringEnabled(true)` if permitted and measurement is needed; collection has overhead and the metrics are runtime data according to JVM capabilities, not guaranteed SLAs.

### 14.3 Java Flight Recorder

JFR has events for analyzing monitor contention, including `jdk.JavaMonitorEnter` on supporting JDKs. Events have thresholds/collection settings, so not every monitor acquisition is recorded. Check the recording configuration, collection timestamps, involved threads, and stack traces to find slow critical sections.

JFR is useful for comparing contention **before and after** a code change. Some profiling tools also measure lock hold time and wait time separately; distinguish these two metrics to avoid optimizing the wrong place.

## 15. What to measure when improving locks

Do not evaluate a fix with a single "feels faster" run. Measure under a realistic contended workload:

| Metric | Question it helps answer |
| --- | --- |
| **Blocked time / contention count** | How often and how long do threads wait for the monitor? |
| **Critical-section hold time** | How long does the holder keep the lock? Are there unusual outliers? |
| **Throughput** | How many operations per second does the system complete under load? |
| **p95/p99 latency** | How are the slowest requests affected? |
| **Thread pool saturation** | How many workers are busy waiting on locks, and what is the queue backlog? |
| **CPU utilization / context switching** | Are many threads contending for CPU or incurring overhead from contention? |
| **Correctness invariants** | Does the optimization preserve accurate results without lost updates? |

The same measurement can reflect multiple causes. For example, increased blocked time can stem from long hold times, more contenders, or a new code path using the lock. Look at the correlation between cause and load, rather than simply blaming the `synchronized` keyword.

If the critical section is very short and contention is rare, keeping a simple lock often wins in clarity. Adding complexity with lock striping or CAS may not improve performance if conflict/GC/retry costs are higher.

## 16. Advanced optimization approaches and limits

### 16.1 Reducing lock scope or acquisition frequency

Batch updates that can be batched from a business perspective to reduce acquisition count, but do not hold the monitor longer just to process a huge batch. Weigh the trade-off between batch size, contender latency, and the invariants to protect.

### 16.2 Splitting independent state

If two groups of data **do not share an invariant**, each group can have its own lock or its own owner object. However, if a report requires a consistent snapshot across both groups, splitting locks makes atomic snapshots harder. Do not split locks per field of the same invariant just to reduce contention.

### 16.3 Immutable snapshot + atomic update

If state can be represented as an immutable value object, an `AtomicReference<State>` lets readers grab **a snapshot reference** without holding a monitor. Writers can build a new state and commit via `compareAndSet`. This is another way to preserve multi-field invariants, but CAS can retry many times under contention, allocates new objects, and requires avoiding non-idempotent side effects in the retry loop.

### 16.4 Standard concurrent data structures

`ConcurrentHashMap`, `BlockingQueue`, `LongAdder`, and primitives in `java.util.concurrent` have their own contracts suited to many workloads. For example, `LongAdder` is useful for high-throughput statistics when many writers increment concurrently, but `sum()` during concurrent updates **is not an atomic snapshot** of all cells; do not use it to protect payment invariants that require an exact number at every instant.

There is no "best" primitive for every problem. If throughput increases but inconsistencies appear or snapshot properties are lost, the optimization has changed the business contract.

### 16.5 Virtual threads and monitor contention

In Java 21+, virtual threads can help a large number of I/O-waiting tasks without dedicating a fixed platform thread per task. However, **virtual threads do not turn one monitor into many monitors**: multiple virtual threads contending for the same `synchronized(lock)` still serialize inside the critical section, so lock contention and long hold times remain a logical bottleneck.

Scheduler implementation details, pinning, and optimizations related to `synchronized` have changed across JDK versions. When evaluating virtual thread performance, check the **specific JDK version and actual profiler data**, rather than applying a pinning conclusion from one JDK to all versions.

## 17. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Holding `synchronized` while making HTTP/database/file I/O calls. | Contenders on the same monitor wait for the I/O duration. | Prepare/snapshot under lock, do I/O outside lock, re-validate/commit per protocol. |
| Calling `Thread.sleep()` inside a critical section. | The thread sleeps while still holding the monitor. | Move sleep/waiting outside the lock if possible. |
| Calling `CountDownLatch.await()` or `Future.get()` while holding a monitor the worker needs. | Lock convoy or task-dependency deadlock. | Wait outside the locked region; review the dependency graph. |
| Invoking callbacks under a monitor when callbacks acquire other locks. | Lock-order inversion, deadlock, unpredictable latency. | Invoke callbacks after releasing the lock with an appropriate snapshot/ordering. |
| Using two different monitors for one invariant. | Mutual exclusion/visibility does not cover the full state. | Use a single owner lock or a proven multi-lock protocol. |
| Synchronizing only the writer while getters bypass the lock. | Readers may see intermediate state or lack happens-before. | Read snapshots under the same protocol. |
| Splitting check and update into two critical sections. | Another thread interleaves; quota oversubscription/lost update. | Re-check and commit within the same critical section. |
| Assuming `Thread.interrupt()` immediately cancels a `BLOCKED` thread waiting for a monitor. | Cancellation does not take effect as expected. | Use a primitive supporting interruptible/timed acquisition if needed. |
| Treating every `WAITING` thread as monitor contention. | Misdiagnosis of latches, futures, parks, or I/O. | Distinguish `BLOCKED` from other wait states; inspect stack/owner. |
| Assuming intrinsic monitor fairness is FIFO. | A contender may wait longer than expected. | Design a fairness policy with an appropriate primitive if required. |
| Adding new locks without load measurement or invariant checks. | Can reduce throughput or introduce new deadlocks. | Measure latency/contention, test correctness, review lock ordering. |

## 18. Checklist when a contended monitor is detected

1. **Identify lock identity.** Are the contending threads actually using the same monitor? Is it `this`, `Class`, or a private object?
2. **Identify the holder.** Which thread owns the lock? What is the holder's stack doing?
3. **Measure hold time and blocked time.** Is contention due to frequent operations or an unusually slow branch?
4. **Find blocking operations in the critical section.** Are there I/O calls, sleeps, joins, Futures, latches, callbacks, or nested locks?
5. **Write down the invariants.** Which fields/operations truly must stay together under the monitor? Do readers need a snapshot?
6. **Propose minimal scope.** Move local/immutable work outside, keeping state check + commit inside the lock.
7. **Review exceptions and cancellation.** Could a failing operation leave state half-updated or leave threads waiting indefinitely?
8. **Review lock ordering.** Do other call paths acquire locks in reverse order or invoke callbacks that acquire additional locks?
9. **Verify** with concurrency tests and before/after profiling under the same load.
10. **Change primitives only with good reason.** `ReentrantLock`, atomic state, or concurrent collections change contracts and require re-reviewing correctness.

## 19. Self-check questions

**1.** At which step is a thread that is `BLOCKED` waiting on `synchronized(lock)` typically stuck?  
**Answer:** At the step of acquiring the intrinsic monitor currently owned by another thread.

**2.** Does a holder thread calling `Thread.sleep(500)` inside `synchronized(lock)` release the monitor?  
**Answer:** No. `sleep` pauses the thread, but it still owns the lock.

**3.** Which locks does `Object.wait()` release on the lock object?  
**Answer:** It releases the monitor of the object being waited on, not other monitors currently held; upon returning from wait, it must reacquire that monitor.

**4.** Are two methods both marked `synchronized` guaranteed to contend for the same monitor?  
**Answer:** No. Instance `synchronized` locks `this`; static `synchronized` locks the `Class` object; two different instances have different monitors.

**5.** Why can `main` holding a lock and calling `join()` on a worker that needs the same lock cause a deadlock?  
**Answer:** `main` waits for the worker to finish, but the worker cannot acquire the lock held by `main`; `join()` does not automatically release `main`'s monitor.

**6.** Does calling `interrupt()` on a contender waiting for an intrinsic monitor guarantee it stops waiting immediately?  
**Answer:** No. Waiting to acquire an intrinsic monitor does not have the same interruptible acquisition semantics as `ReentrantLock.lockInterruptibly()`.

**7.** Is it safe to move a quota check outside `synchronized` while keeping the update inside the lock?  
**Answer:** No, not without re-checking under the lock; another thread can change the state between the check and the update.

**8.** Why doesn't a `ReentrantLock` by itself solve long contention?  
**Answer:** Because lock hold time still depends on the code inside. `ReentrantLock` adds timed/interruptible acquisition mechanisms; it does not automatically reduce hold time.

**9.** Does a thread dump showing 20 `BLOCKED` threads prove a deadlock?  
**Answer:** Not yet. You need to inspect the lock owner, the holder's execution path, progress over time, and any dependency cycle.

**10.** What must a critical-section optimization achieve?  
**Answer:** Preserve invariants, happens-before/visibility, and atomicity as before, while improving blocked time/latency/throughput measured under a suitable workload.

**Takeaway:** Monitor contention occurs when multiple threads want the same intrinsic lock. **Keep locks short, protect the right invariants, and do not wait on external work while holding a lock** are the core design principles. When you need timeout/cancellation at lock acquisition time, use a primitive with the appropriate contract; when investigating a slow application, distinguish `BLOCKED` from `WAITING` states and pinpoint the exact holder and monitor hold duration.
