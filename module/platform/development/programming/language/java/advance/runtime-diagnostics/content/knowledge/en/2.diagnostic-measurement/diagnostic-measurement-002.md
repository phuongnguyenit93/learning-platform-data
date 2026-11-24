# 2.2 Establishing a Healthy Baseline and Recording Measurement Conditions

A number like "70% CPU", "p95 = 180 ms", or "600 MiB heap used" is **not enough** to conclude a Java application is abnormal. You need to know which build it was measured on, at what load, whether the JVM was warmed up, over what time window, what the actual CPU/RAM limits were, and how the system normally behaves beforehand.

A **baseline** (reference benchmark) is a set of metrics with its context, collected via a method consistent enough to compare against another measurement. Establishing a baseline is not simply taking a dashboard screenshot: you must define what "normal" means, choose metrics, fix or record measurement conditions, collect sufficient samples, and preserve verifiable evidence.

This lesson focuses on **measurement methodology** in Java runtime diagnostics: building a trustworthy baseline, recording measurement conditions, avoiding bias from warm-up/JIT/GC/load/containers, and using the baseline to evaluate variance instead of jumping to root-cause attributions.

## 1. Understanding Baselines, Normal State, and Quality Thresholds

### 1.1 A Baseline Contains Both Metrics and Measurement Conditions

A minimal baseline record answers four groups of questions:

1. **What is measured?** E.g., p50/p95/p99 latency of an endpoint, throughput, error rate, CPU, GC pauses, heap used, queue depth.
2. **Where and with what is it measured?** Which JVM/process/container/host, which tool and version, and what units and calculation method each metric uses.
3. **Under what conditions is it measured?** Build, JDK/JVM/flags, GC, allocated resources, data, request types, arrival rate, concurrency, dependencies, warm-up, measurement duration.
4. **Is the data trustworthy for comparison?** How many requests/samples, any dropped samples, synchronized clocks/windows, repeated runs, any unexpected system incidents.

Therefore, a baseline can be summarized as:

```text
Baseline = measurement conditions / scenario
         + time-series metrics with units and timestamps
         + data collection / processing method
         + quality checks and run-to-run variance
```

If the conditions are missing, the numbers lack context for comparison; if raw numbers and methodology are missing, conclusions are hard to reproduce.

### 1.2 "Normal" Does Not Mean "Meeting Requirements"

Separate three concepts:

| Concept | Answers the Question | Example |
| --- | --- | --- |
| **Baseline** | Under defined conditions, what results does the system typically produce and how much does it vary? | Under a fixed scenario, p95 fluctuates around 85–95 ms across multiple runs |
| **SLO / acceptance criteria** | What quality level *must* the system achieve? | At least 99.9% of requests succeed within the specified window |
| **Alert threshold** | When should an anomaly or quality violation be investigated? | Alert when p95 rises sustainably above baseline and request count is large enough |

A baseline taken from a system that is already slow can very consistently reproduce that slowness. It is still a baseline describing the current state, yet **does not prove** the system meets its SLO. Conversely, an application with p95 lower than baseline can still violate its SLO on 5xx errors or availability.

There is no universal 10%, 20%, or 30% increase threshold valid for every system. Normal variance, user impact, and measurement uncertainty determine when attention is warranted.

### 1.3 Normal Is a Clearly Described *Set of Conditions*

For Java services, you typically need to distinguish at least the following contexts if they matter in practice:

- **Cold start:** application startup, class loading, pool initialization, cold caches; timing/CPU/IO can differ from steady state.
- **Warm-up:** JIT compiling hot execution paths, caches and connection pools gradually reaching operating state; do not assume stabilization after a fixed duration.
- **Steady state:** load and target metrics are relatively stable within the observation window; GC, slow requests, and normal variance still occur.
- **Normal peak:** expected peak by hour or workload; should have its own baseline rather than comparing low load to high load.
- **Batch/maintenance:** background jobs, compaction, backups, or scheduled tasks can shift the profile; explicitly record whether they are running.

Do not lump every state into a single "normal" number and use it to explain all situations. When production has multiple load profiles, use per-profile baselines or condition on the appropriate variables.

## 2. Choose a Repeatable Scenario Before Measuring

A useful baseline ties to a specific diagnostic question. For example: "At a write rate of 50 requests/second, what p95 latency and CPU usage does the create-order endpoint exhibit on this build?" is completely different from "How much CPU does the application consume when idle?".

### 2.1 Define the Workload as a Measurement Contract

Explicitly record:

- **Paths:** endpoint/message type/batch job, read-write operation mix, payloads, data sizes, and response types.
- **Input load:** requests/s actually *sent* (offered rate), requests/s completed (throughput), concurrency/in-flight, think time, connection hold time, and retries.
- **Data:** table/collection size, key distribution, cache hit ratio, data ordering, schema version, new vs. existing data.
- **Dependencies:** DB, cache, broker, DNS, third-party services; latency, pool limits, and topology. A "slow DB today" changes the application's baseline even with unchanged code.
- **Distribution:** ramp-up, burst, steady, periodic; error rate and timeouts are also workload characteristics and must not be omitted.
- **Success criteria:** rules allowing a dataset to be accepted as a healthy baseline—e.g., no deploys mid-run, no unexpected infrastructure faults, sufficient traffic, clean logs.

**Offered load is not throughput.** If clients send the next request only after the previous one completes (closed-loop model), a slow service can *reduce the sending rate itself*, making metrics look "lightly loaded". For arrival-rate tests, measure both the request generation schedule and completed requests; use load generators aware of **coordinated omission** (failing to record waiting time when the generator stops issuing requests on schedule because the system stalls).

### 2.2 Fix What Must Be Fixed, Record What Cannot Be Controlled

To compare two runs A/B, you do not need to claim the entire environment is strictly identical; you need to **know what is the same, what changed, and the potential impact of the differences**.

| Condition Group | Minimum to Save | Why Can It Skew the Baseline? |
| --- | --- | --- |
| Code and config | Commit/build ID, image digest, feature flags, pool/cache config, log level | Same version tag can still run a different artifact or flags |
| Java runtime | Java vendor/version/build, JVM implementation, `-Xms`/`-Xmx`, GC, JVM flags, `JAVA_TOOL_OPTIONS` if used | JIT, GC, ergonomics, sizing vary across runtimes or flags |
| Resources | CPU cores/quota, affinity, memory limit, host/VM type, container requests/limits, replica count | CPU throttling and memory pressure increase latency |
| Workload | Script/version, arrival rate, concurrency, payload, endpoint mix, dataset, and seed | Changing work volume and type breaks comparability |
| Dependencies | DB/broker/cache versions, topology, pool limits, external latency | The bottleneck may reside in another system |
| Measurement | Instrumentation/profiler, sampling, scrape interval, histogram buckets, exporter version | Tools introduce overhead or change calculation semantics |
| Timing | UTC start/end, display timezone, warm-up, run count, deploy/GC/backup events | Wrong window mixes cold start with steady state |

Do not store passwords, tokens, connection strings with secrets, or personal data in the baseline manifest. For sensitive flags/env vars, record the configuration version or sanitized values sufficient to prove the measurement conditions.

## 3. Choose Metrics Across Application, JVM, and OS Layers

Measuring thoroughly does not mean collecting every metric that exists. Start from the hypotheses you need to distinguish, then pick a complementary set of metrics.

### 3.1 Application Layer and User Outcomes

A useful set for HTTP/services:

| Metric | Unit / How to Read | Points of Caution |
| --- | --- | --- |
| Request count | count of requests in window | Define whether retries and timeouts are counted |
| Offered request rate | requests/second from client/generator | Distinguish requests sent from requests finished by server |
| Throughput | completed requests/second | Do not infer latency from throughput alone |
| p50/p95/p99 latency | ms from distribution of same-type/same-window requests | p99 is sensitive to sample count; avoid averaging percentiles |
| Error rate | errors / total valid requests, % | Record error types: 4xx/5xx/timeout/transport/application |
| In-flight, queue length, pool utilization | count or % | Clarify metric definition and pool limits |
| Dependency latency | ms per DB/cache/broker/call | Measuring end-to-end alone may fail to locate the slow layer |

A 500 ms request might spend 450 ms waiting on the database, 30 ms in application processing, and 20 ms elsewhere. To know whether the Java runtime has an issue, you need phase breakdowns or sufficiently detailed traces; total latency alone is not enough.

### 3.2 JVM: Measure Runtime Behavior in the Same Window

- **GC:** count, total pause time, pause distribution, allocation rate, heap occupancy before/after GC. A single long pause outside the latency window cannot automatically explain slow requests inside the window.
- **Memory:** used/committed/max heap, metaspace, code cache, direct/native memory when observable; compare against RSS and memory limit. `-Xmx` is not total process RAM.
- **Threads and contention:** live platform thread count, deadlock/blocked/waiting, executor queues, lock waits; virtual threads (Java 21+) do not map 1:1 to native OS threads.
- **Compilation/class loading:** JIT warm-up, class loading, and compilation can make startup measurements differ from steady state.
- **JFR / MXBeans / GC logs:** complementary sources to correlate runtime events with anomalies seen in application metrics. Record recording type and overhead if applicable.

Avoid comparing JVM CPU when one run has a heavy profiler enabled and the other does not; observation itself can alter the system. Record whether instrumentation is present across all runs or only in one diagnostic session.

### 3.3 OS, Container, and Host: Actual Resources Available to the JVM

- CPU by **process and thread**, utilization relative to allowed CPUs, CPU throttling, and runnable queue when available.
- RSS and container/cgroup usage, memory limit, OOM events; page cache and native memory depending on accounting mechanism.
- Disk latency/IOPS/throughput, network errors/RTT, open file descriptors/socket states.
- VM CPU steal, host contention, or noisy neighbor when observable by tools.

For example, 20% average host CPU utilization does not rule out container CPU throttling due to a low quota. Conversely, a drop in heap used does not imply RSS drops immediately. When capturing a baseline, record the **metric scope**: host-wide, container, process, or per-thread.

### 3.4 Prioritize a Lean but Cross-Checkable Metric Set

A steady-state service measurement typically starts with four groups:

1. **Outcomes:** throughput, latency distribution, error rate.
2. **Pressure:** concurrency, queue/in-flight, pool utilization.
3. **JVM:** heap trend, GC pauses/frequency, thread count, and relevant runtime events.
4. **System:** process CPU, quota/throttling, RSS/limit, disk/network when suspected.

Once differences appear, increase detail—for instance, JFR recordings or thread dumps around the anomaly timestamp. Capturing full profiles on every baseline run is costly and prone to altering measurement conditions.

## 4. Choose Windows, Cadence, and Calculations for Meaningful Numbers

### 4.1 Each Run Should Have Clear Phases

Example for a fixed load test:

```text
Prepare data / system
      |
      v
Start JVM and dependencies
      |
      v
Warm-up: apply representative load, wait for stability
      |
      v
Steady-state official measurement: record start/end time
      |
      v
Cooldown / stop load
      |
      v
Save metrics, raw samples, JFR/logs, and manifest with run ID
```

**Do not include warm-up in a steady-state baseline** if steady state is the goal; you can still save it as a separate dataset. Never assume warm-up always finishes in exactly 30 seconds: it depends on the application, JIT, caches, connection setup, GC, and load. Observe throughput, latency, compilation/GC, and caches until relatively stable under target conditions.

A run may contain multiple measurement intervals, but clearly mark which interval is official. If measuring startup too, separate startup time and first-request latency instead of blending them into steady-state p95.

### 4.2 Wall-Clock Time, Monotonic Time, and Window Alignment

- Use **UTC wall-clock** to align timestamps across machines, logs, and dashboards; store timezone as well if UI displays local time.
- Use a monotonic clock like `System.nanoTime()` to measure **elapsed duration within the same JVM**; do not convert `nanoTime()` values into calendar timestamps. Do not use `System.currentTimeMillis()` as the primary source for short intervals because wall-clock time can be adjusted.
- When comparing events across JVM, container, DB, and load generator, ensure clock synchronization is tight enough or record skew; check time ranges and timezones.
- Record **scrape interval**, query step, aggregation window, and missing-sample handling. Do not compare a 5-minute metric point directly against a 10-second latency histogram and claim causality.

For example, a GC pause at 10:02:15Z only helps explain a p99 spike if the corresponding latency window and requests cover that interval, without timestamp skew, and with sufficient source resolution.

### 4.3 Counters, Gauges, Histograms: Avoid Wrong Denominators

A **Counter** accumulates events: compute rate over a window as counter delta / seconds; watch for resets on process restart. A **Gauge** is an instantaneous value or state measurement (heap used, queue depth): min/max/avg over time can be taken while preserving its definition. A **Histogram/timer** represents a distribution of observations: used to derive percentiles when enough samples exist.

Example: from 12:00:00 to 12:01:00 UTC, if the completed counter increases by 12,000, average throughput in the window is `12,000 / 60 = 200 requests/second`. If there are 24 errors in 12,000 completions, the error rate is `24 / 12,000 × 100 = 0.2%`. Both calculations are valid only if numerator and denominator define the same subject and same window.

Percentiles require keeping **distributions or mergeable histograms**:

- p95 = the value that roughly 95% of observations do not exceed, depending on interpolation/estimation method. Different measurement systems may calculate percentiles differently.
- **Do not average per-minute p95 values to get the overall window p95.** Two minutes have different request counts and different distributions; "mean of p95s" does not equal the percentile of combined data.
- When aggregating across endpoints/instances, know how histograms merge, bucket resolution, and labels so you do not mix fundamentally different requests.
- Distinguish metrics for **successful requests** from all completed requests; dropping timeouts can make p99 look artificially good.
- With few samples, p99 is close to the maximum and highly volatile. Always store `count` alongside every percentile.

### 4.4 Repeat Runs and Describe Variance

One good run does not make a baseline. Collect multiple independent runs under equivalent conditions (e.g., at least three runs as a practical starting point, **not a universal statistical rule**). Between runs, you may vary timing or reset data if the scenario requires; record the exact procedure.

For each metric, save:

- Per-run values and sample counts, not just one aggregate number.
- Median/spread across runs, min-max range, or appropriate quantile range; retain raw data for reanalysis.
- Signs of trend and possible skew from hot caches, JIT, background load, GC, or CPU throttling.
- Excluded windows and **predefined exclusion reasons**; never discard a run merely because the result looks "bad".

If the system varies by hour of day, peak and off-peak baselines make more sense than a single average that erases cycles. Baselines must be intentionally updated when technology, load, or architecture changes, with change history and update criteria.

## 5. Record Measurement Conditions in a Verifiable Manifest

Create a separate condition record for **each run**, linking the run ID to data/recordings/logs. Below is a **hypothetical illustrative example**, not the configuration or result of an existing system:

```yaml
baseline:
  baseline_id: "order-api-steady-50rps-v1"
  run_id: "order-api-steady-50rps-r03"
  status: "accepted"
  purpose: "Compare p95, throughput, CPU, and GC between two builds"
  run_window_utc:
    warmup_start: "2026-10-28T09:00:00Z"
    measurement_start: "2026-10-28T09:10:00Z"
    measurement_end: "2026-10-28T09:20:00Z"
    sampling_interval_seconds: 10
  application:
    artifact: "order-api"
    commit: "a7b8c9d"
    image_digest: "sha256:example-digest-for-documentation"
    feature_flags_profile: "profile-A-v2"
    replica_count: 1
  runtime:
    java_vendor: "Example JDK distribution"
    java_version: "21"
    gc: "G1"
    heap_initial_mib: 512
    heap_max_mib: 512
    jvm_flags_profile: "jvm-flags-v3"
  infrastructure:
    environment: "isolated-load-test"
    container_cpu_limit_cores: 2
    container_memory_limit_mib: 1536
    host_type: "documented-test-vm"
  workload:
    script_version: "create-order-v4"
    model: "constant-arrival-rate"
    offered_rps_target: 50
    payload_profile: "small-order-v2"
    dataset_version: "seed-order-100k-v3"
    dependencies_profile: "db-and-cache-test-v2"
  collection:
    latency_scope: "end-to-end client observed, all completed"
    histogram_scheme: "latency-hist-v2"
    metrics_collector_version: "collector-v3"
    tracing_sample_probability: 0.1
    jfr_enabled: false
  quality_gate:
    requests_completed: 30000
    unexpected_infrastructure_incidents: 0
    collection_gap_seconds: 0
    notes: "No deploys during measurement window"
  artifacts:
    request_histogram: "run-r03-latency.hist"
    timeseries: "run-r03-metrics.json"
    environment_snapshot: "run-r03-environment.json"
```

**How to use the manifest:** values like `commit`, `image_digest`, `jvm_flags_profile`, and artifact paths must be replaced with actual data from the run itself; the string `example-digest-for-documentation` in the example only illustrates structure and is not a valid deployable digest. In real deployments, store valid hashes/digests, raw data, and corresponding access permissions. If a field cannot be measured, explicitly record "not observed" along with its impact on comparability; never silently assume equality.

The example above has a 600-second measurement window and a 50 requests/second target, so **30,000 completed requests** is only plausible if throughput actually reached target with no backlog left over or counting errors. Do not use multiplication to "fill in pretty numbers"; `requests_completed` must come from measured metrics.

The condition record should also reference access permissions for JFR/GC logs/tracing and retention periods. For production, watch out for sensitive data in logs, request payloads, JFR stack traces, or heap dumps. The manifest can omit raw payloads and instead use profile names and dataset checksums containing no secrets.

## 6. Collect Evidence Inside the JVM and Runtime Environment

Choose tools based on measurement goals. The commands below illustrate the type of information to collect, not an automated script applicable to every machine.

### 6.1 Identify the Exact Process's Java Runtime/Flags

```bash
java -version
jcmd -l
```

`java -version` reflects the `java` binary in your current terminal; if the service uses a different Java executable, that output is **not enough**. From the process list, identify the right PID and query it, e.g., with hypothetical PID `4242`:

```bash
jcmd 4242 VM.command_line
jcmd 4242 VM.flags
jcmd 4242 GC.heap_info
```

`jcmd` is usually present in JDK/HotSpot, though minimal runtime containers may omit it; attaching may be blocked by permissions, PID namespaces, or JVM flags. `jcmd 4242 GC.heap_info` only gives state at the moment of reading and does not replace time-series GC metrics. When comparing A/B baselines, read both startup flags and **effective flags** if available; the same `-Xmx` does not guarantee the same GC or processor count.

### 6.2 Cross-Check OS/Container Limits

On Linux, pick the PID and cgroup of the exact process. In a cgroup v2 environment mounted at the conventional path, you can inspect:

```bash
cat /proc/4242/status
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
```

These are example commands for PID `4242` and its corresponding cgroup; if run from the host, another container, or a different namespace, `/sys/fs/cgroup` does not necessarily point to the service's cgroup. On cgroup v1 and other OSes, interfaces differ. For `cpu.max`, two values quota/period represent the CPU limit, or `max` means no quota is enforced at that level. You should also capture CPU throttling counters when proving CPU starvation; looking at CPU utilization alone is insufficient.

Before/after benchmarks, keep snapshots of process/container resource limits to catch cases where quota, replica count, or host accidentally changed for one run. Metrics must clearly state units: bytes vs. MiB, cores vs. percentage of one core, ms vs. seconds.

### 6.3 Collect in Increasing Order of Intrusion

Depending on the question, start with application metrics, JMX/MXBeans, exporters, and already-enabled GC logs; continue with controlled JFR recordings; and finally capture heavy profiling or dumps only in suitable environments.

For example, heap dumps can be huge, contain sensitive data, and incur significant pause/IO cost; do not capture heap dumps by default in every baseline measurement. NMT must be enabled at JVM startup to have corresponding data, and carries its own overhead. If tools are toggled between runs, explicitly record that change in the manifest and assess whether results remain comparable.

## 7. Java 17+ Practice: Computing Metrics for a Sample Window

The following example **computes summary statistics from fixed data** and does not pretend to measure production CPU or latency. It illustrates how percentiles depend on sample data and must be accompanied by `count` and measurement interval. Java 17+ can compile/run it directly.

Save as `BaselineWindowDemo.java`:

```java
import java.util.Arrays;
import java.util.Locale;

public class BaselineWindowDemo {
    static long percentileNearestRank(long[] sorted, int percentile) {
        if (sorted.length == 0 || percentile < 1 || percentile > 100) {
            throw new IllegalArgumentException("invalid percentile or empty data");
        }
        int rank = (int) Math.ceil(percentile / 100.0 * sorted.length);
        return sorted[rank - 1];
    }

    public static void main(String[] args) {
        long[] latencyMs = {8, 11, 11, 13, 17, 20, 26, 45, 90, 120};
        Arrays.sort(latencyMs);

        long completed = latencyMs.length;
        long errors = 0;
        double measurementSeconds = 2.0;

        System.out.println("count=" + completed);
        System.out.println("p50_ms=" + percentileNearestRank(latencyMs, 50));
        System.out.println("p95_ms=" + percentileNearestRank(latencyMs, 95));
        System.out.println("p99_ms=" + percentileNearestRank(latencyMs, 99));
        System.out.printf(Locale.ROOT, "throughput_rps=%.1f%n",
                completed / measurementSeconds);
        System.out.printf(Locale.ROOT, "error_rate_pct=%.2f%n",
                errors * 100.0 / completed);
    }
}
```

Compile and run:

```bash
javac BaselineWindowDemo.java
java BaselineWindowDemo
```

**Exact** stdout for the fixed data:

```text
count=10
p50_ms=17
p95_ms=120
p99_ms=120
throughput_rps=5.0
error_rate_pct=0.00
```

**Explanation:**

- This is the **nearest-rank** method: sorted ascending, the position of p95 is `ceil(0.95 × 10) = 10`, so the value is 120 ms. Another system might interpolate percentiles or use approximate histograms and yield a different result.
- With only 10 observations, both p95 and p99 equal the maximum value. **Do not use ten points as a production p99 baseline**. Comparing tail latency requires many more observations, sufficient duration, and a consistent statistical method.
- Throughput of 5 requests/second over **2 seconds** is illustrative synthetic data. Setting `measurementSeconds = 2.0` does not make the program generate or measure requests for 2 seconds.
- The code does not measure durations via `System.nanoTime()`, does not separate timeouts from successful requests, and does not collect errors from a real system. When building a production collector, events must be recorded and categorized properly before applying statistics.

If you need to measure duration for a real operation **inside the same JVM**, you can take two `System.nanoTime()` readings around the work being observed and take the difference. However, manual microbenchmarks easily mislead due to JIT, dead-code elimination, GC, warm-up, and OS noise; for method-level performance benchmarks, prefer **JMH** and build a scenario with clear controls. Service diagnostic baselines should measure real request flows or representative workloads rather than extrapolating from a console-printing loop.

## 8. Reading Multi-Run Baselines and Comparing Before–After

Suppose three steady-state runs with the same load profile yield the following **hypothetical** dataset:

| Run | Completed requests | Throughput (req/s) | p95 latency (ms) | Error (%) | Process CPU (avg cores) |
| --- | ---: | ---: | ---: | ---: | ---: |
| A1 | 30,006 | 50.01 | 90 | 0.10 | 0.74 |
| A2 | 29,994 | 49.99 | 93 | 0.10 | 0.77 |
| A3 | 30,000 | 50.00 | 88 | 0.10 | 0.75 |

The numbers above were invented to practice reading tables, **not data collected from any spreadsheet or machine**. Three runs can only be treated as equivalent when conditions and measurement methods truly match. The hypothetical window per run is 600 seconds; throughput = completed/600. CPU "0.75 cores" differs from saying "75% CPU" on a multi-core host.

In the example, the median of the **three per-run p95 values** is 90 ms; this is the "median of per-run p95s", **not the pooled p95 of 90,000 requests**. Only with the raw histograms can you compute the combined distribution p95 properly. You should keep individual runs to inspect variance and avoid hiding differences.

A build B measured under the same conditions shows p95 = 117 ms across three runs with matching load and resources. Compared to the representative baseline of 90 ms, the relative difference is:

```text
Delta p95 (%) = (p95_B - p95_A) / p95_A * 100
              = (117 - 90) / 90 * 100
              = +30%
```

**Correct interpretation:** reported p95 is 30% higher than the chosen reference value. You cannot yet conclude "code B caused slowness" if CPU quota, DB, dataset, time window, instrumentation, or histogram aggregation changed; nor is statistical confidence established from a single run of B. The change must be repeated or cross-checked against baseline variance and evidence across related layers.

### Verifiable Comparison Rules

1. **Compare the right quantities:** same metric name, unit, endpoint labels, error definition, percentile estimator/histogram, and window duration.
2. **Compare under matching conditions:** version, workload, data, heap/GC, CPU/memory limits, dependencies, collector. When conditions differ, record which condition is the test variable and which are confounders.
3. **Compare the distribution:** p50, p95, p99, max, errors/timeouts, and count; do not cherry-pick one "pretty" percentile.
4. **Compare across multiple runs:** does the difference exceed normal variance, repeat consistently, and correspond to rises in GC/CPU/IO/queues?
5. **Preserve decision trace:** conclusion, evidence links, run IDs, methodology, and limitations; a baseline is not a number that silently auto-updates without history.

## 9. Java-Specific Situations That Easily Skew Baselines

### 9.1 Unwarmed JVM / Shifting JIT

Java application startup involves class loading, lazy initialization, cache filling, and JIT compilation. With varying workloads, hot code paths in one run may differ from another. Therefore record startup time, warm-up profile, and only start steady-state under predefined conditions. If the goal is cold-start latency, measure cold start **as a separate scenario**.

### 9.2 Different GC and Heap Behavior Masked by Equal Throughput

Two builds may achieve identical throughput while one has a high allocation rate, long GC pauses, or RSS close to the container limit—carrying very different risk. Record GC algorithm, heap settings, pause distribution, used/committed heap, and resource limits. One stray long GC outside the measurement window can make a baseline unrepresentative; sufficient duration and multiple runs are required.

### 9.3 CPU Throttling / Host Contention

The same "2 cores" across two environments may differ in CPU microarchitecture, virtualization, noisy neighbors, affinity, quota, and scheduling. If one run is continuously throttled while the other is not, you cannot attribute all differences to code. Record limits and throttling counters alongside latency, especially in containers/Kubernetes.

### 9.4 Caches, Datasets, and External Dependencies

A hot-cache run and a cold-cache run are not equivalent. Adding a DB index, changing row counts, or changing data distribution can also alter query plans and latency. Keep dataset snapshots/seeds or explicitly declare cache/dependency states; when production data shifts naturally, build baselines per condition group rather than treating them as static.

### 9.5 Observation Alters the System

Enabling debug logging, continuous stack sampling, Java agents, native profilers, or heavy JFR configs all add overhead. For before/after comparisons, keep measurement consistent; if deep profiling is needed to locate a root cause, mark that run as a **diagnostic profile** and avoid mixing it into unprofiled baselines.

### 9.6 Dropped Samples, Resets, and Under-Sampled Percentiles

Missed scrapes, exporter restarts, counter resets, or trace-sampling drops can break continuity. A p99 from a few dozen requests does not represent tail latency; overly coarse histogram buckets lack resolution. Always check count, histogram coverage, and observability pipeline health before trusting charts.

## 10. Common Pitfalls and Self-Checks

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Taking one CPU point as "normal baseline" | Lacks workload, scope, and variation over time | Record run window, request rate, process/cgroup CPU, and repeat |
| Comparing p95 from different endpoints or windows | Different request distributions, calculation, and sample counts | Match labels, window, histogram algorithm, and sample count |
| Aggregating p95 by simple averaging | Percentiles do not add/average like counts | Merge raw observations or compatible histograms |
| Omitting JDK/GC/flags | Runtime changes latency and memory | Save runtime identity, startup/effective flags, GC, and heap |
| Saying "host is idle" means "container has enough CPU" | Quotas and throttling are independent of spare host CPU | Measure cgroup quotas and throttling alongside process CPU |
| Mixing warm-up and steady state | Includes class loading/JIT/cache fill unrelated to target | Define separate phases and windows |
| Switching measurement tools between A and B | Overhead and semantics can differ | Keep collection profile constant; document any change |
| Treating baseline as SLO | Stable current state can still be poor quality | Evaluate baseline against separate business objectives |
| Deleting bad runs without stating reasons | Introduces result selection bias | Define exclusion criteria beforehand, keep audit trail |
| Failing to save raw data or manifest | Impossible to re-verify conclusions when metrics change | Save run ID, data, conditions, calculation method, and tool versions |

You can safely execute a "mini-baseline" for a Java service yourself:

1. Pick one request path, one load level, and one clear latency definition.
2. Record build, JDK/GC/flags, CPU/memory limits, dataset, dependencies, measurement tools, and UTC timestamps.
3. Separate warm-up from a 5–10 minute measurement *if the scenario and request rate fit*; actual duration must be governed by statistical confidence and GC/load cycles, not treating 5–10 minutes as a universal standard.
4. Collect per-request histograms/counts/errors, throughput, queues, JVM GC/heap, and process/container CPU and memory; keep windows aligned.
5. Repeat under the same profile, save raw data, and note variance.
6. When signs deviate from baseline, cross-check changed variables before concluding root cause.

## 11. Checklist for Accepting a Baseline for Diagnostics

- [ ] **Identity:** exact service, build/commit, runtime/JVM, process/container/host, and run ID.
- [ ] **Conditions:** workload, payload, offered load, dataset, dependencies, flags, quotas/limits, and measurement profile are described.
- [ ] **State:** cold start/warm-up/steady-state/peak cleanly separated; official window has UTC timestamps.
- [ ] **Metrics:** units, sources, scopes, denominators, sample counts, sampling intervals, and percentile method defined.
- [ ] **Reliability:** no severe missing data, counter resets handled, excluded runs documented with reasons.
- [ ] **Variance:** multi-run metrics present, or limitations explicitly noted when repetitions are insufficient.
- [ ] **Corroboration:** sufficient application + JVM + OS/container evidence to spot major confounders.
- [ ] **Storage:** manifest, raw data/histograms, required recordings/logs, and conclusions linked to the same run ID.
- [ ] **Boundaries:** baseline described as observed state under measured conditions; SLOs/thresholds kept as separate decisions.

**Conclusion:** A trustworthy baseline is **a reproducible set of results under explicitly recorded conditions**. In Java runtime diagnostics, you must simultaneously control workload, JVM state (warm-up/JIT/GC), OS/container resources, and metric collection. Only then do you have solid footing to state where a new measurement "differs from normal", by how much, and whether that difference warrants deep investigation.