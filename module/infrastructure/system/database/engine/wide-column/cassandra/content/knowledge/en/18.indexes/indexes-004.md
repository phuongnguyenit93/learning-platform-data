# CREATE/DROP INDEX and Observing Readiness

## 1. Why is a successful CREATE INDEX statement not enough?

In Apache Cassandra, the **primary index** is formed from the table's **partition key**: the system uses tokens to locate replicas and then uses clustering keys to scan rows within a partition. When an application needs to query by **non-primary-key** columns, Cassandra can provide **secondary indexes**. Adding an index impacts the schema, read/write paths, compaction, internode networking, and how Java applications execute CQL.

`CREATE INDEX` is only the **beginning of the index lifecycle**. If the table already holds data, Cassandra must still build lookup structures for existing data across the relevant nodes. When deploying to a multi-node cluster, distinguish:

1. **Schema has recorded the index**: definition is visible in `system_schema.indexes`.
2. **Schema agreement**: nodes agree on the same schema change version.
3. **Index build/query readiness**: the index over existing data has been built, and the nodes needed to serve queries are ready.
4. **Verified performance and correctness**: queries return expected results at real CL within acceptable latency and load limits.

The first three milestones **do not automatically prove the fourth**. Furthermore, `DROP INDEX` removes the secondary query path: the base table remains intact, but `WHERE indexed_column = ?` queries may **stop being valid**. Consequently, both creating and dropping an index are schema changes that must be coordinated with the application.

This lesson belongs to the **Indexes** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It connects partition keys, query-driven table design, replication, consistency, compaction, repair, Cassandra errors, and the Java Driver into a verifiable index management workflow.

**Learning outcomes:**

- Write `CREATE INDEX`, `DROP INDEX`, `IF NOT EXISTS`, and `IF EXISTS` accurately in context.
- Distinguish primary index, legacy 2i, SAI, and version-specific limitations.
- Query `system_schema.indexes` metadata; inspect SAI with `system_views.indexes` and node-local metrics on Cassandra 5.x.
- Build a CQL lab with data inserted **before creating the index** to observe backfill/build requirements.
- Verify index readiness across **all nodes the application may contact**, not just one coordinator.
- Design safe deployment, testing, query cutover, drop, and rollback steps.
- Diagnose `InvalidRequest`, not-yet-queryable, `Unauthorized`, timeout, and Java connectivity errors.

## 2. Distinguish index types before writing DDL

| Type | How it is formed | Access mechanism | Use CREATE/DROP INDEX? |
| --- | --- | --- | --- |
| **Primary index** | Automatic from the table's `PRIMARY KEY` | Partition key/token; clustering rows inside a partition | **No**, not created with `CREATE INDEX`. |
| **2i, legacy secondary index** | Legacy secondary index; maintained as a local hidden index table per node | May require multi-node coordination when querying without partition key | **Yes**, with version-dependent syntax/defaults. |
| **SAI, Storage-Attached Index** | Column-level index attached to memtables/SSTables, built into **Apache Cassandra 5.0+** | Supports compatible multi-predicate/range queries via index query planner | **Yes**, specify `USING 'sai'` on supporting versions. |
| **SASI, SSTable-Attached Secondary Index** | Legacy custom index with its own implementation and modes | Experimental feature, **not recommended for production** | Has custom syntax, but do not enable just for this lesson. |

**Version constraints:** upstream Apache Cassandra 3.x/4.x provides 2i, whereas **SAI is integrated starting in 5.0**. Cassandra-compatible distributions may differ in features, defaults, or support; verify against your exact running server. SASI is not equivalent to SAI and is not a default choice for new designs.

In Cassandra 5.x, `default_secondary_index` and guardrails can govern which index type is created when `CREATE INDEX` **omits `USING`**. Therefore, when documentation or migrations require a specific index type, **explicitly declare the implementation if your version supports it** and always verify metadata after creation. A name like `status_idx` does not indicate whether it is 2i or SAI.

### 2.1. An index does not mean every query is fast

An index helps select candidate rows by a column. It does **not** automatically:

- Turn `status` into the base table's partition key.
- Guarantee `WHERE status='OK'` reads little data when `OK` matches most of the table.
- Create cluster-wide ordering for `ORDER BY event_time`.
- Eliminate replica/consistency, tombstone, network, or read repair costs.
- Replace **partition/bucket** design, hot-partition prevention, and controlling rows per partition.

When queries generally know the full partition key, prefer primary-key access over adding a secondary index.

## 3. CREATE INDEX syntax: choosing the right target and version

### 3.1. Common forms

~~~sql
-- General syntax template, NOT runnable before a table exists.
CREATE INDEX IF NOT EXISTS index_name
ON keyspace_name.table_name (column_name);

-- Only on Apache Cassandra 5.x with SAI.
CREATE INDEX IF NOT EXISTS index_name
ON keyspace_name.table_name (column_name)
USING 'sai';

-- Legacy type only when the running version supports the implementation name.
CREATE INDEX IF NOT EXISTS index_name
ON keyspace_name.table_name (column_name)
USING 'legacy_local_table';
~~~

Explanation:

- `index_name`: index name **unique within the keyspace**; two different indexes in the same keyspace cannot share a name.
- `keyspace_name.table_name`: existing table with a valid target column.
- `column_name`: indexed column. Each SAI index applies to **one column**; filtering across multiple columns requires following multi-SAI index rules.
- `IF NOT EXISTS`: prevents an error if an index with the same name already exists, but **does not compare or alter implementation/options**; never rely on it to confirm the system matches expected config.
- `USING 'sai'`: requests SAI and runs only on servers that actually support it.
- `USING 'legacy_local_table'`: explicitly declares the legacy type on supporting versions. On Cassandra 4.x you may need standard 2i syntax and post-creation metadata checks.

In Cassandra 5.0, `CREATE INDEX` can take extra options such as `WITH OPTIONS` for SAI. For instance, `case_sensitive`, `normalize`, and `ascii` affect text matching semantics. **Do not change these options without understanding their effect on query results and index rebuildability.**

### 3.2. Which targets can be indexed?

Not all columns or operators are supported equally. Examples:

| Case | Consideration before creating |
| --- | --- |
| `text`, `int`, `double`, `timestamp` columns | Typically indexable depending on implementation/version. |
| Single-column partition key | Primary index already optimizes lookups; SAI disallows indexing a **single-column partition key**. |
| One component of a composite partition key | SAI 5.x can support indexing a component, but evaluate real query behavior. |
| Clustering/regular/static columns | Check index-type restrictions; do not assume identical semantics across all column kinds. |
| `list/set/map` collections | `KEYS`, `VALUES`, `ENTRIES`, `FULL` syntax depends on data/index type; verify version docs. |
| `counter` | SAI indexes are not supported on counter columns. |
| Non-frozen UDT | SAI has explicit restrictions; do not assume all UDT forms are indexable. |

Errors such as `InvalidRequest` or `Cannot create index` at this stage are typically **schema/feature/constraint** errors, not index build or node failure issues. Read the server error message before reaching for "increase timeout."

### 3.3. DROP INDEX syntax

~~~sql
-- Names are scoped to the keyspace, not the table.
DROP INDEX IF EXISTS keyspace_name.index_name;
~~~

`DROP INDEX` removes the **index definition and structures**, not the base table or its rows. `IF EXISTS` prevents errors when the index does not exist, but **does not prove dropping it won't break applications**. Once the index is gone, requests relying on that indexed predicate may fail with `InvalidRequest`.

**Never use `DROP TABLE` to remove an index.** `DROP TABLE` destroys the application's schema and data; its blast radius is completely different from `DROP INDEX`.

## 4. Timeline: metadata → schema agreement → index build → queryable

~~~mermaid
flowchart TD
    DDL["CREATE INDEX sent to Cassandra"] --> SCHEMA["Schema contains index"]
    SCHEMA --> AGREEMENT["Verify schema agreement across nodes"]
    SCHEMA --> BUILD["Build index over existing data"]
    BUILD --> READY{"Index queryable on relevant nodes?"}
    READY -->|"No"| OBS["Monitor logs, status, errors; do not shift traffic"]
    OBS --> BUILD
    READY -->|"Yes"| CHECK["Compare results via primary key + indexed query"]
    AGREEMENT --> CHECK
    CHECK --> PERF["Load test, check CL/replicas, latency & rollback"]
    PERF --> SWITCH["Controlled traffic cutover"]
~~~

Branches may proceed in parallel; this is a **logical runbook**, not a fixed internal execution sequence for every implementation.

### 4.1. "Present in system_schema" is only definition state

~~~sql
SELECT keyspace_name, table_name, index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_ops_lab';
~~~

This metadata table lists declared indexes in the keyspace (once created in the lab). It does not provide a uniform, reliable `is_queryable` column across all 2i and SAI types. Inspect `kind`/`options` against the index type and version to identify 2i vs. SAI.

**Do not equate:** `DESCRIBE TABLE` printing `CREATE INDEX` ≠ historical data index build is finished on every node.

### 4.2. What is schema agreement?

After DDL, nodes exchange schema metadata. **Schema agreement** means the cluster shares a consistent view of the **schema definition**. However, it:

- Does not prove all data replicas are synchronized.
- Does not guarantee every background index build has finished.
- Does not prove every Java Driver session has refreshed its schema metadata.
- Does not prove indexed queries meet SLAs at real CL and concurrency.

From an authorized administrative node:

~~~bash
nodetool describecluster
nodetool status
~~~

`nodetool describecluster` displays schema version groups, while `nodetool status` reports cluster health from the queried node's perspective. To confirm index readiness, **still monitor builds and test real queries**.

### 4.3. Indexes on populated tables require backfill/build

When creating an index **on a table that already contains data**, Cassandra must build index entries for existing rows. Per Apache docs:

- 2i uses a **background index build** without blocking base table reads/writes for the entire duration.
- SAI builds index components across SSTables and memtables; for existing data, wait until the index status is **queryable**.
- New writes after index creation are handled by the implementation's write/index maintenance path.
- Build duration scales with data volume, SSTable count, disk/CPU capacity, ongoing compaction, and node health.

Never send queries relying on a new index to production the instant DDL returns success. Set up a **monitored readiness wait phase** with explicit completion criteria instead of a fixed sleep.

## 5. Two observation sources: system_schema and system_views

### 5.1. system_schema.indexes: all declared index types

~~~sql
-- Schema metadata, usable when your version provides this system_schema table.
SELECT index_name, table_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_ops_lab';
~~~

In the lab examples this will list `events_2i` and/or `events_sai`. If an expected index name does not appear, verify:

1. Are you connected to the intended cluster/port/native endpoint (`SHOW HOST`)?
2. Are keyspace/table/index names spelled accurately?
3. Did DDL fail due to permissions, syntax, index restrictions, or default index type?
4. Has a node/schema not yet observed the change?

The presence of a metadata row only confirms **the index is declared**. Do not treat metadata row counts as the number of replicas that finished building.

### 5.2. SAI 5.x: system_views.indexes for runtime state

On Apache Cassandra 5.0+, SAI provides the **`system_views.indexes`** virtual table. Inspect its schema first:

~~~sql
DESCRIBE TABLE system_views.indexes;

-- Exact key of the virtual table: keyspace_name + index_name.
SELECT keyspace_name, index_name, table_name, column_name,
       is_building, is_queryable, indexed_sstable_count,
       per_column_disk_size, per_table_disk_size
FROM system_views.indexes
WHERE keyspace_name = 'index_ops_lab'
  AND index_name = 'events_sai_status_idx';
~~~

Key columns:

| Column | Meaning | Must not be inferred |
| --- | --- | --- |
| `is_building` | Whether the node records an active index build | `false` **alone does not prove** the index is queryable. |
| `is_queryable` | Whether the index can serve queries on the queried node | Does not prove all other nodes are ready. |
| `indexed_sstable_count` | Number of SSTables actually containing indexed data | Does not equal total table SSTables if some SSTables lack indexed data. |
| `per_column_disk_size` | Disk size of the index portion specific to this column | Not the total table disk size. |
| `per_table_disk_size` | Disk size of shared table-level index components | Do not multiply/sum blindly across multiple indexes on the same table. |
| `column_name`/`table_name` | Identifies the index's column/table | Does not confirm permissions or query shape are valid. |

**Node-local perspective:** this virtual table reflects the node serving the CQL statement. In a multi-node cluster, check **every native endpoint that can receive relevant queries** or use centralized per-node-labeled monitoring. Seeing `true` from one contact point does not mean all replicas finished building.

If your Cassandra version lacks this virtual table or columns, **do not create extra tables** or try to edit `system_views` directly: verify the server version, implementation, and virtual table schema of your running release.

### 5.3. Why not use system_views.indexes to check 2i?

`system_views.indexes` is documented for **SAI**, not as a universal status API for all 2i and SASI implementations. For legacy 2i:

- Query `system_schema.indexes` to verify DDL/type.
- Monitor build messages, logs, and metrics from **each node** holding the index.
- Verify schema agreement and node health; check `nodetool`.
- Run indexed queries **validated against base data** after build completion, in a lab or under controlled traffic.
- If a rebuild is necessary, use `nodetool rebuild_index` per runbook; **do not treat rebuild as mandatory after every CREATE INDEX**.

One indexed query returning 2 expected rows in a single-node lab **does not prove** builds completed across a multi-node cluster. Inspect every relevant node or centralized observability source.

## 6. Shared lab: preparing a partition-keyed table and deterministic data

### 6.1. Prerequisites

Examples use a **single-node Cassandra lab** with `cqlsh` and privileges to create schemas/indexes. The 2i branch works on 4.x/5.x after checking defaults; the SAI branch **runs only on Apache Cassandra 5.0+**.

From a terminal:

~~~bash
cqlsh 127.0.0.1 9042
~~~

In cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS index_ops_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS index_ops_lab.events_2i (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  status text,
  temperature double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

DESCRIBE TABLE index_ops_lab.events_2i;
~~~

`SimpleStrategy`/RF = 1 serves a **non-fault-tolerant** lab. Multi-datacenter production typically uses `NetworkTopologyStrategy` and per-DC RF; never copy this lab setup as a production default.

**Table design:** composite partition key `(device_id, event_day)` serves single-device, single-day queries; clustering `(event_time, event_id)` supports chronological reads. `status` is a regular column and does not automatically provide primary-index lookups.

### 6.2. Insert fixtures before creating the index

~~~sql
INSERT INTO index_ops_lab.events_2i
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'OK', 24.2);

INSERT INTO index_ops_lab.events_2i
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'WARN', 30.8);

INSERT INTO index_ops_lab.events_2i
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:03:00Z',
        33333333-3333-4333-8333-333333333333, 'WARN', 28.5);

INSERT INTO index_ops_lab.events_2i
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-03', '2026-11-21', '2026-11-21T01:07:00Z',
        44444444-4444-4444-8444-444444444444, 'OK', 25.0);
~~~

Fixed UUIDs/UTC timestamps ensure **re-runs upsert the same rows** instead of adding duplicate-key rows. If the table already contains other data, do not assume exactly four rows exist; verify table contents and fixture state. `IF NOT EXISTS` does not alter an existing table with a different schema.

Baseline query, **no index required**:

~~~sql
CONSISTENCY ONE;

SELECT event_time, status, temperature
FROM index_ops_lab.events_2i
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

Expect `01:05 WARN 30.8` then `01:00 OK 24.2`. This is a clean access path via partition/clustering keys.

### 6.3. Before indexing, querying by status may be rejected

~~~sql
-- Execute ONLY BEFORE creating the index in the lab.
-- Valid SELECT syntax, but no lookup path exists for the regular column.
SELECT device_id, event_day, event_time, status
FROM index_ops_lab.events_2i
WHERE status = 'WARN';
~~~

Without an index on `status`, Cassandra typically returns `InvalidRequest` or a filtering warning. Do not fix it by adding `ALLOW FILTERING` in production. This is a **negative test** showing how an index changes query capability.

## 7. Branch A: creating and verifying legacy 2i

### 7.1. Check version, pick the right syntax

**On Cassandra 4.x** with traditional 2i, for example:

~~~sql
CREATE INDEX IF NOT EXISTS events_2i_status_idx
ON index_ops_lab.events_2i (status);
~~~

**On Cassandra 5.x** and versions supporting explicit implementation names, to avoid relying on defaults:

~~~sql
-- Run INSTEAD OF the CREATE INDEX above, not both.
CREATE INDEX IF NOT EXISTS events_2i_status_idx
ON index_ops_lab.events_2i (status)
USING 'legacy_local_table';
~~~

**Choose exactly one branch** matching your server version. If you run both statements, `IF NOT EXISTS` skips the second rather than "converting the index type." To verify:

~~~sql
DESCRIBE TABLE index_ops_lab.events_2i;

SELECT index_name, table_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_ops_lab'
  AND table_name = 'events_2i';
~~~

Inspect `kind`/`options` to confirm the actual index type, especially on Cassandra 5.x where default settings can vary.

### 7.2. After CREATE INDEX: when is it usable?

Because four rows were written **before** creating the index, the system must index the existing data. With 2i, building runs in the background; `CREATE INDEX` returning does not substitute for build verification.

In the single-node lab, after the build finishes and queries are ready:

~~~sql
SELECT device_id, event_day, event_time, status, temperature
FROM index_ops_lab.events_2i
WHERE status = 'WARN';
~~~

Expect **2 rows**: `sensor-01` at `01:05` and `sensor-02` at `01:03`. The order across two different partitions **is not guaranteed**.

Do not assume a single successful `SELECT` right after creating an index means the index is complete across every node in a production cluster. On multi-node clusters, check logs/builds/health per node and validate across multiple representative partitions.

### 7.3. Writing more data after the index exists

~~~sql
INSERT INTO index_ops_lab.events_2i
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-04', '2026-11-21', '2026-11-21T01:09:00Z',
        55555555-5555-4555-8555-555555555555, 'WARN', 31.0);

SELECT device_id, event_time, status
FROM index_ops_lab.events_2i
WHERE status = 'WARN';
~~~

Expect **3 rows** once the write is reflected at the lab's CL. Cassandra maintains the index automatically for new writes. In real clusters with concurrent writers and RF > 1, account for CL and replica readiness before concluding "every node observes the same state."

### 7.4. Observing the impact of UPDATE on an indexed column

~~~sql
UPDATE index_ops_lab.events_2i
SET status = 'OK'
WHERE device_id = 'sensor-02'
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T01:03:00Z'
  AND event_id = 33333333-3333-4333-8333-333333333333;

SELECT device_id, event_time, status
FROM index_ops_lab.events_2i
WHERE status = 'WARN';
~~~

Expect `sensor-02` **no longer in the `WARN` results**, while `sensor-01` and `sensor-04` still match. Read by primary key if you need to cross-check the row. Updating/deleting indexed columns incurs maintenance and tombstone overhead, especially with 2i on high-churn data.

## 8. Branch B: SAI on Apache Cassandra 5.0+

### 8.1. Create a separate lab table

**Skip all of section 8 if running upstream Cassandra 3.x/4.x.** SAI is integrated starting in Apache Cassandra 5.0 and uses dedicated syntax.

~~~sql
CREATE TABLE IF NOT EXISTS index_ops_lab.events_sai (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  status text,
  temperature double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

-- Insert data before CREATE INDEX to observe index build.
INSERT INTO index_ops_lab.events_sai
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'WARN', 30.8);

INSERT INTO index_ops_lab.events_sai
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:03:00Z',
        33333333-3333-4333-8333-333333333333, 'WARN', 28.5);

INSERT INTO index_ops_lab.events_sai
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-03', '2026-11-21', '2026-11-21T01:07:00Z',
        44444444-4444-4444-8444-444444444444, 'OK', 25.0);
~~~

### 8.2. Create SAI and inspect status

~~~sql
-- Apache Cassandra 5.0+.
CREATE INDEX IF NOT EXISTS events_sai_status_idx
ON index_ops_lab.events_sai (status)
USING 'sai';

-- Can also index a numeric column when the workload needs ranges.
CREATE INDEX IF NOT EXISTS events_sai_temperature_idx
ON index_ops_lab.events_sai (temperature)
USING 'sai';

-- Verify the indexes exist in the schema.
SELECT index_name, table_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_ops_lab'
  AND table_name = 'events_sai';

-- Inspect virtual table structure on the running version.
DESCRIBE TABLE system_views.indexes;
~~~

Specific status check:

~~~sql
SELECT index_name, table_name, column_name, is_building, is_queryable,
       indexed_sstable_count
FROM system_views.indexes
WHERE keyspace_name = 'index_ops_lab'
  AND index_name = 'events_sai_status_idx';

SELECT index_name, table_name, column_name, is_building, is_queryable
FROM system_views.indexes
WHERE keyspace_name = 'index_ops_lab'
  AND index_name = 'events_sai_temperature_idx';
~~~

In a multi-node cluster, check this state **per node**. If `is_queryable = false`, the index cannot yet serve queries using it. Even if `is_building = false` while `is_queryable = false`, investigate—never assume "not building" equals ready.

### 8.3. Run queries only after SAI is queryable

~~~sql
-- Two WARN rows in the events_sai fixture.
SELECT device_id, event_time, status, temperature
FROM index_ops_lab.events_sai
WHERE status = 'WARN';

-- Both predicates have SAI; only sensor-01 matches temperature >= 30.
SELECT device_id, event_time, status, temperature
FROM index_ops_lab.events_sai
WHERE status = 'WARN'
  AND temperature >= 30.0;
~~~

Expected results:

| Query | Results on `events_sai` |
| --- | --- |
| `status = 'WARN'` | 2 rows: `sensor-01`, `sensor-02`. |
| `status = 'WARN' AND temperature >= 30` | 1 row: `sensor-01`, `30.8`. |

Each SAI index covers one column; the engine can coordinate multiple indexed predicates within a compatible query. **Do not use `LIKE '%text%'` to demonstrate SAI 5.0**, because `LIKE` is unsupported by SAI per official docs.

### 8.4. What are the impacts of adding or dropping an SAI index?

- The base table continues serving queries that **do not depend on the index**.
- When recreating SAI on a populated table, wait for build/queryable across the relevant nodes.
- SAI indexes have index components attached to SSTables; flush/compaction and incoming writes affect index component lifecycles.
- After `DROP INDEX`, queries relying solely on that index can no longer remain a working API unless another access path exists.

Do not treat `DROP` followed by `CREATE` as an "instant index fix" in busy production: the transition window can cause application errors and rebuilding consumes disk/CPU.

## 9. DROP INDEX: safe order before and after removal

### 9.1. Pre-drop procedure

Never run `DROP INDEX` directly just because an index doesn't show up in one test query. A solid checklist:

1. **Inventory** all queries/services/jobs using the indexed column; watch out for dynamic CQL and internal jobs.
2. Confirm an **alternative query path**: partition key, materialized/query-oriented table, another appropriate SAI, or search service.
3. Deploy updated clients / feature flags and verify zero requests still depend on the old index.
4. Monitor query patterns, error rates, latency, and index metrics on a representative cluster.
5. Snapshot schema metadata, recording the exact **index name + options** so it can be recreated on rollback.
6. Schedule a maintenance window/approval if dropping impacts multiple services or a rollback rebuild would be heavy.

### 9.2. Testing DROP in the lab

After completing all checks in Branch A:

~~~sql
-- Drops only the events_2i lab index.
DROP INDEX IF EXISTS index_ops_lab.events_2i_status_idx;

SELECT index_name, table_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_ops_lab'
  AND table_name = 'events_2i';

-- Base table remains intact and partition-key queries still work.
SELECT event_time, status, temperature
FROM index_ops_lab.events_2i
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

**Once the schema converges**, querying `events_2i` solely by `status='WARN'` returns an error because no index exists. This is **expected lab behavior**, not data loss:

~~~sql
-- Negative test: this query now requires an index or another access strategy.
SELECT device_id, event_time, status
FROM index_ops_lab.events_2i
WHERE status = 'WARN';
~~~

For the separate SAI branch, if testing drop on Cassandra 5.x:

~~~sql
-- Only after capturing metadata and verifying impact.
DROP INDEX IF EXISTS index_ops_lab.events_sai_temperature_idx;

-- The status index still exists; status-only queries remain supported.
SELECT device_id, event_time, status
FROM index_ops_lab.events_sai
WHERE status = 'WARN';
~~~

**Do not assume** `WHERE status='WARN' AND temperature>=30` stays allowed or efficient as before, because one predicate no longer has an index. On Cassandra 5.x, the planner may require filtering or return `InvalidRequest`. Never blindly add `ALLOW FILTERING` to keep a service running without measuring cost.

### 9.3. Rollback is not a magical "IF NOT EXISTS"

If an index is dropped by mistake or rollback is needed:

1. Use the saved `CREATE INDEX` definition with the **exact implementation and options**.
2. Confirm no index with the same name and different config exists.
3. Recreate the index and wait for schema agreement + build/queryable.
4. Verify results by primary key, sample indexed values, and CL.
5. Only after all gates pass should traffic be routed back.

Putting `IF NOT EXISTS` in the recreate statement **does not instantaneously restore index data**. The index must rebuild over existing rows, which on large clusters can generate substantial load.

## 10. When to use nodetool rebuild_index?

For 2i / native secondary indexes, Cassandra provides an administrative command:

~~~bash
# Illustrative ONLY; do not run outside a lab or approved runbook.
# Syntax: nodetool rebuild_index <keyspace> <table> <indexName...>
nodetool rebuild_index index_ops_lab events_2i events_2i_status_idx
~~~

This command can perform a **hot rebuild of a native secondary index** on the node contacted by `nodetool`. Because `nodetool` uses the administrative/JMX channel (commonly port 7199 when configured), it is **distinct from native CQL port 9042**.

**Do not run `rebuild_index` as a default step after `CREATE INDEX`.** Cassandra builds indexes automatically. Consider rebuilding only when there is evidence of a corrupted/out-of-sync node-local index and your version's runbook permits it. Rebuilding consumes CPU/disk/compaction; plan node by node with monitoring, disk headroom, load checks, and rollback.

Also distinguish:

- **`nodetool repair`**: synchronizes **replica data** across token ranges via anti-entropy.
- **`nodetool rebuild_index`**: rebuilds a **native secondary index** on a specific node.
- **`nodetool compact`**: runs SSTable compaction per supported operation.
- **`DROP/CREATE INDEX`**: changes the **index schema** (creating/removing index structures), which can affect client queries.

Never swap these commands arbitrarily just because a `SELECT` returns `ReadTimeout`.

## 11. Why readiness must account for RF, CL, and topology

Suppose a cluster has one datacenter with RF = 3. At `LOCAL_QUORUM`, each normal read/write requires responses from a **quorum of replicas in the local DC** (typically 2 when RF = 3). However, a secondary index query **without a partition key** may search across many token ranges and nodes: the number of nodes participating in the index search can **differ** from the replica count for a single partition.

One node reporting `is_queryable=true` may not represent the remaining nodes. When a distributed index query runs:

- The coordinator must query data across the relevant nodes/ranges.
- If a replica is unavailable, `Unavailable` or timeouts can occur depending on CL and cluster state.
- If SAI is not yet queryable on a required node, the query may fail or be unable to use the index path.
- Checking results on only one node can miss incomplete builds on other nodes.
- If a Java application discovers peers and routes requests to multiple coordinators, verify all native endpoints and the local DC.

**Deployment rule:** in multi-node clusters, **tie index status to node, keyspace, index name, and check timestamp**. Never equate "one query succeeded" with "every replica is complete."

## 12. Operational runbook: CREATE → READY → SWITCH → DROP

| Phase | Tasks | Gate condition |
| --- | --- | --- |
| **Pre-CREATE** | Finalize query patterns, server versions, DC/RF/CL, schema, index type, capacity, service owner | Valid data model, DDL permissions, and approved change plan. |
| **CREATE** | Run CQL with explicit implementation and unique name; log DDL timestamp | No permission/type/guardrail errors. |
| **SCHEMA** | Inspect `system_schema.indexes` and schema agreement | All nodes received the right definition; no wrong index type. |
| **BUILD** | Check logs/builds; for SAI check `system_views.indexes` per node | Index is queryable on all required nodes with no build errors. |
| **VALIDATE** | Cross-check indexed queries against primary-key queries / base dataset | No missing/wrong rows; key update/delete/TTL cases verified. |
| **LOAD TEST** | Test key distribution, common/rare selectivity, p95/p99, CPU/GC, disk/compaction, network | Within SLOs, no abnormal overload or timeouts. |
| **SWITCH** | Enable new query via feature flag / canary | Acceptable client metrics and error rates; rollback ready. |
| **DROP OLD** | Prove zero remaining dependencies, then drop legacy index | New query stable, schema backed up, recovery plan ready. |
| **POSTCHECK** | Check schema, client connections, query errors, and disk metrics | System stable; results and lessons documented. |

### 12.1. Monitoring load during the build phase

| Metric group | What to watch |
| --- | --- |
| **Index state** | `is_building`/`is_queryable` for SAI, 2i logs, index build errors. |
| **CPU/GC** | Increased load from index building / SSTable scans, GC pauses, and queues. |
| **Disk** | Free space, index size, write/read I/O, compaction backlog. |
| **Native latency** | p50/p95/p99 read/write latency, timeouts/retries, request throughput. |
| **Internode** | Messages/bytes, down nodes, or packet loss. |
| **Consistency** | RF/CL, `Unavailable`, `ReadTimeout`, `WriteTimeout`. |
| **Data correctness** | Primary-key vs. indexed query comparisons sampled across different partitions/keys. |

Never apply a fixed threshold like "index build always finishes in N minutes" across clusters. The goal is **measurable readiness criteria**, not waiting an arbitrary estimated duration.

## 13. Java Driver 4.x: how applications should handle index changes

Java applications send CQL over the native protocol; **indexes are server-side schema objects**, not something the driver creates via prepared statements. The snippet below assumes the `events_sai` lab on Cassandra 5.x is **already queryable**, or can be adapted to `events_2i` with an active index.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Duration;

public final class CassandraIndexReadinessDemo {
    public static void main(String[] args) {
        String host = System.getenv().getOrDefault("CASSANDRA_HOST", "127.0.0.1");
        String dc = System.getenv().getOrDefault("CASSANDRA_DC", "datacenter1");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .build()) {

            PreparedStatement byIndex = session.prepare(
                "SELECT device_id, event_time, status, temperature " +
                "FROM index_ops_lab.events_sai WHERE status = ?");

            BoundStatement query = byIndex.bind("WARN")
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(100)
                .setTimeout(Duration.ofSeconds(5));

            int rowCount = 0;
            for (Row row : session.execute(query)) {
                rowCount++;
                System.out.println(row.getString("device_id") + " : " +
                    row.getDouble("temperature"));
            }
            System.out.println("matching_rows=" + rowCount);
        } catch (RuntimeException error) {
            // Do not log passwords, tokens, or sensitive bind values.
            System.err.println("query_failed_type=" +
                error.getClass().getName());
            throw error;
        }
    }
}
~~~

**Conditions:**

- `events_sai` exists only if you ran the Cassandra 5.x branch; use `events_2i` and the legacy index if running the Cassandra 4.x lab.
- `datacenter1` is an example; fetch the actual DC name from `SELECT data_center FROM system.local;`.
- TLS/credentials are omitted assuming a local lab without auth. Real environments must configure SSL/CA, authentication, contact points, and CQL permissions.
- `setConsistencyLevel(ONE)` and `setTimeout(5s)` are statement settings for illustration, **not production defaults**.
- `setPageSize(100)` controls only page size, not proving total matching rows or cluster fan-out is capped at 100.
- `PreparedStatement` can be impacted by schema changes; after a drop, queries relying solely on an indexed column may be rejected at prepare or execution time. Never retry the same failing query endlessly.

### 13.1. Avoiding race conditions during rollout

If a service deploys new code **before** the index is queryable, requests can fail even though the schema already lists the index name. Safe sequence:

1. Guard new queries behind a **feature flag** so they are not sent automatically.
2. DBAs/operators complete schema/build/readiness across all relevant nodes.
3. Run smoke tests using the application's actual identity/TLS/CL and compare against base data.
4. Enable canary traffic, monitoring error rates and latency.
5. Ramp traffic gradually once results stabilize.

After dropping an old index, re-enable queries depending on it only after **recreating and completing the build**, not merely because an operator ran `CREATE INDEX`.

## 14. Diagnosing errors by stage

| Symptom | Issue category | How to check |
| --- | --- | --- |
| `CREATE INDEX` throws `SyntaxException` | Syntax/version | `SHOW VERSION`, index name/`USING` clause, and server version docs. |
| `InvalidRequest: index already exists` | DDL/index name | Index name is keyspace-unique; read metadata before using `IF NOT EXISTS`. |
| `CREATE INDEX ... USING 'sai'` rejected on 4.x | Unsupported feature | Upstream SAI starts in 5.0; use 2i or query-driven table design. |
| `Unauthorized` on CREATE/DROP | DDL permissions | Inspect roles/authorizer; never disable authentication. |
| Index in `system_schema.indexes` but query fails | Build incomplete or incompatible type | For SAI check `system_views.indexes` per node; for 2i check logs/build status. |
| `is_building=false, is_queryable=false` | SAI cannot serve queries | Inspect server logs, disk, build failures, node health; do not mark READY. |
| Index query works on node A but fails on node B | Inconsistent readiness or schema/topology mismatch | Check each node, schema agreement, versions, and cluster health. |
| Post-drop query returns `InvalidRequest` | Missing indexed access path | Identify remaining callers on old query; switch data model or roll back. |
| `ReadTimeout` / `DriverTimeoutException` | Replica/fan-out/overload | Check CL/RF, network, index selectivity, CPU/disk/compaction, retries. |
| `Unavailable` | Insufficient replicas available for CL | `nodetool status`, replication settings, DC, internode network. |
| `AllNodesFailedException` in Java | Native connection failure | Check DNS, port 9042, TLS/auth, contact points, local DC before blaming the index. |
| Common status query slow despite SAI queryable | Low selectivity, large result set | Measure matching rows, p95/p99, and cost; consider a query-oriented table. |
| DDL blocked by guardrail | Operational/feature limit | Check default index type, max indexes per table, column types, and version policy. |

### 14.1. Two common misconceptions

**"I see the index in DESCRIBE so it's ready"** — false: `DESCRIBE` shows schema, not local index build completion on every node.

**"After DROP INDEX I can still SELECT by partition key so apps aren't affected"** — incomplete: only queries not relying on the index remain unaffected; APIs executing `WHERE status=?` can fail immediately once the schema updates.

## 15. Practice exercises

1. Distinguish primary index, 2i, and SAI. Why is `CREATE INDEX` not used for the primary key?
2. Create `index_ops_lab.events_2i`, insert four rows **before** creating the index, try `status='WARN'`, and record the error.
3. Run the version-appropriate legacy `CREATE INDEX`. Use `system_schema.indexes.kind/options` to verify which type was actually created.
4. Explain the three states—**schema exists**, **schema agreement**, and **index build/queryable**—and why they are not identical.
5. After 2i finishes building, query `status='WARN'`: predict the two rows. Insert `sensor-04 WARN` and verify how the index updates.
6. Update `sensor-02 WARN→OK`. Use both primary-key and indexed queries to compare, and discuss write amplification/tombstones.
7. On an Apache Cassandra 5.0+ lab, create `events_sai` and two SAI indexes; inspect `is_building`/`is_queryable` in `system_views.indexes`.
8. Why does `is_queryable=true` on one node not prove the entire cluster is ready? Propose how to gather per-node-labeled status.
9. Run the SAI query `status='WARN' AND temperature>=30`. Verify the expected row and explain how two column-level indexes coordinate.
10. Test `DROP INDEX` on the 2i lab, verify table/data remain intact, and confirm the `status` query fails as expected.
11. Outline a rollback plan if a production index still used by a service was accidentally dropped: stopping failing queries, recreating the index, waiting for build, and verifying.
12. Compare `nodetool rebuild_index`, `nodetool repair`, and `DROP/CREATE INDEX`. Why are they not interchangeable?
13. Draft an operational checklist before creating an index on a table with tens of millions of rows: disk space, node count, CL/RF, maintenance window, metrics, and retries.
14. Using Java Driver 4.x with prepared `WHERE status=?`, explain why clients must wait for rollout readiness before enabling new queries.
15. Diagram a CI/CD or change-management pipeline with **CREATE → BUILD → VERIFY → CANARY → SWITCH → DROP OLD**, specifying the gate condition for each phase.

**Completion criteria:** You can create/drop indexes with the right type and version, inspect schema metadata, understand that schema agreement does not mean build completion, verify SAI queryability per node and 2i via build/log/query validation, and execute safe traffic cutover/rollback without losing tables or causing unexpected query failures.

## Official references

- [Apache Cassandra — CREATE INDEX](https://cassandra.apache.org/doc/stable/cassandra/reference/cql-commands/create-index.html): index syntax, `IF NOT EXISTS`, `USING 'sai'`, and data type limits.
- [Apache Cassandra — DROP INDEX](https://cassandra.apache.org/doc/stable/cassandra/reference/cql-commands/drop-index.html): `DROP INDEX IF EXISTS keyspace.index` syntax.
- [Apache Cassandra — Secondary Indexes](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexes.html): index types, async builds, and `legacy_local_table`.
- [Apache Cassandra — Rebuilding and maintaining 2i](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/operations/2i-build.html): background builds and hot rebuilds via nodetool.
- [Apache Cassandra — SAI concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-concepts.html): memtable/SSTable attachment and query planner.
- [Apache Cassandra — Monitor SAI indexes](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/operations/monitoring.html): `is_queryable`, `is_building`, and node-local state.
- [Apache Cassandra — SAI virtual tables](https://cassandra.apache.org/doc/stable/cassandra/reference/sai-virtual-table-indexes.html): `system_views.indexes` structure and index metrics.
- [Apache Cassandra — nodetool rebuild_index](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): rebuild index syntax and node scope.
- [Apache Cassandra — Indexing concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/indexing-concepts.html): choosing among primary/2i/SAI.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): sessions, prepared statements, consistency, timeouts, and metadata.
