# 1.7 Choosing Java Diagnostic Tools by the Question to Answer and Allowable Impact

When a Java application hits an issue in a real environment, the first important question is not "should I use `jstack`, `jmap`, or which profiler?", but **"what needs to be proven, which signal must be observed, and how much intervention can the system tolerate?"** A tool producing vast data is still the wrong choice if the data does not answer the question, misses the failure window, or makes the situation worse.

**Expected outcomes:** learners know how to turn symptoms into testable questions; choose telemetry, thread dumps, Java Flight Recorder (JFR), GC tools, heap dumps, Native Memory Tracking (NMT), or profilers in the right order; assess operational costs; and know when to stop or escalate collection.

## 1. Diagnose by Question, Not by Tool Name

A diagnostic reasoning chain has five parts:

1. **Observed symptom:** e.g., p99 latency climbs from 200 ms to 2 s; process CPU spikes; container is OOMKilled.
2. **Specific question:** "Is time spent on CPU, lock waits, I/O, or GC?"; "Is RSS growing from Java heap or native memory?"
3. **Evidence separating hypotheses:** CPU per process and thread; GC events; thread stacks at multiple timestamps; post-GC heap charts; native allocations by category.
4. **Impact budget:** how much extra CPU overhead is permitted, how much RAM/disk can be used, whether application pauses are acceptable, and whether JVM access is permitted.
5. **Decision rule:** what data supports or refutes the hypothesis and how many repeated samples are needed.

For instance, "API is slow" is not reason enough to immediately dump the heap. First determine whether the error concentrates on one endpoint, one instance, one window, or everywhere; whether requests wait on downstream; whether CPU, GC, or lock contention rose at the same time. A heap dump rarely answers a request latency question directly.

**Separate three observation layers:**

- **Outside the JVM:** latency, throughput, error rate, queue depth, CPU, RSS, I/O, network, cgroup/container limits. This is usually the first and least intrusive layer to inspect if telemetry already exists.
- **Inside the JVM over time:** heap/GC metrics, thread counts, JFR events, GC logs, sampling profilers. Useful when issues vary with load or appear transiently.
- **Point-in-time structural snapshots:** thread dumps, class histograms, heap dumps, class loader details. Useful for seeing concrete state and objects, though a single snapshot proves neither a trend nor a cause.

## 2. How to Measure "Allowable Impact"?

Impact is not just CPU percentage. A command may use little average CPU yet trigger a **safepoint/pause**, spike memory, write gigabytes of data, expose sensitive data in heap/stacks, or require permissions unavailable in production.

| Practical Budget | Collection Examples | Impacts to Account For | When to Use |
| --- | --- | --- | --- |
| **T0 — read existing telemetry only** | dashboards, traces, logs, CPU/RSS/cgroup metrics | Primarily the cost of reading external telemetry; does not actively attach to the JVM | Default starting point during an ongoing incident |
| **T1 — brief, bounded queries** | `jcmd VM.version`, `VM.flags`, `JFR.check`; `jstat -gc` with a finite sample count | Attach permissions, output size, sampling interval | Gather context and numbers before escalating |
| **T2 — controlled snapshots or time-bounded recording** | `jcmd Thread.print`, `GC.heap_info`, JFR `settings=default` for a bounded window | Thread dumps/heap info may require JVM coordination; large thread counts make dumps costlier; JFR uses CPU/RAM/disk | When T0–T1 cannot separate hypotheses |
| **T3 — detailed profiling/logging** | Short-term JFR `settings=profile`; sampling profilers; elevated tracing/logging; NMT if already enabled | Overhead depends on settings, event rate, load, and environment; logs/recordings can grow very fast | Time-boxed execution, measure impact, have a stop plan |
| **T4 — heavy or potentially disruptive collection** | `GC.class_histogram`, `GC.heap_dump`; debugger pausing at breakpoints; agents or instrumentation altering behavior | Can cause pauses, Full GC, heavy I/O and disk usage, or alter process state | Only when necessary evidence justifies the cost and safe windows/conditions exist |

This is a **practical decision scale**, not official JDK "Impact" labels. For example, `jcmd` documentation assigns `Thread.print` **Medium** impact depending on thread count; `GC.heap_info` is **Medium**; `GC.class_histogram` and `GC.heap_dump` are **High**. `JFR.start` may be listed as **Low**, yet **`profile` recordings incur higher overhead than `default`**. Always check `jcmd <pid> help <command>` and measure on realistic workloads; never assume a "low impact" command is risk-free.

Before running, specify:

- **Stop thresholds:** significant extra CPU above baseline, rising p99 or errors, emerging JVM pauses, disk filling up, service instability.
- **Collection bounds:** duration, sampling interval, recording size, output directory, retention period.
- **Reversibility:** ability to stop recordings/logging, lower frequency, and clean up artifacts per procedure; an already started heap dump may not be cleanly abortable without side effects.
- **Data scope:** heap dumps, system properties, stack traces, JFR files, and logs can contain business data, arguments, usernames, or sensitive paths.

## 3. Tool Selection Matrix by Question

| Question to Answer | Signals to Inspect | Start With | When to Escalate | Risks/Warnings |
| --- | --- | --- | --- | --- |
| **What drives rising CPU?** | Process/thread CPU, CPU time by stack, GC CPU | Existing OS metrics and traces; short JFR sampling | JFR `profile` or sampling profiler with CPU stacks when attributing to methods | `RUNNABLE` in a dump does not mean burning CPU; sampling has bias |
| **Why is p95/p99 slow (what is waiting)?** | Request traces, queue waits, socket I/O, locks, GC pauses | Tracing + metrics + JFR `default` | Sequential thread dumps, JFR `profile`, monitor/park/IO event analysis | A single thread dump does not prove "slow due to locks" |
| **Application hung/deadlocked?** | `BLOCKED` threads, lock owners, wait cycles, changes over time | Two to three appropriately spaced thread dumps; `jcmd Thread.print -l` | JFR lock events or lock-graph analysis when dumps do not suffice | Repeated dumps on a JVM with thousands of threads can cause impact |
| **Is GC causing stutters/throughput drop?** | GC frequency, pauses, post-GC live heap, allocation rate | Enabled GC metrics/logs; `jstat -gc`; JFR GC events | Bounded GC logging, detailed JFR; histogram if retention is suspected | Do not trigger `System.gc()` just to "test"; it alters the evidence |
| **Is Java heap actually leaking?** | Live set across many GC cycles, slope vs. load, retained objects | Heap metrics over time + JFR allocation/GC | `GC.class_histogram`, then heap dump and retained-path analysis when needed | Histograms/dumps have high impact; one snapshot does not prove a leak |
| **RSS/container memory rising while heap is stable?** | RSS/PSS, cgroup, direct buffers, native stacks, metaspace, code cache | OS/container metrics + JVM heap/metaspace summary | `VM.native_memory summary` and `summary.diff` if NMT is enabled | NMT does not cover every malloc in native libraries; requires startup flag |
| **Where did OOM occur?** | OOME type, stderr, GC logs, cgroup OOMKilled, heap/native sizes | Classify `Java heap space`, `Metaspace`, `Direct buffer memory`, or kernel kill | Heap dump on OOME if configured, or branch-appropriate NMT/native tools | OOMKilled can occur before the JVM can write a heap dump |
| **Metaspace/class loaders growing?** | Loaded/unloaded classes, metaspace, class loader count | `VM.metaspace basic`, class loading metrics | `VM.classloader_stats` or heap analysis when suspecting retained class loaders | Many loaded classes alone does not prove a leak |
| **Low throughput with low CPU?** | Queues, thread pool saturation, connection pools, downstream latency | App metrics/traces, pool metrics, thread dumps | Appropriate JFR socket/file/lock/park events | Do not look only at CPU and conclude the app is "idle" |
| **JVM crash/native fault?** | `hs_err_pid*.log`, core dump, exit code, OS/container events | Collect crash logs and system state | Offline/core analysis with tools matching the JDK version | Live attach tools cannot help a dead process; core dumps hold sensitive data |

**Selection principle:** use the **lowest-impact tool sufficient to distinguish hypotheses**. If time-series observation explains the failure, no heap dump is needed yet; if the question requires retention relationships, a class histogram cannot replace a heap dump's retained graph.

## 4. Understanding Strengths and Limits of Each Tool Group

### 4.1. Metrics, Logs, Distributed Traces

Metrics show **scale and trends**; tracing shows **where requests spent time**; logs record **events and error context**. Sources already deployed prior to the incident usually carry minimal extra cost to read. Always compare against a baseline with matching load and instance, noting timestamps, timezone, and units.

Do not confuse host CPU with Java process CPU; do not confuse cgroup memory limits with `-Xmx`. RSS includes many components outside the Java heap; rising heap used within a normal GC cycle is not automatically a leak. Overly verbose, synchronous, sensitive logging also carries overhead; "logging is free" is a false assumption.

### 4.2. `jcmd` and `jstat`: Quick Snapshots or Light Sampling

`jcmd` sends diagnostic commands to a running JVM; **the command list depends on JDK, vendor, JVM, and version**. Run `jcmd <pid> help` to check available commands and impact labels. `VM.version`, `VM.flags`, and `JFR.check` are typical context-gathering steps. `GC.heap_info` gives point-in-time heap info; do not treat it as a long-term growth chart.

`jstat -gc` reads GC counters at fixed intervals, useful for spotting changes in GC frequency or volume. Those numbers alone do not answer "which objects retain heap." You must interpret fields according to the specific collector and JDK version; cross-check with logs or JFR when analyzing pauses.

### 4.3. Thread Dumps: Good for "What Is Waiting?", Weak for Long-Term Trends

`jcmd <pid> Thread.print -l` prints thread stacks and lock information. Compare **multiple snapshots** taken during the actual failure window; look for threads stuck in the same place, lock owners, deadlock signs, and batches of requests waiting on the same resource. `WAITING`/`TIMED_WAITING` can be completely normal in thread pools; `RUNNABLE` can be in native I/O. Never infer the culprit from a single state or frame.

With **virtual threads** (JDK 21+), some traditional dumps/tools do not display every virtual thread as expected. Check the virtual-thread dump capabilities of that exact JDK, and prefer JFR or virtual-thread-aware commands when needed.

### 4.4. JFR and Java Mission Control (JMC)

JFR records time-stamped events (CPU, GC, allocations, locks, threads, I/O… depending on enabled events). Use `settings=default` to start with a low-overhead recording; when deeper stacks/events are needed, run `settings=profile` **for a short window**. `.jfr` recordings can be analyzed with the `jfr` CLI or the JMC GUI.

JFR uses sampling, thresholds, and event configurations: **missing events does not mean the phenomenon did not occur**. Recordings must align with the error window and exact process. Configuring heap statistics tracking, paths to GC roots, deep stacks, or every allocation can generate substantial overhead; enable only when the question truly requires it.

### 4.5. Class Histograms and Heap Dumps: Distinguishing "Many Objects" from "Who Retains Them"

`GC.class_histogram` summarizes object counts and sizes by class at measurement time. It is an orientation step when suspecting abnormal object accumulation; the JDK classifies it as **High impact**. It does not reveal which root keeps objects alive and can be skewed by transient workload.

`GC.heap_dump` produces an HPROF file to investigate retained size, dominator trees, and GC roots. It is a late-stage choice because it can introduce significant pauses and heavy I/O/disk usage; by default the command may trigger a Full GC (depending on options), altering state before capture. Files can contain passwords, tokens, and customer payloads: store, transfer, and delete per security policy. Do not dump heap just to explain a CPU spike or request timeout without signs pointing to the heap.

### 4.6. NMT and OS Tools for Native Memory

NMT is a HotSpot feature tracking memory categories managed by the JVM. To use `VM.native_memory summary`, the JVM generally must be **started from launch** with `-XX:NativeMemoryTracking=summary` (or `detail`); enabling NMT adds overhead. Set a baseline when steady and compare `summary.diff` to find growing categories: Thread, Class, Code, GC, Internal… NMT does not measure all allocations from non-JVM native libraries; pair it with OS RSS/PSS, cgroup metrics, and OS native profilers.

If `heap used` is flat while RSS rises, **do not assume a Java heap leak**. It could be direct buffers, per-thread native stacks, class metadata, JIT code cache, memory-mapped files, native allocators/libraries, or container memory accounting behavior.

### 4.7. Sampling Profilers, Debuggers, and Instrumentation

Sampling profilers (e.g., async-profiler on supported environments) can reveal CPU/alloc/lock hotspots and flame graphs, yet native/perf permissions, stack-unwinding mechanisms, sampling frequency, and JVM settings govern overhead and accuracy. Verify versions, OS/container permissions, and measure impact on a similar system before production use.

Debugger breakpoints, tracing every method call, dynamic agents/instrumentation, or wide debug logging can alter timing and behavior; on latency-sensitive systems, prefer bounded sampling and offline analysis. Never treat attaching an agent or modifying JVM flags as a "read-only" action.

## 5. Tool Selection Workflow During an Incident

**Step 1 — Narrow scope.** Record instance/pod, PID, failure timestamp, JDK/JVM version, load conditions, GC state, and CPU/RAM/disk limits. Define a testable question: "Is ≥50% of request time spent waiting on connection pool acquisition?" is a hypothesis, not a foregone conclusion.

**Step 2 — Collect T0 layer.** Compare latency, throughput, errors, CPU, RSS, heap, GC pauses, thread/queue/pool metrics, and downstream traces in the same time window. Pick the branch: CPU, wait/lock, heap/GC, native memory, or crash.

**Step 3 — Set observation budget.** Specify duration (e.g., 60 seconds), acceptable cost, pause tolerance, disk capacity, and artifact path; note the stop command for recordings. Flag whether data may be sensitive.

**Step 4 — Capture the right T1–T2 evidence.** Pick one or a few commands capable of separating hypotheses. For time-varying bugs: prefer metrics/JFR; for hangs/locks: compare multiple thread dumps; for OOM: separate heap, metaspace, native, and OOMKilled first.

**Step 5 — Read results and falsify hypotheses.** For example, low process CPU and rare GC pauses, while traces show rising DB wait time: continue investigating pool/downstream; a CPU profiler will likely not answer this question. Always record both the observation **and** the reasoning.

**Step 6 — Escalate to T3–T4 only for remaining evidence gaps.** Document "why lightweight snapshots/recordings were insufficient," projected cost, operational conditions, and file handling. If impact exceeds budget, stop, move to staging/canary, or schedule collection for a safer window.

**Step 7 — Close with verification.** Stop extra recordings/logs, archive evidence with timestamps and load conditions, compare metrics before/after collection, and restrict artifact access. A good diagnosis ends with a concrete next decision, not a pile of unexplained files.

## 6. Practical Commands on HotSpot JDK 17+ (Linux/macOS)

The examples below **illustrate tool selection and observation execution**; do not run commands blindly in production. Replace `12345` with the PID of the **exact JVM**; run as an authorized user in the same PID namespace. `jcmd` and `jfr` belong to the JDK; minimal runtime images may lack these tools. The `/tmp` path is a Linux example: use a directory with sufficient space, permissions, and approval for storing artifacts.

### 6.1. Start by Identifying the JVM and GC Counters

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.flags
jcmd 12345 help Thread.print
jcmd 12345 GC.heap_info
jstat -gc 12345 1000 5
```

`jstat` in the example takes **5 samples**, **1,000 ms** apart, then exits; this is bounded sampling. `VM.flags` and `VM.version` help interpret the collector/heap/JDK. `GC.heap_info` carries a Medium impact label, so do not invoke it rapidly just because its output is short. Exact output varies by JVM, collector, load, and timing; do not pre-assume fixed GC or heap values.

### 6.2. When Requests Hang, Compare Thread Dumps

```bash
jcmd 12345 Thread.print -l > thread-1.txt
sleep 10
jcmd 12345 Thread.print -l > thread-2.txt
```

Run only during the symptom window; the 10-second gap is illustrative—adjust to failure duration and impact. Compare held/waited locks, repeated stacks, abnormal thread counts, and request states. Do not conclude deadlock from a single `BLOCKED` thread; look for a wait cycle or equivalent evidence. With large thread counts, take fewer dumps.

### 6.3. When Timeline Evidence Is Needed, Record a Time-Bounded JFR

```bash
jcmd 12345 JFR.start name=triage settings=default duration=60s filename=/tmp/triage.jfr
jcmd 12345 JFR.check
# After the recording finishes its duration and the file has been written:
jfr summary /tmp/triage.jfr
jfr print --events jdk.CPULoad,jdk.GarbageCollection /tmp/triage.jfr
```

`settings=default` is usually the right starting point; by default JFR tracks events configured in `default.jfc`. `JFR.check` verifies the recording is active. When finer CPU stacks/allocations are needed, **after evaluating the impact budget** you may take a short recording with `settings=profile`. Verify the file exists before running `jfr summary`; if expected events are absent, inspect event settings before concluding.

### 6.4. When Native Memory Growth Is Suspected and NMT Was Enabled at Startup

```bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory baseline
# Repeat after an intentional interval/load window:
jcmd 12345 VM.native_memory summary.diff
```

`summary.diff` compares against the baseline; if the JVM reports NMT is not enabled, plan a restart with the proper tracking flag—**do not infer from empty results**. NMT does not measure all native memory in an application.

### 6.5. When Justified to Escalate to High-Impact Collection

```bash
jcmd 12345 help GC.class_histogram
jcmd 12345 help GC.heap_dump
# Run only after evaluating pauses, I/O, disk space, and sensitive data:
jcmd 12345 GC.class_histogram > histogram.txt
jcmd 12345 GC.heap_dump /secure/heap-12345.hprof
```

These commands are documented as **High impact**, not initial discovery steps. `GC.heap_dump` may request a Full GC by default; do not mechanically switch to `-all` to "reduce impact" because the captured object set and costs may differ from analysis needs. Plan HPROF disk space according to heap size and protect the file.

## 7. Three Concrete Decision Scenarios

**Scenario A — p99 increases and process CPU rises, while GC pauses are normal.**

- Question: which methods consume CPU in the app, or are waits interleaved?
- Start: correlate p99 with CPU, request traces, GC, and throughput; pick a representative instance.
- Next tool: time-bounded JFR to examine CPU samples/stacks and timeline events; suitable sampling profiler if JFR is insufficient.
- Do not rush: heap dump; there is no evidence the issue lies in object retention.
- Valid conclusion requires: aligned load window, repeated stack/hotspot samples, separating application CPU from GC/runtime/OS.

**Scenario B — container gradually nears memory limit, while post-GC heap used stays nearly flat.**

- Question: where is off-heap memory growing—JVM internals or native libraries/cgroup?
- Start: RSS/PSS, cgroup memory, heap committed/used, direct buffer metrics, thread count, metaspace.
- If NMT is on: take `VM.native_memory summary`, baseline, and diff across a load cycle. If off: use existing OS/native telemetry and plan enabling NMT on an appropriate restart.
- Do not rush: GC heap dump merely because container memory rose; HPROF does not represent all native allocations.
- Valid conclusion requires: the growing memory category over time and measurements reconciled under matching load conditions.

**Scenario C — API timeouts, low CPU, rising pending requests.**

- Question: are threads stuck on locks, connection pools, downstream network, or queues?
- Start: request traces, thread-pool/connection-pool metrics, downstream errors and latency.
- If snapshots are needed: two or three thread dumps during errors comparing owners/waiters and repeated stacks; if I/O/lock waits fluctuate rapidly, use suitable JFR events.
- Do not rush: CPU profiler for a primarily waiting problem; do not assume `WAITING` = deadlock.
- Valid conclusion requires: evidence of waiting on a specific resource, count of affected requests, and matching timing signals.

## 8. Common Interpretation Traps and Mistakes

1. **Picking tools before the question.** Collecting heap dumps, thread dumps, and profiles before thinking about what to look for creates high risk and noisy data.
2. **Treating one point in time as a trend.** Heap used, `RUNNABLE`, a class histogram, or a single CPU sample does not prove a leak, deadlock, or hotspot.
3. **Ignoring JVM differences.** Available `jcmd` commands, impacts, and virtual-thread capture depend on JDK/vendor/collector; always query `help` on the exact JVM.
4. **Confusing Java heap with process RAM.** `-Xmx` does not cap total RSS; kernel/cgroup OOMKilled differs from a JVM `OutOfMemoryError`.
5. **Ignoring measurement cost.** Thread dumps across thousands of threads, long `profile` JFRs, per-request logging, and heap dumps can distort the very latency under investigation.
6. **Omitting timestamps and context.** Missing timestamps/timezones, PID/pod, version, load type, and config-change times makes correlation difficult.
7. **Concluding from "no events seen."** Sampling, JFR thresholds, disabled events, or recordings missing the error window can all explain absence.
8. **Neglecting data security.** Heap dumps and recordings can hold sensitive data; access rights, storage paths, and retention limits must be controlled.
9. **Repeating High-impact commands for more samples.** Back-to-back histograms or heap dumps can worsen pauses/I/O and disrupt natural state.
10. **Mistaking correlation for causation.** CPU rising alongside p99 may come from a third cause; stacks, traces, or event sequences are needed to verify the mechanism.

## 9. Tool Selection Record Template

| Field | Example Entry |
| --- | --- |
| Question | "Is p99 rising due to CPU or waiting on the connection pool?" |
| Scope | Instance/pod A, verified PID, specific JDK/GC |
| Symptom window | 14:05–14:10, timezone and load/throughput |
| Existing evidence | p99, CPU, heap, GC pauses, traces, pool queue |
| Intervention budget | 60 s recording acceptable; Full GC or heap dump unacceptable |
| Chosen tools | JFR `default` for 60 s and two thread dumps if gaps remain |
| Expected result | Wait times or CPU stacks aligned with slow requests |
| Stop criteria | Errors/p99 worsen during collection, disk or resources cross threshold |
| Conclusion/action | Hypothesis supported/refuted, artifact stored properly, next step |

**Self-check question:** If you could make only **one** next measurement without causing a Full GC, which measurement best separates your top two hypotheses? Answer in terms of **question → signal → tool → impact level → draw-able conclusion**, not just a tool name.

## References

- Oracle, [`jcmd` command reference (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): syntax, options, and Impact labels of each command.
- Oracle, [Diagnostic Tools (JDK 21)](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): JFR, thread dumps, native memory, and analysis workflows.
- Oracle, [`jfr` command reference (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `summary`, `print`, and recording operations.

When applying in practice, prioritize documentation for the **exact JDK version of the target process** and local help via `jcmd <pid> help`.