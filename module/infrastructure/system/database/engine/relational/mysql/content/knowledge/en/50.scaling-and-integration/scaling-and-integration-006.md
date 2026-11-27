# Debezium and Other CDC Tools: Snapshots, Offsets, and Schema Changes

## Objectives

After this lesson, you will be able to:

- Explain Change Data Capture (CDC) and the role of the MySQL binary log in streaming data changes to other systems.
- Distinguish initial snapshots from continuous change event streams.
- Describe how Debezium tracks binlog positions/GTIDs and stores source offsets to resume after restarts.
- Identify risks of duplicates, lost binlogs, offset resets, and extended downtime.
- Explain schema history and the impact of DDL on decoding row events.
- Design consumers resilient to schema evolution, event ordering, and reprocessing.
- Compare Debezium with other CDC options and build operational, monitoring, and recovery procedures.

## 1. What Is CDC and What Problem Does It Solve?

Change Data Capture (CDC) records changes occurring in a database and forwards them to other systems. Instead of periodically running queries to scan entire tables for new rows, CDC reads the change stream at the source to detect `INSERT`, `UPDATE`, and `DELETE` operations.

In a MySQL architecture, the binary log (binlog) is a key data source for CDC. When MySQL writes transactions to the binlog, a connector can read these events, decode row changes, and publish them to Kafka, message brokers, data warehouses, search indexes, or other services.

Common use cases:

- Synchronizing data from MySQL to a data lake or data warehouse.
- Updating Elasticsearch/OpenSearch or search caches.
- Emitting change events to other microservices.
- Building read models or materialized views in downstream systems.
- Creating near-real-time analytics pipelines.
- Migrating data across database systems without continuous full-table scans.

CDC is not a backup and does not replace MySQL replication. It is a change event stream for data integration. Downstream systems must manage schemas, retries, duplicates, ordering, and disconnection handling on their own.

## 2. Overall Architecture with Debezium

Debezium is an open-source CDC platform. In a common deployment, Debezium runs as a Kafka Connect source connector. The connector connects to MySQL, takes an initial snapshot if configured, then reads the binlog and emits records into Kafka.

~~~mermaid
flowchart LR
    APP[Application writing data] --> MYSQL[(MySQL)]
    MYSQL --> BINLOG[Binary log]
    SNAP[Snapshot reader] --> MYSQL
    BINLOG --> DBZ[Debezium MySQL Connector]
    SNAP --> DBZ
    DBZ --> KC[Kafka Connect]
    KC --> DATA[Kafka data topics]
    KC --> HIST[Schema history topic]
    KC --> OFF[Connect offset storage]
    DATA --> CONSUMER[Consumer / Stream processor]
    CONSUMER --> DW[Warehouse / Search / Service]
~~~

Each component has a distinct role:

| Component | Role |
|---|---|
| MySQL source | Source database generating binlogs from transactions |
| Snapshot | Reads the current state of tables at a consistent point in time |
| Debezium connector | Decodes the binlog, builds change events, and manages source positions |
| Kafka Connect | Manages connector/task lifecycle, persists source offsets, and routes records |
| Data topics | Holds events by database/table or naming rules |
| Schema history | Stores DDL history needed to interpret row structures at each point in time |
| Offset storage | Stores source read progress so the connector can resume |
| Consumer | Applies or transforms change events downstream |

Data topics, the schema history topic, and offset storage are not the same kind of data. Do not use a data topic in place of schema history or manually alter internal offsets without a recovery plan.

## 3. How Does Debezium Read MySQL?

MySQL writes committed changes to the binary log. With row-based logging, the binlog contains row-level change data rather than only the original SQL statements. Debezium reads binlog events, uses schema metadata to decode data types, and creates key/value records.

Simple flow:

1. The application performs `INSERT`, `UPDATE`, or `DELETE`.
2. MySQL executes the transaction and writes changes to the binlog upon commit.
3. Debezium reads the binlog from the stored or initial position.
4. The connector decodes row events against the corresponding schema.
5. The connector creates change events and sends them to Kafka Connect.
6. Kafka Connect forwards records to Kafka topics.
7. Offsets are persisted via Kafka Connect's mechanism so subsequent runs know the processed source position.

Debezium does not re-query entire tables for every change. During streaming, it tails the binlog continuously and processes row events in source order.

### 3.1. Basic MySQL Configuration Requirements

A MySQL configuration typically requires the following conditions:

- Binary logging is enabled.
- `binlog_format` is `ROW`.
- `binlog_row_image` should be set to `FULL` so the connector has complete before/after row information for various operations and schemas; this produces larger binlogs compared to `MINIMAL`.
- `server_id` is unique within the replication topology.
- Binlogs are retained long enough for the connector to recover after interruptions.
- The CDC user has data read privileges for snapshots and the replication privileges needed to read the binlog.
- If reading from a replica, replication configuration and `log_replica_updates` must fit the architecture.

Example foundational settings in a configuration file:

~~~ini
[mysqld]
server_id=301
log_bin=mysql-bin
binlog_format=ROW
binlog_row_image=FULL
binlog_expire_logs_seconds=604800
~~~

The 604800-second retention example equals 7 days and is illustrative only. Actual retention must exceed maximum expected downtime plus time for investigation, recovery, and catch-up. For systems with long maintenance windows or connectors that could remain stopped for several days, longer retention is required.

You can check variables with:

~~~sql
SHOW VARIABLES
WHERE Variable_name IN (
  'log_bin',
  'binlog_format',
  'binlog_row_image',
  'binlog_expire_logs_seconds',
  'gtid_mode',
  'server_id'
);
~~~

GTID is not mandatory for every Debezium setup, but it makes tracking transaction history and handling source failover more convenient. When using GTID, understand how the connector identifies the source and ensure servers in the topology maintain consistent GTID history.

### 3.2. CDC Account Privileges

The connector needs different privileges depending on the operation:

- Reading schemas/tables and data during snapshots.
- Reading database info and required metadata.
- Registering/reading the binlog as a replication client.
- Possibly needing locking or flush privileges under specific snapshot modes.

Do not grant global administrative privileges just to get the connector running. Create a dedicated CDC user, restricting databases/tables, allowed client hosts, and privileges to match the exact Debezium version, MySQL version, and snapshot locking mode in use. Debezium documentation for each version lists exact privileges; check it before deploying.

Illustrative user creation example:

~~~sql
CREATE USER 'debezium'@'10.%'
IDENTIFIED BY 'REPLACE_WITH_SECRET';

GRANT SELECT, SHOW DATABASES, REPLICATION SLAVE,
      REPLICATION CLIENT
ON *.* TO 'debezium'@'10.%';
~~~

This is not a universal production privilege list for all versions. Some snapshot modes or MySQL versions require additional privileges such as `RELOAD` or `LOCK TABLES`; some newer MySQL versions rename or adjust replication privileges. Grant only what is needed after checking connector requirements and testing actual snapshots.

Never store plaintext passwords in source control or unprotected connector configurations. Use Kafka Connect `ConfigProvider`, a secret manager, or your platform's secret configuration mechanism.

## 4. Initial Snapshot

When a connector starts in initial snapshot mode, it needs the current state of the selected tables. The snapshot gives downstream baseline data before receiving subsequent changes.

General workflow:

1. The connector connects to MySQL and identifies schemas/tables within the capture scope.
2. The connector coordinates acquiring the binlog position or GTID with a consistent snapshot.
3. The connector reads table data at the snapshot view and emits snapshot records.
4. Once the snapshot completes, the connector resumes streaming from the coordinated binlog position.

The core requirement is having no gap between snapshot state and the binlog stream. If the snapshot captures data at time T while streaming starts from a position after T without proper coordination, changes occurring in between can be lost. If streaming starts too early or the snapshot is inconsistent, some changes may appear duplicated. Debezium manages this coordination according to the snapshot mode and connector version.

### 4.1. Consistent Snapshots

With InnoDB, snapshots typically rely on a consistent read inside a transaction. The locking mechanism used to determine schemas and binlog coordinates can vary by snapshot locking mode. Tables using engines without consistent transactional reads such as MyISAM do not receive the same snapshot guarantees; locking may be needed to keep data stable while reading.

Key concepts:

- **Consistent snapshot:** rows are read against the same logical data image.
- **Global read lock:** a brief global lock may be used to synchronize metadata/position and secure the starting point.
- **Table lock:** table locks can directly block writes on captured tables.
- **Snapshot locking mode:** controls how the connector acquires locks during snapshots; specific options depend on Debezium version and user privileges.

Minimal-locking modes reduce write blocking duration but require suitable conditions regarding storage engines, DDL, and privileges. Lockless modes carry risks under concurrent DDL or engines lacking transactional snapshots. Do not choose a mode based on its name alone; read version-specific documentation and test under real workloads.

### 4.2. Snapshot Events vs. Streaming Events

Debezium normally represents snapshot records with operation code `r` (read). Binlog changes typically have operation codes:

| Operation | Meaning |
|---|---|
| `r` | Row emitted from a snapshot |
| `c` | `INSERT` |
| `u` | `UPDATE` |
| `d` | `DELETE` |

Consumers must understand that an `r` record is existing baseline state read from the table, not a new `INSERT` just executed by the application. If a consumer increments order counts or sends notifications for every event without distinguishing snapshot reads from `c`, baseline data may be treated as new transactions.

Simplified event envelope example:

~~~json
{
  "before": null,
  "after": {
    "order_id": 9001,
    "status": "PAID",
    "total_amount": 125.50
  },
  "source": {
    "db": "sales",
    "table": "orders",
    "snapshot": "true"
  },
  "op": "r"
}
~~~

Actual envelopes include timestamps, transaction metadata, connector version, and schema structures depending on the converter. Do not hardcode consumers to a simplified payload without verifying your converter and Debezium version.

### 4.3. Choosing a Snapshot Mode

Debezium MySQL offers multiple snapshot modes depending on version. Common modes generally mean:

- Initial snapshot then stream: suitable when seeding all existing state.
- One-time snapshot then stop: used to export current state without continuing CDC.
- Schema-only, no data: used in certain deliberate initialization/recovery scenarios.
- No snapshot: stream only from the configured position or existing offset.
- Snapshot when needed: can trigger a re-snapshot when old offsets are no longer usable.
- Incremental snapshot: captures chunks while the connector continues streaming.

Property names and mode lists change across Debezium generations. Never copy a `snapshot.mode` value from an outdated guide without checking documentation for your running version. Snapshot mode governs baseline data and starting position; changing it can trigger massive replays or alter connector recovery behavior.

## 5. Incremental Snapshots

An initial snapshot can take many hours for large tables. Meanwhile, the connector must retain binlogs so no intermediate changes are missed. Incremental snapshots allow reading a table in chunks while the binlog stream continues running.

General workflow:

1. The connector receives a signal to start an incremental snapshot for a table.
2. The table is split into chunks using a key or supported segmentation mechanism.
3. The connector reads each chunk and emits snapshot records.
4. Binlog changes occurring during the snapshot continue to be processed.
5. The connector coordinates watermarks/chunk state to handle cases where the same row appears in both the snapshot and a new change.
6. Once all chunks finish, the snapshot is marked complete and normal streaming continues.

Incremental snapshots are helpful when adding tables or re-capturing a dataset without stopping the connector for long periods. They still generate read load on MySQL and can replay multiple records, so downstream must be idempotent.

Incremental snapshot signals can be sent via a signaling table in MySQL or a connector-supported signal channel. Exact mechanisms and configuration depend on version. Protect signal write privileges; unauthorized operators or consumers must not trigger full-table snapshots in production.

### 5.1. Chunking Keys

Chunking usually requires a stable key to partition ranges. A simple primary key is a good choice. If a table lacks a primary key or suitable unique key, the connector may struggle to define chunks and event keys.

Before running an incremental snapshot:

- Check primary keys and unique keys.
- Evaluate data distribution and chunk size.
- Avoid altering keys or table structure during the snapshot without a compatible procedure.
- Monitor `SELECT` load, buffer pool, I/O, and replication lag.
- Ensure snapshot signals are not sent repeatedly by accident.

### 5.2. Handling Concurrent Changes

Suppose the snapshot is reading a chunk containing order 9001 while the application updates the order status. The connector may receive both a binlog row event and a snapshot row for the same key. Watermarks and chunk reconciliation allow Debezium to determine which record to emit to keep the final state consistent.

Consumers should still use keys and versions/source positions to handle duplicates. Do not assume an incremental snapshot emits every row strictly once across all retries or restarts.

## 6. Binlog Position, GTID, and Source Offsets

An offset represents the connector's progress at the MySQL source. With binlog file/position, the position typically includes the binlog filename and byte offset. With GTID, progress can be represented by the processed GTID set. Debezium may also store partition info, server identity, snapshot state, or other internal details.

Binlog coordinate example:

~~~text
mysql-bin.000127 : 845921
~~~

This indicates the connector has processed up to that byte offset in the binlog file. Internal offset structures are not an API for applications to build dependencies on; they can change across connector versions.

### 6.1. Where Are Offsets Stored?

In Kafka Connect distributed mode, source offsets are stored in an internal Kafka topic configured by workers, typically the offset storage topic. In standalone mode, offsets may be stored in a file. The connector uses offset storage to determine where on the source to resume after restarts.

Distinguish:

- **Source offset:** the position read/recorded at MySQL.
- **Kafka record offset:** the record's position within a Kafka partition.
- **Consumer offset:** the position processed by a consumer group in Kafka.

These three offsets are independent. A consumer committing its Kafka offset does not mean the MySQL source offset advanced at the same time, and vice versa.

### 6.2. Resuming After Restarts

During a normal connector restart:

1. Kafka Connect loads the persisted source offset.
2. Debezium resolves the corresponding binlog position/GTID and snapshot state.
3. The connector verifies the required binlogs still exist.
4. The connector resumes reading from the recorded position.
5. Records may be replayed if a failure occurred around the time records were sent before the offset was durably persisted.

Therefore, consumers should process events idempotently. CDC pipelines generally require duplicate-tolerant designs rather than assuming every record appears strictly once across all failure modes.

### 6.3. Kafka Offsets Do Not Prove Downstream Persistence

The connector may have published a record to Kafka while the consumer has not processed it yet. Conversely, a consumer may process a record and crash before committing its consumer offset, causing redelivery.

If a consumer writes to another database, consider transaction coordination between updating the target and committing the Kafka offset. There is no default shared transaction across MySQL source, Kafka, and a downstream database.

A safe pattern typically involves:

- Using the source primary key as the message key.
- Applying upserts on the target.
- Recording source position/version if older events must be rejected.
- Committing the consumer offset after the target operation succeeds.
- Designing target operations to be re-runnable without duplicate side effects.

## 7. Why Is Binlog Retention Critical?

Offsets are useful only if the binlog containing the resume position still exists on MySQL. If the connector stays stopped longer than binlog retention, MySQL may purge old files. When the connector returns, it cannot resume from the saved position.

Example:

- The connector processed up to `mysql-bin.000127`.
- The connector stops for 5 days.
- MySQL keeps binlogs for only 3 days and purges the file containing the offset.
- Upon restart, the connector cannot continue reading from the old position.

At this point a recovery procedure is required: restore binlogs from archives if available, or perform a controlled snapshot/rebootstrap. Never arbitrarily point the offset to the newest file, as that skips all changes during the lost interval.

### 7.1. Choosing Retention

Retention must account for:

- Maximum acceptable connector downtime.
- Time to detect alerts and resolve incidents.
- Time the connector needs to catch up on backlog.
- Binlog generation rate during peak workloads.
- Disk capacity allocated for binlogs and data growth rate.
- Kafka Connect maintenance or upgrade windows.

If MySQL generates 50 GB of binlogs per day and needs 7 days of retention, theoretical binlog storage alone is roughly 350 GB, excluding other logs and headroom. Use peak actual generation rates for sizing, not low averages.

Monitor:

- Retained binlog disk usage.
- Oldest existing binlog file.
- Connector offset relative to the latest binlog position.
- Lag duration and catch-up rate.
- Purge events or low-disk alerts.

Never manually purge binlogs still needed by connectors. If logs must be cleaned up, verify offsets of every replica and CDC consumer first.

## 8. Schema Changes and Schema History

Binlog row events contain row data, but to decode them properly, the connector must know the table structure at the time the event was generated. If schemas evolve over time, using only the current schema can misdecode older row events.

Initial `orders` table example:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);
~~~

Later adding a column:

~~~sql
ALTER TABLE orders
  ADD COLUMN currency CHAR(3) NOT NULL DEFAULT 'VND';
~~~

Row events before the DDL have two columns; events after the DDL include `currency`. The connector must know both the old and new schemas aligned with binlog positions to interpret the bytes inside row events.

Debezium's MySQL connector maintains an internal schema history. Schema history records structural changes in order so the connector can reconstruct the necessary schema when reading binlogs or recovering from older offsets.

### 8.1. Schema History Topic vs. Data Topics

The schema history topic is internal state serving the connector. It is not a business event topic for consumers. Data topics carry table change events; schema history stores DDL/schema changes required for decoding.

Schema history must preserve complete DDL ordering and be configured per Debezium requirements—typically a single-partition topic to preserve historical order. Ensure the topic has appropriate durability and retention; do not apply log compaction, delete old segments, or alter partition counts out of routine Kafka administration habit without verifying connector version requirements.

Do not:

- Delete the schema history topic as routine Kafka housekeeping.
- Rename or swap the history topic without a recovery plan.
- Use the schema history topic as a downstream data source.
- Assume Schema Registry replaces Debezium's internal schema history.

Schema Registry (when using Avro, Protobuf, or JSON Schema) manages schemas of records emitted to consumers. Internal schema history manages how the connector interprets MySQL schemas along the binlog timeline. The two components solve different problems.

### 8.2. DDL and Schema Change Timing

MySQL records DDL in the binlog as statement/query events. Debezium must process DDL in exact order relative to row events to update schema history.

Changes to test:

- Adding nullable columns or columns with defaults.
- Dropping columns.
- Renaming columns.
- Changing data types, lengths, precision, or scale.
- Changing charset/collation.
- Adding/dropping indexes or constraints.
- Renaming tables or moving tables across schemas.
- Dropping and recreating tables.

Some DDL statements execute in MySQL with implicit commits and metadata locks. Do not run arbitrary schema migrations during long snapshots without evaluating how the connector handles them. In particular, renaming a column may appear downstream as the old field disappearing and a new field appearing; not every converter or schema registry treats it as a compatible rename.

### 8.3. Consumers Must Tolerate Schema Evolution

A resilient consumer never assumes every record always has the exact same fixed set of fields. When a schema adds a column:

- Older consumers must ignore unknown fields or rely on compatible schema evolution.
- New fields should be nullable or have clear defaults.
- Consumers must handle historical records lacking the new field.

When dropping or renaming a column:

- Identify which consumers still read the old field.
- Deploy consumers that understand both old and new schemas before the contract DDL.
- Use expand/contract for breaking changes.
- Never treat column renaming as harmless simply because SQL `ALTER` succeeds.

Schema compatibility for Avro/Protobuf/JSON Schema depends on converters and Schema Registry policies. Test backward/forward/full compatibility rules with real schemas prior to rollout.

## 9. Example Debezium MySQL Connector Configuration

Illustrative configuration for Kafka Connect distributed mode:

~~~json
{
  "name": "sales-mysql-cdc",
  "config": {
    "connector.class": "io.debezium.connector.mysql.MySqlConnector",
    "tasks.max": "1",
    "database.hostname": "mysql-source.internal",
    "database.port": "3306",
    "database.user": "debezium",
    "database.password": "INJECT_FROM_SECRET_PROVIDER",
    "topic.prefix": "sales",
    "database.include.list": "sales_app",
    "table.include.list": "sales_app.orders,sales_app.order_items",
    "snapshot.mode": "initial",
    "include.schema.changes": "true",
    "schema.history.internal.kafka.bootstrap.servers": "kafka:9092",
    "schema.history.internal.kafka.topic": "schema-history.sales"
  }
}
~~~

This example targets modern Debezium versions using `topic.prefix` and `schema.history.internal.*`. Property names, snapshot modes, and configuration options can change across versions. Always consult the reference guide matching your exact connector version.

Explanation:

- `connector.class` selects the MySQL source connector.
- `database.hostname`/`port` identifies the source MySQL instance.
- `database.user`/`password` is the CDC account; passwords must be injected securely.
- `topic.prefix` creates the topic namespace for source records.
- `database.include.list` and `table.include.list` restrict capture scope.
- `snapshot.mode` controls initial snapshot behavior.
- `include.schema.changes` controls emitting schema change info per version capabilities.
- `schema.history.internal.*` configures where internal schema history is stored.

Kafka Connect workers also require separate configuration for bootstrap servers, key/value converters, offset storage, config storage, status storage, and security. Those worker properties do not replace connector properties.

If downstream needs transaction boundaries, check the transaction metadata property for your Debezium version (typically `provide.transaction.metadata`) and configure consumers accordingly. Enable it only with an explicit requirement because transaction metadata increases record volume and downstream processing logic.

### 9.1. Data Topics

With `topic.prefix` set to `sales`, default topic names typically follow:

~~~text
sales.sales_app.orders
sales.sales_app.order_items
~~~

Topic names can change if custom topic naming strategies or transforms are configured. Do not hardcode topic names when custom naming strategies are used; verify actual topics in the deployed environment.

### 9.2. Record Keys and Values

For tables with primary keys, Debezium usually uses the primary key value as the message key. This routes events for the same row to the same Kafka partition when standard key partitioning is used.

Simplified update event example:

~~~json
{
  "before": {
    "order_id": 9001,
    "status": "PENDING"
  },
  "after": {
    "order_id": 9001,
    "status": "PAID"
  },
  "op": "u"
}
~~~

Delete events normally carry operation `d` with `before` containing pre-delete data; afterward Kafka Connect/Debezium may emit a tombstone record with the matching key and `null` value depending on configuration. Tombstones support log compaction in Kafka. Consumers must understand the difference between an enveloped delete event and a tombstone.

If a table lacks a primary key or suitable unique key, message keys may be unstable or `null`. This affects per-row partitioning, upserts, deletes, and compaction. CDC designs should favor tables with stable unique keys.

## 10. Ordering Guarantees and Duplicate Handling

MySQL's binlog orders transactions. Debezium emits events in source order within the connector's scope, yet the order observed by consumers also depends on Kafka partitions and parallel processing.

Points to remember:

- Events with the same key usually stay in the same partition when using a key partitioner.
- Ordering between two different keys is not globally guaranteed across multiple partitions.
- Consumers processing concurrently can finish a later event before an earlier one unless per-partition ordering is preserved.
- Snapshot events and streaming events may be processed at different times; never infer business order solely from timestamps.
- Retries and restarts can replay records.

### 10.1. Idempotent Consumers

Consumers should apply upserts keyed by the source primary key rather than blind `INSERT`s. For update events, update target state by key. For deletes, delete or mark the record deleted.

If downstream must prevent older events from overwriting newer events, persist an appropriate source position, GTID, or transaction metadata and apply only newer events per defined rules. Do not use `ts_ms` alone as an absolute ordering key because clock skew, timestamp precision, and transactions can make ordering ambiguous.

Target table example storing source version:

~~~sql
CREATE TABLE order_projection (
    order_id BIGINT NOT NULL PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    source_version BIGINT NOT NULL
) ENGINE=InnoDB;
~~~

The `source_version` field here is a conceptual example. In real systems, choose a meaningful, comparable ordering token from the envelope/source metadata. File/position binlog coordinates are not simple single integers; you may need to store structured positions or normalized transaction metadata.

### 10.2. Handling Deletes and Tombstones

Consumers must distinguish:

- Delete envelope: an event describing a delete operation, potentially containing `before`.
- Tombstone: a record with the same key and a `null` value.

If a consumer ignores tombstones while handling delete envelopes properly, projections can still stay updated. If a consumer uses a compacted topic to reconstruct final state, tombstones allow Kafka to remove keys from the compacted log per broker semantics.

Do not treat `null` values as always indicating corrupted data; they can be intentional tombstones.

## 11. Transaction Metadata and Consistency

A single MySQL transaction can modify multiple rows or multiple tables. Debezium can emit transaction metadata when configured appropriately; records may include a transaction identifier and intra-transaction ordering details depending on connector version.

If downstream needs to apply a group of changes as a single logical unit, evaluate transaction metadata and how consumers handle transaction boundaries. Do not assume Kafka delivers an entire transaction's events as one single message.

Options:

- Accept row-by-row updates and design projections to tolerate temporary intermediate states.
- Use transaction metadata to buffer related events before applying.
- Write data to staging and commit projections once the transaction-end marker arrives.

Holding overly large transactions downstream increases latency and memory usage. Balance business consistency against streaming throughput capability.

## 12. MySQL Failover and Connectors

If the source MySQL is a primary in a replication topology, during failover to another server the connector must resume reading the same data history. GTIDs help identify processed transactions across servers, but failover is safe only if the topology maintains consistent GTID/binlog history.

Before pointing the connector to a new node:

- Confirm the new node has complete data and GTID history.
- Confirm required binlogs still exist.
- Confirm server identity and replication privileges.
- Verify connector configuration can recognize the new source.
- Never let the connector read two out-of-sync sources simultaneously.
- Verify schema history remains consistent with the event stream.

If a failover loses the binlogs containing the offset, the connector may be unable to resume normally. In that case, restore log archives or run a snapshot/rebootstrap procedure. Never reset offsets just to make the connector transition to `RUNNING` without knowing what data will be skipped or replayed.

## 13. Other CDC Tools and How to Choose

Debezium is not the only choice. Several approaches exist:

| Option | Characteristics | Best fit when |
|---|---|---|
| Debezium | Binlog-based CDC connector, integrates with Kafka Connect, schema history, and snapshots | Needing a Kafka pipeline, multiple connectors, and multiple consumers |
| Maxwell | Lightweight MySQL binlog reader emitting JSON events to Kafka or message streams depending on setup | Wanting a relatively simple MySQL CDC pipeline and accepting the tool's feature model |
| Canal | Popular MySQL CDC ecosystem in some environments, with binlog parser and adapters | Infrastructure already runs Canal or needs integration with its ecosystem |
| AWS DMS | Managed migration and CDC service on AWS | Preferring a managed service with supported targets |
| Native binlog client | Reading replication protocol/binlogs directly via libraries or custom code | Having specialized requirements and a team capable of maintaining parsers, offsets, schemas, and recovery |
| MySQL replication | Replicating transactions between MySQL servers | The goal is MySQL replicas, read scaling, or HA rather than publishing events to heterogeneous consumers |

Selection criteria:

- Supported sources and targets.
- Snapshot mechanisms and re-capture capabilities.
- Offset storage and recoverability.
- DDL/schema history management.
- Handling of transactions, deletes, keys, and schema evolution.
- Broker integration, security, monitoring, and operations.
- Catch-up speed, throughput, and latency.
- Community, documentation, version support, and team capability.

Do not pick a tool based solely on throughput benchmarks. A fast pipeline lacking schema-change or offset recovery capabilities creates greater data risk during incidents.

## 14. Monitoring a CDC Pipeline

A CDC pipeline requires monitoring the source, connector, broker, and consumers.

| Group | Metrics / Conditions |
|---|---|
| Connector health | `RUNNING`/`FAILED` state, task restarts, most recent errors |
| Snapshot | Table/chunk progress, rows read, snapshot duration, lock errors |
| Source lag | Distance between latest binlog position and connector-processed position |
| Binlog retention | Oldest existing file, log disk usage, risk of purging needed offsets |
| Kafka | Produce errors, broker availability, topic partitions, replication, and disk |
| Schema history | Topic exists, readable/writable, not deleted or altered out of process |
| Consumer | Consumer lag, retries, dead-letter queue, schema errors, and processing time |
| Data quality | Duplicates, missing keys, unexpected NULLs, row counts, and reconciliation checksums |

Do not rely solely on connector `RUNNING` status as proof of pipeline health. A connector can be `RUNNING` while source lag climbs steadily, downstream consumers stall, or schema history nears storage limits.

### 14.1. Estimating Lag

Lag can be measured via binlog position deltas, source commit timestamps, and broker arrival timestamps. Each method has caveats:

- Timestamps are affected by clock skew and inter-server delays.
- Binlog positions are comparable only within the same file/log sequence and require rollover handling.
- GTID sets compare transaction history but do not directly express processing duration.
- Consumer lag reflects Kafka consumer progress, not source connector progress.

Track multiple indicators together to distinguish a slow connector from a slow consumer.

## 15. Common Troubleshooting Scenarios

### 15.1. Connector Fails to Start

Check:

1. DNS, TCP, TLS, and firewalls from Kafka Connect workers to MySQL.
2. User/password, host grants, and snapshot/replication privileges.
3. `log_bin`, `binlog_format`, `binlog_row_image`, and `server_id`.
4. Connector class and version dependencies.
5. Property names matching your Debezium version.
6. Schema history topic and Kafka permissions.

Read the root error in connector logs. Do not change many configuration settings at once, as that obscures the root cause.

### 15.2. Connector Reports Binlog No Longer Exists

Usually MySQL purged the file needed by the saved offset. Resolution steps:

- Inspect the current offset and the required binlog file/position.
- Check whether archived binlogs can be restored.
- If no logs exist, determine which time window a snapshot/rebootstrap will replay or require reconciliation for.
- Plan consumer pauses or duplicate handling while rebuilding the baseline.
- Increase retention and add alerts to prevent recurrence.

Do not point the connector to start at the newest binlog just to clear the error. Doing so can skip changes that occurred while the connector was stopped.

### 15.3. Snapshot Is Slow

Check:

- Table and index sizes.
- Read speed, buffer pool, and I/O.
- Lock modes and long-running transactions.
- Impact on application workload.
- Network throughput to Kafka Connect.
- Whether consumers/brokers are causing backpressure.

For large tables, consider incremental snapshots, controlled increases in read capacity, or narrowing capture scope. Never relax lock modes in production without testing consistency first.

### 15.4. Schema History Mismatch or Unreadable

Check:

- The schema history topic still exists and was not deleted.
- The connector points to the exact topic for that deployment.
- The topic has proper configuration and permissions.
- The offset points to a binlog position covered by matching schema history.
- Whether any DDL ran outside the process or was filtered from the connector.

Never recreate an empty schema history topic and restart the connector with old offsets. The connector may fail to decode existing row events or construct incorrect schemas. Follow recovery instructions matching your exact Debezium version.

### 15.5. Consumers Receive Duplicates

Duplicates can occur due to:

- Connector restarts around the moment records were sent and source offsets saved.
- Kafka consumers finishing processing before committing consumer offsets.
- Re-running snapshots or incremental snapshots re-emitting chunks.
- Consumer retries after errors with indeterminate target commit state.

Use upserts/idempotency keys, record source versions, and monitor duplicate rates. Never manually delete duplicate records from Kafka without understanding the impact on offsets and ordering.

## 16. Safe Schema Change Workflow with CDC

Schema changes require coordinating MySQL, Debezium, converters/Schema Registry, and all consumers.

Example renaming column `status` to `order_status`:

1. **Expand:** add nullable `order_status`, keeping `status`.
2. Deploy the application writing both columns in the same transaction.
3. Backfill older rows in batches while letting the connector continue reading the binlog.
4. Verify events contain both the new and old fields; update consumers to understand the new schema.
5. Switch consumers to read `order_status` once data is reconciled.
6. Wait until all older consumers and applications no longer depend on `status`.
7. **Contract:** drop `status` in a separate migration.
8. Verify schema history, DDL events, and consumers after contracting.

Never rename a column directly while consumers still expect the old field. The DDL may be captured by the connector, yet downstream systems are not guaranteed to automatically map the old field to the new field.

### 16.1. Changing Data Types

When changing `DECIMAL` precision/scale, `VARCHAR` length, `ENUM`, or numeric types:

- Check whether existing data fits within the new type bounds.
- Check whether converters and Schema Registry accept the change.
- Verify how consumers handle precision, scale, and `NULL`.
- Verify historical events still decode under older schemas.
- Use expand/contract migrations for incompatible changes.

Do not test only new records. Consumers may need to replay older records from Kafka, so new schemas must remain compatible with records retained according to topic retention.

## 17. Testing a CDC Pipeline

A CDC test should run against real MySQL and a real broker or an equivalent integration environment. Test end-to-end from source operations to consumer outcomes, not just whether the connector reports `RUNNING`.

Key tests:

1. Snapshot a pre-populated table and verify `r` records.
2. Run `INSERT`, `UPDATE`, and `DELETE` after the snapshot and verify `op`/`key`/`before`/`after`.
3. Restart the connector and verify it resumes from its offset.
4. Stop the connector for a short interval, restart it, and verify catch-up.
5. Execute DDL adding a column and verify schema history and new records.
6. Run an incremental snapshot on a large table while updating the same rows concurrently.
7. Simulate consumer restarts to test idempotency.
8. Test tables without primary keys and decide key-handling strategy.
9. Simulate binlog retention expiration in a lab environment and rehearse recovery.
10. Test TLS, credential rotation, and CDC user privileges.

### 17.1. Data Reconciliation

Once CDC is running, reconcile across:

- Row counts per table or logical partition.
- Aggregates by day, status, or tenant.
- Checksums across primary key ranges.
- Counts of processed inserts/updates/deletes.
- Records with missing keys, duplicates, or schema conversion errors.

Do not use row counts alone as complete proof. Two tables with identical row counts can still contain different data. Reconciliation must account for snapshot boundaries and ongoing concurrent transactions.

## 18. Deployment and Operations Runbook

### Before Enabling the Connector

- [ ] Choose CDC tool and connector version.
- [ ] Verify MySQL binlog settings and server identity.
- [ ] Choose binlog retention based on expected downtime and catch-up.
- [ ] Create a least-privilege CDC user.
- [ ] Prepare TLS and secret management.
- [ ] Define database/table include lists.
- [ ] Prepare the schema history topic and Kafka Connect offset storage.
- [ ] Verify consumers handle snapshots, deletes, and schema changes.

### During Snapshot Execution

- [ ] Monitor locks, query load, I/O, and table progress.
- [ ] Verify snapshot records and row counts.
- [ ] Do not run breaking DDL during the snapshot window without a plan.
- [ ] Confirm the connector transitions to streaming after the snapshot.
- [ ] Monitor source lag and Kafka consumer lag.

### During Streaming Operations

- [ ] Alert on `FAILED` connectors/tasks or frequent restarts.
- [ ] Alert when binlog retention nears dropping below expected downtime.
- [ ] Monitor schema history and offset storage.
- [ ] Monitor duplicates, conversion errors, and dead-letter queues.
- [ ] Verify consumer idempotency and per-key ordering.
- [ ] Test MySQL failover periodically.

### During Recovery

- [ ] Determine the source offset and whether required binlogs still exist.
- [ ] Preserve schema history and offsets during investigation.
- [ ] If re-snapshotting is needed, scope duplicates and baseline state.
- [ ] Prepare downstream reconciliation before reopening traffic.
- [ ] Record start/end timestamps of the outage window.
- [ ] Update retention, alerts, and runbooks post-incident.

## 19. Practical Scenario

An e-commerce system has a MySQL database `sales_app` with tables `orders`, `order_items`, and `customers`. The data warehouse needs near-real-time data. The team deploys the Debezium MySQL Connector via Kafka Connect. Initially, the connector captures a snapshot and then streams the binlog.

During the first week, the connector is stopped for 30 hours for Kafka Connect maintenance. MySQL retains binlogs for only 24 hours. After restarting, the connector reports that the binlog containing its saved offset cannot be found. At the same time, the application team wants to rename `orders.status` to `orders.order_status`.

Build an action plan:

1. Identify the last source offset, binlog file/position, or GTID saved by the connector.
2. Check whether binlog archives contain the purged log segments.
3. If archives exist, evaluate restoring them and resuming cleanly from the exact history.
4. If no archives exist, plan a snapshot/rebootstrap and identify downstream data that may experience duplicates.
5. Keep the current schema history intact until the recovery plan is finalized.
6. Defer the column-rename DDL and execute expand/contract by adding the new column and dual-writing.
7. Update consumers to understand the new schema and reconcile data before contracting the old column.
8. Increase binlog retention enough to cover maximum downtime, remediation time, and catch-up.
9. Add alerts for source lag, oldest binlog file, connector status, and consumer lag.
10. Rehearse the "connector stopped longer than retention" scenario in a lab environment.

**Self-check questions:**

1. What problem does the initial snapshot solve before binlog streaming?
2. Why must the snapshot boundary be coordinated with the binlog position?
3. How does operation `r` differ from `c`?
4. How do source offsets differ from Kafka record offsets and consumer offsets?
5. Why must binlog retention exceed maximum connector downtime?
6. How does Debezium's internal schema history differ from Schema Registry?
7. Why can renaming a column break older consumers even when the connector still reads the binlog?
8. How should consumers handle duplicates and deletes/tombstones?
9. When are incremental snapshots useful, and why is a stable key required?
10. If the required offset has been purged, why should you not start the connector at the newest binlog?

## Conclusion

CDC with Debezium turns the MySQL binlog into an event stream for downstream systems. Snapshots provide baseline state, binlog streaming captures subsequent changes, source offsets let the connector resume across restarts, and schema history decodes row events across DDL changes. Pipeline reliability depends on consistent snapshots, binlog retention, offset storage, schema evolution, and consumer idempotency. Operate CDC as a stateful data system: monitor source lag, protect schema history, test restarts/failover, and maintain a re-snapshot runbook before promoting the pipeline to production.

## References

- [Debezium Documentation — MySQL Connector](https://debezium.io/documentation/reference/stable/connectors/mysql.html)
- [Debezium Documentation — MySQL Connector Snapshot](https://debezium.io/documentation/reference/stable/connectors/mysql.html#mysql-snapshots)
- [Debezium Documentation — MySQL Connector Schema History](https://debezium.io/documentation/reference/stable/connectors/mysql.html#mysql-schema-history)
- [Debezium Documentation — Incremental Snapshots](https://debezium.io/documentation/reference/stable/incremental-snapshots.html)
- [Kafka Connect Documentation — Source Connector Offsets](https://kafka.apache.org/documentation/#connectconfigs)
- [MySQL 8.4 Reference Manual — The Binary Log](https://dev.mysql.com/doc/refman/8.4/en/binary-log.html)
- [MySQL 8.4 Reference Manual — Replication and Binary Logging Options](https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html)
