# Monitoring Log Capacity in Java Core Logging — Production Operations

## 1. Why monitor log capacity?

**Monitoring log capacity** means continuously observing how much storage resource logs are consuming, how fast they are growing, how much capacity remains, and whether the system is losing logs, exceeding quotas, or approaching an outage due to storage exhaustion. This is not just the question "is `app.log` large?", but a **multi-layered** problem: Java application → appender/console → filesystem or container runtime → shipper/collector → search backend → archive/backup.

When logs grow unexpectedly, an application incident can trigger an infrastructure incident:

- An exception loop continuously writing stack traces fills the disk; no space remains for new logs or temporary files.
- Disk pressure impacts databases and other processes on the same mount or node; in Kubernetes, it can lead to **Pod eviction**.
- The file logger fails to write while the application keeps running; subsequent errors leave no evidence for investigation.
- Collector lag causes queues/buffers to grow, retries increase traffic, and records may arrive late at the backend or be dropped according to drop policies.
- The index/backend runs out of quota or incurs rapid cost spikes even while the application's **local disk** still has free space.
- Misconfigured retention/rotation: archives are not cleaned up, or are deleted before the required audit retention period expires.

**Goal:** know the current state, forecast before exhaustion, identify the log-producing component, fire alerts with enough lead time to act, and curb growth **without accidentally deleting critical evidence**.

### Example scenario

~~~text
09:00   log directory = 5 GiB, filesystem usable = 20 GiB
09:05   log directory = 7 GiB, filesystem usable = 18 GiB
09:10   log directory = 9 GiB, filesystem usable = 16 GiB
...
09:50   log directory could reach 25 GiB if the rate stays the same
~~~

In the interval above, logs grow at roughly **2 GiB / 5 minutes = 0.4 GiB/minute**. If other workloads remain constant and that rate holds, the remaining 16 GiB only provides about 40 minutes to the theoretical 0 GiB mark; in practice, however, you must subtract **reserve capacity** and never wait until 0 to act. This is a trend estimate, not a filesystem guarantee.

## 2. Measure multiple capacity metrics, not just one file's size

| Metric | Meaning | Suitable measurement source |
| --- | --- | --- |
| `filesystem_total_bytes` | Total capacity of the filesystem storing logs | OS, host exporter, Java `FileStore` |
| `filesystem_usable_bytes` | Bytes **available** to the application/non-root user at measurement time | OS or `FileStore.getUsableSpace()` |
| `filesystem_unallocated_bytes` | Unallocated bytes on the filesystem | OS/Java `getUnallocatedSpace()`, distinct from `usable` |
| `filesystem_used_percent` | Usage across the entire mount, not just logs | Host filesystem metrics |
| `log_directory_bytes` | Total size of active + archived log files in the defined directory | Dedicated agent / bounded file inventory |
| `active_log_file_bytes` | Size of the file currently being written | Filesystem/file appender metrics |
| `archived_log_bytes` | Size of rotated and compressed files | File inventory / storage lifecycle |
| `log_bytes_written_total` | Cumulative log bytes emitted over time | Appender/agent instrumentation if actually present |
| `log_events_written_total` | Number of events written successfully | Counter instrumented at the sink, if available |
| `log_events_dropped_total` | Number of events dropped due to queue/filter/backpressure | Logger, appender, or collector depending on support |
| `collector_queue_bytes` / `collector_queue_size` | Backlog waiting to be forwarded | Collector/exporter/shipper metrics |
| `backend_ingested_bytes` | Log data received by the backend/index | Backend billing/ingest metrics |
| `backend_stored_bytes` | Storage size after indexing/compression/replication | Backend/index/storage metrics |
| `inode_free` | Number of free inodes/file entries (on inode-based filesystems) | Linux host metrics/`df -i` |
| `ephemeral_storage_used` | Pod/container temporary storage including logs, writable layers, emptyDir | Kubelet/CRI metrics |
| `retention_oldest_age` | Age of the oldest existing archive/record | Inventory/lifecycle job |

**Three numbers that are commonly confused:**

1. **Log bytes written by the application** do not equal the file bytes occupied on disk: output also includes timestamps, JSON envelopes, stack traces, and rotation may compress files. Appenders may buffer.
2. **File sizes in a directory** do not equal all space lost on the mount: the mount also holds image layers, DBs, temp files, journals, and **unlinked files still held open by a process** on Unix.
3. **Ingested or billed volume** does not equal disk storage volume: the backend may compress, index, replicate, and store snapshots; each layer must be measured according to the platform's policies.

For example, an app has only 2 GiB of archives while the filesystem is 95% full: the cause could be another workload, deleted-but-open files, container runtime logs in another path, or a volume quota—not necessarily a failing appender rotation.

## 3. Understand capacity, usable space, and quotas

In Java SE 17, `java.nio.file.FileStore` provides:

- `getTotalSpace()` — reported size of the file store, in bytes.
- `getUnallocatedSpace()` — number of unallocated bytes in the file store.
- `getUsableSpace()` — number of bytes available **to the current JVM** as reported by the system.
- `isReadOnly()` — read-only status of the file store.

These results are **point-in-time hints, not a guarantee that a write operation will succeed**. The OS, quotas, permissions, concurrent writers, reserved blocks, and mount/container differences can change the actual writable bytes immediately after reading.

~~~java
// Java 17 snippet: requires importing java.nio.file.Files, Path, FileStore.
Path logDirectory = Path.of("logs").toAbsolutePath();
FileStore fileStore = Files.getFileStore(logDirectory);
long total = fileStore.getTotalSpace();
long usable = fileStore.getUsableSpace();
long unallocated = fileStore.getUnallocatedSpace();
~~~

This is a **snippet**: the path must exist, and it can throw `IOException`/`SecurityException`; the full program in section 7 includes corresponding exploratory handling. Do not read `unallocated` and assume all those bytes are writable by the application user.

### Important measurement limitations in containers

If the JVM runs inside a container, `FileStore` may be measuring a mount exposed through an overlay filesystem or volume mount. The mount's total/usable numbers **do not necessarily reflect cgroup quotas, Pod ephemeral-storage limits, or storage backend quotas**. A Pod can be evicted for exceeding its ephemeral storage limit before the host mount bytes seen by the JVM drop low.

Therefore, measure simultaneously from **host/kubelet/container runtime**, **application file store**, and **backend**, as each layer has its own scope of authority. Do not use a single JVM metric as the sole source for all storage alerts.

### Inodes: free bytes remaining, yet file creation can still fail

On inode-based filesystems, a huge number of small log files can exhaust inodes even when byte capacity remains. When that happens, creating a new file can fail. On Linux, `df -i` shows inode usage; node-exporter exposes filesystem file-node metrics if the filesystem and collector support them. Java `FileStore` does not provide a portable API specifically for inode counts; an appropriate OS monitoring layer is required.

## 4. Log generation rate and time to exhaustion

**Current capacity** tells you how dangerous the situation is right now; **growth rate** tells you how much time you have to remediate. A system with 20% free space writing 10 GiB/minute can be more urgent than one with 10% free space growing very slowly.

Metrics to track:

- **`log_write_bytes_per_second`:** new log bytes pre- or post-compression under one consistent definition; do not mix two frames of reference.
- **`log_events_per_second`:** log records/second, by normalized service, level, or event type.
- **`log_directory_growth_bytes_per_second`:** change in directory size over time; can be negative during rotation/cleanup.
- **`filesystem_usable_bytes`:** usable bytes remaining on the mount, reflecting other workloads as well.
- **`time_to_exhaustion`:** estimated time to reach the reserve threshold based on the observed net consumption rate.

Approximate formulas:

\[
r_{\text{log}} = \frac{\Delta \text{bytes log}}{\Delta t}
\]

\[
T_{\text{reserve}} \approx
\frac{\max(0, \text{usableBytes}-\text{reserveBytes})}
     {\text{netConsumptionBytesPerSecond}}
\]

The second formula **only applies when the net consumption rate is positive and meaningful**. If the rate is 0 or negative, do not assume "infinite" time remains; rotation may be occurring, load may be temporarily low, metrics may be missing, or a burst has not yet appeared. Forecasts should be smoothed over a sufficient window, paired with peak rate, and alerted alongside absolute free-byte thresholds.

**Distinguish the two rates:**

1. `r_log` measures newly written logs, useful for detecting a service suddenly spamming errors.
2. `r_disk` measures the rate at which **filesystem usable space decreases**, including logs **and other writers**, already factoring in cleanup; more useful for forecasting node disk exhaustion, though it does not identify the cause.

Example:

~~~text
Usable = 5 GiB; reserve = 1 GiB; net consumption rate = 128 MiB/minute
Time to reserve ≈ (4096 MiB) / (128 MiB/minute) = 32 minutes.
~~~

If a 512 MiB/minute spike occurs, the time drops to 8 minutes. Do not take a single 5-minute data point as absolute truth; display the variance band and alert appropriately.

### Tracking trends across multiple windows

- 1–5 minutes: detects bursts/imminent exhaustion quickly, though noisy during rotation.
- 30–60 minutes: detects steady growth rates, yielding more reliable forecasts.
- 1–7 days: tracks business trends, hourly/daily peaks, and post-release shifts.
- Retention window: compares growth against deletion policies to see whether steady state is sustainable.

Track **peaks around deployments or production errors**, not just daily averages. An incident error loop can generate tens or hundreds of times more logs than normal traffic.

## 5. Capacity estimation and retention budgeting

A basic estimate:

\[
\text{raw bytes/day}
\approx \text{events/second} \times \text{bytes/event} \times 86400
\]

~~~text
100 events/s × 800 bytes/event × 86,400 s
= 6,912,000,000 bytes/day ≈ 6.44 GiB/day
~~~

If retained for 7 days at the same rate, raw payload ≈ **45 GiB**, before accounting for compression, active files, archive metadata, indexes, replicas, backups, headroom, or higher-traffic days.

Factors that skew estimates:

- Multi-line stack traces, frequent exceptions, messages containing large objects.
- JSON logs with repeated metadata and log-injection escaping.
- Compression ratios varying by payload.
- Index overhead and backend replica count.
- Log shipping replays/duplicates, ingest retries, differing retention policies.
- GB (10^9 bytes) vs. GiB (2^30 bytes) accounting, and whether the provider bills by compressed or uncompressed ingestion.
- Hot vs. cold storage duration, query cost, restore cost, and per-class retention.

**Do not use a single shared budget for all logs**: audit/security logs must be kept per approved policy; operational DEBUG logs can be much shorter. If the source appender deletes files when reaching `totalSizeCap`, it can delete audit logs prematurely if both log types are mixed. Separate pipelines and retention by classification.

## 6. Curb growth with rolling files, not just by "lowering the level"

### Logback Classic: size + time rolling

An example `logback.xml` configuration illustrating **general application logs**, not an audit/legal-hold policy:

~~~xml
<configuration>
    <appender name="APP"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>100MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>5GB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} [%thread] %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="APP"/>
    </root>
</configuration>
~~~

Key semantics per the Logback documentation:

1. `SizeAndTimeBasedRollingPolicy` creates archives by **date** (`%d`) and by **index** (`%i`) when the file reaches `maxFileSize`; both conversion tokens are required for this policy type.
2. `maxFileSize=100MB` is the rollover trigger threshold for the active file within a period, **not a guarantee that total logs will stay at most 100 MB**.
3. `maxHistory=7` with a daily pattern aims to keep roughly 7 periods of archives per the policy's rules; it does not delete an event at exactly 7×24 hours.
4. `totalSizeCap=5GB` caps **total archives managed by the policy**; **the active file is not part of the archives cap**. `maxHistory` is evaluated first, `totalSizeCap` second; cleanup can be asynchronous.
5. When the app writes rapidly during a burst, disk usage can exceed expected thresholds before rollover, cleanup, or compression completes. Do not treat config as an absolute firewall against disk exhaustion.
6. Each `totalSizeCap` only manages archives belonging to its policy; other files, temp files, Docker logs, shipper buffers, and backups still consume disk.
7. If you need to retain log types with longer retention obligations, **do not let the same policy delete them prematurely**. Audit logs should have independent storage/retention and evidence preservation.

If the application only needs to cap total archive bytes by time period, `TimeBasedRollingPolicy` with `maxHistory`/`totalSizeCap` may suffice; the combined size+time policy is used when you also want to bound individual file sizes. Configuration must match the actual Logback version in use.

### Log4j 2 and deletion policies

Log4j 2 provides `RollingFile`, size/time-based triggers, and a rollover strategy; you can configure a `Delete` action with conditions such as `IfLastModified` and `IfAccumulatedFileSize`. This is an **archive management tool**, not a controller for the entire filesystem. Sort order conditions, `basePath` scope, file patterns, and `testMode` must be carefully verified before enabling deletion in production.

Example **conceptual components**:

~~~text
RollingFile appender
  +-- SizeBasedTriggeringPolicy / TimeBasedTriggeringPolicy
  +-- rollover strategy
        +-- archived files
        +-- Delete action (basePath, IfFileName, IfLastModified...)
~~~

When executing cleanup, only match archive files within the defined directory and do not follow uncontrolled symlinks. Test with dry-run/testMode if supported by your version and configuration. In particular, never point a broad deletion rule at a directory that also contains audit logs or business data.

### Avoid two rotation systems controlling the same file

On Linux, an application might use `RollingFileAppender` while OS `logrotate` also rotates the same file. The two mechanisms can race on rename/truncate, leading to lost or duplicated logs, file descriptors writing to an old inode, wrong timestamps, or unexpected disk growth. Choose **one rotation owner** per file or design an explicit reopen protocol.

`logrotate copytruncate` can have a line-loss window because the file is still being written to during copy/truncate; use it only when the trade-off is understood and no better reopen mechanism exists. Do not treat logrotate as an audit durability mechanism.

## 7. Java 17 runnable: monitor filesystem and classify risk

The following example uses **JDK 17 only** to:

- Retrieve the `FileStore` for an existing directory and read total/usable bytes.
- Classify four **simulated** scenarios: OK, warning by time-to-reserve, critical, and unknown growth rate.
- Never delete, truncate, create files, or modify logging configuration.
- Print deterministic output for the simulated samples, along with **two booleans** checking whether the current environment can report capacity.

**Note:** This is a learning tool, not a metrics exporter or production disk-protection mechanism. Another process can consume space immediately after the check; quotas, inodes, or container limits can block writes even when the JVM reports free bytes.

Create **`LogCapacityDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

public class LogCapacityDemo {
    private static final long MIB = 1024L * 1024L;

    enum Risk {
        OK, WARNING, CRITICAL, UNKNOWN_RATE
    }

    static Risk assess(
            long totalBytes,
            long usableBytes,
            long netGrowthBytesPerMinute,
            long reserveBytes) {

        if (totalBytes <= 0
                || usableBytes < 0
                || usableBytes > totalBytes
                || netGrowthBytesPerMinute < 0
                || reserveBytes < 0
                || reserveBytes > totalBytes) {
            throw new IllegalArgumentException("invalid sample");
        }

        // Crossing the reserve threshold must prioritize a critical alert.
        if (usableBytes <= reserveBytes) {
            return Risk.CRITICAL;
        }

        // Not enough evidence to forecast time to disk exhaustion.
        if (netGrowthBytesPerMinute == 0) {
            return Risk.UNKNOWN_RATE;
        }

        long minutesToReserve =
                (usableBytes - reserveBytes) / netGrowthBytesPerMinute;
        if (minutesToReserve <= 15) {
            return Risk.CRITICAL;
        }
        if (minutesToReserve <= 60) {
            return Risk.WARNING;
        }
        return Risk.OK;
    }

    public static void main(String[] args) throws IOException {
        long reserve = 100 * MIB; // Learning threshold only.

        System.out.println("sample_ok="
                + assess(1000 * MIB, 800 * MIB, 10 * MIB, reserve));
        System.out.println("sample_warning="
                + assess(1000 * MIB, 500 * MIB, 10 * MIB, reserve));
        System.out.println("sample_critical="
                + assess(1000 * MIB, 130 * MIB, 10 * MIB, reserve));
        System.out.println("sample_no_growth="
                + assess(1000 * MIB, 500 * MIB, 0, reserve));

        // Observe only the file store of an existing path.
        Path directory = Path.of(
                args.length == 0 ? "." : args[0])
                .toAbsolutePath().normalize();
        FileStore store = Files.getFileStore(directory);

        System.out.println("filesystem_total_positive="
                + (store.getTotalSpace() > 0));
        System.out.println("filesystem_usable_nonnegative="
                + (store.getUsableSpace() >= 0));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LogCapacityDemo.java
java LogCapacityDemo .
~~~

**Stdout on a typical filesystem reporting positive total space and non-negative usable space:**

~~~text
sample_ok=OK
sample_warning=WARNING
sample_critical=CRITICAL
sample_no_growth=UNKNOWN_RATE
filesystem_total_positive=true
filesystem_usable_nonnegative=true
~~~

The four `sample_*` lines are **deterministic outputs for simulated data** and have been verified with JShell. The two filesystem lines depend on the environment: `FileStore` may report 0 total on special mounts, or throw `IOException` on invalid paths/permissions; there is no guarantee every machine prints `true` for both. The command above only reads filesystem metadata; it does not read file contents or delete data.

Program walkthrough:

1. `MIB` defines 1 MiB = 1,048,576 bytes; do not mix MB and MiB in calculations.
2. `assess(...)` takes a **net consumption rate already measured by the monitoring system** (simulated here); do not infer `netGrowthBytesPerMinute` from a single `FileStore` read.
3. `reserveBytes` is the reserve budget. In the sample, reserve = 100 MiB. With usable = 800 MiB, 70 minutes remain at 10 MiB/minute growth → `OK`; with 500 MiB, 40 minutes → `WARNING`; with 130 MiB, 3 minutes → `CRITICAL`.
4. If growth = 0 in one sample, `UNKNOWN_RATE` does not mean "no need to monitor"; metrics may be missing, logging may be temporarily quiet, or rolling may have just cleaned up.
5. `Files.getFileStore(directory)` reads the store for **an existing path**. To monitor a real log directory, pass the actual path after directory creation/deployment config and verify the mount is as expected. If a separate volume is used, it may differ from the filesystem of `"."`.
6. The code does not use `Files.walk(...)` to scan millions of log files. Measuring `log_directory_bytes` in practice requires an inventory/bounded scan or a dedicated agent, because scanning everything on a request thread can consume excessive CPU/I/O.
7. Production alerts should not be emitted by each JVM running a timer and printing warnings into **the very log file that is filling up**. Export telemetry via metrics/health endpoints or OS exporters so observability is decoupled from the failing filesystem.

**Scope note:** the classification logic in the demo uses **15 and 60 minutes purely for practice**; SRE teams must choose thresholds based on investigation/remediation speed, peak bursts, reserve headroom, and service requirements. Do not copy them as unapproved SLOs or hard requirements.

## 8. Prometheus and node-exporter: detecting imminent exhaustion

On Linux hosts running Prometheus `node_exporter`, common metrics include:

- `node_filesystem_size_bytes` — filesystem size.
- `node_filesystem_avail_bytes` — bytes available to non-root users.
- `node_filesystem_free_bytes` — free bytes on the filesystem; not necessarily equal to `avail`.
- `node_filesystem_files` and `node_filesystem_files_free` — total/free inodes or file nodes, when supported by the filesystem.
- `node_filesystem_readonly` — read-only status of the mount.

Example **PromQL** for a mount **confirmed to be the one containing logs** (replace `/var/log` if logs reside on a different mount):

~~~promql
100 * (
  node_filesystem_avail_bytes{mountpoint="/var/log"}
  /
  node_filesystem_size_bytes{mountpoint="/var/log"}
) < 15
~~~

This illustrates the condition "usable below 15%"; it does not claim 15% fits every system. If `/var/log` is not a separate mount point, the selector above may return **no series**; locate the exact mount of the directory (e.g., `/` or another volume) before using it. With `node_exporter`, filter out pseudo-filesystems/bind mounts and match `instance`, device, and `fstype` labels appropriately to avoid noisy alerts.

Forecasting space depletion via linear interpolation:

~~~promql
predict_linear(
  node_filesystem_avail_bytes{mountpoint="/var/log"}[1h],
  4 * 3600
) < 0
~~~

This query forecasts whether `avail_bytes` could drop below 0 within the next 4 hours based on the past 1 hour. It is a **linear estimate sensitive to rotation and bursts**, not a prophecy; combine it with a free-threshold condition, a minimum duration (`for` clause), and an alert for missing metrics. If `predict_linear` is skewed by a rollover that suddenly increases free space, the forecast can be misleading.

Example inode alert:

~~~promql
(
  node_filesystem_files_free{mountpoint="/var/log"}
  /
  node_filesystem_files{mountpoint="/var/log"}
) < 0.10
~~~

Apply this only when the filesystem provides valid file-node metrics and a positive denominator. Alongside `node_filesystem_avail_bytes`, it catches inode exhaustion that does not show up in free-byte counts.

### Measuring log write rate from the appender

If the application **actually instruments the counter** `app_log_written_bytes_total`, you can query:

~~~promql
sum by (service) (
  rate(app_log_written_bytes_total[5m])
)
~~~

The metric name above is **only a custom example**, not a default metric automatically emitted by SLF4J/Logback/JUL. You must define whether the counter measures bytes **before the encoder, after the encoder, or bytes successfully written**; measurements from different stages cannot be added interchangeably.

To detect fast/spiking logs, maintain separate counters for `log_events_written_total`, `log_write_errors_total`, and `log_events_dropped_total` with **low-cardinality** labels: service, level, appender/sink, and outcome. Do not put `requestId`, timestamped filenames, `userId`, or error messages into labels.

### Alert even when metrics are missing

No metrics does not mean the disk is safe. If the exporter/agent dies at the same time the filesystem fills up, charts may freeze and no alert will fire. Design separate alerts for **exporter down, scrape errors, and missing series**, and check collection lag and clock synchronization. The alerting path should not depend on the very log file under threat.

## 9. Docker: stdout/stderr can still fill the host

In Docker, Java applications often log to console, yet logs do not "disappear from disk." Depending on the logging driver, Docker stores stdout/stderr in the daemon's data area. With the `json-file` driver, if rotation is not configured, files can grow unbounded according to the active driver/version policy.

Example `daemon.json` for Docker Engine with `json-file`:

~~~json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
~~~

**Technical notes:**

1. `max-size` is the log-driver file rotation threshold, and `max-file` is the number of files retained; `log-opts` values in `daemon.json` must be **strings**.
2. New daemon default settings apply to **containers created after the configuration change**; running containers do not automatically adopt new rotation settings from a daemon restart alone. Inspect/recreate them per your deployment process.
3. `max-size=10m` and `max-file=3` only cap per driver and per container; they do not guarantee the host has enough space for **hundreds of containers**, images, and other volumes.
4. Docker's `local` driver supports rotation and compression by design. Choose a driver based on `docker logs` needs, existing collectors, and operability; do not switch solely because a file looks large without understanding the pipeline.
5. **Do not directly edit or delete Docker-managed JSON files with arbitrary tools**; Docker recommends letting the daemon manage them. External manipulation can cause unexpected behavior and make collectors lose their offset.

**If the JVM writes both to a `RollingFileAppender` on a volume and to console for the same event**, the two paths can create duplicates in the backend. That is a routing/ingest issue; distinguish both sinks before sizing capacity and billing.

## 10. Kubernetes: local ephemeral storage, container logs, and eviction

In Kubernetes, local ephemeral storage can be consumed by:

- Container writable layers.
- Container logs managed by the runtime/kubelet.
- Disk-backed `emptyDir` volumes.
- Temporary files or caches on the node.

The kubelet measures usage according to the configured filesystem/runtime layout. When a Pod or container exceeds local ephemeral storage limits, or the node filesystem enters disk pressure, the Pod can be **evicted** under the active rules. Nodes may track `nodefs`, `imagefs`, and `containerfs` depending on layout; these do not necessarily map to three physical disks.

Example container resource requests/limits for ephemeral storage:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: logging-demo
spec:
  containers:
    - name: app
      image: example/app:v1
      resources:
        requests:
          ephemeral-storage: "512Mi"
        limits:
          ephemeral-storage: "2Gi"
~~~

This manifest **illustrates structure**, not a deployable workload (the image `example/app:v1` is a placeholder). These limits help the kubelet/scheduler manage storage in supported layouts; they are **not dedicated disk space always reserved for you**, do not guarantee long-term log retention, and do not replace node disk-pressure alerts or rotation. Some filesystem configurations are not fully metered by kubelet ephemeral usage tracking.

**Do not monitor only `app.log` inside the container**: stdout may be stored elsewhere on the node. Sidecar collectors also have buffers/queues, writable layers, and `emptyDir` sharing the same budget. When multiple Pods share a node, their combined logs can push the node into eviction even if each app is below its individual threshold.

Observability sources:

- Node filesystem free bytes and free inodes/file nodes.
- Pod/container ephemeral storage usage, evictions, and kubelet events.
- Kubelet/runtime container log rotation settings.
- Collector queue depth, receiver/export errors, and whether receivers are reading the right sources.
- Impact on other node workloads during disk pressure.

Kubernetes is not a long-term audit store: local ephemeral storage has **no durability guarantee** when a Pod or node is lost. If logs have retention obligations, ship them to durable storage with an ACK/retention contract and test recovery.

## 11. Centralized backends and ingestion cost

Monitoring local capacity alone is insufficient if logs are forwarded to Elasticsearch/OpenSearch, Loki, cloud logging, a data lake, or another system. Each backend has its own constraints:

| Layer | Signals to monitor |
| --- | --- |
| Receiver/ingest | Records/bytes received, schema errors, rejected logs, rate limits |
| Queue/exporter | Queue depth, pending bytes, retries, backpressure, drops |
| Hot index | Index/storage bytes, shards/replicas, mappings, growth rate |
| Object storage/archive | Stored bytes, object count, lifecycle/retention, restores |
| Query | Latency, failed queries, cost, index/search limits |
| Billing | Ingested GB, stored GB-month, overages, and post-release changes |

**Ingest bytes** may be billed differently from **stored bytes** (compression, indexing, replicas); do not multiply a local disk figure to estimate your bill. Pull the actual billing metrics from your platform and reconcile by service/team/environment where supported.

Common pitfall: enabling `DEBUG` in a service to diagnose an incident and forgetting to turn it off a week later. Local logs rotated so the host stayed safe, but backend ingest/billing multiplied. Put in place:

- Bytes/event and records/s budgets per service/environment, compared before and after releases.
- Alerts when error logs or stack traces spike suddenly.
- Expiration deadlines and an owner responsible for disabling temporary `DEBUG`/`TRACE` toggles.
- Governance over high-cardinality fields and index labels to prevent search cost spikes.
- Separate retention for audit, security, application logs, and debug logs.
- Checks ensuring sampling/rate limiting does not drop mandatory security/audit events.

If a collector resends the same batch after a lost ACK, some backends may ingest duplicates. Costs and event counts can rise as well. Address this using the pipeline's delivery semantics and idempotency, rather than assuming free disk space means everything is fine.

## 12. Designing actionable alerts

No single threshold fits every environment; the table below is a **structural suggestion**, not a mandatory default.

| Signal | Early warning | Critical alert | What to check |
| --- | --- | --- | --- |
| Log mount free capacity | Usable below chosen warning threshold | Below absolute reserve | Are other workloads sharing the mount? |
| Time-to-reserve | E.g., under 4 hours in a steady trend | E.g., under 30 minutes or burn rate spiking | Did rolling/cleanup just run? |
| Available inodes | Steadily declining or low per policy | Critically close to inode exhaustion | Are there many small files? |
| App log output rate | Abnormally high vs. baseline | Rapidly rising, posing near-term risk | Error loop, debug toggle, payload logging |
| Queue/collector buffer | Backlog growing and not draining | Buffer/queue nearly full, drops/errors | Remote backend error or network issue? |
| Log write errors/drops | Starting to occur | Losing audit/critical events | Appender sync/async policy |
| Backend ingest cost | Consumption exceeding daily/weekly budget | Uncontrolled overage growth | New release, duplicate source, debug |
| Retention gap | Archives older than policy or deleted early | Missing audit records / hold violation | Lifecycle/config/permissions |

**Reduce alert noise:** use a `for` duration long enough to ignore isolated spikes; group by mount/service/sink; do not alert per file when thousands of archives exist. However, fast-moving hazards such as audit drops or a disk with only minutes left may require immediate alerting.

A disk alert can carry `severity=warning` and `critical` based on **absolute free bytes**, **free ratio**, and **time-to-reserve**. Do not rely solely on "disk > 90%" on a 20 TiB volume where 10% free is still huge; conversely, a 2 GiB volume at 30% free with logs writing 100 MiB/minute can be critical.

### Useful dashboards

A production dashboard should show:

1. Free bytes and free percentage by node/mount with 1-hour and 24-hour trends.
2. Directory/archive bytes by service where measurement is reliable.
3. Log events/s and log bytes/s by level, service, and environment.
4. Rolling/retention events, archive count/size, and free files/inodes.
5. Collector queues, retries, drops, rejected logs, and ingest latency.
6. Backend stored bytes, ingest bytes, billing, and retention.
7. Release/config changes near volume spikes (deploy version, `DEBUG` switch).
8. Links to the disk-pressure runbook, owners, and impact.

Do not use timestamped `filename`, `requestId`, `userId`, or `eventId` as metric labels: cardinality will explode. Store detailed metadata in **log events** for record-level investigation.

## 13. Runbook when logs nearly fill the disk

A practical procedure prioritizing **evidence preservation and service safety**:

1. **Confirm the mount:** identify the exact filesystem running low (`df -h`, `df -i` on Linux; host/container metrics) and where `app.log`/stdout/collector buffers actually reside. Being able to read a file inside a container does not prove its host storage location.
2. **Confirm the growth driver:** measure usage and bytes-per-second, correlate with deployment times, exception loops, and log-level changes. Separate app logs from DBs, temp files, and container images.
3. **Check logger config:** inspect `RollingFileAppender`, `maxHistory`, `totalSizeCap`, active files, and archived files; check whether rotation is failing or multiple loggers are writing to the same file.
4. **Check file count and inodes:** many small files can exhaust inodes. On Linux hosts, `du` helps locate large directories, though scanning huge directories consumes I/O; keep the scope narrow in production.
5. **Check deleted-but-open files:** on Linux, `lsof +L1` (with appropriate permissions) can find unlinked files whose descriptors remain open; disk space is not freed until the handle closes. Do not hastily kill a process if it serves critical business traffic.
6. **Reduce log generation at the source:** look for retry/exception loops, temporary `DEBUG`/`TRACE`, and payload logging; adjust levels or sampling only after understanding security/audit impact. Do not hide failures by turning off all `ERROR` logs.
7. **Clean up through the rightful owner:** prefer app- or daemon-managed retention/rotation. Do not blindly `rm` or truncate active files, archives under legal hold, Docker-managed JSON logs, or database files.
8. **Increase capacity/budget if needed:** expand the volume, increase reserve headroom, or shorten retention **per policy**; move logs to a dedicated volume where appropriate. Do not move logs to an unprotected mount just to gain space.
9. **Verify after remediation:** free bytes recover, write errors/drops stop increasing, collector backlogs drain, no audit logs are lost, backend queries still return logs, and alerts return to normal.
10. **Postmortem and prevention:** capture metric snapshots, root cause, whether alert thresholds caught it in time, config changes, owners, and burst tests to add.

### Why didn't deleting a file free disk space?

On Unix-like filesystems, when a file is **unlinked** while a process still holds an open file descriptor, its blocks remain allocated until the last descriptor closes. Running `rm app.log` removes the filename, but the appender keeps writing to the old inode; `df` does not show the expected free space, and normal path-based log access is lost. Verify with OS tools such as `lsof +L1` and manage the writer's lifecycle cleanly.

### Why avoid cleaning up with `truncate -s 0` directly?

Truncating an active file can destroy critical evidence and break the collector's offset/rotation assumptions, causing skipped or duplicated records. If emergency action is required, follow an approved runbook with proper backup/retention; it is better to curb the source, rotate via the owner, or expand capacity.

**Never delete audit logs just to reclaim space**, unless authorized by policy and the appropriate authority. Audit logs may be subject to legal hold or retention mandates; doing so destroys evidence without fixing the root cause.

## 14. Design mistakes that distort metrics

| Mistake | Consequence | How to avoid |
| --- | --- | --- |
| Watching only `app.log` size | Misses archives, stdout, collectors, Docker logs | Measure the full path and every real sink |
| Treating `FileStore.getUsableSpace()` as Pod quota | Over-trusts mount-level stats | Pair with kubelet/container/runtime metrics |
| Using `getUnallocatedSpace()` instead of usable | Overstates bytes the app is allowed to write | Use usable space when forecasting app capacity |
| Alerting only on "disk > 90%" | Misses burn rate or large drives with ample reserve | Combine free bytes, ratio, and ETA |
| Computing rate from two points across rotation | Sees negative growth and assumes risk is gone | Use longer windows and byte counters/host trends |
| Recursively scanning all logs every second | Creates self-inflicted I/O and CPU overhead | Use a dedicated agent, bounded scans, and sensible intervals |
| Confusing raw log bytes with backend billed GB | Inaccurate cost forecasts | Use actual ingest/storage billing metrics |
| Assuming `totalSizeCap` caps the whole disk | Active logs, temp, and other files are outside the cap | Alert on host mount, reserve, and separate audit/caps |
| Enabling both logrotate and RollingFile on one file | Races, duplicate logs, or lost logs | Assign a single rotation owner |
| Deleting open files on Linux | Space is not freed; logs become hard to access | Check open descriptors and handle the writer |
| Directly truncating Docker `json-file` logs | Breaks daemon management and collector offsets | Manage via the Docker log driver |
| Lowering log level without protecting audit | Loses evidence and compliance guarantees | Classify logs and protect the audit path |
| Seeing collector queue at 0 and assuming full delivery | Events may be dropped or the exporter may be down | Monitor drops, errors, received, and exported counts |
| Source file size grows while backend is missing logs | Drops, retries, parser failures, or misrouting | Reconcile counts across the pipeline |
| Not monitoring inodes | New file creation fails despite free bytes | Monitor inodes at the appropriate host layer |
| Using timestamped filenames as metric labels | High-cardinality explosion | Label metrics by service, sink, and mount |
| Testing only normal daily traffic | Fails under error bursts | Test incident loads and shutdown behavior |
| Treating rotation as valid audit retention | Premature deletion, lost holds and evidence | Maintain separate, verified storage lifecycle/retention |

## 15. Testing capacity monitoring systems

### Unit tests for logic

- `usableBytes` near and equal to reserve: does status differ properly according to `<=`?
- Zero log generation rate / missing metric: returns **insufficient data** status instead of dividing by zero.
- High growth rate exhausting reserve within 15 minutes: critical alert.
- Between 15 and 60 minutes: warning; beyond 60 minutes: OK under the demo's thresholds.
- Invalid total/usable values or negative numbers: validate inputs rather than computing garbage ETAs.
- Multi-filesystem systems: metrics must bind to the correct mount/path.
- Verify no code deletes files when it is only supposed to measure and alert.

### Integration tests for Java logging

1. **Rolling:** have the app write enough to trigger size-based rollover; verify archive names, compression, `maxHistory`, and `totalSizeCap` across a real lifecycle.
2. **Burst:** simulate continuous errors to spike the log rate; do alerts fire early enough, and does the appender experience I/O errors or drops?
3. **Full queue:** for async loggers/collectors, test block/drop/fallback policies and actual event counts received at the backend.
4. **Near-full disk in a test environment:** use a small test volume/container, never a production filesystem. Observe how the app handles write failures and whether metrics/alerts still function.
5. **Pod eviction:** verify kubelet reports ephemeral usage and the app ships logs durably before Pod termination.
6. **Docker rotation:** create a container with desired logging driver options; verify file count/size and behavior after recreate.
7. **Inode exhaustion:** create many small test files on a sandboxed filesystem with its own quota, without filling a real node.
8. **Retention:** audit archives are not cleaned up early; old application logs are cleaned per policy; hot storage and backups follow proper lifecycles.
9. **Recovery:** once disk is expanded or cleaned up, verify the collector queue drains, the appender recovers, and new logs are written and delivered.
10. **Alert routing:** verify exporter-down and missing-series cases also trigger alerts, not just low metric values.

### Metrics need clear contracts

If you instrument a Java appender yourself, clearly define whether `written_bytes` measures bytes **after the encoder and successful write** or estimated bytes from the message before formatting. Counting `log_events_total` at the logger API call site does not equal events actually written (filters, sampling, or backpressure may drop them). Reconcile producer, appender, collector, and backend using per-stage counters rather than assuming they must be strictly equal at every instant.

Beware of **recursive logging**: when an appender logs a "disk full" error into itself, the error can loop infinitely. A separate health/metrics/alert channel is preferred for reporting logging pipeline status.

## 16. Production readiness checklist

- [ ] Map every path logs travel through: files, stdout, Docker/kubelet, collectors, backends, and archives.
- [ ] Monitor free bytes, usable percentage, and inodes (where applicable) **on the exact mount**.
- [ ] Measure log throughput/second and growth trends, forecasting time-to-reserve rather than looking only at used capacity.
- [ ] Configure rotation/retention with a clear owner; `maxHistory`/`totalSizeCap` must not delete audit logs prematurely.
- [ ] Measure active files + archives + queues/buffers and isolate them from workloads sharing the disk.
- [ ] Check Pod ephemeral-storage, Docker logging-driver rotation, and Node disk pressure when running in containers.
- [ ] Set alert thresholds based on absolute reserve, time to intervene, bursts, and SLOs; detect exporter downtime.
- [ ] Track appender write failures/drops and collector rejections/retries/lag; do not infer complete logging from free disk space alone.
- [ ] Monitor backend ingest/storage/billing and post-release debug toggles.
- [ ] Maintain a safe disk-full runbook that avoids deleting open files or arbitrarily truncating Docker-managed logs.
- [ ] Test failure paths, inodes, bursts, rotation, retention, audit preservation, recovery, and alert delivery.
- [ ] Review capacity planning periodically against peak traffic and retention policies.

**Remember:** Monitoring log capacity is not just running `du -sh logs` or `df -h`. You must simultaneously **measure remaining writable bytes**, **log generation rate**, **time-to-reserve**, **archive/queue/backend capacity**, **write errors/drops**, and **retention constraints**. Combining the right measurement layers, controlled rolling, early alerts, and safe remediation procedures ensures logging supports operations instead of becoming the cause of a service outage.

### Official references

- Oracle Java SE 17 — [`java.nio.file.FileStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html), [`Files.getFileStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- Logback — [Rolling file appenders: `SizeAndTimeBasedRollingPolicy`, `maxHistory`, `totalSizeCap`](https://logback.qos.ch/manual/appenders-rolling.html).
- Log4j 2 — [Rolling file appenders and Delete actions](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html).
- Prometheus — [Monitoring Linux host metrics with node_exporter](https://prometheus.io/docs/guides/node-exporter/), [PromQL functions: `predict_linear`](https://prometheus.io/docs/prometheus/latest/querying/functions/).
- Docker — [Configure logging drivers](https://docs.docker.com/engine/logging/configure/), [JSON File logging driver](https://docs.docker.com/engine/logging/drivers/json-file/).
- Kubernetes — [Local ephemeral storage](https://kubernetes.io/docs/concepts/storage/ephemeral-storage/), [Node-pressure eviction](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/).
