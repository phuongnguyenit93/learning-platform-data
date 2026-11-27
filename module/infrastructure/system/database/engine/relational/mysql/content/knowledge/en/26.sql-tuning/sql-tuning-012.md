# Hints, FORCE/USE/IGNORE INDEX, and Version-Specific Syntax Conditions

## Lesson Objectives

After this lesson, you will be able to:

- Explain why index hints exist and when to leave decisions to the optimizer.
- Distinguish USE INDEX, FORCE INDEX, and IGNORE INDEX.
- Write correct INDEX/KEY syntax, index names, aliases, and FOR JOIN, FOR ORDER BY, and FOR GROUP BY scopes.
- Understand how MySQL combines multiple index hints, handles empty index lists, and rejects mixing USE with FORCE.
- Use comment-style optimizer hints such as JOIN_INDEX, ORDER_INDEX, GROUP_INDEX, INDEX, and NO_* variants.
- Distinguish the semantics of new optimizer index hints from traditional USE INDEX.
- Know the support milestones from MySQL 8.0.20 and compatibility status in MySQL 8.4 and 9.7.
- Verify hints using EXPLAIN, SHOW WARNINGS, and EXPLAIN ANALYZE.
- Evaluate hint impact on representative data and avoid locking in a forced plan when data changes.

The MySQL optimizer selects indexes based on query predicates, statistics, and cost estimates. In most cases, let the optimizer choose on its own. When EXPLAIN reveals it picked an unsuitable index or when a specific index stabilizes a plan in a measured workload, hints can restrict its choices.

There are two common syntax families:

1. Traditional index hints placed after the table name, such as USE INDEX, FORCE INDEX, and IGNORE INDEX.
2. Optimizer hints placed inside a special comment after SELECT, UPDATE, INSERT, REPLACE, or DELETE, such as JOIN_INDEX and NO_ORDER_INDEX.

The two groups differ in scope and precedence. Understand these differences clearly before introducing hints into application code.

## 1. When Should You Use Index Hints?

An index hint guides the optimizer on which indexes may or may not be considered. It does not create new indexes or change data structures.

A hint can be useful when:

- EXPLAIN shows the optimizer picking a low-selectivity index when a much better index exists.
- Statistics do not accurately reflect data distribution and you need to test an alternative access path.
- A query has competing indexes and you want to restrict choices to validate a hypothesis.
- You need to measure the effect of excluding an index from the plan.
- You need to separate the index used for row lookup from the index used for ORDER BY or GROUP BY.

Never add a hint just because you see type = ALL or because you believe using an index is always faster. A table scan can be cheaper when the table is small or a query needs most of the rows. Hints never replace checking statistics, filter predicates, data types, composite index column order, and actual row counts.

A sensible workflow:

1. Run EXPLAIN and record the current plan.
2. Identify which indexes can satisfy the predicates properly.
3. Test the hint in a test environment.
4. Compare access type, key, rows, Extra, and actual execution time.
5. Test across multiple parameter values and data distributions.
6. Keep the hint only if the improvement is stable and clearly justified.

## 2. Prepare Practice Tables

The examples use an InnoDB orders table with multiple indexes serving different purposes.

~~~sql
CREATE TABLE sales_order_hint_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    ordered_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    region_code VARCHAR(12) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_customer_status (customer_id, order_status),
    KEY idx_status (order_status),
    KEY idx_ordered_at (ordered_at),
    KEY idx_total_amount (total_amount),
    KEY idx_region_ordered (region_code, ordered_at)
) ENGINE = InnoDB;

CREATE TABLE customer_hint_demo (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;
~~~

Load some sample data:

~~~sql
INSERT INTO sales_order_hint_demo (
    order_id,
    customer_id,
    order_status,
    ordered_at,
    total_amount,
    region_code
)
VALUES
    (7001, 101, 'PAID',      '2026-02-01 09:15:00', 1250000.00, 'NORTH'),
    (7002, 101, 'PAID',      '2026-02-03 11:30:00', 2400000.00, 'NORTH'),
    (7003, 102, 'PENDING',   '2026-02-08 14:00:00',  890000.00, 'SOUTH'),
    (7004, 103, 'PAID',      '2026-02-15 16:45:00', 3400000.00, 'NORTH'),
    (7005, 101, 'CANCELLED', '2026-02-18 10:20:00',  450000.00, 'NORTH'),
    (7006, 104, 'PAID',      '2026-03-02 08:10:00', 5100000.00, 'CENTRAL'),
    (7007, 102, 'PENDING',   '2026-03-05 13:25:00',  760000.00, 'SOUTH'),
    (7008, 103, 'PAID',      '2026-03-10 17:05:00', 1750000.00, 'NORTH'),
    (7009, 105, 'PAID',      '2026-03-14 10:00:00',  980000.00, 'EAST'),
    (7010, 106, 'PENDING',   '2026-03-20 12:30:00', 2150000.00, 'EAST');

INSERT INTO customer_hint_demo (customer_id, customer_name)
VALUES
    (101, 'Nguyen An'),
    (102, 'Tran Binh'),
    (103, 'Le Chi'),
    (104, 'Pham Dung');
~~~

Check index names:

~~~sql
SHOW INDEX FROM sales_order_hint_demo;
~~~

Index names—not column names—are passed to hints. The primary key is referenced by the name PRIMARY. Examples may yield different plans depending on row count, statistics, version, and configuration; tiny tables commonly cause the optimizer to pick a table scan.

## 3. Traditional Index Hint Syntax

Index hints are placed immediately after the table name and alias in a table reference.

General syntax:

~~~text
tbl_name [[AS] alias] [index_hint_list]

index_hint_list:
    index_hint [index_hint] ...

index_hint:
    USE {INDEX|KEY}
      [FOR {JOIN|ORDER BY|GROUP BY}] (index_list)
  | {IGNORE|FORCE} {INDEX|KEY}
      [FOR {JOIN|ORDER BY|GROUP BY}] (index_list)

index_list:
    index_name [, index_name] ...
~~~

INDEX and KEY are interchangeable synonyms in this syntax.

Example:

~~~sql
SELECT
    o.order_id,
    o.total_amount
FROM sales_order_hint_demo AS o
USE INDEX (idx_customer_status)
WHERE o.customer_id = 101;
~~~

The hint attaches to the table reference sales_order_hint_demo with alias o. When using an alias, keep the alias consistent across the query. For comment-style optimizer hints, the table name referenced in the hint must also match the alias active in the query block.

### 3.1. Index Name, Not Column Name

Suppose there is an index:

~~~text
KEY idx_customer_status (customer_id, order_status)
~~~

The valid name in the hint is idx_customer_status:

~~~sql
SELECT *
FROM sales_order_hint_demo
USE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

The following is wrong because customer_id is a column name, not an index name:

~~~sql
SELECT *
FROM sales_order_hint_demo
USE INDEX (customer_id)
WHERE customer_id = 101;
~~~

To reference the PRIMARY KEY, use PRIMARY:

~~~sql
SELECT *
FROM sales_order_hint_demo
FORCE INDEX (PRIMARY)
WHERE order_id = 7001;
~~~

MySQL permits an unambiguous prefix of an index name, yet you should write the full name to avoid collisions when indexes are added later.

## 4. USE INDEX: Restrict the Set of Considered Indexes

USE INDEX tells MySQL to consider only the listed indexes when looking up rows in the table. Any index omitted from the list is excluded from the candidate set for that scope.

Example:

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    order_status
FROM sales_order_hint_demo AS o
USE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

USE INDEX does not force MySQL to use a listed index at all costs. The optimizer can still pick a table scan if it estimates a scan is cheaper or if no listed index applies to the predicates.

Key points:

- Only listed indexes are considered for the hint's scope.
- A table scan remains eligible.
- Multiple indexes can be listed.
- USE INDEX is suited for narrowing candidates, not forcefully banning table scans.

### 4.1. USE INDEX with an Empty List

The syntax USE INDEX () is valid and means use no indexes for that scope:

~~~sql
EXPLAIN
SELECT *
FROM sales_order_hint_demo AS o
USE INDEX ()
WHERE customer_id = 101;
~~~

This provides a baseline comparison against a table scan. Use it only on small tables or test environments; never apply it carelessly to large tables.

An empty list is invalid for FORCE INDEX or IGNORE INDEX. Both of those require at least one index name.

## 5. FORCE INDEX: Make Table Scans Appear Very Expensive

FORCE INDEX behaves similarly to USE INDEX, while adding the assumption that a table scan is very costly. MySQL falls back to a table scan only if there is no way to use any of the specified indexes to find rows.

Example:

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    order_status
FROM sales_order_hint_demo AS o
FORCE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

Comparison with USE INDEX:

| Trait | USE INDEX | FORCE INDEX |
|---|---|---|
| Restricts candidate indexes | Yes | Yes |
| Table scan still eligible | Yes, by cost | Only when no listed index can be used |
| Strength | Narrows candidate set | Stronger, assigns very high cost to scans |
| Guarantees index is always used | No | No, if the index is inapplicable |

FORCE INDEX cannot make an index applicable to predicates it does not support. For instance, if an index covers only customer_id while the query filters on a different unindexed column with no usable access path, MySQL must still scan the table.

Never think of FORCE INDEX as commanding the storage engine to read an index regardless of query predicates.

## 6. IGNORE INDEX: Exclude Indexes from Consideration

IGNORE INDEX instructs MySQL not to consider the specified indexes within the hint's scope.

Example:

~~~sql
EXPLAIN
SELECT
    order_id,
    order_status,
    total_amount
FROM sales_order_hint_demo AS o
IGNORE INDEX (idx_status)
WHERE order_status = 'PAID';
~~~

MySQL may consider another index, index merge if applicable, or a table scan. IGNORE INDEX does not specify a replacement index.

Use IGNORE INDEX when evidence shows a specific index leads the optimizer to a poor plan. Re-evaluate after data or statistics change because an index ignored today may become helpful for tomorrow's workload.

### 6.1. Compare All Three Hints on the Same Query

~~~sql
EXPLAIN
SELECT *
FROM sales_order_hint_demo
USE INDEX (idx_status)
WHERE order_status = 'PAID';

EXPLAIN
SELECT *
FROM sales_order_hint_demo
FORCE INDEX (idx_status)
WHERE order_status = 'PAID';

EXPLAIN
SELECT *
FROM sales_order_hint_demo
IGNORE INDEX (idx_status)
WHERE order_status = 'PAID';
~~~

Record type, possible_keys, key, rows, and Extra. On a tiny table, the optimizer may still scan with USE INDEX; FORCE INDEX prices the scan higher; IGNORE INDEX drops idx_status from consideration.

No single fixed output applies to all servers because plans depend on data and cost models.

## 7. FOR JOIN, FOR ORDER BY, and FOR GROUP BY Scopes

An index can help locate rows, sort data, or group data. Those three phases may need different indexes.

### 7.1. FOR JOIN

FOR JOIN affects indexes considered when looking up rows and executing joins. Omitting the FOR clause applies the hint to all phases of the statement.

Example:

~~~sql
EXPLAIN
SELECT
    order_id,
    order_status
FROM sales_order_hint_demo AS o
USE INDEX FOR JOIN (idx_customer_status)
WHERE customer_id = 101;
~~~

FOR JOIN is the scope to specify explicitly when you only want to control the index used for row lookup and JOIN processing. Omitting FOR applies the hint to JOIN, ORDER BY, and GROUP BY together.

### 7.2. FOR ORDER BY

FOR ORDER BY affects indexes used for sorting.

~~~sql
EXPLAIN
SELECT
    order_id,
    ordered_at,
    total_amount
FROM sales_order_hint_demo AS o
USE INDEX FOR ORDER BY (idx_ordered_at)
ORDER BY ordered_at DESC
LIMIT 5;
~~~

This hint influences index choice for ORDER BY. It does not force that index to be used for WHERE row lookups.

### 7.3. FOR GROUP BY

FOR GROUP BY affects indexes used for GROUP BY processing.

~~~sql
EXPLAIN
SELECT
    order_status,
    COUNT(*) AS order_count
FROM sales_order_hint_demo AS o
USE INDEX FOR GROUP BY (idx_status)
GROUP BY order_status;
~~~

If the index does not fit the predicates or grouping, MySQL may still need another execution strategy. Inspect EXPLAIN to verify whether the hint actually changed anything.

### 7.4. No FOR Clause Means All Scopes

Example:

~~~sql
SELECT *
FROM sales_order_hint_demo
IGNORE INDEX (idx_status)
WHERE order_status = 'PAID'
ORDER BY ordered_at;
~~~

IGNORE INDEX without a FOR clause excludes idx_status for JOIN, ORDER BY, and GROUP BY alike.

If you only want to exclude an index during sorting, state it explicitly:

~~~sql
SELECT *
FROM sales_order_hint_demo
IGNORE INDEX FOR ORDER BY (idx_status)
WHERE order_status = 'PAID'
ORDER BY ordered_at;
~~~

Picking the exact scope prevents unintended effects on row lookups or grouping.

### 7.5. FULLTEXT Exceptions

Index hints follow special rules for FULLTEXT searches:

- In `IN NATURAL LANGUAGE MODE`, index hints are silently ignored; for example, IGNORE INDEX does not stop MySQL from using a FULLTEXT index.
- In `IN BOOLEAN MODE`, hints with `FOR ORDER BY` or `FOR GROUP BY` are silently ignored.
- In boolean mode, hints with `FOR JOIN` or without a FOR clause apply to all query processing phases, including row retrieval, grouping, and sorting.

This is an exception to how JOIN/ORDER BY/GROUP BY scopes work in standard queries. If a query uses `MATCH(...) AGAINST(... IN BOOLEAN MODE)`, verify with EXPLAIN rather than inferring behavior from the FOR clause alone.

## 8. Combining Multiple Index Hints

MySQL permits multiple index hints on the same table reference. Hints are collected by type and scope.

Example:

~~~sql
SELECT
    order_id,
    customer_id,
    order_status,
    ordered_at
FROM sales_order_hint_demo AS o
USE INDEX FOR JOIN (idx_customer_status)
USE INDEX FOR ORDER BY (idx_ordered_at)
WHERE customer_id = 101
ORDER BY ordered_at DESC;
~~~

Here:

- idx_customer_status is restricted for row lookup and joins.
- idx_ordered_at is restricted for ORDER BY.

Key syntax rules:

- Naming the same index multiple times is allowed and not automatically an error.
- Lists of the same type and scope are merged.
- IGNORE INDEX is applied after USE INDEX or FORCE INDEX.
- Without a FOR clause, the hint applies to all scopes.
- Mixing USE INDEX and FORCE INDEX on the same table reference is a syntax error under index hint rules.

Invalid example:

~~~sql
SELECT *
FROM sales_order_hint_demo
USE INDEX FOR JOIN (idx_customer_status)
FORCE INDEX FOR JOIN (idx_ordered_at)
WHERE customer_id = 101;
~~~

If you need a different hint strength, choose one uniform hint type for the table reference instead of mixing USE and FORCE.

### 8.1. IGNORE Is Applied After USE or FORCE

~~~sql
SELECT *
FROM sales_order_hint_demo
USE INDEX (idx_customer_status, idx_status)
IGNORE INDEX (idx_status)
WHERE customer_id = 101;
~~~

The resulting list contains idx_customer_status. idx_status was removed by IGNORE INDEX.

### 8.2. Listed Indexes Must Make Sense for the Query

Listing an index does not magically make it support incompatible predicates. For example, index (customer_id, order_status) can support customer_id or customer_id plus order_status via its leftmost prefix. It does not naturally become a good access path for a query filtering solely on order_status.

Before forcing an index, check its definition via SHOW INDEX and verify column order.

## 9. Comment-Style Optimizer Index Hints Since MySQL 8.0.20

Starting in MySQL 8.0.20, MySQL supports index-level optimizer hints. This family is designed to gradually replace FORCE INDEX and IGNORE INDEX respectively.

Primary hints:

| Optimizer hint | Scope | Traditional index hint equivalent |
|---|---|---|
| JOIN_INDEX | Row lookup and joins | FORCE INDEX FOR JOIN |
| NO_JOIN_INDEX | Exclude index from lookup/join | IGNORE INDEX FOR JOIN |
| ORDER_INDEX | Sorting | FORCE INDEX FOR ORDER BY |
| NO_ORDER_INDEX | Exclude index from sorting | IGNORE INDEX FOR ORDER BY |
| GROUP_INDEX | Grouping | FORCE INDEX FOR GROUP BY |
| NO_GROUP_INDEX | Exclude index from grouping | IGNORE INDEX FOR GROUP BY |
| INDEX | All scopes | FORCE INDEX |
| NO_INDEX | Exclude index from all scopes | IGNORE INDEX |

General syntax:

~~~sql
SELECT /*+ JOIN_INDEX(table_alias index_name) */
    ...
FROM table_name AS table_alias;
~~~

Optimizer hints must appear inside a special comment starting with /*+ placed immediately after the statement keyword or at the start of a query block.

### 9.1. JOIN_INDEX and NO_JOIN_INDEX

JOIN_INDEX restricts indexes used across all access methods within the JOIN scope, such as ref, range, or index_merge.

~~~sql
EXPLAIN
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id,
    o.customer_id,
    o.order_status
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

Exclude an index from the JOIN scope:

~~~sql
EXPLAIN
SELECT /*+ NO_JOIN_INDEX(o idx_status) */
    o.order_id,
    o.order_status
FROM sales_order_hint_demo AS o
WHERE o.order_status = 'PAID';
~~~

The name o in the hint must match the table alias in that query block.

### 9.2. ORDER_INDEX and GROUP_INDEX

ORDER_INDEX influences the index used for sorting:

~~~sql
EXPLAIN
SELECT /*+ ORDER_INDEX(o idx_ordered_at) */
    o.order_id,
    o.ordered_at
FROM sales_order_hint_demo AS o
ORDER BY o.ordered_at DESC
LIMIT 5;
~~~

GROUP_INDEX influences index scans for GROUP BY:

~~~sql
EXPLAIN
SELECT /*+ GROUP_INDEX(o idx_status) */
    o.order_status,
    COUNT(*) AS order_count
FROM sales_order_hint_demo AS o
GROUP BY o.order_status;
~~~

These hints correspond to FORCE INDEX in their respective scopes, not USE INDEX.

### 9.3. INDEX and NO_INDEX

INDEX combines JOIN_INDEX, GROUP_INDEX, and ORDER_INDEX. It applies across all scopes.

~~~sql
EXPLAIN
SELECT /*+ INDEX(o idx_customer_status) */
    o.order_id,
    o.customer_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

NO_INDEX excludes an index from all scopes:

~~~sql
EXPLAIN
SELECT /*+ NO_INDEX(o idx_status) */
    o.order_id,
    o.order_status
FROM sales_order_hint_demo AS o
WHERE o.order_status = 'PAID';
~~~

Do not confuse INDEX with USE INDEX. INDEX has FORCE INDEX semantics: a table scan is chosen only if there is no way to use any listed index to find rows.

### 9.4. Why Do New Optimizer Hints Lack a Direct USE INDEX Equivalent?

JOIN_INDEX, ORDER_INDEX, GROUP_INDEX, and INDEX carry FORCE INDEX semantics. The NO_* variants correspond to IGNORE INDEX.

Consequently, no single optimizer hint captures the exact semantics of narrowing the candidate index list while still letting table scans compete on cost like USE INDEX.

To mimic USE INDEX, you must exclude all other indexes using NO_* and leave only the desired index. For example, to allow only idx_ordered_at in the ORDER BY scope, list every other index to exclude:

~~~sql
SELECT /*+ NO_ORDER_INDEX(
    o PRIMARY,
    idx_customer_status,
    idx_status,
    idx_total_amount,
    idx_region_ordered
) */
    o.order_id,
    o.ordered_at
FROM sales_order_hint_demo AS o
ORDER BY o.ordered_at DESC;
~~~

This approach requires updates whenever indexes are added or dropped from the schema. If the goal is simply narrowing candidates while letting table scans compete, traditional USE INDEX expresses it more directly.

## 10. Query Blocks, Aliases, and Optimizer Hint Placement

Optimizer hints can target a table in the current query block or a named query block.

Simple example:

~~~sql
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

If the table has alias o, use o in the hint. Using the base table name instead of the alias can prevent the hint from applying as intended.

With nested queries, name query blocks using QB_NAME:

~~~sql
SELECT /*+ QB_NAME(main_qb) */
    o.order_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id IN (
    SELECT /*+ QB_NAME(customer_qb) */
        x.customer_id
    FROM sales_order_hint_demo AS x
    WHERE x.region_code = 'NORTH'
);
~~~

Then a hint can reference a query block:

~~~sql
SELECT /*+ QB_NAME(main_qb)
           JOIN_INDEX(@main_qb o idx_customer_status) */
    o.order_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

Query block syntax is helpful when dealing with subqueries, derived tables, CTEs, or multiple tables sharing aliases across different query blocks.

### 10.1. Hint Comment Placement

With SELECT:

~~~sql
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

With UPDATE:

~~~sql
UPDATE /*+ JOIN_INDEX(o idx_customer_status) */
    sales_order_hint_demo AS o
SET order_status = 'PAID'
WHERE o.customer_id = 101;
~~~

Optimizer hints must follow the respective statement keyword. Ordinary comments /* ... */ without the plus sign are not treated as optimizer hints by the parser.

Do not place an optimizer hint arbitrarily in the middle of a SELECT expression or after WHERE and expect it to take effect.

## 11. Precedence Between Index Hints and Optimizer Hints

Traditional index hints and optimizer hints can appear together, yet they do not always act independently.

Important rules in MySQL 8.4:

- If a statement contains at least one index-level optimizer hint (JOIN_INDEX, GROUP_INDEX, ORDER_INDEX, INDEX, or NO_* variants), any traditional USE INDEX, FORCE INDEX, and IGNORE INDEX hints in the same statement are ignored. This compatibility rule is documented in the MySQL 8.0.20 Release Notes.
- Within optimizer hints, index-level hints take precedence over other optimizer hints, including other index-level hints; remaining hints operate only within the index set permitted by the index-level hints.
- When no index-level optimizer hint overrides them, USE INDEX, FORCE INDEX, and IGNORE INDEX take precedence over INDEX_MERGE and NO_INDEX_MERGE optimizer hints.
- Inapplicable hints may be ignored; writing a hint does not guarantee the optimizer can construct that access path.

Avoid mixing multiple control mechanisms just to force a plan. If a statement has conflicting hints, inspect SHOW WARNINGS and EXPLAIN to verify which hint took effect; in particular, never expect traditional index hints to remain active when index-level optimizer hints are present in the same statement.

## 12. Syntax Differences Across MySQL Versions

### 12.1. Before MySQL 8.0.20

Traditional index hints USE INDEX, FORCE INDEX, and IGNORE INDEX existed in older MySQL versions, including MySQL 5.7 and 8.0 releases prior to 8.0.20.

In these versions, do not use JOIN_INDEX, ORDER_INDEX, GROUP_INDEX, or INDEX optimizer hints because the new index-level optimizer hint family is not yet supported.

### 12.2. MySQL 8.0.20

MySQL 8.0.20 added:

- JOIN_INDEX and NO_JOIN_INDEX.
- GROUP_INDEX and NO_GROUP_INDEX.
- ORDER_INDEX and NO_ORDER_INDEX.
- INDEX and NO_INDEX.

The new hints are designed to replace FORCE INDEX and IGNORE INDEX respectively. The MySQL 8.0.20 documentation notes that traditional index hints are expected to be deprecated in a future release and may eventually be removed.

Key point: 8.0.20 is the milestone that introduced the new optimizer hints, not the milestone that removed USE/FORCE/IGNORE INDEX syntax.

### 12.3. MySQL 8.4 and 9.7

The MySQL 8.4 and 9.7 manuals still document and support USE INDEX, FORCE INDEX, and IGNORE INDEX syntax. At the same time, they recommend migrating toward JOIN_INDEX, GROUP_INDEX, ORDER_INDEX, INDEX, and NO_* variants.

Do not claim that USE/FORCE/IGNORE INDEX were removed in 8.4 or 9.7. Current documentation states they are expected to be deprecated in a future version and possibly removed afterward.

If your application supports multiple versions, verify the minimum server version before introducing the new index-level optimizer hints into SQL. A query using JOIN_INDEX will fail to run on servers older than 8.0.20.

### 12.4. Compatibility Summary Table

| Version | USE/FORCE/IGNORE INDEX | JOIN_INDEX, ORDER_INDEX, GROUP_INDEX, INDEX |
|---|---|---|
| MySQL 5.7 | Yes | No |
| MySQL 8.0 before 8.0.20 | Yes | New hint family not yet available |
| MySQL 8.0.20 and later | Yes | Yes |
| MySQL 8.4 | Yes, still documented | Yes, recommended as gradual replacement |
| MySQL 9.7 | Yes, still documented | Yes, recommended as gradual replacement |

When deploying across mixed environments, choose syntax compatible with the lowest version or branch SQL by server version.

## 13. Limitations by Statement Type

Traditional index hints:

- Supported in SELECT.
- Supported in UPDATE.
- Supported in multi-table DELETE syntax.
- Not supported in single-table DELETE under traditional index hint syntax.

Multi-table DELETE example:

~~~sql
EXPLAIN DELETE o
FROM sales_order_hint_demo AS o
IGNORE INDEX FOR JOIN (idx_status)
JOIN customer_hint_demo AS c
    ON c.customer_id = o.customer_id
WHERE o.order_status = 'CANCELLED';
~~~

This statement illustrates index hint placement in a multi-table DELETE and uses EXPLAIN to inspect the plan without deleting rows. If EXPLAIN is removed to execute the DELETE, CANCELLED orders belonging to customers present in customer_hint_demo will be deleted; run only on a practice database after confirming data scope.

The newer index-level optimizer hints are documented to support both single-table and multi-table DELETE. Therefore, if a hint is needed for a single-table DELETE, check compatibility of JOIN_INDEX/NO_JOIN_INDEX or INDEX/NO_INDEX on your target version.

## 14. Verifying Whether a Hint Was Actually Used

Never assume a hint took effect just because the SQL ran without error.

### 14.1. Use EXPLAIN

~~~sql
EXPLAIN
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id,
    o.customer_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

Check:

- type: did the access type change?
- possible_keys: which indexes were considered?
- key: which index was selected?
- key_len: how much of the index was used?
- rows: how did estimated rows change?
- Extra: are there Using index, Using where, or Using filesort?

With TREE:

~~~sql
EXPLAIN FORMAT=TREE
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id,
    o.customer_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

### 14.2. Use SHOW WARNINGS

Inspect hint diagnostics immediately after EXPLAIN:

~~~sql
EXPLAIN
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;

SHOW WARNINGS;
~~~

Extended EXPLAIN output can show which optimizer hints were applied. Ignored hints do not appear in this extended note. Duplicate or conflicting hints may emit warnings.

If a hint does not appear or fails to alter the plan, check:

- Are the table name and alias in the hint exact?
- Does the index name exist?
- Is the hint supported on the current server version?
- Is the query block targeted correctly?
- Does the index apply to the predicates?
- Is a higher-precedence hint overriding another?

### 14.3. Use EXPLAIN ANALYZE to Measure Actual Execution

EXPLAIN shows only the plan and estimates. To measure actual time and rows, run EXPLAIN ANALYZE on a SELECT with acceptable cost:

~~~sql
EXPLAIN ANALYZE
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id,
    o.total_amount
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

Compare actual rows, loops, and timing before and after the hint. Never run EXPLAIN ANALYZE carelessly on heavy production queries because it executes the SELECT.

## 15. Hands-On Comparison: USE, FORCE, IGNORE, and Optimizer Hints

### Lab 1: Capture the Default Plan

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    order_status
FROM sales_order_hint_demo
WHERE customer_id = 101;
~~~

Record type, key, rows, and Extra. This is the comparison baseline.

### Lab 2: Narrow Indexes with USE INDEX

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    order_status
FROM sales_order_hint_demo
USE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

Compare against the baseline. Determine whether a table scan is still allowed.

### Lab 3: Penalize Table Scan Cost with FORCE INDEX

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    order_status
FROM sales_order_hint_demo
FORCE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

Compare key and type against USE INDEX. Explain why FORCE INDEX can make the optimizer choose the index even on a small table.

### Lab 4: Exclude an Index with IGNORE INDEX

~~~sql
EXPLAIN
SELECT
    order_id,
    order_status,
    total_amount
FROM sales_order_hint_demo
IGNORE INDEX (idx_status)
WHERE order_status = 'PAID';
~~~

Check whether the optimizer picks another index or a table scan.

### Lab 5: Control Only ORDER BY

~~~sql
EXPLAIN
SELECT
    order_id,
    ordered_at
FROM sales_order_hint_demo
USE INDEX FOR ORDER BY (idx_ordered_at)
ORDER BY ordered_at DESC
LIMIT 5;
~~~

Explain why FOR ORDER BY does not force an index for WHERE.

### Lab 6: Control Only GROUP BY

~~~sql
EXPLAIN
SELECT
    order_status,
    COUNT(*)
FROM sales_order_hint_demo
USE INDEX FOR GROUP BY (idx_status)
GROUP BY order_status;
~~~

Observe the plan and Extra. Check whether the index helps group rows more efficiently.

### Lab 7: Use New Optimizer Hints

~~~sql
EXPLAIN
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id,
    o.customer_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

Compare against FORCE INDEX FOR JOIN.

### Lab 8: Exclude an Index with NO_JOIN_INDEX

~~~sql
EXPLAIN
SELECT /*+ NO_JOIN_INDEX(o idx_status) */
    o.order_id,
    o.order_status
FROM sales_order_hint_demo AS o
WHERE o.order_status = 'PAID';
~~~

Identify the excluded index and the fallback plan.

### Lab 9: Check Server Version

~~~sql
SELECT VERSION() AS mysql_version;
~~~

Run queries using JOIN_INDEX on MySQL 8.0.20 or later. If supporting 8.0.19 or earlier, switch to compatible traditional index hints.

### Lab 10: Compare Actual Execution Time

Pick a query with representative data. Measure baseline and hinted plans via EXPLAIN ANALYZE. Record actual rows, loops, timing, and output results. Keep a hint only if the gain is reproducible.

## 16. Common Mistakes

| Misconception | Reality | How to handle |
|---|---|---|
| USE INDEX forces index usage | Table scan can still be selected | Use FORCE when there is a clear reason to penalize scan cost |
| FORCE INDEX always uses the index | If index is inapplicable, a scan can still happen | Check predicates and index definition |
| IGNORE INDEX selects a replacement index | It only excludes the named index | Let optimizer pick among remaining paths or hint another |
| FOR JOIN controls ORDER BY too | It affects row lookup and joins | Use FOR ORDER BY separately |
| Omitting FOR applies only to WHERE | Omitting FOR applies to all scopes | Specify the exact scope when needed |
| INDEX optimizer hint equals USE INDEX | INDEX equals FORCE INDEX | Use NO_* to mimic excluding unwanted indexes |
| Empty list is valid for all hint types | Only USE INDEX allows an empty list | FORCE and IGNORE require an index_list |
| Hints take column names | Hints take index names | Verify with SHOW INDEX |
| Aliases do not matter | Optimizer hints must match the active alias | Use the alias declared in the query block |
| New hints work on all MySQL 8.0 versions | Index-level optimizer hints began in 8.0.20 | Check minimum server version |
| A hint took effect because SQL ran cleanly | Hints can be ignored or inapplicable | Inspect EXPLAIN and SHOW WARNINGS |
| Forcing an index always makes queries faster | The index may be unselective or require many lookups | Measure with representative data and parameters |

## 17. Workflow for Introducing Hints Into Application Code

Before keeping a hint in code:

1. Record the original query, parameters, and MySQL version.
2. Run EXPLAIN and save the baseline plan.
3. Confirm the proposed index exists and matches column order.
4. Test USE INDEX, FORCE INDEX, or IGNORE INDEX with the narrowest required scope.
5. If running 8.0.20 or later, consider the corresponding new optimizer index hint.
6. Check aliases, query blocks, and precedence rules.
7. Re-run EXPLAIN to verify the plan changed as expected.
8. Run EXPLAIN ANALYZE or workload benchmarks to measure actual rows and timing.
9. Test across multiple parameter values, including both common and rare values.
10. Document the rationale, minimum version, and criteria for revisiting the hint.
11. Monitor whenever data distribution, indexes, or MySQL version changes.

Decision flowchart:

~~~mermaid
flowchart TD
    A[Query has a suboptimal plan] --> B[EXPLAIN baseline]
    B --> C{Suitable index exists?}
    C -->|No| D[Design or fix index first]
    C -->|Yes| E{Need to restrict index set?}
    E -->|Yes| F[USE INDEX]
    E -->|Need to penalize scan| G[FORCE INDEX]
    E -->|Need to exclude index| H[IGNORE INDEX]
    F --> I[EXPLAIN and measure]
    G --> I
    H --> I
    D --> I
    I --> J{MySQL 8.0.20 or later?}
    J -->|Yes| K[Consider JOIN_INDEX / ORDER_INDEX / GROUP_INDEX / INDEX]
    J -->|No| L[Keep compatible syntax]
    K --> M[SHOW WARNINGS and EXPLAIN ANALYZE]
    L --> M
    M --> N[Keep hint only if improvement is stable]
~~~

## Conclusion

USE INDEX restricts the set of candidate indexes while still allowing table scans. FORCE INDEX also restricts candidates while pricing table scans as very expensive. IGNORE INDEX excludes listed indexes from consideration. FOR JOIN, FOR ORDER BY, and FOR GROUP BY confine the effect to the intended query phase.

Starting in MySQL 8.0.20, optimizer index hints—JOIN_INDEX, ORDER_INDEX, GROUP_INDEX, INDEX, and their NO_* variants—provide a newer control mechanism. They match FORCE/IGNORE semantics per scope rather than directly matching USE INDEX. MySQL 8.4 and 9.7 continue supporting traditional syntax while steering users toward the newer hint family.

Use hints as deliberate verification and control tools. EXPLAIN confirms the plan, SHOW WARNINGS verifies recognized hints, and EXPLAIN ANALYZE plus benchmarks validate real-world impact. Retain a hint only with solid evidence that it consistently improves the workload across target data and versions.

## References

- MySQL 8.4 Reference Manual — Index Hints: https://dev.mysql.com/doc/refman/8.4/en/index-hints.html
- MySQL 8.4 Reference Manual — Optimizer Hints: https://dev.mysql.com/doc/refman/8.4/en/optimizer-hints.html
- MySQL 8.0 Reference Manual — Index Hints: https://dev.mysql.com/doc/refman/8.0/en/index-hints.html
- MySQL 8.0 Reference Manual — Optimizer Hints: https://dev.mysql.com/doc/refman/8.0/en/optimizer-hints.html
- MySQL 8.0.20 Release Notes: https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-20.html
- MySQL 9.7 Reference Manual — Index Hints: https://dev.mysql.com/doc/refman/9.7/en/index-hints.html
- MySQL 9.7 Reference Manual — Optimizer Hints: https://dev.mysql.com/doc/refman/9.7/en/optimizer-hints.html
- MySQL 8.4 Reference Manual — Invisible Indexes: https://dev.mysql.com/doc/refman/8.4/en/invisible-indexes.html
