# RANGE, LIST, HASH, KEY, and COLUMNS Variants

MySQL allows splitting a large table into multiple **partitions** according to predefined rules. Applications still query a single table name, while MySQL determines which partitions to read or write based on the partition key value. The four main strategies are `RANGE`, `LIST`, `HASH`, and `KEY`; `RANGE COLUMNS` and `LIST COLUMNS` are variants that allow using one or more columns directly as the partitioning key.

Choosing the right strategy depends on how data is divided: by date/number ranges, by lists of value groups, by a hash function, or by MySQL's internal hashing algorithm. Partitioning can help eliminate irrelevant partitions during queries (partition pruning) and simplify data lifecycle management. It does not replace indexing, does not automatically distribute data across multiple servers, and does not guarantee every query will be faster.

This lesson belongs to the **DATABASE_MYSQL** module. The module aims at mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, while practicing reading execution plans, optimizing queries, managing privileges, backing up, and handling relational database operational issues. Within the **Partitioning** chapter, this lesson focuses on `RANGE`, `LIST`, `HASH`, `KEY`, and the `COLUMNS` variants.

## 1. What Is Partitioning?

Partitioning divides a table's data into segments managed by the storage engine. To SQL users, the table is still referenced by a single name:

```sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE order_date >= '2026-01-01'
  AND order_date <  '2026-02-01';
```

If the table is partitioned by date, the optimizer can determine that only a subset of partitions contains data in this date range and skip the remaining partitions.

Key concepts to distinguish:

- **Partition key:** the column or expression that determines which partition a row belongs to.
- **Partition:** a segment of data within a partitioned table.
- **Partition pruning:** an optimization that eliminates partitions guaranteed not to contain matching rows.
- **Partitioned table:** a table split into partitions yet still queried as a single table.

In MySQL, partitioning is a mechanism for splitting data within the same instance/server. It is not sharding and does not automatically move partitions to other servers. With InnoDB, each partition has its own index structures; MySQL does not provide a single global index spanning across all partitions.

## 2. Choosing a Partitioning Strategy

| Strategy | How partitions are determined | Appropriate when |
|---|---|---|
| `RANGE` | Expression value falls within a range | Time-series data, sequence numbers, or numeric intervals. |
| `RANGE COLUMNS` | Value of one or more columns falls within a range | Wanting to partition directly on `DATE`, `DATETIME`, strings, or multiple columns. |
| `LIST` | Expression value belongs to a defined list | Region codes, product types, or business groups with numeric codes. |
| `LIST COLUMNS` | One or more columns belong to a list of values/tuples | Grouping by strings, dates, or multiple columns without an integer expression. |
| `HASH` | Integer expression result is hashed for distribution | Wanting relatively even distribution by a value without natural business boundaries. |
| `KEY` | MySQL applies an internal hash function on one or more columns | Wanting to distribute by columns of various data types without writing a custom hash expression. |

`RANGE`/`LIST` represent data domains defined by the designer. `HASH`/`KEY` distribute rows according to hash output. Choose a strategy based on query predicates and data retention workflows, not just row count.

## 3. RANGE Partitioning

`RANGE` splits data into non-overlapping intervals. Each partition declares an upper bound using `VALUES LESS THAN`. A value equal to the upper bound belongs to the next partition, not the current one.

Example splitting orders by year:

```sql
CREATE TABLE orders_by_year (
    order_id BIGINT NOT NULL,
    order_date DATE NOT NULL,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, order_date),
    KEY idx_customer_date (customer_id, order_date)
) ENGINE = InnoDB
PARTITION BY RANGE (YEAR(order_date)) (
    PARTITION p_before_2024 VALUES LESS THAN (2024),
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

Meaning of the partitions:

- `p_before_2024`: `YEAR(order_date) < 2024`.
- `p2024`: `2024 <= YEAR(order_date) < 2025`.
- `p2025`: `2025 <= YEAR(order_date) < 2026`.
- `p_future`: all remaining values, thanks to the `MAXVALUE` bound.

`VALUES LESS THAN (2025)` is an exclusive upper bound. Dates in 2025 are placed into `p2025`, not `p2024`.

### 3.1. Inserting and Querying Data

```sql
INSERT INTO orders_by_year
    (order_id, order_date, customer_id, total_amount)
VALUES
    (1001, '2024-12-31', 42, 150.00),
    (1002, '2025-01-01', 42, 250.00),
    (1003, '2025-08-15', 51, 300.00),
    (1004, '2026-02-10', 51, 450.00);
```

Querying using the partitioning expression itself:

```sql
SELECT order_id, order_date, total_amount
FROM orders_by_year
WHERE YEAR(order_date) = 2025;
```

A condition compatible with the `YEAR(order_date)` expression helps the optimizer identify which partition needs to be read. You can inspect selected partitions with:

```sql
EXPLAIN
SELECT order_id, order_date, total_amount
FROM orders_by_year
WHERE YEAR(order_date) = 2025;
```

In `EXPLAIN` output, the `partitions` column indicates which partitions the execution plan expects to access.

### 3.2. MAXVALUE and Managing Future Ranges

`MAXVALUE` is the highest possible bound, commonly used as a catch-all for values not yet split into dedicated partitions. Once a `MAXVALUE` partition exists, you cannot simply `ADD PARTITION` with a higher bound. To carve a new range out of the last partition, you must reorganize the partition containing `MAXVALUE` using `REORGANIZE PARTITION`.

The following example illustrates the operation structure on a lab table:

```sql
ALTER TABLE orders_by_year
REORGANIZE PARTITION p_future INTO (
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

After this operation, 2026 data belongs to `p2026`, while data from 2027 onward belongs to `p_future`. Partition DDL can move or reorganize large volumes of data; check disk space, locking duration, and operational plans before running on production tables.

## 4. RANGE COLUMNS

`RANGE COLUMNS` allows partitioning directly on the values of one or more columns. There is no need to wrap date columns in `YEAR()` or `TO_DAYS()`. It supports column types such as integers, `DATE`, `DATETIME`, and strings; arbitrary expressions are not allowed in the column list.

Example partitioning directly by date:

```sql
CREATE TABLE orders_by_date (
    order_id BIGINT NOT NULL,
    order_date DATE NOT NULL,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, order_date),
    KEY idx_customer_date (customer_id, order_date)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (order_date) (
    PARTITION p_before_2025 VALUES LESS THAN ('2025-01-01'),
    PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Querying by a date range:

```sql
SELECT order_id, order_date, total_amount
FROM orders_by_date
WHERE order_date >= '2025-04-01'
  AND order_date <  '2025-05-01';
```

A direct range condition on `order_date` aligns with `RANGE COLUMNS` boundaries, enabling the optimizer to prune partitions outside the query range.

### 4.1. Multi-Column RANGE COLUMNS

`RANGE COLUMNS` can take multiple columns. MySQL compares values lexicographically from left to right as tuples:

```sql
CREATE TABLE shipment_events (
    event_id BIGINT NOT NULL,
    event_date DATE NOT NULL,
    region_id INT NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    PRIMARY KEY (event_id, event_date, region_id)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date, region_id) (
    PARTITION p_early VALUES LESS THAN ('2025-01-01', 100),
    PARTITION p_late VALUES LESS THAN ('2026-01-01', 100),
    PARTITION p_future VALUES LESS THAN (MAXVALUE, MAXVALUE)
);
```

With the tuple `(event_date, region_id)`, `event_date` is compared first. `region_id` only breaks ties when `event_date` is equal. Therefore, this is not an independent split by region and then by year; use multiple columns only when tuple ordering matches your business boundaries.

## 5. LIST Partitioning

`LIST` places rows into partitions based on whether the expression value belongs to a declared list. Traditional `LIST` expressions must evaluate to an integer.

Example splitting by numeric region ID:

```sql
CREATE TABLE sales_by_region_id (
    sale_id BIGINT NOT NULL,
    region_id INT NOT NULL,
    sale_date DATE NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (sale_id, region_id),
    KEY idx_region_date (region_id, sale_date)
) ENGINE = InnoDB
PARTITION BY LIST (region_id) (
    PARTITION p_north VALUES IN (1, 2),
    PARTITION p_central VALUES IN (3, 4),
    PARTITION p_south VALUES IN (5, 6)
);
```

Value mapping:

- `region_id` 1 and 2 belong to `p_north`.
- `region_id` 3 and 4 belong to `p_central`.
- `region_id` 5 and 6 belong to `p_south`.

Unlike `RANGE`, `LIST` has no `MAXVALUE` bound to catch all remaining values. If you insert a `region_id` not listed in any partition, MySQL raises an error stating no matching partition was found. You must update the partition configuration whenever the business value domain expands.

### 5.1. Querying and Pruning

```sql
SELECT sale_id, sale_date, amount
FROM sales_by_region_id
WHERE region_id IN (1, 2);
```

Conditions on the partition key allow the optimizer to consider only the matching partitions if it can resolve the value set. Use `EXPLAIN` to verify the `partitions` column.

## 6. LIST COLUMNS

`LIST COLUMNS` allows using non-integer column types directly, such as `VARCHAR`, `DATE`, or numeric types. It also supports partitioning on multiple columns.

Example splitting sales by string region code:

```sql
CREATE TABLE sales_by_region (
    sale_id BIGINT NOT NULL,
    region_code VARCHAR(20) NOT NULL,
    sale_date DATE NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (sale_id, region_code),
    KEY idx_region_date (region_code, sale_date)
) ENGINE = InnoDB
PARTITION BY LIST COLUMNS (region_code) (
    PARTITION p_north VALUES IN ('NORTH', 'NORTHEAST'),
    PARTITION p_central VALUES IN ('CENTRAL'),
    PARTITION p_south VALUES IN ('SOUTH', 'SOUTHWEST')
);
```

Query:

```sql
SELECT sale_id, region_code, amount
FROM sales_by_region
WHERE region_code = 'NORTH';
```

`LIST COLUMNS` avoids having to convert string codes into integer expressions just to partition. However, the value lists still must cover every possible value that may be written.

### 6.1. Multi-Column LIST COLUMNS

Partitions can be declared using tuples of multiple columns:

```sql
CREATE TABLE regional_sales (
    sale_id BIGINT NOT NULL,
    country_code CHAR(2) NOT NULL,
    region_code VARCHAR(20) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (sale_id, country_code, region_code)
) ENGINE = InnoDB
PARTITION BY LIST COLUMNS (country_code, region_code) (
    PARTITION p_vn_north VALUES IN (('VN', 'NORTH')),
    PARTITION p_vn_south VALUES IN (('VN', 'SOUTH')),
    PARTITION p_us_north VALUES IN (('US', 'NORTH')),
    PARTITION p_us_south VALUES IN (('US', 'SOUTH'))
);
```

Each tuple `(country_code, region_code)` must match a declared list. Multi-column `LIST COLUMNS` is useful when a combination of values is a natural partitioning unit; partition count grows rapidly if too many classification dimensions are combined.

## 7. HASH Partitioning

`HASH` uses the result of an integer expression to distribute rows across a fixed number of partitions. MySQL applies an internal hash/modulo calculation based on the expression and partition count.

Example splitting orders by customer into eight partitions:

```sql
CREATE TABLE orders_by_customer_hash (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    order_date DATE NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, customer_id),
    KEY idx_customer_date (customer_id, order_date)
) ENGINE = InnoDB
PARTITION BY HASH (customer_id)
PARTITIONS 8;
```

MySQL computes the partition from `customer_id`; the user does not specify values per partition. With eight partitions, each row is distributed into one of the eight partitions based on the hash result.

### 7.1. HASH by Expression

A `HASH` expression must return an integer. For example:

```sql
CREATE TABLE events_by_month_hash (
    event_id BIGINT NOT NULL,
    event_date DATE NOT NULL,
    payload_size INT NOT NULL,
    PRIMARY KEY (event_id, event_date)
) ENGINE = InnoDB
PARTITION BY HASH (MONTH(event_date))
PARTITIONS 4;
```

This example demonstrates the syntax; it is not a good design for separating data over time because January of every year will hash from the same month value `1`. If you need to manage data by year/month and prune by date ranges, `RANGE` or `RANGE COLUMNS` is generally more appropriate.

### 7.2. HASH and Data Distribution

`HASH` does not let the designer assign specific rows to specific partitions. Distribution depends on the expression values and the number of partitions. It can help spread data evenly if input values have a suitable distribution, but it does not guarantee every partition holds the exact same number of rows.

If queries frequently filter on the partition key, the optimizer can determine which partition to read. If queries lack a corresponding predicate, MySQL may have to inspect many or all partitions.

## 8. KEY Partitioning

`KEY` also distributes rows by hashing, but MySQL chooses its own internal hash function instead of requiring the user to write an integer expression. You can use one or more columns of supported data types.

Example:

```sql
CREATE TABLE customers_by_key (
    customer_id BIGINT NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (customer_id, email),
    KEY idx_created_at (created_at)
) ENGINE = InnoDB
PARTITION BY KEY (customer_id)
PARTITIONS 8;
```

`KEY (customer_id)` uses MySQL's hashing algorithm to select a partition. Unlike `HASH`, the user does not supply an expression like `YEAR(created_at)` or `customer_id + 1`.

### 8.1. Multi-Column KEY

```sql
PARTITION BY KEY (customer_id, created_at)
PARTITIONS 8;
```

The list of columns participating in the hash affects how data is distributed. If the column list is omitted, MySQL uses the primary key if one exists; if not, it can use an eligible unique key according to `KEY` partitioning rules. In production design, explicitly declare the columns to make the partition key clear.

`KEY` is often useful when distributing by string columns or data types that are inconvenient to convert into an integer expression. Still, column selection must align with queries needing pruning and unique key constraints.

## 9. LINEAR HASH and LINEAR KEY

MySQL supports two variants: `LINEAR HASH` and `LINEAR KEY`:

```sql
PARTITION BY LINEAR HASH (customer_id)
PARTITIONS 8;
```

```sql
PARTITION BY LINEAR KEY (customer_id)
PARTITIONS 8;
```

These variants use a linear hashing algorithm, which differs from regular hash distribution. The algorithm is designed so that expanding or shrinking the partition count may require less data redistribution in certain scenarios, though data distribution can differ from standard `HASH`/`KEY`.

Do not pick `LINEAR` just because its name sounds more optimized. Evaluate partition count, key distribution, partition add/drop operations, and actual query plans.

## 10. Comparing RANGE, LIST, HASH, KEY, and COLUMNS

| Characteristic | RANGE | RANGE COLUMNS | LIST | LIST COLUMNS | HASH | KEY |
|---|---|---|---|---|---|---|
| Partition definition | Upper bound of range | Upper bound by column/tuple | List of values | List of values/tuples | Number of partitions | Number of partitions |
| Partition key | Expression | One or more columns | Expression | One or more columns | Integer expression | One or more columns |
| Direct DATE/DATETIME support | Usually needs conversion expression | Yes | Usually needs integer expression | Yes | Expression must return integer | Can use supported column types |
| Catch-all partition | Can use `MAXVALUE` | Can use `MAXVALUE` | No `MAXVALUE` | No `MAXVALUE` | Not applicable | Not applicable |
| Distribution | Ordered ranges | Ordered ranges | Value sets | Value sets | Hash expression | MySQL internal hash |
| Common use case | Range-based data lifecycle | Direct date/column partitioning | Finite numeric code groups | Finite string/tuple groups | Relatively even distribution | Column distribution without custom hash |

Note: `COLUMNS` is only a variant of `RANGE` and `LIST`. There is no `HASH COLUMNS` or `KEY COLUMNS` syntax.

## 11. Primary Key and Unique Key Constraints

This is one of the most important design constraints in MySQL partitioning: **every unique key on the table, including the primary key, must contain all columns used in the partitioning expression**.

Example table partitioned by `order_date`:

```sql
CREATE TABLE orders_partitioned (
    order_id BIGINT NOT NULL,
    order_date DATE NOT NULL,
    customer_id BIGINT NOT NULL,
    PRIMARY KEY (order_id, order_date)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (order_date) (
    PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

The primary key includes `order_date`, because it is the partition key. Declaring `PRIMARY KEY (order_id)` alone will be rejected by MySQL because the unique key does not include `order_date`.

### 11.1. Impact on Table-Wide Uniqueness

With `PRIMARY KEY (order_id, order_date)`, MySQL enforces uniqueness of the pair of values, not of `order_id` alone across all partitions. Two rows with the same `order_id` but different `order_date` values still satisfy the composite key.

If business logic requires `order_id` to be unique across the entire table, reconsider the partition key design or enforce uniqueness at the application layer or via a separate lookup table. You cannot assume a unique index solely on `order_id` will work when partitioning by `order_date`.

## 12. Important Limitations of InnoDB Partitioning

Before partitioning a business table, verify these constraints:

- InnoDB partitioned tables do not support foreign key constraints; nor can they be referenced by a foreign key on another table in the standard way.
- Every unique key must include all columns in the partitioning expression.
- Partitioning expressions must follow the syntax/functions permitted by MySQL; subqueries, stored functions, UDFs, or variables cannot be used as partition keys.
- Traditional `RANGE` and `LIST` use expressions returning integers; to use `DATE`, `DATETIME`, or strings directly, consider the `COLUMNS` variants.
- `BLOB` and `TEXT` cannot be used as partitioning columns.
- All partitions of a table share the same storage engine and the same column/index definitions.
- There is no global index across all partitions; indexes are organized per partition.

In particular, the foreign key restriction can make partitioning unsuitable for relational schemas with heavy referential integrity. Evaluate data constraints before choosing partitioning merely because a table has many rows.

## 13. Partition Pruning

Partition pruning is the optimizer's ability to skip partitions that cannot possibly contain rows matching the query predicates. This is typically the most important query benefit of partitioning.

With the `orders_by_date` table partitioned via `RANGE COLUMNS(order_date)`, the query:

```sql
EXPLAIN
SELECT order_id, order_date, total_amount
FROM orders_by_date
WHERE order_date >= '2025-04-01'
  AND order_date <  '2025-05-01';
```

can access only partition `p2025`, because the remaining partitions do not contain dates in this range.

In `EXPLAIN`, check:

- `partitions`: list of partitions accessed.
- `type`, `key`, `rows`: index access method and estimated rows inside the selected partitions.
- `Extra`: additional filter conditions or processing steps.

Partition pruning and index lookup are two separate optimization layers. Pruning reduces the number of partitions examined; indexes locate rows inside the selected partitions. A query with good pruning can still scan many rows within a partition if it lacks an appropriate index.

### 13.1. Writing Predicates Compatible with the Partition Key

If partitioned by:

```sql
PARTITION BY RANGE (YEAR(order_date))
```

then querying with the expression:

```sql
WHERE YEAR(order_date) = 2025
```

is the direct way to express the predicate against the partition expression.

If partitioned by:

```sql
PARTITION BY RANGE COLUMNS (order_date)
```

then querying directly by range:

```sql
WHERE order_date >= '2025-01-01'
  AND order_date <  '2026-01-01'
```

aligns with the partition key. Avoid wrapping the column in unnecessary functions when the goal is helping the optimizer recognize partition boundaries.

## 14. Managing and Inspecting Partitions

Inspect the table definition:

```sql
SHOW CREATE TABLE orders_by_date;
```

Inspect partition metadata:

```sql
SELECT
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders_by_date'
ORDER BY PARTITION_ORDINAL_POSITION;
```

With InnoDB, `TABLE_ROWS` is an estimate and not always an exact row count. If exact counts are needed, run `COUNT(*)` with appropriate filters while considering read cost.

Common DDL operations:

```sql
-- Add a new RANGE partition when the table does not yet have MAXVALUE
ALTER TABLE some_range_table
ADD PARTITION (
    PARTITION p2027 VALUES LESS THAN (2028)
);
```

```sql
-- Reorganize the last partition that has MAXVALUE
ALTER TABLE orders_by_year
REORGANIZE PARTITION p_future INTO (
    PARTITION p2027 VALUES LESS THAN (2028),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

```sql
-- Preview the definition and partition list
SHOW CREATE TABLE orders_by_year;
```

`DROP PARTITION` removes all data in the dropped partition. It is a destructive operation; verify the partition name, backup/retention rules, and operational approval before running it.

## 15. When Should You Use Each Strategy?

### RANGE / RANGE COLUMNS

Choose when data has natural boundaries by time, sequence, or value ranges—for example, monthly/yearly orders, daily logs, or ID ranges. `RANGE COLUMNS` fits when you want to use `DATE`/`DATETIME` and range predicates directly.

### LIST / LIST COLUMNS

Choose when values belong to predefined finite groups, such as geographic regions, tenant tiers, or business codes. You need a process to update partitions as the value catalog expands. If new values appear frequently and cannot be predicted upfront, `LIST` can cause insert failures due to missing partitions.

### HASH

Choose when you want distribution based on an integer expression and have no business boundaries suited to `RANGE`/`LIST`. Check whether queries filter on the same partition key; if not, pruning may offer little benefit.

### KEY

Choose when you want distribution across one or more columns without writing a custom integer hash expression. `KEY` is convenient when columns are strings or types that a `HASH` expression cannot use directly.

## 16. Partitioning Does Not Replace Indexes or Query Design

A table with 100 partitions does not mean a query will be 100 times faster. If a query does not filter on the partition key, MySQL may have to check every partition. If each partition lacks suitable indexes, the engine still has to scan many rows inside each partition.

Keep the roles clear:

| Mechanism | Problem solved |
|---|---|
| Partitioning | Splits data and can eliminate irrelevant partitions. |
| Index | Finds rows efficiently within data structures/partitions. |
| Query tuning | Reduces rows read, cuts computation, and improves execution order. |
| Sharding | Distributes data across multiple nodes/servers managed by application or middleware architecture. |

A small table rarely needs partitioning. Partitioning also makes schemas, unique keys, foreign keys, and DDL workflows more complex. Measure with realistic data and establish clear benefits before adopting it.

## 17. Common Mistakes

| Mistake | Consequence | How to handle |
|---|---|---|
| Using `RANGE` but leaving gaps in value ranges | Inserts outside all partitions fail | Declare contiguous bounds or `MAXVALUE` if a catch-all is needed. |
| Using `LIST` but forgetting new values | Inserts with unlisted values fail | Manage value lists and partitions alongside the release process. |
| Using `RANGE` on dates without understanding `YEAR()` | Queries with predicates not matching the expression may fail to prune as expected | Use compatible predicates or `RANGE COLUMNS`. |
| Forgetting the partition key in a unique key | DDL is rejected by MySQL | Include every column of the partition expression in all unique keys, including the PK. |
| Thinking `PRIMARY KEY(order_id, order_date)` guarantees `order_id` uniqueness | Only the `(order_id, order_date)` pair is unique | Design a table-wide uniqueness mechanism suitable for business needs. |
| Needing foreign keys on an InnoDB partitioned table | FK constraint cannot be created | Re-evaluate partitioning or the relational design. |
| Creating too many partitions | Increases metadata, optimizer, and maintenance overhead | Choose partition count based on workload and data lifecycle. |
| Assuming partitioning automatically speeds up all queries | Non-pruned queries can still read many partitions | Inspect `EXPLAIN` and per-partition indexes. |
| Confusing partitioning with sharding | Expecting data to automatically span multiple servers | Use a separate sharding architecture if multi-node distribution is needed. |
| Running `DROP PARTITION` without checking data | Loss of all rows in the partition | Verify retention, backups, and exact partition name before DDL. |

## 18. Partitioning Design Process

1. **Identify the real problem to solve.** Clarify whether it is slow queries, data lifecycle, storage size, or old-data deletion.
2. **Analyze the workload.** Profile common predicates, query time ranges, joins, and pagination patterns.
3. **Choose the partition key.** Pick columns/expressions directly tied to query filters and data lifecycle.
4. **Choose the strategy.** `RANGE` for intervals, `LIST` for value sets, `HASH`/`KEY` for distribution.
5. **Verify constraints.** Ensure every unique key contains the partition key; evaluate foreign keys and data types.
6. **Design boundaries.** Avoid gaps, overlaps, and missing values; consider `MAXVALUE` for `RANGE`.
7. **Design per-partition indexes.** Create indexes to serve queries after pruning.
8. **Test with representative data.** Include values immediately before, at, and after partition boundaries.
9. **Read `EXPLAIN`.** Check `partitions`, `key`, `type`, `rows`, and `Extra`.
10. **Plan operations.** Define schedules for adding, reorganizing, and dropping partitions, plus backups and retention.
11. **Measure the entire workload.** Compare read queries, writes, DDL, and operational overhead before and after.

## 19. Practice Exercises

### Exercise 1: Yearly RANGE

Create an orders table partitioned by `YEAR(order_date)` with partitions for 2024, 2025, and a future partition.

**Task:** insert rows on the last day of a year and the first day of the next year; identify the target partition and explain `VALUES LESS THAN` bounds.

### Exercise 2: Daily/Date RANGE COLUMNS

Create a table partitioned directly on `order_date` using `RANGE COLUMNS`.

**Task:** query a single month with a range predicate; use `EXPLAIN` to inspect the `partitions` column.

### Exercise 3: LIST by Region ID

Create a `LIST` table for numeric region IDs 1–6, then try inserting ID 7.

**Task:** observe the error when no matching partition exists and propose a process for adding new values.

### Exercise 4: LIST COLUMNS by String

Create a table partitioned by `region_code VARCHAR`, using groups `NORTH`, `CENTRAL`, and `SOUTH`.

**Task:** query a single region code and verify partition pruning.

### Exercise 5: HASH and KEY

Create two lab tables: one with `HASH(customer_id)` and one with `KEY(customer_id)`, each having eight partitions.

**Task:** compare how the partition key is declared and explain the difference between a user-specified `HASH` expression and `KEY`'s internal hash.

### Exercise 6: Multi-Column COLUMNS

Create a `RANGE COLUMNS(event_date, region_id)` or `LIST COLUMNS(country_code, region_code)` table.

**Task:** verify how MySQL compares tuples and determine which partition boundary values fall into.

### Exercise 7: Unique Keys and Partition Keys

Create a table partitioned by `order_date` while declaring only `PRIMARY KEY(order_id)`.

**Task:** observe the error, fix the primary key to include `order_date`, and explain the impact on table-wide uniqueness.

### Exercise 8: Partition Pruning

Run the same query with and without a condition on the partition key.

**Task:** compare `partitions`, `key`, and `rows` in `EXPLAIN`; explain why partitioning does not replace indexes.

## 20. Partitioning Review Checklist

- [ ] Identified the concrete problem that partitioning is meant to solve.
- [ ] Partition key aligns with query predicates and data lifecycle.
- [ ] Selected the right strategy among `RANGE`, `RANGE COLUMNS`, `LIST`, `LIST COLUMNS`, `HASH`, or `KEY`.
- [ ] `RANGE` boundaries are contiguous, non-overlapping, and handle future values.
- [ ] `LIST` covers all valid values that can be inserted.
- [ ] Understood tuple comparison behavior when using multi-column `COLUMNS`.
- [ ] Every unique key and primary key contains the partition key.
- [ ] Evaluated the impact of a composite primary key on business uniqueness.
- [ ] Verified InnoDB partitioned table foreign key restrictions.
- [ ] Per-partition indexes support queries after pruning.
- [ ] `EXPLAIN` shows only the expected partitions being accessed.
- [ ] Processes exist for adding, reorganizing, and dropping partitions.
- [ ] Checked backup/retention before `DROP PARTITION` operations.
- [ ] Measured read, write, and operational costs after partitioning.

## 21. Key Takeaways

`RANGE` splits by value intervals, `LIST` splits by lists of values, `HASH` distributes by an integer expression, and `KEY` uses MySQL's internal hash algorithm. `RANGE COLUMNS` and `LIST COLUMNS` allow using one or more columns directly, including supported date and string types.

Partitioning helps when the partition key matches query predicates or data lifecycle management workflows. Verify partition pruning with `EXPLAIN`, design proper indexes inside each partition, and remember that every unique key must include the partition key columns. With InnoDB, carefully consider foreign key limitations and table-wide uniqueness before partitioning a business table.
