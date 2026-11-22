# `sum()` on an Adder Is Not an Atomic Snapshot During Updates

`LongAdder` and `DoubleAdder` in `java.util.concurrent.atomic` are designed for cases where **many threads concurrently update a total or counter**, especially to reduce contention when update frequency is high. They can provide higher update throughput than `AtomicLong` under some high-contention scenarios, at the cost that reading the total with `sum()` has a weaker contract than an atomic read.

The core point of this lesson: **each call to `increment()`/`add()` can update shared state thread-safely, but `sum()` does not guarantee capturing the entire total at a single atomic instant during concurrent updates.** This lesson belongs to the *Numbers and Concurrency* group, focusing on explaining this mechanism, the consequences of using `sum()` for correctness/bound decisions, when the result is reliable, and when to pick another mechanism.

## 1. Three Distinct Concepts: Safe Updates, Aggregate Reads, and Atomic Snapshots

You must distinguish:

1. **Thread-safe update:** multiple threads call `adder.increment()` or `adder.add(delta)` instead of using a plain `long` variable with `count++`, which loses updates due to a data race.
2. **Aggregate read:** `adder.sum()` sums the components holding the total and returns a `long`. This value is useful for observing operational metrics.
3. **Atomic snapshot:** a read operation guaranteed to appear as reading the entire state at **a single logical instant** between the start and end of the operation, even while other threads keep updating.

`LongAdder.sum()` satisfies goal (2), but the API documentation **does not promise (3)**. While it collects numbers from the components, other updates may take place. Consequently, the result may **omit some updates overlapping the read interval**. When no concurrent updates remain, `sum()` returns the exact total of completed updates, assuming no overflow or reset altered the state.

Do not confuse a **non-atomic snapshot** with **"every addition is broken."** `LongAdder`'s update calls still provide concurrent counting; the missing guarantee lies in *observing the set of components at one simultaneous instant*, not in `LongAdder` degrading into an unsynchronized `long`.

## 2. Why Does LongAdder Have a Multi-Part Sum?

`AtomicLong` holds a single atomic value. When many threads update that same value via CAS or atomic operations, they can contend on the same update location.

`LongAdder` solves a different problem: it keeps a **base value** and can expand into **component cells (cells/stripes)** under contention. Multiple threads are spread across cells to reduce contention when adding to the total. Conceptual model:

~~~text
Writers:
Thread A --add(1)--> base / cell[0]
Thread B --add(1)-->        cell[1]
Thread C --add(1)-->        cell[2]
                                 |
Reader: sum() ------------------+--> sums base + cells
                                      across read passes
~~~

This is an **explanatory diagram**, not a guarantee of cell count, thread-to-cell mapping, or line-by-line algorithm across all JDKs. Depending on contention levels, the internal structure can differ.

If summing must visit multiple cells sequentially, it cannot automatically treat the read values as **a single immutable joint snapshot**. While the reader reads the first cell, a writer may update the second cell; before the reader reaches the next cell, another writer may update the first cell as well. Component reads occur at different points in time.

The JavaDoc clearly states `LongAdder.sum()`'s contract: **not an atomic snapshot**; in the absence of concurrent updates, the result is accurate, whereas updates occurring while summing is in progress may not be included in the returned result.

This does not mean `sum()` necessarily returns a wrong or missing count on every run. On simple workloads, a measurement may happen to match the total at some instant. **You cannot prove atomicity simply by running a test multiple times and always seeing reasonable numbers.**

## 3. Which LongAdder APIs Are Relevant?

| API | Meaning | Concurrency notes |
|---|---|---|
| `new LongAdder()` | Creates an initial total of 0 | Share the exact same instance among writers for one counter |
| `add(long x)` | Adds `x` (can be negative) | Safe for concurrent updates |
| `increment()` | Equivalent to `add(1)` | Suitable for event counters |
| `decrement()` | Equivalent to `add(-1)` | Decrements are possible; do not assume the total is monotonic |
| `sum()` | Reads total across components | **Not an atomic snapshot** with concurrent writers |
| `longValue()` | Equivalent to `sum()` | No stronger than `sum()` |
| `toString()` | Converts `sum()` result to string | Not a stronger snapshot |
| `reset()` | Resets sum components to 0 | Use only when no concurrent writers are active |
| `sumThenReset()` | Reads total then resets to 0 | Not an atomic read-and-clear while writers still run |

In particular, `sumThenReset()` is **not equivalent** to atomic `AtomicLong.getAndSet(0)` in its guarantees under contention. Sum components are processed sequentially; if writers update during the reset, the API does not guarantee the returned value equals all data prior to a reset boundary. Do not use `sumThenReset()` as an automatic tool to partition metrics into windows **without losing or miscounting updates** while writers remain active.

## 4. Standalone Java 17+ Example with Verifiable Output

File `AdderSnapshotDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.LongAdder;

public class AdderSnapshotDemo {
    public static void main(String[] args) throws InterruptedException {
        final int workers = 4;
        final int iterations = 50_000;
        LongAdder counter = new LongAdder();
        CountDownLatch go = new CountDownLatch(1);
        Thread[] threads = new Thread[workers];

        for (int i = 0; i < workers; i++) {
            threads[i] = new Thread(() -> {
                try {
                    go.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
                for (int j = 0; j < iterations; j++) {
                    counter.increment();
                }
            });
            threads[i].start();
        }

        System.out.println("before release = " + counter.sum());
        go.countDown();

        // Observation only: DO NOT claim this is an atomic snapshot.
        long during = counter.sum();
        System.out.println("during within range = " +
                (during >= 0 && during <= workers * iterations));

        // After join(): no writer is updating counter anymore.
        for (Thread thread : threads) {
            thread.join();
        }
        System.out.println("after join = " + counter.sum());

        // sumThenReset is used when there are no writers at all.
        LongAdder batch = new LongAdder();
        batch.add(3);
        batch.add(4);
        System.out.println("quiescent batch = " + batch.sumThenReset());
        System.out.println("after reset = " + batch.sum());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 AdderSnapshotDemo.java
java AdderSnapshotDemo
~~~

Expected output (without external interruption):

~~~text
before release = 0
during within range = true
after join = 200000
quiescent batch = 7
after reset = 0
~~~

Explanation:

- Before `go.countDown()`, all workers wait on the `CountDownLatch` gate, so no `increment()` has run yet: 0 is deterministic.
- After opening the gate, `during` may be 0, several thousand, 200,000, or another value in range; the program **does not print the specific number of `during`** because it depends on execution scheduling.
- In this example there are only **increments by 1**, no resets/decrements/`long` overflow, and total increments are at most 200,000. A range check is reasonable for this example, **yet it does not prove `sum()` is an atomic snapshot**.
- `Thread.join()` waits for all four workers to finish. Each worker performs 50,000 updates, so after `join()` with no writers left, `sum()` yields exactly `4 × 50,000 = 200,000`. `join()` also establishes the happens-before relationship so the main thread observes the completed work.
- `batch.sumThenReset()` returns 7 and resets to 0 **because there are no concurrent updates in this section**.

The code above is a learning example of the API contract, **not a race test aimed at forcing the JVM to expose a bad value**. Mid-flight observation behavior is nondeterministic; to verify correctness, rely on the contract and mechanism analysis rather than writing a unit test asserting a specific `during` value.

## 5. Timeline Walkthrough: Why Is There No Single Snapshot Instant?

Suppose two internal components correspond to groups of writers. Illustrative timeline:

| Time | Writers | Reader calling `sum()` |
|---|---|---|
| t0 | Cells hold already completed updates | Begins summing |
| t1 | Writer A updates the first component | Reader has read or is reading the first component |
| t2 | Writer B updates the second component | Reader reads the second component |
| t3 | Further updates continue | Reader sums the values it read |
| t4 | Writers may still be running | `sum()` returns a number |

There is no common "freeze point" across all components. Some concurrent updates may be included and others excluded; you cannot say `sum()` necessarily reflects the total **at the exact moment of call**, **at the moment of return**, or **including all updates that happened during the read**.

**Notice the difference between two statements:**
- **True:** `sum()` does not guarantee an atomic snapshot during ongoing updates.
- **False in general:** Every `sum()` result during updates is "garbage data" or always inaccurate.

For a counter that only increments from 0 with no reset or overflow, mid-flight reads are usually sufficient to plot a rising event curve over time. However, an observational chart **has different requirements** from figures that must close books accurately at a business cutoff.

## 6. Comparing LongAdder with AtomicLong

| Criterion | `LongAdder` | `AtomicLong` |
|---|---|---|
| Accumulated state | May consist of multiple components | A single atomic `long` value |
| `+1` update | `increment()` | `incrementAndGet()` or `getAndIncrement()` |
| Read | `sum()`: non-atomic snapshot during concurrent updates | `get()`: atomic read of one value |
| Read then zero | `sumThenReset()`: unsafe as an atomic boundary while writers remain | `getAndSet(0)`: atomic exchange on **one** value |
| High contention | Often reduces contention for update-heavy workloads | Can contend on a single variable |
| Resources | Can use extra memory for cells | One primary state variable |
| Best suited for | Metrics, histograms, frequently updated stats read for observation | Counters requiring decisions from atomic values, update ordering, CAS/bounds |

`AtomicLong.get()` is atomic at the level of **one value**; this does not create an atomic snapshot across **multiple** `AtomicLong` instances or other data structures. Maintaining invariants across multiple fields still requires an appropriate coordination mechanism (e.g., a shared lock or immutable state published via one atomic reference).

Do not treat the table as claiming `LongAdder` is always faster. Performance depends on thread count, contention level, read frequency, CPU, counter usage pattern, and JVM. When optimizing, measure the real workload with a proper benchmarking tool rather than inferring from a tiny loop printing elapsed time.

## 7. Right Use Cases for LongAdder: Metrics and Statistics

A common example is a **processed-request counter**:

~~~java
import java.util.concurrent.atomic.LongAdder;

public class RequestMetrics {
    private final LongAdder processed = new LongAdder();

    public void onProcessed() {
        processed.increment();
    }

    public long reportApproximate() {
        return processed.sum();
    }
}
~~~

This code is a reusable class; when multiple threads call `onProcessed()`, incrementing is safe. `reportApproximate()` used while workers keep running is an observational read that may omit some concurrent updates. Name and specify the API clearly—such as `estimate`, `observedTotal`, or "value at scrape time"—so consumers do not mistake it for a closed-period figure.

Using it in metrics systems can tolerate short-term observation skew because subsequent scrapes will see completed updates (barring application resets or overflow). Do not generalize this to every collection/windowing scheme: calling `sumThenReset()` while writers update offers no guarantee of assigning each event accurately to the right window.

A way to build a multi-key histogram:

~~~java
ConcurrentHashMap<String, LongAdder> frequencies =
        new ConcurrentHashMap<>();

frequencies.computeIfAbsent("OK", key -> new LongAdder()).increment();
frequencies.computeIfAbsent("ERROR", key -> new LongAdder()).increment();

long ok = frequencies.get("OK").sum();
~~~

This snippet requires `import java.util.concurrent.ConcurrentHashMap;` and `LongAdder`, placed inside a method. `computeIfAbsent` ensures creating/publishing the value for a key via `ConcurrentHashMap`'s mechanism, while each `LongAdder` tracks per-key statistics. However, reading **multiple keys** into a report does not produce a consistent snapshot of the entire map or of all `LongAdder` instances at a single point in time.

## 8. When Not to Use sum() for Strict Decisions

### A. Do Not Use as a Unique ID Generator

~~~java
long next = adder.sum() + 1;
// Unsafe to issue a unique ID and only then call increment().
~~~

Two threads can observe the same sum and generate the same ID; even if `sum()` were an ideal snapshot, **read then increment** are two separate steps, so a race still occurs. Use `AtomicLong.incrementAndGet()` or a dedicated ID generator when an atomic operation issuing the next number is required.

### B. Do Not Use to Enforce Hard Quotas

~~~java
if (adder.sum() < capacity) {
    adder.increment();
    // Does not guarantee final total stays within capacity.
}
~~~

There are two problems: `sum()` is not an atomic snapshot of `LongAdder`, and the **check condition then increment** pair is not executed as an atomic transaction either. Multiple threads can simultaneously see available room and all increment.

For a quota represented by a single integer, use an `AtomicLong` state with a CAS loop, or a dedicated synchronization mechanism for resource allocation:

~~~java
import java.util.concurrent.atomic.AtomicLong;

static boolean reserveOne(AtomicLong used, long capacity) {
    while (true) {
        long current = used.get();
        if (current >= capacity) {
            return false;
        }
        if (used.compareAndSet(current, current + 1)) {
            return true;
        }
    }
}
~~~

The method snippet above goes inside a Java class. Assume `capacity` is a valid non-negative number and does not require exceeding the `long` range. If CAS fails, another thread changed the value, so retry from the new state. This is a **linearized check + increment on the same variable**, far better suited than `if (sum < capacity) increment`.

### C. Do Not Use for Financial Closing or Audit Figures

Calling `sum()` while transactions are running does not guarantee all committed business operations are counted accurately at a cutoff boundary. You need a transaction model, ledger, event log, synchronization, or checkpoint with proper semantics. `LongAdder` is only a `long` accumulator, not a substitute for business consistency.

When handling fractional monetary amounts, using `DoubleAdder` as a ledger is even worse: `double` also suffers from floating-point error and depends on addition order. Represent the smallest unit as `long` when range permits, or use a decimal type/storage mode matching the system contract.

## 9. How Do You Get an Exact Final Total?

**Principle:** read after knowing all writers have terminated and nobody is updating that adder anymore. One way is waiting with `Thread.join()` as in Section 4's program. With tasks submitted to an `ExecutorService`, wait on `Future.get()` or an appropriate completion mechanism before reading the total. If writers outside the awaited group remain, the read is still a concurrent observation.

Crucially, do not rely on picking an arbitrary `Thread.sleep(...)` duration. Sleeping 100 ms or 1 second **does not prove** writers are finished and does not create an atomic snapshot. A completion signal with explicit guarantees is required.

A system continuously ingesting events may have no "moment when all writers stop." When an exact total for timestamp `T` is required, the design must define event boundaries and coordinate so all updates belonging to that boundary complete before closing. Use an appropriate lock/epoch/checkpoint mechanism or compute exact totals from durable storage. Swapping the adder reference and calling `sum()` on the old instance **is not enough** if writers still hold the old reference and keep updating after the swap.

**Do not confuse** `sum()` returning accurately when the system is quiescent with `sum()` creating quiescence itself. The reader does not block writers and does not impose a data cut boundary.

## 10. reset() and sumThenReset(): Risks When Misused

`LongAdder.reset()` clears the accumulated value. `sumThenReset()` combines reading and resetting in effect, yet the API documentation explicitly notes these methods are **effective accurately only when there are no concurrent updates**.

When writers are still adding numbers:
- An update can land in the window where the reader has already read part of the state but not yet reset that part.
- The returned read value and the total remaining after reset may fail to partition updates cleanly across a single atomic boundary.
- A single `sumThenReset()` does not guarantee capturing all updates completed prior to an arbitrary business cutoff you choose.

The following snippet is **safe under the assumption of no other writers**:

~~~java
LongAdder window = new LongAdder();
window.add(8);
window.add(2);

long completedWindow = window.sumThenReset(); // 10
long nextWindow = window.sum();               // 0
~~~

This snippet requires `import java.util.concurrent.atomic.LongAdder;` and belongs inside a Java method. If concurrent writers exist, you cannot rely on the 10/0 result as a general contract.

If metric windows require exact boundary precision, design a window-closing workflow: block/redirect writers using a protocol with completion acknowledgment, then read the previous generation's total. `LongAdder`'s methods do not provide this protocol on their own.

## 11. DoubleAdder Has the Same Snapshot Limits Plus Arithmetic Limits

`DoubleAdder` works similarly but sums `double`. `DoubleAdder.sum()` is also **not an atomic snapshot** during concurrent updates. Moreover, the order of additions within/across threads is not guaranteed, and `double` is not strictly associative in computer arithmetic:

~~~text
(a + b) + c  may differ from  a + (b + c)
in floating-point arithmetic due to rounding.
~~~

Therefore, even after all writers terminate, `DoubleAdder.sum()` can differ bit-for-bit from summing the same values sequentially in a fixed order. This is a **numerical stability** difference, separate from the concurrent snapshot issue. When value counts or magnitudes vary widely or high precision is required, pick an appropriate summation design.

Example:

~~~java
import java.util.concurrent.atomic.DoubleAdder;

DoubleAdder total = new DoubleAdder();
total.add(0.1);
total.add(0.2);

double result = total.sum();
System.out.println(result); // 0.30000000000000004 (with IEEE 754 double)
~~~

This snippet only illustrates ordinary `double` addition on a single thread. Do not use `DoubleAdder` expecting exact decimal monetary totals. For systems requiring stable `double` sums or bounded error, consider compensated summation/sorting and thread coordination rather than assuming a concurrent accumulator solves it automatically.

## 12. Common Misconceptions and Mistakes

1. **"If LongAdder is thread-safe, sum() must be atomic."** Partial updates and concurrent multi-part reads are two separate contracts.
2. **"If repeated runs always give the right sum(), the API guarantees it."** Scheduling might not expose differences in tests; the JavaDoc contract determines what is guaranteed.
3. **"Wrapping the adder in volatile makes sum atomic."** `volatile` on the reference does not atomically lock reading all internal components.
4. **"synchronized (adder) { return adder.sum(); } is enough."** Locking only protects the operation if **every writer** obeys the same lock or an equivalent coordination mechanism. By default, `increment()` does not acquire the adder object's monitor.
5. **"sumThenReset() is just like AtomicLong.getAndSet(0)."** Under concurrent updates, `sumThenReset()` lacks the atomic boundary of `getAndSet` on a single `AtomicLong`.
6. **"Reading the sum then incrementing to issue sequence numbers is safe."** That is a non-atomic read-modify-write regardless of counter implementation.
7. **"AtomicLong solves snapshots across multiple metrics too."** It guarantees operations on a single value; multiple variables still require a shared synchronization protocol if a consistent state is needed.
8. **"You can wait for writers with sleep."** `sleep()` does not wait for completion with any binding guarantee; use `join()`, `Future.get()`, latches, or barriers matching the task structure.
9. **"One LongAdder with sumThenReset for per-minute metrics is always exact to the minute."** There is no exact boundary guarantee if events are still updating during reset.
10. **"LongAdder never overflows."** It accumulates in `long`; sums exceeding the `long` range still overflow/wrap per Java integer arithmetic. Choose an appropriate data range and detection/bounding mechanism if totals can exceed limits.
11. **"DoubleAdder is exact decimal addition."** It uses `double` with non-fixed addition order across threads; account for error if the application is precision-sensitive.
12. **"Reading multiple LongAdders one by one gives a whole-system snapshot."** Values are read at different times; if invariants span multiple statistics, additional coordination is required.

## 13. Which Type to Choose for Specific Requirements?

| Requirement | Suitable choice | Explanation |
|---|---|---|
| Counting requests, logging events, metrics under high contention | `LongAdder` | Efficient updates; accept `sum()` as a non-atomic observational read |
| Atomically incrementing sequences, single-variable quotas, CAS on current state | `AtomicLong` | Provides `get()` and atomic read-modify-write |
| Multi-key statistics with continuous updates | `ConcurrentHashMap<K, LongAdder>` | Independent per-key counters, though whole-map snapshots are not automatically atomic |
| Exact total after all tasks complete | `LongAdder` + completion synchronization | `sum()` is accurate once updates stop, within valid numeric bounds |
| Exact total at a point in time in an always-running system | Synchronized cutoff/checkpoint protocol | `sum()`/`sumThenReset()` alone does not define a boundary |
| Statistical `double` sum tolerating rounding error | `DoubleAdder` | Watch rounding and addition order |
| Monetary ledgers / auditable data | Transaction data and contract-compliant numeric types | An in-memory counter cannot replace consistency and durability |

## 14. Self-Check Questions

**Question 1.** Two threads continuously call `LongAdder.increment()`. Another thread calls `sum()` in the meantime. Can the value be treated as all updates that occurred right at the moment of the call?

**Answer:** No. `sum()` may exclude updates occurring during summation; the JavaDoc does not guarantee an atomic snapshot in this scenario.

**Question 2.** After both workers have `join()`ed and no other thread is updating, each having executed 1,000 `increment()` calls, what must `sum()` equal?

**Answer:** 2,000, assuming it started at 0, had no resets/decrements/overflow, and workers truly finished. No concurrent updates remain at read time.

**Question 3.** Does `if (adder.sum() < 10) adder.increment();` keep the total at most 10 across multiple threads?

**Answer:** No. Reading the sum and incrementing do not form an atomic check-and-update action. Use `AtomicLong.compareAndSet` in a loop or appropriate synchronization/quota algorithms.

**Question 4.** Can `sumThenReset()` be used to close a 1-minute window accurately while writers keep updating the same instance?

**Answer:** There is no such guarantee. You need a mechanism ensuring writers of the old window have finished before reading/resetting, or a different metrics collection design.

**Question 5.** If you switch from `LongAdder` to `AtomicLong`, is a single `get()` call enough to take a consistent snapshot across five different counters?

**Answer:** No. One `AtomicLong.get()` atomically reads **one** value, not an atomic transaction across five variables.

**Question 6.** After stopping all writers to a `DoubleAdder`, is `sum()` guaranteed to match sequential addition in a fixed order bit-for-bit?

**Answer:** No. Stopping contention makes reading the components stable, yet floating-point arithmetic can round differently when addition order changes.

## 15. Summary and Authoritative Sources

- **`LongAdder.add()/increment()`:** for safe concurrent updates, optimized for statistics under contention.
- **`LongAdder.sum()`:** reads the total for observation; **not an atomic snapshot while writers are still running**.
- **After synchronizing completion of all writers:** `sum()` returns the exact total of completed updates, within arithmetic bounds and without resets.
- **`sumThenReset()`/`reset()`:** use only at quiescent boundaries or under synchronization protocols excluding concurrent updates.
- **`AtomicLong.get()/incrementAndGet()/compareAndSet()/getAndSet()`:** suited for single `long` state requiring atomic reads or read-modify-write.
- **`DoubleAdder.sum()`:** same snapshot limitations plus non-associative `double` caveats.

Official API docs for reference:
- [`LongAdder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): `sum`, `reset`, `sumThenReset`, and intended use in concurrent statistics.
- [`DoubleAdder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/DoubleAdder.html): concurrent snapshots and `double` addition order.
- [`AtomicLong` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): atomic operations on a single `long` value.
- [`Thread.join` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): waiting for a thread to terminate; related happens-before rules are in `java.util.concurrent` and the Java Memory Model docs.
