# Analyzing Pipeline Allocations, GC, and Processing Bottlenecks

In the **Performance and Memory** chapter of the **Java Stream API**, a pipeline using `filter`, `map`, `flatMap`, `reduce`, `collect`, or `parallelStream` might produce correct output yet run slowly, allocate excessive temporary objects, or put pressure on the *garbage collector* (GC). When that happens, the answer is neither reflexively abandoning Streams for loops nor flipping on `parallel()` hoping every problem disappears.

You must answer three **distinct** questions:

1. **Allocation:** which objects are created per execution, how many bytes are allocated, and at which stage?
2. **GC and live heap:** how much data remains referenced, does GC run frequently or cause significant pauses, and does peak memory exceed limits?
3. **Processing bottleneck:** is request completion time actually dominated by CPU, GC, I/O wait, synchronization locks, collected data volume, or parallel splitting limits?

These three questions are related yet **not identical**. A program can allocate many short-lived objects while GC handles them efficiently; or it can have low allocation rates while retaining a huge Map that grows heap and forces heavy live-data tracing. Likewise, frequent GC lines in logs might not be the primary reason the application is slow.

This lesson explains how to formulate **testable hypotheses**, choose appropriate measurements (JFR, GC logs, JMH, and end-to-end runs), spot common Stream API costs, apply small controlled optimizations, and re-verify both correctness and performance.

> **Illustrative environment:** Java 17+. Core Stream APIs exist since Java 8; `Stream.toList()` since Java 16. Some diagnostic tools and GC logging flags in examples require modern JDKs. Measurement commands are for learner practice; no real benchmark numbers are assumed in this lesson.

## 1. First, define “slow” using metrics

You cannot optimize soundly from a vague observation like “this pipeline seems slow”. Define metrics tied to business goals:

| Metric | Question answered | Example unit |
| --- | --- | --- |
| **Latency** | How long does one execution take? | ms/request or ms/batch |
| **Throughput** | How much data is processed per second? | requests/s, events/s |
| **CPU usage/time** | Is the machine actually doing heavy computation? | %, CPU-time |
| **Allocation rate** | How many bytes per second does the JVM allocate? | MB/s |
| **Allocation per operation** | Roughly how many bytes does each execution allocate? | B/op |
| **Live heap** | How much data remains retained after collection? | MB |
| **Peak memory** | How high does memory peak during a batch? | MB, GB |
| **GC frequency/pause** | How often does GC run and how does it affect latency? | times/s, ms/pause |
| **I/O wait / blocking** | How long do threads wait on disk, network, DB, or locks? | ms or time share |

Record these metrics alongside **data size, filter pass rate, distinct key count, group sizes, JDK version, heap configuration, and concurrency level**. Without that context, comparing measurements across days or environments is very difficult.

### Example of an actionable performance report

~~~text
Workload: 100,000 events/batch, 2,000 distinct customers
JDK: version and GC recorded from runtime environment
Mode: sequential, fixed identical input
Metric A: latency p50/p95 and throughput
Metric B: allocation B/op and MB/s
Metric C: GC pauses, heap used after collection
Metric D: CPU hotspots and I/O wait time
Hypothesis: pipeline allocates intermediate objects in map/collect
~~~

**Never jump from a symptom straight to a root cause.** Measure to confirm whether the true bottleneck sits in the suspected stage.

## 2. Distinguishing allocation, live heap, and retention

Three concepts often conflated:

### 2.1. Allocation: object creation rate

In a pipeline:

~~~java
List<String> labels = events.stream()
        .map(event -> event.customerId() + ":" + event.latencyMs())
        .toList();
~~~

String concatenation can allocate new result strings, and `toList()` must hold the output elements. Yet **you cannot count exact allocated objects merely by reading source code**: the compiler, JIT, escape analysis, allocation optimizations, and JDK implementation details all affect runtime behavior.

So instead of claiming “every `map` definitely allocates X objects”, measure `B/op` or allocation samples on the actual workload.

### 2.2. Live heap: data that cannot be collected yet

Suppose:

~~~java
List<String> labels = events.stream()
        .map(Event::customerId)
        .toList();
~~~

If `labels` stays referenced by a cache or field, the list and its referenced elements remain live data. If you only compute a sum and return `long`, many temporary objects become unreachable right after the pipeline finishes.

**High allocation does not automatically mean high live heap.** Conversely, a cache holding millions of entries can occupy massive heap even when each incoming request allocates almost nothing new.

### 2.3. Retention: holding objects longer than necessary

A notable example:

~~~java
Map<String, List<Event>> byCustomer = events.stream()
        .collect(Collectors.groupingBy(Event::customerId));
~~~

The result retains **lists of every event per customer**. If `byCustomer` lives long, most `Event` objects stay reachable; GC cannot reclaim them merely because the pipeline ended.

If business logic only needs counts:

~~~java
Map<String, Long> counts = events.stream()
        .collect(Collectors.groupingBy(
                Event::customerId,
                Collectors.counting()
        ));
~~~

Each customer now keeps one count in the output rather than a `List<Event>` holding all records. Accumulated memory scales mainly with **distinct customers**, not total events, though input objects might still be referenced elsewhere.

**Lesson:** Aggregating into the right result shape can cut *retained heap* far more than micro-optimizing a few temporary objects.

## 3. Common memory costs in Stream pipelines

| Pipeline pattern | Potential cost | Question to measure |
| --- | --- | --- |
| `map` returning new objects | Result objects, strings, boxing | Which objects are actually allocated? |
| `map(...).toList()` | All output elements retained | Is materializing every element truly needed? |
| `filter(...).toList()` | Result list proportional to kept elements | Can `count`/`sum` suffice if only metrics are needed? |
| `flatMap` | Child streams, intermediate objects, flattening | Is fan-out large? Are child sources I/O-backed? |
| `mapMulti` | May use internal buffers depending on implementation | Does it outperform `flatMap` on the target JDK? |
| `boxed()` / `Stream<Integer>` | Boxing/unboxing, potential wrapper allocations | Can a primitive stream stay unboxed until the terminal? |
| `sorted()` | Must sort, often buffers intermediate elements | Is full sorting needed or just top-K? |
| `distinct()` | Tracks previously seen elements | Is distinct value count large? |
| `groupingBy(..., toList())` | Map plus lists holding all elements per group | Do you need counts/sums/max or truly full lists? |
| `toMap` | Map per distinct key, collisions/merges | How many keys exist, and how many key collisions occur? |
| `parallelStream` | Subtasks, per-branch accumulators, merge buffers | Does it raise throughput at the expense of heap/GC? |

**Note:** This table lists **cost sources to inspect**, not fixed byte or object guarantees. Laziness, JIT optimization, and terminal operations can alter what actually executes.

## 4. Spotting boxing before touching GC tuning

For purely numeric problems, using `Stream<Long>` and wrapper-producing transforms can cost more than primitive streams.

### Boxed version

~~~java
long total = events.stream()
        .filter(Event::error)
        .map(Event::latencyMs)
        .reduce(0L, Long::sum);
~~~

`map(Event::latencyMs)` on `Stream<Event>` yields `Stream<Long>` at the API type level; primitive `long` is boxed into `Long` to pass through the object Stream. The JIT **may** eliminate some boxing, yet you should not assume it always removes all of it.

### Primitive version

~~~java
long total = events.stream()
        .filter(Event::error)
        .mapToLong(Event::latencyMs)
        .sum();
~~~

`mapToLong` produces a `LongStream` and `sum` computes a `long` result. This is usually a strong candidate to reduce boxing in numeric aggregation pipelines.

**Both snippets share identical meaning** on valid `Event` inputs when sums stay within `long` and mappers have no side effects. `long` addition can wrap on overflow per Java rules; if business logic forbids overflow, add bounds checks or use a wider numeric type.

### Staying primitive across the pipeline

~~~java
long total = events.stream()
        .filter(Event::error)
        .mapToLong(Event::latencyMs)
        .filter(value -> value > 0L)
        .sum();
~~~

Avoid switching through `boxed()` just to continue numeric arithmetic, unless a downstream API genuinely requires objects.

Example:

~~~java
// Boxing may be unnecessary when only summing:
long total = events.stream()
        .mapToLong(Event::latencyMs)
        .boxed()
        .reduce(0L, Long::sum);
~~~

A fair benchmark must compare **the exact same computation and input**; never drop a filter from the primitive branch while keeping it in the boxed branch.

## 5. Complete program: verify correctness before measuring

The example below runs on **Java 17+**, builds deterministic data, and compares three aggregations:

- Sum of error latencies using `Stream<Long>` with `reduce`.
- Sum of error latencies using `LongStream.sum()`.
- Grouped sum of error latencies per customer using `groupingBy(..., summingLong(...))`.

Save as `PipelineDiagnosticsDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class PipelineDiagnosticsDemo {

    record Event(
            int customerId,
            long latencyMs,
            boolean error
    ) {}

    // Deterministic input created outside the pipeline under test.
    static List<Event> createData(int count) {
        return IntStream.range(0, count)
                .mapToObj(i -> new Event(
                        i % 2_000,
                        1L + i % 97,
                        i % 9 == 0
                ))
                .toList();
    }

    static long boxedTotal(List<Event> events) {
        return events.stream()
                .filter(Event::error)
                .map(Event::latencyMs)
                .reduce(0L, Long::sum);
    }

    static long primitiveTotal(List<Event> events) {
        return events.stream()
                .filter(Event::error)
                .mapToLong(Event::latencyMs)
                .sum();
    }

    static Map<Integer, Long> groupedTotal(
            List<Event> events) {

        return events.stream()
                .collect(Collectors.groupingBy(
                        Event::customerId,
                        Collectors.summingLong(event ->
                                event.error()
                                        ? event.latencyMs()
                                        : 0L)
                ));
    }

    public static void main(String[] args) {
        List<Event> events = createData(100_000);

        long boxed = boxedTotal(events);
        long primitive = primitiveTotal(events);

        Map<Integer, Long> groups = groupedTotal(events);
        long groupedSum = groups.values().stream()
                .mapToLong(Long::longValue)
                .sum();

        if (boxed != primitive || boxed != groupedSum) {
            throw new AssertionError(
                    "Different aggregate results");
        }

        System.out.println(
                "events=" + events.size()
                + ", customers=" + groups.size()
                + ", totalErrorLatency=" + primitive
        );
    }
}
~~~

Run:

~~~bash
javac --release 17 PipelineDiagnosticsDemo.java
java PipelineDiagnosticsDemo
~~~

This dataset has 100,000 records and up to 2,000 distinct customer IDs. `groupedTotal` has a **broader business task** than the two sum-only pipelines: it maintains a Map per customer. Therefore, **do not** compare `groupedTotal`'s runtime against `primitiveTotal` as a “which API is faster” test when their outputs differ. The demo verifies shared correctness and sets up context for retained-heap analysis.

The program **does not** use `System.nanoTime()` to declare one style faster. For reliable timing, we will use JMH next.

## 6. Separating CPU bottlenecks from GC bottlenecks

A slow pipeline can be stalled in very different places:

### CPU bottleneck

Signs to look for:

- CPU is busy running mappers, comparators, hashing, or string manipulation.
- JFR or profilers show high CPU samples in data-processing methods.
- Latency scales with element count or algorithmic complexity.
- GC pauses represent a tiny slice of total time despite allocations.

For example, in a pipeline like:

~~~java
List<String> normalized = names.stream()
        .map(name -> expensiveNormalize(name))
        .toList();
~~~

If `expensiveNormalize` is truly costly, swapping `toList` for another collector will not remove the bottleneck. Measure where CPU time goes.

### GC bottleneck or heap pressure

Signs to look for:

- High allocation rate paired with frequent GC cycles.
- GC pauses or concurrent GC work consume a large fraction of time and CPU.
- Post-GC heap climbs steadily because data stays retained.
- Allocation failures, GC overhead warnings, or `OutOfMemoryError` occur under real load.
- *Tail latency* (such as p95/p99) correlates with GC activity.

However, **many lines in a GC log do not prove GC is the main cause**. An efficient collector can reclaim lots of short-lived objects with minimal pauses. Correlate GC timelines against latency, CPU, and heap before concluding.

### I/O or lock wait bottleneck

Signs to look for:

- CPU looks low while requests remain slow.
- Threads block on file reads, network sockets, JDBC, locks, or queues.
- JFR shows substantial `FileRead`, `SocketRead`, `ThreadPark`, or lock contention time.
- Adding `parallelStream` fails to raise throughput and may worsen contention.

In such cases, changing `map` to `mapToLong` may shave negligible overhead without touching the main wait time.

## 7. Lazy pipelines: do not measure unexecuted work

Streams primarily use **lazy evaluation**. Timing only pipeline construction like this is misleading:

~~~java
var pipeline = events.stream()
        .filter(Event::error)
        .mapToLong(Event::latencyMs);

// No terminal operation yet: the pipeline may not have traversed the source.
~~~

Trustworthy measurements must include a **terminal operation** that actually consumes data:

~~~java
long result = events.stream()
        .filter(Event::error)
        .mapToLong(Event::latencyMs)
        .sum();
~~~

Yet do not assume **every lambda always runs** just because a terminal operation is present. The Stream API permits optimizations based on source and pipeline characteristics.

Example:

~~~java
long count = List.of("a", "b", "c").stream()
        .peek(System.out::println)
        .count();
~~~

On a `SIZED` source with known size, implementations may compute `count()` **without running operations that cannot affect element count**, so `peek`'s action may not execute as expected.

**Never use `peek` invocation count as a guaranteed work metric**, and never put mandatory business logic in `peek`. In benchmarks, pick terminal operations whose output the compiler/harness observes and never time an unexecuted pipeline.

## 8. Observing GC with unified logging

On modern JDKs, enable **unified logging** to observe GC behavior:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags \
     -jar application.jar
~~~

The snippet uses `\` line continuation for POSIX shells. In Windows/PowerShell, put all options on one line or use PowerShell's line continuation rules:

~~~text
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar application.jar
~~~

`gc.log` reports collector choice, GC durations, pre/post-collection heap, and events per JDK configuration. Analyze:

1. **GC time** relative to application uptime; longest pauses and pause distribution.
2. **GC frequency** relative to request/batch rate and allocation rate.
3. **Heap before/after GC**: is live data growing, or are only temporary objects being collected?
4. **GC event types**: young collections, concurrent phases, full collections per the active collector.
5. **Latency correlation**: do slow requests line up with major GC activity?
6. **Machine context**: heap size, CPU, load, JDK, flags, and container memory limits.

**Do not treat young GC count alone as a negative KPI.** Higher frequency may simply mean the collector is efficiently reclaiming short-lived objects as designed. Judge by actual impact on latency, throughput, and resources.

### GC overhead and retention are not the same

If post-GC heap always drops back to roughly the same baseline, the workload is creating short-lived objects. If post-GC heap climbs steadily across batches/caches, investigate **retained objects** and the references keeping them alive. A logical leak might be a static `List`, an unbounded Map cache, a callback holding old data, or unbounded keys in `groupingBy`.

GC cannot “free” objects still validly referenced by the application.

## 9. Using Java Flight Recorder (JFR)

**Java Flight Recorder** collects runtime events while an application runs. On JDKs supporting JFR, record a profile:

~~~bash
java -XX:StartFlightRecording=filename=pipeline.jfr,settings=profile,dumponexit=true \
     -jar application.jar
~~~

In a single-line environment:

~~~text
java -XX:StartFlightRecording=filename=pipeline.jfr,settings=profile,dumponexit=true -jar application.jar
~~~

After the application exits, inspect a summary via CLI:

~~~bash
jfr summary pipeline.jfr
~~~

Print specific event types if present in the recording:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.ObjectAllocationSample,jdk.GarbageCollection pipeline.jfr
~~~

Not every recording enables every event; **allocation events can be sampled** rather than an exact tally of every object. The `profile` configuration has different overhead from `default`, and JDK versions vary in event names/configs. Check your recording configuration before drawing conclusions.

Key views to inspect:

| JFR category | What to look for |
| --- | --- |
| **Execution samples** | Which methods account for most CPU samples? |
| **Allocation samples** | Which object types and call stacks dominate allocation samples? |
| **GC events** | Do GC activity and pauses match latency spikes? |
| **File/Socket I/O** | File reads, network reads, and source wait latency |
| **Thread parking/locks** | Thread waits, lock contention, effective parallelism |
| **Heap/threads** | Resource usage trends over the run |

You can open `pipeline.jfr` in a compatible analyzer like **Java Mission Control** to inspect timelines and call stacks more easily. Use findings to form **concrete hypotheses**: e.g. “string construction in the mapper dominates allocation samples” rather than “Stream API is slow”.

### Caution with profilers

Profilers do not “see” optimized-away allocations, and collection itself carries overhead. Never treat a single JFR screenshot or short capture as sufficient proof to redesign an architecture. Record runtime environment, capture duration, load, data samples, and before/after metrics.

## 10. JMH: measuring per-operation latency and allocation

**JMH** (*Java Microbenchmark Harness*) is built for benchmarking JVM code with warmup, forks, and repeated measurements. When comparing two semantically equivalent pipelines, JMH avoids many pitfalls of hand-rolled `System.nanoTime()` loops.

This example **requires JMH dependencies and annotation processors** in a benchmark project, not just the standard JDK. It measures the **exact same error-latency sum** two ways: boxed and primitive.

In an appropriate JMH project, save as `src/main/java/benchmark/PipelineAllocationBenchmark.java` (inside a named package, not the default package):

~~~java
package benchmark;

import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 4)
@Measurement(iterations = 6)
@Fork(2)
public class PipelineAllocationBenchmark {

    record Event(long latencyMs, boolean error) {}

    @State(Scope.Thread)
    public static class Data {

        @Param({"1000", "100000"})
        public int count;

        List<Event> input;

        @Setup(Level.Trial)
        public void setup() {
            input = IntStream.range(0, count)
                    .mapToObj(i -> new Event(
                            1L + i % 97,
                            i % 9 == 0
                    ))
                    .toList();
        }
    }

    @Benchmark
    public long boxedSum(Data data) {
        return data.input.stream()
                .filter(Event::error)
                .map(Event::latencyMs)
                .reduce(0L, Long::sum);
    }

    @Benchmark
    public long primitiveSum(Data data) {
        return data.input.stream()
                .filter(Event::error)
                .mapToLong(Event::latencyMs)
                .sum();
    }

    @Benchmark
    public long imperativeSum(Data data) {
        long result = 0L;
        for (Event event : data.input) {
            if (event.error()) {
                result += event.latencyMs();
            }
        }
        return result;
    }
}
~~~

All three branches compute the **exact same sum** over the defined dataset. The loop branch acts as a **baseline to quantify overhead**, not a mandate for how application code must be written.

The exact JMH run command depends on build setup. Given a properly packaged JMH benchmark artifact, you can run something like:

~~~bash
java -jar benchmarks.jar PipelineAllocationBenchmark -prof gc
~~~

`-prof gc` instructs JMH to report available allocation/GC statistics depending on profiler/JVM, such as bytes allocated normalized per operation. Do not assume every metric is available identically on every JDK.

### Interpreting results within scope

A **measurement target** table, not pre-measured data:

| Benchmark | Semantics | Metrics to compare |
| --- | --- | --- |
| `boxedSum` | Total latency of error events | µs/op, B/op, GC |
| `primitiveSum` | Same sum | µs/op, B/op, GC |
| `imperativeSum` | Same sum | µs/op, B/op, GC |

For each `count` configuration:

- Verify **exact correctness** in a separate test first.
- Compare **time and allocations** on the exact same data volume.
- Repeat across multiple forks to reduce JIT and OS-scheduling skew.
- Exclude list creation from per-operation timing, since data is built in `@Setup(Level.Trial)`.
- Adopt changes only when gains are stable and meaningful for the real workload.

Returning `long` from JMH benchmarks lets the harness observe the result. For other workloads, use `Blackhole` to consume results properly. Never strip out real work just to measure empty loops.

## 11. `B/op` and `MB/s`: understand before optimizing

Two related metrics:

~~~text
allocation per operation ≈ allocated bytes / operation count
allocation rate ≈ allocated bytes / elapsed time
~~~

Exact calculation depends on the measurement tool, work/op definition, profiler, and sampling strategy.

**Hypothetical** example, not JMH output:

~~~text
A: 4 KB/op, 1,000 ops/s -> roughly 4 MB/s
B: 8 KB/op,   100 ops/s -> roughly 0.8 MB/s
~~~

B has **higher B/op** yet a lower per-second allocation rate because its throughput is lower. Therefore, never compare allocation rates while ignoring throughput, input size, and latency.

Likewise, an optimization that cuts B/op while doubling runtime may not pay off if the application is CPU-bound rather than GC-bound.

**Watch out for “allocation = memory leak”:** allocating short-lived objects is normal on the JVM. A logical leak is when **objects past their lifetime stay referenced**, causing live heap or other resources to accumulate unexpectedly.

## 12. When should `toList` be replaced with an aggregation?

A pipeline retaining every output element:

~~~java
List<Long> values = events.stream()
        .filter(Event::error)
        .map(Event::latencyMs)
        .toList();

long total = 0L;
for (Long value : values) {
    total += value;
}
~~~

This materializes a `List<Long>` and its elements just to sum them. If **only a single total is needed**, avoid keeping the intermediate list:

~~~java
long total = events.stream()
        .filter(Event::error)
        .mapToLong(Event::latencyMs)
        .sum();
~~~

The core difference is not merely boxed vs. primitive, it is the **business result shape**:

- If the UI needs every individual latency, `toList()` may be required.
- If only sum, count, or min/max is needed, use the matching terminal operation.
- If per-key stats are needed, choose a downstream collector holding only needed metrics.
- If both the list and total are needed, check whether a single-pass collector can compute both cleanly.

A lazy pipeline **does not mean zero retained data**: `toList`, `sorted`, and certain collectors can still retain very many elements.

## 13. `groupingBy`: controlling cardinality and downstream collectors

A classic memory bottleneck is grouping by a **high-cardinality** key:

~~~java
Map<Integer, List<Event>> grouped = events.stream()
        .collect(Collectors.groupingBy(
                Event::customerId
        ));
~~~

If each event has a different `customerId`, the Map grows nearly as large as the event count. With a List per group, container and reference counts grow too.

When only counts or sums are needed:

~~~java
Map<Integer, Long> errorCountByCustomer =
        events.stream().collect(
                Collectors.groupingBy(
                        Event::customerId,
                        Collectors.summingLong(
                                event -> event.error() ? 1L : 0L)
                )
        );
~~~

This retains one `Long` total per key instead of Lists of every `Event`. Even so, **the Map still scales with distinct customers**. You cannot call it `O(1)` memory when keys grow unboundedly.

If raw data has a unique ID per request, consider whether grouping by a coarser key (such as service or hour) preserves business semantics. If every key is truly required, consider a database, external aggregation, or explicit caps/batching.

### Be cautious with `groupingByConcurrent`

In parallel Streams, `groupingByConcurrent` can reduce Map-merging overhead while altering ordering behavior; it does not automatically guarantee speedups or fewer allocations.

If the downstream is `toList()` and intra-group order matters, never replace `groupingBy` with `groupingByConcurrent` for speed while overlooking its unordered contract.

## 14. `sorted`, `distinct`, and stateful stages

Some intermediate operations become bottlenecks due to coordination or retained state.

### `sorted`

~~~java
List<Event> ordered = events.stream()
        .sorted(java.util.Comparator.comparingLong(
                Event::latencyMs))
        .toList();
~~~

Sorting the entire source typically takes **O(N log N)** time and can need `O(N)` intermediate memory depending on implementation. If business logic only wants the **single largest element**, use an aggregating terminal:

~~~java
java.util.Optional<Event> slowest = events.stream()
        .max(java.util.Comparator.comparingLong(
                Event::latencyMs));
~~~

This avoids building a full sorted list just to pick one element. For **top-K** with small K, consider a bounded heap or specialized collector, carefully defining tie-breakers and verifying correctness.

### `distinct`

~~~java
long uniqueCustomers = events.stream()
        .map(Event::customerId)
        .distinct()
        .count();
~~~

`distinct` must track seen keys to avoid double-counting; high distinct key counts can grow state substantially. If the real goal is estimating cardinality on massive streams, approximate algorithms with explicit error bounds may be required; the Stream API does not turn `distinct` into a constant-memory cardinality counter.

### Prefix operations

`limit`, `skip`, `takeWhile`, and `dropWhile` on sources with encounter order can require coordination under parallelism, especially to preserve exact prefix boundaries. Calling `unordered()` can change semantics; do so only when logical result order is not needed.

## 15. Source bottlenecks: `Spliterator` and I/O sources

No matter how efficient a pipeline's math is, it cannot outrun a slow data source without changing architecture.

Common cases:

| Source | Limit to inspect | Suggestion |
| --- | --- | --- |
| `ArrayList`, arrays | CPU, cache locality, data size | Easy to split, well-suited for CPU-bound tests |
| `IntStream.range` | Per-element work | Easily splittable numeric source, usually low overhead |
| `Iterator` wrapped as Stream | `trySplit` and element-by-element access | Often batches sequentially, hard to speed up |
| `Files.lines` | I/O, charset decoding, disk speed | Does not become faster just by calling `parallel()` |
| Database cursor | DB/network latency and fetch size | Streams do not replace query optimization |
| Custom `Spliterator` | `estimateSize`, `SIZED`, `ORDERED`, `trySplit` | Declare characteristics truthfully and test splitting |

A source can bottleneck due to poor `trySplit()` or sequential reading. Then `parallelStream` spawns tasks without raising source throughput.

**Never misdeclare `Spliterator.SIZED` or `SUBSIZED` hoping Streams run faster.** Characteristics are contracts used by the runtime to optimize; false declarations cause wrong results or invalid optimizations.

### File handle leaks are not the same as many heap objects

A pipeline might hold few heap objects yet exhaust system file descriptors/handles if I/O sources are not closed. With `Files.lines`, use `try-with-resources` to manage lifecycle, even when terminal operations stop early:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long errorLines(Path path) throws java.io.IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {
        return lines.filter(s -> s.startsWith("ERROR")).count();
    }
}
~~~

`count()` finishing does not mean it called `close()`. When investigating a slow or resource-starved application, inspect file handles, connections, threads, and resource ownership alongside heap/GC. **GC tuning cannot fix a resource-lifecycle leak.**

## 16. Parallel streams: separating speedup from contention

For independent CPU-bound per-element work, parallel execution **can** boost throughput when the source splits well, data is large enough, and merge costs are low.

At the same time, it can introduce:

- **More allocations** from per-branch accumulators and temporary merge buffers.
- **Contended locks** if mappers mutate external state/collections.
- **More cache misses** or task-splitting overhead exceeding actual computation.
- **CPU pressure** on concurrent requests sharing the common pool or host cores.
- **Ordered stages** forcing coordination to preserve order.
- **Higher GC pressure** as multiple tasks allocate simultaneously.

**Unsafe** example:

~~~java
List<Long> output = new java.util.ArrayList<>();

events.parallelStream()
        .map(Event::latencyMs)
        .forEach(output::add);
~~~

`ArrayList` is not designed for unsynchronized concurrent writes. Seeing one run happen to preserve element count does not prove the code is correct.

Replace with a proper terminal operation:

~~~java
List<Long> output = events.parallelStream()
        .map(Event::latencyMs)
        .toList();
~~~

On ordered sources, `toList()` preserves result order. Yet if only the latency sum is needed, `mapToLong(...).sum()` avoids building the entire list.

Do not assume adding `synchronized` solves everything. It may protect individual writes while causing contention and still failing to guarantee encounter order in `forEach`.

## 17. Arithmetic accuracy when optimizing allocations

A performance optimization **must not alter business semantics**.

When summing money with `BigDecimal`:

~~~java
BigDecimal total = amounts.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Switching to `double` may reduce or alter allocation behavior, yet can break decimal precision and change rounding behavior.

`BigDecimal` operations typically return new result objects. That alone does not prove `BigDecimal` should be abandoned. Check precision requirements, throughput, and actual memory numbers before trading anything off.

If the domain allows storing the **smallest currency unit** in `long`, a `LongStream` can be efficient, provided overflow and unit conversions are controlled. Without an exact conversion contract, **never change `BigDecimal` to `long` just to make a benchmark look prettier**.

Likewise, switching from a collector holding a full list to returning only a sum reduces memory, yet is **not equivalent** if the caller still needs every output record.

## 18. Diagnosing issues with a repeatable process

You can follow a nine-step workflow:

### Step 1 — State the goal clearly

Example: “Reduce p95 aggregation time for 100,000 events/batch without changing totals or group lists.”

### Step 2 — Fix workload and data

Record seeds/fixtures, input sizes, filter pass rates, distinct keys, fan-out, JDK, heap, and parallelism. Never use an unstable live network source as your sole benchmark evidence.

### Step 3 — Measure end-to-end baseline

Record duration, throughput, CPU, heap, allocations, GC pauses, and wait metrics. Identify which component dominates.

### Step 4 — Use JFR/GC logs to narrow the scope

Locate allocation hotspots, retained heap, GC timing, CPU samples, and thread states. If most time sits in DB/network waits, do not start by tweaking `map`.

### Step 5 — Form a specific hypothesis

Example: “On the hot path, `map(Event::latencyMs).reduce` adds overhead compared to `mapToLong().sum()`.” A hypothesis must be tested, not assumed true.

### Step 6 — Make one small change

Change one variable at a time. Never change GC flags, algorithm, JDK version, and parallel mode simultaneously; otherwise you cannot tell what caused an improvement or regression.

### Step 7 — Verify correctness before benchmarking

Compare against an oracle or fixture: group values, required ordering, null behavior, overflow, exceptions, and closed I/O resources.

### Step 8 — Benchmark under identical conditions

Use JMH for microbenchmarks and integration runs for real pipelines. Compare latency/throughput **and** B/op, GC, and peak memory across multiple runs, inspecting variance.

### Step 9 — Decide and monitor

Keep an optimization only if it delivers meaningful improvement on representative workloads without adding disproportionate risk or maintenance burden. After deployment, monitor metrics over time and keep a rollback plan if real behavior diverges from predictions.

Decision flowchart:

~~~text
Slow pipeline / rising heap
           |
           v
Define workload + baseline
           |
           v
  JFR + GC log + metrics
           |
     +-----+------+------------------+
     |            |                  |
   Hot CPU     Hot GC/heap       I/O/lock wait
     |            |                  |
 map/hash/    allocation +       source, locks,
 sort/reduce  retention          queries
     |            |                  |
     +------------+------------------+
                  |
                  v
         Pick one small change
                  |
                  v
      Correctness test + Benchmark
                  |
          +-------+-------+
          |               |
       Improved       No gain
          |               |
      Monitor         Keep/revert and
      post-deploy     hunt next bottleneck
~~~

## 19. Symptom table: read symptoms, do not guess causes

| Observation | Hypothesis to check | Next measurement |
| --- | --- | --- |
| High B/op, low GC pauses | Many short-lived objects handled well by GC | JMH `-prof gc`; does it actually hurt throughput? |
| Post-GC heap climbs over time | Map/cache/List retaining data | Heap profile, JFR/heap dump per ops policy |
| High CPU inside mapper | Expensive transform/parsing | CPU samples; compare algorithm or inputs |
| Low CPU, high latency | Waiting on I/O, locks, or queues | JFR I/O/ThreadPark, distributed trace |
| `parallelStream` is slower | Split/merge/ordered/lock overhead | JMH sequential vs. parallel on identical workload |
| GC pauses correlate with p99 | Collector/heap pressure | GC log timeline vs. p99 over time |
| `groupingBy` uses huge heap | Many groups or storing Lists per group | Measure cardinality, retained heap; change downstream if contract allows |
| `sorted` dominates runtime | Full sort when only top-K/max is needed | CPU samples; benchmark alternative algorithm |
| `flatMap` spawns many child Streams | Small fan-out, intermediate overhead | Compare against `mapMulti` with same semantics/JDK |
| Few JFR allocation samples | Sampling threshold, JIT elimination, or event config | Verify recording settings; JMH allocation profiler |
| Latency spikes only under high load | Contention, saturation, GC pressure, or I/O quota | Load test tracking concurrency and resource usage |

Avoid single-cause thinking: one symptom can have multiple causes, and two bottlenecks can occur together.

## 20. Things to avoid before measuring

1. **Never optimize by gut feeling:** “Streams are slow”, “lambdas allocate objects”, “lots of GC is bad” are incomplete engineering claims.
2. **Never mass-replace `flatMap` with `mapMulti`:** measure by fan-out, JDK, and short-circuiting. Some `mapMulti` implementations may buffer.
3. **Never switch everything to parallel:** measure CPU, source splitting, ordered stages, contention, and business results.
4. **Never use `toList` when only a sum is needed**, yet never drop the list if callers genuinely need every element.
5. **Never strip validation or error checks for speed:** that turns the benchmark into a different problem.
6. **Never use `peek`/side effects as a guaranteed element-count metric.**
7. **Never treat JFR sampling as an exact count of every allocation**, or one GC log as full proof of a memory leak.
8. **Never tune GC flags based on a microbenchmark alone** without measuring end-to-end impact.
9. **Never throw unlimited heap at retained-object bugs:** larger heaps may hide symptoms without fixing retention.
10. **Never announce an N-times speedup without reproducible real benchmarks.**

These rules separate **evidence-based optimization** from complex changes that hurt maintainability or break data contracts.

## 21. Practice exercises

### Exercise 1 — Distinguish allocation from retention

One pipeline creates 100,000 temporary strings and returns only the element count. Another creates a 50,000-key Map and caches it long-term. Which pipeline has higher memory pressure?

**Answer:** Not enough data to state flatly. The first may have high **allocation rate** with low live heap; the second retains long-lived objects. Measure B/op, retained heap, and GC/throughput impact.

### Exercise 2 — Choosing a primitive pipeline

~~~java
long total = events.stream()
        .map(Event::latencyMs)
        .reduce(0L, Long::sum);
~~~

**Task:** Write a version that reduces boxing.

**Answer:**

~~~java
long total = events.stream()
        .mapToLong(Event::latencyMs)
        .sum();
~~~

Both must use the same input, filtering, and numeric range before benchmarking. The primitive version is a candidate, not an automatic guarantee of being faster on every JDK.

### Exercise 3 — When to drop `toList`?

A pipeline computes average latency, currently calling `toList` to keep all latencies before summing. What should you try instead?

**Answer:** Use `mapToLong(...).average()` if only the arithmetic mean is needed and `OptionalDouble`/empty-data semantics fit. If the list is still needed for display or inspection, you cannot drop `toList` while keeping the same functionality.

### Exercise 4 — `groupingBy` and retention

A report calls `groupingBy(key)` and then only reads `size()` on each list. How can retained heap be reduced?

**Answer:** Try `groupingBy(key, counting())` to keep one count per key without Lists of all elements. The Map still scales with distinct keys.

### Exercise 5 — Is a GC log alone enough?

A batch runs for 100 seconds with 200 young GCs, yet total GC pause time is only 70 ms. Can you conclude GC caused the 100-second runtime?

**Answer:** No. Recorded pause time is tiny relative to runtime; inspect CPU, concurrent GC work, allocations, I/O, and other factors. Collection count alone does not prove a GC bottleneck.

### Exercise 6 — JMH snippet missing a terminal operation

~~~java
@Benchmark
public Object buildOnly() {
    return events.stream().filter(Event::error);
}
~~~

**Answer:** Mainly measures pipeline construction, not traversing/filtering every event. Add a terminal operation performing the target work, and prepare inputs outside measurement.

### Exercise 7 — Are two measurements fair?

Benchmark A uses `flatMapToInt` and `sum`; B uses `mapMulti` producing `Stream<Integer>` then `toList`. Can you conclude API B is slower?

**Answer:** No. The two branches differ in data type, boxing, terminal operation, and output shape. Design benchmarks with identical task, types, data, and parallelism.

### Exercise 8 — Parallelism and shared Maps

~~~java
Map<Integer, Long> counts = new HashMap<>();

events.parallelStream().forEach(e ->
        counts.merge(e.customerId(), 1L, Long::sum)
);
~~~

**Answer:** `HashMap` is mutated concurrently from multiple tasks and is unsafe. Use `collect(groupingBy(..., counting()))` or an appropriate concurrent collector if semantics allow. Re-measure because thread-safe does not automatically mean faster.

### Exercise 9 — Analyzing a processing bottleneck

A profiler shows low CPU usage, most threads waiting on JDBC, and negligible GC pauses. What should be the top priority?

**Answer:** Investigate queries, DB indexes, query count, fetch size, connection pool, or data-access design. Replacing `map` with `mapToLong` is unlikely to fix primary wait time if JVM computation is only a small fraction.

### Exercise 10 — Preserving semantics during optimization

A pipeline uses `BigDecimal` for exact monetary sums and rounds the total once. Should you switch immediately to `double` because JMH runs faster?

**Answer:** Not if business rules require decimal accuracy. A faster benchmark for a different arithmetic problem does not justify breaking the contract. Switch numeric types only with exact conversion rules and thorough testing.

## 22. Optimization sign-off checklist

Before calling a Stream optimization complete:

- [ ] Have a **representative workload** and explicit latency/throughput targets.
- [ ] Record JDK, GC, heap, input size, key count, and concurrency level.
- [ ] Measure a baseline over sufficient duration, not a single run.
- [ ] Identify the bottleneck across CPU/GC/I/O/locks instead of guessing from code.
- [ ] Measure allocation B/op and live/peak heap when memory is involved.
- [ ] Separate temporary objects from objects retained by live references.
- [ ] If changing algorithms, check complexity, fan-out, and group counts.
- [ ] If changing collectors, preserve exact output data and ordering requirements.
- [ ] If switching to primitives, check overflow and numeric semantics.
- [ ] If switching to parallel, eliminate shared mutable state and verify combiners.
- [ ] If using I/O in the pipeline, ensure sources close within the right lifecycle.
- [ ] JMH measures **identical semantics** with a real terminal operation.
- [ ] Integration measurements show meaningful improvement on the real system.
- [ ] Post-deploy monitoring and a rollback plan are ready if needed.

## 23. Key takeaways

- **Allocation rate, live heap, and peak memory are three distinct concepts.** Many short-lived objects do not automatically equal a memory leak.
- **GC frequency alone cannot identify a bottleneck.** Measure pauses, CPU work, retained heap, and correlation with latency/throughput.
- **Pipeline optimization starts from business output.** If only a sum is needed, do not materialize a list; if only per-group counts are needed, do not keep Lists of every record.
- **Primitive streams can reduce boxing**, yet actual impact depends on JIT and workload; always measure.
- **Stateful operations** like `sorted`, `distinct`, and `groupingBy` carry costs tied to input size/key count; do not judge solely by code brevity.
- **Parallel Streams do not cure every bottleneck:** poorly splittable sources, I/O, contention, or ordered stages can make them slower.
- **JFR shows where to investigate**, GC logs reveal collection activity, JMH measures small changes on identical workloads, and integration benchmarks confirm real gains.
- **Never treat mapper/peek invocation counts as a guaranteed KPI** when pipelines can be lazy, short-circuit, or optimized.
- **Correctness before performance.** A fast pipeline that drops data, overflows numbers, or leaks I/O handles is not a successful optimization.

**Main point:** To analyze allocations, GC, and bottlenecks in the Java Stream API, **measure phenomena separately**, isolate the cause, change one variable at a time, and re-verify both outputs and resources. Valuable optimizations are those **proven on representative data, faithful to business contracts, and free of new memory or operational risks**.
