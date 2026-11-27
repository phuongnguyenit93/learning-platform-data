# Index Condition Pushdown and Predicates Pushed to the Storage Engine

A customer table has several million rows. The application needs to find active users in a specific region whose last name contains a certain substring and whose profile description also contains a keyword. A composite index can help MySQL quickly locate the region/status range, yet if every row in that range must be read in full before checking the last name, MySQL may still have to access a huge number of records.

Index Condition Pushdown (ICP) is an optimization that lets MySQL push down part of the filter conditions—those evaluable using only columns present in the index—to the storage engine. The engine evaluates those conditions while reading index entries and fetches full rows only for entries that pass. Thus, ICP can reduce full record reads, especially when the index does not cover all columns the query needs.

ICP does not automatically run every `WHERE` condition inside the index, does not replace index design, and is not synonymous with a covering index. Understanding which predicates locate the index range, which can be pushed down to the engine, and which must still be filtered after reading rows is the key to evaluating its real benefit.

## 1. What is Index Condition Pushdown?

In a query using a secondary index, MySQL normally performs two steps:

1. Traverse the index to find entries matching the access conditions.
2. For each required entry, read the full record from the clustered index (InnoDB) or row location (MyISAM), then check remaining predicates.

If a predicate only needs columns already present in the index, reading the full row before checking that predicate is wasteful. ICP lets the storage engine evaluate that predicate directly on the index entry.

High-level flow:

1. The optimizer selects an index and determines access conditions.
2. The server builds an index condition from predicates evaluable using indexed columns.
3. The storage engine traverses index entries and checks the index condition.
4. Entries that fail are discarded inside the engine without reading the full row.
5. Entries that pass are used to read the full row if the query still needs columns absent from the index.
6. The server continues checking remaining predicates and produces the result.

ICP is most helpful when a query uses an index to find a relatively wide set of entries, has additional filter predicates on indexed columns, yet still needs to read non-indexed columns to return results or evaluate other conditions.

## 2. Example: filtering index entries before reading full rows

Create a customer profiles table:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    region_code CHAR(2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    profile_text TEXT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_customer_region_status_lastname
        (region_code, status, last_name)
) ENGINE=InnoDB;
```

Query:

```sql
SELECT
    id,
    first_name,
    profile_text
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE'
  AND last_name LIKE '%nguyen%'
  AND profile_text LIKE '%architect%';
```

Index `idx_customer_region_status_lastname` contains three columns: `region_code`, `status`, and `last_name`. Conditions `region_code = 'VN'` and `status = 'ACTIVE'` locate the index range. Condition `last_name LIKE '%nguyen%'` cannot form a useful range prefix due to the leading wildcard, yet the `last_name` value is still available in the index entry, so the storage engine can check it via ICP.

Conversely, `profile_text` is not in the index. The engine cannot evaluate this predicate solely from the index entry. Entries passing the index condition still require reading the full row so the server can check `profile_text LIKE '%architect%'` and retrieve `first_name` and `profile_text` to return.

If many customers in VN are `ACTIVE` yet only a small fraction have a matching last name, ICP can avoid many full row reads.

## 3. ICP vs. predicates used for index range lookup

Not every predicate on an indexed column plays the same role.

With a composite index:

```sql
KEY idx_orders_customer_status_created
    (customer_id, status, created_at)
```

Query:

```sql
SELECT id, total_amount
FROM orders
WHERE customer_id = 120
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
```

All three predicates can participate in locating the index range in key-part order. If the index already narrows the range tightly, ICP may bring little additional benefit.

Another example:

```sql
KEY idx_people_zip_last_first
    (postal_code, last_name, first_name)
```

```sql
SELECT *
FROM people
WHERE postal_code = '700000'
  AND last_name LIKE '%tran%'
  AND address LIKE '%District 1%';
```

`postal_code` locates the index region. The `last_name` predicate can be evaluated on the index entry via ICP even though it cannot narrow a prefix range due to the leading wildcard. `address` is not in the index, so full rows are needed to evaluate it.

Distinguish between:

| Predicate type | Role |
|---|---|
| Access condition / range condition | Locates the starting point and span to scan in the index |
| Index condition | Checked directly on index entries by the engine via ICP |
| Residual `WHERE` condition | Must still be checked after reading the row or at the server layer |

A predicate may be used for index positioning, used as ICP, or retained as a residual condition. Classification depends on the index, expression, access method, and storage engine evaluation capability.

## 4. Where does ICP operate in MySQL's architecture?

The optimizer at the server layer decides whether ICP can be used. The server passes the index condition down to the storage engine through the handler interface. The storage engine reads index entries and evaluates predicates against fields available inside each entry.

For InnoDB:

- Secondary index leaf entries contain the indexed column values plus the row's primary key.
- Without ICP, the engine may have to use the primary key to access the clustered index and fetch the full row for every entry that needs server-layer evaluation.
- With ICP, the engine first checks eligible predicates on the secondary index entry.
- Only entries passing the index condition need to access the clustered index if the query still requires the full row.

With MyISAM, the engine can also use ICP to avoid reading rows from the data file when the index condition fails.

ICP is an optimization between the server and the storage engine. It does not alter the logical result of SQL; it changes when and where part of the filtering occurs to reduce I/O.

## 5. Conditions for MySQL to use ICP

ICP applies only when the following factors align:

1. The query uses an index access path that MySQL supports for ICP.
2. Part of the predicates can be evaluated solely from columns present in the chosen index.
3. The query still needs to read full rows or benefits from filtering index entries prior to row reads.
4. The predicate is in a form the storage engine can evaluate.
5. Depending on table and index type, no engine or expression restrictions apply.

Access methods that commonly support ICP include `range`, `ref`, `eq_ref`, and `ref_or_null`. ICP is not a mechanism applied to full table scans.

### 5.1. InnoDB only uses ICP on secondary indexes

In InnoDB, clustered index leaf pages already contain full row data. When accessing via the clustered index, reading the index entry already brings in the full row; there is no separate row lookup step for ICP to avoid.

Therefore, ICP is meaningful for InnoDB secondary indexes. When a query uses the primary key/clustered index, the optimizer typically gains no ICP benefit in avoiding full-row lookups.

### 5.2. Queries served by a covering index may not need ICP

If all columns needed for conditions and output reside in the index, the storage engine can return results purely from the index. Since no full-row read is needed, ICP generally adds no extra benefit.

Example:

```sql
SELECT region_code, status, last_name
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE'
  AND last_name LIKE '%nguyen%';
```

With index `(region_code, status, last_name)`, this query can be fully covered by the index. `Using index` typically indicates the query uses a covering index. This differs from `Using index condition`.

### 5.3. Expressions that cannot be pushed down to the engine

A predicate cannot be pushed down if the storage engine cannot evaluate it from index entries or the expression is unsupported for ICP. Common cases:

- Predicates referencing columns not in the index.
- Predicates requiring results of a subquery.
- Predicates depending on stored functions or expressions requiring server-layer evaluation.
- The query does not use a suitable access method/index.
- The query is already fully served by a covering index, leaving no full-row lookup to save.
- InnoDB does not support ICP for secondary indexes on virtual generated columns.

Do not try to rewrite every predicate just to force ICP. Prioritize correct semantics, appropriate indexes, and execution plan checks.

## 6. Recognizing ICP with EXPLAIN

Basic usage:

```sql
EXPLAIN
SELECT
    id,
    first_name,
    profile_text
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE'
  AND last_name LIKE '%nguyen%'
  AND profile_text LIKE '%architect%';
```

In tabular output, the `Extra` column may contain:

```text
Using index condition
```

This indicates MySQL is using Index Condition Pushdown for the query.

The output may also show `Using where` at the same time. This is not contradictory:

- `Using index condition` means predicates are evaluated at the storage engine on index entries.
- `Using where` means additional filtering occurs at the server layer after fetching rows or after access steps.

Not seeing `Using index condition` means the current query is not using ICP. Causes may include the optimizer not picking a suitable index, no eligible pushdown predicates, an unsupported access method, or the query already being served by a covering index.

### 6.1. EXPLAIN FORMAT=JSON

You can view the plan in JSON format:

```sql
EXPLAIN FORMAT=JSON
SELECT
    id,
    first_name,
    profile_text
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE'
  AND last_name LIKE '%nguyen%'
  AND profile_text LIKE '%architect%';
```

Depending on version and plan structure, JSON may represent the index condition under a property such as `index_condition`, alongside `attached_condition` or related filter details. Inspect `access_type`, `key`, `used_key_parts`, and conditions attached to the table access to understand each predicate's role.

Do not rely on a single JSON field to conclude the entire query was pushed down. Cross-check against the selected index and tabular output.

### 6.2. EXPLAIN FORMAT=TREE and EXPLAIN ANALYZE

MySQL 8.0 supports:

```sql
EXPLAIN FORMAT=TREE
SELECT
    id,
    first_name,
    profile_text
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE'
  AND last_name LIKE '%nguyen%'
  AND profile_text LIKE '%architect%';
```

Starting in MySQL 8.0.18, `EXPLAIN ANALYZE` executes the `SELECT` statement and provides actual row counts and timings per iterator:

```sql
EXPLAIN ANALYZE
SELECT
    id,
    first_name,
    profile_text
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE'
  AND last_name LIKE '%nguyen%'
  AND profile_text LIKE '%architect%';
```

`EXPLAIN ANALYZE` actually runs the query. Only use it with safely executable `SELECT` statements and appropriate data. Actual row counts help compare estimates with reality, though not every plan displays an explicit counter of full-row lookups avoided by ICP. Combine plans, runtimes, and benchmarks on representative data.

## 7. Distinguishing Using index condition, Using index, and Using where

These three indicators are frequently confused:

| Extra | Meaning | Still needs full-row reads? |
|---|---|---|
| `Using index condition` | ICP evaluates predicates on index entries before row lookups | Possibly yes, if `SELECT` or residual conditions need non-indexed columns |
| `Using index` | Covering index: the query can obtain needed columns from the index | Usually no full-row lookup needed |
| `Using where` | Additional filtering is still performed at the server layer | Depends on index and accessed columns |

These values can appear together. For example, `Using index condition; Using where` means part of the predicates is pushed to the engine while the remainder is still filtered at the server layer.

### 7.1. Illustrating three cases

**Case A — No ICP, not covering**

The index locates a range of entries. The server must read the row before evaluating predicates on remaining indexed columns or non-indexed columns. Many full-row lookups may occur.

**Case B — With ICP**

The engine evaluates predicates that can be checked from the index entry. Only entries that pass require full-row reads to retrieve `SELECT` columns or check residual conditions.

**Case C — Covering index**

All needed columns reside in the index. The engine can return data directly from the index without full-row lookups. Here, the gain comes from covering index access rather than ICP reducing row lookups.

## 8. ICP does not reduce all kinds of work

ICP reduces full-row accesses for index entries rejected by the index condition. It does not necessarily reduce:

- The number of index entries scanned within the access range.
- The cost of reading index leaf pages.
- The cost of checking remaining predicates on full rows.
- Sorting, grouping, or joining costs after table access.
- The final number of rows returned.

For instance, `LIKE '%nguyen%'` lacks a fixed prefix for a range lookup by last name. MySQL may still have to scan every entry in the `region_code/status` region, after which ICP discards non-matching last names. Thus, ICP cuts down full-row lookups but does not turn a substring search into a narrow index range scan.

If most index entries pass ICP, the gain may be small. If very few entries pass, the avoided full-row lookups can be substantial.

## 9. Designing composite indexes so ICP can shine

Composite indexes should be designed around actual query patterns:

1. Put selective equality columns at the start of the index.
2. Consider range or sorting columns next.
3. Include columns usable by ICP in the index if pre-lookup filtering yields sufficient savings.
4. Consider `SELECT` columns if aiming for a covering index, while avoiding overly wide indexes.

Example:

```sql
KEY idx_orders_customer_status_created
    (customer_id, status, created_at)
```

Query:

```sql
SELECT id, total_amount
FROM orders
WHERE customer_id = 120
  AND status = 'PAID'
  AND created_at >= '2026-01-01';
```

The index can seek by `customer_id`, `status`, and the `created_at` range. If `total_amount` is not in the index, InnoDB may need clustered row lookups for matching entries.

If there is an extra condition on another indexed column that cannot narrow the range, ICP can filter it before row lookup. Still, adding columns to an index increases storage size, `INSERT`/`UPDATE`/`DELETE` costs, and buffer pool footprint. Create indexes based on workload, selectivity, and benchmarks.

### 9.1. Column order and leftmost prefix

With index:

```sql
KEY idx_a_b_c (a, b, c)
```

MySQL organizes the index in `(a, b, c)` order. A predicate on `a` can locate a prefix; a predicate on `b` helps when `a`'s scope fits; a predicate on `c` may serve range or ICP depending on prefix and access method.

ICP does not abolish the leftmost prefix rule. If a query lacks suitable predicates on leading columns, the optimizer may not use the index as expected. ICP only optimizes filtering entries after an index access path has been chosen.

### 9.2. Wide indexes are not always better

Adding many columns to an index can:

- Enlarge the index and consume buffer pool memory.
- Increase write and index maintenance overhead.
- Reduce page fan-out, increasing the number of pages read.
- Increase index build time and DDL impact.
- Create indexes nearly redundant with existing ones.

Sometimes a narrower index that locates the range well plus ICP filtering the rest is sufficient. In other cases, a covering index offers greater benefit. Measure on data with near-production distribution.

## 10. Toggling ICP for verification

ICP is controlled by the `index_condition_pushdown` optimizer switch. You can inspect its status:

```sql
SELECT @@SESSION.optimizer_switch;
```

Test disabling it in the current session:

```sql
SET SESSION optimizer_switch = 'index_condition_pushdown=off';
```

Then re-run `EXPLAIN` for the same query. Re-enable it:

```sql
SET SESSION optimizer_switch = 'index_condition_pushdown=on';
```

Modify only the session for testing; avoid changing `GLOBAL` in production merely to test a single query. When comparing, keep data, parameters, isolation level, and cache state as consistent as possible; run multiple iterations to avoid drawing conclusions from one noisy measurement.

If disabling ICP leaves the plan or runtime virtually unchanged, the query may not benefit significantly, the index condition may not be selective, or the bottleneck lies elsewhere.

## 11. Predicates that typically cannot be pushed down

A predicate can be pushed down only if the engine has the data and evaluation capability. Examples like the following usually remain at the server layer:

```sql
-- profile_text is not in the index.
WHERE profile_text LIKE '%architect%'
```

```sql
-- Condition contains a subquery.
WHERE last_name = (
    SELECT preferred_last_name
    FROM user_preferences
    WHERE user_id = 10
)
```

```sql
-- Condition calls a stored function.
WHERE normalize_name(last_name) = 'nguyen'
```

Even when `last_name` is in the index, an expression calling a function may not be evaluable by the storage engine via ICP. Moreover, wrapping an indexed column in a function can also prevent using the index for range positioning.

Do not assume that "because a column is in the index, any expression on it can be pushed down." The predicate must belong to the set of expressions supported by the optimizer and storage engine.

## 12. ICP and other optimization techniques

| Technique | Primary effect | Difference from ICP |
|---|---|---|
| Composite index | Creates multi-column access paths | It is an index structure; ICP filters entries once an index is used |
| Covering index | Returns results solely from the index | Avoids full-row lookups entirely when all needed columns are in the index |
| Index range scan | Scans only an index interval | Narrows the entries that must be scanned |
| Index Condition Pushdown | Filters entries using predicates on indexed columns before row lookup | Reduces full-row lookups within the scanned span |
| Multi-Range Read (MRR) | Organizes row lookups in order/batches to improve I/O | Optimizes how rows are fetched, not the predicate filtering mechanism |
| Partition pruning | Skips partitions that need not be accessed | Reduces data scope at the partition level |

Techniques can work together in the same plan. For instance, partition pruning cuts down partitions, a range scan locates the index span, ICP filters entries, and MRR optimizes fetching the remaining rows.

## 13. ICP in JOINs

ICP can also help when a table is accessed via an index inside a `JOIN` plan. For example, joining `orders` with `customers`:

```sql
SELECT
    o.id,
    o.customer_id,
    o.created_at,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.note LIKE '%priority%';
```

If `orders` has index `(customer_id, status, note)` and `note` matches pushdown rules, the engine can filter index entries before reading full rows. Actual applicability depends on join order, access method, index type, and predicates.

It is not true that conditions in `ON` are always pushed or conditions in `WHERE` are never pushed. The optimizer analyzes expressions after applying rewrite transformations and selects a plan. Inspect `EXPLAIN` on the complete query.

## 14. Evaluating ICP benefit with real data

A verification workflow:

1. Pick a slow query using a secondary index that requires full rows.
2. Read `EXPLAIN`, identifying the index, access type, and `Using index condition`.
3. Identify which predicates are pushed down and which remain residual.
4. Check data distribution: how many entries pass the index condition?
5. Run `EXPLAIN ANALYZE` to observe actual rows and timing.
6. Compare with ICP enabled vs. disabled in a test session.
7. Measure multiple times with the same parameters and a representative workload.
8. Check the impact of any additional index on writes and disk usage.

Do not compare single-run timings alone. Warm/cold cache, concurrency, buffer pool, I/O, and parameter skew can alter outcomes. A query optimal for one parameter value may not be optimal for another.

### 14.1. Quantitative thinking example

Suppose an index scan must traverse 100,000 entries in the active-customers region:

| Stage | Without ICP | With ICP |
|---|---:|---:|
| Index entries scanned | 100,000 | 100,000 |
| Entries passing last-name predicate | 100,000 need lookup before filtering | 2,000 |
| Estimated full-row lookups | 100,000 | 2,000 |
| `profile_text` checks | 100,000 rows | 2,000 rows |

Numbers are illustrative only. Reality depends on predicates, indexes, engine, optimizer, and data. The core point is that ICP may scan the same number of index entries while drastically reducing full-row fetches.

## 15. Common misconceptions

| Misconception | Reality |
|---|---|
| ICP lets MySQL skip all unrelated index entries | ICP checks conditions on entries already scanned; it does not necessarily narrow the range scan |
| If a column is in the index, any predicate on it can be pushed | The predicate must also be supported by the optimizer and storage engine |
| `Using index condition` means covering index | It indicates ICP; the query may still need to read full rows |
| `Using index` and `Using index condition` are the same | `Using index` usually indicates a covering index; ICP filters entries before row lookup |
| ICP eliminates all residual `WHERE` filters | Conditions on non-indexed columns still need server-layer evaluation |
| ICP always makes queries faster | If the condition is not selective or other costs dominate, gains may be minor |
| ICP replaces composite indexes | ICP complements an index access path; it does not replace proper index structure |
| InnoDB uses ICP identically on every index | ICP helps on secondary indexes; the clustered index already holds full rows |
| Disabling ICP server-wide is a query fix | Test at the session level and tune based on the specific plan |

## 16. Checklist when analyzing Index Condition Pushdown

- Which access method is the query using: `range`, `ref`, `eq_ref`, or `ref_or_null`?
- Is the chosen index an InnoDB secondary index?
- Which columns are in the index, and what is the key-part order?
- Which predicates locate the range?
- Which predicates can be checked solely from index entries?
- Which predicates require full rows or server-layer evaluation?
- Does `EXPLAIN` show `Using index condition`?
- Does `Using where` appear alongside it, and which filtering does it represent?
- Does the query truly need full rows, or could it become a covering index?
- Is the ICP condition selective enough to cut row lookups?
- Does `EXPLAIN ANALYZE` show row counts and timings matching expectations?
- Were ICP on/off benchmarks executed under identical conditions?
- Does any additional index significantly increase write cost and storage?

## Conclusion

Index Condition Pushdown allows the storage engine to evaluate predicates derivable from index entries before reading full rows. With InnoDB, the main benefit arises when accessing secondary indexes while the query still requires non-indexed columns. `Using index condition` signals ICP; `Using index` typically signals a covering index; `Using where` indicates remaining server-layer filtering. ICP can reduce full-row lookups without necessarily reducing scanned index entries or replacing residual filters. Design composite indexes around query patterns, distinguish access conditions from index conditions, inspect `EXPLAIN`, and measure on representative data before drawing performance conclusions.
