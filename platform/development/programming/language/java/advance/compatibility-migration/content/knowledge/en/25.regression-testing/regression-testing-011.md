# Setting Functional, Performance, and Operational Acceptance Thresholds in CI

## 1. Why Are Acceptance Thresholds Needed When Upgrading Java?

In **Java Advance Compatibility Migration**, a build that compiles successfully on a new JDK does not yet prove the product is ready for release. A migration can preserve data types and public APIs while altering serialization behavior, timezone handling, concurrent execution ordering, latency under high load, native memory usage, or container startup speed.

For a controlled release, the team needs to turn the vague question **“Is the new JDK okay?”** into deterministic conditions:

- **Functional correctness:** which behaviors must remain unchanged, and which behaviors are allowed to change according to the published contract?
- **Performance:** how much are throughput, latency, allocation, CPU, GC, and startup allowed to diverge from the baseline?
- **Operational readiness:** does the application start up, stay healthy, respect resource limits, handle failures, shut down, and remain observable on the target infrastructure?
- **Reliability of evidence:** does the CI data have sufficient environmental equivalence, sample count, stability, and reproducibility to draw a conclusion?
- **Release decision:** which violations block merge/release, which violations trigger warnings, and when must an investigation or exception approval occur?

An **acceptance threshold** is a boundary defined *before evaluating results* to decide PASS, FAIL, INCONCLUSIVE, or approval needed. It differs from running tests and then picking a number so that the current results barely pass.

In this lesson, a **CI gate** is an automated step that checks one or more conditions. Not every kind of criterion can be measured well by a short job in CI: for example, memory leaks require soak tests, while canary behavior under real traffic requires post-deployment monitoring. Therefore, a good design splits gates by stage while still maintaining clear criteria, owners, and evidence.

Learning objectives:

1. Establish pass/fail criteria for the three groups: functional, performance, and operational.
2. Select the right baseline for comparing before and after a JDK migration.
3. Write thresholds specifying units, measurement direction, data, and noise-handling rules.
4. Avoid false conclusions from benchmarks run in non-equivalent environments.
5. Organize pipelines consisting of correctness gates, performance gates, runtime smoke tests, and deployment verification.
6. Handle flaky tests, missing data, variance, borderline results, and exceptions.
7. Record evidence so that release, canary, or rollback decisions are explainable and auditable.

## 2. Distinguishing Test Assertion, Quality Gate, SLO, and Error Budget

The following concepts are often confused:

| Concept | Answers the question | Example |
|---|---|---|
| **Test assertion** | Does one test case produce the right result? | API returns HTTP 400 for an invalid payload. |
| **Functional acceptance criterion** | Which set of contracts must remain intact? | No data loss, no out-of-scope breaking changes. |
| **Quality gate** | May the pipeline advance to the next step or release? | 100% of critical contract tests must PASS. |
| **Performance regression budget** | How much deviation from the baseline is acceptable? | p95 latency does not increase beyond the approved amount under fixed load. |
| **Absolute performance limit** | Does the result exceed a maximum/minimum regardless of baseline? | p99 stays below the required latency ceiling. |
| **Operational readiness criterion** | Does the artifact operate safely on the target runtime? | Zero OOMKilled in the defined test; SIGTERM is handled. |
| **SLO** | What is the target service quality over an operating window? | 99.9% of valid requests succeed over 30 days, as defined by the SLI. |
| **Error budget** | How much quality degradation is allowed to be consumed in the SLO window? | Remaining downtime/errors allowed under the SLO. |

A CI quality gate can use some thresholds derived from an SLO, yet **a 5-minute benchmark does not prove a 30-day SLO**. Conversely, an application exceeding the regression budget relative to the baseline may still lie below the SLO ceiling; a clear decision policy is needed on whether that regression is permitted.

### 2.1. Three Types of Conditions Should Appear Together

For a performance metric, you typically need:

1. **Absolute guardrail:** does not exceed a ceiling or drop below a floor.
2. **Regression budget (relative/absolute delta):** does not degrade from the baseline beyond the allowed amount.
3. **Evidence validity conditions:** valid sample count, environment, test duration, variance, and coverage.

For example, latency in the new version at 180 ms versus 100 ms is an 80% regression. Even if the SLO allows under 500 ms, the team may still decide **FAIL** because the regression is too large. Conversely, if the baseline is already at 480 ms and the candidate rises to 490 ms, even though the delta is small, it may still cross the safety threshold defined for load-surge headroom.

### 2.2. Policies Must Distinguish Statuses

A gate should not merely return a boolean from every situation. Recommended statuses:

~~~text
PASS         Sufficient evidence and all mandatory conditions are met.
FAIL         A confirmed violation or real error occurred.
INCONCLUSIVE Insufficient evidence/stability to conclude.
WAIVED       An exception approved within proper scope and expiration.
~~~

In a required pipeline, both FAIL and INCONCLUSIVE normally **must not automatically release**. However, recording two distinct statuses prevents confusing a test infrastructure outage with an application regression.

## 3. Setting the Baseline Before Choosing Thresholds

A **baseline** is a reference result with clear provenance used to evaluate a candidate. An unreliable baseline diminishes the value of all subsequent comparisons.

### 3.1. What Can a Baseline Be?

- A release running stably in production on the old JDK.
- The same source commit built and run on two different JDKs to isolate JDK impact.
- Approved benchmark results from a release branch.
- A set of golden outputs and contract fixtures for functionality.
- Independent thresholds taken from SLOs/product requirements when no prior version exists.

Do not automatically use “the last CI run result” as a rolling baseline if that run could already contain a regression. An approved baseline should have a version, creation date, approver/approval policy, and environment description.

### 3.2. Two Different Comparisons

In a migration, distinguish:

**Pure JDK comparison:**

~~~text
Same source code and locked dependencies
    ├── Run on baseline JDK
    └── Run on target JDK
~~~

This measurement reveals runtime/JIT/GC/implementation differences if the harness and environment are kept equivalent.

**Product change comparison:**

~~~text
Release baseline: source + old JDK + old dependencies
Release candidate: new source + new JDK + new dependencies
~~~

This measurement reflects the overall impact on consumers, yet **cannot attribute every change solely to the JDK**.

If root-cause analysis is needed, a 2 × 2 matrix can be designed when build/runtime compatibility permits:

| Source / runtime | Old JDK | New JDK |
|---|---|---|
| Baseline code | A | B |
| Candidate code | C | D |

A→B suggests the JDK impact on baseline code; A→C suggests code changes on the old JDK; B→D suggests code changes once on the new JDK; A→D is the combined impact. Not every combination can compile or run, especially when dependencies have raised their minimum Java version; in that case, document the limitation instead of guessing.

### 3.3. Metadata That Must Accompany a Baseline

A minimal performance baseline should describe:

| Attribute | Information to record |
|---|---|
| Artifact | Commit, dependency lock/BOM, checksum or image digest. |
| JDK | Vendor, major, update/build, JVM implementation, and flags. |
| OS/hardware | CPU model/architecture, vCPU, memory, kernel, container image. |
| Runtime constraints | CPU quota/cpuset, memory limit, cgroups mode. |
| Benchmark tool | Tool/version, scenario, harness, warmup, and measurement. |
| Workload | Dataset size, request mix, concurrency, throughput target. |
| External dependencies | DB/cache versions, network conditions, isolation strategy. |
| Results | Raw sample data, summary metrics, variance, and logs. |
| Ownership | Owner, approval date, expiry/re-baseline policy. |

A p95 measured on a laptop and a p95 measured on a shared cloud runner are not two points that can be compared accurately merely because the test names match.

## 4. Defining the Functional Scope to Protect

A functional gate must start from the **product contract**, not from test coverage percentages.

Critical contract categories when upgrading the JDK:

- Public Java API and binary compatibility for libraries.
- HTTP/gRPC/message wire contracts: field names, status codes, schemas.
- Persistence: data, transactions, isolation, schema migrations, and rollback.
- Serialization: JSON, XML, Java serialization, protobuf, date/time, and charset.
- Authorization/security: without losing mandatory checks.
- Concurrency: ordering, atomicity, race conditions, and deadlocks.
- TLS/crypto: certificate validation, providers, and supported algorithms.
- Timezone/locale/Unicode and arithmetic with rounding rules.
- Startup/configuration, plugin discovery, reflection, and modularity when the application relies on them.
- Consumer APIs/CLIs when libraries/modules are updated.

Select only criteria that truly belong to the product contract. A migration may intentionally change old behavior for security reasons or change a public API in a major release; approved differences must be described and tested against the **new** contract, not silently treated as undocumented “allowed regressions”.

### 4.1. Sample Functional Criteria

| ID | Contract | Threshold | Level |
|---|---|---|---|
| F-01 | Critical business journeys | 100% of mandatory cases PASS on target JDK. | Blocker |
| F-02 | Public API/ABI does not break committed contracts | 0 unapproved breaking changes. | Blocker |
| F-03 | Authorization and cross-tenant data isolation | 0 violations in mandatory security test suite. | Blocker |
| F-04 | Database transaction rollback | 100% of failure-path assertions PASS. | Blocker |
| F-05 | Serialization/wire golden fixtures | Results within defined tolerance/normalization. | Blocker or versioned |
| F-06 | Secondary UI rendering | No regressions at defined severity; some cosmetic changes may be accepted. | By severity |

These are illustrative thresholds for a system, not a universal standard forced on every project. When writing F-01, include concrete test IDs, expected behavior, JDK matrix, data, and PASS conditions.

### 4.2. Why Is “100% Test Pass” Still Not Enough?

If a business domain has no tests, 100% of existing tests passing can still leave gaps. Therefore, a functional gate should verify:

1. Mandatory test suites actually executed.
2. Whether the number of skipped/disabled tests is within policy.
3. Whether test discovery found all required tests.
4. Results are not masked by retries or ignoreFailures.
5. Critical contract fixtures, consumer tests, or end-to-end flows are present.
6. Tests run on the declared **actual JDK/runtime**, not just the Java compiler toolchain.

Coverage can be a supporting signal, yet is not the sole proof that the entire contract has been tested.

## 5. Functional Gates by Risk Level

A useful model separates severity levels:

| Level | Example | Suggested gate |
|---|---|---|
| Critical | Data loss, privilege exposure, monetary error, authentication bypass. | Immediate FAIL; no routine self-waiver. |
| High | Undocumented breaking public API, wrong transaction, crash on supported runtime. | FAIL merge/release. |
| Medium | Auxiliary behavior differs, workaround exists and impact scope is limited. | FAIL or require time-bound approval per policy. |
| Low | Cosmetic differences, non-contract log ordering. | Warning/triage; do not overwrite golden output to ignore. |

Severity must be agreed upon by product/engineering/security owners; developers must not downgrade severity themselves after seeing a test fail.

### 5.1. Contract Tests and Golden Files

Example API receiving JSON:

~~~json
{
  "customerId": "c-102",
  "balance": "128.50",
  "createdAt": "2026-01-15T09:30:00Z"
}
~~~

If the contract specifies balance as a decimal string with exactly two decimal digits and createdAt as UTC ISO-8601, tests should verify those properties. Do not compare the entire JSON as a raw string when object field order is not part of the contract; doing so easily causes false failures.

Conversely, if the API genuinely requires key ordering or a byte-for-byte signature, normalization that strips information will mask regressions.

A guiding principle:

> Normalize differences that are meaningless under the contract, yet never normalize away the very content the contract protects.

### 5.2. Testing Arithmetic Precision Errors

Not every floating-point result can demand bitwise equality across changed libraries/JDKs/algorithms. Depending on the business domain:

- Currency uses decimals and explicit rounding policies.
- Measurements have reasonable absolute/relative tolerances.
- Invariants must always hold even when microscopic values fluctuate.
- NaN, Infinity, signed zero, and overflow need dedicated policies if they affect the contract.

Tolerance must be determined upfront from data domain characteristics; do not increase epsilon merely to let a regression “pass” CI.

## 6. Choosing the Right Performance Metrics for the Workload

Performance is multi-dimensional. Using only throughput or only total test duration can be misleading.

| Metric | Example unit | Desired direction | Requires further analysis |
|---|---|---|---|
| Throughput | requests/s, jobs/min | Higher is better | Load mix, concurrency, errors. |
| p50 latency | ms | Lower is better | Median experience; does not reflect tail. |
| p95 latency | ms | Lower is better | Tail latency with sufficient samples. |
| p99 latency | ms | Lower is better | Sensitive to noise/sample count; needs volume. |
| Startup time | s | Lower is better | Cold/warm start, image pull, readiness. |
| Allocation rate | MiB/s or bytes/op | Depends on policy; usually lower is better | Workload, GC, escaping objects. |
| GC pause p99 | ms | Lower is better | Collector, pause count, CPU quota. |
| GC CPU overhead | % CPU/time | Usually lower is better | Throughput trade-off. |
| Process/container memory | MiB | Must stay within budget | RSS, cgroup usage, native memory. |
| CPU utilization | core-seconds/req | Not always “lower is better” | Keeping same throughput/latency. |
| Error/timeout rate | % | Lower is better | Must not trade correctness for speed. |

**100% CPU usage is not automatically a regression** if the workload intentionally saturates CPU to measure throughput; 20% CPU usage does not prove health either if threads are blocked and throughput is low. Metrics must be interpreted by test type.

### 6.1. Classifying Workloads

Separate scenarios are needed:

1. **Microbenchmark:** a single algorithm or internal API measured with an appropriate tool like JMH.
2. **Component benchmark:** database mapper, JSON serializer, HTTP client, crypto/compression.
3. **Service load test:** endpoints and real dependency mix under defined concurrency.
4. **End-to-end:** business flow traversing multiple services.
5. **Startup/cold start:** time from process start to serving state.
6. **Soak/stress:** memory growth, concurrency, GC, and stability over time.

Do not use a microbenchmark to conclude the entire service meets its SLO. Conversely, a stable service p99 does not guarantee a critical compute function has not become much slower if current traffic does not trigger it.

## 7. Designing Quantitative Performance Budgets

There are two types of boundaries:

**Absolute guardrail**, for example:

~~~text
p95 latency <= 250 ms
error_rate <= 0.1%
startup_time <= 40 s
~~~

**Regression budget**, for example:

~~~text
candidate p95 latency increases by no more than 10% over baseline
candidate throughput decreases by no more than 8% compared to baseline
~~~

The numbers in this lesson are **illustrative data** to explain how to design gates; they are not pre-packaged thresholds to apply directly to a product.

### 7.1. Relative Delta Formulas

For “lower is better” metrics:

~~~text
regression_pct = (candidate - baseline) / baseline × 100%
~~~

For “higher is better” metrics:

~~~text
regression_pct = (baseline - candidate) / baseline × 100%
~~~

In both formulas, positive values represent worsening. A positive baseline and handling for baselines equal to 0 or near 0 are required.

Example p95 latency:

~~~text
baseline  = 100 ms
candidate = 112 ms
regression_pct = (112 - 100) / 100 × 100% = 12%
~~~

If policy allows at most 10% regression, then FAIL.

Example throughput:

~~~text
baseline  = 2,000 requests/s
candidate = 1,860 requests/s
regression_pct = (2000 - 1860) / 2000 × 100% = 7%
~~~

If the maximum budget is 8% and other guardrails PASS, this metric can PASS.

### 7.2. Combining Relative Thresholds with Small Absolute Margins

If a metric's baseline is only 0.2 ms, a 0.05 ms difference is already 25% and may just be harness noise. One strategy is:

~~~text
allowed_worsening = max(relative_budget × baseline,
                        absolute_noise_allowance)
~~~

Example with p95:

~~~text
relative_budget       = 10%
absolute_noise_allowance = 5 ms
baseline              = 100 ms
allowed_worsening     = max(10 ms, 5 ms) = 10 ms
regression boundary   = 110 ms
~~~

This policy allows exceeding one of the two thresholds depending on how it is specified, so it must be approved upfront. For metrics with very strict requirements, you may want AND or a separate hard ceiling; do not choose operators arbitrarily after viewing results.

Example:

~~~text
PASS if:
  candidate <= baseline + allowed_worsening
  AND candidate <= absolute_ceiling
  AND measurement_quality == VALID
~~~

This is an unambiguous rule for “lower is better” metrics; for throughput, the inequalities must be reversed.

### 7.3. Baseline Equal to 0

When error count baseline = 0, percentage regression calculation is meaningless. Use absolute criteria:

- Critical security violation count = 0.
- Unhandled error count = 0 in the mandatory scenario set, per policy.
- Error rate <= ceiling appropriate for sample volume.
- Restart/OOMKilled count = 0 in stability tests of defined duration.

A result of “0 errors out of 10 requests” does not prove a tiny production error rate; appropriate measurement windows and volume are needed.

## 8. Example Performance Criteria Set for an API

Suppose an internal payment processing service runs with a fixed load suite, illustrative measurements:

| Metric | Baseline | Candidate | Illustrative gate | Result |
|---|---:|---:|---|---|
| p95 latency | 180 ms | 189 ms | Max +10%; ceiling 250 ms | PASS |
| p99 latency | 310 ms | 365 ms | Max +12%; ceiling 400 ms | FAIL on delta |
| Throughput | 2,000 req/s | 1,940 req/s | Max -8%; floor 1,700 req/s | PASS |
| Error rate | 0.02% | 0.03% | Ceiling 0.10% with sufficient samples | PASS |
| Startup to ready | 24 s | 27 s | Max +20%; ceiling 35 s | PASS |
| Peak container memory | 1,200 MiB | 1,500 MiB | Ceiling 1,600 MiB; regression budget per policy | Needs delta check |

The conclusion for this criteria set is **not eligible to PASS the overall performance gate** because p99 increased beyond the allowed limit, even though it remains below the 400 ms absolute ceiling. Do not ignore p99 merely because throughput remains good.

### 8.1. One Metric Does Not Represent Overall Quality

For example, if a candidate's throughput increases by 20% while the error rate rises from 0% to 2%, that is not an acceptable improvement if response quality drops.

Or if latency decreases while CPU core-seconds/request doubles, that can increase cost and cause throttling when deployed under the same resource limit. Separate user-facing performance from resource efficiency.

## 9. Measurement Noise and Baseline Stability

Running a benchmark once and treating a 2% difference as conclusive is usually unreliable. Sources of noise include:

- CPU frequency scaling, turbo boost, and temperature.
- Shared CI runners suffering contention.
- Changing CPU quota/cpuset.
- JIT warmup, tiered compilation, and profile-guided behavior of the JVM.
- GC cycles, classloading, code cache, and thread scheduling.
- Disk/page cache, network jitter, and DNS.
- Database cache, indexes, background maintenance.
- Insufficient request count for p99.
- Different datasets between baseline and candidate.
- Different JDK vendor/update, GC, OS kernel, or container image.
- Test ordering, randomized seeds, and concurrent jobs running on the same machine.

**A regression smaller than the measurement system's noise floor should not be declared with certainty as a real regression.** Conversely, large fluctuations when the environment changes still require isolating the cause.

### 9.1. Separating Warmup from Measurement

For a JIT-based JVM:

~~~text
Process start
    │
    ▼
Classloading / JIT warmup / cache settling
    │
    ▼
Measurement window
    │
    ▼
Aggregate + variance + evidence validity
~~~

Warmup duration or phase-transition criteria must be defined in advance; do not arbitrarily discard slow candidate samples assuming “it probably wasn't warm yet”.

Specifically, **startup-time benchmarks** must measure real cold starts rather than stripping warmup and reporting that as startup latency. The two tests answer two different questions.

### 9.2. Repeating Multiple Process Runs

For example, run 5–10 independent measurement runs in the same suitable environment, each with defined warmup and measurement phases. This is only an illustrative count; the required number of runs must be based on variance, cost, and gate sensitivity.

Do not treat 10,000 samples inside a single JVM process as equivalent to 10,000 independent runs when every sample is affected by the same GC state or runner condition.

### 9.3. Baseline Distribution Instead of a Single Number

Example p95 latency across independent runs:

~~~text
Baseline:  101, 99, 103, 100, 98 ms
Candidate: 110, 112, 108, 111, 109 ms
~~~

Comparing medians across runs can be useful. However, if:

~~~text
Baseline: 100, 120, 98, 140, 102 ms
Candidate: 108, 111, 105, 122, 110 ms
~~~

then the baseline fluctuates much more heavily; the gate should examine measurement quality, infrastructure-induced outliers, and a rerun plan, rather than cherry-picking a favorable baseline run.

Statistics such as median, interquartile range, median absolute deviation, or bootstrap confidence intervals can help, yet must be applied under valid assumptions about sample independence. Do not compute a p-value from millions of request samples in one process and treat it as millions of independent experiments.

## 10. Choosing a Policy for Borderline Results

A strong gate needs to define an **uncertainty zone**:

~~~text
Clear conditions met to PASS
      │
      ▼
Near-threshold zone / high variance → INCONCLUSIVE or rerun
      │
      ▼
Clear threshold violation → FAIL
~~~

Illustrative policy example:

1. If data is missing or environments are not equivalent: INCONCLUSIVE.
2. If the candidate violates a hard ceiling or correctness rule: FAIL.
3. If regression exceeds budget and repeated runs show the same trend: FAIL.
4. If regression is near the budget, within the quantified noise band: rerun under a pre-bounded rerun policy.
5. If after rerunning it remains inconclusive: INCONCLUSIVE, escalate to the benchmark owner.
6. If PASS and evidence is valid: allow the pipeline to proceed.

Do not use a “keep rerunning until one run PASSES” strategy. Uncontrolled reruns degrade the value of quality gates and encourage selecting lucky outcomes.

### 10.1. Having a Policy When Runners Are Too Noisy

If shared runners produce high variance, better solutions may be:

- Dedicated benchmark workers with fixed resources.
- Pinning CPU affinity/CPU limits and checking the noise floor.
- Using internal load generation to avoid network variance when measuring microbenchmarks.
- Reducing background tasks.
- Comparing baseline and candidate in adjacent turns on the same worker when appropriate.

Do not inflate the regression budget to a huge level just because the measurement environment is unstable. Doing so destroys the gate's ability to detect real regressions.

## 11. Statistical Testing: Practical Significance and Limits

A result can be statistically “significant” while the difference is only 0.1% and negligible to the product; or a dangerous 10% difference may lack enough samples for statistical power.

Therefore, decisions should consider simultaneously:

1. **Effect size:** the practical magnitude of the difference.
2. **Measurement uncertainty:** reliability and variability.
3. **Product budget:** what the workload can tolerate.
4. **Hard operational limits:** absolute bounds that must be guaranteed.

Choose confidence intervals, paired comparisons, or robust methods depending on the measurement design. Do not apply a simple t-test if samples have autocorrelation, heavily skewed distributions, or baseline/candidate are not independent as assumed.

### 11.1. Percentiles Need Sufficient Data

p99 is a tail metric. With 100 requests, p99 depends mainly on 1 extreme request and fluctuates wildly. Even with workloads of thousands of requests, p99 must still be interpreted according to the sampling window and distribution shape.

When reporting p95/p99, record:

- Number of successful and failed requests.
- Percentile calculation method (raw samples or histogram approximation).
- Histogram resolution and sampling policy.
- Warmup/measurement duration.
- Load shape/concurrency.
- Whether timeouts or failed requests are excluded from latency metrics.

If failed requests are arbitrarily excluded from latency, a candidate can look “fast” because the slowest requests timed out and were dropped from the sample. A separate gate for error rate and an explicit definition of the latency population are needed.

## 12. JMH and Controlled Java Benchmarks

For microbenchmarks in Java, **JMH** is a suitable tool because it provides warmup, measurement, forking, and handles many JIT pitfalls. However, JMH does not automatically eliminate all hardware noise or turn a microbenchmark into a production SLO conclusion.

Simple example using JMH annotations:

~~~java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class StringParsingBenchmark {
    private final String input = "12345678";

    @Benchmark
    @BenchmarkMode(Mode.AverageTime)
    @OutputTimeUnit(TimeUnit.NANOSECONDS)
    public int parse() {
        return Integer.parseInt(input);
    }
}
~~~

The snippet above only illustrates how to declare a benchmark and requires appropriate JMH dependencies/harness. Do not simply run the class like a regular application main and conclude it is a reliable benchmark.

### 12.1. JMH Principles

- Define warmup, measurement iterations, and forks.
- Do not write benchmarks where the compiler eliminates the entire computation due to no observable effect.
- Ensure inputs/state represent the scenario being tested.
- Distinguish AverageTime, Throughput, and SampleTime; do not compare inverted units.
- If benchmarks run across multiple JDKs, record JDK flags, collector, CPU, and JMH version.
- Inspect post-optimization efficiency and realistic workloads, not just one micro-operation.

For very small functions, distortion from constant folding or dead-code elimination can be far larger than the JDK regression the team wants to measure.

### 12.2. Service Load Tests Need a Different Harness

When measuring REST APIs, use an appropriate load generator and metric pipeline; do not treat a JMH benchmark of a serializer as representative of the p99 of an API involving databases and networks.

For end-to-end tests, lock down the workload mix (for example, 70% read, 20% update, 10% create), dataset, concurrency, warmup, error handling, and duration.

## 13. Operational Thresholds on the New JVM

Operations are not just “Pod Running” or “systemd active”. A service can be alive yet unready, heavily throttled, fail to flush data on shutdown, or lack logs to investigate incidents.

Operational criteria typically include:

| ID | Metric/behavior | Illustrative threshold | Verification method |
|---|---|---|---|
| O-01 | Successful startup on target JDK | 100% mandatory, no unsupported flags used | Smoke startup and JVM logs. |
| O-02 | Post-startup readiness | Ready before policy timeout | Probe/health test. |
| O-03 | OOMKilled | 0 in defined load/soak tests | Pod status, memory.events, logs. |
| O-04 | Crashes/Unexpected restarts | 0 within stability window, except active kill tests | Container/systemd events. |
| O-05 | Peak memory | Below container limit with approved headroom | Cgroup/RSS/native/heap metrics. |
| O-06 | CPU throttling | Within budget under fixed load | Cgroup cpu.stat/metrics. |
| O-07 | Graceful shutdown | Drain/stop within grace period, zero data loss | SIGTERM + integration test. |
| O-08 | Diagnostics | GC/application logs and metrics present, no secret leaks | Collector/smoke checks. |
| O-09 | TLS/truststore | Connects to valid endpoints without disabling verification | TLS integration tests. |
| O-10 | Agent/instrumentation | Required agent loads exactly once and supports the JDK | Startup instrumentation check. |

“0” values apply within the **defined test window**; they cannot extrapolate to zero failure probability in unbounded production.

### 13.1. Distinguishing Hard Limits from Headroom

A container memory limit of 2 GiB does not mean “1.99 GiB peak = good PASS”. If the workload bursts, adds connections, shifts traffic mix, or incurs GC native overhead, remaining headroom is too thin.

An illustrative policy:

~~~text
memory_limit        = 2048 MiB
max_allowed_peak    = 1740 MiB
required_headroom   ≈ 308 MiB
~~~

These are example levels only, not standard ratios. Headroom needs to account for memory variance, native buffers, caches, and availability targets.

### 13.2. CPU Throttling Has No Universal Threshold

nr_throttled/nr_periods, throttled_usec, and CPU quota help identify contention, yet there is no single “safe” percentage for every workload. A batch job may tolerate substantial throttling if it finishes before its deadline, whereas a low-latency API is sensitive to tail latency.

Thresholds should be tied to:

- CPU limits and cgroups version.
- Workload type and traffic.
- Latency/throughput requirements.
- GC/concurrency behavior.
- Cost and capacity policy.

Do not draw conclusions from a single counter; correlate throttled time and application latency along the same timeline.

## 14. Startup Time, Readiness, and Shutdown Have Separate Thresholds

### 14.1. Defining Start/End Points

“Startup time” can mean several things:

- Time from launching the java process to the main method.
- From JVM start to application context initialized.
- From container start to startup probe succeeding.
- From Pod scheduled to Ready.
- From deployment creating a Pod until the instance is ready to serve traffic.

These definitions **are not equivalent**. When comparing JDKs, if the goal is JVM/application startup, do not mix image pull, scheduling, and node provisioning into the metric and blame the JDK.

Example criterion:

~~~text
Metric: application_start_to_ready_seconds
Start: process start timestamp
End: readiness endpoint meets the required condition
Load: no external warmup traffic
Budget: median <= baseline × 1.15
Absolute ceiling: <= 35 seconds
Samples: at least 5 independent process launches
~~~

Numbers are illustrative. An application requiring cache warming or DB migrations during startup may need different policies and metrics.

### 14.2. Graceful Shutdown

In Kubernetes, Pods have terminationGracePeriodSeconds; systemd has TimeoutStopSec. Gates can proactively send SIGTERM during tests and verify:

1. The process receives the signal.
2. Readiness is lowered according to contract.
3. No new requests are accepted violating policy.
4. In-flight work and transactions finish or roll back safely.
5. Background job consumers stop cleanly.
6. The process exits within the defined grace period.

Do not use a test that only checks exit code 0 to prove no data was lost, because an application can exit cleanly while abandoning an important business operation mid-flight.

## 15. GC, Heap, and Native Memory in Acceptance Gates

When switching JDKs, GC ergonomics or container/cgroups support may change. You typically need to measure:

- Heap used/committed/max.
- GC pause distribution and total pause time.
- GC throughput/CPU overhead.
- Allocation rate and promotion behavior.
- Metaspace/class count, code cache.
- Direct/off-heap/native memory, thread stacks.
- Process RSS and cgroup memory.current/peak.
- OOM events and JVM crash logs.

### 15.1. Do Not Use Heap Usage as a Proxy for Container Memory

Example:

~~~text
Java heap used peak       800 MiB
Java heap max            1200 MiB
Container memory peak    1900 MiB
Container limit          2048 MiB
~~~

Heap is only part of memory. Even when heap uses only 800 MiB, the container can sit near its hard limit due to native buffers, metaspace, stacks, mmap, or page cache.

### 15.2. Native Memory Tracking Has Its Own Scope

On a compatible HotSpot JDK, Native Memory Tracking (NMT) helps categorize certain JVM native allocations. However, NMT does not cover all allocations from native libraries/third-party code and has overhead.

Therefore, if setting a gate on native memory, record the measurement source: NMT category, process RSS, cgroup memory, or another profiling tool. Do not compare NMT total against cgroup memory.current as if the two values represent the same quantity.

### 15.3. Defining the Memory Measurement Window

Peak memory depends on test duration, warmup, cache growth, GC, and data. Distinguish:

- Startup peak.
- Steady-state peak.
- Soak peak or growth slope.
- Peak under stress.

A 2-hour soak test cannot be compared directly against a 5-minute benchmark to conclude the candidate has a memory leak solely from different peaks.

## 16. Designing a Multi-Tier CI Pipeline

A practical pipeline can be organized as:

~~~text
Commit / pull request
       │
       ▼
Build & static compatibility checks
       │
       ▼
Unit + API/contract tests
       │
       ▼
Integration tests on supported JDK matrix
       │
       ▼
Service startup/container smoke tests
       │
       ▼
Performance benchmark on controlled runners
       │
       ▼
Operational/stability tests
       │
       ▼
Aggregate evidence and quality gates
       │
       ├─ FAIL / INCONCLUSIVE → Block and triage
       │
       └─ PASS → Candidate eligible for staging/canary
                                  │
                                  ▼
                           Rollout gates
~~~

Not every job must run on every pull request if cost is high. They can be categorized:

| Stage | Typically runs | Examples |
|---|---|---|
| Per-commit/PR | Fast, high determinism | Compile, unit, contract, dependency/bytecode, smoke. |
| Protected branch/pre-release | Medium, stable environment | JDK matrix, integration, service load test. |
| Nightly | Time-consuming | Soak, memory growth, broad OS/GC matrix. |
| Release candidate | Full per policy | Functional/perf/operational evidence, packaging. |
| Staging/canary | Production-like environment | Health, real traffic/error rate, shutdown, rollback. |

What matters is that the release gate knows which jobs are mandatory. Do not let a candidate be automatically released merely because per-PR tests PASS while nightly/regression jobs are FAILING or lack valid data.

## 17. Java Runtime Matrix: Compile JDK Differs from Test JDK

Gradle Java Toolchains can use a newer JDK for the compiler while compiling with options.release targeting the minimum Java level; the Test task may need a different launcher from the compiler.

Kotlin DSL example for a Java library with minimum Java 17 yet built with JDK 21:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

val testJdk = providers.gradleProperty("testJdk")
    .orElse("17").map(String::toInt)

tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(
            JavaLanguageVersion.of(testJdk.get())
        )
    })
}
~~~

This is an example of choosing the runtime for Gradle Test tasks, not a guarantee that every custom JavaExec or test plugin will automatically pick up this configuration. Verify against the Gradle API level and actual project source.

In CI:

~~~bash
./gradlew clean test -PtestJdk=17
./gradlew clean test -PtestJdk=21
~~~

These runs can be executed in separate jobs. When running in parallel, isolate build directories/caches if they could cause contention. Beyond unit tests, test the packaged artifact with runtime dependencies on the minimum JDK.

### 17.1. Why Must You Actually Run on the Minimum JDK?

Compiling with javac --release 17 does not automatically downgrade the bytecode of dependent libraries. A transitive dependency with Java 21 class versions can be loaded on Java 17 and hit UnsupportedClassVersionError.

Therefore, if the product declares support for Java 17 and Java 21:

- Mandatory functional tests must exist on Java 17.
- Compatibility smoke tests with the artifact on Java 17.
- An appropriate test suite on Java 21.
- If other OS/architectures are supported, extend the matrix according to product commitments.

The number of combinations need not be an infinite Cartesian product; design by risk while never dropping the declared minimum runtime.

## 18. Separating the “Gate Engine” from Measurement Data

A good design has three components:

1. **Test/benchmark runner** produces standardized result data.
2. **Policy file** describes thresholds, validity conditions, and severity.
3. **Gate evaluator** reads data, decides PASS/FAIL/INCONCLUSIVE, and generates reports.

Example policy in YAML format:

~~~yaml
policyVersion: 1
suite: java-compatibility
minimumIndependentRuns: 5

functional:
  mandatorySuites:
    - api-contract
    - security-boundary
    - persistence-rollback
  requiredPassRate: 1.0
  allowSkippedCriticalTests: false

performance:
  scenario: checkout-read-write
  latencyP95:
    direction: lower
    maxRegressionPercent: 10
    absoluteCeilingMs: 250
  throughput:
    direction: higher
    maxRegressionPercent: 8
    absoluteFloorRps: 1700

operational:
  unexpectedRestartCountMax: 0
  oomKillCountMax: 0
  requireReady: true
  requireGracefulStop: true
~~~

This is an **illustrative policy**, not the schema of an automatically installed standard tool. To run in practice, an evaluator is needed that understands the exact field names, units, and rules.

### 18.1. Validity Metadata Conditions Must Not Be Skipped

In addition to the policy above, the evaluator should verify:

- Baseline and candidate ran on sufficiently equivalent hardware/OS/runtime constraints.
- Workload/scenario and test data share the same definition.
- Measurement units and histogram configurations match.
- Number of independent runs is sufficient.
- No runs had infrastructure failures or unclassified timeouts.
- Mandatory test suites have reports.
- Candidate artifact, dependency graph, and JDK metadata match the target.
- No unknown/missing metrics are silently treated as 0.

If p99 data is missing and the evaluator defaults it to 0 ms and PASSES, the gate encourages blind spots instead of controlling regressions.

## 19. Example Gate Formulas Easy to Automate

For metrics with positive baseline and candidate values:

~~~text
For "lower is better":
    absolute_ok = candidate <= ceiling (if any)
    regression_ok = candidate <= baseline × (1 + budget)

For "higher is better":
    absolute_ok = candidate >= floor (if any)
    regression_ok = candidate >= baseline × (1 - budget)

pass = valid_evidence AND absolute_ok AND regression_ok
~~~

A simple Python 3 implementation for already-aggregated data:

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class Gate:
    direction: str              # "lower" or "higher"
    max_regression_pct: float    # e.g., 10.0
    hard_bound: float            # ceiling if lower, floor if higher


def evaluate_metric(baseline: float,
                    candidate: float,
                    gate: Gate) -> tuple[bool, str]:
    if baseline <= 0:
        return False, "INCONCLUSIVE: baseline must be > 0"

    if gate.direction == "lower":
        regression_boundary = baseline * (
            1.0 + gate.max_regression_pct / 100.0
        )
        okay = (candidate <= regression_boundary
                and candidate <= gate.hard_bound)
    elif gate.direction == "higher":
        regression_boundary = baseline * (
            1.0 - gate.max_regression_pct / 100.0
        )
        okay = (candidate >= regression_boundary
                and candidate >= gate.hard_bound)
    else:
        return False, "INCONCLUSIVE: unknown metric direction"

    return okay, "PASS" if okay else "FAIL"


latency = Gate("lower", 10.0, 250.0)
print(evaluate_metric(180.0, 189.0, latency))

throughput = Gate("higher", 8.0, 1700.0)
print(evaluate_metric(2000.0, 1940.0, throughput))
~~~

The example only illustrates threshold logic **after metrics have been validated**. It does not handle missing data, NaN/Infinity, confidence intervals, environment comparability, or sample-count validity, and thus **is not a complete production CI gate**. In a real implementation, those conditions must be checked first and INCONCLUSIVE outcomes handled as a distinct state.

### 19.1. Do Not Bury Thresholds in Uncontrolled Code

It is better to keep policies reviewed/versioned in the repository with clear ownership and prevent the candidate author from loosening thresholds in the same change without additional review.

Record the policy revision in every report so you know why the same numbers PASSED last week yet FAILED this week when thresholds changed.

## 20. Exit Code Rules and CI Aggregation

A gate step should output structured results and an appropriate exit status:

~~~text
PASS         exit 0
FAIL         exit non-zero
INCONCLUSIVE exit non-zero in required job
~~~

These are operational suggestions; depending on the CI engine, separate error codes or structured statuses can be distinguished. What matters is **never letting missing evidence default to PASS**.

Example aggregator summary:

~~~text
Functional gate    PASS
Performance gate   FAIL (p99 +17.7% > +12% budget)
Operational gate   PASS
Evidence quality   PASS
---------------------------------
Overall            FAIL
~~~

Values are illustrative. Do not add points into an average score so that a critical functional failure is “offset” by good throughput.

### 20.1. Hard-Fail, Soft-Fail, and Warning

Choose levels by risk:

- **Hard-fail:** critical correctness, security, data integrity, ABI contracts, OOM/crash, or critical hard performance ceilings.
- **Soft-fail with owner:** newly added benchmark, high-variance data not yet proving regression, secondary observation metrics.
- **Warning:** non-contract log format changes, trends far from dangerous levels that warrant monitoring.

If soft-fail still allows merging, specify release conditions: a warning in a PR may become a blocker at release candidate time. Do not let warnings linger forever without an owner.

## 21. Flaky Tests and Retry Policy

A flaky test is one that gives different results when code/test conditions should be equivalent. It can stem from races, time dependencies, shared state, environment, or test design.

During a JDK migration, a test that used to be “occasionally red” may fail more often because JIT/scheduler/GC timing changes; that should not be dismissed as “just CI”.

### 21.1. Classifying Root Causes

| Symptom | Likely cause | Handling approach |
|---|---|---|
| Race test fails randomly | Shared mutable state, scheduling. | Fix concurrency/test isolation. |
| Test times out only on shared runners | Resource contention or timeout too low. | Compare runner resources, profile, and budget. |
| Database test has data drift | Fixture state not reset. | Proper isolation/rollback/testcontainers. |
| Test fails only on new JDK | Behavior/API/runtime change. | Reproduce and debug JDK-specific difference. |
| Test passes after multiple retries | Flaky or transient issue; correctness unproven. | Record retry count; investigate rather than taking only the final result. |

### 21.2. Retries Must Not Erase Failure Evidence

A policy may allow 1–2 retries for classified infrastructure errors, yet must record:

- First failure.
- Suspected cause.
- Retry count.
- Result of each attempt.
- Final status and owner.

For critical security/data-integrity tests, keeping only the PASS after retries can mask unstable regressions. Systems should generally block until root cause is found or an explicit exception is approved.

### 21.3. Time-Bound Quarantine

If a flaky test is quarantined:

1. Assign an owner.
2. Document reason and issue.
3. Set a remediation deadline.
4. Assess whether it belongs to critical coverage.
5. If critical, put compensating checks in place before temporarily lifting the gate.

Do not quarantine a test merely because it makes the new candidate FAIL and then claim functionality is qualified.

## 22. Baseline Drift and Updating Thresholds

After a few weeks, hardware, dependencies, or workloads may change, making the old baseline no longer representative.

**Re-baselining** is an approved process for establishing a new baseline, not an automatic overwrite every time the pipeline runs.

### 22.1. When Is Re-Baselining Needed?

- Intentional hardware/CPU architecture or container resource changes.
- Frameworks/algorithms replaced in a major release.
- Workloads/test datasets changed across versions.
- Product SLOs or traffic mix republished.
- Benchmark harnesses/measurement tools upgraded.
- JDK migration completed, and the new version is confirmed as the operational baseline.

### 22.2. Update Steps

1. Archive the old baseline and why it is no longer suitable.
2. Run the test suite in a standard environment with an accepted candidate.
3. Collect multiple measurements, variance data, and metadata.
4. Compare against SLOs/absolute guardrails before approving the new baseline.
5. Obtain approval from responsible owners/teams.
6. Version the baseline + policy, recording effective and review dates.
7. Do not delete historical evidence, as it is needed to spot long-term regressions.

If a metric gradually gets slower, automatically updating the baseline daily can let each run slip only slightly and eventually degrade drastically while still PASSING. Avoid such “ratcheting regression”.

## 23. Waivers and Exception Handling

Not every criterion is always absolute. A migration may accept a performance trade-off to patch a security vulnerability or meet a new product requirement. However, an exception must be an **intentional decision**, not secretly altering thresholds.

A minimal waiver should contain:

| Field | Requirement |
|---|---|
| Gate/metric ID | Which criterion is exempted? |
| Artifact/version | Which candidate does it apply to only? |
| Observed deviation | Concrete deviation and evidence. |
| Business/security rationale | Why is it still accepted? |
| Compensating controls | How is risk mitigated? |
| Owner/approver | Who is accountable and who approved? |
| Expiration | When does it expire or what condition removes it? |
| Follow-up issue | Plan to remediate and re-measure. |

For example, a startup benchmark increasing by 8 seconds due to adding mandatory certificate verification can be assessed in risk context with an approved SLO/timeout adjustment. However, waivers should not be used to overlook authorization failures or severe data loss.

### 23.1. Do Not Turn WAIVED Into PASS

In reports, state clearly:

~~~text
Gate O-Startup: WAIVED until version X, approver Y
Gate F-Authorization: PASS
Gate P-Latency: PASS
Overall release: CONDITIONAL APPROVAL
~~~

The conditional approval status must be visible in internal release notes/decision records. When a waiver expires, the pipeline must revert to policy enforcement.

## 24. From CI to Staging/Canary

CI measures functionality and performance under designed conditions; production traffic is usually more complex and contains long-tail workloads. Therefore, a high-risk migration should have rollout gates.

A sequence:

~~~text
CI quality gates PASS
        │
        ▼
Staging on target JDK/image
        │
        ▼
Synthetic + integration + load checks
        │
        ▼
Canary rollout (small share)
        │
        ▼
Compare SLI/error/latency/memory against controls
        │
   ┌────┴─────┐
   ▼          ▼
PASS         FAIL
   │          │
Expand       Rollback and triage
   │
   ▼
Full rollout + monitoring
~~~

### 24.1. Canary Metrics

Commonly valuable metrics:

- Error rate by endpoint/status, not just aggregate 5xx.
- Tail latency and throughput by traffic segment.
- JVM crashes, OOMKilled, restarts, and health failures.
- CPU throttling, heap/native memory, GC pauses/overhead.
- Database connection pool saturation, queue depth, and timeouts.
- TLS, message retries/dead-lettering, or anomalous data.
- Critical business correctness signals (for example, failed transaction counts).

Compare canary against a control cohort under sufficiently equivalent traffic conditions. If the canary receives only lightweight requests while the control receives heavy requests, direct latency comparison will not reflect JDK impact.

### 24.2. Rollback Gate

Clearly define:

- Which metric violations trigger automatic rollback.
- Observation window and minimum sample count.
- Behavior when the metrics pipeline loses data.
- Maximum time before rolling back.
- Plan to roll back image/JDK/config and DB changes.
- Owners receiving alerts and investigating.

Rolling back a Java binary may be insufficient if the same migration changed database schemas, serialized state, or message formats in a non-backward-compatible way.

## 25. Root-Cause Analysis When Gates FAIL After a JDK Upgrade

When a gate turns red, first determine **what the evidence says** rather than rushing to edit thresholds.

### 25.1. Functional Failure

If unit/contract tests FAIL:

1. Inspect the failing assertion, JDK runtime/version, and stack trace.
2. Determine whether APIs, exception types, serialization, timezone, or charset changed.
3. Compare dependency graphs and test data.
4. Check thread scheduling/races if failures are intermittent.
5. Use the smallest test case to reproduce.
6. If the new behavior is an intentional change, update contracts/tests with review.

### 25.2. Performance Regression

If p95 increases or throughput drops:

1. Check measurement comparability and sample counts.
2. Check CPU quota/cpuset, throttling, and memory limits.
3. Compare JDK flags, GC, active processors, and compiler/JIT behavior.
4. Identify which workloads are affected rather than relying on one aggregate number.
5. Measure allocation, GC pauses, cache hits/misses, DB I/O, and network.
6. Check dependencies/frameworks changed alongside the JDK.
7. Rerun under a bounded policy to separate noise.
8. Fix the root cause or produce a decision record when trade-offs are accepted.

### 25.3. Operational Failure

If OOMKilled, crashed, or not Ready:

1. Distinguish Java OutOfMemoryError from kernel/container OOM kills.
2. Inspect cgroup memory.events, container status, and JVM heap/native metrics.
3. Check startup scripts/systemd/Kubernetes commands/args.
4. Identify removed JVM flags and agent compatibility.
5. Check truststores, TLS, filesystem permissions, and native libraries.
6. Re-test on the actual deployed runtime/OS/architecture.

Do not blame every post-migration failure on the JDK core. Changing base images, container runtimes, build plugins, frameworks, or dependencies can also be the cause.

## 26. Example Acceptance Matrix for Java 17 → Java 21

Suppose a service currently runs Java 17, targets Java 21, and its business contract has not changed. An illustrative matrix:

| Gate | Java 17 baseline | Java 21 candidate | Threshold | Result to report |
|---|---|---|---|---|
| API contract | Current golden fixtures | Run identical fixtures | 0 unapproved breaking differences | PASS/FAIL |
| Auth/data isolation | Mandatory security tests | Run same fixtures | 0 violations | PASS/FAIL |
| Transaction rollback | Failure-path suite | Run on JDK 21 | 100% of required cases PASS | PASS/FAIL |
| CPU-bound component throughput | 15,000 op/s | Example 14,250 op/s | Max -8% | PASS |
| Service p95 | 120 ms | Example 135 ms | Max +10%; ceiling 180 ms | FAIL |
| Service error rate | 0.01% | Example 0.01% | Ceiling 0.10% with sufficient samples | PASS |
| Startup-to-ready | 20 s | Example 23 s | Max +20%; ceiling 30 s | PASS |
| Peak memory | 950 MiB | Example 1,050 MiB | Within approved budget | Per policy |
| OOMKilled/restarts | 0 | 0 | 0 in stability window | PASS |
| Graceful shutdown | Succeeded | Succeeded | Stops within grace period | PASS |

With p95 going from 120 ms to 135 ms, the regression is 12.5%, exceeding the 10% budget. In this example, the overall gate **FAILS** until the regression is resolved or an approved waiver is issued. You cannot conclude “the application passes” merely because all functional tests PASS.

### 26.1. Note on GC Changes

If the new JDK defaults to a different collector/setting, measuring baseline and candidate with default flags reflects both **default policy** and runtime improvements. That is valuable if the product intends to use the new defaults.

If you want to isolate core JDK impact, you can run an additional benchmark with controlled GC/flags, provided the collector/flags are supported on both versions. Do not force an unsupported GC merely to artificially keep environments “identical”.

## 27. Traceable CI Report Architecture

A quality report should contain:

~~~text
Release candidate:
  commit:
  artifact/image checksum:
  dependency lock/BOM:
  JDK vendor/version/update:
  build tool:

Baseline:
  source/version:
  JDK and flags:
  hardware/OS/container:
  policy version:

Functional:
  required suites:
  executed/passed/failed/skipped:
  failing contract IDs:

Performance:
  scenario and dataset:
  run count/warmup/measurement:
  raw result locations:
  baseline/candidate summaries:
  variation/uncertainty:
  per-metric budget and outcome:

Operational:
  startup/readiness:
  memory/CPU/cgroup limits:
  heap/GC/native metrics:
  OOM/crashes/restarts:
  TLS/agent/shutdown:

Decision:
  PASS / FAIL / INCONCLUSIVE / WAIVED:
  blockers:
  waived metrics + approvals:
  next action and owner:
~~~

Do not replace metrics with a single line “Performance OK”. Baseline, candidate, units, thresholds, variance, and scenario IDs are needed so others can re-verify.

### 27.1. Raw Data and Summaries

Raw measurements should be retained per retention policy to investigate discrepancies; summaries help approvers read quickly. Metrics must be tied to the exact artifact commit/JDK/hardware/test profile to avoid cross-comparing results from two different pipelines by mistake.

Do not store private production payloads, tokens, or secrets in benchmark artifacts. If tests use production-like data, an anonymization process or safe synthetic data must be in place.

### 27.2. Do Not Overwrite PASS/FAIL History

When a gate is rerun, preserve history or at least reference the first attempt and reason. If only the final PASS result is kept, the team loses the ability to detect CI instability and track long-term trends.

## 28. Checklist Before Making a Quality Gate a Required Check

### 28.1. Functional

- [ ] Inventory of critical user journeys and contract IDs exists.
- [ ] Required suites are discovered and executed on the target JDK.
- [ ] No critical tests are skipped/quarantined uncontrollably.
- [ ] API/binary compatibility has a policy for public libraries.
- [ ] Serialization, persistence, time/locale, security, and concurrency have appropriate tests.
- [ ] Intentional changes are versioned and reviewed.

### 28.2. Performance

- [ ] Baseline is approved and has complete metadata.
- [ ] Runner/hardware/JDK/resources/workload are equivalent.
- [ ] Warmup, measurement, and independent runs are defined.
- [ ] Metrics have clear units and desired directions.
- [ ] Hard ceilings/floors and regression budgets are defined where needed.
- [ ] Policies exist for baseline 0, missing data, and variance.
- [ ] Not self-passed by taking a lucky rerun.
- [ ] p95/p99 have sufficient sample volume and consistent calculation methods.

### 28.3. Operational

- [ ] Startup/container/JDK/version and agents match the target runtime.
- [ ] Resource limits, Xmx/native headroom, and GC are measured.
- [ ] OOMKilled, crashes, restarts, throttling, and probes have evidence.
- [ ] SIGTERM/graceful shutdown has been tested on the appropriate topology.
- [ ] Logs, metrics, and alerts are present and do not expose secrets.
- [ ] TLS/truststore/native dependencies have integration tests.

### 28.4. Policy and CI Operations

- [ ] Policy file is versioned and has an owner.
- [ ] FAIL/INCONCLUSIVE cannot be automatically interpreted as PASS.
- [ ] Required jobs and release gating are clear.
- [ ] Rebaselining/waivers have approvals, expiration, and audit trails.
- [ ] Metric artifacts include checksum, JDK, and environment metadata.
- [ ] Staging/canary/rollback criteria exist for high-risk releases.

The checklist guides CI design in real products; checking off an item requires evidence, not assuming verification occurred merely because configuration exists in the repository.

## 29. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| “A green build means migration succeeded.” | Runtime/performance bugs go undetected. | Have functional, performance, and operational gates. |
| Setting thresholds after looking at the candidate | Tailoring results to desired outcomes. | Define policy upfront, version, and review. |
| Taking baseline from any arbitrary run | Easily noisy or contains regressions. | Approved, repeated baseline with full metadata. |
| Comparing benchmarks across different CPUs/hardware | False regressions/improvements. | Use equivalent runners and workloads. |
| Comparing only average latency | Misses tail/timeouts. | Measure p95/p99, error rate, and sufficient samples. |
| Comparing only % without absolute bounds | Can PASS while violating SLO. | Combine hard ceilings/floors and regression budgets. |
| Having only absolute SLO bounds | Allows large regressions below the ceiling. | Add relative regression budgets. |
| Defaulting missing metrics to 0 | False gate PASS. | Fail closed or INCONCLUSIVE. |
| Retrying until PASS | Masks flaky regressions. | Bounded rerun policy, keep history. |
| Auto-updating baseline daily | Gradual degradation goes unnoticed. | Rebaseline with approval. |
| Tests pass on build JDK, not run on minimum JDK | Risk of runtime dependency failures. | Run Test JVM/real artifacts on supported JDKs. |
| Xmx is below limit so OOM cannot happen | Native/off-heap still consumes memory. | Measure cgroup peak and headroom. |
| Treating CPU throttling as a harmless secondary metric | Can severely inflate tail latency. | Tie metric to workload/SLO. |
| Evaluating p99 from very few requests | Unreliable percentile. | Sufficient sample volume and measurement window. |
| Benchmark passes because failed requests were excluded | Candidate looks fast yet errors heavily. | Gate error rate and define latency population. |
| Computing an average score across all gates | Security flaws “offset” by throughput. | Independent critical hard-fails. |
| Waivers without expiry/owner | Quality debt drags on indefinitely. | Time-bound and audited waivers. |
| Treating Pod Running as Ready/Healthy | Misses probe/traffic failures. | Runtime readiness and integration checks. |
| Only CI, no rollout gates | Misses production behavior. | Canary/SLO checks and rollback plans. |

## 30. Step-by-Step Process for Implementing Acceptance Thresholds

**Step 1 — Define the support contract.** Record minimum/target JDKs, OS, architecture, API compatibility, and mandatory preserved behaviors. Specify business-critical journeys and security/data invariants.

**Step 2 — Lock in the baseline.** Select representative release/artifact/JDK/workload; save checksums, dependency locks, hardware/container metadata, and raw measurements.

**Step 3 — Categorize metrics.** Split into functional, performance, and operational; define units, direction, time window, source of truth, and owner for each metric.

**Step 4 — Define thresholds upfront.** Use hard ceilings/floors, regression budgets, and evidence quality rules. For critical functional tests, require 0 violations in the defined test set.

**Step 5 — Establish controlled runners.** Lock resource limits, datasets, tool versions, warmup, samples, and test harnesses; avoid noisy neighbors for sensitive performance measurements.

**Step 6 — Run the JDK matrix.** Test on the new JDK and runtimes still declared as supported. Separate build JDK outcomes from runtime JVM outcomes. Check dependency artifacts and class-file levels.

**Step 7 — Integrate the gate engine.** Read structured results and versioned policies; distinguish PASS/FAIL/INCONCLUSIVE. Missing data must never default to PASS.

**Step 8 — Diagnose failures.** Classify correctness, noise, runtime resources, GC/JIT, dependencies, or deployment. Reproduce rather than merely changing thresholds.

**Step 9 — Record the decision.** Save per-metric results, raw data, JDK/runtime metadata, waivers, and approvers.

**Step 10 — Deploy with guardrails.** After CI PASSES, proceed to staging/canary per policy. Monitor errors, tail latency, memory, OOM, restarts, and roll back upon violations.

**Step 11 — Maintain thresholds.** Review noise, product changes, and rebaseline through an approved process. Do not let the baseline automatically drift toward the latest results.

## 31. Conclusion

**Setting functional, performance, and operational acceptance thresholds in CI** is the mechanism that turns Java compatibility migration from “run tests and see if they are green” into **a criteria- and evidence-driven release decision**. Functional gates protect API/data/security contracts; performance gates measure deviations from baselines and hard limits in controlled environments; operational gates verify the JDK, container resources, startup, readiness, logs, GC/memory, shutdown, and recoverability.

There is no single latency regression percentage or MaxRAMPercentage right for every product. Thresholds must be chosen based on user experience, SLOs, workloads, measurement noise, and business risk levels. Baselines need provenance, measurements must be reproducible, missing data must be clearly classified, and waivers must have owners and expirations.

The ultimate goal is not **making every CI cell green at all costs**, but rather **knowing precisely what has been verified, what has not, what level of degradation is allowed, and when to block or roll back**. When those rules are governed alongside artifacts, the JDK/runtime matrix, and rollout policies, teams can upgrade Java transparently, protect existing contracts, and catch regressions early enough before impacting users.
