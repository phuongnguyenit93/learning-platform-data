# 21.8 Preventing Evidence Loss on Restart and Recording Diagnostic Command Side Effects

## 1. Problem: A Restart Can Wipe Out Both Symptoms and Evidence

A JVM slows down, requests time out, or memory climbs steadily. On-call restarts it, the service recovers quickly, and dashboards switch to the new PID. Yet the old JVM's Java thread stacks, lock owners, heap objects, unexported JFR buffers, GC/JIT counters, native memory mappings, and connection-pool states are gone. Reporting "restart fixed the error" **never proves root cause**.

Even diagnostic actions taken before a restart can **alter the system being measured**. Thread dumps require JVM coordination and produce output; heap histograms or heap dumps can trigger pauses, GC, and heavy disk I/O; enabling JFR adds CPU/memory overhead; changing logging changes what gets written afterward. Without recording the timing and impact of every command, analysts can mistake **tool side effects** for **application symptoms**.

Objectives:

- Classify evidence prone to loss on **process restart**, container replacement, pod eviction, log rotation, forced kill, and `OOMKilled`.
- Collect in priority order: **external-to-JVM data → lightweight snapshots → medium-impact snapshots → heavy dumps only when justified**.
- Know when not to delay a restart, and explicitly document **what could not be captured and why**.
- Tag accurately: **PID, start time, host/container namespace, JDK, UTC timestamp, incident ID**.
- Maintain a **command ledger**: command/flags, start/end, expected impact, observed impact, exit code, output path/size/checksum, and next decision.
- Understand how `JFR.dump` differs from `JFR.stop`; heap dumps differ from OS cores; Java `OutOfMemoryError` differs from kernel/cgroup `OOMKilled`; graceful termination differs from `SIGKILL`.
- Practice with a Java 17+ lab showing file-backed evidence surviving across two JVM runs, while recognizing shutdown hooks **are not guaranteed**.

**Principle:** prioritize state that **exists only while the exact failing JVM is alive**, without sacrificing system availability to run a diagnostic command that exceeds your time or resource budget.

## 2. Classify Evidence Before It Vanishes

| Source | What Can Be Lost After Restart | Preservation Measure |
| --- | --- | --- |
| Live Java threads, monitor/lock state, park/wait stacks | Thread and lock state of the failing incarnation | `jcmd Thread.print -l` or JDK-appropriate thread dump with timestamps |
| Java heap, objects, classloaders, metaspace | Objects/GC roots and failing app state | Heap dump/histogram **only when budget permits**; never default |
| JVM flags, process command line, uptime, GC counters, compiler/code-cache metrics | Counters reset or configs change in the new JVM | `VM.version`, `VM.command_line`, `VM.flags`, `VM.uptime` + build/UID |
| Active JFR recording and repository | Unflushed buffers; overwritten retention window; container files wiped | `JFR.check` then `JFR.dump` to durable location; verify file |
| GC/unified logs, `stdout`/`stderr` | Logrotate, container replacement, node eviction, short retention | Centralized logs, pre-restart export, record time range |
| `hs_err_pid*.log`, OS core, HPROF | May not have been created; file on ephemeral local disk | Preconfigure error/dump paths, core policies, volumes, or export |
| RSS, open FDs/sockets, maps, cgroup memory, process tree | PID disappears and OS counters shift | `ps`, `/proc`, `ss`, OS/container monitoring |
| Downstream DB/pool metrics, application tracing | May outlive the JVM externally, though not forever | Save query/dashboard ranges, incident IDs, log/trace correlation |

**Never mix incarnations:** after a restart, the OS can reuse the same PID; inside containers, PID may always be 1. A PID **alone is not an identity**. Also record process start time, container ID, pod UID, image digest, JDK build, and UTC timestamps.

An OS core dump is **not** an HPROF heap dump; `hs_err_pid*.log` is a text fatal-error report. Java OOME does not guarantee an OS core; container `OOMKilled` via kernel `SIGKILL` usually **gives the JVM no time to write** heap dumps, JFR, or shutdown hooks. Prepare these artifacts upfront or export proactively while alive.

## 3. Decision Order During a Real Incident

"Capture first, restart later" is not an absolute rule. If the service is severely breaching SLOs, disk is nearly full, or the kernel is about to OOMKill, the incident commander may decide to restart immediately and **explicitly document the uncollected evidence**. A multi-GiB heap dump is not worth prolonging an outage or exhausting node storage.

A balanced workflow:

1. **T0 – record context and time budget:** severity, detection time, environment, owner, SLO, max time allowed for capture.
2. **T1 – capture external data outside the process:** CPU/RSS/GC dashboards, error/trace logs, request rate, downstream latency, OOM/eviction events; save time ranges/queries.
3. **T2 – identify the exact failing JVM:** PID + start time/uptime, JDK version, flags, deployment image, container ID, filesystem/memory headroom.
4. **T3 – capture low/medium-impact snapshots:** thread dump if justified, JFR dump if a recording is running, NMT summary if NMT was enabled at startup.
5. **T4 – evaluate heavy captures with approval:** histogram, HPROF, OS core; require disk/CPU/pause/secret-handling budgets, never by default.
6. **T5 – verify files outside the JVM lifecycle:** meaningful output, exit code 0, file exists, sensible size, checksum, copied to durable storage.
7. **T6 – restart and log rationale:** who decided, when, by what method, new PID/incarnation.
8. **T7 – compare before/after:** health, throughput, CPU, GC, memory, p95/p99; annotate command side effects and counter resets.

An **illustrative** deadline example (not a mandatory SLA): spend at most 60–90 seconds on low-impact snapshots; **skip heap dumps** when the container is nearly out of memory or disk. Real budgets depend on architecture, load, recovery deadlines, and approvers.

## 4. Tool Impact Table — Must Be Recorded in the Ledger

`Low/Medium/High` ratings below follow Oracle JDK 21 `jcmd` guidance and do not represent fixed costs. Real impact also depends on thread count, heap size, GC, storage, container quotas, and JDK build.

| Tool / Action | Evidence Sought | Potential Perturbation |
| --- | --- | --- |
| `date`, `ps`, `/proc/<PID>/status`, external metrics | UTC, process identity, RSS, FDs, cgroup state | Small OS overhead, read/namespace permissions, race if PID exits |
| `jcmd <PID> VM.version`, `VM.command_line`, `VM.flags` | JVM vendor/build, launch options, flags | Usually **Low**; attach may wait; command line may contain secrets |
| `jcmd <PID> JFR.check` | Is any recording running? | Usually **Low**, status read only |
| `jcmd <PID> JFR.dump name=... filename=...` | Export retained JFR events | **Low** per docs, yet writes file I/O; **does not stop recording** |
| `jcmd <PID> Thread.print -l` | Java platform-thread stacks and locks | **Medium**: scales with thread count, JVM coordination, large output |
| `jcmd <PID> Thread.dump_to_file -format=json ...` (supporting JDK) | Snapshot including virtual and platform threads | Large output with many virtual threads; not a timeline |
| `jcmd <PID> VM.native_memory summary` | HotSpot-tracked native memory | Requires NMT enabled at startup; carries NMT overhead and misses external native allocations |
| `jcmd <PID> GC.heap_info` | Heap summary | Oracle rates **Medium** |
| `jcmd <PID> GC.class_histogram` | Object/class histogram | **High**: scans heap, can cause pauses/GC; depends on mode and JVM |
| `jcmd <PID> GC.heap_dump /path/file.hprof` | HPROF heap dump | **High**: heavy I/O/CPU/disk, **triggers Full GC by default unless `-all` is used** |
| `jcmd <PID> GC.run` | Requests `System.gc()` | **Mutates heap/GC state**; not pure observation |
| `jcmd <PID> JFR.start` or changing recording settings | Starts capturing new events | Sampling/recording overhead; cannot recover timeline prior to start |
| `jcmd <PID> VM.log ...` / `VM.native_memory baseline` | Alters log config or sets NMT diff baseline | **Alters diagnostic state** and comparison data; may rotate logs |
| `jhsdb ... --pid` | HotSpot SA live inspect | **High risk**: Oracle docs warn it may hang or crash the JVM on detach |
| `kill -QUIT <PID>` (Unix/HotSpot) | May emit thread dump to JVM output | Signal and output stream are non-neutral; logs/files can be lost |
| `SIGTERM` / restart / `SIGKILL` | Terminates JVM | Loses in-memory state; hard kill prevents Java shutdown hooks |

**`GC.heap_dump -all` does not mean "safe":** it avoids the default Full GC request per Oracle, yet remains a High-impact operation, dumps unreachable objects too, and changes how the heap is interpreted. Likewise, `GC.class_histogram -all` changes the counted object set. Always record **the exact options** alongside the artifact.

Distinguish three concepts:

- **Expected impact:** risk from docs and architecture, e.g., "histogram is High impact, may pause."
- **Observed impact:** real numbers from logs/metrics before–during–after the command, such as command duration, GC counts/pauses, CPU, and p99. If unmeasured, record **unknown**, never `0`.
- **Causality:** p99 climbing during a heap dump is a correlation; inspect workload, GC logs, and confounders before asserting the command caused it.

## 5. Linux Runbook: Lightweight Sampling With Intact Provenance

Execute only on JVMs you are authorized to administer. This is a **selective operational example**, not a mandate to run everything in production. Replace PID and incident ID with verified values. `OUT` must sit on durable storage with ample space and restricted permissions.

### 5.1 OS Snapshot Before JVM Commands Can Perturb State

~~~bash
PID=12345
INCIDENT=INC-2026-10-29-001
OUT="/secure/persistent/incidents/$INCIDENT/$PID"
umask 077
mkdir -p "$OUT"

date -u '+%Y-%m-%dT%H:%M:%SZ' > "$OUT/start-utc.txt"
ps -o pid,ppid,lstart,etime,rss,comm -p "$PID" > "$OUT/process.txt"
cat "/proc/$PID/status" > "$OUT/status.txt"
cat "/proc/$PID/smaps_rollup" > "$OUT/smaps-rollup.txt"
cat "/proc/$PID/limits" > "$OUT/limits.txt"
cat "/proc/$PID/cgroup" > "$OUT/cgroup.txt"
~~~

Save `stderr` and exit codes on failure; missing permissions, nonexistent files, non-Linux OSes, and exited PIDs are common causes. `ps` and `/proc` capture instantaneous state **of that exact process**; never substitute a new PID later if the old file wasn't collected. `smaps_rollup` depends on kernel support.

### 5.2 Targeted Diagnostic Commands

~~~bash
jcmd "$PID" VM.version > "$OUT/version.txt" 2>&1
jcmd "$PID" VM.command_line > "$OUT/command-line.txt" 2>&1
jcmd "$PID" VM.flags > "$OUT/flags.txt" 2>&1
jcmd "$PID" VM.uptime > "$OUT/uptime.txt" 2>&1
jcmd "$PID" JFR.check > "$OUT/jfr-check.txt" 2>&1
# Only when lock/thread evidence is needed and pause budget permits:
jcmd "$PID" Thread.print -l > "$OUT/thread-01.txt" 2>&1
~~~

Not every command should run in the same order when the app is dying: with only 10 seconds left, prioritize external data plus an existing JFR dump; never let a thread dump delay recovery past budget.

**Record timing and return codes.** Single-command example:

~~~bash
START_MS="$(date +%s%3N)"
jcmd "$PID" VM.version > "$OUT/version-2.txt" 2>&1
STATUS=$?
END_MS="$(date +%s%3N)"
printf 'command=VM.version exit_code=%s duration_ms=%s\n' \
  "$STATUS" "$((END_MS - START_MS))" >> "$OUT/ledger.txt"
~~~

`date +%s%3N` is GNU `date` and not guaranteed on macOS/BSD. Production runbooks should record start/end UTC, operator ID, tool version, impact, and destination. **Never use `jcmd 0`** because per documentation it can dispatch commands to **all** matching JVMs on the host, far beyond one incident PID.

When taking a second thread dump, record the interval between dumps and thread counts. One thread dump cannot prove a sustained deadlock or measure wait duration; multiple snapshots + lock owners + metrics are far more reliable.

### 5.3 JFR: Snapshot vs. Stop

Once `JFR.check` confirms a recording name, such as `baseline`:

~~~bash
jcmd "$PID" JFR.dump name=baseline filename=/secure/persistent/jfr/before-restart.jfr
~~~

`JFR.dump` **writes retained data to a file while the recording keeps running**; `JFR.stop` is what ends the recording. Never confuse the two. To preserve data before a restart, verify **the file path inside the target JVM's filesystem namespace**: in Kubernetes, a path visible inside the container need not exist on the host terminal and vice versa. Output filenames should include incident ID, PID, and timestamp; never overwrite prior captures.

JFR retains events only within its **retention window** (`maxage`/`maxsize`, repository, and buffers) and per enabled event types. Dumping at minute 30 does not guarantee minute 1 is still present. If JFR was not already running, `JFR.start` begins **from that moment onward** and cannot "record the past" before the incident. Starting JFR also adds overhead and belongs in the ledger.

`JFR.dump` can fail due to no active recording, missing permissions, or full disks; verify **the file exists and is readable** rather than trusting exit code alone. Inspect with `jfr summary /path/file.jfr` on a machine with a compatible JDK after copying to secure storage.

### 5.4 Heap Dump / Histogram: Side-Effect Commands, Not Default Baseline

~~~bash
# Check exact syntax for the running JDK first:
jcmd "$PID" help GC.heap_dump
jcmd "$PID" help GC.class_histogram

# HIGH IMPACT: run only with approval and disk/memory/latency budget.
jcmd "$PID" GC.class_histogram > "$OUT/histogram.txt" 2>&1
jcmd "$PID" GC.heap_dump /secure/persistent/dumps/before-restart.hprof
~~~

Heap dumps trigger a Full GC by default unless `-all` is passed on JDK 21; the tool still consumes disk/CPU and can exhaust remaining headroom. If a GC-triggering command ran, any comparison of heap used/GC count **after** vs. before must mark that intervention. HPROFs can hold tokens, passwords, and customer data; never attach directly to public tickets.

If a Java heap leak is suspected while the app is about to be OOMKilled, **skip the heap dump**, log the missing evidence explicitly, and protect availability. Lighter options include existing GC logs/JFR or OS/cgroup memory history. Never run `GC.run` to "clean up" before capturing baseline state without explicitly noting the state mutation.

### 5.5 Before Restart: Validate Artifacts and Move Out of the Process Lifecycle

~~~bash
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$OUT/capture-end-utc.txt"
ls -lah "$OUT"
find "$OUT" -maxdepth 1 -type f -name '*.txt' -print0 |
  sort -z | xargs -0 -r sha256sum > "$OUT/manifest.sha256"
~~~

Verify files contain real data: `thread-01.txt` might hold only "Unable to attach to target VM" instead of a thread dump. Never hash an incomplete HPROF as final. When the initial file sits in an ephemeral container, **copy/export it to persistent storage and verify the copy's hash** before restarting.

A checksum proves integrity across copying, **not** that the file came from the right PID; always pair with metadata. Never delete/rename original evidence or overwrite an earlier snapshot.

## 6. Kubernetes/Containers: Evidence-Loss Traps

### Kubernetes `--previous` Is Only a Best-Effort Fallback

~~~bash
# Example namespace=payments, pod=api-7f9b6c, container=api:
kubectl -n payments get pod api-7f9b6c -o yaml > pod-before.yaml
kubectl -n payments describe pod api-7f9b6c > describe-before.txt
kubectl -n payments logs api-7f9b6c -c api --timestamps > current.log
kubectl -n payments logs api-7f9b6c -c api --previous --timestamps > previous.log
~~~

`kubectl logs --previous` fetches logs from the prior container instance **only if the node still retains them**. By default, Kubernetes keeps at most one terminated container's logs across restarts, and log rotation or pod eviction can wipe them. Once a pod is deleted, logs may no longer be retrievable via the API. Use centralized logging, export with UTC and correlation IDs, and verify retention.

Capture pod UID, container ID, restart count, image digest, node, PID namespace, cgroup memory events, and quotas. PID 1 **inside a container** does not equal PID 1 on the host. Running `kubectl exec` after a rollout can hit the **new JVM**, not the failing one.

### Docker/Storage and Shutdown

Files in a container's writable layer or `/tmp` are **not guaranteed to survive container replacement**. Bind mounts, PVCs, or object-store shippers are far more durable, yet still require checking permissions, quotas, and transfer completion. Restarting only the process inside the same container might leave files behind, but never rely on that luck for incident retention.

On shutdown, Java shutdown hooks can run during normal termination, whereas **`SIGKILL` prevents hooks from running**. Kernel OOM kills, node crashes, forced pod kills, or expired termination grace periods can cut off JFR/heap/log exports mid-flight. Never assume `dumponexit=true` or `-XX:+HeapDumpOnOutOfMemoryError` always produces artifacts on **`OOMKilled`**. Java-thrown `OutOfMemoryError` and OS `OOMKilled` are two different mechanisms.

If using `systemd` with privileges, check `journalctl -u <unit>` and `coredumpctl list/info` to see whether logs or cores remain; a core file is not an HPROF. Cores and `hs_err_pid` files can hold secrets, so inspect them only in a controlled environment.

## 7. Prepare Trace Preservation From Startup

In operational design, JVM options can direct artifacts onto a **durable volume** upfront. These are **independent options**, not a single shell pipeline:

~~~text
-XX:ErrorFile=/persistent/incidents/hs_err_pid%p.log
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/persistent/incidents
-XX:StartFlightRecording=name=baseline,settings=default,disk=true,maxage=20m,maxsize=256m,dumponexit=true,filename=/persistent/incidents/on-exit.jfr
-Xlog:gc*:file=/persistent/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Conditions:

- `ErrorFile` helps only when HotSpot **gets a chance to write** a fatal-error log; the directory must exist and be writable.
- `HeapDumpOnOutOfMemoryError` does not mean "guaranteed evidence on every OOM"; if the OS kills the process first, no file may be created.
- `StartFlightRecording` with `disk=true` maintains a bounded repository; `dumponexit=true` exports when the JVM exits **cleanly along a supported path**, with no guarantee on hard kills.
- `-Xlog` rotation overwrites older files if collectors lag; size `filecount`/`filesize` to target retention.
- Heap/core/JFR files can consume huge disk and contain secrets. Configure disk alerts, access controls, lifecycle policies, and retention at the destination.

Never continuously enlarge log volumes while running heap dumps as a node nears disk exhaustion. Beyond performance and availability, **crash/heap data** is sensitive and needs access approvals, retention limits, and redaction.

## 8. Diagnostic Ledger: Every Command Has a Reason and a Side Effect

At minimum, record per diagnostic action:

| Field | How to Record |
| --- | --- |
| `incident_id`, `actor`, `approval` | Accountable person and justification |
| `start_utc` / `end_utc` / `duration_ms` | Timestamps aligned to the incident timeline |
| `node/pod/container/PID/process_start` | Identifies the exact JVM incarnation |
| `command` and options | Verbatim command with secrets redacted; include `-all`, `-l`, and sampling settings |
| `expected_impact` | Low/Medium/High per docs/workload profile, GC/safepoint/I/O risk |
| `observed_impact` | Measured GC pauses/counts, CPU, p99, disk bytes, errors, thread pauses |
| `exit_code`, `stderr` | Success vs. attach/permission failure; never log "collected" if failed |
| `output_uri`, `bytes`, `sha256` | Durable storage location, size, integrity hash |
| `limitations` | Missing samples, JFR disabled, rotated files, process exit, partial snapshots |
| `restart` | Decision maker, method/UTC, new JVM PID, uncollected items |

**Illustrative** example, not a real incident:

~~~text
incident=INC-2026-10-29-001
start_utc=2026-10-29T10:14:21Z
target=payments/api-7f9b6c;container=api;pid=12345
command=jcmd 12345 Thread.print -l
expected_impact=medium; actor=oncall; approval=INC-2026-10-29-001
duration_ms=850; exit_code=0; output=thread-01.txt; bytes=294321
observed=thread snapshot created; effect on p99 unknown
limitations=one instant only; no contention duration inference
~~~

If not actually measured, write `unknown`—never invent `0 ms pause`. Separate expected impact (potential risk) from observed impact (real measurements). During post-incident review, overlay command timestamps on SLO, CPU, GC, and RSS graphs; if p99 spikes alongside a dump, check traffic and unrelated GCs before claiming causality.

## 9. Java 17+ Lab: Checkpoints Surviving Across Two JVM Incarnations

This lab **does not self-restart, crash, or take heap dumps**. It creates a unique evidence file per PID/UUID, logs checkpoints and a heap-used reading, and exits. Run it twice in the same directory to see traces from two distinct processes without overwriting files. It includes a shutdown hook illustrating graceful exit, though **never rely on hooks running during `SIGKILL` or node crashes**.

Create **`EvidenceCheckpointLab.java`**:

~~~java
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.UUID;

public final class EvidenceCheckpointLab {
    private static Path artifact;

    private static synchronized void append(String line) {
        try {
            Files.writeString(artifact,
                    Instant.now() + " " + line + System.lineSeparator(),
                    StandardCharsets.UTF_8, StandardOpenOption.APPEND);
        } catch (IOException e) {
            System.err.println("EVIDENCE_WRITE_FAILED="
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: EvidenceCheckpointLab <directory> <seconds>");
        }
        int seconds = Integer.parseInt(args[1]);
        if (seconds < 1 || seconds > 120) {
            throw new IllegalArgumentException("seconds must be 1..120");
        }
        Path directory = Path.of(args[0]).toAbsolutePath().normalize();
        Files.createDirectories(directory);

        long pid = ProcessHandle.current().pid();
        artifact = directory.resolve(
                "evidence-" + pid + "-" + UUID.randomUUID() + ".log");

        String header = "pid=" + pid + System.lineSeparator()
                + "java=" + System.getProperty("java.version")
                + System.lineSeparator()
                + "startUtc=" + Instant.now() + System.lineSeparator();
        Files.writeString(artifact, header, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW);

        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> append("shutdownHook=called"), "evidence-hook"));

        append("phase=start");
        System.out.println("PID=" + pid);
        System.out.println("EVIDENCE_FILE=" + artifact);
        System.out.println("PHASE=READY");

        Thread.sleep(seconds * 1_000L);
        long heapUsed = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getUsed();
        append("heapUsedBytes=" + heapUsed);
        append("phase=finished");
        System.out.println("PHASE=FINISHED");
    }
}
~~~

Explanation:

1. `PID + UUID` prevents overwriting another run's incident file; `CREATE_NEW` fails rather than replacing an existing file.
2. `append()` logs UTC per milestone alongside Java version and PID; this is a checkpoint, **not a full heap dump** or OS RSS.
3. `MemoryMXBean.getHeapMemoryUsage().getUsed()` measures instantaneous Java heap used, distinct from NMT `committed`, OS RSS, and retained size.
4. `shutdownHook=called` appears on normal exit; it does not mean hard kills or broken filesystems will record it.
5. Only a directory truly **durable across the container/pod lifecycle** preserves files. Files in temp or writable layers are not a retention strategy.

Compile and run twice with JDK 17+:

~~~bash
javac EvidenceCheckpointLab.java
java EvidenceCheckpointLab ./incident-evidence 2
java EvidenceCheckpointLab ./incident-evidence 2
~~~

Stdout shape (PID and path vary per run):

~~~text
PID=<OS-assigned-PID>
EVIDENCE_FILE=<absolute-path>/evidence-<PID>-<UUID>.log
PHASE=READY
PHASE=FINISHED
~~~

After two runs, `incident-evidence` holds two distinct files. Each file is expected to contain `pid=`, `java=`, `startUtc=`, `phase=start`, `heapUsedBytes=`, `phase=finished`, and on clean exit `shutdownHook=called`. Check `stderr` if any file write fails. Heap bytes, PIDs, and UUIDs are **non-deterministic**.

To inspect live state of **the lab JVM itself**, run for `120` seconds and invoke `jcmd` from another terminal using the printed PID:

~~~bash
java EvidenceCheckpointLab ./incident-evidence 120
# While the lab is alive, in a second terminal:
jcmd <PID> VM.version
jcmd <PID> Thread.print
jcmd <PID> JFR.check
~~~

These `jcmd` calls are conditional inspection commands on a **demo JVM**, not proof that production behaves identically. Never run `kill -9` on someone else's service to test this. Knowing that `SIGKILL` skips shutdown hooks is enough to justify **external persistence before restart**.

## 10. Diagnostic Scenarios and Accurate Reporting

### A. Service Hung, Needs Early Restart

An API hangs with thousands of queued requests; within a 60-second budget you can capture alert timestamps, downstream/pool metrics, process identity, one or two thread dumps, and a JFR dump if already running. If `jcmd` fails to attach or exceeds budget, **log the failure** and let the incident commander restore service. Never swap in `jhsdb --pid` recklessly, since live SA attach can freeze or crash the target.

After restart, analyze pre-restart events, locks, and wait states alongside queue/pool metrics. Never declare the restart fixed the root cause merely because latency returned to normal.

### B. Memory Near OOMKilled, Insufficient Disk to Dump

Heap or native memory is climbing, cgroup memory nears limit, and disk is tight. `GC.heap_dump` risks pausing the JVM and exhausting resources. A sound decision is **skipping the heap dump**, capturing OS/cgroup memory and existing GC logs/JFR, and logging the reason: "heavy capture exceeded budget; no HPROF." Distinguish Java OOME from kernel OOMKill. Never trigger another OOM just chasing a potentially incomplete file.

### C. High CPU That Vanishes After Restart

Pre-restart process ran at 100% CPU; post-restart runs at 20%. Never treat post-restart `jcmd`/JFR as a profile of the old JVM. Compare only pre-restart CPU time/throughput/JFR exports and historical metrics from the same window. If JFR was started only near the end of the outage, document exact coverage rather than inventing earlier CPU behavior.

### D. Heap Lower After Diagnostics Than Before

On-call runs default `GC.heap_dump` and observes heap used drop afterward. Dumping can request a Full GC; comparison tables must separate "heap-used-before" and "heap-used-after-diagnostic-GC" rather than interpreting the drop as self-recovery. If a latency spike coincides, inspect GC events and command duration before concluding.

## 11. Common Mistakes

1. **"Restart fixed it, so no thread dump was needed."** May have wiped out the only lock/queue evidence.
2. **"File exists means the command succeeded."** File may contain only "Unable to attach" or be truncated.
3. **"`JFR.dump` stops the recording."** False; `JFR.stop` does.
4. **"`dumponexit=true` guarantees a recording on `OOMKilled`."** False; `SIGKILL` skips graceful shutdown.
5. **"`HeapDumpOnOutOfMemoryError` always saves the day on kernel OOMKill."** False; Java OOME differs from OS kill.
6. **"Histograms and heap dumps are free read-only commands."** False; they scan the heap, can trigger GC/pauses, and consume heavy disk/CPU.
7. **"`GC.run` leaves the system unchanged."** False; it alters heap state and metrics.
8. **"`jcmd 0` targets the first process."** False; it can broadcast to all matching JVMs.
9. **"`kubectl logs --previous` lasts forever."** False; retained only while node container log retention holds.
10. **"`/tmp` inside a container is durable evidence."** False once the container/pod is replaced.
11. **"Same PID means the same JVM."** False due to PID reuse and namespaces.
12. **"Run heap dump and restart immediately without verifying."** The file may still be writing, copying, or unreadable.
13. **"No need to log which commands ran to find root cause."** Data was already perturbed and timeline context is lost.
14. **"Expected impact Low means latency cannot budge."** False; measure on the actual workload and JDK build.
15. **"Attaching raw core/HPROF files to public tickets is fine."** Can leak tokens, passwords, and user data.

## 12. Pre- and Post-Restart Checklist

### Before

- [ ] Incident ID, severity, SLO, operator, approval, and **time budget** for evidence are set.
- [ ] UTC, PID/start time, image/container/pod UID, JDK vendor/build, and runtime flags recorded.
- [ ] Dashboards/metrics/logs/traces saved for the pre-fault window.
- [ ] Diagnostic commands chosen by **necessity** and Low/Medium/High impact.
- [ ] Every command logs start/end/exit code/output, expected impact, and observed impact/`unknown`.
- [ ] Active JFR dumped if appropriate; files verified outside volatile filesystems.
- [ ] Heavy GC/histogram/heap dumps avoided when lacking disk/CPU/pause budget.
- [ ] File permissions, sizes, checksums, and copies to durable storage verified.
- [ ] Anything **impossible to collect** documented with reasons before restart.

### After

- [ ] Restart time, method, and `SIGKILL`/`OOMKilled` reason (if any) recorded.
- [ ] Old and new JVM incarnations kept distinct; never subtract/add GC counters across different PIDs/start times.
- [ ] Pre-restart artifacts verified readable and properly access-controlled.
- [ ] Throughput, CPU, memory, p95/p99, and error rate compared at matched load.
- [ ] Incident timeline annotates state-changing commands, outcomes, and limitations.
- [ ] Instrumentation, continuous JFR, and retention plan updated for recurrence.
- [ ] Security, redaction, and retention policies enforced on HPROF/cores/logs.

### Official References

- Oracle JDK 21 — `jcmd`, per-command impact, `GC.heap_dump`, `Thread.print`, and `JFR.dump`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — `java`, `StartFlightRecording`, `HeapDumpOnOutOfMemoryError`, unified logging: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21 — Recording API, `dump()`, `stop()`, retention: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html
- Oracle JDK 21 — Virtual Threads, `Thread.dump_to_file`: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- Kubernetes — Logging Architecture and `--previous` history: https://kubernetes.io/docs/concepts/cluster-administration/logging/
- Kubernetes — `kubectl logs` reference: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/

**Conclusion:** the most valuable evidence is often **the irreproducible live state of the exact failing JVM**. Collect in the right order within impact limits, back up to durable storage, log every command and measurement side effect, and only then restart when appropriate. A strong report separates **what was observed**, **what the tools altered**, **what lacks evidence**, and **hypotheses left to test**.
