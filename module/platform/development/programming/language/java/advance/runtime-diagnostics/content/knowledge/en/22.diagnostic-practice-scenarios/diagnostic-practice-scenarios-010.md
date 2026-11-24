# 22.10 Writing a Report of Symptoms, Hypotheses, Evidence, Changes, and Validation Results

## Learning Objectives

A JVM investigation is operationally valuable only when someone else can read **what happened**, **why the team suspected a specific mechanism**, **which evidence supported or refuted it**, **what was changed**, and **how the outcome was validated**. A `jcmd` output, JFR chart, or heap dump file is not by itself a complete investigation report.

After this lesson, you will be able to:

1. Write a technical report following the chain **symptom → hypothesis → evidence → change → validation**, clearly separating observations from interpretations.
2. Quantify scope/impact using timestamps, request counts, error rates, throughput, p50/p95/p99 latency, and CPU/GC/heap, without misusing statistics or comparing mismatched load windows.
3. Build an **evidence index** with IDs, timestamps/timezones, sources, scopes, limitations, and secure storage locations so others can audit it.
4. State **falsifiable hypotheses** and proactively record contradicting results rather than cherry-picking snapshots that fit a preconceived conclusion.
5. Document changes specifically: version, scope, rationale, risks, rollback plan, and guardrails; never confuse "deployed" with "fixed".
6. Design a **properly controlled before/after validation** with explicit acceptance criteria, knowing when you can only conclude "partially improved" or "insufficient evidence".
7. Use a standalone Java 17+ program to practice reading a sample metrics table and writing a **simulated report** with consistent numbers.

> **Guiding principle:** A strong report is not the one with the most screenshots, but the one that lets readers **trace every conclusion back to exact evidence**, understand **uncertainty**, and see **the next verification step**. A wrong hypothesis that is cleanly falsified is still investigative progress.

## 1. Five Required Sections and Supporting Sections

Organize the report in the order a reader makes decisions, not the order you happened to open tools:

| Component | Question to Answer | Minimum Content | Common Mistake |
| --- | --- | --- | --- |
| **1. Symptom** | What abnormal behavior did users/systems observe? | Measured metrics, impact scope, start/end, baseline, workload, version. | "App is slow" with no time window or unit. |
| **2. Hypothesis** | Which mechanism *could* explain the symptom? | Testable predictions, suspect source, evidence that would falsify it. | Writing the cause as if already proven. |
| **3. Evidence** | Which real observations support/refute it? | ID, timestamp, tool, snapshot/event/metric, sampling/thresholds, limits. | Pasting screenshots without time axes, units, or sources. |
| **4. Change** | How was the system modified? | Code/config/runtime action, version, rollout, decision maker, rollback. | Writing only "optimized" or hiding concurrent changes. |
| **5. Validation** | Did the change improve things safely and reproducibly? | Matched measurement conditions, before/after, acceptance criteria, guardrails, remaining uncertainty. | Treating one p95 dip as root-cause confirmation. |

Those five sections usually benefit from **metadata**, **executive summary**, **timeline**, **risks/sensitive data**, **conclusion status**, and **action items**. Supporting sections help readers find evidence and act, without replacing the five core questions.

### Three-Level Skimmability

**Level 1 — 30 seconds:** What is the problem, who is affected, has impact been mitigated, what risks remain, and what is the current status?

**Level 2 — 5 minutes:** Symptom and comparison tables, primary hypotheses, counter-evidence, changes, validation results, and next decisions.

**Level 3 — audit/re-investigation:** Detailed timeline, environment identifiers, exact commands/settings, securely stored artifacts and raw data, analysis methodology, limitations, code/config diffs, and approval records.

One report serves all three levels without dumping thousands of raw log lines inline.

## 2. Before Writing: Defining the "Incident" and Scope Boundaries

**Scope** must be stated explicitly so readers do not extrapolate measurements from a single JVM to the entire fleet.

Simulated report example:

| Field | Value Filled in Example |
| --- | --- |
| Incident ID | `INC-DEMO-017` (illustrative ID only). |
| Service | `catalog-api` in a **simulated staging** environment. |
| JVM | Java 17, one application container process; does not assume all replicas behave identically. |
| Time window | 09:00–10:00 on 2026-10-29, timezone `UTC+07:00`. |
| Workload | A fixed set of **pre-built** 20 latency samples, not taken from production. |
| Versions | `build-A` (baseline), `build-B` (simulated incident), `build-C` (candidate). |
| Primary metrics | Request latency in milliseconds, error count/rate within the same sample set. |
| Intended audience | Developers, operators, and verification reviewers. |
| Status | **Training example, not a real investigated production incident.** |

In real environments, record **application, cluster/namespace, instance/pod, deployment region, JDK/GC, config version**, deploy timestamps, and approved metric sources. If a change rolled out to only 10% of replicas, never write as if the entire service ran that version.

### Timestamps: Recording So Logs, JFR, and Metrics Align

Always record timestamps with timezone/offset, for example:

```text
2026-10-29T09:15:00+07:00
```

When logs/JFR use `UTC`, convert to a single timezone before claiming two events coincided. Record **event time**, **collection time**, and **file creation time** separately when they differ. For example, a JFR file holds events from 09:15 while `JFR.dump` ran at 09:20; **09:20 is not when every event inside the file happened**.

If host/container clocks differ or have clock skew, document the offset and alignment method. Aligned timestamps show **correlation**; an exact timeline does not by itself prove causation.

## 3. Writing the "Symptom" Section with Verifiable Measurements

### 3.1. Separating Three Layers: User Report, System Observation, and Impact

1. **User report:** "Loading the search page sometimes spins or throws errors." That is an input signal, not a diagnosis.
2. **System observation:** "During 09:12–09:17, p95 latency rose from ~120 ms at baseline to 980 ms in the sample set; 4/20 requests failed." This is a measurement from the **simulated** example.
3. **Impact:** "Users face long waits/timeouts and reduced throughput." In production, cite actual affected users/requests; never extrapolate user counts from a 20-sample lab set.

Structure of a solid symptom statement:

> Within a **specific time window**, a **specific component and request group** exhibited **abnormal metrics** relative to a **matched baseline**, with a **measured impact scope**; this is the **symptom**, not yet a root-cause conclusion.

### 3.2. Choosing the Right Indicators

| Indicator | What It Answers Well | Required Conditions |
| --- | --- | --- |
| **Request count** | How many samples were actually measured? | Measurement unit, window, and data source. |
| **Error rate** | Fraction of failed requests in a defined set. | Specify failure type: HTTP 5xx, timeout, unhandled exception... |
| **p50** | Typical latency of the sample set. | Document calculation/histogram method if comparing systems. |
| **p95/p99** | Tail of latency distribution; surfaces slow request cohorts. | Sufficient sample size, matching request type, identical formula. |
| **Throughput** | Requests/s, jobs/s, bytes/s. | Never confuse incoming arrival rate with completed request rate. |
| **CPU** | Process/host/container CPU load. | Distinguish CPU quota/throttling, per-core %, and host CPU %. |
| **GC pause** | Duration/intensity of GC stops. | Based on GC logs/JFR with explicit coverage window. |
| **Heap/Metaspace** | Used/committed memory and trend over time. | Never confuse heap with native memory or claim a leak from one point. |
| **Thread/lock wait** | Waiting on monitors, parks, I/O, or queues. | Note thresholds and sampling; pair with call stacks/timelines. |

Performance incident reports must include **units**. "Latency 300" lacks `ms`; "CPU 2.0" lacks denominator; "heap 80%" lacks limit and memory region.

### 3.3. Small Formulas Frequently Misstated

With 4 errors in 20 requests:

\[
\text{Error rate}=\frac{4}{20}\times100\%=20\%.
\]

Dropping from 20% to 5% means:

- **Absolute drop:** 15 **percentage points**.
- **Relative drop:** `(20 - 5) / 20 = 75%`.

Never write "dropped 15%" when you mean **15 percentage points**. With 20 samples, rates are highly sensitive to single requests: **one error** shifts the rate by **5 percentage points**. Never use small sets to certify a long-term SLO.

If p95 latency drops from 980 ms to 195 ms in the sample dataset:

\[
\text{Relative drop}=\frac{980-195}{980}\times100\%\approx80.1\%.
\]

Yet **195 ms is still above the 120 ms baseline**, so "returned to normal" is not proven.

### 3.4. A Baseline Is Not a Free Pre-Existing Constant

Document where and under what conditions the baseline was measured: same endpoint, request size, client count, window duration, data version, traffic mix, warm-up, cache state, hardware/CPU quota, GC, and instrumentation level.

Comparisons break when:

- Baseline measured a warmed-up JVM while the incident measured cold start.
- Pre-fix ran 10 req/s while post-fix ran 1 req/s.
- Pre-fix computed p95 on successful requests while post-fix included **all requests**, including timeouts.
- One pod's p95 is compared against fleet p95, or against an average of per-pod p95s.
- Before/after sample sizes differ wildly without disclosure.
- JFR recording or profiler settings changed between the two windows.

When conditions are not equivalent, label it **"reference comparison only, insufficient for causal inference"** and plan a clean re-measurement.

## 4. Writing Testable and Falsifiable Hypotheses

A well-structured hypothesis:

```text
If [suspect mechanism] causes [symptom],
then during [matching window / workload / condition],
we predict we will observe [specific signal].
If that signal is absent or [contradicting data] is observed,
the hypothesis must be downgraded or rejected.
```

Examples:

| ID | Hypothesis | Testable Prediction | Falsifying Evidence |
| --- | --- | --- | --- |
| **H1** | A `synchronized` block holding a monitor long stalls workers, raising p95. | Multiple threads `BLOCKED` on the same monitor; JFR shows long `jdk.JavaMonitorEnter` durations; owner runs a long critical section. | No contention in the same window under sufficient settings; data shows latency lies elsewhere. |
| **H2** | GC pauses are the primary cause of latency spikes. | GC logs/JFR show pauses long enough and overlapping most slow requests; latency drops when GC behavior improves. | Slow requests do not overlap significant pauses, or pauses are far smaller than request delays. |
| **H3** | Slow backend/downstream responses. | Tracing and `jdk.SocketRead` or upstream logs show rising wait times on that downstream call. | Downstream latency stays flat under matching workload; slow requests do not hit that call. |
| **H4** | CPU throttling / compute saturation. | CPU utilization/quota throttling and stack samples align with the latency spike window. | CPU/quota look healthy while threads wait mainly on I/O/monitors; hypothesis weakens. |

**Distinguish "not observed" from "falsified":** Absence of `jdk.JavaMonitorEnter` in JFR does not rule out lock contention if the event was disabled, threshold was too high, or the recording missed the window. Falsification requires **measurement quality sufficient to detect the effect**.

### Ranking Hypotheses Without Inventing False Precision

Assign **high / medium / low / unassessed** along with conditions and evidence sources. Avoid pseudo-probabilities like "87.4% sure it is GC" without a calibrated quantitative model.

Short table:

| ID | Current Confidence | Rationale | Next Verification |
| --- | --- | --- | --- |
| H1 | Medium | Simulated thread dump shows waiters on a monitor; not yet proven owner held it due to the code change. | Compare JFR and critical section code before/after. |
| H2 | Low | GC pauses are not long enough in the same illustrative window. | Check exact GC logs aligned to slow requests. |
| H3 | Unassessed | Missing downstream logs/tracing. | Collect call durations keyed by request ID. |
| H4 | Unassessed | Missing CPU quota/throttle metrics. | Add CPU throttling metrics and JFR samples. |

As new evidence arrives, update confidence levels rather than rewriting history to fit the final conclusion.

## 5. Indexing Evidence Before Writing Conclusions

**Evidence** is more than a file link. It is a metadata record letting reviewers know **where from**, **when**, **what it can say**, and **what it cannot say**.

### 5.1. Structure of Each Evidence Entry

An entry can include:

- **Fixed ID:** `E01`, `E02`... used consistently throughout the report.
- **Source and metric name:** metric exporter, APM, request log, GC log, `jfr`, `jcmd`, heap dump, code diff, experiment.
- **Absolute time range:** timezone, capture window, JVM/instance, and clock sync status.
- **Collection method:** command, JDK/agent version, event settings, sampling/thresholds, scrape interval, filters, and any transformations.
- **Observation:** verified numbers/excerpts without extrapolating beyond the data.
- **Limitations:** snapshot vs. time series; possible dropped events; JFR sampling/thresholds; measured heap subset; representativeness.
- **Storage location/security label:** artifact ID in an access-controlled internal store; never embed raw heap dumps/secrets in widely shared reports.
- **Link to hypotheses:** supports, refutes, or inconclusive.

### 5.2. Common Java Evidence Types and Limitations

| Source | Strong When | Limitations to Record |
| --- | --- | --- |
| **Application logs / tracing** | Linking request IDs, endpoints, errors, callers, and downstreams over time. | Logs may drop or sample; clock skew; PII exposure. |
| **Metrics** | Multi-minute/multi-instance trends for request rate, error rate, p95, CPU, heap, GC. | Aggregation windows, scrape intervals, histogram buckets affect numbers. |
| **GC log** | Checking pause timestamps, GC types, pre/post heap, collection cycles. | Cannot link to specific requests without timeline alignment. |
| **JFR `.jfr`** | Timestamped CPU samples, GC, lock waits, allocation samples, I/O, threads. | Event settings/thresholds/sampling; `duration` is usually elapsed time, not automatically CPU time. |
| **Thread dump** | Thread stacks and states at one instant, plus lock owners/contenders if visible. | Point-in-time snapshot; does not prove how long a thread has already waited. |
| **`GC.class_histogram`** | Instance counts and total **shallow bytes** per class. | Does not show retained size/leak root cause; can trigger GC; not equal to RSS. |
| **Heap dump + MAT** | Inspecting object graphs, dominator trees, and paths to GC roots. | Heavy and sensitive; single snapshot, not multi-day trend. |
| **`VM.native_memory`** | NMT native memory categories with baseline/diff if enabled from startup. | Misses some native allocations; distinguish reserved vs. committed. |
| **Code/config diff** | Shows actual changes touching suspect mechanisms. | "Has a diff" does not prove the diff caused the issue. |
| **Validation experiment** | Observing effect and regressions against explicit criteria. | Confounders, noise; before/after without controls does not prove causality. |

### 5.3. Simulated Evidence Index Example

| ID | Window/Source | Recorded Observation | Limitations |
| --- | --- | --- | --- |
| **E01** | 09:00–09:05, baseline sample | 20 requests, p95 = 120 ms, errors 0/20. | Synthetic figures, tiny sample. |
| **E02** | 09:12–09:17, incident sample | 20 requests, p95 = 980 ms, errors 4/20. | Synthetic figures; lacks real traffic mix. |
| **E03** | 09:14, illustrative thread dump | Multiple workers `BLOCKED` on a monitor; one thread holds monitor. | Snapshot only; needs repeated samples/timeline for duration. |
| **E04** | 09:15–09:17, illustrative JFR | Several long `jdk.JavaMonitorEnter` events on that same code path. | Assumes event enabled and matching window; verify in real runs. |
| **E05** | 09:18, illustrative code review | An I/O call executes inside a `synchronized` region. | Suggests mechanism only; change impact needs validation. |
| **E06** | 09:30–09:35, after-change sample | 20 requests, p95 = 195 ms, errors 1/20. | Simulated candidate, not a production conclusion. |

**All of E01–E06 are simulated exercise data**, not real captured recordings or dumps. The program in section 10 produces E01, E02, and E06; E03–E05 are hypothetical scenarios for practicing multi-source evidence correlation.

### 5.4. Protecting and Sharing Evidence

HPROF files can contain tokens and user data; JFR can contain class/method names, threads, paths, endpoints, and even JVM arguments/properties depending on events. Command lines can expose secrets passed via `-D`. Therefore:

- Restrict who can collect/read artifacts via least privilege and approvals.
- Store raw files in stores/volumes with ACLs, encryption, auditing, and retention; cite **artifact IDs** and sanitized excerpts in reports.
- Never paste raw dumps, property lists, token-bearing URLs, or PII-containing stacks into public tickets/chats.
- State "HPROF archived in restricted investigation store" rather than publishing open download links.
- Verify checksums when required by process; never alter original files to make numbers look cleaner.
- Record who collected each artifact, when, with which tool, and ownership; ensure retention cleanup occurs per policy.

## 6. Collecting JVM Evidence Tailored to the Question, Not by Habit

The commands below are **illustrative guidance** for authorized JVM administration. PID `12345` is purely a placeholder; verify the real PID, attach permissions, namespace/container, and impact before running. Some commands carry medium/high impact or capture sensitive data.

### 6.1. Threads and Locks

```bash
jcmd -l
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l
```

`Thread.print -l` outputs thread stacks and `java.util.concurrent` lock details when available. In your report:

- Record the exact thread dump timestamp and how many threads share each pattern.
- Separate `BLOCKED` (waiting on intrinsic monitor) from `WAITING`/`TIMED_WAITING` (e.g., park/condition/sleep).
- Inspect lock owners, call sites, and a second snapshot if available to avoid single-snapshot bias.
- Never call a few `WAITING` threads a deadlock; idle executors wait normally.

### 6.2. Scoped JFR Capture

```bash
jcmd 12345 help JFR.start
jcmd 12345 JFR.start name=incident-investigation settings=profile
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=incident-investigation filename=/tmp/incident-investigation.jfr
jcmd 12345 JFR.stop name=incident-investigation
```

- `settings=profile` can consume more resources than `default`; bound duration/size and follow ops guidelines.
- `JFR.dump` writes inside the **target JVM's** filesystem and **does not stop the recording**.
- During analysis: run `jfr summary incident-investigation.jfr` to see which event types exist; run `jfr print --events jdk.JavaMonitorEnter ...` if that type is actually present.
- Events below threshold or disabled are absent; absence does not automatically refute a hypothesis.
- Align timezones/clocks with metrics and logs before joining timestamps.

### 6.3. GC and Memory

```bash
jcmd 12345 GC.heap_info
jcmd 12345 help GC.class_histogram
jcmd 12345 GC.class_histogram
jcmd 12345 VM.native_memory summary
```

**Do not run all of these blindly.** `GC.class_histogram` has high impact in some situations and can trigger a collection (depending on options); it reports shallow bytes per class, not leak root causes. `VM.native_memory summary` helps only when NMT was enabled at JVM startup; never read `"not enabled"` as `"0 bytes native memory"`. A heap dump (`GC.heap_dump`) carries even higher impact and sensitivity; collect it only when the question requires the object graph and approval is granted.

A strong report explains **why** a measurement was chosen, what was collected, and what was intentionally **skipped** due to cost or irrelevance.

### 6.4. Hypothesis-Driven Evidence Selection Table

| Question | Collect First | When to Collect Deeper Data |
| --- | --- | --- |
| Slow requests due to locks? | Thread dumps, JFR monitor/park events, request/queue metrics. | When needing owner/contender visibility across windows, inspect code and extra thread dumps. |
| Due to CPU/JIT? | Process/thread CPU metrics, JFR execution samples, and compilation events. | Approved deep profiler/async-profiler when samples are insufficient. |
| Due to GC? | GC logs, JFR GC pauses, heap usage, and allocation rate. | Heap dump when suspecting retained objects/leaks, not merely because GC ran slow. |
| Due to socket/file I/O? | Tracing, socket/file JFR events, downstream metrics. | Network/storage infrastructure if app-level evidence is inconclusive. |
| Due to memory/native? | Heap/Metaspace metrics, NMT (if enabled), RSS/container memory. | Controlled heap dump, MAT, or detailed NMT. |

## 7. Separating Evidence, Correlation, and Causation

These three statements **are not equivalent**:

1. **Observation:** "Within the same minute, p95 rose and `JavaMonitorEnter` recorded several high durations."
2. **Hypothesis:** "Lock contention may be contributing to the p95 increase."
3. **Causal conclusion:** "After controlling workload and modifying the critical section, lock waits dropped and latency improved reproducibly; multiple evidence sources agree and alternative hypotheses were evaluated."

Only the first statement is a direct observation from numbers. The second is an **interpretation to test**. The third demands **controlled validation**; when evidence is incomplete, state "strongly supported", "unproven", or "refuted within measurement scope".

### 7.1. Common Traps

- **Correlation ≠ causation:** two metrics rising together does not mean the first caused the second; a shared traffic spike could drive both.
- **Survivorship bias:** measuring only successful requests hides latency on timed-out requests.
- **Selection bias:** cherry-picking a few snapshots showing lock contention while ignoring thousands of clean ones.
- **Observer effect:** enabling heavy JFR events or debugger breakpoints perturbs the workload itself.
- **Regression to the mean:** symptoms may subside naturally after a spike without code changes; comparing closely around a spike invites false credit.
- **Confounding:** scaling out, cache warm-ups, network recovery, GC, or traffic shifts happening alongside a fix deploy.
- **Aggregate masking:** fleet p95 improves while one tenant/endpoint degrades; slice by meaningful dimensions.

### 7.2. Phrasing Confidence Precisely

Match wording strictly to evidence strength:

| Level | Phrasing |
| --- | --- |
| Observed | "E02 recorded p95 = 980 ms across 20 synthetic samples." |
| Supports hypothesis | "E03–E05 align with monitor contention, though controlled experiments are still needed." |
| Counter-evidence | "No matching-duration GC pauses appeared in the recorded window; primary GC hypothesis is deprioritized." |
| Change applied | "The candidate moved I/O out of the critical section on the evaluated code path." |
| Bounded result | "In synthetic samples, p95 dropped to 195 ms; still above the 120 ms baseline and not proven in production." |
| Unknown | "Insufficient throughput/CPU/traffic-mix data and repeated runs to conclude." |

Honest reporting about unknowns drives better operational decisions than declaring "root cause found" based on matching timestamps alone.

## 8. Documenting Changes So Others Can Reproduce and Roll Back

The **Change** section must describe **the exact intervention** and potential side effects.

Useful structure:

1. **Goal:** which hypothesis is addressed and which metric is expected to improve?
2. **Scope:** module/class/method/config, JVM/instance, version/build, and rollout percentage.
3. **Mechanism:** lock type changed, critical section narrowed, caching, deadline, or pool adjustment?
4. **Risks:** race conditions, update ordering, stale caches, memory pressure, throughput, timeouts.
5. **Pre-rollout testing:** relevant unit/integration/concurrency tests and pass/fail criteria.
6. **Observed impact:** deploy timestamp, dashboards/recordings used for comparison, guardrails.
7. **Rollback:** exact prior build/config, trigger conditions, and responsible owner per runbook.
8. **Concurrent changes:** pod scaling, traffic shifts, DB migrations, feature flags... if any, since they act as confounders.

### 8.1. Example Explaining Moving I/O Out of a Critical Section

Illustrative **before** snippet (not a full Java file):

```java
synchronized (cacheLock) {
    byte[] fresh = storage.readCurrent(); // Can block on I/O for a long time
    cache.put(key, fresh);
}
```

Illustrative **after** snippet showing a conditional approach:

```java
byte[] fresh = storage.readCurrent();     // Executed outside monitor
synchronized (cacheLock) {
    cache.put(key, fresh);
}
```

`cacheLock`, `storage`, `cache`, and `key` are assumed application components. This is purely an **illustrative snippet**, not a standalone compilable program.

**This transformation is not universally safe.** If multiple threads read/write concurrently, data structures and consistency rules may require version checks, compare-and-set, per-key locking, immutable snapshots, or another strategy. Moving I/O outside a lock **can introduce races/stale writes** unless invariants are proven. Before marking "fixed", run concurrency tests and verify business correctness.

### 8.2. "Change" Differs from "Successful Solution"

- "Deployed build C" is an **action**.
- "CPU dropped after deploy" is an **observation**.
- "Build C reduced CPU" is a **causal hypothesis**.
- "Verified the code change is the primary cause" can be written only when evidence and experimental design are strong enough.

Even when a rollback brings symptoms back and a redeploy improves them again, that is stronger evidence — yet still check cache warm-up, traffic shifts, and environmental variance.

## 9. Designing the "Validation" Section Before Applying Changes

Without defining **pass/fail criteria** upfront, investigators easily cherry-pick post-deploy metrics favoring the fix. Pre-commit criteria:

| Item | Example Criterion in Simulated Staging | Meaning |
| --- | --- | --- |
| **Primary metric** | p95 latency drops to **≤ 150 ms** under baseline-like workload. | Recovery goal for the exercise. |
| **Error rate** | No higher than baseline; investigate any errors. | Avoid "faster" achieved by dropping failed requests from samples. |
| **Throughput** | Does not fall below baseline at equal load. | A change can speed up successful requests while lowering throughput. |
| **CPU/GC** | No abnormal spike after the change. | Guardrail to catch hidden trade-offs. |
| **Concurrency correctness** | No races/stale writes/data corruption in targeted tests. | A broken lock fix can make the system fast and wrong. |
| **Observation duration** | Multiple comparable windows post-warm-up, including peak hours if relevant. | Catches delayed regressions; avoids one lucky sample. |
| **Rollback trigger** | Error spike or guardrail breach per approved policy. | Keeps decisions objective rather than emotional. |

Thresholds in this table are **hypothetical for the exercise**, not universal SLOs for every service.

### 9.1. At Minimum, Include a Before / Incident / After Table

| Metric | Baseline | Incident | After-change | Accurate Interpretation |
| --- | ---: | ---: | ---: | --- |
| Request count | 20 | 20 | 20 | Tiny sample; insufficient for production conclusions. |
| Error count | 0 | 4 | 1 | One error still occurred after the change. |
| Error rate | 0.0% | 20.0% | 5.0% | Dropped 15 percentage points from incident; not back to baseline. |
| p50 latency | 100 ms | 150 ms | 130 ms | Median improved yet remains above baseline. |
| p95 latency | 120 ms | 980 ms | 195 ms | Dropped ~80.1% from incident; **missed ≤150 ms target**. |
| p99 latency | 120 ms | 1250 ms | 220 ms | With n=20, nearest-rank p99 picks the maximum value. |
| Measurement conditions | Pre-built sample | Pre-built sample | Pre-built sample | No statistical inference about a real service. |

The values above are generated from the fixed dataset in the Java program in section 10. **They are not benchmark results or observations of a production JVM.**

### 9.2. Mandatory Questions When Comparing Before/After

1. Are time window, endpoint, request mix, data size, client count, CPU quota, and heap/GC/JDK identical?
2. Are request count, error count, timeouts, and sampling computed with **the same denominator**?
3. Do load generator, client, and server share the same instrumentation/clocks/config?
4. Did deploys, cache warm-ups, autoscaling, feature flags, or downstream behavior change mid-test?
5. Is the delta larger than normal noise? Are there repeated trials/controls for confidence?
6. Did secondary metrics (error rate, throughput, memory, CPU, correctness) regress?
7. Are both passed **and** failed criteria explicitly listed?
8. Is longer observation, rollback, or scope reduction needed before declaring resolved?

If conditions cannot match completely, document **limitations** and use stronger methods: traffic replay, cohort canaries, request-mix matching, true A/B tests, or approved rollback/redeploy checks. Never slap **"A/B test"** on two different-load time windows lacking proper grouping and controls.

## 10. Java 17+ Practice: Computing Percentiles on Simulated Data and Writing an Honest Conclusion

To practice presenting metrics cleanly, we construct **three fixed datasets**, without `Thread.sleep`, networking, or GC, because the goal here is **reporting and reasoning**, not JVM benchmarking.

The program uses **nearest-rank percentiles**: sort latencies ascending and pick element `ceil(p × n)` (1-indexed). Other percentile definitions exist; always state the formula when comparing against real metrics systems.

Create **`EvidenceMetricsDemo.java`**:

```java
import java.util.Arrays;

public final class EvidenceMetricsDemo {
    record Series(String name, int[] latencyMs, int errors) {}

    private static int nearestRank(int[] values, double quantile) {
        if (values.length == 0) {
            throw new IllegalArgumentException("Empty sample");
        }
        int[] sorted = Arrays.copyOf(values, values.length);
        Arrays.sort(sorted);
        int rank = (int) Math.ceil(quantile * sorted.length);
        return sorted[Math.max(1, rank) - 1];
    }

    private static void report(Series series) {
        int n = series.latencyMs().length;
        double errorRate = 100.0 * series.errors() / n;
        System.out.printf(
                "%s n=%d errors=%d errorRate=%.1f%% p50=%dms p95=%dms p99=%dms%n",
                series.name(), n, series.errors(), errorRate,
                nearestRank(series.latencyMs(), 0.50),
                nearestRank(series.latencyMs(), 0.95),
                nearestRank(series.latencyMs(), 0.99));
    }

    public static void main(String[] args) {
        report(new Series("baseline", new int[]{
                80,90,100,105,110,95,90,85,100,110,
                105,115,120,90,100,85,110,120,95,100
        }, 0));

        report(new Series("incident", new int[]{
                90,95,105,110,115,120,125,130,140,150,
                160,190,220,320,410,600,780,900,980,1250
        }, 4));

        report(new Series("after-change", new int[]{
                85,90,95,100,105,110,115,120,125,130,
                140,145,150,155,165,170,175,185,195,220
        }, 1));

        System.out.println("Synthetic illustration; not a benchmark.");
    }
}
```

Compile/run on JDK 17 or newer:

```bash
javac --release 17 EvidenceMetricsDemo.java
java EvidenceMetricsDemo
```

**Exact** program stdout (samples are fixed):

```text
baseline n=20 errors=0 errorRate=0.0% p50=100ms p95=120ms p99=120ms
incident n=20 errors=4 errorRate=20.0% p50=150ms p95=980ms p99=1250ms
after-change n=20 errors=1 errorRate=5.0% p50=130ms p95=195ms p99=220ms
Synthetic illustration; not a benchmark.
```

The code was compiled with `javac --release 17` and executed on a newer JDK; the stdout above was verified.

### 10.1. Moving from Data to Report Prose

**What you should write:**

> Across the simulated 20-sample datasets per stage, p95 rose from 120 to 980 ms; in the after-change set p95 was 195 ms, roughly an 80.1% drop from the incident yet still above baseline. Error rate dropped from 20% to 5% without returning to 0%. Results align with partial improvement in the exercise; **insufficient to prove the fix works in production**.

**What you should not write:**

> Build C completely fixed the latency bug, performance jumped 80%, and all users are back to normal.

The second statement is wrong because p95 is still 195 ms, 1/20 requests still failed, there is no throughput, user count, or real workload data, and a percentage **latency drop** does not automatically equal an identical percentage "performance gain".

### 10.2. Why Is `n=20` a Major Warning?

When `n = 20` with nearest-rank:

- p95 selects element `ceil(0.95 × 20) = 19` after sorting.
- p99 selects element `ceil(0.99 × 20) = 20`, i.e., **the maximum value**.
- Adding or removing one request swings percentiles dramatically.
- Each single error shifts the error rate by **5 percentage points**.
- The program contains no confidence intervals, traffic mix, controls, or repeated runs.

**Takeaway:** code computes consistently, yet **conclusion quality** depends on sampling design, representativeness, and independent evidence. A program producing neat numbers never replaces real validation.

## 11. Complete Filled Example Report: Simulated Staging Case

> **Note:** All actors, figures, timelines, snapshots, and changes in this section are **simulated for learning**, not describing a real system. Metrics E01/E02/E06 come from section 10's program; E03/E04/E05 are hypothetical evidence illustrating how to connect reasoning.

### Summary

**Incident ID:** `INC-DEMO-017`  
**Target:** `catalog-api`, simulated staging, Java 17  
**Window:** 09:00–09:40, 2026-10-29 (`UTC+07:00`)  
**Status:** Candidate improved metrics on sample data, **missed the p95 ≤150 ms criterion**, needs further validation.

**Impact observed in exercise:** in the 20-request dataset, p95 rose from 120 ms (baseline) to 980 ms (incident) and errors rose from 0/20 to 4/20. Do not infer production user counts because data is synthetic.

**Primary hypothesis:** contention on a monitor could be a major latency driver while an I/O call sits inside the critical section. Illustrative evidence E03–E05 fits this hypothesis, yet real JFR measurements and controlled load tests on the actual system are still needed.

**Illustrative change:** the candidate moved the I/O read outside the monitor on the evaluated branch, subject to data-consistency testing. No production deployment happens in this exercise.

**Sample results:** p95 dropped from 980 ms to 195 ms and error rate dropped from 20% to 5%, yet baseline was 120 ms and 0%. **Cannot close the incident as "fully recovered".**

### Symptoms and Timeline

| Time UTC+07 | Simulated Event/Action | Trace |
| --- | --- | --- |
| 09:00–09:05 | Ran baseline sample set `build-A`. | E01: p95=120 ms, 0/20 errors. |
| 09:12–09:17 | Detected p95 spike in sample set `build-B`. | E02: p95=980 ms, 4/20 errors. |
| 09:14 | Captured hypothetical thread dump in incident window. | E03: waiters blocked on monitor, one owner thread. |
| 09:15–09:17 | Inspected hypothetical JFR events in same window. | E04: wait events on the same call path. |
| 09:18 | Reviewed hypothetical critical-section code. | E05: I/O operation inside monitor. |
| 09:20 | Defined candidate and required tests. | Proposed change, not yet treated as a fix. |
| 09:25 | Ran correctness checks/risk assessment for candidate. | Real test results needed when executed for real. |
| 09:30–09:35 | Read after-change sample set `build-C`. | E06: p95=195 ms, 1/20 errors. |
| 09:40 | Wrote conclusion and follow-up validation plan. | Status: **insufficient improvement**. |

### Hypotheses

- **H1 — Monitor contention:** *illustrated* as consistent by E03/E04/E05. Controlled testing required to confirm causal role.
- **H2 — GC pauses:** insufficient simulated data to confirm or rule out. Requires GC logs/JFR in the same window for a real incident.
- **H3 — Slow downstream:** no downstream measurements collected yet. Plan to inspect tracing and socket events.
- **H4 — CPU saturation:** no CPU/quota metrics yet. Not yet ranked as a cause.

### Evidence

E01, E02, and E06 are samples and statistics computed by the Java program in section 10. E03, E04, and E05 are hypothetical scenarios with no real raw artifacts to download; hence this **is not a production sign-off record**.

Confidence in primary root cause: **unconfirmed**. Co-occurrence of monitor waits and latency (if observed in reality) only forms a grounded hypothesis without ruling out all other variables.

### Change and Risks

**Candidate:** move the I/O operation outside the critical section, keeping shared-state updates under the monitor.

**Risks:** stale data/races when two threads read and update concurrently; must prove invariants and check ordering and retry policies.

**Deployment:** simulation only; production rollout would require review, canary, and rollback.

**Rollback in real workflow:** revert to a verified build, triggered by error-rate/latency/correctness guardrails. Never assume rollback erases prior side effects.

### Validation

| Criterion | Simulated Target | After-change | Assessment |
| --- | --- | --- | --- |
| p95 latency | ≤150 ms | **195 ms** | **Not met**. |
| Error rate | No higher than 0% baseline | **5%** | **Not met**. |
| Throughput | No drop | Not measured | **Inconclusive**. |
| CPU/GC/memory | No regression | Not measured | **Inconclusive**. |
| Data consistency | No races/stale writes | Not tested live | **Inconclusive**. |
| Reproducibility | Multiple runs under equal load | One synthetic set only | **Insufficient**. |

**Decision:** Do not declare "incident resolved"; prioritize gathering sufficient samples, running concurrency tests, and validating under matched workload in staging. If real data shows regression, halt rollout per approved policy.

### Post-Report Action Plan

| Action | Purpose | Completion Criteria |
| --- | --- | --- |
| Add monitor wait and thread owner capture to the test window. | Test H1 directly. | JFR/thread dumps with timestamps, settings, call paths, and proper access storage. |
| Run stress/concurrency tests on candidate. | Catch stale writes and races from moving I/O out of the monitor. | Invariants and test assertions pass; not judged by latency alone. |
| Run matching traffic mix with enough samples across multiple cycles. | Reduce sampling noise and confounders. | Repeated before/after runs with disclosed sample sizes and p95 formula. |
| Measure CPU/GC/throughput/error rate. | Verify guardrails. | No regressions beyond approved thresholds. |
| Update conclusion and rollout/rollback decision. | Close the feedback loop. | Named approver, evidence, and clear next actions. |

This example report remains **useful** even with status "unconfirmed": readers see which measurements exist, which hypotheses remain untested, candidate risks, and criteria required before closing.

## 12. Phrasing That Makes Reports Credible

### 12.1. Avoid Claims Stronger Than the Evidence

| Avoid Writing | Write Instead |
| --- | --- |
| "JVM died because of GC." | "GC log recorded a 1.2 s pause coinciding with multiple request timeouts; correlate with request tracing to quantify contribution." |
| "Thread dump proves deadlock." | "One dump shows two threads waiting on locks. No cycle verified yet; need owner graph or deadlock detection." |
| "Memory leak because heap is high." | "Heap used climbed across multiple cycles without returning to baseline; inspect retained objects/GC roots after stabilization." |
| "Fixed because JFR shows no more slow events." | "No slow events appeared in the new recording; verify event enabled, threshold, and matching workload before comparing." |
| "p95 dropped 80%, performance rose 80%." | "Sample p95 latency dropped ~80.1%; cannot infer throughput, resource usage, or whole-service impact yet." |
| "Someone misconfigured it." | "A config change lacking guardrails/validation increased risk; strengthen automated checks and detection." |
| "Cannot reproduce, so no bug exists." | "Did not reproduce under current conditions; compare data, load, and environment against the incident window." |
| "Root cause 100% proven." | "Data and tests within measurement scope strongly support H1; limitations remain around duration/samples/conditions." |

### 12.2. Blameless Reporting

Describe **systems, decisions, data, missing controls, and recurrence prevention** rather than naming individuals to assign emotional blame. Postmortem culture improves operational mechanisms: guardrails, reviews, tests, monitoring, and deploy/rollback safety.

Distinguish:

- **Trigger:** e.g., a deployment that lengthened a critical section.
- **Technical mechanism:** multiple threads waiting on a monitor building queues and latency.
- **Contributing factors:** missing load tests on traffic mix, missing lock-wait alerts, or missed code-review checks.
- **Impact:** rising p95 and rising error/timeout rates.
- **Preventive actions:** shrink lock scope, test invariants, add alerts, canary rollouts, and rollback triggers.

You never need to conclude "one person was the root cause" to write a high-quality report.

## 13. Final Quality Check Before Sending

### 13.1. Data Check

- [ ] Start/end times, timezone, and environment/instance/JDK are specified.
- [ ] Symptoms state metrics, units, baseline, and impact scope.
- [ ] Metric names, denominators, window durations, and percentile methods are consistent.
- [ ] Counts/error rates/p95 in tables, charts, and prose **do not contradict each other**.
- [ ] Evidence index exists; every major claim links to verifiable ID(s).
- [ ] Distinguishes **snapshots**, thresholded/sampled events, aggregated metrics, and raw data.
- [ ] Does not equate a dump file's creation timestamp with event or request timestamps.
- [ ] No raw secrets/PII, raw heap dumps/JFRs, or credential-bearing command lines posted inline.

### 13.2. Reasoning Check

- [ ] Each hypothesis states expected signals and falsification criteria.
- [ ] Data **contradicting the main hypothesis** is also recorded.
- [ ] Correlation is not confused with causation, nor one trial with production proof.
- [ ] Technical changes state rationale, scope, version, risks, and rollback.
- [ ] Validation uses comparable load, sufficient windows/samples, and guardrail metrics.
- [ ] Each criterion clearly states **passed / failed / not measured**; never mark "PASS" for unmeasured checks.
- [ ] Current status and owner of the next decision are named.
- [ ] Report is blameless and contains concrete preventive action items.

### 13.3. Writing Check

- [ ] Opens with a readable summary, not thousands of log lines.
- [ ] Avoids undefined abbreviations; tables/charts include axes, time, and units.
- [ ] Clearly tags **real data**, **simulated data**, and **hypotheses**.
- [ ] Code snippets are labeled illustrative vs. runnable, with grounded stdout.
- [ ] Safe, permissioned paths/methods to access artifacts are noted without assuming public links.
- [ ] Clear enough for someone outside the investigation team to understand and challenge what still needs verification.

## 14. Practice Exercises

### Exercise 1: Fixing a Symptom Statement

Weak statement: "Server lagged, probably GC."

**Fix:** "During the 10-minute incident window, endpoint X's p95 latency rose from ~140 ms to 850 ms and error rate rose from 0.5% to 4.2% in matched-window metrics. GC is one hypothesis to check against timestamped GC logs/JFR." Numbers here are **hypothetical examples**, not real measurements.

### Exercise 2: Finding Weaknesses in Evidence

Data: one thread dump shows 12 `WAITING` threads.

**Question:** Can you conclude a deadlock?

**Answer:** No. Idle executor threads or threads waiting on `BlockingQueue.take()` also show `WAITING`. You need stacks, an owner/lock graph, repeated snapshots, and verification of whether work is progressing.

### Exercise 3: Evaluating Post-Fix Results

From section 10's code: p95 dropped from 980 to 195 ms, baseline is 120 ms, and criterion is 150 ms.

**Answer:** Improved **in the simulated dataset**, yet **missed** the recovery target. With only 20 samples per stage and no real system, this is not enough to prove a bug is fixed.

### Exercise 4: One Change and Two Diverging Metrics

p95 dropped, yet throughput halved, error rate climbed, or concurrency tests failed.

**Answer:** Do not declare "PASS" just because latency improved. Evaluate guardrails, prioritize correctness, and trigger rollback/adjustment per defined criteria.

### Exercise 5: Unverified Conclusion Statement

Statement: "After deploy, CPU is lower, so the new code solved the root cause."

**Answer:** Insufficient. Traffic could have dropped, autoscaling shifted load, caches warmed up, error counts changed, or CPU throttling occurred. Compare matched load, check profiling and secondary metrics, and run repeated or controlled tests.

## 15. Key Takeaways

- **Symptom:** describe what went wrong using contextualized metrics.
- **Hypothesis:** describe a plausible mechanism with tests and falsifiers.
- **Evidence:** record verifiable observations with IDs, timestamps, sources, and limits.
- **Change:** document exact intervention, rationale, risks, and rollback.
- **Validation:** compare before/after under fair conditions, with explicit pass/fail criteria and unmeasured gaps noted.
- **Strong conclusion:** never hide contradicting data, never conceal uncertainty, and never outrun your evidence.

A report can rightly conclude **"impact mitigated, root cause not yet confirmed"**. That is a valuable investigative outcome when backed by evidence, risks, an owner, and clear next actions.

## References

- [Oracle JDK 21 — `jcmd` and diagnostic commands](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.print`, `GC.heap_info`, `GC.class_histogram`, `JFR.start/dump/stop`, `VM.native_memory`.
- [Oracle JDK 21 — `jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `summary`, `metadata`, `print`, filtering JFR events.
- [Oracle Java 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): picking the right tool for CPU, threads, GC, memory, and runtime incidents.
- [Google SRE — Postmortem Culture: Learning from Failure](https://sre.google/resources/book-update/postmortem-culture/): learning from incidents, evidence, blamelessness, and systemic improvement.
- [Google SRE — Lessons Learned: Postmortem Culture](https://sre.google/sre-book/lessons-learned/): evaluating what happened, response effectiveness, and preventive actions.

