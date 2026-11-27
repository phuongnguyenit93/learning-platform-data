# possible_keys, key, key_len, and Index Usage Conditions

When reading EXPLAIN in MySQL, the three columns possible_keys, key, and key_len answer three distinct questions:

- **possible_keys**: which indexes could be considered to locate rows for the table at this step?
- **key**: which index did the optimizer actually choose?
- **key_len**: how many bytes of the index prefix are used for the chosen access path?

Do not see an index name in possible_keys and conclude the query used that index. Likewise, do not treat key_len as the total index size or the number of SELECTed columns. Read all three columns together with type, ref, rows, filtered, Extra, WHERE/JOIN conditions, and the actual index definition.

This article focuses on how MySQL determines candidate indexes, the leftmost prefix rule for composite indexes, interpreting key length, search predicates that can leverage indexes, Index Condition Pushdown (ICP), and verifying plans with EXPLAIN.

## 1. Sample table for reading plans

Create an orders table with data types that have clear byte lengths:

~~~sql
CREATE TABLE orders (
    order_id    BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status_code TINYINT UNSIGNED NOT NULL,
    created_at  DATETIME NOT NULL,
    total       DECIMAL(12, 2) NOT NULL,
    note        VARCHAR(100) NULL,
    PRIMARY KEY (order_id),
    KEY idx_customer_status_created
        (customer_id, status_code, created_at),
    KEY idx_status_created
        (status_code, created_at),
    KEY idx_created_at (created_at)
) ENGINE = InnoDB;
~~~

The indexes in this example serve different purposes:

| Index | Key part order | Typical query |
|---|---|---|
| PRIMARY | order_id | Looking up one order by primary key |
| idx_customer_status_created | customer_id, status_code, created_at | Finding a customer's orders by status and time |
| idx_status_created | status_code, created_at | Finding orders by status and time range |
| idx_created_at | created_at | Finding orders by time range |

The primary example columns are all NOT NULL and fixed-length types. This makes key_len calculations easy to observe:

- BIGINT: 8 bytes.
- TINYINT: 1 byte.
- DATETIME without fractional seconds: 5 bytes.

Therefore, the composite index (customer_id, status_code, created_at) has a declared key parts length of 14 bytes: 8 + 1 + 5. key_len in EXPLAIN may be 8, 9, or 14 depending on which portion of the index the query predicates actually use.

## 2. Inspecting the columns in EXPLAIN

Run EXPLAIN on a query:

~~~sql
EXPLAIN
SELECT order_id, customer_id, status_code, created_at, total
FROM orders
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

Traditional tabular EXPLAIN can display these columns:

| Column | Meaning |
|---|---|
| id | Order/identifier of the SELECT block |
| select_type | Type of SELECT block, such as SIMPLE or PRIMARY |
| table | Table or derived table read at this step |
| partitions | Accessed partitions if the table is partitioned |
| type | Access method such as const, eq_ref, ref, range, index, or ALL |
| possible_keys | Candidate indexes usable for finding rows |
| key | Index chosen by the optimizer |
| key_len | Length of the index portion used, in bytes |
| ref | Column or value compared against the index |
| rows | Estimated number of rows to read |
| filtered | Estimated percentage of rows remaining after filter conditions |
| Extra | Additional details such as Using where, Using index, or Using index condition |

The three columns possible_keys, key, and key_len should be read together. It is completely normal for a plan to list several indexes in possible_keys while only one index is selected in key.

## 3. possible_keys: indexes eligible for consideration

possible_keys lists the indexes the optimizer could consider to find matching rows for the table's predicates at that execution step.

Example query:

~~~sql
SELECT order_id, total
FROM orders
WHERE customer_id = 42;
~~~

Index idx_customer_status_created begins with customer_id, so it can be used. possible_keys may list this index.

With the query:

~~~sql
SELECT order_id, total
FROM orders
WHERE status_code = 2
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
~~~

idx_status_created fits because the two conditions match its leading key parts. idx_created_at can also be a candidate because the query has a range condition on created_at. The optimizer will compare the estimated costs of the options.

### 3.1. possible_keys is not a list of all indexes on the table

A table may have many indexes, yet possible_keys lists only those deemed relevant to locating rows at that step.

Example:

~~~sql
SELECT order_id, total
FROM orders
WHERE status_code = 2;
~~~

idx_status_created can be considered because its leading key part is status_code. idx_customer_status_created cannot be used to locate rows by status_code without a predicate on customer_id, due to the leftmost prefix rule.

If a query has no predicates matching any index, possible_keys can be NULL even if the table has many indexes.

### 3.2. A non-empty possible_keys does not mean an index will be used

possible_keys is a candidate list, not the final decision. The optimizer may pick a full table scan if:

- The table is small and sequential reads are cheaper than index lookups.
- The condition matches most of the rows.
- The index has low selectivity.
- The cost of reading the index plus jumping back to the clustered index exceeds a scan.
- Cardinality statistics do not accurately reflect current data.

Therefore, always read the key column to see the final choice.

## 4. key: the index chosen by the optimizer

key indicates the index MySQL actually chose to access the table in the plan.

Example:

~~~sql
EXPLAIN
SELECT order_id, total
FROM orders
WHERE customer_id = 42;
~~~

If the plan chooses idx_customer_status_created, the key column displays that index name.

If key is NULL, MySQL chose no index for the table's access path at that step. This does not automatically mean the query is broken or missing an index. A full scan might genuinely be cheaper, or the predicates might not match existing index structures.

### 4.1. Comparing possible_keys and key

| possible_keys | key | Interpretation |
|---|---|---|
| idx_a, idx_b | idx_a | Two candidates exist; the optimizer selected idx_a |
| idx_a | NULL | Index may be relevant, yet the optimizer chose not to use it |
| NULL | NULL | No suitable index listed or no index used to locate rows |
| idx_a | idx_a | The sole candidate was selected |

Actual values depend on the query, statistics, version, and data.

### 4.2. The chosen index is not necessarily the one with the fewest key parts

The optimizer weighs multiple factors:

- Estimated rows to examine.
- Cardinality and selectivity of key parts.
- Equality versus range predicates.
- Whether it must return to the clustered index to fetch missing columns.
- Whether the index can satisfy ORDER BY or GROUP BY.
- Whether index-only/covering access is possible.
- I/O cost and remaining filter evaluations.

You cannot pick an index simply by counting columns in an index or reading its name.

## 5. key_len: length of the index portion used

key_len is the byte length of the index key portion the optimizer uses to access rows. It helps identify up to which key part a composite index is being utilized.

With the sample table:

~~~sql
KEY idx_customer_status_created
    (customer_id, status_code, created_at)
~~~

Length of each key part:

| Key part | Type | Length |
|---|---|---:|
| customer_id | BIGINT UNSIGNED NOT NULL | 8 bytes |
| status_code | TINYINT UNSIGNED NOT NULL | 1 byte |
| created_at | DATETIME NOT NULL | 5 bytes |
| Total | | 14 bytes |

### 5.1. Using only the first key part

~~~sql
EXPLAIN
SELECT order_id
FROM orders
WHERE customer_id = 42;
~~~

If the optimizer chooses idx_customer_status_created, key_len is typically 8 because only customer_id is needed to locate rows.

### 5.2. Using the first two key parts

~~~sql
EXPLAIN
SELECT order_id
FROM orders
WHERE customer_id = 42
  AND status_code = 2;
~~~

The optimizer can use customer_id and status_code. key_len is typically 9 bytes (8 + 1).

### 5.3. Using all three key parts

~~~sql
EXPLAIN
SELECT order_id
FROM orders
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
~~~

The two equality predicates use the first two key parts, and the range predicate uses the created_at key part. When the optimizer uses all three parts, key_len is typically 14 bytes.

The figures above illustrate how to calculate based on the data types and sample schema. Actual results should be confirmed with EXPLAIN on the running version and query.

## 6. key_len is not the total index size

Several common misconceptions:

- key_len = 8 does not mean the index stores only 8 bytes or has only one column.
- key_len = 14 does not mean the query SELECTs 14 bytes of data.
- key_len does not measure index size on disk.
- key_len does not tell you how many columns are returned.
- key_len does not tell you whether the query has a covering index.

key_len describes the length of the key prefix used in the access path. To know whether an index contains enough columns for the query, inspect the index definition and Extra, especially Using index.

### 6.1. Nullable columns add a NULL-indicator byte

When a key part allows NULL, the key entry needs extra metadata to represent the NULL state. Consequently, key_len can be larger than the base byte size of the data type.

Example:

~~~sql
CREATE TABLE nullable_lookup (
    id BIGINT UNSIGNED NOT NULL,
    category_id INT NULL,
    PRIMARY KEY (id),
    KEY idx_category (category_id)
) ENGINE = InnoDB;
~~~

INT has a data length of 4 bytes. Because category_id is nullable, key_len can be 5 bytes: 4 bytes for data and 1 byte for the NULL flag.

If the column is changed to NOT NULL, the NULL flag byte is no longer needed.

### 6.2. VARCHAR and variable-length columns have length bytes

For variable-length columns such as VARCHAR, the key entry also includes bytes storing the value's length. The number of length bytes depends on the column's maximum byte limit:

- Up to 255 bytes: typically requires 1 length byte.
- Over 255 bytes: typically requires 2 length bytes.

If the column is nullable, there is also a NULL-indicator byte.

Example:

~~~sql
CREATE TABLE name_lookup (
    id BIGINT UNSIGNED NOT NULL,
    short_code VARCHAR(40) NOT NULL,
    long_code VARCHAR(100) NULL,
    PRIMARY KEY (id),
    KEY idx_short_code (short_code),
    KEY idx_long_code (long_code)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;
~~~

With utf8mb4, VARCHAR(40) can require up to 160 bytes of character data, plus length bytes. VARCHAR(100) can require up to 400 bytes plus 2 length bytes; since it is nullable, there is also a NULL byte. Thus key_len is not simply character count multiplied by bytes per character.

Do not calculate key_len by eye for every complex type. Use EXPLAIN as your source of truth and cross-check with data type, nullability, charset, collation, and index prefix length.

### 6.3. Prefix indexes

An index can store only a prefix of a string column:

~~~sql
CREATE INDEX idx_note_prefix
ON orders (note(20));
~~~

With a prefix index, key length is calculated from the declared prefix plus data-type overhead and NULL flag if applicable. key_len does not represent the entire VARCHAR(100).

Prefix indexes save storage space, yet multiple values can share the same prefix, forcing MySQL to check additional conditions against the full row.

## 7. The leftmost prefix rule for composite indexes

A composite index stores key parts in the order declared. With:

~~~sql
KEY idx_customer_status_created
    (customer_id, status_code, created_at)
~~~

The contiguous prefixes usable for lookups are:

- (customer_id)
- (customer_id, status_code)
- (customer_id, status_code, created_at)

You cannot use status_code alone to locate rows efficiently with this index without a condition on customer_id. Similarly, having only created_at without customer_id cannot skip the first two key parts to scan a contiguous range on created_at.

### 7.1. Typical conditions

| Query condition | Composite index usability |
|---|---|
| customer_id = 42 | Yes, uses the first key part |
| customer_id = 42 AND status_code = 2 | Yes, uses the first two key parts |
| customer_id = 42 AND status_code = 2 AND created_at >= ... | Yes, uses all three parts |
| status_code = 2 | Cannot use a prefix of this index |
| created_at >= ... | Cannot use a prefix of this index |
| customer_id = 42 AND created_at >= ... | Uses customer_id to locate; created_at may be checked via ICP |

### 7.2. Equality conditions first, range conditions after

With index (customer_id, status_code, created_at), the query:

~~~sql
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
~~~

has two equality conditions first followed by a range condition. This is the ideal shape for the designed composite index.

If a key part is skipped or already uses a range condition, trailing key parts generally do not continue narrowing the range scan in the same way consecutive equality prefixes do. However, they can still help evaluate conditions inside the index, satisfy ordering, or cover the query depending on the plan.

This is why column order in a composite index matters. Design it around actual query patterns, not merely table column order.

## 8. Which conditions can use an index?

The optimizer generally leverages indexes best when a column is compared directly against a constant or resolved value:

~~~sql
WHERE customer_id = 42
WHERE created_at >= '2026-01-01'
WHERE status_code IN (1, 2, 3)
WHERE total BETWEEN 100 AND 500
WHERE note LIKE 'urgent%'
WHERE note IS NULL
~~~

These predicates can produce lookups or range scans on a suitable index.

### 8.1. Functions on columns

The predicate:

~~~sql
WHERE DATE(created_at) = '2026-01-01'
~~~

does not produce the same access pattern on a standard index over created_at because the DATE() function wraps the column. It can be rewritten as a range:

~~~sql
WHERE created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-01-02 00:00:00'
~~~

If business logic forces querying by an expression, consider a functional index or an indexed generated column, and verify with EXPLAIN.

### 8.2. Leading wildcards in LIKE

~~~sql
WHERE note LIKE '%urgent'
~~~

cannot identify a starting point in a standard B-tree index because strings could begin with any character. Conversely:

~~~sql
WHERE note LIKE 'urgent%'
~~~

can produce a prefix range if the collation and data type allow.

### 8.3. Data type conversions

Comparing mismatched types can force MySQL to convert one side of the expression. If conversion is applied to an indexed column, index usability can drop.

For instance, if customer_id is BIGINT, passing a properly typed integer parameter is cleaner than comparing against a non-standard string. Check column types and driver bind-parameter types.

### 8.4. OR and index merge

The query:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = 42
   OR status_code = 2;
~~~

can use Index Merge if the optimizer judges combining multiple indexes beneficial. The plan may display access type index_merge. Do not assume OR always causes a full scan; likewise, do not assume Index Merge is always better than a well-chosen composite index.

## 9. Index Condition Pushdown (ICP)

Index Condition Pushdown allows MySQL to push part of the filter condition down to the storage engine to be checked against columns present in a secondary index before fetching the full row from the clustered index.

The goal is to avoid reading full rows for index entries that already fail conditions verifiable inside the index.

Example with index:

~~~sql
KEY idx_customer_status_created
    (customer_id, status_code, created_at)
~~~

Query:

~~~sql
SELECT order_id, total
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
~~~

The customer_id predicate uses the first key part to locate an index slice. status_code sits between customer_id and created_at without a predicate. Therefore, created_at cannot join a contiguous prefix to bound the range as in the earlier example.

However, created_at is still present in the secondary index. With a suitable plan, InnoDB can evaluate the created_at predicate on the index entry before jumping back to the clustered index to fetch total. EXPLAIN can display Using index condition in the Extra column.

### 9.1. Using index condition is not Using index

These two indicators mean different things:

| Extra | Meaning |
|---|---|
| Using index condition | Index Condition Pushdown is active; conditions are checked on index entries before reading full rows |
| Using index | The query can retrieve all required columns directly from the index (covering/index-only access) |
| Using where | The server still applies filter conditions after the access method |

Using index condition does not mean the query is fully covered by the index. The example above still must fetch total from the clustered record because total is not in the secondary index.

Using index also does not mean every predicate was used to bound the range. It speaks to retrieving required columns from the index, not solely how the access range was constructed.

### 9.2. When is ICP helpful?

ICP is typically beneficial when:

- The access method reads many entries from a secondary index.
- Some conditions can be evaluated on columns already stored in the index.
- Many entries are eliminated before needing to fetch the clustered record.
- The query needs columns absent from the secondary index, so remaining entries still require a full row lookup.

ICP can cut down clustered index lookups. It does not eliminate the cost of scanning the index and is no substitute for proper key column ordering.

For InnoDB, ICP applies to secondary indexes; it provides no comparable benefit on a clustered index because the full record already resides in that index.

## 10. Distinguishing Using where, Using index, and Using index condition

Example:

~~~sql
EXPLAIN
SELECT order_id, total
FROM orders
WHERE customer_id = 42
  AND status_code = 2;
~~~

If the optimizer uses the composite index to locate rows yet must still check another predicate, Extra may show Using where.

If the index holds every column required by the query, the plan may display Using index. In InnoDB, secondary indexes also store the row's primary key so they can locate clustered records; this can also make queries needing only the primary key covering.

If a predicate can be evaluated on the secondary index before fetching the full record, the plan may display Using index condition.

Extra tokens can appear in combination depending on the query and version. Do not treat a single label as a performance verdict.

## 11. Reading an example plan end to end

Query:

~~~sql
EXPLAIN
SELECT order_id, total
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

Suppose EXPLAIN outputs:

~~~text
table: orders
type: ref
possible_keys: idx_customer_status_created, idx_created_at
key: idx_customer_status_created
key_len: 8
ref: const
rows: 120
filtered: 100.00
Extra: Using index condition
~~~

This is an illustrative output to explain how to read plans, not a guaranteed output across all datasets.

Analysis:

1. possible_keys lists two candidate indexes because the query filters on customer and timestamp.
2. key is idx_customer_status_created, meaning the optimizer chose the index starting with customer_id.
3. type = ref indicates equality access on customer_id.
4. key_len = 8 shows that only the customer_id key part is used for positioning; status_code is omitted, so created_at cannot extend the prefix to narrow the lookup range.
5. rows = 120 is the estimated number of rows to read within the customer's slice, not a guaranteed actual row count.
6. Using index condition shows that the created_at predicate is evaluated on the secondary index entry before reading the clustered record to retrieve total.

If estimated rows is very high or a different index is chosen, check data distribution, statistics, and actual predicates.

## 12. Using EXPLAIN JSON and TREE

Tabular EXPLAIN is handy for quickly inspecting possible_keys, key, key_len, type, and Extra.

To view a more detailed structure:

~~~sql
EXPLAIN FORMAT=JSON
SELECT order_id, total
FROM orders
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

The JSON plan provides details on access paths, indexes, row estimates, predicates, and costs in a nested structure. Specific fields depend on plan type and version.

On MySQL 8.0.16 and later, you can view the tree format:

~~~sql
EXPLAIN FORMAT=TREE
SELECT order_id, total
FROM orders
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

TREE clarifies iterator order and relationships between steps. EXPLAIN ANALYZE is supported since MySQL 8.0.18; it executes the query and reports actual metrics. Example:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, total
FROM orders
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

EXPLAIN ANALYZE genuinely executes the SELECT and reports iterator timings, actual row counts, and loop counts. It is not merely an estimate; assess query cost and environment before running it.

## 13. Inspecting index structure and statistics

Before concluding an index is not being used, inspect the actual indexes:

~~~sql
SHOW INDEX FROM orders;
~~~

Key columns to inspect:

- Key_name: name of the index.
- Seq_in_index: position of the key part.
- Column_name: column included in the index.
- Sub_part: prefix length if the index stores only part of the column.
- Cardinality: estimated number of distinct values.
- Collation: ascending/descending order of the key part per metadata.

You can also inspect metadata via INFORMATION_SCHEMA:

~~~sql
SELECT
    INDEX_NAME,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    NON_UNIQUE,
    SUB_PART,
    CARDINALITY
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

Cardinality is an estimate. On heavily modified data, stale statistics can cause the optimizer to misjudge costs.

Update statistics:

~~~sql
ANALYZE TABLE orders;
~~~

Then re-run EXPLAIN and compare. ANALYZE TABLE updates optimizer statistics; it does not guarantee a particular index will be chosen.

## 14. Why does an index appear in possible_keys while key is NULL?

Common causes:

### 14.1. Small table

If the table has only a few rows, reading the entire table can be cheaper than opening an index and fetching clustered records. The optimizer may choose type = ALL and key = NULL.

### 14.2. Non-selective predicate

If a predicate matches most rows, an index does not meaningfully reduce rows read. A full scan can be more efficient.

### 14.3. Inaccurate statistics

Cardinality or histograms not reflecting current distribution lead to bad estimates. Check SHOW INDEX, ANALYZE TABLE, and EXPLAIN ANALYZE.

### 14.4. Index does not cover the query

If the query needs many columns outside the secondary index, MySQL may have to read clustered records for too many entries. That cost can exceed a scan.

### 14.5. Incompatible expression or data type

Functions on columns, type conversions, mismatched collations, or expressions not matching a functional index can render an index ineligible.

### 14.6. Wrongly ordered composite index

If the query filters only on the second or third key part while skipping the leading key part, the composite index may not be usable for positioning.

## 15. Analysis workflow when an index is not used

1. Run EXPLAIN on the exact SQL and representative parameters.
2. Read possible_keys, key, key_len, type, rows, filtered, and Extra.
3. Use SHOW INDEX to inspect key part ordering, prefix lengths, and cardinality.
4. Match WHERE/JOIN predicates against key part ordering and the leftmost prefix.
5. Check for functions on columns, type conversions, and collations.
6. Check whether the index is sufficiently selective and whether many clustered index lookups are required.
7. Run ANALYZE TABLE if statistics appear stale.
8. Use EXPLAIN FORMAT=JSON or TREE to inspect the detailed access path.
9. Use EXPLAIN ANALYZE to compare actual row counts and timings.
10. Only after understanding the root cause, test rewriting the query or changing indexes.

Do not add new indexes or use FORCE INDEX merely because key is currently NULL. First prove that the current scan is expensive and that the proposed index lowers cost.

## 16. When should FORCE INDEX be used?

MySQL provides index hints such as:

~~~sql
SELECT order_id, total
FROM orders FORCE INDEX (idx_customer_status_created)
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
~~~

FORCE INDEX instructs the optimizer to prioritize the specified indexes and makes table scans look prohibitively expensive during plan selection. It does not guarantee faster queries and cannot fix a poorly designed index.

Consider hints only when:

- Statistics and estimates have already been verified.
- Benchmarks prove the default choice causes stability issues.
- The specified index fits the predicates and workload.
- A monitoring plan is in place as data evolves.

Hints can backfire when data distribution or table size shifts. Prefer fixing statistics, indexes, or queries before locking the optimizer into a single choice.

## 17. Common mistakes

**"possible_keys is the index currently used."** No. That is the candidate list; key indicates the selected index.

**"key = NULL means the table has no indexes."** No. The table may have indexes, yet the optimizer found none suitable or chose a scan for lower cost.

**"key_len is the total index length."** No. It is the byte length of the key portion used for the access path.

**"key_len equals the number of columns used."** No. Each data type has its own byte size; nullable and variable-length columns also add overhead.

**"A composite index can look up by any column."** No. A B-tree composite index follows the leftmost prefix rule for positioning.

**"After a range condition, all trailing key parts are useless."** Not entirely. They usually do not narrow the range further as a contiguous prefix, but they can still support ICP, covering, or ordering.

**"Using index condition means the query is covered."** No. ICP filters index entries before fetching full rows; covering is indicated by Using index.

**"Using where is a sign of a bad query."** No. It merely indicates residual conditions are evaluated after the access method. Evaluate row counts, cost, and the actual plan.

**"EXPLAIN rows is the actual row count."** No. It is an estimate; use EXPLAIN ANALYZE to observe actual row counts and timings.

**"FORCE INDEX always fixes a plan."** No. Hints can worsen plans when data or workloads shift.

## 18. Checklist for reading possible_keys, key, and key_len

- [ ] Read the right table/row in EXPLAIN, especially in multi-table JOINs.
- [ ] Distinguished possible_keys from key.
- [ ] Identified why indexes were or were not listed.
- [ ] Checked key parts and column ordering via SHOW INDEX.
- [ ] Reconciled key_len against data types, nullability, charset, and prefix length.
- [ ] Applied the leftmost prefix rule when reading composite indexes.
- [ ] Distinguished conditions bounding the range from conditions evaluated via ICP.
- [ ] Distinguished Using index condition, Using index, and Using where.
- [ ] Read type, ref, rows, filtered, and Extra together.
- [ ] Verified statistics before forcing the optimizer.
- [ ] Used EXPLAIN ANALYZE when actual metrics were needed in a suitable environment.
- [ ] Measured index impact on both reads and writes.

## Conclusion

possible_keys shows candidate indexes considered; key shows the chosen index; key_len shows the byte length of the index portion used for access. For composite indexes, key_len helps identify up to which key part the optimizer utilized, provided you account for data types, nullability, variable-length encoding, and prefixes.

To evaluate whether a query leverages indexes effectively, combine these three columns with leftmost prefix rules, type, rows, filtered, and Extra. Separate range-bounding predicates from conditions filtered via ICP, verify statistics, and confirm with EXPLAIN ANALYZE before changing indexes or forcing the optimizer.
