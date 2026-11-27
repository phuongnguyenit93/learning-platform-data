# Array Indexing vs. Junction Tables in PostgreSQL

## 1. When a column needs to store multiple values

A post may have multiple tags, a product may have multiple attributes, a lesson may belong to multiple topics, or a user may hold multiple permission codes. In PostgreSQL, there are two common modeling approaches:

1. **Array in a single column:** store elements of the same type in `integer[]`, `text[]`, or another array type; commonly paired with a **GIN index** for membership, containment, and overlap queries.
2. **Junction table:** a many-to-many relational model with one row per pair, such as `post_tags(post_id, tag_id)`; commonly paired with **B-tree indexes, PRIMARY KEY, and FOREIGN KEY** constraints to enforce integrity and support joins.

Example with a blog post:

~~~text
Approach A — array column:

posts_array
+---------+---------------------------+----------+
| post_id | title                     | tag_ids  |
+---------+---------------------------+----------+
| 101     | PostgreSQL Fundamentals   | {1,2,4}  |
| 102     | JSON and Arrays           | {1,5,6}  |
+---------+---------------------------+----------+

Approach B — junction table:

posts                              post_tags
+---------+--------------------+   +---------+--------+
| post_id | title              |   | post_id | tag_id |
+---------+--------------------+   +---------+--------+
| 101     | PostgreSQL ...     |   | 101     | 1      |
| 102     | JSON and Arrays    |   | 101     | 2      |
+---------+--------------------+   | 101     | 4      |
                                   | 102     | 1      |
                                   | 102     | 5      |
                                   | 102     | 6      |
                                   +---------+--------+
~~~

Both approaches can answer “which posts have the PostgreSQL tag?”. However, they differ significantly in **referential integrity, index structure, updates, reporting, element count limits, and data lifecycle**.

What matters is not picking whichever option feels “more modern,” but choosing **which model accurately represents the business relationship and fits the queries your workload runs most often**.

### Learning objectives

After completing this lesson, you will be able to:

- Understand PostgreSQL arrays, `integer[]`/`text[]` types, empty arrays, NULLs, duplicate elements, and element ordering.
- Correctly use array operators `@>`, `<@`, `&&`, and `=` in SQL.
- Distinguish `element = ANY(array_column)` from containment operators and understand why query shape affects index eligibility.
- Create a **GIN index** with `USING gin` and inspect `Bitmap Index Scan`/`Bitmap Heap Scan` with `EXPLAIN`.
- Distinguish GIN for membership queries from B-tree for whole-array comparisons.
- Design a normalized junction table with primary keys, foreign keys, and bidirectional indexes.
- Write equivalent queries for “has at least one tag,” “has all tags,” “has no tags,” and tag analytics reports.
- Evaluate array `UPDATE`s, MVCC, TOAST, GIN pending lists, locking, concurrency, and storage costs.
- Plan migrations between array columns and junction tables without losing data.
- Interpret benchmark results and select a design based on real-world constraints.

> **Scope:** this article focuses on SQL arrays and many-to-many relationships in PostgreSQL. JSONB has **different** operators and GIN operator classes from arrays and is compared separately to prevent confusion. Run hands-on SQL only in an authorized test database/schema. `EXPLAIN ANALYZE` executes the statement; for DML, always have a data-protection plan.

---

## 2. Before choosing an index: what semantics do arrays carry?

### 2.1. An array is an ordered value that can contain duplicates

PostgreSQL allows:

~~~sql
SELECT
    ARRAY[1, 2, 3]::integer[] AS normal_array,
    ARRAY[1, 1, 2]::integer[] AS duplicate_elements,
    ARRAY[]::integer[] AS empty_array,
    ARRAY[NULL, 2]::integer[] AS with_null;
~~~

An array **is not a mathematical set**:

- Element order matters for whole-array equality, subscript access, and `unnest`.
- Duplicate elements can still appear.
- NULL elements can exist unless prevented by application logic or a constraint.
- A **NULL array column** differs from an **empty array**, and both differ from an array containing a NULL element.

Example:

~~~sql
SELECT
    ARRAY[1,2]::integer[] = ARRAY[2,1]::integer[]
        AS same_ordered_value,
    ARRAY[1,1]::integer[] = ARRAY[1]::integer[]
        AS same_multiplicity,
    ARRAY[]::integer[] IS NULL
        AS empty_is_null,
    (NULL::integer[]) IS NULL
        AS null_array_is_null;
~~~

### 2.2. Containment does not count occurrences

PostgreSQL defines containment `@>` by **element presence**, without requiring matching multiplicity.

~~~sql
SELECT
    ARRAY[1]::integer[] @> ARRAY[1,1]::integer[]
        AS contains_both_occurrences,
    ARRAY[1,1]::integer[] @> ARRAY[1]::integer[]
        AS contains_one,
    ARRAY[1,2]::integer[] && ARRAY[2,3]::integer[]
        AS has_common_element;
~~~

All three expressions return `true`. This is decisive when using an array to represent a **tag set**: if duplicates are not prevented, a row can contain the same tag twice while `@>` queries report nothing unusual.

### 2.3. Multidimensional arrays are possible

~~~sql
SELECT ARRAY[[1,2],[3,4]]::integer[][] AS matrix;
~~~

Multidimensional arrays suit certain technical structures, but tag/membership problems should generally stick to **one-dimensional arrays**. PostgreSQL tracks dimensions and subscripts specifically, while `unnest` flattens elements in storage order. Do not use a multidimensional array to replace a complex relationship requiring foreign keys, per-pair uniqueness, or per-element metadata.

### 2.4. NULL array, empty array, and NULL element are three distinct cases

| Value | Conceptual meaning | `cardinality` |
|---|---|---|
| `NULL::integer[]` | Unknown / array data missing | NULL |
| `'{}'::integer[]` | Definitely zero elements | 0 |
| `ARRAY[NULL]::integer[]` | One element slot holding NULL | 1 |
| `ARRAY[1,2]::integer[]` | Two elements | 2 |

If “no tags assigned” means an empty array in your domain, declare `NOT NULL DEFAULT '{}'::integer[]` and enforce a rule against NULL elements.

### 2.5. Element types must be consistent

`integer[]` holds integers, `text[]` holds text, `uuid[]` holds UUIDs. PostgreSQL checks types; cast literals explicitly whenever ambiguity is possible:

~~~sql
SELECT ARRAY[1,2,3]::integer[] @> ARRAY[2]::integer[];
~~~

Do not rely on arbitrary implicit casts when an API passes JSON/text/UUID values, because operator resolution or index quals may differ.

---

## 3. Key array operators

Four primary operators relate to GIN `array_ops`:

| Operator | How to read | Example | Intuitive result |
|---|---|---|---|
| `a @> b` | a **contains all elements** of b | `'{1,2,3}'::int[] @> '{1,3}'::int[]` | true |
| `a <@ b` | a **is an element-wise subset** of b | `'{1,3}'::int[] <@ '{1,2,3}'::int[]` | true |
| `a && b` | a and b **share at least one element** | `'{1,2}'::int[] && '{2,4}'::int[]` | true |
| `a = b` | Two **array values are equal** | `'{1,2}'::int[] = '{2,1}'::int[]` | false |

Detailed explanation:

### 3.1. Has all tags: `@>`

~~~sql
SELECT ARRAY[1, 2, 4]::int[] @> ARRAY[1, 4]::int[]
       AS has_all_requested_tags;
~~~

If column `tag_ids` holds `{1,2,4}` and the user requests tags 1 **and** 4, the predicate is:

~~~sql
WHERE tag_ids @> ARRAY[1,4]::int[]
~~~

`@>` means **containment**, not “array greater than.”

### 3.2. Has any tag: `&&`

~~~sql
SELECT ARRAY[1, 2, 4]::int[] && ARRAY[4, 5]::int[]
       AS has_any_requested_tag;
~~~

If the application wants posts with tag 4 **or** 5:

~~~sql
WHERE tag_ids && ARRAY[4,5]::int[]
~~~

Note: `&&` on arrays means **element overlap**; the same symbol on range or geometry types has data-type-specific semantics.

### 3.3. Every tag of the post is in an allowed set: `<@`

~~~sql
SELECT ARRAY[1,4]::int[] <@ ARRAY[1,2,4,5]::int[]
       AS only_allowed_tags;
~~~

Find posts whose **assigned tags all** belong to the whitelist:

~~~sql
WHERE tag_ids <@ ARRAY[1,2,4,5]::int[]
~~~

This is not equivalent to “the post has all whitelist tags.” The containment direction is reversed.

### 3.4. Whole-array equality: `=`

~~~sql
SELECT ARRAY[1,2]::int[] = ARRAY[1,2]::int[] AS equal_value;
~~~

Equality checks order and element count. When the goal is “two posts share the same **set** of tags,” equality may fail unless stored arrays are canonicalized.

### 3.5. Empty arrays create special cases

~~~sql
SELECT
    ARRAY[1,2]::int[] @> ARRAY[]::int[]
        AS contains_empty_array,
    ARRAY[1,2]::int[] && ARRAY[]::int[]
        AS overlaps_empty_array,
    ARRAY[]::int[] <@ ARRAY[1,2]::int[]
        AS empty_is_contained;
~~~

Under standard element-set semantics:

- Every non-NULL array contains the empty array.
- Nothing overlaps an empty array.
- The empty array is a subset of every non-NULL array.

For “has all requested tags,” if the requested list is empty, `@> '{}'` evaluates to true for all rows (except SQL NULL). The API must define whether that matches intended behavior.

### 3.6. NULL is not treated like a normal tag

Under three-valued SQL logic, distinguish:

- Array column is NULL.
- Array contains a NULL element.
- Operator returns TRUE/FALSE/UNKNOWN by definition.

Never use `ARRAY[NULL]` to mean “empty tag”; if you must represent “tag unknown,” model that state explicitly. Set-like tag designs should forbid NULL elements via data validation.

---

## 4. Are `ANY`, `unnest`, and containment operators identical?

### 4.1. Checking one element with ANY

~~~sql
SELECT 4 = ANY(ARRAY[1,2,4]::int[]) AS has_four;
~~~

Against a column:

~~~sql
WHERE 4 = ANY(tag_ids)
~~~

This is natural, common, and semantically valid for many queries.

### 4.2. Why doesn't ANY automatically become a GIN index scan?

Built-in GIN `array_ops` is designed for **array operators** such as `@>`, `&&`, `<@`, and `=`. `4 = ANY(tag_ids)` is a **scalar-to-array comparison**, which the planner does not automatically rewrite into `tag_ids @> ARRAY[4]` to utilize GIN.

For membership workloads on a GIN-indexed array column, test the predicate:

~~~sql
WHERE tag_ids @> ARRAY[4]::int[]
~~~

And **verify with `EXPLAIN`**. Do not assert blindly that every `ANY` query always uses or fails to use another index; expressions, PostgreSQL versions, and alternative access paths influence the plan.

### 4.3. Subtle but important difference with NULL

When an array contains NULL elements and no value matches, `4 = ANY(tag_ids)` returns **UNKNOWN**, whereas containment can have different semantics. Inside `WHERE`, only TRUE retains rows, so some rewrites return the **same selected rows**, yet they are **not identically equivalent boolean expressions** in all contexts.

For example, when returning a boolean column to an API, apply `COALESCE` or enforce strict NULL constraints before substituting one expression for another.

### 4.4. `unnest` expands an array into rows

~~~sql
SELECT t.tag_id
FROM unnest(ARRAY[1,2,4]::int[]) AS t(tag_id);
~~~

When counting tags, joining with a tags table, or aggregating, `unnest` is useful. However:

~~~sql
WHERE 4 IN (SELECT unnest(tag_ids))
~~~

is not the syntax to use for leveraging a GIN index on `tag_ids`. It forces repeated unnesting; for straightforward membership, prefer an indexable array operator or a junction table.

### 4.5. Choose expressions by meaning, not only by index

| Business question | Appropriate array expression |
|---|---|
| Has tag 4? | `tag_ids @> ARRAY[4]::int[]` or `4 = ANY(tag_ids)` |
| Has tag 4 **and** 5? | `tag_ids @> ARRAY[4,5]::int[]` |
| Has tag 4 **or** 5? | `tag_ids && ARRAY[4,5]::int[]` |
| All tags in whitelist? | `tag_ids <@ ARRAY[1,2,4,5]::int[]` |
| Has zero tags? | `cardinality(tag_ids) = 0` when NOT NULL |
| Exactly that array value in that order? | `tag_ids = ARRAY[1,2]::int[]` |
| Count tags on a post? | `cardinality(tag_ids)`, watch out for duplicates |
| Count posts per tag? | `unnest` + `GROUP BY` / or junction table |

---

## 5. GIN indexes: the inverted index idea

### 5.1. What is GIN?

**GIN (Generalized Inverted Index)** indexes the **internal components/keys within a composite value**. For tag arrays, picture it conceptually as:

~~~text
posts_array rows
101 -> {1,2,4}
102 -> {1,5,6}
103 -> {2,3}
104 -> {3,4}
105 -> {}
106 -> {1,3,4}

GIN (logical "element -> row list" view):
  tag 1 -> 101, 102, 106
  tag 2 -> 101, 103
  tag 3 -> 103, 104, 106
  tag 4 -> 101, 104, 106
  tag 5 -> 102
  tag 6 -> 102
~~~

This illustrates **inverted entries / posting lists**, not the physical byte layout of GIN pages. PostgreSQL internally uses index tuples, posting lists, posting trees, and GIN maintenance mechanisms.

### 5.2. Why GIN fits array membership

For:

~~~sql
WHERE tag_ids @> ARRAY[1,4]::int[]
~~~

GIN gathers candidate row locations from keys 1 and 4 and checks the matching condition without necessarily decoding every array across the whole table. For:

~~~sql
WHERE tag_ids && ARRAY[4,5]::int[]
~~~

it locates rows containing at least one key from the query set.

Effectiveness depends on tag frequency, elements per row, table size, selectivity, and cache state.

### 5.3. The array_ops operator class

To inspect the built-in GIN operator class for arrays:

~~~sql
SELECT
    am.amname AS access_method,
    opc.opcname AS operator_class,
    opc.opcintype::regtype AS input_type,
    opc.opcdefault
FROM pg_opclass AS opc
JOIN pg_am AS am ON am.oid = opc.opcmethod
WHERE am.amname = 'gin'
  AND opc.opcname = 'array_ops';
~~~

Core `array_ops` supports the essential array operators; for standard array columns:

~~~sql
CREATE INDEX idx_posts_tag_ids_gin
ON array_lab.posts_array
USING gin(tag_ids);
~~~

selects the appropriate default GIN operator class.

### 5.4. GIN is not a UNIQUE constraint on elements

A GIN index on `tag_ids` **does not prevent**:

- Two posts sharing tag 1.
- A single post containing `{1,1,2}`.
- A tag ID missing from the tags dictionary table.
- A post accumulating too many tags.

Indexes accelerate lookups; they **do not replace** PRIMARY KEY, FOREIGN KEY, CHECK constraints, or business rules.

### 5.5. One GIN index can serve multiple array queries

The same `USING gin(tag_ids)` index can support:

~~~sql
WHERE tag_ids @> ARRAY[1,4]::int[]
WHERE tag_ids && ARRAY[3,5]::int[]
WHERE tag_ids <@ ARRAY[1,2,3,4]::int[]
WHERE tag_ids = ARRAY[1,2]::int[]
~~~

However, “the operator class supports the operator” differs from “the planner will definitely pick the index” and “the index is always faster.” Under low selectivity, Seq Scan can win.

---

## 6. What role does a B-tree index on an array play?

### 6.1. B-tree supports whole-array comparisons

PostgreSQL defines ordering and equality across entire array values based on element types and dimensions/subscripts. Thus you can create a B-tree index on an array column when appropriate:

~~~sql
CREATE INDEX idx_posts_exact_tag_array
ON array_lab.posts_array USING btree(tag_ids);
~~~

This index serves **whole-array equality** or range/sort ordering under array comparator semantics; it is not an inverted index over individual tags.

### 6.2. B-tree does not replace GIN for “contains tag”

A B-tree index on `tag_ids` **cannot automatically** accelerate:

~~~sql
WHERE tag_ids @> ARRAY[4]::int[]
~~~

because this predicate inspects **an element inside the array value**, rather than comparing the entire array value against an intact search key.

### 6.3. B-tree can help exact canonical arrays

If the application normalizes tags into sorted, deduplicated arrays and queries for “posts with exact tag set {1,2},” B-tree equality can be an option:

~~~sql
WHERE tag_ids = ARRAY[1,2]::int[]
~~~

For equality to represent set equality, however, you must **canonicalize order and duplicates** on write; GIN does not enforce those rules automatically.

### 6.4. Expression indexes for element counts

If the workload frequently searches for untagged posts:

~~~sql
WHERE cardinality(tag_ids) = 0
~~~

you might consider a B-tree expression index:

~~~sql
CREATE INDEX idx_posts_tag_count
ON array_lab.posts_array ((cardinality(tag_ids)));
~~~

Or a partial index covering untagged post IDs:

~~~sql
CREATE INDEX idx_posts_without_tags
ON array_lab.posts_array(post_id)
WHERE cardinality(tag_ids) = 0;
~~~

These two indexes are **alternative test candidates**, not both required at once. They serve predicates on **element count**, unlike GIN membership. On tables with only a few rows, the maintenance cost exceeds any benefit.

---

## 7. Unified lab dataset for arrays and junction tables

Let's use a shared dataset to compare both models. All examples stay within a dedicated schema without touching production tables.

### 7.1. Create the schema and tag catalog

~~~sql
CREATE SCHEMA IF NOT EXISTS array_lab;

CREATE TABLE array_lab.tags (
    tag_id INTEGER PRIMARY KEY,
    tag_name TEXT NOT NULL UNIQUE
);

INSERT INTO array_lab.tags(tag_id,tag_name)
VALUES
    (1, 'PostgreSQL'),
    (2, 'SQL'),
    (3, 'Java'),
    (4, 'Performance'),
    (5, 'JSON'),
    (6, 'Array');
~~~

The tag catalog highlights an important limitation of `int[]`: PostgreSQL does not provide a **per-element FOREIGN KEY** directly referencing `tags(tag_id)` the way a junction table enforces FKs on scalar columns.

### 7.2. Create posts with an array column

~~~sql
CREATE TABLE array_lab.posts_array (
    post_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    tag_ids INTEGER[] NOT NULL DEFAULT '{}'::integer[],
    CHECK (array_position(tag_ids, NULL) IS NULL)
);
~~~

- `NOT NULL` ensures the array column itself cannot be NULL.
- `DEFAULT '{}'::integer[]` represents an untagged post as an empty array.
- `array_position(tag_ids, NULL) IS NULL` forbids **NULL elements** inside a **one-dimensional** array where PostgreSQL supports this function. `array_position` uses matching semantics capable of finding NULL elements.

**This constraint does not forbid duplicate elements**; `{1,1}` can still be inserted unless prevented elsewhere.

### 7.3. Load six posts

~~~sql
INSERT INTO array_lab.posts_array(post_id,title,tag_ids)
VALUES
    (101, 'PostgreSQL Fundamentals',  ARRAY[1,2,4]),
    (102, 'JSON and Arrays',       ARRAY[1,5,6]),
    (103, 'Java Connecting to SQL',   ARRAY[2,3]),
    (104, 'Optimizing Java',        ARRAY[3,4]),
    (105, 'Untagged Post',   ARRAY[]::integer[]),
    (106, 'Java with PostgreSQL',ARRAY[1,3,4]);

SELECT post_id, title, tag_ids, cardinality(tag_ids) AS tag_count
FROM array_lab.posts_array
ORDER BY post_id;
~~~

Expected output (when run once on an empty table):

| post_id | title | tag_ids | Element count |
|---:|---|---|---:|
| 101 | PostgreSQL Fundamentals | `{1,2,4}` | 3 |
| 102 | JSON and Arrays | `{1,5,6}` | 3 |
| 103 | Java Connecting to SQL | `{2,3}` | 2 |
| 104 | Optimizing Java | `{3,4}` | 2 |
| 105 | Untagged Post | `{}` | 0 |
| 106 | Java with PostgreSQL | `{1,3,4}` | 3 |

### 7.4. Create a GIN index

~~~sql
CREATE INDEX idx_posts_array_tag_ids_gin
ON array_lab.posts_array USING gin (tag_ids);

ANALYZE array_lab.posts_array;
~~~

This creates a GIN index for array operators. `ANALYZE` updates planner statistics; it does **not force** queries to pick the index.

### 7.5. Tiny datasets usually pick Seq Scan

A six-row table is almost always faster via Seq Scan than a GIN lookup followed by heap fetches. So if `EXPLAIN` shows:

~~~text
Seq Scan on posts_array ...
~~~

do not treat that as a bug. Later sections show how to generate a larger synthetic lab dataset to compare realistic costs.

---

## 8. Array queries: single tag, multiple tags, whitelist, and untagged posts

### 8.1. Posts with the PostgreSQL tag (1)

~~~sql
SELECT post_id, title, tag_ids
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1]::integer[]
ORDER BY post_id;
~~~

Expected result: **101, 102, 106**.

### 8.2. Posts with both PostgreSQL (1) and Performance (4)

~~~sql
SELECT post_id, title, tag_ids
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1,4]::integer[]
ORDER BY post_id;
~~~

Expected result: **101, 106**.

### 8.3. Posts with at least one of JSON (5) or Performance (4)

~~~sql
SELECT post_id, title, tag_ids
FROM array_lab.posts_array
WHERE tag_ids && ARRAY[4,5]::integer[]
ORDER BY post_id;
~~~

Expected result: **101, 102, 104, 106**.

### 8.4. Posts whose tags all belong to {1,2,4}

~~~sql
SELECT post_id, title, tag_ids
FROM array_lab.posts_array
WHERE tag_ids <@ ARRAY[1,2,4]::integer[]
ORDER BY post_id;
~~~

Expected result: **101, 105**. Post 105 has an empty array, which is a subset of the whitelist under containment semantics.

### 8.5. Untagged posts

~~~sql
SELECT post_id, title
FROM array_lab.posts_array
WHERE cardinality(tag_ids) = 0
ORDER BY post_id;
~~~

Expected result: **105**. With the `NOT NULL` design, this is the reliable expression. Do not use `tag_ids IS NULL` to look for empty arrays.

### 8.6. Posts without a specific tag

~~~sql
SELECT post_id, title
FROM array_lab.posts_array
WHERE NOT (tag_ids @> ARRAY[4]::integer[])
ORDER BY post_id;
~~~

With non-NULL arrays, expected result: **102, 103, 105**. Negated predicates like this rarely gain much from GIN to skip most of a table; always measure on real data.

### 8.7. A crucial point about negative predicates

GIN excels at locating **specific keys that are present**. “Does not contain tag X” typically matches the majority of rows and still inspects many records. Never assume `NOT(tag_ids && ...)` performs as well as `tag_ids && ...`.

---

## 9. Inspecting GIN plans

### 9.1. EXPLAIN before running

~~~sql
EXPLAIN
SELECT post_id, title
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1,4]::integer[];
~~~

### 9.2. EXPLAIN ANALYZE, BUFFERS

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT post_id, title
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1,4]::integer[];
~~~

An illustrative plan when the planner uses GIN:

~~~text
Bitmap Heap Scan on posts_array
  Recheck Cond: (tag_ids @> '{1,4}'::integer[])
  Buffers: shared hit=...
  -> Bitmap Index Scan on idx_posts_array_tag_ids_gin
       Index Cond: (tag_ids @> '{1,4}'::integer[])
~~~

**Not guaranteed** on a six-row table. Seq Scan may still be chosen because it is cheaper.

### 9.3. Explaining each node

- **Bitmap Index Scan:** finds candidate tuple locations via GIN.
- **Bitmap Heap Scan:** fetches matching rows from the heap.
- **Index Cond:** condition used to probe the index.
- **Recheck Cond:** executor re-evaluates the predicate when heap bitmaps or index semantics require it.
- **Buffers:** buffer page accesses, not row counts.

### 9.4. Recheck does not mean the index returns wrong rows to the app

An index scan or lossy bitmap supplies candidates, and the executor guarantees only rows satisfying the predicate are returned. `Recheck Cond` does not indicate broken indexes. Inspect `Heap Blocks: exact/lossy`, `Rows Removed by Index Recheck` if printed, and the exact conditions.

### 9.5. EXPLAIN ANALYZE executes the statement

Fine for lab SELECTs. For UPDATE/DELETE:

~~~sql
-- DO NOT run in production just to "peek at the plan":
EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM array_lab.posts_array WHERE post_id = 101;
~~~

`ANALYZE` here **actually deletes the row**. To view only estimated DML plans, run `EXPLAIN` without ANALYZE; if you must benchmark DML, run inside a controlled transaction on a test database and watch out for non-rollbackable side effects.

---

## 10. From a post with a tag list to a many-to-many relationship

### 10.1. Normalized model

A junction table represents **each post–tag pair as its own row**:

~~~text
posts_rel                 post_tags                 tags
+---------+-------+        +---------+--------+      +--------+-------------+
| post_id | title |        | post_id | tag_id |      | tag_id | tag_name    |
+---------+-------+        +---------+--------+      +--------+-------------+
| 101     | ...   |<-------| 101     | 1      |----->| 1      | PostgreSQL  |
| 102     | ...   |        | 101     | 2      |      | 2      | SQL         |
| ...     | ...   |        | 101     | 4      |      | 4      | Performance |
+---------+-------+        | 102     | 1      |      | ...    | ...         |
                           +---------+--------+      +--------+-------------+
~~~

This is a **many-to-many** relationship: a post has many tags, and a tag belongs to many posts.

### 10.2. Create posts_rel

~~~sql
CREATE TABLE array_lab.posts_rel (
    post_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL
);
~~~

### 10.3. Create post_tags with referential integrity

~~~sql
CREATE TABLE array_lab.post_tags (
    post_id BIGINT NOT NULL
        REFERENCES array_lab.posts_rel(post_id)
        ON DELETE CASCADE,
    tag_id INTEGER NOT NULL
        REFERENCES array_lab.tags(tag_id),
    PRIMARY KEY (post_id, tag_id)
);
~~~

Explanation:

- `post_id` must reference a real post.
- `tag_id` must reference a real tag.
- `PRIMARY KEY(post_id,tag_id)` prevents **attaching the same tag twice to one post**.
- `NOT NULL` is implied by PK, though writing it explicitly clarifies intent.
- `ON DELETE CASCADE` on `post_id` removes links when a post is deleted without deleting rows from the tag dictionary.
- Avoid putting `ON DELETE CASCADE` on `tag_id` by default if business rules require blocking deletion of tags still in use.

### 10.4. Populate junction rows from the array lab data

~~~sql
INSERT INTO array_lab.posts_rel(post_id,title)
SELECT post_id,title
FROM array_lab.posts_array;
~~~

Since the lab arrays contain no duplicates or NULLs:

~~~sql
INSERT INTO array_lab.post_tags(post_id,tag_id)
SELECT p.post_id, t.tag_id
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS t(tag_id);
~~~

**These two lab models exist for comparison, not as a recommendation to keep dual copies in production automatically.** Any production transition must handle concurrent writes and consistency.

### 10.5. Bidirectional indexes

The PK `(post_id,tag_id)` creates a B-tree suited to “get all tags for a post”:

~~~sql
SELECT tag_id
FROM array_lab.post_tags
WHERE post_id=101;
~~~

Meanwhile, “find all posts with tag 4” benefits from the **reverse index**:

~~~sql
CREATE INDEX idx_post_tags_tag_post
ON array_lab.post_tags(tag_id,post_id);
~~~

This composite B-tree filters on `tag_id` and reads `post_id` directly inside the index in suitable plans; in PostgreSQL, a PK on `(post_id,tag_id)` is not an efficient substitute for `tag_id`-first lookups on large junction tables.

### 10.6. Foreign keys and indexes are separate concerns

Creating a FOREIGN KEY **does not automatically create an index on the referencing FK column**. PostgreSQL requires an index/unique constraint on the referenced side, whereas you should proactively index the referencing side whenever workloads look up, delete, or update related links. For `post_tags`, the PK serves `post_id` and `idx_post_tags_tag_post` serves `tag_id`.

---

## 11. Querying the junction table: any/all/none

### 11.1. Has tag 1

~~~sql
SELECT p.post_id, p.title
FROM array_lab.posts_rel AS p
JOIN array_lab.post_tags AS pt
  ON pt.post_id = p.post_id
WHERE pt.tag_id=1
ORDER BY p.post_id;
~~~

Expected result: **101, 102, 106**.

The PK `(post_id,tag_id)` ensures a post cannot have multiple rows for tag 1, so no `DISTINCT` is needed just to paper over duplicate links.

### 11.2. Has either tag 4 or 5

Use `EXISTS` to avoid duplicating a post that carries both 4 and 5:

~~~sql
SELECT p.post_id, p.title
FROM array_lab.posts_rel AS p
WHERE EXISTS (
    SELECT 1
    FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id
      AND pt.tag_id IN (4,5)
)
ORDER BY p.post_id;
~~~

Expected result: **101, 102, 104, 106**.

Using `JOIN ... WHERE tag_id IN (4,5)` would emit **two rows** for a post carrying both tags. When one row per post is desired, use `EXISTS` or `SELECT DISTINCT` with an eye on cost and semantics.

### 11.3. Has both tag 1 and tag 4

A clean pattern uses two `EXISTS` clauses:

~~~sql
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE EXISTS (
    SELECT 1 FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id AND pt.tag_id=1
)
AND EXISTS (
    SELECT 1 FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id AND pt.tag_id=4
)
ORDER BY p.post_id;
~~~

Expected result: **101, 106**.

### 11.4. Has all tags in a dynamic set

When the target set is normalized into a **distinct non-NULL** list:

~~~sql
WITH requested(tag_id) AS (
    VALUES (1), (4)
)
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
JOIN array_lab.post_tags AS pt
  ON pt.post_id=p.post_id
JOIN requested AS r
  ON r.tag_id=pt.tag_id
GROUP BY p.post_id,p.title
HAVING COUNT(DISTINCT pt.tag_id) =
       (SELECT COUNT(DISTINCT tag_id) FROM requested)
ORDER BY p.post_id;
~~~

Expected result: **101, 106**. This is *relational division*: “posts containing every tag in the requested set.”

Clarify what should happen when **`requested` is empty**: this JOIN query returns zero rows, whereas `@> '{}'` on non-NULL arrays returns all posts. If you want “vacuous truth” semantics, handle empty inputs explicitly or use a nested `NOT EXISTS` pattern.

### 11.5. Does not have tag 4

~~~sql
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id
      AND pt.tag_id=4
)
ORDER BY p.post_id;
~~~

Expected result: **102, 103, 105**.

### 11.6. Has no tags at all

~~~sql
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id
)
ORDER BY p.post_id;
~~~

Expected result: **105**. In a junction table, **absence of link rows** represents an empty tag set; never insert a fake row with `tag_id=NULL`.

---

## 12. Tag statistics and aggregation queries

Real-world workloads rarely stop at “find posts with a tag.” Product teams also need popular tags, posts with the most tags, most recent tag assignment, display order, or tag co-occurrence metrics.

### 12.1. Post count per tag — array model

~~~sql
SELECT
    t.tag_id,
    d.tag_name,
    COUNT(DISTINCT p.post_id) AS posts_count
FROM array_lab.tags AS d
JOIN (
    SELECT p.post_id, u.tag_id
    FROM array_lab.posts_array AS p
    CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
) AS t
    ON t.tag_id=d.tag_id
JOIN array_lab.posts_array AS p
    ON p.post_id=t.post_id
GROUP BY t.tag_id,d.tag_name
ORDER BY posts_count DESC, t.tag_id;
~~~

This illustrates `unnest` and `COUNT(DISTINCT post_id)`. It can be written more concisely as:

~~~sql
SELECT
    d.tag_id,
    d.tag_name,
    COUNT(DISTINCT p.post_id) AS posts_count
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
JOIN array_lab.tags AS d
  ON d.tag_id=u.tag_id
GROUP BY d.tag_id,d.tag_name
ORDER BY posts_count DESC,d.tag_id;
~~~

If an array has duplicate elements, `COUNT(*)` **counts element occurrences**, whereas `COUNT(DISTINCT p.post_id)` counts **distinct posts carrying that tag**. That difference matters.

### 12.2. Post count per tag — junction model

~~~sql
SELECT
    d.tag_id,
    d.tag_name,
    COUNT(*) AS posts_count
FROM array_lab.post_tags AS pt
JOIN array_lab.tags AS d
  ON d.tag_id=pt.tag_id
GROUP BY d.tag_id,d.tag_name
ORDER BY posts_count DESC,d.tag_id;
~~~

Because `PRIMARY KEY(post_id,tag_id)` forbids duplicate pairs, `COUNT(*)` matches the number of tagged posts. To **include tags used by zero posts**, switch to LEFT JOIN:

~~~sql
SELECT
    d.tag_id,
    d.tag_name,
    COUNT(pt.post_id) AS posts_count
FROM array_lab.tags AS d
LEFT JOIN array_lab.post_tags AS pt
  ON pt.tag_id=d.tag_id
GROUP BY d.tag_id,d.tag_name
ORDER BY d.tag_id;
~~~

Do not use `COUNT(*)` with LEFT JOIN when unused tags should display 0; LEFT JOIN emits one row with NULL `pt` columns, turning `COUNT(*)` into 1.

### 12.3. Tag count per post — array model

~~~sql
SELECT
    post_id,
    title,
    cardinality(tag_ids) AS elements_count
FROM array_lab.posts_array
ORDER BY elements_count DESC,post_id;
~~~

`cardinality` counts **elements**, including duplicates and NULLs if present. It does not automatically deduplicate distinct tags.

### 12.4. Tag count per post — junction model

~~~sql
SELECT
    p.post_id,
    p.title,
    COUNT(pt.tag_id) AS distinct_tags_count
FROM array_lab.posts_rel AS p
LEFT JOIN array_lab.post_tags AS pt
  ON pt.post_id=p.post_id
GROUP BY p.post_id,p.title
ORDER BY distinct_tags_count DESC,p.post_id;
~~~

Because the PK prevents duplicate post–tag pairs, link row count equals distinct tag count. Post 105 with zero links cleanly reports 0.

### 12.5. Fetching tag names for display — array model

~~~sql
SELECT
    p.post_id,
    p.title,
    COALESCE(
        array_agg(d.tag_name ORDER BY u.ordinality)
            FILTER (WHERE d.tag_id IS NOT NULL),
        '{}'::text[]
    ) AS tag_names
FROM array_lab.posts_array AS p
LEFT JOIN LATERAL unnest(p.tag_ids)
    WITH ORDINALITY AS u(tag_id,ordinality)
    ON true
LEFT JOIN array_lab.tags AS d
    ON d.tag_id=u.tag_id
GROUP BY p.post_id,p.title
ORDER BY p.post_id;
~~~

`WITH ORDINALITY` preserves the array's element order. If an ID in the array is missing from the dictionary, LEFT JOIN yields a NULL `tag_name`; here the filter excludes missing dictionary entries from display, yet **real systems should never silently ignore orphan IDs**—audit and fix them.

### 12.6. Fetching tag names — junction model

~~~sql
SELECT
    p.post_id,
    p.title,
    COALESCE(
        array_agg(d.tag_name ORDER BY d.tag_id)
            FILTER (WHERE d.tag_id IS NOT NULL),
        '{}'::text[]
    ) AS tag_names
FROM array_lab.posts_rel AS p
LEFT JOIN array_lab.post_tags AS pt ON pt.post_id=p.post_id
LEFT JOIN array_lab.tags AS d ON d.tag_id=pt.tag_id
GROUP BY p.post_id,p.title
ORDER BY p.post_id;
~~~

Here display order is determined by `ORDER BY d.tag_id`. A junction table does not store insertion order by default; if user-defined ordering is required, add an explicit `position` column.

### 12.7. Comparing aggregation costs

A GIN index on an array **does not guarantee** that `CROSS JOIN LATERAL unnest(...) GROUP BY` accelerates like a GIN point lookup. When analytics scan every tag of every post, unnesting every array can dominate execution cost.

A junction table stores each edge as a row, and with `(tag_id,post_id)` indexing and normal relational planner statistics it often fits tag-level reporting, dimension joins, and multi-stage analytics much more naturally.

---

## 13. Relational model: data integrity is a huge advantage

### 13.1. Arrays lack per-element foreign keys

Suppose an app executes:

~~~sql
INSERT INTO array_lab.posts_array(post_id,title,tag_ids)
VALUES (201,'Non-existent tag',ARRAY[9999]);
~~~

With the array schema, this statement **is not rejected by any FK to `tags`** because no per-element foreign key exists. To reject tag 9999, you need **application/trigger/transactional validation** or a different model.

In the junction table:

~~~sql
INSERT INTO array_lab.post_tags(post_id,tag_id)
VALUES (101,9999);
~~~

immediately violates the FOREIGN KEY referencing `tags(tag_id)` if tag 9999 does not exist. No custom trigger is required to catch it.

> The two INSERTs above are illustrative. If you ran the first one, record 201 remains in the lab until cleaned up; do not leave invalid data around when running fair comparisons between the two models.

### 13.2. No default per-element uniqueness in arrays

~~~sql
SELECT ARRAY[1,1,2]::integer[] AS tags_with_duplicates;
~~~

PostgreSQL does not forbid duplicate elements automatically, and a GIN index **does not** enforce uniqueness either. In `post_tags`, `PRIMARY KEY(post_id,tag_id)` prevents duplicate pairs across all transactions.

If an array needs “set” semantics, an application can normalize:

~~~sql
SELECT COALESCE(
    array_agg(DISTINCT elem ORDER BY elem),
    '{}'::integer[]
) AS canonical_tags
FROM unnest(ARRAY[2,1,1,4]::integer[]) AS u(elem);
~~~

Result: `{1,2,4}`. However, normalizing on read **does not guarantee** every writer stored canonical arrays; enforcement requires write-path checks or schema constraints.

### 13.3. Deleting tags and updating metadata

Suppose tag 3 must be removed:

- **Junction table:** an FK blocks deleting a tag still referenced, or you can deliberately set `ON DELETE CASCADE` on the tag FK per business policy.
- **ID array:** deleting `tags.tag_id=3` does not automatically detect arrays still holding 3 unless custom cleanup/validation runs.
- **Name array:** renaming a tag can force rewriting huge numbers of arrays; a dictionary + linked IDs only updates one row's `tag_name`.

Whenever a tag carries a name, description, language, creator, permissions, and lifecycle status, a dedicated `tags` dictionary table pays off regardless of which membership structure you pick.

### 13.4. Relationships with their own attributes

Business requirements may ask:

- Who assigned this tag?
- When was it assigned?
- Was the tag auto-suggested by the system or manually added by a user?
- Does the tag have a priority or display order?
- Is it the post's primary tag?

A junction table extends naturally:

~~~sql
-- Example schema extension; run only if modifying the lab:
ALTER TABLE array_lab.post_tags
ADD COLUMN assigned_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE array_lab.post_tags
ADD COLUMN assigned_by BIGINT;
~~~

These attributes **belong to the post–tag edge**, not to the post or tag alone. That is a strong signal to use a junction table instead of maintaining parallel arrays (`tags[]`, `assigned_at[]`, `assigned_by[]`) synced by index position—a fragile design prone to drift.

### 13.5. When tag ordering is needed

If users drag-and-drop tags into order, the junction table can add:

~~~sql
ALTER TABLE array_lab.post_tags
ADD COLUMN display_order INTEGER;
~~~

along with appropriate constraints. Decide whether the same tag can appear more than once. With `PK(post_id,tag_id)`, each tag appears at most once while `display_order` records its rank.

---

## 14. Modifying data: array UPDATE vs. junction INSERT/DELETE

### 14.1. Adding a tag to an array

Adding tag 5 to post 103 only if not already present:

~~~sql
UPDATE array_lab.posts_array
SET tag_ids = array_append(tag_ids,5)
WHERE post_id=103
  AND NOT (tag_ids @> ARRAY[5]::integer[]);
~~~

This is a single-row UPDATE. It creates a **new MVCC row version** and requires maintaining the GIN index since the indexed array column changed.

### 14.2. Removing a tag from an array

~~~sql
UPDATE array_lab.posts_array
SET tag_ids = array_remove(tag_ids,5)
WHERE post_id=103;
~~~

`array_remove` deletes **every occurrence** of that value. If an array holds duplicate tag IDs, one statement removes all of them.

### 14.3. Adding a tag in the junction table

~~~sql
INSERT INTO array_lab.post_tags(post_id,tag_id)
VALUES (103,5)
ON CONFLICT (post_id,tag_id) DO NOTHING;
~~~

With the composite PK, this operation is idempotent per pair: repeating it never inserts a duplicate.

### 14.4. Removing a tag in the junction table

~~~sql
DELETE FROM array_lab.post_tags
WHERE post_id=103 AND tag_id=5;
~~~

Thanks to the PK, this touches **one edge row** instead of rewriting the post's entire tag list.

### 14.5. Avoid mixing up state during lab testing

The two lab schemas exist for **comparison**, with no triggers or dual-write keeping them synchronized. Running an array `UPDATE` without mirroring it in `post_tags` causes them to diverge. When verifying “equivalent query outputs,” preserve the initial data or apply identical updates to both sides in the lab.

### 14.6. Concurrency: application read-modify-write can lose updates

Suppose two users read `tag_ids={1,2}`, user A adds 3, and user B adds 4:

~~~text
A reads {1,2}                B reads {1,2}
A computes {1,2,3}           B computes {1,2,4}
A UPDATE tag_ids={1,2,3}     B UPDATE tag_ids={1,2,4}
                       -> Tag 3 risks being lost
~~~

When each client overwrites the full value computed from a stale snapshot, the second write can clobber the first (*application-level lost update*). Apply proper concurrency control:

- Atomic `UPDATE SET tag_ids=array_append(tag_ids,...)` with appropriate predicates instead of overwriting from stale snapshots.
- Row locking, version columns, or optimistic concurrency when needed.
- Proper transaction isolation and retry logic for serialization failures.

In a junction table, two transactions inserting **two different pairs** do not overwrite a shared list field. Still, handle constraint conflicts and related business invariants properly.

### 14.7. Update cost on large tables

For a post holding thousands of tags, adding a tag to an array column writes a new array value, updates TOAST storage, and updates GIN index entries. In a junction table, it typically inserts one small link row and updates its B-tree entries.

That **does not mean the junction table always does less I/O**: a junction table introduces extra heap rows, index pages, joins, and FK checks. Benchmark with realistic element counts and update rates.

---

## 15. MVCC, HOT, TOAST, and rewriting large arrays

### 15.1. MVCC never edits an array value in place

In PostgreSQL, `UPDATE` creates a new MVCC row version. Even when logically changing a single array element, PostgreSQL stores a new array value on the new row version rather than editing an independent sub-cell as in a normalized link row.

### 15.2. HOT updates and indexed columns

**HOT (Heap-Only Tuple) updates** skip index updates when eligible—notably when no indexed columns are modified and sufficient free space remains on the heap page.

If `tag_ids` has a GIN index and is modified, the `UPDATE` is ineligible for HOT due to modifying an indexed column. This raises write amplification when tags change frequently.

If an `UPDATE` modifies only `title` while leaving `tag_ids` unchanged, HOT eligibility depends on other indexes, page free space, and executor/storage conditions.

### 15.3. TOAST for large arrays

Arrays are variable-length values. When an array grows large, PostgreSQL may compress or store it out-of-line via **TOAST**, depending on storage settings and size.

Consequences:

- Fetching the whole array may require reading and decompressing TOAST chunks.
- Updating a large array writes new TOAST data.
- VACUUM must reclaim dead tuples and stale TOAST chunks.
- WAL and replication volume can grow.

Never dump an unbounded list into an array simply because “one column looks cleaner than multiple tables.”

### 15.4. Junction tables also incur MVCC and maintenance costs

`INSERT`/`DELETE` on `post_tags` still generates WAL, index updates, and dead tuples (on DELETE); VACUUM and B-tree maintenance still cost resources. Yet updating a single post–tag edge does **not force** rewriting the entire set of tags for that post like updating an array column.

### 15.5. Read-mostly vs. write-heavy workloads

| Workload | Array column | Junction table |
|---|---|---|
| Few tags/post, rarely updated | Compact and convenient to read | Extra joins/rows, stronger integrity |
| Very large tags/post | TOAST, index/update pressure | More rows/index pages, per-link updates |
| Concurrent tag edits on the same post | Row contention and read-modify-write risks | Independent pair operations, PK/FK support |
| Fetch all tags of one post | Simple single-array fetch | B-tree scan on `post_id` + aggregation if needed |
| Find all posts with a tag | GIN membership | B-tree `(tag_id,post_id)` |
| Multi-dimensional reporting/analytics | Heavy unnesting needed | Each edge is a row, natural for JOIN/GROUP BY |
| Tag metadata, FKs, permissions | Needs workarounds | FKs/joins fit naturally |
| Preserving tag order | Built into arrays | Add explicit `position` column |

---

## 16. Read costs: fetching one post vs. reverse-filtering by tag

### 16.1. Fetching all tags of a single post

~~~sql
SELECT tag_ids
FROM array_lab.posts_array
WHERE post_id=101;
~~~

A primary key lookup on `post_id` locates one row and returns one array. For small tag lists, this is very convenient.

Junction table:

~~~sql
SELECT tag_id
FROM array_lab.post_tags
WHERE post_id=101
ORDER BY tag_id;
~~~

PK `(post_id,tag_id)` supports `post_id` lookups and can return sorted `tag_id`s directly when appropriate.

### 16.2. Filtering all posts with a given tag

Array column:

~~~sql
SELECT post_id
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[4]::int[];
~~~

Junction table:

~~~sql
SELECT post_id
FROM array_lab.post_tags
WHERE tag_id=4;
~~~

GIN and a reverse B-tree `(tag_id,post_id)` are two distinct index structures, both capable of serving reverse lookups. If only `post_id`s are needed, the junction B-tree index holds them directly, though **Index Only Scan** still depends on the visibility map; if `title` is needed, a join or lookup against `posts` is required.

### 16.3. An overly common tag

If 90% of posts carry the “SQL” tag, querying for SQL returns almost the entire table:

- GIN must process huge posting lists/candidates and heap fetches.
- The `tag_post` B-tree must also scan many links and join many rows.
- Planner may pick Seq Scan / Hash Join because it beats massive index lookups.

“Having an index” **does not shrink the output cardinality**. For high-frequency tags, APIs should apply pagination, pre-aggregation, and caching where appropriate.

### 16.4. A very rare tag

If only 0.01% of posts contain a specific tag, GIN array membership or a reverse B-tree link lookup cuts scanned rows dramatically.

### 16.5. Multi-tag queries

For “has all 10 tags,” GIN intersects candidate posting lists across keys in the inverted structure. A junction table can use `GROUP BY`/`HAVING`, multiple `EXISTS`, or `JOIN`s. Which performs better depends on requested tag count, each tag's selectivity, posting list sizes, row counts, and planner statistics.

---

## 17. Solving “has all tags” with relational division

### 17.1. Direct array representation

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1,3,4]::int[];
~~~

Expected result: **106**.

### 17.2. Join + GROUP BY/HAVING

~~~sql
SELECT
    p.post_id,
    p.title
FROM array_lab.posts_rel AS p
JOIN array_lab.post_tags AS pt
  ON pt.post_id=p.post_id
WHERE pt.tag_id IN (1,3,4)
GROUP BY p.post_id,p.title
HAVING COUNT(DISTINCT pt.tag_id)=3;
~~~

Expected result: **106**.

Comparing `COUNT` to 3 only works when the requested set has **three distinct tag IDs** and the junction table prohibits NULLs per schema.

### 17.3. Multiple EXISTS can stay readable for small fixed sets

~~~sql
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE EXISTS (
    SELECT 1 FROM array_lab.post_tags AS x
    WHERE x.post_id=p.post_id AND x.tag_id=1
)
AND EXISTS (
    SELECT 1 FROM array_lab.post_tags AS x
    WHERE x.post_id=p.post_id AND x.tag_id=3
)
AND EXISTS (
    SELECT 1 FROM array_lab.post_tags AS x
    WHERE x.post_id=p.post_id AND x.tag_id=4
);
~~~

The planner can convert these into semi-join / index-lookup strategies. **Never declare one query universally faster** merely from SQL text length.

### 17.4. General logical form with nested NOT EXISTS

Find posts where **there does not exist any requested tag that the post lacks**:

~~~sql
WITH requested(tag_id) AS (
    VALUES (1),(3),(4)
)
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM requested AS r
    WHERE NOT EXISTS (
        SELECT 1
        FROM array_lab.post_tags AS pt
        WHERE pt.post_id=p.post_id
          AND pt.tag_id=r.tag_id
    )
)
ORDER BY p.post_id;
~~~

This form has a notable property: if `requested` is **empty**, “no requested tag is missing” evaluates to TRUE for **every post**, matching containment semantics with an empty array for non-NULL arrays.

Still, optimizer choices and execution strategies depend on the dataset; benchmark it.

### 17.5. Correctness before optimization

If the requested input array contains duplicates:

~~~text
requested = [1,1,4]
~~~

`@>` does not treat multiplicity as needing tag 1 twice. A junction query must deduplicate `requested` with `DISTINCT` before comparing `COUNT = number_requested`; checking `COUNT(*)=3` against a duplicate-laden list produces wrong answers.

---

## 18. Data dependencies and updating the dictionary

### 18.1. Renaming a tag

~~~sql
UPDATE array_lab.tags
SET tag_name='Postgres'
WHERE tag_id=1;
~~~

When both the array model and the junction model store **tag IDs**, renaming a tag in the dictionary requires no updates to `posts_array.tag_ids` or `post_tags`. The junction table's advantage is not “arrays cannot reference a dictionary,” but that **FK constraints enforce valid IDs**.

### 18.2. Deleting a tag

In the linked model, deleting a referenced tag is blocked by the FK unless cascade rules specify otherwise. In the array model, the database has no per-element FK to block it, leaving behind **orphan references**.

Auditing orphan IDs in arrays:

~~~sql
SELECT DISTINCT
    p.post_id,
    u.tag_id AS missing_tag_id
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
LEFT JOIN array_lab.tags AS d
  ON d.tag_id=u.tag_id
WHERE d.tag_id IS NULL
ORDER BY p.post_id,missing_tag_id;
~~~

On clean lab data, this returns zero rows. Notice this is an **audit query**, not a write-time constraint preventing invalid writes.

### 18.3. Deleting a post

In the linked model, an `ON DELETE CASCADE` FK on `post_tags.post_id` removes links transactionally when deleting a post. In the array model, `tag_ids` lives inside the post row and vanishes with it; the tag dictionary stays untouched.

### 18.4. Metadata on relationships

If users assign tags with `confidence_score`, `assigned_by`, or `assigned_at`, a junction table is the natural place for those attributes. An array storing only tag IDs would require much more complex structures and struggle with per-element enforcement.

---

## 19. Order, duplicate tags, and boundaries between list, set, and relation

### 19.1. Three different semantics

| Domain requirement | What must be represented | Viable design |
|---|---|---|
| A post has an **unordered set of unique tags** | Post–tag edge | Junction `PK(post_id,tag_id)`; or canonical array |
| A playlist has **ordered tracks** | Ordered list, duplicates possible | Junction with `position`/`item_id`, or array if small and rarely edited |
| An order has **each product with quantity, unit price** | Separate business line items | `order_items`, **never** a bare `product_ids` array |

### 19.2. Junction tables can capture order

If tags form an ordered list:

~~~sql
-- Alternative design illustration; no need to alter lab's post_tags:
CREATE TABLE array_lab.post_tag_positions (
    post_id BIGINT NOT NULL
        REFERENCES array_lab.posts_rel(post_id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL
        REFERENCES array_lab.tags(tag_id),
    position INTEGER NOT NULL CHECK (position >= 1),
    PRIMARY KEY (post_id,tag_id),
    UNIQUE (post_id,position)
);
~~~

This guarantees each tag appears at most once per post and no two tags share a position. It **does not automatically keep positions gap-free** (1,2,3...) after deletions/edits; the application or a procedure must manage renumbering if needed.

### 19.3. When duplicates are meaningful

If a list allows the same item to appear multiple times, `PRIMARY KEY(post_id,tag_id)` no longer fits. Use a surrogate `item_id` or `PK(post_id,position)` with an FK on `tag_id`. Design from **business rules** instead of forcing data into a pre-picked structure.

### 19.4. Never rely on implicit SQL row order

A junction table does not guarantee `SELECT` returns rows in insertion order without `ORDER BY`. Arrays store intrinsic element order, whereas tables require storing and sorting by a deterministic key when order matters.

---

## 20. How do JSONB arrays differ from SQL arrays?

Since the overarching chapter is **JSON and Arrays**, let's compare all three representations:

| Characteristic | `integer[]` / `text[]` | `jsonb` array | Junction table |
|---|---|---|---|
| Element type | Single uniform SQL type | JSON values (can mix types) | Typed columns with FKs |
| Empty representation | `'{}'::int[]` | `'[]'::jsonb` | Zero link rows |
| Containment query | Array `@>` | JSONB `@>` with JSONB rules | `JOIN`/`EXISTS` |
| Overlap operator `&&` | Supported on SQL arrays | No equivalent built-in JSONB operator | `IN`/`EXISTS` |
| GIN opclass | `array_ops` | `jsonb_ops` or `jsonb_path_ops` | Link B-tree indexes |
| Per-element referential integrity | No direct FK | No direct FK | Native FK |
| Per-edge metadata | Awkward / manual checks | Flexible structure, weak relational checks | Natural |
| Multi-dimensional reporting | `unnest` | JSONB expansion functions | SQL joins/grouping |
| Updating a single link | Rewrites array value | Rewrites JSONB value | `INSERT`/`DELETE` one row |

### 20.1. SQL array containment

~~~sql
SELECT ARRAY[1,2]::int[] @> ARRAY[2]::int[] AS sql_array_contains;
~~~

### 20.2. JSONB containment shares the symbol but uses different types

~~~sql
SELECT '[1,2]'::jsonb @> '[2]'::jsonb
       AS jsonb_array_contains;
~~~

Both write `@>`, yet **operator implementations, operator classes, data types, and matching rules** differ. Never apply `array_ops` to a JSONB column.

### 20.3. JSONB document with a tags field

~~~sql
CREATE TABLE array_lab.posts_jsonb (
    post_id BIGINT PRIMARY KEY,
    doc JSONB NOT NULL
);

INSERT INTO array_lab.posts_jsonb(post_id,doc)
VALUES
    (101,'{"title":"PostgreSQL Fundamentals","tags":["PostgreSQL","SQL","Performance"]}'::jsonb),
    (102,'{"title":"JSON and Arrays","tags":["PostgreSQL","JSON","Array"]}'::jsonb);

CREATE INDEX idx_posts_jsonb_doc
ON array_lab.posts_jsonb USING gin(doc);
~~~

Query:

~~~sql
SELECT post_id
FROM array_lab.posts_jsonb
WHERE doc @> '{"tags":["PostgreSQL"]}'::jsonb;
~~~

Built-in GIN on JSONB uses different operator classes than array GIN. Flexible JSONB fits evolving document schemas, yet when tags represent business relationships needing FKs, uniqueness, and dimensional analytics, a junction table stays stronger.

### 20.4. JSONB key existence differs from array membership

The JSONB `?` operator tests key/top-level string-array element existence for compatible JSONB shapes:

~~~sql
SELECT post_id
FROM array_lab.posts_jsonb
WHERE (doc -> 'tags') ? 'PostgreSQL';
~~~

Indexing `doc` as a whole does not automatically guarantee `(doc->'tags') ? ...` uses that index efficiently; if this expression is hot, consider a dedicated GIN expression index:

~~~sql
CREATE INDEX idx_posts_jsonb_tags_expr
ON array_lab.posts_jsonb
USING gin ((doc -> 'tags'));
~~~

This is another reminder that **the index must match the predicate and expression**, rather than assuming “any GIN index accelerates every JSON operator.”

### 20.5. When is JSONB a good fit?

- Rapidly evolving payloads/schemas that do not need joins/FKs per field.
- Document storage exchanged with external systems.
- Numerous nested optional attributes.
- Query requirements suited to JSONB containment/JSONPath operators.

If you only need a homogeneous list of integer tag IDs, SQL `integer[]` is cleaner and more strongly typed. If you need a many-to-many relationship with FKs and metadata, a junction table is usually the better foundation.

---

## 21. GIN pending list and write throughput impact

### 21.1. GIN stores inverted entries, not one key per row

A post with 30 tags contributes many index keys/posting entries to GIN. Inserting or updating large arrays has a different cost profile than a single scalar B-tree key.

### 21.2. fastupdate

GIN supports `fastupdate`, routing new index entries through a **pending list** before merging them into the main index tree. This can speed up everyday INSERT throughput, yet a large pending list can cause:

- Queries scanning both the main index and pending entries.
- CPU/I/O spikes when flushing the pending list.
- Heavy cleanup work during VACUUM or triggered merges.
- Latency jitter under bursty write workloads.

### 21.3. Checking settings

~~~sql
SHOW gin_pending_list_limit;
~~~

At the index level, storage parameters can be configured during `CREATE INDEX` or `ALTER INDEX` when permitted:

~~~sql
CREATE INDEX idx_posts_array_tags_gin_tuned
ON array_lab.posts_array
USING gin(tag_ids)
WITH (fastupdate=on);
~~~

This illustrates an **alternative test index**; do not create a duplicate if an equivalent GIN index already exists. Keeping two identical GIN indexes is discouraged.

### 21.4. Disabling fastupdate is not always faster

Turning `fastupdate` off forces INSERTs to update the main GIN structure immediately, raising per-statement write cost. Leaving `fastupdate` on can shift overhead to queries and periodic cleanups. Choose based on:

- Elements per row.
- INSERT/UPDATE rate.
- Read latency SLAs.
- Autovacuum/maintenance schedule.
- Storage, WAL, and replication capacity.

**Never change production-wide settings over a single slow query** without benchmarking and a runbook.

### 21.5. VACUUM and GIN cleanup

Autovacuum/VACUUM cleans up dead tuples and participates in merging the GIN pending list according to PostgreSQL mechanics. Under heavy DELETE/UPDATE workloads, monitoring VACUUM lag, dead tuples, and index bloat is just as important as reading query plans.

### 21.6. Never disable autovacuum to “avoid GIN slowdowns”

Long-term disabling of autovacuum lets dead tuples accumulate and risks MVCC/XID wraparound issues. If the GIN pending list becomes a bottleneck, inspect root causes, index design, and maintenance tuning rather than disabling a foundational safety mechanism.

---

## 22. Monitoring array queries: EXPLAIN, BUFFERS, and statistics

### 22.1. Plan using GIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids && ARRAY[1,5]::int[];
~~~

Look for:

- `Bitmap Index Scan` on GIN vs. `Seq Scan`.
- Does `Index Cond` match `&&`/`@>`?
- `actual rows` vs. estimated `rows`.
- `Buffers: shared hit/read` and temp I/O.
- `Rows Removed by Index Recheck`, if present.
- Overall `Execution Time`.

### 22.2. Plan using the junction table's B-tree

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE EXISTS (
    SELECT 1 FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id
      AND pt.tag_id=1
);
~~~

Look for:

- `Index Scan`/`Index Only Scan` on `idx_post_tags_tag_post`?
- `Nested Loop`, `Hash Semi Join`, or another join strategy?
- Heavy heap fetches from `posts_rel`?
- `actual rows`, `loops`, and fan-out.

### 22.3. Never add parent and child buffers or times together

Parent node timings and buffers **already include** child work. Do not sum `Hash Join actual time` + `Seq Scan actual time` + `Index Scan actual time` to get query time; read `Execution Time` and examine child branches to isolate hotspots.

### 22.4. Index usage statistics

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname='array_lab'
ORDER BY relname,indexrelname;
~~~

These are cumulative resettable counters; `idx_scan=0` right after index creation does not prove the index is useless.

### 22.5. Index size

~~~sql
SELECT
    c.oid::regclass AS index_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS index_size,
    pg_relation_size(c.oid) AS bytes
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='array_lab'
  AND c.relkind IN ('i','I')
ORDER BY bytes DESC,index_name::text;
~~~

A larger GIN index is not necessarily slower than a smaller B-tree index; weigh query patterns, write overhead, and total footprint across heap, TOAST, and junction rows.

---

## 23. Benchmarking fairly: comparing both models on identical data

### 23.1. Why isn't the six-post lab enough to conclude?

A six-row table scans faster with `Seq Scan` than GIN, while a junction join adds microseconds of setup overhead. Those numbers **do not extrapolate** to millions of posts with 20–100 tags each.

Always benchmark at representative scale and data distributions rather than judging by schema brevity alone.

### 23.2. Generating an independent synthetic dataset

This section is **optional**; run only when your lab database has adequate CPU, disk, and time. These tables leave the six sample posts untouched and avoid the 1..6 tag FK.

~~~sql
CREATE TABLE array_lab.big_posts (
    post_id BIGINT PRIMARY KEY,
    tag_ids INTEGER[] NOT NULL
);

INSERT INTO array_lab.big_posts(post_id,tag_ids)
SELECT
    g::bigint,
    ARRAY[
        1 + (g % 101),
        1 + ((g / 7) % 101),
        1 + ((g / 37) % 101)
    ]::integer[]
FROM generate_series(1,50000) AS g;
~~~

Each row holds three **array positions**; since the formula can yield duplicate tag IDs within one row, never equate `cardinality(tag_ids)=3` with three distinct tags.

### 23.3. Create the GIN index

~~~sql
CREATE INDEX idx_big_posts_tags_gin
ON array_lab.big_posts USING gin(tag_ids);

ANALYZE array_lab.big_posts;
~~~

### 23.4. Create the corresponding linked data

~~~sql
CREATE TABLE array_lab.big_post_tags (
    post_id BIGINT NOT NULL
        REFERENCES array_lab.big_posts(post_id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (post_id,tag_id)
);

INSERT INTO array_lab.big_post_tags(post_id,tag_id)
SELECT DISTINCT p.post_id,u.tag_id
FROM array_lab.big_posts AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id);

CREATE INDEX idx_big_post_tags_reverse
ON array_lab.big_post_tags(tag_id,post_id);

ANALYZE array_lab.big_post_tags;
~~~

`DISTINCT` removes duplicate pairs that the synthetic generator may produce. No FK to `array_lab.tags` is added here because synthetic data uses tag IDs 1..101 while the sample catalog only has 1..6.

### 23.5. Comparing “has tag 17”

Array column:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM array_lab.big_posts
WHERE tag_ids @> ARRAY[17]::integer[];
~~~

Junction table:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM array_lab.big_post_tags
WHERE tag_id=17;
~~~

Because `big_post_tags` has a composite PK, each post appears at most once with tag 17, so both queries count identically. The synthetic table contains no NULL arrays.

### 23.6. Comparing “has either tag 17 or 32”

Array:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM array_lab.big_posts
WHERE tag_ids && ARRAY[17,32]::integer[];
~~~

Junction:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(DISTINCT post_id)
FROM array_lab.big_post_tags
WHERE tag_id IN (17,32);
~~~

`DISTINCT` on the junction side is essential because a post carrying **both 17 and 32** produces two matching link rows. Dropping `DISTINCT` changes the metric from post count to link count.

### 23.7. Comparing “has both tags 17 and 32”

Array:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM array_lab.big_posts
WHERE tag_ids @> ARRAY[17,32]::integer[];
~~~

Junction:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM (
    SELECT post_id
    FROM array_lab.big_post_tags
    WHERE tag_id IN (17,32)
    GROUP BY post_id
    HAVING COUNT(*)=2
) AS matching_posts;
~~~

`COUNT(*)=2` works here because the requested set has two distinct tag IDs, the PK prevents duplicate edges, and the filter selects only those two tags. If input lists can contain duplicates, deduplicate first.

### 23.8. Comparing total storage, not just index size

The array design stores array values inside the posts table plus a GIN index. The junction design involves:

- The posts table.
- The `post_tags` table with many rows.
- The PK index on `(post_id,tag_id)`.
- The reverse index on `(tag_id,post_id)`.
- FK checks and WAL/index maintenance.

Comparing totals:

~~~sql
SELECT
    'array_big_posts' AS design,
    pg_total_relation_size('array_lab.big_posts'::regclass) AS bytes
UNION ALL
SELECT
    'linked_big_post_tags',
    pg_total_relation_size('array_lab.big_post_tags'::regclass);
~~~

**Note that this comparison omits** shared post metadata in a separate table and row-header differences; include every related relation when benchmarking production architectures. Never treat these two numbers alone as total system cost.

### 23.9. Measure multiple workload shapes

| Query / operation | What to measure |
|---|---|
| Very rare tag | p50/p95 latency, buffers |
| Common tag | Output size, seq vs. index |
| ANY of 2–10 tags | Index/postings vs. JOIN DISTINCT |
| ALL of 2–10 tags | GIN containment vs. aggregation/semi-joins |
| Fetch all tags of one post | Array fetch vs. ordered link scan |
| Count posts per tag | Unnest/group vs. indexed join/group |
| Add/remove one tag | Array `UPDATE` vs. link `INSERT`/`DELETE` |
| Delete a post | Index/TOAST vs. FK cascade |
| Rename a tag | Dictionary-only vs. mass array rewrite |
| Large batch import | WAL, pending cleanup, index size |
| VACUUM / reindex | Maintenance duration, disk headroom |

### 23.10. Caching and concurrency

A first run hits cold caches while the second benefits from warm buffers. Never declare arrays faster simply because you benchmarked them **after** the junction queries. Alternate run orders, repeat measurements, and test under realistic concurrent read/write loads.

---

## 24. Maintaining consistency when multiple clients edit tags concurrently

### 24.1. The concurrency problem

Suppose two transactions simultaneously assign tag 5 to post 101. The business invariant is “each post–tag pair exists at most once.”

In the junction model:

~~~sql
INSERT INTO array_lab.post_tags(post_id,tag_id)
VALUES (101,5)
ON CONFLICT (post_id,tag_id) DO NOTHING;
~~~

`PRIMARY KEY(post_id,tag_id)` enforces uniqueness at the database layer even under concurrency. One transaction waits at a unique-index conflict and proceeds according to isolation and `ON CONFLICT` semantics.

In the array model, if two clients concurrently append 5 without locking or checks, `{1,2,4,5,5}` can result. You must explicitly guard set semantics.

### 24.2. “Read, check, then UPDATE” has a race condition

Code flow:

~~~text
SELECT tag_ids ...
if (5 not in tag_ids):
    UPDATE tag_ids = previous_tags_plus_5
~~~

suffers from race conditions / lost updates when two clients overwrite based on stale snapshots. This is a transactional issue, not a GIN bug.

An SQL variant pushing the check into the `UPDATE`:

~~~sql
UPDATE array_lab.posts_array
SET tag_ids = array_append(tag_ids,5)
WHERE post_id=101
  AND NOT (tag_ids @> ARRAY[5]::integer[]);
~~~

avoids many application read-modify-write races, yet **does not replace** all concurrency, uniqueness, and ordering guarantees. Depending on isolation level, PostgreSQL waits, re-evaluates the condition, or throws a serialization error requiring retry. Design and test against specific transaction semantics.

### 24.3. Capping tags per post

With an array column, a simple row-local constraint works:

~~~sql
ALTER TABLE array_lab.posts_array
ADD CONSTRAINT chk_posts_max_20_tags
CHECK (cardinality(tag_ids) <= 20);
~~~

This is straightforward because all tags reside on one row.

In a junction table, “at most 20 tags per post” spans **multiple child rows**, so a single-row CHECK constraint on `post_tags` cannot count sibling rows. You need transactional logic, stored procedures, triggers, or advisory/parent locking if the DB itself must strictly enforce that cap.

### 24.4. Do not rely on CHECK alone on an array column to replace FKs

A row-local CHECK constraint cannot reference rows across `tags` the way a multi-element SQL FOREIGN KEY would. Custom functions or triggers querying the dictionary are feasible in specialized setups, yet require careful handling of concurrency, snapshots, permissions, dictionary updates, and migrations; a junction table provides native FKs out of the box.

### 24.5. Document NULL, duplicate, and ordering contracts explicitly

A solid contract for array tags:

~~~text
- tag_ids is NOT NULL.
- Empty array means no tags assigned.
- No NULL elements allowed.
- No duplicate tag IDs allowed.
- Element order carries no business meaning.
- Every tag ID must exist in the dictionary.
- At most 20 tags per post.
~~~

Only part of this contract can be enforced directly via `NOT NULL`/`DEFAULT`/row `CHECK`; the rest needs write validation, triggers, or a relational model change.

A junction table enforces most of this contract natively via `NOT NULL`/PK/FK; the 20-tag cap still needs custom enforcement.

---

## 25. Bidirectional B-trees for junction tables: get the column order right

### 25.1. PRIMARY KEY(post_id,tag_id) serves post → tags

~~~sql
SELECT tag_id
FROM array_lab.post_tags
WHERE post_id=106
ORDER BY tag_id;
~~~

Multicolumn B-trees use leading-prefix semantics; a PK beginning with `post_id` efficiently scans a post's tags.

### 25.2. Index(tag_id,post_id) serves tag → posts

~~~sql
SELECT post_id
FROM array_lab.post_tags
WHERE tag_id=4
ORDER BY post_id;
~~~

Index:

~~~sql
CREATE INDEX idx_post_tags_tag_post_alt
ON array_lab.post_tags(tag_id,post_id);
~~~

This merely illustrates an index equivalent to `idx_post_tags_tag_post` created earlier. **Do not create two identical reverse indexes** in production or lab without reason. What matters is column order.

### 25.3. Never assume one composite index covers every access direction

A B-tree on `(post_id,tag_id)` is not equivalent to `(tag_id,post_id)` for standalone `tag_id` predicates. PostgreSQL may apply different scan tactics depending on version and stats, yet you should never rely on a `post_id`-leading index for efficient global `tag_id` lookups.

### 25.4. Queries with extra filter columns

If `post_tags` stores `assigned_at`, “all posts given tag 4 within the last 7 days” may benefit from:

~~~sql
-- Design pattern; requires assigned_at column to exist:
CREATE INDEX idx_post_tags_tag_assigned
ON array_lab.post_tags(tag_id,assigned_at DESC,post_id);
~~~

Do not run this on the lab until that column exists. Choose index columns to fit `WHERE`, `ORDER BY`, `LIMIT`, and selectivity—not guesswork.

### 25.5. Index coverage and Index-Only Scans

With a junction table, a query requesting only `post_id` backed by `(tag_id,post_id)` can qualify for an **Index Only Scan** when the visibility map allows it. Still, covering columns does not guarantee zero heap fetches; PostgreSQL must verify MVCC tuple visibility.

With GIN, membership queries typically run a `Bitmap Heap Scan` fetching heap rows; never assume GIN yields an index-only scan returning both `post_id` and `title`.

---

## 26. How does the planner choose between GIN and Seq Scan?

### 26.1. Tag selectivity

If tag 1 appears on 80% of posts, a GIN lookup must fetch most heap pages anyway. The planner often chooses `Seq Scan`, especially when returning `title` or large payloads across most rows.

If tag 99 appears on only 100 of 10 million posts, the inverted index provides massive savings.

### 26.2. Array element statistics

PostgreSQL collects specialized statistics for array elements on supported types and versions. Inspect `pg_stats`:

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_elems,
    most_common_elem_freqs,
    elem_count_histogram
FROM pg_stats
WHERE schemaname='array_lab'
  AND tablename IN ('posts_array','big_posts')
  AND attname='tag_ids'
ORDER BY tablename;
~~~

Fields:

- `most_common_elems`: frequently occurring element values collected by ANALYZE.
- `most_common_elem_freqs`: estimated frequencies of those common elements.
- `elem_count_histogram`: distribution of distinct element counts per array.

Do not confuse **per-element statistics** with `n_distinct` of the **whole array value**. Read the proper fields against representative samples.

### 26.3. Run ANALYZE after bulk loads

~~~sql
ANALYZE array_lab.posts_array;
ANALYZE array_lab.big_posts;
ANALYZE array_lab.big_post_tags;
~~~

Skip `ANALYZE` on the big tables if you didn't create them. After large data loads or tag distribution shifts, `ANALYZE` gives the planner fresh statistics.

### 26.4. Adjusting the statistics target judiciously

~~~sql
ALTER TABLE array_lab.big_posts
ALTER COLUMN tag_ids SET STATISTICS 300;

ANALYZE array_lab.big_posts;
~~~

Increasing statistics target can improve cardinality estimates on skewed tag distributions at the cost of extra ANALYZE time and `pg_stats` storage. Do not crank every column's target up blindly without evidence of misestimation.

### 26.5. Never double-count parent and child node timings

In `EXPLAIN ANALYZE`, parent execution time includes child subtrees. If a top-level `Hash Join` takes 100 ms, child Index/Seq scans are already inside that 100 ms. Never sum all node `actual time` values; look at `Execution Time`.

### 26.6. Parameterized queries

Applications commonly execute:

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids @> $1::integer[];
~~~

This is parameterized SQL; actual plan selection and index use depend on `$1`'s value, statistics, and generic vs. custom plan caching.

A query passed a very common tag and the same SQL passed a rare tag can need different plans; benchmark across representative parameter groups.

---

## 27. Migrating from an array column to a junction table

This is a critical architectural transition. When a system initially stores `posts.tag_ids` in an array and later requires foreign keys, edge metadata, or heavy analytics, never perform an uncontrolled schema swap.

### 27.1. Audit data before backfilling

Find duplicate elements within the same post:

~~~sql
SELECT
    p.post_id,
    u.tag_id,
    COUNT(*) AS occurrences
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
GROUP BY p.post_id,u.tag_id
HAVING COUNT(*) > 1
ORDER BY p.post_id,u.tag_id;
~~~

Find orphan tag IDs:

~~~sql
SELECT DISTINCT p.post_id,u.tag_id
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
LEFT JOIN array_lab.tags AS d ON d.tag_id=u.tag_id
WHERE d.tag_id IS NULL
ORDER BY p.post_id,u.tag_id;
~~~

Find NULL arrays or NULL elements if production permits them:

~~~sql
SELECT post_id
FROM array_lab.posts_array
WHERE tag_ids IS NULL
   OR array_position(tag_ids,NULL) IS NOT NULL;
~~~

Whenever duplicates, orphans, or NULLs exist, establish **business-approved cleanup rules**. Never drop duplicates silently with `DISTINCT` if multiplicity carried real meaning.

### 27.2. Build the linked schema

In production, deploy the new tables, PKs, FKs, and indexes in migrations mindful of lock windows and disk budgets. In our lab, `posts_rel` and `post_tags` play this role.

### 27.3. Backfill in batches

A query modeling one batch (lab post IDs 101–106):

~~~sql
INSERT INTO array_lab.post_tags(post_id,tag_id)
SELECT DISTINCT
    p.post_id,
    u.tag_id
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
WHERE p.post_id BETWEEN 101 AND 106
ON CONFLICT (post_id,tag_id) DO NOTHING;
~~~

This requires `posts_rel` and `tags` to already hold the referenced keys. On tables with millions of posts, split into small batches with checkpoint/retry logic while monitoring WAL, transaction duration, and replication lag.

### 27.4. Capturing concurrent writes during backfill

This is the highest-risk part of the migration. While the backfill job copies rows, the API may still add or remove tags. Simply taking a snapshot copy and switching reads to the junction table can **lose writes occurring after the snapshot**.

Context-dependent strategies:

- **Controlled short write pause:** backfill and cut over inside a planned maintenance window.
- **Application dual-write:** update both models **within the same transaction** where possible, handling failures and consistency verification.
- **Triggers / CDC / event log:** capture array changes and replay them onto link rows, carefully managing ordering, idempotency, and error handling.
- **Single clear source of truth:** designate only one authoritative store at any moment; avoid independent conflicting writers on both sides.

Never assume “turning on dual-write” alone suffices without planning backfill ordering, in-flight writes, retries, and recovery.

### 27.5. Reconciling results under set semantics

Compare sorted distinct array sets against sorted link sets:

~~~sql
SELECT p.post_id
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL (
    SELECT COALESCE(
        array_agg(DISTINCT u.tag_id ORDER BY u.tag_id),
        '{}'::integer[]
    ) AS array_set
    FROM unnest(p.tag_ids) AS u(tag_id)
) AS a
CROSS JOIN LATERAL (
    SELECT COALESCE(
        array_agg(pt.tag_id ORDER BY pt.tag_id),
        '{}'::integer[]
    ) AS link_set
    FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id
) AS l
WHERE a.array_set IS DISTINCT FROM l.link_set
ORDER BY p.post_id;
~~~

Once synchronized, this query should return **zero rows**. Note that it only checks posts present in `posts_array`; real migrations must also verify newly added/deleted posts and orphan link rows in the reverse direction.

### 27.6. Comparing total row counts is not enough

Both systems might hold 1 million links yet **disagree on which post–tag pairs exist**. Verify:

- Post count and distinct post–tag pair count.
- Orphan IDs and duplicate pairs.
- Row-by-row comparisons by post or batch/partition.
- Sampled or full checksums matching the contract.
- Pending async write events.
- Business queries and authorization rules.

### 27.7. Cut over reads, cut over writes, keep a rollback path

A typical sequence:

~~~text
Define linked model + indexes/FK
                 |
                 v
Audit existing array data
                 |
                 v
Batch backfill linked rows
                 |
                 v
Capture/sync concurrent writes
                 |
                 v
Reconcile data and query outputs
                 |
                 v
Gradually shift reads to linked model
                 |
                 v
Cut over source of truth to linked model
                 |
                 v
Monitor and retain rollback window
                 |
                 v
Drop array column only once unused
~~~

If compatibility is needed for rollback, do not drop the array column immediately after the first check. Plan cleanly when dual-writing can stop so models don't silently drift.

---

## 28. Returning arrays from a junction table without storing two copies

One strength of the linked model is being able to expose an **array-shaped interface** to legacy consumers without storing a duplicate `tag_ids` column on `posts`.

### 28.1. ARRAY(SELECT ... ORDER BY ...)

~~~sql
SELECT
    p.post_id,
    p.title,
    ARRAY(
        SELECT pt.tag_id
        FROM array_lab.post_tags AS pt
        WHERE pt.post_id=p.post_id
        ORDER BY pt.tag_id
    ) AS tag_ids
FROM array_lab.posts_rel AS p
ORDER BY p.post_id;
~~~

An `ARRAY(SELECT ...)` subquery returns an empty array when zero rows match, so post 105 receives `{}`. This pattern works nicely for building application DTOs and API responses.

### 28.2. Creating a compatibility VIEW

~~~sql
CREATE VIEW array_lab.posts_with_tag_array AS
SELECT
    p.post_id,
    p.title,
    ARRAY(
        SELECT pt.tag_id
        FROM array_lab.post_tags AS pt
        WHERE pt.post_id=p.post_id
        ORDER BY pt.tag_id
    ) AS tag_ids
FROM array_lab.posts_rel AS p;
~~~

Consumers can `SELECT` from the view and receive an array column. Keep in mind:

- The view **computes the array** dynamically from link rows at query time; it is not a physically cached heap array.
- Filtering `tag_ids @> ...` against the view **does not automatically use a GIN index** as a stored array column would.
- Across many posts, correlated subqueries or aggregations can incur noticeable runtime cost.
- If you materialize/cache it via a materialized view, manage refreshes, invalidation, and staleness explicitly.

Views provide **schema compatibility**, not free query acceleration.

### 28.3. Keep a single source of truth

Never keep two authoritative stores simply because two APIs want different shapes. Store and constrain one canonical model, and **derive the other on read** or cache it with an explicit refresh policy.

---

## 29. Reverse migration: from junction table to array

Occasionally a workload shifts toward read-mostly lookups over small bounded memberships with zero per-edge metadata, making a stored array projection attractive.

### 29.1. Aggregating links into an array

~~~sql
SELECT
    p.post_id,
    COALESCE(
        array_agg(pt.tag_id ORDER BY pt.tag_id)
            FILTER (WHERE pt.tag_id IS NOT NULL),
        '{}'::integer[]
    ) AS tag_ids
FROM array_lab.posts_rel AS p
LEFT JOIN array_lab.post_tags AS pt
  ON pt.post_id=p.post_id
GROUP BY p.post_id
ORDER BY p.post_id;
~~~

Because `post_tags` has a composite PK, `DISTINCT` is unnecessary. Adding `ORDER BY` guarantees deterministic output order.

### 29.2. Information lost during conversion

- Per-link attributes like `assigned_at`, `assigned_by`, and `confidence`.
- Native per-edge FK/uniqueness semantics.
- Edge-level constraints and per-tag access rules.
- Row-level independent updates.
- Ordering if mis-aggregated or if business logic needs something other than `tag_id` order.

Never switch storage to an array merely because an API emits JSON arrays; views or DTO projections can assemble arrays from relational rows.

### 29.3. Syncing a materialized array projection

If you intentionally store a denormalized tag array to accelerate specific reads, specify:

- What updates the projection?
- Maximum acceptable staleness lag relative to the source?
- Which link updates invalidate which caches?
- Which APIs require strict read-your-writes?
- How is the projection rebuilt after errors?
- How do checksums/monitors detect drift?

This is **controlled denormalization**, never zero-cost magic.

---

## 30. Business-driven decision matrix

| Criterion | Array column + GIN | Junction table + B-tree |
|---|---|---|
| Small bounded ID set, read-mostly | **Strong candidate** | Also works, more rows/joins |
| Fast membership queries `@>`/`&&` | **GIN fits well** | `tag_id`-indexed lookups fit well |
| Many tags, frequent updates | Expensive array/GIN/TOAST rewrites | **Usually cleaner** per-link writes |
| Referential integrity to tag catalog | No native per-element FK | **Built-in FK** |
| No duplicate post–tag pairs | Needs write rules/canonicalization | **Built-in composite PK** |
| Edge-level metadata | Awkward and unnatural | **Very natural** |
| Fetch all tags of one post | Convenient single-column fetch | `post_id` B-tree + aggregation |
| Reverse lookup posts by tag | GIN inverted lookup | `(tag_id,post_id)` B-tree |
| “How many posts per tag” reports | Unnest + group, potentially heavy | Direct `GROUP BY` on links |
| Per-tag/per-link permissions | Complex in arrays | Joins/row-level rules fit naturally |
| Preserve tag order | Inherently ordered | Add `position` column |
| Internal IDs without dictionary | Reasonable | May be overkill if genuinely tiny |
| Very common tag | GIN may offer little help | B-tree also cannot avoid large output |
| “Same item repeated with quantity” | Arrays lack line metadata | Line-item table required |
| Transactionally enforce 20-tag cap | Easy row-level CHECK | Needs aggregate constraint/locking |
| JSONB/path querying | Arrays are not JSONB | JSONB/document is a third candidate |
| Schema change / migration cost | Harder if APIs depend on array column | Requires backfill/cutover on change |

### 30.1. Default rule of thumb

If **tags represent a genuine business relationship** between two entities with a catalog, foreign keys, permissions, analytics, multiple concurrent writers, or edge metadata, a **junction table** is the safer long-term starting point.

If the list is a **small, bounded intrinsic attribute**, changes infrequently, and is primarily queried via containment/overlap, an **array column + GIN** is a solid choice.

Never treat either rule as dogma; measure latency, storage, write rate, and integrity needs.

---

## 31. Model and index selection diagram

~~~mermaid
flowchart TD
    A["An entity holds multiple values"] --> B{"Do values have independent entities, FKs, or per-edge metadata?"}
    B -- "Yes" --> C["Junction table post_tags"]
    B -- "No" --> D{"Small, bounded list with infrequent updates?"}
    D -- "Yes" --> E["Consider SQL array"]
    D -- "No" --> F["Consider junction table or another model"]
    C --> G["PK(post_id,tag_id) + FK + index(tag_id,post_id)"]
    E --> H{"Membership queries or whole-array equality?"}
    H -- "Membership, ANY/ALL/overlap" --> I["GIN array_ops, @>, &&, <@"]
    H -- "Exact whole-array comparison" --> J["B-tree array / canonicalize order"]
    F --> K["Measure workload and data shape"]
    G --> L["EXPLAIN + measure JOINs, writes, FKs, analytics"]
    I --> L
    J --> L
    K --> L
    L --> M{"Correct semantics and acceptable trade-offs?"}
    M -- "Yes" --> N["Deploy, monitor, enforce consistency"]
    M -- "No" --> O["Adjust model/indexes and re-measure"]
~~~

### 31.1. Core principle

**Index structures only accelerate data access paths; they do not change the semantics of the stored data.** Choosing GIN over B-tree does not turn an ID array into an FK-enforced relation. Creating a junction table does not automatically make an “any/all tags” query correct if SQL permits duplicate joins or mishandles empty target sets.

---

## 32. Production index operations

### 32.1. Creating a GIN index on a large table

~~~sql
CREATE INDEX CONCURRENTLY idx_posts_array_tags_gin_online
ON array_lab.posts_array USING gin(tag_ids);
~~~

**Lab note:** if an equivalent GIN index already exists, do not add a duplicate. On active production tables receiving writes, `CONCURRENTLY` avoids blocking normal DML, though keep in mind:

- Cannot run inside an explicit transaction block.
- Consumes scan I/O, CPU, WAL, and disk space.
- Must wait for conflicting transactions/snapshots to finish.
- Leaves behind an `INVALID` index if canceled or failed.
- Requires progress monitoring and proper rollout timing.

### 32.2. Checking index validity

~~~sql
SELECT
    idx.relname AS index_name,
    ix.indisvalid,
    ix.indisready,
    pg_get_indexdef(ix.indexrelid) AS definition
FROM pg_index AS ix
JOIN pg_class AS idx
  ON idx.oid=ix.indexrelid
JOIN pg_class AS tbl
  ON tbl.oid=ix.indrelid
JOIN pg_namespace AS ns
  ON ns.oid=tbl.relnamespace
WHERE ns.nspname='array_lab'
  AND tbl.relname IN ('posts_array','big_posts')
ORDER BY idx.relname;
~~~

`indisvalid=false` means the planner cannot use the index as a normal valid index. **Seeing an index name in catalogs does not prove its build succeeded.**

### 32.3. Monitoring build progress

~~~sql
SELECT
    pid,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index
WHERE datname=current_database();
~~~

Empty output simply means no index build is running right now. Do not divide `blocks_done/blocks_total` as an exact overall percentage, since index builds pass through multiple phases and waits.

### 32.4. DROP / REINDEX

Before dropping a redundant or invalid index, verify dependencies, query usage, permissions, and recovery plans. `DROP INDEX CONCURRENTLY` and `REINDEX ... CONCURRENTLY` obey strict transaction rules and cannot run inside explicit transaction blocks.

Never drop an index hastily merely because `idx_scan=0` over a short observation window.

### 32.5. Cost of extra indexes

Every additional index adds:

- Disk footprint.
- INSERT/UPDATE/DELETE latency.
- WAL volume and buffer pressure.
- VACUUM/autovacuum work.
- Backup, reindex, and migration duration.

Never create a GIN array index, B-tree array index, two expression indexes, and a GIN JSONB index all at once “just in case” when the workload does not need them.

### 32.6. Foreign keys and cascading deletes also have a cost

Junction tables enforce FKs, so deleting a post can trigger multiple child link deletions. B-tree indexes locate matching child rows quickly, yet still generate WAL, I/O, locks, and trigger checks. “Normalized relational design” is not free either.

---

## 33. Security and correctness rules when querying arrays

### 33.1. Never build array literals via string concatenation from user input

Never write:

~~~text
SQL = "WHERE tag_ids @> ARRAY[" + raw_user_input + "]"
~~~

This exposes SQL injection vulnerabilities alongside quoting/casting bugs. Use parameterized SQL with explicit array types:

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids @> $1::integer[];
~~~

Have the database driver bind `$1` as a typed array parameter; exact placeholder syntax depends on the driver/ORM.

### 33.2. Validating tag IDs

If the API only permits dictionary tags 1..6, an SQL array column does not prevent out-of-range IDs by itself. Validate inputs and manage concurrency, or enforce an FK in a junction table.

### 33.3. Per-tag access control

Some tags may be tenant-scoped or permission-restricted. A shared ID array does not automatically prevent users from mixing tags belonging to another tenant. A junction table can include `tenant_id` and composite FKs/unique constraints to enforce tenant boundaries. Remember that **FKs alone never replace authorization/RLS**, so enforce proper access policies too.

### 33.4. Do not confuse performance with security

GIN accelerates membership filtering; it does not prevent unauthorized users from reading sensitive tags if their role has table privileges. Authorization and RLS (where needed) must be designed separately and verified via `EXPLAIN` under the restricted role.

### 33.5. Normalize names in text[] tags

If storing `text[]` values like `{'postgres','Postgres','POSTGRES'}`, the application must define case, collation, and synonym semantics. PostgreSQL GIN `array_ops` will not equate those three strings unless the comparison type/operator treats them as equal.

Using a canonical tag dictionary with integer IDs and FKs avoids label fragmentation.

---

## 34. Common mistakes and misconceptions

| Misconception | Consequence | Fix |
|---|---|---|
| “Arrays are sets, automatically unique and unordered” | Duplicates/ordering cause surprises | Define list vs. set semantics |
| “`{1,1}` @> `{1,1,1}` is false” | Misunderstanding containment multiplicity | `@>` tests element presence |
| “NULL array equals empty array” | Wrong `IS NULL`/`cardinality` queries | Use `NOT NULL DEFAULT '{}'` when appropriate |
| “A NULL element represents an unknown tag” | Complex three-valued UNKNOWN semantics | Forbid NULL elements in tag sets |
| “GIN automatically accelerates `ANY`” | Planner may skip GIN | Use `@> ARRAY[element]` and check `EXPLAIN` |
| “GIN speeds up any array function” | Predicates outside operator class | Stick to `@>`/`&&`/`<@`/`=` |
| “B-tree on an array searches tags fast” | B-tree compares whole array values | Use GIN for membership |
| “GIN prevents duplicate tags” | Arrays can still hold duplicates | Canonicalize writes or use junction PK |
| “GIN enforces FKs per element” | Orphan IDs slip through | Junction FK or explicit validation |
| “GIN always beats Seq Scan” | Common tags or small tables penalize index | Benchmark selectivity |
| “With GIN, `NOT contains` is fast too” | Negated filters often match most rows | Measure and revisit query design |
| “`cardinality=0` uses GIN fast” | It is an expression-count predicate | Add expression/partial index if needed |
| “20 slots means 20 distinct tags” | Duplicates still count in cardinality | Deduplicate if set semantics |
| “`COUNT(*)` after `unnest` equals posts/tag” | Duplicates inflate post counts | Use `COUNT(DISTINCT post_id)` |
| “`JOIN ... WHERE tag IN(...)` gives 1 row per post” | Multi-tag matches duplicate posts | Use `EXISTS` or `DISTINCT` |
| “`HAVING COUNT(*)=N` works with duplicate inputs” | Wrong `ALL` tags result | Deduplicate requested set |
| “Empty requested set returns zero rows” | `ALL` over empty set is vacuously true | Define empty semantics and write matching SQL |
| “FK auto-indexes the referencing column” | Parent delete/update scans child table | Index referencing FK column as needed |
| “`PK(post_id,tag_id)` accelerates tag lookups” | Column order wrong for reverse lookup | Create B-tree `(tag_id,post_id)` |
| “Appending a tag only edits 1 byte” | MVCC writes new row/TOAST/GIN entries | Measure write amplification |
| “App read-modify-write on arrays is always safe” | Lost updates/duplicates under concurrency | Atomic SQL update or lock/version |
| “Junction tables always use less disk” | More rows, FKs, and indexes | Measure heap + index footprint |
| “Arrays always fetch tags faster” | TOAST/cache/size can shift balance | Benchmark realistic sizes |
| “Junction tables add zero read overhead” | Joins and aggregations have cost | Measure index scans and joins |
| “JSONB arrays share `array_ops`” | Different JSONB GIN operators | Use `jsonb_ops`/`jsonb_path_ops` |
| “JSONB flexibility removes need for relations” | Loses per-edge FK and uniqueness | Model according to invariants |
| “Querying an `ARRAY(SELECT...)` view uses array GIN” | Computed dynamically, no stored GIN | Inspect view query plans |
| “Copying rows and switching reads finishes migration” | Loses writes made during backfill | Sync concurrent writes and audit |
| “Matching `COUNT(*)` proves models match” | Different edge pairs can sum equally | Reconcile pair-by-pair |
| “GIN pending list never affects latency” | Cleanup or query scans add jitter | Monitor `fastupdate`/VACUUM |
| “`CREATE INDEX CONCURRENTLY` is free” | Heavy I/O/WAL, waits, invalid risk | Monitor, plan headroom, handle rollback |
| “`EXPLAIN ANALYZE DELETE` only simulates” | Actually deletes rows | Omit `ANALYZE` or use lab transactions |
| “Index-Only Scan never touches heap” | Visibility map controls heap fetches | Inspect `Heap Fetches` |
| “`SELECT` without `ORDER BY` keeps insertion order” | Relations have no guaranteed order | Store `position` and use `ORDER BY` |
| “Drop array column right away” | Breaks older apps/workers | Follow expand/backfill/cutover/contract |

---

## 35. Pre-decision design checklist

### Data characteristics

- [ ] Is each element a **tag ID**, a scalar attribute, or a real entity?
- [ ] Must duplicates be **prohibited**?
- [ ] Is element order or multiplicity significant?
- [ ] How are NULL arrays, empty arrays, and NULL elements defined?
- [ ] What are the average, p95, and maximum elements per object?
- [ ] Is there a dictionary table requiring FK enforcement?
- [ ] Does each link need metadata, permissions, or timestamps?

### Query patterns

- [ ] Do queries primarily fetch all tags for one post, or search posts by tag?
- [ ] Are there `ANY`/`ALL`/`NOT`/whitelist filters?
- [ ] Are there `GROUP BY tag` analytics or multi-dimension joins?
- [ ] How skewed is the distribution between rare and ultra-common tags?
- [ ] Does the API require top-k or keyset pagination?
- [ ] Can indexes accelerate the exact predicates and expressions used?

### Update patterns

- [ ] How many writes per second occur?
- [ ] Do multiple clients edit tags on the same post concurrently?
- [ ] Do arrays regularly exceed inline limits and spill into TOAST?
- [ ] Are there bulk imports, bulk tag deletions, or tag renames?
- [ ] Are multi-table transactional invariants required?

### Operations

- [ ] Were queries benchmarked on representative scale rather than six posts?
- [ ] Was `EXPLAIN (ANALYZE, BUFFERS)` inspected?
- [ ] Was total heap + index + TOAST footprint accounted for?
- [ ] Were `INSERT`/`UPDATE`/`DELETE` and `VACUUM` costs measured?
- [ ] Is monitoring in place for GIN pending lists and autovacuum?
- [ ] Were WAL, replication, and backup overhead factored in?
- [ ] Is a migration/cutover plan ready if the model changes later?
- [ ] Are FKs, orphans, duplicates, and consistency continuously audited?

---

## 36. Practice exercises

These exercises use the `array_lab` schema and sample data. Any task creating indexes, altering tables, or updating rows must run inside a **dedicated practice database**. If you previously modified tags in earlier sections, reset to the initial state or recreate your own lab environment to verify sample answers. Never run `DROP`, `DELETE`, or `UPDATE` on production tables just to test lesson examples.

### Exercise 1 — Array or set?

Explain why `ARRAY[1,1,2]` is a valid array yet does not represent a canonical tag set. If business rules forbid duplicate tags, what invariants must be enforced?

### Exercise 2 — NULL vs. empty

Compare `NULL::integer[]`, `'{}'::integer[]`, and `ARRAY[NULL]::integer[]`. Write a query returning `cardinality` for each case.

### Exercise 3 — Containment ignores multiplicity

Predict and explain:

~~~sql
SELECT ARRAY[1]::int[] @> ARRAY[1,1]::int[];
~~~

If the requirement is “contains element 1 exactly twice,” is this operator appropriate?

### Exercise 4 — Array equality

Are `ARRAY[1,2]` and `ARRAY[2,1]` equal under `=`? What must a query do to compare **the same set of tags**?

### Exercise 5 — Finding a single tag

Write a query finding posts with tag 1 using `@>` on `array_lab.posts_array`. On the initial dataset, which `post_id`s are returned?

### Exercise 6 — Finding all tags

Write a query finding posts with both tag 1 **and** tag 4. Which operator fits, and why not `&&`?

### Exercise 7 — Finding any tag

Write a query finding posts with tag 4 **or** tag 5. What `post_id`s are expected?

### Exercise 8 — Whitelist

Write a query finding posts using only tags from `{1,2,4}` via `<@`. Why does untagged post 105 match?

### Exercise 9 — No tags

Write a query finding untagged posts. Contrast `cardinality(tag_ids)=0` vs. `tag_ids IS NULL` in the lab schema.

### Exercise 10 — Without tag 4

Write an array query finding posts without tag 4. Can you assume GIN speeds up a negated predicate as effectively as a positive one?

### Exercise 11 — ANY vs. GIN

Explain the difference between:

~~~sql
WHERE 4 = ANY(tag_ids)
~~~

and:

~~~sql
WHERE tag_ids @> ARRAY[4]::integer[]
~~~

How do they differ regarding GIN `array_ops` operator support? Are there NULL edge cases to watch for?

### Exercise 12 — GIN index

Write the statement to create a GIN index on `tag_ids`. Which operators does built-in `array_ops` support? Is the planner guaranteed to pick GIN on a six-row table?

### Exercise 13 — B-tree on an array

Create a B-tree index on `tag_ids`. Does it locate element 4 inside arrays like GIN? When does a B-tree on array values make sense?

### Exercise 14 — Index for count predicates

If you frequently filter `cardinality(tag_ids)=0`, write an appropriate expression index or partial index and explain why GIN membership does not automatically optimize it.

### Exercise 15 — EXPLAIN GIN

Run `EXPLAIN (ANALYZE, BUFFERS)` on the query finding posts with tags `{1,4}`. If `Bitmap Index Scan` and `Bitmap Heap Scan` appear, what does each node do?

### Exercise 16 — Recheck

Does `Recheck Cond` in a Bitmap Heap Scan mean GIN is broken or returning wrong results? Which additional fields show false positives or lossy pages?

### Exercise 17 — Creating a junction table

Write the SQL defining `post_tags(post_id,tag_id)` with a composite PK and two FKs to `posts_rel` and `tags`. Can the same tag be attached twice to one post?

### Exercise 18 — Reverse index

Which query does `PK(post_id,tag_id)` serve? Create the index needed to list all posts carrying tag 4.

### Exercise 19 — Linked any tag

Write an `EXISTS` query finding posts with **at least one** tag in `{4,5}`. Why can a direct JOIN duplicate posts?

### Exercise 20 — Linked all tags

Write a junction query finding posts carrying **both** tag 1 and tag 4 using `GROUP BY`/`HAVING` or two `EXISTS` clauses.

### Exercise 21 — Dynamic ALL request

A user sends a requested list `[1,1,4]`. Why shouldn't you use `HAVING COUNT(*)=3` directly on link rows? How should the input be normalized?

### Exercise 22 — ALL with an empty set

If an API asks for “posts containing **all** tags in an empty set,” what logic applies? Why might a plain `JOIN`/`HAVING` query return nothing whereas `@> ARRAY[]` returns all non-NULL arrays?

### Exercise 23 — Counting tags on a post

Write SQL for both the array model and the junction model to count tags on post 101. When an array contains duplicates, how do the two counts differ?

### Exercise 24 — Popular tag report

Write a junction-model query counting posts per tag (including unused tags), and explain why `LEFT JOIN` requires `COUNT(pt.post_id)` instead of `COUNT(*)`.

### Exercise 25 — Counting posts per tag via unnest

Write an array query counting **distinct posts** per `tag_id` using `unnest`. What goes wrong if you use `COUNT(*)` when arrays contain duplicate tag IDs?

### Exercise 26 — Concurrent tagging

Two clients add tag 5 to post 101 concurrently. What does the junction PK + `ON CONFLICT DO NOTHING` prevent? Why does application read-modify-write on arrays risk lost updates?

### Exercise 27 — Array append/remove

Write SQL to append tag 5 if missing from a post, and SQL to remove tag 5. Does `array_remove` delete one occurrence or all occurrences?

### Exercise 28 — Referential integrity

A post contains tag 9999 while the dictionary only holds 1..6. Why doesn't a GIN index catch this? Which model natively blocks it via FK?

### Exercise 29 — Deleting from the tag dictionary

In the linked model without `ON DELETE CASCADE` on `tag_id`, what happens when deleting a referenced tag? What happens with an ID array?

### Exercise 30 — Edge metadata

Business rules require tracking who assigned each tag, when, and a confidence level. Would you pick an ID array, JSONB, or a junction table as the primary model? Explain.

### Exercise 31 — Tag order

If users reorder tags by drag-and-drop, what column should the junction table add? Does SQL guarantee rows return in insertion order by default?

### Exercise 32 — ARRAY(SELECT ...)

Write a query returning a sorted `integer[]` of `tag_id`s per post directly from `post_tags` without storing a second array column.

### Exercise 33 — JSONB vs. SQL arrays

Write SQL comparing `'[1,2]'::jsonb @> '[2]'::jsonb` and `ARRAY[1,2]::int[] @> ARRAY[2]::int[]`. Do they use the same GIN operator class?

### Exercise 34 — JSONB tags example

A table has a JSONB column `doc` storing `{"tags":["PostgreSQL"]}`. Write a containment filter and a supporting index; why can't `array_ops` be used?

### Exercise 35 — GIN pending list

How does GIN `fastupdate` help, and what overhead can it introduce? Why is disabling autovacuum to avoid cleanup unsafe?

### Exercise 36 — TOAST and HOT

A post has 10,000 tags, and one tag in the indexed array is updated. What costs arise? Why can a junction model perform better on single-edge updates?

### Exercise 37 — Fair benchmarking

List at least six metrics or operations to measure when comparing GIN arrays against B-tree links across one million posts. Why must rare and common tags be tested separately?

### Exercise 38 — Pre-migration data audit

Write queries to detect duplicate elements and orphan tag IDs in `posts_array` before migrating to the linked model.

### Exercise 39 — Backfill and concurrent writes

Outline a migration workflow from arrays to a junction table that avoids losing concurrent writes during backfill. Why doesn't comparing `COUNT(*)` across tables prove the link sets match?

### Exercise 40 — Architecture synthesis

Choose an initial model and index strategy for three scenarios:

1. Each row holds 3–8 fixed config codes, almost never updated, frequently queried with “has any of these codes.”
2. Each product has hundreds of categories edited frequently by admins, requiring FKs, category metadata, and top-category reports.
3. An API serves an ordered playlist allowing repeated tracks, where each item tracks `position`/`created_by` under multiple concurrent writers.

State your rationale, trade-offs, and how you would benchmark to validate each choice.

---

## 37. Suggested solutions

### Exercise 1 — Arrays are not sets automatically

`ARRAY[1,1,2]` has three element slots, including two copies of 1. If tags represent a set, duplicates must be prevented. The junction table's `PK(post_id,tag_id)` enforces uniqueness natively; an array column needs controlled canonicalization/validation. A GIN index is not a per-element unique constraint.

### Exercise 2 — NULL, empty, and NULL element

~~~sql
SELECT cardinality(NULL::integer[]) AS null_array_count,
       cardinality('{}'::integer[]) AS empty_array_count,
       cardinality(ARRAY[NULL]::integer[]) AS null_element_count;
~~~

Expected outputs: NULL, 0, 1. If “untagged” means empty set in your domain, declare `NOT NULL DEFAULT '{}'::int[]` and forbid NULL elements.

### Exercise 3 — Containment ignores multiplicity

~~~sql
SELECT ARRAY[1]::int[] @> ARRAY[1,1]::int[];
~~~

Returns TRUE: array containment tests element presence rather than requiring two distinct copies. If multiplicity matters, store counts/line items or compare arrays under different rules.

### Exercise 4 — Ordered equality

`ARRAY[1,2] = ARRAY[2,1]` is FALSE. To test whether two arrays contain the same tag set, canonicalize to sorted distinct elements before comparing with `=`, or check bidirectional containment `a @> b AND b @> a` while accounting for NULLs, dimensions, and business rules.

### Exercise 5 — Single tag

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1]::int[]
ORDER BY post_id;
~~~

Expect 101, 102, 106 on the initial lab dataset.

### Exercise 6 — All tags

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1,4]::int[]
ORDER BY post_id;
~~~

Expect 101, 106. `&&` only checks for **at least one** common element, not both 1 and 4.

### Exercise 7 — At least one tag

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids && ARRAY[4,5]::int[]
ORDER BY post_id;
~~~

Expect 101, 102, 104, 106.

### Exercise 8 — Whitelist

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids <@ ARRAY[1,2,4]::int[]
ORDER BY post_id;
~~~

Expect 101, 105. An empty array is a subset of every non-NULL array under set containment semantics, not a filter bug.

### Exercise 9 — Empty array

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE cardinality(tag_ids)=0;
~~~

Expect post 105. Because `tag_ids` is `NOT NULL`, `tag_ids IS NULL` returns zero rows; NULL arrays differ from empty arrays.

### Exercise 10 — Without tag

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE NOT (tag_ids @> ARRAY[4]::int[])
ORDER BY post_id;
~~~

Expect 102, 103, 105. Negative predicates typically match most rows and rarely gain as much from inverted index lookups as positive key lookups; check `EXPLAIN`.

### Exercise 11 — ANY vs. GIN

`4 = ANY(tag_ids)` is a scalar-array comparison; `tag_ids @> ARRAY[4]` uses the array containment operator supported by GIN `array_ops`. Do not assume the planner rewrites `ANY` into containment automatically. With NULL elements, the two can differ on TRUE/FALSE/UNKNOWN in general boolean contexts even when selecting identical rows in non-NULL membership `WHERE` filters.

### Exercise 12 — Creating GIN

~~~sql
CREATE INDEX idx_posts_array_tags_gin_answer
ON array_lab.posts_array USING gin(tag_ids);
~~~

GIN `array_ops` supports `@>`, `<@`, `&&`, and `=`. On six rows, Seq Scan is cheaper; having an index never forces the planner to pick it.

### Exercise 13 — B-tree array

~~~sql
CREATE INDEX idx_posts_exact_tags_btree_answer
ON array_lab.posts_array USING btree(tag_ids);
~~~

B-tree compares whole array values rather than acting as an inverted index for arbitrary internal tags. It fits exact array equality or whole-array ordering when workloads require them.

### Exercise 14 — Index for counts

~~~sql
CREATE INDEX idx_posts_no_tags_answer
ON array_lab.posts_array(post_id)
WHERE cardinality(tag_ids)=0;
~~~

Or an expression index:

~~~sql
CREATE INDEX idx_posts_tag_count_answer
ON array_lab.posts_array ((cardinality(tag_ids)));
~~~

Pick **one appropriate option**, not both. GIN `array_ops` indexes element presence, not element counts.

### Exercise 15 — EXPLAIN GIN

~~~sql
EXPLAIN (ANALYZE,BUFFERS)
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1,4]::int[];
~~~

With Bitmap Index Scan, the index collects candidate heap pointers; Bitmap Heap Scan retrieves rows and rechecks conditions where needed. Small tables often choose Seq Scan.

### Exercise 16 — Recheck

No. Recheck verifies candidates safely rather than signaling corruption. Inspect `Heap Blocks: exact/lossy`, `Rows Removed by Index Recheck`, index quals, and overall plan structure.

### Exercise 17 — Junction constraints

~~~sql
CREATE TABLE array_lab.post_tags_answer (
    post_id BIGINT NOT NULL
        REFERENCES array_lab.posts_rel(post_id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL
        REFERENCES array_lab.tags(tag_id),
    PRIMARY KEY(post_id,tag_id)
);
~~~

A post–tag pair cannot appear twice due to the composite PK, while many posts can still share a tag and each post can carry many tags.

### Exercise 18 — Reverse B-tree

`PK(post_id,tag_id)` serves finding a post's tags. To find posts by tag:

~~~sql
CREATE INDEX idx_post_tags_answer_reverse
ON array_lab.post_tags(tag_id,post_id);
~~~

Skip creating a duplicate if an identical index already exists in your lab.

### Exercise 19 — EXISTS any

~~~sql
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE EXISTS (
    SELECT 1 FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id
      AND pt.tag_id IN (4,5)
)
ORDER BY p.post_id;
~~~

Expect 101, 102, 104, 106. A direct JOIN emits duplicate post rows if a post carries both 4 and 5; `EXISTS` tests pure existence.

### Exercise 20 — Linked all

~~~sql
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
JOIN array_lab.post_tags AS pt ON pt.post_id=p.post_id
WHERE pt.tag_id IN (1,4)
GROUP BY p.post_id,p.title
HAVING COUNT(DISTINCT pt.tag_id)=2
ORDER BY p.post_id;
~~~

Expect 101, 106. Although the PK blocks duplicate post–tag edges, `COUNT(DISTINCT ...)` keeps the `ALL` logic clear for distinct target sets.

### Exercise 21 — Requested duplicates

Input `[1,1,4]` has three slots but only **two distinct tag IDs**. Because the junction table stores at most one row per pair, `COUNT(*)=3` will miscount or match nothing. Deduplicate inputs with `DISTINCT` into `{1,4}` and compare count = 2, or use two `EXISTS` predicates.

### Exercise 22 — ALL with empty set

Under “no requested tag is missing,” every post satisfies `ALL(empty set)`. Array `@> '{}'` is true for non-NULL arrays. A JOIN starting from an empty `requested` set produces zero rows to group, so matching empty-set semantics requires explicit empty handling or **nested `NOT EXISTS`** (relational division with vacuous truth).

### Exercise 23 — Tag count per post

Array:

~~~sql
SELECT post_id,cardinality(tag_ids) AS tag_count
FROM array_lab.posts_array
WHERE post_id=101;
~~~

Junction:

~~~sql
SELECT COUNT(*) AS tag_count
FROM array_lab.post_tags
WHERE post_id=101;
~~~

Both equal 3 on the original data. With duplicate elements in an array, `cardinality` counts all slots whereas the junction PK permits only distinct pairs.

### Exercise 24 — Report all tags

~~~sql
SELECT
    d.tag_id,d.tag_name,
    COUNT(pt.post_id) AS posts_count
FROM array_lab.tags AS d
LEFT JOIN array_lab.post_tags AS pt ON pt.tag_id=d.tag_id
GROUP BY d.tag_id,d.tag_name
ORDER BY d.tag_id;
~~~

`COUNT(pt.post_id)` ignores NULLs from `LEFT JOIN`, giving 0 for unused tags, whereas `COUNT(*)` counts the placeholder row as 1.

### Exercise 25 — Distinct post count from arrays

~~~sql
SELECT
    u.tag_id,
    COUNT(DISTINCT p.post_id) AS posts_count
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
GROUP BY u.tag_id
ORDER BY u.tag_id;
~~~

If an array stores `{1,1,2}`, `COUNT(*)` double-counts the post for tag 1; `COUNT(DISTINCT post_id)` prevents that bug.

### Exercise 26 — Concurrent inserts

`PK(post_id,tag_id)` prevents duplicate pairs in the database; `ON CONFLICT DO NOTHING` makes retries idempotent per pair. With arrays, two clients reading the same snapshot and writing back whole arrays risk overwriting each other's additions. Use locked/atomic server-side updates or optimistic version checks.

### Exercise 27 — Append/remove

~~~sql
UPDATE array_lab.posts_array
SET tag_ids=array_append(tag_ids,5)
WHERE post_id=103
  AND NOT (tag_ids @> ARRAY[5]::int[]);

UPDATE array_lab.posts_array
SET tag_ids=array_remove(tag_ids,5)
WHERE post_id=103;
~~~

`array_remove` strips **all** occurrences of 5. Removing just one occurrence in an ordered list requires different logic.

### Exercise 28 — Per-element FK

GIN only indexes array members for search; it never validates IDs against a catalog. `{9999}` can be inserted freely without custom checks. A junction table enforces `FOREIGN KEY(tag_id) REFERENCES tags(tag_id)` to block orphan IDs.

### Exercise 29 — Deleting dictionary tags

In the linked model with a non-cascading tag FK, deleting a referenced tag **is rejected** by the FK. With ID arrays, the catalog row can be deleted, leaving dangling orphan IDs inside stored arrays.

### Exercise 30 — Edge metadata

Pick a **junction table as the source of truth**: each row stores `post_id`, `tag_id`, `assigned_at`, `assigned_by`, and `confidence` with proper constraints and indexes. JSONB/arrays allow flexible shapes yet complicate FKs, uniqueness, and per-link updates. Edge-level metadata is a classic indicator for a junction table.

### Exercise 31 — Tag order

Add a `position` or `display_order` column to the junction row with uniqueness constraints per post where needed. Queries must specify `ORDER BY display_order,tag_id` or another deterministic key; SQL relations **do not guarantee** insertion order without `ORDER BY`.

### Exercise 32 — Building arrays from links

~~~sql
SELECT
    p.post_id,
    p.title,
    ARRAY(
        SELECT pt.tag_id
        FROM array_lab.post_tags AS pt
        WHERE pt.post_id=p.post_id
        ORDER BY pt.tag_id
    ) AS tag_ids
FROM array_lab.posts_rel AS p
ORDER BY p.post_id;
~~~

For untagged posts, `ARRAY(SELECT ...)` cleanly returns `{}` without storing a duplicate array column.

### Exercise 33 — SQL array vs. JSONB array

~~~sql
SELECT ARRAY[1,2]::int[] @> ARRAY[2]::int[] AS sql_array_contains,
       '[1,2]'::jsonb @> '[2]'::jsonb AS jsonb_contains;
~~~

Both show containment, yet they use **different operator classes and type semantics**: GIN `array_ops` for SQL arrays vs. GIN `jsonb_ops`/`jsonb_path_ops` for JSONB.

### Exercise 34 — JSONB tags

~~~sql
SELECT post_id
FROM array_lab.posts_jsonb
WHERE doc @> '{"tags":["PostgreSQL"]}'::jsonb;
~~~

Candidate index:

~~~sql
CREATE INDEX idx_posts_jsonb_doc_answer
ON array_lab.posts_jsonb USING gin(doc);
~~~

`array_ops` does not apply to JSONB because JSONB is a distinct type with its own operators and operator classes. For queries using `(doc->'tags') ? ...`, consider a GIN expression index on that exact expression.

### Exercise 35 — GIN fastupdate

`fastupdate` batches new index entries into a pending list to aid write throughput, at the cost of queries scanning pending entries and periodic cleanup latency spikes. Autovacuum/VACUUM also handles MVCC dead tuples and pending-list merges; **never turn it off** merely to dodge cleanup work.

### Exercise 36 — TOAST and HOT

Updating a large indexed array generates a new row version, new TOAST chunks, GIN updates, WAL, and dead tuples, while disabling HOT updates because an indexed column changed. A junction table turns adding/removing one tag into a small link `INSERT`/`DELETE`, trading off higher row count, PK/FK checks, and B-tree maintenance.

### Exercise 37 — Fair benchmarking

Measure at least: p50/p95 query latency, `shared hit/read` buffers, temp I/O, GIN/B-tree index sizes, total table+TOAST footprint, `INSERT`/`UPDATE`/`DELETE` throughput, WAL volume, VACUUM/cleanup overhead, memory usage, planning time, actual rows returned, and cardinality estimate accuracy.

Rare tags yield high index selectivity; common tags match most rows where Seq Scan or another join strategy wins. Measuring only one tag misrepresents the workload.

### Exercise 38 — Pre-backfill audit

Duplicate elements:

~~~sql
SELECT p.post_id,u.tag_id,COUNT(*) AS occurrences
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
GROUP BY p.post_id,u.tag_id
HAVING COUNT(*)>1;
~~~

Orphans:

~~~sql
SELECT DISTINCT p.post_id,u.tag_id
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
LEFT JOIN array_lab.tags AS d ON d.tag_id=u.tag_id
WHERE d.tag_id IS NULL;
~~~

Define cleanup rules for each anomaly before PK/FK constraints on the junction table reject invalid rows.

### Exercise 39 — Migrating with concurrent writes

Workflow:

1. Audit duplicates, orphans, NULLs, and invariants.
2. Create linked tables/PK/FK/indexes.
3. Backfill in batches with checkpoints and retries.
4. Capture/sync concurrent changes via transactional dual-write, triggers/CDC, or a controlled maintenance cutover.
5. Reconcile **every post–tag pair**, not just total row counts.
6. Run shadow/canary reads to verify query parity.
7. Cut over source of truth with a rollback option.
8. Monitor drift and remove the array column only after all consumers have migrated.

Two tables with equal `COUNT(*)` can still contain **different pairs**; verify via set equality, anti-joins, or keyed checksums.

### Exercise 40 — Three scenarios

**1. 3–8 fixed config codes, read-mostly:** an `integer[]` column with `NOT NULL DEFAULT '{}'`, duplicate/NULL guards, and a GIN index for `@>`/`&&` is a strong fit. Benchmark selectivity, size, and write cost; switch to a junction table if strict FKs are required.

**2. Products with hundreds of categories, metadata, and frequent edits:** use a `product_categories(product_id,category_id)` junction table with composite PK, FKs, and reverse index `(category_id,product_id)`. Benchmark join throughput, category analytics, DML overhead, and storage. An array can serve only as a read projection, never replacing the constrained source of truth.

**3. Ordered playlist allowing duplicates:** use `playlist_items(playlist_id,item_id,position,created_by,...)` or a surrogate row ID with position uniqueness and FKs. Never use `PK(playlist_id,item_id)` if the same track can appear multiple times. Use transactions/locking or optimistic concurrency for reordering and measure write contention. Small arrays may serve DTOs/caches, yet cannot match row-level metadata and concurrency control.

---

## 38. PostgreSQL documentation and search keywords

When cross-checking against your exact PostgreSQL major version, consult:

- [PostgreSQL — Array Types](https://www.postgresql.org/docs/current/arrays.html): declarations, element access/updates, array constructors, dimensions.
- [PostgreSQL — Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html): `@>`, `<@`, `&&`, `cardinality`, `array_position`, `unnest`.
- [PostgreSQL — Index Types](https://www.postgresql.org/docs/current/indexes-types.html): B-tree, GIN, GiST, SP-GiST, BRIN.
- [PostgreSQL — GIN Indexes](https://www.postgresql.org/docs/current/gin.html): inverted indexes, operator classes, pending-list behavior, `fastupdate`.
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): `USING gin`, expression/partial indexes, `CONCURRENTLY`.
- [PostgreSQL — Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html): column ordering and composite index usage.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): `PRIMARY KEY`, `UNIQUE`, `CHECK`, `FOREIGN KEY`.
- [PostgreSQL — Query Planning Statistics](https://www.postgresql.org/docs/current/planner-stats.html): `pg_stats`, histograms/MCVs, selectivity estimation.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): query plans, actual rows/loops, `BUFFERS`, index vs. sequential scans.
- [PostgreSQL — TOAST](https://www.postgresql.org/docs/current/storage-toast.html): variable-length attribute storage.
- [PostgreSQL — MVCC](https://www.postgresql.org/docs/current/mvcc.html): transaction visibility and row versions.

Links under `/current/` may reflect a newer PostgreSQL major version than your environment. Whenever an operator, maintenance rule, or DDL behavior is production-critical, check docs for your **exact major version** and test on staging.

---

## 39. Summary

**GIN indexes help PostgreSQL quickly locate elements stored inside array columns; junction tables model many-to-many relationships with explicit relational constraints. The two options solve different classes of problems and should never be swapped without considering business semantics.**

Key takeaways:

- SQL arrays are **ordered values that permit duplicates and NULLs**, not sets.
- Array operators `@>`, `<@`, `&&`, and `=` carry distinct semantics; **`@>` does not count multiplicity**.
- **GIN `array_ops`** accelerates membership/overlap/containment on SQL arrays. `element = ANY(array_col)` is not the same indexable operator form; test `@> ARRAY[element]` when targeting GIN.
- **B-tree on arrays** compares whole array values rather than acting as an inverted index; `cardinality(array)` predicates may need separate expression or partial indexes.
- A GIN index provides no FKs, per-element uniqueness, cardinality limits, or normalization. Enforcing those invariants requires additional mechanisms or a **junction table**.
- **Junction tables** with `PRIMARY KEY(post_id,tag_id)` and two FKs prevent duplicate pairs and orphan references. A reverse index `(tag_id,post_id)` accelerates tag-to-post lookups.
- `EXISTS`, `NOT EXISTS`, and `GROUP BY`/`HAVING` express ANY/ALL/NONE queries on junction tables. Watch out for duplicate join multiplication and **empty requested sets**.
- Modifying one tag in an array writes a new row version/TOAST/GIN update, whereas a linked `INSERT`/`DELETE` modifies one edge row; conversely, arrays fetch a single post's full tag list conveniently.
- Tag analytics, edge metadata, per-tag permissions, dictionary renames/deletes, and high concurrent writes usually make **junction tables** easier to maintain.
- JSONB arrays, SQL arrays, and junction tables have **different operators and index classes**; never choose JSONB solely because API payloads arrive as JSON when the domain needs FKs and uniqueness.
- Optimization must consider **query latency, write overhead, GIN pending lists, VACUUM, total heap/index/TOAST storage, caching, and concurrency**, not a single `EXPLAIN` on a tiny table.
- When migrating, **batch backfill + concurrent write sync + pair-by-pair reconciliation + cutover + rollback** matter far more than a one-off `INSERT ... SELECT`. You can expose arrays from a junction table via `ARRAY(SELECT ...)` without storing two sources of truth.

Practical workflow: **determine whether elements are attributes or relationships → lock down NULL/duplicate/ordering/FK semantics → pick array + GIN or junction + B-tree → write accurate ANY/ALL/NONE queries → measure EXPLAIN, stats, and write overhead → keep only necessary indexes → deploy and monitor consistency under real workloads**.
