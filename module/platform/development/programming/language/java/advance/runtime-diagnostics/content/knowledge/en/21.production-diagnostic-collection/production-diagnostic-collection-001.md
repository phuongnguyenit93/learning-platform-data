# 21.1 Designing a Resource-Budgeted Baseline Dataset of VM Info, GC Logs, and JFR

> **Scope:** Java 21, HotSpot JVM, long-running service environments on virtual machines, containers, or Kubernetes. The baseline dataset is a collection of evidence **captured proactively before an incident**, sufficient to correlate JVM state, GC, and key JFR activity with user-facing symptoms. The design must both **provide pre-, during-, and post-incident data** and **stay within CPU, latency, RAM, disk, I/O/network, and retention budgets**. Recording more data does not automatically improve diagnostic capability.

## 1. Required Outcomes

A solid baseline configuration must answer six questions:

1. **Which JVM is running?** JDK vendor/build, application version, GC/heap flags, PID and startup time, instance/container/pod, CPU/RAM limits.
2. **Is GC affecting latency?** GC logs with UTC + uptime, GC ID, pauses, heap before/after, and required collector details.
3. **What else happened at the same time?** JFR with a ring buffer/disk recording, verified event settings, and sufficient CPU/threads/GC/locks/I/O data for common diagnostic needs.
4. **How long is data retained?** Size limits, measured write rates, actual time window under peak load, and dump triggers before rotation overwrites data.
5. **What is the cost?** Per-workload overhead, peak disk usage including exported files, container quotas, shipping bandwidth, and replica multiplication costs.
6. **Who has access and when is it deleted?** Data classification, ACLs, encryption, checksums, owners, retention policies, and handoff procedures.

Do not confuse **having JFR enabled** with **having preserved an investigation file**, or **having GC logs** with **having enough minutes captured before an alert**. You must rehearse the full pipeline: startup → recording → exporting → opening/reading → preserving and deleting on schedule.

## 2. Cost-Based Three-Tier Design

| Tier | Contents | Frequency / Condition | Main Risks |
| --- | --- | --- | --- |
| A — per-JVM-session inventory | VM.version, VM.flags, VM.command_line when permitted, VM.uptime, app build, pod UID, container limits | At startup/restart and on config changes | Leaking secrets in arguments, misidentifying instances after restart |
| B1 — GC log | Unified logging for GC/pauses, UTC+uptime, with file rotation | Continuous, moderate verbosity | Excessive writes during GC storms, rotation deleting pre-incident data |
| B2 — default JFR | Recording using default.jfc, disk=true, bounded maxage/maxsize | Continuous within budget | Actual retention shorter than required, repository filling up or lost on pod death |
| C — elevated diagnostic capture | JFR profile/custom config, detailed lock/I/O, thread dumps, debug logging | Short window once a hypothesis and approval exist | Overhead, STW/disk/CPU impact, large or sensitive data |

Tiers A, B1, and B2 form the **baseline dataset** of this lesson. Tier C is only an escalation strategy and must not be enabled indiscriminately across all replicas.

**Do not include in an unbounded baseline:** heap dumps, class histograms, NMT detail, full thread dumps every few seconds, JFR path-to-GC-roots, or Heap Statistics. Those operations serve different purposes and can consume significant CPU, heap, and I/O or introduce substantial pauses.

## 3. Shared Identity and Timeline Design

Every artifact must tie back to **a specific JVM instance**, not just a service name.

| Attribute | Data to Retain | Value |
| --- | --- | --- |
| Service/environment | name, deployment, namespace, app build/image digest | Identifies the application group and release |
| Instance | hostname, pod UID/container ID, JVM PID, and startup timestamp | PIDs can collide across pods or be reused |
| VM | vendor, Java 21 build, VM name, GC, Xms/Xmx, JFR config | Explains differences across deployments |
| Resource limits | cgroup CPU quota, CPU throttling, memory limit, volume quota | Explains CPU/RSS behavior and log retention capacity |
| Time | UTC timestamp, JVM uptime, timezone, NTP skew, sampling bucket | Aligns request latency/GC/JFR without clock drift errors |
| Artifact | type, source, start/end UTC, path, size, checksum, owner, TTL | Protects and traces diagnostic data |

JFR events carry absolute timestamps; unified logging can print UTC and uptime; monitoring sometimes uses 10-second or 1-minute buckets. **Do not claim causality at millisecond precision when clock skew or metric resolution does not support it.**

Hypothetical example: three pods all run a JVM with PID 1. Using only the PID to correlate GC logs and JFR is **wrong**; you must include pod UID/instance and JVM startup time. After a rolling restart, a new inventory record is required even if the image/app version has not changed.

### 3.1. Practical Manifest Template

~~~yaml
schema: java21-diagnostics-baseline/v1
service: catalog-api
environment: production
instance: catalog-api-pod-example
pod_uid: example-uid
jvm_start_utc: "2026-10-29T09:20:00Z"
jvm_pid: 1
jdk_version: "21.0.x"
jdk_vendor: "capture-actual-value"
gc: "verify-from-VM-flags"
jfr_setting: default
gc_log_pattern: "/srv/diag/gc-%p.log"
jfr_retention: "maxage=30m,maxsize=128m"
clock: "UTC; NTP offset must be checked"
artifacts:
  - kind: vm-flags
    file: vm-flags.txt
    checksum: "compute-after-write"
  - kind: gc-log
    file: gc-1.log
    checksum: "compute-after-write"
  - kind: jfr-incident
    file: incident-window.jfr
    checksum: "compute-after-write"
~~~

This is an **illustrative schema**, not captured data. During implementation, populate real values; never submit placeholders and claim collection is complete.

## 4. Tier A — VM Metadata: Infrequent Capture, Complete Context

### 4.1. Java 21 Command Set

For a JVM running on a host or container where the operator has attach permissions, verify the real PID. Sample commands:

~~~bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.uptime
jcmd <PID> VM.flags
jcmd <PID> VM.command_line
jcmd <PID> VM.info
~~~

Explanation:

- **VM.version:** target HotSpot/JDK version info; do not confuse with `java -version` on the operator's machine, which may run a different JDK.
- **VM.uptime:** JVM lifetime in seconds; correlate with startup time from the orchestrator/monitoring.
- **VM.flags:** runtime flag values, including heap/GC and configuration variables that can affect footprint, pauses, and JFR.
- **VM.command_line:** startup arguments, which may contain app paths, flags, and important configuration.
- **VM.info:** broader JVM/environment/status details, useful during incident analysis though it can be long.
- **jcmd -l:** finds PIDs in the observable namespace, not a durable identity mechanism.

**Special security note:** `VM.command_line` and `VM.system_properties` may contain tokens, passwords, proxies, hostnames, and internal connection settings. Do not paste them directly into tickets, Git, or public chat. Separate **restricted-access raw artifacts** from **redacted copies** used for sharing.

One snapshot per startup/restart or configuration change is sufficient for **inventory**. Capturing `VM.info` every second serves no purpose; use metrics/JFR to observe CPU/heap fluctuations.

### 4.2. Sample Capture and File Verification

Linux shell example, assuming the operator has verified the PID and holds permissions:

~~~bash
umask 077
TARGET_PID=12345
EVIDENCE_DIR="$HOME/java-diagnostics"
mkdir -p "$EVIDENCE_DIR"
chmod 700 "$EVIDENCE_DIR"

date -u +"%Y-%m-%dT%H:%M:%SZ" > "$EVIDENCE_DIR/captured-utc.txt"
jcmd "$TARGET_PID" VM.version > "$EVIDENCE_DIR/vm-version.txt"
jcmd "$TARGET_PID" VM.uptime > "$EVIDENCE_DIR/vm-uptime.txt"
jcmd "$TARGET_PID" VM.flags > "$EVIDENCE_DIR/vm-flags.txt"
~~~

**12345 is a hypothetical PID**—do not copy it into production. Check the exit code of each `jcmd`, along with file sizes and permissions: shell redirection can still create an empty file when attach fails. Pull app build, image digest, and CPU quota from an authorized deployment inventory rather than inferring them from the PID name.

Do not store secrets merely in the name of "completeness." If startup command lines must be retained, apply dedicated access controls and redaction; never auto-attach raw files to ticketing systems.

## 5. Tier B1 — GC Unified Logging: Content Selection and Rotation

### 5.1. What Do GC Logs Add Beyond JFR?

GC logs provide a collector-specific event stream: GC ID, phases, pauses, heap before/after, causes when available, and JVM logging configuration details. JFR gives a timeline across CPU/GC/threads/locks/I/O; **GC logs are typically richer in collector detail**. Both require UTC/uptime and JVM identity to compare against request latency.

**GC duration does not always equal STW pause.** Collectors have concurrent phases; do not add a total GC duration and its internal pause phases together as if there were two separate stops. When reporting p99 impact, align exact **GC pause intervals**, not just GC counts.

### 5.2. Disk-Bounded Java 21 Startup Syntax

Assume `/srv/diag` is a filesystem writable by the JVM account:

~~~bash
java \
  -Xlog:gc*,safepoint:file=/srv/diag/gc-%p.log:utctime,uptime,level,tags:filecount=4,filesize=20M \
  -jar app.jar
~~~

- **gc* and safepoint**: tag selectors at default level; event volume depends on collector and workload.
- **utctime,uptime**: enables correlation with JFR UTC timestamps and positioning along JVM lifetime.
- **level,tags**: identifies log severity and event type, preserving context during parsing.
- **%p**: embeds the PID into the log filename; **not a unique ID across multiple containers**. If using a shared volume, partition by pod/instance or use distinct file naming/manifests.
- **filecount=4,filesize=20M**: rough budget of about **80 MiB** of logs per instance plus headroom. Rotation has overhead and rounding tolerance; verify actual files after testing.

A GC storm can multiply the log write rate several times over. Therefore, **rotation bounds disk space, not retention hours**. If output is set to debug/trace or a log shipper duplicates data, costs are higher.

### 5.3. Measure in Practice Before Broad Rollout

~~~bash
jcmd <PID> VM.log list
ls -lh /srv/diag
df -h /srv/diag
df -i /srv/diag
~~~

If `VM.log` syntax needs build-specific verification, run `jcmd <PID> help VM.log`. Track bytes written over a representative load period and compute:

~~~text
rate_mib_per_hour = measured_log_mib / measured_hours
expected_retention_hours ≈ configured_rotation_mib / rate_mib_per_hour

Example: 80 MiB rotation, 10 MiB/hour = roughly 8 hours at the measured rate.
When an incident raises the rate to 40 MiB/hour, retention drops to 2 hours.
~~~

This is an **estimate**, not an exact guarantee. Prioritize measuring **peak-hour** rates to size rotation. If longer pre-alert retention is needed, ship GC logs early to a suitably secured store with separate retention instead of increasing `filecount` indefinitely.

In a running JVM, `jcmd VM.log` can adjust some outputs/tags when permitted, but **cannot recover unlogged events from the past**. Temporary debug-level increases must have a TTL, owner, and rollback.

## 6. Tier B2 — Continuous Low-Overhead JFR

### 6.1. How Does `default` Differ from `profile`?

Oracle JDK 21 ships `default.jfc` and `profile.jfc`. **default.jfc** is recommended for continuous recording, with overhead **typically under 1%** per Oracle documentation (not a guarantee for every workload). **profile.jfc** enables more event types and is suited for short investigations, but consumes more CPU and disk.

| Configuration | Recommended Use | Limitations to Remember |
| --- | --- | --- |
| default | Continuous baseline to locate the incident window | Does not enable all events or every stack by default; thresholds/sampling may omit short operations |
| profile | Short profiling runs when finer hot methods or contention detail is needed | Higher event rate/overhead; must define a stop point |
| Custom .jfc | A specific hypothesis requiring extra events or lower thresholds | Must benchmark overhead and keep the config file to interpret results |

**Do not enable Heap Statistics or path-to-gc-roots in the baseline out of habit.** They are meant for memory leak investigations and can trigger extra GCs or expensive collections, distorting the very latency the system is measuring.

### 6.2. Starting JFR Alongside GC Logs

~~~bash
java \
  -Xlog:gc*,safepoint:file=/srv/diag/gc-%p.log:utctime,uptime,level,tags:filecount=4,filesize=20M \
  -XX:StartFlightRecording=name=baseline,settings=default,disk=true,maxage=30m,maxsize=128m \
  -jar app.jar
~~~

JFR flag explanation:

- **name=baseline**: recording identifier used by `JFR.check` or `JFR.dump`.
- **settings=default**: applies `default.jfc`; does not mean every event is enabled.
- **disk=true**: uses a disk repository to store recording data; the repository path may default to the OS temp directory. Verify against actual configuration.
- **maxage=30m**: target time window for retaining recorded data on disk, provided space suffices.
- **maxsize=128m**: cap on retained recording data; JFR stores data in chunks and enforces a minimum chunk size constraint. This is not a limit on **total disk including exported dump files, GC logs, application logs, and temporary files**.

**The actual time window can be shorter than 30 minutes** when data is written rapidly and `maxsize` is reached before `maxage`. You must measure bytes/hour and inspect the start/end timestamps of real dump files. Once the JFR ring has rotated away the incident window, those events cannot be reconstructed later.

### 6.3. Verification and Preservation on Alert

~~~bash
jcmd <PID> JFR.check
jcmd <PID> JFR.check verbose=true
jcmd <PID> JFR.configure
~~~

Verify recording name, duration, event settings/thresholds, disk/maxage/maxsize, and repository path. The account running `jcmd` must have attach permissions; container PIDs differ from host PIDs.

Right after an incident occurs, write a dump **before the ring rotates**:

~~~bash
jcmd <PID> JFR.dump name=baseline \
  filename=/srv/diag/incident-20261029T101500Z.jfr
~~~

The timestamped filename is **hypothetical** and must be replaced with a unique name matching the actual time. The dump file is created on the **target JVM's filesystem** and can occupy space comparable to a full recording **in addition to** existing chunks. `JFR.dump` does not stop the background recording, but writing the file still consumes I/O and requires headroom.

After exporting the file:

~~~bash
jfr summary /srv/diag/incident-20261029T101500Z.jfr
jfr metadata --events jdk.GarbageCollection,jdk.CPULoad \
  /srv/diag/incident-20261029T101500Z.jfr
~~~

`jfr summary` verifies the recording interval and event counts for the **entire file**; it does not isolate a single high-p99 minute on its own. Use JDK Mission Control or the `jdk.jfr.consumer` API to analyze specific intervals. If an event is absent, check configuration, thresholds, sampling, duration, retention, and whether you attached to the right JVM before concluding no issue occurred.

### 6.4. Short-Window Escalation

When more execution samples or finer stack/lock/I/O details are needed and cost has been verified:

~~~bash
jcmd <PID> JFR.start name=incident-profile \
  settings=profile disk=true duration=3m \
  filename=/srv/diag/incident-profile.jfr
~~~

**This is a time-bounded investigation session**, not a replacement for the baseline configuration. Check with `JFR.check` and confirm the profile recording stops on schedule while the baseline recording remains intact. If exporting an intermediate file while it is still running:

~~~bash
jcmd <PID> JFR.dump name=incident-profile \
  filename=/srv/diag/incident-profile-partial.jfr
~~~

Include **the profile recording, exported files, baseline ring, and GC logs** when checking the disk budget. Do not rely on a single static overhead figure because events may be collected concurrently under the effective configuration; load-test the full active combination.

## 7. Calculable and Verifiable Resource Budgets

### 7.1. Capacity Model

~~~text
PerJVM_LocalBudget =
    GC_log_rotation
  + JFR_repository
  + concurrent_JFR_exports
  + incident_profile_files
  + VM_metadata
  + other_local_logs/temp
  + safety_headroom

FleetBudget = Σ PerJVM_LocalBudget across replicas and nodes

GC_retention_hours ≈ GC_rotation_bytes / observed_GC_bytes_per_hour

JFR_retention_hours ≈ min(
    configured_maxage_hours,
    maxsize_bytes / observed_JFR_bytes_per_hour
)
~~~

These are **estimation** formulas: event rates rise during incidents, JFR chunking/temporary files have granularity, compression/copying create transient peaks, and storage/container limits may differ from host filesystems.

### 7.2. Quantitative Example (Not a Default Configuration)

Assume 4 replicas, each pod has a 1 GiB diagnostics volume, and app logs sit on a separate volume; per pod:

| Item | Allocation |
| --- | ---: |
| GC logs: 4 × 20 MiB | 80 MiB |
| JFR continuous repository | 128 MiB |
| One concurrent JFR incident dump | 128 MiB |
| VM snapshots + manifest | 5 MiB |
| Temporary/metadata/other | 20 MiB |
| Safety headroom | 128 MiB |
| **Total** | **489 MiB/pod** |

Calculation: **80 + 128 + 128 + 5 + 20 + 128 = 489 MiB/pod**. Across 4 replicas, total reserved capacity is around **1,956 MiB (~1.91 GiB)** across volumes, excluding app disk usage or unplanned incident profiles.

If **three** JFR dump files are kept simultaneously instead of one, you must add the actual size of two additional copies; you cannot rely solely on the ring's `maxsize=128m`. If multiple pods share a PVC, enforce limits per **PVC/node** rather than merely dividing evenly per pod.

Disk-exhaustion safeguards: alert when volume usage crosses an agreed threshold; cap concurrent dumps, apply cooldowns to avoid alert flapping, restrict profiling when space is tight, ship via secure channels, and verify checksums before deleting source files.

### 7.3. CPU, Latency, and RAM

Oracle documentation notes that `default.jfc` **typically** has low overhead, but the total cost of VM snapshots, GC logging, JFR event sampling, exporters, checksums, encryption, compression, and shipping depends on the application.

Run A/B or canary tests under identical JDK build, GC flags, CPU quota, request load, dataset, and warmup:

1. **A:** application and existing monitoring, no added baseline data.
2. **B:** enable startup VM inventory + rotated GC logs.
3. **C:** add continuous default JFR.
4. **D:** enable a short profile/custom recording to size escalation budget.
5. Repeat during normal hours and peak load, keeping full measurement counts and variance.

Compare throughput, p95/p99 latency, error rate, CPU-seconds/request, JVM RSS/cgroup memory, CPU throttling, GC pauses, local disk bytes/s, network ship throughput, and disk high-water mark. Report only overhead **measured on an equivalent workload**; do not treat the documented <1% figure as an SLO commitment.

**RAM:** JFR uses local/global buffers in addition to keeping chunks on disk; `maxsize`/`maxage` do not bound all native memory overhead. Only tune `JFR.configure` parameters such as `memorysize`/`stackdepth` with supporting evidence and an understanding of JVM initialization constraints.

### 7.4. Actual Retention and Operational Edge Cases

- GC storms increase bytes/hour, causing logs to rotate faster.
- A default ring with `maxage=30m` and `maxsize=128m` may retain only a few minutes if recording event rates are high.
- A container that is OOMKilled/evicted can lose its JFR repository on ephemeral storage before an operator can dump it.
- An exported dump file can fill the volume even while the ring stays within `maxsize`.
- When copying to central storage, shipper bandwidth and queues are bounded; never allow queue/logging backlogs to consume unbounded disk.
- If multiple services share one volume, enforce per-tenant quotas and prioritize logs required for application operation.
- Record the **actual earliest retained event timestamp** during each drill; `maxage` alone does not prove retention.

## 8. Startup, Verification, and Shipping Runbook

### 8.1. Preparing the Filesystem

Example with JVM account `app` in a Linux environment:

~~~bash
sudo install -d -o app -g app -m 0700 /srv/diag
sudo -u app test -w /srv/diag
df -h /srv/diag
df -i /srv/diag
~~~

Substitute paths, accounts, owners, and volumes to match reality. The directory should be dedicated, quota-bounded, and outside public web roots or source code repositories.

### 8.2. Illustrative Startup Configuration for All of Tier B

~~~bash
java -Xms512m -Xmx2g \
  -Xlog:gc*,safepoint:file=/srv/diag/gc-%p.log:utctime,uptime,level,tags:filecount=4,filesize=20M \
  -XX:StartFlightRecording=name=baseline,settings=default,disk=true,maxage=30m,maxsize=128m \
  -jar app.jar
~~~

**-Xms512m / -Xmx2g are examples only**; a service container may have a memory limit smaller than heap + metaspace + stacks + buffers, so recalculate accordingly. The JFR repository location may default to temp: verify with `JFR.configure` and configure storage per policy; do not assume all JFR data resides in `/srv/diag`.

### 8.3. Mandatory Acceptance Tests

~~~bash
jcmd <PID> VM.version
jcmd <PID> VM.flags
jcmd <PID> VM.uptime
jcmd <PID> VM.log list
jcmd <PID> JFR.check verbose=true
jcmd <PID> JFR.configure
~~~

PASS only when:
- PID and JVM instance are verified;
- GC logs contain lines with UTC/uptime and rotation works;
- `JFR.check` shows the `baseline` recording running with the expected settings;
- a **real** JFR dump can be exported and opened with `jfr summary`;
- artifacts carry timestamps, owner, checksum, and destination;
- disk/CPU overhead stays within the measured budget;
- no secrets are exposed in broadly shared locations.

`jcmd` shell redirection can create an empty file even if attach fails; inspect both exit code and contents. In containers, `jcmd` from the host may not see the JVM due to PID namespaces/users; tools inside minimal JDK images may not be installed.

## 9. Incident Collection: Prioritize Volatile Data First

A concise incident workflow:

1. **Stamp the symptoms**: UTC start/end, p95/p99/error rate, endpoint, traffic, pod/host, metric resolution, and clock skew.
2. **Target the right JVM**: confirm version/PID/startup/GC flags; never mix replicas.
3. **Dump the JFR ring immediately** if retention still covers the symptom; use a unique filename on the target JVM's filesystem.
4. **Preserve GC logs** covering the same window, including rotated files; do not delete the actively written file.
5. **Save VM metadata/manifest** and checksums once artifacts finish writing, then copy safely to the destination.
6. **Align on a single timeline** across GC pauses, JFR events, and APM/traces; inspect the request critical path rather than summing durations of parallel threads.
7. **Escalate conditionally**: if evidence is missing, enable `profile` or detailed logging for a few minutes with an approved budget and owner. Past unrecorded data cannot be created.
8. **Return to baseline**; retain or delete data per retention policy, explicitly documenting any missing/lost intervals.

If an alert arrives later than ring retention, mark **evidence unavailable** rather than claiming the JVM had no anomalous events.

### 9.1. Extracting a Surviving Historical Window

Java 21 allows `JFR.dump` with explicit `begin`/`end` times. UTC timestamp example:

~~~bash
jcmd <PID> JFR.dump name=baseline \
  begin=2026-10-29T10:14:30Z end=2026-10-29T10:17:00Z \
  filename=/srv/diag/incident-window.jfr
~~~

Recording name, path, and timestamps are all **samples** to be replaced. If a long event began before the window, extracting chunks and filtering events by start/end may require keeping a broader source recording. Dumping cannot recover segments already rotated out by `maxsize`/`maxage`.

## 10. Java 21 Lab to Verify All Three Layers

The standalone lab program below runs for about 20 seconds, continuously allocating small arrays to generate a test workload. It **does not guarantee** that JFR contains every event type or that GC occurs a fixed number of times, but it lets you verify the end-to-end pipeline.

Create **BaselineCaptureLab.java**:

~~~java
public final class BaselineCaptureLab {
    private static volatile byte[] lastBlock;

    public static void main(String[] args) throws Exception {
        int seconds = args.length == 1 ? Integer.parseInt(args[0]) : 20;
        if (seconds < 1 || seconds > 120) {
            throw new IllegalArgumentException("seconds must be 1..120");
        }
        System.out.println("BASELINE LAB START");
        long finish = System.nanoTime() + seconds * 1_000_000_000L;
        while (System.nanoTime() < finish) {
            lastBlock = new byte[256 * 1024];
            lastBlock[0] = 1;
            Thread.sleep(50);
        }
        System.out.println("BASELINE LAB DONE");
    }
}
~~~

Run using JDK 21 in a writable practice directory:

~~~bash
mkdir -p ./diag-lab
javac BaselineCaptureLab.java
java -Xms32m -Xmx128m \
  -Xlog:gc*,safepoint:file=./diag-lab/gc-%p.log:utctime,uptime,level,tags:filecount=3,filesize=10M \
  -XX:StartFlightRecording=name=baseline,settings=default,disk=true,maxage=5m,maxsize=64m,dumponexit=true,filename=./diag-lab/baseline-lab.jfr \
  BaselineCaptureLab 20
~~~

**Stdout printed by the program itself**, excluding JFR/JVM messages:

~~~text
BASELINE LAB START
BASELINE LAB DONE
~~~

While it is still running, from another terminal on the same host/user:

~~~bash
jcmd -l
jcmd <LAB_PID> VM.version
jcmd <LAB_PID> VM.flags
jcmd <LAB_PID> VM.log list
jcmd <LAB_PID> JFR.check verbose=true
~~~

After the program exits normally, thanks to `dumponexit=true`, the recording is dumped to the specified basename file (if the filesystem is writable). Inspect:

~~~bash
ls -lh ./diag-lab/
jfr summary ./diag-lab/baseline-lab.jfr
jfr print --events jdk.GarbageCollection,jdk.CPULoad \
  ./diag-lab/baseline-lab.jfr
~~~

There is no fixed stdout for `jfr` commands: event counts and runtime timestamps vary per machine. **GC events may not appear** even when properly configured, because the run is short and the heap may suffice; do not treat that as proof of missing logging. What must be proven is that the file exists, the interval is accurate, enabled events match settings, and the file opens cleanly.

Try two more runs under similar load: one with `settings=profile`; one with a higher allocation rate or modified GC log rotation. Measure actual bytes/s, overhead, and retention rather than copying the lab's `64m`/`10M` values into production.

## 11. Security and Data Lifecycle

| Artifact | Risk | Mitigation |
| --- | --- | --- |
| VM.command_line, VM.system_properties | Passwords, tokens, DB URLs, proxy credentials | Restrict capture, encrypt raw, produce redacted copy, least privilege |
| VM.version, VM.flags, inventory | System configuration, paths, and topology | Role-based access, do not publish internally without scope |
| GC logs | Heap sizing, GC tuning, application timing | Rotation, ACLs, isolated storage, policy-driven deletion |
| JFR | Method/class/thread names, call stacks, host/path/network info, event fields | Isolated storage, encryption at rest/in transit, audit/TTL |
| Manifest and checksums | Pod/instance info and artifact locations | Appropriate classification and access permissions |

Design a **two-tier retention model**: local rings retain recent data with strict bounds to protect the service; upon an incident, artifacts are exported to a controlled secure store and retained longer per **policy** (Java does not enforce a default 7-day TTL). After copying, verify file sizes, source/destination checksums, readability with the appropriate tools, and record the custodian.

Never post raw JFR/VM properties to GitHub, public tickets, pastebins, or unapproved chats. Never delete source files while the JVM is still writing or before the destination copy is verified; delete/revoke upon expiration per policy.

## 12. QA and Monitoring Metrics for the Diagnostics Pipeline Itself

A pipeline does not pass merely because startup had no errors. Verify:

| Check | PASS When | What to Do on FAIL |
| --- | --- | --- |
| JVM identity | Consistent vendor/build, PID/startup, pod UID, app version | Fix manifest/metadata collection |
| GC logging | File exists, UTC/uptime present, rotation works, output on intended volume | Check `-Xlog` flags, JVM permissions, collector |
| JFR availability | `JFR.check` shows `baseline` with correct settings | Check startup flags, JDK, permissions, disk |
| JFR recoverability | Dump succeeds, `jfr summary` opens it, file covers symptom window | Resize ring within budget or dump earlier |
| Disk and quotas | Covers ring + dump + headroom without uncontrolled sharing of critical volumes | Reduce recording/exports, adjust volume/quota |
| Latency overhead | p95/p99, throughput, CPU, and RSS within measured thresholds | Reduce event/log detail, shorten capture |
| Security | Raw artifacts absent from public storage; ACLs/checksums/retention verified | Isolate, redact, revoke, and report incident |
| Timeline | UTC/uptime aligns with metrics within documented tolerance | Check NTP/timezone and collector delays |

Track **oldest retained event age, GC log bytes/hour, JFR write bytes/hour, JFR dump failures, volume used%, shipping backlog, collector CPU, latency overhead, and NTP offset**. Re-verify the budget after every change to JDK build, GC, `.jfc`, log verbosity, container limits, storage, traffic, or replica count.

## 13. Common Design Mistakes

| Mistake | Impact | Fix |
| --- | --- | --- |
| Enabling JFR only after the incident ends | Past data is lost | Continuous default ring, dump immediately on alert |
| Assuming `maxage=30m` always keeps 30 minutes | `maxsize` may evict older data sooner | Measure peak JFR rate and earliest-event time |
| Counting only JFR `maxsize` and ignoring exported files | Dumps fill the volume | Reserve space for repository + dumps + profile + headroom |
| Treating 80 MiB GC rotation as a fixed 8 hours | GC storms rotate much faster | Measure normal hours and peak load |
| Running `profile` continuously on every replica | High overhead/I/O | Default baseline, time-bounded `profile` with TTL |
| Placing GC/JFR on critical app data volumes | Exhausting quota harms the service | Dedicated volume and alerts |
| Omitting JVM start time | PIDs get reused | Pair instance/pod + PID + startup UTC |
| Pasting VM flags/args directly into tickets | Leaks secrets | Separate raw and redacted artifacts |
| Not verifying files actually open | Empty or corrupt files collected | `jfr summary`, checksums, readback |
| Missing JFR events interpreted as no issue | False negative conclusion | Check thresholds, `.jfc`, sampling |
| Turning on debug logging without an off-schedule | Shrinks retention and hits latency | Escalation with owner and rollback |
| Summing JFR durations across multiple threads | Inflates perceived request downtime | Align time windows, critical path, and interval overlap |

## 14. Deployment Checklist

**Pre-production**
- [ ] A diagnostic question is defined for every signal.
- [ ] JDK 21 build, collector, Xms/Xmx, instance identity, and NTP are properly selected.
- [ ] VM inventory captured once per session, with secret-handling procedures in place.
- [ ] GC logs with UTC+uptime, rotation, and measured bytes/hour.
- [ ] Default JFR disk recording with bounded `maxage`/`maxsize`.
- [ ] Budgets calculated for CPU, RAM, disk+export headroom, shipping/network, and retention per replica count.
- [ ] Policies established for permissions, retention, checksums, and ownership.

**Post-deploy**
- [ ] `VM.version`/`flags`/`uptime` match the intended JVM.
- [ ] GC logs produce files, meaningful rotation, and UTC-aligned timestamps.
- [ ] `JFR.check verbose=true` confirms `baseline` and settings.
- [ ] Tested a real `JFR.dump`, confirmed `jfr summary` opens it, and verified retained window.
- [ ] Alerts configured for quota, dump failures, and collector backlog.

**During an incident**
- [ ] Record symptom window, request p99/throughput, host/pod, and clock uncertainty.
- [ ] Dump the JFR ring before it rotates out; preserve GC logs for the same window.
- [ ] Attach VM snapshot/manifest, version, checksum, and ACL.
- [ ] Escalate profile/logs only with controlled duration, owner, and budget.
- [ ] Report any missing data intervals, return to baseline, and retain/delete per TTL.

## 15. Self-Assessment Exercises

1. A pod has 80 MiB GC logs, a 128 MiB JFR ring, one 128 MiB dump, and 128 MiB headroom. If you add a 180 MiB profile recording, what is the minimum capacity to budget? What items are still missing?
2. An 80 MiB GC log rotation writes 10 MiB/hour normally and 40 MiB/hour during a GC storm. Approximately what is the retention in each case, and why is it not fixed?
3. JFR has `maxage=30m` and `maxsize=128m`; at an event rate of 32 MiB/minute, roughly how many minutes of data actually remain? What change is safer than raising `maxsize` indefinitely?
4. Three pods share PID=1, and after a rolling restart PID=1 appears again. Design an artifact key that prevents mixing recordings.
5. If an alert fires at 10:20 and the dump occurs at 10:22, while the JFR ring only holds data from 10:18 onward, can you draw conclusions about 10:10? State the confidence level.
6. Explain why `VM.system_properties` must not be auto-pasted into tickets and how to grant permissions for raw vs. redacted versions.
7. Design an A/B experiment to measure combined overhead of GC logging + default JFR at 100, 500, and 1000 req/s; choose metrics and stop thresholds.
8. Design a trigger to save JFR when p99 breaches SLO that includes cooldown, quota, and copy count limits to prevent alert flapping from filling the disk.

**Completion criteria:** ability to read all three layers (VM info/GC log/JFR); calculate budgets and retention; verify empirically on JDK 21; and preserve pre-incident recordings, protect data, and escalate safely.

## 16. Java 21 Primary References

- [Oracle JDK 21 — jcmd: VM.version, VM.flags, VM.info, VM.log, JFR.start, JFR.dump, JFR.check](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — java: unified logging -Xlog, -XX:StartFlightRecording](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle JDK 21 — Flight Recorder Configurations: default.jfc, profile.jfc, and overhead](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html)
- [Oracle JDK 21 — jfr: summary, metadata, print](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — Diagnostic Tools: VM inventory and diagnostic utilities](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
