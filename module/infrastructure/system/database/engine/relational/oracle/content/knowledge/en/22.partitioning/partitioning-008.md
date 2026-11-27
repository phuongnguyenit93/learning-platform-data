# EXCHANGE PARTITION for Loading or Moving Data in Oracle

A monthly partitioned transaction table can receive millions of rows per period. Loading data via direct INSERT into a large table requires performing DML on target partitions, maintaining indexes, generating undo/redo, and coordinating with the running workload. In some ETL workflows, a more efficient approach is loading data into a standalone staging table, validating the data, and then using **EXCHANGE PARTITION** to swap the staging table's segment with a partition of the target table.

EXCHANGE PARTITION is a partition-level metadata operation: Oracle swaps the data/segment between a partition of a partitioned table and a compatible nonpartitioned table. It is neither a row-by-row copy command nor an INSERT SELECT. As a result, the operation can be very fast compared to moving massive numbers of rows with DML, but it requires structural compatibility between the two tables, staging data belonging strictly to the target partition, proper handling of indexes and constraints, and application awareness that it is DDL with an implicit commit.

This lesson belongs to the **Partitioning** group of Database Engine Relational Oracle. It focuses on two main usage patterns: exchange-in to move prepared data into a partition, and exchange-out to extract a partition into a standalone table for archiving, export, or external processing. It also explains validation, local/global indexes, UNUSABLE states, statistics, DDL locking, structural restrictions, and an operational ETL workflow.

After this lesson, you will be able to:

- Explain EXCHANGE PARTITION as a segment/metadata swap rather than a row-by-row copy.
- Design a staging table compatible with a partitioned table.
- Distinguish exchange-in and exchange-out, and understand where data resides after the swap.
- Use WITH VALIDATION and WITHOUT VALIDATION responsibly.
- Handle local indexes using INCLUDING INDEXES/EXCLUDING INDEXES.
- Maintain global indexes with appropriate options and verify their status afterward.
- Organize a workflow to load staging, validate data, exchange, gather statistics, and publish.
- Use exchange-out to extract historical data into an archive table.
- Identify the impact of DDL implicit commits, locks, and concurrency.
- Inspect partition/index metadata and execution plans after exchanging.
- Build a safe deployment checklist for ETL and partition lifecycles.

> **Example scope:** Illustrative statements follow Oracle Database 19c. Partitioning has separate edition/licensing requirements; run examples only on a database where partitioning entitlement has been verified. Index maintenance syntax and options may vary by release, table/index type, and partition type. Consult the SQL Language Reference / VLDB and Partitioning Guide for your exact version before using in production.

## 1. What Problem Does EXCHANGE PARTITION Solve?

Suppose table SALES is partitioned by month. Every month, the system receives a large file from a source system. The workflow can:

1. Load the file into a staging table.
2. Validate data types, mandatory values, duplicate keys, and date ranges.
3. Build required indexes/constraints on staging.
4. Swap staging with the corresponding monthly partition.
5. Verify the partition and indexes after exchanging.
6. Gather statistics and make the new data available to workloads.

~~~text
FILE / SOURCE SYSTEM
        |
        v
   STAGING TABLE
   - load rows
   - validate values
   - prepare indexes
        |
        | EXCHANGE PARTITION
        v
PARTITIONED TABLE
   SALES
   +-- P_2026_01
   +-- P_2026_02  <--- segment from staging
   +-- P_2026_03
        |
        v
   APPLICATION / REPORTS
~~~

If staging holds compatible data and the exchange succeeds, Oracle swaps the corresponding segments/metadata. Data in staging becomes the content of the target partition; old data from the partition moves into the staging table.

### 1.1. Exchange does not copy rows one by one

Key difference:

| Method | Approach | Typical cost |
| --- | --- | --- |
| INSERT INTO partitioned_table SELECT ... | Reads and inserts each row into target table | DML, undo/redo, index maintenance, and logging per load mode |
| DELETE/TRUNCATE then INSERT | Deletes old data then loads new data | DML/DDL and index maintenance |
| EXCHANGE PARTITION | Swaps partition segment with compatible table | Primarily a metadata/segment operation, plus chosen validation and index maintenance |

Exchange does not make the entire ETL pipeline free. Loading staging, building indexes, validation, updating global indexes, gathering statistics, and DDL locking still consume time and resources. The main benefit is that bringing the prepared segment into the partition avoids inserting row by row through the partitioned table.

### 1.2. Exchange is a two-way swap

The name "exchange" is crucial: it is a swap, not "copy staging into the partition while keeping staging intact."

Before exchange:

~~~text
Partition P_2026_01: [old rows]
Staging table:      [new rows]
~~~

After exchange:

~~~text
Partition P_2026_01: [new rows]
Staging table:      [old rows]
~~~

If the partition was initially empty, staging receives the partition's empty segment after exchange. If the partition held old data, staging receives that old data. You must plan for staging contents post-operation; never assume staging still holds the freshly loaded dataset.

## 2. Two Primary Usage Patterns

### 2.1. Exchange-in: loading data into a partition

Exchange-in is used when staging already contains data for one specific partition:

- The partitioned table has partition P2026_01.
- The nonpartitioned staging table has an identical compatible structure.
- Staging holds rows belonging to the January 2026 range.
- After validation and exchange, staging rows become the contents of P2026_01.

This is a standard pattern in data warehouses, fact tables, and periodic ETL.

### 2.2. Exchange-out: extracting a partition into a standalone table

Exchange-out is used when extracting one partition's data:

- Archiving an old partition.
- Exporting data by period.
- Reprocessing data outside the main table.
- Moving data to another tablespace or system via a separate workflow.

If the receiving exchange table was initially empty, after the operation it holds the partition's rows. The partition in the original table receives the empty segment of the receiving table. If you want to remove the partition from the table entirely, `DROP PARTITION` can follow exchange-out, depending on retention and procedures.

### 2.3. Exchange does not automatically create a backup

Because data is swapped, staging may hold the old data after exchange, yet this is not a complete backup strategy:

- Staging may be truncated/dropped during cleanup.
- Exchange DDL performs an implicit commit.
- Data/metadata/indexes must be protected by backup/recovery policies.
- Exchanging the wrong partition or wrong staging table can immediately impact reports.

Treat exchange as a controlled publish/relocation step, not a backup.

## 3. Compatibility Requirements Between Partition and Staging Table

EXCHANGE PARTITION requires the nonpartitioned exchange table to be structurally compatible with the partitioned table. This is where the most careful preparation is needed.

### 3.1. Column count, order, and data types

In principle, corresponding columns must match in:

- Number of columns.
- Column order.
- Data types and related data type attributes.
- Compatible length/precision/scale.
- Hidden, virtual, or special column characteristics if present.

Do not compare only column names. A table with identical column names in a different order or with different data types may fail to exchange or violate data requirements.

### 3.2. Use explicit DDL for staging

Example partitioned table:

~~~sql
CREATE TABLE sales_part_lab (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2026
        VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026_01
        VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02
        VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p_future
        VALUES LESS THAN (MAXVALUE)
);
~~~

Staging table with the exact same columns in the exact same order:

~~~sql
CREATE TABLE sales_stage_lab (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL
);
~~~

Staging is a nonpartitioned heap table. In real designs, also verify character sets, collations, virtual/invisible columns, LOBs, object types, identity columns, hidden columns, compression, and special attributes.

### 3.3. CTAS does not automatically copy all attributes

`CREATE TABLE AS SELECT` can quickly create an empty table:

~~~sql
CREATE TABLE sales_stage_lab AS
SELECT sale_id, sale_date, customer_id, amount
FROM sales_part_lab
WHERE 1 = 0;
~~~

CTAS is handy for copying data types/column expressions in some cases, but do not assume it copies everything:

- Primary key, unique, foreign key, and check constraints.
- Indexes.
- Defaults and certain column properties.
- Triggers.
- Partition-specific metadata or hidden-column semantics.
- Physical attributes required for exchange.

After CTAS, inspect and add whatever is missing. For standardized pipelines, explicit DDL or the release-supported exchange-table creation syntax can be safer and easier to review.

### 3.4. FOR EXCHANGE WITH TABLE

Some Oracle releases support syntax to create an exchange table based on a partitioned table's structure:

~~~sql
CREATE TABLE sales_stage_lab
FOR EXCHANGE WITH TABLE sales_part_lab;
~~~

`FOR EXCHANGE WITH TABLE` is designed to create a nonpartitioned table structurally ready for exchange, including certain details that regular CTAS omits. Check support and syntax in the SQL Language Reference for your running release. Do not assume older versions support this syntax.

### 3.5. Constraints must be reviewed separately

Exchanging can involve:

- NOT NULL.
- CHECK constraints.
- Primary key/unique constraints.
- Foreign keys.
- Constraint states ENABLE/DISABLE and VALIDATE/NOVALIDATE.
- Constraints depending on columns or data in other tables.

Do not inspect only table column DDL and overlook constraint states. Unique/primary keys can affect whether validation can be skipped or require corresponding indexes. Foreign keys and features like reference partitioning carry additional conditions.

Before exchanging, compare `USER_CONSTRAINTS`/`ALL_CONSTRAINTS` and check documentation for your release and specific structure. If staging has different constraints than the partitioned table, do not assume Oracle automatically carries all semantics across.

### 3.6. Indexes and special structures

If you want to exchange indexes alongside the partition, corresponding indexes must be compatible. Check:

- Column lists and column order.
- Data types/function-based expressions.
- Uniqueness.
- Local/global organization.
- Index partitioning and status.
- Compression, visibility, and related index properties.

LOBs, domain indexes, IOTs, nested tables, virtual/hidden columns, reference partitioning, and specialized structures can have specific restrictions. Verify each case instead of applying a simple heap-table pattern.

## 4. EXCHANGE PARTITION Syntax

General pattern:

~~~sql
ALTER TABLE partitioned_table
EXCHANGE PARTITION partition_name
WITH TABLE staging_table
[INCLUDING INDEXES | EXCLUDING INDEXES]
[WITH VALIDATION | WITHOUT VALIDATION]
[UPDATE GLOBAL INDEXES];
~~~

Option names and support may differ by release/table type; check the SQL Language Reference for your target version.

### 4.1. EXCHANGE PARTITION

Specify the partition in the partitioned table:

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab;
~~~

Oracle swaps the segment/data of `P2026_01` with `SALES_STAGE_LAB` if structural and constraint conditions match.

### 4.2. INCLUDING INDEXES

`INCLUDING INDEXES` requests swapping corresponding indexes along with the partition data. For local indexes, the staging table needs matching indexes with compatible structure to swap index segments with the local index partitions.

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
INCLUDING INDEXES
WITH VALIDATION;
~~~

Do not interpret `INCLUDING INDEXES` as "Oracle automatically builds any missing indexes." It does not replace designing matching indexes on staging. If indexes are incompatible or missing, the operation can fail.

### 4.3. EXCLUDING INDEXES

`EXCLUDING INDEXES` does not swap corresponding indexes. Depending on index type and operation, the affected local index partition may be marked `UNUSABLE` and require rebuilding/recovery. When using `EXCLUDING INDEXES`, include a post-exchange status check and index recovery plan.

Do not pick `EXCLUDING INDEXES` just to simplify DDL and then forget index maintenance. Queries and DML can be impacted when index partitions are unusable.

### 4.4. WITH VALIDATION

`WITH VALIDATION` directs Oracle to verify that rows in the exchange table satisfy the target partition's boundaries. For the January 2026 partition in our example, data must fall within:

~~~text
2026-01-01 <= sale_date < 2026-02-01
~~~

Validation may have to scan staging data and take longer. In return, it lets Oracle confirm the data belongs to the designated partition.

### 4.5. WITHOUT VALIDATION

`WITHOUT VALIDATION` skips checking whether staging rows satisfy the partition bound. Use it only when another process has already guaranteed range/list/hash compliance with auditable checks.

If staging contains a March row and is exchanged into the January partition without validation, the data can end up in the wrong partition relative to its partition key. When queries use partition pruning, Oracle may skip the partition holding that row, causing missing or incorrect query results.

Example:

~~~sql
-- Use only after validating staging via a reliable process.
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
WITHOUT VALIDATION;
~~~

Do not use `WITHOUT VALIDATION` merely to "make it faster" without independent data verification. With primary key/unique constraints or special structures, Oracle may still perform checks or enforce additional rules even when `WITHOUT VALIDATION` is specified; never assume this option skips every check.

### 4.6. UPDATE GLOBAL INDEXES

Global indexes span multiple table partitions. When exchanging a partition, global index entries may need updating to reflect post-exchange ROWIDs/segments. The `UPDATE GLOBAL INDEXES` option directs Oracle to maintain global indexes during the operation as supported by the release.

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
INCLUDING INDEXES
WITH VALIDATION
UPDATE GLOBAL INDEXES;
~~~

If global index maintenance is omitted when updates are required, global indexes can become `UNUSABLE` or require subsequent maintenance depending on release/operation semantics. Check `USER_INDEXES` after the operation. Do not infer index health solely from DDL returning success.

## 5. Exchange-In Workflow: Loading Staging into a Partition

Recommended workflow with distinct steps:

1. Prepare the target partition and staging table.
2. Load data into staging.
3. Validate data and check duplicate keys.
4. Create/prepare required indexes and constraints.
5. Lock/freeze staging so no concurrent DML runs.
6. Exchange the partition with appropriate validation.
7. Verify indexes, constraints, and row counts.
8. Gather statistics.
9. Mark the batch complete and release to consumers.

### 5.1. Create the partitioned table

~~~sql
CREATE TABLE sales_part_lab (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2026
        VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026_01
        VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02
        VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p_future
        VALUES LESS THAN (MAXVALUE)
);
~~~

`P2026_01` accepts values from 2026-01-01 up to before 2026-02-01 because the preceding partition already captures values less than 2026-01-01.

### 5.2. Create a compatible staging table

~~~sql
CREATE TABLE sales_stage_lab (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL
);
~~~

In this lab, staging has the exact matching column order and data types. In production, thoroughly verify all additional attributes listed in Section 3.

### 5.3. Load data into staging

~~~sql
INSERT INTO sales_stage_lab
    (sale_id, sale_date, customer_id, amount)
VALUES
    (1001, DATE '2026-01-03', 501, 120);

INSERT INTO sales_stage_lab
    (sale_id, sale_date, customer_id, amount)
VALUES
    (1002, DATE '2026-01-15', 502, 250);

INSERT INTO sales_stage_lab
    (sale_id, sale_date, customer_id, amount)
VALUES
    (1003, DATE '2026-01-28', 501, 80);

COMMIT;
~~~

Committing staging before exchanging finalizes the batch and avoids exchange DDL implicitly committing an open load transaction. In real ETL, batch ID and load status should be tracked in a dedicated orchestration table.

### 5.4. Validate the range before exchanging

~~~sql
SELECT COUNT(*) AS rows_outside_partition
FROM sales_stage_lab
WHERE sale_date < DATE '2026-01-01'
   OR sale_date >= DATE '2026-02-01';
~~~

The result must be 0 for partition `P2026_01`. Also check:

~~~sql
SELECT COUNT(*) AS total_rows,
       COUNT(sale_id) AS nonnull_sale_id,
       COUNT(sale_date) AS nonnull_sale_date,
       MIN(sale_date) AS min_sale_date,
       MAX(sale_date) AS max_sale_date,
       SUM(amount) AS total_amount
FROM sales_stage_lab;
~~~

Check duplicate `sale_id` within staging:

~~~sql
SELECT sale_id, COUNT(*) AS duplicate_count
FROM sales_stage_lab
GROUP BY sale_id
HAVING COUNT(*) > 1;
~~~

If `sale_id` must be unique table-wide, you also need to check for duplicates against other partitions or ensure a global unique index/constraint protects it. Checking staging alone is insufficient to guarantee table-wide uniqueness.

### 5.5. Exchange into the partition

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
WITH VALIDATION;
~~~

This simple example has not created local/global indexes yet, so index options are not needed here. In production with indexes, choose `INCLUDING`/`EXCLUDING INDEXES` and `UPDATE GLOBAL INDEXES` according to your tested design.

After exchange:

- `P2026_01` holds rows 1001, 1002, 1003.
- `SALES_STAGE_LAB` receives the old segment of `P2026_01`.
- If the partition was previously empty, staging receives an empty segment.

### 5.6. Verify data after exchange

~~~sql
SELECT sale_id, sale_date, customer_id, amount
FROM sales_part_lab PARTITION (p2026_01)
ORDER BY sale_id;
~~~

Query without specifying the partition:

~~~sql
SELECT sale_id, sale_date, customer_id, amount
FROM sales_part_lab
WHERE sale_date >= DATE '2026-01-01'
  AND sale_date < DATE '2026-02-01'
ORDER BY sale_id;
~~~

Reconcile row counts and total amount against the staging batch metrics recorded prior to exchange. Store row counts, checksums/aggregates, and batch identifiers in the ETL system for reconciliation.

## 6. Local Indexes and INCLUDING INDEXES

### 6.1. Local indexes are partitioned alongside table partitions

Create a local index:

~~~sql
CREATE INDEX ix_sales_part_date_local_lab
ON sales_part_lab(sale_date)
LOCAL;
~~~

Oracle creates index partitions corresponding to the table partitions. When exchanging a partition, the target local index partition must also be handled.

### 6.2. Prepare matching indexes on staging

To swap the local index segment along with the data, staging needs a matching index with a compatible structure:

~~~sql
CREATE INDEX ix_sales_stage_date_lab
ON sales_stage_lab(sale_date);
~~~

Then:

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
INCLUDING INDEXES
WITH VALIDATION;
~~~

`INCLUDING INDEXES` does not build indexes on staging automatically. Matching indexes must be prepared in the exact structure Oracle requires. Verify column counts, column order, uniqueness, and related attributes.

### 6.3. EXCLUDING INDEXES and rebuilding

If the exchange omits indexes, the affected local index partition may be marked `UNUSABLE`. Afterward, check:

~~~sql
SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name = 'IX_SALES_PART_DATE_LOCAL_LAB'
ORDER BY partition_position;
~~~

If an index partition is `UNUSABLE` and the design requires it usable, rebuild it:

~~~sql
ALTER INDEX ix_sales_part_date_local_lab
REBUILD PARTITION p2026_01;
~~~

Substitute actual object names for index and partition. Rebuilding consumes I/O and TEMP/redo depending on options, and can impact workloads. Plan for it rather than treating rebuilds as free.

### 6.4. Choosing INCLUDING vs. EXCLUDING

| Scenario | Consideration |
| --- | --- |
| Need local indexes usable immediately after exchange | Prepare matching staging indexes and use `INCLUDING INDEXES` |
| Can tolerate unusable index partitions during maintenance window | `EXCLUDING INDEXES`, then rebuild per plan |
| Staging lacks matching indexes | Do not assume `INCLUDING INDEXES` creates them; prepare indexes or choose another strategy |
| Many large local indexes | Compare cost of building staging indexes vs. rebuilding partition indexes |

The best choice depends on batch volume, number of indexes, acceptable maintenance/downtime window, and post-exchange workload.

## 7. Global Indexes and UPDATE GLOBAL INDEXES

### 7.1. Global indexes span multiple partitions

Global indexes support lookups by keys excluding the partition key, such as a table-wide unique `SALE_ID`. When a partition is exchanged, affected ROWIDs/segment mappings can change; global indexes must be maintained to point to the right rows.

Example:

~~~sql
CREATE INDEX ix_sales_part_id_global_lab
ON sales_part_lab(sale_id)
GLOBAL;
~~~

### 7.2. Maintaining global indexes during exchange

If supported by the release and operation:

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
INCLUDING INDEXES
WITH VALIDATION
UPDATE GLOBAL INDEXES;
~~~

`UPDATE GLOBAL INDEXES` instructs Oracle to maintain global indexes during the exchange. This work can increase DDL duration and resource consumption, especially for large indexes.

If global index maintenance is omitted during the operation, index status may transition to `UNUSABLE` or require subsequent maintenance depending on release/operation semantics. Verify via `USER_INDEXES`/`ALL_INDEXES` after DDL.

### 7.3. Global index maintenance is a trade-off

| Option | Benefit | Cost/Risk |
| --- | --- | --- |
| Maintain global indexes during exchange | Consumers can continue using indexes in supported states | Exchange incurs extra index update work |
| Do not maintain during exchange | May reduce work inside critical DDL window | Indexes may become unusable; requires rebuild/maintenance before index-dependent workloads run |

Never let applications continue running queries relying on a global index while it is `UNUSABLE`. Make index status verification a gate before publishing data.

### 7.4. Checking indexes after exchange

~~~sql
SELECT index_name, index_type, status
FROM user_indexes
WHERE table_name = 'SALES_PART_LAB'
ORDER BY index_name;

SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name IN (
    SELECT index_name
    FROM user_indexes
    WHERE table_name = 'SALES_PART_LAB'
)
ORDER BY index_name, partition_position;
~~~

Global partitioned indexes may require inspecting `USER_IND_PARTITIONS`; global nonpartitioned indexes are checked in `USER_INDEXES`. Inspect the right views for each index type.

## 8. WITH VALIDATION and WITHOUT VALIDATION

### 8.1. WITH VALIDATION protects partition bounds

For RANGE partition `P2026_01`:

~~~text
lower bound: 2026-01-01 (exclusive of previous partition)
upper bound: 2026-02-01 (exclusive)
valid rows: 2026-01-01 <= SALE_DATE < 2026-02-01
~~~

`WITH VALIDATION` requires exchange table data to satisfy the partition condition. If even one row falls out of range, Oracle rejects the exchange.

### 8.2. WITHOUT VALIDATION places responsibility on the pipeline

When using `WITHOUT VALIDATION`, the pipeline must perform independent checks beforehand. At a minimum:

- All rows have valid partition keys, with no NULLs if the key requires NOT NULL.
- Min/max values lie within partition bounds.
- No discrete values violate LIST partition definitions.
- No duplicate keys violate unique constraints.
- Check constraints and business rules are satisfied.
- The batch is closed, with no DML modifying data after validation.

If staging can still be written to after the check step, prior validation results are no longer trustworthy. Lock staging or make it immutable prior to exchange.

### 8.3. Validation does not replace business checks

`WITH VALIDATION` checks partition compliance. It does not automatically verify:

- Whether total amount matches the source file.
- Absence of business duplicates if no matching constraint exists.
- Whether customer codes are valid in source systems.
- Whether the batch contains the expected row count.
- Whether time zones/currencies were converted correctly.

Keep partition-bound validation separate from data-quality validation.

### 8.4. Unique/primary keys and validation

Unique constraints can affect how Oracle performs the exchange and whether validation can be skipped. In some cases Oracle still checks uniqueness or applies additional rules even when `WITHOUT VALIDATION` is specified. Never treat `WITHOUT VALIDATION` as a guarantee that Oracle skips all checks. Consult the SQL Language Reference for your exact release, constraint states, and index structures before choosing.

## 9. Exchange-Out: Extracting a Partition into a Standalone Table

Exchange-out is useful when an old partition needs archiving or exporting without `DELETE`ing rows individually from the main table.

### 9.1. Prepare the archive table

The archive table needs a compatible structure:

~~~sql
CREATE TABLE sales_archive_stage_lab (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL
);
~~~

If indexes need to be exchanged, prepare matching indexes with the required structure. Otherwise, choose `EXCLUDING INDEXES` and plan index status verification/rebuilding.

### 9.2. Exchange the partition out to a table

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_archive_stage_lab
WITH VALIDATION;
~~~

After the operation:

- `SALES_ARCHIVE_STAGE_LAB` contains the rows previously in `P2026_01`.
- `P2026_01` receives the segment of `SALES_ARCHIVE_STAGE_LAB`, which is empty if the archive table was initially empty.

### 9.3. After exchange-out

Separate follow-up steps can be run:

- Reconcile row counts and aggregates.
- Gather statistics on the archive table.
- Export using Data Pump or move data through an archiving pipeline.
- Compress/move the archive table according to policy.
- Drop the now-empty partition if removing the old partition is the goal, or keep the partition for reuse.

Never `DROP` a partition before exchanging out if data must be kept. Likewise, never `DROP` the archive staging table before export/backup finishes.

### 9.4. Moving data between tables

Exchange-out followed by exchange-in can be used to transfer segments between compatible objects, though it must be managed carefully:

- Do the target and source tables share identical structures?
- Do they share identical partition bounds or data rules?
- Are indexes and constraints preserved?
- How are global indexes on each table handled?
- Is data verified after each swap?

Never treat exchange as a repeatable copy operation without accounting for the current contents on both sides.

## 10. DDL Transaction Boundaries, Locking, and Concurrency

### 10.1. EXCHANGE PARTITION is DDL

`ALTER TABLE EXCHANGE PARTITION` is DDL. Oracle performs an implicit commit per DDL rules: any active transaction is committed before the DDL runs, and a successful DDL is committed afterward.

Therefore:

- Never place exchange in the middle of DML statements inside a business transaction that must roll back together.
- Commit staging loads and finish data-quality checks before issuing DDL.
- Do not expect `ROLLBACK` to undo an exchange.
- If an erroneous exchange occurs, a reverse exchange DDL or pre-designed recovery procedure is required—not `ROLLBACK`.

### 10.2. Exchange requires locks

Exchange must acquire necessary locks/metadata locks on the partitioned table, partition, and exchange table. "Metadata-only" does not mean "completely non-blocking." Wait impact depends on release, options, active sessions, and object types.

Before exchanging:

- Verify the batch is closed.
- Prevent concurrent DML on staging.
- Identify workloads that might access the target partition during the DDL window.
- Configure appropriate timeouts/operational policies if available.
- Monitor session waits and DDL duration.

### 10.3. Failed DDL and data state

If exchange fails due to structural incompatibility or failed validation, Oracle raises an error and does not complete the swap. However, the pre-DDL implicit commit may still have committed the preceding DML transaction. Therefore, staging loads must be intentionally committed/finalized before calling exchange.

### 10.4. Active read consumers

Do not assume running queries will be unaffected. DDL requires appropriate locks and may wait or cause other sessions to wait. Test concurrency under realistic workloads, query durations, and your release. For critical tables, you may need a maintenance window or a data-publishing strategy via views/synonyms/application state.

## 11. Statistics and Metadata After Exchange

### 11.1. Inspect partitions

~~~sql
SELECT
    partition_name,
    partition_position,
    num_rows,
    blocks,
    tablespace_name
FROM user_tab_partitions
WHERE table_name = 'SALES_PART_LAB'
ORDER BY partition_position;
~~~

`NUM_ROWS`/`BLOCKS` depend on statistics and can be stale. Do not substitute statistics for `COUNT(*)` reconciliation when verifying a batch.

### 11.2. Check index status

~~~sql
SELECT index_name, status, uniqueness
FROM user_indexes
WHERE table_name = 'SALES_PART_LAB'
ORDER BY index_name;

SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name IN (
    SELECT index_name
    FROM user_indexes
    WHERE table_name = 'SALES_PART_LAB'
)
ORDER BY index_name, partition_position;
~~~

Publishing criteria should require every index needed by the workload to be usable. If any index is `UNUSABLE`, perform the appropriate rebuild or maintenance and re-verify.

### 11.3. Gather statistics

After exchange, review partition and global table statistics. Do not assume staging statistics automatically become accurate statistics for the partitioned table:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname     => USER,
        tabname     => 'SALES_PART_LAB',
        partname    => 'P2026_01',
        granularity => 'PARTITION',
        cascade     => TRUE
    );
END;
/
~~~

Depending on your statistics strategy, global statistics or incremental statistics may also need updating. In production, follow DBA policies and maintenance windows; gathering stats can change execution plans.

### 11.4. Check DDL and partition bounds

~~~sql
SELECT DBMS_METADATA.GET_DDL(
           'TABLE',
           'SALES_PART_LAB',
           USER
       )
FROM dual;
~~~

`USER_TAB_PARTITIONS` provides partition metadata, but `HIGH_VALUE` uses the `LONG` type in some dictionary views, limiting direct querying. Use `DBMS_METADATA` or appropriate tools when exact definitions must be extracted.

## 12. Exchange and Index/Constraint Strategies

### 12.1. Design indexes before choosing an exchange mode

Build an inventory:

| Index | Type | Role | Handling during exchange |
| --- | --- | --- | --- |
| IX_SALES_DATE_LOCAL | Local | Date queries within partition | `INCLUDING INDEXES` or rebuild local index partition |
| IX_SALES_ID_GLOBAL | Global | Table-wide lookup by sale_id | `UPDATE GLOBAL INDEXES` or post-exchange maintenance |
| PK_SALES | Unique/constraint-backed | Enforces uniqueness | Check whether unique key contains partition key and exchange rules |

Fill in this table for your actual schema. No single `INCLUDING INDEXES` clause solves every index type.

### 12.2. Unique keys and partition keys

If the table is partitioned by `SALE_DATE` while `SALE_ID` must be globally unique:

- A local unique index on `SALE_ID` alone may violate partitioned-table uniqueness rules because the key omits the partition key.
- A global unique index can enforce `SALE_ID` table-wide.
- Exchange must update the global unique index so entries point to the correct ROWIDs.

Partition key and uniqueness must be decided together. Otherwise, the exchange workflow may fail or force massive index rebuilds after every batch.

### 12.3. Constraint validation and staging

Staging should adhere to the corresponding data rules. Several checks can run prior to exchange:

~~~sql
-- Required values
SELECT COUNT(*)
FROM sales_stage_lab
WHERE sale_id IS NULL
   OR sale_date IS NULL
   OR customer_id IS NULL
   OR amount IS NULL;

-- Invalid amount values
SELECT COUNT(*)
FROM sales_stage_lab
WHERE amount < 0;

-- Check duplicates in staging
SELECT sale_id, COUNT(*)
FROM sales_stage_lab
GROUP BY sale_id
HAVING COUNT(*) > 1;
~~~

These are supplementary business checks. Database constraints should still be declared appropriately to protect data when other streams write to the table.

## 13. Controlled Production ETL Workflow

A pipeline can be divided into states:

~~~text
CREATED
   |
   v
LOADING
   |
   v
LOADED
   |
   v
VALIDATING
   |
   v
READY_TO_EXCHANGE
   |
   v
EXCHANGING
   |
   v
EXCHANGED
   |
   v
INDEX_CHECK
   |
   v
STATS_REFRESH
   |
   v
PUBLISHED
~~~

If any step fails, the batch must transition to an investigable error state. Never mark `PUBLISHED` simply because the DDL returned success; verify indexes, data, and statistics as required.

### 13.1. Record batch metadata

An orchestration table can store:

~~~sql
CREATE TABLE etl_exchange_batch_lab (
    batch_id       NUMBER PRIMARY KEY,
    target_table   VARCHAR2(30 CHAR) NOT NULL,
    target_partition VARCHAR2(30 CHAR) NOT NULL,
    source_name    VARCHAR2(100 CHAR),
    row_count      NUMBER,
    amount_total   NUMBER(18,2),
    status         VARCHAR2(30 CHAR) NOT NULL,
    loaded_at      TIMESTAMP,
    validated_at   TIMESTAMP,
    exchanged_at   TIMESTAMP,
    published_at   TIMESTAMP,
    error_message  VARCHAR2(2000 CHAR)
);
~~~

Batch metadata supports reconciliation and workflow recovery if the scheduler/job stops mid-run. Batch states must be managed consistently; never record an `"EXCHANGED"` status before the DDL has actually succeeded and been verified.

### 13.2. Verify staging is closed

Once batch loading finishes:

- Stop writers to staging or switch to a new staging table version.
- Record row count/aggregates.
- Run validation.
- Lock down the batch ID.
- Prevent other jobs from modifying staging during the exchange.

If DML occurs after validation but before exchange, the exchanged data may differ from the validated data. That is a pipeline race condition.

### 13.3. Idempotency and retries

If the scheduler loses connection and misses the DDL response, do not blindly re-run the exchange. Because exchange is a swap, a second run could swap the data back or produce an unintended state.

When the client loses the response:

1. Reconnect.
2. Inspect the contents of the target partition and staging.
3. Reconcile batch ID/row count/aggregates.
4. Check index status.
5. Determine whether the exchange already occurred.
6. Re-run only once the actual state is clearly understood.

This is workflow-level idempotency: actions must be driven by verified state rather than blindly resending the same DDL.

### 13.4. Logging and audit

Record:

- Batch ID and partition name.
- Start/end timestamps.
- Row counts and aggregates before/after.
- Validation mode.
- Index mode and global/local index status.
- Statistics refresh.
- User/session/SQL ID if needed.
- Publish outcome and errors.

Exchange DDL is a major data-management operation; auditing helps explain where data originated and when it entered the main table.

## 14. Limitations and Cases Requiring Careful Verification

Do not apply a simple exchange pattern to every table type. Before using it on complex objects, check release documentation for:

- Partitioned IOTs and overflow/mapping tables.
- LOB columns and SecureFiles/BasicFiles.
- Domain indexes.
- Bitmap indexes and specialized indexes.
- Virtual, invisible, or hidden columns.
- Identity columns and default expressions.
- Object types, nested tables, or XMLType.
- Reference partitioning and cascading exchange.
- Compression, tablespace, encryption, and logging attributes.
- Enabled/validated primary key, unique, check, and foreign key constraints.
- Global/local index maintenance.
- Online exchange or newer concurrency options in the release.

These conditions can change across releases and structures. Build a proof of concept using production-like DDL instead of testing only on a simple four-column table and assuming every object exchanges cleanly.

## 15. Common Errors

| Error/Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Exchange reports incompatible structure | Column count, order, data types, or attributes mismatch | Compare DDL of both tables including hidden/virtual columns |
| WITH VALIDATION fails | Rows exist outside partition bounds | Locate invalid rows, fix staging, and re-run validation |
| Using WITHOUT VALIDATION yet queries miss rows | Data exchanged into the wrong partition | Reconcile partition key; reverse exchange/relocate per plan |
| Local index partition UNUSABLE | Excluding indexes or incompatible index exchange | Rebuild/repair per index strategy |
| Global index UNUSABLE | Global index not maintained during operation | Use `UPDATE GLOBAL INDEXES` or rebuild per plan |
| INCLUDING INDEXES fails | Staging lacks matching index or definitions mismatch | Prepare compatible staging indexes |
| DDL waits on locks | Sessions actively using table/partition or staging | Identify blocker, coordinate workload and maintenance window |
| Staging holds old data after exchange | This is swap semantics | Inspect and process staging after reconciliation |
| Retrying exchange reverses data | Client resent DDL after connection drop | Check actual state before retrying |
| Statistics do not reflect new batch | Stale stats or not refreshed at right level | Gather partition/global stats per policy |
| DDL unexpectedly commits prior DML | Pre-DDL implicit commit | Intentionally finish staging transaction before exchange |
| Exchange unsupported on special object | Release/object type restriction | Check SQL Language Reference and test in equivalent environment |

## 16. Comprehensive Lab: Exchange-In Then Exchange-Out

This lab assumes an Oracle environment licensed for Partitioning. Run in a dedicated schema.

### Step 1 — Create the partitioned table

~~~sql
CREATE TABLE sales_exchange_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

### Step 2 — Create the staging table

~~~sql
CREATE TABLE sales_exchange_stage_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
);
~~~

### Step 3 — Load staging

~~~sql
INSERT INTO sales_exchange_stage_lab VALUES
    (1, DATE '2026-01-03', 101, 120);

INSERT INTO sales_exchange_stage_lab VALUES
    (2, DATE '2026-01-15', 102, 250);

INSERT INTO sales_exchange_stage_lab VALUES
    (3, DATE '2026-01-28', 101, 80);

COMMIT;
~~~

### Step 4 — Check partition range

~~~sql
SELECT COUNT(*) AS invalid_rows
FROM sales_exchange_stage_lab
WHERE sale_date < DATE '2026-01-01'
   OR sale_date >= DATE '2026-02-01';
~~~

The result must be 0.

### Step 5 — Exchange-in

~~~sql
ALTER TABLE sales_exchange_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_exchange_stage_lab
WITH VALIDATION;
~~~

### Step 6 — Confirm the partition received the data

~~~sql
SELECT *
FROM sales_exchange_lab PARTITION (p2026_01)
ORDER BY sale_id;
~~~

### Step 7 — Create an archive table and exchange-out

~~~sql
CREATE TABLE sales_exchange_archive_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
);

ALTER TABLE sales_exchange_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_exchange_archive_lab
WITH VALIDATION;
~~~

After this step, `SALES_EXCHANGE_ARCHIVE_LAB` holds the rows just exchanged out. `P2026_01` receives the empty segment from the initial archive table.

### Step 8 — Reconcile archive

~~~sql
SELECT COUNT(*) AS row_count,
       MIN(sale_date) AS min_date,
       MAX(sale_date) AS max_date,
       SUM(amount) AS total_amount
FROM sales_exchange_archive_lab;
~~~

Reconcile with the batch metadata recorded earlier.

### Step 9 — Clean up lab (optional)

~~~sql
DROP TABLE sales_exchange_archive_lab PURGE;
DROP TABLE sales_exchange_stage_lab PURGE;
DROP TABLE sales_exchange_lab PURGE;
~~~

`DROP TABLE` is DDL and performs an implicit commit. Run only when sure the tables belong to the lab and data is no longer needed.

## 17. Pre-Execution Checklist for EXCHANGE PARTITION

**Structure**

- Target table has the right partition and bounds.
- Staging is a compatible exchange table.
- Column count, order, data types, and column properties have been reconciled.
- Hidden/virtual/identity/LOB/object-specific columns have been checked.
- Matching constraints and indexes have been prepared.

**Data**

- Batch load is finished and committed.
- No active writers remain on staging.
- Range/list partition validation passed.
- Duplicate/business checks passed.
- Row counts and aggregates have been recorded.
- Batch ID and data source have been audited.

**Exchange options**

- Choice between `WITH VALIDATION` and `WITHOUT VALIDATION` is clearly justified.
- `INCLUDING`/`EXCLUDING INDEXES` chosen according to local index strategy.
- Global indexes are maintained or have a rebuild plan.
- Release supports the exact syntax and options used.

**Operations**

- DDL implicit commit behavior is understood.
- Locks and workload impact have been evaluated.
- Appropriate maintenance window/timeout is in place.
- Step exists to verify partition and index status.
- Step exists to gather statistics.
- Plan exists for reconciliation, recovery, and post-swap staging handling.
- Rule exists to verify actual state before retrying.

## 18. Self-Check Questions

1. Is `EXCHANGE PARTITION` a data copy or a segment swap?
2. Why can staging contain the partition's old data after an exchange?
3. How do exchange-in and exchange-out differ in purpose?
4. Why should CTAS not be treated as a complete copy of table DDL?
5. Which attributes must be compatible between staging and the partitioned table?
6. What does `WITH VALIDATION` verify?
7. How can `WITHOUT VALIDATION` cause wrong results during partition pruning?
8. Does partition-bound validation replace data-quality validation?
9. What condition does `INCLUDING INDEXES` require on staging?
10. How can `EXCLUDING INDEXES` affect a local index partition?
11. What is the purpose of `UPDATE GLOBAL INDEXES`?
12. Why must `USER_INDEXES` and `USER_IND_PARTITIONS` be checked after exchange?
13. Why might a unique key excluding the partition key require a global unique index?
14. Why is `EXCHANGE PARTITION` an important DDL boundary?
15. Can a successful exchange be undone with `ROLLBACK`?
16. Why must staging be committed/finalized before exchanging?
17. Can exchange wait for locks even though it is primarily a metadata operation?
18. What must be verified after exchange before publishing?
19. Why must exchange never be blindly retried after a client loses connection?
20. When is exchange-out useful for archiving?

**Suggested Answers:**

1. A segment/metadata swap between a partition and a compatible nonpartitioned table.
2. Because it is a swap operation; the partition's old data moves to the staging table.
3. Exchange-in moves staging into a partition; exchange-out extracts a partition into a standalone table.
4. CTAS generally does not copy all constraints, indexes, triggers, and column attributes.
5. Column count, order, data types, and relevant special attributes.
6. Whether exchange table data satisfies the target partition bounds.
7. Rows placed in the wrong partition may be skipped by pruning when querying by the partition key.
8. No; business rules, duplicates, aggregates, and data sources must be checked separately.
9. Corresponding staging indexes must have a compatible structure to exchange index segments.
10. Local index partitions may become `UNUSABLE` and require rebuilding.
11. Maintain global indexes so entries continue pointing to the right rows after exchange.
12. To confirm indexes remain usable and safe for consumers.
13. Local unique indexes must satisfy partition-key rules; global unique indexes can enforce table-wide uniqueness.
14. DDL performs an implicit commit and does not roll back like DML.
15. No; a reverse exchange DDL or recovery procedure is required.
16. Because DDL can implicitly commit open transactions before executing.
17. Yes; DDL still requires appropriate metadata/table/partition locks.
18. Row counts, aggregates, partition bounds, constraints, index status, statistics, and batch state.
19. Because exchange is a swap; running it again may swap data back.
20. When you want to extract an old partition into a standalone table for export/archiving/separate processing.

## Oracle Reference Documentation

- [Oracle Database 19c VLDB and Partitioning Guide — Exchanging Partitions](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/maintenance-partition-tables-indexes.html): exchanging partitions and managing partitioned tables/indexes.
- [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): `EXCHANGE PARTITION` syntax, index options, and validation.
- [Oracle Database 19c SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): creating partitioned tables and structural attributes.
- [Oracle Database 19c VLDB and Partitioning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/): partitioning strategies, maintenance, and data warehousing.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html): gathering and managing statistics.
- [Oracle Database Reference — USER_TAB_PARTITIONS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TAB_PARTITIONS.html): partition metadata for the current schema.
- [Oracle Database Reference — USER_IND_PARTITIONS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_IND_PARTITIONS.html): status and metadata of local/global index partitions.

**Key takeaway:** `EXCHANGE PARTITION` is a segment-swap operation between a partition and a compatible staging table. Prepare staging carefully, verify data belongs in the target partition, decide how local/global indexes are handled, and verify data and index status after DDL. Because exchange is DDL with an implicit commit and cannot be undone with `ROLLBACK` like DML, pipelines must finalize batches, track states, reconcile results, and verify actual state before retrying.
