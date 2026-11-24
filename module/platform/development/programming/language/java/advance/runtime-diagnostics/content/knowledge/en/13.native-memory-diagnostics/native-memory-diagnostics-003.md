# 13.3 Enabling NativeMemoryTracking at Startup with `summary` or `detail`

## 1. What Is Native Memory Tracking (NMT) For?

**Native Memory Tracking (NMT)** is a **HotSpot JVM** diagnostic capability that accounts for memory managed by the JVM itself: reserved and committed heap, class metadata, thread stacks, JIT code cache, GC structures, internal allocations, and several other native allocation sources. NMT helps answer:

- How much memory has the JVM **reserved** and **committed** per category?
- Which category grows over time, even while the Java heap looks stable?
- If deeper inspection is needed, which **native allocation call sites** or virtual address regions are contributing to the growth?
- After the application warms up, how much does memory change between two points in time?

This lesson focuses on **enabling NMT right when starting the JVM** via `-XX:NativeMemoryTracking=summary` or `-XX:NativeMemoryTracking=detail`, then verifying the configuration and reading it with `jcmd`. This is a tool for analyzing **HotSpot-side native memory**, not a heap profiler or a detector for every memory leak in the process.

**Important limitation:** NMT does not fully cover direct allocations by third-party native libraries, JNI code that bypasses HotSpot-tracked allocators, or every part of JDK library memory. Therefore, NMT results are **not identical** to RSS, container memory, or the entire process address space. Metrics must be cross-checked with the OS when suspecting a native leak outside the JVM.

## 2. Why Must It Be Enabled at Startup?

HotSpot sets NMT to `off` by default to avoid tracking overhead. Choose the level with a **JVM startup option**:

```text
-XX:NativeMemoryTracking=off
-XX:NativeMemoryTracking=summary
-XX:NativeMemoryTracking=detail
```

Per HotSpot documentation (JDK 17–26), `jcmd VM.native_memory` can **read** tracked results, create a baseline, print diffs, and **shut down** NMT, but it **cannot re-enable NMT once off or upgrade `summary` to `detail` within the same JVM**. When a higher NMT level is needed, update the startup option and **restart the JVM** following appropriate operational procedures. If an incident occurs while NMT is off, there is no way to retroactively reconstruct allocation history from past allocations.

| Startup Level | What Is Collected | Suitable Questions | Limitations |
| --- | --- | --- | --- |
| `off` (default) | Does not maintain NMT | Run when NMT is not needed | `jcmd` cannot retrieve a useful NMT report. |
| `summary` | Aggregates by subsystem/category, `malloc`/`mmap`/`arena`, reserved/committed | Which category is growing? Is JVM native memory increasing? | Insufficient data to trace detailed call sites. |
| `detail` | Everything in `summary` **plus** native allocation call sites and virtual memory/committed region map | Which allocation site is growing? Which native region makes the difference? | More detailed tracking and reporting can increase CPU, RAM, dump time, and output size. |

NMT alters the performance profile and uses memory itself; Oracle documentation gives a reference impact of **5–10% performance overhead**, depending on workload/build. Do not treat this figure as a guarantee for every configuration: benchmark your actual application when deploying in latency-sensitive environments. `detail` should be used purposefully when `summary` already points to an abnormal category without enough evidence.

**Selection rule:** start an investigation with `summary` for readability; when you need to pinpoint native C/C++ call sites, purposefully restart with `detail` from startup. No `jcmd` operation can accurately convert prior `summary` data into `detail`.

## 3. Ways to Launch the JVM with NMT

### 3.1 Direct Java Application Launch

```bash
java -XX:NativeMemoryTracking=summary -Xms256m -Xmx1g -jar application.jar
```

Switch to `detail` for deep investigation:

```bash
java -XX:NativeMemoryTracking=detail -Xms256m -Xmx1g -jar application.jar
```

Choose only **one** of the two levels per run. `-Xms`/`-Xmx` in the examples are illustrative heap settings, not prerequisites for NMT. `-XX` options must appear **before** `-jar` or the main class name:

```bash
# Unintended placement: arguments after application.jar are passed to main(String[] args)
java -jar application.jar -XX:NativeMemoryTracking=summary
```

The line above may pass an unexpected argument to the application while **JVM NMT remains disabled**.

### 3.2 Launching via Classpath

```bash
java -XX:NativeMemoryTracking=summary -cp out com.example.Main
```

No Java code needs to call an NMT API. The `-XX:NativeMemoryTracking` option is processed by the JVM **before `main` runs**. This syntax applies to compatible HotSpot/OpenJDK applications, including executable Spring Boot JARs launched via `java -jar`.

### 3.3 Containerized Applications

Place the option in the container's actual Java launch command. Example `exec` form in a Dockerfile:

```dockerfile
ENTRYPOINT ["java", "-XX:NativeMemoryTracking=summary", "-jar", "/app/application.jar"]
```

If the runtime starts via a wrapper script or orchestration config, verify the **final effective command** (entrypoint, args, environment) to ensure the flag reaches the Java process. You can set `JAVA_TOOL_OPTIONS=-XX:NativeMemoryTracking=summary` in an appropriate environment, but that variable affects **every JVM** inheriting it, including build tasks or helper tools; document its scope and test first. Avoid accidentally enabling `detail` across all services.

In containers, distinguish **the PID seen inside the container** from the PID seen on the host. `jcmd` must see the JVM in the same PID namespace, with a compatible Java tool and attach permissions. Do not infer PID from pod or service names.

### 3.4 Printing Statistics on Normal JVM Exit

Additional diagnostic options can tell HotSpot to print NMT at the end of the process lifecycle:

```bash
java -XX:NativeMemoryTracking=summary \
     -XX:+UnlockDiagnosticVMOptions \
     -XX:+PrintNMTStatistics \
     -jar application.jar
```

The example above uses Unix shell line-continuation syntax; on Windows PowerShell, put all options on **one line** or use PowerShell's line-continuation syntax. `-XX:+UnlockDiagnosticVMOptions` and `-XX:+PrintNMTStatistics` are for printing stats on exit; they are **not required** if you only want to enable `summary`/`detail` and inspect via `jcmd`. On `SIGKILL`, container OOM kill, or abrupt OS termination, do not expect this shutdown report to appear.

## 4. Verifying the Right Running JVM

Before analyzing, verify the version, PID, JVM options, and NMT status **on the target application**:

```bash
java -version
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
jcmd <PID> help VM.native_memory
jcmd <PID> VM.native_memory summary scale=MB
```

Replace `<PID>` with the actual PID listed, without typing `<` and `>`. `java -version` in the terminal only describes the binary in your shell PATH; `jcmd <PID> VM.version` confirms the runtime of **the target process**. `VM.command_line` or `VM.flags` verifies that the NMT flag was passed at startup, even when configuration comes from a launcher or script.

When NMT is not enabled, the JVM may return a message equivalent to "Native memory tracking is not enabled". That is a **startup configuration** issue, not a `jcmd` bug. When NMT is enabled at `summary`, running `detail` will not fabricate missing call sites. Read the actual output of your JDK and run `jcmd <PID> help VM.native_memory` to check the exact command syntax.

**Permissions:** `jcmd` typically requires the same host/namespace and a user with attach permissions; `-XX:+DisableAttachMechanism`, container PID namespaces, JDK images missing `jcmd`, or security restrictions can cause commands to fail even when NMT is enabled. When encountering attach errors, resolve permissions/deployment workflow per policy instead of concluding "NMT is off".

## 5. `summary`: Reading Aggregates and Separating Reserved from Committed

Start with:

```bash
jcmd <PID> VM.native_memory summary
jcmd <PID> VM.native_memory summary scale=MB
```

You will see a `Total` line followed by categories. General structure:

```text
Native Memory Tracking:
Total: reserved=..., committed=...
- Java Heap (reserved=..., committed=...)
- Class (reserved=..., committed=...)
- Thread (reserved=..., committed=...)
- Code (reserved=..., committed=...)
- GC (reserved=..., committed=...)
- Other (reserved=..., committed=...)
...
```

This is only a **field-layout sketch**; category names, category counts, and `malloc`/`mmap` details vary across JDKs, GCs, platforms, and configurations. Run `jcmd` on the target JVM to see real numbers.

- **Reserved**: virtual address range set aside by the JVM; not synonymous with bytes of physical RAM used. For example, with a large `-Xmx`, Java Heap may reserve a large range without committing all of it.
- **Committed**: memory committed for allocation by the OS as observed by NMT. This still **does not strictly equal RSS**: committed does not mean every page is resident in physical RAM at read time.
- **`malloc`**: memory allocated via native allocation paths tracked by NMT; output may include allocation counts.
- **`mmap`**: virtual address regions based on mappings/reservations, often related to Java Heap, class space, code cache, and other JVM areas.
- **`arena`**: chunk-based memory management for short-lived allocations; do not treat arena counts as leaked bytes of individual Java objects.

Common categories:

| Category | What to Look At | Example Next Investigation Steps |
| --- | --- | --- |
| `Java Heap` | Heap reserved/committed, affected by `-Xms`/`-Xmx` and GC | Cross-check `GC.heap_info`, heap usage, GC logs; NMT does not profile individual Java objects. |
| `Class` | Metaspace, class space, class metadata | Class loaders, dynamic class generation, class unloading, `VM.classloader_stats`/`VM.metaspace`. |
| `Thread` | Thread structures, native stack reservation/commit | Platform thread count, stack size, thread creation; do not infer exact live thread count from bytes alone. |
| `Code` | JIT-generated code / code cache | Compilation status and code cache usage. |
| `GC` | Garbage collector native structures | Active collector, CPU/heap count, GC config and supporting structures. |
| `Compiler` | C1/C2/JIT compiler resources | Warm-up, compilation activity, post-startup rise/fall cycles. |
| `Internal`, `Other` | Allocations tracked by HotSpot that do not fit specialized categories | Check `detail` and build-specific docs; avoid immediately blaming "Other = leak". |
| `Native Memory Tracking` | Memory used by the tracker itself | Observation overhead. |
| `Symbol`, `Arena Chunk`, `Module`, `Logging`… | JVM runtime structures | Track growth direction across checkpoints; categories may appear/vary by JDK. |

**Common mistake:** treating `Total reserved` as RAM in use, or computing `Total committed` minus `Java Heap committed` and calling the remainder "all native memory of the process". That subtraction only gives the non-heap portion **within NMT's scope**, excluding allocations HotSpot does not track.

## 6. `detail`: Viewing Native Call Sites and Virtual Memory Map

To see **JVM-side allocation sites** linked to memory growth, the JVM must be started with `detail`:

```bash
java -XX:NativeMemoryTracking=detail -jar application.jar
```

When running:

```bash
jcmd <PID> VM.native_memory detail scale=KB
```

In addition to the categories in `summary`, the report can include:

- **Virtual memory map**: reserved/committed address ranges with associated HotSpot call sources.
- **Call-site allocation statistics**: aggregated allocations by native allocation sites, sometimes showing C/C++ symbols or addresses depending on build and symbols.
- **Breakdown by `malloc`/`mmap` and committed regions**: helps identify which part of a category grew.

"Call site" here is **not a Java stack trace of individual objects**. NMT does not return the chain of Java methods that called `new` like a heap profiler. If you suspect a heap leak, use a heap dump/profiler; if you suspect JNI or C libraries allocating outside HotSpot, use OS/native tools or an appropriate profiler.

`detail` reports are often long; save artifacts with **timestamp, PID, JDK build, and NMT mode**. Use `detail.diff` after a baseline to focus on growth rather than scrolling through every address in the full report.

**Cannot switch level with a read command:** a JVM running `summary` provides `summary`/`summary.diff`; to get full `detail`/`detail.diff`, restart with `NativeMemoryTracking=detail`.

## 7. Baseline and Diff: Analyzing Trends Instead of One Snapshot

A single NMT snapshot shows current state; a leak hypothesis requires **repeated growth over time**. After the application warms up and before starting the measured load phase, set a baseline:

```bash
jcmd <PID> VM.native_memory baseline
```

After 5, 15, or 30 minutes of steady workload, capture the diff:

```bash
jcmd <PID> VM.native_memory summary.diff scale=MB
```

If started with `detail`, you can use:

```bash
jcmd <PID> VM.native_memory detail.diff scale=KB
```

`summary.diff`/`detail.diff` display **current values and increases/decreases** relative to the baseline; plus/minus signs indicate the delta, not whether the current total itself is small or large. Calling `baseline` again replaces the reference point, so record the baseline timestamp and avoid accidentally resetting it mid-measurement.

Sample workflow:

1. Start the app with NMT and verify `VM.native_memory summary` works.
2. Let the app warm up; record heap committed, RSS/working set, CPU, thread count, request rate, DB/network load, and collector.
3. Set `baseline` **after warm-up**; mark the exact timestamp.
4. Run a controlled workload; capture `summary.diff` multiple times and save each output.
5. If a category grows steadily across multiple load-stop/GC cycles without returning to baseline levels, escalate to deep investigation (e.g., a new `detail` run).
6. Run a control workload and cross-check process-level RSS; verify whether growth comes from legitimate caching, JIT, class loading, GC sizing, or memory pools before calling it a leak.

**There is no absolute rule "positive delta = leak".** The JVM normally grows memory during warm-up, compilation, class metadata expansion, GC, or connection pools. Small leaks require longer observation windows; test under comparable load and object/resource lifecycles.

## 8. Java 17+ Example: Seeing NMT Before and After a Native Allocation

Save the following standalone program as **`NmtStartupDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.ByteBuffer;

public class NmtStartupDemo {
    private static volatile ByteBuffer retained;

    public static void main(String[] args) throws Exception {
        BufferedReader console =
                new BufferedReader(new InputStreamReader(System.in));

        System.out.println("READY");
        console.readLine();

        retained = ByteBuffer.allocateDirect(32 * 1024 * 1024);
        retained.put(0, (byte) 1);
        System.out.println("ALLOCATED");

        console.readLine();
        System.out.println("DONE");
    }
}
```

`ByteBuffer.allocateDirect` requests a direct buffer of roughly **32 MiB** outside the regular Java heap; `retained` holds a reference so the buffer is not eligible for reclamation during measurement. Writing one byte ensures at least the start of the buffer is touched. The code requires no preview APIs; use **JDK 17+ and HotSpot** for the NMT steps.

Compile:

```bash
javac --release 17 NmtStartupDemo.java
```

**Terminal 1** — run in `summary` mode:

```bash
java -XX:NativeMemoryTracking=summary -Xms128m -Xmx512m NmtStartupDemo
```

The program prints `READY` and **waits for Enter**. On **terminal 2**, find the PID of `NmtStartupDemo` and set a baseline:

```bash
jcmd -l
jcmd <PID> VM.native_memory summary scale=MB
jcmd <PID> VM.native_memory baseline
```

Return to terminal 1 and **press Enter once** to allocate the buffer. When you see `ALLOCATED`, switch to terminal 2:

```bash
jcmd <PID> VM.native_memory summary.diff scale=KB
```

Inspect the category with a positive delta from the allocation; on many HotSpot builds, direct buffers may appear under `Other`/`malloc`, though **no specific category name or exact 32,768 KB output is guaranteed**: the runtime incurs additional metadata and background allocations. Cross-check changes in `Total committed`, categories, and RSS; percentages and addresses are not fixed.

Finally, press Enter a second time in terminal 1 to exit. If the user presses Enter **twice**, the stdout lines **printed by the program**, in order, are:

```text
READY
ALLOCATED
DONE
```

The `jcmd` commands in terminal 2 produce separate output and are not the application's stdout.

**Re-run with `detail`:** after the previous app exits, run:

```bash
java -XX:NativeMemoryTracking=detail -Xms128m -Xmx512m NmtStartupDemo
```

Repeat the baseline step before the first Enter, then run:

```bash
jcmd <PID> VM.native_memory detail.diff scale=KB
```

Compare the call-site details that appear in `detail` but are absent in `summary`. This is an educational simulation, not a leak measurement: the buffer is intentionally held briefly, and process resources are reclaimed by the OS on exit. On systems lacking an interactive console, `readLine()` may receive EOF and exit early; run in an interactive terminal to reproduce the steps accurately.

## 9. Real-World Operations: From Symptoms to Action

### Case A — Container OOM-Killed, Java Heap Not Full

**Observation:** `-Xmx` appears smaller than the container memory limit, yet RSS keeps climbing. **Action:** enable `summary` on the next deploy; collect NMT over time alongside cgroup/container memory, RSS, thread stacks, native libraries, and memory mappings. If NMT `Total committed` rises correspondingly, identify the category; if RSS rises while NMT stays flat, expand investigation to native/JNI libraries/allocators and OS page mappings.

**Do not conclude:** low NMT proves the process is not consuming memory; the tracker's scope has limits.

### Case B — `Thread` Grows Steadily After Each Request Wave

**Hypothesis:** platform threads are growing, or thread lifecycle/pool config is not releasing them. **Action:** compare NMT `Thread` with thread dumps, OS thread counts, pool executors, and stack sizes. Stack `reserved` can be much larger than `committed`. Do not use NMT as the sole source for counting virtual threads, and do not assume each virtual thread has a dedicated OS stack.

### Case C — `Class` Grows While Heap Does Not Grow Proportionally

**Hypothesis:** growing metaspace/classloaders, proxy/bytecode generation, hot reload, or unreleased classloaders. **Action:** compare `Class`, `VM.classloader_stats`, `VM.metaspace`, loaded class count, and deployment history; when exact native sources are needed, run `detail`. Class metadata rising for a period after startup can be normal.

### Case D — `Code` or `GC` Grows After Warm-Up

**Hypothesis:** JIT code cache / GC structures being allocated on demand. **Action:** keep JDK, collector, `-Xms/-Xmx`, warm-up duration, and load constant; inspect deltas across phases. If the curve gradually flattens and memory stays within bounds, there is no evidence of a leak.

### Case E — `Other` Grows Steadily, `summary` Cannot Explain Enough

**Action:** save snapshots, create a reproduction environment, and **restart with `detail`**; take a baseline after warm-up, reproduce the workload, and call `detail.diff`. If HotSpot call sites do not grow while RSS still grows, investigate native allocations outside NMT. Do not rely on the `Other` label alone to blame the application or a specific library.

## 10. Operational Errors and Fixes

| Symptom | Common Cause | How to Check / Fix |
| --- | --- | --- |
| `VM.native_memory` reports NMT is not enabled | Startup missing flag, flag placed after `-jar`, config updated without restarting process | Check `VM.command_line`/`VM.flags`, fix Java command and restart. |
| `detail` has no call sites | Process only enabled `summary` | Relaunch with `-XX:NativeMemoryTracking=detail`; cannot "upgrade" via `jcmd`. |
| `summary.diff` errors or has no baseline | `baseline` has not been called in the current JVM | Call `baseline` after warm-up then capture diff; baselines do not persist across process restarts. |
| `jcmd` cannot attach | Different user/PID namespace, tool missing from image, attach disabled, unsupported non-HotSpot JVM | Check PID namespace, user, Java version, `jcmd -l`, and runtime policy. |
| `Total reserved` is huge | Large virtual address reservation for heap/class space | Compare `committed`, RSS, `-Xmx`, cgroup; reserved differs from actual RAM used. |
| NMT cannot explain RSS growth | Outside JVM tracking scope, native libraries, OS mappings, or RSS differing from committed | Use `pmap`/`smaps` on Linux, process memory tools, native profilers, and OS metrics. |
| Results change when upgrading JDK/GC | Different categories, allocation implementations, and GC configurations | Compare under the same workload, build, GC, and flags; avoid comparing single numbers without context. |
| Stopping NMT with `VM.native_memory shutdown` | Tracker disabled in the current process | To track again, restart the process with the NMT flag. |

Do not overlook measurement cost: `detail` can add overhead and huge output, especially when polled continuously. For critical processes, consider `summary` level, capture frequency, and measurement duration, then reproduce with `detail` in staging when deep analysis is needed. NMT reports can also expose runtime-sensitive addresses/native symbols; store them in access-controlled locations.

## 11. Distinguishing NMT from Other Memory Metrics

| Data | What Does It Measure / Observe? | Directly Answered by "NMT summary/detail"? |
| --- | --- | --- |
| NMT `reserved` | Virtual address space reserved by HotSpot | Yes; not physical RAM. |
| NMT `committed` | Memory HotSpot committed for allocation | Yes; not strictly equal to RSS. |
| Java heap used | Bytes of objects remaining on the heap per GC/runtime | No; use heap/GC metrics or heap profilers. |
| RSS / working set | Process pages currently resident in RAM per the OS | No; use OS/container metrics. |
| cgroup container memory | Memory charged against the container limit | No; check cgroup/monitoring. |
| JNI / third-party native `malloc` | Allocations outside HotSpot NMT visibility | Usually no; use a native allocation profiler or OS tools. |
| Buffer pool (direct/mapped) | Pool statistics from `BufferPoolMXBean` | Independent; combine to explain buffer allocations. |

For example, when Java heap `reserved=1GiB` and `committed=256MiB`, adding **1 GiB + native committed** exaggerates RAM consumed because 1 GiB is reserved virtual address space. Conversely, looking only at heap used can miss Thread Stacks, GC, Code Cache, or native library allocations. Sound operational decisions require looking at **heap usage, NMT deltas, RSS/container metrics, and application load** together.

## 12. Checklist Before Confirming NMT Is Enabled Properly

- [ ] `-XX:NativeMemoryTracking=summary` or `detail` is placed **before `-jar`/main class** in the actual Java command.
- [ ] The JVM was restarted after editing startup options, and the **runtime PID/JDK** matches the target app.
- [ ] `jcmd <PID> VM.command_line`/`VM.flags` confirms the flag; `VM.native_memory summary` returns a valid report.
- [ ] Chose `summary` for category analysis and `detail` when call sites are genuinely needed; aware that level cannot be upgraded in the same process.
- [ ] Understand that `reserved` differs from `committed`, both differ from RSS, and NMT has coverage limits.
- [ ] Recorded JDK/HotSpot version, GC, `-Xms/-Xmx`, PID, OS/container, load, and timestamp for each sample.
- [ ] Set `baseline` after warm-up and collected `summary.diff` or `detail.diff` multiple times under a controlled workload.
- [ ] Evaluated overhead on critical workloads and avoided overly frequent detail dumps.
- [ ] If suspecting a native leak outside the JVM, added OS/native metrics before attributing root cause.
- [ ] If `PrintNMTStatistics` is enabled, understand that abruptly killed processes may not print exit reports.

## 13. Official Reference Documentation

1. Oracle Java 21 VM Guide, *Native Memory Tracking* — describes modes, `jcmd`, baseline, coverage limits, and exit stats: https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html
2. Oracle Java 26 VM Guide, *Native Memory Tracking* — verify the same startup mechanisms on modern JDKs: https://docs.oracle.com/en/java/javase/26/vm/native-memory-tracking.html
3. Oracle Java 26 `jcmd` manual — `VM.native_memory` syntax and options: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html
4. Oracle Java 21 Troubleshooting Guide, *Diagnostic Tools* — categories, `summary/detail`, `baseline/diff`, and reading examples: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
5. Oracle `java` launcher options — `-XX:NativeMemoryTracking` syntax on specific builds: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html

**Practical rule:** choose the NMT level at startup, verify on the exact process, record a baseline after warm-up, and cross-check **category/call-site deltas** against OS metrics. NMT excels at isolating HotSpot-managed memory, but it is insufficient on its own to settle every native leak or application RSS question.
