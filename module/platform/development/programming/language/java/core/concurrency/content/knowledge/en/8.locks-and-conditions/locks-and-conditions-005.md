# Fairness Policy: Throughput and Starvation in Java Locks & Conditions

## 1. Why does the fairness policy affect concurrent applications?

When multiple threads want to enter a **critical section** at the same time, the lock decides which thread gets the right to proceed when the resource becomes available. If some threads are granted entry repeatedly while others have to wait for a very long time, the system may achieve good overall throughput, yet the experience of individual tasks becomes uneven.

In Java, `ReentrantLock`, `ReentrantReadWriteLock`, and `Semaphore` provide a **fairness** option. This is a policy about **the priority order for granting access under contention**, not a promise that every thread or every request will complete in equal time.

Three concepts need to be separated:

- **Fairness:** the degree to which the granting mechanism respects threads that were already waiting before a new thread arrives.
- **Throughput:** the number of tasks completed per unit of time, such as transactions/second or critical section entries/second.
- **Starvation:** a thread may have to wait unusually long or fail to make progress because other threads keep receiving the resource.

Key point: **stronger fairness can reduce throughput**, especially when many threads contend for a single lock and handing off ownership requires waking up threads and context switching. Conversely, an unfair configuration often takes advantage of the currently running thread continuing to acquire the lock, but can create very high tail latency for some waiters.

This lesson discusses only **pure Java** concurrency APIs and behavior, unrelated to framework configuration.

### Learning Outcomes

After this lesson, you should be able to:

1. Distinguish between `ReentrantLock(true)` and `ReentrantLock(false)`; understand that `fair` does not mean "strict FIFO".
2. Explain **barging**, lock convoy, starvation, and the trade-off between throughput and p95/p99 wait time.
3. Identify the important exception of `tryLock()` on a fair lock.
4. Understand how `Condition.await()`, `signal()`, `signalAll()`, and lock reacquisition relate to the fairness policy.
5. Distinguish lock fairness from the fairness of `Semaphore` and `ReentrantReadWriteLock`.
6. Write runnable Java 17+ code, and know how to design benchmarks/tests instead of drawing conclusions from a single scheduler observation.

## 2. Where do fair and nonfair actually differ?

### 2.1. Nonfair lock: allows barging

With `new ReentrantLock()` or `new ReentrantLock(false)`, the lock is **nonfair** by default. A newly arriving thread can acquire the lock even if other threads are already waiting, depending on the state and lock-granting implementation. The behavior where a later-arriving thread jumps ahead of a waiter is commonly called **barging**.

This sometimes benefits throughput: a thread already running on the CPU can acquire the lock immediately instead of having to wake a sleeping thread and wait for it to be scheduled. Context switching, cache locality, and scheduling overhead can be reduced.

However, if many "newcomers" continuously win ownership, a specific waiter can wait for a very long time. The higher the contention, the greater the risk that measuring only average transactions hides massive latency for the unlucky group of waiters.

### 2.2. Fair lock: prioritizes the longest-waiting waiter

`new ReentrantLock(true)` requests a fair policy. According to the API contract, under contention, a fair lock **favors granting access to the longest-waiting thread**. This policy helps reduce the chance that a thread waiting for the lock is repeatedly bypassed by later-arriving threads.

Even so, the Java documentation notes very clearly: **fairness of locks does not guarantee fairness of thread scheduling**. One thread may be granted the lock many times during a period while another thread has not yet been scheduled on the CPU; waiting for the lock is only one part of a task's lifecycle.

A fair lock also does not force two threads to **start** in the exact order they were created, `start()`ed, or enqueued as tasks. The policy applies at lock contention points according to the contract, rather than creating a global ordering across the entire application.

### 2.3. High-level comparison

| Criterion | Nonfair `ReentrantLock` | Fair `ReentrantLock(true)` |
| --- | --- | --- |
| Default of `ReentrantLock()` | Yes | No |
| Barging with `lock()` when waiters exist | Possible | Generally yields priority to longest-waiting waiter |
| Typical goal | High throughput in contended workloads | Reduce variance in lock acquisition wait time |
| Tail latency of a waiter | Can be very bad | Generally easier to bound, no absolute deadline |
| Context switching / handoff | Can be more economical | Can be more expensive under heavy contention |
| Eliminates deadlock | No | No |
| Protects shared mutable state if all access paths use the same lock | Yes | Yes |
| Guarantees fair CPU scheduling | No | No |

When there is **little or no contention**, enabling fairness may produce no observable benefit; only when the workload genuinely has many waiters does this policy become an operational consideration worth weighing.

## 3. Configuring and observing fairness with ReentrantLock

Declaration:

~~~java
// Configuration illustration; this snippet is not a standalone program.
ReentrantLock defaultLock = new ReentrantLock();
ReentrantLock explicitlyNonfair = new ReentrantLock(false);
ReentrantLock fairLock = new ReentrantLock(true);

System.out.println(defaultLock.isFair());       // false
System.out.println(explicitlyNonfair.isFair());  // false
System.out.println(fairLock.isFair());           // true
~~~

`isFair()` reports **the configured policy**, not how many times each thread was granted the lock or confirmation that latency is fair. To evaluate effectiveness, you must measure wait time, hold time, throughput, timeout/rejection counts, and overall latency.

### 3.1. Example 1 — multiple threads using a fair lock (Java 17+)

The following example verifies the shared update result and shows where fairness is configured. It intentionally **does not assert the order in which threads enter the lock**: that order can vary depending on the scheduler.

Create the file `FairCounterDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class FairCounterDemo {
    static final class Counter {
        private final ReentrantLock lock;
        private int value;

        Counter(boolean fair) {
            lock = new ReentrantLock(fair);
        }

        void increment() {
            lock.lock();
            try {
                value++;
            } finally {
                lock.unlock();
            }
        }

        int value() {
            lock.lock();
            try {
                return value;
            } finally {
                lock.unlock();
            }
        }

        boolean isFair() {
            return lock.isFair();
        }
    }

    public static void main(String[] args) throws Exception {
        Counter counter = new Counter(true);
        ExecutorService executor = Executors.newFixedThreadPool(4);
        CountDownLatch start = new CountDownLatch(1);
        Future<?>[] tasks = new Future<?>[4];

        try {
            for (int i = 0; i < tasks.length; i++) {
                tasks[i] = executor.submit(() -> {
                    try {
                        start.await();
                        for (int j = 0; j < 1000; j++) {
                            counter.increment();
                        }
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            start.countDown();
            for (Future<?> task : tasks) {
                task.get();
            }

            System.out.println("fair = " + counter.isFair());
            System.out.println("count = " + counter.value());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac FairCounterDemo.java
java FairCounterDemo
~~~

Stdout when tasks are not interrupted and complete normally:

~~~text
fair = true
count = 4000
~~~

Four workers wait together for the latch to open, and each worker increments the counter 1,000 times. `ReentrantLock` protects the `value++` operation so the total is 4,000. `isFair()` is `true` because the constructor selects the fair policy. `Future.get()` lets the caller wait for each task to finish and receive an error if a task fails with an unhandled exception.

**What the example does not prove:** It does not measure whether a fair lock is faster or slower than a nonfair lock, does not prove that a specific thread is granted the lock first, and does not show the tail latency of waiters. Replacing `Counter(true)` with `Counter(false)` still produces a total of 4,000 as long as the same lock protects every update; the difference lies in **the contention policy**, not in the correctness of the locked count.

If a task is interrupted during `start.await()`, it restores the interrupt flag and skips the increment loop; therefore, the "tasks complete normally" condition for the output also includes having no external cancellation/interrupt. In production code, you should explicitly decide how to report failure when a task is canceled rather than silently skipping the work.

### 3.2. Why must unlock be in finally?

~~~java
// Illustration inside a method; lock has already been declared.
lock.lock();
try {
    mutateSharedState();
} finally {
    lock.unlock();
}
~~~

Fairness does **not** help if a thread acquires the lock and exits via an exception without releasing it. `ReentrantLock` does not automatically unlock when leaving a method like `synchronized` does. You need `finally`, and you should avoid holding the lock across unbounded I/O, uncontrolled callbacks, or long sleeps.

## 4. An exception to remember: tryLock() can barge even on a fair lock

An important misconception is assuming that `new ReentrantLock(true)` makes **every way of acquiring the lock** follow the queue.

In reality, according to the `ReentrantLock` contract:

- `lock()` on a fair lock applies the waiter-priority policy under contention.
- `lockInterruptibly()` allows interruptible waiting while still respecting the lock's fair policy.
- `tryLock()` **with no timeout** acquires the lock immediately if it is available, **even if other threads are waiting**—meaning it allows **barging even when the lock is configured as fair**.
- `tryLock(timeout, unit)` on a fair lock honors the fairness policy when waiting to acquire the lock and can be interrupted.
- According to the API documentation, `tryLock(0, TimeUnit.SECONDS)` can be used when you want an immediate attempt that still honors fairness, unlike the no-argument `tryLock()`. Note that the timed overload can throw `InterruptedException`.

This matters if your code uses `lock()` on the main path and the no-argument `tryLock()` on another path: the fast-try path can jump ahead of waiters already lined up in the queue. You should not claim "no starvation because the lock is fair" if the application still has barging paths.

### Example 2 — tryLock without blocking indefinitely (Java 17+)

Create the file `TryLockWaitDemo.java`:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class TryLockWaitDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ReentrantLock lock = new ReentrantLock(true);
        lock.lock(); // The main thread holds the lock.

        try {
            Thread worker = new Thread(() -> {
                boolean immediate = lock.tryLock();
                System.out.println("immediate = " + immediate);

                if (immediate) {
                    lock.unlock();
                }

                try {
                    boolean timed =
                        lock.tryLock(50, TimeUnit.MILLISECONDS);
                    System.out.println("timed = " + timed);

                    if (timed) {
                        lock.unlock();
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    System.out.println("interrupted");
                }
            }, "contender");

            worker.start();
            worker.join();
        } finally {
            lock.unlock();
        }
    }
}
~~~

Compile and run:

~~~bash
javac TryLockWaitDemo.java
java TryLockWaitDemo
~~~

Typical stdout when the worker is not interrupted:

~~~text
immediate = false
timed = false
~~~

Because `main` holds the lock until **after** `worker.join()`, the worker cannot acquire the lock from another thread: `tryLock()` returns false immediately, while `tryLock(50, MILLISECONDS)` waits up to approximately the requested duration and then returns false. The timed call does not guarantee an exact 50 ms wall-clock wait.

This example demonstrates **controlled failure handling**, not a race among waiters. It does not directly illustrate barging, because when the worker tries, the lock is not free. To study barging, you need to test execution schedules where waiters are already queued, measure acquisition order, and accept that the outcome of a single run is non-deterministic.

### 4.1. tryLock does not guarantee forward progress on its own

When `tryLock` returns false, the work has not been performed. If code keeps retrying in a tight busy loop, some threads can consume CPU without making progress, creating fresh contention or livelock. You need to choose backoff, retry limits, deadlines, a queue, or an appropriate blocking approach.

When multiple locks must be acquired together, `tryLock` can help **release already-held locks** if the next lock cannot be acquired; however, you still need consistent lock ordering or a proper coordination protocol to avoid deadlock, livelock, and starvation.

## 5. How does starvation differ from deadlock and livelock?

| Phenomenon | Description | Example |
| --- | --- | --- |
| **Starvation** | A task fails to get a resource for a long time even though other work continues to complete | A waiter is repeatedly barged past by new tasks |
| **Deadlock** | A group of tasks wait on each other in a cycle, and none can release the needed dependency | A holds lock 1 and waits for 2; B holds 2 and waits for 1 |
| **Livelock** | Tasks continuously react/yield to each other without completing useful work | Two threads repeatedly call tryLock and retry in lockstep |
| **Long blocking** | A task waits a very long time because the owner holds the resource for too long | The holder performs blocking I/O inside the critical section |
| **Priority inversion** | A high-priority task must wait for a resource held by a low-priority task | High priority waits on lock; low priority is not scheduled to release it |

You can have starvation **without deadlock**: a set of tasks keeps completing while task X keeps waiting. A fair lock helps reduce the risk of starvation **caused by lock-granting order**, but it does not solve CPU scheduling starvation, deadlock from holding multiple locks, thread pool worker starvation, or a task holding a lock for too long.

There is also no proof of "absolute zero starvation" solely from `isFair() == true`. If a worker has never been scheduled by the CPU to reach `lock()`, it is not even in the lock wait queue in the relevant sense. If the owner never releases, waiters still wait regardless of policy.

## 6. Throughput, latency, and lock convoy

### 6.1. Why is nonfair often faster under heavy contention?

In a workload with short critical sections, many active threads, and a queue of waiters:

1. Thread X releases the lock.
2. A waiting thread Y needs to be woken up and scheduled by the CPU.
3. Meanwhile, thread Z, which is already running on the CPU, wants to acquire the lock.

With a nonfair policy, Z can acquire the lock immediately if it sees the lock is free. Utilizing the already-running thread can reduce scheduler waiting and avoid some context switches.

With a fair policy, prioritizing the waiting waiter may require waiting for Y to make progress. If Y has not yet been scheduled on the CPU, threads that are ready to run may have to wait. In some systems, a **lock convoy** (threads lining up to be served sequentially) causes throughput to drop.

However, "often" is an empirical tendency, **not a law for every workload**. In workloads with low contention, where most time is spent in I/O, or under different CPU scheduling policies, results can differ. Only benchmarking in a representative environment can determine the actual trade-off.

### 6.2. Don't measure only completed task count

One configuration might produce 20,000 operations/second while some tasks wait several seconds to acquire the lock. Another configuration might handle 18,000 operations/second while drastically reducing waiter tail wait times.

Metrics to observe:

| Metric | Question |
| --- | --- |
| Throughput (ops/s) | How many operations does the system complete per second? |
| Lock wait p50/p95/p99 | How long do a typical waiter and the slowest waiters wait? |
| Max wait / timeout rate | Are any tasks being starved or exceeding deadlines? |
| Critical-section hold time | How long does the owner hold the lock? Is there I/O or blocking inside the lock? |
| Active waiters / queue length | How many threads are contending? |
| CPU/context switching | Is scheduler overhead overshadowing useful work? |
| GC/allocations | Is work inside the locked region creating memory pressure? |
| Per-thread completion distribution | Are some threads granted access significantly less often? |

High throughput with spiking p99 may be unsuitable for interactive tasks; conversely, a batch job needing maximum aggregate speed may tolerate individual wait-time variance if there are no strict fairness constraints.

### 6.3. Can fairness increase average latency?

Yes. If the handoff policy adds overhead and all tasks are short, the total time per lock entry can increase. At the same time, eliminating extreme waits can **improve the latency distribution**. You need to look at average, tail latency, and deadline misses together; there is no guarantee that fair always improves p99 in every environment.

Shortening lock hold times, eliminating unnecessary locks, partitioning state, using immutable snapshots, or using message passing sometimes yields larger gains than debating fair vs. nonfair. However, optimizations must never break shared data invariants.

## 7. Condition: being signaled does not mean running immediately

A `Condition` is typically created from `ReentrantLock.newCondition()`, separating a **business-condition** wait queue from waiting for **lock ownership**.

Basic flow:

1. A thread holds the lock and sees that the condition is not yet met.
2. It calls `condition.await()`, **temporarily releasing the lock** and starting to wait for a signal.
3. Another thread acquires the lock, updates the state, and calls `signal()` or `signalAll()`.
4. The awakened thread **must reacquire the lock** before `await()` returns and it resumes checking the state.

**Signaling does not directly hand the lock to the waiter**, and there is no guarantee that the waiter will be scheduled on the CPU immediately after `signal()`. The current owner still holds the lock until it unlocks, and other threads may also be contending.

Per the `ConditionObject` contract of `ReentrantLock`, waiters are signaled in FIFO order on the condition queue, but **reacquiring the lock** is governed by the associated lock's acquisition policy. With a fair lock, threads contending after a signal follow the lock's wait-priority policy; that still does not create a hard deadline or a scheduler guarantee.

### Example 3 — condition and checking with while (Java 17+)

Create the file `ConditionSignalDemo.java`:

~~~java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionSignalDemo {
    static final class Gate {
        private final ReentrantLock lock = new ReentrantLock(true);
        private final Condition openCondition = lock.newCondition();
        private boolean open;

        void awaitOpen() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (!open) {
                    openCondition.await();
                }
            } finally {
                lock.unlock();
            }
        }

        void open() {
            lock.lock();
            try {
                open = true;
                openCondition.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Gate gate = new Gate();

        Thread waiter = new Thread(() -> {
            try {
                gate.awaitOpen();
                System.out.println("Gate opened");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                System.out.println("Wait interrupted");
            }
        }, "gate-waiter");

        waiter.start();
        gate.open();
        waiter.join();
    }
}
~~~

Compile and run:

~~~bash
javac ConditionSignalDemo.java
java ConditionSignalDemo
~~~

When the waiter is not interrupted, stdout is:

~~~text
Gate opened
~~~

Even though `gate.open()` may run **before** the waiter enters `await()`, the program remains correct because the `open` state is stored and checked under the same lock. If `open` is already true, the waiter does not wait and does not depend on whether it "received a signal".

`while (!open)` is mandatory as a design pattern: `Condition` allows **spurious wakeups**, and the state can change between the signal and the moment the waiter reacquires the lock. Using a plain `if` could allow the waiter to proceed even when the condition is no longer true.

`signal()` wakes only one eligible waiter; `signalAll()` wakes all of them, which can sometimes create heavy contention as many threads simultaneously try to reacquire the lock. Choose based on your invariants and how many waiters can make progress, not on the assumption that `signalAll` is always "more fair".

### 7.1. Can waiting on a Condition starve?

Yes. Even when the lock is fair, a task may never receive the appropriate signal, or its predicate may repeatedly become false before it reacquires the lock. Lock fairness does not replace condition coordination logic and does not guarantee business completion order.

You must evaluate:

- Can the wait condition ever become true?
- Do all relevant state transitions signal the right condition?
- Is `signalAll` needed because different waiters have different predicates?
- Are there timeouts/cancellations to handle prolonged waiting?
- Can any thread hold the lock too long or be starved by the scheduler?

Those questions are separate from enabling `new ReentrantLock(true)`.

## 8. How does Semaphore fairness differ from Lock fairness?

`Semaphore` manages a number of **permits**. For example, a semaphore with three permits allows at most three operations to hold permits concurrently, commonly used to limit concurrency accessing an external resource.

~~~java
// Illustration, not a standalone program.
Semaphore permits = new Semaphore(3, true);

permits.acquire();
try {
    accessLimitedResource();
} finally {
    permits.release();
}
~~~

You need to import `java.util.concurrent.Semaphore` and handle `InterruptedException` for `acquire()`. With `fair=true`, the semaphore applies FIFO ordering at **specific internal queuing points** under contention. Do not simply assume "the thread that calls `acquire` first is guaranteed to get a permit first", because the actual order depends on which thread reaches that internal point first.

**Similar exception to locks:** the no-argument `Semaphore.tryAcquire()` can take an available permit **even if waiters are ahead of it**, even when the semaphore is configured as fair. `tryAcquire(0, TimeUnit.SECONDS)` honors fairness under contention and can throw `InterruptedException`.

`Semaphore` has no owner constraint like `ReentrantLock`; one thread can `release()` a permit acquired by another thread, so permit acquisition/release logic must be especially careful to avoid over-releasing. Enabling fair does not fix incorrect releases.

### Example 4 — limiting work with a fair semaphore (Java 17+)

Create the file `FairSemaphoreDemo.java`:

~~~java
import java.util.concurrent.Semaphore;

public class FairSemaphoreDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Semaphore slots = new Semaphore(2, true);

        slots.acquire(2);
        System.out.println("available = " + slots.availablePermits());

        slots.release();
        System.out.println("available = " + slots.availablePermits());

        slots.release();
        System.out.println("fair = " + slots.isFair());
        System.out.println("available = " + slots.availablePermits());
    }
}
~~~

Compile and run:

~~~bash
javac FairSemaphoreDemo.java
java FairSemaphoreDemo
~~~

Stdout:

~~~text
available = 0
available = 1
fair = true
available = 2
~~~

This example illustrates the API and that permits are tracked accurately by count; because there is no contention between multiple threads, it does **not** prove that the fair policy changes service order or throughput. When benchmarking a semaphore, measure both permit wait latency and utilization of the protected resource.

## 9. Fairness of ReentrantReadWriteLock

`ReentrantReadWriteLock` separates a **read lock** (allowing multiple readers to hold it simultaneously when not blocked by a writer according to policy) and a **write lock** (excluding access from other readers and writers).

- **Nonfair** is the default; it does not enforce arrival-order priority and can cause some readers or writers to be delayed for a very long time under continuous contention.
- **Fair** (`new ReentrantReadWriteLock(true)`) applies a policy that favors approximate arrival order: either the longest-waiting single writer or the longest-waiting group of readers is served according to the JDK policy. It does not require every read/write to always complete in strict global order.
- The no-argument `readLock().tryLock()` and `writeLock().tryLock()` methods **do not honor fairness**, similar to `ReentrantLock.tryLock()`.
- Fairness does not turn read/write lock hold times into bounded durations; a writer can still wait on a reader holding the lock for a long time, or a reader can be delayed/timed out by other factors.

Read-heavy, write-light workloads do not automatically mean a read-write lock is faster than a `ReentrantLock`; you need to consider how many readers actually run in parallel, critical section length, lock overhead, and the risk of writer waiting.

`ReentrantReadWriteLock.WriteLock` supports `newCondition()`; `ReadLock.newCondition()` does not and throws `UnsupportedOperationException`. Conditions on the write lock also do not automatically provide fairness for business predicates.

## 10. What problems does a fair policy NOT fix?

### 10.1. Deadlock from multi-lock acquisition order

A fair lock only decides the order **among threads waiting on that same lock**. It does not eliminate wait cycles:

~~~text
Thread A: holds L1 -> waits for L2
Thread B: holds L2 -> waits for L1
~~~

Even if both L1 and L2 are configured as fair, they can still deadlock. You must use consistent lock ordering, reduce lock nesting, or use another cycle-avoidance protocol.

### 10.2. Holding locks for too long

If a thread performs a network query, sleeps, or does slow file I/O inside a critical section, waiters still wait until the owner releases the lock. Fairness does not force an owner to yield the lock on a time slice. Measure lock hold times and move long blocking operations outside the locked region whenever preserving invariants allows.

### 10.3. Thread pool starvation

In an executor with only one worker, if running task A submits task B to the same pool and waits on `B.get()`, it can cause task-dependency deadlock/starvation. Enabling fair on a lock used by the task does not create an extra worker for B.

### 10.4. CPU scheduler, priority, and external resources

Lock fairness does not control the CPU scheduler order, OS priority policies, database connections, API rate limits, or disk speed. Those bottlenecks require their own management measures: backpressure, timeouts, bounded queues, capacity planning, etc.

### 10.5. Correctness of shared data

Both fair and nonfair locks provide mutual exclusion and memory visibility when used properly. A code path that reads state outside the lock can still be wrong even if the lock is fair. Choosing fairness **does not fix data races** or broken invariants.

## 11. How to use queues, wait times, and state observation?

`ReentrantLock` provides methods such as `hasQueuedThreads()`, `hasQueuedThread(thread)`, `getQueueLength()`, and `isFair()`. They are useful for **monitoring and diagnostics**, but queue state can change immediately after being read. `getQueueLength()` is an **estimate**, not an exact transactional metric or a basis for deciding whether a compound operation is safe.

Metrics to record should be tied to tasks:

- Timestamp immediately before `lock()` and immediately after acquire to compute wait time.
- Timestamp at acquire and release to compute lock hold time.
- Timestamp at task entry and completion to compute end-to-end latency.
- Timeout/interrupt/retry counts, broken down by task type or pool.
- Queue depth and context switching at the diagnostic level.

Do not log on every lock acquisition on a hot path if logging itself becomes a bottleneck or distorts the benchmark's latency distribution.

### 11.1. Pattern for measuring wait time with System.nanoTime

~~~java
// Illustration placed inside a method where lock and recorder are already initialized.
long started = System.nanoTime();
lock.lock();
long acquired = System.nanoTime();
try {
    performCriticalWork();
} finally {
    long released = System.nanoTime();
    lock.unlock();
    recorder.recordWaitNanos(acquired - started);
    recorder.recordHoldNanos(released - acquired);
}
~~~

This is illustrative code, **not a standalone program**. `System.nanoTime()` is suitable for measuring elapsed intervals within the same JVM; `recorder` must be low-overhead and thread-safe. To prevent recorder errors from interfering with lock release, you can measure inside the critical section and **record metrics after unlocking**, or ensure the recorder neither throws exceptions nor blocks.

In the illustration above, `released` is captured before `unlock()`, so it is an estimate of lock hold time and does not measure the full release cost; a production recorder should be consistent in how it measures and verify its overhead.

## 12. Benchmarking fair vs. nonfair properly

### 12.1. Benchmark design checklist

Do not compare by running once and printing `System.currentTimeMillis()`. Java has JIT compilation, GC, OS scheduling, CPU frequency scaling, and many sources of environmental noise. For a serious benchmark:

1. **Choose a representative workload:** worker count, read/write ratio, critical section length, contention level, I/O cost, and core count.
2. **Use the exact same business logic:** change only the fair/nonfair policy while keeping the pool, input data, timeouts, task count, and environment constant.
3. **Warm-up and multiple measurement iterations:** to reduce JIT bias and short-term fluctuations.
4. **Measure both throughput and latency:** p50/p95/p99 wait time, per-thread completion, max wait, and deadline misses.
5. **Verify correctness:** all work completes, data invariants are preserved, and no exceptions are swallowed.
6. **Avoid creating measurement bottlenecks:** synchronous logging, a locked recorder, or object allocation inside the measurement can mask the effect being tested.
7. **Distinguish CPU-bound from I/O-bound:** context switching and lock hold times can behave very differently.
8. **Do not assume a single conclusion:** fair locks often increase overhead under contention, but the throughput drop and wait-time distribution benefit depend on the workload.

JMH is a common benchmarking tool in the Java ecosystem. When benchmarking long-term starvation risk, include tests with continuously contending queues/waiters and report wait-time distributions rather than only aggregate throughput.

### 12.2. How to read a hypothetical result

Suppose two configurations are measured on the same workload:

| **Hypothetical** metric | Nonfair | Fair |
| --- | ---: | ---: |
| Throughput | 42,000 ops/s | 35,000 ops/s |
| p99 lock wait | 18 ms | 8 ms |
| Observed max wait | 250 ms | 42 ms |

These are **illustrative numbers for reading the table only**, not an actual benchmark, nor do they reflect any specific JVM or hardware. If the goal prioritizes total operation count, nonfair may be attractive. If individual tasks have deadlines, the fair wait-time distribution may be more suitable.

However, if the application has a task that occasionally holds the lock for 2 seconds, switching to fair will **not** fix that bottleneck on its own. Optimizing the lock-holding path can matter more than changing the acquisition policy.

## 13. Common mistakes

**"A fair lock guarantees that whichever thread calls `lock()` first enters first."** Not necessarily. Two threads can be scheduled differently by the CPU; the fair policy applies under contention and waiting, and does not let you infer order from thread creation or task submission time.

**"Enabling fairness guarantees zero starvation."** False for CPU scheduling, owners that never release, un-signaled conditions, external resources, and paths using barging `tryLock()`.

**"`tryLock()` on a fair lock always respects FIFO."** False: the no-argument overload can barge. When you need a non-blocking attempt that still honors fairness, consider the zero-timeout overload and handle interruption.

**"Nonfair locks are always faster."** There is no guarantee for all workloads; you must measure contention, throughput, and latency for your actual application.

**"Fairness solves deadlocks."** No. Multi-lock acquisition ordering and resource wait cycles are a different problem from waiter ordering on a single lock.

**"`signal()` immediately hands the lock to the waiter."** No. The waiter only proceeds after reacquiring the lock; always check the condition in a `while` loop.

**"Using `signalAll()` is fairer."** `signalAll` can trigger a large burst of contention, waking many waiters only for them to wait again; choose based on predicates and liveness requirements.

**"Queue length of 0 means no contention."** `getQueueLength()` is only an estimate at a point in time; the state can change immediately after reading.

**"A single 4-thread run proves fair/nonfair has better performance."** No. You need multi-iteration benchmarks, controlled conditions, and distribution metrics, not conclusions from incidental log ordering.

**"Enabling fair fixes non-thread-safe code."** Fairness is only a lock-granting policy; code reading or writing outside the locking protocol can still be wrong.

## 14. Policy selection guide

| Problem | Priority | Initial suggestion |
| --- | --- | --- |
| Many very short operations, throughput is primary | Aggregate throughput, lock contention | Start with default nonfair, measure wait times |
| Many similar tasks, each with a deadline | p95/p99 and starvation risk | Evaluate fair while measuring throughput |
| Low contention | Simplicity, correctness | Nonfair is usually enough; fairness may not matter |
| Many readers, few writers | Read/write contention | Measure `ReentrantReadWriteLock` and writer wait risk |
| Limiting external resources outside the JVM | Permit queue and overload | `Semaphore` with or without fair, depending on SLA |
| Condition with multiple predicates | Predicate/liveness | Design `await`/`signal` properly; fairness only helps reacquire |
| Multiple locks held simultaneously | No deadlock | Consistent lock ordering before optimizing fairness |
| Tasks blocked by pool or I/O | Capacity/deadline | Fix the bottleneck; lock fairness is not enough |

A practical approach is to start from **correctness** and **invariants**, measure contention and wait requirements, and then choose fair when there is evidence of starvation or tail latency worth addressing. Do not rush to enable fair just because one thread looks slow: the root cause may be lock hold time, the executor, or a downstream dependency.

## 15. Self-check questions

**1.** Does `new ReentrantLock(true)` guarantee that task A finishes before task B if A is submitted first?

No. Submission order, scheduling order, reaching the lock call, lock hold duration, and work after the critical section are all separate orders. Fairness primarily governs lock acquisition priority when waiters exist.

**2.** A fair `ReentrantLock` has a queue of waiters. A new thread calls `tryLock()` right as the lock becomes free. Can it jump the queue?

Yes. The no-argument `tryLock()` can barge even when the lock is configured as fair. The timed overload on a fair lock has different fairness semantics.

**3.** Does fairness fix a deadlock where A holds L1 waiting for L2 and B holds L2 waiting for L1?

No. That is a multi-lock wait cycle; you need a shared lock ordering or another protocol to avoid circular wait.

**4.** Does `condition.signal()` make the waiter immediately execute the code after `await()`?

No. The waiter must reacquire the lock before `await()` returns; the current owner may still hold the lock, and the scheduler decides when the thread runs.

**5.** Why should you measure both throughput and p99 lock wait?

Throughput describes total completed operations; p99 shows how much latency the slow group of waiters can experience. A configuration that is faster overall can still perform poorly for tasks with deadlines.

**6.** Does simply choosing `Semaphore(3, true)` guarantee that three requests will finish in the exact order they were received?

No. Fairness applies at internal permit acquisition points; being granted a permit does not mean equal execution time, and the no-argument `tryAcquire()` can barge.

**Key takeaway:** **Fairness is an access-granting policy under contention**, not a promise about the CPU scheduler or completion deadlines. A fair lock often helps reduce the risk of a waiter being repeatedly jumped in line, at the possible cost of lower throughput. Use the right API overloads, keep critical sections short, design conditions properly, and measure both overall performance and per-task-group wait times.
