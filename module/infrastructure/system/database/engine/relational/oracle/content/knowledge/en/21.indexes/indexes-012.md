# UNUSABLE Status, REBUILD, COALESCE, and Index Maintenance Costs in Oracle

## 1. Why Monitor Index Status?

Indexes help Oracle locate rows faster without scanning the entire table in many cases. However, an index is also a physical data structure that must be maintained whenever the table changes. During operations, an index can become **UNUSABLE**, accumulate underutilized leaf blocks, or need to be moved to another tablespace or physically rebuilt.

Oracle provides different operations for different goals:

- **UNUSABLE:** marks an index or index partition as unusable.
- **REBUILD:** recreates the index structure, typically used to recover an unusable index or change storage attributes.
- **COALESCE:** merges adjacent B-tree leaf blocks to increase free-space reuse within the index.

Do not treat `REBUILD` and `COALESCE` as interchangeable commands. An unusable index must be rebuilt to become usable again; coalesce reorganizes leaf blocks of an already valid B-tree.

Furthermore, indexes incur maintenance overhead on every DML statement touching indexed columns. A design with too many indexes can help `SELECT`s while making `INSERT`, `UPDATE`, `DELETE`, bulk loads, backups, and space management more expensive.

> This lesson uses Oracle Database 19c. `ALTER INDEX` and DDL commands can directly affect applications; test only in a lab schema. Oracle DDL issues an implicit commit, so you cannot rely on `ROLLBACK` to undo a rebuild or unusable operation.

## 2. VALID and UNUSABLE Status

### 2.1. VALID

An index in `VALID` status can be considered by the optimizer when building execution plans and is maintained according to Oracle DML rules. `VALID` status does not guarantee the optimizer will pick the index; selection still depends on predicates, statistics, selectivity, access cost, and other factors.

### 2.2. UNUSABLE

An index in `UNUSABLE` status cannot be used as a valid index for data access. The optimizer ignores it. If an index or partition is unusable, queries can still run using a full table scan or another access path, provided the query has a valid way to read the data.

Example:

~~~sql
ALTER INDEX ix_orders_customer UNUSABLE;
~~~

This statement marks the entire index unusable. It does not drop the source table or delete business data in the table. The index segment may still remain allocated until rebuilt or handled via appropriate DDL.

### 2.3. An unusable index vs. an index not chosen by the optimizer

These two situations are different:

- **VALID index not chosen:** the optimizer decided a full scan or another access path is cheaper. The index still exists and may be used by other SQL statements.
- **UNUSABLE index:** the optimizer cannot use that index. You must restore its status with an appropriate operation if applications depend on it.

Do not conclude an index is unusable merely because an execution plan does not show `INDEX RANGE SCAN` or `INDEX UNIQUE SCAN`.

## 3. Why Indexes or Index Partitions Become UNUSABLE

Common causes include:

### 3.1. Intentional marking

A DBA or data-loading job may intentionally mark an index unusable:

~~~sql
ALTER INDEX ix_sales_customer UNUSABLE;
~~~

The usual goal is avoiding index maintenance overhead during a bulk load or major maintenance task, then rebuilding once data loading completes.

Do not apply this casually to indexes actively used by applications. Check constraints, index types, privileges, and recovery plans first.

### 3.2. Bulk loads and direct-path loads

Some direct-path load processes or options that skip index maintenance can leave indexes unusable. For example, SQL*Loader direct path has options related to skipping index maintenance; outcomes depend on load mode and errors encountered.

If skipping index maintenance to speed up loading, the workflow must include steps to inspect and rebuild indexes before reopening workloads that rely on them.

### 3.3. Table or partition maintenance operations

Some table DDL operations, such as `MOVE`, or partition maintenance operations can render one or more indexes or index partitions unusable unless Oracle is instructed to maintain indexes in the same statement.

For example, when dropping or truncating a table partition, global indexes may be affected unless an appropriate global index maintenance option is used. Exact syntax and behavior depend on operation type, release, and index type. After partition maintenance, check the status of both local index partitions and global indexes rather than assuming everything remains `VALID`.

### 3.4. Only a single partition becomes unusable

With a partitioned index, a single index partition or subpartition can become unusable while remaining partitions stay usable. This is why you must check partition-level metadata rather than only the overall index status.

Example:

~~~sql
ALTER INDEX ix_sales_local
MODIFY PARTITION p2026_01 UNUSABLE;
~~~

Partition names are illustrative. For a local partitioned index, each index partition corresponds to a table partition under the local index structure.

### 3.5. UNIQUE and PRIMARY KEY constraints

Indexes enforcing `PRIMARY KEY` or `UNIQUE` constraints uphold uniqueness. Oracle does not permit arbitrarily marking a constraint-enforcing index unusable in a way that bypasses uniqueness checking. Inspect dependent constraints before planning maintenance.

If you need to change how a constraint is enforced, design a dedicated constraint workflow and understand the data integrity implications. Never treat marking an index unusable as a safe way to temporarily disable a unique constraint.

## 4. DML When an Index Is UNUSABLE

### 4.1. Impact on SELECT

The optimizer does not use unusable indexes. Queries can still succeed via a full table scan or another index:

~~~sql
SELECT order_id, order_total
FROM orders
WHERE customer_id = 100;
~~~

If the index on `CUSTOMER_ID` is unusable and no alternative access path exists, Oracle may have to read more table blocks. Query results remain accurate; the issue is potential performance degradation.

### 4.2. Impact on INSERT, UPDATE, and DELETE

Standard DML must maintain associated indexes. When an index is unusable, behavior depends on configuration and index type:

- When skipping unusable indexes is disallowed, DML can fail with `ORA-01502`.
- `SKIP_UNUSABLE_INDEXES` allows certain DML statements to continue while skipping unusable nonunique indexes.
- An unusable index enforcing a `UNIQUE`/`PRIMARY KEY` constraint cannot be skipped in a way that defeats uniqueness checking; DML must still preserve the constraint.

Example error:

~~~text
ORA-01502: index 'OWNER.IX_ORDERS_CUSTOMER' or partition of such index is in unusable state
~~~

### 4.3. SKIP_UNUSABLE_INDEXES

The parameter `SKIP_UNUSABLE_INDEXES` controls whether DML may skip certain unusable indexes/index partitions. Check it with:

~~~sql
SHOW PARAMETER skip_unusable_indexes;
~~~

Or:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'skip_unusable_indexes';
~~~

In a lab session, you can test:

~~~sql
ALTER SESSION SET skip_unusable_indexes = TRUE;
~~~

When enabled, Oracle can allow DML on a table with an unusable nonunique index without maintaining that index. This is useful in certain bulk-load workflows, though queries cannot use the index until it is rebuilt.

**Do not interpret `SKIP_UNUSABLE_INDEXES` as "all broken indexes are ignored."** Indexes backing unique constraints cannot be skipped if doing so bypasses uniqueness enforcement. Restrictions also depend on index type and DML operation.

### 4.4. Why must you rebuild right after skipping an index?

Suppose a table has an unusable index on `CUSTOMER_ID`. While DML is allowed to skip the index:

- The table continues receiving data.
- The index is not updated for those changes.
- The optimizer does not use the unusable index.
- Upon rebuild, Oracle reconstructs the index from current table data.

Therefore, enabling `SKIP_UNUSABLE_INDEXES` without rebuilding and verifying status leaves an unusable access path behind.

## 5. Inspecting Index and Partition Status

### 5.1. USER_INDEXES

To inspect indexes in the current schema:

~~~sql
SELECT index_name,
       table_name,
       index_type,
       uniqueness,
       status,
       tablespace_name
FROM user_indexes
ORDER BY table_name, index_name;
~~~

Useful columns:

- `INDEX_NAME`: index name.
- `TABLE_NAME`: base table.
- `INDEX_TYPE`: index type.
- `UNIQUENESS`: `UNIQUE` or `NONUNIQUE`.
- `STATUS`: status for non-partitioned indexes; for partitioned indexes, check partition metadata.
- `TABLESPACE_NAME`: tablespace storing the index, if applicable.

### 5.2. ALL_INDEXES and DBA_INDEXES

Users can inspect visible indexes via `ALL_INDEXES`:

~~~sql
SELECT owner, index_name, table_owner, table_name,
       index_type, uniqueness, status
FROM all_indexes
ORDER BY owner, table_name, index_name;
~~~

DBAs can inspect all indexes:

~~~sql
SELECT owner, index_name, table_owner, table_name,
       index_type, uniqueness, status
FROM dba_indexes
ORDER BY owner, table_name, index_name;
~~~

For partitioned indexes, index-level status may not reflect individual partition status. Inspect the corresponding partition views.

### 5.3. Checking index partitions

~~~sql
SELECT index_name,
       partition_name,
       status,
       tablespace_name
FROM user_ind_partitions
ORDER BY index_name, partition_position;
~~~

Using the DBA view:

~~~sql
SELECT index_owner,
       index_name,
       partition_name,
       status,
       tablespace_name
FROM dba_ind_partitions
WHERE status = 'UNUSABLE'
ORDER BY index_owner, index_name, partition_position;
~~~

### 5.4. Checking subpartitions

~~~sql
SELECT index_name,
       partition_name,
       subpartition_name,
       status,
       tablespace_name
FROM user_ind_subpartitions
ORDER BY index_name, partition_name, subpartition_position;
~~~

To find unusable subpartitions:

~~~sql
SELECT index_name, partition_name, subpartition_name, status
FROM user_ind_subpartitions
WHERE status = 'UNUSABLE';
~~~

### 5.5. Checking constraints using an index

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated,
       index_name
FROM user_constraints
WHERE index_name = UPPER(:index_name);
~~~

If an index is tied to a `PRIMARY KEY` or `UNIQUE` constraint, understand the constraint thoroughly before altering index status.

## 6. REBUILD: Recreating Index Structure

### 6.1. When is REBUILD needed?

`REBUILD` is typically used when:

- An index or partition has become unusable.
- Moving an index to a different tablespace.
- Changing supported storage or compression attributes.
- Recreating physical structure after a maintenance operation.
- Measured evidence shows rebuilding aligns with space or workload goals.

Do not rebuild solely because an index is old, because `BLEVEL` grew by one, or because someone claims "indexes always need periodic defragmentation." B-trees naturally split and reuse blocks; measure before intervening.

### 6.2. Rebuild an entire non-partitioned index

~~~sql
ALTER INDEX ix_orders_customer REBUILD;
~~~

Oracle rebuilds the index structure from the table data. Once successful, the index returns to usable status.

### 6.3. Rebuild an index partition

~~~sql
ALTER INDEX ix_sales_local
REBUILD PARTITION p2026_01;
~~~

Only the specified partition is rebuilt. This is usually the right choice when only one local or global index partition is unusable.

### 6.4. Rebuild an index subpartition

~~~sql
ALTER INDEX ix_sales_local
REBUILD SUBPARTITION sp2026_01_a;
~~~

Use the actual subpartition name from the dictionary. Do not confuse table partitions with index partitions/subpartitions; verify in `USER_IND_PARTITIONS` and `USER_IND_SUBPARTITIONS` before running.

### 6.5. Rebuild and move tablespace

~~~sql
ALTER INDEX ix_orders_customer
REBUILD TABLESPACE index_ts;
~~~

This recreates the index in the target tablespace. Ensure the tablespace has enough space during the rebuild, because the new structure may coexist with the old segment until the operation completes.

### 6.6. Rebuild ONLINE

~~~sql
ALTER INDEX ix_orders_customer REBUILD ONLINE;
~~~

`ONLINE` allows regular DML to continue on the table during most of the rebuild, subject to Oracle support conditions and index type. It reduces application blocking compared with an offline rebuild, though it does not mean zero locks or zero brief synchronization phases at the start and end.

Online rebuilds can consume additional resources and carry restrictions by index type, partitioning, edition, or specific operations. Check the 19c SQL Language Reference before running in production.

### 6.7. Parallel rebuild

~~~sql
ALTER INDEX ix_orders_customer
REBUILD PARALLEL 4;
~~~

Parallelism can shorten elapsed time using multiple processes, while increasing CPU, I/O, temporary space, and resource contention. Pick DOP based on system capacity rather than setting a high value just to finish one command quickly.

If you do not want to retain the parallel attribute after rebuilding:

~~~sql
ALTER INDEX ix_orders_customer NOPARALLEL;
~~~

### 6.8. NOLOGGING and recovery

You can specify `NOLOGGING` in certain rebuild operations:

~~~sql
ALTER INDEX ix_orders_customer
REBUILD NOLOGGING;
~~~

`NOLOGGING` can reduce redo volume for eligible portions of the operation, though not every change generates zero redo. `FORCE LOGGING` can override this setting. `NOLOGGING` also affects media recovery and standby/Data Guard synchronization; coordinate with DBAs and backup policies before using it.

Never use `NOLOGGING` as an unconditional performance trick.

## 7. COALESCE: Merging B-tree Leaf Blocks

### 7.1. Concept

In a B-tree index, leaf blocks hold index entries pointing to table rows. After many `DELETE`s or data changes, some leaf blocks may hold fewer entries and index space may be underutilized.

`COALESCE` merges adjacent mergeable leaf blocks within the same branch of the tree, making freed blocks available for reuse inside the index.

Syntax:

~~~sql
ALTER INDEX ix_orders_customer COALESCE;
~~~

For a partition:

~~~sql
ALTER INDEX ix_sales_local
COALESCE PARTITION p2026_01;
~~~

`COALESCE` is an online operation for B-tree indexes per Oracle's support rules and does not require allocating a new index segment of comparable size to replace the old segment.

### 7.2. COALESCE is not REBUILD

`COALESCE`:

- Merges adjacent mergeable leaf blocks.
- Lets the index reuse freed blocks.
- Does not reconstruct the entire index tree like `REBUILD` does.
- Does not move the index to another tablespace.
- Does not aim to lower the high-water mark or return full segment space to the tablespace.

`REBUILD`:

- Recreates the index structure.
- Can reorganize larger portions of the tree.
- Can change tablespace or supported attributes.
- Can produce a more compact new segment depending on data and storage.
- Typically requires extra space during the operation.

### 7.3. COALESCE does not fix an UNUSABLE index

`COALESCE` maintains leaf block structure on a usable B-tree index. If an index is marked `UNUSABLE`, `REBUILD` is required to recreate it before use. Do not use `COALESCE` as a substitute for `REBUILD` on an unusable index.

### 7.4. Does COALESCE return space to the tablespace?

Do not expect `COALESCE` to shrink the index segment or release trailing extents back to the tablespace. Freed blocks can be reused within the index segment, yet the high-water mark and allocated segment size may stay the same.

If the goal is moving tablespaces or reclaiming segment space, evaluate `REBUILD` or an appropriate segment operation rather than running `COALESCE` alone.

### 7.5. Index types

`COALESCE` applies to B-tree indexes. Do not apply the same assumptions to bitmap, domain, or specialized indexes. For specialized index types, use maintenance operations supported by that indextype and Oracle.

## 8. Comparing REBUILD, COALESCE, and Doing Nothing

| Condition / Goal | Typically appropriate action | Reason |
| --- | --- | --- |
| Index `UNUSABLE` | `REBUILD` | Recreates index to restore usability |
| Single index partition `UNUSABLE` | `REBUILD PARTITION` | Recovers only the affected partition |
| Single index subpartition `UNUSABLE` | `REBUILD SUBPARTITION` | Narrower scope than rebuilding the whole index |
| `VALID` B-tree with mergeable leaf blocks | `COALESCE` | Reuses leaf blocks without allocating a new segment |
| Need to move tablespace | `REBUILD TABLESPACE` | Recreates index in a different storage location |
| Need rebuild while DML continues | `REBUILD ONLINE` if supported | Reduces DML blocking time |
| Index `VALID`, queries fast, no space issues | Do nothing | Avoids unnecessary maintenance overhead |
| Index `VALID` yet not chosen by optimizer | Check query/stats/selectivity first | Not being chosen does not mean the index is broken |

## 9. Cost of REBUILD and COALESCE

### 9.1. Storage space

`REBUILD` typically requires space for the new structure while the old structure still exists. For large indexes, reserve tablespace capacity, temporary space, and headroom for the operation to finish.

`COALESCE` does not create a new index segment to replace the old one; thus additional space requirements are usually much lower.

### 9.2. CPU and I/O

`REBUILD` must read source data to recreate the index, sort it, and write the new structure. This can generate substantial CPU and I/O load, especially on large indexes or parallel rebuilds.

`COALESCE` operates on leaf blocks eligible for merging and is usually lighter than a full rebuild. Still, running coalesce frequently across many indexes consumes I/O and maintenance time.

### 9.3. REDO, UNDO, and recovery

Redo volume depends on `LOGGING`/`NOLOGGING`, `FORCE LOGGING`, operation type, and database configuration. Even with `NOLOGGING`, understand the implications for backups, media recovery, and standby databases.

`UNDO` primarily serves transactions and consistent reads; do not equate undo cost with redo. DDL and index maintenance operations follow Oracle's own logging mechanics.

### 9.4. Locking and concurrency

Offline rebuilds can block DML on the table during the operation. `REBUILD ONLINE` permits concurrent DML within supported limits, yet requires extra processing for concurrent changes and still involves synchronization points.

B-tree coalesce is an online operation, generally better suited when reducing leaf block slack without replacing the entire index.

### 9.5. Statistics and execution plans

After an index changes, review statistics and execution plans if the workload shows signs of change. Never assume a rebuild automatically makes queries faster.

Metrics commonly inspected in `USER_INDEXES`/`DBA_INDEXES`:

- `BLEVEL`: branch levels in the tree as recorded by Oracle stats.
- `LEAF_BLOCKS`: leaf block count per statistics.
- `DISTINCT_KEYS`: count of distinct key values.
- `CLUSTERING_FACTOR`: correlation between index order and table row placement.
- `LAST_ANALYZED`: timestamp when stats were gathered.

Rebuilding an index does not physically reorder rows in the table. Therefore, it does not automatically fix a poor clustering factor caused by table row placement. Never decide to rebuild based solely on `BLEVEL` or `LEAF_BLOCKS`; combine with workload, execution plans, response times, and segment metrics.

## 10. Index Maintenance Overhead in Daily DML

Indexes are not free. Every index may need updates whenever table data changes.

### 10.1. INSERT

When inserting a row into a table, Oracle must insert corresponding entries into every relevant index. A table with 12 indexes has significantly more structures to maintain than a table with 2 indexes.

### 10.2. DELETE

When deleting a row, Oracle must process entries in affected indexes. Leaf blocks may retain free space that Oracle can reuse for later entries.

### 10.3. UPDATE

If an `UPDATE` modifies a column in an index key or referenced by an index, Oracle must update the corresponding index entry. If it changes only columns unrelated to an index, that index generally needs no entry update.

For composite indexes, check whether modified columns belong to the key. Function-based indexes also depend on their indexed expressions.

### 10.4. Cumulative cost

Each additional index can increase:

- Duration and I/O of `INSERT`, `DELETE`, and some `UPDATE` operations.
- Redo/undo associated with data and index changes.
- Segment storage, backup size, and recovery time.
- Statistics gathering and maintenance window overhead.
- Resource contention in concurrent write workloads.

Indexes remain essential for primary keys, unique constraints, foreign key access patterns, and critical queries. The goal is not minimizing indexes at all costs, but keeping indexes with clear access or integrity value.

## 11. Maintaining Partitioned Indexes

### 11.1. Local partitioned indexes

A local index is partitioned along the same partitioning scheme as the table. Each table partition has a matching index partition.

If one local index partition becomes unusable:

~~~sql
ALTER INDEX ix_sales_local
REBUILD PARTITION p2026_01;
~~~

Rebuild only that partition rather than the entire index, if that is the affected scope.

### 11.2. Global partitioned indexes

A global partitioned index has a partitioning scheme independent of the table's partitions. An operation on a table partition can impact multiple parts of a global index depending on operation type and index maintenance options.

After `DROP`/`TRUNCATE`/`MOVE` of a table partition, check global indexes and related index partitions. Use `UPDATE INDEXES` or `UPDATE GLOBAL INDEXES` when supported by the syntax and when operations require keeping indexes valid.

Do not assume every partition maintenance command behaves identically for local and global indexes.

### 11.3. Checking before and after partition maintenance

~~~sql
SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name = 'IX_SALES_LOCAL'
ORDER BY partition_position;
~~~

After DDL, re-run the query to catch any `UNUSABLE` partitions. If found, identify the affected partitions and rebuild the exact scope.

### 11.4. Rebuild partition vs. coalesce partition

Rebuild partition:

~~~sql
ALTER INDEX ix_sales_local
REBUILD PARTITION p2026_01;
~~~

Coalesce partition:

~~~sql
ALTER INDEX ix_sales_local
COALESCE PARTITION p2026_01;
~~~

Rebuild restores an unusable partition or recreates its structure; coalesce merges leaf blocks of an already usable B-tree partition.

## 12. Planning Bulk Loads with Indexes

For staging tables or large fact tables, maintaining many indexes while loading millions of rows can slow loading down. A possible strategy:

1. Identify indexes that can be temporarily skipped during the batch.
2. Check which indexes enforce constraints and cannot be skipped.
3. Plan marking unusable or using a supported load method.
4. Run the bulk load with appropriate `SKIP_UNUSABLE_INDEXES` handling.
5. Rebuild unusable indexes after loading.
6. Gather or verify statistics.
7. Reconcile row counts, constraints, and execution plans before reopening workloads.

This is a controlled maintenance-window procedure, not how daily DML should run on live application-facing tables.

### 12.1. Illustrative workflow example

Suppose table `SALES_STAGE` has nonunique index `IX_SALES_STAGE_REGION`:

~~~sql
ALTER INDEX ix_sales_stage_region UNUSABLE;

ALTER SESSION SET skip_unusable_indexes = TRUE;

-- Bulk load data into SALES_STAGE using an appropriate procedure.

ALTER INDEX ix_sales_stage_region REBUILD;
~~~

After rebuild:

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE index_name = 'IX_SALES_STAGE_REGION';
~~~

Confirm the index returns to `VALID` before closing the maintenance window. If there are multiple indexes, track the list and status of every index rather than relying on a single successful rebuild command.

### 12.2. Do not mark constraint-supporting indexes unusable

Before applying the strategy above, check:

~~~sql
SELECT constraint_name, constraint_type, status, index_name
FROM user_constraints
WHERE table_name = 'SALES_STAGE';
~~~

Unique/primary key enforcement cannot be skipped like a nonunique secondary index. If the batch must enforce uniqueness while loading, design constraint and load procedures separately.

## 13. Evaluating Whether to Rebuild

Before rebuilding a `VALID` index, answer:

### 13.1. Is there an actual problem?

- Which query is slow?
- Does the execution plan use the index?
- Is the index the right access path for the predicate?
- Are statistics current and representative of the data?
- Has there been a major change in row count or value distribution?

If a query is slow due to unselective predicates, functions on columns not matching the index, datatype conversions, network latency, or table I/O, rebuilding will likely not fix the root cause.

### 13.2. Is there evidence regarding space?

Inspect segment size and index statistics:

~~~sql
SELECT segment_name,
       segment_type,
       bytes,
       blocks
FROM user_segments
WHERE segment_type LIKE 'INDEX%'
ORDER BY bytes DESC;
~~~

And:

~~~sql
SELECT index_name,
       blevel,
       leaf_blocks,
       distinct_keys,
       clustering_factor,
       last_analyzed
FROM user_indexes
ORDER BY leaf_blocks DESC;
~~~

Statistics might be stale. Check collection timestamps and subsequent workload.

### 13.3. Weigh impact against benefit

Rebuild can reduce segment size in certain cases, recreate index structure, or move tablespaces / change storage attributes.

However, it can also consume I/O, CPU, temporary space, redo depending on logging, and compete with active workloads. Rebuild will not speed up queries if the bottleneck lies elsewhere.

If an index works well and there is no specific storage objective, leaving it alone is usually the sensible choice.

## 14. DDL Operations and Transactions

`ALTER INDEX`, `ALTER TABLE`, `CREATE INDEX`, and `DROP INDEX` are DDL. Oracle performs an implicit commit before and after DDL under Oracle transaction rules.

Example:

~~~sql
UPDATE maintenance_log
SET status = 'STARTED'
WHERE task_id = 10;

ALTER INDEX ix_orders_customer REBUILD;

ROLLBACK;
~~~

Do not expect `ROLLBACK` to undo both the pre-DDL `UPDATE` and the rebuild as one normal DML transaction. DDL creates a commit boundary; the `UPDATE` before DDL may already have been implicitly committed.

Therefore:

- Never run index maintenance DDL in the middle of an unfinished business transaction.
- Schedule maintenance windows and log status separately.
- If auditing is needed, record before/after status in separate transactions knowing implicit commit behavior.
- Prepare a recovery plan in case a rebuild fails.

## 15. Common Errors

| Error / Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `ORA-01502` | DML or access encountered an unusable index or index partition | Check status and rebuild the proper scope |
| `ORA-00001` after rebuild or load | Source data has duplicate keys; unique constraint caught violation | Inspect duplicates and uniqueness rules |
| Rebuild runs out of space | Tablespace lacks capacity for the new structure | Allocate extra space, choose appropriate tablespace |
| Online rebuild rejected | Index type or syntax does not support online rebuild | Check index-type restrictions and Oracle 19c docs |
| DML still fails despite `SKIP_UNUSABLE_INDEXES` enabled | Index backs a unique constraint or index type cannot be skipped | Check constraint/index type |
| Query slows down after index becomes unusable | Optimizer cannot use the index and picks another access path | Rebuild if the index is needed; inspect execution plan |
| `COALESCE` does not shrink segment | `COALESCE` reuses blocks inside the index rather than releasing extents | Use `REBUILD` or suitable segment operation to reclaim space |
| Rebuild did not improve query | Root cause is not index structure | Inspect SQL, stats, selectivity, clustering factor, and I/O |
| Local/global partition index unusable after DDL | Partition maintenance did not maintain indexes with desired option | Check partition status and rebuild affected parts |
| Cannot rollback rebuild | DDL issued an implicit commit | Plan DDL separately, use recovery procedures |

## 16. Self-Contained Hands-On Lab

The following exercises use a dedicated table. Run only in a lab schema; never run `UNUSABLE` or `REBUILD` on real application indexes.

### 16.1. Create table and indexes

~~~sql
CREATE TABLE orders_index_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_total NUMBER(12,2),
    order_status VARCHAR2(20 CHAR)
);

INSERT INTO orders_index_lab
SELECT level,
       MOD(level, 1000) + 1,
       MOD(level * 17, 100000) / 100,
       CASE WHEN MOD(level, 3) = 0 THEN 'CLOSED' ELSE 'OPEN' END
FROM dual
CONNECT BY level <= 10000;

CREATE INDEX ix_orders_lab_customer
ON orders_index_lab(customer_id);

CREATE INDEX ix_orders_lab_status
ON orders_index_lab(order_status);

COMMIT;
~~~

### 16.2. Check status

~~~sql
SELECT index_name, index_type, uniqueness, status
FROM user_indexes
WHERE table_name = 'ORDERS_INDEX_LAB'
ORDER BY index_name;
~~~

### 16.3. Mark a nonunique index unusable

~~~sql
ALTER INDEX ix_orders_lab_customer UNUSABLE;
~~~

Verify:

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE index_name = 'IX_ORDERS_LAB_CUSTOMER';
~~~

### 16.4. Observe SELECT

~~~sql
SELECT COUNT(*)
FROM orders_index_lab
WHERE customer_id = 10;
~~~

The query can still run, though the optimizer will not use that unusable index. Use `EXPLAIN PLAN` or `DBMS_XPLAN` to observe the access path:

~~~sql
EXPLAIN PLAN FOR
SELECT *
FROM orders_index_lab
WHERE customer_id = 10;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

### 16.5. Test DML when an index is unusable

Check session setting:

~~~sql
SHOW PARAMETER skip_unusable_indexes;
~~~

To test skipping unusable nonunique indexes:

~~~sql
ALTER SESSION SET skip_unusable_indexes = TRUE;

INSERT INTO orders_index_lab
       (order_id, customer_id, order_total, order_status)
VALUES (20001, 10, 500, 'OPEN');

COMMIT;
~~~

Behavior depends on index type, constraints, and settings. Do not use this lab to conclude unique indexes are also skipped.

### 16.6. Rebuild to recover

~~~sql
ALTER INDEX ix_orders_lab_customer REBUILD;
~~~

Verify:

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE index_name = 'IX_ORDERS_LAB_CUSTOMER';
~~~

The index should return to `VALID`.

### 16.7. Test COALESCE

~~~sql
ALTER INDEX ix_orders_lab_customer COALESCE;
~~~

This illustrates coalescing on a usable B-tree index. Check status:

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE index_name = 'IX_ORDERS_LAB_CUSTOMER';
~~~

`COALESCE` does not replace `REBUILD` if the index is unusable.

### 16.8. View index statistics and segment

~~~sql
SELECT index_name, blevel, leaf_blocks,
       distinct_keys, clustering_factor, last_analyzed
FROM user_indexes
WHERE table_name = 'ORDERS_INDEX_LAB';

SELECT segment_name, bytes, blocks
FROM user_segments
WHERE segment_name LIKE 'IX_ORDERS_LAB%';
~~~

Metrics are point-in-time snapshots. Never judge performance from a single metric alone.

### 16.9. Clean up lab (optional)

~~~sql
DROP TABLE orders_index_lab PURGE;
~~~

`DROP TABLE` also drops dependent indexes on the table. DDL issues an implicit commit; run only after finishing the lab when data is no longer needed.

## 17. Index Maintenance Checklist

1. **Is the index actually UNUSABLE?** Check `USER_INDEXES` or `DBA_INDEXES`.
2. **Is it a partitioned index?** Check `USER_IND_PARTITIONS` and `USER_IND_SUBPARTITIONS`.
3. **Does the index support a PRIMARY KEY/UNIQUE constraint?** Check `USER_CONSTRAINTS` before altering.
4. **Is DML hitting ORA-01502 or are queries just not picking the index?** The two situations require different actions.
5. **Can SKIP_UNUSABLE_INDEXES be used?** Only when index type and constraints allow; plan an explicit rebuild schedule.
6. **What is the rebuild scope?** Whole index, partition, or subpartition.
7. **Is ONLINE required?** Check support by index type and resource overhead.
8. **Does the tablespace have enough space?** Account for the new segment, temp space, and I/O load.
9. **Are PARALLEL or NOLOGGING used?** Weigh CPU, redo, backups, standby, and `FORCE LOGGING`.
10. **Is the goal merging leaf blocks or recreating structure?** Pick `COALESCE` or `REBUILD` accordingly.
11. **Do you need to reclaim space to the tablespace?** `COALESCE` does not aim to lower segment high-water marks.
12. **Have execution plans and statistics been checked?** Never rebuild solely on `BLEVEL` or index age.
13. **Was partition maintenance involved?** Check local and global index status after DDL.
14. **Will DDL commit the active transaction?** Close business transactions before running.
15. **Was post-maintenance status verified?** Confirm indexes and partitions returned to usable state.

## 18. Self-Check Questions

**Question 1.** How does an `UNUSABLE` index differ from a `VALID` index not selected by the optimizer?

**Question 2.** How does the optimizer handle an unusable index?

**Question 3.** What error can DML encounter when an index is unusable?

**Question 4.** Does `SKIP_UNUSABLE_INDEXES` mean all unusable indexes can be skipped?

**Question 5.** Why cannot an index supporting a unique constraint be skipped like a nonunique index?

**Question 6.** When should `REBUILD` be used?

**Question 7.** When is `COALESCE` more appropriate than `REBUILD`?

**Question 8.** Does `COALESCE` return all segment space back to the tablespace?

**Question 9.** Can you `COALESCE` an unusable index to recover it?

**Question 10.** Why can `REBUILD ONLINE` still require resources and lock synchronization?

**Question 11.** Why check `DBA_IND_PARTITIONS` instead of only `DBA_INDEXES`?

**Question 12.** Does rebuilding an index automatically fix a poor clustering factor caused by table row order?

**Question 13.** Why do extra indexes increase `INSERT` and `DELETE` costs?

**Question 14.** Why should you not run `REBUILD` on a fixed schedule for every index?

**Question 15.** Can `REBUILD` DDL be rolled back like an `UPDATE`?

<details>
<summary>Answer hints</summary>

1. `VALID` but not chosen is an optimizer decision; `UNUSABLE` cannot be used by the optimizer.
2. Ignores the unusable index and picks another access path.
3. `ORA-01502` when DML cannot skip the unusable index.
4. No. Restrictions apply by index type and constraints; unique enforcement cannot be skipped.
5. Because the constraint must continue ensuring no duplicate keys exist.
6. When an index or index partition is unusable, structure needs recreation, moving tablespaces, or changing supported attributes.
7. When the B-tree is still usable and the goal is merging adjacent leaf blocks to reuse space.
8. No. Freed blocks can be reused within the index; segment size does not necessarily shrink.
9. No. An unusable index requires `REBUILD`.
10. `ONLINE` permits concurrent DML per support conditions, yet still requires resources and synchronization phases.
11. Because a partitioned index can have only one partition or subpartition unusable while others remain usable.
12. No. Rebuilding an index does not reorder physical rows in the table.
13. Each change requires maintaining extra index entries, I/O, redo/undo, and space.
14. Rebuilding consumes resources and may not improve queries if there is no actual issue.
15. No. `ALTER INDEX` is DDL and issues an implicit commit per Oracle rules.

</details>

## 19. Official Oracle Documentation

1. [Oracle Database 19c SQL Language Reference — ALTER INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-INDEX.html): `UNUSABLE`, `REBUILD`, `REBUILD PARTITION`, `COALESCE`, and index attributes.
2. [Oracle Database 19c SQL Language Reference — CREATE INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html): index types, partitioned indexes, logging, and parallel options.
3. [Oracle Database 19c Administrator's Guide — Managing Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-indexes.html): managing, monitoring, and maintaining indexes.
4. [Oracle Database 19c Database VLDB and Partitioning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/): local/global indexes and impact of partition maintenance.
5. [Oracle Database 19c Reference — USER_INDEXES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_INDEXES.html): status and statistics of indexes in the current schema.
6. [Oracle Database 19c Reference — USER_IND_PARTITIONS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_IND_PARTITIONS.html): index partition metadata.
7. [Oracle Database 19c Reference — USER_IND_SUBPARTITIONS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_IND_SUBPARTITIONS.html): index subpartition metadata.
8. [Oracle Database 19c Reference — SKIP_UNUSABLE_INDEXES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/SKIP_UNUSABLE_INDEXES.html): DML behavior with unusable indexes.
9. [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): `MOVE`, partition maintenance, and index maintenance options.

**Key principle:** `UNUSABLE` is an index state that the optimizer cannot use; DML can be impacted and `SKIP_UNUSABLE_INDEXES` helps only within supported limits—specifically, it never bypasses unique constraint enforcement. `REBUILD` recreates the structure and is the way to recover an unusable index. `COALESCE` merges only adjacent leaf blocks of a usable B-tree, aiding space reuse within the segment rather than replacing rebuilds or guaranteeing extents are returned to the tablespace. Every index increases DML and storage costs; maintain indexes only with clear goals, metrics, and recovery plans.
