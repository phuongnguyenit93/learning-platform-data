# Operator Classes, Collations, and Sort Order in PostgreSQL Indexes

A B-tree index on `title` can be very helpful for `WHERE title = 'ABC'` and `ORDER BY title`, yet it will not necessarily be used for `WHERE title LIKE 'ABC%'` when the database uses a non-`C` locale. A GIN index on `jsonb` can support searching JSON containing key–value pairs, yet a query checking key existence may require a **different operator class**. And two indexes sharing the same columns with different `ASC`/`DESC`/`NULLS FIRST` settings can serve different mixed sort orders.

To choose the right index in PostgreSQL, you need to understand three related concepts with distinct roles:

- **Operator class (opclass):** defines the set of operators and support functions an index access method can use for a given data type. Examples include `text_ops`, `text_pattern_ops`, `jsonb_ops`, and `jsonb_path_ops`.
- **Collation:** defines the comparison and sorting rules for certain string/text data types. For example, `"C"` rules differ from linguistic rules provided by the operating system or ICU.
- **Index sort order:** for B-trees, keys can be stored/scanned in `ASC` or `DESC` order, with nulls placed `NULLS FIRST` or `NULLS LAST`. In composite indexes, each column's direction determines which `ORDER BY` clauses are supported directly.

Key takeaway: **a single column may need different indexes for equality checks, prefix matching, linguistic sorting, JSON containment/existence, or substring search**. There is no “one B-tree for every operator.”

This lesson builds lab data, introduces operator selection mechanics, collation semantics, index ordering, and composite indexes; then applies them to `EXPLAIN`, catalog inspection, index design, and exercises with solutions. Examples target modern PostgreSQL; ICU/extension-related features depend on build options, version, and lab permissions.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the distinct roles of **index access method**, **operator class**, **collation**, and **key ordering**.
2. Read index definitions containing `text_pattern_ops`, `COLLATE "C"`, `DESC NULLS LAST`, or `USING GIN (... jsonb_path_ops)`.
3. Distinguish default B-tree indexes from prefix-matching B-trees, JSONB GIN indexes, and trigram indexes.
4. Know when an `ORDER BY` clause can leverage B-tree ordering instead of requiring a `Sort`.
5. Choose composite indexes with directions and `NULL` placement matching `ORDER BY ... LIMIT` queries.
6. Recognize risks when changing collations, upgrading ICU/libc, or assuming fixed Vietnamese string ordering.
7. Inspect installed opclasses/collations via catalogs and read `EXPLAIN (ANALYZE, BUFFERS)`.

## 2. Mental Model of an Index: Multiple Distinct Decisions

Consider:

~~~sql
CREATE INDEX idx_example
ON example_table (
    title COLLATE "C" text_pattern_ops ASC NULLS LAST
);
~~~

This definition combines:

| Component | In Example | Answers the Question |
| --- | --- | --- |
| Access method | `btree`, default when `USING` is omitted | How is the index organized and searched? |
| Column/expression | `title` | Which value serves as the key? |
| Collation | `"C"` | By what rules are strings compared? |
| Operator class | `text_pattern_ops` | Which operators can utilize the index structure? |
| Sort order | `ASC` | Does the B-tree order keys ascending or descending? |
| NULL placement | `NULLS LAST` | In the specified scan direction, do nulls come first or last? |

**Do not confuse opclass with collation.** The operator class connects SQL operators to index capabilities; collation defines text comparison rules; `ASC`/`DESC` specifies key traversal direction. An index can also include a `WHERE` predicate (partial index), `INCLUDE` columns, or expressions.

### 2.1. An Index Does Not Automatically Guarantee Index Scan

An index being **capable of supporting** a query differs from it **actually being chosen**. The planner weighs:

- Table size and estimated returned rows.
- Selectivity of filter predicates.
- Whether ordering can come from the index or requires a `Sort`.
- Heap access cost, random I/O, and cache state.
- Statistics, physical correlation, parallelism, and other joins.

Thus, on a 10-row table, `Seq Scan` is often completely reasonable even with an ideal index.

## 3. Preparing Lab Data

Create this schema only in a lab database. Do not run these steps against production tables.

### 3.1. Creating the Table

~~~sql
CREATE SCHEMA idx_lab;

CREATE TABLE idx_lab.items (
    item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL,
    title text NOT NULL,
    category text NOT NULL,
    price numeric(12, 2),
    created_at timestamptz NOT NULL,
    attrs jsonb NOT NULL DEFAULT '{}'::jsonb
);
~~~

`price` is nullable so we can observe `NULLS FIRST`/`NULLS LAST`. The `title` column contains Vietnamese diacritics, unaccented strings, and mixed uppercase/lowercase letters.

### 3.2. Inserting Sample Data

~~~sql
INSERT INTO idx_lab.items
    (sku, title, category, price, created_at, attrs)
VALUES
    ('CF-001', 'Cà phê rang', 'drink', 79000,
      '2026-02-01 09:00:00+07',
      '{"color":"brown","stock":15,"tags":["coffee"]}'),
    ('CF-002', 'Ca phe sua', 'drink', 45000,
      '2026-02-02 09:00:00+07',
      '{"color":"white","stock":30,"tags":["coffee","milk"]}'),
    ('CF-003', 'cà phê hòa tan', 'drink', 32000,
      '2026-02-03 09:00:00+07',
      '{"color":"brown","stock":20,"tags":["coffee"]}'),
    ('TE-001', 'Trà sen', 'drink', 55000,
      '2026-02-04 09:00:00+07',
      '{"color":"green","stock":10,"tags":["tea"]}'),
    ('BK-001', 'Sách SQL', 'book', 170000,
      '2026-02-05 09:00:00+07',
      '{"lang":"vi","stock":8,"tags":["database"]}'),
    ('BK-002', 'Sach PostgreSQL', 'book', 210000,
      '2026-02-06 09:00:00+07',
      '{"lang":"vi","stock":6,"tags":["database"]}'),
    ('BK-003', 'Index cơ bản', 'book', 125000,
      '2026-02-07 09:00:00+07',
      '{"lang":"vi","stock":12,"tags":["database"]}'),
    ('OF-001', 'Bút mực', 'office', 12000,
      '2026-02-08 09:00:00+07',
      '{"color":"blue","stock":100,"tags":["pen"]}'),
    ('OF-002', 'Bìa hồ sơ', 'office', NULL,
      '2026-02-09 09:00:00+07',
      '{"color":"red","tags":["folder"]}'),
    ('OF-003', 'Giấy ghi chú', 'office', 22000,
      '2026-02-10 09:00:00+07',
      '{"color":"yellow","stock":40,"tags":["paper"]}');
~~~

### 3.3. Verification

~~~sql
SELECT
    item_id, sku, title, category, price
FROM idx_lab.items
ORDER BY item_id;
~~~

There are 10 items; `OF-002` has a null price. Sort results on `title` may vary across default collations, so these examples **do not assume a fixed Vietnamese sort order**.

## 4. Index Access Method First, Operator Class Second

A PostgreSQL index has an **access method**.

| Access method | Typical Use | Related Capabilities |
| --- | --- | --- |
| `btree` | Equality, range, ordered key traversal | `=`, `<`, `<=`, `>`, `>=`, `ORDER BY` |
| `hash` | Equality lookup via compatible operators | Provides no ordering useful for `ORDER BY` |
| `GIN` | Multi-component values such as JSONB, arrays, tokens/trigrams | Supported operators depend on GIN operator class |
| `GiST` | Generalized index framework for geometric/range/specialized types | Operator class governs searches and certain specialized ordered scans |
| `SP-GiST` | Space-partitioned index structures | Depends on data type and operator class |
| `BRIN` | Summarizes table block ranges | Often effective when data has strong physical correlation |

Examples:

~~~sql
CREATE INDEX idx_items_price
ON idx_lab.items USING btree (price);

CREATE INDEX idx_items_attrs_gin
ON idx_lab.items USING gin (attrs);
~~~

`USING btree` can be omitted because B-tree is the default. `USING gin`, however, must be stated explicitly when you want a GIN index.

### 4.1. Operator Classes Belong to an Access Method

An operator class defines, for a **specific access method**, which operators and support functions handle a given key type.

For instance, `text_pattern_ops` belongs to B-tree; `jsonb_path_ops` belongs to GIN; `gin_trgm_ops` from the `pg_trgm` extension is an operator class for GIN.

They cannot be swapped arbitrarily merely because all of them deal with “text or JSON indexes.”

### 4.2. Default When Omitting Opclass

~~~sql
CREATE INDEX idx_items_title_default
ON idx_lab.items (title);
~~~

PostgreSQL picks the default operator class suitable for **type `text` + access method B-tree** (typically `text_ops`). This option serves general B-tree comparisons under the effective collation.

If your target is a different operator pattern, inspect the corresponding opclass instead of assuming a default index works.

## 5. Operator Classes and Operator Families

An **operator class** groups operators and support functions for one key type and one access method. An **operator family** groups related opclasses/operators so comparisons across multiple compatible data types can work together.

Practical example: an integer index can sometimes be used by the planner in comparisons against another integer type thanks to supported cross-type operator family semantics. That does not mean **every cast** or every comparison can use the index.

### 5.1. SQL Operators Are Not One-to-One Index Operators

~~~sql
WHERE title = 'Sách SQL'
WHERE title < 'T'
WHERE title LIKE 'Sa%'
WHERE title ILIKE '%sql%'
~~~

All four predicates reference `title`, yet they can require **different index mechanisms**. PostgreSQL must have an operator or condition transformation supported by the opclass alongside applicable collation rules.

### 5.2. Inspecting Operator Classes via Catalogs

~~~sql
SELECT
    am.amname AS access_method,
    opc.opcname AS operator_class,
    opc.opcintype::regtype AS input_type,
    opc.opcdefault AS is_default
FROM pg_opclass AS opc
JOIN pg_am AS am
    ON am.oid = opc.opcmethod
WHERE opc.opcname IN (
    'text_ops',
    'text_pattern_ops',
    'varchar_pattern_ops',
    'jsonb_ops',
    'jsonb_path_ops',
    'gin_trgm_ops'
)
ORDER BY am.amname, opc.opcname, opc.opcintype::regtype::text;
~~~

Output depends on installed extensions and PostgreSQL version. If `pg_trgm` is not installed, `gin_trgm_ops` will not appear; `jsonb_ops` may have entries corresponding to different access methods.

### 5.3. Never Edit System Catalogs Directly

Catalogs such as `pg_opclass`, `pg_am`, and `pg_amop` are helpful for **reading metadata**. Never modify system catalogs directly to attach operators to indexes. Custom operator classes are an advanced topic for extension developers who deeply understand access methods and comparison semantics.

## 6. Default B-tree and Comparison Semantics

~~~sql
CREATE INDEX idx_items_price_asc
ON idx_lab.items (price);
~~~

Queries the index can support depending on selectivity:

~~~sql
SELECT item_id, price
FROM idx_lab.items
WHERE price = 79000;

SELECT item_id, price
FROM idx_lab.items
WHERE price >= 50000 AND price < 150000;

SELECT item_id, price
FROM idx_lab.items
ORDER BY price ASC NULLS LAST
LIMIT 5;
~~~

Because `price` is `numeric`, it has no string collation; comparison operators follow numeric semantics.

### 6.1. Sorting Prices as Text Can Be Wrong

~~~sql
SELECT
    item_id,
    price,
    price::text AS price_string
FROM idx_lab.items
ORDER BY price::text;
~~~

Lexicographic order of `'12000'`, `'79000'`, `'170000'` as **strings** does not match numeric order. Nor does a B-tree index on `price numeric` automatically become an index for the expression `price::text`.

When sorting by price amount, **`ORDER BY price`** is the proper expression; format as text only at the presentation layer.

### 6.2. Changing the Expression Changes Index Matching

~~~sql
WHERE price + 1000 > 50000
~~~

differs from:

~~~sql
WHERE price > 49000
~~~

in whether the planner can use an index on the **base column**, even though both predicates are mathematically equivalent within valid value ranges. PostgreSQL will not necessarily rewrite arbitrary expressions/functions into an index range scan. Write simple predicates directly on the column whenever possible.

## 7. What Is a Collation?

A **collation** defines rules for comparing and sorting collatable string data. It affects operations like:

~~~sql
ORDER BY title
WHERE title < 'M'
WHERE title = 'cafe'
~~~

in ways determined by data type, operator, and collation.

Sample text values:

~~~text
Ca phe sua
Cà phê rang
cà phê hòa tan
Sách SQL
Sach PostgreSQL
~~~

Byte-order or code-point order does not necessarily match natural Vietnamese dictionary order. Systems may choose `libc` or ICU providers and locales to meet linguistic requirements.

### 7.1. Checking Database Settings

~~~sql
SHOW lc_collate;
SHOW lc_ctype;
~~~

These reflect the database's base locale settings. The **effective collation for a specific column or expression** also depends on the column's declared collation and any explicit `COLLATE` clause.

### 7.2. Viewing Collations in PostgreSQL

~~~sql
SELECT
    collname,
    collprovider,
    collisdeterministic,
    collversion
FROM pg_collation
WHERE collname IN ('C', 'POSIX')
ORDER BY collname;
~~~

Columns covering provider/deterministic/version exist on modern PostgreSQL; exact catalogs and options can vary by version.

### 7.3. COLLATE in SELECT

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY title COLLATE "C", item_id;
~~~

`"C"` is a built-in collation using C/byte-oriented comparison rules—it is **not “standard Vietnamese alphabetical order.”** It is useful when deterministic machine-oriented ordering or C rules are needed.

Compare with:

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY title, item_id;
~~~

The second query uses the default effective collation of `title`; the two orderings **can differ**.

## 8. Column-Level vs. Expression-Level Collation

Collation can be declared at column creation time:

~~~sql
CREATE TABLE idx_lab.labels (
    label_id integer PRIMARY KEY,
    name_c text COLLATE "C" NOT NULL,
    note text
);
~~~

Column `name_c` declares `"C"` as its collation.

You do not need to alter an existing column just to test a collation:

~~~sql
SELECT
    title,
    title COLLATE "C" AS title_c
FROM idx_lab.items
ORDER BY title COLLATE "C";
~~~

### 8.1. COLLATE Does Not Convert Encoding

~~~sql
SELECT title COLLATE "C"
FROM idx_lab.items;
~~~

This expression **does not modify the underlying bytes stored in `title`**, does not re-encode UTF-8, does not strip accents, and does not lowercase characters. It solely specifies comparison and sorting rules where applicable.

### 8.2. COLLATE Applies Only to Collatable Types

You cannot attach `COLLATE` arbitrarily to `integer` or `numeric`:

~~~sql
-- Not meaningful syntax for numeric:
SELECT price COLLATE "C"
FROM idx_lab.items;
~~~

Collation applies to types supporting linguistic/string comparison rules such as `text`, `varchar`, and other collatable types.

### 8.3. Comparisons Using Explicit Collation

~~~sql
SELECT sku, title
FROM idx_lab.items
WHERE title COLLATE "C" >= 'A'
  AND title COLLATE "C" < 'N'
ORDER BY title COLLATE "C";
~~~

In the query above, both range filtering and sorting require `"C"` semantics. If an existing index uses a different collation, the query cannot automatically exploit that index's sort order and range bounds.

## 9. Collation and B-tree Index Compatibility

Suppose you have:

~~~sql
CREATE INDEX IF NOT EXISTS idx_items_title_default
ON idx_lab.items (title);
~~~

The query:

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY title
LIMIT 10;
~~~

can use this index's ordering if the planner deems it beneficial.

However:

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY title COLLATE "C"
LIMIT 10;
~~~

requires ordering under **`"C"`**. If `title`'s default collation is not `"C"`, the default index does not guarantee the same order.

### 9.1. Creating an Index with an Explicit Collation

~~~sql
CREATE INDEX idx_items_title_c
ON idx_lab.items (title COLLATE "C");
~~~

Then:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, title
FROM idx_lab.items
ORDER BY title COLLATE "C"
LIMIT 5;
~~~

The planner **may** consider the new index. On a 10-row table, `Seq Scan + Sort` can still be cheaper.

### 9.2. Do Not Treat Two Collations as Interchangeable

If an index uses `"C"` collation, do not assume it satisfies `ORDER BY title` under a different linguistic collation.

Rule: **comparison and sorting semantics of query and index must be compatible**. Compatibility is not determined merely by matching column names.

## 10. Default Operator Class text_ops

For a B-tree on a `text` column:

~~~sql
CREATE INDEX idx_items_title_normal
ON idx_lab.items (title);
~~~

This definition uses the default operator class (typically `text_ops`) and the column's effective collation.

It fits:

~~~sql
SELECT sku, title
FROM idx_lab.items
WHERE title = 'Sách SQL';
~~~

and B-tree comparisons / `ORDER BY` clauses with compatible semantics.

### 10.1. Not Every LIKE Uses a Standard B-tree Index

~~~sql
SELECT sku, title
FROM idx_lab.items
WHERE title LIKE 'Ca%';
~~~

`LIKE 'Ca%'` is a **prefix match**. Under many non-`C` collations, a standard `text_ops` B-tree may **not suffice for PostgreSQL to convert `LIKE` into an index range scan**.

That is a classic use case for `text_pattern_ops`.

### 10.2. text_ops Follows Collation Ordering

If the primary goal is `ORDER BY title` under a linguistic locale, a default B-tree index with the matching collation is usually more appropriate than `text_pattern_ops`. The two opclasses solve different problems.

## 11. text_pattern_ops and LIKE 'prefix%'

~~~sql
CREATE INDEX idx_items_title_prefix
ON idx_lab.items (title text_pattern_ops);
~~~

`text_pattern_ops` is a B-tree opclass supporting character-by-character pattern comparisons rather than full linguistic collation sorting rules. It is designed to help **`LIKE` prefix searches** when a standard locale prevents the default B-tree from optimizing them.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, title
FROM idx_lab.items
WHERE title LIKE 'Ca%';
~~~

The planner can turn the fixed prefix into an index range condition while still checking the `LIKE` predicate to ensure accuracy.

### 11.1. Pattern Opclasses by Column Type

| Column Type | Common B-tree Pattern Opclass |
| --- | --- |
| `text` | `text_pattern_ops` |
| `varchar` | `varchar_pattern_ops` |
| `char(n)` / `bpchar` | `bpchar_pattern_ops` |

Do not pick `text_pattern_ops` simply because “the column holds text” when the actual data type differs and expects its corresponding opclass.

### 11.2. Fixed-Prefix Predicates

~~~sql
WHERE title LIKE 'Ca%'
~~~

has a fixed leading string: `Ca`.

By contrast:

~~~sql
WHERE title LIKE '%phe%'
~~~

starts with a wildcard. Neither standard B-tree nor `text_pattern_ops` **can narrow to a fixed prefix range** the way `LIKE 'Ca%'` does.

### 11.3. Equality and Range Are Not Identical

`text_pattern_ops` can support equality comparisons in appropriate contexts, yet **does not fully substitute** for a standard collation index on textual range queries:

~~~sql
WHERE title > 'M'
ORDER BY title
~~~

interpreted under the required linguistic collation. If the workload needs both prefix matching and locale-based range/sort, you may need **two specialized indexes** or a different design, weighing write and storage costs.

### 11.4. Special Behavior Under C Collation

When the effective collation is `C`, a standard B-tree index can serve `LIKE 'abc%'` prefix matching without needing a separate `text_pattern_ops` index. This is why you must **know the active collation** before mechanically adding extra indexes.

## 12. Combining COLLATE "C" and pattern_ops

Syntax:

~~~sql
CREATE INDEX idx_items_title_c_pattern
ON idx_lab.items (
    title COLLATE "C" text_pattern_ops
);
~~~

This creates an index with key `title`, collation `"C"`, and the B-tree pattern opclass.

### 12.1. When Is It Useful?

When an application intentionally wants `"C"` comparison rules alongside prefix search, you can keep expressions and index keys consistent with that rule.

However, under `"C"` collation, the default B-tree already handles prefix `LIKE` well in many situations, so **do not assume adding `pattern_ops` automatically improves performance**. Inspect real queries and `EXPLAIN`.

### 12.2. Do Not Assume It Serves Every ORDER BY

An index using `text_pattern_ops` is tuned for pattern semantics; it does not substitute for a `text_ops` B-tree index serving `ORDER BY title` under a different linguistic collation.

More important than index names are the **operators, collation, and opclass comparator**.

## 13. Case-Insensitive Search

`ILIKE` is commonly used for case-insensitive text matching:

~~~sql
SELECT sku, title
FROM idx_lab.items
WHERE title ILIKE 'ca%';
~~~

Do not assume a standard B-tree index on `title` supports every `ILIKE`. In many workloads, one option is **normalizing via `lower` in an expression index**:

~~~sql
CREATE INDEX idx_items_lower_title_prefix
ON idx_lab.items (
    (lower(title)) text_pattern_ops
);
~~~

The query must use the matching expression:

~~~sql
SELECT sku, title
FROM idx_lab.items
WHERE lower(title) LIKE 'ca%';
~~~

### 13.1. Case-Folding Depends on Locale

`lower`/`upper` depend on linguistic and collation rules. Do not claim they behave identically across all Unicode variants, Vietnamese diacritics, or case-folding edge cases in every language.

### 13.2. Query and Index Must Match Expressions

~~~sql
WHERE lower(title) LIKE 'ca%'
~~~

can match an index on `lower(title)`.

However:

~~~sql
WHERE title ILIKE 'ca%'
~~~

will not automatically rewrite into a lookup on an expression index of `lower(title)` across all versions and execution scenarios. Always inspect the plan of the **exact SQL your application sends**.

### 13.3. Do Not Strip Diacritics Arbitrarily

If the business requires accent-insensitive Vietnamese search, that is a **distinct requirement** from case-insensitive search. It may require ICU collations, normalization, `unaccent`, or a dedicated search index—each with trade-offs in accuracy, indexability, and version behavior. Never discard diacritics in stored source columns if information loss is unacceptable.

## 14. Trigrams for LIKE '%substring%'

The `pg_trgm` extension provides operator classes for trigram-based search, helpful for certain `LIKE`, `ILIKE`, regex, and similarity queries.

In a lab, if extension permissions permit:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_items_title_trgm
ON idx_lab.items
USING gin (title gin_trgm_ops);
~~~

Then:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, title
FROM idx_lab.items
WHERE title ILIKE '%phe%';
~~~

A GIN trigram index **can** accelerate unanchored substring searches lacking a fixed prefix, which B-tree prefix indexes cannot handle in the same way.

### 14.1. Trigrams Are Not Magic

Cost and index usability depend on:

- Whether the pattern yields enough extractable trigrams.
- Keyword length, wildcards, and special characters.
- Row count, match selectivity, and language characteristics.
- GIN maintenance, storage size, and update frequency.

For very short patterns or patterns with too few trigrams, the planner may gain nothing from the index. **GIN trigram indexes do not supply B-tree ordering for `ORDER BY title`.**

### 14.2. Prefix vs. Substring

| Primary Query | Typical Index Approach to Consider |
| --- | --- |
| `title = 'Sách SQL'` | Default text B-tree |
| `title LIKE 'Ca%'` | Collation-appropriate B-tree, possibly `text_pattern_ops` |
| `lower(title) LIKE 'ca%'` | Expression B-tree `(lower(title)) text_pattern_ops` |
| `title ILIKE '%sql%'` | GIN/GiST trigram when data and patterns fit |
| `ORDER BY title COLLATE "C"` | B-tree with matching collation |

A system may use multiple techniques depending on **query patterns**, yet do not create every index simply because it exists.

## 15. JSONB Operator Classes: jsonb_ops and jsonb_path_ops

For `jsonb`, GIN is a popular choice:

~~~sql
CREATE INDEX idx_items_attrs_ops
ON idx_lab.items
USING gin (attrs jsonb_ops);
~~~

`jsonb_ops` is the common default GIN operator class for `jsonb`. It supports a broad range of JSONB operators:

~~~sql
SELECT sku
FROM idx_lab.items
WHERE attrs @> '{"color":"brown"}'::jsonb;

SELECT sku
FROM idx_lab.items
WHERE attrs ? 'stock';
~~~

### 15.1. jsonb_path_ops

~~~sql
CREATE INDEX idx_items_attrs_path
ON idx_lab.items
USING gin (attrs jsonb_path_ops);
~~~

`jsonb_path_ops` focuses on a narrower operator set and can often build a smaller, more efficient index for eligible containment and JSON path queries, depending on document structure.

~~~sql
SELECT sku
FROM idx_lab.items
WHERE attrs @> '{"color":"brown"}'::jsonb;
~~~

can use an appropriate GIN index with `jsonb_path_ops`.

However:

~~~sql
SELECT sku
FROM idx_lab.items
WHERE attrs ? 'stock';
~~~

**is not supported by `jsonb_path_ops` the same way as `jsonb_ops`**, because the key-existence operator `?` is outside the operator strategies provided by `jsonb_path_ops`.

### 15.2. Quick Selection Table

| Requirement | `jsonb_ops` | `jsonb_path_ops` |
| --- | --- | --- |
| Containment `@>` | Yes | Yes |
| JSON path matching `@?`/`@@` (supported versions) | Yes | Yes |
| Key existence `?`, `?|`, `?&` | Yes | No |
| Supported operator breadth | Wider | Narrower |
| Size and selectivity | Workload-dependent | Often leaner/faster for suitable containment queries |

Do not choose an opclass solely by index size. If your application relies heavily on `attrs ? 'stock'`, choosing `jsonb_path_ops` alone can hurt performance even if one standalone `@>` query gets faster.

### 15.3. Two GIN Indexes on One Column Have Overhead

The examples created two indexes strictly to **illustrate the difference**. In production, every GIN index adds write, `VACUUM`, storage, and maintenance costs. Keep only the index matching the **operators your workload needs**, rather than copying every example.

### 15.4. GIN Does Not Replace ORDER BY

~~~sql
WHERE attrs @> '{"color":"brown"}'
ORDER BY created_at DESC
LIMIT 10
~~~

GIN helps locate items matching JSON predicates, yet **does not supply `created_at` ordering**. The planner may still need to sort matching rows or use an alternative access strategy.

## 16. ASC, DESC, and NULLS in B-tree

The default ordering of an unspecified B-tree key:

~~~sql
CREATE INDEX idx_items_price_default
ON idx_lab.items (price);
~~~

is equivalent in ordering intent to:

~~~sql
CREATE INDEX idx_items_price_explicit
ON idx_lab.items (price ASC NULLS LAST);
~~~

Running both statements creates **two separate indexes**; they are shown to compare syntax, not to recommend duplicates.

### 16.1. ORDER BY Defaults

In PostgreSQL:

| ORDER BY | Default Null Placement |
| --- | --- |
| `ORDER BY price ASC` | `NULLS LAST` |
| `ORDER BY price DESC` | `NULLS FIRST` |
| `ORDER BY price ASC NULLS FIRST` | Explicitly puts nulls first |
| `ORDER BY price DESC NULLS LAST` | Explicitly puts nulls last |

Because `OF-002` has `price = NULL`, the query:

~~~sql
SELECT sku, price
FROM idx_lab.items
ORDER BY price DESC NULLS LAST;
~~~

keeps items with null prices **at the end**.

### 16.2. Two-Way B-tree Scanning

A B-tree can be scanned **forward** or **backward**:

~~~text
Index: price ASC NULLS LAST

Forward scan  -> price ASC NULLS LAST
Backward scan -> price DESC NULLS FIRST
~~~

Therefore, to serve default `ORDER BY price DESC`, **you do not necessarily need a separate `DESC` index** on a single column.

However:

~~~sql
ORDER BY price DESC NULLS LAST
~~~

does not match a backward scan of `ASC NULLS LAST` regarding null placement. If null placement matters, you may need an index declared with matching direction/null placement, or an extra sort step.

### 16.3. A DESC NULLS LAST Index

~~~sql
CREATE INDEX idx_items_price_desc_last
ON idx_lab.items (price DESC NULLS LAST);
~~~

This index aligns forward scans with:

~~~sql
SELECT sku, price
FROM idx_lab.items
ORDER BY price DESC NULLS LAST
LIMIT 5;
~~~

The planner can read the leading entries from the index instead of scanning and sorting the entire table, especially on large tables with small `LIMIT`.

## 17. Composite Indexes and Multi-Column ORDER BY

A B-tree index:

~~~sql
CREATE INDEX idx_items_category_price
ON idx_lab.items (
    category ASC,
    price DESC NULLS LAST,
    item_id ASC
);
~~~

can serve:

~~~sql
SELECT item_id, category, price
FROM idx_lab.items
ORDER BY
    category ASC,
    price DESC NULLS LAST,
    item_id ASC;
~~~

This index stores a **mixed sort order**: ascending `category`, descending `price`, ascending `item_id`.

### 17.1. Backward Scan Reverses All Components

If an index stores:

~~~text
category ASC,
price DESC NULLS LAST,
item_id ASC
~~~

then a backward scan yields the exact inverse order:

~~~text
category DESC,
price ASC NULLS FIRST,
item_id DESC
~~~

You cannot use a simple **full-scan reversal** to get an arbitrary combination like:

~~~sql
ORDER BY category ASC, price ASC
~~~

when the index directions do not match. The planner may still use a partial prefix order followed by a sort or incremental sort depending on the plan.

### 17.2. With an Equality Predicate on the Leading Column

~~~sql
SELECT sku, title, price
FROM idx_lab.items
WHERE category = 'book'
ORDER BY price DESC NULLS LAST, item_id ASC
LIMIT 3;
~~~

Because `category` is pinned by `= 'book'`, the remaining index portion yields entries ordered by `price DESC NULLS LAST, item_id ASC` directly for the query.

This is a classic pattern for “Top N items by price within a category.”

### 17.3. Tie-Breaker Keys for Pagination

If two items share the same `price`, writing only:

~~~sql
ORDER BY price DESC
~~~

does not guarantee a deterministic order between ties. Adding `item_id`:

~~~sql
ORDER BY price DESC NULLS LAST, item_id ASC
~~~

stabilizes pagination within a single snapshot and supports cursor tracking.

Still, when rows are **inserted, deleted, or updated concurrently**, even a deterministic `ORDER BY` cannot prevent `OFFSET` pagination from shifting rows between separate requests.

## 18. Leading-Column Principle in Composite Indexes

A B-tree index on:

~~~sql
(category, price DESC, item_id)
~~~

is ordered from left to right. When a query uses:

~~~sql
WHERE category = 'book'
ORDER BY price DESC, item_id
~~~

constraining the leading column allows exploiting the remaining columns' order.

If a query only asks:

~~~sql
ORDER BY price DESC
~~~

across **all categories of the table**, an index on `(category, price)` **does not supply global price ordering** because rows are grouped by `category` first. The index might still be used for other reasons, yet its order cannot satisfy a global `ORDER BY price`.

### 18.1. Do Not Turn “Leftmost Prefix” into an Absolute Prohibition

PostgreSQL supports multiple strategies including index scans, bitmap scans, incremental sort, and in newer versions/conditions index skip scan optimizations. A query omitting the leading column can still use an index in some cases.

A more accurate design rule: **predicates on leading columns and query ordering strongly shape index efficiency and `ORDER BY` alignment**; inspect actual execution plans.

### 18.2. Filter-Oriented vs. Order-Oriented Indexes

A highly selective lookup on `sku`:

~~~sql
WHERE sku = 'BK-001'
~~~

returns a single row; a lookup index on `sku` suffices—there is no need for complex `DESC` key directions.

Conversely, a listing query:

~~~sql
WHERE category = 'book'
ORDER BY price DESC NULLS LAST
LIMIT 20
~~~

benefits from a **combined filter + order index**. Design indexes around **complete query patterns**, not isolated columns.

## 19. LIMIT, Top-N, and Sort Cost

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, title, price
FROM idx_lab.items
WHERE category = 'drink'
ORDER BY price DESC NULLS LAST, item_id
LIMIT 3;
~~~

If the planner uses an index with matching order, it can stop once enough rows for `LIMIT` are found, subject to residual filters and execution details. Without a matching index, the planner may pick `Sort` (possibly using top-N heapsort) or another path.

### 19.1. LIMIT Does Not Guarantee Fast Index Execution

If `WHERE` has low selectivity or the index scan must read and discard many entries before satisfying `LIMIT`, gains shrink. On a 10-row table, scanning everything and sorting is usually tiny anyway.

### 19.2. Incremental Sort

When inputs are already sorted by a **prefix** of `ORDER BY`, PostgreSQL can use `Incremental Sort` in supported versions/situations instead of sorting the entire rowset across every key from scratch.

Matching part of an index does not mean sorting the remaining keys is free. Check the plan for `Sort` or `Incremental Sort`.

## 20. Expression ORDER BY and Expression Indexes

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY lower(title);
~~~

An index solely on `title` does not automatically supply ordering for `lower(title)`.

You can create an expression index:

~~~sql
CREATE INDEX idx_items_lower_title
ON idx_lab.items (lower(title));
~~~

Then:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, title
FROM idx_lab.items
ORDER BY lower(title)
LIMIT 5;
~~~

### 20.1. Expression and Collation Must Align

If a query requests:

~~~sql
ORDER BY lower(title) COLLATE "C"
~~~

you can define:

~~~sql
CREATE INDEX idx_items_lower_title_c
ON idx_lab.items (
    (lower(title)) COLLATE "C"
);
~~~

Do not assume an index on `lower(title)` with a different default collation guarantees `"C"` order.

### 20.2. Expression Indexes Also Incur Write Cost

Every `INSERT`/`UPDATE` touching the key expression requires maintaining the expression index. Moreover, expression indexes require functions/expressions satisfying index **immutability** rules.

Do not attempt to place session-, timezone-, or mutable-state-dependent functions into an expression index expecting PostgreSQL to accept them.

## 21. INCLUDE Columns Do Not Determine Sort Order

PostgreSQL B-trees can carry **non-key columns** to enable some index-only scans:

~~~sql
CREATE INDEX idx_items_category_price_covering
ON idx_lab.items (
    category,
    price DESC NULLS LAST,
    item_id
)
INCLUDE (sku, title);
~~~

`category`, `price`, and `item_id` are **key columns** governing ordering and searchability.

`sku` and `title` inside `INCLUDE` are purely **attached payload columns**; they do not extend `ORDER BY` ordering and cannot serve as key predicates in the same manner.

### 21.1. Index-Only Scan Depends on More Than INCLUDE

For a query to use `Index Only Scan`, it also depends on:

- All needed columns being stored in the index.
- The access method supporting index-only scans.
- Visibility map / heap state and MVCC allowing heap reads to be reduced or skipped.
- Planner cost estimates favoring the plan.

**A covering index does not guarantee every query runs as an `Index Only Scan`.**

### 21.2. Do Not Overstuff INCLUDE Columns

Payload columns enlarge indexes and raise write overhead; huge values can exceed index entry limits and fail index creation or updates. Include only columns offering clear practical value.

## 22. Deterministic and Nondeterministic Collations

In modern PostgreSQL, collations can be **deterministic** or **nondeterministic**. A nondeterministic ICU collation can compare strings according to equivalence rules where distinct byte sequences evaluate as equal.

Typical business goals include:

- Case-insensitive matching.
- Accent-insensitive matching at a chosen strength level.
- Handling equivalent Unicode representations.

Do not assume any single collation automatically solves **all three** at once. Always verify locale, collation strength, normalization, and application rules.

### 22.1. Custom ICU Collation

If PostgreSQL is built with ICU support and privileges allow:

~~~sql
CREATE COLLATION idx_lab.name_ci (
    provider = icu,
    locale = 'und-u-ks-level2',
    deterministic = false
);
~~~

That locale specification targets case-insensitive comparisons at strength level 2 while typically remaining accent-sensitive. Availability depends on ICU and PostgreSQL versions; **do not treat this optional example as mandatory in every lab**.

### 22.2. Using the Collation

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY title COLLATE idx_lab.name_ci, item_id;
~~~

And if this query/collation pattern runs frequently:

~~~sql
CREATE INDEX idx_items_title_ci
ON idx_lab.items (title COLLATE idx_lab.name_ci);
~~~

### 22.3. Impact on UNIQUE Constraints and Equality

A **unique B-tree index** on text using a nondeterministic collation can treat strings deemed equivalent by that collation as **duplicate keys**, even when their underlying bytes differ.

While helpful for case-insensitive uniqueness, it requires a consistent policy from ingestion through constraint enforcement. Never switch an existing column's collation without first analyzing values that might suddenly collide as duplicates.

### 22.4. Pattern Matching Limitations Vary by Version

Different PostgreSQL versions impose restrictions or differences on `LIKE`/regex support with **nondeterministic collations**. Never assume pattern operators and opclasses behave identically under deterministic and nondeterministic collations.

If an application needs both case-insensitive equality and substring search, **verify behavior on your exact version and inspect plans**; you may need expression indexes, trigrams, normalization, or a dedicated search approach.

## 23. Collation Versions and ICU/libc Upgrades

Sorting rules governed by collation libraries (ICU or libc) can change across OS, PostgreSQL, or ICU upgrades. If a B-tree index was built under older comparison rules while the comparator changed, index entry ordering can become inconsistent with new comparisons.

Potential consequences:

- `ORDER BY` or index lookups returning incorrect results under the updated rules.
- Unique indexes behaving inconsistently regarding duplicate detection.
- Indexes needing to be rebuilt.

### 23.1. Checking Catalog Collation Versions

~~~sql
SELECT
    collname,
    collprovider,
    collversion,
    pg_collation_actual_version(oid) AS actual_version
FROM pg_collation
WHERE collname = 'name_ci'
   OR collname = 'C'
ORDER BY collname;
~~~

Collation names can exist across multiple schemas; in real systems, filter explicitly by `collnamespace`/schema. Some collations lack meaningful versions (returning null), and outputs vary by provider.

### 23.2. REINDEX Before Refreshing Metadata

When collation comparison rules change, you must **assess and rebuild affected indexes**, such as with `REINDEX` following operational procedures. Simply running:

~~~sql
ALTER COLLATION idx_lab.name_ci REFRESH VERSION;
~~~

**does not rebuild any index**; it only updates version metadata after compatibility issues have been resolved.

Never run version refresh solely to silence warnings while skipping required index rebuilds. Database default collations have additional database-level version tracking/refresh mechanisms depending on PostgreSQL version—follow documented upgrade procedures carefully.

### 23.3. Operational Impact of REINDEX

Standard `REINDEX` acquires locks affecting concurrent access; `REINDEX CONCURRENTLY` has its own mechanics and restrictions. Before running in production, plan scope, execution order, disk headroom, cancellation handling, and recovery steps.

## 24. Inspecting Actual Definitions with pg_indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'idx_lab'
  AND tablename = 'items'
ORDER BY indexname;
~~~

`indexdef` exposes `USING gin`, `COLLATE`, explicit opclasses, expressions like `lower(title)`, `DESC NULLS LAST` directions, and `INCLUDE` clauses if present.

### 24.1. Never Guess from Index Names Alone

A name like `idx_items_title_prefix` **does not prove** the index actually uses `text_pattern_ops` if schema definitions drifted. Truth lives in catalogs, not naming conventions.

### 24.2. pg_get_indexdef

~~~sql
SELECT
    idx.indexrelid::regclass AS index_name,
    pg_get_indexdef(idx.indexrelid) AS definition
FROM pg_index AS idx
WHERE idx.indrelid = 'idx_lab.items'::regclass
ORDER BY idx.indexrelid::regclass::text;
~~~

`pg_get_indexdef` reconstructs index definitions directly from catalog metadata, useful when comparing two indexes with similar columns that differ in opclass or collation.

## 25. Inspecting Per-Key Opclass and Collation

In modern PostgreSQL, `pg_index` stores opclass and collation OIDs per **key column**. You can inspect them directly:

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    pos.key_position + 1 AS key_number,
    pg_get_indexdef(
        i.indexrelid,
        pos.key_position + 1,
        true
    ) AS key_definition,
    opc.opcname AS operator_class,
    coll.collname AS collation_name
FROM pg_index AS i
CROSS JOIN LATERAL
    generate_series(0, i.indnkeyatts - 1)
    AS pos(key_position)
JOIN pg_opclass AS opc
    ON opc.oid = i.indclass[pos.key_position]
LEFT JOIN pg_collation AS coll
    ON coll.oid = i.indcollation[pos.key_position]
WHERE i.indrelid = 'idx_lab.items'::regclass
ORDER BY i.indexrelid::regclass::text, pos.key_position;
~~~

Details:

- `indnkeyatts` is the count of **key columns**, excluding `INCLUDE` payload columns.
- `indclass` stores opclass OIDs for keys.
- `indcollation` stores collation OIDs for collatable keys; numeric keys typically have no collation OID.
- `pg_get_indexdef(..., key_number, true)` prints each key expression.

### 25.1. Why Exclude INCLUDE Columns from This Loop?

`INCLUDE` columns belong to total index attributes, yet **are not search/sort keys** and do not have key opclasses in the same sense. When inspecting key ordering or opclasses, iterate over `indnkeyatts` rather than total `indnatts`.

## 26. Reading EXPLAIN to Verify Index Suitability

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, price
FROM idx_lab.items
WHERE category = 'book'
ORDER BY price DESC NULLS LAST, item_id
LIMIT 3;
~~~

Plan nodes you may encounter:

| Indicator | Meaning |
| --- | --- |
| `Index Scan using ...` | Planner uses the index to locate and traverse entries |
| `Index Only Scan` | Capable of returning data directly from index per MVCC rules |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Collects row locations via index bitmap; generally does not preserve B-tree output order |
| `Seq Scan` | Sequential heap scan |
| `Sort` | Explicit sorting step |
| `Incremental Sort` | Exploits an already sorted key prefix where eligible |
| `Index Cond` | Predicates handled by the index itself |
| `Filter` | Residual predicates checked after fetching candidate rows |
| `Buffers` | Per-node block counts (`hit`/`read`/`dirtied`/`written`) |

### 26.1. An Index Used for Filtering May Not Supply Order

A query using GIN `attrs @> ...` can use the index to find matching rows and then run `Sort` on `created_at`. Never interpret “uses an index” as “needs no sort.”

### 26.2. Index Scans Can Traverse Backward

In a plan, `Index Scan Backward` shows PostgreSQL scanning a B-tree in reverse when beneficial—direct evidence that `ORDER BY DESC` does not always require a separate `DESC` index.

### 26.3. Do Not Force Planner Flags to Judge Production Performance

Planner GUC flags are useful in labs to inspect candidate paths, yet turning off `enable_seqscan` is not a real optimization. On tiny tables, `Seq Scan` can legitimately win; always evaluate against representative datasets and statistics.

## 27. Adding Larger Data to Inspect Real Plans

A 10-row lab table is usually too small for the planner to prefer indexes. To observe index plans on a larger dataset, you can insert **10,000 synthetic items** in your test database:

~~~sql
INSERT INTO idx_lab.items (
    sku, title, category, price, created_at, attrs
)
SELECT
    'AUTO-' || lpad(g::text, 6, '0'),
    'Item ' || g::text,
    CASE
        WHEN g % 3 = 0 THEN 'book'
        WHEN g % 3 = 1 THEN 'drink'
        ELSE 'office'
    END,
    CASE
        WHEN g % 20 = 0 THEN NULL
        ELSE (10000 + (g % 500) * 100)::numeric(12,2)
    END,
    TIMESTAMPTZ '2026-02-01 00:00:00+00'
        + (g * INTERVAL '1 minute'),
    jsonb_build_object(
        'source', 'generated',
        'group', g % 5
    )
FROM generate_series(1, 10000) AS s(g);

ANALYZE idx_lab.items;
~~~

**Run this only if you want to observe plans on larger data.** Queries counting the original 10 items will no longer match earlier counts once executed.

### 27.1. Comparing Two Queries After Expanding Data

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, price
FROM idx_lab.items
WHERE category = 'book'
ORDER BY price DESC NULLS LAST, item_id
LIMIT 10;
~~~

versus:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, price
FROM idx_lab.items
WHERE category = 'book'
ORDER BY price ASC NULLS FIRST, item_id
LIMIT 10;
~~~

An index ordered `(category ASC, price DESC NULLS LAST, item_id ASC)` does not naturally deliver **both sort orders** cleanly in the same direction. Compare `Sort`, `Index Scan`, and total execution time.

### 27.2. Synthetic Data Cannot Replace Production Workloads

Generated rows are uniform with simple distributions. Base production conclusions on actual table sizes, skew, call rates, and live queries—not a few milliseconds in a lab.

## 28. Combining WHERE, ORDER BY, LIMIT, and Collation

Example query:

~~~sql
SELECT sku, title, price
FROM idx_lab.items
WHERE category = 'book'
  AND price >= 100000
ORDER BY price DESC NULLS LAST, item_id
LIMIT 20;
~~~

Step-by-step analysis:

1. `category = 'book'` is an equality filter on the leading key.
2. `price >= 100000` is a range predicate on the price key.
3. `ORDER BY price DESC NULLS LAST, item_id` requests descending price with nulls last and ascending tie-breaker ID.
4. `LIMIT 20` makes an ordered index scan especially attractive.

Now consider a different query:

~~~sql
SELECT sku, title
FROM idx_lab.items
WHERE lower(title) LIKE 'sa%'
ORDER BY title COLLATE "C"
LIMIT 20;
~~~

Here we have **two separate requirements**:

- Prefix filtering on expression `lower(title)`.
- Sorting by `title COLLATE "C"`, a different key.

A single index on `lower(title) text_pattern_ops` aids filtering, yet **does not supply ordering by raw `title`**. A sort step or different query/index design may be required.

## 29. Common Mistakes

### Mistake 1. Thinking Opclass and Collation Are the Same Thing

`text_pattern_ops` governs which pattern operators an index supports; `"C"` specifies collation comparison rules. They are two separate properties of an index key.

### Mistake 2. Creating a Default B-tree and Expecting Every LIKE to Be Fast

`LIKE 'abc%'` differs from `LIKE '%abc%'`. Prefix searches can use B-tree pattern matching; unanchored substring searches usually require trigrams or another search strategy.

### Mistake 3. Ignoring Locale When Using Prefix LIKE

Under non-`C` locales, a default B-tree may not accelerate prefix `LIKE` as expected; inspect `text_pattern_ops` and `EXPLAIN`.

### Mistake 4. Using text_pattern_ops for Every ORDER BY

Pattern ordering does not replace locale-aware B-tree ordering. If linguistic sorting is required, provide an index with matching collation.

### Mistake 5. Querying with ILIKE When Only a lower(title) Expression Index Exists

The planner does not necessarily rewrite `title ILIKE ...` into `lower(title) LIKE ...` to hit that expression index. Write the query to match the indexed expression or consider trigrams.

### Mistake 6. Treating lower() as Accent Removal

Case folding differs from stripping Vietnamese diacritics; handle these two requirements separately.

### Mistake 7. Assuming ORDER BY title Matches Across All Machines

Collations and library versions affect sorting. Never hardcode expected Vietnamese sort positions across unspecified environments.

### Mistake 8. Expecting an Index to Match a Different Query Collation

`ORDER BY title COLLATE "C"` generally cannot leverage an index built under a different linguistic collation.

### Mistake 9. Thinking DESC Always Needs a Dedicated DESC Index

B-trees support backward scans. Scanning an `ASC NULLS LAST` key backward yields `DESC NULLS FIRST`.

### Mistake 10. Forgetting NULLS FIRST/LAST

`DESC` defaults to nulls first; `DESC NULLS LAST` differs meaningfully on nullable columns.

### Mistake 11. Assuming Composite Indexes Sort Any Subset of Columns

An index on `(category ASC, price DESC)` cannot provide table-wide `ORDER BY price DESC` because entries are grouped by `category` first.

### Mistake 12. Omitting Tie-Breaker Keys

When multiple rows share the same `price`, `ORDER BY price DESC` alone leaves ordering nondeterministic. Add a unique tie-breaker like ID when stability matters.

### Mistake 13. Thinking INCLUDE Affects Ordering

`INCLUDE (title)` never turns `title` into a sort key. Only key columns and their directions govern index ordering.

### Mistake 14. Choosing jsonb_path_ops for Key-Existence Queries (?)

`jsonb_path_ops` does not index key-existence operators like `?` the way `jsonb_ops` does. Match opclass to actual query operators.

### Mistake 15. Expecting GIN JSONB Indexes to Satisfy ORDER BY

GIN accelerates containment and JSON search predicates, not general B-tree sort orders.

### Mistake 16. Creating Duplicate Indexes Because a Lab EXPLAIN Picked Seq Scan

Small tables naturally prefer sequential scans. Never conclude an opclass or index definition is broken based on 10 rows.

### Mistake 17. Upgrading Collations and Running Only REFRESH VERSION

`ALTER COLLATION ... REFRESH VERSION` does not rebuild indexes. Rebuild dependent indexes whenever underlying comparators change.

### Mistake 18. Assuming Nondeterministic Collations Support Every LIKE/Regex

Pattern operator support depends on PostgreSQL version and collation type. Always verify in your target environment.

### Mistake 19. Casting Columns in WHERE/ORDER BY Without Matching Expression Indexes

`price::text` or `lower(title)` is not the same key as the raw column for search/sort purposes. Simplify expressions or create matching expression indexes.

### Mistake 20. Running REINDEX CONCURRENTLY Inside Arbitrary Transaction Scripts

Concurrent index maintenance has strict transaction boundaries and operational considerations. Review command rules and plan migrations properly.

## 30. Hands-On Exercises

Exercises use schema `idx_lab`. Create new indexes only in a lab database. If you loaded the 10,000 synthetic rows from Section 27, evaluate plans on that expanded dataset.

### Exercise 1. Explain Index Components

In `CREATE INDEX ... ON t (title COLLATE "C" text_pattern_ops DESC NULLS LAST)`, identify the access method, collation, opclass, direction, and null placement.

### Exercise 2. Defaults

If you write `CREATE INDEX ix ON t(title)` on a `text` column, which access method and opclass does PostgreSQL typically pick?

### Exercise 3. Equality

Write a query looking up exact `sku = 'BK-001'` and a matching B-tree index.

### Exercise 4. Prefix Search

Write an index and query for `title LIKE 'Ca%'` in a database using a non-`C` collation. Why can `text_pattern_ops` help?

### Exercise 5. Substring

Does `title ILIKE '%sql%'` have a fixed prefix? Which access method/opclass could you try?

### Exercise 6. Case-Insensitive Prefix

Write an expression index for `lower(title) LIKE 'ca%'` along with its matching query.

### Exercise 7. Collation C

Write `ORDER BY title COLLATE "C"`. Does it guarantee natural Vietnamese dictionary order?

### Exercise 8. Collation Mismatch

Does an index on `title` with collation A automatically satisfy `ORDER BY title COLLATE B`?

### Exercise 9. Single-Column DESC

Why can an index on `price ASC NULLS LAST` serve default `ORDER BY price DESC` without adding another index?

### Exercise 10. DESC NULLS LAST

Why does `ORDER BY price DESC NULLS LAST` differ from `ORDER BY price DESC` when nulls exist? Write an index definition directly matching it.

### Exercise 11. Composite Index

Create an index on `category ASC, price DESC NULLS LAST, item_id ASC` and write a query filtering `category='book'` sorted by descending price.

### Exercise 12. Scan Reversal

If you scan the index from Exercise 11 backward, what ordering does it produce across the three keys?

### Exercise 13. Full-Table Sort

Why does `(category, price)` fail to guarantee table-wide `ORDER BY price`?

### Exercise 14. Tie-Breaker

Why can pagination ordered strictly by `price DESC` be unstable without adding `item_id`?

### Exercise 15. Include

Does `INCLUDE (sku,title)` make an index match `ORDER BY title` when `title` is not a key?

### Exercise 16. JSON Containment

Write a GIN index using `jsonb_path_ops` and a query filtering `attrs @> '{"color":"brown"}'`.

### Exercise 17. JSON Key Existence

If the application primarily runs `attrs ? 'stock'`, should you favor `jsonb_ops` or `jsonb_path_ops`?

### Exercise 18. GIN + ORDER BY

Does a GIN index on `attrs` return rows ordered by `created_at DESC` on its own? What else is needed?

### Exercise 19. ICU Nondeterministic Collations

How can nondeterministic collations affect equality and `UNIQUE` constraints? Why verify your PostgreSQL version when using `LIKE`?

### Exercise 20. Collation Version

What risk do ICU/libc version changes pose to B-trees? Does `ALTER COLLATION ... REFRESH VERSION` run `REINDEX` automatically?

### Exercise 21. Catalogs

Write queries against `pg_indexes` and `pg_opclass` to determine which opclass an index uses.

### Exercise 22. EXPLAIN

If a plan shows `Bitmap Index Scan` followed by `Sort`, what does that indicate about the chosen index's filtering vs. ordering capability?

### Exercise 23. Prefix vs. Linguistic Sorting

A page both filters `title LIKE 'Ca%'` and sorts `ORDER BY title` in a Vietnamese locale. Can one `pattern_ops` index definitely optimize both?

### Exercise 24. Designing Indexes from Workload

Given three query groups: (a) filter `category`, top 20 `price DESC NULLS LAST`; (b) substring `ILIKE` on `title`; (c) JSON key existence. Propose candidate indexes and how to verify them.

## 31. Suggested Answers

### Exercises 1–2. Structure

Without `USING`, the default access method is B-tree. `COLLATE "C"` is collation; `text_pattern_ops` is opclass; `DESC` and `NULLS LAST` are direction and null placement. A B-tree text index omitting opclass normally uses `text_ops`.

### Exercise 3. Equality

~~~sql
CREATE INDEX idx_items_sku
ON idx_lab.items (sku);

SELECT item_id, sku, title
FROM idx_lab.items
WHERE sku = 'BK-001';
~~~

For exact equality lookups, default B-tree is a standard choice. If `sku` must be unique per business rules, prefer a `UNIQUE` constraint/index rather than a plain index.

### Exercise 4. Prefix

~~~sql
CREATE INDEX idx_items_title_pattern
ON idx_lab.items (title text_pattern_ops);

SELECT sku, title
FROM idx_lab.items
WHERE title LIKE 'Ca%';
~~~

`text_pattern_ops` enables character-based prefix B-tree matching across many non-`C` locales.

### Exercise 5. Substring

`'%sql%'` has no fixed prefix. You can evaluate `pg_trgm` with GIN `gin_trgm_ops`:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_items_title_search
ON idx_lab.items USING gin (title gin_trgm_ops);
~~~

Account for extension installation permissions as well as pattern/data distributions.

### Exercise 6. LOWER Expression

~~~sql
CREATE INDEX idx_items_title_lower_pattern
ON idx_lab.items ((lower(title)) text_pattern_ops);

SELECT sku, title
FROM idx_lab.items
WHERE lower(title) LIKE 'ca%';
~~~

### Exercises 7–8. Collation

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY title COLLATE "C", item_id;
~~~

`"C"` is C/byte-oriented ordering and does not match Vietnamese dictionary ordering. An index built with collation A does not provide collation B ordering when their comparators differ.

### Exercises 9–10. Scan Direction and Nulls

A B-tree can scan `ASC NULLS LAST` backward to produce `DESC NULLS FIRST`, which matches default `ORDER BY DESC`.

However, `DESC NULLS LAST` requires nulls at the end:

~~~sql
CREATE INDEX idx_items_price_desc_last_answer
ON idx_lab.items (price DESC NULLS LAST);
~~~

### Exercise 11. Filter and Sort Index

~~~sql
CREATE INDEX idx_items_cat_price_answer
ON idx_lab.items (
    category ASC,
    price DESC NULLS LAST,
    item_id ASC
);

SELECT sku, price
FROM idx_lab.items
WHERE category = 'book'
ORDER BY price DESC NULLS LAST, item_id ASC
LIMIT 20;
~~~

### Exercise 12. Backward Scan

Resulting order: `category DESC`, `price ASC NULLS FIRST`, `item_id DESC`.

### Exercises 13–14. Composite Order and Tie-Breaker

An index `(category,price)` groups by `category` first, so it provides no global `price` ordering. Adding `item_id` to `ORDER BY` makes ordering deterministic across equal-priced items, though it alone does not prevent drift caused by concurrent mutations between pages.

### Exercise 15. INCLUDE

No. `INCLUDE` holds payload values for covering scans and does not govern B-tree sort order.

### Exercise 16. JSON Containment

~~~sql
CREATE INDEX idx_items_attrs_path_answer
ON idx_lab.items USING gin (attrs jsonb_path_ops);

SELECT sku
FROM idx_lab.items
WHERE attrs @> '{"color":"brown"}'::jsonb;
~~~

### Exercise 17. JSON Existence

Favor `jsonb_ops`, because it supports the key-existence operator `?`; `jsonb_path_ops` does not support that operator set.

### Exercise 18. GIN and Sort

GIN finds rows via supported search operators rather than yielding rows ordered by `created_at DESC` like an ordered B-tree scan. The planner must add a `Sort` or pick another access strategy.

### Exercises 19–20. ICU

Nondeterministic collations can treat distinct byte sequences as equal per configured comparison rules, affecting `=` and `UNIQUE`. Pattern operator support depends on version and setup. When ICU/libc rules change, affected indexes may require `REINDEX`; `REFRESH VERSION` updates metadata only and does not rebuild indexes.

### Exercise 21. Catalogs

~~~sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'idx_lab'
ORDER BY indexname;

SELECT
    am.amname, opc.opcname, opc.opcdefault
FROM pg_opclass AS opc
JOIN pg_am AS am ON am.oid = opc.opcmethod
WHERE opc.opcname IN (
    'text_ops',
    'text_pattern_ops',
    'jsonb_ops',
    'jsonb_path_ops'
)
ORDER BY am.amname, opc.opcname;
~~~

To inspect per-key opclasses, join `pg_index.indclass` with `pg_opclass` or read `pg_get_indexdef`.

### Exercise 22. Bitmap and Sort

The bitmap scan uses the index to gather matching row locations, yet does not preserve B-tree order for `ORDER BY`; `Sort` handles the remaining ordering step.

### Exercise 23. Prefix vs. Linguistic Order

Not necessarily. Pattern opclasses optimize character-level prefix lookup, whereas linguistic `ORDER BY title` needs matching collation order. Two indexes, a `Sort`, or adjusted query design may be required depending on the workload.

### Exercise 24. Proposed Indexes

~~~sql
-- (a) Equality filter + top-N price:
CREATE INDEX idx_items_cat_price_top
ON idx_lab.items (
    category,
    price DESC NULLS LAST,
    item_id
);

-- (b) Substring search, once pg_trgm is available:
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_items_title_substring
ON idx_lab.items USING gin (title gin_trgm_ops);

-- (c) JSON key existence:
CREATE INDEX idx_items_attrs_key
ON idx_lab.items USING gin (attrs jsonb_ops);
~~~

Next, inspect `EXPLAIN (ANALYZE, BUFFERS)` on representative queries and data; review `Index Cond`, `Sort`, buffers, row counts, and write overhead. Indexes should be tuned or pruned if workload measurements do not justify their cost.

## 32. Quick Reference Table

| Goal | Design Direction |
| --- | --- |
| Numeric equality and range comparisons | Default B-tree |
| Locale-aware `ORDER BY text` | B-tree with matching collation |
| Sort under `"C"` rules | Index key with `COLLATE "C"` when needed |
| `LIKE 'prefix%'` in non-`C` locales | B-tree `text_pattern_ops` / type variant |
| `lower(text) LIKE 'prefix%'` | Expression B-tree with pattern opclass |
| `ILIKE '%substring%'` | `pg_trgm` + GIN/GiST opclass when appropriate |
| JSONB containment `@>` | GIN `jsonb_ops` or `jsonb_path_ops` |
| JSONB key existence `?` | GIN `jsonb_ops` |
| Default `ORDER BY price DESC` | Backward scan of `ASC` B-tree possible |
| `ORDER BY price DESC NULLS LAST` | Pay attention to null order; consider matching B-tree |
| Category filter + top-N price | Composite B-tree `(category,price DESC...,id)` |
| Multi-key mixed ordering | Declare `ASC`/`DESC` per key |
| Covering query | Appropriate `INCLUDE`; never used as sort key |
| Inspect index definitions | `pg_indexes` / `pg_get_indexdef` |
| Inspect opclasses | `pg_opclass` + `pg_am` |
| Inspect collations | `pg_collation` |
| Verify plans | `EXPLAIN (ANALYZE, BUFFERS)` |
| Collation rule change on upgrade | Assess/rebuild affected indexes, then refresh version per runbook |

## 33. Pre-Creation Index Checklist

1. **Which operators do real queries use?** `=`, `LIKE 'a%'`, `ILIKE '%a%'`, `@>`, `?`, or `ORDER BY`?
2. **Which access method fits structurally?** B-tree, GIN, GiST, BRIN...?
3. **Does the default operator class support needed operators?** Or do you need `text_pattern_ops`/`jsonb_path_ops`?
4. **What are the column and query collations?** Do they differ from `"C"` or across environments?
5. **Are case- or accent-insensitive semantics required?** Have semantics and ICU versions been verified?
6. **Which direction and null placement does `ORDER BY` specify?** `ASC`/`DESC`/`NULLS FIRST/LAST`?
7. **Are composite index columns in the right order?** Do equality filters and ordering keys align?
8. **Is there a tie-breaker for stable pagination?** For instance `item_id`.
9. **Does the query expression match the index key?** `lower(title)` is not identical to `title`.
10. **Are you expecting a GIN index to provide ordering?** If so, the design mismatches the tool.
11. **Are there duplicate or near-duplicate indexes?** Each index increases storage and write amplification.
12. **Did you run `ANALYZE` and `EXPLAIN` on representative data?** Never extrapolate from a 10-row table.
13. **Do you track collation versions on upgrades?** Reindex dependent indexes per operational runbooks.
14. **Does deployment need `CONCURRENTLY`?** Understand transaction and locking rules before executing.

## 34. Summary

Understanding a PostgreSQL index requires looking beyond **column names**. You must evaluate **access method, operator class, collation, ordering, and key representation** together.

The **operator class** governs **which operators** PostgreSQL can accelerate with the index: default text B-tree works for general comparisons, `text_pattern_ops` helps prefix matching in certain locales, GIN `jsonb_ops` supports a broader JSON operator set than `jsonb_path_ops`, and trigrams enable certain substring searches.

**Collation** defines string comparison and sorting rules. An index on `title COLLATE "C"` does not automatically serve every linguistic `ORDER BY title`. ICU/libc upgrades can alter comparison rules, requiring careful **collation version management and `REINDEX`**, not just metadata refreshes.

**B-tree ordering** supports forward and backward scans, yet `ASC`/`DESC` and `NULLS FIRST`/`NULLS LAST` must align. In composite indexes, mixed column directions are key design choices for `WHERE ... ORDER BY ... LIMIT`.

Practical rule: **start from real queries, identify operators and collations, pick the right opclass and ordering structure, and verify with `EXPLAIN` on representative data**. That produces fewer, sharper indexes—avoiding misdirected tuning and keeping PostgreSQL systems maintainable.
