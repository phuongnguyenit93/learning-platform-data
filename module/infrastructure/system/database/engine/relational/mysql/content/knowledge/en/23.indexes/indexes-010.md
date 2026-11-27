# Indexes

## Descending Indexes and Multi-Directional Sorting Queries

When a query must sort by multiple columns in different directions—such as descending score with ascending creation time—a standard ascending B-tree index may not provide the exact order required by `ORDER BY`. MySQL 8.0 supports descending indexes, allowing you to declare `ASC` or `DESC` individually for each key part. As a result, InnoDB can read the index in the matching order and reduce or eliminate an extra sorting step.

Descending indexes are particularly useful for leaderboards, transaction lists, event histories, and top-N screens with multi-criteria sorting. However, an index helps only when column order, sort direction, filter predicates, and query expressions align with the index structure. Adding `DESC` to an index does not automatically make every `ORDER BY` query faster.

### 1. Why is multi-directional sorting needed?

A query may sort by multiple criteria. For example, a leaderboard page needs the highest score first; if two players tie on score, the one who achieved it earlier comes first; if still tied, `id` breaks the tie for deterministic ordering:

```sql
SELECT id, player_name, score, achieved_at
FROM leaderboard
WHERE season_id = 2026
ORDER BY score DESC, achieved_at ASC, id ASC
LIMIT 20;
```

The required order is:

1. `score DESC`: higher scores come first.
2. `achieved_at ASC`: among equal scores, earlier timestamps come first.
3. `id ASC`: uses a unique key to break remaining ties.

If only index `(season_id, score)` exists, the index can help filter by season and sort by score, yet does not necessarily satisfy the next two sort directions. On large datasets, MySQL may have to perform an extra sort step. An index with matching directions for all three sort columns allows InnoDB to read rows directly in the desired order.

### 2. ASC, DESC, and backward B-tree scans

A B-tree index has a key order. An index declaring all key parts in ascending order can be scanned forward or backward. For instance, index `(a ASC, b ASC)` can serve:

```sql
-- Forward index scan.
ORDER BY a ASC, b ASC

-- Backward scan over the entire index order.
ORDER BY a DESC, b DESC
```

When scanning backward, the direction of every key part flips simultaneously. Consequently, index `(a ASC, b ASC)` cannot directly supply a mixed order like `a ASC, b DESC` via a backward scan: a backward scan produces `a DESC, b DESC`.

Descending indexes solve this by storing an individual direction for each key part. Example:

```sql
CREATE INDEX idx_a_asc_b_desc
    ON sample_table (a ASC, b DESC);
```

This index can be scanned forward for `ORDER BY a ASC, b DESC`, or scanned backward for the fully inverted order `ORDER BY a DESC, b ASC`.

| Index definition | Order satisfied by forward scan | Order satisfied by backward scan |
| --- | --- | --- |
| `(a ASC, b ASC)` | `a ASC, b ASC` | `a DESC, b DESC` |
| `(a ASC, b DESC)` | `a ASC, b DESC` | `a DESC, b ASC` |
| `(a DESC, b ASC)` | `a DESC, b ASC` | `a ASC, b DESC` |

The core rule is that the directions of the entire key-part chain must match along one consistent traversal direction: forward or fully reversed. If only a subset of columns flips direction, an index with matching directions is needed.

### 3. Descending index syntax in MySQL 8.0

Directions can be declared directly in the column list of `CREATE INDEX`:

```sql
CREATE INDEX index_name
ON table_name (
    col_1 ASC,
    col_2 DESC,
    col_3 ASC
);
```

Or declared inside `CREATE TABLE` / `ALTER TABLE`:

```sql
ALTER TABLE leaderboard
ADD INDEX idx_season_score_time (
    season_id ASC,
    score DESC,
    achieved_at ASC,
    id ASC
);
```

MySQL 8.0 supports true descending indexes in InnoDB. In older versions, the `DESC` keyword in an index definition was parsed and ignored; the index was created in ascending order. Therefore, confirm the server version before relying on mixed-direction indexes to optimize queries.

### 4. Example: multi-directional top-N

Suppose you have a seasonal leaderboard table:

```sql
CREATE TABLE leaderboard (
    id BIGINT NOT NULL,
    season_id INT NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    score INT NOT NULL,
    achieved_at DATETIME NOT NULL,
    PRIMARY KEY (id)
) ENGINE = InnoDB;
```

Query retrieving the top 20 players in a season:

```sql
SELECT id, player_name, score, achieved_at
FROM leaderboard
WHERE season_id = 2026
ORDER BY score DESC, achieved_at ASC, id ASC
LIMIT 20;
```

An index matching the filter predicate and sort order:

```sql
CREATE INDEX idx_leaderboard_season_score_time
ON leaderboard (
    season_id ASC,
    score DESC,
    achieved_at ASC,
    id ASC
);
```

`season_id` comes first because the query filters on a single season value. Once the leading key part is fixed, InnoDB can read entries ordered by `score DESC`, `achieved_at ASC`, `id ASC`. If the index provides the full order, MySQL can avoid an extra sort and stop after fetching 20 matching rows.

If the query returns only columns contained in the index, you can design a covering index by appending columns to read. However, adding `player_name` to the index enlarges it and raises write cost; measure real benefits before widening:

```sql
CREATE INDEX idx_leaderboard_top_cover
ON leaderboard (
    season_id ASC,
    score DESC,
    achieved_at ASC,
    id ASC,
    player_name ASC
);
```

In InnoDB, secondary indexes already contain the primary key as a row locator. You do not need to mechanically repeat the primary key column if it is already implicitly appended; nevertheless, explicit key-part ordering still needs to be designed and verified around query requirements. An overly wide covering index can do more harm than good.

### 5. Leftmost prefix rule and filter predicates

Multi-column indexes follow the leftmost prefix principle: key-part order starts at the first column. Columns preceding the `ORDER BY` portion typically need to be fixed by equality conditions so the index can supply ordering for subsequent columns.

Example index:

```sql
CREATE INDEX idx_order_status_date
ON orders (status ASC, created_at DESC, id ASC);
```

The following query fits:

```sql
SELECT id, created_at
FROM orders
WHERE status = 'paid'
ORDER BY created_at DESC, id ASC
LIMIT 50;
```

`status` is fixed to a single value, so the rest of the index can provide `created_at DESC, id ASC` ordering.

If the `status` predicate is omitted:

```sql
SELECT id, status, created_at
FROM orders
ORDER BY created_at DESC, id ASC;
```

The index above sorts first by `status`; rows across multiple statuses are not globally sorted by `created_at` alone. The optimizer may pick another index or perform a sort.

Range conditions on a key part also require attention. For example, `status = 'paid' AND created_at < ... ORDER BY created_at DESC, id ASC` can still leverage the time-ordered index slice. Yet if a column preceding the sort columns is unfixed, or the query needs discontinuous ordering across multiple value groups, the index may not provide the desired global order. `IN` with multiple values on a leading key part can also produce multiple ranges; inspect the actual plan rather than assuming it behaves like a single equality value.

### 6. Mixed sorting and backward scans of the entire index

Consider the query:

```sql
SELECT id, priority, created_at
FROM support_ticket
WHERE tenant_id = 42
ORDER BY priority DESC, created_at ASC, id ASC
LIMIT 30;
```

Index with matching directions:

```sql
CREATE INDEX idx_ticket_tenant_priority_time
ON support_ticket (
    tenant_id ASC,
    priority DESC,
    created_at ASC,
    id ASC
);
```

This index is read forward for the requested order. If a query requests reversing every direction:

```sql
ORDER BY priority ASC, created_at DESC, id DESC
```

MySQL can scan the index backward after fixing `tenant_id`. However, reversing only part of the order—such as `priority ASC, created_at ASC, id ASC`—is not the complete reverse of the index above; another index or a sort step may be needed.

When designing, explicitly write out the desired direction for every column before creating the index. Never look solely at the first column being `DESC` and conclude the index supports arbitrary `ASC`/`DESC` combinations.

### 7. LIMIT, top-N, and pagination

Descending indexes often yield clear benefits when queries need only a small number of leading rows:

```sql
SELECT id, score, achieved_at
FROM leaderboard
WHERE season_id = 2026
ORDER BY score DESC, achieved_at ASC, id ASC
LIMIT 20;
```

With a matching index, InnoDB can seek to the `season_id` key region, read in exact order, and stop once enough rows are gathered. Without a matching index, MySQL may have to collect candidate rows and sort them; `LIMIT` can reduce memory/cost of the top-N sort algorithm without eliminating scanning of matching rows.

For deep pagination, `LIMIT offset, count` may have to skip many entries before returning the requested page. You can use keyset pagination based on the entire sort key to resume from the previous page's last row. For order `score DESC, achieved_at ASC, id ASC`, the continuation predicate takes the form:

```sql
SELECT id, score, achieved_at
FROM leaderboard
WHERE season_id = 2026
  AND (
      score < :last_score
      OR (score = :last_score AND achieved_at > :last_achieved_at)
      OR (
          score = :last_score
          AND achieved_at = :last_achieved_at
          AND id > :last_id
      )
  )
ORDER BY score DESC, achieved_at ASC, id ASC
LIMIT 20;
```

Placeholders `:last_score`, `:last_achieved_at`, and `:last_id` are values bound by the application from the previous page's final row. The condition must reflect each key part's direction accurately; using a simple tuple comparison in one direction would be wrong under mixed sort directions. The final tie-breaker key should be unique so no rows are skipped or duplicated across pages.

### 8. NULL, collation, and ORDER BY expressions

Index direction must align with how MySQL sorts values. Under MySQL's default ordering, `NULL` sorts before non-`NULL` values in `ASC` and after them in `DESC`. If the application needs custom `NULL` placement—such as always placing `NULL`s last regardless of direction—you may need a `CASE` expression or a suitable generated column/functional index.

Example:

```sql
SELECT id, published_at
FROM article
ORDER BY
    (published_at IS NULL) ASC,
    published_at DESC,
    id ASC;
```

An index containing only `(published_at DESC, id ASC)` will not necessarily satisfy the full ordering because the `(published_at IS NULL)` expression is the first sort key part. If this is a critical query, you can create a generated column representing the `NULL` flag and index the matching key parts, then verify whether the optimizer uses the index.

Similarly, `ORDER BY LOWER(name)` or sorting under a collation different from the index may require extra computation/sorting. Functional indexes or generated columns can help when the expression is supported and matches the query. Avoid wrapping columns in functions without reason and without a matching index.

### 9. ORDER BY with JOINs and multiple tables

In a `JOIN` query, the data order of an individual table does not guarantee result order after joining. The optimizer may pick a different join order and require sorting after combining rows. An index on the driving table can assist filtering and ordering, yet whether sorting is eliminated depends on join order, join conditions, cardinality, and `ORDER BY` columns.

Example:

```sql
SELECT o.id, o.total, c.name
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE o.status = 'paid'
ORDER BY o.total DESC, o.created_at ASC, o.id ASC
LIMIT 50;
```

A candidate index on `orders`:

```sql
CREATE INDEX idx_orders_status_total_date
ON orders (status ASC, total DESC, created_at ASC, id ASC);
```

This index can support filtering and ordering on `orders`; `customers` needs a suitable index on the join key (typically primary key `id`). Even so, if the optimizer chooses another join plan or must process additional predicates, sorting may still appear. Always verify with `EXPLAIN` on the complete query.

### 10. Costs and limits of descending indexes

Every additional index increases disk usage and write cost. A descending index also requires maintenance on inserts, deletes, or key-part updates. Before creating the index, weigh:

- Which queries truly need mixed ordering and their execution frequency.
- Filter ratio, returned row count, and selectivity of leading key parts.
- Whether an existing index already serves the order via forward/backward scan.
- Index size, key width, buffer pool impact, and added write overhead.
- Whether queries need a covering index or just an index to filter/sort and look up rows.

In InnoDB, change buffering does not apply to secondary indexes that have descending key parts. For write-heavy workloads, this can impact I/O cost compared to an equivalent ascending secondary index. Benchmark under realistic read/write patterns before broad deployment.

Do not create two indexes differing solely in direction unless queries genuinely require both orders. One index can serve the completely reversed order via backward scan, so check reuse of existing indexes first.

### 11. Inspecting indexes and execution plans

View index definitions:

```sql
SHOW CREATE TABLE leaderboard;

SHOW INDEX FROM leaderboard;
```

In MySQL, `INFORMATION_SCHEMA.STATISTICS.COLLATION` typically indicates key-part direction: `A` is ascending, `D` is descending; `NULL` can appear for unordered index types such as spatial indexes.

```sql
SELECT
    INDEX_NAME,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    COLLATION,
    CARDINALITY
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'leaderboard'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Inspect the query plan:

```sql
EXPLAIN
SELECT id, player_name, score, achieved_at
FROM leaderboard
WHERE season_id = 2026
ORDER BY score DESC, achieved_at ASC, id ASC
LIMIT 20;
```

Observe `key`, `type`, `rows`, `filtered`, and `Extra`. If `Extra` includes `Using filesort`, MySQL requires an extra sorting step for that plan. The name `filesort` does not necessarily mean sorting writes to disk files; the algorithm may use memory or temporary files depending on size and configuration.

In MySQL 8.0.18 and later, `EXPLAIN ANALYZE` executes the query and reports actual timings and row counts per iterator:

```sql
EXPLAIN ANALYZE
SELECT id, player_name, score, achieved_at
FROM leaderboard
WHERE season_id = 2026
ORDER BY score DESC, achieved_at ASC, id ASC
LIMIT 20;
```

Use `EXPLAIN ANALYZE` only when running the actual query and consuming its corresponding resources is acceptable. Compare estimates against actual row counts and timings to detect skewed statistics or unexpected plans.

### 12. Design and benchmarking workflow

1. Write the real query with `WHERE` predicates, the full `ORDER BY` list, and `LIMIT`.
2. Record `ASC`/`DESC` direction for each key part, including a unique tie-breaker column.
3. Place appropriate equality filter columns at the front of the index, followed by ordering key parts.
4. Check whether an existing index can serve it via forward or fully backward scan.
5. Create a test index and run `EXPLAIN`; confirm the selected key, rows scanned, and absence/presence of `Using filesort`.
6. Use `EXPLAIN ANALYZE` and benchmark with production-like data distribution; measure p50/p95/p99 latency, CPU, I/O, and insert/update cost.
7. Compare against the plan prior to adding the index; keep the new index only when read/sort gains outweigh storage and write costs.

A benchmark running one query on a warm buffer pool may not represent real load. Test reasonable warm/cold cache states, varied filter values, skewed duplicate counts on leading key parts, and concurrent write workloads.

### 13. Checklist before creating a descending index

1. Is there an important query using mixed `ASC`/`DESC` `ORDER BY`?
2. Is MySQL running version 8.0 with true descending index support, or an older version that ignores `DESC`?
3. Do key-part order and index directions match `ORDER BY` via forward or full backward scan?
4. Are preceding key parts fixed by appropriate predicates?
5. Is a unique tie-breaker key needed for stable pagination?
6. Do `NULL`s, collation, expressions, or `JOIN`s produce an order different from the index?
7. Do `EXPLAIN` and `EXPLAIN ANALYZE` confirm actual benefits?
8. Are storage, buffer pool, DML, and change buffering costs acceptable?

Descending indexes enable InnoDB to store distinct sort directions per key part, thereby supporting multi-directional `ASC`/`DESC` queries that a standard ascending index cannot satisfy with a single backward scan. Effective design must align filter conditions, leftmost prefix, full sort order, `LIMIT`, and actual workload; `EXPLAIN` and benchmarks provide the final validation.
