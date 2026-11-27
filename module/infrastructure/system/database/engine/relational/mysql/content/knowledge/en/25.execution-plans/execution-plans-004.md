# Access Types: const, eq_ref, ref, range, index, and ALL

## Lesson objectives

After this lesson, you will be able to:

- Read the `type` column in EXPLAIN and understand how MySQL accesses each table in an execution plan.
- Distinguish unique-key lookups (`const`, `eq_ref`) from lookups that can return multiple rows (`ref`).
- Identify key-range access (`range`), full index scans (`index`), and full table scans (`ALL`).
- Relate `type` to `possible_keys`, `key`, `key_len`, `ref`, `rows`, `filtered`, and `Extra`.
- Explain why `index` is not always faster than `ALL`, and why `ALL` is sometimes still a reasonable choice.
- Use practice data and EXPLAIN to compare access types, then verify hypotheses with EXPLAIN ANALYZE.

In MySQL, EXPLAIN shows how the optimizer intends to read and combine data. The `type` column in tabular format describes how MySQL accesses a table within a join plan. In JSON format, the corresponding property is `access_type`.

The six values in this lesson are commonly used to gauge the selectivity of an access path: `const`, `eq_ref`, `ref`, `range`, `index`, and `ALL`. They describe different ways of reading data, ranging from locating at most one row via a unique key to scanning an entire index or an entire table.

Do not read `type` as an absolute performance ranking. A good access type can still be slow if it executes millions of lookups; an `ALL` scan can be reasonable if the table is tiny or the query needs most of the rows. Always read `type` alongside estimated rows, the chosen index, filter conditions, and actual measurements.

## 1. Where is the type column in EXPLAIN?

Start with any query:

~~~sql
EXPLAIN
SELECT *
FROM sales_order
WHERE customer_id = 101;
~~~

Tabular EXPLAIN typically includes the following columns:

If server configuration changes the default EXPLAIN format, explicitly request tabular format with `EXPLAIN FORMAT=TRADITIONAL`. In JSON, the property corresponding to the `type` column is `access_type`; TREE represents iterators using a tree description.

| Column | Meaning to read |
|---|---|
| `id` | Order or identifier of the query block in the plan |
| `select_type` | Query block type, such as SIMPLE or PRIMARY |
| `table` | Table or table alias being read |
| `partitions` | Partitions accessed if the table is partitioned |
| `type` | Access/join type used to read the table |
| `possible_keys` | Candidate indexes the optimizer may consider |
| `key` | Index the optimizer actually selected |
| `key_len` | Length of the key portion used |
| `ref` | Value or column compared against the index |
| `rows` | Estimated number of rows the optimizer expects to read |
| `filtered` | Estimated percentage of rows remaining after table-level filter conditions |
| `Extra` | Additional details such as Using index, Using where, or Using filesort |

The `type` column answers the question: will MySQL locate rows by a unique key, probe an index, scan a range, or scan the entire structure?

The `key` column answers the question: which index is used? Both columns must be read together. For example, `type = range` and `key = idx_order_date` means MySQL uses the order-date index to read matching key ranges.

MySQL also has other access types such as `system`, `fulltext`, `ref_or_null`, `index_merge`, `unique_subquery`, and `index_subquery`. This lesson focuses on the six common values listed in the title.

### 1.1. EXPLAIN does not execute the SELECT statement

~~~sql
EXPLAIN
SELECT order_id, total_amount
FROM sales_order
WHERE ordered_at >= '2026-02-01'
  AND ordered_at <  '2026-03-01';
~~~

Standard EXPLAIN retrieves the plan estimated by the optimizer; it does not run the SELECT statement to return business rows.

To observe execution metrics, MySQL 8.4 supports:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, total_amount
FROM sales_order
WHERE ordered_at >= '2026-02-01'
  AND ordered_at <  '2026-03-01';
~~~

EXPLAIN ANALYZE genuinely executes the SELECT statement and adds actual row counts, loop counts, and iterator timings. Only use it on queries whose execution cost is acceptable, especially in production.

EXPLAIN ANALYZE always uses TREE format, so it does not display the tabular `type` column. Use tabular EXPLAIN to read access types, then use EXPLAIN ANALYZE to cross-check actual row counts and timings.

### 1.2. Access type depends on table position in a join

In a join query, tables are read in an order chosen by the optimizer. Values from a previously read table can serve as inputs to locate rows in the next table.

For example:

- The first table may be filtered by a constant.
- The next table may be probed by the previous table's foreign key.
- The third table may be looked up by primary key based on results from the first two tables.

Therefore, `eq_ref` and `ref` are usually understood in the context of each row combination from preceding tables. Do not look at a single EXPLAIN row while ignoring the order of rows in the output.

## 2. Preparing practice data

The examples in this lesson use a test database with three tables: customer, sales_order, and order_line. Each table uses InnoDB so B-tree indexes behave in the standard application way.

### 2.1. Creating tables

~~~sql
CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(120) NOT NULL,
    email VARCHAR(190) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customer_email (email)
) ENGINE = InnoDB;

CREATE TABLE sales_order (
    order_id BIGINT UNSIGNED NOT NULL,
    order_no VARCHAR(30) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    ordered_at DATETIME NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    note VARCHAR(200) NOT NULL,
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_order_no (order_no),
    KEY idx_customer_status (customer_id, order_status),
    KEY idx_order_status (order_status),
    KEY idx_order_date (ordered_at),
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
) ENGINE = InnoDB;

CREATE TABLE order_line (
    order_line_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_line_id),
    KEY idx_line_order (order_id),
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id)
        REFERENCES sales_order (order_id)
) ENGINE = InnoDB;
~~~

Important indexes in this lesson:

- `PRIMARY KEY` on customer and sales_order are unique, non-NULL keys.
- `uq_order_no` is a unique index on order_no.
- `idx_customer_status` is a composite index with customer_id in the leading position.
- `idx_order_status` and `idx_order_date` are non-unique indexes.
- `idx_line_order` enables finding multiple line items belonging to an order.

### 2.2. Loading data

~~~sql
INSERT INTO customer (
    customer_id, customer_name, email
)
VALUES
    (101, 'Nguyen An', 'an@example.test'),
    (102, 'Tran Binh', 'binh@example.test'),
    (103, 'Le Chi', 'chi@example.test'),
    (104, 'Pham Dung', 'dung@example.test');

INSERT INTO sales_order (
    order_id,
    order_no,
    customer_id,
    order_status,
    ordered_at,
    total_amount,
    note
)
VALUES
    (5001, 'SO-2026-0001', 101, 'PAID',
     '2026-02-01 09:15:00', 1250000.00, 'standard delivery'),
    (5002, 'SO-2026-0002', 101, 'PAID',
     '2026-02-03 11:30:00', 2400000.00, 'gift wrap'),
    (5003, 'SO-2026-0003', 102, 'PENDING',
     '2026-02-08 14:00:00',  890000.00, 'call before delivery'),
    (5004, 'SO-2026-0004', 103, 'PAID',
     '2026-02-15 16:45:00', 3400000.00, 'standard delivery'),
    (5005, 'SO-2026-0005', 101, 'CANCELLED',
     '2026-02-18 10:20:00',  450000.00, 'cancelled by customer'),
    (5006, 'SO-2026-0006', 104, 'PAID',
     '2026-03-02 08:10:00', 5100000.00, 'priority delivery'),
    (5007, 'SO-2026-0007', 102, 'PENDING',
     '2026-03-05 13:25:00',  760000.00, 'awaiting payment'),
    (5008, 'SO-2026-0008', 101, 'PAID',
     '2026-03-10 17:05:00', 1750000.00, 'standard delivery');

INSERT INTO order_line (
    order_line_id, order_id, product_code, quantity, unit_price
)
VALUES
    (9001, 5001, 'KB-01', 1, 1250000.00),
    (9002, 5001, 'MS-01', 2,  350000.00),
    (9003, 5002, 'KB-02', 1, 2400000.00),
    (9004, 5003, 'CB-01', 1,  890000.00),
    (9005, 5004, 'MN-01', 2, 1700000.00),
    (9006, 5005, 'HD-01', 1,  450000.00),
    (9007, 5006, 'SC-01', 1, 5100000.00),
    (9008, 5007, 'CB-02', 1,  760000.00),
    (9009, 5008, 'KB-01', 1, 1750000.00);
~~~

This is a small dataset to clearly observe relationships and query results. The optimizer may pick different plans on tiny datasets because table scan costs are low. When needing to observe a specific access type, this lesson uses `FORCE INDEX` or `STRAIGHT_JOIN` in annotated examples; these are practice tools, not a directive to force plans in real applications.

## 3. const: finding at most one row by constant value

`const` is used when MySQL can find at most one row by comparing the entire primary key or an entire unique index against constant values.

Example with primary key:

~~~sql
EXPLAIN
SELECT *
FROM customer
WHERE customer_id = 101;
~~~

Example with unique index:

~~~sql
EXPLAIN
SELECT *
FROM sales_order
WHERE order_no = 'SO-2026-0001';
~~~

For these queries:

- The condition supplies concrete key values directly in the SQL statement.
- All parts of the PRIMARY KEY or UNIQUE index are used.
- At most one row matches.
- The optimizer can read the row up front and treat its column values as constants for the rest of the plan.

### 3.1. Composite keys must use all parts

Suppose a table has a composite unique key:

~~~sql
CREATE TABLE warehouse_bin (
    warehouse_id INT UNSIGNED NOT NULL,
    bin_code VARCHAR(30) NOT NULL,
    capacity INT UNSIGNED NOT NULL,
    PRIMARY KEY (warehouse_id, bin_code)
) ENGINE = InnoDB;
~~~

Query using both key parts:

~~~sql
EXPLAIN
SELECT capacity
FROM warehouse_bin
WHERE warehouse_id = 1
  AND bin_code = 'A-01';
~~~

This case can use `const`, because the entire composite primary key is compared against constant values.

If only warehouse_id is filtered, the condition uses only one part of the composite primary key and can return multiple rows. It is no longer a `const` lookup on the full primary key.

### 3.2. How does const differ from ref?

If a condition looks up by a non-unique key, a single value can match multiple rows. MySQL must read all matching rows, so the access type is typically `ref`.

If a full unique key is matched against constants and at most one row can exist, `const` applies instead.

Not every WHERE clause with an equality operator produces `const`. Equality on an unindexed column or a non-unique index is insufficient to guarantee at most one row.

## 4. eq_ref: each prior row combination matches at most one row

`eq_ref` typically appears on a table joined after another table. For each combination of rows from preceding tables, MySQL reads at most one row in the current table using the entire PRIMARY KEY or a UNIQUE NOT NULL index.

Example: each order belongs to exactly one customer:

~~~sql
EXPLAIN
SELECT
    o.order_id,
    o.order_no,
    c.customer_name
FROM sales_order AS o
STRAIGHT_JOIN customer AS c
    ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID';
~~~

`STRAIGHT_JOIN` tells MySQL to read sales_order first and then customer. For each order row, the join condition supplies a customer_id to look up exactly one row via customer's PRIMARY KEY.

In EXPLAIN, the customer row may show:

- `type = eq_ref`
- `key = PRIMARY`
- `ref` referencing the customer_id column of sales_order

The `type` value for sales_order depends on indexes and statistics; the focus in this example is the access type for customer.

### 4.1. Conditions for eq_ref

Core requirements:

1. The comparison is an equality check, usually using the `=` operator.
2. All parts of the index are used.
3. The index is a PRIMARY KEY or UNIQUE NOT NULL.
4. The comparison value can be a constant or a column from a previously read table.

If the join uses only part of a composite unique index, or a non-unique index, MySQL may have to use `ref` because one value could match multiple rows.

### 4.2. eq_ref example with composite tables

~~~sql
EXPLAIN
SELECT
    l.order_line_id,
    o.order_no
FROM order_line AS l
STRAIGHT_JOIN sales_order AS o
    ON o.order_id = l.order_id;
~~~

For each line item, order_id identifies at most one order via sales_order's PRIMARY KEY. The sales_order table can be accessed via `eq_ref`.

`eq_ref` is generally a highly selective join path. However, if the preceding table has millions of rows, MySQL may still execute millions of lookups. Inspect loop counts and actual execution time rather than relying solely on the access type label.

## 5. ref: finding all rows sharing an index value

`ref` is used when MySQL probes an index by a value without being able to guarantee only a single matching row.

Example finding all orders for customer 101:

~~~sql
EXPLAIN
SELECT
    order_id,
    order_no,
    order_status
FROM sales_order FORCE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

Index `idx_customer_status(customer_id, order_status)` has customer_id in the leading position. The query uses the leading portion of the index to locate that customer's orders. Because one customer can have multiple orders, the appropriate access type is `ref`.

### 5.1. ref can use a leftmost prefix

The composite index in the practice schema is `KEY idx_customer_status (customer_id, order_status)`.

A query filtering only customer_id:

~~~sql
SELECT *
FROM sales_order
WHERE customer_id = 101;
~~~

can utilize the leading portion of the index. This is the leftmost prefix rule: MySQL can exploit consecutive columns starting from the first column of a composite index.

If filtering only order_status without customer_id, this index is generally not a direct candidate for a leftmost-prefix lookup. The separate index `idx_order_status` in the practice schema serves that case.

### 5.2. ref does not mean a single row

Suppose a customer has 3,000 orders. A `ref` lookup by customer_id can still return 3,000 rows.

Therefore, also read:

- `rows`: estimated rows to read per access.
- `filtered`: estimated percentage of rows remaining after filter conditions.
- `Extra`: residual conditions checked after retrieving rows.
- Loop count in EXPLAIN ANALYZE if the query is a join.

A `ref` returning few rows is usually efficient. A `ref` returning very many rows can be expensive, especially when repeated for numerous rows from a preceding table.

## 6. range: reading one or more key ranges

`range` uses an index to retrieve a subset of rows falling within one or more value ranges. Common predicates include:

- `>`, `>=`, `<`, `<=`
- `BETWEEN`
- `IN (...)`
- `IS NULL`, `IS NOT NULL`
- `LIKE 'prefix%'` on a B-tree when the pattern does not start with a wildcard

Example finding orders in February:

~~~sql
EXPLAIN
SELECT
    order_id,
    order_no,
    ordered_at,
    total_amount
FROM sales_order FORCE INDEX (idx_order_date)
WHERE ordered_at >= '2026-02-01 00:00:00'
  AND ordered_at <  '2026-03-01 00:00:00';
~~~

Index `idx_order_date(ordered_at)` supports range access over the time window. The half-open interval `[start of month, start of next month)` is usually convenient for DATETIME because you do not need to guess whether the end of the day includes fractional microseconds.

### 6.1. BETWEEN and multiple ranges

~~~sql
EXPLAIN
SELECT order_id, ordered_at
FROM sales_order
WHERE ordered_at BETWEEN
      '2026-02-01 00:00:00'
      AND '2026-02-28 23:59:59';
~~~

Or:

~~~sql
EXPLAIN
SELECT order_id, order_status
FROM sales_order
WHERE order_status IN ('PAID', 'PENDING');
~~~

The optimizer can use range access if the index and costs align. Even when predicates use equality or IN, `type` may appear as `range` when MySQL constructs one or more index ranges.

### 6.2. Range on a composite index

With a composite index, MySQL can form ranges across consecutive key parts. Example:

~~~sql
CREATE INDEX idx_customer_date
ON sales_order (customer_id, ordered_at);
~~~

Query:

~~~sql
EXPLAIN
SELECT order_id, ordered_at
FROM sales_order
WHERE customer_id = 101
  AND ordered_at >= '2026-02-01 00:00:00'
  AND ordered_at <  '2026-03-01 00:00:00';
~~~

The optimizer can use customer_id as the equality prefix and ordered_at as the range boundary on the composite index.

With a B-tree composite index, once a key part uses a range condition, subsequent key parts generally do not continue narrowing the same range as straightforwardly as preceding equality conditions. Check `key_len`, optimizer trace, and the actual plan to see exactly which key parts participated in building the range.

### 6.3. Range does not always mean reading few rows

If a query range spans most of the table, scanning the index and fetching rows can cost more than a full table scan. The optimizer may pick `ALL` instead of `range` when the estimated cost of range access is unfavorable.

Additionally, predicates wrapping columns in functions, mismatched type casts, or leading wildcards can prevent efficient range access on a standard index.

An example that typically struggles to leverage a B-tree index on ordered_at:

~~~sql
SELECT order_id
FROM sales_order
WHERE DATE(ordered_at) = '2026-02-15';
~~~

It can be rewritten as a range condition:

~~~sql
SELECT order_id
FROM sales_order
WHERE ordered_at >= '2026-02-15 00:00:00'
  AND ordered_at <  '2026-02-16 00:00:00';
~~~

This rewrite gives the optimizer an opportunity to use direct range access on ordered_at.

## 7. index: scanning the entire index tree

`index` means MySQL scans the entire index tree of the table. It resembles `ALL` in that it does not restrict reads to a selective range; the difference is that the scanned structure is the index tree.

Example:

~~~sql
EXPLAIN
SELECT customer_id
FROM sales_order FORCE INDEX (idx_customer_status);
~~~

Index `idx_customer_status` contains customer_id and order_status; InnoDB secondary indexes also carry the primary key to locate rows. Because the query only needs customer_id, the index can cover all returned data.

The plan may show:

- `type = index`
- `key = idx_customer_status`
- `Extra = Using index`

This means MySQL can satisfy the needed data directly from the index without reading individual rows from the clustered index.

### 7.1. Full index scan vs. index lookup

Two concepts are easily confused:

- Index lookup: locating a value or range via an index, typically represented by `const`, `eq_ref`, `ref`, or `range`.
- Full index scan: traversing every entry of an index, represented by `type = index`.

A query selecting only indexed columns may still have to read every entry. Having an index does not automatically make a query a selective lookup.

### 7.2. Using index is not an access type

`Using index` appears in the `Extra` column, not the `type` column.

- `type = index`: the access method is scanning the entire index.
- `Extra = Using index`: the query can be satisfied using only data in the index (covering/index-only scan).

You can have `type = range` paired with `Using index` if MySQL reads an index range and all needed columns reside in the index. Conversely, `type = index` can appear without `Using index` if full rows must still be fetched from the clustered index.

### 7.3. When is an index scan useful?

A full index scan can be reasonable when:

- The index is significantly smaller than the table row data.
- The query only needs columns stored in the index.
- Index order satisfies ORDER BY.
- The query needs most entries, yet an index-only scan reads less data than a table scan.

If the index is wide, spans many columns, or the query must look up every row in the clustered index, scanning the whole index may offer no benefit.

## 8. ALL: scanning the entire table

`ALL` means MySQL performs a full table scan on the table. With InnoDB, reading row data typically traverses the clustered index.

Example:

~~~sql
EXPLAIN
SELECT *
FROM sales_order
WHERE total_amount >= 0;
~~~

In the practice schema, there is no index on total_amount. The condition also matches all sample rows, and the query requests all columns. A full table scan is the natural choice.

### 8.1. ALL is not always a bug

`ALL` can be reasonable when:

- The table has only a few rows.
- The query needs most of the rows in the table.
- No suitable index exists.
- An index has low selectivity, making many random lookups more expensive than a sequential scan.
- The optimizer estimates a full scan costs less than index paths.

What matters is the number of rows read, the number of rows returned, and query frequency. A full scan on a 20-row configuration table is rarely concerning; a full scan on a hundred-million-row transaction table on every request can be a major issue.

### 8.2. When should ALL be investigated?

Investigate when:

- The table is large yet the query needs only a few rows.
- A suitable index exists, yet `possible_keys` or `key` looks unexpected.
- Filter conditions are non-sargable, such as wrapping a column in a function.
- Mismatched data types in comparisons trigger type conversion.
- Index statistics are stale or data distribution is skewed.
- A join query causes a large table to be scanned repeatedly.

You can refresh statistics after major data changes:

~~~sql
ANALYZE TABLE sales_order;
~~~

ANALYZE TABLE updates statistics for the optimizer; it does not create indexes and does not guarantee the plan will change in the desired direction. Re-run EXPLAIN afterward.

## 9. Comparing the six access types

| type | Access pattern | Rows per lookup | Common example |
|---|---|---:|---|
| `const` | Reads at most one row via full unique key with a constant | 0 or 1 | PRIMARY KEY = 101 |
| `eq_ref` | Lookup via full PRIMARY KEY/UNIQUE NOT NULL per prior row combination | At most 1 | Join order.customer_id to customer.PK |
| `ref` | Equality lookup on a non-unique index or leftmost prefix | Potentially many | customer_id = 101 |
| `range` | Reads one or more index ranges | A subset | ordered_at within a range |
| `index` | Scans the entire index tree | All index entries | Reading columns covered by index |
| `ALL` | Scans the entire table | All rows | Filtering unindexed column, selecting many columns |

The MySQL documentation lists join types in a general order from best to worst, but that ordering does not replace cost evaluation. In particular, both `index` and `ALL` scan an entire structure; an index scan helps only when the index structure is smaller or better covers the required data.

### 9.1. Distinguishing by asking questions

When reading an EXPLAIN row, ask in sequence:

1. Is there a full unique key matched against constants? Likely `const`.
2. Is this a joined table looked up by a full unique key from prior rows? Likely `eq_ref`.
3. Can the equality lookup return multiple rows? Likely `ref`.
4. Does the query need a range of values on an index? Likely `range`.
5. Is there no selective filter, yet only an index needs scanning? Likely `index`.
6. Is there no beneficial index path, or are most rows needed? Likely `ALL`.

The next question is always: how many rows does MySQL estimate it must read, and how many did it actually read?

## 10. Reading columns accompanying type

### 10.1. possible_keys and key

- `possible_keys` lists indexes usable for locating rows.
- `key` is the index actually chosen.
- `key = NULL` usually means no index is used to locate rows in that table.

An index appearing in possible_keys yet not chosen is not necessarily a bug. The optimizer may estimate a scan is cheaper than lookups, or that the index lacks selectivity.

### 10.2. key_len

`key_len` shows the length of the key portion used. For composite indexes, it helps identify how many key parts MySQL utilized.

Do not interpret key_len by naively counting characters or columns. Length depends on data type, nullability, byte length, character set, and which key parts actually participate in the access condition.

### 10.3. ref

`ref` shows the column or constant compared against the index. In joins, this value typically points to a column from a preceding table.

For instance, on the customer row in an order join query, ref may be the customer_id column of sales_order. This is a clue that lookups are driven by each customer_id fetched from the prior table.

### 10.4. rows and filtered

`rows` is the estimated number of rows MySQL expects to read per table access. `filtered` is the estimated percentage of rows remaining after additional filter conditions.

Illustrative example:

| type | rows | filtered | Interpretation |
|---|---:|---:|---|
| ref | 100 | 10.00 | Expected to read 100 rows, roughly 10% remain after filtering |
| range | 500 | 80.00 | Expected to read 500 rows in range, roughly 80% remain |
| ALL | 100000 | 1.00 | Scans 100,000 rows, only roughly 1% remain |

These are illustrative figures, not measurements from the practice schema. Inaccurate estimates can mislead the optimizer into choosing a poor join order or access path.

### 10.5. Extra

Common values include:

- `Using index`: the query can be satisfied by the index without reading extra rows from the clustered index.
- `Using where`: additional conditions are checked after fetching rows.
- `Using index condition`: Index Condition Pushdown allows the storage engine to evaluate part of a condition directly on index entries.
- `Using filesort`: MySQL requires an extra sorting step for ORDER BY.
- `Using temporary`: the query requires a temporary table for an intermediate step.

Do not infer total cost from `type` alone. A `range` query might still filesort or fetch many extra rows; a `ref` query might execute a vast number of times inside a join.

## 11. Lab: observing each access type

The following statements use the schema from section 2. Run EXPLAIN before each SELECT and identify the corresponding table row.

### Lab 1: const on PRIMARY KEY

~~~sql
EXPLAIN
SELECT *
FROM customer
WHERE customer_id = 101;
~~~

Expected: the customer table can use `const`, with key as PRIMARY. Verify the condition uses the entire primary key.

### Lab 2: const on UNIQUE NOT NULL

~~~sql
EXPLAIN
SELECT order_id, customer_id, total_amount
FROM sales_order
WHERE order_no = 'SO-2026-0001';
~~~

Expected: at most one-row lookup via `uq_order_no`. Confirm the index is declared UNIQUE and the order_no column is NOT NULL.

### Lab 3: eq_ref in a join

~~~sql
EXPLAIN
SELECT
    o.order_id,
    o.order_no,
    c.customer_name
FROM sales_order AS o
STRAIGHT_JOIN customer AS c
    ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID';
~~~

Locate the customer row in EXPLAIN. It is read after sales_order and can use PRIMARY KEY to find at most one customer per order.

### Lab 4: ref on a non-unique index

~~~sql
EXPLAIN
SELECT
    order_id,
    order_no,
    order_status
FROM sales_order FORCE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

Expected: composite index idx_customer_status is used via its leading customer_id part. One customer can have multiple orders, so the access type can be `ref`.

### Lab 5: range on order date

~~~sql
EXPLAIN
SELECT order_id, ordered_at, total_amount
FROM sales_order FORCE INDEX (idx_order_date)
WHERE ordered_at >= '2026-02-01 00:00:00'
  AND ordered_at <  '2026-03-01 00:00:00';
~~~

Expected: the optimizer can use `range` with idx_order_date. If small data causes the optimizer to pick ALL, grow the test dataset or use FORCE INDEX in a separate experiment to observe the access path.

### Lab 6: index full scan

~~~sql
EXPLAIN
SELECT customer_id
FROM sales_order FORCE INDEX (idx_customer_status);
~~~

Expected: `type = index`, the index is scanned in full. Since only customer_id (present in the index) is needed, Extra may show Using index.

### Lab 7: ALL full table scan

~~~sql
EXPLAIN
SELECT *
FROM sales_order
WHERE total_amount >= 0;
~~~

Expected: the condition has no dedicated index and the query requests all columns. A full table scan may be selected.

### Lab 8: Comparing index scan and table scan

~~~sql
EXPLAIN
SELECT customer_id
FROM sales_order FORCE INDEX (idx_customer_status);

EXPLAIN
SELECT *
FROM sales_order;
~~~

Compare estimated rows, key, type, and Extra. The first query needs only one column present in the index; the second requests entire rows.

### Lab 9: Observing access types across multiple tables

~~~sql
EXPLAIN
SELECT
    c.customer_name,
    o.order_no,
    l.product_code,
    l.quantity
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id
JOIN order_line AS l
    ON l.order_id = o.order_id
WHERE c.customer_id = 101;
~~~

Follow the table order in EXPLAIN. The customer table may be read via const; subsequent tables may use ref or eq_ref depending on join order and selected indexes. The optimizer is free to reorder joins if the query does not lock order.

## 12. Why might the actual plan differ from expectations?

### 12.1. Table is too small

For tables with only a few rows, a full table scan can be cheaper than reading an index and jumping back to the clustered index. Hence EXPLAIN may show `ALL` even when a matching index exists.

This is a cost-based decision, not necessarily an optimizer bug.

### 12.2. Non-selective predicate

If a query returns most rows, index lookups can trigger many random reads. Scanning the entire table in physical order can be cheaper.

For instance, filtering order_status = 'PAID' might return most of the table if nearly all orders are paid. A status index will not necessarily speed up that query.

### 12.3. Statistics do not reflect data yet

The optimizer relies on statistics to estimate row counts and selectivity. After loading or deleting large volumes of data, you can run:

~~~sql
ANALYZE TABLE customer, sales_order, order_line;
~~~

Then re-run EXPLAIN and compare. Do not assume ANALYZE TABLE will always alter the plan or make queries faster.

### 12.4. Data types and expressions hindering index usage

Common issues:

- Comparing a column with a value of a different data type, causing implicit conversion.
- Wrapping an indexed column in a function such as DATE(ordered_at).
- Using LIKE with a leading wildcard such as LIKE '%2026'.
- Filtering only the second column of a composite index without constraining the leading part.
- Performing arithmetic on a column, making the predicate non-sargable.

Write predicates on indexed columns in a form that enables lookups or range scans whenever business logic permits.

### 12.5. Limitations of composite indexes

An index `(customer_id, order_status)` can serve predicates on customer_id alone or customer_id combined with order_status. It does not automatically serve queries filtering only order_status well.

Before creating new indexes, cross-check column order against actual queries and verify whether existing indexes already suffice.

## 13. Workflow for reading EXPLAIN on the job

When investigating a slow query, follow this sequence:

1. Run EXPLAIN and identify query blocks and table order.
2. Read `type` for each table, starting with the first table.
3. Cross-check `possible_keys`, `key`, `key_len`, and `ref`.
4. Read `rows` and `filtered` to spot tables with heavy read volume.
5. Check `Extra` for residual filtering, sorting, temporary tables, or covering indexes.
6. Verify whether WHERE and JOIN conditions align with index column order.
7. Run EXPLAIN ANALYZE in an appropriate environment to compare estimates with actual rows and timings.
8. Only change indexes or SQL after pinpointing the bottleneck.
9. Re-measure with identical data, parameters, and load conditions to confirm improvement.

Reference diagram:

~~~mermaid
flowchart TD
    A[Run EXPLAIN] --> B[Read table order]
    B --> C[Read type and key]
    C --> D[Check rows, filtered, Extra]
    D --> E{Scan or lookup too wide?}
    E -->|Yes| F[Inspect conditions and indexes]
    E -->|No| G[Check sort, temporary, and repeated joins]
    F --> H[Test change on representative data]
    G --> H
    H --> I[EXPLAIN ANALYZE and re-measure]
    I --> J[Compare plan, actual rows, and timing]
~~~

## 14. Common misconceptions

| Misconception | Reality | How to handle |
|---|---|---|
| const and eq_ref are the same | const reads at most one row from constants; eq_ref looks up one row per prior table combination | Check whether the table is a join input |
| Every equality condition yields const | The index may be non-unique or use only part of the key | Check index definition and key_len |
| ref always returns a single row | Non-unique indexes can return very many rows | Read rows and filtered |
| range only applies to greater/less-than operators | IN, BETWEEN, and some equality ranges can also produce range access | Inspect the access path in EXPLAIN |
| index means the query reads few rows | type=index is a full index scan | Distinguish index scan from index lookup |
| Using index is an access type | It is Extra metadata indicating covering/index-only access | Read both type and Extra |
| ALL is always a bad plan | Small tables or queries fetching most data may suit a full scan | Evaluate cost and actual rows |
| If an index exists, the optimizer always uses it | The optimizer weighs cost and selectivity | Inspect key and possible_keys |
| rows is the actual row count | It is an optimizer estimate | Use EXPLAIN ANALYZE to measure |
| key_len directly counts simple index columns | Length depends on data type, nullability, and key parts used | Cross-check index definition and charset |
| FORCE INDEX always makes queries faster | Forcing an index can yield a costlier plan | Use only for experiments or after thorough measurement |

## 15. Practice exercises

### Exercise 1: Recognizing const

Write two queries looking up a customer by PRIMARY KEY and by email via the UNIQUE index. Run EXPLAIN and explain why each query can use const.

### Exercise 2: Distinguishing const and eq_ref

Use a query joining orders to customers. Explain why customer is read per order rather than being treated as a const table.

### Exercise 3: Observing ref

Find all orders for customer_id = 101. Modify data so one customer has hundreds of orders and compare estimated rows.

### Exercise 4: Leftmost prefix

Use the `(customer_id, order_status)` index. Compare EXPLAIN for conditions with customer_id only, order_status only, and both conditions.

### Exercise 5: Time range

Write a February query using BETWEEN and using a half-open interval. Compare the plans and explain the difference regarding DATETIME boundaries.

### Exercise 6: Full index scan

Use FORCE INDEX to scan idx_customer_status. Modify the SELECT to also retrieve note, which is not in the index, and observe Extra.

### Exercise 7: Full table scan

Query by total_amount. Add a suitable index in a test environment and re-run EXPLAIN. Compare plans before and after.

### Exercise 8: Small data vs. large data

Run the same query on a table with few rows and one with many rows. Observe when the optimizer switches between ALL and an index-based access type.

### Exercise 9: Verifying estimates

Run EXPLAIN and EXPLAIN ANALYZE for a join query. Compare estimated rows with actual rows, loop counts, and timings.

### Exercise 10: Diagnosing a slow query

Pick a query with ALL or an index scan on a large table. Analyze existing indexes, propose a change, and demonstrate improvement with plans and measured metrics.

## Conclusion

`const` and `eq_ref` are lookup paths matching at most one row; `ref` uses an equality lookup that can return multiple rows; `range` reads one or more index ranges; `index` scans the entire index tree; and `ALL` scans the entire table.

Always read the `type` column together with `key`, `key_len`, `ref`, `rows`, `filtered`, and `Extra`. Then verify the actual plan with EXPLAIN ANALYZE when appropriate. A good access type does not guarantee a fast query if row counts or loop counts are huge; likewise, a full scan is not a bug if it carries the lowest cost for the data and results required.

## References

- MySQL 8.4 Reference Manual — EXPLAIN Output Format: https://dev.mysql.com/doc/refman/8.4/en/explain-output.html
- MySQL 8.4 Reference Manual — Range Optimization: https://dev.mysql.com/doc/refman/8.4/en/range-optimization.html
- MySQL 8.4 Reference Manual — EXPLAIN Statement: https://dev.mysql.com/doc/refman/8.4/en/explain.html
- MySQL 8.4 Reference Manual — How MySQL Uses Indexes: https://dev.mysql.com/doc/refman/8.4/en/mysql-indexes.html
- MySQL 8.4 Reference Manual — Multiple-Column Indexes: https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html
- MySQL 8.4 Reference Manual — Verifying Index Usage: https://dev.mysql.com/doc/refman/8.4/en/verifying-index-usage.html
