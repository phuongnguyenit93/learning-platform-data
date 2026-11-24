# 12.5. Distinguishing Live Objects from All Recorded Objects and GC Triggering Behavior

## Objectives and Scope

In **Java heap dump and memory leak diagnostics**, choosing between "live objects only" and "all objects currently in the heap" changes the **collected data**, the **meaning of conclusions**, and **whether the collection command requests garbage collection (GC)**. Without recording the dump mode, a heap dump full of "garbage" objects can easily be misread as a memory leak; conversely, a live-only dump may have already discarded traces of a temporary allocation burst just before capture.

This lesson primarily uses **HotSpot on JDK 17+**, `jcmd`/`jmap` commands, and Eclipse Memory Analyzer (MAT). Specific behavior must be verified against the running JDK version, garbage collector, and configuration; do not assume every JVM shares identical options.

## 1. What Is a "Live Object"?

The Java heap stores instances and arrays. The garbage collector determines their reachability from **GC roots**, such as references on Java threads, `static` fields, JNI global references, and JVM-managed roots. Conceptually:

```text
GC roots
   ├──> singleton/static cache ──> Object A ──> Object B    (reachable)
   └──> thread/local variable ──> Object C                 (reachable)

Object D ──> Object E                                     (no path from GC root)
```

- **Reachable/live (as determined by the JVM/GC at measurement time):** an object still held by a valid reference chain from roots and belonging to the set the GC must retain—for example A, B, and C. In practice, additional rules govern weak/soft/phantom references, finalization, and collector type; do not equate "live" with "every variable that ever pointed to the object."
- **Unreachable but not yet reclaimed:** an object that no longer has a valid reference path from GC roots, yet the GC has not reclaimed its memory. For example, D and E may still reside in the heap before the next collection. They are **eligible for collection**, which does not mean they vanish the instant a variable is assigned `null`.
- **Already reclaimed by GC:** the object no longer exists in the active heap; a heap dump taken afterward **cannot recover** reclaimed objects.
- **"All objects" in a heap dump:** every object that the dump mechanism records as **still present in the Java heap at snapshot time**, including reachable objects and, if still present, unreachable ones. It does not mean "every object ever created by the application since startup."

A **live object is not automatically a memory leak**: it may be a valid cache, session data, or request-handling state. Conversely, an unreachable object still sitting in the heap merely reflects **uncollected garbage**, not a leak.

## 2. How Do a Live Dump and an All-Objects Dump Differ?

| Aspect | Live-only heap dump | All-objects heap dump |
| --- | --- | --- |
| Selected object set | Only objects the JVM determines are live/reachable during the collection process | Objects remaining in the heap, including currently unreachable objects |
| Objects already reclaimed by GC before snapshot | Absent | Also absent |
| Data about uncollected garbage | Usually absent after GC selects the live set | May be present if GC has not reclaimed it before the snapshot |
| Preferred use | Tracing retained objects, GC roots, retained heap, suspected leaks | Investigating temporary allocation bursts, garbage awaiting collection, pre/post-GC differences |
| Interpretation risk | Losing transient/unreachable evidence due to pre-dump GC | Easily equating "present in dump" with "being retained" |
| HPROF size | Often smaller when garbage is cleared beforehand | Can be larger due to containing unreachable objects |
| Proves a leak on its own? | No; requires retention paths and trend observation | No; unreachable objects are not a leak |

**Note:** You cannot guarantee an `all` dump is always larger than a `live` dump if captured at different times. GC may have run, the application keeps allocating, and the measurement itself alters state. Comparisons must record timestamps, load, configuration, and dump mode.

### Illustrative scenario

Suppose at time `t0`, a cache holds 12 MB of reachable objects, and a batch just dropped all references to 35 MB of temporary arrays, which GC has not yet reclaimed.

- **An all dump captured right then** may contain both the 12 MB cache and the 35 MB of temporary arrays. The presence of those 35 MB does not mean a GC root is holding them.
- **A live dump with GC before the snapshot** may contain only the cache and other reachable objects. The temporary arrays were reclaimed and will not appear.
- **If the cache grows continuously** across multiple post-GC points, and MAT shows a reference path holding the cache from a static root, then you have stronger evidence of abnormal retention.

These numbers illustrate observation scope; real HPROF files also contain JVM objects, the object graph, and metadata, so do not estimate file size simply by summing the illustrative figures.

## 3. `jcmd GC.heap_dump` Options and Full GC Triggering

In **HotSpot JDK 17**, the `jcmd` documentation explicitly states: **`GC.heap_dump` requests a Full GC by default, unless `-all` is specified**. This should be noted in every investigation report. "Requests a Full GC" describes the tool's behavior; collector implementation and actual impact depend on the JVM, so never promise a fixed pause duration.

### 3.1. Default dump: live objects prioritized, requests Full GC

```bash
jcmd 12345 GC.heap_dump /tmp/heap-live.hprof
```

- `12345` is an example PID of the target Java process; replace it with the real PID.
- The JVM **requests a Full GC** before creating the HPROF under the command's default behavior. This can reclaim unreachable objects, altering heap usage and snapshot contents.
- Best suited when focusing on **objects retained after GC**, paths to GC roots, and retained heap.
- Do not use this mode if your goal is to preserve evidence of uncollected garbage right at the symptom moment; the tool-requested GC can wipe out that evidence.
- The command has **high impact**; the requested GC, dump creation, and I/O can cause substantial latency.

### 3.2. `-all` dump: can record unreachable objects, does not request Full GC from the command

```bash
jcmd 12345 GC.heap_dump -all /tmp/heap-all.hprof
```

- The `-all` option instructs the JVM to dump **all objects, including unreachable objects** currently present in the heap according to the JVM's capture mechanism.
- On JDK 17, choosing `-all` means **this command does not request a Full GC** before dumping. This is **not a guarantee that "no GC will occur"**: the application or JVM can still trigger GC due to allocation load or other reasons during observation.
- `-all` also **does not mean the operation will not pause the application**. Heap inspection/dumping can still trigger safepoints, pauses, and CPU/disk overhead even without requesting a Full GC.
- Choose this when inspecting unreachable objects **not yet collected**, or when avoiding a default-command Full GC that would clear the state under investigation.

`/tmp/heap-*.hprof` is a Linux/macOS path example. On Windows, use an absolute path such as `C:/dumps/heap-all.hprof`. Paths are resolved in the **target JVM's environment**, so write permissions and disk space are required on the corresponding host/container/namespace.

### Quick decision table for `jcmd`

| Command | Snapshot scope | Requests Full GC before dump? |
| --- | --- | --- |
| `jcmd PID GC.heap_dump FILE` | Live objects by default | **Yes**, per HotSpot JDK 17 documentation |
| `jcmd PID GC.heap_dump -all FILE` | Includes unreachable objects if still in heap | **No**, due to the `-all` option |
| `jcmd PID GC.class_histogram` | Class-level instance/byte counts in default mode | Do not infer GC behavior from the name alone; check logs/JDK |
| `jcmd PID GC.class_histogram -all` | Histogram including unreachable objects | `-all` here changes counting scope; histograms contain **no** object graph |
| `jcmd PID GC.run` | **Does not create a heap dump**; calls `System.gc()` | A separate GC request; do not run to "inspect" when preserving scene state |

`PID` and `FILE` in the table are **placeholders**; actual execution requires a numeric PID and concrete path as in the two examples above. On the running JVM, verify supported syntax with `jcmd 12345 help GC.heap_dump`.

## 4. `jmap`, Dump on `OutOfMemoryError`, and Limitations of Each Source

### `jmap`

JDK 17 also includes these commands:

```bash
jmap -dump:live,format=b,file=/tmp/jmap-live.hprof 12345
jmap -dump:format=b,file=/tmp/jmap-all.hprof 12345
```

In `jmap` documentation, `live` selects only live objects; **omitting `live` dumps all objects**. This defines the data scope, **not a substitute** for verifying whether GC actually ran during the command. To confirm GC on a real process, check GC logs; for the two `jcmd GC.heap_dump` options above, JDK 17 documents the Full GC request explicitly. `jmap` is documented as experimental/unsupported, so prefer `jcmd` on standard HotSpot deployments.

### Automatic dump on `OutOfMemoryError`

You can configure the JVM to save an HPROF on OOME:

```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/oom.hprof -jar app.jar
```

This is an **incident-time dump**, not a deliberate `jcmd -all` or default `jcmd` capture. When OOME occurs because the Java heap cannot allocate, the JVM **has usually already attempted GC to free space**, so the incident dump may contain very few unreachable objects. There are also cases where GC did not run before OOME; do not guess without logs. An OOME can also involve native memory or Metaspace, in which case a Java heap HPROF does not capture the entire cause.

**Do not call `System.gc()` or `jcmd GC.run` before collection just to "make the numbers cleaner."** Doing so can alter the very objects and traces under investigation. If you need a post-GC live set, state that goal and use the appropriate dump mode.

## 5. Java 17+ Hands-On: Retained Objects vs. Dereferenced Objects

Create the file **`HeapDumpScopeDemo.java`**:

```java
public class HeapDumpScopeDemo {
    // volatile to preserve an observable reference path from the static field.
    private static volatile byte[][] retained;
    private static volatile byte[][] temporary;

    private static byte[][] allocate(int count, int bytesPerArray) {
        byte[][] result = new byte[count][];
        for (int i = 0; i < count; i++) {
            result[i] = new byte[bytesPerArray];
        }
        return result;
    }

    public static void main(String[] args) throws InterruptedException {
        retained = allocate(8, 256 * 1024);      // ~2 MiB still reachable
        temporary = allocate(160, 256 * 1024);   // ~40 MiB temporarily referenced
        temporary = null;                       // drop temporary reference path

        System.out.println("Retained arrays: " + retained.length);
        System.out.println("PID: " + ProcessHandle.current().pid());
        Thread.sleep(120_000);                  // allow capturing dumps from another terminal
    }
}
```

Compile and run from the first terminal:

```bash
javac -encoding UTF-8 HeapDumpScopeDemo.java
java -Xms128m -Xmx128m -XX:+UseSerialGC \
  -Xlog:gc=info \
  HeapDumpScopeDemo
```

On Unix shells, trailing `\` continues the command across lines; in PowerShell, enter the entire `java` command on one line. The program prints the exact line `Retained arrays: 8`; the PID depends on the process. The program then keeps the JVM alive for about 120 seconds.

In a second terminal, replace `12345` with the printed PID:

```bash
jcmd 12345 GC.heap_dump -all /tmp/demo-all.hprof
jcmd 12345 GC.heap_dump /tmp/demo-live.hprof
```

**What to understand when observing:**

1. `retained` is a `static` field holding an 8-element array, each pointing to a `byte[]`; these arrays remain reachable.
2. After `temporary = null` and execution moves on, the cluster of 160 arrays becomes **unreachable** and eligible for GC reclamation. Assigning `null` **does not run GC by itself**.
3. If GC has not reclaimed them yet, a `-all` dump **may** record those unreachable arrays. The default dump requests a Full GC, so it may no longer contain them.
4. **Do not assume fixed object counts, file sizes, GC counts, or `jcmd` stdout**: the JVM can trigger GC during allocation or before a snapshot. Results vary by environment.
5. Two sequential dumps are **not an independent A/B experiment**: the first dump, natural GC, or the second dump changes heap state. For cleaner comparisons, restart under equivalent conditions and inspect GC logs in parallel.

This example illustrates **reachability and the difference between the two commands**. It does not intentionally leak: once the `temporary` reference is dropped, the arrays' memory can be reused after GC.

## 6. Opening HPROF in Eclipse MAT: Why Can "All" Look Like "Live"?

This is an entirely separate layer: **the analysis tool's parser mode**, not the JVM's collection mode.

According to Eclipse Memory Analyzer documentation, when opening a dump, MAT **excludes unreachable objects from the object graph during parsing by default**, since they are usually unnecessary for memory leak analysis. MAT still provides an **Unreachable Objects** histogram, but the object graph of excluded objects cannot be traversed in a default parse session.

Consequences:

- A `-all` file may indeed contain unreachable objects, yet **MAT's default Histogram and Dominator Tree do not show all of them** because MAT filtered them out while building its index.
- The **Unreachable Objects histogram** shows classes and counts of unreachable objects MAT recorded; in default parse mode, you cannot trace individual excluded objects through the graph from that histogram.
- To inspect unreachable objects in detail inside an all-objects dump, enable **Keep unreachable objects** under **Window → Preferences → Memory Analyzer**, delete old snapshot index files if necessary, and reopen the dump to **re-parse**. Ensure the original file was captured in a mode that records unreachable objects; MAT's option cannot resurrect objects reclaimed by GC before the dump.
- **Keep unreachable objects** is an analysis-tool setting on an existing file; **it does not trigger GC on the target application**. Conversely, `jcmd -all` affects how the JVM collects data and does not force MAT to keep unreachable objects in the graph.

When investigating leaks, MAT offers several useful views:

- **Histogram:** counts/`shallow heap` by class; an object's shallow size excludes the objects it references.
- **Dominator Tree / Retained Heap:** identifies groups of objects retained by an influential owner/root. Retained heap estimates the memory that would become collectible if a dominant object or group were freed, within the graph MAT is analyzing.
- **Path to GC Roots:** traces why an object remains held (e.g., `static Map`, `ThreadLocal`, or an unregistered listener).

**Never shout "Leak!" just because a class has many instances in an all dump.** First separate unreachable objects from objects held by valid reference paths, then evaluate growth over time.

## 7. Verifying Exactly Whether GC Ran During a Dump

When launching an application under investigation, enable GC/safepoint logs (for example):

```bash
java -Xms128m -Xmx128m \
  -Xlog:gc*=info,safepoint=info:file=gc-events.log:time,uptime,level,tags \
  HeapDumpScopeDemo
```

After running `jcmd`, correlate timestamps across command execution, GC log entries, and HPROF write times.

**How to read safely:**

- When running default **`GC.heap_dump`**, JDK 17 docs state the command **requests a Full GC**. Confirm in the logs whether a matching GC event occurred, its GC type, pause duration, and actual heap delta; never deduce pause time solely from a file's existence.
- When running **`GC.heap_dump -all`**, the command **does not request a Full GC**. However, if logs still show GC around that time, check whether natural GC, allocation thresholds, or another operation triggered it.
- `-all` is **not a non-stop mode**: capturing the heap still incurs pauses and resource costs. Check application latency, GC/safepoint logs, and dump duration.
- Use `jcmd 12345 help GC.heap_dump` to check options on your specific JVM. Never assume identical behavior across different collectors, versions, and vendors without testing.

Illustrative log example (**not fixed output**):

```text
[10.000s][info][gc] GC(3) Pause Full (Diagnostic Command) 45M->6M(128M) 87.123ms
```

Actual messages may differ; the key skill is recognizing **GC cause**, **heap before/after**, and **pause duration** rather than guessing from a filename. Some collectors report multiple phases or different wording.

## 8. Choosing a Strategy by Diagnostic Goal

| Practical question | Preferred capture approach | How to interpret |
| --- | --- | --- |
| Why does post-GC heap stay high or climb across cycles? | Live dump, GC logs, multiple sample points at equal load | Check retained heap, Dominator Tree, GC roots; distinguish valid caches from abnormal retention. |
| Is the app creating lots of short-lived objects awaiting GC? | All dump if you need pre-GC unreachables; also measure allocation/GC via JFR and GC logs | Unreachables in a dump do not prove a leak; use allocation rate and collection stats to understand churn. |
| Need to preserve the scene right before GC cleans up garbage? | `jcmd GC.heap_dump -all` while recording timestamp, load, and GC logs | Command does not request Full GC, though natural GC and capture pauses still apply. |
| HPROF generated after `OutOfMemoryError` | OOME dump + GC logs + detailed OOME message | GC was usually already attempted before the error; dump is not guaranteed to contain prior garbage. |
| Histogram class is huge, no paths to GC roots | Check MAT parser settings and Unreachable Objects | May be unreachable objects filtered by MAT; enable Keep unreachable before re-parsing if needed. |
| Heap dump looks normal but process RSS is high | Native Memory Tracking, thread stacks, direct memory/Metaspace, OS metrics | A Java heap HPROF does not cover all native memory types. |

To investigate leaks systematically, record **JDK/collector, PID, heap flags, timestamp, system load, exact dump command, and GC log state**. In MAT, locate **reference paths keeping objects alive** and changes *after GC* across observations under comparable conditions.

### Minimum workflow when a memory leak is suspected

1. Check the **symptom**: steady post-GC heap climb, increasing GC frequency, OOME, or merely temporary allocation bursts.
2. Choose scope: to examine *objects still retained*, use live; to preserve traces of *uncollected unreachables*, use `-all`.
3. Prepare **disk space and capture timing**; avoid taking multiple large dumps in production during peak load without assessing impact.
4. Run the chosen command while saving GC/safepoint logs and recording **whether the dump command did/did not request a Full GC**.
5. Open the HPROF in MAT, verify the **Keep unreachable objects** setting matches your goal, and examine Histogram, Dominator Tree, and Path to GC Roots.
6. If confirming a leak, verify the **retained object graph** and **trend over time**; cross-check allocation code, cache eviction, listeners, `ThreadLocal`, lifecycle, or the specific retaining root.

## 9. Common Mistakes

1. **"An all dump means every object ever created."** False: objects already reclaimed by GC before the snapshot do not come back in HPROF.
2. **"An unreachable object appearing in a dump means a leak."** False: it is usually garbage waiting to be collected.
3. **"A live object appearing in a dump means a leak."** False: the object may be legitimately in use.
4. **"`-all` guarantees zero GC and zero pause."** False: `-all` only omits the Full GC request from `jcmd GC.heap_dump` in JDK 17; the JVM can still GC for other reasons and dumping itself consumes resources.
5. **"A default heap dump does not affect the running program."** False: default `jcmd GC.heap_dump` requests a Full GC; heap state and GC logs can change before the snapshot.
6. **"If MAT does not show unreachable objects, the file does not contain them."** False: MAT filters unreachable objects by default during parsing; check how the dump was taken and the Keep unreachable option.
7. **"Comparing the file size of two consecutive dumps proves a leak."** False: timing, workload, automatic GC, tool-triggered Full GC, and runtime objects all vary.
8. **"Just run `System.gc()` before dumping to make it clean."** Doing so can destroy transient evidence and add pauses; only force GC with clear intent.
9. **"HPROF reflects total process RAM."** False: direct/native memory, Metaspace, and other regions require their own tools.
10. **"Having a histogram is enough to find the leak root."** False: histograms provide class-level aggregates; understanding retention requires analyzing the object graph and GC roots.

## 10. Self-Check Questions

**Question 1.** A temporary `List<byte[]>` was just dereferenced and GC has not run yet. Can the arrays appear in `jcmd PID GC.heap_dump -all FILE`?  
**Answer:** Possibly, if they are still present in the heap when the snapshot is created. That does not by itself prove a leak.

**Question 2.** Does `jcmd PID GC.heap_dump FILE` on HotSpot JDK 17 request a Full GC?  
**Answer:** Yes, by default; `-all` is the option that **avoids requesting a Full GC from the dump command**.

**Question 3.** Does `-all` guarantee zero pause?  
**Answer:** No. Natural GC can still occur, and heap inspection plus writing HPROF still carries cost and can pause the application.

**Question 4.** An HPROF file was captured with `-all`, yet MAT shows only reachable objects. Why?  
**Answer:** MAT discards unreachable objects during parsing by default; inspect Unreachable Objects and enable Keep unreachable objects if you want their graph preserved.

**Question 5.** Seeing 500 MB of unreachable objects in one snapshot is proof of a leak?  
**Answer:** Not yet. You must examine why they existed prior to GC and their trend. Java heap leaks are typically proven by objects still retained from GC roots and abnormal growth in the live set.

**Question 6.** The JVM just hit OOME; why doesn't the dump show the temporary allocation burst before the failure?  
**Answer:** One or more GCs likely reclaimed unreachable objects before the dump was written; HPROF does not record a full allocation history.

## Official References

- [Oracle JDK 17 — `jcmd`, `GC.heap_dump` and `-all` section](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle JDK 17 — `jmap`, `-dump:live` and all objects section](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jmap.html)
- [Oracle JDK 17 — `java`, `HeapDumpOnOutOfMemoryError` and `HeapDumpPath`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle JDK 17 — Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-memory-leaks.html)
- [Eclipse Memory Analyzer — Unreachable Objects](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/unreachable_objects.html)
- [Eclipse Memory Analyzer — Keep unreachable objects](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/tasks/configure_mat.html)
