# Live Objects in the Java Heap with jmap

A **live object** is an object that the garbage collector (GC) still considers reachable at the time of heap inspection. An object typically remains live when a reference path exists from a GC root to that object. For example, an object held in a static field, in a collection still used by the application, or on the stack of a running thread can continue to exist in the heap.

In the `jmap` tool, the `live` option restricts the histogram or heap dump to the set of live objects. This option is useful when investigating memory leaks, because it focuses on objects that are still retained after the GC reclaims objects that are no longer reachable.

It is important to distinguish a live object from an object currently being processed. An object may no longer be needed for business logic yet remain live because a cache, listener, static collection, or thread inadvertently holds a reference to it. This is one of the most common causes of continuous heap growth.

## 1. How Is an Object Considered Live?

The GC does not decide whether an object is live solely based on whether a variable in the source code is still within its declaration scope. The JVM determines the set of reachable objects from **GC roots** and Java's reachability rules.

Common reference sources include:

- Local references still held by the JVM in a running thread's stack frame.
- Static fields of loaded classes.
- JNI global/local references held by native code.
- Active threads, monitors, and certain internal JVM structures.
- Other reachable objects that hold references to the object in question.

Example:

~~~java
static final List<Object> CACHE = new ArrayList<>();

public static void keep(Object value) {
    CACHE.add(value);
}
~~~

Objects added to `CACHE` remain reachable via the static field and collection, so the GC cannot reclaim them while the collection still holds the reference. If the application continuously adds elements without removing old ones, the number of live objects can grow over time.

Conversely:

~~~java
public static void createTemporaryObjects() {
    List<byte[]> temporary = new ArrayList<>();
    for (int i = 0; i < 1000; i++) {
        temporary.add(new byte[1024]);
    }
}
~~~

After the method returns and no other references to the arrays remain, they can become unreachable and be reclaimed by the GC in a subsequent cycle. An object becoming unreachable does not mean its memory is returned immediately; the GC decides when reclamation occurs.

Java also has reachability levels associated with `SoftReference`, `WeakReference`, and `PhantomReference`. Reference processing rules affect when an object is considered eligible for reclamation. Therefore, “live” is a result of the JVM's reachability and reference-processing rules at the time of inspection, not a business label assigned by the application.

## 2. Why Filter for Live Objects?

A full-heap histogram can include objects that have not yet been reclaimed by the GC even though they are no longer reachable. A live histogram helps focus on objects that are still being retained.

| Question | Appropriate Data |
|---|---|
| How many instances of each class are currently in the heap, including unreclaimed objects? | All-objects histogram |
| After excluding unreachable objects, which classes still account for many instances? | Live-objects histogram |
| Which object is retaining a large number of other objects? | Live heap dump and reference graph/dominator tree analysis |
| Which class increases in instance count across multiple runs of a similar workload? | Comparing live histograms or multiple heap dumps |

Live objects are especially useful when investigating memory leaks caused by unbounded cache growth, unregistered listeners/callbacks, ThreadLocals retaining objects, old classloaders after redeploys, non-expiring sessions, or buffers held by an unexpected reference graph.

A histogram only reports instance counts and total shallow size per class. It does not show who is holding the objects. To find the root cause, you must open a heap dump in an analysis tool and trace the reference path to a GC root.

## 3. Viewing a Live Histogram with jmap

`jmap` is a command-line tool in the JDK for inspecting heap information of a Java process. Identify the PID first with:

~~~sh
jcmd -l
~~~

Or:

~~~sh
jps -l
~~~

Command to view a histogram containing only live objects:

~~~sh
jmap -histo:live <pid>
~~~

Example:

~~~sh
jmap -histo:live 18360
~~~

The output typically includes these columns:

~~~text
 num     #instances         #bytes  class name (module)
-------------------------------------------------------
   1:          5000          80000  com.example.CacheEntry
   2:          1200          38400  java.lang.String
   3:           250          20000  byte[]
Total          6450         138400
~~~

Meaning:

- `num`: rank of the class in the histogram.
- `#instances`: number of instances of the class.
- `#bytes`: total shallow size of the instances of that class.
- `class name`: name of the class; may include the module.

This is illustrative output. Counts, sizes, and class ordering depend on the JVM, workload, collector, and timing of the histogram.

`#bytes` is the total direct size of objects of that class, not retained heap. Retained heap is the amount of memory that could only be freed if an object or group of objects retaining them were removed from the graph; evaluating this requires a heap dump analysis tool.

You can write the histogram to a file:

~~~sh
jmap -histo:live,file=live-histogram.txt <pid>
~~~

The `parallel=<number>` option adjusts the number of inspection threads based on JVM capabilities. A value of 1 disables parallel processing; 0 lets the VM choose the thread count. There is no need to change this option without a specific measurement reason.

## 4. Comparing All Objects vs. Live Objects

Without `live`, `jmap -histo` counts all objects visible to heap inspection, including objects not yet reclaimed even though they are unreachable. You can specify `all` explicitly:

~~~sh
jmap -histo <pid>
jmap -histo:all <pid>
jmap -histo:live <pid>
~~~

| Command | Scope |
|---|---|
| `jmap -histo <pid>` | All objects in the heap per snapshot |
| `jmap -histo:all <pid>` | All objects in the heap |
| `jmap -histo:live <pid>` | Only objects considered live |

For example, suppose an application just created 100,000 temporary objects and dropped their references while still holding 5,000 objects in a static array. An all-objects histogram might show:

~~~text
#instances    class name
100000        HeapProbe$DeadRecord
  5000        HeapProbe$LiveRecord
~~~

After a live-only inspection:

~~~text
#instances    class name
  5000        HeapProbe$LiveRecord
~~~

`DeadRecord` no longer appears in the live histogram because those instances are no longer reachable and were reclaimed by the GC while determining the live set. Exact results depend on GC timing and workload; if the GC already reclaimed the objects before running the all-objects histogram, the two measurements may look similar.

Live-only inspection may trigger a GC to determine the set of reachable objects. This can cause pauses or affect latency. Consider heap load, the collector, and timing before running it in production.

## 5. Creating a Heap Dump Containing Only Live Objects

A histogram shows which classes have many instances. If you need to know which objects are retaining other objects, generate a heap dump in HPROF format to analyze the reference graph.

Dump only live objects:

~~~sh
jmap -dump:live,format=b,file=heap-live.hprof <pid>
~~~

Dump all objects:

~~~sh
jmap -dump:all,format=b,file=heap-all.hprof <pid>
~~~

Example with PID:

~~~sh
jmap -dump:live,format=b,file=C:/diagnostics/heap-live.hprof 18360
~~~

| Option | Meaning |
|---|---|
| `live` | Write only objects considered live |
| `all` | Write all objects in the heap |
| `format=b` | Use binary HPROF format |
| `file=<path>` | Path to the heap dump file |
| `gz=<level>` | Write a compressed dump with level 1–9 |

If neither `live` nor `all` is specified, `jmap -dump` defaults to dumping all objects. If both are passed, `live` takes precedence according to current JDK help output.

Heap dumps can be very large and pause the process during collection. Ensure sufficient disk space and choose a writable directory. Do not overwrite an existing dump unless you have confirmed it is no longer needed for investigation.

## 6. Analyzing a Heap Dump

Once you have an HPROF file, open it with a compatible tool, such as Eclipse Memory Analyzer (MAT) or a heap analyzer suitable for the dump version. Typical steps:

1. Open the `heap-live.hprof` file.
2. View the histogram to find classes with high instance counts or large total shallow size.
3. Open the dominator tree to find objects retaining the largest share of the heap.
4. Select a suspicious instance and inspect its incoming references.
5. Use “Path to GC Roots” to trace the reference path from a GC root to the object.
6. Identify the collection, static field, thread, ThreadLocal, listener, or classloader holding the object.
7. Cross-reference with the source code and the lifecycle of the component owning the reference.
8. Fix the cause of retention, then repeat the workload and compare heap snapshots.

For example: the histogram shows millions of `com.example.Session` instances. In the dominator tree, a static `ConcurrentHashMap` retains most of the sessions. Path to GC Roots might show that the map belongs to a singleton service. In that case, inspect the session expiration/removal logic and the map's lifecycle.

Do not conclude there is a memory leak based solely on a high instance count. A bounded cache, pool, or registry may hold objects intentionally. Check growth rate, retained heap, configured limits, and behavior after the workload ends.

## 7. Java 17+ Example: Creating Live and Temporary Objects

The following example retains 5,000 `LiveRecord` instances in a static field while creating 100,000 `DeadRecord` instances and dropping their references. The program keeps the JVM running so you have time to capture histograms.

Create `HeapProbe.java`:

~~~java
public class HeapProbe {
    static Object[] keep;

    public static void main(String[] args) throws InterruptedException {
        keep = new Object[5_000];
        for (int i = 0; i < keep.length; i++) {
            keep[i] = new LiveRecord(i);
        }

        Object[] temporary = new Object[100_000];
        for (int i = 0; i < temporary.length; i++) {
            temporary[i] = new DeadRecord(i);
        }
        temporary = null;

        System.out.println("heap-probe-ready");
        Thread.sleep(120_000);
    }

    static class LiveRecord {
        final int id;
        LiveRecord(int id) { this.id = id; }
    }

    static class DeadRecord {
        final int id;
        DeadRecord(int id) { this.id = id; }
    }
}
~~~

Compile with Java 17 or later:

~~~sh
mkdir -p out
javac --release 17 -d out HeapProbe.java
~~~

Run the program:

~~~sh
java -Xms256m -Xmx256m -cp out HeapProbe
~~~

Exact stdout:

~~~text
heap-probe-ready
~~~

Open a second terminal and find the PID:

~~~sh
jcmd -l
~~~

Suppose the PID is `18360`. Run the all-objects histogram first:

~~~sh
jmap -histo:all 18360
~~~

Then run the live-only histogram:

~~~sh
jmap -histo:live 18360
~~~

In a test run with JDK 24.0.2, the all-objects histogram recorded 100,000 `HeapProbe$DeadRecord` and 5,000 `HeapProbe$LiveRecord` instances. The live histogram showed only 5,000 `HeapProbe$LiveRecord` instances. Byte sizes and total counts of other classes may vary by JDK, architecture, and environment.

When finished, return to the terminal running `HeapProbe` and press `Ctrl+C` to stop the process.

## 8. Using jcmd Instead of jmap

Oracle marks `jmap` as experimental and unsupported, and it may be removed in future JDK releases. Troubleshooting documentation recommends using `jcmd` for modern diagnostics because it provides a newer diagnostic command interface and lower overhead in many scenarios.

Live-only histogram using `jcmd`:

~~~sh
jcmd <pid> GC.class_histogram
~~~

As of JDK 24, this command does not require `-all` by default, so it inspects only live objects. To include unreachable objects as well:

~~~sh
jcmd <pid> GC.class_histogram -all
~~~

Live-only heap dump:

~~~sh
jcmd <pid> GC.heap_dump heap-live.hprof
~~~

All-objects heap dump:

~~~sh
jcmd <pid> GC.heap_dump -all heap-all.hprof
~~~

`GC.heap_dump` requests a full GC before dumping by default, unless `-all` is used. Both `GC.class_histogram` and `GC.heap_dump` have high impact depending on heap size and contents. Check the command description before running:

~~~sh
jcmd <pid> help GC.class_histogram
jcmd <pid> help GC.heap_dump
~~~

If a command is unavailable on your target JDK version, check the help output of that specific JVM and the corresponding version documentation. Do not assume every JDK has the same options.

## 9. Impact and Precautions When Capturing Live Heap Data

Determining the live set may require a GC or a safepoint heap inspection operation. Potential impacts include:

- Application pauses while the JVM inspects the heap or performs a full GC.
- Increased CPU and I/O usage while generating the histogram or dump.
- Temporary file growth and disk space pressure.
- Altered heap state as unreachable objects are reclaimed during inspection.
- Service latency impact, especially with large heaps or high traffic.

On JDK 24, `jcmd GC.class_histogram` is marked Impact: High; `GC.heap_dump` is also Impact: High and requests a full GC by default unless `-all` is selected. Therefore, prefer running these during a maintenance window or on a replica/staging environment whenever possible. If you must collect data in production, coordinate with operations and monitor pauses/latency.

A live heap dump can still contain a great deal of sensitive data: tokens, passwords, sessions, personal information, request payloads, and business data. “Live” does not mean the data is safe to share. Restrict read permissions, encrypt at rest and in transit, never upload to public locations, and delete according to your retention policy.

## 10. Common Misconceptions

| Misconception | Accurate Explanation |
|---|---|
| Live objects are newly created objects | Object age does not determine liveness; reachability is what matters |
| Objects no longer used by business logic die automatically | If a reference from a GC root still exists, the object remains live |
| A variable going out of scope means the object is reclaimed immediately | The object only becomes eligible for GC; the GC decides when to reclaim it |
| `-histo:live` and `-histo` always produce the same result | An all-objects histogram may still include unreachable objects not yet reclaimed by GC |
| A histogram shows which object is retaining memory | A histogram only summarizes class/instances/bytes; you need a heap dump and reference analysis |
| `#bytes` is retained heap | It is the total shallow size per class, not retained size |
| A live heap dump contains no sensitive data | Live objects can hold secrets and user data |
| `jmap` is a long-term supported tool | Oracle marks `jmap` as experimental/unsupported and recommends `jcmd` |

## 11. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jmap: command not found` | Only JRE is installed or JDK `bin` is missing from `PATH` | Install the JDK and verify `PATH`/`JAVA_HOME` |
| Cannot attach to PID | Wrong PID, JVM has exited, or insufficient attach permissions | Re-check the PID, run as the appropriate user, and inspect the attach error |
| Expected class missing from live histogram | Objects were unreachable and reclaimed by GC | Check the all-objects histogram and reference paths in the workload |
| All-objects and live histograms look nearly identical | GC already reclaimed temporary objects before measurement, or most objects remain reachable | Repeat a controlled workload and measure close to object creation |
| Heap dump file cannot be created | Insufficient write permissions, missing directory, or out of disk space | Choose a valid path, verify permissions and available disk space |
| Heap dump is very large | Large heap or dumping all objects | Use a live dump when appropriate, and consider compression and storage capacity |
| Application pauses during dump | GC/heap inspection can cause pauses and heavy I/O | Capture dumps during an appropriate window, monitor impact, and consider using a replica |
| Cannot open HPROF file | Truncated file, insufficient disk space, or incompatible analyzer | Verify the file completed writing and use a tool that supports HPROF |
| Windows reports missing `dbgeng.dll` | Missing Debugging Tools for Windows on configurations that require it | Install the required component and check `PATH` to `jvm.dll` |
| `jmap` hangs or is unresponsive | JVM is hung or attach did not complete | Use `jcmd` if possible; for core dumps, see `jhsdb jmap` in JDK documentation |

## 12. Memory Leak Investigation Workflow Using Live Objects

1. Identify the correct JVM and PID using `jcmd -l` or OS tools.
2. Record heap usage, workload, and sampling timestamp.
3. Run a live histogram to identify classes with high instance counts or large shallow size.
4. Capture a live heap dump when you need to inspect the object graph.
5. Use the dominator tree and Path to GC Roots to identify references retaining objects.
6. Cross-reference with caches, collections, listeners, ThreadLocals, threads, and classloaders in the source code.
7. Verify whether objects are retained intentionally or due to missing lifecycle/cleanup logic.
8. Fix the root cause, re-run an equivalent workload, and compare histograms/dumps.
9. Confirm that live object counts and retained heap stabilize after the load ends.
10. Protect and delete heap dumps according to your data policy.

### Checklist

- [ ] Identified the correct PID of the target JVM.
- [ ] Understood that a live object is one reachable under GC rules.
- [ ] Distinguished between all-objects histograms and live histograms.
- [ ] Understood that `#bytes` is shallow size, not retained heap.
- [ ] Used a live heap dump when reference graph analysis is needed.
- [ ] Accounted for GC impact, pauses, CPU, I/O, and file size.
- [ ] Used dominator tree/Path to GC Roots to locate objects retaining heap.
- [ ] Cross-referenced with the lifecycle and purpose of caches/collections.
- [ ] Considered using `jcmd` instead of `jmap`.
- [ ] Protected heap dumps since they may contain sensitive data.

`jmap -histo:live` and `jmap -dump:live` help focus on objects that the GC still considers reachable. Combining histograms, heap dumps, and reference-path analysis to GC roots helps pinpoint the class or collection holding objects for too long, allowing you to identify the cause of a memory leak and verify the fix afterward.

## References

- [Oracle JDK 24 — The jmap Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmap.html)
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle JDK 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [Oracle JDK 24 — Troubleshooting Memory Leaks](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-memory-leaks.html)