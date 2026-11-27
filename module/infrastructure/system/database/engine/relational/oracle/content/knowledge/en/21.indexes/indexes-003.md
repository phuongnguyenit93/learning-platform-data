# Composite Indexes, Leading Columns, and Column Ordering

In Oracle Database, a **composite index** (also called a concatenated index or multicolumn index) is an index created on two or more columns or expressions of the same table. A composite index stores keys in the order of the declared columns. That order determines how keys are sorted, which data ranges Oracle can locate directly, row filtering capability, and `ORDER BY` support.

Three key concepts:

- **Leading column:** the first column in the index definition.
- **Leading prefix:** one or more consecutive columns starting from the first column. For index `(A, B, C)`, the prefixes are `(A)`, `(A, B)`, and `(A, B, C)`.
- **Column order must follow the workload:** choose based on `WHERE`, `JOIN`, `ORDER BY`, `GROUP BY` patterns, value ranges, data distribution, and DML cost. There is no mechanical rule that the column with the highest cardinality must always go first.

Example:

~~~sql
CREATE INDEX ix_orders_customer_status_date
ON orders (customer_id, status, created_at);
~~~

The index is sorted first by `CUSTOMER_ID`, within each `CUSTOMER_ID` by `STATUS`, and within each `CUSTOMER_ID`/`STATUS` pair by `CREATED_AT`. It is typically suited for queries finding orders for a customer, further filtered by status and a date range. It is not equivalent to `(STATUS, CUSTOMER_ID, CREATED_AT)` or `(CREATED_AT, CUSTOMER_ID, STATUS)`.

This lesson explains B-tree composite index structure, leading prefixes, equality/range predicates, index skip scan, `ASC`/`DESC` ordering, workload-driven column design, `NULL`s, unique indexes, function-based indexes, statistics, and how to read execution plans.

## 1. What Is a Composite Index?

Single-column index:

~~~sql
CREATE INDEX ix_orders_customer
ON orders (customer_id);
~~~

Composite index:

~~~sql
CREATE INDEX ix_orders_customer_status
ON orders (customer_id, status);
~~~

A two-column index holds combined keys from `CUSTOMER_ID` and `STATUS`. In a B-tree index, keys are sorted in lexicographic order: Oracle compares the first column first; if equal, it compares the second column; if still equal, it considers the third column.

Suppose the data is:

| CUSTOMER_ID | STATUS | CREATED_AT |
| ---: | --- | --- |
| 10 | CLOSED | 2025-01-02 |
| 10 | CLOSED | 2025-01-09 |
| 10 | NEW | 2025-01-03 |
| 10 | NEW | 2025-02-01 |
| 20 | CLOSED | 2025-01-04 |
| 20 | NEW | 2025-01-07 |

With index `(CUSTOMER_ID, STATUS, CREATED_AT)`, the logical order can be visualized as:

~~~text
CUSTOMER_ID
  10
    CLOSED
      2025-01-02
      2025-01-09
    NEW
      2025-01-03
      2025-02-01
  20
    CLOSED
      2025-01-04
    NEW
      2025-01-07
~~~

This is why column order matters. The index is organized by `CUSTOMER_ID` first, not by `CREATED_AT` across the entire table.

### 1.1. A composite key is not manual string concatenation

Index `(A, B)` is not equivalent to creating a concatenated string column `A || B`. Oracle manages each key component according to its datatype, collation, and comparison rules. Manually concatenating columns can cause collisions, alter `NULL` semantics, and prevent normal index usage on individual columns.

### 1.2. An index stores keys and row location information

A B-tree index typically stores:
- Key values in the order of the columns/expressions.
- `ROWID` information to access rows in the heap table.
- Branch block and leaf block structures for searching and scanning keys.

A composite index can allow a query to read only the index if all needed columns are in the index and the optimizer picks an appropriate access path. When columns not in the index are needed, Oracle can access the table by `ROWID`.

## 2. Leading Column and Leading Prefix

With the index:

~~~sql
CREATE INDEX ix_sales_region_product_date
ON sales (region_id, product_id, sale_date);
~~~

Valid leading prefixes are:

1. `REGION_ID`
2. `REGION_ID, PRODUCT_ID`
3. `REGION_ID, PRODUCT_ID, SALE_DATE`

Prefixes start from the first column and do not skip columns in between.

Oracle can generally use an index range scan to locate a key range matching a prefix. Conditions on non-leading columns can still be useful, though access capability and cost differ.

### 2.1. Condition using only the leading column

~~~sql
SELECT sale_id, region_id, product_id, sale_date
FROM sales
WHERE region_id = 10;
~~~

Index `(REGION_ID, PRODUCT_ID, SALE_DATE)` can locate the range of entries starting with `REGION_ID=10`. Entries in this range lie contiguously ordered by the subsequent columns.

### 2.2. Condition using the first two columns

~~~sql
SELECT sale_id, region_id, product_id, sale_date
FROM sales
WHERE region_id = 10
  AND product_id = 200;
~~~

Oracle can use the `(REGION_ID, PRODUCT_ID)` prefix to narrow the search range further than `REGION_ID` alone.

### 2.3. Condition using all three columns

~~~sql
SELECT sale_id
FROM sales
WHERE region_id = 10
  AND product_id = 200
  AND sale_date >= DATE '2025-01-01'
  AND sale_date <  DATE '2025-02-01';
~~~

The index can position by `REGION_ID` and `PRODUCT_ID`, then bound the `SALE_DATE` interval within that key range.

### 2.4. Filtering only on the second column

~~~sql
SELECT sale_id, region_id, product_id
FROM sales
WHERE product_id = 200;
~~~

Index `(REGION_ID, PRODUCT_ID, SALE_DATE)` has no prefix starting with `PRODUCT_ID`. Oracle cannot simply find a single contiguous range for `PRODUCT_ID=200` across the whole index, because `PRODUCT_ID` values are sorted within each `REGION_ID`.

Depending on data and cost, Oracle may:
- Use another index starting with `PRODUCT_ID`.
- Use a full table scan.
- Use an index full scan or index fast full scan if suitable.
- Consider an index skip scan if the number of distinct values in the leading column is low enough and conditions allow.

Do not conclude an index can never be read when the leading column is missing. The point to understand is that it lacks a direct prefix-based range scan on `PRODUCT_ID`.

### 2.5. Skipping a middle column

With index `(A, B, C)`, a query filters on `A` and `C` without filtering on `B`:

~~~sql
SELECT *
FROM t
WHERE a = :a
  AND c = :c;
~~~

Oracle can use `A` to locate the key range; `C` can be applied as a filter on entries within `A`'s range. Condition `C` does not form an `(A, C)` prefix because `B` sits in between. If `B` has many values, the range scanned may be larger than desired.

If this query is frequent and highly selective, evaluate an index `(A, C)` or another column order based on the full workload.

## 3. Index Range Scan and Prefix Predicates

A composite B-tree index enables Oracle to locate a contiguous range of keys. The more of the leading part of the key a predicate pins down, the narrower the search range can be.

Example index:

~~~sql
CREATE INDEX ix_order_customer_status_date
ON orders (customer_id, status, created_at);
~~~

### 3.1. Equality on the first column

~~~sql
WHERE customer_id = :customer_id
~~~

Oracle locates the range of entries for one customer.

### 3.2. Equality on the first two columns

~~~sql
WHERE customer_id = :customer_id
  AND status = 'NEW'
~~~

Oracle locates the range for one customer and status `'NEW'`.

### 3.3. Equality followed by range

~~~sql
WHERE customer_id = :customer_id
  AND status = 'NEW'
  AND created_at >= :from_date
  AND created_at <  :to_date
~~~

This is a pattern well suited to `(CUSTOMER_ID, STATUS, CREATED_AT)`: equalities pin down the prefix, and the range bounds the trailing part.

### 3.4. Range on the first column, predicate on a later column

~~~sql
WHERE customer_id BETWEEN :low_id AND :high_id
  AND status = 'NEW'
~~~

Oracle can use `CUSTOMER_ID` to locate multiple ranges/sub-ranges. The `STATUS` condition can still be evaluated on index entries or as a filter step, but it no longer forms a single contiguous range corresponding to one specific `CUSTOMER_ID` value.

A generally helpful design principle is to place common equality columns before range columns when that reflects the dominant query structure. However, consider all queries and index reusability; this is a heuristic, not an absolute law.

### 3.5. Multiple equality conditions

~~~sql
WHERE customer_id = :customer_id
  AND status = :status
  AND channel_id = :channel_id
~~~

When all conditions are equalities, Oracle can use the prefix columns to isolate a narrow range. The ordering among equality columns can affect:
- Other queries that filter only on one of those columns.
- Queries filtering on a shorter prefix.
- Ability to support `ORDER BY`.
- Index size and value distribution.
- Skip scan and other access paths.

Do not look at only a single query when choosing column order.

## 4. Equality Before Range: A Useful Principle, Not Mechanical

With index:

~~~sql
CREATE INDEX ix_orders_customer_date_status
ON orders (customer_id, created_at, status);
~~~

and query:

~~~sql
WHERE customer_id = :customer_id
  AND created_at >= :from_date
  AND created_at < :to_date
  AND status = 'NEW'
~~~

Oracle can use the `CUSTOMER_ID` equality and `CREATED_AT` range to define the index range. `STATUS`, sitting after the range column, can be checked as a filter; it does not narrow the contiguous range as effectively as when `STATUS` precedes `CREATED_AT`.

If most queries filter by `CUSTOMER_ID` + `STATUS` equality and then `CREATED_AT` range, `(CUSTOMER_ID, STATUS, CREATED_AT)` is usually the more natural candidate.

However, if the most critical query fetches all orders by `CUSTOMER_ID` and `CREATED_AT` regardless of `STATUS`, `(CUSTOMER_ID, CREATED_AT, STATUS)` may be a better fit.

### 4.1. Range is not just BETWEEN

Range conditions include:
- `>`, `>=`, `<`, `<=`
- `BETWEEN`
- Date/time interval comparisons
- Certain prefix/range conditions depending on datatype and collation

Example:

~~~sql
WHERE created_at >= TIMESTAMP '2025-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2025-02-01 00:00:00'
~~~

Half-open intervals are usually ideal for timestamps because you do not have to guess end-of-day fractional seconds.

### 4.2. Predicates after a range column can still be useful

Do not misunderstand this as "columns after a range are useless." Oracle can still:
- Evaluate predicates on trailing columns inside index entries.
- Use those columns to reduce table accesses.
- Achieve index-only access if the query is covered.
- Combine multiple access paths or filters based on cost.

What to avoid is assuming a predicate after a range always establishes an equally narrow contiguous range bound as an equality prefix. Inspect access vs. filter predicates in the plan.

## 5. Index Skip Scan

**Index skip scan** is an access path Oracle can use when a query lacks a condition on the leading column but has a condition on a trailing column. Oracle logically splits the index into subindexes for each distinct value of the leading column and probes the relevant subindexes.

Example:

~~~sql
CREATE INDEX ix_emp_gender_dept
ON employees (gender, department_id);
~~~

Query:

~~~sql
SELECT employee_id, department_id
FROM employees
WHERE department_id = 10;
~~~

If `GENDER` has very few distinct values, such as `M`/`F`, Oracle may consider a skip scan:
- Search inside the logical subindex `GENDER='F'`.
- Search inside the logical subindex `GENDER='M'`.
- Combine entries matching `DEPARTMENT_ID=10`.

### 5.1. When can skip scan be suitable?

Skip scan may be considered when:
- The leading column has low cardinality.
- A trailing column has a selective predicate.
- The number of distinct values in the leading column is small.
- Skip scan cost is lower than a full table scan or alternative access paths.

If the leading column has millions of distinct values, the number of logical subindexes to probe can be large and skip scan becomes unattractive.

### 5.2. Skip scan does not replace leading-column design

If the workload frequently queries by `DEPARTMENT_ID` without filtering `GENDER`, `(GENDER, DEPARTMENT_ID)` is not necessarily the best choice. An index `(DEPARTMENT_ID, GENDER)` directly supports the `DEPARTMENT_ID` prefix and is usually more predictable for that workload.

Skip scan is an optimizer option, not a guarantee that any query missing a leading predicate will use the index well.

### 5.3. Checking the plan to recognize it

In an execution plan, you may see the operation `INDEX SKIP SCAN`. Exact operation choices depend on version and plan. Do not create an index with a low-cardinality leading column expecting skip scan when an index starting with the actual queried column is simpler and more effective.

## 6. Choosing Column Order Based on Workload

Suppose the `ORDERS` table has columns:
- `ORDER_ID`: primary key.
- `CUSTOMER_ID`: customer.
- `STATUS`: status.
- `CREATED_AT`: creation timestamp.
- `SALES_REP_ID`: sales representative.
- `CHANNEL_ID`: channel.

Common queries:

~~~sql
-- Q1: new orders for a customer within a date range.
SELECT order_id, created_at
FROM orders
WHERE customer_id = :customer_id
  AND status = 'NEW'
  AND created_at >= :from_date
  AND created_at < :to_date;

-- Q2: orders for a customer.
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = :customer_id;

-- Q3: NEW orders within a date range system-wide.
SELECT order_id, customer_id
FROM orders
WHERE status = 'NEW'
  AND created_at >= :from_date
  AND created_at < :to_date;

-- Q4: orders for a sales rep, sorted newest first.
SELECT order_id, created_at
FROM orders
WHERE sales_rep_id = :sales_rep_id
ORDER BY created_at DESC;
~~~

A single composite index will not necessarily serve all four patterns optimally. Candidates might be:

| Index | Naturally supported query pattern |
| --- | --- |
| `(CUSTOMER_ID, STATUS, CREATED_AT)` | Q1 and prefix `CUSTOMER_ID` for Q2 |
| `(STATUS, CREATED_AT)` | Q3 |
| `(SALES_REP_ID, CREATED_AT DESC)` | Q4 |

Whether to create all three depends on query frequency, row count, DML cost, storage, and existing indexes.

### 6.1. No single index is optimal for every query

If you create:

~~~sql
CREATE INDEX ix_orders_customer_status_date
ON orders (customer_id, status, created_at);
~~~

Q1 has a full prefix. Q2 uses the `CUSTOMER_ID` prefix. But Q3 filters only on `STATUS` and `CREATED_AT` without `CUSTOMER_ID`; this index does not provide a direct prefix range scan for Q3.

If you reverse the order:

~~~sql
CREATE INDEX ix_orders_status_date_customer
ON orders (status, created_at, customer_id);
~~~

Q3 can be supported naturally, but Q2 filtering only on `CUSTOMER_ID` lacks a leading prefix.

Column order is a workload trade-off, not an isolated "best" property.

### 6.2. Columns frequently used in leading positions may deserve priority

If many queries filter by `CUSTOMER_ID` without filtering `STATUS`, putting `CUSTOMER_ID` first lets the index serve:
- `CUSTOMER_ID`.
- `CUSTOMER_ID` + `STATUS`.
- `CUSTOMER_ID` + `STATUS` + `CREATED_AT`.

A single index `(CUSTOMER_ID, STATUS, CREATED_AT)` can serve consecutive prefixes. Conversely, a query filtering only `STATUS` is not directly supported by prefix.

### 6.3. Cardinality and selectivity

Column **cardinality** usually refers to the number of distinct values; predicate **selectivity** refers to the proportion of rows selected.

Examples:
- `STATUS` has 3 values (`NEW`/`PROCESSING`/`CLOSED`) -> low cardinality.
- `CUSTOMER_ID` has hundreds of thousands of values -> high cardinality.
- Predicate `STATUS='CLOSED'` may select 70% of the table -> low selectivity.
- Predicate `CUSTOMER_ID=12345` may select 0.001% of the table -> high selectivity.

High-cardinality columns often yield more selective predicates, but do not automatically have to lead every composite index. If queries always include equalities on both `CUSTOMER_ID` and `STATUS`, ordering also depends on prefixes to support, ranges, `ORDER BY`, and data distribution.

### 6.4. Equality columns can be ordered for reusability

Suppose the workload has:
- `CUSTOMER_ID`.
- `CUSTOMER_ID` + `STATUS`.
- `STATUS` + `CHANNEL_ID`.

If `CUSTOMER_ID` frequently appears alone, there is good reason to put it first. If `STATUS` + `CHANNEL_ID` is the primary workload, another index may be required.

When all predicates are equalities, ordering columns to support the widest set of query prefixes is often more useful than simply sorting by descending cardinality.

### 6.5. Placing range columns after equality columns when appropriate

Common pattern:

~~~sql
WHERE customer_id = :id
  AND status = :status
  AND created_at >= :from_ts
  AND created_at < :to_ts
~~~

Index `(CUSTOMER_ID, STATUS, CREATED_AT)` places the two equalities before the range. This is a useful practical heuristic for this query.

If `CREATED_AT` is used independently in many queries, another index starting with `CREATED_AT` or a partitioning/workload-aligned design may be needed. Do not try to cram everything into one index.

## 7. Composite Indexes Supporting ORDER BY

An index can help avoid or reduce sort overhead if the query ordering matches the index key order and prefix conditions.

Index:

~~~sql
CREATE INDEX ix_orders_customer_created
ON orders (customer_id, created_at);
~~~

Query:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at;
~~~

Once `CUSTOMER_ID` is pinned, entries in that range are sorted by `CREATED_AT`. Oracle can use the index to return rows in order without a separate sort, depending on the plan and columns needed.

### 7.1. ORDER BY matching column order

Index `(A, B)` can support:

~~~sql
WHERE a = :a
ORDER BY b;
~~~

because `A` is pinned, leaving the remaining order within the range sorted by `B`.

Index `(A, B, C)` can support:

~~~sql
WHERE a = :a
ORDER BY b, c;
~~~

if sort directions match the index definition and no conditions alter ordering requirements.

### 7.2. ORDER BY prefix

Index `(A, B, C)` can supply ordering by `A`, by `A, B`, or by `A, B, C`. But if you only `ORDER BY B` across the entire table without pinning `A`, the index is still ordered by `A` before `B`, so it is not globally ordered by `B`.

Example:

~~~sql
SELECT *
FROM t
ORDER BY b;
~~~

Index `(A, B)` does not produce table-wide ordering by `B`; `B` values are grouped within each `A`.

### 7.3. ASC and DESC

Oracle B-tree indexes can be scanned forward or backward. The index:

~~~sql
CREATE INDEX ix_orders_customer_date
ON orders (customer_id ASC, created_at ASC);
~~~

can be scanned in reverse to deliver `CUSTOMER_ID DESC, CREATED_AT DESC` in suitable cases. However, a mixed order such as:

~~~sql
ORDER BY customer_id ASC, created_at DESC
~~~

is not equivalent to reversing the entire `(CUSTOMER_ID ASC, CREATED_AT ASC)` index. A descending index may be needed:

~~~sql
CREATE INDEX ix_orders_customer_date_mix
ON orders (customer_id ASC, created_at DESC);
~~~

Check the actual plan; the optimizer may choose a sort over an index scan if the index path is more expensive.

### 7.4. NULLS FIRST and NULLS LAST

Default `NULL` ordering in Oracle:
- `ASC` defaults to `NULLS LAST`.
- `DESC` defaults to `NULLS FIRST`.

If a query requires:

~~~sql
ORDER BY created_at DESC NULLS LAST
~~~

check the index direction and whether the index can satisfy the `NULL` ordering. A descending key orders `NULL`s differently from an ascending key. Do not assume an index scan always satisfies every `ORDER BY` simply because the column names match; direction and `NULL` positioning matter as well.

### 7.5. Order is not guaranteed without a final ORDER BY

Even if an execution plan happens to read an index in sorted order, the application must still write `ORDER BY` in SQL to guarantee the result order contract. Never rely on physical index order or the current plan.

## 8. Composite Indexes for JOINs

Composite indexes are often helpful when `JOIN` conditions and filters combine multiple columns.

~~~sql
SELECT o.order_id,
       o.created_at,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = 'NEW'
  AND o.created_at >= :from_date;
~~~

Index candidates on `ORDERS` might be `(STATUS, CREATED_AT, CUSTOMER_ID)` or `(CUSTOMER_ID, STATUS, CREATED_AT)` depending on join access order, cardinality, and other workloads.

The index on `CUSTOMERS` may already be provided by the `CUSTOMER_ID` primary key. Do not create duplicate indexes if the primary key already provides a suitable index.

### 8.1. Foreign-key-side indexes

If queries frequently find orders by `CUSTOMER_ID`, an index starting with `CUSTOMER_ID` is useful:

~~~sql
CREATE INDEX ix_orders_customer_status
ON orders (customer_id, status);
~~~

A foreign key index can also assist certain parent `UPDATE`/`DELETE` operations and joins, depending on workload. Oracle does not automatically create indexes for every foreign key; DBAs/Developers must assess the need.

### 8.2. Join indexing is not based solely on column order in ON

A `JOIN` query can involve multiple predicates:
- Equality `JOIN` keys.
- `WHERE` filters.
- Date ranges.
- `ORDER BY`.

Examine the access paths for both outer and inner tables, expected row counts, join methods, and cardinality. Designing an index solely from one `ON` clause can miss other critical conditions.

## 9. Composite Indexes and Covering Queries

An index **covers** a query when all columns needed for filtering, joining, sorting, and returning results can be read from the index, allowing Oracle to avoid table access in certain plans.

Example:

~~~sql
CREATE INDEX ix_orders_customer_status_date_id
ON orders (customer_id, status, created_at, order_id);
~~~

Query:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = :customer_id
  AND status = 'NEW'
ORDER BY created_at;
~~~

All required columns are inside the index. Oracle can choose `INDEX RANGE SCAN` without accessing the table, if the plan and conditions allow.

### 9.1. Covering indexes are not always worth creating

Adding more columns to an index:
- Increases segment storage size.
- Increases `INSERT`/`UPDATE`/`DELETE` overhead.
- Increases redo/undo and index maintenance.
- Can reduce the number of entries per leaf block.
- Can increase tree height or the number of blocks to read.

Add columns to cover a query only when the measured read benefit justifies the write and storage cost. Do not mechanically include every `SELECT` column in an index.

### 9.2. INCLUDE columns differ across database engines

Some databases offer `INCLUDE` syntax to store non-key columns at the leaf level without participating in the sort key. Do not blindly apply that syntax pattern to standard Oracle B-tree indexes. In Oracle, columns declared in a composite index are part of the key; consider key order and key width carefully.

## 10. NULLs in Composite Indexes

Oracle B-tree indexes do not store an entry for a row where **all index key columns are NULL**. In a composite index, if at least one key column has a non-NULL value, the row can have an index entry.

Example:

~~~sql
CREATE INDEX ix_t_a_b
ON t (a, b);
~~~

| A | B | B-tree entry |
| --- | --- | --- |
| 10 | 20 | Yes |
| 10 | NULL | Yes |
| NULL | 20 | Yes |
| NULL | NULL | No entry |

This matters when designing queries that search for `NULL` and when considering single-column indexes on nullable columns.

### 10.1. Single-column index on a nullable column

~~~sql
CREATE INDEX ix_employee_middle_name
ON employees (middle_name);
~~~

Rows where `MIDDLE_NAME` is `NULL` have no entry in that B-tree index. The query:

~~~sql
SELECT employee_id
FROM employees
WHERE middle_name IS NULL;
~~~

generally cannot use this single-column B-tree index to locate all `NULL` rows, because those rows have no entry. The optimizer typically chooses a table scan or another access path.

### 10.2. Composite indexes can store rows with a NULL column

~~~sql
CREATE INDEX ix_employee_dept_name
ON employees (department_id, middle_name);
~~~

If `DEPARTMENT_ID` has a value while `MIDDLE_NAME` is `NULL`, the row still has an entry because the full key is not `NULL`. The index can support queries filtering by `DEPARTMENT_ID` and checking `MIDDLE_NAME` within that range.

### 10.3. NULLs and unique composite indexes

Unique composite indexes/constraints follow Oracle-specific `NULL` rules. Do not assume every row with one `NULL` column is ignored the same way as a row where the entire key is `NULL`. If using a unique index to enforce a business rule involving nullable columns, verify the exact semantics of `NULL` combinations against documentation and test in a sandbox schema; do not rely on simplistic models like "NULLs are always equal" or "NULLs are always distinct."

If the business requires conditional uniqueness, a function-based unique index or appropriate constraint design may be needed. `NULL` handling must be explicitly defined.

## 11. Unique Composite Indexes

You can create a unique index across multiple columns:

~~~sql
CREATE UNIQUE INDEX ux_customer_external_key
ON customer_external_id (source_system, external_id);
~~~

The index guarantees the key combination does not duplicate under Oracle's uniqueness rules. Example:
- `SOURCE_SYSTEM='CRM'`, `EXTERNAL_ID='A100'`.
- `SOURCE_SYSTEM='ERP'`, `EXTERNAL_ID='A100'`.

These two rows do not collide on the composite key because `SOURCE_SYSTEM` differs.

### 11.1. Unique constraint and unique index

You can declare a constraint:

~~~sql
ALTER TABLE customer_external_id
ADD CONSTRAINT uq_customer_external
UNIQUE (source_system, external_id);
~~~

Oracle usually creates a unique index to enforce the constraint if no suitable index exists. A `UNIQUE` constraint expresses a schema-level data integrity rule; a unique index is an index object with a uniqueness property. When the business requirement is uniqueness, prefer declaring an explicit constraint so metadata and intent are clear.

### 11.2. Do not create a unique index just for query speed

If the column combination does not truly need to be unique, a unique index will reject valid business data. Choose a nonunique composite index when the goal is purely an access path.

## 12. Function-Based Composite Indexes and Expressions

A standard column index may not be usable if a query applies a function to the column:

~~~sql
SELECT *
FROM customers
WHERE UPPER(email) = UPPER(:email);
~~~

An index on `EMAIL` will not directly support range access for `UPPER(EMAIL)`. You can create a function-based index:

~~~sql
CREATE INDEX ix_customers_upper_email
ON customers (UPPER(email));
~~~

Multiple expressions can be combined:

~~~sql
CREATE INDEX ix_orders_customer_month
ON orders (customer_id, TRUNC(created_at, 'MM'));
~~~

The query:

~~~sql
SELECT *
FROM orders
WHERE customer_id = :customer_id
  AND TRUNC(created_at, 'MM') = DATE '2025-01-01';
~~~

can match the expression index if conditions and datatypes align.

### 12.1. Expressions must match

Oracle must recognize that the predicate expression corresponds to the index expression. Differences in function, datatype, implicit conversion, or phrasing can prevent index usage.

If the query filters:

~~~sql
WHERE TRUNC(created_at) = DATE '2025-01-01'
~~~

while the index was created on `TRUNC(created_at, 'MM')`, the two expressions are not semantically identical. Do not expect the index to automatically satisfy a different predicate.

### 12.2. Avoid wrapping columns unnecessarily

When you can write a range directly:

~~~sql
WHERE created_at >= TIMESTAMP '2025-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2025-02-01 00:00:00'
~~~

it is usually much easier to use an index on `CREATED_AT` than wrapping the column in `TRUNC` inside `WHERE`, while preserving full time-component accuracy. Use function-based indexes only when the expression represents an actual query pattern that must be supported.

## 13. Implicit Conversion and Datatypes

A composite index may fail to be utilized as expected if a predicate forces Oracle to convert datatypes on the indexed column side.

For example, `CUSTOMER_ID` is `NUMBER`, yet the application binds a string:

~~~sql
WHERE customer_id = '100'
~~~

Oracle may apply implicit conversion depending on datatype precedence rules. If conversion is applied to the indexed column, access path choice can be degraded; if the string cannot be converted to a number, the query can fail.

In JDBC, bind the proper datatype:

~~~java
statement.setLong(1, customerId);
~~~

instead of passing a string for a `NUMBER` column.

For `DATE`/`TIMESTAMP`, use properly typed bind variables or explicit ANSI literals. Avoid relying on `NLS_DATE_FORMAT` or `NLS_NUMERIC_CHARACTERS` for implicit conversions.

## 14. Composite Indexes and GROUP BY

An index can support grouping queries if column order and predicates match:

~~~sql
SELECT customer_id,
       status,
       COUNT(*) AS order_count
FROM orders
WHERE customer_id = :customer_id
GROUP BY customer_id, status;
~~~

Index `(CUSTOMER_ID, STATUS)` can supply entries in an order suitable for group processing in some plans.

However, there is no guarantee Oracle will always use the index or avoid a sort. The optimizer can choose `HASH GROUP BY`, `SORT GROUP BY`, a table scan, or another access path based on cost.

### 14.1. GROUP BY does not imply display order

`GROUP BY` defines groups; it does not guarantee output order. If the application needs sorted output, add `ORDER BY`:

~~~sql
SELECT customer_id,
       status,
       COUNT(*) AS order_count
FROM orders
GROUP BY customer_id, status
ORDER BY customer_id, status;
~~~

An index can help supply the order, but `ORDER BY` remains the SQL contract.

## 15. Composite Indexes and Index Prefix Redundancy

If index `(A, B, C)` exists, it can serve many prefix queries on `A` and `A, B`. Therefore, a separate index `(A)` may be redundant in some workloads.

However, do not automatically drop a prefix index based solely on column definitions:
- Index `(A)` is smaller and lighter than `(A, B, C)`.
- A narrow index can serve queries reading only `A` with fewer blocks.
- A unique constraint or foreign key may depend on the index.
- Indexes may differ in compression, partitioning, visibility, or direction.
- DML workloads and optimizer plans can change.
- Wider indexes carry higher maintenance costs.

Before removing a prefix index, check:
- Constraints using the index.
- SQL workload and execution plans.
- Index usage monitoring if properly configured and interpreted.
- Licensed AWR/ASH or monitoring tools.
- Size and DML overhead.
- Queries needing a narrow index.

## 16. Compression and Composite Index Size

A composite index may have many entries repeating leading column values, such as many rows with the same `CUSTOMER_ID`. Oracle supports index key compression for certain B-tree indexes:

~~~sql
CREATE INDEX ix_orders_customer_status_date
ON orders (customer_id, status, created_at)
COMPRESS 2;
~~~

`COMPRESS 2` specifies the number of leading columns compressed via prefix compression. Compression can reduce storage when prefixes repeat heavily, with trade-offs in CPU and workload behavior. Measure on real data.

Do not confuse:
- Index key compression compresses the index key prefix.
- Advanced Index Compression offers different features/levels depending on edition, licensing, and version.
- Compression does not replace proper column ordering.

## 17. Optimizer Statistics and Selectivity

The optimizer needs statistics to estimate row counts and access path costs. For composite indexes, statistics can include:
- Number of distinct keys.
- Leaf blocks.
- Clustering factor.
- B-level.
- Average leaf blocks per key.
- Histograms on columns where appropriate.
- Extended statistics for column groups when columns are correlated.

If `CUSTOMER_ID` and `STATUS` are correlated, independent single-column predicate estimates can be inaccurate. For example, some customers only have `CLOSED` orders while others have a high proportion of `NEW` orders. Column group statistics can help the optimizer estimate cardinality more accurately in some cases.

### 17.1. Gathering table and index statistics

In an authorized environment:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS',
        cascade => TRUE
    );
END;
/
~~~

`CASCADE` gathers statistics for associated indexes as well. In production, DBAs must choose appropriate `METHOD_OPT`, `DEGREE`, `ESTIMATE_PERCENT`, `GRANULARITY`, and collection schedules; do not run ad-hoc bulk statistics collection during peak hours.

### 17.2. Extended statistics for column groups

When multiple columns are correlated, you can create column group statistics:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           USER,
           'ORDERS',
           '(CUSTOMER_ID, STATUS)'
       )
FROM dual;
~~~

Then re-gather table statistics following the appropriate procedure. Extended statistics provide cardinality estimation metadata to the optimizer; they do not create an index and do not replace a composite index.

## 18. Reading Execution Plans to Understand Composite Indexes

Do not conclude an index is used just because column names appear in `WHERE`. Check the execution plan:

~~~sql
EXPLAIN PLAN FOR
SELECT order_id, created_at
FROM orders
WHERE customer_id = 100
  AND status = 'NEW'
  AND created_at >= DATE '2025-01-01'
  AND created_at <  DATE '2025-02-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Common operations:
- `INDEX RANGE SCAN`: scans a matching key range.
- `INDEX UNIQUE SCAN`: locates a unique key.
- `INDEX SKIP SCAN`: skips through distinct leading key values via logical subindexes.
- `INDEX FULL SCAN`: scans the entire index in index order.
- `INDEX FAST FULL SCAN`: reads index blocks as a segment without guaranteeing index order.
- `TABLE ACCESS BY INDEX ROWID`: accesses table rows via ROWIDs from the index.
- `TABLE ACCESS FULL`: full table scan.

Exact operation names and choices depend on version, index structure, data, and optimizer decisions.

### 18.1. Access predicates and filter predicates

In `DBMS_XPLAN`, predicate information distinguishes:
- **Access predicate**: condition used to position or bound the access range.
- **Filter predicate**: condition evaluated additionally on rows/entries already accessed.

With index `(A, B, C)` and query `WHERE A = :a AND C = :c`, `A` may appear as an access predicate while `C` acts as a filter depending on the plan. This illustrates why skipping a middle column in a prefix does not necessarily narrow the search range as expected.

### 18.2. Viewing the actual cursor plan

If authorized and the SQL has executed:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
~~~

`ALLSTATS LAST` is helpful when runtime plan statistics were collected. Compare `E-Rows` and `A-Rows` to see if cardinality estimates diverge significantly. Not every session has privileges to read cursor plans or runtime statistics.

### 18.3. EXPLAIN PLAN is not a runtime measurement

`EXPLAIN PLAN` generates an estimated plan in `PLAN_TABLE`. It does not prove execution time, buffer gets, or actual row counts. When evaluating performance, use runtime statistics and representative data, while accounting for bind values and bind peeking/adaptive behavior.

## 19. Testing Composite Indexes in a Sandbox Schema

Create a demo table to observe prefixes and column order. These commands are for a practice schema only.

### 19.1. Create the table

~~~sql
CREATE TABLE order_index_demo (
    order_id    NUMBER(10)
        CONSTRAINT pk_order_index_demo PRIMARY KEY,
    customer_id NUMBER(8) NOT NULL,
    status      VARCHAR2(12 CHAR) NOT NULL,
    created_at  DATE NOT NULL,
    amount      NUMBER(12,2) NOT NULL,
    channel_id  NUMBER(4)
);
~~~

### 19.2. Load sample data

~~~sql
INSERT INTO order_index_demo
VALUES (1, 10, 'NEW', DATE '2025-01-02', 100, 1);

INSERT INTO order_index_demo
VALUES (2, 10, 'CLOSED', DATE '2025-01-05', 150, 2);

INSERT INTO order_index_demo
VALUES (3, 10, 'NEW', DATE '2025-01-15', 200, 1);

INSERT INTO order_index_demo
VALUES (4, 20, 'NEW', DATE '2025-01-03', 300, 1);

INSERT INTO order_index_demo
VALUES (5, 20, 'CLOSED', DATE '2025-02-01', 400, 2);

INSERT INTO order_index_demo
VALUES (6, 30, 'NEW', DATE '2025-01-20', 250, 3);

INSERT INTO order_index_demo
VALUES (7, 30, 'CLOSED', DATE '2025-02-10', 350, 1);

COMMIT;
~~~

### 19.3. Create an index by customer, status, date

~~~sql
CREATE INDEX ix_oid_customer_status_date
ON order_index_demo (customer_id, status, created_at);
~~~

### 19.4. Query by leading column

~~~sql
SELECT order_id, customer_id, status
FROM order_index_demo
WHERE customer_id = 10;
~~~

The index has prefix `CUSTOMER_ID`, so it can be considered for this access path.

### 19.5. Query by first two leading columns

~~~sql
SELECT order_id, created_at
FROM order_index_demo
WHERE customer_id = 10
  AND status = 'NEW'
ORDER BY created_at;
~~~

The `CUSTOMER_ID`/`STATUS` prefix is pinned; `CREATED_AT` is ordered within that range.

### 19.6. Query by equality + range

~~~sql
SELECT order_id, created_at, amount
FROM order_index_demo
WHERE customer_id = 10
  AND status = 'NEW'
  AND created_at >= DATE '2025-01-01'
  AND created_at <  DATE '2025-02-01'
ORDER BY created_at;
~~~

This query pattern matches the index order created. Since `AMOUNT` is not in the index, Oracle may access the table by `ROWID` to retrieve that column.

### 19.7. Query only by the second column

~~~sql
SELECT order_id, customer_id
FROM order_index_demo
WHERE status = 'NEW';
~~~

The current index has no leading prefix `STATUS`. Oracle may choose a table scan or another access path; do not force the optimizer to use the index merely to prove the index exists.

### 19.8. Create an alternative index to test the status workload

~~~sql
CREATE INDEX ix_oid_status_date
ON order_index_demo (status, created_at);
~~~

Query:

~~~sql
SELECT order_id, created_at
FROM order_index_demo
WHERE status = 'NEW'
  AND created_at >= DATE '2025-01-01'
  AND created_at <  DATE '2025-02-01';
~~~

The new index starts with `STATUS` and `CREATED_AT`, better matching this query's prefix. The two indexes serve different goals; in a real system, evaluate the maintenance cost of keeping both.

### 19.9. Gather statistics and view plan

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDER_INDEX_DEMO',
        cascade => TRUE
    );
END;
/

EXPLAIN PLAN FOR
SELECT order_id, created_at
FROM order_index_demo
WHERE customer_id = 10
  AND status = 'NEW';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

A tiny demo table may lead the optimizer to choose `TABLE ACCESS FULL` because its cost is low. That does not prove the index is wrong; the dataset is simply too small to show index benefits. Performance testing requires sufficiently large datasets and representative distributions.

### 19.10. Clean up sandbox objects

~~~sql
DROP TABLE order_index_demo PURGE;
~~~

Drop the sandbox table created for this lesson only when you are sure the data is no longer needed. `DROP TABLE` is DDL with an implicit commit; cleanup should be performed separately.

## 20. Common Composite Index Design Mistakes

| Issue | Why it happens | Resolution |
| --- | --- | --- |
| Query filters only the second column while the index starts with another | No direct leading prefix | Evaluate an index starting with the queried column, or skip scan if leading NDV is low |
| Overly wide index | Adding many columns just to cover a few queries | Weigh read benefit against storage and DML overhead |
| Range column placed before equality | Trailing predicate struggles to narrow a contiguous range | Consider equality before range based on workload |
| Choosing leading column solely for high cardinality | Ignores queries needing other prefixes | Analyze workload and common prefixes |
| Trying to serve every query with one index | Queries have different filter patterns | Design a minimal index set aligned with workload |
| Wrapping column in a function | Predicate does not match the base column index | Write direct range predicates or create a function-based index |
| Binding the wrong datatype | Implicit conversion can prevent index usage | Bind proper `NUMBER`/`DATE`/`TIMESTAMP` types |
| Assuming index scan always returns desired order | Missing `ORDER BY` or direction/`NULL` mismatch | Write `ORDER BY` and check the plan |
| Dropping a prefix index without checking | Narrow index may be cheaper or back a constraint | Check workload, constraints, usage, and plans |
| Relying on skip scan as primary design | Leading column may have many distinct values | Create an index matching frequent leading predicates |
| Creating a unique index purely for speed | Can unintentionally enforce business uniqueness | Use a nonunique index if uniqueness is not required |
| Treating EXPLAIN PLAN as runtime proof | Estimated plan can differ from actual execution | Inspect cursor plans and runtime statistics |

## 21. Column Ordering Design Process

When deciding to create a composite index, follow this sequence:

1. Collect real SQL statements with high frequency or high cost.
2. Record columns appearing in equality predicates, range predicates, `JOIN`, `ORDER BY`, and `GROUP BY`.
3. Identify query prefixes that need support, especially queries filtering only a subset of columns.
4. Place common equality columns first when doing so supports multiple useful prefixes.
5. Consider range columns after equality prefixes if the query pattern fits.
6. Examine selectivity, cardinality, data distribution, and column correlation.
7. Examine `ORDER BY` order, `ASC`/`DESC`, and `NULLS FIRST`/`LAST`.
8. Assess whether queries can be covered by the index or require table access.
9. Factor in storage size, `INSERT`/`UPDATE`/`DELETE` cost, and redo/undo.
10. Review existing indexes, unique/primary/foreign keys, and prefix redundancy.
11. Gather appropriate statistics.
12. Inspect execution plans and runtime statistics on representative data.
13. Test bind values with different selectivities.
14. Keep the index only if it delivers measurable benefit to the overall workload.

### 21.1. Quick decision table

| Query pattern | Index order worth evaluating |
| --- | --- |
| `WHERE A = :a` | `(A, ...)` |
| `WHERE A = :a AND B = :b` | `(A, B, ...)` or `(B, A, ...)` depending on prefix workload |
| `WHERE A = :a AND B BETWEEN ...` | `(A, B, ...)` |
| `WHERE A = :a AND B = :b AND C BETWEEN ...` | `(A, B, C)` |
| `WHERE B = :b` | Index starting with `B` or another access path |
| `WHERE A = :a ORDER BY B` | `(A, B)` |
| `WHERE A = :a ORDER BY B DESC` | Evaluate direction `(A, B DESC)` or appropriate scan |
| `WHERE A = :a AND C = :c`, index `(A,B,C)` | `A` can position; `C` may act as a filter since `B` is skipped |
| `WHERE B = :b`, index `(A,B)` with few distinct `A` | Skip scan may be considered; measure |

This table is only a starting point. The optimizer selects plans based on cost; a prefix-compatible index is not guaranteed to be chosen on every execution.

## 22. Common Misconceptions

**Index `(A,B,C)` is the same as index `(B,A,C)`.** False. Key ordering differs, leading prefixes differ, and directly supported queries differ.

**Having an index containing column `B` means `WHERE B = ...` will always use an efficient index range scan.** False if `B` is not the leading column. Oracle may use skip scan or scan the index differently, which is not equivalent to a direct prefix lookup.

**The highest-cardinality column must always go first.** False. You must consider query prefixes, equality/range, `ORDER BY`, selectivity, and the overall workload.

**Predicates on columns after a range column are completely useless.** False. They can still filter on index/table entries or assist covering; they simply do not necessarily narrow the range contiguously like a prefix.

**Equality must always precede every other column in every index.** That is a helpful heuristic for many query patterns, not a rigid rule. Consider which queries matter most and which prefix orders need support.

**Index skip scan makes the leading column unimportant.** False. Skip scan cost depends on the number of distinct leading values, and the optimizer only chooses it when cost-effective.

**Index `(A,B,C)` can always replace index `(A)`.** Not always. A dedicated index on `A` is narrower, can be cheaper, and may support specific constraints or workloads.

**An index scan automatically guarantees result order.** False under the SQL contract. A final `ORDER BY` is required.

**A DESC index just requires reversing the entire index.** False for mixed `ASC`/`DESC` orderings; individual column directions may need to be designed specifically.

**B-tree indexes store rows where all key columns are NULL.** False. Oracle B-trees do not create entries for rows where every key column is `NULL`.

**Adding every SELECT column to an index always makes queries faster.** False. Wide indexes increase storage and DML cost; covering benefits must be measured.

**One composite index serves only one query.** False. It can serve multiple leading prefixes and related query patterns.

**EXPLAIN PLAN choosing an index proves the query is fast.** False. You must inspect runtime, logical reads, actual cardinality, and workload.

## 23. Practice Exercises

1. Create index `(CUSTOMER_ID, STATUS, CREATED_AT)`. List all leading prefixes.
2. Why does a query with only `WHERE STATUS='NEW'` lack a direct prefix on that index?
3. Explain lexicographic order using three columns `A, B, C` and sample data.
4. Write a query with equality on `CUSTOMER_ID` and `STATUS`, and range on `CREATED_AT`.
5. If a query filters only `CUSTOMER_ID`, and neither `STATUS` nor `CREATED_AT` has a condition, which index can support it?
6. If a query filters only `PRODUCT_ID` while the index starts with `REGION_ID`, which access paths might Oracle consider?
7. How does index skip scan work? Why can low cardinality on the leading column help?
8. Why should you not rely on skip scan if queries on the second column occur frequently?
9. Explain why equality columns are often placed before range columns.
10. With `A BETWEEN ... AND ... AND B = :b`, how might predicate `B` be handled with index `(A, B)`?
11. Why can index `(CUSTOMER_ID, CREATED_AT)` support `WHERE CUSTOMER_ID = :id ORDER BY CREATED_AT`?
12. Why does index `(A, B)` not automatically supply global ordering for `ORDER BY B`?
13. Compare `(A ASC, B ASC)` and `(A ASC, B DESC)` for mixed `ORDER BY` queries.
14. Where does Oracle place `NULL`s by default for `ASC` and `DESC`?
15. Why does a single-column B-tree index not store entries for rows where that column is `NULL`?
16. With index `(A, B)`, does a row with `A=10`/`B=NULL` have an entry? Explain.
17. Compare a unique composite index and a unique constraint.
18. When is a function-based composite index appropriate?
19. Why can binding a `NUMBER` column as a `String` affect index access?
20. A query selects only columns present in an index. When can Oracle avoid `TABLE ACCESS BY ROWID`?
21. Why should you not add every column to an index just to make a covering index?
22. Index `(A, B, C)` already exists. When might a separate index `(A)` still be useful?
23. Explain how clustering factor affects the choice of an index range scan.
24. Why can column group statistics help when `A` and `B` are correlated?
25. Inspect `DBMS_XPLAN` and distinguish access predicates from filter predicates.
26. Why is `EXPLAIN PLAN` insufficient to conclude performance?
27. Design an index for a query filtering `CUSTOMER_ID`, `STATUS`, and a `CREATED_AT` range.
28. Design an index for a query filtering `STATUS` and a `CREATED_AT` range system-wide.
29. If both queries above are important, should you create two indexes? State the trade-offs.
30. Build a test plan for a new index using a representative workload and runtime statistics.

**A composite index is sorted in the order of its declared columns. The leading column and leading prefixes determine which key ranges Oracle can locate directly; equality, range, `ORDER BY`, `NULL`s, and skip scan are all affected by that order.** Choose column order based on real workload, balance access capability against write and storage cost, and verify with statistics and actual execution/runtime plans. There is no single optimal column order for every query; a good index is one that supports critical access patterns at an appropriate overall cost.
