# Local Secondary Indexes and Query Coordination Cost

## 1. The problem: finding data without knowing the partition key

Apache Cassandra is a **distributed wide-column** database. A table is distributed by its **partition key**, while **clustering columns** order rows within each partition. A query that knows the full partition key typically has a clear routing path to the replicas holding the data.

However, an application sometimes asks: "Find all events with `status = 'WARN'`," when `status` is not part of the primary key. To support filtering on such columns, Cassandra provides **secondary indexes**. The original index type is **2i (legacy secondary index)**, implemented as a **local index structure on each node**.

2i creates the impression of a "cluster-wide index" because users simply send a `SELECT ... WHERE status = ?` query. In reality, **there is no central index node holding a complete list of all rows**. Each node maintains an index for the data residing on that node; the coordinator must coordinate searches across the relevant nodes/replicas. This is why 2i can incur higher **fan-out, network, CPU, disk I/O, and result-merging costs** than a partition-key query.

This lesson belongs to the **Indexes** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module and connects with query-driven table design, replication/consistency, compaction/repair, troubleshooting, and accessing Cassandra from Java.

**After this lesson, you will be able to:**

1. Explain why 2i is called a **local index** and why its queries can become **distributed queries**.
2. Compare the execution path of a partition-key `SELECT` versus a 2i `SELECT` without a partition key.
3. Create, query, inspect, and drop a 2i using CQL in a safe lab environment.
4. Analyze cardinality, matching row counts, wide partitions, update/delete frequency, and node count to predict cost.
5. Understand why `LIMIT`, `ALLOW FILTERING`, and raising consistency do not automatically make 2i queries cheap.
6. Know when to prefer a query-driven table or **SAI** (Apache Cassandra 5.0+) instead of 2i.
7. Gather evidence via cqlsh, tracing, metrics, and the Java Driver before deciding to use an index in production.

## 2. Distinguishing primary index, 2i, and SAI

| Criterion | Primary index | Legacy secondary index (2i) | Storage-Attached Index (SAI) |
| --- | --- | --- | --- |
| Query entry point | **Partition key** | Indexed column value, including non-primary-key columns | Column value with SAI |
| How is it created? | Automatically when creating `PRIMARY KEY` | Version-appropriate `CREATE INDEX` (legacy type) | `CREATE INDEX ... USING 'sai'` per supported syntax/version |
| Storage | Storage engine partition/row structures | **Hidden local index table on each node**, separate from base table | Index structures attached to Memtables/SSTables |
| When partition key is missing | Cannot be used for a single-partition point lookup | May have to search across multiple nodes and merge results | More optimized index query mechanism, but still requires considering distribution and selectivity |
| Maintenance cost | Tied to table writes | Extra index writes/data, tombstones, rebuilds | Extra storage/indexing cost; integrated into the storage engine |
| Version | All common Cassandra versions | Long-standing 2i mechanism | **Apache Cassandra 5.0+** |
| New design recommendation | Preferred whenever key is known | Restricted; use only when validated, especially alongside partition key | Preferred to evaluate if indexing non-key columns in Cassandra 5.x+ |

According to Apache Cassandra 5.0 documentation, `legacy_local_table` is the default 2i type when running `CREATE INDEX` without specifying a type, whereas `sai` is the newer mechanism. For Cassandra 4.x, check your version's syntax and support; **do not copy 5.x SAI options into older versions**.

Do not treat SAI as a "solution for every query": if a query must scan or aggregate most of the dataset, you still need to evaluate partition design, workload, node count, and analytics solutions.

## 3. How is a local index maintained on each node?

### 3.1. Hidden table mapping indexed values to rows

With 2i, when a node holds base table data, it maintains **a local hidden index table** for the indexed column. Conceptual model:

~~~text
Node A:
  Base table:
    (sensor-01, 2026-11-21, 01:00) -> status=OK
    (sensor-02, 2026-11-21, 01:02) -> status=WARN
  Local 2i for status:
    OK   -> [row keys sensor-01/...]
    WARN -> [row keys sensor-02/...]

Node B:
  Base table:
    (sensor-03, 2026-11-21, 01:03) -> status=WARN
  Local 2i for status:
    WARN -> [row keys sensor-03/...]
~~~

This is a **simplified model**, not a claim that data is split across exactly two nodes or that the hidden table's physical format matches this text layout. With a replication factor greater than 1, multiple replicas can store the same partition, and each replica maintains index information **locally on its own node**.

Key takeaways:

- The index **does not ship all `status` values to a central index server**.
- The local index helps a node find **candidate row keys**, after which it must inspect/read base table data to return accurate results.
- Replicas and data state still follow Cassandra's **replication, consistency, and timestamp/tombstone** rules.
- Stale index entries can exist after updates/deletes; the read path performs validation checks to avoid returning rows that no longer match the predicate.

### 3.2. When is the index updated?

When an application executes `INSERT` or `UPDATE` on a column with 2i, Cassandra maintains the index along the table's write path. If you create an index **after data already exists**, Cassandra must **build the index over existing data**, typically via a background build process. During that window, do not assume an index query will immediately return complete results across the entire cluster.

When changing:

~~~text
status = 'WARN'  -->  status = 'OK'
~~~

the node must handle invalidating the old mapping and writing the new mapping. Repeated updates/deletes can leave **tombstones** in the index and data sources, increasing read and compaction costs. Automatic index maintenance **does not mean zero cost**.

## 4. Why must the coordinator do more work?

### 4.1. Query by partition key: known destination

Consider a table with partition key `(device_id, event_day)`:

~~~sql
SELECT event_time, status
FROM local_2i_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

The coordinator computes the token for the partition, identifies the replica set from the keyspace's replication strategy, and sends read requests according to the CL. This access path has a **clearly bounded key scope**.

### 4.2. Index query without partition key: unknown destination

~~~sql
SELECT device_id, event_day, event_time, status
FROM local_2i_lab.events_by_device_day
WHERE status = 'WARN';
~~~

Here `status` is an indexed column, but every partition in the table **could potentially contain** `WARN`. The coordinator cannot use `status` as a partition key to compute a single base-table token. It must orchestrate search tasks across **multiple nodes/replicas responsible for the relevant data ranges**, gather candidate rows, verify predicates, and merge results.

~~~mermaid
flowchart LR
    App["cqlsh / Java Driver"] -->|"WHERE status='WARN'"| Coord["Coordinator"]
    Coord -->|"Search local 2i"| A["Node A: local index"]
    Coord -->|"Search local 2i"| B["Node B: local index"]
    Coord -->|"Search local 2i"| C["Node C: local index"]
    A -->|"Candidate rows and data"| Coord
    B -->|"Candidate rows and data"| Coord
    C -->|"Candidate rows and data"| Coord
    Coord -->|"Merge + verify + limit results"| App
~~~

**This diagram only illustrates fan-out**: not every 2i request necessarily sends a message to *every* node. The planner, token ranges, replica selection, CL, and version determine how many nodes actually participate. However, when the partition key is omitted, the number of nodes/partitions examined can grow with data size and cluster scale.

### 4.3. Components of read cost

A mental model:

~~~text
Read by partition key:
  find replicas for 1 partition
  + read partition / clustering range
  + coordinate responses per CL

Read by 2i without partition key:
  plan index search across multiple nodes/token ranges
  + communicate and wait on multiple search branches
  + read local index on each branch
  + read base rows / filter stale candidates
  + merge, paginate, and return results
~~~

Do not turn this sketch into an absolute `N × latency` timing formula. Sub-tasks may run in parallel; final latency can be governed by **the slowest branch, tail latency, result size, networking, paging, contention, and deadlines**. Total CPU/I/O/network across the cluster can still rise under wide fan-out.

### 4.4. Role of consistency level

With **RF = 3 in a single datacenter**, `LOCAL_QUORUM` typically requires two replicas in that DC to respond for each queried data range; `ONE` requires fewer. However, **CL is not the number of nodes a 2i query must contact**, because an index query without a partition key can span many partitions and token ranges.

Do not conflate:

- **Number of replicas needed to satisfy consistency**.
- **Number of nodes/ranges that must be contacted to find all candidate rows**.
- **Number of rows that actually match the predicate**.

Therefore, lowering `LOCAL_QUORUM` to `ONE` does not eliminate the distributed search nature and weakens consistency guarantees; do not treat it as a default "fix" for slow 2i queries.

## 5. Choosing columns to index: cardinality, selectivity, and data distribution

### 5.1. Clear definitions of two terms

- **Cardinality** of a column: the number of distinct values in the dataset. A boolean has at most two values, whereas a nearly unique UUID has very high cardinality.
- **Matching fraction** (proportion of rows matching a value): the number of rows matching `status = 'WARN'` divided by the total rows examined. In a 1-million-row example, if `WARN` matches 800,000 rows the result set is huge; if it matches 100 rows the result set is small.

A column whose cardinality is not ultra-low can still have **skewed distribution**. For example, `status` has 10 values, but `OK` accounts for 99% of rows: querying `OK` has a high matching fraction, while `WARN` may be small. Effectiveness must be evaluated **per value and against the real workload**, not solely by distinct value count.

### 5.2. Why both extremes are unfavorable for 2i

| Column characteristic | Example | Primary cost/risk |
| --- | --- | --- |
| Very few values | `is_active boolean`, `status = 'OK'` on almost every row | Each common value has a huge posting list; index partitions can become large and hot. |
| Nearly unique values | `request_id uuid` or unique email | Huge number of index entries and expensive distributed lookups compared to a keyed point lookup; higher maintenance/storage cost. |
| Frequently updated/deleted | `current_state` changing many times per minute | Index tombstones/stale entries, read amplification, and compaction overhead. |
| Moderate cardinality, rarely changing | `category` or device type in a bounded set | Can be usable if queries are well scoped, especially when partition key is known; still requires benchmarking. |
| Column used to fetch most of the table | `status='OK'` on 98% of rows | An index does not turn exporting/scanning massive volume into a small operation. |

A common flawed rule of thumb is "**always create a 2i for low cardinality**." *Too-low* cardinality can generate gigantic index buckets. Conversely, indexing *too-high* cardinality can create countless entries for little gain per query. The sweet spot depends on **matching fraction, partition width, update rate, node count, and read frequency**.

### 5.3. Wide tables and hot partitions still matter

Suppose a single `device_id` accumulates millions of events in a partition without time bucketing. A `status` index may return candidates across many clustering rows of that partition; reading base rows, checking tombstones, and paging remain very heavy. **An index does not replace time bucketing** or partition size control.

If too many concurrent writes target an extremely common indexed value on a node, the local index structure itself can become another source of contention/hotspot. During design, inspect both the **base partition key** and the distribution of **indexed values**.

## 6. Lab: creating a 2i and comparing keyed vs. distributed queries

The lab below assumes **Cassandra 4.1 or 5.x, a single isolated node, RF = 1**, with no production data. It demonstrates **validity** and 2i syntax; it **cannot measure multi-node fan-out**. To measure coordinator overhead, you need a multi-node lab cluster with larger data volume and matching hardware/configuration.

### 6.1. Creating the keyspace and query-driven table

From a terminal with `cqlsh`:

~~~bash
cqlsh 127.0.0.1 9042
~~~

In cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS local_2i_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS local_2i_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  site_id text,
  status text,
  value double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

DESCRIBE TABLE local_2i_lab.events_by_device_day;
~~~

With composite partition key `(device_id, event_day)`, the best query for this model is "events for one device on one day," optionally bounded by `event_time`. `site_id` and `status` are **regular columns**, so knowing only them is insufficient to locate a partition via primary indexing.

### 6.2. Inserting sample data with fixed keys

~~~sql
INSERT INTO local_2i_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, site_id, status, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'site-A', 'OK', 25.1);

INSERT INTO local_2i_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, site_id, status, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'site-A', 'WARN', 29.4);

INSERT INTO local_2i_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, site_id, status, value)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:02:00Z',
        33333333-3333-4333-8333-333333333333, 'site-B', 'OK', 24.0);

INSERT INTO local_2i_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, site_id, status, value)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:07:00Z',
        44444444-4444-4444-8444-444444444444, 'site-B', 'WARN', 30.2);

INSERT INTO local_2i_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, site_id, status, value)
VALUES ('sensor-03', '2026-11-21', '2026-11-21T01:01:00Z',
        55555555-5555-4555-8555-555555555555, 'site-A', 'OK', 23.3);

INSERT INTO local_2i_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, site_id, status, value)
VALUES ('sensor-03', '2026-11-21', '2026-11-21T01:06:00Z',
        66666666-6666-4666-8666-666666666666, 'site-A', 'NEW', 24.1);
~~~

Because the UUIDs and primary keys are fixed, re-running the same statements **upserts** the same rows rather than inserting duplicate-key rows. If the lab table already contains rows from another run, adjust row-count expectations or use a fresh lab keyspace; **do not TRUNCATE non-lab tables**.

### 6.3. Baseline: SELECT by partition key, without 2i

~~~sql
CONSISTENCY ONE;

SELECT event_time, status, value
FROM local_2i_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

Expected **two rows**: `01:05 WARN 29.4` then `01:00 OK 25.1`. This is the efficient access path via partition key and clustering order, **requiring no secondary index**.

### 6.4. Creating a local 2i on status

~~~sql
-- Legacy secondary index syntax works in Cassandra 4.x/5.x.
-- Create only in the lab because indexes carry real operational cost.
CREATE INDEX IF NOT EXISTS local_2i_status_idx
ON local_2i_lab.events_by_device_day (status);

DESCRIBE TABLE local_2i_lab.events_by_device_day;

SELECT index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'local_2i_lab'
  AND table_name = 'events_by_device_day';
~~~

Per Cassandra 5.0 documentation, omitting `USING` creates a legacy 2i of type `legacy_local_table` (on versions where that default applies). On other versions, check the configuration/type and documentation for your running version; do not assume every `CREATE INDEX` creates an SAI.

If you create the index **after the six rows already exist**, the build over existing data may proceed **asynchronously**. Before concluding a query returns incomplete results, verify index build completion across nodes and inspect logs/metrics if needed. Do not treat a successful `CREATE INDEX` return as automatic proof the index is immediately ready cluster-wide.

### 6.5. SELECT via 2i without a partition key

~~~sql
SELECT device_id, event_day, event_time, site_id, status, value
FROM local_2i_lab.events_by_device_day
WHERE status = 'WARN';
~~~

Once the index is ready and no extra data is present, expect **two rows**:

| device_id | event_time (UTC) | site_id | status | value |
| --- | --- | --- | --- | ---: |
| `sensor-01` | `01:05` | `site-A` | `WARN` | 29.4 |
| `sensor-02` | `01:07` | `site-B` | `WARN` | 30.2 |

**Do not expect a fixed ordering across rows from two partitions.** `CLUSTERING ORDER BY` applies only *within the same partition*; it does not impose a global sort for rows retrieved via an index across multiple partitions.

In a single-node lab, fast execution does not prove a 2i query will stay fast on a table with tens of millions of rows across many nodes. Full **fan-out/merge** costs appear only when multiple token ranges and replicas participate in serving the query.

### 6.6. Adding the partition key to narrow scope

~~~sql
SELECT event_time, status, value
FROM local_2i_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND status = 'WARN';
~~~

The goal is to find `WARN` **within a known partition**. This pattern is logically narrower in scope than table-wide `WHERE status='WARN'` and is a scenario where 2i can carry lower risk. However, how the planner combines primary-key and indexed predicates can depend on version; if rejected for filtering, **do not blindly add `ALLOW FILTERING`**. Check the schema, query rules, an alternative that queries solely by partition key and filters the small row set in the application, or evaluate SAI in a supported version.

### 6.7. Illustrative error: multiple conditions unsupported by a single 2i

~~~sql
-- site_id is not in the primary key and has no separate index.
-- On many Cassandra versions this raises a filtering error.
SELECT device_id, event_time, status
FROM local_2i_lab.events_by_device_day
WHERE status = 'WARN'
  AND site_id = 'site-A';
~~~

Do not assume that having an index on `status` makes Cassandra automatically build composite indexing for other columns. Legacy 2i has limitations with **multiple predicates**; even creating two separate 2i indexes can still require `ALLOW FILTERING` in certain queries, as Cassandra documentation illustrates. If querying by `site_id + status + day` is frequent, evaluate **a query-driven table** or **SAI in Cassandra 5.x**.

## 7. Updating/deleting indexed columns: what is the impact?

### 7.1. Changing a row's status

Perform this only **after verifying the initial `WARN` results**:

~~~sql
UPDATE local_2i_lab.events_by_device_day
SET status = 'OK'
WHERE device_id = 'sensor-02'
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T01:07:00Z'
  AND event_id = 44444444-4444-4444-8444-444444444444;

-- Once the change is reflected, usually only sensor-01's WARN remains.
SELECT device_id, event_time, status
FROM local_2i_lab.events_by_device_day
WHERE status = 'WARN';
~~~

Because the update specifies the **full primary key**, Cassandra knows which row to modify. The 2i must update mappings for both the old value `WARN` and the new value `OK`. During index maintenance, **tombstones and stale index entries** can increase read and compaction overhead, especially on frequently updated columns.

Do not use a read from a single replica during concurrent writes to assert immediately that all replicas and indexes have converged. Replication, CL, index build speed, and node state still affect observations in a real cluster.

### 7.2. Why stale index entries do not return wrong data

An index may still map to a row after the row is deleted or the indexed value changes, depending on SSTable, tombstone, and replica states. Cassandra includes mechanisms for **validating candidate results and handling tombstones** to avoid returning stale data; however, doing so still requires reading base data and adds overhead. This is why write/update/delete-heavy tables are typically **poor candidates for legacy 2i**.

### 7.3. Removing the index from the lab

~~~sql
-- Operates only on the lab index; queries filtering by status may stop working.
DROP INDEX IF EXISTS local_2i_lab.local_2i_status_idx;
~~~

`DROP INDEX` removes the index structure, **not the base table**. In real systems, this command can break applications querying by that index; follow migration tracking and rollback plans rather than running it ad hoc.

## 8. How can distributed queries become expensive?

### 8.1. Fan-out increases total resource usage and tail latency

When a query does not specify a partition, the coordinator may have to search across multiple token ranges and communicate with many nodes. As cluster scale grows:

- **More sub-tasks** can generate additional requests, queueing, and context switching.
- **One slow branch** can prolong overall response time.
- **Large result sets** increase bytes transferred, serialization/deserialization, paging, and coordinator aggregation CPU.
- **Timeouts and retries** can amplify cluster load when each initial request already fans out.
- **RF/CL** affects replica count and response requirements, but does not turn `status` into a partition key.

Thus, a small matching row count does not necessarily mean a cheap query: Cassandra may still need to **query many locations** to be certain it found all candidates.

### 8.2. LIMIT does not prevent pre-search cost

~~~sql
SELECT device_id, event_day, event_time, status
FROM local_2i_lab.events_by_device_day
WHERE status = 'OK'
LIMIT 10;
~~~

`LIMIT 10` caps the number of returned rows, **not guaranteeing that only ten index entries are read** or only one node is contacted. With a distributed local index, finding candidates and coordinating results can still be expensive. Moreover, `LIMIT` **does not establish cluster-wide ordering**; if you need the "10 latest OK events system-wide," you need a model/query that guarantees ordering over an appropriate scope.

### 8.3. ALLOW FILTERING does not create an index

~~~sql
-- Warning example: do not run on large tables.
SELECT device_id, event_time, status
FROM local_2i_lab.events_by_device_day
WHERE status = 'WARN'
  AND site_id = 'site-A'
ALLOW FILTERING;
~~~

`ALLOW FILTERING` permits Cassandra to perform **extra filtering steps** that it warns have unpredictable cost. It does not turn `site_id` into a new index and does not guarantee the planner will read only one partition. Use it deliberately only in labs or thoroughly measured workloads; **never treat it as a "optimize query" switch**.

### 8.4. Local indexes and availability

If some nodes or index replicas are unavailable or still building, 2i queries may fail with `Unavailable`, `ReadTimeout`, or `DriverTimeout` depending on CL, node health, and planner behavior. A working index on a subset of nodes does not prove the entire cluster is ready.

Interpret errors accurately:

- `Unavailable`: insufficient replicas available for the requested consistency level.
- `ReadTimeout`: insufficient responses received before the deadline.
- `DriverTimeoutException`: client timeout expired before receiving a complete response.
- `InvalidRequest`: invalid query/index/filtering per CQL or schema rules.

Do not resolve index failures by **opening all firewall ports, lowering production CL, or setting infinite timeouts**.

## 9. Observing and measuring: never extrapolate from one tiny query

### 9.1. Verifying schema and index existence

~~~sql
SHOW VERSION;
DESCRIBE TABLE local_2i_lab.events_by_device_day;

SELECT keyspace_name, table_name, index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'local_2i_lab'
  AND table_name = 'events_by_device_day';
~~~

If the index is missing, verify the creation statement ran against the **intended cluster and keyspace**. If the index was just created on a populated table, check **build status per node**. Having the index in schema metadata does not by itself prove local index builds have completed on every node.

### 9.2. Tracing both query patterns

~~~sql
-- Lab exercise: TRACING introduces overhead.
TRACING ON;

-- Baseline with explicit partition routing.
SELECT event_time, status
FROM local_2i_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';

-- Query relying solely on the secondary index.
SELECT device_id, event_time, status
FROM local_2i_lab.events_by_device_day
WHERE status = 'WARN';

TRACING OFF;
~~~

In the trace, inspect the **coordinator, index lookup steps, count/type of peer requests, and timings** as recorded by your version. Do not assume the number of trace lines equals the number of replicas; a tiny query on one node cannot demonstrate full distributed networking. Because tracing adds overhead, also measure latency with tracing **off**.

### 9.3. Client and cluster metrics to measure

| Metric group | Question |
| --- | --- |
| **Read latency p50/p95/p99** | How does tail latency of `WHERE status=?` differ from a keyed lookup? |
| **Coordinator request latency** | How long does the receiving node spend coordinating and merging? |
| **Internode traffic/messages** | Do index queries generate significantly more network requests? |
| **Partition/index selectivity** | How many actual rows match each value? Does one value represent 90% of rows? |
| **Disk I/O, SSTable count, compaction** | Are reading index/base rows, tombstones, and compactions creating bottlenecks? |
| **CPU/GC, queues, dropped messages** | Does fan-out increase load/latency on the coordinator or replicas? |
| **Timeout/retry rate** | Does increasing concurrency trigger retry storms? |
| **Index build/rebuild status** | Have all nodes finished building the index before benchmarking? |

In environments with Cassandra administrative access:

~~~bash
nodetool status
nodetool describecluster
nodetool tablestats local_2i_lab.events_by_device_day
nodetool compactionstats
~~~

`nodetool` commands typically run over JMX, **not** CQL/native port 9042. Output depends on the version and target node. `nodetool status` shows ring health, not per-query 2i cost; correlate metrics with specific workloads.

### 9.4. How to benchmark fairly on a multi-node cluster

1. Run two representative workloads: `Q_key` with the full partition key and `Q_2i` with only the indexed predicate; **do not call them semantically identical** if returned row counts differ.
2. Record **row count, bytes, key distribution, and matching fraction** for each query. Normalize requested work when comparing latency.
3. Fix Cassandra version, RF, CL, CPU/RAM/disk, client concurrency, page size, and timeouts; record cqlsh/driver versions.
4. Separate warm-up from measurement and run repeated trials; never draw conclusions from a single trace or cold-cache query.
5. Collect **p95/p99, throughput, network bytes, CPU/GC, disk I/O, and compaction/tombstone metrics** across multiple nodes.
6. Test both **common and rare** indexed values; do not test only a `WARN` value with very few rows.
7. Evaluate slow or disconnected nodes in a **lab**; never inject faults arbitrarily in production.

Do not invent arbitrary thresholds like "2i is always fast under N nodes/N million rows." The crossover point to another table or SAI depends on actual data and SLAs.

## 10. Index maintenance and background operations

### 10.1. Index build and rebuild

After `CREATE INDEX` on an existing table, Cassandra builds the index over existing data in the background. On a multi-node cluster, verify **each node** has completed the process while monitoring logs/index metrics and read/write latency impact.

If a native index becomes corrupted or needs rebuilding per version guidance, Cassandra provides an administrative command:

~~~bash
# Reference syntax ONLY; do not run arbitrarily in production.
# Rebuilding an index can generate substantial CPU/disk/compaction load.
nodetool rebuild_index local_2i_lab events_by_device_day local_2i_status_idx
~~~

This command applies to the node contacted by `nodetool` (typically localhost or `-h` host). Do not run it once and assume indexes across the **entire cluster** are rebuilt. Plan node by node, monitoring progress/logs, JMX permissions, disk space, and rollback steps per your runbook.

### 10.2. Compaction, repair, TTL, and tombstones

2i is a local index tied to each node's data, affected by updates, deletes, and maintenance. When a table uses **TTL**, accumulates tombstones, or frequently mutates indexed values, the index can accumulate stale entries and deletion markers that require extra filtering at query time.

However, **repairing replica data** and **rebuilding a local index** are distinct operations:

- `nodetool repair` synchronizes replica data across token ranges according to operational consistency.
- `nodetool rebuild_index` rebuilds a table's native secondary index on the specified node.
- `nodetool compact`/compaction processes SSTables and tombstones per compaction strategy; it is not a blanket "fix all 2i queries" command.

Do not run rebuild, repair, or major compaction as harmless trial-and-error; assess load and root cause first.

## 11. Alternatives when 2i coordination cost is too high

### 11.1. A second query-driven table

Suppose an important business requirement is:

> Fetch `WARN` alerts at a site on a given day, newest first, up to 100 rows.

The original table with partition key `(device_id,event_day)` does not match this access pattern. You can design a dedicated query table:

~~~sql
-- Illustrative model: time-bucketed by site, day, status, and shard.
-- Sharding requires a deterministic rule; do not change it arbitrarily on retries.
CREATE TABLE IF NOT EXISTS local_2i_lab.events_by_site_status_day (
  site_id text,
  event_day date,
  status text,
  shard smallint,
  event_time timestamp,
  device_id text,
  event_id uuid,
  value double,
  PRIMARY KEY ((site_id, event_day, status, shard),
               event_time, device_id, event_id)
) WITH CLUSTERING ORDER BY
  (event_time DESC, device_id ASC, event_id ASC);
~~~

Example query for one shard:

~~~sql
SELECT event_time, device_id, event_id, value
FROM local_2i_lab.events_by_site_status_day
WHERE site_id = 'site-A'
  AND event_day = '2026-11-21'
  AND status = 'WARN'
  AND shard = 0
LIMIT 100;
~~~

This design **does not automatically populate data** in the new table. The application or pipeline must write or backfill matching rows. If multiple shards are used, query the relevant shards and **merge top-N** in the application; shard count depends on throughput and partition size rather than a single constant for all sites.

**Status-change warning:** when `status` is part of the query table's partition key, changing `WARN → OK` typically requires **deleting the row from the old partition and writing the row to the new partition**. This is a multi-table synchronization problem subject to partial failures, requiring idempotency/reconciliation. Cassandra `BATCH` is not a global SQL transaction with full rollback/isolation.

### 11.2. SAI if using Apache Cassandra 5.0+

**Storage-Attached Index (SAI)** is built into Apache Cassandra 5.0, attaching indexes to Memtables/SSTables and supporting predicates more efficiently than legacy 2i across many workloads. For modern schemas, Cassandra documentation recommends evaluating SAI rather than creating new legacy 2i indexes when secondary indexing is needed.

An example for **Cassandra 5.x on a separate lab table**, without mixing SAI and 2i on `events_by_device_day`:

~~~sql
-- Run only if Cassandra 5.x supports SAI.
-- Completely separate table with NO legacy 2i.
CREATE TABLE IF NOT EXISTS local_2i_lab.events_sai_demo (
  event_id uuid PRIMARY KEY,
  status text,
  site_id text
);

CREATE INDEX IF NOT EXISTS status_sai_idx
ON local_2i_lab.events_sai_demo (status)
USING 'sai';

INSERT INTO local_2i_lab.events_sai_demo (event_id, status, site_id)
VALUES (77777777-7777-4777-8777-777777777777, 'WARN', 'site-A');

SELECT event_id, status, site_id
FROM local_2i_lab.events_sai_demo
WHERE status = 'WARN';
~~~

If you are on Cassandra 4.x, **skip this SAI block**; run the example only on a version supporting SAI after creating the `local_2i_lab` keyspace from the earlier lab. Different Cassandra distributions and versions have distinct indexing rules. SAI also incurs **index/write/storage overhead and distributed query costs**, so benchmark rather than assuming "zero fan-out cost."

### 11.3. When should you avoid both 2i and SAI?

- Queries are **full-table scans or system-wide aggregations**: choose Spark/analytics, ETL pipelines, or appropriate summary tables.
- A few indexed values match **most of the table**: index structures barely reduce the volume of data read.
- You need a **globally ordered cluster-wide top-N**: use a controlled bucketing/aggregation model and merge strategy.
- Data is continuously updated/deleted across many states: evaluate index maintenance, tombstones, and synchronization costs.
- Access needs can be expressed cleanly via an **explicit partition key**: primary-key queries are usually simpler with more predictable cost.

## 12. Java Driver: one session, two access patterns

Example for **Java Driver 4.x**, using the lab table and `local_2i_status_idx` index created earlier. The code executes one point/partition query and one index query; **do not treat a single run's timing as a benchmark**.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Duration;
import java.time.LocalDate;

public class LocalSecondaryIndexDemo {
    public static void main(String[] args) {
        String host = System.getenv().getOrDefault("CASSANDRA_HOST", "127.0.0.1");
        String dc = System.getenv().getOrDefault("CASSANDRA_DC", "datacenter1");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .build()) {

            PreparedStatement byKey = session.prepare(
                "SELECT event_time, status, value " +
                "FROM local_2i_lab.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ?");

            PreparedStatement byStatus = session.prepare(
                "SELECT device_id, event_time, status, value " +
                "FROM local_2i_lab.events_by_device_day " +
                "WHERE status = ?");

            BoundStatement keyQuery = byKey.bind(
                    "sensor-01", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(50)
                .setTimeout(Duration.ofSeconds(5));

            BoundStatement indexQuery = byStatus.bind("WARN")
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(50)
                .setTimeout(Duration.ofSeconds(5));

            long startKey = System.nanoTime();
            int keyRows = 0;
            for (Row row : session.execute(keyQuery)) {
                keyRows++;
            }
            long keyElapsedNs = System.nanoTime() - startKey;

            long startIndex = System.nanoTime();
            int indexRows = 0;
            for (Row row : session.execute(indexQuery)) {
                indexRows++;
            }
            long indexElapsedNs = System.nanoTime() - startIndex;

            System.out.println("partition_rows=" + keyRows +
                    " duration_ns=" + keyElapsedNs);
            System.out.println("index_rows=" + indexRows +
                    " duration_ns=" + indexElapsedNs);
        }
    }
}
~~~

**Code limitations and takeaways:** If you executed `DROP INDEX` in section 7.3, recreate `local_2i_status_idx` and verify index build completion before running this Java example; otherwise, `byStatus` may be rejected.

- `datacenter1` is an example; use the actual DC name from `SELECT data_center FROM system.local;`.
- CL, page size, and timeout are **statement-level settings**, independent of `CONSISTENCY` in another cqlsh session.
- The driver may pick different coordinators for the two statements; an index query without a partition key typically **cannot be routed to a single specific token** like a keyed query.
- The two statements have **different semantics and row counts**, so printed durations are not a fair performance comparison.
- `System.nanoTime()` measures client-side wall-clock time in this example, including Java/network/deserialization overhead; benchmark with repeated trials, warm-up, and percentiles.
- The snippet omits TLS/auth for lab simplicity. Production must configure an SSL context, credentials, approved contact points, and retry policies.
- If the index was dropped or is still building, `byStatus` may fail or return incomplete data; do not automatically add `ALLOW FILTERING` or retry indefinitely.

## 13. Troubleshooting: accurately diagnosing 2i errors

| Symptom | Possible explanation | Check/action |
| --- | --- | --- |
| `WHERE status='WARN'` is rejected | Index does not exist, wrong keyspace/table, unsupported predicate | `DESCRIBE TABLE`, `system_schema.indexes`, verify version and query. |
| `CREATE INDEX` finished but queries return incomplete results | Background build not yet finished on all nodes, or data/CL changing | Inspect logs/index build status and replica health; metadata alone is insufficient. |
| Index query is fast in a 1-node lab, slow in a cluster | Fan-out, token range count, network/merge, hot index values | Measure p95/p99 and total resources across multiple nodes with representative data. |
| `status='OK'` is slow, `status='WARN'` is fast | Skewed matching fraction, huge `OK` posting list | Measure matching rows per value and re-evaluate table/index design. |
| Frequent `status` updates cause high latency/tombstones | Index/stale-entry maintenance and compaction | Avoid indexing volatile columns, monitor compaction, consider SAI/another table. |
| Query with two regular-column conditions raises `InvalidRequest` | One or two 2i indexes cannot efficiently combine predicates | Review query rules; never blindly add `ALLOW FILTERING` in production. |
| `ReadTimeout` on index query | Many sub-tasks, slow replica, overloaded cluster | Inspect coordinator, CL, fan-out, queues, disk, network, and logs. |
| `Unavailable` at `LOCAL_QUORUM` | Insufficient replicas for RF/DC/CL | Check `nodetool status`, replication settings, and internode networking. |
| Java reports `AllNodesFailedException` | Unstable session/native connections | Verify DNS/TCP 9042, TLS/auth, `broadcast_rpc_address`, local DC; do not blame 2i before connectivity works. |
| Application query errors right after `DROP INDEX` | Application depended on the indexed column and lost its query path | Perform dependency/migration analysis before dropping indexes. |
| Query with `LIMIT 10` still consumes heavy resources | LIMIT does not eliminate initial fan-out/index lookup | Evaluate scope/partition design and measure remote requests. |
| Returned rows change after updates/deletes | Concurrent writes, timestamps/tombstones, CL, and index state | Read by primary key to verify, and inspect consistency and logs. |

## 14. Self-practice exercises

1. Explain why legacy 2i is called a **local index** even though `WHERE status='WARN'` can return rows from multiple nodes.
2. Draw the path from **Java Driver → coordinator → local indexes → base rows → result** and compare it with a partition-key query.
3. Create `local_2i_lab.events_by_device_day` and load the sample data. Run the query by `(device_id,event_day)` to verify the baseline.
4. Create `local_2i_status_idx`, read `system_schema.indexes`, and confirm the index kind on the table. If prior data exists, why must you wait for the build?
5. Query `status='WARN'`, state the two expected rows, and explain why a global ordering cannot be expected.
6. Run `status='WARN' AND site_id='site-A'` to observe Cassandra's filtering error/constraint; why does adding a 2i not automatically handle every predicate?
7. Update `sensor-02`'s row from `WARN` to `OK`. Observe the change and explain how tombstones/stale index candidates can raise costs.
8. With a 10-million-row dataset where `status='OK'` accounts for 98%, why does a 2i on `status` have poor selectivity for this query?
9. Compare indexing a boolean column, a nearly unique UUID, and a moderately cardinal category that rarely updates. Do not choose based on cardinality alone; name two more metrics you need.
10. Explain why `LIMIT 10` on a query without a partition key does not necessarily reduce network fan-out and total I/O significantly.
11. In an RF = 3 cluster, how many replicas does `LOCAL_QUORUM` need in a DC with RF = 3? Why is that **not** the only number of nodes that may participate in a table-wide 2i query?
12. Run controlled tracing on a point query and an index query, inspect events related to the coordinator/replicas, and then turn tracing off.
13. Propose an alternative query table to retrieve `WARN` events for a site on a day. If sharded, how must the application merge results?
14. Explain why combining 2i and SAI on the same table is discouraged by documentation and why Cassandra 4.x cannot use Cassandra 5.x SAI syntax.
15. Draft a production index deployment checklist: cardinality, matching fraction, updates/deletes, build time, RF/CL, tail latency, disk/compaction, rollback, and access permissions.

**Completion criteria:** You can accurately distinguish a **local index** structure from a **distributed query**, create and query a 2i yourself, explain why coordinator fan-out is expensive, select/reject indexed columns based on workload, and propose query-driven table designs or SAI when 2i is unsuitable.

## References

- [Apache Cassandra — Indexing concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/indexing-concepts.html): distinguishing primary indexing, local 2i, and SAI, and recommending 2i use with a partition key.
- [Apache Cassandra — Secondary index (2i) concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/2i-concepts.html): local hidden tables, performance limits, and differences from SAI.
- [Apache Cassandra — When to use an index](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/2i-when-to-use.html): low/high cardinality, large posting lists, updates/deletes, and wide partitions.
- [Apache Cassandra — Working with secondary indexing (2i)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/2i-working-with.html): creating/viewing/dropping indexes, multi-predicate queries, and collection indexes.
- [Apache Cassandra — CREATE INDEX](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexes.html): index syntax, `legacy_local_table` and `sai` types, background indexing.
- [Apache Cassandra — Rebuilding 2i](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/operations/2i-build.html): index build and rebuild operations.
- [Apache Cassandra — nodetool rebuild_index](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): `nodetool rebuild_index keyspace table indexName` syntax.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): prepared statements, consistency, paging, timeouts, and metadata/coordinator handling.
