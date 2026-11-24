# 4.6 Distinguishing Observation Commands from Commands That Trigger GC, Dumps, or State Changes

## Learning objectives

`jcmd` is a JDK tool used to send **diagnostic commands** to a running JVM. Not every `jcmd` command merely "reads information": some commands can request garbage collection (GC), scan the entire heap, create large files, start/stop JFR recordings, alter logging configuration, or modify a runtime-manageable flag.

This lesson helps you:

- Distinguish **observation intent**, **evidence-collection cost**, and **state-changing effects** of a command.
- Recognize common command groups on **HotSpot/JDK 17+**: `VM.*`, `Thread.print`, `GC.*`, and `JFR.*`.
- Understand why **Impact: Low/Medium/High** in help output does not mean "read-only" or "always safe under production load".
- Choose an action sequence moving from least intrusive to more intrusive, preserving baseline evidence before running commands that can skew the phenomenon.
- Estimate risks across pauses, CPU, memory, I/O, disk, data exposure, and runtime changes, and document every intervention to interpret diagnostic results accurately.
- Practice on a Java 17 JVM launched by yourself, clearly separating observation examples from examples meant only for lab environments.

## 1. Three questions to ask before every command

A diagnostic operation can fall into multiple categories at once. To evaluate it accurately, separate three independent questions:

1. **What is the command's purpose?** Reading configuration, checking status, capturing a snapshot, creating a recording, or actively making the JVM perform an action?
2. **How expensive is the command?** Does the work force the JVM to walk many threads/objects, pause or synchronize at a safepoint, allocate buffers, write large files, or spike CPU/I/O?
3. **What does the command change?** Does it invoke GC, alter live object sets, create/modify files, enable sampling, rotate logs, start a remote management agent, or change an active flag?

For example, `VM.version` primarily reads version info at low cost. Conversely, `GC.heap_dump` writes a potentially huge HPROF file; on JDK 17, by default it **requests a full GC** unless `-all` is specified. Thus, both are called "diagnostic commands", yet their impacts differ drastically.

Specifically: a command documented with **Impact: Low** can still **intentionally change state**. `VM.set_flag` is described as setting a VM flag, `VM.log` can change log output, `JFR.start` can start a recording, and `ManagementAgent.start` can open remote management. "Low" assesses the **expected operational cost/impact of executing the command itself**, not a promise of "no writes, no state changes".

## 2. Four behavioral categories for classifying commands

| Behavioral category | JDK 17 examples | What are you doing? | What still needs attention? |
| --- | --- | --- | --- |
| **A. Primarily observational** | `VM.version`, `VM.uptime`, `VM.flags`, `VM.command_line`, `JFR.check` | Reading metadata, flags, recording state | Attach has cost; output may contain sensitive info |
| **B. Costly snapshot collection** | `Thread.print`, `GC.heap_info`, `VM.native_memory summary`, `GC.class_histogram` | Traversing threads/heap/native metadata to emit info | Can cause pauses, CPU load, large output; histogram is documented as Impact: High |
| **C. Artifact creation or data capture** | `JFR.dump`, `GC.heap_dump`, `JFR.start` | Writing JFR/HPROF or starting continuous capture | Disk, sensitive data, sampling overhead, GC, and recording lifecycle |
| **D. JVM state intervention** | `GC.run`, `VM.set_flag`, `VM.log` when configuring, `JFR.stop`, `ManagementAgent.start` | Requesting GC, changing flags/logs, ending recordings, or starting agents | Alters measurement conditions and process behavior; separate intended effect from side effects |

This is a **classification by operational intent**, not four mutually exclusive buckets. `GC.heap_dump` is both a heavy snapshot and can trigger GC; `JFR.dump` writes a file yet does not stop the recording by default; `VM.log` can merely list config when using `list`, yet also has options that genuinely alter logging.

To avoid confusion, apply two separate labels when planning:

- **JVM-documented Impact:** Low/Medium/High per `jcmd <PID> help <COMMAND>` or that JDK's docs.
- **Operational effect:** reading info / costly collection / writing artifacts / mutating runtime state, along with expected CPU, pauses, I/O, and generated data.

For the exact same command, real impact also depends on **JDK/vendor build, heap size, thread/class counts, workload, GC algorithm, disk speed, and active flags**. Never turn a documentation label into a fixed "max pause" number without measuring.

## 3. Identify the right JVM and check help before executing

Examples below assume you have **JDK 17+ and a target JVM under valid administrative control**. On hosts with multiple JVMs, always verify the exact PID, launch command, and environment.

On supported operating systems, begin with:

```bash
jcmd -l
jcmd <PID> help
jcmd <PID> help VM.version
jcmd <PID> help GC.heap_dump
jcmd <PID> help GC.run
```

In shell examples, `<PID>` is a **placeholder to replace with a real numeric PID**, not a literal string. Exact syntax and Impact level must be checked on the **target JVM**; commands may be unavailable or have different options across JDKs.

Things to know before attaching:

- `jcmd` sends requests to a running JVM on the same machine/attach scope; normally requires matching effective user/group with the target process.
- `jcmd -l` may not list JVMs in another container/namespace. When that happens, find the PID with appropriate container/process tools; do not conclude the JVM does not exist.
- `jcmd 0 <COMMAND>` can broadcast the request to **multiple Java processes**, so never use it for actions with side effects; work only with a **verified PID**.
- JDK tools may be missing in minimal runtime images; the attach mechanism may be disabled and permissions restricted. Do not jump from an attach error to "the JVM is hung".
- Record **PID, container/pod, start time, JVM vendor/version, timestamp, and purpose**; PIDs can be reused after a restart, so tie them to process identity.

`jcmd <PID> help <COMMAND>` shows the description, required permission, options, and Impact label for a JVM supporting that command. Always check **specific options**, because two modes of the same command can behave very differently.

## 4. Primarily observational commands: what to start with?

| Command | Information gathered | Impact in JDK 17 docs | Notes |
| --- | --- | --- | --- |
| `VM.version` | JVM/VM version | Low | Suitable for target confirmation |
| `VM.uptime` | JVM uptime | Low | Helps spot recent process restarts |
| `VM.command_line` | Command line used to launch the JVM | Low | May expose sensitive arguments/paths |
| `VM.flags` | Active flag values | Low | Reads flags, does not alter flags |
| `VM.system_properties` | Java system properties | Low | May contain tokens, connection URLs, private config |
| `JFR.check` | List/details of running recordings | Low | Does not start a recording |
| `VM.log list` | Current logging configuration | `VM.log` is listed as Low | `list` is an inspection action; other options can modify logging |

**Observation-only** example for a confirmed JVM:

```bash
jcmd <PID> VM.version
jcmd <PID> VM.uptime
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
jcmd <PID> JFR.check
jcmd <PID> VM.log list
```

You do not need to run all of them in every investigation. Gather just enough data for your hypothesis. If the issue is elevated latency after a restart, `VM.uptime`, `VM.flags`, and recording status are typically far more useful than immediately taking a heap dump.

**"Observational" does not mean "completely free".** Attaching interacts with the process, produces output, and can contend for resources. Avoid tight polling loops or excessive output capture when the application is already overloaded. Also protect `VM.system_properties` and `VM.command_line` results before sharing them.

## 5. Observational snapshots that still carry cost

### 5.1 `Thread.print`: modifies no config, yet can affect timing

```bash
jcmd <PID> Thread.print
jcmd <PID> Thread.print -l
```

`Thread.print` prints stack traces of Java threads. `-l` adds `java.util.concurrent` lock details when supported. On JDK 17, docs label it **Impact: Medium**, depending on thread count.

Why evaluate carefully?

- Systems with many threads and deep stacks can produce huge output, spending time walking and collecting data.
- Capturing a consistent view may require synchronization and introduce latency; there is no promise of "zero safepoint/pause".
- A single thread dump is only a point-in-time snapshot. `WAITING` does not by itself prove a deadlock; check lock owners, call paths, process state, and multiple samples when needed.
- If multiple samples over time are needed, space them deliberately and record the interval; never run an unbounded tight loop in production.

For instance, if many requests are hung, trying `Thread.print` at deliberate intervals can be far better than a heap dump. Still, taking the dump itself can bump latency, so mark its timestamp on charts.

### 5.2 `GC.heap_info`: reads heap info, not an intentional GC trigger

```bash
jcmd <PID> GC.heap_info
```

This command provides general heap info; JDK 17 docs rate it **Impact: Medium**. It is not designed to "force GC right now", yet still carries diagnostic cost.

Do not confuse `GC.heap_info` with `GC.class_histogram`:

- `GC.heap_info` returns general heap layout/status info.
- `GC.class_histogram` traverses objects to count instances/bytes per class; docs rate it **Impact: High**, depending on heap size and contents. In some execution paths, gathering statistics may involve a GC request or expensive phase, so check options and test on the target JDK.

If you only need to check configured/committed heap capacity, do not start with a full-heap histogram.

### 5.3 `VM.native_memory summary`: only useful if NMT is ready

```bash
jcmd <PID> VM.native_memory summary
```

JDK 17 docs rate `VM.native_memory` **Impact: Medium**. Using NMT reports requires the JVM to have Native Memory Tracking enabled at startup; otherwise, the command reports that NMT data is unavailable.

Distinguish the options:

- `summary` / `detail`: reads reports from the tracking system.
- `baseline`: sets an **internal comparison mark** for NMT, making it a diagnostic state change.
- `summary.diff` / `detail.diff`: compares against the established baseline.
- `shutdown`: changes NMT tracking state; not a metric-reading step.

NMT tracks supported JVM-internal memory, not every allocation made by external native libraries. A "low NMT" report does not prove low RSS or cgroup memory usage.

## 6. Group requiring caution: commands that can request GC

### 6.1 What does `GC.run` actually request?

```bash
jcmd <PID> GC.run
```

Per JDK 17 `jcmd` docs, this command calls `java.lang.System.gc()` and is rated **Impact: Medium** depending on heap/contents. It is an explicit request for the JVM to execute GC semantics per `System.gc()`.

That **does not mean** an identical full stop-the-world GC always happens:

- With JVM flags like `-XX:+DisableExplicitGC`, explicit GC requests may be ignored.
- Different collectors handle `System.gc()` differently depending on JDK/flags; pause duration, concurrency, and reclaimed objects are not constant.
- Even when few objects are reclaimed, GC work consumes CPU and alters heap occupancy, allocation/pause metrics, cache state, or indirect behaviors.
- If you are investigating "heap rising before GC", running `GC.run` can **wipe out the evidence you needed to observe** and make before/after natural comparisons harder.

Therefore, do not view `GC.run` as a "GC reporting command". When studying post-explicit-GC retention in a lab, mark it clearly as an **intentional intervention**, not a neutral pre-investigation baseline snapshot.

### 6.2 `GC.class_histogram`: looks like a report, yet is heavy

```bash
jcmd <PID> GC.class_histogram
jcmd <PID> GC.class_histogram -all
```

- Histograms report object counts and bytes by class, useful for spotting types occupying substantial heap.
- Per JDK 17 docs, **Impact: High**; scanning the heap can incur significant cost.
- `-all` asks to include **unreachable objects as well**, changing *the set of objects counted*. Using that option does not turn a histogram into a lightweight or non-intrusive measurement.
- On HotSpot, default histogram collection can involve GC/processing to reflect live objects; verify behavior on your **specific JDK/collector/options** rather than assuming every call triggers a "100% full GC".
- A histogram aggregates by class without showing **retaining reference paths** or allocation sources, nor is it sufficient alone to confirm a memory leak.

If you suspect a leak, examine post-GC heap trends over time, allocation metrics, and restart/OOM signals first. Escalate to a histogram or dump only when lighter measurements cannot answer the question.

### 6.3 Why post-GC snapshots can distort the incident story

Suppose pre-diagnosis heap was at 85% of `-Xmx` and latency rose. You invoke `GC.run`, after which heap used drops and latency returns to normal. That **does not prove** the root cause was "Java needs more frequent GC": you just altered state, timing, live objects, and possibly system load.

Document clearly in the timeline:

```text
14:00:00  p99 rises, heap used high, no explicit GC
14:01:00  gather baseline GC metrics / flags / logs
14:02:00  operator invokes jcmd <PID> GC.run
14:02:02  heap used drops after GC activity (if any)
14:03:00  p99 measured again
```

This is an **illustrative scenario**, not evidence from a real JVM. Any metrics **after 14:02** must be tagged "post-intervention", never merged into the natural baseline as though the environment remained untouched.

## 7. `GC.heap_dump`: can trigger GC and writes a large file

Common syntax on JDK 17:

```bash
jcmd <PID> GC.heap_dump /path/to/diagnostics/app-heap.hprof
```

This command writes an HPROF-formatted heap dump. JDK 17 docs explicitly state **Impact: High** and **requests a full GC by default** unless `-all` is specified. The `-all` option dumps unreachable objects too; it changes the dataset and does not guarantee the dump will be lightweight, pause-free, or harmless to the process.

Evaluate four risk groups:

1. **JVM impact:** GC requests, heap walking, and writing data can cause pauses and CPU overhead, especially with large heaps and latency-sensitive apps.
2. **Capacity/I/O:** HPROF files can be huge, saturating disk bandwidth or filling disks/container ephemeral storage; I/O pressure can degrade normal requests.
3. **Sensitive data:** dumps can hold strings, sessions, tokens, customer info, buffers, and live object contents. Enforce proper read permissions, secure storage, and cleanup procedures.
4. **Data interpretation:** if a default dump requested a full GC, the post-dump heap **no longer reflects the untouched pre-action state**. If `-all` was used, do not compare object totals directly with a reachable-only dump.

A successful dump does not itself confirm a memory leak's root cause. You must analyze dominators, retaining paths, instance counts, and retention characteristics against workload/lifecycle.

**Details to record before dumping:** why the dump is needed, PID/build, heap size, memory/container headroom, available disk space, absolute file path, expected duration, baseline metrics, storage destination, and who has access.

**Lab-only illustrative command** targeting a test process you manage:

```bash
# Example: replace <PID> with a real lab PID, choose an absolute path with sufficient space.
jcmd <PID> GC.heap_dump /tmp/jcmd-lab-heap.hprof
```

On Windows, use a path valid for the target JVM. Files are created in the target process's filesystem context; with containers, host paths and container paths can differ. Do not rely on relative paths when reliable artifact retrieval is needed.

## 8. JFR: both observes and modifies collection behavior

Java Flight Recorder (JFR) is useful for capturing CPU, allocation, GC, thread, lock, and runtime events with configuration-dependent overhead. Distinguish `JFR.*` commands precisely:

| Command | Meaning | Side effects to record |
| --- | --- | --- |
| `JFR.check` | Inspect existing recordings | Primarily reads status; Impact Low |
| `JFR.start` | Start a new recording | Mutates JVM state; allocates events/buffers, may write to disk; profile/settings affect overhead |
| `JFR.dump` | Write recording data to file | I/O and artifact; on JDK 17, recording **keeps running** after dump |
| `JFR.stop` | End a recording | Mutates state; depending on `filename`, data may be written or discarded |
| `JFR.configure` | View or modify JFR config | Not "read-only" by default: without options may show settings, with options can mutate them |

Read-only check example:

```bash
jcmd <PID> JFR.check
```

**Intentional lab-environment** action example:

```bash
jcmd <PID> JFR.start name=lab-profile settings=profile duration=30s filename=/tmp/lab-profile.jfr
jcmd <PID> JFR.check
```

`JFR.start` being documented as Impact Low **does not** prove every recording has negligible overhead. JDK presets include `default` and `profile`; `profile` collects more data with higher overhead, suitable for short windows when needed. Events such as paths to GC roots (`path-to-gc-root`) can take considerable time; check options, workload, file size, and resource budget before enabling.

`JFR.dump name=lab-profile filename=...` writes a file yet **does not stop the recording** on JDK 17. `JFR.stop name=lab-profile` is what ends the recording; if no output path is given, data may be discarded per command semantics. Never use `JFR.stop` just to "check if JFR is running".

If an ops team already started a recording earlier, avoid launching/stopping one with a colliding name or altering its config. First confirm recording ID/name, owner, scope, and collection goal.

## 9. `VM.log`, `VM.set_flag`, and other state-changing tools

### 9.1 `VM.log`: reads or modifies logging depending on options

On JDK 17, `VM.log` can list, enable/disable, configure outputs, or rotate logs.

```bash
jcmd <PID> VM.log list
```

The command above uses `list` to **inspect** current configuration. Conversely, invocations with configuration arguments such as `output`, `what`, `decorators`, `disable`, or `rotate` can **alter logging or log files**.

For example, raising GC logging from `info` to `debug` increases event volume and I/O; if logged to container stdout, it can impact both the collector and the log shipping pipeline. Disabling or rotating logs can also disrupt data needed mid-investigation. Always record the **original configuration**, estimated impact, start time, revert time, and who will verify.

Docs assign Impact Low to `VM.log`, which does not eliminate side effects caused by **the volume of logs generated after the change**.

### 9.2 `VM.set_flag`: Impact Low, yet not a read operation

`VM.flags` **reads** flag values. `VM.set_flag` **sets** a flag value that is dynamically manageable and permitted by the JVM. Syntax per target help looks like:

```bash
jcmd <PID> help VM.set_flag
```

Do not use `VM.set_flag` as a check to "show flag values": pick `VM.flags` or `VM.command_line`. Not all flags can be modified at runtime; some require a JVM restart or are blocked by the VM. If you change a flag, confirm its initial value, effect mechanism, whether the new value took effect, and how to revert it.

`Compiler.directives_add/remove/clear` are similar: labeled Impact Low in docs, yet they **modify directives**. Never treat commands in a group identically just because one contains "print" or docs say "Low".

### 9.3 Management agent and native agents: impact beyond performance

- `ManagementAgent.status` reads agent status.
- `ManagementAgent.start` can launch the **remote management agent**, altering network exposure, management config, ports, and access control. Impact Low never means bypassing security policy.
- `JVMTI.agent_load` loads a native agent into the JVM. This alters active code/instrumentation, not a status read.

Never activate an agent casually just because `help` lists Impact Low. These actions can alter system behavior far longer than the command's execution time.

## 10. Decision reference table for common `jcmd` commands

The table separates **Impact in Oracle JDK 17 docs** from **practical operational effects to manage**. Across other vendors/JDKs, prioritize the target JVM's own help.

| Command | JDK 17 doc Impact | Operational nature | Usage notes |
| --- | --- | --- | --- |
| `VM.version`, `VM.uptime` | Low | Primarily read | Confirm right JVM/PID |
| `VM.command_line`, `VM.flags` | Low | Primarily read | May expose sensitive arguments |
| `VM.system_properties` | Low | Primarily read | Do not share raw output if it contains secrets |
| `JFR.check` | Low | Read recording state | Does not replace `JFR.start` |
| `VM.log list` | Low (`VM.log` group) | Read logging config | Distinguish from config-modifying options |
| `GC.heap_info` | Medium | Read heap info | Still has cost; does not intentionally request GC |
| `Thread.print` | Medium | Capture thread snapshot | Cost scales with thread count; may introduce latency |
| `VM.native_memory summary` | Medium | Read NMT | NMT must be enabled; `baseline` differs from `summary` |
| `GC.class_histogram` | High | Gather heap statistics | Can be very heavy; `-all` does not make it "completely safe" |
| `GC.run` | Medium | Requests `System.gc()` | Can alter heap/latency depending on GC/flags |
| `GC.heap_dump` | High | Dump + requests full GC by default | Large file, sensitive data, I/O/pauses |
| `JFR.start` | Low | **Starts recording** | Overhead depends on settings/duration |
| `JFR.dump` | Low | **Writes file**, recording keeps running | Output file, I/O, may have costly options |
| `JFR.stop` | Low | **Ends recording** | Not a read command |
| `VM.log` config | Low | **Changes log output/level** | Alters log volume and I/O |
| `VM.set_flag` | Low | **Modifies dynamic flag** | Eligible flags only; save original state |
| `ManagementAgent.start` | Low | **Starts management agent** | Can alter network/security surface |
| `JVMTI.agent_load` | Low | **Loads native agent** | Alters instrumentation/runtime mechanics |

Do not automatically place `GC.heap_dump` in a "read-only" bucket just because it produces diagnostic evidence. Equally, do not assume a primarily read command is safe at any frequency; **repeated automation** of a command can have far greater impact than a single run.

## 11. Workflow choosing from least intrusive to most intrusive

### Step 1 — Define symptom and required evidence

For example: "p99 latency rose after deploy", "post-GC heap keeps rising", "requests hang despite low CPU". Ask a specific question: do you need version/flags, thread states, heap footprint, allocation paths, or object retaining paths?

### Step 2 — Collect passive evidence first

Record timestamps, build/JDK/flags, request traces, existing GC logs, and CPU/memory/queue metrics before attaching. With `jcmd`, start with `VM.version`, `VM.uptime`, `VM.command_line`, `VM.flags`, and `JFR.check` where appropriate.

### Step 3 — Check `help`, estimate cost for the JVM and workload

Do not just read the command name: ask how many objects/threads it walks, whether it requests GC, whether it writes files or alters flags/agents/recordings; check disk capacity, permissions, container setup, and request-latency impact. Note exact JDK version and options.

### Step 4 — Take moderate snapshots if sufficient

For hangs/locks: consider `Thread.print` at a few timestamps; for heap sizing: `GC.heap_info`; for native memory: `VM.native_memory summary` if NMT is enabled; for multi-dimensional performance: bounded JFR with suitable settings.

Monitor before/after changes: if the command itself spikes CPU/GC/latency, mark that artifact/snapshot on the timeline.

### Step 5 — Escalate only when the question demands it

Use `GC.class_histogram` or `GC.heap_dump` when you need object totals or retaining paths that lighter tools cannot answer. Use `GC.run` only when a deliberate investigation requires explicit GC. Use `VM.set_flag`/`VM.log` config or JFR recordings when the goal genuinely warrants runtime changes.

Coordinate timing, owner, CPU/disk budget, and revert plan based on system health. Never change config and run histograms/dumps simultaneously and blame all metric shifts on one cause.

### Step 6 — Label "pre-intervention / post-intervention"

A sound report never merges windows:

```text
T0: p99 rises, before any jcmd actions
T1: VM.flags + GC.heap_info (observation)
T2: Thread.print -l (costly snapshot)
T3: GC.run (explicit GC intervention)
T4: measure heap/GC/latency post-intervention
T5: GC.heap_dump (dump + possible full GC depending on options)
```

Timestamps are illustrative only. Metrics after T3 must be interpreted as **post-intervention measurements**, and a snapshot after T5 is not "untouched T0 evidence".

### Step 7 — Cross-check outcomes and clean up artifacts

Evaluate explanations from logs/JFR/threads/GC against timestamps and workload. Check HPROF/JFR storage locations, permissions, file lifecycle, whether recordings are still active, and whether logging/flag configs need reverting. For dumps or recordings containing application data, enforce access controls and retention limits.

## 12. Java 17+ Lab without touching a production JVM

This example creates **a test Java process** for observing with `jcmd`, requiring neither heap dumps nor explicit GC triggers. It also includes a `fixture` mode with deterministic stdout so learners can verify behavior distinctions.

Create file `JcmdCommandKindsDemo.java`:

```java
public class JcmdCommandKindsDemo {
    public static void main(String[] args) throws InterruptedException {
        if (args.length == 1 && args[0].equals("fixture")) {
            System.out.println("VM.version: inspect version");
            System.out.println("Thread.print: inspect threads with cost");
            System.out.println("GC.run: request System.gc()");
            System.out.println("GC.heap_dump: write HPROF, request full GC by default");
            System.out.println("VM.set_flag: change manageable VM flag");
            return;
        }

        if (args.length == 1 && args[0].equals("target")) {
            System.out.println("PID=" + ProcessHandle.current().pid());
            System.out.println("READY");
            Thread.sleep(120_000L);
            System.out.println("DONE");
            return;
        }

        System.out.println("Usage: java JcmdCommandKindsDemo fixture|target");
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac JcmdCommandKindsDemo.java
java JcmdCommandKindsDemo fixture
```

**Exact** stdout in `fixture` mode:

```text
VM.version: inspect version
Thread.print: inspect threads with cost
GC.run: request System.gc()
GC.heap_dump: write HPROF, request full GC by default
VM.set_flag: change manageable VM flag
```

That mode **sends no `jcmd` commands**; it simply prints a reminder table, so stdout is stable. To observe a live JVM:

1. Open terminal A and run `java JcmdCommandKindsDemo target`. The program prints its actual PID and `READY`, then sleeps for about 120 seconds.
2. While the target is running, open terminal B, replace `<PID>` with the printed PID, and run `jcmd <PID> help`, `VM.version`, `VM.flags`, `Thread.print`, or `GC.heap_info`.
3. Record timestamps, response times, output sizes, and process state. After 120 seconds, the target exits with `DONE`; to retry, launch it again and use the **new PID**.

Commands in terminal B:

```bash
jcmd <PID> help
jcmd <PID> VM.version
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jcmd <PID> Thread.print
```

**There is no fixed stdout** for `target` mode or `jcmd`: PID, version, flags, heap, and stack traces vary by machine/JDK/state. A `READY` line only indicates the target began sleeping; it does not prove `jcmd` can attach across every namespace/permission boundary.

**Optional extension in an isolated lab, not a required step:** try creating a short JFR capture and inspecting the file; or try a dump on a **small-heap test process** with ample disk space. Measure latency/GC behavior and distinguish output files from runtime state changes. Never practice these operations on other JVMs just to learn commands.

## 13. Three practical scenarios

### Scenario A — High service latency, suspected thread contention

**Question:** are threads waiting on locks or waiting on downstream calls? A valuable approach is inspecting metrics/errors/traces, then taking timestamped `Thread.print` snapshots, adding `-l` if lock details are needed.

**Not needed right away:** `GC.heap_dump`, `GC.run`, or `VM.set_flag`. They do not directly reveal queueing/lock causes and can distort latency.

**Limitation:** a single thread dump cannot prove a deadlock or sole bottleneck. You need multiple timestamped samples, wait mechanisms, and correlation with requests.

### Scenario B — Post-GC heap rising steadily, suspected memory leak

**Question:** which objects are retained, of which classes, and via what retaining paths? Start with heap/GC logs, existing JFR/allocation metrics, `GC.heap_info`, and NMT if native memory is suspected. When insufficient, consider a controlled histogram or dump.

**Risks:** histograms carry High Impact; heap dumps may request a full GC, produce huge HPROF files, and contain sensitive info. If dumped after an explicit GC, note clearly that the baseline was altered.

**Limitation:** many instances of one class do not prove a leak; you need growth over time, retained references, and business lifecycle context.

### Scenario C — Diagnosing with JFR in production

**Question:** is a recording already active with sufficient events for analysis? First run `JFR.check`; if none exists, pick appropriate settings and duration before considering `JFR.start`. A 1-minute `profile` recording can incur higher overhead than a long-running `default` recording.

**Risks:** JFR buffers, event sampling, file output, and `path-to-gc-root` have cost; `JFR.dump` writes a file, `JFR.stop` ends the recording. Starting/stopping is not pure observation.

**Limitation:** JFR sampling can miss events, recording windows may miss the fault, or event settings may be insufficient to confirm root cause. Never say "JFR showed nothing, so no bug exists".

## 14. Checklist before running a diagnostic command with side effects

Answer these questions **before acting on a real system**:

- Do I have the right **PID, container, JVM version/vendor, and workload** that I am authorized to inspect?
- Have I recorded **pre-intervention** symptoms and baseline?
- Does the information goal truly require `GC.run`, a histogram, a heap dump, a new recording, or changing a flag?
- Have I read `jcmd <PID> help <COMMAND>` and understood options like `-all`, `name`, `filename`, `settings`, `list`, or `disable`?
- What are the expected pauses/CPU/I/O and output size at actual heap/thread scale?
- If producing HPROF/JFR/logs, is the path valid for the target process, is there enough disk and permission, and is there a process to store/clean up sensitive data?
- Does the command change GC, flags, logging, JFR, NMT baseline, or management/agent state? Who will monitor and revert it?
- Have I set timestamps, request/load correlation, abort thresholds, and side-effect detection?
- Does the final report capture exact commands/flags/options/timestamps, outputs, observed impacts, and conclusion limits?

## 15. Common mistakes

1. **Seeing "Impact: Low" and assuming the command is read-only.** `VM.set_flag`, `JFR.start`, and `VM.log` can alter state despite a Low impact rating.
2. **Seeing "snapshot" and assuming zero JVM impact.** `Thread.print` and histograms incur cost proportional to actual scale.
3. **Using `GC.run` as a GC inspection tool.** It requests `System.gc()`; behavior depends on collector/flags and can ruin baselines.
4. **Taking a dump before measuring current heap/GC status.** A default dump can request a full GC, altering the object set before analysis.
5. **Using `-all` and claiming zero risk remains.** `-all` changes the inspected object set and does not guarantee low cost.
6. **Reading a post-full-GC histogram and comparing it directly against `-all`.** The two object sets differ semantically; you cannot conclude objects "disappeared" because a leak vanished.
7. **Assuming `JFR.dump` stops the recording.** On JDK 17, the recording keeps running after dump; `JFR.stop` stops it.
8. **Running JFR `profile` long-term without measuring overhead.** Higher-detail event settings can impact CPU, disk, and latency.
9. **Calling `VM.log` without a rollback plan.** Increasing logging can drive I/O and alter the very metrics under observation.
10. **Using a main class name or PID 0 to broadcast commands.** It can hit multiple JVMs; verify a single unique PID.
11. **Skipping container namespace and attach-permission checks.** `jcmd -l` does not always see JVMs in other containers, and attach failure does not prove a hung JVM.
12. **Treating HPROF files like harmless logs.** They can contain sensitive data; enforce access and storage controls.
13. **Failing to timestamp when commands were run.** When CPU/GC/latency charts shift right after diagnostics, cause and effect are easily misattributed.
14. **Chaining multiple heavy commands on an overloaded JVM.** Impacts compound, ruin comparability, and can prolong the incident.
15. **Trusting docs for a different JDK over target help.** Commands, options, and Impact can vary by version/vendor; check the target itself.

## 16. Self-check questions

1. How do `VM.flags` and `VM.set_flag` differ in intent and side effects, even though both carry Impact Low on JDK 17?
2. Why is `GC.heap_info` not equivalent to `GC.class_histogram`? Which command fits better when you only need heap configuration/overview?
3. Which API does `GC.run` invoke? Why can you not guarantee an identical full stop-the-world GC every time?
4. What does `GC.heap_dump` do by default on JDK 17 before/while writing HPROF? What does `-all` change, and what does it not guarantee?
5. An engineer sees heap used drop right after running `GC.run` and announces the leak cause is found. What is missing from that conclusion?
6. How do `JFR.check`, `JFR.start`, `JFR.dump`, and `JFR.stop` affect recording state and files?
7. A 4 GiB heap dump is created inside a nearly full container. What risks arise beyond the JVM pause itself?
8. Why is `jcmd -l` missing a Java PID in another container insufficient to prove the process does not exist?
9. What is the difference between a "low-cost command" and a "command that does not alter application behavior"?
10. When writing a report after a diagnostic session involving a histogram and JFR, which timestamps and option details must be preserved so others can distinguish pre- and post-intervention state?

## Reference documentation

- Oracle, **The jcmd Command — Java SE 17**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Self-verify on the target JVM: `jcmd <PID> help` and `jcmd <PID> help <COMMAND>`. Command lists, options, and Impact levels **can vary** by JDK implementation/version.

**Key takeaway:** classify `jcmd` by **actual effect and cost**, not by command name or a bare Impact label. Gather the least intrusive evidence first, run intentional GC/dumps/recordings/configuration changes only when truly needed, and always mark on the timeline what the diagnostic tool itself changed.