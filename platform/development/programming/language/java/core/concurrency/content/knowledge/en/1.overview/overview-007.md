# Safety, liveness, progress, and starvation in Java Concurrency

When multiple threads access shared state concurrently, a program can **produce incorrect results** or **never complete its work**. These two classes of problems must be evaluated separately: *safety* asks whether anything bad can happen; *liveness* asks whether the good things that need to happen can continue to happen. *Progress* describes an algorithm's progress guarantee; *starvation* describes a situation where a thread/task waits indefinitely even though the system as a whole keeps making progress.

This lesson applies to **Java concurrency in general**: the Java Memory Model, threads, intrinsic locks, `java.util.concurrent`, atomic operations, and coordination algorithms. Spring-specific integration mechanisms are out of scope.

## 1. Distinguishing the four core concepts

| Concept | Question to answer | Example |
| --- | --- | --- |
| **Safety** | Can any forbidden state or result occur? | An account balance must not go negative; each job is processed only once. |
| **Liveness** | Under appropriate progress assumptions, does the work have a chance to eventually complete? | A waiting thread can be woken up; requests do not hang forever. |
| **Progress** | Under contention, at what level does the algorithm guarantee progress for the system as a whole or for each thread? | Lock-free guarantees system-wide progress in the algorithmic model; wait-free has a bounded number of steps per invocation. |
| **Starvation** | Can a specific task go unserved indefinitely even while other tasks continue running? | A thread repeatedly loses lock or CAS contention. |

**Safety** is typically expressed using an *invariant*: a condition that must hold in every valid observable state. For example, if two threads each withdraw one unit of money from an account with a balance of `1`, after valid processing there must be at most one successful withdrawal and the balance must remain non-negative. Simply checking `balance > 0` before subtracting is insufficient if another thread can interleave between the check and the subtraction.

**Liveness** is a temporal property: work must be able to make progress, usually stated under assumptions such as threads continuing to be scheduled by the CPU, resources eventually being released, and threads not being permanently halted. No Java algorithm on its own can guarantee that the operating system will grant CPU time to a thread that is permanently starved by the scheduler.

**Progress** is typically a guarantee proven at the algorithmic level within an execution model. A program can preserve safety without having liveness; for example, a lock is held properly so data is never corrupted, but the thread holding the lock never releases it. Conversely, all threads appearing to run very fast does not prove safety if data updates are subject to a race condition.

**Starvation** is a per-task issue. The overall system may still achieve high throughput, yet one specific thread makes no progress. Therefore, "system-wide progress" does not mean "every thread completes."

## 2. Safety: protecting invariants, not just individual variables

### 2.1 Race conditions and compound operations

Consider the following operations:

```java
if (balance.get() > 0) {
    balance.decrementAndGet();
}
```

Even though `balance` is an `AtomicInteger`, the read, comparison, and decrement are **three separate steps**. Two threads can both read a positive balance and then both decrement it. Each `decrementAndGet()` call is atomic, but the overall business condition "only decrement when funds remain" is not atomic. This is a *check-then-act* bug.

Three concerns are often conflated:

- **Atomicity:** can another thread interleave in the middle of a critical operation or state transition?
- **Visibility:** do other threads see the new write?
- **Ordering:** which operations can the JVM/compiler/CPU reorder, and which *happens-before* relationships constrain what can be observed?

In the Java Memory Model, `volatile` provides the visibility/ordering guarantees needed for the corresponding reads and writes, but `volatile int count` with `count++` can still lose updates because `++` is a read–modify–write operation. A `synchronized` block used consistently for all reads and writes of the related state, or a CAS operation on `AtomicInteger`, can preserve the appropriate invariant. Never use two different locks for the same invariant and assume synchronization is correct.

### 2.2 Java 17+ example: safety violation and fixing it with CAS

Create `SafetyLivenessDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class SafetyLivenessDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger unsafeBalance = new AtomicInteger(1);
        CountDownLatch bothChecked = new CountDownLatch(2);
        CountDownLatch startDecrement = new CountDownLatch(1);

        Runnable unsafeWithdraw = () -> {
            if (unsafeBalance.get() > 0) {
                bothChecked.countDown();
                try {
                    startDecrement.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                unsafeBalance.decrementAndGet();
            } else {
                bothChecked.countDown();
            }
        };

        Thread first = new Thread(unsafeWithdraw, "unsafe-1");
        Thread second = new Thread(unsafeWithdraw, "unsafe-2");
        first.start();
        second.start();
        bothChecked.await();
        startDecrement.countDown();
        first.join();
        second.join();

        AtomicInteger safeBalance = new AtomicInteger(1);
        AtomicInteger successfulWithdrawals = new AtomicInteger();
        Runnable safeWithdraw = () -> {
            while (true) {
                int current = safeBalance.get();
                if (current <= 0) {
                    return;
                }
                if (safeBalance.compareAndSet(current, current - 1)) {
                    successfulWithdrawals.incrementAndGet();
                    return;
                }
            }
        };

        Thread third = new Thread(safeWithdraw, "safe-1");
        Thread fourth = new Thread(safeWithdraw, "safe-2");
        third.start();
        fourth.start();
        third.join();
        fourth.join();

        System.out.println("Unsafe balance: " + unsafeBalance.get());
        System.out.println("Safe balance: " + safeBalance.get());
        System.out.println("Successful safe withdrawals: "
                + successfulWithdrawals.get());
    }
}
```

Compile and run:

```bash
javac SafetyLivenessDemo.java
java SafetyLivenessDemo
```

Output:

```text
Unsafe balance: -1
Safe balance: 0
Successful safe withdrawals: 1
```

**Why is the first result deterministic?** `CountDownLatch` forces both threads to complete the `> 0` check before either thread is allowed to decrement the balance. Since both read the initial value `1`, each thread decrements by one: `-1`. The latch only serves to reproduce the race; it is not a fix for the invariant.

In the safe branch, `compareAndSet(current, current - 1)` performs a conditional state transition as a single atomic operation. If another thread has already changed the balance, the CAS fails and the loop reads again. Starting from `1`, only one thread can transition it to `0`; the other thread observes `0` and returns. `join()` ensures the main thread waits for the worker threads to finish before printing the results.

The CAS loop here solves **safety** for a single balance variable. It does not by itself prove that a specific thread will succeed within a bounded number of steps under sustained contention. If an invariant spans multiple variables or resources, design a shared synchronization protocol, use a lock with the appropriate scope, or use a data structure with a suitable atomic contract. You cannot make a multi-step business operation atomic merely by replacing every field with `AtomicInteger`.

### 2.3 Linearizability and linearization points

A concurrent invocation is *linearizable* if each operation can be viewed as taking effect at a single point in time between its call and its return, while respecting the real-time order of non-overlapping invocations. In the safe withdrawal example, the successful CAS is the linearization point of the balance-decrement operation.

Linearizability is a useful safety criterion for concurrent APIs; it **does not guarantee liveness or fairness**. A data structure can return correct responses for every completed call while still leaving some other calls waiting indefinitely.

## 3. Liveness: does work keep making progress?

Failure modes to distinguish:

| Phenomenon | What happens? | Symptoms |
| --- | --- | --- |
| **Deadlock** | A set of threads has a circular dependency on resources or events that each other must release. | Threads wait for locks forever; no thread in the wait cycle advances. |
| **Livelock** | Threads keep changing state/running, but continuously react to each other without doing useful work. | CPU is active, retry counts climb, and successful task completions do not increase. |
| **Starvation** | A specific thread is repeatedly bypassed while other threads are able to make progress. | Latency of one task grows without bound; overall throughput may still look good. |
| **Unbounded blocking** | Waiting on a condition, I/O, or synchronous operation with no guaranteed timeout or exit path. | Hanging requests, prolonged `await()`, `take()`, or lock acquisition. |

**Classic deadlock:** thread A holds lock `L1` and needs `L2`; thread B holds `L2` and needs `L1`. Each thread waits for a lock held by the other. Safety of the locked data may remain intact, but liveness fails.

**Classic livelock:** two tasks yield to each other in lockstep and both immediately retry, so neither ever gets through. A retry policy with appropriate backoff and jitter can reduce the likelihood of synchronized loops; bounds/timeouts and an evaluation of the actual logic are still required.

**Classic starvation:** a low-priority thread, a request at the back of an unfair queue, or a CAS contender that repeatedly fails because other threads always win. Starvation does not require a deadlock: other threads continue to complete.

Be careful to distinguish "deadlock-free" from "live": eliminating lock cycles does not prove the absence of starvation, unbounded I/O waits, or livelock.

## 4. Progress guarantees of concurrent algorithms

Four common levels are described in shared-memory models with their corresponding execution assumptions:

| Level | Primary guarantee | Can a single thread wait forever? |
| --- | --- | --- |
| **Blocking** | Progress may depend on another thread running or releasing a lock. | Yes; a halted thread holding a lock can block all contenders. |
| **Obstruction-free** | An operation can complete if it runs long enough without contention from other operations. | Yes. |
| **Lock-free** | Under continued execution, the system makes progress: operations cannot continuously impede each other without some call completing. | Yes; one thread may always lose. |
| **Wait-free** | Every invocation completes within a bounded number of its own steps under the algorithmic model. | No, per the algorithm's step bound; wall-clock time still depends on scheduling. |

The conceptual hierarchy within the non-blocking family is: **wait-free is stronger than lock-free, and lock-free is stronger than obstruction-free**. `lock-free` does not mean "uses no OS waiting mechanism at any implementation layer," and an API named `Atomic*` does not automatically make the entire business operation calling it wait-free.

For a CAS retry loop:

```java
while (true) {
    int oldValue = counter.get();
    int newValue = oldValue + 1;
    if (counter.compareAndSet(oldValue, newValue)) {
        break;
    }
}
```

If a CAS fails because the value changed, then another contender succeeded in making a change. This is the typical basis for a system-wide progress argument for a simple CAS loop. However, a thread executing the loop can fail many times, or even starve. Conclusions about a complete algorithm also depend on assumptions, shared state, work inside the loop, and implementation-layer behavior. Do not claim `wait-free` without a per-invocation step bound.

**Design goal:** choose the progress level based on requirements. An explicit lock with a timeout, narrow scope, and easily proven invariants may be a better fit than a complex CAS loop. Under strict latency requirements, verify latency distributions, lock wait times, and retry counts—not just throughput.

## 5. Starvation, fairness, and resource allocation policies

*Fairness* describes how opportunities are distributed among contenders. A fair lock generally tries to favor threads that have waited longer; a *nonfair lock* may allow a newly arriving contender to acquire the lock ahead of waiting threads (*barging*) to improve throughput under certain workloads.

Java provides fairness options for several primitives:

- `new ReentrantLock(true)`: uses a fairer queuing policy for normal lock acquisitions; **does not** strictly guarantee thread execution order or CPU scheduling time. Untimed `tryLock()` can still barge and acquire the lock even when threads are waiting, even on a fair lock.
- `new Semaphore(permits, true)`: uses a fair policy when granting permits at defined queuing points; does not imply fairness for actions outside the primitive.
- `synchronized`: provides no FIFO/fairness contract to rely on when designing against starvation.
- `Thread.yield()`, `Thread.setPriority()`, and `Thread.sleep()`: are not fairness guarantees; scheduling depends on the JVM/OS.

Example of safe lock management, illustrating Java 17 syntax:

```java
import java.util.concurrent.locks.ReentrantLock;

final class Inventory {
    private final ReentrantLock lock = new ReentrantLock(true);
    private int stock = 10;

    public boolean reserveOne() {
        lock.lock();
        try {
            if (stock == 0) {
                return false;
            }
            stock--;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
```

This is an **illustrative snippet**, not a complete program with `main`. The `finally` block guarantees the lock is released even if an exception is thrown, helping avoid accidental lock retention. The `true` flag affects the lock's contention policy, but it does not make this method wait-free and does not guarantee a maximum latency. In real systems, measure throughput and tail latency before enabling fairness, as it can introduce scheduling overhead.

Starvation can also arise from **thread-pool starvation**: tasks in a pool wait for the results of other tasks submitted to the same pool when all worker threads are already occupied. Even with no lock cycle, no free worker remains to execute the awaited tasks. Avoid such dependent waiting structures, or separate execution resources and define appropriate capacity/queue policies.

## 6. Reducing the risk of deadlock and unbounded waiting

### 6.1 Consistent lock ordering

If every code path that needs both `L1` and `L2` acquires them in the same order `L1` → `L2`, you eliminate wait cycles caused by inverting **those two locks**. The rule must hold across all call paths; a hidden method that acquires an additional lock can break the assumption. Avoid holding locks while performing network I/O, invoking uncontrolled callbacks, or waiting on a long-running `Future.get()`.

### 6.2 Timed waiting and interruption handling

Example of attempting to acquire a lock with a timeout while preserving the interruption contract:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

final class TimedCriticalSection {
    private final ReentrantLock lock = new ReentrantLock();

    public boolean execute() throws InterruptedException {
        if (!lock.tryLock(200, TimeUnit.MILLISECONDS)) {
            return false;
        }
        try {
            // Perform short work without unbounded I/O waits.
            return true;
        } finally {
            lock.unlock();
        }
    }
}
```

This is also an **illustrative snippet**. The acquire timeout only bounds the time spent **waiting for the lock**, not the execution time inside the critical section. The method throws `InterruptedException` so the caller can decide how to cancel or coordinate. If you catch the exception to terminate a task, you typically need to restore the interruption flag with `Thread.currentThread().interrupt()` and exit the work. Never swallow an interruption and continue waiting indefinitely.

Use `Condition.await()` inside a `while` loop checking the predicate, because *spurious wakeups* can occur and the condition may have changed by the time the thread wakes up:

```java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
    // Proceed while the ready predicate remains true under the lock.
} finally {
    lock.unlock();
}
```

The snippet above assumes `lock`, `condition`, and `ready` are properly declared and all operations on `ready` follow the same synchronization protocol. Calling `signal()` alone does not guarantee that the awakened thread will immediately receive CPU time or finish within a deadline.

For producer/consumer workflows, prefer primitives with clear contracts such as `BlockingQueue`, and consider timed variants (`offer(timeout)`, `poll(timeout)`) when you need to prevent unbounded waiting. For `ExecutorService`, clearly define `shutdown()`, `awaitTermination(timeout)`, and `shutdownNow()`; `shutdownNow()` only attempts to interrupt tasks and cannot force uncooperative tasks to stop immediately.

## 7. How to verify safety and liveness

### Verifying safety

1. Write invariants as testable assertions: "balance is non-negative," "each ID transitions state only once," "total granted permits never exceed the limit."
2. Identify the required atomic scope: a single variable, multiple variables, or an entire sequence of business state transitions.
3. Reason through whether all critical interleavings preserve the invariant; mark linearization points if the API requires them.
4. Use concurrency tests with a shared starting gate (`CountDownLatch`/`CyclicBarrier`) to increase the probability of races; repeat stress tests and assert the final state. Passing tests do not prove the absence of races.
5. Use appropriate JVM concurrency/interleaving testing tools when deeper evidence is needed; do not infer from a single stable run that code is thread-safe.

### Verifying liveness/progress

1. List every waiting point: lock acquisition, `wait()`/`await()`, queues, `Future.get()`, I/O, `join()`, sleep, and mutually dependent tasks.
2. For each waiting point, identify what triggers its release, whether it can be blocked by the waiter itself, and whether timeouts or cancellation exist.
3. Measure lock wait times, CAS retry counts, queue depth, throughput, timeout rates, and p95/p99 latency per task group; good averages can mask starvation.
4. When an application hangs, collect thread dumps (`jcmd <pid> Thread.dump_to_file ...` where supported by the JVM, or `jstack <pid>` appropriate for the JDK/JVM). Inspect `BLOCKED`, `WAITING`, and `TIMED_WAITING` states, stack traces, and lock ownership; a single `WAITING` state alone does not prove deadlock.
5. Java provides `ThreadMXBean.findDeadlockedThreads()` to help detect certain monitor/ownable-synchronizer deadlocks. Finding no deadlocks with this API **does not prove** the absence of livelock, starvation, I/O waits, or all forms of dependency cycles.

A practical fairness test must apply sustained contention and observe **per-thread service levels**, not just system-wide operations per second. Do not try to prove "starvation is impossible" from a finite benchmark alone.

## 8. Choosing techniques by problem

| Need | Typical design approach | What still must be checked |
| --- | --- | --- |
| Protecting multiple fields sharing one invariant | `synchronized` or a shared `Lock` across all access paths | Lock scope, lock ordering, exceptions, and contention |
| A single counter/simple state needing atomic updates | `AtomicInteger`, `AtomicLong`, or appropriate CAS | Multi-step invariants, retries, starvation risk |
| Passing tasks between producers and consumers | `BlockingQueue` with an appropriate capacity | Backpressure, shutdown, timeouts, cancellation |
| Many reader threads, few writer threads | Suitable concurrent structure or `ReadWriteLock` when beneficial | Writer starvation risk, lock overhead |
| Resource with a bounded number of concurrent accesses | `Semaphore` with fairness policy when needed | Permit leaks, resource overflow, permit-granting policy |
| Must cancel work when a time limit is exceeded | Timed wait/lock APIs, cooperative interruption | Whether inner code cooperates with cancellation; whether resources are reclaimed |

Evaluate both correctness and performance. Fairness can improve service opportunity but does not guarantee hard deadlines; fewer locks can increase throughput but make safety reasoning harder. Unless you have a specific requirement, choose standard primitives with clear contracts and verify invariants before optimizing algorithms.

## 9. Common misconceptions

- **"Using `volatile` makes `count++` thread-safe."** False: visibility does not make a compound increment atomic.
- **"Every field is `Atomic*`, so the business operation is safe."** False: invariants spanning multiple operations can still be interleaved.
- **"No race observed in tests means there is no race."** False: rare interleavings may simply not have occurred yet.
- **"No deadlock means the program has liveness."** False: starvation, livelock, I/O waits, missed signals, and thread-pool starvation can still occur.
- **"Lock-free means every thread is fast."** False: system-wide progress does not guarantee progress for an individual call.
- **"A fair lock guarantees wall-clock FIFO and zero starvation in all cases."** False: JVM/OS scheduling, contention points, lock acquisition APIs, and external logic bugs still matter.
- **"`sleep()` or `yield()` fixes race conditions."** False: they alter interleaving probabilities rather than establishing atomicity or required happens-before synchronization.
- **"A lock acquisition timeout gives the whole task a deadline."** False: the critical section and I/O inside it can still hang.

## 10. Knowledge self-check

1. Two threads concurrently call `if (atomic.get() > 0) atomic.decrementAndGet()`. Which property can be violated? **Safety**, because check-then-act is not atomic.
2. Thread A waits for `L2` while holding `L1`, and B waits for `L1` while holding `L2`. What is this? **Deadlock**, a liveness failure caused by a circular dependency.
3. Operations in a CAS loop still succeed, but thread T keeps failing. What can be true? **The system has progress while T suffers starvation**.
4. Does `new ReentrantLock(true)` guarantee every call finishes within 100 ms? **No**: a fairness policy is not an execution deadline and does not control OS scheduling.
5. What is needed to prove an operation is wait-free? **A bound on the operation's own step count** under the algorithmic assumptions, rather than merely observing other threads completing.
6. Data is consistent, but an untimed `Future.get()` waits forever. Is safety or liveness affected? **Liveness**, even though safety may still hold.

**Remember:** start with invariants to evaluate safety, then map wait dependencies and resource allocation policies to evaluate liveness. Distinguish *system-wide* progress from *per-thread* progress, and always check for starvation under realistic contention.
