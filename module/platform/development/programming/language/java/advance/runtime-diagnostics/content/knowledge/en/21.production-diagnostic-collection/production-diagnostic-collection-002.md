# 21.2 Prioritizing Collection by Symptom and Remaining Time Before the Incident Vanishes

## Objectives

In operations, **diagnostic evidence has an expiration window**. A JVM may recover on its own, be replaced by an autoscaler, be terminated by the OOM killer, have its container rescheduled, or experience a CPU/latency spike lasting only tens of seconds. If you choose the wrong collection order, by the time a multi-gigabyte heap dump finishes writing, the deadlocked thread is gone, the instance has restarted, and the in-memory JFR recording no longer exists.

This lesson teaches how to choose **the right evidence, in the right order, at the right risk level** based on symptoms and the expected remaining lifetime of the incident. After completing this lesson, you will be able to:

1. Distinguish evidence that **vanishes when the process dies**, evidence already available in logs/monitoring, and evidence that must be prepared **before an incident**.
2. Prioritize by symptom: **hang/deadlock, CPU spike, GC thrashing/heap OOM, native RSS growth, I/O/latency, and crash/restart**.
3. Use remaining time (a few seconds, under a minute, several minutes, long-term stability) to choose among **JFR dumps, thread dumps, process/OS snapshots, heap histograms, heap dumps, and NMT**.
4. Differentiate **fast/low-risk snapshots** from operations that **can pause the JVM, consume disk/CPU, and alter live state**.
5. Preserve **timestamps, PID/container identity, access controls, and file provenance** so teams can correlate evidence post-incident.
6. Design **runbooks and preconfiguration** so short incidents still yield enough data, rather than pinning all hopes on running commands after failure occurs.

**Rule of thumb:** there is no single rigid order suitable for every incident. A step's priority depends on **how likely the evidence is to vanish, its value in answering the diagnostic question, capture duration, system impact, storage capacity, and data security**. When a process appears to have only seconds left to live, grab what can finish immediately without hastening its termination.

## 1. Why Does Evidence Ordering Matter?

Imagine a JVM heading toward an OOM in 30 seconds:

~~~text
T0     Memory/RSS anomaly begins
T+5s   Alerts fire; JVM is still running
T+10s  On-call identifies the right container/PID
T+15s  Can dump running JFR, read metrics, grab stacks
T+25s  Heap may hit limit, GC thrashes
T+30s  OOM killer or platform restarts process
T+31s  /proc/PID, thread states, live heap: no longer accessible
~~~

If at T+15s you launch **GC.heap_dump** on a large heap, the command may take too long, increase disk pressure, and destabilize an already struggling JVM. A heap dump can be invaluable for a leak, yet it is not the automatic **first step** on a process about to be killed.

Conversely, if you observe **slow memory growth over many hours**, have approval to dump, and possess ample disk and time, a well-timed heap dump can be more decisive than several thread dumps. Prioritization must therefore follow **symptoms and time remaining**, not a blind "run every command" checklist.

### 1.1. Evidence Types Have Different Lifespans

| Evidence Type | When Is It Lost? | Priority When Instance Is Dying |
| --- | --- | --- |
| **Java thread stack/state**, lock owners, in-flight tasks | Vanishes when threads change state or process exits | Very high for hangs, deadlocks, CPU spikes |
| **Running JFR** | In-memory buffers and process repository may disappear on exit/eviction; some files survive if flushed | Very high if a recording exists and covers the fault window |
| **/proc/PID, native threads, RSS, fds, socket/memory maps** on Linux | Vanishes when the process exits | High when an OS/native perspective is needed |
| **Heap object graph at fault state** | Cannot be recaptured after GC, restart, or once the leak clears | High for retention/OOM, but dump cost is substantial |
| **GC/class histogram** | Snapshot shifts across GC cycles and may itself alter state | Medium–high depending on symptoms and risk |
| **Continuous GC/application logs** | Usually survive restarts if shipped externally; may rotate/delete or live only on ephemeral disk | Capture/freeze early, though not a substitute for live snapshots |
| **Metrics pushed to observability systems** | Depends on retention/scrape period; often survive process death | Retrievable afterward, but exact window must be recorded |
| **Fatal-error log, core file, configured OOM heap dump** | Generated on failure; may sit on non-persistent local disk | Preserve immediately post-crash; do not assume they are always produced |

**Important:** Kubernetes Pod UID, container ID, and Linux PID are distinct identities. PIDs can be reused after a process dies. During handoffs, record **host, namespace/container, start time, and PID** so you do not accidentally analyze a different JVM.

### 1.2. Three Questions Before Pressing Enter

1. **What is the primary symptom to explain?** CPU, hang, heap, native RSS, I/O, crash, or mixed?
2. **How long will the evidence remain?** Just seconds before restart, under a minute, or stable for tens of minutes?
3. **Will this command worsen the system or destroy the data being captured?** Stop-the-world, Full GC, heap dump disk I/O, major pauses, secrets, quotas, permissions?

If question 2 is "a few seconds" and question 3 is "may take minutes," pick a fast, high-value snapshot or dump an already configured recording rather than forcing a heavy command at all costs.

## 2. Selection Rules by Remaining Time

The intervals below are **illustrative coordination bands**, not a guarantee that JVM commands will complete within the stated window:

| Estimated Time Remaining | Goal | Do First | Consider Carefully |
| --- | --- | --- | --- |
| **0–15 seconds** | Rescue the hardest-to-reproduce traces | Confirm PID; dump **already-running JFR** or capture **one thread snapshot** per symptom; record timestamp, Pod/process state | Avoid launching a large heap dump or collecting dozens of unrelated metrics |
| **15–60 seconds** | Secure initial snapshot plus one complementary view | JFR dump + thread/OS metrics or fast memory snapshot per symptom; log any attach errors | Histogram/heap dump only if high value, system can tolerate it, and disk allows |
| **1–5 minutes** | Capture time-series and root-cause indicators | Repeat **thread/CPU/GC/OS samples**, JFR, pool metrics; then selectively run histogram/NMT and controlled dump | Do not wait for a "complete set" before saving critical snapshots |
| **Over 5 minutes / stable** | Before–after comparison, deep analysis | Baseline, JFR profile over sufficient window, NMT diff if enabled, heap dump when appropriate, log/trace correlation | Weigh overhead, security, backpressure, and capture frequency |

Sometimes you cannot tell how long an incident will last. In that case, assess **high instance-loss risk**: restart loops, container `memory.current` approaching limit, rapidly climbing RSS, OOM messages, or an impending watchdog kill. **Prioritize immediate snapshots** instead of waiting for clean dashboards.

**Order by "value over cost":** evidence that can answer a key question, is about to vanish, finishes quickly, and has minimal impact comes first. If taking a dump is likely to trigger an earlier OOM or eviction, its expected value drops.

## 3. Symptom-Driven Dispatch Table

| Symptom | First, When Very Little Time Remains | Next, If JVM Stays Alive | Deep Capture When Time/Resources Permit |
| --- | --- | --- | --- |
| **Hang/deadlock, stalled requests** | **Thread.print -l** or ready thread dump; record PID/time | Repeat thread dumps to spot sustained waits; dump running JFR | JFR ThreadPark/JavaMonitorEnter, lock ownership, queue/pool/DB |
| **Brief CPU spike** | OS process/thread CPU snapshot and/or **JFR.dump** of running recording | Repeat CPU-by-thread, stack snapshots, timestamps | JFR ExecutionSample, appropriate native profiling, code/JIT/GC correlation |
| **GC thrash, imminent heap OOM** | Existing JFR, heap/GC metrics, GC logs, and process/cgroup memory snapshot | Histogram if tolerable; verify heap used after GC | Heap dump when time/disk/approval suffice, MAT, GC-root paths |
| **Native RSS growth / container OOM** | RSS/RssAnon/RssFile, Threads, cgroup memory/current/events, quick OS maps | **VM.native_memory summary** if NMT enabled, BufferPoolMXBean, fd count | Detailed smaps, NMT baseline/diff if present, native profiler/JNI |
| **I/O / latency spike** | Timestamps, errors/timeouts, inflight/queue/pool, available JFR | Thread dumps, socket/file metrics, DNS/DB/network indicators | JFR SocketRead/Write/FileRead/Write, traces, and before/after load |
| **Crash/restart already happened** | Preserve logs, `hs_err_pid`, core, exported heap dump/JFR, Pod events | Timeline of OOM/exit code, last state, host/container metrics | Reproduce with preconfigured diagnostics; cannot snapshot a dead JVM |
| **Classloader/metaspace growth** | Metaspace/heap overview, JFR/NMT if available | Classloader stats, class-load count | Heap dump / classloader reference paths and NMT detail if pre-enabled |

**This is a priority guide, not a mandate to run every command.** For an 8-second CPU spike, a heap dump is usually lower value than CPU/JFR snapshots. For prolonged heap retention on a stable PID, a heap dump can be the decisive evidence.

## 4. Understand Command Impact Before Capturing

For **HotSpot JDK 21**, **jcmd** documentation classifies *impact* per command; actual cost depends on heap size, thread count, and system health:

| Command / Source | Meaning | Impact Considerations |
| --- | --- | --- |
| **jcmd PID JFR.check** | Inspect active recordings | Typically **Low** |
| **jcmd PID JFR.dump** | Export active recording to file while continuing | Typically **Low**, still incurs I/O and file storage cost |
| **jcmd PID Thread.print -l** | Thread stack/locks snapshot | **Medium**, can be heavy with very high thread counts |
| **jcmd PID GC.heap_info** | Current heap overview | **Medium** per JDK 21 |
| **jcmd PID VM.native_memory summary** | NMT memory summary when enabled | **Medium**; unavailable if NMT was not enabled |
| **jcmd PID GC.class_histogram** | Count instances/shallow bytes by class | **High**, depends on heap and options; may trigger GC |
| **jcmd PID GC.heap_dump** | Generate HPROF heap dump | **High**, heavy disk/CPU, triggers Full GC by default unless `-all` is used |
| **/proc/PID/status, smaps_rollup** | Linux OS memory/thread snapshot | Usually lighter than full heap dump, subject to permissions and mapping count |
| **Core dump / native profiler** | Deep native state | High impact/size/permission requirements; only when qualified and planned |

**Do not treat Low/Medium/High as fixed time SLAs.** When a JVM is severely stalled, `jcmd` attach may hang or time out. You may have to rely on **previously emitted data** (log shippers, existing JFR files, metrics, crash artifacts) rather than waiting indefinitely for attach.

### A Heap Dump Can Destroy the Very State You Want to Inspect

**GC.heap_dump** requests a Full GC before dumping by default (HotSpot), except when the **-all** option is passed. A Full GC can alter reachable object counts/heap usage and disrupt the application. The `-all` mode retains unreachable objects as well, so interpreting a "leak" must adjust accordingly.

Never run a dump just to "see what's in there" during the final minute before OOM. Check heap size, free disk/inodes/quota, write throughput, filesystem state, and incident commander authorization. An HPROF file can be huge and contain **passwords, tokens, customer data, SQL strings, and business objects**.

## 5. Best Foundation: Pre-Incident Preparation

An incident lasting a few seconds rarely gives you time to start a new profiler, wait for samples, and then dump. **Preparation** is almost always worth more than heroic manual intervention during failure.

### 5.1. Continuous Logging and Metrics

Prioritize having these in place ahead of time:

- GC logs with timestamps, rotation, and shipping to durable storage within cost policies.
- Application errors, request latency (p95/p99), success/error/timeout counts, inflight/queue depth, and key I/O indicators.
- JVM heap/non-heap, thread count, JIT/GC counters, and container RSS/`memory.current`, CPU throttling/restarts.
- Host/container event timeline, OOMKilled, exit codes, and accurate timestamps.
- Pod UID/container ID, version/build ID, and deployment change events.

If the scrape interval is 30 seconds and a spike lasts 3 seconds, metrics may **miss the peak entirely**. Consider higher-resolution metrics or continuous recording; never force a sparse sample into an absolute conclusion.

### 5.2. Bounded Rolling JFR

In HotSpot, a recording can be started at JVM launch via **-XX:StartFlightRecording** with appropriate settings. Conceptual example:

~~~bash
java \
  "-XX:StartFlightRecording=name=continuous,settings=default,maxage=30m,maxsize=256m,disk=true" \
  -jar app.jar
~~~

**This is only a startup example for an existing `app.jar`.** Ensure heap/disk/resources are adequate; verify flags against your JVM/vendor and policies. **maxage/maxsize** cap retained recording data. Do not assume `default.jfc` captures every useful event; if socket latency or monitor stacks are needed, verify effective settings and thresholds.

When an incident occurs, if the recording has **already been running long enough**, you can run **JFR.dump** without waiting for a new recording to accumulate data. Starting JFR **at T+20s** cannot reconstruct a CPU spike that happened at **T+5s**.

### 5.3. Preconfigured OOM/Crash Artifacts

Example JVM options to evaluate before enabling:

~~~bash
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/secure/diagnostics
-XX:ErrorFile=/secure/diagnostics/hs_err_pid%p.log
~~~

These options belong on the actual Java command line, not as three standalone shell commands. **HeapDumpOnOutOfMemoryError** generates a heap dump when the JVM throws a **Java OutOfMemoryError** under applicable conditions; it **does not guarantee** a dump if the **kernel/container OOM killer sends SIGKILL** or disk space runs out.

**-XX:ErrorFile** applies to applicable fatal error logs and does not mean every Java exception creates an `hs_err`. Core dumps require separate OS configuration and sensitive-data controls.

**Preconfiguration does not guarantee every crash produces a file.** After an incident, still verify actual files, exit reasons, paths, and upload/retention.

## 6. Initial Linux Runbook: Verify Identity and Freeze Lightweight Metrics

This step targets a live Java process on a host/container with **jcmd** and access permissions. Do not assume running from another container sees the same PID namespace. Replace `PID=12345` with the real PID and use a path **readable only by authorized users**.

~~~bash
PID=12345
umask 077
OUT="/secure/diagnostics/incident-$(date -u +%Y%m%dT%H%M%SZ)-$PID"
mkdir -p "$OUT"

date -u '+%Y-%m-%dT%H:%M:%SZ' > "$OUT/utc-time.txt"
ps -o pid,ppid,lstart,etime,rss,vsz,nlwp,comm -p "$PID" \
  > "$OUT/process-identity.txt" 2>&1

# These files exist only on Linux and may be restricted by /proc permissions:
cat "/proc/$PID/status" > "$OUT/proc-status.txt" 2>&1
cat "/proc/$PID/limits" > "$OUT/proc-limits.txt" 2>&1
~~~

**ps** and `/proc` confirm whether the process is alive, its start time, RSS/VSZ, and native thread count. **Never treat PID as a durable identity**; if the process restarts and the PID changes, later outputs must not be merged as the same JVM. Also record **host, container ID/Pod UID, application version, namespace, and incident ID** in your incident management system.

**Avoid automatically copying full command lines into broadly shared artifacts**: command lines and environments can contain secrets. Never dump `/proc/PID/environ` or heap dumps to public locations. This example **does not create cgroup identity automatically** and does not verify write permissions on `/secure/diagnostics`; that directory must exist or be creatable in your environment.

### When Attach Works and JFR Is Already Running

~~~bash
jcmd "$PID" JFR.check > "$OUT/jfr-check.txt" 2>&1

# Only when JFR.check confirms an active recording:
jcmd "$PID" JFR.dump filename="$OUT/incident.jfr" \
  > "$OUT/jfr-dump-result.txt" 2>&1
~~~

Per JDK 21 documentation, **JFR.dump writes a file without stopping the active recording**. If multiple recordings exist, pass **name=...** to select the right one. A successful `JFR.dump` message does not replace **verifying the file exists, has valid size, and covers the incident time window**.

~~~bash
ls -lh "$OUT/incident.jfr"
jfr summary "$OUT/incident.jfr"
~~~

**Do not run `JFR.start` and claim you rescued the 30 seconds prior to starting it.** A new recording only captures from its start time onward; lost events cannot be recovered.

### When the Primary Problem Is Hang / Lock Contention

~~~bash
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$OUT/threads-1-time.txt"
jcmd "$PID" Thread.print -l > "$OUT/threads-1.txt" 2>&1

# If the incident persists, capture again for comparison:
sleep 5
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$OUT/threads-2-time.txt"
jcmd "$PID" Thread.print -l > "$OUT/threads-2.txt" 2>&1
~~~

If only 5–10 seconds remain, capture **one** thread dump first rather than waiting for 3 snapshots. If over a minute remains, multiple dumps spaced 5–10 seconds apart distinguish transient waits from sustained deadlocks or blocked queues. `Thread.print` on JDK 21 prints thread stacks within its supported scope; for **virtual threads**, dump contents and visibility depend on JDK and command. When dumping large numbers of virtual threads, investigate **Thread.dump_to_file** or JFR on supporting JDKs rather than assuming a single `Thread.print` lists all virtual threads.

### When the Primary Problem Is a CPU Spike

~~~bash
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$OUT/cpu-1-time.txt"

# Linux: snapshot native threads, CPU, and state at sampling time:
ps -L -p "$PID" -o pid,tid,psr,stat,pcpu,comm \
  > "$OUT/os-threads-cpu.txt" 2>&1

# Complement with Java stacks while the spike is still happening:
jcmd "$PID" Thread.print > "$OUT/cpu-thread-stacks.txt" 2>&1
~~~

OS per-thread CPU and Java stacks should be taken **close to the same timestamp**, though `pcpu` from `ps` follows its own measurement semantics and is not an exact per-method profile. When hot methods are needed, **JFR ExecutionSample** from an already-running recording is usually more informative than a single thread dump. If a CPU spike vanishes after 3 seconds, there may not be enough time to start a meaningful new recording.

## 7. Memory Symptoms: Choosing by Risk and Time

### 7.1. Heap Growth / GC Thrashing Near OOM

While the process is alive, prioritize:

1. **Existing GC logs/metrics**, plus a JFR dump if a recording is running; capture a **memory/GC snapshot**.
2. Record **RSS/container memory, heap used/committed, last GC, and restart policy** to separate Java heap OOM from cgroup OOM.
3. If the JVM is still running and can tolerate a pause with proper approval, use **GC.class_histogram** to see which classes dominate instance counts and shallow bytes.
4. Only when **heap retention** is a prime suspect and disk/time/authorization are sufficient, take **GC.heap_dump**; log when it ran, whether Full GC occurred, file size, and security handling.
5. Post-incident, inspect the HPROF in MAT for **Dominator Tree, retained size, and Paths to GC Roots**. Never conclude a leak from a single histogram.

Commands with escalating impact—do not run blindly in sequence:

~~~bash
jcmd "$PID" GC.heap_info > "$OUT/heap-info.txt" 2>&1

# High impact; run only after risk evaluation:
jcmd "$PID" GC.class_histogram > "$OUT/class-histogram.txt" 2>&1

# High impact, may trigger Full GC; creates a very large file:
jcmd "$PID" GC.heap_dump "$OUT/heap.hprof" \
  > "$OUT/heap-dump-result.txt" 2>&1
~~~

**There is no rule saying "you must run heap_dump before dying."** If the process has 10 seconds left and a dump will clearly blow the disk/time budget, rescue lightweight stats, running JFR, and logs. Conversely, if this is a rare chance to catch a one-off leak and resources allow, deciding to dump early may be far more valuable than unrelated snapshots.

### 7.2. Native RSS Growth Without Heap Growth

Capture OS metrics first since they vanish immediately on exit:

~~~bash
grep -E '^(VmSize|VmRSS|RssAnon|RssFile|RssShmem|Threads):' \
  "/proc/$PID/status" > "$OUT/memory-status.txt" 2>&1

# Linux kernels supporting smaps_rollup:
cat "/proc/$PID/smaps_rollup" \
  > "$OUT/smaps-rollup.txt" 2>&1
~~~

Next, if **NMT was enabled at JVM startup**:

~~~bash
jcmd "$PID" VM.native_memory summary scale=MB \
  > "$OUT/nmt-summary.txt" 2>&1
~~~

- **NMT** records HotSpot-tracked allocations split by reserved/committed; it does not capture all native allocations from JNI/third-party libraries and does not directly equal RSS.
- **/proc/PID/status**: `VmRSS` is resident memory; `VmSize` is virtual address space; `RssAnon`/`RssFile` distinguish anonymous vs. file-backed pages at the OS level.
- **smaps_rollup**: RSS/PSS/Private/Shared; depending on kernel and permissions, it may be inaccessible.
- **NMT not enabled at startup**: you cannot turn on NMT summary/detail mid-flight using `jcmd`. Record "NMT unavailable," rely on OS/process metrics, `BufferPoolMXBean`, and a plan to enable it for reproduction.
- **NMT baseline/diff** is meaningful only when a prior baseline and subsequent snapshots exist; you cannot "diff into the past" if you set the baseline only after the incident.

If cgroup `memory.current` climbs while process RSS does not match, do not blame every cgroup byte on the Java PID: page cache, kernel accounting, and other processes in the cgroup may contribute.

## 8. I/O and Latency Symptoms: Capture at the Right Time, Not Just the Right Tool

When p99 latency spikes suddenly while throughput continues:

**Within the first few seconds**, record timestamps, request success/error/timeout rates, inflight counts, queue lengths, active/pending connection pool stats, cgroup CPU throttling, and running JFR (if any). That snapshot shows whether the bottleneck was active during the error window.

If it persists long enough:

- Repeat thread dumps to check for threads waiting on I/O/locks/parks or an exhausted thread pool.
- Inspect JFR **jdk.SocketRead**, **jdk.SocketWrite**, **jdk.FileRead**, **jdk.FileWrite**, **jdk.ThreadPark**, and **jdk.JavaMonitorEnter** when those events are enabled.
- Correlate DB connection pools, downstream response times, network RTT/retransmits, disk queues, and OS metrics.
- Record **the exact same time window** for client/server latency and JFR. A 500 ms `SocketRead` might belong to one specific request; you cannot infer overall p99 latency from that event without correlation.

**Do not start with a heap dump** simply because requests are slow. If thread dumps/JFR point to I/O waits or lock contention, a heap dump is rarely the highest-value tool in a short incident.

**Do not equate `Count=0` in JFR with "no I/O"**: the event may be disabled, thresholds may filter short operations, or the recording may not cover the incident window.

## 9. After Process Death: Switch Strategy Immediately

A dead JVM cannot yield live thread stacks, heap graphs, or `/proc/PID`. Do not loop `jcmd PID` endlessly after a container restarts: the old PID may be gone, or a new process may now own that PID.

Workflow:

1. Record **exit timestamp**, exit code/reason (e.g., `OOMKilled` if reported by the platform), Pod UID/container ID, deployment/build ID, and host/node.
2. Preserve **stdout/stderr, GC logs, application logs, platform events, and last metrics** before rotation or eviction deletes them.
3. Look for **hs_err_pid**, core files, HPROF files from **HeapDumpOnOutOfMemoryError**, dumped JFR files, or remaining repository/chunks on disk; never assume files appeared automatically.
4. Check disk paths and permissions; **copy artifacts before the node/container is garbage-collected** if policy permits.
5. When reproducing, configure continuous JFR, GC log shipping, OOM/crash artifacts, and earlier snapshot triggers/alerts.
6. State **bounded conclusions** if evidence is missing; never fabricate thread dumps or HPROF conclusions from a newly restarted JVM's logs.

Note: **OOMKilled (kernel SIGKILL)** is not the same as Java throwing **OutOfMemoryError**. The JVM's heap dump handler may not have a chance to run on SIGKILL, even when configured.

## 10. Ranking Evidence by Value

A simple planning method scores each action along four criteria:

| Criterion | Question | If the Answer Is "High" |
| --- | --- | --- |
| **Volatility** | Will the data vanish immediately on restart, GC, or stack transition? | Capture early |
| **Relevance** | Does it directly distinguish among suspected root causes? | Capture early |
| **Cost / Impact** | Does the command cause pauses, Full GC, heavy disk, timeouts, or sensitive-data exposure? | Defer or require approval |
| **Completion Probability** | Given remaining time, is the command likely to finish? | Prioritize commands that can finish |

Examples:

- For an **8-second deadlock**, a thread dump has high diagnostic power, whereas a heap dump is both slow and off-target.
- For a **one-off heap leak** with 10 minutes remaining, an HPROF may justify its cost over taking 20 more CPU snapshots.
- For a **container about to be OOMKilled**, capturing `/proc`/cgroup snapshots and running JFR is far more feasible than a 6 GiB heap dump.
- For **high CPU without JFR running**, an early per-thread CPU snapshot + thread dump beats starting JFR and waiting several minutes.

**Do not rigidly insist on "getting everything."** Re-evaluate after each action: is the incident ongoing, how much time remains, is the most critical evidence safely stored, and could the next step jeopardize the instance?

## 11. Java 17+ Dispatch Planning Example

The program below **does not execute diagnostic commands**; it simply prints suggested orderings by symptom and urgency band. It uses an illustrative rule for decision-making practice; it **does not predict actual runtime** of heap dumps or `jcmd` and does not replace an authorized runbook.

Create **CapturePriorityDemo.java**:

~~~java
import java.util.List;

public final class CapturePriorityDemo {
    enum Symptom { HANG, CPU, HEAP_OOM, NATIVE_RSS }

    private static List<String> candidates(Symptom symptom) {
        return switch (symptom) {
            case HANG -> List.of(
                    "verify process identity",
                    "one thread dump",
                    "dump existing JFR",
                    "repeat thread dump");
            case CPU -> List.of(
                    "verify process identity",
                    "per-thread CPU snapshot",
                    "dump existing JFR",
                    "correlate repeated samples");
            case HEAP_OOM -> List.of(
                    "verify process identity",
                    "dump existing JFR",
                    "lightweight heap and cgroup snapshot",
                    "consider heap dump only after risk check");
            case NATIVE_RSS -> List.of(
                    "verify process identity",
                    "OS RSS and cgroup snapshot",
                    "NMT summary if pre-enabled",
                    "repeat memory comparison");
        };
    }

    private static void show(Symptom symptom, int secondsLeft) {
        int maximum = secondsLeft <= 15 ? 2
                : secondsLeft <= 60 ? 3 : 4;

        List<String> actions = candidates(symptom);
        System.out.println(symptom + " " + secondsLeft + "s:");
        for (int i = 0; i < Math.min(maximum, actions.size()); i++) {
            System.out.println("  " + (i + 1) + ". " + actions.get(i));
        }
    }

    public static void main(String[] args) {
        show(Symptom.HANG, 12);
        show(Symptom.HEAP_OOM, 45);
        show(Symptom.CPU, 180);
    }
}
~~~

Run on JDK 17+:

~~~bash
javac CapturePriorityDemo.java
java CapturePriorityDemo
~~~

**Exact stdout:**

~~~text
HANG 12s:
  1. verify process identity
  2. one thread dump
HEAP_OOM 45s:
  1. verify process identity
  2. dump existing JFR
  3. lightweight heap and cgroup snapshot
CPU 180s:
  1. verify process identity
  2. per-thread CPU snapshot
  3. dump existing JFR
  4. correlate repeated samples
~~~

This is an example of **priority selection**, not a benchmark. For `HEAP_OOM` without an active JFR recording, **skip the unavailable `JFR.dump` step** and move to the next evidence item. For `HANG` where the JVM does not respond to attach, switch to logs/metrics or out-of-process capture per runbook.

Do not mistake `secondsLeft` in this demo for a command SLA. Even a "low impact" operation can hang due to environment, permissions, I/O, mutexes, or an unresponsive JVM.

## 12. Comparing Scenarios With Equal Time Remaining but Different Priorities

### Scenario A — 30 Seconds Before Instance Replacement

Symptoms: API p99 jumps to 15 seconds, DB pool waiting, CPU low, platform schedules Pod restart in 30 seconds.

**Reasonable order:**

1. Record process/container identity, timestamps, pool pending, inflight, and request errors.
2. Capture a thread dump to see threads blocked on pool acquisition or network reads.
3. Dump **running JFR**, if present, to preserve the timeline leading into the fault.
4. If time remains, grab another thread snapshot and downstream metrics.

**Unreasonable:** generating a 4 GiB heap dump before capturing any lock/pool/thread evidence. The HPROF may be irrelevant and burn through the capture window.

### Scenario B — 30 Seconds, `memory.current` Approaching Limit

Symptoms: Java heap used is relatively flat, while RSS/RssAnon and cgroup `memory.current` rise fast; platform may OOMKill.

**Reasonable order:**

1. Record identity, process memory, cgroup current/max/events, and native thread count.
2. If NMT was enabled upfront, grab a quick NMT summary; dump running JFR to preserve timeline.
3. If NMT is absent, note "unavailable"; inspect `BufferPoolMXBean` if a metrics endpoint already exposes it.
4. Focus on preserving logs and platform OOM events before the process disappears.

**Unreasonable:** running repeated class histograms looking for a "Java object leak" when the heap is flat and native RSS is the issue. Histograms cost time and cannot explain off-heap allocations.

### Scenario C — 20 Minutes Remaining, Reproducible Suspected Heap Leak

Symptoms: after each workload cycle, heap used after GC grows; no imminent restart; ample disk and authorization.

**Reasonable order:**

1. Baseline heap/GC metrics, JFR, and workload timestamps.
2. Capture heap histogram/HPROF at a point of retention, accounting for Full GC semantics.
3. If possible, reproduce and take a second snapshot under equivalent load.
4. Analyze MAT Dominator Tree, retained sets/GC roots, and compare across business lifecycles.

In this situation, a heap dump carries far more diagnostic value than chasing an arbitrary thread dump.

## 13. Evidence Quality, Reliability, and Safety

### 13.1. Timestamping and Provenance

Every artifact should record:

- Incident ID; host, Pod UID/container ID, PID, and JVM start time if available.
- JDK/vendor/version, application version/build, command/tool version.
- **UTC timestamp** at start/end of capture, filename, and config/options.
- Time windows of JFR, GC logs, and metrics; timezone and clock skew across hosts if relevant.
- Command success or failure, exit status, permissions/namespace.
- File size, hash when chain of custody is required, and durable storage location.

When capturing multiple artifacts, use distinct names instead of overwriting earlier files; never let a second capture erase the first piece of evidence. **Data incompleteness** must be stated clearly: JFR only covers the last 10 seconds, thread dump is a single point-in-time, smaps uncollected, NMT disabled, or heap dump failed due to disk space.

### 13.2. Access Controls and Sensitive Data

Thread dumps can expose class/method names and operational details; heap dumps/HPROF, JFR, and crash cores can contain sensitive data. Never upload them to public chats or unapproved systems. Use **umask 077**, private directories, access controls, encryption/retention, and proper redaction workflows.

**Never automatically run destructive commands** like `kill -9`, `GC.run`, or restarts just to "make capture easier" unless backed by a runbook and authority. Remediation actions can destroy the root cause and impact customers; if a restart is unavoidable, rescue lightweight data first and coordinate with the incident commander.

### 13.3. Avoiding Making Collection the Culprit

- Overly dense JFR settings, verbose logging, or stack traces can add noticeable overhead.
- Histograms and heap dumps are heavy and require disk space and time.
- NMT has overhead and must be enabled upfront via appropriate flags.
- Full `smaps` on processes with huge mapping counts can be expensive; try `smaps_rollup` first if sufficient.
- Never read/write all of `/proc` or dump gigabytes of artifacts onto a filesystem near quota; doing so can trigger eviction or another OOM.
- If SRE/security policy prohibits attach in production, rely on approved metrics, JFR, and logs; never bypass permissions.

## 14. How to Report Post-Incident

An effective collection report includes:

**A. Decision at incident time:** "CPU spike, estimated 10–15s left; prioritized OS thread CPU + running JFR, deferred heap dump as irrelevant and high-risk."

**B. Actual artifacts:** "JFR dumped covering T−30s to T+5s; thread dump at 09:10:12; process RSS/cgroup at 09:10:13; missing further snapshots due to process restart at 09:10:15." This is an illustrative presentation.

**C. Evidence limits:** "No heap dump; NMT not enabled; JFR ExecutionSample is sampling-based; insufficient evidence to confirm a native leak."

**D. Next actions based on gaps:** add rolling JFR, GC log shipping, earlier capture triggers, cgroup OOM alerts, dedicated dump disk, or staging reproduction.

Never write **"verified no leak"** when you only have a thread dump. Never write **"no deadlock"** from a single stack snapshot taken after the spike ended. **Good evidence must be strictly scoped to what was actually captured and when.**

## 15. Common Pitfalls

1. **Running a heap dump first for every symptom**: slow, High impact, and often irrelevant.
2. **Waiting until the incident ends to start a recording**: `JFR.start` cannot reconstruct a lost timeline.
3. **Taking a single thread dump after a hang self-recovers**: fails to reflect the fault state.
4. **Omitting PID/Pod UID/start time**: easily conflates JVMs across restarts or PID reuse.
5. **Stopping JFR just to dump** unnecessarily: `JFR.dump` normally keeps the recording running.
6. **Assuming `JFR.dump` always succeeds**: missing recordings, missing permissions, or full disks can cause failure.
7. **Thinking NMT can be enabled late to diff against pre-incident memory**: incorrect.
8. **Using `GC.class_histogram` as proof of a native RSS leak**: a Java heap histogram does not inventory all native memory.
9. **Treating reserved code cache, committed heap, and RSS as the same quantity**: they are not directly comparable.
10. **Triggering Full GC before preserving evidence**: alters the heap and extends pauses.
11. **Treating absence of event as absence of phenomenon**: recording settings, thresholds, or coverage may be insufficient.
12. **Not checking the filesystem**: dumps fail partway, exhaust quotas, and worsen the outage.
13. **Killing/restarting an instance before rescuing a high-value snapshot**: live evidence is lost.
14. **Looping `jcmd` against a dead PID**: wastes time and risks hitting a different process reusing that PID.
15. **Counting files without checking content/time window**: files may be empty or miss the incident interval.
16. **Failing to distinguish OOMKilled from Java OutOfMemoryError**: changes whether an HPROF is expected.
17. **Sharing dumps containing secrets without proper authorization**: privacy and security exposure.
18. **Collecting more data than can be analyzed without a hypothesis**: raises overhead while missing vital evidence.

## 16. Self-Check Quiz

**Q1.** Roughly 8 seconds remain before restart; the JVM is hung with no evidence of heap growth. Should you take a thread dump or a heap dump first?  
**Answer:** prioritize a quick thread dump/lock snapshot and identity; a heap dump is both costly and poorly targeted.

**Q2.** A CPU spike just ended, and then you invoke `JFR.start`. Can you recover stack samples from the earlier spike?  
**Answer:** no. A new recording captures only from its start time; only a pre-existing rolling JFR or profiler could have preserved past data.

**Q3.** A container was OOMKilled with SIGKILL even though `HeapDumpOnOutOfMemoryError` was enabled. Is an HPROF guaranteed to exist?  
**Answer:** no. Check for the actual file; a kernel kill may bypass Java `OutOfMemoryError` and leave the JVM no time to dump.

**Q4.** NMT was not enabled at startup, and 40 seconds remain before restart. Can `VM.native_memory summary.diff` reveal a native leak over the past two hours?  
**Answer:** no. NMT cannot retroactively track past allocations, and baseline/diff requires pre-enabled tracking plus an earlier baseline.

**Q5.** `JFR.dump` created a file, but `jfr summary` shows the recording ended 30 minutes before the incident. Can it explain the current CPU spike?  
**Answer:** insufficient—the recording must cover the incident timestamp. A file named "incident.jfr" does not prove relevance.

**Q6.** With RSS rising, Java heap steady, and `RssAnon` growing, should you run Java heap histograms repeatedly before inspecting `/proc` and NMT?  
**Answer:** generally no. Prioritize OS/native evidence and NMT if pre-enabled, then choose heap tools only if a matching hypothesis emerges.

**Q7.** The system has 20 minutes left, a reproducible heap leak, and ample disk. Is capturing a heap dump reasonable?  
**Answer:** it can be reasonable after weighing High impact/Full GC, permissions, disk capacity, and optimal timing to capture the retained graph.

**Q8.** You have a thread dump, GC metrics, a JFR file that misses the incident window, and no application logs due to disk rotation. Can the report declare a definitive root cause?  
**Answer:** only if the remaining evidence is truly sufficient; otherwise state uncertainty, gaps, and preconfiguration improvements.

## References

- [Oracle JDK 21 — jcmd command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): impact, JFR.check/JFR.dump, Thread.print, GC.heap_info/class_histogram/heap_dump, and VM.native_memory.
- [Oracle JDK 21 — Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html): collecting thread traces, JFR, core files, logs, and pre-restart artifacts.
- [Oracle JDK 21 — Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html): JFR while a leak is happening and heap dumps while the JVM is alive.
- [Oracle JDK 21 — Recording API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): maxAge/maxSize, dump, recording lifecycle, and retention limits.
- [Oracle JDK 21 — Java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): StartFlightRecording, HeapDumpOnOutOfMemoryError, HeapDumpPath, and ErrorFile.
- [Linux man-pages — proc_pid_status](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html): VM RSS, virtual memory, native thread count, process fields.
- [Linux kernel — proc filesystem documentation](https://www.kernel.org/doc/html/latest/filesystems/proc.html): /proc/PID/smaps, smaps_rollup, and process metrics.
