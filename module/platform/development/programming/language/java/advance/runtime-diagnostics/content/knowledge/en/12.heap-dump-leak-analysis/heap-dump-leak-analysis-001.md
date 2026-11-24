# 12.1 What a Heap Dump Stores and How It Differs from a Class Histogram or Allocation Recording

## Objectives

After this lesson, you will be able to answer three distinct questions when analyzing Java memory: **which objects are currently in the heap, which classes occupy the most space, and which code paths continuously create new objects?** You will also understand why a high allocation chart does not prove a memory leak, and why a histogram alone is not enough to determine what is keeping objects alive.

## 1. Distinguishing the Three Perspectives

- **Heap dump:** a point-in-time snapshot of the heap memory structure. It lets you navigate from objects to fields, references, retention chains, and GC roots; well-suited for investigating **retention** (objects still being held alive).
- **Class histogram:** a point-in-time summary table, typically showing **class name, instance count, and total shallow bytes**. Well-suited for spotting abnormally growing object groups and narrowing down suspects quickly; lacks reference graph details.
- **Allocation recording/profile:** data collected over **a time interval**, typically allocation events or samples from JFR/profilers, which may include class, thread, call stack, and estimated weight/bytes. Well-suited for finding **allocation hot spots** (call paths creating many objects), though it does not by itself tell you which objects remain alive.

The key point: **allocation is when an object is created; retention is when an object remains reachable and has not been reclaimed.** An application can allocate very rapidly while GC reclaims well, or allocate relatively little yet retain large amounts of data that are no longer needed.

| Question to answer | Preferred tool | Why |
| --- | --- | --- |
| Which objects and references are in the heap at capture time? | Heap dump | Contains per-instance data and links between them |
| Which classes have many instances / occupy many shallow bytes? | Class histogram | Fast per-class aggregation |
| Which object keeps a set of other objects from being collected by GC? | Heap dump + dominator tree + path to GC roots | Traces retention relationships |
| Which method is creating most of the objects or allocated bytes? | JFR/allocation profiler | Captures event samples and allocation stacks over time |
| Is there a sustained memory leak? | Trend monitoring + heap dumps at multiple points + GC info | A single snapshot only shows state; persistent retention growth must be proven |

## 2. What Does a Heap Dump Actually Store?

On HotSpot/OpenJDK, a heap dump is typically generated in the **HPROF** format. It describes the state of the Java heap at the time of collection; it is a set of objects and their reference relationships, not merely a RAM usage report.

Core groups of information:

1. **Object instances and arrays:** the type/class of the object, recorded primitive field data, reference fields pointing to other objects; arrays include element type, length, and corresponding elements/values. For example, a list object may point to a backing array, and then to its elements.
2. **Class metadata for decoding the heap:** class names, class hierarchy, instance/static fields, and links to class loaders; this allows analysis tools to map objects to their proper types and identify which class loader holds the data. This does not mean capturing all bytecode, all Metaspace metadata, or all JVM internal data.
3. **References and GC root information exported by the format/VM:** for example, information related to stack local variables, static fields, threads, and JNI handles. Tools like Eclipse MAT use these to compute **Paths to GC Roots**, showing why an object remains reachable.
4. **Sizes and counts:** the analysis tool derives or computes the shallow size of each object and related object sets, then computes retained size based on the reference graph. These are analysis results rather than precomputed totals stored in a single column inside the dump.

### Shallow size, retained size, and GC root

- **Shallow size**: the memory of the object itself, such as the shell of a Map or array object (excluding all objects it references).
- **Retained size**: the total memory of objects that would become unreachable if the object under consideration were removed from the retention graph, according to the dominator model. It represents memory retention impact, not just the size of the parent object.
- **GC root**: a starting point that the JVM considers live when tracing reachable objects; following reference edges from a root explains why an object has not been collected.

For example, a cache Map might have a shallow size of only a few dozen bytes, yet hold hundreds of thousands of entries and byte arrays. The **retained size** of the object holding the cache can be huge. A class histogram may show many byte arrays; **a heap dump is what lets you trace the reference path back** from those arrays to the cache or static field holding them.

### What a heap dump does not provide on its own

- Not a history: a standard dump **does not store exact creation timestamps, allocation rates, the call stack that created each object, or a list of objects that once existed and were already reclaimed by GC**.
- Not a full-process snapshot: it does not directly and fully describe **native/off-heap memory** such as direct buffer native payloads, thread native stacks, Code Cache, Metaspace, mmap, or sockets/file descriptors. A Java object representing a native resource may be visible, but the underlying native memory is not necessarily in the heap dump.
- Does not automatically prove a "leak": objects alive at capture time may be completely legitimate. You must compare against expected lifecycle, trends over time, GC behavior, and retention paths.
- Not a GC-neutral snapshot of pre-GC state: with the HotSpot command shown later, by default the JVM **requests a Full GC before writing the heap dump**; the `-all` option changes the set of included objects and omits that Full GC request. Therefore, the two capture modes can yield different results.

**Sensitive data notice:** a heap dump can contain strings, tokens, request payloads, customer data, and application state in readable form. Control access permissions, storage locations, retention periods, and file sharing.

## 3. What Does a Class Histogram Record and Omit?

A histogram typically has one row per class or array type, containing rank, **#instances**, **#bytes**, and class name. Illustrative example (hypothetical numbers):

~~~text
 num     #instances       #bytes  class name
   1:         10000     11000000  [B
   2:          2000       480000  java.lang.String
   3:           100        12000  java.util.HashMap
~~~

In JVM class name notation, **[B** is a byte array (`byte[]`). **#bytes** represents the total shallow size of the instances in that row, not their retained size. The summary column **does not tell you which request the 10,000 byte arrays came from**, why they are still alive, or which `HashMap` holds those arrays.

A histogram is useful when:
- Quickly comparing two points in time **under the same measurement conditions**: are the instance count/bytes of a class increasing?
- Identifying suspects such as `byte[]`, `char[]`, `String`, Map entries, or objects from application packages.
- Getting a concise overview before creating and analyzing a large dump file.

Important limitations:
- No per-object references and no paths to GC roots or dominator tree.
- No call stacks or allocation rate per second.
- A sharp increase in a class can be a valid cache, increased traffic, application warm-up, or large input payloads; **it is not sufficient to prove a leak**.
- A histogram taken directly from the live JVM at one time and a histogram built from a dump file can differ, especially when the object set and GC conditions are not identical.

## 4. What Does an Allocation Recording Store and How Does It Differ from a Heap Dump?

An **allocation recording** observes *object creation activity* over a measurement window. With Java Flight Recorder (JFR), events/samples such as **jdk.ObjectAllocationSample** can provide the object type, thread, stack trace, and **weight** (byte weight used to estimate allocation pressure). Other detailed event types, such as **jdk.ObjectAllocationInNewTLAB** or **jdk.ObjectAllocationOutsideTLAB**, depend on recording configuration and measurement overhead. Other profilers may use their own sampling mechanisms.

Why sample? Recording every single allocation in a busy system can incur very high overhead. Therefore, **sampling results are estimates**, not a guaranteed log containing every object. Do not read the event count as the actual total number of allocations when the tool is sampling.

An allocation recording answers:
- Which call stack/method creates many `byte[]` arrays or temporary objects?
- During the measurement window, how do the allocation rate and allocating class groups fluctuate?
- Which threads or request paths create allocation pressure leading to frequent GCs?

It **does not by itself answer** whether those objects are still alive, which root is holding them, or whether they were reclaimed by GC right after the event. A JFR file contains many event types depending on configuration; it is not an HPROF heap dump either. Another event type, **OldObjectSample**, can assist in investigating long-lived objects and paths to GC roots if the appropriate feature is enabled, but it is only sampled and does not replace the full object graph of a heap dump.

Practical contrast examples:

- **Scenario A — creating many temporary objects:** every request allocates thousands of buffers and drops references after sending the response. JFR may report an allocation hot spot; after GC, a heap dump/histogram may contain very few of those buffers. The issue is **allocation pressure/GC overhead**, not necessarily a leak.
- **Scenario B — unbounded cache retention:** requests add only a few objects into a static `Map` with no eviction policy. Over time, retained heap grows; a heap dump shows the `Map` holding data, and a histogram shows which classes accumulate. JFR can help locate where they were originally allocated, but does not directly show current retention relationships.

## 5. Tool Selection Comparison Table

| Criterion | Heap dump (HPROF) | Class histogram | Allocation recording (e.g., JFR) |
| --- | --- | --- | --- |
| Nature | Snapshot of object graph | Point-in-time class aggregation | Events/samples emitted over a time window |
| Unit of observation | Individual instances and references | Class, instance count, shallow bytes | Allocation/sample, class, stack/thread, weight |
| Finds what keeps objects alive | **Yes**, via graph, GC roots/dominator | **No** | Not directly with standard allocation samples |
| Finds call stack causing allocation | Usually **no** | **No** | **Possible**, if stack capture is configured |
| Sees allocated objects already reclaimed by GC | No in a standard live dump | No in a standard live histogram | **Possible**, if events are captured upon creation |
| Tracking changes over time | Compare multiple dumps; a single dump has no timeline | Compare multiple histograms | Well-suited for timeline/rate over recording period |
| Typical cost | High impact, may cause Full GC/pause and very large files | Can incur pause/time scanning the heap | Depends on events and config; sampled profiles are usually lighter |
| Best suited for | Finding retention/leaks and retaining roots | Narrowing down classes and count fluctuations | Finding allocation hot spots/GC pressure |

**Do not equate heap usage with process RSS:** the Java heap is only one part of process memory. If RSS grows while Java heap after GC remains stable, investigate native/off-heap memory rather than inferring a leak from a histogram.

## 6. Java 17+ Hands-On: High Allocation Alongside Few Retained Objects

The following program creates 20,000 byte arrays, continuously replacing them via a `volatile` field, and then retains 500 arrays in a `List`. The replaced arrays become eligible for GC. JIT, GC, library classes, and capture timing will vary the exact counts observed in practice.

Save the file **HeapSnapshotDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class HeapSnapshotDemo {
    private static volatile byte[] mostRecent;
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 20_000; i++) {
            mostRecent = new byte[1_024];
        }

        for (int i = 0; i < 500; i++) {
            RETAINED.add(new byte[1_024]);
        }

        System.out.println("Retained arrays: " + RETAINED.size());
        System.out.println("Ready for diagnostics");
        Thread.sleep(180_000L);
    }
}
~~~

Compile and run (JDK 17+, using HotSpot as an example):

~~~bash
javac HeapSnapshotDemo.java
java -Xmx128m -XX:StartFlightRecording=filename=alloc.jfr,settings=profile,dumponexit=true HeapSnapshotDemo
~~~

The two deterministic stdout lines from the program are:

~~~text
Retained arrays: 500
Ready for diagnostics
~~~

In a second terminal, find the running Java PID and capture the different measurements:

~~~bash
jcmd -l
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump heap.hprof
~~~

- **Histogram** lets you inspect total `byte[]` present at measurement time, but there are also `byte[]` created by the JDK itself or libraries, so do not expect exactly 500.
- **Heap dump** opened in Eclipse Memory Analyzer (MAT) lets you drill down from `byte[]` to the `List` or other roots. `RETAINED` is a static field holding a reference to the `List`; `mostRecent` holds the single latest array.
- **JFR** was enabled from startup. After the program exits, use the command below to inspect allocation samples if the actual recording contains the corresponding events:

~~~bash
jfr print --events jdk.ObjectAllocationSample alloc.jfr
~~~

JFR sample data can point toward where arrays are created; the exact event count is **not fixed** and will not be "20,500 objects" due to sampling, other allocations, and JVM optimizations. This demonstrates **information differences**, not a test asserting that all tools must return identical totals.

If you need a dump when the heap runs out of memory, you can preconfigure the JVM with **-XX:+HeapDumpOnOutOfMemoryError** and **-XX:HeapDumpPath=/path/to/dump.hprof**. Ensure sufficient disk space, write permissions, and file protection procedures.

## 7. Practical Investigation Workflow

### When post-GC heap continues rising and a leak is suspected

1. Verify the symptom using heap/GC metrics over time and traffic state. Distinguish pre-GC peak usage from remaining usage **after meaningful GC cycles**.
2. Take histograms at comparable points in time; check which class groups are growing in instances or shallow bytes. This is only the suspect-selection step.
3. When you need to know why objects stay alive, capture a **heap dump** at an appropriate moment; if possible, collect another dump under equivalent load and GC conditions for comparison.
4. Open in **Eclipse MAT**: inspect Histogram, Dominator Tree, or Top Consumers, then **Paths to GC Roots** for suspicious objects. Trace back to the static field, cache, queue, listener, collection, or class loader holding them.
5. Compare against the intended lifecycle: are the objects alive due to a valid cache, an unfinished job, or missing remove/evict/close/unregister logic? Fix the lifecycle management and re-measure.

**Reasoning example:** histogram shows `byte[]` count rising → dump identifies `byte[]` belonging to many cache values → Paths to GC Roots connects the cache to a static field → inspect the eviction policy. A leak conclusion is only substantiated if data that should have expired is being retained indefinitely.

### When GC runs frequently and throughput drops, but post-GC heap is stable

1. Capture a **JFR allocation profile** over a period with representative load, inspecting class groups, allocation rate, and call stacks.
2. Optimize appropriate hot spots: avoid unnecessary repeated buffer creation, eliminate redundant intermediates, or consider batching/pooling where beneficial.
3. Re-measure allocation rate, latency, and GC after the change. Do not conclude "no leak" from just a few minutes of recording; evaluate retention separately if signs of accumulation appear.

### HotSpot diagnostic commands and operational notes

~~~bash
# Replace PID with the target process and path with a location that has sufficient disk space.
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump /safe-path/heap.hprof

# With -all, includes unreachable objects; does not request a Full GC before dumping.
jcmd <PID> GC.heap_dump -all /safe-path/all-objects.hprof

# Record JFR for 2 minutes; actual events depend on profile and JDK.
jcmd <PID> JFR.start name=alloc settings=profile duration=2m filename=/safe-path/alloc.jfr
~~~

According to JDK 21 **jcmd** documentation, `GC.heap_dump` requests a Full GC by default unless **-all** is specified; both `GC.class_histogram` and heap dump are classified as high-impact. Taking a dump can pause the application for a long time and produce huge files. Execute at an appropriate time, verify disk space and permissions, and avoid running multiple heavy tasks concurrently on a production JVM. Flags and command support depend on the JDK/VM; examples here apply to HotSpot/OpenJDK.

**-all does not mean "more accurate data for concluding a leak."** It includes unreachable objects awaiting GC collection, so the object set differs from a default live dump. When comparing two measurements, document the capture method and GC conditions.

## 8. Common Reasoning Mistakes

1. **"The histogram shows 2 GB of `byte[]`, so `byte[]` must be leaking."** False: that is total shallow bytes at capture time; it does not tell who holds them, why they are held, or whether they are growing abnormally.
2. **"JFR records many allocations, so the heap will keep growing."** False: a high allocation rate can coexist with a stable post-GC heap if objects are very short-lived.
3. **"The largest object in the heap is the root cause."** Not necessarily: a small object like a cache holder can retain an entire graph of large objects. Inspect dominators and retained size.
4. **"A heap dump contains the allocation stack of every object."** Usually false for standard HPROF dumps; use an allocation profiler/JFR if you need creation call paths.
5. **"A single heap dump proves a leak."** Insufficient: you must compare against expected lifecycle, trends, and retention paths.
6. **"Freeing Java heap will immediately reduce RSS."** False: the JVM may retain committed heap regions, and RSS also includes native memory; the two metrics are not identical.
7. **"With the `-all` flag, all numbers across tools must match."** False: differences in timing, GC behavior, object scope, sampling, and overhead mean totals cannot be forced to match.

## 9. Self-Check on Tool Selection

- Need to know **which cache holds 500,000 old objects**: capture a heap dump, inspect the dominator tree and paths to GC roots; a histogram only helps locate the class.
- Need to know **which method allocates 1 GB of temporary objects per minute**: capture a JFR/allocation profile with stack traces, analyzing timeline and sample weights.
- Need to **see which classes are growing rapidly in count** before deciding to dump: compare class histograms at multiple times under the same conditions.
- Need to investigate **RSS rising while post-GC Java heap is flat**: add native/off-heap memory analysis; the three Java-object-focused tools do not fully explain every process memory region.

### Reference Documentation

- [Oracle JDK 21 — jcmd: GC.heap_dump, GC.class_histogram, and JFR.start](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — jfr command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle — Troubleshoot Memory Leaks and OldObjectSample](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html)
- [Eclipse Memory Analyzer — Finding Memory Leak](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/findingmemoryleak.html)
