# 1.5 From Symptom to Hypothesis, Evidence, and Root Cause

> **Module:** Java Advance – runtime-diagnostics · **Group:** 1. Diagnostics Model

## 1. Objectives and Scope

When a Java application is slow, hangs, spikes in CPU, runs out of memory, or fails intermittently, what you see first is usually only a **symptom**. Good diagnostics is the process of turning a symptom into a **testable and falsifiable hypothesis**, gathering evidence from the JVM and related components, and identifying the mechanism that actually produced the incident. The goal is not to find one abnormal chart to name the bug, but to explain **why**, **under what conditions**, **by what mechanism**, and **why the remediation works**.

After this lesson, you will be able to:

- Describe an incident using metrics, timestamps, and impact scope instead of impressions like "the system seems slow."
- Distinguish symptom, observed signal, hypothesis, evidence, direct cause, root cause, and contributing factor.
- Formulate competing hypotheses and predict the observable traces if each hypothesis were true.
- Select appropriate JVM/application/OS measurements, interpret positive and negative evidence, and avoid confusing correlation with causation.
- Verify the mechanism through a chain of evidence, controlled reproduction, or reversible changes, then confirm results after fixing.

The scope is **Java runtime diagnostic reasoning**. Tools such as thread dumps, JFR, GC logs, heap dumps, metrics, and traces appear as evidence sources; this lesson does not replace deep-dive guides for individual tools.

## 2. Six Concepts to Keep Distinct

| Concept | Question It Answers | Java Example |
| --- | --- | --- |
| **Symptom** | What are users or the system experiencing? | API latency p99 jumps from 250 ms to 3 s, 5xx errors rise. |
| **Signal** | What measurements or traces exist? | 40 BLOCKED threads; HTTP queue grows; GC pauses remain low. |
| **Hypothesis** | What mechanism *could* produce the symptom? | A monitor is being held too long, forcing many requests to wait. |
| **Evidence** | What observations support or refute the hypothesis? | Multiple thread dumps at different timestamps all point to the same monitor and owner thread. |
| **Root cause** | What condition/mechanism caused the incident and can be fixed to prevent recurrence? | Code holds a shared lock while calling a slow operation; as load increases, lock wait time amplifies. |
| **Contributing factor** | What made the incident more likely or more severe? | Synchronized retries, unbounded queues, lack of alerting on lock contention. |

**Direct cause** differs from root cause. For example, an API timeout is the direct cause of the error response; requests blocked on a lock may be the proximate mechanism; designing the critical section around a slow call is the fixable root cause. An incident can have **multiple root causes**, and "root" is defined within the controllable system boundary, not as an absolute label.

**Mitigation** differs from **fix**. Adding replicas, disabling a faulty feature, or rolling back can restore service quickly, yet if the flawed synchronization design remains, the incident can return.

## 3. Start with a Measurable Problem Statement

Before launching a profiler or reading source code, write a "problem statement" containing:

1. **Impact:** which user flows/APIs, error rate, violated SLOs, affected instances, and affected customers.
2. **Delta from baseline:** p50/p95/p99, throughput, CPU, heap, GC, queues, or error rate before and after; specify units, sampling window, and sample count.
3. **Timing:** last known healthy time, anomaly onset, recovery time; synchronize timezones and clocks across sources.
4. **Occurrence conditions:** only on a specific version, node, tenant, route, load level, payload size, or time of day.
5. **Changes near onset:** deployments, flags, traffic, JVM settings, schema/indexes, dependencies, certificates, cron jobs, caches, or resource limits.
6. **What is *unknown*:** missing or potentially inaccurate data, so assumptions do not turn into facts.

Hypothetical example: "From 14:05–14:18 UTC, POST /orders p99 rose 240 ms → 2.8 s on 3/4 instances of v2.7; throughput stayed nearly flat, timeout rate jumped 0.1% → 7%; JVM CPU ~30%, GC pause p99 under 20 ms; a feature flag calling the reconciliation service was recently enabled." This statement suggests a much clearer direction than "Java is slow after deploy," yet it **does not prove** the new flag is the cause.

Avoid comparing p99 across windows with vastly different traffic or sample counts without noting it. p99 on small samples fluctuates heavily; averages can hide distribution tails. Align metrics at the request level vs. per-dependency level to avoid conflating the two.

## 4. Diagnostic Chain: From Observation to Causal Mechanism

Use the following loop, stepping back whenever evidence refutes an assumption:

**Symptom → quantification/timeline → competing hypotheses → predicted traces → evidence collection → falsification/verification → root cause → action → confirmation.**

### Step 1 — Narrow the Impact Scope and Build a Timeline

Capture timestamps for detection, onset, deploys/flags, load shifts, retry onset, rollback, and recovery. Compare **affected** instances against **unaffected** instances during the same window; this is often a better control than staring at one isolated chart.

Ask: did errors occur before the suspected deploy? Did load rise before or after latency? Is a full thread pool the initial cause or a consequence of slow requests? Something appearing **after** the symptom is unlikely to be the initial trigger, though it can still amplify the incident.

### Step 2 — Form Multiple Falsifiable Hypotheses

Each hypothesis must state the mechanism and **predicted traces**. For example, the same symptom "p99 rises, CPU is low" could stem from:

| Hypothesis | If True, Expect to See | Evidence That Weakens/Refutes It |
| --- | --- | --- |
| H1: lock contention | Multiple threads BLOCKED or parked waiting on the same resource across samples; wait time grows with load | Request-handling threads are not waiting on locks; no contention hotspot during failure window |
| H2: database pool exhaustion | Connection acquire time and pool waiter count rise; active connections hit the limit | Low acquire time, plenty of idle connections in the pool at the exact time |
| H3: slow dependency | Client spans/timeouts to the same endpoint rise; pool or socket waits align with failure window | Dependency spans stay stable; slowness occurs before or after the call |
| H4: long GC pauses | Pause timestamps in GC logs/JFR align with delayed requests | Total pause time is tiny compared to the incident; many requests are slow while JVM is running |
| H5: CPU quota/throttling | Container CPU is throttled, run queue grows, requests slow down when quota is reached | No throttling observed and no related CPU-consuming processes/threads |

"Maybe there is a JVM bug" is not yet a hypothesis. Write it as: **If [mechanism X] causes [symptom Y], I expect [observation A/B] within [time window/scope]; if [C] is observed, the hypothesis weakens.** Rank hypotheses by explanatory power, testability, impact, and measurement cost; avoid prioritizing only what is easiest to change.

### Step 3 — Collect Evidence from Least Invasive to Deeper

Start with correlation-ID logs, request metrics, existing traces, JVM/OS dashboards, and change history. Only when insufficient should you deliberately take thread dumps, JFR, GC logs, or heap dumps. Record **timestamps**, version, process ID, instance, sample size, and collection conditions.

A snapshot captures state at only one instant. Repeated thread dumps taken while the error is ongoing distinguish transient waits from persistent blocks; JFR examines events over time. Collect close to the symptom window, because dumps taken after recovery often lose the trace.

### Step 4 — Corroborate and Actively Seek Disconfirming Data

Find at least two complementary sources of evidence, such as **slow request trace → thread dump waiting on monitor → contention metric rising**. Note that two charts derived from the same source are not truly independent. Inspect non-failing cases, pre-incident windows, control instances, and failures that do not fit the pattern.

Distinguish:
- **Co-occurrence:** CPU and p99 rise together.
- **Temporal ordering:** CPU rises before p99.
- **Mechanism:** stacks/profiles prove which work CPU-consuming threads are doing and which step is slowed.
- **Intervention check:** removing or isolating the factor improves latency under equivalent conditions.

Only after linking these steps should you raise confidence in causation. Correlation IDs link events together, **but do not by themselves prove causation**.

### Step 5 — Controlled Verification

Prefer testing in staging with equivalent configuration, load scale, dataset, and version. Change **one meaningful variable** per run: e.g., shrink the critical section or move the remote call outside the lock; keep traffic and thread-pool limits constant. If verifying directly in production is necessary, use a bounded canary/flag with a rollback plan.

Strong verification answers three questions: (1) does the phenomenon reproduce when triggering conditions appear, (2) does a change targeting the mechanism eliminate the predicted trace, (3) do user metrics and side effects improve sustainably? Do not force OOM or deadlocks in production merely to "prove" a point.

### Step 6 — Finalize Root Cause and Verify Post-Fix

Describe **trigger + mechanism + impact + amplifying conditions**. Separate emergency mitigation, code/config fix, and guardrails such as bounded queues, circuit breakers, dashboards, alerts, or regression tests. Compare before/after under similar traffic, verifying you did not shift the failure elsewhere or add hidden overhead.

State "undetermined" if evidence only narrows down the area. Confidence is a conditional conclusion, not a requirement to pick a culprit.

## 5. Reading Java Runtime Signals in Context

| Signal Source | Used to Check | Interpretation Pitfalls |
| --- | --- | --- |
| Request metrics + distributed traces | Latency breakdown, retries, errors, queues, dependencies | Missing spans due to sampling or pre-span queue time skew conclusions |
| Application logs with request ID | Exceptions, branching decisions, timeouts, causal timeline | Logs under heavy error load may be dropped, async, or suffer clock skew |
| Thread dump | Thread states, stacks, owned/waited monitors, deadlocks, executors | RUNNABLE does not always equal consuming CPU; one dump does not show frequency |
| JFR (Java Flight Recorder) | CPU samples, allocations, lock contention, I/O, GC, latency events over time | Recording must cover the failure window; sampling does not measure every instruction |
| GC logs / GC metrics | Pauses, pre/post-GC heap usage, allocation pressure, collector behavior | Concurrent GC activity may be an effect of traffic/allocation, not the root cause |
| Heap dump / class histogram | Object types, retained graph, suspected retention | Large, sensitive, and costly; high instance count alone does not prove a leak |
| OS/container metrics | CPU throttling, RSS, page faults, I/O, network, file descriptors | RSS differs from Java heap; CPU % must be read against core count and quota |
| Downstream/pool metrics | Connection acquisition, wait queues, timeouts, resource limits | Full pool may be caused by slow downstream, not wrong pool size |

**Read thread states carefully:** BLOCKED typically means waiting to enter a Java monitor; WAITING/TIMED_WAITING can be waiting on a condition, parking, sleeping, or idle work. A sleeping thread that **holds a monitor** can still cause other threads to be BLOCKED. Thread pools having many WAITING threads when idle is normal. RUNNABLE from the JVM's view does not guarantee a thread is actively running on CPU at every instant.

**Memory:** rising heap used is not necessarily a leak; check the trend of retained objects across GC cycles, allocation rate, heap limits, and container RSS. Direct buffers, metaspace, native stacks, and mmap contribute to RSS outside the heap. Do not trigger a forced Full GC in production just to establish a baseline without evaluating its impact.

**CPU and GC:** high JVM CPU can come from application code, JIT compilation, allocation/GC, retry loops, or spin locks. If GC pauses are short, check CPU samples/OS throttling before blaming GC. If CPU is low while p99 is high, prioritize wait times on I/O, locks, queues, semaphores, pools, and remote calls.

## 6. Minimum Evidence Collection Commands on JDK 17+

Run on the exact host/container and in the namespace that can see the target JVM; appropriate permissions are required. Record **PID, timestamp, instance, and application version** alongside collected data. The commands below are operational examples—do not run them repeatedly without restraint in production.

~~~bash
# List Java JVMs visible to the current account.
jcmd -l

# Replace <PID> with the verified target Java PID.
jcmd <PID> VM.command_line
jcmd <PID> Thread.print -l
jcmd <PID> GC.heap_info

# Start a 60-second recording; the file is written when recording completes.
jcmd <PID> JFR.start name=diagnosis settings=profile duration=60s filename=incident.jfr

# Once the JFR file exists, view a summary using the JDK tool.
jfr summary incident.jfr
~~~

Interpretation notes:

- **VM.command_line** proves the actual JVM flags and entrypoint; compare against container configuration and launch scripts instead of guessing from source config files.
- **Thread.print -l** is helpful when suspecting monitor waits/deadlocks; capture a few snapshots a few seconds apart during the error window to compare stacks and lock owners. Do not treat every WAITING thread as "stuck."
- **GC.heap_info** provides a heap snapshot; insufficient alone to conclude a leak.
- **JFR.start** collects time-series events. Profiling/recording still carries overhead, and data may include class names, paths, stacks, or sensitive info; choose appropriate settings, duration, storage location, and access controls. Where the JDK/configuration does not support an action, rely on existing logs/metrics and note the limitation.
- **VM.native_memory summary** is useful only if Native Memory Tracking was enabled at JVM startup, such as `-XX:NativeMemoryTracking=summary`; data is not available by default.
- Heap dumps can be huge and carry far greater impact than the commands above. Collect only with a clear purpose, sufficient disk space, proper permissions, and an impact assessment.

Thread dumps generated by signals or other tools can differ in format/mechanism across JDKs. Before comparing, verify that samples come from the same PID and incident window. Do not paste stack traces containing tokens, secret URLs, or customer data into public sharing tools.

## 7. Complete Analysis Scenario: p99 Spikes Due to Holding a Monitor Too Long

*Hypothetical scenario for practicing the method; the following measurements are illustrative, not benchmark results.*

A Java API sees p99 rise from 180 ms to 2.4 s when traffic grows by 40%. Process CPU remains steady at 28–35%, and GC pause p99 stays under 15 ms. Slow requests concentrate on the order-status update endpoint. Initially, there are three hypotheses:

- **H1:** update-handling threads hold a shared monitor while executing a slow operation, forcing other requests to queue.
- **H2:** the DB connection pool is exhausted, causing waits at acquisition.
- **H3:** stop-the-world GC pauses delay concurrent requests.

**Predictions to test:** H1 predicts multiple threads waiting on the same monitor in thread dumps while one thread holding the monitor performs slow work. H2 predicts rising DB pool acquire time, active connections hitting max, and many stacks waiting to acquire. H3 predicts long pause timestamps in logs/JFR aligning with slow requests.

**Chain of evidence:** Traces show slowness sits in the internal status-update step; connection acquire time is low. Three thread dumps in the error window show many requests BLOCKED waiting on the same monitor, while the owner thread sleeps/waits on a slow operation. GC pauses remain far too small to explain 2.4 s latency. This **strongly supports H1** and weakens H2/H3 in the observed window. To avoid equating "monitor wait" with root cause, continue verifying **why the monitor is held so long**, which call path sits inside the critical section, and what load triggers it.

### 7.1 Java 17+ Example Reproducing Only the Monitor Wait Mechanism

This minimal example **intentionally** holds a monitor while sleeping to create an easily observable trace. It models lock contention—it is **not** HTTP handling code or proof that a real app sleeps inside a critical section.

Save the file as **LockContentionDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class LockContentionDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch acquired = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            synchronized (LOCK) {
                acquired.countDown();
                try {
                    Thread.sleep(20_000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "lock-holder");

        Thread waiter = new Thread(() -> {
            synchronized (LOCK) {
                System.out.println("waiter acquired lock");
            }
        }, "lock-waiter");

        holder.start();
        acquired.await();  // Ensure holder has entered synchronized.
        waiter.start();     // Waiter must wait for holder to release LOCK.
        waiter.join();
        holder.join();
    }
}
~~~

Compile and run in the first terminal:

~~~bash
javac LockContentionDemo.java
java LockContentionDemo
~~~

Within the first ~20 seconds, open another terminal:

~~~bash
jcmd -l
jcmd <PID_CUA_DEMO> Thread.print -l
~~~

Pick the PID matching the **LockContentionDemo** class, not another JVM. When caught at the right moment, **lock-holder** is typically in TIMED_WAITING due to Thread.sleep while **still owning the monitor**, and **lock-waiter** is BLOCKED waiting for that monitor. After about 20 seconds, the program exits and stdout from the program is:

~~~text
waiter acquired lock
~~~

Do not assert exact stack line locations, monitor addresses, or PIDs since they vary by JDK and run. Here CountDownLatch only ensures the holder thread acquires the monitor **before** the waiter thread starts; it is not the contended object under investigation.

### 7.2 Turning Evidence into a Root-Cause Hypothesis

Suppose application code has the structure "read state → global lock → call remote API → update state → release lock." When the remote API occasionally slows down, lock hold duration increases; every new request must queue up. **Queue wait time** grows rapidly with contention and can push p99 high even while CPU and GC remain normal.

Root-cause hypothesis: "The critical section holding a shared monitor wraps a slow I/O call; dependency latency extends lock hold time, causing multiple requests to become BLOCKED and driving p99 up as concurrency grows."

How to verify:
1. Cross-check the deployed code against thread dumps to confirm the monitor, lock owner, and actual I/O call site; verify traces/metrics for the same timestamp.
2. In a test environment, generate similar load and deliberately increase dependency latency within controlled bounds; observe waiting thread count and p99.
3. Redesign to shorten lock hold time, e.g., perform I/O outside the critical section **if** data invariants and update ordering remain correct; consider replacing the global monitor with finer-grained synchronization, bounded queues, or key-independent coordination.
4. Repeat under the same conditions, comparing p50/p95/p99, throughput, thread states, data errors, and retries. Fixing lock contention while breaking consistency is not a successful fix.

If removing the slow call from the critical section reduces BLOCKED threads and brings p99 back to baseline under similar load, confidence in the mechanism rises substantially. If symptoms persist, reopen H2/H3 or new hypotheses; do not edit the report to force-fit the initial diagnosis.

## 8. Counter-Scenario: Do Not Mistake GC or Memory for the Root Cause

Suppose after a deploy, **heap used**, GC count, and p99 all rise together. A hasty conclusion is "GC is causing slowness, increase `-Xmx`." Another causal path may be: a code change creates many temporary objects → allocation rate rises → GC runs more frequently → CPU contention and tail latency rise. In this case, the **abnormal allocation in code** is what needs fixing, while GC is the runtime's reaction.

It is also possible a slow dependency keeps requests alive longer, retaining more objects/request contexts in the heap, causing heap used to rise **after** latency rises. Data needed to distinguish them:

| Question | Data Needed |
| --- | --- |
| Are GC pauses long enough and aligned with slow requests? | GC logs/JFR with timestamps compared against request traces |
| Did allocation rate rise before or after the errors? | JFR allocation samples, throughput, deploy timeline |
| Are objects retained long-term or merely allocated heavily and collected? | Heap trend across natural GC cycles, class histogram/retained graph when needed |
| Is memory growth inside the heap or off-heap? | Heap committed/used vs. container RSS, direct/native metrics |
| Does increasing heap actually address the mechanism? | Controlled comparison and side effects: pauses, RSS limits, OOMKilled |

The fix may be eliminating excess allocations, fixing an unbounded cache, bounding concurrency, or optimizing payloads. Increasing heap can sometimes be a valid tuning step, yet it is not by itself proof of cause; and container RSS OOMKilled can happen before Java heap even touches `-Xmx`. For leaks, you need evidence of **retention growing over time under comparable conditions**, not just one large heap snapshot.

## 9. Evaluating Evidence Quality

"Good evidence" is not the evidence supporting the most appealing story. Evaluate along six axes:

1. **Right scope:** Does it come from the affected instance/PID/version/endpoint?
2. **Right timing:** Was it collected while symptoms were still occurring, with synchronized timestamps?
3. **With controls:** Is it compared against healthy periods, non-failing groups, or equivalent load?
4. **Independent:** Do traces, runtime events, and pool metrics provide distinct observational angles?
5. **Falsifiable:** What observation would make us discard the hypothesis, and have we actively looked for it?
6. **Causally linked:** Does the evidence explain the entire path from trigger to impact, and has an intervention been verified where safe?

Assign confidence levels in a grounded way:

- **Low:** only correlation or a single snapshot; multiple hypotheses remain plausible.
- **Medium:** multiple samples in the exact failure window align with one mechanism; controls and disconfirming evidence were checked, but no intervention has been tested yet.
- **High:** multi-source observation, mechanism proven, and reproduction/remediation changes traces and outcomes as predicted.

Do not turn "no error logs found" into "no errors occurred." Logging can be missing, filtered, not retained long enough, or fail to cover waiting sections. If profiling relies on sampling, absence from samples also does not guarantee a code path did not execute.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Better Practice |
| --- | --- | --- |
| Picking the cause solely from an exception name | Fixes only the symptom or misses upstream causes | Build a timeline and ask what mechanism led to the exception |
| Two charts rise together ⇒ causation | Confuses consequences/amplifiers with the trigger | Compare timing, stacks/traces, controls, and test one variable at a time |
| Seeking only evidence confirming a favorite hypothesis | Confirmation bias | Write falsifying predictions upfront and keep competing hypotheses |
| One thread dump ⇒ application deadlock | Mistakes valid waits or contention for a deadlock cycle | Take multiple samples, check owner/wait graph and progress |
| Seeing RUNNABLE ⇒ JVM burning CPU in that code | Confuses JVM state with OS CPU scheduler | Combine CPU samples, OS metrics, quotas, and duration |
| Seeing heap rise ⇒ memory leak | Confuses allocation/higher load with retention | Check trends, GC, heap/RSS, and retention chains |
| Raising thread pools/heap or timeouts unconditionally | Masks symptoms, adds queues and downstream pressure | Find true limits, queueing, and resource budgets; measure before/after |
| Taking unprepared heap dumps in production | Pauses, disk exhaustion, sensitive data exposure | Assess purpose/cost/permissions, prefer lightweight signals first |
| Measuring after rollback and concluding about failure time | Loses critical evidence | Capture timestamped evidence before changing state if safe |
| "Errors stopped after deploy" ⇒ fixed the right root cause | Could just be different load or time of day | Compare conditions, check predicted mechanisms and regressions |

A test can **disprove a hypothesis and still be valuable**: ruling out H3 helps focus on H1/H2. Do not modify code just to prove what you already believe; let the data drive the decision.

## 11. Reusable Incident Report Template

~~~text
INCIDENT / IMPACT
- Service, version, instance, affected users/APIs:
- Start/end timestamps, timezone, SLO/error/latency/throughput:
- Baseline and sampling method:

VERIFIED OBSERVATIONS
- Symptoms:
- Metrics/logs/traces/JFR/thread dumps/GC logs (PID, timestamp, source):
- Occurrence conditions and controls:
- Missing data / measurement limitations:

HYPOTHESES
- H1: mechanism → predicted traces → supporting/refuting observations
- H2: mechanism → predicted traces → supporting/refuting observations
- Hypotheses not yet ruled out:

CAUSAL CONCLUSION
- Trigger:
- Proximate mechanism:
- Root cause (if sufficient evidence):
- Contributing factors:
- Confidence level and basis; remaining uncertainties:

ACTIONS / VERIFICATION
- Mitigation and rollback capability:
- Root-cause fix, guardrails, regression tests:
- Before/after metrics under comparable conditions:
- Verification outcome; owner monitoring follow-up:
~~~

This report must show the **link between each conclusion and actual evidence**, not merely list tools run. For snapshots, JFR files, or heap dumps containing sensitive data, store them in access-controlled locations, cite appropriate references, and follow system retention policies.

## 12. Self-Check Exercises

**Exercise A.** An API shows rising p99, low CPU, and many threads in TIMED_WAITING. Is that enough to conclude a deadlock? **No.** Check stacks, what they are waiting on, whether any monitors are held, whether requests continue progressing, multiple time samples, and related traces. TIMED_WAITING may simply be valid sleeping threads.

**Exercise B.** After a code change, allocation rate triples and GC frequency increases, yet each GC pause is very short. Is calling "GC is the root cause" justified? **Not yet.** Check the allocation source, CPU consumed by GC, latency correlation, and the new code path. Elevated allocation may be the mechanism needing remediation.

**Exercise C.** Active DB pool connections hit max, acquire time rises, and downstream latency had already risen beforehand. Will merely increasing pool size solve the root cause? **Inconclusive.** Pool exhaustion may result from connections being held longer due to slow downstream; enlarging the pool could even amplify pressure. Link traces, pool waits, query latency, retries, and DB limits.

**Exercise D.** A canary build removes I/O from the critical section, BLOCKED threads drop sharply, yet overall service p99 stays high. What conclusion fits? **One contention mechanism improved, but it does not fully explain the symptom.** Check routes, canary traffic share, remaining bottlenecks, and competing hypotheses.

**Completion criteria:** For a real or simulated incident, write a statement with baseline and timestamps, at least two falsifiable hypotheses, predicted traces and corresponding measurements, a table of positive/negative evidence, a causal mechanism chain, and a verification plan for the fix. A well-argued "insufficient data" conclusion is better than a guessed root cause.

## Takeaways

- **Symptoms** are the starting point, **hypotheses** are testable mechanisms, **evidence** is properly scoped and timestamped data, and **root cause** must explain the causal chain and point to preventive measures.
- Always seek **falsifying** evidence, track surviving hypotheses, and cross-check application–JVM–OS–dependencies. No single metric suffices to diagnose every Java runtime issue.
- High-quality conclusions follow **trigger → mechanism → symptom → verification → post-fix effect**; explicitly record confidence levels and unknowns.