# COPY in cqlsh, Scale Limits, and Alternative Data Loading Tools

## 1. What Is `COPY` and When Is It Used?

**Apache Cassandra** is a **distributed wide-column database**. In real environments, data loading must consider partition keys, clustering columns, replication factor, consistency level, active node count, and compaction/streaming load. Within the **Tools and Connections** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, the `COPY` command in **cqlsh** helps practice CSV import/export and recognize operational limits in multi-node systems.

`COPY` is a **cqlsh utility command**, not general CQL syntax that a Java application can send via `CqlSession.execute("COPY ...")`. It works in two directions:

- **`COPY ... FROM 'file.csv'`:** cqlsh reads a CSV from the machine where the **cqlsh process is running**, converting rows into write operations to an **existing table** in Cassandra.
- **`COPY ... TO 'file.csv'`:** cqlsh reads table data over the Cassandra native protocol and writes a CSV on the machine where the **cqlsh process is running**.

Both operations use the same application → native protocol path, typically TCP **9042**. The coordinator and replicas still process CQL according to schema, replication, and consistency; `COPY` does not create a separate channel that "bypasses" Cassandra.

| Scenario | Is `COPY` Suitable? | Notes |
| --- | --- | --- |
| Testing 50–1,000 sample rows in a lab | **Yes** | Easy to inspect the CSV and cross-check error counts. |
| Importing a small/medium CSV with a known schema | **Possibly** | Evaluate load and verify per partition. |
| Exporting a small dataset for exploration or manual inspection | **Possibly** | CSV is a data export, not a complete backup. |
| Migrating very large datasets across clusters | **Usually not the first choice** | Use dedicated bulk/streaming tools or distributed pipelines. |
| Backing up and restoring exact schema, TTL, tombstones, permissions, and point-in-time data | **No** | Consider snapshots/SSTables and proper backup/restore procedures. |
| Continuous change synchronization between systems | **No** | Requires a CDC/streaming pipeline or checkpointed connector. |

**Lesson objectives:** run `COPY FROM` and `COPY TO` in a controlled manner; understand column mapping, CSV formatting, data errors, and primary keys; and know how to choose alternative tools when exceeding cqlsh's scale.

## 2. Where Does `COPY` Interact with Cassandra's Architecture?

~~~mermaid
flowchart LR
    CSV["CSV file on machine running cqlsh"] -->|"COPY FROM: read and convert rows"| SH["cqlsh"]
    SH -->|"Native CQL / TCP 9042"| CO["Coordinator node"]
    CO -->|"Write by token/partition and CL"| R1["Replica A"]
    CO -->|"Write by token/partition and CL"| R2["Replica B"]
    CO -->|"Write by token/partition and CL"| R3["Replica C"]
    R1 -.->|"Read via coordinator"| CO
    R2 -.->|"Read via coordinator"| CO
    CO -.->|"COPY TO: CQL results"| SH
    SH -.->|"Write CSV"| OUT["Export file on machine running cqlsh"]
~~~

This diagram depicts a multi-replica cluster. In a **single-node RF = 1** lab, only one replica exists; in multi-datacenter clusters, replicas and consistency are determined by the real configuration.

Important consequences:

1. `COPY FROM` **does not choose which node stores the data**. Cassandra computes the token from the **partition key** and selects replicas via the replication strategy.
2. `COPY` is still subject to **network latency, native protocol, authentication, authorization, and consistency** just like normal CQL operations.
3. `COPY TO` reads via normal requests; it **does not guarantee a consistent snapshot across the entire export duration** while data continues changing.
4. CSV files live on the **cqlsh client side**, not automatically on all Cassandra nodes.
5. `COPY` does not automatically create keyspaces, tables, indexes, roles, permissions, or replication policies. The schema must be prepared beforehand.

## 3. Lab Setup: Query-Driven Table Design Before Importing

### 3.1. Prerequisites

This example assumes:

- A single-node Cassandra instance for the lab, with cqlsh able to connect to `127.0.0.1:9042`.
- Permissions to create keyspaces/tables and read/write sample data.
- A simple UTF-8 CSV file with verified headers and column order.
- Commands run strictly in a **lab environment**, not unconditionally applied to production.

Open cqlsh from the terminal:

~~~bash
cqlsh 127.0.0.1 9042
~~~

At the cqlsh prompt:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS cqlsh_copy_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS cqlsh_copy_lab.readings_by_device_day (
  device_id text,
  reading_day date,
  read_at timestamp,
  reading_id uuid,
  metric text,
  value double,
  PRIMARY KEY ((device_id, reading_day), read_at, reading_id)
) WITH CLUSTERING ORDER BY (read_at DESC, reading_id ASC);

DESCRIBE KEYSPACE cqlsh_copy_lab;
DESCRIBE TABLE cqlsh_copy_lab.readings_by_device_day;
~~~

In this table:

- **Composite partition key**: `(device_id, reading_day)`. Records for one device on one day share the same partition.
- **Clustering columns**: `read_at` and `reading_id`. They sort records chronologically and keep primary keys unique when multiple events occur at the same timestamp.
- **Target query**: read records for **one device on one day**, optionally bounded in time via clustering columns.
- **RF = 1 and `SimpleStrategy`**: strictly for practicing on a single node. Multi-datacenter systems typically use `NetworkTopologyStrategy` and appropriate per-DC replication factors.

When designing for large datasets, evaluate record counts **per partition**. A standalone `device_id` partition key can cause unbounded partition growth; adding `reading_day` is an example of **time bucketing**, where bucket width should reflect actual ingestion rate.

### 3.2. Creating a CSV File with Matching Columns and Types

Create a text file named `readings.csv` on the **machine running cqlsh** with the following content:

~~~csv
device_id,reading_day,read_at,reading_id,metric,value
sensor-01,2026-11-21,2026-11-21T01:00:00Z,11111111-1111-4111-8111-111111111111,temperature,25.1
sensor-01,2026-11-21,2026-11-21T01:05:00Z,22222222-2222-4222-8222-222222222222,temperature,25.3
sensor-02,2026-11-21,2026-11-21T01:02:00Z,33333333-3333-4333-8333-333333333333,humidity,60.0
sensor-02,2026-11-22,2026-11-22T01:02:00Z,44444444-4444-4444-8444-444444444444,humidity,61.0
~~~

Verify before importing:

| CSV Column | Cassandra Type | Requirement |
| --- | --- | --- |
| `device_id` | `text` | Must not be blank since it is part of the partition key. |
| `reading_day` | `date` | Valid date format, e.g., `2026-11-21`. |
| `read_at` | `timestamp` | Prefer explicit timezone, e.g., `Z` suffix (UTC). |
| `reading_id` | `uuid` | Valid UUID; uniquely distinguishes rows sharing the same timestamp. |
| `metric` | `text` | String describing the measurement type. |
| `value` | `double` | Numeric value using a decimal dot per sample data syntax. |

**Do not assume CSV headers generate a schema.** The table already has a defined structure. The column list in `COPY` must match the file's data order; `HEADER = TRUE` identifies/skips the header line and does not guarantee arbitrary column reordering by name.

## 4. `COPY FROM`: Loading CSV into an Existing Table

### 4.1. Syntax

At the `cqlsh>` prompt:

~~~sql
COPY cqlsh_copy_lab.readings_by_device_day
  (device_id, reading_day, read_at, reading_id, metric, value)
FROM 'readings.csv'
WITH HEADER = TRUE;
~~~

Run this only after `readings.csv` exists and is readable from the **cqlsh process**. Keyspace and table names are fully qualified to avoid `USE` context mistakes.

If the file is not in the working directory, pass an **absolute path** suitable for your environment:

~~~sql
-- Example on a Linux environment where the file actually exists at this path.
COPY cqlsh_copy_lab.readings_by_device_day
  (device_id, reading_day, read_at, reading_id, metric, value)
FROM '/workspace/import/readings.csv'
WITH HEADER = TRUE;
~~~

On Windows, paths and quoting must match cqlsh/Python and the active shell. Do not assume cqlsh reads files on the **Cassandra server** merely because the command runs in a cqlsh session connected to that server.

### 4.2. Verifying Data by Partition Key

~~~sql
-- Check sensor-01 on 2026-11-21.
SELECT read_at, metric, value
FROM cqlsh_copy_lab.readings_by_device_day
WHERE device_id = 'sensor-01'
  AND reading_day = '2026-11-21';

-- Check sensor-02 on 2026-11-21.
SELECT read_at, metric, value
FROM cqlsh_copy_lab.readings_by_device_day
WHERE device_id = 'sensor-02'
  AND reading_day = '2026-11-21';

-- Check sensor-02 on 2026-11-22.
SELECT read_at, metric, value
FROM cqlsh_copy_lab.readings_by_device_day
WHERE device_id = 'sensor-02'
  AND reading_day = '2026-11-22';
~~~

Expected results:

| Partition | Expected Rows | Values |
| --- | ---: | --- |
| `('sensor-01', '2026-11-21')` | 2 | `25.3` and `25.1`, ordered by `read_at` descending. |
| `('sensor-02', '2026-11-21')` | 1 | `60.0`. |
| `('sensor-02', '2026-11-22')` | 1 | `61.0`. |

Checking known partitions individually avoids running a full-table `SELECT COUNT(*) FROM keyspace.table` on large datasets. **Full-table `COUNT(*)` is not a free bulk migration check**; it can scan vast numbers of partitions and impose heavy load.

### 4.3. Does Re-Running `COPY FROM` Create Duplicate Data?

In Cassandra, `INSERT` with the same primary key generally behaves as an **upsert**. With a file containing **fixed** UUIDs and timestamps, re-running `COPY FROM` overwrites cells in the same rows rather than creating new rows. However:

- If the CSV generates a new `reading_id` each run, those lines become **different rows**.
- If values, write timestamps, TTLs, or other fields change, the impact of re-importing must be evaluated.
- If multiple writers modify the same primary key concurrently, file execution order does not guarantee the final data reflects "the last imported line" by wall-clock time. Cassandra resolves conflicts via cell timestamps.
- `COPY FROM` **does not** turn the entire file into a transaction. Rows already written are not automatically rolled back when another row fails.

Therefore, design **stable primary keys, pipeline idempotency**, and post-failure re-run procedures **before** loading large datasets.

## 5. `COPY TO`: Exporting CSV and Understanding Export Limits

### 5.1. Exporting the Full Table in the Lab

~~~sql
COPY cqlsh_copy_lab.readings_by_device_day
  (device_id, reading_day, read_at, reading_id, metric, value)
TO 'readings-export.csv'
WITH HEADER = TRUE;
~~~

`readings-export.csv` is written on the **machine/environment running cqlsh**. The expected data row count in the lab is 4 (excluding the header), assuming no older data existed in the table. Formatting of timestamps, numbers, and quotes may differ from the original input file; compare **parsed values** rather than requiring byte-for-byte string matching.

### 5.2. Exporting a Subset of Columns

~~~sql
COPY cqlsh_copy_lab.readings_by_device_day
  (device_id, reading_day, read_at, metric, value)
TO 'readings-summary.csv'
WITH HEADER = TRUE;
~~~

When exporting to load into another table, verify the **target primary key** carefully. For instance, `readings-summary.csv` omits `reading_id`: it is **insufficient** to re-import back into the original table because a primary key component is missing. A "valid CSV" does not equal "data sufficient for restoration."

### 5.3. `COPY TO` Is Not `SELECT` with `WHERE`

`COPY ... TO` is designed to export table data and select **columns**, not to replace an arbitrary `SELECT ... WHERE ...` query. If you only want to inspect a small partition, run a `SELECT` by partition key or a controlled export application; do not assume `COPY TO` supports arbitrary CQL `WHERE` filtering.

**Do not rely on exported CSV row order** as a global cluster ordering. Clustering order defines ordering only within a partition; Cassandra does not guarantee partitions are scanned in any business-meaningful order.

### 5.4. `COPY TO` Is Not a Consistent Backup

A CSV file produced by `COPY TO` does not fully preserve:

- Keyspace/table definitions, replication strategies, indexes, roles, and `GRANT` permissions.
- Cell-level metadata such as **write timestamps**, **remaining TTL**, or full tombstone/deletion semantics.
- A **global point-in-time snapshot** while applications write concurrently; different export pages may reflect different points in time.
- Full formatting/data details for special types such as collections/UDTs/blobs without dedicated encoding and testing.

Therefore, using `COPY TO` for testing or targeted exports is reasonable, but **never treat a CSV file as a direct substitute for full cluster backup/snapshot recovery**.

## 6. CSV Pitfalls That Cause Silent Data Corruption

### 6.1. Fields Containing Commas, Quotes, and Newlines

CSVs must follow consistent escaping/quoting rules. With commas as delimiters, values like `"sensor, north"` must be quoted properly. Example:

~~~csv
device_id,reading_day,read_at,reading_id,metric,value
"sensor,north",2026-11-21,2026-11-21T01:00:00Z,55555555-5555-4555-8555-555555555555,temperature,23.4
~~~

Never use `String.split(",")` to parse real-world CSVs if values may contain commas, quotes, or embedded newlines. Use a standards-compliant CSV parser and test encoding/escaping.

cqlsh provides `COPY` options for delimiter, quote, escape, header, and other parameters. Example when using semicolons:

~~~sql
-- Use only when the input file is actually delimited with ';'.
COPY cqlsh_copy_lab.readings_by_device_day
  (device_id, reading_day, read_at, reading_id, metric, value)
FROM 'readings-semicolon.csv'
WITH HEADER = TRUE AND DELIMITER = ';';
~~~

In this example, `readings-semicolon.csv` must have been **created with `;` as its delimiter** beforehand. Do not run this command against the original comma-delimited `readings.csv`.

### 6.2. Empty Values, NULLs, and Data Types

Cases that must be explicitly designed:

- **Blank fields**: decide whether they represent empty strings or `null`; behavior depends on the `NULL` option and column/cqlsh version. Do not assume all blank fields mean the same thing.
- **Missing partition key/clustering columns**: a row cannot be identified without a valid primary key.
- **Timestamps without timezone**: easily interpreted inconsistently across environments. Prefer timestamps with explicit offsets or `Z` when appropriate.
- **Decimal numbers**: `25.1` differs from `25,1` when comma is the delimiter.
- **UUIDs**: malformed or missing `reading_id` values prevent rows from being written.
- **Text/UTF-8**: non-ASCII text (such as Vietnamese characters), line breaks, BOM markers, or non-UTF-8 encodings can cause unexpected parser behavior.
- **Collections/UDTs/blobs**: verify the exact representation format for your CQL/cqlsh version; do not treat complex values as plain strings.

Before a large import, test a small file covering **nulls, quotes, Unicode, timestamps, negative numbers, and duplicate keys** to observe how cqlsh actually parses them.

### 6.3. Checking Mappings and Import Errors

| Symptom | First Suspect | Resolution |
| --- | --- | --- |
| `File not found` / `No such file` | Path exists on host while cqlsh runs in a container, or different working directory | Check the file inside the cqlsh environment; use a valid absolute path. |
| Permission denied reading/writing file | OS permissions or read-only mount | Check permissions of the user running cqlsh, mount options, and disk space. |
| `InvalidRequest`, invalid data type errors | CSV columns/types mismatch the table | Run `DESCRIBE TABLE`, fix parsing/formatting per column. |
| Header imported as a data row | Missing or incorrect `HEADER = TRUE` | Check the first line and specify the header option accurately. |
| Values land in the wrong columns | Wrong column list order, wrong delimiter/quote | Cross-check headers, column order, and test with a few sample lines. |
| Many rows fail while some rows enter the DB | Import is not atomic at file level | Inspect error messages/logs, determine which rows were written, and apply re-run policy. |
| `Unauthorized` | Account lacks `MODIFY`/`SELECT` permissions | Check roles/GRANTs; do not disable security. |
| `Unavailable` or timeouts | Insufficient replicas/CL, slow nodes, load, or network | Check replication factor, CL, topology, and metrics; throttle import rate deliberately. |

Do not judge success solely by exit code or a generic "processed" count. Cross-check **source record count, failed record count, exact samples by primary key, and data validity**.

## 7. Scale Limits: Why `COPY` Is Not a General-Purpose Bulk Loader

`COPY` is convenient to start with, but shows limitations as row counts grow.

### 7.1. The Machine Running cqlsh Becomes a Bottleneck

During import, CSV data is read and parsed on the cqlsh client side, then sent over the network. During export, read results flow through cqlsh before being written to disk. Consequently, client-side CPU, RAM, disk throughput, network, the Python/cqlsh process, and timeouts can become **bottlenecks**.

Issues that may arise:

- Loading or exporting many millions of rows can take a very long time and is hard to checkpoint/resume cleanly from a failed line.
- Setting parallelism too high can trigger **backpressure, timeouts, dropped messages, or compaction backlogs** in Cassandra.
- Large row/partition sizes make reads/writes heavy even when "rows per file" appears modest.
- A multi-node cluster does not automatically turn a single cqlsh process into a large-scale distributed data processor.
- `COPY TO` on a large table can consume substantial I/O and bandwidth because it traverses many partitions.

**There is no universal threshold such as "`COPY` is always fast under N GB" across environments.** Performance depends on hardware, Cassandra/cqlsh version, networking, partition distribution, row size, RF, CL, and background tasks. Evaluate via **representative load testing**, not row counts alone.

### 7.2. Tuning with Bounded Concurrency

Some cqlsh versions expose options for concurrency, batching, timeouts, and page size in `COPY`. Exact option names and semantics vary by version; verify them in the current `cqlsh/COPY` documentation before setting parameters.

Principles:

1. Start with a **small dataset** with well-distributed keys, measuring throughput, latency, and errors.
2. Increase concurrency **step by step**, monitoring CPU, GC, disk I/O, compaction, memtable/flush, queues, and networking on every node.
3. Avoid sending multi-partition batches expecting "one batch = one SQL transaction" or thinking batches are always faster than individual writes.
4. Once timeouts or backlogs appear, **reduce ingestion rate** rather than scaling workers indefinitely.
5. Never lower production consistency merely to speed up a load test; align on data guarantees and fault tolerance.

If an operation may need to be re-run, maintain **external manifests, checksums, valid row counts, key lists, and checkpoints**. `COPY` does not provide an end-to-end checkpointed orchestration engine.

### 7.3. Consistency and Timing Limitations

- **No whole-file snapshot transaction:** a table can keep receiving writes/deletes while `COPY TO` runs. Exports do not guarantee every row reflects the same point in time.
- **Non-atomic imports:** a dropped connection mid-file leaves part of the rows already written.
- **Does not preserve TTL/writetime like a physical copy:** re-importing CSV can create different timestamps/TTLs than the original data.
- **Does not fix flawed schemas:** a poorly modeled table can still hit hotspots even when CSV parsing is flawless.
- **No business correctness guarantee on retries:** primary keys and idempotency must be designed, especially for aggregates/counters.

That is why tools should be chosen to match the **data source, migration goal, consistency requirements, validation, and recovery needs**.

## 8. Alternative Data Loading Tools: Choosing by Source and Purpose

| Tool / Approach | Best Suited When | Typical Input | Key Considerations |
| --- | --- | --- | --- |
| **cqlsh `COPY FROM/TO`** | Labs, checks, and small/medium CSVs | CSV | Easy to use, but limited scale and checkpoint control. |
| **DataStax Bulk Loader (DSBulk)** | Larger bulk loads/unloads needing better mapping/tuning and error handling | CSV, JSON, and supported sources/sinks | Verify **version, license, and compatibility** with your Apache Cassandra/cluster; do not assume every release supports every schema/type. |
| **Spark Cassandra Connector** | Existing Spark pipelines needing distributed reads/writes | DataFrame/Dataset, Spark ETL sources | Must manage partitioning, write throughput, Spark/Scala/Cassandra version alignment, and cluster resources. |
| **SSTableLoader / SSTable streaming** | Moving data already in **Cassandra SSTable** format | SSTables generated in compatible format/version | **Does not accept raw CSV directly**; requires matching schema, topology, version compatibility, and a streaming runbook. |
| **Java Driver + prepared statements** | Application integration requiring validation, transformation, and custom idempotency | Parsed records from files/DBs/APIs | Must manage concurrency limits, retries, paging, backpressure, and batch semantics. |
| **Kafka Connect/NiFi or streaming pipelines** | **Continuous** ingestion with checkpoints/monitoring | Event topics, CDC streams, source systems | At-least-once/exactly-once semantics depend on the connector and key design, not implicitly guaranteed by Cassandra. |

### 8.1. DSBulk: Common Upgrade Path from `COPY`

DSBulk is a bulk loading/unloading tool offering source/sink handling and column mapping, commonly used for workloads larger than cqlsh `COPY`. When selecting DSBulk, read the documentation for your **exact DSBulk version** and verify server/driver compatibility.

**Structural** example (not a copy-paste runnable command without setting up the tool, files, and cluster configuration):

~~~bash
# Verify DSBulk is installed along with its actual version/syntax.
dsbulk --version
dsbulk help
~~~

A real DSBulk job also requires **contact points/native port**, local datacenter, credentials/TLS, keyspace/table, data paths, column mappings, error-handling mode, timeouts, and appropriate concurrency. Never leave real passwords in command history. Before loading an entire dataset, run a dry-run or test load on a small slice using your tool version's features.

**Note:** DSBulk typically uses `dsbulk load`/`dsbulk unload`, though mapping, connector, auth options, and flag names can change across versions. Consult official documentation rather than copying commands out of context from another cluster.

### 8.2. Spark Cassandra Connector: Controlled Distributed Loading

If data already lives in Spark, the connector turns DataFrames into Cassandra writes. The advantage is distributed reading/transformation; the risk is that **multiple executors may hammer a few hot partitions simultaneously** if data modeling is unsuitable.

Requirements:

- Align Spark, Scala, Java, connector, and Cassandra versions.
- Design partition keys to avoid funneling most records into one key.
- Control task counts, connections, throughput, retries, and per-partition errors.
- Measure latency and compaction backlogs before and after increasing parallelism.

Never assume "Spark is distributed so loading into Cassandra is infinitely fast"; Cassandra remains bound by replicas, networking, disk, and compaction.

### 8.3. SSTableLoader: Fundamentally Different from CSV Import

**SSTable** is Cassandra's on-disk storage format. Tools such as `sstableloader` stream SSTable files into a cluster based on topology; this is a completely different approach from parsing CSV over native CQL.

If your source data is CSV, you cannot rename `.csv` to `.db` or run `sstableloader` directly on CSV. Using SSTable streaming requires a process to **generate valid SSTables** for the target schema/version and verify compatibility. Snapshot/SSTable restoration is a distinct operational procedure involving schema, token ranges, and post-migration repair.

### 8.4. Java Driver: When Record-by-Record Validation and Transformation Are Needed

The Java Driver fits when incoming records require business validation, timestamp normalization, type mapping, partition-key derivation, or custom idempotency policies.

Example of **a single parameterized write**, not a full multi-million-row CSV importer:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class CassandraPreparedInsertDemo {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1") // Replace with actual DC.
                .build()) {

            PreparedStatement prepared = session.prepare(
                "INSERT INTO cqlsh_copy_lab.readings_by_device_day " +
                "(device_id, reading_day, read_at, reading_id, metric, value) " +
                "VALUES (?, ?, ?, ?, ?, ?)");

            BoundStatement statement = prepared.bind(
                    "sensor-03",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T01:00:00Z"),
                    UUID.fromString("55555555-5555-4555-8555-555555555555"),
                    "temperature",
                    22.5)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE);

            session.execute(statement);
        }
    }
}
~~~

In real applications:

- Parse CSV using a **quote/escape-aware parser**, validate against the schema, and convert to Java types before `bind`.
- Reuse `CqlSession` and `PreparedStatement`; never open a new session per row.
- Use **async/bounded concurrency** or backpressure with a capped number of in-flight requests; increase concurrency only when metrics confirm cluster headroom.
- Log errors by primary key/checkpoint and design retries for **idempotent** operations. A write timeout may already have persisted data partially; do not retry blindly.
- Configure credentials, TLS, local datacenter, CL, and timeouts to match the real topology. `datacenter1` in the example is illustrative only.

### 8.5. Quick Selection by Purpose

~~~mermaid
flowchart TD
    A["Need to import or export Cassandra data"] --> B{"Is source in SSTable format?"}
    B -->|"Yes"| C["Evaluate SSTableLoader / restore per version and topology"]
    B -->|"No"| D{"Continuous or one-time data?"}
    D -->|"Continuous"| E["Kafka Connect / NiFi / checkpointed pipeline"]
    D -->|"One-time"| F{"Is source already in Spark?"}
    F -->|"Yes"| G["Spark Cassandra Connector"]
    F -->|"No"| H{"Small/medium CSV, manual operation?"}
    H -->|"Yes"| I["cqlsh COPY + data verification"]
    H -->|"No"| J["DSBulk or rate-limited Java Driver pipeline"]
~~~

This is an **initial classification guide**, not a mandatory choice. Account for schema, data volume, cluster size, compatibility, recovery needs, and operational capacity.

## 9. Controlled Data Loading Runbook

### 9.1. Before Loading

1. **Confirm the target**: cluster, datacenter, keyspace/table, Cassandra version, and where the loader process runs.
2. **Verify the schema**: partition key, clustering columns, data types, indexes, and business queries.
3. **Check capacity**: RF, CL, Up/Down nodes, disk capacity, CPU/GC, compaction backlog, and network bandwidth.
4. **Sanitize input data**: normalize timezones, UUIDs, nulls/empties, Unicode, duplicate business keys, file encoding, and quoting.
5. **Protect access**: credentials/TLS, `MODIFY` permission on target tables, and secure handling of CSVs with sensitive data.
6. **Define reconciliation criteria**: input row count, expected key count, per-partition samples, checksums/manifests, error logs, and reload plan.
7. **Run a small dry run**: test several distinct partitions and edge-case values before running a massive file.

### 9.2. During Loading

Monitor both client and cluster sides:

| Client / Tool Side | Cassandra Side |
| --- | --- |
| Records/sec rate, succeeded/failed record counts | Read/write latency, queues, dropped messages |
| CPU/RAM and file-reading throughput of cqlsh/loader | CPU, GC, memtable/flush, disk I/O |
| Connect timeouts, retries, and error files | Replica availability, compaction backlog |
| Connection pool, in-flight requests | Network throughput, disk space, active streaming/repair |

If timeouts climb alongside CPU/disk/compaction backlogs, **throttle the load and investigate** rather than raising timeouts and concurrency infinitely. If failures are `Unauthorized` or type mismatches, stop and fix the root cause; retrying the same row will not self-heal.

### 9.3. After Loading

1. Reconcile parsed row counts, failed write counts, and actual expected rows across sample partitions.
2. Execute **business queries with full partition keys** and verify data types and timestamp formatting.
3. Where consistency matters, verify results at the appropriate CL and replica health; do not equate "tool exited cleanly" with data verified across all replicas.
4. Archive reports/manifests, input sources, tool versions, config parameters, load duration, and errors for traceability.
5. For topology/RF changes or SSTable-level backup/restore, follow separate operational/repair procedures when required by version documentation; **do not run repair merely because `COPY` finished**.

## 10. Scenario Example: From Lab CSV to a Pipeline of Tens of Millions of Records

**Context:** a system records temperature/humidity from several thousand devices every minute; historical data must be loaded into Cassandra before a Java service starts reading.

### 10.1. Why Not Use One Partition Forever per Device?

If a table uses `PRIMARY KEY (device_id, read_at)` and one device accumulates millions of events, the partition can grow huge. A design like `PRIMARY KEY ((device_id, reading_day), read_at, reading_id)` splits data by day. At extremely high ingestion rates, shorter buckets may be needed; at low rates, longer buckets may make sense.

The partition key directly governs **token distribution and replica load**. Even a fast CSV loader can bottleneck a cluster if most records land in a few hot partitions.

### 10.2. Choosing Tools by Stage

| Stage | Data Volume | Suggested Approach |
| --- | --- | --- |
| Schema validation | 4–100 records | `cqlsh COPY FROM` and `SELECT` by partition. |
| Representative pilot | Small slice covering all record types | DSBulk or Java pipeline with validation/metrics. |
| Large historical backfill | Millions to tens of millions of records | DSBulk/Spark or partitioned/bounded-concurrency Java pipeline matched to real capacity. |
| Ongoing incremental data | Continuous stream from services/event bus | Java Driver or streaming connector with checkpoints and idempotency. |
| Physical transfer in native Cassandra format | Compatible SSTables/snapshots | SSTable loader/restore runbook, not CSV `COPY FROM`. |

These volume ranges illustrate **workload classification**, not benchmarks or hard tool thresholds. Decisions must rely on load tests and observed cluster metrics.

### 10.3. Practices to Prevent Business Data Errors

- **Do not generate random sequence IDs on each retry** if the same record may be reloaded; derive stable primary keys from source data.
- **Do not build large multi-partition Cassandra `BATCH` statements just for speed**: Cassandra batches have different semantics from multi-row SQL transactions and can add overhead.
- **Do not treat a `COPY TO` export taken under live writes as a global snapshot**; consistent backup/restore requires dedicated procedures.
- **Do not mix staging/production data**: use fully qualified table names and verify endpoints before running `COPY`.
- **Do not lower consistency or disable TLS/auth when imports feel slow** without assessing security and consistency requirements.

## 11. Practice Exercises and Self-Evaluation

1. Create `cqlsh_copy_lab.readings_by_device_day` per Section 3, and save the sample CSV into `readings.csv` inside the environment running cqlsh.
2. Run `COPY ... FROM` with `HEADER = TRUE`. Verify each known partition using `SELECT` with the full partition key.
3. Run `COPY ... TO` to `readings-export.csv`. Compare actual parsed values rather than row order or timestamp string formatting.
4. Intentionally swap `metric` and `value` in the column list of a `COPY FROM` command on another lab file. Predict the error or corrupted data and describe a check to catch it.
5. Create a CSV row with a comma inside a properly quoted text field. Explain why a CSV parser must understand quotes instead of using `split(",")`.
6. Suppose `COPY FROM` fails after successfully writing 60% of a file. Propose a reconciliation and re-run strategy based on **fixed primary keys** without needing whole-file rollback.
7. Explain why `COPY TO` does not fully back up schema, replication, TTLs, tombstones, and point-in-time cluster state.
8. With 30 million CSV records and a multi-node cluster, compare `COPY`, DSBulk, Spark Connector, and Java Driver on load, error control, and operations.
9. Given a set of existing SSTables, explain why `sstableloader` fits better than CSV `COPY FROM` and list compatibility checks required.
10. A Java process needs to load hundreds of thousands of records with custom validation logic. Describe how to use prepared statements, bounded concurrency, metrics, and idempotency policies.
11. After an import, full-table `SELECT COUNT(*)` takes too long. Propose a data quality verification method using sample partitions, manifests, and controlled record counts.

**Completion criteria:** import/export CSVs with `COPY`, explain clearly where files are read/written, verify data type mappings and partition keys, state non-atomic/non-snapshot limitations, and choose the right alternative for large-scale or continuous loading.

## References

- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `COPY FROM`, `COPY TO`, CSV options, and cqlsh runtime requirements.
- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): data types, primary keys, `INSERT`/`SELECT`, and query-driven table modeling.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html): data partitioning, queries, and partition key design.
- [DataStax Bulk Loader (DSBulk)](https://docs.datastax.com/en/dsbulk/): bulk import/export, mapping, and tool-version configuration.
- [Spark Cassandra Connector](https://github.com/datastax/spark-cassandra-connector): deployment documentation and connector compatibility.
- [Apache Cassandra — SSTable tools](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/sstable/index.html): SSTable tools and streaming/migration utilities.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): prepared statements, consistency, async API, and retries.
