# 14.9. Evaluating Recording Overhead, Disk Usage, and Access Permissions for `.jfr` Files

## 1. The Problem to Solve

**Java Flight Recorder (JFR)** lets you observe JVM behavior through events such as GC activity, allocations, threads, I/O, and execution samples. A `.jfr` recording can be invaluable when tracking down abnormal latency or CPU usage; however, enabling recording also consumes resources, uses buffers, generates I/O, and may store internal application details.

Therefore, before enabling JFR on a user-facing JVM, you must answer **three independent questions**:

1. **Recording overhead:** with the current event config and load, how much does JFR affect CPU, throughput, latency, pauses, memory, and I/O?
2. **Capacity:** where does the recording repository live, how fast does data grow over time, what do `maxage`/`maxsize` protect, and does exporting `.jfr` require extra free space?
3. **Access permissions:** who is allowed to issue recording commands, which process actually creates the file, who can read the events, and how are files transferred, retained, and deleted?

**Goal:** know how to pick `default` or `profile` for the task, estimate a resource budget from grounded measurements, run a bounded recording session, verify permissions and file readability, and make a deployable decision. This lesson covers operating and governing a recording; detailed analysis of JFR event contents is covered in other lessons.

Command examples below use **HotSpot/OpenJDK 21** as the reference baseline. Options may vary on other JVMs/JDKs; always check `jcmd <pid> help JFR.start` and `JFR.dump` on the target JVM.

## 2. Data Model: Buffers, Repository, and `.jfr` Files Are Three Separate Layers

JFR is built into the JVM: events are collected in buffers, then optionally written as **chunks** into a recording repository, and exported as a `.jfr` file readable by JDK Mission Control (JMC) or the `jfr` tool.

~~~text
Application / HotSpot
   │  emits events (name, time, fields, stack trace if enabled)
   ▼
JFR buffers in JVM / native memory
   │
   ├─ disk=true ──> repository holding recording chunks
   │                    │  rolling data; subject to maxage/maxsize
   │                    │
   │                    └── JFR.dump / JFR.stop(filename=...)
   │                             ▼
   │                        exported .jfr file
   │                             ▼
   │                    storage, analysis, transfer, deletion
   │
   └─ disk=false ──> relies on data still in buffers;
                       bounded history, no continuous chunk store
~~~

**Three important consequences:**

- **Repository** is where chunks live while the JVM records; by default it is typically under the OS temp directory and can be configured via `JFR.configure repositorypath=...`. Do not assume that because the final export path is `/secure/recordings/x.jfr`, *all* intermediate data stayed in that secured directory.
- **Exported file** is the output of `JFR.dump`, `JFR.stop filename=...`, or dump-on-close mechanisms. It has its own lifecycle. Rotating or evicting rolling data in the repository **does not automatically delete** previously dumped files, copies, or backups elsewhere.
- `JFR.dump` can write a snapshot **while the recording continues**. Distinguish "exporting a file at 12:00" from "stopping recording at 12:00." One session can produce multiple snapshot files; each adds disk usage and data-exposure surface.

`.jfr` is a binary format containing metadata and multiple event types, not a plain-text log file. File size is not simply event count times printed text length; schema metadata, stack traces, constant pools, and chunk structure all contribute to size.

## 3. What Drives JFR Cost?

| Component | Source of Cost | What to Measure? |
| --- | --- | --- |
| Event emission | Capturing fields, timestamps, context, sometimes stack traces | Per-process CPU, throughput, and latency |
| High-volume events | Many events/sec from I/O, object allocations, thread activity, etc. | Event counts by type via `jfr summary`, bytes/sec |
| Buffers and internal work | Native/in-JVM buffers, flushes, metadata, and housekeeping | Resident memory, native memory, GC, and CPU |
| Writing chunks to repository | Storage throughput, IOPS, disk/overlay filesystem pressure | Write bytes/sec, I/O wait, storage quota, free space |
| Dumping files | Reading/finalizing data, serializing/copying to output, possible I/O burst | Dump duration, peak I/O, file size, and free space |
| Special events | Overly detailed events/stack traces, dense sampling, heap statistics, GC-root paths | Capture-time pauses/latency, GC events, throughput |
| File analysis | JMC/`jfr` reading, decoding, and rendering data | RAM/CPU/disk of the **analysis** machine, separate from the recording JVM |

Oracle JDK 21 documentation describes `default.jfc` as a low-overhead config suitable for continuous recording and typically under roughly 1% for appropriate workloads; `profile.jfc` records more data and can consume more resources. **Typical figures are not guarantees for every application.** Latency-sensitive endpoints, heavy I/O workloads, or custom configs can differ markedly.

### 3.1. Why Do Event Changes Raise Overhead?

- **Enabling more events:** adds work and data volume, especially per-operation events rather than periodic ones.
- **Lowering `threshold`:** short-duration events previously skipped begin to be recorded, increasing event volume.
- **Increasing sampling frequency (`period`):** gathers more samples and collection work; balance resolution against cost.
- **Enabling stack traces or raising `stackdepth`:** captures more call-stack data, increasing collection cost and file size; value depends on the investigation goal.
- **Enabling `HeapStatistics` or collecting paths to GC roots:** can trigger heavy work affecting pauses. On JDK 21, the diagnostic command option is written `path-to-gc-root` (singular); verify with `help` on the running JVM. Never leave it on permanently just to "collect everything."
- **Running multiple concurrent recordings:** effective event settings and retention/dumping depend on JVM-wide state. Measure **total** cost and storage budget for the whole process rather than naively multiplying one recording's cost.

**Do not infer CPU overhead from `.jfr` file size alone.** An event with a stack trace costs more than a simple-field event; a workload with a tiny file can still suffer pauses from heavy diagnostic options. Conversely, a fairly large file does not by itself prove JFR slowed down the application.

### 3.2. Picking the Right Configuration for the Problem

| Purpose | Initial Configuration | Operational Controls |
| --- | --- | --- |
| Continuous recording to keep history when incidents strike | `settings=default` | `disk=true`, `maxage` and `maxsize` caps, free-space monitoring |
| Temporary deep dive into CPU, allocations, or I/O | `settings=profile` | Short `duration`, off-peak if possible, check overhead and event volume |
| Investigating a specific event category | Copy of `.jfc` with tuned events/thresholds | Verify filters, test in staging; never edit the original `default.jfc` |
| Investigating suspected severe memory leaks | Allocation/heap events and GC-root paths only when truly needed | Accept potentially heavy work; set strict windows and stop criteria |

For JFR started automatically at JVM launch, use `-XX:StartFlightRecording=...`; for an already-running JVM, use `jcmd` to start and inspect live. Both approaches ultimately face the exact same cost, disk, and permission questions.

## 4. Bounded Practice Session with `jcmd`

Suppose a running HotSpot process has PID `21891`, and `/srv/app/jfr/` has been created with proper permissions and free space. **The PID and path are examples, not values taken from your machine.**

### 4.1. Verify the Actual JVM and Parameters

~~~bash
jcmd 21891 VM.version
jcmd 21891 help JFR.start
jcmd 21891 help JFR.dump
jcmd 21891 JFR.configure
~~~

If any command returns an attach/permission error or cannot find the diagnostic command, stop at that check. Never assume non-HotSpot JVMs or different JDK versions have identical parameters.

### 4.2. Continuous Rolling-Window Recording

~~~bash
jcmd 21891 JFR.start name=diag-rolling settings=default disk=true maxage=30m maxsize=256m
jcmd 21891 JFR.check name=diag-rolling
~~~

- `name` identifies the recording when multiple recordings exist.
- `settings=default` picks a lower-overhead event set than `profile`.
- `disk=true` enables writing chunks to the repository.
- `maxage=30m` keeps rolling data within the target age window; `maxsize=256m` sets a nominal cap on retained disk data for this recording. **Whichever limit is reached first evicts older data**, so a dump may contain less than 30 minutes when event rates are high.
- On JDK 21, `maxsize` must be no smaller than JFR's configured `maxchunksize`. Chunk/flush mechanics mean you should not treat 256 MiB as a hard quota for the entire filesystem.

**Setting a dedicated repository:** if chunks must sit on a controlled partition, run `JFR.configure repositorypath=/srv/app/jfr/repository` before starting recordings and verify the JVM-side path and permissions. Some JFR parameters can only be changed before JFR initializes; check `help` and VM state. Never move a repository mid-recording by manually relocating active chunks.

### 4.3. Export a Snapshot and Stop in a Controlled Manner

~~~bash
# File is written by the target JVM; path is resolved in that JVM's filesystem
jcmd 21891 JFR.dump name=diag-rolling filename=/srv/app/jfr/diag-rolling.jfr

# Verify the recording is still running after the dump
jcmd 21891 JFR.check name=diag-rolling

# Stop when collection is no longer needed
jcmd 21891 JFR.stop name=diag-rolling

# Inspect the exported file with the JDK's bundled tool
jfr summary /srv/app/jfr/diag-rolling.jfr
~~~

`JFR.dump` does not imply `stop`. In this example, `dump` created the file before `stop` was called. `JFR.stop` **without `filename`** does not export a final file; if you have not dumped yet and want to keep data, specify `filename` on `stop`.

A bounded profiling session can be started directly like this:

~~~bash
jcmd 21891 JFR.start name=diag-profile settings=profile duration=2m disk=true filename=/srv/app/jfr/profile-2m.jfr
~~~

Setting `duration=2m` performs a timed capture; `filename` is used when the recording ends. On a JVM crash or sudden kill, do not assume the file is complete or all events were flushed.

### 4.4. Differences Between `maxage`/`maxsize` at Start vs. Dump

| Parameter | `JFR.start` with `disk=true` | `JFR.dump` |
| --- | --- | --- |
| `maxage` | Limits history **retained in the recording** | Selects the history window to **export** if data remains |
| `maxsize` | Nominal size cap for data **retained** | Size cap for data included in the **export** |
| `filename` | Final target when recording stops (if configured) | Snapshot output path **when the command runs** |
| `duration` | Collection time before the recording auto-stops | Does not have the same meaning |
| `disk=false` | Does not retain chunk history on disk like `disk=true` | Cannot be used for long-term history retention |

**Avoid this misconception:** `maxage=30m` does not schedule deletion of an already-exported `diag-rolling.jfr` file, and `maxsize=256m` does not cap the cumulative size of all `JFR.dump` copies or backups. If a cron job dumps every 5 minutes, you must manage file count, retention duration, and quotas **separately**.

## 5. Measuring Overhead via Controlled A/B Testing

A percentage cited in documentation is no substitute for measuring on your real system. Minimum procedure:

1. **Baseline:** run a representative workload with no extra JFR recording across at least several windows to measure natural variance. Record JDK/vendor, GC, CPU quota, heap, and load.
2. **Default:** on the same environment and workload, enable `settings=default` with your target duration/retention and measure the exact same metrics.
3. **Profile or custom:** only when genuinely needed, repeat within a bounded window. Never compare a high-load run against a low-load baseline and blame JFR.
4. **Separate warm-up:** JIT warm-up, caches, and initial GC load can skew results. Use multiple trials with matching steady-state windows; reverse run order if appropriate.
5. **Separate dump timing:** measure **continuous recording** overhead separately from `JFR.dump`/`JFR.stop` bursts; dumps can also be affected by filesystem or network-volume performance.
6. **Validate:** compare medians and key percentiles across runs, recording variance/noise rather than cherry-picking one clean sample.

Recommended metric suite:

| Group | Metrics to Collect | How to Interpret |
| --- | --- | --- |
| Experience | Throughput, p95/p99 latency, error rate | Business metrics decide whether overhead is acceptable |
| CPU | Process CPU time, CPU utilization, throttling | Do not confuse high CPU% from heavier load with JFR cost |
| Memory | Heap used/committed, process RSS, native memory where available | JFR uses buffers and metadata; heap used alone is insufficient |
| GC | Event count, pause distribution, GC time | Distinguish workload/GC shifts from recording impact |
| Storage | Disk write bytes/sec, IOPS, free bytes, quota | Monitor both repository and export paths |
| File | `.jfr` byte size, duration, event counts by type | Used to estimate data rate and spot overly noisy events |
| Dump | Wall-clock duration, peak I/O, error messages | A large dump can cause bursts distinct from background write cost |

### 5.1. Comparison Formulas and Hypothetical Example

For "lower is better" metrics (CPU, latency), relative increase is:

\[
\text{Cost increase (\%)} =
\frac{\text{Value with JFR enabled} - \text{Baseline}}{\text{Baseline}}\times 100
\]

For "higher is better" metrics (throughput), relative reduction is:

\[
\text{Throughput reduction (\%)} =
\frac{\text{Baseline} - \text{Value with JFR enabled}}{\text{Baseline}}\times100
\]

The table below uses **hypothetical numbers to practice the math**, not a JFR benchmark or universal acceptance threshold:

| Metric | No Recording | `default` | `profile` |
| --- | ---: | ---: | ---: |
| Throughput | 1,000 req/s | 990 req/s | 950 req/s |
| Average CPU consumed | 2.00 cores | 2.04 cores | 2.20 cores |
| p99 latency | 100 ms | 105 ms | 120 ms |

Per the table: `default` lowers throughput by **1%**, increases CPU by **2%**, and increases p99 by **5%**. `profile` lowers throughput by **5%**, increases CPU by **10%**, and increases p99 by **20%**. Never use these hypothetical figures to predict every application.

In particular, if CPU is capped by quotas/throttling, a small CPU increase can trigger a large p99 spike. If p99 naturally fluctuates by 20 ms, a 5 ms difference in one trial is inconclusive. Run multiple trials under identical conditions with system-owner stop criteria.

## 6. Estimating Disk Capacity and Retention from Real Data

### 6.1. Measuring Data Generation Rate

For a representative snapshot, record:

- **Total file bytes:** via `stat` or filesystem metadata; state MB vs. MiB clearly.
- **Time span contained in the recording:** derived from actual event/window timestamps; do not assume command runtime if the recording had a delay, rotation, or missing segments.
- **Event counts by type:** `jfr summary file.jfr` identifies which events dominate space and summarizes the file.
- **Rate:** `rate = bytes / seconds` over the observed window. Measure both normal and peak hours; rates can climb with request volume, GC activity, or I/O.

Initial linear estimation formula:

\[
B_\mathrm{window}\approx R_\mathrm{bytes/sec}\times T_\mathrm{seconds}
\]

With `n` JVMs or multiple recordings/dump files, sum across sources:

\[
B_\mathrm{total}\approx \sum_{i=1}^{n} R_i T_i
+ B_\mathrm{exports}+B_\mathrm{headroom}
\]

This is a **budget estimate**, not an exact law for all JFR runs: chunk rotation, format compression/encoding, profile, event mix, snapshots, and flush lag can all vary the rate.

**Hypothetical example:** a file contains **96 MiB across 12 minutes**, a rate of roughly **8 MiB/minute**. Retaining about 30 minutes at a similar rate needs around **240 MiB**. A recording configured with `maxage=30m maxsize=256m` runs tight on budget at this load; if event rate rises, the size constraint can evict older minutes before reaching 30 minutes. You must also reserve space for the chunk currently being written, exported dumps, other JVMs' files, and filesystem headroom.

If the system must guarantee at least 30 minutes **during peak hours**, measure high-percentile rates and set `maxsize` and filesystem quotas with ample headroom. **Never set a quota equal to average usage and assume it is safe.**

### 6.2. Disk Usage That `maxsize` Does Not Control

Suppose you have 8 JVMs, each rolling up to 256m—the recordings alone can consume around 8 × 256m before counting repository overhead, shared quotas, and other recordings. If each JVM also dumps a large file every 10 minutes into a directory kept for 7 days, total exported files can exceed the rolling budget many times over.

Separate at least **four zones**:

1. JFR buffers and metadata inside the JVM.
2. Repository chunks currently maintained by the JVM.
3. `.jfr` outputs from dump/stop, on the same disk or a separate one from the repository.
4. Copies sent to object storage, analysis hosts, ticketing systems, backups, and CI artifacts.

Enforce access controls, quotas, expiration policies, and monitoring for **each zone**. Rotating files in zone 2 does not manage the lifecycle of files in zone 3 or 4.

### 6.3. Disk Monitoring Recommendations

- Track `free bytes` and `free inodes` of the filesystems hosting the repository and output, not just `du` on the output directory.
- Alert when remaining space drops too low for a worst-case dump; do not wait for 100% disk full.
- Define who performs housekeeping on exported files and how failed deletes/uploads are handled.
- Sudden `.jfr` size jump? Run `jfr summary` to find event counts by type; correlate with setting or workload changes before blaming JFR.
- Dumps can fail due to disk full, missing permissions, wrong paths, namespaces, or write errors. Never mistake a 0-byte or missing file for "no events occurred."

## 7. Access Permissions: Issuing Commands Differs from Reading Files

A successful capture must distinguish **three actors**:

| Actor | Required Permission | Typical Failure Mode |
| --- | --- | --- |
| Person/tool sending `jcmd` | Can attach and send diagnostic commands to target JVM per policy/OS | Different user permissions, attach disabled on JVM, different container PID namespace |
| JVM process writing chunks/files | Write access **in the filesystem seen by the JVM** | `JFR.dump` path exists on host but not inside container; directory not writable |
| Person/tool reading `.jfr` file | Traverse directory + read file permissions; compatible JFR tools | File exists but JMC/`jfr` cannot read it; ACL or wrong file owner on copy |

The `jcmd` caller is not necessarily the owner of the created file. The target path in the command is resolved **inside the target JVM**. For instance, a JVM in a container may write `/srv/app/jfr/out.jfr` on a private mount; the same literal path on the host does not necessarily refer to the same file.

### 7.1. `.jfr` Files Can Contain Sensitive Data

Depending on configuration and enabled events, a file may expose:

- Package/class/method names, stack traces, code structure, filesystem paths.
- Thread names, processes, host/JVM info, and application components.
- File/network info, endpoints, request timestamps, SQL, or payloads **if** the app/framework/custom JFR event recorded those fields.
- Usernames, business identifiers, URLs, or secrets if custom events inadvertently logged them.

Do not assume every `.jfr` contains passwords or payloads; **actual contents depend on event settings**. Yet never treat JFR as "harmless profiling data" either. Audit event types and fields before transferring files outside authorized environments.

**Minimum policy:** least privilege, explicit storage location, retention limit, encryption in transit/at rest if required by policy, auditing who can read/download/delete, restricting sharing via unauthorized chat/email/tickets, and deleting temporary copies after analysis. If filtering events with `jfr scrub`, inspect the resulting file: filtering event types does not automatically anonymize all remaining sensitive strings or fields.

### 7.2. Example on Linux/Unix

Suppose the application runs under a service user and administrators have provisioned a properly owned directory. Before starting the JVM, set up directories with restricted permissions:

~~~bash
# Run as the service user or during provisioning with matching privileges.
install -d -m 700 /srv/app/jfr
install -d -m 700 /srv/app/jfr/repository

# Only meaningful when run in the same shell that launches the JVM:
umask 077
java -jar app.jar
~~~

A `umask 077` in a shell sending `jcmd` later **does not change the umask of the running JVM**. Actual repository/output permissions depend on the JVM user, directory mode, umask, ACLs, JFR implementation, and filesystem. After dumping, inspect:

~~~bash
ls -ld /srv/app/jfr /srv/app/jfr/repository
stat -c '%U %G %a %s %n' /srv/app/jfr/diag-rolling.jfr
# If the environment uses ACLs:
getfacl /srv/app/jfr/diag-rolling.jfr
~~~

If file permissions are too broad, handle them per the service's owner/ACL policy; on typical POSIX filesystems you may need `chmod 600` after creation, but never use `chmod 777` to "fix" file-write errors. Authorized readers need traverse permission on **every parent directory**.

Likewise, do not place the repository in shared `/tmp` and assume only exported files need protection. If temporary space must be used, verify directory permissions, creating process, crash/restart cleanup, and mount options.

### 7.3. Containers, Kubernetes, and Windows

**Containers/Kubernetes:**

- Host PIDs, container PIDs, and attach permissions may differ. Use the right JVM/PID namespace and ensure the tool can see the process.
- `JFR.configure repositorypath` and `JFR.dump filename` must point to paths writable inside the **JVM container**; to retrieve files externally, check volume mounts and permissions.
- Ephemeral storage has quotas and may vanish when a pod terminates; never treat a file existing inside a container as long-term storage.
- Shared volumes, sidecars, user namespaces, `securityContext`, and read-only root filesystems can alter read and write access.
- Never bake sensitive files into image layers, logs, or public CI artifacts.

**Windows:** check file/dir ACLs with `icacls` or appropriate admin tools, verify the JVM's service account, drive/path permissions, and cleanup mechanisms. `chmod`/`umask` above are POSIX examples and do not translate directly to NTFS ACLs.

### 7.4. What Is Security vs. Merely Operations?

- `maxage`/`maxsize` are **data retention controls**, not access-control or encryption features.
- Renaming `.jfr`, zipping, or moving files to a hidden directory does not protect data; real access controls are required.
- A successful JFR dump does not prove the analyst has read access; verify ACLs on the **actual output**.
- Files evicted from the repository may still exist in backups or copies. Retention policies must cover copies and organizational compliance requirements.

## 8. Java 17+ Practice: Write a Small `.jfr` File, Check Size, and Verify Events

The example below uses the **official JFR APIs** `jdk.jfr` and `jdk.jfr.consumer` included in JDK 17 and later. It defines a custom event, enables it, emits 200 events, dumps a temporary `.jfr` file, reads it back to verify, and deletes the file. This demonstrates **measurement/verification capability**, not a reliable throughput/CPU benchmark: do not use the runtime of this tiny program as the overhead % of a production service.

Single file `JfrBudgetDemo.java`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;
import jdk.jfr.consumer.RecordedEvent;

public final class JfrBudgetDemo {
    @Name("training.CostEvent")
    @Label("Cost demo event")
    static final class CostEvent extends Event {
        @Label("Sequence")
        long sequence;
    }

    public static void main(String[] args) throws Exception {
        Path destination = Files.createTempFile("jfr-budget-", ".jfr");
        try {
            try (Recording recording =
                     new Recording(Configuration.getConfiguration("default"))) {
                recording.setName("budget-demo");
                recording.setToDisk(true);
                recording.setMaxAge(Duration.ofMinutes(1));
                recording.setMaxSize(32L * 1024 * 1024);
                recording.enable(CostEvent.class).withoutStackTrace();

                recording.start();
                for (int i = 0; i < 200; i++) {
                    CostEvent event = new CostEvent();
                    event.sequence = i;
                    event.commit();
                }
                recording.stop();
                recording.dump(destination);
            }

            int matchingEvents = 0;
            try (RecordingFile recordingFile = new RecordingFile(destination)) {
                while (recordingFile.hasMoreEvents()) {
                    RecordedEvent event = recordingFile.readEvent();
                    if (event.getEventType().getName()
                             .equals("training.CostEvent")) {
                        matchingEvents++;
                    }
                }
            }

            System.out.println("matchingEvents=" + matchingEvents);
            System.out.println("nonEmpty=" + (Files.size(destination) > 0));
            System.out.println("fileDeletedInFinally=true");
        } finally {
            Files.deleteIfExists(destination);
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac JfrBudgetDemo.java
java JfrBudgetDemo
~~~

Verified stdout of the example on OpenJDK 24, with event logic compatible with JDK 17+:

~~~text
matchingEvents=200
nonEmpty=true
fileDeletedInFinally=true
~~~

**Line-by-line explanation:**

- `Configuration.getConfiguration("default")` starts from the default JFR configuration, then `enable(CostEvent.class)` explicitly enables the custom event. Without enabling it, you cannot assume 200 `commit()` calls will appear in the file.
- `withoutStackTrace()` reduces stack data for this lab event; in a real call-site investigation, stack traces may be necessary and incur cost.
- `setToDisk(true)`, `setMaxAge`, and `setMaxSize` bound the recording's history; they do **not** set ACLs or quotas on exported files.
- `recording.stop()` followed by `recording.dump(destination)` writes the file from the stopped recording's data. For recordings with `toDisk=true`, the API allows dumping after `stop` before `close`.
- `RecordingFile` inspects events in the file, distinguishing "a `.jfr` file exists" from "the file actually contains the required events."
- `Files.size` verifies the file is non-empty; **exact byte size varies across JDKs, machines, and runs**, so the example prints only a boolean.
- `try/finally` cleans up the temp file even if a step throws an exception; `fileDeletedInFinally=true` describes the cleanup branch about to execute, not a post-delete check. In real apps, temp paths must also satisfy security policies.

**To measure overhead:** keep a real application workload steady and run baseline/default/profile sessions per section 5. Do not extrapolate production cost from the JVM/JFR startup time of this small program. **To inspect size:** change the `nonEmpty` line to print `Files.size(destination)`, keeping in mind that is the byte count of *one* file under *one* workload, not a fixed constant across all sessions.

**To keep the file for inspection:** use an appropriately permissioned directory and intentionally skip cleanup in a controlled session; accompany that change with retention and deletion policies. Never put production output into shared public temp by default.

## 9. Layer-by-Layer Troubleshooting for Recording Failures

| Symptom | Likely Cause | Verification Step |
| --- | --- | --- |
| `jcmd` cannot find PID or attach fails | Wrong PID/namespace; different user; JVM stopped; attach blocked | `jcmd -l` in the right environment, OS permissions, `VM.version` |
| `JFR.start` reports invalid option | Different JDK/VM, misspelled option, `maxsize` below `maxchunksize` | `jcmd <pid> help JFR.start` and `JFR.configure` |
| Recording running but no output file | No dump/stop with filename yet; checking wrong path; `disk=false` not persisting history | `JFR.check`, `JFR.dump`, path seen by the JVM |
| Dump reports permission denied | JVM user cannot write directory or traverse parent directories | Owner/mode/ACL along the full path, JVM service account |
| File created but analyst cannot open it | Reader lacks ACL, file not copied out of volume, file incomplete/corrupt | `stat`/`icacls`, `jfr summary`, filesystem mounts |
| Repository size grows rapidly | High event rate, missing `maxage`/`maxsize`, multiple recordings | `JFR.check`, settings, disk usage, event counts |
| `.jfr` larger than expected | Event types/thresholds changed, many stack traces, different workload | `jfr summary`, compare equal-workload intervals |
| `.jfr` small yet missing the incident timestamp | Retention too short, `maxsize` evicted old chunks, recording started late | Timeline, start time, `maxage`, free space, file event timestamps |
| P99 rises during dump | I/O burst, GC-root paths, saturated shared disk, or concurrency | Correlate dump timing with latency, IOPS, GC/JFR events |
| Repository usage drops yet disk remains full | Exported/snapshot/backup files accumulated or deleted files held open | `du`/`df`, quotas, file ownership, housekeeping |

On dashboards, separate `RECORDING_RUNNING`, `DUMP_SUCCEEDED`, `FILE_VALIDATED`, and `FILE_SECURED`. A green status for start does not replace verifying the file was created, contains the needed events, and is properly secured.

## 10. Recommended Operational Workflow and Stop Criteria

Before capturing: define the concrete diagnostic question, recording duration, JDK version, required events, data owner, remaining disk space, and read/write permissions. Set up post-enable verification checks.

During capture: watch throughput/p99/CPU, free space/quotas, event rates, and write errors. If the application breaches approved performance thresholds or the filesystem nears full, stop per your runbook; never leave it running blindly because "`default` is usually light."

At completion: explicitly `dump` or `stop filename=...`, check exit status, `jfr summary`, time span/event types, file size, and ACLs. Transfer files only to authorized recipients with context on purpose and sensitivity. Revoke temporary permissions, delete unneeded files, and track copies.

### Decision Checklist Before Enabling JFR

- [ ] Defined a diagnostic question and retention duration instead of collecting all events indefinitely.
- [ ] Checked `jcmd ... help JFR.start` for the target JVM; know settings, version, and collector.
- [ ] Measured or reasonably estimated CPU/latency impact and defined stop thresholds.
- [ ] Identified repository path, output path, volume/mount, filesystem quota, and reserve space.
- [ ] Picked `maxage`/`maxsize` or `duration` appropriately, understanding chunk rotation and that dumps are not deleted by them.
- [ ] Separated attach permissions, JVM file-write permissions, and reader permissions.
- [ ] Checked whether files may hold sensitive data and established transfer/storage/deletion policies.
- [ ] Have post-dump verification (`JFR.check`, `jfr summary`, size, ACLs) and an assigned owner for cleanup.

## 11. Self-Check Exercises

**Exercise 1 — overhead.** Under the same workload, baseline is 1,000 req/s and p99 = 100 ms; with `profile` enabled, throughput is 950 req/s and p99 = 120 ms. How much did throughput drop? **5%**. How much did p99 rise? **20%**. Can you conclude all JFR recordings increase p99 by 20%? **No**; this reflects a specific config, workload, and measurement window.

**Exercise 2 — retention.** A recording generates 8 MiB/minute. The goal is to retain at least 30 minutes of history, yet `maxsize` is only 160 MiB. At an ideal steady rate, the window is 160/8 ≈ **20 minutes**, before chunk and overhead effects. Does increasing `maxage` to `1h` fix it? **No**; the size cap still evicts older data.

**Exercise 3 — multiple dumps.** A JVM keeps a rolling recording with `maxsize=256m`, but automation dumps 100 MiB every 5 minutes for 6 hours without cleaning up files. Roughly how much exported data accumulates? **72 × 100 MiB = 7,200 MiB**, not counting the repository and copies. `maxsize` does not protect the output directory from this accumulation.

**Exercise 4 — container permissions.** An operator can send `JFR.dump`, yet the JVM reports it cannot create `/mnt/jfr/report.jfr`. Diagnose in order: does the path exist inside the JVM container, what is the process UID/GID, do parent directories have execute/write permissions, and is the mount read-only or out of quota? Seeing `/mnt/jfr` on the host does not prove the container sees the same volume.

**Exercise 5 — data sharing.** A `.jfr` recording has custom events containing request URLs and user identifiers. Can it be published publicly simply because `jfr scrub` filtered out GC events? **No**; inspect remaining events and fields, and verify organizational policy and recipient authorization.

**Exercise 6 — performance.** The file is only 4 MiB, yet stopping one recording spiked p99. Can you blame large file size? **No**; check GC-root paths, heap statistics, CPU/GC, I/O bursts, and JVM work occurring at dump/stop time.

## 12. Key Takeaways

1. `default.jfc` is a lightweight starting point for continuous recording, and `profile.jfc` suits bounded deep dives; **measure overhead under real load**.
2. **Repository chunks differ from `.jfr` outputs.** Rolling quotas do not delete exported files or copies.
3. `maxage` and `maxsize` cap retained history in a recording when `disk=true`; node-wide disk usage still depends on JVM count, chunks, and exports.
4. Permission to **run `jcmd`**, permission for the **JVM to write files**, and permission to **read files** are three separate problems.
5. `.jfr` files can hold sensitive information. Access controls, content review, retention, and cleanup must accompany collection.
6. A recording is truly useful only when it has the right events and time range without violating performance, storage, or access budgets.

## References

- Oracle Java SE 21, [Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html) — `default.jfc`, `profile.jfc`, and overhead trade-offs.
- Oracle Java SE 21, [The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html) — `JFR.configure`, `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`, size/age limits, and JDK 21 option names.
- Oracle Java SE 21, [The jfr Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html) — `summary`, `print`, `metadata`, `scrub`, and file analysis.
- Oracle Java SE 21, [jdk.jfr.Recording API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html) and [jdk.jfr.consumer](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/package-summary.html) — creating, stopping, dumping, size/age, and reading events.
- Oracle Java SE 21, [The java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html) — `-XX:StartFlightRecording` and startup JFR options.
