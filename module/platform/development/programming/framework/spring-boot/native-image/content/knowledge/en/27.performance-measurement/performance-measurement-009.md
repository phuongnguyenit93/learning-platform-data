# Repeating Measurements, Recording Conditions, and Separating Noise from Meaningful Change

## 1. Why Is a Single Measurement Not Enough?

Performance measurements of Spring Boot on the JVM and GraalVM Native Image usually aim to compare startup time, memory usage, throughput, or latency. These figures fluctuate with machine load, cache state, JIT warm-up, garbage collection, OS scheduling, network conditions, and database activity. Consequently, a single fast or slow run is never enough to conclude whether a new build is better or worse.

A trustworthy measurement requires three elements: **controlled repetition**, **complete condition logging**, and **evaluating the magnitude of difference**. You must separate natural run-to-run variance from consistent changes driven by code, configuration, or binary type.

In the **SPRING_BOOT_NATIVE_IMAGE** module, measurements often compare the JVM against a native executable. The two runtimes behave differently: the JVM has JIT warm-up and its own heap/GC; a native executable typically lacks HotSpot-style runtime JIT. You must therefore clearly define the measurement phase, workload, and environment for the comparison to be meaningful.

## 2. Define Questions and Metrics Before Running

Do not start by running a benchmark and cherry-picking flattering numbers. Write down the exact questions to answer, such as:

- Does the native executable reduce time from process start to readiness?
- How much does RSS change after 60 seconds idle?
- Is throughput preserved when processing the same workload?
- Does p95/p99 latency improve at the target concurrency?
- Is native build duration acceptable given the runtime benefits?

Select metrics matching each question:

| Metric | Unit | How to Interpret |
|---|---:|---|
| Startup-to-ready | ms or s | From process launch until the application is ready to accept traffic |
| RSS | MiB | Physical memory resident for the process at measurement time |
| Heap used | MiB | Heap memory currently in use; measured differently from RSS |
| Throughput | requests/s | Requests completed per second |
| Latency | ms | Request processing time; report p50/p95/p99 |
| CPU | % or CPU-seconds | CPU consumption during the workload |
| Error rate | % | Percentage of failed requests |
| Build duration | s or min | Time to build the native executable |

Do not let one metric stand in for every aspect. Lower RSS does not prove higher throughput; faster startup does not prove lower latency under load.

## 3. Define Exact Start and End Points

Startup time requires an observable start point and readiness condition. For example:

- **Start**: when the supervisor/process launcher begins creating the process.
- **Ready**: when the health/readiness endpoint reports ready and required dependencies are connected.

Do not use the "Started Application" log timestamp if the application still needs to warm caches, run migrations, or wait for dependencies before serving traffic. If the goal is time from process start to socket listen, label it explicitly as startup-to-listen rather than startup-to-ready.

Request latency also needs a clear boundary: client-side end-to-end versus server-side handler duration. Client-side includes network, connection setup, and serialization; server-side typically excludes all or part of those components.

## 4. Repeat Measurements Methodically

Repetition estimates variance. The required count depends on noise and benchmark cost; no single number fits every workload.

A practical starting workflow:

1. Run a few pilot iterations to catch setup mistakes and estimate variance.
2. Execute warm-up per the defined protocol if the runtime/workload requires it.
3. Collect at least 10–20 independent measurements for stable metrics when cost permits.
4. For noisy benchmarks or p99, gather more samples and run longer durations.
5. Report the full distribution and sample count, never just the fastest run.

For startup, each measurement should launch a fresh process because startup state belongs to the process lifecycle. For throughput/latency, each sample should be a measurement window with a defined workload and duration; do not treat individual requests within a single load run as completely independent benchmark runs.

You can interleave JVM and native in multiple alternating blocks to reduce the impact of thermal drift, background load, or host state changing over time.

## 5. Warm-Up and Cold Start Must Be Separated

The HotSpot JVM needs time to JIT-compile and optimize code. Measuring the JVM immediately after process startup reflects interpreter/compilation phases. Measuring after warm-up better reflects steady-state behavior.

Native Image generally lacks equivalent JIT warm-up, yet can still be influenced by page cache, class/resource loading, connection pools, DNS, TLS sessions, database caches, and application caches.

Design two separate question sets accordingly:

- **Cold-start behavior**: measure fresh processes with caches in a defined state, without skipping startup work.
- **Steady-state behavior**: after warm-up/workload stabilization, measure latency/throughput and resource consumption.

Never warm up the JVM for 5 minutes while measuring native right after startup and call that a fair throughput comparison. Likewise, never ignore cold-start if the primary product use case is scale-to-zero or serverless.

## 6. Record Machine and Environment Conditions

Each benchmark run must record at minimum:

| Group | Information to Record |
|---|---|
| Hardware | CPU model, core count, RAM, architecture |
| OS | Distribution/version, kernel, Windows/macOS version |
| Runtime | JDK vendor/version, GraalVM version, Native Image version |
| Build | Commit SHA, compiler flags, optimization, debug/strip settings |
| Application | Spring Boot version, profile, configuration, feature flags |
| Dependencies | Driver/library versions and resolved dependency graph |
| Container | Image digest, base image, CPU/memory limits, runtime user |
| Workload | Request mix, concurrency, duration, payloads, and dataset |
| External systems | Database version, topology, cache state, network path |
| Host state | Power mode, background load, CPU throttling, thermal state |

Record seemingly minor details as well: container CPU quotas, memory limits, JVM flags, GC, heap sizing, native memory settings, and replica counts. If environments differ, do not merge measurements into a single comparison without explanation.

## 7. Control Confounding Variables

A solid benchmark holds constant or records variables that can shift results:

- Run on the same machine or identical instance type.
- Use identical OS, kernel, architecture, and container limits.
- Keep database dataset, indexes, and cache policies identical.
- Use identical request mix, payloads, and concurrency.
- Disable unnecessary background workloads or record their load level.
- Keep network path and client placement identical.
- Avoid running native builds concurrently with benchmarks.
- Monitor CPU throttling, thermal throttling, and memory pressure.
- Use identical logging/metrics/tracing configurations.

If running on shared CI runners is unavoidable, log host metadata and background load. Noisy CI results work for catching large regressions; for small differences, benchmark on a more tightly controlled machine or runner.

## 8. Report Distributions, Not Just Averages

Latency is usually right-skewed: most requests are fast while a few are substantially slower. Mean can be dragged up by outliers; p50/p95/p99 describe different regions of the distribution.

Reports should include:

- Run count/request count and duration per run.
- Mean and standard deviation when distribution shape is appropriate.
- Median and interquartile range (IQR) for a more robust center and spread.
- p50, p95, p99 for latency.
- Min/max only as supplementary context; never conclude from min.
- Error rate and number of excluded samples with reasons.

Example summary table:

| Runtime | Runs | Startup median | Startup IQR | Median RSS after 60s |
|---|---:|---:|---:|---:|
| JVM | 15 | 1,850 ms | 120 ms | 310 MiB |
| Native | 15 | 420 ms | 35 ms | 105 MiB |

Numbers only illustrate formatting, not experimental findings of this module. In real reports, attach raw data and measurement conditions.

## 9. Variance and Measurement Error

Suppose the same configuration produces varying results across runs. Variance can stem from:

- System and scheduler noise.
- Warm/cold cache states.
- JIT/GC or background compilation.
- Unsettled connection pools.
- Network jitter and database load.
- Measurement tool resolution and overhead.
- Temperature shifts and CPU frequency scaling.

Standard deviation describes spread around the mean when appropriate. IQR measures the span between Q1 and Q3 and resists outliers. Confidence intervals express uncertainty of an estimate under chosen methods and assumptions.

Never mechanically dismiss every difference smaller than one standard deviation as "meaningless." Consider sample design, distribution shape, sample size, and the minimum change that matters to the product.

## 10. Distinguish Statistical Significance from Practical Significance

These are two separate questions:

- **Statistical significance**: does the data provide sufficient evidence that the difference is not merely random variation under the chosen analytical model?
- **Practical significance**: is the difference large enough to impact SLAs, costs, user experience, or architectural decisions?

With huge samples, a 1 ms difference can be statistically significant yet irrelevant to a 500 ms SLA. Conversely, with few runs, a 20% improvement can be practically compelling yet require more data to estimate reliably.

Before benchmarking, define the **minimum practically important difference**. For instance, a team might set a target of reducing startup by at least 200 ms or RSS by at least 50 MiB to justify changing the pipeline; such thresholds must come from real system needs, not generic examples.

## 11. Calculate Percentage Change in the Right Direction

For lower-is-better metrics like startup or latency:

`improvement(%) = (baseline - candidate) / baseline × 100`

For higher-is-better metrics like throughput:

`improvement(%) = (candidate - baseline) / baseline × 100`

Example: median startup drops from 1,800 ms to 450 ms:

`(1800 - 450) / 1800 × 100 = 75%`

RSS drops from 300 MiB to 120 MiB:

`(300 - 120) / 300 × 100 = 60%`

Always state units and the baseline. If the baseline is 0 or ratio percentages make no sense for the metric, do not force the percentage formula.

## 12. Use Confidence Intervals and Paired Comparisons When Appropriate

When comparing JVM and native, you can run blocks on the same host in alternating order to reduce drift. When two measurements are paired by block (e.g., a JVM run followed by a native run under matching conditions), analyzing paired differences is often more informative than comparing two unrelated sets.

For roughly normal metrics meeting assumptions, confidence intervals of the mean help express uncertainty. For skewed distributions or outliers, consider medians, bootstrap confidence intervals, or nonparametric methods. Never shop for statistical tests after seeing the data just to obtain a desired p-value.

State the method, confidence level, sample size, and assumptions. For operational decisions, prioritize both effect size and uncertainty range rather than a lone p-value.

## 13. Outliers: Never Delete Bad Runs Arbitrarily

An outlier may be a genuine measurement glitch, or it may reveal a real production issue: GC pauses, throttling, connection retries, or tail latency. Never delete a sample simply because it worsens results.

Handling workflow:

1. Flag anomalous samples.
2. Inspect logs/metrics/host telemetry for root cause.
3. Apply pre-established or documented exclusion criteria.
4. If caused by out-of-scope infrastructure faults, exclude with documented justification and report excluded counts.
5. If it is application behavior that could occur in production, keep it in the analysis.
6. Report results both with and without excluded samples if the decision hinges on them.

Do not trim top/bottom percentiles arbitrarily without stating the methodology. An ugly tail latency spike may be the exact issue the benchmark needed to expose.

## 14. Measure Startup, Memory, and Throughput with Separate Protocols

**Startup**: launch a fresh process each run, use a readiness probe, record process start and ready timestamps, and fix dependency readiness and migration policies. Report median/IQR along with run count.

**Memory**: explicitly select RSS, heap, or native memory; sample at milestones such as post-startup, after 60 seconds idle, and after load. Never compare JVM heap used directly against native RSS as if they were the same metric.

**Throughput/latency**: use a dedicated load generator, warm up per protocol, hold concurrency/request mix constant, run long enough to stabilize, and report p50/p95/p99 plus error rate. Ensure the load generator never becomes a bottleneck.

## 15. Example Reproducible Benchmark Protocol

A protocol comparing JVM and Native Image might specify:

```text
Question: Compare startup-to-ready and steady-state HTTP latency
Host: Linux x86_64, 8 vCPU, 16 GiB RAM
Container: same CPU quota and memory limit
Database: same test dataset and endpoint
Application: same commit, Spring profile and request behavior
JVM: recorded JDK, heap and GC flags
Native: recorded GraalVM and Native Image build arguments

Startup:
- 15 fresh process launches per runtime
- Same readiness endpoint
- Record process start and readiness timestamp

Steady state:
- 2-minute warm-up
- 10-minute measurement window
- Fixed request mix and concurrency
- 5 independent runs per runtime
- Report throughput, p50/p95/p99 and error rate

Memory:
- Record RSS at ready, 60 seconds idle and after load
- Record JVM heap separately where applicable
```

This protocol is illustrative; adjust run counts and durations to your noise level and SLAs. Archive scripts, datasets, request fixtures, and raw results alongside the benchmark report so others can reproduce it.

## 16. Avoiding Unfair Comparisons Between JVM and Native

Common mistakes:

| Mistake | Why It Is Wrong | Fix |
|---|---|---|
| Measuring JVM at start and native after warm-up | Different runtime phases | Define cold-start and steady-state separately |
| Comparing JVM heap against native RSS | Different metrics | Compare RSS to RSS; report heap separately |
| Different CPU/memory limits | Unequal resources | Use identical quotas/host class |
| Different profiles or features | Different workload executed | Identical commit/configuration/behavior |
| Running only once | Cannot estimate variance | Repeat independently and report distributions |
| Reporting only the best run | Hides tail and noise | Report median, spread, and percentiles |
| Deleting outliers arbitrarily | Biases results | Explicit sample exclusion rules |
| Measuring only the health endpoint | Unrepresentative of real workload | Use a production-like request mix |
| Underpowered load generator | Throughput capped by client | Verify client CPU/network headroom |

## 17. Recording Results and Comparing Over Time

Every report should contain:

- Benchmark question and primary metrics.
- Baseline/candidate commits and artifact digests.
- Protocol, script, and dataset versions.
- Host/container/runtime conditions.
- Raw samples, summary statistics, and plots if available.
- Outlier/exclusion notes.
- Practical threshold and conclusion.
- Limitations and unmeasured scenarios.

When comparing across releases, keep the benchmark harness stable. If you change the load generator, dataset, or readiness definition, mark it as a protocol change; never splice two series together as if they were the same measurement.

Periodic benchmarks can detect drift, but enforce hard regression gates in CI only when the environment is stable enough and thresholds are calibrated against baseline noise. On noisy runners, use results as investigation signals rather than failing builds on small swings.

## 18. Pre-Conclusion Checklist

- Benchmark questions and metrics were defined upfront.
- Start/end boundaries and warm-up are clearly defined.
- Sufficient independent runs and appropriate measurement windows were executed.
- JVM and native used identical workload, dataset, and resource limits.
- Hardware, OS, toolchain, profile, and dependency versions are recorded.
- Median/percentiles and dispersion are reported, not just best run.
- Outliers were investigated and handled under documented rules.
- Statistical significance is distinguished from practical significance.
- Minimum practically important change thresholds exist for the product.
- Raw data, scripts, artifact digests, and reports are archived.
- Conclusions apply strictly to the measured metrics, workload, and environment.

## 19. Self-Check Questions

1. Why is a single startup measurement insufficient to compare JVM and Native Image?
2. What is the difference between cold-start and steady-state benchmarks?
3. Why must startup-to-ready be clearly defined?
4. When are median/IQR preferable to reporting only the mean?
5. What do standard deviation and confidence intervals describe?
6. How does statistical significance differ from practical significance?
7. Why should outliers never be removed arbitrarily?
8. How should RSS and heap be compared properly?
9. Which environmental conditions must be recorded for a benchmark to be reproducible?
10. When should benchmarks act as a CI gate versus merely an investigation signal?

**Key takeaway:** a reliable performance conclusion rests on repeated measurements, explicitly documented protocols and conditions, distributions with uncertainty bounds, and practical significance thresholds. Compare JVM against Native Image on identical workloads, separate cold-start from steady-state, and archive raw data so others can reproduce your findings.
