# Warming up JVM, JIT, and Avoiding Broken Microbenchmarks

## 1. Why can a Java concurrency measurement be wrong from the start?

For the exact same piece of Java code, execution time when the application has just started can differ significantly from when the system has been running for a while. If you simply time a loop with `System.nanoTime()`, it is very easy to mistakenly conclude that code version A is faster than B, one concurrent API is faster than another, or more threads are always better.

**Warm-up** is the process of pre-running a workload so that initialization and optimization activities have a chance to occur before measuring the desired state. **JIT (Just-In-Time compilation)** is one of several reasons performance changes over time: the JVM may start by interpreting bytecode, collect execution profiles, and then compile hot paths into optimized machine code.

However, warm-up **is not magic that makes measurements accurate**. It does not eliminate bias caused by the optimizer removing code, CPU frequency scaling, GC, thread scheduling, resource contention, unrepresentative data, or using the wrong benchmarking tool. For concurrency problems, coordination overhead and contention between threads make results even noisier.

This article focuses on **Java SE / JVM in general** and measuring concurrent code performance, not application framework abstractions.

### Distinguishing three performance questions

| Question | What is measured? | Appropriate warm-up? |
| --- | --- | --- |
| Startup/cold path | From process start until ready to serve; the first request or task | Do not exclude cold-start; that is the target being measured |
| Steady-state throughput | Amount of work completed per second once the system is running | Usually requires sufficient warm-up, observing the stabilization point |
| Steady-state latency | Time to complete a single operation/request once the system is running | Needs appropriate warm-up; distinguish per-operation latency from harness overhead |

If the real task requires optimizing startup time, warming up and discarding all initial runs will **hide** the cost you care about. Conversely, if you want to compare steady-state throughput, mixing startup with hot runs will skew the results.

## 2. What happens as Java code warms up?

The following details describe the **HotSpot JVM** commonly found in OpenJDK, not a mandatory requirement of every Java Virtual Machine.

### 2.1 Class loading, initialization, and ecosystem setup

The first few times a class is used, the JVM may have to load, link, and initialize the class, run static initializers, set up related structures, and create necessary objects/methods. The program may also not yet have created worker threads, executors, buffers, connections, or data structures.

Therefore, a single call may bear setup costs that occur only once or occasionally. You must decide clearly whether that setup cost is within the measurement scope. For example, measuring the cost of **creating an ExecutorService** is a different problem from measuring the cost of **executing tasks on an existing executor**.

### 2.2 Interpreter, profiling, tiered compilation

A typical path in HotSpot can look like this:

```text
Bytecode
   |
   v
Interpreter (observes how code runs)
   |
   +----> C1 compiler: fast compilation, may collect profiling
   |
   +----> C2 compiler: deeper optimization for hot code
   |
   v
Machine code currently in use by the JVM
```

This is a conceptual diagram, **not a rigid sequence** that every method must always go through completely. HotSpot typically enables *tiered compilation*, selecting compilation levels based on invocation counts, loop iteration counts, branch profiles, object types, and many other factors. The JVM can compile a long-running loop using **OSR (On-Stack Replacement)** without waiting for the method to finish before applying the compiled code.

Optimizations that may occur:

- **Inlining:** replacing a method call with the method body when appropriate, paving the way for further optimizations.
- **Constant folding/propagation:** precomputing expressions whose values are known with certainty.
- **Dead-code elimination:** removing computations that do not affect observable results.
- **Loop optimizations:** optimizing loops, eliminating redundant computations, and transforming execution.
- **Escape analysis and scalar replacement:** under suitable conditions, eliminating certain allocations or breaking an object into scalar values.
- **Speculative optimization:** based on observed object types/behavior; if an assumption no longer holds, the JVM can **deoptimize**, fall back to another execution path, and recompile.

Therefore, "having run 1,000 times" **does not prove the JIT has finished optimizing**. A rarely called method, work with different data, a different thread, or a changing profile may still need compilation/deoptimization.

### 2.3 Warm-up is not just JIT

After running for some time, many factors outside the JIT also change state:

- CPU data/instruction caches and branch predictors have "learned" the workload.
- Heap, allocation paths, TLABs, and GC generations/cycles are in a different state.
- Threads and thread pools are initialized; some threads have passed their first-time costs.
- JDK/libraries have lazy caches, internal structures, and resource initialization.
- The CPU adjusts clock frequency and turbo/thermal state based on load and temperature.
- OS scheduling changes based on other processes and CPU busyness.

**Consequence:** observing that later rounds are faster than the first round is **not sufficient proof** that the JIT alone caused the entire difference. You should use observability tools and multiple controlled runs to explain the cause.

## 3. Example of observing warm-up with Java 17+

This is an **illustrative experiment**, not a reliable benchmark for publishing speedup ratios. The program computes a function with varying input, stores the result in a `volatile` field to create an observation point, and prints the time of each round.

Save as `WarmupObservation.java`:

```java
public class WarmupObservation {
    private static volatile long visibleResult;

    static long work(int seed) {
        long x = seed;
        for (int i = 0; i < 1000; i++) {
            x = x * 1664525L + 1013904223L;
        }
        return x;
    }

    public static void main(String[] args) {
        for (int round = 1; round <= 5; round++) {
            long start = System.nanoTime();
            long sum = 0;
            for (int i = 0; i < 20_000; i++) {
                sum ^= work(i + round);
            }
            visibleResult = sum;
            long elapsed = System.nanoTime() - start;
            System.out.println(
                    "round=" + round
                    + ", result=" + visibleResult
                    + ", elapsedNs=" + elapsed);
        }
    }
}
```

Compile and run:

```shell
javac --release 17 WarmupObservation.java
java WarmupObservation
```

A single run will print **five lines**, each with `round=...`, `result=...`, and `elapsedNs=...`. `result` is computed using deterministic Java arithmetic; **`elapsedNs` always depends on the machine and the run**, so no "standard timing output" is provided. The code above was compiled with `--release 17` and run successfully on JDK 24.

### Reading the results correctly

1. Early rounds **may** be slower due to JIT, class loading, and various initialization effects, but latency is not guaranteed to decrease monotonically across rounds.
2. `volatile visibleResult` creates an observation point after each round; it does not replace proper benchmark design. The volatile write cost is still inside the timing region.
3. `System.nanoTime()` is a clock for measuring **elapsed wall-clock intervals**, not single-thread CPU time, and it does not automatically exclude scheduling, GC, JIT, or OS noise.
4. The `round` loop includes harness code, method calls, and addition/XOR operations. You cannot treat `elapsedNs / 20_000` as the pure time of `work` without knowing how the optimizer transformed the code.
5. Running the experiment a few times and seeing different numbers is **the reason to use a dedicated harness**, not proof that the JIT is broken.

To try observing HotSpot compilation while running the example:

```shell
java -XX:+PrintCompilation WarmupObservation
```

The JVM may print many compilation lines, including for JDK libraries. Output varies by HotSpot version, CPU state, and run; the printed lines are not a performance score. On supported JDKs, you can enable GC logging in a separate diagnostic run with `-Xlog:gc`; logging itself adds overhead, so do not compare it directly against non-logging runs by default.

## 4. Why microbenchmarks using nanoTime are often wrong

A **microbenchmark** measures a small operation (nanoseconds, microseconds, or milliseconds). The shorter the operation, the more easily design flaws overwhelm the real signal.

### 4.1 Dead-code elimination

```java
long start = System.nanoTime();
long sum = 0;
for (int i = 0; i < 1000; i++) {
    sum += i;
}
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

The snippet above is an **anti-pattern illustration**. The variable `sum` is never used, so the compiler can eliminate the entire computation or transform the loop. You think you are measuring 1,000 additions, but you may only be measuring the clock calls and surrounding shell.

**Fix principle:** ensure the result of the computation is actually observed. In JMH, a benchmark can **return the result**, or use `Blackhole.consume(...)` when multiple results must be consumed. Simply "printing the result to the console" inside the measurement causes I/O to overwhelm the operation being measured.

### 4.2 Constant folding and unrepresentative inputs

```java
// Anti-pattern when measuring a tiny computation:
int value = 40 + 2;
```

The compiler can immediately know the result is 42. Even if replaced by a function call, after inlining the JIT can still recognize invariant inputs and optimize more aggressively than in a real workload.

**Fix principle:** use a pre-prepared, representative set of inputs with appropriate variation, place state in a JMH `@State`, and consume the results. However, do not generate random inputs or read files inside the timing region if that is not part of the work you want to measure.

### 4.3 Operation too short, measured too few times, wrong unit division

```java
long t0 = System.nanoTime();
int x = 2 * 3;
long ns = System.nanoTime() - t0;
```

The snippet above cannot separate the cost of multiplication from the effective resolution/overhead of the clock and compiler. Nanosecond units do not mean the clock accurately measures every single nanosecond.

Manually increasing the loop count sometimes reduces relative overhead, but introduces the risk of the JIT optimizing **the entire loop** in a way that does not resemble an isolated call. The harness needs to control iteration counts and ensure an observable result.

### 4.4 Warming up one configuration, then measuring another

If you always measure A first and B second in the same JVM, B may benefit from caches, JIT, or a warmer CPU state. Conversely, B may suffer from heap/GC pressure or thermal throttling. You cannot conclude B is faster just because it ran later.

**Fix principle:** multiple **independent JVM forks**, multiple measurements, and comparing result distributions. Keep the same JDK, flags, hardware, heap, inputs, power mode, and load environment. Alternate evaluation order across trials/series when comparing noisy systems.

### 4.5 Accidentally timing data creation and setup inside the main operation

```java
// Inappropriate if the goal is only lookup cost:
long t0 = System.nanoTime();
var data = new java.util.ArrayList<Integer>();
for (int i = 0; i < 100_000; i++) data.add(i);
boolean found = data.contains(99_999);
long elapsed = System.nanoTime() - t0;
```

This measurement includes allocation, boxing, list construction, and searching. **If the goal is the entire workflow**, that measurement may be valid; **if the goal is only `contains`**, prepare the data outside the measured region.

### 4.6 Confusing throughput, latency, and speedup

- **Throughput:** higher `ops/s` is usually better, provided each operation has the same meaning.
- **Average time:** lower `ns/op` or `µs/op` is usually better, provided the benchmark mode and units are compatible.
- **Latency tail (p95/p99):** essential when latency requirements exist; the average does not describe the tail of the distribution.
- **Speedup:** only meaningful when workload, machine conditions, data size, and measurement goals are equivalent; for concurrency, comparing total `ops/s` at 1 and 4 threads also depends on core count, contention, and saturation level.

Do not average "speedup ratios" across incompatible runs, and do not report performance with decimal precision beyond what the data and real variance support.

## 5. Using JMH for more accurate microbenchmarks

**JMH (Java Microbenchmark Harness)**, developed by OpenJDK, coordinates warm-up, measurement, JVM forking, return values/Blackhole, throughput and time modes, and thread count configuration. JMH **reduces many common errors**, but does not replace proper workload design and interpretation.

### 5.1 Creating a standalone benchmark project

You need a JDK and Maven with access to dependencies from Maven Central. In an **empty directory not inside another Maven project**, run:

```shell
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DgroupId=org.example -DartifactId=jvm-bench -Dversion=1.0-SNAPSHOT
```

This command uses the OpenJDK JMH archetype to generate a Maven configuration including the required **annotation processing** steps. Merely adding the `jmh-core` dependency without running the generator is not enough for a working JMH benchmark suite.

### 5.2 Benchmarking JIT with varying inputs and observable output

Place the file `jvm-bench/src/main/java/org/example/JitWarmupBenchmark.java`:

```java
package org.example;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class JitWarmupBenchmark {
    private long input = 1;

    @Benchmark
    public long mix() {
        long x = input++;
        for (int i = 0; i < 100; i++) {
            x = x * 1664525L + 1013904223L;
        }
        return x;
    }
}
```

Build and run commands:

```shell
cd jvm-bench
mvn clean verify
java -jar target/benchmarks.jar JitWarmupBenchmark
```

Explanation of each part:

- `@Benchmark` marks the method to be measured. It runs inside the auto-generated harness.
- `@State(Scope.Thread)` creates separate state for each benchmark thread. `input++` varies across invocations, reducing the risk of accidentally measuring a constant computation. This is still **part of the measured operation**, so you must account for it when drawing conclusions about `mix`.
- `return x` ensures the result is consumed by JMH using an appropriate mechanism, preventing the computation from being eliminated for lack of an observable result. For multiple outputs, JMH also provides `Blackhole.consume`.
- `@Warmup(iterations = 5, time = 1)`: five warm-up iterations, about one second each. Their results are excluded from the final measurement score.
- `@Measurement(iterations = 5, time = 1)`: five measurement iterations after warm-up in each fork.
- `@Fork(2)`: runs in two independent child JVMs to reduce dependence on the state of a single JVM process.
- `Mode.AverageTime` and `TimeUnit.NANOSECONDS`: reports average time per operation in `ns/op`.

**There is no fixed `ns/op` value** to compare against your machine: JMH must be run on the target environment, and results depend on CPU, JVM, and noise. The warm-up/fork parameters above are a starting point for experimentation, **not a guarantee** that the workload has stabilized. Inspect iteration-by-iteration progress, increase warm-up, or change the measurement setup if trends or high variance persist.

### 5.3 What is Blackhole for in JMH?

Suppose a benchmark computes two results:

```java
@Benchmark
public void twoResults(Blackhole blackhole) {
    blackhole.consume(calculate(inputA));
    blackhole.consume(calculate(inputB));
}
```

This is an **illustrative snippet inside a JMH class**, not a standalone Java file: it requires importing `org.openjdk.jmh.infra.Blackhole`, two inputs, and a `calculate` method. `Blackhole` makes results observable without console I/O. If a computation returns only **a single result**, simply `return` the value from the `@Benchmark` method; you do not need to add `Blackhole` to every method.

However, `Blackhole` also **cannot automatically fix** bad setup, measuring the same meaningless input repeatedly, or a benchmark that does not match reality.

## 6. JMH for concurrency: thread count and state determine conclusions

When a computation runs across multiple threads, you must distinguish **CPU capacity**, **synchronization cost**, **contention**, and **total throughput**. Two core JMH mechanisms:

- `@Threads(n)` or the CLI option `-t n` controls the number of benchmark worker threads.
- `@State(Scope.Thread)` gives each thread its own state; `@State(Scope.Benchmark)` creates shared state across workers of the same benchmark, suitable when you need to measure **real contention**.

The following example measures the throughput of an `AtomicLong` **shared** among benchmark threads:

Add `jvm-bench/src/main/java/org/example/SharedCounterBenchmark.java`:

```java
package org.example;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
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
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class SharedCounterBenchmark {
    private final AtomicLong counter = new AtomicLong();

    @Benchmark
    public long incrementShared() {
        return counter.incrementAndGet();
    }
}
```

Rebuild after adding the file, then measure two separate configurations:

```shell
mvn clean verify
java -jar target/benchmarks.jar SharedCounterBenchmark -t 1
java -jar target/benchmarks.jar SharedCounterBenchmark -t 4
```

Because of `@State(Scope.Benchmark)`, workers execute `incrementShared` on **the same `AtomicLong`** in each run. With multiple threads, atomic operations can contend on the same cache line. The `ops/s` result is the **total throughput** of the defined workload, not per-thread throughput.

Do not assume `-t 4` will quadruple throughput; the machine may lack cores, hit a bottleneck at CAS/cache coherence, experience clock scaling, or be affected by OS scheduling. If you change `Scope.Benchmark` to `Scope.Thread`, you are measuring **each thread having its own counter**, which is a completely different problem from contention. Never compare those two numbers as if they were the same workload.

### Concurrency-specific pitfalls

1. **Measuring a single worker and concluding for multiple workers:** fails to reproduce contention, lock convoys, or cache-line bouncing.
2. **Creating threads on every invocation when you only want to measure a concurrent operation:** the result becomes thread creation/submission/synchronization time for the whole workflow.
3. **Timing `executor.submit` without waiting for task completion:** measures only enqueueing/dispatching, not the work itself.
4. **Using `Thread.sleep` to "wait for tasks to finish":** easily under-waits or over-waits; to measure end-to-end, use `Future.get`, `CountDownLatch`, `Phaser`, or a reliable completion mechanism.
5. **Reading a shared counter unsafely:** code with data races can produce both wrong results and meaningless measurements; use synchronization/atomics matching the contract.
6. **Mixing logging, `println`, or unintended I/O into a critical section:** results become dominated by devices, buffers, and extra locks.
7. **Measuring uncontended `synchronized` and extrapolating to multi-threaded apps:** uncontended and contended paths behave differently.
8. **Using far more workers than cores and treating it as an algorithmic improvement:** you must clarify whether the workload is CPU-bound or blocking/I/O-bound.

For producer/consumer pipelines, queues, and backpressure, **JMH microbenchmarks only answer part of the question**. Also measure end-to-end throughput, queue depth, pending task count, p95/p99 latency, allocation/GC, CPU utilization, and error rates in a representative load test.

## 7. Designing controlled measurement experiments

A practical workflow for Java concurrency:

1. **State a clear hypothesis:** for example, "replacing a synchronized counter with `AtomicLong` increases throughput at four threads" or "a warm pool reduces first-task latency." Do not start by running a timer and then guessing what you measured.
2. **Choose the corresponding metric:** throughput, average time, tail latency, CPU time, allocation rate, GC pauses, or startup. Do not conflate them.
3. **Keep the workload realistic:** input data, read/write ratio, task duration distribution, contention level, producer/consumer count, queue size, and rate limits should match real conditions.
4. **Design setup cleanly:** initialize data and resources outside the measured region if they are not the target; keep them inside if they are what you need to evaluate.
5. **Distinguish cold and warm:** if optimizing cold-start, measure from a fresh process; if optimizing steady-state, warm up while checking stabilization behavior. Record HotSpot and JDK configuration.
6. **Run enough forks and iterations:** use JMH for small operations, inspect numbers across forks/iterations, and adjust durations; avoid trusting a single "pretty" run.
7. **Verify functional correctness:** outputs must be right, tasks must actually complete, and the optimizer must not have eliminated work or let tasks silently fail.
8. **Reduce environmental noise:** stabilize CPU governor/power plan when possible, limit background jobs, record hardware/cores/OS/JDK/flags/heap, and avoid comparing scores from differently configured machines.
9. **Verify causes with profilers/telemetry:** if you suspect JIT, check compilation; if you suspect GC, check GC logs/JFR; if you suspect contention, check thread dumps/JFR/lock events. Instrumentation also has overhead: run diagnostics separately when needed.
10. **Report with uncertainty:** document fork count, warm-up, measurement, threads, error/dispersion, data, and versions. Repeat before deciding on optimizations.

### Diagnostic interpretation table

| Observation | Valid conclusion? | What to check |
| --- | --- | --- |
| First round is slower than later rounds | Runtime state changed | Compilation, class initialization, caches, GC, CPU state |
| B is faster than A once | Not enough | Multiple forks, variance, run order, configuration |
| Throughput increases from 1 to 4 threads | May scale on that measured workload | Cores, contention, CPU, total ops/s, and correctness |
| Good average latency but bad p99 | Notable tail latency exists | Pauses, scheduling, contention, queues, GC |
| Very fast JMH score but app does not improve | Benchmark is unrepresentative | Real data, call paths, I/O, locks, allocations, and end-to-end |

## 8. Diagnostic tools and how to read metrics

**JMH:** a solid choice for comparing *microbenchmarks* after properly identifying the method/operation. Supports forking, warm-up, measurement, and thread counts; it does not by itself prove the benchmark represents a real service.

**JFR (Java Flight Recorder):** used when you need to observe allocations, GC, CPU, lock contention, and many runtime events in a realistic application. Example on a supported JDK:

```shell
java -XX:StartFlightRecording=filename=recording.jfr,duration=60s -jar your-app.jar
```

This is a **command template**; replace `your-app.jar` with your actual JAR. Running with JFR incurs some overhead; separate profiling runs from benchmark runs.

**HotSpot compilation log:** `-XX:+PrintCompilation` helps show which methods are compiled, though the number of log lines is not a score. For deeper investigation, you can explore JITWatch and tools for your JVM.

**GC log:** `-Xlog:gc` helps determine whether GC is occurring during the measurement window. Do not blame every "spike" on GC without evidence.

**Thread dump/CPU profiler:** helps locate `BLOCKED`, `WAITING`, lock ownership, contention, hot paths, and oversubscription. For CPU-bound workloads and `synchronized`/atomics, profilers and multi-thread-level measurements can be more meaningful than a few isolated nanoseconds.

A good benchmark should **explain why the numbers change**, not just pick the smallest number.

## 9. Misconceptions to eliminate

| Misconception | Correct understanding |
| --- | --- |
| "Running 100 times guarantees the JVM is warmed up" | JIT thresholds, profiles, class loading, and GC depend on workload and HotSpot version |
| "The last measurement is always the most reliable" | CPU throttling, GC, OS noise, or deoptimization can happen at any time |
| "`nanoTime` accurately measures a single instruction's time" | It measures elapsed time; overhead and optimizer effects can exceed the operation |
| "Writing the result to `volatile` makes a valid benchmark" | Observable results are necessary, but do not solve all optimizations and noise |
| "JMH always guarantees a valid microbenchmark" | JMH provides the harness; workload and design remain the author's responsibility |
| "Longer warm-up is always more accurate" | Warm-up must match the target state, but has costs and does not remove all noise |
| "Most threads is always fastest" | Scaling is bounded by cores, contention, memory bandwidth, and scheduling |
| "With `@Fork(2)`, you don't need to check variance" | Forking reduces single-process state bias, but you still must inspect dispersion and error |
| "JIT always makes code faster" | JIT usually optimizes, but also consumes CPU/memory to compile and can deoptimize |
| "Low `ns/op` means low production latency" | Production also involves networking, queueing, GC, locks, downstreams, and different data |

## 10. Knowledge self-check

**Q1. What is warm-up?** Running a workload before the measurement region to bring the runtime to a state relevant to the measurement goal. Do not skip startup if startup itself is what you are studying.

**Q2. Does running many times guarantee HotSpot has reached a steady state?** No. You must inspect iteration results, the environment, and when needed, compilation/GC.

**Q3. Why might you measure "0 ns" for a loop?** The compiler may eliminate unobservable computations, constant-fold, or optimize the loop; clock/timer overhead also makes single measurements meaningless.

**Q4. How do `@State(Scope.Thread)` and `@State(Scope.Benchmark)` differ?** One gives each worker its own state, while the other shares state across workers; this difference changes contention behavior.

**Q5. Is `@Warmup` included in the final JMH score?** No; it runs before measurement iterations. However, JIT/deoptimization and GC can still occur during measurement.

**Q6. What problem does `@Fork` solve?** It runs additional independent JVMs to reduce sharing optimized/initialized state from a single JVM; it does not create identical hardware environments.

**Q7. Why doesn't timing `submit()` measure task completion?** `submit` usually just accepts/enqueues the task and returns a `Future`, while the task may still be queued or running. You must measure until completion if the goal is end-to-end latency.

**Q8. When should you use JMH vs. a load test?** JMH fits small operations, API/method costs, or controlled contention patterns; load tests fit end-to-end latency/throughput/queues/backpressure on realistic workloads.

## 11. Pre-trust measurement checklist

- [ ] Measurement goal is defined: cold-start, steady-state, throughput, or latency.
- [ ] Java/JDK/HotSpot flags, CPU, cores, OS, heap, and workload are recorded.
- [ ] Operation output is observed, without dead-code elimination or altered semantics.
- [ ] Setup, data, allocation, and I/O are placed appropriately for the goal.
- [ ] Warm-up is sufficient and stability is checked; fixed iteration counts are not treated as dogma.
- [ ] Multiple iterations/forks are run and variance is evaluated, rather than cherry-picking the best run.
- [ ] Concurrency measures the right shared state, thread count, contention level, and task completion.
- [ ] Conclusions are separated from JIT, GC, cache, CPU, and scheduling effects when evidence is lacking.
- [ ] A/B comparisons use equivalent workloads and environments.
- [ ] Before production rollout, re-verify with profiling and end-to-end load testing.

### Official references

- [OpenJDK JMH — README, project creation, and running benchmarks](https://github.com/openjdk/jmh)
- [OpenJDK JMH Samples — examples of avoiding dead-code elimination with return/Blackhole](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java)
- [JDK 21 `java` launcher — `-XX:+PrintCompilation` and tiered compilation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [JDK 21 Java Flight Recorder API and guide](https://docs.oracle.com/en/java/javase/21/jfapi/)