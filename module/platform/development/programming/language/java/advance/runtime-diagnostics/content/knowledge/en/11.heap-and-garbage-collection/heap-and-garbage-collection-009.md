# 11.9 Identifying required evidence before changing heap size or GC parameters

## Objectives

When a Java application is slow, consumes a lot of memory, or throws out-of-memory errors, increasing the heap or tuning the Garbage Collector (GC) is an **intervention hypothesis**, not a default conclusion. Before making changes, operators need to prove the issue relates to memory/GC management, determine actual resource limits, and establish baseline metrics to evaluate both benefits and side effects.

After this lesson, you should be able to answer four questions: **(1)** Which symptom is violating targets? **(2)** Which data links that symptom to heap/GC? **(3)** What could be affected by the planned change? **(4)** How will you confirm the change is better and know when to roll back?

Illustrative scope: HotSpot/OpenJDK 17+ (especially JDK 21), with G1 as a common example. Flag names, GC capabilities, and tools may vary across JVM versions/vendors; always verify actual configuration.

## 1. Define the problem before picking parameters

There is no single "right" heap size for every system. A larger heap can reduce collection count yet increase container memory pressure; a smaller pause goal can increase GC frequency and CPU cost. GC is only one of many sources of latency.

First, record clearly:

- **Symptom:** p95/p99 latency breaching SLO, throughput drop, rising error rate, high CPU, process OOMKilled, OutOfMemoryError, or long pauses.
- **Timing and scope:** when did it start; which pods/instances are affected; only during traffic spikes, after deploy, or in steady state; is it reproducible?
- **Acceptable thresholds:** latency SLO, minimum throughput, error budget, CPU and memory limits, operational safety requirements.
- **Context:** JDK/vendor/version, active collector, heap flags, CPU quota, cgroup/container memory limit, replica count, and workload characteristics.

A sawtooth `heap used` graph only shows that the JVM is allocating and collecting; **by itself it does not prove the heap is too small**. Similarly, p99 rising alongside high CPU is not enough to prove GC is the culprit.

### Distinguishing memory concepts

| Concept | Meaning when reading metrics | Common confusion |
| --- | --- | --- |
| Heap used | Heap memory currently in use at sampling time | Not synonymous with live objects remaining after GC |
| Heap committed | Heap portion the JVM has committed from the OS | Does not necessarily equal heap used or RSS |
| Heap max / -Xmx | Heap capacity ceiling permitted by the JVM | Not the ceiling for total process memory |
| Live set (estimated) | Objects still reachable after an appropriate GC run | Occupancy immediately after a young GC is not an absolute live-set measurement |
| Non-heap/native | Metaspace, code cache, stacks, direct buffers, internal JVM regions, and native allocations | Can drive RSS up even when the heap has free space |
| RSS / working set | Physical memory / working set observed at the process/container level | Differs from reserved/committed reported by the JVM; tool-dependent |
| GC pause (STW) | Time the application must stop for the corresponding GC/safepoint phase | Cannot replace full latency measurements or CPU spent by concurrent GC |

**Key takeaway:** OutOfMemoryError: Java heap space, OutOfMemoryError: Metaspace, native thread errors, and container OOMKilled have different causes as well as different evidence to inspect.

## 2. Minimum evidence dossier

Before any proposal to change heap/GC settings, collect data within the same time window and under the same load conditions. Each source answers its own question:

| Group | Evidence required | Used to decide |
| --- | --- | --- |
| Application targets | RPS/throughput, p50/p95/p99, errors/timeouts, SLO, spike timestamps | Is there a real problem and which metric must the change improve? |
| Workload | Request mix, concurrency, batch size, payload distribution, cache warm-up, deploy/scaling events | Are we comparing identical loads and operating phases? |
| Runtime config | Java version/vendor, active GC, -Xms/-Xmx, MaxRAMPercentage if applicable, JVM flags, CPU/memory quota | Under what limits is the JVM actually running, and do they match assumptions? |
| Heap | Used/committed/max over time, usage after GC cycles, peaks under load | Does the heap lack headroom, face allocation bursts, or have a growing live set? |
| GC activity | Timestamps, GC type/cause, pause duration, frequency, total GC time, Full GC, concurrent cycles, allocation/evacuation failure signs if reported by collector | Is there a plausible causal correlation between GC and the symptom? |
| CPU and OS/container | Process/container CPU, throttling, RSS/working set, memory limit, OOM events, swap/page pressure where applicable | Are there off-heap issues or resource limits that would make tuning backfire? |
| Object allocation/retention | Allocation hotspots from JFR/profiler, class histogram/heap dump if truly needed, live object trend | Would raising heap merely delay a leak, or is the workload allocating too much? |
| Other latency sources | Thread states, lock contention, I/O, database/network latency, non-GC safepoints | Does another cause explain p99 better? |

**Minimum to conclude:** (a) measured symptom; (b) verified configuration and resource limits; (c) timestamped heap and GC data; (d) correlation with load and latency; (e) before/after measurement plan. If any item is missing, state "insufficient evidence" instead of guessing parameters.

### Time alignment and reliability

Use consistent timezones/UTC timestamps, reconciling clocks across APM, OS, and GC logs. Measure across multiple comparable load intervals, covering both normal periods and failures; separate warm-up from steady state. Avoid concluding from a single heap snapshot or a single log event. Record sampling times, configuration, units (MiB, ms, %, requests/s), and build versions.

## 3. Collecting evidence on a running JVM

The examples below use JDK 17+ and a Linux/macOS shell; adjust PID/paths for your actual environment. Attach commands typically require the same OS user as the Java process, appropriate container permissions, and JDK tools installed; some images ship only a JRE or restrict attach mechanisms.

### 3.1. Confirming JVM, flags, and current heap

~~~bash
java -version
jcmd -l
PID=12345  # Replace with the real PID of the process to inspect
jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" GC.heap_info
jstat -gcutil "$PID" 1000 30
~~~

How to read:

- **VM.command_line / VM.flags:** confirms the process's actual flags, avoiding reliance on outdated deployment docs. Arguments may contain sensitive data: share only sanitized output.
- **GC.heap_info:** snapshot of current heap state; output format depends on the collector. To understand trends, sample continuously or use telemetry.
- **jstat -gcutil:** samples every 1 second, 30 times. Occupancy percentage columns and GC counts/times depend on collector/JDK; total GC time must be computed as a delta across the measurement window, not by using cumulative startup totals as a short-window ratio.
- **Warning:** jcmd and jstat provide different slices of information; never use results from another PID or from after a restart to explain a pre-restart incident.

### 3.2. Timestamped GC logs to align with latency

Enable Unified JVM Logging from application startup, if deployment policies allow:

~~~bash
java -Xlog:help
java '-Xlog:gc*,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M' -jar app.jar
~~~

This is an example of **log collection**, not a heap size recommendation. Ensure valid write paths, proper rotation/disk capacity, log access controls, and check observation overhead. If the service is already running, evaluate dynamic logging configuration via JVM-supported commands and operational policy; do not restart production just to test a flag without a safe plan.

Read GC logs along these axes:

1. **When:** do pause/GC cycle timestamps coincide with rising p99 or timeouts?
2. **What:** young/mixed/full GC, safepoints, concurrent marking, and the cause recorded by the collector.
3. **How long/how often:** pause distribution (p95/p99/max), GCs per minute, STW time fraction in the window; do not look only at the average.
4. **Memory before/after:** how much heap occupancy is reclaimed, and does it rise at the same load level? "After" figures depend on event type.
5. **Pressure:** are there Full GCs, to-space exhausted/evacuation failures, allocation failures, humongous allocations, or collector-reported anomalies? Interpret only after confirming collector and JDK.

GC can run concurrently and use CPU without large pauses. Therefore, summing pause times alone does not capture total GC cost. Conversely, long latency can come from safepoints, locks, I/O, or the scheduler even when GC pauses are short.

### 3.3. JFR and application evidence sources

When you need to correlate allocation/GC/CPU/latency, consider Java Flight Recorder (JFR), if the environment allows:

~~~bash
jcmd "$PID" JFR.start name=heap_gc_probe settings=profile duration=5m filename=heap-gc-probe.jfr
jcmd "$PID" JFR.check
jfr summary heap-gc-probe.jfr
~~~

The summary command runs **after the file finishes writing** and where the file resides. Five minutes is only an example; pick a window representative of the problem. The profile configuration has collection overhead that should be measured/bounded, and sensitive data must be protected. Use JFR to inspect allocation hotspots, GC events, and thread/lock/I/O activity actually present in the recording; do not assume every event is enabled under every configuration.

Align JFR, APM metrics, and application logs by timestamp. For example, if request p99 jumps by 500 ms with no matching pause or GC CPU, there is insufficient basis to blame GC. If lock contention or slow database queries appear at the same timestamp, investigate those factors first.

### 3.4. Native memory and container memory

On HotSpot, Native Memory Tracking (NMT) helps inspect JVM-tracked native memory, though it usually **must be enabled at startup**; example observation configuration:

~~~text
-XX:NativeMemoryTracking=summary
~~~

Once NMT is enabled:

~~~bash
jcmd "$PID" VM.native_memory summary
~~~

NMT reports reserved/committed by category; it is not an RSS measurement, nor does it cover all allocations from external native libraries outside the JVM. Do not toggle it casually in production without weighing overhead and restart procedures.

When running on Linux cgroup v2, you can inspect the exact process/container cgroup:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
~~~

The paths above represent a standard cgroup v2 mount; locations and interfaces differ on cgroup v1/Kubernetes/hosts. Cross-check process RSS, container working set, CPU throttling, and orchestrator OOMKilled events. **Memory limits apply to many non-heap components**: metaspace, code cache, thread stacks, direct/native buffers, GC metadata, native libraries, and related overhead.

### 3.5. Heap dumps and histograms: only when the hypothesis requires them

If post-GC `used` across appropriate collection cycles keeps climbing under similar load, suspecting object retention/leaks requires data on live objects and reference paths. You can consider a histogram, JFR allocation profiling, or a heap dump with a dedicated plan. **GC.class_histogram** can cause pauses/GC; **GC.heap_dump** has high impact and often requests a Full GC unless special options are used. Heap dumps can contain tokens and user data and can fill up disks. Collect only with proper authorization, disk space, and maintenance timing; never take dumps routinely like a lightweight metric. Increasing -Xmx does not cure a leak.

## 4. From metrics to diagnosis

### 4.1. Checking the link to latency

Correlation alone does not prove causation. For each incident, build a shared timeline:

| Time marker | Application | GC/heap | CPU/OS | Assessment |
| --- | --- | --- | --- | --- |
| Before incident | Normal RPS, p99 | Baseline pauses, occupancy | Baseline RSS and CPU | Baseline |
| During incident | Clear p99/error spike | Which GC events/cycles, durations, before–after used | Throttling, OOM, I/O, locks | Do timing and magnitude match enough to explain it? |
| After incident | Does p99 recover or stay degraded | Was heap reclaimed, is live set still high? | Did resources recover? | Which causes remain plausible? |

Hypothetical example: at 10:00, p99 climbs from 90 ms to 550 ms; GC logs show only 12–24 ms pauses and no nearby Full GCs. You cannot attribute the entire 460 ms difference to those pauses; investigate the request path, contention, CPU throttling, and I/O. If ~600 ms Full GC pauses align with the p99 spikes, GC becomes a stronger hypothesis, yet you must still ask **why** the heap/collector was pushed into Full GCs.

### 4.2. Reading "heap after GC" properly

- Track occupancy after collections of comparable scope, on the same collector and load; never mix after-young-GC with after-full-GC numbers carelessly.
- If the heap trough climbs across cycles at constant load, suspect retention, unbounded cache growth, or a growing live set. You need allocation/retention evidence; expanding the heap may only postpone failure.
- If the trough is stable while peaks hit the limit during bursts and GC runs back-to-back, the hypothesis of insufficient heap headroom is worth checking after ruling out abnormal allocation bursts.
- If plenty of heap headroom remains and GC time is tiny compared to SLOs, changing -Xmx or GC lacks a solid empirical basis.
- Do not use a universal occupancy threshold like "80% means raise Xmx": that ratio depends on collector, GC phase, object distribution, load, and measurement window.

### 4.3. Distinguishing throughput, latency, and footprint

**Latency:** GC pauses or CPU contention can contribute to tail latency. Compare pause timestamps and durations against p99 while also checking non-GC causes.

**Throughput:** GC consuming significant CPU/time during steady load reduces processing capacity. Tightening pause goals can make GC run more often, lowering throughput even as individual pauses shrink.

**Footprint:** A large maximum heap can allow the JVM to retain more memory during operation, pushing containers close to memory limits. Xmx bounds the heap; it **does not** guarantee the whole process stays under the container limit.

## 5. Decision matrix: what must be observed before tuning?

| Observed signal | Additional evidence to check | Reasonable course of action |
| --- | --- | --- |
| p99 rises, GC pauses are small/uncorrelated | APM traces, threads/locks, I/O, CPU throttling, safepoints | Prioritize non-GC causes; no basis for GC tuning yet |
| Very frequent Young GCs, high allocation rate | Allocation profiling, request mix, stable live set, CPU/GC time | Cut churn/object allocations if possible; only then test headroom/GC |
| Repeating Full GCs or evacuation/allocation failures | GC logs, before–after occupancy, peak load, retained objects, container headroom | Determine temporary heap shortage vs. live set/leak; test raising heap only if budget allows |
| Long-term post-GC occupancy growth at equivalent load | Retention trend, heap histogram/dump when appropriate, cache policy | Investigate leak/long-retained objects; raising heap is not the root fix |
| Container OOMKilled while heap is not full | RSS/working set, native/direct/metaspace, threads, cgroup events | Investigate native/limits; raising Xmx may worsen it |
| GC pauses proven to drive tail latency | Pause histogram, SLO, GC CPU, throughput, collector/JDK | Test pause goal/collector in a controlled experiment with guardrails |
| Healthy app, infrequent GC, ample memory headroom | SLO and stable baseline | Leave unchanged; avoid tuning just because "heap feels unoptimized" |

**Diagnose before changing parameters:** prove where the bottleneck sits. No single parameter guarantees low p99, high throughput, and small footprint for every workload.

## 6. Choosing an intervention hypothesis and understanding trade-offs

### 6.1. When to test changing -Xmx?

Sound rationale: GC pressure stems from insufficient temporary working space **after understanding live set and allocation rate**, and the memory budget genuinely permits it. Before proposing a new Xmx, record:

- Current max/committed/used heap, peak usage under peak load, post-GC trough, allocation rate, count/duration of Full GCs, and collector signals of tight headroom.
- Memory limit / host capacity, peak RSS/native/non-heap, margin for thread stacks/direct buffers/code cache/metaspace, variance with load, and other processes.
- Expected impact on GC frequency, pause duration, container OOM risk, and replica count.

A preliminary budget check is: **candidate Xmx + peak possible non-heap/native + safety margin must stay below available RAM limit**. This is a prerequisite for testing, not an automatic heap-sizing formula. Never subtract current RSS from the memory limit and give the entire remainder to the heap: current RSS already includes resident heap, and many native regions grow with load.

### 6.2. When to test changing -Xms?

-Xms is initial heap; -Xmx is maximum heap. Consider -Xms only when observing that heap expansion/shrinking or warm-up causes significant instability; measure startup time, RSS/committed, and the environment's RAM budget. Setting -Xms equal to -Xmx can fit some steady services yet commits more memory up front, and is not a universal rule.

### 6.3. -XX:MaxRAMPercentage and container limits

If -Xmx is not set explicitly, HotSpot may choose max heap from JVM-detected RAM and percentage flags such as -XX:MaxRAMPercentage. Compare **the actual max heap value** in the process against the cgroup/container limit. Do not treat -Xmx and MaxRAMPercentage as two independent heap ceilings that add together. Raising the heap ratio without leaving headroom for native memory can trigger OOMKilled.

### 6.4. Pause goals and GC selection

With G1, -XX:MaxGCPauseMillis is a **soft goal**, not a guarantee that pauses always stay below the set value. Tightening the goal can cause more frequent GCs, higher CPU, or lower throughput. When evaluating, compare **application p99 + GC pause histogram + GC CPU + throughput + RSS**, not just one pause chart.

Switching collectors (for example, latency-oriented collectors if supported by JDK/vendor) is a major change: validate compatibility, CPU/memory cost, behavior under workload, and operational settings. With G1, avoid locking young generation size via -Xmn or NewRatio merely for "fewer GCs" without evidence; G1 adjusts young generation size to pursue its pause goal. Advanced flags such as IHOP, region size, or thread counts should only be considered when concrete GC data points to that bottleneck and tests prove improvement.

## 7. Designing a controlled experiment before rollout

Each test is a measurable hypothesis, for example: "With the same request mix at 800 RPS, raising max heap from 2 GiB to 2.5 GiB will eliminate Full GCs causing p99 spikes while peak RSS stays within budget." Numbers here are **illustrative only**, not configuration recommendations.

1. **Save the baseline:** revision/build, Java version, GC, all relevant JVM flags, CPU/memory limits, replica count, load, warm-up time, and steady-state window; archive GC logs/JFR/metrics with matching timestamps.
2. **Change one primary variable:** e.g., only -Xmx; avoid changing GC, replicas, CPU limits, cache policy, or request mix simultaneously so results remain attributable.
3. **Generate comparable load:** identical concurrency, request mix, payloads, peaks/bursts, and warm-up; repeat enough times to filter noise. For production A/B, control traffic split and instance differences.
4. **Measure identical windows and units:** p50/p95/p99, throughput, errors, GC count/p95/p99/max pauses, total pause time, GC/total CPU, allocation rate, peak/after-GC heap, process/container RSS, throttling, and OOM events.
5. **Define guardrails upfront:** do not trade away SLOs or spike OOM risk; prepare a fast rollback to baseline config if p99, error rate, CPU/RSS, or stability degrades.
6. **Conclude from distributions and repeatability:** differences must be substantial, consistent, and meaningful for application goals. Better GC indicators without p99/throughput improvement may not justify the change.

Sample decision record table:

| Field | Baseline | Candidate | Acceptance criteria |
| --- | --- | --- | --- |
| JDK / collector / flags | Record actual values | Record exactly one primary change | Equivalent environment |
| Load and window | RPS, request mix, duration | Same workload | Load variance within chosen threshold |
| p99 / errors | Baseline reading | New reading | Meets SLO, zero regression |
| GC pause and CPU | Histogram, total pause, GC CPU | Same calculation | Improvement aligned with hypothesis |
| Heap after-GC and RSS | Trend/peak | Trend/peak | Does not push process/container toward OOM |
| Decision | Retain baseline data | Keep / rollback | Backed by evidence, owner, and review date |

## 8. Examples of analysis with sufficient vs. insufficient evidence

### Scenario A — not yet justified to conclude "must increase heap"

A service on JDK 21/G1 has a 4 GiB memory limit and 2 GiB Xmx. At peak hours, p99 jumps from 90 ms to 550 ms; max GC pauses near the spikes are 24 ms, with no Full GCs; container working set is near its limit and CPU throttling increases. From this data there is **insufficient evidence** to increase Xmx or switch GC. Raising Xmx could heighten OOMKilled risk. Inspect traces, CPU quota/throttling, locks, and I/O, while confirming memory breakdown and timestamp correlation.

### Scenario B — grounds to run an experiment, not yet enough to roll out directly

Another service sees long Full GCs coinciding with p99 spikes, and GC logs show insufficient headroom during peak bursts; after comparable collections, occupancy is broadly stable with no sign of long-term retention growth. Metrics indicate the memory limit still leaves margin for native/GC overhead if testing a larger Xmx. You can hypothesize "insufficient heap headroom at peak" and test **a single Xmx change** under controlled load. If pauses drop while RSS crowds the memory limit or throughput suffers, reject the candidate; if Full GCs disappear, p99 meets SLO, and CPU/RSS remain safe across repeated equivalent trials, then you have grounds to roll out.

### Scenario C — signs of a leak, raising heap only delays it

After every similar load wave, post-collection heap occupancy climbs higher over hours, retained object count rises, and eventually Full GC/OOME occurs. Inspect allocation/retention, cache size, reference-holding collections, thread-locals, listeners, or classloaders per the specific symptoms. Raising the heap may extend time-to-failure, yet never resolves what retains the objects.

## 9. Checklist before changing a parameter

- [ ] Symptoms, SLOs, and violation timestamps are measured; a representative baseline exists.
- [ ] JDK/vendor, collector, **active** JVM flags, CPU/memory limits, build, and workload are verified.
- [ ] GC logs/metrics share aligned timestamps with latency/errors, same timezone, covering before–during–after phases.
- [ ] Heap used/committed/max trends, post-GC occupancy, and allocation rate are available—or a plan exists to gather missing data.
- [ ] Pauses/GC CPU/throughput are correlated with the issue; locks, I/O, CPU throttling, and non-GC safepoints are checked.
- [ ] Java heap OOME, native/metaspace issues, and container OOMKilled are distinguished; RSS/memory headroom is verified.
- [ ] Retention/leaks are investigated if the heap trough climbs over time at constant load.
- [ ] Hypothesis written: **which parameter** changes, based on what observation, which metric is expected to improve, and which side effects to monitor.
- [ ] Valid comparison, guardrails, rollback plan, and evaluation owner are in place.
- [ ] If evidence is missing, state what is missing and **do not change** heap/GC merely because the system "feels short on RAM".

## 10. Practical conclusion

Treat heap size and GC flags as **testable variables** inside a system with many sources of slowness or memory exhaustion. The proper decision chain is:

**Symptom/SLO → actual configuration and limits → workload + heap + GC + OS timeline → rule out other causes → falsifiable hypothesis → A/B test with guardrails → keep or roll back.**

The strongest evidence is not "GC runs a lot" or "heap is 80% full", but rather: **data from the right time, right process, and right collector; a clear explanation of the mechanism; and a change confirmed to improve application targets without shifting risk onto CPU, native memory, or stability**.

### Official reference documentation

- Oracle JDK 21 — jcmd: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — Java launcher, JVM options, and Unified Logging: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21 — Garbage-First GC Tuning: https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-garbage-collector-tuning.html
