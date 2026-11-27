# Load Testing During Bootstrap, Streaming, Repair, or Backup

> **Chapter:** Load and Distributed Fault Testing  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Context:** Apache Cassandra is a distributed wide-column database. Understanding partition keys, query-driven table design, replication, read/write consistency levels, CQL, compaction, repair, and the Java Driver is essential for accurately measuring the impact of operational tasks.  
> **Focus:** Designing and executing load tests **before, during, and after** node bootstrap, SSTable streaming, repair, and backup without mistaking background task completion for user-facing service quality.

## 1. Problem: The Cluster Is Up, Yet API Latency Jumps Multiple Times

A Cassandra cluster serves an API writing events and reading tenant history. Normally, the request success rate is high and p99 latency is stable. Operations adds a node to expand capacity; during **bootstrap**, the new node must receive data from existing replicas. At the same time, the system may be:

- Reading SSTables and transmitting data over the network.
- Writing streamed data to disk on the receiving node.
- Running compaction, flushes, repair, or housekeeping.
- Handling CQL requests from the Java application across coordinators/replicas.
- Experiencing shifting replica counts/token ranges and load balancing as topology transitions.

A dashboard that merely shows **node UP** or **bootstrap completed** does not tell you whether the API still meets SLOs. A dashboard showing only average CPU can also miss saturated disk I/O, pending tasks, GC pauses, hot partitions, or cross-DC network congestion.

**The question in this lesson is not just “Did the operation finish?” but:**

1. Once the operation starts, how do **successful throughput, p95/p99, and error rate** of the production workload change?
2. Which component becomes the bottleneck: coordinator, replica, disk, network, JVM, compaction, thread pools, or the Java application?
3. **How much headroom does it consume**, how long does it take to finish, and does the cluster return to baseline afterward?
4. Can we continue the operation, throttle it, pause per runbook, or must we **STOP** due to data/quorum risk?
5. After bootstrap/repair/backup, is the data accurate, complete, and **recoverable** within RPO/RTO contracts?

Answering reliably requires **a methodical load experiment**, not a couple of CPU screenshots or a feeling that the system “looks fine.”

### Learning Objectives

After this lesson, you can:

- Describe the differences among **bootstrap**, **streaming**, **repair**, **snapshots**, and **off-cluster backup copy**.
- Plan a **baseline → background task → recovery** measurement using representative CQL workloads and RF/CL.
- Select metrics from **application caller, Java Driver, Cassandra nodes, disk, network, and background resources**.
- Use **nodetool** in read-only observation mode; know which operational commands require authorization and runbooks.
- Write an asynchronous Java load probe with bounded in-flight requests.
- Track **success throughput, error budget, p99, pending tasks, streaming progress, disk headroom**, and stop criteria.
- Distinguish **backup files created locally** from **backups copied off-node, restored, and reconciled**.
- Interpret results to decide maintenance windows, topology changes, and capacity planning.

> **Safety boundary:** Bootstrap, decommission, rebuild, repair, fault-injection, and heavy backup load tests must only run on an **approved staging/lab cluster** or inside dedicated production change windows/runbooks. This lesson **does not ask** you to stop replicas, break networking, change tokens/RF, or run repairs on a live production cluster just to practice.

## 2. Which Operational Mechanisms Generate What Load?

### 2.1. Bootstrap: A New Node Joins and Receives Token Ranges

When a node joins a Cassandra cluster via bootstrap, the cluster places data according to token ranges and replication rules. The new node typically receives SSTable data via **streaming** from eligible source nodes. Meanwhile, topology status may display the node as **JOINING** before entering normal serving state; exact behavior depends on version and topology.

Consequences to measure:

- **Sending nodes:** disk reads, outbound network, CPU, and metadata/streaming tasks.
- **Receiving node:** inbound network, SSTable writes, disk I/O, free disk space, CPU, and follow-on background work.
- **Cluster:** coordinator overhead, ownership/token map shifts, read/write p99, pending compactions, and availability.
- **Clients:** driver topology discovery and load balancing, new connections, node health tracking, and transient errors during transition.

**Never conclude** “adding a node immediately reduces load.” During bootstrap, existing nodes can work harder because they **simultaneously serve CQL and stream data outward**. Headroom before the operation matters more than node count after it finishes.

### 2.2. Streaming: Transferring SSTables Between Nodes

**Streaming** is the data-transfer mechanism between nodes, triggered during bootstrap, rebuild, node replacement/decommission, repair, and certain rebalancing operations depending on version and configuration.

Signals to observe:

- Active **bytes/files/sessions** being sent/received and actual transfer rate.
- Disk reads on senders, disk writes on receivers.
- Network throughput plus packet retransmissions/errors.
- CPU/GC/native memory and disk/network queues.
- CQL workload read/write latency under resource contention.

**Do not equate streaming with repair**: repair includes comparison and synchronization across replicas; streaming may occur as part of repair, yet a streaming session alone does not indicate cluster-wide repair completion.

### 2.3. Repair: Reconciling and Synchronizing Replicas

Cassandra uses **anti-entropy repair** to compare replicas owning the same token ranges and synchronize differences. Depending on version and strategy, this involves validation, Merkle-tree-related work, streaming sessions, pending compactions, and bookkeeping.

Repair can concurrently consume:

- CPU and I/O to read and compare SSTables.
- Inter-replica network bandwidth.
- Disk space to receive/store streamed data and run compaction.
- Threads, queues, and memory for repair/streaming tasks.
- Replica capacity needed to satisfy **`LOCAL_QUORUM`** requests.

Repair is **not** a backup, cannot undo a valid but mistaken business `DELETE`, and does not create cross-partition ACID transactions. **Full/incremental repair behavior, flags, effects on repaired SSTables, and pause capability** depend on Cassandra version and tooling; consult the runbook for your exact version.

### 2.4. Backup: Snapshots vs Off-Cluster Copies

A **Cassandra snapshot** typically holds hard links to existing SSTables. Taking a snapshot can be faster than copying the entire dataset, yet:

- Snapshots **pin SSTables** so space cannot be reclaimed until snapshots are cleared per lifecycle policy; free disk shrinks over time.
- Local snapshots do not sit **outside the failure domain** of the node or disk.
- Creating a snapshot does not mean a verified backup with checksum/manifest has been shipped to external storage.
- **Backup copy/upload** consumes disk reads, network, CPU (compression/encryption/checksumming), and destination I/O.
- Incremental backups or commitlog archiving, when enabled, have their own storage semantics and space footprint; measure and verify config/version behavior.

Backups are judged by both **impact on live workloads** and **recoverability**; a job reporting “upload succeeded” has not yet proven restores meet RPO/RTO.

### 2.5. Quick Comparison

| Task | Typical load path | Consequences to verify | Invalid inferences |
|---|---|---|---|
| **Bootstrap** | Sender disk read/network, receiver disk write, topology shifts | Node enters expected state, data/tokens and CL work properly, p99 recovers | Adding a node always makes APIs faster right away |
| **Standalone streaming** | Network/disk read-write, sessions, retries | Progress/bytes, no missing data, CQL still meets SLO | Streaming succeeded means all repairs finished |
| **Repair** | Validation I/O/CPU, network, difference streaming | Repair coverage and progress, replica health, correct data | Repair replaces backups |
| **Snapshot** | Metadata/hard links, optional flush per procedure, pinned SSTables | Snapshot manifest, retained size, disk headroom | Local snapshot is safe outside failure domains |
| **Copy/upload backup** | Disk reads, compression/encryption/checksum, outbound network | Independent copy, checksum, restore drill | Copy finished means restore automatically works |

## 3. Load Flow from the Java Application to Cassandra Nodes

~~~mermaid
flowchart LR
    A["Load generator\nCQL / Java Driver"] --> B["Coordinator\nrouting + CL"]
    B --> C["Replica 1\nmemtable/SSTable"]
    B --> D["Replica 2\nmemtable/SSTable"]
    B --> E["Replica 3\nmemtable/SSTable"]
    F["Bootstrap / repair / backup"] --> G["Disk + Network + CPU/GC"]
    G --> C
    G --> D
    G --> E
    C --> H["Compaction, flush, streaming"]
    D --> H
    E --> H
    H --> G
~~~

A statement is routed by **partition key** and token ownership. With **RF = 3** in one DC, a **`LOCAL_QUORUM`** request typically needs responses from **two of three replicas**. Whenever one replica is busy sending SSTables or a disk saturates, requests can stall even while the coordinator shows low CPU utilization.

You can also hit a **hot partition**: thousands of requests targeting one partition and its replica set. In that case, adding nodes will not evenly split hot-key load by itself; you must redesign query-aligned bucketing or sharding.

### 3.1. Four Sources of Measurement Noise

1. **Changing partition key distribution** alters results due to hot tokens rather than repair.
2. **Changing consistency level** alters latency/errors without preserving the same business guarantee.
3. **Changing query/payload shape** alters byte volume or tombstone/collection cost.
4. **Changing load generator count or connection pools** can saturate the client before Cassandra.

Therefore, keep workload, query shape, CL, and data fixtures equivalent across baseline and operational phases. Any mandatory change must be logged explicitly as an **experimental variable**.

## 4. Query-Driven Test Table Design

Illustrative model: a service writing events and reading daily tenant history.

~~~sql
-- Only for lab/staging with matching dc1, RF 3 topology.
CREATE KEYSPACE IF NOT EXISTS load_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS load_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    event_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), event_at, event_id)
) WITH CLUSTERING ORDER BY (event_at DESC, event_id ASC);

-- Point-lookup table for a specific business request.
CREATE TABLE IF NOT EXISTS load_lab.event_by_id (
    tenant_id uuid,
    event_id uuid,
    event_at timestamp,
    event_type text,
    PRIMARY KEY ((tenant_id, event_id))
);
~~~

**Design notes:**

- **(tenant_id, event_day)** is the partition key for history queries. Queries must bind both components; day acts as a bucket preventing unbounded partition growth.
- **event_at, event_id** are clustering columns: newest first, with ID breaking timestamp ties.
- **(tenant_id, event_id)** is the partition key of a separate lookup table. Multiple tables may be maintained denormalized; dual-writes require proper idempotency and reconciliation.
- **payload** drives row size and network/disk throughput; use synthetic data, never real PII or secrets.
- For extreme hot tenants, daily buckets can still grow large; monitor row count, bytes/partition, and tombstones, and adjust bucketing/sharding if needed.

### 4.1. Prepared Reads and Writes

~~~sql
-- Bounded single-partition read.
SELECT event_at, event_id, event_type, payload
FROM load_lab.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT ?;

-- Insert event using key generated at start of logical request.
INSERT INTO load_lab.events_by_tenant_day (
    tenant_id, event_day, event_at, event_id, event_type, payload
) VALUES (?, ?, ?, ?, ?, ?);

-- Point read by single event ID.
SELECT event_at, event_type
FROM load_lab.event_by_id
WHERE tenant_id = ?
  AND event_id = ?;
~~~

The load suite must **preload data in a dedicated step** with stable key distribution before measuring. Reading empty partitions looks fast yet **does not represent** workloads crossing multiple SSTables/tombstones. Conversely, hammering a single partition measures a **hotspot** rather than normal throughput.

### 4.2. Controlling Schema, Keyspace, and Fixtures

- Create schema/keyspace **before the baseline**, not DDL executed from every client at benchmark start.
- Mark preload complete and verify row counts / partition samples.
- Keep data types, payload sizes, TTL/tombstone distributions, and read/write ratios constant across comparison runs.
- Never use **`ALLOW FILTERING`** to build an unpredictable workload and draw latency conclusions from it.
- Never add indexes/secondary tables or switch compaction strategies between runs when isolating bootstrap impact.
- If production workloads use TTLs/tombstones, build a representative fixture and track read amplification separately.

## 5. Defining Workload Profiles and Resources

No single “generic Cassandra benchmark” fits every application. Choose at least two profiles:

| Workload | Purpose | Elements to keep constant |
|---|---|---|
| **Representative mix** | Mirrors live traffic: e.g., 70% reads, 30% writes | Query shapes, partition distribution, row size, CL, page size |
| **Read-heavy** | Exposes read p99 and tombstone/SSTable pressure | Partition distribution and result sizes |
| **Write-heavy** | Exercises commitlog/memtable/flush/compaction | Mutation bytes/s, batches, concurrency |
| **Hot-partition case** | Probes limits when one tenant spikes | Hot key list and skew ratio |
| **Bulk/batch job** | Models real backfill/export pressure | Bounded parallelism, retry budget, deadlines |
| **Control workload** | Reference baseline without maintenance tasks | Same code, driver, cluster size, capacity |

Ratios like **70/30, N requests/s, page size 100** here are purely illustrative. Acceptance numbers must match your actual SLOs, queries, and datasets.

### 5.1. Two Load-Generation Models

- **Open-loop:** dispatches requests at a target **arrival rate**, measuring rejections and timeouts too. Reveals how the system behaves when incoming demand does not slow down with latency.
- **Closed-loop:** N workers send the next request only after the previous finishes. When the server slows down, offered load drops automatically, which can **hide saturation** if you only inspect error rate.

Use both where possible and state clearly which model you ran. Simply spawning **N threads** and reporting “1,000 ops/s” without separating sent, completed, and dropped counts produces misleading numbers.

### 5.2. Client-Side Guardrails

The Java Driver supports async execution, yet **async does not make unbounded in-flight requests safe**. You need:

- Bounded **in-flight limits** (`Semaphore`/concurrency control) and bounded queues.
- Bounded **arrival rate**, timeouts, and attempt limits.
- Separate tracking of **logical requests** vs **physical driver attempts/retries**.
- For paging queries, measure both **first-page latency** and **full-result latency**; never measure only `executeAsync` of page one.
- Never co-locate the load generator, Cassandra nodes, and backup tools on one machine where generator CPU/disk/NIC saturation skews conclusions.

## 6. Controlled Measurement Scenario

Each run needs at least three phases:

~~~mermaid
flowchart TD
    A["Preflight: schema, RF/CL, node health, free disk"] --> B["Warm-up + steady workload"]
    B --> C["Baseline: capture p50/p95/p99 and throughput"]
    C --> D["Single task: bootstrap / stream / repair / backup"]
    D --> E["Hold same workload and record time-series metrics"]
    E --> F{"Stop gate breached?"}
    F -->|Yes| X["Stop load / intervene per runbook"]
    F -->|No| G["Task completes and is verified"]
    G --> H["Recovery window: measure time back to baseline"]
    H --> I["Compare, archive evidence, and decide GO/NO-GO"]
~~~

**Benchmark each task independently before testing overlaps.** If repair and backup run together and p99 spikes, you cannot tell each task's share without single-task baselines and control runs. Hold workload and inputs constant across runs and repeat when necessary to account for variance.

### 6.1. Recommended Experiment Matrix

| Case | CQL workload | Background task | Additional metrics to capture |
|---|---|---|---|
| **C0** | Representative mix | No new maintenance task | Baseline and existing background noise |
| **B1** | Same mix | Bootstrap one lab node | Streaming bytes, JOINING → NORMAL transition, p99 |
| **S1** | Same mix | Approved lab streaming procedure | Sender/receiver disk/network, progress |
| **R1** | Same mix | Scoped token-range repair | Repair sessions, validation, streaming/compaction |
| **P1** | Same mix | Controlled local snapshot | Snapshot duration, pinned/free disk |
| **P2** | Same mix | Off-node backup copy | Copy throughput, network/disk, checksums |
| **C1** | Same mix | No new task, post-operation | Recovery duration, p99, backlog |
| **X1** | Same mix | Deliberate repair + backup overlap | Resource interaction; run only after isolated tests |

**C0/C1 do not mean zero background compaction**: Cassandra continues normal housekeeping. The goal is measuring under consistent real background behavior while logging confounding events.

### 6.2. Warm-Up, Duration, and Repeated Runs

- Warm up long enough for driver connection pools, caches, memtables/GC, and instrumentation to stabilize; avoid measuring just the first few seconds.
- Measure baseline across multiple 1–5 minute windows aligned with service SLOs rather than taking a single p99 snapshot.
- Operational tasks can take hours. Use durable dashboards/recordings and slice results across load and progress phases.
- Run **at least several repetitions** in staging when comparing config changes; natural variance in disk/GC/compaction must be acknowledged.
- Never start the next run before the cluster returns to normal state and disk headroom recovers.

## 7. What to Measure: Metrics from Caller to Node

Operational testing is only trustworthy when **system changes correlate directly with application impact**. Collect before/during/after metrics at matching time granularity.

### 7.1. Caller and Java Driver Metrics

| Group | Metrics | Interpretation |
|---|---|---|
| **Traffic** | Offered RPS, accepted RPS, successful completed RPS | Separates incoming demand from served throughput |
| **Latency** | p50, p95, p99, max, first-page/full-result | Did users see tail latency while background work ran? |
| **Errors** | Timeout, ReadFailure/WriteFailure, Unavailable, Overloaded | Missing replicas/CL, overload, or client deadlines? |
| **Concurrency** | In-flight count, client queue depth/wait, shed/rejected | Is work backing up inside the driver or app? |
| **Retries** | Service/driver/gateway retries, speculative executions | Is physical traffic being amplified? |
| **Connections** | Pool/channel utilization, reconnects, coordinator/DC | Did topology shifts trigger excessive client churn? |
| **Paging** | Pages/query, rows/page, per-page latency | Do multi-page queries degrade on later pages? |
| **Correctness** | Missing/duplicate events, failed invariants, stale reads | Never trade data integrity for higher throughput |

**Rising p99 alongside falling success rate** is especially deceptive: recording latency only for succeeded requests excludes timed-out requests from histograms. Always place **error rate and deadline-exceeded counts** beside percentiles, distinguishing success-only latency from client-observed latency.

### 7.2. Cassandra Cluster Metrics

| Layer | Metrics / observations | Why it matters |
|---|---|---|
| **Coordinator** | Read/write latency, request counts, failures, timeouts | Is the CL contract still met? |
| **Replica** | Local read/write latency, thread pools, pending/dropped tasks | Which replica became the bottleneck? |
| **Disk** | Read/write bytes/s, IOPS, await/latency, queue depth, utilization, free | Bootstrap/repair/backup competing with CQL |
| **Network** | In/out bytes/s, cross-node/cross-DC traffic, retransmits, packet drops | Is streaming saturating NICs or WAN links? |
| **JVM** | Heap, off-heap/native RSS, GC pauses, CPU | Are buffers/GC causing tail latency? |
| **Storage internals** | SSTable count, active/pending compactions, memtable/flushes | How did SSTable count and background I/O change? |
| **Streaming** | Active sessions, bytes/files sent/received, progress, failed/retried transfers | Is data transfer progressing or stalled? |
| **Repair** | Sessions/ranges completed, validation/streaming metrics, failures | Does repair progress/coverage match plan? |
| **Backup** | Snapshot count/size, pinned SSTables, copied bytes, checksum failures, remote storage | Can data recover without exhausting disk? |
| **Topology** | Node status, DC/rack, RF, token ownership, schema agreement | Do SLOs reflect healthy full-replica topology? |

Exact metric names vary across **Cassandra versions, JMX exporters, monitoring stacks, operators, and managed services**. Never invent Prometheus metric names and assume they exist; inspect the **cluster's actual metrics registry** and document the real mapping.

### 7.3. Separating Measurement Phases Along the Timeline

Emit milestone markers from the orchestrator:

~~~text
T0: cluster healthy, warm-up finished
T1: baseline started
T2: baseline ended, background task started
T3: streaming/repair/backup reaches peak load
T4: background task reports completion
T5: integrity checks and background backlog verification
T6: API p99/error/throughput return to baseline thresholds
~~~

**Post-task recovery time = T6 − T4**, and it is rarely zero. Compaction backlog, retained files, cache churn, or driver reconnects can linger well after the CLI tool reports done.

## 8. Safe Cassandra Observation Commands During Testing

Use read-only metadata/metric commands supported by your running version:

~~~bash
# DC/rack/token layout and node state.
nodetool status

# Node info and heap/off-heap/disk summary.
nodetool info

# Active streaming and network tasks, as supported by version.
nodetool netstats

# Thread pools, pending and dropped messages.
nodetool tpstats

# Active compaction and backlog.
nodetool compactionstats

# Keyspace/table stats.
nodetool tablestats load_lab.events_by_tenant_day

# Partition/row size distributions per version.
nodetool tablehistograms load_lab events_by_tenant_day

# Existing snapshots; verify naming/paths for your version.
nodetool listsnapshots
~~~

**`nodetool` outputs are only one slice of evidence**, never a replacement for Java application histograms or OS-level disk/network telemetry. For example:

- **`nodetool status`** shows Up/Down/Joining/Leaving from the node perspective, yet Up never guarantees good p99.
- **`nodetool netstats`** shows active streaming; **never infer real throughput** from a single counter snapshot—sample repeatedly and compute deltas over time.
- **`nodetool tpstats`** reveals rising pending/dropped tasks; correlate with baseline and request errors to pinpoint bottlenecks.
- **`nodetool compactionstats`** shows compaction jobs, yet disk device latency still requires OS telemetry.
- **`nodetool listsnapshots`** lists local snapshots; it says nothing about whether backups reached remote storage intact.

Commands like **`nodetool repair`**, **`rebuild`**, **`decommission`**, **`cleanup`**, node join/replace actions, **`snapshot`**, and **`clearsnapshot`** mutate cluster state or retained files. **Never treat them as diagnostic read commands**; execute them only through authorized operators with approved runbooks and change windows. In particular, **`clearsnapshot`** can destroy recovery points before external backups finish.

### 8.1. OS-Level Observations

On Linux nodes, VMs, or containers with valid telemetry access, collect:

- Disk read/write throughput, per-device latency (`await`), and queue depth.
- Per-interface network in/out rates and retransmissions/drops.
- CPU user/system/iowait, memory, file descriptors, and cgroup throttling.
- GC duration/pauses, heap/off-heap memory, and compaction I/O.
- Free disk space **before and during** operations, separating data directories, snapshot directories, and separate filesystems if present.

**Never assume 50% CPU means 50% headroom.** An SSD can already hit its IOPS limit or extreme p99 I/O latency while CPU stays low. Similarly, partially utilized NICs can suffer retransmits, queuing, or WAN RTT spikes across DCs.

## 9. Bounded Asynchronous Java Load Probe

The snippet below is a **load-harness component**, not a full production benchmark suite. It:

- Shares a single **`CqlSession`** and **`PreparedStatement`**.
- Reads a preloaded partition at **`LOCAL_QUORUM`**.
- Bounds in-flight requests with a **`Semaphore`**.
- Records **first-page latency**, success/failure/rejection counts, and histograms via **Micrometer `Timer`**.
- Performs no application-level retries; still review the driver's configured retry policy.
- Never blocks driver callbacks with **`join`/`get`/`sleep`**.

### 9.1. Probe Code

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class BoundedReadProbe {
    private final CqlSession session;
    private final PreparedStatement select;
    private final Semaphore slots;
    private final Timer firstPageLatency;

    private final LongAdder successes = new LongAdder();
    private final LongAdder failures = new LongAdder();
    private final LongAdder rejected = new LongAdder();

    public BoundedReadProbe(
            CqlSession session, MeterRegistry registry,
            int maxInFlight) {
        if (maxInFlight <= 0) {
            throw new IllegalArgumentException(
                "maxInFlight must be positive");
        }
        this.session = session;
        this.slots = new Semaphore(maxInFlight);
        this.select = session.prepare(
            "SELECT event_at, event_id, event_type, payload " +
            "FROM load_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

        this.firstPageLatency = Timer
            .builder("cassandra.load.first_page")
            .description("Latency of first Cassandra result page")
            .publishPercentileHistogram()
            .register(registry);
    }

    public CompletionStage<AsyncResultSet> tryRead(
            UUID tenantId, LocalDate day) {

        if (!slots.tryAcquire()) {
            rejected.increment();
            return failed(new RejectedExecutionException(
                "Load probe in-flight limit reached"));
        }

        final long started = System.nanoTime();
        try {
            BoundStatement query = select
                .bind(tenantId, day, 100)
                .setPageSize(50)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            return session.executeAsync(query)
                .whenComplete((page, error) -> {
                    try {
                        firstPageLatency.record(
                            System.nanoTime() - started,
                            TimeUnit.NANOSECONDS);
                        if (error == null) {
                            successes.increment();
                        } else {
                            failures.increment();
                        }
                    } finally {
                        slots.release();
                    }
                });
        } catch (RuntimeException error) {
            failures.increment();
            firstPageLatency.record(
                System.nanoTime() - started,
                TimeUnit.NANOSECONDS);
            slots.release();
            return failed(error);
        }
    }

    public long successes() { return successes.sum(); }
    public long failures() { return failures.sum(); }
    public long rejected() { return rejected.sum(); }

    private static <T> CompletionStage<T> failed(
            Throwable error) {
        java.util.concurrent.CompletableFuture<T> result =
            new java.util.concurrent.CompletableFuture<>();
        result.completeExceptionally(error);
        return result;
    }
}
~~~

**Dependencies:** compatible Java Driver 4.x and Micrometer Core versions. **`CqlSession` must be built and configured with TLS/auth, local DC, contact points, and lifecycle management** by the test application before passing it to the probe. A single Java process should share the session; never open a new session per request.

**Important:** Success here means **the first result page arrived**, not that all rows across pages were consumed. If production workloads read multiple pages, **chain `fetchNextPage()` through the final page**, measure **full-result latency**, and release the permit only after the entire pipeline completes; otherwise results will look overly optimistic.

### 9.2. Generating Rate Safely

A load scheduler or worker pool controls the **arrival rate** and selects **`tenantId/day`** keys from the preloaded fixture. Never write a loop launching millions of **`CompletableFuture`** tasks and awaiting them all at the end.

Pseudocode:

~~~text
Test load: 500 logical reads/s, max 80 in-flight requests
Each second:
    pick partition keys from fixed distribution (normal + hot)
    check rate budget and admission slot
    if no slot left: record rejected, DO NOT queue unboundedly
    if admitted: invoke probe.tryRead(key, day)
    record result status or exception class

At end of each phase:
    stop dispatching new requests
    wait for outstanding operations within a bounded deadline
    preserve histograms, error counts, and run ID
~~~

**Never report only “500 requests scheduled.”** Record **offered, admitted, succeeded, failed, and rejected**. If the client rejects 20% due to exhausted slots, successful throughput is far below the nominal dispatch rate.

### 9.3. Avoiding Harness-Induced Distortion

- Run the load generator on a dedicated machine with sufficient CPU/network, never sharing disks with Cassandra nodes.
- Preload fixtures and warm up before measuring; avoid expensive UUID generation or heavy payload serialization inside callbacks.
- Monitor generator CPU, GC, connection pools, and queues; if the generator saturates, numbers no longer measure Cassandra alone.
- Keep Java driver version, timeouts, retry policies, CL, and prepared statements identical across runs.
- Micrometer histograms reveal latency distributions, yet verify **sampling/export/percentile configuration** and bucket resolution; **never substitute mean latency for p99**.
- For Spring Boot services exposing built-in metrics, measure directly at API endpoints too and cross-check against the probe; the probe alone does not replace **end-to-end SLA testing**.

## 10. Mixed Read/Write Workloads and Data Correctness During Benchmarks

A `SELECT`-only workload misses production flush/commitlog pressure; an `INSERT`-only workload fails to reproduce multi-SSTable/tombstone read-path overhead. Use a mixed profile:

~~~text
Logical operation mix (example):
  65% SELECT by tenant + event_day
  25% INSERT new event with stable event_id
  10% point SELECT by tenant + event_id

Recorded per operation:
  query_shape, logical_request_id, key_distribution_group,
  regular_consistency, elapsed_ms, result_state,
  driver_attempts_observed, payload_bytes_group
~~~

These are **illustrative ratios**. If dual-writing two tables, track total mutations and avoid confusing **one logical event** with **two physical writes**. When retrying after a timeout:

- Keep **`event_id` fixed** across retries of new writes; never mint duplicate IDs.
- Mark **`setIdempotent(true)`** only on verified-safe mutations (key/value/timestamp/TTL and side effects).
- On **`WriteTimeout`/`WriteFailure`**, the outcome may be `UNKNOWN`; do not treat it as “definitely unwritten.”
- Count **successful logical operations** rather than summing raw driver attempts as business completions.

If the test requires end-to-end once-only semantics, add **idempotency keys, verification queries, and service-level reconciliation**. Pushing high throughput while losing or duplicating records fails quality criteria.

## 11. Correlation Matrix: Connecting Events to Impact

| Observed symptom | Inspect further | Testable hypothesis |
|---|---|---|
| p99 rises while success RPS falls | Disk await, streaming network, pending reads | Streaming competes for disk/network with CQL |
| p99 rises despite low CPU | Disk latency/queue, GC pauses, replica skew | Bottleneck lies outside average CPU |
| Sender outbound network spikes | `netstats` sessions, retransmits, cross-DC traffic | Bootstrap streaming consumes link capacity |
| Pending compactions jump post-stream | SSTable count, free disk, compaction throughput | Receiving node bears heavy post-copy compaction load |
| Repair duration grows abnormally | Repair ranges, validation time, I/O, failed sessions | Resource contention or hot token range |
| Snapshot finishes fast yet free disk drops | Snapshot size, SSTable retention, backup copy status | Snapshots pin old SSTables before scheduled cleanup |
| Backup upload slows while read latency worsens | Backup read I/O, NIC utilization, checksum CPU | Chunk reading/checksumming saturates resources |
| Client timeouts rise without matching server timeouts | Client queue, driver timeout, retries, network | Bottleneck on client or network path |
| `LOCAL_QUORUM` errors jump when a node drops | RF, node status, coordinator logs | Insufficient replicas or CL timeout |
| Missing data appears on reads after topology change | Schema, token ownership, CL, fixtures, logs | Investigate correctness immediately; don't just raise timeouts |

These are **working hypotheses**, not automatic proofs of causation. Correlate timelines, compare against baselines, and confirm with controlled or repeated runs.

## 12. Preflight: Conditions Required Before Starting

Before running each case, document:

1. **Environment and authorization:** which staging/lab cluster, operator identity, and formal approval.
2. **Topology:** Cassandra version, node count, DC/racks, keyspace RF, and Java Driver local DC.
3. **Node health:** zero unexpected `DOWN` nodes, healthy gossip, and schema agreement.
4. **Data readiness:** fixtures preloaded, realistic partition/hotkey distribution, recent restorable backup.
5. **Disk headroom:** sufficient space for incoming streaming, pinned snapshots, and compaction—not just current data size.
6. **Capacity headroom:** network, disk IOPS, CPU/GC well below saturation at baseline.
7. **Monitoring:** time-aligned metrics and dashboards covering p99, errors, streaming, compaction, and backups.
8. **Load generator:** verified non-bottlenecked client with a working kill switch.
9. **Stop/rollback plan:** decision owner, stop criteria, and which operations **cannot be safely aborted mid-flight**.
10. **Data correctness:** fixtures/hashes/counts and pre/post reconciliation method ready.
11. **Concurrent jobs:** scheduled compactions, repairs, backups, or ETL that could add noise; log them rather than blindly killing jobs.
12. **Version-specific operations:** verified exact `nodetool`/operator syntax and limits for this cluster.

If the baseline is already overloaded or free disk is dangerously low, declare **NO-GO** for heavy bootstrap/repair testing. This lesson never recommends pushing an under-provisioned cluster until it breaks without headroom or a recovery path.

## 13. Case B1 — Measuring Load During Node Bootstrap

### 13.1. Objective and Scope

Question: **Does adding a new node while keeping the CQL workload steady breach p99 or error budgets?** Alongside that, verify token-range/data transfer completes safely and measure post-bootstrap recovery time.

Execute only in staging matching production topology under a DBA/SRE-approved scale-out plan. Never add a node merely by bumping a container replica count without verifying tokens, seeds, DC/rack, replication, disk capacity, and Cassandra version.

### 13.2. Test Steps

1. **Preflight:** verify node count, DC/rack, RF, schema agreement, disk headroom, SSTable counts, GC, compaction, and Cassandra/SSTable versions.
2. **Preload:** load enough synthetic data to drive meaningful streaming within lab limits; never use real customer data.
3. **Baseline:** run the representative read/write mix at the locked arrival rate. Capture p50/p95/p99, successful RPS, failures, retries, in-flight, and OS metrics.
4. **Mark T2:** record the exact time the operator initiates bootstrap via the supported, approved procedure.
5. **Monitor every window:** `nodetool status`/`netstats`, bytes sent/received, sender/receiver disk, network, pending compactions, and CQL p99/error rate.
6. **Do not increase load generator rate** mid-run just because Cassandra now has an extra node. You are measuring topology transition impact, not capacity under simultaneous load growth.
7. **Once bootstrap finishes:** verify expected node status, token ownership/replica placement, schema agreement, and zero unresolved failed streaming sessions.
8. **Recovery window:** maintain the workload for a bounded post-window, tracking pending tasks/compactions, free disk, and p99 returning to baseline.
9. **Reconcile:** read fixture partitions across diverse token ranges; never rely solely on node `UP`.
10. **Report:** summarize bootstrap duration, peak network/disk load, worst p99/error rate, recovery time, and data verification results.

### 13.3. Observable Outcomes

| Phase | Hypothetical observation | Verification needed |
|---|---|---|
| Before bootstrap | Stable p99, disk/network below limits | Valid baseline |
| Receiving SSTables | High sender disk read, high receiver disk write | Streaming competing with workload |
| Streaming nearly done | p99 stays elevated, pending compactions high | Post-stream housekeeping still active |
| Node enters normal state | `netstats` idle, node `UP/NORMAL` | Not yet proof API latency recovered |
| After 15–30 minutes | p99/throughput and queues return to baseline | Evidence of recovery |

**15–30 minutes** is purely illustrative; actual windows depend on data size and background load and should never be a rigid pass/fail cutoff on their own.

### 13.4. What Not to Do

- Do not alter **RF** just to make bootstrap look faster; RF changes require separate controlled testing.
- Do not flip **`LOCAL_QUORUM` → `ONE`** in the generator to suppress errors without documenting the experimental variable change.
- Do not treat “bootstrap finished” as a substitute for data validation and API latency recovery.
- Do not bootstrap multiple nodes simultaneously before benchmarking a single node; concurrent streams compound load.
- Do not trigger ad-hoc repair, cleanup, or token moves mid-bootstrap just because progress looks slow, unless official runbooks instruct it.
- Do not assume hot partitions are cured afterward: hot traffic still hits the replica set owning that token range.

## 14. Case S1 — Measuring Standalone Streaming

Streaming occurs within bootstrap (Case B1), and also during rebuild, node replacement/decommission, or repair via supported workflows. Separate two measurements:

- **Streaming inside bootstrap:** keeps full topology-change context.
- **Isolated SSTable transfer cost:** run another approved lab streaming operation and record the exact trigger.
- **Never simulate “streaming” by manually copying SSTable files into data directories**; that risks corruption and misrepresents the streaming protocol.

### 14.1. Key Metrics

1. **Bytes to transfer:** expected data across token ranges or repaired SSTables.
2. **Effective throughput:** completed bytes divided by elapsed time, split inbound vs outbound.
3. **Concurrent sessions:** failed/retried sessions and tail session duration.
4. **Sender disk reads / receiver disk writes:** IOPS, disk latency, and free space.
5. **NIC throughput and retransmissions:** per inter-node link, especially across DCs or WANs.
6. **Concurrent CQL p99/errors:** queue/in-flight levels and retry amplification.
7. **Compaction backlog:** plus whether snapshots/backups are pinning SSTables.

For example, transferring **120 GiB** at **60 MiB/s** effective throughput:

~~~text
120 GiB = 122,880 MiB
122,880 MiB / 60 MiB/s = 2,048 seconds ≈ 34.1 minutes
~~~

This is strictly an **idealized lower bound** from data size and average rate; protocol overhead, concurrency, validation, retries, resource contention, rate variance, and SLO throttling all extend wall time. **Never present this formula as a guaranteed completion forecast.**

### 14.2. Fastest Possible Streaming Is Not the Sole Goal

Pushing streaming rates until disks saturate can breach read p99 SLOs or trigger timeouts. Consider operational profiles:

| Profile | Bandwidth/background throttling | Priority |
|---|---|---|
| **API-first** | Streaming throttled tightly to preserve headroom | Protects interactive SLOs |
| **Balanced** | Steady headroom reserved for both APIs and transfer | Optimizes duration within guardrails |
| **Maintenance-first** | Uses higher capacity inside approved windows | Appropriate only during low traffic with approval |

Exact streaming throttle knobs depend on Cassandra version and operator tooling. Before changing settings, verify **your version's actual throttling mechanism** on staging instead of copying outdated property names from other versions.

### 14.3. Separating Network Bottlenecks from Disk Bottlenecks

- If **network utilization is low** while disk await is high: bottlenecked by disk reads/writes, flushes, or compaction.
- If disks have headroom while **network saturates or retransmits spike**: inspect NICs, routing, WAN, MTU, and streaming session count.
- If both stay low while progress stalls: inspect failed sessions, node health, error logs, and task queues.
- If client p99 degrades on only a subset of partitions: check coordinator/replica placement and hot token ranges rather than assuming cluster-wide saturation.

A single throughput sample only says “something is busy”; correlate multi-window metrics with progress and SLOs.

## 15. Case R1 — Measuring Load During Repair

### 15.1. Repair Is a Read/Validation/Write Workload, Not Just One Command

Repair must follow organizational consistency policies tailored to Cassandra version, RF/DC, node count, and repair strategy. On test clusters, **only authorized operators** trigger scoped repair sessions—for instance, a specific keyspace/table or defined token ranges.

Record during the run:

- **Repair mode:** full vs incremental or exact tool/operator version.
- **Scope:** keyspaces, tables, token ranges, DCs/hosts as supported.
- **Concurrency:** concurrent repair/validation/streaming sessions.
- **Dataset:** data size, SSTable count, and divergence degree among replicas.
- **Resources:** disk I/O, CPU, network, GC, and compaction backlog.
- **Completion semantics:** which exact ranges finished cleanly and whether any failed.

Never run a **cluster-wide or full-keyspace repair** as a casual quick benchmark without a runbook and capacity plan. Repair can be vastly heavier than local snapshots, especially over large datasets, high SSTable counts, or constrained links.

### 15.2. Three-Phase Breakdown

| Phase | Key metrics | Core question |
|---|---|---|
| **Validation / comparison** | Disk reads, CPU, SSTable I/O, time per range | Slow due to sheer data volume or resource shortage? |
| **Difference streaming** | Bytes sent/received, network, disk writes | How much data diverged, and did bandwidth bottleneck? |
| **Post-repair** | Compaction backlog, free disk, CQL p99 | Did APIs recover and did repair cover the intended scope? |

Actual phase overlap varies by version and repair implementation; do not assume every repair streams huge volumes. Even when replicas match closely, Merkle validation still consumes heavy read I/O despite minimal streamed bytes.

### 15.3. Useful Experiments

1. **CQL baseline** without any new repair running.
2. Launch a scoped repair session while holding the workload constant.
3. Mark **start / validation / stream / end** timestamps alongside metric timelines.
4. If supported by runbooks, test **parallelism/throughput caps** in a separate run.
5. Compare **repair completion time** against p99, errors, in-flight, and disk stats across runs.
6. Verify sample partition data at proper CL after repair finishes.
7. Watch the **post-repair window** until compaction and backlogs return to acceptable bounds.

**Never manufacture inconsistency by editing SSTables directly, altering system tables, or crashing production nodes.** Fault tests involving replica divergence must use supported lab tooling with a clean restore plan.

### 15.4. When Repair Exposes Failures

If **ReadTimeout, WriteTimeout, Unavailable, or Overloaded** errors surge:

- Verify RF, CL, and node health before simply raising client timeouts.
- Check disk queue/latency and compaction, not only CPU.
- Check whether repair concurrency or streaming breached resource budgets.
- Keep workload context clear and shed/throttle background work per runbook—or **PAUSE/STOP** per approved gates.
- Avoid infinite CQL retries in Java; timed-out writes have unknown outcomes requiring idempotency keys and reconciliation.

### 15.5. Repair Does Not Replace Backups

A clean repair does not let you recover from an accidental `DROP`, application bug, or full-DC loss. You need independent backups, manifests, security controls, and restore drills. Conversely, solid backups never relieve the cluster of periodic anti-entropy repair.

## 16. Case P1/P2 — Measuring Snapshots and Off-Cluster Backups

### 16.1. Split Into Distinct Phases

~~~mermaid
flowchart TD
    A["Backup preflight: free disk, source health"] --> B["P1: create snapshot per runbook"]
    B --> C["Record manifest/SSTable links and pinned size"]
    C --> D["P2: copy/upload data to independent fault domain"]
    D --> E["Checksum/encryption/manifest verification"]
    E --> F["Restore drill on isolated cluster"]
    F --> G["Reconcile CQL/schema and measure RPO/RTO"]
    G --> H["Clear local snapshot once approved"]
~~~

**Measure the entire pipeline.** Taking a local snapshot in two seconds does not mean backup finished: network upload, checksumming, and restore account for most of the time and resource cost.

### 16.2. Local Snapshots

Cassandra snapshots preserve SSTables using hard links inside data directories per SSTable snapshot design. Monitor:

- **Snapshot creation time**, associated flushes, and I/O impact by version/method.
- **Snapshot count, tags, paths, SSTable filenames, and byte sizes**.
- **Free disk / pinned bytes** while snapshots stay on disk; compaction cannot reclaim old SSTables still referenced by snapshots.
- **Flush/compaction latency** and read/write impact during snapshot creation/retention.
- **Consistency of the backup set** across nodes, token ranges, and schema/metadata.

Never take repeated snapshots as a “stress benchmark” when disk headroom is tight. Local snapshots remain vulnerable to physical node or volume failures.

### 16.3. External Backup Copy

During upload to independent storage, track:

| Measurement source | Metric | Purpose |
|---|---|---|
| Source node | Disk read bytes/s, await/queue | Does backup read I/O hurt Cassandra reads? |
| Host / backup sidecar | Compression/encryption/checksum CPU, heap/queues | Is the backup agent the bottleneck? |
| Network | Upload bytes/s, retransmits, egress link | Is the link saturated or incurring cross-DC egress? |
| Object store / target | Completed bytes, failed chunks, retry counts | Are transfers completing steadily? |
| Cassandra | p95/p99, successful RPS, read/write errors | Are APIs breaking SLOs during backup? |
| Storage | Snapshot pinned/retained size and free disk | Do retained recovery points threaten disk full? |

Copy jobs read large SSTables sequentially while Cassandra may also be compacting or streaming. If multiple nodes upload simultaneously, aggregate network/storage pressure can far exceed single-node readings.

### 16.4. Integrity and Restorability

A backup passes only with proof of:

1. **Accurate scope:** keyspaces/tables, token coverage, schema, and version.
2. **Manifest/checksums:** all required files present, sizes/hashes match, no partial status.
3. **Security:** TLS, encryption at rest, KMS/IAM controls, and retention enforcement.
4. **Separate failure domain:** not just a snapshot sitting on the source disk/node.
5. **Restore drill:** actual restore onto an isolated cluster compatible with Cassandra/Java Driver, never disrupting source clusters.
6. **Data verification:** fixture/partition queries, row counts, sample keys, and invariants checked.
7. **RPO/RTO:** actual measured data-loss window and restore duration, not guesswork.

If requirements demand **point-in-time recovery**, snapshots generally must pair with incremental backups or commitlog archiving per your version and design. Never assume snapshots alone recover every write up to an arbitrary instant T.

### 16.5. Example Backup Evaluation Table

| Stage | Duration | API impact | Evidence |
|---|---|---|---|
| Local snapshot | Measured | p99/errors at creation | Snapshot tag/manifest |
| Off-cluster copy | Measured | p99/errors during upload | Checksums, remote objects |
| Integrity verification | Measured | Verifier CPU/disk | Matching hashes/coverage |
| Restore drill | Measured | Runs on isolated cluster | Data accuracy, RPO/RTO |
| Local cleanup | Measured | Free disk reclaimed | Confirmed safe recovery point |

Never purge local snapshots until retention policy and **verified external backup completion** permit it. Conversely, never leave old snapshots forever until disks fill; manage lifecycles with clear ownership.

## 17. When Repair, Streaming, and Backup Overlap

In production, maintenance tasks frequently compete for identical physical resources:

~~~text
Repair validation       → SSTable reads + CPU
Streaming sender        → SSTable reads + outbound network
Streaming receiver      → Inbound network + SSTable writes
Backup copy             → SSTable reads + outbound network
Compaction              → SSTable reads + SSTable writes + CPU
CQL application reads   → Memtable/SSTable reads + network
CQL application writes  → Commitlog/memtable + flush/compaction
~~~

Running these concurrently can push disks or networks past saturation even when every task stays mild in isolation.

### 17.1. Measure Overlap Cost Only After Single-Task Baselines

| Test | Tasks | Goal | Precondition |
|---|---|---|---|
| **R1** | Repair alone | Measure repair overhead | Valid baseline |
| **P2** | Backup copy alone | Measure backup network/disk overhead | Adequate backup storage |
| **X1** | Repair + backup copy | Measure combined contention | R1/P2 understood and stop gates active |
| **X2** | Bootstrap + backup | Model worst-case maintenance window | Only when truly needed and approved |
| **C1** | No new tasks after X1/X2 | Measure recovery and backlog drain | Cluster still holds headroom |

Do not run X1/X2 if R1 or P2 alone already pushes p99/errors past SLOs. Overlap tests should model **realistic operational risk**, not destroy test clusters needlessly.

### 17.2. Never Add Two p99 Increases Linearly

If repair alone adds 80 ms to p99 and backup alone adds 50 ms, concurrent execution will **not** equal **baseline + 80 + 50**. Tail latency suffers non-linear effects from queuing, cache eviction, disk contention, GC pauses, token skew, and retry storms. Measure overlaps **directly** and compare both successful throughput and error rates, not just p99.

### 17.3. Scheduling and Throttling Background Tasks

Operations teams can choose to:

- Prohibit heavy repair and backup uploads from overlapping during peak hours.
- Throttle backup uploads or streaming rates to preserve bandwidth and disk headroom.
- Cap concurrent repair jobs/nodes using supported tooling controls.
- Maintain a calendar avoiding collisions with upgrades, restore drills, and heavy ETL/backfills.
- Add headroom or capacity **before** rolling out aggressive maintenance schedules.

Make scheduling decisions around **SLOs and recoverability**, not raw job completion speed. Finishing maintenance fastest while breaking user APIs is rarely the right trade-off.

## 18. Stop Gates: When to Proceed, Throttle, or Abort

Define **GO / THROTTLE / PAUSE / STOP / ESCALATE** criteria before starting tests. The thresholds below are strictly **illustrative**, not universal Cassandra rules:

| Criterion (example) | GO | Consider throttling | STOP / ESCALATE |
|---|---|---|---|
| **API p99** | Within approved SLO | Sustained rise before breach | Repeated SLO breaches across windows |
| **Error rate** | Within error budget | Unusual case-specific rise | `Unavailable`/`Overloaded` or error budget threatened |
| **Free disk** | Headroom covers stream/compaction/snapshot | Projected shortfall before job ends | Safety floor hit or rising disk-full risk |
| **Disk latency/queue** | Representative healthy range | Climbing while p99 worsens | Sustained saturation and growing pending tasks |
| **Streaming/repair progress** | Advancing with zero failed tasks | Slowing, retries increasing | Stalled, failed ranges, or data errors |
| **Node health** | Replicas satisfy CL, healthy schema | One node unusually slow | Quorum or service availability at risk |
| **Data correctness** | Fixtures and invariants pass | Verification inconclusive | Missing/corrupt data detected |
| **Backup integrity** | Complete manifests and checksums | Slow or partial uploads | Integrity failure; no valid recovery point |

### 18.1. Example Quantitative Service Thresholds

Suppose a service **agrees before testing**:

~~~yaml
slo_example:
  read_p99_ms_max: 250
  logical_error_rate_max_percent: 1.0
  successful_rps_min: 900
maintenance_gates_example:
  warning_after_consecutive_windows: 2
  stop_after_consecutive_windows: 3
  window_minutes: 2
  disk_free_min_percent: 20
  no_failed_repair_ranges: true
  no_unverified_backup_chunks: true
  no_data_correctness_failures: true
~~~

Values like **250 ms, 900 RPS, 20% free disk** illustrate **one test agreement**, not defaults or universal guidance. Disk headroom must account for **absolute free bytes**, projected SSTable/backup growth, and compaction space amplification; a single percentage threshold rarely suffices on huge volumes.

### 18.2. Proper Response When a Stop Gate Fires

**First control the test load source.** Stop dispatching new synthetic requests, preserve evidence, throttle background tasks through supported interfaces, or enter incident mode. Crucially:

- **Never kill Cassandra JVMs, abort streaming/repair, or manually wipe snapshots** just because p99 climbed, unless approved by runbooks and owners.
- Interrupted streaming or repair jobs leave partial state requiring proper resume/cleanup handling. Stopping the load generator does not automatically stop Cassandra background jobs.
- Whenever replica/quorum safety or data integrity is threatened, **prioritize protecting data** over finishing the benchmark.
- If a backup upload fails, never delete existing verified recovery points until a replacement succeeds verification.
- Record who decided, when, cluster state, active jobs, next actions, and resume conditions.

### 18.3. Assigning GO/NO-GO Accountability

| Role | Decisions / evidence owned |
|---|---|
| **Service owner / Java team** | SLOs, business correctness, query mix, client metrics |
| **DBA / Cassandra owner** | RF/DC, topology, repair/streaming behavior, schema, storage risks |
| **SRE / platform** | Capacity, disk/network health, alerting, maintenance orchestration |
| **Backup / DR owner** | Backup integrity, off-cluster copies, RPO/RTO, restore sign-off |
| **Change approver / incident commander** | GO/PAUSE/STOP authority and production scheduling |

A green dashboard with nobody accountable for verifying data correctness or restorability does not pass acceptance.

## 19. Reading Metrics and Sizing Capacity: A Worked Example

Suppose we hold **1,000 offered logical requests/second** constant across three phases. All figures are **hypothetical**:

| Metric | Baseline C0 | During bootstrap B1 | Post-recovery C1 |
|---|---:|---:|---:|
| Offered logical RPS | 1,000 | 1,000 | 1,000 |
| Successful completed RPS | 995 | 940 | 995 |
| Failed completed RPS | 5 | 60 | 5 |
| p99 successful read latency | 140 ms | 390 ms | 155 ms |
| Average client in-flight | 170 | 490 | 190 |
| Sender disk read | 110 MiB/s | 310 MiB/s | 120 MiB/s |
| Sender outbound network | 70 MiB/s | 160 MiB/s | 75 MiB/s |
| Pending compaction tasks | 3 | 25 | 4 |

**Assessment:**

1. Offered load stayed fixed, yet **successful throughput dropped by 55 RPS**.
2. Error rate over completed requests jumped from roughly **0.5% to 6%**.
3. Read p99 rose from **140 ms to 390 ms**, breaching the illustrative 250 ms SLO in Section 18.
4. Client in-flight and pending compactions spiked cleanly in line with resource contention.
5. After recovery, p99 dropped back to 155 ms; still verify error rates, disk backlog, and data parity before closing.
6. **Never treat correlation as automatic proof of cause:** inspect timelines, server logs, warm-up artifacts, retries, pre-existing compactions, and generator health.

Reasonable verdict: **Case B1 under this configuration fails the illustrative SLO**, even if bootstrap finishes cleanly. Re-test on staging with tighter streaming throttles, an off-peak maintenance window, added capacity, or revised conditions.

### 19.1. Estimating Headroom Beyond CPU Percentage

Suppose a source disk already serves **350 MiB/s** at baseline on storage rated near **500 MiB/s** realistic mixed throughput. Streaming or backup requires another **250 MiB/s** read from the same volume:

~~~text
Estimated total demand = 350 + 250 = 600 MiB/s
Observed effective capacity ≈ 500 MiB/s

Demand exceeds observed capacity by ~100 MiB/s,
before counting seeks/IOPS, write latency, compaction, and queuing.
~~~

This is a **rough back-of-the-envelope estimate**, not a precise disk scheduling model. Sequential 500 MiB/s bandwidth never guarantees good mixed random read/write latency at that rate. Measure actual device latency and I/O p99 on real hardware.

### 19.2. Capacity Planning for Snapshots and SSTable Retention

Suppose a data directory holds **700 GiB** with **300 GiB free**, and retention policy keeps snapshots for several days. Never assume “snapshots are hard links so they cost 0 bytes.” As compaction writes new SSTables, old SSTables stay pinned by snapshots, driving **actual disk usage** upward. You must:

- Forecast ingest volume, compaction churn, and retention duration.
- Track **real filesystem space used** and snapshot-pinned/retained bytes, not just apparent file sizes listed naively.
- Trigger alerts well ahead of disk-full and enforce copy/verify/cleanup timelines.
- Check whether concurrent bootstrap/repair streaming leaves enough headroom.

Never sum apparent snapshot directory listings blindly when hard links share inodes; understand how your filesystem monitoring accounts for shared blocks so you neither double-count nor underestimate pinned retention.

### 19.3. Throughput Without Matching Consistency Contracts Is Meaningless

If Test A uses `LOCAL_ONE` while Test B uses `LOCAL_QUORUM`, higher throughput in A proves nothing for applications bound to stronger consistency guarantees. Always record RF/DC, CL, and retry policy per phase and compare cases under **identical acceptance contracts**.

## 20. Benchmark Result Report Template

Teams can store benchmark records using a structured template in their reporting/changelog system:

~~~yaml
experiment:
  id: "load-lab-bootstrap-2026-11-example"
  operation: "bootstrap"
  environment: "staging-isolated"
  owner: "cassandra-platform"
  approved_change: "<change-reference>"
  started_at_utc: "<timestamp>"
  finished_at_utc: "<timestamp>"
versions:
  cassandra: "<exact-version>"
  java_driver: "<exact-version>"
  jdk: "<exact-version>"
topology:
  dc: "dc1"
  nodes_before: 3
  nodes_after: 4
  keyspace: "load_lab"
  replication_factor_in_dc1: 3
client_workload:
  offered_rps: 1000
  query_mix: "representative-read-write"
  partition_distribution: "normal-plus-known-hot-set"
  read_consistency: "LOCAL_QUORUM"
  write_consistency: "LOCAL_QUORUM"
  max_in_flight: 100
  request_timeout_ms: "<configured-and-verified>"
  retry_policy: "<policy-name-and-budget>"
baseline:
  success_rps: 995
  p99_read_ms: 140
  error_percent: 0.5
during_operation:
  success_rps_min: 940
  p99_read_ms_max: 390
  error_percent_max: 6.0
  streaming_bytes: "<observed>"
  peak_disk_read_mib_s: 310
  peak_network_out_mib_s: 160
  failed_stream_sessions: "<observed>"
after_operation:
  p99_read_ms: 155
  error_percent: 0.5
  recovery_minutes: "<measured>"
correctness:
  fixture_queries_passed: true
  missing_events: 0
  duplicate_logical_events: 0
  schema_and_topology_verified: true
decision:
  verdict: "NO-GO for this load/SLO profile"
  action: "test throttling or different maintenance window"
evidence:
  metrics_dashboard: "<link>"
  nodetool_logs: "<location>"
  generator_report: "<location>"
  change_log: "<location>"
~~~

This is an **illustrative report schema**, not a runnable Cassandra config. Record **`NOT_MEASURED`** for any unmeasured field instead of guessing values. Never log real tenant identifiers, raw payloads, access tokens, object-store secrets, or sensitive customer data into benchmark artifacts.

### 20.1. Questions the Conclusion Must Answer

Every report should answer using observed data:

- **Did the task cover its intended scope?** Did bootstrap token ranges, repair ranges, or backup manifests complete cleanly?
- **Did the API breach SLOs while running?** For how many minutes and with which error classes?
- **How long did recovery take after the task reported completion?**
- **What evidence identifies the main bottleneck?** Disk, network, GC, coordinator, replica skew, or driver?
- **How reliable is the conclusion?** Were any tasks overlapping, how many runs occurred, and what background noise was ruled out?
- **How far were data correctness and restorability verified?**
- **Operational recommendations:** schedule windows, concurrency/throughput caps, capacity upgrades, stop gates, owners, and follow-up tests.

## 21. Fault Scenarios and Post-Task Recovery

Measuring under healthy cluster conditions is only step one. **Load and Distributed Fault Testing** also covers what happens when background operations fail mid-flight. Trigger these faults **strictly in approved lab clusters** with tested recovery paths.

### 21.1. Streaming Source Node Becomes Unavailable

**Scenario:** during a lab bootstrap, a source node streaming SSTables abruptly stops responding.

What to observe:

- Does bootstrap/streaming report **failed/retried sessions** or continue progressing?
- Do replica placement and CL remain sufficient for application traffic?
- Does the Java Driver see **`Unavailable`/`ReadTimeout`/`WriteTimeout`** and retry amplification?
- Is the joining node stuck in a transitional state?
- Are follow-up data correctness, repair, or cleanup steps required by the runbook?

**Never conclude** “streaming failed means data is lost” or “node Up means everything is safe.” Inspect exact topology state, token coverage, server logs, and prepared CQL verification; let the owner follow version-appropriate resume, replacement, or rollback procedures.

### 21.2. Repair Validation Completes, Then Difference Streaming Fails

**Scenario:** repair finishes validation cleanly, then a network error breaks an SSTable sync stream.

Accurate reporting format:

~~~text
repair_status: PARTIAL / FAILED
validation_completed: <observed coverage>
streaming_failed: <failed ranges/sessions>
data_correctness: NOT_YET_VERIFIED
repair_complete: false
next_action: inspect logs; resume/fix-forward via approved runbook
~~~

**Never mark `COMPLETE`** merely because validation ran or a wrapper tool returned partial success. When failures happen, record exact completed vs unsynchronized ranges and execute version-specific recovery steps.

### 21.3. Backup Storage Rejects Uploads While Snapshots Pin SSTables

**Scenario:** backup upload to object storage starts, then hits access denied, quota limits, or network timeouts. Local snapshots stay pinned and free disk keeps falling.

Required steps:

1. **Classify remote storage failures** properly (auth/quota/network/checksum) rather than lumping them with Cassandra write timeouts.
2. **Preserve previously verified recovery points.**
3. Inspect uploaded manifest/chunks and the backup tool's resume mechanics.
4. Track snapshot pinned bytes and free disk; if space runs critically low, escalate per retention/backup ownership rules.
5. Clear local snapshots only after a new backup verifies cleanly or an approved DR decision authorizes it.
6. Run a restore drill on an isolated cluster to verify RPO/RTO.

A **partially uploaded** backup is never usable merely because some SSTables exist in remote storage.

### 21.4. Client Timeouts During Backup and Repair

The Java service sees **`WriteTimeout`** while disks saturate. Some replicas may have applied the mutation. If an API gateway retries with a new request ID, business records can duplicate.

Mitigations:

- Persist stable **logical request IDs** and enforce idempotency.
- Shed load or throttle maintenance per runbook; never blindly slam retries when `Overloaded`.
- Never silently downgrade `LOCAL_QUORUM` to `LOCAL_ONE`, changing consistency guarantees.
- Reconcile CQL state by partition key whenever outcomes are ambiguous.
- If invariants were broken, handle it as a data incident; finishing repair or backups does not automatically repair business-logic bugs.

### 21.5. Overdriving Load Invalidates the Benchmark

Once saturated, pushing arrival rate higher to “find the absolute ceiling” causes successful RPS to collapse, errors to spike, and queues/disk I/O to linger long after the generator stops. That leaves fixtures, caches, and SSTables altered beyond valid comparison with the prior baseline.

Respect **stop gates** and let the cluster recover fully; before running again, establish a fresh baseline C0 rather than chaining runs immediately out of an overloaded state.

## 22. Practice Exercises with Suggested Answers

### Exercise 1 — Node Up Yet API Slow

After bootstrap, **`nodetool status`** shows the new node `UP/NORMAL`. Yet read p99 remains 2.5x baseline, pending compactions are elevated, and disk await is high.

**Question:** Can we mark the bootstrap test PASS against SLOs?

**Suggested answer:** No, because the p99 SLO is breached. Node `UP` reflects only membership status. Continue observing the recovery window, compaction/disk metrics, and application latency; apply agreed GO/NO-GO gates.

### Exercise 2 — Streaming Speed and Ideal Time

We need to transfer **120 GiB**. Sustained average rate without errors is **60 MiB/s**. Estimate ideal copy time.

**Answer:** `120 × 1,024 / 60 =` **2,048 seconds**, roughly **34.1 minutes**. This excludes validation, retries, compaction, headroom margins, and non-transfer phases.

### Exercise 3 — Comparing Benchmarks with Different Consistency Levels

Case A reads at **`LOCAL_ONE`**; Case B reads at **`LOCAL_QUORUM`**. Case A finishes 30% faster.

**Question:** Can we conclude Case A's bootstrap had less operational impact?

**Suggested answer:** No direct comparison is valid. CL is a changed variable altering required replica responses and latency. Re-run under identical contract CL and compare each against its own baseline.

### Exercise 4 — Fast Snapshot, Shrinking Free Disk

A snapshot took just seconds, yet a day later free disk drops sharply without major traffic growth. Dashboards show heavy ongoing compaction.

**Question:** What likely happened?

**Suggested answer:** Snapshots hold hard links to SSTables; compaction creates new SSTables while old ones stay pinned by the snapshot, increasing total disk consumed. Inspect `listsnapshots`, filesystem accounting, external backup verification, and approved retention cleanup—never delete unverified recovery points hastily.

### Exercise 5 — Concurrent Repair and Backup

R1 alone yields p99 = 180 ms; P2 alone yields p99 = 170 ms; baseline p99 = 130 ms.

**Question:** Can we compute concurrent X1 p99 as `180 + 170 − 130 = 220 ms`?

**Suggested answer:** No. Queuing, disk/network contention, retries, and GC combine non-linearly. Measure X1 directly on staging after isolated R1/P2 show sufficient headroom and stop gates are configured.

### Exercise 6 — Did the Client Achieve 1,000 RPS?

The load generator reports scheduling 1,000 requests/s, with 780 requests/s succeeding, 80 failing, and 140 rejected at admission.

**Question:** What is the successful throughput?

**Answer:** **780 successful logical requests/s** (per reported figures), not 1,000. Report failed and rejected counts alongside successes and diagnose why offered rate exceeded served capacity.

### Exercise 7 — Is Backup Upload Success Enough?

A job reports success after copying 5 TB of backups to remote storage. Operations saved no schema/manifest/checksum and has never run a restore.

**Question:** Can we certify a 1-hour RTO?

**Suggested answer:** No. Upload completion alone does not prove recovery within 1 hour. Verify manifests, checksums, encryption keys, documented runbooks, and execute an isolated restore drill to measure RPO/RTO.

### Exercise 8 — Should We Run Cluster-Wide Repair as a Stress Benchmark?

A 10 TB staging cluster already has p99 near its SLO limit. Someone suggests launching a **cluster-wide full repair** immediately to see if it survives.

**Suggested answer:** Do not start without headroom and risk assessment. Scope repair more narrowly per supported tooling with an assigned owner, stop gates, telemetry, and recovery plan rather than running cluster-wide full repair blindly.

### Exercise 9 — `ReadTimeout` Persists After Repair

Repair completes and replicas match, yet the application still hits `ReadTimeout` on one very hot tenant.

**Question:** Does repair fix hot partitions?

**Suggested answer:** No. A hot partition funnels excessive traffic onto the specific replicas owning its token even when their data matches perfectly. Analyze partition key/bucketing/sharding, row sizes, SSTables/tombstones, read latency, and node capacity.

### Exercise 10 — Streaming Network Underutilized Yet Slow

A 10 Gbps NIC shows light utilization while streaming crawls. Sender disk `await` and queue depth are high.

**Question:** Should we raise the network bandwidth cap to speed it up?

**Suggested answer:** Not first. Disk I/O is likely the bottleneck; raising network caps will not make disks read faster. Inspect per-disk IOPS/latency, compaction activity, SSTable reads, and live workload contention.

### Exercise 11 — Benchmark Report Missing Timestamps

A report states only “daily average read p99 was 240 ms,” with no markers for when bootstrap started or ended.

**Question:** Why is this insufficient?

**Suggested answer:** It blurs baseline, peak impact, post-task recovery, and unrelated background jobs together. Time-stamped event markers, windowed telemetry, traffic rate, and CL are required.

### Exercise 12 — Open-Loop vs Closed-Loop

Test A uses 100 workers each waiting for completion before sending the next request; when Cassandra slows, RPS drops automatically. Test B fires a steady 1,000 RPS.

**Question:** Why do these tests expose load differently?

**Suggested answer:** Test A is closed-loop, throttling offered rate automatically as latency climbs and hiding saturation; Test B is open-loop, sustaining arrival pressure and exposing queuing, rejections, and errors. Always specify the model and match it to test goals.

### Exercise 13 — `WriteTimeout` During Backup Copy

Java writes events while backup reads SSTables and hits `WriteTimeout`. The service mints a fresh `event_id` on retry.

**Question:** What bug can this introduce?

**Suggested answer:** If the first write already landed on some replicas, retrying with a new ID produces two duplicate logical events. Keep identity stable, enforce idempotency and reconciliation, and reduce load rather than feeding a retry storm.

### Exercise 14 — Partial Repair Marked Complete

A repair job verifies 95% of ranges while 5% fail on network errors. The wrapper logs “completed with errors,” yet an internal report marks it PASS.

**Question:** Is that valid?

**Suggested answer:** No. Mark it **PARTIAL/FAILED**, list the failed ranges, and run remediation per runbook/version; 95% coverage is never 100% completion when policy requires full coverage.

### Exercise 15 — Adding Up Disk Load

A disk reads **350 MiB/s** at baseline; streaming needs **250 MiB/s**, against effective storage throughput around **500 MiB/s** for similar workloads.

**Question:** What is the risk?

**Answer:** Rough combined demand of **600 MiB/s** exceeds observed capacity by roughly **100 MiB/s**, threatening rising disk queues, higher latency, and p99 breaches. Measure mixed random I/O under real load and throttle tasks or add headroom.

### Exercise 16 — Running Bootstrap While Holding Snapshots

A node has only 15% free disk left, holds old snapshots pinning SSTables, and is about to receive bootstrap streaming.

**Question:** Should we proceed (GO)?

**Suggested answer:** Not yet. Forecast incoming streamed bytes, compaction headroom, and snapshot retention; confirm verified off-node backups exist, then clean up per runbook or expand disk first. Never wipe snapshots recklessly.

## 23. Pre-, During-, and Post-Test Checklist

### 23.1. Before Starting

- [ ] Execute only in an approved environment/window with clear ownership.
- [ ] Record exact Cassandra, JDK, Java Driver, and operator versions plus version-specific limits.
- [ ] Document DC/racks, node count, RF, CL, schema agreement, token layout, and node states.
- [ ] Preload representative synthetic fixtures with locked query shapes, payload sizes, and key skew.
- [ ] Define **open-loop vs closed-loop**, offered rate, max in-flight, deadlines, and retry budget.
- [ ] Confirm the load generator will not saturate CPU/disk/network before Cassandra.
- [ ] Record baseline p50/p95/p99, successful throughput, error rate, GC/disk/network, and compaction stats.
- [ ] Confirm adequate disk headroom for incoming streaming, compaction, retained snapshots, and backup reads.
- [ ] Verify existing recovery points and restore/rollback plans for tasks carrying data risk.
- [ ] Define stop gates, alerts, and runbook triggers for THROTTLE/PAUSE/STOP.

### 23.2. During Execution

- [ ] Record start/end/phase timestamps for bootstrap, streaming, repair, snapshots, and copy/upload.
- [ ] Hold CL, query mix, and rate steady for valid comparison.
- [ ] Monitor **p99 alongside successful RPS and error rates**, never one metric alone.
- [ ] Watch disk latency/queues/free space, network, CPU/GC/native RSS, and pending tasks.
- [ ] Capture version-accurate `nodetool status/netstats/tpstats/compactionstats/tablestats`.
- [ ] Log repair coverage, failed sessions, and streamed bytes/files separately.
- [ ] Separate snapshot creation duration from off-node upload, checksumming, and restore time.
- [ ] Never hike retries or weaken consistency mid-run to turn a benchmark “green.”
- [ ] When stop gates trip, halt the load source and follow runbooks; **never kill nodes or purge snapshots ad hoc**.
- [ ] Tag runs with correlation/run IDs without logging secrets, sensitive partition keys, or user payloads.

### 23.3. After Completion

- [ ] Verify node health, topology/token ownership, schema agreement, and replica/CL readiness.
- [ ] Reconcile fixture data via prepared CQL, checking for missing or duplicate logical events.
- [ ] For repair, confirm all target ranges and failed sessions are resolved.
- [ ] For backup, verify remote manifests/checksums/keys and run an isolated restore drill.
- [ ] Observe the recovery window until p99/error/throughput and compaction backlogs stabilize.
- [ ] Record peak/average resource usage, elapsed runtime, recovery time, and error budget spent.
- [ ] Never clear local snapshots without approval; enforce lifecycle retention and capacity tracking.
- [ ] Compare C0/B1/S1/R1/P1/P2/X1 under identical contracts; never sum p99 deltas arithmetically.
- [ ] Record GO/NO-GO verdict, evidence-backed bottlenecks, required follow-up tests, and action owners.
- [ ] Store artifacts with access controls so reports do not vanish when jobs finish.

## 24. Conclusion

**Load testing during bootstrap, streaming, repair, or backup** means more than watching MiB/s transferred or read off disk. In Cassandra, background maintenance shares **disks, network links, CPU/GC, SSTables, compaction, and replica capacity** with live client queries serving consistency contracts. An operational command can report success while the Java API still suffers high p99 latency, timeouts, error-budget burn, or lingering compaction backlog.

A reliable test workflow runs **preflight → baseline representative workload → single controlled operation → timeline-aligned metrics → data verification → recovery window → GO/NO-GO**. Test overlapping repair, backup, and streaming only after characterizing each task alone and arming clear stop gates. Combine **`nodetool`** with OS/JVM telemetry, yet always judge against **successful throughput, end-to-end p99, and data correctness** from the Java application.

Finally, **replication does not replace backup, repair cannot undo business-logic mistakes, local snapshots do not cross failure domains, and completed maintenance jobs do not prove RPO/RTO**. A solid benchmark tells you **how much correct work the system sustains, under which load and faults, for how long, and with what impact and recovery risk**.

