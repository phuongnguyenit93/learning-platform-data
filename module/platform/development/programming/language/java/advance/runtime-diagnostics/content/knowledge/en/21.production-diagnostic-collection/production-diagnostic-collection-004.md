# 21.4 Setting Stop Conditions, Size Caps, and Retention TTLs for Diagnostic Files

## 1. Objective: Bound Collection So It Never Causes a New Incident

In Java/HotSpot operations, each investigation can generate **Java Flight Recorder (JFR) recordings**, GC logs, thread dumps, Native Memory Tracking (NMT) snapshots, heap dumps (`.hprof`), fatal VM logs (`hs_err_pid...log`), core/minidumps, and application diagnostics. Evidence is most valuable when captured at the right moment, yet collecting **for too long, too frequently, or leaving files around indefinitely** can fill disks, raise latency, push containers into OOM, and leak sensitive data.

A complete policy must answer **three separate questions**:

1. **Stop condition:** how long may a diagnostic job run, and what triggers automatic or operator-initiated early termination?
2. **Size budget:** how much active recording data may be kept, how many files may be created, and how much volume/shared storage may they occupy?
3. **Retention/TTL:** how long are finalized diagnostic files kept locally and remotely, and what conditions permit deletion?

**Core distinction:** `JFR maxage=2h` does **not** delete exported `.jfr` files after two hours. `JFR maxsize=256m` does **not** turn the entire diagnostics directory into a 256 MB hard quota. `-XX:+HeapDumpOnOutOfMemoryError` does **not** auto-rotate or delete `.hprof` files. Each layer needs its own policy and operational mechanism.

Examples use JDK 17+ on HotSpot/OpenJDK. Verify exact syntax, attach permissions, filesystems, and target JDK/vendor behavior before applying to production.

## 2. Artifact Lifecycle: Never Confuse Active Data With Finalized Files

| State | Examples | Required Limits |
| --- | --- | --- |
| **COLLECTING** | Active JFR recording; scheduler invoking `jcmd` periodically | Duration, iteration count, cadence, overhead, stop/cancel commands |
| **STAGING/WRITING** | JFR repository chunks; heap dump mid-write; `.part` upload | Free space, quotas, never delete open files |
| **FINALIZED** | Completed `.jfr` dump; thread dump text; complete `.hprof` | Integrity check, checksum, permissions, filename, timestamp |
| **ARCHIVED** | File uploaded and checksum-verified | Secure vault, expiry, legal hold, access audit |
| **EXPIRED/DELETED** | File eligible for cleanup after TTL | Allowlist-scoped deletion, audit trail, never delete active artifacts |

Three distinct timestamps exist: **collection start**, **recording/dump completion**, and **file expiration**. Stopping a recording does not delete its files. Conversely, deleting an open repository file does not cleanly stop the recording.

Maintain **metadata/manifests** per artifact: `artifact_id`, `service`, `instance`, `PID`, `incident_id`, `type`, `state`, `started_at_utc`, `finalized_at_utc`, `size_bytes`, `sha256`, `archive_location`, `expiry_at_utc`, `legal_hold`, and `owner`. Without a manifest, relying solely on file extensions or `mtime` easily leads to deleting the wrong file.

## 3. Matrix of Built-In Mechanisms by File Type

| Artifact | What Stops Collection? | What Bounds Data Size? | Exported File TTL |
| --- | --- | --- | --- |
| **JFR** | `duration`, `JFR.stop`, `Recording.stop()` | `disk=true,maxage,maxsize` manage the **repository**; `JFR.dump maxage/maxsize` filter the dump | **Not built-in**; must be managed outside the JVM |
| **GC/unified logs** | JVM shutdown or runtime `jcmd VM.log` | `-Xlog:...:filecount=N,filesize=...` rotates by size | Size/count rotation only, not time-based TTL |
| **Thread dumps** | Each `jcmd Thread.print` finishes; scheduler hits sample cap | Max sample count, command timeout, collector output quota | Text cleanup via external job |
| **NMT snapshots** | `jcmd VM.native_memory` finishes; collector stops polling | Sample count, cadence, output byte cap | Cleanup outside the JVM |
| **Heap dumps** | Dump command completes or OOME trigger fires | Pre-capture space/quota/admission checks; **no built-in rotation** | Separate cleanup/archival TTL |
| **`hs_err_pid`** | HotSpot fatal reporter | Output path and filesystem quota; no `filecount`/`filesize` | Separate TTL |
| **OS core/minidumps** | OS/runtime crash handling | OS core policies/`systemd-coredump`/quotas | OS/central archive policy |
| **Application logs** | Logging framework/agent | Logback/Log4j/collector rotation | Separate retention rules |

Enforce a **global budget** when multiple JVMs or pods share a volume: 20 JVMs each capped at a 256 MB recording still consume gigabytes of repository space **before counting dumps, logs, or cores**.

## 4. Understanding `duration`, `maxage`, and `maxsize` in JFR

Key parameters:

- **`duration=120s`**: the recording is allowed to run for **up to roughly 120 seconds** from start and stops automatically upon reaching duration. Can be stopped earlier via `JFR.stop`.
- **`maxage=2h`**: retains recent enough chunks in the **JFR disk repository**. Aged-out chunks are evicted by the runtime. If `maxsize` is hit first, retention may be **less than** two hours.
- **`maxsize=256m`**: cap on data **retained in the recording's repository**; chunk-based eviction is not byte-exact.
- **`disk=true`**: flushes/retains data in the JFR disk repository; `maxage`/`maxsize` govern this mode.
- **`filename=...`**: destination file written when the recording stops/completes per config, **not the path of every repository chunk**.
- **`dumponexit=true`**: requests writing the recording when the JVM shuts down gracefully; **not guaranteed** on `SIGKILL`, kernel OOM kill, or host crash.

| Misconception | Reality |
| --- | --- |
| "`maxage=2h` deletes files after 2 hours" | False: it bounds **data age in the repository**, not exported `.jfr` file lifetimes. |
| "`maxsize=256m` caps the whole volume at 256 MB" | False: excludes other recordings, dump files, logs, staging, and metadata. |
| "`duration=2m` means the file lives only 2 minutes" | False: the recording stops after 2 minutes, while the exported file can linger for years without cleanup. |
| "`JFR.dump` stops collection" | False: it writes a snapshot while the recording keeps running. |
| "`disk=false` with `maxage/maxsize` creates rolling disk history" | Misaligned with intent: data stays bounded by memory buffers rather than the disk repository described above. |
| "`maxsize=0` means retain zero bytes" | For this option, 0 typically means **unlimited**. |

**Never set `maxsize` smaller than JFR's configured `maxchunksize`**, as `JFR.start` enforces constraints accordingly. Run `jcmd <PID> help JFR.start`/`JFR.configure` to verify exact rules on the target JDK.

## 5. Recipe A: JFR Capture With Automatic Stop Duration

### Enabling at JVM Startup

```bash
java -XX:StartFlightRecording=name=boot,settings=profile,disk=true,duration=120s,maxage=120s,maxsize=128m,filename=/var/diag/jfr/boot-%p-%t.jfr -jar application.jar
```

Key-value pairs in the **startup flag** are separated by **commas**, and JVM options must precede **`-jar`**. In this example, `profile` should only be used for a targeted diagnostic window because it consumes more CPU, disk I/O, and memory than `default`. The output directory must exist on the **target JVM's** filesystem with write permissions.

After roughly 120 seconds, the recording stops and writes the output file. `duration` bounds the impact of a single capture, yet the resulting file still needs an external TTL. If the JVM dies abruptly, there is no guarantee the destination file will be complete.

### Capturing on a Running JVM Without Restart

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> help JFR.start
jcmd <PID> JFR.start name=incident settings=profile disk=true duration=120s maxage=120s maxsize=128m filename=/var/diag/jfr/incident-%p-%t.jfr
jcmd <PID> JFR.check name=incident
```

Unlike the startup flag, **`JFR.start` options via `jcmd` are space-separated**. `<PID>` is a placeholder—substitute the actual PID; the tool requires attach permissions and matching PID namespace.

If the incident ends early, actively finalize the data:

```bash
jcmd <PID> JFR.dump name=incident filename=/var/diag/jfr/incident-snapshot-%p-%t.jfr
jcmd <PID> JFR.stop name=incident filename=/var/diag/jfr/incident-final-%p-%t.jfr
```

`JFR.dump` exports a snapshot **without stopping** the recording. `JFR.stop` stops the named recording; always specify `name` to avoid stopping a background recording by mistake. If the recording already auto-stopped due to `duration`, inspect the file and recording state before issuing another `stop`.

## 6. Recipe B: Continuous JFR Retaining Only Recent History

Rare incidents can start and finish before an operator ever runs `profile`. A common pattern is a **continuous recording** with explicit bounds:

```bash
java -XX:StartFlightRecording=name=ring,settings=default,disk=true,maxage=2h,maxsize=256m -jar application.jar
```

Omitting `duration` keeps the recording active until explicitly stopped or the JVM exits. This configuration attempts to keep **at most two hours and up to the chosen repository cap**; if high JFR throughput hits 256 MB early, older chunks are evicted before two hours elapse.

When an alert fires, dump the target window:

```bash
jcmd <PID> JFR.check name=ring
jcmd <PID> JFR.dump name=ring maxage=15m maxsize=64m filename=/var/diag/jfr/ring-%p-%t.jfr
```

In **`JFR.dump`**, `maxage`/`maxsize` filter **the slice exported by that dump**; they do not alter the underlying recording's retention policy. After dumping, `ring` keeps recording. Size limits are chunk-based, not byte-exact guarantees on the output file. Run `jfr summary` and check actual file size after dumping.

**Hidden trap:** dumping a new file every 10 minutes produces **144 files per day**. `ring maxsize=256m` does not delete the 143 older dumps. Therefore, you need separate policies for **dump count, total exported bytes, and TTL**.

If you need to stop `ring`:

```bash
jcmd <PID> JFR.stop name=ring filename=/var/diag/jfr/ring-final-%p-%t.jfr
```

Collection can only resume by starting a new recording or reconfiguring; never assume `JFR.dump` stopped any recording.

## 7. Stop Conditions Must Have Multiple Priority Tiers

Do not rely solely on `duration` expiring. In a diagnostic campaign, define prioritized triggers:

| Trigger | **Illustrative** Example (Not a JVM Default) | Outcome |
| --- | --- | --- |
| **Max duration** | Profile JFR capped at 120 seconds | Stop and export at time limit |
| **Sufficient evidence** | 3 slow traces, 5 thread dumps, 1 valid JFR collected | Halt additional collection |
| **Incident recovered** | p99 normal for 5 consecutive minutes | Stop on-demand recording; keep ring if designed |
| **Max iterations** | 5 thread dumps; 3 NMT samples | Issue no further captures |
| **Collector timeout** | A `jcmd` call hangs beyond 15 seconds | Mark attempt failed/partial; never treat partial output as complete |
| **Overhead limit** | Collection worsens CPU, disk I/O, or latency | Reduce sampling or abort supplemental capture |
| **Disk high-watermark** | Diagnostics volume hits 80% | Reject large new artifacts; prioritize safety |
| **Incident budget** | Combined finalized + staging nears 2 GiB | Deny new captures or archive first |
| **Security/policy** | File contains prohibited data or enters legal hold | Isolate/handle per policy; block publication |
| **Lifecycle** | JVM restart, pod replacement, deploy completion | Seal metadata, preserve completed artifacts |

Thresholds like **120s, 5 iterations, 80%, 2 GiB** are illustrative only; size them to match load, quotas, evidence needs, and incident response requirements.

**Priority rule:** service and data safety > minimum trustworthy evidence > expanded capture. If a volume runs low on space, never attempt a multi-GiB heap dump by recklessly deleting files the application is using.

## 8. Size-Bounded GC/Unified Log Rotation

HotSpot JDK 9+ provides Unified Logging. Example limiting file sizes and rotated file count:

```bash
java -Xlog:gc*:file=/var/diag/gc/gc-%p.log:time,uptime,level,tags:filecount=5,filesize=10M -jar application.jar
```

- `gc*` logs GC events matching the JVM's tag selector.
- `file=...gc-%p.log` embeds the PID to separate instances.
- `filecount=5` caps the number of rotated log files.
- `filesize=10M` is a **target rotation size**, not a byte-exact hard limit.
- Upon rotation, older data is overwritten. This is **size/count retention**, not a guaranteed 7-day history.

**Warning:** on HotSpot, `filecount=0` means **no rotation** rather than "keep zero files," allowing logs to grow without bound. On each target JDK, check:

```bash
java -Xlog:help
```

`jcmd <PID> VM.log` on supporting versions can adjust active logging; verify `help VM.log` and avoid mutating logging during an incident without recording the prior configuration.

**Do not expect `-Xlog` to manage Logback/Log4j2 application logs.** Frameworks and log shippers have their own rotation, TTLs, and quotas; your policy must cover them if they share a volume.

## 9. Heap Dumps: No Built-In Rotation for `.hprof` Files

Enable dump on OOME:

```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/diag/heap -jar application.jar
```

`-XX:HeapDumpPath` specifies only the output target. It **does not** enforce total capacity, file count, age limits, or auto-deletion. A large heap dump can create severe disk/I/O pressure, and container/kernel OOM kills may leave the JVM **no time to write the file**.

Proactive capture while the JVM is alive (only after impact assessment):

```bash
jcmd <PID> GC.heap_dump /var/diag/heap/manual-investigation.hprof
```

Heap dumping is a **heavy** operation that triggers safepoints/pauses and produces huge files often containing secrets, object payloads, or user data. Never capture them continuously in production merely to "have extra data."

Three guardrails are required **outside** `HeapDumpPath`:

1. **Admission:** allow only for valid incidents with authorization, sufficient space, and clear snapshot justification.
2. **Concurrency:** cap simultaneous heap/core dumps on the same pod/host/volume; enforce cooldowns.
3. **Retention:** delete local copies only after completion, verified upload, and confirmation of no legal hold.

**Never abort an in-progress dump and treat the partial `.hprof` as valid.** If a collector times out or the process dies mid-write, mark the artifact `INCOMPLETE`. Validate with proper analysis tooling before citing it as evidence.

`-Xmx` caps the Java heap; it **does not** mean the dump file matches `-Xmx` byte-for-byte, nor does it represent total RSS or the container memory budget.

## 10. Fatal Error Logs, OS Core Dumps, and Post-Crash Evidence

When HotSpot hits a fatal error, it may emit `hs_err_pid...log`. Set the path via:

```bash
java -XX:ErrorFile=/var/diag/crash/hs_err_pid%p.log -jar application.jar
```

`ErrorFile` has no `filecount`/`filesize` like Unified Logging; cleaning old crash files requires a separate policy. Even when configured, the reporter may fail to write on full disks, permission errors, or forced kills.

Native core/minidumps can be **far larger** than other diagnostic files and contain sensitive memory contents. Storage location, size, and retention depend on OS/environment controls such as `ulimit -c`, `core_pattern`, `systemd-coredump`, WER, container policies, and filesystem quotas. **Never** rely on JFR parameters to bound OS core dumps.

A container exit code of `137` typically corresponds to `SIGKILL`, yet **does not prove `OOMKilled` by itself**; verify orchestrator and kernel evidence. During kernel kills, `dumponexit=true`, `finally` blocks, and JVM shutdown hooks **are not guaranteed**; rely on continuous recordings and early exports while the process is healthy enough.

For fatal artifacts, assign owners, encryption, access controls, TTLs, and legal-hold checks per incident workflow. Never store core dumps indefinitely on volumes holding live application data.

## 11. Thread Dumps, NMT Snapshots, and Polling Scripts: Cap Iterations, Never Loop Forever

A thread dump is generated with:

```bash
jcmd <PID> Thread.print -l
```

An NMT snapshot (useful only if Native Memory Tracking was enabled at JVM startup):

```bash
jcmd <PID> VM.native_memory summary scale=MB
```

These commands typically **exit on their own** once output is returned; the risk lies in schedulers or scripts invoking them **how many times** and how outputs are stored. Illustrative limits: 5 thread dumps spaced 2 seconds apart, 3 NMT snapshots spaced 30 seconds apart, 15-second per-command timeout, and at most 1 active collector job per JVM. Actual bounds must be tuned to the workload.

Each sample needs a fresh filename, UTC timestamp, PID, and sequence number. **Never append the same command repeatedly into an unbounded file**, and never treat a timed-out command's partial output as complete.

Linux example for **a single** sample (substitute real PID and verify permissions):

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
jcmd <PID> Thread.print -l > "/var/diag/threads/thread-$STAMP.txt"
```

This snippet takes one snapshot only; it does not implement timeouts or loops. A production collector must capture exit codes, confirm write completion, and only then transition state to `FINALIZED`. For NMT `summary.diff`, record the `baseline` and timestamps; never treat positive deltas as leaks without workload correlation.

## 12. Size Total Quota Before Choosing `maxsize`

Illustrative partitioning of a **10 GiB** diagnostics volume:

| Item | **Illustrative** Allocation |
| --- | ---: |
| Total volume capacity | 10 GiB |
| Safety headroom withheld from diagnostics | 3 GiB |
| Usable diagnostic budget | 7 GiB |
| JFR repository and dumped files | 1 GiB |
| GC logs + thread/NMT text logs | 0.5 GiB |
| One approved heap/core dump | 4 GiB |
| Upload staging, metadata, and reserve | 1.5 GiB |

This is a **design budget**, not a limit enforced automatically by the JVM. If an expected heap dump is 8 GiB while only 4 GiB is budgeted, **do not start it** without an alternative volume/artifact plan. Account for multiple pods sharing a volume and concurrent collectors.

Formula:

```text
usable_diag_budget = min(volume_quota,
                         available_bytes - safety_headroom)

peak_storage_demand = active_repositories
                    + active_rotating_logs
                    + concurrent_heap_core_dumps
                    + finalized_local_files
                    + upload_staging
                    + filesystem_overhead
```

Safety bounds **must be enforced** via filesystem/volume quotas, collector admission, high-watermark alerts, and cleanup logic. Writing numbers in a runbook without measuring `free_bytes`/`used_bytes` provides no real protection.

**One GiB = 1,073,741,824 bytes.** Avoid mixing binary GiB with decimal MB in budget tables; JFR `m`/`M` flags and APIs have their own conventions—verify carefully.

## 13. Retention: Managing **Finalized** Files With Metadata and TTLs

Illustrative matrix (not a mandatory legal recommendation):

| Artifact | Local Retention After Finalize/Upload | Remote Archive Retention | Notes |
| --- | --- | --- | --- |
| JFR incident `.jfr` | 7 days | 30 days | Verify `jfr summary`, checksum, encryption |
| Rotated/closed GC logs | 3–7 days | 14–30 days | Never delete active GC log |
| Thread/NMT text | 3 days | 14 days | Sample count already bounded |
| `.hprof` | 24–48 hours after verified upload | Per ticket/policy, e.g., 7–30 days | Contains objects and potentially secrets |
| `hs_err_pid` | 7 days | 30 days if incident open | Retain JDK/vendor/build context |
| Core/minidumps | Only when needed, short local TTL | Per security incident process | Large, sensitive, strict access controls |

**Where does TTL start counting?** Record `finalized_at_utc` or `archived_at_utc` in the manifest and anchor TTL there; `mtime` is a fragile proxy altered by copies, restores, or `touch`. If policy states "delete local 48 hours after upload," check `uploaded_at_utc` specifically—not when the JVM started writing the file.

Two storage tiers require **two distinct policies**:

- **Local staging**: short TTL, preserved headroom, protection for files being written or uploaded.
- **Remote archive**: TTL aligned with investigation duration, encryption, owner, permissions, checksums, audit trails, and legal holds.

Never delete a local file simply because an upload **started**; require proof that the remote store holds the matching object, size, and checksum. While an investigation remains open or a legal hold applies, cleanup policies must protect artifacts even past normal TTL.

## 14. Safe Cleanup Workflow Without Accidental Deletion

A cleanup job should proceed in order:

1. **Scope:** restrict to a dedicated, authorized diagnostics directory; enforce type/prefix allowlists; never follow symlinks outside scope.
2. **Inventory:** read manifest, file type, owner, UTC timestamps, state, size, checksum, incident ID, and hold status.
3. **State check:** skip `COLLECTING`, `WRITING`, `UPLOADING`, files whose size is still changing, and open repository or GC log files.
4. **Archive check:** verify remote object existence, size/checksum match, and applied access policies; if unverified, retain locally and raise an error.
5. **Expiry check:** compare TTL, confirm incident closed and no legal hold active; never rely solely on filename or `mtime`.
6. **Quota policy:** when disk nears capacity, throttle new artifact creation first; delete only **eligible artifacts** rather than deleting blindly.
7. **Dry-run:** print candidate filenames, sizes, ages, and deletion reasons; require policy-compliant review.
8. **Delete:** remove only allowlisted, verified files, never symlink targets or actively written files; record an audit trail.
9. **Verify:** re-measure disk used/free, reconcile manifest/remote archive, and alert on undeletable files.

Avoid commands like `rm -rf /var/diag/*` or deleting all `*.hprof` files in operations. Such commands ignore open incidents, active writes, archive state, and legal holds.

### Linux Dry-Run: List Only, Do Not Delete

Example finding `incident-*.jfr` files with **mtime** older than roughly 7 days in a dedicated directory:

```bash
find /var/diag/jfr -maxdepth 1 -type f -name 'incident-*.jfr' \
  -mmin +10080 -print
```

This command only produces a **candidate list**. `mtime` does not equal `finalized_at_utc`; **never** switch blindly to `-delete` without checking manifests, archive status, and legal holds.

### Windows PowerShell Dry-Run: List Only

```powershell
$cutoff = (Get-Date).ToUniversalTime().AddDays(-7)
Get-ChildItem -LiteralPath 'D:\diag\jfr' -File -Filter 'incident-*.jfr' |
  Where-Object { $_.LastWriteTimeUtc -lt $cutoff } |
  Select-Object FullName, Length, LastWriteTimeUtc
```

This read-only query also cannot tell if a file is in use or under legal hold; it merely assists inventory before cleanup policy decides.

## 15. Java 17+: `Recording` Demo Bounding Duration, Age, Size, and Early Stop

The JDK provides `jdk.jfr.Recording` to manage recordings from Java code. Below is a **standalone** program: it enables a custom JFR event, bounds max runtime, repository age, and repository size, then stops early and exports the file. It does **not** configure post-export TTL deletion.

Save as **`BoundedJfrDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public class BoundedJfrDemo {
    @Name("demo.diagnostics.Marker")
    @Label("Diagnostic Marker")
    public static final class Marker extends Event {
        @Label("Sequence")
        public int sequence;
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("bounded-demo.jfr").toAbsolutePath();

        // Do not overwrite an existing diagnostic file.
        if (Files.exists(output)) {
            throw new IllegalStateException(
                    "Output exists; run in a clean working directory");
        }

        try (Recording recording = new Recording()) {
            recording.setName("bounded-demo");
            recording.setToDisk(true);
            recording.setDuration(Duration.ofSeconds(5));
            recording.setMaxAge(Duration.ofMinutes(1));
            recording.setMaxSize(64L * 1024 * 1024);
            recording.setDestination(output);
            recording.enable(Marker.class).withThreshold(Duration.ZERO);

            recording.start();
            Marker event = new Marker();
            event.sequence = 1;
            event.commit();

            // Assume enough evidence is captured: stop before the 5-second limit.
            // setDestination(...) writes the file when stop succeeds.
            recording.stop();
        }

        System.out.println(
                "recording_saved=" + Files.isRegularFile(output));
        System.out.println("stop_reason=manual");
    }
}
```

Run on JDK 17+ with JFR, inside a writable directory containing no existing `bounded-demo.jfr`:

```bash
javac --release 17 BoundedJfrDemo.java
java BoundedJfrDemo
jfr summary bounded-demo.jfr
```

**Stdout of the Java program alone**, assuming successful execution:

```text
recording_saved=true
stop_reason=manual
```

`jfr summary` produces its own event/file summary, varying by JDK. The program sets `setDuration(5s)` as the maximum duration **if not stopped early**, yet calls `stop()` sooner once the sample is captured. `setMaxAge(1m)`/`setMaxSize(64 MiB)` govern **repository** retention; this brief demo will not hit those limits. The output file **does not vanish after one minute**; TTL deletion still belongs to the collector/storage layer.

`Recording.setMaxSize(long)` accepts raw **bytes**, not a string like `"64m"` as in the CLI. `setMaxAge(Duration)` and `setDuration(Duration)` accept `Duration` objects. To export while still running, call `recording.dump(Path)`; stopping early with `stop()` when a destination is configured writes the output and transitions the recording state accordingly. Once stopped, a recording **cannot be restarted** on the same `Recording` instance.

## 16. Diagnostic Files in Docker/Kubernetes: Where to Store and Clean Up?

In containers, `/var/diag` resides on the filesystem **visible to the JVM process**. Using ephemeral container storage risks losing files when a pod is deleted or redeployed. For artifacts needed for post-crash analysis:

- Use a **dedicated volume/PVC or exporter** with defined size and retention; never share volumes holding critical databases or application data paths.
- Check permissions: the JVM must write `.jfr`, `.hprof`, and GC logs; the collector/archiver reads with least privilege.
- Include pod/container instance ID, hostname, PID, release, and UTC timestamp in filenames/manifests to prevent collisions across restarts.
- Remember `JFR.dump`/`GC.heap_dump` write on the **JVM/container filesystem**, not necessarily on the machine invoking `jcmd`.
- Check cgroup memory, ephemeral disk quotas, pod eviction rules, and runtime restart policies. A heap dump can breach quotas even when `-Xmx` looks modest.
- Archive to encrypted object storage with checksums; if upload fails, **never** delete locally and **never** mark the incident saved.
- When JFR/GC logs run continuously, calculate total cost across all pods rather than multiplying one recording's limit for a single service.

Do not keep raising `maxage` or `maxsize` reactively during incidents when quotas/hard limits are missing; coordinate **CPU overhead, storage, and SLAs**.

## 17. Illustrative Campaign Policy (Not a JVM Config File)

```yaml
diagnostics:
  incident_id: checkout-p99
  owner: oncall-platform

  jfr:
    settings: profile
    max_duration: 120s
    repository_max_age: 120s
    repository_max_size: 128MiB

  collection:
    max_concurrent_jobs_per_jvm: 1
    max_thread_dump_samples: 5
    max_nmt_samples: 3
    command_timeout: 15s

  storage:
    dedicated_path: /var/diag
    local_budget: 2GiB
    safety_headroom: 1GiB
    high_watermark: 80_percent
    verify_archive_checksum: true

  retention:
    jfr_local_ttl_after_finalization: 7d
    heap_local_ttl_after_verified_archive: 48h
    protect_active_files: true
    protect_open_incidents: true
    protect_legal_holds: true
    dry_run_cleanup: true

  stop_conditions:
    - max_duration_reached
    - enough_evidence_collected
    - incident_resolved_after_cooldown
    - disk_or_overhead_guardrail
```

This YAML is a **policy model for collector builders**, not syntax read directly by `java` or `jcmd`. If your stack uses Prometheus/Alertmanager, Kubernetes jobs, agents, or an orchestration service, implement the mapping from this policy to JVM commands, volume quotas, upload/retention jobs, and alerts. Never stop at writing YAML without components that **actually enforce the limits**.

## 18. Real-World Scenario: Before, During, and After an Incident

### Before the Incident

A service experiences unpredictable p99 spikes. Enable a JFR ring `settings=default,disk=true,maxage=2h,maxsize=256m`; configure rotated GC logs without writing to critical data filesystems. For OOME, consider a heap dump trigger on a sufficiently sized volume while accounting for cost.

### When the Incident Starts

The collector confirms pod/PID, incident type, latency/CPU/disk headroom, and active job counts. If deeper profiling is needed, run `JFR.start name=incident settings=profile duration=120s...`, capping at one heavy campaign at a time. Set stop triggers if the incident resolves, quotas climb, or overhead spikes. Capture only the agreed max counts of thread/NMT samples.

### When Stopping

Use `JFR.dump` for a snapshot before stopping an on-demand recording, or let `duration` finish and verify the exported file. **Do not stop the background ring** unless policy dictates. Mark an `.hprof` file complete only after the JVM/tool reports success and artifact checks pass; never delete files mid-write.

### After the Incident

Write the manifest + SHA-256, verify `jfr summary` and event types, upload securely, and verify the remote object and checksum. Mark local files eligible for cleanup only when finalized, past TTL, free of legal holds, and verified in archive. Re-measure disk usage post-cleanup and retain an audit trail.

### Reviewing Policy

If alerts typically arrive more than two hours late, `ring maxage=2h` is too short. If `maxsize` is hit before two hours, increasing `maxage` alone will not help—lower event volume or recalculate the disk budget. If `profile` pushes p99 higher, trim event settings or duration. If disk lacks space for a heap dump, adjust storage or collection strategy rather than **forcing a write and causing a system-wide disk-full outage**.

## 19. Common Mistakes to Avoid

| Misconception | Why It Is Wrong | Fix With |
| --- | --- | --- |
| "`duration=2m` auto-deletes the file after two minutes" | Stops the recording only, no file TTL | Separate retention job |
| "`maxage=2h` deletes all 2-hour-old `.jfr` files" | Governs JFR repository data only | Manifest + TTL |
| "`maxsize=256m` guarantees the whole volume stays under 256 MB" | Dumps/logs/other recordings sit outside that cap | Volume quota / global budget |
| "`JFR.dump` also stops the recording" | Collection can continue after dumping | `JFR.stop name=...` to stop |
| "`JFR.dump maxsize=64m` produces an exact 64 MB file" | Chunking, metadata, and granularity apply | Check actual file size and quota |
| "`filecount=0` keeps zero log files" | Disables rotation, letting logs grow | Positive `filecount` and sensible `filesize` |
| "GC log rotation preserves exactly 7 days" | Rotates by size/count, not TTL | Time-based archive/retention |
| "`HeapDumpPath` caps dump size" | Sets output path only | Pre-capture quota/headroom check |
| "`OOMKilled` always leaves a heap dump" | Kernel may kill before JVM dumps | OS/cgroup events and monitoring |
| "Delete open JFR repository files to free disk" | Corrupts active recording/writes | Stop/rotate and clean only finalized artifacts |
| "`mtime` equals finalized time" | Copies, `touch`, or restores alter `mtime` | Manifest UTC timestamp |
| "Once upload starts, local copy can be deleted" | Upload may fail or mismatch | Verify remote checksum before delete |
| "Delete all old files regardless of tickets" | May violate legal holds or open incidents | Scope/hold/owner checks and audit |
| "Per-JVM quota is enough for the cluster" | Concurrent pods multiply total usage | Global budget and concurrency caps |
| "Keep core/heap dumps forever just in case" | Increases data exposure and cost | TTL, encryption, access controls |
| "`SIGKILL` always runs shutdown hooks / `dumponexit`" | No chance for Java cleanup | Proactive dump before kill |

## 20. Pre-Start and Wrap-Up Checklist

- [ ] Objective, PID/JDK build, owner, and incident ID identified.
- [ ] `max_duration`, early stop triggers, and confirmation that the recording stopped are in place.
- [ ] **Size budget** covers repository, exported dumps, logs, staging, and OS cores—not just one JFR `maxsize`.
- [ ] For JFR, `duration`, `maxage`, `maxsize`, `disk`, `filename`, and `dumponexit` are properly distinguished.
- [ ] `settings=default` chosen for continuous vs. short `profile` for targeted needs, with measured overhead.
- [ ] GC/unified logs have `filecount`/`filesize`; app logs have separate rotation.
- [ ] `.hprof`/core dumps have safety headroom, quotas, concurrency caps, and approval flow.
- [ ] Thread/NMT collectors have max sample counts, intervals, timeouts, and bounded output.
- [ ] Dedicated diagnostics directory, permissions, and exact path verified inside target container/JVM.
- [ ] Finalized files carry metadata: state, UTC timestamps, size, checksum, owner, and incident.
- [ ] Archives encrypted and checksum-verified; local files never deleted merely because upload started.
- [ ] TTL applied to **finalized/archived files**, respecting legal holds and open-incident protections.
- [ ] Cleanup uses dry-run, allowlists, no out-of-scope symlinks, audit logging, and post-cleanup disk checks.
- [ ] Alerts tested for disk pressure, collector failures, partial artifacts, and overdue files.
- [ ] End-to-end flow rehearsed: start → dump/stop → verify → archive → retention → cleanup.

## 21. Official Documentation

1. Oracle JDK 21 `jcmd` manual — `JFR.start`, `JFR.dump`, `JFR.stop`, and duration/maxage/maxsize parameters: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
2. Java SE 21 `Recording` API — `setDuration`, `setMaxAge`, `setMaxSize`, `setToDisk`, `setDestination`, and `stop`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html
3. Oracle JDK 26 `java` manual — `-XX:StartFlightRecording`, Unified Logging `-Xlog`, `filecount/filesize`, and `ErrorFile`: https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html
4. Oracle JDK 21 `java` manual — Unified Logging syntax on JDK 21: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
5. Oracle Java 21 *Prepare Java for Troubleshooting* — continuous JFR, core/heap dumps, GC logs, and operational cost: https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html
6. Oracle Java 21 *Diagnostic Tools* — `jcmd`, heap dumps, and postmortem artifacts: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
7. Java SE 21 `java.nio.file.Files` — file inspection and metadata API for collectors: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html

**Conclusion:** enforce **when to stop**, **how much active data is retained**, and **when finalized files expire** at three separate layers. JFR options, GC log rotation, and JVM dump flags solve only **part** of the problem; quotas, manifests, archiving, checksums, TTLs, and safe cleanup are what make the entire diagnostic campaign safe, repeatable, and free of self-inflicted disk or security incidents.
