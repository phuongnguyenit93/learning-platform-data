# Using `jcmd` GC Commands for JVM Diagnostics

`jcmd` is a JDK command-line tool used to send diagnostic commands to a running Java Virtual Machine (JVM). The `GC.*` command group provides heap information, object statistics, finalization queue details, garbage collection triggers, and heap dumps for memory analysis.

Common commands:

| Command | Purpose |
|---|---|
| `GC.heap_info` | View general information about the Java heap |
| `GC.class_histogram` | Report object counts and byte sizes by class |
| `GC.heap_dump` | Create a heap dump in HPROF format |
| `GC.run` | Invoke `System.gc()` on the target JVM |
| `GC.finalizer_info` | View information about the finalization queue |
| `GC.run_finalization` | Invoke `System.runFinalization()` |

Not all commands are read-only. `GC.heap_info` provides general diagnostics; `GC.class_histogram` and `GC.heap_dump` can generate significant load; `GC.run` can request a GC cycle; and a heap dump can cause pauses and produce large files. Choose the command based on the question you need to answer, check its impact, and run it against the right JVM.

The toolchain verified for this guide is Zulu/OpenJDK 24.0.2. The available commands and options depend on the JDK version, target JVM, and collector; always use `jcmd <pid> help` to see what the process actually supports.

## 1. How `jcmd` Sends Commands to a JVM

`jcmd` communicates with a JVM through the attach mechanism and the diagnostic command framework. Each running JVM has a process ID (PID); the operator selects the PID and sends a command supported by that JVM.

General syntax:

~~~text
jcmd <pid> <command> [arguments]
~~~

Usage forms:

~~~text
jcmd -l
jcmd <pid> help
jcmd <pid> help GC.heap_info
jcmd <pid> GC.heap_info
~~~

- `jcmd -l`: lists the JVMs visible to the tool on the current machine.
- `jcmd <pid> help`: lists the commands supported by the target JVM.
- `jcmd <pid> help <command>`: shows the syntax, options, and impact level of a specific command.
- `jcmd <pid> <command>`: sends the command to the selected process.

If you pass PID `0`, `jcmd` sends the command to all Java processes it can manage. Avoid using PID `0` with commands that create heap dumps or trigger GC, as this can affect multiple applications simultaneously.

`jcmd` runs on the same machine as the target JVM. The tool usually needs to run under the same user account as the process; the attach mechanism may be disabled or restricted by the security environment. In containers, run it from the appropriate container/PID namespace or an environment that can see the target process.

## 2. Finding the Right Java Process

Start with:

~~~text
jcmd -l
~~~

Illustrative example output:

~~~text
18240 com.example.OrderService
29116 com.example.ReportWorker
31552 jdk.jshell/jdk.internal.jshell.tool.JShellToolProvider
~~~

PIDs change on every startup. Do not copy example PIDs into a real environment; obtain the PID from the current output.

You can use the main class name to locate a process:

~~~text
jcmd OrderService help
~~~

However, when multiple processes share the same main class or have similar names, using the PID is clearer and safer.

After finding the PID, verify you have the right JVM before running high-impact commands:

~~~text
jcmd 18240 VM.command_line
jcmd 18240 VM.version
jcmd 18240 VM.info
~~~

These `VM.*` commands help verify the process's command line, version, and runtime information. They do not replace confirming the owner, environment, and operational purpose.

## 3. Viewing GC Commands and Detailed Help

Do not guess commands or options based on another JDK. Query the target JVM directly:

~~~text
jcmd 18240 help
~~~

Filter the GC-related commands in the output, for example:

~~~text
GC.class_histogram
GC.finalizer_info
GC.heap_dump
GC.heap_info
GC.run
GC.run_finalization
~~~

Then view the individual help pages:

~~~text
jcmd 18240 help GC.class_histogram
jcmd 18240 help GC.heap_dump
~~~

Command help shows:

- Exact syntax.
- Supported options.
- Option data types.
- Default values.
- The impact level reported by the JVM.

On JDK 24.0.2, `GC.class_histogram` and `GC.heap_dump` are marked with High impact; `GC.heap_info`, `GC.run`, `GC.finalizer_info`, and `GC.run_finalization` have Medium impact. Impact levels are guidelines for planning, not guarantees of execution time.

## 4. `GC.heap_info`: Viewing a Java Heap Overview

Usage:

~~~text
jcmd 18240 GC.heap_info
~~~

This command returns general information about the target JVM's Java heap. Depending on the collector and version, the output may include:

- Heap capacity or total heap region size.
- Used and free space.
- G1 region information.
- Generation or pool sizes exposed by the collector.
- Various internal heap-related metrics.

Illustrative example output:

~~~text
Garbage-First (G1) Heap
regions: ...
Heap Usage:
   ...
~~~

Do not use illustrative numbers to predict an application's memory usage. Field names, units, and output structure depend on the collector.

### When should you use it?

- Checking overall heap usage.
- Comparing state before and after an operational action.
- Confirming whether the JVM heap is near its configured limit.
- Gathering initial data before deciding to take a histogram or heap dump.

`GC.heap_info` does not show which objects are retaining memory. If you need to find classes consuming the most space, use `GC.class_histogram`; if you need to analyze the object graph and retaining paths, you need a heap dump and an appropriate analysis tool.

## 5. `GC.class_histogram`: Object Statistics by Class

Usage:

~~~text
jcmd 18240 GC.class_histogram
~~~

This command generates a histogram of objects in the Java heap. The output typically has these columns:

| Column | Meaning |
|---|---|
| `num` | Row number in the report |
| `#instances` | Number of instances of the class |
| `#bytes` | Total bytes accounted for by those instances |
| `class name` | Class name; may include the module |

Example output structure:

~~~text
 num        #instances          #bytes  class name (module)
   1:             ...             ...  [B (java.base)
   2:             ...             ...  java.lang.String (java.base)
   3:             ...             ...  java.util.HashMap$Node (java.base)
 ...
 Total             ...             ...
~~~

The `...` placeholders represent values that vary per process. A histogram is a point-in-time snapshot, not a measure of allocation rate over time.

### 5.1. The `-all` Option

According to JDK 24.0.2 help:

- Default `-all=false`: does not require inspecting all objects including unreachable objects.
- `-all=true`: inspects unreachable objects as well.
- `-parallel=0`: lets the JVM choose the number of inspection threads; `1` disables parallelism; other values request the specified number of threads, though the JVM may use fewer.

Examples:

~~~text
jcmd 18240 GC.class_histogram -all=true
jcmd 18240 GC.class_histogram -parallel=1
~~~

`-all=true` changes the set of objects counted, so results should not be compared directly with the default histogram without noting the option.

### 5.2. How to Read a Histogram

If a class has a large number of instances, ask:

- Is the application intentionally caching many objects?
- Is a collection growing without bounds?
- Are objects being held by static fields or singletons?
- Are strings, byte arrays, or buffers kept longer than expected?
- Are many small instances adding up to a large total size?

A histogram does not display full reference relationships. A class with a large total byte count is not necessarily the root cause; you need to analyze what is retaining those objects. Use a heap dump to inspect the dominator tree, retained size, and reference paths when needed.

`GC.class_histogram` has High impact because it must inspect the heap. On large heaps, the command can consume significant CPU and cause noticeable pauses. Avoid running it continuously in production just for routine observation.

## 6. `GC.heap_dump`: Creating an HPROF Heap Dump

Usage:

~~~text
jcmd 18240 GC.heap_dump D:\diagnostics\orders.hprof
~~~

On macOS/Linux:

~~~text
jcmd 18240 GC.heap_dump /var/tmp/orders.hprof
~~~

A heap dump contains information about objects and reference relationships in the heap at the moment of capture. You can open the file with Eclipse MAT, VisualVM, or any tool that supports the HPROF format.

According to JDK 24.0.2 help, `GC.heap_dump` supports these options:

| Option | Purpose |
|---|---|
| `-all` | Dump unreachable objects as well |
| `-gz=1` | Write a gzip-compressed dump; level 1 is fastest |
| `-gz=9` | Higher compression, more CPU usage |
| `-overwrite=true` | Allow overwriting an existing dump file |
| `-parallel=1` | Request a single thread to create the heap dump |

Example creating a gzip-compressed file:

~~~text
jcmd 18240 GC.heap_dump -gz=1 D:\diagnostics\orders.hprof.gz
~~~

### 6.1. Impact of a Heap Dump

Creating a heap dump is a High-impact operation:

- It can take a long time depending on heap size and object count.
- It can cause safepoint pauses or affect latency.
- It requires sufficient disk space; files can be very large.
- By default, the JVM requests a full GC before dumping, unless `-all` is specified.
- With `-all`, the dump includes unreachable objects and does not request a full GC, per the behavior described in the help output.
- The dump file is created on the target JVM's machine/namespace using that process's permissions.

Do not write heap dumps to shared paths without enough disk space. Use an absolute path, verify write permissions, and confirm the target file does not already exist unless you intend to overwrite it.

### 6.2. Protecting Data in Heap Dumps

Heap dumps can contain:

- Access tokens, session IDs, and API keys.
- Passwords or authentication data still in memory.
- Users' personal information.
- Request/response payloads and business data.
- Sensitive data in caches or buffers.

Treat heap dumps as sensitive data. Restrict access permissions, store them in approved locations, encrypt them at rest and in transit, set retention periods, and delete them according to policy after analysis. Do not attach dumps directly to public tickets.

## 7. `GC.run`: Requesting the JVM to Run Garbage Collection

Usage:

~~~text
jcmd 18240 GC.run
~~~

According to help, this command invokes:

~~~java
System.gc();
~~~

This is an explicit GC request. It does not guarantee that all unreferenced objects will be reclaimed immediately, and actual behavior depends on the collector and JVM configuration.

Notes:

- `System.gc()` may be ignored if the JVM is running with `-XX:+DisableExplicitGC`.
- The collector may perform a full GC or take another action depending on its implementation.
- A GC cycle can cause pauses, increase CPU usage, and affect latency.
- Running it repeatedly is not a fix for a memory leak.
- Memory reclaimed inside the heap is not necessarily returned immediately to the operating system.

Do not use `GC.run` as a periodic "memory cleanup" step in production. If you suspect a memory leak, collect metrics, a histogram, or a heap dump to identify which references are holding the objects.

## 8. `GC.finalizer_info` and `GC.run_finalization`

These two commands relate to Java's legacy finalization mechanism.

### 8.1. Viewing the Finalization Queue

~~~text
jcmd 18240 GC.finalizer_info
~~~

This command provides information about the Java finalization queue. It is useful when investigating applications that still rely on `finalize()` or when the finalizer queue grows abnormally.

Do not use the finalizer count as a general measure of garbage collection. Finalization is a separate mechanism with non-deterministic execution timing and can delay object reclamation.

### 8.2. Requesting Finalization to Run

~~~text
jcmd 18240 GC.run_finalization
~~~

This command invokes `System.runFinalization()`. It asks the JVM to run pending finalizers on a best-effort basis; it does not guarantee that all finalizers will run immediately or in any specific order.

Finalization has been deprecated for removal since Java 18. New code should use `AutoCloseable`, `try-with-resources`, `Cleaner` when genuinely needed, or explicit resource management APIs. Do not rely on `GC.run_finalization` to close files, sockets, or native resources in normal operational flows.

## 9. Choosing a GC Command by Question

| Question | Appropriate command | Impact to consider |
|---|---|---|
| How much heap is currently in use? | `GC.heap_info` | Medium |
| Which classes have many instances or occupy many bytes? | `GC.class_histogram` | High |
| Which objects retain memory and what are the reference paths? | `GC.heap_dump` followed by HPROF analysis | High |
| Can we ask the JVM to run GC to test a hypothesis? | `GC.run` | Medium; may cause pauses |
| Is there an issue with the finalization queue? | `GC.finalizer_info` | Medium |
| Do we need to request processing of legacy finalizers? | `GC.run_finalization` | Medium; do not use as a cleanup strategy |

A sound workflow for investigating memory pressure:

1. Collect metrics and GC logs to identify trends.
2. Use `GC.heap_info` to get a general heap overview.
3. If object breakdown is needed, run `GC.class_histogram` at an appropriate time.
4. If the reference graph is needed, plan a heap dump.
5. Analyze retained size and the dominator tree using an HPROF tool.
6. Identify the code retaining the objects, fix the root cause, and measure again.

Do not start with a heap dump for every incident. Use lower-impact operations if they are sufficient to answer the question.

## 10. Java 17 Example: Creating a JVM to Practice GC Commands

Create `GcDemo.java`:

~~~java
public final class GcDemo {
    private static byte[][] retained;

    private GcDemo() {
    }

    public static void main(String[] args) throws InterruptedException {
        retained = new byte[8][];
        for (int i = 0; i < retained.length; i++) {
            retained[i] = new byte[1024 * 1024];
        }

        System.out.println(
                "GC demo ready; retained arrays=" + retained.length);

        Thread.sleep(300_000);
    }
}
~~~

The array is held in a static field so the byte arrays remain reachable while the process waits. The program only creates test data and does not access the network or files.

Compile:

~~~text
javac --release 17 GcDemo.java
~~~

Run in the first terminal:

~~~text
java -Xms64m -Xmx128m GcDemo
~~~

Stdout:

~~~text
GC demo ready; retained arrays=8
~~~

The program waits up to five minutes so you have time to send diagnostic commands. Open a second terminal and find the PID:

~~~text
jcmd -l
~~~

Find the line with the main class `GcDemo`, then replace `<PID>` with the actual PID in the following commands:

~~~text
jcmd <PID> help
jcmd <PID> GC.heap_info
jcmd <PID> GC.class_histogram
jcmd <PID> GC.finalizer_info
~~~

You can create a heap dump to practice analysis:

~~~text
jcmd <PID> GC.heap_dump -gz=1 gc-demo.hprof.gz
~~~

The heap dump command has High impact and may request a full GC by default. Only run it when you have prepared storage space and can accept a pause. Terminate the program with `Ctrl+C` in the first terminal.

PIDs and heap figures vary by machine, JDK, and collector; only the stdout line printed by the program is fixed.

## 11. Running a Group of Diagnostic Commands in PowerShell

You can collect several pieces of diagnostic information in a single script. Use the `$javaPid` variable instead of `$pid`, because PowerShell already has the automatic `$PID` variable.

~~~powershell
$javaPid = 18240

jcmd $javaPid VM.version
jcmd $javaPid VM.command_line
jcmd $javaPid GC.heap_info
jcmd $javaPid GC.class_histogram
~~~

Each command is sent individually and its output appears in the terminal. The histogram has High impact; consider the timing before adding it to an automated script.

If you need to save output, redirect each command to a file with appropriate permissions. For a heap dump, use a separate command and specify an explicit path:

~~~powershell
jcmd $javaPid GC.heap_dump -gz=1 D:\diagnostics\app.hprof.gz
~~~

Do not run multiple heap dumps concurrently on the same JVM without evaluating the impact on pauses, CPU, and disk I/O.

## 12. Permissions, Containers, and Attach Limitations

If `jcmd -l` does not list the expected JVM, check:

- `jcmd` is running on the right host machine.
- The user running `jcmd` has permission to attach to the target JVM.
- The JVM and `jcmd` are in the same/appropriate PID namespace or container.
- The process has not exited and the PID has not been reused.
- The attach mechanism is not disabled with `-XX:+DisableAttachMechanism`.
- Security policies or the runtime environment are not blocking the attach listener.

In containers, the PID shown from the host may differ from the PID inside the container. Running `jcmd -l` and `jcmd` inside the same container or namespace is the most reliable way to identify the right PID.

Some serverless environments, hardened containers, or processes started with attach disabled may not allow `jcmd`. In those cases, rely on GC logs, JFR, metrics, and platform-supported diagnostics.

## 13. How GC Commands, GC Logs, and JFR Differ

`jcmd GC.*` commands are point-in-time diagnostics or actions. GC logs and JFR are better suited for observing trends over time.

### GC Logging

You can enable logging at JVM startup:

~~~text
-Xlog:gc*
~~~

GC logs show GC frequency, pause times, heap occupancy, and collector details per event. For production applications, configure log rotation and output file locations from the start.

### Java Flight Recorder

JFR records runtime events such as GC, allocations, threads, locks, and more. JFR is well suited when you need to correlate memory behavior with application activity over a period of time.

`jcmd` also provides `JFR.*` commands on many JDKs, but they are not part of the `GC.*` group. Check `jcmd <pid> help JFR.start` before using them.

Do not rely on a single histogram or heap dump to draw conclusions about allocation rate or pause distribution. Combining multiple observation sources gives a clearer picture of the root cause.

## 14. Troubleshooting GC Commands

### `No such process`

**Cause:** The PID does not exist, the process has exited, or the PID was taken from a different namespace.

**Resolution:** Re-run `jcmd -l` in the right environment and verify the PID before sending commands.

### `AttachNotSupportedException` or Unable to Attach

**Cause:** Different user, attach mechanism disabled, mismatched container/PID namespace, or a security environment blocking attach.

**Resolution:** Run under the appropriate user, check `-XX:+DisableAttachMechanism`, and execute from the right host/container. Do not arbitrarily relax process security permissions.

### `Unknown diagnostic command`

**Cause:** The target JVM does not support that command, or the command has a different name in the current JDK.

**Resolution:** Run `jcmd <PID> help`, then check `help <command>` on the target JVM itself.

### `GC.class_histogram` Runs Slowly

**Cause:** Large heap, high object count, or heap inspection generating significant load.

**Resolution:** Choose a low-traffic window, check metrics first, limit how often it runs, and consider `-parallel` per the JVM's help output.

### `GC.heap_dump` Fails

**Cause:** Insufficient disk space, nonexistent path, missing write permissions for the process, or the file already exists without overwrite enabled.

**Resolution:** Use an absolute path, verify disk space and permissions, and only enable `-overwrite=true` when overwriting is explicitly intended.

### Heap Dump Causes Long Application Pauses

**Cause:** Dumping must traverse a large number of objects and may request a full GC by default.

**Resolution:** Schedule during a maintenance window, weigh the pause cost, use `-gz` to reduce storage size, and only use `-all` when unreachable objects are needed.

### `GC.run` Does Not Reduce Heap as Expected

**Cause:** Objects are still reachable, explicit GC is disabled, the collector makes a different decision, or the heap has not returned memory to the OS.

**Resolution:** Check references and retained size with histograms and heap dumps; review GC logs. Do not repeat `GC.run` to mask a memory leak.

### Histogram Changes Between Runs

**Cause:** Different workload, allocations, GC activity, and capture timing.

**Resolution:** Compare under equivalent load conditions and record the `-all` option, timestamp, and collector; do not treat two snapshots from different times as strictly equivalent measurements.

## 15. Checklist Before Running GC Commands in Production

- [ ] Identified the correct host, container, PID, and JVM owner.
- [ ] Confirmed the JDK/JVM version and supported commands with `jcmd <PID> help`.
- [ ] Reviewed the impact and options of the specific command.
- [ ] Defined the diagnostic question that needs to be answered.
- [ ] Considered pause, CPU, and memory overhead.
- [ ] Running `GC.run` only with a clear reason; not using it as a memory leak fix.
- [ ] Running histograms/heap dumps only after evaluating load.
- [ ] Verified path, disk space, and permissions for any heap dump.
- [ ] Protected dump files as sensitive data.
- [ ] Not using PID `0` for commands that can affect multiple JVMs.
- [ ] Saved output with timestamp, PID, JDK version, and command line.
- [ ] Cross-checked results against GC logs, metrics, or JFR before concluding.
- [ ] Planned cleanup of dump files according to the retention policy.

`jcmd` GC commands help inspect the heap and gather evidence when investigating memory issues. Use `GC.heap_info` to start, `GC.class_histogram` to classify objects, and `GC.heap_dump` when you need to analyze the reference graph. Understanding the impact, verifying the target JVM, and protecting dump data will make diagnostics safer in both development and production environments.