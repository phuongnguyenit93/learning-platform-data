# System Logs, GC Logs, and Correlating Latency Spikes

## 1. The Problem: Why Does p99 Spike While Average CPU Stays Normal?

A Java application reads data from **Apache Cassandra** by partition key. For hours, API p99 latency stays around 40 ms. At 10:05 UTC, p99 spikes to 2 seconds, several `ReadTimeout` errors occur, and then latency subsides a few minutes later. The cluster-wide average CPU dashboard stays around 45%. Looking only at CPU or a few application `ERROR` lines makes it hard to know whether the issue lies in **JVM garbage collection (GC)**, the **SSTable/read path**, **compaction**, **disk**, **network**, or a specific **replica**.

In Cassandra, a query passing through a coordinator may require responses from multiple replicas. Even a single paused or congested replica can drive up tail latency, particularly when the consistency level (CL) needs that replica's reply. Conversely, spotting a "GC pause" line in logs near the incident timestamp **does not automatically prove GC was the root cause**.

This lesson walks through **correlating timestamped evidence** from:

- **System/application logs:** node lifecycle events, timeouts, dropped messages, flushes, compactions, repairs, and cluster status.
- **GC logs:** heap allocation/reclamation activity, *stop-the-world* (STW) pauses, and pause durations.
- **Metrics:** p50/p95/p99 latency, timeout counts, queues, heap, disk I/O, tombstone scans, and backlogs.
- **CQL tracing:** execution steps of **one selected query** across coordinator/replicas.
- **Client/Java Driver:** how long the request ran on the client, which CL, which coordinator, and which exception occurred.

**Goal:** read logs and time units accurately, construct a verifiable timeline, separate correlation from causation, test competing hypotheses, practice with `cqlsh`/`nodetool`/Java, and write evidence-backed incident reports.

> Scope: Cassandra running on the JVM with standard full replicas, e.g., under `NetworkTopologyStrategy`. Log file names, GC flags, JMX metrics, log wording, and tracing options vary across Cassandra/JDK versions. All log lines shown in this lesson are **illustrative examples**, not output measured from a live cluster.

## 2. Mental Model: Requests Traverse Multiple Latency Layers

Even on a table with partition key `(device_id, event_day)`, a read is more than a single file lookup:

~~~mermaid
flowchart TD
    A["Java client sends SELECT"] --> B["Network to coordinator"]
    B --> C["Coordinator selects replicas by token, RF, and CL"]
    C --> D["Replica: queue + CPU + JVM"]
    D --> E["Memtable / key cache / Bloom filter / SSTable"]
    E --> F["Disk read, decompression, version/tombstone reconciliation"]
    F --> G["Replica sends result or digest"]
    G --> H["Coordinator verifies and returns response"]
    H --> I["Driver reads pages, decodes, and app processes"]
    J["GC pause / heap pressure"] -.-> C
    J -.-> D
    K["Disk I/O / compaction / repair"] -.-> E
    L["Network / replica down"] -.-> B
    L -.-> G
~~~

End-to-end latency can be conceptualized in components:

~~~text
Client latency
  ≈ client/network time
  + coordinator wait/orchestration
  + replica wait/processing
  + response transfer and reconciliation
  + decoding/paging and app work included in the timer
~~~

This is a **conceptual decomposition**, not terms you can blindly add up from arbitrary metrics. Replicas execute **in parallel**, and speculative retries, paging, or timeouts may occur; never sum three replicas' times linearly.

### Averages Hide Tail Latency Incidents

| Metric | Meaning | Watch Out For |
| --- | --- | --- |
| **p50** | Half of requests finish at or below this threshold. | Can remain healthy even while a small fraction of requests stall badly. |
| **p95** | Roughly 95% of requests stay within this mark. | More sensitive to distribution tails than the mean. |
| **p99 / p99.9** | Captures the slowest requests by percentile. | Needs sufficient sample size; group percentiles cannot be averaged arbitrarily. |
| **Timeout rate** | Share of requests failing to complete before configured deadline. | Not every timeout is caused by GC. |
| **Throughput** | Requests/second in the same window. | Traffic bursts can build queues even before average CPU saturates. |

For example, out of 10,000 requests in a minute, 9,900 finish in 20 ms and 100 take 2,000 ms: **the vast majority remain fast**, yet the tail severely impacts users. Dashboards must retain **latency histograms, error counts, and request rates** over **the same time window**, never just an average.

## 3. What Can Each Log Type Tell You?

| Source | What to Look For | Limitations |
| --- | --- | --- |
| Cassandra **`system.log`** | Node lifecycle, gossip/topology, timeouts/dropped messages, warnings, flush/compaction/repair, disk or JVM-related events per version. | Log lines are signals/events; not every request is logged in detail. |
| **`debug.log`** (if configured) | Finer-grained traces to investigate specific mechanisms. | Can add significant I/O and log volume; never leave enabled cluster-wide indefinitely. |
| JVM **GC log** | Timestamp, GC type, pause duration, pre/post-GC heap, concurrent phases per configuration. | Cannot tell by itself which partition, query, or disk caused allocation pressure. |
| **Java client/driver logs** | Request start/end, coordinator if recorded, timeouts, retries, request ID, and CL. | Client time includes network, queues, paging, and app code. |
| **OS/storage logs & metrics** | Disk latency, I/O errors, saturation, OOM, network drops, container throttling. | Must be matched to the exact PID, node, and volume Cassandra actually uses. |
| **Tracing sessions** | Selected execution steps of a specific query on coordinator/replicas. | Not full distributed tracing of all app layers; carries overhead and TTL retention. |

### 3.1. Do Not Assume Identical Paths Across All Environments

Depending on installation:

- Cassandra may write logs to `logs/` under its install directory, `/var/log/cassandra/`, or **journald/stdout** in containers.
- GC logs may go to a dedicated file configured via JVM flags or stdout; some systems **do not enable detailed GC logging**.
- `system.log`, `debug.log`, and rotated archives have distinct retention rules; your analysis should record **node, Cassandra/JDK version, file path, and time range**.
- Logging configuration across versions typically involves **Logback** and JVM flags. Avoid mass-editing logging configs mid-incident before understanding reload behavior and impact.

**The log-reading commands below only illustrate usage on Linux hosts with authorized access**—real files may reside elsewhere:

~~~bash
# Search for errors, warnings, or timeouts in a verified system.log path.
grep -Ei 'timeout|dropped|overload|error|warning|compaction|flush' \
  /var/log/cassandra/system.log

# Inspect the tail in a lab environment.
tail -n 200 /var/log/cassandra/system.log

# When logs are routed to journald:
journalctl -u cassandra --since "2026-11-21 10:00:00" \
  --until "2026-11-21 10:20:00"
~~~

Adjust paths, service names, and **timestamp timezones** for the node being inspected. `grep` can miss relevant context when log phrasing differs; inspect surrounding lines around the incident window, not just lines containing `ERROR`.

## 4. Building a Reliable Timeline: Normalize Clocks Before Blaming Root Causes

This is the step most often skipped when claiming "GC appeared right when latency jumped."

### 4.1. Five Time Formats Not to Confuse

| Time Source | Characteristics | Alignment Rule |
| --- | --- | --- |
| Application logs | May use UTC, local timezone, or logger-specific format. | Record explicit zone; convert to UTC. |
| Cassandra system logs | Format/zone depend on logging config and host. | Verify offset; never guess from DC name. |
| Java GC logs | May print UTC with offset, JVM uptime since boot, or both. | If uptime is used, establish JVM start time and clock offset. |
| Metrics dashboards | Scrape timestamp, aggregation window, and sampling interval. | Distinguish **event time** from **scrape time**; finite resolution applies. |
| CQL tracing | Event timestamp, elapsed from session start, trace session ID. | Verify microsecond/millisecond units and emitting node clock. |

Modern JDK GC logs using **unified logging** (e.g., `-Xlog:gc*`) may print timestamps like `[2026-11-21T10:05:02.123+0000]` or uptime like `[12345.678s]` depending on decorators. Older JDK GC logs use different formats. **Uptime 12,345 seconds is not 12:34:05 UTC**.

### 4.2. Timestamp Synchronization Procedure

1. Anchor on the **UTC incident window** from client SLOs, e.g., 10:05:00–10:10:00 UTC.
2. Verify NTP/clock skew and timezones across **all involved nodes**, including Java clients, coordinators, and replicas. A 30-second clock skew on one node can invert apparent cause and effect.
3. Check log rotation: pre- and post-incident entries may live in different files.
4. Record **start timestamp, end timestamp, duration, node, and source** separately for each event.
5. Overlay data onto the same time window; keep both raw timestamps and normalized UTC marks.
6. Note **uncertainty bounds**: a 30-second metric scrape interval cannot prove exact ordering of two events 2 ms apart.

**Simulated** timeline example:

| UTC Time | Source | Event | Valid Conclusion |
| --- | --- | --- | --- |
| 10:04:40 | Application | Read p99 ~45 ms | Pre-incident baseline. |
| 10:05:01 | JVM N2 | GC STW pause 1.8 seconds | N2 paused Java thread execution during the pause window. |
| 10:05:01–10:05:04 | Client metrics | Read p99 2.1 seconds, timeouts climb | Temporally correlated with pause, not yet proof of sole cause. |
| 10:05:03 | Cassandra N1 | Some reads hit slow replica | Potentially tied to N2; inspect specific queries/endpoints. |
| 10:05:10 | N2 Metrics | Queues drain, p99 returns to baseline | Consistent with transient stall; still check I/O and traffic. |

**Stronger correlation** appears when the pause starts **before or during** the slowdown, requests actually depend on N2, queues build on N2, and p99 recovers right after the pause ends. **Weak correlation** occurs if GC happens on an unrelated node or disk I/O was already saturated beforehand.

## 5. Understanding GC Logs: Pauses, Concurrent Phases, and Heap Pressure

### 5.1. What Does GC Mean for Cassandra?

The JVM allocates many objects while handling requests, decoding payloads, assembling result sets, reading/writing, and running background tasks. The **garbage collector** reclaims unreferenced memory. Some GC phases require **stop-the-world (STW)**: JVM application threads pause during that interval. Other phases run **concurrently**, meaning the node is not completely frozen for their entire duration.

| GC Log Signal | General Meaning | Relationship to Latency |
| --- | --- | --- |
| **Young GC / evacuation pause** | Reclaims young generation; typically includes an STW pause. | Frequent or elongated pauses can add to p99 if they exceed request budgets. |
| **Mixed collection** (on supporting collectors) | Reclaims old regions alongside young in selected cycles. | Check pause distribution and post-GC heap occupancy. |
| **Full GC** | Broad collection scope; can involve major pauses depending on collector/version. | Investigate if paired with timeouts or repeating continuously. |
| **Concurrent mark/cleanup** | GC work running concurrently alongside application threads. | Do not treat the entire concurrent phase duration as an STW pause. |
| **Allocation failure / evacuation failure** | GC faces allocation or promotion pressure. | Signals heap pressure or excessive allocation rates. |
| **Post-GC heap remains high** | Many live objects remain or cannot be reclaimed yet. | Inspect trend, working set size, and retention causes. |

### 5.2. Illustrating How to Read a GC Log Line

~~~text
# SIMULATED example in JVM unified GC logging style:
[2026-11-21T10:05:01.100+0000][info][gc,start] GC(420) Pause Young (Normal)
[2026-11-21T10:05:02.900+0000][info][gc] GC(420) Pause Young (Normal) 5G->3G(8G) 1800.000ms

# Data points to extract:
collector_phase  = Pause Young
pause_duration   = 1800 ms = 1.8 seconds
heap_before      = 5 GiB (illustrative notation)
heap_after       = 3 GiB
heap_capacity    = 8 GiB
gc_id            = 420
node             = N2
~~~

**Do not conclude "Cassandra froze for 1.8 seconds due to insufficient heap" from a single GC line.** Long pauses can stem from collector choice, heap sizing, object graphs, allocation rates, CPU contention, cgroup throttling, or hardware stalls. You need historical trends and complementary metrics.

### 5.3. Distinguishing Heap from Off-Heap, OS Page Cache, and Container Memory

Cassandra also relies heavily on **off-heap/direct memory**, memory-mapped/index structures, and **OS page cache**. A half-empty JVM heap does not guarantee the node has no memory pressure; conversely, the OS using RAM for page cache is not a heap leak.

Signals to inspect together:

- Used/committed/max heap, allocation rate, and **heap after GC**.
- GC pause count/total duration, max pause, and p99 pause where samples suffice.
- Process RSS, direct/off-heap memory, cgroup/container memory limits, and OOM/throttling events.
- CPU user/system/steal, run queues, major page faults, and disk I/O latency.
- Collector flags, heap sizing, JDK version, and Cassandra version.

**Never resize heap or swap collectors mid-incident simply because GC appeared in logs.** JVM tuning requires baselines, version compatibility checks, and controlled testing; oversized heaps can worsen pauses, while undersized heaps trigger frequent GC cycles.

### 5.4. Commands for Inspecting GC

~~~bash
# Run on authorized nodes; verify syntax for your version.
nodetool gcstats

# Where JDK/OS permit and PID is verified:
jcmd <cassandra-java-pid> GC.heap_info
~~~

`nodetool gcstats` provides summary GC stats per version, helpful for spotting rising GC activity. `jcmd` heap-info commands can aid diagnosis; **never casually trigger full heap dumps or pause-inducing commands in production**, as they consume disk and stall traffic. `<cassandra-java-pid>` is a placeholder—never paste it literally.

## 6. Reading `system.log`: Finding Evidence That Supports or Refutes GC Hypotheses

In Cassandra, request failures can surface across multiple layers, and logs do not capture every request's full journey. When latency climbs, ask **which node, which operation, and which timestamp**.

| Event Group Potentially Seen | Hypothesis | Further Evidence to Check |
| --- | --- | --- |
| **Timeouts / dropped messages / overloaded** | A thread pool or replica fell behind. | `nodetool tpstats`, request rate, queues, GC, network, and disk. |
| **GC/pause-related warnings** | JVM pauses delayed responses. | GC log: pause start/end, duration, and alignment with query endpoints. |
| **Compaction/flush activity** | Disk I/O competing with reads/writes. | `compactionstats`, disk latency/IOPS, pending flushes, SSTable count. |
| **Tombstone / large partition warnings** | Replica scanning lots of dead data or oversized partitions. | Query shape, `tablestats`, tracing, `tablehistograms`, and partition model. |
| **Gossip / node down / topology** | Replica unavailable or routing shifted. | `status`, network latency, retries, CL, and coordinator. |
| **Repair/streaming events** | Sync tasks creating CPU/network/disk pressure. | `netstats`, repair logs, disk/network metrics. |
| **Filesystem errors / out-of-disk** | Write/flush/read path blocked or failing. | `df`, disk latency, kernel/storage logs, and physical volumes. |

**Simulated** example illustrating how to reason:

~~~text
10:05:01.050 UTC  [N1] WARN Request timeout for a read
10:05:01.200 UTC  [N2] INFO Compaction started
10:05:01.250 UTC  [N2] GC pause begins
10:05:03.050 UTC  [N2] GC pause ends (1800 ms)
10:05:03.100 UTC  [N1] WARN Replica response arrived late
~~~

Even though GC sits close to the read timeout, **the sequence above still needs validation**: are clocks synchronized? Was N1 actually waiting on N2? Did compaction already push disk latency up before GC started? Both **GC and latency could be downstream effects** of heavy allocation or compaction activity.

**Do not treat log severity as the sole gauge.** Important clues are often logged at `INFO` or `WARN`, while client p99 may spike before the server logs a single `ERROR`.

## 7. Correlating Logs with Cassandra Metrics

### 7.1. Diagnostic Command Suite on a Node

In lab/staging or with authorized production access:

~~~bash
nodetool status
nodetool info
nodetool gcstats
nodetool tpstats
nodetool compactionstats
nodetool netstats
nodetool proxyhistograms
nodetool tablestats telemetry_diag.events_by_device_day
nodetool tablehistograms telemetry_diag events_by_device_day
~~~

Exact command names, arguments, and outputs **depend on version**. If your cluster uses different syntax, run `nodetool help <command>` first.

| Command / Metric Group | What to Look For | How to Distinguish from GC |
| --- | --- | --- |
| `gcstats` and GC metrics | Do GC frequency/durations spike alongside the incident? | If GC is flat while disk latency climbs, prioritize I/O hypotheses. |
| `tpstats` | Pending/blocked tasks and dropped messages per thread pool. | High queues can stem from GC, overload, disk, or network; check timeline. |
| `compactionstats` | Active/pending compactions and backlog. | I/O contention can slow reads even without long STW pauses. |
| `netstats` | Streaming/handoff tied to topology changes or repair. | Saturated WAN/network causes timeouts even with healthy JVMs. |
| `proxyhistograms` | Coordinator-side latency distributions per command behavior. | Correlate with client latency, noting time windows/samples may differ. |
| `tablehistograms` | Table-level size/latency distributions per tool output. | If only one table is slow with dense tombstones, don't blame the whole JVM. |
| `tablestats` | SSTable count, disk space, partition/tombstone metrics, read/write stats. | Stale data/tombstones and overlapping SSTables inflate read work. |
| `status` | Which nodes/DCs/racks are up/down/joining. | CL may wait on failed replicas or skewed load distribution. |

`nodetool` values may be **cumulative totals since boot, instantaneous gauges, or decaying histograms**, depending on metric and version. Never subtract two counters to claim "the last request" without knowing their semantics. For histograms, check sample windows, request counts, and resets/restarts.

### 7.2. Minimum Dashboard to Establish Causality

Plot on **the same UTC time axis**:

1. **Application-side** request rate, p50/p95/p99, timeouts/unavailables/errors by query name and CL.
2. **Cassandra-side** coordinator read/write latency, timeouts, and dropped messages.
3. **Per-node** GC pause count, max pause, total pause time, and post-GC heap.
4. **Per-node/volume** CPU/GC CPU, process RSS, cgroup throttling, disk await/queue depth, free disk, and network latency.
5. Pending/active compaction, flushes, repair/streaming, hints, and SSTable/tombstone signals.
6. Node membership, DC/rack status, plus deploy, backup, and topology-change events.

**Never average node p99s** to represent cluster p99. If compatible histogram buckets exist, merge underlying distributions mathematically before computing quantiles; otherwise display per-node p99 or annotate the limitation. Avoid high-cardinality labels like `partition_key`, `request_uuid`, or `trace_id` on broad metrics to prevent monitoring overload and data exposure.

## 8. Four Common Hypotheses and How to Refute Them

### 8.1. Hypothesis A — Prolonged GC Pause

**Supporting signals:** p99/timeouts spike concurrently with a large STW pause on JVM N2; request queues pile up on N2 and drain right after the pause ends; traces/clients show requests waiting on N2.

**What to rule out:** Were disk/CPU/network already congested earlier? Was the GC phase concurrent rather than STW? Did N2 actually own the partition and participate under the request's CL?

**Action:** Trace sources of allocation/heap pressure, inspect JVM/GC config, batch/row sizes, and traffic—always testing tuning changes in a controlled environment against a baseline.

### 8.2. Hypothesis B — Compaction or Disk I/O Slowing Reads

**Supporting signals:** disk latency and I/O queues climb *before* p99; `compactionstats` shows a backlog; system logs show heavy compaction/flushes; GC pauses do not rise proportionally.

**What to rule out:** Did read/write throughput surge, is a disk failing, or are snapshots/streaming adding I/O? A compaction starting at that minute isn't necessarily guilty if disk utilization remains low.

**Action:** Check capacity headroom, compaction throughput limits, compaction strategy, partition sizes, concurrent maintenance, and load schedules; never force major compaction when disks are nearly full.

### 8.3. Hypothesis C — Tombstone Scans or Oversized Partitions

**Supporting signals:** only one query/table group is slow; tombstone warnings, high SSTable counts, or large partitions appear; tracing shows far more data scanned than rows returned.

**What to rule out:** Are there index/cache misses, skewed/hot partitions, or token-range scans instead of exact partition reads? Are GC pauses a side effect of large query allocations rather than an independent root cause?

**Action:** Redesign partition keys/bucketing around queries, bound clustering ranges, review TTL/delete patterns, and monitor tombstones/compaction. `LIMIT 10` **does not** guarantee the replica only inspects 10 items on disk.

### 8.4. Hypothesis D — Replica/Network Issues or Insufficient Quorum

**Supporting signals:** errors cluster on a specific DC/rack/node; network retransmits, node flapping, or gossip churn occur; `LOCAL_ONE` and `LOCAL_QUORUM` latencies diverge sharply.

**What to rule out:** Could the replica be slow due to GC or disk rather than network? Which replicas did the tracer select? Remember `LOCAL_QUORUM` at RF = 2 requires **both** replicas in that DC, unlike RF = 3 needing two of three.

**Action:** Investigate node/network/driver routing, verify RF/CL and repair status; **never drop CL hastily** without understanding impacts on consistency and durability guarantees.

| Prominent Signal | GC | Disk/Compaction | Tombstones/Partition | Network/Replica |
| --- | --- | --- | --- | --- |
| Long STW pause aligns with spike | Strong | Possible secondary factor | Possible from allocations | Non-specific |
| Disk await/queue rises before spike | Non-specific | Strong | Can co-occur | Non-specific |
| Tombstones scanned spike on one table | Non-specific | Can co-occur | Strong | Non-specific |
| Failures cluster on one rack/DC | Possible if JVM on that rack | Possible if disks on that rack | Less specific | Strong |
| p99 drops immediately after pause ends | Stronger if trace confirms | Still cross-check | Still cross-check | Still cross-check |

This table **guides investigation**, not automated root-cause classification.

## 9. CQL Tracing: Inspecting One Query Without Tracing All Traffic

### 9.1. Query-Aligned Lab Table

Assume a lab cluster with DC `dc1` and at least three active replicas:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_diag
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_diag.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  reading decimal,
  quality text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

`(device_id, event_day)` is a **composite partition key** determining token/replicas; `event_time, event_id` are clustering columns. Querying within a single partition and time range aligns far better with this design than scanning across all partitions.

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_diag.events_by_device_day
  (device_id, event_day, event_time, event_id, reading, quality)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:05:00Z',
   123e4567-e89b-42d3-a456-426614174001, 20.75, 'OK');

INSERT INTO telemetry_diag.events_by_device_day
  (device_id, event_day, event_time, event_id, reading, quality)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:10:00Z',
   123e4567-e89b-42d3-a456-426614174002, 21.10, 'OK');
~~~

### 9.2. Selective Tracing in `cqlsh`

~~~sql
TRACING ON;

SELECT event_time, event_id, reading
FROM telemetry_diag.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 20;

TRACING OFF;
~~~

`CONSISTENCY` and `TRACING` are **`cqlsh` commands**, not part of a CQL statement sent verbatim by the driver. After running the query, `cqlsh` displays the **Tracing session** along with events, hosts, and elapsed times depending on version and state.

Illustrative example of phases you might see (**not fixed verbatim output**):

~~~text
Tracing session: <trace-session-uuid>
Activity                                  Source     Elapsed
Execute CQL3 query                        N1         0 us
Sending READ message                       N1        50 us
Replica begins read                        N2       450 us
Reading from SSTables / merging results     N2       900 us
Sending response                           N2      1500 us
Request complete                           N1      2000 us
~~~

**Safe reading rules:**

1. `Source` indicates which node emitted the event; not every event comes from the coordinator.
2. `Elapsed` is typically measured from the trace session start in **microseconds**, unlike milliseconds on client dashboards.
3. Event presence does not mean all wait time was instrumented; seeing no GC event **does not prove GC did not happen**.
4. To align across nodes, cross-check session ID, timestamps/elapsed offsets, clock skew, and version-specific tracing semantics.
5. Trace records live in Cassandra's tracing tables with **retention/TTL and overhead**; never treat them as permanent storage for every request.

### 9.3. Can You Query Trace Sessions via CQL?

Where permitted and before traces expire, system tables such as `system_traces.sessions` and `system_traces.events` store session data depending on version:

~~~sql
-- Replace the UUID below with the real session ID returned by cqlsh/driver.
SELECT *
FROM system_traces.sessions
WHERE session_id = 123e4567-e89b-42d3-a456-426614174099;

SELECT *
FROM system_traces.events
WHERE session_id = 123e4567-e89b-42d3-a456-426614174099;
~~~

If a trace is missing, it may be due to TTL expiration, tracing not enabled/persisted, request timeouts, permissions, or version differences. Do not infer the query never ran. **Avoid enabling tracing on all production requests** because tracing itself generates extra mutations, I/O, and background load that can worsen incidents.

## 10. Java Driver 4.x: Measuring Client Latency and Capturing Trace IDs Selectively

Java applications should attach a **stable query name** (never full CQL containing sensitive values), measure latency with a **monotonic** clock, and log UTC timestamps to correlate with server logs. Example using Apache Cassandra Java Driver 4.x:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class TraceSlowRead {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement select = session.prepare(
                    "SELECT event_time, event_id, reading " +
                    "FROM telemetry_diag.events_by_device_day " +
                    "WHERE device_id = ? AND event_day = ? LIMIT 20");

            // ONLY in lab or for selected diagnostic requests.
            // Never enable continuous tracing on all production traffic.
            BoundStatement read = select.bind(
                    "device-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setTracing(true);

            Instant startedUtc = Instant.now();
            long startNanos = System.nanoTime();

            try {
                ResultSet rs = session.execute(read);
                ExecutionInfo execution = rs.getExecutionInfo();
                UUID traceId = execution.getTracingId();
                int rows = 0;
                for (Row row : rs) {
                    rows++;
                }
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - startNanos);
                System.out.println("query=events_by_device_day"
                        + " started_utc=" + startedUtc
                        + " cl=LOCAL_QUORUM"
                        + " status=success"
                        + " elapsed_ms=" + elapsedMs
                        + " rows=" + rows
                        + " trace_id=" + traceId);
            } catch (RuntimeException ex) {
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - startNanos);
                System.err.println("query=events_by_device_day"
                        + " started_utc=" + startedUtc
                        + " cl=LOCAL_QUORUM"
                        + " status=failure"
                        + " elapsed_ms=" + elapsedMs
                        + " exception=" + ex.getClass().getSimpleName());
                throw ex;
            }
        }
    }
}
~~~

**Interpreting results properly:**

- `System.nanoTime()` measures **duration**, not a UTC wall-clock timestamp. `Instant.now()` provides a timestamp for log alignment; keep the two concepts separate.
- The `for (Row row : rs)` loop may fetch additional pages (with larger data) and includes **client iteration**; instrument separately if you need first-response or per-page timing.
- `ExecutionInfo.getTracingId()` may return `null` if no trace ID was returned. It ties to the corresponding execution/page; never assume one ID covers an entire multi-page sequence.
- When a request times out, the client may receive no trace ID even though the server performed partial work. Timeouts **do not prove the request never executed**.
- In production, emit structured logs or metrics via your app's observability library tagged with `query_name`, `status`, CL, DC, and an app-generated request/correlation ID. Never use **per-request UUIDs** as Prometheus labels due to unbounded cardinality.
- `127.0.0.1` and `dc1` are lab placeholders only. Real systems must configure proper contact points, local DC, TLS/authentication, and timeout/retry policies.

**Warning:** this snippet uses `setTracing(true)` strictly for targeted diagnostic requests. For ongoing traffic visibility, rely on metrics and **sampling** rather than tracing every query.

## 11. Case Study: Reconstructing an Incident from Four Evidence Sources

### 11.1. Collected Data

Suppose from 10:00 to 10:15 UTC, 4,000 reads/s hit `telemetry_diag.events_by_device_day` with RF = 3 in `dc1` and CL = `LOCAL_QUORUM`.

| Source | Simulated Evidence |
| --- | --- |
| Application metrics | p50 = 24 ms, p99 jumps from 60 ms to 2.2 s at 10:05; `ReadTimeout` spikes. |
| GC log N2 | One **1.8-second STW pause** starts at 10:05:01 UTC; post-GC heap drops clearly. |
| Cassandra `tpstats` N2 | Read queue builds up and drains once the JVM resumes. |
| CQL tracing | Several slow requests show delayed replies from N2 during that window. |
| Disk metrics N2 | Disk await stays fairly flat with no matching I/O spike. |
| GC logs N1 and N3 | No long pauses around that timestamp. |

### 11.2. Formulating Hypotheses and Conditional Conclusions

**Strong hypothesis:** the STW GC pause on N2 delayed replica responses, impacting reads that depended on N2; p99 spiked while requests waited on N2 and recovered once N2 resumed.

**Unjustified conclusions:** "100% of timeouts were caused by GC," "GC was triggered by memtables," or "simply raising heap size will fix it." Further steps require checking allocation rates, post-GC heap trends across cycles, collector type, CPU throttling, and workload on N2.

One insightful detail: since `LOCAL_QUORUM` only needs two of three replicas and the coordinator often receives fast replies from N1/N3, **not every request waits on N2**. Replica selection, speculative retry, node readiness, and quorum timing explain why **p50 stays flat while p99 spikes**.

### 11.3. A Deceptive Correlation Case

Change the facts:

- `GC log N2` only shows long **concurrent marking phases** with STW pauses under 20 ms.
- Disk await on N2 climbed to hundreds of milliseconds **prior to 10:05**, with compaction/streaming active.
- Tracing shows prolonged SSTable read waits, while post-GC heap remains steady.

Here, prioritize **I/O contention and compaction**. Blaming GC merely because the word `GC` appears in logs is wrong: **concurrent phase duration is not a full-JVM pause**, and heavy disk I/O can simultaneously slow reads and indirectly perturb allocation/GC behavior.

## 12. Low-Risk Production Diagnostic Workflow

### Step 1 — Define Symptoms and Scope

Record **UTC start/end**, app/query name, CL, keyspace/table, DC/rack, affected nodes, p50/p95/p99, request rate, and error types. Distinguish **reads vs. writes** and **exact partition reads vs. scans**. Never blame one node from a cluster-averaged dashboard.

### Step 2 — Check Health and Recent Changes Around the Incident

Check node up/down status, app deployments, config changes, streaming/repair, backups, compaction, disk space, CPU, and network. If the entire cluster's p99 jumps together, inspect shared resources; if only one rack/node degrades, prioritize local faults or skewed traffic.

### Step 3 — Collect Logs from the **Right Nodes** and Normalize Timestamps

Preserve pre- and post-incident slices of system logs, GC logs, and application logs. Record JDK/Cassandra versions, timezones, NTP skew, and JVM start anchors if GC logs use uptime. Avoid filtering away context by looking only at `ERROR`.

### Step 4 — Place GC Alongside Latency and Queues

Identify **actual STW pauses** and their durations, pre/post-GC heap, and GC counts. Simultaneously compare `tpstats`, disk I/O, CPU, and coordinator/replica latency. **If GC does not overlap requests or pauses are tiny**, do not blame GC.

### Step 5 — Capture Selective Traces

Run a few representative queries in a lab or in production under approved sampling/permissions. Correlate trace ID, query name, coordinator, replicas, and event durations. Tracing adds overhead, so **never enable it across all traffic** while overloaded.

### Step 6 — Test Hypotheses Using Falsifying Evidence

Write at least **two competing hypotheses** and evidence that could refute each, for example:

| Hypothesis | Expected When True | Evidence That Weakens It |
| --- | --- | --- |
| GC slowed requests | Overlapping pause, queue buildup, trace waiting on that node. | Tiny/non-overlapping pause or on another node; disk/network saturated earlier. |
| Disk/compaction slowed requests | Disk await and compaction backlog align with spike. | Flat disk latency; only N2 JVM had a large STW pause. |
| Tombstone scans caused latency | Only one table/query slow; scanning many markers/dead rows. | Multiple tables slow together; tiny read payloads; zero tombstone pressure. |
| Replica/network caused timeouts | Errors tied to DC/rack, retransmits, node flapping, unmet CL. | Replicas healthy; slowdown tracks one batch query or JVM pause. |

### Step 7 — Remediate the Real Cause and Verify Post-Change

Assess action risk: shed/throttle query load, fix hot partitions/schema, tune compaction schedules, resolve disk/network bottlenecks, maintain replicas, or tune JVM **per runbooks and testing**. Avoid impulsive major compactions, heap dumps, concurrency hikes, or CL downgrades on a stressed cluster.

After changes, re-measure **identical metrics before vs. after** over multiple cycles: p99, error rate, throughput, GC pauses, post-GC heap, disk/queues, and client impact. Document remaining uncertainties in the report rather than overclaiming causation.

## 13. Dashboards and Alerts: What Should Be Monitored Continuously?

| Group | Suggested Metrics / Alerts | Why? |
| --- | --- | --- |
| **Client SLOs** | p95/p99 latency, timeout rate, request rate by query name + CL. | Detect user impact before hunting for internal causes. |
| **Cassandra coordinator** | Read/write/range latency, timeouts, unavailables, dropped messages. | Separate server-side request failures from app-layer time. |
| **JVM GC** | Max/p99 STW pause, total pause time per minute, post-GC heap, allocation rate. | Determine whether tail latency aligns with JVM pauses. |
| **Thread pools** | Pending/blocked/dropped tasks; read/write/flush pools per version. | Spot queue accumulation and stage congestion. |
| **SSTable / read path** | SSTable count, partition size, tombstones scanned, cache misses. | Identify oversized partitions or multi-version read overhead. |
| **Disk & maintenance** | Disk latency, IOPS, free space, compaction/flush/repair/streaming backlogs. | Separate I/O issues from GC and predict disk exhaustion risks. |
| **Replica / network** | Node membership, cross-DC latency, packet loss, failed repairs/hints. | Spot replicas failing to accept or reply to mutations in time. |

No universal GC pause threshold fits every system. An API with a **200 ms SLO** can be disrupted by a 300 ms pause, whereas a minute-scale batch workload behaves differently. Base alerts on **latency budgets, baselines, pause durations, frequency, and blast radius**, not merely `GC happened`.

A minimal incident report should contain:

~~~text
Incident ID:
UTC start/end:
Service, query name, CL:
Affected DC/rack/node:
Client p50/p95/p99, throughput, timeouts:
Server latency/queues:
GC phase, STW duration, heap before/after:
Disk/compaction/repair/network context:
Tracing session ID and replicas involved (if any):
Normalized timeline + clock uncertainty:
Primary hypothesis / alternatives / contradictory evidence:
Mitigation, result, follow-up, and owner:
~~~

## 14. Hasty Conclusions to Avoid

| Claim | True / False | Reason |
| --- | --- | --- |
| "GC appeared in the same minute p99 jumped, so GC caused it." | **False** | Must prove the pause impacted those requests and rule out disk/network/queries. |
| "Concurrent GC ran 5 seconds, so the JVM froze for 5 seconds." | **False** | Concurrent phases do not stop application threads for their full duration. |
| "Low average CPU means GC pauses cannot happen." | **False** | Brief STW pauses can spike p99 while average CPU stays moderate. |
| "One coordinator `ERROR` line tells you which replica is slow." | **False** | Need traces, endpoints, CL, and multi-node timelines. |
| "`LOCAL_QUORUM` requires every replica in the DC." | **False** | RF = 3 needs 2 ACKs; only RF = 2 needs 2/2. |
| "Cluster p99 = average of node p99s." | **False** | Percentiles cannot be added or averaged that way. |
| "`LIMIT 10` means Cassandra only reads 10 rows from SSTables." | **False** | Tombstones and stale versions can force scanning far more entries. |
| "Tracing every request is the fastest way to debug." | **False** | Tracing adds I/O and extra writes, potentially amplifying outages. |
| "JVM uptime GC timestamps align directly with UTC clock." | **False** | Must convert via JVM start time or wall-clock decorators and verify clocks. |
| "A write timeout means zero replicas applied the write." | **False** | Some replicas may have applied the mutation; the client just missed enough ACKs. |
| "A UTC timeline and falsifiable hypotheses make diagnosis reliable." | **True** | Reduces mistakes from clock skew and confirmation bias. |

## 15. Self-Check Exercises with Answers

**Exercise 1.** Application p99 jumps from 50 ms to 1.5 seconds at 10:00 UTC. Node N2's GC log shows a 4-second `Concurrent Mark` phase, yet the longest STW pause is only 10 ms. Is there enough evidence to blame GC?

**Answer:** **No.** Concurrent phases do not freeze the entire JVM. Check CPU/disk/queues/traces and any real STW pauses overlapping the requests.

**Exercise 2.** One node logs GC timestamps as `[12345.678s]`, while application logs print `2026-11-21T10:05:01Z`. Can you compare those two numbers directly?

**Answer:** **No.** That GC timestamp is JVM uptime; you need the JVM start time and clock offset to convert it to wall-clock/UTC.

**Exercise 3.** On an RF = 3 cluster in `dc1`, `LOCAL_QUORUM` reads need two replica responses. N2 suffers a 2-second STW pause, yet p50 stays healthy while p99 spikes. Why?

**Answer:** Not every request waits on N2: the coordinator often completes quickly using the other two replicas. Requests that wait on N2 or hit delays on related coordinators/replicas form the distribution tail.

**Exercise 4.** System logs report dropped messages and `tpstats` shows rising pending read tasks. Can you conclude the root cause is JVM GC?

**Answer:** **Not yet.** Queues/dropped messages result from many bottlenecks: GC, disk, hot partitions, traffic surges, or network issues. Correlate GC logs, OS metrics, traces, and request rates.

**Exercise 5.** Two nodes have p99 of 100 ms and 1,000 ms, handling 9,900 and 100 requests respectively. Is cluster p99 equal to `(100+1000)/2 = 550 ms`?

**Answer:** **No.** Aggregate p99 depends on the full request-weighted distribution; node p99s cannot be averaged. Merge underlying histograms/datasets properly.

**Exercise 6.** Tracing a `SELECT` shows SSTable reads took long, while node GC pauses stay steady. What else should you check?

**Answer:** Disk await/IOPS, compaction/streaming, SSTable counts, tombstone scans, partition sizes, cache hit rates, and query shape (exact partition vs. scan).

**Exercise 7.** While p99 is spiking, a team plans to turn on `TRACING ON` for every request across all applications. What is the risk?

**Answer:** Tracing creates additional mutations, I/O, storage, and CPU load, risking further overload. Take small controlled samples and prioritize metrics/logs first.

**Exercise 8.** After adjusting the compaction schedule, p99 drops; can you state compaction was 100% the root cause?

**Answer:** **Not necessarily.** Traffic, GC, or node health may have shifted concurrently. Compare before-and-after metrics, timelines, control groups if feasible, and evidence refuting alternative hypotheses.

## 16. Decision Flowchart When Latency Rises

~~~mermaid
flowchart TD
    A["Cassandra API p99/timeouts rise"] --> B["Identify query/CL, UTC window, node/DC"]
    B --> C["Correlate client metrics, system logs, GC logs, and OS metrics"]
    C --> D{"Long STW GC pause overlaps requests/replicas?"}
    D -->|Yes| E["Inspect queues, heap, allocation, and pause causes"]
    D -->|No / inconclusive| F["Measure disk, compaction, tombstones, and network"]
    E --> G{"Tracing/metrics confirm slow node is on request path?"}
    F --> G
    G -->|Yes| H["Prioritize hypothesis backed by multiple sources"]
    G -->|No| I["Gather more evidence; check clock skew"]
    I --> C
    H --> J["Mitigate per runbook; avoid heavy load-inducing ops"]
    J --> K["Re-measure p99, timeouts, GC, disk, queues; document conditional findings"]
~~~

**Key takeaway:** system logs show **what events occurred**, GC logs reveal **whether and how long the JVM paused**, and metrics/tracing show **which requests and execution stages slowed down**. Only by aligning all sources on a **unified timeline accounting for timezones and clock skew**, mapping to the **exact coordinator/replicas and CL**, and testing competing hypotheses can you establish whether GC, disk, tombstones, compaction, or network contributed to latency. The goal of diagnosis is **evidence-based service recovery**, not hunting for a single log line to blame.
