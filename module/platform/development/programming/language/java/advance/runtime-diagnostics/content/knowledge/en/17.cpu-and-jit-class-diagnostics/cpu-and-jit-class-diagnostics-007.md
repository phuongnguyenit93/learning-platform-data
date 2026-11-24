# 17.7 Identifying a Full Code Cache or Abnormal Compilation Activity Before Changing Flags

## 1. Problem to Diagnose

A Java application runs fine after startup, yet hours later CPU rises, throughput drops, or p95/p99 degrades. Logs occasionally mention **CodeCache** or the compiler; operators want to immediately bump `-XX:ReservedCodeCacheSize`, compiler thread count, or JIT thresholds. Doing so can mask the root cause and introduce new native-memory or CPU pressure.

You must distinguish at least three situations:

1. **Code cache / specific code heap under pressure:** insufficient suitable space to store new compiled code; code cache full warnings, temporary pauses/halting of compilation at some stage, and performance degradation can occur.
2. **Abnormal compilation activity despite free space:** compiler queue stays backed up, compilations/failed compilations/deoptimizations rise, compiler threads burn significant CPU, and class or method churn forces the JIT to redo work.
3. **Normal warm-up or fluctuation:** JIT compiles heavily early in the lifecycle or after a load shift; queues stay short, code heaps retain free space, and performance stabilizes after warm-up. High CPU may stem from business code, GC, or native work rather than the compiler.

**Desired output:** time-series data on each code heap's state, compiler queue/compilation events, CPU, and workload; establish an evidence-based hypothesis before considering HotSpot parameter changes. This lesson uses **HotSpot JVM** terminology and tools, primarily JDK 17–24; verify actual commands on other builds/JDKs.

## 2. JIT, Compiled Code, and the Code Cache

When the JVM executes bytecode, parts of the code are initially interpreted. In HotSpot with **tiered compilation**, frequently executed code can be compiled at different optimization levels, typically involving the C1 and C2 compilers. The JVM gathers profiling, optimizes, and can **deoptimize** compiled methods when assumptions about types/classes/paths no longer hold. This process is beneficial yet requires CPU and storage for compiled code.

The **code cache** is *native executable* memory holding compiled `nmethod`s and other runtime code snippets used by the JVM. It differs from:

- **Java heap:** stores Java objects managed by GC; raising `-Xmx` does not enlarge the code cache.
- **Metaspace:** primarily holds class metadata; loading many classes can indirectly impact JIT, yet metaspace ≠ code cache.
- **Compilation queue:** list of tasks waiting for the compiler; a long queue does not automatically mean the code cache is out of space.
- **JIT compiler CPU:** effort spent generating/optimizing machine code; high compiler CPU does not prove the code cache is full.

When **segmented code cache** is enabled, HotSpot can split the area into separate code heaps:

| Code Heap | Typical Role | What to Watch |
| --- | --- | --- |
| `non-nmethods` | Interpreter/runtime stubs, adapters, and non-`nmethod` code snippets | Do not lump blindly with compiled Java methods; capacity and reclamation differ |
| `profiled nmethods` | Compiled methods in stages carrying profiling info, usually tied to tiered compilation | Pressure rises when lots of code is compiled at profiling tiers |
| `non-profiled nmethods` | Compiled methods needing no further profiling, usually including highly optimized code | Often the heap experiencing pressure in long-running applications |

**Segmented heap layouts are not always identical.** `-XX:+SegmentedCodeCache`, `-XX:ReservedCodeCacheSize`, tiered compilation, and JDK build determine how regions are organized. When segmented, the three code heaps have separate budgets; *total code cache remaining* does not guarantee the specific heap needing space still has contiguous blocks available. In non-segmented mode, a single code cache region reports differently. Never assume every app has exactly three heaps.

HotSpot runs a **code sweeper** to clean up compiled methods that are no longer used/valid. Many `nmethod`s can be invalidated, made not entrant, and later reclaimed per JVM mechanisms; reclamation is not necessarily instantaneous. Fragmentation and free-block state also matter on allocation failures, beyond a simple `used/max` ratio.

## 3. Recognizing Symptoms and Reasoning Traps

| Symptom | Hypothesis to Test | Insufficient to Conclude |
| --- | --- | --- |
| Log `CodeCache is full` / `Compiler has been disabled`, JFR `jdk.CodeCacheFull`, specific code heap near or out of space, compilation status changes | **Code cache pressure / full occurred**; can impact JIT and throughput | One old startup warning does not prove compilation is still disabled now; space may have been reclaimed/resumed |
| `Compiler.queue` backed up across multiple snapshots, compiler threads burn high CPU, many `jdk.Compilation` or compilation failures | **Compiler backlog / compilation churn**; separate legitimate warm-up tasks from sustained anomaly | One long queue snapshot does not prove cache exhaustion |
| JFR `jdk.Deoptimization` rises, same methods recompiled repeatedly | Speculation invalidation, shifting types/classes, or workload logic; can drive recompilation | A few deoptimizations are normal JVM behavior |
| Code heap near capacity yet queue empty, no full events, stable throughput/latency | Code is stored and reused; **no harm observed** | High `used/max` percentage alone is not an incident |
| High CPU, ample code heaps, sparse compilation events, execution samples in app methods | **CPU-bound business logic**, algorithms, or GC | Cannot be solved by `ReservedCodeCacheSize` |
| Code cache `used` rises after deploy, then plateaus | JIT warm-up or new traffic triggering compilation | Not a leak just because it does not drop after traffic subsides |

**Strong evidence** requires linking: errors/performance regression in the same window **and** the code heap running out of suitable capacity or `CodeCacheFull` firing, compiler/queue status shifting, and user-visible performance degrading. One counter never replaces the full causal chain.

### Recognizing When the Compiler Stops and Resumes

Some HotSpot configurations may **stop/pause the compiler when the code cache fills**, then sweep/reclaim code and resume compilation when conditions permit. Thus both "JIT was permanently disabled" and "JIT will definitely self-recover" are too strong without logs and status across different timestamps.

If the compiler can no longer emit new optimized code, un-warmed paths may keep running interpreted or in lower-tier compiled code; impact depends on workload. **Do not assume all old compiled methods were deleted** just because a compiler-disabled message appeared.

## 4. Evidence-Collection Workflow Before Tuning

### Step 1 — Lock Down Version, Workload, and Timeline

Record **Java vendor/build**, `java -version`, process/PID and CPU quota, container memory limit, uptime, deploy time, classes loaded/unloaded, requests/s, in-flight requests, p50/p95/p99, error rate, GC pauses, and process CPU. Determine the **rate of change** during the anomaly: did the code heap fill gradually over hours or spike once during warm-up? Measure matching traffic/workloads when comparing two runs.

First verify active JVM flags:

~~~bash
# Replace <PID> with the target JVM PID.
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> VM.flags -all
~~~

`VM.flags -all` is long; inspect relevant effective flags such as `ReservedCodeCacheSize`, `InitialCodeCacheSize`, `SegmentedCodeCache`, `TieredCompilation`, `CICompilerCount`, and `UseCodeCacheFlushing` on the exact JDK. Do not substitute blog defaults from a different version for runtime values.

### Step 2 — Snapshot CodeCache and Compiler Queue Properly

~~~bash
jcmd <PID> Compiler.codecache
jcmd <PID> Compiler.queue
jcmd <PID> Compiler.CodeHeap_Analytics aggregate
~~~

- `Compiler.codecache`: prints **layout, size, used, max_used, free** or equivalent code-heap statistics and compilation info depending on HotSpot build. Inspect each heap, not just one total.
- `Compiler.queue`: snapshots **methods queued** for compilation. Queue is a point-in-time snapshot; run several times spaced properly to observe progress before claiming a backlog.
- `Compiler.CodeHeap_Analytics aggregate`: adds visibility into code heap state, free-space distribution, and sweeper activity when needed. On supporting JDKs, functions include `UsedSpace`, `FreeSpace`, `MethodCount`. The command may hold `CodeCache_lock` while analyzing, so choose timing and detail level carefully.
- `Compiler.codelist` (optional) prints currently live compiled methods, useful when comparing methods accumulating in the code cache; output can be huge with higher impact than normal `codecache`.

Use `jcmd <PID> help` and `jcmd <PID> help Compiler.CodeHeap_Analytics` to confirm supported commands and impact levels on the actual JVM. Save **multiple snapshots** (e.g., normal baseline, right before throughput drops, during the incident, after recovery); record timestamp and load with each snapshot. Never run it just once after the incident is over.

### Step 3 — Combine with JFR to See Progression Over Time

You can start a bounded recording on a running JVM:

~~~bash
jcmd <PID> JFR.start name=jit-triage settings=profile duration=60s filename=jit-triage.jfr
# After the recording finishes:
jfr summary jit-triage.jfr
jfr print --events jdk.CodeCacheFull,jdk.CodeCacheStatistics,jdk.Compilation,jdk.CompilationFailure,jdk.CompilerStatistics,jdk.Deoptimization jit-triage.jfr
~~~

**Interpret events, not just event names:**

| Event | What to Ask | Notes |
| --- | --- | --- |
| `jdk.CodeCacheFull` | Did a code heap report full, and which heap? | Event may be rare and setting-dependent; absence does not rule out an incident prior to the recording |
| `jdk.CodeCacheStatistics` | How did code heap capacities/usage change over the recording? | Event frequency and fields vary by JDK/settings |
| `jdk.Compilation` | Which compilation attempts occurred, their durations, compilers/tiers, and methods? | Heavy compilation right at warm-up is not yet abnormal |
| `jdk.CompilationFailure` | Were there failed compilations and specific reasons? | Failures can stem from optimizer limits or complex methods, not automatically a full cache |
| `jdk.CompilerStatistics` | What compiler activity stats appear? | Use trends and context; may not be enabled in every template |
| `jdk.Deoptimization` | Was compiled code deoptimized, and for what reason? | Deopts can be normal when speculation is invalidated |

`jfr summary` reports **actual recorded event counts**. If an event type is absent from the file, check the recording's **enabled/period/threshold settings**; many events fire only under special conditions. Never conclude "never fills" from 60 seconds without `CodeCacheFull`. Open the `.jfr` in **JDK Mission Control** to align CPU timelines, compiler events, code cache metrics, GC, class loading, JIT/deoptimization, and latency spikes. JMC page names depend on version.

### Step 4 — Measure Compiler CPU and Other Branches

The C1/C2 compilers run on compiler threads and can consume substantial CPU during warm-up or compilation churn. Use OS process/thread CPU, JFR `ThreadCPULoad`/Compiler events, or a CPU profiler **that covers JVM native/compiler threads**. `jdk.ExecutionSample` primarily observes executing Java code and does not reliably show full CPU of native compiler threads.

Compare alongside compilation counts, queue, and `codecache used/free`:

- Process CPU rises **alongside a persistent compiler queue and long compilation events** → grounds to investigate compiler backlog.
- CPU rises while queue is empty, class loading is steady, and code cache has plenty of room → profile business methods, GC, and native work.
- Code heap space drops to exhaustion, full events/logs fire, and then new compilations drop or compiler status shifts → grounds to investigate code cache.

### Step 5 — Compare Before/After Changing One Variable

Do not change `ReservedCodeCacheSize`, `CICompilerCount`, `TieredCompilation`, and `CompileThreshold` all at once. To test a hypothesis, pick one trial setting on staging, keep workload/container/JDK consistent, and re-measure:

- Code heap utilization, free blocks, `CodeCacheFull` count, and compilation status;
- Compiler queue, compilation/deoptimization/failure rates;
- Process/compiler CPU, throughput, p95/p99, errors;
- Native memory/container headroom and warm-up duration.

The goal is to prove **the exact bottleneck shifted** and user-facing performance improved, not merely to make warnings disappear.

## 5. Decision Tree: Where Is the Bottleneck?

~~~text
Poor CPU/p99 or JIT warnings present
             |
             v
  Check JVM flags + per-heap CodeCache + logs/JFR
             |
     CodeCacheFull/full log aligned with failure time?
        /                              \
      Yes                              No / unclear
      |                                  |
      v                                  v
  Check which heap,              Compiler.queue growing
  free blocks, sweeper,          across multiple snapshots?
  compile status                         /       \
      |                                Yes        No
      v                                 |          |
  Confirm impact                        v          v
  + code cache pressure           JFR Compilation/   CPU samples,
      |                            Failure/Deopt,     GC, I/O, class
      v                            compiler CPU       load/workload
  Find cause of code                  |                |
  accumulation, fragmentation,        v                v
  class/method churn;              Compilation churn  Likely not
  consider QA'd tuning             or warm-up?        code cache
~~~

This tree is **not a rigid binary test**. You can have both code cache pressure and compiler churn simultaneously; an empty queue in the current snapshot does not prove there was no earlier backlog. Prioritize timestamp correlation and controlled experiments.

## 6. Illustrative Diagnostic Scenarios

### Scenario A — A Specific Code Heap Runs Out of Space

After deploy, the system generates many JIT-compiled methods. At `t1`, logs emit `CodeCache is full`, JFR records `jdk.CodeCacheFull` in the same window, `Compiler.codecache` shows **one specific code heap** nearly out of `free`, the compiler temporarily disables and then resumes (or stays disabled), and p99 rises alongside that phase. This is a strong evidence set for **code cache pressure**.

Investigate next: which code heap; after which class loading or code generation it grew; whether the sweeper reclaims code; whether fragmentation/free blocks are an issue; and whether workload transitioned from warm-up to new code paths. If code genuinely stays live because many hot methods exist, raising capacity can help **after measuring**. If code churn comes from a classloader leak, dynamic proxies, or unbounded class generation, raising capacity only delays the next full event.

### Scenario B — Long Queue Yet Plenty of Cache Space

A new burst hits many uncompiled methods. `Compiler.queue` grows across several snapshots; OS metrics show high compiler CPU and JFR `jdk.Compilation` rises, while heaps retain substantial headroom with no matching `CodeCacheFull`. This may be **legitimate warm-up** or compiler capacity/workload churn, not cache exhaustion.

If the queue drains on its own, latency returns to baseline, and compilation rate drops, warm-up is likely. If the same paths repeatedly burn compilation CPU, check class churn, deoptimization reasons, generated code, classloaders, and Compiler failures. Raising `ReservedCodeCacheSize` will not help code that **cannot compile fast enough**.

### Scenario C — Repeated Deoptimization and Recompilation

A service frequently alters class shapes, executes dynamic invocations, or passes varying object types through the same sites. JFR shows repeated deoptimizations and compilations on the corresponding methods/branches, compiler CPU is high, and throughput drops, while the code cache is not full. Hypothesize **unstable profiling/speculation or class/method churn**; confirm with traces and input/load changes.

Deoptimization is not always a bug: HotSpot conservatively adjusts optimized code when assumptions break. Treat it as abnormal only when frequency/recompilation counts are substantial, correlate with a performance regression, and map to identifiable code paths.

### Scenario D — High CPU Unrelated to JIT

The process nearly hits its CPU quota, `Compiler.queue` is mostly empty, compiled code is stable, JFR `jdk.ExecutionSample` clusters in serialization/crypto loops, and no codecache-full evidence exists. The likely cause is a **CPU-bound workload**. Investigate algorithms, data, and parallelism before touching JIT flags.

### Scenario E — High Code Cache Usage Yet Healthy System

After warm-up, code cache occupancy is high and remains steady for hours; there are no full events/logs, compiler status is enabled, and p99 and throughput are healthy. High occupancy **is not a standalone incident**. Monitor trends and headroom; do not change `ReservedCodeCacheSize` merely because of an arbitrary percentage threshold.

## 7. Java 17+ Lab: Observing CodeHeap and Compiler Time

This lab uses the **Java Management API** to read memory pools named `CodeHeap` or `Code Cache` plus `CompilationMXBean`. It intentionally executes code to give the JIT a chance to warm up, then prints several snapshots. The goal is **identification and measurement**, not forcing Code Cache exhaustion. Results vary by vendor/JDK, CPU, tiered compilation, and environment.

Create **`JitCodeCacheProbe.java`**:

~~~java
import java.lang.management.CompilationMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.util.Locale;

public final class JitCodeCacheProbe {
    private static volatile long sink;

    private static long mix(long n) {
        for (int i = 0; i < 100; i++) {
            n ^= n << 13;
            n ^= n >>> 7;
            n ^= n << 17;
        }
        return n;
    }

    private static void workload() {
        long value = 0;
        for (int i = 0; i < 250_000; i++) {
            value ^= mix(i + 1L);
        }
        sink = value;
    }

    private static void snapshot(String label) {
        CompilationMXBean compiler =
                ManagementFactory.getCompilationMXBean();
        long compileMs = -1;
        if (compiler != null
                && compiler.isCompilationTimeMonitoringSupported()) {
            compileMs = compiler.getTotalCompilationTime();
        }
        System.out.printf(Locale.ROOT,
                "phase=%s totalCompilationTimeMs=%d%n",
                label, compileMs);

        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            String name = pool.getName();
            String normalized = name.toLowerCase(Locale.ROOT);
            if (!normalized.contains("codeheap")
                    && !normalized.contains("code cache")) {
                continue;
            }
            MemoryUsage usage = pool.getUsage();
            if (usage == null) {
                continue;
            }
            System.out.printf(Locale.ROOT,
                    "pool=%s usedKiB=%d committedKiB=%d maxKiB=%d%n",
                    name, usage.getUsed() / 1024,
                    usage.getCommitted() / 1024,
                    usage.getMax() / 1024);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 1
                || (args.length == 1 && !args[0].equals("--inspect"))) {
            System.out.println("Usage: java JitCodeCacheProbe [--inspect]");
            return;
        }

        System.out.println("pid=" + ProcessHandle.current().pid());
        snapshot("start");

        for (int batch = 1; batch <= 4; batch++) {
            workload();
            snapshot("batch" + batch);
        }

        if (args.length == 1) {
            System.out.println("inspectionWindowSeconds=20");
            Thread.sleep(20_000);
        }
        System.out.println("checksum=" + sink);
    }
}
~~~

Compile and run:

~~~bash
javac JitCodeCacheProbe.java
java JitCodeCacheProbe
~~~

**Output format** (values and pool names vary; no fixed literal stdout):

~~~text
pid=<PID>
phase=start totalCompilationTimeMs=<number or -1>
pool=CodeHeap 'non-nmethods' usedKiB=<...> committedKiB=<...> maxKiB=<...>
pool=CodeHeap 'profiled nmethods' usedKiB=<...> committedKiB=<...> maxKiB=<...>
pool=CodeHeap 'non-profiled nmethods' usedKiB=<...> committedKiB=<...> maxKiB=<...>
phase=batch1 totalCompilationTimeMs=<...>
...
phase=batch4 totalCompilationTimeMs=<...>
...
checksum=<integer value>
~~~

**Reading the metrics:**

- `pool` names are real runtime names; non-segmented environments may show `Code Cache` instead of three `CodeHeap`s.
- `usedKiB` is the space currently used as reported by the MXBean for that code memory pool; `committedKiB` and `maxKiB` have different meanings. `maxKiB=-1` is a valid API value when max is undefined; do not interpret it as a negative code cache.
- `totalCompilationTimeMs` is a **cumulative** compiler time counter from `CompilationMXBean` when supported; `-1` means unsupported. It is **not batch duration**, not compile time specifically for `mix`, and cannot by itself measure CPU saturation.
- One or more pools rising in `used` after warm-up is normal. The lab does not have enough methods to guarantee filling the code cache or triggering `jdk.CodeCacheFull`; seeing no warnings is expected.

To inspect with `jcmd`, run this in the first terminal:

~~~bash
java JitCodeCacheProbe --inspect
~~~

When the program prints `inspectionWindowSeconds=20`, open a second terminal and replace `<PID>` with the printed PID:

~~~bash
jcmd <PID> Compiler.codecache
jcmd <PID> Compiler.queue
jcmd <PID> Compiler.CodeHeap_Analytics aggregate
~~~

**Lab note:** the program only holds a 20-second window for attaching, and does not intentionally force cache exhaustion. To investigate a real incident, run these commands against **the target application's PID** while also collecting JFR/CPU/throughput over the same period.

You can capture a JFR recording while running the example:

~~~bash
java -XX:StartFlightRecording=filename=jit-probe.jfr,settings=profile,dumponexit=true JitCodeCacheProbe
jfr summary jit-probe.jfr
jfr print --events jdk.CodeCacheFull,jdk.CodeCacheStatistics,jdk.Compilation,jdk.CompilationFailure jit-probe.jfr
~~~

`jit-probe.jfr` is written when the program exits. A normal recording may have **no** `CodeCacheFull` or `CompilationFailure` events; that is expected in this lab. `CodeCacheStatistics`/`Compilation` events depend on recording settings. For controlled JFR experiments, tune recording profiles on staging; never try to force CodeCache exhaustion in production.

## 8. When Should You Consider Changing Flags?

After diagnosing, separate **capacity tuning** from **compiler-behavior tuning**:

| Confirmed Condition | Priority Action | Flags Considered Only After Measuring |
| --- | --- | --- |
| Specific code heap genuinely exhausted, with warnings/events and performance impact | Inspect code churn, sweeper, fragmentation, compiled method count, and segmented layout | `-XX:ReservedCodeCacheSize=<size>`; if segmented, evaluate compatible `NonNMethodCodeHeapSize`, `ProfiledCodeHeapSize`, `NonProfiledCodeHeapSize` budgets |
| Compiler backlog from sudden compilation surge | Inspect warm-up, code generation, dynamic proxies, class churn, compilation failures | `CICompilerCount`/tier strategy only after profiler proves compiler CPU/queue is the bottleneck |
| Abnormal recompile/deopt | Find why types/classes, code paths, or builds/dependencies changed | Do not rush to force `CompileThreshold` or disable tiered JIT; flags alter startup/steady-state and mask bugs |
| High code cache without full/stalls | Monitor capacity and trend; no user impact | No flag change needed |
| CPU-bound business code, GC, I/O | Optimize the right layer and add CPU/downstream capacity if needed | CodeCache tuning misses the root cause |

**Do not treat documentation defaults as runtime values.** `ReservedCodeCacheSize` depends on JDK, tiered compilation choice, and current configuration; `SegmentedCodeCache` may be on or off. Parameters changing code cache structure typically require startup flags and a restart. Larger capacities cost virtual/native memory and can push the process toward container limits; inspect memory headroom.

**Do not try to "fix" issues by disabling code-cache flushing** (`UseCodeCacheFlushing`), disabling JIT/tiered compilation, or arbitrarily raising compiler threads. Turning off flushing can make code cache pressure harder to recover from; disabling tiered changes compilation/throughput characteristics. Such changes require dedicated tests and a rollback plan, never as a first diagnostic step.

### Evidence-Backed Flag Experiment Plan

1. Keep **JDK/build, CPU quota, traffic, data, class-loading pattern, and GC settings** identical between baseline and candidate.
2. Change only **one** flag tied to the identified cause, recording effective flags via `VM.flags -all`.
3. Run from cold start through warm-up to steady state; measure both warm-up time and long-term throughput/p95/p99.
4. Compare JFR `CodeCacheFull`, code heaps, compiler queue/CPU, compilation failures/deoptimizations, GC, and memory footprint.
5. Accept the change only when it resolves the cause without degrading latency, CPU, or memory limits; prepare a rollback path if different traffic reproduces the issue.

## 9. Common Interpretation Errors

1. **"Code cache 90% used means it's full."** False: allocations may still succeed normally; inspect specific heaps, free blocks, logs/events, and real impact.
2. **"Full code cache means Java heap is out of memory."** False: code cache is native executable memory, distinct from `-Xmx`; metaspace is also distinct.
3. **"Increasing `ReservedCodeCacheSize` fixes all JIT errors."** False: CPU-bound compiler queues, repeated deoptimization, and generated-code churn do not vanish on their own.
4. **"An empty `Compiler.queue` proves there is no issue."** False: it is a snapshot; the compiler may have temporarily disabled or a backlog may have just passed.
5. **"One compilation failure means the compiler is broken."** False: JIT may bail out of an optimization or fall back, depending on reason and execution outcome.
6. **"Many compilations are abnormal."** False: warm-up, loading classes, and fresh profiles triggering JIT work are by design.
7. **"Every deoptimization is a regression."** False: speculative optimization requires deopt when assumptions break; evaluate frequency and cost.
8. **"Once a full event occurs, JIT stays off forever."** False: status can recover after sweeping/flushing; track compiler status over time.
9. **"NMT Code committed tells you the code heap has enough contiguous free blocks."** False: NMT tracks VM memory categories, not replacing `Compiler.codecache`/heap analytics.
10. **"High CPU must be the C2 compiler."** False: profile application code, GC, native code, and compiler threads using the right event types.
11. **"A JFR recording without `CodeCacheFull` means it never filled."** False: recordings have time windows and event settings; absence in one window does not rule out earlier events.
12. **"More compiler threads always run faster."** False: compiler workers compete with request threads for CPU and can worsen tail latency.

## 10. Incident Checklist Before Changing JVM Flags

- [ ] Recorded JDK vendor/build, `VM.command_line`, `VM.flags -all`, CPU/memory quota, and deploy time.
- [ ] Collected throughput, p50/p95/p99, errors, process CPU, compiler-thread CPU, GC, and class-load trends **over the same time window**.
- [ ] Captured multiple `Compiler.codecache` snapshots per heap; know exactly which heap has/lacks space.
- [ ] Captured multiple `Compiler.queue` snapshots and know whether the queue is draining.
- [ ] Checked logs/JFR `jdk.CodeCacheFull`, `jdk.CodeCacheStatistics`, `jdk.Compilation`, `jdk.CompilationFailure`, `jdk.Deoptimization` per actual recording settings.
- [ ] Distinguished legitimate warm-up, code cache pressure, compiler backlog, compilation churn, and unrelated CPU/GC/I/O.
- [ ] Considered `Compiler.CodeHeap_Analytics` when suspecting fragmentation/sweeper/code pressure.
- [ ] If suspecting full code cache, confirmed impact on compilation status or latency/throughput, not just `% used`.
- [ ] When tuning a flag, planned **one hypothesis → one variable → verification measurement → rollback**.
- [ ] Conclusion report documents observations, confidence level, and unverified points.

### Version-Specific Official Documentation

- Oracle JDK 21 — Java launcher / Advanced JIT Compiler Options and Code Heap State Analytics: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21 — `jcmd`, `Compiler.codecache`, `Compiler.queue`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — JFR and diagnostic tools: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JFR Event Reference/JMC events (`CodeCacheFull`, `Compilation`, `CompilationFailure`): https://docs.oracle.com/en/java/java-components/jdk-mission-control/8/jmc-flightrecorder/constant-values.html

**Conclusion criterion:** before increasing code cache size or altering JIT flags, you must be able to answer **which exact heap ran short of capacity, what the compiler was doing, whether those events coincided with performance degradation, and which bottleneck the planned change addresses**.
