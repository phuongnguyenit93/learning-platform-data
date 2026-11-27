# Index Range Scan, Unique Scan, Full Scan, and Fast Full Scan

Oracle Database has several ways to read a B-tree index. Common operations seen in execution plans include **INDEX UNIQUE SCAN**, **INDEX RANGE SCAN**, **INDEX FULL SCAN**, and **INDEX FAST FULL SCAN**. Additionally, the optimizer may choose **TABLE ACCESS FULL** to read the entire table instead of using an index.

These names describe different data access paths. They are not fixed tiers of "fast" versus "slow." An `INDEX RANGE SCAN` can be very efficient when retrieving a small percentage of rows, yet expensive if it must read hundreds of thousands of ROWIDs scattered across the table. A `TABLE ACCESS FULL` can be the best choice when a query needs most of the data.

This lesson focuses on how B-tree indexes store keys and ROWIDs, the conditions suited to each operation, the difference between index full scan and fast full scan, how the optimizer estimates costs, and how to read execution plans to understand which access path Oracle actually chose.

## 1. How Does a B-tree Index Store Data?

An Oracle B-tree index is a balanced tree structure. For a standard index, internal nodes navigate to the key range to read; leaf blocks store index keys and ROWIDs pointing to rows in the table.

~~~text
                 ROOT / BRANCH
                 /           \
          BRANCH               BRANCH
          /    \               /    \
       LEAF   LEAF           LEAF   LEAF
        |      |              |      |
      key+   key+           key+   key+
      ROWID  ROWID          ROWID  ROWID
~~~

One way to visualize it:

- Root/branch blocks guide navigation to the target key range.
- Leaf blocks contain entries sorted by the index key.
- ROWID identifies the row's location in the table segment.
- Leaf blocks are linked so they can be traversed sequentially in key order.

Example:

~~~sql
CREATE INDEX ix_employee_department_salary
ON employees (department_id, salary);
~~~

The index stores key pairs sorted by `DEPARTMENT_ID`, then `SALARY`, together with the ROWID of the corresponding row. If a query searches for employees in department 10 with a salary of 20,000 or more, Oracle can navigate to key range `(10, 20000)` and read subsequent leaf entries matching the condition.

### 1.1 What is ROWID used for?

`ROWID` is the logical address of a row in Oracle. When an index scan locates matching entries, Oracle can use their ROWIDs to access the rows in the table:

~~~text
INDEX RANGE SCAN
       |
       |  ROWID values
       v
TABLE ACCESS BY INDEX ROWID
       |
       v
   Table rows
~~~

If all columns needed by the query are already in the index and Oracle can retrieve the result directly from the index, the plan may omit `TABLE ACCESS BY INDEX ROWID`. This is often called index-only access or covering access.

An index helps locate rows, but it does not contain every column of the table by itself. If the query needs `EMPLOYEE_NAME` while the index only contains `DEPARTMENT_ID` and `SALARY`, Oracle generally must use ROWIDs to read the rows from the table.

### 1.2 An index is not a full copy of the table

A B-tree index stores only the indexed key columns and row location information. Consequences include:

- An index is usually smaller than the table, yet still incurs costs for reading leaf blocks and accessing the table.
- Columns missing from the index may require table access.
- DML on the table must maintain the index, increasing `INSERT`/`UPDATE`/`DELETE` cost.
- A single-column B-tree index does not store entries for rows where the entire index key is `NULL`.

Therefore, do not create an index solely because a column appears in `WHERE`. Evaluate selectivity, returned row count, blocks to read, and index maintenance overhead.

## 2. Operations to Distinguish

| Plan Operation | Goal | Rows/entries potentially read |
|---|---|---|
| INDEX UNIQUE SCAN | Find at most one entry by full unique key | 0 or 1 logical entry |
| INDEX RANGE SCAN | Find a key range or set of keys | 0 to many entries |
| INDEX FULL SCAN | Traverse all leaf entries in key order | All entries in the index |
| INDEX FAST FULL SCAN | Read all index blocks using a fast scan, without preserving key order | All required index blocks |
| TABLE ACCESS FULL | Read all table blocks within the scan scope | All table blocks |

Operation names have specific meanings in execution plans. Do not infer purely from the word `FULL`: both `INDEX FULL SCAN` and `INDEX FAST FULL SCAN` read the entire index, but their traversal method and output ordering differ.

## 3. INDEX UNIQUE SCAN

`INDEX UNIQUE SCAN` locates a single entry using the full key of a unique index. The result contains at most one logical row.

Example table:

~~~sql
CREATE TABLE employees (
    employee_id   NUMBER(8) PRIMARY KEY,
    department_id NUMBER(6),
    employee_name VARCHAR2(100),
    salary        NUMBER(12,2)
);
~~~

The `EMPLOYEE_ID` primary key creates a unique index (unless another constraint/index configuration is specified). Query:

~~~sql
SELECT employee_id,
       department_id,
       employee_name,
       salary
FROM employees
WHERE employee_id = 1001;
~~~

Oracle may choose:

~~~text
SELECT STATEMENT
  TABLE ACCESS BY INDEX ROWID EMPLOYEES
    INDEX UNIQUE SCAN (PK_EMPLOYEES)
~~~

First, the index finds the entry for `EMPLOYEE_ID = 1001`. Then the ROWID is used to fetch the remaining columns from the table.

### 3.1 Conditions for a unique scan

With a single-column unique index:

~~~sql
CREATE UNIQUE INDEX ux_employee_email
ON employees(email);
~~~

An equality query:

~~~sql
SELECT employee_id, email
FROM employees
WHERE email = 'linh@example.com';
~~~

can use `INDEX UNIQUE SCAN` because the predicate fully specifies the unique key.

With a multi-column unique index:

~~~sql
CREATE UNIQUE INDEX ux_order_line
ON order_lines(order_id, line_number);
~~~

The query:

~~~sql
SELECT *
FROM order_lines
WHERE order_id = 500
  AND line_number = 3;
~~~

can use a unique scan because both key columns are constrained by equality.

If you only specify:

~~~sql
WHERE order_id = 500
~~~

there can be multiple lines for an order. This accesses a prefix of the composite index and typically uses `INDEX RANGE SCAN`, not a unique scan.

### 3.2 Unique scan does not mean reading only a single block

To find an entry, Oracle may need to read root, branch, and leaf blocks. If the query requests columns outside the index, it must also read a table block by ROWID. Caching can make buffer-cached blocks fast to read, yet the operation can still involve multiple block accesses.

### 3.3 Unique scan differs from unique constraint

A unique constraint is a data integrity rule. `INDEX UNIQUE SCAN` is an access path in an execution plan.

- Having a unique constraint does not mean every query uses a unique scan.
- The optimizer may choose a full table scan if the query requests many rows or index cost is unfavorable.
- An equality query on a unique key can usually use a unique scan, though the final choice depends on expressions, datatypes, statistics, and plan cost.

### 3.4 NULLs and unique keys

Oracle allows `NULL` values in unique constraints per Oracle rules; a unique key does not imply all columns are `NOT NULL`. An `IS NULL` condition is not a normal equality lookup on a unique key. With a single-column B-tree, entries for rows with a `NULL` key are not stored, so that index cannot find all `NULL` rows on its own.

If an identifier column requires a unique and mandatory value, `NOT NULL` is typically combined with `PRIMARY KEY` or `UNIQUE` per data requirements.

## 4. INDEX RANGE SCAN

`INDEX RANGE SCAN` reads a range of entries from index leaf blocks. It is a common operation when querying:

- Equality on a nonunique column.
- Lookup by prefix of a composite index.
- Range conditions such as `>`, `>=`, `<`, `<=`, `BETWEEN`.
- Prefix patterns such as `LIKE 'ABC%'` under compatible conditions.
- A list of values that can be executed across multiple ranges.

Example:

~~~sql
CREATE INDEX ix_employee_department
ON employees(department_id);

SELECT employee_id,
       employee_name,
       department_id
FROM employees
WHERE department_id = 10;
~~~

If department 10 represents only a small fraction of the table, an index range scan can be efficient. Oracle locates the start of key `10` and reads matching entries.

### 4.1 Range scan with interval conditions

~~~sql
SELECT employee_id, salary
FROM employees
WHERE salary BETWEEN 20000 AND 40000;
~~~

With an index on `SALARY`, Oracle can locate the first leaf entry satisfying `SALARY >= 20000` and scan forward until exceeding `40000`.

`BETWEEN` is inclusive of both bounds, equivalent to:

~~~sql
salary >= 20000
AND salary <= 40000
~~~

### 4.2 Composite indexes and leading columns

Suppose:

~~~sql
CREATE INDEX ix_orders_customer_date
ON orders(customer_id, order_date);
~~~

The following queries can leverage the index key order:

~~~sql
-- Find one customer.
WHERE customer_id = 101

-- Find a customer's orders within a date range.
WHERE customer_id = 101
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'

-- Find by customer prefix range.
WHERE customer_id BETWEEN 100 AND 200
~~~

A query filtering only `ORDER_DATE` without a `CUSTOMER_ID` condition cannot normally use a single contiguous range on the leading prefix. Oracle may consider index skip scan or another access path, but you should not design under the assumption that every column in an index can be searched independently with equal efficiency.

### 4.3 Range scan with IN

~~~sql
SELECT employee_id, department_id
FROM employees
WHERE department_id IN (10, 20, 30);
~~~

The optimizer may perform multiple range accesses or wrap the index scan in an `INLIST ITERATOR` operation. The plan shape depends on the number of values, statistics, and cost.

### 4.4 LIKE and index range scan

A prefix pattern:

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_name LIKE 'AN%';
~~~

can be transformed into a key range starting with `AN`, provided datatype/collation and expressions allow.

A pattern with a leading wildcard:

~~~sql
WHERE customer_name LIKE '%AN'
~~~

generally cannot determine a starting point for a standard B-tree range. Oracle may choose a full scan or another technique. If the business needs substring matching, consider an appropriate search design rather than expecting a standard B-tree index to handle it well.

### 4.5 INDEX RANGE SCAN DESCENDING

Oracle can traverse an index range in reverse order:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE customer_id = 101
ORDER BY order_date DESC;
~~~

With a suitable index `(customer_id, order_date)`, the plan may display `INDEX RANGE SCAN DESCENDING`. Even so, only a query-level `ORDER BY` guarantees result ordering for the caller.

### 4.6 Range scan does not mean reading little data

A query with an indexed condition that returns 70% of the table's rows may incur:

1. Reading many leaf blocks.
2. Fetching very many ROWIDs.
3. Reading many scattered table blocks.

In this case, a full table scan can be cheaper due to sequential or multiblock I/O. The optimizer chooses based on estimated cost, not a rule of "if an index exists, use the index."

## 5. TABLE ACCESS BY INDEX ROWID

After an index scan, Oracle often must access the table to retrieve columns not stored in the index:

~~~text
SELECT STATEMENT
  TABLE ACCESS BY INDEX ROWID EMPLOYEES
    INDEX RANGE SCAN IX_EMPLOYEE_DEPARTMENT
~~~

The index scan produces ROWIDs for matching rows. Table access uses those ROWIDs to fetch the corresponding rows.

### 5.1 Why can table access be expensive?

If rows are scattered across many blocks, Oracle may have to read many individual table blocks. The correlation between index key order and row locations in the table is partly reflected by the **clustering factor**.

- Low clustering factor: adjacent index entries generally point to rows physically near each other in the table; ROWID access saves block I/O.
- High clustering factor: adjacent index entries may point to scattered table blocks; a large range scan can cause many table block accesses.

Clustering factor is not a direct time measurement and does not decide the plan by itself. It is an optimizer statistic used when estimating the cost of table access by ROWID.

### 5.2 TABLE ACCESS BY INDEX ROWID BATCHED

In some plans, Oracle displays `TABLE ACCESS BY INDEX ROWID BATCHED`. Batching collects ROWIDs to sort/group table block accesses and reduce random I/O.

Because row fetching can be optimized by block, do not rely on the physical order produced by an index scan to infer final row order. If order is required, use `ORDER BY`.

### 5.3 Index-only access

If the query only needs columns present in the index:

~~~sql
CREATE INDEX ix_employee_dept_salary
ON employees(department_id, salary);

SELECT department_id, salary
FROM employees
WHERE department_id = 10;
~~~

Oracle can return the required columns directly from the index, avoiding table access. This is one reason indexes may be designed to cover a critical query.

However, adding too many columns to an index makes it wider, increasing storage, buffer cache usage, and DML cost. Consider covering indexes only when workload and measurements prove the benefit.

## 6. INDEX FULL SCAN

`INDEX FULL SCAN` traverses all leaf entries of an index in key order. Oracle reads the required leaf range starting from the beginning or end depending on direction, and can emit values in index order.

Example:

~~~sql
CREATE INDEX ix_employee_department_salary
ON employees(department_id, salary);

SELECT department_id, salary
FROM employees
ORDER BY department_id, salary;
~~~

If the index fits and the optimizer finds the cost favorable, the plan can use `INDEX FULL SCAN`. Because the query only needs the two columns already in the index, Oracle may avoid reading the table.

### 6.1 Why read the whole index?

An index full scan may be chosen when:

- The query needs many or all index entries.
- The index is significantly smaller than the table.
- The index contains all columns needed by the query.
- The index order satisfies sorting requirements.
- The index access path costs less than a full table scan plus a sort.

### 6.2 INDEX FULL SCAN can help satisfy ORDER BY

The index is ordered by `(department_id, salary)`. The query:

~~~sql
SELECT department_id, salary
FROM employees
ORDER BY department_id, salary;
~~~

matches that key order. Oracle can walk the index in order and avoid a separate sort.

However, if a `JOIN`, parallel operation, batching, or another operation alters row order, the optimizer may still require a sort. SQL does not guarantee result order without a final `ORDER BY` on the query.

### 6.3 INDEX FULL SCAN vs. INDEX RANGE SCAN

| Characteristic | INDEX RANGE SCAN | INDEX FULL SCAN |
|---|---|---|
| Scope | A range of keys matching predicates | All leaf entries |
| Starting point | At the matching key position | At the beginning/end of the leaf chain |
| Entry count | Can be few or many | All entries |
| Key order | Traversed in index order within the range | Traversed completely in index order |
| Common use | Selective filtering | Reading the entire index, potentially leveraging order |

## 7. INDEX FAST FULL SCAN

`INDEX FAST FULL SCAN` reads all blocks of an index using a fast scan approach, typically leveraging multiblock I/O and capable of parallel execution. Oracle treats the index as a smaller segment to read all needed data.

The most important difference from `INDEX FULL SCAN`:

**Fast full scan does not guarantee index key order.**

Example:

~~~sql
SELECT department_id, salary
FROM employees;
~~~

If both columns are in index `(department_id, salary)` and the optimizer estimates the index is smaller/cheaper than the table, the plan may choose `INDEX FAST FULL SCAN`.

### 7.1 What does fast full scan read?

This operation reads index blocks optimized for throughput rather than walking the leaf chain sequentially to preserve key order. It can read multiple blocks at once, similar to how a full table scan reads blocks.

The goal is to extract all required data from the index at the lowest cost, not to return sorted data.

### 7.2 Fast full scan usually requires a covering index

Example:

~~~sql
CREATE INDEX ix_orders_customer_date
ON orders(customer_id, order_date);

SELECT customer_id, order_date
FROM orders;
~~~

The query only needs columns inside the index, making fast full scan a viable candidate. If the query also needs `ORDER_TOTAL`, which is not in the index, Oracle requires additional table access or another access path; when reading many rows, a full table scan may be better.

### 7.3 Do not rely on fast full scan for ordering

The query:

~~~sql
SELECT customer_id, order_date
FROM orders
ORDER BY customer_id, order_date;
~~~

cannot rely on `INDEX FAST FULL SCAN` to preserve order. If the optimizer chooses fast full scan, a sort operation may sit above it:

~~~text
SORT ORDER BY
  INDEX FAST FULL SCAN IX_ORDERS_CUSTOMER_DATE
~~~

If index order is desirable, `INDEX FULL SCAN` may be another candidate. The optimizer selects based on total cost.

### 7.4 Fast full scan and NULL columns

A single-column B-tree index does not store entries for rows with `NULL` in that column. If a query needs every row of the table, an index consisting solely of a nullable column may not contain all rows needed to replace a full table scan.

With a composite B-tree index, a row still has an entry if at least one key column is non-NULL. However, if all key columns are `NULL`, no entry is stored.

Therefore, when evaluating an index fast full scan as an alternative to reading the table, ensure the index contains every required row. Do not assume scanning the entire index is always equivalent to reading the entire table.

### 7.5 Fast full scan can run in parallel

Because it does not need to preserve leaf-chain order, fast full scan is suited to distributing blocks across multiple parallel execution servers under supported conditions. Parallel query still depends on configuration, privileges, object attributes, and optimizer decisions; having a fast full scan does not automatically mean the query runs in parallel.

## 8. TABLE ACCESS FULL

`TABLE ACCESS FULL` reads all table blocks within the scan scope. It does not need an index to locate individual rows; Oracle reads the table segment and applies predicates.

Example:

~~~sql
SELECT employee_id,
       employee_name,
       department_id,
       salary
FROM employees
WHERE salary > 10000;
~~~

If most employees earn over 10,000 or the table is relatively small, a full table scan can be cheaper than:

1. Traversing an index to collect ROWIDs.
2. Accessing table blocks for a huge number of rows.

### 8.1 Why is a full table scan sometimes better than an index?

A full table scan can typically read blocks sequentially via multiblock I/O, maximizing I/O throughput. Conversely, an index range scan covering a large fraction of rows may read many leaf blocks and many scattered table blocks.

The optimizer weighs:

- Expected number of returned rows.
- Total table blocks to read.
- Index leaf blocks to read.
- Clustering factor.
- Index and table sizes.
- Predicate selectivity.
- System statistics and I/O/CPU costs.
- Parallel degree and execution conditions.

### 8.2 Full scan does not mean ignoring WHERE

The `TABLE ACCESS FULL` operation reads table blocks and then filters rows according to predicates. The query:

~~~sql
SELECT *
FROM employees
WHERE department_id = 10;
~~~

can still use a full table scan if the optimizer estimates reading the entire table is cheaper. The `WHERE` condition is still applied; full scan simply describes how input blocks are read.

### 8.3 Full scan does not guarantee order

Even if a table was populated in ascending ID order or current data happens to come back in some order, `TABLE ACCESS FULL` does not guarantee result order. To obtain deterministic ordering, write:

~~~sql
ORDER BY employee_id;
~~~

## 9. Comparing INDEX FULL SCAN and INDEX FAST FULL SCAN

These two operations are easy to confuse because both read the entire index:

| Criterion | INDEX FULL SCAN | INDEX FAST FULL SCAN |
|---|---|---|
| Scope | All leaf entries | All required index blocks |
| Traversal | Via leaf chain / key order | Block scan optimized for throughput |
| Key order | Preserved | Not preserved |
| I/O | Typically ordered traversal, potentially single-block | Can use multiblock I/O |
| Satisfies ORDER BY | Yes, if order matches and the plan preserves order | No |
| Index-only access | Possible | Usually an important condition |
| Goal | Read the entire index in order | Read the index quickly as a compact structure |

A quick way to remember:

- `INDEX FULL SCAN`: reads the whole index in key order.
- `INDEX FAST FULL SCAN`: reads the whole index without needing key order.
- `TABLE ACCESS FULL`: reads all table blocks.

There is no rule that fast full scan is always faster than full scan. If ordering is needed, the extra sort cost can make fast full scan less attractive. If you only need aggregations over indexed columns, fast full scan can be a strong candidate.

## 10. Choosing Access Paths by Predicate Shape

Suppose we have indexes:

~~~sql
CREATE UNIQUE INDEX ux_employee_id
ON employees(employee_id);

CREATE INDEX ix_employee_dept_salary
ON employees(department_id, salary);
~~~

Indicative examples:

| Query | Potentially suitable access path | Reason |
|---|---|---|
| `employee_id = 1001` | INDEX UNIQUE SCAN | Equality on the entire unique key |
| `department_id = 10` | INDEX RANGE SCAN | One department can have multiple employees |
| `department_id = 10 AND salary >= 20000` | INDEX RANGE SCAN | Leading equality + range on the next column |
| `department_id BETWEEN 10 AND 20` | INDEX RANGE SCAN | A range on the leading key |
| `department_id IN (10,20)` | RANGE SCAN / INLIST ITERATOR | Multiple key ranges |
| Select all `department_id, salary` in index order | INDEX FULL SCAN may fit | Reads full index and can preserve order |
| Select all `department_id, salary` without ordering | INDEX FAST FULL SCAN may fit | Reads full index for throughput |
| Select many columns of most rows | TABLE ACCESS FULL may fit | Avoids mass table accesses via ROWID |

These are reasoning guidelines, not guaranteed operations. The optimizer decides based on cost and statistics.

## 11. Selectivity: How Many Rows Does a Predicate Filter?

**Selectivity** is the estimated fraction of rows matching a predicate. A highly selective predicate returns only a small portion of the table:

~~~sql
WHERE employee_id = 1001
~~~

If `employee_id` is unique, selectivity is very small (high filtering). Index unique scan is usually appropriate.

A low-selectivity predicate can return many rows:

~~~sql
WHERE status = 'ACTIVE'
~~~

If 95% of rows are `ACTIVE`, an index range scan might fetch nearly every row and access the table by ROWID. A full table scan can be cheaper.

### 11.1 Selectivity depends on data distribution

Do not look solely at the number of distinct values. For example, `STATUS` has two values `ACTIVE` and `INACTIVE` distributed 99%/1%. A predicate for `ACTIVE` and a predicate for `INACTIVE` have vastly different selectivities.

The optimizer uses column statistics, histograms where appropriate, and other metadata to estimate cardinality. Stale or unrepresentative statistics can lead to poor plans.

### 11.2 Avoid fixed percentage rules

There is no universal threshold such as "below 10% use index, above 10% use full scan." The decision depends on:

- Table block count.
- Row width.
- Index leaf block count.
- Clustering factor.
- Buffer cache and system statistics.
- Columns required from the table.
- Parallelism and I/O subsystem.

## 12. How Clustering Factor Affects Index Range Scan

Clustering factor reflects how closely table row order correlates with index key order.

Example index on `CUSTOMER_ID`:

- If rows for the same customer sit near each other in the table, a range may read fewer table blocks.
- If rows are inserted interleaved across many customers, ROWIDs for one customer may span very many different blocks.

In the second case, an index range scan can incur many table block accesses even if the returned row count is not huge.

### 12.1 Checking clustering factor

In a schema with privileges to inspect user index statistics:

~~~sql
SELECT index_name,
       table_name,
       blevel,
       leaf_blocks,
       distinct_keys,
       clustering_factor,
       num_rows
FROM user_indexes
WHERE table_name = 'EMPLOYEES';
~~~

General meaning:

- `BLEVEL`: branch depth of the index.
- `LEAF_BLOCKS`: statistical count of leaf blocks.
- `DISTINCT_KEYS`: statistical count of distinct key values.
- `CLUSTERING_FACTOR`: index/table order correlation.
- `NUM_ROWS`: statistical count of index entries.

Statistics may be out of date or vary by index type. Never judge an index good or bad from a single column in isolation.

### 12.2 Refreshing statistics

In an authorized environment following DBA procedures:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'EMPLOYEES',
        cascade => TRUE
    );
END;
/
~~~

`CASCADE => TRUE` requests statistics gathering for associated indexes per `DBMS_STATS` behavior. Production environments must adhere to system schedules, permissions, and statistics policies; do not arbitrarily gather stats on large busy tables without evaluation.

## 13. Reasons Oracle May Not Use an Index as Expected

Having an index does not mean the optimizer can or should use it.

### 13.1 Not using the leading column

Index:

~~~sql
CREATE INDEX ix_orders_customer_date
ON orders(customer_id, order_date);
~~~

Predicate:

~~~sql
WHERE order_date >= DATE '2026-01-01'
~~~

does not constrain `customer_id`. Oracle may consider skip scan if leading key values are few and cost is favorable, but a full table scan or another index could also be better.

### 13.2 Applying a function to a column

~~~sql
WHERE TRUNC(order_date) = DATE '2026-01-01'
~~~

can prevent a direct range scan on a standard index on `ORDER_DATE`. A range rewrite is usually much more index-friendly:

~~~sql
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-01-02'
~~~

If queries frequently require `TRUNC(order_date)`, consider a function-based index:

~~~sql
CREATE INDEX ix_orders_order_day
ON orders(TRUNC(order_date));
~~~

Evaluate datatype, NLS behavior, expression syntax, and index maintenance cost.

### 13.3 Implicit conversion

If a column is `NUMBER` yet the application binds a string, or a `DATE` column is compared against an NLS-dependent string, Oracle may need to convert data. When a conversion function wraps the indexed column, the access path can become inefficient or miss the expected range scan.

Bind the correct datatype:

- `NUMBER` with numeric types.
- `DATE`/`TIMESTAMP` with date/time types.
- `VARCHAR2` with string types.

Do not convert the indexed column to another type in a predicate when you can convert the input value to match the column type.

### 13.4 Unselective predicates

If a predicate returns most of the table, a full table scan can be cheaper than an index range scan plus numerous table accesses by ROWID. This may be the right optimizer choice.

### 13.5 Inaccurate or unrepresentative statistics

Stale stats, missing histograms on skewed columns, or bind values with varying selectivities can produce poor cardinality estimates. When investigating, compare `E-Rows` and `A-Rows` in the actual plan.

### 13.6 OR expressions

Predicates with `OR` across multiple columns may require multiple access paths. Oracle can use `OR` expansion or bitmap conversion depending on the case, but not every `OR` translates into a single simple index range scan.

## 14. Index Range Scan with a Composite Index: Detailed Example

Create an orders table:

~~~sql
CREATE TABLE lab_orders (
    order_id     NUMBER(10) PRIMARY KEY,
    customer_id  NUMBER(10) NOT NULL,
    order_date   DATE NOT NULL,
    status       VARCHAR2(20) NOT NULL,
    total_amount NUMBER(14,2) NOT NULL
);

CREATE INDEX ix_lab_orders_customer_date
ON lab_orders(customer_id, order_date);
~~~

Query:

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM lab_orders
WHERE customer_id = 101
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01';
~~~

The optimizer may use:

~~~text
SELECT STATEMENT
  TABLE ACCESS BY INDEX ROWID LAB_ORDERS
    INDEX RANGE SCAN IX_LAB_ORDERS_CUSTOMER_DATE
~~~

The index locates the key range:

~~~text
(101, 2026-01-01) <= key < (101, 2026-02-01)
~~~

Then it retrieves ROWIDs and fetches the matching rows. Because the query requires `TOTAL_AMOUNT`, which is not in the index, table access is typically required.

### 14.1 Creating a covering index

You could test:

~~~sql
CREATE INDEX ix_lab_orders_customer_date_amount
ON lab_orders(customer_id, order_date, total_amount);
~~~

The query above can retrieve the needed columns from the index, avoiding table access. However, the index is wider and increases DML/storage cost. If the query returns very many rows, scanning a wide index may still cost more than a full table scan.

Do not create a second index if the existing one already meets workload needs; inspect the plan and measure first.

## 15. Comparing Scan Types by Example

Suppose we have:

~~~sql
CREATE INDEX ix_lab_orders_customer_date
ON lab_orders(customer_id, order_date);
~~~

### 15.1 Reading only indexed columns, no ordering required

~~~sql
SELECT customer_id, order_date
FROM lab_orders;
~~~

`INDEX FAST FULL SCAN` may fit if the index is smaller than the table and contains all required rows/columns.

### 15.2 Reading only indexed columns and ordering required

~~~sql
SELECT customer_id, order_date
FROM lab_orders
ORDER BY customer_id, order_date;
~~~

`INDEX FULL SCAN` may be considered to provide key order. If the optimizer picks fast full scan or another access path, the plan may require a sort.

### 15.3 Needing many table columns

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       status,
       total_amount
FROM lab_orders;
~~~

If nearly the entire table is needed and the index does not cover the columns, `TABLE ACCESS FULL` is usually the natural candidate.

### 15.4 Selectively filtering one customer

~~~sql
SELECT order_id, order_date, total_amount
FROM lab_orders
WHERE customer_id = 101;
~~~

`INDEX RANGE SCAN` on leading key `CUSTOMER_ID` may fit if customer 101 has few orders relative to the whole table.

## 16. Reading Execution Plans

### 16.1 EXPLAIN PLAN

Example:

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id,
       employee_name
FROM employees
WHERE department_id = 10;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

In the output, examine:

- `Operation`: `INDEX RANGE SCAN`, `INDEX UNIQUE SCAN`, or `TABLE ACCESS FULL`.
- `Name`: index or table name.
- `Rows`: estimated row count.
- `Cost`: relative cost used by the optimizer to compare plans.
- `Predicate Information`: access and filter conditions.

### 16.2 Access predicates and filter predicates

In a plan:

- **access predicate**: locates the index/table range to read.
- **filter predicate**: discards rows after the operation retrieves data.

Example with index `(customer_id, order_date)`:

~~~sql
WHERE customer_id = 101
  AND order_date >= DATE '2026-01-01'
  AND status = 'PAID'
~~~

The first two conditions can be used to bound the range in the index. `STATUS` is not in the index, so it can act as a filter after reading the table row. `Predicate Information` shows which conditions the optimizer actually applies at each operation.

### 16.3 Actual execution statistics

In a test environment, capture the actual plan:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       employee_name
FROM employees
WHERE department_id = 10;
~~~

After running:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +COST'
    )
);
~~~

Compare:

- `E-Rows`: optimizer's estimated row count.
- `A-Rows`: actual row count emitted by the operation per collected stats.
- `Buffers`: logical reads if displayed.
- `Reads`: physical reads if displayed.
- `Starts`: number of times the operation started.

If an index range scan estimates 10 rows yet actually returns 100,000 rows, the optimizer may have underestimated table access cost. Investigate stats, histograms, bind values, and predicates before forcing an index.

### 16.4 EXPLAIN PLAN is not a runtime plan

`EXPLAIN PLAN` shows the plan generated under explain conditions. It does not capture full runtime execution with bind values, adaptive plans, and real statistics.

When investigating production, prefer inspecting the actual cursor via `DBMS_XPLAN.DISPLAY_CURSOR` if privileges and instrumentation allow.

## 17. Hints and Why You Should Not Force Indexes Casually

Oracle provides hints such as:

~~~sql
SELECT /*+ INDEX(e ix_employee_department) */
       e.employee_id,
       e.department_id
FROM employees e
WHERE e.department_id = 10;
~~~

A hint can steer the optimizer toward an index, but:

- A hint can be invalid or ignored.
- A forced plan today may perform poorly as data grows.
- An index range scan may cause excessive ROWID/table block accesses.
- Hints do not substitute for good statistics and proper SQL.

Consider hints only after verifying the natural plan is problematic, diagnosing why the optimizer picked it, and benchmarking on representative data.

Do not use `FULL` or `INDEX` hints as a default trick on every query.

## 18. Common Misconceptions

| Incorrect assumption | Accurate understanding |
|---|---|
| If an index exists, Oracle must use it | The optimizer compares costs across access paths |
| UNIQUE SCAN always reads exactly one block | It may need root/branch/leaf blocks plus a table block |
| RANGE SCAN always returns few rows | A range can be very wide |
| FULL SCAN is always slow | It can be cheaper when most of the data is needed |
| INDEX FULL SCAN and FAST FULL SCAN are identical | One preserves key order; the other does not |
| FAST FULL SCAN can satisfy ORDER BY | Order is not guaranteed; `SORT ORDER BY` may be required |
| INDEX RANGE SCAN needs no table access | Table access is needed if the query selects non-indexed columns |
| Wider indexes are always better | Wide indexes increase storage, I/O, and DML cost |
| Higher clustering factor is better | Lower clustering factor favors ROWID access |
| `LIKE '%abc'` uses B-tree range like a prefix | Leading wildcards normally prevent standard range positioning |
| Having WHERE guarantees index usage | Low-selectivity predicates can favor full scans |
| Index scans automatically guarantee result order | Only a final `ORDER BY` guarantees SQL ordering |

## 19. Workflow for Choosing and Investigating Access Paths

~~~mermaid
flowchart TD
    A["Read SQL and identify returned columns"] --> B["Identify predicates and index keys"]
    B --> C{"Equality on entire unique key?"}
    C -->|Yes| D["INDEX UNIQUE SCAN may fit"]
    C -->|No| E{"Selective key range / leading prefix?"}
    E -->|Yes| F["INDEX RANGE SCAN may fit"]
    E -->|No| G{"Does index cover the query?"}
    G -->|Yes, key order needed| H["INDEX FULL SCAN may fit"]
    G -->|Yes, no order needed| I["INDEX FAST FULL SCAN may fit"]
    G -->|No| J["Compare with TABLE ACCESS FULL"]
    D --> K["Inspect actual plan and measure"]
    F --> K
    H --> K
    I --> K
    J --> K
    K --> L["Compare E-Rows/A-Rows, buffers, reads, and predicates"]
~~~

Practical steps:

1. Determine the row count and columns the query needs.
2. Identify index keys, column order, and uniqueness properties.
3. Identify equality, range, `IN`, `LIKE`, `NULL`, or expression predicates.
4. Inspect operations in the execution plan.
5. Check whether table access by ROWID reads many blocks.
6. Correlate selectivity, clustering factor, and actual rows.
7. Compare against a full table scan and other indexes.
8. Modify indexes, SQL, or hints only with measured evidence.

## 20. Hands-On Self-Check Exercises

Exercises use the `EMPLOYEES`, `ORDERS`, and `LAB_ORDERS` tables mentioned above. Run in a test schema and avoid index name collisions with existing objects.

### Exercise 1 — Unique scan

Create a primary key on `EMPLOYEE_ID`. Query one ID by equality. Use `DBMS_XPLAN` to check whether Oracle chooses `INDEX UNIQUE SCAN`. Explain the `TABLE ACCESS BY INDEX ROWID` step if it appears.

### Exercise 2 — Range scan on a nonunique key

Create an index on `DEPARTMENT_ID`. Query a department with many employees. Observe `INDEX RANGE SCAN` and the number of ROWIDs returned.

### Exercise 3 — Composite index

Create index `(CUSTOMER_ID, ORDER_DATE)`. Compare a query filtering only `CUSTOMER_ID`, a query filtering both `CUSTOMER_ID` and `ORDER_DATE`, and a query filtering only `ORDER_DATE`. Explain the role of the leading column.

### Exercise 4 — INDEX FULL SCAN

Run a query selecting only columns in the index with an `ORDER BY` matching key order. Observe whether the plan can use `INDEX FULL SCAN` to avoid a sort.

### Exercise 5 — INDEX FAST FULL SCAN

Run a query needing only indexed columns without `ORDER BY`. Compare the plan when the optimizer picks fast full scan. Check whether result order is deterministic.

### Exercise 6 — Full table scan

Run a query returning most of the table and many columns. Compare the plan with an index range scan when using a more selective predicate. Explain why a full scan can be cheaper.

### Exercise 7 — Clustering factor

Query `USER_INDEXES` for the test table's indexes. Compare clustering factor, leaf blocks, and actual buffer gets of a range scan query.

### Exercise 8 — Function predicate

Compare `TRUNC(order_date) = ...` against a half-open date interval. Check access predicates and plans. Try a function-based index in the test schema.

### Exercise 9 — LIKE prefix and suffix

Compare `LIKE 'AN%'` with `LIKE '%AN'` on an indexed column. Note the difference in access path.

### Exercise 10 — Reading actual plans

Collect `ALLSTATS LAST`. Compare `E-Rows` and `A-Rows`, `Starts`, `Buffers`, and `Reads`. List possible causes if the optimizer misestimates cardinality.

## 21. Summary

| Operation/concept | Role |
|---|---|
| INDEX UNIQUE SCAN | Finds at most one entry by full unique key |
| INDEX RANGE SCAN | Reads a range of entries matching predicates |
| INDEX FULL SCAN | Reads all leaf entries in key order |
| INDEX FAST FULL SCAN | Reads all index blocks for throughput without preserving order |
| TABLE ACCESS FULL | Reads all table blocks |
| TABLE ACCESS BY INDEX ROWID | Uses ROWIDs to fetch columns from the table after an index scan |
| Covering index | An index containing all columns required by a query |
| Selectivity | Estimated proportion of rows matching a predicate |
| Clustering factor | Correlation between index order and row positions in the table |
| Leading column | First column of a composite index, critical for range access |
| Access predicate | Condition used to locate the data range |
| Filter predicate | Condition applied to filter rows after data is fetched |

Evaluate access paths by the actual work a query requires. Equality on a full unique key generally suits a unique scan; selective predicates on a key range can suit a range scan; full index scan can leverage key order; fast full scan prioritizes throughput when ordering is not needed; and a full table scan can be cheapest when reading most of the table. Execution plans and runtime statistics reveal which choice fits your specific data and workload.
