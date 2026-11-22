# Class Histogram with jmap

A **class histogram** is a statistical table of Java objects in the heap grouped by class. Each row shows how many instances a class currently has and the total shallow heap size of those instances. It is a fast way to find object groups consuming large amounts of Java heap, detect abnormally growing collections, and gather initial evidence when investigating a memory leak.

In the JDK, `jmap -histo <pid>` generates a heap histogram for a running Java process. The `-histo:live` option counts only reachable objects. For modern diagnostic workflows, Oracle recommends using `jcmd <pid> GC.class_histogram`; this command has High impact, depending on the heap size and contents.

A histogram is a per-class summary, not an object graph diagram. It shows which classes have many objects and how many shallow bytes they occupy, but it does not directly show which object is holding references that prevent a group of objects from being freed. When you need to find the retention paths keeping objects alive, capture a heap dump and analyze it with a tool such as Eclipse Memory Analyzer (MAT) or JDK Mission Control.

## 1. What is a class histogram?

The Java heap stores objects created while the application is running. An application can create many objects across many different classes:

- Domain objects such as `Order`, `Customer`, or `Session`.
- Collections such as `HashMap`, `ArrayList`, and their internal nodes.
- String and array objects such as `String`, `byte[]`, and `char[]`.
- Framework, library, JDK, and JVM objects.
- Objects representing proxies, lambdas, caches, or buffers.

A class histogram groups objects by class and reports the instance count and total size for each group.

For example, if an application creates 500,000 `com.example.Session` objects and each one holds references to many other objects, a histogram can reveal the elevated `Session` count. It helps identify which classes need further investigation.

A histogram answers:

- Which class has the most instances?
- Which class has the largest total shallow heap?
- Is the instance count of a domain class growing across snapshots?
- How much heap are arrays such as `byte[]` or `Object[]` occupying?
- Are any unexpected classes or collections appearing near the top?

A histogram does not directly answer:

- Which object is a GC root or what is holding a reference to it?
- What is the total size of the entire object graph retained by a given object?
- At which line of code was an object allocated?
- How much native memory or direct memory is being used?

To answer these latter questions, you need a heap dump, allocation profiling, JFR, JMX, or native memory tracking tools.

## 2. Running jmap -histo

Syntax:

```sh
jmap -histo <pid>
```

`<pid>` is the process ID of the Java application to inspect. For example:

```sh
jmap -histo 24680
```

This command attaches to the target JVM and prints a histogram of the Java object heap. PID 24680 is only an illustrative number; replace it with the actual PID.

You can use the full path if `jmap` is not in your PATH:

```sh
$JAVA_HOME/bin/jmap -histo 24680
```

On Windows PowerShell:

```powershell
& "$env:JAVA_HOME\bin\jmap.exe" -histo 24680
```

The output can be quite long. Redirect it to a file to read, search, and compare:

```sh
jmap -histo 24680 > histogram.txt
```

On PowerShell:

```powershell
jmap -histo 24680 | Out-File -Encoding utf8 histogram.txt
```

Avoid running histograms continuously at high frequency on a latency-sensitive application. Heap inspection can be time-consuming and impact JVM performance, depending on heap size, object count, garbage collector, and runtime.

## 3. Reading the output columns

Typical output looks like this:

```text
 num     #instances         #bytes  class name (module)
-------------------------------------------------------
   1:         50000        2400000  com.example.Session (app)
   2:        100000        1600000  java.lang.String (java.base)
   3:         25000         800000  [B (java.base)
   4:          5000         240000  java.util.HashMap$Node (java.base)
-------------------------------------------------------
 Total        180000        5040000
```

This is an illustrative example of the formatting, not a fixed output. Counts, byte sizes, ordering, and module information depend on the application, JDK, and runtime architecture.

| Column | Meaning |
|---|---|
| `num` | Rank of the row in the histogram |
| `#instances` | Number of object instances belonging to the class |
| `#bytes` | Total shallow heap size of the instances of that class, in bytes |
| `class name` | Class name or class descriptor |
| `module` | Module containing the class in JDK versions that display this information |
| `Total` | Total instances and total bytes across all reported rows |

Rows are typically sorted in descending order by total bytes. The top-ranked class is the group occupying the most shallow bytes at the time of capture, not necessarily the class with the highest instance count.

For example:

- `com.example.Session` has 50,000 instances.
- The total shallow size of the `Session` group is 2,400,000 bytes.
- `java.lang.String` has 100,000 instances and occupies 1,600,000 bytes.
- `[B` is the notation for a byte array.

Do not use the `num` rank as a stable identifier across snapshots. Rankings change as object counts and sizes change.

## 4. Shallow heap size vs. retained heap size

This is the most important distinction when reading a class histogram.

**Shallow heap size** is the size of the object itself, including the object header, fields, and padding/alignment according to how the JVM represents objects. It does not include the size of other objects referenced by that object.

**Retained heap size** is the amount of heap memory that would be freed if the object or group of objects under consideration were no longer held by any other references. This value depends on the reference graph and dominator relationship.

Example:

```java
class Customer {
    String name;
    byte[] avatar;
}
```

A `Customer` object holds a reference to a `String` and a byte array.

In the histogram:

- The shallow bytes of `Customer` count only the `Customer` object itself.
- The shallow bytes of `String` are counted in the `String` row.
- The shallow bytes of `byte[]` are counted in the byte array row.
- The histogram does not roll the `avatar` size into the `Customer` row.

Therefore, a class with a small shallow heap can still be the anchor retaining a very large object graph. To find retained heap, dominators, and paths from GC roots, you need to analyze a heap dump.

Do not add histogram values together under the assumption that a parent object retains all child objects; the histogram already accounts for each object under its own class.

## 5. Calculating the average size per instance

You can estimate the average shallow size of a class using:

\[
\text{Average shallow size}
=
\frac{\text{\#bytes}}{\text{\#instances}}
\]

For example, a class with 50,000 instances and a total of 2,400,000 bytes:

\[
\frac{2,400,000}{50,000}=48 \text{ bytes/object}
\]

This is an average derived from the histogram. It is useful for relative comparisons, but it does not indicate retained size and does not replace inspecting the actual object layout.

For objects of the same class, shallow size is typically uniform within a single runtime, though it can vary across JDKs, architectures, compressed references, object alignment, and JVM flags.

Do not assume a Java object always has a fixed size such as 16 or 24 bytes. Use the numbers from the runtime you are analyzing.

## 6. Understanding array class names

Histograms typically display array class names using JVM descriptors:

| Name in histogram | Corresponding Java type |
|---|---|
| `[B` | `byte[]` |
| `[C` | `char[]` |
| `[I` | `int[]` |
| `[J` | `long[]` |
| `[F` | `float[]` |
| `[D` | `double[]` |
| `[Z` | `boolean[]` |
| `[Ljava.lang.Object;` | `Object[]` |
| `[[B` | Two-dimensional byte array |

Arrays can consume a lot of memory even when the domain class holding them uses very few shallow bytes. For example, a cache storing many payloads as byte arrays can push `[B` to the top of the histogram.

Since Java 9, the internal representation of `String` in mainstream JDKs uses a byte array for string contents in many cases. Therefore, when investigating string-related memory usage, look at both the `java.lang.String` row and the `[B` row, rather than looking only at `String`.

A large `[B` row does not automatically prove a memory leak. You need to determine whether the arrays come from payloads, buffers, caches, serialization, or another component.

## 7. Difference between -histo and -histo:live

`jmap` supports two forms:

```sh
jmap -histo <pid>
```

```sh
jmap -histo:live <pid>
```

| Command | Object scope |
|---|---|
| `jmap -histo <pid>` | Summarizes objects in the heap, including uncollected objects |
| `jmap -histo:live <pid>` | Summarizes only live/reachable objects |

Unreachable objects may remain in the heap until the garbage collector reclaims them. Consequently, a histogram without `:live` can include garbage objects that had not yet been collected at the time of capture.

`-histo:live` is useful when you want to observe the live set and filter out noise from unreferenced objects. However, determining live objects requires reachability/GC processing depending on the JVM implementation; this operation can cause significant pauses or overhead.

For production environments, evaluate the impact before running it. If you need metrics over time with lower overhead, consider JFR or JMX instead of repeatedly requesting live histograms.

## 8. Difference between jmap -histo and jcmd GC.class_histogram

Oracle recommends using `jcmd` for modern diagnostics instead of older tools like `jmap`.

The corresponding command is:

```sh
jcmd 24680 GC.class_histogram
```

Check the syntax on the target JVM:

```sh
jcmd 24680 help GC.class_histogram
```

In JDK 21, the `GC.class_histogram` command supports these options:

| Option | Meaning |
|---|---|
| Without `-all` | Does not request counting unreachable objects; defaults to `false` |
| `-all` | Inspects all objects, including unreachable objects |
| `-parallel=N` | Number of parallel threads used to inspect the heap; `0` lets the JVM choose, `1` disables parallelism |

Example inspecting only live objects by default:

```sh
jcmd 24680 GC.class_histogram
```

Example including unreachable objects:

```sh
jcmd 24680 GC.class_histogram -all
```

Note that the defaults of the two tools differ according to JDK 21 documentation. `jmap -histo` without `:live` summarizes heap objects; `jcmd GC.class_histogram` defaults to `-all=false`, whereas `-all` enables inspecting unreachable objects as well.

`GC.class_histogram` is documented by Oracle as **Impact: High**, depending on heap size and contents. It should not be treated as a lightweight monitoring operation. Check `help` on the exact target JVM before running, as diagnostic commands and options can vary across versions or implementations.

## 9. Finding the PID before running a histogram

You can find running JVMs using:

```sh
jps -l
```

Example:

```text
24680 com.example.HistogramDemo
25120 com.example.OrderService
```

After identifying the right process:

```sh
jmap -histo 24680
```

Or using `jcmd`:

```sh
jcmd 24680 GC.class_histogram
```

If you do not see the process, use OS tools:

Linux/macOS:

```sh
ps -ef
```

Windows PowerShell:

```powershell
Get-Process java, javaw -ErrorAction SilentlyContinue
```

In containers, the PID on the host may differ from the PID inside the container. Run the tool in the appropriate container/PID namespace, or identify the PID in the environment where the tool can attach.

Attach tools generally need to run on the same machine as the target JVM and under an OS account with appropriate permissions. When operating in a multi-user environment, verify the account running the application and the attach policy.

## 10. Java 17+ example: creating objects to observe a histogram

The following example retains 100,000 instances of a domain class in a static collection. Because of the static reference, the objects remain reachable while the program waits.

Create `src/com/example/HistogramDemo.java`:

```java
package com.example;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class HistogramDemo {
    private static final List<SampleRecord> RETAINED =
            new ArrayList<>();

    private static final class SampleRecord {
        private final int id;

        private SampleRecord(int id) {
            this.id = id;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 100_000; i++) {
            RETAINED.add(new SampleRecord(i));
        }

        System.out.println("READY records=" + RETAINED.size());

        new CountDownLatch(1).await();
    }
}
```

Compile:

```sh
mkdir -p out
javac -d out src/com/example/HistogramDemo.java
```

Run:

```sh
java -cp out com.example.HistogramDemo
```

Expected stdout:

```text
READY records=100000
```

The program waits indefinitely so you can open a second terminal and inspect the heap. Use `jps -l` to find the PID of `com.example.HistogramDemo`.

Run the histogram:

```sh
jmap -histo <pid>
```

Or count only live objects:

```sh
jmap -histo:live <pid>
```

Look for the class `com.example.HistogramDemo$SampleRecord`. The histogram should show roughly 100,000 instances of this class while the program is holding the list. Total bytes depend on object layout and JVM configuration, so do not hard-code a specific byte value.

If you want to use `jcmd`:

```sh
jcmd <pid> GC.class_histogram
```

After practicing, return to the first terminal and press Ctrl+C to stop the program.

## 11. Finding the classes consuming the most heap

When opening a histogram, start by examining the two primary columns:

- High `#instances`: the class creates many objects.
- High `#bytes`: the class has a large total shallow heap.

These two rankings are not necessarily the same. A class with many small objects may rank high in instance count but lower in total bytes. A class with fewer large objects may rank high in total bytes.

How to interpret common patterns:

| Symptom | Investigation direction |
|---|---|
| Many `String` objects | Check string caches, keys, payloads, logging, or long-lived data |
| Many `[B` arrays | Check byte contents, serialization, network buffers, file payloads |
| Many `Object[]` arrays | Check backing arrays of collections, queues, or caches |
| Many `HashMap$Node` objects | Check growing maps, unremoved keys, or unbounded caches |
| Many domain classes like `Session`/`Request` | Check lifecycle, timeouts, cleanup, and reference retention |
| Many proxies/lambdas | Check proxy creation, callbacks, listeners, or class generation |
| Many classloaders/classes | Check redeploys, plugin lifecycles, and classloader leaks |

These are hypotheses to investigate, not automatic conclusions. An application may legitimately retain hundreds of thousands of `String` objects or map nodes if its workload requires it.

## 12. Histograms and memory leaks

A memory leak in Java typically occurs when an application no longer needs an object but still holds a reference to it. The garbage collector only reclaims objects that are no longer reachable from GC roots.

Histograms help detect growth patterns:

1. Start the application and wait for warm-up to complete.
2. Put the application under a steady workload or repeatable load scenario.
3. Capture an initial histogram.
4. Let the application run for a period of time.
5. Capture a follow-up histogram under similar conditions.
6. Compare instance counts and total bytes per class.
7. Look for classes growing steadily across multiple snapshots.
8. Use a heap dump to identify the object graph and reference retention paths.

Comparison example:

| Class | Snapshot 1 | Snapshot 2 | Notes |
|---|---:|---:|---|
| `com.example.Session` | 10,000 | 40,000 | Sharp increase; check lifecycle |
| `java.lang.String` | 80,000 | 110,000 | Growing; identify allocation source and owner |
| `byte[]` | 20,000 | 90,000 | Possibly related to payloads/caches |
| `java.util.HashMap$Node` | 15,000 | 55,000 | Check map usage and eviction policy |

The table above is only an analysis example. Do not conclude there is a leak from two isolated snapshots. Account for equivalent load conditions, warm-up time, GC activity, and traffic changes.

An increase in class instances can reflect higher workload, cache warming, or legitimate queue accumulation. A stronger signal is when the live set continues to grow after the application reaches steady state and across GC cycles.

## 13. Comparing histograms over time

You can save each capture to a separate file:

```sh
jmap -histo:live 24680 > histo-01.txt
```

After some time:

```sh
jmap -histo:live 24680 > histo-02.txt
```

And continue:

```sh
jmap -histo:live 24680 > histo-03.txt
```

Use `diff` or a spreadsheet tool to compare:

```sh
diff -u histo-01.txt histo-02.txt
```

On Windows, you can use `Compare-Object` after reading the files, or import the data into an appropriate analysis tool. Do not compare solely by line/rank number because class rankings can shift; compare by class name and module.

If your goal is tracking the live set, keep the capture mode consistent across runs. Do not compare a histogram that includes unreachable objects against a live-only histogram and treat the difference as a memory leak.

For more reliable conclusions, record the timestamp, PID, JDK version, heap size, workload, and time of the last GC alongside each histogram file.

## 14. Why a histogram is not enough to find the root cause

A histogram only aggregates by class. It does not preserve relationships between individual objects. For example:

- A cache may hold many `Customer` objects.
- A `Customer` holds an `Order` list.
- Each `Order` holds many `LineItem` objects.
- Each `LineItem` holds `String` and byte array objects.

A histogram can show that all of these classes are consuming memory, but it cannot point to which cache object is anchoring the entire group.

To find the root cause:

1. Capture a heap dump at an appropriate time.
2. Open the heap dump with Eclipse Memory Analyzer (MAT) or an equivalent tool.
3. Inspect the histogram and dominator tree.
4. Find objects with large retained heap.
5. Check the path to GC roots to see the reference chain.
6. Trace back to the code creating and holding the reference.
7. Identify the missing lifecycle handling or cleanup.
8. Fix the code and re-run the workload to verify that the retained/live set stabilizes.

Example of capturing a heap dump with `jcmd`:

```sh
jcmd 24680 GC.heap_dump /tmp/app-heap.hprof
```

Heap dumps can be very large, require disk space, and may cause significant pauses. According to JDK 21 documentation, this command has High impact and triggers a full GC by default unless the `-all` option is used. Check the command help before running it in production.

## 15. Class histograms and class loader statistics

If a histogram shows many classes or objects related to classloaders, inspect class loaders separately.

`jmap` provides the option:

```sh
jmap -clstats 24680
```

It prints class loader statistics for the Java heap.

With `jcmd`:

```sh
jcmd 24680 VM.classloader_stats
```

This command prints statistics about classloaders. You can also inspect:

```sh
jcmd 24680 VM.classloaders
```

Classloader leaks can occur when an application is redeployed while the old classloader is still retained by threads, `ThreadLocal` variables, static references, JDBC drivers, logging frameworks, or unregistered callbacks.

The histogram shows the related classes/objects; classloader statistics and a heap dump help pinpoint what is retaining the classloader.

## 16. Class histograms do not measure total process memory

A class histogram counts objects in the Java heap. The total `#bytes` does not equal the process's total RSS or resident memory.

Other memory regions can include:

- Metaspace and compressed class space.
- Thread stacks.
- JIT code cache.
- Native allocations from JNI or native libraries.
- Direct byte buffers and off-heap regions.
- GC, compiler, and internal JVM data structures.

If process RSS grows while the Java heap histogram does not grow accordingly, investigate native memory and off-heap regions.

Native Memory Tracking (NMT) must be enabled at JVM startup, for example:

```sh
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Once the JVM is running, view the summary:

```sh
jcmd 24680 VM.native_memory summary
```

NMT tracks native memory categories managed by HotSpot. It does not track every allocation made by third-party native code. If you suspect a native leak outside NMT's scope, use OS-level tools such as process memory maps or a native profiler.

## 17. Impact and safety when running histograms

According to JDK 21 documentation:

- `jmap` is an experimental and unsupported tool, and may change or be removed in future JDK releases.
- `jcmd GC.class_histogram` has High impact, depending on heap size and contents.
- Heap inspection can increase pause times or affect application latency.
- Output can be very long for large heaps with many classes.

Safe practices:

- Verify the exact PID and target environment.
- Run under an account with appropriate attach permissions.
- Capture during an acceptable maintenance or observation window.
- Limit consecutive captures.
- Redirect output to a file to avoid flooding terminal logs.
- Check available disk space if capturing a heap dump.
- Protect histogram and heap dump files, as they can expose class names, packages, and internal structure.
- Never upload heap dumps to public locations; heap dumps may contain user data, tokens, or sensitive business data.

If you need frequent diagnostics in production, prefer JFR, JMX, or an appropriate observability system. Use histograms as a targeted investigation step rather than continuous polling.

## 18. Alternatives and complementary tools

| Tool | Data | When to use |
|---|---|---|
| `jcmd PID GC.class_histogram` | Class histogram on the heap | Recommended replacement for `jmap` histogram |
| `jmap -histo` | Heap histogram of objects by class | Interactive diagnostics on runtimes that still support it |
| `jmap -histo:live` | Histogram of live objects | Observing the live set |
| `jmap -dump:live,format=b,file=...` | HPROF heap dump of live objects | When an object graph is needed for deep analysis |
| `jcmd PID GC.heap_dump file.hprof` | HPROF heap dump | Generating data for MAT or a heap analyzer |
| JDK Mission Control/JFR | Allocations, live set, GC events, and trends over time | Investigating leaks or prolonged memory growth |
| JConsole/JMX | Heap pools and runtime MBeans | Monitoring memory usage and trends |
| NMT | Native memory categories managed by HotSpot | Investigating memory outside the Java heap |

JFR is useful when you need to see which objects are allocated frequently and how the live set changes over time. JMC can analyze live objects, allocations, and paths to GC roots when the recording is configured appropriately.

Histograms and heap dumps complement each other: a histogram helps identify suspicious classes; a heap dump helps identify specific objects and reference chains.

## 19. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| `jmap: command not found` | JDK is not installed or `JAVA_HOME/bin` is not in PATH | Use the right JDK and verify the executable location |
| `Could not find process` | Wrong PID, process stopped, or different namespace | Use `jps -l`/`ps` to re-identify the process |
| Attach refused | Different user, OS permissions, or attach disabled | Check user, permissions, and runtime configuration |
| Expected class is missing | Class not loaded yet, no instances exist, or wrong PID | Check workload, classloader, and target process |
| Large difference between `-histo` and `-histo:live` | Many uncollected unreachable objects | Compare with the right scope and note the live/all difference |
| Histogram changes drastically between runs | Different workload, different GC timing, or app still warming up | Capture under steady load and record timestamps |
| `byte[]` dominates the heap | Large payloads, caches, serialization, or buffers | Find array owners via heap dump and dominator tree |
| Histogram does not explain RSS growth | Memory growth is outside the Java heap | Check NMT, direct memory, and native allocations |
| Histogram takes a long time to run | Large heap or very high object count | Pick an appropriate window, use `jcmd`, and monitor impact |
| `jcmd GC.class_histogram` reports unknown command | JVM/version does not support that command | Run `jcmd PID help` and check the target JDK |
| Heap dump file cannot be created | Missing write permissions or insufficient disk space | Choose a writable path and verify free disk space |
| Cannot find leak from histogram | Reference retention in object graph is not visible in class counts | Capture a heap dump and inspect dominators and paths to GC roots |

If the attach tool fails, do not conclude that the heap has no issues. Verify the process, user, namespace, and runtime before switching tools.

## 20. Investigation workflow using class histograms

When an application shows signs of heap growth or `OutOfMemoryError`:

1. Identify from error messages and logs whether the issue is Java heap, Metaspace, or native memory.
2. Find the exact PID and record the JDK version, heap limit, collector, and timestamp.
3. Wait for the application to finish warm-up if the situation permits.
4. Capture an initial histogram with `jcmd PID GC.class_histogram` or `jmap -histo:live PID`.
5. Save the output and timestamp.
6. Maintain a steady workload during the observation window.
7. Capture additional histograms and compare by class name, instance count, and bytes.
8. Focus on domain classes or collections that grow steadily.
9. If the owner is unclear, capture a heap dump and analyze dominators/paths to GC roots.
10. If RSS grows while the Java heap remains stable, inspect native memory.
11. Identify the code holding references and the lifecycle that needs fixing.
12. Re-run the same workload to confirm the live set stops growing.

In reports, clearly distinguish between all-objects histograms and live-objects histograms, as the two modes have different meanings. Do not conclude a memory leak from a single class having many instances or from a single snapshot.

## 21. Checklist

- [ ] Identified the exact JVM PID and environment/container.
- [ ] Confirmed attach permissions for the operating account.
- [ ] Used `jmap -histo <pid>` or `jcmd <pid> GC.class_histogram`.
- [ ] Understood the difference between `jmap -histo` and `jmap -histo:live`.
- [ ] Distinguished `jmap`'s default from `jcmd`'s `-all` option.
- [ ] Read instance count, bytes, and class name columns accurately.
- [ ] Understood that `#bytes` is shallow heap, not retained heap.
- [ ] Examined arrays such as `[B`, `[C`, `[I` and internal collections.
- [ ] Captured multiple snapshots under comparable workloads.
- [ ] Avoided running heap inspections too frequently in production.
- [ ] Captured a heap dump when dominators and paths to GC roots were needed.
- [ ] Checked native memory if RSS did not match the Java heap.
- [ ] Protected histograms and heap dumps from unauthorized access.
- [ ] Recorded JDK version, PID, timestamp, workload, and histogram mode.

## 22. References

- Oracle JDK 21 Tool Reference — The `jmap` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jmap.html
- Oracle JDK 21 Tool Reference — The `jcmd` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java Troubleshooting Guide — Diagnostic Tools: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle Java Troubleshooting Guide — Troubleshoot Memory Leaks: https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html

A class histogram is an effective starting point for understanding which objects are occupying the Java heap. Read instance counts and shallow bytes accurately, distinguish reachable objects from uncollected objects, and compare multiple snapshots under a steady workload. When you need to find what is keeping objects alive, move to a heap dump, dominator tree, and paths to GC roots; when process memory grows outside the heap, inspect native memory with the appropriate tools.
