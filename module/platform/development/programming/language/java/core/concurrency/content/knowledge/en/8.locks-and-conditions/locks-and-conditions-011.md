# Cost, Complexity, and Criteria for Choosing a Lock Type in Java

In Java Concurrency, the question “should I use `synchronized`, `ReentrantLock`, `ReadWriteLock`, or `StampedLock`?” cannot be answered merely by counting how many threads access the data. Each mechanism provides a different contract regarding **mutual exclusion**, **memory visibility**, **waiting and cancellation**, **contention**, **fairness**, and **the difficulty of proving the program correct**. A more complex lock does not automatically mean faster; a simple lock is not inherently a bottleneck.

A good way to choose is to identify **the invariant that needs to be protected**, **the coordination that must happen within a critical section**, and **the cost if a thread waits**, and only then measure performance under a realistic workload. This lesson belongs to the **Locks & Conditions** topic of **general Java Concurrency**, without considering Spring-specific mechanisms.

## 1. First: What Problem Does a Lock Solve?

When multiple threads concurrently read/write mutable state, proper protection requires two aspects:

- **Mutual exclusion / atomicity:** a group of steps related to an invariant executes without another thread interleaving. For example, checking a balance and then deducting money must be in the same logical transaction.
- **Happens-before / visibility:** an unlock on the same monitor happens-before a subsequent lock; standard `Lock` implementations have corresponding memory semantics. Only readers that follow the same protocol have a guarantee of observing published updates.

Example:

~~~java
private final Object lock = new Object();
private int available = 100;
private int reserved;

boolean reserve() {
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

This is a **code snippet of a class**, not a standalone runnable program. The invariant here is `available >= 0`, `reserved >= 0`, and `available + reserved == 100`. The check, decrement, and increment all lie within the same critical section.

To read both fields **as a snapshot**, a reader must also acquire the same lock and read them during a single ownership. Two `synchronized` getters called sequentially may return values from two different points in time if a writer interleaves between the calls. Using `volatile` on each field alone does not turn two writes into an atomic update.

**Starting point:** choose **the data ownership protocol** before choosing a lock class. If any getter or callback can bypass the lock, replacing `synchronized` with `StampedLock` will not fix the bug.

## 2. What Does “Lock Cost” Consist Of?

There is no single fixed overhead number across all JVMs. The cost depends on the JDK, CPU, contention level, critical section, cache layout, and how benchmarks are run.

| Cost Type | Cause | How to Inspect |
| --- | --- | --- |
| **Acquire / release** | Instructions and synchronization barriers / atomic operations needed to acquire and release the lock. | Benchmark the low-contention path, use an appropriate profiler. |
| **Contention wait** | A contender has to wait for the current holder. | Blocked time, lock profiling, thread dumps, JFR. |
| **Scheduling / wake-up** | A thread is parked/blocked and then woken up and rescheduled. | p95/p99 latency, context switching, lock wait time. |
| **Cache coherence** | Multiple cores update the same lock state/metadata, causing traffic. | Profiling / CPU counters where supported. |
| **Serialization** | The critical section prevents operations from running concurrently. | Throughput as workers increase; hold time duration. |
| **Fairness bookkeeping** | Queueing / order-preserving policies can reduce “barging” and lower throughput. | Benchmark fair vs. nonfair under the same load. |
| **Read/write coordination** | Read locks have their own metadata; acquiring/releasing for each reader still has a cost. | Compare against a mutex when only reading a few fields. |
| **Optimistic retry** | CAS failure or optimistic-read validation failure forces work to be redone. | Retry rate, allocation, CPU, tail latency. |
| **Programming complexity** | Easy to forget `unlock()`, forget to validate, mix up conditions, cause deadlock, or scatter invariants. | Code review, stress tests, production incidents. |

Do not just measure the nanoseconds of an empty `lock()` and extrapolate application performance from that. A long critical section caused by network I/O or an external callback will overshadow the acquisition cost. Conversely, millions of tiny updates to a single shared point can be limited by cache contention and lock acquisition frequency.

**The most important metrics under high contention are usually lock hold time and contention frequency**, not the API name.

## 3. Questions You Must Answer Before Choosing

1. **What state must be consistent?** A single variable, multiple fields in the same invariant, or multiple objects?
2. **What is the read/write ratio and operation duration?** Does a read only fetch two fields, or query large data? How frequent are writes?
3. **What is the actual number of contenders?** Existing threads do not necessarily all contend for the same lock.
4. **Is condition waiting required?** Do you need `await`/`signal` on multiple independent conditions, or only state updates?
5. **Is there a deadline/cancellation at lock acquisition?** If you need `tryLock(timeout)` or `lockInterruptibly()`, an intrinsic monitor does not provide an equivalent acquisition policy.
6. **Is fairness needed?** Fairness can affect throughput and latency, but it does not replace an SLA.
7. **Do you need to acquire multiple locks?** Lock ordering, reentrancy, and deadlock risk will determine complexity.
8. **Do reads need a linearizable snapshot?** A report might tolerate an approximation, whereas payments/quotas usually cannot.
9. **On error/interrupt, is the state still valid?** Releasing a lock does not mean state has been rolled back.
10. **Can the bottleneck be measured?** Do not optimize a lock just because you “heard” another class is faster.

Every requirement must stem from the API contract and invariants, not from random configuration tricks.

## 4. `synchronized`: The Foundational Choice, Usually Worth Trying First

`synchronized` uses the **intrinsic monitor** attached to an object. The JVM automatically acquires it upon entering the block/method and releases it upon exit, even if an exception is thrown. This option has many advantages:

- Concise code; impossible to forget `unlock()` on normal return/exception paths.
- Reentrant: a thread holding the monitor can re-enter that same monitor.
- Clear Java Memory Model contract: unlock → subsequent lock on the **same monitor**.
- Well-suited for protecting a group of fields sharing an invariant.
- No separate Lock/Condition objects needed if only mutual exclusion is required.

Important limitations:

- Waiting to **acquire a monitor** via `synchronized` has no timeout overload or `lockInterruptibly()`. A thread `BLOCKED` on a monitor does not abort waiting when interrupted.
- No guaranteed FIFO/fairness policy.
- Only one monitor per object; `Object.wait()/notify()/notifyAll()` exist, but when there are multiple distinct predicates, organizing conditions can be difficult.
- If a critical section holds the lock while performing I/O, `Thread.sleep()`, `Future.get()`, or slow callbacks, contention remains high. `sleep()` does not release the monitor.

### 4.1 Which Lock Object Should You Choose?

~~~java
final class Counter {
    private final Object lock = new Object();
    private long value;

    void add(long delta) {
        synchronized (lock) {
            value += delta;
        }
    }

    long get() {
        synchronized (lock) {
            return value;
        }
    }
}
~~~

This is an **illustrative class snippet**. A private lock prevents external code from synchronizing on the same object and affecting liveness.

Notes:

- A `synchronized` instance method acquires the monitor of `this`.
- A `static synchronized` method acquires the monitor of the `Class` object.
- Two different instances have two different monitors, so this is only appropriate if the protected state is also independent.
- Avoid locking on string literals/interned strings or boxed constants that could be unintentionally shared.
- Do not confuse `volatile` with a monitor; `volatile` does not protect multi-step check-then-act operations.

### 4.2 When Is `synchronized` Good Enough?

If the critical section is short, contention is low, timed/interruptible acquisition is not needed, and a private monitor protects the entire invariant, `synchronized` is usually the **lowest-risk and easiest-to-review** decision. Only switch to a more complex primitive when there is a specific requirement or measurements prove an issue.

## 5. `ReentrantLock`: Explicit Locking in Exchange for Control

`java.util.concurrent.locks.ReentrantLock` also provides mutual exclusion and memory effects like an intrinsic monitor when used properly. The differences lie in the extended operations:

| Requirement | `synchronized` | `ReentrantLock` |
| --- | --- | --- |
| Mutual exclusion | Yes | Yes |
| Reentrant | Yes | Yes |
| Auto-release when exiting block via exception | Yes, handled by JVM | No; **must call `unlock()` in `finally`** |
| Try acquiring lock immediately | No direct equivalent API | `tryLock()` |
| Acquire lock with timeout | Not available on acquisition | `tryLock(timeout, unit)` |
| Interruptible lock acquisition | Not available on acquisition | `lockInterruptibly()` |
| Multiple distinct wait conditions on one lock | One wait set/monitor + `wait/notify` | Multiple `Condition`s via `newCondition()` |
| Fair option | No fairness parameter | `new ReentrantLock(true)` |
| Observe queue/waiters | Mainly via JVM diagnostics | Provides some monitoring methods; results are point-in-time |

### 5.1 Rules for Correct Usage

~~~java
lock.lock();
try {
    // Read/write protected state.
} finally {
    lock.unlock();
}
~~~

This is a code snippet assuming `lock` is of type `ReentrantLock`. You must call `lock()` **before** `try`, and only call `unlock()` after successfully acquiring the lock. If `lockInterruptibly()` is interrupted **before acquiring**, you must not call `unlock()` on a thread that does not own the lock.

Because the lock is a manually managed object, the risk of bugs increases if you:

- Forget to unlock on a return/exception branch.
- Acquire/release an unequal number of times when using reentrancy.
- Expose the lock externally, allowing callers to hold it arbitrarily long.
- Hold the lock across uncontrolled callbacks/I/O.
- Call `Condition.await()` or `signal()` without owning the lock as required by the contract.

**There is no guarantee that `ReentrantLock` is always faster than `synchronized`.** They may have different optimization paths depending on the JDK and workload; real benchmarks decide.

## 6. Java 17+ Example: Timeout When Waiting for a Lock

An intrinsic monitor does not have timed acquisition. The example below uses `ReentrantLock.tryLock(timeout)` to prevent a thread from waiting indefinitely when a holder still owns the lock.

Create the file `TimedLockChoiceDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public final class TimedLockChoiceDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch holderEntered = new CountDownLatch(1);
        CountDownLatch releaseHolder = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            lock.lock();
            try {
                holderEntered.countDown();
                releaseHolder.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                lock.unlock();
            }
        }, "holder");

        Thread contender = new Thread(() -> {
            try {
                boolean acquired =
                        lock.tryLock(100, TimeUnit.MILLISECONDS);
                System.out.println("Acquired: " + acquired);
                if (acquired) {
                    try {
                        System.out.println("Critical section");
                    } finally {
                        lock.unlock();
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "contender");

        holder.start();
        holderEntered.await();

        contender.start();
        contender.join();
        releaseHolder.countDown();
        holder.join();
        System.out.println("Finished");
    }
}
~~~

Java 17+ commands:

~~~bash
javac TimedLockChoiceDemo.java
java TimedLockChoiceDemo
~~~

Stdout on a normal run without external interruption:

~~~text
Acquired: false
Finished
~~~

**Why is the result deterministic?** The holder does not release the lock before `main` opens `releaseHolder`; `main` only opens it after `contender` has finished. `contender` cannot acquire the lock within the 100 ms deadline and returns `false`. There is no `sleep()` guessing the schedule.

Key takeaways:

- The timeout only limits **the wait time to acquire**, not the execution time of the operation after the lock is acquired.
- `tryLock()` without a timeout tries immediately and returns a boolean; `tryLock(timeout, unit)` can throw `InterruptedException`.
- Do not use the timeout branch as a silent “fallback” that drops financial updates; you must clearly define the API outcome, retry policy, and caller notification.
- `unlock()` is inside `finally` after a successful acquire, never releasing a lock owned by another thread.
- On application shutdown/cancellation, coordinate cleanup and release any necessary latches/conditions.

## 7. Fairness: Cost and Misconceptions

`new ReentrantLock(true)` requests a **fairness policy**: when multiple threads contend, the lock tends to grant access to the longest-waiting thread according to the API's queueing mechanism. `new ReentrantLock(false)` (the default) allows a nonfair policy, which often benefits throughput in many workloads.

However, fairness does **not** mean:

- every task finishes within a deadline;
- the JVM/OS scheduler allocates CPU fairly;
- critical section duration becomes shorter;
- application-level starvation disappears (e.g., due to I/O, pool saturation, or task dependencies).

An easily overlooked detail: **zero-argument `tryLock()` can acquire the lock immediately if it is free even on a fair `ReentrantLock`**, even if other threads are waiting. If you need stricter fairness compliance in the try-acquire path, you must understand the differences between overloads and their specific contracts. Do not describe a fair lock as strict FIFO across every API method.

A fair lock can reduce “barging”, but it also incurs queue-management overhead and can lower throughput. Choose it when there is a justified requirement for lock-waiting fairness, and measure with a representative workload.

## 8. `Condition`: When One Lock Protects Multiple Wait Conditions

If a thread needs to wait for **a predicate** of state protected by a lock, repeatedly releasing/reacquiring the lock to poll is inefficient. A `Condition` bound to a `Lock` allows the thread currently owning the lock to call `await()`:

1. Atomically **releases the associated lock** while waiting.
2. Waits for `signal()` / `signalAll()`, interruption, or spurious wakeup.
3. Reacquires the lock before `await()` returns normally.
4. Must re-check the predicate using **`while`**, not `if`.

Unlike `Object.wait()`, a `ReentrantLock` can create **multiple `Condition` instances** to separate different waiter groups:

- `notEmpty`: consumers waiting for an item to be available;
- `notFull`: producers waiting for space to be available.

### 8.1 Java 17+ Example: Bounded One-Slot Buffer

Create the file `ConditionBufferDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class ConditionBufferDemo {
    static final class OneSlotBuffer {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();
        private Integer value;

        void put(int item) throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (value != null) {
                    notFull.await();
                }
                value = item;
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        int take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (value == null) {
                    notEmpty.await();
                }
                int item = value;
                value = null;
                notFull.signal();
                return item;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        OneSlotBuffer buffer = new OneSlotBuffer();
        CountDownLatch consumerStarted = new CountDownLatch(1);

        Thread consumer = new Thread(() -> {
            consumerStarted.countDown();
            try {
                System.out.println("Taken: " + buffer.take());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        consumerStarted.await();

        buffer.put(42);
        consumer.join();
        System.out.println("Finished");
    }
}
~~~

Compile/run commands:

~~~bash
javac ConditionBufferDemo.java
java ConditionBufferDemo
~~~

Stdout without external interruption:

~~~text
Taken: 42
Finished
~~~

**Analysis:**

- `OneSlotBuffer` has only one slot; the state `value == null` means the buffer is empty.
- The consumer checks the predicate under the lock; if empty, `notEmpty.await()` releases the lock so the producer can enter `put()`. If the producer puts before the consumer enters, the consumer sees `value != null` and does not need to wait, so no signal is lost under this protocol.
- The producer sets `value` and calls `notEmpty.signal()` while holding the lock, then unlocks. Only then can the consumer reacquire the lock and read `value`; memory visibility is guaranteed by the lock protocol.
- The `while` loop guards against spurious wakeups and the condition changing before the waiter reacquires the lock.
- The program uses one producer and one consumer to keep stdout simple; the buffer class can be used across multiple threads, though shutdown/cancellation and fairness policies still need to be defined as required.

**Do not write your own bounded queue like this in production if `ArrayBlockingQueue` already meets your needs.** This example is for explaining `Condition`. Standard queues already handle many edge cases and provide `put()`/`take()`/timed operations.

## 9. `ReadWriteLock`: Allowing Multiple Readers Simultaneously

`java.util.concurrent.locks.ReadWriteLock` defines two locks with distinct roles:

- **Read lock:** multiple readers can hold it concurrently as long as no writer holds the write lock.
- **Write lock:** a writer needs exclusive access to update state, blocking conflicting readers/writers according to the protocol.

`ReentrantReadWriteLock` is the standard implementation. It can help workloads that are **read-heavy, write-light, with sufficiently long read critical sections**, but 90% reads does not automatically guarantee better performance than a mutex.

### 9.1 Hidden Costs

- Every reader still needs to acquire/release a read lock and update/check coordination state.
- When there are many reader threads, the lock metadata becomes a shared point of contention.
- Writers must wait for active readers to finish; long-running readers increase write latency.
- Fairness policy affects starvation/throughput, but does not create a guaranteed deadline.
- For extremely short read critical sections (just two getters), read lock overhead can be more expensive than a simple mutex in some workloads.

### 9.2 Upgrade/Downgrade

`ReentrantReadWriteLock` supports a controlled **downgrade** where a thread holding the write lock acquires the read lock and then releases the write lock. However, **read-to-write upgrade is not generally supported**: holding the read lock and attempting to acquire the write lock can lead to an indefinite wait when exclusivity cannot be obtained.

Instead, do: read/check under read lock → release read lock → acquire write lock → **re-check the condition** → commit. The gap between release and acquire allows state to change; you must not assume the old condition still holds.

### 9.3 Runnable Java 17+: Snapshot Under Read Lock

Create the file `ReadWriteLockChoiceDemo.java`:

~~~java
import java.util.concurrent.locks.ReentrantReadWriteLock;

public final class ReadWriteLockChoiceDemo {
    private static final class Inventory {
        private final ReentrantReadWriteLock rw =
                new ReentrantReadWriteLock();
        private int available = 100;
        private int reserved;

        boolean reserve() {
            rw.writeLock().lock();
            try {
                if (available == 0) {
                    return false;
                }
                available--;
                reserved++;
                return true;
            } finally {
                rw.writeLock().unlock();
            }
        }

        Snapshot snapshot() {
            rw.readLock().lock();
            try {
                return new Snapshot(available, reserved);
            } finally {
                rw.readLock().unlock();
            }
        }
    }

    private record Snapshot(int available, int reserved) {
        int total() {
            return available + reserved;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Inventory inventory = new Inventory();
        Runnable task = () -> {
            for (int i = 0; i < 100; i++) {
                inventory.reserve();
            }
        };

        Thread a = new Thread(task, "a");
        Thread b = new Thread(task, "b");
        a.start();
        b.start();
        a.join();
        b.join();

        Snapshot s = inventory.snapshot();
        System.out.println("Available: " + s.available());
        System.out.println("Reserved: " + s.reserved());
        System.out.println("Total: " + s.total());
    }
}
~~~

Compile and run:

~~~bash
javac ReadWriteLockChoiceDemo.java
java ReadWriteLockChoiceDemo
~~~

Stdout:

~~~text
Available: 0
Reserved: 100
Total: 100
~~~

Two writers compete to acquire the write lock; there are exactly 100 successful reservations. The snapshot is read within a single read lock acquisition, so it never reads `available` from an earlier version and `reserved` from a later version.

Note that this program **does not prove the performance** of a read/write lock: it consists mostly of writers and only a single snapshot at the end. Benchmarking a real read-heavy workload is required before deciding to replace a mutex.

## 10. `StampedLock`: More Modes, More Rules

`java.util.concurrent.locks.StampedLock` supports a **write lock**, a **read lock**, and an **optimistic read** using stamps. It is not a `ReentrantLock` under a new name.

Important characteristics:

- **Non-reentrant:** a method holding a write lock that tries to acquire the write lock again along a nested call path can deadlock itself.
- A stamp is a token returned from an acquire operation; the exact stamp must be passed to `unlockRead(stamp)` / `unlockWrite(stamp)`.
- `tryOptimisticRead()` returns a stamp used to **validate** whether a writer invalidated the snapshot during the read phase; it does not hold a read lock.
- If `validate(stamp)` fails, you must re-read under a read lock or retry according to an appropriate protocol.
- Mode-conversion operations like `tryConvertToWriteLock` exist, but conversions can fail; you must check the result and manage stamps/modes with extreme care.
- Does not provide a `Condition` contract like `ReentrantLock.newCondition()`.
- Does not guarantee fairness; starvation can easily occur if used inappropriately for the workload.

### 10.1 Optimistic Read: Read Then Validate

Illustrative pattern:

~~~java
long stamp = lock.tryOptimisticRead();
int x = state.x;
int y = state.y;

if (!lock.validate(stamp)) {
    stamp = lock.readLock();
    try {
        x = state.x;
        y = state.y;
    } finally {
        lock.unlockRead(stamp);
    }
}
return new Snapshot(x, y);
~~~

This is an **illustrative method snippet**, assuming `lock` is a `StampedLock`, `state` holds two primitive fields, the method returns a `Snapshot`, and the types are already declared. It does not run standalone.

Key points:

1. An optimistic read **can observe an intermediate state while a writer is modifying it**, before validation.
2. Only use the results after **`validate(stamp) == true`**. If validation fails, re-read under a real read lock.
3. Do not use unvalidated values to cause side effects, access out-of-bounds array indices, invoke methods on references that may be mutating, or make irreversible decisions.
4. This pattern is simple for primitive fields. For mutable/complex object graphs, reading before validation can be operationally unsafe or error-prone; consider using a read lock from the start.
5. A stamp is not a durable business “version ID”. It is a token for the locking/validation protocol.

### 10.2 When Should You Not Use It?

If the code needs reentrancy, multiple `Condition`s, complex mutable object values, or the team lacks strong testing and review practices for optimistic protocols, `StampedLock` easily increases maintenance cost more than the performance gained. A low optimistic validation success rate forces frequent retries, wasting CPU and adding complexity.

Use it when profiling and benchmarks show **many independent reads, rare writes, and optimistic reads usually succeed**, while state can be safely represented as a snapshot.

## 11. Not Every Problem Needs a Lock

A lock is a good solution for multi-step invariants; for simple state, specialized primitives can be less risky.

| Problem | Worth Considering | Why |
| --- | --- | --- |
| Simple visibility flag/signal, single writer | `volatile` or latch/future depending on protocol | No mutual exclusion needed for multiple steps. |
| Independent increment counter needing exact reads | `AtomicInteger`/`AtomicLong` | Atomic read-modify-write for a single variable. |
| Multi-writer metrics, approximate sum read during updates | `LongAdder` | Spreads contention; `sum()` is not an atomic snapshot under concurrent updates. |
| Updating multiple fields as **one immutable value** | `AtomicReference<State>` + CAS | A single reference holds the whole snapshot, updated with one CAS. |
| Producer/consumer waiting for items | `BlockingQueue` | Handles coordination internally; no need to write a custom `Condition` buffer. |
| One-time completion signal | `CountDownLatch` | Wait for an event rather than accessing mutable state via a custom lock. |
| Limiting how many tasks use a resource concurrently | `Semaphore` | Controls permits; does not automatically make fields atomic. |
| Many independent keys, concurrent map access | `ConcurrentHashMap` | Specialized concurrent API, though multi-key operations still have their own invariants. |

### 11.1 `AtomicReference` and CAS Also Have Costs

If you use `AtomicReference<ImmutableState>` to hold a multi-field snapshot, a writer creates a new state and calls `compareAndSet(old, next)`. Under concurrent updates, CAS fails and must retry. Costs include:

- Allocation for candidate states that may be discarded.
- Retries under high contention; no guarantee that a specific thread will succeed in a bounded number of attempts.
- Hard-to-review code if side effects exist inside the computation of `next`.
- Potential ABA issues if an algorithm reuses identity/values without checking history.

Do not put network calls, email sending, or external state mutations inside retryable computations. For complex state, a simple lock can be easier to get right and faster.

### 11.2 Individual Atomic Variables Do Not Mean Multi-Variable Consistency

Two separate `AtomicInteger`s do not turn `available--` and `reserved++` into an atomic transition. If you need `available + reserved == capacity` in every snapshot, use **one critical section** or **one immutable `State` published atomically**.

Any “lock-free” decision must also prove proper happens-before, atomicity, and invariants. Do not replace a lock with `volatile` just to avoid `BLOCKED` threads.

## 12. Reentrancy, Fairness, Cancellation: You Cannot Swap Locks Mechanically

Beyond performance, switching primitives can change **API semantics**.

### 12.1 Reentrant or Not?

- Intrinsic monitors: reentrant.
- `ReentrantLock`: reentrant.
- `ReentrantReadWriteLock`: supports reentrancy according to its own rules.
- `StampedLock`: **non-reentrant**.

A method chain that works fine under `synchronized` can deadlock itself after switching to `StampedLock` if a nested helper method acquires the lock again. Before switching, inspect the call graph and nested acquisitions.

### 12.2 Interruptibility of Acquisition

- A thread `BLOCKED` trying to enter `synchronized` has no timed/interruptible acquisition equivalent to `ReentrantLock.lockInterruptibly()`.
- `ReentrantLock.lockInterruptibly()` and `tryLock(timeout, unit)` can throw `InterruptedException`.
- `Condition.await()` is a condition-waiting operation, distinct from waiting to acquire a lock initially.
- `Object.wait()` can throw `InterruptedException` and releases the monitor while waiting; `Thread.sleep()` does not release a held monitor.

Distinguish **cancellation of a thread waiting to acquire a lock** from **cancellation of a thread already holding a lock**. No API automatically guarantees that a business operation can roll back cleanly at an arbitrary instruction.

### 12.3 Fairness and Starvation

A fair option can help when a group of contenders waits disproportionately, but it does not fix code that holds locks too long or has circular dependency graphs. Fairness also has scheduling/throughput costs; what needs to be defined is the expected user-level policy, not just a configuration flag.

## 13. Deadlock and Multi-Lock Ordering

When two locks must be held simultaneously, a circular dependency can occur:

~~~text
Thread A: holds lock1 -> waits for lock2
Thread B: holds lock2 -> waits for lock1
~~~

If a single owner lock can protect the entire invariant, the design is often simpler and easier to prove correct. When multiple locks are unavoidable, use a **consistent global ordering**, such as by a unique, immutable object ID.

Illustrative snippet:

~~~java
Account first = left.id < right.id ? left : right;
Account second = left.id < right.id ? right : left;

synchronized (first.lock) {
    synchronized (second.lock) {
        // Check and update state involving both accounts.
    }
}
~~~

This snippet is **not standalone**: it requires an `Account` class with a unique, immutable ID, its own lock, and state. In production, you must handle the same-account case, duplicate/invalid IDs, and ensure all other call paths follow the same order. Do not expose locks publicly or allow external callbacks to acquire locks in reverse order.

**Cost consideration:** splitting one lock into many can increase concurrency when data is independent, but it increases the deadlock surface and makes multi-object snapshots harder. Only shard locks when you can prove invariants are not improperly split and there is a measurable benefit.

### 13.1 Do Not Wait for Completion While Holding a Lock the Task Needs

~~~java
synchronized (lock) {
    worker.start();
    worker.join();
}
~~~

This illustrative snippet assumes `worker` needs `lock` while running; the caller holds the lock and waits for the worker to finish, while the worker needs that very lock to finish, creating a deadlock. `Thread.join()` does not release held monitors.

Avoid `Future.get()`, `CountDownLatch.await()`, or blocking I/O inside a critical section if the awaited work needs the held lock/worker. When you genuinely need to wait for a condition on a lock, use `Condition`/`Object.wait()` according to the protocol so the associated lock is released while waiting.

## 14. Virtual Threads and Lock Selection

Since Java 21, **virtual threads** make the thread-per-blocking-task model viable for many workloads, but they **do not free invariants from synchronization requirements**:

- Multiple virtual threads acquiring the same monitor still serialize inside the critical section.
- Holding a lock across slow I/O still causes contenders to wait and increases application-level latency.
- `ReentrantLock` is not automatically faster than an intrinsic monitor just because it runs on a virtual thread.
- Virtual-thread pinning issues when holding an intrinsic monitor have changed across JDK versions. For example, JDK 21 had pinning cases associated with `synchronized`; later JDK releases have improvements. Always verify against **the specific JDK being deployed** and inspect JFR/profilers rather than applying one version's rule to every runtime.
- `ReentrantLock` with interruptible/timed acquisition is useful when cancellation contracts require it, but switching lock types must still preserve ordering and invariants.

Evaluate locks **based on workload, JDK version, and real cancellation requirements**, rather than using “virtual threads” as a default excuse to replace all `synchronized` blocks.

## 15. Benchmark Properly Before Optimizing

A lock microbenchmark is very easy to get wrong due to compiler/JIT optimizations, dead-code elimination, warm-up, false sharing, artificial contention, and results dominated by work outside the lock.

### 15.1 Practical Steps

1. **Establish a correctness baseline.** Before and after optimization, the code must produce the same results/invariants under multi-threaded contention.
2. **Measure the right workload.** Reader/writer counts, critical section duration distribution, state size, and load level must represent production.
3. **Distinguish throughput from latency.** A lock that increases average throughput but pushes p99 lock-wait time too high may violate your SLA.
4. **Measure contention.** Thread dumps, `ThreadMXBean`, Java Flight Recorder (JFR), and profilers can show which threads are waiting on monitors/locks, what the holder is doing, and wait durations.
5. **Measure lock hold time too.** Many `BLOCKED` contenders may be caused by a single holder calling slow I/O/sleep inside the critical section.
6. **Warm-up and fair comparison.** Use the same JDK, JVM flags, input data, thread count, and environment; run multiple iterations and inspect result distributions.
7. **Check for bugs after optimization.** Do not accept “faster” if it drops atomic snapshots or updates.
8. **Document trade-offs.** Know how much code complexity increases relative to the measured gain.

**JMH** (Java Microbenchmark Harness) is suitable for JVM microbenchmarks. This lesson does not quote fixed nanosecond numbers because results depend entirely on benchmark setup and runtime.

### 15.2 Metrics to Record

| Metric | Interpretation |
| --- | --- |
| Operations/second | Useful throughput as workers scale. |
| Median, p95, p99 latency | Wait/execution time of requests/operations, especially tail distribution. |
| Lock acquisition/blocked time | Cost incurred by waiting contenders. |
| Critical section hold time | Duration the holder keeps the lock. |
| Retry/optimistic validation failure | Extra cost of CAS and `StampedLock`. |
| CPU, allocation, and GC | Overhead of retries, immutable candidates, and metadata. |
| Read/write proportion | Validates whether `ReadWriteLock` or optimistic read fits the workload. |
| Correctness invariants | Correctness must not be lost when changing primitives. |

Do not set a goal of “zero `BLOCKED` threads”. A bit of blocking can be reasonable and save CPU compared to spin loops. The goal is correctness plus sufficient performance to meet requirements, not eliminating every lock.

## 16. Choosing a Lock Type by Scenario

| Scenario | Reasonable Initial Choice | Why / What to Verify |
| --- | --- | --- |
| One mutable object, a few fields sharing an invariant, short critical section | **`synchronized` with a private lock** | Easy to read, reentrant, auto-releasing; verify all readers/writers follow the same protocol. |
| Need timed/interruptible acquisition | **`ReentrantLock`** | `tryLock(timeout)` / `lockInterruptibly()`; unlock in `finally`. |
| One lock with multiple predicates to wait on separately | **`ReentrantLock + Condition`** or an existing concurrent structure | Separate `notEmpty`/`notFull`; check predicates in a `while` loop. |
| Many readers, few writers, relatively long read critical sections | **`ReentrantReadWriteLock`** to experiment | Measure read-lock overhead and writer latency; not automatically faster than a mutex. |
| Very many simple reads, rare writes, easily validated snapshot | **`StampedLock`** if benchmarks prove the benefit | Non-reentrant and optimistic validation protocol is harder; needs fallback. |
| Single independent counter/flag variable | **Atomic/`volatile`** depending on the problem | Avoid unnecessary locks; `volatile` does not fix multi-step invariants. |
| Multi-field immutable snapshot, side-effect-free updates | **`AtomicReference<State>`** | CAS atomically publishes state, trading off retries/allocations. |
| Producer–consumer buffer | **`BlockingQueue`** | Less error-prone than hand-rolling `wait/notify/Condition`. |
| Many independent keys in a map | **`ConcurrentHashMap`** | Multi-key operations still need their own protocol. |

**Priority order:** correctness → deadline/cancellation → wait conditions → read/write pattern → actual contention → maintenance complexity. If two choices both meet requirements, prefer the simpler API until performance evidence proves otherwise.

## 17. Common Lock Selection Mistakes

**Mistake 1: “`ReadWriteLock` has two lock types so it is always faster than `synchronized`.”** False. Read locks still have overhead; small critical sections or frequent writers can yield lower throughput than a mutex.

**Mistake 2: “`StampedLock` optimistic read does not block so the data can be used immediately.”** False. Data read before validation may be inconsistent; it may only be used if validation succeeds, or else you must fall back to a read lock.

**Mistake 3: “Switching `synchronized` to `ReentrantLock` is a performance fix.”** No guarantee. If the holder still calls slow I/O under the lock, contention remains.

**Mistake 4: “A fair lock guarantees every thread finishes on time.”** False. Fairness does not change OS scheduling, task duration, or other wait points.

**Mistake 5: “Two getters under separate read locks are enough for a snapshot.”** If a writer interleaves between the two calls, they can come from two different versions. Read the entire invariant under **a single** read lock.

**Mistake 6: “An atomic variable per field solves the overall invariant.”** Per-variable atomicity does not create an atomic transaction across multiple variables.

**Mistake 7: “Only `unlock()` on the happy path.”** Exceptions/returns can leak the lock; use `try/finally` immediately after acquiring.

**Mistake 8: “You can upgrade a read lock to a write lock directly.”** With `ReentrantReadWriteLock`, read-to-write upgrade is not supported as a general operation; you must release and re-check after acquiring the write lock.

**Mistake 9: “`Condition.signal()` means the waiter runs immediately.”** The waiter still has to reacquire the lock and may see the predicate changed; always check in a `while` loop.

**Mistake 10: “Waiting on an intrinsic monitor can be interrupted to exit immediately.”** Waiting to acquire a monitor has no interruptible acquisition mechanism equivalent to `lockInterruptibly()`.

**Mistake 11: “JMH or a single profiling run gives permanent results.”** Different JDKs, hardware, read/write frequencies, and code paths can flip the results.

**Mistake 12: “Removing locks is always better.”** If the design loses proper happens-before/atomicity, the system may run faster while producing corrupt data.

## 18. Self-Check Questions

**1.** An object has three fields sharing an invariant; writes are rare and take only a few instructions. What should you start with?  
**Answer:** A private `synchronized` lock for both operations and snapshots, unless there are special requirements. Measure before choosing a more complex solution.

**2.** You need to bound the wait time to acquire a lock. Does an intrinsic monitor have a timed acquisition API?  
**Answer:** No. `ReentrantLock.tryLock(timeout, unit)` is more suitable, but you must handle the timeout branch and unlock properly.

**3.** You use `ReentrantReadWriteLock`, but a writer runs continuously; is it guaranteed to be faster than a mutex?  
**Answer:** No. The writer is still exclusive, readers have overhead and may wait; you need to benchmark with the real read/write ratio.

**4.** Why must `Condition.await()` be paired with a `while` loop?  
**Answer:** Because of spurious wakeups and because the predicate can change before the waiter reacquires the lock.

**5.** `StampedLock.tryOptimisticRead()` returns a stamp, two fields are read, and then `validate` fails. What should you do?  
**Answer:** Retry or acquire a read lock, re-read both fields, and only use a validated snapshot.

**6.** Multiple nested methods acquire the same lock. Is `StampedLock` suitable as a mechanical replacement for `synchronized`?  
**Answer:** No. `StampedLock` is non-reentrant and can cause the code to deadlock itself.

**7.** Two `AtomicInteger`s manage `available` and `reserved`. Is that enough to keep `available + reserved == capacity` in every snapshot?  
**Answer:** No. You need to update and read the group of fields under a shared atomic protocol.

**8.** Does zero-argument `tryLock()` on a fair `ReentrantLock` always respect the queue?  
**Answer:** No; this overload can barge when the lock is free, regardless of the fairness flag.

**9.** Why shouldn't you hold a lock while calling `Future.get()` waiting on a worker that needs that lock?  
**Answer:** It can create a circular wait preventing the worker from completing; wait outside the critical section or design a condition protocol.

**10.** When should you accept the added complexity of `ReadWriteLock` or `StampedLock`?  
**Answer:** When the correctness contract is proven, the workload has matching characteristics, and benchmarks/profiling show a large enough benefit over the overhead, retries, and maintenance cost.

**Remember:** There is no “strongest lock” for every situation. **`synchronized` is a good baseline when you only need clear mutual exclusion**; `ReentrantLock` is chosen for acquisition/condition control; `ReadWriteLock` when parallel reads pay off; and `StampedLock` when an optimistic protocol is genuinely worth it. Every decision must preserve invariants and happens-before, handle shutdown/interruption, and be validated by measurements on an appropriate workload.