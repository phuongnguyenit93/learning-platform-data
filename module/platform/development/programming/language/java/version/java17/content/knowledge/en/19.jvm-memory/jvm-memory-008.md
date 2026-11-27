# Distinguishing Heap, Metaspace, and Native Memory Leaks in Java 17

A Java process can grow in memory consumption even when the heap is not full. Conversely, the heap can fill up even when the OS still has plenty of RAM. To diagnose accurately, you must distinguish **Java heap**, **metaspace**, and other **native memory** regions. Remember that metaspace is itself allocated from the process's native memory.

- **Heap leak:** objects no longer needed by business logic are still held by references reachable from a GC root.
- **Metaspace leak:** class metadata persists because the class loader owning those classes is still kept alive.
- **Native memory growth/leak:** off-heap memory grows due to thread stacks, direct buffers, JNI/native libraries, the code cache, or internal JVM structures.

This lesson explains symptoms, causes, JVM and OS metrics, and diagnostic tools still current in Java 17.

## 1. Memory map of a Java process

~~~text
Java Process
|
+-- Java heap
|   +-- Objects and arrays
|   +-- Instance data
|
+-- Native memory
|   +-- Metaspace: class metadata
|   +-- Thread stacks
|   +-- Direct buffers / NIO
|   +-- JIT code cache
|   +-- GC and JVM internal structures
|   +-- JNI and native libraries
|
+-- Memory-mapped regions and OS-managed areas
~~~

This is a conceptual diagram, not an exact physical address layout. Regions may be reserved or committed differently; JVM and OS tools may also categorize them differently.

### 1.1. The heap holds application objects

~~~java
User user = new User("An");
byte[] payload = new byte[1024 * 1024];
~~~

These objects and arrays are normally allocated on the heap. The Garbage Collector (GC) reclaims heap objects when they are no longer reachable from a GC root.

The heap is commonly bounded with:

~~~bash
java -Xms512m -Xmx2g -jar app.jar
~~~

- `-Xms`: initial heap size.
- `-Xmx`: maximum heap limit.

`-Xmx` is not the total memory limit of the process. Metaspace, thread stacks, direct buffers, the code cache, and other native regions still consume memory outside the heap.

### 1.2. Metaspace stores class metadata

Metaspace stores metadata used by the JVM to manage loaded classes, methods, fields, runtime constant pools, and type-related information.

Metaspace resides in **native memory**, not inside the Java heap. Therefore:

- The heap can have plenty of free space while metaspace runs out.
- Raising `-Xmx` does not directly resolve a metaspace exhaustion error.
- Live class loaders can retain metadata for the classes they loaded.
- When a class loader becomes eligible for collection and class unloading runs, its metadata can be freed.

Metaspace can be bounded with `-XX:MaxMetaspaceSize`. Setting the limit too low can trigger an error even when the application has no leak.

### 1.3. Native memory is broader than metaspace

Native memory is memory used by the process outside the heap. Beyond metaspace, notable regions include:

- Stacks of individual platform threads.
- Direct byte buffers.
- JIT compiler and code cache.
- Internal JVM, GC, and symbol table structures.
- Memory allocated by JNI or native libraries.
- Certain memory-mapped files or I/O areas.

Therefore, **metaspace is part of native memory**, while native memory is the broader concept.

## 2. What does a memory leak mean?

A memory leak occurs when a program continues holding memory it no longer needs for actual work. That memory cannot be reused because references or management mechanisms keep it pinned.

In Java, GC automatically reclaims objects that are no longer reachable. However, GC cannot know on its own which objects are "no longer useful" in business terms. If an object stays reachable via a static field, cache, listener, or thread, GC must treat it as alive.

### 2.1. Distinguishing a leak from a high allocation rate

| Observation | Description | Common symptoms |
|---|---|---|
| High allocation rate | Many objects are created but quickly become unreachable | Frequent GC; post-GC heap drops sharply |
| Large live set | Many objects remain needed for current state | Post-GC heap is high but stable for a given load |
| Heap leak | Unneeded objects remain referenced | Post-GC heap climbs steadily across comparable cycles |
| Native memory growth | Native regions grow with threads, buffers, class metadata, or libraries | RSS rises while heap does not grow proportionally |

A traffic spike can legitimately raise heap usage. Never conclude there is a leak from a single memory usage snapshot; watch trends over time and compare at equivalent load.

### 2.2. GC cannot reclaim objects that remain reachable

~~~java
import java.util.ArrayList;
import java.util.List;

public class HeapLeakExample {
    private static final List<byte[]> CACHE = new ArrayList<>();

    public static void retainForever() {
        while (true) {
            CACHE.add(new byte[1024 * 1024]);
        }
    }
}
~~~

Each iteration allocates an approximately 1 MiB array and appends it to the static list. Because the list retains references to all arrays, they stay reachable. GC cannot reclaim them.

This is a leak caused by unbounded data retention logic. The fix is designing data lifecycles:

- Put size bounds on caches.
- Use an appropriate eviction policy.
- Remove data on expiration or session end.
- Do not retain objects longer than business requirements dictate.
- Control registered listeners, callbacks, and tasks.

### 2.3. Common sources of heap leaks

| Reference holder | Example | Remediation |
|---|---|---|
| Static collection | List or Map accumulating objects forever | Bound size, remove elements per lifecycle |
| Unbounded cache | Cache keys growing per request | TTL, maximum size, eviction |
| Unregistered listener | Event source retains an expired object | Call unregister/remove listener |
| ThreadLocal | Thread pool retains previous request values | Call `remove()` upon completion |
| Backlogged queue | Producer outpaces consumer | Backpressure and queue bounds |
| Session or registry | Stale sessions remain in a Map | Expiration and cleanup |
| Callback/future | Closure captures a large object graph | Complete/cancel tasks, drop unneeded references |
| Retained ClassLoader on heap | Registry still holds an old plugin's loader | Clean registries, threads, and context class loaders |

Example using `ThreadLocal` in a thread pool:

~~~java
private static final ThreadLocal<RequestContext> CONTEXT =
        new ThreadLocal<>();

void handle(Request request) {
    try {
        CONTEXT.set(new RequestContext(request));
        process(request);
    } finally {
        CONTEXT.remove();
    }
}
~~~

Thread pools reuse threads after requests finish. Without removing the value, a thread can retain `RequestContext` and its object graph longer than intended.

## 3. Identifying the three problem types by symptoms

| Observation | Heap leak | Metaspace leak | Native memory growth |
|---|---|---|---|
| Post-GC heap used | Typically climbs steadily | May stay stable | May stay stable |
| Loaded class count | May stay stable | Typically climbs or fails to unload | May stay stable |
| Class loader count | May stay stable | May grow continuously | May grow if loader-related |
| Thread count | May stay stable | May stay stable | May grow if stacks are the source |
| Direct buffer memory | Not necessarily rising | Not necessarily rising | May rise |
| Process RSS | May rise | May rise | May rise even when heap is stable |
| Typical OOME | `Java heap space` | `Metaspace` | `Direct buffer memory`, `unable to create native thread` |

This table guides investigation, not an absolute rule. A heap leak can pin a class loader and prevent metaspace reclamation; a native library leak may not appear in a heap dump at all.

## 4. Investigating a heap leak

### 4.1. Watching post-GC heap

A valuable indicator is how much heap remains used after GC has had a chance to reclaim unreachable objects.

If heap used climbs across multiple GC cycles under comparable traffic and business state, investigate which objects are being retained.

Do not look solely at instantaneous heap used. While an application runs, heap rises naturally from allocations before GC runs.

### 4.2. Enabling GC logs in Java 17

Java 17 uses Unified JVM Logging:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

GC logs help observe:

- GC timestamps and types.
- Heap before and after GC.
- GC frequency.
- Pause times.
- Heap reclaimed per cycle.

If post-GC heap keeps trending upward across equivalent load phases, it signals a need to inspect live objects and retention paths.

### 4.3. Using jcmd for histograms and heap dumps

Find the Java process PID and run `jcmd`:

~~~bash
jcmd <pid> GC.class_histogram
~~~

A histogram shows instance counts and total bytes by class. Comparing multiple snapshots can highlight classes growing abnormally.

Capture a heap dump:

~~~bash
jcmd <pid> GC.heap_dump filename=heap.hprof
~~~

You can open the heap dump with Eclipse Memory Analyzer (MAT) or a compatible VisualVM. Focus on:

- Dominator tree.
- Retained heap.
- Path to GC roots.
- Collections or caches retaining many objects.
- Instances that grew sharply between two snapshots.

Capturing a heap dump can pause the application and consume substantial disk space. Dump files can also contain sensitive data; store and share them in line with your system's data protection policies.

### 4.4. Retained heap and dominators

Shallow size is an object's own direct size. Retained heap is the memory that would be freed if that object no longer kept other objects alive.

A cache Map object might take only a few KB itself while retaining hundreds of MB of objects via its entries. When hunting leaks, retained heap and GC root paths are usually far more informative than shallow size alone.

## 5. Metaspace leaks and class loader lifecycles

Metaspace stores metadata for classes loaded by the JVM. Every class is tied to the class loader that defined it. As long as that class loader remains reachable, the JVM cannot simply free metadata for the classes it defined.

In long-running applications—especially those with plugins, hot reload, application servers, or dynamic class generation—class loaders can be retained after a module has stopped.

### 5.1. A class loader leak scenario

1. The application creates a new class loader to load a plugin.
2. The plugin is used.
3. The application logically stops the plugin.
4. A static registry still holds a reference to a plugin class or its class loader.
5. The class loader never becomes unreachable, so its metadata cannot be freed.

Common loader retainers:

- Static Maps holding classes, instances, or loaders.
- Threads still executing plugin code.
- Thread context class loaders still pointing to an old loader.
- ThreadLocals holding objects defined by the plugin.
- Uncancelled listeners, executors, timers, or callbacks.
- Framework caches retaining reflection metadata.

### 5.2. Class unloading is not an arbitrary unload operation

The JVM generally reclaims metadata for classes when the defining class loader becomes eligible for collection and class unloading runs. Therefore, clearing one reference to an object instance may not suffice; check every reference path to the class loader.

`URLClassLoader.close()` closes resources opened by the loader, such as JAR file handles. It **does not make the class loader unreachable by itself and does not guarantee classes are unloaded**. The application must still clear live references to the loader.

### 5.3. Signs of metaspace growth

- Metaspace used grows with each plugin deploy/reload.
- Loaded class count climbs steadily.
- Class loader count grows with each module lifecycle.
- Heap dumps show old loaders remain reachable.
- GC fails to reduce metaspace significantly even after old modules stop.

Metaspace growth does not always mean a leak. An application may legitimately load more classes as traffic or features expand; compare against class loader counts, loaded classes, and deployment lifecycles.

### 5.4. Monitoring class loading via JMX

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

ClassLoadingMXBean classLoading =
        ManagementFactory.getClassLoadingMXBean();

System.out.println("Loaded: " + classLoading.getLoadedClassCount());
System.out.println("Total loaded: " + classLoading.getTotalLoadedClassCount());
System.out.println("Unloaded: " + classLoading.getUnloadedClassCount());
~~~

- `getLoadedClassCount`: number of classes currently loaded.
- `getTotalLoadedClassCount`: total classes loaded since JVM startup.
- `getUnloadedClassCount`: total classes unloaded.

If total loaded rises normally while currently loaded keeps climbing across reloads without dropping, investigate class loaders and unloading behavior.

## 6. Bounding and monitoring metaspace

### 6.1. MaxMetaspaceSize

You can set a cap:

~~~bash
java -XX:MaxMetaspaceSize=256m -jar app.jar
~~~

When required metadata exceeds the limit, the JVM may throw:

~~~text
java.lang.OutOfMemoryError: Metaspace
~~~

Do not raise the limit just to mask a leak. If old class loaders remain alive, raising the cap only delays the failure and increases native memory pressure.

### 6.2. MetaspaceSize is not MaxMetaspaceSize

| Option | Meaning |
|---|---|
| `-XX:MetaspaceSize` | Initial threshold related to triggering GC to reclaim class metadata |
| `-XX:MaxMetaspaceSize` | Maximum limit for metaspace |

Do not confuse `MetaspaceSize` with maximum metaspace capacity. Adjusting the GC threshold is no substitute for fixing a class loader leak.

### 6.3. Viewing class loader statistics

You can run:

~~~bash
jcmd <pid> VM.classloader_stats
~~~

This command reports class loader statistics and associated metadata usage. Combine it with loaded/unloaded class counts and heap dumps to find which loaders persist.

You can also inspect memory pools via JMX; exact pool names depend on the JVM:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;

for (MemoryPoolMXBean pool :
        ManagementFactory.getMemoryPoolMXBeans()) {
    System.out.println(
            pool.getName() + " : " + pool.getUsage()
    );
}
~~~

Look for pools named around Metaspace or Compressed Class Space on HotSpot. Do not hardcode pool names if the application must run across multiple JVM vendors.

## 7. Native memory outside metaspace

When heap and metaspace do not explain RSS growth, investigate other native regions.

### 7.1. Thread stacks

Each platform thread has its own stack for frames, local variables, and call state. Many concurrent threads can significantly increase native memory.

Factors to examine:

- Live thread count.
- Configured stack size per thread.
- Actually committed stack memory.
- OS thread/process limits.
- Remaining memory available to the process.

`-Xss` sets the stack size per thread:

~~~bash
java -Xss512k -jar app.jar
~~~

Reducing `-Xss` too aggressively can trigger `StackOverflowError` on deep call stacks. Spawning unbounded threads can trigger `OutOfMemoryError: unable to create native thread`.

Monitor threads:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean threads = ManagementFactory.getThreadMXBean();

System.out.println("Live threads: " + threads.getThreadCount());
System.out.println("Peak threads: " + threads.getPeakThreadCount());
~~~

If thread count keeps climbing, look for thread leaks: unclosed executors, per-request thread creation, stuck tasks, or threads holding resources longer than intended.

### 7.2. Direct ByteBuffer

`ByteBuffer.allocateDirect` allocates memory outside the heap:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(16 * 1024 * 1024);
~~~

Direct buffers can benefit certain I/O paths by avoiding extra copies between heap and native I/O. However, they still consume process memory.

If an application continuously creates direct buffers and holds references, native memory grows even though the heap wrapper objects are relatively small.

Do not allocate a fresh direct buffer for every tiny operation. Consider buffer reuse, bounded pooling, and careful lifecycle management.

Monitor via `BufferPoolMXBean`:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
    System.out.println("Pool: " + pool.getName());
    System.out.println("Count: " + pool.getCount());
    System.out.println("Used: " + pool.getMemoryUsed());
    System.out.println("Capacity: " + pool.getTotalCapacity());
}
~~~

Pools are commonly named `direct` and `mapped` on HotSpot. `getMemoryUsed` and `getTotalCapacity` are distinct metrics; do not mechanically add them to heap used to deduce RSS.

If direct memory is exhausted, you may see:

~~~text
java.lang.OutOfMemoryError: Direct buffer memory
~~~

You can set a direct memory limit with `-XX:MaxDirectMemorySize`, but investigate buffer creation/retention before raising the cap.

### 7.3. JNI and native libraries

Applications may invoke native code via JNI or third-party libraries. Memory allocated by native code is not necessarily visible in heap dumps.

Symptoms:

- RSS climbs while heap used and metaspace stay fairly flat.
- NMT does not account for the full growth.
- The leak appears after invoking a specific native library or driver.
- Memory is freed only when the process exits.

Investigation requires library logs, native profilers, OS tools, and auditing native resource deallocation on the JNI side. Never assume GC will reclaim regions allocated directly by native code.

### 7.4. JIT code cache and internal JVM structures

The JVM uses native memory for the code cache storing JIT-compiled machine code, alongside structures for GC, symbols, compilers, and the runtime.

If the code cache nears capacity, the JVM may log a warning or curtail optimizing compilation; this is not necessarily a heap leak.

Inspect logs, NMT statistics, and JVM metrics before changing code cache settings. Do not blame every unexplained native memory rise on metaspace.

## 8. Comparing types of OutOfMemoryError

The OOME message often provides an initial clue:

| Message | Likely involved region / issue | Investigation direction |
|---|---|---|
| `Java heap space` | Cannot allocate object on the heap | Heap dump, GC logs, retained heap, `-Xmx` |
| `GC overhead limit exceeded` | GC spends too much time while reclaiming very little heap | Heap leak, overly large live set, allocation patterns |
| `Metaspace` | Insufficient space for class metadata or cap hit | Class loaders, class loading/unloading, `MaxMetaspaceSize` |
| `Compressed class space` | Insufficient compressed class space | Class count, class loaders, class space settings |
| `Direct buffer memory` | Cannot allocate more direct buffers | BufferPoolMXBean, buffer lifecycles, direct memory limit |
| `unable to create native thread` | Cannot spawn new native thread | Thread count, stack, OS process/thread limits, RAM |
| `Native memory allocation (malloc) failed` | JVM or native code failed a native allocation | NMT, OS memory, container limit, JNI/native libraries |

One message does not always point to a single cause. For example, `unable to create native thread` can result from OS thread limits even when RAM is plentiful. `Java heap space` can stem from `-Xmx` being too low for a valid live set rather than a leak.

## 9. Measuring heap and non-heap via Java Management APIs

Java provides memory management APIs in `java.lang.management`.

### 9.1. MemoryMXBean

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

MemoryUsage heap = memory.getHeapMemoryUsage();
MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();

System.out.println("Heap used: " + heap.getUsed());
System.out.println("Heap committed: " + heap.getCommitted());
System.out.println("Heap max: " + heap.getMax());

System.out.println("Non-heap used: " + nonHeap.getUsed());
System.out.println("Non-heap committed: " + nonHeap.getCommitted());
System.out.println("Non-heap max: " + nonHeap.getMax());
~~~

Fields:

- `used`: memory currently used in the reported pool/region.
- `committed`: memory the JVM has committed for use.
- `max`: maximum limit if defined; may be undefined.

**Non-heap in MemoryMXBean is not the same as all native memory.** It reflects non-heap pools managed by JVM memory management, such as metaspace and the code cache on HotSpot. Thread stacks, JNI native allocations, and many other regions are not fully represented here.

### 9.2. Inspecting individual MemoryPoolMXBeans

~~~java
for (MemoryPoolMXBean pool :
        ManagementFactory.getMemoryPoolMXBeans()) {

    MemoryUsage usage = pool.getUsage();

    System.out.printf(
            "%s: used=%d, committed=%d, max=%d%n",
            pool.getName(),
            usage == null ? -1 : usage.getUsed(),
            usage == null ? -1 : usage.getCommitted(),
            usage == null ? -1 : usage.getMax()
    );
}
~~~

Pool names and groupings depend on the JVM and collector. Do not assume every JVM returns the exact same pool names.

### 9.3. Do not use Runtime.freeMemory to measure native memory

~~~java
Runtime runtime = Runtime.getRuntime();

long heapUsed = runtime.totalMemory() - runtime.freeMemory();
long heapMax = runtime.maxMemory();
~~~

These figures apply to the JVM heap. They are not total process RAM and exclude metaspace/direct memory/thread stacks/native libraries.

This is a frequent mistake when logging a single "memory used" metric and assuming the whole process uses only that much memory.

## 10. Native Memory Tracking (NMT)

HotSpot offers Native Memory Tracking to monitor many native allocation categories managed by the JVM. NMT must be enabled at JVM startup; it cannot be fully enabled retroactively on a process launched without tracking.

### 10.1. Enabling NMT

Summary mode:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Detail mode:

~~~bash
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

`detail` provides finer breakdown at higher overhead. Choose the tracking level suited to your investigation environment.

### 10.2. Viewing NMT statistics with jcmd

~~~bash
jcmd <pid> VM.native_memory summary
~~~

You can request units:

~~~bash
jcmd <pid> VM.native_memory summary scale=MB
~~~

Create a baseline:

~~~bash
jcmd <pid> VM.native_memory baseline
~~~

After a period or load test, compare:

~~~bash
jcmd <pid> VM.native_memory summary.diff scale=MB
~~~

NMT diff shows which native memory categories grew since the baseline, such as Class, Thread, Code, GC, or others.

### 10.3. NMT has limitations

NMT is helpful, yet it does not account for every byte in the process:

- NMT tracks native allocation categories managed by HotSpot.
- Native allocations by third-party libraries/JNI may not be fully captured.
- NMT does not replace a heap dump.
- NMT does not replace OS tools for viewing RSS, virtual memory, or cgroup usage.
- Tracking carries overhead; detail mode costs more resources than summary.

If RSS climbs while NMT stays nearly flat, investigate native allocations managed outside the JVM along with OS metrics.

## 11. Comparing heap, metaspace, and process memory

Different metrics answer different questions:

| Metric | Question answered | Source |
|---|---|---|
| Heap used | How much space are objects on the heap using? | MemoryMXBean, GC logs |
| Heap after GC | After GC, how many live objects remain? | GC logs, heap dumps |
| Metaspace used | How much space is class metadata using? | MemoryPoolMXBean, NMT |
| Direct buffer memory | How much direct/mapped buffer memory is in use? | BufferPoolMXBean |
| Thread count | How many threads are alive? | ThreadMXBean, `jcmd Thread.print` |
| Native memory categories | Which categories is the JVM using native memory for? | NMT |
| RSS / working set | How many memory pages are currently resident in RAM? | OS/process tools |
| Container memory | How much memory is the container using per cgroups? | Container runtime / cgroup metrics |

### 11.1. RSS is not simply heap + metaspace

RSS is the number of process pages currently resident in RAM as measured by the OS. RSS spans multiple regions and is affected by shared pages, mapped files, page residency, and OS accounting.

Therefore, do not add heap used and metaspace used expecting it to match RSS. Nor should total committed memory be treated as physical RAM actually resident.

### 11.2. Container memory limits

In containers, memory limits typically apply to the whole process/container, not just the heap.

An application can have:

- Heap still below `-Xmx`.
- Metaspace still under its cap.
- Yet thread stacks, direct buffers, and native allocations push total memory past the cgroup limit.
- Container runtime or kernel kills the process due to OOM.

When running in containers, track both JVM metrics and container memory usage/limits. Do not set `-Xmx` equal to the entire memory limit without reserving room for native memory and overhead.

## 12. Symptom-driven investigation workflow

An ordered workflow prevents guesswork tuning.

### Step 1: Identify which metric is growing

Collect at the same timestamps:

- Heap used and post-GC heap.
- Non-heap/metaspace usage.
- Direct buffer usage.
- Thread count.
- Process RSS/working set.
- Container memory if applicable.

You need a time series, not a single snapshot.

### Step 2: If post-GC heap rises, capture a heap dump

Use GC logs to confirm the trend, then take two heap dumps at comparable load points if needed. Compare retained heap and paths to GC roots to locate retaining collections, caches, threads, or listeners.

### Step 3: If metaspace rises, investigate class loading

Inspect:

- Loaded class count.
- Unloaded class count.
- Class loader statistics.
- Metaspace pool.
- Heap dump for references to old class loaders.

Pay special attention to plugin deploys/reloads, dynamic proxies, bytecode generation, or class-generating frameworks.

### Step 4: If heap is stable but RSS rises, inspect native memory

Enable NMT on the next diagnostic launch if not already active. Take a baseline, run the workload, and inspect the diff. Also check:

- Direct buffer pool.
- Thread count and stack settings.
- JNI/native libraries.
- Code cache and JVM native categories.
- Container/OS memory metrics.

### Step 5: Verify by changing one factor at a time

Once you find a suspect, verify with a repeatable workload:

- Bound the cache and inspect retained heap.
- Clear ThreadLocal and see if objects are reclaimed.
- Unregister listeners or shut down executors and watch class loaders.
- Cap the direct buffer pool and watch `BufferPoolMXBean`.
- Reduce threads or tune pools and watch native usage.

Do not change multiple limits simultaneously, or it will be hard to tell what fixed the issue.

## 13. Common diagnostic commands on Java 17

| Purpose | Command |
|---|---|
| List Java processes | `jcmd -l` |
| View VM flags | `jcmd <pid> VM.flags` |
| View class loader statistics | `jcmd <pid> VM.classloader_stats` |
| View object histogram | `jcmd <pid> GC.class_histogram` |
| Create a heap dump | `jcmd <pid> GC.heap_dump filename=heap.hprof` |
| Print thread dump | `jcmd <pid> Thread.print` |
| View NMT summary | `jcmd <pid> VM.native_memory summary` |
| Create NMT baseline | `jcmd <pid> VM.native_memory baseline` |
| Compare NMT | `jcmd <pid> VM.native_memory summary.diff` |
| Start JFR recording | `jcmd <pid> JFR.start name=MemoryProfile settings=profile duration=60s filename=memory.jfr` |

Some commands can trigger pauses or produce large files. Run them in appropriate environments and ensure adequate storage and access permissions for dumps/recordings.

### 13.1. Using Java Flight Recorder

JFR can record object allocation events, GC, threads, locks, and other JVM activity. Start a recording:

~~~bash
jcmd <pid> JFR.start name=MemoryProfile settings=profile duration=60s filename=memory.jfr
~~~

Then open `memory.jfr` with a compatible JDK Mission Control to analyze.

JFR is helpful for finding:

- Allocation hotspots.
- GC frequency and duration.
- Thread activity.
- Code paths creating many objects.
- Memory-related JVM events.

JFR does not replace a heap dump when you need to inspect the object graph and reference paths keeping objects alive. The two tools answer different questions.

## 14. Common misguided fixes

### 14.1. Raising -Xmx to hide a heap leak

Raising the heap can reduce OOME frequency briefly, yet if caches or collections keep growing unbounded, the leak persists.

Inspect retained objects and reference paths before deciding to resize the heap.

### 14.2. Raising MaxMetaspaceSize without checking class loaders

If old class loaders remain pinned, raising metaspace only postpones the error. First identify which loaders are not collected and which references keep them alive.

### 14.3. Calling System.gc() to handle leaks

`System.gc()` only asks the JVM to consider running GC; it does not guarantee objects will be freed. Objects that remain reachable must still be retained. Repeated GC calls can also degrade performance.

### 14.4. Looking only at the heap to judge process memory

A stable heap does not mean stable native memory. Monitor metaspace, direct buffers, threads, and RSS together.

### 14.5. Looking only at RSS to conclude a heap leak

RSS growth can come from thread stacks, direct buffers, metaspace, native libraries, or page residency. Combine JVM and OS metrics to narrow down the source.

### 14.6. Turning off GC or shrinking heap to save RAM

Changing collectors or heap sizing without understanding the workload can increase pauses and obscure bugs. Gather metrics first, identify which memory region is growing, and then tune.

## 15. Combined example: recording heap, non-heap, direct buffers, and threads

Create **`MemorySnapshot.java`**:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;

public class MemorySnapshot {

    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

        printUsage("Heap", memory.getHeapMemoryUsage());
        printUsage("Non-heap", memory.getNonHeapMemoryUsage());

        System.out.println("Direct / mapped buffer pools:");

        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            System.out.printf(
                    "%s: count=%d, used=%d, capacity=%d%n",
                    pool.getName(),
                    pool.getCount(),
                    pool.getMemoryUsed(),
                    pool.getTotalCapacity()
            );
        }

        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        System.out.println("Live threads: " + threads.getThreadCount());
        System.out.println("Peak threads: " + threads.getPeakThreadCount());

        Runtime runtime = Runtime.getRuntime();

        long heapUsed = runtime.totalMemory() - runtime.freeMemory();

        System.out.println("Runtime heap used: " + heapUsed);
        System.out.println("Runtime heap max: " + runtime.maxMemory());
    }

    private static void printUsage(String name, MemoryUsage usage) {
        System.out.printf(
                "%s: used=%d, committed=%d, max=%d%n",
                name,
                usage.getUsed(),
                usage.getCommitted(),
                usage.getMax()
        );
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 MemorySnapshot.java
java MemorySnapshot
~~~

Byte counts vary by machine and execution timing. Interpret them within their proper scopes:

- Heap: object region managed by GC.
- Non-heap: non-heap memory pools reported by the JVM.
- Direct/mapped pools: buffer memory managed through NIO buffer pools.
- Live threads: number of active threads.
- Runtime heap: heap metrics, not total process memory.

Do not sum these numbers arbitrarily, as some categories overlap or differ in accounting across JVM vendors.

## 16. Practice exercises

### Exercise 1: Distinguish a leak from high allocation rate

An application sees heap used rise to 1 GB before GC and drop to 250 MB after GC. This repeats many times and the post-GC level stays fairly stable.

**Question:** Is there enough evidence to conclude a heap leak?

**Answer:** No. This may simply be a high allocation rate where objects are reclaimed normally. Track post-GC heap across comparable load phases and inspect retained objects if an upward trend appears.

### Exercise 2: Unbounded static cache

A static Map stores requests by ID without removing entries when requests complete.

**Question:** Which region grows and why does GC not reclaim entries?

**Answer:** The heap grows because the static Map retains keys, values, and their object graphs. Those objects remain reachable via the static field so GC cannot reclaim them. Add cache bounds, TTL, or removal aligned with the business lifecycle.

### Exercise 3: Stable heap yet Metaspace OOME

An application deploys plugins multiple times. Each deploy creates a new class loader; after undeploy, a registry still holds a `Class` object from the plugin.

**Question:** Why can metaspace grow?

**Answer:** A `Class` object holds a link to its defining class loader. The registry keeps the class loader alive, so metadata for classes belonging to that loader is not eligible for unloading. Clean up the registry and references to the loader, threads, ThreadLocals, and related callbacks.

### Exercise 4: Direct buffers

An application uses `ByteBuffer.allocateDirect` to create a 32 MiB buffer per request without bounding concurrent requests.

**Question:** Why might a heap dump fail to explain total RSS?

**Answer:** Buffer payloads live off-heap. A heap dump mainly shows wrapper objects and references; inspect `BufferPoolMXBean`, NMT, and OS metrics to investigate native/direct memory.

### Exercise 5: Thread leak

Thread count grows over time, post-GC heap is stable, yet container memory climbs.

**Question:** What should you inspect?

**Answer:** Inspect thread dumps, whether executors are shut down, whether threads are blocked, per-request thread creation, and `-Xss` settings. Each platform thread's stack consumes native memory.

### Exercise 6: NMT does not explain RSS

RSS grows by 800 MB while NMT diff grows by only 100 MB.

**Question:** Can you conclude NMT is broken?

**Answer:** No. NMT tracks native memory categories managed by HotSpot and does not cover every allocation by third-party native libraries. Investigate JNI/native code, mapped memory, buffers, and OS metrics.

## 17. Takeaways

When diagnosing memory in Java 17, clearly distinguish three scopes:

- **Heap leak:** objects are no longer needed yet remain reachable. Use GC logs, heap dumps, dominator trees, and paths to GC roots.
- **Metaspace leak:** class metadata is not freed because class loaders remain alive. Track class loading, class unloading, class loader statistics, and references retaining loaders.
- **Native memory growth:** off-heap memory grows due to thread stacks, direct buffers, JNI/native libraries, the code cache, or JVM structures. Combine NMT, `BufferPoolMXBean`, `ThreadMXBean`, and OS metrics.

Metaspace belongs to native memory, yet does not represent all native memory. Heap used, non-heap used, direct buffer usage, and process RSS are distinct metrics; use the right metric for the right question.

Never raise memory limits just to mask symptoms. Find the growing region, identify which objects or resources retain memory, fix lifecycles or resource bounds, and verify with a repeatable workload.

## 18. References

- [Oracle Java SE 17 — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap and non-heap memory metrics.
- [Oracle Java SE 17 — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): JVM memory pool statistics.
- [Oracle Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): direct and mapped buffer pool metrics.
- [Oracle Java SE 17 — ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): currently loaded, total loaded, and unloaded class counts.
- [Oracle Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): JVM thread metrics.
- [Oracle Java SE 17 — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): diagnostic commands for Java processes, heap dumps, class histograms, class loaders, and NMT.
- [Oracle Java SE 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): enabling and reading HotSpot native memory statistics.
- [Oracle Java SE 17 — Troubleshooting Memory Leaks](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-memory-leaks.html): heap leak investigation workflow and diagnostic tools.
- [OpenJDK JEP 195 — Handle Metaspace Allocation Failure](https://openjdk.org/jeps/195): background on handling metaspace allocation failures in HotSpot.



