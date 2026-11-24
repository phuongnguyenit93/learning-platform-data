# 17.1. Distinguishing High CPU of a Process, Single Thread, GC, or Compiler

## Objectives

When a Java application uses high CPU, you need to answer **at what level CPU is increasing**, **which threads are actually consuming it**, and **whether the work belongs to application code, the garbage collector (GC), or the JIT compiler**. A high process CPU value alone is not enough to conclude there is an infinite loop; a `RUNNABLE` thread alone is also not enough to prove it is consuming CPU. Accurate analysis requires connecting **OS measurements over a time interval** with **thread dumps/JFR/GC logs/JIT compilation**, while also considering host or container CPU limits.

This lesson uses **HotSpot JDK 17+ on Linux** for its examples; other OS tools (Windows/macOS), other collectors, or newer JDKs may change thread names, counters, and display formats. Example numbers in this lesson are labeled as illustrative, not fixed measurements from a real machine.

After this lesson, you will know how to:

1. Distinguish **process CPU**, **per-native-thread CPU**, **CPU from GC workers**, and **CPU from C1/C2/JIT compiler threads**.
2. Calculate CPU usage from **the delta of CPU time and wall time**, and understand why a process can show more than 100%.
3. Use `top -H`/`pidstat -t`/`ps -L` and then map **OS TID** to `nid=0x...` in a HotSpot thread dump.
4. Distinguish GC **pause/elapsed time** from **GC worker CPU time**, and JIT **compilation events** from **actual CPU used**.
5. Collect JFR/GC logs, correlate timestamps, and choose an appropriate fix without blind tuning.

## 1. How Does CPU Time Differ from Wall-Clock Time?

**Wall time** is elapsed clock time. **CPU time** is the amount of time a CPU actually spends executing instructions of a process/thread (typically including user time and system/kernel time), accumulated across the slices when the scheduler grants it CPU. A thread that is sleeping, waiting for I/O, or waiting on a lock can lengthen request duration while consuming little CPU.

With two samples of the **same process** separated by `Δwall` seconds:

```text
CPU% per logical CPU = 100 × Δprocess_cpu_time / Δwall_time

Normalized CPU% across N logical CPUs = 100 × Δprocess_cpu_time / (N × Δwall_time)
```

The units of CPU time and wall time must be consistent. Similarly, for a thread:

```text
thread_CPU% per logical CPU = 100 × Δthread_cpu_time / Δwall_time
```

**Hypothetical** example over a 10-second window:

- The process uses 24 seconds of CPU time: **240% of one core**; that is an average load equivalent to 2.4 logical CPUs.
- On a machine with 8 logical CPUs: the corresponding figure is **30% of total 8-core capacity** if sampled over the exact window and without a quota.
- One thread uses 8 seconds of CPU in the same window: **80% of one core**. Other threads combined may use 16 seconds of CPU.
- A process at 240% **does not mean one thread is using 240% of one core**; multiple threads run concurrently across multiple CPUs.

**Tool caveat:** `top` has modes normalized per core or by total CPU (Irix/Solaris mode), `ps %CPU` is often the ratio of CPU time over the process/thread lifetime rather than a 1-second window, and Task Manager and Kubernetes use different denominators. Do not directly compare two percentages from incompatible tools or denominators.

**High load ≠ CPU throttling:** a container with a 2-core quota on a 32-core host can be throttled when the process needs 4 cores. If you only look at "12.5% of host", you will miss that the container has exhausted its quota. Check `cpu.max`/`cpu.stat` (cgroup v2), Kubernetes requests/limits, and throttled time.

## 2. Four Layers Easily Conflated

| Observation Layer | What Is Being Measured? | Reliable Ways to Read | What the Metric Does Not Prove on Its Own |
| --- | --- | --- | --- |
| **Process CPU** | Total CPU time of the entire JVM process: app threads + VM/GC/JIT/native activity in the process | `top -p PID`, `pidstat -p PID`, JMX process CPU, JFR `jdk.CPULoad` | Does not distinguish whether the culprit is application, GC, or compiler. |
| **Thread CPU** | CPU time of a specific OS thread | `top -H -p PID`, `pidstat -t -p PID`, or ThreadMXBean for **Java platform threads** | Thread name or `RUNNABLE` state is not enough to conclude its CPU usage over the entire window. |
| **GC CPU** | CPU time spent by GC/VM workers performing GC work | GC logs with user/sys/real when available, JFR GC, OS thread CPU, collector phase data | Total GC pause or total GC wall time does not automatically equal CPU time consumed. |
| **Compiler CPU** | CPU used to JIT-compile/optimize Java methods, typically by C1/C2 compiler workers | OS per-thread CPU + name/stack, JFR compilation, `jcmd Compiler.queue`, compilation logs | A method being compiled many times does not by itself tell you total compiler CPU. |

The layers are not completely separate: **GC and the compiler are both included in process CPU**; thread CPU is how process CPU is attributed to individual threads if the tool has full visibility. **An application thread** can also spend time running JDK library code, native/JNI code, or assisting GC work, depending on the collector and timing. Do not assume you can identify every CPU cycle accurately from thread names alone.

## 3. Step 1 — Identify the Right JVM/PID and CPU Window

Example using PID **`12345`** on Linux:

```bash
jcmd -l
top -p 12345
pidstat -p 12345 1 5
```

- `jcmd -l` lists JVMs that the attach tool can discover; inside Docker or another namespace, the JVM may not appear. Use OS tools to get the exact PID if needed.
- `top -p` is useful for quick observation; `pidstat -p 12345 1 5` (`sysstat` package) provides 5 samples at 1-second intervals, convenient for seeing whether the CPU increase is sustained or just a spike.
- High **JVM CPU** with low **host-wide CPU** may simply be one JVM using a few cores on a large machine. Conversely, if host CPU is high while JVM CPU is low, inspect other processes.
- Record **timestamp, PID, Java version, collector, workload, and container quota**; do not combine data before and after a restart into a single window.

If `pidstat` is not installed, you can take multiple `top`/equivalent OS metric samples. On Windows, use Task Manager/Process Explorer/PerfMon; do not use Linux `/proc` commands.

**CPU analysis must have a time dimension:** a single `ps -p 12345 -o %cpu` snapshot is only a clue; it is not enough to say which thread burned CPU right when latency rose.

## 4. Step 2 — Find Which Native Thread Actually Uses CPU

### 4.1. Measure by OS Thread ID (TID)

```bash
top -H -p 12345
pidstat -t -p 12345 1 5
ps -L -p 12345 -o pid,tid,pcpu,stat,comm
```

- `top -H` displays the threads of a process, often showing a `PID` column, though in thread mode that value is actually each thread's **TID**.
- `pidstat -t` provides CPU history per TID across measurement intervals, avoiding misidentifying a thread just because it happened to be running during a single snapshot.
- `ps -L` is useful for verifying PID/TID, state, and name, but `pcpu` uses a lifetime-based calculation, so do not use it as a 1-second CPU sample without verifying its semantics.
- One thread running near **100% of one core** across multiple samples may be a hot loop or CPU-bound task; many threads at 20–40% each can produce very high total process CPU.

Pick the **top 2–3 consecutive TIDs**, and record their percentages and timestamps. Note that TIDs can be reused after a thread exits; matching data across distant intervals without checking thread lifetime is risky.

### 4.2. Match Decimal OS TID to Hexadecimal `nid`

HotSpot `Thread.print` may print a Java thread like:

```text
"busy-worker" #35 prio=5 os_prio=0 cpu=5412.00ms elapsed=6.31s tid=0x00007f... nid=0x3039 runnable
   java.lang.Thread.State: RUNNABLE
        at demo.Worker.compute(Worker.java:42)
```

This is an **illustrative example**; names, fields, and formatting vary by JDK and OS. `nid=0x3039` is the **native thread ID in base 16 (hexadecimal)** corresponding to **12345** in decimal. This example only illustrates the conversion; the JVM PID `12345` in the commands above happens to share the same digits as the sample TID because an easy-to-remember number was chosen, not as a rule.

Convert a decimal TID to hex in Bash:

```bash
printf '0x%x\n' 12345
```

Output of the `printf` command for the exact sample number:

```text
0x3039
```

Or in PowerShell:

```powershell
'{0:x}' -f 12345
```

Take a thread dump:

```bash
jcmd 12345 Thread.print -l
```

**Distinguish three IDs:**

- **PID** is the JVM process ID (in the observed OS namespace).
- **Linux TID/LWP** is the native thread ID inside the process, used to match against HotSpot **`nid`**.
- **Java Thread.getId()/ThreadMXBean thread ID** is the Java thread identifier, **not the Linux TID**. Do not use it directly to search for `nid` without a valid mapping.

If a TID does not appear in the Java thread dump, it may be a VM/GC/JIT/native thread that is not printed as a Java application thread, or the thread has already exited, or the dump and OS stats were taken at different times or in different PID namespaces. OS threads are an important signal even when the Java thread dump does not list all internal workers.

### 4.3. Do Not Use `RUNNABLE` as a CPU Measurement

`RUNNABLE` in a Java thread dump can include threads currently executing, ready to run, or performing native/I/O operations depending on where they block. A `WAITING`/`TIMED_WAITING` thread usually does not consume much CPU while sleeping, but its state at one instant does not tell you its CPU usage over the preceding few seconds.

A better way to correlate:

1. OS measurements showing **increasing CPU time** for a TID in the exact window.
2. Two or three thread dumps near that window showing which application/JVM stacks are involved.
3. JFR/async-profiler or sampled method profiles showing which functions appear most frequently when running on CPU.
4. Combine all three with workload/latency to avoid blaming a transient thread.

A stack showing `java.util.HashMap` does not prove `HashMap` has a bug: it is only where execution happened to be. You need to examine the callers and sample frequency/CPU.

## 5. Step 3 — Distinguish GC CPU from GC Pause

GC can consume CPU during **stop-the-world (STW)** pauses and/or **concurrent phases**. An STW pause is **the time the application is paused according to GC measurement boundaries**, whereas GC CPU time is **the total CPU time consumed by the GC workers**.

Hypothetical example:

- A 100 ms STW phase with **4 GC workers** executing an average of 80 ms of CPU each: total GC CPU time is approximately **320 ms**, even though wall pause is only **100 ms**.
- A concurrent GC phase can consume CPU while the application continues running, increasing process CPU while STW pauses remain very short.
- Do not infer **GC CPU% = total GC pause / window duration**, and do not add all concurrent phase wall-time into STW.

### 5.1. Enable GC Logging

For a freshly started JVM, for example HotSpot JDK 17:

```bash
java -Xms256m -Xmx512m \
  -Xlog:gc*=info:file=gc.log:time,uptime,level,tags \
  -jar app.jar
```

In the log, look for **GC frequency/types**, STW pauses, concurrent phases, heap before/after, and **CPU times user/sys/real** lines if emitted by the collector/JDK.

- **`user`**: total user CPU time of the relevant threads under the log's accounting.
- **`sys`**: kernel/system CPU time.
- **`real`**: wall-clock duration of that phase/event.
- **`user + sys` greater than `real`** can be completely normal when parallel GC uses multiple workers. Do not mistake this for a log bug.
- With concurrent collectors, individual timing lines also do not necessarily represent *all* GC CPU of the process. You need to understand each phase's scope, workers, and measurement source.

Not every GC log includes complete CPU information, especially with different tags/levels. If `user/sys/real` is missing, check the log configuration/JDK instead of guessing from pause times.

### 5.2. Use JFR to Cross-Check GC

If a recording was captured over the right interval:

```bash
jfr summary diag.jfr
jfr print --events "jdk.GarbageCollection,jdk.GCPhasePause" diag.jfr
```

`jdk.GarbageCollection` describes the GC event; `jdk.GCPhasePause` reports the duration of recorded pauses. Duration does not equal total GC CPU. To identify background GC activity, combine timeline, collector-specific events, and OS TID CPU. Do not assume every event name is enabled in the recording; `summary` shows which event types actually exist.

When **process CPU is high** and **GC logs show dense GC phases**, OS threads named as GC workers consume CPU, post-GC heap drops very little, or the allocation rate is very high, the evidence points toward **GC overhead**. Conversely, a long pause with low average process CPU does not mean all pause time was spent "burning CPU"; you still must inspect safepoints, collector behavior, scheduler, and workload.

### 5.3. When Should You Tune GC?

Only after you have evidence. Check live set, allocation rate, premature promotion, heap size, memory pressure, GC collector flags, and CPU limits. Reducing allocations in the application is often more effective than blindly tweaking collector flags. Some collectors use additional background threads when idle CPU is available; you need to balance **throughput, tail latency, and CPU headroom**.

## 6. Step 4 — Distinguish JIT/Compiler CPU

The **Just-In-Time compiler (JIT)** translates and optimizes hot Java methods into machine code. HotSpot has compiler tiers; threads typically have names related to **`C1 CompilerThread`**, **`C2 CompilerThread`**, or JVMCI depending on configuration/JDK. Compilation CPU is **JVM background work**, and is still counted in process CPU. Some causes include:

- The application has just started/warmed up or deployed new code; many hot methods are being compiled.
- Many classes/methods are loaded and executed for the first time, with tiered compilation active.
- Recompilation, deoptimization, or code cache pressure keeps the compiler working.
- A workload generates heavy method specialization/hot spots, extending compilation longer than expected.

**Do not equate "lots of JIT compilations" with "JIT CPU is the culprit"**: you must see compiler TIDs actually consuming CPU in the same window as compiler activity. Also, **CPU spent executing JIT-compiled code** belongs to application threads, not compiler threads.

### 6.1. JIT Diagnostic Commands

```bash
jcmd 12345 Compiler.queue
jcmd 12345 Compiler.codecache
jcmd 12345 VM.flags
```

- `Compiler.queue` shows methods queued for compilation **at the moment of sampling**; an empty queue at one instant does not rule out earlier compilation.
- `Compiler.codecache` describes the compiled machine code area. High code cache usage alone does not prove the compiler is currently consuming heavy CPU.
- `VM.flags` helps identify flags/conditions such as tiered compilation, code cache, and compiler thread settings; also check `jcmd 12345 help Compiler.queue` to verify commands supported by the target JVM.

You can enable compilation logging **at startup** in a test environment:

```bash
java -XX:+PrintCompilation -jar app.jar
```

This log shows when and which methods were compiled as recorded by the JVM. **It is not CPU% data for compiler workers.** Enabling logging adds overhead, output can be large, and you must not directly infer CPU usage from log line counts.

### 6.2. JFR Compiler Events

```bash
jfr summary diag.jfr
jfr print --events "jdk.Compilation,jdk.CompilerQueueUtilization" diag.jfr
```

These events can help correlate compilation duration and queue activity, depending on JDK version and recording configuration. A **compilation duration** is the execution time of a compilation task per event semantics; do not sum all durations and call that the exact total compiler CPU without verifying multiple compiler workers, overlap, and field definitions.

When OS TIDs show compiler workers consuming CPU across multiple windows, compilation events/tiered compilation are dense, GC is not especially heavy, and application samples do not dominate, JIT is likely driving the process CPU increase. For legitimate warm-up, you may just need to measure steady state after warm-up; for sustained CPU affecting SLAs, examine startup/deploy patterns, code cache, profiling, and workload characteristics before changing compiler flags.

**Do not rush to disable JIT or tiered compilation** to "save CPU": reducing compilation CPU can make application code run much slower and consume more total CPU. Always benchmark with the same workload across both cold start and steady state.

## 7. JFR Combined with OS Metrics: Read a Timeline Instead of One Screenshot

For PID `12345`, capture a 60-second recording (the file is written after the recording completes):

```bash
jcmd 12345 JFR.start name=cpu-diag settings=profile duration=60s filename=cpu-diag.jfr
```

After the file has been created:

```bash
jfr summary cpu-diag.jfr
jfr print --events "jdk.CPULoad,jdk.ThreadCPULoad" cpu-diag.jfr
jfr print --events "jdk.ExecutionSample" --stack-depth 24 cpu-diag.jfr
jfr print --events "jdk.GarbageCollection,jdk.GCPhasePause,jdk.Compilation" cpu-diag.jfr
```

- **`jdk.CPULoad`**: process/JVM CPU signal relative to the machine over the recording (if enabled and present).
- **`jdk.ThreadCPULoad`**: per-thread CPU signal per JFR collection capabilities; cross-check TID, thread lifetime, and measurement interval. Do not treat method sample counts as a direct substitute for CPU time.
- **`jdk.ExecutionSample`**: stack samples of running Java code, useful for finding hot methods. **Sample counts only estimate hot spots**, depending on sampling frequency, event settings, sampleable threads, and statistics; they do not represent exact milliseconds of CPU.
- **`jdk.GarbageCollection/jdk.GCPhasePause`**: GC timing/events; not every phase is counted as STW.
- **`jdk.Compilation`**: compilation activity; correlate with compiler OS thread CPU, because event duration alone is not CPU load.

Run `jfr summary` first to see which events are present. You can open the same file in **JDK Mission Control (JMC)** to inspect timelines, CPU, threads, GC, hot methods, and compiler activity. **Java application JFR does not necessarily sample all GC/JIT/native workers completely**; when native CPU is suspected, OS/perf profiler results remain essential.

A proper reading flow:

```text
Process CPU rises at t = 14:32:10
         |
         +-- OS TID worker-7 CPU up?
         |       +-- JFR ExecutionSample + thread dump -> application hot path
         |
         +-- OS GC worker(s) CPU up?
         |       +-- GC log + JFR GC events -> GC phase and allocation pressure
         |
         +-- OS C2 CompilerThread CPU up?
                 +-- Compiler.queue + JFR Compilation -> JIT work
```

Always check clocks: OS samples, GC logs, and JFR timestamps may use different timezones or formats. Do not correlate events just because their output order happens to align.

## 8. Java 17+: Example Measuring CPU of Two Java Threads and Process CPU

The following program creates **one compute-busy thread** and **one sleeping thread**, taking two samples of CPU time and wall time. It **does not force high GC/JIT CPU** because the goal is to observe the difference between process CPU and individual Java thread CPU. It also illustrates why process CPU includes additional JVM activity beyond the two demo threads.

Create **`CpuAttributionDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.atomic.AtomicBoolean;

public class CpuAttributionDemo {
    private static volatile long result;

    private static void spin(AtomicBoolean running) {
        long value = 1L;
        while (running.get()) {
            value = value * 1664525L + 1013904223L;
        }
        result = value;
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        boolean threadCpuEnabled =
                threads.isThreadCpuTimeSupported() && threads.isThreadCpuTimeEnabled();

        com.sun.management.OperatingSystemMXBean os =
                ManagementFactory.getPlatformMXBean(
                        com.sun.management.OperatingSystemMXBean.class);

        AtomicBoolean running = new AtomicBoolean(true);
        Thread busy = new Thread(() -> spin(running), "demo-busy");
        Thread sleeper = new Thread(() -> {
            while (running.get()) {
                try {
                    Thread.sleep(50);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }, "demo-sleep");

        busy.start();
        sleeper.start();

        long wallStart = System.nanoTime();
        long procStart = os == null ? -1 : os.getProcessCpuTime();
        long busyStart = threadCpuEnabled ? threads.getThreadCpuTime(busy.getId()) : -1;
        long sleepStart = threadCpuEnabled ? threads.getThreadCpuTime(sleeper.getId()) : -1;

        Thread.sleep(1000);

        long wallEnd = System.nanoTime();
        long procEnd = os == null ? -1 : os.getProcessCpuTime();
        long busyEnd = threadCpuEnabled ? threads.getThreadCpuTime(busy.getId()) : -1;
        long sleepEnd = threadCpuEnabled ? threads.getThreadCpuTime(sleeper.getId()) : -1;

        running.set(false);
        busy.join();
        sleeper.join();

        double wallSeconds = (wallEnd - wallStart) / 1_000_000_000.0;
        System.out.println("Threads: " + busy.getName() + ", " + sleeper.getName());

        if (procStart >= 0 && procEnd >= procStart) {
            double percent = 100.0 * (procEnd - procStart)
                    / (wallEnd - wallStart);
            System.out.printf("processCpu=%.1f%% of one core%n", percent);
        } else {
            System.out.println("processCpu: unavailable");
        }

        if (busyStart >= 0 && busyEnd >= busyStart
                && sleepStart >= 0 && sleepEnd >= sleepStart) {
            double busyPercent = 100.0 * (busyEnd - busyStart)
                    / (wallEnd - wallStart);
            double sleepPercent = 100.0 * (sleepEnd - sleepStart)
                    / (wallEnd - wallStart);
            System.out.printf("busyCpu=%.1f%% sleepCpu=%.1f%% of one core%n",
                    busyPercent, sleepPercent);
        } else {
            System.out.println("threadCpu: unavailable");
        }

        System.out.println("DONE");
    }
}
```

Compile and run on **HotSpot JDK 17+**:

```bash
javac --release 17 CpuAttributionDemo.java
java CpuAttributionDemo
```

Lines printed by the program itself have stable content:

```text
Threads: demo-busy, demo-sleep
<one line showing processCpu or processCpu: unavailable>
<one line showing busyCpu/sleepCpu or threadCpu: unavailable>
DONE
```

The two angle-bracket lines above are **placeholders describing variable output**, not literal output text; actual CPU numbers must come from the machine running the code. When CPU metrics are supported and enabled, `busyCpu` is typically greater than `sleepCpu` over the sampling interval. However, the scheduler, container quota, CPU throttling, GC/JIT, and test conditions can alter percentages significantly; "exact 100%" is not guaranteed.

Design notes:

- `System.nanoTime()` measures **elapsed wall time** between two samples, not CPU time.
- `com.sun.management.OperatingSystemMXBean.getProcessCpuTime()` (HotSpot/OpenJDK JDK management extension) measures **cumulative process CPU time**, including internal JVM threads, not just the two demo Java threads. It may return `-1` when unsupported.
- `ThreadMXBean.getThreadCpuTime(id)` measures **cumulative CPU time of a Java platform thread** by Java thread ID, and may return `-1` if unsupported/disabled or if the thread is no longer alive. Capture both samples **while the threads are still alive**, before stopping/joining them.
- JVM thread CPU measurement can be disabled; the example checks status and **does not enable it automatically** because changing collection configuration can incur overhead.
- `getId()` in Java 17 is the **Java thread ID**, not the Linux TID or HotSpot `nid`. This example does not provide a mapping to OS thread IDs.
- `result` is `volatile` to prevent the optimizer from treating the computation loop as dead code; `AtomicBoolean` provides a stop signal visible across threads.
- The busy loop runs for only about one second; do not run busy-loop experiments in production. This is a standalone educational program.

**Observation limit:** Total CPU across **Java platform threads** seen by `ThreadMXBean` does not always equal total process CPU, because the JVM may use VM/GC/compiler/native threads not listed in Java thread IDs, and because the measurements are not taken at the exact same instant. To accurately attribute CPU to GC/JIT, combine OS and JVM tools rather than subtracting and calling the remainder "GC".

## 9. High CPU Without Faster Throughput: Check Quota and Contention

High CPU consumption can be useful work or wasted overhead:

- **Legitimate CPU-bound work:** image processing, compression, encryption, complex computation; multiple cores are busy and throughput scales with load.
- **Busy spin/polling:** status-checking loops without sleep/backoff, overly aggressive retries, or pathological regex/algorithms; one thread sustains near one core without increasing throughput.
- **Lock contention:** many `BLOCKED` or I/O-waiting threads typically stretch wall time rather than burning CPU themselves; however, spin locks or active retries can burn CPU. Inspect stacks and actual CPU time.
- **GC pressure:** allocation churn, high live set, or sustained collector activity spends CPU reclaiming memory.
- **JIT warm-up:** compiler threads burn CPU during a phase that may be acceptable to improve steady-state performance.
- **CPU throttling:** the container has exhausted its quota; the application waits on the scheduler and latency climbs even though the process does not appear to hit 100% of the host.

On Linux **cgroup v2**, inspect the exact cgroup containing the JVM (the paths below only illustrate the default root):

```bash
cat /proc/12345/cgroup
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
```

- `cpu.max` contains quota and period, or `max` if no quota is set at that cgroup level. For example, `200000 100000` corresponds to an average quota of about **2 CPUs**, not two pinned logical cores.
- `cpu.stat` contains counters such as `usage_usec` and `nr_throttled`/`throttled_usec` when provided by the CPU controller; **take the delta between two samples** to know CPU used and throttling within a window.
- If the JVM resides in a child cgroup or has limits on a parent cgroup, you must identify **the exact path and ancestor quotas**. The `/sys/fs/cgroup` paths above are not guaranteed to point to the JVM's exact cgroup on every host/container.
- `throttled_usec` is the throttling duration reported by the system per cgroup semantics, not directly equal to request latency. Correlate timestamps and latency.

**When host CPU is low yet the service is slow**, check quota/throttling, locks/I/O, and the scheduler. Never conclude "CPU isn't high so CPU isn't the problem."

## 10. Quick Diagnostic Matrix

| Metrics Observed in the Same Window | Primary Suspect | How to Confirm |
| --- | --- | --- |
| High process CPU; **one Java application TID** near 100% of one core; stacks repeat app logic | Hot loop, CPU-heavy algorithm, retry/polling | `top -H` + TID→`nid` + multiple thread dumps + JFR ExecutionSample |
| High process CPU; **multiple application TIDs** at 30–70% | Parallel workload, concurrency, contention/spin | Group OS TIDs, CPU profiles, queue depth/throughput, inspect app methods |
| High process CPU; **GC worker threads** have high CPU; heavy GC log activity | GC overhead or allocation churn | GC logs, heap after-GC, JFR GC events, OS worker CPU |
| High process CPU; **C1/C2 CompilerThread** consumes CPU during warm-up | JIT compilation | OS per-thread + JFR Compilation + Compiler.queue/codecache + deployment timing |
| High process CPU; no application thread in thread dump shows matching CPU | JVM internal/native/JNI threads or visibility limits | OS TID + native profiler/JFR/NMT as appropriate; do not assume remainder is GC |
| Moderate process CPU; high host CPU | Other processes using CPU | System-wide `top`/Process Explorer, cgroup/host metrics |
| Low host CPU%; cgroup `nr_throttled` rising; high latency | Container CPU quota pressure | `cpu.max`, `cpu.stat`, container usage/limits, p95/p99 latency |
| High latency; low process CPU; many threads WAITING/BLOCKED | I/O, lock contention, external dependency | Thread dumps, traces, lock metrics; CPU is not the only bottleneck |
| GC pauses rising while GC worker CPU is not high | STW/safepoint or scheduling issue | GC phases, safepoint logs, OS pressure; do not equate pause with CPU |
| Compiler queue has entries while compiler TIDs show low CPU | Queue existed at snapshot time | Sample TIDs multiple times before attributing CPU to the compiler |

**Rule:** Start from **symptom** → measure **process CPU** → find **TIDs and CPU share over a window** → correlate **JVM stacks/events** → cross-check **GC/JIT/container/application** → fix and re-measure. A single `top` screenshot or a standalone thread dump cannot prove causality.

## 11. Repeatable Real-World Investigation Workflow

### Case: JVM Uses 260% CPU While Service p99 Spikes

This is a **hypothetical scenario**, not observed data from a specific system.

1. **Lock down the scope:** confirm 260% comes from `top` in per-core mode, i.e., about **2.6 cores**; record core count, container quota, PID, timestamp, and load.
2. **Collect 5 TID samples:** `pidstat -t -p PID 1 5`; suppose one application TID is ~90%, two GC workers total ~120%, and a compiler worker is ~30%; other TIDs contribute the rest.
3. **Map HotSpot `nid`:** convert each decimal TID to hex and take `jcmd PID Thread.print -l` near that time. The application thread may be running a heavy method, while GC/JIT workers may not appear in the Java thread list.
4. **Cross-check GC/JFR:** if GC pauses/concurrent work are dense and post-GC heap is large, GC overhead is well-supported; if GC activity is sparse, do not blame 120% solely on the `GC worker` name without timeline/phase evidence.
5. **Cross-check compiler:** are there compilation events and compiler queue activity in the same window? If warming up after a deploy, JIT CPU may be transient.
6. **Analyze the 90% application thread:** collect JFR ExecutionSample or CPU profiler data to identify hot code; a method appearing once on a stack dump is not proof of a hotspot.
7. **Make a targeted change:** reduce allocations/busy loops, fix algorithms, adjust concurrency or GC configuration after measuring; consider warm-up strategy if JIT is significant.
8. **Re-measure under the same load:** compare process/core CPU, per-thread CPU, GC pauses and GC CPU, compiler activity, throughput, and p99. Do not optimize for a single CPU number at the expense of throughput.

### What to Record in an Incident Report?

Keep a **timeline table with measurement sources**:

| Time | Process CPU/cores | Top TID and CPU | GC/JIT Evidence | Latency/Throughput |
| --- | --- | --- | --- | --- |
| Before spike | Baseline | Baseline | Few notable events | Normal |
| During spike | High | Specific TID | Corresponding logs and JFR | High p99 |
| After spike | Returned to baseline? | Which TID dropped? | Did GC/JIT finish? | Did p99 recover? |

Fill in **actual measurements** from tools; do not treat hypothetical values from this lesson as observed results. When logging/sampling adds overhead, note its impact level.

## 12. Common Pitfalls

1. **"Process at 300% CPU means one thread is at 300%."** False in per-core measurement mode: usually multiple threads are using ~3 CPU cores combined.
2. **"A `RUNNABLE` Java thread is burning CPU."** False: you need CPU time deltas and sampling in the right window.
3. **"High process CPU must be an infinite loop in the application."** False: GC workers, C1/C2 compilers, JVM/native threads, and JNI all live inside the process.
4. **"A 200 ms GC pause means GC used 200 ms of CPU."** False: pause is the wall time of the stop phase; workers may run in parallel or GC may run concurrently.
5. **"Many GC events prove GC uses the most CPU."** Insufficient: you need CPU time or worker/TID/phase evidence.
6. **"Compiler queue has work means the compiler is using 100% of a core."** Insufficient: a queue snapshot is not a CPU metric.
7. **"Each `PrintCompilation` line equals 1 ms of compiler CPU."** False: you must understand the specific log contents and actual CPU time.
8. **"Increasing heap always fixes high CPU."** False: it only helps in certain allocation/GC scenarios; it can increase memory footprint and cause other problems.
9. **"`ps %CPU` and `pidstat 1 5` cover the same window."** False: `ps` may report a lifetime average, whereas `pidstat` reports the sampling interval.
10. **"`nid` is `Thread.getId()`."** False: HotSpot `nid` relates to the OS native TID; Java thread ID is a different concept.
11. **"If a thread isn't in `Thread.print`, it doesn't exist."** False: VM/internal/native workers do not appear as Java threads, and timing races also occur.
12. **"JFR method samples give exact milliseconds of CPU per function."** False: sampling is a statistical estimate; you need enough samples and awareness of sampling bias.
13. **"Host CPU is low so the container can't be CPU-starved."** False: cgroup quota may already be hit and throttled.
14. **"High CPU is always bad."** False: productive CPU use can accompany good throughput; evaluate latency/throughput targets, cost, and headroom.
15. **"One thread dump is enough to find the root cause of a spike."** False: a dump is a snapshot of state/stack and must be paired with CPU deltas and a timeline.

## 13. Self-Check Questions

**Question 1.** Over 10 seconds, the JVM accumulates 18 seconds of CPU time. What is the CPU% per core?  
**Answer:** 180%; i.e., an average of 1.8 cores. If the machine has 8 logical cores and no quota, that is approximately 22.5% of total 8-core capacity.

**Question 2.** `top -H` shows TID 4096 at the top, while `Thread.print` lists `nid=0x1000`. Can they be related?  
**Answer:** Yes, 0x1000 hex = 4096 decimal, provided they are in the same OS namespace, same JVM, and the thread is still alive.

**Question 3.** A GC pause is 50 ms with 8 workers running simultaneously. Can total GC CPU time exceed 50 ms?  
**Answer:** Yes. Multiple workers running in parallel can add up to more CPU time than the wall pause; you must measure/correlate the specific scope.

**Question 4.** A `C2 CompilerThread` has high CPU right after deployment, while application method CPU is low. Can you attribute it to JIT immediately?  
**Answer:** It is a strong hypothesis if compilation events/queue activity occur in the same window; cross-check multiple TID/JFR samples before concluding.

**Question 5.** `ThreadMXBean.getThreadCpuTime(7)` returns `-1`. Does that mean the Java thread used 0 CPU?  
**Answer:** No. The thread may have terminated, may not exist, or CPU time measurement may be disabled or unsupported. Never turn "unmeasurable" into "0 CPU".

**Question 6.** A machine has 32 cores, the container quota is 2 cores, and the JVM reports around 180% of one core. Could it be throttled?  
**Answer:** Yes. The JVM may be near its 2-core quota even though it is only using about 5.6% of the host's 32-core capacity. Check `cpu.max`, `cpu.stat`, and actual metrics.

**Question 7.** A thread dump shows `java.util.HashMap.get` on a `RUNNABLE` thread. Should you optimize `HashMap` immediately?  
**Answer:** No. You need per-TID CPU in the same window, multiple stack samples, hot path/callers, and distribution data to identify the root cause.

## References

- [Oracle JDK 17 — `jcmd`: `Thread.print`, `Compiler.queue`, `Compiler.codecache`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle Java SE 17 — `ThreadMXBean` and `getThreadCpuTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [Oracle JDK 17 — `java`, GC Unified Logging and `PrintCompilation`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle JDK 17 — Troubleshoot Performance Issues Using JFR: CPULoad, ThreadCPULoad, GC, hot methods](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK 17 — `jfr`: `print` and `summary`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [Oracle Java SE 17 — `OperatingSystemMXBean` extension](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html)
- [Linux kernel documentation — Control Group v2: CPU controller](https://docs.kernel.org/admin-guide/cgroup-v2.html)
