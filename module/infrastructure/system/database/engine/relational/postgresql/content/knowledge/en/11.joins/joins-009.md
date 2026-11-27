# UNION, UNION ALL, INTERSECT, and EXCEPT in PostgreSQL

## 1. Four Operations for Combining Query Results

When working across multiple data sources, a system often needs to answer different questions:

- Which product codes **appear in at least one source**?
- Which codes **exist in both sources**?
- Which codes does source A have **that do not yet exist in source B**?
- If a code appears twice in A and three times in B, how many are shared or left over?
- Can we merge event logs from two systems **without losing events that happen to have identical content**?

PostgreSQL supports set operations on **results of queries with compatible structures**:

| Operator | Meaning | Duplicate Handling |
|---|---|---|
| `UNION` | Rows appearing in either or both sides | Removes duplicates |
| `UNION ALL` | All rows from both sides | Preserves every occurrence |
| `INTERSECT` | Rows common to both sides | Removes duplicates |
| `INTERSECT ALL` | Common rows according to occurrence count | Keeps minimum count |
| `EXCEPT` | Rows in left side but not in right side | Removes duplicates |
| `EXCEPT ALL` | Remaining left rows after subtracting right occurrences | Keeps surplus count |

Key point: these operators compare **all selected columns by position**, without inferring primary or business keys. If you select only `code`, you compare codes. If you select `code, category, qty`, you compare triples.

Lesson objectives:

1. Understand **sets** vs. **multisets (bags)** in SQL.
2. Correctly write `UNION`, `UNION ALL`, `INTERSECT`, `EXCEPT`, and their `ALL` variants.
3. Explain how `NULL`, duplicates, and data types are handled.
4. Use parentheses, `ORDER BY`, and `LIMIT` with the right scope.
5. Distinguish set operations from `JOIN`, `NOT EXISTS`, and `NOT IN`.
6. Apply them to finding deltas and performing two-way data reconciliation.
7. Read `EXPLAIN` and know when to optimize.

> The creation and loading commands in this lesson should be run only in a practice database with appropriate privileges, never in production without a proper process.

---

## 2. Sets vs. Multisets

### 2.1. Sets Contain No Repeated Elements

In set theory:

~~~text
A = {A, B, C}
B = {B, C, D}

A union B     = {A, B, C, D}
A intersect B = {B, C}
A minus B     = {A}
~~~

In SQL, an element is **a result row** consisting of the selected columns. Two rows must match across every corresponding value to be treated as duplicates for deduplication.

### 2.2. Multisets Preserve Occurrence Counts

SQL routinely returns multiple rows with identical values:

~~~text
Source A: [A, B, B, C]
Source B: [B, B, B, D]
~~~

Here B appears twice in A and three times in B. `UNION ALL` keeps **five** Bs; `UNION` keeps **one**; `INTERSECT ALL` keeps **two** Bs; `INTERSECT` keeps **one**.

### 2.3. Multiplicity Formulas

Let `a(x)` be how many times row `x` appears in the left result and `b(x)` be how many times it appears in the right result.

| Operation | Output Count of x |
|---|---|
| `UNION ALL` | `a(x) + b(x)` |
| `UNION` | 1 if either side has x, else 0 |
| `INTERSECT ALL` | `min(a(x), b(x))` |
| `INTERSECT` | 1 if both sides have x, else 0 |
| `EXCEPT ALL` | `max(a(x) - b(x), 0)` |
| `EXCEPT` | 1 if left has x and right does not, else 0 |

Note: `EXCEPT` is **directional**. `A EXCEPT B` can be completely different from `B EXCEPT A`.

---

## 3. Preparing Practice Data

Create a dedicated schema so other tables are untouched:

~~~sql
CREATE SCHEMA IF NOT EXISTS setops_lab;

CREATE TABLE setops_lab.source_a (
    seq INTEGER PRIMARY KEY,
    code TEXT,
    category TEXT,
    qty INTEGER
);

CREATE TABLE setops_lab.source_b (
    seq INTEGER PRIMARY KEY,
    code TEXT,
    category TEXT,
    qty INTEGER
);
~~~

`seq` is a per-source ID. `code` is the comparison code. Both tables intentionally omit `UNIQUE(code)` because a code can appear multiple times.

Source A:

~~~sql
INSERT INTO setops_lab.source_a (seq, code, category, qty) VALUES
    (1, 'A', 'hardware', 10),
    (2, 'B', 'software', 20),
    (3, 'B', 'software', 20),
    (4, 'C', 'hardware', 30),
    (5, 'D', NULL, NULL),
    (6, NULL, 'unknown', NULL),
    (7, 'E', 'service', 0);
~~~

Source B:

~~~sql
INSERT INTO setops_lab.source_b (seq, code, category, qty) VALUES
    (101, 'B', 'software', 20),
    (102, 'B', 'software', 20),
    (103, 'B', 'software', 20),
    (104, 'C', 'hardware', 30),
    (105, 'F', 'hardware', 40),
    (106, 'D', NULL, NULL),
    (107, NULL, 'unknown', NULL),
    (108, NULL, 'unknown', NULL),
    (109, 'G', 'service', 50);
~~~

Check row counts:

~~~sql
SELECT 'A'::text AS source_name, COUNT(*) AS row_count
FROM setops_lab.source_a
UNION ALL
SELECT 'B'::text AS source_name, COUNT(*) AS row_count
FROM setops_lab.source_b
ORDER BY source_name;
~~~

The result is **7 rows in A** and **9 rows in B**. Once INSERTs have been run, do not re-run them on the same tables or `seq PRIMARY KEY` will fail.

### 3.1. Code Frequencies in Both Sources

~~~sql
SELECT code, COUNT(*) AS frequency
FROM setops_lab.source_a
GROUP BY code
ORDER BY code NULLS LAST;
~~~

Source A has A:1, B:2, C:1, D:1, E:1, NULL:1.

~~~sql
SELECT code, COUNT(*) AS frequency
FROM setops_lab.source_b
GROUP BY code
ORDER BY code NULLS LAST;
~~~

Source B has B:3, C:1, D:1, F:1, G:1, NULL:2.

These frequencies serve as the reference to verify the `ALL` operations.

---

## 4. UNION: Combine and Deduplicate

~~~sql
SELECT code FROM setops_lab.source_a
UNION
SELECT code FROM setops_lab.source_b
ORDER BY code ASC NULLS LAST;
~~~

Result:

~~~text
A
B
C
D
E
F
G
NULL
~~~

There are **8 distinct rows**. Even though B appears multiple times in both sources, only one B is kept.

### 4.1. UNION Defaults to DISTINCT

`UNION` and `UNION DISTINCT` have the exact same semantics: deduplicate. PostgreSQL guarantees no output order without a trailing `ORDER BY`; incidental alphabetical ordering is not a SQL guarantee.

### 4.2. Deduplication Across the Entire Row

Two rows `(B,software,20)` and `(B,software,25)` differ when selecting three columns, yet represent the same code when selecting only `code`.

~~~sql
SELECT code, category, qty
FROM setops_lab.source_a
UNION
SELECT code, category, qty
FROM setops_lab.source_b
ORDER BY code NULLS LAST, category NULLS LAST, qty NULLS LAST;
~~~

The definition of **duplicate row** depends on the selected column list. Do not mindlessly include `seq` or `updated_at` when you only want a unique list of codes.

### 4.3. Business Duplicates vs. Technical Duplicates

Strings `'abc'`, `'ABC'`, and `'abc '` may represent the same code in business logic yet will not automatically collapse in every PostgreSQL setup.

If codes are case-insensitive and whitespace-trimmed:

~~~sql
SELECT upper(btrim(code)) AS normalized_code
FROM setops_lab.source_a
UNION
SELECT upper(btrim(code)) AS normalized_code
FROM setops_lab.source_b
ORDER BY normalized_code NULLS LAST;
~~~

Apply normalization only after verifying business rules, collation, and Unicode handling.

---

## 5. UNION ALL: Combine While Preserving All Rows

~~~sql
SELECT code FROM setops_lab.source_a
UNION ALL
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

There are **16 rows**, equal to 7 + 9. Frequencies:

| code | Count in UNION ALL |
|---|---:|
| A | 1 |
| B | 5 |
| C | 2 |
| D | 2 |
| E | 1 |
| F | 1 |
| G | 1 |
| NULL | 3 |

### 5.1. When to Use It

- Merging event logs, transactions, or independently processed records.
- Combining data from partitions or sources that already have distinct ID schemes.
- Building an intermediate set for `GROUP BY` frequency counting.
- Preserving meaningful duplicate records without losing valid transactions.

Example when two real order tables exist:

~~~sql
SELECT 'web'::text AS channel, order_id, amount
FROM web_orders
UNION ALL
SELECT 'store'::text AS channel, order_id, amount
FROM store_orders;
~~~

This is illustrative SQL, not tables created in the lab. The `channel` label identifies where each order originated.

### 5.2. Why Is UNION ALL Usually Cheaper?

`UNION ALL` skips the deduplication step; PostgreSQL can simply concatenate branch outputs with an `Append` node or equivalent plan. `UNION` often requires `HashAggregate` or `Sort/Unique` to eliminate duplicates.

However, **pick the right semantics before optimizing**. If an API expects unique codes, switching to `UNION ALL` just for speed breaks correctness.

### 5.3. Preserving Source Provenance

~~~sql
SELECT
    'A'::text AS source_name,
    seq AS source_seq,
    code, category, qty
FROM setops_lab.source_a
UNION ALL
SELECT
    'B'::text AS source_name,
    seq AS source_seq,
    code, category, qty
FROM setops_lab.source_b
ORDER BY source_name, source_seq;
~~~

When `seq` is unique only within each source, the `(source_name,source_seq)` pair accurately distinguishes row provenance.

---

## 6. INTERSECT: The Common Rows

~~~sql
SELECT code FROM setops_lab.source_a
INTERSECT
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

Result has **4 distinct values**:

~~~text
B
C
D
NULL
~~~

### 6.1. Use Cases

- SKUs present in **both warehouses**.
- Customers appearing in **both CRM and billing**.
- Permissions granted in **both authorization sets**.
- Identical rows across two datasets for the compared columns.

`INTERSECT` removes duplicates by default; multiple occurrences of B in each source do not make B repeat in the output.

### 6.2. INTERSECT ALL: Multiset Intersection

~~~sql
SELECT code FROM setops_lab.source_a
INTERSECT ALL
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

Multiplicity formula:

~~~text
min(count_A(x), count_B(x))
~~~

Result:

~~~text
B
B
C
D
NULL
~~~

Total **5 rows**, since B has min(2,3)=2, C=1, D=1, and NULL has min(1,2)=1.

### 6.3. Do Not Confuse INTERSECT with INNER JOIN

A has two Bs and B has three Bs:

- `INTERSECT` → **1 B**.
- `INTERSECT ALL` → **2 Bs**.
- `INNER JOIN` on code → can produce **6 B pairs**.

JOIN pairs every matching row combination; `INTERSECT ALL` takes the **minimum** common occurrence count without multiplying combinations.

---

## 7. EXCEPT: Rows Only on the Left Side

### 7.1. A Minus B

~~~sql
SELECT code FROM setops_lab.source_a
EXCEPT
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

Result: **A, E**.

### 7.2. B Minus A

~~~sql
SELECT code FROM setops_lab.source_b
EXCEPT
SELECT code FROM setops_lab.source_a
ORDER BY code NULLS LAST;
~~~

Result: **F, G**.

Set difference is **not commutative**. `A EXCEPT B` means "in A, not in B"; `B EXCEPT A` means "in B, not in A."

### 7.3. EXCEPT ALL Subtracts Occurrence Counts

~~~sql
SELECT code FROM setops_lab.source_b
EXCEPT ALL
SELECT code FROM setops_lab.source_a
ORDER BY code NULLS LAST;
~~~

Applying `max(count_B(x)-count_A(x),0)`, the result is:

~~~text
B
F
G
NULL
~~~

There are **4 rows**: one surplus B (3 vs. 2), one each for F and G, and one surplus NULL (2 vs. 1).

In the `A EXCEPT ALL B` direction:

~~~sql
SELECT code FROM setops_lab.source_a
EXCEPT ALL
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

only **A and E** remain.

### 7.4. When Do You Need EXCEPT ALL?

In reconciliation, two files might contain the **exact same set of distinct values** yet differ in repetition counts. For example:

~~~text
File 1: [B, B, C]
File 2: [B, B, B, C]
~~~

Both directions of `EXCEPT` return empty because the distinct sets are identical. Yet `File 2 EXCEPT ALL File 1` returns **one surplus B**.

`EXCEPT ALL` is valuable when each occurrence represents a distinct meaningful event, or when detecting duplicate file ingestion.

### 7.5. EXCEPT Does Not Automatically Detect Per-ID UPDATEs

If the same customer ID has a changed email, `EXCEPT` over `(ID, email)` returns one row only in the old snapshot and one row only in the new snapshot. It does not conclude those two rows are **the same customer updated**. Classifying INSERT/UPDATE/DELETE requires matching by business key and comparing attributes—typically via a FULL JOIN.

---

## 8. NULL in Set Operations

### 8.1. NULLs Are Treated as Equal for Deduplication

~~~sql
SELECT NULL::integer AS value
UNION
SELECT NULL::integer AS value;
~~~

Result: **1 NULL row**.

~~~sql
SELECT NULL::integer AS value
UNION ALL
SELECT NULL::integer AS value;
~~~

Result: **2 NULL rows**.

~~~sql
SELECT NULL::integer AS value
INTERSECT
SELECT NULL::integer AS value;
~~~

Result: **1 NULL row**.

~~~sql
SELECT NULL::integer AS value
EXCEPT
SELECT NULL::integer AS value;
~~~

Result: **0 rows**.

In set deduplication, intersection, and difference, two NULLs at the same column position are treated as **not distinct** for row comparison.

### 8.2. Yet NULL = NULL Is Not TRUE

~~~sql
SELECT NULL::integer = NULL::integer AS comparison_result;
~~~

Result is NULL (UNKNOWN). The rules of the `=` expression differ from duplicate comparison in set operations. Do not mistakenly conclude PostgreSQL changed SQL three-valued logic.

### 8.3. NULL Across Multiple Columns

~~~sql
SELECT 'D'::text AS code, NULL::integer AS qty
UNION
SELECT 'D'::text AS code, NULL::integer AS qty;
~~~

Only one tuple `('D',NULL)`.

~~~sql
SELECT 'D'::text AS code, NULL::integer AS qty
UNION
SELECT 'D'::text AS code, 0::integer AS qty;
~~~

Yields **two tuples**: `('D',NULL)` and `('D',0)`. NULL is not 0.

### 8.4. IS NOT DISTINCT FROM in JOIN Conditions

When you need NULL-safe equality inside a predicate:

```sql
a.code IS NOT DISTINCT FROM b.code
```

evaluates to TRUE when both are NULL or hold equal values. This helps in `NOT EXISTS` and `JOIN`, though it does not turn a JOIN into `INTERSECT ALL`.

---

## 9. Rules on Column Count, Position, and Data Types

### 9.1. Both Branches Must Have the Same Number of Columns

Valid:

~~~sql
SELECT code, category FROM setops_lab.source_a
UNION ALL
SELECT code, category FROM setops_lab.source_b;
~~~

Invalid:

~~~sql
SELECT code FROM setops_lab.source_a
UNION ALL
SELECT code, category FROM setops_lab.source_b;
~~~

PostgreSQL errors because the two queries do not have the same column count. This rule also applies to `INTERSECT` and `EXCEPT`.

### 9.2. Columns Match by Position, Not by Name

~~~sql
SELECT code, category FROM setops_lab.source_a
UNION ALL
SELECT category, code FROM setops_lab.source_b;
~~~

Because both columns are TEXT, the query runs, yet B's rows have **swapped column meanings**. PostgreSQL does not align columns by name; keep expressions in the exact same order across branches.

### 9.3. Corresponding Columns Must Share a Common Type

~~~sql
SELECT 1::integer AS value
UNION ALL
SELECT 2.5::numeric AS value;
~~~

PostgreSQL resolves a common numeric type. However, `INTEGER` and `DATE` have no sensible common type:

~~~sql
-- Intentionally invalid example:
SELECT 1::integer AS value
UNION
SELECT DATE '2026-01-01' AS value;
~~~

Never cast everything to `TEXT` just to "make it compile," because comparing dates or numbers as strings can produce wrong results. Choose data types matching business semantics.

### 9.4. Cast NULL Literals Explicitly When Needed

~~~sql
SELECT code, NULL::integer AS qty
FROM setops_lab.source_a
UNION ALL
SELECT code, qty
FROM setops_lab.source_b;
~~~

`NULL::integer` lets PostgreSQL resolve the placeholder column type cleanly, especially in nested operations.

### 9.5. Output Column Names Come from the First Branch

~~~sql
SELECT code AS product_code FROM setops_lab.source_a
UNION ALL
SELECT code AS sku FROM setops_lab.source_b
ORDER BY product_code;
~~~

The output column name is `product_code`, not `sku` from the second branch.

---

## 10. Avoid SELECT * When Comparing Business Keys

~~~sql
SELECT * FROM setops_lab.source_a
UNION
SELECT * FROM setops_lab.source_b;
~~~

Both lab tables have the same four columns, so the query runs. Yet these two rows:

~~~text
A: (seq=2, code=B, category=software, qty=20)
B: (seq=101, code=B, category=software, qty=20)
~~~

**are not duplicates**, because `seq` differs. When you only want the union or intersection of product codes, do not include source-local `seq` in the comparison.

`SELECT *` is also fragile if a table later adds or reorders columns, breaking the set operation or silently misaligning columns. Explicitly list projected columns consistently across all sources.

---

## 11. Operator Precedence: INTERSECT Before UNION/EXCEPT

In PostgreSQL:

1. `INTERSECT` has **higher** precedence than `UNION` and `EXCEPT`.
2. `UNION` and `EXCEPT` share the same precedence and associate **left to right**.
3. Use **parentheses** to express exact grouping whenever combining multiple operators.

Example:

~~~sql
SELECT 1 AS n
UNION
SELECT 1 AS n
INTERSECT
SELECT 2 AS n;
~~~

Equivalent to:

~~~text
{1} UNION ({1} INTERSECT {2})
= {1}
~~~

Result: **1 row with n=1**.

Whereas:

~~~sql
(
    SELECT 1 AS n
    UNION
    SELECT 1 AS n
)
INTERSECT
SELECT 2 AS n;
~~~

returns **0 rows**.

With `UNION` and `EXCEPT`:

~~~sql
SELECT 'x'::text AS item
UNION
SELECT 'y'::text AS item
EXCEPT
SELECT 'x'::text AS item;
~~~

is parsed as `({x} UNION {y}) EXCEPT {x}`, returning **y**.

Whereas:

~~~sql
SELECT 'x'::text AS item
UNION
(
    SELECT 'y'::text AS item
    EXCEPT
    SELECT 'x'::text AS item
);
~~~

returns **x and y**. Parentheses alter the outcome—they are not decorative.

When mixing `UNION ALL` with default `EXCEPT`, remember the outer `EXCEPT` still applies DISTINCT semantics; if you need to subtract **frequencies**, use `EXCEPT ALL`.

---

## 12. ORDER BY and LIMIT with Set Operations

### 12.1. A Trailing ORDER BY Sorts the Entire Result

~~~sql
SELECT code FROM setops_lab.source_a
UNION
SELECT code FROM setops_lab.source_b
ORDER BY code ASC NULLS LAST;
~~~

This `ORDER BY` sorts the **final combined result** after the union. Without `ORDER BY`, SQL guarantees no ordering.

### 12.2. Direct ORDER BY After a Set Operation Has Restrictions

PostgreSQL allows referencing **output column names or column positions** in the `ORDER BY` of a `UNION`/`INTERSECT`/`EXCEPT`:

~~~sql
SELECT code FROM setops_lab.source_a
UNION
SELECT code FROM setops_lab.source_b
ORDER BY 1 DESC NULLS LAST;
~~~

If you need a new expression like `lower(code)`, wrap it in a subquery:

~~~sql
SELECT code
FROM (
    SELECT code FROM setops_lab.source_a
    UNION
    SELECT code FROM setops_lab.source_b
) AS merged
ORDER BY lower(code) ASC NULLS LAST, code ASC NULLS LAST;
~~~

### 12.3. Per-Branch LIMIT Requires Parentheses

To take the 3 rows with highest `seq` from each source:

~~~sql
(
    SELECT seq, code FROM setops_lab.source_a
    ORDER BY seq DESC
    LIMIT 3
)
UNION ALL
(
    SELECT seq, code FROM setops_lab.source_b
    ORDER BY seq DESC
    LIMIT 3
)
ORDER BY seq DESC;
~~~

The query above returns at most **6 rows**.

Whereas:

~~~sql
SELECT seq, code FROM setops_lab.source_a
UNION ALL
SELECT seq, code FROM setops_lab.source_b
ORDER BY seq DESC
LIMIT 3;
~~~

returns only the **top 3 `seq` rows across both sources combined**.

An `ORDER BY` inside a parenthesized branch with `LIMIT` picks that branch's subset; the outer `ORDER BY` controls the **final display order**. Never apply an outer `LIMIT` without an outer `ORDER BY` when deterministic pagination is required.

---

## 13. Using CTEs to Name Intermediate Datasets

### 13.1. CTEs Separate Preparation from Comparison

~~~sql
WITH
a_codes AS (
    SELECT code
    FROM setops_lab.source_a
    WHERE code IS NOT NULL
),
b_codes AS (
    SELECT code
    FROM setops_lab.source_b
    WHERE code IS NOT NULL
)
SELECT code FROM a_codes
EXCEPT
SELECT code FROM b_codes
ORDER BY code;
~~~

This finds **non-NULL codes present only in A**, returning A and E.

Benefits of CTEs:

- Each source gets a clear name.
- Data can be normalized/filtered before comparing.
- Reduces repetition of complex subqueries.
- Easier to inspect each step in a data pipeline.

A CTE does not force PostgreSQL to materialize the full result into memory or a temp file. The planner may inline or materialize CTEs depending on version and conditions. Use `EXPLAIN` instead of guessing execution behavior.

### 13.2. Normalizing Data Consistently on Both Sides

~~~sql
WITH
a_codes AS (
    SELECT NULLIF(upper(btrim(code)), '') AS code
    FROM setops_lab.source_a
),
b_codes AS (
    SELECT NULLIF(upper(btrim(code)), '') AS code
    FROM setops_lab.source_b
)
SELECT code FROM a_codes
INTERSECT
SELECT code FROM b_codes
ORDER BY code NULLS LAST;
~~~

`btrim` trims leading/trailing whitespace, `upper` uppercases, and `NULLIF(..., '')` turns empty strings into NULL. **This is strictly an example policy.** If empty strings have distinct meaning or codes are case-sensitive, do not apply this blindly.

### 13.3. Symmetric Difference: Rows on Only One Side

Symmetric difference:

~~~text
(A EXCEPT B) UNION (B EXCEPT A)
~~~

With source labels:

~~~sql
WITH
only_a AS (
    SELECT code FROM setops_lab.source_a
    EXCEPT
    SELECT code FROM setops_lab.source_b
),
only_b AS (
    SELECT code FROM setops_lab.source_b
    EXCEPT
    SELECT code FROM setops_lab.source_a
)
SELECT 'only_in_A'::text AS side, code FROM only_a
UNION ALL
SELECT 'only_in_B'::text AS side, code FROM only_b
ORDER BY side, code NULLS LAST;
~~~

Result:

| side | code |
|---|---|
| only_in_A | A |
| only_in_A | E |
| only_in_B | F |
| only_in_B | G |

Labels are added **after** `EXCEPT`. Putting differing labels beforehand and then comparing with `UNION`/`INTERSECT` makes every row distinct because the label column participates in comparison.

---

## 14. Distinguishing Set Operations from JOIN

### 14.1. UNION Stacks Rows Vertically

~~~sql
SELECT code, category FROM setops_lab.source_a
UNION ALL
SELECT code, category FROM setops_lab.source_b;
~~~

The result has two columns like each branch, with rows from both sources stacked into one relation.

### 14.2. JOIN Combines Columns Horizontally by Condition

~~~sql
SELECT
    a.seq AS seq_a,
    b.seq AS seq_b,
    a.code,
    a.qty AS qty_a,
    b.qty AS qty_b
FROM setops_lab.source_a AS a
JOIN setops_lab.source_b AS b
  ON a.code = b.code
ORDER BY a.code, a.seq, b.seq;
~~~

`JOIN` returns columns from both A and B, forming **every matching row pair**. With code B appearing twice in A and three times in B, `INNER JOIN` produces **6 B pairs**.

Compare:

| Operation on code | Occurrences of B |
|---|---:|
| `UNION ALL` | 5 |
| `UNION` | 1 |
| `INTERSECT ALL` | 2 |
| `INTERSECT` | 1 |
| `INNER JOIN` | 6 pairs |

Those numbers reflect **different semantics**—never swap operators just because one query looks shorter.

### 14.3. When Is JOIN a Better Fit?

- Fetching a customer's name from the customers table to enrich a transaction.
- Placing `qty_a` and `qty_b` side by side for the same business key.
- Comparing attributes of two versions of an entity.
- Classifying records as inserted, updated, or deleted.

When the goal is a **set of common keys or missing keys**, `INTERSECT`/`EXCEPT` usually expresses it more directly.

---

## 15. EXCEPT vs. NOT EXISTS and NOT IN

### 15.1. EXCEPT Returns Distinct Rows Only

~~~sql
SELECT code FROM setops_lab.source_a
EXCEPT
SELECT code FROM setops_lab.source_b;
~~~

Returns A and E, each once.

### 15.2. NOT EXISTS Preserves Individual Source Row Details

If you want **each row of A** lacking a matching code in B:

~~~sql
SELECT a.seq, a.code, a.category, a.qty
FROM setops_lab.source_a AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM setops_lab.source_b AS b
    WHERE b.code IS NOT DISTINCT FROM a.code
)
ORDER BY a.seq;
~~~

This retains `seq` and all columns of A. If a code missing from B appears three times in A, all three rows are kept.

`IS NOT DISTINCT FROM` treats two NULLs as equal in the comparison, aligning closely with how set operations treat duplicate NULLs in that column.

### 15.3. NOT IN and the NULL Trap

~~~sql
SELECT code
FROM setops_lab.source_a
WHERE code NOT IN (
    SELECT code FROM setops_lab.source_b
);
~~~

Because B contains one or more NULLs, `NOT IN` evaluates to **UNKNOWN** instead of TRUE for A codes matching no non-NULL value in B.

Example:

~~~sql
SELECT 'A'::text NOT IN (
    SELECT code FROM setops_lab.source_b
) AS result_value;
~~~

The result is NULL (UNKNOWN), not TRUE. When subtracting two nullable column sets, `EXCEPT` is much clearer and safer.

### 15.4. LEFT JOIN Anti-Join Needs a Guaranteed Non-NULL Marker

~~~sql
SELECT a.seq, a.code
FROM setops_lab.source_a AS a
LEFT JOIN setops_lab.source_b AS b
  ON b.code IS NOT DISTINCT FROM a.code
WHERE b.seq IS NULL
ORDER BY a.seq;
~~~

Here `b.seq` is PK and cannot be NULL on any real B row; `b.seq IS NULL` proves no B row matched.

Never use `b.code IS NULL` as the marker when `code` is nullable and `ON` can match two NULLs. That would wrongly flag a matched NULL-code row as "unmatched."

---

## 16. Comparing One Column vs. Multiple Columns

Intersection by `code` alone:

~~~sql
SELECT code FROM setops_lab.source_a
INTERSECT
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

Result: B, C, D, NULL.

Intersection by three columns:

~~~sql
SELECT code, category, qty
FROM setops_lab.source_a
INTERSECT
SELECT code, category, qty
FROM setops_lab.source_b
ORDER BY code NULLS LAST, category NULLS LAST, qty NULLS LAST;
~~~

Result has four tuples:

~~~text
(B, software, 20)
(C, hardware, 30)
(D, NULL, NULL)
(NULL, unknown, NULL)
~~~

If one side changes B's `qty` from 20 to 25, **intersection by `code`** still includes B, whereas **intersection by triple** no longer includes that B tuple.

Before writing the query, clarify:

- Are we comparing **key existence** or **full row content**?
- Should timestamps, versions, or statuses be included?
- Should source-local ID columns be excluded?
- Do NULLs share the same meaning across both sources?
- Must duplicate occurrence counts be preserved?

---

## 17. Reconciling Two Data Snapshots

Suppose we have two snapshot tables with the same structure:

~~~text
snapshot_old(customer_id, email, status)
snapshot_new(customer_id, email, status)
~~~

These are **illustrative** table names, not created in the lab.

### 17.1. Checking Whether the Sets of Tuples Match

~~~sql
(
    SELECT customer_id, email, status FROM snapshot_old
    EXCEPT
    SELECT customer_id, email, status FROM snapshot_new
)
UNION ALL
(
    SELECT customer_id, email, status FROM snapshot_new
    EXCEPT
    SELECT customer_id, email, status FROM snapshot_old
);
~~~

If empty, both sides contain the exact same **set of distinct tuples** across the selected columns in the compared snapshots. Do not conclude duplicate row counts are equal.

### 17.2. Checking Multisets Including Repetition Counts

~~~sql
(
    SELECT customer_id, email, status FROM snapshot_old
    EXCEPT ALL
    SELECT customer_id, email, status FROM snapshot_new
)
UNION ALL
(
    SELECT customer_id, email, status FROM snapshot_new
    EXCEPT ALL
    SELECT customer_id, email, status FROM snapshot_old
);
~~~

If empty, both sides have the **exact same multiplicity of every tuple** across those columns at that point in time.

### 17.3. Classifying INSERT/UPDATE/DELETE

`EXCEPT` alone cannot distinguish an updated record from two unrelated tuples. When `customer_id` is a unique non-NULL key in both snapshots:

~~~sql
SELECT
    COALESCE(o.customer_id, n.customer_id) AS customer_id,
    CASE
        WHEN o.customer_id IS NULL THEN 'INSERT'
        WHEN n.customer_id IS NULL THEN 'DELETE'
        WHEN o.email IS DISTINCT FROM n.email
          OR o.status IS DISTINCT FROM n.status THEN 'UPDATE'
        ELSE 'UNCHANGED'
    END AS change_type
FROM snapshot_old AS o
FULL OUTER JOIN snapshot_new AS n
  ON o.customer_id = n.customer_id;
~~~

This illustrates **assigning a per-key change status** rather than merely listing differing tuples.

### 17.4. Both Sources Must Reflect the Same Point in Time

In live systems, one side may receive new events while the other has not yet synced. Therefore:

1. Align snapshot, watermark, or cutoff timestamps.
2. Align record scope, filter predicates, and soft-delete policies.
3. Identify business keys, payload columns, and audit columns.
4. Verify character normalization, types, timezones, and collations.
5. Decide between set vs. multiset reconciliation.
6. Compare row counts, distinct keys, two-way `EXCEPT` diffs, and aggregates.
7. Store reconciliation output with proper access controls; avoid exposing PII in reports.

An empty diff confirms parity only within the **compared scope**, not that two systems remain synced forever.

---

## 18. Combine First, Then GROUP BY to Count Per Source

`UNION ALL` paired with `GROUP BY` is great when you need per-source frequencies instead of mere presence/absence.

~~~sql
WITH combined AS (
    SELECT 'A'::text AS source_name, code
    FROM setops_lab.source_a
    UNION ALL
    SELECT 'B'::text AS source_name, code
    FROM setops_lab.source_b
)
SELECT
    code,
    COUNT(*) FILTER (WHERE source_name = 'A') AS count_a,
    COUNT(*) FILTER (WHERE source_name = 'B') AS count_b
FROM combined
GROUP BY code
ORDER BY code NULLS LAST;
~~~

Result:

| code | count_a | count_b |
|---|---:|---:|
| A | 1 | 0 |
| B | 2 | 3 |
| C | 1 | 1 |
| D | 1 | 1 |
| E | 1 | 0 |
| F | 0 | 1 |
| G | 0 | 1 |
| NULL | 1 | 2 |

To compute signed differences and classify them:

~~~sql
WITH combined AS (
    SELECT 'A'::text AS source_name, code
    FROM setops_lab.source_a
    UNION ALL
    SELECT 'B'::text AS source_name, code
    FROM setops_lab.source_b
),
counts AS (
    SELECT
        code,
        COUNT(*) FILTER (WHERE source_name = 'A') AS count_a,
        COUNT(*) FILTER (WHERE source_name = 'B') AS count_b
    FROM combined
    GROUP BY code
)
SELECT
    code,
    count_a,
    count_b,
    count_a - count_b AS signed_difference,
    CASE
        WHEN count_a > 0 AND count_b = 0 THEN 'only_A'
        WHEN count_b > 0 AND count_a = 0 THEN 'only_B'
        WHEN count_a = count_b THEN 'same_count'
        ELSE 'different_count'
    END AS comparison_status
FROM counts
ORDER BY code NULLS LAST;
~~~

`signed_difference` can be negative, zero, or positive. By contrast, `EXCEPT ALL` returns only **non-negative surplus counts** in the chosen subtraction direction.

---

## 19. Performance: EXPLAIN and Deduplication Cost

### 19.1. UNION Must Deduplicate Rows

~~~sql
EXPLAIN
SELECT code FROM setops_lab.source_a
UNION
SELECT code FROM setops_lab.source_b;
~~~

Depending on the plan, PostgreSQL may use:

- `Append` to combine branch inputs.
- `HashAggregate` to extract distinct tuples.
- `Sort` and `Unique` to sort and deduplicate.
- Other nodes/strategies depending on version, statistics, and parallelism.

`UNION ALL` skips deduplication and is usually lighter when **every row should stay**. Never switch `UNION` to `UNION ALL` if uniqueness is required.

### 19.2. INTERSECT/EXCEPT Use Specialized Nodes

~~~sql
EXPLAIN
SELECT code FROM setops_lab.source_a
EXCEPT ALL
SELECT code FROM setops_lab.source_b;
~~~

You may see `HashSetOp` or `SetOp` paired with scans/sorts depending on the plan. Inspect:

- Row counts per branch.
- Row width: how wide each row is.
- Whether `WHERE` filters run before the set operation.
- Heavy sorts/hashes, temp files, and disk I/O.
- Estimated vs. actual rows.
- Appropriate indexes or parallelism.

### 19.3. EXPLAIN ANALYZE Executes the Query

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT code FROM setops_lab.source_a
UNION
SELECT code FROM setops_lab.source_b;
~~~

`ANALYZE` causes PostgreSQL to **actually run** the query to measure timing and buffer activity. On tiny lab tables that is convenient; on millions of production rows, evaluate load and permissions first.

### 19.4. Indexes Help Filtering, Not Free Deduplication

~~~sql
CREATE INDEX ix_source_a_code ON setops_lab.source_a (code);
CREATE INDEX ix_source_b_code ON setops_lab.source_b (code);
~~~

These two indexes are **lab experiments**. They can speed up filters like:

~~~sql
SELECT code
FROM setops_lab.source_a
WHERE code = 'B';
~~~

Yet a `UNION` across **full tables** still has to read many rows and hash/sort to deduplicate. Indexes also add write and storage overhead, so never add them to production without workload metrics.

### 19.5. Filter Before UNION

~~~sql
SELECT code
FROM setops_lab.source_a
WHERE category = 'hardware'
UNION
SELECT code
FROM setops_lab.source_b
WHERE category = 'hardware'
ORDER BY code;
~~~

Pushing appropriate filters into each branch reduces data volume before combining. Note that not every filter movement across `EXCEPT`, `INTERSECT ALL`, or `LIMIT` branches preserves semantics.

### 19.6. Memory and Temp I/O

Sorting or hashing many wide rows can consume RAM or spill to temporary files. Investigate:

1. Do you really need to select that many columns?
2. Are you deduplicating an event set that should stay intact?
3. Can `WHERE` predicates reduce input volume?
4. Are CPU-heavy normalization expressions running per row?
5. Could an index or different plan help?
6. Are many similar queries running concurrently?

Do not blindly raise server-wide `work_mem` whenever a sort looks slow; total RAM across concurrent sorts/hashes can add up fast.

---

## 20. UNION and UNION ALL in Recursive CTEs

PostgreSQL supports `WITH RECURSIVE` combining an anchor term and a recursive term:

~~~sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM numbers
    WHERE n < 5
)
SELECT n
FROM numbers
ORDER BY n;
~~~

Result:

~~~text
1
2
3
4
5
~~~

### 20.1. UNION ALL and Cycles

If the data forms a graph:

~~~text
A → B
B → C
C → A
~~~

the recursive term can keep revisiting A without cycle protection. `UNION ALL` preserves every generated row, so cyclic paths cause infinite recursion.

`UNION` removes **entirely duplicate rows**, sometimes avoiding revisiting a node if the output is only the node ID. However, if the output includes `(node_id, depth)`:

~~~text
(A,0)
(A,3)
(A,6)
~~~

those are three distinct rows, so `UNION` **does not guarantee termination**.

You need explicit termination: depth limits, visited-node tracking, or `CYCLE` syntax on supported PostgreSQL versions. Never rely solely on an outer `LIMIT` for safety, especially if the query sorts or aggregates the recursive output.

---

## 21. Data Types and Collations in Deduplication

### 21.1. Some Types Lack Standard Equality

`UNION`/`INTERSECT`/`EXCEPT` must determine when two rows are equal for deduplication. PostgreSQL's `json` type lacks the general equality operator required for this:

~~~sql
-- Example that fails because json lacks appropriate equality.
SELECT '{"a":1}'::json AS payload
UNION
SELECT '{"a":1}'::json AS payload;
~~~

To compare JSON values using `jsonb` semantics when business rules permit:

~~~sql
SELECT '{"a":1}'::jsonb AS payload
UNION
SELECT '{"a":1}'::jsonb AS payload;
~~~

`UNION ALL` skips deduplication, so it works with types unsupported by `UNION DISTINCT` as long as both branches resolve a valid common type.

### 21.2. Collations and Unicode

`TEXT` comparisons depend on collation, especially with nondeterministic ICU collations. Do not assume every environment distinguishes the following identically:

~~~text
abc
ABC
á
a
abc with trailing spaces
~~~

When reconciling two sources, enforce consistent normalization/collation rules and test accented characters, casing, and whitespace.

### 21.3. Timestamps, Numbers, and TEXT Representations

Two timestamp strings in different timezones can represent the same instant when properly parsed as `TIMESTAMPTZ`. Similarly, `'1.0'` and `'1.00'` are distinct strings yet identical `NUMERIC` values.

Decide whether to compare **typed values** or **raw string representations**. Never cast arbitrarily just to silence a `UNION` type error.

---

## 22. Common Mistakes and Misconceptions

| Mistake | Consequence | Right Approach |
|---|---|---|
| Using `UNION` when every transaction is needed | Silently drops identical-looking transactions | Use `UNION ALL` and include event IDs |
| Using `UNION ALL` for a unique code list | Returns duplicate codes | Use `UNION` or appropriate `DISTINCT` |
| Using `SELECT *` to reconcile codes | IDs/timestamps change duplicate definition | Select exact comparison columns |
| Swapping column order between branches | Compiles yet mixes column meanings | Align columns by position and semantics |
| Ignoring data types | Type errors or wrong comparisons | Pick a semantically sound common type |
| Assuming `NULL = NULL` is TRUE | Misunderstands three-valued logic | Distinguish set operations from predicates |
| Treating `INTERSECT` as `JOIN` | Wrong multiplicity, many-to-many blowup | Pick operator matching desired output |
| Swapping `EXCEPT` branches by mistake | Missing rows in opposite direction | Label clearly as "only in A/B" |
| Using `EXCEPT` when occurrence counts matter | Ignores frequency mismatches | Use `EXCEPT ALL` |
| Using `NOT IN` on a nullable table | `UNKNOWN` drops expected rows | Use `EXCEPT` or `NOT EXISTS` |
| Omitting parentheses when mixing operators | Wrong evaluation order | Use parentheses or CTEs |
| Putting `ORDER BY` inside a branch and omitting outer `ORDER BY` | Final order is not guaranteed | Sort at the outermost result layer |
| Putting an expression in `ORDER BY` directly after `UNION` | Can be rejected by syntax | Wrap in a subquery |
| Adding source labels before `UNION` expecting codes to deduplicate | Different labels make every row distinct | Compare codes first, label afterward |
| Reconciling across mismatched timestamps | False diffs from lag or concurrent writes | Align snapshots/watermarks |
| Assuming indexes make deduplication free | Misestimates query cost | Read `EXPLAIN` and measure |
| Using `UNION` instead of `UNION ALL` to stop recursive cycles | Still loops if depth changes | Add depth limits/cycle detection |
| Comparing only `COUNT(*)` | Two tables with equal counts can still differ | Run two-way `EXCEPT` (and `EXCEPT ALL` if needed) |

---

## 23. Operator Selection Flowchart

~~~mermaid
flowchart TD
    A["Need to combine two SQL results"] --> B{"Want to pair columns by a condition?"}
    B -- "Yes" --> C["JOIN or key-based comparison"]
    B -- "No" --> D{"Want union, intersection, or difference?"}
    D -- "Union" --> E{"Keep every occurrence?"}
    E -- "Yes" --> F["UNION ALL"]
    E -- "No" --> G["UNION"]
    D -- "Intersection" --> H{"Need multiplicity?"}
    H -- "Yes" --> I["INTERSECT ALL"]
    H -- "No" --> J["INTERSECT"]
    D -- "Difference" --> K{"Need multiplicity?"}
    K -- "Yes" --> L["Directional EXCEPT ALL"]
    K -- "No" --> M["Directional EXCEPT"]
~~~

Before writing the query, answer in order:

1. What entity/event does one result row represent?
2. Which **columns** determine whether two rows are duplicates?
3. Must duplicate occurrence counts be kept?
4. For difference, which direction is the source under check?
5. Do both sides have compatible column counts and data types?
6. Do NULLs, empty strings, collations, and timezones align in meaning?
7. Are parentheses, per-branch `LIMIT`s, and a final `ORDER BY` needed?
8. Is the query small/safe enough to benchmark in the current environment?

---

## 24. Practice Exercises

Exercises use `setops_lab.source_a` and `setops_lab.source_b`, unless another hypothetical dataset is stated.

### Exercise 1 — UNION

Write a query returning distinct codes appearing in at least one source, sorted ascending with NULLs last. How many rows?

### Exercise 2 — UNION ALL

Write a query combining codes while keeping all occurrences. How many times does B appear, how many times does NULL appear, and how many rows total?

### Exercise 3 — INTERSECT

Find codes appearing in both A and B. Explain why NULL appears in the output.

### Exercise 4 — INTERSECT ALL

Write a query returning the multiset intersection. How many Bs appear and how many rows total?

### Exercise 5 — A Minus B

Find codes present only in source A.

### Exercise 6 — B Minus A

Compare `EXCEPT` and `EXCEPT ALL` when finding what B has that A lacks. Why do B and NULL appear in `ALL` yet not in `DISTINCT`?

### Exercise 7 — Comparing One Column vs. Three Columns

Write `INTERSECT` on `code`, then on `code,category,qty`. Describe a case where the two produce different results.

### Exercise 8 — Positional Column Matching

If A selects `(code,category)` and B selects `(category,code)`, can `UNION ALL` execute? Why is it wrong?

### Exercise 9 — SELECT *

Why are two rows with identical `code` B, `category` software, `qty` 20, yet different `seq`, not deduplicated when `seq` is selected?

### Exercise 10 — NULL

Predict the result row counts:

~~~sql
SELECT NULL::text UNION SELECT NULL::text;
SELECT NULL::text UNION ALL SELECT NULL::text;
SELECT NULL::text INTERSECT SELECT NULL::text;
SELECT NULL::text EXCEPT SELECT NULL::text;
~~~

### Exercise 11 — Operator Precedence

Explain the result of:

~~~sql
SELECT 1 AS n
UNION
SELECT 1 AS n
INTERSECT
SELECT 2 AS n;
~~~

Compared to:

~~~sql
(SELECT 1 AS n UNION SELECT 1 AS n)
INTERSECT
SELECT 2 AS n;
~~~

### Exercise 12 — Symmetric Difference

Write SQL returning `side,code` with `only_in_A`: A/E and `only_in_B`: F/G.

### Exercise 13 — Per-Source Counts

Use `UNION ALL` and `GROUP BY` to return `code`, `count_a`, `count_b`, and the signed difference.

### Exercise 14 — Duplicates in Snapshots

Source A has row X twice and B has X three times. Why are both directions of `EXCEPT` empty? Which `EXCEPT ALL` returns one X?

### Exercise 15 — ORDER BY lower(code)

Write a `UNION` query over both sources, sorting by `lower(code)` with NULLs last using valid PostgreSQL syntax.

### Exercise 16 — Per-Branch LIMIT

Fetch the three highest-`seq` rows from A and the three highest-`seq` rows from B, combine with `UNION ALL`, and sort descending by `seq`.

### Exercise 17 — NOT IN and NULL

Why might `code NOT IN (SELECT code FROM B)` fail to return A/E? Write a more reliable way to find the missing set.

### Exercise 18 — INTERSECT vs. JOIN

A has B twice and B has B three times. Predict the count of B for `UNION ALL`, `INTERSECT`, `INTERSECT ALL`, and the pair count for `INNER JOIN`.

### Exercise 19 — Tagging Source Origin

Write SQL combining `seq`, `code`, `qty` with a `source_name` column, avoiding confusing `seq` from A and B as a global ID.

### Exercise 20 — EXPLAIN

A large `UNION` query shows `Sort`/`Unique` nodes. What are they doing? If business rules require preserving all events, which operator should you consider?

### Exercise 21 — Recursive CTE

Why does `UNION` not guarantee stopping a cycle when each node visit produces a different `depth`?

### Exercise 22 — Production Reconciliation

List at least six factors to align before running a two-way `EXCEPT` to verify two sources are in sync.

---

## 25. Suggested Solutions

### Exercise 1

~~~sql
SELECT code FROM setops_lab.source_a
UNION
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

**8 rows:** A, B, C, D, E, F, G, NULL.

### Exercise 2

~~~sql
SELECT code FROM setops_lab.source_a
UNION ALL
SELECT code FROM setops_lab.source_b;
~~~

Total **16 rows**; B appears **5 times**, NULL **3 times**.

### Exercise 3

~~~sql
SELECT code FROM setops_lab.source_a
INTERSECT
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

**B, C, D, NULL**. NULLs at the same position are treated as matching during set operations.

### Exercise 4

~~~sql
SELECT code FROM setops_lab.source_a
INTERSECT ALL
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

B appears **2 times**, total **5 rows**: B, B, C, D, NULL.

### Exercise 5

~~~sql
SELECT code FROM setops_lab.source_a
EXCEPT
SELECT code FROM setops_lab.source_b
ORDER BY code;
~~~

Result: **A, E**.

### Exercise 6

~~~sql
SELECT code FROM setops_lab.source_b
EXCEPT
SELECT code FROM setops_lab.source_a;
~~~

Result: **F, G**.

~~~sql
SELECT code FROM setops_lab.source_b
EXCEPT ALL
SELECT code FROM setops_lab.source_a
ORDER BY code NULLS LAST;
~~~

Result: **B, F, G, NULL**. B and NULL each appear once more in B than in A, yet because both appear at least once in both sources, they are excluded by `EXCEPT` DISTINCT.

### Exercise 7

~~~sql
SELECT code FROM setops_lab.source_a
INTERSECT
SELECT code FROM setops_lab.source_b;
~~~

compares codes. Meanwhile:

~~~sql
SELECT code, category, qty FROM setops_lab.source_a
INTERSECT
SELECT code, category, qty FROM setops_lab.source_b;
~~~

compares triples. If one side has `(B,software,20)` and the other has `(B,software,25)`, B is a shared code yet the two triples do not match.

### Exercise 8

It runs because the positional types are compatible, yet PostgreSQL **does not match by column name**. Keep `code, category` in the exact same order on both sides.

### Exercise 9

`UNION` compares all selected columns. Different `seq` values make the two rows distinct even when the other three columns match. Select only `code` to deduplicate by code.

### Exercise 10

`UNION`: **1 NULL**. `UNION ALL`: **2 NULLs**. `INTERSECT`: **1 NULL**. `EXCEPT`: **0 rows**. Never infer from this that `NULL = NULL` is TRUE in predicates.

### Exercise 11

`INTERSECT` has higher precedence, so the first query is `{1} UNION ({1} INTERSECT {2})`, returning **1**. The parenthesized query is `({1} UNION {1}) INTERSECT {2}`, returning zero rows.

### Exercise 12

~~~sql
WITH
only_a AS (
    SELECT code FROM setops_lab.source_a
    EXCEPT
    SELECT code FROM setops_lab.source_b
),
only_b AS (
    SELECT code FROM setops_lab.source_b
    EXCEPT
    SELECT code FROM setops_lab.source_a
)
SELECT 'only_in_A'::text AS side, code FROM only_a
UNION ALL
SELECT 'only_in_B'::text AS side, code FROM only_b
ORDER BY side, code NULLS LAST;
~~~

### Exercise 13

~~~sql
WITH all_codes AS (
    SELECT 'A'::text AS src, code FROM setops_lab.source_a
    UNION ALL
    SELECT 'B'::text AS src, code FROM setops_lab.source_b
)
SELECT
    code,
    COUNT(*) FILTER (WHERE src = 'A') AS count_a,
    COUNT(*) FILTER (WHERE src = 'B') AS count_b,
    COUNT(*) FILTER (WHERE src = 'A')
        - COUNT(*) FILTER (WHERE src = 'B') AS difference
FROM all_codes
GROUP BY code
ORDER BY code NULLS LAST;
~~~

### Exercise 14

`EXCEPT` deduplicates by default, so both sides represent the same set `{X}` despite different counts. `B EXCEPT ALL A` returns **one surplus X**.

### Exercise 15

~~~sql
SELECT code
FROM (
    SELECT code FROM setops_lab.source_a
    UNION
    SELECT code FROM setops_lab.source_b
) AS merged
ORDER BY lower(code) NULLS LAST, code NULLS LAST;
~~~

### Exercise 16

~~~sql
(
    SELECT seq, code FROM setops_lab.source_a
    ORDER BY seq DESC LIMIT 3
)
UNION ALL
(
    SELECT seq, code FROM setops_lab.source_b
    ORDER BY seq DESC LIMIT 3
)
ORDER BY seq DESC;
~~~

Parentheses scope each `LIMIT` to its individual branch.

### Exercise 17

B contains NULL, causing `NOT IN` to return UNKNOWN for unmatched codes. Use:

~~~sql
SELECT code FROM setops_lab.source_a
EXCEPT
SELECT code FROM setops_lab.source_b;
~~~

Or `NOT EXISTS` with `IS NOT DISTINCT FROM` if individual source rows must be preserved.

### Exercise 18

`UNION ALL` has **5 Bs**, `INTERSECT` has **1 B**, `INTERSECT ALL` has **2 Bs**, and `INNER JOIN` on B yields **6 B pairs**.

### Exercise 19

~~~sql
SELECT 'A'::text AS source_name, seq AS source_seq, code, qty
FROM setops_lab.source_a
UNION ALL
SELECT 'B'::text AS source_name, seq AS source_seq, code, qty
FROM setops_lab.source_b
ORDER BY source_name, source_seq;
~~~

### Exercise 20

`Sort`/`Unique` performs **deduplication** for `UNION`. If business rules need every event, `UNION ALL` is accurate and skips deduplication. Measure row counts, row width, memory/temp I/O, and actual workload.

### Exercise 21

The same node at a different depth forms a distinct row, which `UNION` does not remove. Use depth limits, visited-node tracking, or cycle detection.

### Exercise 22

Align: identical **snapshot/watermark**, identical data scope, identical business keys and compared columns, data types/collations/timezones, NULL handling, duplicate policy, access permissions, row count checks, and two-way diffs.

---

## 26. Conclusion

`UNION`, `UNION ALL`, `INTERSECT`, and `EXCEPT` combine **rows from two query results** across corresponding columns, unlike `JOIN` which pairs columns horizontally by condition.

- **UNION:** union, removes duplicates.
- **UNION ALL:** union, keeps occurrences with count `a(x)+b(x)`.
- **INTERSECT:** intersection, removes duplicates.
- **INTERSECT ALL:** multiset intersection, keeps `min(a(x),b(x))` occurrences.
- **EXCEPT:** left minus right difference, removes duplicates.
- **EXCEPT ALL:** multiset difference, keeps `max(a(x)-b(x),0)` occurrences.

Each operator compares **all selected columns by position**. PostgreSQL treats two NULLs at the same position as equal during set deduplication, even though `NULL = NULL` is not TRUE in predicates. Columns must match in count and have compatible types; select them by **reconciliation semantics** rather than `SELECT *`.

When combining multiple operators, remember `INTERSECT` binds tighter than `UNION`/`EXCEPT`; use parentheses to express exact grouping. To sort the output, add a trailing `ORDER BY`; for per-branch `LIMIT`s, use parentheses. `UNION ALL` saves deduplication overhead, yet only when **keeping all rows matches business rules**.

A reliable workflow: **define what one row represents → pick comparison columns → choose set vs. multiset → pick union/intersection/difference and direction → check NULLs, types, and ordering → reconcile two ways → measure the plan on representative data**.
