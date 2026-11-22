# False Sharing and Cache-Line Contention in Java Concurrency

## 1. The Problem: Two Threads Without Shared Variables Still Slowing Each Other Down

Suppose two threads perform independent work: thread A continuously updates counter A, and thread B continuously updates counter B. The two counters are in **different storage locations** and each counter is written by only one thread, so from the perspective of program logic, they do not need to contend for a lock. Why, then, can the program still run slowly when both threads execute concurrently on two CPU cores?

One cause is **false sharing**: two independent variables reside on the **same cache line**, while at least one thread repeatedly writes to its own data. The cache coherence protocol manages ownership at the *cache line* level, not at the level of individual Java variables. As a result, cores may have to repeatedly transfer write ownership of the same line, even though they never modify the same variable.

This is a **performance** issue of memory layout and concurrent access; it does not mean there is a *data race* or a Java Memory Model (JMM) bug.

**Lesson objectives:** understand the cache line mechanism, distinguish false sharing from true sharing, recognize common access patterns in Java, perform controlled measurements, and choose solutions commensurate with their costs.

## 2. What Is a Cache Line?

A CPU typically does not load an individual 8-byte `long` variable from main memory into cache on its own; it transfers data in contiguous blocks of memory called **cache lines**. Many modern x86-64 systems use **64-byte** lines, though the size and protocol details depend on CPU architecture. **There is no guarantee in the Java language that every machine uses a 64-byte cache line.**

Example illustrating a 64-byte cache line (logical diagram, not a JVM object layout guarantee):

```text
                  CACHE LINE (64 bytes, illustrative)
byte offset       0       8      16      24      32       ...    63
                  +-------+-------+-------+-------+---------------+
Thread A writes ->|   A   |   B   | other data in the same line   |
                  +-------+-------+-------+-------+---------------+
                          ^
                          |
                   Thread B writes

A and B are two independent longs (each long typically occupies 8 bytes).
```

A simplified model of this phenomenon on a multi-core machine:

1. Core 0 acquires the line containing A and B in a writable state, then updates A.
2. Core 1 wants to write B. Because B lies on the **same line**, core 1 must acquire the appropriate state/ownership of that line according to the cache coherence protocol.
3. Core 0 continues writing A, so it again needs write ownership of the line. Ownership of the line can bounce back and forth between cores; coherence traffic and wait times increase.
4. The more interleaved updates occur, the greater the line-transfer overhead becomes compared to the simple logical addition.

Protocols such as MESI/MOESI are useful mental models, though one should not assert that every CPU or every write always executes the exact same sequence of messages. Nor does it necessarily involve copying back to DRAM after every update: data/ownership transfers can occur between caches within the memory hierarchy.

**The issue lies in the granularity of cache coherence:** the hardware does not know that A and B are logically independent fields. It must preserve coherence for the entire line.

## 3. Distinguishing True Sharing, False Sharing, and Lock Contention

| Situation | What do the two threads access? | What is being contended? | Common mitigation approaches |
| --- | --- | --- | --- |
| **True sharing** | Same counter/address; at least one thread writes | The shared value and write ownership of the line containing it | Reduce update frequency, sharding/striping, aggregate results |
| **False sharing** | Two different counters/addresses, but on the same cache line | Ownership of the **line**, even though no value is shared | Separate hot locations onto different lines; batch updates locally |
| **Lock contention** | Same monitor/`Lock` or critical section | Synchronization/lock-waiting mechanism; sometimes accompanied by cache effects | Shorten lock scope, reduce competing threads, redesign synchronization |
| **Read-only sharing** | Multiple cores only read unchanging data | Typically no continuous write stream causing line ping-pong | Can be completely normal; avoid pointless optimization |

All three performance causes can **coexist**. For example, two different locks placed next to each other can cause false sharing on metadata, while threads also genuinely contend on another lock.

False sharing only matters when there is a **repeated write** pattern large enough for coherence overhead to be significant. Two adjacent variables that are only read, or written only once each, do not automatically cause a practical problem.

## 4. Java 17+ Example: Updating `AtomicLongArray` at Near and Far Indices

`AtomicLongArray` provides atomic read/write operations per element; each `getAndIncrement(index)` performs an atomic update at an **individual index**. We can create two threads, each owning one index, so there is no logical contention on the same counter.

Two configurations to observe:

- **near:** two threads write to indices `0` and `1`, which are typically two adjacent `long`s in the array's backing storage.
- **far:** two threads write to `0` and `32`; the element distance is 256 bytes, much farther than a typical 64-byte cache line.

**Important caveat:** The JVM and hardware do not guarantee addresses/alignment or cache line size for this example, so this is an **illustrative experiment** rather than a benchmark that proves false sharing on every machine. Atomic increment itself has overhead; timing differences must not be automatically attributed solely to false sharing.

Create `FalseSharingDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLongArray;

public final class FalseSharingDemo {
    private static final int ITERATIONS = 2_000_000;

    private record Measurement(long elapsedNanos, long left, long right) {}

    private static Thread worker(
            AtomicLongArray counters,
            int index,
            CountDownLatch ready,
            CountDownLatch start) {
        return new Thread(() -> {
            ready.countDown();
            try {
                start.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            for (int i = 0; i < ITERATIONS; i++) {
                counters.getAndIncrement(index);
            }
        }, "counter-" + index);
    }

    private static Measurement runCase(int leftIndex, int rightIndex)
            throws InterruptedException {
        AtomicLongArray counters = new AtomicLongArray(64);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Thread leftThread = worker(counters, leftIndex, ready, start);
        Thread rightThread = worker(counters, rightIndex, ready, start);
        leftThread.start();
        rightThread.start();

        // Start measuring once both threads are ready.
        ready.await();
        long begin = System.nanoTime();
        start.countDown();

        leftThread.join();
        rightThread.join();
        long elapsed = System.nanoTime() - begin;

        long left = counters.get(leftIndex);
        long right = counters.get(rightIndex);
        if (left != ITERATIONS || right != ITERATIONS) {
            throw new AssertionError("Counter value is incorrect");
        }
        return new Measurement(elapsed, left, right);
    }

    public static void main(String[] args) throws InterruptedException {
        Measurement near = runCase(0, 1);
        Measurement far = runCase(0, 32);

        System.out.println("near counts: " + near.left() + " / " + near.right());
        System.out.println("far counts: " + far.left() + " / " + far.right());
        System.out.printf("near: %.3f ms; far: %.3f ms%n",
                near.elapsedNanos() / 1_000_000.0,
                far.elapsedNanos() / 1_000_000.0);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac FalseSharingDemo.java
java FalseSharingDemo
```

The first two lines of stdout on a normal run will be:

```text
near counts: 2000000 / 2000000
far counts: 2000000 / 2000000
```

The last line prints `near: <time> ms; far: <time> ms`; **values vary by run and machine**, so there is no fixed stdout number for this line. Seeing `near` slower than `far` is a sign consistent with the false sharing hypothesis, **not conclusive proof**. Sometimes the two cases are equal or reversed due to JIT, the scheduler, core count, CPU state, system noise, and array layout.

Why use `CountDownLatch` and `join()`?

- `ready` ensures both threads are ready before releasing `start`, reducing startup skew; it still does not eliminate all noise.
- `join()` waits for both threads to finish before reading the counters. Both the atomicity of `AtomicLongArray` and the *happens-before* relationship of thread termination/`join` help verify correct results.
- Each index is **updated by only one thread**. The result is correct in both cases; any difference is execution cost, not lost updates.
- Each `getAndIncrement` uses an atomic primitive, so its overhead can differ from workloads using plain writes. Do not use the ratio of two runs in this demo to claim a specific production speedup.

## 5. A More Precise Mechanism: Data Proximity and Access Patterns

### Data Location Matters More Than Variable Names

Two fields declared together in the same class are **not guaranteed** to be laid out next to each other in source code order. The JVM may reorder fields, add headers, alignment, and padding; object types, VM modes, and other optimizations also have an effect. Similarly, two Java objects allocated consecutively have **no guarantee** of residing on two different cache lines (or on the same line).

In the array example, primitive elements of the same array are stored in contiguous regions in a typical layout. Therefore, using near/far indices is experimentally more meaningful than assuming two objects created sequentially with `new` will be exactly 64 bytes apart. Even so, **do not turn a 64-byte/layout assumption into a portable Java rule**.

### Read/Write Frequency Determines Severity

A line can be cached in a shared state by multiple cores when they only read it. When a core writes, it needs a writable state and other copies must be handled according to the coherence protocol. False sharing is especially expensive with **continuous, alternating write updates across multiple cores**. If one thread finishes writing before the other starts, or if both threads are scheduled on the same core and do not actually run concurrently, the effect may be less pronounced.

### The Java Memory Model and Cache Coherence Are Not the Same Thing

The JMM defines the visibility, ordering, and *happens-before* rules that a Java program is allowed to rely on. Cache coherence is the underlying hardware mechanism for keeping caches consistent. The JMM **does not promise that two logically independent variables are placed on separate lines**.

- `volatile` and atomic operations provide visibility/ordering guarantees under the Java contract, but they do not prevent false sharing if two independent locations share a line.
- `synchronized` and `Lock` solve logical synchronization requirements; adding locks does not address the root cause of false sharing and can sometimes increase contention.
- A `long[]` where two threads only write to **two different indices** can also experience similar hardware issues without necessarily having a data race on the same element. `AtomicLongArray` is used in the demo so updates actually occur via atomic primitives, making the effect easier to observe; **not** because every primitive array requires atomics.

## 6. Common Java Patterns

### 6.1. A Per-Worker Counter Array

For example, a system assigns `counters[workerId]` to each worker. Logically this avoids true sharing, but the counters sit next to each other. If each worker increments its counter millions of times per second on different cores, a line holding multiple counters can ping-pong. This is a classic false sharing example caused by adjacent data layout.

### 6.2. Multiple State `volatile` Variables Placed Close Together

Two threads may continuously update independent `volatile long sequenceA` and `volatile long sequenceB` fields. If the layout places the fields on the same line, they may contend for write ownership. However, reading source code alone is not enough to prove they share a line: you need to inspect the layout and measure under a realistic workload.

### 6.3. Queues/Ring Buffers with Sequence Cursors

In high-performance data structures, producer and consumer threads may update separate indices, such as publish/consume sequences. Two frequently written cursors sharing a line can cause cache-line contention, even though each side has its own responsibility. This must be measured alongside the synchronization overhead required to ensure proper publish/consume ordering; **never remove `volatile`/atomics just to reduce coherence traffic if doing so breaks visibility**.

### 6.4. Mixing Hot and Cold Data

A frequently written status field placed on the same line as data that other threads frequently read can force readers to reload the line or lose cache efficiency. This is a data layout and invalidation issue. Not every case is a symmetric two-writer pattern, but the same line-granularity coherence principle applies.

## 7. Reducing False Sharing: Choosing a Solution Based on Workload

### A. Reduce the Number of Writes to Shared Data

If business logic allows, each thread can accumulate counts into a local variable in a batch, then periodically flush the total to the shared location. For example, instead of calling `counter.incrementAndGet()` on every event, it can add 100 or 1,000 events to a local variable and publish the sum later. Reducing the number of writes/atomic operations often has a greater impact than padding alone.

However, batching changes metric freshness, introduces the risk of losing unflushed counts on a crash, and alters observation-time semantics. The correctness contract must be clearly stated before applying it.

### B. Spread Hot Data Across Different Lines

For array-based per-worker counters, you can use a stride large enough for the measured architecture, such as index `workerId * 16` for a `long[]` (16 elements = 128 bytes). This **usually** keeps two hot values off the same 64-byte line, but it costs memory and provides no portable guarantee of line size or alignment. With `AtomicLongArray`, increasing index spacing works similarly to the `far` example.

If using a stride, encapsulate the mapping in a small abstraction rather than scattering multiplications throughout the codebase. Check for index overflow, allocation cost, and cache footprint. In particular, never allow two threads to write to the same index due to a miscalculated index.

### C. Use Local Data and Aggregate Later

If each thread owns a counter, it may be best to keep the counter local and aggregate at processing boundaries or via an appropriate snapshot/merge mechanism. `ThreadLocal` can be used in traditional thread pools, but thread lifecycle, resetting, and cleanup must be considered to avoid retaining unwanted state. Do not assume a `ThreadLocal` is an instantaneously readable global-total aggregation strategy.

### D. `LongAdder` for a Single Counter Contended by Many Threads

If **multiple threads update the same logical counter**, `LongAdder` in `java.util.concurrent.atomic` is worth considering. It distributes updates across internal cells under contention, and `sum()` aggregates them afterward; this often reduces true sharing on a single atomic.

However:

- `LongAdder` addresses a **true sharing** pattern; it is not a cure-all for false sharing between independent variables.
- `sum()` is not an atomic snapshot with respect to concurrent updates. Do not use `sum()` as a direct drop-in replacement for a linearizable read if the business logic requires an instantaneous consistent snapshot.
- There is additional memory and aggregation overhead; verify against a real workload.

### E. Padding or `@Contended` at the Appropriate Implementation Layer

Some high-performance libraries intentionally separate hot fields using padding. However, declaring multiple `long p1, p2, ...` fields **does not guarantee** the JVM will preserve the expected order, size, or spacing; the JIT and object layout can alter the result. Separating objects via separate `new` allocations also **does not guarantee** cache-line separation.

HotSpot/JDK also has an internal annotation `jdk.internal.vm.annotation.Contended` to hint to the JVM to pad a field/class. This is **not a Java SE public API**: application code typically needs `--add-exports java.base/jdk.internal.vm.annotation=ALL-UNNAMED` when compiling/running on the classpath and a HotSpot flag such as `-XX:-RestrictContended` for the annotation in user code to take effect. Flags and behavior may change across JVM/JDK versions. Do not apply it blindly in portable libraries; verify the exact JVM version, layout, and benchmark results. This annotation does not turn individual elements of an `AtomicLongArray` into separately padded fields.

### F. Restructure the Work

Sometimes a better design is to assign write ownership of a group of data to a single thread/partition, send events through a queue, and aggregate. This can avoid multiple cores alternating writes to the same memory region, trading off queue overhead, transfer latency, and backpressure handling. The decision depends on thread count, update frequency, SLAs, and required semantics.

## 8. Measure Properly: A Single Benchmark Is Not Enough

False sharing is easily confused with atomic overhead, ordinary cache misses, core migration, or scheduler behavior. A single run where `near` is slower than `far` is only a **hypothesis to be tested**.

A sound measurement process:

1. **Keep the algorithm and workload identical**, changing only the counter spacing/layout. If you simultaneously change locks, data types, or the number of atomic operations, you cannot attribute the cause solely to false sharing.
2. **Ensure at least two threads are actively updating**, ideally running on separate cores when observing cross-core coherence; check physical core count, thread scheduling, and affinity if the environment permits.
3. **Warm up the JVM/JIT**, run multiple iterations, multiple JVM forks, and measure the median/distribution rather than a single result. Reverse the case order, as earlier/later cases can be affected by thermal effects, frequency scaling, and cache state.
4. **Observe both throughput and latency**, avoiding reading just a single nanosecond figure. When comparing against production, tie it to realistic load and thread ratios.
5. **Control noise:** GC, allocations, CPU scaling, background processes, NUMA, container CPU limits, dead-code elimination optimizations, memory bandwidth, and other data dependencies.
6. **Verify layout** on the actual JDK/CPU when the hypothesis relies on offsets; combine with hardware performance counters/profiling when supported. A thread dump alone typically cannot tell which line is being contended.
7. **Evaluate trade-offs:** padding increases RAM/cache footprint; optimizing a few counters may slow down other parts or fail to improve end-to-end throughput.

### Java Microbenchmark Harness (JMH)

JMH is better suited than hand-rolled `System.nanoTime()` loops because it handles warmup, repeated measurements, forking, and result consumption. The sketch below **requires a project with JMH dependencies and annotation processor configured**; it is not a standalone Java file to run with just `javac`:

```java
import java.util.concurrent.atomic.AtomicLongArray;
import org.openjdk.jmh.annotations.*;

@State(Scope.Group)
public class CounterLayoutBenchmark {
    private final AtomicLongArray values = new AtomicLongArray(64);

    @Benchmark
    @Group("adjacent")
    @GroupThreads(1)
    public long adjacentLeft() {
        return values.incrementAndGet(0);
    }

    @Benchmark
    @Group("adjacent")
    @GroupThreads(1)
    public long adjacentRight() {
        return values.incrementAndGet(1);
    }

    @Benchmark
    @Group("separated")
    @GroupThreads(1)
    public long separatedLeft() {
        return values.incrementAndGet(0);
    }

    @Benchmark
    @Group("separated")
    @GroupThreads(1)
    public long separatedRight() {
        return values.incrementAndGet(32);
    }
}
```

With `@Group` and `@GroupThreads(1)`, each case has two methods invoked by two benchmark threads; `@State(Scope.Group)` lets threads in the group share a single group state object. You must configure thread/core counts, forks, warmup, and iterations consistently, and compare the `adjacent` group against `separated` across multiple runs. Results still depend on actual cache-line layout and atomic overhead. If using `Mode.Throughput`, understand the result units and how JMH counts operations for a group before drawing conclusions.

Object layout inspection tools such as JOL can help inspect field offsets for a given JVM. Hardware profilers (depending on CPU/OS) can provide information on coherence/cache-to-cache transfers or HITM; however, inferring false sharing from a single hardware counter is error-prone. Combining **layout + access pattern + improvement upon data separation + repeated measurements** builds convincing evidence.

## 9. Common Misconceptions and Optimization Mistakes

**“One variable per thread guarantees no contention.”** False. Not sharing a variable only eliminates contention at the logical level; two variables can still share a cache line.

**“Using `volatile`/atomics prevents false sharing.”** Those primitives guarantee operations and visibility under the Java memory model; they do not separate storage addresses on their own. Under write-heavy workloads, atomic read-modify-write operations actually make line-ownership overhead easier to observe.

**“Putting fields in different objects solves it.”** There is no guarantee that objects are separated by a cache line. You must verify actual layout and access paths.

**“Adding 64 bytes of padding is portable.”** Cache line size, object headers, alignment, field layout, and padding rules are not fixed Java SE contracts. Padding also increases memory footprint and can hurt cache locality for sequential read workloads.

**“Separating hot fields is always faster.”** Not necessarily. If data is frequently read together by a single thread and rarely written, keeping it close together leverages spatial locality. Separating lines can increase cache misses and memory consumption.

**“Cache-line contention is the same as lock contention.”** No. Threads can be `RUNNABLE`, not waiting on any Java monitor, while most CPU cycles are spent on memory/coherence stalls. Do not just look for `BLOCKED` threads and conclude there is no false sharing.

**“A single near/far benchmark run proves the cause.”** No. You must account for algorithm, layout, CPU topology, scheduling, and JIT effects. Changing multiple factors at once invalidates the conclusion.

**“LongAdder is the default optimization for every field.”** No. It targets a shared counter incremented frequently, uses extra memory, and `sum()` has different semantics from an atomic snapshot read.

## 10. Checklist When Reviewing Java Concurrency with Hot Updates

- Are **two or more threads writing** to different but nearby memory locations at high frequency? Sharing a cache line is a possibility to verify.
- Is this **true sharing, false sharing, lock contention, or cache misses/GC**? Gather evidence before changing code.
- Is the access pattern **write-heavy** or **read-mostly**? Can it be changed to local aggregation or batching?
- Do results depend on **JVM object layout, cache line size, or CPU topology**? Document environment assumptions explicitly.
- Does using stride, padding, or changing counter types preserve existing **visibility, atomicity, ordering, and semantics**?
- Have you benchmarked with warmup/multiple forks and monitored realistic workloads? Does the improvement outweigh the added memory/complexity cost?

## 11. Reasoning Exercises

**Scenario A.** Thread A increments `array[0]` and thread B increments `array[1]` one million times, each thread using its own index; on a 64-byte cache line system the elements happen to share a line. Is there a logical data race on the same element? Why is it still slow?

**Answer:** No two threads write to the same element, so there is no logical contention on the same counter; however, both need write ownership of the line containing both elements, causing ownership to bounce between cores. This is false sharing if it causes performance degradation.

**Scenario B.** Two threads call `AtomicLong.incrementAndGet()` on a single object. Should this be called false sharing?

**Answer:** That is **true sharing** because both are actually updating the same variable. You may consider `LongAdder` if only addition is needed with appropriate `sum()` semantics.

**Scenario C.** A group of fields that are only read after initialization share a line. Do you need separate padding for each field?

**Answer:** Usually no; cores can share read copies without write ping-pong traffic. Padding may actually worsen locality.

**Scenario D.** Separating two counters makes a microbenchmark 30% faster, but overall system throughput does not change. Should you apply it immediately?

**Answer:** Not enough justification. The counters may not be on the critical path, or the main bottleneck is elsewhere; changing layout also has a memory cost. Base the decision on profiling and a representative workload.

**Technical takeaway:** optimizing false sharing starts with recognizing that **cache coherence operates at the line level**, then proving that concurrent writes to independent locations are causing significant line contention. Only separate/pad data after preserving correctness and measuring a real benefit in an appropriate environment.
