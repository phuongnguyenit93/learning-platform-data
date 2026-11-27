# TABLE ACCESS FULL, BY INDEX ROWID, and Index Access Paths

## 1. What Is an Access Path in an Execution Plan?

Oracle Database uses the Cost-Based Optimizer (CBO) to choose how to read data for each table or partition in a SQL statement. The method Oracle uses to locate and retrieve rows from an object is called an **access path**.

In an execution plan, access paths are typically represented by operations such as:

- `TABLE ACCESS FULL`: reads table blocks via a full scan.
- `INDEX UNIQUE SCAN`, `INDEX RANGE SCAN`, `INDEX SKIP SCAN`: locates matching entries in a B-tree index.
- `TABLE ACCESS BY INDEX ROWID`: uses ROWIDs to fetch the corresponding rows from the table after finding entries in an index.
- `INDEX FULL SCAN`, `INDEX FAST FULL SCAN`: reads the entire index in different ways.
- `BITMAP INDEX ...`: operates on bitmap indexes, commonly seen in analytical workloads.

An access path is part of an execution plan, not a separate SQL command or a type of index. The optimizer chooses an access path based on statistics, query predicates, table/index structure, and estimated cost. The same SQL statement can receive different plans when data, statistics, bind values, or the execution environment change.

## 2. TABLE ACCESS FULL

### 2.1. How Does Oracle Perform a Full Table Scan?

`TABLE ACCESS FULL` indicates that Oracle reads data directly from the table's blocks rather than looking up ROWIDs through a B-tree index. For a heap table, a full scan reads the segment's formatted blocks below the high water mark (HWM), then applies filter conditions to determine which rows to return.

Example:

```sql
SELECT order_id, customer_id, order_date, amount
FROM orders
WHERE order_date >= DATE '2026-01-01';
```

If the condition returns a large portion of the rows in `ORDERS`, the optimizer may choose a full scan. In that case, the execution plan may contain the operation:

```text
TABLE ACCESS FULL  ORDERS
```

Oracle can read multiple consecutive blocks using multiblock I/O. For queries requiring a large percentage of the data, reading blocks sequentially is often more efficient than looking up individual index entries and returning to the table to read scattered blocks one by one.

For partitioned tables, partition pruning can eliminate irrelevant partitions before access. Thus, `TABLE ACCESS FULL` on selected partitions does not necessarily mean Oracle reads all data across every partition in the table.

### 2.2. When Is a Full Scan a Good Choice?

A full scan is often reasonable in the following situations:

- The table is small; the cost of reading the whole table is lower than going through an index.
- The query needs most of the rows in the table.
- The filter condition has low selectivity, meaning matching rows account for a large share.
- The query needs many columns while an index contains only a small subset of them; using the index would require many table lookups.
- ROWIDs in the index are scattered across many table blocks, causing index-based row retrieval to incur many block reads.
- Analytical or batch queries can leverage multiblock I/O and parallel execution.

Do not conclude that `TABLE ACCESS FULL` is bad merely because the operation name contains `FULL`. A full scan can be the lowest-cost access path. Forcing Oracle to use an index when a query needs many rows can sometimes make the query slower.

### 2.3. Filter Conditions in a Full Scan

A full scan reads blocks and discards rows that do not satisfy the predicate. In the Predicate Information section of the execution plan, the condition may appear as `filter`:

```text
filter("ORDER_DATE">=DATE '2026-01-01')
```

A filter condition does not mean Oracle found an index access path. It indicates that the condition is evaluated against the rows processed by the operation.

## 3. B-Tree Indexes and ROWIDs

### 3.1. What Does an Index Store?

A B-tree index is a balanced tree structure consisting of a root block, branch blocks, and leaf blocks. Leaf entries are ordered by the index key; for a standard B-tree index on a heap table, each entry stores the key value and the ROWID of the corresponding row.

Example:

```sql
CREATE INDEX ix_orders_customer_date
    ON orders(customer_id, order_date);
```

This index is ordered by `CUSTOMER_ID`, and then by `ORDER_DATE` within each customer value. When a query has predicates matching the leading portion of the key, Oracle can traverse from the root/branch blocks to the leaf range containing the target entries.

### 3.2. What Is a ROWID?

A ROWID is an address used to locate a row in a table. For a heap table, an extended ROWID represents physical location metadata such as the data object, file, block, and row slot within the block. Once an index returns a ROWID, Oracle can use that address to read the table block containing the corresponding row.

A ROWID is not a business key like `ORDER_ID`. It is physical location metadata managed by Oracle. Do not store ROWIDs as permanent identifiers in an application, because operations that move or reorganize data can change physical addresses.

### 3.3. Why Do Indexes Often Appear Alongside TABLE ACCESS BY INDEX ROWID?

An index contains only its key columns and location metadata. If the SQL query requests additional columns not present in the index, Oracle must fetch the actual row from the table.

Example:

```sql
SELECT order_id, customer_id, order_date, amount, status
FROM orders
WHERE customer_id = :customer_id
  AND order_date >= DATE '2026-01-01';
```

With index `(CUSTOMER_ID, ORDER_DATE)`, Oracle can locate matching entries via `INDEX RANGE SCAN`. However, `ORDER_ID`, `AMOUNT`, and `STATUS` are not in the index, so Oracle must fetch the data from the table by ROWID.

An illustrative execution plan:

```text
SELECT STATEMENT
  TABLE ACCESS BY INDEX ROWID  ORDERS
    INDEX RANGE SCAN           IX_ORDERS_CUSTOMER_DATE
```

Read the plan tree bottom-up to follow the data flow: `INDEX RANGE SCAN` finds matching entries and returns ROWIDs; `TABLE ACCESS BY INDEX ROWID` uses those ROWIDs to read rows from `ORDERS`.

### 3.4. TABLE ACCESS BY INDEX ROWID BATCHED

A variant that may appear is:

```text
TABLE ACCESS BY INDEX ROWID BATCHED  ORDERS
```

Oracle collects a batch of ROWIDs and sorts or organizes reads by block to reduce scattered table block accesses. Batching can improve I/O locality when many ROWIDs point to different blocks.

`BATCHED` does not mean SQL output is guaranteed to be ordered by ROWID or by index order. If the application requires ordered results, the SQL statement must still include an appropriate `ORDER BY`.

For partitioned tables and global indexes, the plan may also display operations such as `TABLE ACCESS BY GLOBAL INDEX ROWID`. When reading a plan, inspect the full operation name to recognize the access type and its relationship to partitions.

## 4. B-Tree Index Access Paths

### 4.1. INDEX UNIQUE SCAN

`INDEX UNIQUE SCAN` looks up a single entry in a unique index using equality conditions on the entire unique key. If the key is a single column:

```sql
SELECT order_id
FROM orders
WHERE order_id = :order_id;
```

and `ORDER_ID` has a unique index or is a primary key, Oracle can use `INDEX UNIQUE SCAN`.

For a unique composite index on `(A, B)`, to uniquely identify one entry this way, predicates must supply equality values for all key columns. If there is only a condition on `A`, Oracle typically must scan a range rather than perform a unique lookup.

A unique scan yields at most one index entry. If the query needs columns not stored in the index, the plan will still have `TABLE ACCESS BY INDEX ROWID` above it to read the table row.

### 4.2. INDEX RANGE SCAN

`INDEX RANGE SCAN` searches a range of entries in an index. It commonly appears with:

- Equality predicates on a non-unique index key.
- Equality predicates on the leading portion of a composite index.
- Range predicates such as `>`, `>=`, `<`, `<=`, or `BETWEEN` on the column following the equality prefix.

Example:

```sql
SELECT order_id, order_date
FROM orders
WHERE customer_id = :customer_id
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2027-01-01';
```

With index `(CUSTOMER_ID, ORDER_DATE)`, Oracle can locate the leaf region corresponding to a `CUSTOMER_ID`, then read the `ORDER_DATE` range within that region.

A range scan can return one or many ROWIDs. How many entries must be read depends on predicate selectivity and data distribution. A range scan does not automatically guarantee the entire SQL query has the desired order; index ordering can avoid a sort only when the columns, sort directions, and query conditions align.

### 4.3. INDEX RANGE SCAN DESCENDING

`INDEX RANGE SCAN DESCENDING` reads an index range in reverse order. Oracle can use this access path when a query needs descending order matching the index key, for example:

```sql
SELECT order_id, order_date
FROM orders
WHERE customer_id = :customer_id
ORDER BY order_date DESC;
```

Whether a `SORT ORDER BY` operation can be avoided depends on the overall index structure, predicates, and sort directions. Always verify the execution plan rather than inferring from a single line of SQL.

### 4.4. INDEX SKIP SCAN

Composite indexes are organized in column order. An index `(A, B)` is typically most useful when a query has a predicate on the leading column `A`. Nevertheless, Oracle can sometimes still use the index when a query filters only on `B`, via `INDEX SKIP SCAN`.

Example index:

```sql
CREATE INDEX ix_orders_status_customer
    ON orders(status, customer_id);
```

Query:

```sql
SELECT order_id
FROM orders
WHERE customer_id = :customer_id;
```

Oracle can treat the index as multiple logical sub-indexes, one per distinct `STATUS` value, and search for `CUSTOMER_ID` within each sub-index. This can be helpful when the leading column has low cardinality (few distinct values).

Skip scan is not a default substitute for an index with the right column order. If the leading column has many distinct values, probing across numerous logical ranges can be expensive. When a workload frequently filters by `CUSTOMER_ID`, an index leading with `CUSTOMER_ID` may be more appropriate.

### 4.5. INDEX FULL SCAN

`INDEX FULL SCAN` reads all leaf entries of an index in key order. Oracle may choose this access path when:

- The query only needs columns available in the index.
- Reading the index is smaller or cheaper than reading the entire table.
- The index order satisfies a sorting requirement, avoiding a separate sort step.

Example:

```sql
SELECT customer_id, order_date
FROM orders
ORDER BY customer_id, order_date;
```

If index `(CUSTOMER_ID, ORDER_DATE)` is eligible and contains all required columns, Oracle can read the index in order to return results. When all needed data is already in the index, `TABLE ACCESS BY INDEX ROWID` is unnecessary.

### 4.6. INDEX FAST FULL SCAN

`INDEX FAST FULL SCAN` reads all blocks of the index much like scanning a table segment, typically using multiblock I/O. It does not preserve index key order in the output.

This access path is useful when a query needs all data from a sufficiently narrow index and does not require index ordering. For example, if a query only needs columns already present in the index, Oracle can scan the index instead of the table:

```sql
SELECT COUNT(*)
FROM orders;
```

The optimizer may pick a suitable index to obtain the needed information, though the actual choice depends on statistics and cost. `INDEX FAST FULL SCAN` is not synonymous with `INDEX FULL SCAN`: fast full scan prioritizes efficient block scanning without guaranteeing key order, whereas full scan follows index order.

### 4.7. Summary of B-Tree Index Scans

| Operation | Purpose | Key Characteristics |
|---|---|---|
| `INDEX UNIQUE SCAN` | Look up one entry by full unique key | At most one entry |
| `INDEX RANGE SCAN` | Search a range of entries | Can return multiple entries/ROWIDs |
| `INDEX RANGE SCAN DESCENDING` | Read a range in reverse order | Can support matching descending order |
| `INDEX SKIP SCAN` | Search on a non-leading column of a composite index | Probes logical ranges per leading column value |
| `INDEX FULL SCAN` | Read the entire index in key order | Can support `ORDER BY` and index-only access |
| `INDEX FAST FULL SCAN` | Read all index blocks | Multiblock I/O; does not guarantee key order |

## 5. Index-Only Access and Other Index Types

### 5.1. When Is TABLE ACCESS BY INDEX ROWID Not Needed?

If an index contains all columns required for predicates and output, Oracle can satisfy the query using only the index. Example:

```sql
SELECT customer_id, order_date
FROM orders
WHERE customer_id = :customer_id;
```

With index `(CUSTOMER_ID, ORDER_DATE)`, the returned values are already in the index. The plan may need only `INDEX RANGE SCAN` without revisiting the table.

This is often called index-only access or covering access. The benefit is avoiding table block reads via ROWID. However, adding too many columns to an index to cover every query enlarges the index and increases write, update, and storage overhead. Balance read workloads against write workloads.

### 5.2. Bitmap Indexes

A bitmap index stores information indicating which rows match a key value in bitmap form. Oracle can combine multiple bitmaps using operations like `BITMAP AND` or `BITMAP OR`, then convert the resulting bitmap into ROWIDs to read the table.

An illustrative plan might contain:

```text
TABLE ACCESS BY INDEX ROWID  ORDERS
  BITMAP CONVERSION TO ROWIDS
    BITMAP AND
      BITMAP INDEX SINGLE VALUE  IX_ORDERS_STATUS_BM
      BITMAP INDEX SINGLE VALUE  IX_ORDERS_REGION_BM
```

Bitmap indexes are typically suited for data warehouse or analytical workloads where predicates combine low-cardinality columns. In OLTP workloads with heavy concurrent DML updates, bitmap indexes can cause broader lock granularity and hurt concurrency; evaluate carefully before applying them.

### 5.3. Function-Based Indexes

When a query filters on an expression, an index built on that exact expression may be required:

```sql
CREATE INDEX ix_customers_upper_email
    ON customers(UPPER(email));

SELECT customer_id
FROM customers
WHERE UPPER(email) = :email;
```

A function-based index creates an access path over the expression's output. The predicate must match the indexed expression for the optimizer to use it. Statistics on the expression and on the index serve different roles: statistics aid cardinality estimation, while the index provides the access path.

## 6. Why Does Oracle Choose a Full Scan or Index Access?

The optimizer estimates the cost of candidate plans. There is no single fixed selectivity threshold across all tables that dictates when an index is used. Key factors include:

### 6.1. Selectivity and Cardinality

**Selectivity** reflects the fraction of rows matching a predicate; **cardinality** is the estimated number of rows at an operation. The more selective a predicate is, the better chance an index has to reduce data read. Still, an index scan with good selectivity can be expensive if the ROWIDs point to many distinct blocks.

If the optimizer misestimates cardinality, it can pick an unsuitable access path. Check statistics and extended statistics when columns are correlated or predicates involve expressions.

### 6.2. Clustering Factor

Clustering factor describes how closely the order of ROWIDs in an index matches the physical order of rows in table blocks. Roughly speaking:

- Low clustering factor, close to the number of table blocks: consecutive ROWIDs in the index tend to point to fewer repeated blocks.
- High clustering factor, close to the number of table rows: consecutive ROWIDs tend to be scattered across many blocks.

When the clustering factor is high, an index range scan may have to read many separate table blocks. If a predicate returns many rows, a full scan can be cheaper.

### 6.3. Table and Index Size

An index significantly smaller than the table can be an efficient read path, especially when the query only needs indexed columns. Conversely, if a query needs many columns and many rows, reading the index and then visiting the table can generate more I/O than a full scan.

### 6.4. Other Factors

The optimizer also considers:

- Table block count and row count, index leaf blocks, and index height.
- Histograms and data distribution skew.
- Number of columns the query reads and potential for index-only access.
- Partition pruning and local/global index type.
- System statistics, I/O model, parallel degree, and environment attributes.
- Whether a predicate can serve as an index access condition or only filter rows after retrieval.

Therefore, do not evaluate a plan with simplistic rules such as "if an index exists, it must be used" or "full scan is always slow." Examine actual row counts, blocks read, and the query's goal.

## 7. ACCESS Predicates and FILTER Predicates

In the Predicate Information section of an execution plan, Oracle distinguishes between conditions used to access data and conditions used to filter rows already retrieved:

- `access(...)`: conditions used to pinpoint the index range or access scope of the operation.
- `filter(...)`: conditions evaluated against rows received or read by the operation.

Example with index `(CUSTOMER_ID, ORDER_DATE)`:

```sql
SELECT order_id, amount
FROM orders
WHERE customer_id = :customer_id
  AND order_date >= DATE '2026-01-01'
  AND status = 'SHIPPED';
```

The optimizer can use `CUSTOMER_ID` and `ORDER_DATE` to seek a range in the index. If `STATUS` is not in the index, `STATUS = 'SHIPPED'` may be evaluated after Oracle fetches rows from the table. In that case, the plan can show `access` on the two index columns and `filter` on `STATUS`.

Distinguishing these two predicate types reveals how much the index narrows the search and how many rows Oracle reads before filtering further. However, not every operation has both predicate types; always read them in the context of the specific operation.

## 8. Reading and Verifying Access Paths with DBMS_XPLAN

### 8.1. Getting an Execution Plan with Runtime Metrics

You can use the `GATHER_PLAN_STATISTICS` hint to collect runtime metrics for the cursor:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id, customer_id, order_date, amount
FROM orders
WHERE customer_id = :customer_id
  AND order_date >= DATE '2026-01-01';
```

Immediately after running the SQL, inspect the executed cursor:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL,
    NULL,
    'ALLSTATS LAST +PREDICATE +ALIAS'
  )
);
```

`ALLSTATS LAST` displays runtime statistics for the most recent execution when row-source statistics were collected. Without the hint or corresponding statistics-gathering configuration, actual columns may not appear in full.

### 8.2. Columns to Observe

| Column | Meaning |
|---|---|
| `Operation` / `Name` | Operation type and accessed object |
| `E-Rows` | Rows estimated by the optimizer |
| `A-Rows` | Actual rows returned by the operation |
| `Starts` | Number of times the operation started |
| `Buffers` | Recorded logical reads (buffer gets) |
| `Reads` | Recorded physical reads |
| `A-Time` | Actual time recorded for the operation |

When evaluating an access path, compare `E-Rows` and `A-Rows` first. Large discrepancies can cause upper operations in the plan tree to receive inputs very different from projections. Next, examine `Buffers`, `Reads`, `Starts`, and elapsed time to understand actual resource cost.

Do not mechanically sum times across all operation rows, because parent node times can include child node times. Treat the plan as a data-processing tree and read metrics according to parent-child relationships.

### 8.3. EXPLAIN PLAN and DISPLAY_CURSOR

`EXPLAIN PLAN` shows the plan the optimizer projects for a SQL statement in the explain context. It does not execute the SQL to collect actual metrics. Bind values, session settings, and environment differences can make an explain plan differ from the cursor that actually runs.

`DBMS_XPLAN.DISPLAY_CURSOR` reads a cursor's plan from the shared SQL area and can display runtime statistics if collected. When troubleshooting performance issues, prioritize the actual cursor's plan along with its corresponding bind values and execution conditions.

## 9. Example Comparing Two Access Paths

Suppose `ORDERS` has millions of rows and has an index:

```sql
CREATE INDEX ix_orders_customer_date
    ON orders(customer_id, order_date);
```

### Highly Selective Query

```sql
SELECT order_id, amount
FROM orders
WHERE customer_id = 90001
  AND order_date >= DATE '2026-11-01'
  AND order_date <  DATE '2026-11-08';
```

If only a few rows match, the optimizer may choose:

```text
SELECT STATEMENT
  TABLE ACCESS BY INDEX ROWID  ORDERS
    INDEX RANGE SCAN           IX_ORDERS_CUSTOMER_DATE
```

The index narrows the search range; ROWID fetches `ORDER_ID` and `AMOUNT` from the table. If the index covers all needed columns, the table access operation may no longer be needed.

### Query Needing Most of the Table

```sql
SELECT order_id, customer_id, order_date, amount, status
FROM orders
WHERE order_date >= DATE '2020-01-01';
```

If the condition returns most of the rows, an index could cause excessive table block accesses and require reading many columns absent from the index. The optimizer may choose:

```text
SELECT STATEMENT
  TABLE ACCESS FULL  ORDERS
```

The two plans above only illustrate how operations can appear; they are not fixed plans for every database. The actual choice depends on data, statistics, configuration, and optimizer-computed cost.

## 10. Workflow for Analyzing and Improving Access Paths

When encountering a slow query, follow this workflow:

1. Obtain the actual SQL, bind values, and execution plan of the cursor that ran.
2. Use runtime statistics to identify operations with large discrepancies between `E-Rows` and `A-Rows`.
3. Determine whether the query needs few rows or many rows; check which predicates are `access` and which are `filter`.
4. Check existing indexes, composite index column order, columns the query reads, and index-only access potential.
5. Check clustering factor, leaf blocks, histograms, freshness of table/index statistics, and partition pruning eligibility.
6. Compare logical reads, physical reads, and elapsed time across alternatives on a representative workload.
7. Only modify indexes, statistics, or SQL with evidence of the root cause; after making changes, re-run and verify the actual plan.

Avoid adding an index solely because you see `TABLE ACCESS FULL`, and avoid forcing `INDEX` or `FULL` via hints before understanding the costs. Every new index adds storage footprint and maintenance overhead during inserts, updates, and deletes. A good access path is one whose cost matches the workload and query requirements.

## Oracle References

- [Oracle Database 19c SQL Tuning Guide — Optimizer Access Paths](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-access-paths.html)
- [Oracle Database 19c SQL Tuning Guide — Generating and Displaying Execution Plans](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/generating-and-displaying-execution-plans.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html)
- [Oracle Database 19c Concepts — Indexes and Index-Organized Tables](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/indexes-and-index-organized-tables.html)
