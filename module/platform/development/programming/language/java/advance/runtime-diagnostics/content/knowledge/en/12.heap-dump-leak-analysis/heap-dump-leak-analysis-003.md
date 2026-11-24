# 12.3. Capturing HPROF with `GC.heap_dump` or `HotSpotDiagnosticMXBean`

When a Java application exhibits abnormal heap growth, repeated `OutOfMemoryError: Java heap space`, or high post-GC object retention, a **heap dump** provides a point-in-time snapshot of objects on the Java heap. On HotSpot, two common ways to proactively capture an HPROF snapshot are **sending `GC.heap_dump` via `jcmd` from outside the process** and **invoking `HotSpotDiagnosticMXBean.dumpHeap(...)` from Java code or JMX**. Both approaches serve different operational scenarios, yet both produce data for analyzing references and object distribution.

After this lesson, you should be able to identify the correct PID, choose an HPROF capture method, understand the impact of GC and `-all`/`live` flags, generate a valid dump file on the host running the JVM, verify the output, and avoid common mistakes that lose evidence or disrupt the service.

## 1. What Does HPROF Store and Omit?

An **HPROF heap dump** is a binary file containing information about the Java object graph recorded by the JVM: classes, instances, arrays, reference relationships, and associated GC roots as supported by the dump generator. Tools such as Eclipse Memory Analyzer (MAT) can open HPROF files to inspect histograms, dominator trees, retained sizes, and reference paths to GC roots.

- **Shallow size**: the memory of the object/array itself, excluding objects it references.
- **Retained size**: the heap space that could be freed if that object and its dependent objects were no longer held from GC roots, according to the tool's analysis model.
- **GC root**: a root anchor from which the JVM traces reachability, such as references from stacks/threads, classes/static fields, or other JVM mechanisms.

HPROF is **not** a snapshot of total process RAM. It does not replace measurements of thread stacks, Metaspace, code cache, JNI/native allocations, direct buffer backing memory, RSS, or container memory. A `DirectByteBuffer` object may appear in HPROF, but its native backing memory is not recorded intact like a Java array.

A heap dump also **does not by itself prove a memory leak**. A warm cache, large batch, or high traffic can legitimately hold many objects. Concluding a leak requires examining reference owners and trends over time under comparable load conditions.

## 2. Choosing the Right Capture Method

| Criterion | `jcmd <PID> GC.heap_dump` | `HotSpotDiagnosticMXBean.dumpHeap(...)` |
| --- | --- | --- |
| Triggered by | Operator or external tool outside the application | The application itself, an internal task, or an authorized JMX client |
| Requires changing application code? | No | Yes if invoked directly in app code; built-in MXBean can also be called via JMX |
| Typical requirements | JDK with `jcmd`, correct PID, ability to attach to the HotSpot JVM | JVM with `jdk.management`/HotSpot MXBean and invocation permissions |
| Object scope selection | Default; or `-all` to include uncollected objects | `live=true` or `live=false` parameter |
| Output controls | Filename and JDK-version-dependent options (JDK 21 has `-gz`, `-overwrite`) | File path ending in `.hprof`; this API provides no compression option |
| Best suited for | Ad-hoc incidents on a running process | Integrated diagnostic flows, controlled triggers, JMX |

Both methods can cause **substantial application pauses** due to full-heap operations, especially on large heaps. Choose an appropriate time and instance before running in production. Never treat a heap dump as a lightweight metric read.

## 3. Preparing Before Capturing HPROF

1. **Verify the JVM/PID** of the exact service and environment. In containers or Kubernetes, the host PID can differ from the PID visible inside the container namespace. `jcmd -l` may not list JVMs inside another Docker process namespace.
2. **Choose an absolute path on the host or filesystem where the target JVM runs**, such as `/var/tmp/diagnostics/service-12345.hprof`. Include service/PID/timestamp in the filename to avoid colliding with old files. Even when invoked from a remote JMX client, the file is written **on the target JVM's machine**.
3. **Ensure the directory exists and the JVM user has write permission**, and that the filesystem has sufficient free space. HPROF size depends on object count and cannot be derived directly from `-Xmx`; multi-GiB heaps can create huge files. In containers, also check volume/ephemeral storage capacity.
4. **Account for operational impact**: dumping can cause long safepoints/pauses; `jcmd GC.heap_dump` in default mode also requests a Full GC. Record timestamp, PID, Java version, heap limit, and traffic context so the snapshot can be interpreted accurately.
5. **Protect sensitive data**: HPROF files can contain strings, tokens, session data, personal information, and application payloads. Restrict read permissions, store in controlled locations, transfer securely, and delete per policy after analysis.

A dump command only succeeds while **the JVM is still alive and capable of executing the command**. If the OS has already killed the JVM due to OOM, you cannot go back and attach to the vanished PID.

## 4. Method A — `jcmd GC.heap_dump` on a Running JVM

### Step 1: Find and confirm the PID

On a machine with a JDK and appropriate permissions:

~~~bash
jcmd -l
~~~

From the output, identify the PID of the **right Java process**. Cross-check the process command line, service name, and environment, as multiple JVMs may run the same main class. In containers, run the tool inside an environment that sees the PID and can attach to the target JVM.

Suppose the PID to inspect is **12345** (example only; replace with the actual PID):

~~~bash
jcmd 12345 help GC.heap_dump
jcmd 12345 VM.command_line
jcmd 12345 GC.heap_info
~~~

`help GC.heap_dump` shows the syntax and options supported by the **target JVM**; `VM.command_line` and `GC.heap_info` help confirm the run and current heap state. `jcmd` needs to run on the same machine, with a matching effective user/group and working attach mechanism. Command names and options may vary by JDK/JVM.

### Step 2: Take a default dump

Example on Linux with an existing directory and absolute path:

~~~bash
jcmd 12345 GC.heap_dump filename=/var/tmp/diagnostics/service-12345.hprof
~~~

On **HotSpot JDK 21**, this creates an HPROF file; **unless `-all` is specified, the JVM requests a Full GC before writing**. Unreachable objects may be reclaimed prior to the snapshot. This is helpful when you want to observe objects retained after GC, though it also alters heap state at measurement time.

The path above is in the **target** process's filesystem, not the directory where the operator happens to invoke `jcmd`. When running from a host or separate container, verify mounts and namespaces; the file may reside inside the container's filesystem.

### Step 3: When to use `-all`?

~~~bash
jcmd 12345 GC.heap_dump -all filename=/var/tmp/diagnostics/service-12345-all.hprof
~~~

Per JDK 21 `jcmd`, `-all` includes objects that are **unreachable yet uncollected**, and the command **does not request a Full GC** before dumping. This mode is useful if you need evidence of garbage present in the heap at that moment; conversely, data can be larger and noisier when analyzing leaks. `-all` **does not mean** zero pause or that no GC activity can occur for other reasons.

Do not compare object counts between a default snapshot and a `-all` snapshot as if both used the same definition of "live set."

### Step 4: Compress HPROF on write (optional, JDK-dependent)

HotSpot JDK 21 supports `-gz`. Example:

~~~bash
jcmd 12345 GC.heap_dump -gz=1 filename=/var/tmp/diagnostics/service-12345.hprof.gz
~~~

Level `1` favors compression speed; level `9` compresses more tightly at the cost of extra CPU/time. Check whether your analysis tool opens `.hprof.gz` directly or requires decompressing first. Never assume all JDKs/VMs support the same flags; always check `help GC.heap_dump` on the target PID.

JDK 21 also offers `-overwrite`, though by default it does not overwrite existing files. During investigations, **prefer new filenames** so you do not destroy an earlier snapshot.

### Step 5: Verify the artifact

On the machine or volume where the JVM wrote the file:

~~~bash
ls -lh /var/tmp/diagnostics/service-12345.hprof
~~~

Confirm the file exists, has non-zero size, a matching modification timestamp, and opens in an HPROF analysis tool. `Heap dump file created` from `jcmd` is an initial success signal; successfully opening it in MAT or an equivalent tool is stronger verification. If `-gz` was used, check the corresponding compressed filename.

## 5. Method B — Calling `HotSpotDiagnosticMXBean.dumpHeap`

`com.sun.management.HotSpotDiagnosticMXBean` resides in the `jdk.management` module on modern HotSpot JDKs. Method signature:

~~~java
void dumpHeap(String outputFile, boolean live) throws IOException;
~~~

Details:

- `outputFile`: file path on the **machine running the target JVM**; if relative, it resolves against the target JVM's startup working directory. Use an absolute path to avoid confusion.
- `live=true`: includes only reachable ("live") objects per the API definition; may trigger GC work to determine this set.
- `live=false`: does not restrict the dump to reachable objects only, so uncollected objects may be included.
- The path must end with the **`.hprof`** suffix; an existing file, inability to create/write, or running out of space throws `IOException`. There is no compression parameter or `-overwrite` option on this method.
- This interface is **HotSpot-specific**, not a mandatory contract implemented by every JVM. Where unavailable, do not assume it can be invoked on another runtime.

You can obtain the MXBean in-process:

~~~java
HotSpotDiagnosticMXBean diagnostic =
        ManagementFactory.getPlatformMXBean(HotSpotDiagnosticMXBean.class);
diagnostic.dumpHeap("/var/tmp/diagnostics/app-live.hprof", true);
~~~

This is an **illustrative snippet**; the complete runnable example right below includes imports, MXBean null checking, and path handling. Do not attach heap dump generation to normal HTTP requests: a single request could trigger a long pause, fill disk, or produce repeated snapshots if retried unexpectedly. If built into an application, use an authenticated diagnostic trigger with rate limiting and an explicit output path.

In addition to direct code calls, the MXBean is typically registered under the ObjectName `com.sun.management:type=HotSpotDiagnostic` and can be invoked by JMX tools such as JConsole if secure administrative access is configured. **A path entered via remote JMX still resolves on the application host, not on the machine running JConsole.**

## 6. Self-Contained Java 17+ Example to Try Both Methods

Create the file **`HprofDemo.java`**. The program holds references to eight arrays, supporting an `mxbean` mode to write HPROF directly and a `wait` mode so you can attach `jcmd` from another terminal.

~~~java
import com.sun.management.HotSpotDiagnosticMXBean;
import java.lang.management.ManagementFactory;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class HprofDemo {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        for (int i = 0; i < 8; i++) {
            RETAINED.add(new byte[1024 * 1024]);
        }

        if (args.length == 2 && "mxbean".equals(args[0])) {
            HotSpotDiagnosticMXBean diagnostic =
                    ManagementFactory.getPlatformMXBean(
                            HotSpotDiagnosticMXBean.class);
            if (diagnostic == null) {
                throw new IllegalStateException("HotSpot MXBean unavailable");
            }

            Path destination = Path.of(args[1]).toAbsolutePath();
            diagnostic.dumpHeap(destination.toString(), true);
            System.out.println("Created: " + destination.getFileName());
            return;
        }

        if (args.length == 1 && "wait".equals(args[0])) {
            System.out.println("PID: " + ProcessHandle.current().pid());
            Thread.sleep(180_000L);
            System.out.println("Wait finished");
            return;
        }

        System.out.println("Usage: mxbean <new-file.hprof> | wait");
    }
}
~~~

Compile with JDK 17 or later (HotSpot):

~~~bash
javac HprofDemo.java
~~~

**Try MXBean** in a writable directory, making sure the filename does not already exist:

~~~bash
java -Xms32m -Xmx128m HprofDemo mxbean demo-live-001.hprof
~~~

On success, the program's stdout prints:

~~~text
Created: demo-live-001.hprof
~~~

Then verify `demo-live-001.hprof` in the directory where the program ran. If you re-run with the same filename, the API may throw `IOException` because the file already exists; pick a new filename instead of overwriting snapshots.

**Try `jcmd`** using two terminals:

Terminal A:

~~~bash
java -Xms32m -Xmx128m HprofDemo wait
~~~

The program prints `PID: <actual PID>`, then stays alive for about three minutes. In Terminal B, replace **12345** with the observed PID and choose a new writable path:

~~~bash
jcmd 12345 GC.heap_dump filename=/var/tmp/diagnostics/hprof-demo-12345.hprof
~~~

On Windows, you can specify a path such as `C:/dumps/hprof-demo-12345.hprof` after creating the directory and ensuring write permissions. Actual `jcmd` output includes the PID and JVM status messages, without an identical fixed stdout string across all JDKs.

Because `RETAINED` is a static field holding the arrays, they appear in the object graph and can be traced along appropriate GC root paths; how an analyzer displays shallow/retained sizes also depends on the JVM version and dump contents. Exiting `wait` mode after three minutes simply ends the demo program and is not evidence of OOM.

## 7. Understanding `-all` and `live`: Capture Mode Changes What You See

| Invocation | Target objects included | GC behavior |
| --- | --- | --- |
| `jcmd ... GC.heap_dump filename=...` | Objects remaining in the snapshot after the requested GC step | JDK 21 requests a Full GC unless `-all` is passed |
| `jcmd ... GC.heap_dump -all filename=...` | Includes unreachable objects not yet reclaimed | Does not request a Full GC for the dump |
| `dumpHeap(path, true)` | Only live/reachable objects | May request collection to determine the live set |
| `dumpHeap(path, false)` | Not restricted to live objects only | Cannot be treated as a guarantee of zero safepoints |

**Example:** the application just dropped references to a 100 MiB array, but GC has not run yet. A `-all` snapshot can still include that array, whereas a live-only snapshot taken after a Full GC will no longer contain it. Looking solely at a histogram and concluding a "100 MiB leak" from a `-all` image would be wrong. Conversely, when investigating allocation churn or high temporary object volume, seeing unreachable objects can carry its own diagnostic value.

Live-only mode is generally better when hunting for **objects being retained**; use `-all` mode when you have a specific diagnostic question and understand the tradeoffs. A post-Full-GC snapshot may not reflect the exact peak heap right before the event.

## 8. Opening HPROF and Answering the Right Leak Questions

Recommended sequence with Eclipse MAT or an equivalent HPROF reader:

1. Open the right HPROF file, noting timestamp, JVM version, PID, dump flag (`live` vs. `all`), and load at capture time.
2. Check the **Histogram** to see object types and total shallow size. High counts of `byte[]` or `String` are only signals, not proof of who holds them.
3. Inspect the **Dominator Tree** and **Retained Heap** to find objects or structures retaining the most space.
4. Trace **Path to GC Roots** for suspects, paying attention to static fields, collections/caches, listeners, thread-locals, class loaders, or queues.
5. Compare against design intent: is the cache bounded, does the data have a clear lifecycle, have threads/requests finished, or is an old class loader still pinned?
6. Where possible, compare **multiple post-GC snapshots at equivalent traffic** alongside GC metrics over time. "An object is still reachable" is not enough to prove it will never be released.

Important limitation: retained size is a property of the **reference graph at dump time**. It does not add directly onto native memory to yield RSS, nor is it a guarantee that GC would immediately reclaim that exact number of bytes.

## 9. Common Errors and Troubleshooting

| Symptom | Common cause | How to check / resolve |
| --- | --- | --- |
| `Could not attach`, `AttachNotSupportedException`, permission denied | Wrong PID, different user/group, attach disabled on JVM, process exited, different container namespace | Verify JVM PID, user permissions, process state, attach mechanism, and namespace |
| `Unknown diagnostic command` or missing desired option | Target JDK/JVM is a different version or lacks support | Run `jcmd 12345 help GC.heap_dump` against the target JVM itself |
| File does not appear on caller's machine | Dump was written inside the target JVM's / container's filesystem | Check working directory, absolute path, and mounts/volumes inside the process |
| `IOException`: file exists/cannot write | MXBean does not overwrite, filename not new, insufficient permissions, missing directory, or disk full | Pick a new `.hprof` path, create valid directory, check quota/disk/permissions |
| `IllegalArgumentException` from MXBean | Usually path lacks the `.hprof` extension | Rename output to end in `.hprof` (do not use `.hprof.gz` directly with this method) |
| Service slows down or times out during dump | Large heap, long Full GC/heap walk, busy CPU/I/O | Prefer a secondary instance or off-peak window; measure duration; never trigger concurrent dumps |
| HPROF opens fine but suspect is missing | Full GC removed unreachable objects; mistimed snapshot; issue is native/off-heap | Check `live`/`all` flag, capture under target load, correlate with heap/GC trends and NMT/OS metrics if native is suspected |
| `jcmd` fails after JVM dies | PID no longer exists, or process was OOMKilled before attach | Prepare pre-crash capture; where suitable, configure `-XX:+HeapDumpOnOutOfMemoryError` and `-XX:HeapDumpPath=...` at startup |

**Note on automatic OOME dumps:** `-XX:+HeapDumpOnOutOfMemoryError` is a separate fallback mechanism and does not replace the two proactive techniques in this lesson. It can only work if the JVM is still able to write a dump during the failure; a container abruptly killed by the OS may produce no file.

## 10. Short Checklist Before Using in Real Environments

- I have verified the **exact JVM/PID** and access permissions.
- I know whether the dump needs **live objects** or **all objects**, and understand it can trigger a Full GC/pause.
- The path **on the host/container running the JVM** is absolute, the directory exists, the file does not exist yet, and sufficient disk space is available.
- I selected the right method: `jcmd` for external operation; `HotSpotDiagnosticMXBean` for code/JMX control.
- I have a plan to verify the written HPROF opens properly and to protect sensitive data inside the file.
- During analysis, I trace **who holds the objects** and correlate history/load, never concluding a leak from file size or a single histogram.

**Key takeaway:** `GC.heap_dump` and `HotSpotDiagnosticMXBean.dumpHeap` both create a **Java heap** snapshot in HPROF format, differing in how they are triggered and which objects they include. Always record **PID + timestamp + path + live/all mode**, as those four facts determine the evidentiary value when investigating leaks.

## Official References

- Oracle JDK 21, *The jcmd Command* — `GC.heap_dump` syntax, `-all`, `-gz`, `-overwrite`, and Full GC impact: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Java SE 21 API, *HotSpotDiagnosticMXBean* — `dumpHeap(outputFile, live)`, path, file suffix, exceptions: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html
- Oracle JDK 21, *Troubleshoot Memory Leaks* — capturing dumps via `jcmd`, JMX, and OOME options: https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html
