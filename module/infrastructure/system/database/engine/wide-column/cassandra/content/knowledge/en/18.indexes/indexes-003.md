# Comparing 2i, SASI, and SAI by Version and Support Status

## 1. Why check the version before choosing an index?

Apache Cassandra is a **distributed wide-column** database optimized for queries that locate data via the **partition key** and then filter/scan **clustering columns** within the partition. In practice, applications also need to search data by non-key columns, such as `status = 'WARN'`, `temperature >= 30`, or names starting with a prefix.

Three names are easily confused:

- **2i**: *legacy secondary index*, the traditional secondary index maintained on each node as a local hidden index table.
- **SASI**: *SSTable-Attached Secondary Index*, a custom index implementation attached to SSTable structures that previously supported prefix/substring and range queries, but **is classified by Apache Cassandra as an experimental feature and not recommended for production**.
- **SAI**: *Storage-Attached Indexing*, a modern indexing mechanism integrated into **Apache Cassandra 5.0**, with read/write paths attached to memtables/SSTables and support for multi-index query planning.

**SASI and SAI are not two spellings of the same feature.** SASI refers to the `org.apache.cassandra.index.sasi.SASIIndex` implementation with modes such as `PREFIX`, `CONTAINS`, and `SPARSE`. SAI is a new implementation with a different indexing/query engine, created via `USING 'sai'` on supported Cassandra versions. Nor can you assume every SASI capability—especially `LIKE '%...%'`—exists in SAI.

This lesson belongs to the **Indexes** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Index choice directly impacts query-driven table modeling, partition sizing, coordinator/replica latency, replication/consistency, compaction/repair, and how Java applications issue CQL.

**After this lesson, you will be able to:**

1. Read a version matrix and distinguish **present in source**, **creatable**, **recommended**, and **production-supported**.
2. State the architectural, operator, and limitation differences among **2i, SASI, and SAI**.
3. Create/inspect 2i in a general lab; run SAI examples **only on compatible Cassandra 5.x**; recognize SASI opt-in requirements and risks.
4. Explain fan-out cost when the partition key is omitted and why an index does not replace query-driven table design.
5. Verify actual index types via `system_schema.indexes`, server version, and configuration instead of guessing by name.
6. Plan migrations from 2i/SASI to SAI or new query tables with correctness, latency, data consistency, and rollback criteria.
7. Write Java Driver prepared statements matching the right query shape without relying on false assumptions about index support.

## 2. Understanding what "supported" really means

A feature may **exist in the source code**, have a documentation page, and still **not be recommended for production environments**. Therefore, separate at least four states:

| State | Question to verify | Meaning |
| --- | --- | --- |
| **Implementation exists** | Is the JAR/class/index type present in the server build? | Does not prove the feature is enabled or stable. |
| **Creation allowed** | Do CQL, `cassandra.yaml`, guardrails, and DDL permissions allow creating the index? | May work in a lab, not necessarily approved for production deployment. |
| **Documented** | What does documentation for the exact **version and distribution** say? | Docs may describe experimental use or legacy compatibility. |
| **Operationally supported** | Does the vendor/distribution commit to support, upgrades, backup, repair, and rebuild? | Must check the policy of the specific system you run. |

**Specifically regarding SASI:** Apache Cassandra's documentation still describes `SASIIndex`, yet the `sasi_indexes_enabled` setting is explicitly marked **experimental** and **not recommended for production use**. The existence of a SASI documentation page does not make it a safe choice for new investments.

### 2.1. Practical matrix for Apache Cassandra

| Apache Cassandra version | Primary indexing | Legacy 2i | SASI | SAI |
| --- | --- | --- | --- | --- |
| **3.11** | Yes | Yes | SASI implementation exists in relevant 3.x branches; verify build/config and experimental policy | **No built-in SAI like Apache 5.0** |
| **4.0** | Yes | Yes | SASI is an experimental feature; verify toggle/config in the specific patch | **No built-in SAI like Apache 5.0** |
| **4.1** | Yes | Yes | `sasi_indexes_enabled` is documented as **false by default**, experimental, not recommended for production | **No built-in SAI like Apache 5.0** |
| **5.0** | Yes | Yes for legacy compatibility | SASI docs/code remain, but marked experimental; disabled by default in documented config | **Built-in SAI**, the preferred direction for many secondary indexing queries |

This matrix describes **upstream Apache Cassandra** and does not replace compatibility matrices for DataStax Enterprise, Astra DB, ScyllaDB, internal forks, or managed Cassandra-compatible services. Another product may offer SAI prior to Cassandra 5.0 or impose its own syntax/limits: **never infer feature versions solely from the Cassandra API name**.

For newer releases or experimental branches, always read the specific release documentation at deployment time. Never assume a feature "available in 5.0" will retain identical options, defaults, or syntax forever.

### 2.2. Do not infer index type solely from `CREATE INDEX`

On Cassandra 5.x, settings such as `default_secondary_index` can determine the implementation when `CREATE INDEX` **omits `USING`**. Compatibility configurations often document `legacy_local_table`, whereas a differently configured cluster may pick another default type.

Therefore:

- If you intend **2i**, check the resulting index type after creation and the cluster default; on supporting versions, specify the implementation explicitly when needed.
- If you intend **SAI**, specify `USING 'sai'` in CQL and verify that your Cassandra version supports it.
- If you are studying **SASI**, run `CREATE CUSTOM INDEX ... USING 'org.apache.cassandra.index.sasi.SASIIndex'` only in a lab where opt-in is explicitly permitted.
- `IF NOT EXISTS` does not confirm an existing index has the **expected type and options**; always inspect metadata afterward.

## 3. Architectural comparison: where does indexed data live?

~~~mermaid
flowchart TB
    APP["Java Driver / cqlsh"] --> CO["Coordinator: parses query"]
    CO --> R["Responsible replica/node"]
    R --> BASE["Base table: memtable + SSTables"]
    R --> I2["2i: hidden local index table"]
    R --> IS["SASI: SSTable / memtable-attached index"]
    R --> IA["SAI 5.x: SSTable + memtable-attached index"]
    I2 -.->|"Lookup candidate primary keys"| BASE
    IS -.->|"Lookup candidate primary keys"| BASE
    IA -.->|"Lookup candidate primary keys"| BASE
~~~

This diagram **illustrates three selectable implementation paths**; it does not mean a single table should enable all three index types simultaneously. In the labs below, each type uses a **separate table** to avoid conflicts and isolate behavior.

### 3.1. Legacy 2i: hidden index table on each node

2i is maintained locally on each node holding base table data. A node uses the index to find candidate keys and then reads/verifies rows from the base table. Because the index is not centralized, queries that **know only a secondary column** without a **partition key** can force the coordinator to search across many nodes and token ranges.

Key points:

- 2i remains a distributed index in terms of **query scope**, even though its structures are stored **locally on each node**.
- Very common values like `status='OK'` can produce massive matching sets.
- Frequently updated/deleted columns incur extra index maintenance and tombstones.
- Apache documentation recommends using 2i **when the partition key is known**, rather than as a general substitute for primary-key queries.

### 3.2. SASI: SSTable-attached index, still experimental

SASI (*SSTable-Attached Secondary Index*) is implemented as a custom index leveraging structures on memtables/SSTables and specialized on-disk search indexes. Documentation describes these modes:

| SASI Mode | Query idea | Warning |
| --- | --- | --- |
| `PREFIX` | Prefix of a text value, e.g., `LIKE 'Over%'` | Depends on analyzer, case sensitivity, and implementation. |
| `CONTAINS` | Substring/suffix search per analyzer capabilities, e.g., `LIKE '%heat%'` | Can increase storage footprint; not equivalent to full-text search. |
| `SPARSE` | Optimized for numeric/range data with specific distributions | Not a universal speedup for all range queries. |

SASI can support certain queries that 2i does not serve conveniently, but that **does not remove its experimental label**. A fast query on a 100-row lab does not prove SASI is production-ready regarding stability, correctness under deletes/updates, streaming, rebuilds, upgrades, or long-term support.

**Operational conclusion:** treat SASI as a **legacy/experimental feature to understand or maintain older systems**, not a default choice for new Apache Cassandra designs.

### 3.3. SAI: new mechanism integrated with the storage engine

In Apache Cassandra 5.0, SAI indexes memtables and SSTables per column, keeping index data co-located on the same node as the data. At query time, the coordinator can orchestrate distributed range reads, evaluate selectivity, and replicas can **combine predicates across multiple SAI indexes**.

Advantages noted in SAI documentation:

- Indexes follow the SSTable **flush/compaction** lifecycle rather than living in a separate hidden table like 2i.
- Supports **equality and range** predicates on documented types; allows multiple indexed predicates in a single supported query.
- Exposes **index build state/metrics**, with streaming and rebuild tied to cluster operations.
- Supports multiple column types such as numeric, text, UUID, date/timestamp, and collections according to SAI-specific rules.

**Do not assume:** "SAI has zero write amplification," "SAI guarantees every query hits 1 node," or "SAI replaces Elasticsearch/Lucene for all search types." SAI still consumes CPU/RAM/disk, index builds, and distributed coordination; it is a **filtering/indexing engine** and does not impose a global result sort order.

## 4. Query capability matrix: the three types are not equivalent

| Requirement | 2i | SASI | Apache 5.x SAI | Recommendation |
| --- | --- | --- | --- | --- |
| `status = 'WARN'` | Yes on indexed column | Yes when feature enabled | Yes | Prefer primary key / query-driven table; use SAI if secondary filtering is needed on 5.x. |
| `temperature >= 30.0` | Do not treat 2i as a general range solution | Has numeric/range modes depending on config | Supports numeric ranges | Verify column type/operators against your version. |
| `note LIKE 'Over%'` | Not a basic 2i capability | Possible with SASI PREFIX | **SAI does not support LIKE** | Avoid assuming SASI → SAI migration keeps the same query text. |
| `note LIKE '%heat%'` | Not a basic 2i capability | Possible with SASI CONTAINS | **SAI does not support LIKE** | If true substring/full-text search is needed, evaluate a search engine or another model. |
| `status='WARN' AND temperature>=30` | Combining multiple 2i is limited, may require filtering | Supports compound predicates depending on syntax/options | SAI can combine multiple SAI indexes | Benchmark selectivity and returned row count. |
| Lookup by partition key + clustering range | **Primary index suffices** | Unnecessary | Unnecessary | Avoid adding redundant indexes. |
| **Cluster-wide** ordered Top-N | Not solved automatically | Not solved automatically | Not solved automatically | Requires table/bucket/index ordering or a dedicated aggregation layer. |
| Scanning/aggregating nearly the whole table | Not an ideal workload | Not an ideal workload | Not an ideal workload | Use batch analytics/ETL or summary tables. |

The limits above describe only the **representative feature set**. For example, text tokenization/analyzers, collection `CONTAINS`, `IN`, AND/OR, and vector search depend on the exact CQL/SAI version and data types. Do not infer from CQL collection `CONTAINS` that SAI supports **text substring search** like SASI `LIKE '%...%'`.

### 4.1. Cardinality and selectivity matter more than index name

Suppose a table has 10 million rows:

- `status='OK'` matches **9.8 million rows**: an index can still lead to huge result sets and heavy reads.
- `status='WARN'` matches **200 rows**: an index has a better chance of narrowing results, though the coordinator may still need to probe many data ranges.
- `request_id` is nearly unique: if this is the primary access path, a direct **partition key** is usually far more cost-predictable than a 2i on a UUID.
- `note LIKE '%error%'`: if free-text search is a core workflow, separately analyze tokenizer semantics, ranking, language rules, and update rate.

There is no universal rule like "low cardinality always suits 2i" or "SAI is always fast at any selectivity." Measure **per-value matching fraction**, returned row count, p95/p99, network fan-out, storage footprint, and write/update overhead.

## 5. Before writing DDL: verify version and configuration

### 5.1. Check server/cqlsh versions

From a terminal with `cqlsh`:

~~~bash
cqlsh 127.0.0.1 9042
~~~

In cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

SELECT cluster_name, data_center, release_version
FROM system.local;
~~~

`SHOW VERSION` displays the connected cqlsh/server/CQL/native protocol versions. `release_version` from `system.local` is the version of **the node serving the SELECT**, which does not prove every node in the cluster runs the same version during a rolling upgrade.

### 5.2. Inspect index metadata in the schema

~~~sql
-- Run after creating the lab keyspace/tables/indexes in subsequent sections.
SELECT keyspace_name, table_name, index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_versions_lab';
~~~

`kind` and `options` report the implementation/index options recorded by Cassandra in the schema; **representation varies across versions**. Do not rely solely on a name like `status_idx` or `IF NOT EXISTS` to conclude whether an index is 2i or SAI.

### 5.3. Check `cassandra.yaml` and guardrails

| Setting to inspect | Question to verify |
| --- | --- |
| `sasi_indexes_enabled` | In Cassandra 4.1/5.0 docs: SASI is experimental, **false by default**, not recommended for production. |
| `default_secondary_index` | On supporting versions: when `USING` is omitted, does it create 2i or SAI? |
| `default_secondary_index_enabled` | Does the cluster permit `CREATE INDEX` without `USING`, or require explicit implementation? |
| SAI guardrails | Max SAI indexes per table, indexable types/options, query limits, and resource quotas. |
| DDL permissions | Does the role have `CREATE` permission on the relevant keyspace/index resource? |
| Mixed versions | Have all nodes finished upgrading and do they all support the new index type and schema? |

Do not **enable SASI simply because a lesson provides an example**. If your organization disallows it, read the SASI section as **theory** and run only the 2i or SAI labs. Modifying `cassandra.yaml` and performing rolling restarts are outside this lesson's scope and require approved operational procedures.

## 6. Base lab: shared table and data for comparison

**Safety conditions:** an isolated lab cluster with no production data. The examples create an RF=1 keyspace with `SimpleStrategy` solely for easy **single-node** practice; they do not model multi-datacenter replication or fault tolerance.

Create the keyspace:

~~~sql
CREATE KEYSPACE IF NOT EXISTS index_versions_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};
~~~

Sample dataset:

| record | device_id | event_day | event_time UTC | status | temperature | note |
| --- | --- | --- | --- | --- | ---: | --- |
| 1 | sensor-01 | 2026-11-21 | 01:00 | OK | 24.2 | Normal |
| 2 | sensor-01 | 2026-11-21 | 01:05 | WARN | 30.8 | Overheat motor |
| 3 | sensor-02 | 2026-11-21 | 01:03 | WARN | 28.5 | Overflow pump |
| 4 | sensor-03 | 2026-11-21 | 01:07 | WARN | 31.2 | Overheat valve |

**Functional expectation:** `status='WARN'` matches 3 records, while `status='WARN' AND temperature >= 30` matches 2 records (sensor-01 and sensor-03). Do not infer a global ordering among records belonging to different partitions.

### 6.1. Table definition for 2i

~~~sql
CREATE TABLE IF NOT EXISTS index_versions_lab.events_2i (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  status text,
  temperature double,
  note text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

In this table, `(device_id, event_day)` is the **composite partition key**; `event_time` and `event_id` are clustering columns. `status`, `temperature`, and `note` are regular columns; without an index, you cannot expect to filter on them across all partitions at point-lookup cost.

### 6.2. Insert four rows with deterministic primary keys

~~~sql
INSERT INTO index_versions_lab.events_2i
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111,
        'OK', 24.2, 'Normal');

INSERT INTO index_versions_lab.events_2i
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222,
        'WARN', 30.8, 'Overheat motor');

INSERT INTO index_versions_lab.events_2i
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:03:00Z',
        33333333-3333-4333-8333-333333333333,
        'WARN', 28.5, 'Overflow pump');

INSERT INTO index_versions_lab.events_2i
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-03', '2026-11-21', '2026-11-21T01:07:00Z',
        44444444-4444-4444-8444-444444444444,
        'WARN', 31.2, 'Overheat valve');
~~~

Fixed UUIDs/timestamps ensure re-runs **upsert** the same primary keys rather than creating new rows. If the table already exists with a different schema, `IF NOT EXISTS` does not alter it; inspect `DESCRIBE TABLE` before running. If the lab already holds leftover rows outside the fixture, total row counts may differ; reset data only in an **isolated lab** under safety policy.

Baseline check **without using a secondary index**:

~~~sql
CONSISTENCY ONE;

SELECT event_time, status, temperature
FROM index_versions_lab.events_2i
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

Expected two rows for `sensor-01`: `01:05 WARN` then `01:00 OK`. This is the preferred query pattern when the application knows the partition key.

## 7. Lab branch A: legacy 2i (available across versions)

### 7.1. Create the index and verify its type

~~~sql
-- On Cassandra 4.x: plain CREATE INDEX is typically legacy 2i.
-- On 5.x: check default_secondary_index; do not guess from DDL alone.
CREATE INDEX IF NOT EXISTS events_2i_status_idx
ON index_versions_lab.events_2i (status);

DESCRIBE TABLE index_versions_lab.events_2i;

SELECT index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_versions_lab'
  AND table_name = 'events_2i';
~~~

If Cassandra 5.x is configured with `default_secondary_index: sai` or requires an explicit `USING` clause, the statement above **is no longer guaranteed to create a 2i**. On versions supporting explicit index type declarations:

~~~sql
-- Use ONLY if your Cassandra version supports this implementation name,
-- and only on a separate lab table without a conflicting index name/column.
-- Reference syntax for Apache Cassandra 5.x:
CREATE INDEX IF NOT EXISTS explicit_legacy_status_idx
ON index_versions_lab.events_2i (status)
USING 'legacy_local_table';
~~~

**Choose one of the two creation approaches**—never run both on the same column just to "be sure." If the wrong type was created, verify its type first, `DROP INDEX` the lab index cleanly, and recreate it in a controlled manner.

### 7.2. Querying via the local index

~~~sql
SELECT device_id, event_day, event_time, status, temperature
FROM index_versions_lab.events_2i
WHERE status = 'WARN';
~~~

Once the index finishes building over existing data, expect **3 rows**, possibly in varying order across runs or clusters. In a multi-node cluster, the coordinator may query many local indexes; a low returned row count **does not guarantee** low total message or network volume.

Testing a single partition combined with an index predicate:

~~~sql
SELECT event_time, status
FROM index_versions_lab.events_2i
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND status = 'WARN';
~~~

Providing the full partition key clearly narrows the scope. If your planner/Cassandra version requires additional filtering, check the rules and consider querying solely by partition key and filtering the small row set in the application. Do not add `ALLOW FILTERING` arbitrarily in production.

### 7.3. Limitations of 2i

- `status='WARN' AND temperature>=30` does not automatically become an intersection of two indexes simply by creating two legacy 2i indexes.
- Indexes are maintained on nodes holding the data and typically require reading base rows to validate candidates.
- Updating/deleting indexed columns incurs maintenance and tombstone overhead.
- Highly skewed data (`status='OK'` matching 98% of rows) or wide partitions can make queries slow.
- Index DDL on a populated table triggers a **build process**; schema presence alone does not prove every node has finished building.

**Do not use an RF=1 lab to conclude 2i performs well on a multi-node cluster.** The lab primarily verifies query syntax and semantics, not benchmark performance.

## 8. Lab branch B: SASI (reading or strictly controlled experiment only)

### 8.1. Status warning

SASI may appear in source/binaries and 4.1/5.0 documentation, yet `cassandra.yaml` docs explicitly list **`sasi_indexes_enabled: false` by default** and label the feature experimental, **not recommended for production**. This lesson **does not instruct enabling SASI on any cluster serving real data**.

If your environment disallows `SASIIndex`, **skip all CQL in section 8**—you can still complete the lesson using the comparison matrix and 2i/SAI labs. Do not edit `cassandra.yaml` or restart nodes just to run this example.

### 8.2. Separate lab table and PREFIX example

**Run only if** administrators have prepared an **isolated lab cluster** with SASI permitted and your Cassandra build includes the implementation:

~~~sql
CREATE TABLE IF NOT EXISTS index_versions_lab.events_sasi (
  event_id uuid PRIMARY KEY,
  note text,
  temperature double
);

CREATE CUSTOM INDEX IF NOT EXISTS events_sasi_note_idx
ON index_versions_lab.events_sasi (note)
USING 'org.apache.cassandra.index.sasi.SASIIndex'
WITH OPTIONS = {'mode': 'PREFIX'};

INSERT INTO index_versions_lab.events_sasi (event_id, note, temperature)
VALUES (55555555-5555-4555-8555-555555555555,
        'Overheat motor', 30.8);

INSERT INTO index_versions_lab.events_sasi (event_id, note, temperature)
VALUES (66666666-6666-4666-8666-666666666666,
        'Overflow pump', 28.5);

INSERT INTO index_versions_lab.events_sasi (event_id, note, temperature)
VALUES (77777777-7777-4777-8777-777777777777,
        'Normal', 24.2);

-- SASI PREFIX: LIKE prefix query on supporting versions.
SELECT event_id, note
FROM index_versions_lab.events_sasi
WHERE note LIKE 'Over%';
~~~

Expect two rows—`Overheat motor` and `Overflow pump`—**provided SASI is enabled, the index is built, and the analyzer/options match**. Row return order does not imply a global sort.

For **substring** searches like `'%heat%'`, SASI offers a `CONTAINS` mode on a separate index (not merely adding `LIKE` onto a PREFIX index). Verify the exact mode/analyzer, cost, and limitations of your running version. Do not mix other index types on the same table for direct comparison.

### 8.3. SASI is not SAI

Common pitfalls:

1. Seeing a class name containing `SASIIndex` and thinking the server supports `USING 'sai'` — **false**.
2. Seeing that SAI also attaches to SSTables and assuming SAI supports `LIKE 'Over%'` — **incorrect per Apache 5.0 documentation**.
3. Seeing SASI still documented in 5.0 and treating it as a production-stable feature — **false due to its experimental status**.
4. Using tiny data / low concurrent writes to claim SASI is fast or free of tombstone/rebuild overhead — **unsubstantiated**.
5. Enabling the SASI option on a single node in a multi-node cluster without rollout/config checks — **schema and stability risk**.

## 9. Lab branch C: SAI (Apache Cassandra 5.x+ only)

### 9.1. Prerequisites

**Do not run these commands on upstream Apache Cassandra 4.0/4.1/3.11**, because SAI was integrated in Cassandra 5.0. If using another distribution that provides SAI, consult that distribution's documentation instead of assuming identical syntax/operators.

Create a separate table without 2i/SASI:

~~~sql
CREATE TABLE IF NOT EXISTS index_versions_lab.events_sai (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  status text,
  temperature double,
  note text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

CREATE INDEX IF NOT EXISTS events_sai_status_idx
ON index_versions_lab.events_sai (status)
USING 'sai';

CREATE INDEX IF NOT EXISTS events_sai_temperature_idx
ON index_versions_lab.events_sai (temperature)
USING 'sai';
~~~

**Result:** each SAI index is a per-column index. Two indexes on two columns of the same table can be combined in a single query with supported `AND` predicates, unlike the false assumption that "two legacy 2i indexes always intersect automatically."

### 9.2. Insert data with the same semantics as the 2i lab

~~~sql
INSERT INTO index_versions_lab.events_sai
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111,
        'OK', 24.2, 'Normal');

INSERT INTO index_versions_lab.events_sai
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222,
        'WARN', 30.8, 'Overheat motor');

INSERT INTO index_versions_lab.events_sai
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:03:00Z',
        33333333-3333-4333-8333-333333333333,
        'WARN', 28.5, 'Overflow pump');

INSERT INTO index_versions_lab.events_sai
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-03', '2026-11-21', '2026-11-21T01:07:00Z',
        44444444-4444-4444-8444-444444444444,
        'WARN', 31.2, 'Overheat valve');
~~~

### 9.3. SELECT using one and two SAI indexes

~~~sql
-- Equality: expect 3 rows.
SELECT device_id, event_time, status, temperature
FROM index_versions_lab.events_sai
WHERE status = 'WARN';

-- Two indexed predicates: expect 2 rows.
SELECT device_id, event_time, status, temperature
FROM index_versions_lab.events_sai
WHERE status = 'WARN'
  AND temperature >= 30.0;

-- Numeric range via SAI: expect 2 rows.
SELECT device_id, temperature
FROM index_versions_lab.events_sai
WHERE temperature >= 30.0;
~~~

These statements require **Cassandra 5.x after index build completion**. Do not use return order to claim `sensor-03`'s partition precedes `sensor-01`'s: clustering order applies only within a partition, not across all partitions cluster-wide.

**Mandatory negative test:**

~~~sql
-- WARNING: query intentionally unsupported by SAI text index.
-- SAI does not support LIKE per Cassandra 5.0 documentation.
SELECT device_id, note
FROM index_versions_lab.events_sai
WHERE note LIKE 'Over%';
~~~

In this table `note` does not even have an SAI index; even if you created an SAI index on `note`, **`LIKE` remains unsupported according to SAI 5.0 documentation**. Do not explain away this error as "forgot to enable `ALLOW FILTERING`" and run a full scan in production.

### 9.4. Verifying that the index is queryable

Cassandra 5.x provides a virtual table for inspecting SAI state:

~~~sql
DESCRIBE TABLE system_views.indexes;

SELECT keyspace_name, table_name, index_name, is_queryable, is_building
FROM system_views.indexes
WHERE keyspace_name = 'index_versions_lab'
  AND table_name = 'events_sai';
~~~

If your Cassandra version lacks `system_views.indexes` or has different columns, inspect `DESCRIBE` and version-specific docs. `is_queryable` and `is_building` are documented in SAI reference docs to distinguish "index exists in schema" from "index is ready on the current node."

**The virtual table reflects the view of the node receiving the query.** On a multi-node cluster, check build state/metrics across the relevant nodes; one node reporting `is_queryable=true` does not prove the entire cluster is ready during a rollout.

## 10. Understanding operational costs across the data lifecycle

| Operation | 2i | SASI | SAI |
| --- | --- | --- | --- |
| **INSERT/UPDATE** | Maintains local hidden index table | Maintains SASI structures on memtable/SSTable | Maintains memtable indexes and SSTable-attached index data |
| **DELETE/TTL/tombstones** | Can leave stale candidates/tombstones, raising maintenance | Must evaluate SASI behavior and tombstone impact per version | Integrated read-path post-filtering/tombstone handling with SSTable lifecycle |
| **Build on populated table** | Background build on each node | Requires building SASI index when enabled | Index build with queryable/building status visibility |
| **Flush/compaction** | Hidden index has separate storage/compaction activity | Tied to flush/SSTable process per implementation | Index components follow SSTable/compaction lifecycle |
| **Bootstrap/streaming** | Must account for local index availability and rebuild procedures | Do not rely on experimental feature for new operational designs | SAI supports integrated streaming; verify in practice/version |
| **Backup/restore** | Cannot simply copy DDL and assume data and indexes are restored | Requires compatible runbook if still used | Index is attached to storage, yet still requires backup/restore and query verification |
| **Index drop** | Drops index, not base table | Drops custom index, not base table | Drops SAI, not base table |

An index does not automatically fix **replica data inconsistency**. `nodetool repair` synchronizes replicas; rebuilding an index is a separate operation. Never run `repair`/`compact`/`rebuild_index` indiscriminately just because one query is slow.

### 10.1. High-churn columns are a distinct challenge

Suppose `status` flips from `WARN` to `OK` dozens of times over a row's lifetime. Measure:

- Write cost and actual number of index updates.
- Size of SSTable/index components and compaction rate.
- Tombstones and the number of base rows re-verified.
- Query latency on a newly changed indexed value under your active CL.
- Behavior after TTL expiration/deletion, verifying queries do not return stale invalid rows.

Do not assume "SASI is SSTable-attached" or "SAI is modern" means updates/deletes are **free**. Correctness must still be validated under your application's replication and consistency settings.

## 11. Decision workflow for choosing an index

~~~mermaid
flowchart TD
    A["Is there a query by partition key?"] -->|"Yes"| B["Prefer primary indexing + clustering"]
    A -->|"No"| C{"Which Apache Cassandra version?"}
    C -->|"5.0 with SAI"| D{"Does SAI support operator + datatype?"}
    D -->|"Yes"| E["Test SAI on separate table, benchmark, verify queryable"]
    D -->|"No"| F["Design query-driven table / search service"]
    C -->|"3.x/4.x upstream"| G{"Does legacy 2i meet needs & benchmark acceptably?"}
    G -->|"Yes, bounded scope"| H["Controlled 2i + measure real load"]
    G -->|"No"| F
    C -->|"Existing SASI"| I["Experimental: legacy maintenance only, not default for new work"]
    I --> F
    E --> J["Review p95/p99, disk, build/repair, rolling upgrade"]
    H --> J
~~~

### 11.1. Technical evaluation checklist

Before proposing an index, answer:

1. **Business query**: what exact `WHERE` clauses and row counts are required? Is cluster-wide sorting mandatory?
2. **Version/distribution**: upstream Apache or managed/distribution? Does it provide the feature and production support?
3. **Selectivity**: how many rows match each value; which values are most frequent, and what is the cardinality?
4. **Partition key**: have you identified a partition/bucket? Could a query-oriented table replace an index?
5. **Write path**: update/delete/TTL frequency on the indexed column; are compaction backlog and index storage acceptable?
6. **RF/CL**: which local DC, how many replicas must respond, and what is current node/repair health?
7. **Operational readiness**: do runbooks exist for build/rebuild, streaming, backup/restore, rolling upgrades, and DDL permissions?
8. **SLA**: throughput, p95/p99, concurrent requests, timeouts, retry rate, and resource limits.
9. **Rollback**: if the index underperforms, does the application have an alternative query path before running `DROP INDEX`?

## 12. Migrating from 2i/SASI to SAI or query-driven tables

### 12.1. There is no "ALTER INDEX TYPE SASI TO SAI"

This is a **query strategy migration**, not flipping a flag to convert old index files into new ones. A safe plan:

1. **Inventory**: from schemas and logs, catalog index names, types/options, query patterns, dependent apps/users, and server versions.
2. **Verify target**: choose a Cassandra version supporting the target feature; complete upgrade/topology validation before creating new indexes.
3. **Use a separate test table/cluster**: load representative data; avoid mixing SAI and 2i on the same table if version docs advise against it.
4. **Create SAI or a query-oriented table**: index each column/predicate per the target version's rules.
5. **Wait for build completion and validate**: inspect `system_schema.indexes`, `system_views.indexes` if available, sample rows by primary key, and test indexed queries.
6. **Compare semantics**: notably, migrating `SASI LIKE 'prefix%'` or `'%substring%'` to SAI **is not equivalent** because SAI 5.0 does not support `LIKE`.
7. **Benchmark**: keep dataset, RF/CL, load, cache warmth, page size, and returned rows consistent; measure p50/p95/p99, CPU/GC, disk/network, and compaction.
8. **Roll out with rollback capability**: shift traffic only after preparing feature flags and a path back to the old query/table.
9. **Monitor post-rollout**: correctness, query timeouts, disk growth, per-node build/queryability, retries, and tail latency.
10. **Clean up legacy indexes**: `DROP INDEX` only after confirming **zero remaining dependent queries** and following change management.

### 12.2. Specific note when upgrading Cassandra 4.x → 5.x

A mixed-version cluster undergoing a rolling upgrade **is not automatically safe for creating new SAI schemas**. Every node must understand the new index type and schema; your upgrade plan must follow the version's documentation and orchestrator process. Never check `SHOW VERSION` on one coordinator and immediately create SAI in production while 4.x nodes remain.

If SAI cannot be used and you still need predicates outside the partition key, consider a query-driven table:

~~~sql
-- Illustrative alternative: find WARN by site + day.
-- Add shard if a partition gets too hot; requires shard/merge logic.
CREATE TABLE IF NOT EXISTS index_versions_lab.warn_by_site_day (
  site_id text,
  event_day date,
  shard smallint,
  event_time timestamp,
  device_id text,
  event_id uuid,
  temperature double,
  PRIMARY KEY ((site_id, event_day, shard),
               event_time, device_id, event_id)
) WITH CLUSTERING ORDER BY
  (event_time DESC, device_id ASC, event_id ASC);
~~~

This table fits only if the workload needs `WARN` per site/day and the pipeline **writes only WARN events**. It does not sync automatically from `events_2i`. If an event changes status, the application must handle updates/deletes on the secondary table, idempotency, and reconciliation. Sharding the partition key spreads load, but top-N queries across shards must merge results in the application.

## 13. Observing indexes and queries with cqlsh/nodetool

### 13.1. Metadata and index state

~~~sql
DESCRIBE KEYSPACE index_versions_lab;
DESCRIBE TABLE index_versions_lab.events_2i;

SELECT keyspace_name, table_name, index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_versions_lab';
~~~

For SAI on Cassandra 5.x:

~~~sql
-- Only when the server version exposes system_views.indexes.
DESCRIBE TABLE system_views.indexes;
SELECT keyspace_name, table_name, index_name, is_queryable, is_building
FROM system_views.indexes
WHERE keyspace_name = 'index_versions_lab'
  AND table_name = 'events_sai';
~~~

**Do not treat schema metadata as runtime status**: an index declared in the schema does not prove it has finished building on every replica. Virtual table values can be **node-local**; when troubleshooting a multi-node cluster, inspect all relevant nodes.

### 13.2. Controlled trace comparison

~~~sql
TRACING ON;

-- Baseline by partition key (no secondary index needed).
SELECT event_time, temperature
FROM index_versions_lab.events_2i
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';

-- Query via index without partition key.
SELECT device_id, event_time, temperature
FROM index_versions_lab.events_2i
WHERE status = 'WARN';

TRACING OFF;
~~~

Traces can show coordinator/replicas, remote requests, and stage timings, but **tracing adds overhead** and is not a neutral benchmark. Measuring latency without tracing on a larger workload is required for meaningful p95/p99 comparisons. Never leave tracing enabled across all production traffic.

Common commands from an administrative node:

~~~bash
nodetool status
nodetool describecluster
nodetool compactionstats
nodetool tablestats index_versions_lab.events_2i
~~~

`nodetool` typically uses the administrative/JMX port, not native port 9042. Commands may differ across versions; never run `rebuild_index` or major compaction just because an index query is slow. Identify the index type, build status, replica health, and root cause first.

### 13.3. Production-like test matrix

| Measurement group | Minimum scenarios |
| --- | --- |
| **Correctness** | Compare rows by primary key; update `WARN→OK`; delete; TTL expiration; read at real CL. |
| **Selectivity** | Rare `status='WARN'` vs. common `status='OK'`; ranges with varying match rates. |
| **Scalability** | Scale partition count, node count, and data size; measure remote requests and coordinator CPU. |
| **Write overhead** | INSERT/UPDATE/DELETE under realistic concurrency, compaction, and index disk growth. |
| **Recovery** | Index build/rebuild, node restarts, bootstrap/streaming, topology changes on a lab cluster. |
| **Client behavior** | Paging, timeouts, retry policies, driver local DC, TLS/auth, query cancellation. |
| **Long-running** | Run across flush/compaction/repair cycles and track p95/p99. |

No universal constant like "SAI is N times faster than 2i" applies to every system. Numbers must be tied to specific hardware, versions, workloads, and configurations.

## 14. Java Driver 4.x: indexes change schema, not the CQL API

The Java Driver still sends **prepared statements over the native protocol**. Index type is determined by server-side Cassandra schema, **not by the Java Driver choosing among 2i/SASI/SAI**. When changing index/query syntax, update application statements accordingly.

Example using the **general 2i lab**:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Duration;

public class IndexVersionQueryDemo {
    public static void main(String[] args) {
        String host = System.getenv().getOrDefault("CASSANDRA_HOST", "127.0.0.1");
        String dc = System.getenv().getOrDefault("CASSANDRA_DC", "datacenter1");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .build()) {

            PreparedStatement ps = session.prepare(
                "SELECT device_id, event_time, status, temperature " +
                "FROM index_versions_lab.events_2i " +
                "WHERE status = ?");

            BoundStatement query = ps.bind("WARN")
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(100)
                .setTimeout(Duration.ofSeconds(5));

            int rows = 0;
            for (Row row : session.execute(query)) {
                rows++;
                System.out.println(
                    row.getString("device_id") + " / " +
                    row.getInstant("event_time") + " / " +
                    row.getDouble("temperature"));
            }
            System.out.println("matching_rows=" + rows);
        }
    }
}
~~~

**Conditions:** 2i is created and fully built; TLS/auth are omitted to keep the lab concise. `datacenter1` is an **illustrative name**—retrieve your actual local DC from `SELECT data_center FROM system.local;`. Production systems must enable TLS/CA, credentials, timeouts, and organizational retry policies.

For SAI 5.x, `WHERE status = ? AND temperature >= ?` is a different statement against a different table (`events_sai`); ensure the proper SAI indexes exist. For SASI `LIKE`, the query runs only when SASI is permitted and cannot be copied verbatim to SAI 5.x with the same semantics.

**Results and latency:** a Java client running a 2i query may pick a coordinator that does not hold matching data; queries lacking a partition key generally cannot use token-aware routing to a single token. `setPageSize(100)` does not guarantee the query only scans/reads 100 rows total, and `setTimeout(5s)` is purely an example value. Measure and log error classes (without logging passwords or sensitive bind values) to distinguish `InvalidRequest`, `Unavailable`, server read timeouts, and driver timeouts.

## 15. Troubleshooting matrix by index type

| Symptom | Likely cause | Proper check |
| --- | --- | --- |
| Cassandra 4.1 rejects `USING 'sai'` | SAI is not built into upstream 4.1 | Check `SHOW VERSION` and server docs; use a query-oriented table or validated 2i. |
| SASI `CREATE CUSTOM INDEX` is rejected | Experimental feature disabled or disallowed by distribution | Check `sasi_indexes_enabled` and policy; do not enable in production to bypass the error. |
| `CREATE INDEX` without `USING` creates an unexpected type | `default_secondary_index` is configured | Inspect `system_schema.indexes.kind/options` and server config. |
| `LIKE` query works on SASI but fails on SAI | SAI 5.x does not support `LIKE` | Choose different query semantics or a search service; do not assume equivalence. |
| SAI index appears in schema but queries fail | Index still building / not yet queryable on node | Check `system_views.indexes` and per-node build metrics/logs. |
| 2i query without partition key is slow | Distributed fan-out, poor selectivity, or large dataset | Measure p95/p99, remote requests, result counts, topology/CL. |
| `status='OK'` is very slow while `WARN` is fast | `OK` matches most of the table | Measure matching fraction and consider an appropriate primary key/table. |
| Index maintenance causes write latency | Updates/deletes/tombstones, flush/compaction | Inspect CPU, disk, GC, compaction, and per-index metrics. |
| `Unavailable` at `LOCAL_QUORUM` | Insufficient replicas for keyspace RF/DC/CL | Check `nodetool status`, replication settings, and internode networking. |
| `ReadTimeout` on index query | Slow replica, wide fan-out, high cluster load | Targeted tracing, metrics, query selectivity, cluster health. |
| Java `AllNodesFailedException` | DNS/TCP/TLS/auth/peer discovery failure | Check native endpoints and driver local DC before blaming the index. |
| Application errors after `DROP INDEX` | Queries still depended on the dropped index | Inventory queries and roll out app changes before dropping; keep rollback ready. |
| `ALLOW FILTERING` lets query run but slowly | Permits broad read/filtering; creates no new index | Rewrite query around a partition or build a proper data model/index. |

## 16. Practice exercises and self-assessment

1. Distinguish **implementation exists**, **feature enabled**, and **production-recommended** using the SASI example.
2. Build a 2i/SASI/SAI comparison table for Cassandra 3.11, 4.1, and 5.0. Explain why SAI syntax cannot be brought into upstream 4.1.
3. In Cassandra 5.0, why is `CREATE INDEX ...` without `USING` insufficient to prove an index is legacy 2i?
4. Create `events_2i` and the four sample rows. Compare a partition-keyed query with a `status`-only query.
5. Query `system_schema.indexes` to distinguish index name, kind, and options. If an index was just created on a populated table, what additional state must you inspect?
6. Explain why 2i is stored locally yet queries without a partition key still cause coordinator fan-out.
7. Suppose `status='OK'` matches 98% of rows and `WARN` matches 0.01%. Analyze selectivity per value rather than by cardinality alone.
8. Review the SASI section and explain the difference between `PREFIX` and `CONTAINS`. Why shouldn't `sasi_indexes_enabled` be turned on lightly in production?
9. On a **5.x lab cluster with SAI**, create two SAI indexes on `events_sai` and run `status='WARN' AND temperature>=30`. Predict the two returned rows.
10. Test `LIKE 'Over%'` on the SAI lab and explain the operator limitation; why might migrating from SASI to SAI require rewriting queries?
11. Use `system_views.indexes` on 5.x to inspect `is_queryable` and `is_building`. Why must you observe every relevant node in a multi-node cluster?
12. Design a table to fetch the latest alerts by site/day without scanning the whole cluster. Address sharding/merging and updates when status changes.
13. Write a migration runbook from 2i/SASI to SAI covering inventory, lab setup, build, query validation, benchmarking, rollout/rollback, and dropping legacy indexes.
14. Use the Java Driver with a `WHERE status = ?` prepared statement and list latency contributors outside Java (replicas, coordinator, compaction, internode).
15. Propose when to drop all three index types in favor of ETL/analytics or a dedicated search engine.

**Completion criteria:** You can accurately read the **version/state matrix**, clearly distinguish 2i, SASI, and SAI in architecture and operators, practice on the lab branch matching your version, avoid confusing experimental SASI with stable SAI, and design safe migrations/queries grounded in evidence about data distribution, CL/RF, and cluster operations.

## Official references

- [Apache Cassandra — Indexing concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/indexing-concepts.html): primary index, secondary index 2i, and the SAI milestone in Apache Cassandra 5.0.
- [Apache Cassandra — 2i concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/2i-concepts.html): local indexes as hidden tables and impact on distributed queries.
- [Apache Cassandra — SASI Index](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/SASI.html): custom index, `SASIIndex`, `PREFIX`, `CONTAINS`, and `SPARSE`.
- [Apache Cassandra 4.1 — cassandra.yaml](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html): `sasi_indexes_enabled`, experimental status, and default false.
- [Apache Cassandra 5.0 — cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): SASI opt-in, `default_secondary_index`, and guardrails.
- [Apache Cassandra — SAI concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-concepts.html): read/write path on memtables/SSTables and combining indexed predicates.
- [Apache Cassandra — SAI FAQ](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-faq.html): supported operators (`LIKE` unsupported), indexed data, and `system_views.indexes`.
- [Apache Cassandra — SAI quickstart](https://cassandra.apache.org/doc/stable/cassandra/getting-started/sai-quickstart.html): creating and querying SAI on Cassandra 5.0.
- [Apache Cassandra — CREATE INDEX](https://cassandra.apache.org/doc/stable/cassandra/reference/cql-commands/create-index.html): `USING` syntax, index types, and limits.
- [Apache Cassandra — nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): inspecting nodes, compaction, and cluster status.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): sessions, prepared statements, paging, consistency, and timeouts.
