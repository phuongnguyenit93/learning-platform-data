# ADD, DROP, TRUNCATE, SPLIT, MERGE, and MOVE PARTITION

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Partitioning  
> **Objective:** Understand and use partition maintenance operations in Oracle Database: ADD, DROP, TRUNCATE, SPLIT, MERGE, and MOVE PARTITION. Understand applicability conditions by partitioning type, impacts on data and local/global indexes, ways to reduce maintenance duration, post-DDL status checks, and safe deployment planning.

## 1. What Is Partition Maintenance?

Partitioning divides a large table into multiple logical parts called partitions. Applications still query the table by its common name, while Oracle can read only the relevant partitions thanks to partition pruning. Each partition typically has its own segment and storage attributes.

Example of a transaction table partitioned by month:

~~~sql
CREATE TABLE sales (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p_2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p_2026_03 VALUES LESS THAN (DATE '2026-04-01')
);
~~~

Instead of a single segment for all data, the table has partitions by date range. When old data must be processed, a new month prepared, or data moved to another tablespace, the DBA can operate on a single partition.

Operations covered in this lesson:

| Operation | Primary effect | Data in partition |
|---|---|---|
| ADD PARTITION | Adds a new partition | New partition is initially empty |
| DROP PARTITION | Removes a partition from the table | Partition data is removed |
| TRUNCATE PARTITION | Deletes all rows in a partition | Partition remains intact but empty |
| SPLIT PARTITION | Divides one partition into two or more parts per supported syntax | Rows are redistributed into new partitions |
| MERGE PARTITIONS | Combines compatible partitions into one partition | Rows are retained in the resulting partition |
| MOVE PARTITION | Moves partition segment or changes storage attributes | Rows are retained; segment is rebuilt/relocated |

These are structural maintenance DDL statements. Do not confuse `MERGE PARTITIONS` with the DML `MERGE` statement used to combine INSERT and UPDATE.

## 2. Identify the Partitioning Type Before Operating

Supported syntax and operations depend on how the table is partitioned.

### 2.1. Range partitioning

Range partitioning divides data into ordered value ranges. Each partition declares an upper bound via `VALUES LESS THAN`.

~~~sql
CREATE TABLE sales_range (
    sale_id NUMBER,
    sale_date DATE,
    amount NUMBER(12,2)
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p_2026_h1 VALUES LESS THAN (DATE '2026-07-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

A range partition holds values from its lower bound (the exclusive upper bound of the preceding partition) up to its exclusive upper bound. A value equal to the upper bound belongs to the next partition.

If a `MAXVALUE` partition already exists, you cannot add a range partition with a higher finite bound. Typically you must `SPLIT` the `MAXVALUE` partition to carve out a new range while retaining the future slice.

### 2.2. List partitioning

List partitioning divides data by discrete values:

~~~sql
CREATE TABLE customers_by_region (
    customer_id NUMBER,
    region_code VARCHAR2(20 CHAR),
    customer_name VARCHAR2(100)
)
PARTITION BY LIST (region_code) (
    PARTITION p_north VALUES ('NORTH'),
    PARTITION p_south VALUES ('SOUTH'),
    PARTITION p_other VALUES (DEFAULT)
);
~~~

When adding a new region, check which partition already owns that value, especially if a `DEFAULT` partition exists. Moving values already stored in `DEFAULT` to a dedicated partition typically requires splitting/moving according to Oracle release syntax.

### 2.3. Hash partitioning

Hash partitioning distributes rows using a hash of the partition key:

~~~sql
CREATE TABLE customer_events (
    event_id NUMBER,
    customer_id NUMBER NOT NULL,
    event_time DATE,
    payload VARCHAR2(200)
)
PARTITION BY HASH (customer_id)
PARTITIONS 4;
~~~

Hash partitioning is typically used to distribute data and I/O evenly rather than creating time/business boundaries like range/list. Hash partitions can be added or dropped per Oracle-supported syntax; Oracle may have to redistribute rows across partitions. Evaluate execution time and resource cost instead of assuming it is metadata-only.

### 2.4. Composite partitioning

Tables can be partitioned across two levels, such as RANGE-HASH:

~~~sql
CREATE TABLE sales_composite (
    sale_id NUMBER,
    sale_date DATE,
    customer_id NUMBER,
    amount NUMBER(12,2)
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 4 (
    PARTITION p_2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p_2026_02 VALUES LESS THAN (DATE '2026-03-01')
);
~~~

Operations at the partition level can affect multiple subpartitions. Inspect both local index partitions and subpartitions, as well as DDL limits for the specific composite partitioning type.

### 2.5. Inspecting partitioning metadata

In the table owner's schema:

~~~sql
SELECT table_name,
       partitioning_type,
       subpartitioning_type,
       partition_count,
       def_tablespace_name
FROM user_part_tables
WHERE table_name = 'SALES';
~~~

List partitions:

~~~sql
SELECT table_name,
       partition_name,
       partition_position,
       tablespace_name,
       num_rows,
       last_analyzed
FROM user_tab_partitions
WHERE table_name = 'SALES'
ORDER BY partition_position;
~~~

For other schemas, use `DBA_PART_TABLES` and `DBA_TAB_PARTITIONS` if privileges allow. `NUM_ROWS` and `LAST_ANALYZED` come from statistics, not exact real-time row counts.

## 3. Preparation Before Running Partition DDL

Partition maintenance can delete data or alter segments/indexes. Before executing:

1. Confirm the exact owner, table, and partition name.
2. Confirm partition key, partitioning type, and boundaries.
3. Check row count, data dates, and retention rules.
4. Check local/global indexes and the status of each index partition.
5. Identify constraints, foreign keys, triggers, materialized views, and dependent applications.
6. Review active transactions and the maintenance window.
7. Confirm appropriate backups, recovery, and retention if the operation removes data.
8. Test the DDL in an environment matching the production Oracle version.
9. Record pre-operation metadata and row counts for reconciliation.
10. Prepare handling for `UNUSABLE` indexes or failed operations.

Standard partition DDL statements perform an implicit commit before and after the statement. You cannot use `ROLLBACK` to undo DROP, TRUNCATE, SPLIT, MERGE, or MOVE PARTITION like uncommitted DML. Treat these as administrative operations with real consequences.

## 4. ADD PARTITION — Adding a Partition

`ADD PARTITION` creates a new partition. The new partition is normally empty; adding a partition does not automatically move existing data into it, except in mechanisms that redistribute data such as certain hash operations.

### 4.1. Adding a range partition

Suppose table `SALES_RANGE` has a final partition `P_2026_H1` with bound less than `DATE '2026-07-01'` and no higher-bound partition.

~~~sql
ALTER TABLE sales_range
ADD PARTITION p_2026_h2
VALUES LESS THAN (DATE '2027-01-01')
TABLESPACE sales_data;
~~~

The new partition accepts values from the previous partition's upper bound up to before 2027-01-01.

If the last partition already has bound `MAXVALUE`, an `ADD PARTITION` with a higher finite bound is invalid because no partition can be placed after `MAXVALUE`. Use `SPLIT PARTITION` on the `MAXVALUE` partition to create the desired boundary.

### 4.2. Adding a list partition

~~~sql
ALTER TABLE customers_by_region
ADD PARTITION p_east
VALUES ('EAST')
TABLESPACE customer_data;
~~~

The value `'EAST'` must not already be assigned to another partition. If a `DEFAULT` partition exists, check the syntax and procedure for moving values out of `DEFAULT` for your Oracle release; do not assume `ADD` alone automatically migrates existing rows.

### 4.3. Adding a hash partition

On a hash-partitioned table, a partition can be added using appropriate syntax:

~~~sql
ALTER TABLE customer_events
ADD PARTITION p_hash_5
TABLESPACE event_data;
~~~

Oracle distributes rows according to hash partitioning. Adding a partition can require redistributing existing data and cause significant I/O. Review release documentation, expected execution time, and online/availability capabilities.

### 4.4. Interval partitioning

On an interval-partitioned table, Oracle can automatically create partitions when an INSERT introduces a value beyond the transition range. Thus, manual `ADD PARTITION` for each new month is not always necessary.

Example:

~~~sql
CREATE TABLE monthly_sales (
    sale_id NUMBER,
    sale_date DATE NOT NULL,
    amount NUMBER(12,2)
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH')) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01')
);
~~~

When new data exceeds the transition point, Oracle creates interval partitions according to the interval rule. You still need to monitor partition names, default tablespaces, indexes, and storage policies.

### 4.5. When to use ADD?

- Preparing future data ranges.
- Adding a new value group in list partitioning.
- Increasing hash partition count when redistribution is needed.
- Preparing a partition for the next batch load.

After `ADD`, verify partition metadata, tablespaces, and corresponding local index partitions. If the table has global indexes, confirm their status and usability.

## 5. DROP PARTITION — Removing a Partition and Its Data

`DROP PARTITION` removes the partition from the table. Data inside the partition is discarded along with the partition segment.

Example:

~~~sql
ALTER TABLE sales_range
DROP PARTITION p_2026_h1;
~~~

This operation fits data whose retention period has expired or an erroneously created partition with a verified handling plan.

### 5.1. DROP vs. DELETE

~~~sql
DELETE FROM sales_range
WHERE sale_date < DATE '2026-07-01';
~~~

`DELETE` is DML: Oracle locates each matching row, generates undo/redo, and maintains indexes, triggers, and constraints; it can be rolled back prior to commit.

~~~sql
ALTER TABLE sales_range
DROP PARTITION p_old_data;
~~~

`DROP PARTITION` is partition maintenance DDL: it removes the partition segment and related metadata; it does not generate row-by-row undo records the way standard `DELETE` does. DDL performs an implicit commit, so it cannot be undone with `ROLLBACK`.

For large data volumes, `DROP PARTITION` is generally much more efficient than `DELETE`ing all rows in a partition when partition boundaries match business requirements exactly. However, indexes, constraints, and dependencies must still be handled.

### 5.2. Cannot drop the last remaining partition in the usual way

Oracle does not allow dropping a partition if doing so would leave a partitioned table with no valid partitions. To remove all data, consider `TRUNCATE TABLE` or dropping the table according to purpose and privileges.

### 5.3. DROP with global indexes

Local indexes are partitioned in correspondence with table partitions. When a table partition is dropped, the matching local index partition is dropped as well.

Global indexes can be affected because their entries reference rows across many table partitions. Without proper global index maintenance, the global index or its partitions may be marked `UNUSABLE` depending on the operation and version.

Common index maintenance syntax example:

~~~sql
ALTER TABLE sales_range
DROP PARTITION p_old_data
UPDATE INDEXES;
~~~

Older releases or specific syntaxes may use `UPDATE GLOBAL INDEXES`. Check the SQL Language Reference for your exact version and verify index status after DDL. Do not assume identical syntax or behavior across every release.

### 5.4. Dropping a partition with data that must be retained

If a partition holds data that must still be preserved, you may need to export, back up, archive, or `EXCHANGE PARTITION` with a staging table before dropping. Never drop first and figure out recovery afterward.

A common strategy is moving an old partition to an archive tablespace or exchanging it out to a separate table, verifying the result, and then dropping per the retention policy. `EXCHANGE PARTITION` is a distinct operation requiring checks on constraints and index alignment.

## 6. TRUNCATE PARTITION — Deleting Rows While Keeping the Partition

`TRUNCATE PARTITION` removes all rows in a partition while retaining the partition definition so new data can be loaded into the same range.

~~~sql
ALTER TABLE sales_range
TRUNCATE PARTITION p_2026_h1;
~~~

Use it when emptying a partition to reload data, resetting a batch/period, or deleting all data within a partition's scope.

### 6.1. Differences between DROP and TRUNCATE

| Criterion | DROP PARTITION | TRUNCATE PARTITION |
|---|---|---|
| Partition definition | Removed | Retained |
| Data | Removed | Deleted |
| Segment | Partition segment removed | Segment emptied/reinitialized per Oracle management |
| Reusing the same partition | Requires ADD/SPLIT or restructuring | Can reload directly into existing partition |
| Best suited for | Permanently removing a data range | Clearing a range while preserving structure |

Both are DDL, perform an implicit commit, and cannot be rolled back like uncommitted `DELETE`.

### 6.2. TRUNCATE and indexes

The matching local index partition is truncated alongside the table partition. Global indexes must be maintained per release syntax/capability; otherwise, indexes can be impacted or require rebuilding.

Example:

~~~sql
ALTER TABLE sales_range
TRUNCATE PARTITION p_2026_h1
UPDATE INDEXES;
~~~

After the operation, inspect `USER_INDEXES` and `USER_IND_PARTITIONS` to confirm indexes remain usable. Some Oracle versions support asynchronous global index maintenance or optimizations for DROP/TRUNCATE; that does not remove the need to verify status and queryability.

### 6.3. TRUNCATE is not equivalent to DELETE

`TRUNCATE PARTITION` does not fire row-level `DELETE` triggers the way row-by-row `DELETE` does; verify trigger and constraint semantics in Oracle documentation. DDL also provides no row-by-row rollback.

If row-level deletion auditing is needed, capture data beforehand or use a separate archive/audit process. Do not substitute `TRUNCATE` for `DELETE` when business logic relies on per-row delete triggers.

### 6.4. Foreign keys and constraints

Partition maintenance may be restricted when a table is referenced by foreign keys or has related constraints/dependencies. Verify constraints, `ENABLED`/`VALIDATED` states, and corresponding DDL rules. Never disable foreign keys just to push DDL through without a plan to revalidate data.

## 7. SPLIT PARTITION — Dividing a Partition

`SPLIT PARTITION` divides an existing partition into smaller partitions along new boundaries. This is useful when a future partition is too broad, a range needs splitting, or a specific value region must be isolated.

For example, a table has partition `P_FUTURE` covering all dates up to `MAXVALUE`:

~~~sql
PARTITION p_future VALUES LESS THAN (MAXVALUE)
~~~

To split year 2027 out of the future region:

~~~sql
ALTER TABLE sales_range
SPLIT PARTITION p_future
AT (DATE '2028-01-01')
INTO (
    PARTITION p_2027,
    PARTITION p_future
);
~~~

The first resulting partition receives rows below the split boundary within the old range; the second receives the remainder. Verify names and high bounds to ensure no erroneous ranges are created.

### 7.1. Splitting a partition along a range boundary

Suppose `P_2026_H2` contains dates from 2026-07-01 up to before 2027-01-01. It can be split into two partitions:

~~~sql
ALTER TABLE sales_range
SPLIT PARTITION p_2026_h2
AT (DATE '2026-10-01')
INTO (
    PARTITION p_2026_q3,
    PARTITION p_2026_q4
);
~~~

Rows before 2026-10-01 go into `P_2026_Q3`; rows from 2026-10-01 up to before the old bound go into `P_2026_Q4`.

### 7.2. SPLIT is not merely metadata renaming

Oracle must distribute rows into the resulting partitions and maintain indexes. If the partition holds substantial data, the operation can consume I/O, CPU, temporary space, and redo. Duration depends on row count, storage, indexes, parallelism, and online options.

Do not treat `SPLIT` on a large partition as an instantaneous operation.

### 7.3. SPLIT and indexes

Matching local index partitions must also be split to remain synchronized with table partitions. Global indexes may require maintenance or rebuilding depending on DDL options.

For example, index maintenance can be specified in the same DDL:

~~~sql
ALTER TABLE sales_range
SPLIT PARTITION p_2026_h2
AT (DATE '2026-10-01')
INTO (
    PARTITION p_2026_q3,
    PARTITION p_2026_q4
)
UPDATE INDEXES;
~~~

Verify `UPDATE INDEXES` syntax and online capabilities for your Oracle release. After `SPLIT`, check table partition and index partition statuses; do not assume all indexes remain usable.

### 7.4. Splitting list partitions and hash partitions

Other partitioning methods have their own `SPLIT` syntax and capabilities. List partitions may require specifying the value set assigned to each resulting partition. Hash partitions are normally managed using `ADD`/`DROP` and hash distribution rather than splitting at a range boundary.

Do not apply `RANGE AT(...)` examples to `LIST`/`HASH`. Consult your partitioning type and release syntax before running.

## 8. MERGE PARTITIONS — Combining Partitions

`MERGE PARTITIONS` combines compatible partitions—usually adjacent range partitions—into a single partition. Use it when partition count grows excessive, data needs consolidation, or fine granularity on older periods is no longer required.

Example:

~~~sql
ALTER TABLE sales_range
MERGE PARTITIONS p_2026_q3, p_2026_q4
INTO PARTITION p_2026_h2;
~~~

The resulting partition takes the highest upper bound of the source partitions. Rows from both partitions are preserved in the resulting partition.

### 8.1. Conditions and meaning

- Source partitions must satisfy compatibility and ordering requirements of the partitioning method.
- For range partitioning, adjacent partitions are normally merged.
- The resulting partition name must not conflict with any existing name.
- The resulting partition's bound must accurately span the combined range of the source partitions.
- Check release restrictions for list, composite, and other partition types.

Do not merge partitions just because their names appear adjacent; verify boundaries and actual data.

### 8.2. MERGE partitions is not SQL MERGE

~~~sql
MERGE INTO target_table t
USING source_table s
ON (t.id = s.id)
WHEN MATCHED THEN UPDATE SET t.value = s.value
WHEN NOT MATCHED THEN INSERT (id, value) VALUES (s.id, s.value);
~~~

This is DML `MERGE` for synchronizing rows.

~~~sql
ALTER TABLE sales_range
MERGE PARTITIONS p_2026_q3, p_2026_q4
INTO PARTITION p_2026_h2;
~~~

This is DDL `MERGE PARTITIONS` for changing partitioning structure. The two statements have entirely different purposes and transaction semantics.

### 8.3. Indexes after MERGE

Local index partitions are merged along with table partitions. Global indexes must be maintained or can become unusable if the operation lacks appropriate maintenance clauses.

Example:

~~~sql
ALTER TABLE sales_range
MERGE PARTITIONS p_2026_q3, p_2026_q4
INTO PARTITION p_2026_h2
UPDATE INDEXES;
~~~

After DDL, check local/global index status, partition counts, and query plans.

## 9. MOVE PARTITION — Relocating a Partition Segment

`MOVE PARTITION` moves a partition's data into a new segment, typically to change tablespaces, storage attributes, or reorganize the segment.

Example of moving a partition to another tablespace:

~~~sql
ALTER TABLE sales_range
MOVE PARTITION p_2026_h1
TABLESPACE sales_archive;
~~~

The partition still belongs to `SALES_RANGE` and retains its data, while its segment moves to the target tablespace.

### 9.1. When to use MOVE?

- Moving older data to a lower-cost tablespace.
- Moving a partition out of a tablespace running low on space.
- Changing storage attributes or compression.
- Reorganizing a segment after heavy DML.
- Preparing for backup, tiered storage, or maintenance strategies.

`MOVE` differs from `DROP`/`TRUNCATE`: data is preserved. However, it is still DDL that may read/write large data volumes and consume substantial resources.

### 9.2. MOVE can affect ROWIDs and indexes

`MOVE` builds a new segment; physical `ROWID`s of rows can change. Local index partitions and global indexes referencing `ROWID`s must be handled per Oracle's index maintenance rules.

If appropriate index maintenance is not requested, indexes may be marked `UNUSABLE`. Example:

~~~sql
ALTER TABLE sales_range
MOVE PARTITION p_2026_h1
TABLESPACE sales_archive
UPDATE INDEXES;
~~~

Syntax and support for `UPDATE INDEXES`, `ONLINE`, or other options depend on Oracle release and index type. Check index status afterward.

### 9.3. Online move

Some releases/editions and partition types support `MOVE PARTITION ONLINE`:

~~~sql
ALTER TABLE sales_range
MOVE PARTITION p_2026_h1
TABLESPACE sales_archive
ONLINE
UPDATE INDEXES;
~~~

`ONLINE` allows certain DML operations to continue during the move, but it does not mean completely lock-free or without limitations. Brief lock phases, extra resource demands, datatype/index/partitioning restrictions, and version differences may still apply.

Before using it, check the SQL Language Reference, relevant licensing/edition rules, and test on an equivalent schema. Do not blindly add `ONLINE` to DDL if your release does not support it.

### 9.4. Compression and storage attributes

`MOVE` can combine storage attributes or Oracle-supported compression:

~~~sql
ALTER TABLE sales_range
MOVE PARTITION p_2026_h1
TABLESPACE sales_archive
COMPRESS FOR QUERY HIGH
UPDATE INDEXES;
~~~

Compression option names and applicability depend on edition, release, and table type. Compression can reduce storage and read I/O while increasing CPU during loads/queries or altering DML characteristics. Benchmark your workload before applying broadly.

## 10. Local Indexes and Global Indexes in Partition Maintenance

This must be checked after nearly every ADD, DROP, TRUNCATE, SPLIT, MERGE, and MOVE operation.

### 10.1. Local index

A local index is partitioned in alignment with table partitions. Each local index partition holds entries only for its corresponding table partition.

Advantages:

- Easier lifecycle management during `DROP`/`TRUNCATE PARTITION`.
- Partition maintenance can be performed locally.
- Fits data with a partition-based lifecycle.
- Partition pruning and index partition pruning can narrow read scope.

Example:

~~~sql
CREATE INDEX ix_sales_date_local
ON sales_range(sale_date)
LOCAL;
~~~

When adding a table partition, Oracle creates the corresponding index partition from the local index definition. During drop/truncate/split/merge/move, local index partitions are maintained according to the respective operation.

### 10.2. Global index

A global index can reference rows across multiple table partitions and does not necessarily share boundaries with table partitions.

Global nonpartitioned index example:

~~~sql
CREATE INDEX ix_sales_customer_global
ON sales_range(customer_id);
~~~

Global partitioned index:

~~~sql
CREATE INDEX ix_sales_customer_g
ON sales_range(customer_id)
GLOBAL PARTITION BY HASH(customer_id)
PARTITIONS 4;
~~~

Global indexes are useful when queries search on a key excluding the partition key or require a table-wide index. However, table partition maintenance can force global indexes to update entries across a broader scope.

### 10.3. Why can a global index become UNUSABLE?

When a table partition is dropped, truncated, split, merged, or moved, corresponding ROWIDs/entries in a global index may become invalid if Oracle does not perform maintenance. Oracle may mark the index or index partitions `UNUSABLE` to prevent queries from using stale structures.

You can request maintenance inside the DDL via `UPDATE INDEXES` if the operation/release supports it. Otherwise, you must rebuild the index or index partitions afterward.

### 10.4. Checking index status

Overall indexes:

~~~sql
SELECT index_name,
       index_type,
       uniqueness,
       status,
       partitioned
FROM user_indexes
WHERE table_name = 'SALES_RANGE'
ORDER BY index_name;
~~~

Index partitions:

~~~sql
SELECT index_name,
       partition_name,
       status,
       tablespace_name
FROM user_ind_partitions
WHERE index_name IN (
    SELECT index_name
    FROM user_indexes
    WHERE table_name = 'SALES_RANGE'
)
ORDER BY index_name, partition_position;
~~~

For subpartitioned indexes, inspect `USER_IND_SUBPARTITIONS`. For other schemas, use `DBA` views if granted privileges.

Pay attention to `USABLE`/`UNUSABLE` status. Seeing DDL complete is not sufficient; production queries can fail or lose index access if an index partition is unusable.

### 10.5. Rebuilding an index or index partition

If an index partition becomes unusable, rebuild it using appropriate syntax:

~~~sql
ALTER INDEX ix_sales_date_local
REBUILD PARTITION p_2026_h1;
~~~

For a global nonpartitioned index:

~~~sql
ALTER INDEX ix_sales_customer_global
REBUILD;
~~~

Rebuilding requires I/O, CPU, temporary space, and may generate redo depending on logging. Assess duration, online support, and DML impact before running.

## 11. Statistics After Partition Maintenance

Partition DDL can alter row counts, data distribution, and index structure. Old statistics may no longer represent the new partition.

Partition statistics can be viewed via:

~~~sql
SELECT table_name,
       partition_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name = 'SALES_RANGE'
ORDER BY partition_name;
~~~

Gather statistics for the table and partitions per policy:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_RANGE',
        granularity      => 'AUTO',
        cascade          => TRUE,
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE
    );
END;
/
~~~

`DBMS_STATS` offers incremental statistics and granularity options for partitioned tables. Choices depend on partition count, query workload, and DBA procedures.

Do not run overly broad statistics gathers after every DDL if an incremental/automatic policy is already configured. Confirm the optimizer has the required statistics for new or modified partitions.

## 12. Partition DDL and Availability

Partition maintenance can read/write many blocks, acquire metadata/table locks, and impact running transactions. The degree of blocking depends on the operation, release, `ONLINE` option, indexes, and workload.

Before deploying to production:

- Schedule a maintenance window if the operation is offline or may block.
- Check active sessions accessing the partition.
- Estimate tablespace, `TEMP`, and redo capacity.
- Ensure archive log destination has sufficient space if redo volume is large.
- Check standby/Data Guard if the database uses replication.
- Benchmark runtime on production-scale data.
- Monitor locks, I/O, redo generation, and competing jobs.
- Have an operational rollback plan: restore/reload/recreate, since committed DDL cannot use standard `ROLLBACK`.

Some operations provide an `ONLINE` option yet still carry restrictions. `ONLINE` is a property to verify per operation and release, not a guarantee of zero downtime.

## 13. Operation Comparison Table

| Operation | Keeps partition definition? | Keeps existing data? | Main impact |
|---|---|---|---|
| ADD | Adds definition | Yes, old data stays in old partitions (except hash redistribution depending on operation) | Expands range/partition count |
| DROP | No | No, partition is removed | Permanently removes segment and data |
| TRUNCATE | Yes | No, rows in partition are deleted | Empties partition for reuse |
| SPLIT | Replaces one partition with multiple | Yes, rows are redistributed | Creates finer-grained boundaries |
| MERGE PARTITIONS | Replaces multiple partitions with one | Yes, rows are consolidated | Reduces partition count |
| MOVE | Yes | Yes | Relocates/rebuilds segment; may change ROWIDs |

## 14. Monthly Partition Lifecycle Example

A monthly range-partitioning strategy may operate as follows:

~~~text
Before new period:
  P_2026_01 | P_2026_02 | P_2026_03 | P_FUTURE
       |
       +-- SPLIT P_FUTURE to prepare next month
       |
When retention expires:
  DROP old month's partition after archive/backup
       |
When needing to reload a month:
  TRUNCATE that month's partition
       |
When needing to change storage:
  MOVE partition to an appropriate tablespace
       |
When there are too many small partitions:
  MERGE adjacent range partitions if appropriate
~~~

Another design approach is pre-creating future partitions via `ADD` instead of keeping a `MAXVALUE` partition. The choice depends on data loading workflows, interval partitioning, retention, and deployment practices.

### 14.1. Example preparing future partitions with SPLIT

Suppose `P_FUTURE` has bound `MAXVALUE`:

~~~sql
ALTER TABLE sales_range
SPLIT PARTITION p_future
AT (DATE '2027-01-01')
INTO (
    PARTITION p_2026
        TABLESPACE sales_data,
    PARTITION p_future
        TABLESPACE sales_future
)
UPDATE INDEXES;
~~~

Then inspect boundaries, tablespaces, and index status. If the old partition held data belonging to 2026, Oracle distributes those rows into the corresponding resulting partition.

### 14.2. Example at retention expiration

After data has been archived and deletion is approved:

~~~sql
ALTER TABLE sales_range
DROP PARTITION p_2024_01
UPDATE INDEXES;
~~~

Reconcile remaining partition counts, index status, and row counts from statistics. Do not rely solely on `NUM_ROWS` if statistics are stale.

## 15. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| ADD range partition after MAXVALUE | Invalid DDL | `SPLIT` the `MAXVALUE` partition |
| DROP partition before archiving retained data | Data loss for that partition's scope | Back up/exchange/archive and confirm retention first |
| Confusing DROP with TRUNCATE | Loses partition definition when only wanting to empty it | Choose the right DDL |
| Using mass DELETE instead of DROP partition | Generates heavy undo/redo and row-by-row processing | Use partition maintenance if predicate matches full partition |
| Forgetting global indexes | Indexes may turn `UNUSABLE` or require rebuild | Use appropriate index maintenance and check status |
| Treating local indexes like global indexes | Misjudges maintenance scope | Identify index types beforehand |
| SPLIT/MERGE without checking boundaries | Data lands in unexpected partitions | Read `HIGH_VALUE` and test in lab |
| MOVE partition without handling indexes | Index partitions can become unusable | Use `UPDATE INDEXES` or rebuild |
| Using RANGE examples on LIST/HASH tables | Syntax errors or unsupported DDL | Verify partitioning type |
| Thinking DDL can ROLLBACK | Cannot recover via transaction rollback | Backup, staging, and recovery plan |
| Failing to update statistics | Optimizer misestimates after major changes | Run `DBMS_STATS` per policy |
| Assuming ONLINE means zero locks | Short locks/operation limits may still apply | Check release and test under workload |
| Forgetting subpartitions | Misses index/storage changes | Check composite partitioning metadata |

## 16. Pre- and Post-Partition Maintenance Checklist

### Before the operation

- [ ] Confirm exact schema, table, and partition.
- [ ] Confirm RANGE/LIST/HASH/INTERVAL/COMPOSITE.
- [ ] Check high bound, list values, or hash partition count.
- [ ] Verify data inside the partition and retention policy.
- [ ] Confirm whether DROP or TRUNCATE is required.
- [ ] Confirm SPLIT/MERGE boundaries and resulting partition names.
- [ ] Verify target tablespace if performing MOVE.
- [ ] Inventory local/global indexes and index partition statuses.
- [ ] Check constraints, FKs, triggers, MVs, and dependencies.
- [ ] Assess transactions, locks, redo, TEMP, and capacity.
- [ ] Verify syntax/`ONLINE`/`UPDATE INDEXES` on the target Oracle release.
- [ ] Have appropriate backups/archives and recovery plans ready.

### After the operation

- [ ] Inspect `USER_TAB_PARTITIONS` and boundary/order.
- [ ] Check partition/subpartition counts.
- [ ] Check tablespaces and segments.
- [ ] Inspect `USER_INDEXES`, `USER_IND_PARTITIONS`, and `USABLE` status.
- [ ] Rebuild index partitions if required.
- [ ] Gather/adjust statistics per policy.
- [ ] Run representative queries and inspect execution plans.
- [ ] Reconcile row/data counts with batch or archive records.
- [ ] Verify jobs, standby, and dependent applications.
- [ ] Log DDL audit: operator, timestamp, statement, outcome.

## 17. Key Takeaways

- `ADD` creates a new partition; with range partitioning, you cannot add a partition beyond an existing `MAXVALUE` partition without restructuring boundaries.
- `DROP PARTITION` removes both the partition definition and its data; `TRUNCATE PARTITION` only empties the partition for reuse.
- `SPLIT` divides one partition into parts along boundaries; `MERGE PARTITIONS` combines compatible partitions, typically adjacent range partitions.
- `MOVE PARTITION` preserves data while relocating/rebuilding the segment, commonly used to change tablespaces or storage attributes.
- Partition DDL performs an implicit commit; standard `ROLLBACK` cannot recover dropped/truncated data.
- Local indexes align with table partitions; global indexes span broader scope and require appropriate maintenance/rebuilding.
- `UPDATE INDEXES` and `ONLINE` support, syntax, and limits depend on the operation and Oracle release.
- After DDL, verify partition metadata, index status, statistics, and execution plans.
- Partition maintenance simplifies lifecycle management of large datasets, yet still requires evaluating locks, I/O, redo, TEMP, backups, and dependencies.
- Never apply RANGE syntax to LIST/HASH or composite partitioning; identify the exact partitioning type before deploying.

### Oracle Reference Documentation to Consult

- [Oracle Database VLDB and Partitioning Guide](https://docs.oracle.com/en/database/) — Partition maintenance operations, ADD/DROP/TRUNCATE/SPLIT/MERGE/MOVE.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — ALTER TABLE partition clauses and ALTER INDEX.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/) — Managing tablespaces, segments, indexes, and partitioned tables.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — USER_PART_TABLES, USER_TAB_PARTITIONS, USER_INDEXES, and USER_IND_PARTITIONS.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — DBMS_STATS and optimizer statistics.

Syntax, online capabilities, global index maintenance, and restrictions per partitioning method change across Oracle releases. Before running in production, consult documentation for your exact version, test DDL on an equivalent schema, and confirm index/partition statuses afterward.
