# Amdahl's Law and Speedup Limits in Parallel Java Execution

## 1. Why Adding Threads Does Not Mean the Program Runs That Many Times Faster

A Java program may consist of independent segments that run concurrently, but it also has steps that **must be sequential**: preparing shared data, waiting for a required result from a previous step, merging results, operating on locked resources, or processing in a single place. The sequential portion does not disappear when we increase the number of workers.

**Amdahl's law** gives the ideal speedup limit for **the same fixed amount of work** when only a portion of the work can be executed in parallel. It is a tool for estimating the maximum benefit of increasing parallelism and deciding which part to optimize first.

For example, suppose a task takes 100 ms on one worker, consisting of:
- 20 ms that must be sequential;
- 80 ms that can be divided evenly across multiple workers.

With 4 workers, the new ideal time is `20 + 80 / 4 = 40 ms`, which is **2.5 times** faster, not 4 times. Even with infinite workers, the 20 ms portion still exists: the ideal limit is only **5 times**.

## 2. Formula, Notation, and Derivation

Let:

| Symbol | Meaning |
|---|---|
| `T(1)` | Baseline execution time with one processing unit, for a fixed workload. |
| `p` | **Proportion of baseline time** belonging to work that can be sped up by parallel execution, `0 ≤ p ≤ 1`. |
| `1 - p` | Proportion of time that must be sequential. |
| `N` | Number of effective parallel processing units in the ideal model, `N ≥ 1`. |
| `S(N)` | Speedup: `T(1) / T(N)`. |

If the sequential part takes `(1 - p) × T(1)`, and the parallelizable part takes `p × T(1) / N` under ideal conditions, then:

```text
T(N) = T(1) × [(1 - p) + p / N]

S(N) = T(1) / T(N)
     = 1 / [(1 - p) + p / N]
```

When `N` is very large, `p / N` approaches 0:

```text
S(max) = 1 / (1 - p)      if p < 1
```

With `p = 1`, the model has no sequential part left, so `S(N) = N`; this ideal model does not account for synchronization overhead, thread creation, scheduling, data transfer, or resource contention.

**Important:** `p` is the proportion of **baseline execution time** that can be sped up, not the proportion of lines of code, methods that can be called concurrently, existing threads, or CPU percentage shown in Task Manager. A short method called millions of times may account for most of the time; conversely, a long method rarely called may contribute very little.

### Hand-Calculated Example

Suppose `p = 0.90`, meaning 90% of the time is parallelizable and 10% is sequential.

| N (effective workers) | Sample formula | Ideal speedup | Efficiency per worker `E = S/N` |
|---:|---|---:|---:|
| 1 | `1 / (0.10 + 0.90)` | 1.000× | 100.0% |
| 2 | `1 / (0.10 + 0.90/2)` | 1.818× | 90.9% |
| 4 | `1 / (0.10 + 0.90/4)` | 3.077× | 76.9% |
| 8 | `1 / (0.10 + 0.90/8)` | 4.706× | 58.8% |
| 16 | `1 / (0.10 + 0.90/16)` | 6.400× | 40.0% |
| ∞ (limit) | `1 / 0.10` | 10.000× | Not applicable |

If `T(1) = 100 s`, then with 8 workers the ideal time is `100 × (0.10 + 0.90/8) = 21.25 s`, corresponding to `100 / 21.25 ≈ 4.706×`. Adding workers still improves performance, but **marginal returns diminish** because the 10 s sequential part does not decrease.

## 3. Differences Between Speedup, Efficiency, and Throughput

**Speedup** of a fixed piece of work:

```text
speedup = processing time with 1 worker / processing time with N workers
```

**Parallel efficiency** is `S(N)/N`, representing the relative utilization compared to ideal linear speedup `S(N)=N`. For example, if `S(8)=4.706`, the efficiency is `4.706/8≈58.8%`; this does not mean each CPU core is busy exactly 58.8% of the time.

**Throughput** is the number of tasks completed per second. If a program processes many independent requests concurrently, increasing the number of workers can increase throughput even when **the latency of a specific request remains almost unchanged**. Amdahl's law in the formula above describes the time of a **fixed workload**, and does not automatically predict throughput, queue wait time, or `p95/p99` tail latency.

To use the formula correctly, we must agree on what "one piece of work" is: a fixed batch, a fixed computation, or a fixed data processing run. You must not compare the time to process 10,000 records on one thread against 100,000 records on multiple threads and call that ratio Amdahl's speedup.

## 4. Java 17 Example: Computing the Ideal Limit

Save as `AmdahlCalculator.java`:

```java
import java.util.Locale;

public class AmdahlCalculator {
    static double speedup(double parallelFraction, int workers) {
        if (parallelFraction < 0 || parallelFraction > 1 || workers < 1) {
            throw new IllegalArgumentException("p must be 0..1 and N >= 1");
        }
        return 1.0 / ((1.0 - parallelFraction)
                + parallelFraction / workers);
    }

    public static void main(String[] args) {
        double p = 0.90;

        for (int n : new int[] { 1, 2, 4, 8, 16 }) {
            double s = speedup(p, n);
            System.out.printf(Locale.ROOT,
                    "N=%2d speedup=%.3f efficiency=%.3f%n",
                    n, s, s / n);
        }

        System.out.printf(Locale.ROOT,
                "Gioi han ly tuong: %.1fx%n", 1.0 / (1.0 - p));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac AmdahlCalculator.java
java AmdahlCalculator
```

Exact stdout:

```text
N= 1 speedup=1.000 efficiency=1.000
N= 2 speedup=1.818 efficiency=0.909
N= 4 speedup=3.077 efficiency=0.769
N= 8 speedup=4.706 efficiency=0.588
N=16 speedup=6.400 efficiency=0.400
Gioi han ly tuong: 10.0x
```

`Locale.ROOT` keeps the decimal separator in the output consistent (`.`), independent of the operating system locale. In the model, `N` is the number of workers that can actually compute in parallel; **`newFixedThreadPool(16)` does not guarantee 16 physical cores** or a corresponding speedup.

If `p=0.80`, the ideal ceiling is only `1/(1-0.80)=5×`. If `p=0.95`, the ceiling rises to `20×`, but with 8 workers the ideal speedup is still only `1/(0.05+0.95/8)≈5.926×`. Thus, improving the sequential portion or increasing the parallelizable fraction is sometimes more beneficial than adding workers.

## 5. Ideal Formula vs. Actual Execution Time

In a real program, the approximate execution time can be written as:

```text
T(N) ≈ Tserial + Tparallel / N + Toverhead(N)
```

`Toverhead(N)` is not necessarily constant and sometimes increases as the number of workers increases:

- **Thread creation and management:** thread initialization, context switching, scheduling, and task wake-up have costs.
- **Splitting/merging results:** task creation, queue submission, waiting on `Future`, `join()`, and merging or reducing data.
- **Synchronization:** `synchronized`, `Lock`, contention on counters/queues, and critical section contention.
- **Memory and cache:** RAM bandwidth limits, cache coherence, false sharing, and cache misses; more cores do not create infinite memory bandwidth.
- **Hardware limits:** number of physical cores, SMT/hyper-threading, other processes, power-saving modes, and thermal throttling.
- **GC and allocation:** allocating many intermediate objects or increasing the live set can cause GC pressure.
- **Data dependencies:** one task must wait for another task's result; simply splitting into more tasks does not make them usefully concurrent.

A realistic scenario: a computation finishes in 100 ms with one worker, with an ideal parallel fraction of 90%. With 8 workers, Amdahl predicts 21.25 ms. If scheduling, locking, and merging add 8 ms, the time could be `29.25 ms`, giving a speedup of only `100 / 29.25 ≈ 3.419×`. That is why ideal numbers should not be treated as a performance guarantee.

Amdahl's law **is not a law that forbids any speedup from exceeding the predicted number** when a real program changes algorithms, uses the cache better, or runs a different workload; those situations change the assumptions of the original model. If measurements exceed predictions, check your assumptions and measurement methodology rather than concluding that Java "violates" Amdahl's law.

## 6. Java 17 Example: Splitting a Fixed Workload Across ExecutorService

The snippet below demonstrates how to split **the same CPU-bound computation** into non-overlapping ranges. It verifies the result is correct before discussing speed, because speeding up by skipping elements is invalid.

Save as `FixedWorkDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class FixedWorkDemo {
    private static long calculate(int fromInclusive, int toExclusive) {
        long sum = 0;
        for (int i = fromInclusive; i < toExclusive; i++) {
            long value = i % 997L;
            sum += (value * value + 7L * value) % 1009L;
        }
        return sum;
    }

    public static void main(String[] args) throws Exception {
        final int items = 8_000_000;
        final int workers = Math.min(4,
                Math.max(1, Runtime.getRuntime().availableProcessors()));

        long sequential = calculate(0, items);
        ExecutorService executor = Executors.newFixedThreadPool(workers);

        try {
            List<Future<Long>> results = new ArrayList<>();

            for (int part = 0; part < workers; part++) {
                int from = (int) ((long) part * items / workers);
                int to = (int) ((long) (part + 1) * items / workers);
                results.add(executor.submit(() -> calculate(from, to)));
            }

            long parallel = 0;
            for (Future<Long> result : results) {
                parallel += result.get();
            }

            System.out.println("Ket qua bang nhau: " + (sequential == parallel));
            System.out.println("So worker hop le: "
                    + (workers >= 1 && workers <= 4));
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(1, TimeUnit.MINUTES)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Run:

```bash
javac FixedWorkDemo.java
java FixedWorkDemo
```

Stdout (independent of the number of CPUs reported by the JVM):

```text
Ket qua bang nhau: true
So worker hop le: true
```

Explanation:
1. `calculate(0, items)` is the sequential baseline, using the same computation algorithm as each task.
2. `[0, items)` is divided into `workers` contiguous, non-overlapping ranges covering all data; intermediate values are cast to `long` to avoid overflow when multiplying the index.
3. `submit` returns a `Future<Long>`; `get()` waits for the task to complete and sums the results, forming a sequential result-merging phase.
4. The thread pool is shut down with `shutdown()` after use; Java 17 does not require and does not use `try-with-resources` for `ExecutorService`.

This example **demonstrates correct work partitioning**; it does not by itself prove a speedup. For a small number of items, task and scheduling overhead may exceed the time saved.

### Measuring Empirical Speedup Within the Right Scope

You can measure time using `System.nanoTime()` before/after the sequential section and before/after the parallel section, then compute `speedupObserved = elapsedSequential / elapsedParallel`. However, measuring only once, always running the baseline before the parallel run, or including pool creation time on only one side can easily lead to wrong conclusions.

To benchmark more fairly:
- Use **the same data, algorithm, and output** with equivalent resources; clearly decide whether startup/pool creation is included in the measurement.
- Warm up so JIT compilation and class loading have less impact; measure multiple iterations across multiple forks, observing the distribution rather than trusting a single random run.
- Prevent dead-code elimination and constant folding; ensure the results are actually used/checked.
- Control CPU frequency, allocated cores, background load, heap, and GC; record the exact JDK/JVM version.
- For Java microbenchmarks, consider **JMH (Java Microbenchmark Harness)** instead of writing a custom timing loop that is prone to error. For an entire pipeline, measure end-to-end at realistic workload levels, including sequential and waiting parts.

You cannot infer `p` simply by counting tasks or threads. You can use a profiler, JFR (Java Flight Recorder), thread dumps, and CPU profiling to find where time is spent, then re-measure after making changes. Aggregate measurements can be used to check model fit, but the resulting `p` is only an estimate dependent on the workload and environment.

## 7. Using Amdahl's Law for Engineering Decisions

### Case A: Adding Workers When the Sequential Part Is Still Large

`T(1)=100 ms`, of which 30 ms must be sequential. With `p=0.70`:

```text
N=2  -> T=30+70/2   = 65.00 ms -> S≈1.538x
N=4  -> T=30+70/4   = 47.50 ms -> S≈2.105x
N=8  -> T=30+70/8   = 38.75 ms -> S≈2.581x
N=∞  -> T approaches 30 ms     -> ceiling S≈3.333x
```

If the goal is to be at least 4 times faster for the same work, simply adding workers **cannot achieve the goal within the model**. You must reduce the sequential part, change the algorithm, or change the problem constraints.

### Case B: Optimizing the Sequential Part First

Suppose a 100 ms baseline consists of 20 ms serial and 80 ms parallelizable. With 8 workers: `T(8)=20+80/8=30 ms` (3.333×). If you optimize the serial step from 20 ms down to 5 ms while keeping the 80 ms parallel part, the total time with 8 workers becomes `5+80/8=15 ms`. Compared to the **original** 100 ms baseline, this is 6.667×. However, after changing the code, the percentage `p` relative to the new baseline has changed; you must not keep plugging `p=0.80` into every calculation as if nothing changed.

### Case C: Increasing N Increases Contention

Suppose with 4 workers, `T=40 ms`, but 8 workers cause lock/contention and merging to add 20 ms. Even though the ideal divided part shrinks, the actual `T(8)` may be **greater than 40 ms**. You need to find hot locks, reduce shared mutable state, avoid overly small tasks, use appropriate data structures, or reduce the number of workers. Increasing N when the workload has already saturated memory bandwidth usually does not help.

### Case D: I/O-Bound Workloads

Tasks waiting on network/disk can benefit from concurrency by **hiding wait time**, increasing concurrent requests or throughput. However, the speed of processing a single request still depends on external services and connection limits. Do not treat `N` in the formula as an arbitrary number of threads and conclude that a single request will speed up proportionally. To apply Amdahl's model, you must identify the part that can actually overlap or run in parallel, with the same workload and resources.

## 8. Distinguishing Amdahl's Law from Scaling the Workload

Amdahl's law here assumes a **fixed-size workload / strong scaling**: increasing resources while keeping the problem size constant. **Weak scaling**, by contrast, increases the amount of work along with resources, for example each core still processes a fixed partition. When the workload changes, the evaluation differs, and you can use a Gustafson-style perspective to ask: "in the same amount of time, how much larger a problem can be processed?"

Therefore, state the goal clearly before saying something "scales well":
- Reducing latency to complete **a fixed batch**? Measure strong-scaling speedup and compare against Amdahl.
- Increasing throughput for **many independent tasks**? Measure tasks/s, latency, queue length, and resource saturation.
- Processing a larger dataset in **the same amount of time**? Measure weak scaling; do not plug the times of two different datasets directly into Amdahl's `S(N)=T(1)/T(N)`.

## 9. Common Misconceptions and Pitfalls

| Misconception | What to do instead |
|---|---|
| "With 8 threads, the maximum speedup must be 8×." | Determine `p`, physical cores, overhead, and contention; 8× is only a special ideal case. |
| "90% of the code can run in parallel, so p=0.90." | Measure **execution time**, do not count lines of code. |
| "N is the number of threads created." | In the model, `N` is the effective parallel processing capacity, which cannot exceed hardware and workload limits. |
| "Amdahl predicts exact runtime on every machine." | It is an ideal bound/estimate under fixed assumptions; measure actual overhead and load. |
| "For CPU-bound work, the more tasks the better." | Tasks that are too small incur high overhead; choose a sufficiently large task size and measure. |
| "A 4× speedup means every request's throughput is also 4×." | Fixed-workload latency, throughput, and concurrency are different metrics. |
| "After optimizing the algorithm, keep using the old p." | Whenever structure or workload changes, re-measure the baseline and time proportions. |

## 10. Self-Check Exercises

**Exercise 1.** A computation has `p=0.75`. With 4 effective workers, what is the ideal speedup? What is the ceiling when N is very large?

```text
S(4) = 1 / (0.25 + 0.75/4)
     = 1 / 0.4375
     ≈ 2.286x

S(max) = 1 / 0.25 = 4x
```

**Exercise 2.** A batch runs sequentially in 200 ms, consisting of 40 ms serial and 160 ms parallelizable. With 8 workers and 10 ms overhead, what are the modeled actual time and speedup?

```text
T(8) = 40 + 160/8 + 10 = 70 ms
Speedup = 200/70 ≈ 2.857x
```

Even without overhead, the ideal result is only `200/60≈3.333×`; you cannot assume 8×.

**Exercise 3.** When increasing workers from 4 to 16, throughput increases while per-request latency stays unchanged. Does this contradict Amdahl's law? **No**. The system may be serving multiple independent requests concurrently; distinguish system-wide throughput from the runtime of a single request.

**Exercise 4.** A program measures slower with 16 workers than with 8 workers. Should we create 32 threads? **There is no basis for doing so**. First profile CPU, locks, queues, cache/memory, and GC; check whether tasks are too small or exceed the effective core count.

## 11. Practical Summary

Amdahl's law answers the question: **given a fixed amount of work and a remaining fraction of time that cannot be parallelized, how much faster can adding workers make it under ideal conditions?**

```text
Ideal speedup:   S(N) = 1 / [(1 - p) + p/N]
Ceiling (p < 1): S(max) = 1 / (1 - p)
Efficiency:      E(N) = S(N) / N
```

When optimizing Java concurrency, define the workload, measure the baseline, find the sequential/critical path, choose a parallelism level suited to the cores and synchronization cost, and benchmark end-to-end. **Reducing the serial portion and overhead is often as important as, or more important than, adding threads.**

### References

- [Java SE 17 — `ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): executor lifecycle and waiting for completion.
- [Java SE 17 — `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): retrieving and waiting for task results.
- [Java SE 17 — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): elapsed-time clock.
- [OpenJDK — JMH](https://openjdk.org/projects/code-tools/jmh/): microbenchmarking tool for the JVM.
