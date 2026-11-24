# 4.4 Command Groups: VM Info, Threads, Heap, Compiler, JFR, and Native Memory

## Learning objectives

`jcmd` is a JDK utility that sends **diagnostic commands** to a running JVM. When investigating production Java issues, operators often see dozens of commands in `jcmd <PID> help` without knowing which ones only read state, which create heavy snapshots, which start recordings, and which are only useful if the JVM was configured at startup. This lesson organizes six groups: **VM information, threads, heap/GC, compiler/JIT, Java Flight Recorder (JFR), and Native Memory Tracking (NMT)**.

After this lesson, you will be able to:

- Choose a command group based on **symptoms** rather than running a barrage of unnecessary commands.
- Interpret common outputs: VM startup flags, thread/lock states, class histograms, code cache, JFR recordings, and NMT reserved/committed memory.
- Distinguish **observation-only commands** from commands that mutate JVM state or have high impact such as `GC.heap_dump`, `GC.class_histogram`, `JFR.start`, and `VM.native_memory baseline`.
- Perform a safe diagnostic pass on HotSpot/JDK 21, verify command names via `help`, tie evidence to the exact PID/timestamp, and keep sensitive data within authorized boundaries.
- Understand **each tool's limits**: a thread dump is not a CPU profile, a heap histogram does not prove a leak by itself, JFR does not capture the past before it was enabled, and NMT is not equal to total process RSS.

The primary examples use **HotSpot JDK 21**. Diagnostic command lists and syntax can vary by vendor, VM implementation, JDK version, and permissions. Always check available commands on the target JVM before using them.

## 1. How to read the jcmd command system

### 1.1 Identify the right PID and check help

In a terminal with JDK `jcmd`, the command:

```bash
jcmd -l
```

can list Java processes visible to the tool. This list **may exclude JVMs in separate namespaces/containers**. If you get a PID from systemd, Kubernetes, a Windows service, or a process manager, cross-check the service, container/pod, process start time, and actual JVM; a PID alone can be reused after a restart.

With the real PID of a running HotSpot JVM:

```bash
jcmd 12345 help
jcmd 12345 help VM.flags
jcmd 12345 help Thread.print
jcmd 12345 help JFR.start
```

**12345 is only an illustrative PID** and must be replaced with a verified PID. `help` shows the names and options **supported by the target JVM**, making it safer than copying commands from another environment or a post written for a different JDK. If `jcmd 12345 help` reports a command does not exist, do not guess new names; check the version, implementation, and corresponding docs.

`jcmd` sends requests to a JVM on the **same machine**, requiring matching effective user/group and attach permissions. Container PID namespaces, security policies, minimal runtime images, a JVM started with attach disabled, or non-HotSpot implementations can all block access. An attach failure does not prove the process is not Java.

### 1.2 Do not equate "diagnostic" with non-intrusive

In `jcmd` documentation, each command carries **Impact: Low / Medium / High**, a relative impact estimate rather than a runtime duration guarantee. Most VM info commands are light; thread dumps scale in cost with thread count; histograms and heap dumps can have heavy impact; starting/stopping JFR changes collection activity; NMT baseline changes the comparison mark.

| Impact level / group | Examples | Operational meaning |
| --- | --- | --- |
| State reading, usually light | `VM.version`, `VM.flags`, `Compiler.queue`, `Compiler.codecache`, `JFR.check` | Quick snapshots; still limit frequency and access permissions |
| Observation scaling with data size | `Thread.print`, `GC.heap_info`, `VM.metaspace`, `VM.native_memory summary` | Measure overhead; avoid tight polling loops across many replicas |
| Heavy / high-volume snapshots | `GC.class_histogram`, `GC.heap_dump` | May pause threads/require safepoints or GC, consuming CPU, I/O, disk, and time |
| Diagnostic state control | `JFR.start`, `JFR.dump`, `JFR.stop`, `VM.native_memory baseline` | Creates/changes recordings or sets baselines; requires clear goal, duration, permissions, and output path |
| Mutates JVM behavior, avoid when only reading | `GC.run`, `VM.set_flag`, `VM.log`, `Compiler.directives_add` | Not part of passive information gathering; evaluate impact and rollback separately |

Printing "statistics" does not make a command cheap. In particular, `GC.heap_dump` may request a **full GC** before dumping by default; JDK 21 docs note the exception when `-all` is selected. Do not use `GC.run` to "check GC" when you only need to observe: it performs a call equivalent to `System.gc()`.

### 1.3 Map of the six groups

```text
jcmd <PID> help
      |
      +-- VM.*             -> VM version, command line, flags, properties, uptime
      +-- Thread.*         -> stacks, thread states, lock evidence
      +-- GC.*             -> heap info, object histogram, heap dump (use caution)
      +-- Compiler.*       -> JIT queue, code cache, compiled methods
      +-- JFR.*            -> check/start/dump/stop Java Flight Recording
      +-- VM.native_memory -> native memory via NMT (if enabled at startup)
```

A command name is not a uniform API across every JVM. For example, `Thread.dump_to_file` appears in newer JDKs, but **should not be assumed present in HotSpot JDK 21**; this lesson uses `Thread.print`, which is documented in JDK 21. Likewise, commands from other JVM implementations may have different names/syntax; obtain `help` from the **target VM itself**.

## 2. VM group: identifying the process instance and effective configuration

VM info commands should be used first because they ensure you are analyzing the right run and allow others to reproduce findings.

```bash
jcmd 12345 VM.version
jcmd 12345 VM.uptime
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
jcmd 12345 VM.system_properties
```

### 2.1 Meaning and limitations

| Command | Evidence obtained | Limitations to remember |
| --- | --- | --- |
| `VM.version` | Running VM name/version/build | Not `java -version` invoked by the current terminal |
| `VM.uptime` | How long the JVM has been up; `-date` can include date per command | Combine with process start time when restarts occur; does not prove app health |
| `VM.command_line` | JVM command line info at startup | May contain secrets; startup args do not reflect all runtime changes |
| `VM.flags` | VM flags and current values shown by the command | Not identical to the full original shell command line |
| `VM.flags -all` | Flags supported by the VM, including current/default/ergonomic values per implementation | Does not mean every flag was passed via CLI by an operator |
| `VM.system_properties` | Java system properties at read time | Can be altered in code via `System.setProperty`; output easily exposes credentials |

On HotSpot JDK 21, `VM.info` can provide a broader environment/state report and is usually lightweight, though it may contain extensive internal data. When deeper detail is needed, run `jcmd 12345 help VM.info` to confirm availability first, then check sharing scope for the output.

**Distinguish three configuration layers:**

1. **Startup inputs**: `-Xms`, `-Xmx`, `-XX`, `-D`, `-javaagent`, and VM options received at launch. Inspect via `VM.command_line` and, where appropriate, `RuntimeMXBean.getInputArguments()`.
2. **Current effective VM flags**: `VM.flags`/`VM.flags -all` can include values selected by VM ergonomics based on JDK/GC/memory/container limits, or modified at runtime if supported.
3. **Application arguments**: parameters after the main class or `-jar app.jar` handled by `main(String[] args)`/frameworks; do not conflate with VM input arguments.

For example, `-Xmx2g` is a startup option, whereas `MaxHeapSize` is the flag name representing the heap limit the JVM uses. If `VM.flags -all` shows `MaxHeapSize` while `VM.command_line` lacks `-Xmx`, the JVM may have derived the value from defaults or memory limits. The two outputs do not contradict each other.

**Security:** `VM.command_line` and `VM.system_properties` can contain JDBC URLs, `-Dpassword`, tokens, internal paths, and truststore credentials. Do not paste raw stdout into public tickets/chats. Collect via authorized procedures, filter with key allowlists, and redact before saving; diagnostic data can leak secrets even when commands are read-only.

### 2.2 When to choose the VM group?

- The JVM is "running JDK 21" yet throws `UnsupportedClassVersionError`: verify `VM.version`, vendor, runtime properties, and class-file compatibility; the SSH shell's `java -version` may belong to a different JDK.
- Production GC/heap differs from YAML: compare `VM.command_line`, `VM.flags`, and process/container limits; do not assume intended values match what the JVM actually uses.
- Only one replica fails: capture the VM/JVM and app build fingerprint of both the **failing replica** and a healthy reference replica, tagged with PID/start time/UTC.
- Diagnostic results change after a restart: check `VM.uptime`, process start time, and deployment metadata to avoid mixing evidence from two runs.

The VM group answers **"which process is this, under what execution settings?"**; it does not directly explain high CPU or hung requests.

## 3. Thread group: Thread.print and contention evidence

### 3.1 Syntax and purpose

```bash
jcmd 12345 Thread.print
jcmd 12345 Thread.print -l
jcmd 12345 Thread.print -e
```

On HotSpot JDK 21:

- `Thread.print` prints stack traces and states of threads observable by the command; useful for finding threads in `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`.
- `Thread.print -l` adds details about **`java.util.concurrent` locks** when available; helps identify lock waiting relationships in a snapshot.
- `Thread.print -e` enables extended thread info per implementation; rely on actual output to see which fields appear.

Per JDK 21 docs, `Thread.print` has **Medium** impact, scaling with thread count. A server with thousands of threads can produce huge output; do not set up a cron dumping every few milliseconds or hit all replicas simultaneously without assessing cost.

### 3.2 How to read the output

**Abbreviated illustrative** example, not stdout from a specific JVM:

```text
"worker-17" ... java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.OrderService.update(OrderService.java:87)
    - waiting to lock <0x...> (a java.lang.Object)
"worker-4" ... java.lang.Thread.State: TIMED_WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
```

Explanation:

- `BLOCKED` usually indicates a thread wants to enter a monitor held by another thread, not that process CPU is saturated.
- `WAITING`/`TIMED_WAITING` can be normal behavior (queues, pools, timers, sleep) and must be interpreted in context.
- `RUNNABLE` does not always mean the thread is continuously burning CPU; it also reflects how the JVM/OS represents thread state.
- A stack snapshot shows **location at capture time**, not what percentage of total CPU that method consumed.
- Lock data helps form contention/deadlock hypotheses, but requires correlating related threads, owners, dumps at multiple timestamps, and JFR lock/park events when appropriate.

### 3.3 Capturing multiple snapshots safely

When requests stall intermittently, rather than concluding from one dump, take a few timestamped snapshots across the incident window—for example one near the start, one mid-incident, and one near the end. Spacing depends on symptom duration; data must be tagged with service/PID/start time to avoid mixing across restarts.

Do not run `jcmd 12345 Thread.print > threads.txt` without knowing where the terminal runs and whether writing there is permitted. **Redirection with `>` is a shell action**, so the file is created on the shell's machine, whereas heap/JFR dumps are created by the VM at paths seen by the **target process**. This is a critical distinction when diagnosing across containers or remote shells.

For **virtual threads** (JDK 21), some traditional commands do not by default list every unmounted virtual thread. Do not conclude "no virtual threads are waiting" just because they are missing from `Thread.print`. For virtual-thread-heavy applications, use JFR and thread dump/observability mechanisms appropriate to your JDK/implementation; check `help` before relying on syntax from newer Java versions.

## 4. Heap/GC group: GC.heap_info, histogram, and heap dump

These three commands look related yet serve different purposes and carry different impacts:

```bash
jcmd 12345 GC.heap_info
jcmd 12345 GC.class_histogram
jcmd 12345 GC.heap_dump /path/approved/heap-12345.hprof
```

The last command is **a syntax example only** and can create a multi-GB file with major impact. **Do not run a heap dump in production merely while learning the command group.**

### 4.1 GC.heap_info: snapshot of heap layout/status

`GC.heap_info` gives an overview of the Java heap according to the target collector/JDK, with **Medium** impact. Use it when you need heap size/usage, regions/generations, and GC context at collection time. Output varies by collector, JVM version, and state, so fields are not fixed.

Conceptual check: heap `used` is the amount of Java heap reported as in use by the VM at measurement time; **it is not total resident set size (RSS)**, nor does a single capture prove a memory leak. A Java process also holds thread stacks, metaspace, code cache, direct/native memory, and memory mappings.

When heap usage is high, compare multiple timestamps and workloads (especially post-GC), measure allocation rate, GC pauses, and memory limits. High yet stable heap may be normal; heap climbing over multiple cycles under comparable load warrants deeper analysis.

### 4.2 GC.class_histogram: object distribution by class

`GC.class_histogram` displays instance counts and bytes per class, useful for spotting classes with unusually high object totals such as `byte[]`, `char[]`, `java.util.HashMap$Node`, or a specific DTO. JDK 21 docs mark it **Impact: High**.

```bash
jcmd 12345 help GC.class_histogram
jcmd 12345 GC.class_histogram -all
```

With `-all`, the command includes **unreachable objects** rather than only objects per default mode. This scope can change conclusions because objects not yet collected by GC are not necessarily still referenced by the application. Do not equate a histogram with live heap growth or retained size.

What a histogram **does not provide on its own**: object graph/reference chains retaining objects, retained size by GC roots, lifecycle, or allocation paths. If `byte[]` tops the byte list, you only know which type occupies significant space **at measurement time**; you do not yet know what retains them, whether it is a valid cache or a leak, or whether most will be reclaimed in the next GC cycle.

Do not run histograms repeatedly to build an "allocation profile": it is a high-impact snapshot operation, not lightweight allocation sampling. To find allocation sites, consider JFR allocation events and targeted GC telemetry.

### 4.3 GC.heap_dump: creating an HPROF for object graph analysis

`GC.heap_dump` creates a heap dump file, typically analyzable with Eclipse Memory Analyzer/JMC or equivalent tools. On JDK 21, documentation notes **High** impact depending on heap size/content; **by default it requests a full GC unless `-all` is specified**. Thus impact includes not only file I/O but also possible pauses and heap state changes at capture time.

```bash
# Reference syntax; RUN ONLY after evaluating cost and obtaining authorization.
jcmd 12345 GC.heap_dump /path/approved/heap-12345.hprof
```

Before collecting: verify disk capacity/filesystem of the JVM process, unique filename, access permissions, timeouts, service impact, and retention/deletion policy. The path is where the **target JVM** writes the file; it will not automatically appear on the laptop running the command if the JVM runs in a container or another machine. Heap dumps can contain passwords, tokens, personal data, request strings, and sensitive object values.

Do not use `-all` as a "guaranteed cheap/safe mode": it changes the captured object set (including unreachable objects) and GC interaction, and can still produce a huge dump. If you only want a heap overview, pick `GC.heap_info` first. State command names, options, and goals explicitly to avoid someone running a full heap dump when asked for "heap stats".

### 4.4 Control-oriented GC commands

`GC.run` asks the JVM to invoke `System.gc()`; `GC.run_finalization` asks it to invoke `System.runFinalization()`. They can cause impact and are not passive snapshots. Do not treat `GC.run` as a "standard gauge" to check production health, because the action itself alters the data you intend to observe.

**Choose by problem:** heap pressure → `GC.heap_info` plus GC events; suspecting a class holds too many objects → controlled histogram; need retained references → heap dump when impact budget and permissions allow; suspecting high allocation rate → JFR allocation profiling instead of repeated histograms.

## 5. Compiler/JIT group: Compiler.queue, codecache, codelist

Java HotSpot uses JIT compilation. As the application warms up, code is compiled from bytecode to native machine code to improve performance; the compile queue and code cache reflect these activities, though they do not directly measure request latency or method invocation counts.

```bash
jcmd 12345 Compiler.queue
jcmd 12345 Compiler.codecache
jcmd 12345 Compiler.codelist
jcmd 12345 Compiler.directives_print
```

### 5.1 Compiler.queue

`Compiler.queue` lists methods **waiting for compilation** at call time, **Low** impact per JDK 21 docs. A large/persistent queue under a specific workload can suggest warm-up activity or compiler pressure, but must be correlated with throughput, CPU, JFR/compiler events, JIT compiler threads, and system state.

**An empty queue does not mean** no compilation occurred/is occurring, no interpreted code remains, or the app has reached steady-state performance. It is merely a snapshot of the queue reported by the command.

### 5.2 Compiler.codecache

`Compiler.codecache` displays the layout and limits of the **code cache** where HotSpot stores compiled native code, **Low** impact. When logs/JFR indicate a full code cache or restricted compilation, this command helps inspect code heap segments and remaining capacity.

The code cache resides in **JVM native memory**, outside the Java heap `-Xmx`. Hence free GC heap **does not rule out** code cache pressure. Code heap names and layout depend on VM/JDK/options; do not assume every segment always exists.

### 5.3 Compiler.codelist

`Compiler.codelist` lists live compiled methods in the code cache, **Medium** impact. The list can be very long; use it when investigating compiler state or checking whether a method has compiled code. A method absent from one snapshot **does not prove** it never executed—it may be interpreted, deoptimized, have a changed compiled entry, or no longer sit in the cache.

### 5.4 Compiler.directives_print and other commands

`Compiler.directives_print` only prints **active compiler directives**. Conversely, `Compiler.directives_add`, `Compiler.directives_clear`, and `Compiler.directives_remove` modify directives, so avoid them during read-only diagnostics. `Compiler.perfmap` on Linux creates a map file for `perf`, which also has a file-writing side effect.

Scenario: an app is slow for the first 30 seconds and then stabilizes. Compare warm-up vs. steady-state using request latency/CPU/JFR alongside `Compiler.queue`, `Compiler.codecache`, `VM.flags`, and compiler event data. **Do not conclude "JIT is the root cause" just because the queue once had methods**; the queue is one piece of evidence to align with the incident timeline.

## 6. JFR group: capturing CPU, allocation, GC, and lock timelines

Java Flight Recorder (JFR) collects JVM/application events and samples to analyze behavior **over time**. A `.jfr` file typically contains many event types—CPU execution samples, allocations, GC pauses, threads, locks, I/O, etc.—depending on **settings** and event thresholds. JFR both provides recording controls via `jcmd` and generates observation/profiling data.

### 6.1 Checking running recordings (read state)

```bash
jcmd 12345 JFR.check
jcmd 12345 JFR.check name=triage
jcmd 12345 JFR.check name=triage verbose
```

Without `name`, `JFR.check` reports active recordings. `verbose` can display event settings; follow the target JVM's `help`. Having no active recording **does not prove JFR cannot run**, and having no old JFR file does not mean the JVM never recorded previously.

### 6.2 Quick 60-second capture with profile settings

When you have a clear goal and have assessed overhead, you can run a bounded JFR session:

```bash
jcmd 12345 JFR.start name=triage settings=profile duration=60s filename=triage.jfr
jcmd 12345 JFR.check
```

- `name=triage` names the recording for referencing via `JFR.check`/`JFR.stop`.
- `settings=profile` uses a preset with higher detail than `default`, typically suitable for **short durations**; do not assign a fixed overhead across all workloads.
- `duration=60s` gives the recording a bounded duration and stops it automatically afterward. If `filename` is specified, the file is written when the recording stops per configuration.
- `filename=triage.jfr` is a path writable by the **target JVM**; relative paths resolve against the target process's working directory.
- If the incident ended before the recording started, the contents only describe the **subsequent period** and cannot retroactively recover past data.

Once the file exists, use `jfr summary` to inspect event types/counts, or open it in JDK Mission Control (JMC). Contents vary by collector, settings, workload, and sampling; never fabricate CPU or GC numbers from an unexecuted example.

```bash
jfr summary triage.jfr
```

The `jfr` command above is a **JDK file-reading tool**, not a diagnostic command attached to a process via `jcmd`. You need the file readable from the analysis environment.

### 6.3 Rolling recording: keeping pre-incident evidence

When incidents are brief and hard to reproduce, a bounded `default` recording can retain a window of history:

```bash
jcmd 12345 JFR.start name=rolling settings=default disk=true maxage=15m maxsize=256m
jcmd 12345 JFR.check name=rolling
```

When an alert fires while the recording is still running:

```bash
jcmd 12345 JFR.dump name=rolling filename=incident.jfr maxage=10m
```

When you no longer need to keep the recording active:

```bash
jcmd 12345 JFR.stop name=rolling
```

Understand the three operations:

1. `JFR.start` **starts a recording** and alters collection state. Without `duration`, by default the recording may run until stopped.
2. `JFR.dump` **exports current data to a file while the recording keeps running**. `maxage` on dump only bounds the history written into the file; it cannot include events already discarded earlier.
3. `JFR.stop` **stops the recording**. It is not the same as `JFR.dump`; keep them distinct to avoid losing monitoring early or forgetting to stop a long-running recording.

`maxage=15m` on a recording is a data age limit; `maxsize=256m` is an on-disk size limit. Under high event rates, older data can be evicted before 15 minutes even if the age limit is not reached. `settings=default` has lower overhead than `profile` under typical conditions, yet still carries overhead and requires retention management.

Commands such as `JFR.configure` change recorder configuration; `path-to-gc-root` can prolong work and affect pauses. Do not add such options indiscriminately to an ordinary CPU latency case. A JFR file can contain class/method names, stacks, paths, URLs, properties, and sensitive values depending on enabled events; protect access like any production artifact.

### 6.4 Interpreting JFR accurately

- **CPU samples** show stack distribution during sampled intervals, not every request or every stack frame that ever ran.
- **Allocation events** point to object creation sites within sampling/event settings; they do not equate to retained objects/leaks.
- **GC events** include timestamps/pause durations for correlating with p99 latency, but temporal coincidence alone does not prove GC is the sole cause.
- **Lock/park events** require checking thresholds/settings, involved threads, and workload.
- A 60-second recording **does not represent** a rare incident occurring every 2 hours if captured at the wrong time. Choose duration and triggers according to incident behavior.

## 7. Native Memory group: VM.native_memory and NMT prerequisites

### 7.1 What is Native Memory Tracking?

Native Memory Tracking (**NMT**) is a **HotSpot** feature that tracks many native/internal memory allocations of the JVM: Java heap reserved/committed, class/metaspace, threads, code, GC, compiler, and several other subsystems. It is especially helpful when **process RSS/memory grows while Java heap used does not grow accordingly**.

What NMT **is not**:

- NMT is not equal to the process's resident bytes reported by the OS/container.
- NMT does not fully track all allocations from **JNI/third-party native code** or certain JDK library areas; output can omit memory outside NMT's scope.
- NMT `reserved` is reserved virtual address space, not physical RAM currently in use. `committed` is memory the VM has committed within tracked areas; it is also not exact RSS.
- An NMT report does not replace a heap dump for finding Java objects holding references.

On HotSpot, NMT is **off by default** and must be enabled at **JVM startup**:

```bash
# Example of a fresh launch, not a command controlling a running PID:
java -XX:NativeMemoryTracking=summary -jar application.jar
```

There are two main levels: `summary` for category totals and `detail` for detailed call sites; `detail` carries higher overhead and must be chosen appropriately at startup. Oracle documents NMT overhead at roughly **5–10%**, so do not treat it as a free option for every production workload.

**You cannot turn NMT from off to summary/detail via `jcmd` on a running HotSpot JVM**; it can only be shut down if supported by the VM, and shutdown may not be restartable within that process. If you see "Native memory tracking is not enabled", do not repeatedly run `VM.native_memory baseline` or assume rising RSS has no issue. To have NMT next time, choose the startup option and an appropriate deployment plan.

### 7.2 Report, baseline, and diff syntax

When the JVM **already runs with NMT enabled**:

```bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory summary scale=MB
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff
```

- `summary`: aggregated **reserved/committed** view by category plus total tracked by NMT.
- `scale=MB`: changes display unit; does not change memory consumption.
- `baseline`: sets a **new comparison mark**, changing the state of NMT measurement (not directly altering application config).
- `summary.diff`: difference from the latest baseline; without a baseline, no comparison exists.
- `detail`/`detail.diff`: requires NMT enabled at **detail** and matching call-site data; do not expect detailed stack call sites from `summary`.

When using `detail`, for example:

```bash
# Only appropriate if the JVM was started with -XX:NativeMemoryTracking=detail.
jcmd 12345 VM.native_memory detail
jcmd 12345 VM.native_memory detail.diff
```

NMT `baseline` does not evaluate "baseline quality"—if set while the JVM is still starting up, normal subsequent class loading/JIT memory growth can be mistaken for a leak. Take the baseline after warm-up and compare **the same workload phase** across enough points in time.

### 7.3 Example of interpreting NMT

Suppose an illustrative output shows:

```text
Total: reserved=4000MB, committed=900MB
- Java Heap (reserved=2048MB, committed=512MB)
- Thread    (reserved=220MB, committed=30MB)
- Code      (reserved=250MB, committed=64MB)
...
```

These are **hypothetical numbers to explain terminology**, not exact stdout formatting from a real JVM. You cannot conclude "the JVM is using 4 GB of RAM" because reserved is 4 GB. Nor can you conclude RSS is exactly 900 MB because NMT committed memory does not measure all native allocations and does not equal OS resident pages.

Suppose `summary.diff` 20 minutes later reports `Thread` committed increased by 80 MB; ask whether thread count/stack memory grew, workload shifted, or a thread-creation mechanism is not releasing threads. If `Code` grows during warm-up, that can be normal JIT compilation. If `Class`/metaspace grows, check classloaders and class unloading. **A diff is trend evidence, not yet the cause of a leak**.

### 7.4 Combining with other tools

- **Large heap**: compare `GC.heap_info`, heap usage/GC metrics, allocations, and histogram if needed.
- **Metaspace/class growth**: `VM.metaspace` or `VM.classloader_stats` if supported by the JVM; `VM.metaspace basic` on HotSpot JDK 21 gives concise stats, impact depending on options.
- **Thread/native stack growth**: `Thread.print`, thread count, OS/process thread count, and NMT `Thread` category.
- **Code cache**: `Compiler.codecache` and NMT `Code` category.
- **RSS grows while NMT stays flat**: may involve native allocations outside NMT scope, mappings, direct/native libraries, or resident page behavior; use OS/container figures and valid native tools to proceed.

Do not mistakenly add Java heap `used` to NMT total as if they were completely disjoint: NMT already includes Java Heap reserved/committed. Do not treat NMT categories like heap histogram object classifications; they are **two different levels of observation**.

## 8. Command selection table by symptom

| Symptom / question | Start with | If deeper analysis is needed | Avoid confusing |
| --- | --- | --- | --- |
| Which JVM and flags is the service running? | `VM.version`, `VM.uptime`, `VM.flags` | `VM.command_line`, redacted selected properties | Startup inputs differ from effective flags; do not use shell's `java -version` for target |
| Hung requests or lock contention | `Thread.print` (a few snapshots), metrics | `Thread.print -l`, JFR lock/park events | A single `WAITING` stack is not a deadlock |
| High process CPU, need hotspots | CPU metrics, `JFR.check` | Bounded JFR profile or suitable CPU profiler | A lone `Thread.print` is not a CPU profile |
| Heap near limit / frequent GC | `GC.heap_info`, GC logs/JFR events | Controlled histogram or heap dump | A heap snapshot does not prove a leak |
| Suspect a class retains many objects | `GC.class_histogram` if cost is acceptable | `GC.heap_dump` and retained reference analysis | Histogram counts do not show the reference graph |
| Slow warm-up / JIT | `Compiler.queue`, `Compiler.codecache` | `Compiler.codelist`, JFR compiler events, flags | Point-in-time queue does not conclude latency root cause |
| Growing native memory / RSS | Heap + OS RSS + NMT status | `VM.native_memory summary`/diff **if NMT enabled** | Reserved ≠ committed ≠ RSS; NMT does not cover all native allocations |
| Brief / rare incident | Metrics, logs, existing JFR recording | `JFR.dump` retained history, trigger capture | JFR started late does not record prior events |

The order above is a **starting point**, not a requirement that every incident run every group. The goal is choosing the **fewest commands needed for sufficient evidence**.

## 9. Java 17+ Lab: sample JVM to test all six groups

Create file **`JcmdLab.java`**. The program keeps a JVM alive for 120 seconds, spawns a sleeping background thread, and computes a simple loop. It suffices to observe PID, threads, heap, compiler state, and test JFR/NMT in a learning environment. Never target a production JVM with high-impact commands for lab practice.

```java
public final class JcmdLab {
    private static volatile long result;

    public static void main(String[] args) throws InterruptedException {
        System.out.println("JcmdLab READY");
        System.out.println("PID=" + ProcessHandle.current().pid());

        Thread sleeper = new Thread(() -> {
            try {
                Thread.sleep(120_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "demo-sleeper");

        sleeper.start();

        long sum = 0;
        for (long i = 0; i < 2_000_000; i++) {
            sum += i % 7;
        }
        result = sum;

        sleeper.join();
        System.out.println("JcmdLab DONE");
    }
}
```

Compile and run with JDK 17+ (the jcmd command examples target **HotSpot JDK 21**):

```bash
javac JcmdLab.java
java -XX:NativeMemoryTracking=summary JcmdLab
```

**Exact first stdout line**:

```text
JcmdLab READY
```

The next line is `PID=<actual PID>`; after the background thread finishes sleeping for 120 seconds, the program prints `JcmdLab DONE`. Runtime duration and PID are not fixed; you can stop early with Ctrl+C. The `-XX:NativeMemoryTracking=summary` option **applies only to the newly launched demo JVM**; it is not an action that turns on NMT for an already running JVM.

In another terminal, use the PID printed by the program, e.g., **12345**:

```bash
jcmd 12345 help
jcmd 12345 VM.version
jcmd 12345 VM.uptime
jcmd 12345 VM.flags
jcmd 12345 Thread.print
jcmd 12345 GC.heap_info
jcmd 12345 Compiler.queue
jcmd 12345 Compiler.codecache
jcmd 12345 JFR.check
jcmd 12345 VM.native_memory summary
```

Grounded expectations:

- `VM.version` confirms the **JcmdLab** runtime, and `VM.uptime` increases with elapsed time.
- `Thread.print` can show the thread named `demo-sleeper` in a sleeping/timed-waiting state **if captured before it finishes**. Do not expect identical thread counts, ordering, or every stack across machines.
- `GC.heap_info` reports heap data depending on collector; `Compiler.queue` may be empty because the demo is tiny—do not treat that as an error.
- `JFR.check` before starting normally has no recording created by the demo; the JVM might still have another recording from startup options.
- `VM.native_memory summary` shows NMT data by category because the demo JVM was started with `summary`; numbers depend on the environment.

If you want to try a short JFR capture on **JcmdLab**:

```bash
jcmd 12345 JFR.start name=lab settings=profile duration=20s filename=jcmd-lab.jfr
jcmd 12345 JFR.check
```

Run while the JVM still has enough time left (within the 120 seconds). After 20 seconds, check the file on the filesystem used by the demo JVM; inspect it with `jfr summary jcmd-lab.jfr`. There is no fixed stdout because activity and the JVM determine events/samples.

To practice `baseline`/diff, only on the demo JVM with NMT:

```bash
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff
```

Two measurements taken close together may show small changes or fluctuations; do not expect to see a "memory leak" since this program creates none. Practice prioritizes observation commands; neither `GC.heap_dump` nor `GC.class_histogram` is needed to complete the lab, as they have high impact and add little value for a tiny demo.

### What QA should verify in the lab

1. Every command uses the **real PID**, never copying `12345` onto an unrelated process.
2. `jcmd` runs in an environment with attach permission, compatible JVM, and matching namespace while the process is still alive.
3. `VM.native_memory` works due to the startup flag `-XX:NativeMemoryTracking=summary`, not because `jcmd` turned NMT on automatically.
4. `JFR.start` generates data depending on workload/settings; `JFR.check` only reports recording state.
5. `Thread.print` is a snapshot; `demo-sleeper` disappears after 120 seconds.
6. `GC.heap_info`, `Compiler.queue`, and `NMT` are read and interpreted using **actual observed values**, without copying fake sample numbers into reports.

## 10. Production diagnostic workflow in increasing order of intrusion

### Step 1: Frame the question and select the process

Record the incident, `t_start`/`t_detect`, service, pod/container/node, PID, process start time, version/deploy revision, and request scope. Some tools print command lines containing secrets; decide immediately on storage location and sharing restrictions.

### Step 2: Gather lightweight evidence and fingerprint

Typically start with `VM.version`, `VM.uptime`, `VM.flags`, and existing OS/JVM metrics. If the command line is needed, read it in a restricted environment and **redact**. Never run simultaneous heap dumps or profiles across all replicas.

### Step 3: Pick a group by symptom

- **Threads/locks** if latency is high yet CPU is low or requests are stuck.
- **GC.heap_info** if heap/GC shows abnormal behavior.
- **Compiler.queue/codecache** if slow startup or JIT/cache pressure is suspected.
- **JFR** to analyze CPU/allocation/GC/lock timelines across the exact incident phase.
- **NMT** if native memory grows and the JVM has NMT enabled; if NMT is off, document the limitation instead of trying to enable it live in-process.

### Step 4: Set an impact budget

For each command, record Impact, duration, output size, disk space, CPU/memory overhead, replica count, permissions, and stop criteria. If a histogram/heap dump is needed, run it only after weighing full GC/pause effects, sensitive data risk, and file destination.

### Step 5: Read evidence with exact semantics

Separate snapshots from time-series data; separate **correlation** from **causation**. A JVM with many `WAITING` threads is not necessarily deadlocked; `byte[]` dominating the heap is not necessarily a leak; `Code` NMT growth after startup is not necessarily a bug; a GC event overlapping a latency spike still requires checking traffic, blocking, and other factors.

### Step 6: Clean up stateful operations

If you started an unbounded JFR recording, define when to stop/dump it and clean up artifacts. NMT baseline is only a new reference point and should not be reset indiscriminately while others are comparing against it; do not run `VM.native_memory shutdown` unless you genuinely want to turn NMT off and accept it cannot be re-enabled via `jcmd`. Heap dump/JFR files must follow access control, retention, and data policies.

### Step 7: Report and re-verify

State the exact commands executed, UTC timestamps, version/JDK, PID/start time, relevant flags, observed values, **and measurement limitations**. After controlled remediation, use metrics/JFR/traces under comparable load to evaluate results. If no evidence exists from the incident window, state "insufficient data" instead of extrapolating current output backward to the past.

## 11. Common confusions

| Confusion | Accurate explanation |
| --- | --- |
| `jcmd -l` lists every JVM on the host and in every container. | PID namespaces, permissions, and implementations affect the list; identify the target properly. |
| All `jcmd` commands are read-only and completely safe. | `JFR.start/stop` change recording state; histogram/dump have high impact; `GC.run` triggers GC. |
| `VM.flags` is verbatim what the operator passed at startup. | It shows current flags/values, which may include defaults/ergonomics and runtime changes. |
| One `Thread.print` proves a CPU hotspot or deadlock. | Only a snapshot; requires multiple timestamps, lock owners, profiles/metrics, and load context. |
| JDK 21 `Thread.print` includes every unmounted virtual thread. | Not by default; requires JDK-appropriate tooling/recordings for virtual thread states. |
| `GC.heap_info` equals process RSS. | Java heap is only part of process memory; there are also native memory, code cache, stacks, and mappings. |
| `GC.class_histogram` identifies the exact object causing a leak. | Histograms aggregate by class and do not show reference paths retaining objects. |
| `GC.heap_dump` only writes a file without affecting the app. | Can trigger full GC, pauses, and heavy I/O; contains sensitive data. |
| Empty `Compiler.queue` means the JVM is not using JIT. | The queue is a point-in-time snapshot; compiled methods can still reside in the code cache. |
| Empty `JFR.check` means the JVM cannot use JFR. | It only lists current recordings; the JVM may support starting a new one. |
| Running `JFR.start` after an incident captures the earlier cause. | Recordings only hold history if already enabled/retaining data beforehand. |
| `JFR.dump` stops the recording. | Dump exports data while the recording keeps running; stop with `JFR.stop`. |
| `VM.native_memory summary` enables NMT automatically if off. | NMT must be enabled at startup; the report command does not enable tracking. |
| NMT `reserved` is the RAM the process is currently using. | Reserved address space differs from committed and differs from RSS. |
| NMT covers every native allocation from JNI/third-party libraries. | NMT covers HotSpot-internal tracked areas; outside regions require additional tools. |
| Increasing NMT diff always means a memory leak. | It can be warm-up, compiler, class loading, thread count, or workload changes. |

## 12. Self-assessment questions

**1.** A service has 600 hung requests with low CPU. Should you run `GC.heap_dump` immediately?

**Answer:** No. Start with request/queue/pool metrics, `Thread.print` (a few snapshots), and lock/wait evidence; if needed, JFR lock/park events. A heap dump carries high impact and does not directly tell you what threads are waiting on.

**2.** `VM.flags -all` shows `MaxHeapSize`, while `VM.command_line` has no `-Xmx`. Is there a contradiction?

**Answer:** No. The JVM can select heap size via defaults/ergonomics/resource limits. Startup arguments and effective flags are two different data layers.

**3.** Code cache grows during a few minutes of warm-up, and `Compiler.queue` has entries. Is that enough to conclude JIT is faulty?

**Answer:** Not enough. JIT compilation and code cache growth are normal during warm-up. Correlate latency, CPU, codecache status, compiler events, flags, and steady-state baselines.

**4.** A JVM does not have NMT enabled; can you run `jcmd PID VM.native_memory baseline` to start tracking memory?

**Answer:** No. On HotSpot, NMT must be enabled with `-XX:NativeMemoryTracking=summary` or `detail` at startup. If not enabled, use OS/heap/JFR data as appropriate and note the limitation.

**5.** NMT reports `reserved=5 GB`, `committed=1.2 GB`, and the OS reports RSS 1.4 GB. Can you add 5 + 1.2 + 1.4?

**Answer:** No. Those are different concepts/metrics with significant overlap. Reserved is not resident RAM; NMT committed is not RSS, and NMT does not cover every native allocation.

**6.** A JFR rolling recording is running. You want to save the last 10 minutes while continuing capture—which command do you pick?

**Answer:** `jcmd PID JFR.dump name=<recording> filename=<file> maxage=10m` if the recording is running, still holds enough history, and the file path is valid. `JFR.dump` does not stop the recording; use `JFR.stop` only when you truly want to end it.

**7.** `GC.class_histogram` shows many `byte[]`. Can you conclude a cache leak?

**Answer:** Not yet. You need to inspect live objects, reference chains/retained sizes, lifecycle, and trends over time. A large histogram can reflect legitimate workload data.

**8.** After running `JFR.start settings=profile duration=60s`, process CPU rises. Does that prove the original app inherently had high CPU?

**Answer:** Not yet. Recording has overhead; compare before/after baselines under matching settings/duration and equivalent workload. Do not ignore measurement cost when interpreting cause.

## 13. Quick takeaway

- **VM** answers *"Which JVM is this, and how is it configured?"*.
- **Thread** answers *"Where are the threads and what resources are they waiting on at capture time?"*.
- **Heap/GC** answers *"How are Java heap and object types distributed?"*, with cost jumping sharply for histograms/dumps.
- **Compiler/JIT** answers *"What is the VM compiling, and what is the code cache state?"*.
- **JFR** provides *"an event/sample timeline over a measurement window"*, requiring the recording to be active at the right time.
- **NMT** provides *"reserved/committed JVM native/internal memory by category and diff from baseline"*, **only when NMT was enabled at startup**.

Choose commands based on **symptoms, required depth of evidence, impact level, and access permissions**. When collecting evidence, record the exact PID, process run, timestamp, settings, and measurement limits; interpret every snapshot in context rather than jumping straight to root cause.

### References

- [Oracle JDK 21 — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): command list and Impact syntax, `VM.*`, `Thread.print`, `GC.*`, `Compiler.*`, `JFR.*`, `VM.native_memory`.
- [Oracle JDK 21 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html): enabling `-XX:NativeMemoryTracking`, baseline/diff, reserved/committed, NMT limits and overhead.
- [Oracle Java SE 21 — Java Flight Recorder API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/module-summary.html): event recording, configuration, and JFR API scope.
- [Oracle JDK 21 — The jfr Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): reading/summarizing `.jfr` files and file analysis tools.