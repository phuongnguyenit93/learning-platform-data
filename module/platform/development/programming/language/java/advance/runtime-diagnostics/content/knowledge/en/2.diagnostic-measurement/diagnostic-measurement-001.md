# 2.1 Defining Reproduction Scenarios, Input Workload, and Diagnostic Exit Criteria

## Learning Objectives

A Java incident investigation is only trustworthy when others can understand **under what conditions the error occurs**, **what kind of load the system must process**, and **what evidence is sufficient to close the diagnosis**. This lesson guides you through designing those three components before collecting large volumes of logs, thread dumps, or performance profiles.

After this lesson, you will be able to:

- Write a **reproduction contract**: trigger operation, environment, data, failure oracle, control conditions, and how to repeat it.
- Describe a **workload** by request arrival rate, concurrency level, operation mix, payload size, duration, data, and warm-up phase.
- Set verifiable **diagnostic exit criteria**: evidence sufficient to confirm/refute hypotheses, reproducibility level, confidence level, and handoff steps.
- Distinguish between **"diagnosis complete"**, **"mitigation verified"**, and **"fix verified"**.

## 1. Start with an Observable Symptom

Descriptions like "JVM is slow", "service hangs", or "occasionally crashes" are not enough to design a measurement. They do not tell us the subject, timing, impact, or what counts as a failure.

Turn the report into a testable statement:

> "In application version X, when handling roughly 100 requests/second for 10 minutes, the `POST /checkout` path shows p95 latency increasing from around 180 ms to over 800 ms; the phenomenon is concentrated on two instances after load increases, identified via request IDs and latency charts."

The numbers above are **illustrative only**. For a real incident, you must fill in actual measurements, data sources, and time windows.

A useful symptom statement typically answers:

| Question | Information to Record |
| --- | --- |
| **What is wrong?** | Wrong result returned, HTTP 5xx, timeout, hung request, throughput drop, post-GC heap growth, high CPU, or restart |
| **Where is it wrong?** | Service name, endpoint/job, instance/pod, deployment region, build version, and JDK |
| **When did it start?** | Timestamp with timezone, duration, frequency, and whether it correlates with a deploy/config change |
| **Who and how much is affected?** | User group, requests, partitions, tenants, business impact |
| **Compared to what?** | A baseline of the same operation type, data, and load in a state considered healthy |
| **Primary evidence?** | Metric queries, trace IDs, timestamped logs, test cases, thread/JFR snapshots, and storage locations |

**A symptom is not a root cause.** A request timeout only confirms that the request exceeded its deadline; it does not prove the origin is GC, database, queue, network, or a specific piece of code. Write the symptom in a way that does not "bake in" a root-cause hypothesis.

## 2. What Is a Reproduction Scenario?

A reproduction scenario is **a set of conditions and actions described clearly enough to repeat the phenomenon**. It resembles a repeatable experiment: hold the necessary factors constant, intentionally vary one factor, and observe the result.

It consists of six parts:

1. **Starting point:** artifact/build hash, JDK/JVM, important flags, OS/container, configuration, dependencies, and initial data state.
2. **Trigger:** request, job, task schedule, specific input, sequence of operations, or load ramp timing.
3. **Execution procedure:** step-by-step instructions or load-generation script, including startup, warm-up, measurement duration, and stop procedure.
4. **Failure oracle:** verifiable conditions such as error codes, incorrect output, exceeded deadlines, blocked threads, or process exit.
5. **Evidence and control:** request IDs, logs, traces, charts, metrics, test output, and a healthy run under equivalent conditions.
6. **Repeatability:** how many runs out of total attempts exhibit the failure, whether it depends on timing/load/order/seed, and what factors remain uncontrolled.

### 2.1 Record Enough Context for Others to Reproduce

Information to fix or record depending on the incident type:

- **Code and JVM:** commit or image digest, JDK version and vendor, startup flags, `-Xms`/`-Xmx` if relevant, libraries/drivers.
- **System:** allocated CPUs, container memory limit, OS, deployment region, topology, DNS, network route.
- **Application:** profile, feature flags, timeouts/retries, thread/connection pool sizes, cache TTL, log sampling.
- **Data:** seed data, dataset size, distribution shape, hot keys, index state, schema/migrations, required tenant/permissions.
- **Dependencies:** database, queue, object storage, external APIs, their versions, latencies, and limits.
- **Timing and lifecycle:** freshly started or warmed up, cold or warm cache, uptime before the error appears, concurrent cron/batch jobs.
- **Input:** method/path, relevant headers, sanitized request body (secrets stripped), item count, payload size, request type.

You do not necessarily have to freeze **every** system variable: record those that could affect the phenomenon and make explicit what remains unknown. In particular, "same source code" does not mean "same binary, JDK, flags, configuration, and load".

### 2.2 Classify the Reproducibility Level

**Deterministic reproduction.** Given the same input and preconditions, the error always occurs. For example, a fixed input causes a Java method to return an incorrect result. Unit/integration tests and code inspection are usually effective here.

**Load/state-dependent reproduction.** The error only appears when active connections increase, memory fills up over time, cache is cold, queues grow long, or a specific sequence of operations occurs. You must describe the *state history prior to measurement*, not just a single request.

**Intermittent/probabilistic reproduction.** The error appears irregularly, potentially due to race conditions, scheduling, network, or deadlines. Instead of demanding "must fail 100%", record `k/n` runs, duration, and conditions of each run. For example, "6/20 runs timed out within 10 minutes at equivalent rate" is not enough to conclude the true probability is exactly 30%.

**Not reproducible in a controlled environment.** You can still diagnose from production evidence (logs/traces/JFR/metrics) if sufficient traces were captured. Clearly document the limitations and confidence level, and do not claim a hypothesis is disproven just because "local tests didn't fail".

### 2.3 Reproduction Contract Template

```text
Incident: [quantified symptom, impact]
Run ID / time / timezone:
Service, build, JDK, JVM flags:
Environment: CPU/memory limits, dependencies, and relevant config
Initial state: data, cache, queue, connections, warm/cold
Input: operations, request mix, data size/type
Trigger: step-by-step, seed (if any), load level, and duration
Failure oracle: clear oracle, e.g., timeout > 2 s or wrong result
Control: healthy version/window under equivalent conditions
Observations: k/n runs or p95/p99 metrics, errors, throughput
Evidence: source name, timestamp, request/trace ID, storage location
Stop condition and test data cleanup procedure:
Uncontrolled factors / hypotheses to verify:
```

A good runbook is specific enough that a teammate can rerun it without asking "which endpoint do I call?", "what data do I use?", "how many requests do I send?", or "what counts as a failure?".

## 3. Input Workload Must Be Defined Before Measuring

**Workload** is the distribution of work a program receives and processes over time. Two runs with the same total of 10,000 requests can produce very different JVM states if one spreads them evenly over 10 minutes and the other bursts them into 10 seconds.

### 3.1 Workload Dimensions

| Dimension | Useful Way to Describe |
| --- | --- |
| **Arrival rate** | Requests/second (RPS), events/second, messages/second, whether ramp-up and spikes exist |
| **Concurrency** | Number of requests or tasks actively in progress; for closed-loop clients, max virtual users / in-flight requests |
| **Mix** | E.g., 70% read, 20% search, 10% write; distinguish fast/slow branches |
| **Input size/complexity** | Payload bytes, record count, size distribution, query type, hot/cold keys |
| **Duration** | Warm-up, ramp, steady-state measurement window, bursts, recovery time |
| **Data and state** | Dataset, cache hit/miss, connection pool, queue depth, accumulated data |
| **Dependency conditions** | Database/API latency, timeouts, injected errors, rate limits, and connection limits |
| **Machine conditions** | CPU/memory limits, instance count, GC/JVM flags, background tasks |

**Do not use "100 users" as a substitute for "100 RPS".** One user can send more or fewer requests depending on think time, response time, and scheduling. The number of active tasks in flight is also not necessarily equal to the number of clients.

Illustrative examples:

- **Open load model:** the generator proactively sends 50 new requests per second even if the server is slow; if the server cannot keep up, queues/backlogs can grow.
- **Closed load model:** 20 concurrent clients, each waiting for a response before sending the next; when responses slow down, total RPS typically drops accordingly.

The two models answer two different questions. When testing capacity against external traffic, check whether the load model matches reality; when reproducing a race condition, concurrency and task scheduling may matter more than average RPS.

In steady state, Little's Law states that **average number of work items in the system = average completion rate × average time spent in the system** (given consistent measurement boundaries and assumptions). This is a relationship for sanity checking, **not** a direct conversion formula between RPS and user count when the system is congested or unstable.

### 3.2 Separate Each Run into Three Phases

1. **Preparation and warm-up:** start the system, warm up JIT, class loading, caches, or connection pools if the scenario is warm-state; explicitly note if measuring cold start. Do not mix warm-up samples into the steady-state measurement window.
2. **Measurement phase:** fix the load schedule, dataset, and time window. Collect latency, error rate, achieved throughput, backlog, CPU/heap/GC, thread/connection pools, and dependency timing appropriate to the problem type.
3. **Recovery and cleanup:** reduce/stop load, check whether queues drain, verify whether resources return to steady levels, clean up test data, and save artifacts. For leaks or cumulative anomalies, the post-load observation window can be decisive.

**Measure the load generator:** if the load generator itself is overloaded, dropping connections, or drifting from schedule, server charts no longer reflect the intended workload. Record both **target/offered RPS** and **achieved RPS**, client-side errors, client timeouts, in-flight count, and load generator responsiveness.

### 3.3 Choose Representative Input Data

- Choose both typical cases **and** edge cases: large payloads, hot keys, high record counts, cache misses, and requests hitting many dependencies.
- Fix the random seed when generating synthetic data for repeatability; also keep in mind a single seed may not be representative. Use multiple documented seeds if the error depends on distribution.
- For data-mutating scenarios, ensure each run starts from an equivalent state or has a reset mechanism. Accumulated data can make subsequent runs slower even when code has not changed.
- Use synthetic or sanitized data; avoid copying tokens, personal data, or raw production information into logs and reports.
- A "small request, hot cache" scenario is not representative of an incident that only happens on large queries, cold caches, or skewed data.

## 4. Establish a Baseline and Choose Metrics Before Running

A **baseline** is a reference observation for comparison. It may be a healthy environment, a previous release, or a healthy time window in the same environment. A baseline is trustworthy when **equivalent conditions** are recorded for data, workload, duration, instance count, and configuration.

For a Java service, you typically need a combination of:

- **User signals:** p50/p95/p99 latency, error rate, timeout rate, output correctness.
- **Volume:** incoming requests, completed requests, achieved throughput, waiting requests, queue depth.
- **JVM:** process CPU, heap used after GC, allocation rate, GC pause time/frequency, thread count, and blocked/waiting threads.
- **Infrastructure and dependencies:** CPU throttling, memory/container OOM, DB connections, pool wait time, network/errors, downstream latency.
- **Localization evidence:** logs with correlation/request IDs, trace spans, JFR, or thread/heap dumps when needed.

A single metric is rarely enough. For example, p99 rising together with GC pauses only forms a **hypothesis** that GC contributes to latency; you must align timestamps, cross-check requests/traces, and rule out queuing/dependencies before concluding.

### 4.1 Define Metrics Clearly to Avoid Mis-measurement

- **Latency:** measured from where to where? At the client from send to full response receipt, at the gateway, or inside the handler? Does it include queuing, retries, and timeouts? Never compare metrics with different boundaries as if they were identical.
- **Error rate:** is the denominator all incoming requests, all completed requests, or only valid requests? Does the numerator include 5xx, timeouts, or specific business errors? Document how expected 4xx responses are handled.
- **p95:** the 95th percentile of observations; different from the mean. With few samples, p95/p99 are unstable, so choose an appropriate window and sample size, and repeat runs when variance is high.
- **Throughput:** RPS requested by the generator differs from RPS completed by the server. Under saturation, backlog can grow even while completed throughput stays flat.
- **Thresholds:** stated thresholds should derive from SLOs, baselines, or investigation goals—never chosen arbitrarily after seeing the results.

You must also specify how failed requests are counted in latency percentiles: some systems report only successful-request latency, while others include all attempts. If timeouts are excluded from the success histogram, p95 can look great while the error rate climbs sharply.

## 5. Design Comparable Runs

A simple design uses **one intentional variable changed** between runs:

| Run | Artifact | Workload | Configuration | Goal |
| --- | --- | --- | --- | --- |
| A – baseline | Known healthy build | Same input/load model | Reference configuration | Record healthy behavior |
| B – incident | Build under investigation | Same as A on relevant dimensions | Same as A, except difference under test | Verify symptom |
| C – hypothesis | Same build as B | Same as B | Change only one suspected factor | Test hypothesis |
| D – verify | Build with fix/mitigation | Same as B | Intended deployment configuration | Verify effectiveness and regressions |

If you cannot change just one variable (for example, production differs from staging), list the remaining differences and evaluate whether they weaken the conclusion. Do not call a difference "ruled out" without measuring it.

**Hypothetical example:** An API runs fine at 40 RPS, but timeouts increase at 120 RPS. Trying a larger DB connection pool reduces timeouts, which supports the pool-contention hypothesis, but you still need to check connection wait time, active connections used, query latency, and impact on the DB. Simply seeing "increasing the pool helped" does not prove the root cause.

For rare phenomena or race conditions, you may need to collect multiple thread dumps/JFR samples, run longer loops, try multiple seeds, or synchronize task schedules. When reproduction is difficult, explicitly record the **level of uncertainty** and missing observation conditions.

## 6. Diagnostic Exit Criteria: Define First, Evaluate Later

An investigation can end in several valid states; do not use a single word "done" to obscure the gap between understanding a bug and fixing it.

### 6.1 Three Distinct Milestones

| Milestone | What Must Be Present? | What Is Not Implied? |
| --- | --- | --- |
| **Diagnosis complete** | Symptom, impact, and trigger conditions are clear; evidence is sufficient to confirm the cause or isolate it with stated confidence/limitations; next steps have an owner | Does not imply the bug is fixed or gone |
| **Mitigation verified** | Impact-reducing measure has before–after measurements, introduces no obvious new incidents; monitoring and rollback plan exist if needed | Does not imply the root cause has been eliminated |
| **Fix verified** | Change fixes the actual root cause; failing test/reproduction scenario and related workload pass acceptance gates; post-deploy monitoring and regression checks pass | Does not mean the system can never fail again |

If **the cause is not yet verified**, a valid outcome can be "investigation remains open, with collected evidence and prioritized hypotheses". Do not promote it to `Diagnosis complete` merely because time ran out or reproduction temporarily stopped.

### 6.2 Checklist for "Ready to Close Diagnosis"

1. **Scope defined:** failure scenario, environment, build, and trigger conditions are documented as a runbook.
2. **Traceable evidence:** every major conclusion points to metric queries, trace/log IDs, dump/test outputs, timestamps, and run IDs.
3. **Reproduced or reproduction limits explained:** frequency and conditions are clear; if not reproduced, field evidence and uncertainty are stated.
4. **Hypotheses tested:** describes which test or comparison supported/refuted each hypothesis; avoids concluding from correlation alone.
5. **Root cause and mechanism described:** failing layer (logic, pool, GC, dependency, input, config, resources, etc.) stated with appropriate confidence.
6. **Action verification criteria defined:** thresholds, workload, repetition count, and environment needed to validate the fix.
7. **Clear handoff:** owner, planned change, remaining risks, monitoring procedure, or decision to keep investigation open.

When the goal is strictly **root-cause identification**, you do not have to wait for a fix to be deployed before closing the diagnosis step; record the remediation status separately. When the goal is **full service recovery**, add fix-verification and monitoring gates.

### 6.3 Quantitative Criteria for a Measurement Scenario

Good criteria are specific enough to answer PASS/FAIL and include applicability conditions.

**Illustrative example, not a universal SLO recommendation:**

```text
Service: checkout-service, recorded build and JDK
Workload: 100 target RPS, 70% read / 30% checkout,
          payload from fixed sample dataset
Load generation: open model, 2-minute ramp
Warm-up: 3 minutes; measurement window: 10 minutes
Repetitions: minimum 3 independent runs, same model and initial state
Measurement sources: client metrics + server metrics + traces tagged with run ID
Acceptance gate: p95 < 300 ms; HTTP 5xx and timeout < 1%
                 completed throughput does not drop below measurement target;
                 no unbounded queue growth during steady state
Counting policy: latency of successful and failed requests
                 recorded separately, errors not dropped from error rate
Comparison conditions: equivalent instance count, data, JVM flags,
                       dependencies, and resource limits
Output: per-run table, metric queries, trace IDs, and deviations
Safe stop: abort load if service impact or resources
           exceed agreed thresholds
```

Values like `100 RPS`, `300 ms`, and `1%` must be replaced with your real system's thresholds. If 100 incoming RPS is not achieved because the load generator is slow or the environment is under-provisioned, do not mark PASS based on a "pretty" p95 at lower load.

**Do not force every phenomenon into latency/error criteria.** For a memory leak, the criterion might be heap used after full/major GC or stable heap over a sufficiently long observation window under the same workload. For a deadlock, the criterion might be absence of the lock-wait cycle under the reproduction pattern and all tasks completing within deadline. For incorrect data, the criteria are correctness assertions, not p95.

## 7. Java 17+ Example: Checking Criteria with Fixed Data

The following self-contained example is **not a benchmark tool or load generator**. It demonstrates how to turn quantitative criteria into a verifiable computation, separating baseline and incident states. Each run uses **20 fixed samples simulated in code**; the output is completely deterministic. Twenty samples are far too few to draw statistically meaningful p95 conclusions for production.

Create `DiagnosticCriteriaDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class DiagnosticCriteriaDemo {
    record Sample(int latencyMs, boolean error) { }

    record Metrics(int total, int errors, int p95Ms) {
        double errorRate() {
            return (double) errors / total;
        }
    }

    static List<Sample> samples(boolean incident) {
        List<Sample> result = new ArrayList<>();
        for (int i = 0; i < 20; i++) {
            int latency = (incident && i >= 18)
                    ? 600
                    : 100 + (i % 5) * 10;
            boolean error = incident && i == 19;
            result.add(new Sample(latency, error));
        }
        return result;
    }

    static Metrics summarize(List<Sample> samples) {
        if (samples.isEmpty()) {
            throw new IllegalArgumentException("empty samples");
        }

        int[] latencies = samples.stream()
                .mapToInt(Sample::latencyMs)
                .sorted()
                .toArray();
        int errors = (int) samples.stream()
                .filter(Sample::error)
                .count();

        // Nearest-rank p95: ceil(0.95 * n), one-based.
        int index = (int) Math.ceil(0.95 * latencies.length) - 1;
        return new Metrics(samples.size(), errors, latencies[index]);
    }

    static void report(String runId, Metrics m) {
        boolean pass = m.p95Ms() <= 200 && m.errorRate() <= 0.01;
        System.out.printf(Locale.ROOT,
                "%s: n=%d errors=%d errorRate=%.1f%% p95=%dms verdict=%s%n",
                runId, m.total(), m.errors(), m.errorRate() * 100,
                m.p95Ms(), pass ? "PASS" : "FAIL");
    }

    public static void main(String[] args) {
        report("baseline", summarize(samples(false)));
        report("incident", summarize(samples(true)));
    }
}
```

Compile/run on JDK 17 or higher:

```bash
javac DiagnosticCriteriaDemo.java
java DiagnosticCriteriaDemo
```

Exact stdout:

```text
baseline: n=20 errors=0 errorRate=0.0% p95=140ms verdict=PASS
incident: n=20 errors=1 errorRate=5.0% p95=600ms verdict=FAIL
```

Why is this result right?

- Baseline has 20 samples with latencies cycling through `100, 110, 120, 130, 140 ms`, each appearing four times. The nearest-rank p95 position is the 19th position (1-based), equal to `140 ms`; there are zero errors.
- Incident has 18 small samples and two `600 ms` samples. The 19th position is `600 ms`; one sample is marked as an error, so error rate is `1/20 = 5%`.
- The illustrative rule sets `p95 <= 200 ms` **and** `error rate <= 1%`. Baseline PASSes, incident FAILs.
- The program computes latency percentiles over **all samples, including samples marked as error**. In real systems, state this rule explicitly and usually also report successful-request latency separately so timeouts are not masked.

**Important limitation:** this code does *not* generate 100 RPS, create real concurrency, measure processing time, or simulate JIT, GC, or network. It only checks criteria against a predetermined dataset. In real benchmarks, replace `samples(...)` with data collected from the exact measurement window, include failed requests, combine JVM/dependency evidence, and repeat enough times.

## 8. End-to-End Example: Going from a Timeout Report to a Measurement Contract

Suppose there is a report: "After increasing load, `POST /checkout` times out more often." Follow this order, noting that the numbers below are **an illustrative scenario only**.

### Step 1: Define the Symptom

- `POST /checkout` returns timeouts when load increases; need to verify timeout rate, latency, and client deadline limits.
- Record specific version, region, instances, and timestamps. Attach request IDs to connect client, gateway, application, and database traces.
- Do not jump to concluding "GC is broken" or "not enough connections" at this step.

### Step 2: Build the Reproduction Scenario

- Use a test dataset of recorded size containing no real customer data.
- Record `JDK 17`, artifact image digest, `-Xmx`, and timeout/pool configuration if relevant.
- Starting from the same initial data state, test 20, 60, and 100 RPS sequentially, each with a documented warm-up and measurement window. If workload changes between runs, document the difference explicitly.
- Measure offered and completed RPS, p95/p99, 5xx/timeouts, connection pool wait, DB latency, GC pauses, and CPU. Record a run ID for each level.

### Step 3: Verify Hypotheses

Suppose at 100 RPS, p95 rises along with pool wait time and active connections hitting the limit. That is **supporting evidence** for the pool-exhaustion hypothesis, not the sole proof. Also check slow queries, long-running transactions, DB-side timeouts, and queuing; if adjusting pool size in the test environment, hold the remaining factors equivalent and measure the effect on the database.

### Step 4: Close with an Evidence-Backed Conclusion

A good conclusion records:

```text
Symptom: increased timeouts on POST /checkout when load >= [measured level]
Conditions: specific build/JDK/config/dataset/run ID
Evidence: trace [ID], pool wait [metric], error rate [metric]
Hypotheses confirmed/refuted: [conclusion and test]
Limitations: [unmeasured factors or environment differences]
Decision: [fix or mitigation direction, owner]
Verification gate: [workload, repetitions, latency, errors, resources]
Status: diagnosis / mitigation / fix verified, each milestone stated clearly
```

Do not conclude with "saw the pool was full so increased the pool". Increasing the pool can mask symptoms or overload the DB. The goal is to find the bottleneck mechanism and then verify the corresponding remedy.

## 9. Common Mistakes When Defining Scenarios and Criteria

**1. No failure oracle.** "Run it and see if it looks slow" cannot be compared across runs. Define concrete error codes, latency bounds, incorrect outputs, deadlines, queues, or thread states.

**2. Recording only total requests.** 10,000 requests spread over 30 minutes is very different from a burst of 10,000 requests in 10 seconds. Record arrival schedule, mix, concurrency, input, warm-up, and duration.

**3. Changing multiple variables at once.** Increasing `-Xmx`, changing a query, expanding the pool, and lowering load all at once until the error vanishes leaves you not knowing which factor worked. Use controlled runs and document differences.

**4. Comparing baselines under different conditions.** The healthy build was measured with a warm cache on an 8-CPU host, while the failing build ran with a cold cache on a 2-CPU container; comparing p95 directly can lead to false conclusions.

**5. Looking only at successful requests.** Timeouts rise, but a histogram containing only 200 responses makes p95 look low. Report both errors/timeouts and the latency inclusion policy.

**6. Confusing concurrency with arrival rate.** Treating virtual user count as RPS without measuring actual throughput; concluding load is equivalent when it is not.

**7. Collecting once and generalizing.** Phenomena depending on JIT, GC, races, caches, or networks have variance. Repeat runs, record distributions and confidence levels, especially for p99 or rare errors.

**8. Forgetting measurement-tool interference.** Profilers, verbose logging, heap dumps, and load generators can skew timing or load; document observation config and its overhead. Run load tests in controlled environments and stop when safety limits are exceeded.

**9. Declaring "fixed" because it failed to reproduce once.** A single PASS at a lower workload does not prove the bug is gone. Run the exact trigger scenario, complete enough repetitions, and check for side effects.

**10. Failing to save evidence.** Conclusions without timestamps, run IDs, metric queries, and traces/logs are difficult to audit or revisit.

## 10. Short Handoff Template for an Investigation

```text
[SCENARIO]
Issue / impact:
Service + build + JDK + env:
Trigger + preconditions:
Input dataset / seed / payload:
Load model / RPS / concurrency / mix / duration:
Warm-up + measurement window + timezone:
Failure oracle + baseline:
Reproduction k/n runs + run IDs:

[EVIDENCE]
Metrics and query/window:
Trace/log/thread/JFR IDs:
Hypotheses tested, controls, observations:
Root cause or remaining uncertainties:

[EXIT CRITERIA]
Diagnosis evidence gate:
Mitigation validation (if applicable):
Fix verification workload + numerical thresholds:
Regression checks + monitoring window:
Owner / decision / remaining risk:
```

## 11. Self-Check Questions

1. Why does 100 virtual users not equal 100 requests/second? How do open and closed load models differ?
2. An error occurs in production only after 30 minutes of uptime and does not reproduce on local restart. Which state and lifecycle factors need to be added to the runbook?
3. A system reports p95 = 200 ms, yet 15% of requests time out. Why can you not conclude "latency target met" without knowing the denominator and how failed requests are recorded?
4. You changed `-Xmx`, increased the DB pool, and modified a query in the same round; the error disappeared. What are you still missing before saying you found the root cause?
5. What criteria allow marking **diagnosis complete** while **not yet** marking **fix verified**? In an unreproducible case, what limitations must be documented?
6. If a benchmark targets 100 RPS, yet the server only receives/completes 50 RPS, what must be checked before accepting a PASS result?

**Remember:** Before measuring, explicitly write down **the reproduction scenario and state**, **the input workload model**, **the failure oracle**, **an equivalent baseline**, and **verifiable exit criteria**. Only then do logs, metrics, traces, and JVM data become evidence for decision-making rather than disconnected snapshots.