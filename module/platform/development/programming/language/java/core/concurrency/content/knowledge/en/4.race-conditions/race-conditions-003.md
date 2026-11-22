# Lost Update in Counter Increment Operations — Java Concurrency

## 1. Lesson Objectives

Suppose two threads increment a shared counter once each. We expect the variable to increase from 0 to 2. However, sometimes the result is only 1. One increment has been **lost** because both threads read the same old value and the later write overwrites the result of the earlier write. This phenomenon is called a **lost update**, a very common type of **race condition**.

After this lesson, you will be able to:

- Explain why `count++` consists of multiple logical steps and does not guarantee atomicity across threads.
- Draw an interleaving that causes a lost update, and distinguish atomicity, visibility, and ordering in the Java Memory Model.
- Reproduce a lost update **in a controlled manner** with a Java 17+ program producing a deterministic result.
- Fix it using `synchronized`, `Lock`, `AtomicInteger`/CAS, and `LongAdder`, choosing a solution based on read/write requirements.
- Identify pitfalls such as `volatile int count`, `get()+incrementAndGet()`, locking on the wrong object, incrementing across multiple executors, and reading results before tasks have completed.

**Scope:** Java SE, the Java Memory Model, and JDK synchronization APIs. Examples run standalone on Java 17 or later.

## 2. From One Line of Code to Three Read–Modify–Write Steps

Consider the example:

~~~java
class Counter {
    int count = 0;

    void increment() {
        count++;
    }
}
~~~

`count++` is equivalent in **computational semantics** to:

~~~java
int oldValue = count;        // (1) read
int newValue = oldValue + 1; // (2) compute new value
count = newValue;            // (3) write
~~~

These three steps are merely an **explanatory model**, not a claim that the virtual machine must emit exactly three machine instructions or cannot optimize them. What matters is that the entire read–modify–write operation **does not automatically become an atomic action** when multiple threads access shared state concurrently.

With multiple threads, each thread may read before the other writes. The final result depends on the interleaving order and synchronization constraints. Java guarantees the atomicity of a single ordinary `int` read or write, but **does not** guarantee atomicity for the entire `count++` expression.

### Interleaving That Loses an Increment

Initially `count = 10`; two threads T1 and T2 each perform one increment:

| Step | Thread T1 | Thread T2 | Shared Variable |
|---|---|---|---|
| 1 | Read `count = 10` into temporary variable | — | 10 |
| 2 | — | Read `count = 10` into temporary variable | 10 |
| 3 | Compute `10 + 1 = 11` | — | 10 |
| 4 | — | Compute `10 + 1 = 11` | 10 |
| 5 | Write `count = 11` | — | 11 |
| 6 | — | Write `count = 11` | 11 |

Expected result: **12**. Result in this execution schedule: **11**. Two operations were called, yet only one increment is reflected in the final state.

~~~text
                  T1                           T2
                  │                            │
             read count=10                     │
                  │                       read count=10
            compute 10+1                       │
                  │                       compute 10+1
             write count=11                    │
                  │                       write count=11
                  └─────────────┬──────────────┘
                                ▼
                         final count = 11
                           (expected 12)
~~~

Not every run loses an update: if T1 completes the entire increment before T2 reads, `count` can be 12. Therefore, a race condition does not mean the bug occurs on every execution.

## 3. Lost Update, Data Race, and the Java Memory Model

A **race condition** is an undesirable outcome caused by the ordering or interaction between concurrent executions. A **data race** under the Java Memory Model is a pair of conflicting accesses to the same variable from different threads, at least one of which is a write, not ordered by a happens-before relationship. A program can have a race condition that causes a logic bug even when individual accesses are properly synchronized, if a **sequence of actions** is not protected as a single cohesive operation.

Three concepts to distinguish:

| Property | Question | What does `count++` typically lack? |
|---|---|---|
| **Atomicity** | Does the entire update occur as a single uninterruptible step? | No. Two threads can read the same value and overwrite each other. |
| **Visibility** | Does a value written by one thread appear in time to another thread? | With unsynchronized fields, there is no guarantee of timely visibility of updates. |
| **Ordering** | Which operations must be observed under a happens-before relationship? | There is no required synchronization relationship between racy increments. |

The fact that an individual `int` read/write is atomic **does not imply** that the entire `count++` expression is atomic. Ensuring visibility also **does not automatically** ensure atomicity.

### Why Does `volatile` Not Fix a Lost Update?

~~~java
class VolatileCounter {
    volatile int count;

    void increment() {
        count++; // STILL has lost update
    }
}
~~~

`volatile` provides visibility and ordering semantics: a volatile write and a corresponding volatile read establish happens-before relationships according to the Java Memory Model rules. However, two threads can still read the same value (even if it is the latest value at the time of the read), both compute `+1`, and both overwrite the variable. There is no lock or atomic read–modify–write operation to eliminate that interleaving.

Example:

~~~text
volatile count = 7
T1: read 7
T2: read 7
T1: write 8
T2: write 8
=> count = 8, one update lost
~~~

Remember: `volatile` is suitable for certain independent status flags like `stopRequested`; it does not replace `synchronized` or atomic APIs for accurate counter increments.

### Why Do `sleep()`, `yield()`, or Running Fast/Slow Not Protect Against It?

`Thread.sleep(...)` only asks the thread to sleep for a duration; `Thread.yield()` is a hint to the scheduler. Neither call turns `count++` into an atomic operation or creates a critical section. Adding `sleep` may make the bug easier to observe in a test, but it **does not prove** a fix is correct. Multi-core CPUs, JIT compilation, caches, and system load change the execution schedule; "ran 1,000 times without error" is still not enough to claim thread safety.

## 4. Reproducing the Bug with a Deterministic Result

The common test of `2 threads × 100_000 count++` can yield a result lower than 200,000, but it is **unreliable**: many runs still produce 200,000. To understand a lost update precisely, we deliberately make both threads **read the variable first**, and only then open the gate for both to write.

Save the file **LostUpdateDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class LostUpdateDemo {
    private static int count = 0;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothHaveRead = new CountDownLatch(2);
        CountDownLatch allowWriting = new CountDownLatch(1);

        Runnable increment = () -> {
            int snapshot = count;
            bothHaveRead.countDown(); // signal that count has been read

            try {
                allowWriting.await(); // do not write until the other thread has read
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            count = snapshot + 1; // write based on stale snapshot
        };

        Thread first = new Thread(increment, "first");
        Thread second = new Thread(increment, "second");

        first.start();
        second.start();

        bothHaveRead.await(); // ensure both have read count = 0
        allowWriting.countDown(); // open the gate for writing
        first.join();
        second.join();

        System.out.println("expected=2");
        System.out.println("actual=" + count);
        System.out.println("lost=" + (2 - count));
    }
}
~~~

Compile and run:

~~~bash
javac LostUpdateDemo.java
java LostUpdateDemo
~~~

Output under normal conditions, without external interruption:

~~~text
expected=2
actual=1
lost=1
~~~

**Why this result is deterministic:**

1. `bothHaveRead` starts at 2. Each worker reads `count` into a **separate local variable**, then counts down.
2. Main only opens `allowWriting` after knowing **both reads have completed**. Before that point, neither worker is allowed to write `count`.
3. Since `count` is initially 0 and neither thread has written yet, both snapshots are 0.
4. Once the gate opens, each worker writes `0 + 1 = 1`. Regardless of which writes first, the final value is 1.
5. `join()` waits for both workers to finish before main reads the result. `join` also establishes a happens-before relationship from the worker's actions to the waiting thread.

**Crucial point:** `CountDownLatch` in this example is **used to stage a buggy interleaving**, not to fix the bug. Waiting for both threads to finish reading before allowing them to write makes the lost update guaranteed. To fix it, you must protect the **read + compute + write** operation inside a shared atomic operation or critical section.

## 5. First Fix: Using `synchronized`

A shared monitor lock can ensure that only one thread at a time executes the entire read–modify–write section.

~~~java
class SynchronizedCounter {
    private int count;

    public synchronized void increment() {
        count++;
    }

    public synchronized int get() {
        return count;
    }
}
~~~

`synchronized` on an instance method uses the monitor of the object itself (`this`). When T1 holds the monitor, T2 wanting to enter `increment()` on the **same instance** must wait. When T1 exits the critical section, T2 reads the updated value. Unlocking the monitor and subsequently locking the same monitor establishes a happens-before relationship, providing both mutual exclusion and visibility.

**Condition:** All relevant accesses must follow the proper synchronization protocol. If another method writes directly to `count` without holding the same monitor, the protocol no longer holds.

### Private Lock When Separation from the Object Monitor Is Needed

~~~java
class LockedCounter {
    private final Object lock = new Object();
    private int count;

    void increment() {
        synchronized (lock) {
            count++;
        }
    }

    int get() {
        synchronized (lock) {
            return count;
        }
    }
}
~~~

Using `private final Object lock` prevents external code from accidentally locking on the same monitor via `synchronized(this)`. Both `increment` and `get` must use the **same lock object**.

A common mistake:

~~~java
void brokenIncrement() {
    synchronized (new Object()) { // each call creates a separate lock
        count++;
    }
}
~~~

The snippet above **illustrates a bug** inside a class with a `count` field; it does not resolve the race between different calls. Each thread holds its own newly created monitor, so there is no mutual exclusion on the shared variable.

### Using `ReentrantLock` When More Control Is Needed

~~~java
import java.util.concurrent.locks.ReentrantLock;

class ReentrantCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int count;

    void increment() {
        lock.lock();
        try {
            count++;
        } finally {
            lock.unlock();
        }
    }

    int get() {
        lock.lock();
        try {
            return count;
        } finally {
            lock.unlock();
        }
    }
}
~~~

`ReentrantLock` enables capabilities such as `tryLock()`, `lockInterruptibly()`, and `Condition` objects when specific needs arise. Always place `unlock()` inside a `finally` block after successfully acquiring the lock. For a simple counter, `synchronized` is usually clearer and less error-prone.

## 6. Second Fix: `AtomicInteger` and Atomic Read–Modify–Write

Java provides `java.util.concurrent.atomic.AtomicInteger` for an `int` value that needs atomic updates without writing a monitor lock for every increment.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class AtomicCounter {
    private final AtomicInteger count = new AtomicInteger();

    void increment() {
        count.incrementAndGet();
    }

    int get() {
        return count.get();
    }
}
~~~

`incrementAndGet()` performs an atomic increment with appropriate memory visibility semantics. Each successful update has a **linearization point**: increments can be reasoned about as having a valid sequential order even when called concurrently by multiple threads.

Common APIs:

| Method | Meaning |
|---|---|
| `get()` | Gets the current value with the volatile read semantics of the atomic API. |
| `set(v)` | Writes the value with volatile write semantics. |
| `getAndIncrement()` | Atomically increments by 1; **returns the old value**. |
| `incrementAndGet()` | Atomically increments by 1; **returns the new value**. |
| `addAndGet(delta)` | Atomically adds `delta`; returns the new value. |
| `getAndAdd(delta)` | Atomically adds `delta`; returns the old value. |
| `compareAndSet(expected, update)` | If the value is still equal to `expected`, atomically attempts to set it to `update`; returns a boolean indicating success/failure. |

The implementation typically relies on atomic/CAS mechanisms supported by the JVM and hardware. CAS may need to retry under contention. Do not infer from method names that every increment always completes in constant time or has zero overhead.

**Do not increment an atomic counter like this:**

~~~java
AtomicInteger count = new AtomicInteger();
int old = count.get();
count.set(old + 1); // two separate atomic calls, but the combination is NOT atomic
~~~

Two threads can still both observe `get() = 0`, and then both call `set(1)`. Even though each `get` and `set` call has proper memory semantics, the overall read–modify–write sequence remains unprotected. You must use `incrementAndGet()`, `getAndIncrement()`, `addAndGet()`, or a proper CAS loop.

## 7. Third Fix: `LongAdder` When Many Threads Contend on the Same Counter

`LongAdder` is optimized for the case where **very many threads frequently accumulate** into the same metric. Instead of always updating a single location like `AtomicLong`, the implementation can split updates across multiple internal cells to reduce contention, and then sum them when read.

~~~java
import java.util.concurrent.atomic.LongAdder;

class MetricsCounter {
    private final LongAdder requests = new LongAdder();

    void recordRequest() {
        requests.increment();
    }

    long total() {
        return requests.sum();
    }
}
~~~

Advantages and limitations:

- `increment()` / `add(n)` are well suited for high-frequency metrics such as total requests, event counts, or hit counts.
- `sum()` is **not an atomic snapshot** while other threads are still updating: the read value may omit concurrent updates.
- `sumThenReset()` is also not a safe choice for collecting exact figures while concurrent updates are still occurring; the documentation notes it should only be used when no concurrent updates are guaranteed if a complete value is required.
- `LongAdder` does not provide `compareAndSet` on the sum; therefore, it is unsuitable if you need a rule like "only increment if the value has not reached a limit."
- Performance benefits depend on workload, contention level, core count, memory, and JDK; do not assume it is always faster than `AtomicLong`.

**Which one should you choose?**

| Requirement | Usually Reasonable Choice | Reason |
|---|---|---|
| A single exact counter, continuously updated and read | `AtomicInteger`/`AtomicLong` | Atomic increment, simple API, provides CAS. |
| Multiple fields that must maintain a shared invariant | `synchronized`/`Lock` | Protects the entire multi-step operation under the same critical section. |
| Statistical counter with many writers, only needing periodic totals | `LongAdder` | Reduces contention, accepting that `sum()` is not an atomic snapshot during writes. |
| Conditional operation needed, such as `count < limit` then increment | CAS loop or lock | Check and update must be a single logically atomic action. |
| Single-threaded scenario with no shared variable | Plain `int`/`long` | No need to pay synchronization overhead when there is genuinely no concurrent access. |

## 8. Standalone Example: Comparing Three Safe Counter Approaches

The program below uses two threads, each incrementing 100,000 times. It does not rely on race luck to succeed: all three counters protect their updates. `join()` ensures all increments have completed before reading the results.

Save the file **SafeCountersDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public class SafeCountersDemo {
    interface Counter {
        void increment();
        long value();
    }

    static class SynchronizedCounter implements Counter {
        private long count;

        @Override
        public synchronized void increment() {
            count++;
        }

        @Override
        public synchronized long value() {
            return count;
        }
    }

    static class AtomicCounter implements Counter {
        private final AtomicInteger count = new AtomicInteger();

        @Override
        public void increment() {
            count.incrementAndGet();
        }

        @Override
        public long value() {
            return count.get();
        }
    }

    static class AdderCounter implements Counter {
        private final LongAdder count = new LongAdder();

        @Override
        public void increment() {
            count.increment();
        }

        @Override
        public long value() {
            return count.sum();
        }
    }

    static void repeat(Counter counter) {
        for (int i = 0; i < 100_000; i++) {
            counter.increment();
        }
    }

    static long run(Counter counter) throws InterruptedException {
        Thread t1 = new Thread(() -> repeat(counter), "worker-1");
        Thread t2 = new Thread(() -> repeat(counter), "worker-2");
        t1.start();
        t2.start();
        t1.join();
        t2.join();
        return counter.value();
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("synchronized=" + run(new SynchronizedCounter()));
        System.out.println("atomic=" + run(new AtomicCounter()));
        System.out.println("longAdder=" + run(new AdderCounter()));
    }
}
~~~

Compile and run:

~~~bash
javac SafeCountersDemo.java
java SafeCountersDemo
~~~

Output:

~~~text
synchronized=200000
atomic=200000
longAdder=200000
~~~

Why does `LongAdder.sum()` give the complete result here even though it is not an atomic snapshot? Because main waits for both threads to finish via `join()`; when `sum()` is called, **no writers are updating anymore**. In another program, if `sum()` is read while workers are still running, the result is a sum observed over a time interval and may differ from an instantaneous total.

**Do not treat these three runs as a benchmark.** Execution order, JIT warmup, OS fluctuations, and workload size can change timings. The purpose of the example is to demonstrate correctness, not to prove by what percentage `LongAdder` is faster.

## 9. Advanced Note: A Sequence of Multiple Atomic APIs Can Still Be Wrong

A common design is limiting the number of reservations:

~~~java
AtomicInteger booked = new AtomicInteger();
int capacity = 10;

if (booked.get() < capacity) {
    booked.incrementAndGet(); // WRONG if two threads enter the if branch together
}
~~~

Although `get()` and `incrementAndGet()` are each atomic, the **check-then-increment** operation is not atomic. When `booked=9`, two threads can both see `9<10` and both increment: the result can end up as **11**, violating the capacity of 10.

### Fixing with a `compareAndSet` Loop

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class CapacityCounter {
    private final AtomicInteger booked = new AtomicInteger();

    public boolean tryBook(int capacity) {
        if (capacity < 0) {
            throw new IllegalArgumentException("capacity must be >= 0");
        }
        while (true) {
            int current = booked.get();
            if (current >= capacity) {
                return false;
            }
            if (booked.compareAndSet(current, current + 1)) {
                return true;
            }
            // Concurrent update occurred: re-read the new state and retry.
        }
    }

    public int count() {
        return booked.get();
    }

    public static void main(String[] args) {
        CapacityCounter counter = new CapacityCounter();
        System.out.println(counter.tryBook(1));
        System.out.println(counter.tryBook(1));
        System.out.println(counter.count());
    }
}
~~~

Compile and run:

~~~bash
javac CapacityCounter.java
java CapacityCounter
~~~

Output:

~~~text
true
false
1
~~~

CAS succeeds only if the value is still `current` at the update step; if another thread has modified the value, the call fails and the loop retries based on the new state. This pattern preserves the `count <= capacity` invariant when all relevant changes go through the same protocol, `capacity` is passed consistently, and there are no external updates. The example manages an in-memory counter within a single JVM; it does not automatically synchronize data with external systems or multiple processes.

**A caution about multi-state invariants:** Some invariants involving multiple variables, multiple objects, or external resources cannot be fixed with a single `AtomicInteger`. When checking and updating multiple fields must be consistent, design a shared critical section, immutable state replaced via CAS, or an appropriate coordination mechanism for that resource scope.

## 10. Lock, Atomic, and Volatile from a Happens-Before Perspective

### `synchronized`

One thread exiting a monitor (`unlock`) happens-before another thread entering (`lock`) **that same monitor**. Within the same critical section, mutual exclusion prevents two threads from performing read–modify–write on the counter simultaneously. Reading/writing outside the lock, or using two different lock objects, breaks this synchronization guarantee.

### `AtomicInteger`

`get()`, `set()`, and atomic update operations have defined memory effects; `incrementAndGet()` is an atomic update. Using multiple separate calls such as `get()` followed by `set(...)` creates an interleaving window. Therefore, you must choose an update operation that matches the requirements **of the entire business action**.

### `volatile`

Volatile visibility and ordering allow threads to observe updates under happens-before rules, but do not grant mutual exclusion for read–modify–write. `volatile int count++` is still racy. Conversely, a `volatile boolean running` flag that only needs independent state reads/writes can be suitable if there are no complex invariants.

### `join()`, `CountDownLatch`, and `Future.get()`

These are tools for **lifecycle coordination and observation synchronization**, and do not automatically fix a broken increment:

- After a thread terminates normally and another thread calls `join()` on it, the actions of the finished thread happen-before the actions after `join()` in the waiting thread.
- `CountDownLatch` provides a happens-before relationship via `countDown()` and `await()` per its API contract; latches commonly help coordinate start times, completion, or staged ordering.
- With `Future`, the actions of the asynchronous task happen-before the actions following the corresponding `Future.get()`. However, `Future.get()` does not magically make a counter incremented by multiple workers atomic.

Only calling `join()` after **all writes have completed** gives main a sound basis for reading the final result. Without waiting, printing the counter may miss increments that workers have not finished executing yet — this is an observation-timing issue in addition to lost updates.

## 11. Common Mistakes and How to Identify Them

### Mistake 1: Assuming a `static` shared variable is "protected"

`static` only makes a field belong to the class, meaning multiple instances can share the value. It has **no** atomic or synchronized properties. `final` on a counter reference also does not make operations that mutate internal counter state thread-safe.

### Mistake 2: Each thread holds a different `Counter`

If each thread increments its own instance, you are no longer testing lost updates on the same variable. When a shared total is intended, exactly one shared counter must be passed to the workers. Likewise, if using `synchronized`, all workers must synchronize on the same instance/monitor.

### Mistake 3: `synchronized` on the right method, but other access paths bypass the lock

One synchronized method cannot save unprotected direct writes to the field. Prefer `private` fields and a consistent update API. Avoid exposing mutable state references that can be modified elsewhere without holding the lock.

### Mistake 4: Using `volatile` for increment or check-then-increment

`volatile` does not provide atomic read–modify–write; neither does `AtomicInteger.get()` combined with `AtomicInteger.set()`. Choose `incrementAndGet`, CAS, or a lock covering the entire operation.

### Mistake 5: Starting two threads without `join` and checking `count` immediately

`start()` only requests execution; it does not wait for completion. If main prints the result right after starting, the value may be low because execution has not finished, even when using an atomic counter. Wait via `join()`, `Future.get()`, or `CountDownLatch` according to the problem's semantics.

### Mistake 6: Using `int` for large totals despite overflow

`int` has a range from -2^31 to 2^31-1. When exceeding this range, Java integer addition overflows according to 32-bit integer rules; the counter can become negative even when every update is atomic. `AtomicInteger` **does not prevent overflow**. Choose `long`, `AtomicLong`, `LongAdder`, or design a limit/overflow policy as required.

### Mistake 7: Using `LongAdder` as an exact instantaneous balance

`LongAdder.sum()` while writers are still running is not an atomic snapshot. For cumulative metrics, this is a reasonable tradeoff; for an invariant that needs to decide "if space remains, then increment," you must use atomic CAS or a lock.

### Mistake 8: Assuming races only happen on multi-core CPUs

Even on a single core, the scheduler can switch threads between steps. Multiple cores increase the likelihood of simultaneous execution, but are not a prerequisite for lost updates. Thread scheduling and the Java Memory Model are both part of the problem.

### Mistake 9: Confusing lost updates with log ordering issues

Logs printed in an indeterminate order across threads are not necessarily a lost update. Check the **state/invariant** of the shared counter after tasks complete. There must be an exact expectation: N workers × M increments should reach N×M if there is no overflow and no dropped/cancelled tasks.

### Mistake 10: Using a quick microbenchmark to declare the "best" solution

`synchronized` can be very suitable for its simplicity, `AtomicInteger` fits single-counter operations, and `LongAdder` fits high-writer metrics. Actual cost varies with contention, core count, runtime, and read/write ratio; verify correctness first, and benchmark the right workload later.

## 12. Testing and Diagnostic Guidelines

A thorough testing strategy consists of two layers:

**Layer 1 — controlled interleaving test:** Use `CountDownLatch` as in the first example to prove that two threads really can read the same snapshot and overwrite each other. This is a **deterministic logic proof**, rather than merely waiting for the scheduler to get lucky.

**Layer 2 — testing under load:** Run multiple tasks incrementing a shared counter, start them concurrently with a barrier/latch, then join or await `Future`. Compare against `expected = threads × incrementsPerThread`. Repeat across multiple configurations. A passing result from one stress run **does not prove** the code is race-free; an incorrect result is proof of a problem. When writing concurrency tests, ensure tasks are not unexpectedly cancelled/interrupted and that the expected calculation does not overflow.

To go deeper, you can use specialized tools like **OpenJDK jcstress** to test observable outcomes under various interleavings/JMM rules, or inspect thread dumps/JFR when suspecting contention or blocked threads. Thread dumps primarily show waiting states; they do not by themselves prove `count++` is atomic. In production code, always examine counter data, error rates, retry logic, and dropped updates together.

### Code Review Checklist

- **One shared value?** Confirm all workers use the same counter, without cloning the variable or creating separate counters.
- **Any read–modify–write?** `++`, `--`, `x += n`, `map.put(key, map.get(key)+1)` all require atomicity evaluation.
- **Any conditional update?** `if (count < limit) count++` requires atomicity across both the check and the update.
- **Where is synchronization?** Same monitor, same `Lock`, atomic API, or a proper thread confinement protocol.
- **When is the result read?** Wait for work to finish; distinguish reading a snapshot while writers are active from reading the final total.
- **Is the data type wide enough?** Check for overflow, business limits, and metric requirements.
- **Are multiple fields updated?** A single atomic counter does not automatically maintain consistency across all related fields.

## 13. Self-Check Exercises

**Question 1.** Two threads each increment `count` 10,000 times with `volatile int count`. Is the value guaranteed to be 20,000?

**Answer:** No. `volatile` provides visibility and ordering, but does not make `++` atomic; interleaving can cause lost updates.

**Question 2.** One thread uses `counter.incrementAndGet()`, while another uses `counter.get(); counter.set(old + 1)` on the same `AtomicInteger`. Is this thread-safe?

**Answer:** No. The `get()+set()` path is still a non-atomic compound update; all writers must follow the same proper update protocol.

**Question 3.** Does `synchronized` on two different instances protect the same `static` variable?

**Answer:** No, if each instance uses its own `this` monitor. You must use **one shared lock** for the `static` variable, or an appropriate atomic field.

**Question 4.** Is `LongAdder.sum()` an exact snapshot while multiple workers are calling `increment()`?

**Answer:** No. It is suitable for metric totals with concurrent updates, but does not guarantee an atomic snapshot. After all workers have finished and joined, `sum()` reflects the completed increments.

**Question 5.** Why is `Future.get()` not enough to prevent lost updates?

**Answer:** `get()` waits for the task and observes its result/exception with appropriate memory consistency; if the task itself performed a racy `count++` in parallel, waiting for completion does not recover lost updates.

## 14. Conclusion and References

A shared counter must satisfy **two independent conditions**: updates must be atomic if multiple threads increment concurrently; and the result must be observed with a proper synchronization relationship and at the right time. Plain `count++` lacks atomicity. `volatile` only addresses visibility/ordering, without locking the three read–compute–write steps. Choose `synchronized`/`Lock` when multi-step operations require a shared invariant, `AtomicInteger` or `AtomicLong` when updating a single counter needs exactness and can use CAS, and `LongAdder` for high-contention increment metrics where a non-atomic snapshot during writes is acceptable.

Official API Documentation:

- Java Language Specification §17 — Threads and Locks: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- `AtomicInteger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- `LongAdder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- `CountDownLatch`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- `ReentrantLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html

**Core takeaway:** *An atomic read plus an atomic write do not automatically form an atomic increment.* When fixing a lost update, you must protect the entire read–modify–write — and protect any related conditions as well.
