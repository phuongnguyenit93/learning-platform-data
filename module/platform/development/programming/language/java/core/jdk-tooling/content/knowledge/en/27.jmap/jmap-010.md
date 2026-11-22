# jmap and jcmd in Java Memory Diagnostics

**`jmap`** and **`jcmd`** are two JDK command-line tools used to inspect a running Java Virtual Machine (JVM). Both can assist with heap analysis, object statistics, and generating heap dumps. `jcmd` also provides a broader diagnostic command system, including thread dumps, VM flags, classloaders, Java Flight Recorder (JFR), and native memory.

In modern workflows, **`jcmd`** should be preferred because it is the diagnostic interface recommended by Oracle. `jmap` remains useful when working with legacy commands or when specialized syntax for heap histograms or heap dumps is needed, though the JDK documentation marks it as experimental and unsupported.

## 1. Roles of jmap and jcmd

Both tools connect to a running local JVM to collect diagnostic data.

**`jmap`** focuses on memory and heap information:

- Summarizes object counts and sizes by class.
- Generates heap dumps in HPROF format.
- Displays classloader statistics.
- Lists objects awaiting finalization on JDKs that still support this command.

**`jcmd`** sends diagnostic commands to the target JVM. Its command set is broader:

- Heap: `GC.heap_info`, `GC.class_histogram`, `GC.heap_dump`.
- Classloader: `VM.classloader_stats`, `VM.classes`.
- Thread: `Thread.print`.
- JVM: `VM.flags`, `VM.command_line`, `VM.system_properties`, `VM.info`.
- JFR: `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
- Native memory: `VM.native_memory` when Native Memory Tracking is enabled.

Both tools can trigger resource-intensive operations. Heap histograms and heap dumps may pause the JVM, trigger GC, or consume significant CPU and I/O. Choose commands based on the specific diagnostic question and check their Impact level before running them.

## 2. Quick Comparison of jmap and jcmd

| Criterion | `jmap` | `jcmd` |
| --- | --- | --- |
| Scope | Primarily heap and classloaders | Heap, GC, threads, JFR, VM flags, classloaders, native memory, and many more |
| Process selection | PID | PID or main class; can list JVMs |
| List JVMs | No equivalent `-l` mode | `jcmd -l` |
| Heap histogram | `jmap -histo` | `GC.class_histogram` |
| Heap dump | `jmap -dump` | `GC.heap_dump` |
| Classloader stats | `jmap -clstats` | `VM.classloader_stats` |
| Thread dump | Not its primary function | `Thread.print` |
| JFR | No | `JFR.start/check/dump/stop` |
| Native memory | Not its primary function | `VM.native_memory` |
| Usage guidance | Useful for traditional heap operations | Preferred for modern diagnostic workflows |

Oracle marks `jmap` as experimental/unsupported and recommends `jcmd` for JVM diagnostics. Specific commands still depend on the JDK version, JVM vendor, and process state.

## 3. Checking Version and Help

Use tools from the same JDK or a JDK compatible with the target JVM. Check versions:

```bash
java -version
jmap -h
jcmd -h
```

`jmap` help displays the main command groups:

```text
jmap -clstats <pid>
jmap -finalizerinfo <pid>
jmap -histo[:[<histo-options>]] <pid>
jmap -dump:<dump-options> <pid>
```

`jcmd` help shows the general syntax:

```text
jcmd <pid | main class> <command ...>
jcmd -l
jcmd -h
```

`jcmd` does not have a single fixed list of commands that applies to every JVM. Query the target JVM directly:

```bash
jcmd 18420 help
jcmd 18420 help GC.heap_info
jcmd 18420 help GC.class_histogram
jcmd 18420 help GC.heap_dump
```

The `help <command>` command also provides syntax, options, and Impact information for that command. This is a necessary step before running a command that may heavily impact production.

## 4. Finding the Right JVM to Diagnose

Use `jcmd -l` to list JVMs visible to the current account:

```bash
jcmd -l
```

Sample output:

```text
18420 com.example.app.Main
29116 org.apache.catalina.startup.Bootstrap
```

`jmap` typically accepts a PID:

```bash
jmap -histo:live 18420
```

`jcmd` accepts a PID or main class name:

```bash
jcmd 18420 VM.uptime
jcmd com.example.app.Main VM.uptime
```

Prefer the PID when multiple instances run the same main class. The PIDs in these examples are illustrative only; obtain the actual PID from your live environment.

You can use target `0` with `jcmd` to send a command to all discovered JVMs. Do not use this in routine operations because the command can affect multiple applications simultaneously.

Attaching depends on the user, OS permissions, PID namespace, and JVM configuration. With Docker/Kubernetes, you may need to run the tool in the same container or PID namespace as the target process.

## 5. Viewing a Java Heap Overview

`jcmd GC.heap_info` provides an overview of the heap and several related memory regions:

```bash
jcmd 18420 GC.heap_info
```

Sample output with G1:

```text
18420:
 garbage-first heap   total reserved 30932992K, committed 2113536K, used 23419K
 region size 16384K, 2 young (32768K), 0 survivors (0K)
 Metaspace       used 1349K, committed 1536K, reserved 1114112K
 class space    used 85K, committed 192K, reserved 1048576K
```

Meaning:

- **Reserved:** address space reserved by the JVM.
- **Committed:** memory committed for JVM use.
- **Used:** memory currently in use according to the collector's statistics.
- **Metaspace:** native memory region storing class metadata.
- **Class space:** region reserved for compressed class pointers when the JVM uses this mechanism.

The numbers and formatting depend on the collector, JVM version, and application state.

`GC.heap_info` is useful for quickly checking how much heap is in use. It does not show which objects are retaining memory and does not replace a heap dump or histogram.

## 6. Generating a Class Histogram with jmap

A class histogram summarizes instance counts and object sizes by class. Using `jmap`:

```bash
jmap -histo 18420
```

According to JDK 24 help, if neither `live` nor `all` is specified, `jmap -histo` defaults to counting all objects in the heap.

Count only live objects:

```bash
jmap -histo:live 18420
```

Explicitly specify all objects:

```bash
jmap -histo:all 18420
```

Save the histogram to a file:

```bash
jmap -histo:live,file=histogram.txt 18420
```

You can adjust the number of threads used during heap inspection:

```bash
jmap -histo:live,parallel=1 18420
```

Sample output:

```text
 num     #instances         #bytes  class name
-------------------------------------------------------
   1:          8769        8861376  [B
   2:          1858         229248  java.lang.Class
   3:          8680         208320  java.lang.String
   4:          1326         152624  [Ljava.lang.Object;
```

How to read it:

- `#instances`: number of instances of the class.
- `#bytes`: estimated total shallow size of those instances.
- `class name`: class name or array descriptor; `[B` is a byte array, `[I` is an int array.

A histogram does not show the retained size of the object graph. A class with a large total shallow size is not necessarily the root cause of a memory leak. To find which references are keeping objects alive, you need to analyze a heap dump using a tool such as Eclipse Memory Analyzer (MAT).

A live-only histogram may trigger a GC to determine which objects are still alive, pausing the application. Check the command's Impact level and avoid running it repeatedly during peak hours.

## 7. Generating a Class Histogram with jcmd

The corresponding command in `jcmd` is `GC.class_histogram`:

```bash
jcmd 18420 GC.class_histogram
```

In the tested JDK 24, the command has the following options:

- `-all`: includes unreachable objects; default is `false`.
- `-parallel`: number of parallel threads used to inspect the heap.

Example explicitly including unreachable objects:

```bash
jcmd 18420 GC.class_histogram -all
```

Reduce parallelism:

```bash
jcmd 18420 GC.class_histogram -parallel=1
```

On JDK 24, the command help lists **Impact: High**, depending on heap size and contents. Do not run histograms repeatedly on a large JVM without evaluating pause times and CPU usage.

### Default Differences to Remember

| Command | Default | How to request all objects |
| --- | --- | --- |
| `jmap -histo` | All objects | `jmap -histo:all` |
| `jmap -histo:live` | Live objects | No extra option needed |
| `jcmd GC.class_histogram` | Live/reachable objects only by command default | `jcmd PID GC.class_histogram -all` |

When comparing results between the two tools, you must select the same object scope. If one command counts all objects and the other counts only live objects, instance counts and byte totals can differ even on the same JVM.

## 8. Generating a Heap Dump with jmap

A heap dump is a snapshot of the object graph in the heap, typically in HPROF format. Using `jmap`:

```bash
jmap -dump:live,format=b,file=/var/tmp/heap-live.hprof 18420
```

Meaning:

- `-dump`: creates a heap dump.
- `live`: dumps only live objects.
- `format=b`: binary format.
- `file=...`: output file path.
- `18420`: JVM PID.

Dump all objects:

```bash
jmap -dump:all,format=b,file=/var/tmp/heap-all.hprof 18420
```

JDK 24 help also supports gzip compression:

```bash
jmap -dump:live,format=b,gz=1,file=/var/tmp/heap-live.hprof.gz 18420
```

Compression levels range from 1 to 9; 1 prioritizes speed, while 9 prioritizes higher compression.

The `live` and `all` options determine the object scope. According to the help text, `live` takes precedence if both are specified; if neither is specified, `jmap` defaults to dumping all objects.

Heap dumps can be very large, require heavy disk I/O, and cause noticeable pauses. Check available disk space, write permissions, and workload impact before running.

## 9. Generating a Heap Dump with jcmd

The corresponding command in `jcmd` is `GC.heap_dump`:

```bash
jcmd 18420 GC.heap_dump /var/tmp/heap-live-jcmd.hprof
```

In JDK 24, the command requests a full GC before dumping by default. You can specify `-all` to include unreachable objects and avoid that default full GC behavior:

```bash
jcmd 18420 GC.heap_dump -all /var/tmp/heap-all-jcmd.hprof
```

Gzip compression can be used:

```bash
jcmd 18420 GC.heap_dump -gz=1 /var/tmp/heap-live-jcmd.hprof.gz
```

Specific options depend on the JDK version; check with:

```bash
jcmd 18420 help GC.heap_dump
```

### Notes on File Paths

`jcmd` parses the command and arguments of a diagnostic command. Use simple paths without spaces to avoid unintentionally splitting them into multiple arguments:

Windows:

```powershell
New-Item -ItemType Directory -Force C:\\diagnostics | Out-Null
jcmd 18420 GC.heap_dump C:\\diagnostics\\heap-live.hprof
```

macOS/Linux:

```bash
mkdir -p /var/tmp/diagnostics
jcmd 18420 GC.heap_dump /var/tmp/diagnostics/heap-live.hprof
```

Do not write dumps into shared directories or directories with broad access permissions. HPROF files can contain tokens, sessions, user data, request payloads, and other sensitive objects.

## 10. Comparing Live Objects and All Objects

The two modes serve different purposes:

**Live objects** are objects that remain reachable according to GC rules at the time of inspection. This is usually the right scope when looking for objects actively retained by the application.

**All objects** include unreachable objects that have not yet been collected. This scope can be useful when studying the full heap state, though the numbers do not represent the memory actively kept alive by the application.

Examples:

```bash
jmap -histo:live 18420
jmap -histo:all 18420

jcmd 18420 GC.class_histogram
jcmd 18420 GC.class_histogram -all
```

When creating heap dumps:

```bash
jmap -dump:live,format=b,file=/var/tmp/live.hprof 18420
jmap -dump:all,format=b,file=/var/tmp/all.hprof 18420

jcmd 18420 GC.heap_dump /var/tmp/live-jcmd.hprof
jcmd 18420 GC.heap_dump -all /var/tmp/all-jcmd.hprof
```

If your goal is to find a memory leak, start with a live-object histogram and heap dump. Then use MAT to inspect the dominator tree, retained size, and GC roots.

## 11. Viewing Classloader Statistics

Classloader statistics are useful when investigating:

- Abnormal Metaspace growth.
- Applications creating many classloaders.
- Repeated redeployments where old classloaders are not released.
- Frameworks/plugins loading classes dynamically.
- Classloader leaks.

Using `jmap`:

```bash
jmap -clstats 18420
```

Using `jcmd`:

```bash
jcmd 18420 VM.classloader_stats
```

Output may include the classloader, parent, loaded class count, and Metaspace chunk/block statistics.

Abbreviated sample output:

```text
ClassLoader         Parent              CLD*               Classes   ChunkSz   BlockSz  Type
0x...               0x...               0x...               1185      4456448   1360928  <boot class loader>
0x...               0x...               0x...                  1         6144      2560  jdk.internal.loader.ClassLoaders$AppClassLoader
Total = 2
```

Formatting depends on the JDK. A large number of classes or high memory usage does not by itself prove a leak; compare across time and after deploy/undeploy cycles.

## 12. Additional jcmd Commands Beyond jmap's Scope

`jcmd` can do much more than heap inspection.

### Thread Dump

```bash
jcmd 18420 Thread.print -l
```

Prints thread stack traces along with lock information. Useful when investigating deadlocks or thread contention.

### JVM Flags and Command Line

```bash
jcmd 18420 VM.flags -all
jcmd 18420 VM.command_line
jcmd 18420 VM.system_properties
```

Used to inspect runtime configuration, startup arguments, and system properties. Output may contain paths, endpoints, or secrets if the application passes sensitive information via command-line arguments or system properties; sanitize before sharing.

### Java Flight Recorder

Start a recording:

```bash
jcmd 18420 JFR.start name=incident settings=default duration=60s filename=/var/tmp/incident.jfr
```

Check status:

```bash
jcmd 18420 JFR.check name=incident
```

Export a snapshot:

```bash
jcmd 18420 JFR.dump name=incident filename=/var/tmp/incident-snapshot.jfr
```

Stop a recording:

```bash
jcmd 18420 JFR.stop name=incident filename=/var/tmp/incident-final.jfr
```

`default` is designed for lower-overhead recordings; `profile` collects more data at higher overhead. Use `profile` only for short periods when deep analysis is required.

### Native Memory Tracking

If NMT was enabled at JVM startup:

```bash
jcmd 18420 VM.native_memory summary
```

You can set a baseline and compare:

```bash
jcmd 18420 VM.native_memory baseline
jcmd 18420 VM.native_memory summary.diff
```

NMT does not track Java heap statistics. It helps inspect native memory for Metaspace, threads, code cache, GC, and other subsystems. If the JVM did not enable NMT at startup, it cannot be fully enabled retroactively on a running process.

## 13. Analyzing Heap Dumps with Specialized Tools

A heap dump is raw data; you need an analysis tool to understand the object graph.

Commonly used tools:

- **Eclipse Memory Analyzer (MAT):** opens HPROF files, finds leak suspects, dominator trees, retained sizes, GC roots, and reference paths.
- **Java Mission Control (JMC):** analyzes JFR recordings and runtime data.
- **Other HPROF tools:** can inspect class histograms or object references depending on their supported features.

A typical MAT workflow:

1. Open the `.hprof` file.
2. Run the Leak Suspects Report for initial leads.
3. Check the Histogram to find classes with many instances or large shallow sizes.
4. Check the Dominator Tree to find objects retaining the most memory.
5. Inspect Path to GC Roots to see why an object remains reachable.
6. Cross-reference with source code, threads, caches, and application lifecycle.
7. Repeat the dump after making changes to verify the trend.

Do not conclude a memory leak solely from a class having a high instance count. A legitimate cache can also retain many objects; you must determine whether those objects should have been released.

## 14. Java 17 Hands-on Example: Creating a Heap with Retained Objects

The following example creates an application that retains several byte arrays in a static list so that histograms and heap dumps contain easily identifiable data.

Structure:

```text
project/
  src/
    com/example/diagnostics/
      HeapTarget.java
  out/
```

File **`src/com/example/diagnostics/HeapTarget.java`**:

```java
package com.example.diagnostics;

import java.util.ArrayList;
import java.util.List;

public final class HeapTarget {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    private HeapTarget() {
    }

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 8; i++) {
            RETAINED.add(new byte[1024 * 1024]);
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Retained arrays=" + RETAINED.size());

        Thread.sleep(120_000);
    }
}
```

Compile with Java 17:

```bash
javac --release 17 -d out src/com/example/diagnostics/HeapTarget.java
```

Run:

```bash
java -cp out com.example.diagnostics.HeapTarget
```

Sample output:

```text
PID=18420
Retained arrays=8
```

The PID changes on each run. The byte arrays are held in a static list, so they remain reachable while the program runs.

Open a second terminal and find the JVM:

```bash
jcmd -l
```

Assuming the PID is `18420`, inspect the heap:

```bash
jcmd 18420 GC.heap_info
```

View histograms with both tools:

```bash
jmap -histo:live 18420
jcmd 18420 GC.class_histogram
```

Create heap dumps:

```bash
jmap -dump:live,format=b,file=/var/tmp/heap-jmap.hprof 18420
jcmd 18420 GC.heap_dump /var/tmp/heap-jcmd.hprof
```

Open either HPROF file in MAT to locate the byte arrays and the reference path from the static field `RETAINED`.

Stop the program with Ctrl+C in the terminal running `HeapTarget`. This example is a small practice workload, not a benchmark, and does not represent a production application heap.

## 15. Impact Levels and Operational Safety

In JDK 24 tested on an experimental JVM:

| Command | Impact per JVM help |
| --- | --- |
| `GC.heap_info` | Medium |
| `GC.class_histogram` | High, depending on heap size and content |
| `GC.heap_dump` | High, depending on heap size and content |
| `VM.classloader_stats` | Low |
| `VM.native_memory` | Medium |
| `JFR.start` | Medium; depending on settings, can range from low to high |

Impact levels may vary across JDKs/vendors. Always run `jcmd <pid> help <command>` on the target JVM.

Safe practices:

- Start with `GC.heap_info` and lighter statistics before taking a dump.
- Avoid running histograms or heap dumps repeatedly without need.
- Plan for disk space and pause durations.
- Do not dump the heap onto a nearly full disk.
- Protect HPROF/JFR files because they may contain sensitive application data.
- Restrict read permissions and encrypt during storage/transfer according to policy.
- Record the PID, timestamp, JDK version, and commands executed.
- Do not use `jcmd 0` unless you intend to affect all discovered JVMs.
- Stop the JFR recording once sufficient data has been collected.

## 16. Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| JVM not visible | Wrong user, different container/PID namespace, or process stopped | Run `jcmd -l` in the right environment |
| `AttachNotSupportedException` or Access denied | Missing attach permissions or attach mechanism disabled | Check user, PID, JVM options, and policy |
| Unknown diagnostic command | Target JVM does not support the command or typo in name | Run `jcmd <pid> help` |
| Histogram is slow or pauses the app | Large heap, many objects, or High-impact command | Reduce frequency, choose an appropriate time window |
| Heap dump fails to write | Missing permissions, non-existent directory, or out of disk space | Check directory, permissions, and available disk space |
| JDK reports split file argument | `jcmd` path contains spaces and parser splits it into multiple arguments | Use a path without spaces, check quoting per JDK |
| HPROF is too large | Large heap or dumping all objects | Choose live-only when appropriate, compress, or increase disk space |
| Missing NMT summary | JVM did not enable Native Memory Tracking at startup | Enable `-XX:NativeMemoryTracking=summary` on the next restart |
| Histograms differ between jmap and jcmd | Commands used different live/all object scopes or heap changed | Compare with the same scope at close timestamps |
| Cannot find leak cause from histogram | Histogram only shows shallow size, not retention paths | Open the HPROF in MAT and inspect dominators/GC roots |

## 17. Tool Selection Workflow

Choose a command based on the question you need to answer:

| Question | Tool/command to start with |
| --- | --- |
| How much heap is currently used? | `jcmd PID GC.heap_info` |
| Which classes have the most instances? | `jcmd PID GC.class_histogram` |
| Need statistics using traditional jmap syntax? | `jmap -histo:live PID` |
| Need to find which objects are being retained? | `jcmd PID GC.heap_dump`, then analyze with MAT |
| Need classloader/Metaspace statistics? | `jcmd PID VM.classloader_stats` |
| Which threads are waiting on locks? | `jcmd PID Thread.print -l` |
| Need to record performance over time? | `jcmd PID JFR.start ...` |
| Native memory growing abnormally? | `jcmd PID VM.native_memory summary` if NMT is enabled |
| Need to inspect VM flags and startup configuration? | `jcmd PID VM.flags -all` and `VM.command_line` |

A memory diagnostic workflow typically starts with `jcmd -l`, followed by `GC.heap_info`, and then `GC.class_histogram`. Only take a heap dump when histograms and metrics indicate that deeper object graph analysis is needed.

## 18. Key Takeaways

- `jmap` primarily serves heap histograms, heap dumps, and classloader statistics.
- `jcmd` has a broader scope and is Oracle's recommended choice for modern JVM diagnostics.
- `jmap -histo:live` and `jcmd GC.class_histogram` can target live objects; check `-all` when you need unreachable objects as well.
- The default all/live behavior of the two tools differs; always compare using the same scope.
- `jmap -dump` and `jcmd GC.heap_dump` produce HPROF files for analysis in MAT.
- `jcmd GC.heap_dump` requests a full GC by default; the `-all` option changes that scope and behavior on the tested JDK.
- `jcmd` also supports JFR, thread dumps, VM flags, classloaders, and native memory diagnostics.
- Histograms show shallow size; heap dumps/MAT help analyze retained size and GC roots.
- Heap dumps and histograms can heavily impact the JVM; check Impact, disk space, and workload before running.
- Protect HPROF/JFR files as they may contain sensitive data.
- Check `jcmd <pid> help <command>` on the target JVM before running a command.

Understanding the strengths and limitations of `jmap` and `jcmd` helps you choose the right way to collect heap data, analyze object retention, and diagnose JVMs safely—especially when handling memory pressure or suspected memory leaks.

## References

- [The jmap Command — JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmap.html)
- [The jcmd Command — JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Java SE 24 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.html)
