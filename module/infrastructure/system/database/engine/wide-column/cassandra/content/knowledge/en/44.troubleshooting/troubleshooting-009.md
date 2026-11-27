# Excessive Tombstones or Queries Hitting Large Partitions

## 1. Real-World Scenario: A Timeline API Is Slow Even When Fetching Just 20 Rows

A Java system uses **Apache Cassandra** to store IoT events and lets users query the latest 20 events for a device. For the first few months, API p99 stays under 50 ms. After enabling a 30-day TTL, ramping up ingestion, and adding bulk delete jobs, some queries take several seconds or return read timeouts. Node logs occasionally warn about **scanning huge numbers of tombstones**, while another group of devices has **oversized partitions** and reads slowly despite almost zero tombstones.

Crucially, both issues can coexist on the same table, yet **their root causes, evidence, and fixes differ**:

- **Tombstone-heavy read:** the replica must skip past many deletion/expiration markers or SSTable versions before finding enough live rows; `LIMIT 20` does not mean reading only 20 physical cells.
- **Oversized/hot partition:** one partition key accumulates excessive clustering rows/bytes or request concurrency, driving up memtable/SSTable work, compaction, heap/GC, and disk/network load—especially when queries scan wide ranges.
- **Both:** a massive partition containing waves of expired TTL rows or overlapping range deletes; p99 spikes sharply and requires fixing both workload/query shapes and data lifecycle.

~~~mermaid
flowchart TD
    A["API SELECT LIMIT 20, high p99"] --> B["Coordinator reads by partition key"]
    B --> C["One or more full replicas read memtable + SSTables"]
    C --> D{"Are live rows easy to find?"}
    D -->|Dense tombstones| E["Scan many deletion markers/cells"]
    D -->|Large partition or wide range| F["Scan many clustering rows/bytes and SSTables"]
    E --> G["Disk/CPU/GC/network pressure, read timeout, or warnings"]
    F --> G
    G --> H["Measure exact source rather than just raising timeouts"]
~~~

This lesson belongs to the **Troubleshooting** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module: distributed architecture, wide-column model, partition keys, query-driven table design, read/write consistency, replication, compaction, repair, and Java integration.

**Objectives:**

1. Distinguish tombstones, expired TTL cells, partition/range/row deletions, large partitions, and hot partitions.
2. Read timeout signals, tombstone warnings, histograms, tracing, and load distributions before picking a fix.
3. Write CQL queries with **full partition keys + clustering ranges + limits**, understanding why they can still be expensive.
4. Trace causes from TTL, `DELETE`, `UPDATE ... SET column=null`, write patterns, bucket sizes, data skew, and compaction strategies.
5. Evaluate safety around `gc_grace_seconds`, tombstone purging, hints, replica repair, and zombie data risks.
6. Separate short-term mitigations (rate/concurrency/page/timeout policies) from durable fixes (bucketing/sharding/query-driven tables).
7. Build runbooks, dashboards, Java Driver guardrails, integration/load tests, and incident exit criteria.

> **Version scope:** examples use CQL/Driver 4.x and Apache Cassandra 4.x/5.x concepts; exact command names, metrics, guardrails, compaction options, and warning defaults vary by deployment. Never treat illustrative numbers as universal production thresholds. Load-inducing operational commands must only be executed with proper authorization and planning on appropriate clusters.

## 2. First Separate Three Distinct Phenomena

| Phenomenon | Typical Signals | What to Prove? | Remediation Direction |
| --- | --- | --- | --- |
| **Tombstone-heavy query** | Deletion-marker scan warnings/errors; high tombstone-scanned histogram; few live rows yet high latency. | How many tombstones the query scans, in which partition/range, and what creates the deletes/TTLs. | Stop excessive tombstone generation; improve query locality, retention, compaction, and repair per policy. |
| **Large partition** | High estimated/max partition size, many clustering rows, heavy bytes scanned/transferred, rising GC/disk/compaction. | Which partition key concentrates data, byte/row ratios, and how wide the query range is. | Redesign partition key, time bucketing, bounded sharding, and query-driven projections. |
| **Hot partition** | A few keys absorb high read/write QPS; specific replicas/coordinators run hot even without giant partitions. | QPS distribution across keys/tokens and replica placement; confirm whether skew exists. | Caching/rollups, rate limits, bounded distribution/sharding, and fixing client workload. |
| **Other cluster overload** | High p99 across multiple tables; GC/disk/compaction/repair backlogs, network, or driver throttling. | Timeline correlation with CPU, disk, GC, pending tasks, and retries. | Fix the operational bottleneck; never blame tombstones without evidence. |

A partition of just a few MiB can be **extremely hot**; conversely, a partition of hundreds of MiB that is rarely read might not cause an immediate incident. Never blame every high p99 on "large partitions" merely because a table holds many rows cluster-wide: Cassandra distributes **per partition token**, and the real question is how large or hot **one specific key** is.

### 2.1. Signals to Classify Early on the Client

~~~text
request:
  query_name          = events_recent_by_device_day
  CQL shape           = SELECT ... WHERE full_partition_key AND time_range
  regular CL          = LOCAL_QUORUM
  driver page size    = 100
  CQL LIMIT           = 100
  request timeout     = 1s (example)
  device/day          = redacted or controlled hash

observed:
  error class         = ReadTimeout / Unavailable / client timeout / other
  latency             = ...
  attempts/coordinator= ...
  rows actually read  = ...
  app JSON bytes      = ...
~~~

**`ReadTimeout`**, **`Unavailable`**, and driver request timeouts are not the same thing, nor do they mean data was lost. A query aborted by a tombstone threshold differs from one failing for lacking replicas. Classify the error accurately before retrying or touching CL.

## 3. What Is a Tombstone in Cassandra?

A **tombstone** is a deletion/expiration marker in Cassandra's storage structures used to reconcile cell versions across replicas and SSTables. Just because an API no longer sees a row **does not mean** the physical data and deletion marker vanished from all SSTables immediately.

### 3.1. Common Forms

| Form | Common Source | Read / Operational Impact |
| --- | --- | --- |
| **Cell tombstone** | Deleting/setting `null` on a column, or cell TTL expiration. | Reads must inspect deletion markers before determining which columns remain live. |
| **Row deletion** | `DELETE` of one row by full clustering key. | Row cells are shadowed by deletion timestamp; requires replica convergence. |
| **Range tombstone** | `DELETE` of a clustering range inside a partition. | Scanning clustering ranges must evaluate interval markers, especially when overlapping. |
| **Partition deletion** | `DELETE` of an entire partition by partition key. | Shadows all rows in the partition with a deletion timestamp; scope/range and SSTables still matter. |
| **TTL expiration** | `USING TTL` or `default_time_to_live`. | Cell logically expires and behaves as a deletion/expiry during reads and compaction. |

**Not every `UPDATE` creates a tombstone:** writing a non-null value to the same cell creates a newer version; deleting a column or setting `null` is a deletion whose exact behavior depends on mapping/driver settings. Likewise, it is false that "every overwritten cell becomes a tombstone": older versions are shadowed and cleaned during compaction under standard rules.

### 3.2. Why Not Delete Immediately?

Cassandra maintains multiple replicas and stores memtables/SSTables in an LSM tree. If R1 receives a `DELETE` while R3 is down, R3 still holds the old live row. Tombstones must persist long enough and propagate via replication/repair so the old row does not resurrect (**zombie data**) when R3 rejoins.

~~~mermaid
sequenceDiagram
    participant C as Coordinator
    participant R1 as R1
    participant R2 as R2
    participant R3 as R3 (down)
    C->>R1: DELETE key
    C->>R2: DELETE key
    C--xR3: Missing delete
    R1-->>C: ACK
    R2-->>C: ACK
    C-->>C: LOCAL_QUORUM met 2/3
    Note over R1,R2: Tombstone retained to shadow old version
    Note over R3: Old row may still exist
    Note over R1,R3: Repair/hints and grace policy govern safety
~~~

### 3.3. Tombstone Scan Count Is Not Total Tombstones on Disk

A "scanned X tombstones" warning reflects **one specific read path** on a replica/coordinator per instrumentation/version. It does **not** mean the whole table contains only X tombstones, nor that each live row corresponds to one tombstone. Likewise, table histograms reflect **recent scan distributions**, not an exact count of every tombstone stored on disk.

## 4. Large Partitions: Logical Size, On-Disk Size, and Rows Scanned

A Cassandra partition groups rows sharing the exact **full partition key**, ordered by clustering keys. Because a partition spans multiple SSTables and replicas, "partition size" needs clear definitions:

- **Logical live bytes/rows:** data currently readable via CQL at a given point/CL.
- **SSTable partition bytes:** data stored in a single SSTable, including older versions and tombstones; one logical partition spans many SSTables.
- **Per-read cost:** how many SSTables, bytes, cells, and markers must actually be decoded or merged to serve a query.
- **Hotness:** read/write request rate, concurrency, and replicas stressed by a key—not strictly proportional to byte size.

### 4.1. Table Design Prone to Unbounded Partition Growth

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_diag
WITH replication = {'class':'NetworkTopologyStrategy','dc1':3};

-- V1: ONE partition per device, accumulating years of events together.
CREATE TABLE IF NOT EXISTS telemetry_diag.events_by_device_v1 (
    tenant_id text,
    device_id text,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id,device_id),event_time,event_id)
) WITH CLUSTERING ORDER BY (event_time DESC,event_id ASC);
~~~

If `device-7` emits 25 events/second at an average of 600 bytes **estimated payload + overhead**:

\[
25\times86{,}400\times600
=1{,}296{,}000{,}000\ \text{bytes/day}
\approx1.21\ \text{GiB/day}.
\]

A single month exceeds **tens of GiB** of logical writes for **one partition key** without TTL or bucketing; physical disk further depends on compression, compaction, tombstones, and RF. These numbers are **illustrative**, not a hard Cassandra threshold or guaranteed compression ratio.

### 4.2. Cassandra Has No Universal "Safe Partition Size for Every Workload"

Do not treat "every partition must be under X MiB" as an official universal rule. Operational targets should follow **workload statistics**:

| Indicator | Question | Why It Matters |
| --- | --- | --- |
| Estimated p95/p99 partition size | Is there an extreme tail? | A few keys can dominate disk capacity and compaction work. |
| Max partition size / row count | Which key is the outlier? | Broad range queries face high latency/timeout risk. |
| Rows read/page and bytes returned | Scanning too wide or pulling unused `payload`? | Heap/GC/network pressure in Java and replicas. |
| SSTables per read | Merging too many files/versions? | Read amplification. |
| Partition-specific QPS | Is one key a hotspot? | Replica/coordinator scheduling and cache pressure. |
| TTL / delete density | Ratio of tombstones to live rows? | Tombstone scanning and compaction load. |

A 30 MiB partition can still cause severe trouble if it holds **millions of tiny rows** and heavy tombstones; a larger partition queried with a tight clustering range might perform adequately. **Measure the real read path** rather than relying solely on file size.

## 5. Read Path: Why Is `LIMIT 20` Still Slow?

### 5.1. CQL `LIMIT` Bounds Only *Logical Results*

~~~sql
-- Query supplies full partition key, yet NO time bound.
SELECT event_time,event_id,event_type,payload
FROM telemetry_diag.events_by_device_v1
WHERE tenant_id='tenant-a' AND device_id='device-7'
LIMIT 20;
~~~

If the first 500,000 rows from the start of the scan have expired via TTL or been deleted, Cassandra must **walk past huge numbers of deletion markers and shadowed versions** to collect 20 live rows. `LIMIT` never forces a replica to inspect only 20 physical cells or 20 bytes. Bad cases trigger warnings, tombstone failures, or timeouts depending on version, thresholds, and workload.

### 5.2. Use Clustering Ranges Matched to Business Needs

~~~sql
SELECT event_time,event_id,event_type
FROM telemetry_diag.events_by_device_v1
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_time >= '2026-11-20T00:00:00Z'
  AND event_time < '2026-11-21T00:00:00Z'
LIMIT 100;
~~~

This is a **bounded partition lookup + clustering time range**, far better than scanning all history when the product only asks for one day. Still, if **that specific day** holds hundreds of thousands of tombstones or massive payloads, reads remain slow; adding a range **narrows scope**, without guaranteeing zero tombstones.

### 5.3. `page-size` Is Not a Cure-All Either

Java Driver can set page size to 50 instead of 500. That caps rows per network page (as a target count, not an absolute byte cap) and keeps Java heap smaller, yet **if a replica must scan 100,000 tombstones before finding one live row, even `page-size=10` still times out**.

Likewise, `SELECT *` pulls large unused `payload` columns. Select **only required columns**, bound queries, and inspect server-side work.

## 6. Tombstone-Generating Patterns in Java and CQL

### 6.1. `DELETE` and `UPDATE` Setting `null`

~~~sql
-- Delete one column of a row identified by full primary key:
DELETE payload FROM telemetry_diag.events_by_device_v1
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_time='2026-11-21T08:00:00Z'
  AND event_id=123e4567-e89b-42d3-a456-426614174001;

-- Delete the whole row:
DELETE FROM telemetry_diag.events_by_device_v1
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_time='2026-11-21T08:00:00Z'
  AND event_id=123e4567-e89b-42d3-a456-426614174001;

-- Some mapper/driver code sends null as a deletion:
UPDATE telemetry_diag.events_by_device_v1
SET payload = null
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_time='2026-11-21T08:00:00Z'
  AND event_id=123e4567-e89b-42d3-a456-426614174001;
~~~

In Java Driver, distinguish **CQL `NULL`** from **`UNSET`**: `setToNull(...)` carries deletion semantics, whereas `unset(...)` (when supported by version/protocol) leaves the column untouched. A Spring Data `save()` on a partially loaded entity whose omitted fields are `null` can silently delete cells depending on converter/mapping settings. Always inspect generated CQL and run integration tests—never assume Java `null` means "leave unchanged".

### 6.2. Range `DELETE` on Clustering Columns

~~~sql
-- Example on a table with event_time as first clustering column:
DELETE FROM telemetry_diag.events_by_device_v1
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_time < '2026-11-01T00:00:00Z';
~~~

Deleting a clustering range writes a **range tombstone** instead of immediately scrubbing SSTable rows. If an hourly job repeatedly deletes overlapping historical ranges, replica reads must evaluate growing sets of interval markers. Designing retention via **bucketing + appropriate TTL** usually beats scheduled bulk `DELETE` scans of millions of rows, though compaction and repair policies still determine when space is safely reclaimed.

### 6.3. Default TTL and Per-Write TTL

~~~sql
-- Illustrative: 7-day expiry counts from mutation write time, not event_time.
INSERT INTO telemetry_diag.events_by_device_v1
  (tenant_id,device_id,event_time,event_id,event_type,payload)
VALUES
  ('tenant-a','device-ttl','2026-11-21T08:00:00Z',
   123e4567-e89b-42d3-a456-426614174002,'HEARTBEAT','ok')
USING TTL 604800;
~~~

TTL expires based on **write-time / server semantics**, not when `event_time` becomes seven days old. If a late event timestamped last year is inserted today, a 7-day TTL normally starts **at insert time**, not the event's timestamp. For time-series data, explicitly decide **ingestion-time retention vs. event-time retention** and test replays/backfills.

**Never** remove TTL across every table just to "eliminate tombstones"; dropping TTL causes unbounded partition/disk growth, while overly short TTL breaks retention and business correctness.

## 7. `gc_grace_seconds`: A Safety Guard, Not a "Clean Now" Button

`gc_grace_seconds` defines how long deletion markers are retained so replicas that missed a delete have a window to synchronize. Actual physical reclamation also depends on SSTable overlap, compaction strategy, repair state, and Cassandra version.

### 7.1. Zombie Data Risk

~~~mermaid
sequenceDiagram
    participant R1 as Replica R1
    participant R2 as Replica R2
    participant R3 as Replica R3 (down)
    R1->>R1: DELETE -> tombstone
    R2->>R2: DELETE -> tombstone
    Note over R3: Retains old live row
    Note over R1,R2: Not repaired in time
    Note over R1,R2: Compaction post-grace may purge tombstone
    R3-->>R1: Old node rejoins with live row
    Note over R1,R3: Zombie data can resurrect
~~~

### 7.2. Operational Rules

- Repair all relevant replica/table/token scopes **frequently enough relative to grace and maintenance windows**; track **coverage and last successful repair**, not merely job invocation counts.
- Never set `gc_grace_seconds=0` on tables with RF>1, deletes, replica outages, or compliance retention unless **strict special conditions are verified by DBA/SRE**.
- Never run `nodetool compact` / force major compaction assuming it will "safely purge all tombstones" while replicas remain unrepaired; it drives heavy I/O without guaranteeing safe reclamation.
- Never delete SSTables, commit logs, or hints, or forge mutation timestamps to "clean dirty data"; you risk destroying deletion history.
- When a node stays down near or beyond grace, follow **node recovery/replace/restore runbooks** and reconcile against external sources of truth rather than assuming full repair recovers lost deletion history.

### 7.3. Hints and Read Repair Do Not Replace Anti-Entropy

Hinted handoff is a **best-effort**, time-bounded replay of missed writes for temporarily absent replicas; read repair only heals data touched by reads per version/config. Preserving tombstone correctness requires scheduled **anti-entropy repair** across token ranges, DCs, and replicas. Once a tombstone is purged from all remaining sources, repair cannot reconstruct deletion intent out of thin air.

## 8. What Do Tombstone Warnings and Failures Actually Indicate?

Many Cassandra releases expose thresholds such as:

~~~yaml
# Illustrates common Cassandra parameter names,
# NOT settings to apply blindly in production.
tombstone_warn_threshold: 1000
tombstone_failure_threshold: 100000
~~~

Values **1,000 / 100,000 are merely common historical defaults** in certain releases, not fixed standards across every Cassandra version, distribution, guardrail, or query. These thresholds measure tombstones **scanned** during a single read per implementation semantics—**not total tombstones stored on a partition**.

### 8.1. Distinguishing Warnings, Failures, and Timeouts

| Symptom | Likely Meaning | Action Required |
| --- | --- | --- |
| Warning "Scanned over ... tombstones" | A read scanned enough tombstones to breach the warn threshold. | Identify query/key/range, logs/metrics, and mutation source. |
| Tombstone failure / `TombstoneOverwhelmingException` | Server aborted the read beyond the failure threshold to protect resources. | Fix tombstone/query root cause; do not simply bump threshold. |
| `ReadTimeout` / driver timeout | Query exceeded deadline or replicas/queues/network stalled. | Analyze load, SSTables/tombstones, CL, GC/disk, and coordinator. |
| `Unavailable` | Insufficient live replicas for CL per current membership. | Check topology/RF/DC; do not blame tombstones by default. |
| Client memory/GC pressure | `SELECT *`, huge pages/bytes, Java heap accumulation. | Narrow projections/pages/rows; profile heap and driver. |

**Tombstone warnings and timeouts can co-occur, yet are not identical.** A large partition full of live rows can time out with zero tombstone warnings.

### 8.2. Why Raising Thresholds Only Masks the Problem

Cranking `tombstone_failure_threshold` sky-high so reads "stop failing" lets queries burn CPU, disk, and heap for longer, harming co-located tenants on the replica and raising cluster-wide p99. Consider tuning thresholds **only after** profiling query load, benchmarking, checking resource budgets, and securing approval/rollback; it is never the primary fix.

## 9. First 15-Minute Triage: Protect SLOs and Collect Evidence

When p99 climbs or tombstone failures fire, prioritize **impact containment** and **root-cause classification** before touching SSTables.

### 9.1. Initial Action Map

~~~mermaid
flowchart TD
    A["High read p99 or tombstone warnings"] --> B["Confirm query_name, CL, partition, and UTC window"]
    B --> C{"Widespread across all queries?"}
    C -->|Yes| D["Check node health, GC, disk, pending tasks, compaction, network"]
    C -->|No, specific partitions| E["Measure tombstone scans, partition size, hot keys, query range"]
    D --> F{"Node overloaded / replica down?"}
    F -->|Yes| G["Shed background load; restore availability and capacity"]
    F -->|No| E
    E --> H{"High tombstone scans?"}
    H -->|Yes| I["Check TTL/DELETE/null writes, SSTables/compaction, repair"]
    H -->|No| J["Check partition bytes/rows, wide ranges, payload, QPS"]
    I --> K["Bounded mitigation + planned schema/retention fix"]
    J --> K
    G --> L["Re-measure SLO + consistency + data correctness"]
    K --> L
~~~

**Not everything is solved in 15 minutes.** This is the sequence for **collecting traces and protecting the cluster**; table redesigns, repairs, and compaction strategy changes belong in planned staging-tested workflows.

### 9.2. Questions You Must Answer

1. **When did it start?** Did a Java deploy, backfill, TTL policy change, batch DELETE, compaction/repair, or RF/CL change immediately precede the p99 rise?
2. **How wide is the blast radius?** One `query_name`, one tenant/device/day, one table, one token range, or the whole cluster?
3. **What is the read path?** Does the query supply the full partition key, or use `ALLOW FILTERING`, `IN`, wide ranges, or `SELECT *` pulling huge payloads?
4. **Which replicas are slow?** Any Down nodes, disk await, GC pauses, dropped tasks, or compaction backlogs?
5. **Tombstone evidence?** Server scan warnings, rising JMX histograms, and matching requests?
6. **Partition size/hotness?** How many rows/bytes live under that specific key; is request rate heavily skewed?
7. **Consistency contract?** Does the caller truly require `LOCAL_QUORUM`; is multi-DC or repair lag complicating reads?
8. **Safe load shedding?** Can you pause batch analytics, rate-limit non-essential endpoints, narrow time windows, or trim projections without breaking correctness?

### 9.3. Never Gather Evidence in Ways That Worsen the Outage

- Never run `SELECT * FROM ks.table`, full-table `COUNT(*)`, or broad `ALLOW FILTERING` on degraded production.
- Never turn on `TRACING ON` for 100% of traffic, and never force repeated compactions/flushes just to "check status".
- Never print raw partition keys, payloads, JWTs, credentials, or sensitive CQL literals into shared dashboards/logs; use query names, sampled hashes, and access-controlled logs.
- Never configure infinite driver retries: slow requests fan out across coordinators/replicas and trigger **retry amplification**.
- Never downgrade `LOCAL_QUORUM` to `LOCAL_ONE` just to turn charts green without evaluating business consistency.

## 10. Cassandra-Side Observation Tools: Commands, Metrics, and Limits

### 10.1. `nodetool` Commands on Authorized Nodes

~~~bash
# Observe first; zero data-deleting commands here.
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool gcstats
nodetool proxyhistograms
nodetool tablestats telemetry_diag.events_by_device_v1
nodetool tablehistograms telemetry_diag events_by_device_v1
~~~

| Tool | Answers | Does **Not** Automatically Answer |
| --- | --- | --- |
| `nodetool status` | Node/DC/rack/token membership, `UN`/`DN`. | Which key is oversized or tombstone-heavy; `UN` does not prove converged replicas. |
| `nodetool info` | Load, uptime, key cache, version-specific node info. | Exact root cause of read timeouts. |
| `nodetool tpstats` | Thread-pool pending/completed/dropped tasks. | What sits inside SSTables of a specific partition. |
| `nodetool compactionstats` | Pending/running compactions, estimated bytes/progress. | Whether a given tombstone has been safely purged. |
| `nodetool gcstats` | Per-node GC counts and pause durations. | Whether tombstones exist without table/query evidence. |
| `nodetool proxyhistograms` | Read/write latency distribution at the coordinator. | End-to-end HTTP, serialization, or pool wait latency. |
| `nodetool tablestats` | Table-local reads/writes, SSTables, partition estimates, caches/bloom/tombstones per version. | Exact logical row count or cross-replica equality. |
| `nodetool tablehistograms` | Version-specific histograms of partition sizes, cell counts, and latencies. | Which query caused the tail outlier without log/query correlation. |

**Check versions:** Cassandra 3.x used `cfstats`/`cfhistograms`; Cassandra 4.x/5.x changed outputs and flags. Never copy metric names or flags across versions without testing in a lab.

### 10.2. JMX / Metrics Worth Watching

| Metric (Conceptual Name; Exact Name May Vary) | Diagnostic Meaning |
| --- | --- |
| `TombstoneScannedHistogram` | Distribution of tombstones scanned across table reads per Cassandra instrumentation. |
| `LiveScannedHistogram` | Compares live cells/rows scanned against tombstones; not an exact on-disk row count. |
| `EstimatedPartitionSizeHistogram` | Estimated partition size distribution; spots heavy tails. |
| `MaxPartitionSize` / `MeanPartitionSize` | Outlier / rapid partition growth clues; semantics may be per-SSTable. |
| Table `ReadLatency`, coordinator `ClientRequest.Read.Latency` | Separates local table storage reads from overall coordinator read requests. |
| `SSTablesPerReadHistogram` | Read amplification from merging multiple SSTables. |
| `PendingCompactions`, compaction throughput | Whether compaction keeps pace with writes/deletions. |
| Thread pool `PendingTasks` / `DroppedTasks` | Queue backlogs/overload, not solely tombstones. |
| JVM heap/GC/disk await/CPU/RTT | Physical resource bottlenecks driving tail latency. |

MBean names usually sit under `org.apache.cassandra.metrics` with `type=Table`, `keyspace`, `scope`, and `name`; **never assume exact names** from this table, especially on Cassandra 5.x or vendor distributions. Inspect your actual exporter's metric list, build dashboards by **node + DC + keyspace/table + query name**, and never put raw partition keys into metric labels.

### 10.3. Reading Histograms Properly

- **Histograms show measurement distributions** over a window/scope—not always "how many tombstones currently exist in the table".
- **Cumulative vs. windowed:** restarts or exporter resets alter values; never compare 10-day cumulative stats on one node against a freshly restarted node.
- **Per-node p99s cannot be summed or averaged** into a cluster p99. Merge compatible histogram buckets/scopes properly.
- **Estimated partition size** comes from on-disk stats and may differ from live logical bytes or merged partition size across all SSTables.
- **High p99 can reflect queue saturation** even when tombstone histograms barely move; view histograms alongside CPU/GC/compaction, offered QPS, and timeouts.

### 10.4. Locating Which Partition or Hot Key Causes Trouble

Least-invasive order:

1. From **application tracing / structured logs**, identify sampled `query_name` and hashed/canonical partition IDs of slow requests.
2. Compare **per-device/per-bucket event distributions** from an application ingestion ledger or rollup source—**never** full-table `COUNT(*)`.
3. Use `nodetool toppartitions` or node/metric tools **if supported and authorized**, with bounded duration and top-K; it reflects **recent activity/hotness**, not an exact ranking of largest partitions by bytes.
4. Cross-check with `tablestats`/`tablehistograms`, sampled query traces, and disk/GC metrics.
5. For SSTable forensics, run `sstablemetadata`/`sstabledump` per runbook **on snapshots or offline copies**, never scanning live SSTables haphazardly mid-incident.

**Security:** partition keys may embed tenant or device identifiers; redact or hash them in reports and keep raw values out of general telemetry.

## 11. Query Tracing and Logs: Pinpointing Which Query Hits Tombstones

### 11.1. A Bounded Sample CQL Query

~~~sql
-- Run in lab/staging or on an approved sample query.
-- CONSISTENCY/TRACING are cqlsh commands, not sent via Java Driver.
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time,event_id,event_type
FROM telemetry_diag.events_by_device_v1
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time < '2026-11-21T09:00:00Z'
LIMIT 50;

TRACING OFF;
~~~

Traces reveal coordinator, queried replicas, read/merge stages, and version-dependent SSTable/tombstone counts; **they do not capture every app, GC, or network detail**. For heavy queries, tracing adds overhead—sample sparingly and turn off immediately once evidence is gathered.

### 11.2. Warnings and Errors in `system.log`

Signals to correlate by query, correlation ID, and time window (exact wording varies):

~~~text
WARN  ... Read ... live rows and ... tombstone cells ...
WARN  ... Scanned over ... tombstones ...
ERROR ... TombstoneOverwhelmingException ...
ERROR ... ReadTimeoutException / overloaded / dropped messages ...
INFO  ... Compaction ... / Repair ...
~~~

**These are conceptual log patterns**, not verbatim strings for every Cassandra release. Some warnings return as **protocol warnings** to Driver 4.x via `ExecutionInfo.getWarnings()`. To correlate with Java requests, record **CQL shape/query name**, UTC timestamp, CL, chosen coordinator, and warning counts instead of logging raw payloads.

### 11.3. When Warnings Originate on Another Node

The driver selects coordinators, and each coordinator selects replicas by token/CL. Even if Java logs `coordinator=R1`, storage bottlenecks may sit on replicas R2/R3. Inspect metrics/logs on **the natural replicas of the affected key**, not just the node the client talked to.

## 12. Hypothesis Table and Non-Destructive Checks

| Hypothesis | Signals | Non-Destructive Verification | Remediation Path |
| --- | --- | --- | --- |
| TTL creates dense tombstones in window. | TTL expiry matches p99 spike; many tombstones, few live rows. | Sample `TTL(col)` on live rows, retention config, histograms/traces. | Proper bucketing, time-windowing, compaction policy; avoid arbitrary TTL bumps. |
| Large-range batch `DELETE`. | Job rollout aligns with tombstone warnings; overlapping range tombstones. | Audit/job logs, CQL shape, SSTable/tombstone stats. | Pause rogue job; switch retention to bucketing + TTL. |
| App writes `null` continuously. | `payload`/fields vanish unexpectedly after Spring Data deploy. | Redacted driver CQL logs, `null` vs. `UNSET` integration test. | Update only needed columns, use `UNSET` cleanly, fix mapping. |
| Unbucketed per-device partition. | Huge max partition size; long-lived/chatty devices are outliers. | Ingestion rate × row bytes × duration, table metrics, bounded sample query. | V2 bucketed by day/hour/shard; dual-write/backfill/cutover. |
| `SELECT *` fetches huge `payload`. | High network/heap/JSON serialization; small row counts. | Compare narrow vs. full projection at same CL/page, response bytes, JVM profile. | Narrow projections, DTOs, or summary tables. |
| Query lacks clustering range. | `WHERE` specifies full partition key yet scans all days. | Query trace, HTTP filters, rows/bytes read. | Enforce bounded time ranges and buckets. |
| `ALLOW FILTERING` / wide token scan. | Many partitions read; latency/IO scales with total table volume. | CQL query review, warnings, table metrics. | Query-driven tables or benchmarked indexes; eliminate broad filtering. |
| Many SSTables, compaction backlog. | High `SSTablesPerRead`, pending compactions, high disk await. | `tablestats`, `compactionstats`, LSM metrics. | Tune capacity/throttling/strategy; avoid blind major compactions. |
| Slow/down replicas or lost quorum. | `UN`/GC/network issues, `Unavailable`/timeouts across many tables. | `nodetool status`, `tpstats`, driver CL/routing, OS metrics. | Restore replica/capacity, run repair per runbook. |
| Insufficient repair / grace window. | Deleted data resurrects; replicas diverge. | Last successful repair coverage, grace period, outage/tombstone history. | DBA/SRE zombie/restore remediation, not merely compaction tweaks. |

Never pick a row from this table and apply a fix immediately. Each hypothesis requires at least **one direct signal** and **one control comparison** (narrow query, metrics, ingestion/compaction timeline, or staging test) before concluding.

## 13. Compaction: Why Don't Tombstones Vanish on Their Exact Expiration Day?

Cassandra writes using an LSM engine: mutations hit commit log + memtable, flush into immutable SSTables, and compaction merges SSTables while resolving versions and deletion markers under strict safety rules.

~~~mermaid
flowchart LR
    A["INSERT/UPDATE/DELETE/TTL"] --> B["Commit log + memtable"]
    B --> C["Flush -> SSTable files"]
    C --> D["SSTables with multiple versions/tombstones"]
    D --> E["Compaction per strategy"]
    E --> F{"Safe to purge? overlap/grace/repair conditions"}
    F -->|No| G["Tombstones persist"]
    F -->|Yes| H["Obsolete data/tombstones partially reclaimed"]
~~~

### 13.1. Why Do Tombstones Persist Past Grace?

- The SSTable holding the tombstone **has not yet been selected** for compaction.
- Another SSTable still holds shadowed data/versions; dropping the marker early risks **resurrecting** old data.
- Compaction strategy, overlap/repair state, TTL expiries of co-located cells in the same SSTable, and guardrails can block or delay purging.
- SSTables may span repaired/unrepaired pools, tightening safety rules.
- Near-full disks or high pending compaction backlogs delay cleanup.

**No guarantee exists** that "30-day TTL + 10-day grace = physical bytes vanish on day 40". TTL defines logical read/retention semantics, not a block-storage deletion timer.

### 13.2. Comparing Compaction Strategies

| Strategy | Typical Fit | Impact on Tombstones / Partitions | Risks to Check |
| --- | --- | --- | --- |
| **STCS** (Size-Tiered) | Write-heavy, general-purpose workloads. | Merges similarly sized SSTables; tombstone purging depends on overlap and compaction scheduling. | High read amplification/SSTable counts, especially with scattered TTL/DELETEs. |
| **LCS** (Leveled) | Read-heavy needing bounded SSTables per read. | Reduces read amplification via leveled organization. | High write amplification and compaction I/O; still cannot fix a bad partition key. |
| **TWCS** (Time-Window) | Append-mostly time-series in time order with uniform TTLs. | Groups SSTables by time window; can drop whole expired SSTables when safe and unshadowed. | Late/out-of-order writes, replays, deletes, or cross-window data block whole-SSTable drops and keep tombstones alive. |
| **UCS** (Unified, where supported) | Mixed read/write workloads with adaptive policies per release. | Differs from STCS/LCS/TWCS; benchmark and check version docs. | Never assume it is enabled everywhere in 4.x/5.x or solves every tombstone issue. |

**TWCS is not a magic switch for every TTL table.** If you frequently update the same partitions/rows across windows, or backfill with older timestamps, verify **write-timestamp / compaction-window semantics** and shadowed-SSTable risks. Time-series with heavy updates/deletes behaves very differently from append-only streams.

### 13.3. Changing Compaction Strategy Will Not Fix a Bad Partition Key

If V1 stores **a device's entire multi-year history** in one tens-of-GiB partition, switching STCS → TWCS may alter read/write amplification or TTL cleanup, yet **the full partition remains huge** and unbounded queries still suffer. The durable fix is **query-driven bucketing/sharding**; compaction is a storage-layer setting, not a substitute for token placement.

### 13.4. Actions Never to Trigger Reflexively

~~~text
DO NOT run immediately in production upon seeing tombstones:
  - nodetool compact cluster-wide on all nodes at once
  - nodetool garbagecollect everywhere ignoring overlap/repair
  - setting gc_grace_seconds to 0 to "wipe tombstones"
  - cranking tombstone_failure_threshold sky-high so queries stop failing
  - running full repair across all token ranges simultaneously
  - manually deleting SSTables, hints, or commit logs
  - ALTER TABLE switching to TWCS without benchmarking existing data
~~~

Even if an operation frees space, weigh **data safety, replica repair coverage, disk headroom, I/O budget, Cassandra version, and rollback**. Never run these just because a dashboard shows high tombstone histograms.

## 14. Redesigning Partitions: Time Bucketing and Bounded Queries

For event timelines, **time bucketing** prevents a single device from piling years of data into one partition.

### 14.1. Example V2 Partitioned by Day and Hour

~~~sql
-- Each (tenant_id,device_id,event_day,event_hour) tuple is one partition.
CREATE TABLE IF NOT EXISTS telemetry_diag.events_by_device_hour_v2 (
    tenant_id text,
    device_id text,
    event_day date,
    event_hour int,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY (
      (tenant_id,device_id,event_day,event_hour),
      event_time,event_id
    )
) WITH CLUSTERING ORDER BY (event_time DESC,event_id ASC);
~~~

Compute `event_day` and `event_hour` from **`event_time` in UTC** when partitioning by event time—never from the pod's local timezone. Producers, Java readers, replay/backfill jobs, and repair/reconciliation tools must all agree on bucket derivation. Partitioning by ingestion time is a **different model** that handles late events differently and changes event-time query behavior.

### 14.2. Size Buckets for p95/p99 Devices, Not Fleet Averages

At 25 events/second, 600 bytes/row:

~~~text
Per day  = 25 × 86,400 × 600 ≈ 1,296,000,000 bytes ≈ 1.21 GiB
Per hour = 25 ×  3,600 × 600 ≈    54,000,000 bytes ≈ 51.5 MiB
~~~

This estimates **logical bytes written**, excluding compression/SSTable overhead, live overlap, deletions, RF, or snapshots. If the busiest device emits **100 events/second**, one hour hits ~206 MiB (at 600B/event). Therefore:

1. Measure the **per-key event/second distribution**, not just the global mean.
2. Measure actual row bytes via profiling/sampling and inspect disk/SSTables.
3. Pick day/hour/15-minute buckets based on **partition byte budgets and query patterns**.
4. Account for growth, bursts, and late-data/backfills instead of assuming p99 equals mean traffic.
5. Benchmark p99/GC/disk/compaction with production-like TTLs and deletes.

**There is no mandatory "Cassandra limit = 50 MiB".** In this example, an hour bucket drastically shrinks partitions compared to multi-year partitions; choose the final bucket width from SLOs, capacity, and testing.

### 14.3. CQL Querying One Hour Instead of Full History

~~~sql
SELECT event_time,event_id,event_type
FROM telemetry_diag.events_by_device_hour_v2
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_day='2026-11-21'
  AND event_hour=8
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time < '2026-11-21T09:00:00Z'
LIMIT 100;
~~~

This query supplies the **full partition key** and a bounded clustering range. It shrinks scan scope and bytes transferred with narrow projections, though it **does not erase existing tombstones** in V1 or fix repair schedules.

### 14.4. When Even One Hour Is Too Large

For ultra-hot devices, add a **deterministic shard** to the partition key:

~~~sql
-- Example new variant adding shard_id; never ALTER v2 in-place.
PRIMARY KEY (
  (tenant_id,device_id,event_day,event_hour,shard_id),
  event_time,event_id
)
~~~

Compute the shard using a deterministic hash of **event ID or logical key**, e.g., `shard = stableHash(eventId) mod 8` (identical across all languages/clients). A producer retrying the same event ID must land on **the exact same shard** to avoid creating duplicate logical events across partitions.

**Trade-off:** reading all events in an hour requires **fanning out to up to eight shards** with bounded concurrency, merging/sorting by `(event_time, event_id)`, and enforcing a **global `LIMIT`**—Cassandra does not `ORDER BY` across shards. Changing 8 shards to 16 later breaks routing for historical data; version the table/mapping and migrate rather than altering the modulus over existing data.

## 15. Query-First Redesign: Clarify What Users Actually Ask

### 15.1. Recommended Tables by Access Pattern

| API Requirement | Suitable Partition / Projection | Risks to Control |
| --- | --- | --- |
| Latest 50 events for **one device in a day** | `events_by_device_day` with clustering time DESC, day bucket (or hour if needed). | If a hot device's day grows too large, shrink bucket; "latest" may span multiple hours. |
| Search within **a one-hour window** | `events_by_device_hour_v2` full key + time range. | Late events and UTC timezones. |
| All events for a **site** in one minute | Table/projection keyed by `site_id, minute` or a dedicated rollup. | Never scan `N` devices unboundedly. |
| Event counts by event type/day | Pre-aggregated counters/rollups (explicit retry semantics). | Never run full-table `COUNT(*)` for real-time dashboards. |
| Lookup by `event_id` | Lookup/projection table keyed by event ID if mandatory. | Dual-write/CDC/reconciliation; never use `ALLOW FILTERING`. |
| Arbitrary text payload filtering | Dedicated search/analytics engine or validated index. | Never treat Cassandra `ALLOW FILTERING` as full-text search. |

In wide-column modeling, **query-driven table design** embraces denormalization and multiple projections. However, "adding a table" means **synchronizing mutations, TTLs, DELETEs, and backfills**—it does not form a multi-table ACID transaction.

### 15.2. Balancing Bucket Size Against Read Fan-Out

Too large a bucket → huge partitions, read/compaction/tombstone pressure. Too small a bucket → timelines must touch many partitions, driving coordinator requests, latency, and concurrency. Balance using real workload math:

~~~text
target_partition_bytes =
  (peak_events_per_second_per_key)
  × (bucket_seconds)
  × (observed_bytes_per_event)

estimated_query_partitions =
  ceil(query_window_seconds / bucket_seconds)
  × shard_count
~~~

These formulas are **bounded estimates**: account for bursty arrivals, event-time skew, row-size variance, SSTable amplification, and UTC boundary off-by-one edges. If a query's partition count exceeds budget, reject it with a validation error or serve from a **projection/rollup** rather than unbounded fan-out.

### 15.3. Late Events and Key Changes

If a late event carries an event time from last month's bucket, writing it into an older time window can interfere with TWCS whole-SSTable expiration. If changing an event's time alters its **clustering key or partition**, Cassandra cannot update primary keys in place; use **INSERT new key + DELETE old key** with idempotent reconciliation—another source of tombstones or duplicates if migrations/repairs are unmanaged.

## 16. Java Driver 4.x: Preventing Unbounded Reads in the Application

An API must never accept a `deviceId` and run `SELECT *` across all history. The example below caps reads to **one UTC hour, 1–100 rows, and a narrow projection**, assuming Spring Boot manages a long-lived `CqlSession`.

~~~java
// EventWindowReader.java — Java 17, Driver 4.x.
package example.cassandra.troubleshooting;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class EventWindowReader {
    public record EventSummary(Instant at, UUID id, String type) {}

    private final CqlSession session;
    private final PreparedStatement query;

    public EventWindowReader(CqlSession session) {
        this.session = session;
        this.query = session.prepare(
            "SELECT event_time,event_id,event_type " +
            "FROM telemetry_diag.events_by_device_hour_v2 " +
            "WHERE tenant_id=? AND device_id=? " +
            "AND event_day=? AND event_hour=? " +
            "AND event_time>=? AND event_time<? LIMIT ?");
    }

    public List<EventSummary> fetchOneHour(
            String tenantId, String deviceId,
            Instant fromInclusive, Instant untilExclusive, int limit) {

        if (tenantId == null || tenantId.isBlank()
                || deviceId == null || deviceId.isBlank()) {
            throw new IllegalArgumentException("Partition key required");
        }
        if (fromInclusive == null || untilExclusive == null
                || !fromInclusive.isBefore(untilExclusive)) {
            throw new IllegalArgumentException("Invalid time window");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Limit outside [1,100]");
        }

        var utcStart = fromInclusive.atZone(ZoneOffset.UTC);
        LocalDate day = utcStart.toLocalDate();
        int hour = utcStart.getHour();
        Instant nextHour = utcStart.truncatedTo(
                java.time.temporal.ChronoUnit.HOURS)
            .plusHours(1)
            .toInstant();

        if (untilExclusive.isAfter(nextHour)) {
            throw new IllegalArgumentException(
                "Window crosses hour bucket; split with bounded fan-out");
        }

        BoundStatement statement = query.bind(
                tenantId, deviceId, day, hour,
                fromInclusive, untilExclusive, limit)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(Math.min(limit, 50))
            .setTimeout(Duration.ofSeconds(2));

        ResultSet result = session.execute(statement);
        List<EventSummary> output = new ArrayList<>();
        // CQL LIMIT remains the logical cap even across multiple driver pages.
        for (Row row : result) {
            output.add(new EventSummary(
                row.getInstant("event_time"),
                row.getUuid("event_id"),
                row.getString("event_type")));
        }
        return output;
    }
}
~~~

### 16.1. What Does This Example Protect Against?

- **No per-request session creation:** prepares statements once and reuses an injected/managed `CqlSession`.
- Reads strictly **one UTC-hour partition** and a range within that hour; never silently crosses hour boundaries.
- **Page size <= 50** bounds per-page memory/network frames (not an absolute byte cap); CQL `LIMIT <= 100` caps total rows.
- Projects **only three needed columns**, avoiding fetching and discarding multi-hundred-KiB `payload` blobs.
- Keeps `LOCAL_QUORUM` per consistency contract; the 2-second timeout is an **illustrative policy to benchmark**, not a tombstone cure.
- Multi-hour queries must split into **bounded buckets** with a global limit/merge and query deadlines—never fanning out into thousands of requests.

### 16.2. What Does It **Not** Protect Against?

- Does not stop a replica from scanning heavy tombstones **inside that hour bucket itself**.
- Does not replace tenant authorization: the service/filter must confirm the caller may read `tenantId`/`deviceId`, since table-level Cassandra RBAC does not enforce row-level tenant isolation.
- Does not turn results into an isolated snapshot across concurrent inserts, deletes, or TTLs.
- Does not magically handle `ReadTimeout` recovery; exceptions must be classified, metered, and retried within bounds only when safe.
- Does not guarantee total packet/response bytes stay below a hard ceiling; still measure payload schemas, projections, and ingress limits.

### 16.3. Never Raise Timeouts or Lower CL on Gut Instinct

A 2-second query budget may already be many times your target p99. Raising it to 20 seconds keeps threads, heap, and in-flight requests pinned longer, building queues and load amplification. **Timeouts are service-protection budgets**, not storage tuning. Every adjustment must measure **offered/achieved rate, p95/p99, in-flight counts, and replica metrics**—and never downgrade `LOCAL_QUORUM` just to dodge read costs.

## 17. Spring Data Cassandra: Repository Convenience Does Not Replace Query Design

### 17.1. Derived Methods Do Not Magically Create Indexes

~~~java
// ANTI-PATTERN thinking: declaring this Java method does NOT give
// Cassandra an efficient access path to find event_type across all partitions.
// List<EventEntity> findByEventType(String eventType);
~~~

If `event_type` is a regular column on a device/time-partitioned table, Cassandra cannot serve cheap queries by `event_type` merely because Spring Data supports derived method names. Broad `ALLOW FILTERING` is rarely production-safe.

### 17.2. Entity `null`s and Partial Updates

In object mapping, loading an entity missing some columns and calling `repository.save(entity)` can emit unintended mutations depending on version, converter, and null-handling rules—including deleting cells and creating tombstones. Instead of "read a 3-column DTO and `save()` the full entity", use:

- Explicit CQL `UPDATE` targeting **only the modified columns** with the full primary key.
- `UNSET` on bind markers when meaning "do not touch this column", verified for your driver/protocol version.
- Integration tests inspecting generated CQL and null/tombstone behavior for your pinned Spring Data patch.
- Optimistic locking via **`@Version`/conditional mutations** when concurrency requires it, rather than letting plain upserts overwrite stale state.

**`@Version` adds LWT/Paxos cost**, so never enable it on append-only events merely to work around a tombstone mapping bug. Concurrency control and tombstone generation are **orthogonal concerns**.

## 18. V1 → V2 Migration: You Cannot `ALTER PRIMARY KEY` and Hope Large Partitions Shrink

Moving from partition `(tenant_id, device_id)` to `(tenant_id, device_id, event_day, event_hour)` changes **token ownership, replica placement, and query routing**. Cassandra does not support altering an existing table's primary key structure via `ALTER TABLE` like adding a regular column.

### 18.1. Reversible Migration State Machine

~~~mermaid
flowchart LR
    A["V1 serving"] --> B["CREATE V2 + capacity"]
    B --> C["Dual-write/CDC captures future mutations"]
    C --> D["Checkpoint backfill by device/time range"]
    D --> E["Catch up late writes, TTL/deletes"]
    E --> F["Reconcile IDs/values/expiry"]
    F --> G["Shadow reads + V2 canary"]
    G --> H["Cut over reads/writes with rollback"]
    H --> I["Post retention/approval -> retire V1"]
~~~

### 18.2. Pitfalls That Shrink Tombstones While Corrupting Data

| Issue | Why It Is Dangerous | How to Verify |
| --- | --- | --- |
| Backfill copies TTL-capped rows as `INSERT`s with no TTL. | Data persists forever, violating retention/compliance. | Preserve expiry / remaining TTL policies; never reset lifetimes silently. |
| Computing `event_time` buckets in the host's local timezone. | Writes to wrong `event_day, event_hour`; queries miss rows. | UTC conversion tests around midnight and DST if input carries timezones. |
| Dual-write succeeds on one table and times out on the other. | V1/V2 drift and potential loss of late events. | Durable CDC/event log, idempotent retries, DLQ/reconciliation. |
| Failing to replay `DELETE`s onto exact V2 keys. | V2 keeps live rows deleted in V1; compliance risk. | Deletion ledger/CDC and point/row/range delete mapping. |
| Minting new UUIDs during retries or backfill. | Logical duplicates in V2; counts mismatch. | Stable full primary keys; reconcile exact ID sets. |
| Cutting over before V2 covers all queried buckets. | API returns missing events. | Shadow/canary queries across historical windows and late buckets. |
| Dropping V1 too early. | Loses rollback path and source-of-truth reconciliation. | Backups/retention checks, signed approval, zero remaining V1 clients. |

### 18.3. Never "Fix Partition Size" with Manual Bulk Deletes

Issuing millions of `DELETE`s against V1 creates even more tombstones without shrinking physical partitions immediately. Replace V1 cleanly via **versioned table migration and cutover**, retiring the old table per retention and rollback policies rather than running ad-hoc deletes mid-incident.

## 19. Hot Partitions and Skew: Timeouts Without Huge Partitions

Suppose a cluster stores one million partitions of only 5 MiB each, yet one `gateway-master` device receives 40% of all reads while most partitions sit idle. Token placement concentrates that load on the RF replicas owning `gateway-master`. **Adding more cluster nodes** will not split the load of **one hot key** across the cluster; RF fixes how many natural replicas serve that key.

### 19.1. How Skew Propagates

~~~mermaid
flowchart TD
    A["Fleet has many partition keys"] --> B["Most keys: low QPS"]
    A --> C["gateway-master: very high QPS"]
    C --> D["Token placement picks only RF natural replicas"]
    D --> E["CPU/disk/cache/queues saturate on those replicas"]
    E --> F["Read p99, timeouts, and retries spike"]
    B --> G["Other nodes may still have idle capacity"]
~~~

**Not every hotspot is Cassandra's fault:** a cache-miss storm, retry storm, or buggy client key can trigger artificial hotspots. Measure client QPS, coordinator distribution, per-node token load, and partition-level sampling.

### 19.2. Measure Distributions Rather Than Averages

| Observation | Hypothesis to Verify |
| --- | --- |
| 1% of keys drive 80% of read QPS. | May need caching, precomputation, single-flight coalescing, or a new projection. |
| 1% of keys hold 60% of live bytes. | Size buckets/shards/capacity around high-percentile keys. |
| A few nodes have high p99 while others are idle. | Token/replica skew or local node disk/GC trouble. |
| Hot key has few bytes yet high latency. | High concurrency, cache churn, read/write contention, or network/queues. |
| Huge partition yet reading only the latest 10 rows. | Actual query width, tombstone density, and `SSTablesPerRead` govern cost. |

Never blindly default to massive shard counts. If an endpoint needs all events for a device, `N` shards multiply every read by **`N`-way fan-out**. Establish **latency budgets, global limits, bounded concurrency, merge ordering, pagination, and backpressure** before sharding.

### 19.3. When Caching or Rollups Help

- **Latest settings / rarely changing summaries:** cache with explicit TTL/invalidation, or keep a dedicated `latest_event_by_device` table.
- **Counts / aggregates:** precompute by site/device/hour instead of reading raw events for live dashboards.
- **Raw event timelines:** query bounded buckets paged by clustering key; caches can help if invalidation handles late writes and deletes.
- **Compliance deletions:** must purge/invalidate caches and projections so UIs never serve "deleted" data from Redis/CDN.

Caching only shifts load; **it never fixes tombstone safety, repair cadence, or runaway partition growth on disk**.

## 20. Replication, Consistency, and Repair When Diagnosing a Slow Read

### 20.1. RF=3 and `LOCAL_QUORUM`

~~~text
Keyspace: NetworkTopologyStrategy {'dc1': 3}
Full natural replicas: R1, R2, R3
Read LOCAL_QUORUM: needs 2 responses from full replicas in dc1
Read LOCAL_ONE: needs only 1 response in dc1
Read ALL: needs all 3 full replicas
~~~

If R2 holds many SSTables/tombstones or suffers heavy disk/GC stalls, reads involving R2 slow down. However, **`LOCAL_QUORUM` does not blindly mean "read from the two fastest replicas regardless of correctness"**; read paths, replica selection, digest vs. full-data requests, and speculative retries depend on version and config. Never guess coordinator/replica behavior solely from contact points.

### 20.2. Why Switching `LOCAL_QUORUM` to `LOCAL_ONE` Is Not a Fix

- Waiting on one replica instead of two **alters the consistency contract**; an unrepaired replica can serve stale data.
- Tombstone scans on **the selected replica** can still be massive, so `LOCAL_ONE` still times out.
- It does not relieve hot-key load: the same small set of natural replicas still handles the key.
- If the API relies on `LOCAL_QUORUM` for read-after-write accuracy, downgrading breaks business correctness.

Preserve the approved CL; any proposed change needs correctness analysis, quorum math, multi-DC review, and canary/rollback plans.

### 20.3. Read Repair Is Not Full Anti-Entropy Repair

A quorum read can repair inconsistencies spotted **within that read's scope**, depending on Cassandra version and table config. It does not scan cold keys or ensure a formerly down replica received every delete and TTL. **Anti-entropy repair** compares replicas by token range via Merkle trees and streaming; running it on schedule within scope prevents divergence and zombie data.

### 20.4. Multi-DC Complicates Diagnostics

With `dc1:3, dc2:3`, `LOCAL_QUORUM` in `dc1` needs only **two full replicas in `dc1`**. If the remote DC lags, UIs reading in `dc2` observe discrepancies; hint delivery, repair, and DC-local settings matter. A **local-only repair** does not automatically reconcile cross-DC divergence unless repair scope spans both DCs.

**Never** cite "reads look right in `dc1`" as proof that tombstones in `dc2` are safe after a remote replica was down for an extended period.

## 21. Short-Term Incident Mitigation: Favor Reversible Changes

### 21.1. Lower-Risk Mitigations

| Action | Why It Helps | Must Verify |
| --- | --- | --- |
| Tighten the endpoint's time window. | Shrinks clustering rows/ranges scanned. | Does not drop user-required data; pagination contract holds. |
| Project only needed columns; drop large `payload`. | Cuts network, deserialization, and heap pressure. | DTO/API compatibility; tombstone scans may persist. |
| Cap `LIMIT`, page size, bytes, and request rate. | Reduces full-response and in-flight footprint. | Small page size does not eliminate internal tombstone scans. |
| Bound concurrency and enforce admission control. | Prevents overload and retry storms on hot replicas. | Never drop mandatory writes without durable queueing/ACKs. |
| Pause or throttle batch reports and backfills. | Frees disk, CPU, compaction, and network headroom. | Resumable checkpoints and business SLAs respected. |
| Targeted caching/projections for hot endpoints. | Cuts repeated hot reads. | Invalidation, consistency, tenant security, and TTLs. |
| Shift traffic onto a canary-validated V2 schema. | Eliminates V1 large-partition scans. | V2 reconciliation, late writes, and deletes verified. |

### 21.2. Actions Requiring Explicit Approval and Separate Measurement

- **Scaling node count:** helps only if hotspots or capacity can redistribute—does not split one fixed partition key; topology changes add streaming, cleanup, and repair load.
- **Raising timeouts:** may temporarily mask errors while swelling in-flight queues; watch p99, queues, and goodput.
- **Changing compaction strategy:** requires benchmarking; can trigger large compaction backlogs needing disk headroom.
- **Running repair:** essential for diverged data, yet not an instant p99 tombstone cure; consumes CPU, disk, and network and must be scheduled.
- **Changing `gc_grace_seconds` or tombstone thresholds:** carries data-safety/correctness risks; never adjust impulsively mid-incident.

### 21.3. Stop Criteria

Example defined before testing:

~~~text
STOP / ROLLBACK IF:
  HTTP errors > approved budget during canary window
  Cassandra read p99 > baseline×2 for a sustained interval
  pending tasks / dropped messages climb steadily
  free disk drops below safety headroom
  retry attempts/s exceed global budget
  GC pauses / OOM risk breach operational thresholds
  ACKed events go missing or unexpected deletes/resurrections appear
~~~

These thresholds are **methodological examples**, not universal constants across deployments. Document baselines, traffic shapes, observation windows, and escalation owners before starting any canary.

## 22. Java Service Error Handling: Never Turn Timeouts into Empty Results

An anti-pattern:

~~~java
// ANTI-PATTERN — illustrative snippet:
try {
    return reader.fetchOneHour(tenant, device, from, until, 100);
} catch (Exception ignored) {
    return List.of(); // Returns "no events" when DB timed out.
}
~~~

When Cassandra returns `ReadTimeout`, returning an empty list misleads callers into thinking zero events occurred—potentially triggering duplicate replays or corrupting reports. Classify cleanly:

| Error | Appropriate API Behavior | Notes |
| --- | --- | --- |
| `ReadTimeout` / driver request timeout | Return transient error (e.g., 503/504 per contract), with bounded retries if safe. | Never return `404` or `[]` as a successful read. |
| `Unavailable` | Report service/resource temporarily unable to meet CL. | Check replica availability; never auto-downgrade CL. |
| Tombstone-overwhelming / invalid query | Flag query/data-shape error; alert ops and protect endpoint. | Never rapidly retry the exact same failing partition/range indefinitely. |
| Invalid range input | Return 400/422 per contract before sending CQL. | Enforce `from < until`, bucket count caps, and page-size bounds. |
| `Unauthorized` / tenant mismatch | Return 403 or 404 per security policy. | Never fall back to an admin role. |
| Mapping / codec / schema drift | Return 500 or managed failure mode. | Fix dependencies/schema; never blame tombstones by default. |

### 22.1. Driver Retry Policy and Speculative Execution

Java Driver may retry operations marked retryable/idempotent per config, or fire speculative executions across coordinators if enabled. Both can **pile extra load onto the exact natural replicas of a hot partition**. When the root cause is a tombstone-heavy read, trying another coordinator does not make tombstones vanish.

Enforce **global retry budgets, deadlines, driver throttler/in-flight caps, and per-endpoint concurrency**, and track retry attempts/sec. Never monitor only HTTP requests—one HTTP request can emit multiple CQL attempts.

### 22.2. Client Metric Labels Must Never Contain Raw Keys

~~~text
metrics labels:
  query_name     = events_recent_by_device_hour
  outcome        = success | read_timeout | unavailable | invalid_range
  local_dc       = dc1
  table          = events_by_device_hour_v2
  api_route      = /events

NEVER attach:
  tenant_id, device_id, event_id, raw CQL literals, API tokens, payloads
~~~

To investigate hot partitions, use **access-controlled sample logs**, policy-approved keyed hashes/pseudonyms, short log TTLs, and ticket correlation. High-cardinality partition keys overwhelm metrics backends and leak sensitive identifiers.

## 23. Integration Tests: Tombstones, `null`/`UNSET`, and Bounded Reads

### 23.1. Tests Requiring Real Cassandra

Unit tests with mocked repositories verify the service rejects wide windows, yet **cannot prove** TTL/deletes write deletion markers, queries scan tombstones, or compaction/repair behaves properly. Use a Cassandra lab or Testcontainers for CQL and Java Driver behavior—noting that a **single-node RF1** cluster cannot prove RF3 quorum, repair, or zombie resurrection.

### 23.2. Fixture with Tombstones and a Live-Row Probe

~~~sql
-- Run only in an isolated test keyspace; lab RF must match node count.
CREATE KEYSPACE IF NOT EXISTS diag_test
WITH replication = {'class':'NetworkTopologyStrategy','datacenter1':1};

CREATE TABLE IF NOT EXISTS diag_test.events (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id,event_day),event_time,event_id)
) WITH CLUSTERING ORDER BY (event_time DESC,event_id ASC);
~~~

A Java test can:

~~~text
1. Seed one unique test partition key with 1,000 rows.
2. Delete 900 rows via DELETE with full clustering key, or let TTL expire.
3. SELECT the window spanning deleted rows + a few live rows, LIMIT 20.
4. Record elapsed time, ExecutionInfo warnings, and assert exact live row IDs.
5. SELECT a small window holding only live rows as a control.
6. Observe version-specific metrics/traces (do not assert exact tombstone counts
   across every build or compaction schedule).
7. Clean up per test lifecycle; never TRUNCATE a shared test table.
~~~

**Reliable assertions:** after ACKed `DELETE` and reading at matching CL, deleted rows are absent from live results; partitions never bleed across keys; query windows respect `LIMIT`. **Unreliable assertion:** asserting a tombstone warning fires after exactly 900 deletes across every Cassandra version and compaction state; use dedicated performance tests with pinned configs if verifying guardrail thresholds.

### 23.3. Testing `NULL` vs. `UNSET`

~~~text
Seed row:
  payload="A", event_type="ALERT"

UPDATE only event_type="WARN":
  - path A: SET payload=null (CQL deletion)
  - path B: bind payload UNSET (leave column untouched, where supported)

SELECT full PK:
  path A: payload has no logical value
  path B: payload remains "A"

Inspect generated CQL, mapper behavior, storage versions, and warnings/metrics.
~~~

This is why **Spring Data partial entity updates** require integration tests against the real dependency graph rather than mocked `save()` calls.

### 23.4. Testing Guardrails at the HTTP Layer

| Input | Expected Behavior |
| --- | --- |
| Missing `tenantId`/`deviceId`. | Reject before building any statement. |
| `until <= from`. | Reject invalid time range. |
| Query spans two hours when service supports one hour. | Reject or split into two budgeted buckets without dropping UTC boundary events. |
| `limit=0` or `limit>100`. | Reject or clamp per explicit contract; never permit unbounded `LIMIT`. |
| Client cancels request. | Stop fetching further pages; release resources. |
| Cassandra read timeout. | Return explicit failure, never a fabricated `[]`. |
| Tenant B requests Tenant A's key. | Authorization denies before querying cross-tenant data. |
| Rows carry huge payloads. | Narrow-projection endpoint skips deserializing payload; benchmark bytes. |

## 24. Load Testing: Separating Tombstone Density from Partition Size

Instead of testing "1 million generic rows", construct a **two-factor matrix**:

| Dataset | Partition Bytes/Rows | Tombstone Density | What to Observe |
| --- | --- | --- | --- |
| **S1** | Small. | Low. | Baseline latency, CPU, and network. |
| **S2** | Small. | High. | Pure tombstone scan overhead and threshold warnings. |
| **S3** | Large, many live rows. | Low. | Read amplification / wide range scans, disk, heap, and GC. |
| **S4** | Large. | High. | Compounded impact on p95/p99 and timeouts. |
| **S5** | Smaller V2 buckets. | Same retention as S4. | Proves reduced read work from proper key/time design. |
| **S6** | Modest bytes yet heavy QPS on one key. | Low or moderate. | Hot-partition queueing; do not confuse with storage size. |

### 24.1. Keeping Workloads Comparable

~~~text
Fixed per experiment:
  Cassandra version/topology/RF/CL
  Java Driver/timeouts/page size/retry policy
  CQL query shape + payload projection
  Read/write ratio and request arrival pattern
  TTL/delete policy, compaction strategy, data age distribution

Record:
  offered RPS, achieved RPS, timed-out/rejected, in-flight
  p50/p95/p99, bytes returned, pages fetched
  tombstone/live scanned histograms, SSTablesPerRead
  CPU/GC/disk await/network, pending compactions
  accurate result IDs/values, not just counts
~~~

**Closed-loop** load tests throttle offered requests whenever latency climbs, making degradation look artificially mild. For capacity analysis, use open-loop arrival rates with **bounded queues/in-flight**, deadlines, and backpressure, avoiding **coordinated omission** in histograms—while ensuring the load generator does not accidentally crush shared test clusters.

### 24.2. Define Pass/Fail Criteria Upfront

For example, V2 passes as an improvement under **identical business/query correctness** and workload when:

- p95/p99, server tombstones scanned, and `SSTablesPerRead` drop or meet agreed targets.
- No unexpected explosion in **global CQL requests** from multi-bucket/shard fan-out.
- Heap/GC and disk/network stay stable with non-growing compaction backlogs.
- TTL, deletes, replay idempotency, and event ID sets remain 100% accurate.
- Read consistency/CL and tenant isolation remain intact—never "improve performance" by weakening correctness contracts.

**Never treat illustrative benchmark numbers as SLAs.** Your application's real workload, retention, RF/DC, and SLOs dictate the thresholds.

## 25. Case Study A: Dense TTLs and Range Deletes Cause 20-Row Pages to Time Out

### 25.1. Simulated Context

A V1 telemetry table partitions by `device_id` with a 14-day TTL. Following an audit event, the app team runs a scheduled job deleting older `event_time` ranges while some clients still replay events from past days. `GET /devices/{id}/events?limit=20` sees p99 spike sharply.

| Time | Observation | Hypothesis to Verify |
| --- | --- | --- |
| Day 1 | One device writes 20 events/s; partition grows steadily. | Unbucketed history lands in a single token key. |
| Day 15 | Waves of cells hit TTL expiry. | Deleted/expired cells rise; SSTables may not drop yet. |
| Day 16 | Range `DELETE` job runs multiple passes over old intervals. | Likely writes overlapping range tombstones. |
| Day 17 | `LIMIT 20` takes >2 seconds on certain devices. | Likely scanning tombstones ahead of live rows. |
| Incident | Server tombstone scan warnings, high `SSTablesPerRead`. | Measure exact query/key/time window rather than trusting global warnings alone. |

**Numbers and timelines are simulated**, not live production measurements or version-independent guarantees.

### 25.2. Investigation Path

1. Collect `query_name`, redacted full partition key, CL, chosen time window, timeout, p99, and warnings from sample requests.
2. Inspect `TombstoneScannedHistogram`, `LiveScannedHistogram`, and `SSTablesPerReadHistogram` on the natural replicas.
3. Align schedules of **TTL expirations, batch DELETEs, mapper null writes, repairs, and compactions**.
4. Run a **bounded one-hour query** and a **control query on a low-delete day** in staging or authorized production samples.
5. Check TWCS/STCS/LCS and SSTable state: are late/out-of-order writes blocking expired SSTables from dropping?
6. Verify **repair cadence and `gc_grace` safety** before proposing any purge.

### 25.3. Mitigation and Root Fix

- Throttle or pause non-critical **batch DELETE** jobs while preserving checkpoints; never halt compliance-mandated deletions without an approved alternative.
- Restrict the API to **UTC buckets/time windows**, project only needed columns, and limit concurrent reads per key.
- Design V2 with **hour/day buckets sized to p99 ingestion**, uniform TTL retention, and partition-aligned queries.
- Re-evaluate **TTL vs. range DELETE**: avoid overlapping deletion mechanisms unnecessarily while honoring retention rules.
- If TWCS fits an append-only stream, benchmark with real late-write/delete patterns; never switch strategies blindly.
- Post-cutover, reconcile event IDs, live/deleted states, TTL expiries, and repair state—do not declare victory merely because warnings subsided.

**Avoid:** raising `tombstone_failure_threshold` to "silence errors", forcing cluster-wide major compaction, or setting `gc_grace_seconds=0` before replica convergence is guaranteed.

## 26. Case Study B: Large Partition with Few Tombstones; Case C: Mapper `null`s

### 26.1. Case B — Hot 30 GiB Gateway, Unbounded Time Range

Suppose one gateway emits 10,000 events/minute, all stored in **one partition per device**. The UI shows "latest 50 events", yet an export feature runs an unbounded `SELECT * WHERE device_id=?`, streaming every payload through Java.

**Symptoms:**

- High `MaxPartitionSize` and SSTable partition size estimates.
- Heavy client bytes, JSON serialization, heap/GC, plus server disk/network load.
- Tombstone histograms stay modest; latency tracks **rows/bytes and page count**.
- The gateway key absorbs far higher QPS than typical devices.

**Differential diagnosis:** run two control checks at identical CL on an appropriate test dataset/cluster: (a) narrow projection with a 1-hour clustering range, (b) full projection with a wide range. If (a) is fast while (b) is slow, **query width/bytes** is the bottleneck—still verify replica SSTables/queues rather than blaming tombstones.

**Fix:** migrate to **hour-bucketed** per-device tables, use narrow projections for timelines, enforce checkpointed byte-budgeted exports or an analytics pipeline, and shard/cache/rollup if an hour bucket remains hot. Never assume adding 10 Cassandra nodes splits an existing partition across 10 token locations.

### 26.2. Case C — After Spring Data Deploy, Tombstones Spike While TTL Is Unchanged

An endpoint loads a partial entity with few columns, updates one field, and calls `save(entity)`. A mapper upgrade changed its `null` handling, writing `payload = null` on every save. The table uses no TTL, yet tombstone scans climb.

**Symptoms:** tombstone warnings start right after deploy; CQL writes and explicit row deletes did not rise correspondingly; fields unexpectedly vanish without business delete requests.

**Verification:** review redacted **generated CQL**, distinguish `UNSET` vs. `NULL`, check resolved Spring Data/Driver versions, and run an integration test: seed row A, update field B, assert A remains intact.

**Fix:** use explicit `UPDATE ... SET fieldB=? WHERE full_key` or a verified partial-update policy ensuring omitted fields never emit `null` deletions. Reconcile corrupted rows from external sources of truth—code fixes alone do not restore already-tombstoned values.

### 26.3. Why Separate the Three Case Studies?

| Case | Prominent Evidence | Foundational Fix |
| --- | --- | --- |
| A — TTL + DELETE | High tombstones scanned, overlapping retention/deletes. | Retention policy + bucketing/compaction/repair. |
| B — Large/hot partition | Huge partition/bytes/QPS, tombstones may be low. | Query-first schema, bucketing/sharding, bounded exports. |
| C — Mapper `null`s | Sudden deletion markers right after deploy. | Generated CQL, mapping/`UNSET`, update-semantics tests. |

Applying one generic "raise timeouts and compact" action leaves all three root causes **unresolved**.

## 27. Incident Runbook: From Detection to Postmortem

### 27.1. Phase 0 — Confirm Impact and Change Authority

~~~text
Incident ID:
Environment / cluster / DC:
Start UTC:
Affected API / query_name / table:
RF and requested CL:
P95/P99 / throughput / errors vs baseline:
Affected tenant/device scope (redacted):
Recent deployment / TTL/delete/backfill/repair changes:
Incident commander / DB operator / rollback owner:
~~~

Never fire off maintenance commands just because dashboards turned red. Check for **Down nodes, multi-DC lag**, backup/repair activity, and data-safety constraints first.

### 27.2. Phase 1 — Controlled Sampling

1. Pick **3–5 sampled slow queries** with `query_name`, CL, time window, result row counts, and warning/timeout classes.
2. Check logs/metrics on **the natural replicas** of affected partitions, not only the coordinator.
3. Capture `tablestats`, `tablehistograms`, `compactionstats`, `tpstats`, `gcstats`, and disk/CPU/RTT.
4. Compare tombstone-scanned vs. live-scanned trends, partition bytes/rows/`SSTablesPerRead`, and hot-key QPS.
5. Audit TTLs, recent DELETE ranges, mapper null writes, schema/query changes, and last repair coverage.
6. Classify as **tombstone-heavy**, **oversized**, **hot-key**, or **other overload**—recognizing multiple causes can coexist.

### 27.3. Phase 2 — Safe Load Shedding

- Pause or throttle non-essential backfills, exports, and crawlers using checkpoints.
- Enforce bounded request ranges and bucket counts; return clear validation errors on oversized queries.
- Switch endpoints to **narrow projections**, dropping unused `payload` bytes.
- Cap in-flight requests/retries with global deadlines and per-tenant/device rate limits where warranted.
- Never alter consistency/retention contracts or delete data without approval.
- If a node is Down, resolve **availability/recovery** in parallel—tombstones and replica lag are separate dimensions.

### 27.4. Phase 3 — Tested Root-Cause Fixes

| Finding | Proposed Change | Pre-Canary Prerequisites |
| --- | --- | --- |
| Per-device partition too large. | V2 bucketed by day/hour + optional shard. | Schema, dual-write/CDC, TTL/delete replay, reconciliation. |
| Unnecessarily wide query reads. | Clustering range + limit + narrow projection. | Verify request semantics; regression-test paging and buckets. |
| Mapper emits `null` deletions. | Field-specific `UPDATE` / `UNSET` policy. | Integration test `null` vs. `UNSET`; zero silent data loss. |
| TTL/delete overlap + tombstone scans. | Align lifecycle/retention/compaction for append-only. | Test expired SSTable drops, out-of-order writes, repair safety. |
| Compaction/disk backlog. | Capacity/rate/throttling/strategy tuning. | Disk headroom, version check, load test, rollback/observability. |
| Stale replica / long outage. | Anti-entropy / restore plan. | Token/DC coverage, `gc_grace`, valid sources, operator sign-off. |

### 27.5. Phase 4 — Verify Recovery

**Success** requires at least:

1. API p95/p99, achieved throughput, timeouts/errors/retries, and queues/in-flight meet approved targets under representative load.
2. Tombstone warnings/scan distributions and query bytes/partition ranges **improve for the identified cause**—not merely "warnings stopped logging".
3. Data correctness: expected **event IDs, values, and live vs. deleted states** reconciled on representative partitions/buckets.
4. Repair/retention/compaction policies introduce no zombie data or bad expirations; CPU/GC/disk/compaction show no new risks.
5. Client/API tenant isolation, pagination, global ordering, UTC buckets, and rollback paths remain intact.

Never claim "completely fixed" after one green `SELECT LIMIT 20` while workload p99 stays high or missing IDs remain unexplained.

### 27.6. Phase 5 — Postmortem

Record explicitly:

~~~text
Root cause:     confirmed tombstone / large partition / hotspot / other
Evidence:       query + metrics + logs + timeline (redacted)
Immediate fix:  bounded query / rate limit / load isolation / ...
Permanent fix:  schema, retention, compaction, repair cadence, API contract
Correctness:    ID/value + TTL/delete reconciliation
Performance:    p95/p99 before/after at comparable offered load
Rollback:       artifact/schema/feature-flag path + stop criteria
Prevention:     monitors/alerts/tests/deployment checklist
Owner and due:  ...
~~~

## 28. Anti-Patterns to Spot Immediately

| Anti-Pattern | Consequence | Better Alternative |
| --- | --- | --- |
| "`LIMIT 20` means the replica reads exactly 20 physical cells." | Can still scan huge SSTables/deletion markers before live rows. | Measure tombstones/live scanned, clustering range, bytes, and server latency. |
| "All read timeouts are caused by tombstones." | Ignores partition size, hot QPS, GC, disk, network, coordinator. | Classify cause from metrics, tracing, and workload. |
| "Partition size = total keyspace size divided by partition count." | Averages hide heavy tails and skew. | Measure p95/p99/max sizes and per-key ingestion distribution. |
| "Adding nodes splits one giant partition across all nodes." | One key hashes to one token and RF replica set. | Change partition key/bucketing/sharding; scale-out helps distributable loads. |
| "Just switch STCS to TWCS and all tombstones vanish." | Late writes/deletes/overlap block purges; partition key unchanged. | Benchmark real workload/retention; redesign around queries. |
| "Once TTL expires, SSTables vanish immediately." | Ignores grace, overlap, compaction, and repair. | Separate logical TTL expiry from physical reclamation. |
| "Set `gc_grace_seconds=0` to purge tombstones." | Causes zombie data when replicas miss deletes. | Maintain repair cadence, grace safety, and retention plans. |
| "Major compaction safely wipes every marker." | Heavy I/O; no purge guarantee; risks data safety if misapplied. | Compaction policy backed by headroom and repair evidence. |
| "Set `tombstone_failure_threshold` huge as the fix." | Reads keep burning resources, widening blast radius and p99. | Fix queries, TTLs, deletes, and data model. |
| "Run full-table `COUNT(*)` to find large partitions." | Heavy scan worsens an active incident. | Use metrics, ingestion ledgers, and bounded partition probes. |
| "Use `ALLOW FILTERING` to fetch all events by status." | Unpredictable wide scans. | Query-driven projection/table or benchmarked index. |
| "`SELECT *` then filter payloads in Java." | Wastes bytes, heap, and network. | Narrow CQL projections, DTOs, or summary tables. |
| "One partition per device for all history is natural." | Long-lived devices grow giant partitions. | Day/hour buckets sized to measured peaks. |
| "Sharding into 256 partitions is always good." | Massive 256-way fan-out/merge overhead per read. | Pick shard counts from QPS/bytes and bounded queries. |
| "Change modulus N in `hash(eventId)%N` in place." | Breaks routing for older writes; duplicates/missing data. | Use V2 schema/versioned migration and stable hashing. |
| "Backfill TTL rows as plain `INSERT`s without TTL." | Extends retention indefinitely; compliance breach. | Preserve exact expiry / remaining TTL semantics. |
| "Wipe V1 history with millions of `DELETE`s to free disk." | Generates floods of tombstones without instant reclamation. | Migrate/cut over cleanly, then retire the old table safely. |
| "Partial entity save with null fields is a no-op." | Often emits cell deletion markers. | Inspect generated CQL; use `UNSET` and field-specific updates. |
| "`LOCAL_ONE` always fixes read timeouts." | Risks stale reads and still hits tombstone scans. | Keep CL contract; fix root cause. |
| "`LOCAL_QUORUM` proves every replica converged." | Third replica may lag behind. | Check repair, hints, and replica-level validation. |
| "If `nodetool status` is `UN`, tombstones are safe." | Membership does not prove deletes propagated. | Track repair coverage, `gc_grace`, and deletion ledgers. |
| "Read timeout = device has zero events." | API returns false empty/404 responses. | Classify transient failure, bounded retries, preserve correctness. |
| "Infinite retries make slow queries succeed." | Amplifies load on hot replicas. | Enforce deadlines, rate/admission limits, and query redesign. |
| "Mock repository unit tests prove no tombstones are created." | Never exercises real CQL, storage, or TTL behavior. | Run integration tests on target Cassandra version. |
| "Make p99 charts pretty by dropping offered load silently." | Invalid benchmark comparison. | Report offered/achieved RPS, errors, GC, and identical query shape. |
| "Run compaction, repair, and schema migration simultaneously." | Masks causes, saturates I/O, complicates rollbacks. | Stage one layer at a time with canaries and validation. |

## 29. Self-Check Exercises with Answers

**Ex 1.** A `SELECT ... LIMIT 20` takes 3 seconds and the server warns it scanned 100,000 tombstones. Why didn't `LIMIT 20` save it?

**Answer:** `LIMIT` caps **logical returned rows**, not the deletion markers or SSTable versions scanned to locate 20 live rows. Narrow the query scope, inspect TTL/delete patterns, compaction, and data model.

**Ex 2.** Does `ReadTimeout` always mean excessive tombstones?

**Answer:** **No.** Down replicas, disk/GC/queues, networking, hot partitions, large payloads, or wide query ranges all cause timeouts. Classify using warnings, histograms, traces, and resource metrics.

**Ex 3.** What is the difference between a **large partition** and a **hot partition**?

**Answer:** A large partition involves **bytes/rows under one full partition key**; a hot partition involves **request frequency/concurrency** hitting that key. A tiny few-MiB key can be scorching hot, while a huge partition may get little QPS.

**Ex 4.** Given `PRIMARY KEY ((tenant_id,device_id),event_time,event_id)`, what determines the token?

**Answer:** The entire **composite partition key `(tenant_id, device_id)`**. `event_time` and `event_id` only order and identify rows within the partition; they do not generate new tokens.

**Ex 5.** A device emits 25 events/s at 600 bytes/event. Roughly how many logical bytes per day?

**Answer:** `25 × 86,400 × 600 = 1,296,000,000 bytes ≈ 1.21 GiB`, excluding compression, replication, and storage overhead.

**Ex 6.** Switching to 1-hour buckets at 25 events/s × 600B/event gives roughly how much per hour?

**Answer:** `25 × 3,600 × 600 = 54,000,000 bytes ≈ 51.5 MiB`. This is an estimate; measure peak rates and p99 partition size.

**Ex 7.** Why can a table with only 100 partitions cause worse incidents than one with 1 million partitions?

**Answer:** If each of those 100 keys holds massive rows/bytes or absorbs extreme QPS, reads, compaction, and hotspots become severe. **Total partition count** never replaces per-key size and hotness distributions.

**Ex 8.** Does `UPDATE ... SET payload = null` carry the same semantics as omitting `payload`?

**Answer:** **Not by default.** `NULL` in CQL typically creates a deletion/tombstone, whereas `UNSET` (when supported) leaves the column untouched. Verify how your mapper/driver binds values.

**Ex 9.** What happens when a job `DELETE`s a wide clustering range?

**Answer:** Cassandra writes a **range tombstone** covering the deleted span; logical deletion does not immediately erase physical data. Subsequent reads and compactions must process that marker.

**Ex 10.** Why does `gc_grace_seconds` exist?

**Answer:** It retains deletion markers long enough for replicas that missed a delete to synchronize. Purging tombstones early while an offline replica still holds live rows causes **zombie data**.

**Ex 11.** Should you set `gc_grace_seconds=0` solely because disks are nearly full?

**Answer:** **No.** It compromises correctness/repair and does not guarantee instant disk reclamation. Address compaction, overlap, disk headroom, repair cadence, and retention policies.

**Ex 12.** If a row has a 7-day TTL, is its SSTable guaranteed to vanish on day 7?

**Answer:** **No.** TTL expires cells logically per write semantics; physical cleanup waits for compaction, overlap resolution, grace, and replica state.

**Ex 13.** An event has `event_time` from a year ago yet is inserted today with `USING TTL 604800`. Does TTL count from `event_time` or write time?

**Answer:** Normally from Cassandra's **write-time semantics**, not `event_time`. Backfills and late events therefore require explicit expiry handling.

**Ex 14.** Why is keyspace-wide `COUNT(*)` bad for investigating large partitions during an incident?

**Answer:** It runs an expensive scan across a stressed cluster without quickly pinpointing which key is the outlier. Use table metrics, ingestion ledgers, and bounded partition-scoped probes.

**Ex 15.** What does `TombstoneScannedHistogram` measure?

**Answer:** The **distribution of tombstones scanned across table reads** (per version/instrumentation)—not the total count of tombstones sitting on disk.

**Ex 16.** If `SSTablesPerReadHistogram` and disk await rise together, are tombstones definitely the sole cause?

**Answer:** **No.** Read amplification from many SSTables, lagging compaction, or wide reads can spike even with few tombstones. Cross-check live vs. tombstone scans, query ranges, and storage metrics.

**Ex 17.** When `nodetool status` shows all three replicas `UN`, have deletes definitely converged?

**Answer:** **Not yet.** Membership does not prove every tombstone reached every replica. Check best-effort hints and anti-entropy repair/validation across tokens, DCs, and retention windows.

**Ex 18.** Does changing `LOCAL_QUORUM` to `LOCAL_ONE` fix tombstone-heavy reads at the root?

**Answer:** **No.** The queried replica still scans tombstones, while your consistency contract weakens and risks stale reads. Fix queries, retention, or storage—never downgrade CL carelessly.

**Ex 19.** When is TWCS most suitable?

**Answer:** Workloads that are **mostly append-only time-series in time order with uniform TTLs** benefit from time windows and whole-SSTable expiration when safe. Evaluate late/out-of-order writes, updates, and cross-window deletes carefully, as they hinder cleanup.

**Ex 20.** How do STCS and LCS differ in focus?

**Answer:** STCS groups SSTables by size for write-heavy workloads; LCS organizes SSTables into levels to bound SSTables per read at the cost of higher write/compaction amplification. Neither fixes a bad partition key.

**Ex 21.** If `events_by_device_hour_v2` still hits 2 GiB partitions for an ultra-hot device, what next?

**Answer:** Measure p99 event rate and row bytes; shrink the bucket window or add **deterministic sharding** with bounded shard count/fan-out, then benchmark query latency, merges, and global limits—never raise shard counts blindly.

**Ex 22.** What goes wrong if you hash `shard_id` from a fresh UUID on every retry?

**Answer:** The same logical event can route to **different partitions/keys**, creating duplicates. Producers must keep event IDs and full primary keys deterministic across retries.

**Ex 23.** Why does bumping shards from 8 to 16 by editing `hash(eventId)%N` in place hide older data from queries?

**Answer:** Older rows were written under `N=8` routing, while new readers look up partitions computed with `N=16`. Use versioned routing/tables with backfill and cutover.

**Ex 24.** An API needs only `event_time, event_type` yet fetches 200 KiB `payload` blobs per row. First fix?

**Answer:** Switch to a **narrow column projection**/DTO, cap row/byte budgets, and benchmark at identical CL/query. If server reads still scan heavy tombstones, resolve the storage issue separately.

**Ex 25.** During schema migration, backfill accidentally `INSERT`s TTL-capped rows without any TTL. What is the risk?

**Answer:** **Extending retention indefinitely**, risking compliance violations. Migrations must preserve exact expiry, remaining TTL, and deletions with reconciliation.

**Ex 26.** An app catches `ReadTimeout` and returns `[]`. What is wrong?

**Answer:** Service failures get disguised as "zero events", corrupting reports and caller retry logic. Return transient errors per contract, emit logs/metrics, and perform bounded retries only when safe.

**Ex 27.** Why does blindly retrying 1 request into 5 CQL attempts worsen a hot partition?

**Answer:** Retries keep hammering the exact same natural replicas and scanning the same SSTables/tombstones, amplifying CPU, disk, and queue saturation. Enforce deadlines, retry budgets, admission control, and query/model fixes.

**Ex 28.** Do `nodetool toppartitions` and `MaxPartitionSize` measure the same thing?

**Answer:** **No.** `toppartitions` observes keys **hot by activity** within a window/version; partition-size metrics estimate **on-disk bytes/rows**. A hot key need not be huge.

**Ex 29.** An integration test deletes 900/1,000 rows and asserts a tombstone warning threshold must appear. Is that reliable?

**Answer:** **Not a portable assertion.** Warnings depend on query shape, thresholds, live/tombstone cells scanned, compaction timing, and version. Assert logical deletion correctness; measure warnings/histograms in dedicated performance tests with pinned configs.

**Ex 30.** If p99 drops after raising the client timeout, is the root cause fixed?

**Answer:** **Not established.** Raising timeouts only gives requests longer to finish; in-flight queues may swell while correctness and tombstone scans stay unchanged. Measure true p99, goodput, bytes, server scans, errors, and node resources at equal offered load.

## 30. Safe Diagnosis and Rollout Checklist

~~~text
TRIAGE / SCOPE
[ ] Separated tombstone-heavy, large partition, hot partition, and global overload.
[ ] Recorded query_name, CQL shape, CL, RF/DC, UTC window, LIMIT/page size.
[ ] Classified ReadTimeout, Unavailable, tombstone failure, driver timeout.
[ ] Captured offered vs. achieved QPS, p95/p99, retries, queues/in-flight.
[ ] Established UTC incident markers and deploy/delete/TTL/repair timeline.

DATA MODEL / QUERY
[ ] Full partition key supplied; no blind scans or ALLOW FILTERING.
[ ] Clustering range and CQL LIMIT match endpoint contract.
[ ] Narrow SELECT projection; no deserializing unused payloads.
[ ] Measured p95/p99 partition bytes/rows and per-key event rates.
[ ] Day/hour/minute buckets sized to peaks and real row bytes, not global means.
[ ] Shards use stable hashing/routing, bounded fan-out, and global ordering.
[ ] UTC boundaries, late events, and identical timestamps covered by integration tests.

TOMBSTONE / RETENTION
[ ] Audited TTL (default/write), row/range/partition DELETEs, and null writes.
[ ] Distinguished CQL NULL vs. UNSET in mapper/Driver.
[ ] Correlated TombstoneScannedHistogram/LiveScannedHistogram with logs.
[ ] Monitored SSTablesPerRead, pending compactions, disk await, and GC.
[ ] gc_grace_seconds and last successful repair coverage meet safety policies.
[ ] Never dropped grace to 0, deleted SSTables/hints, ran truncatehints, or forced blind compactions.
[ ] Compaction strategy matches append/out-of-order/TTL/UPDATE/DELETE patterns.
[ ] If switching strategy, verified capacity, headroom, canary, and rollback.

JAVA / HTTP
[ ] Managed CqlSession + prepared CQL; never create sessions per request.
[ ] Server LIMIT and client page size separated, with byte/row budgets.
[ ] Enforced CQL deadlines, bounded in-flight/retries, and backpressure.
[ ] Timeouts never coerced into empty lists or 404.
[ ] All endpoints enforce tenant/device authorization.
[ ] Zero raw payloads or partition IDs in high-cardinality metrics.
[ ] Tested Spring Data generated CQL; nulls never delete columns silently.

MIGRATION / CORRECTNESS
[ ] Created V2 separately; never altered partition keys in place.
[ ] Dual-write/CDC provides durable catch-up, stable full keys, idempotent retries.
[ ] Backfill preserves TTL expiry, DELETEs, timestamps, and generations.
[ ] Reconciled event IDs, live/deleted state, and values—not just COUNT.
[ ] Shadow reads/canaries, SLO stop criteria, and rollback artifacts/schemas ready.
[ ] V1 retired only after retention, backups, approvals, and zero remaining clients.

VALIDATION / OPERATIONS
[ ] Tested shapes S1..S6: small/large × low/high tombstones + hot QPS.
[ ] Multi-node RF3/LOCAL_QUORUM and anti-entropy tested separately where needed.
[ ] Never changed CL/timeout/page/projection mid-A/B benchmark unrecorded.
[ ] Server metrics and client p99 improved at comparable offered load.
[ ] Correctness, pagination, TTL/delete, and tenant isolation verified post-fix.
[ ] Archived incident report, owners, repair schedule, and monitoring alerts.
~~~

## 31. On-Call Decision Flowchart

~~~mermaid
flowchart TD
    A["High read timeout / p99"] --> B["Identify request/query/table/CL, UTC time window"]
    B --> C{"Multiple tables/keys slow together?"}
    C -->|Yes| D["Check replica availability, GC, disk, queues, repair/compaction"]
    D --> E{"Node/cluster overloaded?"}
    E -->|Yes| F["Shed noncritical load; restore availability/capacity safely"]
    E -->|No| G["Inspect narrow sample, table metrics, and query shape"]
    C -->|No| G
    G --> H{"High tombstones scanned?"}
    H -->|Yes| I["Check TTL, range DELETEs, NULL mapper, gc_grace, SSTables"]
    H -->|No| J{"High partition bytes/rows or per-key QPS?"}
    J -->|Yes| K["Narrow range/projection; bucket/shard/rollup design"]
    J -->|No| L["Inspect network/driver/JSON, filters, cache, compaction"]
    I --> M["Bounded mitigation + retention/compaction/repair plan"]
    K --> M
    L --> M
    F --> N["Verify p99, QPS, errors, ID/value correctness"]
    M --> N
    N --> O{"Targets met on representative traffic?"}
    O -->|No| P["Rollback/escalate; test next hypothesis"]
    P --> G
    O -->|Yes| Q["Canary rollout, add alerts, write postmortem"]
~~~

### 31.1. Verifiable Conclusion Template

~~~text
Identified:
  query_name=events_recent_by_device
  primary_cause=TTL + range tombstones in per-device partition
  evidence=server warnings + tombstone histogram + CQL trace + delete job UTC

Actions:
  immediate=bound UTC time window, throttle batch deletions, bound in-flight
  long_term=V2 hour buckets + narrow projection, tested TTL/repair policy

Unchanged:
  LOCAL_QUORUM / tenant authorization / business retention policy

Verified:
  client p99 and timeouts under comparable workload
  expected IDs/values/TTLs/deletes accurate on sampled partitions/buckets
  compaction/disk/GC/backlogs within bounds; repair coverage recorded

Remaining risks:
  legacy v1 partitions / late writes / backup restore / cross-DC ...
~~~

Never write a vague conclusion like "Cassandra had tombstones so we forced compaction and it's fine" without documenting **which query, test limits, preserved correctness, storage/replica side effects, and ongoing monitoring owners**.

## 32. References and Summary

Verify configuration options and APIs against your **exact pinned Cassandra, Java Driver, and Spring Data versions**:

1. [Apache Cassandra — Documentation](https://cassandra.apache.org/doc/stable/): architecture overview, read/write paths, storage engine, replication, and version-specific settings.
2. [Apache Cassandra — CQL data manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT`, `UPDATE`, `DELETE`, TTL, CQL conditions, `LIMIT`.
3. [Apache Cassandra — Compaction](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/index.html): STCS/LCS/TWCS/UCS strategies by version, SSTable expiration, tombstone handling.
4. [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): anti-entropy repair, Merkle trees, token-range scope, full/incremental repair, and tombstone safety.
5. [Apache Cassandra — Nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): node/table statistics, compaction/task health, and exact CLI syntax.
6. [Apache Cassandra Java Driver 4.18 — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/): prepared/bound statements, bind parameters, and reuse.
7. [Apache Cassandra Java Driver 4.18 — Paging](https://apache.github.io/cassandra-java-driver/4.18.0/core/paging/): page size, full traversal, and native paging limits.
8. [Spring Data Cassandra — Mapping/Template](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): mapping, persistence, and partial updates per Spring Data release line.

**Summary:** Both tombstone-heavy reads and large/hot partitions can cause Cassandra **high read p99, timeouts, or GC/disk/network spikes**, yet they demand **different evidence and fixes**. Tombstones arise from `DELETE`, `NULL`, TTL, and range deletions; they must live long enough to protect consistency when replicas lag, so **`gc_grace_seconds`, compaction, and anti-entropy repair** are never casual disk-cleanup buttons. Oversized partitions stem from **partition keys, bucketing, and workload patterns**; neither a small `LIMIT` nor a compaction strategy fixes a schema stuffing years of events under one token key. Start from **query shape + CL + metrics/logs/tracing + partition/QPS distributions**, shed load safely, and adopt **query-driven buckets/shards/projections** alongside migrations that preserve TTL, deletes, and reconciliation. Mark an incident resolved only when **p95/p99, goodput, tombstone/partition scans, resource pressure, and ID/value/retention correctness** all hold under representative traffic—never merely because warnings stopped firing.
