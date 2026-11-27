# Invisible Indexes and Testing Index Removal from the Optimizer

When an index appears no longer necessary, dropping it immediately carries risk: an overlooked query might still depend on that index and suddenly slow down after removal. MySQL 8.0 provides **invisible indexes** to test excluding an index from optimizer selection while keeping the index in the table.

When an index is set to `INVISIBLE`, the optimizer does not use it in standard query plans. However, InnoDB continues maintaining the index as data is inserted, updated, or deleted. This lets operations teams observe impacts on read plans before deciding whether to restore `VISIBLE` or permanently drop the index.

## 1. What is an invisible index?

An invisible index is an index that still exists in the storage structure but is marked hidden from the optimizer. This feature has been available since MySQL 8.0.

Key distinctions:

- A `VISIBLE` index can be considered normally by the optimizer.
- An `INVISIBLE` index is ignored by the optimizer during normal queries.
- InnoDB still updates invisible indexes when `INSERT`, `UPDATE`, or `DELETE` modifies relevant columns.
- Invisible indexes still consume disk storage and still incur write maintenance costs.
- If it is a unique index, the uniqueness constraint is still enforced even while the index is invisible.
- A primary key cannot be made invisible.

Because the index remains present, invisible indexes are useful for testing query plan selection impact. They do not fully simulate the storage savings and write-cost reductions of dropping the index.

## 2. Creating and toggling index visibility

Example `products` table with an index on category and creation time:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    category_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    created_at DATETIME NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (product_id),
    KEY idx_products_category_created (category_id, created_at)
) ENGINE = InnoDB;
```

Switch the index to invisible:

```sql
ALTER TABLE products
ALTER INDEX idx_products_category_created INVISIBLE;
```

Restore visibility so the optimizer uses the index again:

```sql
ALTER TABLE products
ALTER INDEX idx_products_category_created VISIBLE;
```

You can check visibility via `SHOW INDEX`:

```sql
SHOW INDEX FROM products;
```

In MySQL 8.0, the output includes a `Visible` column showing `YES` or `NO`. You can inspect detailed metadata via `INFORMATION_SCHEMA.STATISTICS`:

```sql
SELECT INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX, IS_VISIBLE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'products'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

`IS_VISIBLE` shows the visibility status of each index component. For composite indexes, multiple rows share the same `INDEX_NAME`, one per column in the index.

## 3. Checking plans before hiding an index

Before testing, identify which queries might be using the index. Example:

```sql
EXPLAIN
SELECT product_id, product_name, created_at
FROM products
WHERE category_id = 20
ORDER BY created_at DESC
LIMIT 30;
```

Record these details:

- `key`: the index the optimizer currently chooses.
- `type`: access type, such as `ref`, `range`, or `ALL`.
- `rows`: estimated rows to read.
- `Extra`: may show whether the query needs `Using filesort` or can use the index.

If `key` is `idx_products_category_created`, the index contributes to executing this query. This is a candidate to check carefully before testing invisibility.

Do not inspect only one sample query. Gather important queries across the workload, including key lookups, filters, joins, sorts, aggregations, and infrequent periodic statements. An index might not appear in daily queries yet remain critical for month-end reports or maintenance jobs.

## 4. Testing index exclusion from the optimizer

After recording the baseline plan, switch the index to invisible:

```sql
ALTER TABLE products
ALTER INDEX idx_products_category_created INVISIBLE;
```

Re-run `EXPLAIN` for the same query:

```sql
EXPLAIN
SELECT product_id, product_name, created_at
FROM products
WHERE category_id = 20
ORDER BY created_at DESC
LIMIT 30;
```

The optimizer no longer selects `idx_products_category_created`. It may select another index, perform a table scan, or adopt a different plan. Compare `key`, `type`, `rows`, `Extra`, and execution time to evaluate the impact.

If you need to inspect what plan an invisible index would produce, enable the `use_invisible_indexes` option in a test session:

```sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;

SET SESSION optimizer_switch = 'use_invisible_indexes=on';

EXPLAIN
SELECT product_id, product_name, created_at
FROM products
WHERE category_id = 20
ORDER BY created_at DESC
LIMIT 30;

SET SESSION optimizer_switch = @saved_optimizer_switch;
```

When `use_invisible_indexes=on`, the optimizer is allowed to consider invisible indexes within that session. This option helps compare plans while the index is hidden versus restored to the candidate pool. The example saves the entire initial `optimizer_switch` value in a session variable and restores it after testing, which is especially important when using connections from a connection pool.

`EXPLAIN ANALYZE` can provide actual timings and row counts for `SELECT` queries in MySQL 8.0.18 and later:

```sql
EXPLAIN ANALYZE
SELECT product_id, product_name, created_at
FROM products
WHERE category_id = 20
ORDER BY created_at DESC
LIMIT 30;
```

This command actually executes the query. Use it only with safely executable read queries and account for extra load when running in production.

## 5. Process for evaluating whether an index can be removed

A testing workflow should follow clear steps:

1. **Record current state:** index name, columns, column order, uniqueness, size, and queries currently using it.
2. **Measure baseline:** save `EXPLAIN` plans, timings, rows read, and workload metrics under representative load.
3. **Set invisible:** switch exactly one index to `INVISIBLE` to isolate the impact of that single index.
4. **Observe the workload:** run critical queries, reports, scheduled jobs, and real business flows; monitor latency and resources.
5. **Decide:** if any query regresses, restore `VISIBLE`; if no impact appears over a representative observation period, consider a controlled drop step.
6. **Verify post-change:** continue monitoring plans and latency after restoring or dropping the index.

Avoid hiding multiple indexes simultaneously on the first test. If metrics degrade, pinpointing which index caused the change becomes much harder.

## 6. Restoring and permanently dropping an index

If an important query slows down, restore visibility immediately:

```sql
ALTER TABLE products
ALTER INDEX idx_products_category_created VISIBLE;
```

Then re-verify plans and performance of affected queries.

If you have tested long enough and confirmed the index is no longer needed, you can drop it:

```sql
DROP INDEX idx_products_category_created ON products;
```

Dropping an index reclaims storage and eliminates index maintenance cost during writes. This is a crucial difference from invisible indexes: invisibility only excludes the index from optimizer selection, whereas `DROP INDEX` removes the index structure.

Before dropping, verify whether the index supports a unique constraint, foreign key, or infrequent query. In particular, an invisible unique index still enforces uniqueness; dropping it removes that uniqueness constraint. Indexes required for relational constraints must be handled strictly according to InnoDB and schema requirements.

## 7. Limitations and impacts to understand

### Invisible does not mean disabled

InnoDB still has to maintain invisible indexes. For instance, inserting a new product or updating `category_id` or `created_at` still inserts or updates corresponding entries in the invisible index. Consequently, an invisibility test does not directly measure the write-time and storage savings gained after dropping the index.

### Unique indexes still enforce uniqueness

If `email` is protected by an invisible unique index, two rows still cannot share the same email. The optimizer skips the index for queries, yet uniqueness checks remain active on writes.

### Primary keys cannot be invisible

In InnoDB, the primary key is the clustered index and organizes the table's data. You cannot use invisible indexes to test excluding the primary key from the optimizer. Distinguish the primary key from secondary indexes whose visibility can be toggled.

### Constraints and schema dependencies

Before changing an index's visibility, check whether the index satisfies constraints or schema dependencies. Do not assume every index can be hidden or dropped arbitrarily. Test the operation in a staging environment with an equivalent schema to confirm MySQL accepts the change.

### DDL changes still require a rollout plan

`ALTER TABLE` may require a metadata lock and can affect sessions accessing the table. Check MySQL version, table size, long-running transactions, and your system's DDL deployment process. Execute during an appropriate window and monitor afterward.

## 8. When should you use invisible indexes?

| Scenario | How to handle |
|---|---|
| Suspecting a secondary index is no longer used by queries | Set it invisible during an observation window before dropping |
| Wanting to measure plans without a specific index available to the optimizer | Set invisible, then compare `EXPLAIN` and timings |
| Wanting to inspect what plan would use an invisible index | Enable `use_invisible_indexes` in a test session |
| Important query degrades after hiding an index | Restore `VISIBLE` and investigate the affected query |
| Wanting to actually reduce disk usage and write cost | Drop only after thorough evaluation and constraint checks |

Invisible indexes are a risk-reduction tool when evaluating redundant indexes. They do not replace workload collection, constraint verification, and benchmarking on representative data.

## 9. Self-check

1. How does an invisible index differ from `DROP INDEX`?
2. Why does an invisible index still incur overhead during `INSERT`, `UPDATE`, and `DELETE`?
3. Does an invisible unique index still prevent duplicate data?
4. What does the `use_invisible_indexes` option do, and at what scope should it be enabled?
5. Why must you observe infrequent queries as well before dropping an index?
6. Can a primary key be made invisible? Why or why not?
7. Why does an invisibility test not fully measure the write-cost savings achieved after dropping an index?
