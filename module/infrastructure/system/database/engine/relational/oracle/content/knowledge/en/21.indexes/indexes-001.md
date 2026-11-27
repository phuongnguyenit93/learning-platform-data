# B-tree Structure and Key Lookup Mechanisms in Oracle

When an application looks up a customer by ID, retrieves orders within a date range, or joins two tables on a key, Oracle needs to locate the matching rows in the data. Having to read the entire table every time can be expensive when the table contains millions of rows. A **B-tree index** is the most common index structure in Oracle Database: it sorts keys, organizes index blocks into a balanced tree, and stores ROWIDs that point to rows in the table.

An important point is that an index is not a complete copy of the table. It is an auxiliary structure maintained alongside the data, containing key values and row location information. When a query matches the key order and has good selectivity, Oracle can traverse from the root block through branch blocks to a leaf block, and then use the ROWID to read the data blocks. For a key range, Oracle can locate the first matching leaf entry and then continue scanning subsequent leaf entries in order.

This lesson belongs to the **Indexes** group of Database Engine Relational Oracle. It focuses on B-tree structure, how keys are searched, how leaf entries and ROWIDs are read, composite index ordering, access paths in execution plans, clustering factor, NULLs, DML impact, and optimizer statistics.

After this lesson, you will be able to:

- Describe the roles of root, branch, and leaf blocks in a B-tree index.
- Explain why a balanced tree finds keys with fewer block reads than a full table scan.
- Distinguish between index unique scan, range scan, full scan, fast full scan, and skip scan.
- Understand how Oracle uses ROWID to access rows in table blocks.
- Choose column order for a composite index based on predicates and key ordering.
- Explain selectivity, clustering factor, and the cost of table access by ROWID.
- Recognize the limitations of B-tree indexes with NULLs and expressions on columns.
- Understand index leaf splits, index maintenance during INSERT/UPDATE/DELETE, and the cost of having many indexes.
- Read an execution plan to determine whether an index is actually used and whether it provides a benefit.
- Inspect index metadata and statistics using data dictionary views.

> **Example scope:** Syntax and behavior are illustrated according to Oracle Database 19c. Tables with the `_LAB` suffix are for a dedicated practice schema. Execution plans depend on data, statistics, bind values, version, and configuration; no single access path is always best for every table.

## 1. Why Are Indexes Needed?

Suppose the `ORDERS` table has several million rows and the application frequently runs:

~~~sql
SELECT order_id, customer_id, order_date, status
FROM orders
WHERE order_id = :order_id;
~~~

Without an appropriate access path, Oracle may have to read many table blocks to find the required `order_id`. A B-tree index on `ORDER_ID` helps Oracle locate the key in a sorted structure and obtain the ROWID of the corresponding row.

### 1.1. Table scan and index lookup

~~~text
TABLE ACCESS FULL
  Read table blocks
  Evaluate predicates on rows
  Return matching rows

INDEX ACCESS
  Search key in B-tree
  Get ROWID from leaf entry
  Read table block containing the row
  Return matching rows
~~~

An index is beneficial when the number of rows to find is small relative to the amount of data that must be read. If a query needs most of the table, sequentially reading the entire table can be cheaper than traversing an index and jumping to very many table blocks.

### 1.2. An index is an auxiliary structure that must be maintained

A table can have multiple indexes. When you `INSERT`, `DELETE`, or `UPDATE` key columns, Oracle must update the affected indexes. Indexes speed up reads for some queries, but they increase:

- Storage space.
- Write work during DML.
- Redo and undo associated with changes.
- Maintenance, backup, and administration overhead.

Therefore, you should not create an index on every column just because the column appears in `WHERE`. Create indexes for the actual workload and verify effectiveness using execution plans and runtime statistics.

## 2. A B-tree Index Is a Balanced Multi-Way Search Tree

A B-tree in Oracle is a multi-way search tree structure organized by database blocks. It is not a simple binary tree with at most two children per node. A single branch block can contain many separator keys and many pointers to lower-level blocks.

### 2.1. Three conceptual block types

~~~text
                   ROOT BLOCK
                 /      |      \
                v       v       v
          BRANCH 1  BRANCH 2  BRANCH 3
            /  \       /  \      /  \
           v    v     v    v    v    v
         LEAF  LEAF  LEAF LEAF LEAF LEAF
           |     |     |    |    |    |
           +-----+-----+----+----+----+
             leaf blocks linked in key order
~~~

- **Root block:** the starting point of the tree. It contains separator key information and pointers to branch or leaf blocks below it.
- **Branch block:** an intermediate block that guides the search. It contains separator keys and child block addresses.
- **Leaf block:** the leaf level containing index entries with keys and ROWIDs (or equivalent information for the index entry).

For a very small index, the root can simultaneously serve as the leaf level; not every index has separate root, branch, and leaf levels.

### 2.2. Balanced tree

All leaf blocks sit at the same depth of the tree. As data grows or changes, Oracle maintains the structure so that searches still traverse a relatively small number of tree levels. Tree height generally grows slowly relative to the number of entries because each branch block can point to many child blocks.

Do not confuse a B-tree with a single sorted list. The structure is divided across many blocks; root/branch blocks direct searches to the appropriate leaf, while leaf blocks hold key ranges and are linked in order.

### 2.3. Separator keys and block pointers

A branch block holds key values that help Oracle choose which branch to descend into. When searching for a value, Oracle compares the search key against separator values, selects the appropriate child pointer, and continues at the child block. This process repeats until reaching the leaf level.

As an illustration, suppose numeric keys are split into ranges:

~~~text
Root:
  <  1000  -> Branch A
  >= 1000  -> Branch B

Branch B:
  <  1500  -> Leaf B1
  >= 1500  -> Leaf B2

Leaf B2:
  1500 -> ROWID X
  1501 -> ROWID Y
  1503 -> ROWID Z
~~~

The values above only illustrate navigation; they do not describe the exact way Oracle encodes branch keys or divides blocks in every index.

## 3. Leaf Entries: Keys and ROWIDs

### 3.1. What does a leaf entry contain?

For a standard B-tree index, a leaf entry represents a key value and the ROWID of a row in the table:

~~~text
INDEX LEAF ENTRY
+--------------------+--------------------------+
| Indexed key value  | ROWID                    |
+--------------------+--------------------------+
| 1001               | file/block/row location  |
| 1002               | file/block/row location  |
| 1002               | file/block/row location  |
| 1005               | file/block/row location  |
+--------------------+--------------------------+
~~~

If multiple rows share the same key value in a nonunique index, the leaf level can contain multiple entries for the same key with different ROWIDs. For a unique index, non-NULL key values must be unique according to the index/constraint rules.

### 3.2. ROWID is the row address

`ROWID` is a pseudocolumn provided by Oracle to locate a row. For a standard heap-organized table, an extended ROWID encodes information such as data object number, relative file number, block number, and row slot. It allows Oracle to identify the table block and the row's position within that block.

Example:

~~~sql
SELECT
    employee_id,
    ROWID
FROM employee_data_lab
WHERE employee_id = 101;
~~~

ROWID is not a business key. Do not use ROWID as a durable identifier in applications because row movement, shrink/move table operations, partition maintenance, or data reorganization can change ROWIDs.

### 3.3. Index lookup often requires additional table access

~~~text
1. INDEX RANGE/UNIQUE SCAN
       |
       v
   Get ROWID from leaf
       |
       v
2. TABLE ACCESS BY INDEX ROWID
       |
       v
   Read columns not in the index
~~~

For example, the index contains only `EMPLOYEE_ID`, but the query also retrieves `FULL_NAME`:

~~~sql
SELECT employee_id, full_name
FROM employee_data_lab
WHERE employee_id = 101;
~~~

Oracle finds `EMPLOYEE_ID` in the index, retrieves the ROWID, and then reads the table block to get `FULL_NAME`. The execution plan may show `INDEX UNIQUE SCAN` followed by `TABLE ACCESS BY INDEX ROWID`.

### 3.4. Index-only access

If all columns to be returned are already present in the index, Oracle can retrieve the data from the index without accessing the table block for each row:

~~~sql
SELECT employee_id
FROM employee_data_lab
WHERE employee_id = 101;
~~~

With a suitable primary-key index, the query may need only index access. However, the specific plan chosen by the optimizer still depends on statistics and cost. Some queries that need to verify data consistency or access additional information may require other operations.

Do not add many columns to an index just to turn a query into index-only access if the increased storage and DML cost outweighs the read benefit.

## 4. How Oracle Searches for a Key

### 4.1. Equality lookup

With an index on `EMPLOYEE_ID`:

~~~sql
SELECT employee_id, full_name
FROM employee_data_lab
WHERE employee_id = 101;
~~~

High-level process:

1. Read the root block.
2. Compare `101` against separator keys and select the child block.
3. Traverse any required branch blocks.
4. Locate the leaf entry with key `101`.
5. Retrieve the ROWID.
6. Read the table block if columns outside the index are needed.

If the index is unique and the equality condition covers the entire unique key, the optimizer can choose `INDEX UNIQUE SCAN`. If the index is nonunique, or equality covers only part of a composite key, `INDEX RANGE SCAN` may be used.

### 4.2. Range lookup

~~~sql
SELECT order_id, order_date, status
FROM orders
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01';
~~~

With an index on `ORDER_DATE`, Oracle can:

1. Find the first leaf entry with `ORDER_DATE` greater than or equal to the start date.
2. Read subsequent leaf entries in key order.
3. Stop when exceeding the end date boundary.
4. Use ROWIDs to fetch matching rows if needed.

Leaf blocks are linked in key order, making it possible to scan a contiguous range without returning to the root for every entry.

### 4.3. Prefix lookup

With a composite index `(A, B, C)`, a predicate with conditions on `A` or `A` and `B` can usually locate a key range using the leading prefix:

~~~sql
WHERE a = :a

WHERE a = :a
  AND b = :b

WHERE a = :a
  AND b >= :b_start
~~~

When the condition lacks the leading column `A`, Oracle generally cannot use the index as a direct range lookup on `B`. Other access paths such as index skip scan may be possible, but they require suitable data and statistics.

### 4.4. Why do searches typically require few block reads?

An index holds many entries per block. Reading one branch block can select among many child blocks. Therefore, even when a table has very many rows, the number of tree levels does not grow linearly with the number of entries.

Do not assume a fixed number of levels for every index. Block size, entry count, key length, compression, block fullness, and DML history affect actual fan-out and height.

## 5. B-tree Index Scan Types in Execution Plans

The operation name in an execution plan shows how Oracle uses the index. Not every operation containing the word `INDEX` means only one row is read.

### 5.1. INDEX UNIQUE SCAN

Finds at most one unique key value:

~~~sql
SELECT employee_id
FROM employee_data_lab
WHERE employee_id = :employee_id;
~~~

If `EMPLOYEE_ID` is a primary key and the equality predicate fully specifies the key, Oracle can use `INDEX UNIQUE SCAN`. This operation searches for a single unique entry by key.

### 5.2. INDEX RANGE SCAN

Used for a range of keys or multiple entries with the same value:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = :customer_id;
~~~

If multiple orders share the same `customer_id`, Oracle must read a corresponding range of leaf entries. Range scan also applies to greater-than/less-than conditions, `BETWEEN`, or prefixes of a composite index.

### 5.3. INDEX RANGE SCAN DESCENDING

Oracle can scan leaf entries in descending order when a query requests descending order and the index/ordering is compatible:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE customer_id = :customer_id
ORDER BY order_date DESC;
~~~

The ability to avoid a sort depends on column order, `ASC`/`DESC` direction in the index, predicates, and additional columns in `ORDER BY`. Do not assume every index range scan automatically satisfies every `ORDER BY`.

### 5.4. INDEX FULL SCAN

`INDEX FULL SCAN` reads all leaf entries in index order. It can be useful when:

- The query needs most or all keys in the index.
- The index contains all columns to be returned.
- The index order satisfies `ORDER BY`.
- The optimizer estimates reading the index is cheaper than reading the table.

Full scan here means the entire index, not the entire table.

### 5.5. INDEX FAST FULL SCAN

`INDEX FAST FULL SCAN` reads index blocks in a manner similar to a multiblock full scan, without guaranteeing rows are returned in key order. It can be used when the index contains all required columns and reading the index is cheaper than reading the table.

Comparison:

| Operation | Read scope | Key order guaranteed? |
| --- | --- | --- |
| INDEX RANGE SCAN | A range of keys | In index order within the scanned range |
| INDEX UNIQUE SCAN | A single unique key | Not a large-set scan |
| INDEX FULL SCAN | All leaves in order | In index order |
| INDEX FAST FULL SCAN | Entire index by block/multiblock | Key order not guaranteed |

### 5.6. INDEX SKIP SCAN

Skip scan can be useful when a composite index has multiple columns, but the query does not filter on the leading column. Oracle treats distinct values of the leading column as sub-ranges and probes the rest of the index.

For example, an index `(GENDER, DEPARTMENT_ID)` where `GENDER` has very few distinct values:

~~~sql
SELECT employee_id
FROM employee_data_lab
WHERE department_id = :department_id;
~~~

Oracle may consider `INDEX SKIP SCAN` if the number of distinct `GENDER` values is low and the estimated cost is favorable. This is not a universal substitute for an index starting with `DEPARTMENT_ID`. If querying by `department_id` is an important workload with good selectivity, an index `(DEPARTMENT_ID, ...)` is usually the more direct design.

### 5.7. INDEX JOIN SCAN

In some cases, Oracle can combine multiple indexes to obtain all query columns without accessing the table, via an index join. This is a specialized access path; do not build multiple overlapping indexes just hoping the optimizer will choose it.

### 5.8. No single access path is always best

A query fetching one customer from a large table may be an ideal fit for an index range scan. A report fetching 80% of the rows may be better served by a full table scan. You must consider actual row counts, blocks to read, clustering factor, returned columns, sorting, parallelism, and overall cost.

## 6. Composite B-tree Indexes and Column Order

A composite index contains multiple columns in a defined order. That order is a critical part of the search structure.

### 6.1. Example index (CUSTOMER_ID, ORDER_DATE)

~~~sql
CREATE INDEX ix_orders_customer_date_lab
ON orders_lab(customer_id, order_date);
~~~

Keys are sorted by `CUSTOMER_ID` first, and then by `ORDER_DATE` within each `CUSTOMER_ID` group:

~~~text
(CUSTOMER_ID, ORDER_DATE)

(10, 2026-01-03)
(10, 2026-01-12)
(10, 2026-02-01)
(20, 2026-01-05)
(20, 2026-03-09)
(30, 2026-02-15)
~~~

Matching query:

~~~sql
SELECT order_id, order_date
FROM orders_lab
WHERE customer_id = :customer_id
  AND order_date >= :start_date
  AND order_date < :end_date;
~~~

Oracle can locate the `customer_id` group and then scan the `order_date` range within that group.

### 6.2. Leading column

For index `(CUSTOMER_ID, ORDER_DATE)`:

| Predicate | Chance of using the index |
| --- | --- |
| CUSTOMER_ID = :c | Uses leading prefix |
| CUSTOMER_ID = :c AND ORDER_DATE >= :d | Uses prefix and range |
| CUSTOMER_ID = :c AND ORDER_DATE BETWEEN ... | Uses prefix and range |
| ORDER_DATE >= :d, without CUSTOMER_ID | Not a direct range lookup on the leading prefix; skip scan or another access path may be considered |

Do not say the second column "can never be used." Skip scan, full index scan, fast full scan, or other transformations can allow the index to be used. However, if the workload primarily filters `ORDER_DATE` independently, an index starting with `ORDER_DATE` is usually a better fit.

### 6.3. Column order is not based solely on individual selectivity

When choosing column order, consider:

- Which predicates commonly appear together.
- Equality predicates vs. range predicates.
- What `ORDER BY` the queries require.
- Number of distinct values and data distribution.
- Whether an index is needed to support a foreign key or join.
- Whether the index can serve multiple different SQL statements.
- DML overhead and storage size.

Do not mechanically apply the rule "most selective column always goes first." Leading columns should serve critical access patterns; the right order depends on predicate combinations and how the optimizer accesses the data.

### 6.4. Equality before range is often a useful starting point

For the query:

~~~sql
WHERE customer_id = :customer_id
  AND order_date >= :start_date
  AND order_date < :end_date
~~~

Index `(CUSTOMER_ID, ORDER_DATE)` is often a natural candidate: equality on the leading column, range on the next column. But if other queries filter on date independently, another index may be needed. Design for the overall workload, not just a single SQL statement.

### 6.5. Indexes with DESC direction

Oracle allows defining `ASC`/`DESC` ordering on index columns:

~~~sql
CREATE INDEX ix_orders_customer_date_desc_lab
ON orders_lab(customer_id, order_date DESC);
~~~

A descending index can support queries retrieving the latest date per customer when other conditions align. However, Oracle can also scan an ascending index in reverse in many cases. Check the execution plan before creating a `DESC` index solely because a SQL statement has `ORDER BY DESC`.

## 7. Selectivity and Cardinality

### 7.1. Selectivity is how strongly a predicate filters

Selectivity describes the fraction of data retained after applying a predicate. A condition matching only 10 rows in a 1-million-row table has very high selectivity in the sense of strong filtering (a small result ratio). A condition matching 800,000 rows out of 1 million filters weakly.

Example:

~~~sql
WHERE employee_id = 101
~~~

If `employee_id` is a primary key, the result is at most one row.

~~~sql
WHERE employment_status = 'ACTIVE'
~~~

If 95% of employees are `ACTIVE`, the predicate does not filter much. A full table scan may be cheaper than index lookups plus hundreds of thousands of table block visits.

### 7.2. Cardinality is the estimated or actual row count

The optimizer estimates the number of rows after each operation to compare plans. In an execution plan:

- `E-Rows`: estimated number of rows.
- `A-Rows`: actual number of rows when runtime statistics are gathered.

If estimates diverge far from reality, the optimizer can choose an inappropriate join method, join order, or access path.

### 7.3. Histograms and skewed distributions

A column can have a skewed distribution. For example, 95% of rows have `STATUS='ACTIVE'` while only 5% are `'CLOSED'`. Simple average statistics may not describe every value well. Histograms can help the optimizer estimate selectivity per specific value when appropriate.

Do not blindly create histograms on every column. Statistics strategy must be based on workload, bind usage, and DBA policy.

## 8. Clustering Factor: The Index Finds Rows, but Table Blocks Are Scattered

An index may find ROWIDs very quickly, yet reading the table blocks can still be expensive if rows in key order are scattered across the table.

### 8.1. What does clustering factor measure?

Clustering factor describes the correlation between the order of keys in the index and the physical order of rows in table blocks. In simple terms:

- Low clustering factor, close to the number of table blocks: rows with nearby keys tend to reside near each other in the table.
- High clustering factor, close to the number of rows: rows with nearby keys tend to reside in many different table blocks.

This is a statistic used to estimate the cost of `TABLE ACCESS BY INDEX ROWID`, not a direct measure of business quality or overall fragmentation.

### 8.2. Intuitive example

Case where data is organized in correlation with the key:

~~~text
INDEX KEY ORDER:  1  2  3  4  5  6
ROWID BLOCK:      A  A  A  B  B  B
~~~

Case where rows are scattered:

~~~text
INDEX KEY ORDER:  1  2  3  4  5  6
ROWID BLOCK:      A  Z  C  X  B  Y
~~~

In the first case, multiple consecutive ROWIDs can be read from just a few table blocks. In the second case, Oracle may have to access many different blocks.

### 8.3. Impact on the decision to use an index

If a predicate returns very few rows, an index can still perform well even when the clustering factor is high. If a predicate returns many rows and each ROWID points to a different block, a full table scan may be cheaper.

Therefore, "having an index" is not enough to conclude a query is fast. Look at selectivity, clustering factor, number of table blocks, and number of rows to fetch.

### 8.4. Checking clustering factor

~~~sql
SELECT
    index_name,
    blevel,
    leaf_blocks,
    distinct_keys,
    num_rows,
    clustering_factor
FROM user_indexes
WHERE table_name = 'ORDERS_LAB'
ORDER BY index_name;
~~~

Table names in the data dictionary are normally stored in uppercase unless created with quoted identifiers. Replace `ORDERS_LAB` with the actual table name.

## 9. NULLs and B-tree Indexes

### 9.1. Single-column B-tree indexes do not store entries when the value is NULL

For a standard B-tree index on a single column, rows where that column is `NULL` do not produce an index entry. Thus, the query:

~~~sql
SELECT *
FROM employee_data_lab
WHERE work_email IS NULL;
~~~

usually cannot use a B-tree index on `WORK_EMAIL` alone to find all `NULL` rows, because `NULL` rows have no entry in that index.

### 9.2. Composite indexes can store entries when one column is NULL

In a multi-column index, if at least one column in the key has a non-NULL value, an index entry can exist even when another column is `NULL`. For example, an index `(DEPARTMENT_ID, WORK_EMAIL)` can have an entry for `(10, NULL)` because the entire composite key is not `NULL`.

Consequently, an `IS NULL` predicate on the second column may be supported in some composite indexes when the leading column is suitably constrained. Verify with the actual plan and data.

### 9.3. Function-based indexes for handling NULLs

If a workload frequently searches for `NULL` values in a single column, you can consider a function-based index with an expression that converts `NULL` into an appropriate sentinel value:

~~~sql
CREATE INDEX ix_employee_email_nvl_lab
ON employee_data_lab(NVL(work_email, 'NO_EMAIL'));
~~~

The query must use a compatible expression:

~~~sql
SELECT employee_id
FROM employee_data_lab
WHERE NVL(work_email, 'NO_EMAIL') = 'NO_EMAIL';
~~~

The sentinel must be chosen so it cannot be confused with valid data, and datatype/collation must match. Function-based indexes increase DML cost and require appropriate statistics. Do not create this kind of index if `NULL` queries are rare.

### 9.4. Unique indexes and NULLs

`NULL` is not compared like a normal value in SQL. Uniqueness rules have special cases when keys contain `NULL`; do not rely on assumptions that `NULL` is always treated as a distinct value or always excluded from every index. Check the unique constraint/index definition, key column count, and Oracle semantics for the specific case. For business keys that must have a value, explicitly declare `NOT NULL` together with `UNIQUE`/`PRIMARY KEY`.

## 10. Predicates That Can Make Indexes Hard to Use

### 10.1. Functions on columns

A standard index on `ORDER_DATE` is organized by `ORDER_DATE` values. The condition:

~~~sql
WHERE TRUNC(order_date) = DATE '2026-01-15'
~~~

applies a function to the column, so it does not map directly to a range lookup on a standard index.

You can rewrite it as a half-open interval:

~~~sql
WHERE order_date >= DATE '2026-01-15'
  AND order_date <  DATE '2026-01-16'
~~~

Or create a function-based index if the workload and design require the `TRUNC` expression:

~~~sql
CREATE INDEX ix_orders_order_day_lab
ON orders_lab(TRUNC(order_date));
~~~

### 10.2. Converting columns to strings

Do not filter a month with:

~~~sql
WHERE TO_CHAR(order_date, 'YYYY-MM') = '2026-01'
~~~

when a range predicate can be used:

~~~sql
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
~~~

A range predicate clearly expresses time boundaries, avoids format/NLS dependencies, and makes it easier to use index range access on the base column.

### 10.3. Implicit conversion

Comparing a `NUMBER` column with a string or a `DATE` column with an unformatted string can force Oracle to perform type conversion. If conversion is applied to the indexed column, the access path may be affected; conversion can also depend on NLS settings and cause data errors.

Bind the correct datatype:

~~~sql
-- JDBC: bind NUMBER using setLong/setBigDecimal,
-- DATE/TIMESTAMP using setDate/setTimestamp as appropriate.
~~~

Never concatenate strings to build SQL conditions from user input.

### 10.4. LIKE and leading wildcards

With a B-tree index on `LAST_NAME`:

~~~sql
WHERE last_name LIKE 'Ng%'
~~~

can support a range scan because the pattern has a fixed prefix. However:

~~~sql
WHERE last_name LIKE '%Ng'
~~~

has no fixed leading prefix, so a standard B-tree cannot easily locate a contiguous key range. A full scan, Oracle Text, or a different search design may be needed depending on requirements.

## 11. DML and B-tree Index Maintenance

An index is not a read-only structure. Oracle maintains indexes synchronously with table changes within a transaction.

### 11.1. INSERT

When inserting a row:

1. Oracle writes the row into a table block.
2. Creates an entry in each relevant index, if the key qualifies to be stored.
3. Updates the leaf/branch structure if necessary.
4. Writes appropriate undo/redo for recovery and rollback.

If there is space in the index leaf block, the entry is inserted in key order. If there is not enough space, Oracle may perform a block split.

### 11.2. DELETE

Deleting a row must remove or mark the corresponding entry in affected indexes according to index management rules. Deleting many rows can generate significant maintenance work and does not necessarily shrink the segment immediately.

### 11.3. Updating non-indexed columns

If an `UPDATE` only changes a column not included in an index key or index expression, that index usually does not need its entry updated. However, the table block still changes and the transaction still generates undo/redo.

### 11.4. Updating indexed columns

If a key value changes, Oracle must update the entry's position in the index: essentially removing the old key and inserting the new key. This increases DML cost compared to updating non-indexed columns.

### 11.5. Leaf block splits

When a leaf block no longer has room to insert a new entry in key order, Oracle may split the block, distribute entries to a new block, and update the tree structure as needed.

~~~text
BEFORE SPLIT
Leaf A: [10, 20, 30, 40, 50]  (nearly full)

INSERT key 35

AFTER SPLIT (ILLUSTRATIVE)
Leaf A: [10, 20, 30]
Leaf B: [35, 40, 50]
       |
       +-- branch/root updated if needed
~~~

The diagram above only illustrates the idea of splitting; entry counts, split points, and branch updates depend on actual block layout and state.

### 11.6. Why do many indexes slow down DML?

An `INSERT` into a table with 8 indexes may need to update up to 8 index structures in addition to the table block. Updating a column that participates in multiple indexes also generates extra work. Therefore, each index needs a clear workload justification.

### 11.7. Monotonically increasing keys

An index on an increasing key such as a sequence ID can concentrate new inserts into the rightmost leaf region in key order. This behavior can cause contention on the trailing leaf block under very high concurrent insert workloads. Reverse key indexes or partitioning designs may help certain workloads, but they carry trade-offs: reverse key indexes lose the ability to do standard key-order range scans. Do not apply them just because an ID increases; measure contention and query patterns first.

## 12. Index Compression and Variants

### 12.1. Prefix compression

A composite index may have many entries repeating the leading prefix value. Index key compression can reduce storage by storing repeated prefixes more efficiently within blocks:

~~~sql
CREATE INDEX ix_orders_region_customer_lab
ON orders_lab(region, customer_id)
COMPRESS 1;
~~~

This example illustrates compressing one prefix column. Effectiveness depends on the amount of repetition, key length, access patterns, and CPU cost. Compression can reduce block count/I/O, but also incurs processing overhead; measure on real data.

### 12.2. Reverse key indexes

A reverse key index reverses the byte order of the key to scatter sequentially increasing values across leaf blocks. It can reduce hot-block contention at the trailing insertion point in some insert-heavy workloads.

In return, key order is no longer useful for standard range scans on the original values. Equality lookups can still work well, while range predicates may lose their benefit. Choose this only when the workload is primarily equality lookups and contention has been measured.

### 12.3. Bitmap indexes are not B-tree

A bitmap index is a different index type, typically suited to analytical/read-heavy workloads and low-cardinality columns in environments with low concurrent DML. It represents row sets as bitmaps and has different locking characteristics. Do not casually use bitmap indexes on OLTP tables with heavy concurrent writes. This lesson focuses on B-tree indexes.

## 13. Index Statistics and the Data Dictionary

### 13.1. Viewing indexes in the current schema

~~~sql
SELECT
    index_name,
    table_name,
    index_type,
    uniqueness,
    status,
    blevel,
    leaf_blocks,
    distinct_keys,
    clustering_factor
FROM user_indexes
ORDER BY table_name, index_name;
~~~

Notable columns:

- `INDEX_TYPE`: index type.
- `UNIQUENESS`: `UNIQUE` or `NONUNIQUE`.
- `STATUS`: index status.
- `BLEVEL`: number of branch levels according to index statistics.
- `LEAF_BLOCKS`: number of leaf blocks according to statistics.
- `DISTINCT_KEYS`: number of distinct key values.
- `CLUSTERING_FACTOR`: correlation between index order and table blocks.

Statistics may be stale or uncollected; do not interpret a number in isolation from when and how stats were gathered.

### 13.2. Viewing columns and order of a composite index

~~~sql
SELECT
    index_name,
    column_position,
    column_name,
    descend
FROM user_ind_columns
WHERE table_name = 'ORDERS_LAB'
ORDER BY index_name, column_position;
~~~

`COLUMN_POSITION` shows the column order in the index. `DESCEND` shows the sort direction of the column in the index. Check this information before concluding whether a predicate can use a leading prefix or whether an `ORDER BY` can be satisfied by the index.

### 13.3. Viewing which constraint an index belongs to

~~~sql
SELECT
    constraint_name,
    constraint_type,
    table_name,
    index_name,
    status
FROM user_constraints
WHERE constraint_type IN ('P', 'U')
ORDER BY table_name, constraint_name;
~~~

Primary key and unique constraints may be backed by unique indexes in Oracle. Do not drop an index used by a constraint without understanding the impact on the constraint.

### 13.4. Gathering statistics

In a lab schema, you can gather statistics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS_LAB',
        cascade => TRUE
    );
END;
/
~~~

`CASCADE` collects statistics for the associated indexes as well. In production, stats gathering must follow DBA policy, maintenance windows, and workload considerations. Statistics can change execution plans for many SQL statements.

## 14. Reading Execution Plans to Verify Index Benefit

### 14.1. EXPLAIN PLAN

~~~sql
EXPLAIN PLAN FOR
SELECT order_id, customer_id, order_date
FROM orders_lab
WHERE customer_id = 100
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

The estimated plan may show `INDEX RANGE SCAN` and `TABLE ACCESS BY INDEX ROWID`, or `FULL TABLE SCAN` if the optimizer estimates that approach is cheaper.

### 14.2. Actual plan with runtime statistics

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id, customer_id, order_date
FROM orders_lab
WHERE customer_id = 100
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Check:

| Field | Meaning |
| --- | --- |
| Operation | Access path and how data is combined |
| E-Rows | Optimizer's estimated row count |
| A-Rows | Actual row count when runtime statistics are collected |
| Starts | Number of times the operation executed |
| Buffers | Logical I/O |
| A-Time | Elapsed time recorded for the operation |
| Predicate Information | Access/filter predicates |

### 14.3. Access predicates and filter predicates

Access predicates help locate the range to read from an index or table. Filter predicates are applied to discard rows after they have been accessed. A condition can be an access predicate at one operation and a filter predicate at another.

When reviewing a plan, check:

- Which columns are used to locate the index range?
- Which predicates are only evaluated after reading a leaf or table row?
- How many ROWIDs are retrieved?
- Are there many `TABLE ACCESS BY INDEX ROWID` operations?
- Are the buffers for index and table access reasonable?
- Are estimated rows close to actual rows?

### 14.4. An index scan can cost more than a full table scan

Example query:

~~~sql
SELECT *
FROM orders_lab
WHERE status = 'ACTIVE';
~~~

If 95% of orders have status `ACTIVE` and `SELECT *` needs many columns, an index on `STATUS` could force Oracle to retrieve ROWIDs for most of the table and read many table blocks. A full table scan can be cheaper.

Do not force an index with hints just because the index exists. If you need to test an alternative, use a hint in a test environment and compare actual metrics; then diagnose why the optimizer chose its plan.

### 14.5. COST is not elapsed time

`COST` is an internal optimizer estimate used to compare candidate plans. It is not milliseconds, seconds, or an exact count of physical blocks that will be read. Look at actual rows, buffers, elapsed time, I/O, and workload when benchmarking.

## 15. Hands-on Lab: Creating and Observing B-tree Indexes

### 15.1. Create the lab table

~~~sql
CREATE TABLE orders_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date DATE NOT NULL,
    status VARCHAR2(12 CHAR) NOT NULL,
    total_amount NUMBER(12,2) NOT NULL
);
~~~

The primary key creates or uses a suitable unique index to enforce `ORDER_ID`.

### 15.2. Load sample data

~~~sql
INSERT INTO orders_lab
SELECT
    LEVEL AS order_id,
    MOD(LEVEL, 100) + 1 AS customer_id,
    DATE '2026-01-01' + MOD(LEVEL, 180) AS order_date,
    CASE
        WHEN MOD(LEVEL, 10) = 0 THEN 'CLOSED'
        ELSE 'ACTIVE'
    END AS status,
    100 + MOD(LEVEL, 500) AS total_amount
FROM dual
CONNECT BY LEVEL <= 10000;

COMMIT;
~~~

### 15.3. Create a composite index

~~~sql
CREATE INDEX ix_orders_customer_date_lab
ON orders_lab(customer_id, order_date);
~~~

### 15.4. Gather statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS_LAB',
        cascade => TRUE
    );
END;
/
~~~

### 15.5. Query by leading prefix and range

~~~sql
SELECT order_id, customer_id, order_date
FROM orders_lab
WHERE customer_id = 25
  AND order_date >= DATE '2026-03-01'
  AND order_date < DATE '2026-04-01'
ORDER BY order_date;
~~~

Check the plan to see whether Oracle chooses `INDEX RANGE SCAN` on the composite index. Because the lab dataset is small, the optimizer may still choose a table scan; that does not mean the index is wrong.

### 15.6. Query by the second column only

~~~sql
SELECT order_id, order_date
FROM orders_lab
WHERE order_date >= DATE '2026-03-01'
  AND order_date < DATE '2026-04-01';
~~~

Compare the plan with the previous query. Because the index starts with `CUSTOMER_ID`, a predicate on `ORDER_DATE` alone lacks the leading prefix; the optimizer may choose a table scan or a different access path. Try adding a separate index on `ORDER_DATE` in the lab environment, gather statistics, and compare buffers and actual rows:

~~~sql
CREATE INDEX ix_orders_date_lab
ON orders_lab(order_date);
~~~

### 15.7. Compare function predicate and range predicate

~~~sql
-- Predicate applying a function to the column.
SELECT COUNT(*)
FROM orders_lab
WHERE TRUNC(order_date) = DATE '2026-03-15';

-- Range predicate.
SELECT COUNT(*)
FROM orders_lab
WHERE order_date >= DATE '2026-03-15'
  AND order_date < DATE '2026-03-16';
~~~

Both queries have the same meaning for a `DATE` column in this example. Compare their plans and consider a function-based index if the `TRUNC` query is an important pattern.

### 15.8. Inspect metadata

~~~sql
SELECT index_name, index_type, uniqueness, blevel,
       leaf_blocks, distinct_keys, clustering_factor
FROM user_indexes
WHERE table_name = 'ORDERS_LAB'
ORDER BY index_name;

SELECT index_name, column_position, column_name, descend
FROM user_ind_columns
WHERE table_name = 'ORDERS_LAB'
ORDER BY index_name, column_position;
~~~

### 15.9. Clean up the lab table (optional)

Run only when you are sure this is the lab table you created and you no longer need the data:

~~~sql
DROP TABLE orders_lab PURGE;
~~~

`DROP TABLE` is DDL and issues an implicit commit according to Oracle rules. Do not run it on real business tables.

## 16. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| A B-tree is a binary tree | It is a multi-way search tree organized by database blocks |
| Indexes store entire table rows | Leaf entries primarily store keys and ROWIDs |
| Having an index always makes queries fast | Selectivity, clustering factor, columns needed, and table access cost determine performance |
| INDEX RANGE SCAN always reads only one row | It can read a range spanning many entries |
| INDEX FULL SCAN and FAST FULL SCAN are the same | Full scan follows key order; fast full scan does not guarantee order |
| The second column of a composite index can never be used | Skip scan or full index access can use it, though the leading prefix is usually important |
| All NULLs are stored in a single-column B-tree index | Entries where the entire key is NULL are not stored in a standard B-tree |
| ROWID is a stable business key | ROWID is a physical/logical row locator that can change when rows move |
| Adding indexes does not affect INSERT | Every relevant index must be maintained |
| Rebuilding an index always makes queries faster | Rebuild only when there is a specific reason and concrete evidence |
| Lower COST definitely means faster | COST is an optimizer estimate, not elapsed time |
| Index scan is always better than full table scan | Reading most of a table can be cheaper than table lookups via an index |

## 17. B-tree Index Design Principles

When considering a new index:

1. Identify the SQL statements and workload to support.
2. Identify equality, range, join, and `ORDER BY` predicates.
3. Choose leading columns based on critical access patterns.
4. Check whether returned columns can be satisfied from the index or require table access.
5. Estimate selectivity and expected number of ROWIDs.
6. Check clustering factor and table/index sizes.
7. Consider `INSERT`/`UPDATE`/`DELETE` overhead.
8. Gather appropriate statistics.
9. Inspect actual execution plans and buffers.
10. Keep the index when overall workload benefit outweighs maintenance cost.

### 17.1. Avoid redundant indexes

An index `(CUSTOMER_ID, ORDER_DATE)` already has the leading prefix `CUSTOMER_ID`. A single-column index on `CUSTOMER_ID` may be redundant unless there is another reason such as different compression, uniqueness, partitioning, or workload behavior. Before adding an index, review existing indexes and the SQL statements using them.

### 17.2. Do not rebuild on a schedule without reason

B-tree indexes are maintained automatically by Oracle. Leaf block splits do not automatically mean an index is broken or needs rebuilding. Rebuilds consume I/O, TEMP, redo, time, and resources; they can also increase system load.

Consider `REBUILD`/`COALESCE` only when there is evidence regarding segment state, query effectiveness, administrative requirements, or sound DBA guidance. Understand the difference between `REBUILD` and `COALESCE`, online vs. offline modes, and locking/space impacts.

### 17.3. Indexes do not replace constraints

An index can back a primary key or unique constraint, but a nonunique index does not enforce uniqueness. If the business requires uniqueness, declare a `PRIMARY KEY`/`UNIQUE` constraint rather than merely creating an index and hoping the application always checks before `INSERT`.

## 18. Self-Check Questions

1. What are the conceptual block levels in an Oracle B-tree index?
2. What are root and branch blocks used for?
3. What information does a leaf entry normally contain?
4. Why should ROWID not be used as a business key?
5. When is `INDEX UNIQUE SCAN` appropriate?
6. How does `INDEX RANGE SCAN` differ from `INDEX FULL SCAN`?
7. Does `INDEX FAST FULL SCAN` guarantee key order?
8. In what composite index scenario can skip scan be useful?
9. How does the leading column affect range lookup capability?
10. Why might an index scan require `TABLE ACCESS BY INDEX ROWID`?
11. What does index-only access mean?
12. How do selectivity and cardinality differ?
13. What does clustering factor describe?
14. When can a full table scan be cheaper than an index range scan?
15. How does a single-column B-tree index handle rows with `NULL` values?
16. Why can a function on a column make a standard index hard to use?
17. What query pattern does a function-based index support?
18. When does a leaf block split occur?
19. Does updating a column not in an index require updating that index?
20. Why do many indexes make `INSERT`/`UPDATE`/`DELETE` more expensive?
21. What is the trade-off of a reverse key index?
22. Where can `BLEVEL` and `LEAF_BLOCKS` be viewed?
23. Why should `A-Rows` be compared with `E-Rows`?
24. Is `COST` equal to execution time?
25. Why should indexes not be rebuilt purely on a schedule?

**Answer hints:**

1. Root, branch, and leaf; small indexes can combine root with the leaf level.
2. Choosing branches and navigating to the leaf block containing the key.
3. Key value and the row's ROWID.
4. ROWID is a locator that can change when rows are moved or reorganized.
5. When equality fully specifies a unique key.
6. Range scan reads a range of keys; full scan reads all leaves in index order.
7. No.
8. When the leading column is missing, has few distinct values, and cost is favorable.
9. The leading prefix locates the key range; without it, another access path may be needed.
10. Because the index usually only stores keys/ROWIDs, while other columns reside in table blocks.
11. The query obtains all required columns from the index and can avoid table access.
12. Selectivity is the filtering ratio; cardinality is the estimated or actual row count.
13. The correlation between index key order and row positions in table blocks.
14. When the predicate returns most of the table or table lookups via ROWID are too expensive.
15. Entries where the entire key is `NULL` are not stored in a standard B-tree.
16. Because the index is sorted by base column values, not function results.
17. When queries frequently use the same indexed expression.
18. When a leaf block lacks space for a new entry in key order.
19. Usually no, provided it does not change the key or an indexed expression.
20. Every affected index must be maintained and generate corresponding redo/undo.
21. Reduces insert contention on the trailing leaf, but loses standard range scan capability on original keys.
22. `USER_INDEXES` or `ALL_INDEXES`/`DBA_INDEXES`.
23. To spot cardinality estimation errors and understand the runtime plan.
24. No, cost is an internal optimizer estimate.
25. Because rebuilding consumes resources and not every split or fragmentation slows down an index.

## Oracle Reference Documentation

- [Oracle Database Concepts — Schema Objects: Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/indexes-and-index-organized-tables.html): index concepts and data organization.
- [Oracle Database Administrator's Guide — Managing Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-indexes.html): creating, managing, and maintaining indexes.
- [Oracle Database SQL Language Reference — CREATE INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html): index syntax, composite, descending, compression, and function-based indexes.
- [Oracle Database Reference — USER_INDEXES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_INDEXES.html): index metadata and statistics.
- [Oracle Database Reference — USER_IND_COLUMNS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_IND_COLUMNS.html): index column order and attributes.
- [Oracle Database SQL Tuning Guide — Access Paths](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-access-paths.html): index scans and access paths.
- [Oracle Database SQL Tuning Guide — Optimizer Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html): optimizer statistics, cardinality, and selectivity.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html): gathering and managing optimizer statistics.

**Key takeaway:** A B-tree index is a balanced multi-way search tree in which root and branch blocks lead to leaf entries containing keys and ROWIDs. An index helps Oracle locate a key range quickly, but the ultimate benefit depends on the number of rows to read, table block locality, returned columns, and index maintenance overhead during writes. Design around leading predicates and workload, then confirm with actual execution plans and runtime statistics.
