# Loading Data with cqlsh COPY, sstableloader, or Appropriate Bulk Tools in Apache Cassandra

> **Chapter:** Migration and Schema  
> **Scope:** Selecting and operating a strategy for loading data into Apache Cassandra based on source format (CSV/JSON, SSTables, event streams), volume, schema, partition keys, target topology, read/write consistency levels, and cluster capacity. This lesson uses CQL, CLI, and Java Driver 4.x examples; tool flags and syntax vary across versions, so always verify `--help` and the documentation of your deployed binary.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **logical bulk loading** (CSV/CQL mutations) from **physical SSTable streaming**, understanding how each affects timestamps, TTLs, tombstones, and replication.
2. Choose among `cqlsh COPY FROM`, `sstableloader`, DataStax Bulk Loader (DSBulk), Spark Cassandra Connector, Java Driver, and `nodetool import` based on source data, scale, and business requirements.
3. Prepare keyspaces/tables around **queries and partition keys**, verify types/primary keys/UDTs, set per-datacenter RF, and avoid hot/wide partitions before loading.
4. Write `COPY FROM/TO` examples for CSVs with headers, delimiters, NULLs, UUIDs, and timestamps; recognize quoting/encoding errors and CSV limitations.
5. Describe the pipeline for loading SSTables from snapshots/staging with `sstableloader`, including how it reads the ring and streams to natural replicas instead of running per-row `INSERT`s.
6. Design rate-limited batch loads with controlled retries, idempotency, checkpoints, dead-letter/quarantine queues, and observability.
7. Execute migrations following **backfill → catch-up → dual-write/CDC if needed → validation → cutover**, without overwriting valid newer mutations.
8. Validate data across multiple token ranges and datacenters using CQL, Java, and metrics, knowing when to stop, roll back, or perform a forward fix.

In the **`DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`** module, Cassandra is a **distributed wide-column database**: partition keys hash to tokens, the replication strategy selects replicas, and table design is tied directly to queries. Loading one million rows **does not** prove data is evenly distributed, read-efficient, or consistent. You must align the ingest path with **the query path and write path** first.

## 2. Understanding the three input data types

~~~text
                          DATA SOURCES
                               |
             +-----------------+------------------+
             |                 |                  |
        CSV / JSON /       SSTables from      Events / CDC /
        Parquet / RDBMS    Cassandra          source app
             |                 |                  |
        Must map types     SSTable format     Choose mutation
        & primary keys     /schema/partitioner semantics
             |                 |                  |
        COPY / DSBulk /    sstableloader      Driver / Spark /
        Spark / Java       (streaming)        custom pipeline
             |                 |                  |
             +-----------------+------------------+
                               |
                       CASSANDRA CLUSTER
              ring / RF / disk / compaction / CQL
                               |
                   BUSINESS DATA RECONCILIATION
~~~

**Logical loading** turns inputs into new CQL mutations, subject to `INSERT/UPDATE/DELETE` logic, declared write timestamps/TTLs, and live replication. **Physical SSTable loading** injects already-encoded SSTable data into the storage engine; existing timestamps, TTLs, and tombstones inside the files remain meaningful and do not turn into fresh CQL writes.

### 2.1. Bulk load goals differ from restore

| Goal | Example | Primary concern |
|---|---|---|
| **Initial seed** | Load 20 million CSV transactions into a new cluster | Schema, partition distribution, throughput, and complete key checks |
| **Historical backfill** | Load 2020–2024 orders into a table with live traffic | Avoid overwriting newer data, TTLs, cutoffs, dual-writes |
| **SSTable migration** | Move backups from a 3-node ring to a 5-node ring | SSTable compatibility, topology/RF, streaming |
| **Schema redesign** | From `orders_by_id` to `orders_by_customer_day` | Key transformation, fan-out, multi-table consistency |
| **Incremental catch-up** | Load mutations arriving after a snapshot | Ordering/version/idempotency, CDC retention |
| **Local node recovery** | Node lost a disk; SSTable copy exists for its ranges | Usually evaluate replace/rebuild/repair or local import |

Bulk loading from CSV is not a guaranteed way to undo accidental deletes; `COPY FROM` typically generates fresh timestamps and can **override tombstones or newer updates** unless designed against. Conversely, loading old SSTables may fail to surface rows masked by newer tombstones.

## 3. Tool selection matrix

| Tool | Input | Write mechanism | Best suited for | Main limitations |
|---|---|---|---|---|
| **`cqlsh COPY FROM`** | CSV (text) | CQL mutations across cluster | Small/medium datasets, PoCs, controlled imports | Not a large-scale ETL tool; limited error/type/TTL handling |
| **`cqlsh COPY TO`** | CQL table → CSV | Paged reads and serialization | Exporting small/medium datasets for inspection/labs | Not a cluster-wide consistent snapshot; drops SSTable metadata |
| **DataStax Bulk Loader (DSBulk)** | CSV/JSON and supported connectors | Parallelized CQL mutations | Larger datasets than COPY, clean mapping/logging, throttling | Still issues CQL writes; verify connector/version/auth/schema |
| **Spark Cassandra Connector** | Spark DataFrame: Parquet/JSON/JDBC/CSV… | Distributed reads/writes | Complex ETL/transformations, scale-out | Spark overhead, shuffles, skew, version compatibility |
| **Java Driver 4.x importer** | App-specific sources | Bounded async prepared CQL | Business pipelines, custom validation, idempotency/CDC | You own concurrency, retries, and checkpointing |
| **`sstableloader`** | Cassandra SSTable files | Streaming to natural replicas | Migrating/seeding from SSTables, changed target topology | Does not read CSV; requires compatible format/schema/partitioner |
| **`nodetool import`** | Local SSTables | Loads files into **one node** | Local file restores matching node token ranges | Does not stream cluster-wide to replicas; not a general loader |
| **SSTable writer + loader** | Transformed input → offline SSTables | Build SSTables then stream | Specialized validated pipelines | Format/version complexity; requires compatible writer library |

### 3.1. Quick decision tree

~~~text
Is the source valid Cassandra SSTables?
  |
  +-- YES --> Does target have a different ring/RF/node ownership?
  |             |
  |             +-- YES --> Prefer sstableloader
  |             |
  |             +-- NO --> Need cluster-wide streaming?
  |                         +-- YES: sstableloader
  |                         +-- NO, local files match node/ranges:
  |                                   consider nodetool import
  |
  +-- NO --> Is it simple CSV, moderate volume, needing quick execution?
               |
               +-- YES --> COPY FROM + dry-run/baseline/validation
               |
               +-- NO --> Need explicit mapping and CLI-style large loads?
                            +-- YES: DSBulk after version check
                            +-- NO: Complex/distributed ETL?
                                       +-- YES: Spark Connector
                                       +-- NO: Java Driver pipeline
~~~

"Moderate" and "large" **have no universal row-count threshold**. One million 200-byte rows with evenly spread partition keys behave very differently from one million rows each holding a 1 MiB blob for a single tenant. **Partition count, size, and skew** matter far more than raw row count.

### 3.2. When not to use a tool

- **`COPY FROM`**: hundreds of GiB/TiB with multi-table mapping and strong resumability needs; evaluate DSBulk/Spark/custom ETL instead.
- **`sstableloader`**: input is CSV/JSON or requires changing primary keys/splitting rows by business logic. Transform first with another tool.
- **`nodetool import`**: backups from an old ring whose tokens do not belong to the target node, or when streaming to the full cluster is required.
- **Spark**: a few-KB CSV or an environment without Spark; operational overhead outweighs benefit.
- **Giant CQL batches**: never a replacement for bulk loaders; multi-partition logged batches create overhead and coordinator pressure.

## 4. Capacity planning before loading

### 4.1. Do not count rows alone

Build an input profile table:

| Attribute | Hypothetical example | Impact |
|---|---|---|
| Row count | 20 million | Total requests/mutations |
| Average row size | 1 KiB | Logical data volume |
| Distinct partitions | 4 million | Token load distribution |
| P99 partition size | 15 MiB | Hot/wide partitions, reads/compaction |
| Largest partition | 1 GiB | Risk of overheating a node/replica set |
| RF | 3 | Data written across multiple natural replicas |
| Target | 6 nodes, 1 DC | Disk/network capacity |
| TTL/DELETE/updates | 30% of rows have TTL | Tombstones and compaction |
| Import window | 6 off-peak hours | Required throughput |

For 20 million rows over 6 hours, average required logical throughput is:

\[
\frac{20\,000\,000}{6 \times 3600} \approx 926\ \text{rows/s}.
\]

This is the **logical ingest target**, not physical disk writes. With RF=3, replicas each receive mutations, while actual byte/CPU/disk overhead depends on topology, compression, memtables, compaction, indexes, and retries; **never blindly multiply by three to claim exact IOPS**.

### 4.2. Resource headroom

- Disk: encoded/compressed logical data × RF, plus indexes/SAI, temp files, compaction output, and snapshot retention.
- CPU: serialization, validation, write path, compaction, compression, checksums.
- RAM: memtables, buffers, page cache, JVM heap/off-heap, client page/batch buffers.
- Network: client→coordinator, coordinator→replica, internode streaming, and cross-DC traffic.
- Availability: replicas must preserve quorum/CL for live reading/writing apps.
- Workload: ingest can degrade p99 for **other query families**, not only the batch job.

Never start streaming onto a nearly full disk. Post-load SSTable compaction can require substantial **temporary headroom**, especially when many SSTables flush together.

### 4.3. Arrival rate vs. service rate thinking

~~~text
Input rows/s
    |
    v
Importer concurrency & throttle
    |
    v
Coordinator / replica mutation stages
    |
    v
CommitLog + Memtable --> Flush --> SSTables --> Compaction
    |                    |                   |
 Client timeouts     PendingFlushes    PendingCompactions
    |                    |                   |
    +--------------------+-------------------+
                         |
                 Observe backpressure
~~~

If input rate exceeds sustainable storage capacity, queues may climb **only after a long delay**: memtables and caches absorb bursts initially, then flushes and compaction gradually consume disk and I/O. Never declare "max throughput" from the first 30 seconds.

## 5. Schema is the contract for the entire load

### 5.1. Design around queries before choosing a loader

Suppose the app needs two access paths:

1. Fetch the 50 most recent events for a tenant on a day.
2. Fetch a specific event by tenant/day and event ID.

Sample table:

~~~sql
-- Single-node lab; multi-DC production uses NetworkTopologyStrategy.
CREATE KEYSPACE IF NOT EXISTS bulk_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS bulk_lab.events_by_tenant_day (
    tenant_id text,
    day date,
    event_time timestamp,
    event_id uuid,
    status text,
    amount decimal,
    note text,
    PRIMARY KEY ((tenant_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

- Partition key `(tenant_id, day)` bounds data per tenant/day.
- Clustering columns `event_time, event_id` sort chronologically within the partition and avoid row collisions.
- `status` and `note` are regular columns. There is no default cluster-wide index/path to search by `status`.
- For massive tenants, a single day may still be too wide: add **smaller buckets or queryable shards**, after sizing app fan-out.
- If the business needs direct lookups by `event_id` without knowing the day, add a **second query-driven table**.

You cannot alter the partition key via `ALTER TABLE` on a populated table to "rebalance." Typically you must **CREATE a new table**, reload with the proper key mapping, and plan a read/write cutover.

### 5.2. Verify CQL types against source data

| Cassandra type | CSV/JSON input | Risk if mapped wrongly |
|---|---|---|
| `text` | UTF-8, may contain commas/newlines/Unicode | Broken CSV quoting, encoding errors, stripped accents |
| `uuid` | Standard UUID format | Never substitute sequence integers or timestamps for UUIDs |
| `timeuuid` | Version-1 time-based UUID | UUID v4 is invalid; do not auto-generate if ordering must be preserved |
| `date` | `YYYY-MM-DD` | Timezone/timestamp-column mix-up |
| `timestamp` | ISO-8601 with timezone/UTC | Hour shifts, precision loss if source uses nano/microseconds |
| `decimal` | Arbitrary-precision decimal | Locale decimal/thousands separators, precision truncation |
| `int`/`bigint` | In-range integers | Overflow, thousands separators, nulls |
| `boolean` | Parser-accepted true/false | `1/0` or "yes/no" may be rejected |
| `blob` | Connector-encoded bytes | Raw CSV text bytes are not valid |
| `list`/`set`/`map`/UDT | Serialized in supported syntax/connector format | Flat CSV strings do not auto-parse into collections/UDTs |
| `counter` | Dedicated counter mutation | Cannot be loaded via ordinary integer `INSERT` |

**Data-integrity warning:** successful type parsing alone is not enough. Converting `2026-11-21T23:30:00+07:00` into `2026-11-21T23:30:00Z` silently shifts real time by **7 hours**. If the partition key uses local dates, define explicitly which timezone computes the date; never accidentally mix UTC days and local days.

### 5.3. Null primary keys and duplicate inputs

- Primary-key components cannot be null. A CSV row missing `tenant_id` or `day` goes to **quarantine**, never into an "unknown" bucket unless business-approved.
- Two rows with the **same primary key** are two mutations to the **same row**, not two distinct rows. Depending on timestamps and column semantics, the later write may mask the earlier one.
- Generating a fresh `event_id` on every retry creates **business duplicates**. Preserve stable event IDs and idempotency keys from the source.
- `INSERT`ing null into a regular column can write a tombstone/delete, unlike **omitting the column from the mutation**. Never let blank CSV cells silently delete existing data.

### 5.4. Replication and consistency before loading

Multi-DC production requires appropriate keyspace strategy and RF:

~~~sql
-- Illustrative DDL; run only if dc1/dc2 ACTUALLY exist.
CREATE KEYSPACE production_events
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': '3',
    'dc2': '2'
};
~~~

`RF` is the replica count per DC, **not** row count or a free speed knob. `LOCAL_QUORUM` requires enough replicas in the local DC proportional to RF; boosting throughput by lowering CL alters the **consistency contract**, not an equivalent optimization. If RF changes after data is loaded, follow a **repair/rebuild/streaming runbook** so historical data reaches new replicas.

## 6. `cqlsh COPY FROM`: loading CSV directly

### 6.1. Basic syntax

~~~sql
-- Run inside cqlsh. The CSV file resides on the machine RUNNING cqlsh.
COPY bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status, amount, note
) FROM '/srv/bulk-lab/events.csv'
WITH HEADER = TRUE
AND DELIMITER = ',';
~~~

`COPY FROM` reads CSV, casts fields to CQL types per schema, and issues writes. **It does not accept SSTables**, cannot choose new primary keys on its own, and does not turn the cluster into a "consistent snapshot."

**File paths are local to the `cqlsh` client**, not paths required on every Cassandra node. If `cqlsh` runs inside a container, mount the file into that container. If running from a laptop, server paths like `/var/lib/...` are not directly reachable.

### 6.2. Sample CSV with quoting and Unicode

~~~csv
tenant_id,day,event_time,event_id,status,amount,note
tenant-a,2026-11-21,2026-11-21T08:00:00Z,11111111-1111-1111-1111-111111111111,NEW,1200.50,"Đơn mới, đã xác nhận"
tenant-a,2026-11-21,2026-11-21T08:05:00Z,22222222-2222-2222-2222-222222222222,PAID,1200.50,"Khách ghi: ""giao buổi sáng"""
tenant-b,2026-11-21,2026-11-21T09:10:00Z,33333333-3333-3333-3333-333333333333,NEW,75.25,"Đặt qua ứng dụng"
~~~

This CSV uses commas as delimiters, **double quotes** around fields containing commas, and doubled quotes `""` to escape embedded quotes. Vietnamese characters require consistent encoding; UTF-8 is recommended. Rows with newlines inside quoted fields require a compliant CSV parser; **never** split text naively with `line.split(",")`.

Because each `event_id` is distinct, these three lines form three distinct primary keys. Commas inside `note` do not produce an eighth column when quoting is parsed properly.

### 6.3. Key shared and COPY FROM options

Per Apache `cqlsh` documentation, notable option names include:

| Option | Scope | Meaning | Rule |
|---|---|---|---|
| `HEADER` | FROM/TO | Whether first line contains column names | Explicitly set `TRUE` when file has headers |
| `DELIMITER`, `QUOTE`, `ESCAPE` | FROM/TO | CSV syntax | Match source exactly to prevent column shift |
| `NULLVAL` | FROM/TO | String representing null, defaults to `null` | Distinct from empty text; define mapping explicitly |
| `ENCODING` | FROM/TO | Text encoding | Choose UTF-8 and verify actual file encoding |
| `NUMPROCESSES` | FROM/TO | Number of `cqlsh COPY` worker processes | Raising it increases client/server load; do not raise blindly |
| `INGESTRATE` | FROM | Max rows/second limit | Size per SLO/capacity |
| `MAXROWS`, `SKIPROWS`, `SKIPCOLS` | FROM | Limit/skip data slices | Useful for labs/chunking; check to avoid missed lines |
| `MAXBATCHSIZE`, `MINBATCHSIZE` | FROM | Batch size inside importer | Never raise unboundedly; avoid huge batches |
| `CHUNKSIZE` | FROM | Rows handed to a worker process | Affects memory and overhead |
| `MAXATTEMPTS` | FROM/TO | Retry attempts per chunk/range | Does not guarantee business idempotency |
| `MAXPARSEERRORS`, `MAXINSERTERRORS` | FROM | Error threshold before aborting | Inspect error files; never allow silent errors |
| `ERRFILE` | FROM | File capturing failed rows | Protect sensitive data and replay with control |
| `RATEFILE` | FROM/TO | Logs throughput statistics | Use to measure throughput if permitted |

No single `NUMPROCESSES`/`INGESTRATE` fits every cluster. Tune from a **baseline** and storage capacity; check `COPY ... HELP` and exact binary docs before setting advanced flags. `COPY` parses and executes in chunks, so multiple retries do not mean "exactly once."

### 6.4. Rate-limited load template in staging

~~~sql
-- Example configuration for a LAB cluster only.
-- Do not treat 300 rows/s as a universal production recommendation.
COPY bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status, amount, note
) FROM '/srv/bulk-lab/events.csv'
WITH HEADER = TRUE
AND INGESTRATE = 300
AND MAXPARSEERRORS = 0
AND MAXINSERTERRORS = 0
AND ERRFILE = '/srv/bulk-lab/copy-import-errors.csv';
~~~

Setting `MAXPARSEERRORS=0` and `MAXINSERTERRORS=0` prevents errors from being skipped under the error budget; operators must still verify **exit status, summary output, error files, and actual rows**. Never assume `cqlsh` loaded everything into Cassandra simply because no exception scrolled across the screen.

### 6.5. `cqlsh COPY TO`: exporting a sample table

~~~sql
COPY bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status, amount, note
) TO '/srv/bulk-lab/events-export.csv'
WITH HEADER = TRUE
AND ENCODING = 'UTF8';
~~~

`COPY TO` runs paged reads across token ranges and writes CSV client-side. **It is not a physical SSTable backup**: it omits write timestamps, tombstones, TTL/expiration metadata, commit logs, and update history. If writes continue during export, a range-by-range CSV contains data from **multiple points in time**, not an atomic snapshot.

Never use `COPY TO` as proof of RPO=0 or a full restore strategy for tables whose DELETEs/TTLs must be preserved accurately. For exporting a few hundred rows in a lab, however, it remains very handy.

### 6.6. CSV mistakes that "succeed syntactically, fail semantically"

| Error | Example | Remediation |
|---|---|---|
| Column shift from quotes | `"Hanoi, Vietnam"` split in two | Use compliant CSV parser; verify field counts |
| Locale decimal format | `1.200,50` | Normalize decimal separators before import |
| Null vs. empty string | Literal `null` parsed as NULLVAL | Pick safe sentinel; validate source |
| Unicode/BOM issues | First column header contains BOM | Use clean UTF-8; inspect leading header bytes |
| Wrong timezone | `+07:00` treated as `Z` | Normalize instants and day buckets |
| Duplicate primary key | Two identical `tenant-a/day/time/id` rows | Check duplicates and business versioning |
| Missing required field | Blank `event_id` | Quarantine; never auto-generate IDs on retry |
| CSV formula injection on export | Cell starts with `=` or `+` | Never open untrusted exports in spreadsheets without escaping/sanitizing |

**Right pipeline:** parse → validate → quarantine bad rows → load a small sample → verify by primary key → scale up. Never use `COPY FROM` to blindly "clean" source data with unknown semantics.

## 7. DataStax Bulk Loader (DSBulk): CSV/JSON with better mapping and observability

DSBulk is a **CQL/Java Driver-based** bulk tool that reads CSV/JSON sources, applies mappings, and executes configured prepared writes or reads. It overcomes several operational limits of `cqlsh COPY` at scale, yet **does not alter Cassandra fundamentals**: partition keys, RF/CL, timestamps/TTLs, and disk/compaction still govern outcomes.

### 7.1. Loading the same CSV file

~~~bash
# Requires compatible DSBulk installed and connectivity to the LAB cluster.
# -h specifies contact point(s), not the storage streaming port.
dsbulk load \
  -h 127.0.0.1 \
  -k bulk_lab \
  -t events_by_tenant_day \
  -url /srv/bulk-lab/events.csv \
  -header true
~~~

Per DSBulk docs, when CSV headers match CQL column names, DSBulk can infer mapping; **explicit mapping is recommended** when production schemas/CSVs have many columns or differing names. For headerless files, map by positional index:

~~~bash
# Example only for a headerless CSV with verified two-column order.
dsbulk load \
  -h 127.0.0.1 \
  -k bulk_lab \
  -t demo_two_columns \
  -url /srv/bulk-lab/no-header.csv \
  -header false \
  -m '0=tenant_id,1=event_id'
~~~

`demo_two_columns` is a **hypothetical table name** illustrating mapping, not a table created in Section 5. Do not run the second command unless that table exists.

### 7.2. Dry run and concurrency throttling

~~~bash
# Validate mapping/input without writing to the table.
dsbulk load \
  -h 127.0.0.1 \
  -k bulk_lab -t events_by_tenant_day \
  -url /srv/bulk-lab/events.csv \
  --dryRun
~~~

Once dry runs and samples pass, bound in-flight queries:

~~~bash
# 16 is an illustrative starting value for a LAB only.
dsbulk load \
  -h 127.0.0.1 \
  -k bulk_lab -t events_by_tenant_day \
  -url /srv/bulk-lab/events.csv \
  --engine.maxConcurrentQueries 16
~~~

`--engine.maxConcurrentQueries` is a **concurrency safeguard**, not a fixed rows/second guarantee: actual throughput depends on latency, batching, and backpressure. Per current DSBulk guidance, this option is preferred over older executor rate/in-flight flags. Never jump from 16 to thousands simply because a CSV is taking long to finish.

### 7.3. Error logs and quarantine

A DSBulk load categorizes errors into:

| Error class | Example | Handling |
|---|---|---|
| Connector/parser | Bad CSV quoting or malformed JSON | Quarantine source file/line; fix encoding/parser |
| Mapping | Missing primary-key field or unconvertible type | Fix schema mapping or source data |
| Write/server | Timeout, unavailable, overload, auth failure | Diagnose CL/nodes/resources; **conditional** retry |
| LWT/Paxos | Conditional write did not apply | Often a **business conflict**; never retry infinitely |

DSBulk emits operation logs and `connector.bad`, `mapping.bad`, `load.bad`, and `paxos.bad` files depending on errors and config. These files can contain **raw source records**, so encrypt and restrict access. Never publish error files openly for debugging convenience.

**Never equate "rows processed" with "valid rows persisted in the cluster."** Source rows may collide on primary key, be masked by tombstones/TTLs, or be overwritten by newer mutations; validate logical outcomes.

### 7.4. When to choose DSBulk over COPY?

- Multiple CSV/JSON files needing explicit mapping and per-record error logs.
- Need chunked/batched ingestion with summary metrics and concurrency caps.
- Dataset too large for `cqlsh COPY` to coordinate cleanly, yet no Spark cluster is warranted.
- Team can operate DSBulk versions, auth/TLS, configs, and secure log storage.

**Never use DSBulk to bypass partition-key design.** It can hammer a hot partition fast enough to overload a natural replica set; the root flaw is the data model.

## 8. Spark Cassandra Connector: distributed transform before load

For massive Parquet/Delta/JDBC/JSON sources needing cleaning and complex schema transformations, Spark often fits better than simple CSV copies.

### 8.1. General pipeline

~~~text
RDBMS/Parquet/JSON/CSV
          |
      Spark read
          |
    Validate schema
    Normalize timezones/IDs
    Deduplicate by business key
    Derive tenant/day buckets
          |
      Repartition/shuffle
          |
    Cassandra Connector
          |
    Prepared/mapped CQL writes
          |
       Cassandra
          |
    Sample + full reconciliation
~~~

Spark **does not automatically fix** duplicate primary keys or CDC ordering. If streaming inputs replay, enforce idempotency/versioning in the data layer. Too many Spark partitions/concurrent tasks can trigger write spikes; too few bottleneck on a single executor.

### 8.2. Illustrative Spark Scala example

~~~scala
import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._

val spark = SparkSession.builder()
  .appName("CassandraBulkLab")
  .getOrCreate()

val raw = spark.read
  .option("header", "true")
  .option("inferSchema", "false")
  .csv("/srv/bulk-lab/events.csv")

// Parse date/timestamp/UUID and amount per target schema.
// In real workloads, check for null/format errors after casting.
val normalized = raw.select(
  col("tenant_id"),
  to_date(col("day"), "yyyy-MM-dd").as("day"),
  to_timestamp(col("event_time")).as("event_time"),
  col("event_id"),
  col("status"),
  col("amount").cast("decimal(18,2)").as("amount"),
  col("note")
)

normalized.write
  .format("cassandra")
  .option("keyspace", "bulk_lab")
  .option("table", "events_by_tenant_day")
  .mode("append")
  .save()
~~~

This is a **skeleton snippet** illustrating flow, not guaranteed to compile without compatible connector dependencies. For CQL `uuid` columns, the Spark connector may require native UUID typing rather than Strings; apply mapping/casts per your **connector version** or handle conversion in a typed step. Configure matching **Spark/Scala/Cassandra** connector dependencies and connection/auth/TLS settings.

Modern connector docs support `.format("cassandra")` with `keyspace`/`table`; older codebases still use the long format class `org.apache.spark.sql.cassandra`. Never copy old examples without checking the dependency matrix.

### 8.3. Repartitioning can help or hurt

A Spark job can repartition data by partition-key groups to prevent executor skew, but balance carefully:

- Repartitioning entirely by `tenant_id` when a few tenants dominate concentrates load onto a handful of tasks.
- Repartitioning into too many tasks causes **driver/network/cluster** storms of thousands of simultaneous writes.
- A hot Cassandra partition stays hot even when Spark tasks look balanced: all writes for the same key still hit the same natural replica set.
- Shuffling huge datasets burns Spark worker disk and stalls jobs before reaching Cassandra.

Measure **source read, transformation, shuffle, and Cassandra write**, not just `save()` duration. Define duplicate resolution explicitly: if an event appears twice with differing versions, blind `dropDuplicates` can keep the wrong version.

### 8.4. When not to use Spark

A table with a few thousand rows or one small CSV does not need a Spark cluster. If the workload needs event-by-event reads/writes with custom transactional checks, a controlled Java Driver pipeline is often simpler. Spark shines when **ETL/scale-out** is the bulk of the work—not because Cassandra "requires Spark to be fast."

## 9. `sstableloader`: bulk loading SSTables into a live ring

`sstableloader` reads **SSTable files** from a stable directory and streams data to natural replicas according to the target cluster's ring and replication strategy. It does not read CSVs, does not execute per-row CQL `INSERT`s, and **does not** create schemas for you.

### 9.1. Turning a snapshot into a staging SSTable directory

Suppose the source has a snapshot:

~~~text
/var/lib/cassandra/data/source_events/
  events_by_tenant_day-<table_id>/
    snapshots/snap-20261121/
      nb-1-big-Data.db
      nb-1-big-Statistics.db
      nb-1-big-TOC.txt
      ... other components
~~~

Paths above are format illustrations. Each SSTable comprises multiple files sharing a generation; `nb`/`ma` prefixes, BIG/BTI formats, and auxiliary files depend on Cassandra version. Never copy `Data.db` alone.

Create an **isolated copy** in staging under `<target_keyspace>/<target_table>`:

~~~text
/srv/loader-staging/bulk_lab/events_by_tenant_day/
    nb-1-big-Data.db
    nb-1-big-Statistics.db
    ...
~~~

If sets from multiple source nodes share **colliding generation names**, never overwrite files in one folder. Separate staging directories per source set or use a supported rename/rewrite tool; never rename one component's prefix without its siblings.

### 9.2. Syntax and prerequisites

~~~bash
sstableloader --help

# Example loader running on the host holding the staging copy;
# contact points belong to the TARGET CLUSTER, not the source.
sstableloader \
  --nodes 10.20.0.11,10.20.0.12 \
  --throttle-mib 16 \
  /srv/loader-staging/bulk_lab/events_by_tenant_day
~~~

| Parameter/condition | Meaning |
|---|---|
| `--nodes` / `-d` | Initial target hosts to fetch topology; **not** the list of all replicas written |
| Directory `<keyspace>/<table>` | Loader infers target table from parent path by default |
| `--target-keyspace` | Supported versions can remap target keyspace; does not rename tables or transform schemas |
| `--throttle-mib` | Streaming rate cap in MiB/s; size to real capacity |
| Native/streaming ports, auth/TLS | Reaching port 9042 does not prove internode streaming ports are open |
| SSTable format/partitioner/schema | Loader binary must read the format, and target must be compatible |
| Source snapshot copy | Never point at live SSTables actively undergoing compaction or writes |
| Disk/network headroom | Streaming can increase compaction/IO on target |

**Distinguish source and target:** `sstableloader` docs warn against running the tool against live SSTables managed by Cassandra on the local host. The safe approach runs the loader on an **offline/staging copy** while the **target cluster is running** to receive streams. Never shut down the target cluster just because the loader reads files from a host.

### 9.3. Why `sstableloader` fits topology changes

~~~text
SOURCE (3 nodes, RF=3):       TARGET (5 nodes, RF=3):
    A -- B -- C                    P -- Q -- R -- S -- T
     \    |    /                     \      |       /
       snapshot                       new token ring
           |                                 ^
    copy SSTables                            |
           |                                 |
       sstableloader ------------------------+
            Stream sections by NEW token ownership
~~~

There is no 1:1 A→P, B→Q, C→R mapping. Token ranges and natural replicas may have changed completely. `sstableloader` places data according to the **target's replication** rather than preserving source-node file placement.

### 9.4. `sstableloader` is not a business-data repair tool

- Matching primary keys with differing timestamps reconcile under Cassandra rules, not "last file loaded wins."
- Newer tombstones still mask rows from older SSTables.
- Expired TTLs do not automatically reset when re-streaming files.
- If tombstones were purged and an older SSTable returns, **zombie data** can appear; reconcile against deletion events.
- Loader success does not guarantee all source token ranges were covered: a snapshot from one node holds only part of the dataset.
- Denormalized tables, secondary indexes, and materialized views have separate schemas and data flows; verify after loading.

Therefore, if source data needs **primary-key transformation or cleansing**, use DSBulk/Spark/Java to issue new mutations per design; never try to turn `sstableloader` into SQL ETL.

## 10. How do `nodetool import`, `refresh`, and `sstableloader` differ?

| Attribute | `sstableloader` | `nodetool import` | `nodetool refresh` |
|---|---|---|---|
| Source | Staging SSTables | Local staging SSTables | SSTables placed inside live table directory |
| Scope | **Cluster/replicas** per target ring | **Single node** invoked | **Single node** invoked |
| Token ownership | Loader splits ranges across natural replicas | Can validate local node tokens | Operator responsible for placing right files |
| Target keyspace/table | From directory/option | Command KS/table arguments | Table directory and arguments |
| Integrity/cache/repaired checks | Streaming path | Verify/token/cache options | Fewer safeguards; legacy |
| Differing source/target topology | **Preferred** | Easy to misplace files | Easy to misplace files |
| Works for CSV | No | No | No |

`nodetool import` is recommended over legacy `refresh` in modern bulk-loading guides. Example:

~~~bash
# Execute only on authorized nodes with matching schema and token ranges.
nodetool help import
nodetool import -- bulk_lab events_by_tenant_day \
  /srv/local-staging/events_by_tenant_day
~~~

If import reports tokens out of range, **never pass `--no-tokens` to force files onto the node**. Storing out-of-range files on a node causes unreadable data or replica divergence. Likewise, avoid `--no-verify`/`--quick` without validating the source.

**When a new node needs data from healthy replicas**, **replace/rebuild or repair** is often more appropriate than manual local file imports. This lesson covers data loading—never turn a node failure into manual SSTable file copying without verifying topology.

## 11. Timestamps, TTL, tombstones, and idempotency when reloading

### 11.1. A "row" does not always share one single timestamp

Cassandra reconciles data at the cell/row/tombstone level by write timestamp (microseconds). One row can hold:

~~~text
PK = (tenant-a, day=2026-11-21, event_time=08:00, id=1111)
  status = PAID        writetime = 1_800_000_000_100_000
  amount = 1200.50     writetime = 1_800_000_000_090_000
  note   = "manual"    writetime = 1_800_000_000_110_000
~~~

These are simulated timestamps unrelated to the CSV row's business time. When `COPY TO` exports CSV, these write timestamps **are not exported by default**. `COPY FROM` creates new mutations and can overwrite newer cells if stamped with current time.

### 11.2. Example of backfill overwriting live data

~~~text
T0  Source snapshot:
      order-123.status = NEW, source_version=1

T1  User updates TARGET table:
      order-123.status = PAID, source_version=2

T2  Old CSV backfill runs via COPY FROM:
      order-123.status = NEW
      (mutation receives T2 write timestamp)

T3  Client reads:
      may see NEW again because T2 is newer than T1.
~~~

**This is not a `cqlsh` bug**: the loader executes writes according to Cassandra semantics. Never load an old CSV snapshot directly into a table receiving continuous live writes without a version/ordering protection strategy.

### 11.3. Ordering protection approaches

| Approach | Mechanism | Conditions / risks |
|---|---|---|
| **Controlled write pause** | Pause writes in a short window, backfill, verify, resume | Fits small datasets where downtime/RTO is allowed |
| **Isolated new table/keyspace** | Backfill into table B, then catch up and cut over | Needs storage headroom, dual-read, feature flags |
| **Preserved source timestamps** | Write CQL with `USING TIMESTAMP` reflecting logical source time where permitted | Requires trusted source metadata and unified conflict policy |
| **Business version + merge logic** | Accept only newer versions via controlled pipeline/conditions | Cannot use blind `INSERT`; LWT adds cost |
| **CDC/outbox delta catch-up** | Capture T0 watermark, backfill snapshot, replay post-T0 events | Must guarantee CDC retention, ordering, completeness |
| **Per-tenant/bucket cutover** | Lock or transfer write ownership per subset | Requires planned routing, ownership, and rollback |

If the source carries event versions, **never treat CQL client timestamps as a perfect business sequence**. Clock skew or future-dated write timestamps can shadow subsequent updates. When transactional logic is required, build conflict resolution on **idempotency keys, source sequences, audits**, and proper coordination.

### 11.4. Preserving write timestamps when valid metadata exists

In controlled Java or CQL pipelines, CQL can specify write timestamps:

~~~sql
-- Conceptual example; 1800000000100000 is microseconds and
-- must be derived from a trusted source before execution.
INSERT INTO bulk_lab.events_by_tenant_day
    (tenant_id, day, event_time, event_id, status)
VALUES (
    'tenant-a', '2026-11-21', '2026-11-21T08:00:00Z',
    11111111-1111-1111-1111-111111111111, 'NEW'
) USING TIMESTAMP 1800000000100000;
~~~

`USING TIMESTAMP` controls only the newly generated CQL mutation; it **cannot reconstruct tombstone history** lost during CSV export. For sources with **per-column** timestamps, a single `INSERT` with one shared timestamp does not preserve full cell history; plan explicitly or use compatible SSTables/snapshots.

### 11.5. TTL/expiration requires an independent policy

~~~text
Source T0: INSERT session USING TTL 3600
90 minutes after T0: re-import from CSV

If COPY FROM runs without TTL:
  session may live forever in target.

If re-imported with fresh TTL 3600:
  session may live another full hour.

Neither matches "session expires at T0+3600".
~~~

For TTL-bound data, know the original expiration and policy:

1. If a record has already expired by wall-clock time, **do not recreate it** unless intentionally required.
2. If still alive, compute **remaining TTL** relative to target time and account for clock skew/races.
3. If exact expiration/TTL preservation is mandatory, consider compatible SSTable migration or a metadata-complete pipeline.
4. If valid tombstones/DELETEs occurred after T0, replay deletions and verify those rows **remain absent**.

Never lower `gc_grace_seconds` to purge data after a bulk load without guaranteeing repair/retention: premature tombstone GC can cause **zombie data** when older SSTables return.

### 11.6. Are retries idempotent?

A CQL `INSERT` with identical primary key and values is close to a replayable upsert, yet **insufficient to claim universal exactly-once**:

- Retries with differing client timestamps can affect conflict resolution.
- Default TTL restarts from zero when a mutation is resent.
- `COUNTER UPDATE` increments are **not idempotent** like point-key INSERTs.
- LWT `IF NOT EXISTS` can return `[applied]=false` on retry even though the first attempt succeeded.
- Generating a new UUID per retry creates duplicate rows.
- Writing the same row while updating inconsistent column subsets interleaves state.

Anchor idempotency on **business rules and source event IDs**, checkpoint only after ACK/validation, and reconcile timed-out "unknown outcome" writes. Never blindly replay an entire error file infinitely.

## 12. Batching: why `BEGIN BATCH` is not a bulk accelerator

A common misconception is that stuffing one million CQL inserts into one `BEGIN BATCH` makes loading faster. In Cassandra:

- **Multi-partition logged batches** require batchlog writes and coordinator overhead; they are not global SQL/RDBMS transactions.
- **Unlogged batches** do not eliminate per-mutation I/O and offer no cross-partition atomicity.
- Oversized batches trigger warnings and overload coordinators.
- Grouping a few mutations **within the same partition** can make sense, but measure actual p99/throughput and semantics.
- DSBulk/`cqlsh COPY` manage their own batching policies; never raise `MAXBATCHSIZE` blindly to optimize.

~~~sql
-- Do not use this pattern as a production bulk loader!
BEGIN BATCH
  INSERT INTO bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status
  ) VALUES (
    'tenant-a', '2026-11-21', '2026-11-21T08:00:00Z',
    11111111-1111-1111-1111-111111111111, 'NEW'
  );
  INSERT INTO bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status
  ) VALUES (
    'tenant-b', '2026-11-21', '2026-11-21T08:00:00Z',
    22222222-2222-2222-2222-222222222222, 'NEW'
  );
APPLY BATCH;
~~~

These two rows belong to **two different partitions**; for a bulk importer, sending individual prepared statements with bounded concurrency is far easier to control. Batches never bypass disk or compaction bottlenecks.

### 12.1. Concurrency vs. stability trade-off

If an importer holds `N` in-flight requests with mean latency `W` seconds, intuitive steady-state throughput is roughly `N/W` assuming zero retries or new bottlenecks. That is **not a guarantee**: Cassandra involves RF, coordinators, disk flushes/compaction, and partition skew.

For example, 32 in-flight × 50 ms mean ≈ 640 requests/s is purely theoretical. Pushing to 256 in-flight can multiply disk await so throughput stalls while tail latency and timeouts explode. Use **concurrency feedback loops** driven by p99, errors, and resource metrics rather than one-off division math.

## 13. Live schema migration pipeline while the app stays online

A typical project: an old `events_by_tenant` table has overly wide partitions and must move to a time-bucketed `events_by_tenant_day`.

### 13.1. Old data and new tables cannot swap keys in place

~~~text
V1 (old):
  PRIMARY KEY ((tenant_id), event_time, event_id)
  => Large tenants create massive wide partitions

V2 (new):
  PRIMARY KEY ((tenant_id, day), event_time, event_id)
  => Partitioned by tenant/day

No ALTER TABLE changes the partition key.
Must CREATE TABLE V2, backfill, catch up updates,
and switch application reads/writes.
~~~

### 13.2. Safe phases

~~~text
                         SOURCE V1 (live)
                                |
                Pick watermark / snapshot T0
                                |
                    Backfill history T<=T0
                                |
                         TARGET TABLE V2
                                |
           +--------------------+--------------------+
           |                                         |
    CDC/outbox/delta from T0                     New dual-writes
           |                                         |
           +--------------------+--------------------+
                                |
                  Catch up to acceptable lag
                                |
                    Audit keys/versions/TTLs
                                |
                     Canary reads from V2
                                |
                     Cut traffic by cohort
                                |
                   Monitor + rollback window
~~~

**There is no automatic cross-table atomicity** because Cassandra does not offer RDBMS-style cross-table transactions across arbitrary operations. When an app dual-writes and V1 succeeds while V2 fails, you need a repeatable compensating mechanism such as an outbox or event stream with durable retries and reconciliation.

### 13.3. Watermarks and catch-up must not rely on naive wall clocks

A watermark can be an offset/event sequence from an **authoritatively ordered** source. Simply noting "T0=10:00 UTC," scanning V1 with CQL, and reading CDC after 10:00 can miss late-arriving mutations, retries, or clock-skewed writes.

Safer workflow:

1. Select a **source of truth** (event log/CDC/transactional snapshot) with guaranteed checkpoints.
2. Record the source watermark/offset and define handling for late-timestamp events.
3. Backfill from a consistent snapshot within supported scope.
4. Catch up post-checkpoint events with version-ordered idempotent replay.
5. Verify lag/coverage meets criteria, not merely "source queue looks empty."
6. Continue reconciliation after shifting writes.

If you only have a **non-atomic cluster-wide** Cassandra snapshot without a reliable changelog, explicitly **document consistency bounds** and schedule an appropriate quiesce or dual-write window. Never promise zero-downtime/lossless migration from a `COPY TO` export alone.

### 13.4. Gated cutover and rollback

| Phase | Advancement criterion | If not met |
|---|---|---|
| New schema deployed | Correct DDL, schema agreement, and right RF/DC | Stop; fix schema first |
| Backfill completed | Full source file coverage; all errors triaged | Backfill only missing chunks |
| Delta caught up | Low lag, valid versions/order, zero unprocessed critical events | Do not shift reads |
| Canary reads | Matching results/ordering/paging, p99 and errors within SLO | Roll back read flag; fix V2 |
| Writes to V2 | Healthy dual-write/outbox and zero data gaps | Keep V1 authoritative; replay events |
| Full cutover | RPO/RTO, monitoring, and rollback approved | Hold rollback window |
| Retire V1 | Zero remaining consumers; retention/backups verified | **Do not** DROP/TRUNCATE prematurely |

**Rolling back read routing** is much easier than rolling back **one-way writes**. Once only V2 receives writes after cutover, reverting to V1 requires **reverse replication/replay** or keeping V1 synchronized throughout the rollback window. Never promise "just flip the feature flag back to V1" if V1 has already missed new writes.

## 14. Controlled execution: baseline, throttling, checkpoints, and stop conditions

### 14.1. Baseline before importing

Every production load plan needs:

| Group | Values to record | Purpose |
|---|---|---|
| Cluster/ring | `nodetool status`, RF/DC, down/joining nodes, free disk | Confirm target replicas and capacity |
| Application | QPS, query families, read/write p95/p99, timeouts/unavailables | Measure user impact |
| Importer | Input rows/bytes, parse errors, accepted/failed, retries | Separate ingest speed from correctness |
| JVM/driver | In-flight count, connection pools, client timeouts, retries | Spot client-side overload |
| Storage write path | Memtable bytes, `PendingFlushes`, `CommitLog` waits | Catch slow flushes/commit logs |
| Compaction | `PendingCompactions`, `Compaction.PendingTasks`, bytes compacted | Spot backlogs trailing bursts |
| Read amplification | SSTables per read, tombstones per read | Prevent loads from degrading reads |
| OS | CPU, GC, disk await/IOPS, network, free disk | Protect physical headroom |

Read-only inspection commands:

~~~bash
nodetool version
nodetool status
nodetool describecluster
nodetool tablestats bulk_lab.events_by_tenant_day
nodetool tpstats
nodetool compactionstats
nodetool netstats
nodetool gcstats
~~~

`nodetool status` shows ring membership/liveness, **not whether data finished loading**. `PendingCompactions` is a backlog estimate, not seconds remaining. Correlate commands with JMX/Prometheus and application metrics **within the same UTC window**.

### 14.2. Ramp up instead of starting at max speed

~~~text
PRE-FLIGHT:  healthy replicas, disk, schema, source integrity
       |
  CANARY:   1 file / 1 token group / 1 tenant bucket
       |
  VERIFY:   parse + CQL results + p99 + resources
       |
  RAMP 1:   raise import concurrency/INGESTRATE moderately
       |
  VERIFY:   do pending flushes/compactions drain backlogs?
       |
  RAMP 2:   only while metrics and SLAs hold
       |
  FINAL:    checkpoints, catch-up, reconciliation
       |
  CUTOVER:  read/write flags with rollback plan
~~~

The target is **maximum sustainable throughput**, not **5-second peak throughput**. When disk/compaction backlogs accumulate over hours, a 10-minute canary will not expose them. Step concurrency up gradually and hold each plateau long enough to observe downstream effects.

### 14.3. GO / HOLD / STOP conditions

| Condition | Classification | Action |
|---|---|---|
| Invalid input checksum/header/schema | `STOP` | Fix source; never let malformed mutations enter target |
| Invalid rows or null PKs | `HOLD` or `STOP` | Quarantine and decide whether skipping is valid |
| Missing replicas prevent meeting CL | `STOP` | Restore availability first |
| Write p99 spikes; timeouts breach SLO | `STOP/THROTTLE` | Slow down without weakening consistency guarantees |
| Free disk drops below operational headroom | `STOP` | Halt unthrottled streaming/compaction pressure |
| Prolonged `PendingFlushes` and blocked allocations | `HOLD` | Investigate disk/flush health; throttle load |
| `PendingCompactions` rises but drains post-peak; SLOs hold | Controlled `GO` | Keep monitoring |
| Missing data in a token range | `HOLD` | Check source coverage/checkpoints and repair |
| Purged DELETE/TTL rows reappear | `STOP` | Audit and fix logic; do not shift traffic |
| Canary sample sufficient, data accurate, SLOs and headroom healthy | `GO` | Expand batch by batch |

**Never hard-code a blanket threshold like "pending > 20 means stop" for every cluster.** Derive thresholds from baseline, disk class, RF, compaction strategy, and application SLOs; for quorum loss or severe data corruption, stop immediately without waiting three windows.

### 14.4. Safe chunk manifests and checkpoints

~~~text
RUN_ID: orders-v2-backfill-2026w47
SOURCE_SNAPSHOT: snapshot-id-abc
DEST_SCHEMA_HASH: ddl-sha256-...
DEST_CLUSTER: cluster-v2/dc1

CHUNK_0001:
  source_file: events-0001.csv
  source_sha256: ...
  input_rows: 100000
  expected_unique_primary_keys: 99998
  tool: dsbulk load
  started_utc: ...
  finished_utc: ...
  parsed: 100000
  confirmed_written: ...
  failed_or_unknown_outcome: ...
  reconciliation: PASS/FAIL
  state: VERIFIED

CHUNK_0002:
  state: PENDING
~~~

Record `VERIFIED` only after **inspecting write outcomes and data validation**, never merely because a tool process exited 0. A failed write may already have applied on replicas before the client timed out; on replay, preserve **the same PK and idempotent semantics**.

### 14.5. Separate "parse error" from "unknown write outcome"

| Error type | Immediate retry allowed? | Reason |
|---|---|---|
| Wrong CSV column count | No | Fix input; retrying changes nothing |
| Null primary key | No | Lacks valid identity |
| Type conversion error | No | Needs normalization/mapping fix |
| Auth/TLS failure | No | Fix environment first |
| Cassandra unavailable | Possible after restoring CL/health | Never add load to an unhealthy cluster |
| Client write timeout | **Only per idempotency policy** | Write may already have applied |
| LWT `[applied]=false` | Do not treat as transport error | May be a legitimate conflict or retry of an earlier success |
| Duplicate source event | Per dedup/version rule | Never turn into fabricated new records |

`COPY`/DSBulk error logs should capture **source filename/line number or event ID** for reconciliation; never log full PII payloads to general dashboards. Store error files under security and retention controls.

## 15. Verifying correctness: "loaded" ≠ "accurate data"

### 15.1. Three validation layers

| Layer | Question | Evidence |
|---|---|---|
| **Transport** | Were all files/chunks parsed or streamed completely? | Exit codes, bytes/rows, error/retry logs |
| **Replica placement** | Did data reach natural replicas/ranges/DCs per target RF? | Token coverage, ring, loader logs, repair checks |
| **Business correctness** | Are all PKs/columns, statuses/versions, TTLs/DELETEs, and derived tables right? | Audits, expected key sets, hashes/canonical serialization |

**One successful `SELECT` at CL=`ONE`** does not prove all replicas hold the data. Conversely, `LOCAL_QUORUM` succeeding in `dc1` does not confirm `dc2` is fully loaded. In large migrations, verify **per DC** matching application serving requirements.

### 15.2. Never rely solely on cluster-wide `COUNT(*)`

`SELECT COUNT(*) FROM large_table` scans huge ranges, causes timeouts, and competes for read I/O. Even when it returns the right count, you can still have:

- A missing key offset by a duplicate or stale key.
- Wrong `status` values despite matching row counts.
- Valid rows masked by tombstones/TTLs in one DC but not another.
- Mis-mapped decimals, timezones, or UUIDs.
- Divergent denormalized tables even while the base table count matches.

**Small lab tables can use counts**, whereas production should use **source manifests + per-partition/token-range checksums or controlled sampling/aggregates**, paired with business audits and full reconciliation where required.

### 15.3. Test key sets must include must-be-present and must-be-absent rows

~~~text
EXPECTED:
  tenant-a/day21/event-1111 -> status NEW, amount 1200.50
  tenant-a/day21/event-2222 -> status PAID, amount 1200.50
  tenant-b/day21/event-3333 -> status NEW, amount 75.25
  tenant-c/day21/event-4444 -> DELETED by audit at T1
  session-xxx                 -> EXPIRED by TTL at T2
~~~

Checking only the first three rows lets old SSTable imports **resurrect deleted data** while reports still say PASS. For sensitive data or legally mandated retention, verifying **must-be-absent** keys is a mandatory gate.

### 15.4. Logical checksums require canonical serialization

To hash source and target data:

1. Select comparable columns, including primary keys and business versions.
2. Normalize timestamps to UTC instants, decimals to canonical precision/format, and unordered collections deterministically.
3. Explicitly define NULL vs. absent columns, active TTLs, and deleted-row semantics.
4. Sort by primary key or use a commutative multiset hash.
5. Compute checksums per **bucket/token range** to pinpoint faults rather than one table-wide hash.
6. Version the serialization logic; changing normalization changes hashes even when data did not change.

Matching hashes confer confidence only up to the **chosen algorithm and coverage**. They cannot replace audits for deleted mutations or events lost before a snapshot.

### 15.5. Performance acceptance is also a gate

A migration with 100% accurate rows that spikes `p99 read` 10× and fills a rack's disks is not ready for traffic. Enforce gates across:

- Correctness: PKs, columns, deletes/TTLs, derived tables, CDC catch-up.
- Availability: ring/replicas/CL, timeouts, unavailables.
- Resources: CPU/disk/GC, pending flushes/compactions, network, headroom.
- Application: query families, p95/p99, paging, connection pools, error rates.
- Operability: checkpoints/rollback window, log integrity, on-call readiness.

Declare `MIGRATION_VALIDATED` only alongside **exact coverage scope** (sampled/full) and UTC timestamp—never claim "100% verified" after checking three rows.

## 16. Lab A — Create CSV, load via cqlsh COPY, and verify

**Objective:** practice a small, complete flow: schema → clean CSV → `COPY FROM` → read by PK → `COPY TO` → explain why CSV export is not a physical backup.

**Environment:** Cassandra 4.1/5.0 **single-node lab**, `cqlsh` able to read files on its local host/container, and privileges to create keyspaces/tables. Never run on a live production table. All lab data is synthetic.

### Step 1 — Create lab schema

Run the `CREATE KEYSPACE`/`CREATE TABLE` statements from Section 5.1, then verify:

~~~sql
DESCRIBE KEYSPACE bulk_lab;
DESCRIBE TABLE bulk_lab.events_by_tenant_day;

CONSISTENCY ONE;
~~~

Use `SimpleStrategy`/RF=1 **only in a single-node environment**. Production must set RF/DC and CL per business contract.

### Step 2 — Create a UTF-8 CSV on the machine running cqlsh

On a Linux lab host, for example:

~~~bash
mkdir -p /srv/bulk-lab

cat > /srv/bulk-lab/events.csv <<'CSV'
tenant_id,day,event_time,event_id,status,amount,note
tenant-a,2026-11-21,2026-11-21T08:00:00Z,11111111-1111-1111-1111-111111111111,NEW,1200.50,"Đơn mới, đã xác nhận"
tenant-a,2026-11-21,2026-11-21T08:05:00Z,22222222-2222-2222-2222-222222222222,PAID,1200.50,"Khách ghi: ""giao buổi sáng"""
tenant-b,2026-11-21,2026-11-21T09:10:00Z,33333333-3333-3333-3333-333333333333,NEW,75.25,"Đặt qua ứng dụng"
CSV

wc -l /srv/bulk-lab/events.csv
sha256sum /srv/bulk-lab/events.csv
~~~

`wc -l` should print 4 (1 header + 3 records) because this sample has no newlines inside quoted fields. For CSVs with multiline fields, **physical line count does not equal record count**; use a proper CSV parser instead of treating `wc -l` as authoritative.

### Step 3 — Run rate-limited load

In `cqlsh`:

~~~sql
COPY bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status, amount, note
) FROM '/srv/bulk-lab/events.csv'
WITH HEADER = TRUE
AND INGESTRATE = 100
AND MAXPARSEERRORS = 0
AND MAXINSERTERRORS = 0
AND ERRFILE = '/srv/bulk-lab/copy-errors.csv';
~~~

If `cqlsh` reports file-not-found, check the **client host/container**—never run `chmod 777` on Cassandra's data directory to work around it. On Unicode parse errors, verify the file is real UTF-8 and check for BOM/locale issues. If errors persist, **never continue** by raising error thresholds to unlimited.

### Step 4 — Read and verify exact primary keys

~~~sql
SELECT event_time, event_id, status, amount, note
FROM bulk_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';

SELECT event_time, event_id, status, amount, note
FROM bulk_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-b'
  AND day = '2026-11-21';
~~~

Expected results:

| Partition | Clustering key | Status | Amount | What to verify |
|---|---|---|---:|---|
| `tenant-a/2026-11-21` | 08:00, UUID `1111…` | NEW | 1200.50 | String containing comma |
| `tenant-a/2026-11-21` | 08:05, UUID `2222…` | PAID | 1200.50 | Escaped double quotes preserved |
| `tenant-b/2026-11-21` | 09:10, UUID `3333…` | NEW | 75.25 | Clean Unicode |

Because clustering order is `event_time DESC`, rows inside `tenant-a`'s partition return 08:05 before 08:00 unless the query alters ordering. Never compare raw CSV text order against CQL query order and falsely claim rows were "reordered."

### Step 5 — Export back with COPY TO

~~~sql
COPY bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status, amount, note
) TO '/srv/bulk-lab/exported.csv'
WITH HEADER = TRUE;
~~~

Inspect the exported file with a CSV parser; verify **canonical values and primary keys** rather than expecting byte-for-byte identity with the input file, because CQL may normalize timestamp formatting, decimals, ordering, or quoting. `COPY TO` omits TTL/tombstone/write-timestamp metadata and does not replace snapshots/backups.

### Step 6 — Controlled error test

Create a **separate file** with one invalid row (do not modify the valid source file):

~~~csv
tenant_id,day,event_time,event_id,status,amount,note
tenant-z,2026-11-21,2026-11-21T11:00:00Z,not-a-uuid,NEW,99.99,"invalid key"
~~~

Save it as `/srv/bulk-lab/invalid.csv` and run `COPY FROM` similarly with `MAXPARSEERRORS=0`. Expect the importer to report a parse/type error and **insert zero rows with invalid UUIDs**. Archive the output/error file to inspect the error class; never turn this test into inserting real corrupted rows.

### Step 7 — Should you re-run the same file?

Re-loading the same CSV issues fresh `INSERT`s for the same PKs. In an isolated lab table with no concurrent mutations, you may still see three rows, yet that **does not prove every production replay is safe**. If a value was later edited, deleted, or given a TTL after the initial load, re-importing can stamp newer timestamps and alter state. **Always enforce a checkpoint/idempotency policy.**

## 17. Lab B — Stream SSTables with sstableloader to a separate keyspace

**Objective:** observe the difference between CSV mutation loading and SSTable streaming without overwriting the table populated by `COPY`. Requires extra disk and `nodetool snapshot` privileges; skip this lab if your environment restricts running the loader.

### Step 1 — Capture source state at T0

After Lab A loads cleanly, in `cqlsh`:

~~~sql
SELECT event_time, event_id, status, amount
FROM bulk_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';
~~~

Record the T0 state for all three keys.

### Step 2 — Snapshot only the lab table

~~~bash
# Run nodetool on the lab node; verify version help flags.
nodetool help snapshot
nodetool snapshot \
  --tag bulk_lab_snapshot_01 \
  --table events_by_tenant_day \
  bulk_lab

nodetool listsnapshots
~~~

Do not pass `--skip-flush` here because recent writes must be flushed into SSTables before snapshotting. Snapshots are hard links to SSTables on the node; to create an independent backup, **copy** them into a dedicated staging directory.

### Step 3 — Create a matching target schema in another keyspace

~~~sql
CREATE KEYSPACE IF NOT EXISTS bulk_lab_streamed
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS bulk_lab_streamed.events_by_tenant_day (
    tenant_id text,
    day date,
    event_time timestamp,
    event_id uuid,
    status text,
    amount decimal,
    note text,
    PRIMARY KEY ((tenant_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**If the target already holds data from a prior lab run, you cannot reuse it as an empty table and claim you are testing T0.** Create a uniquely named test keyspace/table or inspect pre-existing state beforehand.

### Step 4 — Write a source mutation after the snapshot

~~~sql
UPDATE bulk_lab.events_by_tenant_day
SET status = 'UPDATED_AFTER_SNAPSHOT'
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
  AND event_time = '2026-11-21T08:00:00Z'
  AND event_id = 11111111-1111-1111-1111-111111111111;
~~~

Now the live source holds `UPDATED_AFTER_SNAPSHOT`, whereas the T0 snapshot holds `NEW`. This proves **`sstableloader` transfers the older snapshot and does not replicate live writes made after T0**.

### Step 5 — Copy SSTables into the staging target path

Example source path (do not copy literal `<table-id>`):

~~~text
/var/lib/cassandra/data/bulk_lab/
  events_by_tenant_day-<table-id>/
    snapshots/bulk_lab_snapshot_01/
      nb-...-Data.db
      nb-...-Statistics.db
      ... SSTable components
~~~

Locate the real directory:

~~~bash
find /var/lib/cassandra/data/bulk_lab \
  -type d -path '*/snapshots/bulk_lab_snapshot_01' -print
~~~

After substituting the real path into `SNAP_DIR`, copy it:

~~~bash
# Only on a LAB host with permission to read snapshots.
SNAP_DIR="/var/lib/cassandra/data/bulk_lab/events_by_tenant_day-<table-id>/snapshots/bulk_lab_snapshot_01"
STAGING="/srv/loader-staging/bulk_lab_streamed/events_by_tenant_day"

mkdir -p "$STAGING"
chmod 700 "$STAGING"

# STAGING must be empty; if not empty, STOP and inspect.
cp -a "$SNAP_DIR"/. "$STAGING"/
find "$STAGING" -maxdepth 1 -type f -print
~~~

If the table spans multiple data directories, collect SSTables from **all relevant directories**. When combining SSTables from multiple nodes with colliding generation names, keep staging folders separated per source set to avoid overwrites.

### Step 6 — Stream to the running lab cluster

~~~bash
sstableloader --help

# 127.0.0.1 is valid only if loader runs on the same host as the lab Cassandra node.
sstableloader \
  --nodes 127.0.0.1 \
  --throttle-mib 8 \
  /srv/loader-staging/bulk_lab_streamed/events_by_tenant_day
~~~

If the native CQL port works yet streaming fails, inspect internode storage ports, TLS, and logs. On format/version incompatibility, **never** hand-edit SSTable bytes; use a compatible binary or an offline format-upgrade runbook on a copy. Never point the loader at live SSTables actively modified by compaction.

### Step 7 — Verify T0 snapshot differs from live T1 source

~~~sql
CONSISTENCY ONE;

SELECT event_id, status
FROM bulk_lab_streamed.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';

SELECT event_id, status
FROM bulk_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';
~~~

Expected in target `bulk_lab_streamed`: event `1111…` remains `NEW` from T0. In source: that event is now `UPDATED_AFTER_SNAPSHOT`. This intentional contrast illustrates **SSTable snapshot vs. live CQL mutation**.

If rows are missing in target, check loader output, source snapshot coverage, table path/schema, partitioner/format, and TTL/tombstones—never blindly re-run without identifying the cause.

### Step 8 — Observe cluster effects

~~~bash
nodetool status
nodetool netstats
nodetool tablestats bulk_lab_streamed.events_by_tenant_day
nodetool compactionstats
~~~

Post-load, SSTables may compact and disk I/O may rise. With three rows, the lab is too small to benchmark loader throughput. Pass the lab when **target CQL matches T0** and you can explain why T1 appears only in the source.

## 18. Comparing outcomes of both labs

| Criterion | Lab A: `COPY FROM` | Lab B: `sstableloader` |
|---|---|---|
| Input | Client-side CSV | Snapshot SSTable components |
| Target | `bulk_lab.events_by_tenant_day` | `bulk_lab_streamed.events_by_tenant_day` |
| Data write path | New CQL mutations | SSTable streaming |
| Write timestamps | Determined by CQL write/import semantics | Preserves timestamps stored in SSTables |
| TTL/tombstone history | CSV omits metadata | SSTables carry corresponding metadata |
| Target topology | CQL coordinator/replicas per RF/CL | Streams to natural replicas per target ring |
| Partition key transform | Possible via ETL step before import | No: files must match target schema/token semantics |
| When source continues receiving writes | CSV snapshot does not auto-catch up | Snapshot SSTables do not auto-catch up either |
| Verification | Primary keys, values, error records | Source ranges/files, streaming, data/replicas |
| Strength | Simple for small CSVs | Efficient when valid SSTables already exist |

**Never use a tiny-row lab to declare one tool "faster."** DSBulk/Spark/COPY/`sstableloader` target **different inputs and problems**; fair performance comparisons require equivalent datasets, topologies, RF/CL, page sizes, and resource headroom.

## 19. Java Driver 4.x: importer with prepared statements and bounded in-flight window

When CSVs require custom validation, multi-source mapping, source event IDs, or business-version checks, you can build a **custom Java importer**. Writing your own means owning backpressure, errors, retries, progress, and checkpoints. Never open a new `CqlSession` per row or fire a million unthrottled `executeAsync()` calls.

### 19.1. Preparing parsed and validated records

Assume the Java pipeline receives each `Event` already parsed by a standard CSV library (Apache Commons CSV, Jackson CSV, or equivalent), with UUIDs, dates, UTC timestamps, decimals, primary keys, and business rules validated. **The snippet below is not a CSV parser**: it handles only Cassandra writes.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public final class BoundedEventImporter {
    public record Event(
        String tenantId,
        LocalDate day,
        Instant eventTime,
        UUID eventId,
        String status,
        BigDecimal amount,
        String note
    ) {}

    private static final int MAX_IN_FLIGHT = 16; // LAB example
    private final CqlSession session;
    private final PreparedStatement insert;

    public BoundedEventImporter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO bulk_lab.events_by_tenant_day " +
            "(tenant_id, day, event_time, event_id, status, amount, note) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)");
    }

    public void importEvents(Iterable<Event> source) {
        List<CompletionStage<AsyncResultSet>> window =
            new ArrayList<>(MAX_IN_FLIGHT);

        for (Event row : source) {
            validate(row);

            BoundStatement statement = insert.bind(
                    row.tenantId(),
                    row.day(),
                    row.eventTime(),
                    row.eventId(),
                    row.status(),
                    row.amount(),
                    row.note())
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true);

            window.add(session.executeAsync(statement));
            if (window.size() == MAX_IN_FLIGHT) {
                awaitWindow(window);
            }
        }
        if (!window.isEmpty()) {
            awaitWindow(window);
        }
    }

    private static void validate(Event row) {
        if (row.tenantId() == null || row.tenantId().isBlank()
            || row.day() == null || row.eventTime() == null
            || row.eventId() == null || row.status() == null) {
            throw new IllegalArgumentException("Invalid source record");
        }
    }

    private static void awaitWindow(
            List<CompletionStage<AsyncResultSet>> window) {

        CompletableFuture<?>[] futures = window.stream()
            .map(CompletionStage::toCompletableFuture)
            .toArray(CompletableFuture[]::new);

        // Drain up to MAX_IN_FLIGHT requests before issuing the next window.
        CompletableFuture.allOf(futures).join();
        window.clear();
    }
}
~~~

Reading the code:

1. `PreparedStatement` is prepared once, giving the driver routing-key metadata when the partition key is bound properly.
2. `MAX_IN_FLIGHT=16` bounds **concurrent pending requests**, not 16 QPS. Actual rate depends on latency and server load.
3. When `allOf().join()` throws an exception, **other requests in the window may already have succeeded**. Never mark the entire window failed or complete; production pipelines must track **record IDs + per-request outcomes** and handle unknown outcomes.
4. `setIdempotent(true)` only signals the **driver retry policy**. Set it only when semantically idempotent: same PK, same values/timestamp/TTL policy; **never** apply it mechanically to counters/LWTs.
5. `CL=ONE` fits the RF=1 lab, not multi-replica production. Preserve `LOCAL_QUORUM` or the app's required CL in production designs.
6. The code assumes `source` normalized nulls; binding `note=null` can create tombstone semantics. To skip updating `note`, use **UNSET or a column-subset statement** per version/driver rather than assuming null means "ignore."
7. Never log source payloads/PII into metric logs. Log event IDs/checkpoints and error categories.

### 19.2. Why this code is only an importer skeleton

For production, add:

| Aspect | Required implementation |
|---|---|
| Parser | Compliant CSV/JSON streaming reader, encoding checks, schema validation |
| Rate control | Token bucket or adaptive concurrency driven by SLOs and pending queues |
| Retries | Exponential backoff, jitter, transient vs. permanent classification, idempotency |
| Checkpoints | Source offsets/manifests, per-PK/event-ID status, never ACK unknown outcomes |
| Error sink | Quarantine malformed records; log masked errors |
| Metrics | Input/accepted/failed/unknown rates, p95/p99, in-flight/retries |
| Credentials | Secrets manager, TLS, least-privilege CQL role |
| Lifecycle | Session reuse, clean shutdown awaiting in-flight futures before close |
| Versions | Cassandra/driver compatibility, prepared statement/schema change handling |
| Correctness | Backfill/catch-up + reconciliation audits, TTL/timestamp/DELETE preservation |

**Never rely on a fixed per-instance `MAX_IN_FLIGHT` as your sole backpressure mechanism** if a batch job spawns multiple parallel writers/processes: enforce total job concurrency, not just one Java instance's window.

### 19.3. Limiting retries and timeouts

A client write timeout does not prove Cassandra **did not write**. The coordinator/replicas may have applied it while the ACK dropped or arrived late. When retrying:

- Keep source event IDs and primary keys immutable.
- Where business sequences/timestamps exist, protect update order.
- Never inflate `request.timeout` sky-high just to make `COPY`/Java jobs "stop erroring."
- Never lower CL casually to boost throughput.
- Cap max attempts/backoff and route **unknown** outcomes to reconciliation.
- Run selective retries only after the cluster stabilizes; avoid retry storms while disk/GC are overloaded.

### 19.4. Monitoring Java and Cassandra simultaneously

~~~text
Java:
  source rows/s
  normalized/invalid rows/s
  requests in-flight, successful/failed/unknown
  request p95/p99 by target table + CL
  retries and pool exhaustion

Cassandra:
  ClientRequest.Write.Latency/Timeouts
  Table.WriteLatency, Memtable/CommitLog
  PendingFlushes, PendingCompactions
  node CPU/GC/disk await/network
  replica liveness/ring and disk free

Business:
  unique primary keys loaded
  source-to-target match rate
  CDC catch-up lag / watermark
  must-be-absent DELETE/expired keys
~~~

**Successful optimization** raises **verified-correct hourly throughput** while preserving headroom and SLOs—not merely firing more `executeAsync` calls per second.

## 20. Real-world scenarios for tool selection and troubleshooting

### Case A — Small CSV, matching schema, demo needed today

**Input:** 3,000 rows, 7 simple columns, clear PK, single-node lab cluster.  
**Decision:** `cqlsh COPY FROM` is the simplest choice—save the error file and verify by PK. Do not spin up Spark for a few hundred KiB.

**Key point:** simple does not mean skipping baselines; CSVs can still break UUIDs/dates/decimals or carry duplicate PKs.

### Case B — 100 GB CSV across thousands of files needing selective error replay

**Decision:** Consider DSBulk with explicit mapping, a dry run on a subset, concurrency caps, operation logs, and error files. If transformations are complex, choose Spark/custom ETL.  
**Avoid:** Pushing everything through one uncheckpointed `cqlsh COPY` or cranking `NUMPROCESSES` until the cluster times out.

### Case C — Source is already SSTables, target topology differs

**Input:** Snapshot from a 3-node ring, target is 5 nodes/RF3, same partitioner and compatible SSTable format.  
**Decision:** `sstableloader` from staging for ring-aware streaming to target replicas.  
**Avoid:** Copying files 1:1 node A→P, B→Q and calling `refresh`.

### Case D — Old table partitioned by tenant, new table partitioned by tenant/day

**Decision:** Use DSBulk/Spark/Java to emit mutations with the right `day`; `sstableloader` **cannot transform the primary-key structure** of old SSTables.  
**Risk:** Wrong timezone day buckets, duplicate event IDs, or dropped events around midnight.

### Case E — Backfill collides with live status updates

**Situation:** Source snapshot holds `NEW`, app just updated target to `PAID`, then `COPY FROM` writes `NEW` with a fresh timestamp.  
**Decision:** `STOP`, inspect event versions/watermarks, recover the newer mutations, and switch to isolated backfill/catch-up.  
**Avoid:** Re-importing the snapshot again hoping last-write-wins somehow picks the business winner.

### Case F — Java bulk importer raises in-flight to 500 and write timeouts explode

**Hypothesis:** Coordinator/replicas/disks saturated, and driver retries multiply load.  
**Action:** Throttle concurrency down cleanly; inspect `tpstats`, `compactionstats`, disk latency, and CL. Never let the importer keep enqueueing millions of futures while older requests stall.

### Case G — Rows loaded accurately, yet `WHERE status='PAID'` stays slow

**Reason:** Bulk loaders do not alter the data model. If `status` is only a regular column and queries lack a matching partition key or index, queries either require filtering or are rejected.  
**Action:** Design query-driven tables/indexes and benchmark rather than blaming `COPY`.

### Case H — CSV export then re-import breaks TTLs

**Reason:** CSV lacks original expirations; `COPY FROM` writes mutations under current TTL/target defaults.  
**Action:** Block cutover, identify rows that should have expired, use a metadata-complete source or compute accurate remaining TTLs. Never "resurrect" sessions/PII slated for expiry.

### Case I — DSBulk error files contain sensitive data

**Risk:** `*.bad` files and operation logs can hold raw source lines; broad file sharing leaks data.  
**Action:** Restrict ACLs, encrypt, mask, enforce retention, set safe log levels, and keep credentials out of CLI arguments/process lists using secure secret mechanisms.

### Case J — `sstableloader` reaches native CQL yet streaming fails

**Possibilities:** Storage port/TLS/firewall/broadcast address blocked; source SSTable format/partitioner/schema mismatch.  
**Action:** Check `--help`/logs/network connectivity to all natural endpoints, not just initial hosts; keep original backups intact and never hand-edit SSTables.

### Case K — DSBulk or Spark reports "100% processed," yet one DC lacks data

**Possibilities:** Local quorum in `dc1` did not verify `dc2`, misconfigured RF/DC, a replica was DOWN, or source range coverage was incomplete.  
**Action:** Inspect topology, logs/repair, validate per DC at proper CL, and sample across token ranges—never equate transport success with replica correctness.

### Case L — Streaming many SSTables onto a nearly full cluster

**Risk:** Streaming adds new SSTables, compaction needs temp space, snapshots pin old files, and app p99 degrades.  
**Decision:** Halt ramp-up, assess disk headroom and capacity; never blindly force major compactions or delete SSTables/tombstones to free space.

## 21. Checklist for choosing and running a safe bulk load

### 21.1. Before loading

- [ ] Goal clearly defined as **initial load, schema migration, backfill, or restore**.
- [ ] Source format identified (CSV/JSON/Parquet/event log vs. SSTables) and matching tool chosen.
- [ ] Authoritative owner/source-of-truth and trusted recovery point/watermark established.
- [ ] Row count, bytes, distinct partition keys, p95/p99 partition size, and skew measured.
- [ ] Target schema supports **required queries**, with partition/clustering keys reviewed.
- [ ] CQL types, UUID/date/timestamp timezones, decimals/collections/UDT mappings verified.
- [ ] Primary-key fields non-null; explicit policies for duplicate/invalid rows.
- [ ] Per-DC RF, CL, ring, and natural replica placement verified.
- [ ] If using SSTables: format/partitioner/table schema, file components/checksums, and source range coverage verified.
- [ ] If using `sstableloader`: `keyspace/table` directory, initial hosts, storage ports/TLS, and staging verified.
- [ ] If using `COPY`/DSBulk: CSV encoding/headers/quoting/NULLVAL and error files verified.
- [ ] If using Spark/Java: dependency versions, mappers, concurrency, retries, and checkpoints tested.
- [ ] No concurrent major topology change/repair without a capacity plan.
- [ ] Baseline p99, throughput, disk/GC, memtables/flushes/compactions, and replica health captured.
- [ ] Timestamps, TTLs, tombstones, GDPR/retention, and **must-be-absent** keys evaluated.
- [ ] Strategy defined for ongoing writes: pause, dual-write/CDC, or isolated backfill.
- [ ] Tested in lab/staging with samples and independent backups ready.
- [ ] `GO/HOLD/STOP` triggers and rollback/escalation owners defined.

### 21.2. During loading

- [ ] Tool targets the intended cluster, local DC, and keyspace/table, confirmed by operator.
- [ ] Input files/checksums and schema hash archived under the run ID.
- [ ] Load broken into small enough batches/chunks for resumability and reconciliation.
- [ ] Concurrency/rate limits enforced, stepping up only while p99 and disk headroom stay healthy.
- [ ] Parse/type errors handled separately from write timeouts/unknown outcomes.
- [ ] Error/quarantine files preserved until reconciled, never overwritten or deleted early.
- [ ] `COPY FROM` blocked from stamping fresh timestamps onto live tables at risk of overwriting newer writes.
- [ ] No giant cross-partition BATCHes or disabling CL/repair/tombstone safeguards for speed.
- [ ] Flush/compaction queues, disk await, node liveness, and Java request p99 monitored.
- [ ] Checkpoints track **VERIFIED** chunks, not merely "processed."
- [ ] For SSTable streams, track per-node/per-DC transfers and source file sets, not just total bytes.

### 21.3. After loading

- [ ] Source totals, parsed, rejected, attempts, confirmed writes, and unknown outcomes reconcile with manifest.
- [ ] All source chunks/token ranges verified; zero skipped source files.
- [ ] PKs/column values/versions/ordering/TTLs/DELETEs pass audit.
- [ ] Target schema, indexes/derived tables, and query patterns behave as expected.
- [ ] Required natural replicas/DCs hold data; repair/backfill follows runbook.
- [ ] Java query families meet p95/p99, timeout, and original consistency targets.
- [ ] No runaway compaction/flush backlogs or depleted disk headroom.
- [ ] CDC/outbox catch-up lag meets criteria; post-snapshot writes preserved.
- [ ] Feature-flag canary reads/cutover tested with complete-data rollback viable.
- [ ] **Must-be-absent** status verified for DELETED/TTL-expired rows.
- [ ] Staging, error logs, source snapshots, and credentials retained/cleaned per policy.
- [ ] Coverage report (full/sampled), actual RPO/RTO, owner, and residual risks completed.

## 22. Self-assessment questions

**Q1.** You have a 10,000-row static CSV and a single-node lab cluster. Which tool should you start with?  
**Guidance:** `cqlsh COPY FROM` is usually simplest if schema and types are clean, paired with sampling/error checks/validation.

**Q2.** You have SSTables from cluster A, and target cluster B changed node count and RF. Why is `sstableloader` better than `nodetool import` on each node?  
**Guidance:** It streams according to the target ring's natural replicas and token ownership rather than arbitrary local file copies.

**Q3.** Does `dsbulk load` require the target table to exist with the right partition key?  
**Guidance:** Yes; mapping transforms fields, not the underlying data model or replica placement.

**Q4.** A CSV starts with `tenant_id,day,event_time,...`. Why is `HEADER = TRUE` needed with `COPY FROM`?  
**Guidance:** Otherwise the column-name header line is parsed as a data record, causing type or PK errors.

**Q5.** Why can `"Khách ghi: ""giao sáng"""` not be split with `String.split(",")`?  
**Guidance:** CSVs use quoting/escaped quotes and can embed commas and newlines inside fields.

**Q6.** Does `COPY TO` followed by `COPY FROM` preserve tombstones, original TTLs, and per-cell write timestamps?  
**Guidance:** No; CSV is a logical export, not an SSTable backup.

**Q7.** `tenant-a/day21` contains millions of events. Does raising `NUMPROCESSES` solve the hot partition?  
**Guidance:** No; the natural replica set owning that partition remains the bottleneck—fix bucket/workload design instead.

**Q8.** Does DSBulk `--dryRun` write data to the cluster?  
**Guidance:** No; it validates inputs and mappings before a real load.

**Q9.** Does DSBulk `--engine.maxConcurrentQueries 16` cap throughput at exactly 16 rows/s?  
**Guidance:** No; it caps concurrent in-flight queries, while throughput depends on latency and batching.

**Q10.** Why can a Spark job reading Parquet not simply call `repartition(1000)` and assume load is balanced in Cassandra?  
**Guidance:** Hot partition keys still route to the same tokens/replicas; Spark shuffles do not alter Cassandra partition distribution.

**Q11.** If the old table has `PRIMARY KEY ((tenant_id),...)`, can `ALTER TABLE` add `day` into the partition key?  
**Guidance:** No; you need a new table, backfill, and access-pattern cutover.

**Q12.** Target already received a `PAID` update at T1, then a CSV backfill from snapshot T0 containing `NEW` runs at T2. What is the risk?  
**Guidance:** `COPY` generates newer write timestamps and can overwrite `PAID` with `NEW`.

**Q13.** Why is retrying `UPDATE counter=counter+1` not idempotent like re-importing a row with a stable key?  
**Guidance:** Counter increments can apply multiple times, corrupting the total.

**Q14.** On a client timeout, can the importer immediately mark the write as "did not happen"?  
**Guidance:** No; the ACK may have dropped even though replicas applied the write—unknown-outcome reconciliation is required.

**Q15.** A row had TTL 3600 set 90 minutes before CSV re-import. Why is `USING TTL 3600` during import wrong if preserving original expiration?  
**Guidance:** It gives the data another full hour of life instead of treating it as expired.

**Q16.** An SSTable stream finished, yet `SELECT` returns 0 rows. Name at least three possible causes.  
**Guidance:** Wrong source ranges/schema/PK, expired TTLs, masking by newer tombstones, or reading from an under-replicated DC.

**Q17.** Why is a matching `COUNT(*)` insufficient to sign off a migration?  
**Guidance:** Primary keys/values/timestamps/deletes can still differ, and scanning triggers heavy cluster load.

**Q18.** Does `LOCAL_QUORUM` succeeding in `dc1` confirm `dc2` holds all data?  
**Guidance:** No. Local quorum verifies only the local DC.

**Q19.** Why keep the original snapshot/backup intact before running `sstableloader`?  
**Guidance:** Staging/streaming/upgrades can fail and require integrity checks or retries; backups remain the recovery source.

**Q20.** When the Java importer reaches 16 in-flight requests, what should the code do before sending more?  
**Guidance:** Await/drain the in-flight window to bound concurrency; never spawn unbounded futures.

**Q21.** After dual-write, V1 stopped receiving writes for 48 hours. Can you roll back the read flag to V1 immediately?  
**Guidance:** No, if V1 is missing recent deltas; reverse sync/replay/validation is needed first.

**Q22.** An importer reports 1,000 rows processed, 998 writes confirmed, and 2 unknown timeouts. Can the chunk be marked VERIFIED?  
**Guidance:** Not yet; resolve and reconcile the two uncertain outcomes first.

**Q23.** Why avoid using one giant logged batch to speed up loading across many partitions?  
**Guidance:** Batchlog/coordinator overhead, higher latency/timeouts, and it is not a SQL bulk transaction.

**Q24.** If compaction backlog rises after streaming while read/write SLAs still hold, must you stop immediately?  
**Guidance:** Watch trends, capacity, and backlog drain rather than one snapshot; throttle or stop if disk headroom or SLOs are threatened.

## 23. Summary

~~~text
                     DATA LOAD PLAN
                           |
                    Classify SOURCE
               /           |           \
           CSV/JSON     SSTables     ETL/Event log
              |            |            |
       COPY / DSBulk  sstableloader  Spark / Java
              |            |            |
       Typed mutations Replica stream Validated mutations
               \           |           /
                \          |          /
                 SCHEMA / PARTITION KEY
                           |
                   TARGET RING / RF / CL
                           |
                RATE LIMIT + CHECKPOINTS
                           |
             +-------------+-------------+
             |             |             |
          TRANSPORT     REPLICA       BUSINESS
          ERRORS        COVERAGE      CORRECTNESS
             |             |             |
             +-------------+-------------+
                           |
                     CATCH-UP / CUTOVER
                           |
                     ROLLBACK WINDOW
                           |
                   MIGRATION_VALIDATED
~~~

**Most important rule:** choose a bulk loader based on **source data and migration goal**, not a slogan like "which tool is fastest." `cqlsh COPY` is convenient for small/medium CSVs, DSBulk adds explicit mapping/error logs and concurrency control, Spark handles distributed ETL, Java Driver serves custom business pipelines, and `sstableloader` streams SSTables to natural replicas on a target ring. Every method is reliable only when **schema/partition keys, timestamps/TTLs, idempotency, RF/DC, SLOs, and reconciliation audits** are engineered with discipline. Loading the files is **the start of validation**, not the end of the migration.

## References

- [Apache Cassandra — cqlsh COPY TO/FROM](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html) — syntax, `HEADER`, `NULLVAL`, `INGESTRATE`, `ERRFILE`, `MAXATTEMPTS`, and COPY limitations.
- [Apache Cassandra — Bulk Loading](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/bulk_loading.html) — `sstableloader`, staging layout, `nodetool import`, and replication-aware streaming.
- [Apache Cassandra — sstableloader](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstableloader.html) — `--nodes`, `--throttle-mib`, native/streaming ports, and source SSTables.
- [Apache Cassandra — nodetool import](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/import.html) — local import, token verification, and repaired metadata.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — query-driven design, partition keys, clustering keys, and denormalization.
- [Apache Cassandra — CQL DML](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — `INSERT`, `UPDATE`, `USING TIMESTAMP`, `USING TTL`, `BATCH`, and CQL semantics.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — `ClientRequest`, `Table`, memtables, compaction, and thread pools.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — replica convergence and repair boundaries.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — DELETE/TTL, grace periods, and zombie data.
- [DataStax Bulk Loader — Load data](https://docs.datastax.com/en/dsbulk/developing/simple-load.html) — `dsbulk load`, CSV/JSON mapping, and `--dryRun`.
- [DataStax Bulk Loader — Engine options](https://docs.datastax.com/en/dsbulk/reference/engine-options.html) — `--engine.maxConcurrentQueries` and load throttling.
- [DataStax Bulk Loader — Logging options](https://docs.datastax.com/en/dsbulk/reference/logging-options.html) — operation logs, `connector.bad`, `mapping.bad`, and `load.bad`.
- [Apache Spark Cassandra Connector — DataFrames](https://github.com/apache/cassandra-spark-connector/blob/trunk/doc/14_data_frames.md) — `format("cassandra")`, `keyspace`, `table`, and read/write APIs.
- [DataStax Java Driver 4.17 — Prepared statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/) — bound metadata, routing keys, and prepared CQL.
- [DataStax Java Driver 4.17 — Query idempotence](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/idempotence/) — identifying idempotent statements and retry risks.
- [DataStax Java Driver 4.17 — Metrics](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metrics/) — session/node metrics, timeouts, and request latency.
