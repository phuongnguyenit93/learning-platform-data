# 22.7 Capturing and Analyzing GC Logs Together with JFR During a Heavy Allocation Phase

## Objectives and Outputs

A Java application can **allocate massive numbers of temporary objects** without having any memory leak. As the allocation rate climbs, the Garbage Collector (GC) works harder, yet you must clearly distinguish **the exact allocation workload**, **GC cycles and pause durations**, **the objects/call sites contributing most allocations**, and **data remaining live after GC**.

This practice lab combines two tools with complementary views:

- **HotSpot Unified GC log**: records GC progress over time, such as collector, GC ID, cause, heap used before/after collection, pause duration, and sub-phases when enabled.
- **Java Flight Recorder (JFR):** captures timestamped events for GC, heap, CPU, and allocation *samples* with class/stack trace; you can also add custom events marking start/end points of the experiment.

After this lesson, you will be able to:

1. Build a **runnable Java 17+ program** that drives a heavy allocation burst while retaining very little long-lived data, without needing to trigger an OOME.
2. Launch **the same JVM process** with unified GC logging and JFR, collecting both artifacts from a single run.
3. Read `GC(n)`, `48M->4M(128M)`, `Pause Young`, and pause durations while avoiding double-counting logs of the same GC.
4. Use `jfr summary`, `jfr print`, and JDK Mission Control to inspect `jdk.GarbageCollection`, `jdk.GCPhasePause`, `jdk.GCHeapSummary`, `jdk.ObjectAllocationSample`, and custom phase-marker events.
5. Join by **timestamp and GC ID** to construct a timeline linking allocation phases, allocation samples, GC pauses, and post-GC heap.
6. Distinguish **allocation pressure**, **GC overhead**, **valid working set**, and **unintended reference retention**, forming conditional conclusions with follow-up verification tools.

**Scope:** HotSpot/OpenJDK Java 17+ using **G1GC** in the lab. Commands and examples were run/verified on OpenJDK 24; core concepts apply to JDK 17/21, while GC counts, symbols, event counts, and durations vary by machine and JDK build. Never take one illustrative run as a production performance baseline.

## 1. Investigation Question: Allocation, GC, or Leak?

Frame three distinct hypotheses before collecting data:

| Hypothesis | Observable Signs | Insufficient to Conclude Alone |
| --- | --- | --- |
| **Allocation churn** — many short-lived objects | Allocation samples cluster at one call site; young GCs run frequently; post-young-GC heap used returns near baseline | Does not by itself prove a bug or leak |
| **GC overhead hurting latency** | Total/count of stop-the-world pauses rises during hot windows; p95/p99 spikes align with or sit near pauses | Seeing GC activity does not prove GC itself slowed down requests |
| **Suspected retention / leak** | Heap used *after comparable GCs* keeps climbing across multiple load/unload cycles, even after work stops | Cannot confirm a leak solely from GC count or one heap snapshot |

**Allocation rate** is memory allocated per unit of time. **Live set/retention** is the volume of objects still reachable at comparable points. These are independent concepts: a program can allocate gigabytes while retaining very little, or allocate slowly while accumulating millions of long-lived objects.

Reading both sources together:

```text
Application workload / object allocation
         |                         |
         |                         v
         |                 JFR allocation samples
         |                 (class, weight, stack, time)
         v                         |
Heap occupancy / GC triggers      |
         |                         |
         +----> Unified GC log <---+
         |       GC(n), before->after, pause, time
         |
         +----> JFR GC / heap events
                  startTime, gcId, pause, heap
         
Join by timestamp + gcId + application phase markers
=> explain when, why, and where GC increased
```

**Do not equate** the byte payload requested by array creations in code with total allocations recorded by the JVM: beyond payload bytes, there are object headers, alignment, other allocations, JIT/escape analysis, and internal JVM activity.

## 2. Setting Up a Safe Measurement Environment

### Prerequisites

- JDK 17 or newer with `java`, `javac`, and `jfr`. Examples used JDK 24; on JDK 21 verify flags with `java -Xlog:help` and `jfr help`.
- A **dedicated, writable** lab directory to hold `gc.log` and `burst.jfr`. Use separate directories/filenames per run so artifacts do not mix.
- Around **128 MiB Java heap** for the sample JVM plus reasonable off-heap headroom. Cumulative allocation exceeds heap size because older objects are continuously reclaimed; the test will not try to keep 468.75 MiB alive simultaneously.
- Never run a workload allocating hundreds of MB in production or environments with scarce memory/unclear quotas. This is a **controlled experiment on a dev/CI machine**.

Check the runtime:

```bash
java -version
javac -version
jfr help
java -Xlog:help
```

Use a matching `java`/`javac`/`jfr` toolchain from the same JDK when possible. Record JDK vendor/version, OS, heap flags, GC, CPU quota, and timestamp before each run. On non-HotSpot JVMs or other collectors, log/JFR formats and GC cycles can differ.

### Target Artifacts

| Artifact | Source | Purpose |
| --- | --- | --- |
| `GcJfrBurstLab.java` | Sample code below | Drives baseline, burst, and recovery phases; emits marker events |
| `gc.log` | JVM `-Xlog` | GC cycles, pre/post heap, pauses, and timestamps |
| `burst.jfr` | JFR started with the JVM | GC events, allocation samples, custom phase markers |
| Program `stdout` | `System.out.println` | Confirms workload ran and expected nominal payload bytes |
| Analysis log | Manual notes or separate tooling | Timeline/correlated findings and measurement limits |

When comparing runs, keep artifacts from **the exact same PID/JVM** together; never mix `gc.log` from run A with JFR from run B.

## 3. Java 17+ Program Creating a Heavy Allocation Phase

The program allocates 30,000 `byte[]` arrays, each holding **16 KiB payload**. New arrays continuously overwrite slots in a ring buffer of only **32 arrays**, so most older arrays lose references once overwritten. At the end of the phase, the program reads data from the ring so the arrays have an observable effect, reducing the chance the compiler eliminates the loop as dead code.

Four custom `lab.AllocationPhase` checkpoints:

- `baseline`: right after entering `main`.
- `burst-start`: right before the heavy allocation loop.
- `burst-end`: right after the allocation loop; records total nominal payload requested.
- `recovery`: after a pause to observe post-burst behavior.

**Note:** sleeping 600 ms before/after only creates an observation window; it does not guarantee a GC runs during sleep and does not replace multi-cycle leak testing.

### Complete Code: `GcJfrBurstLab.java`

```java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

public class GcJfrBurstLab {
    private static final int BLOCKS = 30_000;
    private static final int BLOCK_BYTES = 16 * 1024;
    private static volatile int retainedChecksum;

    @Name("lab.AllocationPhase")
    @Label("Allocation Phase")
    public static class AllocationPhase extends Event {
        @Label("Phase") public String phase;
        @Label("Nominal Allocated Bytes") public long nominalBytes;
    }

    private static void phase(String name, long nominalBytes) {
        AllocationPhase event = new AllocationPhase();
        event.phase = name;
        event.nominalBytes = nominalBytes;
        event.commit();
        System.out.println("phase=" + name);
    }

    private static int allocateBurst() {
        byte[][] ring = new byte[32][];
        for (int i = 0; i < BLOCKS; i++) {
            byte[] block = new byte[BLOCK_BYTES];
            block[0] = (byte) (i & 127);
            block[BLOCK_BYTES - 1] = (byte) (i >> 8);
            ring[i % ring.length] = block;
        }
        int checksum = 0;
        for (byte[] block : ring) {
            checksum += Byte.toUnsignedInt(block[0]);
        }
        return checksum;
    }

    public static void main(String[] args) throws Exception {
        phase("baseline", 0L);
        Thread.sleep(600);
        phase("burst-start", 0L);
        retainedChecksum = allocateBurst();
        phase("burst-end", (long) BLOCKS * BLOCK_BYTES);
        Thread.sleep(600);
        phase("recovery", 0L);
        System.out.println("blocks=" + BLOCKS);
        System.out.println("blockBytes=" + BLOCK_BYTES);
        System.out.println("nominalBytes=" + ((long) BLOCKS * BLOCK_BYTES));
        System.out.println("checksum=" + retainedChecksum);
    }
}
```

Explanation of safety and data semantics:

1. `byte[][] ring = new byte[32][]` retains at most 32 arrays simultaneously in scope, rather than trying to hold all 30,000 arrays. The ring keeps roughly `32 × 16 KiB = 512 KiB` of **final payload**, plus object headers and other objects.
2. `(long) BLOCKS * BLOCK_BYTES` yields **491,520,000 bytes = 468.75 MiB nominal payload** requested across the loop. This is **not** the final live heap size nor the JVM's total allocated bytes.
3. JFR markers `phase("burst-start")`/`phase("burst-end")` help pinpoint the exact window on the timeline; a custom event is not a `System.gc()` call and does not trigger garbage collection.
4. `retainedChecksum` is a `volatile` field and its result is printed; the computation has observable side effects. It is not a substitute for JMH in microbenchmarking.
5. `Thread.sleep(600)` separates phases clearly on the timeline, though scheduling can make actual duration differ from 600 ms.
6. The workload is built to observe **allocation churn**, not simulate a memory leak. Modifying it to hold unbounded objects or raise `-Xmx` creates a completely different experiment.

## 4. Capturing GC Logs and JFR in the Same JVM Run

### 4.1. Verified Launch Commands

In the directory containing the source file, using Bash/Linux/macOS:

```bash
javac GcJfrBurstLab.java

java -Xms128m -Xmx128m -XX:+UseG1GC \
  '-Xlog:gc*=info,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=1,filesize=20m' \
  '-XX:StartFlightRecording=filename=burst.jfr,settings=profile,dumponexit=true' \
  GcJfrBurstLab
```

In **Windows PowerShell**, run the Java command on **one line**, avoiding Bash's `\` line continuation:

```powershell
javac GcJfrBurstLab.java
java -Xms128m -Xmx128m -XX:+UseG1GC '-Xlog:gc*=info,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=1,filesize=20m' '-XX:StartFlightRecording=filename=burst.jfr,settings=profile,dumponexit=true' GcJfrBurstLab
```

This ran cleanly on **OpenJDK 24 on Windows** during testing. On Java 17/21, this unified logging and Startup Flight Recording syntax is available on HotSpot, though default/profile events and counts may differ; verify on your JDK version.

**What does each flag do?**

| Flag | Role |
| --- | --- |
| `-Xms128m -Xmx128m` | Sets initial/max heap both to 128 MiB so heap capacity stays steadier; does not cap total process RSS to 128 MiB |
| `-XX:+UseG1GC` | Fixes G1 so examples like `Pause Young (G1 Evacuation Pause)` apply |
| `-Xlog:gc*=info,safepoint=info` | Captures messages tagged with `gc` (including composite GC tags) and `safepoint` at `info` level |
| `file=gc.log` | Writes GC log to a file; run in a fresh directory to avoid mixing old files |
| `time,uptime,level,tags` | Prints wall-clock timestamp (with timezone offset), JVM uptime, and tags for aligning with JFR |
| `filecount=1,filesize=20m` | Enables bounded log rotation in the demo; **inspect all rotated files** on longer runs |
| `-XX:StartFlightRecording=...` | Starts JFR with the process so the initial burst is not missed |
| `settings=profile` | Template capturing richer profiling data; heavier than `default` and does not promise every event is enabled |
| `filename=burst.jfr,dumponexit=true` | Writes JFR to disk on normal JVM exit; does not guarantee full capture on `SIGKILL`/crash |

**Do not re-run in the same directory** if you still need old artifacts: `gc.log` or `burst.jfr` may be overwritten. In services/CI, use separate directories or filenames keyed by run ID with a retention policy. When long-term GC logs are required, size rotation count/filesize to cover the full investigation window; never read only the newest file when multiple rotated files exist.

### 4.2. Exact Program Stdout

```text
phase=baseline
phase=burst-start
phase=burst-end
phase=recovery
blocks=30000
blockBytes=16384
nominalBytes=491520000
checksum=1008
```

This is the **deterministic stdout of the example**, verified by compiling and running on JDK 24. The JVM may also print **separate** JFR startup messages to the console; startup details such as PID, filename, and maxsize vary. GC counts, pauses, allocation samples, timestamps, file sizes, and latencies also vary between runs.

### 4.3. Verifying Both Artifacts

After the Java process **exits successfully**, check:

```bash
ls -lh gc.log burst.jfr
jfr summary burst.jfr
```

PowerShell equivalent:

```powershell
Get-Item .\gc.log, .\burst.jfr | Select-Object Name,Length
jfr summary burst.jfr
```

If `burst.jfr` is missing, check exit code, JFR startup messages, write permissions, and whether the process exited normally. If `gc.log` lacks expected events, verify the JVM actually ran with `-Xlog`, collector/heap flags, and log rotation. **Never inspect a leftover file from a previous run and declare this run's capture successful.**

You can start a recording on an already running JVM via `jcmd <PID> JFR.start settings=profile ...` and dump when needed; however, for this lab starting GC logging and JFR **from launch on the same PID** avoids window skew. When attaching to a live service, consult `jcmd <PID> help JFR.start`, `JFR.check`, and your operational runbook; JFR attached after a burst cannot recover past events.

## 5. Analyzing the GC Log: GC Count, Pre/Post Heap, Pauses

### 5.1. Reading the JVM Startup Header

Because `gc*=info` is enabled, the start of the file lists the collector and parameters:

```text
[...][info][gc     ] Using G1
[...][info][gc,init] Heap Initial Capacity: 128M
[...][info][gc,init] Heap Max Capacity: 128M
```

These lines are abbreviated from **one example run**. They confirm the collector and heap limit, preventing mistaking a JVM actually running another collector. `128M` is the Java heap cap, **not total RSS**, excluding metaspace, thread stacks, code cache, and many native areas.

### 5.2. Reading a `Pause Young` Line

During verification on OpenJDK 24, a line read:

```text
[2026-10-29T18:19:02.690+0700][0.835s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 48M->4M(128M) 2.355ms
```

Breakdown of each part:

| Part | Explanation |
| --- | --- |
| `2026-10-29T18:19:02.690+0700` | Wall-clock log timestamp, including UTC offset |
| `0.835s` | JVM's own uptime at log time; not seconds since the burst started |
| `info` and `gc` | Log level and GC tag |
| `GC(0)` | VM GC ID for this run, useful for joining with JFR events by `gcId` |
| `Pause Young (Normal)` | A young-generation collection with a stop-the-world pause |
| `G1 Evacuation Pause` | G1 evacuation phase |
| `48M->4M(128M)` | Heap used **before/after** GC, and displayed heap capacity (128 MiB with demo flags) |
| `2.355ms` | Pause duration reported in the GC log for this collection |

**Do not read `48M->4M` as "the JVM freed exactly 44 MiB of leaked objects."** It shows net heap used dropped across one young GC; diagnosing causes still depends on allocation rate, object ages, promotions, and collector behavior.

### 5.3. Distinguishing Start, Completion, and Detailed Sub-Phase Logs

With `gc*=info`, one GC can emit multiple lines:

```text
[...][info][gc,start] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
[...][info][gc]       GC(0) Pause Young (Normal) (G1 Evacuation Pause) 48M->4M(128M) 2.355ms
```

Counting every line containing `Pause Young` as a separate GC **double-counts**. Count only one completion summary line per `GC(n)`; lines tagged `gc,phases`, `gc,heap`, `gc,cpu` describe details of that same GC. Never add all sub-phase durations onto the total pause when those phases already sit inside the total pause.

### 5.4. Observed GC Results from One Run

These numbers were **collected in one example run on OpenJDK 24**, not fixed output across all machines:

| GC ID | Heap used before → after (capacity) | Pause |
| --- | --- | ---: |
| `GC(0)` | 48M → 4M (128M) | 2.355 ms |
| `GC(1)` | 59M → 4M (128M) | 1.651 ms |
| `GC(2)` | 71M → 4M (128M) | 1.774 ms |
| `GC(3)` | 76M → 4M (128M) | 2.064 ms |
| `GC(4)` | 76M → 4M (128M) | 1.549 ms |
| `GC(5)` | 76M → 4M (128M) | 1.722 ms |
| `GC(6)` | 76M → 4M (128M) | 1.494 ms |
| **Total 7 pauses** | — | **12.609 ms** |

The total above sums **the seven durations on the seven completed GC lines**, without re-adding `gc,start` lines or nested GC sub-phases. Use these numbers to practice reading; your run may show fewer or more GCs, a different post-GC heap floor, or different pause ranges.

**Valid observation for this run:** during the heavy allocation phase, heap used rose between young GCs yet fell back near 4M after each cycle; this **is consistent with short-lived objects**. It does not prove the entire application is leak-free, especially if the test was brief or missed other load cycles.

### 5.5. Metrics to Extract

| Metric | How to Obtain | Limitation |
| --- | --- | --- |
| GCs during burst | Count unique GC IDs timestamped in the burst window | Exclude start/sub-phase lines and GCs outside the window |
| Total GC pause | Sum **total** pauses of GCs inside the window | Never add `GCPhasePauseLevel1/2/...` as independent pauses |
| Pause ratio in window | `sum(STW pause duration) / wall duration` | Not directly equal to GC %CPU; concurrent GC and queue latency differ |
| GC frequency | `GC count / observation duration` | Depends on heap size, workload, collector; does not prove a bug on its own |
| Post-GC heap used | Compare points **after comparable GCs** | Young GC does not collect all old-generation objects |
| Pre/post heap occupancy | GC log occupancy | Not equal to total bytes allocated by all objects in the interval |
| App throughput/latency | Independent metrics or load tests | Cannot be inferred from `gc.log` alone |

If user latency is the concern, correlate request traces/metrics on the same timeline. Without latency metrics, restrict conclusions to **GC behavior in the lab**, never blaming GC pauses for an SLO violation without timing overlap.

## 6. Reading JFR: GC Events and Allocation Samples

### 6.1. Checking Event Types and Counts

Inside the lab directory:

```bash
jfr summary burst.jfr
jfr metadata --events jdk.ObjectAllocationSample burst.jfr
jfr metadata --events lab.AllocationPhase burst.jfr
```

`jfr summary` reports instance counts per event type **actually written to the file**; `metadata` describes the schema, not proof that instances occurred. For instance, a file defining `jdk.ObjectAllocationSample` with 0 instances could result from being disabled, insufficient activity, sampling/throttling, or a recording window missing the burst.

**One verified run** produced these counts:

```text
jdk.ObjectAllocationSample       120
jdk.GCHeapSummary                 14
jdk.GCPhasePause                   7
jdk.GarbageCollection              7
lab.AllocationPhase                4
```

This is only an **excerpt of two columns (event name and count)** from `jfr summary`, not verbatim full stdout. 120 allocation samples **does not mean only 120 objects were allocated**; the program requested 30,000 arrays. Those two counts mean entirely different things.

### 6.2. Inspecting Phase Markers to Bound the Window

```bash
jfr print --events lab.AllocationPhase burst.jfr
```

Excerpt **from the verified run**:

```text
lab.AllocationPhase {
  startTime = 18:19:02.082 (2026-10-29)
  phase = "baseline"
  nominalBytes = 0
}
lab.AllocationPhase {
  startTime = 18:19:02.683 (2026-10-29)
  phase = "burst-start"
  nominalBytes = 0
}
lab.AllocationPhase {
  startTime = 18:19:02.741 (2026-10-29)
  phase = "burst-end"
  nominalBytes = 491520000
}
lab.AllocationPhase {
  startTime = 18:19:03.342 (2026-10-29)
  phase = "recovery"
  nominalBytes = 0
}
```

These markers show when the program itself started/ended the allocation loop; **they are not four GCs**. `nominalBytes=491520000` is application-reported data, not bytes measured independently by JFR.

In this dataset, `burst-start` → `burst-end` spans **approximately 58 ms**, yet do not cite that duration as a production throughput figure. JIT, CPU, OS, GC, platform, and JFR overhead all affect timing. When analyzing GC for a specific phase, filter to the marker window instead of the whole file.

### 6.3. Inspecting GC Events and Comparing with the GC Log

```bash
jfr print --events jdk.GarbageCollection burst.jfr
jfr print --events jdk.GCPhasePause burst.jfr
jfr print --events jdk.GCHeapSummary burst.jfr
```

Example `GCPhasePause` for `gcId=0`:

```text
jdk.GCPhasePause {
  startTime = 18:19:02.688 (2026-10-29)
  duration = 2.30 ms
  gcId = 0
  name = "GC Pause"
  eventThread = "VM Thread" (...)
}
```

For the same GC, the GC log has `GC(0) ... 2.355ms` at a matching timestamp. **`gcId` and the time window** confirm both sources describe the same GC; small differences arise from measurement boundaries, resolution, rounding, and duration definitions — not proof that the log is wrong.

Distinguish event types:

| JFR Event | Interpretation | What Not to Do |
| --- | --- | --- |
| `jdk.GarbageCollection` | Collection summary with `gcId`, name, cause, and duration/pause depending on JDK | Treat a concurrent cycle's duration as total STW pause |
| `jdk.GCPhasePause` | A stop-the-world GC pause, with `gcId` and duration | Add sub-phases `GCPhasePauseLevel1/2/3/4` onto total |
| `jdk.GCHeapSummary` | Pre/post-GC heap snapshot with `gcId`/`when` and heap stats | Confuse heap committed with heap used or RSS |
| `jdk.ObjectAllocationSample` | Allocation sample with object class, weight, thread, and stack trace if captured | Count samples as exact object counts |
| `lab.AllocationPhase` | Custom event marking lab steps | Mistake custom markers for JVM-detected GC data |

When `jdk.GCHeapSummary` includes `when=Before GC` and `After GC`, match occupancy by **the same `gcId`**. Fields and presentation can change across JDKs/collectors; inspect schema with `jfr metadata` instead of assuming every field exists.

### 6.4. Inspecting Allocation Samples for Classes and Call Sites

```bash
jfr print --events jdk.ObjectAllocationSample --stack-depth 8 burst.jfr
```

Sample event from the test run:

```text
jdk.ObjectAllocationSample {
  startTime = 18:19:02.683 (2026-10-29)
  objectClass = byte[] (classLoader = bootstrap)
  weight = 522.6 kB
  eventThread = "main" (javaThreadId = 3)
  stackTrace = [
    GcJfrBurstLab.allocateBurst() line: 28
    GcJfrBurstLab.main(String[]) line: 44
  ]
}
```

Interpretation:

- **`objectClass=byte[]`**: the sampled object class. In the lab, we know arrays were created inside `allocateBurst()`.
- **`stackTrace`**: ties the allocation to a call path; if missing, verify event `stackTrace` settings and recorder data.
- **`weight`**: **sample weight** used to estimate allocation pressure when aggregated over enough samples — neither a single object's size nor the exact bytes allocated by the application at that instant.
- **`eventThread=main`**: thread at sample time, without implying every allocation came from one thread.

JFR allocation sampling is **statistical**. Events like `jdk.ObjectAllocationInNewTLAB`/`OutsideTLAB` (if available/enabled) have different semantics and also do not capture **every** object by default. Never sum all allocation event types together as independent meters to claim exact total bytes. To rank top allocating classes, use **properly aggregated weighted samples** in JDK Mission Control or compatible tools, then inspect call stacks.

Moreover, 30,000 `byte[]` creations in Java code do not guarantee 30,000 allocation events: compiler optimizations, JFR throttling/sampling, caches, frameworks, and capture paths all affect counts. Having **120 samples** is not "missing 29,880 events" by definition; it is how sampling works.

## 7. Aligning GC Log and JFR on One Timeline

A strong report connects **phase marker → allocation stack → GC event → heap/pauses → post-burst state**.

### 7.1. Choosing One Common Time System

The GC log enabled two decorators:

- **`time`:** absolute wall-clock timestamp with UTC offset, e.g., `2026-10-29T18:19:02.690+0700`.
- **`uptime`:** seconds since JVM start, e.g., `0.835s`.

`jfr print` displays `startTime` in local timezone and may format per tool settings. When joining, verify **timezone, date, PID, and JVM start time**. Never match events merely because seconds digits look similar when one is uptime and the other is wall-clock time.

In this lab:

```text
JFR marker: burst-start          18:19:02.683
GC log:    GC(0) start           18:19:02.687
JFR:       GCPhasePause gcId=0   18:19:02.688, 2.30 ms
GC log:    GC(0) completed       18:19:02.690, 2.355 ms
...
GC log:    GC(6) completed       18:19:02.738
JFR marker: burst-end            18:19:02.741
JFR marker: recovery             18:19:03.342
```

This timeline is **extracted from one verified run**. Seven young GCs align with the marked burst window. JFR and the GC log act as a **cross-check** via timestamps/`gcId`, rather than relying on one source validating itself.

### 7.2. Phase Analysis Table

| Phase | Program Expectation | GC Log | JFR |
| --- | --- | --- | --- |
| **Baseline** | Loop of 30,000 arrays not yet started | May still show JVM startup/other GC activity | `baseline` marker; pre-burst events excluded from burst totals |
| **Burst-start → burst-end** | Allocates short-lived byte arrays, requesting 491,520,000 bytes payload | Typically multiple young GCs with rising/falling heap occupancy; measure actuals | `byte[]` allocation samples in `allocateBurst()`; `GarbageCollection`/`GCPhasePause` near matching timestamps |
| **Recovery** | Allocation loop finished, short idle | May show no new GC; heap used may not drop on its own if no GC runs | `recovery` marker and any captured GC/heap events |
| **After process exit** | Program exits cleanly | `gc.log` flushed per log settings | `burst.jfr` dumped via `dumponexit=true` |

**Do not conclude "heap still high in recovery ⇒ leak"** if no suitable GC ran after recovery. Heap usage may hold uncollected garbage, and committed memory need not return immediately to the OS. Compare post-GC points across comparable cycles rather than demanding heap used return to 0 whenever the app idles.

### 7.3. Correlating by `gcId`

Within one HotSpot JVM, GC events belonging to the same collection usually share `gcId`, matching `GC(n)` in the GC log. In the demo, `GC(0)` matches `jdk.GCPhasePause gcId=0`. However, if JFR started late, events were filtered/dropped, snapshots cover a narrower window, or the collector uses concurrent phases, **event counts need not equal log line counts**.

Reliable manual workflow:

1. Read timestamps of `burst-start` and `burst-end`.
2. Filter **completed GC lines** within that interval; record `GC(n)`, type, before/after, and pause duration.
3. In JFR, filter `jdk.GarbageCollection`/`GCPhasePause` by time; record `gcId` and duration.
4. Join on `gcId` and cross-check timestamps; never zip by print order if counts differ.
5. From JFR allocation samples in **the same phase window**, rank top classes and call stacks by weight rather than reading every sample across the whole recording.
6. From `GCHeapSummary`/post-GC logs, check whether heap returns near baseline or climbs steadily across cycles.

### 7.4. What to Check When Both Sources Disagree

| Observation | Check First |
| --- | --- |
| GC log shows 7 young GCs, JFR shows only 5 | JFR start/end, retention, enabled flags, event types, export timing |
| GC log 2.355ms, JFR pause 2.30ms | Clock resolution, rounding, event start/end hooks; `gcId` |
| 120 JFR allocation samples vs. 30,000 created arrays | Sampling, throttling/weights — not an allocation-by-allocation log |
| `jdk.GCHeapSummary` shows large heap while GC log `after` is small | Check `when=Before/After`, `gcId`, units, heap used vs. committed, collector |
| High allocation yet barely any GC | Heap large enough, allocation outside window, missing JFR samples; verify data first |
| Heap did not drop during recovery | No GC ran in recovery, objects still reachable, or GC policy keeps heap committed |
| JFR lacks custom markers | Verify right file, event settings, JFR started before `main`, and clean dump |

## 8. Reading in JDK Mission Control (JMC)

If JDK Mission Control is available, open `burst.jfr` and inspect in order:

1. **General/Recording information:** start/end, duration, JVM/JDK, and recording settings to verify this is the right run's file.
2. **Event Browser:** find `lab.AllocationPhase`, read the four checkpoints, and select **the burst window**.
3. **Memory/Allocations:** view allocation pressure over time; group by class and allocation stack. `byte[]` and `GcJfrBurstLab.allocateBurst` are the expected path in the demo.
4. **Garbage Collections / GC Pauses:** compare count, GC type, longest/sum of pauses, and `gcId`/timestamps against `gc.log`.
5. **Heap statistics/usage:** distinguish used, committed, before/after GC; when heap summary has multiple snapshots, match by `gcId`.
6. **CPU and Threads:** check whether other CPU saturation or compiler/GC worker activity adds noise.
7. **Export notes:** save timeline tables/needed screenshots, always recording JDK/event settings and time ranges. Overview charts are interpretive aids; keep the raw file for auditing.

**Do not assume every machine has JMC**, as JMC may be installed separately. JDK's `jfr summary`/`jfr print` commands still allow completing the lab. If JMC uses a different timezone/filter, never compare time labels blindly; normalize timezones first.

## 9. Analysis: Allocation Churn Is Not a Memory Leak

In this experimental run:

- The program requested roughly **468.75 MiB of array payloads** in a very short burst.
- The heap cap was only **128 MiB**.
- The GC log recorded **7 young GCs**; post-young-GC used settled near **4 MiB**, while pre-GC usage climbed into tens of MiB.
- JFR captured **120 `jdk.ObjectAllocationSample`** events showing `byte[]` samples from `GcJfrBurstLab.allocateBurst()`.
- Four markers clearly bounded when the burst started and ended.

This data **strongly supports** the conclusion that the burst mainly created short-lived arrays and GC reclaimed most of them in young collections. **There is no evidence of a leak in this short test.** Still, you cannot declare every object class short-lived or guarantee production is leak-free without further workload and longer observation.

### What Extra Testing Is Needed When Retention/Leak Is Suspected?

Design multiple **ramp-up → ramp-down → repeat** cycles with fixed workload and concurrency:

- Measure heap used after comparable GC points, not just pre-GC heap used.
- Compare before and after warm-up; separate valid caches/connection pools/sessions/indexes from obsolete objects.
- If unreachable-in-logic yet retained objects grow after every cycle, capture a heap dump/histogram and analyze dominators/GC roots **per operational policy**.
- Do not blindly force `System.gc()` as a "standard leak test": it perturbs application behavior and may not run as expected depending on JVM flags. Run controlled GC experiments only in authorized environments.
- Inspect direct buffers, JNI/native memory, metaspace, and RSS if process memory climbs while Java heap/JFR object allocations do not explain it.

### When Is GC Actually a Performance Problem?

Heavy allocation **becomes a problem only** when it noticeably impacts latency/throughput, CPU, or costs that matter to product goals. You also need:

- **Request latency and SLOs** on the same timestamps; do slow requests overlap with GC STW pauses?
- **Sum of pauses / wall duration**, longest pause, GC frequency, and GC CPU time if available. Concurrent GC work differs from stop-the-world pauses.
- **Allocation rate by endpoint or class/call stack** from JFR weighted samples and independent metrics.
- **Matched load and config** for before/after optimization comparisons: JDK, GC, heap, flags, payloads, caches, RPS, concurrency, quotas.
- **Verification changes**: trim allocations on hot paths, size pools/caches sensibly, or adjust data structures, then re-measure p95/GC/alloc. Do not start by tweaking GC flags on gut feeling.

## 10. Common Measurement and Interpretation Mistakes

**1. Counting two `GC(0)` lines as two collections.** `gc,start` and the completion summary share the same GC ID. Count once per ID per reporting goal.

**2. Adding nested GC sub-phases onto total pause.** `GCPhasePauseLevel1/2/3/4` can be nested phases. Never add them onto `GCPhasePause` and conclude the app paused longer than reality.

**3. Reading `48M->4M(128M)` as exactly 44 MiB allocated.** That is pre/post-GC heap occupancy, not total bytes allocated between GCs or bytes leaked.

**4. Treating JFR allocation sample count as object count.** Sampling weights represent statistical estimates; 120 samples do not contradict 30,000 array allocations.

**5. Summing all `weight` values without checking windows and aggregation rules.** Weights are statistically meaningful only within matching event types/settings. If JFR throttling or sampling changes, A/B run comparisons break.

**6. Treating `nominalBytes=491520000` as live heap size.** That is cumulative payload requested by the demo; old arrays overwritten in the ring are continuously reclaimed by GC.

**7. Mixing GC log and JFR from two different runs.** Keep identical JVM/PID, clock/timezone, files, and runtime build; align with markers/`gcId` and timestamps.

**8. Comparing GC log `uptime` directly against JFR local time.** One is elapsed time since start, the other is wall-clock time. Convert to a common time axis.

**9. Reading the JFR file before the process exits to dump.** The demo's `dumponexit=true` writes on clean exit; for mid-run snapshots on long processes, use `jcmd JFR.dump` and verify the file.

**10. Concluding no leak because 4 MiB remained after one young GC.** Old gen, valid caches, or slow leaks may not appear in a short burst. Track post-GC baselines under identical conditions across many cycles.

**11. Blaming GC for high p95 without latency telemetry.** GC had pauses, yet they may not overlap the slow requests; correlate application metrics/tracing and timestamps.

**12. Turning on `gc*=debug` or unbounded full allocation tracing in production.** Verbose logs, dense JFR sampling, and deep stack traces add overhead/disk growth; bound time windows and storage budgets.

**13. Starting JFR too late after the burst passed.** Events before recording started cannot be recovered. Configure JFR from startup or schedule capture early enough.

**14. Comparing runs with different collectors or heap sizes without noting it.** Identical workloads under G1/Parallel/ZGC yield different log formats, pause distributions, and event counts; treat that as an independent variable.

**15. Watching only Java heap and ignoring RSS/native.** GC/JFR object allocations do not reflect all off-heap memory. Metaspace, thread stacks, direct/native buffers, and JNI require separate views.

## 11. Controlled Extended Practice

After running the baseline example cleanly, create three runs **in separate directories**, changing only one variable per run:

| Run | Changed Variable | Prediction to Verify |
| --- | --- | --- |
| A | `-Xms128m -Xmx128m`, original code | Multiple young GCs during burst; JFR samples on `byte[]` |
| B | Larger heap within host limits, same code/collector | Likely fewer GCs; does not guarantee allocation payload drops |
| C | Reduce `BLOCKS` by a fixed factor, same heap | Total payload drops, GC pressure usually drops; measure actuals |

If modifying source code, recompile; keep Java/JFR flags, workload, and timing comparable. **Never hardcode predicted GC counts**, as collector heuristics and environments vary. Record each run's `GC(n)`, pause sum, JFR allocation samples, and phase timestamps.

### Result Recording Table

| Metric | Run A | Run B | Run C |
| --- | --- | --- | --- |
| JDK/OS/G1/heap flags | | | |
| `BLOCKS` × `BLOCK_BYTES`, nominal bytes | | | |
| Markers `burst-start`/`burst-end` | | | |
| GC ID count during burst | | | |
| Total STW pause during burst | | | |
| Longest pause | | | |
| Heap used after last GC in burst | | | |
| `jdk.ObjectAllocationSample` count | | | |
| Top allocation classes/call sites by weight | | | |
| Meaning/limitations | | | |

### Self-Check Questions

1. There were 30,000 `new byte[]` calls yet JFR only has 120 allocation samples; were 29,880 objects lost? **You cannot infer that.** These are sampled events, not a log of every allocation.
2. What does `GC(0) 48M->4M(128M)` mean? **Heap used before/after one GC**, with 128 MiB displayed heap capacity; not a 44 MiB leak.
3. Why might JFR `GCPhasePause gcId=0` and log `GC(0)` show slightly different durations? **Resolution, rounding, and hook boundaries/definitions**; confirm matching GC ID and time.
4. If the `recovery` marker appeared yet heap has not dropped on its own, is there a leak? **Insufficient evidence.** No GC may have run after recovery; compare post-collection checkpoints.
5. Why use burst timestamps instead of viewing the whole JFR file? **To exclude startup/background noise** and isolate the heavy allocation interval.
6. Why doesn't total pause equal total CPU spent on GC? **Concurrent GC performs CPU work outside stop-the-world pauses**, and sub-phases overlap inside total pauses.
7. If JFR contains zero `jdk.ObjectAllocationSample` events, does that mean zero allocations? **No.** Check profile/settings, sampling/throttling, recording window, and artifact integrity.
8. When do you need a heap dump? **When suspecting sustained retention and needing GC roots/owners**, not automatically whenever GC runs frequently.

## 12. Checklist Before Finalizing Your Report

- [ ] Single JVM run; recorded JDK build, collector, heap flags, PID, clock/timezone, and dedicated artifact folder.
- [ ] Both `gc.log` and `burst.jfr` exist and are readable; verified exit status and log rotation.
- [ ] All four markers (`baseline`, `burst-start`, `burst-end`, `recovery`) present at the right timestamps.
- [ ] GC log parsed by **unique GC ID**, without double-counting start/sub-phase lines.
- [ ] Separated **heap used**, **heap capacity**, **total allocated payload**, **object sample weight**, and **RSS**.
- [ ] Total pause summed from non-overlapping STW pauses; nested sub-phases not added.
- [ ] JFR event names/counts, enabled state, and sampling behavior verified.
- [ ] Joined `GC(n)` with JFR `gcId` and timestamps in the same burst window.
- [ ] Top allocation classes/call sites taken from JFR; avoided treating sample count as object count.
- [ ] Avoided declaring a leak from one burst; if retention is suspected, compared across post-GC cycles and investigated owners.
- [ ] When claiming performance impact, backed by independent request latency/throughput metrics and aligned timestamps.
- [ ] Documented **observations**, **hypotheses**, **verification steps**, and demo limitations clearly.

**Conclusion:** Unified GC logs tell you *which GC happened, when, how heap used changed, and how long the JVM paused*. JFR tells you *GC events sharing `gcId`, which object types were sampled at which call stacks, and workload phase markers*. Joining **GC ID + timestamp + phase markers** on the same JVM lets you characterize a **heavy allocation churn** episode with two-source evidence without mistaking it for a **memory leak** or a proven GC bug.

## Official References

- Oracle JDK 21 — `java`, Unified Logging, `-Xlog`, log decorators/rotation: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21 — `jcmd`, `JFR.start`/`JFR.check`/`JFR.dump`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — `jfr` (`summary`, `print`, `metadata`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle JDK 21 — Diagnostic Tools and Flight Recorder: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21 — HotSpot Garbage Collection Tuning Guide: https://docs.oracle.com/en/java/javase/21/gctuning/
- Oracle JDK 21 — `jdk.jfr` API: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html