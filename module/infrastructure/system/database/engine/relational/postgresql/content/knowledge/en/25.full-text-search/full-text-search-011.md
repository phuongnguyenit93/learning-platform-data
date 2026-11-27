# Combining Business Rules with Search Results in PostgreSQL

## 1. Finding Text Does Not Mean Permission to Display Results

Suppose a user searches for **PostgreSQL** on an educational marketplace. The database has many products containing that keyword, yet not every matching row should appear:

- Products belonging to **another tenant**.
- Products in draft status or under moderation review.
- Products that have been **soft-deleted**.
- Unverified sellers or suspended seller accounts.
- Products whose release time has not arrived or that have expired.
- Out-of-stock products or products unavailable in the buyer's country.
- Prices outside the user's selected range.
- Products outside the requested category or missing required *tags*.

A proper search endpoint does not merely return rows matching a keyword—it returns the **intersection of the viewable set, the business-eligible set, and the search-matched set**, and only then ranks and paginates them.

```text
All products
       |
       v
[Access scope: tenant, permissions, RLS]
       |
       v
[Visibility rules: published, deleted, seller]
       |
       v
[Commercial rules: time window, stock, price, region]
       |
       v
[Search predicates: FTS / LIKE / ILIKE / trigram]
       |
       v
[Relevance score + ranking rules]
       |
       v
[Stable ORDER BY + LIMIT / cursor]
       |
       v
Results the user is actually allowed to see
```

This diagram illustrates the **intended semantics**, not a claim that PostgreSQL executes predicates strictly in that order. The planner may reorder filters and pick indexes or joins as long as results preserve these semantics and security constraints.

> **Core rule:** mandatory rules covering tenant scope, authorization, status, and validity window must apply to the **entire candidate set** before determining the “top 20 best results”. Never grab the top 20 ranked rows across the whole table and filter business rules afterward.

## 2. Lesson Objectives

After completing this lesson, you will be able to:

1. Distinguish **search predicates**, **business eligibility**, **authorization**, and **presentation filters**.
2. Combine text search with tenant, seller, status, soft delete, validity window, price, region, and inventory rules.
3. Use `AND` / `OR` with proper parentheses to prevent leaking ineligible or unauthorized rows.
4. Use `JOIN`, `EXISTS`, and `NOT EXISTS` to handle one-to-many relationships without multiplying result rows.
5. Write parameterized SQL queries using PostgreSQL Full Text Search (FTS) and `websearch_to_tsquery`.
6. Combine `ILIKE`/`pg_trgm` with FTS using sound semantics.
7. Distinguish **top-N then filter** from **filter then top-N**.
8. Apply `ts_rank`/`ts_rank_cd`, business signals, deterministic tie-breakers, and pagination.
9. Compute total hit counts and category facets over the exact filtered result set.
10. Choose appropriate B-tree, GIN FTS, GIN trigram, composite, and partial indexes.
11. Read `EXPLAIN (ANALYZE, BUFFERS)` to see where each predicate is applied.
12. Understand the impact of statistics, data skew, and custom vs. generic prepared plans.
13. Maintain tenant isolation and access control when building dynamic queries.
14. Design API/JDBC layers with bind parameters, result limits, and cost controls.
15. Know when price and inventory must be re-verified inside the checkout transaction.
16. Benchmark and evaluate search changes with real metrics rather than just counting SQL lines.

## 3. Four Filter Layers That Should Never Be Mixed Up

A search query typically spans four conceptual layers (plus ranking/pagination).

| Layer | Examples | Nature |
| --- | --- | --- |
| Authorization | `tenant_id = :tenant`, ACL, RLS | **Mandatory**, cannot be bypassed by user options |
| Business eligibility | `status = 'PUBLISHED'`, valid seller, not soft-deleted | Rules governing whether a product may be listed |
| User-selected filters | Category, price range, region, tags, rating | Depends on filters chosen by the user |
| Text matching | FTS, `ILIKE`, trigram, regex | Determines which content matches the search query |
| Ranking/pagination | Relevance, newest, `LIMIT 20` | Orders and slices only the valid result set |

In set terms, every returned item must belong to:

```text
VisibleProducts
  ∩ EligibleProducts
  ∩ UserFilters
  ∩ TextMatches
```

When taking top N, you must take the **top N of this intersection**.

### 3.1. Conditions That Vary Per Account

- A product may be sold in Vietnam while unavailable in other countries.
- Buyer A may have access to internal listings that Buyer B cannot view.
- A seller's items may only become visible once verification passes.
- A promotion or catalog may apply exclusively to members of a specific group.

Consequently, search results depend not only on the keyword, but also on the **authenticated user context**.

### 3.2. Search Predicates Do Not Replace Access Control

Never treat “users do not know the secret product name” as a security control. If a search API omits tenant filtering, matching keywords can expose product names, counts, rankings, or attributes belonging to another tenant.

### 3.3. Display Eligibility Is Not Checkout Guarantee

`stock_qty > 0` at search time is purely an **informational snapshot**. Ordering must still re-verify inventory, price, permissions, sale window, and business constraints inside the checkout transaction to prevent race conditions.

## 4. Creating a Multi-Tenant Practice Schema

All examples run inside a **lab database**—never run lab DDL or seed data in production.

This lesson uses the `search_rules_lab` schema containing:

- `sellers`: sellers, tenants, verification status, suspension timestamps.
- `products`: products, search text, commercial status.
- `product_tags`: many-to-one tags for practicing `EXISTS`.

### 4.1. Sellers Table

```sql
CREATE SCHEMA IF NOT EXISTS search_rules_lab;

CREATE TABLE search_rules_lab.sellers (
    seller_id integer PRIMARY KEY,
    tenant_id integer NOT NULL,
    is_verified boolean NOT NULL DEFAULT false,
    suspended_at timestamptz,
    UNIQUE (tenant_id, seller_id)
);
```

`UNIQUE (tenant_id, seller_id)` supports a composite foreign key from `products`. Even though `seller_id` is already unique by itself, this composite key enforces **that seller and product share the same tenant** at the database layer.

### 4.2. Products Table and Stored tsvector

```sql
CREATE TABLE search_rules_lab.products (
    product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    seller_id integer NOT NULL,
    category_id integer NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    status text NOT NULL
        CHECK (status IN (
            'DRAFT',
            'PUBLISHED',
            'HIDDEN',
            'BLOCKED'
        )),
    deleted_at timestamptz,
    published_at timestamptz,
    available_until timestamptz,
    stock_qty integer NOT NULL
        CHECK (stock_qty >= 0),
    price numeric(12,2) NOT NULL
        CHECK (price >= 0),
    country_code text NOT NULL,
    rating numeric(3,2) NOT NULL
        CHECK (rating >= 0 AND rating <= 5),
    created_at timestamptz NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(
            to_tsvector('simple', coalesce(name, '')),
            'A'
        )
        ||
        setweight(
            to_tsvector('simple', coalesce(description, '')),
            'B'
        )
    ) STORED,
    FOREIGN KEY (tenant_id, seller_id)
        REFERENCES search_rules_lab.sellers
            (tenant_id, seller_id)
);
```

`search_vector` is `GENERATED ALWAYS AS ... STORED`, so PostgreSQL computes and stores the `tsvector` whenever `name` or `description` changes.

- Weight `A` prioritizes keywords in the product name.
- Weight `B` applies to the description.
- `simple` is a basic text-search configuration and **does not perform stemming or semantic Vietnamese word segmentation**.
- The text search configuration is specified **explicitly** so queries and indexes stay consistent.

`tsvector` adds storage overhead and write cost on text updates; it does not replace the original text columns.

### 4.3. Tags Table

```sql
CREATE TABLE search_rules_lab.product_tags (
    product_id bigint NOT NULL
        REFERENCES search_rules_lab.products(product_id),
    tag text NOT NULL,
    PRIMARY KEY (product_id, tag)
);
```

A product can have multiple tags, while `(product_id, tag)` pairs are unique.

### 4.4. Seeding 400 Sellers Across 4 Tenants

```sql
INSERT INTO search_rules_lab.sellers (
    seller_id, tenant_id, is_verified, suspended_at
)
SELECT
    s,
    1 + (s % 4),
    s % 11 <> 0,
    CASE
        WHEN s % 29 = 0
            THEN timestamptz '2026-03-01 00:00:00+00'
        ELSE NULL
    END
FROM generate_series(1, 400) AS v(s);
```

In the lab, some sellers are unverified or suspended. They own products, yet those products are **ineligible to appear** in public search results.

### 4.5. Seeding 80,000 Products

```sql
INSERT INTO search_rules_lab.products (
    tenant_id,
    seller_id,
    category_id,
    name,
    description,
    status,
    deleted_at,
    published_at,
    available_until,
    stock_qty,
    price,
    country_code,
    rating,
    created_at
)
SELECT
    1 + (v.seller_id % 4),
    v.seller_id,
    1 + (v.g % 8),
    CASE
        WHEN v.g % 13 = 0
            THEN 'PostgreSQL Tuning Handbook ' || v.g
        WHEN v.g % 11 = 0
            THEN 'Java Data Guide ' || v.g
        WHEN v.g % 7 = 0
            THEN 'SQL Index Workshop ' || v.g
        ELSE
            'Learning Database ' || v.g
    END,
    CASE
        WHEN v.g % 17 = 0
            THEN 'PostgreSQL search planner and performance'
        WHEN v.g % 19 = 0
            THEN 'Index design, ranking and query planning'
        ELSE
            'Database foundations and practical exercises'
    END,
    CASE
        WHEN v.g % 23 = 0 THEN 'BLOCKED'
        WHEN v.g % 9  = 0 THEN 'HIDDEN'
        WHEN v.g % 5  = 0 THEN 'DRAFT'
        ELSE 'PUBLISHED'
    END,
    CASE
        WHEN v.g % 31 = 0
            THEN timestamptz '2026-05-01 00:00:00+00'
        ELSE NULL
    END,
    CASE
        WHEN v.g % 41 = 0
            THEN timestamptz '2027-01-01 00:00:00+00'
        ELSE timestamptz '2026-01-01 00:00:00+00'
    END,
    CASE
        WHEN v.g % 43 = 0
            THEN timestamptz '2026-06-01 00:00:00+00'
        ELSE NULL
    END,
    v.g % 37,
    (v.g % 10000)::numeric / 10 + 1,
    CASE
        WHEN v.g % 3 = 0 THEN 'VN'
        ELSE 'US'
    END,
    (v.g % 51)::numeric / 10,
    timestamptz '2026-01-01 00:00:00+00'
        + (v.g % 200) * interval '1 hour'
FROM (
    SELECT
        g,
        ((g - 1) % 400) + 1 AS seller_id
    FROM generate_series(1, 80000) AS s(g)
) AS v;
```

Each tenant owns roughly **20,000** products. The dataset intentionally mixes:

- Eligible and ineligible listings.
- Verified, unverified, and suspended sellers.
- Unreleased and expired items.
- Out-of-stock items (`stock_qty = 0`).
- Two regions: `VN` and `US`.
- Keywords split across `name` and `description`.
- Varying prices, ratings, and categories.

Notice one subtlety: because `tenant_id` and `category_id` are both derived from `g`, **the two columns are correlated**. Do not assume every tenant contains an even spread across all eight categories. This also provides a realistic case for studying selectivity and extended statistics.

### 4.6. Seeding Tags

```sql
INSERT INTO search_rules_lab.product_tags (
    product_id, tag
)
SELECT
    product_id,
    CASE
        WHEN product_id % 3 = 0 THEN 'premium'
        ELSE 'general'
    END
FROM search_rules_lab.products;

INSERT INTO search_rules_lab.product_tags (
    product_id, tag
)
SELECT product_id, 'discount'
FROM search_rules_lab.products
WHERE product_id % 17 = 0;
```

Some products carry both `premium`/`general` and `discount`.

### 4.7. Creating Baseline Indexes

```sql
CREATE INDEX products_search_gin_idx
ON search_rules_lab.products
USING gin (search_vector);

CREATE INDEX products_tenant_status_idx
ON search_rules_lab.products (
    tenant_id, status, category_id, price
);

CREATE INDEX products_seller_idx
ON search_rules_lab.products (
    tenant_id, seller_id
);

ANALYZE search_rules_lab.products;
ANALYZE search_rules_lab.sellers;
ANALYZE search_rules_lab.product_tags;
```

These indexes support comparative lab experiments; they **do not guarantee** every query uses an index. In production, avoid creating overlapping indexes without measuring workload benefit.

### 4.8. Inspecting the Generated Data

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS n
FROM search_rules_lab.products
GROUP BY tenant_id, status
ORDER BY tenant_id, status;

SELECT
    COUNT(*) AS all_products,
    COUNT(*) FILTER (
        WHERE stock_qty = 0
    ) AS out_of_stock,
    COUNT(*) FILTER (
        WHERE deleted_at IS NOT NULL
    ) AS soft_deleted,
    COUNT(*) FILTER (
        WHERE available_until IS NOT NULL
    ) AS with_end_date
FROM search_rules_lab.products;
```

## 5. Basic Text Search: Candidates Are Not Business Results

First, inspect text matching alone:

```sql
SELECT
    product_id,
    tenant_id,
    name,
    ts_rank_cd(
        search_vector,
        websearch_to_tsquery('simple', 'postgresql')
    ) AS relevance
FROM search_rules_lab.products
WHERE search_vector @@
      websearch_to_tsquery('simple', 'postgresql')
ORDER BY relevance DESC, product_id DESC
LIMIT 20;
```

Explanation:

- `websearch_to_tsquery` converts plain search input into a `tsquery` using supported web-style syntax.
- `@@` checks whether `tsvector` matches `tsquery`.
- `ts_rank_cd` scores relevance using cover density and lexical weights.
- `ORDER BY relevance DESC` sorts results by score.
- `product_id DESC` acts as a deterministic tie-breaker when scores match.

**Problem:** this query omits tenant, status, deletion, seller, stock, time window, price, and region rules. It illustrates FTS syntax only. **Never ship this query as a public endpoint**.

### 5.1. FTS Matches Can Include Restricted Rows

A draft listing with `PostgreSQL` in its title still matches `@@`. The search engine has no inherent notion of which business states are public unless explicitly filtered.

### 5.2. Search Ranking Never Overrides Access Control

A row with an extremely high relevance score must still be excluded if it belongs to another tenant or is `BLOCKED`.

### 5.3. Filters Are Not Post-Search UI Decoration

Correct results must be defined by **all predicates combined** before `ORDER BY ... LIMIT`, not patched with superficial UI filtering afterward.

## 6. Defining the Eligible Product Set

An illustrative business rule:

A product is publicly visible to a buyer when:

1. It belongs to the authenticated tenant.
2. `status = 'PUBLISHED'`.
3. `deleted_at IS NULL`.
4. `published_at <= as_of`.
5. `available_until IS NULL OR available_until > as_of`.
6. `stock_qty > 0`.
7. Its seller has `is_verified = true`.
8. Its seller is not suspended.
9. `country_code` matches the buyer's allowed region.

Use a fixed timestamp in lab examples for repeatability:

```sql
WITH context AS (
    SELECT
        2::integer AS tenant_id,
        'VN'::text AS country_code,
        timestamptz '2026-11-14 00:00:00+00'
            AS as_of
)
SELECT
    p.product_id,
    p.name,
    p.price,
    p.stock_qty
FROM search_rules_lab.products AS p
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
CROSS JOIN context AS c
WHERE p.tenant_id = c.tenant_id
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.published_at <= c.as_of
  AND (
      p.available_until IS NULL
      OR p.available_until > c.as_of
  )
  AND p.stock_qty > 0
  AND s.is_verified = true
  AND s.suspended_at IS NULL
  AND p.country_code = c.country_code
ORDER BY p.product_id DESC
LIMIT 20;
```

This is the eligibility filter **without a keyword**. Next we combine it with text matching.

### 6.1. Why Include tenant_id in the Join Condition?

```sql
ON s.tenant_id = p.tenant_id
AND s.seller_id = p.seller_id
```

Beyond matching the lab's composite foreign key, this makes the tenant relationship explicit in the query. In multi-tenant systems where schemas allow overlapping IDs across tenants, joining solely on `seller_id` can cross tenant boundaries.

### 6.2. Soft Delete `IS NULL` Check

```sql
AND p.deleted_at IS NULL
```

Never write:

```sql
AND p.deleted_at = NULL
```

because comparing with `NULL` using `=` evaluates to `UNKNOWN`, not `TRUE`.

### 6.3. Half-Open End-Time Condition

```sql
p.available_until IS NULL OR p.available_until > as_of
```

means that once the clock reaches `available_until`, the listing has **expired**.

Business rules must specify this boundary explicitly. Some systems treat the end timestamp as inclusive; changing `>` to `>=` alters semantics and must never be done casually.

### 6.4. Inventory vs. Purchase Guarantee

`stock_qty > 0` represents a display-eligibility snapshot. By checkout time, inventory may have changed. Never treat search results as the sole authority for fulfilling an order.

## 7. Combining Eligibility and Search in One Query

Now add `@@` and ranking to the full query:

```sql
WITH context AS (
    SELECT
        2::integer AS tenant_id,
        'VN'::text AS country_code,
        timestamptz '2026-11-14 00:00:00+00'
            AS as_of,
        websearch_to_tsquery(
            'simple', 'PostgreSQL'
        ) AS tsq
)
SELECT
    p.product_id,
    p.name,
    p.price,
    p.rating,
    p.created_at,
    ts_rank_cd(p.search_vector, c.tsq) AS relevance
FROM search_rules_lab.products AS p
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
CROSS JOIN context AS c
WHERE p.tenant_id = c.tenant_id
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.published_at <= c.as_of
  AND (
      p.available_until IS NULL
      OR p.available_until > c.as_of
  )
  AND p.stock_qty > 0
  AND p.country_code = c.country_code
  AND s.is_verified
  AND s.suspended_at IS NULL
  AND p.search_vector @@ c.tsq
ORDER BY
    relevance DESC,
    p.created_at DESC,
    p.product_id DESC
LIMIT 20;
```

This is a **consistent predicate query**: no row can appear merely by matching a keyword if it fails business eligibility.

### 7.1. The context CTE Unifies Parameters

`context` holds the request-scoped values:

- Tenant.
- Region.
- Reference timestamp (`as_of`).
- Parsed `tsquery`.

This keeps semantics clear and avoids repeating `websearch_to_tsquery` across the query.

### 7.2. Do Not Assume a CTE Always Runs First Physically

Since PostgreSQL 12, non-materialized CTEs may be inlined depending on query structure and optimizer decisions. What matters is the **overall logical semantics**, not assuming writing a CTE first forces execution order.

### 7.3. Do Not Expect the Same Scan Path for Every Keyword

The planner can choose a GIN search index, a business B-tree index, a bitmap combination, or a Seq Scan depending on selectivity. Evaluate performance via `EXPLAIN`, not by counting `WHERE` clauses.

## 8. Fully Parameterizing the Query

In applications, never accept a trusted tenant ID directly from client input or interpolate raw search strings into SQL.

SQL-level `PREPARE` example:

```sql
PREPARE search_products(
    integer,
    text,
    text,
    timestamptz,
    numeric,
    numeric
) AS
WITH q AS (
    SELECT websearch_to_tsquery('simple', $2) AS tsq
)
SELECT
    p.product_id,
    p.name,
    p.price,
    p.rating,
    ts_rank_cd(p.search_vector, q.tsq) AS relevance
FROM search_rules_lab.products AS p
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
CROSS JOIN q
WHERE p.tenant_id = $1
  AND p.country_code = $3
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.published_at <= $4
  AND (
      p.available_until IS NULL
      OR p.available_until > $4
  )
  AND p.stock_qty > 0
  AND s.is_verified
  AND s.suspended_at IS NULL
  AND p.price >= $5
  AND p.price <= $6
  AND p.search_vector @@ q.tsq
ORDER BY
    relevance DESC,
    p.product_id DESC
LIMIT 20;
```

Execution:

```sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE search_products(
    2,
    'PostgreSQL',
    'VN',
    timestamptz '2026-11-14 00:00:00+00',
    10.00,
    500.00
);

DEALLOCATE search_products;
```

### 8.1. Derive Tenant from Authenticated Context

`$1` must come from the server's **verified authorization context**, never trusting an arbitrary `tenant_id` field supplied in an HTTP request body or query string.

### 8.2. Price and Parameter Types

`numeric` represents prices in the lab. In multi-currency systems, enforce `currency_code` and consistent conversion/comparison rules—never compare VND and USD amounts on the same numeric scale.

### 8.3. Server-Controlled Timestamps

In real APIs, `as_of` is usually supplied by the server rather than letting callers pass arbitrary future dates to preview unreleased items unless explicitly permitted.

### 8.4. PREPARE Is Session-Scoped

`PREPARE`/`EXECUTE` belongs to a PostgreSQL session. In Java/JDBC, drivers manage prepared statements separately from SQL-level `PREPARE`; parameterization alone does not guarantee a generic plan is always chosen.

## 9. AND/OR Precedence: A Missing Pair of Parentheses Leaks Rows

This is a critical bug class.

### 9.1. Wrong: OR Breaks Tenant Scope

```sql
-- WRONG: the branch after OR is not bounded by tenant/status.
SELECT p.product_id, p.name, p.tenant_id
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.name ILIKE '%PostgreSQL%'
   OR p.description ILIKE '%PostgreSQL%';
```

In SQL, `AND` binds tighter than `OR`, so PostgreSQL parses this as:

```text
(tenant_id = 2
 AND status = PUBLISHED
 AND name ILIKE ...)
OR
(description ILIKE ...)
```

The second branch can return products from **any tenant**, including `DRAFT`, `BLOCKED`, or soft-deleted rows, as long as the keyword appears in `description`.

### 9.2. Correct: Parenthesize the Text Search Branches

```sql
SELECT p.product_id, p.name, p.tenant_id
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND (
      p.name ILIKE '%PostgreSQL%'
      OR p.description ILIKE '%PostgreSQL%'
  );
```

Now tenant, status, and soft-delete rules govern **both keyword branches**.

Note that this still demonstrates only boolean grouping across three filters—it omits the seller, stock, time window, and country rules required in a full public query.

### 9.3. Practical Rule

Whenever combining multiple keyword branches:

```sql
WHERE mandatory_condition_1
  AND mandatory_condition_2
  AND mandatory_condition_3
  AND (
      text_condition_A
      OR text_condition_B
  )
```

Never assemble SQL fragments across helper methods without guaranteeing precedence.

### 9.4. Complex OR Clauses Also Affect Performance

An `OR` across two predicates can lead the planner to pick a Seq Scan or a `BitmapOr` when suitable indexes exist. Once semantics are verified, check whether efficient index access paths are available.

## 10. Filter-Then-LIMIT Is Fundamentally Different from LIMIT-Then-Filter

A frequent bug is grabbing the top 20 raw text matches and applying business rules afterward.

### 10.1. Wrong Example

```sql
WITH top_text_matches AS MATERIALIZED (
    SELECT
        p.product_id,
        p.name,
        p.status,
        p.deleted_at,
        p.stock_qty,
        ts_rank_cd(
            p.search_vector,
            websearch_to_tsquery('simple', 'PostgreSQL')
        ) AS relevance
    FROM search_rules_lab.products AS p
    WHERE p.search_vector @@
          websearch_to_tsquery('simple', 'PostgreSQL')
    ORDER BY relevance DESC, product_id DESC
    LIMIT 20
)
SELECT *
FROM top_text_matches
WHERE status = 'PUBLISHED'
  AND deleted_at IS NULL
  AND stock_qty > 0;
```

This filters **only after slicing candidates down to 20 rows**.

For example, if 18 out of the top 20 raw matches are invalid, the final output shrinks to 2 rows—even if thousands of valid lower-scoring products exist underneath.

### 10.2. Correct Example

```sql
SELECT
    p.product_id,
    p.name,
    ts_rank_cd(
        p.search_vector,
        websearch_to_tsquery('simple', 'PostgreSQL')
    ) AS relevance
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.stock_qty > 0
  AND p.search_vector @@
      websearch_to_tsquery('simple', 'PostgreSQL')
ORDER BY relevance DESC, p.product_id DESC
LIMIT 20;
```

Here every predicate applies **to the same result set prior to `LIMIT`**.

*Note:* this is an abbreviated example focused on the `LIMIT` pitfall; a public business endpoint must still include seller, time window, and country rules as in Section 7.

### 10.3. Can You Fetch Top K Candidates Before Filtering to Speed Things Up?

That pattern is known as **candidate retrieval / overfetch** in search architectures. However, capping `K` before mandatory rules **does not guarantee** finding a full page of N valid hits and introduces authorization risk if retrieval scope is unsafe.

If a product accepts approximate search, explicitly specify quality/recall expectations and **never rely on post-filtering as the sole boundary protecting restricted rows**.

### 10.4. Why Was `MATERIALIZED` Used in the Wrong Example?

It explicitly illustrates fetching `top_text_matches` first; PostgreSQL must preserve the semantics of `LIMIT` inside a subquery/CTE.

Even without `MATERIALIZED`, a `LIMIT` inside a subquery before an outer `WHERE` still creates “top-K first, filter later” semantics.

### 10.5. Do Not Force MATERIALIZED on Correct Queries

`WITH ... MATERIALIZED` can block predicate pushdown and force materializing large intermediate sets. Only use it when measurements justify it; keeping business filters at the same level as search matching is usually cleaner.

## 11. One-to-Many JOINs Can Duplicate Products

Suppose the UI allows filtering by tag.

### 11.1. Directly Joining All Tags

```sql
SELECT
    p.product_id,
    p.name,
    t.tag
FROM search_rules_lab.products AS p
JOIN search_rules_lab.product_tags AS t
  ON t.product_id = p.product_id
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
ORDER BY p.product_id
LIMIT 20;
```

A product with two tags appears **twice**.

When pagination runs after that join, 20 rows **no longer represent 20 distinct products**.

### 11.2. When Testing Tag Presence Only: Use EXISTS

```sql
SELECT
    p.product_id,
    p.name
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND EXISTS (
      SELECT 1
      FROM search_rules_lab.product_tags AS t
      WHERE t.product_id = p.product_id
        AND t.tag = 'discount'
  )
ORDER BY p.product_id DESC
LIMIT 20;
```

`EXISTS` evaluates to a boolean per product and never multiplies rows regardless of how many tags a product carries.

### 11.3. When You Also Need to Return the Tag List

You can aggregate tags in a subquery after picking the target products, or use `array_agg` with `GROUP BY`. Be careful that `GROUP BY` or aggregation does not inadvertently alter ranking or pagination semantics.

### 11.4. DISTINCT Is Not Always the Right Fix

Adding:

```sql
SELECT DISTINCT p.product_id, p.name ...
```

masks duplicate rows while adding extra hash/sort work and fails to solve cases where one-to-many joins distort `COUNT` or ranking.

Distinguish clearly:

- Filtering by **existence**: `EXISTS`.
- Fetching a single row along a unique relation: `JOIN` on a unique key.
- Summarizing multiple child rows: intentional aggregation.

## 12. EXISTS with Multiple Tag Selections

### 12.1. Any of the Selected Tags

```sql
SELECT p.product_id, p.name
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND EXISTS (
      SELECT 1
      FROM search_rules_lab.product_tags AS t
      WHERE t.product_id = p.product_id
        AND t.tag = ANY(
            ARRAY['discount', 'premium']::text[]
        )
  );
```

This expresses **OR across tags**: at least one tag in the list exists.

### 12.2. Must Have Both Tags

```sql
SELECT p.product_id, p.name
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND EXISTS (
      SELECT 1
      FROM search_rules_lab.product_tags AS t
      WHERE t.product_id = p.product_id
        AND t.tag = 'premium'
  )
  AND EXISTS (
      SELECT 1
      FROM search_rules_lab.product_tags AS t
      WHERE t.product_id = p.product_id
        AND t.tag = 'discount'
  );
```

Unlike `ANY` above, chaining two `EXISTS` predicates enforces **AND across tags**.

### 12.3. Excluding a Forbidden Tag

```sql
AND NOT EXISTS (
    SELECT 1
    FROM search_rules_lab.product_tags AS t
    WHERE t.product_id = p.product_id
      AND t.tag = 'restricted'
)
```

Add this predicate to the **full `WHERE` clause** when business rules exclude items tagged `restricted`.

### 12.4. Why Be Cautious with NOT IN?

`NOT IN (subquery)` obeys three-valued logic if the subquery can emit `NULL`. `NOT EXISTS` expresses anti-joins cleanly when checking “no matching child row exists”.

### 12.5. Indexes for Bidirectional Tag Lookups

In the lab, the primary key `(product_id, tag)` supports looking up tags for a product. If the workload frequently queries **all products sharing a tag**, consider an index:

```sql
CREATE INDEX product_tags_tag_product_idx
ON search_rules_lab.product_tags (tag, product_id);
```

Index column order governs lookups starting from `tag`. Avoid creating production indexes before measuring workload demand.

## 13. Joining Sellers: Mandatory Rules

In the public query:

```sql
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
...
AND s.is_verified
AND s.suspended_at IS NULL
```

This prevents products from surfacing when the seller is unverified or suspended.

### 13.1. One-to-Many vs. Many-to-One

Each product references a single seller via the composite foreign key; since the seller key is unique, this `JOIN` **does not duplicate products**.

If you replace `sellers` with a multi-row seller status history table, omitting the predicate selecting the active version will duplicate rows and produce wrong results.

### 13.2. EXISTS When Only Checking Seller Status

You can also write:

```sql
AND EXISTS (
    SELECT 1
    FROM search_rules_lab.sellers AS s
    WHERE s.tenant_id = p.tenant_id
      AND s.seller_id = p.seller_id
      AND s.is_verified
      AND s.suspended_at IS NULL
)
```

This is useful when you only need to validate the seller without returning seller columns.

### 13.3. Avoid Ambiguous LEFT JOIN Plus WHERE Filters

For example:

```sql
FROM products p
LEFT JOIN sellers s ON ...
WHERE s.is_verified = true
```

discards rows without a matching seller, effectively turning the `LEFT JOIN` into an `INNER JOIN` for that condition.

That behavior may be **intentional** if every valid product requires a verified seller, or a **bug** if business logic intends to keep sellerless items. Specify the requirement before picking a join type.

### 13.4. LEFT JOIN for Optional Display Data

For instance, a product might not have an active promotion row. Using `LEFT JOIN` works well for optional display attributes—just avoid placing a restrictive condition on the optional table in `WHERE` that accidentally drops items without promotions.

## 14. Dynamic Filters: Add Only Selected Predicates

An API may accept:

- Optional `category_id`.
- `min_price` / `max_price`.
- Tag list.
- `min_rating`.
- Country.
- Text query.

Two common patterns exist:

1. One giant SQL statement filled with `OR $n IS NULL`.
2. Selecting among query variants or building predicates dynamically under strict control, **always binding values**.

### 14.1. Optional Filter Pattern

```sql
WHERE p.tenant_id = $1
  AND ($2 IS NULL OR p.category_id = $2)
  AND ($3 IS NULL OR p.price >= $3)
  AND ($4 IS NULL OR p.price <= $4)
```

This preserves semantics when `NULL` means “unfiltered”, yet can prevent a **generic prepared plan** from selecting an optimal index path across both `NULL` and non-`NULL` executions.

### 14.2. Query Variants Can Be Easier to Optimize

Suppose an endpoint supports two modes:

```sql
-- With category:
WHERE p.tenant_id = $1
  AND p.category_id = $2

-- Without category:
WHERE p.tenant_id = $1
```

The application picks one of **two managed SQL templates** and binds parameters accordingly. This does not interpolate raw user input into SQL.

### 14.3. Avoiding Combinatorial Template Explosion

With ten optional filters, you do not need $2^{10}$ hand-written templates. Build SQL from an **allowlisted set of clause fragments**, binding every value through parameters.

Keep **mandatory predicates** unconditional in every branch; no query variant may ever omit tenant or eligibility constraints.

### 14.4. NULL Semantics vs. Empty Selections

`min_price = NULL` must clearly mean “no lower bound”, never silently treated as `0` if `0` carries distinct business meaning.

Similarly, `category_id = NULL` differs from an “empty category list”. An empty array could mean “match nothing” or “do not filter”; document and enforce the contract explicitly.

### 14.5. Never Build Parenthesis-Free Boolean Logic

Any dynamic fragment containing `OR` must wrap itself in parentheses:

```sql
AND (
    p.category_id = $n
    OR p.category_id = $m
)
```

Never append bare `OR ...` at the end of `WHERE`, which would disable tenant and status boundaries.

## 15. Effective Time Windows and Timezones

A product can be:

- Approved, awaiting its scheduled release time.
- Currently active.
- Past its campaign end date.
- Sold only within local calendar dates.

### 15.1. `timestamptz` Columns and Reference `as_of`

In the lab:

```sql
p.published_at <= $as_of
AND (
    p.available_until IS NULL
    OR p.available_until > $as_of
)
```

Using `timestamptz` compares **exact instants in time**. Pass one consistent `as_of` instant across all time predicates in the query.

### 15.2. Repeatable Point-in-Time Queries

```sql
SELECT COUNT(*)
FROM search_rules_lab.products AS p
WHERE p.published_at <=
      timestamptz '2026-11-14 00:00:00+00'
  AND (
      p.available_until IS NULL
      OR p.available_until >
         timestamptz '2026-11-14 00:00:00+00'
  );
```

Testing with a fixed timestamp prevents results from drifting with the wall clock.

### 15.3. In Production

`as_of` can be generated by the server or supplied from a trusted context. Inside a PostgreSQL transaction, `now()` and `CURRENT_TIMESTAMP` return the transaction start time; long-running transactions see an older instant.

When an exact wall-clock instant is needed at a specific step, choose the timestamp source deliberately, and avoid calling `clock_timestamp()` per row in `WHERE` unnecessarily.

### 15.4. Local Calendar Date Ranges

If the UI selects “November 14 in Vietnam time”, convert local boundaries into an **explicit `timestamptz` range**:

```sql
WHERE created_at >=
      (timestamp '2026-11-14 00:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh')
  AND created_at <
      (timestamp '2026-11-15 00:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh')
```

Use a half-open interval `[start, end)` to avoid losing fractional seconds. Never treat local calendar dates as UTC.

### 15.5. Never Create Partial Indexes Using `now()`

A broken idea:

```sql
-- DO NOT USE:
CREATE INDEX ...
ON products (...)
WHERE available_until > now();
```

Index predicates require appropriate immutability; `now()` is not immutable, and the set of “currently valid” rows changes as time advances without row updates.

Index the stable columns that narrow down candidates, and filter dynamic timestamps at query time.

## 16. Price, Currency, and Nullable Business Attributes

### 16.1. Price Ranges

```sql
AND p.price >= $min_price
AND p.price <= $max_price
```

Clarify whether bounds are inclusive, and validate `min > max` in the application.

### 16.2. Currency

If products span multiple currencies, price filters must:

- Filter by explicit currency; or
- Convert using versioned, timestamped exchange rates; and
- Never compare mismatched currencies on the same numeric scale.

No index can fix the semantic error of comparing 500 VND directly against 500 USD.

### 16.3. Unpriced Items

In our lab schema, `price` is `NOT NULL`. If a real system permits `price IS NULL`, `price >= 100` excludes `NULL` rows via three-valued logic.

Decide explicitly whether “contact for quote” items appear under price filters instead of relying on implicit `NULL` behavior.

### 16.4. Ratings and NULL

If a product has no reviews yet, model `rating` as `NULL` (or pair with `review_count`) rather than defaulting to `0`, which confuses unrated items with genuinely 0-star items.

The lab schema assigns fixed ratings solely to illustrate `ORDER BY`; it does not prescribe a real review model.

## 17. FTS, ILIKE, and Trigrams: Pick the Right Text Predicate

### 17.1. Full Text Search

```sql
p.search_vector @@
websearch_to_tsquery('simple', $text)
```

FTS operates over lexemes and tokens, suiting **keyword-oriented queries** rather than arbitrary mid-word substrings.

### 17.2. Substring Contains with ILIKE

```sql
p.name ILIKE '%postgresql%'
```

`ILIKE` evaluates wildcard patterns case-insensitively according to database locale/collation rules.

### 17.3. Escaping Literal Wildcard Characters

If the user types `%` or `_` intending a **literal character**, escape them explicitly:

```sql
p.name ILIKE $pattern ESCAPE '!'
```

The application turns literal input `pg_trgm` into `%pg!_trgm%` using escape character `!`.

Parameter binding prevents SQL injection but **does not escape `LIKE` wildcards automatically**.

### 17.4. Trigram Indexes for Substring Matching

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX products_name_trgm_idx
ON search_rules_lab.products
USING gin (name gin_trgm_ops);
```

A GIN trigram index accelerates `LIKE`/`ILIKE` when patterns contain selective literals, yet **offers little benefit for very short or overly broad patterns**.

### 17.5. FTS Does Not Replace Substring Matching

If a user types `gres` expecting `PostgreSQL`, lexeme-based FTS usually will not match mid-word fragments. `ILIKE '%gres%'` backed by a trigram index fits better.

### 17.6. ILIKE Does Not Strip Accents Automatically

Case-insensitive does not automatically mean accent-insensitive or Unicode-normalized. If UX requires `cafe` to match `Café`, design explicit normalization, collations, or dictionaries.

### 17.7. Guarding Empty Queries

`websearch_to_tsquery('simple', '')` produces an empty `tsquery` with zero useful nodes. The API must define whether empty input:

- Lists all eligible items;
- Requires entering a keyword; or
- Enforces a minimum character count.

Never turn an empty input into `ILIKE '%%'` that scans the table on every keystroke.

## 18. Combining FTS and ILIKE with OR

An application might want to:

- Primarily match words via FTS.
- Still catch substring hits in the title.

Example:

```sql
WITH q AS (
    SELECT
        websearch_to_tsquery('simple', 'PostgreSQL')
            AS tsq,
        '%PostgreSQL%'::text AS title_pattern
)
SELECT
    p.product_id,
    p.name,
    ts_rank_cd(p.search_vector, q.tsq) AS fts_rank
FROM search_rules_lab.products AS p
CROSS JOIN q
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND (
      p.search_vector @@ q.tsq
      OR p.name ILIKE q.title_pattern
  )
ORDER BY
    fts_rank DESC,
    p.product_id DESC
LIMIT 20;
```

**This example focuses on combining two text predicates** and omits seller/stock/time/country filters; keep all mandatory predicates in any production query.

### 18.1. Parenthesizing the OR

Wrapping both text predicates in parentheses guarantees tenant and status apply across both branches.

### 18.2. When FTS Misses but ILIKE Matches

`ts_rank_cd` returns `0` for rows included solely via `ILIKE`. Define an explicit fallback score if such matches need secondary priority.

### 18.3. Combined Ranking Must Reflect Business Meaning

Example scoring formula:

```sql
CASE
    WHEN p.search_vector @@ q.tsq
      THEN ts_rank_cd(p.search_vector, q.tsq)
    ELSE 0
END
+
CASE
    WHEN p.name ILIKE q.title_pattern
      THEN 0.2
    ELSE 0
END AS relevance
```

The constant `0.2` is strictly a **design illustration**, not a universal tuning magic number. FTS scores and business bonuses do not necessarily share scales—evaluate result quality, not just latency.

### 18.4. Index Paths with OR

When both a GIN FTS index and a GIN trigram index on `name` exist, the planner may consider bitmap scans and even `BitmapOr`, or revert to a Seq Scan if predicates are broad or index cost is uncompetitive.

### 18.5. UNION / UNION ALL

You can split two search branches using `UNION` or `UNION ALL` to control query shape, provided you:

- Apply the **exact same mandatory business filters** to both branches.
- Prevent a product matching both branches from appearing twice.
- Merge relevance scores consistently.
- **Never apply `LIMIT` prematurely to individual branches**, which drops global top-N candidates.

Rewriting `OR` into `UNION` is not automatically faster; benchmark both.

## 19. Ranking: Relevance Differs from Commercial Priority

`ts_rank_cd` provides a textual relevance score. Products may also be prioritized by:

- Rating score and review count.
- Recency.
- Promotional status.
- Content completeness.
- Valid campaign boosts.
- Language or regional fit.

### 19.1. Illustrative Formula

```sql
WITH q AS (
    SELECT websearch_to_tsquery('simple', 'PostgreSQL') AS tsq
)
SELECT
    p.product_id,
    p.name,
    ts_rank_cd(p.search_vector, q.tsq)
        AS text_rank,
    (
        ts_rank_cd(p.search_vector, q.tsq)
        + (p.rating::real * 0.02::real)
    ) AS combined_score
FROM search_rules_lab.products AS p
CROSS JOIN q
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.search_vector @@ q.tsq
ORDER BY
    combined_score DESC,
    p.product_id DESC
LIMIT 20;
```

This illustrates **scoring mechanics**, not a production-validated ranking model.

### 19.2. Boosts Never Override Authorization

Regardless of how high text rank or ratings are, a product belonging to a suspended seller must remain excluded.

### 19.3. Avoid Over-Biasing Signals

If ratings overwhelm textual relevance, users searching for a specific keyword may see off-topic yet highly rated items. Test ranking quality against real query benchmarks.

### 19.4. Lexicographic Priority Ordering

Instead of summing incompatible scales:

```sql
ORDER BY
    text_rank DESC,
    p.rating DESC,
    p.created_at DESC,
    p.product_id DESC
```

This has clear semantics: textual rank comes first, while rating breaks ties.

### 19.5. A Unique Tie-Breaker Is Essential

With `ORDER BY relevance DESC` alone, equal-scoring rows can shuffle between executions. Adding `product_id` establishes a deterministic total order within a snapshot.

## 20. Structuring Ranking After Eligibility

A clean, readable query layout:

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'simple', 'PostgreSQL'
    ) AS tsq
),
eligible_matches AS (
    SELECT
        p.product_id,
        p.name,
        p.price,
        p.rating,
        p.created_at,
        ts_rank_cd(p.search_vector, q.tsq) AS text_rank
    FROM search_rules_lab.products AS p
    JOIN search_rules_lab.sellers AS s
      ON s.tenant_id = p.tenant_id
     AND s.seller_id = p.seller_id
    CROSS JOIN q
    WHERE p.tenant_id = 2
      AND p.status = 'PUBLISHED'
      AND p.deleted_at IS NULL
      AND p.stock_qty > 0
      AND p.country_code = 'VN'
      AND s.is_verified
      AND s.suspended_at IS NULL
      AND p.published_at <=
          timestamptz '2026-11-14 00:00:00+00'
      AND (
          p.available_until IS NULL
          OR p.available_until >
             timestamptz '2026-11-14 00:00:00+00'
      )
      AND p.search_vector @@ q.tsq
)
SELECT *
FROM eligible_matches
ORDER BY
    text_rank DESC,
    rating DESC,
    created_at DESC,
    product_id DESC
LIMIT 20;
```

### 20.1. Benefits

- Naming `eligible_matches` highlights the mandatory filtering step.
- Ranking runs strictly over policy-compliant rows.
- No premature `LIMIT` sits inside the candidate CTE.
- Additional `category`/`price`/`tag` filters drop cleanly into the same `WHERE`.

### 20.2. CTEs Are Not Security Boundaries

PostgreSQL optimizes and inlines CTEs; naming a CTE `eligible_matches` **does not replace authorization or RLS**. Security demands proper database roles, policies, and application checks.

### 20.3. CTEs Do Not Materialize Like Legacy Versions

In modern PostgreSQL, non-recursive side-effect-free CTEs are commonly inlined. Never write a CTE just to “force tenant filtering first” under the belief that SQL executes strictly top-to-bottom.

## 21. Pagination: Right Filters Can Still Yield Unstable Pages

### 21.1. LIMIT/OFFSET

```sql
SELECT product_id, name, price
FROM search_rules_lab.products
WHERE tenant_id = 2
  AND status = 'PUBLISHED'
  AND deleted_at IS NULL
ORDER BY created_at DESC, product_id DESC
LIMIT 20 OFFSET 40;
```

Semantics: skip the first 40 ordered results and return the next 20.

**Drawbacks:**

- Deep offsets force scanning and discarding large numbers of preceding rows.
- Concurrent writes between page loads can cause duplicate or skipped items.
- Without a unique tie-breaker, rows sharing `created_at` can reorder unpredictably.

### 21.2. Keyset Pagination for Fixed Orders

For `created_at DESC, product_id DESC`:

```sql
SELECT product_id, name, created_at
FROM search_rules_lab.products
WHERE tenant_id = 2
  AND status = 'PUBLISHED'
  AND deleted_at IS NULL
  AND (created_at, product_id) <
      (
          timestamptz '2026-01-05 00:00:00+00',
          5000::bigint
      )
ORDER BY created_at DESC, product_id DESC
LIMIT 20;
```

This cursor is illustrative; clients must derive the tuple from the **last item on the previous page**, never fabricating production cursors.

### 21.3. Keyset When Sorting by Relevance

For:

```sql
ORDER BY text_rank DESC,
         created_at DESC,
         product_id DESC
```

a cursor can encode `text_rank`, `created_at`, and `product_id` using a matching tuple comparison when types and sort directions align.

Keep in mind that `ts_rank_cd` depends on the keyword and current document text, which shifts if a product is updated. Bind cursors to **the exact keyword, filters, and sort configuration**, and define behavior when underlying data mutates.

### 21.4. Never Reuse Cursors Across Tenants or Filter Sets

Bind cursors to the search context (or verify a signed hash of filters and sort order) so a cursor from one query cannot produce broken ordering or weaken tenant/authorization isolation.

### 21.5. Snapshot Consistency

Under `READ COMMITTED`, separate statements get separate snapshots. Fetching the result page and running `COUNT(*)` in two queries may disagree slightly during concurrent writes.

If strict cross-query snapshot consistency is required, use appropriate transaction isolation (`REPEATABLE READ`), weighing transaction duration overhead against UX tolerance for minor drift.

## 22. COUNT and Total Hits Must Share the Same Business Filters

A classic UI bug displays:

```text
Found 8,000 results.
```

while showing only 200 viewable products because `COUNT(*)` scanned the whole table while the listing query enforced tenant and eligibility rules.

### 22.1. Correct: COUNT Over the Filtered Set

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'simple', 'PostgreSQL'
    ) AS tsq
)
SELECT COUNT(*) AS total_matches
FROM search_rules_lab.products AS p
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
CROSS JOIN q
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.stock_qty > 0
  AND p.country_code = 'VN'
  AND s.is_verified
  AND s.suspended_at IS NULL
  AND p.published_at <=
      timestamptz '2026-11-14 00:00:00+00'
  AND (
      p.available_until IS NULL
      OR p.available_until >
         timestamptz '2026-11-14 00:00:00+00'
  )
  AND p.search_vector @@ q.tsq;
```

This counts only eligible matches before optional filters. If the list query also filters category, price, or tags, `COUNT(*)` must apply **those exact same filters** when reporting total hits.

### 22.2. Full Exact Counts Can Be Expensive

`COUNT(*)` must evaluate every matching candidate to produce an exact total. Even with an index, counting millions of matches is costly.

UX alternatives include:

- Exact total counts only where required.
- Capped or approximate counts when acceptable.
- “Has next page” (`LIMIT N + 1`) pagination without computing full totals.
- Scoped short-TTL count caching if slight staleness is acceptable.

Never present an estimate as an exact count.

### 22.3. `COUNT(*) OVER()`

You can write:

```sql
SELECT
    p.product_id,
    p.name,
    COUNT(*) OVER () AS total_matches
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
ORDER BY p.product_id DESC
LIMIT 20;
```

The window count evaluates after `WHERE` and before `LIMIT` at this query level.

However, **to compute that total**, the executor must process every matching row, defeating early-termination optimizations of `LIMIT`—and if the page is empty (e.g., high `OFFSET`), no row exists to carry the count back to the client.

### 22.4. Never Count Rows After a Many-to-One Tag Join

`COUNT(*)` after joining tags counts product-tag pairs rather than **distinct products**. Use `EXISTS` for tag filters so each product remains a single row.

## 23. Category Facets: Counts Must Stay Consistent

Search UIs often show:

```text
Results for “PostgreSQL”
  Category 2: 25
  Category 6: 18
  ...
```

These counts are called **facets**.

### 23.1. Category Counts After Business Filters and Keyword

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'simple', 'PostgreSQL'
    ) AS tsq
),
eligible_matches AS (
    SELECT p.product_id, p.category_id
    FROM search_rules_lab.products AS p
    JOIN search_rules_lab.sellers AS s
      ON s.tenant_id = p.tenant_id
     AND s.seller_id = p.seller_id
    CROSS JOIN q
    WHERE p.tenant_id = 2
      AND p.status = 'PUBLISHED'
      AND p.deleted_at IS NULL
      AND p.stock_qty > 0
      AND p.country_code = 'VN'
      AND s.is_verified
      AND s.suspended_at IS NULL
      AND p.published_at <=
          timestamptz '2026-11-14 00:00:00+00'
      AND (
          p.available_until IS NULL
          OR p.available_until >
             timestamptz '2026-11-14 00:00:00+00'
      )
      AND p.search_vector @@ q.tsq
)
SELECT
    category_id,
    COUNT(*) AS product_count
FROM eligible_matches
GROUP BY category_id
ORDER BY product_count DESC, category_id;
```

### 23.2. Never Compute Facets After LIMIT

Wrong:

```sql
WITH first_page AS (
    SELECT *
    FROM search_rules_lab.products
    WHERE tenant_id = 2
    ORDER BY product_id DESC
    LIMIT 20
)
SELECT category_id, COUNT(*)
FROM first_page
GROUP BY category_id;
```

That only counts the **20 products on page 1**, not facets across the entire search result.

### 23.3. Self-Excluding Facets

Two common semantics appear once a user selects `category = 2`:

1. **Conjunctive facets:** compute category counts after applying `category = 2`, leaving only category 2.
2. **Disjunctive (self-excluding) facets:** compute category counts using **all other filters**, temporarily omitting the category filter itself so users see counts available in alternative categories.

Neither is universally “right” for every UX. Define the contract explicitly and write matching SQL.

### 23.4. Two Separate Count Queries

- Listing query: enforces all active filters, including the selected category.
- Category facet query: depending on UX, may omit **only** the category filter, while strictly keeping tenant, status, seller, and all authorization/eligibility filters.

Never compute facets over raw matches across other tenants; even aggregate counts can leak restricted information.

### 23.5. Tag Facets

Because a product can have multiple tags, per-tag counts count each product once **per tag**, meaning the sum of tag counts can exceed total products.

Keep clear the difference between “each product belongs to one category” and “each product can carry many tags”.

## 24. Authorization Rules and RLS

Tenant filtering in application SQL is necessary, yet fragile on its own when an application grows across many queries, reports, and endpoints.

PostgreSQL supports **Row-Level Security (RLS)** as a database-level defense layer when configured properly.

### 24.1. Policy Flow

Conceptually:

```text
Verified authentication
       |
       v
Server determines allowed tenant
       |
       v
Trusted role / session context
       |
       v
RLS policy restricts visible rows
       |
       v
Text search query + business filters
```

### 24.2. Illustrative RLS Setup Requiring Careful Deployment

```sql
-- Architecture example; do not run as-is on a shared lab role:
ALTER TABLE search_rules_lab.products
ENABLE ROW LEVEL SECURITY;

CREATE POLICY products_tenant_select_policy
ON search_rules_lab.products
FOR SELECT
USING (
    tenant_id =
    NULLIF(
        current_setting('app.tenant_id', true),
        ''
    )::integer
);
```

Here the policy reads the session setting `app.tenant_id`. **This is not inherently trustworthy** if untrusted users can execute arbitrary SQL or change session GUCs themselves.

Safe deployment requires:

- Properly scoped database roles and connection privileges.
- Server-side tenant authentication; never trusting user-supplied tenant IDs.
- Blocking untrusted clients from running arbitrary SQL or `SET`.
- Setting and resetting session state reliably across connection pools.
- Never using table owners, superusers, or roles with `BYPASSRLS` as end-user connection roles unless intended and understood.
- Matching policies on `sellers` and related tables.
- Testing policies with queries that deliberately omit `WHERE tenant_id`.

### 24.3. Table Owners and FORCE ROW LEVEL SECURITY

By default, table owners bypass RLS in PostgreSQL unless `FORCE ROW LEVEL SECURITY` is enabled where appropriate; superusers and `BYPASSRLS` roles follow special bypass rules.

Never assume “enabling RLS automatically restricts every connection identically”.

### 24.4. Connection Pools and SET LOCAL

If binding tenant context per transaction:

```sql
BEGIN;

SET LOCAL app.tenant_id = '2';

-- Tenant 2 queries within the same transaction.

COMMIT;
```

Ensure every query executes **on the same connection and transaction**, with `app.tenant_id` populated from server authorization.

Never issue `SET LOCAL` outside an explicit transaction expecting it to persist into subsequent autocommit statements.

### 24.5. RLS Does Not Replace Business Eligibility

Tenant RLS restricts visibility to tenant 2, yet does not automatically hide:

- Drafts.
- Blocked products.
- Soft-deleted items.
- Suspended sellers.
- Expired listings.
- Out-of-stock items.

If any of those attributes also act as security rules, enforce them in policies or dedicated controls rather than relying solely on UI logic.

### 24.6. Do Not Let Rankings or Facets Bypass Scope

Authorization must guard **listings, autocomplete, suggestions, counts, facets, and exports alike**. An endpoint returning only counts can still leak the existence and volume of unauthorized rows.

## 25. Do Not Offload Mandatory Filtering to Application Post-Processing

Suppose an API runs:

```sql
SELECT *
FROM search_rules_lab.products
WHERE search_vector @@
      websearch_to_tsquery('simple', $1)
ORDER BY product_id
LIMIT 100;
```

Followed by a Java loop:

```text
if product.tenant == currentTenant
   && product.status == PUBLISHED
   && seller.isVerified
   && stock > 0:
      show product
```

Problems:

1. The database returned rows **outside the authorized scope**.
2. Mistakes in logging, caching, or serialization can leak restricted records.
3. Applying `LIMIT 100` before eligibility prevents filling a valid top-N page.
4. Extra network transfer and object allocation are wasted.
5. Separate count and facet queries easily drift out of sync.
6. The application fetches seller state for ineligible items.

**Solution:** push authorization and business eligibility predicates into the database query itself, backed by RLS and DB roles for defense-in-depth. Application post-processing should handle only display formatting that does not shrink the authorized set.

## 26. Does the Planner Evaluate WHERE Clauses in Written Order?

No. SQL is declarative.

```sql
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.search_vector @@ q.tsq
```

does not guarantee the executor filters tenant first, then status, then FTS. PostgreSQL may:

- Use the GIN index to retrieve text candidates first.
- Use a B-tree or partial index on tenant/status first.
- Combine bitmaps with `BitmapAnd`.
- Run a `Seq Scan` with a combined filter.
- Reorder joins based on statistics.
- Push predicates down into scan nodes where valid.

### 26.1. Planning Must Preserve Semantics

Regardless of evaluation order, a valid query plan returns the exact set of rows dictated by `WHERE`, `JOIN`, and SQL security rules.

### 26.2. Never Rely on WHERE Order to Guard Unsafe Functions

Never treat clause order as a security guard or assume an error-prone/side-effectful function will never run on excluded rows. Enforce security via roles and policies, and make expressions safe against unexpected types or `NULL` values.

### 26.3. MATERIALIZED CTEs Are No Security Panacea

Forcing materialization hurts predicate pushdown and adds memory/temp-disk I/O. It neither replaces RLS/authorization nor fixes a missing tenant condition in an `OR` or `UNION` branch.

## 27. Index Strategy: Business Filters and Search Must Work Together

Combined search queries leverage multiple index types.

### 27.1. B-Tree for Categorical and Range Filters

```sql
CREATE INDEX products_tenant_status_category_price_idx
ON search_rules_lab.products (
    tenant_id,
    status,
    category_id,
    price
);
```

This is a **reference layout**. Our lab already created `products_tenant_status_idx` with this exact definition; do not create a duplicate.

B-trees excel at equality, range, and sort operations along leading keys, especially when those predicates are highly selective.

### 27.2. GIN tsvector

```sql
CREATE INDEX products_search_gin_idx
ON search_rules_lab.products
USING gin (search_vector);
```

GIN finds posting lists and candidate IDs by lexeme. It does not natively store seller verification state or dynamic prices to satisfy every business filter alone.

### 27.3. GIN Trigram on Name

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX products_name_trgm_idx
ON search_rules_lab.products
USING gin (name gin_trgm_ops);
```

Useful for `ILIKE`/contains queries with selective literals. Very short or common patterns may see limited benefit.

### 27.4. Seller Indexes

The lab defines:

```sql
PRIMARY KEY (seller_id)
UNIQUE (tenant_id, seller_id)
```

Joining on `(tenant_id, seller_id)` has unique index paths ready. However, indexing low-cardinality boolean columns like `is_verified` independently does not guarantee better join performance.

### 27.5. Tag Indexes

`PRIMARY KEY (product_id, tag)` retrieves tags for a given product. If finding products by tag dominates the workload, testing `(tag, product_id)` can pay off.

### 27.6. No Single Index Solves Everything

PostgreSQL can start from the FTS GIN index and filter tenant/business predicates, or scan the tenant/status B-tree and evaluate text matches over a smaller subset. The right choice depends on **combined selectivity**, not a single predicate in isolation.

## 28. Partial Indexes for Stable Predicates

Public search queries almost always require:

```sql
status = 'PUBLISHED'
AND deleted_at IS NULL
```

You can define a partial index:

```sql
CREATE INDEX products_visible_tenant_category_price_idx
ON search_rules_lab.products (
    tenant_id, category_id, price
)
WHERE status = 'PUBLISHED'
  AND deleted_at IS NULL;
```

### 28.1. Partial B-Trees Can Be Smaller Than Full Indexes

They index only rows matching the static predicate. When drafts, hidden items, and soft-deleted rows make up a large share of the table, index size and scan cost shrink.

### 28.2. Partial GIN for FTS

```sql
CREATE INDEX products_visible_search_gin_idx
ON search_rules_lab.products
USING gin (search_vector)
WHERE status = 'PUBLISHED'
  AND deleted_at IS NULL;
```

If nearly all FTS queries target published, non-deleted items, a partial GIN index reduces the entries PostgreSQL must maintain.

**Do not keep both a full GIN index and a partial GIN index in production by default.** Maintaining two GIN indexes on the same column causes major write amplification; choose based on whether queries also search drafts/internal records.

### 28.3. Generic Prepared Plans and Partial Index Predicates

If a query writes:

```sql
WHERE status = $1
  AND deleted_at IS NULL
```

a generic plan cannot assume `$1 = 'PUBLISHED'` for every execution, so a partial index defined `WHERE status = 'PUBLISHED'` cannot be used.

When an endpoint **exclusively searches public products**, hardcode the business constants:

```sql
WHERE status = 'PUBLISHED'
  AND deleted_at IS NULL
  AND tenant_id = $1
```

while still binding tenant and keyword, allowing the planner to match the partial index predicate.

### 28.4. Never Put NOW() in a Partial Index Predicate

Do not write:

```sql
-- Invalid as an immutable index predicate:
WHERE available_until > now()
```

Validity changes as wall-clock time advances even when rows are untouched; PostgreSQL requires immutable expressions in index predicates.

### 28.5. Partial Indexes Are Not Access Controls

An index predicate merely limits which rows live inside that index; it **does not prevent another query from reading non-public rows**. Access restrictions must come from RLS, roles, and application authorization.

## 29. Multicolumn GIN or BitmapAnd?

PostgreSQL supports extensions and operator classes such as `btree_gin` for mixing scalar keys inside GIN. Even so, a **multicolumn GIN index** does not automatically outperform combining:

- FTS GIN index.
- B-tree on tenant/category/price.
- Selective `Bitmap Index Scan` paths.
- `BitmapAnd` or post-scan filtering.

### 29.1. BitmapAnd Is One Possible Path

An execution plan may resemble:

```text
Bitmap Heap Scan on products
  Recheck Cond: ...
  Filter: ...
  -> BitmapAnd
       -> Bitmap Index Scan on products_search_gin_idx
       -> Bitmap Index Scan on products_tenant_status_idx
```

This is an **illustrative plan**; the planner can pick another strategy based on statistics.

### 29.2. Tenant Is Not Automatically Inside FTS GIN

A GIN index on `search_vector` stores lexeme postings across all tenants; when a keyword is common across tenants, candidate lists grow large. Consider partial indexes, partitioning, or alternate strategies depending on workload.

### 29.3. Do Not Expect Multicolumn GIN to Solve ORDER BY

`ORDER BY relevance DESC` depends on the runtime keyword, so candidates generally still require rank calculation. B-tree or GIN indexes cannot precompute relevance order across arbitrary queries.

### 29.4. Is Partitioning by Tenant Necessary?

For massive tables where queries always filter by tenant, partitioning can help, at the expense of catalog, DDL, and maintenance overhead. Never split a table into thousands of partitions just to avoid adding the right indexes.

## 30. Using EXPLAIN with Combined Search and Business Predicates

Run:

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    p.product_id,
    p.name
FROM search_rules_lab.products AS p
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.stock_qty > 0
  AND s.is_verified
  AND s.suspended_at IS NULL
  AND p.search_vector @@
      websearch_to_tsquery('simple', 'PostgreSQL')
ORDER BY p.product_id DESC
LIMIT 20;
```

Inspect these elements:

| In EXPLAIN | Question to Ask |
| --- | --- |
| `Seq Scan` | Why was a sequential scan estimated cheaper than an index? |
| `Bitmap Index Scan` | Which index supplied candidates? |
| `Bitmap Heap Scan` | How many heap pages were fetched/rechecked? |
| `Index Cond` | Which predicates narrowed index access? |
| `Filter` | Which business or text predicates filtered after the scan? |
| `Rows Removed by Filter` | Were many candidates discarded by business rules? |
| `Recheck Cond` | Which index conditions required heap recheck? |
| `Hash Join` / `Nested Loop` | How was the seller join executed? |
| `rows` / `actual rows` | Were planner row estimates accurate? |
| `Buffers` | How many shared hits and reads occurred? |
| `Sort` / top-N sort | What did ranking and `ORDER BY` cost? |
| `Planning Time` | Did planning consume significant time? |
| `Execution Time` | What was server-side execution duration? |
| `loops` | Was an index or join node executed repeatedly? |

### 30.1. Cost Is Not Milliseconds

`cost=0.00..1000.00` represents abstract planner cost units, not 1000 ms.

### 30.2. Buffers Are Not Exact Physical Disk Reads

`shared read` indicates blocks brought into PostgreSQL shared buffers; the OS page cache may satisfy those reads without disk I/O. Cold and warm runs behave differently.

### 30.3. A Seq Scan Is Not Automatically a Bug

For very common keywords, large tenant fractions, or small tables, a sequential scan can genuinely be optimal.

### 30.4. Having a GIN Index Does Not Guarantee Using It

The planner weighs candidate retrieval, business filtering, seller joins, sorting, and limits together. An unselective index can rightly be skipped.

### 30.5. EXPLAIN ANALYZE Executes the Statement

For `SELECT`, it executes and times the query. For `UPDATE`/`DELETE`, `EXPLAIN ANALYZE` **modifies data** inside the transaction. Never run DML `EXPLAIN ANALYZE` on production without safeguards.

## 31. Statistics and Data Skew

In our lab, tenant, category, and status are correlated. Inaccurate combined selectivity estimates can mislead join and scan choices.

### 31.1. Inspecting Column Statistics

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    correlation
FROM pg_stats
WHERE schemaname = 'search_rules_lab'
  AND tablename = 'products'
  AND attname IN (
      'tenant_id',
      'category_id',
      'status',
      'country_code'
  )
ORDER BY attname;
```

### 31.2. MCVs and Business Values

If `PUBLISHED` accounts for most rows, a standalone B-tree index on `status` is far less selective than an appropriate partial or composite index.

When one tenant is huge while others are small, a single generic plan may perform poorly for one or both extremes.

### 31.3. Extended Statistics for Correlated Columns

```sql
CREATE STATISTICS products_tenant_category_stats
    (mcv, dependencies)
ON tenant_id, category_id
FROM search_rules_lab.products;

ANALYZE search_rules_lab.products;
```

Multi-column statistics improve row estimates across correlated predicates. They **do not create indexes** and do not enforce access control.

### 31.4. Stale Statistics

Run `ANALYZE` after bulk loads, deletes, or distribution shifts. When a query actually returns 100 rows while the planner estimates 100,000, suboptimal plans result.

### 31.5. Custom vs. Generic Prepared Plans

Parameterized queries over tenant, keyword, and ranges may receive custom or generic plans. To test `plan_cache_mode` in the lab:

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

-- EXPLAIN (ANALYZE, BUFFERS)
-- EXECUTE search_products(...);

ROLLBACK;
```

Similarly, test `force_generic_plan`. **Do not force custom or generic plans database-wide** because of one query; measure both planning overhead and execution time across representative parameters.

## 32. Same Business Result, Multiple Execution Strategies

Several execution patterns occur in practice:

### 32.1. GIN-First

```text
Locate document IDs matching lexemes in GIN
    |
Fetch heap candidates
    |
Filter tenant, status, deleted, seller, stock, time
    |
Rank and sort
```

Works well for selective keywords, yet generates large candidate sets when keywords appear frequently across many tenants.

### 32.2. Business-Index-First

```text
B-tree filters tenant/category/status
    |
Retrieve narrow product subset
    |
Evaluate text match
    |
Rank and sort
```

Often strong when business filters are highly selective.

### 32.3. Bitmap Combination

```text
GIN bitmap of text candidates
          +
B-tree bitmap of business candidates
          |
       BitmapAnd
          |
   Bitmap Heap Scan
          |
  Recheck / remaining filters
```

One access path PostgreSQL may consider, though never guaranteed.

### 32.4. The Right Index Still Leaves Ranking Cost

Search relevance depends on the runtime keyword. Even if candidates are fetched quickly, scoring tens of thousands of hits incurs CPU and sorting cost.

### 32.5. Decide Using Metrics

Do not clutter queries with `MATERIALIZED` CTEs trying to hand-force scan order by intuition. Measure `EXPLAIN (ANALYZE, BUFFERS)`, inspect statistics, and adjust one factor at a time for a clear reason.

## 33. Java/JDBC: Safe Queries with Tenant and Mandatory Filters

Example using `PreparedStatement` with static business predicates and trusted context parameters:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import javax.sql.DataSource;

public final class ProductSearchService {
    private final DataSource dataSource;

    public ProductSearchService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void search(
        int authenticatedTenantId,
        String queryText,
        String country,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        Instant asOf
    ) throws SQLException {

        String sql = """
            WITH q AS (
                SELECT websearch_to_tsquery(
                    'simple', ?
                ) AS tsq
            )
            SELECT
                p.product_id,
                p.name,
                p.price,
                ts_rank_cd(p.search_vector, q.tsq) AS score
            FROM search_rules_lab.products AS p
            JOIN search_rules_lab.sellers AS s
              ON s.tenant_id = p.tenant_id
             AND s.seller_id = p.seller_id
            CROSS JOIN q
            WHERE p.tenant_id = ?
              AND p.country_code = ?
              AND p.status = 'PUBLISHED'
              AND p.deleted_at IS NULL
              AND p.stock_qty > 0
              AND s.is_verified
              AND s.suspended_at IS NULL
              AND p.published_at <= ?
              AND (
                  p.available_until IS NULL
                  OR p.available_until > ?
              )
              AND p.price >= ?
              AND p.price <= ?
              AND p.search_vector @@ q.tsq
            ORDER BY
                score DESC,
                p.product_id DESC
            LIMIT 20
            """;

        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {

            ps.setString(1, queryText);
            ps.setInt(2, authenticatedTenantId);
            ps.setString(3, country);
            ps.setTimestamp(4, Timestamp.from(asOf));
            ps.setTimestamp(5, Timestamp.from(asOf));
            ps.setBigDecimal(6, minPrice);
            ps.setBigDecimal(7, maxPrice);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    System.out.println(
                        rs.getLong("product_id")
                        + ": "
                        + rs.getString("name")
                    );
                }
            }
        }
    }
}
```

### 33.1. Never Accept Tenant ID from Untrusted Request Bodies

`authenticatedTenantId` must come from the server's security context after authentication and authorization.

### 33.2. Bind Values, Never Concatenate Strings

`setString`, `setInt`, `setBigDecimal`, and `setTimestamp` send values separately from SQL structure. Never concatenate `queryText` into SQL literals or regex expressions.

### 33.3. Validate Inputs Before Querying

Validate:

- Keyword length and empty-query behavior.
- Min/max prices and currency.
- Country code against a business allowlist.
- Maximum number of category/tag filters.
- Maximum page size.
- Server-controlled timestamps.

### 33.4. When Dynamic Query Building Is Needed

Append only **fixed, allowlisted SQL clauses** managed by the application, such as:

```java
StringBuilder sql = new StringBuilder(
    "SELECT product_id, name " +
    "FROM search_rules_lab.products " +
    "WHERE tenant_id = ? " +
    "AND status = 'PUBLISHED' " +
    "AND deleted_at IS NULL"
);

if (categoryId != null) {
    sql.append(" AND category_id = ?");
}
```

Then bind the corresponding parameter values. This snippet illustrates fragment assembly only; real endpoints must retain seller, stock, time window, country, and text matching. Ensure no builder branch ever drops mandatory tenant or security clauses.

### 33.5. Never Accept Raw ORDER BY Expressions from Users

Column identifiers and SQL keywords cannot be bound as parameter values. Map sort options through an allowlist:

```text
sort=relevance -> ORDER BY text_rank DESC, product_id DESC
sort=newest    -> ORDER BY created_at DESC, product_id DESC
sort=price_asc -> ORDER BY price ASC, product_id ASC
```

Never interpolate a raw request `sort` string directly into SQL.

## 34. Consistency and Concurrency: Search Is Not Checkout

### 34.1. Search Results Are a Point-in-Time Snapshot

At time T1, a product has `stock_qty = 1`.

- User A searches and sees the item.
- User B purchases it, dropping stock to `0`.
- User A clicks buy at T2.

The search result from T1 no longer reflects inventory at T2.

### 34.2. Checkout Needs Transactional Invariant Protection

Illustrative check keeping stock non-negative:

```sql
BEGIN;

UPDATE search_rules_lab.products
SET stock_qty = stock_qty - 1
WHERE product_id = 1001
  AND tenant_id = 2
  AND status = 'PUBLISHED'
  AND deleted_at IS NULL
  AND stock_qty >= 1
RETURNING product_id, stock_qty;

-- Complete the order only if UPDATE returns exactly 1 row
-- while also checking other business rules.
-- COMMIT or ROLLBACK depending on outcome.
ROLLBACK;
```

This is an **experiment**, not a full checkout flow. It demonstrates conditional atomic stock verification at write time.

### 34.3. Never Read stock_qty Separately Then Update Unconditionally

Two concurrent transactions can both read `stock_qty = 1` and both attempt to purchase, causing overselling unless guarded by conditional updates, locking, or serializable/appropriate transaction design.

### 34.4. Prices and Permissions Must Also Be Re-Verified

Prices, promotions, seller status, purchase limits, country rules, and authorization can change between search and checkout.

### 34.5. Never Lock Search Results in Bulk

Running `SELECT ... FOR UPDATE` over thousands of rows in a public search endpoint causes severe lock contention. Order reservation belongs to a separate workflow from read-only search.

## 35. Testing Against a Business Rule Matrix

A query can return the right top 20 on the happy path while breaking on edge cases.

| Case | Expectation |
| --- | --- |
| Keyword match in another tenant | Must not appear |
| Product in `DRAFT` | Must not appear in public search |
| Product `BLOCKED` | Must not appear |
| Product with `deleted_at` set | Must not appear |
| Unverified seller | Must not appear |
| Suspended seller | Must not appear |
| Future `published_at` | Must not appear |
| `available_until = as_of` | Must not appear if using `>` |
| `available_until IS NULL` | Treated as no end date per rule |
| `stock_qty = 0` | Must not appear if in-stock is required |
| Different `country_code` | Must not appear |
| Price below min / above max | Must not appear |
| Two matching tags on one product | Product must not appear twice |
| `discount` tag filter | Only products carrying `discount` |
| FTS matches description, not name | Appears if business-eligible |
| Keyword containing `%` or `_` | Literal behavior if UI specifies literal |
| Empty keyword | Follows explicit policy; never unbounded scan |
| All top raw matches hidden | Search still surfaces lower-ranked eligible items |
| Equal relevance scores | Stable ID tie-breaker |
| Counts and facets | Never include out-of-scope records |
| Data changes between pages | Obeys defined consistency policy |

### 35.1. Verify Tenant Isolation with Identical Keywords

Seed two identically named products across two tenants, query as Tenant A, and assert **Tenant B's product never appears**.

### 35.2. Test OR Precedence

Seed a product in Tenant B whose keyword appears only in `description`. A buggy `tenant AND name_match OR description_match` query fails this test immediately by leaking Tenant B's item.

### 35.3. Test LIMIT-Before-Filter

Seed over 20 high-relevance ineligible matches alongside 20 lower-relevance eligible matches. A valid query must return all 20 eligible items rather than filtering down the raw top 20.

### 35.4. Test Multiple Tags

Include a product carrying both `premium` and `discount`. Listings must show it once, and total counts must count it once.

### 35.5. Test Timezone Boundaries

Verify items published right at UTC instants corresponding to local midnight against `as_of` and date-range filters.

## 36. System Observability and Cost Control

In production, tuning search endpoints requires live telemetry:

- p50, p95, p99 latency.
- Request rate.
- Rows returned per query.
- Distribution of short vs. long queries.
- Ratio of FTS vs. `ILIKE` vs. regex queries.
- Common filter combinations.
- Hot vs. cold tenants.
- Buffer hits/reads, CPU, and I/O.
- Planning time and execution time.
- Sizes of GIN and B-tree indexes.
- Query cancellations and timeouts.
- Concurrent active search queries.
- Autovacuum and `ANALYZE` health.
- Relevance and ranking quality.

### 36.1. `pg_stat_statements` Helps Spot Hot Queries

When installed and enabled:

```sql
SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Columns and permissions vary by PostgreSQL version. `pg_stat_statements` aggregates normalized queries rather than logging every raw keyword, tenant, and country separately.

### 36.2. Build Representative Benchmark Suites

Include:

- Rare vs. high-frequency keywords.
- 1–2 characters vs. 10 characters vs. multi-word phrases.
- Small vs. multi-million-row tenants.
- With and without category filters.
- Narrow vs. wide price ranges.
- Common vs. rare tags.
- Relevance, newest, and price sort orders.
- First page vs. deep pages.
- Full seller joins plus stock and date predicates.
- Concurrent request load, not single-threaded runs alone.

### 36.3. `statement_timeout`

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';

-- Execute the SELECT search query under test inside this transaction.

ROLLBACK;
```

Timeouts abort runaway queries, though **they do not optimize queries on their own**. With connection pools, keep transaction boundaries and cleanup disciplined.

### 36.4. Rate Limiting and Debouncing

Autocomplete should never hammer the database on **every keystroke** without debouncing, minimum input length, pagination, and concurrency limits.

### 36.5. Never Log Sensitive Keywords or Tenant Details Recklessly

Search terms may carry personal or confidential data. Observe pattern length, query class, result count, or salted hashes rather than dumping raw inputs verbatim into logs.

## 37. Common Mistakes

| Misconception or Mistake | Consequence / Correct Understanding |
| --- | --- |
| “Matching the keyword means displayable” | Authorization and eligibility must also pass |
| Filtering tenant only in the UI | Leaks data through APIs, logs, and caches |
| `tenant AND title OR description` | `OR` escapes tenant scope |
| Applying `LIMIT` before business filters | Returns fewer than N valid hits |
| Joining tags before `LIMIT` | One product can span multiple rows |
| Using `DISTINCT` to patch all duplicates | Adds sort/hash overhead and hides cardinality bugs |
| Counting raw FTS hits | Includes invisible and unauthorized items |
| Counting after `LIMIT 20` | Counts only the current page |
| Computing category facets across all tenants | Leaks cross-tenant counts |
| A product with 3 tags adds 3 to product total | Distinguish product counts from tag counts |
| `status = 'PUBLISHED'` is enough | Seller, soft delete, time window, stock, and region also matter |
| Having FTS GIN makes every query fast | Common keywords, joins, filters, and sorts remain expensive |
| Having a tenant B-tree makes GIN redundant | Each index serves different predicate sets |
| Trigram GIN speeds up 2-char patterns | Often lacks selective trigrams |
| `ILIKE` strips accents | No universal accent-folding guarantee |
| `websearch_to_tsquery` understands any language | Behavior depends on text search config and tokenization |
| Naming a CTE `eligible` secures data | Does not replace RLS or authorization |
| `WHERE` evaluates top-to-bottom | The planner reorders evaluation |
| Generic plans always match `status=$1` partial indexes | Planner cannot assume `$1` is always `'PUBLISHED'` |
| Partial indexes with `now()` work well | Time-based predicates are not immutable |
| Indexing every column helps | Increases WAL, write overhead, storage, and maintenance |
| Deep `OFFSET` is free thanks to `LIMIT` | Still scans and discards preceding rows |
| Ties in rank don't need tie-breakers | Page order can shift across requests |
| Reusing cursors across different keywords | Breaks keyset pagination |
| `COUNT(*) OVER()` is always cheap | Must inspect all matches, disabling early exit |
| `stock > 0` in search guarantees fulfillment | Checkout must re-verify inside a transaction |
| Bind parameters escape `%` and `_` | False; `LIKE` wildcards keep wildcard semantics |
| `SET LOCAL` persists outside a transaction | Requires an active transaction |
| `EXPLAIN ANALYZE` does not run DML | It executes DML and mutates data |
| Any `Seq Scan` is a bug | Can be optimal for small tables or low selectivity |
| High relevance overrides `BLOCKED` status | Mandatory eligibility always takes precedence |

## 38. Practice Exercises with Solutions

All exercises refer to `search_rules_lab`. Run DDL only once in the lab; any abbreviated query highlighting a single aspect must retain all mandatory filters in a real endpoint.

### Exercise 1. Why isn't search simply `@@`?

**Answer:** `@@` only tests lexeme matching. Public search must also enforce tenant scope, permissions, status, seller validity, soft deletion, stock, effective dates, region, and user filters.

### Exercise 2. Find products matching PostgreSQL for tenant 2

```sql
SELECT product_id, name
FROM search_rules_lab.products
WHERE tenant_id = 2
  AND search_vector @@
      websearch_to_tsquery('simple', 'PostgreSQL');
```

**Answer:** this returns tenant-scoped text matches; making it public still requires full eligibility filters.

### Exercise 3. Why can a DRAFT product match a keyword?

**Answer:** its `name` and `description` tokens exist in `search_vector`; FTS does not check business `status` implicitly.

### Exercise 4. How are soft-deleted rows filtered out?

```sql
AND deleted_at IS NULL
```

**Answer:** use `IS NULL`, never `= NULL`.

### Exercise 5. Is the sale end window inclusive or exclusive?

```sql
AND (
    available_until IS NULL
    OR available_until > $as_of
)
```

**Answer:** the example uses an exclusive upper bound: once time reaches `as_of`, the product is expired.

### Exercise 6. Write the verified-seller filter

**Answer:** join on `(tenant_id, seller_id)` and require `s.is_verified AND s.suspended_at IS NULL`.

### Exercise 7. Why can joining sellers solely on seller_id without tenant_id be dangerous?

**Answer:** in multi-tenant schemas where seller IDs might overlap across tenants, joining without `tenant_id` can associate a product with the wrong tenant's seller. Even with the lab's composite FK, writing the full relationship key is good practice.

### Exercise 8. Identify the bug in `tenant = 2 AND name ILIKE X OR description ILIKE X`

**Answer:** SQL parses the `description` branch outside the tenant filter, potentially exposing other tenants' items.

### Exercise 9. Fix operator precedence

```sql
WHERE tenant_id = 2
  AND (
      name ILIKE '%PostgreSQL%'
      OR description ILIKE '%PostgreSQL%'
  )
```

**Answer:** wrap the `OR` branches in parentheses and retain all remaining mandatory filters.

### Exercise 10. Why is taking the top 20 before filtering status wrong?

**Answer:** ineligible rows among those 20 get dropped afterward, returning fewer than 20 valid items even when eligible lower-scoring rows exist.

### Exercise 11. Does a MATERIALIZED CTE replace authorization?

**Answer:** no; it is only a planning/execution construct and neither enforces permissions nor replaces RLS.

### Exercise 12. If a product has two tags, how many rows can a direct JOIN return?

**Answer:** two rows for that product if both tags match; use `EXISTS` or purposeful aggregation instead.

### Exercise 13. Filter products carrying tag discount

```sql
SELECT p.product_id
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND EXISTS (
      SELECT 1
      FROM search_rules_lab.product_tags AS t
      WHERE t.product_id = p.product_id
        AND t.tag = 'discount'
  );
```

**Answer:** `EXISTS` keeps one row per product.

### Exercise 14. How do you require both premium and discount?

**Answer:** combine two `EXISTS` clauses with `AND` (or aggregate explicitly for “has all tags”).

### Exercise 15. How do you require either of the two tags?

**Answer:** a single `EXISTS` with `t.tag = ANY(ARRAY['premium','discount'])` works cleanly.

### Exercise 16. Why is NOT EXISTS helpful when excluding a tag?

**Answer:** it expresses anti-join semantics clearly and avoids three-valued `NULL` traps inherent in `NOT IN`.

### Exercise 17. Filter for in-stock items only

**Answer:** add `AND p.stock_qty > 0` to the `WHERE` clause, while still re-verifying stock at checkout.

### Exercise 18. Why can search stock figures be stale?

**Answer:** another transaction can purchase the item after the search snapshot; search neither locks nor reserves inventory.

### Exercise 19. Use FTS to score relevance

```sql
SELECT
    product_id,
    ts_rank_cd(
        search_vector,
        websearch_to_tsquery('simple', 'PostgreSQL')
    ) AS score
FROM search_rules_lab.products
WHERE search_vector @@
      websearch_to_tsquery('simple', 'PostgreSQL');
```

**Answer:** `@@` filters and `ts_rank_cd` scores; a public query still needs full business predicates.

### Exercise 20. Does FTS automatically match mid-word substrings?

**Answer:** no. FTS matches lexemes; substring containment typically requires `ILIKE`/trigrams.

### Exercise 21. Escape an underscore in a literal ILIKE query

**Answer:** bind `%pg!_trgm%` and write `ILIKE $1 ESCAPE '!'`.

### Exercise 22. Do bind parameters automatically make `%` literal?

**Answer:** no; pattern semantics still apply. Binding stops SQL injection but does not escape `LIKE` wildcards.

### Exercise 23. What must you watch out for when combining FTS and ILIKE with OR?

**Answer:** wrap the `OR` in parentheses inside mandatory tenant/eligibility filters, and define how items matching only one branch are scored.

### Exercise 24. Why can't high relevance surface a BLOCKED product?

**Answer:** blocked items must be excluded before ranking regardless of text or business score.

### Exercise 25. Why does ORDER BY need a tie-breaker?

**Answer:** items sharing the exact same score can appear in unstable order; `product_id` ensures deterministic ordering within a snapshot.

### Exercise 26. What is the problem with OFFSET 100000?

**Answer:** PostgreSQL still has to scan and discard many preceding rows, and concurrent writes can cause duplicates or skips between pages.

### Exercise 27. Should keyset cursors bind to keywords and filters?

**Answer:** yes; a relevance-ordered cursor depends on the exact query and filters and must never be reused across differing requests.

### Exercise 28. Why must COUNT run over eligible matches only?

**Answer:** raw FTS counts include other tenants, drafts, blocked, or expired items, misreporting totals to the UI and leaking restricted counts.

### Exercise 29. Is `COUNT(*) OVER()` always free?

**Answer:** no; computing the window total forces scanning all matching rows and disables early termination from `LIMIT`.

### Exercise 30. Should category facets be computed after LIMIT?

**Answer:** no when reporting facets for the whole search result; only compute after `LIMIT` if the UI intentionally asks for “facets on this page only”.

### Exercise 31. What is a self-excluding facet?

**Answer:** computing category facet counts with **all other filters preserved** while omitting **only the active category filter**, respecting tenant, eligibility, and keyword rules.

### Exercise 32. Can you drop the tenant filter from facets to get “complete numbers”?

**Answer:** no. That exposes data counts belonging to unauthorized tenants.

### Exercise 33. What does a GIN index on search_vector help with?

**Answer:** finding candidate rows by lexemes via `@@`; it does not check seller status, stock, or region on its own.

### Exercise 34. When do composite B-trees on tenant/category/price help?

**Answer:** when business filters are selective; column order must match actual equality and range query patterns.

### Exercise 35. When should you consider a partial index for public products?

**Answer:** when many queries hardcode `status = 'PUBLISHED' AND deleted_at IS NULL` and a smaller index pays off; never treat it as an authorization boundary.

### Exercise 36. Does a generic plan with `status=$1` automatically use a published-only partial index?

**Answer:** no, because it cannot assume `$1` is always `'PUBLISHED'`; hardcoding the constant makes partial-index selection possible.

### Exercise 37. Why avoid `now()` inside partial index predicates?

**Answer:** time-dependent eligibility changes without row updates, violating index immutability requirements.

### Exercise 38. Why can Seq Scan still beat a GIN index?

**Answer:** when a keyword matches a high percentage of rows or other filters dominate cost, sequential scanning can be cheaper overall.

### Exercise 39. Does RLS replace business eligibility rules?

**Answer:** not automatically. Tenant RLS enforces tenant boundaries while queries/policies must still check public status, seller verification, stock, dates, and region.

### Exercise 40. Can you trust `SET app.tenant_id` sent directly by a client?

**Answer:** no. Tenant context must be authenticated and protected server-side or via DB roles; custom GUCs writable by untrusted sessions are not a security boundary.

### Exercise 41. Why do search queries need timezone and locale awareness?

**Answer:** effective date windows and regional availability have business semantics—especially local calendar dates—so local dates must never be assumed equal to UTC.

### Exercise 42. Why shouldn't raw `SORT` strings from HTTP requests go into ORDER BY?

**Answer:** column names and sort keywords cannot be bound as parameter values; validate against an allowlist.

### Exercise 43. May a dynamic query builder drop `status` because “the UI hides drafts”?

**Answer:** no. Mandatory filters belong in every query variant regardless of UI behavior.

### Exercise 44. Why check `Rows Removed by Filter` in EXPLAIN?

**Answer:** it shows how many scanned candidates failed remaining predicates, signaling whether a better access path or index is needed.

### Exercise 45. Does `cost=500` mean 500 ms?

**Answer:** no; those are planner cost units. Inspect actual execution time in `EXPLAIN ANALYZE` for wall-clock timing.

### Exercise 46. Why measure p95/p99 latency and concurrency?

**Answer:** rare keywords can look fast in isolation while high-frequency terms and concurrent traffic drive tail latency spikes.

### Exercise 47. Why re-check prices at checkout?

**Answer:** prices, promotions, or listing rights can change between browsing and buying. Checkout requires transactional invariants.

### Exercise 48. Write a checklist for shipping a correct search endpoint

**Suggested answer:**

1. Separate authorization, eligibility, user filters, text matching, and ranking clearly.
2. Source tenant ID solely from verified auth context; add DB roles/RLS where appropriate.
3. Parenthesize `OR` keyword branches inside mandatory filters across every branch.
4. Filter before `ORDER BY`/`LIMIT`; never post-filter a raw top-K slice.
5. Use `EXISTS` for one-to-many membership checks.
6. Align filtering semantics across listings, total counts, facets, and suggestions.
7. Add FTS/business/partial/trigram indexes justified by workload; avoid redundant indexes.
8. Inspect `EXPLAIN ANALYZE BUFFERS` across selective and broad keywords/filters.
9. Bind parameters, allowlist sorts, and escape `LIKE` wildcards.
10. Cap keyword lengths, page sizes, timeouts, rate limits, and redact sensitive logs.
11. Test tenant isolation plus blocked/draft/deleted/expired/out-of-stock edge cases.
12. Re-verify price and inventory at checkout.

## 39. End-to-End Benchmark Workflow

Once the lab schema and indexes are in place:

### Step 1. Count Raw Text Matches

```sql
SELECT COUNT(*)
FROM search_rules_lab.products
WHERE search_vector @@
      websearch_to_tsquery('simple', 'PostgreSQL');
```

This measures raw keyword hits—**not viewable results**.

### Step 2. Count Tenant-Scoped Matches

```sql
SELECT COUNT(*)
FROM search_rules_lab.products
WHERE tenant_id = 2
  AND search_vector @@
      websearch_to_tsquery('simple', 'PostgreSQL');
```

Compare counts to observe how tenant scoping narrows candidates.

### Step 3. Count Fully Eligible Matches

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'simple', 'PostgreSQL'
    ) AS tsq
)
SELECT COUNT(*)
FROM search_rules_lab.products AS p
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
CROSS JOIN q
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.stock_qty > 0
  AND p.country_code = 'VN'
  AND p.published_at <=
      timestamptz '2026-11-14 00:00:00+00'
  AND (
      p.available_until IS NULL
      OR p.available_until >
         timestamptz '2026-11-14 00:00:00+00'
  )
  AND s.is_verified
  AND s.suspended_at IS NULL
  AND p.search_vector @@ q.tsq;
```

### Step 4. Capture the Actual Plan for the Listing Query

Take the query from Section 7, add `EXPLAIN (ANALYZE, BUFFERS)`, and record scan types, joins, sorts, rows, buffers, and timings.

### Step 5. Vary Filter Selectivity

- No category filter, wide price range.
- `category_id = 2`, narrow price range.
- Tag `discount`.
- Country `VN` vs `US`.
- High-frequency keyword such as `database`.
- Selective keyword such as `postgresql`.
- Zero-hit keyword.

Observe how the planner shifts access paths.

### Step 6. Test Justified Index Changes

For example, test a partial index for published/active rows or a trigram index if `ILIKE` substring matching is required. Avoid duplicate indexes differing only in name.

### Step 7. Re-Measure and Evaluate Systemwide

Record side by side:

| Metric | Before | After |
| --- | --- | --- |
| SQL / filters | Exact query with bind values | Same workload |
| Actual rows | Measured | Measured |
| Plan nodes | Measured | Measured |
| Buffer hits/reads | Measured | Measured |
| Planning Time | Measured | Measured |
| Execution Time | Measured across runs | Measured across runs |
| Index size | Measured | Measured |
| Insert/update latency | Measured | Measured |
| Result correctness | Matrix suite | Must remain identical |
| Tenant isolation | Security tests | Zero regressions |
| p95 / p99 | Measured | Measured |

If a query runs faster yet drops eligible products or leaks cross-tenant records, the change is **unacceptable**.

## 40. Implementation Checklist

| Question | Action |
| --- | --- |
| Where does the current tenant come from? | Strictly from trusted auth context |
| Are RLS and DB permissions aligned? | Test actual application roles and pooling |
| Are all query variants protected? | Keep mandatory predicates everywhere |
| Are `OR` branches grouped? | Wrap correctly in parentheses |
| Are `DRAFT`/`HIDDEN`/`BLOCKED` excluded? | Filtered out of public search |
| Are soft deletes excluded? | `deleted_at IS NULL` |
| Is seller verification enforced? | `JOIN`/`EXISTS` using tenant-scoped keys |
| Are suspended sellers excluded? | Filtered from results |
| Are unreleased items hidden? | Compare `published_at` against `as_of` |
| Are expired items hidden? | Enforce exclusive end time and `NULL` handling |
| Is stock threshold handled? | Filter display; re-verify at checkout |
| Are country/region rules applied? | Show only items sellable there |
| Are currency and prices consistent? | Never compare differing currencies directly |
| Could tag filters duplicate rows? | Use `EXISTS` or intentional aggregation |
| Does FTS config match the language? | Test tokenization and lexemes |
| Could `LIKE` input contain wildcards? | Escape when matching literals |
| Are `ILIKE` contains/regex used? | Evaluate trigram support and query cost |
| Are empty or tiny keywords handled? | Apply explicit policy guards |
| Are ranking boosts bounded? | Never override business eligibility |
| Is ordering deterministic? | Include a unique tie-breaker |
| Is `LIMIT` applied after filtering? | Never slice raw top-K first |
| Do count and list share filters? | Keep semantics aligned |
| Could facets leak cross-tenant data? | Apply identical authorization scope |
| Are self-excluding facets specified? | Drop only the targeted facet filter |
| Is deep pagination expected? | Consider keyset pagination |
| Can rapid UI typing flood queries? | Add debouncing and rate limits |
| Are text search indexes present? | Appropriate `tsvector` GIN or trigram |
| Are business indexes present? | Workload-justified composite/partial B-trees |
| Are duplicate indexes present? | Audit write and storage overhead |
| Are statistics current? | Run `ANALYZE` per workload |
| Was `EXPLAIN` inspected realistically? | Check rows, buffers, joins, and sorts |
| Are generic prepared plans tested? | Test across skewed parameters |
| Are timeouts and quotas set? | Guard against expensive regex/search |
| Are PII and sensitive terms protected? | Redact or aggregate in logs |
| Is checkout concurrency handled? | Transactional stock and price re-checks |
| Is correctness tested? | Auth and business-case matrix |
| Is canary/rollback planned? | Monitor before and after deployment |

## 41. Summary

Combining business rules with search results in PostgreSQL demands **both correctness and performance**:

1. **Start with access control.** Tenant scope, ACLs, and RLS are mandatory boundaries, not optional UI filters.
2. **Express eligibility explicitly.** Public status, soft deletes, verified sellers, effective dates, stock, and region must match documented policy.
3. **Apply text matching on top.** FTS `@@`, `ILIKE`, and trigrams serve different search semantics.
4. **Parenthesize `OR` carefully.** Unwrapped `OR` clauses easily bypass tenant and status filters.
5. **Never `LIMIT` before eligibility.** Top N must always mean the top N among **eligible matches**.
6. **Prevent row multiplication from joins.** Use `EXISTS` for tag or membership filtering.
7. **Synchronize counts, facets, and listings.** Never count raw unrestricted matches or count after `LIMIT` when total hits are required.
8. **Ranking never overrides business rules.** High text relevance must never expose a blocked item.
9. **Keep pagination deterministic.** Use total ordering and context-bound cursors/snapshots.
10. **Indexes are tools, not magic.** GIN for text, B-tree for business keys, trigrams for substrings, partial indexes for static filters—always verify with measurements.
11. **The planner chooses evaluation order.** `WHERE` clause order is never a security boundary.
12. **Keep SQL safe.** Bind parameters, escape `LIKE` literals, allowlist `ORDER BY`, and read tenant from auth context.
13. **Search is only a snapshot.** Re-verify prices, inventory, and eligibility inside the checkout transaction.
14. **Measure the whole system.** `EXPLAIN`, buffers, latency, write overhead, and tenant-isolation tests all count.

Final mental model:

```text
User query + authenticated context
                |
                v
   Mandatory authorization scope
                |
                v
  Business eligibility + user filters
                |
                v
      Full-text / substring matches
                |
                v
      Relevance + business ranking
                |
                v
        Stable ORDER BY + LIMIT
                |
                v
          Visible result page

Same scope and filters
       |
       +--> total matches
       |
       +--> category/tag facets per UX
```

**Core principle:** a search query succeeds only when it returns **the exact rows the user is authorized to view, satisfying all business rules, in deterministic order, with accurate counts**, within acceptable latency and resource cost. Simply making `@@` or `ILIKE` faster is never enough to build a trustworthy search endpoint.
