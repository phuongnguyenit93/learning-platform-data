# Reliable Benchmarking with JMH in Java Concurrency

When optimizing concurrent code, the question to answer is not merely “which snippet runs faster?” but also **under what load conditions, on which hardware/JDK, at what level of resource contention, and whether the difference is reproducible.** Java has a JIT compiler, garbage collector, multiple cache levels, CPU scheduling, a memory model, and synchronization primitives. Therefore, wrapping a few calls with `System.nanoTime()` can easily lead to wrong conclusions.

**JMH (Java Microbenchmark Harness)** is an OpenJDK tool for building, running, and analyzing benchmarks for the JVM. **JMH is not part of the JDK standard library**: it requires dependencies, a benchmark code generator (annotation processor), and proper build configuration. JMH handles warmup, measurement iterations, JVM forks, worker threads, and many measurement pitfalls; however, it **does not automatically guarantee** that your workload design matches a real-world system.

The scope of this article is **Java concurrency in general**: how to use JMH to measure `AtomicLong`, `LongAdder`, contention levels, reader/writer groups, how to interpret scores, and how to control reliability. Benchmarks are only evidence for the measured workload; they do not replace correctness testing or end-to-end benchmarking.

## 1. Why Manual Measurement Often Fails

The following example is **not sufficient** to conclude that one concurrency primitive is “faster”:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    counter.incrementAndGet();
}
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

This snippet is an **illustration of uncontrolled measurement**, not a complete program. It lacks critical factors:

- **JIT warmup / tiered compilation:** early calls incur initialization, interpretation, profiling, compilation, and deoptimization costs. A single measurement may mix multiple JVM phases.
- **Dead-code elimination and constant folding:** the JIT can eliminate unobservable computations, fold constants, or optimize away the entire loop; the result may end up measuring “no work at all.”
- **Loop optimization:** writing a loop inside the measured region can be unrolled, vectorized, or have a different control-flow structure than a single invocation; you must distinguish what constitutes a single JMH operation.
- **Timer granularity/overhead:** measurements that are too short are easily distorted by clock-read overhead and scheduling.
- **GC, safepoints, and OS scheduling:** threads can be paused by garbage collection, context switches, background processes, thermal/power throttling, or migration to another core.
- **Lack of forking:** tests run in the same JVM can interfere with each other through the code cache, profiling data, class state, or static data.
- **Wrong contention model:** a single-threaded benchmark cannot predict the performance of 32 threads writing to the same variable; conversely, “32 threads” does not mean 32 CPU cores.
- **Wrong workload:** comparing operations with different effects or precision, using data that fits entirely in cache, or ignoring allocation rates and realistic read/write ratios all lead to misleading conclusions.

`System.nanoTime()` is a relatively suitable monotonic clock for measuring elapsed time, but **merely swapping the timer does not solve** the remaining biases. JMH is a good starting point; the benchmark author must still control the hypothesis and data.

## 2. Core Concepts of JMH

| Concept / annotation | Role | Notes for concurrency measurement |
| --- | --- | --- |
| `@Benchmark` | Marks a method to be measured by the harness | One invocation must represent a clearly defined operation |
| `@State(Scope.Thread)` | Each worker thread gets its own state | Suitable for measuring unshared / uncontended cases |
| `@State(Scope.Benchmark)` | All workers of a benchmark share the state | Suitable for measuring multiple threads accessing the same object |
| `@State(Scope.Group)` | State is shared within a group | Used with asymmetric reader/writer workloads |
| `@Threads(n)` or `-t n` | Number of benchmark worker threads | Vary thread count to find saturation point; do not equate with core count |
| `@Group` + `@GroupThreads` | Different methods run concurrently in a group | Tests interactions across multiple operation types |
| `@Warmup` | Runs before collecting main results | Allows JIT and state to reach a relatively steady phase |
| `@Measurement` | Duration / number of measurement iterations | Multiple iterations help observe variance |
| `@Fork` | Runs in a separate child JVM | Reduces cross-run state interference |
| `@Param` | Tests controlled input values | Avoids hard-coding a single data size |
| `@Setup`, `@TearDown` | Prepares and cleans up state by level | Separates setup code from the actually measured code |
| `Blackhole` / returning a result | Makes computation results observable | Reduces risk of JIT eliminating useless work |

**Scope defines the meaning of the benchmark:** a separate `AtomicLong` per thread has virtually no contention; a single `AtomicLong` shared across all threads has update contention. If the goal is to compare both cases, they must be two explicit state configurations.

A **JMH operation** is the unit of work the harness uses to compute the score. If a `@Benchmark` executes a batch of 100 increments, the default `ops/s` metric is the number of *benchmark method invocations* per second, not automatically 100 increments/second. You can use `@OperationsPerInvocation` when appropriate, but it must accurately reflect the model and avoid double counting.

## 3. Choosing a Mode and Reading Units

| Benchmark mode | Meaning | Suitable question |
| --- | --- | --- |
| `Mode.Throughput` | Operations completed per unit of time; higher is usually better | How many counter updates per second? |
| `Mode.AverageTime` | Average time per operation; lower is usually better | How long does a single lock or operation take on average? |
| `Mode.SampleTime` | Samples operation times to inspect distribution and percentiles | Is there a large tail at the invocation level? |
| `Mode.SingleShotTime` | Measures a single execution; suitable for startup or very short/long operations needing isolated evaluation | How long does startup/initialization take? |

For example, in `Mode.Throughput`, `Score = 7_500_000 ops/s` means an average of about 7.5 million **JMH operations per second** were measured under that workload and configuration—it does **not** mean a real service can handle 7.5 million requests per second. The number above is only a unit-reading example, not a measurement from a machine.

JMH typically reports `Benchmark`, `Mode`, `Cnt`, `Score`, `Error`, and `Units`. `Error` reflects how JMH aggregates samples/iterations; it should not be treated as a guarantee that the environment is clean or the workload is valid. Differences smaller than the observed variance require further evidence, more forks, and distribution analysis—never cherry-pick the best run.

In multi-threaded benchmarks, the time of an operation under contention also depends on scheduling and the operations performed by other threads. `AverageTime` and `SampleTime` here only measure the `@Benchmark` boundary, not automatically the end-to-end latency of an HTTP request, database transaction, or entire application.

## 4. Creating a Standalone Runnable JMH Project

JDK 17+ and Maven are required. The simplest approach, recommended by the JMH project, is to create a **separate Maven module using an archetype**, rather than embedding stopwatch calls in production code. For example, pinning JMH version **1.37** (the release published on Maven Central at the time of writing):

```bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DarchetypeVersion=1.37 -DgroupId=org.example -DartifactId=jmh-concurrency -Dversion=1.0-SNAPSHOT
cd jmh-concurrency
```

The archetype generates a POM configuration along with the required code-generation compilation pipeline. With JMH, **adding only `jmh-core` as a regular Java library is not enough**; the annotation processor must generate the harness classes. If you configure Maven/Gradle manually, ensure matching versions of `jmh-core` and `jmh-generator-annprocess`, proper annotation processor configuration, an executable benchmark output, and properly packaged dependencies.

Key structure after creation:

```text
jmh-concurrency/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    └── CounterBenchmark.java
```

Place the `CounterBenchmark` class under the `org.example` package as shown in the next section. The archetype may also generate a sample `MyBenchmark.java`; running with the `CounterBenchmark` filter ensures only this benchmark is measured.

From the module root directory:

```bash
mvn clean verify
java -jar target/benchmarks.jar -l
```

`-l` lists the benchmarks discovered by the generator. If your newly written method does not appear in the list, check the package/class, annotation processor, source directory placement, and build success. Then run with `java -jar target/benchmarks.jar`; check `-h` for the full set of CLI options in your installed JMH version.

Official documentation:

- [OpenJDK JMH – project, archetype setup, and CLI usage](https://github.com/openjdk/jmh)
- [JMH Samples – source examples on scope, group, blackhole, and measurement pitfalls](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples)
- [JMH Core 1.37 API](https://javadoc.io/doc/org.openjdk.jmh/jmh-core/1.37)

## 5. Runnable Example: AtomicLong vs. LongAdder Under Contention

Both primitives support concurrent counting, but they **do not share the same read contract**: `AtomicLong.get()` provides an atomic read with strong semantics; `LongAdder.sum()` is an aggregation, not an atomic snapshot when concurrent updates are occurring. The following benchmark **only measures the increment operation**; it does not prove the two types are interchangeable in every API.

Create `src/main/java/org/example/CounterBenchmark.java`:

```java
package org.example;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Benchmark)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 3, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(2)
public class CounterBenchmark {
    private final AtomicLong atomic = new AtomicLong();
    private final LongAdder adder = new LongAdder();

    @Benchmark
    public void atomicIncrement() {
        atomic.incrementAndGet();
    }

    @Benchmark
    public void adderIncrement() {
        adder.increment();
    }
}
```

Design notes:

- `@State(Scope.Benchmark)` makes **all workers of each benchmark share the same counter instance**, thereby measuring contention when `-t` is greater than 1. JMH schedules each benchmark method as a separate workload, not two counters under simultaneous load.
- Both methods perform **a single update on the shared object** per invocation. Do not add a large loop inside the benchmark and do not allocate a new counter per invocation.
- Mutating the counter state is a real side effect observable across threads, unlike a pure computation that could be eliminated; you should still verify the assumption that the benchmark is not distorted by JIT optimizations.
- `@Warmup` and `@Measurement` specify the duration of each iteration; `@Fork(2)` requests two JVM forks for independent evidence. These are **illustrative starting values** and should be adjusted if stability is insufficient.

Compile and run the two conditions **separately**:

```bash
mvn clean verify
java -jar target/benchmarks.jar CounterBenchmark -t 1
java -jar target/benchmarks.jar CounterBenchmark -t 4
```

`-t 1` measures without multiple workers competing for the same counter; `-t 4` measures four workers touching the shared state concurrently. Numeric results **depend on CPU, JDK, JVM settings, machine load, and the workload itself**; there is no fixed stdout score to copy. When reading the report, inspect the full names including `atomicIncrement` / `adderIncrement`, thread count, `Mode=thrpt`, unit `ops/s`, and variance across forks/iterations.

If `LongAdder` leads under multi-threaded writes, the only valid conclusion is: “for the **write-only increment** workload defined here, on this machine and test configuration, throughput is higher.” It does **not** prove `LongAdder` is always faster under high `sum()` frequency, tight memory constraints, or consistent snapshot requirements.

You can run additional thread counts `1, 2, 4, 8, ...` (bounded by the machine, noting logical/physical core counts) and plot throughput vs. thread count. The saturation point can differ across low-core machines, multi-socket CPUs, and JDK versions. Do not compare two primitives if one was run with a different thread count or JVM flags than the other.

## 6. Runnable Example: Asymmetric Read/Write Groups with @Group

A writer-only benchmark does not model a system with many readers and few writers. JMH provides `@Group` to place different benchmark methods into the **same concurrently executing group**, and `@GroupThreads` to specify the number of workers for each role.

Create another file `src/main/java/org/example/ReadWriteGroupBenchmark.java`:

```java
package org.example;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Group;
import org.openjdk.jmh.annotations.GroupThreads;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 3, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(2)
public class ReadWriteGroupBenchmark {

    @State(Scope.Group)
    public static class Counter {
        final AtomicLong value = new AtomicLong();
    }

    @Benchmark
    @Group("readWrite")
    @GroupThreads(3)
    public long read(Counter state) {
        return state.value.get();
    }

    @Benchmark
    @Group("readWrite")
    @GroupThreads(1)
    public long write(Counter state) {
        return state.value.incrementAndGet();
    }
}
```

Run:

```bash
mvn clean verify
java -jar target/benchmarks.jar ReadWriteGroupBenchmark -t 4
```

One group has **3 read-only workers and 1 writer worker**, sharing a `Counter` with `Scope.Group`. `-t 4` creates one complete group. If you increase threads to a multiple of 4, JMH may create multiple independent groups that do not necessarily contend on the same `Counter`; to measure **a single shared data point with more readers/writers**, you must design the state/scope accordingly.

The group report includes an aggregate score and per-method sub-lines. A ratio of **3 reader threads : 1 writer thread does not mean** the read : write operation count will be 3:1, because each operation type runs at a different speed. A read operation is typically cheaper than an update. This benchmark illustrates reads/writes on an **atomic counter**, and does not automatically represent `ReentrantReadWriteLock`, database workloads, or application processing pipelines.

## 7. Designing Workloads for Meaningful Comparisons

Before writing `@Benchmark`, state your hypothesis in words:

> “When N threads concurrently increment a shared counter, LongAdder has higher increment throughput than AtomicLong, provided callers do not need an exact snapshot read while writers are active.”

From that hypothesis, identify the **constants**, **independent variables**, and **dependent variables**. For the example above: hold machine/JDK/JVM flags, warmup, duration, forks, and invocation method constant; vary thread count and primitive; observe throughput, variance, allocation, CPU, and GC. Choose a truly relevant baseline: if production has 99% reads, a write-only benchmark is not a valid basis for choosing a primitive.

**State/thread sharing:** measure both `Scope.Thread` (unshared) and `Scope.Benchmark` (shared) when you want to separate the inherent cost of an operation from the cost of contention. Do not accidentally let each worker create its own object and then conclude that a shared concurrent primitive has “no contention.”

**Data size:** use `@Param` for array size, entry count, hit/miss ratio, work inside a critical section, or striping count; verify that inputs across variants are equivalent. You can initialize data in `@Setup(Level.Trial)` if you only want to measure the operation, but if production always constructs data per request, you need a higher-level benchmark that includes that cost.

The following is a **snippet to embed into a benchmark class with proper JMH annotations**, not a standalone Java file:

```java
@State(Scope.Thread)
public static class Input {
    @Param({"64", "4096"})
    public int size;

    public int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];
        for (int i = 0; i < size; i++) {
            values[i] = i;
        }
    }
}

@Benchmark
public long sum(Input input) {
    long result = 0;
    for (int value : input.values) {
        result += value;
    }
    return result;
}
```

Import `State`, `Scope`, `Param`, `Setup`, `Level`, and `Benchmark` when embedding this snippet. Returning `result` lets the harness observe the output instead of leaving the loop as dead computation. However, fixed initialized data can create cache/JIT advantages unlike production; if real-world inputs vary, model that variation.

**State before each measurement:** `@Setup(Level.Trial)` runs per trial, `@Setup(Level.Iteration)` per iteration, and `@Setup(Level.Invocation)` per invocation; `@TearDown` works similarly. Do not place heavy initialization at the invocation level if your goal is to measure a single small operation. Conversely, benchmarking a data structure that accumulates data unboundedly can change in difficulty over time; perform controlled resets or measure the accumulation intentionally.

**Equivalence:** operations with the same name such as “insert”, “increment”, or “lock” do not necessarily have the same semantics. `LongAdder.sum()` does not provide an atomic snapshot like `AtomicLong.get()` under concurrent updates. Fairness ordering, memory visibility, fallback algorithms, GC impact, and data accuracy can all be product-level differences, not just `ops/s` differences.

## 8. Blackhole, Dead-Code Elimination, and Escape Analysis

If a method performs arithmetic and discards the result, the JIT can eliminate it entirely because it is unobservable:

```java
@Benchmark
public void broken() {
    double x = Math.sqrt(123.456);
    // x is unused; this can be optimized away.
}
```

This is a **non-standalone illustrative snippet** without imports or a class wrapper. To make the computation meaningful, **return the result** from the benchmark method or accept `org.openjdk.jmh.infra.Blackhole` and call `consume(...)` on the result:

```java
@Benchmark
public void consumeResult(Blackhole blackhole) {
    double x = Math.sqrt(123.456);
    blackhole.consume(x);
}
```

Import `@Benchmark` and `Blackhole` in your JMH class. Returning the value is often the simplest solution; `Blackhole` is useful when consuming multiple values or complex data.

**Do not overuse Blackhole:** `consume` itself has overhead; in extremely tiny measurements, that overhead can be relatively large. Do not use `Blackhole` to “rescue” a benchmark that is not doing production-like work. JMH helps prevent computation elimination, but you still must consider constant folding, dead stores, escape analysis, scalar replacement, and compiler intrinsics; when in doubt, vary inputs, inspect disassembly/JIT profiles if tools are available, and benchmark larger workloads.

**Do not wrap tests in an overly long custom loop** just to get “nice” numbers. JMH already handles invocation repetition and measurement duration. If each operation genuinely must be a batch, clearly define the batch size and corresponding operation count.

## 9. Measuring Concurrency: Contention, False Sharing, Scheduling, and Blocking

**Contention:** throughput may rise at 2–4 threads and then drop at 16–32 threads due to cache coherence traffic, CAS retries, lock contention, or memory bandwidth saturation. Test across thread counts and distinguish useful CPU work from blocked/waiting time. “More threads” only increases parallel work when resources and the algorithm actually allow it.

**False sharing:** two logically independent variables located close together on the same cache line can cause cache-line ping-pong across cores. A benchmark with `@State(Scope.Benchmark)` containing multiple fields updated by different threads may unintentionally measure false sharing cost. Check layout, per-thread ownership, memory padding, and data design before concluding an algorithm is slow. Do not use microbenchmark results to assert an exact cache-line size across all CPUs/JVMs.

**Thread pinning, affinity, and CPU topology:** the OS can migrate threads across cores, SMT siblings share resources, and multi-socket CPUs have non-uniform memory access paths. For scientific comparisons, record physical/logical core counts, topology, power governor, and CPU affinity settings if supported by the environment. Do not assume two runs on a plugged-in/charging laptop have identical conditions.

**Blocking vs. CPU-bound:** increasing `@Threads` on a CPU-bound increment is not equivalent to measuring a task that waits on I/O or `LockSupport.park`. A throughput benchmark for an executor, lock, or queue must model producers/consumers, enqueue/dequeue ratios, batching, lock hold times, thread counts, and progress under blocking. Benchmarks using virtual threads (on supported JDKs) still need to specify the scheduler, blocking points, and downstream resources; you cannot extrapolate them from platform-thread microbenchmarks.

**JVM pauses:** GC/safepoints, class loading, or JVM compilation can create outliers; warmup helps but does not eliminate them. If a method allocates, profile allocation rates and GC pressure. A variant that is faster in raw CPU time but allocates heavily or increases tail latency may be worse in practice.

**Correctness before performance:** JMH does not detect linearizability bugs, deadlocks, data races, or memory visibility violations. Unit tests, stress tests, and tools like JCStress (also outside the JDK) test concurrency correctness; JMH answers **performance** questions, not correctness verification.

## 10. A Reproducible Experimental Workflow

### Step 1: State the hypothesis and metric

Explicitly write down the workload, software, thread count, state type, data size, read/write ratio, measured operation, and win/loss criteria. Choose the primary metric before looking at results—for example, throughput of an accepted increment. If the metric does not reflect system goals, change the experimental design.

### Step 2: Fix conditions and build cleanly

Record the JDK vendor/version, JMH version, OS, CPU, cores/SMT, RAM, JVM flags, GC, heap size, and the commit hashes of both the benchmark code and the code under test. Avoid running benchmarks inside an IDE when you need comparable numbers: the environment and build/JMH annotation processing may differ from the CLI. Ensure the same build process and the same binary/config for all variants.

Run benchmarks on a quiet machine with minimal background tasks, stable power, and stable thermals. For CI running on shared machines, scores are useful as reference signals and for catching large regressions, not necessarily reliable for comparing differences of a few percent.

### Step 3: Smoke test, then full run

First use a short run to verify the command, that the source contains the expected JMH benchmarks, state setup, and no abnormal results. Then run sufficiently long warmup/measurement/forks; increase forks and duration if individual iterations fluctuate heavily.

Example running 4 threads, 2 forks, 3 warmup iterations, 5 measurement iterations, 1 second each:

```bash
java -jar target/benchmarks.jar CounterBenchmark -t 4 -f 2 -wi 3 -i 5 -w 1s -r 1s -bm thrpt -tu s
```

Flag meanings:

| Flag | Meaning |
| --- | --- |
| `-t 4` | Number of JMH worker threads |
| `-f 2` | Two separate JVM forks |
| `-wi 3` | Three warmup iterations |
| `-i 5` | Five measurement iterations |
| `-w 1s` | Duration of each warmup iteration |
| `-r 1s` | Duration of each measurement iteration |
| `-bm thrpt` | Throughput mode |
| `-tu s` | Time unit in seconds |
| `-rf json`, `-rff file.json` | Write results in JSON format to the specified file |

Save machine artifacts and the configuration used alongside each JSON file:

```bash
java -jar target/benchmarks.jar CounterBenchmark -t 4 -f 2 -wi 3 -i 5 -w 1s -r 1s -bm thrpt -tu s -rf json -rff counter-t4.json
```

There is no **fixed benchmark stdout**: actual results vary by machine, environment, and run. Take `Score` and `Error` from your actual run; never assign fabricated numbers to any primitive.

### Step 4: Vary one variable at a time, observe the full curve

Using the same JVM flags and benchmark configuration, run `-t 1`, `-t 2`, `-t 4`, `-t 8`, and extend further if hardware and goals warrant it. Re-run the entire comparison pair when changing JDK or CPU; do not combine measurements from two different machines into a simple speedup ratio.

For each configuration, repeat across multiple runs/times if the environment is noisy, and record dispersion. Do not keep only favorable forks. Inspect CPU utilization, GC, allocation, lock contention, and temperature if results invert or fluctuate widely.

### Step 5: Interpret results within scope

A well-scoped conclusion looks like:

> “With four JMH workers concurrently updating a shared counter, on JDK X, CPU Y, with identical warmup/fork/duration, algorithm A achieved higher throughput than B in this increment-only test; this needs validation against real read/write ratios and consistency requirements before changing production code.”

Claim statistical significance only after examining error margins, distributions, and sufficient runs; a small `Error` interval does not cure **systematic bias**. If the difference is near the noise floor, a reasonable conclusion may be “no clear evidence yet,” favoring the simpler or contract-compliant solution.

## 11. Profiling and Result Explainability

JMH supports built-in profilers and environment-dependent plugins. You can list available profilers:

```bash
java -jar target/benchmarks.jar -lprof
```

For example, the `gc` profiler provides allocation/GC metrics when supported by the JMH and JVM versions:

```bash
java -jar target/benchmarks.jar CounterBenchmark -t 4 -prof gc
```

Do not assume all profilers (hardware counters, perf, assembly) are available: they often require OS/tool support, perf counter permissions, or extra JVM flags. Profilers also add overhead; do not equate profiled scores with an unprofiled baseline without accounting for that impact.

When a lock or queue benchmark shows unexpected throughput, check:

- Is CPU usage high because of useful work or because of spinning/CAS contention?
- Do blocked time and parking reflect lock contention?
- How much do allocation rate and GC differ?
- Do cache/false sharing, data locality, or branch prediction change with input?
- Has throughput hit a memory bandwidth, CPU scheduling, or synchronization bottleneck?

Ideally, measure at two layers: **JMH microbenchmarks** to isolate mechanisms, and **application/load benchmarks** to verify resources, latency, p95/p99, and throughput in realistic flows. A few-nanosecond “win” in a primitive can be completely masked by I/O or serialization costs in a real system.

## 12. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Single run without warmup/fork | Mixes startup, JIT, and JVM noise | Use warmup, multiple iterations, multiple forks, and save raw results |
| Unused result | JIT eliminates computation or folds it into a constant | Return the result / use `Blackhole`, verify side effects |
| Accidental object allocation in method | Measures allocation instead of the target operation | Prepare state in `@Setup` if aligned with the hypothesis |
| Incorrect state reset | Stale data causes drift or reset breaks the workload | Define lifecycle and reset logic explicitly |
| Using `Scope.Thread` when wanting shared contention | Misses cross-thread synchronization cost | Use `Scope.Benchmark` or `Scope.Group` |
| Using `Scope.Benchmark` when wanting per-thread | Creates artificial contention | Use `Scope.Thread` |
| Comparing two primitives with different contracts | “Faster” but different correctness guarantees | Compare semantics, visibility, atomicity, and workload |
| Reading throughput as latency | Misjudges user-facing serving capacity | Choose appropriate mode, unit, and measurement boundary |
| Using 32 threads on a small machine and calling it linear scaling | Distorted by oversubscription/scheduling | Test multiple thread counts and record CPU topology |
| Putting a large loop inside `@Benchmark` unnecessarily | Miscounts operations; optimizer alters semantics | One operation per invocation or declare batching explicitly |
| Testing in an IDE or overloaded machine and comparing scores | Non-reproducible, high noise | Use a stable CLI build and record the environment |
| Optimizing from micro-numbers without a real workload | Regressions in latency, memory, or correctness | Monitor end-to-end and run functional tests |
| Assuming JMH replaces race testing | Benchmark runs fast even with wrong results | Use unit/stress/JCStress tests for correctness |

## 13. Suggested Exercises

1. Run `CounterBenchmark` at `-t 1` and `-t 4`, recording both primitives and their units. If the ranking changes, explain it in terms of contention and `LongAdder`'s design.
2. Run `-t 2` and `-t 8` on the same machine if hardware permits. Plot throughput vs. thread count for each primitive; identify where scaling slows down or drops.
3. Run `ReadWriteGroupBenchmark` with a 3-read + 1-write group. Compare the reader and writer sub-throughputs; explain why the read/write operation ratio does not equal the thread ratio.
4. Try increasing `-f` and `-r` when results are unstable; compare variance between the two configurations and note the experimental time cost.
5. Add a case that frequently reads from `LongAdder.sum()` and verify **the required semantics** before comparing performance with `AtomicLong.get()`.
6. Write a one-paragraph report including JDK/JMH version, hardware, configuration, Score/Error/Units, and inference limits. Never claim “X is always faster than Y everywhere” from a single configuration.

## 14. Checklist Before Trusting a JMH Result

- [ ] Hypothesis, measured operation, and `op` unit are clearly defined.
- [ ] All variants have **acceptable correctness and semantics** for the problem.
- [ ] State scope, thread count, and group composition match the intended resource sharing.
- [ ] DCE, constant folding, escape analysis, allocation, and benchmark loops have been reviewed.
- [ ] Warmup, measurement, forks, and duration are sufficient for reproducibility; no cherry-picking the best run.
- [ ] JDK, JMH, JVM flags, CPU, OS, and source/binary versions are recorded.
- [ ] Scores are read with the right `Mode`/`Units` and variation is analyzed.
- [ ] Conclusions state the exact workload scope; production changes are validated via profiling and load testing.

**Core principle:** JMH makes Java concurrency measurements structured and reproducible, but the quality of your conclusion depends on choosing **the right workload, right scope, right worker count, right control baseline, and a sufficiently stable measurement environment**. Numbers are only trustworthy when others can re-run the same code/configuration, inspect the error margins, and understand exactly what the measurement represents.