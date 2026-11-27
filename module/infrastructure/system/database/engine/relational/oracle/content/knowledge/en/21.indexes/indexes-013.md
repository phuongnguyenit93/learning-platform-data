# Covering Indexes, Read/Write Trade-offs, and Avoiding Redundant Indexes in Oracle

## 1. Why Are Covering Indexes Needed?

An index helps Oracle locate matching rows without scanning the entire table in many cases. However, a query can find ROWIDs through an index and still have to read additional table blocks to retrieve columns to display. If the workload repeats that query across large amounts of data, those ROWID table lookups can generate significant extra I/O and logical reads.

A **covering index** is an index that contains all columns a query needs for filtering, joining, sorting, and returning results. When conditions and costs allow, Oracle can answer the query directly from the index without visiting table blocks for every ROWID. In execution plans, this is commonly called *index-only access*.

For example, an application frequently runs:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND order_date >= :from_date
  AND order_date <  :to_date
ORDER BY order_date, order_id;
```

An index containing only `(customer_id, status, order_date)` can locate matching orders quickly, but `ORDER_ID` and `TOTAL_AMOUNT` are not in the index. Oracle may have to access the table to retrieve those two columns. A wider index:

```sql
CREATE INDEX ix_orders_customer_paid_cover
ON orders (
    customer_id,
    status,
    order_date,
    order_id,
    total_amount
);
```

contains all columns needed by that query. If the optimizer picks the index and other conditions permit, the query can execute via an index range scan without `TABLE ACCESS BY INDEX ROWID`.

Covering indexes lower read costs in some workloads, yet make indexes larger and raise `INSERT`, `UPDATE`, and `DELETE` costs. Thus, the goal is picking indexes that benefit critical queries without turning every index into a wide copy of the table.

This lesson belongs to the **Indexes** chapter and covers index-only access in Oracle, designing composite B-tree indexes around predicates and projections, the impact of column ordering, handling `NULL`s, read-versus-write trade-offs, spotting duplicate or redundant indexes, reading execution plans, and the evaluation workflow before adding or dropping indexes.

## 2. How Do Standard Indexes and Covering Indexes Differ?

### 2.1. Standard indexes locate ROWIDs

A standard B-tree index stores key values and ROWID information so Oracle can pinpoint rows in the table. Example:

```sql
CREATE INDEX ix_orders_customer
ON orders (customer_id);
```

Query:

```sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE customer_id = :customer_id;
```

Index `IX_ORDERS_CUSTOMER` helps Oracle find ROWIDs matching `CUSTOMER_ID`. However, the index lacks `ORDER_ID`, `ORDER_DATE`, and `TOTAL_AMOUNT`, so Oracle must access the table to fetch those values.

The execution plan may look like:

```text
SELECT STATEMENT
  TABLE ACCESS BY INDEX ROWID  ORDERS
    INDEX RANGE SCAN           IX_ORDERS_CUSTOMER
```

`INDEX RANGE SCAN` locates matching entries; `TABLE ACCESS BY INDEX ROWID` reads table rows using the discovered ROWIDs.

### 2.2. Covering indexes contain the columns the query needs

If the index holds every column required by the query, Oracle can return values directly from the index:

```sql
CREATE INDEX ix_orders_customer_cover
ON orders (
    customer_id,
    order_id,
    order_date,
    total_amount
);
```

Query:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id;
```

All filtered and displayed columns sit inside the index. The optimizer can choose an index-only path depending on statistics, selectivity, and estimated cost.

The execution plan may simplify to:

```text
SELECT STATEMENT
  INDEX RANGE SCAN  IX_ORDERS_CUSTOMER_COVER
```

This is the index-only access pattern typically meant when discussing covering indexes in Oracle.

### 2.3. ROWID does not substitute for column values

An index entry contains a ROWID to locate a row, but that does not mean Oracle can extract every column of the row from the ROWID alone. If `SELECT` needs `TOTAL_AMOUNT` and the index does not store `TOTAL_AMOUNT`, Oracle must still read the table block.

Similarly, if a query selects primary key `ORDER_ID`, do not assume an index on `CUSTOMER_ID` automatically holds primary key values. A B-tree index stores its declared key columns plus ROWID; to return a business column from an index, ensure that column is part of the index key.

## 3. Determining Whether a Query Can Be Covered by an Index

To evaluate, inspect every column used by the query block:

1. **`SELECT` list:** columns returned to the application.
2. **`WHERE`:** columns used to filter rows.
3. **`JOIN`:** columns used to join tables.
4. **`ORDER BY`:** columns used for sorting.
5. **`GROUP BY`:** columns used for grouping.
6. **`HAVING` and expressions:** columns participating in post-group calculations or conditions.

Example:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND order_date >= :from_date
  AND order_date < :to_date
ORDER BY order_date, order_id;
```

Columns to consider:

| Role | Columns |
|---|---|
| `SELECT` | `ORDER_ID`, `ORDER_DATE`, `TOTAL_AMOUNT` |
| `WHERE` | `CUSTOMER_ID`, `STATUS`, `ORDER_DATE` |
| `ORDER BY` | `ORDER_DATE`, `ORDER_ID` |

An index containing all of these columns has the potential to cover the query:

```sql
CREATE INDEX ix_orders_customer_status_date
ON orders (
    customer_id,
    status,
    order_date,
    order_id,
    total_amount
);
```

This is only a candidate. The index may still not be chosen if the query returns most of the table, if a full table scan is cheaper, if statistics are inaccurate, or if data characteristics make the index inefficient.

### 3.1. SELECT * usually defeats covering benefits

```sql
SELECT *
FROM orders
WHERE customer_id = :customer_id;
```

If the table has many columns, an index on a subset of columns cannot supply the full result. Trying to cram every table column into an index just to cover `SELECT *` creates an overly wide index that wastes storage and slows down every write.

For business queries, explicitly select only needed columns instead of `SELECT *`, especially in frequently executed APIs and reports.

### 3.2. Columns inside expressions must also be considered

Example:

```sql
SELECT UPPER(email)
FROM customers
WHERE UPPER(email) = UPPER(:email);
```

A regular index on `EMAIL` will not directly serve `UPPER(EMAIL)` efficiently. You can use a function-based index:

```sql
CREATE INDEX ix_customers_email_upper
ON customers (UPPER(email));
```

The query expression must be compatible with the index expression. If `SELECT` needs only `UPPER(EMAIL)` and the predicate uses the same expression, this index can serve index-only access appropriately.

### 3.3. JOIN columns are also part of access requirements

```sql
SELECT o.order_id,
       o.order_date,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID';
```

A covering index on `ORDERS` cannot provide `CUSTOMER_NAME` because that column belongs to `CUSTOMERS`. Oracle must still access the customers table or another index serving that side of the join. Evaluate covering per table and per query block; never assume one table's index covers data from another table.

## 4. Designing Composite Indexes for Covering Queries

A composite index contains multiple columns in a defined order:

```sql
CREATE INDEX ix_orders_a_b_c
ON orders (a, b, c);
```

Column order is a vital part of the design. Index `(A, B, C)` is not the same as `(B, A, C)`, even though both contain the same set of columns.

### 4.1. Leading column and index usability

With the index:

```sql
CREATE INDEX ix_orders_customer_status_date
ON orders (customer_id, status, order_date);
```

Oracle can use index prefixes to search by:

- `CUSTOMER_ID`.
- `CUSTOMER_ID` and `STATUS`.
- `CUSTOMER_ID`, `STATUS`, and conditions on `ORDER_DATE`.

A query filtering only on `STATUS` without `CUSTOMER_ID` generally cannot leverage a direct prefix range scan like a query with the leading column. Oracle may consider index skip scan under certain data distributions, but you should not design assuming skip scan will always happen.

### 4.2. Equality predicates and range predicates

A helpful starting rule is placing equality-compared columns first, followed by range columns:

```sql
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND order_date >= :from_date
  AND order_date < :to_date
```

Candidate index:

```sql
CREATE INDEX ix_orders_cust_status_date
ON orders (customer_id, status, order_date);
```

`CUSTOMER_ID` and `STATUS` are equality predicates; `ORDER_DATE` is a range predicate. The index narrows the scan region by the two equalities and then scans the date range.

This is a practical rule of thumb, not an absolute formula. If the workload includes other queries, different selectivities, or different sorting needs, column order may change. When multiple columns are equality predicates, choose their order based on common access paths and prefix needs of other queries.

### 4.3. Adding trailing projection columns to cover a query

After choosing the search keys, you can append columns needed only to return results:

```sql
CREATE INDEX ix_orders_cust_status_date_cov
ON orders (
    customer_id,
    status,
    order_date,
    order_id,
    total_amount
);
```

In standard Oracle B-tree indexes, appended columns remain part of the index key. Oracle lacks the `INCLUDE` syntax for non-key payload columns found in some other DBMSs. Consequently, adding columns purely for covering still widens entries, affecting storage, fan-out, and maintenance overhead.

### 4.4. Sort columns and avoiding SORT

If the query has:

```sql
ORDER BY order_date, order_id
```

an index ordered as:

```sql
(customer_id, status, order_date, order_id, total_amount)
```

can supply matching order once `CUSTOMER_ID` and `STATUS` are pinned by equality predicates. Oracle can avoid a separate sort step if the access path and sort directions align.

If `TOTAL_AMOUNT` were placed before `ORDER_ID`, index order after the prefix would become `(ORDER_DATE, TOTAL_AMOUNT, ORDER_ID)`. That no longer directly supplies `(ORDER_DATE, ORDER_ID)` ordering for rows sharing the same date. Therefore, when aiming to both cover and avoid sorting, place sort columns in exact order before projection-only columns.

### 4.5. ASC, DESC, and NULL ordering

Oracle supports specifying sort direction for index columns:

```sql
CREATE INDEX ix_orders_recent
ON orders (customer_id, order_date DESC, order_id);
```

A `DESC` index can help queries requesting the newest dates. However, B-trees can be scanned backward in many cases; do not create a separate `DESC` index solely because you see `ORDER BY ... DESC`. Verify the execution plan and actual ordering, including `NULL` handling.

## 5. End-to-End Covering Index Design Example

Suppose we have table:

```sql
CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    order_date TIMESTAMP NOT NULL,
    total_amount NUMBER(14, 2) NOT NULL,
    sales_channel VARCHAR2(20),
    note VARCHAR2(1000)
);
```

The application frequently retrieves paid orders for a customer within a time window:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND order_date >= :from_date
  AND order_date < :to_date
ORDER BY order_date, order_id;
```

### 5.1. Start with a search index

```sql
CREATE INDEX ix_orders_customer_status_date
ON orders (customer_id, status, order_date);
```

This index supports locating the data region by customer, status, and date range. However, the query also needs `ORDER_ID` and `TOTAL_AMOUNT`, so the plan may require a table lookup.

### 5.2. Inspect the query plan

In a test session, enable runtime statistics:

```sql
ALTER SESSION SET statistics_level = ALL;
```

Run the query:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND order_date >= :from_date
  AND order_date < :to_date
ORDER BY order_date, order_id;
```

After executing in the same session:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

If the plan shows `TABLE ACCESS BY INDEX ROWID` on `ORDERS`, Oracle is reading the table after the index access step. Check actual rows, buffer gets, starts, and predicate information before concluding table lookup is the bottleneck.

### 5.3. Create a candidate covering index

```sql
CREATE INDEX ix_orders_customer_status_date_cov
ON orders (
    customer_id,
    status,
    order_date,
    order_id,
    total_amount
);
```

The new index contains all columns needed by the query. The optimizer may pick:

```text
SELECT STATEMENT
  INDEX RANGE SCAN  IX_ORDERS_CUSTOMER_STATUS_DATE_COV
```

Exact plans depend on statistics, bind values, Oracle version, and data. If the optimizer keeps choosing the old index or a full table scan, that does not mean the new index is wrong; inspect costs and why that access path was chosen.

### 5.4. Do not keep both indexes without workload evidence

After creating the covering index, the older `(CUSTOMER_ID, STATUS, ORDER_DATE)` index may become a prefix of the new one. Do not drop it immediately. The older index may:

- Be narrower and cheaper for queries needing only the three key columns.
- Be used by constraints or other workloads.
- Have different uniqueness, partitioning, or compression properties.
- Support access paths that the wider index does not serve at equivalent cost.

Measure the workload and check dependencies before deciding whether to keep or drop it.

## 6. Index-Only Access Is Not Always Chosen

An index containing enough columns makes covering *possible*, not *mandatory* for Oracle to choose.

The optimizer estimates cost based on:

- Expected rows returned.
- Predicate selectivity and cardinality.
- Number of index blocks to read.
- Number of table blocks to read if table lookup is needed.
- Clustering factor.
- Table/index statistics and histograms.
- Bind values, optimizer settings, and release version.

If the query returns most of the table, a full table scan can be cheaper than scanning the index. A wide covering index can also be much larger than a narrow index, increasing the number of leaf blocks to read.

### 6.1. Query selecting too many rows

```sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE status = 'PAID';
```

If most rows in the table have status `PAID`, the optimizer may pick a full table scan. Having all required columns in the index does not always make an index scan cheaper.

### 6.2. Clustering factor

Clustering factor reflects correlation between index key order and row locations in table blocks. For a non-covering index, a high clustering factor can scatter ROWIDs across many table blocks, making table lookups expensive. A covering index avoids that table lookup, though the wider index itself requires reading more blocks.

### 6.3. Index scan does not mean low I/O in every situation

An `INDEX FAST FULL SCAN` can read many index blocks via multiblock I/O without preserving key order. An `INDEX FULL SCAN` can read in index order. `INDEX RANGE SCAN` reads only a matching range. Distinguish these operations rather than seeing the word `INDEX` in a plan and assuming the query is fast.

## 7. NULLs and B-tree Index Limitations

Standard Oracle B-tree indexes do not store entries for rows where **all index key columns are NULL**. This is vital when evaluating index-only access.

### 7.1. Single-column index on a nullable column

```sql
CREATE INDEX ix_customers_middle_name
ON customers (middle_name);
```

If `MIDDLE_NAME` is `NULL`, that row has no entry in this single-column B-tree index. Thus, a standard index cannot supply all `MIDDLE_NAME IS NULL` rows merely by scanning its entries.

### 7.2. Composite indexes and NULLs

With:

```sql
CREATE INDEX ix_customers_status_email
ON customers (status, email);
```

If `STATUS` is non-NULL while `EMAIL` is `NULL`, an entry still exists because not all key columns are `NULL`. If both `STATUS` and `EMAIL` are `NULL`, the row has no entry in a standard B-tree index.

### 7.3. When queries need rows with NULLs as well

If a query must return rows where every column in the index is `NULL`, that index cannot represent rows that have no entry. You may need a key design incorporating an appropriate `NOT NULL` column or use another access path.

Do not append a column solely to handle `NULL`s without evaluating its meaning and cost. The right design depends on predicates and data completeness.

## 8. Selecting Covering Columns: Benefits and Costs

### 8.1. Read-side benefits

A well-designed covering index can:

- Eliminate `TABLE ACCESS BY INDEX ROWID` for matching queries.
- Reduce table block reads.
- Lower logical reads and potentially physical I/O.
- Return results from a structure smaller than the table.
- Support both predicates and `ORDER BY` in the same access path.
- Improve latency for repeated, highly selective queries.

The largest gains generally appear on frequently executed queries that read a few columns, filter a relatively small row set, and currently pay significant table lookup costs.

### 8.2. Write-side costs

Every index is a structure that must be maintained:

| DML | Index-related cost |
|---|---|
| `INSERT` | Adds an entry to every relevant index |
| `DELETE` | Removes the corresponding entry from every index |
| `UPDATE` of a key column | Modifies/removes the old index entry and inserts the new entry |
| `UPDATE` of a non-indexed column | Usually requires no entry change in that index |
| `UPDATE` of a column added just for covering | Still requires maintaining the index when that column changes |

Adding `TOTAL_AMOUNT` to an index can speed up read queries, yet every modification to `TOTAL_AMOUNT` incurs index maintenance work.

### 8.3. Storage and cache costs

Wider columns make larger index entries. A wide index can:

- Consume more tablespace storage.
- Fit fewer entries per leaf block.
- Increase the number of leaf blocks to read.
- Increase the likelihood of deeper index trees as data grows.
- Occupy buffer cache, competing with table data and other indexes.
- Increase backup, recovery, and maintenance overhead.

In particular, avoid putting `CLOB`, `BLOB`, or very wide `VARCHAR2` columns into B-tree indexes just to cover a query. Consider an alternative query model or index only necessary keys/expressions.

### 8.4. Read-heavy vs. write-heavy

| Workload | Consideration |
|---|---|
| Repeated analytical reports, infrequent data changes | Covering indexes can yield substantial benefits |
| Write-heavy OLTP with continuous updates | Keep indexes narrow; add covering columns only with measured proof |
| Append-only tables queried by time ranges | Composite indexes aligned with partitions/filters may fit |
| Tables with many mutable columns | Weigh update overhead of columns added to the index |
| Queries returning most of the table | Full table scan may outperform a covering index |

## 9. Do Not Confuse Covering Index with Guaranteed Index-Only Scan

"Covering" describes whether an index contains enough information for a query. "Index-only access" describes the access path the optimizer actually chooses in the plan. The two are related, not identical:

- The index has enough columns, yet the optimizer picks a full table scan.
- The index has enough columns, yet predicates/expressions do not match the key.
- `NULL` data or visibility attributes affect how Oracle executes.
- The query requires columns from another table.
- Statistics or bind selectivity push the optimizer toward a different access path.

Always confirm with actual execution plans and runtime statistics. Never evaluate simply by counting column names in `CREATE INDEX`.

## 10. Avoiding Redundant Indexes

Redundant indexes increase write cost, storage consumption, and optimizer complexity. Before adding a new index, compare against existing indexes.

### 10.1. Exact duplicate indexes

Example:

```sql
CREATE INDEX ix_orders_customer_a
ON orders (customer_id, status);

CREATE INDEX ix_orders_customer_b
ON orders (customer_id, status);
```

Two indexes on the same table with identical column lists and identical primary properties are generally redundant. Every `INSERT`/`DELETE` or key `UPDATE` must maintain both.

Before dropping one, verify the second index does not carry distinct properties such as `UNIQUE`, partitioning, compression, visibility, or constraint backing.

### 10.2. Prefix indexes

Suppose:

```sql
CREATE INDEX ix_orders_customer
ON orders (customer_id);

CREATE INDEX ix_orders_customer_status_date
ON orders (customer_id, status, order_date);
```

The second index has leading prefix `CUSTOMER_ID`, so it can serve many queries filtering only by customer. The narrower single-column index may be redundant unless there is a special need.

However, do not conclude automatically. The narrower index might:

- Be smaller and cheaper for workloads needing only customer ID.
- Back a constraint or specialized query.
- Have different `UNIQUE` or local/global attributes.
- Have different sort direction, compression, or partitioning.

Compare usage counts, buffer gets, write cost, and execution plans of critical queries.

### 10.3. Indexes with different leading columns do not replace each other

```sql
CREATE INDEX ix_orders_customer_status
ON orders (customer_id, status);
```

This index is not equivalent to `(STATUS, CUSTOMER_ID)`. A query filtering only `STATUS` cannot use the first index as efficiently as one led by `STATUS`. Oracle may use skip scan in some situations, though that is not a general replacement.

### 10.4. Single-column indexes vs. composite indexes

If you have:

```sql
CREATE INDEX ix_orders_customer ON orders(customer_id);
CREATE INDEX ix_orders_status ON orders(status);
CREATE INDEX ix_orders_date ON orders(order_date);
```

and the workload predominantly filters customer, status, and date together, a composite index can be more effective than combining multiple single-column indexes:

```sql
CREATE INDEX ix_orders_customer_status_date
ON orders(customer_id, status, order_date);
```

However, a composite index does not automatically replace every single-column index. If the workload also has queries filtering only `STATUS` or `DATE`, measure whether the composite index serves them well enough or separate indexes are warranted.

### 10.5. Constraint-supporting indexes

Indexes can back `PRIMARY KEY`, `UNIQUE`, and foreign key lookups. Oracle creates unique indexes when needed to enforce constraints if no suitable index exists, or reuses existing ones per configuration. Never drop an index just because its columns look similar to another index without checking constraint dependencies.

For foreign keys, an index on child columns is often helpful for `JOIN`s and reduces locking/blocking risks during parent updates or deletes in certain scenarios. If an existing composite index starts with the foreign key columns in matching order, it may already satisfy this need.

## 11. Column Order and Index Reusability

### 11.1. Place commonly queried columns in leading positions

The index:

```sql
(customer_id, status, order_date)
```

serves queries with `CUSTOMER_ID` as a prefix well. If the system primarily queries by `STATUS` and a date range across all customers, this index may not be optimal.

No single column order fits every query. Gather critical query patterns before designing.

### 11.2. Selectivity is not the sole criterion

Columns with many distinct values tend to offer high selectivity, yet do not always belong first in an index. Equality predicates can be combined; leading position also depends on:

- Which prefixes queries use.
- Which columns have range predicates.
- Whether sorting needs to be avoided.
- Data distribution and histograms.
- Reusability across other queries.

For instance, `CUSTOMER_ID` has many distinct values, yet queries always filter both `CUSTOMER_ID` and `STATUS`; the order between those two equality columns may be decided by which prefix other queries need.

### 11.3. Range predicates often limit trailing column effectiveness

With index `(A, B, C, D)` and query:

```sql
WHERE A = :a
  AND B >= :b
  AND C = :c
```

Oracle can use `A` and `B` to define the range scan. Condition `C` can still be checked as an index filter if `C` is in the index, but it does not narrow the scan range like an equality predicate preceding the range key.

Thus, when a query combines multiple equality predicates and one range predicate, place equality keys before the range key, followed by sort/projection columns. Inspect predicate information in the plan to see which columns act as access predicates versus filter predicates.

## 12. Function-Based Indexes and Covering

When a query applies a function to a column, you can create a function-based index:

```sql
CREATE INDEX ix_customers_upper_email
ON customers (UPPER(email));
```

Query:

```sql
SELECT UPPER(email)
FROM customers
WHERE UPPER(email) = UPPER(:email);
```

The index can serve expression-based access. If `SELECT` needs extra columns not in the index, Oracle may still have to visit the table.

### 12.1. Avoid wrapping date columns with TRUNC when possible

The query:

```sql
SELECT order_id, order_date
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
```

can prevent a regular index on `ORDER_DATE` from being used as a direct range scan. It is usually better to write:

```sql
SELECT order_id, order_date
FROM orders
WHERE order_date >= TIMESTAMP '2026-11-14 00:00:00'
  AND order_date <  TIMESTAMP '2026-11-15 00:00:00';
```

If the business truly requires `TRUNC(order_date)` and the query pattern is stable, consider a function-based index:

```sql
CREATE INDEX ix_orders_order_day
ON orders (TRUNC(order_date));
```

Function-based indexes also require maintenance when source values change and need appropriate statistics.

## 13. Reading Execution Plans to Confirm Covering

You cannot verify whether an index covers a query from DDL alone. Inspect the actual query's plan.

### 13.1. Common operations

| Operation | General meaning |
|---|---|
| `INDEX RANGE SCAN` | Reads a matching key range |
| `INDEX UNIQUE SCAN` | Locates a unique key |
| `INDEX FULL SCAN` | Scans the entire index in index order |
| `INDEX FAST FULL SCAN` | Scans the entire index via multiblock reads; key order not guaranteed |
| `TABLE ACCESS BY INDEX ROWID` | Uses ROWIDs from the index to read table rows |
| `TABLE ACCESS FULL` | Scans the entire table |
| `SORT ORDER BY` | Sorts results |
| `SORT GROUP BY` | Sorts/groups data for `GROUP BY` |

A covered query can eliminate `TABLE ACCESS BY INDEX ROWID` for that table. Table accesses on other tables in a `JOIN` may still remain.

### 13.2. Gathering runtime statistics

In a test session:

```sql
ALTER SESSION SET statistics_level = ALL;
```

Execute the real query and inspect the cursor plan:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Check:

- Which operations executed.
- `E-Rows` versus `A-Rows`.
- `Buffers` and `Starts`.
- Access predicates and filter predicates.
- Whether `TABLE ACCESS BY INDEX ROWID` appears.
- Whether a `SORT` step exists that an index could avoid.

### 13.3. Comparing before and after

Record at least:

| Metric | Before | After |
|---|---|---|
| Elapsed time | Measure | Measure |
| Buffer gets | Measure | Measure |
| Physical reads | Measure | Measure |
| Rows returned | Measure | Measure |
| Table access by ROWID | Yes/No | Yes/No |
| Index size | Measure | Measure |
| DML throughput | Measure | Measure |

Do not measure just once with a cold cache or only with a single set of bind values. Test across varying selectivities and realistic workloads.

### 13.4. Do not force indexes with hints prematurely

The `INDEX` hint can be used in controlled tests, but should not mask poor index design or bad statistics. As data shifts, a hinted access path can become slower than a full table scan.

Let the optimizer choose once accurate statistics are in place; keep hints only with solid evidence and a monitoring plan.

## 14. Index and Table Statistics

The optimizer relies on statistics to estimate cardinality and cost. After significant data changes or creating new indexes, check statistics:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS',
        cascade => TRUE
    );
END;
/
```

`CASCADE => TRUE` gathers associated index statistics as supported by Oracle. In production, follow your system's statistics management procedures; never run manual bulk gathers during peak hours without impact assessment.

View index metadata:

```sql
SELECT index_name,
       index_type,
       uniqueness,
       status,
       visibility,
       num_rows,
       leaf_blocks,
       distinct_keys,
       clustering_factor
FROM user_indexes
WHERE table_name = 'ORDERS'
ORDER BY index_name;
```

View index columns and order:

```sql
SELECT index_name,
       column_position,
       column_name,
       descend
FROM user_ind_columns
WHERE table_name = 'ORDERS'
ORDER BY index_name, column_position;
```

`USER_*` views display metadata in the current schema. Use `ALL_*` or `DBA_*` when inspecting other schemas with appropriate privileges.

## 15. Testing New Indexes While Reducing Optimizer Risk

Oracle supports invisible indexes so you can create and test an index without letting regular sessions' optimizers pick it by default.

### 15.1. Create an invisible index

```sql
CREATE INDEX ix_orders_test_cover
ON orders (
    customer_id,
    status,
    order_date,
    order_id,
    total_amount
)
INVISIBLE;
```

An invisible index is still maintained during DML; it still consumes storage and write overhead. `INVISIBLE` only affects optimizer consideration based on session settings.

### 15.2. Enable invisible indexes in a test session

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = TRUE;
```

Then run queries and inspect execution plans. Other sessions do not automatically use the index just because one session set this parameter.

### 15.3. Promote or drop the index

If testing succeeds and is approved:

```sql
ALTER INDEX ix_orders_test_cover VISIBLE;
```

If unnecessary:

```sql
DROP INDEX ix_orders_test_cover;
```

Invisible indexes are an access-path testing tool, not a free way to create indexes. DML still maintains the index, so factor in write costs during the trial period.

## 16. Identifying Redundant Indexes in a Schema

### 16.1. List indexes and columns

```sql
SELECT i.index_name,
       i.index_type,
       i.uniqueness,
       i.status,
       c.column_position,
       c.column_name,
       c.descend
FROM user_indexes i
JOIN user_ind_columns c
  ON c.index_name = i.index_name
 AND c.table_name = i.table_name
WHERE i.table_name = 'ORDERS'
ORDER BY i.index_name, c.column_position;
```

Use the output to group indexes sharing the same column list and compare order, uniqueness, status, visibility, and other attributes.

### 16.2. Find indexes with identical ordered column lists

The query below detects candidates with duplicate key columns:

```sql
SELECT table_name,
       column_list,
       COUNT(*) AS index_count,
       LISTAGG(index_name, ', ')
           WITHIN GROUP (ORDER BY index_name) AS index_names
FROM (
    SELECT table_name,
           index_name,
           LISTAGG(column_name, ', ')
               WITHIN GROUP (ORDER BY column_position) AS column_list
    FROM user_ind_columns
    GROUP BY table_name, index_name
)
GROUP BY table_name, column_list
HAVING COUNT(*) > 1
ORDER BY table_name, column_list;
```

This is only a candidate-discovery step. The query does not compare expressions, partitioning, compression, uniqueness, constraint dependencies, or physical attributes. Never automatically `DROP` indexes appearing in this output.

### 16.3. Check dependent constraints

```sql
SELECT constraint_name,
       constraint_type,
       index_name,
       status
FROM user_constraints
WHERE table_name = 'ORDERS'
  AND constraint_type IN ('P', 'U');
```

If an index backs a `PRIMARY KEY` or `UNIQUE` constraint, manage the constraint/index according to its dependency. Never drop an index used by a constraint just because another index shares similar columns.

### 16.4. Check usage before dropping

Oracle offers index usage tracking mechanisms in certain versions and management tools. Tracking has scope and limitations; a short observation window does not prove an index is unused. Cross-check SQL workloads, AWR/ASH if authorized, and organizational governance procedures before concluding.

### 16.5. Why should you not keep indexes "just in case"?

Unused indexes still carry costs:

- Every `INSERT`/`DELETE` must maintain entries.
- `UPDATE` of key columns must update entries.
- Occupies tablespace storage and buffer cache.
- Increases statistics gathering, backup, and maintenance work.
- Clutters the schema, making index selection harder per workload.

Keep an index only when specific queries, constraints, or operational needs justify its value.

## 17. Covering Indexes and Other Index Types

### 17.1. B-tree indexes

B-trees are the standard choice for OLTP and equality/range queries. Covering indexes in this lesson primarily refer to composite B-tree indexes.

### 17.2. Bitmap indexes

Bitmap indexes can help in certain data warehouse workloads with low-cardinality columns and low concurrent DML. However, bitmap indexes are generally unsuitable for OLTP tables with heavy concurrent updates due to locking characteristics and bitmap update costs.

Do not pick bitmap just because a column has few values; assess workload type and concurrency.

### 17.3. Function-based indexes

Indexes on expressions like `UPPER(email)` or `TRUNC(order_date)` serve predicates using matching expressions. If a query needs other columns too, you may have to include them in the index for covering, while weighing width and cost.

### 17.4. Index-organized tables are not covering indexes

An index-organized table (IOT) stores table row data inside a B-tree structure ordered by primary key. That is a table storage organization choice, different from adding a secondary covering index on a heap table. Do not convert a table to an IOT just to avoid table lookups without analyzing all access patterns, row widths, and DML.

## 18. Covering Index Design Workflow

A practical workflow:

1. **Select critical queries:** based on frequency, latency, buffer gets, and business impact.
2. **Read the full SQL:** record `SELECT`, `WHERE`, `JOIN`, `ORDER BY`, `GROUP BY`, and expressions.
3. **Identify access keys:** equality predicates, range predicates, and `JOIN` columns.
4. **Choose key order:** weigh leading columns, range keys, and sort order.
5. **Select covering columns:** add only needed projection columns, avoiding `SELECT *`.
6. **Assess width:** datatypes, lengths, row counts, and index size.
7. **Check existing indexes:** spot duplicates, prefixes, and constraint-backing indexes.
8. **Prototype under control:** use invisible indexes in a test session when appropriate.
9. **Compare plans and runtime:** buffers, elapsed time, table lookups, sorts, and DML throughput.
10. **Decide to keep or drop:** retain the index only when workload benefit exceeds write and storage cost.

### 18.1. Questions before adding columns to an index

- Is the query frequent and critical?
- Is the current table lookup actually expensive?
- Do the added columns change frequently?
- Are the added columns wide?
- Does the query return too many rows?
- Does an existing index already nearly cover the query?
- Can the query be rewritten to use a range predicate or avoid `SELECT *`?
- Does the new index overlap prefixes with another index?

If you cannot answer these questions, hold off on adding columns to an index "just to be safe."

## 19. Comprehensive Hands-On Lab

The statements below create a dedicated table in a practice schema. Run only with `CREATE TABLE` privileges and avoid colliding with existing data names.

### Step 1. Create the demo orders table

```sql
CREATE TABLE demo_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    order_date DATE NOT NULL,
    total_amount NUMBER(12, 2) NOT NULL,
    note VARCHAR2(500)
);
```

### Step 2. Insert sample data

```sql
INSERT INTO demo_orders
SELECT LEVEL,
       MOD(LEVEL, 100) + 1,
       CASE WHEN MOD(LEVEL, 3) = 0 THEN 'PAID' ELSE 'NEW' END,
       DATE '2026-01-01' + MOD(LEVEL, 365),
       LEVEL * 100,
       'Demo order ' || LEVEL
FROM dual
CONNECT BY LEVEL <= 10000;

COMMIT;
```

### Step 3. Run query before creating covering index

```sql
SELECT order_id,
       order_date,
       total_amount
FROM demo_orders
WHERE customer_id = 42
  AND status = 'PAID'
  AND order_date >= DATE '2026-06-01'
  AND order_date < DATE '2026-07-01'
ORDER BY order_date, order_id;
```

Inspect the plan via `DBMS_XPLAN.DISPLAY_CURSOR` after running the query.

### Step 4. Create the search index

```sql
CREATE INDEX ix_demo_orders_search
ON demo_orders (customer_id, status, order_date);
```

Re-run the query and compare access paths.

### Step 5. Create a covering index for testing

```sql
CREATE INDEX ix_demo_orders_cover
ON demo_orders (
    customer_id,
    status,
    order_date,
    order_id,
    total_amount
)
INVISIBLE;
```

### Step 6. Enable invisible indexes in the test session

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = TRUE;
```

Re-run the query, inspect the plan, and compare `buffers`. After testing, disable the parameter:

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = FALSE;
```

### Step 7. Compare size and metadata

```sql
SELECT index_name,
       status,
       visibility,
       leaf_blocks,
       distinct_keys,
       clustering_factor
FROM user_indexes
WHERE table_name = 'DEMO_ORDERS'
ORDER BY index_name;

SELECT index_name,
       column_position,
       column_name
FROM user_ind_columns
WHERE table_name = 'DEMO_ORDERS'
ORDER BY index_name, column_position;
```

### Step 8. Observe write costs

Try inserting a batch of rows in a demo transaction before and after creating the index, measuring elapsed time and redo/undo if your lab allows. Never conclude from a single run; caching, parsing, and background workload affect results.

### Step 9. Clean up demo indexes and table

Only when confirmed these are objects you created and data is no longer needed:

```sql
DROP INDEX ix_demo_orders_cover;
DROP INDEX ix_demo_orders_search;
DROP TABLE demo_orders PURGE;
```

`DROP TABLE ... PURGE` drops the table and data while bypassing the recycle bin; DDL issues an implicit commit. Never run cleanup commands on business tables or shared objects.

## 20. Common Misconceptions

| Misconception | Reality |
|---|---|
| Having an index means the query does not read the table | Only when the index provides all data and the optimizer chooses that path |
| ROWID in an index can return every column | ROWID only locates the row; non-indexed columns still require table access |
| Adding every SELECT column to an index is always good | Wide indexes increase storage and DML overhead |
| Oracle has INCLUDE columns like every DBMS | Standard B-trees store key columns; there is no common non-key `INCLUDE` payload syntax |
| A covering index is always chosen | The optimizer can choose a full table scan or another access path by cost |
| Index `(A,B,C)` is the same as `(B,A,C)` | Leading columns and key ordering differ |
| A composite index always replaces single-column indexes | Only when workload, constraints, and index properties allow |
| You can drop a prefix index immediately | Must check uniqueness, constraints, partitioning, usage, and performance |
| Single-column B-tree indexes store rows with NULL keys | Rows where all key columns are `NULL` have no entry in a standard B-tree |
| Invisible indexes have zero write cost | Invisible indexes are still maintained by DML |
| ORDER BY is always satisfied by an index | Requires compatible key order and equality prefixes; the optimizer may still `SORT` |
| Checking EXPLAIN PLAN alone is enough | Must inspect runtime statistics and realistic workloads |

## 21. Rules to Remember

| Goal | Principle |
|---|---|
| Filtering by predicates | Place suitable predicate keys in leading columns |
| Covering a query | Include needed filter, join, sort, and projection columns |
| Avoiding table lookups | Confirm the plan has no `TABLE ACCESS BY INDEX ROWID` for that table |
| Avoiding sorts | Place sort keys in matching order after equality prefixes |
| Limiting index width | Add only genuinely needed projection columns |
| Handling dates | Prefer half-open range predicates instead of wrapping columns in `TRUNC` |
| Querying expressions | Consider function-based indexes |
| Avoiding redundant indexes | Compare exact duplicates, left prefixes, and constraint dependencies |
| Balancing reads/writes | Measure query runtime, buffers, DML throughput, and index size |
| Testing new indexes | Use invisible indexes where suitable and inspect plans in a test session |
| Never rely on assumptions | Verify with execution plans and runtime statistics |

## 22. Self-Check Questions

**Question 1.** What is a covering index?

**Answer:** An index containing all columns a query needs for predicates, joins, sorts, and output, enabling Oracle to perform index-only access.

**Question 2.** Why does an index `(customer_id)` still need a table lookup when selecting `total_amount`?

**Answer:** `TOTAL_AMOUNT` is not in the index; ROWID only locates the row and does not store column values.

**Question 3.** Why does column order matter in a composite index?

**Answer:** B-trees are sorted in key order; leading columns determine which prefixes and range scans can be used directly.

**Question 4.** Why are equality predicates usually placed before range predicates?

**Answer:** Equality values narrow the prefix before scanning the range column interval; this starting heuristic should be verified with workload and plans.

**Question 5.** Does Oracle have `INCLUDE` columns like some other DBMSs?

**Answer:** Standard B-tree indexes use a key column list; columns added for covering remain key columns and widen the index.

**Question 6.** Is a covering index always chosen by the optimizer?

**Answer:** No. Cost, cardinality, selectivity, statistics, and index size can make a full table scan or another access path cheaper.

**Question 7.** Why does adding `TOTAL_AMOUNT` to an index make `UPDATE`s more expensive?

**Answer:** Whenever that key column changes, Oracle must maintain the corresponding index entry.

**Question 8.** Why should you avoid creating covering indexes for `SELECT *`?

**Answer:** It would require including almost every column in the index, producing a very wide structure and raising all write costs.

**Question 9.** Does a single-column B-tree index store entries for rows where that column is `NULL`?

**Answer:** No; rows where all key columns are `NULL` are not stored in a standard B-tree index.

**Question 10.** Can index `(A, B)` serve a query filtering only `A`?

**Answer:** Usually yes via leading prefix `A`. A query filtering only `B` lacks the same advantage; skip scan can appear when favorable, though you should not rely on it as a general rule.

**Question 11.** How do you tell whether a query avoided a table lookup?

**Answer:** Inspect the actual execution plan; for that table, `TABLE ACCESS BY INDEX ROWID` is absent, and verify runtime statistics.

**Question 12.** Are invisible indexes free for DML?

**Answer:** No. DML still maintains invisible indexes.

**Question 13.** Can you drop a single-column index simply because it is a prefix of a composite index?

**Answer:** Only after checking workload, constraints, uniqueness, partitioning, compression, and runtime impact.

**Question 14.** Can a covering index replace child tables or good data modeling?

**Answer:** No. Indexes optimize access paths; they do not replace data models, constraints, or business rules.

## 23. Conclusion

A covering index is a composite index containing all columns a query needs, giving Oracle the opportunity to return results via index-only access and avoid reading table blocks by ROWID. When designing one, start from real queries: identify filter, join, sort, and output columns; pick leading columns based on predicates and access patterns; place range and sort keys appropriately; and include only genuinely needed projection columns.

Read benefits must be balanced against write costs. Every column added to an index widens entries, consumes extra storage, and forces `INSERT`, `DELETE`, or `UPDATE` on key columns to maintain extra data. Nor is a covering index guaranteed to be picked by the optimizer in every case; confirm with execution plans and runtime statistics such as buffers, elapsed time, table lookups, and sorts.

Avoid exact duplicate or redundant prefix indexes by inventorying existing indexes, cross-checking workloads, and verifying constraint dependencies before dropping anything. A good index is not the one with the most columns, but one that serves critical queries at an appropriate total read, write, and storage cost.
