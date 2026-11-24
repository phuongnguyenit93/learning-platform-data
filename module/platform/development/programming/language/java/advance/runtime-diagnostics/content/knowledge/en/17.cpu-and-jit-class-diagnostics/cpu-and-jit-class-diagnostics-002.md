# 17.2 Combining CPU Metrics, Multiple Stack Snapshots, and JFR Execution Samples

> **Scope:** Java 21 / HotSpot, diagnosing an application with **high CPU or abnormal throughput/latency**. This lesson shows how to combine **OS/JVM CPU metrics**, **multiple thread stack snapshots (thread dumps)**, and **JFR `jdk.ExecutionSample`** into an evidence-backed conclusion. CPU groups for **JIT compiler, class loading, and GC** are included so you do not mistake JVM CPU for business-code CPU. OS commands illustrate Linux; adjust them for Windows/containers.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Determine **whether CPU is high at the machine, container, process, or OS-thread level**, on the right JVM/PID and within the **same symptom window**.
2. Collect **multiple** timestamped stack snapshots, distinguish `RUNNABLE` from actually consuming CPU, and correlate thread name, Java thread ID, and OS TID (`nid`) when available.
3. Collect JFR `settings=profile`, read `jdk.CPULoad`, `jdk.ThreadCPULoad`, and `jdk.ExecutionSample`, and analyze the distribution of **sampled stacks**.
4. Combine all three sources to narrow down a **hot code path**; explain why a single snapshot or a single sample is **not enough** to confirm the root cause.
5. Recognize **JIT warmup, class loading, GC, native CPU, CPU quota/throttling, and waiting** as competing diagnostic hypotheses; design a re-measurement to refute or support each hypothesis.

**Guiding question:** "During the exact symptom window, is the Java process actually consuming CPU; which threads are consuming it; which stacks repeat across **multiple independent samples**; and does that conclusion align with JFR?"

## 2. Three Evidence Sources Answer Three Different Questions

| Source | Answers Best | Does Not Prove on Its Own |
| --- | --- | --- |
| **Machine/container/JVM/OS thread CPU** (monitoring, `top`, `ps`, cgroup) | Is CPU actually busy, where is it busy, for how long, and what resource limits apply | Which Java method is expensive or which request code path called it |
| **Multiple thread dumps** (`jcmd <PID> Thread.print`) | At each instant, what stack and state each thread is in; whether the same frames repeat | How much CPU a `RUNNABLE` thread consumed between dumps; the full history |
| **JFR execution sampling** (`jdk.ExecutionSample`, combined with `jdk.CPULoad`, `jdk.ThreadCPULoad`) | Over an interval, which stacks/methods appear often in execution samples, and trends by thread/time | How many times a method ran, exact CPU-ns per method, or causality from sample percentage alone |

A credible CPU investigation usually forms an **evidence triangle**:

```text
High process CPU in window T
        │
        ├── OS: which platform threads / TIDs are busy?
        │
        ├── Thread dumps at T1, T2, T3...: which stacks repeat?
        │
        └── JFR in the same T: where do ExecutionSamples cluster?
                              ↓
                  Hot code path hypothesis
                              ↓
                  Measure/adjust and compare under the same load
```

Note: **time correlation** is not yet solid proof of causality. If the three sources contradict each other, look for explanations in timing, sample configuration, thread names, or CPU outside Java user code before modifying the program.

## 3. Before Hunting for Hot Methods: Define "High CPU"

### 3.1. Distinguish Measurement Levels

- **Machine CPU**: utilization of the whole machine/VM. It can be high due to other processes, kernel work, or system services while the application JVM uses little CPU.
- **Process CPU**: cumulative CPU time of threads in the Java process, usually presented as a rate over an interval. `100%` in some Linux tools equals **one logical CPU completely busy**, so a JVM on a multi-core host can show **over 100%**. Other tools normalize to total machine CPU; always state the convention.
- **Thread CPU**: CPU time of one OS/platform thread. It may be a business thread, GC worker, JIT compiler thread, or VM thread.
- **Container/cgroup CPU**: CPU usage compared against **CPU quota**, `cpu.max`, throttle time, and throttled periods. A pod limited to 1 CPU can be severely throttled even while the host still has many idle cores.
- **JFR `jdk.CPULoad`**: periodic event containing JVM user/system and machine ratios; use those fields **as a time-series measurement**, do not count events to conclude CPU percentage.
- **JFR `jdk.ThreadCPULoad`**: per-thread CPU usage information over the measurement period; do not treat a single event or `ExecutionSample` percentage as exact CPU-ns per method.

Reference formula for a measurement interval:

```text
Process CPU cores used ≈ Δ(process CPU time in seconds) / Δ(wall time in seconds)

If in 10 seconds the process gains 18 CPU-seconds:
    average ≈ 1.8 logical CPUs busy during that interval
```

The figure above is **only a conversion from CPU time to average core usage**; you cannot conclude that 1.8 cores were occupied evenly across all 10 seconds or that the system reached 180% under every dashboard's convention. Always read the valid core/quota count and the measurement source's sampling interval.

### 3.2. Easily Misread Signals

| Signal | Priority Interpretation |
| --- | --- |
| Host CPU 95%, JVM process 8% | Inspect other processes or kernel CPU; do not rush to optimize Java |
| JVM uses ~2 cores while pod has a 2-core quota | Possible saturation; check throttling, backlog, p95/p99 |
| JVM CPU high right after startup, drops after a few minutes | Possible JIT warmup, class loading, GC, and caches; not yet enough to call an abnormal hot loop |
| JVM CPU low, request latency high, threads mostly `WAITING` | Check connection pools, locks/parks, socket I/O, downstream instead of treating as a CPU bottleneck |
| A `RUNNABLE` thread in one dump | Does not prove it uses 100% CPU; Java thread state is not a CPU-time measurement |

For containerized applications, compare CPU usage, quota, and `nr_throttled`/`throttled_usec` or the equivalent metric for your cgroup version; formats differ between cgroup v1 and v2. If quota metrics are missing, note the uncertainty explicitly and avoid concluding the system has spare CPU just by looking at host CPU.

## 4. Lock Down the Same Time Window and JVM

Before collecting evidence, record at least: service name, host/pod, PID, **startup time**, JDK vendor/build, deployment method, time window of abnormal p95/p99 or throughput, process and container CPU, and resolution/sampling interval.

Hypothetical example:

```text
Service/pod:        orders-api / orders-7b8...
JVM:                Java 21, PID 3187 (verify on target)
Symptom UTC:        2026-10-29T10:15:20Z .. 10:16:50Z
CPU series:         process + machine + container, 10 s buckets
Stack snapshots:    10:15:30, 10:15:34, 10:15:38, 10:15:42Z
JFR recording:      covers 10:14:30 .. 10:17:30Z
Control window:     10:12:00 .. 10:13:30Z, comparable load
```

**This is illustrative data**, not an observed incident. Timestamps must be normalized to the same timezone/UTC and checked for NTP/clock skew. A dashboard storing 10-second buckets is not precise enough to claim a method started running exactly 5 ms before an alert.

When a JVM restarts, PIDs may be reused. Do not stitch stack dumps/JFR from two different JVMs into a single measurement without clearly marking restart and startup/warmup boundaries.

## 5. Collect CPU Metrics Alongside Thread Dumps on Linux

### 5.1. Verify the Exact Process and Measure CPU

`jcmd` must attach to the JVM as the right user/machine/namespace (in containers, the PID seen from the host may differ). Replace **`3187`** with the actual PID; the examples below are only for authorized observation environments:

```bash
jcmd -l
jcmd 3187 VM.version
jcmd 3187 VM.uptime
ps -p 3187 -o pid,ppid,etime,pcpu,comm
```

View per-OS-thread usage on Linux while the symptom is still active:

```bash
top -H -p 3187
```

Or print the TID table (`ps` CPU percentage is **a statistic per `ps`'s convention/window**, not guaranteed instantaneous):

```bash
ps -L -p 3187 -o pid,tid,psr,pcpu,stat,comm
```

Pick moments when `top` shows hot threads to capture the **OS TID** and timestamp. A JVM has many threads serving different roles; not every OS thread is a request-handling Java thread.

On a host or container under load, avoid running tools too frequently or capturing excessively large outputs. You can capture 3–6 snapshots spaced a few seconds apart during a sustained spike, depending on service sensitivity and thread count.

### 5.2. Capture Multiple Timestamped Thread Dumps

Use commands **supported by JDK 21**:

```bash
jcmd 3187 help Thread.print
jcmd 3187 Thread.print -e -l
```

- `-e`: extended thread information.
- `-l`: `java.util.concurrent` locks/ownable synchronizers information.
- `Thread.print` has **Impact: Medium**, depending on thread count; taking many dumps also incurs cost. Space them wide enough to observe state changes without turning the investigation into a new bottleneck.

Linux shell example **intentionally capturing four snapshots**, with external timestamps around each command:

```bash
umask 077
mkdir -p ./cpu-evidence

for index in 1 2 3 4; do
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "./cpu-evidence/stack-$index.time"
  jcmd 3187 Thread.print -e -l > "./cpu-evidence/stack-$index.txt"
  sleep 3
done
```

Run in a safe directory with write permissions and sufficient disk space; update the PID before running, and check `jcmd` exit codes and non-empty files. Each snapshot reflects only **one instant**; recording `date` before invoking the command also includes attach/dump latency error. If tighter bounds are needed, record timestamps both before and after to bracket the error window.

**Do not paste full `Thread.print` output into public tickets.** Stacks can expose packages, classes, file paths, and internal details. Keep raw files secured, label version/instance/UTC, and restrict access.

### 5.3. From OS TID to `nid` in a Thread Dump

For many **HotSpot platform threads on Linux**, the thread dump line includes `nid=0x...`, which is the native thread ID in hexadecimal; `top -H`/`ps -L` normally displays TIDs in decimal. Illustrative example:

```bash
printf '0x%x\n' 12345
```

Output of the command above:

```text
0x3039
```

If the OS TID is `12345`, search for `nid=0x3039` in the dump **from the same JVM and matching timestamp**, then read the thread name and stack. Do not confuse `nid` with `#...`, `tid=0x...`, or Java's `Thread.getId()/threadId()`; those are different identifiers. IDs can be reused after a thread exits.

With Java 21 **virtual threads**, many virtual threads do not own a fixed OS TID because they multiplex across carriers. Traditional `Thread.print` **does not fully display all virtual threads**. If your task requires inspecting virtual threads, you can use JDK 21's `jcmd <PID> Thread.dump_to_file -format=json <path>`, though its contents/locks/monitors differ from traditional dumps. Never try to "map a virtual thread to a permanent OS TID."

### 5.4. Read Thread States Without Over-Interpreting

| State in Dump | Meaning to Check | What Not to Claim |
| --- | --- | --- |
| `RUNNABLE` | Java thread is runnable or executing; stack shows current location, possibly in a native call | Does not mean the thread is occupying a CPU core |
| `BLOCKED` | Waiting to enter a `synchronized` monitor | Not a CPU-bound loop just because many threads are BLOCKED |
| `WAITING` | Waiting indefinitely via a Java mechanism, e.g., `Object.wait`, `LockSupport.park` | Does not automatically mean a leak or deadlock |
| `TIMED_WAITING` | Bounded wait such as `Thread.sleep`, timed park | Not the cause of high CPU without other evidence |
| `NEW` / `TERMINATED` | Not yet started / already finished (if observable by the tool) | Not a thread currently scheduled busy by the OS |

For `RUNNABLE`, **correlate OS thread CPU** and **call stack repetition** across at least several snapshots. Do not count every `RUNNABLE` line and multiply it out as "number of busy cores."

## 6. Why Are Multiple Stack Snapshots Needed?

A thread dump is a slice lasting a few milliseconds or longer. It can easily catch a normal instruction momentarily running; at the same time, it can **miss** hot code when stacks change rapidly or when a thread was momentarily descheduled by the OS.

For example, a hypothetical sequence for the same thread:

```text
T1  cpu-hot-A  RUNNABLE  PriceCalculator.aggregate()
T2  cpu-hot-A  RUNNABLE  PriceCalculator.aggregate()
T3  cpu-hot-A  RUNNABLE  PriceCalculator.aggregate()
T4  cpu-hot-A  RUNNABLE  PriceCalculator.aggregate()
```

If the OS shows the corresponding TID steadily using CPU and JFR has many `ExecutionSample`s in `PriceCalculator.aggregate`, the hypothesis that this method **consumes substantial execution time during that window** becomes much stronger. However, if you only have one snapshot and `top` shows low CPU, that is not yet proof.

Another sequence:

```text
T1  worker-1  RUNNABLE      processOneBatch()
T2  worker-1  TIMED_WAITING Thread.sleep()
T3  worker-1  WAITING       LinkedBlockingQueue.take()
T4  worker-1  RUNNABLE      processOneBatch()
```

This could be a normal processing loop combining work and waiting; "seeing `processOneBatch` twice" does not prove an infinite loop. Check **CPU usage**, execution frequency, and JFR samples over the same window.

**How to correlate snapshots:**

1. Group by **JVM identity + OS TID/nid + thread name** when available; do not rely solely on thread names, which can collide.
2. Attach timestamps/UTC; confirm they overlap the high-CPU window.
3. Compare **top-down stack patterns and call chains** (top frames can change due to inlining/JIT, so also watch caller frames and hot packages).
4. Treat "appeared in `k` of `n` snapshots" **as an indicative signal**, not "k/n % CPU".
5. Distinguish multiple threads in the same code region from one thread looping there; both can raise CPU, but the fixes differ.
6. Look for disconfirming evidence: when CPU drops, is that stack still present? Across different recordings or loads, does the same pattern appear?

If an application has 100,000 virtual threads, taking many full dumps is unsuitable; use JFR sampling and scoped metrics first, and capture virtual-thread dumps only when clearly justified.

## 7. Collect JFR `ExecutionSample` in the Exact High-CPU Window

### 7.1. Create a Recording on a Running JVM (Java 21)

Verify first that the target JVM has JFR and attach permissions; **start the recording while the symptom is reproducing**, rather than waiting until the incident ends and expecting historical data. Example:

```bash
jcmd 3187 JFR.check
jcmd 3187 JFR.start name=cpu-investigation \
  settings=profile duration=90s \
  filename=/srv/diagnostics/cpu-investigation.jfr
```

`settings=profile` selects a profile that captures more execution samples than `default` on JDK 21; overhead is generally higher, so keep the window bounded. The path **belongs to the JVM's filesystem** and must be writable; the name and PID are examples to replace. If a recording already exists, do not blindly reuse the same name; check `JFR.check` first.

When you need to export data early while keeping the recording running:

```bash
jcmd 3187 JFR.dump name=cpu-investigation \
  filename=/srv/diagnostics/cpu-partial.jfr
```

Save the `.jfc` settings, start/end times, JVM build, checksum, and event types. `JFR.dump` exports data collected so far; it does not produce events from before the recording started.

Once you have the file (in an accessible environment):

```bash
jfr summary cpu-investigation.jfr
jfr metadata --events jdk.ExecutionSample,jdk.CPULoad,jdk.ThreadCPULoad cpu-investigation.jfr
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad cpu-investigation.jfr
jfr print --stack-depth 64 --events jdk.ExecutionSample cpu-investigation.jfr
```

**Comparison caveat:** `jfr print` filters by **event type**, and does not automatically restrict to a user-specified time interval. If the file spans multiple periods, select the interval in JDK Mission Control or build a time filter using `jdk.jfr.consumer`. `jfr summary` counts events across **the entire recording**; do not take whole-file counts to draw conclusions about a single 1-minute incident.

### 7.2. Meaning of the Three Events

| JFR Event | How to Read | Interpretation Errors to Avoid |
| --- | --- | --- |
| `jdk.CPULoad` | Inspect `jvmUser`, `jvmSystem`, `machineTotal` ratios **by timestamp** to see how busy JVM and host are | Counting 10 CPU load events and claiming the JVM used 10 CPUs |
| `jdk.ThreadCPULoad` | Inspect thread CPU load/identity by event and measurement interval; check the role of hot workers | Directly treating `% ExecutionSample` as thread CPU load |
| `jdk.ExecutionSample` | Inspect `eventThread`, `stackTrace`, `startTime`; group by stack/method/time over the **same window** | Treating each event as one method invocation or exact CPU milliseconds |

In JDK 21, `jdk.ExecutionSample` is **sampling** execution locations rather than tracing every call. Threads waiting on locks, sleeping, or in I/O may be sampled less often; to find waiting reasons, inspect `jdk.JavaMonitorEnter`, `jdk.ThreadPark`, `jdk.SocketRead`, and corresponding events **if enabled in the recording**. A method appearing frequently in samples suggests a **hot path** under sampling conditions, not proof by itself that it caused request timeouts.

`default`/`profile` configuration, intervals, stack depth, and workload affect sample counts. Two recordings with different sample counts should not have raw counts compared directly if duration and sampling frequency differ.

### 7.3. Analyzing in JDK Mission Control (JMC)

JMC may be installed separately. Tab names vary by version, but core steps include:

1. Open the `.jfr` file and verify the JVM/instance and recording interval.
2. Select the **exact high-CPU time range** on the timeline; align with timezone and monitoring resolution.
3. Check **CPU usage** for JVM/machine; if JVM CPU is low, drop the "CPU-bound Java code" hypothesis.
4. Open **Method Profiling / Hot Methods / Call Tree** to inspect stack sample proportions; distinguish **self/top method** from **inclusive call tree**.
5. Group by **thread**, separate business workers from compiler/GC/VM threads, and flag methods or libraries where samples cluster.
6. Switch to a normal baseline control window with the same settings; check whether the same method dominates samples even when CPU is low.
7. Check `Compiler`/`Class Loading`/`GC` events and heap/threads when CPU rises near startup/deploy.

For instance, JIT can **inline** methods into callers, changing stack profiles, or optimize loops over time. Do not rely rigidly on the order of a single top frame when snapshots/JFR come from different times or different JVM warmup states.

## 8. Combining Three Sources into One Evidence Table

Do not analyze the three sources as three separate stories. Align them on the same **UTC time, service instance, JVM, and thread group**:

| Window / Signal | Process/Container CPU | Multiple Thread Dumps | JFR ExecutionSample | Working Conclusion |
| --- | --- | --- | --- | --- |
| CPU rise under load | Near quota, TID A uses high CPU | `nid=A` RUNNABLE, repeating `calculate()` frame | Many samples on same code path in window | Strong `calculate()` CPU-bound hypothesis; check JIT/GC |
| High host CPU, low JVM CPU | Machine CPU high, JVM process steady | Business threads mostly WAITING | Few application samples | Check other processes/kernel or quota metrics |
| JVM CPU spike at startup | Process CPU high for first 1–2 minutes | Many class loader/compiler frames (not always visible in Java dumps) | Many startup paths and JIT samples | Possible warmup; re-compare after stabilization |
| High p99, low JVM CPU | Low CPU | Threads waiting on pool/network | Hot-method samples unfocused | Prioritize I/O, contention, pools; inspect JFR blocking events |
| High JVM CPU, few business samples | Process busy | Business threads unremarkable in dumps | Few Java business-code `ExecutionSample`s | Check JIT compiler, GC workers, native CPU, sample settings |

**All rows are illustrative scenarios**, not a real dataset; gather additional logs, load data, and reproduction conditions before changing code.

### 8.1. Do Not Mis-Add Quantities

- `jdk.CPULoad` holds **percentage/ratio values** over time; do not sum those values as CPU-seconds.
- One sample does not carry the execution duration of the corresponding Java frame. Samples across multiple threads and intervals must be **normalized by valid sample count**.
- 60% of samples in `PriceCalculator` **does not mean** the method accounts for exactly 60% of CPU time or 60% of request latency.
- An **inclusive** method in a call tree can appear in many samples because it calls child methods; **self** is when execution was sampled directly in that method. Do not add both percentages from the same stack as two independent CPU sources.
- OS thread CPU can include native/JNI or runtime time; JFR `ExecutionSample` is not a comprehensive native profiler.
- If a host has 8 logical cores and JVM CPU equals 1 core, you cannot call it 100% of the total machine just because `top` displays 100%.

### 8.2. From Correlation to a Testable Hypothesis

Hypothetical investigation summary:

```text
Symptom:    p99 rises alongside process CPU from 0.8 to 2.0 cores
OS:         TIDs 8142/8144 are two busy threads, same JVM/PID
Dumps:      matching nids show computeQuote() in 4/5 snapshots
JFR:        within the window, most sampled stacks for those two threads
            contain computeQuote() or its callers
Controls:   GC pauses low; minimal JIT compilation in window
Hypothesis: computeQuote() performs redundant computation under load
Test:       measure per-request time and throughput before/after change
```

This is an **example of reasoning**, not an actual finding. Verify whether that method is simply a legitimate hot path due to high request volume; reducing work while breaking logic is not a valid optimization.

A credible test must match **the same workload, core/quota count, JDK/GC flags, input data, and warmup state**; report throughput, p95/p99, CPU-seconds/request, and error rate, not merely a cleaner-looking flame graph.

## 9. Java 21 Lab: Two CPU Workers and One Sleeper

The lab below intentionally creates **two continuously computing platform threads** and one thread that only sleeps. This lets you observe the difference between CPU time, thread state across multiple dumps, and `ExecutionSample` distribution without needing an external application.

Create **`CpuCorrelationLab.java`**:

```java
public class CpuCorrelationLab {
    private static volatile boolean stop;
    private static volatile long sink;

    public static void main(String[] args) throws Exception {
        int seconds = args.length == 1 ? Integer.parseInt(args[0]) : 25;
        if (seconds < 1 || seconds > 120) {
            throw new IllegalArgumentException("seconds must be 1..120");
        }
        stop = false;
        Thread cpuA = new Thread(CpuCorrelationLab::burnCpu, "cpu-hot-A");
        Thread cpuB = new Thread(CpuCorrelationLab::burnCpu, "cpu-hot-B");
        Thread sleeper = new Thread(() -> {
            while (!stop) {
                try {
                    Thread.sleep(250);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }, "idle-sleeper");

        cpuA.start();
        cpuB.start();
        sleeper.start();
        System.out.println("READY: two CPU workers and one sleeper");
        Thread.sleep(seconds * 1000L);
        stop = true;
        cpuA.join();
        cpuB.join();
        sleeper.join();
        System.out.println("DONE");
    }

    private static void burnCpu() {
        long x = 1;
        while (!stop) {
            x = mixedWork(x);
            sink = x;
        }
    }

    private static long mixedWork(long x) {
        for (int i = 0; i < 20_000; i++) {
            x ^= (x << 13);
            x ^= (x >>> 7);
            x ^= (x << 17);
        }
        return x;
    }
}
```

This is a standalone program using stable Java APIs available in Java 17+ and **compiles/runs on JDK 21** without preview flags. It only generates local CPU load; **do not run it on production machines** or nodes with tight CPU quotas.

**Terminal A:** compile and start with a 25-second JFR profile:

```bash
javac CpuCorrelationLab.java
java -XX:StartFlightRecording=filename=cpu-lab.jfr,settings=profile,dumponexit=true \
  CpuCorrelationLab 25
```

The program keeps both workers busy for about 25 seconds, then stops them. On normal completion, stdout **printed by the code itself** is:

```text
READY: two CPU workers and one sleeper
DONE
```

The JVM/JFR may print **its own recording startup messages**, so total terminal output may contain more than these two lines. Output files can vary widely in JFR event counts depending on machine and load. The `.jfr` file is written in the working directory; ensure sufficient disk space and permissions.

**Terminal B:** while `READY` is visible, identify the lab's actual PID, measure CPU, and take snapshots. The example below uses `3187` as a **placeholder**, not a fixed PID for the lab:

```bash
jcmd -l
top -H -p 3187
jcmd 3187 Thread.print -e -l
```

Take 3–5 dumps at different times (using the method in Section 5.2). Verify that `cpu-hot-A` and `cpu-hot-B` tend to appear repeatedly in `mixedWork`/`burnCpu`, while `idle-sleeper` is typically in `Thread.sleep`/`TIMED_WAITING`. Exact counts and specific frames are **not guaranteed** due to snapshot timing and JIT inlining.

**After Terminal A finishes**, inspect the recording:

```bash
jfr summary cpu-lab.jfr
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad cpu-lab.jfr
jfr print --stack-depth 64 --events jdk.ExecutionSample cpu-lab.jfr
```

In JMC, open `cpu-lab.jfr`, select the 20–25 seconds when the lab was active, and open Hot Methods/Call Tree. Explain why the two compute threads appear frequently in samples, whereas `idle-sleeper` should not be considered a CPU hotspot merely because it stayed alive just as long.

**Challenge exercise:** re-run the lab with arguments 10 and 40 seconds using the same JDK/JFR settings. Compare **sample proportions by call path** instead of raw sample counts; compare CPU in cores, warmup, and duration. If the machine only has 1 core/quota, the two CPU workers will **contend** for CPU time, and total process CPU may not reach 2 cores. Do not use this lab as a real application benchmark.

## 10. When Data Contradicts Itself: Diagnose Before Fixing

### 10.1. OS Reports High CPU, JFR `ExecutionSample` Is Sparse

Things to check:

- Did you target the right recording/JVM/PID and window? Is JFR using `settings=default` (fewer samples) or is the event disabled?
- Does that CPU come from **GC workers or JIT compiler native threads** that business-Java `ExecutionSample`s under-represent?
- Is CPU spent in JNI/native code, native crypto, codecs, external libraries, or the kernel? A Java stack at snapshot time might only show the native/Java wrapper call.
- Was the sampling duration too short, the method very fast, JIT-inlined, or affected by event drops/truncation or sampling configuration?
- Are `-Xint`, a debug build, unusual JIT flags, or another concurrent profiler altering the profile?

Use per-thread CPU metrics and JFR Compiler/GC events to pick a direction. If you need **native** hotspots, consider an OS profiler such as `perf` on Linux (when permitted and compatible with kernel/JDK), because JFR Java execution samples do not replace all native stacks.

### 10.2. Stack Snapshots Repeatedly Show `RUNNABLE`, Yet CPU Is Low

`RUNNABLE` is not a CPU consumption metric. Threads can be runnable yet **not scheduled onto a CPU by the OS**, waiting in a native syscall, or throttled by a CPU quota. Check per-thread CPU time in the same interval, throttling, logical CPU count, thread scheduling, and sampling. Thread dumps may simply catch a brief running phase while the thread spends most of its time waiting.

### 10.3. JFR Shows Many Samples in Startup Code

Class loading, bytecode verification, JIT compilation, method profiling/warmup, code cache, and GC can cause temporary high CPU. To distinguish:

1. Compare CPU across **startup vs. steady-state** and deployment timestamps.
2. Inspect `jdk.Compilation`, `jdk.ClassLoad`/class loading stats, and GC events **if present** in the recording (do not assume all are enabled).
3. Compare business-code sample counts in a post-warmup window; if the hotspot disappears, optimizing startup-path code may require different criteria than steady-state hot paths.
4. Do not label every stack in compiler/JDK internals a "JIT bug." Only conclude that with evidence of compilation activity, matching thread CPU, and SLO impact.

### 10.4. High Latency, Normal CPU

Use JFR duration events and tracing: `jdk.JavaMonitorEnter`, `jdk.ThreadPark`, `jdk.SocketRead`, `jdk.FileRead`, pool queues, and database latency. These events have their own thresholds and settings, so absence does not prove absence of waiting. JFR execution samples are **biased toward executing threads**; a request waiting long on I/O may generate almost no hot samples even though users experience severe slowness.

### 10.5. Top Hot Methods Shift Between Measurements

Sampling has variance; with small sample counts, method rankings fluctuate easily. Choose a sufficiently long window, record sample counts, repeat measurements, and inspect **call trees, callers, and method groups** rather than a single top frame. If there are two phases (e.g., parse then calculate), aggregating across the whole recording blurs each phase. Split by symptom phases alongside CPU metrics.

## 11. Production Investigation Cross-Check Checklist

| Evidence | Must Capture | Used to Verify |
| --- | --- | --- |
| **CPU timeline** | Host CPU, JVM process, cgroup quota/throttling, same UTC window and buckets | Whether real JVM saturation exists |
| **Per-thread CPU** | OS TID, %CPU or CPU-time delta, timestamp, PID/host | Which OS thread is hot |
| **Snapshot series** | 3–6 timestamped thread dumps, `nid`, stack, and state | Which frames repeat during the spike |
| **JFR recording** | `.jfr` file, recording interval, JDK build, JFR settings/profile, checksum | Sampled data and event ratios |
| **JFR ExecutionSample** | Event count in interval, thread IDs, stacks, hot methods/call tree | Concentration of sampled execution |
| **Supporting JVM runtime** | GC pauses, compiler activity, class loading when events exist | Whether JIT/GC/warmup is confounding the picture |
| **Application** | Request rate, endpoint, trace/span, p95/p99, error rate, deploy | How the hot path maps to user impact |
| **Control comparison** | Normal window with same workload/config and post-change measurement | Whether the hypothesis holds beyond one observation |

Not every service can collect every column. When data is missing, **explicitly mark what is missing** and the confidence level of the conclusion; avoid filling in unmeasured TIDs, CPU %, stacks, or sample counts.

## 12. Common Reasoning Errors

**"Seeing `RUNNABLE` means CPU is occupied."** False: Java thread state is not a CPU profiler. Read OS/JFR CPU time.

**"One thread dump tells you which method uses the most CPU."** False: it is only a snapshot; you need a series of snapshots and sampling in the symptom window.

**"60% of JFR samples means the method uses exactly 60% of CPU."** False: that is a sample proportion of recorded events, subject to sampling bias and filter conditions.

**"Host CPU is 99%, so the Java process is the culprit."** Not certain: check CPU per process and container.

**"16 `RUNNABLE` threads means 16 cores are definitely in use."** Invalid inference; runnable threads can exceed core count and contend for CPU scheduling.

**"The top frame of a sample is the root method causing load."** Not necessarily: check the call chain, inclusive/self samples, JIT inlining, and workload context.

**"No `ExecutionSample`s means no CPU was used."** Not necessarily: recording settings, sample interval, native/GC/compiler CPU, and missing data can all explain it.

**"Optimizing the hot method fixes p99."** Only true after proving critical-path linkage and re-measuring CPU-seconds/request, latency, throughput, and correctness under the same load.

## 13. Self-Assessment Exercises

1. A JVM on an 8-logical-core host uses 1.5 CPU-seconds in one second. Explain what "~1.5 busy cores" means, and why `top`'s `%CPU` can differ from a dashboard normalized across 8 cores.
2. Take four snapshots around the high-CPU period of the lab. Locate `cpu-hot-A/B`, pick a TID from `top -H`, convert it to hex, and match `nid`. Explain why OS TID and Java thread ID are not the same kind of ID.
3. Open `cpu-lab.jfr`; inspect `jdk.CPULoad` and samples of `mixedWork`/`burnCpu`. Repeat the lab with `10` and `40` seconds, compare **sample proportions**, and explain differences caused by warmup/JIT/sampling.
4. In a hypothetical scenario, host CPU is 90%, JVM is 12%, request p99 rises, and most threads are `WAITING`. Write the primary hypothesis and metrics to collect instead of tuning a hot Java method.
5. A JVM has 70% of sampled stacks in `jsonEncode`, yet process CPU is low and QPS is high. Explain why `jsonEncode` can dominate samples without yet warranting optimization.
6. Compare GC/JIT CPU in the minute after deployment against ten minutes later. Design a measurement plan to avoid misdiagnosing warmup as a "CPU leak."

**Completion checklist:** identified the right JVM and UTC window; collected process/container CPU + OS TIDs; captured multiple repeated dumps over time; captured a JFR profile with `ExecutionSample` and CPULoad; aligned stacks/threads over the same phase; checked JIT, GC, class loading, and waiting; stated conditional conclusions, verification tests, and before/after metrics.

## 14. Primary References (Java 21)

- [Oracle JDK 21 — `jcmd` command: `Thread.print`, `JFR.start`, `JFR.check`, `JFR.dump`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — `jfr` command: `summary`, `print`, `metadata`, `view`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK 21 — Virtual Threads: virtual-thread dump and differences from platform threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Oracle JDK 21 — JFR package and event configuration](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Oracle JDK 21 — Diagnostic Tools and thread dump collection limits](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
