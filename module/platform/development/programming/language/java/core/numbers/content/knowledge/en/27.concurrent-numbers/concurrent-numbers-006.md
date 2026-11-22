# `LongAdder`, `DoubleAdder`, and Contended Statistics Counting in Java

## 1. The Problem: Very Many Threads Incrementing One Counter

In a Java server, many threads may concurrently track request counts, error counts, cache hits, or total processing time. If you use a `long` variable and `count++`, many updates can be **lost** because `++` actually consists of reading, computing, and writing. Two threads can both read 10, compute 11, and write 11, whereas the correct result after two increments must be 12.

`volatile long count` does not solve incrementing: `volatile` provides visibility and memory ordering guarantees, **not atomicity for read-modify-write**. When concurrent counting is needed, common approaches are `synchronized`/`Lock`, `AtomicLong`, or `LongAdder`.

`LongAdder` and `DoubleAdder` (package `java.util.concurrent.atomic`, available since Java 8) are designed for workloads where **many threads continuously add to a statistical quantity**, especially under *contention* on the same variable.

After this lesson, you will know:

- Why an `AtomicLong` counter can become a hotspot when many threads update concurrently.
- How `LongAdder` and `DoubleAdder` reduce contention by distributing additions.
- How to run a multithreaded example and read reliable results after `join()`.
- How to distinguish thread-safe updates from **reading an atomic snapshot**.
- How to use `ConcurrentHashMap<K, LongAdder>` to count by label.
- How to handle metric resets, strict quotas, and approximate `double` values properly.

## 2. Mechanism: Distributing Writes to Reduce Contention

`AtomicLong` maintains a single shared atomic state; many threads repeatedly attempt to update that state via CAS (*compare-and-set*) or equivalent atomic primitives. When competing over a single hotspot, attempts can fail and have to retry.

`LongAdder` is optimized for scenarios with a large volume of competing `add`/`increment` operations. Conceptually, it maintains a base sum and can expand internal *cells* to spread writes:

```text
Worker A ---> [cell A] --+
Worker B ---> [cell B] --+---> sum() = base + sum of cells
Worker C ---> [cell C] --+
Worker D ---> [base] ----+
```

The diagram only illustrates the mechanism: **each thread is not guaranteed its own dedicated cell**, nor is the number of cells fixed. Distribution and expansion are JDK implementation details. The trade-off is that adding to independent parts can reduce write contention, while `sum()` must read/combine the parts, which can be more expensive than `AtomicLong.get()`.

`DoubleAdder` applies a similar idea to `double` totals. Neither is the fastest choice in every situation: with very low contention, sparse updates, tight memory, or frequent reads, `AtomicLong` may be simpler and better suited. Actual performance should be measured on your specific workload.

### Three Requirements to Distinguish

1. **Every completed addition is recorded** under the adder's concurrency contract, provided there is no competing reset and no related overflow/precision issue.
2. **Reading the total after updates have stopped**: `sum()` reflects all completed additions, suitable for verifying worker results.
3. **Reading an atomic snapshot while workers are still adding**: `sum()` **does not promise this**; it may read states of different cells at different moments.

## 3. API and Key Differences

| Operation | `LongAdder` | `DoubleAdder` |
|---|---|---|
| Construction | `new LongAdder()` | `new DoubleAdder()` |
| Add a delta | `add(long delta)` | `add(double delta)` |
| Add/subtract 1 | `increment()`, `decrement()` | `add(1.0)`, `add(-1.0)` |
| Read total | `sum(): long` | `sum(): double` |
| Read then reset | `sumThenReset()` | `sumThenReset()` |
| Reset without reading | `reset()` | `reset()` |
| Read via `Number` | `longValue()` matching the sum | `doubleValue()` matching the sum |
| Has `get()`, `compareAndSet()`? | No | No |

`add` operations can take negative values; adders do not count only positive numbers. Both start at 0. `LongAdder.sum()` returns a `long`, so **64-bit integer overflow** is still possible without automatic `Math.addExact` checks.

Note: `LongAdder` **has no `get()` method** like `AtomicLong`; use `sum()` to obtain the total. `LongAdder.longValue()` does not make the snapshot atomic either.

## 4. Complete Example: Four Threads Incrementing a `LongAdder`

**File `LongAdderDemo.java`**, running on Java 17+:

```java
import java.util.concurrent.atomic.LongAdder;

public class LongAdderDemo {
    public static void main(String[] args) throws InterruptedException {
        int workersCount = 4;
        int updatesPerWorker = 100_000;
        LongAdder requests = new LongAdder();

        Thread[] workers = new Thread[workersCount];

        for (int i = 0; i < workersCount; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < updatesPerWorker; j++) {
                    requests.increment();
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("expected=" + workersCount * updatesPerWorker);
        System.out.println("actual=" + requests.sum());
    }
}
```

Run:

```bash
javac LongAdderDemo.java
java LongAdderDemo
```

Output:

```text
expected=400000
actual=400000
```

`join()` is crucial here. It ensures worker tasks have finished before main reads the total, while also providing the *happens-before* relationship for worker actions. With no concurrent writes remaining, `sum()` now returns the total of the 400,000 `increment()` calls in the example.

If you read `sum()` right after calling `start()`, the result may be less than 400,000 because workers are not done yet. That alone does not prove a lost-update bug; the difference may simply be due to observation timing.

Basic operations example (placed inside a method when running):

```java
LongAdder pending = new LongAdder();
pending.increment(); // +1
pending.add(5);       // +5
pending.decrement(); // -1
System.out.println(pending.sum()); // 5
```

When shared across multiple threads, `increment()`, `decrement()`, and `add(long)` support concurrent updates. Reading the total while writes are still ongoing remains statistical.

## 5. `DoubleAdder` Example: Total Processing Time and Sample Count

`DoubleAdder` uses `double` to accumulate quantities where **floating-point precision is acceptable**, such as total latency or measurements. To compute an average, you typically pair it with a `LongAdder` counting samples.

**File `DoubleAdderDemo.java`:**

```java
import java.util.concurrent.atomic.DoubleAdder;
import java.util.concurrent.atomic.LongAdder;

public class DoubleAdderDemo {
    public static void main(String[] args) throws InterruptedException {
        int workersCount = 4;
        int samplesPerWorker = 10_000;

        DoubleAdder total = new DoubleAdder();
        LongAdder count = new LongAdder();
        Thread[] workers = new Thread[workersCount];

        for (int i = 0; i < workersCount; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < samplesPerWorker; j++) {
                    total.add(0.75);
                    count.increment();
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        long n = count.sum();
        double totalTime = total.sum();
        System.out.println("count=" + n);
        System.out.println("total=" + totalTime);
        System.out.println("average=" + totalTime / n);
    }
}
```

```bash
javac DoubleAdderDemo.java
java DoubleAdderDemo
```

```text
count=40000
total=30000.0
average=0.75
```

The example chooses `0.75`, a number representable exactly in binary, so displayed values are free of rounding noise. With `0.1`, do not assume the sum is represented with exact decimal precision.

**Consistency note:** Each worker calls `total.add(0.75)` then `count.increment()`. If a dashboard reads `count.sum()` and `total.sum()` while workers are running, the two values may correspond to different instants. An average computed that way is only a best-effort observation. After `join()` finishes on all workers, both totals stabilize within the example's arithmetic bounds.

An average with `n == 0` must be handled separately. Computing `totalTime / n` with `double` when `n == 0` can yield `NaN` or infinity, not a valid average. In real applications, divide only when samples exist.

## 6. `sum()` Is Thread-Safe, Not an Atomic Snapshot

Some materials use the term "thread-safe" in a way that leads readers to infer **every read sees a globally consistent state**. That is not true for `LongAdder.sum()`/`DoubleAdder.sum()`.

During concurrent writes, a call to `sum()` may sum the base and individual cells at different moments in time. The result is useful for near-read-time statistics, but comes with no guarantee that it represents a single instant in a linearizable model.

For example, a dashboard showing "roughly 10,000 requests processed" can tolerate observation skew. However, enforcing a **hard quota** such as issuing at most 100 tokens must use a mechanism with atomic check-then-update.

Broken code for quota enforcement:

```java
// Illustrative: quota is a shared LongAdder.
if (quota.sum() < 100) {
    quota.increment();
    // Grant permission to this request.
}
```

Two threads can both see `99`, both grant permission, and both increment, exceeding 100. Replacing `LongAdder` with `AtomicLong` while still calling `get() < 100` and `incrementAndGet()` separately **is still insufficient**: the check and update pair must be bound into one atomic protocol, such as a CAS loop or an appropriate lock/transaction.

`AtomicLong.get()` provides an atomic read on **a single variable**; `AtomicLong.compareAndSet()` enables conditional updates. `LongAdder` lacks CAS over the total sum, so do not use it as a unique-sequence generator or exact quota mechanism.

## 7. `reset()` and `sumThenReset()`: Caution with Ongoing Updates

Both adders provide two notable methods:

- `reset()`: resets the accumulator to zero.
- `sumThenReset()`: returns the observed sum and resets it to zero.

They **do not provide an atomic statistical window cut** while multiple threads are calling `add()`. By the API contract, they are best used when **no concurrent updates are happening**. If competing with a reset, updates may be observed across the wrong window or fail to be preserved under strict accounting requirements.

**File `AdderResetDemo.java`** (no concurrent writes):

```java
import java.util.concurrent.atomic.LongAdder;

public class AdderResetDemo {
    public static void main(String[] args) {
        LongAdder requests = new LongAdder();
        requests.add(8);
        requests.increment();

        System.out.println("before=" + requests.sum());
        System.out.println("drained=" + requests.sumThenReset());
        System.out.println("after=" + requests.sum());

        requests.add(3);
        requests.reset();
        System.out.println("afterReset=" + requests.sum());
    }
}
```

```bash
javac AdderResetDemo.java
java AdderResetDemo
```

```text
before=9
drained=9
after=0
afterReset=0
```

An application collecting per-minute metrics can use best-effort resets if minor skew is acceptable; if **zero lost events** is mandatory, coordinate workers to stop writing to the old counter, design epochs, or use an event/metric system with contracted window boundaries.

Swapping an `AtomicReference<LongAdder>` **does not automatically solve everything**: a worker can read the old adder reference before the swap and then update the old adder after the collector already drained its sum. Thus, systems still need coordination rules and write-completion states.

## 8. Label-Based Statistics with `ConcurrentHashMap` and `LongAdder`

When an application records multiple event types, a common pattern holds a separate adder per map key:

```text
"ok"     ---> LongAdder (successful request count)
"retry"  ---> LongAdder (retried request count)
"failed" ---> LongAdder (failed request count)
```

**File `ConcurrentMetricsDemo.java`:**

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class ConcurrentMetricsDemo {
    private static final ConcurrentHashMap<String, LongAdder> COUNTS =
            new ConcurrentHashMap<>();

    private static void record(String event) {
        COUNTS.computeIfAbsent(event, key -> new LongAdder())
                .increment();
    }

    public static void main(String[] args) throws InterruptedException {
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            final int index = i;
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 10_000; j++) {
                    record("ok");
                    if (index % 2 == 0) {
                        record("retry");
                    }
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("ok=" + COUNTS.get("ok").sum());
        System.out.println("retry=" + COUNTS.get("retry").sum());
    }
}
```

```bash
javac ConcurrentMetricsDemo.java
java ConcurrentMetricsDemo
```

```text
ok=40000
retry=20000
```

`ConcurrentHashMap.computeIfAbsent()` coordinates creating the value for a **missing key**; threads then increment the same `LongAdder` instance. Using `if (!map.containsKey(key)) { map.put(key, new LongAdder()); }` is unsafe under contention because two threads can create two counters and overwrite each other's reference.

However, `computeIfAbsent(...).increment()` is two steps, **not an atomic transaction spanning both the map and the counter**. If another thread concurrently calls `remove` or replaces the key's value, a worker holding the old adder can still increment an object no longer in the map. When resetting or rotating metric generations, separate ownership and synchronization rules are needed.

Also, never allow label names to be unbounded strings generated from arbitrary user input; each label allocates at least one counter and can exhaust memory. Design should bound label *cardinality*.

## 9. `DoubleAdder` and Floating-Point Error

`DoubleAdder` does not make `double` addition decimally exact. Two main issues apply:

### 9.1. `0.1` Is Not Represented Exactly in `double`

Numbers like `0.1` have infinite binary expansions, so repeated addition can accumulate drift relative to ideal decimal math. For statistical measurements, error within a defined tolerance may be acceptable. For money, quantities requiring exact match, or accounting reconciliation, `DoubleAdder` is unsuitable as an exact source of truth.

### 9.2. Addition Order Affects the Result

Floating-point addition is *non-associative* when rounding occurs. For example, this snippet can be placed in `main`:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

`1.0` can be lost when added to `-1e16` due to limited significant digits. In `DoubleAdder`, threads updating different cells can alter the order in which partial sums are combined, so you should not require **bit-for-bit identical** results across runs for order-sensitive data.

### 9.3. Handling Non-Finite Inputs

`DoubleAdder` accepts `Double.NaN`, `Double.POSITIVE_INFINITY`, and `Double.NEGATIVE_INFINITY`; these values can turn the sum into `NaN` or infinity. If statistics require summing finite measurements, validate inputs before adding:

```java
// Snippet inside a method; sample is a double,
// total is an initialized DoubleAdder.
if (!Double.isFinite(sample)) {
    throw new IllegalArgumentException("Non-finite sample");
}
total.add(sample);
```

If measurements must be non-negative, also check `sample >= 0.0`.

### 9.4. Choosing a Representation for Money

When money must be stored accurately, use `BigDecimal` combined with transactions/synchronization, or represent values as integers of the **smallest currency unit** (with clear conversion, overflow-check, and remainder policies). Only use `LongAdder` to sum integer currency units for statistics when its snapshot semantics are acceptable; it does not replace accounting transaction mechanisms.

## 10. Tool Selection Comparison

| Need | Commonly suitable choice | Notes |
|---|---|---|
| Many threads writing one metric counter | `LongAdder` | Reduces contention hotspots in some workloads |
| Many threads summing `double` for approximate measurements | `DoubleAdder` | Subject to precision and rounding limits |
| Need `get()`, `compareAndSet()`, sequence generation | `AtomicLong` | Atomic operations on a single variable |
| Need check-then-update quota or multi-field consistency | CAS / lock / transaction | Make the entire operation atomic |
| Need statistics by key | `ConcurrentHashMap<K,LongAdder>` | Bound cardinality; watch counter removal/replacement |
| Need windowing without losing events | Synchronization protocol or metric system with buckets | `sumThenReset` is insufficient under contention |
| Low contention, read-heavy, limited resources | Consider `AtomicLong` | Simpler, potentially lower overhead |
| Money or decimals needing exact precision | `BigDecimal` / integer units + transactions | Thread safety does not guarantee decimal accuracy |

Do not claim adders are always faster than atomics: benchmarks require JMH, JIT warm-up, thread counts, read/write ratios, lock/object sizes, and a representative environment. `System.nanoTime()` around a simple loop is usually insufficient evidence to select a concurrency mechanism.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| `long++` or `volatile long++` across workers | Lost updates | Adder, atomic, or lock |
| Calling `adder.get()` | No such API | Use `sum()` |
| Assuming `sum()` is atomic | Multi-cell snapshot lacks consistency | Use only for best-effort metrics, or wait for writers |
| Using `sum() < limit` then `increment()` to enforce quota | Two workers can both be granted | CAS / lock / transaction |
| Calling `sumThenReset()` while workers still add | Window skew; may not preserve all updates | Coordinate updates and resets |
| Treating `DoubleAdder` as multithreaded `BigDecimal` | `double` has precision error | Choose an appropriate representation |
| Expecting floating-point results to be bit-identical | Addition order varies | Use appropriate error tolerances |
| Replacing a map counter actively used by workers | Workers may write to the old counter | Ownership / epoch rules |
| Unbounded map labels | Unbounded memory growth | Bound label domain |
| Assuming `LongAdder` never overflows | Still a `long` | Evaluate value range and overflow conditions |

## 12. Self-Check Exercises with Solutions

1. **8 workers each call `LongAdder.increment()` 10,000 times. When is `sum()` guaranteed to reach 80,000?**  
   After all workers finish and no other updates/resets occur, provided no overflow happens.

2. **Does `LongAdder` return a unique sequence number during `increment()`?**  
   No. `increment()` returns nothing; `sum()` is not a sequence number tied to that update. Consider `AtomicLong.incrementAndGet()` for sequence generation.

3. **Why is `LongAdder.sum()` unsuitable for exact quota checks?**  
   There is no atomic snapshot, and the check-then-update pair itself must be synchronized together.

4. **Does `DoubleAdder` have `increment()`?**  
   No. Use `add(1.0)`.

5. **After workers finish, what total does `DoubleAdder` give after receiving `0.75` 100 times?**  
   `75.0`. This is an exact binary-representable value, and addition in this range loses no fractional part in the example.

6. **Why is calling `sumThenReset()` while writers are active unsuitable for strictly accurate accounting?**  
   Because reading and resetting are not atomic across the entire structure; concurrent updates may not be cleanly assigned to a single reporting period.

7. **Why is combining `ConcurrentHashMap.computeIfAbsent(k, ...)` with `LongAdder` commonly used?**  
   It safely creates/looks up the shared counter per key at the map level, and then each `increment()` can run concurrently.

8. **If `DoubleAdder` sums money, what goes wrong arithmetically?**  
   `double` cannot represent all decimal numbers accurately and addition order can change the result. Use a decimal model or exact integer units instead.

## 13. Key Takeaways and Documentation

`LongAdder` and `DoubleAdder` help threads **accumulate statistical metrics** under contention. The main benefit is reducing update pressure on a single atomic location. In return, `sum()` does not promise an atomic snapshot while writes are occurring; `sumThenReset()` does not establish an exact period boundary under contention; `DoubleAdder` remains subject to IEEE 754 limits.

Official API documentation:

- [Java 21 — `LongAdder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [Java 21 — `DoubleAdder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/DoubleAdder.html)
- [Java 21 — `AtomicLong`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html)
- [Java 21 — `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
