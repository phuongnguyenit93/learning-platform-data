# 12.4. HeapDumpOnOutOfMemoryError, HeapDumpPath, and Limitations of Automatic Dump Capture

When a Java application runs out of memory, the most valuable evidence can disappear along with the process. A **heap dump** records the state of objects on the Java heap at capture time, helping identify which objects consume memory and which reference paths keep them alive. HotSpot/OpenJDK provides two options commonly used together: `-XX:+HeapDumpOnOutOfMemoryError` to request a dump when the JVM detects certain out-of-memory conditions, and `-XX:HeapDumpPath=...` to specify where to save it.

However, **enabling the flags does not guarantee a dump file after every OOM incident**. The error condition, how the JVM terminates, write permissions, disk space, and container limits all determine whether capture succeeds. This lesson applies primarily to HotSpot/OpenJDK 17+ JVMs; on other JVMs, verify support for the corresponding options.

## 1. What Is a Heap Dump and How Useful Is It?

A heap dump in HPROF format is a snapshot representing the objects, classes, arrays, and reference relationships recorded by the JVM from the heap. Tools such as Eclipse Memory Analyzer (MAT), VisualVM, or compatible profilers can read this file to:

- Inspect the **class histogram**: instance counts and `shallow size` memory for each type.
- Inspect the **dominator tree** and `retained size`: estimate how much memory could be freed if objects dominating a reference subgraph stopped retaining it.
- Trace **path to GC roots**: see why an object remains reachable, for example held by a `static Map`, queue, thread, cache, listener, or class loader.
- Distinguish intentional retention of many objects from a memory leak hypothesis using reference relationships and business context.

A heap dump is **not a complete allocation history**. It does not directly tell you when each object was created, which thread allocated it, or when GC ran without supplementary profiler/JFR/log data. Nor does a dump directly reflect full memory outside the Java heap such as thread stacks, native allocations, direct buffers, code cache, and Metaspace. An application can run out of memory in those areas even when `heap used` is nowhere near `-Xmx`.

An object's presence in a dump **does not automatically mean a memory leak**. Valid caches, in-flight data, and application state must also stay reachable. A Java memory leak is typically the condition where objects are **no longer needed by business logic yet remain referenced**, preventing GC from reclaiming them. Proving that requires examining reference paths alongside load conditions, not merely looking at a class with high counts.

## 2. The Two JVM Options and How They Work Together

| Option | Meaning | Key notes |
| --- | --- | --- |
| `-XX:+HeapDumpOnOutOfMemoryError` | Requests HotSpot to create a heap dump when the VM handles a supported out-of-memory error. | Not guaranteed for every `OutOfMemoryError` or when the OS kills the process. |
| `-XX:HeapDumpPath=<path>` | Specifies the target **filename** or **directory** for the dump. | Only sets the path; does not enable OOM dumping by itself. |
| `-Xmx<size>` | Sets the maximum Java heap limit. | Not a limit on total JVM RSS/native memory; configure with container limits and off-heap regions in mind. |

Example on Linux, assuming the directory already exists and is writable:

```bash
mkdir -p /var/log/myapp/heap-dumps
java -Xms256m -Xmx1024m \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/log/myapp/heap-dumps \
  -jar app.jar
```

If you provide a **directory** path, HotSpot typically names the file similarly to `java_pid12345.hprof` using the PID. If you provide a **specific filename**, such as `-XX:HeapDumpPath=/var/log/myapp/heap-dumps/incident.hprof`, the dump targets that file. When `HeapDumpPath` is omitted, HotSpot usually writes `java_pid<pid>.hprof` in the JVM's current working directory; that directory may differ from where the JAR resides, especially in services or containers.

Do not assume the JVM will create missing parent directories for you. Create them beforehand, and verify write permissions for the **user running the JVM** as well as free space. Using a fixed filename across multiple instances or restarts risks collisions; HotSpot should not be expected to safely overwrite an existing dump file. Per-instance directories or unique filenames are usually easier to operate.

`-XX:...` flags must appear on the command line **before** the class name or `-jar` so the JVM parses them as VM options. If configured via `JAVA_TOOL_OPTIONS` or a framework launcher, check the effective command line because startup scripts can append or override arguments.

## 3. When Does the JVM Automatically Create a Dump?

Typical sequence when the **Java heap is genuinely exhausted**:

1. The application attempts to allocate an object or array.
2. The JVM tries to satisfy the request, potentially triggering GC or other recovery steps depending on the collector.
3. When allocation cannot succeed under JVM constraints, HotSpot raises the appropriate `OutOfMemoryError`.
4. If the dump flag is enabled **and that error path supports it**, the JVM attempts to write an HPROF snapshot to the configured location.
5. Afterward, the application remains in a resource-exhausted state. The exception may propagate, be caught by application code, or terminate the process depending on configuration. The dump file exists only if the write completes.

Therefore, **high heap usage alone does not produce a dump**. If a cache grows to 90% of `-Xmx` without hitting a triggering error, the JVM does not capture one automatically. Conversely, an allocation failure can happen even when the latest dashboard metric for `used` is below `-Xmx`, due to sampling intervals, allocation size, or collector conditions.

HotSpot generally attempts only one automatic heap dump per JVM lifetime upon encountering a qualifying OOM event; do not design automatic capture as a series of snapshots on repeated errors. To compare before/after states, add periodic monitoring, JFR, or controlled manual captures.

### Not all OOMs behave the same

| Condition / typical message | Should you expect an automatic dump? | Why |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | **Usually yes**, if HotSpot is still able to run and write the file. | Java heap allocation failure is the classic target of this option. |
| `OutOfMemoryError: GC overhead limit exceeded` | **Possibly**, depending on VM/collector and error path. | The JVM spent too much time in GC recovering too little; check actual logs and dump output. |
| `OutOfMemoryError: Metaspace` | **Possibly** on supported VM paths, though a heap dump does not directly measure every native Metaspace byte. | Class loaders/class metadata are involved, so supplement with Metaspace and class-loading stats. |
| `OutOfMemoryError: Direct buffer memory` | **Do not assume yes**. | May originate from direct buffer/Java library allocation mechanisms rather than standard Java heap exhaustion. |
| `OutOfMemoryError: unable to create native thread` | **Do not assume yes**. | Usually tied to thread/PID limits or native/stack memory. |
| `new OutOfMemoryError(...)` thrown manually by app code | **Do not assume yes**. | Constructing/throwing the exception in code does not mean HotSpot detected memory exhaustion on the dump-trigger path. |
| Container `OOMKilled`, kernel OOM killer, `SIGKILL` | **No** via this flag mechanism. | The OS terminates the process externally; the JVM gets no chance to execute the OOM dump hook. |
| Native crash / `SIGSEGV` / `kill -9` | **No** via this flag mechanism. | This is not a VM-handled Java heap OOM. |

Depending on JVM version, the dump flag can behave differently for uncommon `OutOfMemoryError` variants, such as requesting an array exceeding VM limits. Never rely solely on the **exception name** to assume an HPROF will exist; confirm via HotSpot's dump log lines and a completed file.

## 4. Standalone Runnable Java 17+ Example

The following exercise **intentionally triggers a Java heap OOM** in a test environment to observe the mechanism. Do not run it in production or on a machine holding critical data.

Save as `HeapDumpDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public final class HeapDumpDemo {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) {
        while (true) {
            RETAINED.add(new byte[1024 * 1024]);
        }
    }
}
```

Each loop iteration allocates roughly a 1 MiB array and adds it to the static list, keeping all stored arrays reachable. With a small heap limit, the program eventually cannot allocate further and typically throws `OutOfMemoryError: Java heap space`.

In a Bash terminal with JDK 17+:

```bash
javac HeapDumpDemo.java
mkdir -p dumps

java -Xms32m -Xmx64m \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=./dumps \
  HeapDumpDemo

ls -lh dumps
```

The `java` command in this example is expected to **exit with an error**, since we deliberately retain arrays until heap exhaustion. On HotSpot, the terminal typically prints output similar to:

```text
java.lang.OutOfMemoryError: Java heap space
Dumping heap to ./dumps/java_pid<process-id>.hprof ...
Heap dump file created [... bytes in ... secs]
```

This is a **message pattern**, not exact stdout/stderr across every JDK and machine. PID, byte count, duration, message order, and stack traces vary; the JVM may also fail to write the dump on I/O errors. The expected file usually ends with `.hprof` inside `./dumps`, e.g., `java_pid12345.hprof`. You can use MAT to inspect `byte[]`, `ArrayList`, and the retention path from the static field `RETAINED`.

If you specify an explicit filename such as `-XX:HeapDumpPath=./dumps/test-oom.hprof`, ensure no file with that name remains from a previous run. With relative paths, `./dumps` resolves relative to the **Java process's working directory**, not necessarily where `HeapDumpDemo.class` is stored.

### Why is this a retention example rather than representative of every leak?

In `HeapDumpDemo`, arrays remain reachable because they are held by `static final List`. GC cannot reclaim them even though they were created in earlier iterations. This is a simple illustration of **retaining references causing heap growth**; when investigating a real application, you must prove the data is no longer needed by business logic. A cache holding data for upcoming requests can have a similar heap shape while still being a valid design if bounds and eviction policies are configured properly.

## 5. Limitations of Automatic Dump Capture

### 5.1. Container and kernel OOM differs from JVM OOM

A container memory limit applies to total memory accounted by the kernel for the container's cgroup, encompassing many components beyond `heap used`. A JVM can have `-Xmx` smaller than the container memory limit and still exceed the cap due to native allocations, thread stacks, direct buffers, or other regions. When the kernel OOM killer terminates the process, you may observe `OOMKilled` or exit code `137` with **no** Java exception and **no** heap dump.

Hypothetical example:

- Container memory limit: **512 MiB**.
- Java heap max: **384 MiB**.
- Metaspace, thread stacks, JIT/code cache, direct buffers, and native allocations grow together.
- Total memory exceeds the container limit and the kernel kills the JVM.

In this situation, `HeapDumpOnOutOfMemoryError` never gets a chance to run. Do not infer "no `.hprof` ⇒ no memory problem." If an application repeatedly gets `OOMKilled`, inspect container/kernel events, RSS/cgroup memory, and off-heap regions; size the overall heap budget **based on measured figures**.

### 5.2. Disk, paths, and write permissions

Dumps can be large; size is not fixed to `-Xmx` and depends on object counts, data structures, and dump format. A multi-GiB HPROF file can fill a volume, impact other services, or fail to finish writing.

Common failure causes:
- Target directory was not created, path has a typo, or a file exists where a directory was expected.
- User running the JVM lacks write permission, filesystem is read-only, or SELinux/AppArmor/policies block writes.
- Volume runs out of space, quota, or inodes; path points to a small temporary filesystem.
- Multiple instances share the same filename, causing new writes to collide with an older dump.
- No mechanism copies/persists the file before the container or pod is replaced; the file sits on ephemeral filesystem layers and vanishes on restart/redeploy.

**Verify permissions and free space as the exact user/container running the JVM**, not just as an admin user on the host. In Kubernetes, if you need to keep dumps after pod recreation, configure appropriate persistent storage, safe copy-out mechanisms, and cleanup policies. Do not rely on a local path inside a pod as durable storage if the pod can be replaced.

### 5.3. Process state is too degraded to finish writing

Even when HotSpot detects a supported OOM, dumping is still a heavy I/O operation occurring under severe resource stress. The JVM can be killed mid-write by the OS, lose volume access, crash, or be forcibly terminated by health checks/restarts. As a result, a file may be truncated, abnormally small, or unreadable. Verify the **completed creation** status in logs and test opening it in an analyzer rather than merely checking that a filename exists.

Dumping can pause the application significantly, spike I/O, and consume disk space. Duration depends on heap size and state, disk speed, and JVM; there is no fixed pause number. On latency-sensitive services, factor this impact into incident response plans.

### 5.4. "Having a dump" does not mean "having the full root cause"

A heap dump taken **after the JVM already ran GC while trying to satisfy an allocation** may no longer contain the short-lived objects that caused allocation pressure beforehand. If failure stemmed from extreme allocation rates with low live retention, a post-OOM dump struggles to show the allocation chain behind that pressure. If the error came from direct buffers or native memory, HPROF shows only part of the picture.

Correlate with additional evidence: error timestamps, GC logs, heap used/committed/max, RSS/container memory, thread counts, request/batch metrics, allocation profiling, and JFR when suitable. Correlation across signals matters more than a single snapshot.

### 5.5. The flag cannot schedule dumps or guarantee one per error

`HeapDumpOnOutOfMemoryError` is a **reactive measure at OOM**, not a periodic sampler, early-warning monitor, or tool to capture every `OutOfMemoryError` exception. Do not expect multiple files from a process experiencing repeated OOMs, especially when `HeapDumpPath` specifies a single filename. If you need to compare two points before and after data grows, plan controlled captures while the JVM is still healthy.

## 6. Comparing Auto Dumps, Manual Dumps, and JFR

| Tool | When to use | Limitations to keep in mind |
| --- | --- | --- |
| Auto dump: `-XX:+HeapDumpOnOutOfMemoryError` | Want a snapshot when the JVM hits a supported OOM condition. | Triggers only on qualifying paths while the JVM can still write; may yield only a late snapshot. |
| Manual dump: `jcmd <pid> GC.heap_dump <file>` | Investigate retention growth before OOM while the process is alive and attachable. | Can cause major pauses; HotSpot's default heap dump command may request a Full GC before dumping. |
| GC logging: `-Xlog:gc*` | Observe GC cadence, before/after sizes, pauses, heap capacity, and reclamation over time. | Does not directly identify which objects hold references. |
| JFR / allocation profiling | Find timing, call sites, object types, and allocation pressure; correlate with GC events. | Depends on event config and overhead; does not replace reading the object graph from a dump. |
| Native Memory Tracking / OS metrics | Investigate thread stacks, native memory, RSS, or container OOM. | Does not replace a heap dump for Java reference-path analysis. |

Example manual capture while the application is still running:

```bash
jcmd <pid> GC.heap_dump /var/log/myapp/heap-dumps/manual-2026-10-29.hprof
```

`<pid>` is only a placeholder for the actual PID; do not copy angle brackets into the terminal. Ensure sufficient space and permissions, as the command can pause the process and usually writes a large file. On some HotSpot versions, `GC.heap_dump` supports `-all` to include uncollected objects without forcing a prior GC; this changes snapshot semantics, so inspect the JVM's own help (`jcmd <pid> help GC.heap_dump`) before choosing.

When you suspect the app creates lots of short-lived data, JFR typically reveals allocation churn better than looking only at a final snapshot. When you suspect long-lived object retention, dump + dominator tree + path to GC roots is more direct.

## 7. Proper Configuration in Services and Containers

### 7.1. Aligning paths with the working directory

In direct Java services, prefer absolute paths:

```bash
java -Xms256m -Xmx2g \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/data/diagnostics/heap \
  -Xlog:gc*:file=/data/diagnostics/logs/gc.log:time,uptime,level,tags \
  -jar app.jar
```

Before launch, both `/data/diagnostics/heap` and `/data/diagnostics/logs` must exist and be writable. Configure log rotation for GC logs, retention/quotas for dumps, and access policies because dumps may contain secrets in strings, tokens, payloads, or user data.

In containers, if using `JAVA_TOOL_OPTIONS`, the corresponding JVM flags can be passed via an environment variable:

```bash
docker run --rm \
  --memory=1g \
  -v "$(pwd)/dumps:/dumps" \
  -e JAVA_TOOL_OPTIONS="-Xmx512m -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/dumps" \
  myapp:latest
```

This command merely illustrates a Java image whose launcher honors `JAVA_TOOL_OPTIONS`; `./dumps` on the host must exist with appropriate write permissions. `--memory=1g` and `-Xmx512m` are example numbers showing headroom reserved for non-heap memory, **not a universal safe ratio**. Size according to measured RSS/native usage, thread counts, direct buffers, and runtime characteristics.

### 7.2. Verifying flags actually took effect

While the process is alive:

```bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
```

`VM.command_line` shows passed JVM arguments, while `VM.flags` shows flags in their current state. Output varies by version and launcher; if a flag does not appear in the short list, use full-listing options/help on the JVM to verify. On services managed by systemd, Docker, or Kubernetes, distinguish **intended config** from the **actual running command**.

You can validate write capability ahead of an incident using a controlled staging OOM test like `HeapDumpDemo`, with the same image, user, mounts, and planned resource limits. This verifies the HPROF creation path far better than trusting a single config line.

## 8. Post-Incident: Finding and Validating the Dump

Follow a structured order to avoid jumping to conclusions:

1. **Classify how the process ended.** Do logs show a VM-reported `java.lang.OutOfMemoryError`, or only `OOMKilled`/`137`/`SIGKILL`? If the OS killed it, Java flags cannot solve a missing dump.
2. **Check startup JVM flags.** Read the command line, environment variables, or deploy config active during the incident. Changing config afterward will not produce a dump for the prior incident.
3. **Search logs for dump messages.** Lines like `Dumping heap to ...`, `Heap dump file created`, or file-creation errors show how far the process got.
4. **Locate the actual path.** For relative paths, check from the JVM's working directory; for directory paths, look for `java_pid*.hprof`; check the right container/mount/host.
5. **Inspect the file.** Check file size, modification time, and whether MAT/VisualVM can parse the HPROF format. A tiny file or parse error often indicates an incomplete dump.
6. **Analyze the object graph.** Use the histogram to orient, dominator tree to find clusters holding high retained memory, and path to GC roots to prove why they remain reachable. Correlate with requests/batches/caches to confirm business abnormality.
7. **Handle data securely.** Restrict who can read dumps, encrypt at rest/in transit, never commit to Git, and purge per retention policy; heaps can contain passwords, tokens, and personal data.

An OOM without a dump should be treated as **missing evidence**, not automatically a flag misconfiguration. The write opportunity may have been lost to a kernel kill or I/O failure.

## 9. Analyzing Three Illustrative Scenarios

### Scenario A — Java heap OOM with an HPROF file

Monitoring shows post-GC heap used rising steadily for hours, ending with `OutOfMemoryError: Java heap space` and `Heap dump file created` in logs. Load stayed relatively flat. Read the HPROF to find object sets with high retained size, such as an accumulating queue backlog or cache keys without eviction. Then verify why those objects stay reachable and whether they are still needed. If a cache grew legitimately due to more customers, apply appropriate eviction/quotas rather than labeling every increase a "leak."

### Scenario B — Pod OOMKilled, no HPROF

The JVM is set to `-Xmx512m` with a pod memory limit of `640 MiB`; thread counts/direct buffers climb and the pod is killed. There is no `Java heap space` stack trace and no heap dump log line. This calls for investigating **process/container memory**: RSS/cgroup, thread count, direct memory, Metaspace, memory requests/limits, and native allocations. Increasing `-Xmx` could worsen pressure on the container.

### Scenario C — Java OOM, incomplete dump

Logs show `Dumping heap to /dumps/...`, followed by an I/O error or an unreadable file; the volume was nearly full or the pod was terminated early. The flag was enabled, but collection failed. The right fix is to provision/mount a writable directory with adequate quota/retention and test in staging. Do not conclude the incident was unrelated to the heap merely because the HPROF file is absent.

## 10. Common Mistakes and How to Correct the Reasoning

- **"Setting `HeapDumpPath` is enough."** False: you also need `-XX:+HeapDumpOnOutOfMemoryError` (or another capture method). `HeapDumpPath` only sets the destination.
- **"Every `OutOfMemoryError` produces a file."** False: you must account for OOM type, JVM/VM path, and write conditions.
- **"Container `OOMKilled` is a Java `OutOfMemoryError`."** False: the OS can kill the process before the JVM throws an exception.
- **"Setting `HeapDumpPath=/dumps` makes the JVM create the folder and keep files across redeploys."** False: you must pre-create, mount/persist, and verify permissions.
- **"The dump file size must equal `-Xmx`."** False: HPROF size depends on live/captured objects and format overhead.
- **"Having a dump tells you which line of code leaks."** False: a dump gives an object graph; you must trace retention paths, map back to business logic, and possibly add allocation profiling.
- **"The biggest object in the dump is the culprit."** False: a large object can be completely valid; inspect retained size, dominators, and lifecycle.
- **"With `HeapDumpOnOutOfMemoryError`, we don't need pre-OOM alerts."** False: auto dump only gets a chance to run **after an error occurs** and may fail to write.
- **"Take as many dumps as possible."** False: pause, disk, security, and analysis costs can be high; capture deliberately with a clear goal.

## 11. Deployment and Verification Checklist

Before deploying:
- Confirm HotSpot/OpenJDK JVM and how `-XX` flags are actually passed.
- Choose a dump storage location with adequate space, quotas, isolation from critical service disks, and a retention/cleanup policy.
- Pre-create the directory, verify write permission as the application user, and pick names/paths that avoid collisions across instances and restarts.
- Review `-Xmx` within the total memory budget, accounting for Metaspace, direct buffers, native memory, and thread stacks.
- Ensure HPROF files are protected as sensitive data with a safe transfer workflow to an analysis machine.
- On staging, trigger a controlled Java heap OOM and verify opening a real HPROF file.

When an incident occurs:
- Distinguish Java heap OOM, native/direct OOM, and container/kernel kill.
- Cross-check GC logs, cgroup/RSS, exceptions, and dump creation lines.
- Verify the dump completed, resides on the expected volume, and was not lost on restart.
- Use MAT/VisualVM to find retained objects and paths to GC roots, then test hypotheses against real workloads.

**Remember:** `-XX:+HeapDumpOnOutOfMemoryError` and `-XX:HeapDumpPath` capture **a conditional memory snapshot** when the JVM hits a supported OOM type. They are valuable for investigating retention/leaks in the Java heap, but are not guaranteed to run when the OS kills the process, off-heap memory runs out, I/O fails, or the filesystem is ephemeral. Reliable diagnosis combines dumps with GC logs, JFR/metrics, infrastructure checks, and reference-path analysis.
