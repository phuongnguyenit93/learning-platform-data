# Heap Histograms, Heap Dumps, and Collection Overhead

When a Java application exhibits abnormal heap growth, creates more objects than expected, or encounters `OutOfMemoryError`, you need to know which classes are consuming memory and which objects are retaining other objects. Java 17 provides diagnostic tools such as **heap histograms**, **heap dumps**, and **Java Flight Recorder (JFR)** to answer those questions.

These three data sources serve different purposes:

- **Heap histogram** summarizes instance counts and total shallow size by class. It helps quickly locate classes occupying a large share of the heap.
- **Heap dump** captures the heap's object graph at a point in time. Analysis tools can find reference paths, dominators, and retained sizes.
- **JFR recording** captures time-series events such as allocations, garbage collection, threads, locks, and I/O. It helps pinpoint when and which operations lead to memory pressure.

Collecting heap data has overhead. Histogram and dump commands may require the JVM to pause at a safepoint, traverse huge numbers of objects, run a Full GC, or write very large files. In production, choose the right level of data, timing, and storage location carefully.

## 1. What Is a Heap Histogram?

A heap histogram is a summary table of objects managed on the Java heap, grouped by class. Each row typically displays:

| Column | Meaning |
| --- | --- |
| `num` | Row number in the output. |
| `#instances` | Number of instances of the summarized class. |
| `#bytes` | Total shallow size of instances belonging to that class. |
| `class name` | Class name; may include module or loader details depending on formatting. |

Illustrative example:

```text
 num      #instances       #bytes  class name
------------------------------------------------
   1          85000       6800000  byte[]
   2          42000       3360000  java.lang.String
   3          12000       1920000  com.example.Order
   4           8000       1280000  java.util.HashMap$Node
   5           4000        640000  com.example.Customer
------------------------------------------------
Total:       151000      14000000
```

These numbers are solely to illustrate how to read the table, not benchmark results or default JVM figures.

### 1.1. Shallow Size vs. Retained Size

`#bytes` in a histogram is the total **shallow size** of instances of that class. Shallow size is the memory of the object itself, excluding the other objects it references.

Example:

```text
Order
  ├── Customer
  ├── Item[]
  │    ├── Item
  │    └── Item
  └── Metadata
```

A histogram tells you how many `Order`, `Customer`, `Item[]`, and `Item` instances exist, along with the shallow bytes for each class. It does not tell you how many other live objects a specific `Order` keeps alive.

**Retained size** is the amount of memory that would be freed if an object (or dominated set of objects) became unreachable from GC roots. To analyze retained size and reference paths, you generally need a heap dump and a heap analysis tool.

Do not sum a class's `#bytes` and call it retained size. The two concepts measure different things.

### 1.2. What Histograms Can and Cannot Answer

Histograms are useful for answering:

- Which classes have the most instances?
- Where are total shallow bytes per class concentrated?
- Are there more `byte[]`, `char[]`, `String`, collection nodes, or DTOs than expected?
- After a change or load phase, which class groups grew sharply?

Histograms do not directly answer:

- Which objects are holding references to those instances?
- Why does an object remain reachable?
- Which reference path leads from a GC root to the object?
- What is the retained size of a specific object?
- Is a rapidly growing class a memory leak or simply a valid cache/batch?

To answer the second group of questions, analyze a heap dump and correlate it with business lifecycles.

## 2. Capturing a Heap Histogram with jcmd

On JDK 17, `jcmd` is the appropriate JVM diagnostic tool for invoking diagnostic commands on a running process.

List JVMs visible to the tool:

```bash
jcmd -l
```

The output displays process IDs and Java process details. Once you identify the exact PID, query command syntax:

```bash
jcmd 12345 help GC.class_histogram
```

Replace `12345` with the actual PID.

### 2.1. Histogram of Live Objects

Command:

```bash
jcmd 12345 GC.class_histogram
```

Under the default behavior of the diagnostic command, the histogram counts only live objects and the JVM requests a Full GC prior to inspecting the heap. This eliminates unreachable objects before counting, but it can incur a significant pause and GC cost.

This is why you must weigh the timing of running the command on latency-sensitive systems or large heaps.

### 2.2. Histogram Including Unreachable Objects

You can request inspecting all objects, including unreachable objects not yet collected:

```bash
jcmd 12345 GC.class_histogram -all
```

`-all` changes the meaning of the statistics: results can include objects eligible for GC collection. Therefore, counts and bytes may be higher than a live-object histogram. This option avoids requesting a Full GC just to filter out unreachable objects before collecting the histogram, though the JVM still has to perform the heap inspection work.

When comparing two histograms, clearly note whether `-all` was used. Comparing live-object results with all-object results as if they were the same metric leads to wrong conclusions.

### 2.3. Interpreting Results

Suppose a histogram displays:

```text
  #instances       #bytes  class name
       90000      7200000  byte[]
       50000      4000000  java.lang.String
       10000      1600000  com.example.Session
```

Observations:

- `byte[]` accounts for the largest total shallow bytes among the rows shown.
- `String` has a high instance count; investigate whether they belong to caches, requests, log buffers, or business data.
- `Session` may warrant attention if its count grows over time or fails to drop after sessions expire.

However, you cannot conclude `Session` is leaking from a single snapshot alone. Compare multiple timestamps under equivalent load, inspect post-GC heap usage, and trace references in a heap dump if necessary.

## 3. What Is a Heap Dump?

A heap dump is a data recording describing the heap at a point in time, typically in **HPROF** format. It contains information about classes, instances, arrays, and reference relationships sufficient for an analysis tool to reconstruct the object graph.

Unlike a histogram that only aggregates by class, a heap dump allows tools to investigate:

- Which exact object instances exist.
- Which object references which other object.
- Paths from GC roots to a specific object.
- Dominator trees and retained sizes.
- Which instances retain collections, caches, listeners, or sessions.

Heap dumps are usually large and sensitive. They can contain strings, request payloads, user data, tokens, or business data residing in memory. Treat dump files as sensitive production data.

### 3.1. How Histograms and Heap Dumps Differ

| Criterion | Heap Histogram | Heap Dump |
| --- | --- | --- |
| Data | Instance counts and shallow bytes per class | Object graph and reference relationships |
| Output size | Usually small, text table format | Can be very large, typically an HPROF file |
| Find classes using large heap | Yes | Yes, via analysis tools |
| Find objects retaining others | Not directly | Yes |
| GC roots/dominator analysis | No | Yes |
| Overhead | Can be high; default live histogram requests a Full GC | Usually high; default live dump requests a Full GC and writes a file |
| Sensitive data risk | Lower, though class names may still be exposed | Higher because it contains object contents |

Start with a histogram when you need to quickly narrow down classes occupying the heap. Switch to a heap dump when you need to find why objects stay alive, reference paths, or retained sizes.

## 4. Creating a Heap Dump with jcmd

Diagnostic command:

```bash
jcmd 12345 GC.heap_dump /var/tmp/app-heap.hprof
```

This creates an HPROF heap dump at the specified path.

Without the `-all` option, the JVM dumps only live objects and requests a Full GC before creating the dump. This focuses the dump on reachable objects, but can pause the application for a significant duration.

On Windows systems, use an appropriate path, for example:

```powershell
jcmd 12345 GC.heap_dump C:\temp\app-heap.hprof
```

The parent directory must exist and the account running the JVM must have write permissions.

### 4.1. Dumping Unreachable Objects with -all

To include unreachable objects not yet collected:

```bash
jcmd 12345 GC.heap_dump -all /var/tmp/app-all-objects.hprof
```

When `-all` is used, the JVM does not request a Full GC solely to filter live objects before dumping. The dump may contain more objects and reflect objects eligible for GC. This can be useful for certain investigations into object allocations/uncollected objects, whereas for finding retained heap or memory leaks, live-object dumps are usually easier to interpret.

Always record this option when saving or sharing results so analysts know which set of objects the dump represents.

### 4.2. Compressing Heap Dumps

JDK 17 supports compressing heap dump output via the `-gz` option:

```bash
jcmd 12345 GC.heap_dump -gz=1 /var/tmp/app-heap.hprof.gz
```

Compression levels range from 1 to 9. Higher levels generally reduce file size further at the cost of extra CPU and compression time. Choose a compression level based on disk limits, allowable time, and decompression/analysis support in downstream tools.

Compression does not make collection free; the JVM still has to traverse the heap and serialize dump data.

### 4.3. Avoiding Accidental Overwrites

If the target file already exists, the command may refuse to overwrite it. Only use `-overwrite` when you are certain the old file is no longer needed:

```bash
jcmd 12345 GC.heap_dump -overwrite /var/tmp/app-heap.hprof
```

In incident workflows, filenames including a timestamp and process ID help prevent overwriting data from previous collections.

### 4.4. Verifying Syntax and Options

Do not rely on syntax memorized from an old script without verifying the running JDK version. Query the target JVM directly:

```bash
jcmd 12345 help GC.heap_dump
jcmd 12345 help GC.class_histogram
```

Options such as `-all`, `-gz`, `-overwrite`, and `-parallel` must be used according to what the target JVM's diagnostic command supports.

## 5. Analyzing Heap Dumps

HPROF files are typically opened with a heap analysis tool such as Eclipse Memory Analyzer (MAT) or another HPROF-compatible analyzer.

A typical analysis workflow includes:

1. Open the dump and wait for the tool to build indexes.
2. Inspect the histogram to identify classes with many instances or high shallow bytes.
3. Inspect the dominator tree to find objects retaining the most memory.
4. Check the retained size of notable dominators.
5. Open paths to GC roots to understand why objects remain reachable.
6. Cross-reference with business lifecycles and code managing caches/sessions/listeners.

### 5.1. Dominator Tree

An object A dominates object B if every path from GC roots to B passes through A. If A and references keeping B alive exclusively through A were removed, B would become unreachable.

The dominator tree helps locate objects holding the majority of the heap. Example:

```text
GC Root
  └── ApplicationContext
       └── CacheManager
            └── UserCache
                 ├── User 1
                 ├── User 2
                 └── User ...
```

If `UserCache` retains millions of un-evicted users, the cache's retained size can be huge. The next questions then concern eviction policies, TTL, invalidation, and whether the cache holds unintended references.

### 5.2. Paths to GC Roots

Reference paths to GC roots show why an object remains alive. Common roots may involve:

- Static fields of a class.
- Thread stacks or held local variables.
- JNI/global references.
- Class loaders or runtime structures retaining objects.

When an object whose lifecycle should have ended remains reachable, the reference path usually points to the component holding it. Read the path with application context; an active reference is not necessarily a bug if the object legitimately belongs to a valid cache or active request.

### 5.3. Shallow Size and Retained Size in Analysis Tools

An object can have a small shallow size yet a huge retained size if it dominates many other objects. For instance, a `HashMap` may occupy few bytes itself while holding references to hundreds of thousands of values.

Conversely, a `byte[]` can have a large shallow size without referencing any other objects. A histogram shows the total bytes of those arrays; a heap dump identifies who holds each array and whether they are released on time.

## 6. Cost of Collecting a Heap Histogram

A heap histogram is usually much lighter than a heap dump in terms of output written, but it should not be treated as a free measurement.

### 6.1. Heap Traversal

To count objects and sum shallow bytes by class, the JVM must traverse a large number of objects on the heap. The cost depends on:

- How much heap is in use.
- Number of objects and object structure.
- Garbage collector and process state.
- Parallel inspection capabilities.
- Live-object vs. all-object option.

A heap with many small objects can take substantial traversal time even if total bytes are modest. Conversely, a heap with fewer large objects has a different cost profile.

### 6.2. Full GC and Pauses

By default, a live-object histogram requests a Full GC prior to inspection. A Full GC can:

- Pause application threads.
- Consume CPU to mark, sweep, and reclaim objects.
- Spike request latency.
- Impact throughput during collection.

The `-all` option skips requesting a Full GC solely to filter live objects because it includes unreachable objects too. Even so, it does not eliminate heap traversal costs or all required safepoints.

### 6.3. Small Output Does Not Mean Cheap Execution

A histogram is a small text table, yet to produce that table the JVM may have had to inspect millions of objects. Output file size does not reflect collection cost.

## 7. Cost of Collecting a Heap Dump

Heap dumps generally cost more than histograms because the JVM must traverse the object graph and write object, class, array, and reference details to disk.

### 7.1. Application Pause Time

A live-object heap dump defaults to requesting a Full GC before dumping. The JVM then creates a consistent snapshot via its heap inspection mechanism; this process can pause application threads or degrade processing capacity for a period.

Duration depends on heap occupancy, object count, disk write speed, compression, and runtime environment. No single pause figure applies universally to all applications.

For latency-sensitive services, a heap dump on a large heap can cause significant disruption. Weigh the timing, current load, downtime budget, and traffic-shifting options before collecting.

### 7.2. CPU and I/O

Dumping requires CPU to traverse the heap, format data, and optionally compress output. It also generates heavy I/O:

- Writing large amounts of data to the filesystem.
- Potentially competing for bandwidth with logs, databases, file uploads, or other tasks.
- Compression increases CPU usage and can prolong dump duration.
- Downstream analysis tools also require substantial CPU and RAM.

If dumping to a nearly full or I/O-saturated volume, the operation can slow down or break other services.

### 7.3. File Size and Free Space

Heap dump size depends on object count, data types, layout, and dump options. You cannot deduce the exact file size as equal to `-Xmx` or heap used. Still, budget ample space and inspect the target volume before starting.

Before dumping, verify:

- The target directory exists and the JVM has write permission.
- The volume has sufficient space for the dump file and related logs.
- Container ephemeral-storage quotas are adequate.
- A cleanup policy exists for old files after analysis.
- Output is not written to a public directory or unintentionally synced folder.

If the filesystem runs out of space mid-dump, the dump may fail while the application has already paid part of the collection cost.

### 7.4. Compression Is a Trade-off

Compression reduces I/O and storage footprint at the cost of higher CPU usage and dump time. If CPU is already saturated, high compression can worsen the incident. If disk or network transfer is the bottleneck, compression can help.

Choose compression based on the current bottleneck, not just desired file size.

## 8. Security and Access Control for Heap Dumps

Heap dumps can contain sensitive data residing in memory:

- Access tokens, session IDs, cookies, or API keys.
- Personal information and request payloads.
- Payment details, addresses, or account information.
- SQL statements, message payloads, or cached data.
- Temporary secrets currently processed by the application.

Therefore:

1. Only personnel authorized for the investigation should read the dump.
2. Store dumps in directories with restricted access permissions.
3. Encrypt in transit and at rest according to organizational policy.
4. Do not attach dumps to public tickets or chat channels.
5. Set a retention period and securely delete files once analysis finishes.
6. When sharing is needed, prefer sanitized histograms or an analysis report over the raw dump file.

Do not treat a heap dump as a harmless log file. It can contain the in-memory contents of the process at capture time.

## 9. JFR in Memory Diagnostics

Java Flight Recorder captures runtime events over time, including allocations, garbage collection, threads, locks, and other JVM activity. JFR helps explain **what happened before and during heap growth**, whereas histograms and heap dumps show the heap's state at capture time.

Questions JFR can help answer:

- Which threads or code paths allocate the most objects?
- When did the allocation rate spike?
- Is GC running frequently or taking long pauses?
- Are there large allocations or increasing pressure tied to workload?
- Which activities coincided with rising latency?

JFR is not a heap dump. A typical recording does not contain the full object graph needed to query retained sizes and paths to GC roots like a heap dump does.

### 9.1. Combining JFR and Histograms

Example workflow:

1. Use JFR to pinpoint when allocation rates increased or GC pressure began.
2. Capture a histogram under representative load to identify classes occupying shallow bytes.
3. Compare histograms at comparable times to see which classes grow and fail to drop after GC.
4. If you need to know which objects retain data, take a controlled heap dump.
5. Use the dominator tree and paths to GC roots to identify retention sources.

JFR helps locate **allocation sources**; histograms help narrow down **existing class populations**; heap dumps help uncover **object retention relationships**.

### 9.2. JFR Is Generally Better Suited for Continuous Observation

JFR can record over extended durations with appropriate settings and generally has lower overhead than full heap dump operations. However, actual overhead depends on events, settings, sampling, workload, and recording duration.

Do not enable every event at high detail for long durations without weighing the cost. Use `default` configurations or `profile` recordings during targeted investigations, and test recording size and overhead in a representative environment.

## 10. Production Collection Workflow

A cautious workflow can be staged by impact level:

### Level 1 — Observe First

- Check heap usage, GC logs/metrics, and existing JFR recordings if available.
- Identify PID, JVM version, incident timing, and workload.
- Determine current CPU, latency, memory, and disk headroom.
- Do not start with a heap dump before knowing what question you need to answer.

### Level 2 — Capture a Histogram

```bash
jcmd 12345 GC.class_histogram
```

Record uptime, PID, timestamp, whether `-all` or default was used, and load state. If you need to avoid a Full GC prior to counting, consider `-all` while understanding that results include unreachable objects.

### Level 3 — Capture a Heap Dump When Reference Paths Are Needed

```bash
jcmd 12345 GC.heap_dump /secure-diagnostics/app-heap-2026-11-15.hprof
```

Run only after verifying free space, permissions, acceptable pause impact, and secure storage. For high-traffic systems, consider draining traffic or shifting load first if architecture allows.

### Level 4 — Analyze and Conclude

- Open the dump in an organization-approved analysis tool.
- Identify dominators and retained sizes.
- Trace GC roots.
- Correlate with JFR, metrics, logs, and object lifecycles in code.
- Document necessary evidence; avoid distributing the raw dump broadly.

### Level 5 — Retain and Clean Up

- Save analysis findings and required histograms.
- Restrict read permissions on HPROF files.
- Delete dumps according to defined retention deadlines.
- Record commands, options, and collection timestamps for reproducibility.

## 11. Automatically Generating a Heap Dump on OutOfMemoryError

The JVM supports the option:

```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/secure-diagnostics -jar app.jar
```

When an `OutOfMemoryError` occurs, the JVM attempts to write a heap dump as configured. This is valuable because the failure may leave the application too unstable for an operator to run commands manually.

However, note:

- A dump does not prevent or fix `OutOfMemoryError`.
- Writing the dump requires disk space and time.
- If the filesystem is full or unwritable, dump creation may fail.
- The file still contains sensitive data and must be protected.
- A dump taken at OOME reflects a heap under extreme pressure; analysis may still require logs and JFR.

Configure `HeapDumpPath` to point to a volume with adequate space and permissions. Do not assume the current working directory is always safe or has enough disk space.

## 12. Factors That Change Collection Cost

| Factor | Histogram | Heap Dump |
| --- | --- | --- |
| Heap occupancy | Increases data to inspect | Increases objects/references to dump |
| Object count | Increases traversal and counting cost | Increases traversal and serialization cost |
| Full GC | Default live histogram requests Full GC; `-all` includes unreachable | Default live dump requests Full GC; `-all` includes unreachable |
| CPU | Heap traversal, optionally parallel inspection | Heap traversal, dump serialization, optional compression |
| Disk I/O | Text output is usually small | File can be very large |
| Pause/latency | Can cause noticeable pauses | Can cause significant and prolonged pauses |
| Security | Usually only class names and counts | Can contain sensitive object contents |

You cannot derive a fixed collection duration from `-Xmx` alone. Measure against production-like workloads and heaps, and keep disk space and time headroom available.

## 13. Useful Diagnostic Commands

| Goal | Command |
| --- | --- |
| List visible JVMs | `jcmd -l` |
| View histogram help | `jcmd <pid> help GC.class_histogram` |
| Capture live-object histogram | `jcmd <pid> GC.class_histogram` |
| Capture histogram including unreachable | `jcmd <pid> GC.class_histogram -all` |
| View heap dump help | `jcmd <pid> help GC.heap_dump` |
| Create live-object heap dump | `jcmd <pid> GC.heap_dump /path/app.hprof` |
| Create dump including unreachable | `jcmd <pid> GC.heap_dump -all /path/app-all.hprof` |
| Create compressed dump | `jcmd <pid> GC.heap_dump -gz=1 /path/app.hprof.gz` |

Examples use placeholder PIDs. Replace `<pid>` with the actual process ID and use valid paths for the target OS. Run `help` on the target JVM to confirm supported syntax and options.

## 14. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| Histograms show which object retains memory. | Histograms only group instances and shallow bytes by class; heap dumps are needed for reference paths and dominators. |
| `#bytes` in a histogram is retained size. | It is the total shallow size per class. |
| Heap dumps always contain only live objects. | By default they dump live objects and request a Full GC; `-all` can include unreachable objects. |
| `-all` makes inspection free. | It avoids a preceding Full GC to filter live objects, but the heap must still be inspected and dumped. |
| Dump file size equals `-Xmx`. | Size depends on the object graph, data, and options; it cannot be inferred accurately from max heap. |
| Histograms are small so the command is cheap. | Output is small, yet the JVM may have to traverse the whole heap and run a Full GC. |
| JFR replaces heap dumps. | JFR records time-series events; heap dumps save the object graph at a point in time. |
| High instance counts equal a memory leak. | It could be valid load, caching, or batching; compare over time and trace object retention. |
| Having a heap dump on OOME solves OOME. | The dump only supplies diagnostic data; it does not fix the cause of memory exhaustion. |
| HPROF files can be shared like normal log files. | HPROF files can contain secrets and user data; enforce access control and retention limits. |

## 15. Practice Exercises

### Exercise 1 — Reading a Histogram

Run a small application that allocates many `String`, `byte[]`, and DTO objects. Capture `GC.class_histogram`, explain the difference between `#instances` and `#bytes`, and point out why the output does not show retained size.

### Exercise 2 — Comparing Live and All Objects

Create many temporary objects and drop their references. Capture both a default histogram and an `-all` histogram. Note which option requests a Full GC prior to inspection and why the counts can differ.

### Exercise 3 — Analyzing a Heap Dump

Create a cache holding many DTOs. Take a heap dump, open it in an HPROF analysis tool, locate the cache in the dominator tree, and inspect paths to GC roots. Explain which objects retain the data.

### Exercise 4 — Measuring Collection Cost

In a test environment, measure execution time for histograms and heap dumps with small and large heaps. Monitor pauses, CPU, I/O, and file size. Do not extrapolate test-machine timings directly to production when workloads differ.

### Exercise 5 — Combining JFR and Histograms

Record JFR while the application allocates many objects. Identify the window where allocation spikes, then take a histogram and compare top classes. Explain why JFR shows activity over time while a histogram is a snapshot.

### Exercise 6 — Preparing a Production Runbook

Write an operational checklist before taking a heap dump: PID, current load, pause budget, volume capacity, write permissions, secure storage location, authorized viewers, and deletion deadline.

## 16. Official Java 17 Documentation

- [Java SE 17 jcmd tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): syntax for `GC.class_histogram`, `GC.heap_dump`, and impact descriptions.
- [Java SE 17 jmap tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jmap.html): documentation for the heap map tool; for diagnostic commands on a running JVM, see `jcmd`.
- [Java SE 17 Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html): recording configurations and event collection levels.
- [Eclipse Memory Analyzer (MAT)](https://eclipse.dev/mat/): tool for analyzing HPROF heap dumps, histograms, dominator trees, and GC roots.

A heap histogram is a fast way to see **which classes occupy shallow heap**; a heap dump helps find **which objects retain memory and why they remain reachable**; JFR tells you **when allocations and JVM activity occurred**. Collecting histograms or dumps can pause the application and consume CPU; heap dumps also require significant I/O, storage space, and protection of sensitive data. Start with lower-cost data, capture dumps only when reference graph analysis is needed, and always account for operational cost upfront.
