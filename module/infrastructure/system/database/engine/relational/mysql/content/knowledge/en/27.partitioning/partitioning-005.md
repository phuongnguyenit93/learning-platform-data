# Partition Pruning and Prunable Filter Predicates

## Objectives

After this lesson, you will be able to:

- Explain partition pruning and why MySQL can skip partitions that contain no matching rows.
- Distinguish partition pruning from index lookup, explicit partition selection, and full scans.
- Write `WHERE` conditions aligned with the partitioning expression so the optimizer eliminates unnecessary partitions.
- Recognize how pruning behaves with `RANGE`, `LIST`, `HASH`, and `KEY`.
- Avoid expressions, type conversions, and predicates that disable pruning.
- Inspect accessed partitions using `EXPLAIN FORMAT=JSON` and version-appropriate `EXPLAIN` formats.
- Combine partition pruning with per-partition indexes.
- Understand InnoDB partitioned table limitations before designing a schema.

Examples target MySQL 8.0/8.4 with InnoDB. Actual execution plans depend on version, partition type, partitioning expression, data, statistics, and indexes.

## 1. What Is Partition Pruning?

Partitioning divides a logical table into multiple partitions. Each partition stores a subset of data according to the declared partitioning rule, such as a date range, a list of values, or a hash output.

When a query includes conditions proving that certain partitions cannot possibly contain matching rows, the optimizer can skip those partitions. This process is called **partition pruning**.

For example, consider an orders table partitioned quarterly by `created_at`. If a query only retrieves orders from Q1 2026, MySQL can read only that quarter's partition instead of searching across every partition in the table.

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01';
```

If the condition aligns with how partitions are defined, the optimizer can determine that the date range falls inside partition `p2026q1` and eliminate the other partitions from the plan.

### 1.1. Pruning Reduces the Number of Partitions Accessed

Partition pruning reduces the physical volume of data that must be examined. It is especially useful for large tables partitioned by time or a business key with clear query patterns.

Pruning does not change the logical result of an SQL statement. If the condition requires data from three partitions, MySQL must access all three partitions.

### 1.2. Pruning Does Not Mean Using an Index

Partition pruning and index access address two different layers:

- **Partition pruning:** determines which partitions may contain matching rows.
- **Index access:** locates matching rows inside the retained partitions.

A query can prune down to a single partition and still perform a full scan of that partition. Conversely, a query can use an index within each partition yet still access all partitions if there is no predicate on the partition key.

Therefore, when analyzing performance, inspect both which partitions are selected and which access method/index is used inside those partitions.

### 1.3. Pruning Differs from Manual Partition Selection

The optimizer performs pruning automatically based on query conditions. MySQL also allows specifying partitions explicitly via the `PARTITION (...)` syntax:

```sql
SELECT order_id, total_amount
FROM orders PARTITION (p2026q1)
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01';
```

This is explicit partition selection requested by the SQL author. If you omit a partition that could contain matching rows, the result will be incomplete. In normal queries, let the optimizer prune automatically and use `EXPLAIN` to verify.

## 2. Conditions for the Optimizer to Perform Pruning

The optimizer must be able to deduce from the query conditions which set of partitions could contain matching rows. The more direct and constant-evaluable the condition is, the more predictable pruning becomes.

Forms of conditions that commonly support pruning include:

- Comparing the partition key to constants with `=`, `<`, `<=`, `>`, `>=`.
- Range conditions using `BETWEEN` or lower/upper bound pairs.
- `IN (...)` with a known set of values.
- Combining conditions with `AND` or `OR` when the optimizer can resolve the branches.
- Conditions on the partitioning expression itself or forms the optimizer can deduce as equivalent.

Not every SQL expression can be transformed into a prunable partition condition. Prefer direct predicates on the partition key and verify the execution plan.

### 2.1. Direct Conditions on the Partition Key

For a table partitioned by `RANGE COLUMNS(created_at)`, the following query form is favorable:

```sql
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01'
```

The two time bounds define a contiguous range directly on the partitioning column. The optimizer can compare this interval against partition boundaries.

### 2.2. Using Half-Open Intervals for Dates and Times

For `DATETIME` or `TIMESTAMP` columns, express a day, month, or quarter as a half-open interval `[start, end)`:

```sql
WHERE created_at >= '2026-02-01 00:00:00'
  AND created_at <  '2026-03-01 00:00:00'
```

This style:

- Includes every moment from the start of February.
- Avoids guessing end-of-day timestamps like `23:59:59.999999`.
- Prevents overlap between consecutive periods.
- Expresses an exclusive upper bound clearly.

When using `TIMESTAMP`, align the session time zone with how the application sends time values. When using `DATE`, literals should match date type/semantics.

### 2.3. Conditions on Non-Partition Columns

Suppose the table is partitioned by `created_at`, but the query only specifies:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 9001;
```

The condition does not constrain `created_at`, so the optimizer generally has to examine all partitions. An index on `customer_id` can help locate the customer inside each partition, but it does not replace partition pruning.

If business logic can provide a time range, add the exact time predicate:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 9001
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
```

This query can both prune by `created_at` and use a suitable index inside the remaining partition.

## 3. Date-Based RANGE COLUMNS Example

`RANGE COLUMNS` fits when you want to partition directly on column values without writing a conversion function in the partition expression.

### 3.1. Creating a Quarterly Partitioned orders Table

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (order_id, created_at),
    KEY idx_orders_customer_created (customer_id, created_at),
    KEY idx_orders_status_created (status, created_at)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p_before_2026 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026q1      VALUES LESS THAN ('2026-04-01'),
    PARTITION p2026q2      VALUES LESS THAN ('2026-07-01'),
    PARTITION p2026q3      VALUES LESS THAN ('2026-10-01'),
    PARTITION p2026q4      VALUES LESS THAN ('2027-01-01'),
    PARTITION p_future     VALUES LESS THAN (MAXVALUE)
);
```

With `RANGE COLUMNS`, each partition holds values strictly less than its declared bound and greater than or equal to the preceding partition's bound. For example:

- `p_before_2026`: dates before `2026-01-01`.
- `p2026q1`: from `2026-01-01` up to before `2026-04-01`.
- `p2026q2`: from `2026-04-01` up to before `2026-07-01`.
- `p_future`: from `2027-01-01` onward.

### 3.2. Why Does the Primary Key Include created_at?

For a partitioned table, MySQL requires every unique key on the table, including the primary key, to contain all columns used in the partitioning expression. Therefore, the example uses:

```sql
PRIMARY KEY (order_id, created_at)
```

instead of `PRIMARY KEY (order_id)` alone.

This carries a design consequence: a unique constraint on `(order_id, created_at)` does not guarantee that `order_id` alone is unique across the entire table. If business rules require globally unique order IDs, design an appropriate ID and lookup mechanism—such as globally unique IDs generated by the application or a separate unpartitioned identity table.

InnoDB partitioned tables also do not support foreign keys under MySQL's partitioning limitations. Evaluate referential constraints before deciding to partition a table with foreign key relationships.

### 3.3. Query Fetching Only Q1 2026

```sql
SELECT order_id, created_at, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01';
```

This interval falls entirely within `p2026q1`. The optimizer can skip the remaining partitions.

### 3.4. Query Spanning Two Quarters

```sql
SELECT order_id, created_at, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-03-15'
  AND created_at <  '2026-04-15';
```

The query intersects two partitions:

- The portion from `2026-03-15` up to before `2026-04-01` belongs to `p2026q1`.
- The portion from `2026-04-01` up to before `2026-04-15` belongs to `p2026q2`.

The optimizer must access both partitions and can skip the rest.

### 3.5. Query Without Time Bounds

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE status = 'PAID';
```

There is no condition on `created_at`, so time-based partition pruning cannot happen. Even with `idx_orders_status_created`, MySQL may still have to inspect the index across all partitions.

## 4. Using Partitioning Expressions and Matching Predicates

Another design style is partitioning by an expression, such as `YEAR(created_at)`.

### 4.1. RANGE by YEAR(created_at)

```sql
CREATE TABLE yearly_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (order_id, created_at)
) ENGINE = InnoDB
PARTITION BY RANGE (YEAR(created_at)) (
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

With this table, the partitioning expression is `YEAR(created_at)`. A direct condition on the expression:

```sql
SELECT order_id, created_at, total_amount
FROM yearly_orders
WHERE YEAR(created_at) = 2026;
```

can allow the optimizer to pinpoint partition `p2026`.

### 4.2. Direct Column Conditions May Not Match the Partition Expression

If the table is partitioned by `YEAR(created_at)`, the following predicate directly matches the intent:

```sql
WHERE YEAR(created_at) = 2026
```

A range predicate on the base column:

```sql
WHERE created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
```

may be transformed by the optimizer in some cases, but do not assume every partitioning expression can be deduced from every equivalent predicate. Verify with `EXPLAIN` on your exact server version and schema. If you want predictable pruning, write predicates matching the partitioning expression or consider `RANGE COLUMNS(created_at)` to partition directly on the column.

### 4.3. Avoid Wrapping the Partition Column in a Mismatched Function

On the `orders` table partitioned with `RANGE COLUMNS(created_at)`, the query:

```sql
SELECT order_id, created_at
FROM orders
WHERE YEAR(created_at) = 2026;
```

can make pruning less straightforward because the filter expression is no longer a direct range on the partition column. Rewrite it as:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2027-01-01';
```

Predicates on the raw column allow the optimizer to compare directly against `RANGE COLUMNS` boundaries and generally favor range access on B-tree indexes.

### 4.4. Avoid Casting the Partition Column

Suppose `created_at` has type `DATE`. Compare it with matching date literals:

```sql
WHERE created_at >= DATE '2026-01-01'
  AND created_at <  DATE '2027-01-01'
```

Avoid writing expressions such as:

```sql
WHERE CAST(created_at AS CHAR) LIKE '2026%'
```

Transforming the partition column can prevent the optimizer from deducing which range partitions to keep while also reducing direct B-tree index usability. If application input is a string, parse and validate it into a `DATE`/`DATETIME` value before binding parameters.

## 5. Pruning with RANGE and LIST

### 5.1. RANGE Partitioning

`RANGE` splits data into contiguous intervals. Predicates with lower/upper bounds aligned with the partition key typically prune well.

Example:

```sql
SELECT *
FROM yearly_orders
WHERE YEAR(created_at) >= 2025
  AND YEAR(created_at) < 2027;
```

When the partitioning expression is `YEAR(created_at)`, the optimizer can keep only partitions whose year domains intersect `[2025, 2027)`.

### 5.2. LIST Partitioning

`LIST` splits data by discrete values. Example partitioning by sales region:

```sql
CREATE TABLE regional_sales (
    sale_id BIGINT NOT NULL,
    region_code CHAR(3) NOT NULL,
    sold_at DATE NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    PRIMARY KEY (sale_id, region_code)
) ENGINE = InnoDB
PARTITION BY LIST COLUMNS (region_code) (
    PARTITION p_north VALUES IN ('HN', 'HP'),
    PARTITION p_south VALUES IN ('HCM', 'CT'),
    PARTITION p_central VALUES IN ('DN', 'HU')
);
```

Query:

```sql
SELECT sale_id, region_code, amount
FROM regional_sales
WHERE region_code IN ('HCM', 'CT');
```

The optimizer can keep only partition `p_south`. With `LIST`, equality or `IN` conditions on the partition key prune easily.

A condition on `sold_at` alone does not constrain `region_code`, so it cannot prune regional partitions.

## 6. Pruning with HASH and KEY

`HASH` and `KEY` are typically used to distribute rows across a number of partitions based on hash output. They do not create human-readable time ranges or value lists like `RANGE`/`LIST`.

### 6.1. HASH Partitioning

Example:

```sql
CREATE TABLE customer_activity (
    activity_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    occurred_at DATETIME NOT NULL,
    PRIMARY KEY (activity_id, customer_id)
) ENGINE = InnoDB
PARTITION BY HASH (customer_id)
PARTITIONS 8;
```

With an equality condition on the partition expression:

```sql
SELECT activity_id, customer_id, occurred_at
FROM customer_activity
WHERE customer_id = 9001;
```

the optimizer can compute which partition holds `customer_id = 9001` and access only that partition.

A condition like `customer_id BETWEEN 9000 AND 9100` does not map to a contiguous range of partitions because hashing scatters values across partitions. The optimizer usually cannot eliminate partitions from such a range alone; check the actual plan.

### 6.2. KEY Partitioning

`KEY` uses a MySQL-provided hash function over one or more columns:

```sql
CREATE TABLE session_events (
    event_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_time DATETIME NOT NULL,
    PRIMARY KEY (event_id, tenant_id)
) ENGINE = InnoDB
PARTITION BY KEY (tenant_id)
PARTITIONS 8;
```

Equality or a known set of values on the key enables pruning:

```sql
SELECT event_id, tenant_id, event_time
FROM session_events
WHERE tenant_id = 42;
```

A query filtering only on `event_time` provides no information to pinpoint a `tenant_id` partition, so it may have to examine every partition.

### 6.3. Do Not Use HASH Expecting Range Pruning

If the workload frequently queries by month or quarter, `RANGE` by date is usually better than `HASH` by date. `HASH` scatters values rather than keeping nearby dates in contiguous partitions.

If the workload frequently queries by a specific tenant, `HASH`/`KEY` by tenant can help distribute data and prune on tenant equality. However, one large tenant can create skew; evaluate data distribution and scalability.

## 7. AND, OR, and IN in Pruning Predicates

### 7.1. Combining the Partition Key with Other Predicates via AND

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01'
  AND status = 'PAID';
```

The time predicate can prune partitions first; the `status` predicate filters rows inside the remaining partitions. Whether an index like `(status, created_at)` or `(created_at, status)` fits depends on query patterns, selectivity, and overall workload.

### 7.2. OR Across Disjoint Ranges

```sql
SELECT order_id, created_at
FROM orders
WHERE (created_at >= '2026-01-01' AND created_at < '2026-04-01')
   OR (created_at >= '2026-07-01' AND created_at < '2026-10-01');
```

The optimizer can identify the two intervals and retain only the partitions intersecting them, such as `p2026q1` and `p2026q3`. Exact pruning behavior depends on how the expression is analyzed; check `partitions` in `EXPLAIN`.

### 7.3. IN with a List of Values

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at IN ('2026-01-10', '2026-04-15', '2026-08-20');
```

With `RANGE COLUMNS` on `created_at`, values belonging to different partitions can cause the optimizer to retain only the matching set of partitions. If multiple values land in the same partition, that partition only needs to be accessed once.

### 7.4. OR Conditions Unrelated to the Partition Key

```sql
SELECT order_id, created_at, customer_id
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-04-01'
   OR customer_id = 9001;
```

Because `AND` has higher precedence than `OR`, the expression is equivalent to:

```sql
WHERE (created_at >= '2026-01-01' AND created_at < '2026-04-01')
   OR customer_id = 9001
```

The `customer_id = 9001` branch can match rows in any time partition. Thus, the optimizer cannot eliminate partitions outside Q1 based solely on the time branch. If business intent requires both conditions to hold together, use `AND`; if `OR` is genuinely required, understand that pruning may be restricted.

Always use parentheses to express Boolean logic explicitly and avoid accidentally disabling pruning.

## 8. Pruning and In-Partition Indexes

Partitioning does not replace indexes. Once pruning retains one or more partitions, MySQL still needs to find rows inside each selected partition.

### 8.1. Indexes Are Organized Per Partition

For InnoDB partitioned tables, indexes are organized locally within each partition (local indexes). MySQL does not provide a shared global index across all partitions as some other database systems do.

For example, the index:

```sql
KEY idx_orders_customer_created (customer_id, created_at)
```

is maintained inside each partition of the table. When a query prunes down to `p2026q1`, the access path uses the index within that partition. When a query must read 8 partitions, index lookups may occur in all 8 partitions.

### 8.2. Combining Pruning and Indexing

Example:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01'
  AND customer_id = 9001;
```

Logical steps:

1. Use the `created_at` predicate to eliminate partitions outside Q1.
2. Within the remaining partition, use a suitable index to locate rows for `customer_id = 9001`.
3. Read the required columns and return the result.

Without a suitable index, MySQL may full-scan the Q1 partition. Pruning reduced the number of partitions read, but not necessarily the cost inside that partition.

### 8.3. Good Index Without a Partition Key Condition

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 9001;
```

The customer index helps locate rows quickly inside each partition, yet MySQL still has to inspect many partitions because it does not know which quarters contain orders for that customer. If customer lookups without time bounds dominate the workload, time-based partitioning may offer little benefit for those queries.

This is why partition keys must be chosen according to actual workload, not just how data is stored.

## 9. Verifying Partition Pruning with EXPLAIN

Do not assume a query prunes just because `WHERE` mentions the partition key. Inspect the execution plan.

### 9.1. EXPLAIN FORMAT=JSON

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01';
```

In the JSON plan, look for the `partitions` property on the node corresponding to the `orders` table. It lists the partitions chosen by the optimizer. For the Q1 example, the list is expected to contain only `p2026q1` if the schema and boundaries match what was declared.

### 9.2. EXPLAIN PARTITIONS on Supporting Versions

You may encounter the traditional syntax:

```sql
EXPLAIN PARTITIONS
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01';
```

Tabular output includes a `partitions` column listing the accessed partitions. In newer MySQL releases, the `EXPLAIN PARTITIONS` syntax is deprecated; prefer `EXPLAIN FORMAT=JSON` for new tooling and documentation.

### 9.3. Reading Alongside key, type, and rows

In addition to `partitions`, inspect:

- `type`: access method inside partitions, such as `range`, `ref`, or `ALL`.
- `key`: chosen index.
- `key_len`: portion of the index used.
- `rows`: estimated rows read along the access path.
- `filtered`: estimated percentage of rows remaining after filtering.
- `Extra`: filter conditions, covering index, ICP, or sorting.

A plan accessing only one partition with `type = ALL` may still scan that entire partition. A plan accessing multiple partitions with `type = ref` can use an index efficiently inside each partition.

### 9.4. EXPLAIN ANALYZE

```sql
EXPLAIN ANALYZE
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01'
  AND customer_id = 9001;
```

`EXPLAIN ANALYZE` actually executes the query and reports actual row counts and timings per iterator. Use it to measure the remaining cost after partition pruning and index access.

This statement generates real execution load; use it on appropriate queries and environments rather than running heavy queries indiscriminately on production.

## 10. Conditions That Degrade Pruning Effectiveness

### 10.1. Not Filtering on the Partition Key

Queries with no predicate on the partition key generally have to examine all partitions:

```sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID';
```

If the table is partitioned by `created_at`, a status predicate does not narrow down time partitions.

### 10.2. Wrapping the Partition Column in a Mismatched Function

With `RANGE COLUMNS(created_at)`, the form:

```sql
WHERE YEAR(created_at) = 2026
```

does not directly express a range on the partition key. Rewrite it as a date range whenever possible:

```sql
WHERE created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
```

### 10.3. Type Mismatches or Casting the Column

Inputs should be bound with types matching the partition key. Casting the column or using incompatible expressions can hinder condition analysis and degrade both pruning and index access.

### 10.4. OR Expanding to Unbounded Regions

An `OR` branch without constraints on the partition key can force the optimizer to retain more partitions. Use parentheses and review condition logic before optimizing.

### 10.5. Runtime-Dependent Conditions Hard to Deduce

Predicates relying on values from another table, complex expressions, or subqueries can prevent the optimizer from resolving the partition set prior to execution. Inspect the actual plan for these cases; do not assume conditions logically equivalent to constants will always prune identically.

## 11. Prepared Statements and Time Parameters

Applications commonly send parameterized queries:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= ?
  AND created_at < ?;
```

With prepared statements, MySQL can use parameter values at execution time to determine which partitions to access in cases that support pruning. Bind parameters with proper `DATE`/`DATETIME`/`TIMESTAMP` types and verify using plans that reflect how the application executes queries.

Never concatenate date/time strings directly into SQL to build partition filters. Prepared statements prevent SQL injection and reduce formatting and type errors.

If a framework or driver emulates prepared statements client-side instead of using server-side preparation, plan observation may differ. Check the actual SQL emitted and the behavior of your connector.

## 12. Monitoring Partitions and Inspecting Definitions

### 12.1. Viewing the Table DDL

```sql
SHOW CREATE TABLE orders;
```

Inspect the `PARTITION BY` clause, partitioning expression, boundaries, and partition names. This is a quick way to verify how the live schema differs from design documentation.

### 12.2. Viewing the Partition List via INFORMATION_SCHEMA

```sql
SELECT
    PARTITION_NAME,
    PARTITION_ORDINAL_POSITION,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY PARTITION_ORDINAL_POSITION;
```

For InnoDB, `TABLE_ROWS` is an estimate, not an exact row count. `DATA_LENGTH` and `INDEX_LENGTH` provide metadata-reported size figures; use OS monitoring tools to cross-check actual file and filesystem usage.

### 12.3. Checking Which Partitions Are Accessed

Combine:

1. `SHOW CREATE TABLE` to understand partition boundaries.
2. `EXPLAIN FORMAT=JSON` to inspect partitions selected by the optimizer.
3. `EXPLAIN ANALYZE` to measure actual row counts and execution time.
4. `INFORMATION_SCHEMA.PARTITIONS` to track size and data distribution.

Do not look solely at how many partitions were pruned. A single oversized partition can still be a bottleneck; evaluate row counts, indexes, and data distribution within it.

## 13. Design Limitations to Remember

Partitioning is a schema design decision, not merely a performance tuning knob.

### 13.1. Every Unique Key Must Contain Partitioning Columns

For a partitioned table, every unique key must include all columns used in the partitioning expression. This impacts the primary key and any other unique constraints.

For example, when partitioning by `created_at`:

```sql
PRIMARY KEY (order_id, created_at)
```

can be valid, whereas:

```sql
UNIQUE KEY uq_order_id (order_id)
```

violates the rule if `created_at` is not part of the unique key.

### 13.2. InnoDB Partitioned Tables Do Not Support Foreign Keys

Foreign keys cannot be created on partitioned InnoDB tables under MySQL's partitioning limits. Nor can another table reference a partitioned InnoDB table via a foreign key.

If a schema relies heavily on FK relationships, evaluate carefully before partitioning. Never drop constraints solely to gain partition pruning without replacing them with an equivalent data integrity safeguard.

### 13.3. Partitioning Does Not Automatically Make All Queries Faster

- Queries not filtering on the partition key may have to access every partition.
- Many partitions increase metadata and planning/administrative overhead.
- Indexes still need to be designed for queries inside partitions.
- The partition key may not align with the most critical queries.
- Skewed data distribution can make one partition much larger than others.

### 13.4. Choose the Partition Key Based on Workload

Before partitioning, inventory real queries:

- How many queries filter by day/month/tenant?
- Do queries always supply the partition key?
- Is old data archived or dropped periodically?
- How large can a single partition grow?
- Are current unique keys and foreign keys compatible?
- Are queries across the entire history needed?

If most queries have no predicate on the partition key, partitioning may fail to deliver the expected pruning.

## 14. Practice Lab: Verifying Pruning Across Predicate Forms

Use the `orders` table created in section 3. Insert test rows across dates belonging to different partitions.

### Exercise 1: Single Partition

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, created_at, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01';
```

Verify whether the JSON lists only `p2026q1` under `partitions`.

### Exercise 2: Two Partitions

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, created_at, total_amount
FROM orders
WHERE created_at >= '2026-03-15'
  AND created_at <  '2026-04-15';
```

Expect the partitions intersecting the range to be `p2026q1` and `p2026q2`.

### Exercise 3: No Partition Key

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, customer_id, total_amount
FROM orders
WHERE status = 'PAID';
```

Observe which partitions the optimizer must inspect. Without a condition on `created_at`, time-based pruning is generally impossible.

### Exercise 4: Comparing Direct Predicates and Functions

```sql
-- Direct form on the partition key
EXPLAIN FORMAT=JSON
SELECT order_id
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2027-01-01';

-- Wrapping the column in a function
EXPLAIN FORMAT=JSON
SELECT order_id
FROM orders
WHERE YEAR(created_at) = 2026;
```

Compare the partition lists. Since the table uses `RANGE COLUMNS(created_at)`, direct predicates typically demonstrate clearer pruning. Record actual server output rather than assuming both plans behave identically.

### Exercise 5: Combining Pruning and Indexing

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-04-01'
  AND customer_id = 9001;
```

Check simultaneously:

- Retained partition list.
- Index selected inside the partition.
- Estimated row count.
- Remaining predicates applied.

### Exercise 6: OR with an Unbounded Partition-Key Branch

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, created_at, customer_id
FROM orders
WHERE (created_at >= '2026-01-01' AND created_at < '2026-04-01')
   OR customer_id = 9001;
```

Explain why the `customer_id = 9001` branch can require keeping partitions outside Q1.

## 15. Common Issues and How to Fix Them

| Situation | Cause | How to fix |
|---|---|---|
| Query still reads all partitions | No predicate on partition key or unprunable predicate | Add a business-valid predicate on the partition key |
| `YEAR(date_col) = ...` does not prune as expected | Partitioned on raw column or mismatched expression | Use a direct range or match the partitioning expression |
| Pruned to one partition yet query is still slow | Full scan or poor index inside that partition | Check `type`, `key`, `rows`, `EXPLAIN ANALYZE`, and index design |
| Good index exists yet many partitions are accessed | Indexes do not replace partition pruning | Add a partition key condition if business logic bounds it |
| Partition key missing from unique key | Violates partitioned table unique key rule | Redesign primary/unique keys and global identity |
| Cannot create foreign key | InnoDB partitioned tables do not support FKs | Consider not partitioning or replacing with an explicit integrity mechanism |
| `OR` disables pruning | One branch can match any partition | Use parentheses, review logic, and inspect the plan |
| `HASH` partitioned table does not prune range queries | Hashing does not preserve value order | Choose `RANGE` if the workload filters by ranges |
| Using `PARTITION (...)` misses data | The SQL author excluded a required partition | Prefer automatic pruning or verify all selected partitions |
| Trusting `TABLE_ROWS` as an exact row count | InnoDB metadata is an estimate | Use `COUNT` when exact counts are required and accept the cost |

## 16. Partition Pruning Optimization Workflow

1. **Verify the partitioning expression:** read `SHOW CREATE TABLE` and confirm the exact columns/functions used.
2. **Choose compatible predicates:** use equality, `IN`, or direct ranges on the partition key when possible.
3. **Use half-open intervals for time:** `>= start AND < end`.
4. **Avoid transforming the partition column:** do not wrap the column in unnecessary functions or casts.
5. **Audit AND/OR logic:** ensure `OR` branches do not accidentally expand across all partitions.
6. **Run `EXPLAIN`:** inspect `partitions` in JSON or a compatible format.
7. **Check in-partition indexes:** evaluate `key`, `type`, `rows`, `filtered`, and `Extra`.
8. **Measure actual execution:** use `EXPLAIN ANALYZE` appropriately to compare estimated vs. actual rows and timing.
9. **Cross-check with workload:** verify whether critical queries actually supply the partition key.
10. **Verify schema constraints:** confirm unique keys, primary keys, and foreign keys are compatible with partitioning.

## 17. Pre-Production Deployment Checklist

- [ ] Partition key and partitioning expression are clearly defined.
- [ ] Query conditions match the partitioning expression or form a prunable direct range.
- [ ] Time predicates use an inclusive lower bound and exclusive upper bound.
- [ ] Parameters are bound as proper `DATE`/`DATETIME`/`TIMESTAMP` types.
- [ ] Verified `partitions` in `EXPLAIN FORMAT=JSON`.
- [ ] Distinguished between number of partitions accessed and number of rows read inside partitions.
- [ ] Indexes inside each partition support remaining filter/JOIN conditions.
- [ ] Checked `OR` branches and function/cast expressions on the partition key.
- [ ] Evaluated workloads lacking partition key conditions.
- [ ] Every unique key includes the columns used in the partitioning expression.
- [ ] Evaluated InnoDB partitioned table foreign key restrictions.
- [ ] Checked data skew, partition count, and operational overhead.
- [ ] Measured representative queries with `EXPLAIN ANALYZE` in an appropriate environment.

## 18. Conclusion

Partition pruning allows the optimizer to skip partitions guaranteed to hold no matching rows. For effective pruning, query conditions must directly express the partition key or partitioning expression, typically via equality, `IN`, or ranges. For time-series data, half-open intervals `>= start AND < end` are clear, avoid endpoint bugs, and support range access.

`RANGE`/`LIST` fit range or discrete value-set predicates; `HASH`/`KEY` generally prune best on equality or finite value sets, without preserving order for range queries. Pruning only reduces the number of partitions examined; indexes still dictate how rows are located inside each partition. Inspect `partitions`, `key`, `type`, `rows`, and actual execution, and account for unique key and foreign key limits on InnoDB partitioned tables before moving a design to production.

## References

- [MySQL 8.4 Reference Manual: Partition Pruning](https://dev.mysql.com/doc/refman/8.4/en/partitioning-pruning.html)
- [MySQL 8.4 Reference Manual: Partitioning Types](https://dev.mysql.com/doc/refman/8.4/en/partitioning-types.html)
- [MySQL 8.4 Reference Manual: Partitioning Limitations](https://dev.mysql.com/doc/refman/8.4/en/partitioning-limitations.html)
- [MySQL 8.4 Reference Manual: EXPLAIN Output Format](https://dev.mysql.com/doc/refman/8.4/en/explain-output.html)
