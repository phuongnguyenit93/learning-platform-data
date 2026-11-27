# `system_schema`, `system_views`, and Metadata for Hands-On Practice

## 1. Why Inspect Metadata Before Running CQL?

Apache Cassandra is a **distributed wide-column database**: data is partitioned by the **partition key**, sorted within a partition by **clustering columns**, replicated per the keyspace's replication strategy, and read/written according to the consistency level (CL). Before optimizing queries, investigating timeouts, scaling a cluster, or connecting the Java Driver, practitioners need to know **which schemas exist** and **which node is providing operational data**.

In the **Tools and Connections** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, this lesson uses three information sources:

1. **`system_schema`**: metadata defining keyspaces, tables, columns, indexes, data types, and related CQL objects.
2. **`system_views`**: a collection of **virtual tables** for viewing runtime state and metrics **of the node receiving the query**.
3. **`system.local`, `system.peers_v2`, and Java Driver metadata**: node/topology information and how applications discover schemas to route requests.

These groups complement each other but cannot be substituted arbitrarily. Reading a schema does not prove all replicas are healthy; reading one virtual table does not provide cluster-wide totals.

**After this lesson, you will be able to:**

- Look up keyspace replication, tables, primary keys, and clustering order from CQL metadata.
- Distinguish **`system_schema.views`** (definitions of *materialized views*, if any) from **`system_views`** (the keyspace of *virtual tables*).
- Inspect native/TLS connections, node settings, thread pools, disk usage, and SSTable tasks using appropriate virtual tables.
- Understand why virtual tables are **node-local**, read-only, and not used to modify Cassandra configuration.
- Cross-check CQL metadata with `DESCRIBE`, `nodetool`, metrics, and Java Driver 4.x.
- Diagnose schema drift, wrong keyspace/partition key, driver discovery, and read/write errors without manually editing system tables.

## 2. Map of System Keyspaces

| Keyspace / Table | Information Provided | Properties to Remember |
| --- | --- | --- |
| `system_schema.keyspaces` | Keyspace names, replication strategy/replicas per DC, durable writes | Schema metadata; read to verify current definitions. |
| `system_schema.tables` | Table names and options such as compaction, compression, default TTL | Does not provide row counts or full actual storage state. |
| `system_schema.columns` | Column names, data types, kind, position, clustering order | Ideal for analyzing partition/clustering keys. |
| `system_schema.indexes` | Secondary index metadata (if any) | Does not imply all index types have identical query costs. |
| `system_schema.types` | User-defined type definitions | Contains rows only if the schema creates types. |
| `system_schema.views` | **Materialized view** definitions on tables | **Not** the `system_views` virtual keyspace. |
| `system_views.*` | Internal metrics/state exposed via virtual tables | **Node-local, non-replicated, and typically read-only**. |
| `system_virtual_schema.*` | Metadata about virtual keyspaces/tables/columns | Used to understand virtual schemas; primarily internal, not application tables. |
| `system.local` | Metadata for the local node, e.g., datacenter, version, schema version | One row representing the node serving the query. |
| `system.peers_v2` | Peer metadata known by the node (modern Cassandra) | May differ while topology/gossip is changing; older versions use `system.peers`. |

**Safety rule:** these system tables are sources to **observe**, not places for learners to run `INSERT`/`UPDATE`/`DELETE` to "fix metadata." Manage schemas with authorized CQL DDL (`CREATE`, `ALTER`, `DROP`), and manage clusters using `nodetool` and version-appropriate operational tooling.

### 2.1. Key Distinctions

~~~mermaid
flowchart LR
    DDL["CREATE/ALTER KEYSPACE, TABLE"] --> META["system_schema<br/>schema definitions"]
    META --> APP["Driver metadata<br/>Keyspace/Table/Column"]
    RUNTIME["Running node"] --> VIRTUAL["system_views<br/>node-local virtual tables"]
    RUNTIME --> LOCAL["system.local / peers_v2<br/>node/topology metadata"]
    APP -->|"CQL request"| RUNTIME
~~~

This diagram illustrates conceptual relationships only. Drivers receive schema metadata through their own mechanisms and refresh according to events/driver policy; do not assume applications must `SELECT system_schema` on every request. During schema propagation across nodes, information may **not converge instantaneously**.

## 3. Lab Setup: Sensor Query Schema

Examples run on a single-node Cassandra instance with `cqlsh` and privileges to create schemas. **RF = 1 is strictly for the lab**, not representative of fault-tolerant production architecture.

From the terminal:

~~~bash
cqlsh 127.0.0.1 9042
~~~

In cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS metadata_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS metadata_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  value double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 0;

INSERT INTO metadata_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'temperature', 25.1);

INSERT INTO metadata_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'temperature', 25.4);
~~~

This design serves the query **"events of one device on one day, newest first."** The composite partition key is `(device_id, event_day)`; `event_time` and `event_id` are clustering columns. The table has no secondary indexes or materialized views yet, so their corresponding metadata tables may return zero rows.

Verify the data with a schema-aligned CQL query:

~~~sql
SELECT event_time, event_type, value
FROM metadata_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

Assuming no prior lab data existed, expect two rows, with `01:05` before `01:00`. Fixed UUIDs allow re-running the lab with the same primary keys; `INSERT` with matching keys is an upsert and does not create extra rows. If the table already exists with a different schema, `IF NOT EXISTS` **does not alter the existing schema**; inspect the definition before proceeding.

## 4. `system_schema`: Reading Keyspace and Table Definitions

### 4.1. Locating the Right Keyspace and Replication

~~~sql
DESCRIBE KEYSPACES;
DESCRIBE KEYSPACE metadata_lab;

SELECT keyspace_name, durable_writes, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'metadata_lab';
~~~

`replication` is a map containing the strategy name and replica configuration. In the lab, you will see `SimpleStrategy`/`replication_factor = 1`. In multi-datacenter production systems, `NetworkTopologyStrategy` and **per-datacenter** replication factors are typically used; check the **actual DC names** before interpreting `LOCAL_QUORUM`.

**Do not confuse:**

- **RF** in `replication`: how many replicas each partition has per topology.
- **CL** on a request: how many replicas must respond for a read/write to succeed.
- **Seed nodes**: gossip discovery points for new nodes; they do not control replica counts and do not appear as a "seed" column in the replication table.

Hypothetical example of a single DC with RF = 3: `LOCAL_QUORUM` requires 2 replicas in that DC to respond. With RF = 1 in the lab, `LOCAL_QUORUM` in that single DC still needs only 1 replica; metadata alone does not prove a cluster has two or three nodes.

### 4.2. Listing Tables and Storage Options

~~~sql
DESCRIBE TABLES;
DESCRIBE TABLE metadata_lab.events_by_device_day;

SELECT keyspace_name, table_name, compaction, compression,
       default_time_to_live
FROM system_schema.tables
WHERE keyspace_name = 'metadata_lab';
~~~

Here, `DESCRIBE TABLE` in **cqlsh** is usually the easiest way to view a readable `CREATE TABLE` statement. `system_schema.tables` is helpful when filtering or listing metadata across multiple tables.

Meaning of several columns:

| Schema Property | Description | What Cannot Be Inferred |
| --- | --- | --- |
| `compaction` | Compaction strategy and parameters configured for the table | Does not show currently running compactions or current backlog. |
| `compression` | SSTable compression algorithm and options | Not an actual disk usage metric. |
| `default_time_to_live` | Default TTL for writes to the table if non-zero | Does not show remaining TTL of individual cells. |
| `gc_grace_seconds` | Parameter related to tombstones/garbage collection | Does not prove repairs ran on schedule. |
| `caching` | Table cache configuration | Not the current cache hit ratio. |

This is **definitional metadata**, not continuously updating metrics. To inspect active compaction tasks or actual disk usage, use virtual tables/`nodetool`/metrics covered below.

### 4.3. Analyzing Partition Keys and Clustering Columns via `columns`

~~~sql
SELECT column_name, kind, position, type, clustering_order
FROM system_schema.columns
WHERE keyspace_name = 'metadata_lab'
  AND table_name = 'events_by_device_day';
~~~

Columns to observe:

| `column_name` | Expected `kind` | Role |
| --- | --- | --- |
| `device_id` | `partition_key` | First component of the composite partition key. |
| `event_day` | `partition_key` | Second component of the partition key (day bucket). |
| `event_time` | `clustering` | First clustering column, sorted descending. |
| `event_id` | `clustering` | Second clustering column, sorted ascending. |
| `event_type`, `value` | `regular` | Data fields not part of the primary key. |

`position` records the key component's index within its key group; never rely solely on **the row order of the SELECT output** to determine composite partition/clustering key order. Use `kind` + `position` and `clustering_order`, and cross-check with `DESCRIBE TABLE`.

**Classic trap:** metadata shows `event_time` is a clustering column, **not an independent partition key**. The query:

~~~sql
-- Does not match the lab table's primary key if missing the partition key.
SELECT event_time, value
FROM metadata_lab.events_by_device_day
WHERE event_time > '2026-11-21T01:00:00Z';
~~~

may be rejected due to filtering/routing restrictions even though the CQL syntax is valid. The proper fix is adding the **full partition key** or designing an additional table for the other query pattern, rather than defaulting to `ALLOW FILTERING` for wide scans.

### 4.4. Finding Indexes, Types, Functions, Aggregates, and Materialized Views

~~~sql
-- May return 0 rows in a lab without indexes/views/UDTs created yet.
SELECT keyspace_name, table_name, index_name, kind
FROM system_schema.indexes
WHERE keyspace_name = 'metadata_lab';

SELECT keyspace_name, type_name, field_names, field_types
FROM system_schema.types
WHERE keyspace_name = 'metadata_lab';

-- Metadata for materialized views (not virtual tables).
SELECT keyspace_name, view_name, base_table_name
FROM system_schema.views
WHERE keyspace_name = 'metadata_lab';
~~~

`system_schema.functions` and `system_schema.aggregates` store metadata for user-defined functions/aggregates if supported by the version/configuration and created. Do not infer "unsupported" merely because a metadata table is empty in a fresh keyspace.

**Critically important:**

| Name | Meaning |
| --- | --- |
| **`system_schema.views`** | Metadata table storing definitions of **materialized views** created over data tables. |
| **`system_views`** | **Virtual tables keyspace** for reading metrics/configuration/state of the **local node**. |

The shared word "views" is a naming coincidence, **not the same kind of object**.

## 5. `system_views`: Node-Local Virtual Tables

Virtual tables were introduced in Apache Cassandra **4.0**. Rather than storing contents in SSTables like regular tables, virtual tables provide a **CQL interface for reading node-generated data at query time**: client info, configuration, thread pools, SSTable tasks, and certain latency/disk metrics.

Per Cassandra's virtual tables documentation:

- Virtual tables in `system_views` are **node-local**, not distributed or replicated like application tables.
- They have **no backing SSTables** and are not targets for application data backups.
- For current virtual tables, **do not use DML to modify metrics/configuration**; `INSERT`, `UPDATE`, `DELETE`/`TRUNCATE`, or DDL on virtual tables are not administrative APIs.
- **Consistency level on `SELECT` against virtual tables is ignored**, because there is no multi-replica read requirement as with replicated tables.
- The list of tables/columns **varies by Cassandra version**; an example in 5.x documentation may not apply verbatim to a 4.0/4.1 cluster.

To discover what your running cluster supports:

~~~sql
DESCRIBE KEYSPACE system_views;
DESCRIBE TABLES;
DESCRIBE TABLE system_views.clients;
DESCRIBE TABLE system_views.settings;
~~~

`DESCRIBE TABLES` does not filter solely to `system_views` unless you switch context with `USE system_views`. To avoid confusion:

~~~sql
USE system_views;
DESCRIBE TABLES;

-- Switch back to the lab keyspace to continue querying data.
USE metadata_lab;
~~~

`DESCRIBE` may print a `"VIRTUAL TABLE ..."` definition for reference only; **do not copy that DDL expecting to create your own virtual tables**.

### 5.1. What Is `system_virtual_schema`?

In Cassandra releases with virtual tables, the **`system_virtual_schema`** keyspace describes virtual keyspaces, virtual tables, and columns (such as `keyspaces`, `tables`, and `columns`). This metadata supports the virtual schema mechanism itself and is **not a place for users to add system columns**.

~~~sql
-- Inspect existence and definitions; do not modify virtual schemas.
DESCRIBE KEYSPACE system_virtual_schema;
DESCRIBE TABLE system_virtual_schema.tables;
~~~

This is an internal metadata source; to view the active list of virtual tables, prefer `DESCRIBE KEYSPACE system_views` or `DESCRIBE TABLES` in the right context. Do not write applications that hard-depend on every virtual table name/column as a stable cross-major-version API.

### 5.2. `system_views.clients`: Who Is Connected to the Node?

~~~sql
DESCRIBE TABLE system_views.clients;

SELECT address, port, driver_name, driver_version,
       protocol_version, ssl_enabled
FROM system_views.clients
LIMIT 20;
~~~

This table typically displays **active native connections on the node handling the SELECT**. Some versions also include `username`, `request_count`, `ssl_protocol`, `connection_stage`, and other client metadata. Available columns depend on version: if `DESCRIBE TABLE` lacks a column, adjust the `SELECT` before running it.

Questions this can answer:

1. Which driver and native protocol version are clients connecting with?
2. Do the observed connections have TLS enabled?
3. Are any connections stuck before ready (`connection_stage`) or showing unusual request counts?
4. During a driver/TLS upgrade, are any legacy clients or plaintext connections still hitting this node?

**Do not interpret `0 rows` as "no applications are connected anywhere in the cluster."** You may be querying a node not receiving those connections, or permissions/versions/timing may yield different results. On multi-node clusters, inspect each relevant node and aggregate separately.

Fields like IP addresses, usernames, drivers, and encryption settings can be operationally sensitive; grant read access only to required accounts and limit sharing logs/screenshots.

### 5.3. `system_views.settings`: Are Runtime Settings as Expected?

~~~sql
DESCRIBE TABLE system_views.settings;

-- Query a parameter when the version's schema provides name/value.
SELECT name, value
FROM system_views.settings
WHERE name = 'native_transport_port';

SELECT name, value
FROM system_views.settings
WHERE name = 'storage_port';
~~~

Values reflect the **configuration of the node serving the query**, helping verify `cassandra.yaml`, native/internode ports, and certain timeout or cache settings. Not every secret is exposed verbatim through this table: Cassandra versions include mechanisms to redact sensitive settings.

If `cassandra.yaml` was recently edited without a proper rollout/restart, runtime values can differ from disk files. **You cannot run `UPDATE system_views.settings SET ...` to change configuration**; use your version's supported config management, JMX, or `nodetool` mechanisms.

### 5.4. Thread Pools: Are Requests Queuing Up?

~~~sql
DESCRIBE TABLE system_views.thread_pools;

SELECT name, active_tasks, pending_tasks, blocked_tasks
FROM system_views.thread_pools
LIMIT 30;
~~~

High and climbing `pending_tasks` or `blocked_tasks` on request-processing executors is a **signal to investigate load**, not automatic proof that "the root cause is found." Combine with CPU, GC, disk I/O, network, request latency, dropped messages, and query patterns.

Do not sum `pending_tasks` across sequential per-node queries and treat the sum as a synchronized point-in-time cluster metric; sequential queries capture different instants.

### 5.5. SSTable Tasks: Observing Related Compaction and Streaming

~~~sql
DESCRIBE TABLE system_views.sstable_tasks;

SELECT keyspace_name, table_name, kind, progress, total, unit
FROM system_views.sstable_tasks
LIMIT 20;
~~~

When tasks are active, fields typically show the task kind (such as compaction), progress, and unit. An empty table may simply mean **no tracked tasks were running at the moment of the SELECT**; never conclude "the cluster never compacts."

Cross-check with:

~~~bash
nodetool compactionstats
nodetool netstats
~~~

`nodetool compactionstats` monitors compaction; `nodetool netstats` inspects streaming during bootstrap/repair. They are not exact 1-to-1 equivalents of `system_views.sstable_tasks`. When seeing high latency, do not run `compact` or `repair` simply because a task appears; assess backlogs, load, maintenance windows, and the purpose of each operation.

### 5.6. Disk / Latency / Internode: Reading the Right Metric Type

Virtual tables available in various Cassandra releases:

| Virtual Table | Common Question |
| --- | --- |
| `system_views.disk_usage` | Which tables/keyspaces consume storage on the queried node? |
| `system_views.local_read_latency` | What is the **local** read latency of tables on this node? |
| `system_views.coordinator_read_latency` | What **coordinator-level** read latency does this node observe? |
| `system_views.local_write_latency`, `coordinator_write_latency` | Write latency status at local/coordinator layers. |
| `system_views.internode_inbound` / `internode_outbound` | Do node-to-node messages show notable queues, errors, bytes, or throughput? |
| `system_views.rows_per_read` / `tombstones_per_read` | Do queries tend to scan many rows or tombstones? |
| `system_views.max_partition_size` | Hints which tables have large partitions on the node, pointing to hot/large partition checks. |

Inspect the schema before selecting columns:

~~~sql
DESCRIBE TABLE system_views.disk_usage;
SELECT * FROM system_views.disk_usage LIMIT 20;

DESCRIBE TABLE system_views.local_read_latency;
SELECT * FROM system_views.local_read_latency LIMIT 20;

DESCRIBE TABLE system_views.internode_outbound;
SELECT * FROM system_views.internode_outbound LIMIT 20;
~~~

Table/column names can differ between 4.x and 5.x. Avoid hard-coding non-existent metric columns and blaming Cassandra for `InvalidRequest`. Run `DESCRIBE TABLE` first, select needed metrics, and avoid unbounded `SELECT *` on wide tables in high-traffic systems.

**Avoid misreading metrics:**

- `local_read_latency` measures local operations, not client end-to-end latency.
- `coordinator_read_latency` covers requests coordinated by this node and does not imply every replica is equally slow.
- Disk usage is **per node and point-in-time**, not total logical size multiplied cleanly by RF.
- Metrics can reset across process lifecycles and fluctuate continuously; evaluate trends/time series before drawing conclusions.

## 6. `system.local` and `system.peers_v2`: Supplemental Topology

In many driver debugging situations, `system_schema` reveals RF but not which datacenter a node belongs to. Query:

~~~sql
SELECT cluster_name, data_center, rack, release_version, schema_version
FROM system.local;

-- Run only on versions that provide peers_v2 (typically Cassandra 4.x and newer).
DESCRIBE TABLE system.peers_v2;
SELECT * FROM system.peers_v2 LIMIT 10;
~~~

On older Cassandra versions, use `system.peers` instead of `system.peers_v2`. System table layouts vary by version, so run `DESCRIBE TABLE` when looking up exact field names such as `peer`, `native_address`, `native_port`, `host_id`, `data_center`, or `rack`.

**Limitations:**

- `system.local` contains metadata of the **node receiving the request**.
- `system.peers_v2` reflects **that node's view of peers**, not a central registry guaranteed to synchronize instantaneously.
- `schema_version` helps compare schema agreement at the metadata level, though eyeballing a UUID does not replace version-appropriate schema agreement diagnostics.
- While nodes bootstrap, change addresses, or gossip has not converged, nodes may see different peers. Combine with `nodetool status`, `nodetool describecluster`, and logs.

### 6.1. Practicing Schema Agreement Checks

Suppose you just ran `ALTER TABLE` in the lab or rolled out a production schema change. You can check the version reported by the queried node:

~~~sql
SELECT schema_version, release_version
FROM system.local;
~~~

In a multi-node cluster, gather corresponding metadata across nodes using appropriate tooling alongside:

~~~bash
nodetool describecluster
nodetool status
~~~

**Schema agreement does not mean all replicas have synchronized data.** It refers strictly to convergence of **schema definitions**. Data repair, streaming, and replication are separate concerns. The Java Driver can wait for schema agreement after DDL, yet metadata read at one instant should not be treated as immutable forever.

## 7. Scenario-Based Metadata Query Runbook

### Scenario A: `SELECT` Rejected for Missing Partition Key

1. Inspect the query and exact table/keyspace names.
2. Run:

   ~~~sql
   DESCRIBE TABLE metadata_lab.events_by_device_day;

   SELECT column_name, kind, position, type, clustering_order
   FROM system_schema.columns
   WHERE keyspace_name = 'metadata_lab'
     AND table_name = 'events_by_device_day';
   ~~~

3. Identify that `device_id` + `event_day` is the partition key, not `event_time`.
4. Fix the query to match the partitioning or design another table for the query pattern. Do not blindly add `ALLOW FILTERING`.

### Scenario B: Timeout with `LOCAL_QUORUM`

1. Check the RF of the **actual keyspace**, not another lab's RF:

   ~~~sql
   SELECT replication FROM system_schema.keyspaces
   WHERE keyspace_name = 'metadata_lab';
   ~~~

2. Check the coordinator's local DC, replica states, and internode networking:

   ~~~sql
   SELECT data_center, rack, release_version FROM system.local;
   ~~~

   ~~~bash
   nodetool status
   nodetool gossipinfo
   ~~~

3. When needed, inspect `system_views.thread_pools`, latency tables, and `sstable_tasks` **on the affected node** for signs of overload.
4. Distinguish `Unavailable` (coordinator sees too few live replicas) from `ReadTimeout`/`WriteTimeout` (too few responses arrived on time). Lowering production CL is not a default fix.

### Scenario C: Java Driver Reports Handshake/TLS or Protocol Errors

~~~sql
DESCRIBE TABLE system_views.clients;
SELECT address, port, driver_name, driver_version,
       protocol_version, ssl_enabled
FROM system_views.clients LIMIT 20;
~~~

Inspect the **exact node** the Java Driver is trying to reach. `ssl_enabled = false` is normal in a non-TLS lab, yet a critical signal to investigate when TLS is mandatory. If a client has not finished the native handshake, it may not appear as a ready connection.

Continue checking DNS, TCP 9042, native TLS, CA/hostname, credentials, local datacenter, and peers' `broadcast_rpc_address`. Remember `system_views.clients` may contain sensitive data—never export real client data to unauthorized locations.

### Scenario D: Compaction Backlog or Rapidly Growing Data

~~~sql
DESCRIBE TABLE metadata_lab.events_by_device_day;
DESCRIBE TABLE system_views.disk_usage;
DESCRIBE TABLE system_views.sstable_tasks;

SELECT * FROM system_views.disk_usage LIMIT 20;
SELECT * FROM system_views.sstable_tasks LIMIT 20;
~~~

Check the table's compaction configuration via `system_schema.tables`, then observe real workload with `nodetool compactionstats` and metrics. Consider partition counts/sizes, tombstones, TTLs, and write volume. Never change a compaction strategy based on a single metrics snapshot.

## 8. Java Driver 4.x: Using the Metadata API Instead of Parsing `DESCRIBE`

In Java applications, you do not need to send `DESCRIBE` as a CQL statement. `DESCRIBE` is a **cqlsh** command. Java Driver 4.x provides a **metadata API** to inspect schemas discovered by the driver.

Example:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.metadata.schema.KeyspaceMetadata;
import com.datastax.oss.driver.api.core.metadata.schema.TableMetadata;

import java.net.InetSocketAddress;
import java.util.Optional;

public class CassandraMetadataDemo {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            Optional<KeyspaceMetadata> keyspace = session.getMetadata()
                    .getKeyspace(CqlIdentifier.fromCql("metadata_lab"));
            if (keyspace.isEmpty()) {
                throw new IllegalStateException("Keyspace metadata_lab not found");
            }

            Optional<TableMetadata> table = keyspace.get()
                    .getTable(CqlIdentifier.fromCql("events_by_device_day"));
            if (table.isEmpty()) {
                throw new IllegalStateException("Table not found");
            }

            System.out.println("Partition key:");
            table.get().getPartitionKey().forEach(column ->
                    System.out.println("  " + column.getName()));

            System.out.println("All columns:");
            table.get().getColumns().forEach((name, column) ->
                    System.out.println("  " + name + " = " + column.getType()));
        }
    }
}
~~~

**Conditions and limitations:**

- `datacenter1` is only an illustrative name. Query `SELECT data_center FROM system.local;` to set `withLocalDatacenter` accurately for your deployment.
- The Java Driver does not automatically enable TLS/auth just because local cqlsh connects; configure SSL context, credentials, and native contact points when needed.
- `session.getMetadata()` returns an **immutable metadata snapshot** at the moment of the call. To see new schemas after DDL, re-fetch metadata after driver refresh/schema agreement; do not hold an old reference expecting it to mutate automatically. <https://apache.github.io/cassandra-java-driver/4.18.1/core/metadata/schema/>.
- Metadata discovery may be disabled or filtered to specific keyspaces via driver config; if an expected schema is missing, check policies/config and permissions rather than editing `system_schema`.
- `system_views` is node-local. A `SELECT * FROM system_views.clients` sent through the driver pool goes to **a coordinator chosen by the driver** and is not guaranteed to return every node's data. To inspect individual nodes, use controlled per-node connections/routing and verify endpoints.
- Metadata does not replace **prepared statements** and queries using proper partition keys. Reading schemas only informs the application of structure; consistency and replicas are still handled per request.

### 8.1. Cross-Checking Schemas with Applications

Suppose the Java Driver reports `InvalidQueryException` for a non-existent column. How to investigate:

1. Confirm the exact keyspace/table the application sends (prefer fully qualified `keyspace.table`).
2. Inspect `DESCRIBE TABLE` in cqlsh and check `system_schema.columns`.
3. Inspect metadata via `session.getMetadata()` and verify it refreshed after DDL migrations.
4. Check cluster schema agreement and migration/schema logs if available.
5. Fix the query, prepared statement, or migration pipeline; never `INSERT` into system tables to "create a column."

## 9. Access Control and What Not to Do

System keyspaces can expose **topology, usernames, IPs, driver versions, configuration, performance, and business data schemas**. Grant read access only to metadata a role genuinely requires; never grant broad permissions across all of `system`/`system_views` to every application solely for debugging convenience.

**Do not:**

- Run `UPDATE system_schema.columns ...` or `DELETE FROM system_schema.tables ...` to alter tables; use valid DDL.
- Run `UPDATE system_views.settings ...` to modify settings; virtual tables are not a DML configuration API.
- Run `DROP` or `TRUNCATE` on virtual tables to "clear metrics."
- Assume `system_views.clients` queried from one coordinator represents connections across the entire cluster.
- Assume `system_schema.tables` reports row counts, logical data size, or throughput.
- Conflate `system_schema.views` with `system_views`.
- Assume every system table exists on every Cassandra version; verify via `SHOW VERSION`/`DESCRIBE`.
- Run unbounded `SELECT *` on tables in production without understanding size and cost. System metadata is typically smaller than application data, yet should still be queried purposefully.

### 9.1. Common Errors

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| `unconfigured table system_views...` | Server too old or virtual table does not exist in that version | Run `SHOW VERSION`, `DESCRIBE KEYSPACE system_views`, check version-matched docs. |
| `Unauthorized` when reading metadata | Role lacks permission to read system tables | Request approved least-privilege grants; do not disable the authorizer. |
| `InvalidRequest` on `UPDATE system_views.settings` | Virtual tables reject DML modifications | Use supported configuration/JMX/`nodetool` mechanisms. |
| `system_schema.views` has zero rows | Lab has not created any materialized views | Unrelated to whether `system_views` exists. |
| Java metadata lacks a newly created table | Stale snapshot, unrefreshed schema/policy, or DDL not yet converged | Fetch a new snapshot, check schema agreement and migrations. |
| `system_views.clients` shows fewer connections than expected | Reflects only the queried node | Inspect each native endpoint and compare driver contact points/topology. |
| `sstable_tasks` is empty under heavy load | No tracked task active at the instant of SELECT, or load stems from elsewhere | Check thread pools, metrics, logs, `nodetool compactionstats`/`netstats`. |
| `system.peers_v2` not found | Version/metadata differences | Check `system.peers` and version docs; never edit system tables. |
| Changing CL does not alter virtual table output | Node-local virtual tables do not apply quorum like data tables | Use CL for replicated tables; target the right node when reading metrics. |

## 10. Practice Exercises

1. Create `metadata_lab.events_by_device_day`, then use `DESCRIBE TABLE` and `system_schema.columns` to identify the **two partition key columns**, clustering order, and data types.
2. Query `system_schema.keyspaces` to inspect `metadata_lab` replication. Explain why RF = 1 does not simulate multi-replica quorum.
3. Compare `system_schema.tables.compaction` with `system_views.sstable_tasks`. Which returns configuration and which returns runtime task status?
4. Query `system_schema.views` and run `DESCRIBE KEYSPACE system_views`. Explain why the two "views" names serve completely different purposes.
5. Run `DESCRIBE TABLE system_views.clients` and inspect active connections on the node. Which fields verify the native protocol version and TLS?
6. Query `system_views.settings` for `native_transport_port` and `storage_port`. Why can't you `UPDATE` a virtual table to change ports?
7. Inspect `system_views.thread_pools` and `sstable_tasks` while the lab executes queries. If `pending_tasks = 0` or the task table is empty, does that prove the entire cluster has no performance issues?
8. Run `SELECT cluster_name, data_center, release_version, schema_version FROM system.local;`. Distinguish node-local runtime info from keyspace schema metadata.
9. Write Java code using `session.getMetadata().getKeyspace(...)` and `getTable(...)` to print column names. After DDL, why must you retrieve fresh metadata instead of reusing an old snapshot?
10. Suppose a `SELECT` filtering on `event_time` without `device_id`/`event_day` fails. Use metadata to explain the error and rewrite the query properly.
11. In a multi-node cluster, why must `system_views.clients` or `disk_usage` be checked on **each node** during an investigation rather than via an arbitrary coordinator?
12. When a system reports timeouts alongside compaction backlogs, list at least three metadata/metric sources to cross-check before altering compaction strategy or consistency.

**Completion criteria:** distinguish schema metadata from node-local virtual metrics; read and explain partition/clustering keys from `system_schema`; choose the right `system_views` tables for observation; never modify system tables directly; and use the Java Driver metadata API to verify schemas during application development.

## References

- [Apache Cassandra — Virtual Tables](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/virtualtables.html): how virtual tables work, `system_views`, `system_virtual_schema`, and node-local/read-only constraints.
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): keyspaces, tables, primary keys, options, and schema objects.
- [Apache Cassandra — System Keyspaces](https://cassandra.apache.org/doc/stable/cassandra/architecture/overview.html): cluster architecture, metadata, and nodes.
- [Apache Cassandra — nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): `status`, `describecluster`, `compactionstats`, `netstats`.
- [Apache Cassandra Java Driver — Schema Metadata 4.18.1](https://apache.github.io/cassandra-java-driver/4.18.1/core/metadata/schema/): `session.getMetadata()`, `getKeyspace`, `getTable`, snapshots, and schema agreement.
