# 2.8 Verifying a Change Under Equivalent Load and Stating Conclusion Limits

## Learning Objectives

When fixing a query, changing GC configuration, expanding a connection pool, or optimizing a piece of Java code, the critical question is not just **"is the system faster after the change?"** but rather: **"Under equivalent load and comparable conditions, did this change improve the target symptom, did it introduce other regressions, and how far does the evidence justify concluding?"**

After this lesson, you will be able to:

- Build a **before (baseline/A)** and **after (candidate/B)** comparison for a specific change, with predefined measurement criteria, load conditions, and PASS/FAIL rules.
- Identify which factors must remain constant, which are allowed to differ, and how to detect differences that invalidate the comparison.
- Read **offered load**, **achieved arrived load**, **completed throughput**, **latency**, **errors**, and **resource costs** simultaneously when evaluating effectiveness.
- Verify **hypothesized mechanisms** with logs, metrics, traces, and JFR/GC/thread evidence when needed, rather than inferring causality from a single metric.
- Write a conclusion with clear scope, confidence level, limitations, and next recommendations; distinguish observed improvement from causal proof and production verification.

## 1. What Does "Under Equivalent Load" Mean?

**Change verification** compares system behavior across two states while trying to vary only the factor under test. In a Java application, that factor may be:

- Source code or algorithm: reducing allocations, fixing loops, removing redundant locks, changing a query.
- Runtime configuration: heap size, GC, thread pools, connection pools, retries, timeouts, caches.
- Dependent systems: database indexes, downstream APIs, connection behavior, or resource limits.
- Deployment topology: instance counts, CPU/memory limits, container images, or JDK versions.

**Equivalent load** is not merely two runs both showing "100 RPS" or "100 virtual users". You must verify whether *the work fed into the system* matches in characteristics and arrival schedule:

| Factor | What Must Be Matched or Explicitly Recorded |
| --- | --- |
| Send rate | Arrival rate over time, ramp-up, spikes, think time, open/closed workload |
| Concurrency level | In-flight requests, client workers, concurrency and queue limits |
| Operation mix | Endpoint/operation weights, read/write ratio, cache hit/miss branches |
| Inputs | Payload sizes, key distribution, record counts, seeds, initial dataset/snapshot |
| Timing | Warm-up, measurement duration, sampling timestamps, cold-start handling |
| System | Build, JDK, JVM flags, OS/container, CPU/memory, replica counts, topology |
| Dependencies | DB state, pools, caches, network, external services, rate limits |
| Measurement tools | Load generator version, latency measurement point, profiler/logging/sampling |
| Load outcome | **Offered**, **arrived**, and **completed** RPS; timeouts/errors, backlog |

A comparison is valid only when conditions **relevant to the hypothesis** are sufficiently equivalent, or when differences are documented and accounted for in interpretation. In real environments, all factors are rarely identical; what matters is knowing which differences can invalidate the conclusion.

**Note on "same environment":** if the change under test is increasing the CPU limit, heap size, or instance count, that factor *must* differ by design. In that case, hold the remaining factors constant and describe the comparison as **the effect of the resource change** plus its added cost. Never call this an "algorithmic improvement" without evidence about the algorithm.

## 2. Why One Before Measurement and One After Measurement Are Usually Not Enough

Suppose p95 latency drops from 400 ms to 290 ms after a code fix. The observed reduction is:

```text
reduction (%) = (before - after) / before × 100
              = (400 - 290) / 400 × 100 = 27.5%
```

**Observation:** p95 is 110 ms lower, or 27.5% below the prior mark, *in those two measurements*. You cannot yet attribute the full improvement to the fix because of other possibilities:

1. The after run accidentally received **lighter load**, despite identical generator configuration.
2. Caches, JIT, or connection pools were **warmer** from earlier runs.
3. The database responded faster at time B, or a resource-competing batch/cron job finished.
4. The after run dropped slow requests from the histogram because they **timed out**, making successful-response p95 look better.
5. Measurement tooling, instance count, CPU limits, or JVM flags differed.
6. The sample size was too small or p95 fluctuates strongly across runs even with zero code changes.

Therefore, "B was faster than A" is a **data description**. Claiming "change X made B faster" requires **controlled comparison design, repetitions, ruling out confounders, and mechanism evidence**.

In runtime verification, state three layers of conclusions clearly:

- **Observed:** how before/after metrics behaved, at what time and in what environment.
- **Evidence-supported:** comparable under load, repeatable, and accompanied by runtime signals consistent with the hypothesis.
- **Unconfirmed or conditional:** environment differences, untested workloads, sample error, or alternative explanations.

## 3. State Hypotheses and Criteria Upfront

Before testing a change, write a falsifiable hypothesis:

> "Under workload `checkout-open-100rps-v1`, optimizing query X will reduce `POST /checkout` p95 latency by at least 20%, with no error rate increase, achieved throughput meeting target, and median CPU rising no more than 8 percentage points. If latency drops yet timeouts increase or target load is not sustained, the change fails the acceptance gate."

The example above uses **illustrative** criteria, not universal default SLO thresholds.

A solid hypothesis specifies all five elements:

1. **Single change:** which commit/config/feature flag differs from baseline; if multiple changes must ship together, treat them as **one intervention bundle** and do not credit individual pieces separately.
2. **Expected mechanism:** why the change helps (fewer allocations, less lock wait, faster query execution, shorter GC pauses, etc.).
3. **Load and conditions:** operation mix, RPS/concurrency, cache/data state, instance count, JVM, measurement phase.
4. **Primary metric and guardrails:** p95/p99, errors, correctness, throughput, CPU, heap/GC, DB pressure, queues.
5. **Failure criteria:** if improvement is insufficient, regressions appear, comparability fails, or evidence is missing, the outcome is FAIL or INCONCLUSIVE.

Do not choose the primary metric or thresholds **after seeing the numbers**, as that biases toward picking whichever metric looks best to declare success. Base technical targets on SLOs, impactful latency bounds, or business needs; also define error margins and acceptable trade-offs.

### 3.1 Distinguish Goals from Guardrails

Suppose a fix lowers p95 by 25% yet increases CPU usage by 80%, triggers database timeouts, or returns incorrect results. Faster speed **does not** make the change acceptable.

| Category | Metrics | Question |
| --- | --- | --- |
| Primary goal | p95/p99 latency or business-valid throughput | Did the change solve the stated problem? |
| Correctness | Assertions, DB state, computed results, business errors | Did it corrupt data or behavior? |
| Reliability | 5xx, timeouts, retries, dropped requests, crashes | Did it trade speed for failures? |
| Load capacity | Offered/received/completed RPS, queues, in-flight | Did it actually process the same amount of work? |
| Cost | CPU, RSS/heap, GC pauses, I/O, DB connections | Did it shift the bottleneck or cost elsewhere? |
| Comparability | Workload mix, dataset, JDK, resource limits | Are before and after results fairly comparable? |

For a memory leak fix, the primary metric may be **the post-GC retained heap trend under equal workload over a long enough duration**; using p95 as the primary metric would miss the hypothesis. For a deadlock fix, the primary metric is **task completion and absence of lock-wait cycles** under the trigger conditions. Never apply one fixed performance scorecard to every type of incident.

## 4. Designing a Controlled A/B Experiment

### 4.1 Freeze the Experiment Profile (Run Manifest)

Create an immutable description before running:

```yaml
experiment_id: checkout-query-v2
hypothesis: "query optimization reduces p95 without error regression"
version_A: "image-digest-A"
version_B: "image-digest-B"
jdk: "17 (record actual vendor and patch version)"
jvm_flags: "record exact startup flags"
environment: "staging-cluster-profile-1"
instance_count: 3
cpu_memory_limits: "record exact requested/limit values"
workload_id: "checkout-open-100rps-mix-v1"
model: "open (scheduled arrivals)"
offered_rate: "100 req/s"
operation_mix: "70% read, 30% checkout"
dataset_snapshot: "synthetic-dataset-v7"
warmup: "3 min"
measurement_window: "10 min"
repetitions_per_variant: 3
metric_source: "client metrics + server metrics + traces"
primary_metric: "client-side p95 end-to-end latency"
guardrails: "errors, achieved throughput, CPU, correctness"
stop_condition: "abort on agreed resource/error/safety threshold"
```

This is an **illustrative template**, not a required config file for the JDK or any benchmark tool. A string like `"17"` does not replace recording the actual vendor and patch version. A thorough verification suite also records load generator commands, sampling, dataset/seed, UTC timestamps, profiler versions, cache state, and links to each run's artifacts.

For tests involving JIT, class loading, GC, or caches, specify whether **warm-up sits outside the measurement window** and whether runs reset the JVM/cache. If the bug occurs only on cold start or after prolonged accumulation, **do not** discard the failing phase merely to make numbers look prettier.

### 4.2 Choose an Appropriate Comparison Layout

**Sequential A then B in the same environment:** easy to run and needs fewer resources, yet vulnerable to time-dependent drift (caches, network, batch jobs, background load). Running all A trials then all B trials lets time act as a confounder.

**Interleaved A–B–A–B or B–A–B–A** when conditions can be reset: helps spot drift over time. Reinitialize datasets/caches strictly so state from one run does not bleed into the next; if reset is impossible, document the limitation.

**Parallel groups:** cuts time-of-day variance, yet you must verify parity of nodes, network, data, and load routing. If A and B share a saturated DB, they can **interfere with each other**, so parallel execution is not automatically a clean control.

**Production canary / A-B:** reflects real traffic best, yet both groups must receive comparable traffic splits with guardrails and rollback ready. Differences in tenants, request types, host placement, caches, or dependency versions can skew results. Never run user-impacting experiments just for benchmark numbers without proper operational controls.

No single run order is "standard" for all cases. Choose the layout based on resetability, time sensitivity, data state, and operational risk, and record why you chose it.

### 4.3 Repeat Runs and Track Variance

One A run and one B run give only two points. Run **multiple independent trials** under equivalent conditions, keeping per-run data instead of only an average. Three runs is an easy teaching example, **not a statistical sample-size standard**.

For skewed metrics like p99 latency, sample count, duration, and sample independence matter greatly. Requests within the same run are often correlated via GC, bursts, dependencies, or queues; do not treat individual requests as independent trials to fabricate false statistical confidence.

Record every run (`A1/A2/A3`, `B1/B2/B3`), both successes and failures. You can use the median across runs to describe typical **run-level p95**; state clearly that this is **the median of per-run p95s**, not the pooled p95 of all requests combined. Computing a pooled percentile requires raw distributions/observations or compatible histograms and a valid merge method; **never average per-run p95/p99 values and call it total p95/p99**.

## 5. Verify Actual Load Before Looking at Result Charts

A fix is only "faster under equivalent load" when the workload **executed as designed** on both versions.

### 5.1 Offered Load, Achieved Load, Completed Load

- **Offered load:** schedule and rate the generator *intended* to send, e.g., 100 new requests per second.
- **Sent/received:** requests actually emitted and reaching the system; watch load generator, proxy, and connection errors.
- **Completed throughput:** requests finished per second, clearly separating successes and failures.
- **In-flight/queue/backlog:** work currently active or queued at measurement time; if rising continuously, the system is not in steady state.

Example:

| Metric | Before A | After B |
| --- | ---: | ---: |
| Offered RPS | 100 | 100 |
| Received RPS | 99 | 98 |
| Completed RPS | 98 | 97 |
| p95 latency | 400 ms | 290 ms |
| Timeout rate | 0.3% | 0.3% |

Numbers are **illustrative only**. If both received/completed close to target load with no unbounded backlog growth and equivalent request mix/data, the comparison stands on solid ground.

Conversely, if B processed only 55 RPS because the generator stalled or clients stopped sending when the server slowed down, B's p95 cannot be called an improvement "at the same 100 RPS" merely because both were configured for 100 RPS.

### 5.2 Open Workload vs. Closed Workload

**Open model:** requests arrive on a fixed-rate schedule largely independent of prior completion times. Well-suited for modeling external traffic; verify schedule accuracy and queue growth when the server slows down.

**Closed model:** a fixed count of concurrent clients/tasks; each client typically waits for a response before sending the next (optionally after think time). When the system slows down, total throughput can drop. Equal virtual-user counts do not guarantee equal RPS.

**Coordinated omission:** when a system stalls, closed-loop tools or generators that throttle themselves can omit requests that should have arrived during the stall, making latency histograms underestimate real-traffic experience. Understand the load model and how the tool accounts for delayed/dropped requests before interpreting p95/p99.

In both models, count errors and timeouts completely. A histogram containing only successful responses can show lower p99 as timeouts climb; that is not success.

### 5.3 Same Load Does Not Mean Other Metrics Must Stay Identical

If the change itself lowers CPU or GC work, CPU/GC **are expected to change** and are part of the measured outcome. What must stay equivalent are inputs/controls such as CPU limits, offered load, datasets, and JVM settings outside the intervention. For capacity tests seeking **maximum sustainable throughput**, ramp offered load identically for A and B to compare capacity curves rather than checking just one RPS point.

## 6. Interpret Results with Acceptance Thresholds and Side Effects

A verification gate template, applicable only when workload and conditions are comparable:

```text
Precondition:
- A and B share the same workload plan/dataset/build-context except change X;
- load generator is not bottlenecked; received/completed reach allowed target;
- warm-up and measurement windows are equivalent; no unbounded backlog growth.

Primary:
- median of per-run p95 decreases by at least 20%
  (also report absolute improvement in ms).

Guardrails:
- error/timeout rate does not rise above predefined threshold;
- correctness assertions PASS;
- achieved throughput meets target;
- CPU, heap/GC, DB wait, and queues stay within budget;
- no new failures on other workloads within test scope.

Outcome:
PASS if all predefined conditions pass.
FAIL if intervention falls short or introduces a regression.
INCONCLUSIVE if workload/conditions/observations are not comparable.
```

Never alter PASS criteria mid-experiment just because B looks good on one metric. If trading higher CPU for lower latency is intentional, document resource cost and acceptable limits upfront.

**Numbers to report together:**

- Before/after values and **absolute delta**, e.g., reduced by 110 ms.
- **Relative delta** vs. baseline, e.g., reduced by 27.5%.
- Per-run distribution or range, run count, and observed request count.
- Errors/timeouts, achieved throughput, resources, and queue state.
- Metric definitions: client vs. server latency, per-run vs. pooled percentiles, and how failed requests are handled.

A 10 ms difference can be huge for a 20 ms endpoint yet negligible for a multi-minute batch job. "Statistically significant" (when properly estimated) and "worth deploying" are different questions; SLOs, correctness, cost, and business impact decide practical value.

## 7. Java 17+ Example: Checking Pre-Recorded Before/After Results

The example below uses **hypothetical records** of three A runs and three B runs. The program does not generate load, measure JFR/GC, or pretend to run a real benchmark. Its goal is illustrating how to **verify load metadata before comparing**, compute gains on run-level p95, and apply guardrails on existing data. In real work, this data must come from load generators, metrics systems, and runtime evidence.

Create `ChangeVerificationDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.ToIntFunction;

public class ChangeVerificationDemo {
    record Plan(String workloadId, String datasetId,
                int targetRps, int durationSeconds, String jdk) { }

    // errorBp: 1 basis point = 0.01 percentage point;
    // 30 means 0.30% error rate.
    record Trial(String variant, Plan plan, int achievedRps,
                 int p95Ms, int errorBp, int cpuPct) { }

    static int median(List<Trial> runs, ToIntFunction<Trial> metric) {
        if (runs.isEmpty() || runs.size() % 2 == 0) {
            throw new IllegalArgumentException("use an odd run count");
        }
        int[] values = runs.stream()
                .mapToInt(metric)
                .sorted()
                .toArray();
        return values[values.length / 2];
    }

    static void validate(List<Trial> before, List<Trial> after) {
        if (before.size() != 3 || after.size() != 3) {
            throw new IllegalArgumentException("expected three runs each");
        }
        Plan expected = before.get(0).plan();
        List<Trial> all = new ArrayList<>(before);
        all.addAll(after);

        for (Trial run : all) {
            boolean samePlan = run.plan().equals(expected);
            boolean meetsLoad = run.achievedRps() * 100
                    >= expected.targetRps() * 95;
            if (!samePlan || !meetsLoad) {
                throw new IllegalArgumentException("not comparable");
            }
        }
    }

    public static void main(String[] args) {
        Plan plan = new Plan("checkout-open-100rps-mix-v1",
                "synthetic-dataset-v7", 100, 600, "17");

        List<Trial> a = List.of(
                new Trial("A", plan, 99, 390, 30, 56),
                new Trial("A", plan, 98, 400, 20, 57),
                new Trial("A", plan, 99, 420, 40, 58));

        List<Trial> b = List.of(
                new Trial("B", plan, 98, 280, 20, 61),
                new Trial("B", plan, 99, 290, 30, 62),
                new Trial("B", plan, 98, 300, 30, 63));

        validate(a, b);
        System.out.println("metadata=matched; achieved>=95 RPS");

        int p95a = median(a, Trial::p95Ms);
        int p95b = median(b, Trial::p95Ms);
        int errA = median(a, Trial::errorBp);
        int errB = median(b, Trial::errorBp);
        int cpuA = median(a, Trial::cpuPct);
        int cpuB = median(b, Trial::cpuPct);

        double reduction = 100.0 * (p95a - p95b) / p95a;
        System.out.printf(Locale.ROOT,
                "p95 median: %d -> %d ms (reduction=%.1f%%)%n",
                p95a, p95b, reduction);
        System.out.printf(Locale.ROOT,
                "error median: %.2f%% -> %.2f%%%n",
                errA / 100.0, errB / 100.0);
        System.out.printf(Locale.ROOT,
                "cpu median: %d%% -> %d%%%n", cpuA, cpuB);

        boolean pass = reduction >= 20.0
                && errB <= errA
                && cpuB <= cpuA + 8;
        System.out.println("gate=" + (pass ? "PASS" : "FAIL"));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac ChangeVerificationDemo.java
java ChangeVerificationDemo
```

Exact stdout:

```text
metadata=matched; achieved>=95 RPS
p95 median: 400 -> 290 ms (reduction=27.5%)
error median: 0.30% -> 0.30%
cpu median: 57% -> 62%
gate=PASS
```

**Calculation explanation:**

- A has three per-run p95s: 390, 400, 420 ms; median = 400 ms.
- B has three per-run p95s: 280, 290, 300 ms; median = 290 ms.
- Reduction = `(400 - 290) / 400 × 100 = 27.5%`.
- Error median: 30 basis points = 0.30% in both A and B.
- CPU median rises from 57% to 62%, i.e., **5 percentage points**, within the illustrative budget of at most 8 percentage points.
- Every run records the same `Plan` and `achievedRps >= 95`, so the example's **metadata validation** passes; the predefined rules yield PASS.

**Example limitations:** `Plan.equals(...)` only checks *matching declared metadata*. It does not prove requests actually arrived on the same schedule, used the same query plan, caches, driver/JVM patch versions, or an unbottlenecked load generator; those require checking real artifacts. `achievedRps >= 95` is a simple check and does **not** verify queues, arrival schedule drift, or correctness. Median of three per-run p95s is not the pooled p95 across all requests. A small fabricated dataset **does not** prove the change is causal, nor does it provide confidence intervals.

If substituting new measurements for `B`, always inspect load metadata and metric definitions before running numerical gates. This demo checks decision consistency and **does not replace JVM diagnostics or benchmark design**.

## 8. Verifying the Mechanism: Measure What the Change Should Affect

Even when B passes the p95 threshold, check whether **the observed mechanism matches the hypothesis**:

| Change Under Test | Expected Mechanism | Evidence to Cross-Check |
| --- | --- | --- |
| Reduce Java allocations | Fewer bytes allocated per request, lower GC pressure | Allocation profiling/JFR, allocation rate, GC events, CPU, and latency |
| Reduce contention | Fewer threads waiting on locks, less blocked/wait time | JFR lock events, multi-point thread dumps, throughput, and p95 |
| Optimize query | Lower query latency / rows read / cost | DB execution plans/metrics, trace spans, pool wait, query correctness |
| Tune connection pool | Fewer requests waiting for connections | Pool in-use/pending/wait time, DB connections, DB CPU/latency, and timeouts |
| Change GC/heap | Pause/throughput/footprint distribution aligns with goal | GC logs/JFR, post-GC heap, CPU, RSS, p99, and OOM behavior |
| Add cache | Higher cache hit ratio, fewer dependency calls | Hit/miss, stale data/correctness, memory footprint, warm/cold cache behavior |

Avoid circular reasoning: "B has lower p95, so GC got better; GC got better, so B has lower p95". Only draw conclusions about GC when you **actually measured GC** and the evidence aligns with the affected requests' timing.

**Mechanisms can be trade-offs.** Expanding a thread pool can sometimes process more concurrent requests, yet also raise context switching, DB pressure, or tail latency. One metric moving favorably does not confirm system-wide improvement without checking resources and dependencies.

When the change is a **correctness bug fix**, the most important gate is passing the failing reproduction test and regression suite. Running performance benchmarks helps only if the fix carries performance risk or load sensitivity; never use a pretty p95 to excuse wrong business results.

## 9. Handling Variance and Conclusion Confidence

Runtime data is noisy. Typical variance sources:

- JIT compilation/deoptimization, class loading, caches, GC, CPU scheduling, container throttling.
- Network jitter, database plans/caches, index/updates, queues, downstream load, and batch jobs.
- Host/instance differences, overloaded load generators, clock/metric sampling, and instrumentation overhead.
- Workload mix, payload distributions, hot/cold data, retries, and request timeouts.

To reduce confusion:

1. **Repeat by design**, saving every run and its conditions. Never discard bad runs just because they conflict with the hypothesis; if dropping a run due to tooling failure, document the rule upfront or independent of desired outcomes.
2. **Use nearby control baselines** and interleave run order when appropriate. Check whether reverting B back to A brings behavior back near baseline; this strengthens evidence of impact though it is still subject to state/load effects.
3. **Inspect distributions**, not just means. For tail latency, collect enough requests in the measurement window and store p95/p99 alongside errors/timeouts; extreme samples matter to users.
4. **Distinguish the unit of sampling**. Requests inside one run can be correlated; genuinely independent runs carry different statistical weight than millions of requests within one congested period.
5. **Estimate uncertainty when needed**. Compute confidence intervals for run-level differences using suitable methods or bootstrap over independent units; never declare "95% confidence" from one measurement or three fabricated runs.
6. **Evaluate practical significance**. Differences smaller than baseline variance or with no SLO/user impact may not justify shipping, even with a small p-value in a huge dataset.

When data conflicts—for example, p95 improves at moderate load yet worsens at high load—report **the curve across load levels** and conditional conclusions. Never force opposing regimes into a single "20% faster" label.

### 9.1 Conclusion States to Distinguish

- **PASS (by predefined gate):** comparability conditions hold and all metrics/guardrails within the measured scope pass thresholds. Does not prove effectiveness across all loads or environments.
- **FAIL:** change misses the target, regresses, or violates a guardrail under valid conditions.
- **INCONCLUSIVE:** insufficient reliable evidence to call PASS/FAIL: non-equivalent load, missing data, too few samples, tooling errors, or major confounders.
- **NOT TESTED:** a workload/environment/effect outside the test plan; cannot be inferred from PASSing another workload.

These labels belong to **measurement experiments**, distinct from **fix deployed / incident closed** status.

## 10. Limitations That Must Be Stated in the Report

A responsible conclusion always anchors numbers to their actual scope. Common limitation categories:

### 10.1 Environment Limitations

- Benchmark ran in staging, not yet verified under real production traffic and topology.
- JDK 17, 2 GiB heap, 2 CPUs, and three replicas were the experimental conditions; results are not guaranteed under other configs.
- Synthetic database is smaller than production data, differing in key distribution, query plans, caches, or real contention.

### 10.2 Workload Limitations

- Tested only 100 RPS and a 70:30 mix; 300 RPS, spikes, background jobs, and large payloads are unverified.
- Measured only 10 minutes of steady state post-warmup; cold start, long-term leaks, rollovers, and post-peak states were not evaluated.
- Tested only two endpoints; batch jobs, scheduled tasks, or other APIs are not covered.

### 10.3 Measurement and Statistical Limitations

- Only three runs per variant with notable spread; insufficient to prove consistent improvement at desired statistical confidence.
- Did not verify load generator schedule accuracy or capture all timeouts; p99 may be biased.
- Used median of per-run p95s rather than pooled p95, without confidence intervals.
- Did not measure CPU throttling, DB waits, GC, or long-term effects; other causes could still explain the delta.

### 10.4 Causal Inference Limitations

- Changing code and configuration together only reveals the **combined** effect; individual contributions cannot be separated.
- Measuring A in the morning and B in the afternoon while dependencies shifted limits causal inference due to time-of-day and external load.
- Without an independent control or a revert check, you may say "consistent with hypothesis", not "root cause proven".
- Picking three favorable runs out of many introduces selection bias.

Stating limitations does not make a report "weak"; it tells readers which decisions the results can safely inform and where follow-up experiments are needed.

## 11. Example of Writing an Evidence-Proportional Conclusion

Suppose a team runs A three times and B three times in staging under the declared plan, obtaining median run-level p95s of 400 ms and 290 ms, identical error medians at 0.30%, CPU median rising 5 percentage points, and every run achieving >=95% of the 100 RPS target.

**Overstated conclusion:**

> "Version B has been proven 27.5% faster in production and completely eliminates the performance issue."

This overreaches the evidence because staging measurements do not prove production behavior, do not cover all workloads, and omit uncertainty.

**Appropriate conclusion:**

> "Across three runs per variant of the 100 RPS synthetic workload in the documented staging environment, median per-run p95 dropped from 400 to 290 ms (a 110 ms or 27.5% reduction). Median error rate held at 0.30%; median CPU rose from 57% to 62%; all runs met the minimum achieved-throughput threshold. The dataset satisfies the experiment's illustrative acceptance gate. Limitations: small run count, no confidence intervals, and unverified parity of real dependency/cache states or production traffic effectiveness; further control checks and canary monitoring are required before claiming broad deployment effectiveness."

If metrics/JFR/traces actually verify that query X reduced execution time as hypothesized, you can add: "Traces and DB metrics linked by run ID support reduced latency in query X as the primary contributing mechanism", with evidence links. Never insert this sentence unless you actually measured it.

## 12. Step-by-Step Practical Workflow

1. **Define the change and hypothesis.** Record commit/config diff, expected mechanism, primary metric, guardrails, and PASS/FAIL/INCONCLUSIVE rules.
2. **Lock the comparison contract.** Workload model, offered rate and arrival schedule, concurrency, operation mix, dataset, warm-up, duration, JDK/JVM, resources, dependencies, and metric sources.
3. **Standardize runs.** Save run IDs, timezone-aware timestamps, build digests, load generator commands, seeds, metrics, and artifact locations. Verify measurement tools work before starting.
4. **Run baseline and candidate multiple times.** Maintain equivalent conditions, use a drift-mitigation layout, and avoid mixing warm-up into steady state when testing steady state.
5. **Validate comparability.** Check offered/sent/received/completed RPS, in-flight/queues, generator errors, mix, data, instances, and dependencies; if invalid, mark INCONCLUSIVE before interpreting gains.
6. **Analyze effectiveness and guardrails.** Report individual runs, absolute/relative deltas, variance, correctness, errors/timeouts, CPU/heap/GC, and DB; never cherry-pick favorable numbers.
7. **Check mechanisms and alternative explanations.** Align logs, metrics, traces, JFR, or GC/thread evidence over the same window; retry if needed, check side effects and other workloads.
8. **Make a conditional decision.** PASS/FAIL/INCONCLUSIVE per predeclared criteria; document limitations, confidence, resource cost, action plan, owner, and canary/rollback gates if deploying.
9. **Monitor post-change.** In production, track SLOs, errors/timeouts, user impact, CPU/DB, load mix, and longer durations; retain results to compare against experimental predictions.

### Comparison Report Template

```text
CHANGE / HYPOTHESIS
- Experiment ID:
- Incident or performance problem:
- Change A -> B (commit/config/package/image):
- Expected mechanism:
- Primary metric and predeclared acceptance threshold:
- Correctness/reliability/cost guardrails:

COMPARABILITY
- Workload model, target and measured arrival/throughput:
- Operation mix, payload distribution, dataset snapshot:
- Warm-up, run duration, time zone and run order:
- JDK/JVM flags, CPU/memory, replicas, dependency state:
- Instrumentation/load generator versions:
- Deviations and sources of confounding:

RESULTS
- A runs (run IDs, values, artifacts):
- B runs (run IDs, values, artifacts):
- Absolute and relative change:
- Per-run spread / uncertainty:
- Errors, timeouts, throughput, queue, CPU/GC/DB:
- Mechanism evidence and alternative explanations:

DECISION
- PASS / FAIL / INCONCLUSIVE:
- Exact scope supported by evidence:
- Limits: environment, load, duration, sample, measurement:
- Untested cases and remaining risks:
- Next test or rollout/canary/rollback gate:
- Owner and date:
```

## 13. Common Mistakes When Verifying Changes

- **"Same 100 virtual users" called "same 100 RPS".** Closed models do not guarantee equal throughput; measure arrival and completed RPS.
- **Benchmarking only once.** Results can depend on JIT, caches, GC, or dependency load; repeat and report variance.
- **Comparing p95 of HTTP 200 responses only.** Dropped timeouts/retries create fake gains; report errors and latency policy.
- **Different warm-up between A and B.** One build has a warm cache, the other cold; invalid comparison.
- **Failing to keep input data equivalent.** Dataset, hot keys, schema/indexes, or state changes can dominate metrics.
- **Bundling multiple changes into B and crediting one line of code.** You only have evidence for the bundle; isolating parts requires another experiment.
- **Averaging p99s and calling it global p99.** Percentiles do not aggregate by averaging.
- **Ignoring guardrails when p95 looks good.** CPU, heap, database, correctness, or error rates may have regressed.
- **Failing to check the load generator.** A throttled generator or coordinated omission can make B look faster.
- **Calling correlation causation.** Ignoring mechanisms, drift, canary splits, and confounders.
- **Concluding "production fixed" from staging.** Only state results apply to the measured workload/environment and list rollout verification gates.
- **Omitting unknowns.** Readers easily turn conditional conclusions into absolute claims.

## 14. Knowledge Self-Check

1. Both versions specify `targetRps=100`, yet A completes 99 RPS while B completes 60 RPS and B shows lower p95. Why can you not call B faster "under equivalent load"?
2. B achieves 30% lower p95, yet timeouts climb from 0.2% to 5%. Does the result pass the reliability gate if the predefined rule says errors must not increase?
3. Why can you not average three per-run p99 values and call it the overall p99 of all requests for A or B?
4. If you change JVM flags, `-Xmx`, and application code simultaneously, what is the strongest causal claim you can legitimately make?
5. You have three stable A/B runs in staging; what limitations must be stated before deciding on a production rollout?
6. A change reduces median p95 yet increases CPU by 20 percentage points when the predefined budget allowed at most 8. What should the PASS/FAIL/INCONCLUSIVE status be if data is complete and workloads are equivalent?
7. How do you use traces, GC logs, or JFR to strengthen evidence for the **mechanism** of a change, rather than merely seeing "before/after differed"?
8. In a benchmark for a queued service, why must you monitor backlog over time instead of only throughput and p95 at a single point?

**Remember:** verifying a change requires **comparable load and conditions**, **predeclared criteria**, **sufficient runs/evidence**, **guardrail evaluation**, and **a conclusion bounded by what was actually measured**. "B passed the gate at 100 RPS in staging" is a useful conclusion; from it, never automatically extrapolate "B is better under every load and every production environment".