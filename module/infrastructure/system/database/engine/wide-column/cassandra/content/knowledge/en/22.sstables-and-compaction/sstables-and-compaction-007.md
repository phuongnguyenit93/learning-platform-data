# Changing Compaction Strategy and Resulting Transition Load

## Goals and Context

In Apache Cassandra, every write is typically appended to the **commit log** and **memtable**; upon flush, the memtable creates a new **SSTable** file. SSTables are immutable storage structures: updating or deleting a row does not modify bytes in old SSTables in place. Therefore, over time, a partition can have multiple versions of data spread across multiple SSTables. **Compaction** reads input SSTables, merges their contents, and writes output SSTables according to the policy of a **compaction strategy**.

Changing strategies is an operational decision with real impact: SSTable count, read/write amplification, temporary disk space, background I/O, CPU, application latency, and tombstone cleanup capability can all shift. The `ALTER TABLE` statement itself is usually fast; **the work of reorganizing data on disk is what can consume substantial resources**.

This lesson belongs to the **SSTables and compaction** chapter in the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. We will connect it to distributed architecture, partition keys, query-driven table design, replication, consistency levels, CQL, repair, and Java applications. The goals are to:

- Explain how a compaction strategy decides **which SSTables are merged and when**, and how it differs from replication or repair.
- Choose among **STCS**, **LCS**, **TWCS**, and, where supported by the version, **UCS** based on write/read/TTL patterns.
- Write CQL to inspect and change the strategy at the **table** level without confusing schema configuration with completed data conversion.
- Anticipate I/O, CPU, disk space, tombstone, and latency loads during the transition period.
- Plan rollout, monitoring, throttling/load shedding, and conditional rollback, alongside before/after measurement exercises.

## 1. How Does Compaction Work?

Imagine a row updated three times and then deleted:

~~~text
Write 1   -> Memtable -> SSTable A: value = "draft"
Write 2   -> Memtable -> SSTable B: value = "review"
Write 3   -> Memtable -> SSTable C: value = "published"
Delete    -> Memtable -> SSTable D: tombstone

On read, Cassandra must reconcile relevant versions/tombstones.
When compaction is eligible, inputs are merged into
a new SSTable and old SSTables are dropped once output completes.
~~~

~~~mermaid
flowchart LR
    W["INSERT/UPDATE/DELETE"] --> M["Commit log + memtable"]
    M --> F["Flush"]
    F --> A["SSTable A"]
    F --> B["SSTable B"]
    F --> C["SSTable C"]
    A --> X["Compaction"]
    B --> X
    C --> X
    X --> N["Output SSTable"]
    N --> Q["Future read path"]
~~~

During compaction, **input and output SSTables may occupy disk space simultaneously**. Cassandra must ensure outputs are created and completed safely before discarding old data. Consequently, a table with enough free space for normal writes can still **run out of disk during compaction**. Changing strategies can also alter how SSTable groups are chosen, triggering multiple rewrites over the same data.

Compaction happens **locally on a node** and that node's replica data. It is not an operation that broadcasts data to every replica:

| Mechanism | Primary job |
| --- | --- |
| **Compaction** | Merges/rewrites SSTables on one node, managing file counts, tombstones, and read/write costs per strategy. |
| **Replication** | Distributes copies per replication factor, tokens, and datacenters. |
| **Repair** | Compares/synchronizes data between replicas; can generate write/streaming load and affect compaction. |
| **Flush** | Writes memtable contents into a new SSTable; does not replace merging existing SSTables. |
| **Backup/snapshot** | Preserves components for recovery; snapshots link to SSTables and can retain files, affecting space reclamation. |

Changing the compaction strategy **does not change partition keys, replication factor, CQL data, or client consistency levels**. Yet it impacts read/write performance of the very queries using those components.

## 2. Comparing Common Strategies

| Strategy | SSTable selection rule | Good when | Trade-offs to watch |
| --- | --- | --- | --- |
| **SizeTieredCompactionStrategy (STCS)** | Groups similarly sized SSTables into tiers | Write-heavy, few random reads, data lacking a clear time-based TTL model | Can accumulate many overlapping SSTables, raising read amplification and needing temp space for large merges |
| **LeveledCompactionStrategy (LCS)** | Organizes SSTables into levels, bounding overlap at higher levels | Frequent random/point reads needing bounded SSTables per lookup | Can rewrite much more data, increasing write amplification, I/O, and CPU |
| **TimeWindowCompactionStrategy (TWCS)** | Groups SSTables by time windows tied to **write/SSTable timestamps** | Mostly append-only time-series, fairly uniform TTLs, few updates to old data | Late arrivals/overwrites/old deletes can create overlap and delay expiration cleanup |
| **UnifiedCompactionStrategy (UCS)** | Unified mechanism with parameters tuning read/write/space amplification trade-offs | Diverse workloads on Cassandra versions **supporting UCS** | Must understand version, parameters, and real metrics before adopting, especially when migrating from legacy strategies |

**Version check:** STCS, LCS, and TWCS exist across many Cassandra versions; **UCS was introduced in Apache Cassandra 5.0**. Do not copy UCS configurations into Cassandra 4.x or unsupported distributions. Defaults, options, and specific recommendations can change across versions.

### Choose Strategy from Query Traits, Not Names

1. **Continuous writes with rare per-key reads:** STCS can lower rewrite cost compared to LCS; watch accumulated SSTable counts and read latency.
2. **Frequent point reads or narrow range reads:** LCS can reduce overlapping SSTables, in exchange for higher background resource use on writes.
3. **Daily events, 7–30 day TTL, rare retro-updates:** TWCS is worth considering if write timing, window, and retention align.
4. **Mixed loads, Cassandra 5.0+:** evaluate UCS and measure on real workloads; do not assume it beats every strategy in all cases.

**Watch out with TWCS:** compaction windows rely on timestamps attached to SSTables/mutations, **not** an arbitrary `event_time` column declared by the application. A row having `day = '2026-11-01'` does not put it into that day's window if the application inserts it on Nov 21 using current write time. Backfills, historical updates, scattered deletes, or client-supplied timestamps can cause SSTables to span windows and hinder TTL reclamation.

## 3. Amplification Forms and the Temporary Space Problem

### 3.1. Read Amplification

A query specifying the **partition key** and clustering range benefits from knowing data location, yet when the same partition exists across multiple SSTables, Cassandra may still need to check multiple places, including Bloom filters/indexes and tombstones. Switching to LCS sometimes cuts overlapping SSTables on the read path; switching to STCS can increase checked files depending on workload.

If queries omit the partition key and force broad scans, changing strategy **will not fix the table design**. Prioritize bounded queries first, then measure compaction impact.

### 3.2. Write Amplification

A mutation is first written to the memtable/SSTable, yet its bytes may be **rewritten multiple times** during compaction. LCS typically requires more rewrites to maintain levels; TWCS can rewrite less once a window closes and data stops changing. Write amplification affects disk bandwidth, drive endurance, CPU, and fresh-write headroom when background jobs contend for I/O.

### 3.3. Space Amplification and Strategy Transitions

Suppose a node holds **600 GiB** of Cassandra data, of which the table changing strategy occupies **240 GiB**. Disk usage can spike temporarily while creating new SSTables; the increase depends on selected SSTable groups, concurrency, snapshots, expired data, and target strategy. No fixed rule like “you need exactly an extra 240 GiB” guarantees safety.

A practical assessment approach:

- Look at **lowest free space on each individual node**, not just total cluster capacity.
- Measure the size of running/pending compactions and output generation rates on that exact node.
- Reserve headroom for **new writes**, commit logs, memtable flushes, streaming/repair, snapshots, and daily variance.
- If free space is insufficient to write outputs before deleting inputs, **throttle down or halt the transition plan**; never try running `nodetool compact` to “free space” when you lack space to write outputs.

Do not confuse **table size** with the number of bytes that must be rewritten during conversion: the same data may go through multiple compaction passes. Data already written under the old strategy **is not necessarily reorganized instantaneously** after `ALTER TABLE`.

## 4. Preparing the Table and Measuring Baseline

The following lab is for a Cassandra environment with a test keyspace; never switch strategies on production tables without a baseline and monitoring plan.

~~~sql
-- Replace datacenter1 with the actual datacenter name.
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
};

CREATE TABLE IF NOT EXISTS telemetry.events_by_device_day (
    tenant_id text,
    device_id uuid,
    day date,
    event_time timestamp,
    event_id timeuuid,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC)
  AND default_time_to_live = 604800
  AND compaction = {
      'class': 'SizeTieredCompactionStrategy'
  };
~~~

Here:

- `(tenant_id, device_id, day)` is the **partition key**; a given device/day is usually read within a narrow slice.
- `event_time` and `event_id` are clustering columns; they support querying a known time range.
- `default_time_to_live = 604800` sets a default **7-day** TTL for regular values; ensure storage requirements permit this TTL.
- The table starts with STCS to illustrate a transition path to TWCS.
- `IF NOT EXISTS` **does not modify an existing table's schema**. When re-running the lab, inspect existing schema before comparing.

Sample writes:

~~~sql
INSERT INTO telemetry.events_by_device_day
    (tenant_id, device_id, day, event_time, event_id, payload)
VALUES (
    'tenant-a', 11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21T09:30:00Z',
    now(), 'sensor=21.5'
);

SELECT event_time, event_id, payload, TTL(payload)
FROM telemetry.events_by_device_day
WHERE tenant_id = 'tenant-a'
  AND device_id = 11111111-1111-4111-8111-111111111111
  AND day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z';
~~~

**Small data like a single row will not suffice to observe compaction.** To test performance, generate an experimental load with multiple flushes/SSTables and production-like write/TTL cycles, while staying inside an authorized lab without exhausting disk capacity.

### Collecting Baseline

~~~bash
# Run on each node holding data for the table.
nodetool status
nodetool tablestats telemetry.events_by_device_day
nodetool compactionstats
nodetool getcompactionthroughput
~~~

Read strategy configuration from schema metadata via CQL:

~~~sql
SELECT keyspace_name, table_name, compaction, default_time_to_live
FROM system_schema.tables
WHERE keyspace_name = 'telemetry'
  AND table_name = 'events_by_device_day';
~~~

Record the baseline in a dedicated log: live SSTable count, table size, bytes read/written, p95/p99 latency, active/pending compactions, per-node free disk, read/write timeouts, and ingest rate. Some `nodetool` versions display different metric names or units; document your exact version when comparing.

## 5. Changing Compaction Strategy with CQL

### 5.1. Example STCS → TWCS for Time-Series Event Data

Proceed only if data is **mostly append-only**, TTLs are roughly uniform, historical updates/deletes are rare, and the compaction window fits the ingest cadence:

~~~sql
ALTER TABLE telemetry.events_by_device_day
WITH compaction = {
    'class': 'TimeWindowCompactionStrategy',
    'compaction_window_unit': 'DAYS',
    'compaction_window_size': '1'
};
~~~

This change is a **schema change** propagated across the cluster. It configures compaction selection and handling **from that moment onward**; it does not mean all old SSTables have been rewritten into one-day windows the instant CQL returns. SSTables created under the prior strategy can stretch out the transition and create background work; actual pace depends on file count, timestamp distribution, and current load.

If schema changes have not yet converged across nodes, do not infer every node uses the new strategy just because `ALTER TABLE` succeeded on the coordinator. Verify schema agreement via management tools/driver and node status.

### 5.2. Example STCS → LCS for Frequent Point Reads

A table serving many exact partition-key lookups with tight latency SLAs might consider:

~~~sql
ALTER TABLE telemetry.events_by_device_day
WITH compaction = {
    'class': 'LeveledCompactionStrategy'
};
~~~

Under this strategy, organizing data into levels can **rewrite substantial amounts of data**, especially when the table is large and writes continue. Measure write amplification, compaction backlog, and read latency; do not assume LCS beats TWCS merely because it reduces overlapping SSTables for one query type.

### 5.3. Example Using UCS When Supported by Server

On an Apache Cassandra **5.0+** cluster with UCS available:

~~~sql
ALTER TABLE telemetry.events_by_device_day
WITH compaction = {
    'class': 'UnifiedCompactionStrategy'
};
~~~

This example only illustrates choosing the **class**. Parameters such as `scaling_parameters` and other UCS options must follow version docs and benchmarks; never apply one blanket value across every workload. If the server does not support it yet, the statement may be rejected: that is a version compatibility issue, not data corruption.

**Configuration rule:** each `ALTER TABLE ... WITH compaction = {...}` sets the table's compaction options map. When switching strategies, declare all options you wish to set for the new strategy; do not assume option keys from the old strategy carry over with equivalent meaning.

### 5.4. Verifying After ALTER

~~~sql
SELECT table_name, compaction
FROM system_schema.tables
WHERE keyspace_name = 'telemetry'
  AND table_name = 'events_by_device_day';
~~~

Continue monitoring `nodetool compactionstats`, `nodetool tablestats`, and per-node metrics. **Seeing the new strategy name only confirms the schema setting**, not that all SSTables have finished converting. Migration activity can run in the background while the application keeps reading and writing.

## 6. Transition Load Generated and Common Symptoms

| Load source | Why it increases after strategy change? | Symptoms to monitor |
| --- | --- | --- |
| **Disk write I/O** | Compaction writes output SSTables and may rewrite old data multiple times | Disk write throughput, disk utilization, pending compactions |
| **Disk read I/O** | Re-reading multiple input SSTables | Read times, contention with queries, disk queues |
| **CPU** | Decompression/compression, merging, and rebuilding storage structures | High CPU, rising query latency |
| **Disk space** | Inputs remain while outputs are written; snapshots can pin files | Falling free disk, flush failures if critically low |
| **Application latency** | Reads/writes contend for resources with compaction | Rising p95/p99, timeouts, dropped messages |
| **Memory/cache** | Different file/index counts and I/O can shift cache efficiency | Fluctuating cache hit rate and read latency |
| **Tombstones** | Tombstone cleanup depends on `gc_grace_seconds`, overlap, TTL, and safety checks | SSTable count and reclaimed space do not drop immediately |
| **Repair/streaming** | Other maintenance tasks also generate I/O/SSTables and compete for resources | Longer repair/streaming durations, compaction backlog |

**Network load** comes primarily from replication, streaming, repair, and client traffic; normal compaction is **node-local**, so you should not claim every compaction copies SSTables over the network. Network impact can be **indirect** if queries/streaming slow down or the cluster runs many parallel tasks.

### Tombstones Do Not Vanish Immediately After Changing Strategy

A deleted or TTL-expired column leaves a tombstone. Cassandra can only drop tombstones when safety conditions are satisfied, including `gc_grace_seconds` and relationships with older data in potentially overlapping SSTables, depending on strategy and data type. Never lower `gc_grace_seconds` recklessly to “clean up fast”, because a replica that missed a delete can resurrect stale data if the grace window expires before synchronization/repair.

TWCS can efficiently reclaim entire expired SSTables **when data in the same window shares similar lifetimes and no live records block it**. Frequent late-timestamped backfills, updates to old events, or mixed TTLs make reclamation unpredictable. Distinguish **logical deletion speed** from **physical disk reclamation speed**.

## 7. Controlled Transition Plan

### Before Changing

1. **Measure workload:** read/write ratio, per-partition query patterns, partition sizes, SSTable counts, TTLs, deletes, backfills, and ingest timing.
2. **Verify version:** confirm class name and options are supported on all nodes; record current schema for rollback.
3. **Set criteria:** e.g., read p95 does not rise past acceptable threshold, free disk stays above reserve floor, pending compactions do not grow continuously.
4. **Budget per-node resources:** free disk, I/O, and fresh-write rate; check snapshots/backups pinning SSTables.
5. **Pick timing:** avoid overlapping with large repairs, bootstrap/decommission/streaming, or heavy backups if headroom is tight.
6. **Prepare observability and rollback:** per-node/table dashboards, logs, comparison queries, and decision owner.

### During Transition

~~~mermaid
flowchart TD
    B["Baseline and verify sufficient resources"] --> C["ALTER TABLE in lab/canary"]
    C --> O["Monitor schema, compaction, p95/p99, disk"]
    O --> D{"Are resources and SLAs\nwithin limits?"}
    D -->|Yes| E["Observe until stable,\ncompare under same workload"]
    D -->|No| F["Throttle load/adjust plan,\nevaluate rollback"]
    E --> G["Roll out to broader scope\nwhen backed by evidence"]
    F --> O
~~~

- **Canary first:** test on a representative table or equivalent environment under realistic load before touching huge tables. Compaction strategy is a **table** property, not a per-replica toggle, so “node-by-node rollout” means controlling environment/load rollout, not running two different strategies on the same table in one cluster.
- **Keep ingest within disk capacity:** sustained backlog growth signals compaction resources cannot keep up with writes. Pause other background jobs if possible.
- **Observe multiple checkpoints:** right after ALTER, at peak backlog, and after stabilization; compare data/loads over matching measurement windows.
- **Throttle background work deliberately:** throughput/concurrency configs depend on version and host budget. For instance, `nodetool setcompactionthroughput` can adjust compaction throughput, though no single number fits every cluster.

### After Transition

1. Confirm schema agreement across nodes.
2. Record SSTable counts, bytes read/written, pending compactions, and disk space at multiple timestamps.
3. Run the same suite of CQL/Java partition-key queries to compare latency/timeouts.
4. Evaluate TTL/tombstone reclamation rates after enough observation time; do not conclude prematurely before windows expire.
5. Monitor across one full representative ingest/TTL cycle to confirm long-term trends.

## 8. Reading Metrics with nodetool and Java Applications

### 8.1. Inspection Commands Without Forcing Major Compaction

~~~bash
nodetool status
nodetool compactionstats
nodetool tablestats telemetry.events_by_device_day
nodetool getcompactionthroughput
~~~

**Do not run `nodetool compact` as a mandatory step right after `ALTER TABLE`.** Major compaction can create huge files, consume heavy CPU/I/O and disk space; on some strategies/time-series tables, it also harms window separation or expired-SSTable drops. Only force compaction after understanding the command's impact, version behavior, and verifying ample headroom.

### 8.2. Java Probe Sample Without Broad Scans

The Java Driver 4.x example below tests a small read query using the proper partition key and clustering range. This is a **read-path latency probe**, not a direct measure of all compaction work:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class CompactionReadProbe {
    private final CqlSession session;
    private final PreparedStatement query;

    public CompactionReadProbe(CqlSession session) {
        this.session = session;
        this.query = session.prepare(
            "SELECT event_time, payload " +
            "FROM telemetry.events_by_device_day " +
            "WHERE tenant_id = ? AND device_id = ? AND day = ? " +
            "AND event_time >= ? AND event_time < ?");
    }

    public long measureMillis(String tenantId, UUID deviceId,
                              LocalDate day, Instant from, Instant to) {
        long started = System.nanoTime();
        int seen = 0;

        for (Row row : session.execute(
                query.bind(tenantId, deviceId, day, from, to)
                    .setPageSize(100)
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM))) {
            if (++seen > 1_000) {
                throw new IllegalStateException("Measurement range too large");
            }
            // Touch actual data to measure result decoding as well.
            row.getString("payload");
        }

        long elapsed = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - started);
        System.out.printf("rows=%d latency_ms=%d%n", seen, elapsed);
        return elapsed;
    }
}
~~~

Reuse `PreparedStatement` and `CqlSession`. Collect many samples and calculate p50/p95/p99 on the measurement side, controlling request rate, data, and cluster state; never draw conclusions from a single probe. Choose `LOCAL_QUORUM` fitting actual RF/DC; consistency level does not optimize a strategy by itself. Measure read and write latencies together, as one strategy can improve reads while raising write cost.

**Example caveat:** page size and row count have logical caps, yet the driver still fetches rows before detecting the cap was exceeded. In heavy load tests, bound the time/partition range in the test data itself and keep probes isolated from production apps.

## 9. When to Roll Back and What Does Rollback Actually Mean?

Suppose a table switches from STCS to LCS and compaction backlog rises steadily, free disk approaches warning thresholds, and write p99 breaches SLA. You may consider reverting to the previous strategy:

~~~sql
-- Example reverting to STCS after a data-driven decision.
ALTER TABLE telemetry.events_by_device_day
WITH compaction = {
    'class': 'SizeTieredCompactionStrategy'
};
~~~

However, **rolling back the schema does not immediately revert all SSTables**. Files already written under the new strategy remain until subsequent compactions process them; changing again can generate **even more** background work. Therefore:

- Prioritize **preventing disk exhaustion**, throttling competing work, keeping replicas healthy, and assessing completion feasibility before changing strategies again.
- If rolling back, log the timestamp, old configuration, and compaction state, and monitor until the system stabilizes.
- Do not treat a successful CQL rollback as the end of risk; backlog, old SSTables, and latency impacts may persist.
- If migration drags on due to huge legacy data, build a plan with proper I/O/disk budgets instead of flipping strategies back and forth.

**Do not manually delete SSTables to free space.** SSTables belong to Cassandra's storage engine; deleting files manually risks data loss or replica divergence. Use supported operational procedures, monitoring, and validated backups.

## 10. Scenario-Based Decision Table

| Symptom | Questions to investigate | Action direction |
| --- | --- | --- |
| Slow point reads, many overlapping SSTables | Does the query include the partition key? Does STCS leave many files to inspect? | Optimize query first; test LCS/UCS on equivalent workload |
| High writes, compaction contending for I/O | What is the rewrite/throughput ratio? | Evaluate STCS/UCS, allocate I/O, and control concurrency |
| Time-series TTL not reclaiming disk | Are there backfills/late updates, mixed TTLs, or cross-window SSTables? | Inspect TWCS, timestamp writes, and TTL policies |
| Free disk drops rapidly after switching strategy | Which compaction is writing large outputs? Are snapshots pinning files? | Shed load, check headroom, adjust plan/roll back if needed |
| Pending compactions climbing | Do writes exceed compaction throughput? Is repair/streaming concurrent? | Find bottleneck and reschedule work |
| `ALTER TABLE` succeeded but latency hasn't improved | Have SSTables been rewritten/stabilized yet? Is test load comparable? | Keep observing over bounded window, compare multiple metrics |
| Want to use UCS on an older cluster | Do the server and distribution support UCS? | Verify version first; never force unsupported options |

## 11. Practice Exercises

**Exercise 1 — Root-Cause Explanation.** A table has the same partition across 40 SSTables, and point reads frequently reconcile many files. Distinguish read amplification from write amplification; predict the impact of testing LCS and state which metrics to measure to verify.

**Exercise 2 — Strategy Switch.** Create the lab table in Section 4, check its schema, run `ALTER TABLE` from STCS to TWCS in a supported environment, then re-read `system_schema.tables`. Explain why seeing the updated `compaction` value does not mean existing SSTables have been split into new time windows.

**Exercise 3 — Time-Series with Backfill.** A device goes offline for 10 days and then replays old data in a single ingest batch today. Analyze why the old `event_time` column does not necessarily dictate TWCS windows; propose how to control backfills and evaluate TTL effectiveness.

**Exercise 4 — I/O Budget.** A node sees free disk dropping while compaction writes outputs. Build a time-series tracking table for free disk, pending compactions, bytes read/written, p99, and throughput; specify concrete thresholds for continuing, throttling, or rolling back.

**Exercise 5 — Combined Repair and Node Recovery.** A node just recovered and is running repair/streaming while a table switches to LCS. Why can this workload spike p99? Outline a maintenance sequence to avoid resource contention and distinguish repair from compaction.

**Exercise 6 — Choosing Among STCS/LCS/TWCS/UCS.** Given three tables: (a) a session table with continuous updates and random reads; (b) a log table with a uniform 14-day TTL and rare edits; (c) a write-heavy, read-light table. Pick an *initial* strategy for each, state assumptions, version requirements, and a benchmark plan to validate.

## Key Takeaways

**`ALTER TABLE ... WITH compaction` only changes the SSTable selection policy; on-disk conversion can take time and generate CPU, I/O, temporary space, compaction backlog, and latency fluctuations.** Choose strategies based on queries, write patterns, TTLs, and Cassandra version; measure per-node baselines, preserve disk headroom, observe until steady state, and recognize that schema rollback does not instantly erase transition overhead. Compaction optimizes local storage, whereas replication and repair solve separate problems in a distributed system.
