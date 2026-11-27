# Lifecycle Storage and Old Data Purge Strategies in Oracle

## 1. Why Is Data Lifecycle Management Needed?

In a long-running system, data usually grows continuously: orders, transactions, business logs, access histories, events, sensor readings, and reporting data. Not all data needs to reside on the same storage tier, share the same access patterns, or be kept indefinitely.

**Information Lifecycle Management (ILM)** organizes data according to its lifecycle stages and business value. A policy typically distinguishes:

- Recent, frequently accessed data: stored on fast storage to serve active transactions.
- Stabilized data, rarely updated yet still queried: moved to lower-cost storage or compressed to save space.
- Historical data required by regulations: archived, with controlled access rights and recoverability.
- Data past retention and free of legal holds: purged from the system via an approved workflow.

Oracle Partitioning helps manage data groups as independent units. If a table is partitioned by time, the DBA can archive, move, compress, truncate, or drop an entire partition instead of processing millions of individual rows.

A sound lifecycle workflow must answer these questions:

1. How long is data retained in the transactional system?
2. When is data moved to archive or cheaper storage?
3. Which data must be retained by law, contract, or audit requirements?
4. When is permanent deletion permitted?
5. How can archived data be queried or restored?
6. Does deletion impact foreign keys, indexes, materialized views, replication, backups, and applications?

> Content uses Oracle Database 19c. Partitioning is a feature requiring separate licensing where applicable; verify your organization's entitlement before deploying. Run DDL examples only in a lab schema or approved maintenance windows. Oracle DDL performs an implicit commit and cannot be rolled back like a DELETE statement.

## 2. Design Retention Policies Before Designing Partitions

Do not start with a `DROP PARTITION` statement. First, establish a retention policy agreed upon by business stakeholders and data governance.

### 2.1. Identify the retention timestamp

A table may have multiple date/time columns:

- CREATED_AT: when the system recorded the row.
- EVENT_TIME: when the event actually occurred.
- BUSINESS_DATE: business date used for reconciliation.
- CLOSED_AT: when the case/record was closed.
- INGESTED_AT: when data was loaded into the database.

The partition key should be based on the column that fits queries, retention, and operations. For example:

- Transaction tables are often partitioned by BUSINESS_DATE or TRANSACTION_DATE.
- Event log tables may be partitioned by EVENT_TIME or INGESTED_AT.
- Case/record tables may be partitioned by CLOSED_AT if retention starts after closure.

Do not assume CREATED_AT is always the right column. An event might arrive days late; if retention uses ingestion time while legal obligations count from occurrence time, the policy may be wrong.

### 2.2. Define retention intervals

Illustrative policy example:

| Stage | Data age | Management approach |
| --- | --- | --- |
| HOT | 0–12 months | Online on high-performance storage |
| WARM | Over 12 to 36 months | Still queryable; can be compressed or moved to another tablespace |
| ARCHIVE | Over 36 to 84 months | Stored in archive table/tablespace or separate storage system |
| PURGE | After 84 months | Deleted once retention obligation ends and no legal hold applies |

These numbers are examples only. Actual periods must follow laws, contracts, audit requirements, security policies, and recovery objectives.

### 2.3. Distinguish archiving from purging

**Archive** means moving data to another storage location while preserving retrieval or restoration capabilities per policy.

**Purge** means deleting data from managed storage. A `DROP PARTITION` command is not an archive; it removes the partition from the table. If historical data must be kept, archive or export it beforehand.

Do not treat a regular backup as an archive. Backups serve system recovery; archives serve deliberate, time-bound retention and usually require dedicated metadata, searchability, access controls, and restoration workflows.

### 2.4. Legal holds and retention exceptions

A record may need to be kept longer than the standard policy due to:

- Ongoing disputes or investigations.
- Audit requirements.
- Contractual or industry regulations.
- Data preservation orders.

Purge workflows must check legal holds before deleting. Hold lists can be managed in a dedicated control table or through a records management system. Do not assume an old partition is eligible for deletion merely because its date is past the cutoff.

## 3. Partitioning as the Foundation of Time-Based Retention

### 3.1. How does partitioning work?

Partitioning divides one logical table into physical partitions. Applications still query the same table name; Oracle automatically routes rows to partitions based on the partition key.

Example:

~~~text
SALES
  |
  +-- P2025_01  (01-Jan to before 01-Feb)
  +-- P2025_02  (01-Feb to before 01-Mar)
  +-- P2025_03  (01-Mar to before 01-Apr)
  +-- P2025_04  (01-Apr to before 01-May)
  ...
~~~

If a query has a condition on the partition key, Oracle can access only the relevant partitions. This mechanism is called partition pruning.

Example:

~~~sql
SELECT SUM(amount)
FROM sales
WHERE sale_date >= DATE '2025-02-01'
  AND sale_date <  DATE '2025-03-01';
~~~

If SALES is partitioned by SALE_DATE, Oracle can read only the February partition instead of scanning the entire table.

### 3.2. Choosing granularity

| Granularity | Suitable when | Considerations |
| --- | --- | --- |
| Daily | Very high volume, need exact day-level purge/archive | Partition count grows rapidly |
| Monthly | Many transactional and reporting systems | Good balance between administration and partition count |
| Quarterly | Moderate volume, quarterly retention | Less flexible when needing to delete part of a month |
| Yearly | Low volume or annual retention | A single partition can become too large |

Do not choose daily partitioning merely to delete data more precisely if each day only has a few hundred rows. Partition counts, subpartitions, index partitions, and dictionary overhead must also be weighed.

### 3.3. The partition key must match queries and retention

If most queries filter by transaction date and retention is also calculated from transaction date, partitioning by transaction date is a natural fit.

If queries frequently filter by CUSTOMER_ID while retention is date-based, you can combine:

- RANGE on SALE_DATE.
- LOCAL index on CUSTOMER_ID.
- Composite partitioning if needed and permitted by licensing/architecture.

Do not partition by a column purely for DDL convenience if it does not reflect how data is accessed or governed.

### 3.4. Partition boundaries are exclusive upper bounds

With RANGE partitioning, the value in `VALUES LESS THAN` is an exclusive upper bound. Example:

~~~sql
PARTITION p2025_01 VALUES LESS THAN (DATE '2025-02-01')
~~~

This partition contains dates strictly before 01-Feb-2025, starting from the previous partition's upper bound. To represent January, the right predicate is:

~~~sql
sale_date >= DATE '2025-01-01'
AND sale_date < DATE '2025-02-01'
~~~

This is a half-open interval `[start of month, start of next month)`. It avoids end-of-day boundary errors, especially when DATE columns include hours/minutes/seconds.

### 3.5. Standardize time zones

For multinational event data, standardize:

- Whether timestamps are stored in UTC or local time.
- Which time zone defines the business date.
- Which calendar defines cutoff points.
- How late-arriving data and backdated timestamps are handled.

If partitioning on DATE while converting from TIMESTAMP WITH TIME ZONE, convert consistently before storing. Never let one process load in UTC while another loads in local time without a convention.

## 4. Creating a Monthly RANGE-Partitioned Table

Sales transaction table example:

~~~sql
CREATE TABLE sales_lifecycle (
    sale_id      NUMBER        NOT NULL,
    sale_date    DATE          NOT NULL,
    customer_id  NUMBER        NOT NULL,
    amount       NUMBER(12,2)  NOT NULL,
    status       VARCHAR2(20 CHAR)
)
PARTITION BY RANGE (sale_date)
(
    PARTITION p2025_01 VALUES LESS THAN (DATE '2025-02-01'),
    PARTITION p2025_02 VALUES LESS THAN (DATE '2025-03-01'),
    PARTITION p2025_03 VALUES LESS THAN (DATE '2025-04-01')
);
~~~

In this example, the first partition holds dates less than 01-Feb-2025. Understand that the first partition's scope also includes dates before 01-Jan-2025 if no lower partition exists.

Create a local index:

~~~sql
CREATE INDEX ix_sales_lifecycle_customer
ON sales_lifecycle(customer_id, sale_date)
LOCAL;
~~~

A local index is partitioned in alignment with table partitions. This is convenient for partition maintenance because index partitions are tied to individual table partitions.

### 4.1. Adding a partition for a new month

Before loading the next month's data:

~~~sql
ALTER TABLE sales_lifecycle
ADD PARTITION p2025_04
VALUES LESS THAN (DATE '2025-05-01');
~~~

If no partition covers the new date value, INSERT can fail with ORA-14400. Operational procedures should create future partitions before batch loads begin.

### 4.2. Should you create a MAXVALUE partition?

You can create a final partition with `VALUES LESS THAN (MAXVALUE)` to avoid errors when data arrives late or future partitions have not been created yet. However, new rows may land in the MAXVALUE partition instead of the expected monthly partition.

When you later need to add a partition with a bound below MAXVALUE, you must `SPLIT` the MAXVALUE partition. That can involve moving data and maintaining indexes.

Therefore:

- Use MAXVALUE if avoiding INSERT failures on out-of-range data is top priority.
- Maintain a process to monitor and handle data inside MAXVALUE.
- Do not let the MAXVALUE partition become a permanent catch-all dumping ground.
- If not using MAXVALUE, pre-create partitions and configure alerts ahead of load deadlines.

### 4.3. Updating the partition key

Oracle defaults to `DISABLE ROW MOVEMENT`. If updating the partition key forces a row to move to a different partition, the statement can fail with ORA-14402.

Row movement can be enabled:

~~~sql
ALTER TABLE sales_lifecycle ENABLE ROW MOVEMENT;
~~~

Enable this only when business rules genuinely require updating the partition key. Moving rows can incur index, redo/undo costs, and change `ROWID`; do not treat it like a normal column update.

## 5. Interval Partitioning: Auto-Creating Partitions Over Time

If data arrives continuously by month, INTERVAL partitioning lets Oracle automatically create partitions for values exceeding the transition point.

~~~sql
CREATE TABLE sales_interval (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE   NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))
(
    PARTITION p_before_2025
    VALUES LESS THAN (DATE '2025-01-01')
);
~~~

The initially declared RANGE partition defines the transition point. When inserting a row whose SALE_DATE falls in the interval region, Oracle automatically creates a monthly partition.

### 5.1. Benefits and limitations

Benefits:

- No need to create monthly partitions via scripts.
- Reduces the risk of forgetting to create new partitions.
- Suits time-series data arriving steadily over time.

Points to watch:

- New partitions get system-generated names like `SYS_P...` unless renamed/managed by users.
- Must monitor partition counts and partition names in the data dictionary.
- Interval partitioning still requires retention, archiving, and purging plans.
- Not every partition key type or interval expression fits every business requirement.

### 5.2. Inspecting auto-generated partitions

~~~sql
SELECT table_name,
       partition_name,
       partition_position,
       tablespace_name,
       num_rows
FROM user_tab_partitions
WHERE table_name = 'SALES_INTERVAL'
ORDER BY partition_position;
~~~

With interval partitioning, never hard-code `SYS_P...` names in purge scripts if names can vary across databases. Use partition position, `HIGH_VALUE`, or metadata managed by partition creation procedures to identify the right partition.

### 5.3. Referencing partitions by timestamp

Oracle supports syntax referencing partitions by value:

~~~sql
SELECT COUNT(*)
FROM sales_interval PARTITION FOR (DATE '2025-03-15');
~~~

This is helpful when partition names are system-generated. For maintenance DDL such as `DROP PARTITION`, statements require the partition name; operational scripts must query metadata to fetch the exact name and verify high values before executing.

## 6. Organizing HOT, WARM, ARCHIVE, and PURGE

An architecture can use tablespaces and partitions to place data across different tiers:

~~~text
                   Lifecycle policy
                           |
             +-------------+-------------+
             |             |             |
            HOT           WARM         ARCHIVE
        most recent   less accessed  long-term history
             |             |             |
        fast storage   lower-cost TS   archive TS / export
             |             |             |
             +-------------+-------------+
                           |
                   retention expired
                           |
                    legal hold check
                           |
                         PURGE
~~~

Example:

- HOT: most recent 12 monthly partitions.
- WARM: partitions from month 13 to month 36, potentially moved to another tablespace or compressed.
- ARCHIVE: older partitions, exchanged to an archive table or exported to an archive repository.
- PURGE: deleted after legal retention expires and required archive/backup checks pass.

Four separate tablespaces are not mandatory. You can share a tablespace while classifying by partition, or store archives outside the database. What matters is having metadata and processes that track which tier data belongs to.

## 7. DROP PARTITION: Fast Old-Data Deletion by Partition

### 7.1. When to use?

If an entire partition is past retention and archive/legal-hold checks are cleared, `DROP PARTITION` is an efficient way to delete a large data group.

~~~sql
ALTER TABLE sales_lifecycle
DROP PARTITION p2025_01
UPDATE INDEXES;
~~~

This command removes the January partition from the table, including its data and partition metadata. The corresponding local index partition is handled as well.

### 7.2. DROP PARTITION vs. DELETE

| Characteristic | DROP PARTITION | DELETE |
| --- | --- | --- |
| Scope | Entire partition | Rows matching WHERE |
| Mechanism | DDL managing segments/metadata | Row-by-row DML |
| Undo/redo | Unlike row-by-row deletion; typically far less than a massive DELETE | Generates undo/redo for row and index changes |
| DELETE triggers | Does not fire like row-by-row DELETE | Fires DELETE triggers |
| ON DELETE CASCADE | Does not auto-cascade like row-by-row DELETE | Can delete child rows if FK uses ON DELETE CASCADE |
| Rollback | DDL cannot be rolled back | Can roll back before COMMIT |
| Recycle bin | Dropped partitions do not go into recycle bin | Recycle bin does not apply that way |
| Best suited for | Deleting a whole expired partition | Deleting a subset of rows or needing trigger/FK semantics |

### 7.3. DROP PARTITION cannot be recovered via ROLLBACK

`DROP PARTITION` is DDL. Oracle performs an implicit commit per DDL rules, and dropped partitions are not placed in the recycle bin. Therefore:

- Never run `DROP PARTITION` before confirming archiving.
- Double-check the exact table, partition, and high value.
- Have backups or archives meeting recovery requirements.
- Log audit records: who ran it, when, which partition, and why.

Do not assume `FLASHBACK TABLE` or the recycle bin can restore a dropped partition. Confirm your recovery plan before purging.

### 7.4. Limitations of DROP PARTITION

- Cannot drop the final partition if the table has only one partition left; handle at the table level instead.
- Certain operations have restrictions with interval partitioning, reference partitioning, and special table types.
- If foreign keys reference data in the partition, resolve referential dependencies first.
- After DDL, check local/global index status.

## 8. TRUNCATE PARTITION: Deleting Rows While Retaining the Partition

When you need to empty a partition while retaining its definition:

~~~sql
ALTER TABLE sales_lifecycle
TRUNCATE PARTITION p2025_01
UPDATE INDEXES;
~~~

Unlike `DROP PARTITION`:

- `TRUNCATE PARTITION` keeps the partition in the table.
- Rows inside the partition are removed.
- The matching local index partition is truncated.
- Global indexes must be maintained or handled with appropriate options.

`TRUNCATE PARTITION` fits when the partition will be reused or when clearing a region's data while keeping the partition structure intact.

### 8.1. DROP STORAGE and REUSE STORAGE

Oracle supports options controlling space handling when truncating a partition:

- `DROP STORAGE`: returns most extents allocated beyond initial storage per Oracle's storage rules.
- `REUSE STORAGE`: retains allocated space so the partition can reuse it.

Choose based on capacity goals and reload likelihood. Do not confuse `TRUNCATE PARTITION` with removing partition metadata.

### 8.2. TRUNCATE PARTITION also cannot be rolled back

`TRUNCATE` is DDL and cannot be rolled back to recover deleted rows. Before running, check archiving, backups, foreign keys, and indexes.

## 9. Archiving via EXCHANGE PARTITION

A common strategy is converting an old partition into a standalone table, then archiving or exporting that table.

### 9.1. Concept

~~~text
SALES partitioned table
        |
        | EXCHANGE PARTITION
        v
SALES_ARCHIVE_STAGE nonpartitioned table
        |
        +--> export / backup / move tablespace
        |
        +--> verify archive
        |
        +--> retain or purge per retention
~~~

`EXCHANGE PARTITION` swaps the data segment between a partitioned table's partition and a nonpartitioned table. This is a metadata/segment swap, usually far faster than copying millions of rows via `INSERT SELECT`.

### 9.2. Create a compatible archive staging table

Example table structure:

~~~sql
CREATE TABLE sales_archive_stage (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE   NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL,
    status       VARCHAR2(20 CHAR)
);
~~~

The exchange table must match in column count, order, data types, and conditions required by Oracle. If using `INCLUDING INDEXES`, create matching indexes on the exchange table to swap local index partitions cleanly.

### 9.3. Exchange the partition

~~~sql
ALTER TABLE sales_lifecycle
EXCHANGE PARTITION p2025_01
WITH TABLE sales_archive_stage
INCLUDING INDEXES
WITH VALIDATION
UPDATE GLOBAL INDEXES;
~~~

Meaning:

- Data from partition `P2025_01` moves into `SALES_ARCHIVE_STAGE`.
- Existing data in `SALES_ARCHIVE_STAGE` (if any) moves into the partition.
- `INCLUDING INDEXES` requires matching indexes to swap index segments cleanly.
- `WITH VALIDATION` directs Oracle to verify rows in the exchange table belong to the exchanged partition. This is the default if omitted.
- `UPDATE GLOBAL INDEXES` maintains global indexes during the operation.

After exchange, partition `P2025_01` becomes empty if the staging table was initially empty; the staging table receives the historical data. You can then export, move, or compress the archive table.

### 9.4. WITH VALIDATION and WITHOUT VALIDATION

`WITH VALIDATION` checks whether data in the exchange table satisfies the partition key bounds. If any row falls outside the range, the operation fails.

`WITHOUT VALIDATION` skips this check. Use it only when the pipeline already guarantees data belongs in the partition through a trusted check. If validation is skipped and invalid rows exist, data can end up in the wrong logical partition and distort partition pruning or administrative results.

Never choose `WITHOUT VALIDATION` solely to speed up the command without prior data controls.

### 9.5. INCLUDING INDEXES and EXCLUDING INDEXES

- `INCLUDING INDEXES`: swaps corresponding indexes between local index partitions and indexes on the exchange table when structures meet requirements.
- `EXCLUDING INDEXES`: does not swap corresponding indexes; some indexes may be marked unusable and require rebuilding.

If the table has global indexes, evaluate `UPDATE GLOBAL INDEXES`. Exchange partition does not automatically keep all global indexes usable in every scenario.

### 9.6. Verify after exchange

~~~sql
SELECT COUNT(*)
FROM sales_archive_stage;

SELECT COUNT(*)
FROM sales_lifecycle PARTITION (p2025_01);
~~~

Reconcile counts and sample data before exporting or purging. Once the archive is confirmed safe, you can drop the empty partition if policy dictates:

~~~sql
ALTER TABLE sales_lifecycle
DROP PARTITION p2025_01
UPDATE INDEXES;
~~~

If you want to keep the partition for reloading or structural continuity, you can leave the empty partition in place.

## 10. Archiving to Another Tablespace or Storage System

After exchanging a partition into an archive table, you can:

- Move the table to an archive tablespace.
- Apply compression suited to storage.
- Export using Data Pump.
- Move tablespaces via transportable tablespaces if architecture and conditions fit.
- Push exports to object storage or enterprise archive systems.

Example moving the archive table to a tablespace:

~~~sql
ALTER TABLE sales_archive_stage
MOVE TABLESPACE archive_ts;
~~~

If using compression, choose syntax and compression levels matching storage, edition, and licensing. Hybrid Columnar Compression depends on supported storage platforms; never assume it works on arbitrary storage.

### 10.1. Archives must include metadata

A useful archive should store:

- Source table and partition name.
- Partition lower/upper bounds.
- Archive timestamp.
- Row counts and checksums/reconciliation data if required by policy.
- Schema version and column mappings.
- Location of export files or tablespace.
- Retention of the archive itself.
- Restoration procedure and authorized personnel.

A dump file alone without metadata makes finding and restoring data far harder.

## 11. Handling Indexes During Partition Maintenance

Partition maintenance can affect indexes. Distinguish local and global indexes.

### 11.1. Local indexes

Local indexes have partitions matching table partitions. When dropping/truncating a table partition, the corresponding local index partition is dropped/truncated in the same operation.

This is why local indexes are usually convenient for tables with time-based retention.

### 11.2. Global indexes

Global indexes can reference rows across many table partitions. When dropping/truncating/exchanging a partition, Oracle must handle related entries so the index does not point to invalid rows or lose usability.

Example:

~~~sql
ALTER TABLE sales_lifecycle
DROP PARTITION p2025_01
UPDATE INDEXES;
~~~

`UPDATE INDEXES` instructs Oracle to maintain indexes during the operation. If omitted, global indexes or index partitions may be marked `UNUSABLE` and require rebuilding.

### 11.3. Asynchronous global index maintenance

Oracle 19c supports asynchronous global index maintenance for `DROP PARTITION` and `TRUNCATE PARTITION` in supported cases. For heap-organized tables, the operation can primarily update metadata while cleaning up orphaned entries later.

Key restrictions include table type, object types, domain indexes, and other conditions. Oracle runs a system job to clean up deferred global indexes; do not arbitrarily delete that job.

Even when asynchronous maintenance is used, still specify `UPDATE INDEXES` per Oracle guidelines and verify index status afterward. `UPDATE INDEXES` does not mean zero cost: synchronous index maintenance can lengthen DDL and generate redo/undo.

### 11.4. Checking indexes after maintenance

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE table_name = 'SALES_LIFECYCLE';
~~~

Partitioned indexes:

~~~sql
SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name IN (
    SELECT index_name
    FROM user_indexes
    WHERE table_name = 'SALES_LIFECYCLE'
)
ORDER BY index_name, partition_position;
~~~

If any index partition is `UNUSABLE`, identify the exact scope and rebuild per policy before index-dependent workloads resume.

## 12. Foreign Keys and Related Data

This is one of the easiest places for a purge to fail.

### 12.1. Parent and child

Suppose:

- `SALES` is the parent table holding transactions.
- `SALE_LINES` is the child table holding transaction line items.
- `SALE_LINES.SALE_ID` references `SALES.SALE_ID`.

If you try to drop an old partition of `SALES` while child rows still reference parent rows, Oracle may block the operation due to referential integrity.

`DROP`/`TRUNCATE PARTITION` is DDL, not equivalent to row-by-row `DELETE`. Do not assume `ON DELETE CASCADE` executes automatically when dropping a partition.

### 12.2. Purge ordering

A workflow can:

1. Archive parent and child for the same retention period.
2. Verify row counts and foreign key relationships in the archive.
3. Delete child rows/partitions per policy.
4. Delete parent rows/partitions.
5. Verify constraints and indexes.

If the child table is also partitioned by time, determine how to synchronize boundaries and purge order. If partitioned with `REFERENCE` partitioning, Oracle has specific cascade rules and restrictions; never mechanically apply standard `RANGE` table syntax.

### 12.3. DELETE and ON DELETE CASCADE

If row-by-row deletion is needed:

~~~sql
DELETE FROM sales
WHERE sale_date < :cutoff_date;
~~~

`DELETE` honors foreign keys and can trigger `ON DELETE CASCADE`. It also fires `DELETE` triggers and generates undo/redo for row changes.

For large partitions, you can archive first and then use partition maintenance DDL once relationships are resolved. If cascade or trigger semantics are required, `DELETE` may be the right choice even if slower.

### 12.4. Do not disable constraints recklessly

Some partition maintenance procedures may require disabling/re-enabling constraints. Before doing so:

- Check whether any child rows still reference data about to be deleted.
- Ensure constraints are re-enabled and re-validated.
- Do not reopen workloads before constraints are restored.
- Record constraint states before and after.

If referencing data still exists, disabling constraints and dropping a partition can leave orphaned rows. Resolve child data before marking complete.

## 13. Batch DELETE When Tables Are Not Partitioned

Not every table uses partitioning. For nonpartitioned tables or partial deletions, batched `DELETE` can be used.

### 13.1. Why avoid deleting millions of rows in one statement?

A massive `DELETE` can:

- Generate huge undo and redo volumes.
- Hold row locks for long durations.
- Pressure the undo tablespace.
- Cause very long transaction rollbacks on failure.
- Load indexes, foreign keys, and triggers heavily.
- Impact replication, standby, and backup windows.

Batch deletion splits the work into smaller transactions. In return, each batch commits independently, so the workflow must be safely restartable.

### 13.2. PL/SQL example deleting by ROWID batches

~~~sql
DECLARE
    l_deleted PLS_INTEGER;
BEGIN
    LOOP
        DELETE FROM sales_nonpartitioned
        WHERE ROWID IN (
            SELECT rid
            FROM (
                SELECT ROWID AS rid
                FROM sales_nonpartitioned
                WHERE sale_date < DATE '2020-01-01'
                ORDER BY sale_date
            )
            WHERE ROWNUM <= 10000
        );

        l_deleted := SQL%ROWCOUNT;
        COMMIT;

        EXIT WHEN l_deleted = 0;
    END LOOP;
END;
/
~~~

This example uses 10,000 rows per batch; size batches according to workload and undo capacity. Conditions must be stable and appropriately indexed if needed. If rows are inserted into the cutoff region while the job runs, the workflow must define whether to process those new rows.

### 13.3. Batch deletes must be restartable

Because each batch commits separately:

- The job can stop after several batches.
- Reruns must resume without failing or accidentally deleting newer data.
- Log the cutoff, batch start/end, deleted row counts, and status.
- Key ranges or partition/key boundaries can be used for checkpointing.

Never mark a job successful simply because the final loop raised no error; reconcile remaining row counts and deleted counts.

### 13.4. ROWID-based DELETE is not the answer for every table

If the predicate has a strong index and few rows need deletion, a direct `DELETE` may suffice:

~~~sql
DELETE FROM sales_nonpartitioned
WHERE sale_date < :cutoff_date;
~~~

If most of the table's data must be deleted, archiving or CTAS/partition exchange/redefinition may fit better. The decision depends on triggers, FKs, indexes, downtime, rollback needs, and space.

## 14. Comparing Old-Data Deletion Strategies

| Strategy | Best suited for | Cost/Risk |
| --- | --- | --- |
| Predicate DELETE | Deleting a small subset, needing trigger/FK semantics | Undo/redo, row locks, index maintenance |
| Batched DELETE | Nonpartitioned tables, large volume needing chunked transactions | Multiple commits, must support checkpoint/restart |
| TRUNCATE PARTITION | Deleting all rows in a partition while keeping structure | Non-rollback DDL; check FKs and indexes |
| DROP PARTITION | Permanently removing an expired partition | Non-rollback DDL; bypasses recycle bin |
| EXCHANGE PARTITION | Archiving or moving partition data to a standalone table | Requires compatible structure, validation, and index handling |
| MOVE PARTITION | Moving a partition to another tablespace/storage | I/O, index maintenance, locks, and space |
| Data Pump/export | Creating a standalone archive copy | Requires managing dumps, metadata, checksums, and restore |
| Materialized/summary data | Retaining aggregated metrics after purging details | Must clarify query and audit requirements |

No single deletion method fits every table. Choose based on data size, retention, foreign key relationships, trigger needs, maintenance windows, and recovery.

## 15. Moving Partitions to Lower-Cost Storage and Compressing Data

Older partitions may still need querying while being accessed infrequently. In that case, moving partitions to another tablespace or applying compression can lower costs.

### 15.1. MOVE PARTITION

~~~sql
ALTER TABLE sales_lifecycle
MOVE PARTITION p2025_01
TABLESPACE archive_ts
UPDATE INDEXES;
~~~

This moves the partition to the archive tablespace. `UPDATE INDEXES` instructs Oracle to maintain indexes as supported by the operation. Without index maintenance, some indexes or index partitions may need rebuilding.

### 15.2. ONLINE MOVE

~~~sql
ALTER TABLE sales_lifecycle
MOVE PARTITION p2025_01
TABLESPACE archive_ts
ONLINE
UPDATE INDEXES;
~~~

`ONLINE MOVE` allows concurrent DML under Oracle's supported conditions. It does not mean zero locking or zero extra resource consumption. Check version limits, table types, LOBs, indexes, and edition before using.

### 15.3. Compression

Oracle supports multiple table compression modes. Example syntax usable when storage/edition/licensing support it:

~~~sql
ALTER TABLE sales_lifecycle
MOVE PARTITION p2025_01
TABLESPACE archive_ts
COMPRESS FOR QUERY LOW
UPDATE INDEXES;
~~~

Hybrid Columnar Compression depends on supported storage platforms. Compression levels and feature entitlement must be verified against Oracle Licensing Information and deployment contracts. Never copy compression syntax from Exadata or storage appliances to unsupported environments.

### 15.4. MOVE is not archiving

`MOVE` only changes a partition's storage location within the database. The data remains in the logical table. If independent archival or removal from the transactional system is required, exchange/export/archive and then purge per policy.

## 16. Heat Map and Automatic Data Optimization (ADO)

Oracle provides Heat Map and Automatic Data Optimization to support ILM.

### 16.1. Heat Map

Heat Map tracks data access and modification activity. ADO can use that information to evaluate policies for compressing or moving data.

To use ADO, Heat Map must be enabled at the system level per DBA configuration and privileges:

~~~sql
ALTER SYSTEM SET HEAT_MAP = ON SCOPE = BOTH;
~~~

Enabling parameters and execution privileges must be managed by the DBA. Check the setting:

~~~sql
SHOW PARAMETER heat_map;
~~~

### 16.2. ADO policy

Example policy to compress a segment after six months of no access:

~~~sql
ALTER TABLE sales_lifecycle ILM ADD POLICY
    COLUMN STORE COMPRESS FOR ARCHIVE HIGH
    SEGMENT
    AFTER 6 MONTHS OF NO ACCESS;
~~~

This illustrates Oracle ADO syntax. Compression level and storage must be supported. HCC depends on the storage platform; verify licensing.

### 16.3. ADO is not automatically a purge policy

Compression/tiering policies adjust how or where data is stored when conditions are met. They do not replace retention policies and do not mean Oracle automatically deletes all expired rows.

Purging still requires a controlled workflow:

- Compute cutoff.
- Check legal holds.
- Archive or confirm archiving is unnecessary.
- Check foreign keys/indexes.
- Execute partition DDL or batched `DELETE`.
- Reconcile and log audit records.

### 16.4. Monitoring policies

Oracle provides data dictionary views and the `DBMS_ILM` package to manage, evaluate, or execute ADO tasks. DBAs should inspect policy status, execution results, and required privileges before automating.

Do not create an ADO policy and assume it ran. Monitor execution schedules, errors, capacity, and compression/movement outcomes.

## 17. Managing Metadata and Tracking Partitions

### 17.1. USER_TAB_PARTITIONS

~~~sql
SELECT table_name,
       partition_name,
       partition_position,
       tablespace_name,
       num_rows,
       last_analyzed
FROM user_tab_partitions
WHERE table_name = 'SALES_LIFECYCLE'
ORDER BY partition_position;
~~~

This view lists partitions of the current table. `HIGH_VALUE` is also in metadata, though its `LONG` data type prevents some SQL tools from processing it like a normal `VARCHAR2` column.

### 17.2. USER_PART_TABLES and USER_PART_KEY_COLUMNS

~~~sql
SELECT table_name,
       partitioning_type,
       subpartitioning_type,
       partition_count,
       interval
FROM user_part_tables
WHERE table_name = 'SALES_LIFECYCLE';
~~~

~~~sql
SELECT name,
       object_type,
       column_name,
       column_position
FROM user_part_key_columns
WHERE name = 'SALES_LIFECYCLE'
ORDER BY column_position;
~~~

These views help verify the partitioning method and partition key.

### 17.3. Segment size by partition

~~~sql
SELECT segment_name,
       partition_name,
       segment_type,
       tablespace_name,
       bytes,
       blocks
FROM user_segments
WHERE segment_name = 'SALES_LIFECYCLE'
ORDER BY partition_name;
~~~

Segment metrics help track which partitions consume the most storage. Do not infer exact row counts purely from segment size because compression, row length, block fullness, and indexes all affect it.

### 17.4. Index partitions

~~~sql
SELECT index_name,
       partition_name,
       status,
       tablespace_name
FROM user_ind_partitions
WHERE index_name LIKE 'IX_SALES%'
ORDER BY index_name, partition_position;
~~~

After partition maintenance, check index partition status to detect `UNUSABLE` states.

## 18. Automating Retention with Controlled Schedules

A retention job may run monthly, yet it should never blindly take the current date and immediately `DROP` partitions.

The workflow should include these steps:

1. Compute cutoff using the agreed time zone/calendar.
2. List partitions whose upper bound is below the cutoff.
3. Check legal holds and exceptions.
4. Confirm archive/export completion and reconciliation.
5. Check foreign keys and dependent partitions.
6. Check local/global index maintenance.
7. Generate the DDL plan for each specific partition.
8. Run inside an approved maintenance window or concurrency mechanism.
9. Verify partition status, index status, and remaining metrics.
10. Log audit results.

### 18.1. Do not construct partition names solely from date strings

Partition names can be user-defined or Oracle-generated. With interval partitioning, names can look like `SYS_P...`; therefore, jobs must query dictionary metadata rather than assuming `P_YYYY_MM` names.

### 18.2. Execute DDL one partition at a time

For critical purges, control is easier when each partition is processed as a distinct step:

- Log the target partition.
- Verify the archive.
- Execute DDL.
- Confirm the partition is gone or empty as intended.
- Check indexes.
- Mark complete.

If one partition fails, the job can halt and resume from the unprocessed partition rather than dropping many periods in one hard-to-reconcile step.

### 18.3. Do not run two jobs concurrently on the same partition

Archive, move, exchange, and purge jobs must not contend on the same partition. Use scheduler locks, control tables, or orchestration mechanisms to guarantee only one workflow manages a partition at any time.

## 19. Impact on Backups, Standby, and Downstream Systems

Before deleting old data, identify all other copies of the data:

- RMAN backups and recovery windows.
- Data Guard standby and redo apply.
- GoldenGate or CDC.
- Materialized views and refresh logs.
- Data warehouses, lakes, or reporting systems.
- Export files and archive storage.

A partition dropped from primary may still exist in backups or downstream systems. If retention requires erasing personal or sensitive data, review replicas and backup expiration policies as well; deleting from the main table may not remove data across the entire ecosystem.

Conversely, if archiving is legally required, ensure the archive copy exists and is restorable before deleting the online copy.

## 20. Common Errors and Scenarios

| Error/Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| ORA-14400 | Partition key value does not map to any existing partition | Create future partition, check range bounds or interval |
| ORA-14402 | Updating partition key moves row between partitions while row movement is disabled | Avoid updating partition key or use controlled `ENABLE ROW MOVEMENT` |
| ORA-02266 | Parent key referenced by enabled foreign key | Handle child rows/constraints in order and revalidate |
| ORA-01502 | Index/index partition unusable after partition maintenance | Check index status, use `UPDATE INDEXES` or rebuild |
| ORA-14083 | Attempting to DROP the table's final remaining partition | Cannot drop the sole partition; handle at table level |
| Partition drop succeeds but missing from recycle bin | `DROP PARTITION` bypasses the recycle bin | Archive/back up before dropping; prepare restore plan |
| EXCHANGE PARTITION fails | Incompatible staging table or rows outside partition range | Check structure, indexes, constraints, and use `WITH VALIDATION` |
| Global index becomes unusable | Global index not maintained in partition DDL | Use `UPDATE INDEXES`/`UPDATE GLOBAL INDEXES` per supported syntax or rebuild |
| Archive missing rows | Exchange/export unreconciled or validation improperly skipped | Reconcile counts, key ranges, checksums, and metadata |
| Slow purge | `DELETE` hits too many rows, heavy indexes/FKs/triggers and undo/redo | Use partition maintenance if business rules allow |
| Retention job deletes wrong data | Wrong cutoff, time zone, legal hold, or partition name | Dry-run, approvals, audit, verify `HIGH_VALUE` and archives |
| ADO policy does not run | Heat Map disabled, policy criteria unmet, or job error | Check `HEAT_MAP`, policy metadata, and `DBMS_ILM` status |
| Archive table cannot be queried as expected | Schema version or indexes/constraints differ from source table | Save schema metadata, test restores and queries |

## 21. Self-Contained Practice Lab

Lab exercises use dedicated tables and never touch application data.

### 21.1. Create a monthly partitioned table

~~~sql
CREATE TABLE sales_lifecycle_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
(
    PARTITION p2025_01 VALUES LESS THAN (DATE '2025-02-01'),
    PARTITION p2025_02 VALUES LESS THAN (DATE '2025-03-01'),
    PARTITION p2025_03 VALUES LESS THAN (DATE '2025-04-01')
);

CREATE INDEX ix_sales_lifecycle_lab_customer
ON sales_lifecycle_lab(customer_id, sale_date)
LOCAL;
~~~

### 21.2. Load sample data

~~~sql
INSERT INTO sales_lifecycle_lab VALUES
(1, DATE '2025-01-10', 101, 100);

INSERT INTO sales_lifecycle_lab VALUES
(2, DATE '2025-02-15', 102, 200);

INSERT INTO sales_lifecycle_lab VALUES
(3, DATE '2025-03-20', 103, 300);

COMMIT;
~~~

### 21.3. Verify partition pruning

~~~sql
EXPLAIN PLAN FOR
SELECT SUM(amount)
FROM sales_lifecycle_lab
WHERE sale_date >= DATE '2025-02-01'
  AND sale_date < DATE '2025-03-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Observe partition access in the execution plan. Displayed details depend on statistics and environment.

### 21.4. Archive via EXCHANGE PARTITION

Create a structurally compatible staging table:

~~~sql
CREATE TABLE sales_archive_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
);

CREATE INDEX ix_sales_archive_lab_customer
ON sales_archive_lab(customer_id, sale_date);
~~~

Exchange the January partition:

~~~sql
ALTER TABLE sales_lifecycle_lab
EXCHANGE PARTITION p2025_01
WITH TABLE sales_archive_lab
INCLUDING INDEXES
WITH VALIDATION;
~~~

Reconcile:

~~~sql
SELECT COUNT(*) FROM sales_archive_lab;
SELECT COUNT(*) FROM sales_lifecycle_lab PARTITION (p2025_01);
~~~

The archive table receives January data; the January partition in the source table becomes empty if staging was initially empty.

### 21.5. Check indexes and drop the empty partition

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE table_name = 'SALES_LIFECYCLE_LAB';

ALTER TABLE sales_lifecycle_lab
DROP PARTITION p2025_01
UPDATE INDEXES;
~~~

Inspect partition metadata:

~~~sql
SELECT partition_name, partition_position, num_rows
FROM user_tab_partitions
WHERE table_name = 'SALES_LIFECYCLE_LAB'
ORDER BY partition_position;
~~~

### 21.6. Try TRUNCATE PARTITION

~~~sql
ALTER TABLE sales_lifecycle_lab
TRUNCATE PARTITION p2025_02
UPDATE INDEXES;
~~~

The February partition still exists with zero rows. This is the difference from `DROP PARTITION`.

### 21.7. Try interval partitioning

~~~sql
CREATE TABLE sales_interval_lab (
    sale_id NUMBER,
    sale_date DATE NOT NULL,
    amount NUMBER(12,2)
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))
(
    PARTITION p_before_2025
    VALUES LESS THAN (DATE '2025-01-01')
);

INSERT INTO sales_interval_lab
VALUES (1, DATE '2025-04-10', 500);

COMMIT;
~~~

Check partitions created by Oracle:

~~~sql
SELECT partition_name, partition_position, tablespace_name
FROM user_tab_partitions
WHERE table_name = 'SALES_INTERVAL_LAB'
ORDER BY partition_position;
~~~

### 21.8. Clean up lab

~~~sql
DROP TABLE sales_archive_lab PURGE;
DROP TABLE sales_lifecycle_lab PURGE;
DROP TABLE sales_interval_lab PURGE;
~~~

DDL has an implicit commit. Run only after completing the lab exercises.

## 22. Pre-Archive and Pre-Purge Checklist

1. **Is retention approved?** Confirm cutoff, time zone, date column, and retention duration.
2. **Are there legal holds or exceptions?** Exclude held records from the purge list.
3. **Is the exact partition confirmed?** Verify partition name, high value, partition position, and row count.
4. **Has data been archived?** Reconcile row counts, key ranges, checksums, and storage location.
5. **Can the archive be restored?** Check metadata, schema version, privileges, and restore procedures.
6. **Are foreign keys or reference partitioning involved?** Process child data and constraints in the proper order.
7. **What happens to local/global indexes?** Choose `UPDATE INDEXES` or a rebuild plan.
8. **Are downstream systems impacted?** Check backups, standby, CDC, materialized views, and reports.
9. **Does DDL have an implicit commit?** Prepare transaction boundaries and approvals.
10. **Should DROP or TRUNCATE be used?** Drop removes partition metadata; truncate leaves an empty partition.
11. **Is EXCHANGE PARTITION needed?** Prepare a compatible staging table and matching indexes.
12. **Is WITHOUT VALIDATION used?** Only when row mapping has already been guaranteed by another process.
13. **Are storage and I/O sufficient?** Account for archiving, moves, compression, global index maintenance, and redo.
14. **Were partitions/indexes checked afterward?** Confirm usable status and remaining data.
15. **Was an audit record logged?** Record operator, timestamp, cutoff, partition, row count, and outcome.

## 23. Self-Check Questions

**Question 1.** Across which stages does ILM manage data?

**Question 2.** Why must retention be defined before writing a `DROP PARTITION` statement?

**Question 3.** How does partitioning make purging old data faster than row-by-row `DELETE`?

**Question 4.** In a RANGE partition, does `VALUES LESS THAN` include the upper bound?

**Question 5.** Why should half-open date ranges be used in `WHERE`?

**Question 6.** What does interval partitioning automatically do when a row exceeds the transition point?

**Question 7.** How do `DROP PARTITION` and `TRUNCATE PARTITION` differ?

**Question 8.** Does a dropped partition go into the recycle bin?

**Question 9.** Why can `DROP PARTITION` not be rolled back with `ROLLBACK`?

**Question 10.** Does `EXCHANGE PARTITION` copy rows one by one?

**Question 11.** How do `WITH VALIDATION` and `WITHOUT VALIDATION` differ?

**Question 12.** Why must global indexes be checked after partition maintenance?

**Question 13.** Does `ON DELETE CASCADE` run automatically during `DROP PARTITION`?

**Question 14.** When should batched `DELETE` be used instead of partition DDL?

**Question 15.** Do Heat Map and ADO automatically delete all data past retention?

<details>
<summary>Suggested Answers</summary>

1. HOT, WARM, ARCHIVE, and PURGE are illustrative stages; actual policies depend on business requirements.
2. Because purging is destructive; you need to know which data is expired, whether legal holds apply, and whether it has been archived.
3. Partition DDL operates on segment/metadata for an entire group of rows rather than processing each row and index entry individually.
4. No. `LESS THAN` uses an exclusive upper bound.
5. To cover the entire duration of a day/month without missing values that carry time components.
6. Creates a suitable interval partition to hold the row.
7. `DROP` removes both partition metadata and data; `TRUNCATE` deletes rows while keeping the partition.
8. No. Dropped partitions are not placed in the recycle bin.
9. Because `DROP PARTITION` is DDL and performs an implicit commit.
10. Not as a row-by-row copy; `EXCHANGE` swaps segments/metadata when structures meet requirements.
11. `WITH VALIDATION` verifies rows belong within the partition range; `WITHOUT VALIDATION` skips the check.
12. Because global indexes can become invalid/unusable if not maintained during the operation.
13. No. `ON DELETE CASCADE` applies to `DELETE` DML, not row-by-row cascading on partition drops.
14. When the table is nonpartitioned, only a subset of rows is deleted, or trigger/FK semantics are required.
15. No. ADO primarily automates compression/tiering; purging requires a separate retention workflow.

</details>

## 24. Official Oracle Documentation

1. [Oracle Database 19c VLDB and Partitioning Guide — Introduction to Partitioning](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-intro.html): partitioning, partition pruning, ILM, and Oracle Partitioning option requirements.
2. [Oracle Database 19c VLDB and Partitioning Guide — Partition Administration](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-admin.html): creating, managing, and maintaining partitions.
3. [Oracle Database 19c VLDB and Partitioning Guide — Maintenance Operations for Partitioned Tables and Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/maintenance-partition-tables-indexes.html): DROP, TRUNCATE, EXCHANGE, UPDATE INDEXES, global index maintenance, and referential integrity.
4. [Oracle Database 19c VLDB and Partitioning Guide — Using Partitioning in a Data Warehouse Environment](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-warehouse.html): partition exchange loads and purging old data in data warehouses.
5. [Oracle Database 19c VLDB and Partitioning Guide — Using Partitioning in an OLTP Environment](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-oltp.html): impact of partition maintenance on DML and availability.
6. [Oracle Database 19c SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): RANGE, INTERVAL, and table partitioning clauses.
7. [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): DROP/TRUNCATE/EXCHANGE/MOVE partition and index options.
8. [Oracle Database 19c Administrator's Guide — Managing Tables](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tables.html): compression, Heat Map, and Automatic Data Optimization.
9. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_ILM](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ILM.html): managing and executing ADO policies.
10. [Oracle Database 19c Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html): licensing conditions for related options and features.

**Key takeaway:** Establish retention policies before deleting data. Time-based partitioning enables archiving, moving, compressing, and purging in large groups; `DROP PARTITION` removes the partition completely, `TRUNCATE PARTITION` leaves an empty partition, and `EXCHANGE PARTITION` swaps a data segment into a standalone table for archiving. Always verify legal holds, foreign keys, local/global indexes, backups, and downstream systems prior to DDL. When a full partition cannot be removed or trigger/FK semantics are required, use controlled `DELETE`, optionally chunked into batches with checkpoints. Heat Map/ADO assist with compression and storage tiering, but do not replace an approved purge workflow.
