# 17.10 Distinguishing Changes Caused by JIT or Load from Evidence of a Performance Bug

## Learning Objectives

When a Java application's CPU climbs or p95 latency degrades, three very different explanations exist:

1. **JIT, class loading, and warm-up:** the JVM is loading classes, gathering profiles, and compiling/optimizing methods; thus the same code under the same load can run faster or slower over time.
2. **Changed load or resources:** request count, concurrency, payloads, cache hits, CPU quota, queues, or dependency latency shifted; p95 can climb near saturation even with zero code changes.
3. **Evidence-backed performance bug (regression):** under comparable conditions for the same functionality, a change increases work or wait time, the result reproduces, and a mechanism explains the difference.

This lesson teaches how to **separate JVM and load signals from bug evidence**, rather than labeling something a "regression" from a single CPU graph. You will learn to formulate testable hypotheses, use JFR/JIT/class metrics, structure A/B experiments, read a runnable Java 17+ example, and write reports with calibrated confidence.

## 1. A Performance Difference Does Not Equal a Bug

**Latency** is wall-clock time from when a request begins until it returns a result. It can include **CPU computation**, **queue wait**, GC pauses, lock contention, sleep, I/O, network, database, and scheduling. **CPU time** measures actual CPU time spent running threads, excluding most waiting time.

```text
Request latency
  = queue wait + application service time + related wait times
Application service time
  = CPU work + GC/lock/I/O/dependency/scheduling delays (per measurement boundary)

High process CPU usage
  may come from more requests, costlier requests,
  JIT/GC/background work, or a busy-loop.
```

Do not infer:

- **CPU up → bug:** 600 RPS normally requires more total CPU than 300 RPS.
- **CPU low → app fast:** a system waiting on DB/locks can have low CPU yet very high p95.
- **p95 up → every method slowed down:** when queues grow, requests spend extra time waiting even if service code did not change.
- **Method X has 60% of CPU samples → X just got 60% slower:** sample share is a fraction of total samples in the window, not an absolute method latency.
- **Different speed after restart → must be a JIT bug:** JVM uptime, class initialization, caches, and compiler tiers are not yet equivalent.

### Minimum Set of Metrics to Read Together

| Aspect | Metrics | Purpose |
| --- | --- | --- |
| User | p50/p95/p99, errors/timeouts, SLO | Confirm symptom |
| Offered workload | arrival RPS, concurrency, request mix, payload size | Know whether load is truly the same |
| Served workload | completed RPS, queue depth, active workers, rejections | Know whether the system is serving or rejecting |
| CPU | process/thread CPU time, CPU%, CPU quota, cgroup throttling | Distinguish using CPU from waiting for CPU |
| JVM | uptime, class load/unload, JIT compilation, code cache, GC pauses | Recognize warm-up and JVM overhead |
| Non-CPU | lock waits, I/O, database/network, cache hits | Avoid wrongly blaming JIT |

Only when units, denominators, and measurement windows are known can two values be compared.

## 2. Hypothesis 1 — Warm-Up/JIT/Class Loading

HotSpot Java has an interpreter and JIT. **Tiered compilation** is usually enabled by default on Server VMs: the JVM initially runs code in less-optimized modes while collecting info on call sites, branches, and type profiles; C1/C2 or equivalent compilers progressively emit optimized machine code. In a Java 17+/21 app, a newly started process may go through:

1. **Class load/link/init:** framework startup, reflection, proxies, lambdas, serialization, and class loaders load classes.
2. **Profile collection:** hot paths run repeatedly; the JVM learns frequent types and branches.
3. **Compilation/inlining:** compilers generate optimized code; code cache and compiler threads consume resources.
4. **Steady state:** the same workload typically shows more stable throughput/latency after warm-up.
5. **Profile shift:** when the workload shape shifts, the JVM may **deoptimize** and recompile. Deoptimization is a normal adaptation mechanism, **not automatically a bug**.

### Common Signs

| Observation | JIT/Class-Loading Hypothesis | How to Verify |
| --- | --- | --- |
| p95 starts poor then drops at constant RPS | Warm-up and class loading | Plot latency vs. uptime alongside compilation/class loads |
| Short-term CPU on compiler threads | Many methods being compiled | JFR compilation events, compiler queue, compilation logs |
| Slow only on the first call to endpoint X | Lazy initialization/class load/cache miss | Correlate class loads, first-hit logs, cache warm-up |
| Shift in request mix causes brief slowdown | Type profiles/compiled code changing | JIT/compiler data and replaying the same workload |
| Code cache near limit | Compilation may be affected | `Compiler.codecache` and JVM logs |

**Important:** if a product has a cold-start SLO, warm-up causing excessive p95 **is still a performance problem to fix**. "Explained by JIT" does not mean "zero user impact"; it simply separates it from a steady-state business-code regression.

Not seeing compiler activity at one instant does not prove no compilation occurred earlier. Not seeing class load events in JFR is also insufficient to conclude no classes loaded: events may be disabled or the recording window may have missed the activity.

### Difference Between Class Loading and a Class Loader Leak

`totalLoadedClassCount` is **cumulative**, so it increases even when classes later unload. Currently loaded classes and unloaded classes must be read separately. Dynamic proxies/lambdas/plugin reloads can be normal, whereas if each reload retains old loaders and metaspace grows, that is a **retention** hypothesis requiring its own investigation. Even then, rising class counts do not by themselves prove a hot-path CPU regression.

## 3. Hypothesis 2 — Rising Load, CPU Saturation, and Queueing

Suppose an app handles 300 requests/s at 45% CPU, p95=70ms. At 650 requests/s, CPU nears quota and p95=280ms. These numbers are **purely illustrative**.

This can occur without any buggy commit:

- **Doing more work:** higher RPS raises total CPU time even if CPU per request stays identical.
- **Sharp queueing growth near saturation:** the system may process each request with the same CPU work, yet requests wait much longer as arrival rate approaches or exceeds service capacity.
- **Request mix shift:** a heavy endpoint takes a larger share, payloads grow, key cardinality rises, or cache misses increase.
- **Cgroup throttling:** the container receives a smaller CPU quota than before, delaying threads even when host CPU graphs look low.
- **Host contention:** another process uses CPU; the JVM faces resource contention.

### Why Can CPU% Mislead?

One Linux tool may show 100% when **one logical core** is fully busy; another dashboard normalizes against total cores or quota so 100% means full CPU budget usage. Always record the metric's **unit and denominator**, allowed vCPUs, and CPU throttling.

### Estimating CPU-Seconds/Request

In a relatively steady window:

```text
CPU-seconds per completed request
≈ Δ(process CPU time in seconds) / completed requests

Hypothetical example:
  120 CPU-seconds over 60 seconds,
  12,000 completed requests
  => ~0.010 CPU-second/request = 10ms CPU/request.
```

This is a **process-level average**, including JVM GC/JIT/background work, not the exact CPU time of a single request. Compare only when operation mix, error rate, retries, and background load match. If CPU/req stays nearly flat while total CPU rises with RPS, you cannot yet call it a CPU regression; if CPU/req rises while RPS stays flat, investigate execution/GC/JIT/dataset cost.

### Load-Curve Experiment

Do not compare A at 300 RPS solely against B at 650 RPS. Run both A and B at 300, 450, and 600 RPS with identical request mix, concurrency policy, payloads, and resource quotas. Plot completed throughput, errors, p95, CPU/req, and backlog. When one version saturates earlier **under identical conditions**, that is far stronger evidence of lost capacity.

## 4. Hypothesis 3 — When Do You Have Evidence of a Regression?

A conclusion that "B is slower than A because of a bug in code" must pass multiple levels:

| Level | Evidence | Valid Inference |
| --- | --- | --- |
| 1. Symptom | Dashboard shows p95 or CPU rising | Phenomenon exists to investigate |
| 2. Same conditions | Equivalent JDK, GC, quota, data, mix, RPS, and warm-up | Reduces confounding from load/JIT |
| 3. Reproducible | Multiple A/B runs, alternated order, steady windows, delta exceeds noise | Evidence of repeatable regression |
| 4. Mechanism | JFR/profiles and code analysis pinpoint new CPU work, allocation, wait, or algorithm | Causal hypothesis tied to a change |
| 5. Intervention | Reverting one change or fixing that exact path, re-measuring identically, restores performance | Stronger causal evidence |

**No single-number test proves every cause.** A/B and rollbacks must be repeated, accounting for cache variance, GC, runtime tiers, noisy neighbors, and business data.

Logic-regression example: at the same 400 RPS and data after warm-up, version B raises CPU/req from 8ms to 13ms and p95 from 88ms to 158ms; CPU profiling shows more work in `List.contains`; restoring an efficient lookup brings CPU/req and p95 back near baseline. This is a **reasoning pattern**, not real application measurements.

### Same p95 Yet Different CPU, or Vice Versa

- **High CPU, high p95:** may be extra CPU work, GC, JIT, a busy-loop, or saturation/queueing. Inspect threads/GC/profiles.
- **Low CPU, high p95:** suspect I/O, downstream services, locks, parks, or request queues. A CPU profiler sampling on-CPU threads will not reveal **off-CPU** waiting time.
- **High CPU, p95 still meets SLO:** may be legitimate workload; weigh efficiency/cost, though no product bug is proven yet.
- **Completed RPS drops, errors/rejections rise:** always compare **offered rate**; never read low completed requests as "light load."

## 5. Collecting JVM Evidence: JFR, jcmd, and Metrics

### 5.1. HotSpot Diagnostic Commands

`12345` is only an example PID: substitute the real Java PID, ensure proper attach permissions, and mind PID namespaces if running in a container.

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.flags
jcmd 12345 Compiler.queue
jcmd 12345 Compiler.codecache
jcmd 12345 VM.classloader_stats
```

- `VM.version`, `VM.flags` verify runtime/flags; do not compare two runs with different JDKs/GCs as if conditions were identical.
- `Compiler.queue` snapshots methods awaiting compilation **at call time**, not JIT history.
- `Compiler.codecache` gives code cache statistics; correlate with logs and timestamps when suspecting cache pressure.
- `VM.classloader_stats` gives class loader/class info; does not by itself prove a class loader leak or CPU bug.

You can enable compiler logging **in a dedicated diagnostic run**:

```bash
java -XX:+PrintCompilation -cp . CpuJitEvidenceDemo
java -Xlog:class+load=info -cp . CpuJitEvidenceDemo
```

These commands can print many lines differing across JDKs/runs; use only for observation, **never treat timings captured with verbose logging as a clean benchmark**. If testing `-Xint` or `-XX:-TieredCompilation` to explore mechanisms, remember they drastically change execution mode; do not conclude "there's a JIT bug in the code" merely because speed differs between that mode and production.

### 5.2. Capture JFR During Reproduction

```bash
jcmd 12345 JFR.start name=perf-check settings=profile duration=120s filename=perf-check.jfr
jcmd 12345 JFR.check name=perf-check verbose=true

# Once the JFR file completes:
jfr summary perf-check.jfr
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad perf-check.jfr
```

In this example, the recording spans 120 seconds; the workload must actually run within that window. `profile` can capture more events/samples than `default` at higher overhead; **not all events are guaranteed enabled**. To snapshot while the recording is still running:

```bash
jcmd 12345 JFR.dump name=perf-check filename=perf-check-now.jfr
```

`JFR.dump` does not stop the recording. Check timestamps, contents, and file paths; an old file with the same name is not proof a new dump succeeded.

Signals to cross-check:

| Event/Metric | Meaning | Limitations |
| --- | --- | --- |
| `jdk.CPULoad` | JVM and machine CPU over time | Does not say which method caused CPU |
| `jdk.ThreadCPULoad` | Which threads are consuming CPU | Differs from stack sampling; compare windows |
| `jdk.ExecutionSample` | Sampled stacks of executing threads | Sampling, not method invocation counts |
| `jdk.Compilation` | JIT compilation activity/duration | May not be enabled; event alone does not prove slowdown |
| `jdk.ClassLoad`/`jdk.ClassUnload` | Class activity over time | Frequency/enabled state depends on config |
| GC events/GC logs | Allocations/collections/pauses can stretch p95 | Must separate GC from application CPU |
| Monitor/park/file/socket events | Where threads wait | Thresholds may filter out short events |

JDK Mission Control helps inspect CPU, hot methods, call trees, class loads, GC, and compilations; select **matching time ranges and capture settings** for two recordings. Before saying "no compilations," run `jfr summary`, check `JFR.check verbose=true` while recording is active, and verify enabled flags, thresholds, sampling, and retention.

### 5.3. Do Not Equate Sample Percentage with Slowness

If method A goes from 30% of CPU samples before to 60% after, **that does not prove A uses twice the CPU time**: other methods may have become less active, total samples may differ, or input mix may have shifted. Self time and inclusive time differ; inspect call trees, per-request CPU, and actual work volume.

## 6. Java 17+ Lab: Same Output, Different Algorithmic Cost

The example below intentionally compares two lookup approaches on identical data:

- `ArrayList.contains` scans sequentially, costing O(N) worst-case per lookup; N queries can scale toward O(N²).
- `HashSet.contains` expects near-O(1) average per lookup with good hashes; N queries scale near O(N), **excluding set-construction cost**.

This is a **teaching experiment**, not a rigorous benchmark: the program warms up 6 rounds, measures 7 rounds, alternates order, computes the median, uses `volatile`, and verifies results to curb dead-code elimination. It still experiences noise from JIT, GC, and CPU frequency scaling, and does not use separate JVM forks. Use JMH for serious microbenchmarking.

### Complete Program

```java
// File: CpuJitEvidenceDemo.java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class CpuJitEvidenceDemo {
    private static volatile int observed;

    private static int countList(List<Integer> keys, int[] queries) {
        int matches = 0;
        for (int query : queries) {
            if (keys.contains(query)) {
                matches++;
            }
        }
        return matches;
    }

    private static int countSet(Set<Integer> keys, int[] queries) {
        int matches = 0;
        for (int query : queries) {
            if (keys.contains(query)) {
                matches++;
            }
        }
        return matches;
    }

    private static long timeList(List<Integer> keys, int[] queries, int expected) {
        long start = System.nanoTime();
        int result = countList(keys, queries);
        long elapsed = System.nanoTime() - start;
        observed = result;
        if (result != expected) {
            throw new AssertionError("list mismatch: " + result);
        }
        return elapsed;
    }

    private static long timeSet(Set<Integer> keys, int[] queries, int expected) {
        long start = System.nanoTime();
        int result = countSet(keys, queries);
        long elapsed = System.nanoTime() - start;
        observed = result;
        if (result != expected) {
            throw new AssertionError("set mismatch: " + result);
        }
        return elapsed;
    }

    private static long median(long[] samples) {
        long[] copy = samples.clone();
        Arrays.sort(copy);
        return copy[copy.length / 2];
    }

    public static void main(String[] args) {
        int count = 4_000;
        List<Integer> list = new ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            list.add(i);
        }
        Set<Integer> set = new HashSet<>(list);
        int[] queries = new int[count];
        for (int i = 0; i < count; i++) {
            queries[i] = i * 2;
        }

        int expected = count / 2;
        for (int i = 0; i < 6; i++) {
            timeList(list, queries, expected);
            timeSet(set, queries, expected);
        }

        int rounds = 7;
        long[] listTimes = new long[rounds];
        long[] setTimes = new long[rounds];
        for (int i = 0; i < rounds; i++) {
            if (i % 2 == 0) {
                listTimes[i] = timeList(list, queries, expected);
                setTimes[i] = timeSet(set, queries, expected);
            } else {
                setTimes[i] = timeSet(set, queries, expected);
                listTimes[i] = timeList(list, queries, expected);
            }
        }

        System.out.println("keys=" + count);
        System.out.println("queries=" + queries.length);
        System.out.println("expectedHits=" + expected);
        System.out.println("sameResult=" + (countList(list, queries) == countSet(set, queries)));
        System.out.println("measurementRounds=" + rounds);
        System.err.printf(Locale.ROOT, "listMedianMs=%.3f%n", median(listTimes) / 1_000_000.0);
        System.err.printf(Locale.ROOT, "setMedianMs=%.3f%n", median(setTimes) / 1_000_000.0);
    }
}
```

Compile and run with JDK 17+ (no external libraries):

```bash
javac CpuJitEvidenceDemo.java
java CpuJitEvidenceDemo
```

**Deterministic stdout**, verified on OpenJDK 24:

```text
keys=4000
queries=4000
expectedHits=2000
sameResult=true
measurementRounds=7
```

**Stderr varies across machines/runs.** One illustrative run produced:

```text
listMedianMs=4.629
setMedianMs=0.130
```

Do not treat those two stderr timings as speed guarantees. `sameResult=true` only shows the lookups return the same result on this input set, not that both structures are equivalent across all application properties.

### From Experiment to Regression Evidence

If a commit switches a lookup from `HashSet` to `ArrayList` and data grows, Big-O provides a **hypothesis** for increased CPU work. To confirm a production bug, keep input distribution, request volume, warm-up, and quota equal; measure CPU/request and latency across multiple runs; observe increased cost in the lookup path via JFR/profiles; fix/revert that exact change and repeat.

The cost of **building the `HashSet`**, memory footprint, and lifecycle must also be counted if the set is rebuilt per request. A faster lookup structure may yield no end-to-end gain when data is small or index creation dominates. Never treat Big-O or a single demo run as the final conclusion.

### Why Is JMH Needed?

Manual `System.nanoTime()` loops can be skewed by warm-up, JIT inlining/deoptimization, DCE/constant folding, GC, OS scheduling, and overly short intervals. **OpenJDK JMH** provides warm-up iterations, measurement iterations, forks, blackhole consumption, and statistical reporting. Use JMH for **hot-path microbenchmarks**; use **end-to-end load tests** to conclude throughput/p95 under concurrency, because JMH does not measure service queues, networks, DBs, or downstream paths.

## 7. Three Scenarios Explaining the Same Symptom

Numbers in the three tables below are **hypothetical illustrative data**, not a real system.

### A — Temporary Due to JIT/Class Initialization

| Since start, constant 400 RPS | CPU vs. Quota | p95 | Compilation/Class Load |
| --- | ---: | ---: | --- |
| 0–30 seconds | 78% | 240ms | High |
| 2–3 minutes | 53% | 112ms | Decreasing |
| 5–10 minutes | 50% | 105ms | Relatively steady |

Appropriate conclusion: **warm-up effect** present, no steady-state bug proven yet. However, if a cold-start SLO requires p95 under 150ms, the initial phase still needs a fix. Do not use steady state to dismiss the user's startup experience.

### B — Driven by Load and Queueing

| Offered RPS | CPU vs. Quota | Queue Depth | p95 |
| --- | ---: | ---: | ---: |
| 300 | 43% | 0–3 | 70ms |
| 450 | 65% | 4–10 | 85ms |
| 650 | 96% | 120+ | 280ms |

Preliminary conclusion: signs of capacity/queueing near saturation; **no commit regression proven yet**. Check completed RPS, CPU/req, resource quotas, errors, and request mix. If B is slower than A at the same 450 RPS, revisit the bug hypothesis.

### C — Bug with Controls and Intervention

| Shared conditions: 400 RPS, post-warm-up | A | B | B after fix |
| --- | ---: | ---: | ---: |
| p95 | 88ms | 158ms | 91ms |
| CPU/request | 8ms | 13ms | 8.2ms |
| Error rate | 0.1% | 0.1% | 0.1% |
| Profile | Few lookup CPU samples | Many samples in `List.contains` path | Returned near baseline |

If A/B repeats across multiple runs under identical conditions, B has higher CPU work/request, JFR supports the costlier lookup mechanism, and fixing that exact path restores metrics, that is **strong evidence** of a regression. You must still report variance, uncontrolled factors, and functional correctness after the fix.

## 8. Designing Reliable A/B Measurements

1. **Define the symptom:** endpoint/job, p50/p95/p99, throughput, errors, time, and SLO. "CPU went up" is a signal, not a complete diagnostic statement.
2. **Lock configuration:** app commit, JDK vendor/version, GC, JVM flags, CPU quota, memory, concurrency, feature flags, host, and dependencies. If testing a JDK upgrade, explicitly mark **runtime as the A/B variable**.
3. **Keep workload equivalent:** identical RPS/concurrency, data/cardinality, payload, request mix, warm/cold cache state, and error handling. Avoid Simpson's paradox when heavy-endpoint share shifts.
4. **Define warm-up:** wait for hot paths, class loads, JIT compilation, and caches to stabilize; measure startup separately if a cold-start SLO exists.
5. **Repeat runs / alternate order:** do not always run A before B. Run multiple trials and track medians, percentiles, and dispersion; avoid concluding from a 3% difference in 10% noise.
6. **Collect matching profiles:** JFR with identical settings and windows for CPU/GC/class/compilation. Watch overhead, sampling, thresholds, and missing data.
7. **Verify mechanism:** CPU/req, hot code paths, allocations/GC, locks/I/O/queues. Any "caused by JIT" claim must align with compilation/profile-change timestamps.
8. **Single-factor intervention:** revert/fix the suspect change, re-run an equivalent workload, and verify both correctness and performance.

### Test Matrix Template

| Field | A | B |
| --- | --- | --- |
| JDK/GC/flags | Record exact | Record exact |
| App commit/flags | Record ID | Record ID |
| CPU quota, memory, host | Record | Record |
| Warm-up and measurement duration | Record stability criteria | Same criteria |
| Offered/completed RPS, mix | Record | Same mix |
| Cache/key cardinality/data | Record | Equivalent |
| p50/p95/p99/errors | Measure | Measure |
| Process CPU time, CPU/req | Measure | Measure |
| GC/queue/throttling | Measure | Measure |
| JFR/compiled methods/class activity | Same settings | Same settings |
| Run count, variance | Record | Record |

## 9. Easily Confused Situations

**"JIT deoptimization = bug."** No. Deoptimization is HotSpot's adaptation mechanism when optimization assumptions break. You need abnormal repeated deopt/recompile and measurable impact under steady load before forming a performance-issue hypothesis.

**"Large code cache = RAM leak."** No. The code cache holds valid compiled code; investigate deeply only when pressure, compiler disabling, or related behavior degrades capacity. Check `Compiler.codecache` and runtime indicators.

**"Class count rose = CPU regression."** No. Legitimate class loading after warm-up or proxy creation also increases counts. Inspect class-loading duration, classloader lifetime, and actual CPU/latency impact.

**"GC pauses cause slowness so JIT is unrelated."** Not necessarily, though mechanisms must be separated. Collect GC logs, allocation rates, and JFR GC events before assigning blame. A request can stall on GC while application CPU is low.

**"Low CPU with high p95 → JIT optimizer slowed it down."** Insufficient. Check off-CPU waits: monitor/park, network, DB, thread scheduling, and queues. A CPU profiler only observes executing threads.

**"Method A profile went from 30% to 60% → A is twice as slow."** False. Sample share depends on denominators, sampling, and call paths. Prefer CPU work/request, thread CPU, and JFR call trees.

**"Disabling JIT with `-Xint` gives different results → JIT caused the bug."** Disabling JIT drastically changes execution mode and performance; that is an exploratory probe, not a production comparison baseline.

**"Running `System.nanoTime()` several times is enough."** Not necessarily. JMH helps prevent DCE/constant-folding and warm-up/fork/order traps; end-to-end load tests capture queues and downstream dependencies.

**"Once CPU drops, the job is done."** If p95 and completion/errors did not improve, you may have lowered resource cost without fixing the user-facing bottleneck. Set the right target.

## 10. Decision Checklist and Conclusion Template

Before calling a change a regression:

- [ ] Know the **real symptom**: p95, p99, throughput, errors/SLO, affected endpoints.
- [ ] Compare workload by **offered rate, completed rate, mix, data, and concurrency**, not total requests alone.
- [ ] Verify **CPU denominator/quota/throttling**, avoiding comparisons across mismatched CPU units.
- [ ] Separated **startup/warm-up** from steady state, or intentionally measured cold start against an SLO.
- [ ] Checked JIT compilation/class loading/code cache/GC in the same window; did not conclude from a single event.
- [ ] A/B ran on identical JDK/config/resources, identical load, and multiple trials; difference exceeds noise.
- [ ] Inspected CPU/request, queues, off-CPU waits, GC, and JFR call stacks.
- [ ] Formulated a hypothesis on method/algorithm/lock/allocation with an independent verification check.
- [ ] Single-factor fix/rollback restores metrics in repeated runs while preserving correctness.
- [ ] Clearly state **confirmed / suspected / insufficient evidence**, along with JFR and experimental limitations.

Conclusion template:

```text
Symptom: p95 /search rose from 90ms to 160ms.
Window: post-warm-up, 400 RPS, identical input mix, quota, JDK/GC.
Observation: CPU-seconds/request rose; errors, throughput, and queues verified.
JIT/class loading: activity does not explain sustained change
    in the measurement window (per collectable events/settings).
Profile: CPU rose in method X on call path Y.
Intervention: changed X or reverted commit Z, re-measured identically.
Conclusion: regression confirmed / still suspected / insufficient evidence.
Limitations: variance, filtered events, and uncontrolled conditions.
```

**Core takeaway:** JIT and class loading explain changes **across time and execution phases**; rising load explains changes **via offered work, saturation, and queueing**. A performance bug is established through **matched controls**, **reproducibility**, **a measurable mechanism**, and **confirming intervention**. Never treat a single CPU chart, one JFR hot method, or a brief benchmark as sole proof.

## References

- Oracle JDK 21 — Java HotSpot VM Performance Enhancements (tiered compilation, code cache): https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html
- Oracle JDK 21 — Diagnostic Tools, JFR, and `jcmd`: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21 — `jcmd` command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — JFR event settings: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle JDK 21 — `jfr` command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- OpenJDK JMH — Java Microbenchmark Harness: https://github.com/openjdk/jmh
