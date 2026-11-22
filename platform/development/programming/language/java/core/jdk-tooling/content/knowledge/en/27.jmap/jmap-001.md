# The jmap Command

**jmap** is a JDK diagnostic tool used to inspect certain memory details of a running Java HotSpot VM. Common tasks include generating heap histograms, exporting heap dumps, viewing class loader statistics, and listing objects awaiting finalization.

jmap is useful when investigating suspected memory leaks, abnormal heap growth, or when collecting data for offline analysis. However, it is classified as an **experimental and unsupported** tool in the JDK documentation; Oracle recommends using **jcmd** for modern diagnostics because it offers more commands and reduces overhead compared to older utilities like jmap.

A heap dump or histogram can cause pauses, trigger garbage collection, consume significant CPU/I/O, and contain sensitive data in the object graph. Therefore, verify the target JVM, choose the right data type, prepare sufficient disk space, and protect the output file before running it in production.

## 1. What is jmap used for?

jmap connects to a Java process and reads information related to the heap or class loaders. Common commands in JDK 24:

| Command | Purpose |
|---|---|
| -histo | Print a histogram of object counts and bytes by class |
| -dump | Export the heap to an HPROF binary file |
| -clstats | Print class loader statistics in the heap |
| -finalizerinfo | View information about objects awaiting finalization |
| --help | Print syntax and supported options |

These operations help answer different questions:

- Which classes currently have the most instances?
- Which classes occupy the most shallow heap bytes?
- Can we capture a heap snapshot to find objects holding long-lived references?
- Which class loaders are loading many classes?
- Are there many objects waiting for finalization?

jmap does not automatically conclude whether an application has a memory leak. It provides a snapshot for engineers to analyze alongside GC logs, JFR, metrics, and application behavior.

### jmap is not a continuous monitoring tool

jmap performs a one-time snapshot or query at runtime. It does not replace time-series metrics, heap occupancy charts, GC pause monitoring, or production profiling.

To observe heap trends over time, use Java Flight Recorder (JFR), JDK Mission Control (JMC), JMX, or a secured monitoring system. Periodic histograms can be useful, but you should not continuously generate heap dumps in production just to track trends.

## 2. Support status and JDK versions

The Oracle JDK 24 Troubleshooting Guide classifies jmap as an experimental tool. The documentation also recommends using jcmd instead of older utilities such as jmap, jinfo, and jstack for better diagnostics and lower overhead.

This means:

- jmap options or output may change between versions.
- The tool may no longer be included in a future JDK release.
- Availability depends on the JVM implementation, operating system, and attach permissions.
- You should not build long-term automation based on jmap output.
- Always check the help output of the exact JDK running the application.

View syntax:

~~~bash
jmap --help
~~~

On OpenJDK 24.0.2 in a test environment, the help lists the `-clstats`, `-finalizerinfo`, `-histo`, and `-dump` commands. Older heap summary options like `-heap` do not appear in this version's help. Do not copy syntax from older JDK documentation without checking the current toolchain.

### Prefer jcmd for new workflows

Oracle recommends using jcmd instead of jmap in modern diagnostic workflows.

Commonly used equivalent commands:

~~~bash
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_dump heap.hprof
jcmd <pid> VM.classloader_stats
jcmd <pid> GC.finalizer_info
~~~

Diagnostic command names and options may vary by JVM. Use the following commands to see which commands the target process supports:

~~~bash
jcmd <pid> help
jcmd <pid> help GC.heap_dump
jcmd <pid> help GC.class_histogram
~~~

Even when using jcmd, heap histograms and heap dumps can still have high impact. Preferring jcmd does not mean heap collection operations become free or pause-free.

## 3. Identifying the right JVM PID

jmap requires the PID of the target Java process. You can use jps to quickly find JVMs on the local machine:

~~~bash
jps -l
~~~

Illustrative output:

~~~text
31840 com.example.ApiServer
32004 com.example.BatchWorker
~~~

If the application is ApiServer, the illustrative PID is 31840. Before running jmap, verify the process using OS tools.

Linux/macOS:

~~~bash
ps -p 31840 -o pid,ppid,user,etime,args
~~~

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process -Filter "ProcessId = 31840" |
    Select-Object ProcessId, ParentProcessId, Name, CommandLine
~~~

PIDs can be reused after a process terminates. Do not use an old PID saved from a previous investigation without re-verifying the process name, user, command line, and start time.

### Permissions and the Attach API

jmap needs to connect to the target JVM. Typically, the tool must run on the same machine and under an account with appropriate attach permissions. Attach can fail if:

- The process no longer exists or its PID has changed.
- The user running jmap differs from the user that started the JVM and lacks appropriate permissions.
- The attach mechanism is disabled in the JVM.
- An OS/container security policy blocks process access.
- The tool's runtime or architecture is incompatible with the target process.
- The JVM is unresponsive or hung.

Do not automatically run as root/Administrator to bypass every attach error. Identify the proper owner and follow operational procedures.

### Containers and PID namespaces

In containers, the same JVM can have different PIDs when observed from inside the container versus from the host. For example, a process might be PID 1 inside the container but PID 42000 on the host.

Run jmap inside the right container or use the verified host PID according to your container runtime's procedures. Do not use a PID from one namespace for a command running in another namespace.

## 4. Heap histograms with -histo

A heap histogram summarizes objects by class. Each row typically has the following columns:

~~~text
 num     #instances         #bytes  class name
------------------------------------------------
   1:         50000        4000000  com.example.Session
   2:         32000        2048000  byte[]
   3:         18000         576000  java.lang.String
~~~

The numbers in this example are illustrative only.

- **num:** rank of the class in the report.
- **#instances:** number of instances of the class.
- **#bytes:** total shallow size of the instances of the class.
- **class name:** name of the class; array classes may appear in formats like `byte[]` or `java.lang.Object[]`.

Shallow size is the direct size of an object, not its retained size. If a HashMap holds references to thousands of objects, the histogram alone does not tell you whether that HashMap is a GC root or which object keeps the entire live graph alive.

### Print a histogram

~~~bash
jmap -histo <pid>
~~~

Example:

~~~bash
jmap -histo 31840
~~~

A histogram helps identify classes with many instances or high shallow byte usage. If application classes like `Session`, `CacheEntry`, or `byte[]` are at the top, investigate allocations and the reference graph before concluding it is a leak.

### Count only live objects

~~~bash
jmap -histo:live <pid>
~~~

The `live` option counts only objects that remain alive after live-object determination. This operation may require a garbage collection and cause a significant pause.

### Count all objects in the heap

~~~bash
jmap -histo:all <pid>
~~~

The `all` option includes objects that are no longer reachable from the garbage collector's perspective. In JDK 24, the help indicates that `all` is the default when neither `live` nor `all` is specified; if both `live` and `all` are provided, `live` takes precedence.

An `all` histogram can show many objects that have already become garbage but have not yet been collected. Therefore, the object count in `all` does not equal the number of objects actively kept alive by the application.

### Write the histogram to a file

~~~bash
jmap -histo:live,file=histogram.txt <pid>
~~~

The `file` option writes the histogram to a file instead of only printing it to the terminal. The `parallel` option controls the number of threads used to inspect the heap:

~~~bash
jmap -histo:all,parallel=1,file=histogram-all.txt <pid>
~~~

- `parallel=1` requests a single thread for inspection.
- `parallel=0` lets the JVM choose the number of threads automatically.
- Other values ask the JVM to attempt using the specified number of threads, though it may use fewer.

Histograms can be large. Ensure the output directory has sufficient disk space and appropriate write permissions.

## 5. Reading histograms to investigate memory leaks

A single histogram only shows a point-in-time snapshot. To investigate a leak, you need to compare over time and exclude uncollected garbage.

Example of two snapshots:

| Class | Histogram 1 | Histogram 2 | Initial Observation |
|---|---:|---:|---|
| Session | 2,000 instances | 20,000 instances | Sharp increase, needs investigation |
| byte[] | 8 MB | 60 MB | Likely payload or buffer |
| String | 1 MB | 1.2 MB | Slight increase |
| RequestContext | 4,000 instances | 4,200 instances | Nearly stable |

This is only a hypothetical example, not actual measurements.

### Analysis workflow

1. Determine whether the histogram is `live` or `all`.
2. Compare the same type of snapshot across collections.
3. Look for classes whose instance count or shallow bytes increase continuously.
4. Check whether that class is a legitimate cache, session, queue, listener, or buffer.
5. Use a heap dump to find reference paths and dominators.
6. Check allocation stacks or JFR if you need to know where the objects are created.
7. Verify under realistic load and with regression tests after applying a fix.

### Histograms do not show what is retaining objects

A histogram does not show which objects hold references to classes with high instance counts. It also does not directly show retained heap.

To find the root cause, open a heap dump with Eclipse Memory Analyzer (MAT), JDK Mission Control, or a suitable HPROF analysis tool. Use the dominator tree, paths to GC roots, and retained size to identify which object graph is holding memory.

Do not conclude there is a memory leak just because a class has a large count. A bounded cache, pool, or queue can legitimately hold many objects by design.

## 6. Creating a heap dump with -dump

A heap dump is a snapshot of the Java heap written to an HPROF binary file. It contains objects, fields, arrays, and reference relationships at the moment of capture.

Syntax:

~~~bash
jmap -dump:<dump-options> <pid>
~~~

Options in JDK 24:

| Option | Meaning |
|---|---|
| live | Dump only live objects |
| all | Dump all objects in the heap |
| format=b | HPROF binary format |
| file=... | Output file path |
| gz=n | Write gzip-compressed HPROF with level n from 1 to 9 |

### Dump the entire heap

~~~bash
jmap -dump:format=b,file=heap.hprof <pid>
~~~

If neither `live` nor `all` is specified, the JDK 24 help states that `all` is the default. The HPROF file can be nearly as large as—or much smaller than—the heap depending on the number of objects, their contents, and how they are stored.

### Dump only live objects

~~~bash
jmap -dump:live,format=b,file=heap-live.hprof <pid>
~~~

The `live` option dumps only objects determined to be live. This process can trigger a garbage collection and cause a pause.

### Explicitly dump all objects

~~~bash
jmap -dump:all,format=b,file=heap-all.hprof <pid>
~~~

The `all` option retains unreachable objects as well. This data can be useful in certain analyses, though the file will include many objects that GC could reclaim.

If both `live` and `all` are specified, `live` takes precedence according to the JDK 24 help.

### Compress the heap dump

~~~bash
jmap -dump:live,format=b,gz=1,file=heap-live.hprof.gz <pid>
~~~

Compression levels:

- 1: faster compression, lower compression ratio.
- 9: stronger compression, higher CPU and time cost.
- Values range from 1 to 9.

Compression can reduce file size, but it increases CPU usage and collection time. Choose a level appropriate for the service's condition and I/O limits.

### Output path

Use an absolute path in production so you know exactly where the file is created:

~~~bash
jmap -dump:live,format=b,file=/var/secure-diagnostics/app-live.hprof <pid>
~~~

On Windows, for example:

~~~powershell
jmap -dump:live,format=b,file=C:\secure-diagnostics\app-live.hprof <pid>
~~~

Ensure the directory exists, the account running the command has write permissions, and the volume has enough free space. Do not write heap dumps into a web root, public artifact directory, or a temporary directory with broad access permissions.

## 7. Heap dumps can impact production

A heap dump is a heavy operation. Its duration and impact depend on heap size, object count, GC algorithm, filesystem, CPU, and how the JVM handles the snapshot.

Main risks:

- The JVM may pause the application for a significant duration.
- A Full GC may be required when dumping only live objects.
- Traversing the heap can consume substantial CPU and I/O.
- The file can occupy a large amount of disk space.
- A full disk can affect other services sharing the same volume.
- The JVM may time out at load balancers or health checks during a long pause.
- The heap dump may contain sensitive user data.

### Planning before a dump

1. Identify the exact PID and service.
2. Check the heap size and available volume space.
3. Choose `live` or `all` based on the question you need to answer.
4. Pick a low-traffic period or maintenance window if appropriate.
5. Prepare an output directory with restricted access permissions.
6. Confirm the collection and secure file transfer procedure.
7. Monitor service health and disk usage.
8. Delete or archive the file according to your retention policy after the investigation.

Do not run repeated heap dumps at short intervals in production without evaluating the overhead.

## 8. Securing heap dumps and histograms

A heap dump does not contain only technical metadata. It may contain:

- Passwords, access tokens, API keys, or session cookies residing in objects.
- Database connection strings and credentials.
- Request/response payloads and personal data.
- Email addresses, phone numbers, or personally identifiable information.
- Transaction data, caches, and uncleared payloads.
- Private keys or secrets if the application keeps them in memory.

Therefore, heap dumps must be handled as sensitive data.

### File protection rules

- Only authorized investigators may read the file.
- Use encrypted volumes or file encryption mechanisms per policy.
- Never upload heap dumps to public file-sharing services.
- Never send the file via unapproved email or chat.
- Never commit the file to Git or include it in build artifacts.
- Record who collected it, timestamp, PID, host, JDK, and reason for collection.
- Enforce retention limits and securely delete the file once no longer needed.
- When sharing reports, prefer redacted histograms or analysis summaries without raw object data.

Heap dump filenames should also avoid containing user information or secrets.

## 9. Class loader statistics with -clstats

Class loaders load classes into the JVM. An application using plugins, hot reload, an application server, or multiple deployments can create many class loaders.

Usage:

~~~bash
jmap -clstats <pid>
~~~

The class loader statistics report helps you inspect:

- Which class loaders currently exist in the heap.
- Parent class loaders.
- Number of classes loaded by each loader.
- Activity and class metadata size details that the tool can gather.

This data is useful when investigating class loader leaks. For example, an application is redeployed multiple times, yet old class loaders remain retained by a `ThreadLocal`, static reference, thread, or library cache.

### Signs to investigate

- The number of class loaders grows with each redeploy.
- Class loaders from an old application remain after undeploy.
- A class loader retains many classes that are no longer needed.
- Threads or static caches hold references to old class loaders.

`jmap -clstats` does not by itself identify the reference path causing the leak. Use a heap dump and GC roots analysis to find what is retaining the class loader.

### Alternative command with jcmd

~~~bash
jcmd <pid> VM.classloader_stats
~~~

On JDK 21.0.9 in a test environment, the `VM.classloader_stats` diagnostic command is supported and has low impact. The exact list of commands depends on the JVM; run `jcmd <pid> help` before executing.

## 10. Finalization queue info with -finalizerinfo

jmap provides the option:

~~~bash
jmap -finalizerinfo <pid>
~~~

This command prints information about objects awaiting finalization. It is useful when an application still relies on the legacy finalization mechanism or when the finalizer queue grows abnormally.

Finalization is not a reliable way to manage resources. Do not rely on `finalize()` to close files, sockets, or critical resources. Use `try-with-resources`, `AutoCloseable`, or explicit lifecycle management.

The corresponding jcmd command may be:

~~~bash
jcmd <pid> GC.finalizer_info
~~~

The exact diagnostic command name and impact level should be verified using the target JVM's help output.

## 11. Using jcmd instead of jmap

jcmd is the modern diagnostic tool recommended by Oracle. It sends diagnostic commands directly to the JVM and can provide heap dumps, histograms, class loader statistics, thread dumps, JFR recordings, and much more.

### Heap histogram

~~~bash
jcmd <pid> GC.class_histogram
~~~

To include unreachable objects as well:

~~~bash
jcmd <pid> GC.class_histogram -all
~~~

On the tested JDK 21.0.9, `GC.class_histogram` has High impact. The actual impact depends on heap size and contents.

### Heap dump

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

This command creates an HPROF dump. According to the tested JVM's help, the operation has High impact and triggers a full GC unless `-all` is specified.

To dump unreachable objects as well:

~~~bash
jcmd <pid> GC.heap_dump -all heap-all.hprof
~~~

You can compress it using the `-gz` option at a level supported by the JVM's help:

~~~bash
jcmd <pid> GC.heap_dump -gz=1 heap.hprof.gz
~~~

If the file already exists, check the overwrite option in help before overwriting.

### Class loader statistics

~~~bash
jcmd <pid> VM.classloader_stats
~~~

### Finalization queue

~~~bash
jcmd <pid> GC.finalizer_info
~~~

### Check impact level before running

~~~bash
jcmd <pid> help GC.heap_dump
jcmd <pid> help GC.class_histogram
~~~

Diagnostic commands can have Low, Medium, or High impact. Read the description from the exact target JVM before running them in production.

### Comparison table

| Need | jmap | Recommended jcmd |
|---|---|---|
| Heap histogram | -histo[:live] | GC.class_histogram |
| Heap dump | -dump:... | GC.heap_dump |
| Class loader statistics | -clstats | VM.classloader_stats |
| Finalization queue | -finalizerinfo | GC.finalizer_info |
| Heap summary | Options vary by JDK | GC.heap_info |

jcmd may provide different commands depending on the JDK. Do not assume every JVM supports the exact same set of diagnostic commands.

## 12. Analyzing core dumps with jhsdb jmap

If the JVM has crashed and produced a core dump, do not use the `jmap <pid>` syntax. Use the Serviceability Agent via `jhsdb`.

View help:

~~~bash
jhsdb jmap --help
~~~

Read a heap summary from a core file:

~~~bash
jhsdb jmap --heap --core core.1234 --exe /path/to/java
~~~

Generate a histogram:

~~~bash
jhsdb jmap --histo --core core.1234 --exe /path/to/java
~~~

Export a heap dump:

~~~bash
jhsdb jmap --binaryheap --dumpfile heap-from-core.hprof --core core.1234 --exe /path/to/java
~~~

Key points to remember:

- `--core` and `--exe` must be specified together.
- `--exe` must be the executable matching the JVM that produced the core dump.
- Core files can be very large and contain sensitive data.
- Core analysis requires proper permissions and compatible binaries.
- Option names and syntax must be verified against the current JDK.

### Warning when attaching jhsdb to a running JVM

jhsdb is a Serviceability Agent tool and has experimental/unsupported status. Oracle warns that attaching jhsdb to a live process can cause the process to hang and is likely to crash it when the debugger detaches.

Therefore, prefer using jhsdb with core dumps for postmortem analysis. Do not attempt `jhsdb --pid` in production just to grab a histogram or heap dump without evaluating and approving the risk of freezing or crashing the service.

## 13. From heap dump to object graph analysis

After generating an HPROF file, open it with an analysis tool such as Eclipse Memory Analyzer (MAT) or another HPROF-compatible tool.

Typical workflow:

1. Open the heap dump file.
2. Generate a histogram to inspect classes by instance count and shallow bytes.
3. Inspect the dominator tree to find objects retaining large amounts of heap.
4. Trace paths to GC roots to see why objects remain reachable.
5. Inspect static fields, `ThreadLocal`, listeners, caches, and collections.
6. Compare snapshots before/after load or after sessions end.
7. Cross-reference with source code and allocation profiles.

### Shallow size vs. retained size

- **Shallow size:** the direct size of an object, excluding other objects it references.
- **Retained size:** the total memory that would be freed if that object and all objects only retained by it became unreachable.

Histograms mainly show shallow size by class. The dominator tree and reference graph help you find retained memory and the objects holding references.

### Example scenario

A service has a `SessionCache` class growing from a few thousand to hundreds of thousands of instances after each traffic spike.

The histogram shows `SessionCache` and `byte[]` increasing. However, the histogram does not tell you whether the cache is bounded. In MAT, the dominator tree shows a static `ConcurrentHashMap` holding all `Session` objects. Paths to GC roots point to a static field in `SessionRegistry` retaining that map.

Possible fixes include setting a TTL, bounding the cache size, removing entries when sessions end, or fixing the lifecycle. Run load tests and verify that retained heap decreases after the fix.

This is an illustrative example of the analysis method, not measurements from a specific application.

## 14. Common errors when running jmap

### Not enough permissions or attach failed

Check the user owning the JVM, attach permissions, OS policy, and the exact PID. Run under the same service account following authorized procedures. Do not escalate privileges arbitrarily.

### Process does not exist

The PID may be wrong, the process may have exited, or the PID may have been reused. Re-verify using `jps` and OS process tools.

### jmap is incompatible with the JVM

Use a JDK tool matching the target JVM's major version and vendor whenever possible. Check 32/64-bit architecture, executable, and runtime provider.

### jmap is unresponsive

The process may be hung or unable to reach a safepoint. Oracle documents using jhsdb in some hung-process scenarios, but note that attaching jhsdb to a live process can hang it and crash it on detach. Prefer collecting a core dump via postmortem procedures or using a supported diagnostic workflow.

### Heap dump cannot be created

Check:

- Whether the file path is valid.
- Whether the directory exists and is writable.
- Whether the volume has enough free space.
- Whether the file already exists or is locked.
- Whether the JVM is still responsive.
- Whether attach permissions and security policies allow it.

Do not overwrite an existing heap dump unless you have confirmed its contents are already safely archived.

### Dump file is too large

Use a `live` dump if you only need live objects, compress if appropriate, and provision a volume with sufficient space. Do not exclude unreachable objects if the goal of the investigation is to inspect the full heap state at capture time.

### Histogram changes drastically between runs

Verify whether both runs used `live` or `all`, check application load, GC state, and capture timing. Compare snapshots taken under the same conditions before concluding there is a leak.

### Output file not found

Relative paths are resolved from the working directory of the shell running the command. Use an absolute path and check the access permissions of the user running the tool.

## 15. Safe heap evidence collection workflow

1. Identify the service, host/container, and current PID.
2. Verify the process name, user, and runtime version.
3. Clarify the investigation question: histogram, heap dump, class loader, or finalizer queue.
4. Read the command's help and impact; prefer `jcmd` for new diagnostics.
5. Estimate pause, CPU, I/O, and file size.
6. Choose `live` or `all` to match the goal.
7. Use a protected output directory with sufficient free space.
8. Collect at an appropriate time and monitor service health.
9. Record metadata: host, PID, JDK, timestamp, command, reason, and operator.
10. Analyze the HPROF file in a controlled environment.
11. Redact sensitive data before sharing reports.
12. Delete the dump file according to your retention policy once finished.

If heap dumps are generated automatically on `OutOfMemoryError`, protect both the dump file and its output path. You can configure the JVM with:

~~~bash
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/secure-diagnostics
~~~

These are JVM startup options for the application, not jmap commands. Check disk space and directory permissions before enabling them in production.

## 16. jmap usage checklist

- Check the JDK version and `jmap --help`.
- Remember that jmap is experimental/unsupported and prefer `jcmd`.
- Verify the exact PID, host, container, and user.
- Check attach permissions before running.
- Choose a histogram or heap dump based on the question to answer.
- Understand the difference between `live` and `all`.
- Remember that histograms report shallow bytes, not retained heap.
- Assess pause/GC/CPU/I/O impact before dumping.
- Prepare disk space and an absolute output path.
- Protect HPROF files because they can contain passwords, tokens, and user data.
- Use MAT or a compatible tool to inspect the dominator tree and GC roots.
- Use `jcmd GC.class_histogram` and `GC.heap_dump` for new workflows.
- Use `jhsdb jmap` with core files; be cautious with live attach.
- Do not treat a single histogram as sufficient proof of a memory leak.
- Record metadata and delete dumps according to the retention policy.

## 17. Key terminology

| Term | Meaning |
|---|---|
| jmap | JDK tool for diagnosing JVM heap and class loaders |
| Heap | Memory region containing Java objects |
| Heap histogram | Summary of instance counts and shallow bytes by class |
| Heap dump | Object graph snapshot in HPROF format |
| HPROF | Binary format used to store heap snapshots |
| Live object | Object still reachable according to live-object determination |
| Unreachable object | Object no longer reachable and eligible for GC reclamation |
| Shallow size | Direct size of an object |
| Retained size | Memory freed when an object and all objects it solely retains become unreachable |
| Class loader | Component that loads classes into the JVM |
| Finalization queue | Objects awaiting finalization processing |
| jcmd | Tool for sending diagnostic commands to the JVM |
| jhsdb | Serviceability Agent tool for analyzing a JVM or core dump |
| MAT | Eclipse Memory Analyzer, a heap dump analysis tool |
| GC root | Starting point of a reference chain keeping an object reachable |
| Dominator tree | Structure used to find objects retaining large amounts of heap |
| JFR | Java Flight Recorder, used to collect runtime events |

jmap can help collect histograms and heap dumps for memory investigations, but it is an experimental/unsupported tool and its operations can cause pauses, GC, heavy I/O, or sensitive data exposure. Prefer `jcmd` for new diagnostics, use HPROF analysis tools to find reference paths and retained heap, and protect every dump file as sensitive production data.

## References

- Oracle JDK 24 — [Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- Oracle JDK 24 — [Troubleshooting Guide: Diagnosing Java Memory Leaks](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- Oracle JDK 24 — [The jhsdb Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jhsdb.html)
- Oracle Java SE 24 — [Java HotSpot VM Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/)