# Heap Dump Analysis in Java

A **heap dump** is a snapshot of the objects residing on the Java heap at a specific point in time. The dump file stores information about classes, object instances, fields, and reference relationships between objects. When an application experiences abnormal memory growth or encounters an `OutOfMemoryError`, a heap dump helps identify which objects consume the most memory and why the garbage collector still has to keep them alive.

With the HotSpot JVM, heap dumps are typically saved in the **HPROF** binary format. Dumps can be generated using `jcmd`, `jmap`, JConsole, or automatically when Java heap exhaustion occurs. Oracle recommends using **jcmd** for new diagnostics; **jmap** is still present in JDK 26, but is marked as experimental and unsupported.

Analyzing a heap dump is not just about finding the class with the most instances. You need to understand the difference between shallow heap and retained heap, trace reference paths from Garbage Collection (GC) roots, inspect dominator objects, and compare multiple snapshots to identify which objects are being retained unexpectedly.

## 1. What Is a Heap Dump Used For?

Heap dumps help investigate issues related to objects on the Java heap:

- Memory leaks: objects that are no longer needed but are still held by a reference.
- Continuous heap growth: the number of instances or object sizes increasing over time.
- `OutOfMemoryError: Java heap space`.
- Unbounded cache or collection growth.
- ClassLoader leaks: old classes and class loaders remaining reachable.
- Overly large object graphs: a single root object retaining many child objects.
- An abnormally high number of instances of a class.
- Memory retained by static fields, listeners, thread locals, or queues.

For example, an application might create many request objects. After a request finishes, those objects should be eligible for garbage collection. However, if a static collection still holds references to them, the objects remain alive and the heap grows steadily.

A heap dump shows the state of objects at the moment the snapshot is taken. It does not record the full history of where and when objects were allocated. To find allocation sites over time, combine it with Java Flight Recorder (JFR), a profiler, or appropriate instrumentation.

## 2. The Java Heap and What a Heap Dump Represents

The Java heap is the runtime memory area used for allocating objects and arrays. The garbage collector determines which objects are still reachable from GC roots and reclaims those that are no longer reachable.

An HPROF heap dump typically contains:

- Class and class loader information.
- Object instances and arrays.
- Primitive field values.
- References between objects.
- GC root information.
- Metadata required to analyze the object graph.

Reference model:

~~~text
GC Roots
   |
   v
Application static field
   |
   v
Cache object
   |
   v
Object array
   |
   +------> Customer object
   |
   +------> Order object
   |
   +------> byte[] buffer
~~~

If a reference path from a GC root to an object still exists, the garbage collector considers that object reachable and will not reclaim it.

### A Heap Dump Does Not Represent the Entire Process RAM

A heap dump focuses on the Java heap. It is not a complete copy of the process's resident memory (RSS) or all native memory.

Areas to distinguish:

| Memory Area | Examples | How a Heap Dump Reflects It |
|---|---|---|
| Java heap | Objects, arrays, collections | Contains object data and references |
| Metaspace | HotSpot class metadata | Not part of the regular object graph on the Java heap |
| Thread stack | Stack frames and local variables | May appear via GC root/reference context, but is not a full dump of stack memory |
| Direct/native memory | DirectByteBuffer payloads, JNI allocations | Does not contain full native payloads |
| Code cache | JIT-compiled code | Not part of Java heap contents |
| Native libraries | C/C++ allocations | Not fully described by a Java heap dump |

If RSS increases while the Java heap does not grow correspondingly, check native memory, direct buffers, thread stacks, metaspace, or JNI libraries. You can use Native Memory Tracking (NMT), OS tools, and JFR to investigate these areas.

## 3. Key Concepts When Reading a Heap Dump

### Shallow Heap

**Shallow heap** is the amount of memory consumed by the object itself, excluding any other objects it references.

For example, an `ArrayList` containing 10,000 `String` objects:

- The shallow size of the `ArrayList` only counts the `ArrayList` object itself.
- The shallow size of the backing `Object[]` counts the reference array.
- The shallow size of each `String` and its backing `byte[]` is counted separately.

Therefore, an object with a small shallow size can still retain a very large amount of memory.

### Retained Heap

**Retained heap** is the amount of memory that could be reclaimed if the object in question became unreachable, based on dominator relationships in the object graph.

Example:

~~~text
Static field
    |
    v
Cache
    |
    v
Object[]
    |
    +----> 10,000 Customer objects
    |
    +----> 10,000 byte[] buffers
~~~

The `Cache` object may have a small shallow size, but a large retained heap because it keeps the backing array and the referenced objects below it alive.

Retained heap is a key metric for finding objects that hold a lot of memory. You cannot simply sum the shallow sizes of all objects reachable from a node, because an object may be referenced by multiple branches. Dominator analysis handles this retention relationship.

### Dominator

Object A **dominates** object B if every path from GC roots to B must pass through A. If A is no longer reachable, B is also no longer reachable through any other path.

A dominator tree transforms the object graph into a tree structure that helps identify which objects are keeping groups of other objects alive.

In Eclipse Memory Analyzer (MAT), the Dominator Tree is typically sorted by retained heap to make it easy to find objects or object groups consuming the most memory.

### GC Roots

GC roots are the starting points the garbage collector uses to determine reachable objects. Common types of roots include:

- References from local variables in the stack frames of active threads.
- Static fields of classes that are kept alive.
- JNI global references.
- Thread objects and internal JVM references.
- Certain internal objects managed by the runtime.

When an object should have ended its lifecycle but still appears on the heap, trace **Path to GC Roots** to find the reference keeping it alive.

### Object Count and Retained Size Are Not the Same

A class with millions of instances is not necessarily the main culprit if each instance is small and short-lived. Conversely, a single cache object can hold millions of child objects and account for most of the retained heap.

Inspect all of the following together:

- Instance count.
- Total shallow heap.
- Retained heap.
- Object types and class loaders.
- Paths to GC roots.
- Changes across snapshots.

## 4. Generating a Heap Dump with jcmd

Oracle recommends using `jcmd` instead of `jmap` in new diagnostic workflows. `jcmd` sends diagnostic commands to a running JVM and supports generating HPROF heap dumps.

Identify the Java process:

~~~bash
jcmd -l
~~~

Example output:

~~~text
2125 com.acme.DemoServer
5485 jdk.jcmd/sun.tools.jcmd.JCmd
~~~

Use the specific PID to generate a dump:

~~~bash
jcmd 2125 GC.heap_dump /secure/diagnostics/heap-2125.hprof
~~~

PID `2125` is just an example; replace it with the PID of your actual application.

The `GC.heap_dump` command has a **High** impact level according to the JDK 26 documentation. By default, the JVM requests a full GC before creating the dump, unless the `-all` option is used. This can cause a noticeable pause depending on heap size and object graph contents.

### Dumping All Objects, Including Unreachable Ones

~~~bash
jcmd 2125 GC.heap_dump -all=true /secure/diagnostics/heap-all.hprof
~~~

The `-all` option requests dumping unreachable objects as well. When `-all` is omitted, the command requests a full GC and generates the dump from the objects remaining after GC.

For typical memory leak analysis, a snapshot of objects still reachable after GC is usually more useful because it focuses on memory that is actually being kept alive.

Only use `-all` when you have a reason to inspect unreachable objects or want to observe contents before GC removes them.

### Compressing the Heap Dump

`jcmd` supports compressing HPROF output as it writes:

~~~bash
jcmd 2125 GC.heap_dump -gz=1 /secure/diagnostics/heap-2125.hprof.gz
~~~

Lower compression levels prioritize speed; higher levels increase compression at the cost of more CPU. Check whether your analysis tool can read compressed files directly; if not, decompress it to an HPROF file before opening.

### Checking Command Syntax

~~~bash
jcmd 2125 help GC.heap_dump
~~~

The target JVM's help output shows available options for that specific JDK and running VM. Common options in JDK 26:

| Option | Meaning |
|---|---|
| -all | Dump unreachable objects as well |
| -gz | Write HPROF in gzip format with the specified compression level |
| -overwrite | Allow overwriting an existing file |
| -parallel | Number of threads used to generate the heap dump |

Do not use `-overwrite` unless you have confirmed the target file can be replaced. By default, the command does not overwrite existing files.

## 5. Generating a Heap Dump with jmap

`jmap` is a legacy tool used to extract memory information from a Java process. In JDK 26, the manual marks `jmap` as **experimental and unsupported**, and it may be changed or removed in future JDK releases. Oracle recommends using `jcmd` for newer diagnostic support and lower performance overhead.

HPROF dump syntax:

~~~bash
jmap -dump:format=b,file=heap.hprof 2125
~~~

Dump only live objects after GC:

~~~bash
jmap -dump:live,format=b,file=heap-live.hprof 2125
~~~

The `-dump` options include:

- `live`: dump only live objects.
- `format=b`: write HPROF binary format.
- `file=filename`: output file name.

Other commonly used options:

~~~bash
jmap -histo 2125
jmap -histo:live 2125
jmap -clstats 2125
jmap -finalizerinfo 2125
~~~

| Option | Purpose |
|---|---|
| -histo | Object histogram by class |
| -histo:live | Histogram counting only live objects |
| -clstats | Class loader statistics |
| -finalizerinfo | Information on objects awaiting finalization |
| -dump | Generate a heap dump |

Do not build new automation that depends on `jmap`'s output format. For generating a dump from a running JVM, prefer:

~~~bash
jcmd 2125 GC.heap_dump /secure/diagnostics/heap.hprof
~~~

## 6. Automatically Generating a Heap Dump on OutOfMemoryError

You can configure the JVM to generate a heap dump when the Java heap is exhausted:

~~~bash
java \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/diagnostics/java_pid%p.hprof \
  -jar app.jar
~~~

Where:

- `-XX:+HeapDumpOnOutOfMemoryError` enables dumping when the JVM detects Java heap exhaustion.
- `-XX:HeapDumpPath` specifies the directory and file name.
- `%p` is replaced by the JVM's process ID.

If `HeapDumpPath` is not set, the default file is created in the working directory with a name like `java_pid<pid>.hprof`.

### Limitations of Automatic Dumping

This option applies to `OutOfMemoryError` caused by Java heap exhaustion. It does not guarantee a dump for every type of `OutOfMemoryError`, such as errors creating native threads or other native resource errors.

Before enabling it in production:

- Choose a directory with sufficient free space.
- Ensure the process has write permissions.
- Use a file name differentiated by PID.
- Restrict read permissions on the file.
- Have a retention policy and clean up old files.
- Test in a staging environment.
- Define how to retrieve the dump from the failing machine for analysis.

If the heap size is close to the container memory limit or disk quota, the dump may fail due to insufficient space. Do not rely solely on automatic dumping without monitoring disk space.

## 7. Analyzing a Heap Dump with Eclipse Memory Analyzer

**Eclipse Memory Analyzer (MAT)** is a heap dump analysis tool that supports reading HPROF files, computing object statistics, building dominator trees, and tracing GC roots.

Download MAT from the official Eclipse site and open the HPROF file:

1. Launch Memory Analyzer.
2. Select Open Heap Dump.
3. Choose the `.hprof` file.
4. Wait for MAT to parse the object graph and build indexes.
5. Start with the Overview and Leak Suspects Report.
6. Inspect the Histogram, Top Consumers, and Dominator Tree.
7. Select suspicious objects and run Path to GC Roots.

MAT can require a large amount of memory to analyze large dumps. If a dump contains tens of millions of objects, use a 64-bit analysis machine with adequate RAM and disk space. You can increase MAT's own heap via the `-Xmx` setting in MAT's `.ini` file.

### Overview

Overview provides a high-level summary of the heap dump, including the number of objects, classes, class loaders, and recorded heap size.

Start from the overview to confirm the dump parsed cleanly and to gauge the scale of the object graph before running heavy queries.

### Histogram

Histogram groups objects by class, typically displaying:

- Class name.
- Number of instances.
- Shallow heap.
- Retained heap or corresponding metrics if calculated.

Illustrative example:

| Class | Instances | Shallow heap |
|---|---:|---:|
| byte[] | 2,000 | 32 MB |
| java.lang.String | 18,000 | 1.2 MB |
| java.util.HashMap$Node | 12,000 | 0.8 MB |
| com.acme.Customer | 2,000 | 0.3 MB |

The numbers above are examples only. Histogram helps find classes with high instance counts or large shallow heap, but it does not tell you who is keeping those objects alive.

### Top Consumers

Top Consumers groups memory-heavy objects by class, package, or class loader. Use this query to narrow down the area to investigate.

### Dominator Tree

Dominator Tree sorts objects by retained heap. This is the right place to find objects retaining a large number of child objects.

Questions to ask:

- Which object has the largest retained heap?
- Does it belong to an application class or a JDK class?
- Is it held by a static field, cache, listener, or thread?
- Are the child objects data that should have already ended their lifecycle?
- Is an old class loader holding many classes or instances?

### Path to GC Roots

Once you find a suspicious object, open Path to GC Roots to view the reference chain from a GC root to the object.

Example:

~~~text
GC Root
   |
   v
LeakyCache.CACHE (static field)
   |
   v
ArrayList
   |
   v
Object[] elementData
   |
   +----> byte[16384]
   +----> byte[16384]
   +----> byte[16384]
~~~

The reference path shows that a static collection is still holding the buffers. If the collection has no size limit or eviction mechanism, the number of objects can grow with the number of requests.

Not every retained object is a leak. Bounded caches, connection pools, or shared objects may be kept alive intentionally. Cross-check against business requirements and the expected lifecycle.

### Leak Suspects Report

The Leak Suspects Report runs heuristics to suggest areas that might be causing a memory leak. It is a useful starting point, not a final conclusion.

Always verify suspects using the dominator tree, retained heap, and path to GC roots.

## 8. Workflow for Analyzing a Heap Dump

An effective workflow:

1. **Identify the symptom**: continuous heap growth, GC failing to reclaim much memory, or an OOME.
2. **Collect a snapshot**: generate an HPROF dump under high load or right after reproducing the issue.
3. **Open in MAT**: confirm the dump parses successfully.
4. **Check the overview**: inspect total objects, classes, and heap size.
5. **Check the histogram**: look for classes with abnormal instance counts or shallow heap.
6. **Check Top Consumers**: identify packages/class loaders consuming the most memory.
7. **Open Dominator Tree**: find objects with large retained heap.
8. **Trace GC roots**: identify the references keeping the objects alive.
9. **Cross-check source code**: look for static collections, listeners, caches, thread locals, or uncleaned lifecycles.
10. **Propose a fix**: bound caches, unregister listeners, remove references, or close lifecycles properly.
11. **Reproduce and test**: run the same workload after the fix.
12. **Collect a new snapshot**: verify retained heap no longer grows abnormally.

Do not stop at finding a class with many instances. You must find the reference keeping the objects alive and determine why that reference exists.

## 9. Comparing Multiple Heap Dumps to Find Trends

A single snapshot shows the state at one moment. Two or more snapshots taken under comparable conditions can help identify growth trends.

Example:

| Snapshot | Requests processed | Cache entries | Cache retained heap |
|---|---:|---:|---:|
| dump-1 | 1,000 | 1,000 | 20 MB |
| dump-2 | 2,000 | 2,000 | 40 MB |
| dump-3 | 3,000 | 3,000 | 60 MB |

The table only illustrates an unbounded cache scenario. Actual numbers must be taken from the dumps using the same query in MAT.

### How to Compare Reliably

- Capture dumps after the same warm-up phase.
- Use the same workload or the same number of requests.
- Record the timestamp, heap size, GC behavior, and runtime configuration.
- Use the same dump generation method, especially regarding how unreachable objects are handled.
- Compare instance count, shallow heap, retained heap, and dominators.
- Look for classes that grow with request count rather than fluctuating randomly with load.
- Check whether objects remain reachable through the same root chain.

When using `jcmd GC.heap_dump` with default options, the command requests a full GC before dumping. This keeps the snapshot focused on objects still reachable after GC. If `-all` is used, the snapshot also includes unreachable objects, so it should not be compared directly with a default dump without accounting for this difference.

### Do Not Confuse Allocation Rate with a Memory Leak

An application can allocate many temporary objects while GC still reclaims them. A high allocation rate causes GC pressure, but it is not necessarily a memory leak.

A stronger indicator of a leak is a post-GC live set that grows steadily while old objects continue to be held by unnecessary references.

## 10. Java 17+ Example: Creating a Cache That Retains Objects Without Bounds

This example simulates a cache holding byte arrays in a static collection with no eviction mechanism. The objects remain reachable, so GC cannot reclaim them.

Structure:

~~~text
project/
  src/
    com/acme/LeakyCache.java
  out/
~~~

File `src/com/acme/LeakyCache.java`:

~~~java
package com.acme;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public final class LeakyCache {

    private static final List<byte[]> CACHE = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 2000; i++) {
            CACHE.add(new byte[16 * 1024]);
        }

        System.out.println("READY objects=" + CACHE.size());
        new CountDownLatch(1).await();
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 -d out src/com/acme/LeakyCache.java
~~~

Run with a bounded heap for practice:

~~~bash
java -Xms128m -Xmx128m -cp out com.acme.LeakyCache
~~~

Exact stdout:

~~~text
READY objects=2000
~~~

The application holds 2,000 byte arrays in a static list and waits indefinitely so the JVM does not exit. This intentionally retains objects to simulate an unbounded cache.

### Generating the Dump

Open a second terminal and find the PID:

~~~bash
jcmd -l
~~~

Suppose the PID is `2125`:

~~~bash
jcmd 2125 GC.heap_dump leaky-cache.hprof
~~~

### Analyzing in MAT

1. Open `leaky-cache.hprof`.
2. Run Histogram and locate the `byte[]` class.
3. Open Dominator Tree.
4. Find `LeakyCache` or the `ArrayList` with a large retained heap.
5. Open Path to GC Roots for one of the `byte[]` objects.
6. Confirm the reference path goes through the static field `CACHE`.
7. Propose bounding the cache or removing references when entries expire.

After analysis, return to the terminal running `LeakyCache` and press Ctrl+C to stop the test process.

Analysis results may vary slightly depending on the JDK, object layout, and MAT version. The core reference path to look for is static `CACHE` holding the backing array, which in turn keeps the `byte[]` objects alive.

## 11. Distinguishing Memory Leaks, Valid Caches, and Allocation Pressure

| Phenomenon | Symptoms | Investigation Approach |
|---|---|---|
| Memory leak | Live set grows over time and unneeded objects remain reachable | Dominator Tree, Path to GC Roots |
| Valid cache | Objects are retained intentionally with bounds/eviction | Check cache policy, TTL, maximum size |
| Allocation pressure | Many temporary objects, frequent GC, but stable post-GC live set | JFR allocation events, allocation profile |
| ClassLoader leak | Old class loaders and their classes remain reachable | Class Loader Statistics, Dominator Tree |
| Native memory leak | RSS grows while Java heap does not grow correspondingly | NMT, OS tools, JNI/native profiler |
| Direct buffer accumulation | `DirectByteBuffer` or native buffers grow | Buffer pool metrics, native memory, reference lifecycle |

Heap dumps are very strong for finding live objects and reference chains. They do not replace allocation profiling or native memory analysis.

## 12. Heap Dumps and Class Histograms

A histogram is a summary of object counts by class. It is usually much smaller than a heap dump and can serve as an initial screening step.

Using `jcmd`:

~~~bash
jcmd 2125 GC.class_histogram
~~~

JDK 26 classifies `GC.class_histogram` as having a High impact because its cost depends on heap size and contents.

A histogram shows which classes have many instances or large shallow heap. It does not provide the full object graph like a heap dump.

Using legacy `jmap`:

~~~bash
jmap -histo 2125
jmap -histo:live 2125
~~~

To determine why objects are being kept alive, you need a heap dump and an object reference analysis tool.

## 13. Heap Dumps from Core Dumps After a Crash

When the JVM has crashed and produced a core dump, you can use the Serviceability Agent via `jhsdb` for postmortem analysis.

Generate an HPROF heap dump from a core file:

~~~bash
jhsdb jmap \
  --exe /path/to/java \
  --core /path/to/core \
  --binaryheap \
  --dumpfile heap-from-core.hprof
~~~

Where:

- `--exe` specifies the Java executable corresponding to the core dump.
- `--core` specifies the core file.
- `--binaryheap` requests dumping the Java heap in HPROF format.
- `--dumpfile` sets the output file name.

Once generated, open the HPROF file in MAT like a regular heap dump.

### Warnings When Using jhsdb

`jhsdb` is an experimental and unsupported tool. Oracle warns that attaching `jhsdb` to a live process can cause the process to hang and potentially crash when the debugger detaches.

For a running JVM, prefer `jcmd`. Use `jhsdb` in postmortem mode with the matching executable and core dump.

Both core dumps and heap dumps can contain sensitive data. Protect both under the same access and retention policies.

## 14. Common Errors When Generating and Analyzing Heap Dumps

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `jcmd` cannot find process | Wrong PID or JVM is in a different container namespace | Use `jcmd -l` or `ps` in the right namespace |
| Attach failed | Different user account or attach mechanism disabled | Check OS permissions and `DisableAttachMechanism` |
| `GC.heap_dump` runs slowly | Large heap or large object graph | Assess pause duration and do not send duplicate commands |
| Dump fails due to insufficient disk | Dump file requires large disk space | Check free space and choose a sufficiently large volume |
| Cannot write file | Process lacks write permission on directory | Choose a directory with write permissions |
| MAT reports parse error | Incomplete, corrupted, or unsupported dump format | Verify the file, JDK, and MAT version; regenerate if needed |
| MAT runs out of memory | Dump has too many objects or MAT heap is too small | Use a 64-bit machine and increase MAT's `-Xmx` |
| No leak found in histogram | Many small objects or issue is in the reference chain | Use Dominator Tree and Path to GC Roots |
| Small retained heap but large shallow heap | Many independent objects or shared references | Inspect histogram and dominator relationships |
| Heap dump does not explain RSS growth | Memory growth is outside the Java heap | Check NMT, direct buffers, JNI, and OS metrics |
| Two snapshots cannot be compared | Different workloads, GC, or dump methods | Standardize conditions and collection method |
| `jmap` does not work on newer JDKs | `jmap` is experimental/unsupported | Switch to `jcmd GC.heap_dump` |
| Core dump cannot be analyzed | Mismatched executable or core file | Use the exact binary and core from the same process/JDK |
| Temporary objects missing in default dump | Full GC reclaimed unreachable objects | Use `-all` when specifically inspecting unreachable objects |

## 15. Protecting Heap Dumps in Production

A heap dump can contain almost all data the application currently holds in memory:

- Access tokens and sessions.
- Passwords or misconfigured secrets.
- Request and response payloads.
- Customer data.
- Personal information.
- Keys or sensitive data stored in objects.
- SQL queries, caches, and business data.

Operational principles:

1. Collect only when there is a clear diagnostic purpose.
2. Verify the target JVM and PID.
3. Assess pause impact and the High impact level before running.
4. Check available disk space.
5. Write to a directory accessible only to authorized groups.
6. Never store dumps in a web root or public directory.
7. Encrypt when storing or transferring according to organizational policy.
8. Never upload heap dumps to public sharing services.
9. Enforce retention limits and securely delete files after investigation.
10. Record who collected it, timestamp, PID, JDK, and storage location.

Heap dumps are far more sensitive than regular logs. Read permissions on dump files must be strictly controlled.

## 16. Heap Dump Analysis Checklist

- [ ] Identify the symptom and analysis goal.
- [ ] Confirm the target JDK, JVM, and PID.
- [ ] Check attach permissions and the attach mechanism.
- [ ] Estimate heap dump size and available disk space.
- [ ] Choose `jcmd GC.heap_dump` for a running JVM.
- [ ] Use `jmap` only when maintaining legacy workflows.
- [ ] Decide whether unreachable objects need to be dumped with `-all`.
- [ ] Protect the HPROF file according to data security policies.
- [ ] Open the dump in MAT and confirm parsing completes.
- [ ] Check overview, histogram, and top consumers.
- [ ] Use Dominator Tree to find large retained heaps.
- [ ] Use Path to GC Roots to find references keeping objects alive.
- [ ] Cross-check against object lifecycles in source code.
- [ ] Compare snapshots under equivalent workloads.
- [ ] Use JFR if you need allocation trends or allocation sites.
- [ ] Use NMT/OS tools if native memory is suspected.
- [ ] Test the fix and verify that the live set stabilizes.

## 17. Key Takeaways

- A heap dump is a snapshot of the object graph on the Java heap at a point in time.
- HPROF is the standard binary format for HotSpot heap dumps.
- `jcmd GC.heap_dump` is Oracle's recommended option for running JVMs; the command has a High impact level.
- `GC.heap_dump` requests a full GC by default; `-all` dumps unreachable objects as well and does not request a full GC by default.
- `jmap` is still in JDK 26 but is experimental/unsupported; prefer `jcmd` for new diagnostics.
- `-dump:live,format=b,file=...` creates an HPROF containing only live objects using `jmap`.
- `-XX:+HeapDumpOnOutOfMemoryError` automatically generates a dump on Java heap exhaustion; `HeapDumpPath` specifies the file location.
- Shallow heap is the size of the object itself; retained heap is the memory that can be reclaimed if the object becomes unreachable based on dominator relationships.
- Dominator Tree finds objects keeping many other objects alive; Path to GC Roots reveals the reference chain.
- Histograms show classes and object counts, but cannot identify the root cause of a leak on their own.
- Comparing multiple snapshots under comparable conditions helps identify a live set growing over time.
- Heap dumps do not fully explain native memory, direct buffer payloads, thread stacks, or RSS.
- MAT Leak Suspects is a starting hint; always confirm with dominators, retained heap, and GC roots.
- Heap dumps can contain secrets and user data; protect dump files like sensitive production data.

## Official References

- [The jmap Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jmap.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Troubleshooting Memory Leaks — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html)
- [Diagnostic Tools — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [The jhsdb Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jhsdb.html)
- [Eclipse Memory Analyzer — Finding Memory Leak](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/findingmemoryleak.html)
- [Eclipse Memory Analyzer — Dominator Tree](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html)