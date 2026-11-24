# 21.3. Prioritizing Low-Impact Evidence Before Evaluating Dumps or Detailed Configuration

When a Java service experiences elevated latency, rising RSS, hung threads, or signs of `OutOfMemoryError`, diagnostic operations **can also make the situation worse**. A large heap dump can pause the JVM, generate heavy I/O, and consume gigabytes of disk right when the machine is starved of memory or storage. Enabling overly verbose logging can spike CPU, string allocations, and file writes. Often, existing metrics, a few well-timed snapshots, or a lightweight JFR recording are already enough to point the investigation in the right direction.

The core principle of this lesson is: **collect the lowest-cost evidence sufficient to test the current hypothesis; escalate collection only after identifying an information gap and accepting the risk**. This means neither "never take a heap dump" nor "every metric is free." It is about managing the trade-off among **diagnostic value, operational impact, capture time, size, and data security**.

Scope: HotSpot/OpenJDK Java 17+ on servers/containers; examples use `jcmd`, `jstat`, Java Flight Recorder (JFR), MXBeans, and collection tiers ranging from existing observability to heap dumps. For other JVMs or versions, check `jcmd <pid> help` and verify actual support before use.

## 1. Why Select Tools by Impact Level?

Three questions must be answered before touching a struggling JVM:

1. **What evidence is missing?** For example: "Which code is driving CPU?", "Are threads waiting on a lock or I/O?", "Is post-GC heap steadily growing?", "Why are objects still reachable?" Each question requires a different kind of data.
2. **Can capturing the evidence distort or destroy the trail?** A command may trigger safepoints, force GC, alter scheduling, increase allocation/I/O, push the process against cgroup limits, or disrupt latency.
3. **Is the output safe, detailed, and durable enough to analyze?** JFR/HPROF files can contain paths, arguments, class names, stack traces, tokens, strings, and user data. Once collected, they require policy-compliant storage, access control, transfer, and deletion.

**Impact is relative**, not an immutable label. A thread dump on a JVM with dozens of threads behaves very differently from one on a JVM with tens of thousands of threads. A short `default` JFR recording differs from continuously capturing full allocation stack traces. Even commands documented as `Impact: Low` should be measured, rate-limited, and monitored on latency-sensitive production services.

## 2. Evidence Priority Ladder: From Lightest to Heaviest

| Level | Evidence / Tool Group | Primary Benefit | Trade-offs and Notes |
| --- | --- | --- | --- |
| **0 — already available** | Dashboards, already-written application logs, OS/cgroup metrics, enabled GC logs, existing traces, deployment timeline. | Requires no new evidence generation from the JVM. | Metrics may be coarsely sampled, aggregated, lack correlation, or exceed retention. |
| **1 — controlled lightweight queries** | `jcmd <pid> VM.version`, `VM.uptime`, `VM.flags`, `VM.command_line`; bounded `jstat -gcutil` sampling; existing JMX counters. | Verifies target process, configuration, and heap/GC/class/thread trends. | Attach, sampling, and stdout output still have overhead and require permissions. |
| **2 — time-bounded lightweight recording** | JFR `settings=default`, dumping an already-running recording, existing logging or narrowly scoped adjustments. | Adds multi-dimensional timestamps/stacks/events to correlate CPU, GC, I/O, and contention. | Overhead, file size, and event coverage depend on settings; do not enable indiscriminately. |
| **3 — medium-impact snapshots / probes** | `jcmd <pid> Thread.print`, `VM.native_memory summary` if NMT is enabled, selected deep statistics commands. | Identifies `BLOCKED`/`WAITING` thread groups, locks, and native-memory subsystems. | Thread count, attach cost, safepoint/VM operations, and output volume can be substantial. |
| **4 — heavy capture requiring explicit approval** | `GC.class_histogram`, `GC.heap_dump`, heap statistics/path-to-GC-roots in certain JFR configs, heavy profilers, or native/core dumps. | Reveals class histograms, object graphs, retained references, and detailed leak evidence. | Can cause major pauses, trigger GC, heavy disk I/O, strict security demands, and worsen symptoms. |

These levels are a **practical selection framework**, not a formal API classification. Per Oracle's Java 17 `jcmd` documentation: `JFR.start` is listed as `Impact: Low`, `Thread.print` as `Medium` depending on thread count, and `GC.class_histogram` and `GC.heap_dump` as `High` depending on heap size. `VM.native_memory` is rated `Medium`. Always inspect the help output and real risk for your specific VM/host.

Even a high-level action **can be the right call** when you must capture state before the process dies and the cost of missing the evidence outweighs collection risk. Even then, explicitly document the decision, timing, expected impact, storage target, abort path, and approver.

## 3. Start With the "Incident Envelope" and Existing Evidence

Before running a command that perturbs the JVM, capture the incident frame:

- **Identity:** service, environment, deployment version, instance/pod/container, host, PID, JVM vendor/version, collector, application uptime.
- **Window:** anomaly onset time, timestamp with timezone, duration, most recent deployment or configuration change.
- **Impact:** request rate, throughput, p95/p99 latency, errors/timeouts/rejections, affected users or jobs.
- **Resources:** host and process CPU, RSS, cgroup memory limit, heap used/committed/max, GC count/pauses, free disk/inodes, socket count, thread count.
- **Existing evidence:** logs with correlation IDs, traces, running JFR, GC log rotation, container events (e.g., `OOMKilled`), autoscaling/restart alerts.
- **Constraints:** does production have a strict latency SLO? Is the JVM about to restart? Is storage volume available? Who is authorized to receive HPROF/JFR?

You do not have to gather everything at once. Pick metrics that directly separate competing hypotheses. For instance, a process killed by cgroup `OOMKilled` might **never throw a `java.lang.OutOfMemoryError` in the Java heap**, so an automatic heap dump may neither exist nor help; check RSS/cgroup/native memory first.

### Preserve Comparability

For every metric, record **the exact instance and units**. Post-GC heap used, committed heap, RSS, container working set, committed native memory, and reserved native memory **are not synonyms**. Never infer a "Java heap leak" solely from a rising RSS graph.

Collect **before–during–after** points when possible: for example, the same instance at 10:00 (normal), 10:10 (anomalous), and 10:20 (recovered). Never compare two instances with different workloads, JDKs, or heap flags and declare one JVM has a memory leak.

## 4. Step 0: Existing Metrics, Logs, and Operational Events

This usually offers the highest information-to-cost ratio. Look for available evidence without asking the JVM to change recording modes:

| Symptom | Metrics to Read First | Differentiation Hint |
| --- | --- | --- |
| Latency spike | ingress latency, app handler duration, queue wait, thread pool active/queue, DB/client duration, error rate | Is work queuing up or is code/I/O running slowly? |
| High CPU | process CPU vs. host CPU, GC CPU/time, method samples if JFR is already running | Is CPU spent in application hot paths, GC, or another process? |
| Heap growth | post-GC used, GC pauses, allocation rate, max/committed | Allocation churn or growing retained live set? |
| RSS growth | RSS/cgroup limit, Java heap committed, thread count, direct buffer pools, metaspace, NMT if enabled | Is heap or native memory the main contributor? |
| Hung threads | active vs. idle threads, queue length, lock/DB pool waits, prior thread dumps if any | Waiting on I/O/locks, backlog, or deadlock? |
| Process death | exit code, `OOMKilled` event, Java exceptions/stderr, fatal error logs, disk capacity | JVM OOM with dump or kernel kill/crash before writing? |
| Post-deploy spike | release timestamp, config diff, traffic mix, warmed-up state, prior GC/JFR baseline | Application regression or load/infra change? |

**Do not look only at averages**. p99 latency can surge dramatically while the mean remains flat; a small percentage of total GC pause time does not rule out a few long pauses. Investigating tail latency requires time series or timestamped events, not just aggregate counts.

**Do not abuse request-content logging** to "get more evidence." Logging payloads, headers, tokens, SQL parameters, or PII introduces both security and I/O risks; enable only essential fields with proper scope and retention.

## 5. Step 1: Verify JVM, Flags, and Lightweight Metrics

On an appropriate host or namespace, with a JDK providing `jcmd` and attach permissions to the target JVM:

```bash
# List JVMs visible from the command execution environment
jcmd -l

# Replace <pid> with the real PID of the target JVM
jcmd <pid> VM.version
jcmd <pid> VM.uptime
jcmd <pid> VM.command_line
jcmd <pid> VM.flags

# Check help for the exact JVM version before running new operations
jcmd <pid> help
```

`jcmd` must target the right PID, host, user, and permissions; inside a container, the internal PID differs from the host PID. `jcmd -l` may not list JVMs in other container namespaces. **Never run `jcmd 0 ...` to broadcast commands to multiple JVMs** when investigating a single service.

Some commands print system properties or command lines containing sensitive data such as endpoints and occasionally credentials; **filter before saving or sharing output**. `VM.flags` shows JVM flags and `VM.command_line` shows launch arguments, though not every runtime or application config change appears here.

### 5.1. Short-Window GC Observation

```bash
# 10 samples, 1,000 ms apart
jstat -gcutil <pid> 1000 10

# If class load/unload info is needed and supported by the tool
jstat -class <pid> 1000 10
```

`jstat -gcutil` reports memory-space utilization percentages and GC counters/elapsed times via HotSpot performance instrumentation; exact columns vary by JDK and collector. This is a **10-second sample window**, not the entire incident, and it does not prove which class or object is leaking. Percentage columns are not MiB; if absolute numbers are needed, check metric types or use JMX/GC logs.

`jstat` must still be run at a sensible frequency; polling hundreds of processes every few milliseconds becomes a monitoring workload of its own that can skew measurements. `1000 10` is an **illustrative low-sample cadence**, not a mandatory schedule.

### 5.2. Bounded Programmatic Reads

- `MemoryMXBean.getHeapMemoryUsage()` and `getNonHeapMemoryUsage()` snapshot managed-memory pools per Java MXBean semantics; **non-heap MXBean does not equal total native RSS**.
- `ClassLoadingMXBean` reports loaded/unloaded classes.
- `ThreadMXBean.getThreadCount()` returns thread count at sample time; **it does not produce a thread dump**.
- `GarbageCollectorMXBean` reports collection counts/times if provided by the collector, though cumulative GC time **is not automatically total stop-the-world pause time** for concurrent collectors.

Lightweight metric reads are useful for spotting **trends**, but cannot answer "which specific objects hold 2 GiB of heap." Escalate to detailed data only when you have a question about object graphs, stacks, or locks that counters cannot answer.

## 6. Java 17+ — Lightweight In-Process State Sampling

The standalone program below invokes only **management MXBeans**, takes two samples roughly one second apart, and requires no Full GC, heap dump, or JVM flag changes. It measures **the JVM running the program itself**, which is useful for understanding the metric pattern; in a real service, export equivalent metrics via secured monitoring/JMX rather than launching a second JVM and mistaking it for the service under investigation.

Save as `LowImpactSnapshot.java`:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;

public final class LowImpactSnapshot {
    record Snapshot(long timestampNs,
                    long heapUsedBytes,
                    long heapCommittedBytes,
                    long nonHeapUsedBytes,
                    int threads,
                    int loadedClasses,
                    long gcCount) {}

    static Snapshot take() {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        ThreadMXBean thread = ManagementFactory.getThreadMXBean();
        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();

        MemoryUsage heap = memory.getHeapMemoryUsage();
        MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();

        long totalGcCount = 0;
        boolean gcCountKnown = true;
        for (GarbageCollectorMXBean bean
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            long count = bean.getCollectionCount();
            if (count < 0) {
                gcCountKnown = false;
            } else {
                totalGcCount += count;
            }
        }

        return new Snapshot(
                System.nanoTime(),
                heap.getUsed(),
                heap.getCommitted(),
                nonHeap.getUsed(),
                thread.getThreadCount(),
                classes.getLoadedClassCount(),
                gcCountKnown ? totalGcCount : -1);
    }

    public static void main(String[] args)
            throws InterruptedException {
        Snapshot before = take();
        Thread.sleep(1000);
        Snapshot after = take();

        double elapsedSeconds =
                (after.timestampNs() - before.timestampNs())
                        / 1_000_000_000.0;
        double heapDeltaMiB =
                (after.heapUsedBytes() - before.heapUsedBytes())
                        / (1024.0 * 1024.0);

        System.out.printf(
                "elapsed=%.3fs heapDelta=%.2fMiB%n",
                elapsedSeconds, heapDeltaMiB);
        System.out.printf(
                "heapCommitted=%dKiB nonHeapUsed=%dKiB%n",
                after.heapCommittedBytes() / 1024,
                after.nonHeapUsedBytes() / 1024);
        System.out.printf(
                "threads=%d->%d loadedClasses=%d->%d%n",
                before.threads(), after.threads(),
                before.loadedClasses(), after.loadedClasses());

        if (before.gcCount() >= 0 && after.gcCount() >= 0) {
            System.out.println(
                    "gcCountDelta=" +
                    (after.gcCount() - before.gcCount()));
        } else {
            System.out.println("gcCountDelta=unavailable");
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac LowImpactSnapshot.java
java LowImpactSnapshot
```

Sample output:

```text
elapsed=1.001s heapDelta=0.10MiB
heapCommitted=16384KiB nonHeapUsed=5900KiB
threads=6->6 loadedClasses=835->844
gcCountDelta=0
```

**Numbers only illustrate the format**; actual values vary by JVM, JIT, loaded classes, and scheduler. `Thread.sleep(1000)` does not guarantee exactly 1.000 second, so the program reports elapsed time measured with `nanoTime()`. Reading multiple MXBeans is not an atomic snapshot, and a 1-second heap delta does not equal allocation rate because GC may have reclaimed objects in between.

This exercise simply illustrates how to ask low-impact questions: "Is heap/non-heap changing?", "Are thread and class counts climbing?", "Did any GC run between two samples?" To inspect **another running JVM**, use tooling, an agent, or monitoring connected to that exact process; never extrapolate from the sample program's own JVM metrics.

## 7. Step 2: Default JFR or Reusing an Existing Recording

Java Flight Recorder is the natural choice when metrics say "something is abnormal" but you do not yet know **when and which stack or activity** correlates with the spike. JFR can provide CPU, GC, thread, I/O, contention, class loading, and application events depending on settings.

### 7.1. Prioritize Pre-Existing Active Recordings

First check whether the JVM already has any recordings:

```bash
jcmd <pid> JFR.check
jcmd <pid> help JFR.dump
```

If an active recording exists with an actual name, such as `service_baseline`, you can take a **snapshot of already-collected data** instead of launching a new recording:

```bash
jcmd <pid> JFR.dump \
  name=service_baseline \
  filename=/var/diag/jfr/service-baseline-incident.jfr \
  maxage=5m
```

The path is **illustrative**; the directory must exist and the target JVM must have write permission. `JFR.dump` **does not stop the recording**; it writes a file from data still retained in the repository. `maxage=5m` bounds the historical slice to dump if available—it cannot recover events that aged out of retention or were never enabled. When running in a container, the file lands on the **target JVM's filesystem/mount**, not automatically on the operator's workstation.

Per Java 17 documentation, `JFR.dump` has `Impact: Low`, yet it still consumes I/O and disk space to write the file and can affect a host that is nearly out of disk. Never treat JFR dumping as completely "free."

### 7.2. If No Recording Exists, Start a Time-Bounded One

Within an authorized incident window, such as **two minutes**:

```bash
jcmd <pid> JFR.start \
  name=triage_2m \
  settings=default \
  duration=120s \
  filename=/var/diag/jfr/triage-2m.jfr
```

`settings=default` is typically suitable for lightweight continuous capture; `profile` records more events with higher overhead and is meant for short windows when evidence is genuinely missing. The file is written when the recording ends as configured; if the JVM is kernel-killed/crashed earlier or the filesystem fails, a complete file may not exist. Never slash event thresholds to near zero just to "capture everything" without evaluating cost.

On a machine with access to the generated file:

```bash
jfr summary /var/diag/jfr/triage-2m.jfr
jfr print --events jdk.GarbageCollection \
  /var/diag/jfr/triage-2m.jfr
```

`jfr summary` reports event types/counts/sizes and time span; it does not automatically deduce root cause. `jfr print` prints details for selected events; on large files, filter carefully to avoid flooding stdout or disk. Event names depend on what is present in the file and on the JVM/settings; an empty count for a target event does not prove zero activity.

### 7.3. When Should You Consider `profile` or Finer Settings?

When `default` has provided evidence pointing to a suspected **CPU hotspot**, **allocation churn**, **long I/O wait**, or **lock contention** but lacks sufficient stacks or samples, consider a short, scoped, approved `profile` recording:

```bash
# Only after agreeing on impact level and stop condition
jcmd <pid> JFR.start \
  name=profile_60s \
  settings=profile \
  duration=60s \
  filename=/var/diag/jfr/profile-60s.jfr
```

Do not leave multiple overlapping `profile` recordings running unbounded. Actual impact varies by application; Oracle describes `default` JFR as low-cost in most cases, but **there is no guarantee of "0% overhead" for every workload**. Heap statistics and path-to-GC-roots are far more expensive features: never enable them merely to gather every possible data type.

**Assess recording quality:** enough events? Does it span the anomaly window? Are thresholds/sampling filtering out short operations? Are the needed stack traces present? If something is missing, raise collection level **deliberately**, rather than turning every event to maximum.

## 8. Step 3: Thread Dumps When the Issue Truly Involves Threads or Locks

Metrics plus lightweight JFR sometimes cannot tell you which specific threads are waiting on a lock, `Future.get()`, a network read, or an executor queue. A few **timestamped thread snapshots** can answer that question.

On HotSpot Java 17:

```bash
# Execute only after impact level is approved
jcmd <pid> Thread.print -l
```

Per Oracle JDK 17, `Thread.print` carries `Impact: Medium` depending on thread count; the `-l` option adds information about certain `java.util.concurrent` locks. Check `jcmd <pid> help Thread.print` on other VMs. **Never treat thread dumps as a completely harmless lightweight call** on services running tens of thousands of threads.

A practical approach is taking **2–3 snapshots spaced meaningfully apart** (e.g., 5–10 seconds, scenario-dependent) if the app can tolerate it, rather than taking one snapshot and declaring a deadlock. Seeing the same threads on the same stacks/locks across multiple points provides stronger evidence than a single snapshot. Never run an infinite loop of `jcmd Thread.print` that adds load and fills disks.

### Reading Thread Dumps Properly

| Observation | What It Might Mean | Do Not Jump to This Conclusion |
| --- | --- | --- |
| Many threads in `WAITING` | Idle workers waiting for tasks, or awaiting a condition/future. | "All threads are dead." |
| Many threads `BLOCKED` on the same monitor | Lock contention in a code region. | "There is a deadlock" unless a lock cycle is seen or detected by the JVM. |
| Workers waiting in `SocketInputStream`/NIO/read | Waiting on I/O or a downstream dependency. | "High CPU caused by the read method." |
| Thread pool queue growing and active threads at max | Likely saturation/backlog. | "Just add more threads," ignoring DB pools or CPU limits. |
| Identical stack across multiple samples | Possible stuck operation or repeated work. | "Definitely a bug" if the thread is legitimately running a long job. |

**Thread dump timing affects behavior**: under heavy load, taking a dump can lengthen pauses or shift timing; compare with latency spikes at that timestamp alongside metrics and traces. Thread dumps can also expose URLs, file paths, and SQL/stacks tied to internal data; store with appropriate permissions.

On newer JDKs with virtual threads, dump tooling can differ from Java 17. Do not blindly copy JDK 21's `Thread.dump_to_file` onto a JDK 17 system if the command does not appear in `jcmd <pid> help`.

## 9. When Native Memory Is Suspected

A service with growing RSS but stable post-GC Java heap requires checking **thread stacks, direct buffers, metaspace, JIT/code cache, GC/native allocations**, or container accounting before concluding a Java heap leak.

If **Native Memory Tracking (NMT) was enabled at startup**:

```bash
jcmd <pid> VM.native_memory summary scale=MB
```

NMT is enabled via `-XX:NativeMemoryTracking=summary` or `detail` at JVM launch; understand its ongoing overhead from startup. If NMT was **not enabled**, runtime commands cannot retroactively provide untracked native allocation history. Do not demand a production restart just to get NMT before analyzing already-available metrics.

When NMT is present and time-based comparison is needed within approved bounds:

```bash
# Mark baseline
jcmd <pid> VM.native_memory baseline

# After the observation interval
jcmd <pid> VM.native_memory summary.diff scale=MB
```

Per JDK 17 `jcmd` docs, `VM.native_memory` has `Impact: Medium`. NMT clarifies HotSpot-managed native pools, yet **does not cover all allocations** from native libraries outside the JVM. Moreover, **reserved ≠ committed ≠ RSS**; never add "reserved" memory as physical RAM in use.

Enabling `-XX:NativeMemoryTracking=detail` for the next deploy carries higher overhead than `summary`. Do so only after deciding which native callsites you want to trace and validating in an appropriate test environment.

## 10. When Is a Histogram More Reasonable Than a Heap Dump?

If earlier data shows **post-GC Java heap used climbing steadily** and you need to know which classes dominate memory, a histogram can serve as an intermediate step before committing to a full HPROF:

```bash
# HIGH impact: do not treat as a "lightweight" check
jcmd <pid> GC.class_histogram
```

`GC.class_histogram` counts objects and shallow bytes per class, but reveals no reference relationships or dominators. It may show numerous `byte[]`, `HashMap$Node`, or cache entries; it **does not prove which objects are leaked** or which GC roots retain them.

Important: Oracle rates `GC.class_histogram` as **High impact**, depending on heap size. It can stall the JVM while inspecting huge object populations and produce large output. Do not classify it as "low impact" simply because the output is text rather than an HPROF file. The `-all` option (where supported) includes unreachable objects, which can mislead readers into thinking every object is live. Always correlate collection policy and timing accurately.

**Deciding whether to capture a histogram:** run it only when you need **per-class object distribution**, the impact fits the situation, lightweight thread/GC/JFR data cannot answer the question, and safe output handling is ready.

## 11. When Is a Heap Dump Truly Needed?

An `.hprof` heap dump captures the object graph and is useful when your goal is finding **retaining reference paths**, dominator trees, retained sizes, classloader retention, or a Java heap leak unexplainable by histograms and metrics.

HotSpot JDK 17 example:

```bash
# HIGH impact; requires valid path/permissions/capacity and approval
jcmd <pid> GC.heap_dump /var/diag/heap/incident-001.hprof
```

Per Oracle JDK 17 docs, `GC.heap_dump` is **High impact** and **triggers a full GC unless `-all` is specified**. A Full GC alters the very object population under study; `-all` writes unreachable objects as well and is not a "zero-impact" toggle. HPROF files can reach gigabytes—do not assume size equals `-Xmx`. Near cgroup memory or disk limits, dumping can worsen the outage or produce a truncated file.

### Go/No-Go Checklist Before a Heap Dump

- [ ] **Clear hypothesis:** are you hunting retained references in the Java heap, rather than native RSS, network timeouts, or a container `OOMKilled` without Java OOM?
- [ ] **Prior evidence:** have you checked post-GC baselines/GC logs, classloader/class counts, or relevant JFR, confirming what only an object graph can answer?
- [ ] **Urgency:** is there a risk of losing the investigation because the process is about to die? Is there a replica or staging environment where reproduction is lower-risk?
- [ ] **Impact:** are the pause and Full GC acceptable? Who approved it? Is there an abort plan or failover if SLO degrades?
- [ ] **Storage:** does the directory exist, is it writable by the JVM user, are quotas/inodes sufficient, is the filename unused, and was free disk checked on **the exact mount**?
- [ ] **Container:** is the file saved on an appropriate volume so it survives pod replacement? Are I/O and ephemeral storage limits checked?
- [ ] **Security:** dumps can contain secrets/PII; restrict read access, encrypt in transit/at rest, enforce retention, and log deletions.
- [ ] **Analysis:** do you have Eclipse MAT/VisualVM, enough RAM on the analysis machine, and a plan to align timestamps with JFR/GC logs?

If most answers are unclear, **do not capture** just because the command is handy. An unopenable heap dump, captured from the wrong instance, lacking correlated logs/metrics, or filling production disk delivers far less value than the damage it causes.

### What About OOM Events?

`-XX:+HeapDumpOnOutOfMemoryError` paired with `-XX:HeapDumpPath=...` can produce a dump when **the JVM handles eligible `OutOfMemoryError` conditions**. These flags are normally set at launch. They **do not guarantee** an HPROF when the kernel/cgroup kills the JVM (`OOMKilled`/`SIGKILL`), write permissions fail, disk fills up, or the process crashes before completion.

Never induce an OOM in production just to test dump mechanics. Validate the workflow in staging with an equivalent image, user, mount, and quota. If production lacks a dump after an incident, check **JVM OOM vs. OS kill**, dump log messages, container events, and mount/retention first—never assume "no dump means no leak."

## 12. Detailed Configuration: Small, Time-Bounded, and Reversible Changes

Some issues lack sufficient evidence under sparse default settings. You may need to:

- Increase detail on **one JFR event group** such as `jdk.SocketRead` or `jdk.JavaMonitorEnter` for a short window, rather than enabling all events.
- Add stack traces or sampling for a specific suspicion, remembering overhead scales with event rate and thresholds.
- Enable rotated **GC unified logging** on the next deployment, or change runtime logging **only when supported by the JVM and approved**, avoiding continuous `trace` logging.
- Enable NMT `summary` at startup for recurring incidents; use `detail` only when native callsites are needed and overhead has been measured.
- Capture heavy heap dumps/diagnostic artifacts only when lighter evidence cannot answer the root-cause question.

Before changing configuration, record **initial state**, start/end times, target instances, operator, disk/CPU budget, auto-stop condition, and restore procedure. Never "crank up all flags just in case"; every change can alter both the symptom and measurement reliability.

Example **read-only check** of existing Unified Logging configuration:

```bash
jcmd <pid> VM.log list
```

`VM.log` can modify logging configuration on supporting versions when passed appropriate options; this example only lists it. To enable extra tags or change outputs, check `jcmd <pid> help VM.log` and test in a compatible environment. Never push an untested dynamic logging change fleet-wide.

### JFR Heap Statistics and GC Roots Are Not First-Line Choices

Enabling **Heap Statistics** in JFR or `path-to-gc-root` can create extra work and pauses. Oracle warns that Heap Statistics can introduce substantial overhead due to GC-coupled heap statistics gathering; GC root options should likewise be enabled only during suspected memory leak investigations. Never set `path-to-gc-root=true` on every recording just to make files "more detailed."

To measure **allocation churn**, JFR samples/metrics may suffice; to inspect the **retained object graph**, consider a heap dump. Those are two different questions, and neither artifact should be expected to fully substitute for the other.

## 13. Incident-Grouped Collection: Three Illustrative Playbooks

### A. p99 Latency Rises While CPU Remains Low

1. Inspect request latency breakdown, thread pool queue/active counts, connection pool pending counts, socket/database metrics, and existing logs.
2. If many workers appear blocked downstream, use `default` JFR or an existing recording to inspect I/O, contention, and timestamps (remembering thresholds may skip short events).
3. If you still cannot tell which threads hold locks or wait, consider **a few conditional thread dumps**, comparing across timestamps.
4. **Do not take a heap dump** solely for high latency when no memory/retention signal exists.

Signals like `ThreadPark` or `SocketRead` are investigative leads, not automatic proof of buggy code. Seeing some threads in `WAITING` is normal if they are idle workers.

### B. RSS Approaches Container Limit While Post-GC Heap Is Flat

1. Check RSS/cgroup memory, container events, `-Xmx` vs. committed heap, thread count, and existing direct buffer/metaspace metrics.
2. If NMT was enabled, read `VM.native_memory summary` and compare against baseline; distinguish reserved vs. committed.
3. If native allocations outside HotSpot NMT are suspected, switch to approved OS/native tooling rather than trying to explain all RSS with an HPROF.
4. Consider a heap dump only if **Java heap retention evidence** emerges or you need to trace objects anchoring native buffers/classloaders.

Reflexively increasing `-Xmx` can get the container killed even sooner by shrinking headroom left for native memory.

### C. Post-GC Heap Climbs Steadily Over Many Hours

1. Collect a time series of post-GC heap used, allocation rate, GC frequency/pauses, workload, and recent deployments.
2. Use existing JFR or `settings=default` to correlate GC, class loading, and allocation samples when enabled.
3. If many objects of specific classes are suspected and orientation is needed, consider a **High-impact** histogram during a safe window.
4. When the question becomes "what keeps these objects from being GC'd," run the heap dump go/no-go checklist and inspect dominator trees and paths to GC roots in MAT.
5. If the leak reproduces reliably in staging, prefer capturing heavy artifacts there to protect production.

Do not mistake every sawtooth heap curve or warm-up climb for a leak. Compare **post-GC baselines across comparable cycles**, not just pre-GC peaks.

## 14. Choose Tools by Question, Not Habit

| Investigation Question | Lightweight Evidence to Try First | Escalate Collection Only When... |
| --- | --- | --- |
| Is the JVM running the right flags and version? | `VM.version`, `VM.flags`, `VM.command_line`. | Rarely requires a heap or thread dump. |
| Is there a concerning GC pause/heap trend? | Dashboards + existing GC logs + `jstat`/default JFR. | Specific object distribution or GC roots are needed. |
| Which methods are CPU hotspots? | JFR execution samples from an appropriate recording. | Sampling is insufficient and a finer profiler is justified. |
| Are tasks slow due to I/O or locks? | Traces, queue waits, DB/socket metrics, JFR I/O/contention events. | Thread stack snapshots are needed to confirm exact blocks. |
| Are metaspace/classloaders growing? | Class loading/Metaspace metrics, `VM.classloader_stats` if appropriate. | Roots retaining specific loaders or metadata must be traced. |
| Is native RSS rising? | OS/cgroup + heap committed + NMT if enabled. | Native profiler or core dump is needed per separate procedure. |
| Java heap leak: which objects hold memory? | Post-GC trend + JFR allocations + histogram if justified. | Only an object graph / retained size can answer it. |
| Did the process vanish abruptly? | Kernel/container events, stderr/fatal logs, exit code. | Failure mode is confirmed before deciding on dumps. |

A dashboard alone is not a conclusion; neither is an HPROF alone. **Evidence sources should corroborate or refute one another**. If metrics say "100% CPU" while JFR shows few CPU samples, check whether the recording covered the exact window, check sampling/thresholds, host vs. JVM CPU, instance count, and timezone before blaming any tool.

## 15. Never Let Diagnostic Tools Take Down the Service

### 15.1. Situations Requiring Extra Caution

- **Memory/cgroup near exhaustion:** a dump or recording can spike I/O, storage, or CPU; the kernel may kill the process mid-capture.
- **Disk nearly full:** JFR, GC logs, or heap dumps can fill volumes shared by the app or critical logs.
- **Extreme latency sensitivity:** snapshots requiring safepoints or Full GC can breach SLOs.
- **Multiple concurrent replicas:** running heavy diagnostics across every replica can turn a local issue into a fleet-wide outage; target a single replica/window when approved.
- **Autoscaling/restarting environments:** files written inside ephemeral containers can disappear; mount and extract safely.
- **Sensitive data:** heap dumps, recordings, and thread dumps can expose tokens, paths, and object payloads.
- **Unknown JVM/vendor:** commands differ in syntax, impact, and support; never copy flags blindly from another version.

In emergencies, **stabilizing the service and preserving existing evidence** may outweigh attempting heavy artifact collection. If restarting or failing over, save available metrics and decision timestamps; never promise to recover uncollected data.

### 15.2. Principle of "Minimal Yet Reproducible Collection"

Every collection should include a minimal manifest:

```text
incident: INC-2026-042
service/instance: inventory-api / pod-7c8f...
JVM: OpenJDK 17.x, PID 1234, G1
window: 2026-10-29T09:15:00Z .. 2026-10-29T09:17:00Z
symptom: p99 latency increased, errors 1.2% (illustrative)
artifact: triage-2m.jfr
command: jcmd 1234 JFR.start name=triage_2m settings=default duration=120s ...
scope/overhead: one JVM, two-minute default recording
time_zone: UTC
owner/approval: authorized operations contact
storage/retention: restricted incident storage; delete per policy
```

All values here are **examples**, not a real incident. A manifest ties each file to the exact version and instance so recordings from different replicas never get mixed up. Compute checksums after transfer if tamper evidence is needed; never commit dumps or configs with secrets to Git or public tickets.

### 15.3. How to Evaluate Observed Impact

While running any diagnostic step above level 0, watch:

- p95/p99 latency and error/timeout/rejection rates vs. the prior window on the same instance.
- User/system CPU, GC pause/time, heap allocation, RSS/cgroup, and disk I/O.
- Size of files being written, free disk/inodes, and network transfer if applicable.
- Exact diagnostic start/stop timestamps: which metrics shifted right when collection began?
- Any signs of disk pressure, container eviction/restart, or corrupted output?

Do not assert "command A caused the spike" merely from temporal proximity; however, if signals degrade simultaneously, enforce **stop conditions** and rollback readiness before continuing. Parameters like `duration`/`maxage`/`maxsize` bound some recordings, yet never replace active monitoring.

## 16. Evidence Integrity: Avoid Over-Inferring From Incomplete Data

A snapshot can be **accurate** yet **unrepresentative**:

- A thread dump shows thread states **only at capture time**; threads might be idle between bursts.
- A short JFR recording misses spikes prior to start; `default` JFR enforces thresholds and sampling.
- A histogram shows object distribution at one instant without reference paths and may reflect a triggered GC.
- An HPROF may be written **after a Full GC**, stripping short-lived objects; it does not recount full allocation history.
- NMT covers HotSpot-tracked areas and cannot be equated with total RAM or container memory.
- 1-minute aggregated metrics hide 200 ms spikes; raising sampling frequency itself carries cost.
- A `.jfr`/`.hprof` file with the right name can still be **truncated** due to full disk, permissions, kill, or crash; verify file size and readability.

Reports should state "evidence observed in window X indicates..." rather than "confirmed root cause" whenever data cannot rule out competing hypotheses.

### Comparing Two Points Does Not Make Multi-Metric Reads Atomic

Reading heap, threads, class counts, and GC counters sequentially via MXBeans captures each metric at slightly different micro-timestamps. Never assume a single scrape represents an atomic, simultaneous JVM snapshot. Across multiple JVMs or hosts, synchronize clocks, record timezones, and account for skew; never subtract `System.nanoTime()` from JVM A against JVM B.

## 17. A Reusable Escalation Decision Flow

```text
New symptom / alert
         │
         ▼
Identify service/PID/instance + risk + time window
         │
         ▼
Read metrics/logs/traces/cgroup and existing recordings
         │
         ▼
Is there a specific, actionable hypothesis?
    ┌────┴────┐
   Yes        No
    │          │
    ▼          ▼
Verify with   Add lightweight metric/snapshot or default JFR
existing          │
evidence          ▼
    │        Any new signal?
    │             │
    └─────────┬───┘
              ▼
Is something missing that only deeper evidence can answer?
              │
      ┌───────┴────────┐
      │                │
     No               Yes
      │                │
      ▼                ▼
Conclude within     Assess impact, data sensitivity, disk,
existing data       permissions, approval, stop condition
      │                │
      │       ┌────────┴────────┐
      │     No-go              Go
      │       │                 │
      │       ▼                 ▼
      │  Defer/escalate   Capture targeted artifact
      │                   once per window
      │                         │
      └─────────────────────────┤
                                ▼
                Verify file + correlate timestamps
                                │
                                ▼
                   Report hypothesis + limitations
```

You do not always need to traverse every level. An issue clearly explained by metrics and traces **stops at lightweight evidence**. If a JVM risks dying before operators can capture an object graph, an early dump may be justified after weighing risks and getting approval. What matters is making a **reasoned decision**, not collecting heavy artifacts out of habit.

## 18. Common Misconceptions

- **"When debugging, start with a heap dump."** False: heap dumps rarely help directly with CPU, I/O, lock, or cgroup kills, and carry High impact.
- **"Thread dumps are just text, so they must be Low impact."** False: Oracle JDK 17 rates `Thread.print` as Medium, scaling with thread count.
- **"Histograms are smaller than HPROFs, so they are cheap."** Not necessarily: `GC.class_histogram` is still rated High impact.
- **"JFR always has 0% overhead."** False: `default` is usually low, but depends on workload and event settings; `profile` and heap statistics can be heavier.
- **"Running `JFR.dump` captures every past event."** False: it captures only events that were enabled and still within retention.
- **"`jstat -gcutil` identifies the exact leaking object."** False: it reports counters and percentages, not an object graph.
- **"RSS equals heap used."** False: RSS includes many native components; native memory must be evaluated separately.
- **"NMT can still inspect past native allocations even if disabled."** False: tracking must be enabled from startup to capture that data.
- **"Heap dumps always capture state without changing the heap."** False: `GC.heap_dump` triggers a Full GC by default on HotSpot JDK 17 unless `-all` is used.
- **"`-all` makes heap dumping cost-free."** False: it changes object scope, not a high-impact operation into a low-impact one.
- **"An HPROF directly pinpoints the buggy line of code."** False: you must trace retained paths/GC roots and correlate business logic; a dump is not an allocation-history profiler.
- **"One snapshot proves a trend."** False: you need time series, matched workloads/windows, and comparability.
- **"You can run the same command across all pods at once."** Dangerous: concurrent diagnostics can trigger a fleet-wide outage; limit targets.
- **"No need to check disk for a one-off dump."** False: large files can fill volumes or breach quotas.
- **"Dumps contain no sensitive data."** False: JFR, heap/thread dumps, and command-line output can contain data requiring protection.
- **"No dump file means the JVM had no problem."** False: writes may fail, get killed, disappear on restart, or go to the wrong path.
- **"More data always yields a better diagnosis."** Not always: noisy data, mismatched sampling, and distortion from overhead can mislead analysis.

## 19. Pre-, Mid-, and Post-Collection Checklist

**Before collecting:**

- [ ] Document the question/hypothesis, instance/PID, time window, and service impact tolerance.
- [ ] Review existing data: metrics, logs, traces, GC/JFR recordings, OS/cgroup events.
- [ ] Pick the **lowest-impact** evidence sufficient to answer the next question.
- [ ] Verify exact JDK, attach permissions, namespace, path, storage, and privacy rules.
- [ ] For Medium/High-impact operations: secure approval, time limit, resource budget, stop condition, and failover plan.
- [ ] Ensure you do not accidentally trigger Full GC or excessive logging.

**During collection:**

- [ ] Record timestamps, timezone, target, and exact commands for correlation.
- [ ] Monitor p99/errors/GC/RSS/disk to catch diagnostic side effects.
- [ ] Never loop heavy commands or leave large captures unbounded; never run fleet-wide.
- [ ] Never send dumps containing secrets/PII to public channels.

**After collection:**

- [ ] Verify artifacts are complete, match the right JVM/instance/window, and open cleanly.
- [ ] Document version, flags, settings/sampling/thresholds, and what the files **do not** cover.
- [ ] Analyze according to hypothesis: timeline/stacks with JFR, thread states with thread dumps, retained graphs with HPROF.
- [ ] Re-check before–during–after metrics to gauge the collection's own impact.
- [ ] Revert temporary logging/profiling, clean up files per retention, and secure evidence.
- [ ] Report **scoped conclusions**, confidence levels, and next steps without over-inferring from missing data.

**Remember:** the best diagnostic step is not the one that collects the most data, but the one with **the highest information value at acceptable impact**. Start from existing telemetry, add counters or short JFR recordings, and reach for thread dumps, histograms, or heap dumps only when you know precisely what evidence you need. Keeping the service stable, tracking exact identity, and safeguarding artifacts are integral parts of Java diagnostics—not afterthoughts.

### References

- [Oracle JDK 17 — jcmd: impact of each diagnostic command, JFR.start/JFR.dump, Thread.print, GC.class_histogram, and GC.heap_dump](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle JDK 17 — jstat: sampling GC/class counters](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html)
- [Oracle JDK 17 — jfr: summary/print for reading recordings](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [Oracle JDK 17 — Troubleshoot Performance Issues Using Flight Recorder: overhead, thresholds, sampling, and heap statistics](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK 17 — Java Management Extensions / MXBean API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/module-summary.html)
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328)
