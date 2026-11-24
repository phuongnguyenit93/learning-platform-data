# 12.2. Capturing `GC.class_histogram` and Understanding Object Counts and Bytes per Class

## Objectives

After this lesson, you will be able to:

1. Capture a **class histogram** from a running JVM using `jcmd <PID> GC.class_histogram`, save the output for review, and understand the scope of the metrics.
2. Correctly read the `#instances`, `#bytes`, `class name`, and `Total` columns and how the JVM sorts classes.
3. Distinguish **shallow size** (direct memory of the object itself) from **retained size** (memory that could be reclaimed if an object or group of objects were freed).
4. Explain why large counts of `byte[]`, `String`, collections, or growing instance counts are not by themselves enough to conclude a memory leak.
5. Compare snapshots under equivalent conditions and know when to escalate to a heap dump, GC logs, JFR, or native memory tools.

> **Core takeaway:** `GC.class_histogram` answers the question "How many objects of each class currently exist and how many direct bytes do they occupy on the Java heap?" It does **not** by itself answer "Who is holding these objects?" or "Why have they not been collected by GC?"

## 1. What Is a Class Histogram?

The Java heap holds **object instances** and **arrays** created by the application and the JDK. A class histogram walks the heap, groups objects by runtime class, and prints summary statistics:

- **Class:** the object type name, such as `com.example.Order`, `java.lang.String`, or `[B` (a `byte[]` array).
- **Instance count:** the number of objects of that class at collection time.
- **Bytes:** the total **direct** size (shallow bytes) of objects of that class.
- **Total:** the sum of instances and shallow bytes across the reported rows.

The tool provides a *snapshot*, not a continuous metric, nor does it report allocation rate. The JVM may allocate many temporary objects and reclaim them normally; a histogram taken after collection may no longer contain them.

**Distinguishing the tools:**

| Tool / Data | Best answers which question? | Does not directly provide |
| --- | --- | --- |
| `GC.class_histogram` | How many instances and how many shallow bytes per class? | GC roots, reference graph, retained size, allocation site. |
| `GC.heap_info` / GC metrics | How much heap is used, and how are heap regions/GC behaving overall? | Which specific objects retain memory. |
| `GC.heap_dump` + analysis tool (e.g., Eclipse MAT) | Which objects are alive, reference chains, dominators, retained size? | Continuous trend if you only have a single dump. |
| JFR / Java Mission Control | When and where allocations happen, GC, runtime behavior over time (depending on recording config)? | Full reference map of every object like a heap dump. |
| Native Memory Tracking | Where is native memory tracked by the JVM being used? | Full Java heap object graph or native memory from external libraries not tracked by the JVM. |

**Real-world example:** `java.lang.String` may show 100,000 instances with 2.4 MB shallow bytes, while `[B` occupies tens of MB. There is no contradiction: each `String` object holds a reference to a `byte[]` containing character data (JDK 9+ uses compact strings depending on content). The array portion is **counted in the `[B` row**, not added into the shallow size of the `String` row.

## 2. Prerequisites and Exact Syntax

`jcmd` is included in the **JDK** (not guaranteed in a JRE or minimal runtime image) and sends diagnostic commands to a running Java process. Use a JDK matching the target JVM; the hands-on example below uses **Java 17 or later**, and also applies to Java 21.

First identify the right PID:

```bash
java -version
jcmd -l
jcmd 12345 help GC.class_histogram
```

In the three commands above, **`12345` is only an illustrative PID**. Replace it with the actual application PID; do not use a thread ID, container ID, or the PID of `jcmd` itself. Running `help` against the **target JVM** is the authoritative way to confirm supported options on the running version.

Syntax:

```text
jcmd <PID> GC.class_histogram [options]
```

Examples (Linux/macOS, Windows PowerShell, or `cmd.exe` all support `>` output redirection):

```bash
# Default statistics, written to stdout:
jcmd 12345 GC.class_histogram

# Save stdout to a file in the terminal running jcmd:
jcmd 12345 GC.class_histogram > histo-01.txt

# Include objects that are currently unreachable:
jcmd 12345 GC.class_histogram -all > histo-all.txt

# Request using up to roughly 2 workers for the heap walk:
jcmd 12345 GC.class_histogram -parallel=2 > histo-parallel.txt
```

| Option | Meaning and notes |
| --- | --- |
| No option | Counts objects considered **live/reachable** after HotSpot's corresponding GC handling; default mode may request a **Full GC** before inspection. |
| `-all` | Inspects **including objects that are no longer reachable** at observation time. This is not "live only"; objects awaiting collection can make numbers higher. On HotSpot, this mode usually avoids the default mode's Full GC request, but still scans the heap and thus consumes resources. |
| `-parallel=0` | Default: lets the JVM automatically choose the number of threads for heap inspection. |
| `-parallel=1` | Uses a single inspection thread, disabling parallelization of the inspection step. |
| `-parallel=N` (N > 1) | The JVM **attempts** to use the requested thread count but may use fewer; it is not a guarantee of faster execution or zero pause. |

**Operational warning:** `jcmd` documentation classifies `GC.class_histogram` as **Impact: High**, depending on heap size and contents. A default run can trigger a Full GC and significant pause. In production, choose timing, sample count, and scope carefully; do not run it in a tight loop during peak traffic just to "monitor continuously."

**Common file-writing misconception:** `GC.class_histogram` prints to **stdout**, so `> histo-01.txt` causes the **shell invoking `jcmd`** to create the file. This differs from `GC.heap_dump /tmp/app.hprof`, which instructs the **target JVM** to write an HPROF file to its own filesystem. Do not arbitrarily pass `filename=...` to `GC.class_histogram`; verify valid syntax with `jcmd <PID> help GC.class_histogram`.

### When attaching fails

- `jcmd` typically must run **on the same host** as the target JVM, under the **same effective user/group**, and in an environment that allows attach.
- If the JVM runs inside Docker/Kubernetes, the PID and filesystem seen from the host may differ; `jcmd -l` on the host will not necessarily see processes inside another container namespace. Verify the PID in the proper namespace and use tools provided inside the container or a valid attach mechanism.
- If the image contains only a minimal Java runtime, `jcmd` may be missing; use an appropriate JDK/debug image after confirming connection method, permissions, and version.
- If the JVM has exited, has attach disabled, or is unresponsive, you cannot rely on a `jcmd` invocation to obtain a histogram.

## 3. Reading a Histogram Output

Typical HotSpot output (the counts, class names, and modules below are **illustrative examples only**, not fixed results):

```text
12345:
 num     #instances         #bytes  class name (module)
-------------------------------------------------------
   1:          5100       10500000  [B (java.base@21)
   2:          4000          96000  HistogramDemo$Payload
   3:          1500          36000  java.lang.String (java.base@21)
   4:           600          28800  java.util.HashMap$Node (java.base@21)
   ...
 Total         ...            ...
```

Field-by-field breakdown:

| Field | How to interpret it | Common misinterpretation |
| --- | --- | --- |
| `num` | Row rank, typically sorted by `#bytes` descending. | Treating rank as a fixed class ID; ranking **can change between measurements**. |
| `#instances` | Number of objects/arrays of that class in the snapshot. | Treating it as the total number of objects allocated over the entire JVM lifetime. |
| `#bytes` | Total shallow size **in bytes** of the instances in that specific class row. | Treating it as retained size or the entire object graph referenced by that class. |
| `class name` | Runtime class name; arrays are displayed using JVM internal naming. | Mistaking `[B` for a user class or counting arrays inside the enclosing class. |
| `(module)` if present | Module/version info for certain classes, depending on JDK. | Treating the module text as part of the Java class name. |
| `Total` | Sum of instances and shallow bytes across the histogram rows. | Treating it as total RAM/RSS or the `-Xmx` heap limit. |

**Calculation:** If a row shows `4,000` instances and `96,000` bytes, the average shallow size is `96,000 / 4,000 = 24 bytes/object`. This division applies **only to the data of that snapshot**; it does not show how many bytes those objects retain via references. Arrays can vary in length, so the average shallow size of `[B` instances is not constant.

### Reading array notation

| Histogram name | Java type |
| --- | --- |
| `[B` | `byte[]` |
| `[C` | `char[]` |
| `[I` | `int[]` |
| `[J` | `long[]` |
| `[Z` | `boolean[]` |
| `[Ljava.lang.Object;` | `java.lang.Object[]` |
| `[[I` | `int[][]` (outer arrays holding references to `int[]`) |

**Important:** for `byte[]` or `int[]`, the byte count includes the array header, actual elements, and JVM-dependent padding/alignment, so you cannot simply multiply `#instances × length` if arrays differ in size. For `int[][]`, the JVM stores inner arrays as separate objects; the histogram counts them under their respective array rows.

Classes like `java.lang.String`, `java.util.HashMap$Node`, `[B`, and `[Ljava.lang.Object;` commonly appear at the top in normal applications. **Seeing them at the top does not imply a leak.** Cross-check against workload, reasonable bounds, cache/buffer limits, and trends over time.

## 4. Java 17+ Hands-On: Creating Controlled Growth to Compare Two Snapshots

We intentionally keep strong references to some objects and arrays so they **are not reclaimed by GC** before taking the histogram. This is a measurement demo, not an uncontrolled leak.

Create the file **`HistogramDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;

public class HistogramDemo {
    private static final List<Payload> ITEMS = new ArrayList<>();
    private static final List<byte[]> LARGE_BUFFERS = new ArrayList<>();

    private record Payload(int id, byte[] body) {}

    private static void allocate(int from, int numberOfItems) {
        for (int i = from; i < from + numberOfItems; i++) {
            ITEMS.add(new Payload(i, new byte[512]));
        }
        for (int i = 0; i < 4; i++) {
            LARGE_BUFFERS.add(new byte[1024 * 1024]);
        }
    }

    public static void main(String[] args) throws Exception {
        BufferedReader input =
                new BufferedReader(new InputStreamReader(System.in));

        allocate(0, 2_000);
        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Phase A: items=" + ITEMS.size()
                + ", largeBuffers=" + LARGE_BUFFERS.size());
        System.out.println("Press Enter to grow...");
        input.readLine();

        allocate(2_000, 2_000);
        System.out.println("Phase B: items=" + ITEMS.size()
                + ", largeBuffers=" + LARGE_BUFFERS.size());
        System.out.println("Press Enter to exit...");
        input.readLine();

        System.out.println("Done.");
    }
}
```

Here:

- `Payload` is a valid **record** since Java 16; the nested class name in the histogram is typically `HistogramDemo$Payload`.
- The `ITEMS` list holds references to each `Payload`, and each `Payload` holds a `byte[512]` array; shallow bytes of `Payload` and of `[B` appear in **two separate rows**.
- `LARGE_BUFFERS` holds four `byte[1 MiB]` arrays in phase A, then eight arrays total in phase B. They are aggregated into the `[B` row alongside many other byte arrays created by the JVM/application.
- Both lists are `static` fields, so the objects remain reachable at both measurement points. `readLine()` keeps the process alive so another terminal can run `jcmd`.

### Terminal A — run the program

```bash
javac --release 17 HistogramDemo.java
java -Xms64m -Xmx256m HistogramDemo
```

Output before pressing Enter (PID depends on the machine):

```text
PID=12345
Phase A: items=2000, largeBuffers=4
Press Enter to grow...
```

**Do not press Enter yet.** `12345` is not a fixed PID; use the actual number printed.

### Terminal B — capture snapshot A

```bash
jcmd -l
jcmd 12345 help GC.class_histogram
jcmd 12345 GC.class_histogram > histo-A.txt
```

In Terminal B, `histo-A.txt` is created by the shell in that terminal's working directory; inspect it only after the `jcmd` command finishes.

### Advance to phase B and capture the second time

Return to Terminal A and **press Enter once**. The program prints:

```text
Phase B: items=4000, largeBuffers=8
Press Enter to exit...
```

Keep Terminal A running. In Terminal B:

```bash
jcmd 12345 GC.class_histogram > histo-B.txt
```

Search for the demo class on Linux/macOS:

```bash
grep -F 'HistogramDemo$Payload' histo-A.txt
grep -F 'HistogramDemo$Payload' histo-B.txt
```

Or in Windows PowerShell:

```powershell
Select-String -Path .\histo-A.txt -SimpleMatch 'HistogramDemo$Payload'
Select-String -Path .\histo-B.txt -SimpleMatch 'HistogramDemo$Payload'
```

Single quotes around `HistogramDemo$Payload` prevent the shell from **expanding `$Payload` as an environment variable**. Do not use the `num` rank to match rows between two files; search by **class name**.

### Results to verify

| Metric | Phase A | Phase B | Interpretation |
| --- | ---: | ---: | --- |
| `HistogramDemo$Payload`: `#instances` | About **2,000** | About **4,000** | 2,000 new instances retained by `ITEMS`; in this example counts typically match those exact marks. |
| `HistogramDemo$Payload`: `#bytes` | JVM-dependent | Increases proportionally to instance count | Includes only the shallow size of the record, **excluding** the `body` array it points to. |
| `[B`: `#instances` | JVM-wide dependent | Increases because demo adds **2,000 512-byte arrays** and **4 1 MiB arrays** | Beyond the demo's arrays, the JVM and libraries also have other byte arrays. |
| `[B`: `#bytes` | JVM-wide dependent | Usually rises significantly (over 4 MiB just from the four new large arrays) | Total shallow bytes of **all** live byte arrays, not just the demo's. |

Note that `-Xms64m -Xmx256m` in the example sets the **initial/maximum heap size**, not the expected byte count in the `Total` row. JVM metrics and table ordering vary with JDK, GC, OS, and loaded libraries.

Finally, return to Terminal A and **press Enter again**; final output:

```text
Done.
```

## 5. How Shallow Size Differs from Retained Size

Consider a simple object model:

```text
ArrayList<Payload> ITEMS
    |
    +--> Payload A (id, reference) --> byte[512]
    |
    +--> Payload B (id, reference) --> byte[512]
    |
    +--> ... 
```

- **Shallow size of `Payload A`**: object header, `id` field, `body` reference variable, and padding. Does not include the 512 bytes of data in the array that `body` points to.
- **Shallow size of `byte[512]`**: array header + elements + alignment. Can exceed 512 bytes due to the array object's own overhead.
- **Retained size of an object**: the heap memory that could be freed if that object were no longer reachable, accounting for reference relationships and any other paths to GC roots. If an array is also referenced by another object, the entire array cannot be counted solely toward `Payload A`'s retained size.

Hypothetical example (purely illustrating the math, **not measured output**):

| Class | `#instances` | `#bytes` | Average shallow |
| --- | ---: | ---: | ---: |
| `app.CacheEntry` | 4,000 | 96,000 | 24 bytes/instance |
| `[B` | 4,200 | 2,300,000 | About 548 bytes/array (mixed lengths) |

Do not add `[B`'s `2,300,000` bytes onto `app.CacheEntry`. Some arrays may belong to other objects or be shared. A histogram lacks reference edges to verify array ownership.

**When you need to find the retaining object:** capture an HPROF heap dump, open it in Eclipse MAT, and check **Dominator Tree**, **Retained Heap**, and **Path to GC Roots**, distinguishing strong/weak/soft references. The histogram only helps pick suspect classes for deeper analysis.

## 6. Comparing Histograms to Spot Leak Symptoms

A single measurement shows which classes occupy memory, but diagnosing a memory leak typically requires **multiple snapshots** and operational context.

Recommended workflow:

1. **Confirm the symptom:** post-GC heap keeps climbing, frequent GC pauses, slow service, or OOME; record timestamps, traffic volume, cache/queue sizes, and JDK version.
2. **Choose a consistent method:** compare two default `GC.class_histogram` runs against each other; avoid comparing a `-all` file with a default file and calling the difference a leak.
3. **Sample under equivalent states:** same JVM instance, after warm-up, roughly comparable workload; if possible, capture after the same type of task/batch completes.
4. **Compare by class name and count/bytes columns:** which classes grow significantly, grow consecutively, and fail to drop after processing cycles and GC? Inspect **both instance count and bytes**, because a few huge arrays can matter more than millions of small objects.
5. **Check business expectations:** is cache growth bounded? Do finished request lists still hold references? Are queue backlogs, retry buffers, thread-locals, and listener registries cleaned up properly?
6. **Move to reference-retention evidence:** when abnormal growth persists, use a heap dump/MAT to find GC roots and retained size; use JFR to trace allocation sites, and logs/metrics to confirm lifecycle.

Hypothetical trend example (**not automatic proof of a leak**):

| Class name | Snapshot 1 `#instances` | Snapshot 2 `#instances` | Snapshot 3 `#instances` | What to check next? |
| --- | ---: | ---: | ---: | --- |
| `app.RequestContext` | 10,000 | 25,000 | 42,000 | Check whether finished requests remain held in a registry/queue. |
| `app.CacheEntry` | 8,000 | 9,500 | 10,000 | If the cache is capped at 10,000, it may be reaching steady state. |
| `java.lang.String` | 150,000 | 180,000 | 155,000 | Fluctuates and gets reclaimed; gather more data rather than assuming a leak. |
| `[B` | 25,000 | 30,000 | 27,000 | Check buffer sources and total `#bytes`; count alone is insufficient. |

**Pitfall:** `#bytes` for a class can increase because of more objects, or for **arrays**, because new arrays are longer. Increasing `#instances` may reflect legitimate pending work. If a class is loaded by multiple classloaders, the display name alone cannot distinguish all cases; inspect classloaders in a heap analysis tool.

### Computing deltas properly

For each class, use:

```text
delta_instances = instances_run_2 - instances_run_1
delta_bytes     = bytes_run_2 - bytes_run_1
avg_shallow     = bytes / instances     (if instances > 0)
```

Hypothetical `Payload` example:

```text
Run 1: 2,000 instances, 48,000 bytes
Run 2: 4,000 instances, 96,000 bytes
=> delta_instances = +2,000
=> delta_bytes     = +48,000 bytes
=> avg_shallow     = 24 bytes/instance in both runs
```

This is purely a **formula illustration**. Actual `Payload` figures depend on object layout, alignment, JVM type, and compilation. When comparing multiple classes, match by **class name + classloader if needed**, never by the `num` rank column.

## 7. When to Use `-all` vs. Default

**Default:** suitable when you want to understand the application's **live set** (objects the JVM still considers alive after the associated collection step). On HotSpot, default mode may request a **Full GC**, giving the measurement significant impact. When comparing two default runs, equivalent conditions make results much more meaningful.

**`-all`:** suitable when you want to see uncollected unreachable objects as well, or need to avoid skewing numbers with an explicit Full GC triggered during inspection. However:

- `-all` does **not** mean "zero pauses," "no performance impact," or "all objects are live."
- Unreachable objects can still appear before GC reclaims them; therefore, a class with high `#bytes` under `-all` does not prove long-term retention.
- Do not mix snapshots with and without `-all` to infer business-driven growth; the two modes inspect different object sets.

**`-parallel`:** affects the number of heap inspection threads the JVM attempts to use; it does not change the logical meaning of `#instances`/`#bytes`. Do not assume `-parallel=8` is safer or faster on a production machine.

## 8. Limitations of Histograms and Other Memory Sources

### Heap vs. process RAM

Histograms focus on **objects on the Java heap**. They do not directly measure:

- **Metaspace** (class metadata), code cache, thread stacks.
- Off-heap/native memory allocated outside the Java heap, such as native libraries.
- Total OS/container Resident Set Size (RSS).
- Actual native buffers behind wrappers like `DirectByteBuffer` (the wrapper sits on the heap, while the native allocation is not counted as the wrapper's shallow bytes).

If RSS rises while the heap histogram stays stable, check GC/heap metrics, Native Memory Tracking (if enabled), direct buffers, thread counts, memory mappings, JNI, and OS/container telemetry. **Having no large class row does not mean the JVM cannot hit an OOME**: native memory, metaspace, heap configuration, or container limits can still be exhausted.

### When do you need a heap dump?

If a histogram shows `app.Order`, `HashMap$Node`, `[B`, or a cache growing persistently, the next question is usually "Which object is keeping them alive?" When authorized, with sufficient storage and acceptable pause impact, you can capture:

```bash
jcmd 12345 GC.heap_dump /tmp/app-12345.hprof
```

This is **a different tool**; the HPROF file is written on the target JVM's filesystem, can be very large, can cause a major pause, and contains sensitive application data. Use a tool like Eclipse MAT to inspect the dominator tree, retained heap, and paths to GC roots. Never use a histogram as a substitute for finding owners/roots.

### When do you need JFR or GC logs?

- **Suspecting heavy temporary allocations:** JFR allocation events/samples or a profiler are suitable for hot allocation paths; live histograms may not show objects already collected by GC.
- **Suspecting GC is causing slowdowns:** GC logs and metrics reveal pause durations, frequency, and post-GC heap levels.
- **Suspecting native memory:** Native Memory Tracking, when enabled, covers JVM-tracked regions, though it does not cover every native allocation from external libraries.

## 9. Common Issues and Troubleshooting

| Symptom | Common cause | How to verify / handle |
| --- | --- | --- |
| `jcmd` not found | Machine/container has only a runtime image, missing JDK tools, or wrong `PATH`. | Install/use a matching JDK; verify `java -version` and `jcmd` location. |
| `jcmd -l` does not see the JVM | Different PID namespace, different user, process exited, or attach restricted. | Identify the real PID and effective user inside the JVM environment; check attach settings. |
| Command takes a long time, service pauses | Very large heap, many objects; default mode may require a Full GC. | Reduce capture frequency, run during low traffic, coordinate operations plan; watch GC logs. |
| Snapshot B has fewer instances than A | GC, workload changes, cache eviction, completed tasks, or mismatched capture modes. | Verify same JVM, same options, GC timing, and load; take additional controlled samples. |
| `[B` is at the top, unknown owner | Histogram does not store owner/reference relationships. | Analyze HPROF in MAT with GC roots; separate arrays belonging to `String`, buffers, serialization, and caches. |
| Expected class not visible | No live instances, nested class has `$`, wrong package, or GC reclaimed them. | Check runtime class name, workload, sampling time; search for substrings in the output file. |
| Histogram file does not appear inside container | `>` writes on the machine/shell invoking `jcmd`, not the JVM's filesystem. | Check the terminal's working directory and write permissions; do not confuse with `GC.heap_dump`. |
| Class row grows continuously | Could be legitimate backlog/caching or a real leak. | Check business caps, measure after workload settles, and find retaining paths. |

**Data security:** a histogram can expose package names, internal classes, modules, and operational characteristics. Heap dumps are even more sensitive because they can contain object data. Share, store, and delete them strictly under appropriate access policies.

## 10. Self-Check

1. A row has `#instances=2,000` and `#bytes=48,000`. Average shallow size? **24 bytes/object**.
2. Does `#bytes` for `app.Customer` include the arrays and objects each `Customer` points to? **No.** Pointed-to objects appear in their own class rows; histograms do not record owners.
3. Why is `[B` often large? Because many components (strings, buffers, encoding/serialization data, etc.) use `byte[]`; evaluate against workload and the heap graph rather than assuming a leak.
4. Should you compare a default histogram with a `-all` histogram to conclude growth? **No**; `-all` can include already-unreachable objects.
5. Is `GC.class_histogram` a low-cost periodic monitoring tool? **No**; documentation classifies it as Impact: High, and default mode may request a Full GC.
6. When suspect object counts increase across multiple snapshots, what is the next step? **Verify workload/cache/GC**, then use a heap dump/MAT to find retaining paths and GC roots if the symptom persists.

## References

- [Oracle Java 21 — `jcmd` (`GC.class_histogram`, `-all`, `-parallel`, Impact: High)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle Java 21 — Diagnostic Tools (using `jcmd`, reading heap histograms)](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html).
- [Oracle — Troubleshoot Memory Leaks (histograms across measurements and when deeper analysis is needed)](https://docs.oracle.com/en/java/javase/23/troubleshoot/troubleshooting-memory-leaks.html).
- [OpenJDK HotSpot — how `ClassHistogramDCmd` handles `-all` and GC requests](https://code.googlesource.com/edge/openjdk/+/refs/heads/master/hotspot/src/share/vm/services/diagnosticCommand.cpp).
