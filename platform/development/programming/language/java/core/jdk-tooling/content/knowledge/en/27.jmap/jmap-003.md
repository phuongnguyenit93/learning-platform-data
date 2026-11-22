# Heap Dump in Java: Collecting and Analyzing the Java Heap

## Objectives

After this lesson, you will be able to explain what a heap dump is and what data it stores; distinguish a heap dump from a heap histogram, thread dump, and core dump; generate a heap dump from a running JVM using `jmap` and `jcmd`; understand the difference between dumping reachable objects only and dumping all objects; configure automatic heap dumps on `OutOfMemoryError`; analyze an HPROF file using Eclipse Memory Analyzer (MAT) or a compatible tool; find retained heap, dominators, and paths to GC roots; compare multiple snapshots to identify memory leaks; and collect diagnostic data safely in production environments.

## 1. What Is a Heap Dump?

A **heap dump** is a snapshot of the Java heap at a specific point in time. The Java heap is the memory area the JVM uses to allocate objects and arrays. A heap dump records objects, their associated classes, field values, and reference relationships needed to analyze the object graph structure.

A heap dump helps answer questions such as:

- Which classes have the most instances?
- Which objects consume the most heap memory?
- Which objects hold references that prevent a group of objects from being reclaimed by the garbage collector?
- Which collections, caches, listeners, or sessions are growing uncontrollably?
- Why does the heap remain full even after the application has finished processing requests?
- What reference path leads from a GC root to an object suspected of being retained?

Heap dumps are typically saved in the binary HPROF format. The file can be opened with Eclipse Memory Analyzer (MAT), JDK Mission Control, or any analysis tool that supports the corresponding HPROF variant.

Heap dumps are high-value diagnostic data, but they can be very large. They can also contain sensitive data held in application memory, such as access tokens, passwords, request payloads, customer information, or business data.

## 2. How Does a Heap Dump Differ from Other Dump Types?

| Data Type | Main Content | Typical Questions Answered |
|---|---|---|
| Heap dump | Objects, arrays, fields, and references in the Java heap | Which objects occupy or retain heap memory? |
| Heap histogram | Instance count and total bytes per class | Which classes are using the most heap? |
| Thread dump | Threads, states, and stack traces | Where are threads waiting or executing? |
| Core dump | OS-level snapshot of process memory | What state was the process/JVM in when it crashed? |
| JFR recording | Runtime events over time | How are allocation, GC, latency, and JVM activity behaving? |

A histogram is smaller and easier to collect than a heap dump, making it suitable for initial screening. A heap dump also preserves reference relationships, allowing analysis tools to identify which objects are retaining other objects.

A core dump contains broader process information, including native memory and OS-level state. A heap dump focuses on the Java heap and does not replace a core dump when investigating native crashes or JNI library errors.

## 3. When Should You Generate a Heap Dump?

### Investigating OutOfMemoryError

When the JVM reports `java.lang.OutOfMemoryError: Java heap space`, a heap dump can show which classes or object graphs are occupying the heap. You should combine it with exceptions, GC logs, metrics, and the incident timestamp to determine the root cause.

### Investigating Memory Leaks

A memory leak in Java typically occurs when objects are no longer needed by the business logic but remain reachable through references from a GC root. Examples include:

- Static collections retaining objects from old requests or sessions.
- Caches without size bounds or an eviction policy.
- Listeners that are registered but never unregistered.
- Thread-locals retaining objects after a task completes.
- Old ClassLoaders retained after a redeploy.
- Queues or maps growing continuously because consumers cannot keep up with producers.

### Checking the Heap After a Deployment or Load Change

You can capture snapshots at comparable stages to compare object counts, retained heap, and reference paths. Keep the load conditions and warm-up duration similar; otherwise, differences may simply reflect different workloads.

### Verifying Suspicions from a Histogram or JFR

A histogram shows which classes have many instances or consume many bytes. JFR can indicate allocation rates and growth periods. Once you identify a suspicious class or timeframe, a heap dump helps trace which objects are retaining those instances.

You do not need to generate a heap dump for every incident. If you only need a general view of heap usage, start with `jcmd PID GC.heap_info`; if you need a per-class breakdown, use `jcmd PID GC.class_histogram`.

## 4. HPROF and What a Heap Dump Contains

HPROF is a binary format used by Java tools to store profiling and heap information. An HPROF heap dump can contain:

- Class descriptions and related metadata.
- Object instances and arrays.
- Field values that can be recorded in the dump.
- Reference relationships between objects.
- Information about GC roots and the object graph needed for reachability analysis.
- Related thread/root information depending on JVM capabilities and dump format.

A heap dump is not a copy of the entire machine's RAM. It focuses on the Java heap and the metadata needed to analyze the object graph. Native allocations, C/C++ library memory, file mappings, and full CPU/register state are not represented as they are in a core dump.

### Reachable and Unreachable Objects

An object is **reachable** if there is a reference path to it from a GC root according to the JVM's reachability rules. GC roots can include thread stack/local references, static references, and other internal roots.

Unreachable objects can be reclaimed by the garbage collector. Therefore, two heap dumps generated in different ways can yield different results:

- Dumping only live objects after GC runs: excludes objects that are unreachable at capture time.
- Dumping all objects, including unreachable ones: retains more data for investigating certain special cases.

An unreachable object is not automatically a memory leak. Memory leaks usually involve objects that are no longer needed yet remain reachable, preventing GC from reclaiming them.

## 5. jmap and Support Status

`jmap` is a JDK command-line tool for printing memory information about a Java process. It provides options for capturing heap dumps, histograms, and class loader statistics.

Java SE 26 documentation classifies `jmap` as an experimental/unsupported tool. It may not be present in a future JDK release. Oracle recommends using `jcmd` instead of `jmap` for better diagnostic capabilities and lower performance overhead.

Therefore:

- Understand `jmap` so you can read older systems, operational scripts, and legacy documentation.
- Check `jmap -h` on the exact target JDK before using it, as options can differ across versions and vendors.
- For new workflows, prefer `jcmd PID GC.heap_dump`.
- For core dumps or postmortem analysis, refer to `jhsdb jmap` and the Serviceability Agent safety warnings.

Do not use a `jmap` binary from a different JDK to diagnose a target JVM without verifying compatibility. Oracle also warns that JDK serviceability tools are unsupported when a tool from one JDK version is used to diagnose a JVM of another version.

## 6. Finding the Target JVM's PID

`jmap` requires the PID of the Java process.

### Using jcmd

~~~bash
jcmd -l
~~~

Example:

~~~text
4128 com.example.OrderService
7852 org.apache.catalina.startup.Bootstrap
~~~

The PIDs in this example are illustrative only. Select the right process based on its main class and command line.

### Using jps or OS Tools

~~~bash
jps -l
~~~

On Linux:

~~~bash
ps -ef | grep '[j]ava'
~~~

On Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^java(w)?\.exe$' } |
    Select-Object ProcessId, Name, CommandLine
~~~

In Docker/containers, running `jps` or `jcmd -l` from the host may not list JVMs inside a separate PID namespace. Find the PID inside the target container or namespace, and run the tool in an environment that can attach to the target JVM.

`jcmd` must run on the same machine as the JVM with the same effective user ID/group ID that launched the JVM. Attach restrictions, container isolation, OS permissions, and `-XX:+DisableAttachMechanism` can also affect diagnostic access. Do not blindly grant broad privileges just to run a dump.

## 7. Creating a Heap Dump with jmap

The HPROF heap dump syntax documented by the JDK is:

~~~bash
jmap -dump:format=b,file=heap.hprof <PID>
~~~

Example creating a dump for process PID 4128:

~~~bash
jmap -dump:format=b,file=order-service.hprof 4128
~~~

Explanation:

- `-dump`: requests a Java heap dump.
- `format=b`: writes the dump in binary HPROF format.
- `file=order-service.hprof`: specifies the destination file path.
- `4128`: the PID of the JVM to capture.

The JDK 26 Troubleshooting Guide uses `jmap -dump:format=b,file=snapshot.jmap PID` to illustrate capturing a heap dump from a running process. The `.hprof` extension is commonly used for easy recognition; the filename itself does not change the binary format written.

### Dumping Only Live Objects

Some `jmap` versions support the `live` suboption:

~~~bash
jmap -dump:live,format=b,file=heap-live.hprof <PID>
~~~

`live` requests dumping only live objects. Syntax and options can vary by version; check `jmap -h` on your exact JDK before running.

Do not assume every `jmap` version has the same semantics as `jcmd GC.heap_dump`. In particular, `jmap`'s default behavior and `jcmd`'s `-all` option are not the same.

### Histogram for Screening Before Dumping

~~~bash
jmap -histo <PID>
~~~

Some versions support printing a histogram of live objects only:

~~~bash
jmap -histo:live <PID>
~~~

A histogram shows instance counts, total bytes, and class names. It does not contain full reference relationships for retained heap analysis like a heap dump does.

### Other Related Information

~~~bash
jmap -clstats <PID>
~~~

Prints class loader statistics for the heap. Useful when abnormal class loader or metaspace growth is suspected.

Depending on the version, `jmap -heap` may display heap configuration and usage. On newer JDKs, check the supported options and prefer the corresponding `jcmd` command.

## 8. Creating a Heap Dump with jcmd — The Recommended Approach

JDK 26 recommends using `jcmd` instead of `jmap` to generate heap dumps.

Syntax:

~~~bash
jcmd <PID> GC.heap_dump heap.hprof
~~~

Example:

~~~bash
jcmd 4128 GC.heap_dump order-service.hprof
~~~

`GC.heap_dump` creates an HPROF file. According to the JDK 26 documentation, this command has a high impact depending on heap size and contents. By default, the command requests a full GC unless the `-all` option is used.

### Dumping All Objects Including Unreachable Ones

~~~bash
jcmd <PID> GC.heap_dump -all heap-all-objects.hprof
~~~

`-all` requests dumping all objects, including unreachable ones. Because this option does not trigger the command's default full GC, the dump may include objects that a normal GC cycle would reclaim.

### Compressing the Dump File

~~~bash
jcmd <PID> GC.heap_dump -gz=1 heap.hprof.gz
~~~

`-gz` accepts a compression level from 1 to 9:

- `1`: fast compression, generally recommended.
- `9`: stronger compression, typically requiring more CPU and time.

Compression reduces file size, but it does not eliminate the overhead of traversing the heap and generating the dump.

### Allowing File Overwrite

~~~bash
jcmd <PID> GC.heap_dump -overwrite heap.hprof
~~~

Use `-overwrite` only after confirming the destination file may be replaced. By default, the command does not overwrite an existing file.

### Adjusting Parallel Dump Threads

~~~bash
jcmd <PID> GC.heap_dump -parallel=2 heap.hprof
~~~

`-parallel` requests the number of threads to use for the heap dump operation. The JVM may use fewer threads than requested. This option does not guarantee that dump time decreases linearly with the thread count.

### Viewing Target JVM Options

~~~bash
jcmd <PID> help GC.heap_dump
~~~

The target JVM's `help` command is the best source of truth for supported options, value types, and defaults on the running runtime.

### Comparing Object Selection Modes

| Command | Meaning |
|---|---|
| `jmap -dump:format=b,file=heap.hprof PID` | HPROF dump using `jmap` syntax; verify the defaults of your JDK version |
| `jmap -dump:live,format=b,file=heap-live.hprof PID` | On versions supporting `live`, dumps only live objects |
| `jcmd PID GC.heap_dump heap.hprof` | HPROF dump; requests a full GC by default |
| `jcmd PID GC.heap_dump -all heap-all.hprof` | Includes unreachable objects and does not request a full GC by default |

Do not port options from `jmap` to `jcmd` by simply swapping the tool name. The two commands have different syntax and object selection rules.

## 9. Choosing the Path, Disk Space, and File Format

A heap dump can be roughly the size of the objects currently stored in the heap, and the file can be larger than expected depending on contents, metadata, format, and dump options.

Before running:

1. Choose a filesystem with sufficient free space.
2. Choose a directory writable by the user running the JVM or diagnostic tool.
3. Verify quotas, container limits, and retention policies.
4. Avoid writing dumps to a nearly full filesystem or a volume holding critical operational data.
5. Include the PID and timestamp in the filename to avoid confusing multiple snapshots.
6. Secure the directory because heap dumps may contain sensitive data.

Example on Linux:

~~~bash
mkdir -p /var/tmp/java-dumps
jcmd <PID> GC.heap_dump /var/tmp/java-dumps/app-heap.hprof
~~~

Example on Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force C:\java-dumps
jcmd <PID> GC.heap_dump C:\java-dumps\app-heap.hprof
~~~

If a dump fails due to insufficient disk space, do not repeatedly retry on the same filesystem. Check partial files, available space, and logs before choosing a new location.

## 10. Automatically Generating a Heap Dump on OutOfMemoryError

You can configure the JVM to generate a heap dump automatically when Java heap exhaustion occurs:

~~~bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/tmp/java-dumps/heap-%p.hprof -jar service.jar
~~~

Where:

- `-XX:+HeapDumpOnOutOfMemoryError`: enables automatic heap dump creation when the JVM throws `OutOfMemoryError` due to Java heap exhaustion.
- `-XX:HeapDumpPath`: specifies the output directory and filename.
- `%p`: is replaced by the process PID.

If `HeapDumpPath` is not specified, the default file is typically named `java_pid<PID>.hprof` in the working directory.

Note: this option applies to `OutOfMemoryError` caused by Java heap exhaustion. It does not cover every `OutOfMemoryError` scenario, such as native thread creation failures or exceptions thrown directly by application code.

Prepare the dump directory before starting the application, ensuring the filesystem has enough space and write permissions. This startup option removes the need to wait for an operator to attach with `jmap`/`jcmd` when an incident occurs.

## 11. Analyzing a Heap Dump with Eclipse Memory Analyzer (MAT)

After generating the HPROF file, open it with Eclipse Memory Analyzer (MAT) or a compatible tool.

A typical analysis workflow includes:

1. Open the `.hprof` file in MAT.
2. Wait for the tool to parse indexes and compute data.
3. Review the Overview to understand dump size, object count, and initial statistics.
4. Run the Leak Suspects Report to identify suspicious object groups.
5. Open the Histogram to inspect instance counts and shallow heap by class.
6. Use the Dominator Tree to identify objects holding large amounts of retained heap.
7. Inspect Path to GC Roots to find the reference chain keeping objects alive.
8. Cross-reference findings with source code, cache policies, lifecycles, and application logs.

MAT may require additional RAM beyond the heap dump's file size to build indexes and run analysis. Open the dump on an analysis machine with sufficient memory rather than directly on a production server.

### Histogram

The Histogram groups objects by class, typically displaying class name, number of instances, shallow heap, and retained heap if computed. It answers which classes have many instances or consume significant memory, but it does not explain why those objects remain alive.

### Shallow Heap and Retained Heap

**Shallow heap** is the memory directly occupied by an object itself, excluding other objects it references.

**Retained heap** is the memory that would be freed if an object or group of objects were removed from the object graph, according to the tool's dominator analysis.

A small wrapper object can hold onto a massive graph. For example, a static map may occupy only a few megabytes of shallow heap while referencing millions of objects behind it; the retained heap of the map or its entries can be vastly larger.

### Dominator Tree

The Dominator Tree helps identify objects or groups of objects that control the reachability of other objects.

If object A dominates object B, every path from a GC root to B passes through A. Once A is no longer referenced, B becomes unreachable along with any objects retained exclusively through it.

A large dominator is a good starting point for investigation, but it does not automatically prove a leak. A large cache may be intentional by design; compare it against configured cache limits and business requirements.

### Path to GC Roots

Path to GC Roots shows the reference chain from a GC root to the object under analysis. For example:

~~~text
GC Root
  -> ApplicationClass.staticCache
      -> HashMap.table
          -> CacheEntry
              -> CustomerSession
                  -> LargePayload
~~~

This path suggests `staticCache` is retaining `CustomerSession` and `LargePayload`. Check whether the cache has eviction/expiration, whether sessions are removed on logout, and whether references are released after requests complete.

When inspecting paths, you can use the tool's options to exclude weak/soft/phantom references so you can focus on strong retention paths. Always verify the GC root type and reference type before drawing conclusions.

## 12. Reading Histograms and Comparing Multiple Snapshots

An example histogram:

~~~text
 num      #instances       #bytes       class name
---------------------------------------------------
   1:         50000      8000000       com.example.Session
   2:         25000      4000000       byte[]
   3:         10000      1200000       java.lang.String
   4:          8000       640000       java.util.HashMap$Node
---------------------------------------------------
 Total:       93000     13840000
~~~

The numbers above illustrate the format only and do not represent a real application.

If `com.example.Session` grows continuously across snapshots, that is a signal to investigate. Verify:

- Does the instance count grow over time, or only when load increases?
- Does heap usage drop after the workload ends and GC has had a chance to run?
- Are instances held by a cache, static field, listener, or thread-local?
- Does retained heap grow along with instance count, or is it just a change in the object graph?
- Were the snapshots captured after similar warm-up times and comparable workloads?

A single snapshot is rarely enough to prove a memory leak. Comparing at least two or three points in time under comparable load helps reveal the trend.

## 13. Hands-On Example: Creating a Heap Dump for a Sample JVM

This example allocates 16 byte arrays of 1 MiB each and stores them in a static list so they remain reachable during heap dump collection.

Create `HeapDumpTarget.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class HeapDumpTarget {
    private static final List<byte[]> retained = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 16; i++) {
            retained.add(new byte[1024 * 1024]);
        }

        System.out.println("heap-dump-target-ready");
        System.out.println("retainedMiB=" + retained.size());

        while (true) {
            Thread.sleep(60_000);
        }
    }
}
~~~

### Compile

Using JDK 17 or later:

~~~bash
javac --release 17 HeapDumpTarget.java
~~~

### Launch the Target JVM

Terminal A:

~~~bash
java HeapDumpTarget
~~~

Exact output:

~~~text
heap-dump-target-ready
retainedMiB=16
~~~

Keep the process running so you can attach from another terminal.

### Find the PID

Terminal B:

~~~bash
jcmd -l
~~~

Locate the `HeapDumpTarget` process and note its PID.

### Create a Heap Dump with jcmd

~~~bash
jcmd <PID> GC.heap_dump heap-dump-target.hprof
~~~

By default, the command requests a full GC before dumping, so unreachable objects may be reclaimed before the snapshot is written.

If you want to include unreachable objects as well:

~~~bash
jcmd <PID> GC.heap_dump -all heap-dump-target-all.hprof
~~~

### Create a Heap Dump with jmap

On a JDK that supports the corresponding `jmap` syntax:

~~~bash
jmap -dump:format=b,file=heap-dump-target-jmap.hprof <PID>
~~~

If your version supports `live` and you want only live objects:

~~~bash
jmap -dump:live,format=b,file=heap-dump-target-live.hprof <PID>
~~~

### Verify the Files

Linux:

~~~bash
ls -lh heap-dump-target*.hprof
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem heap-dump-target*.hprof |
    Select-Object Name, Length, LastWriteTime
~~~

Open one of the HPROF files in MAT to inspect the `HeapDumpTarget` class and the `byte[]` arrays retained in the static list.

### Stop the Sample JVM

Return to Terminal A and press `Ctrl+C`. There is no need to trigger an `OutOfMemoryError` in this exercise.

## 14. Creating a Heap Dump from a Core File with jhsdb

If the JVM has crashed and the OS has generated a core dump, you can use the Serviceability Agent via `jhsdb jmap` for postmortem analysis.

Example extracting a histogram from a core file:

~~~bash
jhsdb jmap --histo --exe /path/to/java --core core-file
~~~

Creating an HPROF heap dump from a core file:

~~~bash
jhsdb jmap --binaryheap --dumpfile heap-from-core.hprof --exe /path/to/java --core core-file
~~~

Printing a heap summary:

~~~bash
jhsdb jmap --heap --exe /path/to/java --core core-file
~~~

Where:

- `--exe`: path to the Java executable corresponding to the core file.
- `--core`: path to the core dump.
- `--histo`: prints the histogram.
- `--binaryheap`: writes the heap as a binary HPROF file.
- `--dumpfile`: output dump filename.
- `--heap`: prints the heap summary.

If the VM was created via the JNI Invocation API, the executable binary may not be named `java`; provide the exact executable that produced the core file.

**Warning:** `jhsdb` is an experimental/unsupported tool. Attaching `jhsdb` to a live process suspends the process and may cause it to crash when the debugger detaches. Prefer analyzing existing core files; do not attach `jhsdb` to live processes as a routine way to capture heap dumps in production.

If `jmap PID` is unresponsive because the process is hung, Oracle recommends using `jhsdb jmap` to run the Serviceability Agent. Assess the impact and collect a core file according to operational procedures before using postmortem tools.

## 15. Combining Heap Dumps with Other Diagnostic Tools

Heap dumps are most effective when combined with other data sources:

| Data | Role |
|---|---|
| GC log (`-Xlog:gc*`) | Shows heap growth/reclamation and GC timing |
| `jcmd GC.heap_info` | Snapshot of overall heap usage |
| `jcmd GC.class_histogram` | Screens classes occupying the most heap |
| JFR | Allocation rate, GC pauses, threads, and events over time |
| Thread dump | Thread states, locks, and stack traces |
| NMT | HotSpot internal memory if enabled at startup |
| Heap dump | Object graph and retaining references |

Example workflow:

1. Metrics alert on continuously rising heap occupancy.
2. Check GC logs to confirm old-generation occupancy does not drop after GC cycles.
3. Capture a histogram to find classes with growing instance counts.
4. Collect JFR data to identify allocation sites and when objects are created.
5. Take a heap dump to inspect the object graph, dominators, and paths to GC roots.
6. Cross-reference source code and fix the lifecycle, cache, or reference issue.
7. Capture a follow-up snapshot after the fix to confirm retained heap stabilizes.

Heap dumps focus on the Java heap. If process RSS grows while the Java heap remains stable, investigate direct buffers, native libraries, thread stacks, memory mappings, and native allocations using NMT or OS tools.

## 16. Application Impact and Production Safety

Generating a heap dump can significantly impact a running JVM.

Key risks:

- The JVM may pause while traversing and writing the heap.
- Default dumps via `jcmd` trigger a full GC, which can increase latency.
- Dump duration depends on heap size, object count, collector, I/O, and disk speed.
- Dump files can consume substantial disk space.
- Heap dumps can contain secrets, personal data, request bodies, and business content.
- Writing a dump to a full filesystem can disrupt the service or produce an incomplete artifact.

Production procedure:

1. Verify the PID and target JVM.
2. Confirm that a heap dump is needed rather than just a histogram or JFR.
3. Check disk space, quotas, and write permissions.
4. Choose a dedicated volume with sufficient capacity.
5. Evaluate collection timing and system load.
6. Protect the file with restricted access permissions and encryption at rest per policy.
7. Record the PID, JDK version, timestamp, command, and reason for collection.
8. Verify the file has a reasonable size and opens cleanly in an analysis tool.
9. Share the file only through approved channels.
10. Delete or archive the file according to the retention policy.

Never upload a heap dump to a public service or attach it to an unprotected ticket. Before sharing with a third party, evaluate sensitive data exposure and your organization's security policies.

## 17. Common Errors and Troubleshooting

### Unable to Attach to the JVM

**Symptom:** `jmap` or `jcmd` reports attach failed, permission denied, or process not found.

**Cause:** Wrong PID, JVM has exited, mismatched user/group, wrong PID namespace/container, or attach mechanism disabled.

**Resolution:** Verify the PID in the correct environment; run the tool with the matching effective user/group; check for `-XX:+DisableAttachMechanism` in startup flags; confirm the tool is compatible with the target JDK.

### jmap Missing or Option Unsupported

**Symptom:** Command not found or invalid option error.

**Cause:** The JDK distribution does not include `jmap`, the experimental tool was removed, or syntax differs by version.

**Resolution:** Prefer `jcmd <PID> GC.heap_dump`; run `jcmd <PID> help GC.heap_dump` to confirm options; never download `jmap` binaries from untrusted sources.

### Insufficient Disk Space

**Symptom:** Dump fails midway, produces an unusually small file, or cannot complete.

**Cause:** Full filesystem, container quota, or underestimated required space.

**Resolution:** Check available space and remove partial files; select a volume with adequate capacity; consider `-gz=1` with `jcmd`; do not retry dumps repeatedly on a full filesystem.

### Dump File Already Exists

**Symptom:** `jcmd` refuses to write to the destination file.

**Cause:** A file with the same name already exists and `-overwrite` was not specified.

**Resolution:** Choose a new filename or use `-overwrite` after confirming the existing file can be replaced.

### Heap Dump Takes Too Long

**Symptom:** Application pauses or latency spikes severely during the dump.

**Cause:** Large heap, high object count, full GC, slow disk, or throttled I/O.

**Resolution:** Evaluate collection timing, run a histogram first, check disk throughput, and consider compression; do not run repeated dumps back-to-back without checking the status of the previous attempt.

### MAT Cannot Open the File

**Symptom:** Tool reports a corrupt file, unrecognized HPROF, or runs out of memory during indexing.

**Cause:** Incomplete dump, truncated file, incompatible format variant, or insufficient RAM/disk on the analysis machine.

**Resolution:** Verify the command completed and check the file size; re-capture the dump onto a volume with enough space; use a compatible MAT version and increase MAT's own heap size if needed.

### Histogram Shows a Large Class Without Clear Cause

**Symptom:** A class has many instances, but it is unclear which objects are retaining them.

**Cause:** Histograms do not contain full reference paths for retained heap analysis.

**Resolution:** Generate a heap dump and use the Dominator Tree and Path to GC Roots to find the reference chain.

### Heap Dump Shows Many Objects Without Proving a Leak

**Symptom:** Snapshot shows many objects, but the application operates normally.

**Cause:** Data reflects normal workload, a valid cache, or a snapshot taken before GC ran.

**Resolution:** Compare multiple snapshots under equivalent load; cross-check GC logs, JFR, and cache policies; verify object reachability and retained heap before concluding there is a leak.

### Process Hung, jmap Unresponsive

**Symptom:** `jmap PID` returns no output.

**Cause:** The JVM is in a hung state or the attach request cannot complete.

**Resolution:** Gather incident data; if a core file is available, use `jhsdb jmap` for postmortem analysis. Do not attach `jhsdb` to a live process unless you accept the risk of hanging the process and crashing it upon debugger detach.

### Automatic Heap Dump Not Created on OOME

**Symptom:** Application reports `OutOfMemoryError` but no HPROF file is produced.

**Cause:** `-XX:+HeapDumpOnOutOfMemoryError` is not enabled, `HeapDumpPath` is invalid, write permissions are missing, disk is full, or the error is not Java heap exhaustion.

**Resolution:** Check startup flags, `HeapDumpPath`, permissions, and disk space; confirm the `OutOfMemoryError` type; test the mechanism in a staging environment.

## 18. Pre- and Post-Heap Dump Checklist

### Before Dumping

- [ ] Identify the exact JVM PID and JDK version.
- [ ] Choose `jcmd` for new workflows; use `jmap` only when compatibility requires it.
- [ ] Decide whether you need live objects only or unreachable objects as well.
- [ ] Run `jcmd <PID> help GC.heap_dump` to check options supported by the target.
- [ ] Verify disk space, quotas, and write permissions.
- [ ] Choose a unique path and filename.
- [ ] Assess application impact and collection timing.
- [ ] Confirm sensitive data protection policies.

### After Dumping

- [ ] Confirm the command completed successfully.
- [ ] Verify the file exists and has a reasonable size.
- [ ] Check that the file opens in MAT or a compatible tool.
- [ ] Record the JDK version, PID, timestamp, and command used.
- [ ] Analyze Histogram, Dominator Tree, and Path to GC Roots.
- [ ] Cross-reference with GC logs, JFR, and metrics.
- [ ] Avoid concluding a leak from a single snapshot.
- [ ] Secure and store the file according to retention policy.
- [ ] Delete temporary files once analysis is complete and deletion is authorized.

## 19. Official References

- [The jmap Command — Java SE 26 Tool Specifications](https://docs.oracle.com/en/java/javase/26/docs/specs/man/index.html) — JDK tool directory and `jmap` documentation location in the release.
- [Java SE 26 Troubleshooting Guide — The jmap Utility](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-guide.pdf) — `jmap` status, heap dumps, histograms, class loader statistics, and recommendation to use `jcmd`.
- [The jcmd Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — `GC.heap_dump`, `-all`, `-gz`, `-overwrite`, `-parallel`, and impact levels.
- [The jhsdb Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jhsdb.html) — `jhsdb jmap`, heap dumps from core files, and warnings on attaching to live processes.
- [Troubleshoot Memory Leaks — Java SE 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html) — histograms, heap dumps, JFR, and memory leak investigation workflow.
- [Eclipse Memory Analyzer (MAT)](https://eclipse.dev/mat/) — HPROF analysis tool, histograms, dominator trees, and retained heap.

A heap dump provides a point-in-time object graph to identify which objects occupy or retain Java heap memory. Prefer `jcmd`, choose the appropriate dump mode, prepare sufficient disk space, analyze retained heap and GC roots, and compare multiple snapshots before concluding a memory leak.
