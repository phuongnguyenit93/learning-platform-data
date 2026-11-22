# LongAdder vs. AtomicLong Under Contention in Java

## 1. The Problem: Multiple Threads Updating the Same Counter

Suppose multiple threads record the number of processed requests, completed tasks, or emitted events. The **counter++** operation on a regular **long** variable is not an atomic read–modify–write operation: threads can read the same stale value, increment it, and overwrite each other's results. Using **volatile long** helps with value visibility and certain memory-ordering guarantees, but it does **not** turn **counter++** into an atomic increment.

In the **java.util.concurrent.atomic** package, two familiar choices are:

- **AtomicLong**: a single **long** value updated via atomic operations such as **incrementAndGet()**, **getAndIncrement()**, **getAndAdd(delta)**, or **compareAndSet(expected, update)**.
- **LongAdder**: an accumulator optimized for high-concurrency updates. It can distribute additions across multiple internal cells and sum them up when **sum()** is called.

**Contention** occurs when multiple threads simultaneously update a shared resource. With a single memory address being updated continuously, CPU cores must coordinate cache line ownership and execute atomic read–modify–write operations. As a result, when the number of threads and write frequency increase, a single counter can become a bottleneck.

However, performance optimization only makes sense if it preserves the **semantics** the application requires. These two classes have a crucial trade-off: **AtomicLong is suitable when you need exact values and atomic decision operations; LongAdder is suitable when you primarily perform heavy additions and occasionally read statistics.**

## 2. AtomicLong: A Single Atomic Value

**AtomicLong** (available since Java 5) holds a single **long** value. Common methods include:

| Method | Meaning |
|---|---|
| **get()** | Reads the current value with volatile read semantics. |
| **set(value)** | Assigns the value with volatile write semantics. |
| **incrementAndGet()** | Atomically adds 1 and returns the value **after** incrementing. |
| **getAndIncrement()** | Atomically adds 1 and returns the value **before** incrementing. |
| **addAndGet(delta)** | Atomically adds delta and returns the new result. |
| **getAndAdd(delta)** | Atomically adds delta and returns the previous result. |
| **compareAndSet(expected, update)** | Updates only if the current value equals expected; returns success/failure. |
| **getAndSet(newValue)** | Atomically swaps the value and returns the previous value. |
| **updateAndGet(function)** | Atomically updates using a function; the function may be re-executed under contention. |

Each atomic update operation can be viewed as occurring at a well-defined point for that value: threads observe a valid order of increments and swaps on the same **AtomicLong**. Therefore, **getAndIncrement()** is well suited for issuing distinct sequence numbers to threads.

For example, when **sequence** starts at 100, two consecutive calls to **getAndIncrement()** return 100 and 101; no other thread can obtain a duplicate number from that same update sequence (unless the **long** overflows or the code explicitly resets the value). A **LongAdder** has no atomic API that returns the sequence number of *the specific increment that just occurred*.

### 2.1. When AtomicLong Updates Experience Contention

~~~text
                 AtomicLong (single logical location)
Thread A  ---- increment ----\
Thread B  ---- increment -----+--> same memory location written frequently
Thread C  ---- increment ----/
~~~

The CPU must synchronize writes to the same location. On multi-core systems, cache line ownership transfers and contention on atomic operations can reduce throughput when the number of writers is large. Whether Java/the JVM uses a read–modify–write instruction or a CAS retry loop on a given code path depends on the implementation and platform; **you should not claim that every increment runs a hand-written CAS loop**.

In many workloads, this cost is completely acceptable: the thread count is small, update frequency is low, or each update also performs much heavier I/O work. **AtomicLong** also has a small footprint and a simple **get()** operation.

### 2.2. AtomicLong Does Not Turn Multiple Steps into a Single Transaction

~~~java
// Incorrect when you need to guarantee a slot is only granted if count < limit:
if (active.get() < limit) {
    active.incrementAndGet();
}
~~~

Between **get()** and **incrementAndGet()**, another thread can exceed the limit. You need a decision and update bound to the same synchronization operation, such as a **compareAndSet** loop:

~~~java
static boolean tryAcquire(java.util.concurrent.atomic.AtomicLong active,
                          long limit) {
    while (true) {
        long current = active.get();
        if (current >= limit) return false;
        if (active.compareAndSet(current, current + 1)) return true;
    }
}
~~~

This is an **illustrative method**, not a standalone Java file. It only allows incrementing when the observed value is still below limit, provided **all** code paths modifying the active variable follow the same policy. For this example, assume limit does not exceed the valid **long** integer range and **current + 1** does not overflow. In applications requiring multi-resource synchronization or complex permit management, consider a dedicated synchronization abstraction.

**LongAdder is not suitable for this case**: reading **sum()** and then incrementing does not form an atomic decision.

## 3. LongAdder: Spreading Write Load Across Internal Cells

**LongAdder** (Java 8+) is a **long** accumulator class supporting:

- **increment()**: equivalent to **add(1)**.
- **decrement()**: equivalent to **add(-1)**.
- **add(delta)**: adds an arbitrary amount.
- **sum()**: reads the total by summing the internal component variables.
- **longValue()**: equivalent to **sum()**.
- **reset()** and **sumThenReset()**: reset operations intended for moments when there are no concurrent updates.

Unlike AtomicLong, **increment()** and **add(delta)** return **void**. This reflects the design: LongAdder does not attempt to provide "the unique value immediately after the increment" to each writer. When threads contend, the adder can expand its set of internal variables to spread out writes.

~~~text
AtomicLong:
  Thread A --\
  Thread B ---+----> [ single long ]
  Thread C --/

LongAdder (conceptual diagram):
  Thread A ------> [ base / cell 0 ] --\
  Thread B ------> [ cell 1        ] ---+--> sum(): add totals together
  Thread C ------> [ cell 2        ] --/
~~~

This is an **explanatory model**, not a guarantee that each thread is permanently pinned to a specific cell. The JDK uses an internal load-striping algorithm and can adjust the number of cells based on contention levels. The actual number of cells, cell selection, layout to avoid false sharing, and scaling limits are implementation details.

### 3.1. Why Does LongAdder Often Improve Throughput with Many Writers?

When a single write hotspot is replaced by multiple write locations, cores compete less over the same cache line. Updates remain thread-safe, but can happen on different cells. This reduction in contention allows **increment()/add()** throughput to often be higher than **AtomicLong** under heavy contention.

In return:

1. **More memory**: it may hold multiple cells, metadata, and padding to reduce cache contention.
2. **More expensive sum reads**: **sum()** must read and sum multiple values instead of reading a single variable.
3. **No atomic snapshot**: while **sum()** is iterating over the cells, other threads can still add to one or more of those cells.
4. **No compare-and-set on the total**: you cannot use sum as a synchronization point for issuing IDs, enforcing exact thresholds, or driving a state machine.

The Javadoc recommends LongAdder for collecting **statistics** when multiple threads update a common sum; under low contention, the performance characteristics of the two classes are often similar, while LongAdder uses more memory.

### 3.2. What Does a "Non-Atomic" sum() Mean?

Suppose the total is held across two cells:

~~~text
Before reading: cell A = 5, cell B = 7
Reader thread reads A = 5
Writer thread adds 1 to B
Reader thread reads B = 8
Reader returns 13
~~~

This is just **one illustrative interleaving**: the reader may observe values at different points in time. There is no contract that a single call to **sum()** is a simultaneous snapshot of all cells at the same instant, or that it includes all updates occurring while the sum is being computed.

Distinguish three things:

- Every successful **add(1)** contributes to the adder; this is not a plain data increment that suffers races and loses updates.
- If you have **stopped all writers and waited for them to finish**, **sum()** returns the exact sum of the completed updates (assuming no **long** overflow, no reset calls, and no other threads updating).
- If writers are still running, **sum()** is an observation for statistics; it does **not** have the linearizable snapshot property that a read from **AtomicLong.get()** has for that single atomic variable.

That makes LongAdder suitable for displaying the number of processed requests on a dashboard or recording periodic telemetry, where a snapshot can lag slightly. It is **not suitable** for verifying a condition like "only one permit left" or generating a unique sequence number.

## 4. Comparison Table for Choosing the Right Tool

| Criterion | AtomicLong | LongAdder |
|---|---|---|
| Logical structure | A single atomic long value. | Multiple component variables summed into a total. |
| Writes | Multiple writers contend on a single write point. | Can stripe write load across multiple cells. |
| Read API | **get()** reads a single atomic value. | **sum()** sums multiple variables; no atomic snapshot. |
| Return value after increment | Yes, via **incrementAndGet()** or **getAndIncrement()**. | No, **increment()** returns void. |
| Compare-and-set | Yes, **compareAndSet()**. | No CAS for the overall total. |
| Write throughput under high contention | Can degrade due to a shared hotspot. | Often better with many writers updating continuously. |
| Low contention | Usually fast enough with compact overhead. | Often similar; not faster by default. |
| Memory footprint | Usually lower. | Can grow noticeably with the number of cells. |
| Read cost | A simple get operation. | Aggregates cells; more expensive when there are many cells. |
| Reset / get-and-reset | **getAndSet(0)** is an atomic swap on a single variable. | **sumThenReset()** is not an atomic swap of the entire total if writers are active concurrently. |
| Best suited for | Sequences, state, quotas/limits, gauges needing consistent reads. | Statistical counters, total event counts, access frequencies per key. |

**There is no universal conclusion that "LongAdder is always faster."** Performance depends on cores, writer count, **sum()** read frequency, update patterns, cache topology, JDK version, execution mode, and the rest of the work done per request.

## 5. Java 17+ Example: Multiple Threads Incrementing Both Counters

The following example is meant to demonstrate **correct counting after workers finish**, not to measure speed. We start multiple threads close together using a latch so each thread increments both counters the same number of times.

Create the file **CounterComparison.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public final class CounterComparison {
    public static void main(String[] args) throws InterruptedException {
        final int threads = 4;
        final int updatesPerThread = 10_000;

        AtomicLong atomic = new AtomicLong();
        LongAdder adder = new LongAdder();

        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);

        for (int i = 0; i < threads; i++) {
            Thread worker = new Thread(() -> {
                ready.countDown();
                try {
                    start.await();
                    for (int n = 0; n < updatesPerThread; n++) {
                        atomic.incrementAndGet();
                        adder.increment();
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    done.countDown();
                }
            });
            worker.start();
        }

        ready.await();
        start.countDown();
        done.await();

        long expected = (long) threads * updatesPerThread;
        System.out.println("expected=" + expected);
        System.out.println("atomic=" + atomic.get());
        System.out.println("adder=" + adder.sum());

        AtomicLong sequence = new AtomicLong(100);
        System.out.println("tickets=" + sequence.getAndIncrement()
                           + "," + sequence.getAndIncrement());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 CounterComparison.java
java CounterComparison
~~~

Output of a normal run without interrupts:

~~~text
expected=40000
atomic=40000
adder=40000
tickets=100,101
~~~

**Explanation:**

1. **ready** ensures all four threads have reached the starting point; **start** lets all of them begin the loop around the same time.
2. Each thread calls **atomic.incrementAndGet()** and **adder.increment()** exactly 10,000 times. There are 40,000 additions on each counter.
3. **done.await()** ensures all threads have finished. When main reads **adder.sum()**, there are no concurrent updates left, so the total is exact. Waiting for completion also establishes the necessary synchronization relationship for reading the final result.
4. **tickets=100,101** shows that **getAndIncrement()** both increments and returns the pre-increment value, something **LongAdder** cannot provide in an equivalent single call.

Do not draw speed conclusions from this program: both updates happen in the **same loop**; measuring a single combined duration cannot isolate the overhead of each counter. Moreover, the small iteration count and thread creation cost can drown out the actual signal being measured.

## 6. Application Example: Event Frequency by Key

An official JDK pattern is combining **ConcurrentHashMap<String, LongAdder>** with **computeIfAbsent()** to count frequencies per event type. Each key owns its own adder, and multiple threads can call the recording method concurrently.

Create the file **EventFrequency.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public final class EventFrequency {
    private static final ConcurrentHashMap<String, LongAdder> COUNTS =
            new ConcurrentHashMap<>();

    private static void record(String event) {
        COUNTS.computeIfAbsent(event, ignored -> new LongAdder())
              .increment();
    }

    public static void main(String[] args) {
        record("ok");
        record("error");
        record("ok");

        System.out.println("ok=" + COUNTS.get("ok").sum());
        System.out.println("error=" + COUNTS.get("error").sum());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 EventFrequency.java
java EventFrequency
~~~

Output:

~~~text
ok=2
error=1
~~~

**computeIfAbsent()** initializes the counter for a non-existent key using **ConcurrentHashMap**'s thread-safe mechanism; subsequent calls to **record("ok")** safely add to the same LongAdder. **The example above runs sequentially** for deterministic output; the same **record** method works from multiple threads. To obtain an exact total at the end of a multithreaded test, you must wait for all writers to finish before calling **sum()**.

Implementation notes:

- Do **not** use **LongAdder** as a key based on counter content; this class does not define value-based equality like an immutable key.
- When keys come from potentially unbounded data (such as unbounded IDs), the map can grow in memory indefinitely; you need to define label bounds, lifecycle, and key eviction.
- If counter deletion/replacement must be synchronized with writers, an explicit lifecycle policy is required. Calling **remove(key)** while another thread still holds a reference to the old LongAdder can cause increments to no longer appear in the map's new counter.
- For **statistical metrics**, reading **sum()** during updates is usually sufficient. For financial logic, authorization, or exact limits, a mechanism with stronger semantics is required.

## 7. Testing Contention Properly

Small self-written benchmarks like "loop 1 million times and take nanoTime" easily lead to wrong conclusions. The JVM has JIT compilation, tiered compilation, warm-up, dead-code elimination, and plenty of noise from the scheduler/GC/turbo boost/caches. To compare performance, use **JMH (Java Microbenchmark Harness)**, which provides warm-up, multiple iterations, and places updates in a realistic contention scenario. JMH is a separate benchmarking tool, not a required **java.util.concurrent** API.

### 7.1. Variables to Control

1. **Threads**: measure 1, 2, 4, 8, ... writers matching real core counts; avoid extrapolating from a single configuration.
2. **Sharing model**: all threads update the **same** counter to measure contention; if each thread uses its own counter, the problem is different.
3. **Read frequency**: measure both rare **sum()** calls (e.g., at the end of each interval) and frequent **sum()** reads alongside writes. LongAdder may trade update speed for aggregation cost.
4. **Throughput and latency**: look at updates/second, time per operation if relevant, and distributions across trials; also monitor CPU and GC levels.
5. **Memory**: examine the footprint when many LongAdders allocate additional cells, especially with many keys or many instances.
6. **JVM/hardware**: record the JDK, core count, CPU, heap configuration, container/VM environment, and background loads.
7. **Measurement definition**: do not include thread creation, executor initialization, or counter construction in update measurements if the goal is to compare **increment** cost.

### 7.2. What Usually Happens?

| Environment | Reasonable expectation (not fixed numbers) |
|---|---|
| Single thread or rare writes | AtomicLong can match or beat LongAdder due to lower structural overhead. |
| Many writers updating the same counter very frequently | LongAdder often increases throughput by reducing write hotspots. |
| Rare updates but continuous sum reads | LongAdder's advantage may disappear due to **sum()** cost. |
| Hundreds of thousands of keys, few updates per key | LongAdder may use more memory than AtomicLong. |
| Need to issue a unique sequence number after each update | Choose AtomicLong for correctness requirements, not because of benchmarks. |

Do not cite multipliers like "2x/10x faster" without actual benchmark results on the target workload.

## 8. reset, sumThenReset, and Metric Boundaries

**AtomicLong.getAndSet(0)** is an atomic swap on the same value. If threads only increment the counter using atomic operations, each increment falls either before or after the swap point in a valid order. Thus, reading an interval's count and resetting it has clear semantics for a **single** AtomicLong variable.

Conversely, **LongAdder.reset()** and **sumThenReset()** operate across the component variables. The Javadoc emphasizes that these operations are **inherently racy** when threads are actively adding; **sumThenReset()** is not guaranteed to return the final total at an exact time boundary while concurrent updates occur. Only use them when writers have been brought to a quiescent point (no longer updating) or when drift within implementation characteristics is acceptable.

Example pattern for measuring requests per interval:

~~~java
// Illustrates usage when updates have been paused:
// LongAdder requests = ...;
// stopAndJoinAllWriters();
// long count = requests.sumThenReset();
// startNextEpoch();
~~~

The snippet above is **only pseudocode**, not a standalone Java program: **stopAndJoinAllWriters()** and **startNextEpoch()** represent the application's lifecycle mechanism. If you simply call **sumThenReset()** on a timer while dozens of workers are still calling **increment()**, you must not treat each interval's data as an exact atomic checkpoint.

If a dashboard only needs cumulative statistics, it is often simpler **not to reset** and instead take the difference between two samples:

~~~text
t0: total = 1_000
t1: total = 1_120
estimated events in interval = 120
~~~

Taking the difference of **sum()** still relies on non-atomic snapshots while writers are running; it suits telemetry that tolerates timing skew, not ledgers requiring absolute precision. If decrements or counter replacements occur, the difference can even be negative. For strict per-epoch measurement, you need explicit synchronization barriers/epoch transitions or a counter with appropriate semantics.

## 9. Which Class Fits Which Real-World Case?

### 9.1. Observability Counters

For example, counting successful requests, errors, consumed events, or processed bytes from multiple writers. You only need totals for periodic reporting/monitoring.

**Prefer LongAdder** if many writers contend; concurrent total reads can serve as near-real-time statistics. At low update frequencies, AtomicLong remains a simple and sensible choice.

### 9.2. Sequence or Ticket Generators

For example, generating monotonically increasing IDs within a single JVM, logging sequences, or internal ticket numbers. Each call needs a distinct value with a clear update order.

**Use AtomicLong.getAndIncrement()** or **incrementAndGet()**. Note the scope: an in-memory sequence in one JVM does not automatically produce unique IDs across multiple JVMs, does not persist across restarts, and can overflow **long** after a very long time.

### 9.3. Limiting Concurrent Running Tasks

For example, allowing no more than 20 concurrent tasks. This problem requires synchronized checking and granting, not just tracking call counts.

**Do not choose LongAdder.sum() followed by increment() to enforce a threshold.** You can use CAS with AtomicLong or a synchronization construct such as **Semaphore**, depending on the model. If using AtomicLong, you must also design the permit release path on completion/failure, as well as exception handling, so permits are not leaked.

### 9.4. Current Active Requests or a Gauge

A gauge metric that calls **increment()** on start and **decrement()** on finish. LongAdder works if you only display the active request count on a dashboard and accept that **sum()** while running is not a strict snapshot. If you need "never negative," "never exceed capacity," or transactional decisions based on the observed value, you need atomic check-and-update or a lock/permit.

### 9.5. Many Infrequently Accessed Counters

If each user/key has its own counter but most keys receive few updates, LongAdder may bring no benefit and introduce object/memory overhead, especially when contention causes cell expansion. Try **AtomicLong** first, then benchmark on the real workload when optimization is needed.

## 10. Common Misconceptions

1. **"LongAdder is faster in every situation."** False. It mainly helps when many writers truly contend on the same sum; read-heavy or low-contention workloads may see no benefit.
2. **"LongAdder.sum() is equivalent to AtomicLong.get()."** False in terms of semantics. **sum()** does not return an atomic snapshot when concurrent updates are happening.
3. **"LongAdder loses increments."** Not true. Completed **add()** calls are accumulated into the state; the caveat is **when the total is observed**, especially during concurrent updates or resets.
4. **"A thread is permanently pinned to one cell."** There is no such guarantee in the API; striping is an implementation detail that can change.
5. **"LongAdder can issue IDs by incrementing and then calling sum."** Not guaranteed: between the two operations, other writers can update it, and **sum()** does not provide an atomic snapshot.
6. **"volatile long++ is enough."** False: volatile does not turn a read–modify–write sequence into an atomic operation.
7. **"AtomicLong never slows down with many threads because it is lock-free."** Atomic primitives still incur cache coherence and contention costs. Lock-free does not mean linear throughput.
8. **"reset or sumThenReset can be called freely while writers are running."** False if exact per-period counts are required.
9. **"Running a for-loop and measuring nanoTime is enough to conclude."** False: JIT, JVM warm-up, thread count, benchmark harness, and read frequency heavily affect the numbers.
10. **"AtomicLong makes every check-then-update safe."** False: only individual atomic operations and algorithms properly built around them have the desired guarantees.

## 11. Decision Checklist

- **Do you need a return value for each increment or CAS against a threshold?** If yes, choose **AtomicLong**.
- **Do you need an exact point-in-time total while writers are still running?** **AtomicLong.get()** has single-atomic-value semantics; **LongAdder.sum()** does not have an equivalent snapshot.
- **Are many writers continuously updating the same counter?** If yes, consider **LongAdder** and measure with the target workload.
- **How frequently is the total read?** If read-heavy, factor in the cost of **sum()**.
- **Are there many per-key counters?** Measure the footprint and bound the number of keys.
- **Do you reset at intervals?** Check the accuracy requirements at reset time and the policy for pausing writers.
- **Have you tested with the real load pattern and core count?** Do not choose based on unsubstantiated benchmarks.

**Rule of thumb:** **AtomicLong** prioritizes atomic operations on **a single value**; **LongAdder** trades immediate read consistency of the total and extra resources to optimize **accumulation throughput under high contention**. Choose based on semantics first, then measure performance.

## 12. Official Documentation

- [LongAdder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [AtomicLong — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html)
- [ConcurrentHashMap — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [CountDownLatch — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
