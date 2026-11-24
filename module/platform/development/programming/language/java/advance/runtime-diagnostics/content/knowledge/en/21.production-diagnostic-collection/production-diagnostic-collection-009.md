# 21.9. Verifying Recovery, Comparing Against Baseline, and Recording Evidence-Based Conclusions

## Lesson Objectives

After completing this lesson, you will be able to:

- Distinguish **mitigated**, **recovered**, **root cause fixed**, and **incident closed per process**.
- Establish an appropriate **baseline** to compare against the incident and post-action periods, avoiding confusing "alerts stopped firing" with "all functionality returned to normal."
- Inspect concurrently **user impact, error rate, p95/p99 latency, traffic/throughput, saturation, Java CPU/GC/heap/native memory, threads/I/O**, and dependency health.
- Use Java tools such as **JFR, JDK Mission Control (JMC), `jcmd`, and `jfr`**, combined with logs, traces, and metrics to add explanatory evidence.
- Build a **recovery gate** using multiple observation windows, comparable load conditions, and predefined thresholds.
- Record an evidence-based conclusion stating **timestamps, scope, actions taken, before/after metrics, supporting artifacts, confidence level, limitations, and follow-ups**—without turning hypotheses into proven facts.

**Context:** Java 17+ in application/JVM operations. Tool and command names may depend on JDK/OS; never run heavy diagnostic commands in production without evaluating impact. Thresholds in examples are **illustrative data**, not universal SLOs for every system.

## 1. What Does "Recovered" Actually Mean?

During an incident, changing a setting, rolling back, or restarting a JVM is merely an **action**. A "deployment succeeded" event is a deployment-system signal; it is **not** proof that customer errors have stopped.

| State | Accurate Phrasing | Minimum Required Evidence |
| --- | --- | --- |
| **Impacted** | Users or processing pipelines still experience errors, slowness, or wrong results | SLIs, per-request errors, functional test results, or user data checks |
| **Mitigated** | Temporary measures reduced or contained impact, though risk remains | Affected traffic path narrowed, error rate lowered, blast radius bounded |
| **Recovered** | Service meets defined operational criteria over a **sufficiently long observation window** under representative load | Error rate, latency, traffic, functionality, resource guardrails, and dependencies stable |
| **Root cause fixed** | Change eliminates the underlying failure mechanism and passes appropriate verification | Reproduction tests no longer fail, code/config correlation and verification evidence |
| **Incident closed** | Accountable owners agree response is complete, status is communicated, and follow-ups are tracked | Decision, timestamp, approver, evidence, and action items |

These states **do not always happen together**. For instance, a faulty rollout is rolled back to restore service while the code bug remains unfixed. You can report **"service recovered via rollback; root cause under investigation,"** never "bug fixed" just because users stopped hitting errors.

A JVM restart that drops CPU or heap used **does not prove a memory leak is gone**. Leaks require observing long enough or across enough workload cycles to verify whether post-warm-up slope returns to normal.

## 2. Establishing a Comparable Baseline

A **baseline** is a dataset representing a known **normal and representative** operating state, typically taken from a pre-incident window for the same service under comparable conditions. It is not a static constant across all circumstances.

### 2.1. Pick Anchors by Equivalence, Not Convenience

When choosing **before / during / after** windows, specify:

- Which **service, endpoint, operation, and tenant/region**; never let cluster-wide averages hide a failing user cohort.
- **Traffic volume** and workload shape: requests/second, concurrency, batch sizes, payload sizes, read/write mix, cache hit rates.
- **Time anchors** (UTC), window duration, day of week/seasonality, peak vs. off-peak hours, batch/scheduler schedules.
- **Application version, JDK, GC, flags, configuration, instance count, CPU/memory limits**, deployment region, and relevant dependencies.
- **Data quality**: sufficient sample counts, healthy exporters, no missed scrape intervals, metrics lag, counter resets, or altered dashboard queries.

For example, comparing p99 at **100 RPS** pre-incident against p99 at **10 RPS** after shedding 90% of traffic is comparing **non-equivalent conditions**. Such a "recovery" may simply reflect dropped load or rejected users. Check **served traffic, rejected traffic, and successful traffic** together—not just latency of served requests.

Not every baseline can be identical. If traffic shifts naturally, use **acceptable bands** or bucket by traffic level; explicitly note which variables differ and how far conclusions still hold. If no trustworthy baseline exists, record **"baseline unavailable"** and fall back to **SLO/SLI + historical ranges + functional checks**, stating limitations clearly.

### 2.2. Minimum Three Windows

An observation frame:

```text
UTC time ------------------------------------------------------------>
        A: BASELINE     B: INCIDENT     [change]    C: RECOVERY 1  D: RECOVERY 2
        known-good      impact          rollback    observe        observe
        metrics/JFR     metrics/JFR      action      without       recurrence?
                                                   major action
```

Windows must use **the same timezone, system scope, and metric definitions**. Choose window length based on detection time, traffic cadence, latency/GC cycles, data sync lag, and recurrence risk; never treat "2 green minutes" as a universal standard for every incident type.

Never alter, aggregate away, or delete raw data to "make the recovery curve look clean." Keep queries, timestamps, metric labels, and dashboard links reproducible.

## 3. Which Metrics Truly Confirm Recovery?

Organize checks into **user symptoms, system causes/guardrails, and evidence quality**.

| Check Group | Metrics / Questions | Recovery Criteria to Verify |
| --- | --- | --- |
| **Customer-facing errors** | Request error rate, timeouts, HTTP 5xx, failed payments, wrong data, retry exhaustion | Back to SLO/normal bounds for **the affected operations**; functional flow verified |
| **Latency** | p50, p95, **p99**, deadline misses, queue wait; properly scoped histograms | Meets SLO for the same endpoints/traffic mix; never rely on average latency alone |
| **Traffic and throughput** | Incoming QPS, accepted vs. served requests, successful ops/s, retry counts | Actual completed work returned to expected levels; not "green" because traffic stopped |
| **Capacity/saturation** | CPU per instance and per request, run queues, thread pools, queue depth, active connections | Saturation cleared, backlog draining steadily, expected headroom restored |
| **GC/heap** | GC pauses, collection frequency, allocation rate, post-GC old-gen, committed/used | No abnormal GC pressure, no dangerous upward slope after warm-up |
| **Native/container memory** | RSS, cgroup `memory.current`, `memory.events`, memory limits, OOM restarts | No climb toward limit or OOM events; never equate RSS with Java heap used |
| **Locks/threads/I/O** | Blocked/waiting threads, JVM thread pools, file/socket I/O latency | Lock contention / I/O bottlenecks back within acceptable levels |
| **Dependencies and correctness** | DB latency, connection pools, downstream errors, caches, consistency, data backlog | Errors not merely shifted downstream; post-incident data backlogs processed |
| **Observability** | Collector/scrape health, sample counts, query coverage, clock sync | Data fresh and broad enough to trust that green status is meaningful |

**Important:** No single "green indicator" automatically replaces the full set. Recovery criteria should be chosen upfront or agreed upon during the incident for **the specific customer impact**. For a data-corruption incident, HTTP 200 and fast latency still do **not** prove recovery if returned data is wrong.

### Three Layers of Evidence

1. **Primary/user-facing evidence:** SLIs/SLOs and user journeys — answers *are users still impacted?*
2. **Supporting/runtime evidence:** CPU, GC, memory, queues, JFR, threads/I/O — answers *has the JVM returned to healthy operation?*
3. **Change/causal evidence:** timeline, config/deploy diffs, repro tests, repro/rollback — answers *does the intervention plausibly explain the observed change?*

Prioritize layer 1 to declare the service recovered. Layer 2 rules out latent risks, and layer 3 supports root-cause conclusions. Whenever a layer is missing, state the gap explicitly.

## 4. Seven-Step Recovery Verification Workflow

### Step 1 — Lock Scope and Time Anchors

Record incident ID, coordinator/owner, environment, region, application/JDK version, deployment release, and **UTC start/detection/mitigation/end**. Separate **action time** (e.g., rollback at 10:42) from **SLI recovery time** (error rate normal from 10:47); the two need not coincide.

For rolling deployments, track traffic percentages on old vs. new builds; until rollout covers the fleet, **do not declare the entire system recovered**.

### Step 2 — Map Symptoms to Pass Criteria

Define pass thresholds upfront—for example, in a hypothetical service:

- Request error rate ≤ **0.1%** across agreed windows.
- p99 request latency ≤ **250 ms**, computed from the right endpoint histogram without mixing percentiles.
- Served traffic within **±10%** of a representative baseline (illustrative comparison condition, not a universal SLO).
- JVM CPU ≤ 75% measured consistently; container RSS within safe bounds.
- Domain-specific functional checks passing across **at least two consecutive windows**; duration depends on SLO, workload cycles, and on-call judgment.

Never quietly relax thresholds after viewing the numbers just to get a PASS. If criteria must change due to legitimate workload shifts, **record the decision, rationale, and approver**.

### Step 3 — Verify Impact Stopped on User Flows

Run controlled synthetic checks, inspect SLI dashboards, and confirm health of the exact endpoints/operations affected. For async systems, also check **backlogs, dead-letter queues, duplicate processing, and delayed jobs**; edge HTTP 200 responses do not mean recovery if background processing is still failing.

If the incident affected data, verify **integrity/consistency** and whether reconciliation/replay is needed; never call recovery solely because CPU dropped and error logs went quiet.

### Step 4 — Observe Stability Over Time

Wait at least long enough to cover failure cycles: GC cycles, cache reloads, cron jobs, queue drains, TTLs, connection rotation, or peak traffic. Declare "recovered" at the verified confidence level while keeping tighter monitoring for long-cycle recurrences.

**There is no universal duration.** If a memory leak surfaces only after 6 hours, two 10-minute windows cannot rule it out. For slow multi-day issues, establish post-incident monitoring with an assigned owner.

### Step 5 — Compare Baseline / Incident / Recovery Under Matched Conditions

Use tables with explicit units and intervals. When seeing "CPU drop from 95% to 40%," ask whether traffic dropped or instance count scaled out. If traffic doubled or instances scaled from 2 to 8 JVMs, per-instance CPU can drop even while total CPU cost per operation rises.

When traffic shifts, normalize metrics such as CPU-seconds per successful operation or **GC pause time per unit wall time** (properly defined), insofar as collectors and data support it. Never treat `CPU% / RPS` as an exact universal formula when CPU% spans differing core counts or container quotas.

### Step 6 — Check for Regressions and Safe Rollback Readiness

After a canary, rollback, or fix, verify:

- Normal requests, bad-input handling, timeouts, and retries.
- Cache hit/miss paths, batch jobs, or peak paths that originally triggered the incident.
- Affected regions, tenants, and endpoints—not just one easy synthetic health check.
- Databases, caches, queues, and downstream services.
- Data correctness/side effects, schema compatibility, and async behavior post-restart.

If any guardrail fails or a new regression appears, **do not close the incident prematurely**; execute contingency/rollback plans per authority and keep gathering evidence.

### Step 7 — Conclude With Explicit Bounds and Hand Off Follow-Ups

Write clearly: "From 11:10–11:30 UTC, two 10-minute windows met criteria ..., at 99–101 RPS vs. 100 RPS baseline. Service recovered in scope X. Root cause Y is not yet proven; continuing 24-hour watch to cover cycle Z."

This is an **illustrative phrasing template**—use it only when real data matches. Assign owners for root-cause investigation and follow-ups; update incident status per organizational workflow without auto-promoting "recovered" to "root cause fixed."

## 5. Measure and Compare Properly: Formulas, Units, Missing Data

### 5.1. Error Rate and Throughput

Within a defined window:

```text
Error rate (%) = 100 × failed requests / total eligible requests
Throughput      = successful operations / window seconds
Incoming RPS    = incoming requests / window seconds
```

**Denominators must match the SLI**: never divide failed background jobs by total HTTP health checks. If requests are dropped before reaching the app (ingress, LB, CDN), JVM-only metrics can **miss failed requests entirely**. Cross-check edge/LB, service, and dependency metrics.

For **cumulative counters**, take window start-to-end deltas, use proper `rate`/`increase` functions in your metrics backend, and handle **counter resets after JVM restarts**. Never subtract into negative numbers or add old and new incarnation counters as one continuous process. Check timestamps and sampling lag.

### 5.2. Percentile Latency: Never Average Two p99 Values

p95/p99 are **quantiles over a request distribution**. You cannot compute a 20-minute p99 by averaging the p99s of two 10-minute windows. You need raw histograms or distributions and proper aggregation.

Likewise, never average the p99 of a fast endpoint with a slow endpoint and call it system p99. When request mix shifts, aggregate p99 can look better even while a critical endpoint stays broken. Track **per endpoint/status/region** and prioritize SLIs reflecting user pain.

### 5.3. Resource Metrics Are Not Interchangeable

- **JVM heap used** measures occupied Java heap at measurement time, not RSS; committed heap differs from reserved/max.
- **RSS** is process-level physical resident memory, spanning much more than the Java heap.
- **Cgroup `memory.current`** is cgroup-level memory usage and can include page cache or other contributors not reflected directly in process RSS.
- **GC collection count/time** are counters that reset on JVM restart; `getCollectionTime()` is approximate, and some collectors return `-1`.
- User/system CPU, per-process percentages, and container CPU-quota percentages can use **different denominators**. Document exact definitions.

Never declare a "memory leak fixed" just because heap is low right after a restart; compare **post-GC old-gen / retained objects / slope** under matched workloads across a long enough lifecycle.

### 5.4. Insufficient Samples and Mismatched Conditions

Zero errors across **5 requests** is not equal to zero errors across **50,000 requests**. Ensure denominators are large enough for your threshold and desired confidence. Never cite `0` as proof of "no errors" when the metrics exporter disconnected or traffic stopped.

When a baseline is missing, metrics are absent, JFR lacks events, or dashboard queries miss scope, report **"insufficient evidence,"** note alternative sources, and state what is needed to complete verification. Never fill `0` in place of `NA`/missing.

## 6. Java Runtime Diagnostics in Verification

### 6.1. Using JFR in Its Proper Role

JFR supplies **configured runtime event data**, not a replacement for user-facing SLIs. If baseline and incident JFR files exist:

1. Verify both recordings cover the right JVM/app/version/period with comparable **event settings**, duration, and scope.
2. Inspect events such as `jdk.CPULoad`, `jdk.ThreadCPULoad`, `jdk.GarbageCollection`, allocations, monitors/locks, and file/socket I/O when present.
3. Use JMC to select **equivalent time ranges** or workload phases across CPU/method profiling, Memory/GC, Threads/Locks, and I/O.
4. Check event counts, thresholds, and sampling; absent events **do not prove** a phenomenon never occurred.
5. Correlate against application and OS/container dashboards. Shorter GC pauses alone do not guarantee checkouts succeed.

CLI example with **existing files**:

```bash
jfr summary before.jfr
jfr summary after.jfr

jfr print --events jdk.GarbageCollection before.jfr
jfr print --events jdk.GarbageCollection after.jfr
```

Two files are comparable only if they **cover meaningful workload phases** under sufficiently similar settings. `jfr summary` checks event types/counts and sizes; raw counts unnormalized by duration or traffic easily mislead. `jfr print` output can be huge, so use JMC or targeted filters instead of dumping everything into incident chat.

### 6.2. Capturing Post-Fix Recordings on a Running JVM

If no recording exists, use `jcmd` in an authorized environment:

```bash
jcmd -l
jcmd <PID> JFR.start name=RecoveryCheck settings=profile duration=60s filename=recovery.jfr
jcmd <PID> JFR.check
```

**Replace `<PID>` with the real PID** and confirm attach permissions. `jcmd` typically must run on the same host with matching user permissions. `settings=profile` adds overhead compared to `default`; choose intentionally rather than profiling every production JVM.

Once the timed recording finishes, verify `recovery.jfr` with `jfr summary` and open it in JMC. To snapshot a running recording, use `JFR.dump`; dumping **does not stop the recording**. Never claim a JFR baseline comparison **when no pre-incident file exists**; in that case, compare historical metrics/logs and clearly scope JFR as post-fix only.

### 6.3. Quick Supplemental JVM Checks

```bash
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> GC.heap_info
jcmd <PID> Thread.print -l
```

These commands are **diagnostic options**, not mandatory checks every time. `GC.heap_info` is only a snapshot; `Thread.print -l` scales in impact with thread count—never spam them in loops. Command names and impacts can vary across JDK implementations; check `jcmd <PID> help` when unsure.

Across JVM restarts or rollouts, record **PID, start time, build version, and flags** for both before and after. Same hostname does not mean same instance, and changing `-Xmx` or GC type alongside application code introduces a **confounder** when attributing causality.

## 7. Runnable Java 17+ Example: Recovery Gate With Load Check and Two Windows

This is an **offline practice exercise** (no production connections) using simulated data to demonstrate **not declaring recovery from a single green metric**. It evaluates four 600-second windows—baseline, incident, recovery-1, recovery-2—computing RPS, error rate, and guardrail checks.

**Illustrative criteria** (not a universal SLO):

- Each recovery window has at least 1,000 requests; RPS differs from baseline by at most 10%.
- Error rate ≤ 0.10%; p99 ≤ 250 ms.
- CPU measured under the **same convention** ≤ 75%.
- RSS ≤ 120% of baseline (merely a memory-growth guardrail; **does not prove absence of leaks**).
- **Both** recovery windows must pass.

### 7.1. Complete Code

Create **`RecoveryGateDemo.java`**:

```java
import java.util.Locale;

public class RecoveryGateDemo {
    record Window(String name, int seconds, long requests, long failures,
                  int p99Ms, int cpuPercent, int rssMiB) {
        double rps() { return requests / (double) seconds; }
        double errorPercent() { return failures * 100.0 / requests; }
    }

    static boolean healthy(Window w, Window baseline) {
        double loadDifference = Math.abs(w.rps() - baseline.rps())
                / baseline.rps();
        return w.requests >= 1000
                && loadDifference <= 0.10
                && w.errorPercent() <= 0.10
                && w.p99Ms() <= 250
                && w.cpuPercent() <= 75
                && w.rssMiB() <= baseline.rssMiB() * 1.20;
    }

    static void print(Window w) {
        System.out.printf(Locale.ROOT,
                "%s: rps=%.1f error=%.3f%% p99=%dms cpu=%d%% rss=%dMiB%n",
                w.name(), w.rps(), w.errorPercent(), w.p99Ms(),
                w.cpuPercent(), w.rssMiB());
    }

    public static void main(String[] args) {
        Window baseline = new Window("baseline", 600, 60000, 6, 140, 42, 512);
        Window incident = new Window("incident", 600, 54000, 2160, 1200, 95, 710);
        Window recovery1 = new Window("recovery-1", 600, 59400, 6, 155, 47, 535);
        Window recovery2 = new Window("recovery-2", 600, 60600, 3, 148, 45, 530);

        print(baseline);
        print(incident);
        print(recovery1);
        print(recovery2);
        System.out.println("Incident healthy: " + healthy(incident, baseline));
        System.out.println("Recovery window 1 healthy: " + healthy(recovery1, baseline));
        System.out.println("Recovery window 2 healthy: " + healthy(recovery2, baseline));
        System.out.println("Two-window recovery confirmed: "
                + (healthy(recovery1, baseline) && healthy(recovery2, baseline)));
    }
}
```

### 7.2. Compile and Run

```bash
javac --release 17 RecoveryGateDemo.java
java RecoveryGateDemo
```

**Exact stdout** when running the program with simulated data:

```text
baseline: rps=100.0 error=0.010% p99=140ms cpu=42% rss=512MiB
incident: rps=90.0 error=4.000% p99=1200ms cpu=95% rss=710MiB
recovery-1: rps=99.0 error=0.010% p99=155ms cpu=47% rss=535MiB
recovery-2: rps=101.0 error=0.005% p99=148ms cpu=45% rss=530MiB
Incident healthy: false
Recovery window 1 healthy: true
Recovery window 2 healthy: true
Two-window recovery confirmed: true
```

This example was **compiled with `javac --release 17` and executed**. Only simulated numbers produce this output; it connects to no live JVM, pulls no real metrics, and proves no real service recovered.

### 7.3. Interpreting Results Properly

- Baseline 60,000 requests / 600 s = **100 RPS**; incident 54,000 / 600 = **90 RPS**, while error rate jumped to **4%** and p99 hit **1,200 ms**.
- Recovery-1 has 99 RPS, 6 failures / 59,400 requests ≈ **0.010%**, p99 **155 ms**, CPU **47%**, and RSS **535 MiB**, passing the simulated guardrails.
- Recovery-2 has 101 RPS, 3 failures / 60,600 requests ≈ **0.005%**, p99 **148 ms**, CPU **45%**, and RSS **530 MiB**.
- Recovery-1 p99 (**155 ms**) remains roughly **10.7%** higher than baseline (**140 ms**); recovery does not require every metric to return **identically** to baseline if SLOs and safety margins are satisfied.
- Both simulated windows pass, so the program prints `true`; this **only evaluates the example predicate**—it does not verify traffic mix, user journeys, data correctness, dependencies, observability freshness, window contiguity, or leaks surfacing hours later.

**Technical limits of the example:** `Window` does not validate timestamps or verify windows are truly consecutive; payloads are hard-coded. In real systems, feed inputs from trustworthy metrics with time ranges, labels, units, and sample counts; check for non-overlapping, gap-free windows; and never average separate p99 values.

### 7.4. Exercises With the Program

1. Change `recovery2` to p99 **380 ms**. Recovery 2 and the two-window result must flip to `false`.
2. Change `recovery1` to `requests=600`. Even with a low error rate, the minimum request floor must block passing.
3. Change `recovery1` to 20 RPS (12,000 requests / 600s) with great latency: the **loadDifference** check must fail.
4. Remove the RSS condition and explain why the gate weakens for memory leaks; then describe adding **post-GC old-gen slope over a sufficient duration** rather than trusting one RSS snapshot.
5. Simulate the same total request rate while shifting most traffic to a cheaper endpoint: explain why an RPS-only gate is **insufficient**.

## 8. Good vs. Misleading Comparison Tables

### Good Table: Same Windows, Units, and Scope

| Metric (10 min, same API region) | Baseline | Incident | Recovery-1 | Recovery-2 | Example Criteria |
| --- | ---: | ---: | ---: | ---: | --- |
| Served RPS | 100 | 90 | 99 | 101 | Within ±10% of baseline |
| Error rate (%) | 0.010 | 4.000 | 0.010 | 0.005 | ≤0.10% |
| Request p99 (ms) | 140 | 1,200 | 155 | 148 | ≤250 ms |
| CPU (%) | 42 | 95 | 47 | 45 | ≤75% same convention |
| RSS (MiB) | 512 | 710 | 535 | 530 | Within guardrail, no sustained climb |

This table holds **simulated data** from the demo program, not a real incident report. Numbers are comparable in the exercise because we defined identical 10-minute windows and traffic class; with real data, attach queries proving equivalence.

### Misleading Summary: Green Indicators Only

```text
Alert: OK
Deployment: SUCCESS
CPU: 20%
=> Resolved
```

Insufficient: CPU can drop because **the service stopped receiving traffic**, the exporter died, JVMs restarted/got killed, traffic shifted to another region, or user impact is masked. Declaring recovery requires user-facing SLIs, load checks, coverage, functional checks, and observation time.

### Recommended Status Phrasing

Never write only "CPU dropped 50%." Write "Average JVM CPU dropped from X to Y at roughly matched instance count, traffic class, and RPS; simultaneously error rate and p99 met targets across two windows ..." If conditions do not match, state explicitly: "CPU dropped, yet traffic also dropped; insufficient basis to conclude performance is fixed."

## 9. Common False-Recovery Traps

### 9.1. Traffic Disappeared

Symptoms: RPS dropped from 100 to 5, CPU and latency look great. A load balancer may have pulled the instance or ingress may be blocked. Check **incoming/served/rejected**, routing, health checks, and end-to-end user flows—never inspect only instances still taking traffic.

### 9.2. Restarts Reset Metrics

A JVM restart resets **GC counters, heap used, and thread counts**; dashboards often show low CPU during early warm-up before peak. Check process start time, instance lifecycle, ramp-up, cache rehydration, JIT compilation, and post-warm-up memory slope; never compare cumulative metrics across restarts without handling resets.

### 9.3. One Region Green, Another Still Red

Aggregate dashboards can look healthy when most traffic sits in a healthy region. Evaluate affected regions, tenants, and endpoints against the same criteria. **Partial recovery** must be stated clearly, never masked behind global averages.

### 9.4. Error Rate Drops While Queue Backlog Remains

A job-ingestion endpoint returns 200 immediately, while downstream workers stay slow, dead-letter queues grow, and retry storms persist. Confirm **completed/successful work**, queue depth/slope, and data consistency—not just synchronous API latency.

### 9.5. Zero Errors Because Telemetry Stopped

A dashboard shows 0 errors when an exporter stopped or Prometheus returns "no data." Check **scrape freshness, missing time series, sample counts, collector health, clocks, and alert rule behavior**. Distinguish *zero observed errors* from *no observations*.

### 9.6. Symptom Patched, Root Cause Unfixed

Rollback restores service without a bug fix or regression test; raising heap delays OOM temporarily while the leak persists. State accurately **mitigation/recovery within verified scope** plus action items for root cause. Never write "permanent fix" for short-term relief.

### 9.7. Confusing Correlation With Causation

At the same time as a hotfix deploy, the DB self-recovered or traffic fell. SLIs improving after a change do not automatically prove the change caused recovery. Rely on timelines, diffs, repro tests, canary/control cohorts, and corroborating signals; until proven, write **"consistent with hypothesis..."** rather than **"proven caused by..."**

## 10. Recording Evidence-Based Incident Conclusions: Mandatory Fields

A strong recovery record or postmortem lets **someone absent during the incident** verify the numbers and understand the scope of conclusions. Avoid pasting raw screenshots lacking queries, timestamps, units, or owners.

### 10.1. Record Template

```text
Incident ID:
Service / environment / region / tenant:
Severity / user impact:
Owner / incident commander:
Timezone (UTC preferred):
Detected at:
Mitigation action and time:
Recovery observation window(s):
Baseline window(s) and reason comparable:
Criteria agreed (SLI/SLO + guardrails + data checks):
Evidence links (dashboards, log query, trace, JFR, deploy diff):
Metrics before / during / recovery (units, denominator, sample count):
Dependency and functional checks:
Remaining risks / unresolved questions:
Conclusion and confidence (recovered / mitigated / not yet verified):
Root cause status (confirmed / hypothesis / unknown):
Next action, owner, due date:
Approval / communication time:
```

This template is a structure **populated from real incidents**, containing no pre-filled claims. If a field lacks evidence, write **"no data / unverified"** rather than guessing exact numbers.

### 10.2. Example of a Well-Bounded Conclusion

```text
Scope: checkout API in region A (excludes batch workers).
Impact: 10:10–10:42 UTC, error rate elevated and p99 breached SLO.
Action: rolled back build B to build A at 10:42 UTC.
Evidence: dashboard X/query Y, trace Z, JFR sample W (sufficient scope).
Comparison: 10:50–11:10 UTC, two 10-minute windows showed
  error rate <=0.1%, p99 <=250ms, and RPS near baseline.
Checks: canary checkout OK, DB dependency healthy, backlog drained.
Conclusion: Checkout API region A recovered per agreed criteria.
Limits: Cannot yet rule out rare 6-hour cyclic failures; root cause
  of build B remains at hypothesis status.
Follow-up: owner O to verify root cause/test and monitor 24 hours.
```

This is a **hypothetical example**, not a real incident report. You can declare *recovered* within region A while **not declaring global service recovery** if other regions remain unverified.

### 10.3. Confidence Levels and Conclusion Categories

Distinguish clearly:

- **Observed:** "error rate in window X fell from A to B per query Q."
- **Correlated:** "The drop followed rollback, though traffic also changed concurrently."
- **Hypothesis:** "Possibly due to connection pool exhaustion."
- **Confirmed:** "Reproduced by a test on the old config, prevented by the fix, and consistent with operational telemetry."
- **Unknown/insufficient evidence:** "No pre-incident baseline or tracing; cause undetermined."

**You do not need absolute root-cause certainty to confirm user recovery**, yet you must explicitly state the boundary between the two. Incident closure can follow recovery once communication and handoffs are complete.

## 11. Case Studies: Different Recovery Patterns

### Case A — CPU/GC Spike After Rollout

After deploying a Java service, CPU jumps 30% → 95% and p99 spikes; rollback lowers CPU. Compare against a baseline matching **RPS, JVM count, JDK flags, GC type, and request mix**. Inspect **CPU samples, GC pauses, and allocation events** in JFR if available. If post-rollback error rate/p99 and capacity stay stable across enough peak cycles, state "service recovered after rollback"; **root cause of the new build remains unconfirmed** until a test and causal evidence exist.

### Case B — OOM Appears Gone After Restart

A JVM hits OOM; restarting drops RSS and heap used and clears alerts. This is **temporary relief**; if object or native allocations keep accumulating, OOM will return. Monitor **post-GC old-gen, RSS/cgroup `memory.current`, allocation rate, and OOM events** long enough under representative load. Document observation duration and which cycles remain uncovered before ruling out leaks.

### Case C — DB Recovers While Queues Remain Backlogged

DB latency returns to normal and HTTP ingress responds fast, yet 500,000 items sit in the backlog with high retries and stale user data. The frontend may be *partially recovered* while the async pipeline is not. Verify **drain rate, oldest-job age, successful processing, DLQs, and consistency** before declaring full recovery.

### Case D — Scale-Out Masks Higher Per-Request Cost

Adding 6 JVMs lowers per-instance CPU and improves p99, yet **CPU-seconds per successful request** may still be elevated due to costly new code. SLOs may be met **by adding capacity**, though documentation must clarify this is a cost-bearing mitigation, with algorithm/GC tuning and cost-per-request left as follow-ups.

### Case E — Canary Only Exercises Easy Traffic

A canary tests 1% traffic on a popular endpoint with zero errors, while the incident hit a rare operation for a specific tenant. Recovery criteria must include the **affected cohort**, never relying on overall canary error rates as a proxy for the whole service. Run targeted synthetic checks, traces, and feature-path checks for the impacted group and watch closely during broader rollout.

## 12. Protecting Evidence and Minimizing Collection Impact

- **Data protection:** JFR, logs, traces, heap dumps, and incident notes can contain usernames, endpoints, class/method names, tokens, request payloads, or PII. Store and share only in authorized places with explicit retention; avoid attaching heap dumps to public tickets.
- **Do not perturb production just to measure:** never enable all JFR events, capture heap dumps, or force Full GCs in production without weighing overhead. `GC.heap_dump` carries High impact; never run it as a routine health check.
- **Provenance and precision:** record query links with timestamps, scope, units, labels, and collector versions. Unannotated graph screenshots easily mislead.
- **Preserve history:** when capturing baseline/recovery files, keep originals with checksums/ownership where applicable; never edit evidence files to polish conclusions.
- **Clear authority:** whoever signs off recovery must hold operational accountability; root-cause follow-ups get their own owner when needed. Not everyone reading a green chart has authority to close an incident.

## 13. Recovery Verification Checklist

1. Confirm which **user journeys, cohorts, and regions** the incident hit—not just JVMs or hosts.
2. Select a **known-good baseline** with recorded timestamps, traffic, instance counts, versions, and queries.
3. Define SLIs/SLOs, resource guardrails, functional/data checks, and **adequate observation windows** before concluding.
4. Verify **traffic is still being served**, denominators are sizable, and dashboards have no data gaps.
5. Compare **baseline / incident / recovery** using matched units and scope; avoid misreading cumulative counters, averaged p99s, or post-restart resets.
6. Check JVM health: CPU/GC/heap/native memory, threads/locks/I/O, and JFR/JMC if recordings have adequate events.
7. Verify dependencies, backlogs, data consistency, and the specific failure paths that triggered the incident.
8. Save evidence links, UTC timestamps, deployment changes, verifier identity, and root-cause status.
9. Declare **recovered** strictly within verified scope; state uncertainties and limitations explicitly.
10. Assign recurrence monitoring, follow-up tests/fixes, owners, and due dates; close the incident per process after communication.

### Self-Check Questions

- Why are dropping CPU and p99 after rollback still insufficient to say the root cause is fixed?
- If error rate is 0% across only 8 requests while an exporter is dropping data, how confident can a recovery conclusion be?
- Can you average the p99 of two windows to obtain the 20-minute p99? Why or why not?
- When traffic drops sharply during an incident, which extra metrics must be checked before calling the service recovered?
- Why does low post-restart heap used not prove a memory leak disappeared?
- If one region is healthy while another still errors, how should the conclusion state scope?
- In `RecoveryGateDemo`, which check catches "metrics look good only because load dropped"? Which check flags high-RSS risk?
- For an evidence-based conclusion, what distinguishes "observed," "hypothesis," and "confirmed root cause"?

## References

- [Google SRE Workbook — Incident Response](https://sre.google/workbook/incident-response/): mitigating impact first, incident coordination, verifying recovery before standing down.
- [Google SRE Workbook — Monitoring](https://sre.google/workbook/monitoring/): tracking SLIs, logs/metrics, data freshness, deployment changes, and dependencies.
- [Google SRE Book — Example Postmortem](https://sre.google/sre-book/example-postmortem/): structuring impact, root causes/triggers, resolution, timeline, evidence, and action items.
- [Oracle Java SE 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): JFR start/check/dump and JVM diagnostic commands.
- [Oracle Java SE 21 — `jfr`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): summary, print, and filtering events from recording files.
- [Oracle JDK Mission Control 9 — Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html): analyzing Code, Memory, Threads/Locks, I/O, and timelines.
- [Oracle Java SE 21 — `MemoryUsage`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html): distinguishing used, committed, and max in the JVM.
- [Oracle Java SE 21 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): counters, collection time, and measurement limits.
