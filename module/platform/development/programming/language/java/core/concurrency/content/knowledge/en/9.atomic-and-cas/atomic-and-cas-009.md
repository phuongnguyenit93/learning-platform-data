# LongAdder and LongAccumulator under Contended Updates in Java

When dozens or hundreds of threads continuously add to **a shared counter**, every update to the same atomic variable can experience contention. In Java, `AtomicLong` provides atomic read–modify–write operations that are well suited when you need **a single value that can be read immediately at any point in time** and operations such as `getAndIncrement()`. However, for **continuously accumulated statistics** (hit counts, event counts, byte counts), having every thread contend on a single update point can become a bottleneck.

`LongAdder` and `LongAccumulator` in the `java.util.concurrent.atomic` package are two specialized JDK utilities: instead of forcing all updates to contend on a single storage location, the implementation can **distribute updates across multiple internal cells**, and combine them when read. They often improve throughput under high contention, at the trade-off of **higher memory overhead and a sum read that is not an atomic snapshot**.

This article belongs to **Atomic & CAS**, focusing on **general Java concurrency, Java 17+**. It does not use Spring-specific concurrency features.

Objectives:
- Accurately distinguish `AtomicLong`, `LongAdder`, and `LongAccumulator` by semantics, not just speed.
- Use `LongAdder.increment()`, `add()`, `sum()`, `reset()`, and `sumThenReset()` in the right context.
- Design functions and identities for `LongAccumulator`; understand why **associative, commutative, side-effect-free** are important requirements.
- Explain why reading a sum or resetting during updates **does not produce an exact snapshot / time-period boundary**.
- Choose the right tool for metrics, per-key counting, max/min operations, and recognize when you need a linearizable update from `AtomicLong` or a lock.

## 1. The problem: a single shared update point under contention

Suppose multiple threads concurrently increment the number of processed events:

~~~java
// Logic illustration, not a standalone runnable file.
private final AtomicLong events = new AtomicLong();

void onEvent() {
    events.incrementAndGet();
}
~~~

`AtomicLong.incrementAndGet()` guarantees that each increment is an **atomic read–modify–write** operation on the same value. That is a major advantage: if the caller needs **the new value of that specific increment**, the API returns that number immediately. However, when many threads continuously update the same point, contended synchronization around this value can increase retry counts and hardware cache-coherence overhead.

Usually there are two distinct categories of needs:

1. **Control state / exact decisions:** issuing unique sequence numbers, checking a limit then incrementing, transitioning state according to a protocol. This requires atomicity at **a single update point**; `AtomicLong` or an appropriate primitive/lock is suitable.
2. **Statistical metrics:** each thread only wants to report "add 1", "add 64 bytes", or "update max". The caller does not need to know the new value after each individual update; a value read while threads are still writing can be a **transient measurement**. `LongAdder`/`LongAccumulator` are worth considering.

**Having many threads does not automatically mean LongAdder is always faster than AtomicLong.** Under low contention, the difference may be small; for write-light, read-heavy workloads or when low memory footprint is needed, `AtomicLong` may be more appropriate. Choose based on **the right semantics first**, then benchmark in practice.

## 2. LongAdder: accumulating long values across multiple threads

`java.util.concurrent.atomic.LongAdder` maintains a `long` sum, initially **0**. Main methods:

| Method | Meaning | Returns |
| --- | --- | --- |
| `add(long x)` | Adds `x` (negative values allowed) | `void` |
| `increment()` | Equivalent to `add(1)` | `void` |
| `decrement()` | Equivalent to `add(-1)` | `void` |
| `sum()` | Sums internal values to return the currently observed total | `long` |
| `longValue()` | Equivalent to `sum()` | `long` |
| `reset()` | Resets internal cells to 0 | `void` |
| `sumThenReset()` | Gets the sum and resets, useful between phases when no writers remain | `long` |

Each `add`/`increment` contributes to the sum maintained by the class's concurrency mechanism. Under contention, the implementation can distribute updates across a **base** and **cells** (auxiliary slots). When `sum()` is read, it aggregates these components.

~~~text
Conceptual model (not a fixed layout across all JVMs):

             LongAdder
       +--------------------+
       | base: partial sum  |
       | cells when needed: |
       |  cell[0]: +8       |
       |  cell[1]: +6       |
       |  cell[2]: +9       |
       +--------------------+
             |
             v
       sum() -> aggregate

Threads can update different cells to reduce contention.
~~~

A specific thread is **not guaranteed by the API to remain bound to a single cell**, the number of cells is not a fixed API parameter, and the number of cells can grow under contention. This is a design explanation, not a promise about internal representation or hashing across all JDK versions.

### 2.1. Java 17+ example: four threads updating 40,000 times

~~~java
// LongAdderContentionDemo.java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.LongAdder;

public class LongAdderContentionDemo {
    public static void main(String[] args) throws InterruptedException {
        int workers = 4;
        int perWorker = 10_000;

        LongAdder total = new LongAdder();
        CountDownLatch begin = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(workers);

        for (int i = 0; i < workers; i++) {
            Thread t = new Thread(() -> {
                try {
                    begin.await();
                    for (int n = 0; n < perWorker; n++) {
                        total.increment();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    done.countDown();
                }
            });
            t.start();
        }

        begin.countDown();
        done.await();
        System.out.println("Total: " + total.sum());
    }
}
~~~

~~~bash
javac LongAdderContentionDemo.java
java LongAdderContentionDemo
~~~

In a normal run without unexpected interrupts, stdout is:

~~~text
Total: 40000
~~~

**Explanation:** Each of the four workers contributes 10,000. Main only calls `sum()` **after** `done.await()` has confirmed that all four tasks have completed. Actions prior to `countDown()` are published according to `CountDownLatch` memory-consistency guarantees; there are no concurrent updates left when main computes the sum. Therefore `sum()` yields the exact result in this example.

If main calls `total.sum()` **while workers are still updating**, it only receives a transient value, **not an atomic snapshot**.

### 2.2. Incrementing, decrementing, adding negative amounts

~~~java
// LongAdderOperationsDemo.java
import java.util.concurrent.atomic.LongAdder;

public class LongAdderOperationsDemo {
    public static void main(String[] args) {
        LongAdder value = new LongAdder();

        value.add(10);
        value.increment();
        value.decrement();
        value.add(-3);
        System.out.println("Sum: " + value.sum());

        long finished = value.sumThenReset();
        System.out.println("Finished: " + finished);
        System.out.println("After reset: " + value.sum());
    }
}
~~~

~~~bash
javac LongAdderOperationsDemo.java
java LongAdderOperationsDemo
~~~

Stdout:

~~~text
Sum: 7
Finished: 7
After reset: 0
~~~

`sumThenReset()` is called when **there are no writers**, so it does not contend with a reset; thus the numbers above are deterministic. `LongAdder` is not limited to positive increments; `add(-3)` is valid. However, calling `sum()` followed by `add(-amount)` does not form a business transaction for "check quota then deduct", because `sum` is not a synchronization point for that invariant.

## 3. LongAccumulator: accumulating with a custom operation

`java.util.concurrent.atomic.LongAccumulator` aggregates `long` values using a caller-supplied operation:

~~~java
new LongAccumulator(accumulatorFunction, identity);
~~~

- `accumulatorFunction` is a `java.util.function.LongBinaryOperator`, with signature `long applyAsLong(long left, long right)`.
- `identity` is the identity element of the operation, i.e., a value e satisfying `f(e, x) = x` (and should also satisfy `f(x, e) = x` for symmetric combination rules).
- `accumulate(x)` feeds an observation x into the accumulator.
- `get()` (or `longValue()`) returns the aggregated result of the internal storage parts.
- `reset()` resets back to identity; `getThenReset()` reads then resets, but is not an atomic period-closing operation with respect to concurrent updates.

Because no accumulation order is guaranteed across threads, the operation **must be suitable for combining in different orders and groupings**. According to the JDK documentation, for predictable results, the operator should be **associative, commutative, and side-effect-free**.

| Accumulation | Operator | Suitable identity | Interpretation |
| --- | --- | --- | --- |
| Sum | `Long::sum` | `0L` | Sum of update amounts |
| Maximum | `Long::max` | `Long.MIN_VALUE` | Largest observed value |
| Minimum | `Long::min` | `Long.MAX_VALUE` | Smallest observed value |
| Bitwise OR | `(a, b) -> a \| b` | `0L` | Union of bit flags |
| Bitwise XOR | `(a, b) -> a ^ b` | `0L` | XOR of values |
| Running subtraction | `(a, b) -> a - b` | Not suitable for this aggregation | Not associative/commutative |
| Running average `(a+b)/2` | Not suitable | Does not satisfy associativity | Depends on order and rounding |

**Warning about maximum identity:** If you use `Long::max` with an identity of `0L`, a set of observations containing only negative numbers (e.g., -12, -4, -7) will produce **0**, which is wrong. You must choose `Long.MIN_VALUE` so that every `long` is valid. Conversely, `Long::min` should use `Long.MAX_VALUE`.

### 3.1. Java 17+ example: finding the maximum of negative values

~~~java
// LongAccumulatorMaxDemo.java
import java.util.concurrent.atomic.LongAccumulator;

public class LongAccumulatorMaxDemo {
    public static void main(String[] args) throws InterruptedException {
        LongAccumulator maximum =
            new LongAccumulator(Long::max, Long.MIN_VALUE);

        Thread a = new Thread(() -> {
            maximum.accumulate(-9);
            maximum.accumulate(-4);
        });
        Thread b = new Thread(() -> {
            maximum.accumulate(-12);
            maximum.accumulate(-7);
        });
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Maximum: " + maximum.get());
        System.out.println("Saved: " + maximum.getThenReset());
        System.out.println("After reset: " + maximum.get());
    }
}
~~~

~~~bash
javac LongAccumulatorMaxDemo.java
java LongAccumulatorMaxDemo
~~~

Stdout:

~~~text
Maximum: -4
Saved: -4
After reset: -9223372036854775808
~~~

Because `Long::max` is **associative/commutative**, the result does not depend on which thread updates first. After `join()`, no writers remain, so `getThenReset()` returns -4 accurately, and `get()` after reset returns to the identity `Long.MIN_VALUE`, not 0.

**Distinguishing an empty state:** For max using `Long.MIN_VALUE`, if no samples have been recorded yet, `get()` also returns `Long.MIN_VALUE`. If the system needs to distinguish "nothing observed yet" from "observed `Long.MIN_VALUE` itself", additional design is required (such as a state structure with a presence flag), and consistency when reading multiple variables must be accounted for.

### 3.2. Another operation example: GCD (greatest common divisor)

The GCD of positive integers is associative and commutative, and the appropriate identity is `0` because `gcd(0,x)=x` for positive x.

~~~java
// LongAccumulatorGcdDemo.java
import java.util.concurrent.atomic.LongAccumulator;

public class LongAccumulatorGcdDemo {
    private static long gcd(long a, long b) {
        while (b != 0) {
            long remainder = a % b;
            a = b;
            b = remainder;
        }
        return a;
    }

    public static void main(String[] args) {
        // Example only passes positive integers.
        LongAccumulator gcdAccumulator =
            new LongAccumulator(LongAccumulatorGcdDemo::gcd, 0L);

        gcdAccumulator.accumulate(18);
        gcdAccumulator.accumulate(24);
        gcdAccumulator.accumulate(30);
        System.out.println("GCD: " + gcdAccumulator.get());
    }
}
~~~

~~~bash
javac LongAccumulatorGcdDemo.java
java LongAccumulatorGcdDemo
~~~

Stdout:

~~~text
GCD: 6
~~~

The `gcd` function here is **pure**, modifies no external state, and only accepts positive numbers in the example. To support all `long` values, you would need careful handling for negative numbers and `Long.MIN_VALUE` because `Math.abs(Long.MIN_VALUE)` overflows in `long`; the example only illustrates associativity/commutativity over positive numbers.

### 3.3. The accumulator function may be re-executed

Do not use the updater to cause non-repeatable side effects:

~~~java
// CODE TO AVOID: logic illustration, not a standalone program.
LongAccumulator wrong = new LongAccumulator((current, x) -> {
    sendEmail(x); // Side effect may repeat during retries.
    return current + x;
}, 0L);
~~~

Because the implementation may retry updates under contention, the function can be applied **multiple times for a single `accumulate` call**. Correct code only performs a pure computation from `current` and `x` and returns the result; sending emails, writing to a DB, or logging one-time business events must be kept separate from the accumulation function.

Choosing an operator that is not associative/commutative, such as subtraction, is also a bug: the result depends on order and cell partitioning, whereas the API does not guarantee a single ordering.

## 4. Why does it reduce contention?

### 4.1. AtomicLong: a single update point

`AtomicLong` holds a single `long` state that atomic updates contend on. This is ideal when you need:

- `incrementAndGet()` returning the new value immediately.
- `getAndIncrement()` issuing a **unique sequence number** at the point of increment.
- `compareAndSet(expected, update)` for a conditional state transition.
- `get()` reading **a current atomic value** of the field per API semantics.

### 4.2. LongAdder/Accumulator: distributing updates when needed

Under contention, the implementation can increase the number of internal variables holding partial sums. Threads update their corresponding internal part, and when reading the result, the code must combine those parts. What is optimized is **update throughput** under contention, with these trade-offs:

- Uses **more memory**, especially with many LongAdder/LongAccumulator instances and many writers.
- `sum()`/`get()` must aggregate multiple components, so **read** cost can increase.
- `sum()`/`get()` is **not an atomic snapshot** while writers are still updating.
- There is no result **returned per individual update** like `AtomicLong.incrementAndGet()`; `LongAdder.increment()` returns `void`.
- Reset operations must be used in phases **without concurrent updates** if exact period-boundary results are needed.

Distributing updates does not mean using a coarse lock to guard every update. Both classes leverage internal JDK atomic mechanisms and coordination, but they do not provide a lock for callers to wrap a multi-step transaction.

## 5. sum() / get(): the read value is not an atomic snapshot

The JDK 17 documentation explicitly states:

- `LongAdder.sum()` returns the currently aggregated sum, **not an atomic snapshot**. Updates occurring during aggregation may not be included in the result.
- `LongAccumulator.get()` is likewise **not an atomic snapshot** with respect to concurrent updates.
- When **there are no concurrent updates**, summing/getting returns the exact value of completed updates published under an appropriate synchronization protocol.

Imagine a read summing multiple cells:

~~~text
Time →
Reader:   read cell A = 10 ────── read cell B = 20 ─── returns 30
Writer:             update A to 11 ─── update B to 21

There may not exist a single point in time where the sum of A and B
equals the value the Reader just computed from different cell versions.
~~~

This is a **conceptual diagram** of the lack of an atomic snapshot, not an exact description of the JDK's per-cell mechanics. Avoid concluding that "every `sum()` call returns the total **at the time of the call**" if writers are still running.

### 5.1. Reading statistics and making business decisions are two different things

Reasonable cases:
- Displaying an approximate metric while requests are still being processed.
- Counting tasks/hits accumulated in a worker pool, read periodically for monitoring.
- Aggregating observed max latency without requiring a linearizable snapshot for control algorithms.

Cases where you **should not** rely solely on `sum()`:
- `if (adder.sum() < limit) adder.increment()` to enforce a **hard limit**.
- `sum()` to issue unique ticket/ID numbers.
- Deciding to book when `available == 1` and then decrementing, needing to prevent overselling.
- Finalizing an exact billing figure at a precise point in time while threads are still updating.

Even `AtomicLong` does not automatically turn **a sequence of `get()` then `incrementAndGet()`** into a conditional transaction. When there is a constraint like "increment only if below the limit", use a **CAS loop**, a lock, or a dedicated primitive to check and update at the same atomic point.

### 5.2. Wanting an exact sum after a batch: wait for writers to finish

The `LongAdderContentionDemo` example used `CountDownLatch` to wait for all tasks before calling `sum()`. A program using an executor can:
1. `submit` all tasks;
2. wait for all `Future.get()` calls to complete successfully (handling exceptions/cancellations properly);
3. ensure no new producers write to the same counter;
4. read `sum()` after that synchronization point.

**It is not enough** to just see that `ExecutorService.shutdown()` has been called: shutdown stops accepting new tasks but **does not wait** for already-accepted tasks to finish. If waiting is interrupted, times out, or a task continues running after the caller stops waiting, you cannot claim there are no concurrent updates.

## 6. reset(), sumThenReset(), getThenReset(), and period boundaries

`LongAdder.reset()` sets the sum components to 0. `LongAdder.sumThenReset()` reads the sum then resets; `LongAccumulator.reset()` sets the components to **identity**; `LongAccumulator.getThenReset()` reads the result then resets to identity.

These operations **are not guaranteed to be atomic with concurrently updating writers**. The JDK describes reset as an inherently contended operation; it is only safe for exact metrics when **no concurrent updates are known to be occurring**.

| API | After reset | Condition to finalize exact metrics |
| --- | --- | --- |
| `LongAdder.reset()` | 0 | No concurrent writers |
| `LongAdder.sumThenReset()` | 0 | No concurrent writers |
| `LongAccumulator.reset()` | Identity provided at creation | No concurrent writers |
| `LongAccumulator.getThenReset()` | Identity provided at creation | No concurrent writers |

### 6.1. Why can concurrent reset lose updates?

Aggregating and clearing internal cells **is not a single transaction** with all ongoing updates. An update can fall in the window between reading and clearing a cell and end up not being classified into the closed period or the new period as intended. Consequently, the result of `sumThenReset()` while producers are writing **has no guarantee** of equaling "all events before the reset point", nor is the next period guaranteed to recover an exact logical boundary.

Do not read the name `sumThenReset` as "atomic `getAndSet(0)`". With `AtomicLong`, `getAndSet(0)` is a single atomic operation on **a single variable** and has different semantics.

### 6.2. Strategies when periodic reporting is needed

**Approach A — Quiescence point:** pause or block new producers, wait for all current producers to finish, then call `sumThenReset`/`getThenReset`, and let producers resume. This is the direct way to establish a boundary.

**Approach B — Approximate statistics:** continuously call `sum()`/`get()` without resetting, accept instantaneous values, and compute deltas between observations for dashboards. This delta is **not** a transactionally exact measurement if writers are still active; it is suitable for monitoring metrics.

**Approach C — Coordinated counter generation swap:** you can manage multiple counters/snapshots by epoch, but swapping an `AtomicReference<LongAdder>` with `getAndSet` is **not enough** to create a strict boundary: a writer already holding a reference to the old counter can update it **after** the new reference is published. To avoid dropping or miscounting across periods, you need a coordination protocol with running writers (drain/in-flight tracking, locks, barriers, or another mechanism), not just swapping the reference.

When business logic requires per-transaction or balance accuracy, use an appropriate transactional primitive instead of relying on LongAdder-style statistics.

## 7. LongAdder vs. AtomicLong: choosing by goal

| Criterion | `AtomicLong` | `LongAdder` |
| --- | --- | --- |
| State | A single atomic `long` value | Sum distributed across internal values under contention |
| Increment operation | `incrementAndGet()` / `getAndIncrement()` returns value | `increment()` returns `void` |
| Read | `get()` is an atomic read of one value | `sum()` is not an atomic snapshot |
| Conditional CAS | Has `compareAndSet` | Does not provide CAS on the sum |
| Under high contention | Can incur cost at a single update point | Usually has higher update throughput |
| Under low contention | Simple, low overhead | Little benefit; sum management overhead still exists |
| Memory | Usually smaller | Can be larger when expanding internally |
| Purpose | Control/state transitions, IDs, point-in-time accuracy on one variable | Metrics, counters, high-throughput updates |
| Reset | `getAndSet(0L)` is an atomic RMW | `sumThenReset()` is not atomic with concurrent updates |

**Examples of sound decisions:**
- Page view counts continuously incremented by workers and read for dashboard display → `LongAdder` is a good candidate to try.
- Issuing strictly unique increasing sequence numbers per request → use `AtomicLong.getAndIncrement()`.
- Hard limit "at most 100 concurrent active tasks" → use a synchronization protocol for **check and update** (e.g., CAS/semaphore), not `if (adder.sum() < 100)`.
- Recording metrics for a batch job with a full `join()` before finalizing → `LongAdder.sum()` is accurate after the batch.

### Why not use volatile long++?

`volatile long count` provides visibility/ordering for field reads/writes, but `count++` is still a **non-atomic read–modify–write**. Two threads can read the same value and both write back the new result, causing lost updates. `AtomicLong.incrementAndGet()` and `LongAdder.increment()` solve concurrent accumulation under each API's contract, but carry different read semantics.

## 8. LongAccumulator vs. LongAdder and AtomicLong

| Criterion | `LongAdder` | `LongAccumulator` | `AtomicLong` |
| --- | --- | --- | --- |
| Combination op | `long` addition | Custom `LongBinaryOperator` | Atomic update on one `long` |
| Identity | Always 0 | Supplied by caller | Initial value supplied by caller |
| Update | `add`, `increment`, `decrement` | `accumulate(x)` | `addAndGet`, `updateAndGet`, `accumulateAndGet`... |
| Read | `sum()` | `get()` | `get()` |
| Atomic snapshot during writes | No | No | Yes for a single `long` |
| Contention level | Can distribute updates | Can distribute updates | Contends on a single value |
| Best suited for | Hits, bytes, event counts | Max/min or custom reductions | Sequence numbers, CAS, conditional updates |

`LongAdder` is the common case of addition and can be understood as roughly analogous to `new LongAccumulator(Long::sum, 0L)` in aggregation semantics, though `LongAdder`'s dedicated API is more convenient and implementation/performance should be measured per workload.

**Do not use `LongAccumulator` with arbitrary operators.** The operator needs a true identity and must not depend on combination order. For example, "keep running average" `(old + sample) / 2` is not associative and does not produce the true overall average. If you want an average, track **sum + count** and divide when aggregating; if you need an exact simultaneous snapshot of both, coordinate reading both with an appropriate protocol.

**Long overflow:** both `LongAdder` and `LongAccumulator` return `long`; operations on `long` can **overflow** according to Java integer rules. If business logic requires totals beyond `long` range with exact precision, choose a different representation and synchronization mechanism; do not assume distributing counters prevents overflow.

## 9. Per-key counting pattern with ConcurrentHashMap

A common scenario: counting occurrences of each event code. You can use `ConcurrentHashMap<String, LongAdder>` so each key has its own concurrent counter. `computeIfAbsent` safely handles creating/retrieving the counter for a key under the map's contract; `increment()` adds to the retrieved instance.

~~~java
// LongAdderFrequencyDemo.java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class LongAdderFrequencyDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, LongAdder> frequency =
            new ConcurrentHashMap<>();

        Runnable record = () -> {
            frequency
                .computeIfAbsent("ok", key -> new LongAdder())
                .increment();
            frequency
                .computeIfAbsent("error", key -> new LongAdder())
                .increment();
            frequency
                .computeIfAbsent("ok", key -> new LongAdder())
                .increment();
        };

        Thread a = new Thread(record);
        Thread b = new Thread(record);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("ok: " + frequency.get("ok").sum());
        System.out.println("error: " + frequency.get("error").sum());
    }
}
~~~

~~~bash
javac LongAdderFrequencyDemo.java
java LongAdderFrequencyDemo
~~~

Stdout:

~~~text
ok: 4
error: 2
~~~

**Why is this correct?** Both threads add to the adder associated with the corresponding key; creating the value via `computeIfAbsent` is a concurrent map operation, rather than hand-rolled `if (map.get(key) == null) map.put(key,new LongAdder())`. Main `join()`s both workers before reading; the result does not depend on scheduling order.

**Limitations to remember:**
- If code **removes/replaces** a key's value while another writer already holds a reference to the old adder, updates may go to an object no longer referenced by the map. You must design the key/counter lifecycle and not assume every `increment` is guaranteed to be reflected in the value currently stored in the map.
- Calling `sum()` across multiple keys while writers are active **does not yield an atomic snapshot of the entire map**.
- One adder per key: with many rarely updated keys, object/metadata overhead can be significant. Consider retention/eviction and benchmark.

## 10. Common mistakes with LongAdder/LongAccumulator

1. **Treating `sum()` as an atomic read of the total.** False while writers are updating. The result is a transient aggregation, not a linearizable snapshot.
2. **Using `sum()` to enforce a hard limit.** The pattern `if (counter.sum() < limit) counter.increment()` suffers from a check–then–act race and reads a non-atomic snapshot.
3. **Using `sumThenReset()` to finalize exact counts while producers are still writing.** Contended resets can drop or misclassify counts across periods. You need quiescence or a fully synchronized epoch protocol.
4. **Choosing the wrong identity for LongAccumulator.** Using 0 with `Long::max` fails when all samples are negative; use `Long.MIN_VALUE`.
5. **Using a non-associative/non-commutative operator.** Results can depend on ordering and grouping, which are not guaranteed.
6. **Putting side effects inside the operator.** The operator may re-run on retries, causing duplicate notifications or payments.
7. **Confusing `increment()` with `incrementAndGet()`.** `LongAdder.increment()` returns `void` and does not issue sequence IDs.
8. **Assuming LongAdder is always faster.** Contention level, read frequency, GC, instance count, and CPU architecture all affect results.
9. **Thinking LongAdder is a monotonically non-decreasing counter.** `add(-x)` and `decrement()` are valid, and a sum across multiple cells read concurrently does not guarantee a simple progression like a single AtomicLong.
10. **Forgetting to handle overflow.** `long` results are bounded; consider value range and counter lifetime.
11. **Assuming `reset()` is thread-safe across periods.** `reset()` is not an atomic epoch transition; writers must be prevented from updating during reset if exactness is required.
12. **Using a frequency map with uncontrolled key removal.** Writers may already hold references to old values; replacing a map entry does not stop in-flight updates to that old value.

## 11. How to benchmark before choosing

To compare `AtomicLong` with `LongAdder` or `LongAccumulator`, use a representative workload, not just a short loop in `main`.

- **Writer count:** one thread, a few threads, more threads than cores? Test multiple levels.
- **Read frequency:** dashboard every second or reading continuously after each update? `sum()` has aggregation cost when there are many cells.
- **Work profile:** is there other computation between updates, or do all threads hammer a single point?
- **Instance count:** one hot counter differs from thousands of cold counters in a map.
- **Memory and GC:** adders can consume more memory; measure heap/allocations if it matters.
- **Warmup/JIT/CPU:** use a reliable microbenchmarking tool such as **JMH** for serious measurements; avoid drawing conclusions from `System.nanoTime()` around an uncontrolled, optimizable loop.
- **Correctness first:** ensure results after all writers finish are correct; do not trade required atomicity for throughput numbers.

Typically measure **operations/second**, **latency**, and **memory** across contention levels. A benchmark result on one machine is not a guarantee across all workloads.

## 12. Safe design checklist

1. **Identify the nature of the metric:** statistical metric or control state? Do you need a value **returned immediately from each update**?
2. **Write down correctness constraints:** is an exact total only needed at the end of a batch, or are decisions required at every point in time?
3. **Choose the primitive:** `AtomicLong` for IDs/conditional CAS; `LongAdder` for hot sums/counters; `LongAccumulator` for reductions like max/min with a valid operator.
4. **Verify the operator:** does it have a true identity, and is it associative, commutative, and side-effect-free? Are there overflow/negative-value/special input domain issues?
5. **Define read points:** if calling `sum()/get()` while writers run, accept it is not an atomic snapshot; if exactness is needed, coordinate stopping and waiting for writers.
6. **Design reset periods:** never assume `sumThenReset()/getThenReset()` is atomic with producers. Build a quiescence/epoch protocol if exact period closing is required.
7. **Evaluate counter lifecycle:** in a map, who creates/removes/replaces? Can writers hold stale references?
8. **Stress test and benchmark:** test multiple contention levels, assert final figures, and monitor throughput and memory before optimizing.

## 13. Self-check

**1.** Four threads each increment a `LongAdder` 10,000 times; main waits for all four threads then calls `sum()`. What is the expected value?  
**Answer:** 40,000 if all workers complete their updates; after the wait point there are no concurrent updates, so the sum is exact.

**2.** Can `LongAdder.increment()` be used to return a unique ID for each request?  
**Answer:** No. The method returns `void`, and `sum()` is not an atomic snapshot. If IDs are needed, use `AtomicLong.getAndIncrement()` or an equivalent primitive.

**3.** With `LongAccumulator(Long::max, 0L)`, add -5 and -2. The right answer should be -2, but what might `get()` return?  
**Answer:** 0, because the wrong identity was chosen. Fix it to `Long.MIN_VALUE`.

**4.** Why is `LongAccumulator((a,b)->a-b, 0)` unsuitable?  
**Answer:** Subtraction is neither associative nor commutative; the result depends on update order and grouping.

**5.** Is `sumThenReset()` an atomic operation equivalent to `AtomicLong.getAndSet(0)`?  
**Answer:** No. With concurrent writers, aggregating and resetting internal cells does not form an atomic period boundary.

**6.** If you want to count per-key frequencies in a `ConcurrentHashMap`, what pattern is reasonable?  
**Answer:** `map.computeIfAbsent(key, k -> new LongAdder()).increment()`. Additional coordination is needed if keys can be removed/replaced concurrently.

**7.** When might `LongAdder` be less advantageous than `AtomicLong`?  
**Answer:** When contention is low, sums are read continuously, there are many rarely updated counters, or the extra memory / aggregation read cost is unsuitable.

**8.** With `LongAccumulator(Long::max, Long.MIN_VALUE)` and no samples yet, what does `get()` return?  
**Answer:** It returns the identity `Long.MIN_VALUE`; it cannot tell "no samples yet" unless the application adds a model representing presence.

**9.** Is swapping an `AtomicReference<LongAdder>` to a new adder enough to strictly close the previous period?  
**Answer:** Not enough. A worker that already read the old reference can still update it after the swap; you need to coordinate with running writers for an exact boundary.

**10.** Should `LongAccumulator` use an operator with database-writing side effects?  
**Answer:** No. The function can be re-applied during retries. Keep the operator pure and separate I/O from the reduction.

**Key takeaway:** `LongAdder` is a strong choice for **counters/sums updated by many threads** when a read snapshot during writes does not need to be linearizable. `LongAccumulator` extends the idea to reductions with a proper identity and an associative/commutative, pure operator. `AtomicLong` remains essential when you need **a single atomic update/read point or conditional CAS**. Choose for protocol correctness first, then optimize throughput.

### Official References

- Java SE 17, `LongAdder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- Java SE 17, `LongAccumulator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAccumulator.html
- Java SE 17, `AtomicLong`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html
- Java SE 17, `ConcurrentHashMap`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html