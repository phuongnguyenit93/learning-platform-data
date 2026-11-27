# Primary Index and Access via Partition/Clustering Key

## 1. What does primary index mean in Cassandra?

In Apache Cassandra, the **primary index** is the fundamental access mechanism based on a table's **partition key**. Knowing the partition key allows Cassandra to identify the replicas responsible for the partition and locate the relevant data without scanning the entire table. Inside each partition, the **clustering columns** determine row ordering, enabling access to a specific row or a contiguous range of rows.

This differs from the relational database mindset about indexes: not every column placed in a `WHERE` clause is quickly looked up via a B-tree. Cassandra is a **distributed wide-column** system where tables are designed **around the queries they will serve**, rather than creating a normalized schema by default and adding indexes to support every filtering pattern.

In the **Indexes** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, this lesson focuses on how the **primary index, partition key, and clustering key** work together with the token ring, replication, and storage engine. Understanding this mechanism helps you practice CQL, explain query errors, choose read/write consistency, observe compaction/repair, and integrate the Java Driver properly.

**After this lesson, you will be able to:**

1. Distinguish **PRIMARY KEY**, **partition key**, **clustering columns**, and **primary indexing**.
2. Explain the path client → coordinator → replica → memtable/SSTable when querying by key.
3. Write `SELECT` statements by partition key, point row, time range, and clustering order.
4. Identify queries missing the partition key, skipping a clustering prefix, or filtering on a regular column.
5. Inspect schema metadata and use a Java Driver prepared statement for keyed queries.
6. Distinguish the primary index from **secondary index (2i)** and **Storage-Attached Index (SAI)**, including version-based limitations.
7. Understand why overly wide partitions or hot partition keys still cause slow queries despite primary indexing.

## 2. PRIMARY KEY = partition key + clustering columns

Every CQL table must declare a **primary key**. The primary key uniquely identifies a row in the table, consisting of two parts with distinct roles:

| Component | Role | Impact on access |
| --- | --- | --- |
| **Partition key** | Determines the partition and token to select replicas | Routes the query to the replica set holding the target partition. |
| **Clustering columns** | Identifies distinct rows and their order within the same partition | Allows locating a row or reading an ordered contiguous range. |
| **Regular columns** | Stores non-key data attributes | Does not automatically create a primary index lookup path on their values. |

Example of three definitions:

~~~sql
-- Single partition key only; each key value has one row.
CREATE TABLE IF NOT EXISTS example_single_key (
  device_id text PRIMARY KEY,
  model text
);

-- device_id is the partition key; event_time, event_id are clustering columns.
CREATE TABLE IF NOT EXISTS example_one_partition_column (
  device_id text,
  event_time timestamp,
  event_id uuid,
  PRIMARY KEY (device_id, event_time, event_id)
);

-- The pair (device_id, event_day) together forms a composite partition key.
CREATE TABLE IF NOT EXISTS example_composite_partition (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
);
~~~

The snippet above **illustrates syntax** assuming an appropriate keyspace is already in `USE`. The lab section below will declare a complete keyspace and table that can be run standalone.

Important distinction:

- `PRIMARY KEY (device_id, event_day, event_time)` has a **single** partition key `device_id`; `event_day` and `event_time` are clustering columns.
- `PRIMARY KEY ((device_id, event_day), event_time)` has the **pair** `(device_id, event_day)` as its partition key; `event_time` is a clustering column.
- The same three columns can produce **completely different data distribution and query capabilities** depending on parenthesis placement.
- **The primary index based on the partition key is maintained automatically by Cassandra**; you neither need nor should run `CREATE INDEX` to "create a primary index" for the partition key.

### 2.1. Primary key determines uniqueness

In a table with `PRIMARY KEY ((device_id, event_day), event_time, event_id)`, two rows sharing the same `device_id` and `event_day` but differing in `event_time` or `event_id` are **two separate rows**. If you run `INSERT` multiple times with the **exact same full primary key**, Cassandra performs an **upsert** of that row's values; it does not create a duplicate primary key row.

Do not confuse this with uniqueness of a regular column such as `event_type`. Many rows can share `event_type = 'temperature'` because it is not part of the primary key.

### 2.2. Partition organization illustration

~~~mermaid
flowchart TB
    K["Partition key = (device_id, event_day)"] --> P1["Partition A<br/>(sensor-01, 2026-11-21)"]
    K --> P2["Partition B<br/>(sensor-02, 2026-11-21)"]
    P1 --> A1["01:10 — event-id-3"]
    A1 --> A2["01:05 — event-id-2"]
    A2 --> A3["01:00 — event-id-1"]
    P2 --> B1["01:03 — event-id-4"]
~~~

The diagram illustrates **logical partitions**, not a one-to-one mapping between a partition and a single machine. Each partition is stored on a **replica set** determined by its token and replication strategy; multiple copies can exist across different nodes. Within each replica, clustering order enables reading `01:10` before `01:05` and then `01:00` when the table declares `event_time DESC`.

## 3. How does the primary index route requests to replicas?

### 3.1. From partition key to token

When an application sends a query with a partition key, Cassandra uses a **partitioner** (commonly `Murmur3Partitioner` by default) to compute a **token** from the key value. Token ranges are assigned to nodes and replicas according to the topology; the keyspace's replication strategy determines the **replica set** storing that partition.

Conceptual example:

~~~text
Partition key ("sensor-01", 2026-11-21)
            |
            v
     Token = hash(partition key)
            |
            v
   Token range + replication strategy
            |
            v
  Replica set (e.g., Node A, Node B, Node C)
            |
            v
  Coordinator reads/writes per consistency level
~~~

**Do not assume the token is computed by hashing each column separately and adding them.** Cassandra uses the specific encoding of the composite partition key and the configured partitioner. The order, type, and value of each column all matter.

### 3.2. Coordinator and replica are two distinct roles

~~~mermaid
sequenceDiagram
    participant App as Java Driver / cqlsh
    participant Coord as Coordinator node
    participant A as Replica A
    participant B as Replica B
    participant C as Replica C
    App->>Coord: SELECT WHERE partition key = ... (CL)
    Coord->>Coord: Compute token, identify replicas
    Coord->>A: Request partition read
    Coord->>B: Request data/digest read as needed
    opt Based on CL/topology and read strategy
        Coord->>C: Contact additional replica
    end
    A-->>Coord: Data or response
    B-->>Coord: Response
    Coord-->>App: Result or timeout/unavailable error
~~~

This diagram is illustrative and does not mean every request must be sent to all three replicas every time. It depends on **CL, node state, read path, and version**. The coordinator can simultaneously be one of the replicas. A token/topology-aware Java Driver can select an appropriate coordinator, yet **querying with the right partition key does not mean data resides on only a single node**.

In a multi-datacenter cluster:

- `NetworkTopologyStrategy` and per-DC RF determine replicas across DCs.
- `LOCAL_QUORUM` requires a quorum of responses from the **local DC**, rather than a fixed fraction of total nodes across the entire cluster.
- Primary indexing helps **locate the partition**; consistency controls **response requirements**. The two concepts do not replace each other.

## 4. How the primary index works inside the storage engine

Cassandra uses an **LSM (Log-Structured Merge)** write architecture: writes go through the commit log and memtable, then are flushed to **immutable SSTables**. Compaction merges SSTables and reorganizes data on disk. Primary indexing is not merely an external lookup table sitting outside the data; it is directly tied to the **partition-based storage structure**.

### 4.1. Write path, partitioning, and row ordering

~~~mermaid
flowchart LR
    W["INSERT / UPDATE"] --> C["Commit log + memtable"]
    C -->|"Flush"| S["Immutable SSTable"]
    S --> D["Partitioned by token"]
    D --> R["Rows in clustering order"]
    S --> M["Compaction with other SSTables"]
~~~

When the same partition receives multiple writes, part of its data may reside in the **memtable** and across several **different SSTables**. A read operation must inspect relevant data across the necessary sources and reconcile versions/timestamps/tombstones; you cannot assume "each partition has only one file."

### 4.2. What index components does an SSTable contain?

File names **depend on the Cassandra version and SSTable format**, but the general idea is to locate the **partition key** first and then navigate to the required rows:

| Component/mechanism | Purpose | Accurate understanding |
| --- | --- | --- |
| **Memtable** | Holds unflushed data with a key-lookup structure | Can serve reads without hitting disk. |
| **Bloom filter** | Rules out SSTables that definitely do not contain the partition key | Can report *maybe present* even when absent; not used to prove a row exists. |
| **Partition index** | Locates a partition's data position within an SSTable | Forms the core of physical primary indexing. |
| **Index summary** | Compacts/samples index information in certain formats | Reduces RAM/index lookup cost, not a list of every row. |
| **Row/partition block index** | Helps locate data sections inside wide partitions | Structure and file names vary by format. |
| **Data component** | Stores row contents, cells, and related metadata | The index points to data; it does not replace data. |

**Version notes:**

- For the traditional SSTable format (commonly called **BIG**), documentation describes `Index.db` mapping partition keys to offsets in `Data.db`, `Summary.db` sampling the index, and `Filter.db` storing the Bloom filter.
- Cassandra 5.0 introduces the **Big Trie (BTI)** index format with `Partitions.db` and `Rows.db` components replacing the legacy `Index.db`. Actual format and files depend on the version, configuration, and existing SSTables.
- Therefore, do not write operational tooling assuming **every** existing SSTable must have exact `Index.db` or `Summary.db` files. Check the format and official documentation for your running version.

### 4.3. Read path through the primary index

Suppose you read all rows of a known partition:

1. The coordinator uses the partition key to identify replicas via the token/ring.
2. Each queried replica checks relevant data in the memtable and SSTables that may contain the key.
3. The Bloom filter can exclude SSTables that **definitely lack** the partition.
4. The partition index and auxiliary structures help locate the partition in the relevant SSTables.
5. Using clustering predicates, Cassandra selects the required **row or row range** within the partition in stored order.
6. The replica/coordinator reconciles timestamps, tombstones, and consistency and returns valid results to the application.

Because data can span multiple SSTables, finding the right partition **does not mean only a single disk read is needed**. SSTable count, partition width, compaction, caches, tombstones, and replica health all affect actual cost.

### 4.4. Not an RDBMS B-tree index

Primary indexing in Cassandra provides **partition-level routing** in a distributed system and LSM storage engine, unlike a B-tree index that lets you run arbitrary queries like `WHERE age > 18 ORDER BY score` over a large table.

For a query filtering only on `event_type = 'temperature'` without a partition key, the primary index has no basis to locate matching partitions. To support that query, you must **design a table for the query** or evaluate an additional indexing option appropriate for your version.

## 5. CQL Lab: from primary key to read results

### 5.1. Setting up the schema on a single-node Cassandra lab

Assuming Cassandra is running and `cqlsh` is available at `127.0.0.1:9042`:

~~~bash
cqlsh 127.0.0.1 9042
~~~

In cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS primary_index_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS primary_index_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  value double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

DESCRIBE TABLE primary_index_lab.events_by_device_day;
~~~

`SimpleStrategy` with RF = 1 is strictly for **single-node learning**. In multi-datacenter deployments, evaluate `NetworkTopologyStrategy` with per-DC RF, especially when assessing `LOCAL_QUORUM`. If the table already exists with a different schema, `IF NOT EXISTS` **does not alter the existing schema**; check `DESCRIBE TABLE` before proceeding.

### 5.2. Creating fixtures with deterministic primary keys

~~~sql
INSERT INTO primary_index_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'temperature', 25.1);

INSERT INTO primary_index_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'temperature', 25.3);

INSERT INTO primary_index_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:10:00Z',
        33333333-3333-4333-8333-333333333333, 'humidity', 60.0);

INSERT INTO primary_index_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:03:00Z',
        44444444-4444-4444-8444-444444444444, 'temperature', 23.8);
~~~

Timestamps end in `Z` (UTC), and UUIDs are fixed. Re-running with the same primary key **upserts** the same rows rather than appending extra rows like an append-only log. Because Cassandra resolves writes by timestamp, do not use script re-runs to infer write ordering under concurrent clients.

### 5.3. Accessing a partition via the primary index

~~~sql
CONSISTENCY ONE;

SELECT event_time, event_id, event_type, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

Expected **3 rows** for `sensor-01`, in order:

| event_time (UTC) | event_type | value |
| --- | --- | ---: |
| 2026-11-21 01:10 | humidity | 60.0 |
| 2026-11-21 01:05 | temperature | 25.3 |
| 2026-11-21 01:00 | temperature | 25.1 |

If you ran a previous exercise and inserted additional rows into the same partition, the row count may differ. To verify cleanly, use a fresh lab keyspace/table or reset data **only on an isolated lab** according to appropriate policy; never run `TRUNCATE` carelessly on a shared cluster.

Why is this query routing-efficient?

- `device_id` **and** `event_day` specify the complete composite partition key.
- Replicas can locate the exact partition via primary indexing.
- Rows within the partition are already sorted by the clustering key; no sorting across all partitions is needed.

### 5.4. Accessing a clustering key range

~~~sql
SELECT event_time, event_type, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T01:05:00Z';
~~~

Expected result is **2 rows** at `01:10` and `01:05`. Cassandra has already identified **a single partition** before applying the range predicate on the first clustering column. This is a core benefit of the **partition + ordered range** design.

Fetching a single row with the full primary key:

~~~sql
SELECT event_time, event_type, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T01:05:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

Expected **1 row** with `temperature / 25.3`. When you supply the full partition key along with all clustering columns, the query targets one specific row.

### 5.5. Clustering order and ORDER BY

The table declares:

~~~sql
WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
~~~

When reading a partition, the default order is `event_time DESC`, with `event_id ASC` ordering rows that share the same timestamp. You can use `ORDER BY` in a direction permitted by CQL, such as reversing the entire clustering order:

~~~sql
SELECT event_time, event_id, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
ORDER BY event_time ASC, event_id DESC
LIMIT 10;
~~~

Expect `01:00` before `01:05` and then `01:10`. **`ORDER BY` on clustering columns is not a cluster-wide `ORDER BY`**, and Cassandra restricts sort orders and filter combinations that do not match the schema. Do not write `ORDER BY value` on a regular column expecting Cassandra to sort across partitions.

`LIMIT 10` only caps the number of rows returned for the query. It does not turn a query missing a partition key into an efficient targeted lookup; `LIMIT` on a broad scan can still incur significant cost.

## 6. Invalid queries and causes rooted in the primary index

### 6.1. Omitting part of a composite partition key

~~~sql
-- Incomplete partition key (missing event_day):
SELECT event_time, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01';
~~~

Because the partition key includes **both** `device_id` and `event_day`, knowing only `device_id` is insufficient to compute the token or locate a specific partition. Cassandra typically rejects this query pattern on a table without another suitable index; depending on the version, it reports a missing or restricted partition key error.

**Do not confuse this:** querying for "one device across all days" is a different business requirement from "one device on a given day." If multi-day queries are common, you can design **controlled bucketing with multiple queries** or build a dedicated table for that query; avoid cluster-wide scans.

### 6.2. Filtering by clustering column only

~~~sql
-- No partition specified; cannot leverage table-wide clustering order.
SELECT event_time, value
FROM primary_index_lab.events_by_device_day
WHERE event_time >= '2026-11-21T01:05:00Z';
~~~

The clustering key only provides lookup ordering **after a partition has been identified**. Querying by `event_time` across all devices requires a different data model, an appropriate index, or an external analytics pipeline. Do not treat `ALLOW FILTERING` as a universal fix.

### 6.3. Skipping a clustering prefix

~~~sql
-- Partition is known, but event_time is skipped to filter on event_id.
SELECT event_time, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

Given the clustering order `(event_time, event_id)`, you generally must constrain the **clustering prefix** before using subsequent columns for efficient row lookup. Without `event_time`, `event_id` does not form an independent sorted lookup path within the partition.

### 6.4. Filtering on a regular column

~~~sql
-- event_type is not in the primary key, and no secondary index exists on the table.
SELECT device_id, event_day, event_time, value
FROM primary_index_lab.events_by_device_day
WHERE event_type = 'temperature';
~~~

The primary index cannot look up partitions by `event_type`. If the business requirement is "view all temperature events," consider:

1. A **query-driven table**, such as grouping by event_type and a time bucket with appropriate partition key and cardinality.
2. Secondary index/SAI if **supported by your version**, workload, and cardinality/selectivity characteristics, after benchmarking.
3. A dedicated analytics/aggregation system if cluster-wide scans or aggregations are genuinely needed.

Adding `ALLOW FILTERING` may cause Cassandra to accept certain otherwise-rejected queries at the cost of scanning and filtering large amounts of data; **it does not create a primary index** and does not guarantee fast queries on large datasets.

### 6.5. Query pattern comparison table

| Query pattern | Uses primary indexing directly? | Assessment |
| --- | --- | --- |
| Both `device_id` and `event_day` | **Yes** | Locates a single partition. |
| Full partition + `event_time = ?` | **Yes** | Finds rows/range within one partition. |
| Full partition + range on `event_time` | **Yes** | Reads a contiguous slice in clustering order. |
| Full partition + full clustering key | **Yes** | Point lookup for a specific row. |
| Only `device_id` | **Incomplete** | Missing part of the composite partition key. |
| Only `event_time` | **No** | Clustering is meaningful only inside a specified partition. |
| Full partition, filtering only on `event_id` | **No (violates clustering prefix)** | Skips `event_time`. |
| Only `event_type` | **No** | Regular column with no secondary index. |
| `SELECT ... LIMIT 10` without WHERE | **Not a point lookup** | Still must scan/distribute read work accordingly. |

**Intentional exceptions:** CQL supports certain `TOKEN(...)` or `IN` queries for reading multiple partitions as well as secondary indexes. They have specific rules and do not change the core principle of efficient query design: prefer knowing the partition key and bounding the data per partition.

## 7. How do primary indexes and secondary indexing differ?

In Cassandra, the word "index" is used for several mechanisms that must be distinguished:

| Type | How is it created? | What does it look up by? | Trade-offs |
| --- | --- | --- | --- |
| **Primary index** | **Automatically** when defining the table's `PRIMARY KEY` | Partition key; then clustering rows | Requires designing the schema around access patterns; highly efficient when keys are known. |
| **Legacy secondary index (2i)** | Created via CQL when supported by version | Indexed non-primary key column | Index is typically local to each node; queries without a partition key can hit many nodes. |
| **Storage-Attached Index (SAI)** | Created using syntax/capabilities of supported versions, **Apache Cassandra 5.0** | Indexed columns attached to SSTables | Adds storage/maintenance overhead; requires evaluating workload and predicate limitations. |
| **Additional query table** | Create another table with a matching primary key and write synchronously from the application | Another access pattern | Must maintain data across multiple tables and handle consistency at the application layer. |

Without secondary indexes, Cassandra **does not automatically index every regular column**. Even with SAI/2i, the fact that a CQL statement runs **does not guarantee low latency or predictable cost** across all cardinalities, partitioning schemes, data sizes, and cluster topologies.

### 7.1. When to choose a new table instead of a secondary index?

Suppose the workload has two query patterns:

- **Q1:** "Events for `sensor-01` on `2026-11-21`" → the existing `events_by_device_day` table fits well.
- **Q2:** "`temperature` events on `2026-11-21` at a site" → evaluate a table bucketed by **site + event_type + day**, clustered by time with key distribution that avoids hotspots; or SAI/analytics if requirements are ad-hoc/complex.

Do not create a massive partition like `PRIMARY KEY ((event_type), event_time, device_id)` when only two `event_type` values exist. Ultra-low partition key cardinality causes **hot partitions** and load skew across replicas.

### 7.2. Secondary indexes do not fix every data modeling flaw

A secondary index can help look up non-primary-key values, but it does not replace:

- Proper **partition sizing** and time bucketing.
- Replica capacity, RF/CL choices, and internode paths.
- Designing to avoid **hot keys** and oversized partitions.
- Analyzing query/range cost, compaction, tombstones, and disk I/O.
- Distinguishing keyed OLTP queries from full-dataset analytics scans.

## 8. Designing partition/clustering keys from access patterns

### 8.1. Design process

Before creating a table, explicitly document:

1. **Who is querying?** A specific device, a site, a customer, or the entire system?
2. **Which parameters must be known in WHERE?** Can most requests supply the full partition key?
3. **Are ranges or ordering required?** For example, the 100 latest events within a day.
4. **What is the write rate per key?** Can a single device write hundreds of thousands of rows per day?
5. **What is the expected row count/partition size?** Daily, hourly, or monthly buckets should be based on real data.
6. **How skewed is the key distribution?** Do a few devices generate 90% of traffic and overheat a few replicas?
7. **RF/CL and topology?** Do queries serve a local DC, multiple DCs, or require stronger guarantees?

Only after answering these should you choose:

~~~sql
PRIMARY KEY ((device_id, event_day), event_time, event_id)
~~~

This choice fits queries by device and day. It does not automatically suit arbitrary reporting by `event_type`, site, or global analytics.

### 8.2. Too-wide vs. too-narrow buckets

| Design | Risk |
| --- | --- |
| `PRIMARY KEY ((device_id), event_time)` | A device's partition can grow unboundedly under continuous writes. |
| `PRIMARY KEY ((device_id, event_day), event_time)` | Reasonable when daily row volume is moderate and queries are day-scoped. |
| `PRIMARY KEY ((device_id, event_hour), event_time)` | Reduces partition width under high traffic, but reading 24 hours spans many partitions. |
| `PRIMARY KEY ((event_type), event_time)` | A few event types create very hot and wide partitions. |
| Too-small bucket | More partitions must be queried for a long-range query, increasing coordination overhead. |

No single bucket size is optimal for every service. In Cassandra, the right choice depends on **row count, row size, query frequency, p95/p99 latency, and load distribution**.

### 8.3. ORDER BY within one partition, not the entire table

If the requirement is "return the 20 latest events across all devices," the query cannot be solved simply with `ORDER BY event_time DESC LIMIT 20` on `events_by_device_day`. Because partitions are distributed by token, clustering order applies **only within each partition**. A different query model/table or an aggregation pipeline is needed for a globally ordered list.

## 9. Inspecting metadata to verify the primary key

In cqlsh:

~~~sql
DESCRIBE TABLE primary_index_lab.events_by_device_day;

SELECT column_name, kind, position, type, clustering_order
FROM system_schema.columns
WHERE keyspace_name = 'primary_index_lab'
  AND table_name = 'events_by_device_day';
~~~

Expected `system_schema.columns` output:

| column_name | kind | Notes |
| --- | --- | --- |
| `device_id` | `partition_key` | First component of the composite partition key. |
| `event_day` | `partition_key` | Second component of the partition key. |
| `event_time` | `clustering` | First clustering column, `DESC`. |
| `event_id` | `clustering` | Second clustering column, `ASC`. |
| `event_type`, `value` | `regular` | Not part of the primary key. |

Do not rely on the **row order** returned by `SELECT` from system tables as an indicator of key order. Read `kind`, `position`, and `clustering_order` alongside the `CREATE TABLE` statement.

Checking the lab keyspace replication:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'primary_index_lab';
~~~

`replication` explains where data copies are placed, but does not tell you which nodes are Up/Down or whether requests meet CL. You also need `nodetool status` and metrics when investigating distributed incidents.

### 9.1. TRACING: observing execution paths in the lab

~~~sql
TRACING ON;

SELECT event_time, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 3;

TRACING OFF;
~~~

Tracing shows the coordinator, read operations, and step timings. It introduces **overhead**, its IDs/timings vary across runs, and it is not a zero-interference benchmark tool. Enable it only for a small number of targeted queries; do not leave `TRACING ON` under heavy production workloads.

### 9.2. Inspecting partition width and SSTables when queries are slow

~~~bash
# Run from an authorized administrative node; not a cqlsh command.
nodetool tablestats primary_index_lab.events_by_device_day

# Partition width/row count histograms (syntax varies by version).
nodetool tablehistograms primary_index_lab events_by_device_day

# View active compactions.
nodetool compactionstats
~~~

Check logs/metrics for SSTable count, tombstones, read latency, partition size, GC, disk I/O, and caches. `nodetool` uses the administrative/JMX interface depending on version, **not native CQL port 9042** like the Java Driver. Do not run `nodetool compact` or `repair` blindly to fix a slow `SELECT` without first diagnosing query cost and data health.

## 10. Java Driver: prepared statements by partition key

Example for **Java Driver 4.x** against the lab table created above. The query always binds the **full partition key** and bounds the clustering range.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;

public class PrimaryIndexQueryDemo {
    public static void main(String[] args) {
        // datacenter1 is just an example; replace with the value from system.local.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT event_time, event_id, event_type, value " +
                "FROM primary_index_lab.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ? " +
                "AND event_time >= ?");

            BoundStatement bound = prepared.bind(
                    "sensor-01",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T01:05:00Z"))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(100);

            for (Row row : session.execute(bound)) {
                System.out.println(
                    row.getInstant("event_time") + " / " +
                    row.getUuid("event_id") + " / " +
                    row.getString("event_type") + " / " +
                    row.getDouble("value"));
            }
        }
    }
}
~~~

**Reading the Java code layer by layer:**

1. `PreparedStatement` holds a parameterized CQL query rather than concatenating user-supplied strings.
2. `device_id` and `event_day` are fully bound to locate the partition; `event_time` bounds the clustering range.
3. The driver communicates over the **native protocol** and can select a suitable coordinator using metadata/token awareness.
4. `setConsistencyLevel(ONE)` sets CL for the **Java statement**. It is independent of the `CONSISTENCY` command in a separate cqlsh session.
5. `setPageSize(100)` controls how many rows the driver requests per page (it does not mean the entire query is capped at 100 rows).

In production systems, configure credentials, TLS/CA, reachable contact points, the proper local datacenter, and appropriate retry/timeout policies. The name `datacenter1` **is not a fixed constant**; verify it using:

~~~sql
SELECT data_center, release_version FROM system.local;
~~~

`CqlSession` should be long-lived and reused across the service. If a table's schema recently changed, check schema agreement and driver metadata refresh/reprepare behavior rather than concluding the primary index "disappeared."

## 11. Diagnosing common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Query `WHERE device_id = ?` is rejected | Missing `event_day` from composite partition key | Bind the full key or design a table supporting multi-day queries. |
| Query with only `event_time` fails | Clustering does not locate partitions table-wide | Supply the full partition key or use a suitable model/index. |
| Query by `event_id` within a partition is rejected | Skipping the `event_time` clustering prefix | Add predicates following the clustering prefix or re-evaluate the data model. |
| Query `event_type = ?` fails | Regular column has no primary index lookup path | Design a query-driven table or evaluate supported SAI/2i. |
| `ALLOW FILTERING` runs the query but is very slow | Requires scanning/filtering many partitions/rows | Avoid full scans; design appropriate partition keys/indexes. |
| `ORDER BY value` is rejected | `value` is not a clustering column | Choose a table ordered for the query or sort at an appropriate layer. |
| `ReadTimeout` despite having full partition key | Hot/large partition, slow replica, SSTables/tombstones/GC/network | Check partition size, CL, node health, compaction, and targeted tracing. |
| `Unavailable` at `LOCAL_QUORUM` | Insufficient available replicas for RF/DC/CL | Inspect keyspace replication, topology, and internode networking; do not lower CL arbitrarily. |
| Results look different after upsert | Same primary key, cell timestamps, or concurrent writes | Inspect fixture data, write timestamps, TTL, and write semantics. |
| Java connects but some queries lose nodes | Driver discovery, native endpoint, topology/routing | Check `broadcast_rpc_address`, local DC, TLS/auth, and per-node logs. |
| Reading the right partition still has high latency | Many SSTables, wide partition, large rows, or system load | Monitor p95/p99, metrics, compaction, and bucket design. |

### 11.1. Slow query analysis checklist

1. **Right table/keyspace?** Do `DESCRIBE TABLE` and metadata match the query's schema?
2. **Full partition key?** For composite keys, are **all components** present with matching data types?
3. **Valid clustering predicates?** Do they follow the clustering prefix and form a contiguous slice?
4. **Partition width?** Is there a hot device or an oversized daily bucket?
5. **RF/CL and replicas?** Which nodes/DCs receive the request, and what is the state of gossip and internode links?
6. **Memtable/SSTable?** Are file counts, compactions, tombstones, caches, or disk I/O abnormal?
7. **Client?** Is the Java Driver properly using prepared statements, local DC, page size, and timeouts?
8. **Controlled measurement:** measure repeatedly on a representative dataset rather than drawing conclusions from a single trace.

## 12. Self-practice exercises

1. State the difference between `PRIMARY KEY (a, b, c)` and `PRIMARY KEY ((a, b), c)`. Explicitly identify the partition key and clustering columns.
2. Create `primary_index_lab.events_by_device_day` and the sample data. Use `DESCRIBE TABLE` to verify the composite partition key.
3. Run a `SELECT` filtering on both `device_id` and `event_day`. List the three rows in `event_time DESC` order and explain why global sorting is not needed.
4. Add `event_time >= '2026-11-21T01:05:00Z'`; predict the row count and explain the range role of the first clustering column.
5. Query using the complete primary key of the `01:05` row and confirm only one row is returned.
6. Remove the `event_day` predicate; record the cqlsh error and explain why `device_id` alone cannot compute the composite partition token.
7. Omit `event_time` while filtering on `event_id`. Why does the clustering order not support the desired lookup path?
8. Try a `SELECT` on the regular column `event_type` without a secondary index. Compare it with a partition-keyed query and state the risks of `ALLOW FILTERING`.
9. Use `system_schema.columns` to list `kind`, `position`, and `clustering_order`. Explain the role of these fields.
10. Draw the path client → coordinator → token/replica → memtable/SSTable and state what a Bloom filter can and cannot definitively conclude.
11. Explain why a single partition can span multiple SSTables and why compaction affects read performance without altering the primary key.
12. Design a table supporting the query "latest 20 temperature events for a site on a given day" without creating oversized partitions. State your traffic/bucketing assumptions.
13. Compare primary indexing, 2i, and SAI; clarify why SAI availability depends on version and why secondary indexes do not automatically solve hotspots.
14. Run the Java Driver query for `sensor-01` with a range on `event_time`; explain the difference between Java statement CL and the `CONSISTENCY` command in cqlsh.

**Completion criteria:** Given a `CREATE TABLE` statement, you can accurately identify partition/clustering keys; explain why keyed queries outperform scans/filtering and write valid point/range queries; understand that the primary index is maintained automatically with version-dependent SSTable structures; and assess the impact of hot/large partitions when modeling data for Cassandra.

## References

- [Apache Cassandra — Indexing concepts](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/indexing/indexing-concepts.html): primary indexing based on partition keys, secondary index 2i, and SAI.
- [Apache Cassandra — Data Definition (DDL)](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/ddl.html): `PRIMARY KEY`, composite partition keys, clustering columns, and `CLUSTERING ORDER BY`.
- [Apache Cassandra — Data Manipulation (DML)](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html): `WHERE` rules, clustering ranges, `ORDER BY`, `TOKEN`, `IN`, and `ALLOW FILTERING`.
- [Apache Cassandra — Storage Engine](https://cassandra.apache.org/doc/latest/cassandra/architecture/storage-engine.html): commit log, memtable, SSTables, Bloom filters, partition index, and Big Trie variants.
- [Apache Cassandra — Bloom Filters](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/bloom_filters.html): excluding SSTables during partition-key reads and false-positive probability.
- [Apache Cassandra — nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): inspecting `tablestats`, `tablehistograms`, and `compactionstats`.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): `CqlSession`, prepared statements, consistency, and paging.
