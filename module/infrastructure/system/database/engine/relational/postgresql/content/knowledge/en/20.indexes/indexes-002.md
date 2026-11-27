# B-tree Indexes and Supported Query Conditions in PostgreSQL

## 1. What Is a B-tree, and Why Does Understanding Query Conditions Matter?

When a PostgreSQL table contains millions of rows, the query:

```sql
SELECT *
FROM orders
WHERE order_id = 123456;
```

should not have to scan every row sequentially if a structure exists that can jump directly to the region containing key `123456`. A **B-tree index** is one of the most important structures for doing exactly that.

A B-tree (Balanced Tree) organizes key entries in a **comparable sort order**, allowing PostgreSQL to locate a specific value, scan a range of values, or read data in key order without necessarily scanning and sorting the entire table. In PostgreSQL, B-tree is the **default index method** for `CREATE INDEX`.

However, creating an index does not guarantee a query will use it. PostgreSQL has to answer two distinct questions:

1. **Can the SQL condition be translated into a search on the B-tree?**
2. **Even if it can, is using the index cheaper than alternative plans?**

For example:

- `customer_id = 42` can be a key lookup.
- `ordered_at >= t1 AND ordered_at < t2` can be a range scan.
- `email LIKE 'user001%'` can leverage a B-tree by prefix under the right collation or operator class.
- `email LIKE '%example.test'` has no fixed leading prefix, so a standard B-tree cannot narrow down a useful key range for this pattern.
- `lower(email) = 'abc'` does not automatically use an index built only on `email`; an **expression index** on `lower(email)` may be required.
- `ORDER BY ordered_at DESC LIMIT 20` is often where a B-tree shines, even when the `WHERE` clause has no equality predicate.

**Key point:** understanding condition types and index column order helps you write queries capable of efficient lookups, yet **the planner still chooses the actual plan** based on statistics and cost estimates.

### Learning Objectives

After this lesson, you will be able to:

1. Explain how a B-tree organizes keys and why it supports exact lookups, ranges, and ordering.
2. Recognize how `=`, `<`, `<=`, `>`, `>=`, `BETWEEN`, `IN`, and `IS NULL` interact with B-trees.
3. Distinguish conditions that **restrict the index scan** from conditions evaluated only as post-scan filters.
4. Understand the exceptions and limits of `LIKE`, `ILIKE`, regular expressions, `text_pattern_ops`, and collations.
5. Design composite index column order around **equality first, range later**, while understanding this is a heuristic rather than an absolute rule across all planner versions.
6. Use B-trees to support `ORDER BY`, `LIMIT`, keyset pagination, `MIN`/`MAX`, and certain `DISTINCT`/`GROUP BY` operations.
7. Apply expression indexes, partial indexes, and `INCLUDE` appropriately.
8. Read `EXPLAIN` output to distinguish `Index Cond`, `Filter`, `Index Scan`, `Bitmap Index Scan`, and `Index Only Scan`.
9. Explain why a valid index might still go unused.
10. Avoid over-indexing by accounting for write, update, `VACUUM`, and maintenance costs.

---

## 2. Intuition Behind the B-tree Structure

A B-tree does not store every row in a list that must be read from the start. It partitions the key space into ordered regions across multiple page levels:

```text
                     [ 30 | 70 ]
                    /     |      \
                   /      |       \
             keys <30   30..69   >=70
                 |        |        |
            [10|20]   [40|55]   [80|90]
                 \        |        /
                    Leaf entries
               pointing to table rows
```

This diagram illustrates only the concept; PostgreSQL's actual page format and implementation details are more complex.

Important characteristics of a B-tree:

- Keys follow a **total order defined by the operator class and collation** where applicable.
- Searches traverse from the root page through internal levels down to the target key region.
- Leaf pages support scanning adjacent keys efficiently during range queries.
- The tree stays balanced as rows are inserted, updated, or deleted; users never balance it manually.
- An index entry does not equate to a full row record. PostgreSQL typically uses the **heap TID** to locate the row version in the heap table, unless an **index-only scan** meets the required conditions.

### 2.1. Lookup Cost vs. Read Cost

When querying `order_id = 123456` with a highly selective index, PostgreSQL traverses a few index pages and fetches very few heap pages.

But if a query returns 80% of the table, traversing the index and touching countless heap pages can be more expensive than a **sequential scan**. Thus, the fact that an index **can support** a comparison does not force the planner to **pick an index scan**.

### 2.2. A B-tree Does Not Replace Table Storage

PostgreSQL still stores table data and row versions in the heap under standard MVCC rules. A B-tree is an **auxiliary access structure** maintained when data changes.

One table can have several B-tree indexes on different keys:

```sql
CREATE INDEX ON orders(customer_id);
CREATE INDEX ON orders(ordered_at);
CREATE INDEX ON orders(status, ordered_at);
```

These three indexes serve different access patterns and incur separate storage and write costs. Never create all of them just because those columns appear in SQL; evaluate the actual workload.

## 3. Creating Lab Data to Observe Query Plans

Use a dedicated learning database and separate schema. The creation and insert scripts below are **strictly for running in a lab**, not for running blindly in production.

### 3.1. Orders Table

```sql
CREATE SCHEMA IF NOT EXISTS btree250;

CREATE TABLE btree250.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id integer NOT NULL,
    status text NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    ordered_at timestamptz NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents >= 0),
    reference_code text NOT NULL
);
```

To generate enough rows for the planner to consider indexes, populate 60,000 synthetic orders using `generate_series`:

```sql
INSERT INTO btree250.orders(
    customer_id,
    status,
    ordered_at,
    amount_cents,
    reference_code
)
SELECT
    (g.n % 2000) + 1 AS customer_id,
    CASE
        WHEN g.n % 20 IN (0, 1) THEN 'CANCELLED'
        WHEN g.n % 20 IN (2, 3, 4, 5) THEN 'PAID'
        ELSE 'NEW'
    END AS status,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g.n % 365) * INTERVAL '1 day'
        + (g.n % 86400) * INTERVAL '1 second' AS ordered_at,
    ((g.n % 5000) + 1) * 100::bigint AS amount_cents,
    'REF-' || lpad(g.n::text, 6, '0') AS reference_code
FROM generate_series(1, 60000) AS g(n);
```

Each time you run this `INSERT` script, it will **add another 60,000 rows**. If you ran it previously, use a fresh lab schema or intentionally reset the fixture.

Quick verification:

```sql
SELECT COUNT(*) AS total_orders
FROM btree250.orders;

SELECT status, COUNT(*)
FROM btree250.orders
GROUP BY status
ORDER BY status;
```

Expected counts after a single insert:

| status | Order count |
|---|---:|
| CANCELLED | 6,000 |
| NEW | 42,000 |
| PAID | 12,000 |

### 3.2. Customers Table for String Queries

```sql
CREATE TABLE btree250.customers (
    customer_id integer PRIMARY KEY,
    email text NOT NULL UNIQUE,
    display_name text NOT NULL
);

INSERT INTO btree250.customers(
    customer_id, email, display_name
)
SELECT
    g.n,
    'user' || lpad(g.n::text, 5, '0') || '@example.test',
    'Customer ' || g.n::text
FROM generate_series(1, 20000) AS g(n);
```

Examples:

```text
customer_id = 1     email = user00001@example.test
customer_id = 100   email = user00100@example.test
customer_id = 1000  email = user01000@example.test
```

`PRIMARY KEY` and `UNIQUE` have already created the appropriate indexes to enforce uniqueness. Do not create a second B-tree index with the same definition without a specific reason.

### 3.3. Updating Lab Statistics

```sql
ANALYZE btree250.orders;
ANALYZE btree250.customers;
```

`ANALYZE` gathers statistics that help the planner estimate row counts and choose plans. In production, autovacuum/autoanalyze normally handles this automatically as configured; you do not need to run `ANALYZE` unconditionally after every `INSERT`.

### 3.4. Plans Can Vary

The `EXPLAIN` queries in this lesson are meant for **observation when you run them yourself**. Do not treat a mentioned plan node as a measurement guaranteed on your server.

Plans vary based on:

- Row count and data distribution.
- PostgreSQL version.
- Statistics.
- Table and index sizes.
- Workload and buffer cache state.
- Collation, operator class, and data types.
- Planner settings and I/O cost parameters.
- Presence or absence of other indexes on the same table.

## 4. Core Comparison Operators Supported by B-trees

Standard B-tree operator classes are built around five ordered comparison strategies:

| Operator | Meaning | B-tree Intuition |
|---|---|---|
| `<` | Less than | Scan key region below threshold |
| `<=` | Less than or equal | Scan key region up to threshold |
| `=` | Equal | Locate specific key or group of matching keys |
| `>=` | Greater than or equal | Scan from threshold upward |
| `>` | Greater than | Scan key region above threshold |

In addition, with compatible data types and operator classes, B-trees support `IS NULL` and `IS NOT NULL`, as well as SQL constructs that the planner rewrites into equivalent searches.

**Note:** not every custom operator named `=` or `<` automatically works with every B-tree. Operator support depends on the **operator family/class**, data types, and how the query expression matches the index definition.

### 4.1. Equality Condition

```sql
SELECT order_id, status, amount_cents
FROM btree250.orders
WHERE order_id = 1250;
```

`order_id` is the `PRIMARY KEY`, so it already has a unique B-tree index. This is a highly selective key lookup; the planner normally has good reason to pick an Index Scan.

### 4.2. Range Condition

Create a timestamp index:

```sql
CREATE INDEX idx_btree250_orders_ordered_at
ON btree250.orders(ordered_at);
```

Then run:

```sql
SELECT order_id, ordered_at, amount_cents
FROM btree250.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-05-01 00:00:00+00';
```

These two predicates define a **half-open** interval:

```text
[2026-04-01 00:00:00+00, 2026-05-01 00:00:00+00)
```

The advantage of a half-open range is avoiding guesswork about microsecond precision or constructing timestamps like “23:59:59.999999”.

### 4.3. BETWEEN

```sql
SELECT *
FROM btree250.orders
WHERE amount_cents BETWEEN 10000 AND 20000;
```

`BETWEEN a AND b` has **inclusive endpoints**, equivalent to:

```sql
amount_cents >= 10000 AND amount_cents <= 20000
```

For an index to be used effectively on `amount_cents`, you need a suitable index on that column or a composite index aligned with the query structure.

### 4.4. Greater-Than/Less-Than Is Not Always Fast

```sql
SELECT *
FROM btree250.orders
WHERE amount_cents >= 100;
```

If nearly every row satisfies `amount_cents >= 100`, a sequential scan can be cheaper than an index scan. **Operator support does not guarantee a cost advantage.**

## 5. Distinguishing Index Cond from Filter

Conditions in `WHERE` can be applied at different stages of execution.

For example, create an index:

```sql
CREATE INDEX idx_btree250_orders_customer
ON btree250.orders(customer_id);
```

Query:

```sql
EXPLAIN
SELECT order_id, customer_id, status, amount_cents
FROM btree250.orders
WHERE customer_id = 42
  AND amount_cents > 200000;
```

When the planner uses the index on `customer_id`, the plan might show:

```text
Index Scan using idx_btree250_orders_customer ...
  Index Cond: (customer_id = 42)
  Filter: (amount_cents > 200000)
```

**This is an illustrative structure**, not live execution output.

Interpretation:

- **`Index Cond`**: conditions used by the index access method to locate or bound which index entries to examine.
- **`Filter`**: additional conditions evaluated after candidate rows are fetched, depending on the plan node.
- If `Rows Removed by Filter` appears in `EXPLAIN ANALYZE`, it tells you how many rows were discarded at that node.

Note that a condition can appear in `Index Cond` and still scan many entries if a composite index lacks predicates on leading columns, or if the search condition does not narrow the key range much. **Appearing in `Index Cond`** does not mean every non-matching row is skipped at zero cost.

### 5.1. Same WHERE, Different Index, Different Plan

If you create a composite index:

```sql
CREATE INDEX idx_btree250_orders_customer_amount
ON btree250.orders(customer_id, amount_cents);
```

then:

```sql
WHERE customer_id = 42
  AND amount_cents > 200000
```

can be bounded using both components of the B-tree: an equality condition on the leading column, followed by a range condition on the second column.

By contrast, a single-column index on `customer_id` typically has to fetch candidate rows to test the amount condition if it is not present in the index.

## 6. Exact Key Lookup and Selectivity

To find a single order by `PRIMARY KEY`:

```sql
SELECT *
FROM btree250.orders
WHERE order_id = 10000;
```

The index created by `PRIMARY KEY` is a unique B-tree unless specialized structures are explicitly used by design. At most one row can match a given `order_id`.

For:

```sql
SELECT *
FROM btree250.orders
WHERE status = 'NEW';
```

even though a B-tree index on `status` can locate the `'NEW'` key region, the lab dataset has 42,000 out of 60,000 orders with `status = 'NEW'`. Needing to read nearly 70% of the table and fetch unindexed columns often leads the planner to prefer `Seq Scan`.

### 6.1. Why Shouldn't You Index Every Boolean/Status Column?

A low-cardinality column is **not automatically useless to index**, but common values may match too large a fraction of rows.

For example:

- `status='NEW'`: 70% of rows → typically low selectivity.
- `status='CANCELLED'`: 10% of rows → may be more useful in some queries.
- `status='PAID' AND ordered_at >= yesterday`: combining with a time range can be much more selective.
- `status='NEW' ORDER BY ordered_at DESC LIMIT 20`: a composite index can still be very effective even for a common status, because only the top few ordered rows are needed.

Evaluate the **entire predicate set, ordering, and row limit**, not just single-column cardinality.

## 7. IN (...) and = ANY (...): Multiple Exact Values

Example fetching orders for a few customers:

```sql
SELECT order_id, customer_id, status
FROM btree250.orders
WHERE customer_id IN (10, 42, 77);
```

Or:

```sql
SELECT order_id, customer_id, status
FROM btree250.orders
WHERE customer_id = ANY (ARRAY[10, 42, 77]);
```

PostgreSQL can use a B-tree index on `customer_id` to perform multiple equality lookups, depending on plan and cost.

### 7.1. IN Does Not Mean a Continuous Range

`IN (10, 42, 77)` specifies three discrete values; it is not equivalent to:

```sql
customer_id BETWEEN 10 AND 77
```

Because `BETWEEN` includes `customer_id` values 11, 12, ... 76, returning unintended rows.

### 7.2. Very Large IN Lists

An `IN`-list with thousands or tens of thousands of elements can bloat query text, increase parse/plan time, or degrade plan quality. For large key sets, consider:

- A temporary table holding the keys and a `JOIN`.
- `= ANY($1::integer[])` with a prepared statement where appropriate.
- Bounded batching.
- Inspecting plan choices and selectivity.

B-trees can still participate, but never assume a huge `IN`-list automatically beats a join.

### 7.3. NULL Inside IN

`x IN (1, NULL)` follows three-valued logic. When `x` does not match `1`, the result evaluates to `UNKNOWN`, not standard `FALSE`. In particular, `NOT IN` over a list or subquery containing `NULL` easily produces unexpected empty results.

To test for NULL explicitly, use `IS NULL`; for set anti-joins, consider `NOT EXISTS` with well-defined NULL semantics.

## 8. IS NULL and IS NOT NULL on B-trees

PostgreSQL B-trees can store NULL keys and support searching for NULLs directly.

Example creating an illustrative table with nullable timestamps:

```sql
CREATE TABLE btree250.tasks (
    task_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    completed_at timestamptz
);

INSERT INTO btree250.tasks(title, completed_at)
VALUES
    ('Task A', NULL),
    ('Task B', TIMESTAMPTZ '2026-06-01 12:00:00+00'),
    ('Task C', NULL);
```

Create an index:

```sql
CREATE INDEX idx_btree250_tasks_completed_at
ON btree250.tasks(completed_at);
```

Two queries:

```sql
SELECT *
FROM btree250.tasks
WHERE completed_at IS NULL;

SELECT *
FROM btree250.tasks
WHERE completed_at IS NOT NULL;
```

In terms of operator capability, B-trees support both `IS NULL` and `IS NOT NULL`. However, on a lab table with **only three rows**, `Seq Scan` is usually cheaper.

### 8.1. NULLS FIRST and NULLS LAST

B-trees maintain a defined sort placement for NULLs. A default ascending index typically corresponds to:

```sql
CREATE INDEX ... ON some_table(column ASC NULLS LAST);
```

Scanning the index backward produces `DESC NULLS FIRST`. If your business query requires `DESC NULLS LAST` or another ordering combination, you may need an index created with the matching sort direction and `NULLS` option.

### 8.2. IS NULL Is Not the Same as = NULL

Wrong:

```sql
WHERE completed_at = NULL
```

Comparing against `NULL` with `=` evaluates to `UNKNOWN`, never true for NULL rows.

Right:

```sql
WHERE completed_at IS NULL
```

This is fundamental SQL logic, and it also determines whether the condition can become an index qual.

## 9. Conditions That Usually Do Not Produce a Useful B-tree Range

### 9.1. Negation

Example:

```sql
WHERE status <> 'PAID'
```

The `<>`/`!=` operator is not one of the core comparison strategies for bounding a single contiguous B-tree range. The matching set is often large, so the planner rarely gains much from a single-column `status` B-tree.

**Do not make the absolute claim that queries with `<>` can never use an index:** the planner can still use an index due to other conditions, sort order, partial indexes, or expression rewrites. The point is that `<>` by itself is rarely as effective as a selective `=` or range predicate on a key.

### 9.2. NOT LIKE and Substring Matches

```sql
WHERE email NOT LIKE 'user001%'

WHERE email LIKE '%001%'

WHERE email LIKE '%@example.test'
```

Negations or patterns lacking a fixed leading prefix do not map naturally onto **a contiguous key range in textual B-tree order**. For true substring searches, another indexing approach such as `pg_trgm` with GIN/GiST usually needs to be evaluated.

### 9.3. Operations That Don't Match the Indexed Expression

Having a B-tree on `ordered_at` does not mean the query below can automatically use that same index efficiently:

```sql
WHERE ordered_at::date = DATE '2026-05-01'
```

Applying a cast to the column produces a different search expression from the original `ordered_at`. With `timestamptz`, timezone behavior also comes into play.

Prefer filtering with a timestamp range on the raw column:

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-05-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-05-02 00:00:00+00'
```

or create an appropriate expression index if the query truly needs that expression and the expression is indexable.

## 10. Prefix LIKE: When B-trees Can Help String Searches

B-trees sort strings according to the relevant operator class and collation. A pattern with a **fixed leading prefix** lets PostgreSQL narrow down a relevant key region in many cases.

Example:

```sql
SELECT customer_id, email
FROM btree250.customers
WHERE email LIKE 'user001%';
```

In the lab data, emails from `user00100...` through `user00199...` are matching candidates.

### 10.1. Important Requirement: Collation

Do not claim that **every default text B-tree** automatically optimizes `LIKE 'abc%'` under every locale.

Under the `C` collation, string sort order aligns with prefix matching for ordinary B-trees. Under many non-`C` collations, PostgreSQL requires a **pattern operator class** to support prefix pattern matching.

For example:

```sql
CREATE INDEX idx_btree250_customers_email_pattern
ON btree250.customers(email text_pattern_ops);
```

This index uses `text_pattern_ops` on the `text` column, supporting prefix pattern matching under supported deterministic collations.

Then run:

```sql
EXPLAIN
SELECT customer_id, email
FROM btree250.customers
WHERE email LIKE 'user001%';
```

The planner can use the pattern B-tree index with prefix bounds. The plan may show internal operators of the pattern operator class such as `~>=~` and `~<~` alongside a `LIKE` filter; do not treat those as business operators to type into your `WHERE` clauses.

### 10.2. Pattern Opclasses Do Not Replace Locale Ordering in All Cases

`text_pattern_ops` uses character-by-character comparison suitable for pattern matching, which can differ from the linguistic ordering expected by `ORDER BY email` under a locale collation.

If your workload needs both:

- `LIKE 'abc%'` lookups;
- linguistic range comparisons or `ORDER BY` sorting;

you may need **two indexes with different opclasses/collations**, or a consistent collation design suited to the data.

Do not create both on every table by default; measure the workload first.

### 10.3. Corresponding Opclasses for varchar and char

Common pattern operator classes include:

- `text_pattern_ops` for `text`.
- `varchar_pattern_ops` for `varchar`.
- `bpchar_pattern_ops` for `char`/`bpchar`.

Choose the opclass matching the column or expression type. Never change column types or operator classes arbitrarily just to make a single `EXPLAIN` example pick an index.

## 11. Prefix LIKE vs. Substring LIKE

Comparison table:

| Condition | Meaning | Can a standard/pattern B-tree help? |
|---|---|---|
| `email = 'user00100@example.test'` | Exact equality | Yes, unique B-tree |
| `email LIKE 'user001%'` | Fixed prefix | Possibly, with compatible collation/opclass |
| `email LIKE 'user%'` | Overly broad prefix | Operator-compatible, though Seq Scan may be cheaper |
| `email LIKE '%001'` | Suffix | Usually does not form a useful B-tree range |
| `email LIKE '%001%'` | Substring | Usually unsuitable for B-tree |
| `email LIKE 'u_er001%'` | Wildcard inside prefix | Can only leverage the fixed portion before the first wildcard, if selective enough |
| `email LIKE 'user001'` | Pattern with no wildcards | May be optimized like an exact lookup depending on type/collation |
| `email ILIKE 'USER001%'` | Case-insensitive | Does not automatically use a standard text B-tree the way case-sensitive LIKE does |

Remember that **the prefix must contain no wildcards and must match the comparison semantics**. An overly short prefix matching most of the table still will not guarantee speed even if an index is used.

### 11.1. Anchored Regular Expressions

In appropriate cases, PostgreSQL can also extract a fixed prefix from case-sensitive anchored regular expressions:

```sql
WHERE email ~ '^user001'
```

However, index condition extraction varies by regex pattern and collation/matching rules. When you only need a simple prefix search, `LIKE 'user001%'` is usually easier to read and verify.

### 11.2. Complex Pattern Matching: Consider pg_trgm

If your primary need is:

```sql
WHERE email LIKE '%001%'
```

or flexible `ILIKE` searches, B-tree is not a specialized substring structure. PostgreSQL provides the `pg_trgm` extension with GIN/GiST operator classes:

```sql
-- Alternative example only; verify extension availability and privileges:
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_btree250_customers_email_trgm
ON btree250.customers
USING gin (email gin_trgm_ops);
```

Do not assume the extension is already installed or that your role has permission to install it in production. Trigram indexes carry their own storage and write costs, and effectiveness depends on search patterns, string length, and data distribution.

## 12. ILIKE and Expression Indexes on lower(...)

`ILIKE` performs case-insensitive pattern matching. For prefixes containing letters, a B-tree on raw column values **does not automatically convert into** an index lookup for arbitrary `ILIKE` patterns.

One design approach is to **normalize the expression in both the index and the query**:

```sql
CREATE INDEX idx_btree250_customers_lower_email_pattern
ON btree250.customers(
    (lower(email)) text_pattern_ops
);
```

Query:

```sql
SELECT customer_id, email
FROM btree250.customers
WHERE lower(email) LIKE 'user001%';
```

The indexed key is **`lower(email)`**, matching the expression used in the query. PostgreSQL can then bound the prefix through the expression index.

### 12.1. Why Not Simply Index email?

```sql
CREATE INDEX ... ON customers(email);
```

An index on `email` stores keys in the order of original values, not necessarily in the order of `lower(email)`. When `WHERE` evaluates `lower(email)`, a matching expression index or an alternative design is needed.

### 12.2. Case-Insensitive Equality Lookups

You can write:

```sql
WHERE lower(email) = lower('USER00100@EXAMPLE.TEST')
```

backed by a B-tree expression index on `lower(email)`. If an index `lower(email) text_pattern_ops` was built primarily for `LIKE`, verify whether it also satisfies your workload's equality/range semantics; a separate index may be needed for locale-based ordering.

### 12.3. Unicode and Collations

`lower()` and locale-dependent comparisons have nuances and limits with Unicode case folding and normalization. Do not treat `lower(email)` as a universal solution for every **locale-independent Unicode comparison** requirement.

For critical identifiers, systems need a consistent normalization policy, suitable collation, uniqueness rules, and tests against real linguistic data.

## 13. Equality + Range with Multi-Column Indexes

A composite B-tree index defines a **column order**. For example:

```sql
CREATE INDEX idx_btree250_orders_status_time
ON btree250.orders(status, ordered_at);
```

The index keys can be visualized as ordered pairs:

```text
(status, ordered_at)

('CANCELLED', t1)
('CANCELLED', t2)
...
('NEW', t1)
('NEW', t2)
...
('PAID', t1)
('PAID', t2)
...
```

With:

```sql
SELECT order_id, status, ordered_at
FROM btree250.orders
WHERE status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-04-01 00:00:00+00';
```

the planner can target the key slice:

```text
status = PAID
and ordered_at in [2026-03-01, 2026-04-01)
```

This is the classic pattern:

> **Equality predicates on leading columns, range predicate on the next column.**

### 13.1. Why Is Leading Equality Helpful?

Once the first column is pinned to `status = 'PAID'`, all `ordered_at` values for that status lie in a contiguous sorted slice inside the composite index. This tightly bounds the scan range.

If you only have:

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
```

against `(status, ordered_at)`, the index's global order is **grouped by `status` first**. Timestamps after the threshold are scattered across different status sections, making this composite index much less direct than `(ordered_at)` for time-only filters.

### 13.2. Leftmost Prefix Is a Heuristic, Not an Absolute Ban

Common design intuition:

- Index `(a, b, c)` works best when predicates constrain `a`.
- Having `a = ?` and `b = ?` leverages multiple key components.
- Having `a = ?` and `b > ?` typically narrows down a contiguous region.
- Predicates on `c` after a range column can still be checked within the index, though they do not necessarily restrict the whole scan range to one interval.

**However:** PostgreSQL includes multiple scan optimizations and strategies, including **skip scan** in supported versions and scenarios. Thus, omitting a leading column predicate does not prove a composite index can **never be used**.

Inspect `EXPLAIN` instead of treating the leftmost-prefix heuristic as a hard prohibition.

## 14. Multiple Columns: Equality, Range, and Trailing Conditions

Consider the index:

```sql
CREATE INDEX idx_btree250_orders_customer_status_time
ON btree250.orders(
    customer_id,
    status,
    ordered_at
);
```

Query:

```sql
SELECT order_id, customer_id, status, ordered_at
FROM btree250.orders
WHERE customer_id = 42
  AND status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00';
```

This matches well because:

1. `customer_id = 42` constrains the first column.
2. `status = 'PAID'` constrains the second column.
3. `ordered_at >= ...` bounds the range on the third column.

### 14.1. What If the Middle Column Is Unconstrained?

```sql
WHERE customer_id = 42
  AND ordered_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00'
```

The B-tree can locate the `customer_id = 42` group, but timestamps for each `status` reside in separate sub-regions. Depending on PostgreSQL version and conditions, the planner may filter on trailing columns within the index, perform a skip scan, or pick a different index.

Do not claim the timestamp condition is **completely ignored**; rather, it does not always restrict the scanned key range as tightly as when preceding columns are fixed by equality.

### 14.2. What If There Is a Range on the First Column?

```sql
WHERE customer_id > 100
  AND status = 'PAID'
```

The range on `customer_id` opens up many customer groups. Equality on `status` can filter index entries, yet it does not form a single contiguous `'PAID'` slice across the index. Sometimes `(status, customer_id)` fits better if this query is a hot path.

### 14.3. Don't Apply Only the “Most Selective Column First” Rule

When designing composite indexes, consider:

- Equality conditions that actually appear in the workload.
- Range conditions.
- `ORDER BY` and `LIMIT`.
- Queries using only a subset of conditions.
- Selectivity and number of distinct values.
- Index-only scan potential.
- Other existing indexes.
- Key ordering and write costs.

A blanket rule of “always put the highest-selectivity column first” is overly simplistic.

## 15. B-trees and ORDER BY Ordering

Because a B-tree stores keys in sorted order, it can eliminate a `Sort` step.

Create:

```sql
CREATE INDEX idx_btree250_orders_time_desc
ON btree250.orders(ordered_at DESC);
```

Query:

```sql
SELECT order_id, ordered_at, status
FROM btree250.orders
ORDER BY ordered_at DESC
LIMIT 20;
```

This is often a major win: PostgreSQL can read **the first 20 rows in index order** instead of scanning and sorting all 60,000 rows, provided plan costs and heap/visibility checks cooperate.

### 15.1. A Single B-tree Index Can Be Scanned Backward

A single-column ascending B-tree can be scanned in reverse to serve descending order:

```sql
CREATE INDEX idx_btree250_orders_time_asc
ON btree250.orders(ordered_at ASC);
```

Therefore, you rarely need two identical single-column indexes differing only by `ASC`/`DESC`, unless there is a specific reason such as `NULLS` ordering or workload needs.

### 15.2. NULLS FIRST/LAST Affects Matching

A default ascending B-tree uses `NULLS LAST`; scanning it backward produces `DESC NULLS FIRST`.

If a query requests:

```sql
ORDER BY completed_at DESC NULLS LAST
```

on a nullable column, a matching index may need to declare that explicit direction and `NULLS` option. Never assume any `ORDER BY` with NULLs matches an arbitrary index without a `Sort`.

### 15.3. ORDER BY Without WHERE Can Still Use an Index

An index is not solely for `WHERE` clauses. The query:

```sql
SELECT *
FROM btree250.orders
ORDER BY ordered_at
LIMIT 10;
```

can leverage the B-tree on `ordered_at` even without any filter predicates.

### 15.4. ORDER BY Over the Entire Table

If a query fetches and returns nearly all rows, an index scan may touch many heap pages randomly. PostgreSQL will sometimes choose `Seq Scan` + `Sort` instead of walking the index. Index ordering shines brightest with a **small `LIMIT`** or when all needed columns are covered by the index.

## 16. Multi-Column ORDER BY: Sort Directions Can Dictate the Index

Create index:

```sql
CREATE INDEX idx_btree250_orders_status_time_id
ON btree250.orders(
    status ASC,
    ordered_at DESC,
    order_id DESC
);
```

Query:

```sql
SELECT order_id, status, ordered_at
FROM btree250.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 25;
```

Because `status` is pinned by equality, the order `ordered_at DESC, order_id DESC` within the `'PAID'` slice matches the index order. PostgreSQL can read the newest rows and stop early.

### 16.1. What Without WHERE status?

```sql
SELECT order_id, status, ordered_at
FROM btree250.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 25;
```

Index `(status, ordered_at DESC, order_id DESC)` sorts by `status` first. It **does not** provide a global ordering by `ordered_at` across all statuses. An index on `(ordered_at DESC, order_id DESC)` would fit better here.

### 16.2. Mixed ASC/DESC Directions

An index `(a ASC, b ASC)` scans forward in:

```text
a ASC, b ASC
```

and backward in:

```text
a DESC, b DESC
```

However, a query with:

```sql
ORDER BY a ASC, b DESC
```

does not directly match either scan direction of that index; you may need an index declared with mixed directions:

```sql
CREATE INDEX example_mixed_order_idx
ON some_table(a ASC, b DESC);
```

When leading columns are pinned by equality, some direction differences within those leading columns no longer affect the group being read; design around **actual queries**, not index names.

## 17. Keyset Pagination: B-tree with ORDER BY and Tuple Comparisons

Large `OFFSET` values force PostgreSQL to step through and discard many rows:

```sql
SELECT order_id, ordered_at
FROM btree250.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20 OFFSET 40000;
```

For deep pagination or infinite scroll, **keyset pagination** is usually a much better fit.

Create index:

```sql
CREATE INDEX idx_btree250_orders_time_id_desc
ON btree250.orders(ordered_at DESC, order_id DESC);
```

First page:

```sql
SELECT order_id, ordered_at, status
FROM btree250.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Save the `ordered_at` and `order_id` values from the last row. Next page:

```sql
SELECT order_id, ordered_at, status
FROM btree250.orders
WHERE (ordered_at, order_id)
    < (TIMESTAMPTZ '2026-11-01 12:00:00+00', 12345)
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

The two literal values in the second-page query are **illustrative placeholders**; in an application, pass the actual values from the last row of the previous page.

### 17.1. Why Include order_id?

If multiple orders share the exact same `ordered_at` timestamp and you sort only by timestamp, row ordering across ties is nondeterministic.

The pair `(ordered_at, order_id)` establishes a deterministic total order when `order_id` is unique.

### 17.2. Tuple Comparison and DESC Order

When both columns sort descending, the next page corresponds to keys **lexicographically smaller** than the last tuple. PostgreSQL can use a matching B-tree for row-wise comparisons when compatible operator classes apply.

If `ORDER BY` mixes `ASC` and `DESC`, or involves `NULL`s, the simple row comparison above can be **incorrect**; write explicit lexicographic conditions matching each component's direction and `NULLS` ordering.

### 17.3. Pagination Does Not Create a Permanent Consistent Snapshot

When pages are fetched across separate requests and transactions, rows can be inserted, deleted, or updated between pages. Keyset pagination is more stable than `OFFSET` in many scenarios, yet it does not guarantee an immutable list over time. If your business logic requires a fixed snapshot, design appropriate transaction snapshots or cutoff markers.

## 18. MIN, MAX, DISTINCT, and GROUP BY

Because B-trees maintain order, they can assist operations beyond `WHERE`.

### 18.1. MIN/MAX

```sql
SELECT MIN(ordered_at)
FROM btree250.orders;

SELECT MAX(ordered_at)
FROM btree250.orders;
```

With a matching B-tree, PostgreSQL can often optimize `MIN`/`MAX` by reading just the start or end of the key range rather than scanning the whole table. Not every expression inside `MIN`/`MAX` receives this optimization.

### 18.2. DISTINCT

```sql
SELECT DISTINCT customer_id
FROM btree250.orders
ORDER BY customer_id;
```

An index on `customer_id` can supply sorted input, assisting some `DISTINCT`/`Unique` plans. Still, with many duplicates or when reading most of the table, hash aggregation or a sequential scan can be cheaper.

### 18.3. GROUP BY

```sql
SELECT customer_id, COUNT(*) AS orders_count
FROM btree250.orders
GROUP BY customer_id
ORDER BY customer_id;
```

The planner may use index order for `GroupAggregate` or choose `HashAggregate` based on cost.

**Do not create an index merely because a SQL query contains `GROUP BY`.** Check data volume, group counts, competing queries, and chosen plans.

### 18.4. Merge Join and Nested Loop

B-trees can assist joins:

- Nested Loop when the outer side supplies a key and the inner table has a fast index lookup.
- Merge Join when both inputs are sorted by the join key, sometimes exploiting index order.
- Other join strategies like Hash Join can still be cheaper on large datasets.

Having a suitable index does not force the planner to use Index Scan or Merge Join.

## 19. B-trees and Data Types

B-trees are not just for integers.

Types that commonly have suitable B-tree operator classes include:

- Integer/bigint and other numeric types.
- `numeric`.
- `date`, `timestamp`, `timestamptz`.
- `text`, `varchar`, and other string types.
- `boolean`.
- `uuid`.
- Certain network types, enums, and custom types with supporting operator classes.

Examples:

```sql
CREATE INDEX idx_btree250_orders_amount
ON btree250.orders(amount_cents);

CREATE INDEX idx_btree250_orders_status
ON btree250.orders(status);
```

However, complex types like JSONB, arrays, spatial geometry, or full-text search involve operators and access patterns where **GIN/GiST/SP-GiST/BRIN** or other strategies are usually a better fit.

### 19.1. Data Types and Implicit Casts

Suppose `customer_id` is an `integer`. Query:

```sql
WHERE customer_id = '42'
```

PostgreSQL can infer the constant's type cleanly in many situations. But if the application casts the indexed column to a different type:

```sql
WHERE customer_id::text = '42'
```

then an index built on the raw `customer_id` column **will not necessarily match**.

When using prepared statements, bind parameters with the matching column type and avoid wrapping indexed columns in casts inside `WHERE` unless necessary.

### 19.2. Timezone Comparisons

A `timestamptz` column represents an absolute point in time; literals with explicit offsets define search bounds independent of session timezone:

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-05-01 00:00:00+00'
```

If an application needs “calendar day in Vietnam time,” compute the exact day boundaries in the business timezone and convert them to `timestamptz` bounds. Never rewrite to `ordered_at::date` and assume both timezone correctness and optimal index usage.

## 20. Expression Indexes: When WHERE Uses Functions or Expressions

A plain index:

```sql
CREATE INDEX idx_btree250_customers_email
ON btree250.customers(email);
```

stores `email` keys. If queries consistently filter with:

```sql
WHERE lower(email) = 'user00100@example.test'
```

consider indexing **the same expression**:

```sql
CREATE INDEX idx_btree250_customers_lower_email
ON btree250.customers(lower(email));
```

Now `lower(email)` can be searched via B-tree.

### 20.1. Expressions Must Match Semantically

An index on `lower(email)` does not serve arbitrary functions of `email`:

```sql
WHERE upper(email) = 'USER00100@EXAMPLE.TEST'
```

This query uses a different expression; never assume it will be optimized by the `lower(email)` index.

### 20.2. Not Every Expression Can Be Indexed

Functions used in index expressions must satisfy PostgreSQL's immutability rules and related requirements.

For example, casting `timestamptz` directly to `date` depends on the session timezone, so an expression index like:

```sql
-- Do not assume this is allowed or has stable semantics:
CREATE INDEX ...
ON some_table((timestamptz_column::date));
```

can be rejected by PostgreSQL because the expression is not `IMMUTABLE`.

Instead of hunting for workarounds to bypass the error, clarify the business timezone, transform the expression in a supported deterministic way, and verify on your target server version.

### 20.3. Cost of Expression Indexes

On every `INSERT` or `UPDATE` affecting the underlying columns, PostgreSQL may have to evaluate the expression and maintain the index. With many expression indexes, write overhead climbs. Create them only when important queries gain clear value.

## 21. Partial B-tree Indexes: Indexing a Subset

If most orders are `'NEW'` yet the system frequently queries **recent `'PAID'` orders**, you can test:

```sql
CREATE INDEX idx_btree250_orders_paid_time
ON btree250.orders(ordered_at DESC, order_id DESC)
WHERE status = 'PAID';
```

Query:

```sql
SELECT order_id, ordered_at, amount_cents
FROM btree250.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

The index stores only rows matching `status = 'PAID'`, making it smaller than a full-table time index across all statuses.

### 21.1. The Planner Must Prove the Query's WHERE Implies the Predicate

A partial index is only eligible when PostgreSQL can prove all target rows definitely satisfy the index predicate.

For instance:

```sql
WHERE status = 'PAID'
```

clearly implies `status = 'PAID'`.

By contrast:

```sql
WHERE status = $1
```

in a prepared statement using a **generic plan** does not imply `status = 'PAID'` for all parameter values. The partial index may not be selected even when the current execution binds `'PAID'`.

### 21.2. Do Not Write “Recent” Predicates Based on now() in an Index

A partial index with a moving time predicate such as:

```sql
-- Not a valid index predicate for sliding time windows:
CREATE INDEX ...
ON some_table(ordered_at)
WHERE ordered_at > now() - INTERVAL '7 days';
```

Index predicates require immutable expressions; `now()` changes over time. Moreover, an index does not automatically “slide its 7-day window” as the clock advances without maintenance.

Instead, use predicates on stable statuses, explicitly managed fixed cutoffs, time-based partitioning, or standard range indexes on the timestamp column.

### 21.3. A Partial Index Does Not Replace a Composite Index for All Queries

If queries sometimes span all statuses, a `'PAID'`-only partial index will not suffice. Analyze key access paths before introducing multiple partial indexes.

## 22. INCLUDE and Covering Indexes

PostgreSQL supports `INCLUDE` to store non-key **payload** columns in index leaf pages without making them part of the primary search key sort order.

Example:

```sql
CREATE INDEX idx_btree250_orders_paid_lookup_cover
ON btree250.orders(
    status,
    ordered_at DESC,
    order_id DESC
)
INCLUDE (customer_id, amount_cents);
```

Query:

```sql
SELECT
    order_id,
    customer_id,
    ordered_at,
    amount_cents
FROM btree250.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

All requested columns are present in this index. PostgreSQL **may** choose an `Index Only Scan` when conditions allow.

### 22.1. INCLUDE Does Not Make Payload Columns Search Keys

In the index above:

- `status`, `ordered_at`, `order_id` are **key columns**.
- `customer_id`, `amount_cents` are **INCLUDE columns**.

A condition:

```sql
WHERE customer_id = 42
```

cannot use an `INCLUDE`d `customer_id` as a leading B-tree search key the way it could if `customer_id` were a **key column**.

`INCLUDE` lets an index carry extra columns to satisfy projections or post-lookup filters in certain plans; it does not replace choosing proper key columns for `WHERE`/`ORDER BY`.

### 22.2. Index Only Scan Can Still Read the Heap

Under MVCC, PostgreSQL must verify row visibility against the active snapshot. `Index Only Scan` relies on the **visibility map** to skip heap reads for pages marked all-visible.

If heap pages are not yet all-visible (for example, after recent `UPDATE`s), the query may still perform **Heap Fetches** despite the node being named `Index Only Scan`.

Run:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, ordered_at, amount_cents
FROM btree250.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

and inspect `Heap Fetches` whenever an `Index Only Scan` appears.

### 22.3. INCLUDE Also Has a Cost

Payload columns enlarge the index, increase write overhead, and can disable or limit internal optimizations (such as B-tree deduplication on indexes with `INCLUDE`). Do not dump every `SELECT` column into `INCLUDE` indiscriminately.

### 22.4. UNIQUE and INCLUDE

In a unique index with `INCLUDE`, uniqueness is enforced solely on the **key columns**, not on the `INCLUDE` payload columns. This is useful when enforcing a unique key while carrying extra columns for reads.

## 23. Unique B-trees and NULL

`PRIMARY KEY` and `UNIQUE` constraints are normally backed by unique B-tree indexes.

Example from the `customers` table:

```sql
email text NOT NULL UNIQUE
```

PostgreSQL creates an index to prevent duplicate emails. The query:

```sql
SELECT customer_id
FROM btree250.customers
WHERE email = 'user00100@example.test';
```

can leverage that index for both data integrity and query performance.

### 23.1. NULL in Unique Indexes

Under standard PostgreSQL behavior, a regular unique index permits multiple `NULL` values because `NULL`s are not treated as equal under the default uniqueness rule.

Modern PostgreSQL versions offer the `NULLS NOT DISTINCT` option when `NULL`s should be treated as duplicates in a unique index or constraint:

```sql
CREATE TABLE btree250.unique_example (
    item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_code text,
    UNIQUE NULLS NOT DISTINCT (external_code)
);
```

With this option, inserting multiple rows with `external_code = NULL` triggers a uniqueness conflict.

**Note:** verify support on your server version. Unique indexes and `IS NULL` serve two distinct roles: enforcing data constraints and querying.

### 23.2. Operator Classes/Collations and Uniqueness

For text, what counts as “two equal strings” can depend on collation and data-type/expression choices. When enforcing case-insensitive uniqueness on emails or usernames, consider a unique expression index on normalized values or another suitable mechanism.

Never assume a `text_pattern_ops` index automatically enforces your application's case-sensitive or case-insensitive uniqueness rules.

## 24. B-tree Is Not Equivalent to GIN, GiST, or BRIN

| Index Method | Typically Best Suited For |
|---|---|
| **B-tree** | `=`, ordered ranges, `ORDER BY`, `LIMIT`, key equality/range lookups |
| Hash | Equality with supported operator class; no sorting or range support like B-tree |
| GIN | Multi-element values: arrays, JSONB, full-text, trigrams |
| GiST | Specialized types/operators such as spatial, ranges, trigrams, or custom extensions |
| SP-GiST | Specialized space-partitioned or non-balanced key structures |
| BRIN | Very large tables with physical block-range correlation, such as monotonically increasing timestamps in append-only logs |

Choose based on **operators and data distribution**. For instance:

```sql
WHERE jsonb_column @> '{"type":"paid"}'
```

points toward a GIN operator class rather than creating a B-tree on JSONB for containment predicates.

Likewise, `LIKE '%substr%'` typically aligns with trigram indexing rather than B-tree.

A B-tree can still make sense on a **scalar extraction expression** from JSONB if queries always compare that extracted value with equality/range and the expression is indexable—for example, indexing `(payload->>'customer_id')` with a consistent type and expression.

## 25. OR, AND, and Bitmap Index Scans

PostgreSQL can combine multiple indexes.

Suppose two indexes exist:

```sql
CREATE INDEX idx_btree250_orders_customer_only
ON btree250.orders(customer_id);

CREATE INDEX idx_btree250_orders_status_only
ON btree250.orders(status);
```

Query:

```sql
SELECT order_id, customer_id, status
FROM btree250.orders
WHERE customer_id = 42
   OR status = 'CANCELLED';
```

The planner can use bitmap operations:

```text
BitmapOr
  Bitmap Index Scan on customer_id
  Bitmap Index Scan on status
    |
Bitmap Heap Scan
```

With `AND` on two indexed predicates, the planner may consider `BitmapAnd`.

### 25.1. What Is a Bitmap Scan?

A `Bitmap Index Scan` collects candidate heap row locations from an index into a bitmap, and `Bitmap Heap Scan` reads the heap pages in physical order. This can reduce random I/O when many matching rows cluster across pages.

However, **`Bitmap Heap Scan` does not preserve B-tree sort order**. If the query has an `ORDER BY`, the planner may need an extra `Sort` node.

### 25.2. OR Does Not Force BitmapOr

If one branch of `OR` matches too many rows, `Seq Scan` can be cheaper. If another composite index applies, the planner may pick a non-bitmap plan.

Only `EXPLAIN` reveals the actual plan.

### 25.3. Don't Overuse OR Instead of IN

For multiple equality checks on the same column:

```sql
WHERE customer_id = 1
   OR customer_id = 2
   OR customer_id = 3
```

it is usually cleaner to write:

```sql
WHERE customer_id IN (1, 2, 3)
```

The planner can optimize both, yet `IN` expresses a set of values on the same key more clearly.

## 26. Composite Index vs. Multiple Single-Column Indexes

Example workload:

```sql
SELECT order_id, ordered_at
FROM btree250.orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY ordered_at DESC
LIMIT 10;
```

Two options:

**A — Multiple single-column indexes:**

```sql
CREATE INDEX ... ON orders(customer_id);
CREATE INDEX ... ON orders(status);
CREATE INDEX ... ON orders(ordered_at);
```

**B — One matching composite index:**

```sql
CREATE INDEX idx_btree250_customer_status_time
ON btree250.orders(
    customer_id,
    status,
    ordered_at DESC
);
```

The composite index can isolate the exact customer and status while supplying time ordering to grab the 10 most recent rows.

### 26.1. A Composite Index Does Not Replace Every Single-Column Index

If the application also runs a major query:

```sql
WHERE status = 'PAID'
ORDER BY ordered_at DESC
LIMIT 100
```

index `(customer_id, status, ordered_at)` is not the default optimal choice, because `customer_id` is unconstrained. You may need `(status, ordered_at DESC)`.

Similarly, if queries filter purely by:

```sql
WHERE ordered_at >= ...
```

an index on `(ordered_at)` may be needed.

### 26.2. Avoid Redundant Duplicate Indexes

If `(customer_id, status, ordered_at)` exists, a single-column `(customer_id)` index may **sometimes** be redundant for customer equality lookups. Still, do not delete it blindly: the narrower index can be faster for specific workloads; measure both query plans and write impact.

Manage indexes as part of system architecture rather than adding them ad hoc for slow queries and forgetting them.

## 27. Index-Only Scans and MVCC: Selecting Columns Isn't Enough

A query selecting only indexed columns may still choose an Index Scan, Seq Scan, or end up reading the heap.

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, status, ordered_at, order_id
FROM btree250.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 15;
```

If an index contains all needed columns, the planner **may** pick `Index Only Scan`. Two conditions matter:

1. All required columns/expressions can be served from the index.
2. Snapshot visibility checks can skip the heap on all-visible pages, or trigger `Heap Fetches` where needed.

### 27.1. How Does VACUUM Help?

`VACUUM` cleans up dead tuple versions and updates the visibility map. A read-heavy, rarely modified table achieves much cleaner index-only scans than a table undergoing constant `UPDATE`s.

Never run manual `VACUUM` in production just to force a plan without understanding workload, autovacuum behavior, privileges, and operational impact.

### 27.2. Index-Only Scan Does Not Mean “Never Touches the Table”

In `EXPLAIN ANALYZE`, `Heap Fetches` can be non-zero. The node name describes the **capability** to satisfy column data from the index, not a guarantee of zero heap reads on every execution.

## 28. Index Selectivity, Statistics, and the Planner

PostgreSQL relies on statistics to estimate how many rows match a `WHERE` clause.

Inspect collected statistics:

```sql
SELECT
    schemaname,
    tablename,
    attname,
    n_distinct,
    null_frac,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'btree250'
  AND tablename = 'orders'
  AND attname IN ('customer_id','status','ordered_at');
```

Meaning:

- `n_distinct`: estimated number of distinct values.
- `null_frac`: fraction of `NULL` values.
- `most_common_vals` and `most_common_freqs`: most frequent values and their frequencies when tracked.
- Histograms and correlation also shape how the planner estimates ranges and physical access costs.

### 28.1. Misestimates Lead to Suboptimal Plans

If data changes heavily or columns have strong correlation, the planner may misestimate row counts.

For example:

```sql
WHERE status='PAID'
  AND ordered_at >= ...
```

if `'PAID'` only appears in recent months while statistics assume column independence, combined selectivity estimates can be off. PostgreSQL provides **extended statistics** for correlated columns, such as multi-column dependencies and MCV lists.

### 28.2. Extended Statistics as a Complementary Tool

Lab example:

```sql
CREATE STATISTICS stats_btree250_status_customer
    (dependencies, mcv)
ON status, customer_id
FROM btree250.orders;

ANALYZE btree250.orders;
```

Creating extended statistics does not improve every query automatically; check data correlation and resulting plans.

### 28.3. Don't Force the Planner to Use an Index Prematurely

You can toggle planner flags like `enable_seqscan` in a lab session to compare plan costs, but never tweak global production flags as a permanent “query fix.”

The real root cause is often:

- Index does not match `WHERE`/`ORDER BY`.
- Low selectivity.
- Stale statistics.
- Column cast or function mismatching the index.
- Query selects many columns, making heap fetches expensive.
- Table too small for an index to pay off.

## 29. Reading EXPLAIN: Common Plan Nodes

| Node/Attribute | Meaning |
|---|---|
| `Seq Scan` | Sequential table scan |
| `Index Scan` | Traverses index and typically fetches heap rows |
| `Index Only Scan` | Can retrieve columns from index; visibility checks may read heap |
| `Bitmap Index Scan` | Builds a bitmap of matching rows from the index |
| `Bitmap Heap Scan` | Reads heap pages using the bitmap |
| `BitmapAnd` / `BitmapOr` | Combines bitmaps from multiple index scans |
| `Sort` | Sorts input rows |
| `Incremental Sort` | Exploits partial input ordering in supported plans |
| `Index Cond` | Condition pushed into the index lookup |
| `Filter` | Additional filter applied at the current node |
| `Recheck Cond` | Condition rechecked on heap/bitmap rows when needed |
| `Rows Removed by Filter` | Rows discarded by `Filter` at that node (shown with `ANALYZE`) |
| `Heap Fetches` | Heap accesses to check MVCC visibility during `Index Only Scan` |
| `actual time`, `rows`, `loops` | Measured execution metrics from `EXPLAIN ANALYZE` |
| `Buffers` | Shared/local/temp block hits, reads, dirtied, written |

### 29.1. EXPLAIN vs. EXPLAIN ANALYZE

```sql
EXPLAIN
SELECT *
FROM btree250.orders
WHERE customer_id = 42;
```

Builds only the estimated plan **without executing the SELECT** to measure runtime.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM btree250.orders
WHERE customer_id = 42;
```

**Executes the SELECT** and reports actual rows, timings, and buffer usage.

Caution: `EXPLAIN ANALYZE` on `UPDATE`/`DELETE`/`INSERT` **actually executes the DML**; use intentional transaction rollback or test strictly in a lab, never casually in production.

### 29.2. Estimated rows vs. actual rows

Illustrative example:

```text
Index Scan ...
  (cost=... rows=10 ...)
  (actual ... rows=30 loops=1)
```

The planner estimated 10 rows while 30 were actually returned. Large discrepancies on critical queries warrant investigating statistics, correlated predicates, parameterization, or index design.

### 29.3. Don't Judge Optimization Just by Seeing Index Scan

An index scan can be slower than a sequential scan if it touches too many heap pages. Judge performance by latency, I/O, buffers, memory, throughput, and concurrency under real workloads.

## 30. Hands-On Comparison of Condition Types

Run each `EXPLAIN` after creating the dataset and relevant indexes.

### 30.1. Equality

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM btree250.orders
WHERE customer_id = 42;
```

Observe whether the planner selects `Index Scan`, `Bitmap Heap Scan`, or `Seq Scan`, along with actual row counts.

### 30.2. Range

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, ordered_at
FROM btree250.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-03 00:00:00+00';
```

With an index on `ordered_at`, this is a clean range condition.

### 30.3. IN-list

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id
FROM btree250.orders
WHERE customer_id IN (42, 100, 999);
```

Observe how the `customer_id` index is used.

### 30.4. ORDER BY LIMIT

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, ordered_at
FROM btree250.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 10;
```

Check whether the matching index eliminates a full-table `Sort`.

### 30.5. Prefix LIKE

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, email
FROM btree250.customers
WHERE email LIKE 'user001%';
```

Compare before and after adding `text_pattern_ops` under an appropriate collation environment.

### 30.6. Substring LIKE

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, email
FROM btree250.customers
WHERE email LIKE '%001%';
```

Do not expect a standard B-tree to help much here. You can compare against a trigram index if your lab permits extensions.

### 30.7. Function on a Column

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, email
FROM btree250.customers
WHERE lower(email) LIKE 'user001%';
```

With a matching expression index on `lower(email) text_pattern_ops`, the planner gains an index option.

## 31. When an Index Exists Yet Goes Unused

One of the most common questions:

> “I just ran CREATE INDEX, why does EXPLAIN still show Seq Scan?”

Common reasons:

### 31.1. Table Is Too Small

On a 3–10 row table, scanning a single page sequentially is cheaper than reading an index and then the heap.

### 31.2. Query Returns Most of the Table

`status = 'NEW'` matches 70% of the lab rows. A low-selectivity index incurs too much random access.

### 31.3. Wrong Column Order in Composite Index

Having `(status, ordered_at)` when the query filters only on `ordered_at` is not always a good match.

### 31.4. Expression Mismatch

Indexing `email` when the query runs `lower(email)`, or indexing `ordered_at` when the query runs `ordered_at::date`.

### 31.5. LIKE Without a Fixed Prefix

`LIKE '%abc%'` does not translate simply into a contiguous B-tree key range.

### 31.6. Incompatible Collation/Opclass

A default locale-collated text index may not support prefix `LIKE` as expected; a pattern operator class or compatible collation is decisive.

### 31.7. Missing or Stale Statistics

The planner misestimates row counts. In the lab run `ANALYZE`; in production inspect autovacuum and statistics settings.

### 31.8. Query Needs Many Unindexed Columns

Index Scan has to touch the heap repeatedly. When many rows match, Seq Scan can win.

### 31.9. Partial Index Predicate Not Provable

The index predicate is `status = 'PAID'`, while a generic prepared plan with `status = $1` cannot prove the parameter is always `'PAID'`.

### 31.10. Another Index Is Better

PostgreSQL picks one plan across available indexes and strategies. Your newly created index might simply not be the lowest-cost option.

**How to investigate:** inspect `EXPLAIN (ANALYZE, BUFFERS)`, statistics, operator class, index definition, and matched row count; never force indexes blindly.

## 32. Cost of Maintaining B-trees During Writes

Indexes are not free.

On `INSERT`:

- PostgreSQL writes the new row into the heap.
- Every affected B-tree index must be updated with the new key.

On `UPDATE`:

- Depending on which columns changed and whether HOT update applies, indexes may require updates.
- Indexes on frequently modified columns add CPU, I/O, and WAL overhead.
- Large indexes increase page reads/writes and storage consumption.

On `DELETE`:

- The row version becomes dead under MVCC; index entry cleanup and space reclamation depend on `VACUUM` and PostgreSQL maintenance.
- Do not assume deleting a row immediately shrinks the index file size.

### 32.1. Index Bloat and Maintenance

On high-churn tables, indexes can become bloated. PostgreSQL relies on page reuse mechanisms, `VACUUM`, and `REINDEX` options when genuinely warranted.

Never run `REINDEX` across production without observation and a plan, as locking and resource impact depend on the method used.

### 32.2. CREATE INDEX CONCURRENTLY

On tables with live write traffic, `CREATE INDEX CONCURRENTLY` avoids blocking normal DML compared to a standard build, though:

- It requires multiple phases/scans and takes longer.
- It has restrictions (for example, it cannot run inside an ordinary transaction block).
- It can leave behind an invalid index if it fails, requiring documented cleanup.
- It does not remove the need to plan for disk space, locks, and deployment duration.

Operational reference example only:

```sql
CREATE INDEX CONCURRENTLY idx_btree250_orders_ref
ON btree250.orders(reference_code);
```

In a populated lab database, this syntax is valid when run outside an explicit transaction block. In production, review the deployment plan and permissions first.

## 33. Inspecting Existing Indexes

In `psql`:

```text
\d+ btree250.orders
\d+ btree250.customers
```

In SQL:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'btree250'
ORDER BY tablename, indexname;
```

Inspecting index size and usage:

```sql
SELECT
    indexrelname AS index_name,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'btree250'
ORDER BY relname, indexrelname;
```

### 33.1. Interpreting Index Usage Statistics

- `idx_scan`: number of index scans initiated on this index according to collected stats.
- `idx_tup_read`: number of index entries returned by scans on this index.
- `idx_tup_fetch`: number of live heap tuples fetched by relevant execution paths; do not assume a simple 1:1 correspondence with `idx_tup_read` across all scan types.

Statistics reset at various times and depend on uptime/monitoring windows. **`idx_scan = 0` is not enough to drop an index** if the full business cycle has not been observed or if the index backs a `UNIQUE`/`PK`/critical constraint.

### 33.2. Checking Index Validity

If a concurrent index build fails during deployment, verify whether the index is valid. Check `pg_index.indisvalid` and `pg_get_indexdef`, or use your administration tools. Never assume the planner can use an index just because its name appears in the catalog.

## 34. Practice Exercises with Solutions

These exercises use the `btree250` schema. When an exercise asks to create an index similar to an earlier one, avoid reusing the same index name; use a fresh lab/schema or inspect existing definitions first.

### Exercise 1. What Is the Default Index Method of CREATE INDEX?

```sql
CREATE INDEX idx_btree250_orders_customer_demo
ON btree250.orders(customer_id);
```

**Answer:** PostgreSQL uses **B-tree** when `USING ...` is omitted.

### Exercise 2. Write an Exact Lookup by order_id

```sql
SELECT *
FROM btree250.orders
WHERE order_id = 12345;
```

**Explanation:** the primary key already has a unique B-tree; equality lookup is the natural fit.

### Exercise 3. Filter Orders in April (UTC)

```sql
SELECT order_id, ordered_at
FROM btree250.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00'
  AND ordered_at < TIMESTAMPTZ '2026-05-01 00:00:00+00';
```

**Explanation:** half-open range, able to leverage the B-tree on `ordered_at`.

### Exercise 4. Why Is BETWEEN Unsuitable for Selecting a Day Using Two Midnights?

**Answer:** `BETWEEN` is inclusive on both ends. Using `BETWEEN` midnight of day 1 and midnight of day 2 erroneously includes the exact midnight timestamp of day 2. The half-open form `>= start AND < next_start` is cleaner.

### Exercise 5. Is IN (10, 20, 30) Equivalent to BETWEEN 10 AND 30?

**Answer:** no. `IN` selects three discrete values; `BETWEEN` selects every value in the interval.

### Exercise 6. Find All Incomplete Tasks

```sql
SELECT task_id, title
FROM btree250.tasks
WHERE completed_at IS NULL;
```

**Explanation:** use `IS NULL`, not `= NULL`; B-trees support `IS NULL`, though a tiny table will likely use `Seq Scan`.

### Exercise 7. Why Does status = 'NEW' Use Seq Scan Despite Having an Index?

**Answer:** in the fixture 70% of orders are `'NEW'`, making the index unselective; a sequential scan can be cheaper than many random heap fetches.

### Exercise 8. Write a Prefix LIKE Pattern That Can Be Optimized

```sql
SELECT email
FROM btree250.customers
WHERE email LIKE 'user001%';
```

**Answer:** the pattern has a fixed leading prefix; with a compatible collation/operator class, a pattern B-tree can support it.

### Exercise 9. Does LIKE '%001%' Use a B-tree Over a Clean Key Range?

**Answer:** normally no, because there is no fixed leading prefix. Consider `pg_trgm` if the workload requires substring searches.

### Exercise 10. What Must You Watch Out for When Using ILIKE for Prefixes?

**Answer:** standard text B-trees do not automatically handle case-insensitive searches. You can index `lower(email) text_pattern_ops` and query `lower(email) LIKE 'user001%'`, or use another suitable approach.

### Exercise 11. Which WHERE Clause Suits Index (status, ordered_at)?

```sql
WHERE status='PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-04-01 00:00+00'
```

**Explanation:** equality on the leading column, range on the second column.

### Exercise 12. Is Index (status, ordered_at) Definitely Useless When Filtering Only on ordered_at?

**Answer:** do not state that as an absolute. It is usually less favorable than an `ordered_at` index for that access path, yet the planner may still use alternative strategies or skip scan in supported cases.

### Exercise 13. Choose an Index for the Newest PAID Orders

```sql
CREATE INDEX idx_btree250_paid_recent_demo
ON btree250.orders(
    status,
    ordered_at DESC,
    order_id DESC
);
```

Query:

```sql
SELECT order_id, ordered_at
FROM btree250.orders
WHERE status='PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 10;
```

**Answer:** the index filters `status` by equality and provides timestamp/ID ordering inside the `'PAID'` slice.

### Exercise 14. Why Do DESC and NULLS Matter?

**Answer:** scanning a B-tree forward or backward reverses both key order and `NULL` placement; an index for `DESC NULLS LAST` does not always match a default `ASC NULLS LAST` index when NULLs are possible.

### Exercise 15. Keyset Pagination

First page:

```sql
SELECT order_id, ordered_at
FROM btree250.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Next page using the two values from the last row:

```sql
WHERE (ordered_at,order_id) < (:last_ordered_at,:last_order_id)
```

**Explanation:** the placeholders above represent application-side parameter syntax; in `psql`, substitute real literals or use a prepared statement. The matching index is `(ordered_at DESC, order_id DESC)`.

### Exercise 16. Can a B-tree Help MAX(ordered_at)?

**Answer:** yes, because an ordered index lets certain plans read just the first or last entry of the key range.

### Exercise 17. Given an Index on email, Will WHERE lower(email) = ... Automatically Use It?

**Answer:** not automatically. The query evaluates a different expression; an expression index on `lower(email)` may be required.

### Exercise 18. How Does INCLUDE Differ from a Key Column?

**Answer:** `INCLUDE` adds payload columns to return data from the index; it does not participate in search ordering or uniqueness checks of the key columns.

### Exercise 19. Why Can Index Only Scan Still Have Heap Fetches?

**Answer:** PostgreSQL must verify MVCC visibility; heap pages not marked all-visible must still be read.

### Exercise 20. Will a Partial Index for PAID Work for a Generic Plan with status = $1?

**Answer:** not guaranteed. A generic plan must remain valid for any parameter value; it cannot assume `status = 'PAID'` always holds.

### Exercise 21. Write a Query Combining Equality and Range Conditions

```sql
SELECT *
FROM btree250.orders
WHERE customer_id = 42
  AND amount_cents >= 150000;
```

**Suggested index:** `(customer_id, amount_cents)`. The planner still chooses based on cost.

### Exercise 22. Why Can customer_id::text = '42' Be Disadvantageous?

**Answer:** casting the column alters the searched expression so it no longer matches the integer index. Prefer comparing as an integer or creating a dedicated expression index if genuinely required.

### Exercise 23. Can SELECT ... WHERE customer_id = 42 OR status = 'PAID' Use One or Two Indexes?

**Answer:** the planner may consider `BitmapOr` combining two indexes, or choose another plan. Check `EXPLAIN` to see the actual decision.

### Exercise 24. Diagnosing a Seq Scan

**Prompt:** a query still runs `Seq Scan` after `CREATE INDEX`.

**Solution:** check whether the table is too small or the filter too broad, whether the index matches expressions/opclass/collation, whether column order fits, whether statistics are current, whether selecting many columns makes heap access costly, and whether another index/plan is cheaper.

### Exercise 25. Reading Actual Execution Time and Buffers

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM btree250.orders
WHERE customer_id = 42;
```

**Answer:** inspect `actual rows`, `actual time`, `Buffers`, and `Index Cond`/`Filter`. Never judge index effectiveness solely by the node name.

### Exercise 26. Should You Run REINDEX Daily to Keep a B-tree “Balanced”?

**Answer:** no. PostgreSQL keeps B-trees balanced automatically; `VACUUM` maintenance and occasional `REINDEX` should be driven by observed bloat, workload behavior, and operational procedures, not scheduled blindly.

### Exercise 27. Finding Rarely Used Indexes

```sql
SELECT relname, indexrelname, idx_scan
FROM pg_stat_user_indexes
WHERE schemaname='btree250'
ORDER BY idx_scan;
```

**Answer:** low scan counts are a signal to investigate, **not sufficient proof** to drop a `UNIQUE`/`PK` index or an index serving rare but vital workloads.

### Exercise 28. Comparing B-tree vs. Trigram

**Prompt:** users search for emails containing `'001'` anywhere in the string.

**Answer:** B-tree lacks a useful key range without a fixed leading prefix. `pg_trgm` with GIN/GiST can fit better; benchmark and verify extension permissions.

## 35. Mistakes to Avoid

### Mistake 1: “If an index exists, the query will definitely use it”

False. The planner compares costs across Index, Bitmap, Seq Scan, and other plans.

### Mistake 2: “B-trees only support equality”

False. They also support ordered range conditions and `ORDER BY`/`LIMIT` operations.

### Mistake 3: “All LIKE predicates use a B-tree”

False. Patterns lacking a fixed leading prefix normally cannot leverage a standard B-tree range.

### Mistake 4: “Prefix LIKE always uses the default text index in every locale”

False. Collation and pattern operator classes play a decisive role.

### Mistake 5: “Prefix ILIKE works just like LIKE”

Incorrect. Case folding often requires an expression index or a different approach.

### Mistake 6: “Given index(a, b), WHERE b = ? is always fast”

Not guaranteed. Key ordering shapes the scan range; skip scan and planner choices depend on data and PostgreSQL version.

### Mistake 7: “The most selective column must always come first in a composite index”

Overly simplistic. Equality, range, `ORDER BY`, `LIMIT`, and other query shapes determine optimal column order.

### Mistake 8: “IN (1, 10, 100) is equivalent to BETWEEN 1 AND 100”

False. `BETWEEN` includes all values in the range.

### Mistake 9: “IS NULL can be written as = NULL”

Incorrect under SQL three-valued logic. Always use `IS NULL`.

### Mistake 10: “A B-tree on ordered_at always works well for ordered_at::date”

Not automatically. Functions/casts change the expression, and `timestamptz::date` is timezone-dependent.

### Mistake 11: “With an index, ORDER BY LIMIT never runs Sort”

Not guaranteed. Column order, `ASC`/`DESC`, `NULLS`, predicates, and cost estimates all matter.

### Mistake 12: “Index-only scan means zero heap reads”

Not necessarily; inspect `Heap Fetches` and the visibility map.

### Mistake 13: “INCLUDE(customer_id) is equivalent to key(customer_id)”

False. `INCLUDE` columns are not search or sort keys.

### Mistake 14: “Partial indexes work for every bind parameter”

False. The planner must prove `WHERE` implies the predicate; generic prepared plans often cannot.

### Mistake 15: “<> is a good range condition just like =”

Usually false. Negation often matches too many rows and does not form a single contiguous range.

### Mistake 16: “If a new index isn't used, PostgreSQL has a bug”

It may be an expression mismatch, missing stats, small table, or `Seq Scan` simply being cheaper.

### Mistake 17: “More indexes always mean faster performance”

Indexes add overhead to `INSERT`/`UPDATE`/`DELETE`, WAL, storage, `VACUUM`, and migrations.

### Mistake 18: “EXPLAIN ANALYZE is safe on all DML”

False. On `INSERT`/`UPDATE`/`DELETE`, `EXPLAIN ANALYZE` executes the statement; control transactions and data carefully.

### Mistake 19: “idx_scan = 0 means drop the index immediately”

False. The index might enforce a constraint, serve rare jobs, or reflect recently reset statistics.

### Mistake 20: “Use B-tree indexes for every kind of search”

False. JSONB containment, full-text search, substrings, spatial data, and massive physically ordered datasets may require GIN/GiST/BRIN or different strategies.

## 36. Quick Reference: Conditions and Suggested Indexes

| Need | Illustrative SQL | When B-tree Fits |
|---|---|---|
| Exact key lookup | `id = ?` | B-tree on `id` |
| Numeric range | `amount >= ? AND amount < ?` | B-tree on `amount` |
| Date/time range | `time >= t1 AND time < t2` | B-tree on `time` |
| Multiple discrete values | `id IN (?, ?, ?)` | B-tree on `id`; reasonable selectivity |
| NULL lookup | `col IS NULL` | Index on `col` with sufficient selectivity |
| Non-NULL lookup | `col IS NOT NULL` | Possible; cost depends on row fraction |
| String prefix | `email LIKE 'abc%'` | Compatible collation or pattern opclass |
| Case-insensitive prefix | `lower(email) LIKE 'abc%'` | Expression index `lower(email)` + pattern ops |
| Substring match | `email LIKE '%abc%'` | Usually not B-tree; consider trigram |
| Equality + range filter | `a = ? AND b >= ?` | Composite index `(a, b)` |
| Three-column filter | `a = ? AND b = ? AND c >= ?` | Composite index `(a, b, c)` |
| Latest per status | `WHERE status = ? ORDER BY time DESC LIMIT 20` | Composite index `(status, time DESC)` |
| Latest across table | `ORDER BY time DESC LIMIT 20` | Index leading with `time` |
| Deep pagination | `(time, id) < (?, ?) ORDER BY time DESC, id DESC` | Composite index `(time DESC, id DESC)` |
| Fetching MIN/MAX | `MAX(time)` | Index with matching order |
| Active subset only | `WHERE active = true` | Partial index with matching predicate |
| Query needs a few extra columns | `SELECT keys, payload ...` | Key columns + `INCLUDE`; favorable visibility |
| Expression lookup | `lower(email) = ?` | Expression B-tree matching query |
| OR across two columns | `a = ? OR b = ?` | Possible `BitmapOr` combining indexes |
| DISTINCT/GROUP BY | `GROUP BY a` | Can benefit from index order; cost-dependent |

## 37. Checklist Before Creating a B-tree Index

1. Are critical queries doing equality, range, prefix `LIKE`, or `ORDER BY`?
2. Do the data type, operator class, and collation support the operators used?
3. Does `WHERE` filter on the **raw column** or on an expression/cast?
4. What percentage of rows satisfy the predicate?
5. Does the query use `ORDER BY ... LIMIT`?
6. In a composite index, how are equality and range columns ordered?
7. Do other queries rely on a leading prefix of that composite index?
8. Are mixed `DESC` directions or specific `NULLS LAST`/`FIRST` options needed?
9. Is there a stable partial predicate that queries provably imply?
10. Do you need an expression index or a pattern operator class?
11. Could `INCLUDE` avoid heap accesses, and is the visibility map favorable?
12. Does an existing index already overlap or duplicate it?
13. How frequent are `INSERT`/`UPDATE`/`DELETE` operations?
14. How much will index size, WAL volume, and `VACUUM` work grow?
15. Have you inspected `EXPLAIN (ANALYZE, BUFFERS)` on representative data?
16. Is `CREATE INDEX CONCURRENTLY` required to avoid blocking writes?
17. For unique/partial indexes, have business rules and `NULL` semantics been verified?
18. Is there a plan to measure effectiveness and remove redundant indexes **after verification**?

## 38. Official PostgreSQL Documentation

Consult the documentation matching your PostgreSQL major version:

- [Index Types — PostgreSQL](https://www.postgresql.org/docs/current/indexes-types.html): index methods and supported operators.
- [Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html): column ordering, equality/range, and multi-column behavior.
- [Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html): `ASC`/`DESC`, `NULLS`, and `LIMIT`.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): expression indexes such as `lower(email)`.
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html): predicates and partial index applicability.
- [Index-Only Scans and Covering Indexes](https://www.postgresql.org/docs/current/indexes-index-only-scans.html): `INCLUDE` and the visibility map.
- [Operator Classes and Operator Families](https://www.postgresql.org/docs/current/indexes-opclass.html): `text_pattern_ops`, operators, and collations.
- [Examining Index Usage](https://www.postgresql.org/docs/current/indexes-examine.html): analyzing index usage and plan selection.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): interpreting `EXPLAIN` output and plan nodes.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): B-tree syntax, partial predicates, `INCLUDE`, and `CONCURRENTLY`.

Certain planner optimizations and opclass/collation capabilities change across versions. Inspect your live server:

```sql
SHOW server_version;
SHOW lc_collate;
```

When evaluating individual text columns in a table, check the collation on the **column or index definition** rather than relying solely on database-level `lc_collate`.

## 39. Summary: From SQL Conditions to B-tree Key Ranges

B-trees are powerful indexes for data with a **comparable total order**:

```text
WHERE id = ?
       |
       +-- Exact key lookup

WHERE time >= t1 AND time < t2
       |
       +-- Contiguous key range scan

WHERE status = ? AND time >= ?
       |
       +-- Index(status, time):
           pin prefix then scan range

ORDER BY time DESC LIMIT 20
       |
       +-- Read in index order,
           can stop early

WHERE email LIKE 'abc%'
       |
       +-- Can use pattern B-tree
           with compatible collation/opclass

WHERE email LIKE '%abc%'
       |
       +-- No fixed leading prefix;
           consider trigram or another strategy
```

Core takeaways:

1. **B-trees support ordered comparisons**, notably `=`, `<`, `<=`, `>`, `>=`, and equivalent SQL forms like `BETWEEN`, `IN`, and `IS NULL`.
2. **`Index Cond` differs from `Filter`.** A predicate appearing in `WHERE` does not automatically narrow the index scan range.
3. **Composite indexes depend on column order.** Leading equality columns followed by a range column is typically effective, though planner strategies mean missing a leading column is not an absolute ban.
4. **B-trees help `ORDER BY`/`LIMIT`**, sometimes even more than `WHERE`, especially for top-N queries.
5. **Strings require understanding collations and operator classes.** Prefix `LIKE` can use a pattern B-tree; substring `LIKE` and general `ILIKE` do not behave identically by default.
6. **Functions/casts on columns alter the searched expression.** You may need range rewrites on the raw column or an expression index.
7. **`INCLUDE` and index-only scans have limits.** Payload columns are not search keys; MVCC visibility can still require heap fetches.
8. **Partial indexes apply only when the predicate is provably implied**; generic prepared plans and dynamic conditions like `now()` are common pitfalls.
9. **The planner decides by cost.** Valid indexes can still lose to `Seq Scan` when filters are broad or tables are small.
10. **Every index has write and operational costs.** Add indexes only after understanding the workload and verifying with `EXPLAIN`, never on guesswork.

**One sentence to remember:** A B-tree performs best when query predicates and ordering translate into **a tightly bounded, ordered key range**; whether PostgreSQL actually chooses that index still depends on data, statistics, and cost.
