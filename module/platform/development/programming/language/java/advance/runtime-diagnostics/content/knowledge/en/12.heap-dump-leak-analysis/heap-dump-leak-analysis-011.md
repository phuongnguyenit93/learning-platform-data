# 12.11 Classifying OutOfMemoryError by Message and Actually Exhausted Resource Region

## Objectives and Diagnostic Principles

Although they share the symptom of "running out of memory," a Java application can fail across several distinct resources: the Java heap, class metadata area, direct buffers, native memory, OS thread/process limits, address space, or container memory limits. Only by identifying the exact **error message**, the **exhausted resource**, and **evidence at the time of failure** can you choose the right remediation.

After this lesson, you will be able to:

1. Classify common `java.lang.OutOfMemoryError` messages on HotSpot/OpenJDK.
2. Distinguish a JVM-thrown OOME, a JVM fatal native allocation failure, and an OS/container process kill.
3. Map each message to its corresponding resource region, and select the right metrics, dumps, logs, and inspection commands.
4. Separate **resource exhaustion symptoms** from **root causes** such as memory leaks, legitimate retention, allocation bursts, class loader growth, or thread limits.
5. Avoid the wrong reflex of "bump `-Xmx` for every OOME," and assemble an evidence record to test hypotheses.

**Scope:** Java 17+ on HotSpot/OpenJDK; many examples apply to JDK 21. Exact messages vary across JVM vendors, JDK versions, collectors, OSes, and erroring APIs. The strings below are diagnostic signals, **not a fixed protocol sufficient to determine the final root cause**.

## 1. Understanding the True Nature of `OutOfMemoryError`

`java.lang.OutOfMemoryError` extends `VirtualMachineError` and is an `Error`: the JVM or a library can throw it when unable to satisfy a memory-related resource allocation. The name "OutOfMemory" **does not mean** "the Java heap is full," and OOME **does not mean** "memory leak."

Three layers to distinguish:

| Layer | Situation | Typical signs | Evidence direction |
| --- | --- | --- | --- |
| **Java-level OOME** | JVM/library throws `java.lang.OutOfMemoryError` | Stack trace or log with class name and message | Message, call stack, GC/JFR/heap/native/thread metrics |
| **JVM fatal native allocation** | JVM fails to allocate native memory and aborts with a fatal error | Message "There is insufficient memory for the Java Runtime Environment to continue", `hs_err_pid...` file, abnormal exit | JVM error log, OS memory, native allocations, limits |
| **OS/container kill** | Kernel/cgroup or orchestrator terminates the process due to memory pressure or limits | `SIGKILL`, `OOMKilled` event, cgroup `memory.events`/`oom_kill`; possibly no Java stack trace | Kernel/cgroup/Kubernetes events, `memory.current`, RSS/working set |

Exit code `137` on Linux/containers usually indicates `SIGKILL` (`128 + 9`), which **does not prove** `OOMKilled` by itself: confirm the reason in orchestrator events, cgroup events, or kernel logs. Similarly, a dead process producing no heap dump does not prove the JVM had no memory issue: an OS kill can strike before Java ever throws an OOME.

**Where allocation fails ≠ root cause.** For instance, `Java heap space` indicates a heap allocation request failed; the root cause could be a collection retaining references too long, an unbounded cache, legitimate load exceeding heap size, or a sudden allocation burst. The stack trace at the throw site points to **the last allocation that failed**, not necessarily the code allocating the objects retaining memory.

## 2. Map: Message → Resource Region → Evidence to Verify

| Common message / event | Associated resource | Follow-up questions before concluding |
| --- | --- | --- |
| `OutOfMemoryError:` **Java heap space** | Java heap (object/array allocation failed) | Heap used/max, pre-error GC, post-GC live set, retained objects, allocation rate, `-Xmx` |
| `OutOfMemoryError:` **GC overhead limit exceeded** | Heap where GC spends excessive effort recovering too little under JVM/collector policy | Total GC time, reclamation ratio, allocation rate, collector, whether limit policy is active |
| `OutOfMemoryError:` **Requested array size exceeds VM limit** | VM-allowed array/object size limit, potentially checked before heap allocation | Requested array size, size calculation, input data, integer arithmetic |
| `OutOfMemoryError:` **Metaspace** | Class metadata in native memory / Metaspace cap | Class count, class loaders, class unloading, Metaspace used/committed/max, `-XX:MaxMetaspaceSize` |
| `OutOfMemoryError:` **Compressed class space** | Region holding `Klass` metadata when compressed class pointers are enabled | Compressed class space usage/limit, class loaders/classes, CCS configuration |
| `OutOfMemoryError:` **Direct buffer memory** or **Cannot reserve ... bytes of direct buffer memory** | Direct `ByteBuffer` limit/reservation, backed by native memory | `BufferPoolMXBean` direct, `-XX:MaxDirectMemorySize`, buffer lifecycle, allocation hotspots |
| `OutOfMemoryError:` **Map failed** or similar mapping message | Memory-mapped files / `mmap` capacity, address space, OS limits, mapping resources | `FileChannel.map`, mapping sizes, address space, mappings, OS/cgroup constraints |
| `OutOfMemoryError:` **unable to create native thread** | OS thread creation: native stack, PID/thread limit, or OS/native memory | Thread count, `pids.current/max`, `ulimit`, RSS/native, thread pool policy |
| **Out of swap space?** or specific native allocation notice | Native/OS virtual memory or swap (JVM/OS dependent) | JVM fatal logs, commit limit, swap, memory maps, limits; verify OOME vs. VM fatal error |
| **Native memory allocation (malloc/mmap) failed** in `hs_err` | Native memory the JVM failed to allocate | `hs_err`, OS/cgroup memory, NMT if enabled, thread count, JVM/native library usage |
| **OOMKilled**, cgroup `oom_kill`, Kubernetes reason `OOMKilled` | Container/OS-level memory limit, not necessarily heap | Container memory limit, peak working set/RSS, cgroup `memory.events`, native/off-heap |
| **CodeCache is full**, compiler disabled... | Code cache may be full | Usually a JIT compilation warning/issue, **not automatically an `OutOfMemoryError`**; read the exact message |

Read the verbatim **exception class + message + stack trace + timestamp**. Never collapse everything under a single "heap OOM" dashboard label. Some errors have varying wording across JDKs/vendors, so mark unmatched cases as **unclassified** and return to primary evidence instead of guessing.

### Quick branch-based triage

1. Is **`java.lang.OutOfMemoryError`** in the logs? If yes, extract the verbatim message and throw site; check whether a process kill or fatal error followed.
2. Does it say **Java heap space / GC overhead**? Prioritize heap and GC evidence, then separate retention, allocation bursts, and undersized heap.
3. Does it say **Metaspace / Compressed class space**? Inspect class metadata, class loaders, unloading, and the corresponding limits.
4. Does it say **direct buffer / native thread / map**? Collect off-heap resource metrics and OS limits rather than starting by raising `-Xmx`.
5. No Java exception, yet **`OOMKilled` / `hs_err`** appeared? Investigate OS/container events or fatal native allocations via their respective logs; a heap dump may not exist.
6. If you only see an ambiguous snippet without context, first verify process, JVM, version, timestamp, and full message before assigning a category.

## 3. Java Heap Group: Same Region, Different Mechanisms

### 3.1. `java.lang.OutOfMemoryError: Java heap space`

**Meaning:** the JVM could not satisfy an object or array allocation on the heap even after permissible reclamation steps at that point. This describes an **allocation failure**, not a statement that every byte of heap holds live objects.

Common hypotheses:

- **Retention/leak:** objects remain reachable via static fields, unbounded caches, listeners, queues, collections, `ThreadLocal`, class loaders, or session lifecycles. Post-GC occupancy and retained counts trend upward under comparable load.
- **Legitimately large live set:** the application genuinely needs to hold data in RAM (e.g., loading an entire dataset in batch), and max heap is too small.
- **Allocation burst:** allocating many large objects/arrays in a short window; heap hits its limit when traffic/concurrency spikes.
- **Very large object/array:** a single allocation needs a huge region, hitting object-size limits, fragmentation, or collector policies—not necessarily millions of small objects.
- **Unexpected configuration:** effective `-Xmx` is lower than planned; container-aware sizing, wrapper scripts, or deployment overrides gave the JVM a different cap.

**Priority evidence:** effective `-Xmx`, pre/post-GC heap occupancy over time, GC logs, heap dump if available and safe, dominator tree, retained size, GC roots, allocation profile, and workload changes. Heap dumps reveal **who retains objects**; allocation profiles reveal **who creates new objects**. They answer different questions—do not substitute one for the other.

**Do not conclude:** "Seeing `Java heap space` means raising `-Xmx` fixes the leak." A larger heap may only delay the crash, or push the container into `OOMKilled` by shrinking native headroom.

### 3.2. `java.lang.OutOfMemoryError: GC overhead limit exceeded`

**Meaning:** the JVM detected spending too much time in GC while reclaiming too little memory according to the GC overhead limit heuristic/policy active for that collector/config. It signals **GC can no longer keep the process making useful progress**, typically due to heap pressure. Do not confuse it with a single long pause.

What to inspect:

- How often GC runs and total GC time across the failure window; pre/post reclamation per cycle.
- Is post-GC heap still very high because objects stay reachable, or because traffic continuously allocates?
- Whether the collector and GC overhead limit option actually apply; never assume one fixed percentage threshold across all JVMs.
- GC CPU, throughput, p99 latency, Full GCs, and allocation pressure on the same timeline.

**Cause-driven action:** check retention, legitimate live footprint, batch sizes, and concurrency before experimenting with heap/GC flags. Disabling the GC overhead limit just to "silence the exception" can leave the app thrashing in GC with zero useful throughput; never treat that as a default fix.

### 3.3. `java.lang.OutOfMemoryError: Requested array size exceeds VM limit`

**Meaning:** a request to allocate an array exceeds the maximum size supported by the JVM. The array limit is not simply `Integer.MAX_VALUE` elements for every array type and JVM; overhead, object headers, and VM rules apply.

Example causes: reading massive data into a single `byte[]`, miscomputing size from a file/stream, unchecked integer arithmetic, or trying to materialize an entire dataset in one array.

**Evidence:** requested length, array type, calculation producing that length, input data, API, and allocating code. Prefer streaming, chunking, input-size validation, and avoiding forcing entire payloads into one array. **Increasing `-Xmx` cannot bypass the VM's array size limit.**

Do not confuse with `NegativeArraySizeException` (negative length) or `Java heap space` (heap allocation failure for a valid array size).

## 4. Metadata Group: Metaspace and Compressed Class Space

### 4.1. `OutOfMemoryError: Metaspace`

On modern HotSpot, class metadata lives primarily in **Metaspace**, managed in native memory (not the Java object heap). Java 8+ no longer uses the old HotSpot PermGen model. Thus, when hitting a Metaspace OOME, increasing `-Xmx` **does not directly** expand Metaspace.

Common possibilities:

- Loading/generating too many classes or class loaders: dynamic proxies, bytecode generation, frameworks/plugins, hot reloads, instrumentation.
- **Class loader leak:** old class loaders remain reachable so their classes and metadata cannot unload, often seen as rising class loader/class counts across redeploys.
- `-XX:MaxMetaspaceSize` set too low for legitimate workload.
- Native/container memory pressure blocking native allocation even without a tight Metaspace cap.

Measure class loader statistics, loaded/unloaded classes, Metaspace used/committed, class metadata over time, NMT (if enabled), and container memory/RSS. High class counts alone **do not prove a leak**: you must show class loaders past their lifecycle remain pinned. Class unloading depends on GC/class-loader reachability and collection timing; class count not dropping right after a young GC is normal.

### 4.2. `OutOfMemoryError: Compressed class space`

When HotSpot uses compressed class pointers, **Compressed Class Space (CCS)** stores the subset of metadata requiring compressed addresses and has its own limit and management. "Compressed class space" pinpoints a different area than "Metaspace," even though both belong to class metadata.

Verify that compressed class pointers are enabled, check `-XX:CompressedClassSpaceSize` if configured, inspect CCS used/committed/reserved metrics, and track class/class-loader growth. Adjust the specific limit only after understanding which classes/loaders grow and confirming container memory headroom.

**Common mistake:** raising `-Xmx`, swapping GCs, or increasing `MaxMetaspaceSize` blindly without checking CCS. The right flag to test depends on the exact region hitting its limit and empirical data.

### 4.3. Class loader leak clues inside a heap dump

Metaspace lives outside the Java heap, yet **reference paths pinning a class loader** often appear in a heap dump: static references, `Thread.contextClassLoader`, cache registries, live threads, unremoved listeners/drivers, or plugin managers holding handles. Inspect both class loader retention paths and Metaspace growth trends; do not search for "Metaspace objects" in the Java heap like regular instances.

## 5. Off-Heap / Direct Buffer and Memory Mapping Group

### 5.1. Direct buffer memory

Messages may appear as:

~~~text
java.lang.OutOfMemoryError: Direct buffer memory
~~~

or on some JDKs:

~~~text
java.lang.OutOfMemoryError: Cannot reserve 1048576 bytes of direct buffer memory (allocated: ..., limit: ...)
~~~

This covers **direct `ByteBuffer`** allocation/management: buffer payloads residing off-heap. A direct buffer usually has a Java wrapper on the heap, while the underlying data memory is managed natively.

Separate three quantities:

- **Java heap:** holds the wrapper/objects referencing the buffer.
- **Direct buffer reservation/limit:** limit governed by `-XX:MaxDirectMemorySize` and JVM tracking for direct buffer allocations; messages may show "allocated/limit."
- **Native/RSS:** total off-heap process memory, broader than direct buffers—including threads, class metadata, code cache, native libraries, and allocations outside the direct-buffer counter.

**Evidence:** `java.nio.BufferPoolMXBean` for the direct pool (`Count`, `MemoryUsed`, `TotalCapacity`; exact names/behavior vary by implementation), NMT if enabled, allocation profiles, connection counts and buffer sizes, cleanup lifecycle, and RSS/container limits. When `MemoryUsed`, `TotalCapacity`, and buffer counts climb with load, distinguish valid pooling/caching from retention/leaks.

Hitting the direct buffer limit **does not mean** the entire OS is out of RAM. Conversely, direct buffers sitting below their cap do not prove native memory is sufficient for everything else. Raising `MaxDirectMemorySize` must fit inside the native/container budget, or it can turn the error into `OOMKilled`.

### 5.2. `MappedByteBuffer` and map failures

`FileChannel.map` and memory-mapped I/O use OS memory mappings and **do not share the exact same lifecycle or limits** as ordinary direct `ByteBuffer`s. An OOME mentioning "Map failed"/`mmap` is not sufficient to blame `MaxDirectMemorySize`.

Check mapping type, file sizes, mapping count, address space, OS `vm.max_map_count` (where applicable), limits, file-backed mappings, and how the app manages lifecycles. Map failures can stem from address space or OS resource limits; inspect the underlying OS error as well. Never recommend raising `-Xmx` for map failures; a larger heap can consume even more address space/memory.

### 5.3. Other native regions

Beyond direct/mapped buffers, native allocations include JNI/FFM libraries, thread stacks, JIT code cache, GC metadata, arenas, runtime internals, and memory-mapped libraries. NMT categorizes memory **tracked by the JVM**, with no guarantee of covering external native libraries; NMT reserved/committed figures **do not equal RSS** either.

If RSS/working set grows while `heap used` stays flat, inspect the native breakdown, direct buffer pools, thread count, Metaspace, memory mappings, cgroup limits, and native profilers when truly needed.

## 6. Native Thread Group: Unable to Create New Threads

A common HotSpot message:

~~~text
java.lang.OutOfMemoryError: unable to create native thread: possibly out of memory or process/resource limits reached
~~~

The JVM must create an OS thread backing each platform thread. Thread creation can fail due to:

- Exhausting OS or cgroup `pids.max` process/thread limits.
- Insufficient memory or address space for the native thread stack and related structures.
- Spawning too many threads from unbounded pools, thread-per-request patterns, leaked threads, or multiple libraries each creating pools.
- Per-user/process limits like `ulimit` and runtime/container policies.

**Evidence to collect:** live thread counts (JVM and OS), growth trends, thread names/states, a thread dump when safe, `pids.current/pids.max`, `ulimit`, actual stack size, and OS/RSS/native memory. Read "unable to create native thread" as a prompt to investigate **thread/resource limits**, not assuming a full heap.

Cause-based fixes include bounded thread pools, concurrency/queue caps, closing executors at end of lifecycle, resolving blocking I/O, and adjusting PID limits within system capacity. Adjust `-Xss` only after understanding impacts on call depth/`StackOverflowError`, resources, and thread counts; shrinking `-Xss` does not fix unbounded thread creation.

**Note:** Java virtual threads (JDK 21) are managed differently from platform threads; virtual thread counts do not equal OS thread counts. Native-thread OOME still relates to platform/carrier threads or other OS threads.

## 7. Fatal Native Allocations and Container `OOMKilled`

### 7.1. JVM fatal error when native memory allocation fails

Example startup/runtime message:

~~~text
There is insufficient memory for the Java Runtime Environment to continue.
Native memory allocation (malloc) failed to allocate ... bytes ...
~~~

You may also see `mmap`/commit failures or failure to reserve the heap at startup. These lines typically appear in a **VM fatal error report** (such as `hs_err_pid*.log`), not necessarily as a `java.lang.OutOfMemoryError` thrown and caught by application code.

Read the complete `hs_err` file: allocation type, bytes requested, native stack, process/thread info, VM flags, OS memory/swap, and cgroup limits. Correlate with process telemetry before death. **Do not** try to solve this with only a dead process's heap dump or by changing `-Xmx` without understanding native memory demand.

### 7.2. Container `OOMKilled` and kernel signals

In Kubernetes, container status may show reason **`OOMKilled`** with exit code `137` and rising restart counts. The JVM can be terminated instantly before writing any Java stack trace, heap dump, or running shutdown hooks. Also rule out `SIGKILL` from other actors when seeing only exit code `137`.

Check termination events/reasons from the container runtime and orchestrator; on Linux cgroup v2, read the target process/container's cgroup:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/pids.current
cat /sys/fs/cgroup/pids.max
~~~

These paths illustrate one common cgroup v2 mount layout. In other containers, cgroup v1, or custom mounts, locate the actual cgroup first; do not assume these files always reflect the app under investigation. `memory.events` contains counters such as `oom` and `oom_kill`; correlate by timestamp and cgroup rather than reading cumulative counters and assuming the latest event belonged to your app.

A **container memory budget** includes heap + Metaspace + thread stacks + direct buffers + code cache + GC/native allocations + other components. Never equate "limit = `-Xmx`" or "RSS = `heap used`." `MaxRAMPercentage` only influences heap sizing rules in applicable setups; it does not grant all memory exclusively to the heap.

### 7.3. Do not confuse with `StackOverflowError`

`java.lang.StackOverflowError` typically occurs when a thread's stack cannot fit another frame due to deep or infinite recursion; it is **a different `Error`**. Never classify it as a Java heap OOME. Native-thread OOME can involve memory needed for stacks, yet it is a **thread creation failure**, distinct from overflowing a stack during execution.

## 8. Gathering Evidence: Right Process, Right Time, Right Tool

### 8.1. Capturing an error profile while the process is alive

The examples below target HotSpot/OpenJDK 17+ in environments with `jcmd`/`jstat` (JDK tools) and valid attach permissions; many minimal containers omit these tools. Substitute the specific PID:

~~~bash
java -version
jcmd -l
PID=12345  # Replace with actual PID
jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" GC.heap_info
jstat -gcutil "$PID" 1000 20
~~~

Explanation:

- `VM.command_line`/`VM.flags` confirm the **running** JVM and options rather than relying on stale Helm charts or manifests.
- `GC.heap_info` gives a heap/Metaspace snapshot depending on implementation, not a substitute for the pre-OOME timeline.
- `jstat -gcutil` takes 20 samples 1 second apart to reveal GC trends; a snapshot after restart **does not represent** the dead process prior to crash.
- `VM.command_line` can expose sensitive arguments: redact secrets before sharing logs.

If suspecting class loader/thread issues, verify command support on the JVM first:

~~~bash
jcmd "$PID" help
jcmd "$PID" Thread.print -l
jcmd "$PID" VM.classloader_stats
~~~

`Thread.print` can produce huge logs or overhead on apps with thousands of threads; apply within operational limits. `VM.classloader_stats` exists on certain HotSpot versions/configs; if unavailable, use class-loading metrics/JFR or suitable alternatives.

On Linux, check process-level thread counts and RSS via:

~~~bash
ps -o pid,nlwp,rss,vsz,cmd -p "$PID"
~~~

RSS from `ps` is typically in KiB on Linux, and VSZ is virtual memory size; neither equals heap size. Columns and units depend on OS.

### 8.2. Conditional native memory observation (NMT)

HotSpot Native Memory Tracking must be enabled at startup to use NMT commands; for example:

~~~text
-XX:NativeMemoryTracking=summary
~~~

Then:

~~~bash
jcmd "$PID" VM.native_memory summary
jcmd "$PID" VM.native_memory baseline
# After a representative load window:
jcmd "$PID" VM.native_memory summary.diff
~~~

NMT carries tracking overhead and its own observation scope; use in production only after evaluating overhead. You cannot enable NMT retroactively after a process dies. `summary`/`diff` show growth/shrinkage in JVM-managed memory categories, **not** replacing process RSS, cgroup memory, or native profilers when external libraries allocate natively.

### 8.3. GC logs and JFR

When startup logging can be configured with appropriate scope:

~~~bash
java '-Xlog:gc*,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M' -jar app.jar
~~~

This illustrative command requires a real `app.jar`, file write permissions, and proper space/rotation. Correlate GC logs with application p99/throughput/errors, CPU, and memory at **matching timestamps**. Where permitted, a JFR recording covering GC/class-loading/allocation events can aid investigation:

~~~bash
jcmd "$PID" JFR.start name=oome_probe settings=profile duration=5m filename=oome-probe.jfr
jcmd "$PID" JFR.check
~~~

The 5-minute duration is illustrative; event coverage depends on configuration, and the `profile` setting adds overhead. Do not claim such a recording will prove a leak or capture every native allocation. Protect logs/recordings as they can contain sensitive data.

### 8.4. Heap dumps: value and limits

Common HotSpot flags for capturing a dump on a Java OOME:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/path/with/space/and/permissions
~~~

These must be configured and tested ahead of time, including disk capacity, file permissions, and sensitive-data policies. Heap dumps can be huge and add I/O pressure; they are not guaranteed on `OOMKilled`, native fatal errors, or full disks. Pointing the path outside small container volumes helps avoid filling the container filesystem.

A heap dump describes only the **Java heap at dump time**. It is valuable for retained objects and GC roots, yet lacks full native allocations. For Metaspace leaks, use the heap dump to trace class loader references alongside class metadata/NMT; for direct buffers, inspect wrappers/retention on heap while verifying direct capacity via buffer pool/native metrics.

**Never run ad-hoc heap dumps in production just to "take a look"** without assessing impact: heap inspection commands can trigger long pauses, request GC, fill disks, and expose sensitive data.

### 8.5. When the process is already dead

If attaching is impossible, rely on pre-collected evidence: application stderr/stdout, structured exception logs, GC logs, configured JFR/heap dumps, `hs_err` files, APM metrics, Prometheus time series, Kubernetes events, kernel/cgroup events, restart reasons, and deployment/JDK flags. Separate process/container IDs **before vs. after restart**: never use measurements from the new process as evidence for the old one.

## 9. Region-by-Region Investigation Table and Experimental Decisions

| Verified finding | Next evidence | Hypothesis / intervention to test | What not to do immediately |
| --- | --- | --- | --- |
| Heap OOME + retained set grows at steady load | Heap dump, dominator tree, GC roots, caches/queues | Fix reference retention, bound caches/queues | Simply bump heap to hide a leak |
| Heap OOME + steady live set, burst exceeds headroom | GC log, allocation rate, peak concurrency, memory budget | Streaming/chunking, cap concurrency, test `-Xmx` within budget | Bump `-Xmx` past container memory limit |
| GC overhead OOME + high GC CPU, tiny reclamation | GC time, post-GC heap, allocation/retention | Reduce churn/retention; benchmark heap/GC sizing | Disable GC overhead check to suppress exception |
| Requested array size exceeds VM limit | Requested length / array type / size formula | Chunking/streaming, validate input, fix arithmetic | Raise `-Xmx` as the sole answer |
| Metaspace/CCS OOME + rising class loader count | Class loader stats, unloading, references, class gen | Fix class loader leak / stop generation; tune cap if valid | Resize heap instead of metadata |
| Direct buffer OOME + direct pool near cap | `BufferPoolMXBean`, peak allocation, cleanup, RSS | Reduce/bound buffer retention, tune pools, budget direct cap | Blindly raise `-Xmx` or direct cap |
| Unable to create native thread + `pids` near cap | Thread dump, `pids.max/current`, OS limits | Bounded pools, fix thread leak, raise limits with justification | Blindly shrink `-Xss` without understanding thread growth |
| `OOMKilled` + heap nowhere near `-Xmx` | cgroup, process RSS, NMT/native, direct/thread/meta | Locate off-heap usage; rebalance limits/replicas/budget | Label it a "Java heap leak" |
| Fatal native malloc failure | `hs_err`, native breakdown, system commit/memory | Reduce native pressure, fix leaks, address OS constraints | Inspect only a Java heap dump |

Evaluate branches **concurrently** when an application faces multiple pressures: one service can suffer both a heap leak and native thread growth. Healthy numbers in one area do not mean the whole process is safe.

## 10. Java 17+ Example to Avoid Overconfident Classification

The following is a **runnable standalone program** illustrating how to turn sample messages into an **initial resource hypothesis**, not root-cause proof. Save as `OomeTriage.java`:

~~~java
import java.util.Locale;

public class OomeTriage {
    static String suspectedArea(String message) {
        if (message == null || message.isBlank()) {
            return "Insufficient information";
        }
        String m = message.toLowerCase(Locale.ROOT);
        if (m.contains("requested array size exceeds vm limit")) {
            return "VM array size limit";
        }
        if (m.contains("gc overhead limit exceeded")) {
            return "Heap and GC reclamation progress";
        }
        if (m.contains("java heap space")) {
            return "Java heap";
        }
        if (m.contains("compressed class space")) {
            return "Compressed class space";
        }
        if (m.contains("metaspace")) {
            return "Metaspace";
        }
        if (m.contains("direct buffer memory")) {
            return "Direct buffer / native allocation";
        }
        if (m.contains("native thread")) {
            return "OS thread, PID limit, or native stack";
        }
        if (m.contains("map failed")) {
            return "Memory mapping / OS resources";
        }
        return "Unclassified; requires exact error text and telemetry";
    }

    public static void main(String[] args) {
        String[] messages = {
            "Java heap space",
            "GC overhead limit exceeded",
            "Metaspace",
            "Cannot reserve 1048576 bytes of direct buffer memory",
            "unable to create native thread: possibly out of memory"
        };
        for (String message : messages) {
            System.out.println(message + " => " + suspectedArea(message));
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac OomeTriage.java
java OomeTriage
~~~

Exact output of the program above (with fixed input strings):

~~~text
Java heap space => Java heap
GC overhead limit exceeded => Heap and GC reclamation progress
Metaspace => Metaspace
Cannot reserve 1048576 bytes of direct buffer memory => Direct buffer / native allocation
unable to create native thread: possibly out of memory => OS thread, PID limit, or native stack
~~~

**Intentional limitation of the example:** it merely matches sample strings without triggering real OOMEs or analyzing runtime state. Production classification must capture full exception type, JVM vendor/version, logs, and corresponding telemetry. For example, `"native memory allocation failed"` from `hs_err` can be a fatal JVM event rather than a `java.lang.OutOfMemoryError`.

### Quick collection template for testing hypotheses

Record the following structure in an incident/ticket:

| Field | What to record |
| --- | --- |
| Service/process | Service name, pod/container, PID, deploy version |
| Timestamp | Timestamp with timezone, restart time, failure time |
| Failure type | Java OOME, VM fatal, OS `OOMKilled`, or unclassified |
| Message | Exception class + verbatim message, stack trace/`hs_err`/termination reason |
| JVM and limits | JDK/vendor, GC, `-Xmx`/`-Xms`, `MaxMetaspaceSize`/`MaxDirectMemorySize` if set, cgroup memory/pids limits |
| Suspected exhausted resource | Heap, Metaspace, CCS, direct, mapped, native thread, native memory, container |
| Evidence at failure | Heap used/post-GC, GC events, RSS, thread/classloader/buffer counters, kernel/cgroup events |
| Hypothesis | A falsifiable statement with conditions and excluded alternatives |
| Experiment and guardrails | Minimal change, equivalent load, p99/errors/throughput, RSS/CPU, rollback plan |

## 11. Three Frequently Misdiagnosed Scenarios

### Scenario A — Heap OOME, yet the issue is object retention

After every batch, heap used rises. Across comparable collections under identical traffic, the post-GC "floor" also rises. Eventually `Java heap space` appears. A heap dump reveals a static map retaining millions of records from completed batches via a GC root. **The root cause is map retention**; the fix is redesigning lifecycle/caching/eviction or streaming. Raising `-Xmx` only delays failure without eliminating live references.

### Scenario B — No Java heap OOME, yet container is `OOMKilled`

Pod memory limit is 1 GiB, `-Xmx` is 512 MiB. Heap used stays around 300 MiB, yet direct buffers + Metaspace + thread stacks + other allocations push the working set past the limit under higher traffic. Kubernetes reports `OOMKilled` with no Java exception. **You cannot conclude the heap was too small**; inspect the full memory budget, direct pool/thread trends, and cgroup events. Raising `-Xmx` from 512 to 768 MiB under the same limit would increase risk.

Numbers are hypothetical examples, not configuration recommendations.

### Scenario C — Metaspace OOME after repeated hot reloads

After each plugin reload, class loader count rises without dropping; Metaspace usage climbs steadily until `OutOfMemoryError: Metaspace`. A heap dump reveals threads spawned by old plugins still holding their context class loader. **Class loader retention** is a strong hypothesis backed by reference chains and trends; stop threads and close plugins properly per lifecycle rather than just bumping `MaxMetaspaceSize`. Confirm via class loader counts, unload events, and flat Metaspace across reload cycles.

## 12. Common Investigation Mistakes

- **Reading only the message while ignoring the environment:** `Java heap space` can mean a leak, burst, or low `-Xmx`. The message guides initial triage, not final proof.
- **Equating heap used, committed, max, and RSS:** all four mean different things; container memory limits govern many regions outside the heap.
- **Using a heap dump to "measure total native RAM":** dumps contain Java objects and references, not full Metaspace, direct allocations, thread stacks, or memory-mapped files.
- **Treating the allocation-failure stack trace as the leak site:** objects may be retained by long-lived references elsewhere; inspect retained paths and GC roots.
- **Seeing many Full GCs and immediately switching collectors:** determine whether Full GCs stem from low headroom, retention, fragmentation, metadata, or allocation bursts; a collector swap will not fix a leak.
- **Running heavy commands during an incident without assessing impact:** heap dumps, class histograms, JFR profiling, and attaching incur overhead, pauses, and I/O; not every command is safe at all traffic levels.
- **Comparing metrics before and after a restart:** different PID, heap, and class loaders. Preserve telemetry from the old process.
- **Relying solely on exit `137`:** confirm the `OOMKilled` reason or kernel/cgroup events; `SIGKILL` can come from other actors.
- **Raising `-Xmx` inside a fixed-limit container:** native headroom shrinks, potentially turning a Java OOME into `OOMKilled`.
- **Counting on `-XX:+HeapDumpOnOutOfMemoryError` for every failure:** VM fatal/native kills are not guaranteed to produce dumps; set up GC logs, container telemetry, and crash logs beforehand.
- **Changing multiple knobs at once:** you will not know what helped or caused a regression; test one hypothesis at a time with clear baselines and rollbacks.

## 13. Final Decision-Making Checklist

- [ ] I recorded the verbatim class/message, stack trace or `hs_err`/termination reason, and timestamp.
- [ ] I distinguished Java OOME from VM fatal native errors and `OOMKilled` kills.
- [ ] I verified the exact JVM version/vendor, flags, and actual OS/cgroup limits.
- [ ] I identified the **suspected exhausted resource** with matching metrics to support or refute it.
- [ ] I compared before, during, and after states on the right PID/pod under equivalent load.
- [ ] For heap: checked live set/retained paths, allocation rate, GC behavior, and peak load.
- [ ] For Metaspace/CCS: checked class loaders/classes/unloading and metadata limits.
- [ ] For direct/native/threads: checked buffer pools, NMT when available, RSS, pids/thread limits, and resource lifecycles.
- [ ] For container kills: obtained `OOMKilled`/cgroup/kernel evidence rather than inferring from exit `137` alone.
- [ ] I formulated a root-cause hypothesis and targeted intervention: fix retention, cap load/threads, stream/chunk, fix class loader/direct lifecycle, or perform validated tuning.
- [ ] I have a baseline, acceptance criteria, guardrails, and rollback plan—no blind heap/GC/OS limit edits.

## 14. Conclusion

**`OutOfMemoryError` is the starting point of diagnosis, never the name of a single root cause.** The right workflow is:

**Read the verbatim error → classify failure type (Java / VM fatal / OS kill) → map to resource region → gather same-time evidence → separate leaks from valid load or config limits → test intervention and verify.**

Never let the word "memory" make you raise the Java heap automatically. Only the **resource that actually failed to allocate**, paired with cross-checked evidence, determines whether to examine heap dumps, class loaders, direct buffers, native threads, memory maps, or container limits.

### Official Environment Reference Documentation

- Java 21 API — OutOfMemoryError: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/OutOfMemoryError.html
- Java 21 — jcmd: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Java 21 — Java launcher / VM options / Unified Logging: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Linux kernel cgroup v2: https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html
