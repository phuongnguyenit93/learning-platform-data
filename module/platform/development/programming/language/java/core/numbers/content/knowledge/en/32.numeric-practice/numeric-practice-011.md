# Comparing Plain, Atomic, and Adder Counters in Java

## 1. Problem to Solve

Suppose an application has four threads, each processing 100,000 events and needing to increment a shared counter. **The expected value is 400,000**, regardless of thread scheduling. Three common approaches are:

- **Plain counter:** an `int` or `long` variable updated with `count++`. Simple and suitable when only one thread owns the data, yet **unsafe** if multiple threads increment concurrently without synchronization.
- **Atomic counter:** `AtomicInteger` or `AtomicLong`. Provides atomic read, increment, add, and compare-and-set operations on a shared value.
- **Adder counter:** `LongAdder`. Allows multiple threads to add to the counter, potentially striping updates across multiple cells to reduce contention; the sum is computed when observed.

A very important baseline for comparison is a **plain counter protected by `synchronized`**. It is still a primitive counter, yet has a lock guarding every appropriate access, so it can be completely correct. The distinction is *plain unprotected* vs. *plain protected*, not that primitives are always wrong.

You must answer all three questions: **Is the result correct under concurrency? Does each read require an atomic snapshot? And is performance actually better on the real workload?**

## 2. Why Can count++ Lose Increments?

~~~java
class Counter {
    long count;

    void increment() {
        count++; // NOT atomic when multiple threads write concurrently
    }
}
~~~

`count++` is a short expression, yet semantically it consists of:

1. Reading the old value.
2. Computing the old value plus 1.
3. Writing the new value back.

When two threads both see `count == 5`, both compute 6 and both write 6, so the total increases only once instead of twice. This is a *lost update*, a form of **race condition**.

| Time | Thread A | Thread B | Stored value |
| --- | --- | --- | ---: |
| 0 | — | — | 5 |
| 1 | Read 5 | — | 5 |
| 2 | — | Read 5 | 5 |
| 3 | Compute 6 | — | 5 |
| 4 | — | Compute 6 | 5 |
| 5 | Write 6 | — | 6 |
| 6 | — | Write 6 | 6 |

A real program might happen to print the expected number in a few trial runs, yet that **does not prove thread safety**. Different interleaving, different core counts, or different JVM optimizations can expose the race.

### Volatile does not fix ++

~~~java
class Counter {
    volatile long count;

    void increment() {
        count++; // lost updates can still occur
    }
}
~~~

`volatile` provides visibility and ordering semantics for operations on the variable under the Java Memory Model. It **does not combine read–add–write into a single atomic operation**. Two threads can still read the same value and write the same result. Do not use `Thread.sleep` or add delays to fix a race: they only alter timing.

If a counter **belongs strictly to one thread**, a plain variable is a good choice; not every counter needs to be atomic.

## 3. Behavior Comparison Table

| Criterion | Unsynchronized `long count++` | `AtomicLong` | `LongAdder` |
| --- | --- | --- | --- |
| Increment from multiple threads without losing updates? | **No** | Yes | Yes |
| Instantaneous read has atomic semantics? | Not guaranteed | `get()` does | `sum()` is not an atomic snapshot |
| Retrieve value before/after each increment? | Unsafe if shared | Yes: `getAndIncrement`, `incrementAndGet` | No |
| Compare-and-set a value? | No | Yes: `compareAndSet` | No |
| Under high contention | Logically incorrect | Contention updating the same state | Can stripe updates to increase throughput |
| Memory cost | Very small | Object holding atomic state | Can be larger due to extra cells |
| Typically suitable cases | Single-thread or externally synchronized | Needs linearizable operations/CAS/IDs | Metrics, write-heavy, infrequent exact reads |

**Do not infer a fixed speed ranking from the table.** `AtomicLong` can be faster than or comparable to `LongAdder` under low contention; `synchronized` can also be fast enough. Only benchmarking the actual workload can decide.

## 4. AtomicInteger and AtomicLong

### 4.1. Basic methods

~~~java
import java.util.concurrent.atomic.AtomicLong;

AtomicLong count = new AtomicLong(0);

long afterFirst = count.incrementAndGet(); // 1
long beforeSecond = count.getAndIncrement(); // 1
long current = count.get(); // 2
long afterAdd = count.addAndGet(10); // 12
~~~

Method names indicate the return value:

- `incrementAndGet()`: increments, then returns the new value.
- `getAndIncrement()`: returns the old value, then increments.
- `addAndGet(delta)`: adds, then returns the new value.
- `getAndAdd(delta)`: returns the old value, then adds.
- `get()` and `set(...)`: reads/writes a shared value.
- `compareAndSet(expected, update)`: updates only if the current value equals expected, returning `true` on success.

`AtomicInteger` provides a 32-bit variant with matching method names. `AtomicLong` uses 64 bits, suitable for counters that can exceed `Integer.MAX_VALUE`.

### 4.2. Why are updates not lost?

Atomic increments are synchronized by mechanisms provided by the JVM/hardware, commonly based on **CAS (compare-and-swap)** or an equivalent hardware operation. When two threads simultaneously increment from 5, only one can update to 6 first; the other must work against the new state and update to 7.

By contract, each atomic operation can be understood as occurring at a **single atomic point** (*linearization point*) on the variable. In performance terms, many threads competing on one state can force CAS retries; thus contention has a cost.

Do not assume every JDK or CPU runs the exact same machine instruction sequence; programmers rely on the API contract, not assumptions about specific implementations.

### 4.3. A get followed by an increment does not form a transaction

~~~java
if (count.get() < 100) {
    count.incrementAndGet();
}
~~~

Even though both calls **are individually atomic**, the combined "check-then-increment" pair **is not atomic**. Two threads can both read 99, both see the condition as true, and push the result to 101.

To enforce a strict cap, use a CAS loop:

~~~java
static boolean tryIncrementBelow(
        AtomicLong counter, long limit) {
    while (true) {
        long current = counter.get();
        if (current >= limit) {
            return false;
        }
        long next = current + 1;
        if (counter.compareAndSet(current, next)) {
            return true;
        }
    }
}
~~~

This is an illustrative method placed in a class with `AtomicLong` imported. If `current < limit` and `limit` is a valid long value, `current + 1` does not overflow. To preserve the invariant, all threads modifying the same counter must follow compatible update protocols.

`AtomicLong.updateAndGet(fn)` also supports an update function, yet the function can re-run when CAS fails: **never put side effects** like database writes or sending notifications inside `fn`.

### 4.4. When to choose Atomic?

- Needing to issue sequence numbers per increment, e.g. `getAndIncrement()` within non-overflowing bounds.
- Needing a snapshot value at a logical point in time for **a single variable**.
- Needing CAS, conditional updates, `getAndSet`, or state management tightly tied to each operation.
- Contention is not too high, or benchmarks show atomic meets requirements.

An atomic for one variable does not automatically protect invariants spanning **multiple independent variables**. If two fields must change together as a transaction, use proper synchronization or encapsulate the entire state into an immutable object updated through an `AtomicReference`.

## 5. LongAdder: Reducing Update Contention

### 5.1. Usage

~~~java
import java.util.concurrent.atomic.LongAdder;

LongAdder requests = new LongAdder();

requests.increment(); // +1
requests.add(5);      // +5
requests.decrement(); // -1

long total = requests.sum(); // 5 if no other concurrent updates
~~~

`LongAdder` maintains a logical value as a sum, yet may use multiple **internal counter cells**. Under contention, threads do not all have to update the exact same cell. This can improve throughput for "write very frequently, read occasionally" metrics.

It does not replace every role of atomics because it trades off value observation semantics.

### 5.2. sum() is not an atomic snapshot while updates are in progress

When calling `sum()`, LongAdder sums the cells. If other threads are still incrementing, different cells may be read at **different points in time**. Therefore:

- `sum()` is useful for near-real-time metrics.
- `sum()` is **not linearizable** like `AtomicLong.get()`.
- Do not use a `sum()` check to enforce quota limits requiring atomic check-and-update.
- Once **all updates have finished** and are properly synchronized, `sum()` returns the exact final total.

In the program in Section 7, all threads have been `join()`ed before `sum()` is called.

### 5.3. Do not use an adder to issue IDs

The following snippet is **wrong for uniqueness**:

~~~java
long id = requests.sum();
requests.increment();
~~~

Two threads can read the same sum before incrementing and receive the same id. LongAdder guarantees no lost additions, **not per-increment before/after values**. Use `AtomicLong.getAndIncrement()` when issuing numbers from a single JVM state, while also managing overflow and cross-JVM coordination requirements.

### 5.4. reset and sumThenReset

~~~java
long sinceLastCheck = requests.sumThenReset();
~~~

`sumThenReset()` is useful for periodic stats collection once **no concurrent updates** are guaranteed. It is not an atomic snapshot-and-reset with ongoing increments. If resetting while threads are incrementing, some updates may not be bucketed into periods as expected.

When exact period boundaries are required, design a stop/handoff protocol for updates, locking, two synchronized alternating buckets, or timestamped event logging. Do not treat `sumThenReset()` as a safe "period-closing" operation under arbitrary concurrency.

### 5.5. Related variants

`DoubleAdder` supports summing `double` values yet still has binary rounding issues; do not use it instead of `BigDecimal` when money must be exact under decimal rules. `LongAccumulator` applies an associative operator with an identity for aggregations other than addition.

## 6. Synchronized Counter: A Safe Baseline

~~~java
class LockedCounter {
    private long count;

    synchronized void increment() {
        count++;
    }

    synchronized long get() {
        return count;
    }
}
~~~

`synchronized` guarantees only one thread at a time executes the critical section under the same monitor. Calling `get()` also uses that monitor, providing proper visibility.

This approach can work well when you need:

- Simple code that is easy to prove correct.
- A group of shared fields that must maintain an invariant.
- Multi-step update logic, not just simple addition.
- Low contention, or profiling shows it is not a bottleneck.

Do not guard `increment()` with a lock while leaving another read/write path accessing `count` without matching synchronization. When there are multiple update paths, all must follow the same protection protocol.

## 7. Java 17+ Example with Deterministic Results

In a pure stress test, `count++` may fail or coincidentally pass depending on thread scheduling, making stdout non-deterministic. Therefore, the first part of the program **deliberately separates read and write** so both threads read `0` before writing. This faithfully reproduces the lost-update mechanism of `count++` while producing deterministic output.

The second part runs four threads, each incrementing three safe counters 100,000 times. Only after the threads finish does main read the totals.

Create the file **`CounterComparisonDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public class CounterComparisonDemo {
    static class PlainCounter {
        int count;
    }

    static class LockedCounter {
        private long count;

        synchronized void increment() {
            count++;
        }

        synchronized long get() {
            return count;
        }
    }

    static int forcedLostUpdate() throws InterruptedException {
        PlainCounter counter = new PlainCounter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch go = new CountDownLatch(1);

        Runnable task = () -> {
            int snapshot = counter.count;
            bothRead.countDown();

            try {
                go.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            counter.count = snapshot + 1;
        };

        Thread a = new Thread(task);
        Thread b = new Thread(task);
        a.start();
        b.start();

        bothRead.await();
        go.countDown();

        a.join();
        b.join();
        return counter.count;
    }

    public static void main(String[] args)
            throws InterruptedException {
        System.out.println("plain forced collision: "
                + forcedLostUpdate() + " (expected 2)");

        final int threads = 4;
        final int repeats = 100_000;

        AtomicLong atomic = new AtomicLong();
        LongAdder adder = new LongAdder();
        LockedCounter locked = new LockedCounter();

        Thread[] workers = new Thread[threads];
        CountDownLatch start = new CountDownLatch(1);

        for (int i = 0; i < threads; i++) {
            workers[i] = new Thread(() -> {
                try {
                    start.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }

                for (int n = 0; n < repeats; n++) {
                    atomic.incrementAndGet();
                    adder.increment();
                    locked.increment();
                }
            });
            workers[i].start();
        }

        start.countDown();

        for (Thread worker : workers) {
            worker.join();
        }

        long expected = (long) threads * repeats;
        System.out.println("expected: " + expected);
        System.out.println("atomic after join: " + atomic.get());
        System.out.println("adder after join: " + adder.sum());
        System.out.println("locked after join: " + locked.get());
        System.out.println("all safe counters exact: "
                + (atomic.get() == expected
                && adder.sum() == expected
                && locked.get() == expected));
    }
}
~~~

Compile and run:

~~~bash
javac CounterComparisonDemo.java
java CounterComparisonDemo
~~~

Stdout (verified with Java):

~~~text
plain forced collision: 1 (expected 2)
expected: 400000
atomic after join: 400000
adder after join: 400000
locked after join: 400000
all safe counters exact: true
~~~

**Explanation:** `CountDownLatch` in `forcedLostUpdate` only coordinates the two threads so both read before either is allowed to write; it does not make the counter atomic. Since both snapshots are 0, both write 1, resulting in 1 instead of 2. The program demonstrates a reproducible *lost update*; if replaced with uncoordinated `count++`, whether the bug triggers on any single run cannot be guaranteed.

The remaining three counters complete 400,000 increments accurately. `join()` ensures threads have finished before checking totals. Putting all three counters in one loop **is only for checking correctness**, not a speed benchmark, because the presence of synchronized and synchronization primitives affects scheduling and CPU interactions.

## 8. Atomics and Adders Do Not Prevent Numeric Overflow

Thread-safe means updates are not lost to races, **not that results stay within the type's range**.

~~~java
AtomicLong atomic = new AtomicLong(Long.MAX_VALUE);
long wrapped = atomic.incrementAndGet();
// Long.MIN_VALUE due to long overflow
~~~

`AtomicInteger` can also overflow `int`. `LongAdder` uses `long` values, so a separate policy is still needed when the sum can exceed `long` range.

If overflow is an error, one approach with AtomicLong:

~~~java
AtomicLong safe = new AtomicLong(Long.MAX_VALUE - 1);

long max = safe.updateAndGet(Math::incrementExact);
// Long.MAX_VALUE

// The next call throws ArithmeticException:
// safe.updateAndGet(Math::incrementExact);
~~~

`Math.incrementExact` throws an error instead of wrapping. The update function must **have no side effects**, because `updateAndGet` may re-invoke it on CAS failure. This is a suitable correctness mechanism when workload/contract permits, not a claim that every counter must use this exact pattern.

If valid values can exceed `Long.MAX_VALUE`, consider a `BigInteger` model with explicitly designed synchronization; `LongAdder` is not arbitrary-precision.

## 9. Snapshots and Observation Boundaries

### 9.1. AtomicLong.get()

`AtomicLong.get()` reads an atomic value, with linearizable semantics for that variable's state. However:

~~~java
long first = atomic.get();
long second = atomic.get();
~~~

the two reads may differ because another thread incremented in between. **One atomic operation does not turn a sequence of consecutive operations into a transaction**.

### 9.2. LongAdder.sum()

`sum()` can read internal cells at different times while updates are ongoing. It suits near-real-time metrics, yet is unsuitable for quota checks requiring atomic accuracy.

Once workers have finished, `join()` and corresponding synchronization ensure their changes are properly observed, and `sum()` returns the final total. This is a critical precondition for writing valid LongAdder tests.

### 9.3. One JVM vs. Multiple JVMs

`AtomicLong` or `LongAdder` only synchronizes state within **a single object/JVM**. If an application runs three instances on three servers, each instance has its own counter; there is no automatic global counter. You must design a distributed system, database, event stream, or ID-generation service per requirements if cross-node consistency is needed.

## 10. Performance: Do Not Just Time One Loop

Factors to observe:

- **Contention:** many threads attempting to update concurrently.
- **Throughput:** increments per second.
- **Latency:** per-operation delay and tail distribution.
- **Memory footprint:** AtomicLong is typically more compact than a LongAdder that has expanded into many cells.
- **Read frequency:** with LongAdder, calling `sum()` frequently shifts the read/write cost ratio.
- **Thread scheduling, JIT, GC, CPU topology:** strongly affect microbenchmarks.

There is no formula stating "LongAdder is always N times faster than AtomicLong." Under high contention and infrequent reads, LongAdder often has a throughput advantage. With few threads, striping/summing overhead may not pay off and AtomicLong is simpler. When complex invariants are needed, `synchronized` may be the right design even if locking has a cost.

### 10.1. How to benchmark with JMH

**JMH (Java Microbenchmark Harness)** is far more appropriate than a single `System.nanoTime()` measurement. A meaningful benchmark needs to:

1. Separate `plain/AtomicLong/LongAdder` or `synchronized` benchmarks by target, never updating all in the same loop.
2. Test multiple thread counts: 1, 2, 4, 8... matching real load.
3. Ensure the counter is actually shared among threads in contention tests.
4. Use warmup, multiple iterations/forks, and consume results to avoid dead-code elimination.
5. Compare the same operation count, data model, and read frequency.
6. Measure throughput, latency, and footprint/GC where relevant.
7. Verify correctness before inspecting speed numbers.

If an unsynchronized plain counter achieves high throughput because it drops updates, it is **not a functionally equivalent solution** for a fair speed comparison.

The example in Section 7 deliberately runs all three approaches together to verify they return the right sum; **do not use that output to conclude which approach is faster**.

## 11. Testing the Right Semantics

### 11.1. Single-threaded test

~~~java
AtomicLong counter = new AtomicLong();

counter.incrementAndGet();
counter.addAndGet(4);
counter.decrementAndGet();
// counter.get() == 4
~~~

This is a basic functional test, **insufficient** to verify correctness when multiple threads update concurrently.

### 11.2. Multi-threaded test

Launch N threads, each incrementing M times, wait for `join()` or `Future.get()`, then compare the sum:

\[
\text{expected}=N\times M.
\]

Compute the expected product in a wide enough range:

~~~java
long expected = (long) threadCount * incrementsPerThread;
~~~

If two int variables are multiplied before casting, the test's expectation itself can overflow and cause false conclusions. For very large datasets, also check for `long` overflow risk.

### 11.3. Stress tests and lost updates

A stress test running thousands of times without showing a bug **does not prove** `count++` is safe. You can add a two-thread coordination test like the demo program, or use specialized concurrency testing tools (such as jcstress) for complex problems.

With LongAdder, tests should require **exact total after all updates finish**, not that a concurrent `sum()` is an atomic snapshot. If the contract requires exact per-period resets, tests must cover period-transition boundaries and concurrent updates.

### 11.4. Business edge-case tests

Also test:

- Non-zero starting values.
- Increments and decrements, whether negative values are valid.
- `Integer.MAX_VALUE`/`Long.MAX_VALUE` overflow and error policies.
- CAS failures under contention and correctness of retry loops.
- Quota/limit conditions never being exceeded.
- Reads occurring concurrently with updates; distinguishing atomic snapshot requirements from approximate metrics.
- Worker shutdown, timeouts, and thread failures; do not assume every worker completes all iterations if exceptions or interruptions occur.

## 12. Choosing an Approach by Scenario

| Primary requirement | Suggestion | Avoid |
| --- | --- | --- |
| Single thread or thread-local data | Plain `long` | Adding unnecessary synchronization |
| Multiple threads, need before/after value per increment | `AtomicLong` | Using `LongAdder.sum()` to issue IDs |
| Multiple threads recording metrics, occasional reads | `LongAdder` | Treating `sum()` as an atomic snapshot |
| Threshold check coupled with increment | CAS loop or shared lock | `if(get < limit) increment()` |
| Multiple fields sharing an invariant | `synchronized`/lock or proper atomic state model | Assuming individual atomics form a transaction |
| Need exact boundary reset while updates stream continuously | Synchronized period-handoff protocol | Uncoordinated `sumThenReset()` |
| Need overflow detection | Exact arithmetic/bounds policy | Assuming atomics or adders prevent overflow |
| Multiple servers | Appropriate distributed counter/DB/service | Assuming an atomic instance is a global counter |

## 13. Common Mistakes

1. **Believing `count++` is atomic because it is one statement.** It can suffer lost updates.
2. **Adding `volatile` and assuming it is thread-safe.** Volatile does not make read-modify-write atomic.
3. **Using LongAdder to issue IDs.** `sum()` and `increment()` do not form a transaction.
4. **Believing `LongAdder.sum()` is an atomic snapshot.** Under concurrent updates, the sum may not correspond to any single instant.
5. **Using `sumThenReset()` while threads are still updating yet expecting strict period splits.** An exact protocol is required.
6. **Using `AtomicLong.get()` followed by updating in a separate call to check quotas.** Races can happen between the two steps.
7. **Assuming AtomicLong is always faster than synchronized.** Measure; multi-field invariants also matter.
8. **Assuming LongAdder is always faster than AtomicLong.** May not hold under low contention or heavy reads.
9. **Forgetting overflow.** Thread safety does not change `long`/`int` bounds.
10. **Reading a plain counter unsynchronized while writes use a lock.** All accesses must follow the same mechanism.
11. **Putting side effects in an `updateAndGet` lambda.** It can re-run during CAS retries.
12. **Benchmarking while updating all candidates in the same loop.** Fails to isolate overhead.
13. **Taking one passing stress test as proof of thread safety.** Races depend on scheduling.
14. **Thinking one AtomicLong coordinates multiple JVMs.** It belongs to one object in one process.
15. **Checking results before threads have joined.** At that point the result is not the final total.

## 14. Self-Check Questions

**Question 1.** Two threads both execute `count++`. Will it always increase by exactly 2?  
**Answer:** No, a lost update can happen because both threads read the same old value.

**Question 2.** Is `volatile long count; count++;` safe?  
**Answer:** No. Volatile does not make read–compute–write atomic.

**Question 3.** A request counter has many threads incrementing concurrently and only exports reports every 10 seconds. What should you consider?  
**Answer:** `LongAdder`, if requirements accept that the sum is not an atomic snapshot during active updates. Still benchmark against the real workload.

**Question 4.** Need a distinct ID after each increment within one JVM—what should you use?  
**Answer:** `AtomicLong.getAndIncrement()` or equivalent, with an overflow policy and consistent issuance paths.

**Question 5.** Is LongAdder exact after joining all workers?  
**Answer:** Yes, if no concurrent updates remain and workers completed properly; `sum()` gives the exact total once quiescent.

**Question 6.** Can a primitive counter protected by synchronized still lose updates?  
**Answer:** No if every update uses the same monitor and read paths follow synchronization; you still need to check for overflow.

**Question 7.** Does `new AtomicLong(Long.MAX_VALUE).incrementAndGet()` throw an exception on overflow?  
**Answer:** No, the result wraps to `Long.MIN_VALUE`. An overflow detection mechanism is needed if business rules require it.

**Question 8.** Does `if (atomic.get() < 100) atomic.incrementAndGet();` always enforce a cap of 100 across multiple threads?  
**Answer:** No, the check and increment are not atomic together; use a CAS loop or synchronization.

**Question 9.** Does one fast run of a plain counter returning the right number prove it is thread-safe?  
**Answer:** No. Reasoning via the Java Memory Model and proper concurrency testing are needed, not a single execution schedule.

**Question 10.** When two approaches are both correct, how do you pick the faster one?  
**Answer:** Measure with JMH using contention levels, thread counts, read frequency, memory, and warmup matching the real workload.

## 15. Official Java Documentation

- [`AtomicLong` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): `get`, `getAndIncrement`, `compareAndSet`, and atomic updates.
- [`AtomicInteger` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): `int` counter with atomic API.
- [`LongAdder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): `increment`, `sum`, `sumThenReset`, and snapshot limitations.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): thread coordination.
- [`Math` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `incrementExact` for overflow detection.
- [Java Language Specification 17, Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): happens-before, visibility, and data races.

**Remember:** Unsynchronized primitive counters can lose updates; `AtomicLong` provides atomic read/update, CAS, and per-increment values; `LongAdder` suits high-contention metric updates, though `sum()` is not an atomic snapshot. Prioritize the correctness contract first, then measure performance.
