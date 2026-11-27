# Streaming/Repair Throughput and Its Impact on Business Queries

> **Chapter:** Resource Tuning  
> **Scope:** Apache Cassandra, a distributed *wide-column* database using partition keys, replicas, SSTables, and consistency levels. This lesson focuses on **data streaming** and **anti-entropy repair** running concurrently with CQL queries from Java applications.  
> **Objective:** Distinguish streaming speed from repair cost; understand bandwidth caps, concurrency, and disk/CPU resources; measure impact on read/write p95/p99; and build a throttling schedule that **stays within SLOs** while still finishing repair safely within the tombstone protection window.

## 1. Scenario: Repair Runs Faster Yet the API Slows Down

A Cassandra cluster spans two datacenters, each with multiple nodes and keyspaces using `NetworkTopologyStrategy`. Normally, the Java API reads partitions by key and writes events at `LOCAL_QUORUM`:

- Read p99: ~70 ms.
- Write p99: ~45 ms.
- Very few timeouts; disk and network still have headroom.

The operations team just raised streaming bandwidth and concurrent repair sessions to shorten maintenance windows. Afterward:

- Read p99 jumped to 350 ms, and write timeouts appeared.
- Disk read/write queues grew; one node's network egress hit saturation.
- `nodetool netstats` showed many active streams.
- `nodetool compactionstats` and `nodetool tpstats` showed growing backlogs.

**You cannot conclude "faster repair is better" simply because GiB transferred per hour increased.** In Cassandra, background jobs and business requests share **replicas, CPU, disk, memory, and NICs**. Running more concurrent work can slow everything down together—even causing repairs to time out and restart.

The tuning problem must satisfy two constraints simultaneously:

1. **Availability and performance:** CQL p95/p99, error rate, and timeouts remain within SLO while repair/streaming run.
2. **Data safety:** repair must cover the required replicas/token ranges **before the tombstone protection window (`gc_grace_seconds`) becomes unsafe**.

The goal is not maximizing a single parameter, but finding the **highest useful throughput where the cluster still meets SLOs with safety headroom**.

## 2. Streaming and Repair Are Related, Not Identical

### What Is Streaming?

**Streaming** is the transfer of data between Cassandra nodes by SSTable/partition/token range. It occurs across multiple operations:

- **Bootstrap:** admitting a new node into the topology and receiving data for the ranges it owns.
- **Rebuild:** populating a node's data, typically when adding a new datacenter from source replicas.
- **Replace or decommission:** shifting ownership and data when replacing/removing a node.
- **Repair:** after comparing replicas, transferring differing data portions.
- Other administrative operations depending on version.

Streaming generates **network traffic**, yet also requires **reading SSTables at the source, writing data at the target**, validating data, and potentially triggering follow-up storage work.

### What Else Does Repair Include Beyond Streaming?

**Anti-entropy repair** reconciles replicas responsible for shared token ranges. Depending on version and repair type, costs may include:

1. Session planning, selecting replicas and ranges.
2. **Validation:** reading data/SSTables to build and compare verification structures such as Merkle trees.
3. Identifying discrepancies.
4. **Streaming:** transferring data needed to synchronize differences.
5. Finalization and updating repair state; incremental repair may involve **anti-compaction** and classifying repaired/unrepaired SSTables.

**A repair streaming almost zero bytes can still be very expensive in I/O and CPU**, because validation still has to read and compare data. Conversely, bootstrap/rebuild can stream massive volumes without carrying repair's anti-entropy purpose.

```text
REPAIR
  |
  +--> Initialize / select token ranges and replicas
  |
  +--> Validation: read SSTables, compute/compare data
  |        |                       |
  |        +--> CPU                +--> Disk reads
  |
  +--> Any divergence?
  |        |
  |        +--> Yes: STREAM data    -> source disk read + NIC + target disk write
  |        +--> No: little/no stream, validation already consumed resources
  |
  +--> Finalize, possibly anti-compaction / metadata update
  |
  +--> Track success per range, not just command start
```

Hence, `stream throughput` and `repair throughput` **are not the same metric**.

## 3. Four Distinct Throughput Metrics to Measure Separately

| Measure | Common Unit | Question Answered | Easily Misinterpreted As |
| --- | --- | --- | --- |
| **Network streaming throughput** | Mb/s, MB/s, or MiB/s | How many bytes/sec is a node transferring? | Overall repair speed |
| **Validation/scan throughput** | GiB scanned/hour | How fast does repair read and compare SSTables? | Actual bytes transferred over the network |
| **Repair coverage throughput** | Token ranges, tables, or data fraction reconciled/hour | Will the schedule finish the protected scope in time? | Number of jobs launched |
| **Business throughput** | CQL requests/s, events/s, transactions/s | How much useful work is the app still serving? | High CPU or network utilization |

Suppose a repair validates 800 GiB of data with only 2 GiB differing:

```text
Data scanned during validation: 800 GiB
Data actually streamed:          2 GiB
Result: streamed bytes are low, yet the job can still take hours.
```

Raising streaming bandwidth caps may **barely reduce validation time**. Identify the actual bottleneck before changing any throttle.

### Distinguishing Bits and Bytes

- `Mb/s`: megabits/second (typically 10^6 bits/second).
- `MB/s`: megabytes/second (typically 10^6 bytes/second).
- `MiB/s`: mebibytes/second, equal to 2^20 bytes/second.
- `1 byte = 8 bits`, excluding protocol/TLS/TCP overhead or compression differences.

For example, a `160 Mb/s` cap corresponds roughly to `20 MB/s` by simple bit/byte division—**not** `160 MB/s`. When reading `nodetool` or config files, verify the **exact unit for your Cassandra version**.

## 4. Request Path and Contended Resources

Suppose the Java app sets its local DC to `dc1` and queries with a complete partition key:

```text
          JAVA APPLICATION
                 |
                 v
           Coordinator (dc1)
                 |
        +--------+--------+
        |                 |
   Replica A           Replica B       LOCAL_QUORUM waits for enough ACKs
        |                 |
   Memtable/SSTable   Memtable/SSTable
        |                 |
        +--------+--------+
                 |
       Shared on each node:
          CPU, memory, cache
          disk / commit log
          internode network
          compaction / repair
```

While repair/streaming runs, these same nodes may simultaneously act as **sources** and **destinations** for different streams.

### Disk Reads

Repair validation scans SSTables; streaming sources must read data. Business reads also need SSTables, partition indexes, Bloom filters, and payload blocks. On devices with high I/O latency or many SSTables/tombstones, contention can cause:

- Rising disk await.
- Growing pending read requests.
- Slower replica responses to the coordinator.
- Rising p99 and read timeouts.

### Disk Writes

Streaming destination nodes write received data. Simultaneously, Cassandra must:

- Write commit log and memtables on the mutation path.
- Flush memtables to SSTables.
- Compact SSTables.
- Handle anti-compaction or repair-related storage tasks where applicable.

Insufficient disk throughput or headroom can build backlogs, threatening both availability and repair completion.

### CPU and Memory

Validation/hashing, serialization, compression/decompression, TLS, and compaction all use CPU. Buffers, metadata, and off-heap structures consume RAM. When CPU saturates, containers throttle, or GC pauses lengthen, not only do streams slow down—CQL executors queue up too.

### Network

A node can send streaming data while simultaneously handling app CQL traffic, replication messages, and gossip/repair traffic. In multi-DC setups, saturating the WAN link hurts replication to the remote DC, even if `LOCAL_QUORUM` requests in the local DC finish without waiting for remote ACKs.

**Do not equate "local quorum doesn't wait for remote ACK" with "WAN doesn't matter".** A saturated WAN builds cross-DC replication lag, leaving clients in the remote DC reading staler data.

## 5. Two Primary Throttling Knobs: Rate and Concurrency

Tuning streaming/repair usually involves **two distinct control groups**.

### Group A — Streaming Throughput Limits

Cassandra releases provide config mechanisms to cap outbound streaming rate and often a separate cap for cross-DC streams. Typical version-dependent parameter names include:

- `stream_throughput_outbound_megabits_per_sec`;
- `inter_dc_stream_throughput_outbound_megabits_per_sec`.

Some releases offer matching `nodetool` commands to inspect/adjust at runtime. Read help **on the exact node in use**, as flag names, entire-SSTable streaming handling, and units vary across releases.

Observation commands first:

```bash
nodetool help getstreamthroughput
nodetool getstreamthroughput

nodetool help getinterdcstreamthroughput
nodetool getinterdcstreamthroughput

nodetool help setstreamthroughput
nodetool help setinterdcstreamthroughput
```

This is not a guaranteed list for every release or CQL-compatible managed service. If a version lacks one of these commands, check supported docs/configs instead of guessing syntax.

**Changing one node does not automatically impose a cluster-wide cap.** With per-node outbound throttles, multiple source nodes can still sum their bandwidth on a shared network link.

Hypothetical example: four source nodes are each capped at 150 Mb/s; if they share a cross-DC link with only 400 Mb/s available, the **aggregate configured rate** can hit 600 Mb/s and saturate the WAN. Do not confuse a node-level cap with a cluster-level bandwidth budget.

### Group B — Work Concurrency

This includes:

- Number of nodes running rebuild/bootstrap/repair concurrently.
- Number of active repair sessions/jobs/ranges.
- Number of streams/channels per peer.
- Number of validation and anti-compaction tasks overlapping.
- How the repair schedule spreads across token ranges, replicas, and datacenters.

Depending on version, `nodetool repair` accepts flags controlling parallelism or job counts; check `nodetool help repair` on the node. A safer approach uses a token-range- and replica-aware orchestrator enforcing **concurrency caps on both source and target nodes**, not just "run N coordinators".

### Why Raising the Throttle Alone Isn't Enough

A rate-limited stream speeds up when you raise its cap. Yet if the bottleneck is:

- **Validation disk reads**, raising the network cap barely helps.
- **CPU scarcity**, higher network caps create no extra CPU.
- **Destination disk writes**, faster sources only grow target queues.
- **Multiple repair ranges hitting one replica**, raising concurrency only multiplies contention.

The true bottleneck—not the highest cap value entered—determines useful throughput.

## 6. Reading `nodetool netstats` and Related Tools

On a lab node or authorized production node:

```bash
nodetool status
nodetool netstats
nodetool compactionstats
nodetool tpstats
nodetool tablestats lab.events_by_device_day
```

| Tool | Useful Information | Limitation |
| --- | --- | --- |
| `nodetool status` | Which nodes/DCs are Up/Down and topology state | `UN` does not guarantee healthy p99 or healthy disks |
| `nodetool netstats` | Streaming progress, send/receive sessions, and version-specific network stats | Does not show full validation/anti-compaction cost |
| `nodetool compactionstats` | Active/pending compactions, processed bytes, related tasks | Does not replace per-range repair completion tracking |
| `nodetool tpstats` | Thread pools/stages active, pending, completed, dropped messages | One snapshot cannot prove sustained queue growth |
| `nodetool tablestats` | Per-table space/SSTables/memtable/latency | Does not capture NIC bandwidth or full end-to-end API latency |

### Measurements Outside Cassandra

```bash
vmstat 1
iostat -xz 1
pidstat -u -p <pid> 1
```

Depending on OS, you may need network tools like `sar`, switch/firewall/WAN telemetry, and container/cgroup metrics. For Java/JVM, inspect GC pauses, heap/off-heap/RSS, and CPU throttling so you don't miss compute/memory causes.

All commands above are **read-only observations**; never run compaction/repair changes in production without a maintenance window and runbook.

### GiB Transferred Alone Doesn't Show Impact

Suppose 100 GiB streams in 10 minutes:

- If SSD reads/writes keep headroom and CQL p99 stays steady, that may be acceptable.
- If read p99 jumps 5x and pending compactions climb, that same rate is excessive.
- If streams run fast yet repeatedly fail on timeouts/errors and restart, **effective** cycle throughput may be low.

Always pair throughput with **repair success rate, completion time, and business SLOs**.

## 7. Budgeting Network and I/O by Node, Replica, and DC

### Simulating an RF=3 Cluster

Suppose `dc1` has 6 nodes, each holding part of an RF=3 keyspace; the application reads/writes steadily at `LOCAL_QUORUM`.

A repair coordinated by N1 pulls replicas N2 and N3 into validation and streaming. A parallel repair coordinated by N4 can also touch N2. **N2 absorbs load from two repairs** even though a coordinator dashboard shows only one job per coordinator.

```text
Repair job A:  Coordinator N1 ---> Replica N2 <--- Coordinator N4 :Repair job B
                                  |
                          shared CPU / disk / NIC
                                  |
                         Live CQL serving replicas
```

Schedules must check **replica overlap**, not merely divide node count by job count.

### Estimating Transfer Time from the Cap

Hypothetical example: **300 GiB** must stream between two node groups over a link with **150 Mb/s** observed useful throughput:

```text
300 GiB ≈ 300 × 2^30 bytes
         ≈ 2.58 × 10^12 bits

Minimum network time ≈ 2.58 × 10^12 / (150 × 10^6)
                     ≈ 17,180 seconds ≈ 4.8 hours
```

This is a **one-way bandwidth lower bound**, excluding protocol overhead, network contention, source/target fluctuations, disk stalls, and stream failures. If repair also validates 2 TiB of data, 4.8 hours cannot represent total job runtime.

### Safety Budgets Never Consume 100% of the NIC

Even on a nominal 10 Gb/s NIC, application traffic, replication, backups, repair, and other traffic share the link. Measure **peak real-world traffic**, reserve required headroom, and size total streaming throughput so queues and p99 stay inside SLOs.

For cross-DC WAN links, factor in **available transfer rate**, latency, packet loss, egress cost, and failover paths. Setting an independent inter-DC stream throttle where supported helps prevent a DC rebuild from choking business replication.

## 8. Impact on the Read Path: P99, SSTables, and Tombstones

A read by partition key typically flows:

1. Driver picks a coordinator (preferring local DC per policy).
2. Coordinator identifies replicas from token and RF.
3. Replicas read memtable/caches/SSTables as needed.
4. Coordinator waits for enough responses per consistency level.
5. Driver returns the result to the application.

When repair runs heavily, **replica disk read bandwidth/latency** faces contention. This becomes especially visible when:

- A partition spans many SSTables due to compaction backlog.
- Many cells expired via TTL or were deleted, causing heavy tombstone scans.
- Queries read wide clustering slices.
- Hot partitions concentrate read traffic onto a few replicas.
- Repair validation scans many SSTables on those exact replicas.

```text
Repair validation reads SSTables --> disk queue grows
                                       |
CQL SELECT also reads SSTables --------+
                                       |
                              replica read latency rises
                                       |
                    coordinator waits longer for LOCAL_QUORUM
                                       |
                             Java API p99 / timeouts rise
```

### Why Can `LIMIT 20` Still Be Slow?

`LIMIT 20` bounds rows **returned**, not physical cells/SSTables scanned before finding enough live rows. If a partition contains many tombstones, repair/compaction disk contention can push p99 up even more sharply.

Tuning streaming while ignoring **partition keys, TTL/delete patterns, and SSTable counts** can misdirect diagnosis: the root cause is read amplification, while repair merely exposes insufficient disk headroom.

## 9. Impact on the Write Path: Commit Log, Memtable, Replication

Cassandra writes arriving at replicas hit the commit log and memtable; flushes and compaction follow. Repair/streaming writes on destination nodes share the same storage and part of CPU/network.

Consequences:

- **Commit log fsync/writes:** higher storage latency can slow ACKs depending on sync policy and node load.
- **Memtable flushes:** slow down when disk write queues grow; un-flushed data accumulates.
- **Compaction backlog:** new SSTables need merging while disks are busy streaming.
- **Replica ACKs:** if a required replica slows down, the coordinator misses consistency level deadlines.
- **Inter-DC replication:** mutation streams to remote DCs can suffer when streaming saturates WAN bandwidth.

A write timeout **does not prove no replica applied the mutation**. Java applications must handle retries considering idempotency and timestamps/TTLs, especially while repair runs during topology changes.

### LOCAL_QUORUM Does Not Eliminate Indirect WAN Risk

With RF=3 per DC, `LOCAL_QUORUM` in dc1 needs only two ACKs in dc1. When the WAN link clogs during a dc2 rebuild:

- Local CQL writes in dc1 may still succeed if local replicas are healthy.
- Yet mutations to dc2 arrive late, so `LOCAL_QUORUM` reads **in dc2** may see stale data.
- If dc1 disks/NICs also bear heavy streaming load, local CQL in dc1 can slow down too.

Tuning must consider **SLOs in both DCs** and freshness requirements for the standby DC.

## 10. CQL Practice: Table and Query Pattern for Measurement

This example uses a `lab` keyspace already present in a test cluster. The table stores events by device and day so partitions stay bounded rather than accumulating a device's entire history:

```cql
CREATE TABLE IF NOT EXISTS lab.events_by_device_day (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

Insert an illustrative record:

```cql
INSERT INTO lab.events_by_device_day
    (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    'device-01',
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    11111111-1111-4111-8111-111111111111,
    'heartbeat',
    'ok'
);
```

Read using the full partition key:

```cql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, event_id, event_type, payload
FROM lab.events_by_device_day
WHERE device_id = 'device-01'
  AND event_day = '2026-11-21'
LIMIT 50;
```

In `cqlsh`, `CONSISTENCY LOCAL_QUORUM` sets the CL for the active CQL session. For proper multi-DC evaluation, know which coordinator node `cqlsh` connects to, RF per DC, and replica health.

This pattern is for **measuring single-partition latency**, not generating excessive overload. Real benchmarks need many partitions, multiple nodes, substantial data volume, realistic read/write mixes, and representative key skew.

### When Is Tracing Useful?

```cql
TRACING ON;

SELECT event_time, event_id, event_type, payload
FROM lab.events_by_device_day
WHERE device_id = 'device-01'
  AND event_day = '2026-11-21'
LIMIT 50;

TRACING OFF;
```

Tracing reveals which coordinator/replicas a sample request hits, yet **does not show cluster-wide streaming bandwidth** and adds overhead. Combine tracing with `tpstats`/`netstats`, node metrics, and driver telemetry rather than turning tracing on at 100% during peak hours.

## 11. Commands to Observe and Adjust Throughput in the Lab

### Step A — Capture Baseline Before Streaming/Repair

```bash
nodetool status
nodetool netstats
nodetool compactionstats
nodetool tpstats
nodetool tablestats lab.events_by_device_day

nodetool getstreamthroughput
nodetool getinterdcstreamthroughput
```

Record timestamps, Cassandra version, DCs, RF, node names, GiB managed, and effective limits. If your release lacks one of the `get...` commands, consult version docs/configs—**never run `set...` commands by guesswork**.

### Step B — Inspect Config Commands Before Changing Anything

Cassandra releases typically support similar runtime commands:

```bash
nodetool help setstreamthroughput
nodetool help setinterdcstreamthroughput
nodetool help repair
```

Example **illustrating common syntax** in the lab, to be used only after checking units and flags with `help`:

```bash
# Example: set outbound streaming cap on the target node.
# Check your release to confirm which unit "200" represents.
nodetool setstreamthroughput 200

# Example: cap outbound streaming between datacenters.
# Command names / options may differ by version.
nodetool setinterdcstreamthroughput 100
```

**Never copy these two set commands straight into production.** They modify resource caps, may affect only one node, and behave differently across standard vs entire-SSTable streaming. Read back `get...` and observe actual throughput to confirm the change took effect.

### Step C — Verify Under Real Work

In a lab cluster, a planned bounded repair can use `nodetool repair` targeting primary ranges and the target keyspace:

```bash
nodetool help repair

# Illustrative only: repair this node's primary ranges for keyspace lab
# Select full/incremental mode and parallelism explicitly per version.
nodetool repair -pr lab
```

This command **does not repair the whole cluster just because it ran once on one node**. Covering all ranges/replicas requires a coordinated schedule; never launch it simultaneously on every node without knowing topology and resource impact.

While repair runs, observe:

```bash
nodetool netstats
nodetool compactionstats
nodetool tpstats
```

Collect JVM/OS/driver metrics with synchronized timestamps. Test under representative load; if repair streams nearly 0 bytes, test results mainly reflect **validation**, which is insufficient to draw conclusions about network throttling during heavy streaming.

## 12. Distinguishing Streaming Limits from Compaction Throughput

In Cassandra, `compaction throughput` and `stream throughput` are **separate** throttles. Releases typically provide tools like `nodetool getcompactionthroughput` and `setcompactionthroughput`.

| Limit | Primary Effect | Does Not Directly Limit |
| --- | --- | --- |
| Outbound streaming throughput | Configured outbound stream rate per node/cross-DC | All validation reads, all compaction, CQL requests |
| Compaction throughput | Resource/byte rate for compaction per version mechanics | Network streaming and coordinator read paths |
| Repair concurrency/jobs | Number of repair operations running in parallel | Guaranteeing one session per node or capping individual streams |
| Scheduling window | When/which range slices run | Instantaneous rate unless paired with throttles/concurrency |

**Setting a low streaming throttle does not guarantee stable queries** if validation still saturates disks. **Setting a very low compaction throttle does not help on its own either**, since SSTable/compaction backlogs inflate read amplification and disk usage.

An effective change targets **whichever background job** is genuinely contending with the read/write path.

## 13. Orchestrating by Load Level Instead of Fixed Speeds

A practical policy can define three modes enforced via an orchestrator and version-supported settings:

| Mode | Condition | Throttling Direction |
| --- | --- | --- |
| **Peak hours** | P99 near SLO, high client traffic | Reduce parallel repair jobs, reserve network/disk for queries |
| **Off-peak hours** | CPU/disk/network have headroom; p99 steady | Carefully step up concurrency/throttles if completion budget requires |
| **Incident or DC recovery** | Node missing data or grace budget nearly exhausted | Prioritize safety; bound concurrency while scaling capacity or shedding app load per runbook |

Do not interpret this table as "stop repair at all costs during peak hours". Delaying too long until successful repair gaps exceed `gc_grace_seconds` increases zombie-data risk. When SLOs and deadlines cannot both be satisfied simultaneously, address **capacity and operational scheduling**, rather than throttling down forever.

### Metric-Driven Feedback Policy

A cautious adjustment loop:

1. Establish baselines: p99, timeouts, read/write throughput, disk await/queue, CPU, NIC, backlog, and repair coverage.
2. Start with relatively conservative concurrency/throughput settings.
3. Run across a **bounded set of ranges/nodes**.
4. Measure impact over a long enough window accounting for bursts and background GC/compaction.
5. If SLOs and headroom look healthy, raise **only one parameter at a time**.
6. If p99, dropped messages, or queues breach thresholds, scale back background activity per runbook.
7. Record ranges/data actually repaired/streamed successfully and reschedule any missed ranges.

Avoid hyper-reactive control loops flipping caps up and down every minute: repair/streaming do not always react instantaneously to throttle edits, and p99 needs a representative observation window.

## 14. Controlled Benchmark Example

A lab cluster runs a representative workload across different outbound streaming caps and concurrency levels. Numbers below are **purely hypothetical**:

| Option | Concurrent Source Jobs | Outbound Cap per Source | Useful Stream | CQL Read P99 | CQL Write P99 | Outcome |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Baseline (no repair) | 0 | — | — | 65 ms | 42 ms | Reference baseline |
| A | 1 | 100 Mb/s | 85 Mb/s | 76 ms | 49 ms | Low background load |
| B | 2 | 200 Mb/s | 300 Mb/s total | 105 ms | 68 ms | Viable if SLO permits |
| C | 4 | 400 Mb/s | 450 Mb/s total | 320 ms | 240 ms | Fails SLO, resource bottleneck |

In Option C, even with very high per-source caps, **useful stream throughput barely scales** because disk/NIC/CPU became the bottleneck, while business latency surges.

This does not prove Option B is optimal for every cluster. With heavy tombstones, slower disks, different RF, or narrower WAN links, the optimum shifts. Also measure **time to successful repair completion**, not just the stream speed column.

### What Must a Good Experiment Hold Constant?

- Same schema, partition keys, query shapes, and representative dataset.
- Same RF/CL/local DC, repair mode, token ranges, and source/target replicas.
- Same CQL traffic or reproducible load profile.
- Same Cassandra/JVM version and equivalent disk/cache state.
- Track error rates, timeouts, stream failures, and repair coverage too.
- Compare across full background cycles; do not conclude from a brief burst.

## 15. Observing from Java Driver 4.x

Java applications should measure the **full client request path** to reflect SLOs and identify coordinators. Example reading one partition with Java Driver 4.x:

```java
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.metadata.Node;

public final class EventReadProbe {
    private final CqlSession session;
    private final PreparedStatement prepared;

    public EventReadProbe(CqlSession session) {
        this.session = session;
        this.prepared = session.prepare(
            "SELECT event_time, event_id, event_type, payload " +
            "FROM lab.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT ?"
        );
    }

    public int readDay(String deviceId, LocalDate day) {
        BoundStatement statement = prepared.bind(deviceId, day, 50)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true)
            .setPageSize(50);

        long startNs = System.nanoTime();
        try {
            ResultSet result = session.execute(statement);
            Node coordinator = result.getExecutionInfo().getCoordinator();

            int count = 0;
            for (Row row : result) {
                count++;
            }

            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startNs);

            System.out.printf(
                "read_ms=%d count=%d coordinator_dc=%s%n",
                durationMs,
                count,
                coordinator == null ? "unknown" : coordinator.getDatacenter());
            return count;
        } catch (RuntimeException ex) {
            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startNs);
            System.err.printf(
                "read_error_ms=%d type=%s%n",
                durationMs, ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
```

Assumes `CqlSession` is configured with valid contact points, authentication, local DC, keyspace, and nodes with RF supporting `LOCAL_QUORUM`. `setIdempotent(true)` is appropriate for this standard SELECT; **do not enable speculative execution blindly**.

This sample logs every request for learning clarity; in production, emit **histograms/metrics with proper sampling and labels** rather than printing on every high-rate call. Always measure **errors** too—tracking only successes hides rising timeouts during heavy streaming.

### Four Parallel Measurements

1. **Java API p99** by operation/customer cohort.
2. **Driver request latency, in-flight/queue, timeouts/retries**, and coordinator host/DC.
3. **Cassandra client request latency** per node and read/write type.
4. **Replica resource metrics** on nodes participating in streaming/validation.

Never subtract `API p99 – Cassandra p99` directly to claim "WAN p99", because quantiles of two distributions do not subtract that way. Accurate attribution requires correlated traces on the same requests, synchronized timestamps, and proper sampling.

## 16. Repair Must Fit Inside the `gc_grace_seconds` Budget

A `DELETE` writes a tombstone to shadow older data in other SSTables/replicas. If an offline replica misses the delete and the tombstone is purged before proper repair/recovery, old values can resurrect (*zombie data*).

Thus, **throttling repair down to keep p99 pretty while repair never finishes is also unsafe**.

### Conservative Time Budget

Let:

- `G`: applicable grace window for at-risk data, typically referencing table-level `gc_grace_seconds`.
- `I`: interval between repair cycle starts.
- `D`: longest duration to complete coverage across required ranges/replicas.
- `F`: contingency buffer for incidents, offline nodes, and retries.
- `M`: safety margin for load variance.

A conservative operational rule:

```text
I + D + F + M < G
```

This is not an internal Cassandra formula; it is a planning tool to keep slow or failing repairs from overrunning the deletion safety window. What matters most is **time since the last successful repair per range/table/DC**, not merely how many jobs started.

Example with `G = 10 days`:

| Component | Plan A | After Over-Throttling |
| --- | ---: | ---: |
| Launch cadence `I` | 4 days | 4 days |
| Completion `D` | 2 days | 4 days |
| Incidents/retries `F` | 2 days | 2 days |
| Margin `M` | 1 day | 1 day |
| Total | 9 days | 11 days |
| Passes conservative rule | Pass | **Fail** |

If throttling extends repair to four days, do not simply accept the new schedule. You must **add capacity, reduce data needing processing, tune concurrency/timing, split ranges smartly, or revisit grace with solid justification**. Never lower `gc_grace_seconds` casually just to GC faster: it shrinks the safety window.

### When a Node Stays Disconnected Long-Term

If a replica was offline longer than grace and may still hold old data, **running late repair does not guarantee eliminating all zombie risk** if necessary tombstones were already evicted on healthy replicas. Evaluate rebuild/replace/restore runbooks matching your version and source state.

## 17. Full vs. Incremental Repair and Resource Cost

Cassandra offers repair modes depending on version:

- **Full repair:** reconciles data across a broader selected scope; can consume more I/O and time.
- **Incremental repair:** focuses on unrepaired data via repaired SSTable tracking and anti-compaction in supporting versions.

Never assume incremental is always cheaper than full in every situation, or that every repair streams many bytes. In well-synchronized workloads, validation/anti-compaction can dominate resource cost.

When sizing throughput/concurrency, record:

1. Exact Cassandra version and full/incremental mode.
2. Participating tables, token ranges, datacenters, and replicas.
3. Repaired vs unrepaired SSTable sizes and mutation churn.
4. Validation volume, streamed bytes, anti-compaction, and successful range outcomes.
5. Overlap risks with other repair/compaction/backup jobs.

One node reporting repair "completed" does not mean the whole cluster is repaired. Track **coverage by token range and replica**.

## 18. Incident Scenarios and Responses

### A — High Streaming Cap Yet Low Network Throughput

**Symptom:** cap was raised, `netstats` still transfers slowly; business p99 does not improve or stays flat.

**Checks:** source disk reads / target disk writes, CPU/TLS, packet loss, other caps (inter-DC, QoS), active stream count, actual data divergence, and validation state.

**Response:** identify the true bottleneck before touching throttles again; stop raising caps if network is not the limiter.

### B — Very Few Bytes Streamed Yet Repair Takes Hours

**Symptom:** replicas are nearly in sync with minimal streaming, yet the job runs for hours.

**Checks:** validation scanning, Merkle trees, SSTable counts, CPU, disk queues, anti-compaction, and range splitting.

**Response:** optimize concurrency and scheduling windows for validation and I/O; raising stream bandwidth will not fix it.

### C — API Read P99 Spikes Right During Repair

**Symptom:** `Pending READ`, disk read await, and pending compactions rise alongside repair.

**Checks:** which replicas receive both CQL traffic and validation, hot partitions, SSTable counts, and tombstones scanned.

**Response:** cut parallel jobs causing replica overlap, shift windows, clear compaction backlogs, or fix schemas/queries causing heavy read amplification.

### D — Writes Time Out While Target Node Streams

**Symptom:** disk write queues, commit log latency, and pending mutations rise; coordinator misses CL ACKs.

**Checks:** target storage bandwidth/headroom, flushes, compaction, RF/CL, and which nodes hold those partitions.

**Response:** ease stream write pressure and expand disk capacity; applications must treat write timeouts as **uncertain outcomes** and avoid blindly retrying non-idempotent operations.

### E — Adding a New DC Slows Down the Existing DC's App

**Symptom:** source DC sends excessive streams to the new DC, saturating WAN or source disks.

**Checks:** inter-DC throttle, concurrent sending source nodes, impact on business replication, and failover readiness.

**Response:** cap aggregate traffic to real link capacity, phase rebuilds, track replication lag/freshness, and do not route client traffic to the new DC before verifying ranges.

### F — Raising Concurrency Makes Repair Slower

**Symptom:** more concurrent sessions cause stream errors/retries and higher GC/compaction; total cycle runtime lengthens.

**Checks:** replica overlap, CPU throttling, disk await, and NIC saturation; measure **successfully completed ranges/hour**.

**Response:** lower concurrency, schedule ranges to avoid overlapping replicas, and favor steady throughput over unsustainable burst rates.

### G — Throttling Too Low Prevents Repair from Meeting Grace

**Symptom:** p99 stabilizes after throttling, yet unrepaired ranges approach the safety deadline.

**Checks:** last successful repair history, table `gc_grace_seconds`, offline node age, duration forecast, and recovery margin.

**Response:** add capacity, prioritize at-risk ranges, shift load, or adjust plans. Never accept a schedule that "meets SLO" if it compromises data correctness.

## 19. Essential Dashboards and Alerts

A tuning dashboard should drill down **cluster → DC → node → job → application**:

| Group | Metrics to Collect | Question Answered |
| --- | --- | --- |
| Streaming | Bytes sent/received, throughput per node/peer/DC, active/error sessions | Where is data moving, and is it stable? |
| Repair | Validation duration, succeeded/failed ranges, time since last success | Is coverage progressing fast enough to meet deadlines? |
| Disk | Read/write latency, queues, IOPS, throughput, free space | Is storage excessively contended? |
| Compaction | Active/pending, bytes processed, backlog | Is background I/O building future debt? |
| CPU/GC | CPU usage, throttling, heap/native, GC pauses | Do nodes still have compute headroom? |
| Network | NIC/WAN throughput, packet loss, retransmits, RTT | Is the link or the node the limit? |
| CQL | Read/write p95/p99, timeouts, unavailable, coordinator/replicas | Are business SLOs impacted? |
| Driver | Request latency, in-flight, errors/retries, local DC | What extra load is the client seeing? |
| Topology | RF/DC, node health, token range ownership | Is the schedule covering the right scope? |

### Three Critical Alerts

1. **Business SLO degradation:** p99 or timeouts cross thresholds while streaming/repair are active.
2. **Repair coverage deadline:** any range/table goes unrepaired too long, leaving insufficient budget before `gc_grace_seconds`.
3. **Resource saturation:** sustained disk await/queues, GC pauses, CPU throttling, or network saturation while useful throughput drops.

Add alerts for repeated stream errors/retries and low disk headroom. When alerting, classify the action: **throttle down jobs/streams** if saturated, or **add capacity/prioritize repair** if deadlines threaten data safety. Never raise timeouts automatically in every situation.

### Metric Aggregation Notes

- Byte and error counters must be converted to **rates**, handling counter resets on node restarts.
- `Cluster-wide p99` is not the average of per-node p99 values.
- Break down by DC/rack so averages never hide one severely degraded replica.
- Use synchronized timestamps to align repair jobs, compaction, GC, and API latency.
- Avoid putting partition keys on all metric labels due to cardinality explosion; use sampling to pinpoint hot partitions.

## 20. Deployable Throttling Runbook

### Before Making Changes

1. Confirm intent: bootstrap, rebuild, replace, or repair; each carries different costs.
2. Check RF, token ranges, DC/rack, source/target replica health, and recent repair history.
3. Baseline CQL p95/p99, timeouts, disk, CPU, network, compaction, and application metrics.
4. Estimate data volume to validate/stream and source–target asymmetry.
5. Check throttle settings, units, node/DC scope, and version runtime support.
6. Establish the completion deadline relative to `gc_grace_seconds` if repairing for tombstone safety.

### During Execution

7. Start with tested job counts and throttles on a narrow scope.
8. Record successful progress per range/node, stream throughput, and validation cost.
9. Monitor p99, timeouts, `tpstats` pending/dropped, disk await, compaction, and GC.
10. If SLOs breach, relieve pressure on the **verified bottleneck**; avoid changing multiple knobs at once.
11. If headroom remains yet the job projects late, step up concurrency/throttles **incrementally** and re-measure.
12. Never launch overlapping repairs hitting the same busy replicas with double load.

### After Completion

13. Verify all intended ranges/replicas repaired/streamed successfully—not just exit code 0.
14. Check post-operation compaction/flush backlogs and free disk space.
15. Compare p95/p99/error rates against baseline to verify no lingering slowdown remains.
16. Validate data/replicas before shifting traffic, especially after a datacenter rebuild.
17. Save final settings, metrics, scope, duration, and retry notes for the next cycle.

**Never manually delete SSTables, force `gc_grace_seconds=0`, or trigger cluster-wide major compaction/repair just to test throughput.** Those operations carry data and resource risks requiring dedicated runbooks.

## 21. Common Misconceptions

**"The more GiB/s repair streams, the better."** False. Repair also involves validation and must meet both SLOs and completion deadlines; excessive streaming triggers errors and spikes p99.

**"Zero streaming means repair uses no I/O."** False. Validation can still read vast amounts of SSTables even when replicas are completely identical.

**"`setstreamthroughput` sets a cluster-wide bandwidth cap."** Never assume this. It typically applies per node/outbound direction, and multiple sources can still sum their traffic on shared links.

**"Setting a low streaming throttle guarantees safe CQL."** False. Validation, anti-compaction, compaction, and CPU can still contend for resources.

**"If repair saturates the network, `LOCAL_QUORUM` is immune."** False. Local replicas still share disk/NIC/CPU; cross-DC traffic can also lag, hurting data freshness and failover.

**"Empty `nodetool netstats` means repair is finished."** False. Repair could be in validation, paused, failed, or incomplete across ranges.

**"Raising concurrency from 2 to 8 makes jobs 4x faster."** Doubtful. Replica overlap, disk, and network contention can actually lengthen total runtime.

**"Disk still has free space, so we can stream at max speed."** False. Free space is not IOPS/throughput/latency, and compaction still needs headroom.

**"Just increase application timeouts while repair runs."** False. Long timeouts mask congestion and pile up in-flight requests without improving throughput.

**"Full and incremental repairs cost the same."** False. Validation scope, SSTable state, and anti-compaction vary by mode and version.

**"Running repair once on N1 repairs the entire keyspace."** False. Verify token-range ownership, DCs, and completion across all required replicas.

**"Throttling repair down whenever p99 rises is always safe."** False if completion deadlines before `gc_grace_seconds` can no longer be met.

## 22. Practical Exercises

1. A repair validates 1 TiB of data yet streams only 500 MiB. Why might doubling `setstreamthroughput` fail to shorten repair time?
2. Distinguish GiB scanned, GiB streamed, and token ranges repaired successfully. Which metric directly reflects coverage?
3. An inter-DC link has 400 Mb/s headroom. Four source nodes are each capped at 150 Mb/s. Why can aggregate traffic still congest the link?
4. By simple arithmetic, how many MB/s is 160 Mb/s? Why should you not assume that equals actual TCP throughput?
5. When disk read await, pending READs, and API p99 rise together during repair, in what order do you verify causality?
6. Why can a `LOCAL_QUORUM` coordinator in dc1 still be impacted by streaming between dc1 and dc2?
7. If the destination disk is write-saturated, will raising the outbound cap at the source solve it?
8. Repair runs two coordinators that both touch replica N2. Why must concurrency be bounded per *replica* rather than per coordinator alone?
9. A cluster has a 10-day grace window: `I=4`, `D=4`, `F=2`, `M=1`. Does the schedule pass the conservative rule? Name at least two ways to fix it.
10. Compare throttling streaming throughput vs throttling compaction throughput; why can't one automatically substitute for the other?
11. The Java Driver logs `LOCAL_QUORUM` timeouts during repair. Why can blind retries cause duplicate effects or worsen load?
12. If `netstats` shows many active streams yet p99 hasn't changed, what additional metrics do you need before raising the cap?
13. Plan an experiment testing three streaming throttle levels, specifying required metrics and mandatory stop conditions.
14. After rebuilding dc2, `netstats` is empty and every node is `UN`. What else must you verify before routing client reads to dc2?
15. Explain why cluster p99 cannot be calculated by averaging every node's p99.
16. Design a runbook when repair slows down due to validation I/O while very little time remains before grace expires.

## 23. Summary Decision Diagram

```text
                  STREAMING / REPAIR IN PROGRESS
                              |
               +--------------+---------------+
               |                              |
       Is repair progress on track?    Are API SLOs met?
               |                              |
        +------+-----+                 +------+------+
        |            |                 |             |
       Yes          No                Yes           No
        |            |                 |             |
  Keep measuring  Find bottleneck      |        Locate CPU,
  and verify      (validation? stream? |        disk, net, GC,
  coverage        CPU/disk/network?)   |        replica overlap
        |            |                 |             |
        +------------+-----------------+-------------+
                              |
             Adjust throttle / concurrency / schedule
             based on metrics; change one knob at a time
                              |
                Verify p99 + timeouts + coverage
                              |
               Ensure deadline before gc_grace
```

**Takeaway:** **Streaming throughput** describes data transfer speed, whereas **useful repair throughput** must account for validation, streaming, anti-compaction, and the rate of successfully completed token ranges. Bandwidth throttles control only part of background cost; **CPU, I/O, network, concurrency, and replica placement** govern the impact on Cassandra queries. Good tuning keeps **application p95/p99 and timeouts within SLO**, while ensuring **repair finishes with a safe margin before `gc_grace_seconds`**.
