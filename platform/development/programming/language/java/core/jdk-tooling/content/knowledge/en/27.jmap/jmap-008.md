# The jmap Command: Syntax and Practice

**jmap** is a JDK command-line utility used to collect heap data from a running Java HotSpot VM. Common operations include printing a heap histogram, exporting an HPROF heap dump, viewing class loader statistics, and listing objects awaiting finalization.

This guide explains how to select the right JVM process, read the command syntax, choose between a histogram and a heap dump, save results to a file, analyze the data, and troubleshoot common errors. A small Java lab later in the guide lets you practice with a process you launch yourself.

In Oracle JDK 24, jmap is classified as **experimental and unsupported**. Oracle recommends using **jcmd** for modern diagnostics because it offers more diagnostic commands and reduces overhead compared to older utilities. Understand jmap to read runbooks and handle existing systems, while preferring jcmd for new workflows.

## 1. Installing and Verifying jmap

jmap comes bundled with the JDK. If a machine only has a minimal runtime image installed, the command might not exist.

Check Java:

~~~bash
java --version
~~~

Check jmap:

~~~bash
jmap --help
~~~

On OpenJDK 24.0.2, help lists the following commands:

- **-histo[:options]**: object statistics by class.
- **-dump:options**: write the heap to a file.
- **-clstats**: class loader statistics.
- **-finalizerinfo**: view objects awaiting finalization.
- **-?**, **-h**, **--help**: print help.

Do not assume every JDK shares the exact same syntax. Older options may no longer exist in newer releases; for example, the OpenJDK 24.0.2 help does not list **-heap**. Check the help output of the exact JDK running your application before putting commands into scripts.

### jmap Is a One-Shot Diagnostic Tool

jmap is not a continuous heap monitoring dashboard. Each invocation captures a point-in-time snapshot or statistics. If you need to track heap trends, GC pauses, and allocations over time, use JFR, JDK Mission Control, JMX, or an organization-approved metrics system.

## 2. General Syntax

Command syntax in JDK 24:

~~~bash
jmap -clstats <pid>
jmap -finalizerinfo <pid>
jmap -histo[:<histo-options>] <pid>
jmap -dump:<dump-options> <pid>
~~~

`<pid>` is the process identifier of the target JVM. Angle brackets in syntax descriptions only indicate placeholders to be replaced with actual values; do not type them when running the command.

Example:

~~~bash
jmap -histo 31840
~~~

31840 is only an illustrative PID. Do not use example PIDs on a real machine. Find and verify the target process's PID before running.

### Distinguishing the Two Option Groups

- Histogram options start with **-histo:** and can include **live**, **all**, **file**, or **parallel**.
- Heap dump options start with **-dump:** and can include **live**, **all**, **format=b**, **file**, or **gz**.

Options are joined with commas. Do not put spaces between options within the same group.

## 3. Finding and Verifying the PID

On a local machine, you can use jps to find JVMs:

~~~bash
jps -l
~~~

Sample output:

~~~text
31840 com.example.HeapLab
32004 com.example.ApiServer
~~~

Then verify the process using OS tools.

Linux/macOS:

~~~bash
ps -p 31840 -o pid,ppid,user,etime,args
~~~

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process -Filter "ProcessId = 31840" |
    Select-Object ProcessId, ParentProcessId, Name, CommandLine
~~~

Notes:

- jps only lists instrumented HotSpot JVMs observable under the current permissions.
- The LVMID printed by jps is usually the OS PID, though it is not guaranteed to always match.
- PIDs can be reused after a process terminates.
- Containers may use a PID namespace, so the PID inside a container differs from the PID seen from the host.
- jmap requires appropriate attach permissions for the target process; typically, the tool runs on the same machine under an account with permission to access the JVM.

Before performing an impactful operation, confirm the process name, user, command line, and start time. Never reuse an old PID from a runbook without re-verifying it.

## 4. Heap Histogram with -histo

A heap histogram reports the number of objects and total shallow bytes per class. This is usually the first step to see which classes occupy the most objects or memory.

Run a histogram:

~~~bash
jmap -histo <pid>
~~~

Example:

~~~bash
jmap -histo 31840
~~~

The output has a structure similar to:

~~~text
 num     #instances         #bytes  class name
------------------------------------------------
   1:         12000         960000  com.example.Session
   2:          8000         512000  byte[]
   3:          6000         192000  java.lang.String
Total        26000        1664000
~~~

The numbers above only illustrate the structure, not measurements from an actual JVM.

Columns:

- **num**: rank of the class in the report.
- **#instances**: number of objects belonging to the class.
- **#bytes**: total shallow size of instances of the class.
- **class name**: class name; arrays may appear as `byte[]` or `java.lang.Object[]`.

### Shallow Size Is Not Retained Size

Shallow size is the memory directly occupied by an object itself. It does not include all other objects referenced by that object.

For example, a HashMap may occupy only a small amount of shallow bytes while holding references to millions of objects. A histogram alone does not tell you how much retained heap that map holds or which objects are keeping references alive.

To find why objects remain alive, you need a heap dump and tools that analyze the reference graph, dominator tree, or paths to GC roots.

## 5. Choosing live or all When Running a Histogram

### Counting Only Live Objects

~~~bash
jmap -histo:live <pid>
~~~

`live` requests statistics for live objects determined by the JVM's reachability analysis. This operation can trigger garbage collection and cause a pause; the impact depends on heap size, GC, and application state.

Use `live` when you want to reduce noise from objects that have already become garbage but have not yet been collected.

### Counting All Objects

~~~bash
jmap -histo:all <pid>
~~~

`all` includes unreachable objects as well. In OpenJDK 24.0.2, help indicates that `all` is the default if neither `live` nor `all` is specified. If both appear, `live` takes precedence.

Use `all` when you need to see objects not yet collected at the time of the snapshot. Do not compare an `all` histogram with a `live` histogram as if they were the same kind of metric.

### Writing a Histogram to a File

~~~bash
jmap -histo:live,file=histogram-live.txt <pid>
~~~

Example with all objects and a single inspection thread:

~~~bash
jmap -histo:all,parallel=1,file=histogram-all.txt <pid>
~~~

`parallel` controls the number of threads used to inspect the heap:

- **parallel=0**: let the JVM decide the number of threads.
- **parallel=1**: use one thread, disabling parallelism.
- Higher values: the JVM attempts to use that many threads, though it may use fewer.

Histograms can be very long. Check the output directory, disk space, and permissions before running.

## 6. Heap Dump with -dump

A heap dump is a snapshot of objects and reference relationships in the Java heap, written in HPROF binary format.

Syntax:

~~~bash
jmap -dump:<dump-options> <pid>
~~~

Example dumping the entire heap:

~~~bash
jmap -dump:format=b,file=heap.hprof <pid>
~~~

Options:

| Option | Meaning |
|---|---|
| live | Dump only live objects |
| all | Dump all objects, including unreachable objects |
| format=b | HPROF binary format |
| file=<path> | Destination file |
| gz=<1..9> | Write a gzip-compressed file with compression level 1 to 9 |

### Dumping Live Objects

~~~bash
jmap -dump:live,format=b,file=heap-live.hprof <pid>
~~~

Choose this command when you want to analyze live objects and the reference paths keeping them alive. Determining live objects may require garbage collection and pause the JVM.

### Dumping All Objects

~~~bash
jmap -dump:all,format=b,file=heap-all.hprof <pid>
~~~

This command retains unreachable objects as well. The data can be useful when investigating a broader heap state, though the file often contains many objects that GC could collect.

In JDK 24 help, if neither `live` nor `all` is specified, the default is `all`; if both are specified, `live` takes precedence.

### Compressing a Heap Dump

~~~bash
jmap -dump:live,format=b,gz=1,file=heap-live.hprof.gz <pid>
~~~

Compression levels:

- **gz=1**: prioritizes compression speed.
- **gz=9**: stronger compression, typically consuming more CPU and time.
- Only use values from 1 to 9.

Compression reduces storage space but does not eliminate the cost of reading the heap and writing the file. Choose a compression level based on application load and volume capacity.

### Using Absolute Paths

Linux/macOS:

~~~bash
jmap -dump:live,format=b,file=/var/secure-diagnostics/heap-live.hprof <pid>
~~~

Windows PowerShell:

~~~powershell
jmap -dump:live,format=b,file=C:\secure-diagnostics\heap-live.hprof <pid>
~~~

The directory must exist and the user running jmap must have write permission. Avoid writing to a web root, public directory, upload directory, or volume with broad access permissions.

## 7. Lab: Creating a JVM with Objects to Observe

This lab creates a program that retains several byte arrays in a static list. The arrays remain referenced for as long as the program waits, so they can be found in both the live histogram and the heap dump.

Create `HeapLab.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class HeapLab {
    private static final List<byte[]> retained = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        int count = args.length == 0 ? 32 : Integer.parseInt(args[0]);

        for (int i = 0; i < count; i++) {
            retained.add(new byte[1024 * 1024]);
        }

        System.out.println("READY retained=" + retained.size());
        Thread.sleep(10 * 60 * 1000L);
    }
}
~~~

Compile with Java 17 or later:

~~~bash
javac --release 17 HeapLab.java
~~~

Open a first terminal and run:

~~~bash
java -Xms64m -Xmx256m HeapLab 32
~~~

Exact stdout:

~~~text
READY retained=32
~~~

The program retains 32 arrays, each with a 1 MiB payload, and waits for up to 10 minutes. Actual shallow bytes include object header/alignment overhead and may vary slightly across JVMs.

Open a second terminal and find the PID:

~~~bash
jps -l
~~~

Find the `HeapLab` line, then verify the PID using `ps` or PowerShell as shown earlier.

Run a live histogram:

~~~bash
jmap -histo:live <pid>
~~~

Look for the `byte[]` line. The instance count may be greater than 32 because the JVM and program also allocate other arrays.

Create a live heap dump:

~~~bash
jmap -dump:live,format=b,file=heaplab-live.hprof <pid>
~~~

Open `heaplab-live.hprof` with Eclipse Memory Analyzer (MAT) or an HPROF-compatible tool. Locate `HeapLab.retained` and the `byte[]` instances to inspect the reference path.

When finished, return to the first terminal and press Ctrl+C to terminate the program. Do not use the lab's PID for any other service.

## 8. Class Loader Statistics with -clstats

Class loaders are responsible for loading classes. Applications with plugins, application servers, hot reload, or repeated redeployments may have many class loaders.

Run:

~~~bash
jmap -clstats <pid>
~~~

Class loader statistics help investigate:

- The number of classes loaded by each loader.
- Parent loader relationships.
- Which loaders are still present in the heap.
- Signs of old loaders not being freed after redeployment.

A lingering old class loader may be held by a ThreadLocal, thread, static field, listener, or cache reference. `jmap -clstats` does not show the full reference path causing the issue; use a heap dump and GC roots analysis to find what is holding the loader.

The recommended equivalent command in jcmd:

~~~bash
jcmd <pid> VM.classloader_stats
~~~

In JDK 24, `VM.classloader_stats` is a low-impact diagnostic command according to the jcmd documentation.

## 9. Information on Objects Awaiting Finalization

Run:

~~~bash
jmap -finalizerinfo <pid>
~~~

This command displays information about objects awaiting finalization. It is useful when investigating legacy code that still uses `finalize()`.

Finalization is not a reliable resource management mechanism. Do not rely on `finalize` to close files, sockets, database connections, or critical resources. Use try-with-resources, `AutoCloseable`, or explicit lifecycle APIs instead.

The equivalent command in jcmd:

~~~bash
jcmd <pid> GC.finalizer_info
~~~

According to JDK 24 jcmd documentation, `GC.finalizer_info` has Medium impact. Always check the target JVM's help because the available diagnostic commands depend on the runtime.

## 10. jcmd Is the Preferred Choice for New Diagnostics

Oracle recommends using jcmd instead of jmap. jcmd provides diagnostic commands with documented impact levels and supports a wider range of JVM information.

List processes:

~~~bash
jcmd -l
~~~

View commands supported by a JVM:

~~~bash
jcmd <pid> help
~~~

View help for heap dump:

~~~bash
jcmd <pid> help GC.heap_dump
~~~

View help for histogram:

~~~bash
jcmd <pid> help GC.class_histogram
~~~

### Histogram with jcmd

~~~bash
jcmd <pid> GC.class_histogram
~~~

Include unreachable objects:

~~~bash
jcmd <pid> GC.class_histogram -all
~~~

### Heap Dump with jcmd

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

Include unreachable objects:

~~~bash
jcmd <pid> GC.heap_dump -all heap-all.hprof
~~~

Compress the dump using the syntax supported by JDK 24 jcmd:

~~~bash
jcmd <pid> GC.heap_dump -gz=1 heap.hprof.gz
~~~

You can specify `-overwrite` if you need to overwrite an existing file; do not use this option without verifying the old file is no longer needed.

According to Oracle JDK 24 documentation, `GC.heap_dump` has High impact and requires a full GC unless `-all` is used. `GC.class_histogram` also has High impact. Check the impact in `help` before running in production.

### Comparing jmap and jcmd

| Goal | jmap | jcmd |
|---|---|---|
| Heap histogram | -histo[:options] | GC.class_histogram |
| Heap dump | -dump:options | GC.heap_dump |
| Class loader statistics | -clstats | VM.classloader_stats |
| Finalization queue | -finalizerinfo | GC.finalizer_info |
| Heap summary | Depends on jmap version | GC.heap_info |

Command names and options may vary between JVMs. Do not assume every JVM supports the same set of diagnostic commands.

## 11. Analyzing Core Dumps with jhsdb jmap

When a JVM crashes and produces a core dump, you can use the Serviceability Agent for offline analysis.

View syntax:

~~~bash
jhsdb jmap --help
~~~

Generate a histogram from a core dump:

~~~bash
jhsdb jmap --histo --core core.1234 --exe /path/to/java
~~~

View heap summary:

~~~bash
jhsdb jmap --heap --core core.1234 --exe /path/to/java
~~~

Export HPROF from a core dump:

~~~bash
jhsdb jmap --binaryheap --dumpfile heap-from-core.hprof --core core.1234 --exe /path/to/java
~~~

`--core` and `--exe` must be provided together. The executable must match the JVM that produced the core dump. The `--pid` option targets a live process, but Oracle warns that attaching jhsdb to a running process can hang the process and may crash it when the debugger detaches. Do not use live attach in production just for experimentation.

JDK documentation also notes that remote `--connect` for jhsdb/debugd is deprecated. Prefer offline core dump analysis or supported diagnostic workflows.

## 12. Reading Heap Dumps with Analysis Tools

jmap creates an HPROF file, but does not analyze the root cause of a memory leak on its own. Use Eclipse Memory Analyzer (MAT), JDK Mission Control, or an HPROF-compatible tool to inspect the object graph.

Common steps:

1. Open the HPROF file.
2. View the histogram by class.
3. Open the dominator tree to find objects holding large retained heap.
4. Use paths to GC roots to find why objects remain reachable.
5. Check static fields, collections, caches, ThreadLocals, listeners, and threads.
6. Compare multiple snapshots if you need to identify trends.
7. Cross-reference reference paths with source code and business lifecycle.

### Shallow Size and Retained Size

- **Shallow size:** the direct size of the object itself.
- **Retained size:** the amount of heap that can be freed if that object and everything kept alive solely by it become unreachable.
- Histograms help find classes with many instances or high shallow bytes.
- Dominator trees and reference graphs help find objects holding retained heap.

A class having many instances does not automatically indicate a memory leak. It could be a bounded cache, pool, or queue. Correlate findings with application load, configuration limits, and trends over time.

## 13. Impact and Safety When Running in Production

Heap inspection can be resource-intensive. Before running:

- Verify the PID and the right service.
- Estimate heap size and volume capacity.
- Choose `live`/`all` based on the question you need to answer.
- Check the impact of the diagnostic command.
- Choose a low-traffic period or maintenance window if appropriate.
- Prepare an output directory with minimal access permissions.
- Monitor latency, health checks, CPU, and disk I/O.
- Do not run repeatedly in a loop without evaluating overhead.

### Heap Dumps Are Sensitive Data

Heap dumps can contain passwords, tokens, session cookies, database credentials, request payloads, personal data, or private material held in application memory.

Therefore:

- Store dumps in an encrypted volume or protected area per policy.
- Restrict who has read access to the file.
- Do not send via email/chat or public file-sharing services.
- Do not commit to Git or include in build artifacts.
- Redact reports before sharing.
- Record who collected it, when, host, PID, JDK, and reason.
- Apply retention policies and securely delete after the investigation is complete.

Histograms are generally less sensitive than heap dumps, but can still reveal class names, packages, and internal structure. Access control should still be enforced.

## 14. Common Errors and Troubleshooting

### Attach Failed or Not Enough Permissions

Check the process owner, attach permissions, OS policy, and correct PID. Typically, the tool needs to run on the same host under a user/group with appropriate permissions. Do not automatically escalate privileges to bypass security controls.

### Process Does Not Exist

The PID may be wrong, the process may have terminated, or the PID may have been reused. Re-check with jps, verify with OS tools, and run the command on the right host/container.

### Unable to Write Heap Dump File

Check:

- Whether the path is valid.
- Whether the directory already exists.
- Whether the user running the command has write permission.
- Whether the volume has enough free space.
- Whether the target file already exists or is locked.
- Whether a filesystem/container protection policy blocks writing.

Prefer absolute paths and do not overwrite existing files without checking first.

### JVM Pause Too Long

A large heap, many objects, live-object traversal, or a full GC can prolong the operation. Monitor service health, stop further diagnostic actions, and follow the incident runbook. Next time, consider a histogram or JFR before a heap dump if you do not yet need the full object graph.

### Histograms Differ Between Runs

Check whether both runs used the same `live`/`all` setting, capture timing, application load, and GC state. Compare snapshots under equivalent conditions before concluding there is a leak.

### Heap Dump Cannot Be Opened

Check whether the file is complete or truncated due to running out of disk space, whether the HPROF version is supported by the analysis tool, and whether the file was corrupted during transfer. Compute a checksum before and after transferring the file to confirm bytes are unchanged.

### jmap Is Missing on the JDK

Some minimal runtime images do not package jmap. Use a full JDK matching the target runtime or use jcmd if available. For new workflows, prefer jcmd per Oracle's recommendation.

## 15. Recommended Memory Diagnostic Workflow

1. Identify the service, host/container, and current PID.
2. Verify user, command line, JDK vendor/version, and heap flags.
3. Start with metrics, GC logs, or JFR to understand trends.
4. If a quick snapshot is needed, run a histogram and choose `live`/`all` to match your goal.
5. Compare histograms over time under comparable conditions.
6. If you need to trace reference paths, capture a heap dump at an appropriate time.
7. Analyze the HPROF file with MAT or a compatible tool.
8. Find dominators, retained heap, and GC roots.
9. Cross-reference with source code, cache policies, listeners, and lifecycle.
10. Fix the root cause and run regression/load tests.
11. Collect a post-fix snapshot to confirm retained heap and trends have improved.
12. Protect and delete dump files according to the retention policy.

Do not use a single histogram or heap dump in isolation to conclude a memory leak without understanding the workload and object lifecycle.

## 16. Checklist Before Running jmap

- Check `jmap --help` for the exact JDK.
- Confirm the right host, container, PID, and user.
- Verify attach permissions.
- Choose `-histo` or `-dump` based on your goal.
- Intentionally choose `live` or `all`.
- Understand GC and pause impact.
- Prepare output directory, write permissions, and disk space.
- Use absolute paths for production captures.
- Protect HPROF files as sensitive data.
- Prefer jcmd for new diagnostic workflows.
- Read the impact of `GC.heap_dump` and `GC.class_histogram`.
- Do not use jhsdb live attach in production without assessing the risk.
- Use HPROF analysis tools to find retained heap and GC roots.
- Save collection metadata and file checksums.
- Delete dumps per retention policy after investigation.

## 17. Key Terms to Remember

| Term | Meaning |
|---|---|
| jmap | JDK tool for collecting heap and class loader information |
| PID | OS-level Process ID of the JVM |
| Heap | Memory area containing Java objects |
| Histogram | Statistics of instance counts and shallow bytes by class |
| Heap dump | Object graph snapshot in HPROF format |
| HPROF | Binary file format containing heap data |
| Live object | Object still reachable according to liveness determination |
| Unreachable object | Object no longer reachable and eligible for GC collection |
| Shallow size | Direct size of the object itself |
| Retained size | Heap that can be freed when an object and what it solely retains become unreachable |
| Class loader | Component that loads classes into the JVM |
| Finalization | Legacy mechanism for processing objects before reclamation; should not be used for resource management |
| jcmd | Tool for sending diagnostic commands to a JVM |
| jhsdb | Serviceability Agent used to analyze a JVM or core dump |
| MAT | Eclipse Memory Analyzer used to analyze heap dumps |
| GC root | Starting point of a reference chain keeping an object alive |
| Dominator tree | Structure used to find objects holding large retained heap |
| JFR | Java Flight Recorder used to collect runtime events |

jmap provides histograms, heap dumps, class loader statistics, and finalization information to support memory investigations. Verify the target process, understand the impact of `live`/`all` and garbage collection, protect HPROF files, and analyze the reference graph with appropriate tools. For new diagnostic workflows, prefer jcmd per Oracle's recommendation.

## References

- Oracle JDK 24 — The jmap Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmap.html
- Oracle JDK 24 — Diagnostic Tools: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Oracle JDK 24 — The jcmd Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Oracle JDK 24 — The jhsdb Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jhsdb.html
- Oracle JDK 24 — Troubleshooting Guide: https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf
