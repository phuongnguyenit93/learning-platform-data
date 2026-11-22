# Comparing Performance Before and After Optimization

Comparing performance before and after optimization determines whether a code or configuration change actually improves the system. A reliable process must measure the same work under equivalent conditions, verify that business results remain unchanged, collect enough runs, and check other metrics that might be affected.

Do not draw conclusions from a single run or look at only one timing number. A change might make a method faster while increasing allocation, memory usage, CPU contention, error rate, or service p99 latency. Therefore, you should combine benchmarks, load tests, JFR, and application metrics depending on the level being compared.

## 1. Define Exactly What to Compare

Before measuring, clearly write down the question and the scope of the change.

Examples:

- Is a new method faster than the old method?
- Does replacing `ArrayList` with `HashSet` reduce lookup time?
- Does a new heap configuration reduce GC pauses?
- Does a new service version increase throughput while maintaining p95/p99 latency?
- Does a database query change reduce request processing time?
- Does a new build reduce CPU or memory usage on the same workload?

Each question requires an appropriate type of measurement.

| Scope | Question | Appropriate Tool |
|---|---|---|
| A small method | Which method is faster? | JMH |
| A code block in an application | How much time elapsed? | System.nanoTime() |
| A running JVM | How do CPU, GC, allocation, or I/O change? | JFR/JMC |
| A single request | How does end-to-end latency change? | Application metrics, tracing |
| Entire service under load | How do throughput, p95/p99, and error rate change? | Load test |
| A process/container | How do CPU, RSS, and memory limits change? | OS/container metrics |

Do not use microbenchmarks as a substitute for load tests. A faster method does not guarantee the service can handle more requests if the bottleneck lies in the database, network, locks, or queues.

## 2. Establish a Baseline Before Making Changes

A **baseline** is the reference data collected from the current version prior to optimization. Without a reliable baseline, you cannot determine the actual improvement.

A good baseline should record:

- Running commit, build number, or version.
- JDK vendor and version.
- JVM flags, heap size, and garbage collector.
- CPU, RAM, OS, and container limits.
- Dataset and input parameters.
- Thread count, concurrency, and request rate.
- Warm-up duration and measurement duration.
- Number of runs, forks, and benchmark settings.
- Throughput, latency, CPU, memory, allocation, GC, and error rate.
- Execution time and background tasks that might interfere.

### Keep Comparison Conditions Constant

When comparing before and after, factors outside the change under test must be kept stable:

- Same hardware or equivalent instance.
- Same JDK vendor/version and JVM flags.
- Same heap size and GC configuration.
- Same input, dataset, and data distribution.
- Same concurrency and workload arrival rate.
- Same cache state: cold vs. cold, warm vs. warm.
- Same database snapshot or data with an equivalent distribution.
- Same network path and dependencies.
- Same warm-up and measurement durations.

If you change the JDK, GC, heap, and code simultaneously, you cannot tell which factor caused the difference.

### Verify the Baseline Is Representative

Do not pick an anomalous time window as a baseline. Choose a workload that reflects real-world behavior, including common cases and expensive inputs.

For a service, this should include:

- Request mix at proportions close to production.
- Small, medium, and large payload sizes.
- Peak and steady-state traffic.
- Commonly used dependencies.
- Error and retry behavior if they are part of the workload.

## 3. Verify Correctness Before Measuring Performance

A version that runs faster but returns wrong results is not a successful optimization.

Before comparing:

1. Run unit tests and integration tests.
2. Confirm that the baseline and candidate produce the same results for the same inputs.
3. Check edge cases, `null`, empty inputs, and large datasets.
4. Check ordering, precision, rounding, and exception behavior where relevant.
5. Verify transactions, resource cleanup, and concurrency semantics.
6. Run correctness tests before performance tests.

For replacement algorithms, verify matching outputs across many inputs, not just one small example.

Never skip correctness just because a benchmark shows a large speedup.

## 4. Choose the Right Metrics

No single metric fully describes performance.

| Metric | Meaning | When to Observe |
|---|---|---|
| Latency | Time to complete an operation/request | How long users have to wait |
| Throughput | Number of operations/requests completed per unit of time | How much work the system processes |
| p50 | Median latency | Typical request experience |
| p95 | 95% of requests complete within this time or less | Latency of slower requests |
| p99 | 99% of requests complete within this time or less | Tail latency |
| Error rate | Percentage of failed requests | Stability and correctness |
| CPU utilization | CPU usage level | Processing cost |
| Heap/Process memory | Heap or total process memory | Memory pressure |
| Allocation rate | Amount of objects/memory allocated per second | GC pressure |
| GC pause/time | Duration and frequency of GC | Impact on latency |
| I/O latency | Duration of file/socket operations | Storage/network bottlenecks |
| Queue depth | Number of pending tasks | Saturation and backpressure |

### Average Latency Is Not Enough

Suppose before optimization p50 = 40 ms, p95 = 100 ms, and p99 = 250 ms. After optimization, p50 drops to 30 ms, but p99 increases to 500 ms.

The average or median may look better while a group of users suffers severe tail latency. Therefore, inspect at least p50, p95, p99, and error rate for services.

### Throughput Must Be Evaluated Alongside Latency

A service can increase throughput by increasing concurrency while simultaneously lengthening queues and increasing p99 latency. Do not treat higher throughput as an improvement if latency or error rate violates the SLO.

## 5. Before-and-After Comparison Formulas

Let:

- **Before:** baseline result.
- **After:** result after the change.

### Latency Reduction Percentage

For latency, lower values are usually better:

\[
\text{Latency reduction (\%)} =
\frac{\text{Before} - \text{After}}{\text{Before}} \times 100
\]

Example: average latency drops from 100 ms to 80 ms:

\[
\frac{100-80}{100}\times100=20\%
\]

Latency is reduced by 20%.

If the result is negative, latency has increased. Do not flip the sign or interpret a negative number as an improvement.

### Speedup Ratio

\[
\text{Speedup} = \frac{\text{Before time}}{\text{After time}}
\]

If before took 100 ms and after took 50 ms, speedup = 2x. The new operation is twice as fast according to the measured metric.

Speedup is not the same as latency reduction percentage: a 2x speedup corresponds to a 50% reduction in time.

### Throughput Improvement Percentage

For throughput, higher values are usually better:

\[
\text{Throughput improvement (\%)} =
\frac{\text{After} - \text{Before}}{\text{Before}} \times 100
\]

If throughput increases from 1,000 to 1,200 requests/s:

\[
\frac{1200-1000}{1000}\times100=20\%
\]

Throughput increased by 20%.

### Resource Comparison

A similar formula can be used to calculate CPU or memory reduction:

\[
\text{Resource reduction (\%)} =
\frac{\text{Before} - \text{After}}{\text{Before}} \times 100
\]

Always specify the unit, scope, and measurement conditions. CPU percentage of a single core, CPU of the entire process, and CPU of the whole container are not the same metric.

## 6. Do Not Rely on a Single Run

Performance results contain noise from:

- JIT compilation and warm-up.
- Class loading and initialization.
- Garbage collection.
- OS scheduling.
- CPU frequency scaling and thermal throttling.
- Background processes.
- Container CPU throttling.
- Cache state.
- Network and database variability.
- Thread contention.

A faster single run might just be luck.

### Run Multiple Times and Inspect the Distribution

For small benchmarks, use multiple measurement iterations and multiple forks. For load tests, repeat independent runs and compare latency distributions.

Commonly used statistics:

- Mean: average value.
- Median: middle value after sorting.
- Standard deviation: spread around the mean.
- Percentiles: p50, p90, p95, p99.
- Confidence interval: reliability range of an estimate.
- JMH error: error margin reported alongside the score.

Do not pick only the best result. Report the number of runs, spread, and confidence interval when possible.

### Execution Order Can Introduce Bias

If you always run the baseline first and the candidate second, the candidate might benefit from a warm cache or warmed-up JIT. Conversely, the candidate might encounter different background load.

You can alternate the execution order, for example:

~~~text
Run 1: Baseline -> Candidate
Run 2: Candidate -> Baseline
Run 3: Baseline -> Candidate
Run 4: Candidate -> Baseline
~~~

For critical benchmarks, JMH forks create independent JVM processes and help reduce state interference from previous runs.

### Compare Confidence Intervals

If the error margins of two results overlap significantly, there is not enough evidence to claim the change provides a real improvement. Increase the number of runs, reduce noise, or use a better experimental design.

Do not claim a 1% change is significant if the natural variance of the benchmark is also around 5%.

## 7. Java 17+ Example: Comparing List Lookup vs. HashSet Lookup

This example compares two ways of checking whether a value exists in a dataset:

- **Baseline:** using `ArrayList.contains()`, linear search.
- **Candidate:** using `HashSet.contains()`, hash-based lookup.

The dataset and queries are created outside the measurement region. Both implementations receive the same queries and must return the same number of matches. The program warms up first, measures multiple rounds, alternates execution order, and compares medians.

This is a controlled demonstration, not a replacement for JMH.

Create the file **BeforeAfterDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.Arrays;

public final class BeforeAfterDemo {
    private static volatile int sink;

    private static int countLinear(
            List<Integer> values, int[] queries) {
        int matches = 0;

        for (int query : queries) {
            if (values.contains(query)) {
                matches++;
            }
        }

        return matches;
    }

    private static int countHashed(
            Set<Integer> values, int[] queries) {
        int matches = 0;

        for (int query : queries) {
            if (values.contains(query)) {
                matches++;
            }
        }

        return matches;
    }

    private static double medianMillis(long[] nanos) {
        long[] sorted = nanos.clone();
        Arrays.sort(sorted);

        return sorted[sorted.length / 2] / 1_000_000.0;
    }

    public static void main(String[] args) {
        final int dataSize = 5_000;
        final int queryCount = 2_000;
        final int warmupIterations = 3;
        final int measurementIterations = 7;

        List<Integer> list = new ArrayList<>(dataSize);
        Set<Integer> set = new HashSet<>(dataSize * 2);

        for (int i = 0; i < dataSize; i++) {
            list.add(i);
            set.add(i);
        }

        int[] queries = new int[queryCount];

        for (int i = 0; i < queryCount; i++) {
            queries[i] = (i * 31) % (dataSize * 2);
        }

        for (int i = 0; i < warmupIterations; i++) {
            sink = countLinear(list, queries);
            sink = countHashed(set, queries);
        }

        long[] linearTimes = new long[measurementIterations];
        long[] hashedTimes = new long[measurementIterations];
        int expectedMatches = countLinear(list, queries);

        for (int i = 0; i < measurementIterations; i++) {
            int linearResult;
            int hashedResult;

            if (i % 2 == 0) {
                long start = System.nanoTime();
                linearResult = countLinear(list, queries);
                linearTimes[i] = System.nanoTime() - start;

                start = System.nanoTime();
                hashedResult = countHashed(set, queries);
                hashedTimes[i] = System.nanoTime() - start;
            } else {
                long start = System.nanoTime();
                hashedResult = countHashed(set, queries);
                hashedTimes[i] = System.nanoTime() - start;

                start = System.nanoTime();
                linearResult = countLinear(list, queries);
                linearTimes[i] = System.nanoTime() - start;
            }

            if (linearResult != expectedMatches
                    || hashedResult != expectedMatches) {
                throw new IllegalStateException(
                        "Implementations returned different results");
            }

            sink = linearResult + hashedResult;
        }

        double linearMedian = medianMillis(linearTimes);
        double hashedMedian = medianMillis(hashedTimes);

        System.out.println("Matches per run: " + expectedMatches);
        System.out.println("Correctness: PASS");
        System.out.printf(
                Locale.ROOT,
                "Median baseline: %.3f ms%n",
                linearMedian);
        System.out.printf(
                Locale.ROOT,
                "Median optimized: %.3f ms%n",
                hashedMedian);
        System.out.printf(
                Locale.ROOT,
                "Median speedup: %.2fx%n",
                linearMedian / hashedMedian);
    }
}
~~~

Compile with Java 17 or later:

~~~bash
javac --release 17 BeforeAfterDemo.java
~~~

Run:

~~~bash
java BeforeAfterDemo
~~~

Deterministic output:

~~~text
Matches per run: 1033
Correctness: PASS
~~~

The three timing lines have the format:

~~~text
Median baseline: <varies> ms
Median optimized: <varies> ms
Median speedup: <varies>x
~~~

Timings vary depending on CPU, JDK, OS, and background load. In one test run using OpenJDK 24.0.2, the program produced a median baseline of 3.393 ms, median optimized of 0.074 ms, and speedup of 46.16x. This is only the result of a specific test environment, not a performance guarantee for all machines.

### Explaining the Results

`List.contains()` has linear search cost proportional to the number of elements. `HashSet.contains()` has an average complexity close to O(1) when the hash distribution is suitable, though it uses more memory and can be affected by hash collisions.

This illustrative example fixes the dataset, query distribution, and number of iterations. In a real application, you also need to measure `HashSet` creation cost, memory footprint, data updates, and concurrency if those costs are part of the business workload.

## 8. Use JMH for Serious Implementation Comparisons

JMH is suitable when comparing small methods or algorithms. It manages warm-up, measurement, forks, state, and result consumption to avoid common pitfalls of hand-rolled benchmarks.

Example benchmark with the same dataset and queries for both implementations:

~~~java
package org.example;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class LookupComparison {
    @Param({"1000", "5000", "20000"})
    public int size;

    private List<Integer> list;
    private Set<Integer> set;
    private int[] queries;

    @Setup(Level.Trial)
    public void setup() {
        list = new ArrayList<>(size);
        set = new HashSet<>(size * 2);

        for (int i = 0; i < size; i++) {
            list.add(i);
            set.add(i);
        }

        queries = new int[2000];

        for (int i = 0; i < queries.length; i++) {
            queries[i] = (i * 31) % (size * 2);
        }
    }

    @Benchmark
    public int baselineListContains() {
        int matches = 0;

        for (int query : queries) {
            if (list.contains(query)) {
                matches++;
            }
        }

        return matches;
    }

    @Benchmark
    public int candidateHashSetContains() {
        int matches = 0;

        for (int query : queries) {
            if (set.contains(query)) {
                matches++;
            }
        }

        return matches;
    }
}
~~~

In the example, `@Setup(Level.Trial)` prepares the data before the benchmark. Both methods return the match count so JMH consumes the result.

### Minimal Maven Configuration

Add JMH 1.37 and the annotation processor to `pom.xml`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.openjdk.jmh</groupId>
        <artifactId>jmh-core</artifactId>
        <version>1.37</version>
    </dependency>
    <dependency>
        <groupId>org.openjdk.jmh</groupId>
        <artifactId>jmh-generator-annprocess</artifactId>
        <version>1.37</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
~~~

Configure compiler release 17 and the corresponding annotation processor; use the Maven Shade Plugin with main class `org.openjdk.jmh.Main` to build an executable benchmark JAR. You can also use the official JMH archetype to initialize the project.

Run the benchmark:

~~~bash
mvn clean package
java -jar target/benchmarks.jar LookupComparison
~~~

Save JSON results:

~~~bash
java -jar target/benchmarks.jar LookupComparison -rf json -rff comparison.json
~~~

Try adding the allocation profiler:

~~~bash
java -jar target/benchmarks.jar LookupComparison -prof gc
~~~

### Reading Results

JMH displays the benchmark name, mode, count, score, error, and unit. For `AverageTime`, a lower score is better. For `Throughput`, a higher score is better.

Compare:

- Same input size.
- Same mode and output unit.
- Same warm-up, measurement, and fork settings.
- Score along with error.
- Allocation and GC when using `-prof gc`.
- Results across multiple forks.

Do not compare `AverageTime` of one version with `Throughput` of another. Do not change the benchmark configuration between two versions and attribute the entire difference to the code.

## 9. Compare Services with Load Tests

A method benchmark cannot simulate an entire service. To compare before and after deployment, run the same workload against both versions in equivalent environments.

### Steps

1. Deploy the baseline to the benchmark environment.
2. Deploy the candidate to an equivalent environment.
3. Use the same dataset, request mix, and concurrency.
4. Warm up both versions.
5. Run the load test for the same duration.
6. Collect throughput, p50, p95, p99, error rate, and resource usage.
7. Repeat across multiple runs.
8. Compare distributions and confidence intervals.
9. Check for regressions in individual endpoints or workloads.
10. Conclude an improvement only when it exceeds the noise level and does not violate SLOs.

### Example Results Table

The table below uses hypothetical data to illustrate how to present results:

| Metric | Before | After | Notes |
|---|---:|---:|---|
| Throughput | 1,000 req/s | 1,180 req/s | +18% |
| p50 latency | 40 ms | 35 ms | -12.5% |
| p95 latency | 110 ms | 90 ms | -18.2% |
| p99 latency | 260 ms | 240 ms | -7.7% |
| Error rate | 0.10% | 0.08% | Decreased |
| CPU | 75% | 82% | Higher CPU cost |
| Memory | 1.8 GB | 2.0 GB | +0.2 GB |

In this example, throughput and latency improved, but CPU and memory increased. You need to review resource limits, headroom, and operational costs before deciding to roll out.

## 10. Use JFR to Explain Why Results Changed

JFR helps diagnose differences between the baseline and candidate. Record sessions under the same workload, duration, and settings.

Start recording:

~~~bash
jcmd <pid> JFR.start name=before settings=profile duration=60s filename=before.jfr
~~~

After deploying the candidate, take an equivalent recording:

~~~bash
jcmd <pid> JFR.start name=after settings=profile duration=60s filename=after.jfr
~~~

View the summary:

~~~bash
jfr summary before.jfr
jfr summary after.jfr
~~~

Open both files in JDK Mission Control and compare:

- CPU hot methods and execution samples.
- Allocation rate and object allocation.
- Garbage collection count, pause duration, and total time.
- File/socket I/O duration.
- Lock contention and thread parking.
- Thread CPU load.
- JIT compilation and class loading.

The `profile` settings collect more data than `default` settings and incur higher overhead. Keep the configuration identical between both recordings and avoid comparing a `profile` recording against a `default` recording.

JFR explains JVM behavior; it does not replace load tests or application-level latency metrics.

## 11. Distinguish Real Improvements from Noise

A small change may fall within the natural variance range.

Example:

| Run | Before | After |
|---|---:|---:|
| 1 | 10.2 ms | 9.8 ms |
| 2 | 9.7 ms | 10.0 ms |
| 3 | 10.1 ms | 9.9 ms |
| 4 | 9.9 ms | 9.7 ms |
| 5 | 10.3 ms | 10.1 ms |

The numbers above are hypothetical examples. The candidate appears slightly faster, but the spread may be larger than the difference. More runs or JMH are needed to evaluate error and confidence intervals.

### When Results Are Unstable

Check:

- Is CPU being contended for by other processes?
- Is there thermal throttling or power saving active?
- Is the container experiencing CPU throttling?
- Does GC occur at different times?
- Is the cache in the same state?
- Does the input have the same distribution?
- Is the database or remote dependency fluctuating?
- Are background jobs running intermittently?
- Is the number of samples/iterations sufficient?

If noise is high, improve the measurement setup before drawing conclusions about the code.

## 12. Common Mistakes

### Measuring Only Once Before and Once After

A single run is easily skewed by JIT, GC, cache, and OS scheduling. Run multiple iterations and forks.

### Looking Only at Average Latency

The average can improve while p99 degrades. Inspect percentiles and error rates.

### Looking Only at Throughput

Higher throughput can come from longer queues, higher concurrency, or increased latency. Evaluate latency and SLOs simultaneously.

### Changing Multiple Factors at Once

If you change code, JDK, heap, and GC together, you cannot attribute the cause to a single change. Change one factor at a time or use a controlled experimental design.

### Comparing a Cold Cache with a Warm Cache

The candidate might benefit from an already-warmed cache. Clearly define cold-start vs. steady-state and apply the same condition to both.

### Using Non-Representative Benchmarks

A small method benchmark may not reflect production allocation, I/O, locks, or request mix. Use load tests for services.

### Optimizing Only the Top Method in a Profiler

A hot method might be a library function called frequently by a caller. Inspect the call tree and workload before making edits.

### Ignoring Setup Costs

If the candidate needs to build a cache or `HashSet` before each operation, but the benchmark excludes setup from the measured region, the results are only valid if that structure is reused in practice.

### Reporting Speedup Without Stating Conditions

Always record the JDK, CPU, input, warm-up, iterations, forks, mode, and units. Never publish a speedup number detached from its measurement environment.

## 13. Using Results in Rollout Decisions

After benchmarking and load testing, decide whether the candidate is safe enough to roll out.

### Canary or Gradual Rollout

When possible, deploy the candidate to a small percentage of traffic first. Compare at the same time and under the same request mix to detect regressions.

Monitor:

- Error rate.
- p50/p95/p99 latency.
- Throughput.
- CPU and memory.
- GC pauses.
- Saturation of thread pools, connection pools, and queues.
- Critical endpoints.

Set rollback thresholds before deployment. If the candidate violates SLOs or causes an error spike, halt the rollout and revert to the baseline according to procedure.

### Check for Regressions Outside the Optimization Scope

A change might improve endpoint A while slowing down endpoint B. Test different request groups and the entire service.

Do not measure only the modified code path; verify there are no regressions in related workloads.

### Store Comparison Evidence

A performance report should record:

- Baseline and candidate versions/commits.
- Goal of the change.
- Environment and configuration.
- Workload and inputs.
- Tools, settings, and measurement duration.
- Number of runs and aggregation method.
- Before/after metrics table.
- Confidence/error or spread.
- Correctness results.
- Regressions and trade-offs.
- Conclusion and rollout conditions.

## 14. Complete Before-and-After Comparison Workflow

1. Define the optimization goal and primary metrics.
2. Choose the tool by level: `nanoTime`, JMH, JFR, or load test.
3. Record baseline version, JDK, JVM flags, and environment.
4. Prepare a representative dataset and workload.
5. Run correctness tests for both baseline and candidate.
6. Warm up both versions in the same way.
7. Run multiple measurement iterations or load-test runs.
8. Alternate execution order or use independent forks to reduce bias.
9. Collect latency, throughput, percentiles, error rate, and resource usage.
10. Use JFR to explain CPU, GC, I/O, allocation, and locks.
11. Calculate improvement percentage and speedup using the right metrics.
12. Evaluate spread and statistical significance.
13. Check memory, CPU, and other endpoints for regressions.
14. Save the report along with configuration and evidence.
15. Perform a canary/gradual rollout and monitor SLOs.
16. Keep the candidate when improvements are repeatable and meet quality requirements.

## 15. Checklist Before Claiming an Improvement

- [ ] Correctness of both baseline and candidate is verified.
- [ ] Baseline was established before the change.
- [ ] Same JDK, JVM flags, and hardware.
- [ ] Same dataset, inputs, and request mix.
- [ ] Same warm-up, measurement, and concurrency.
- [ ] Sufficient iterations/forks/runs.
- [ ] Best result was not cherry-picked.
- [ ] Appropriate mean/median and percentiles are included.
- [ ] Error or confidence interval is included when needed.
- [ ] Latency and throughput are evaluated together.
- [ ] Error rate and SLOs did not degrade.
- [ ] CPU, memory, allocation, and GC were checked.
- [ ] Other workloads were checked for regressions.
- [ ] JFR recordings used identical settings if compared.
- [ ] Environment, versions, and commands are recorded.
- [ ] A rollout/rollback plan is in place if deploying to production.

## 16. Key Terms to Remember

| Term | Meaning |
|---|---|
| Baseline | Reference results before a change |
| Candidate | Version or approach being evaluated |
| Before/After | Metrics before and after a change |
| Benchmark | Controlled measurement for a workload |
| JMH | Java Microbenchmark Harness |
| Load test | Testing a service under defined workload and concurrency |
| Latency | Time to complete an operation/request |
| Throughput | Number of operations/requests completed per unit of time |
| p50/p95/p99 | Latency percentiles |
| Speedup | Ratio of baseline time to candidate time |
| Warm-up | Phase for the JVM to load classes and perform JIT optimization |
| Fork | Independent JVM process used for benchmarking |
| Confidence interval | Reliability range of an estimate |
| Noise | Variance not caused by the change under test |
| Regression | A metric or workload degrading after a change |
| Canary | Deploying to a small fraction of traffic for observation |
| SLO | Service Level Objective |
| JFR | Java Flight Recorder, a tool for recording runtime events |
| JMC | JDK Mission Control, a tool for analyzing JFR |

Before-and-after comparisons are only trustworthy when correctness, workload, environment, and measurement methods are controlled. Use JMH for microbenchmarks, load tests for services, JFR to explain JVM behavior, and metrics to evaluate real-world impact. Only claim an improvement when results are repeatable, error margins are understood, and no regressions are introduced in latency, error rate, or resources.

## References

- OpenJDK — [Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)
- Oracle JDK 24 — [System.nanoTime()](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/System.html#nanoTime())
- Oracle JDK 24 — [Java Flight Recorder](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-api-programmers-guide.pdf)
- Oracle JDK 24 — [Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
