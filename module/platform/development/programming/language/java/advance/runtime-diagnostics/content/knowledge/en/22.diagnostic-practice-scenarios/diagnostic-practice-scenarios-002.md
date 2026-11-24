# 22.2 Diagnosing a CPU-Intensive Loop with jcmd, Thread Dumps, and JFR

## 1. The Problem: CPU Spikes, but Which Thread and Code Are Running?

High CPU in a JVM does not immediately mean an "infinite loop". CPU can be consumed by **continuously running application code**, JIT compilation, garbage collection, serialization, native code, background jobs, high legitimate request volume, or resource contention. Even when a thread is in `RUNNABLE` state, that state alone **does not prove** it is actually consuming significant CPU time.

This practice lab combines **three layers of evidence**:

1. **Operating system:** which Java process and **native thread ID (TID)** are consuming CPU over time?
2. **`jcmd Thread.print`:** what Java stack is that native thread executing, and does that stack repeat across multiple points in time?
3. **Java Flight Recorder (JFR):** do **execution samples** frequently hit the same hot code path within the recording window, and how do CPU and JVM activities evolve alongside it?

The expected result is a **verifiable chain of reasoning**: right JVM → right TID → right Java thread → suspect method/loop → repeated evidence over time → controlled comparison test. Never conclude a root cause just because one thread dump shows `RUNNABLE` or a flame graph highlights a method.

Scope: Java 17+ on HotSpot; **Linux** command examples for finding native TIDs and JDK 21 examples for `jcmd`/`jfr`. On Windows/macOS, the Java/`jcmd`/JFR parts still apply, while observing per-thread CPU and OS identifiers requires the corresponding platform tools.

## 2. Distinguishing "High CPU", "Busy Wait", "Hung", and "Slow"

| Symptom | Process CPU | Thread Signs | Hypotheses to Check |
| --- | --- | --- | --- |
| **Busy CPU loop** | Usually high on one or more logical cores | One or more threads consume CPU; stack repeats in a compute method | Loop missing exit condition, overly expensive algorithm, polling without backoff |
| **Busy-wait / spin** | Can be high even when the system produces little useful work | Thread spins continuously checking a flag/queue/lock | Polling too aggressively; wait loop lacking sleep/park/backoff |
| **Deadlock/blocking wait** | Can be low while requests remain stuck | `BLOCKED`/`WAITING`/`TIMED_WAITING`; lock/deadlock hints | Monitor/lock/condition/I/O; not a CPU loop just because threads make no progress |
| **Many legitimate requests** | High with load, throughput may scale accordingly | CPU spread across many worker threads | Heavy workload, capacity/CPU quota, concurrency configuration |
| **GC/JIT consuming CPU** | Can be high even when Java business threads are not hot | GC/compiler threads and GC/compilation events | Allocation churn, GC pressure, warm-up, code compilation |
| **CPU throttling in containers** | Host-observed CPU may differ from container limit | Runnable threads starved of execution CPU | Cgroup quota/throttling; high CPU ≠ running for the entire wall-clock window |
| **Low CPU, high latency** | Low or moderate | Threads waiting on network, database, locks, queues | Bottleneck lies outside compute code |

**Key distinction:** `RUNNABLE` in a Java thread dump covers threads actively executing as well as certain native paths or threads eligible to run. It is not a measurement saying "this thread used 98% CPU". You need **OS CPU accounting** or per-thread CPU time over an interval to confirm CPU consumption.

In particular, **CPU percentage has multiple denominators**: 100% of **one logical core** in `top` may correspond to around 12.5% of **an 8-logical-core host** depending on display mode; cgroup CPU quota, SMT, `top/ps` normalization, available cores, and sampling interval all affect the figure. Never compare percentages directly from two tools without knowing their conventions.

## 3. Investigation Decision Flowchart

```text
CPU alert / slow application
         |
         v
Confirm host, PID, JVM uptime, timestamp, load level
         |
         v
OS: process CPU? Per-TID CPU across multiple samples?
         |
         +---- No Java thread clearly consuming CPU
         |       |
         |       v
         |    Inspect GC/JIT/native work, CPU quota/throttling,
         |    thread count, independent metrics, sampling window
         |
         +---- Stable hot TID found
                 |
                 v
          Decimal TID -> hex -> nid in thread dump
                 |
                 v
          Repeat thread dumps T0/T1/T2, same stack?
                 |
                 +--- No: shifting workload/code paths,
                 |    thread reuse or changing code
                 |
                 +--- Yes: isolate suspect method/loop
                              |
                              v
                    JFR profile in the same window
                              |
                              v
                    Execution samples + CPU/GC/JIT events
                              |
                              v
                    Control comparison busy vs idle / change one variable
                              |
                              v
                    Conclude with confidence level, document limits
```

This is not a mandatory flow for investigating **every** incident, but it helps separate "where a thread was" from "whether that thread actually burned CPU". Verifying the PID before joining datasets is especially critical after a restart, because the OS can reassign PIDs/TIDs.

## 4. Environment Setup and Safety Boundaries

Prerequisites:

- **JDK 17+** to compile/run; `jcmd` and `jfr` ship in a full JDK and may be absent in minimal runtime images.
- A terminal on the same appropriate host/namespace, or authorized admin tooling. Per JDK documentation, `jcmd` generally needs to run on the same machine and under a user matching the target JVM; attaching across containers has specific constraints.
- Linux `top`, `ps`, `printf`, `sleep` for TID identification commands. `pidstat` if `sysstat` is installed is only an optional supplement.
- A writable directory to store `.jfr`, thread dumps, and manifests. The path in `jcmd ... JFR.start filename=...` is resolved relative to the **target JVM's filesystem**, not necessarily the admin shell's view if the target runs inside a container.

**Do not run the busy loop demo in production.** Even though the program is time-bounded, it intentionally saturates CPU on a thread and can affect shared machines. Prefer a laptop, isolated VM/staging, or a container with explicit quotas. To raise CPU without crashing the JVM, the demo avoids native crashes, `Unsafe`, unbounded heap allocation, or infinite loops.

For real JVMs, prioritize low-intrusion observation first, taking 2–3 well-spaced thread dumps and avoiding triggering `GC.heap_dump`/Full GC just to investigate CPU. A heavy snapshot can introduce pauses/overhead and alter the very phenomenon under study.

## 5. Reproducible Java 17+ Program with a Control Mode

To verify every observation layer, create **one platform thread** named `cpu-hot-loop`. The `busy` mode loops continuously over CPU calculations for a bounded duration; the `idle` mode keeps the same lifecycle but uses `sleep` so it consumes almost no CPU. Both share the same thread name for easy comparison; **thread name is not the native TID**.

Save **`CpuHotLoopDemo.java`** with the following full code:

```java
public final class CpuHotLoopDemo {
    private static volatile boolean running = true;
    private static volatile long checksum;

    private static void busyLoop() {
        long value = 1L;
        while (running) {
            value = value * 2862933555777941757L + 3037000493L;
            value ^= value >>> 21;
        }
        checksum = value;
    }

    private static void idleLoop() {
        while (running) {
            try {
                Thread.sleep(50);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                break;
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        String mode = args.length == 0 ? "busy" : args[0];
        int durationSeconds = args.length < 2
                ? 90
                : Integer.parseInt(args[1]);

        if (args.length > 2
                || (!mode.equals("busy") && !mode.equals("idle"))
                || durationSeconds < 15
                || durationSeconds > 300) {
            throw new IllegalArgumentException(
                    "Usage: CpuHotLoopDemo [busy|idle] [15..300]");
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("mode=" + mode
                + " durationSeconds=" + durationSeconds);

        Runnable task = mode.equals("busy")
                ? CpuHotLoopDemo::busyLoop
                : CpuHotLoopDemo::idleLoop;
        Thread worker = new Thread(task, "cpu-hot-loop");
        worker.start();

        Thread.sleep(durationSeconds * 1000L);
        running = false;
        worker.join();

        System.out.println("finished mode=" + mode);
    }
}
```

### 5.1. Why Is This Code Suitable for Observation?

- `running` is `volatile`: the worker observes changes from the main thread, unlike a local variable read only before the loop. When main sets `false` after the chosen duration, the worker can exit.
- `checksum` is `volatile`: the final computed value is written to a field with observable side effects, reducing the chance that the compiler eliminates the entire calculation as dead code. The demo still depends on JIT/OS scheduling; it does not promise a constant iteration count.
- `busy` mode does not sleep/wait inside the hot loop. In an environment with available CPU, one platform thread will consume significant time on **one logical processor**.
- `idle` mode calls `Thread.sleep(50)` in a loop: the worker exists but spends most of its time in `TIMED_WAITING` with minimal CPU. This serves as a **negative control** to distinguish "thread exists" from "thread burns CPU".
- The `15..300` second bound and `join()` ensure controlled termination. If a debugger/scheduler pauses the process, wall time may differ from the nominal duration.
- Each new JVM is a **separate run**; do not switch `mode` mid-run within the same JVM. The `running` variable only resets when a new process starts.

The code performs no networking, disk I/O, or object allocation inside the hot loop, helping minimize GC noise. Still, **no benchmark is noise-free**: JIT compilation, class loading, the OS scheduler, CPU frequency scaling, and CPU quotas can all introduce variation.

### 5.2. Compiling and Running

In terminal A:

```bash
javac -g CpuHotLoopDemo.java
java CpuHotLoopDemo busy 90
```

Opening output looks like:

```text
PID=<actual PID>
mode=busy durationSeconds=90
```

When exiting normally, the program prints **exactly**:

```text
finished mode=busy
```

`<actual PID>` is only a placeholder, **not** literal stdout. Record the printed PID and use it in subsequent commands. The program runs for roughly 90 seconds unless paused by a debugger or interrupted by an environment error; you can adjust to 120–180 seconds within the allowed range for enough time to operate.

In a **separate run**, run the negative control:

```bash
java CpuHotLoopDemo idle 90
```

`mode=idle durationSeconds=90` and `finished mode=idle` are the corresponding logical outputs. For each run you must capture the **new PID**; never reuse an old PID from the `busy` run.

## 6. Step 1 — Confirming the Exact JVM and CPU Level

In terminal B, while the demo is running, replace `12345` with the actual PID:

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.uptime
jcmd 12345 VM.command_line
```

`jcmd -l` lists JVMs visible from the tool's environment, though it may miss processes in other containers/namespaces. `VM.command_line` helps verify the main class/arguments, but **can expose secrets** in real applications: protect logs and do not share carelessly.

Minimum fields to record:

| Field | Example Recording | Reason |
| --- | --- | --- |
| Timestamp | UTC ISO 8601 + admin host timezone | Align OS CPU, thread dumps, and JFR |
| PID, process start time/uptime | `12345`, actual uptime from `jcmd` | Avoid mixing up JVMs after restarts |
| JDK vendor/build | `VM.version` output | JFR, thread dump, and naming formats may vary |
| Run/workload | `busy` or `idle`, duration, active workload | Compare under matching conditions |
| CPU quota/cores | Available logical CPUs, cgroup limit | Understand the %CPU denominator |
| Tool/measurement window | `top -H`, `ps -L`, T0/T1/T2 | Evidence covers an interval, not a random snapshot |

A process has many threads, so process CPU is the **aggregate** of thread activity under the tool's accounting rules. The demo has one hot worker, whereas real systems have GC, compiler, network, application pool, and native threads; you must pinpoint the right thread rather than attributing total CPU to a single method.

## 7. Step 2 — Finding the CPU-Consuming Native Thread on Linux

In terminal B:

```bash
top -H -p 12345
```

`-H` shows threads; `-p` filters by process PID (display layout and %CPU may vary across `top` versions). Observe **multiple refresh intervals**, not just a single snapshot right after CPU rises.

Another snapshot:

```bash
ps -L -p 12345 -o pid,tid,pcpu,stat,comm
```

- `PID`: Java process.
- `TID`/`LWP`: **native thread ID** in the Linux namespace visible to the tool, distinct from Java's `Thread.getId()`.
- `%CPU`/`PCPU`: ratio estimated by the tool over its interval/lifetime convention. For `ps`, this figure is typically an **average since task start**, not instantaneous CPU over the last 1 second.
- `STAT`: OS scheduling state, not Java `Thread.State`.
- `COMMAND/COMM`: OS thread name may be truncated or differ from the Java thread name; do not rely on name alone for exact matching.

Depending on the host, you can sample by interval with `pidstat` (requires the `sysstat` package):

```bash
pidstat -t -p 12345 1 5
```

This queries CPU usage of tasks/threads belonging to the PID across **5 one-second intervals**. If unavailable, use `top -H` and other system snapshots/metrics instead; do not install ad-hoc software on production hosts.

### 7.1. What to Expect in Both Modes

- **`busy`:** the TID corresponding to `cpu-hot-loop` typically occupies most of one logical core's time; exact 100% is not guaranteed due to CPU quota, thermals, frequency scaling, scheduling/JIT, and other processes.
- **`idle`:** the worker mostly sleeps and uses little CPU; the thread still appears in thread dumps, typically as `TIMED_WAITING`. Other JVM threads still consume a small amount of CPU.
- If both runs show high CPU, check for external load, measuring the wrong target, JIT/GC/other threads, or environment limits. Never force results to fit the demo's expected story.

**Metrics to keep:** which TID shows high `%CPU` across multiple intervals, timestamps, together with PID and thread lifetime. This is the starting point for stack correlation, **not the final conclusion**.

## 8. Step 3 — Mapping the OS TID to `nid` in a Thread Dump

`jcmd <PID> Thread.print` prints Java stacks and JVM thread info. On HotSpot Linux, thread headers typically include `nid=0x...`, which is the native thread ID in **hexadecimal**. From the OS, TID is typically **decimal**. You must convert bases before matching.

Hypothetical example:

```text
Process PID:      12345
TID from top -H:  12416 (decimal)
Convert to hex:   0x3080
Find in dump:     nid=0x3080
```

Convert via shell (Linux/bash):

```bash
printf '0x%x\n' 12416
```

**Exact** output of the conversion:

```text
0x3080
```

In a real run, replace `12416` with the observed hot TID, never guessing `PID+1`. Then run:

```bash
jcmd 12345 Thread.print -l > threads-T0.txt
```

Search for `nid=0x3080` or the name `cpu-hot-loop` in the file. A **structurally illustrative header**, not actual measured output:

```text
"cpu-hot-loop" #XX prio=5 os_prio=0 cpu=...ms elapsed=...s
   tid=0x... nid=0x3080 runnable
   java.lang.Thread.State: RUNNABLE
        at CpuHotLoopDemo.busyLoop(CpuHotLoopDemo.java:<line>)
        at java.lang.Thread.run(Thread.java:<line>)
```

The `cpu=...` and `elapsed=...` fields depend on VM/build/format; **do not invent millisecond values**. If CPU time appears in the header, compare **the delta between snapshots of the same thread**; do not use a cumulative value to infer how much CPU it used in the last second.

**Important:** In HotSpot, `nid` belongs to a **native platform thread**. For **virtual threads** in Java 21, a virtual thread has no fixed OS TID of its own because it can run on carrier platform threads; the TID↔nid mapping technique mainly applies to **platform threads** like in this demo. If the thread name is truncated at the OS level, `nid` is more reliable than name matching.

### When the TID Cannot Be Found in the Dump

Possible causes:

- The thread terminated between OS measurement and when `jcmd` captured stacks.
- Container namespace PID/TID does not match the OS view of the running tool.
- `top` and `jcmd` inspected **two different JVMs** after a restart.
- The native thread does not map to a Java thread with a visible Java stack (e.g., GC/native worker) or output differs by JVM/version.
- Multiple threads have very similar names; match by native identity and timestamp, not name alone.

Do not fudge conclusions by picking a thread with a "close" name while ignoring a `nid` mismatch.

## 9. Step 4 — Taking Multiple Thread Dumps to Avoid Single-Snapshot Diagnosis

A thread dump is a snapshot of **a single instant**. Seeing a thread inside `busyLoop` at dump time does not prove it spent most of the last 60 seconds there. To observe stability, capture three spaced snapshots while the OS still shows the same hot TID.

```bash
jcmd 12345 Thread.print -l > threads-T0.txt
sleep 2
jcmd 12345 Thread.print -l > threads-T1.txt
sleep 2
jcmd 12345 Thread.print -l > threads-T2.txt
```

Depending on thread count, `Thread.print` has **medium** impact per `jcmd` documentation; dump duration can be noticeable. Do not capture dozens of dumps every 100 ms on a heavily loaded service just to catch a stack. Labels T0/T1/T2 are **sequence placeholders**; record actual timestamps before/after each command in incident reports.

Check these properties on the **same `nid`**:

| Observation | Supports CPU Loop Hypothesis? | Limitation |
| --- | --- | --- |
| Same `nid` across 3 dumps, and OS also reports that TID as hot | **Yes**, two independent sources converge on the same native thread | Does not rule out other code paths running between snapshots |
| Stack consistently in `CpuHotLoopDemo.busyLoop` | **Yes**, method repeatedly present when observed | Snapshots do not prove 100% of CPU time was on one line |
| `java.lang.Thread.State: RUNNABLE` | Consistent, but **insufficient** | Runnable may be waiting to be scheduled by the OS |
| Cumulative CPU time of that exact thread rises sharply between dumps | Stronger evidence the thread is burning CPU | Delta must be paired with elapsed time and counter semantics |
| `idleLoop` sits at `Thread.sleep` / `TIMED_WAITING` | Control consistent with a sleeping worker | Could wake briefly between two dumps |
| Stack scatters across methods or `nid` changes | Cannot conclude a single tight stable loop | Could be a worker serving varied requests or TID reuse |
| VM/GC/compiler thread is hot while business stack does not repeat | Shift hypothesis toward runtime work | Do not misattribute GC/JIT CPU to an application method |

### Reading the Stack Bottom-Up and Top-Down

Example stack:

```text
"cpu-hot-loop" ... nid=0x3080 runnable
  java.lang.Thread.State: RUNNABLE
      at CpuHotLoopDemo.busyLoop(CpuHotLoopDemo.java:8)
      at CpuHotLoopDemo$$Lambda$...run(Unknown Source)
      at java.lang.Thread.run(Thread.java:...)
```

This is an **illustrative stack**; line numbers/lambda frames are not guaranteed. The top frame is closest to what is executing; lower frames provide **the call path**. Identify:

1. **Top frame:** which method was active when captured?
2. **Caller chain:** which request/worker or task led there?
3. **Thread name, nid, state:** does it match the hot TID from the OS?
4. **Other snapshots:** does it repeat along the same call path?
5. **Matching build source:** do line numbers correspond to the target JVM's exact files/classes?

The JIT can inline methods, optimize loops, or alter frame representation; do not demand byte-identical line numbers to call it the same **code path**. Conversely, `Thread.run` at the bottom of the stack is normal and not a root cause since it appears on nearly every thread.

### When You Want Lock Information Too

`-l` requests printing `java.util.concurrent` locks for additional context. It does **not** mean `Thread.print -l` measures CPU. In a CPU loop investigation, it helps rule out or identify contention when symptoms lean toward blocking; do not get sidetracked into lock diagnosis if the OS clearly points to a TID actively computing.

## 10. Step 5 — Capturing the CPU Window with JFR

Thread dumps provide only a few instants; **JFR execution sampling** observes many stacks over an interval rather than one snapshot. On HotSpot JDK 21, you can start a recording on a **running** JVM:

```bash
jcmd 12345 JFR.start name=cpu_probe settings=profile duration=40s disk=true filename=/tmp/cpu-probe-%p-%t.jfr
jcmd 12345 JFR.check
```

- `settings=profile` is a more detailed profiling configuration than `default`, typically enabling events needed for profiling like `jdk.ExecutionSample`; exact events/periods depend on JDK version and config.
- `duration=40s` stops the recording automatically after 40 seconds and writes the file at `filename`. The 90-second demo leaves enough time to start early and wait for completion.
- `disk=true` lets JFR spill data to its disk repository during recording, reducing the risk of losing history in a small RAM buffer.
- `filename` is the target path **in the target JVM's filesystem**. `%p` and `%t` expand to PID and timestamp. Do not assume the file literally contains `%p`/`%t`.
- `JFR.check` lists active recording names/states; it does not create a file.
- JFR sampling has overhead and does not guarantee every method or iteration gets an event. Use recordings with **identical settings** when comparing `busy` and `idle`.

Once the recording finishes and the file actually exists, run:

```bash
jfr summary /tmp/cpu-probe-12345-EXAMPLE.jfr
jfr print --events jdk.ExecutionSample --stack-depth 16 /tmp/cpu-probe-12345-EXAMPLE.jfr
jfr print --events jdk.CPULoad /tmp/cpu-probe-12345-EXAMPLE.jfr
```

**The filename above is purely a placeholder.** Replace it with the actual filename reported by `jcmd`. `jfr summary` shows recording duration and event counts by type; `jfr print` filters events for detailed inspection. If you have JDK Mission Control (JMC), open the file and use CPU/method profiling or the flame graph filtered by **thread and time window**.

If a recording is running and you want an immediate snapshot, use:

```bash
jcmd 12345 JFR.dump name=cpu_probe filename=/tmp/cpu-incident-%p-%t.jfr
```

`JFR.dump` exports data **recorded up to that point** without stopping the recording; by contrast `JFR.stop name=cpu_probe filename=...` stops the recording explicitly. In the finite-duration demo, **pick one approach**: wait for `duration` to auto-stop and write the file, or stop/dump explicitly before the JVM exits; never run `JFR.dump` against an already dead PID.

### Interpreting Execution Samples Properly

`jdk.ExecutionSample` is a **stack observation sample**, not an invocation counter. Suppose you see 150 samples containing `CpuHotLoopDemo.busyLoop` in a recording. The valid conclusion is:

> "Within the recording window and current filters, the sampler repeatedly caught the `busyLoop` execution path; this aligns with OS CPU and thread dumps showing that this thread was busy running."

Do not write:

> "`busyLoop` was called 150 times", "it ran for exactly 150 ms", or "150 samples prove 150 iterations."

A single call to `busyLoop` can last **tens of seconds**; the sampler can observe it many times. Changing the sampling period or enabling/disabling events changes the count even with an identical workload.

**Denominator to record:** total valid execution samples within the time window/thread filter, JFR configuration, duration, and thread count. A 60% sample share is **the proportion within the sampled set**, not automatically 60% of whole-process CPU or 60% of request latency.

### What Role Do `jdk.CPULoad` and GC/JIT Events Play?

`jdk.CPULoad` provides periodic CPU statistics that help align CPU timelines inside JFR. It does not replace OS per-thread TIDs when pinpointing a specific thread. Some JFR builds/settings also include `jdk.ThreadCPULoad` depending on recording settings; verify with `jfr summary` and event availability rather than assuming it is present.

If CPU spikes unexpectedly yet `busyLoop` does not appear in execution samples, check:

- Did the profile enable `jdk.ExecutionSample`? Run `JFR.check verbose=true` while recording and/or save the `.jfc` file.
- Did the recording start after the hot loop ended? Is there only 5 seconds of data?
- Are thread name, time filter, and stack depth right? Are there inlined frames or compiler/native paths?
- Is CPU being consumed by **GC, JIT compiler threads, or native code** rather than Java workers?
- Did OS CPU sampling and JFR inspect different JVMs/instances after a restart?
- Did the sampler capture enough valid samples for the phenomenon? Sampling does not catch every execution.

Never treat the absence of an event as absolute proof that "this code did not run."

## 11. Step 6 — Combining Three Layers of Evidence into One Timeline

A **hypothetical numeric example**, not actual run results:

| Point | OS CPU | Thread dump | JFR | Interpretation |
| --- | --- | --- | --- | --- |
| T0 | Java process ~105% of one core; TID 12416 ~95% | `nid=0x3080`, `RUNNABLE` at `busyLoop` | Recording started, few samples so far | Suspect TID narrowed down, not yet conclusive |
| T0+2s | TID 12416 remains high | Same `nid`/method `busyLoop` | More execution samples | Two time-series sources point to the same thread |
| T0+4s | TID 12416 remains high | Similar stack a third time | Many samples on the same stack in window | Strong evidence of a hot loop |
| New `idle` run | Worker TID low CPU | `Thread.sleep`, typically `TIMED_WAITING` | Few execution samples in `idleLoop` | Negative control reinforces the mechanism |

Values like `105%`, `95%`, TIDs, and relative timestamps here **are all hypothetical for teaching correlation**. Learners must record their actual measurements, which can look very different on a machine capped at 0.5 vCPU or while the compiler is active.

### Aligning Timelines When Tools Use Different Clocks

- Record UTC/offset for every command; thread dumps usually carry timestamps, OS CPU covers intervals, and JFR has recording start/end times.
- Record the full **observation window**, e.g., `10:00:00Z–10:00:40Z`, not just "around 10 AM".
- PID/TID are identities within one process lifetime, not durable IDs across restarts.
- If a JFR profile is taken minutes after a CPU spike subsided, not seeing `busyLoop` does not invalidate an earlier thread dump.
- JFR events have thresholds/periods and sampling selection; synchronized graphs show **correlation**, requiring mechanism analysis and controlled changes to conclude causation.

### Criteria for "Strong Enough" in the Demo

You can conclude **evidence strongly supports a CPU-burning loop** when:

1. Exact JVM, PID, and runtime window are verified.
2. OS identifies **one specific TID** using high CPU across multiple intervals.
3. Hex-converted TID matches **`nid` of platform thread `cpu-hot-loop`**.
4. Two or three dumps of the same thread show stacks in `busyLoop` / the same code path.
5. JFR contains matching execution samples within **the same window**.
6. Running `idle` in a new JVM under comparable conditions drops worker CPU markedly and shifts the stack to `Thread.sleep`.

No single signal above proves the cause of every real-world CPU incident on its own. The demo is deliberately designed with a known cause to teach **verification**, not guessing toward a desired answer.

## 12. When Might a "Busy Loop" Conclusion Be Wrong?

### 12.1. Thread Always `RUNNABLE` Yet Not Consuming CPU

The OS may not schedule enough CPU for the thread or the thread may be in a native path while the JVM reports `RUNNABLE`. If actual per-thread CPU is low or erratic, do not call it a **CPU hot loop**. Check CPU time deltas and CFS/cgroup throttling before inferring from Java thread state.

### 12.2. Same Stack Across Three Dumps Yet OS CPU Near 0

If a thread is `TIMED_WAITING` or snapshots happen to land on a very brief path, stacks can look identical. In particular, many pool threads waiting in `ThreadPoolExecutor.getTask` or `LockSupport.park` is **normal**. Do not confuse "unchanged stack" with "burning CPU".

### 12.3. High CPU on `GC Thread` or Compiler Thread

If the OS points to a hot TID named like GC/Compiler rather than an application worker, shift the question to `GC/compilation`. Inspect GC logs/JFR `jdk.GarbageCollection`, `jdk.CPULoad`, `jdk.Compilation`, `jcmd PID Compiler.queue`, and related memory metrics. Never blame GC CPU on a Java method just because an application stack also appeared during that minute.

### 12.4. It Is Actually Legitimate Throughput

A heavy image-processing batch can legitimately use 100% of a core, finish tasks on time, and deliver strong throughput. "High CPU" is only a **resource symptom**. Compare against expected load, completed task rate, SLA/tail latency, and saturation to decide whether there is a bug or simply a need for capacity planning.

### 12.5. Busy-Wait Loop Due to Race/Visibility

If code misuses shared condition variables or polls without backoff, it can spin continuously. Check memory visibility (`volatile`, atomics, locks) **and** wait design. However, fixing concurrency code is not randomly sprinkling `Thread.sleep`: consider blocking queues, conditions, semaphores, `LockSupport.park`, and proper retry/backoff. Adding sleep can alter semantics/latency and does not by itself fix data races.

### 12.6. OS and Container Views Differ

Inside containers, `top` on the host and `jcmd` inside the container may see different PIDs/TIDs due to **PID namespaces**. CPU throttling or quotas also change how CPU% is interpreted. Always annotate each tool's vantage point along with container ID and cgroup metadata; never match two IDs that only coincide by chance.

## 13. Walkthrough of a Hypothetical Incident Analysis

After a deployment, a service exhibits rising process CPU and high p99 latency. Collected data (all **illustrative**, not real measurements):

```text
Run/instance: svc-a / PID 4721 / start 11:20:00Z
Window: 11:25:10Z..11:26:10Z
OS: process ~170% CPU (top convention)
TID 4740: ~95% CPU on one logical core
TID 4752: ~55% CPU
Thread dump T0/T1/T2:
  nid=0x1284 (TID 4740): app.Worker.scanQueue -> app.Worker.spin
  nid=0x1290 (TID 4752): JIT/GC/native activity needing further classification
JFR: ExecutionSample repeated in Worker.spin, with GC/compilation events present.
Control: replacing queue polling with blocking take() in staging
         reduced CPU under comparable load across multiple runs.
```

**How to read this:**

- `4721` is a hypothetical PID, `4740` / `4752` are hypothetical TIDs, and the two `nid` values illustrate base conversion. Do not copy this example as real evidence.
- Two TIDs are consuming CPU concurrently so the process total can exceed 100% under `top` conventions; do not conclude one thread used 170%.
- The app hot stack and JFR suggest a **likely** CPU-burning mechanism; check whether `scanQueue` is doing valid work or spinning uselessly.
- A staging test that reduces polling and lowers CPU under comparable conditions is stronger causal evidence, yet you must still verify throughput, latency, and that no messages are dropped.
- The second TID must be investigated separately; do not collapse total CPU onto one cause before accounting for the remainder.

### Why Is a CPU Drop Alone Insufficient to Confirm a Fix?

If switching to a blocking queue drops CPU from 170% to 80% while throughput also drops 80% and request backlog grows, you may only have made the program **do less work**, not fixed the bug. After a fix, compare **CPU per completed task**, throughput, p95/p99, error rate, and resource usage under the same workload. "Lowest CPU" is not the default goal of performance tuning.

## 14. Evidence Log Template for One Diagnostic Session

Record findings in a short report (fields below are a **fillable template**, not measured results):

```text
Incident ID:
UTC window:
Host / container / namespace:
JDK vendor + exact version:
JVM PID + start time + uptime:
OS CPU convention and quota:
Workload / request rate / concurrency:

T0:
  OS command + timestamp:
  Hot TID (decimal):
  Converted nid (hex):
  Thread.print path:
  Thread name, state, top frames:
T1:
  ...
T2:
  ...

JFR:
  Recording name:
  .jfc/settings and duration:
  File path + actual file name:
  jfr summary (event types/counts/time range):
  ExecutionSample stacks and relevant thread:
  CPU/GC/JIT cross-check:

Hypotheses:
  Supported by:
  Contradicted by:
  Missing evidence:
Negative control and repeated measurements:
Impact and recommended next step:
```

Fill in **actual results**, including intervals where no samples appeared. If stacks, method names, JVM command lines, or JFR files contain sensitive data, apply appropriate access controls and retention; do not paste raw dumps into public tickets. Reports should note who collected each artifact and how, so others can reproduce it.

### Suggested Quantitative Criteria Over an Interval

- `process CPU%` and `thread CPU%` using the same tool convention.
- `thread CPU time delta / wall time delta` over the same interval, if provided by the tool.
- Number of valid intervals where the TID ranked top CPU, e.g., 5/5.
- Number of snapshots showing the same top stack and matching `nid`, e.g., 3/3.
- JFR execution sample count under the matching thread/time filter, version, and settings.
- Throughput and latency across pre-, during-, and post-incident windows.

If per-thread CPU data is missing and you only have `Thread.print`, **downgrade** the conclusion to "the thread was running at location X when captured", never claiming X consumed 90% of process CPU.

## 15. End-to-End Practice Checklist

1. **Run lab:** `javac -g CpuHotLoopDemo.java`; run `busy 90` and note PID.
2. **Verify identity:** `jcmd -l`, `VM.version`, `VM.uptime`, and args/mode.
3. **OS CPU:** `top -H -p PID` / `ps -L`; identify hot TID across multiple intervals.
4. **Hex conversion:** `printf '0x%x\n' TID`; save conversion and namespace name.
5. **Thread dumps:** capture T0/T1/T2 a few seconds apart; find `nid`, name `cpu-hot-loop`, `RUNNABLE`, and top frames.
6. **JFR:** start `settings=profile` for 40 seconds, verify `JFR.check`, wait for file dump, then run `jfr summary`/`jfr print`, inspecting `jdk.ExecutionSample`.
7. **Correlate:** same PID, same window, same thread, OS + stack + JFR evidence, noting anything that contradicts the hypothesis.
8. **Control:** run `idle 90` in a **new JVM**; repeat observations and compare CPU/stack/JFR under the same settings.
9. **Conclude:** describe exact observed state, likely mechanism, sampling limits, and missing data.
10. **Clean up:** let the demo finish normally; confirm the target JVM exited; do not leave unbounded recordings or files with sensitive data without retention rules.

### Three Recommended Phrasing Levels

- **Observation:** "OS reported TID 12416 with high CPU in 5/5 intervals; `nid=0x3080` in T0/T1/T2 had top frame `busyLoop`; JFR showed many execution samples on this path."
- **Appropriate conclusion:** "Cross-source evidence **strongly aligns** with a sustained CPU-bound loop."
- **Impact verification:** "In a matched control run, switching from busy to idle dropped TID CPU as predicted; when shipping to production, test that the fix preserves functionality and throughput."

Conversely, statements like "it's `RUNNABLE` so it's definitely a dead loop" or "50 JFR samples = method ran 50 times" are **invalid**.

## 16. Common Mistakes

1. **Confusing process PID with thread TID:** `jcmd` takes PID; `top -H` shows TID/LWP; keep both recorded.
2. **Comparing decimal TID directly against hex `nid`:** convert bases first; do not guess by thread name.
3. **Reading only one thread dump:** a single snapshot may land on an unrepresentative moment.
4. **Treating `RUNNABLE` as CPU%:** runnable is a thread state, not a CPU counter.
5. **Treating `ps %CPU` as instantaneous 1-second CPU:** its accounting differs from `top`/`pidstat`.
6. **Ignoring cgroup quota/namespace:** breaks the CPU denominator and mismatches IDs.
7. **Not checking JFR recording timing:** capture might start after the hot loop already ended.
8. **Counting JFR execution samples as call counts:** stack sampling does not measure invocation counts.
9. **Comparing `default` against `profile` and blaming count increases on the app:** sampling settings differ.
10. **Not checking event enabled/period:** the file might lack data for the target method.
11. **Forgetting GC/JIT/native threads:** process CPU can be consumed outside business loops.
12. **Reading stacks without matching build source:** line numbers/methods may not align.
13. **Using `jcmd 0` or main class name instead of PID without scoping:** easily sends commands to multiple JVMs.
14. **Capturing too many dumps/recordings in production:** tools themselves add overhead and pause risk.
15. **Reflexively dumping the heap for CPU issues:** expensive and does not directly show which thread burns CPU.
16. **Treating thread name as durable native identity:** names can collide/truncate and TIDs get reused.
17. **Calling a single loop line the root cause unconditionally:** correlate with workload and business metric impact.
18. **Seeing CPU drop after a code change and forgetting throughput:** lower CPU might just mean doing less work.
19. **Skipping a negative control:** makes it hard to separate demo CPU from host/GC/JIT noise.
20. **Leaving a busy loop unbounded on shared hosts:** impacts shared resources; the demo has a finite duration.
21. **Forgetting to verify `jcmd` attached to the right process:** containers/permissions/JDK mismatches can block or misdirect it.
22. **Copying JFR/dump files containing sensitive data:** requires access control and retention policies.

## 17. Self-Check Exercises

**Question 1 — number base.** `top -H` reports decimal TID `12416`. What should you search for in a HotSpot thread dump?

**Answer:** Convert to `0x3080` and search for a header with `nid=0x3080` **in the right PID and time window**. Thread name only assists identification.

**Question 2 — thread state.** One dump shows a `RUNNABLE` thread in `Worker.run`, yet `top -H` shows 0.1% CPU for that TID. Is that enough to call it a CPU hot loop?

**Answer:** No. You need CPU time deltas/intervals; a single Runnable snapshot does not confirm CPU consumption.

**Question 3 — sampling.** JFR shows `busyLoop` in 300 execution samples. Was it called 300 times?

**Answer:** Cannot be inferred. In the demo, `busyLoop` is called **once** by the `busy` worker, yet the sampler can observe it many times while running.

**Question 4 — CPU% vs core count.** A process uses roughly 100% of one core on an 8-logical-core host. What might a host-normalized dashboard report?

**Answer:** Roughly 12.5% **under a host-normalized convention** assuming no quota/throttling or other factors, whereas tools like `top` may display near 100%. Always check the denominator.

**Question 5 — control run.** You run `busy` and `idle` in two separate JVMs. Both have thread name `cpu-hot-loop`. Does that mean their TIDs are the same?

**Answer:** No. TIDs are assigned separately by the OS; `nid` can differ completely and can be reused after a thread exits.

**Question 6 — missing evidence.** `Thread.print` repeatedly points to `busyLoop`, yet the JFR file has no `jdk.ExecutionSample` events. Does that refute the CPU hot loop hypothesis?

**Answer:** Not yet. Check enabled/period, recording window, retained data, sampler behavior, thread/time filters, JDK/tool versions, and OS CPU evidence.

**Question 7 — production triage.** The OS confirms a GC thread uses most of the CPU while application threads show many `WAITING` threads. Should you immediately rewrite a `while` loop spotted in source?

**Answer:** No. Investigate GC/allocation/heap and workload first, and avoid treating a non-hot thread's stack as the root cause.

**Final practice task:** record two runs `busy 90` and `idle 90`; for each run build a table containing PID, decimal/hex TID, 3 thread dumps, JFR recording duration, valid execution sample count, CPU intervals, and conclusion criteria. Explain **why** the three sources OS–`jcmd`–JFR mutually reinforce a hypothesis without turning any single snapshot/sample into absolute causal proof.

## 18. Official Sources and Further Reading

- [Oracle JDK 21 — `jcmd`: `Thread.print`, `JFR.start`, `JFR.dump`, `VM.version`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — `jfr`: `summary`, `print`, `metadata`, event filtering, and stack depth](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- [Oracle JDK 21 — Diagnostic Tools and `jcmd Thread.print -l` examples](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html).
- [Oracle Java 21 — `Thread.State`: RUNNABLE, WAITING, and TIMED_WAITING](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html).
- [Oracle Java 21 — `ProcessHandle`: `pid()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html).
- [Oracle JDK 21 — Java Flight Recorder API (`jdk.jfr`)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/module-summary.html).
- [Linux `proc_pid_task(5)` — per-thread IDs from `/proc/<pid>/task`](https://man7.org/linux/man-pages/man5/proc_pid_task.5.html).

**Rule to remember:** `top/ps/pidstat` answers **which thread consumes CPU**; `jcmd Thread.print` answers **where that thread was on the Java stack at capture time**; JFR answers **which execution paths were sampled over a time interval**. A convincing conclusion requires **matching PID/nid, repetition over time, matching workload, and a control test**, never a single snapshot.