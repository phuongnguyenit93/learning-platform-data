# 20.4 Correlating Heap, Threads, VM Flags, OS, and Resources at Crash Time

## 1. Investigation Mindset: One Incident, Multiple Evidence Layers

When a Java application vanishes, restarts, or stops serving requests, the first question is **not** “was the heap full?” but **“by what mechanism did the process terminate, at what time, and on which node/container?”**. Only after determining the termination mechanism do we combine evidence from the Java heap, threads, VM flags, native memory, operating system, and resource limits.

Consider three very different scenarios:

- **HotSpot fatal error:** the JVM hits `SIGSEGV`/`SIGBUS`/`SIGILL` or an internal fault; it may produce `hs_err_pid*.log` and a core dump. The error log typically reports the current thread, problematic frame, JVM code/version, flags, heap status, and OS info.
- **Java `OutOfMemoryError`:** an allocation fails, such as `Java heap space`, `Metaspace`, `Direct buffer memory`, or `unable to create native thread`. This is a **Java Error** and does not necessarily mean the entire process crashed immediately; if configured properly beforehand, a heap dump may exist.
- **OS/container OOM kill:** the Linux kernel or cgroup manager sends `SIGKILL`. The JVM has **no opportunity** to run its error handler, `finally` blocks, shutdown hooks, or write `hs_err`; you must inspect OS OOM events, container status, and metrics prior to death.

A Java exception does not necessarily cause a JVM fatal error; conversely, a JVM fatal error is not necessarily caused by running out of Java heap. **Not seeing `hs_err` does not prove there was no crash.** The file may be absent because the termination path did not pass through the error handler, the fault was too severe, disk space/permissions were lacking, or artifacts were lost after restart.

This lesson presents a **post-incident** investigation workflow and **pre-incident** data preparation. The goal is not to list every command, but to **correlate sources by the same PID, process start time, timestamp, namespace, and resource boundary** so conclusions are verifiable.

After this lesson, you will be able to:

1. Classify JVM fatal errors, Java OOMEs, OS OOM kills, signals/shutdowns, and application errors.
2. Read the relevant sections of `hs_err` and understand snapshot limitations.
3. Distinguish Java heap **used/committed/max**, native allocations, OS RSS, and cgroup memory.
4. Correlate crash threads/native stacks with thread dumps, VM flags, JFR/GC logs, and CPU/memory/PID limits.
5. Build a timeline from timestamped evidence, evaluate confidence, and test hypotheses by falsification.
6. Prepare files, logs, and metrics so the next crash is **investigatable**, rather than leaving only “pod restarted.”

## 2. First Define What “Crash” Means

The word “crash” on a dashboard may simply mean a **container restart**, whereas the JVM might have received `SIGTERM` and shut down cleanly, received `SIGKILL`, thrown an unhandled exception on the main thread, called `System.exit`, or hit a fatal VM error. Each leaves different evidence.

| Symptom / termination type | Evidence to look for | What **not** to infer |
| --- | --- | --- |
| HotSpot fatal error, e.g. `SIGSEGV` / Windows `EXCEPTION_ACCESS_VIOLATION` | `hs_err_pid*.log`, problematic frame, crash thread, native libraries, core/WER dump | Seeing `libjvm` does not prove a JVM bug |
| `OutOfMemoryError: Java heap space` | Application stderr, pre-error heap usage/GC, heap dump if present, effective `-Xmx` | Do not assume the OS OOM-killed the process |
| `OutOfMemoryError: Metaspace` | Classloader count, metaspace/NMT, `MaxMetaspaceSize`, and class unloading | A heap object histogram alone does not explain all of metaspace |
| `OutOfMemoryError: Direct buffer memory` | Buffer allocations, direct-memory budget, RSS/NMT/OS maps | Unfilled `-Xmx` does not rule out this problem |
| `OutOfMemoryError: unable to create native thread` | Thread count, `-Xss`, OS `ulimit`/PID limit, cgroup `pids.max`, native memory | Raising `-Xmx` is not the default fix |
| OS/cgroup OOM killer sends `SIGKILL` | Kernel/journal logs, cgroup `memory.events`, container `OOMKilled`, RSS/cgroup usage | Exit code 137 **alone** does not prove OOM |
| `SIGTERM`/shutdown/deployment | Termination reason, orchestration events, shutdown logs, drain deadline | Do not treat every restart as a JVM crash |
| Uncaught exception or `System.exit(...)` | Application exception, exit code, startup/shutdown logs | Do not expect `hs_err` |
| Host reboot / hardware / container runtime failure | Host/kernel logs, node events, boot ID, orchestration status | Do not blame a Java frame |

**Exit codes** are often shown by shells/containers as `128 + signal` on Unix (137 ≈ SIGKILL, 139 ≈ SIGSEGV, 143 ≈ SIGTERM), though reporting varies by wrapper/container runtime and a process can intentionally exit with the same code. You must check **termination reason**, signal, kernel events, and matching PID/timestamp. `OOMKilled` from the orchestrator is stronger than guessing from `137`; it still needs to be matched to the exact container instance and timestamp.

## 3. Prioritize Preserving Evidence Before Restarts Wipe the Traces

When an incident occurs, proceed in order:

1. Record the **incident ID**, service, deployment revision, image digest, node, pod/container ID, PID (container PID and host PID if available), detection time, and process start time.
2. Record **UTC timestamps**, each log's timezone, and JVM uptime. Do not mix local time with `uptime` or millisecond timestamps from another clock.
3. Back up **intact** copies of `hs_err`, stderr/stdout, GC logs, JFR, `.hprof` heap dumps, core/WER dumps, application logs, and metrics around the time of failure.
4. Retrieve the **termination status** from the OS/orchestrator and kernel/cgroup OOM events, including events immediately before and after the crash.
5. Record runtime flags, container memory/CPU/PID limits, JDK build, kernel/OS version, JNI/native library versions, thread counts, RSS, cgroup memory, and file-descriptor counts if captured.
6. Build a timeline and attach **source + timestamp + confidence** to each observation; do not turn a hypothesis into a conclusion before cross-checking.

**Crucial point:** after a process has died, `jcmd <pid> ...` cannot attach to that process. Any `VM.flags`, `Thread.print`, `GC.heap_info`, or NMT must be captured **while the process is alive**, read from `hs_err` / core dumps, or pulled from previously stored telemetry. Never record values from the **restarted** JVM and claim they represent the **pre-crash** JVM.

If automatic restarts occur, capture both the process **start timestamp** and container instance ID: **PID 1** can be reused across multiple restarts. Matching by PID alone is insufficient.

### 3.1. Minimizing impact on the scene

- Do not rush to delete the old pod/container before preserving needed logs/artifacts, provided keeping it causes no harm to the system.
- Do not trigger massive heap dumps or core dumps on a service lacking disk/memory headroom without evaluating impact.
- Do not change GC flags, `-Xmx`, or limits at the same time as collecting evidence, as that makes comparisons difficult.
- If immediate service recovery is required, save existing metadata/logs first and investigate on copies; do not block recovery just to capture a risky dump.
- Heap dumps, cores, and `hs_err` can contain passwords, access tokens, env vars, paths, and customer data. Enforce proper access controls, encryption, and retention.

## 4. Evidence Map: What Question Does Each Source Answer?

| Source | Relevant data | Questions it answers | Limitations |
| --- | --- | --- | --- |
| `hs_err_pid*.log` | Signal, problematic frame, current thread, JVM build/flags, heap/process/OS summary | Where did the JVM hit a fatal error? Initial state at death? | Not produced for every termination type; sections may be incomplete |
| GC logs | Heap before/after GC, pauses, collector, allocation/GC pressure | Was the heap steadily filling before the crash? | Does not measure total RSS or native memory |
| `.hprof` | Java object graph/roots, shallow/retained heap | Which objects were keeping the heap alive at dump time? | Excludes many native allocations; dump may be pre/post-GC |
| Thread dumps | Thread names/IDs/stacks/states/locks | Which threads were blocked, in native, deadlocked, or waiting on I/O? | Snapshot may differ from crash moment; thread IDs must be matched |
| `VM.command_line` / `VM.flags` | Startup and effective JVM flags | What were the heap size, GC, thread stack, NMT, and container flags? | Commands run on a new post-restart JVM do not represent the old one |
| NMT `VM.native_memory` | Internal VM native allocations by category, reserved/committed | Did metaspace, threads, code cache, or internal allocations grow? | Requires NMT enabled; does not track all non-JVM library allocations |
| OS process metrics | RSS, VSZ, thread count, FDs, resource limits | How much memory/threads/file handles did the OS see the process using? | RSS does not equal Java heap and cannot be added directly to NMT |
| Cgroup/container metrics | `memory.current`/`memory.max`/`memory.events`, `pids.current` | Did it hit container limits or get OOM-killed? | Metrics are per-cgroup and may include page cache and other processes |
| Kernel/system logs | OOM killer, signals, native crashes, I/O/disk errors | Were there external OS events at the same timestamp? | May lack permissions, logs may have rotated, or retention may be short |
| JFR | GC, threads/monitors, I/O, CPU, execution/alloc events | What were the trends/activities right before the failure? | Must be enabled; data is subject to thresholds/sampling/buffers |
| Orchestrator | Last termination state, restart count, resource limits, node | Who/what restarted the container? | Current container may differ from the dead container |

The right approach is **cross-reading**: for instance, `memory.current` near `memory.max` + increasing `oom_kill` + Kubernetes reporting `OOMKilled` forms a strong signal set for cgroup OOM. An `hs_err` showing `Current thread _thread_in_native` + `Problematic frame C [libnative.so]` helps prioritize the JNI/native library, yet you still need to inspect the core, versions, stack, and reproduction conditions.

## 5. Reading `hs_err`: Correlating Threads, Heap, Flags, and OS in One Snapshot

HotSpot attempts to create a fatal error log upon encountering a severe error. By default it is typically named `hs_err_pid<PID>.log` in the working directory; you can configure `-XX:ErrorFile=/path/hs_err_pid%p.log`. If it cannot write at the expected location, searches must check fallback paths, permissions, and filesystems. Formats vary by JDK/build; a severe crash may leave only the top portion written.

### 5.1. Recommended reading order

**Step A — Header and failure type.** Look for signal/exception, JDK version/build, VM name/architecture, crash timestamp, PID, uptime, and problematic frame. Do not confuse `SIGSEGV` in native code with an ordinary Java `NullPointerException`.

**Step B — Current thread / thread stack.** Check which thread triggered the fatal signal, internal states like `_thread_in_native`, `_thread_in_vm`, or `_thread_in_Java`, native TID, Java frames, native frames, and `VM_Operation` if present. Correlate the native library being called and the JNI boundary.

**Step C — Heap and GC.** Check reported heap/metaspace regions, committed/used if shown, collector info, and GC activity near the crash. A single heap snapshot **does not replace** a multi-minute post-GC trend.

**Step D — VM arguments/flags.** Identify effective `-Xmx`, `-Xms`, collector, `-Xss`, native tracking, container-aware sizing, Java runtime version, and applied options. Compare against expected deployment/config.

**Step E — OS/hardware/resources.** Inspect OS/kernel, CPU/architecture, native memory map, thread count, memory/swap, and file descriptors/limits if present. Cross-check against `/proc`/cgroup/kernel logs or monitoring from the same timestamp.

**Step F — Loaded native libraries / core.** If the problematic frame is in an `.so`/`.dll` library, check its path, version, symbols/native stack, and recent changes.

**Illustrative** excerpt, not a log from a real incident:

```text
# A fatal error has been detected by the Java Runtime Environment:
# SIGSEGV (0xb) at pc=0x00007f00..., pid=4321, tid=4358
# Problematic frame:
# C  [libexamplejni.so+0x1234]
 
Current thread (0x...): JavaThread "worker-7"
                        [_thread_in_native, id=4358, stack(...)]
...
VM Arguments:
jvm_args: -Xms256m -Xmx768m -XX:+UseG1GC
...
Heap:
garbage-first heap total 262144K, used 153600K ...
```

This is a **format illustration**: addresses and sizes do not represent every JDK or collector. HotSpot frame markers commonly use `C` for native C/C++ code, `V` for JVM code, and `J` for compiled Java code; consult the specific build/log rather than inferring root cause from a single letter.

For the sample above, a cautious observation is: there is a fatal signal in a native frame, on a worker thread in native state, in a JVM with configured heap flags. You cannot conclude “insufficient heap” or “JNI definitely has a bug” from four lines alone; you need core/native symbols, runtime version, thread stack, and OS events.

### 5.2. Why is a missing `hs_err` file not negative proof?

Situations where `hs_err` may be absent:

- The OS sent `SIGKILL`, such as the cgroup OOM killer; the JVM had no chance to handle it.
- The process exited via `System.exit` or when `main` finished; that is not a HotSpot fatal error.
- The fault was too severe for the error handler to finish writing.
- Full disk, out of inodes, read-only mount, missing permissions, wrong path, or the artifact existed only inside a deleted container.
- The fatal error handler wrote to the working directory or a fallback location instead of the expected path.

Therefore, when the file is missing, **broaden your source search** rather than treating it as “no crash happened.”

## 6. Comparing Java Heap Against OS-Accounted Memory

One of the most common mistakes is setting `-Xmx=768m` and assuming the process can use at most 768 MiB, or seeing `heapUsed=300 MiB` and completely ruling out an OOM kill in a 1 GiB container.

### 6.1. Metrics that are not equivalent

| Metric | Accurate definition | What cannot be inferred |
| --- | --- | --- |
| `heap used` | Java heap currently holding objects/space in use per JVM metrics | Not total RSS and not all committed heap |
| `heap committed` | Java heap memory committed at the JVM's internal measurement level | Not equal to RSS, and not necessarily live objects |
| `heap max` / `-Xmx` | Configured upper bound for the Java heap | Not a hard cap on the entire process |
| `heap reserved` | Virtual address space reserved for the heap | Not all of it is resident in RAM |
| Metaspace/class/code cache | Memory and management regions for classes/JIT outside the Java heap | Not included in `heap used` |
| Direct/native allocations | Direct ByteBuffers, JNI/native libraries, malloc, mmap, thread stacks, runtime internals | Cannot be diagnosed from HPROF alone |
| `RSS` / `VmRSS` | Physical memory pages resident for the process according to the OS | Not Java live heap; includes shared mappings |
| `VSZ` / `VmSize` | Virtual address space of the process | Not actual physical RAM in use |
| `memory.current` (cgroup v2) | Memory charge of the cgroup and its descendants | May include page cache/kernel memory/other processes; not a single JVM's RSS |
| `memory.max` (cgroup v2) | Hard memory limit of the cgroup; `max` means no limit at this level | Does not replace `-Xmx`, and may not be the tightest limit if an ancestor is stricter |
| NMT `reserved/committed` | Internal JVM tracking by subsystem | Does not replace total OS RSS and does not cover all native code |

Keep in mind an approximate mental model, **not an exact accounting formula**:

```text
Process RSS relates to resident pages of:
    Java heap
  + metaspace / class metadata
  + JIT code cache
  + thread stacks actually touched
  + direct/native buffers
  + JVM internals + shared libraries + ...
(Some pages are shared; accounting systems have their own rules.)

Container memory charge relates to:
    memory used by the JVM and other processes in the cgroup
  + a portion of file/page cache
  + kernel memory and other cgroup/kernel charges
(This is not a simple sum of RSS across processes.)
```

Do not treat `memory.max - Xmx` as **guaranteed** headroom. For example, a container has a **1,024 MiB** limit and `-Xmx=768 MiB`. On paper 256 MiB remains, yet metaspace, stacks, direct buffers, page cache, OS charges, and other processes can consume more than that. Conversely, 768 MiB of reserved heap is not necessarily all committed or resident in RAM at the moment of measurement.

### 6.2. Java heap `OutOfMemoryError`

When `java.lang.OutOfMemoryError: Java heap space` occurs:

1. Check heap usage, GC logs, and **effective** `-Xmx`; examine post-GC live set, growth rate, and allocation pressure.
2. Locate the heap dump captured during the same run (if `-XX:+HeapDumpOnOutOfMemoryError` was set and succeeded); verify timestamp/PID so you do not inspect a dump from a different startup.
3. Analyze Histogram / Dominator Tree / Paths to GC Roots to find abnormally retained objects.
4. Correlate workload, cache/session lifecycle, batch sizes, concurrent requests, and recent changes.
5. Determine whether the process **actually terminated** due to an unhandled exception or another policy. One thread hitting OOME does not mean the entire JVM fatal-crashed instantly.

**A heap dump is not guaranteed evidence for every OOME.** If the system lacks disk space, is killed by the OS before dumping, lacks write permissions, or is in an undumpable state, the HPROF may be absent. Heap dumps can also contain sensitive data and cause large pauses and I/O.

### 6.3. Native/thread/metaspace pressure

If `heap used` is small while RSS or cgroup memory grows:

- Inspect `java.nio.DirectByteBuffer`/network buffers, JNI/native libraries, `malloc`, `mmap`, thread stacks, classloaders/metaspace, code cache, and kernel/page cache.
- For `unable to create native thread`, check `Thread.print`, OS thread count (`Threads` in `/proc/PID/status`), `pids.current/pids.max`, `RLIMIT_NPROC`, `-Xss`, number of executors, and native address space.
- For `Metaspace`, check classloader retention, class counts, and metaspace limits rather than looking only at `-Xmx`.
- For `Direct buffer memory`, check direct memory settings and allocation lifecycles; the JDK may account for direct buffers differently from library native allocations.
- For native leaks, JVM NMT is helpful but **does not measure all memory allocated by non-JVM libraries**. You also need OS profilers/counters/maps, and sometimes a core/native debugger.

In particular, a very large `reserved` figure in JVM NMT does not by itself prove RAM is exhausted: **reserved address space differs from committed memory and from resident physical pages**.

## 7. Thread Snapshots: “Current Thread” vs. “All Threads”

From `hs_err`, you usually get the **Current thread**: the executing thread where the fatal condition reported by the error handler occurred. From `Thread.print`/thread dumps, you get the state of many threads at dump time. Distinguish:

- `_thread_in_native`: thread is inside a native call; useful for scoping the JNI/native boundary, **not enough** by itself to conclude the native library is the root cause.
- `_thread_in_vm`: running VM code. If crashing in a GC/VM operation, inspect GC logs, collector, and JVM build.
- `_thread_in_Java`: Java code running (interpreted or compiled); can still be a victim of native/VM bugs, memory corruption, or hardware faults.
- `BLOCKED`, `WAITING`, `TIMED_WAITING` in a Java thread dump: snapshot states; do not by themselves mean the process crashed due to a deadlock.
- `RUNNABLE` in Java `Thread.State` does not guarantee the thread is burning CPU: it may be waiting on I/O in a native call.

### 7.1. Matching thread IDs at the right layer

An `hs_err` may list `id=...` as the native OS thread ID (TID); Java's `Thread.getId()` or `Thread.threadId()` is an API-level Java thread identifier and must never be assumed equal to TID. Linux `top -H`, `ps -L`, and `/proc/PID/task` show OS threads; Java dumps often print `nid=0x...` in hex. When correlating, convert number bases properly and verify the same PID/process instance.

**Illustrative** example:

```text
hs_err:       Current thread ... id=4358
Java dump:    "worker-7" ... nid=0x1106
OS thread:    LWP/TID 4358
```

Here `0x1106` = `4358` in decimal. Number conversion does not prove it is the same thread if the artifacts came from **two different restarts**. You must verify timestamps and process start times.

### 7.2. Correlating native and Java stacks

When the problematic frame is in `libexamplejni.so`, inspect the stack for:

- Which Java method called JNI or FFI/native bindings.
- C/C++ library version, binary build ID, and symbol addresses.
- Potential invalid pointer access, use-after-free, data races, alignment issues, or ABI mismatches.
- Correlation with recent changes in JDK, native modules, OS/kernel, or compiler.
- Whether crashes repeat at the same frame or shift randomly, suggesting broader memory corruption.

A JVM frame like `V [libjvm.so]` is also not enough to conclude a HotSpot bug: earlier memory corruption from JNI can surface when the VM/GC touches memory. When a native defect is suspected, use **core/WER dump + native symbols + vendor escalation** through authorized procedures, rather than reading only the top of the stack.

Pre-crash thread dumps also help reveal pool saturation, deadlocks, and worker thread spikes. A dump taken 20 minutes before the failure is **trend evidence**, not an exact crash-time snapshot.

### 7.3. Risks when capturing thread dumps

`jcmd PID Thread.print -l` can affect the runtime depending on thread and lock counts. On JDK 21, virtual threads have separate dump/observability mechanisms; do not assume a traditional thread dump shows every virtual thread in the exact same format. Capture samples at multiple points, recording timestamps and the exact command used. Do not run it repeatedly on an overloaded service without assessing impact.

## 8. VM Flags: Read Effective Values, Not Just YAML or Dockerfiles

A deployment might declare a 1 GiB memory limit, the JVM might use a fixed `-Xmx` or RAM-percentage sizing flags, startup scripts might inject `JAVA_TOOL_OPTIONS`/`_JAVA_OPTIONS`, and a Helm chart might append more flags. To investigate properly, record the **actual JVM command**, **effective flags**, and **OS/container limits** together.

Flag groups to cross-check:

| Group | Example flags | Question |
| --- | --- | --- |
| Heap | `-Xms`, `-Xmx`, `-XX:InitialRAMPercentage`, `-XX:MaxRAMPercentage`, `-XX:MaxRAM` | Does heap sizing fit the container limit? |
| GC | `-XX:+UseG1GC` or other collectors, `-Xlog:gc*` | Which collector is active, and what are GC pressure and pauses? |
| Metaspace | `-XX:MaxMetaspaceSize` | Is metaspace capped or growing abnormally? |
| Direct memory | `-XX:MaxDirectMemorySize` (if set) | What cap exists on off-heap buffers? |
| Threads | `-Xss`, `-XX:ActiveProcessorCount` | What thread stack size and CPU topology does the JVM see? |
| Container | `-XX:+UseContainerSupport`, `-XX:MaxRAMPercentage` | Is the JVM reading cgroup constraints appropriately? |
| Native tracking | `-XX:NativeMemoryTracking=summary/detail` | Can a pre-crash baseline/diff be read? |
| Diagnostics | `-XX:ErrorFile`, `-XX:+HeapDumpOnOutOfMemoryError`, `-XX:HeapDumpPath` | Where will artifacts be written, and do disk/permissions allow it? |
| Crash/GC logs | `-Xlog:gc*,safepoint:...` | Is there a timeline of GC/safepoints around the crash? |

Notes:

- `-Xmx` limits the **Java heap**, not the total RAM hard cap of the process.
- `-Xss` configures stack size per environment; with many platform threads, stack reservations and committed pages become significant.
- `-XX:MaxRAMPercentage` does not tell you an exact heap size unless you know the environment the JVM sees, cgroup limits, overriding flags, and JDK version.
- `Use...` flags can be set by ergonomics/runtime; `VM.flags -all` shows many active flags, but output is huge and should be filtered when stored.
- `-XX:NativeMemoryTracking=summary` must be enabled at startup to track data; you cannot ask a dead JVM to reconstruct an uncollected NMT diff.
- VM command lines, system properties, and environment variables may contain secrets. Never paste them wholesale into public tickets.

**How to verify while the JVM is alive** (replace `12345` with the real PID):

```bash
jcmd -l
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.info
jcmd 12345 GC.heap_info
jcmd 12345 Thread.print -l
```

These commands require attach permissions and the right namespace/connection. They carry varying overhead; `Thread.print` and some heap queries can be resource-intensive. Never run them against a post-restart PID and attach the output to an old crash.

## 9. Native Memory Tracking and Reserved/Committed Figures

### 9.1. What does NMT observe?

HotSpot Native Memory Tracking (`NMT`) records allocations **inside the JVM** by category such as Java Heap, Class, Thread, Code, GC, Compiler, and Internal. It **does not cover all `malloc`/`mmap` calls by third-party native libraries**, nor does it replace kernel resident memory accounting. NMT incurs CPU/memory overhead, so test it in an appropriate environment.

If started with:

```text
-XX:NativeMemoryTracking=summary
```

You can capture snapshots:

```bash
jcmd 12345 VM.native_memory summary scale=MB
jcmd 12345 VM.native_memory baseline
# Wait after the application warms up and runs workload ...
jcmd 12345 VM.native_memory summary.diff scale=MB
```

A `baseline` must be established before taking a diff; capture multiple timestamped points. With `detail`, call-site granularity is available at higher overhead. If NMT reports tracking is disabled, that data cannot be recovered from a dead process.

### 9.2. Why not add NMT to RSS?

NMT reports two metrics:

- **reserved:** virtual address space set aside by the JVM.
- **committed:** memory committed for use by the JVM per category.

RSS is **resident memory** observed by the OS; its accounting includes mappings/shared pages, and memory committed by the JVM may not yet be resident. Cgroup memory may also include kernel memory/page cache and descendants. Therefore, never compute `NMT committed + RSS` or assume `NMT committed == RSS`. Compare trends and categories per source, then account for differences on solid evidence.

Example for a process:

```text
NMT Java Heap reserved = 2048 MiB
NMT Java Heap committed = 512 MiB
OS RSS = 700 MiB
container memory.current = 850 MiB
```

All of these numbers **can be simultaneously true** yet unequal. RSS includes resident pages from non-heap regions; cgroup memory can include page cache and other charges. These are purely illustrative numbers, not measurements from the lesson demo.

## 10. Operating System and Cgroups: When the JVM Cannot Write `hs_err`

### 10.1. Linux: process metrics while alive

The following example commands are for **Linux**, not Windows PowerShell. Run only while the PID still exists:

```bash
PID=12345
date -u
ps -o pid,ppid,lstart,etime,rss,vsz,nlwp,stat,cmd -p "$PID"
cat "/proc/$PID/status"
cat "/proc/$PID/limits"
cat "/proc/$PID/cgroup"
ls "/proc/$PID/task" | wc -l
```

Useful observations:

- `VmRSS` and `VmSize`: resident / virtual size of the process; do not confuse with heap.
- `Threads` or `nlwp`: OS thread count; cross-check with `unable to create native thread`.
- `Max open files`, `Max processes`, `Max stack size`, and other limits in `/proc/PID/limits`.
- `/proc/PID/cgroup`: which cgroup the process belongs to; mount/cgroup namespaces may require `/proc/PID/mountinfo` to locate the exact metrics files.
- `PPID`, process start time, command line: avoid confusing a restarted process that reused a PID.

After a crash, `/proc/PID` disappears; you must rely on saved metrics/logs or monitoring system data.

### 10.2. Linux cgroup v2

In many cgroup v2 containers, you can inspect these files:

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/pids.current
cat /sys/fs/cgroup/pids.max
```

**The paths above are only right if the current mount/cgroup namespace maps to the cgroup you are investigating.** On hosts, nested cgroups, or cgroup v1, paths and filenames differ. Read `/proc/<PID>/cgroup` and `mountinfo` to identify the exact cgroup rather than assuming `/sys/fs/cgroup` in a host shell belongs to the dead container.

Meaning:

- `memory.current`: current memory charge; not the JVM's RSS alone.
- `memory.max`: hard limit (or literal `max`).
- `memory.events`: counters such as `high`, `max`, `oom`, `oom_kill`.
- `pids.current/pids.max`: current task count / PID limit; useful when thread creation fails.

`memory.events` contains **counters over the lifetime of the cgroup**, and in cgroup v2 some values are **hierarchical**; `memory.events.local` helps inspect events specific to that cgroup. Thus, a single reading of `oom_kill=1` does not prove a kill in the **current incident** without timestamps/deltas, if the cgroup holds multiple processes, or if an earlier event occurred. Observing the counter increment at the exact moment the container became `OOMKilled` is much stronger evidence.

Do not assume `memory.current` read **after a restart** equals the **pre-crash** container peak: the process/cgroup may have been replaced, counters reset, or metrics lost.

### 10.3. Linux kernel logs

If permissions allow and logs are still retained:

```bash
journalctl -k --since "2026-10-29 09:55:00" --until "2026-10-29 10:05:00"
dmesg --ctime | grep -Ei 'out of memory|oom-kill|killed process'
```

**The timestamps in the example are illustrative only**; replace them with your incident window and pay attention to the timezone displayed by `journalctl`/`dmesg`. Kernel logs may record executable name, host PID, cgroup path, and memory pressure. Without permissions or if logs rotated, “no OOM found” still does not completely rule out an OS kill.

Other limits worth checking when crashes are not heap-related:

- `ulimit`, `RLIMIT_NPROC`, `pids.max` when thread creation fails.
- File descriptors and `EMFILE`/`ENFILE` when opening sockets/files fails.
- Free disk space **and inodes** on dump/log paths; read-only filesystems or full volumes can prevent artifacts from being saved.
- CPU throttling and I/O pressure do not necessarily crash directly, but can trigger timeouts and watchdog/probe restarts.
- Swap availability and memory pressure; do not attribute all memory pressure to a Java heap leak.

### 10.4. Kubernetes / container orchestration

Investigation example (substitute real namespace/pod/container):

```bash
kubectl describe pod myapp-abc -n prod
kubectl get pod myapp-abc -n prod -o json
kubectl logs myapp-abc -n prod -c app --previous --timestamps
```

In the output, look for:

- `lastState.terminated.reason`, `exitCode`, `finishedAt`, restart count.
- CPU/memory requests & limits of the **terminated** container, not just a newer deployment.
- Pod/container ID, node, image digest, and kubelet events.
- `--previous` only helps while previous container logs are still retained by the runtime and the container restarted in the same pod; do not assume they always exist.
- Time-series metrics for the old container: memory working set/usage, OOM counters, CPU throttling, restarts, file descriptors.

If `reason=OOMKilled` while Java `heap used` is low, investigate direct/native memory, page cache, thread stacks, and other processes in the cgroup; do not conclude the JVM heap collector is broken.

### 10.5. Windows or non-Linux environments

On Windows, corresponding sources include **Event Viewer / Windows Event Log**, **Windows Error Reporting (WER)**, process dumps, Performance Counters (Private Bytes, Working Set, thread count, handles), service manager logs, and Job Object memory limits if configured. `hs_err` may report `EXCEPTION_ACCESS_VIOLATION` instead of `SIGSEGV`. Never apply Linux `/proc` or cgroup commands directly to Windows.

On every OS, record JDK vendor/build, architecture, kernel/OS build, CPU/memory limits, binary/native library versions, and process termination time.

## 11. Preparing the JVM So the Next Crash Has Evidence

Example HotSpot JDK 17+ startup flags on **Linux** (paths are illustrative and must exist with sufficient permissions/disk):

```bash
java \
  -XX:ErrorFile=/var/log/myapp/hs_err_pid%p.log \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/log/myapp \
  -Xlog:gc*,safepoint:file=/var/log/myapp/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -XX:NativeMemoryTracking=summary \
  -jar app.jar
```

Explanation:

- `ErrorFile` specifies the fatal error log location (with `%p` to distinguish PIDs).
- `HeapDumpOnOutOfMemoryError` requests a dump when the VM encounters supported OOMEs under dumpable conditions. **Does not guarantee** a dump if the OS sends `SIGKILL`, on fatal native crashes, or when disk space is exhausted.
- `HeapDumpPath` sets the dump directory/file; an HPROF can be huge and contain secrets. Evaluate storage, I/O, and retention.
- `-Xlog:gc*,safepoint...` records the GC and safepoint timeline, rotating by `filecount`/`filesize`. Older logs are lost if rotation is too small.
- `NativeMemoryTracking=summary` provides NMT data for inspection while the process is alive, with some overhead; it is not zero-cost.
- Continuous JFR can be configured with size and retention caps, but **whether a recording survives a crash** depends on flush/disk behavior and file state; verify in your real environment.

**Do not copy example settings straight into production** without evaluating cgroup headroom, disk space, secret retention, performance, and directory permissions. Paths must reside on volumes that actually persist across container restarts.

### 11.1. Capturing state while the JVM is alive

The following commands are for **live measurement / pre-incident or investigating an existing process**:

```bash
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
jcmd 12345 Thread.print -l
jcmd 12345 VM.native_memory summary scale=MB
```

To compare native memory after warm-up:

```bash
jcmd 12345 VM.native_memory baseline
# Capture again after a reasonable observation window:
jcmd 12345 VM.native_memory summary.diff scale=MB
```

If NMT was not enabled at startup, `summary`/`summary.diff` will not provide the NMT metrics you want. When collecting periodically, choose an appropriate cadence, record timestamps, and manage file/metric lifecycles clearly.

### 11.2. Note on manual heap dumps

`jcmd PID GC.heap_dump file.hprof` is a high-impact operation; HotSpot typically triggers a **full GC before dumping**, unless an alternative option is used (e.g., `-all` on JDK 21). That can alter heap state and pause the application. Never run it after the process is dead or when the system cannot tolerate the impact. If core dumps are needed after fatal errors, OS/core-pattern/container runtime settings and permissions must be prepared separately.

## 12. Runnable Java 17+: Capturing a Pre-Crash Correlation Snapshot

You cannot run Java code **after** the JVM has died to read lost runtime state. The following example serves as **live evidence capture**: UTC timestamp, PID, JVM uptime, Java/OS version, heap used/committed/max, non-heap memory, thread count, and thread states. Output can be sent to a secure logging pipeline; the sample prints to stdout for standalone execution.

Create **`CrashContextSnapshot.java`**:

```java
import java.lang.management.*;
import java.time.Instant;
import java.util.EnumMap;
import java.util.Map;

public final class CrashContextSnapshot {
    private static String mebibytes(long bytes) {
        return bytes < 0 ? "unknown" : Long.toString(bytes / 1_048_576);
    }

    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        OperatingSystemMXBean os = ManagementFactory.getOperatingSystemMXBean();

        MemoryUsage heap = memory.getHeapMemoryUsage();
        MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();
        Map<Thread.State, Integer> states = new EnumMap<>(Thread.State.class);
        for (Thread.State state : Thread.State.values()) {
            states.put(state, 0);
        }
        ThreadInfo[] infos = threads.getThreadInfo(threads.getAllThreadIds(), 0);
        for (ThreadInfo info : infos) {
            if (info != null) {
                states.merge(info.getThreadState(), 1, Integer::sum);
            }
        }

        System.out.println("captureUtc=" + Instant.now());
        System.out.println("pid=" + ProcessHandle.current().pid()
                + " uptimeMs=" + runtime.getUptime());
        System.out.println("javaVersion=" + System.getProperty("java.version"));
        System.out.println("os=" + os.getName() + "/" + os.getArch());
        System.out.println("heapUsedMiB=" + mebibytes(heap.getUsed())
                + " heapCommittedMiB=" + mebibytes(heap.getCommitted())
                + " heapMaxMiB=" + mebibytes(heap.getMax()));
        System.out.println("nonHeapUsedMiB=" + mebibytes(nonHeap.getUsed()));
        System.out.println("liveThreads=" + threads.getThreadCount()
                + " states=" + states);
        System.out.println("snapshotComplete");
    }
}
```

Compile and run with Java 17+:

```bash
javac --release 17 CrashContextSnapshot.java
java CrashContextSnapshot
```

Example **stdout tested on a Windows/JDK 24 machine**; environment values and timestamps are not fixed output:

```text
captureUtc=2026-10-29T11:09:24.922191200Z
pid=4452 uptimeMs=52
javaVersion=24.0.2
os=Windows 11/amd64
heapUsedMiB=0 heapCommittedMiB=2048 heapMaxMiB=30208
nonHeapUsedMiB=1
liveThreads=7 states={NEW=0, RUNNABLE=5, BLOCKED=0, WAITING=1, TIMED_WAITING=1, TERMINATED=0}
snapshotComplete
```

The final line **`snapshotComplete`** is a stable marker when the program completes successfully. Preceding numbers vary by JVM, processor count, startup, flags, and OS. `heapUsedMiB=0` in the sample merely reflects rounding down to MiB in a short-lived process, **not that the Java heap contains zero objects**.

### 12.1. Understanding the sample snapshot's limitations

- `MemoryMXBean` reports VM-managed Java heap and non-heap; it **does not fully measure RSS, native `malloc`, or cgroup `memory.current`**.
- `getThreadCount()` and `getAllThreadIds()` form a non-atomic snapshot; threads can start/exit between reads. The state map describes only the sample instant, not thread counts at a future crash.
- `ProcessHandle.current().pid()` is the PID in the namespace seen by the JVM. The container host may see a different PID.
- `RuntimeMXBean.getUptime()` helps identify process age at capture time; correlating crashes also requires process start timestamp, deployment ID, and container ID.
- The code intentionally **does not print all JVM arguments, system properties, or environment variables** to avoid accidentally leaking secrets. To record flags, use diagnostic tooling with secure storage and sensitive-data filtering.
- For postmortem usefulness, snapshots must be captured **periodically or via active monitoring**, not by running this program once after a crash.
- Do not mix `heapMaxMiB` from the demo JVM with the memory limit of another service. In real investigations, run instrumentation or `jcmd` on the exact target service under observation.

The goal of this exercise is to show **multi-dimensional correlation**: timestamp + PID + uptime + heap + threads + JDK + OS. It does not prove crash root cause by itself; OS/container evidence must be collected separately.

## 13. Building a Verifiable Timeline

Suppose (using **purely hypothetical** data) a Java container on a Linux node has `memory.max = 1024 MiB` and JVM `-Xmx=768 MiB`:

| UTC Time | Source | Observation | Initial interpretation |
| --- | --- | --- | --- |
| 10:00:00 | JVM/GC metrics | Post-GC heap used 360 MiB | No sign yet of heap approaching Xmx |
| 10:00:20 | OS metrics | JVM RSS rises from 670 to 850 MiB | Memory growth outside live heap or higher heap residency |
| 10:00:30 | cgroup metrics | `memory.current` 1,010 / 1,024 MiB | Very close to cgroup hard limit |
| 10:00:31 | Kernel/cgroup events | `oom_kill` counter increments from 0 to 1 | An OOM kill occurred within the tracked counter scope |
| 10:00:31 | Orchestrator | Previous container exited `reason=OOMKilled` | Strong evidence a cgroup/OS kill happened |
| 10:00:32 | Service | Pod/container restarted, container PID is 1 again | New process; do not merge its heap with the old process |

**Reasonable conclusion:** the *immediate termination cause* is very likely an **OS/container OOM kill**. A post-GC heap of 360 MiB does not prove a Java heap leak; you must examine direct/native memory, page cache, threads, or other processes in the cgroup to explain why `memory.current` hit the limit. If the cgroup is a parent holding multiple descendants, `memory.events` might reflect another process; match container IDs, event logs, and victim PID to confirm.

**Unreasonable conclusion:** “The JVM died because `-Xmx=768 MiB`, so raise `-Xmx` to 1 GiB.” That can make native memory headroom **even worse** while the container hard limit remains 1 GiB.

### 13.1. What weakens an OOM kill hypothesis?

- No cgroup/OS OOM events **matching the timestamp or victim**, and the container termination reason is a readiness/shutdown failure.
- Exit code 137 caused by an operator running `kill -9` or a watchdog sending `SIGKILL`.
- `memory.current` metrics belong to a **different** cgroup (node/parent) from the container that died.
- Only a **post-restart** snapshot exists, with no prior trend.
- `oom_kill` was already non-zero before the incident with no delta; or a hierarchical counter reflects another descendant.

A conclusion should explicitly state **confidence level and missing evidence**, rather than forcing all sources into one neat story.

## 14. Two Control Scenarios: When “Memory Crash” Is the Wrong Diagnosis

### 14.1. Scenario A — fatal native crash in JNI

Hypothetical facts:

- `hs_err` with matching PID/start time reports `SIGSEGV` and `Problematic frame: C [libcompressionjni.so+offset]`.
- Current thread is a worker in `_thread_in_native`.
- Post-GC heap is stable and cgroup memory still has headroom.
- Core stack shows a JNI call involving a recently updated library version.

**Priority hypothesis:** native library bug, ABI mismatch, memory safety issue, or JNI calling condition. **Cannot conclude yet** solely from the top frame: an earlier memory overwrite could manifest at the current crash address.

Next steps: verify binary build ID, symbols, JNI boundary, crash-triggering input, concurrency, and recent JDK/native library changes; use debugger/core under safe procedures; test reproduction in staging if possible. Arbitrarily increasing the heap will not fix an access violation.

### 14.2. Scenario B — thread creation fails while Java heap has room

Hypothetical facts:

- Application log shows `OutOfMemoryError: unable to create native thread`.
- `pids.current` is near `pids.max`, or `Threads` climbs rapidly.
- `-Xss` is relatively large and there are many platform threads.
- `heap used` is well below `-Xmx`.

**Priority hypothesis:** hitting PID/thread limits or native resource limits, not a default Java heap object leak.

Next steps: measure thread creation rate, executor policies, thread stacks, cgroup PID limits, and OS `RLIMIT_NPROC`; check for thread leaks caused by creating unbounded executors. Distinguish a Java exception terminating `main` from an actual kernel OOM kill.

### 14.3. Scenario C — heap is genuinely exhausted

Hypothetical facts:

- `OutOfMemoryError: Java heap space` appears on stderr.
- GC logs show heap used after major/full GC stays near `-Xmx` across multiple cycles.
- An HPROF from the same incident shows large numbers of cache/session objects kept alive inconsistent with business lifecycle.
- No kernel OOM kill occurred at the time of failure.

**Priority hypothesis:** oversized live set, memory leak, or heap limit inappropriate for the workload. HPROF provides **object graph** evidence, while GC logs provide **trend** evidence. Both must be combined; do not call something a “leak” solely from a single large retained size.

## 15. Practical Branch-by-Branch Triage Workflow

```text
Application disappears / restarts
         |
         v
Have termination reason, exit code, timestamp, process instance?
         |
         +--- No ---> preserve logs + orchestrator/OS metadata
         |
         v
Is there a Java/HotSpot fatal hs_err or core matching PID/time?
         |
         +--- Yes ---> read signal + thread + frame + flags + heap + OS
         |             check native/JVM/GC, compare with core and build IDs
         |
         +--- No ---> Is there an OOME on Java stderr / heap dump?
                         |
                         +--- Yes ---> classify heap/metaspace/direct/thread
                         |             correlate GC, NMT, RSS, limits
                         |
                         +--- No ---> Was there OOMKilled / kernel OOM / SIGKILL?
                                         |
                                         +--- Yes ---> check cgroup/RSS/
                                         |             page cache/native/threads
                                         |
                                         +--- No ---> check SIGTERM,
                                                      deploy, probe, exit,
                                                      host crash, application logs
```

This is a **decision tree to prioritize investigation**, not a strictly mutually exclusive classification. A service can hit a Java OOME and then get killed by a watchdog, or native memory growth can lead to a cgroup OOM kill, or a JNI bug can corrupt the heap and crash during GC. A timeline separates the **underlying cause** from the **immediate termination event**.

A high-quality incident conclusion should record:

- **Observed:** evidence directly seen, including source, paths/IDs, and timestamps.
- **Likely mechanism:** fatal JVM error, Java OOME, SIGKILL/OOMKilled, signal/shutdown, etc.
- **Candidate root cause:** memory configuration, JNI/native bug, insufficient heap, thread leak, resource exhaustion, etc.
- **Counter-evidence:** facts that argue against the hypothesis.
- **Missing evidence:** heap dump, NMT baseline, kernel logs, process IDs, etc.
- **Next check / mitigation:** small measurement or change to verify, along with execution risks.

## 16. Common Pitfalls When Correlating Evidence

**Pitfall 1 — Seeing `-Xmx` below the container limit and concluding OOMKill is impossible.** The JVM also has native memory, thread stacks, code cache, metaspace, page cache, and cgroup charges.

**Pitfall 2 — Treating a heap dump as a snapshot of all RAM.** HPROF primarily holds the Java object graph; use OS metrics/NMT/native tools for off-heap memory.

**Pitfall 3 — Counting `reserved` as RAM in use.** Reserved address space ≠ committed memory ≠ resident physical pages.

**Pitfall 4 — Relying only on `exitCode=137`.** `SIGKILL` has multiple causes. You need termination reason, kernel/cgroup events, victim process, and timeline.

**Pitfall 5 — Ruling out a fatal error because `hs_err` is missing.** The artifact may not have been created/retained, or the OS killed the VM before it could write.

**Pitfall 6 — Seeing `Problematic frame V [libjvm]` and concluding a JVM bug.** JNI memory corruption, native libraries, or hardware can cause the JVM to fail far from the root cause.

**Pitfall 7 — Using a thread dump from the post-restart JVM.** PIDs can repeat; verify start times/container IDs and timestamps.

**Pitfall 8 — Reading `nid` as the Java Thread ID.** `nid` is typically a native ID often written in hex; convert properly to match OS TID.

**Pitfall 9 — Adding NMT committed + RSS or treating them as equal.** They are different accounting systems; compare trends/categories without double-counting.

**Pitfall 10 — Using a single `memory.events oom_kill=1` reading to blame the incident.** Counters need deltas and cgroup scoping; it could be an old or hierarchical event.

**Pitfall 11 — Changing multiple flags at once to “test.”** Changing `-Xmx`, GC, thread pools, and container limits simultaneously makes it hard to tell what had an effect.

**Pitfall 12 — Concluding a leak from one large heap graph.** A large retained heap may be legitimate; compare workload, lifecycle, and multiple snapshots.

**Pitfall 13 — Taking a heap dump when nearly out of disk and worsening the incident.** Dumps are expensive; plan volumes, retention, and timing carefully.

**Pitfall 14 — Using unconverted local timestamps or JVM uptime as epoch time.** Easy to misalign pre- and post-restart logs. Keep timezones, process start times, and sources for all timestamps.

**Pitfall 15 — Ignoring OS PID/file/swap/FD limits.** Not every resource exhaustion is a lack of Java heap.

**Pitfall 16 — Publishing `hs_err`/core/heap dumps publicly.** Artifacts may contain secrets and private data; apply redaction and controlled access.

## 17. Analysis Exercises and Answers

### Exercise 1 — Low heap yet container killed

Container limit 1024 MiB, `-Xmx=768m`. Before restart, post-GC heap used was 350 MiB, OS RSS 890 MiB; `memory.current` 1015 MiB, `oom_kill` incremented, Kubernetes reported `OOMKilled`.

**Question:** Can you conclude a heap leak? What else must be checked?

*Answer:* Not yet. Strong evidence for a cgroup/OS OOM kill, but low live heap does not prove a leak. You need a breakdown of native/direct/metaspace/thread/page cache, cgroup descendants, NMT if enabled, kernel victim info, and metric trends. Do not raise `-Xmx` by default.

### Exercise 2 — Native SIGSEGV in `libjvm`

`hs_err` reports `SIGSEGV`, `Current thread _thread_in_vm`, problematic frame in `libjvm`. No `OutOfMemoryError`.

**Question:** Is it certain the JDK has a bug?

*Answer:* No. You need core/native stack, exact JDK build, GC logs, JNI/native library list, memory corruption evidence, and reproduction steps. It could be a VM bug, but a frame inside the VM can also be where corruption caused by other native code surfaces.

### Exercise 3 — Same PID, different uptime

At 10:00 there is `hs_err_pid1.log`; at 10:02 you run `jcmd 1 VM.flags` in the new container and see different flags.

**Question:** Which data reflects the 10:00 crash?

*Answer:* `hs_err` and artifacts from that same container/process instance—not `jcmd` from the new JVM even though its PID is also 1. Verify process start/container ID, deployment version, and timestamps.

### Exercise 4 — Adding RSS and NMT

NMT committed=600 MiB, OS RSS=720 MiB. Can you report the process uses `1320 MiB`?

*Answer:* No. NMT and RSS overlap and use different accounting models; adding them double-counts memory and does not reflect true memory footprint.

### Exercise 5 — No `hs_err`, exit code 143

Container exited 143 right during a rollout. Kernel has no OOM evidence, and application logs show a shutdown hook running.

*Answer:* Investigate `SIGTERM`/rollout and graceful shutdown first; do not assume a fatal JVM crash.

### Exercise 6 — `oom_kill=3` without a delta

You only have a single post-restart snapshot of `memory.events` showing `oom_kill=3`.

*Answer:* You cannot claim three OOMs occurred in this incident. You need counter history, cgroup scope, victim processes, and contemporaneous orchestrator/kernel logs.

### Exercise 7 — Thread count hits limit

Java stderr shows `unable to create native thread`; `pids.current=500`, `pids.max=512`, platform threads spiked sharply.

*Answer:* Prioritize checking thread leaks, executor pools, cgroup PID limits, and OS thread stacks; this is not evidence of a full Java heap.

## 18. Postmortem and Next-Incident Readiness Checklist

- [ ] Confirmed termination type via exit status, reason, signal, Java stderr, `hs_err`, and kernel events.
- [ ] Matched exact **PID + process start + container ID/node + UTC time**; did not confuse with post-restart JVM.
- [ ] Preserved `hs_err`, GC logs, HPROF, core/WER, JFR, app logs, and dashboard metrics before deletion.
- [ ] If `hs_err` exists, checked signal, current thread, problematic frame, JVM build, heap, flags, OS, and libraries.
- [ ] Distinguished Java heap **used/committed/max** from native memory, RSS, VSZ, and cgroup charge.
- [ ] Obtained pre-crash trends for post-GC heap, RSS, `memory.current/max`, native memory, thread count, FDs, and CPU.
- [ ] Checked `memory.events` **deltas**/cgroup scope, kernel OOM victim, and orchestrator termination state.
- [ ] Checked thread name/ID/`nid` and snapshot timing; did not equate Java thread ID with OS TID.
- [ ] Correlated **effective VM flags** against actual config, `-Xmx`, `-Xss`, collector, direct/metaspace, container sizing, and NMT.
- [ ] Confirmed NMT was enabled at startup if used; did not expect total NMT to equal RSS.
- [ ] Kept in mind `jcmd` commands apply only to **live** processes and should be run with impact awareness.
- [ ] Checked for counter-evidence or contradictions rather than picking a single cause from one isolated metric.
- [ ] Protected, redacted, and stored sensitive artifacts under retention rules.
- [ ] Report includes observed evidence, likely mechanism, root-cause hypothesis, confidence, missing data, and next checks.

**Key takeaway:** A crash is an **event at the JVM–OS–container boundary**. Heap dumps reveal the object graph; thread snapshots show execution/locks at capture time; VM flags explain configuration; OS and cgroups reveal resource charges/limits/kills; and `hs_err` illuminates fatal VM errors. Only by **correlating these pieces for the same process and timeline** can you distinguish Java heap exhaustion, native pressure, thread/PID exhaustion, OS OOM kills, native `SIGSEGV`, or ordinary shutdowns.

## References

- OpenJDK/Java Operations — [How to Find and Interpret the Java HotSpot Fatal Error Log](https://ops.java/troubleshooting/articles/fatal-error-log/): components of `hs_err`, error header, current thread, heap/OS sections.
- Oracle JDK 21 — [Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html): collecting fatal logs, core dumps, heap dumps, JFR/GC logs.
- Oracle JDK 21 — [`jcmd` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `VM.flags`, `VM.command_line`, `Thread.print`, `GC.heap_info`, `VM.native_memory`, and overhead.
- Oracle JDK 21 — [`java` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): JVM flags, `-Xmx`, ErrorFile, NMT, and diagnostic options.
- Oracle JDK 21 — [Diagnostic Tools / Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): NMT reserved/committed, baseline/diff, and limits of tracking non-JVM memory.
- Linux Kernel — [Control Group v2 documentation](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html): `memory.current`, `memory.max`, `memory.events`, and accounting behavior.
- Kubernetes — [Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): limits, memory enforcement, and OOM behavior.
- Oracle Java 21 — [`MemoryMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html) and [`ThreadMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): heap/non-heap snapshots and thread data.
- Oracle JDK 21 — [`jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): inspecting JFR evidence after dumping.
