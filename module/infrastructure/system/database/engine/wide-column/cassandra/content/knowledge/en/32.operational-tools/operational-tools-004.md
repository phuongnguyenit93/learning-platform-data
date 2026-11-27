# nodetool tpstats/compactionstats/netstats and Background Activity in Apache Cassandra

## 1. Why Inspect Background Activity When Cassandra Slows Down?

Apache Cassandra is a distributed **wide-column** database that shards partitions by **partition key** and stores multiple replicas per its replication strategy. When a Java application runs `SELECT` or `INSERT` at a given consistency level, the coordinator interacts with replicas. Simultaneously, Cassandra must sustain several background tasks: **memtable flushes, SSTable compaction, hinted handoff, repair, streaming during bootstrap/rebuild, and internal message processing**.

These background tasks are essential for cluster durability and stability, yet they can contend for **CPU, memory, disk I/O, network, and thread pools** with user reads and writes. Consequently, a node reporting `UN` in `nodetool status` can still suffer read/write timeouts if queues grow or disks saturate.

In the **Operational Tools** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module, three commands are particularly valuable:

- **`nodetool tpstats`**: observes internal executors/thread pools, queues, and certain dropped message counters.
- **`nodetool compactionstats`**: observes active compaction tasks and queued compaction work.
- **`nodetool netstats`**: observes data transfer via **streaming** and related details depending on version.

None of these commands alone concludes "the cluster is healthy" or "this table is broken". This lesson teaches how to **combine the three perspectives** with latency, storage, replication, and logs to diagnose root causes accurately.

### Expected Outcomes

After this lesson, you will be able to:

1. Distinguish **Active, Pending, Completed, Blocked, and Dropped** counters in `tpstats`.
2. Understand why **pending compactions** grow, and read progress/volume in `compactionstats`.
3. Distinguish **SSTable streaming** in `netstats` from normal CQL requests.
4. Build an investigation timeline for p99, timeouts, and disk/network bottlenecks without making unfounded configuration changes.
5. Use CQL and the Java Driver to correlate query shape and consistency level with operational tools.
6. Recognize data boundaries across **Cassandra versions** and avoid dangerous interventions.

## 2. Three Commands, Three Different Questions

| Command | Primary Question | Typical Output Metrics | What the Command Does Not Prove |
|---|---|---|---|
| `nodetool tpstats` | Which executors are busy, are queues building up, or are messages being dropped? | Active, Pending, Completed, Blocked, All time blocked; dropped message counts | Does not directly report disk IOPS, per-query latency, or the origin of all errors |
| `nodetool compactionstats` | Which compactions are running, how are they progressing, and how much work is pending? | Pending tasks, job type/source, processed/total bytes, progress depending on version | Does not measure overall disk health or guarantee when the backlog will drain |
| `nodetool netstats` | Is the node sending or receiving **streaming** data flows? | Mode, send/receive streaming sessions, files/bytes, progress; extra stats depending on version | Does not measure all CQL, gossip, or replica messaging network traffic |

These commands run against **the node being inspected**, typically over JMX or the corresponding management interface. One snapshot on node A **does not replace** observing nodes B and C, especially if one replica is the bottleneck.

### Interaction Diagram

~~~mermaid
flowchart TD
    A["Java API: read/write p99 rises"] --> B["Measure by query, CL, DC, and time"]
    B --> C["nodetool tpstats: pools/queues/dropped"]
    B --> D["nodetool compactionstats: compaction backlog"]
    B --> E["nodetool netstats: active streaming"]
    C --> F["Cross-check disk, CPU, GC, and network"]
    D --> F
    E --> F
    F --> G{"Which bottleneck do metrics confirm?"}
    G --> H["Shed pressure safely or fix root cause"]
    H --> I["Re-measure p95/p99, throughput, and error rate"]
~~~

**Do not infer causality simply because two graphs rise together.** For example, `Pending` rising while streaming runs does not prove streaming is the sole cause. You must also inspect disk throughput/latency, CPU, and incoming request volume.

## 3. Preflight for Operational Tools

Before running diagnostics in production:

- Confirm the **Apache Cassandra version, packaging, and `nodetool` version**; field names, output formatting, and flags can vary.
- Identify which node has the issue, its **datacenter/rack**, keyspace/table, replication factor (RF), and request consistency level (CL).
- Identify the metric source: **local node**, coordinator, a replica, or a cluster-aggregated dashboard.
- Prefer **read-only status** commands and take several readings at clearly recorded timestamps.
- Ensure operators have JMX permissions and no firewall/auth misconfiguration blocks access; a `nodetool` connection failure does not automatically mean Cassandra is down.
- Record UTC time, hostname, JVM uptime/most recent restart, traffic rate, error rate, and p95/p99.

Example initial command set:

~~~bash
# Check version, node state, and available nodetool commands.
nodetool version
nodetool status
nodetool help

# The three main views covered in this lesson.
nodetool tpstats
nodetool compactionstats
nodetool netstats
~~~

If a syntax is rejected, run `nodetool help <command>` on that exact node. **Do not copy flags from another version without verifying.**

## 4. `nodetool tpstats`: Thread Pools, Queues, and Dropped Messages

### 4.1. Why Does Cassandra Have Multiple Stages?

Cassandra processes requests through multiple executor groups or **stages**, such as groups handling reads, mutations, flushes, compactions, and internal tasks. A stage has worker threads executing scheduled tasks and may have a queue holding pending tasks.

Logical flow:

~~~text
Incoming request / message
       |
       v
  Executor queue   <-- Pending
       |
       v
  Worker threads   <-- Active
       |
       v
  Task finished    <-- Completed increments
~~~

If incoming work exceeds processing capacity for long enough, **Pending** can grow. However, a growing queue does not explain *why*; workers may be blocked waiting on disk, CPU, locks, or network, or traffic may simply have spiked.

### 4.2. How to Read Each Column

| Common Field | Interpretation | Investigation Notes |
|---|---|---|
| **Pool Name** | Name of the reported stage/executor | Exact pool list and names differ by release |
| **Active** | Tasks currently executing at snapshot time | High Active is not inherently bad if throughput scales accordingly |
| **Pending** | Work queued but not yet picked up by a worker | What matters is the **trend** and how long the queue stays elevated |
| **Completed** | Total tasks completed within the metric/counter scope | Usually a cumulative counter; compute deltas over time rather than treating as instantaneous rate |
| **Blocked** | Tasks blocked by queue admission capacity or executor limits per version semantics | Does not mean "how many TCP connections are waiting on the network" |
| **All time blocked** | Cumulative counter for blocked tasks | Must consider resets/restarts and rate of increase, not only absolute value |

In the **Dropped Messages** section, output can show dropped message counts by type (such as read-related, mutation-related, or other internal message paths). Names and accounting vary by version. **Dropped** differs from **Pending**: a message may have been discarded past its deadline/path constraints, whereas Pending is work still sitting in a queue.

### 4.3. Illustrative Output Example

~~~text
Pool Name                Active  Pending   Completed  Blocked  All time blocked
ReadStage                    8      350     9800000        0                 0
MutationStage                4       12    12100000        0                 0
MemtableFlushWriter          2      120      180000        0                 0

Message type                                    Dropped
READ                                               75
MUTATION                                            3
~~~

These are **hypothetical numbers**, not exact output across all Cassandra versions. Do not build brittle parsers tied to stage or message-type names from this example.

How to form hypotheses:

- `ReadStage Pending=350`: there is a read-processing backlog; check whether it grows or shrinks over the next minutes alongside read p99.
- `MutationStage Pending=12`: there is a write queue, though you cannot yet conclude it causes timeouts.
- `MemtableFlushWriter Pending=120`: there may be a flush backlog; cross-check `compactionstats`, commitlog usage, and disk latency.
- `READ Dropped=75`: check whether this counter is **actively rising** while read timeouts rise; 75 could be stale residue since node startup.

### 4.4. Comparing Two Snapshots to Compute Deltas

Suppose on the same node, 60 seconds apart:

| ReadStage Metric | 10:00 | 10:01 | Interpretation |
|---|---:|---:|---|
| Active | 6 | 8 | Workers busier |
| Pending | 100 | 1,300 | Backlog grew by 1,200 |
| Completed | 1,000,000 | 1,012,000 | Completed 12,000 more tasks in 60 s |
| READ dropped | 10 | 130 | 120 more dropped messages |

Observed completion rate:

~~~text
(1,012,000 - 1,000,000) / 60 s
= 200 completed tasks / second
~~~

A stage's `Completed` counter **does not necessarily match CQL request counts**; one request can spawn multiple internal tasks. Never use it as an absolute API QPS gauge.

From the figures above, you can conclude **the queue is growing and dropped messages are rising**, but to know why, you must inspect CPU/GC, disk latency, query shape, replica timeouts, and background tasks. Never deduce directly that you lack `1,200 / 60 = 20` threads/second or blindly scale worker counts by that ratio.

### 4.5. Pitfalls When Reading tpstats

1. **Summing Pending across different pools** can be meaningless since one request can enqueue tasks in several stages.
2. **Completed is cumulative**, not QPS; compute deltas and verify the counter did not reset via restart.
3. **High Blocked** does not necessarily mean CPU lock contention; understand the executor's semantics.
4. **Dropped messages do not map 1:1 to failed client requests.** A request can involve retries, multiple replicas, and timeouts.
5. **Pending=0 at one instant** does not rule out high tail latency caused by one slow replica, network jitter, or I/O.
6. **Consistently high Active** can be normal for a busy stage as long as queues and p99 stay stable.

### 4.6. When to Investigate ReadStage or MutationStage

| Signal | Hypothesis | Next Checks |
|---|---|---|
| ReadStage Pending rises with read p99 | Read overload, wide/hot partitions, slow disk | Query shape, `tablehistograms`, SSTables per read, disk I/O |
| MutationStage Pending rises with write timeouts | Replicas processing mutations slowly or overloaded | Commitlog sync, disk, network, write CL, CPU/GC |
| Flush stage Pending stays elevated | Flushes falling behind writes; slow data disk | Commitlog disk usage, SSTable writes, compaction |
| Dropped messages rise while node is still `UN` | Queue/latency or message handling overloaded | Logs, timeouts, dropped by type, resource saturation |
| Pending high on only one node | Hotspot or local node fault | Partition distribution, node CPU/disk, DC/rack |
| Pending rises on all nodes | Broad traffic surge, new deploy, or shared dependency | QPS, concurrency, client retries, background tasks |

## 5. `nodetool compactionstats`: Backlog and Active Work

### 5.1. What Does Compaction Solve?

Cassandra writes data into memtables and flushes them to **immutable SSTables**. Over time, overlapping SSTables cause read amplification, while tombstones and stale updates must be reconciled safely. **Compaction** reads source SSTables, merges data, and writes new SSTables.

Compaction is background work that **consumes disk reads, disk writes, CPU, and temporary disk space**. If write traffic creates SSTables faster than compaction can merge them, SSTable counts climb, degrading read latency and disk consumption.

~~~mermaid
flowchart LR
    A["Memtable flush"] --> B["Multiple immutable SSTables"]
    B --> C["Pending compaction tasks"]
    C --> D["Read source SSTables"]
    D --> E["Merge / reconcile"]
    E --> F["Write new SSTable"]
    F --> G["Release old SSTables when eligible"]
    H["Repair / streaming / client I/O"] -. resource contention .-> D
    H -. resource contention .-> F
~~~

### 5.2. compactionstats Output

~~~bash
nodetool compactionstats
~~~

Depending on version, output may include:

- **Pending tasks**: queued compaction work in the relevant tracking structures.
- Active tasks: job type, keyspace/table, task ID, completed bytes, and estimated total bytes.
- Progress/throughput/estimated remaining time if provided by the version/tool.

**Pending tasks is not the SSTable count.** A single task may process multiple SSTables, and internal task types vary in cost; never multiply pending count by a fixed size to guess remaining bytes or minutes.

**Illustrative** example:

~~~text
pending tasks: 22
id       compaction type    keyspace  table                   completed   total
task-01  COMPACTION         telemetry events_by_device_day   24 GiB      80 GiB
task-02  COMPACTION         telemetry readings_by_device    12 GiB      15 GiB
~~~

Do not use this example as a parsing template because actual output varies across versions.

### 5.3. Why Does the Compaction Backlog Grow?

Common causes:

- **High write/flush rate**: new SSTables are created faster than they can be merged.
- **Heavy updates and deletes**: historical versions/tombstones increase merge work.
- **Mismatched compaction strategy** for the workload (e.g., wrong choice among STCS/LCS/TWCS).
- **I/O contention** with streaming, repair, flushes, and application reads/writes.
- **Disk nearly full**, lacking headroom to write output SSTables before releasing old ones.
- **CPU/compression** slowing tasks or underlying I/O errors.
- **Oversized partitions** or large SSTable counts creating uneven load.

Never see `pending tasks=100` and conclude "double `concurrent_compactors` immediately". If disks are already saturated, higher concurrency can slow tasks further and worsen client p99.

### 5.4. Check Evidence Before Tuning

A sound investigation sequence:

1. `compactionstats`: is the backlog growing across multiple samples? Are active tasks making progress?
2. `tpstats`: are related executor queues rising? Are Read/Mutation stages impacted?
3. `tablestats` or `tablehistograms`: how are SSTable count, read latency, and SSTables per read looking on affected tables?
4. Disk telemetry: read/write throughput, await/p99 disk latency, free bytes, IOPS, and controller throttling.
5. Logs: I/O exceptions, compaction errors, pauses, or shutdowns.
6. Background activities: are repair/streaming jobs running against the same storage?

If pending is high yet **draining steadily** while disk/CPU and client SLOs remain healthy, it may simply be normal catch-up after a burst. If pending climbs continuously, active tasks stall, and free disk shrinks, the risk is much higher.

### 5.5. Temporary Space Needed During Compaction

During compaction, Cassandra must typically retain **old SSTables** while writing **new SSTables** before safely releasing the old files. Hence:

~~~text
Required disk headroom
≈ temporary output SSTable size
  + concurrent flush/streaming/repair activity
  + normal data growth
  + cluster safety margin
~~~

Do not treat this formula as an exact sizing guarantee: compaction strategies (STCS/LCS/TWCS), tombstones, compression, and snapshots all play a role. Measure actual disk consumption and job schedules.

### 5.6. Compaction Can Be Throttled

Some releases expose controls to view or adjust compaction throughput or concurrency (e.g., `nodetool` commands like `getcompactionthroughput`/`setcompactionthroughput` where supported).

**Never raise or lower limits haphazardly.** Lowering the throttle can free I/O for queries short term while letting SSTable backlog pile up. Raising throughput can drain backlog faster while hurting p99 or exhausting disk headroom. Every change needs approval, baseline, and rollback; this lesson uses read-only commands only.

## 6. `nodetool netstats`: Streaming, Not Every TCP Packet

### 6.1. What Activity Is Streaming?

**Streaming** is the internode data-transfer mechanism commonly used during:

- **Bootstrap/add node**: a new node receives token ranges and initial data.
- **Rebuild/replace/decommission/topology change**: handing off data responsibility.
- **Repair**: in phases where differences must be synchronized via streaming.
- Other recovery or data-movement workflows depending on version.

Streaming transfers data at the **SSTable or storage-unit level**, distinct from normal CQL reads/writes. It can drive **high network throughput and heavy disk I/O** without any increase in client requests.

### 6.2. Reading netstats

~~~bash
nodetool netstats
~~~

You may see:

- **Mode** such as NORMAL or operational node states.
- Active **sending** or **receiving streams**.
- Session/peer, files or bytes transferred/estimated total, and progress depending on version.
- Supplementary stats like read repair/network/message pool metrics depending on release.

**Illustrative** example:

~~~text
Mode: NORMAL
Receiving streams from node-X:
  transferred: 80 GiB / 200 GiB
Sending streams to node-Y:
  transferred: 12 GiB / 50 GiB
~~~

Exact field names, groupings, and units depend on Cassandra version. **Do not assume all CQL or gossip connections appear in `netstats`.**

### 6.3. Common Misconceptions About netstats

| Claim | Why It Is Wrong |
|---|---|
| "`netstats` shows no streams → the cluster has no network traffic." | CQL, gossip, replica messaging, and heartbeats generate separate traffic |
| "No streams → repair is finished." | Repair includes prep/validation phases; streams are not active at all moments |
| "Stream progress 90% → definitely 10% time remaining." | File sizes, sessions, rates, finalization, retries, and disk latency vary |
| "Node is `UN` → streaming is definitely done cluster-wide." | Check tasks/status and all relevant nodes; streams from other jobs may still run |
| "Streaming active means the cluster is bootstrapping." | Repair, replace, rebuild, and decommission also trigger streaming |
| "`netstats` proves all replica data is completely accurate." | A streaming session is not a keyspace-wide anti-entropy verification |

### 6.4. Estimating Approximate Rate

Suppose for the same receiving session, you measure:

~~~text
10:00:00  transferred = 80 GiB
10:02:00  transferred = 86 GiB
Delta     = 6 GiB / 120 seconds
          = 6 × 1024 MiB / 120
          ≈ 51.2 MiB/s
~~~

This is the average rate over the **measured interval**, not peak network bandwidth or an exact ETA. Streams can switch files/sources, get throttled, enter new phases, or retry.

If two snapshots belong to **different sessions**, subtracting counters directly is meaningless; ensure consistent session/peer and units.

### 6.5. How Does Streaming Impact Reads/Writes?

When node N1 streams many SSTables to a new node N4:

1. N1 reads large volumes from disk, contending with `SELECT` queries.
2. N1/N4 network links carry extra streaming traffic, potentially sharing paths with replica traffic.
3. N4 writes incoming data to disk, creating write I/O pressure and post-stream tasks.
4. Compaction/flush/repair may continue concurrently, creating multi-way resource contention.
5. Java apps can see p99 rise even when query shapes and CL stay unchanged.

**Do not assume killing streaming is a safe fix.** Bootstrap/repair/replace jobs maintain replication and availability. Identify the running process and check whether it can be throttled or rescheduled per runbook.

## 7. Mapping the Three Commands to Specific Background Activities

| Activity | Visible in `tpstats` (Possibly) | Visible in `compactionstats` (Possibly) | Visible in `netstats` (Possibly) |
|---|---|---|---|
| **High read traffic** | Read-related stage Pending/Active rises | Indirect backlog growth via I/O contention | Usually does not show CQL reads as streams |
| **High write traffic / flush** | Mutation/flush stages busy, pending rises | New SSTables increase compaction demand | Usually does not show CQL writes as streams |
| **Heavy compaction** | Related executors busy depending on version | Active tasks, bytes processed, pending tasks | Local compaction is normally not shown as streams |
| **Repair** | Related stages/queues may rise | Validation/compaction activity depending on version | Streams divergent data when repair transfers are needed |
| **Bootstrap/replace/rebuild** | Some I/O and messaging stages rise | Auxiliary background tasks may appear | Send/receive streams most prominent |
| **Hinted handoff** | Messaging/queues and load on hint-holding node | Not direct compaction | Not treated as SSTable streaming by default |
| **Disk full / I/O stall** | Pending rises across multiple stages | Active progress stalls; pending may rise | Sessions may stall or retry |

The table deliberately says **Possibly**. Exact stages, metrics, and integration vary across Cassandra versions. An "empty" row does not prove the corresponding activity is absent.

### Overload Feedback Loop

~~~mermaid
flowchart TD
    A["Write traffic increases"] --> B["Flushes create SSTables rapidly"]
    B --> C["Compaction backlog grows"]
    C --> D["Read amplification and disk contention"]
    D --> E["Read p99 / timeouts increase"]
    E --> F["Client retries more aggressively"]
    F --> G["New load spikes on coordinator / replicas"]
    G --> H["tpstats Pending and dropped messages rise"]
    H --> D
    I["Concurrent repair or streaming"] --> D
~~~

This is **one plausible scenario**, not a universal law for every incident. Sometimes the right intervention is client backpressure/retry tuning and throttling background work rather than enlarging thread pools.

## 8. Supplementary Commands to Test Hypotheses

The three main commands are often insufficient alone. Combine them with other read-only status commands:

~~~bash
# Topology / replica state by DC and rack.
nodetool status

# Node identity and high-level load.
nodetool info

# Read/write and SSTable stats per table.
nodetool tablestats telemetry.measurements_by_device_day

# Latency and SSTables-per-read distributions where supported.
nodetool tablehistograms telemetry measurements_by_device_day

# Coordinator-level histograms, version-dependent.
nodetool proxyhistograms

# Check commitlog / compaction / streams via metrics and logs,
# not solely from a single nodetool output.
~~~

Beyond `nodetool`, inspect:

- **CPU and GC**: pauses, CPU throttling, heap/off-heap.
- **Disk**: free bytes, disk await/latency, IOPS, bandwidth, SMART/cloud volume throttling.
- **Network**: RTT, retransmissions, packet loss, inter-node/inter-DC throughput.
- **Driver**: request p95/p99, in-flight counts, retries/speculative executions, timeouts/unavailable errors.
- **Cassandra logs**: compaction error stack traces, disk read/write errors, dropped messages, bootstrap/repair timelines.
- **JMX/Prometheus**: per-node counters/rates for stages, pending compactions, streaming, and latency.

Always **record units** (ms/µs/s, MiB/GiB, bytes, counts), measurement windows, and exporter versions. Some counters reset on node restart, turning deltas negative; that signals a data-reset boundary, not "the server un-processed messages".

## 9. CQL Example: What Stage Pressure Can Query Shapes Create?

### 9.1. Query-Driven Schema

Suppose we have a keyspace and table:

~~~cql
CREATE KEYSPACE telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE telemetry.measurements_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    metric_value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

The partition key is **`(device_id, event_day)`**, scoping a query for one device on one day cleanly:

~~~cql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, metric_value
FROM telemetry.measurements_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

With reasonably sized partitions, this query is far cheaper than a full scan. Still, even `LIMIT 50` can read through many SSTables/tombstones before finding 50 live rows. `tpstats` reveals read-stage overload, but **does not replace inspecting query shapes**.

### 9.2. Queries That Easily Cause Unintended Load

~~~cql
-- Anti-pattern illustration: not recommended for production APIs.
SELECT device_id, event_day, event_time, metric_value
FROM telemetry.measurements_by_device_day
WHERE metric_value > 80
LIMIT 50
ALLOW FILTERING;
~~~

`ALLOW FILTERING` without a partition key can force Cassandra to scan broad ranges. `LIMIT 50` caps returned rows, not how many entries are read. When APIs issue queries like this frequently, `ReadStage Pending` or disk I/O climbs; if compaction is also backlogged, tail latency worsens rapidly.

The durable fix is usually **query-driven table design** or indexing/search mechanisms appropriate to the version and workload—not blindly adding worker threads.

### 9.3. CL and Replica Wait Exposure

With RF=3 in one DC:

- `ONE` requires a response from one replica per operation semantics.
- `LOCAL_QUORUM` requires local quorum—two replicas in the DC.
- `ALL` requires every designated replica.

If one replica slows down due to streaming, `LOCAL_QUORUM` requests can suffer if fast healthy replicas fail to reach quorum in time. Still, never conclude **"LOCAL_QUORUM is always slower than ONE by one RTT"**: replica requests are issued concurrently and latency depends on the execution path.

Changing CL is a **consistency/availability** decision, not mere latency tuning. `tpstats`, `netstats`, and `compactionstats` expose load; **they do not replace application correctness design**.

## 10. Java Driver 4.x: Correlating Client Latency with Background Activity

Java applications should emit metrics keyed by **stable query ID**, consistency level, DC, and outcome. Never attach partition key values as metric labels due to unbounded cardinality and potential exposure of sensitive data.

Example reading a single partition with a prepared statement:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

// session is created and managed at application lifecycle.
PreparedStatement query = session.prepare(
    "SELECT event_time, metric_value " +
    "FROM telemetry.measurements_by_device_day " +
    "WHERE device_id = ? AND event_day = ? LIMIT 50"
);

BoundStatement statement = query.bind(
        UUID.fromString("11111111-1111-1111-1111-111111111111"),
        LocalDate.of(2026, 11, 21))
    .setPageSize(50)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

long startNs = System.nanoTime();
String outcome = "success";

try {
    ResultSet rs = session.execute(statement);
    for (Row row : rs) {
        processMetric(row.getInstant("event_time"),
                      row.getDouble("metric_value"));
    }
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    long latencyMs = TimeUnit.NANOSECONDS.toMillis(
        System.nanoTime() - startNs);

    // Demo: replace with cardinality-bounded histogram/logging.
    recordRequest("read_measurements_by_day",
                  "LOCAL_QUORUM", outcome, latencyMs);
}
~~~

`processMetric` and `recordRequest` are **hypothetical hooks**; implement them using your application's metrics/logging backend. Avoid blocking callbacks or buffering excessive rows in memory.

The timing block above spans consuming up to 50 rows; if code paginates unboundedly, distinguish **time to first page** from **time to consume all pages**. The driver also exposes built-in metrics for request latency, retries, and connection pools depending on config.

When Java p99 rises:

1. Correlate timestamps and operation IDs with `tpstats` on relevant coordinators/replicas.
2. Check `compactionstats` to see if backlogs/active compactions coincide.
3. Check `netstats` for active streams to/from those nodes.
4. Check disk/GC/network and error rates to confirm the bottleneck.
5. Compare retry counts and timeouts to catch client retry storms amplifying load.

A successful `execute` does not prove all replicas are synchronized or background jobs are idle; it reflects the outcome of that request at the chosen CL.

## 11. Runbook A: High Read p99, Rising ReadStage Pending

**Scenario:** A DC has three replicas for an RF=3 keyspace. P99 of API `read_measurements_by_day` jumps from 70 ms to 900 ms, and `ReadStage Pending` on node B climbs continuously.

### Step 1 — Quantify Impact

Gather start time, p50/p95/p99, QPS, timeouts, CL, nodes, and DC/rack. Check whether one API is affected or all queries.

### Step 2 — Capture Multiple tpstats Samples

Run `tpstats` on B and at least one healthy node for comparison. Record `Active`, `Pending`, `Completed` deltas, and `Dropped` deltas across timestamps. If B's queue grows while others do not, check token distribution/hot partitions and B's local resources.

### Step 3 — Cross-Check Compaction and Streaming

Check `compactionstats` and `netstats` on B. If heavy compaction, large streams, and high disk I/O latency coincide, storage contention is well-supported. If there is no streaming while read queues climb, investigate scan/tombstone queries and CPU/GC.

### Step 4 — Inspect Table and Queries

Check `tablehistograms`, SSTables per read, tombstone warnings, partition sizes, and whether queries specify full partition keys. Never treat `LIMIT` as proof a query is cheap.

### Step 5 — Shed Pressure Safely

Depending on cause, throttle backfills, reduce concurrency of non-critical jobs, fix query shapes, or adjust repair/streaming schedules per runbook. **Never blindly enlarge thread pools, disable compaction, or lower consistency levels.**

### Step 6 — Verify Recovery

Queues return to baseline; dropped deltas stop rising; p99 and timeouts drop; disk/CPU/GC stabilize. Continue monitoring after background jobs finish to ensure backlogs do not re-accumulate.

## 12. Runbook B: Long Compaction Backlog and Nearly Full Data Disk

**Scenario:** `compactionstats` reports pending tasks climbing from 15 to 180 within an hour; data disk is down to 12% free with heavy updates/TTL churn.

1. **Confirm a real backlog:** sample `compactionstats` over time to see if active tasks advance; identify which tables contribute most work.
2. **Analyze flush and write load:** check `tpstats` flush stages and mutation queues; measure SSTable creation rate and commitlog/disk activity.
3. **Measure true disk headroom:** old and new SSTables coexist during compaction; account for snapshots, streaming, and flushes.
4. **Verify compaction strategy:** STCS/LCS/TWCS have distinct write/read/space amplification profiles; do not switch strategies mid-incident without a plan.
5. **Throttle non-essential load:** rate-limit imports/backfills or eligible background work per runbook; prioritize keeping the read/write path safe.
6. **Never delete SSTables manually:** doing so risks data loss or severe inconsistency.
7. **Verify:** pending drops, active compactions progress, free disk stays out of danger zones, and p99/timeouts normalize.

**Caution:** "stopped compaction" does not mean all old space is immediately reclaimable. Stopping/altering compaction requires understanding file states, generated data, snapshots, and version behavior.

## 13. Runbook C: Bootstrap Streaming Drives Up Write Timeouts

**Scenario:** Node N4 is bootstrapping, and `netstats` on N1/N4 shows heavy streaming. Meanwhile `MutationStage Pending` and write p99 rise on several nodes.

1. Identify which operation drives the stream: **bootstrap, repair, rebuild, or replace**, plus token/keyspace scope and the change owner.
2. Read `nodetool status` for joining/normal and down nodes; **`UJ` is not `UN`**.
3. Track `netstats` by **session/peer**, bytes transferred, and deltas over time. Do not treat one session's % progress as a cluster-wide ETA.
4. Check source disk read latency, target disk write latency, network throughput/packet loss, and cloud volume quotas.
5. Check `tpstats` for pending/dropped in mutation/read stages; check `compactionstats` for additional I/O contention.
6. If resources hit limits, coordinate with the change owner to **throttle streaming or non-critical workloads per runbook**; never arbitrarily abort or delete incoming data.
7. Once N4 transitions to `UN`, verify streaming completed, application metrics stabilized, and post-topology cleanup/repair plans are scheduled properly.

Even if `LOCAL_QUORUM` needs only two ACKs in a DC, having three nodes does not guarantee two ACKs arrive on time while streaming causes I/O stalls; monitor actual client timeouts.

## 14. Alerts and Dashboards: Never Set Thresholds on a Single Snapshot

### 14.1. Alert on Combined Signals

| Alert Scenario | Combined Signals | Why Better Than a Single Metric |
|---|---|---|
| **Read overload** | Sustained ReadStage Pending growth + rising read p99/timeouts | Separates user-impacting queues from harmless bursts |
| **Write overload** | Rising MutationStage/flush backlog + write timeouts + high disk latency | Points to a congested write path |
| **Compaction falling behind** | Growing pending compactions + high SSTables per read + shrinking disk headroom | Combines backlog, performance impact, and capacity risk |
| **Prolonged streaming** | Large remaining bytes / low throughput + node joining too long + errors/retries | Distinguishes healthy streams from stalled ones |
| **Abnormal dropped messages** | Dropped delta > baseline + rising timeouts | A standalone cumulative counter may reflect an old incident |
| **Background I/O contention** | Active compaction/streaming + high disk await + degraded p99 | Demonstrates shared resource saturation |
| **Recovery risk** | Prolonged Down node + repair/hints lagging + capacity warning | Prevents treating "node back UP" as mission accomplished |

Exact numeric thresholds must derive from **baselines, traffic, SLAs/SLOs, cluster size, and version**. No single threshold like `Pending > 100` is universally dangerous across all stages and nodes.

### 14.2. Aggregations to Avoid

- **Never average per-node p99** to report a cluster p99. Percentiles require properly mergeable histograms/distributions.
- **Never sum different queue types** into one "cluster-wide pending" number and interpret it as waiting user requests.
- **Never treat cumulative Completed counters** as throughput; compute delta/time and check for resets.
- **Never subtract `netstats` bytes transferred** across two different sessions to compute speed.
- **Never use total pending compactions** in place of required disk space; task sizes vary widely.

### 14.3. A Minimum Viable Dashboard

- Row 1: API read/write QPS, p50/p95/p99, timeouts/unavailable by DC/CL.
- Row 2: `tpstats` Pending/Active/dropped deltas per node and key stage.
- Row 3: `compactionstats` active/pending, SSTables per read, data disk free/latency.
- Row 4: `netstats` active streaming, bytes/s per node/peer, and bootstrap/repair events.
- Bottom row: CPU, heap, GC, network errors, commitlog/hints/flush, config changes, or deploys.

Never attach partition keys or user IDs as time-series labels for "detailed debugging" due to cardinality and sensitive-data risks; use stable query IDs alongside controlled traces/logs.

## 15. Operational Safety: Observe First, Intervene Second

The three primary commands in this lesson are **observational**, yet the background activities they expose can be highly sensitive to intervention.

| Intended Action | Why Caution Is Required |
|---|---|
| Increasing compaction concurrency/throughput | Can worsen disk contention, spike p99, or exhaust disk headroom |
| Throttling compaction throughput too low | Can prolong SSTable backlogs and increase read amplification |
| Aborting a stream mid-bootstrap/repair | Can prolong incomplete states and leave half-finished work requiring recovery |
| Adding worker threads when Pending is high | If disk/network is the bottleneck, more workers will not fix it |
| Deleting SSTables, commit logs, or hints to free disk | Can cause unrecoverable data loss or break recovery mechanisms |
| Running `nodetool compact`, `repair`, or `flush` "just to test" | Load-generating operations requiring heavy disk/network; unsuitable as casual probes |
| Lowering `LOCAL_QUORUM` to `ONE` to cut timeouts | Alters consistency/correctness guarantees, not merely performance |

**Production handling rule:** record baseline → verify version and root cause → propose a small change with an owner and rollback plan → observe p99/errors/capacity → only then broaden rollout. Execute intrusive commands only under approved runbooks.

## 16. Scenario Exercises

### Question 1 — Is the Queue Growing?

`ReadStage Pending` rises from 120 to 1,020 in 60 seconds, while `Completed` rises from 500,000 to 518,000. What is the observed completion rate? Can you conclude how many extra threads are needed?

**Answer:** `(518,000 - 500,000)/60 = 300` tasks/second. The queue grew by 900 items. You cannot conclude how many threads to add yet; you need service time, workload details, disk/CPU metrics, and stage semantics.

### Question 2 — High Completed Count Without Errors

A node has `Completed=100,000,000`, `Pending=0`, and stable p99. Does a high Completed count prove the node is overloaded?

**Answer:** No. This is typically a cumulative counter of processed tasks. You must inspect deltas, queues, dropped/error rates, and latency.

### Question 3 — High Pending Compactions

`compactionstats` reports pending=70, yet all active compactions are advancing, read/write SLOs look good, and disk headroom is ample. Must you adjust throughput immediately?

**Answer:** No. Monitor the backlog trend and resources; a single pending figure is inconclusive. Changing concurrency/throttling can introduce unnecessary I/O contention.

### Question 4 — No Active Streams

`nodetool netstats` shows zero streaming sessions while Java `SELECT` queries remain slow and network traffic is high. Is that contradictory?

**Answer:** No. `netstats` focuses on storage-level data streaming; CQL traffic and replica messaging carry their own network traffic.

### Question 5 — Can Repair Still Run When netstats Is Empty?

An operator asserts "empty netstats means no repairs are running". True or false?

**Answer:** False. Repair may be in a phase not currently streaming SSTables, and `netstats` is not the sole tool to confirm repair completion. Check logs/metrics and repair task status.

### Question 6 — Concurrent Streaming and Compaction

During bootstrap, `netstats` shows 150 GiB sending, `compactionstats` shows rising backlog, disk await rises, and read p99 climbs. Outline a sound diagnostic sequence.

**Answer:** Check source/destination streams, bytes/s rate, and disk utilization; cross-check compaction backlog, SSTable count, and read stage queues; inspect per-node p99/timeouts; shed non-critical load or throttle background work per runbook if genuine contention is confirmed.

### Question 7 — Stopping Streaming

A new node is `UJ`, and an operator wants to stop streaming and send full production traffic because `nodetool status` shows UP. What should you do?

**Answer:** Never treat `UJ` as `UN`. A joining node has not finished bootstrapping; verify transfer completion and Normal state per procedure rather than forcing traffic or deleting incoming files.

### Question 8 — Dropped Messages

The READ dropped counter jumps from 5 to 305 in one minute while read timeouts also rise. Can you conclude exactly 300 `SELECT` requests failed?

**Answer:** No. The counter tracks internal message types, not a 1:1 mapping to client requests. You can state that the dropped-message delta rose by 300 and correlated with timeouts, then investigate stages, replicas, and logs.

### Question 9 — Compaction Needs Free Space

A node is nearly out of disk while compaction writes output SSTables. Is manually deleting a few source SSTables to "make room" valid?

**Answer:** No. Source SSTables must remain intact until transition completes safely; manual deletion risks data loss. Handle capacity and backlog per runbook.

### Question 10 — Monitoring a Multi-DC Cluster

An application uses `LOCAL_QUORUM` in `dc1`. A node in `dc2` is streaming heavily with high pending queues, yet APIs in `dc1` remain healthy. Should you assume all requests will slow down?

**Answer:** No. Remote-DC impact depends on CL, topology, operation type, and shared resources. Monitor each DC/node independently and avoid extrapolating one node's state to the entire cluster.

## 17. Summary

`nodetool tpstats`, `nodetool compactionstats`, and `nodetool netstats` form **three complementary views** of Cassandra background activity:

1. **`tpstats`** shows how much work executors handle, whether queues are growing, and whether messages are dropped; always examine **deltas and trends**.
2. **`compactionstats`** shows compaction backlog and active task progress; pending count **is not bytes or a fixed ETA**.
3. **`netstats`** shows active data **streaming** sessions; it **does not measure all CQL network traffic** and does not prove repair finished.
4. **Background work contends for CPU, disk, network, and memory** with reads/writes; pinpoint bottlenecks by combining resource metrics, p99/errors, and task activity.
5. **A `UN` node does not prove healthy performance**, and `UJ` is not a completed bootstrap.
6. **Never tune concurrency, throttles, or abort tasks from a single snapshot**; verify version, correctness impact, and rollback plans first.
7. **Java and CQL still require sound partition keys, query shapes, and CL**; no operational tool can turn an expensive full scan into an optimal query.

When Cassandra slows down, the right question is not simply "which command shows a big pending number?", but **"which task is building a backlog, which resource is saturating, which replicas are affected, and how much of the request slowdown does that explain?"** Only when those pieces of evidence connect should you alter how the cluster is operated.
