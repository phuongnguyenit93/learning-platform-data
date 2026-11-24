# 11.4 Reading GC logs according to the active collector instead of forcing a fixed memory-region model

## 1. Problem to solve

A GC log is a journal of the JVM's garbage collection activities: timestamps, causes, processing phases, application pause durations, and memory statistics. **The same word "GC" does not carry the same meaning across all garbage collectors.** Reading logs properly starts with confirming the running JVM/JDK and collector, and only then using that collector's terminology, states, and limits to interpret the log.

You should not assume every JVM heap consists of three fixed physical regions "Eden → Survivor → Old", and infer from there that every GC event is either a "minor GC" or a "full GC". That model is helpful as an introduction to traditional generational collectors, but:

- **Serial/Parallel** manage young/old according to their algorithms and generally perform collections in *stop-the-world* (STW) intervals.
- **G1** still has young/old concepts, but the heap is partitioned into many **regions**; eden, survivor, and old roles can be assigned to different regions over time. It uses young collections, mixed collections, and concurrent marking.
- **ZGC** puts most of its work into concurrent phases. With **JDK 21**, distinguish single-generation ZGC (when only `-XX:+UseZGC` is enabled) from **Generational ZGC** (when `-XX:+ZGenerational` is also enabled).
- **Shenandoah in JDK 21** is a concurrent collector that is not generational in the traditional young/old sense; availability depends on the JDK distribution and platform.

> Scope: primarily HotSpot/JDK 17–21, using JDK 21 as the reference point for ZGC options. Phase names, tags, line structures, and supported flags can change across JDK releases, vendors, and collector modes. Always verify against the actual version rather than inferring from illustrative examples.

### After this lesson, the reader will be able to

1. Confirm which collector and JVM configuration produced a GC log.
2. Distinguish **GC pause**, **concurrent phase**, **GC cycle**, and **heap occupancy**.
3. Read characteristic events of Serial/Parallel, G1, ZGC, and Shenandoah without forcing all of them into a single region diagram.
4. Assess signals of allocation pressure, live object volume, Full/degenerated GC, allocation stalls, and correlation with application latency.
5. Formulate testable hypotheses using logs alongside JVM/OS metrics, rather than concluding a memory leak from a single GC line.

## 2. Establish context **before** analyzing a line

### 2.1. Java version, collector, and heap parameters

When you have access to a running JVM, use the following commands (replace `12345` with the real PID):

```bash
java -version
jcmd -l
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
jcmd 12345 VM.log list
```

- `java -version` describes the JDK invoked in the current terminal; **it may differ** from the JDK of the process under investigation.
- `VM.command_line` shows the process launch command, including `-XX:+Use...GC` options if passed.
- `VM.flags` shows the JVM flag states on that process, including options chosen automatically by the JVM. Commands and output depend on the JDK; cross-check the GC initialization line in the log.
- `GC.heap_info` is a snapshot of heap structure/statistics supported by the JVM at invocation time, not a full history.
- `VM.log list` helps inspect the active Unified Logging configuration. `jcmd` requires appropriate attach permissions and a JDK containing this tool.

Startup logs typically contain a line like `[info][gc] Using G1`, `Using Parallel`, `Using Serial`, `Using ZGC`, or `Using Shenandoah`. **Do not identify the collector merely by seeing the words "young", "old", or "heap" appear casually in a line.**

Illustrative choices for **JDK 21**:

| Collector/mode | Typical selection flags | How to understand heap and GC cadence |
| --- | --- | --- |
| Serial | `-XX:+UseSerialGC` | Young/old; collection work is primarily STW and sequential |
| Parallel | `-XX:+UseParallelGC` | Young/old; STW collection with multiple GC workers; prioritizes throughput |
| G1 | `-XX:+UseG1GC` | Young/old are roles of regions; young/mixed pauses and concurrent marking |
| Single-generation ZGC (JDK 21) | `-XX:+UseZGC` | Does not impose a traditional Eden/Survivor/Old diagram; many concurrent phases |
| Generational ZGC (JDK 21) | `-XX:+UseZGC -XX:+ZGenerational` | Distinguishes young/old generation collections per ZGC's algorithm; still includes concurrent work |
| Shenandoah (JDK 21) | `-XX:+UseShenandoahGC` | Concurrent marking/evacuation/update references; no default young/old split |

G1 is a common default on HotSpot JDK 21, though the actual choice can depend on environment, machine size, JDK build, or startup flags. In particular, **do not assume a newer JDK's ZGC default applies to JDK 21**; confirm `ZGenerational` from configuration when analyzing logs.

### 2.2. Enabling targeted Unified Logging

Example of running an application that writes GC and safepoint events to a file; can be entered as a single terminal command:

```bash
java -Xms256m -Xmx256m -Xlog:gc*,safepoint=info:file=gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=20m -jar app.jar
```

Meaning:

- `gc*` matches tag groups containing `gc`; default level is `info`. `safepoint=info` adds safepoint information. Tags like `gc,heap` or `gc,phases` appear only when the JVM emits logs for the corresponding tag/level.
- `time,uptime,level,tags` are accompanying metadata (*decorators*); `uptime` is convenient for reconstructing ordering, and `time` is convenient when aligning with APM/request logs.
- `%p` is PID and `%t` is the JVM start timestamp in the filename, helping prevent logs from multiple processes from mixing.
- `filecount=5,filesize=20m` configures file rotation; ensure enough retention to cover the incident window. Size numbers are approximate targets.
- `-Xms`/`-Xmx` in the example are experimental parameters; use values appropriate for the real application. Max heap is not synonymous with RSS/container memory limit.

When needing to inspect why region sizes or phase durations were chosen, you can selectively increase detail:

```bash
java -Xlog:gc*=info,gc+heap=debug,gc+ergo=debug:file=gc-detail.log:time,uptime,level,tags:filecount=5,filesize=20m -jar app.jar
```

`-Xlog:help` lists the levels and tags supported by **the JDK in use**. `debug`/`trace` levels make logs larger and can increase overhead; enable only enough to answer specific questions. Typically `-Xlog:gc` is an initial survey level, and `-Xlog:gc*` provides broader context. For an already-running application, you can inspect/adjust log configuration via `jcmd ... VM.log` when permissions and version allow.

## 3. Decoding syntax without jumping to conclusions

**Synthesized shape example** of a G1 line (numbers are invented to explain syntax, not guaranteed output of the program below):

```text
[2026-10-29T10:30:00.000+0700][12.345s][info][gc] GC(12) Pause Young (Normal) (G1 Evacuation Pause) 120M->48M(256M) 6.700ms
```

| Component | How to read it | What must NOT be inferred |
| --- | --- | --- |
| `2026-...` | Wall-clock time according to the JVM/machine clock | That every service's clock is strictly synchronized |
| `12.345s` | JVM uptime at the event | That the application has been serving requests for that exact duration |
| `info`, `gc` | Log level and tag set | That all phases/causes are recorded at this level |
| `GC(12)` | ID linking records belonging to a GC event/cycle | That it is a request ID, thread ID, or "12 Full GCs" |
| `Pause Young ...` | Event name under **G1**; involves an STW interval | That seeing `Young` means every collector has a fixed physical Eden |
| `120M->48M(256M)` | Heap used before → after; heap capacity shown in this line's context | That RSS dropped by exactly 72 MB, or that `256M` is necessarily `-Xmx` |
| `6.700ms` | Reported duration for the pause event | The entire concurrent cycle, or 100% of request interruption time |

Lines tagged `[gc,heap]` and `[gc,phases]` with the same `GC(12)` can add phases and region changes. Read **the entire event group**, rather than concluding from a single `before->after` number.

Distinguish four concepts:

- **STW pause:** the application must stop during a GC phase; directly impacts latency, though the impact on an individual request depends on request timing.
- **Concurrent phase:** GC and the application can run simultaneously; phase duration can be many times longer than a pause. This still incurs CPU/memory-bandwidth cost, but **does not mean the application was stopped for that entire duration**.
- **GC cycle:** a sequence of phases/collections related to a unit of work. On concurrent collectors, a cycle can contain multiple concurrent segments and pauses; on G1 there are also multiple young/mixed collections around concurrent marking.
- **Live set / post-GC occupancy:** the amount of heap retained after collection. This is only a signal of live objects, not proof of a memory leak on its own. Buffers, caches, class metadata, direct buffers, and native memory have separate lifecycles.

## 4. Reading by active collector

### 4.1. Serial and Parallel: generational with STW at the core

For Serial/Parallel, you typically observe:

- **Young GC:** attempts to reclaim memory holding many short-lived objects. A cause like `Allocation Failure` can simply be the normal trigger for a young collection, **not automatically an allocation error or an imminent `OutOfMemoryError`**.
- **Full GC / Old collection:** usually more expensive, potentially linked to old-memory pressure, ergonomics, explicit GC, or other conditions. Read **cause** and before/after heap for context.
- **Promotion and survivor:** objects surviving young GCs may move to survivor/old; if post-GC old usage keeps climbing, investigate retention and allocation rate.
- **Parallel GC uses multiple workers**, yet regular collection phases remain STW. "Parallel" does not mean "concurrent with the application".

Illustrative log shape (exact names and numbers depend on JDK version):

```text
GC(7) Pause Young (Allocation Failure) 90M->28M(128M) 12.300ms
GC(8) Pause Full (Ergonomics) 118M->74M(128M) 95.600ms
```

Questions to ask: Are Full GCs repeating? How much heap remains after a Full GC? Do pause durations exceed the latency budget? Are long-lived objects growing across cycles? Do not apply G1's "mixed collection" concept to Parallel merely because both have an old generation.

### 4.2. G1: read **regions and collection sets**, not three contiguous blocks

G1 divides the heap into **regions**. A region can act as eden, survivor, old, or humongous; regions sharing a role do not have to be contiguous. Two familiar pause types:

- **`Pause Young (Normal)`:** selects a *collection set* of young regions; live objects are evacuated to survivor or old regions. Eden becoming empty after collection **does not mean all objects in eden were dead**.
- **`Pause Young (Mixed)`:** after concurrent marking identifies suitable regions, G1 can collect a subset of **old regions alongside young regions**. "Mixed" is not a Full GC.
- **`Concurrent Start`, `Concurrent Mark Cycle`, `Remark`, `Cleanup`:** mark milestones for discovering live objects and preparing old region selection. Some phases are concurrent, while initial-mark/remark and parts of cleanup have STW pauses. Do not add all concurrent duration into total GC pause time.
- **`Humongous regions`:** large objects (roughly from half a region size under G1's rules) receive special handling. Heavy humongous allocations can cause fragmentation pressure or trigger marking early.
- **`Pause Full` or `Evacuation Failure`:** warns you to inspect insufficient evacuation space, allocation rate, marking timing, and free region count; it is not an automatic response to every "old full" state.

Example interpreting multiple lines for the same event (**illustrative, not a real measured transcript**):

```text
GC(20) Pause Young (Normal) (G1 Evacuation Pause) 160M->72M(256M) 8.000ms
GC(20) Eden regions: 58->0(64)
GC(20) Survivor regions: 4->5(8)
GC(20) Old regions: 32->34
```

Interpretation: G1 just ran an 8 ms young evacuation pause. Eden regions were freed; some objects may have survived and been placed in survivor or promoted to old. Old region count rising from 32 to 34 **does not prove a leak by itself**; inspect a series of many GCs, live old data, and application load. Region counts in these illustrative lines are not MB; region size must be obtained from startup logs/configuration.

If you see:

```text
Pause Young (Concurrent Start) ...
Concurrent Mark Cycle ...
Pause Remark ...
Pause Cleanup ...
Pause Young (Mixed) ...
```

read this as G1's characteristic progression: triggering/conducting marking, finalizing liveness information, and then selecting old regions to reclaim incrementally. Do not translate these lines into "Minor → Major" under a Serial GC framework.

**Approach when G1 has long pauses:** check pause frequency and percentiles; pause types young/mixed/full; `gc+phases` to locate where time goes (such as scanning remembered sets or object copy); `gc+heap` to see eden/survivor/old/humongous; and inputs like allocation rate, live set, and available CPUs. The `-XX:MaxGCPauseMillis` target is a **soft goal**, not a guarantee that every pause stays below the threshold.

### 4.3. ZGC: distinguish versions and **pauses vs. concurrent work**

ZGC aims for short pauses by performing most work concurrently with the application. In **JDK 21**:

- `-XX:+UseZGC` selects **non-generational** mode; do not look for "Eden/Survivor/Old" as mandatory.
- `-XX:+UseZGC -XX:+ZGenerational` selects **Generational ZGC**, which includes generational collection logic; event names may reflect young/old cycles. Do not assume labeling is identical between JDK 21 and other JDKs.
- Messages such as **`Pause Mark Start`/`Pause Mark End`** (mode-dependent), **`Concurrent ...`**, **`Garbage Collection (...)`**, and heap statistics must be read within the same cycle. A cycle taking tens or hundreds of milliseconds **does not mean** the application stopped continuously for that long.
- **Allocation Stalls** or signals that GC cannot keep pace with allocation rate can matter more than an isolated pause. Check retained heap, `-Xmx`, `-XX:SoftMaxHeapSize` if used, allocation rate, and CPU budget for GC workers.
- ZGC can change committed/uncommitted memory; distinguish **heap used**, **heap committed**, **heap reserved/max**, and **RSS**. Reclaiming objects does not necessarily reduce RSS immediately.

Key questions when reading ZGC: is the collector finishing concurrent work fast enough to supply space for new allocations? Are there allocation stalls or CPU pressure? How long are the actual STW pauses? Do not try to "infer Eden is full" from a log that has no Eden.

### 4.4. Shenandoah JDK 21: concurrent evacuation and fallback paths under memory pressure

Shenandoah on supported JDK 21 builds is a concurrent collector, **not generational** like Serial/Parallel. Phases can include:

- `Pause Init Mark` and `Pause Final Mark`: corresponding STW milestones for marking.
- `Concurrent marking`, `Concurrent evacuation`, `Concurrent update references`, or cleanup phases: work mostly running alongside the application.
- **Degenerated GC**: part of the concurrent work must fall back to STW to finish when it cannot keep up; **Full GC** is the heavier fallback path. This is a sign to investigate allocation pressure, heap headroom, and CPU availability.
- **Pacing/heuristics**: the collector may slow down some allocations to avoid running out of space. Application latency can shift even when recorded pauses remain short.

Read along the **mark → evacuate → update references** phases, fallback counts, allocation pressure, and pauses; do not expect an "Old generation after GC" metric to appear. Verify support in your JDK distribution before applying `-XX:+UseShenandoahGC`.

## 5. Systematic analysis: from logs to hypotheses

### 5.1. Sequence for reading an incident window

1. **Lock the time window:** when did request latency/p99 spike, on which node/pod, and with which PID and JVM uptime? Avoid stitching logs across restarted processes or containers.
2. **Identify JVM/collector:** version, GC selection flags, heap min/max, CPU quota, container memory limit, and `Using ...` line.
3. **Classify events:** STW pause, concurrent phase/cycle, Full/degenerated GC, allocation stall, explicit GC. Keep the collector's original names.
4. **Measure impact:** pauses per minute; max/p95/p99 duration of **pauses**; total STW time in the window; duration and frequency of concurrent cycles **tracked separately**. GC pause percentiles do not replace request latency percentiles.
5. **Read heap trends:** used before/after GC over time, heap capacity, estimated live set, old/humongous region counts if G1; for ZGC/Shenandoah read the metrics they actually report.
6. **Check mechanisms:** did G1 finish concurrent marking before old pressure grew? Did ZGC/Shenandoah have allocation stalls/degenerated/full? Did Parallel/Serial have frequent repeating Full GCs? Did safepoint time exceed GC pause time alone?
7. **Correlate non-GC data:** allocation rate, heap histogram/JFR when feasible, CPU/GC threads, RSS/native memory, container OOMKilled, request traces, thread dumps. Only conclude when data sources agree.

You can summarize findings in a small table:

| Verified observation | Reasonable hypothesis | Additional evidence to seek |
| --- | --- | --- |
| Frequent G1 young pauses but stable post-GC heap | Workload creates many short-lived objects | Allocation rate, JFR allocations, CPU, and p99 |
| Increasing G1 mixed pauses; post-Full GC usage stays high | Large live set, cache/retention, or allocation close to limit | Heap histogram/dump, heap size, old/humongous regions |
| Long ZGC concurrent cycles with allocation stalls | Allocation outpaces reclamation or CPU/heap headroom is lacking | Stall logs, allocation rate, CPU quota, committed/used heap |
| Shenandoah falls back to degenerated/full | Concurrent cycle cannot keep up with memory pressure | Fallback timestamps, headroom, pacing, and GC heuristics |
| Slow requests while GC pauses are very short | Cause may lie in CPU, other safepoints, locks, I/O, or network | Request tracing, thread/CPU profiling, safepoint logs |

The "hypothesis" column is **not yet a conclusion**. For instance, `after-GC` rising over three events might be a warming cache; inspect a steady-operation window and understand how retention is designed.

### 5.2. Three commonly misread scenarios

**Scenario A — "Old regions increased, definitely a leak."** G1 can promote long-lived objects from young to old; old growth during warm-up is normal. Compare levels after collections capable of reclaiming old (mixed/full), trends over many cycles, request/cache traffic, and heap object data. Do not use old region counts from a single young pause alone to conclude a leak.

**Scenario B — "Concurrent Mark Cycle took 850 ms, meaning requests froze for 850 ms."** Most concurrent marking runs alongside the application; only specific `Pause ...` phases reflect GC STW stops. At the same time, concurrent work still competes for CPU/memory bandwidth, so latency can degrade **indirectly**. Place it alongside pause/safepoint logs and request traces.

**Scenario C — "Only 2 ms pauses, so GC is unrelated."** With ZGC/Shenandoah, allocation stalls, pacing, CPU contention, or degenerated/full fallbacks can still impact latency. Inspect concurrent signals and machine resources too, not just max pause.

## 6. Runnable Java 17+/21 experiment

Create `GcLogDemo.java` with the content below. The program continuously allocates 64 KiB arrays, retains at most the 64 most recent arrays, and reads a byte from the evicted array to avoid turning the entire loop into unobservable allocations. This is an illustrative workload, not a representative production benchmark.

```java
import java.util.ArrayDeque;
import java.util.Deque;

public class GcLogDemo {
    public static void main(String[] args) {
        Deque<byte[]> recent = new ArrayDeque<>();
        long checksum = 0;

        for (int i = 0; i < 8_000; i++) {
            byte[] block = new byte[64 * 1024];
            block[0] = (byte) i;
            recent.addLast(block);

            if (recent.size() > 64) {
                checksum += recent.removeFirst()[0] & 0xff;
            }
        }

        System.out.println("retained=" + recent.size()
                + ", checksum=" + checksum);
    }
}
```

Compile and run with G1:

```bash
javac GcLogDemo.java
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*=info:file=g1.log:time,uptime,level,tags:filecount=3,filesize=10m GcLogDemo
```

**Program stdout** (excluding GC logs written separately to file):

```text
retained=64, checksum=1011840
```

Explanation: across 8,000 iterations, only the last 64 arrays remain in the deque; 7,936 arrays are removed to sum their unsigned first byte. The byte pattern 0..255 repeats exactly 31 times, so the sum is `31 × (0 + ... + 255) = 1,011,840`. The 64 MiB heap size encourages multiple GCs to observe; frequency, IDs, event names, and pauses depend on JDK/machine, so **there is no fixed GC stdout**.

Try sequentially on a supported JDK, with the same workload and heap configuration:

```bash
java -Xms64m -Xmx64m -XX:+UseParallelGC -Xlog:gc*=info:file=parallel.log:uptime,level,tags GcLogDemo
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*=info:file=g1-again.log:uptime,level,tags GcLogDemo
```

With **JDK 21** and builds supporting these collectors, you can also test ZGC/Shenandoah, though verify flags, minimum heap, and platform resources before comparing:

```bash
java -Xms64m -Xmx64m -XX:+UseZGC -Xlog:gc*=info:file=zgc21.log:uptime,level,tags GcLogDemo
java -Xms64m -Xmx64m -XX:+UseZGC -XX:+ZGenerational -Xlog:gc*=info:file=zgc-gen21.log:uptime,level,tags GcLogDemo
java -Xms64m -Xmx64m -XX:+UseShenandoahGC -Xlog:gc*=info:file=shenandoah21.log:uptime,level,tags GcLogDemo
```

**Log-reading exercise:** for each file, find the collector identification line, list event names, separate STW pauses from concurrent work, note the longest pause, and note the post-collection heap trend. Then state **two differences in interpretation**, such as G1 having young/mixed region phases while single-generation ZGC in JDK 21 has no Eden/Old diagram to apply directly. Do not declare "which collector is best" from this tiny demo alone; a reliable experiment needs realistic workload, warm-up, multiple runs, identical CPU/RAM limits, and latency/throughput criteria.

## 7. Common mistakes and self-checks

| Misconception | Correction |
| --- | --- |
| "Every collector has fixed physical Eden, Survivor, and Old." | Use the active collector's model: G1 region roles, non-generational vs. generational ZGC, concurrent Shenandoah. |
| "`Allocation Failure` in young GC means `OutOfMemoryError`." | That can be a normal collection trigger; look for OOME evidence, repeated failures, or inability to reclaim space. |
| "`Concurrent` = application paused." | Only specific STW/pause phases stop the application; concurrent work can still cause resource contention. |
| "`Pause Young (Mixed)` is a Full GC." | On G1, mixed selects a subset of old regions plus young regions; Full GC has a different mechanism and scope. |
| "`before->after(capacity)` is process RAM." | It is primarily Java heap stats in the collector's context; RSS/native/direct/metaspace require separate tools. |
| "One line of `Old regions` increasing proves a leak." | Inspect many cycles, warm-up, live set, and heap object retention. |
| "Summing durations across all `gc` lines gives GC pause time." | Start/end/phases lines repeat meaning and concurrent phases exist; sum only pause events by exact definition to avoid double counting. |
| "Default collector flags are identical across JDKs." | Check the exact JDK, startup logs, and VM flags; especially ZGC modes across releases. |
| "GC logs explain all latency." | Combine with safepoints, CPU, request traces, I/O, locks, and OS/container metrics. |

## 8. Conclusion checklist for a GC incident

- [ ] State **JDK version, vendor/build, PID, collector, collector mode, `-Xms`/`-Xmx`, CPU, and container limits**.
- [ ] Identify the **exact event types** in the log (young/mixed/full, concurrent cycle, allocation stall, degenerated...) and actual pause scope.
- [ ] Aggregate pauses over the **incident time window**, separating concurrent duration from STW; use consistent timestamps/uptimes.
- [ ] Compare **heap used before/after GC**, live-set trend, and collector-specific metrics (G1 regions/humongous, ZGC stalls, Shenandoah fallbacks...).
- [ ] Separate **observations**, **hypotheses**, and **supporting evidence** before proposing heap increases, collector changes, or application fixes.
- [ ] If changing configuration, re-measure with **the same workload/resource limits**, comparing throughput, p95/p99 latency, CPU, and footprint.

**Core principle:** start with "Which collector, which JDK, which phase, pause or concurrent, which heap metric?" before answering "What is slowing down the application or exhausting memory?". Do not force a fixed memory-region model onto every GC log.

## Reference documentation

- Oracle JDK 21 — [Available Collectors](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html): mechanisms and selection for Serial, Parallel, G1, ZGC.
- Oracle JDK 21 — [Garbage-First Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html): regions, young/mixed collection, concurrent marking.
- Oracle JDK 21 — [java command / Unified JVM Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-Xlog` syntax, tags, decorators, rotation, and GC flags.
- Oracle JDK 21 — [jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `VM.command_line`, `VM.flags`, `GC.heap_info`, `VM.log`.
- OpenJDK/Inside Java — [Introducing Generational ZGC](https://inside.java/2023/11/28/gen-zgc-explainer/): distinguishing ZGC modes in JDK 21.
- Red Hat OpenJDK 21 — [Using Shenandoah GC](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/21/html-single/using_shenandoah_garbage_collector_with_red_hat_build_of_openjdk_21/index): phases, logging, heuristics, and environment constraints.
