# Array Operators, ANY, ALL, and Finding Intersections in PostgreSQL

In relational databases, we usually represent many-to-many relationships using a junction table. However, PostgreSQL also provides the **array** type, allowing a single column to store multiple elements of the same type—for example `TEXT[]` holding tags, `INTEGER[]` holding scores, or `UUID[]` holding a list of references.

When working with arrays, questions are often no longer as simple as `column = value`. An application may need to ask:

- “Does a document contain **both** the `sql` and `postgresql` tags?”
- “Does a document have **at least one** tag from the group `gin`, `api`?”
- “Is a given value present in the array?”
- “Is the score `90` greater than **every** threshold in the array?”
- “Which elements do two arrays share in their **intersection**?”
- “If there is a `NULL` element, an empty array, or a `NULL` array, does the condition evaluate to `TRUE`, `FALSE`, or `NULL`?”
- “Should the intersection be computed as a **distinct set**, or must it preserve element **multiplicity**?”

PostgreSQL offers array operators such as `@>`, `<@`, and `&&`, quantified expressions `ANY`/`ALL`, functions like `unnest`, `array_position`, and `array_agg`, and the set operation `INTERSECT`. These tools are powerful, yet they are **not equivalent in every case**.

Example:

```sql
SELECT
    ARRAY['sql', 'postgresql']::TEXT[]
        @> ARRAY['sql']::TEXT[] AS contains_sql,
    ARRAY['sql', 'postgresql']::TEXT[]
        && ARRAY['python', 'sql']::TEXT[] AS overlaps,
    'sql' = ANY(ARRAY['sql', 'postgresql']::TEXT[])
        AS scalar_matches,
    10 > ALL(ARRAY[2, 3, 5]::INTEGER[])
        AS greater_than_every_threshold;
```

All four expressions above can return `TRUE`, yet they test **four different logical relationships**. Understanding these relationships accurately determines query correctness, GIN index eligibility, and data design choices.

This lesson belongs to the **JSON and Arrays** chapter of the **Database Engine Relational PostgreSQL** module, focusing on using PostgreSQL SQL arrays in queries, edge cases of `ANY`/`ALL`, computing intersections, and techniques for writing safe, unambiguous, optimizable SQL.

---

## 1. Learning objectives

After this lesson, you will be able to:

1. Declare, initialize, read, and distinguish PostgreSQL arrays from JSON strings or comma-separated text strings.
2. Use the array operators `@>`, `<@`, `&&`, and `=` with accurate semantics.
3. Distinguish an array that **contains all** of a target set of elements from an array that has a **non-empty overlap**.
4. Explain the difference between `value = ANY(array)` and `array_column @> ARRAY[value]`, especially regarding index usage.
5. Understand `ANY`/`SOME` and `ALL` with comparison operators such as `=`, `<>`, `<`, and `>`.
6. Predict `TRUE`, `FALSE`, and `NULL` outcomes when encountering empty arrays, NULL arrays, NULL elements, or NULL operands.
7. Understand `value <> ALL(array)` and `NOT (value = ANY(array))`, while avoiding the `NOT IN` pitfall with NULL.
8. Find the **set intersection** of two arrays using `unnest` and `INTERSECT`, or by filtering with `= ANY(...)`.
9. Distinguish `INTERSECT` from `INTERSECT ALL` and avoid mistaking `@>` for a multiplicity-aware check.
10. Preserve order when unnesting arrays with `WITH ORDINALITY` and rebuild arrays using `array_agg(... ORDER BY ...)`.
11. Work with `cardinality`, `array_length`, `array_position`, `array_positions`, `array_append`, `array_remove`, and related functions.
12. Know when a GIN `array_ops` index helps, how to read `EXPLAIN`, and index limitations for `ANY`.
13. Choose between an array and a **relational child table** when foreign keys, uniqueness, multidimensional queries, or frequent per-element updates are required.
14. Use bind parameters in Java/JDBC when passing an array into a query.
15. Write and test queries for computing intersections, tag filtering, tag exclusion, element statistics, and non-destructive array updates.

> **Note:** The `DROP TABLE`, `INSERT`, and `UPDATE` statements in the lab are only meant for a disposable practice database. This lesson explains PostgreSQL behavior; do not assume `EXPLAIN` plans will choose the exact same path across all versions or dataset sizes.

---

## 2. Array types in PostgreSQL

An array column can hold multiple elements of the same type:

```sql
CREATE TABLE example_arrays (
    item_id BIGINT PRIMARY KEY,
    tags TEXT[],
    scores INTEGER[],
    prices NUMERIC(12,2)[],
    flags BOOLEAN[]
);
```

The `[]` suffix denotes an **array type**:

| Type | Example elements | Common use cases |
| --- | --- | --- |
| `TEXT[]` | `'sql'`, `'api'` | Tags, keyword groups |
| `INTEGER[]` | `10`, `20` | Codes or scores |
| `UUID[]` | UUID | Reference ID lists |
| `NUMERIC[]` | `12.50`, `100.00` | Sets of exact numeric values |
| `BOOLEAN[]` | `TRUE`, `FALSE` | Sets of condition flags |
| `TIMESTAMPTZ[]` | Timestamp | Timestamps |

Array elements generally share the same type or are coerced by PostgreSQL to a suitable common type. Do not treat `TEXT[]` as a “JSON array”; JSON/JSONB has its own representation and operators.

### 2.1. Creating arrays with ARRAY[...]

```sql
SELECT
    ARRAY['sql', 'postgresql', 'array']::TEXT[] AS tags,
    ARRAY[10, 20, 30]::INTEGER[] AS scores,
    ARRAY[TRUE, FALSE, TRUE]::BOOLEAN[] AS flags;
```

When PostgreSQL can infer the type from the elements, you can omit the cast. However, explicit casts make instructional queries, parameterized queries, and empty arrays clearer.

### 2.2. Curly-brace literal syntax

PostgreSQL also accepts array literals:

```sql
SELECT
    '{"sql","postgresql","array"}'::TEXT[] AS tags,
    '{10,20,30}'::INTEGER[] AS scores;
```

The curly braces here belong to **PostgreSQL array literal syntax**, not a JSON object.

In dynamic SQL, use bind parameters or `ARRAY[...]` instead of manually assembling a text literal with error-prone escaping.

### 2.3. Empty arrays differ from NULL

```sql
SELECT
    ARRAY[]::TEXT[] AS empty_tags,
    NULL::TEXT[] AS unknown_tags,
    ARRAY[NULL::TEXT] AS one_null_element;
```

These three values are distinct:

- `ARRAY[]::TEXT[]`: an array **known to be empty**, having 0 elements.
- `NULL::TEXT[]`: the **entire array column value is NULL**.
- `ARRAY[NULL::TEXT]`: an array **with one element, where that element is NULL**.

This is the most fundamental distinction when learning `ANY`, `ALL`, and `unnest`.

### 2.4. Element indexing

Standard one-dimensional arrays are accessed starting at position 1:

```sql
SELECT
    (ARRAY['sql', 'api', 'db']::TEXT[])[1] AS first_tag,
    (ARRAY['sql', 'api', 'db']::TEXT[])[3] AS third_tag;
```

PostgreSQL allows arrays with a lower bound other than 1 in certain cases; do not treat 1-based indexing as an invariant of every stored array. When unnesting with `WITH ORDINALITY`, ordinality is a generated sequence starting at 1, not necessarily equal to the array's original subscript.

---

## 3. Lab setup: documents with tags and scores

Let's create a small table so every operator has test cases.

### 3.1. Create schema and table

> **Warning:** `DROP TABLE` deletes any existing lab table with the same name. Run only on a dedicated practice database.

```sql
CREATE SCHEMA IF NOT EXISTS array_ops_lab;

DROP TABLE IF EXISTS array_ops_lab.documents;

CREATE TABLE array_ops_lab.documents (
    doc_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    tags TEXT[],
    scores INTEGER[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

For now, we **allow both `tags=NULL` and NULL elements** so we can fully explain three-valued SQL logic. In a real application, you might choose stricter constraints.

### 3.2. Load data

```sql
INSERT INTO array_ops_lab.documents (
    doc_id, title, tags, scores
)
VALUES
    (
        1, 'PostgreSQL arrays',
        ARRAY['sql','postgresql','array']::TEXT[],
        ARRAY[10,20,30]::INTEGER[]
    ),
    (
        2, 'Java backend',
        ARRAY['java','api','backend']::TEXT[],
        ARRAY[8,6]::INTEGER[]
    ),
    (
        3, 'SQL and JSON',
        ARRAY['sql','json','search']::TEXT[],
        ARRAY[3,4,5]::INTEGER[]
    ),
    (
        4, 'Duplicate tags',
        ARRAY['sql','sql','etl']::TEXT[],
        ARRAY[7,7]::INTEGER[]
    ),
    (
        5, 'Empty arrays',
        ARRAY[]::TEXT[],
        ARRAY[]::INTEGER[]
    ),
    (
        6, 'Unknown arrays',
        NULL::TEXT[],
        NULL::INTEGER[]
    ),
    (
        7, 'Partially unknown tags',
        ARRAY['sql',NULL::TEXT,'qa'],
        ARRAY[NULL::INTEGER,5,10]
    ),
    (
        8, 'Only NULL elements',
        ARRAY[NULL::TEXT],
        ARRAY[NULL::INTEGER]
    ),
    (
        9, 'GIN search',
        ARRAY['postgresql','gin','search']::TEXT[],
        ARRAY[1,2,3]::INTEGER[]
    ),
    (
        10, 'PostgreSQL intersection',
        ARRAY['sql','postgresql','gin','array']::TEXT[],
        ARRAY[8,9]::INTEGER[]
    );

ANALYZE array_ops_lab.documents;
```

### 3.3. Inspect the data

```sql
SELECT
    doc_id,
    title,
    tags,
    scores,
    cardinality(tags) AS tag_count
FROM array_ops_lab.documents
ORDER BY doc_id;
```

Key rows to note:

| doc_id | tags | Meaning |
| ---: | --- | --- |
| 1 | `{sql,postgresql,array}` | Has both SQL and PostgreSQL |
| 2 | `{java,api,backend}` | Does not have SQL |
| 3 | `{sql,json,search}` | Has SQL, no PostgreSQL |
| 4 | `{sql,sql,etl}` | Contains duplicate elements |
| 5 | `{}` | Empty array |
| 6 | `NULL` | Entire array is NULL |
| 7 | `{sql,NULL,qa}` | Has SQL and one NULL element |
| 8 | `{NULL}` | Only a NULL element |
| 9 | `{postgresql,gin,search}` | Has PostgreSQL and GIN |
| 10 | `{sql,postgresql,gin,array}` | Has SQL, PostgreSQL, and GIN |

The examples below assume the lab table has not yet been altered by UPDATE exercises from later sections.

---

## 4. Three key array operators: @>, <@, and &&

The table below serves as the shortest “dictionary” so you never confuse their semantics:

| Operator | Read as | What does it ask? |
| --- | --- | --- |
| `left @> right` | left contains right | Are all required elements from right present in left? |
| `left <@ right` | left is contained by right | Are all elements of left present in right? |
| `left && right` | two arrays overlap | Is there at least one element present in both? |
| `left = right` | two arrays are equal | Are the array values equal under array comparison? |
| `left <> right` | two arrays are not equal | Are they unequal under array comparison? |

For one-dimensional text/int arrays containing **non-NULL elements**, these models are very intuitive.

### 4.1. @> — array contains all required elements

```sql
SELECT
    doc_id, title, tags
FROM array_ops_lab.documents
WHERE tags @> ARRAY['sql','postgresql']::TEXT[]
ORDER BY doc_id;
```

Expected lab output:

| doc_id | title |
| ---: | --- |
| 1 | PostgreSQL arrays |
| 10 | PostgreSQL intersection |

Use `@>` when business logic requires **AND over a tag set**, meaning the document must contain both tags.

### 4.2. @> with a single element

```sql
SELECT doc_id, title
FROM array_ops_lab.documents
WHERE tags @> ARRAY['gin']::TEXT[]
ORDER BY doc_id;
```

Result: docs 9 and 10.

This form is very useful when the `tags` column has a GIN index: the predicate uses an array operator supported by the operator class.

### 4.3. && — at least one common element exists

```sql
SELECT doc_id, title
FROM array_ops_lab.documents
WHERE tags && ARRAY['gin','api']::TEXT[]
ORDER BY doc_id;
```

Result:

| doc_id | Why it matches |
| ---: | --- |
| 2 | Has `api` |
| 9 | Has `gin` |
| 10 | Has `gin` |

`&&` expresses **OR over the requested tag set**: only one common element is needed.

### 4.4. <@ — every row tag belongs to an allowed set

```sql
SELECT doc_id, title, tags
FROM array_ops_lab.documents
WHERE tags <@ ARRAY[
    'sql','postgresql','array','gin','etl'
]::TEXT[]
ORDER BY doc_id;
```

This condition asks whether every element of `tags` is in the allowed set; it does not ask “is at least one tag allowed?”. Among rows without NULL elements, docs 1, 4, 5, and 10 satisfy the condition in a set sense.

### 4.5. Most common confusion: @> vs. &&

```sql
SELECT
    ARRAY['sql','gin']::TEXT[]
        @> ARRAY['sql','api']::TEXT[] AS contains_all,
    ARRAY['sql','gin']::TEXT[]
        && ARRAY['sql','api']::TEXT[] AS overlaps_any;
```

Result:

```text
contains_all = FALSE
overlaps_any = TRUE
```

One shared tag satisfies `&&`, but does not satisfy `@>`.

---

## 5. Be careful with <@ on empty arrays

By set intuition, every element of the empty array belongs to any allowed set. Therefore:

```sql
SELECT
    ARRAY[]::TEXT[] <@ ARRAY['sql']::TEXT[] AS empty_is_subset,
    ARRAY[]::TEXT[] @> ARRAY[]::TEXT[] AS empty_contains_empty,
    ARRAY['sql']::TEXT[] @> ARRAY[]::TEXT[] AS every_array_contains_empty,
    ARRAY[]::TEXT[] && ARRAY['sql']::TEXT[] AS empty_overlaps;
```

For the non-NULL arrays in this example:

| Expression | Result |
| --- | --- |
| `{} <@ {'sql'}` | `TRUE` |
| `{} @> {}` | `TRUE` |
| `{'sql'} @> {}` | `TRUE` |
| `{} && {'sql'}` | `FALSE` |

This can be surprising:

- An empty tag list **satisfies** “every tag is allowed.”
- An empty tag list **does not satisfy** “overlaps with required tags.”
- Any non-NULL array contains the empty array under containment semantics.

If business logic requires “has **at least one** tag and all are valid,” check both:

```sql
WHERE cardinality(tags) > 0
  AND tags <@ ARRAY['sql','postgresql','gin']::TEXT[]
```

Do not use `<@` alone to imply a non-empty array.

---

## 6. Duplicates: containment does not count copies

PostgreSQL array containment **does not treat repetition count as a multiplicity requirement**.

```sql
SELECT
    ARRAY['sql']::TEXT[]
        @> ARRAY['sql','sql']::TEXT[] AS one_contains_two,
    ARRAY['sql','sql']::TEXT[]
        @> ARRAY['sql']::TEXT[] AS two_contains_one,
    ARRAY['sql','sql']::TEXT[]
        = ARRAY['sql']::TEXT[] AS arrays_equal;
```

Result:

| one_contains_two | two_contains_one | arrays_equal |
| --- | --- | --- |
| `TRUE` | `TRUE` | `FALSE` |

Thus:

- `@>` checks element presence, not copy count.
- `=` compares array values where element count and order both matter.
- Do not use `@>` to check “contains at least two occurrences of the `sql` tag.”

### 6.1. Does order matter?

For one-dimensional arrays:

```sql
SELECT
    ARRAY['sql','gin']::TEXT[]
        = ARRAY['gin','sql']::TEXT[] AS same_array,
    ARRAY['sql','gin']::TEXT[]
        @> ARRAY['gin','sql']::TEXT[] AS contains_elements,
    ARRAY['gin','sql']::TEXT[]
        @> ARRAY['sql','gin']::TEXT[] AS reverse_contains;
```

`same_array` is `FALSE` because the order differs; both contains checks are `TRUE` because the element sets match.

**Conclusion:** If your application treats tags as a set, normalize/deduplicate on write or write set-semantic queries. Do not assume an SQL array inherently enforces uniqueness and order-insensitivity.

### 6.2. Counting actual occurrences

```sql
SELECT
    d.doc_id,
    COUNT(*) FILTER (WHERE x.tag = 'sql') AS sql_occurrences
FROM array_ops_lab.documents AS d
CROSS JOIN LATERAL unnest(d.tags) AS x(tag)
WHERE d.doc_id = 4
GROUP BY d.doc_id;
```

Doc 4 has two `sql` elements, so `sql_occurrences=2`.

There is no default constraint forbidding duplicate elements in `TEXT[]`.

---

## 7. ANY: comparing a value against each array element

Common form:

```sql
value operator ANY(array_expression)
```

PostgreSQL evaluates the comparison between `value` and each array element, combining them as **“at least one comparison is true.”**

Example:

```sql
SELECT
    7 = ANY(ARRAY[3,7,9]::INTEGER[]) AS contains_seven,
    7 > ANY(ARRAY[10,2,20]::INTEGER[]) AS greater_than_one,
    'sql' = ANY(ARRAY['java','sql','api']::TEXT[])
        AS string_member;
```

All three evaluate to `TRUE`.

### 7.1. = ANY means membership

```sql
SELECT doc_id, title
FROM array_ops_lab.documents
WHERE 'sql' = ANY(tags)
ORDER BY doc_id;
```

With the lab data, the clearly matching rows are **1, 3, 4, 7, 10**.

`'sql' = ANY(tags)` asks whether the scalar `'sql'` equals **at least one** element of `tags`.

### 7.2. The operator is not always equality

```sql
SELECT
    9 > ANY(ARRAY[10,20,5]::INTEGER[]) AS greater_than_some,
    9 < ANY(ARRAY[10,20,5]::INTEGER[]) AS less_than_some,
    9 <> ANY(ARRAY[9,9,10]::INTEGER[]) AS different_from_some;
```

All three can be `TRUE`:

- `9 > ANY({10,20,5})` is true because 9 > 5.
- `9 < ANY({10,20,5})` is true because 9 < 10.
- `9 <> ANY({9,9,10})` is true because 9 differs from 10, **even though the array contains two 9s**.

This is a critical trap: `x <> ANY(array)` **does not mean** “x is not in the array.” It only asks “is there at least one element different from x?”.

### 7.3. SOME is a synonym for ANY

PostgreSQL supports `SOME` in quantified comparison expressions:

```sql
SELECT
    9 > SOME(ARRAY[2,15]::INTEGER[]) AS some_result,
    9 > ANY(ARRAY[2,15]::INTEGER[]) AS any_result;
```

Both results are equivalent.

### 7.4. Watch the syntax: ARRAY goes on the right

```sql
-- Meaningful: scalar compared against elements of the array.
WHERE 'sql' = ANY(tags)

-- A different question: the entire tags array contains element sql.
WHERE tags @> ARRAY['sql']::TEXT[]
```

The two expressions may select the same rows when the data only holds non-NULL text elements, yet they are **not automatically equivalent across all NULL semantics and index eligibility**.

---

## 8. ALL: comparison must hold for every element

Syntax:

```sql
value operator ALL(array_expression)
```

This means **“every corresponding comparison is true.”**

```sql
SELECT
    10 > ALL(ARRAY[2,3,5]::INTEGER[]) AS greater_than_all,
    10 > ALL(ARRAY[2,30,5]::INTEGER[]) AS not_greater_than_all,
    'sql' = ALL(ARRAY['sql','sql']::TEXT[])
        AS every_element_is_sql;
```

Results in order:

```text
TRUE
FALSE
TRUE
```

### 8.1. <> ALL means no element equals x

A common way to ask “value x is not in the array”:

```sql
SELECT doc_id, title
FROM array_ops_lab.documents
WHERE 'sql' <> ALL(tags)
ORDER BY doc_id;
```

With the lab data:

- Docs 2 and 9 lack `sql` and every element differs from `sql`.
- Doc 5 has an empty array: `<> ALL({})` is `TRUE`.
- Docs 1, 3, 4, 7, and 10 contain `sql`, so `<> ALL` is `FALSE`.
- Doc 6 has a NULL array: result is `NULL`.
- Doc 8 has only a NULL element: result is `NULL`.

Because `WHERE` keeps only conditions returning `TRUE`, docs 6 and 8 are not selected.

### 8.2. 5 > ALL differs from 5 > ANY

```sql
SELECT
    5 > ALL(ARRAY[1,2,3]::INTEGER[]) AS greater_than_every,
    5 > ANY(ARRAY[1,8,9]::INTEGER[]) AS greater_than_one,
    5 > ALL(ARRAY[1,8,9]::INTEGER[]) AS greater_than_every_mixed;
```

Result:

```text
greater_than_every       = TRUE
greater_than_one         = TRUE
greater_than_every_mixed = FALSE
```

### 8.3. ALL is often used for range checks, but it is not a universal shortcut

Example:

```sql
SELECT 80 >= ALL(ARRAY[50,60,70]::INTEGER[]);
```

If score ≥ every threshold, the condition holds. However, if the array contains NULL or is empty, the result differs from expecting “greater than max.” You must understand the next section before turning this into a business rule.

---

## 9. Truth tables: ANY/ALL, empty arrays, and NULL

SQL uses **three-valued logic**: `TRUE`, `FALSE`, and `UNKNOWN` (represented by `NULL`).

With standard **strict** comparison operators like `=`, `<>`, `>`, `<`:

- `ANY` returns TRUE if **at least one** comparison is TRUE.
- If there is no TRUE but at least one NULL result, `ANY` returns NULL.
- If all comparisons are FALSE, `ANY` returns FALSE.
- `ALL` returns FALSE if **at least one** comparison is FALSE.
- If there is no FALSE but at least one NULL result, `ALL` returns NULL.
- If all comparisons are TRUE, `ALL` returns TRUE.

### 9.1. ANY on an empty array

```sql
SELECT
    5 = ANY(ARRAY[]::INTEGER[]) AS any_empty,
    5 > ANY(ARRAY[]::INTEGER[]) AS any_empty_compare;
```

Both return `FALSE`. There is no element for a TRUE comparison to exist.

### 9.2. ALL on an empty array

```sql
SELECT
    5 = ALL(ARRAY[]::INTEGER[]) AS all_empty_equal,
    5 > ALL(ARRAY[]::INTEGER[]) AS all_empty_compare;
```

Both return `TRUE`. No counterexample exists to falsify “every element” — this is **vacuous truth** in quantified logic.

### 9.3. Entire array is NULL

```sql
SELECT
    5 = ANY(NULL::INTEGER[]) AS any_null_array,
    5 = ALL(NULL::INTEGER[]) AS all_null_array;
```

Both return `NULL` because the input array itself is unknown.

### 9.4. NULL elements

```sql
SELECT
    5 = ANY(ARRAY[6,NULL::INTEGER]) AS any_unknown,
    5 = ALL(ARRAY[5,NULL::INTEGER]) AS all_unknown,
    5 = ANY(ARRAY[5,NULL::INTEGER]) AS any_has_match,
    5 = ALL(ARRAY[6,NULL::INTEGER]) AS all_has_mismatch;
```

| Expression | Result | Reason |
| --- | --- | --- |
| `5 = ANY({6,NULL})` | `NULL` | FALSE and UNKNOWN; no TRUE |
| `5 = ALL({5,NULL})` | `NULL` | TRUE and UNKNOWN; no FALSE |
| `5 = ANY({5,NULL})` | `TRUE` | At least one TRUE |
| `5 = ALL({6,NULL})` | `FALSE` | At least one FALSE |

### 9.5. Summary table to memorize

| Array / comparison | `x = ANY(array)` | `x = ALL(array)` |
| --- | --- | --- |
| `ARRAY[]` | FALSE | TRUE |
| `NULL::type[]` | NULL | NULL |
| `ARRAY[x]`, x non-NULL | TRUE | TRUE |
| `ARRAY[y]`, y ≠ x | FALSE | FALSE |
| `ARRAY[x, NULL]` | TRUE | NULL |
| `ARRAY[y, NULL]`, y ≠ x | NULL | FALSE |
| `ARRAY[NULL]` | NULL | NULL |

This table assumes standard strict `=` and a non-NULL `x`. For custom non-strict operators or special comparisons, evaluate the operator's specific semantics.

### 9.6. NULL left operand

```sql
SELECT
    NULL::INTEGER = ANY(ARRAY[1,2]::INTEGER[]) AS unknown_any,
    NULL::INTEGER = ALL(ARRAY[1,2]::INTEGER[]) AS unknown_all,
    NULL::INTEGER = ANY(ARRAY[]::INTEGER[]) AS empty_any,
    NULL::INTEGER = ALL(ARRAY[]::INTEGER[]) AS empty_all;
```

With strict operators, comparing NULL against non-empty elements yields UNKNOWN. On an empty array, however, `ANY=FALSE` and `ALL=TRUE` still hold because zero element comparisons are performed.

---

## 10. Traps with NOT IN, <> ANY, and <> ALL

The three expressions below **do not share the same meaning**:

```sql
x <> ANY(array)
x <> ALL(array)
NOT (x = ANY(array))
```

### 10.1. <> ANY is usually not what you want

```sql
SELECT
    5 <> ANY(ARRAY[5,6]::INTEGER[]) AS not_equal_to_some,
    5 <> ALL(ARRAY[5,6]::INTEGER[]) AS not_equal_to_all;
```

Result:

```text
not_equal_to_some = TRUE
not_equal_to_all  = FALSE
```

A single element 6 suffices to make `5 <> ANY` true, even though the array still contains 5.

If you mean “no element equals 5,” use `5 <> ALL(array)` or negate `5 = ANY(array)` under normal operator semantics, while handling NULL explicitly.

### 10.2. De Morgan's law in three-valued logic

With standard `=` and `<>`:

```sql
NOT (5 = ANY(ARRAY[5,6]::INTEGER[]))
```

corresponds to:

```sql
5 <> ALL(ARRAY[5,6]::INTEGER[])
```

Under strict three-valued SQL logic, both preserve UNKNOWN when an array contains an unresolved NULL.

Neither means “if 5 isn't seen, return TRUE” when a NULL element could hide an unknown value.

### 10.3. NOT IN has the same NULL trap

```sql
SELECT
    5 NOT IN (6,7) AS without_null,
    5 NOT IN (6,NULL::INTEGER) AS with_null;
```

Result:

- `without_null` is TRUE.
- `with_null` is NULL.

Because SQL does not know whether the NULL element equals 5, it cannot return TRUE.

### 10.4. What if “does not have the sql tag” should include NULL arrays?

First clarify the business rule:

- NULL tags mean **tags are unknown**, and should not be treated as “does not have sql” → exclude from results.
- NULL tags mean **no tags stored**, to be treated like an empty array → you can `COALESCE`.
- An array containing a NULL element means an unknown tag → should you accept concluding “does not have sql”?

Example policy “treat a NULL array as empty, while **still preserving UNKNOWN from NULL elements**”:

```sql
WHERE 'sql' <> ALL(
    COALESCE(tags, ARRAY[]::TEXT[])
)
```

If you also want NULL elements treated as “not sql,” state a different policy explicitly; do not silently assume SQL UNKNOWN equals FALSE.

---

## 11. ANY with an array vs. ANY with a subquery

PostgreSQL supports both:

```sql
scalar = ANY(array_expression)
```

and:

```sql
scalar = ANY(subquery)
```

Subquery example:

```sql
SELECT
    d.doc_id, d.title
FROM array_ops_lab.documents AS d
WHERE d.doc_id = ANY (
    SELECT x.doc_id
    FROM array_ops_lab.documents AS x
    WHERE x.title ILIKE '%SQL%'
);
```

Here the right-hand side is **a set of rows produced by SELECT**, not an array column. PostgreSQL applies corresponding semi-join/subquery optimizations.

### 11.1. Membership in a constant list

```sql
SELECT 3 = ANY(ARRAY[1,2,3]::INTEGER[]);
```

is semantically close to:

```sql
SELECT 3 IN (1,2,3);
```

When NULLs appear in the list, both follow three-valued logic.

### 11.2. Membership of a scalar column against an array parameter

Suppose an `orders` table has `status TEXT`:

```sql
SELECT *
FROM orders
WHERE status = ANY($1::TEXT[]);
```

This is a very useful pattern when a request supplies a list of statuses to filter, because the `status` column is **scalar**. With a suitable B-tree index on `status` and sufficient selectivity, PostgreSQL can use an index access path.

### 11.3. Membership inside an array column

```sql
SELECT *
FROM array_ops_lab.documents
WHERE 'sql' = ANY(tags);
```

This is a different pattern: each row holds a `tags` array whose elements must be inspected. Depending on the query, the planner may have to scan rows and evaluate the expression, whereas a GIN array index does not by default optimize this exact expression shape.

**Never use ANY without asking: is the right-hand side a parameter array for a scalar column, an array stored in a column, or a subquery?** They can have completely different access paths.

---

## 12. ANY and ALL with numeric comparisons

With `INTEGER[]`, we test not only membership but also threshold conditions.

### 12.1. At least one score greater than 9

```sql
SELECT doc_id, title, scores
FROM array_ops_lab.documents
WHERE 9 < ANY(scores)
ORDER BY doc_id;
```

Meaning: there exists at least one score element greater than 9.

Note that 9 is on the left:

```text
9 < ANY(scores)
= there exists at least one score such that 9 < score
```

### 12.2. Every score below 50

```sql
SELECT doc_id, title, scores
FROM array_ops_lab.documents
WHERE 50 > ALL(scores)
ORDER BY doc_id;
```

For non-NULL scores, this holds when every score is below 50. However, **empty scores also satisfy it** and **scores containing NULL can evaluate to UNKNOWN**, so if business rules require “at least one score and no NULLs,” add extra predicates.

### 12.3. Accepting only non-empty arrays

```sql
SELECT doc_id, title, scores
FROM array_ops_lab.documents
WHERE cardinality(scores) > 0
  AND 50 > ALL(scores)
ORDER BY doc_id;
```

This excludes empty arrays and NULL arrays. An array containing a NULL element can still make `ALL` evaluate to NULL and be excluded, matching a “do not conclude when data is missing” policy.

### 12.4. Are MIN/MAX equivalent to ANY/ALL?

For a non-empty array with no NULLs:

```sql
x > ALL(array)
```

is equivalent to x being greater than the maximum array element; and:

```sql
x > ANY(array)
```

is equivalent to x being greater than the minimum element.

However:

- `ALL` on an empty array is TRUE.
- `ANY` on an empty array is FALSE.
- `MIN`/`MAX` over `unnest` typically skip NULLs and return NULL when no non-NULL values exist.
- `ANY`/`ALL` propagate UNKNOWN from NULL elements differently.

Therefore, do not mechanically replace ANY/ALL with MIN/MAX when empty or NULL data may exist.

---

## 13. Finding intersections: first define what “intersection” means

Suppose:

```text
A = {sql, postgres, gin, sql}
B = {sql, api, gin, gin}
```

There are at least three distinct questions:

1. **Is there any common element?** → use `A && B`.
2. **Which distinct values appear in both?** → set intersection: `{gin,sql}`.
3. **How many copies of each value appear in the multiset intersection?** → take the smaller count for each element: `{sql,gin}` in this example.

PostgreSQL provides the `&&` operator for question (1), whereas producing a **result array containing the intersecting elements themselves** typically requires `unnest`, `INTERSECT`, or `array_agg`.

### 13.1. Only needing to know if the intersection is non-empty

```sql
SELECT
    ARRAY['sql','postgres','gin']::TEXT[]
    && ARRAY['api','gin']::TEXT[]
        AS has_common_element;
```

Result: TRUE.

### 13.2. How many distinct values are in the intersection?

You must **extract common elements**, deduplicate, and count. Neither `cardinality(A)` nor `cardinality(B)` returns the intersection size.

### 13.3. Does the intersection need a specific order?

A mathematical set is unordered. A PostgreSQL array is ordered. If an API needs results ordered by:

- Alphabetical order.
- Appearance order in A.
- User-defined priority order.
- Element occurrence count.

you must specify that logic explicitly. Do not let JOIN/INTERSECT happenstance dictate product ordering.

---

## 14. Finding distinct intersection with unnest + INTERSECT

`unnest(anyarray)` expands an array into multiple rows.

```sql
SELECT element
FROM unnest(ARRAY['sql','gin','sql']::TEXT[])
    AS x(element);
```

Conceptually the rows are `sql`, `gin`, `sql`. When stable ordering is required, combine with `WITH ORDINALITY` and `ORDER BY` as shown later.

To compute the intersection of two arrays:

```sql
SELECT element
FROM unnest(
    ARRAY['sql','postgresql','gin','sql']::TEXT[]
) AS a(element)

INTERSECT

SELECT element
FROM unnest(
    ARRAY['sql','api','gin','gin']::TEXT[]
) AS b(element)

ORDER BY element;
```

Result:

```text
gin
sql
```

### 14.1. Why does INTERSECT remove duplicates?

By default, `INTERSECT` has **set** semantics: the output contains only distinct values present in both input sets.

Thus even though A contains `sql` twice and B contains `gin` twice, `gin` and `sql` each appear once.

### 14.2. Returning a single array instead of multiple rows

```sql
SELECT COALESCE(
    ARRAY_AGG(element ORDER BY element),
    ARRAY[]::TEXT[]
) AS common_tags
FROM (
    SELECT element
    FROM unnest(
        ARRAY['sql','postgresql','gin','sql']::TEXT[]
    ) AS a(element)

    INTERSECT

    SELECT element
    FROM unnest(
        ARRAY['sql','api','gin','gin']::TEXT[]
    ) AS b(element)
) AS intersection;
```

The result is a `TEXT[]` containing `gin` and `sql` in alphabetical order.

### 14.3. When there is no intersection

If the `INTERSECT` subquery returns 0 rows, `array_agg(...)` returns NULL. We use:

```sql
COALESCE(array_agg(...), ARRAY[]::TEXT[])
```

to return an explicit empty array to the API, if that is the desired contract.

### 14.4. Why use aliases?

When combining `unnest` and subqueries, aliases like `AS a(element)` keep the SQL clear and avoid unintended default column names, especially when multiple arrays are involved.

---

## 15. INTERSECT ALL: intersection preserving multiplicity

If business logic treats lists as **multisets** rather than sets, PostgreSQL supports:

```sql
SELECT element
FROM unnest(
    ARRAY['a','a','b']::TEXT[]
) AS a(element)

INTERSECT ALL

SELECT element
FROM unnest(
    ARRAY['a','a','a','c']::TEXT[]
) AS b(element)

ORDER BY element;
```

The result has **two `a` rows**. Why:

- A has 2 copies of `a`.
- B has 3 copies of `a`.
- The multiset intersection has `min(2,3) = 2` copies of `a`.
- `b` and `c` do not appear in both.

Comparison:

| Expression | Conceptual result |
| --- | --- |
| `INTERSECT` | `{a}` |
| `INTERSECT ALL` | `{a,a}` |
| `ARRAY['a'] @> ARRAY['a','a']` | TRUE |
| `ARRAY['a'] = ARRAY['a','a']` | FALSE |

**Containment is not multiset intersection.** This distinction matters whenever business logic involves quantities or copy counts.

### 15.1. NULL in INTERSECT

SQL set operators like `INTERSECT` treat NULL values as matching each other for deduplication and intersection. For instance, if each input contains a NULL row, the intersection can contain one NULL row.

This **differs** from:

```sql
NULL::TEXT = ANY(ARRAY[NULL::TEXT])
```

because ordinary SQL equality between NULL and NULL returns UNKNOWN.

If your set-operation policy considers “NULL is a valid common element,” `INTERSECT` has different semantics from `= ANY`; choose deliberately.

---

## 16. Finding intersections with = ANY and array_agg

Another approach is unnesting A and keeping elements present in B:

```sql
WITH input AS (
    SELECT
        ARRAY['sql','postgresql','gin','sql']::TEXT[]
            AS left_tags,
        ARRAY['sql','api','gin','gin']::TEXT[]
            AS right_tags
)
SELECT
    COALESCE(
        ARRAY_AGG(DISTINCT elem ORDER BY elem),
        ARRAY[]::TEXT[]
    ) AS common_tags
FROM input
CROSS JOIN LATERAL unnest(left_tags) AS a(elem)
WHERE elem = ANY(right_tags);
```

Result includes `gin` and `sql`.

Explanation:

1. `unnest(left_tags)` produces one row per element of A.
2. `elem = ANY(right_tags)` keeps elements with at least one equal value in B.
3. `DISTINCT` removes duplicates when A repeats an element.
4. `ORDER BY elem` makes the array order deterministic.
5. `COALESCE` turns an empty aggregate from NULL into an empty array per contract.

### 16.1. Advantages

- Readable when you simply need to test membership of A's elements in B.
- Easy to add extra predicates to `WHERE`.
- Can preserve order or duplicates if you adjust the logic and drop DISTINCT.

### 16.2. Limitations

- If both arrays are long, repeated membership scans can consume CPU.
- With NULL elements, `elem = ANY(right_tags)` does not treat NULL as equal to NULL under ordinary `=`.
- If you need multiset intersection by copy count, you cannot simply drop DISTINCT; doing so keeps **all** copies from A whenever B contains at least one copy, rather than taking the minimum count.

### 16.3. When should you use INTERSECT?

Use `INTERSECT` when you want the **set intersection** of two row sources with clean set semantics, especially if NULLs on both sides should match as common values under set operations.

Use `unnest` + `= ANY` when membership filtering is convenient, you need per-element control, and comparison-operator semantics fit your needs.

---

## 17. Intersection between two array columns on the same row

Suppose a table stores both:

```text
requested_tags TEXT[]
available_tags TEXT[]
```

To produce a `common_tags` column for each record, you can use `LATERAL`:

```sql
WITH requests(request_id, requested_tags, available_tags) AS (
    VALUES
      (1,
       ARRAY['sql','gin','api']::TEXT[],
       ARRAY['sql','json','gin']::TEXT[]),
      (2,
       ARRAY['java']::TEXT[],
       ARRAY['sql','api']::TEXT[]),
      (3,
       ARRAY[]::TEXT[],
       ARRAY['sql']::TEXT[])
)
SELECT
    r.request_id,
    COALESCE(c.common_tags, ARRAY[]::TEXT[]) AS common_tags
FROM requests AS r
LEFT JOIN LATERAL (
    SELECT ARRAY_AGG(DISTINCT x.tag ORDER BY x.tag)
        AS common_tags
    FROM unnest(r.requested_tags) AS x(tag)
    WHERE x.tag = ANY(r.available_tags)
) AS c ON TRUE
ORDER BY r.request_id;
```

Expected output:

| request_id | common_tags |
| ---: | --- |
| 1 | `{gin,sql}` |
| 2 | `{}` |
| 3 | `{}` |

### 17.1. Why use LATERAL?

The right-hand subquery references columns of the current `requests` row:

```text
r.requested_tags
r.available_tags
```

`LATERAL` allows evaluating an expression correlated to outer rows. This syntax is useful when processing each pair of arrays individually.

### 17.2. Do not assume a built-in universal intersection function exists

PostgreSQL core **does not have a universal built-in function named `array_intersection(anyarray, anyarray)`** covering all types and duplicate/NULL policies. Some extensions or projects define custom functions; do not write `array_intersection` assuming PostgreSQL always recognizes it.

Express intersections using `INTERSECT`, `unnest`/`array_agg`, or define a custom SQL function if your application frequently needs one fixed contract.

---

## 18. Finding intersections while preserving original array order

An API may require **intersecting elements ordered by first appearance in A**, rather than sorted alphabetically.

Example:

```text
A = [gin, sql, api, gin, postgres]
B = [postgres, sql, gin]

Distinct intersection in A's order:
[gin, sql, postgres]
```

Use `WITH ORDINALITY`:

```sql
WITH inputs AS (
    SELECT
        ARRAY['gin','sql','api','gin','postgres']::TEXT[]
            AS left_tags,
        ARRAY['postgres','sql','gin']::TEXT[]
            AS right_tags
),
first_positions AS (
    SELECT
        x.tag,
        MIN(x.ord) AS first_ord
    FROM inputs AS i
    CROSS JOIN LATERAL unnest(i.left_tags)
        WITH ORDINALITY AS x(tag, ord)
    WHERE x.tag = ANY(i.right_tags)
    GROUP BY x.tag
)
SELECT COALESCE(
    ARRAY_AGG(tag ORDER BY first_ord),
    ARRAY[]::TEXT[]
) AS ordered_intersection
FROM first_positions;
```

Result:

```text
{gin,sql,postgres}
```

### 18.1. Why MIN(ord)?

A contains `gin` twice. We want a single copy in the distinct intersection, placed at its **first occurrence position**. `MIN(ord)` identifies that position.

### 18.2. Do not trust incidental SELECT ordering

Even though `unnest` often emits elements in storage order in simple cases, **the output order of a relational query is not guaranteed without an explicit ORDER BY**. Once JOINs, GROUP BY, or aggregates are combined, ordering can never be assumed.

Inside `array_agg`, put `ORDER BY` **within the aggregate** whenever element order in the resulting array matters.

---

## 19. Deliberate NULL-safe intersections

Some applications treat NULL as a distinct value in an intersection; others exclude NULL completely.

### 19.1. Policy A: drop all NULL elements

```sql
WITH a(tag) AS (
    SELECT * FROM unnest(
        ARRAY['sql', NULL::TEXT, 'gin']::TEXT[]
    )
),
b(tag) AS (
    SELECT * FROM unnest(
        ARRAY['gin', NULL::TEXT, 'api']::TEXT[]
    )
)
SELECT tag
FROM a
WHERE tag IS NOT NULL

INTERSECT

SELECT tag
FROM b
WHERE tag IS NOT NULL

ORDER BY tag;
```

Only `gin` remains.

### 19.2. Policy B: NULL is a valid common element

```sql
SELECT tag
FROM unnest(
    ARRAY['sql',NULL::TEXT,'gin']::TEXT[]
) AS a(tag)

INTERSECT

SELECT tag
FROM unnest(
    ARRAY['gin',NULL::TEXT,'api']::TEXT[]
) AS b(tag);
```

The output contains `gin` **and one NULL row** under set-operation semantics.

### 19.3. NULL-safe comparison in JOIN

If you need a JOIN condition treating two NULLs as matching, PostgreSQL provides:

```sql
a.tag IS NOT DISTINCT FROM b.tag
```

Example:

```sql
SELECT a.tag
FROM unnest(ARRAY['sql',NULL::TEXT]::TEXT[]) AS a(tag)
JOIN unnest(ARRAY['api',NULL::TEXT]::TEXT[]) AS b(tag)
  ON a.tag IS NOT DISTINCT FROM b.tag;
```

`IS NOT DISTINCT FROM` differs from `=` when both operands are NULL. Note that if either side has duplicates, the JOIN multiplies matching pairs; apply DISTINCT/GROUP BY per contract.

### 19.4. Do not try writing IS NOT DISTINCT FROM ANY

`IS NOT DISTINCT FROM` is a SQL NULL-safe comparison construct, **not an arbitrary binary operator you can plug directly into `operator ANY(...)`**. When you need NULL-safe membership, use a JOIN or `EXISTS` subquery with `IS NOT DISTINCT FROM` or an appropriate structure rather than assuming `IS NOT DISTINCT FROM ANY` exists.

---

## 20. ANY/ALL vs. counting elements with aggregates

You can check “at least two values >= 10” by unnesting:

```sql
SELECT
    d.doc_id,
    COUNT(*) FILTER (WHERE s.score >= 10) AS count_ge_10
FROM array_ops_lab.documents AS d
CROSS JOIN LATERAL unnest(d.scores) AS s(score)
GROUP BY d.doc_id
HAVING COUNT(*) FILTER (WHERE s.score >= 10) >= 2
ORDER BY d.doc_id;
```

In the lab, doc 1 has three scores >= 10.

### 20.1. ANY cannot answer cardinality questions

```sql
10 <= ANY(scores)
```

only tells whether **at least one** score meets the threshold, not whether “two or more” do.

### 20.2. ALL does not mean 100% pass rate on non-empty sets

If an array is empty, `x <= ALL(array)` is TRUE by quantified logic, whereas “100% of scores in the list pass” may be invalid when the list has no scores.

Add `cardinality(scores) > 0` if business policy requires a non-empty set of elements.

### 20.3. Arrays with NULLs and aggregates

Aggregates like `COUNT(score)` and `AVG(score)` ignore NULLs; `COUNT(*)` counts rows holding NULL as well.

Example:

```sql
SELECT
    COUNT(*) AS all_elements,
    COUNT(score) AS known_elements,
    AVG(score) AS average_known_score
FROM unnest(
    ARRAY[10,NULL::INTEGER,20]::INTEGER[]
) AS s(score);
```

Row count is 3, known scores count is 2, and the average of the two known scores is 15.

This is **not automatically equivalent** to the UNKNOWN semantics of `ANY`/`ALL`; never swap mechanisms without defining missing-value handling.

---

## 21. Array inspection functions

### 21.1. cardinality — total number of elements

```sql
SELECT
    cardinality(ARRAY[1,2,3]::INTEGER[]) AS three,
    cardinality(ARRAY[]::INTEGER[]) AS zero,
    cardinality(NULL::INTEGER[]) AS unknown;
```

Result:

```text
three   = 3
zero    = 0
unknown = NULL
```

`cardinality` supports multidimensional arrays and returns the total element count across all dimensions.

### 21.2. array_length — length of a single dimension

```sql
SELECT
    array_length(ARRAY[1,2,3]::INTEGER[], 1) AS first_dim,
    array_length(ARRAY[]::INTEGER[], 1) AS empty_dim,
    array_length(NULL::INTEGER[], 1) AS null_dim;
```

Result:

- `first_dim=3`.
- `empty_dim=NULL`, not 0.
- `null_dim=NULL`.

Therefore:

```sql
WHERE array_length(tags, 1) = 0
```

**is not a reliable way to detect empty arrays**. Use `cardinality(tags)=0` or compare against `ARRAY[]::TEXT[]` per contract.

### 21.3. array_dims, array_lower, and array_upper

```sql
SELECT
    array_dims(ARRAY[10,20,30]::INTEGER[]) AS dimensions,
    array_lower(ARRAY[10,20,30]::INTEGER[], 1) AS lower_bound,
    array_upper(ARRAY[10,20,30]::INTEGER[], 1) AS upper_bound;
```

These functions expose dimensionality and original index bounds, especially when working with arrays that do not start at index 1.

### 21.4. NULL vs. empty arrays in reports

```sql
SELECT
    COUNT(*) AS documents,
    COUNT(*) FILTER (WHERE tags IS NULL) AS null_arrays,
    COUNT(*) FILTER (WHERE cardinality(tags) = 0)
        AS empty_arrays,
    COUNT(*) FILTER (WHERE cardinality(tags) > 0)
        AS nonempty_arrays
FROM array_ops_lab.documents;
```

Each metric carries a different meaning. Never automatically equate missing data (NULL) with an empty collection.

---

## 22. Finding element positions: array_position and array_positions

### 22.1. array_position

```sql
SELECT
    array_position(
        ARRAY['sql','gin','sql']::TEXT[], 'sql'
    ) AS first_position,
    array_position(
        ARRAY['sql','gin','sql']::TEXT[], 'java'
    ) AS absent_position;
```

Result:

```text
first_position  = 1
absent_position = NULL
```

The function returns the first occurrence index in a one-dimensional array; it does not return TRUE/FALSE like ANY.

### 22.2. array_positions

```sql
SELECT array_positions(
    ARRAY['sql','gin','sql']::TEXT[],
    'sql'
) AS all_positions;
```

The result is an array of positions, such as `{1,3}`.

### 22.3. Finding NULL elements with array_position

One advantage: `array_position`/`array_positions` use comparison semantics aligned with `IS NOT DISTINCT FROM`, allowing them to locate **NULL element positions**:

```sql
SELECT
    array_position(
        ARRAY['sql',NULL::TEXT,'gin']::TEXT[],
        NULL::TEXT
    ) AS null_position;
```

Result is 2.

This differs from:

```sql
NULL::TEXT = ANY(
    ARRAY['sql',NULL::TEXT,'gin']::TEXT[]
)
```

which returns UNKNOWN under strict equality.

### 22.4. When to use array_position?

- You need to know the **position**.
- You need to locate NULL elements under matching semantics.
- You need to modify/replace an element at a specific position.

When you only need membership and a GIN index exists on the array column, `tags @> ARRAY['x']` is usually the better expression for an index access path.

---

## 23. unnest and WITH ORDINALITY

`unnest` turns an array into rows so you can apply familiar relational SQL tools: JOIN, GROUP BY, DISTINCT, ORDER BY, INTERSECT.

### 23.1. Unnesting one array

```sql
SELECT element
FROM unnest(
    ARRAY['sql','gin','array']::TEXT[]
) AS t(element);
```

### 23.2. Preserving position

```sql
SELECT element, ord
FROM unnest(
    ARRAY['sql','gin','array']::TEXT[]
) WITH ORDINALITY AS t(element, ord)
ORDER BY ord;
```

Ordered output:

| ord | element |
| ---: | --- |
| 1 | sql |
| 2 | gin |
| 3 | array |

### 23.3. Unnesting each row's array

```sql
SELECT
    d.doc_id,
    t.ord,
    t.tag
FROM array_ops_lab.documents AS d
CROSS JOIN LATERAL unnest(d.tags)
    WITH ORDINALITY AS t(tag, ord)
WHERE d.doc_id IN (1,4)
ORDER BY d.doc_id, t.ord;
```

Doc 4 clearly shows two positions holding the same `sql` tag.

### 23.4. Empty and NULL arrays after unnest

`unnest(ARRAY[]::TEXT[])` and `unnest(NULL::TEXT[])` produce zero element rows. With `CROSS JOIN LATERAL`, parent rows with no elements are dropped from the result.

If you want to **keep all parent rows** even when the array is empty/NULL, use `LEFT JOIN LATERAL ... ON TRUE`, and beware that **one null-extended row** will appear for each elementless parent row:

```sql
SELECT
    d.doc_id,
    t.tag,
    t.ord
FROM array_ops_lab.documents AS d
LEFT JOIN LATERAL unnest(d.tags)
    WITH ORDINALITY AS t(tag, ord) ON TRUE
WHERE d.doc_id IN (5,6)
ORDER BY d.doc_id;
```

Do not use `COUNT(*)` after LEFT JOIN LATERAL to infer array length: for an empty/NULL array row, `COUNT(*)` can still be 1. Use `COUNT(t.ord)` or `cardinality(tags)` depending on intent.

---

## 24. array_agg and ARRAY(SELECT ...)

### 24.1. Aggregating rows back into an array

```sql
SELECT
    array_agg(tag ORDER BY tag) AS tags_sorted
FROM (
    VALUES ('sql'::TEXT),('gin'),('postgresql')
) AS x(tag);
```

The result is a text array sorted alphabetically.

### 24.2. Deduplicating

```sql
SELECT
    array_agg(DISTINCT tag ORDER BY tag) AS unique_tags
FROM (
    VALUES ('sql'::TEXT),('gin'),('sql'),('array')
) AS x(tag);
```

The result has a single `sql`, no duplicates.

### 24.3. array_agg can include NULLs in the array

If the input contains NULL, `array_agg` can include NULL elements. To exclude them:

```sql
SELECT
    array_agg(DISTINCT tag ORDER BY tag)
        FILTER (WHERE tag IS NOT NULL) AS known_tags
FROM (
    VALUES ('sql'::TEXT),(NULL::TEXT),('gin')
) AS x(tag);
```

### 24.4. What if there are zero rows?

`array_agg` over 0 input rows returns NULL. If the API expects an empty array, use `COALESCE` with a properly typed empty array:

```sql
SELECT COALESCE(
    array_agg(tag ORDER BY tag),
    ARRAY[]::TEXT[]
)
FROM (
    SELECT 'sql'::TEXT AS tag WHERE FALSE
) AS x;
```

### 24.5. Useful behavior of ARRAY(SELECT ...)

PostgreSQL also allows:

```sql
SELECT ARRAY(
    SELECT tag
    FROM (
        VALUES ('sql'::TEXT),('gin'),('api')
    ) AS x(tag)
    ORDER BY tag
) AS tags_array;
```

When the subquery returns zero rows, this array constructor produces an empty array, unlike `array_agg` which returns NULL on empty input. Choose whichever expression matches your semantics and data.

---

## 25. Building a distinct tag list across the entire table

Suppose a report needs “all tags currently in use”:

```sql
SELECT COALESCE(
    array_agg(DISTINCT t.tag ORDER BY t.tag),
    ARRAY[]::TEXT[]
) AS all_known_tags
FROM array_ops_lab.documents AS d
CROSS JOIN LATERAL unnest(d.tags) AS t(tag)
WHERE t.tag IS NOT NULL;
```

Flow:

```text
documents.tags
    |
    v
unnest per row
    |
    v
filter out NULL elements
    |
    v
DISTINCT and ORDER BY
    |
    v
array_agg
```

### 25.1. Document count per tag

```sql
SELECT
    t.tag,
    COUNT(DISTINCT d.doc_id) AS document_count
FROM array_ops_lab.documents AS d
CROSS JOIN LATERAL unnest(d.tags) AS t(tag)
WHERE t.tag IS NOT NULL
GROUP BY t.tag
ORDER BY document_count DESC, t.tag;
```

Why `COUNT(DISTINCT d.doc_id)`?

Doc 4 contains two copies of `sql`. Using `COUNT(*)` right after unnest would count doc 4 twice for the same tag, whereas the metric here is **number of documents having the tag**, not tag occurrence count.

### 25.2. Want to count total occurrences instead?

Replace with `COUNT(*)` to get element frequency. That is a different metric; do not use DISTINCT when business logic wants to count duplicates.

---

## 26. Multidimensional arrays and unnesting

PostgreSQL supports multidimensional arrays:

```sql
SELECT
    ARRAY[[1,2],[3,4]]::INTEGER[] AS grid,
    array_length(ARRAY[[1,2],[3,4]]::INTEGER[], 1)
        AS first_dim_length,
    array_length(ARRAY[[1,2],[3,4]]::INTEGER[], 2)
        AS second_dim_length,
    cardinality(ARRAY[[1,2],[3,4]]::INTEGER[])
        AS total_elements;
```

Numeric results:

```text
first_dim_length  = 2
second_dim_length = 2
total_elements    = 4
```

`unnest` on a multidimensional array flattens elements into rows in storage order when called:

```sql
SELECT element
FROM unnest(
    ARRAY[[1,2],[3,4]]::INTEGER[]
) AS x(element);
```

### 26.1. Do not conflate shape with set semantics

Multidimensional arrays carry shape and positional information. An `array_agg` or `unnest` can discard dimensionality if you do not record coordinates/shape to reconstruct it.

If the domain object is a “2×2 grid,” do not casually treat it as an unordered set containing 1,2,3,4.

### 26.2. Some functions only support 1D arrays

Functions such as `array_position`/`array_positions` are restricted to one-dimensional arrays. When working with multidimensional matrices, check each function's contract rather than applying 1D examples verbatim.

### 26.3. Multidimensional arrays are not a default replacement for relational tables

If each cell needs its own ID, timestamp, FK, and independent updates, a relational table with coordinate/row/column attributes is usually clearer in OLTP design. Multidimensional arrays fit best when the data is truly a structured value processed together.

---

## 27. GIN indexes for array operators

A major advantage of PostgreSQL is being able to create a GIN index on array columns:

```sql
CREATE INDEX idx_documents_tags_gin
ON array_ops_lab.documents
USING GIN (tags);

ANALYZE array_ops_lab.documents;
```

GIN stands for **Generalized Inverted Index**: conceptually, it maps each element/tag to the rows containing that tag.

```text
"sql"        -> doc 1,3,4,7,10
"postgresql" -> doc 1,9,10
"gin"        -> doc 9,10
"api"        -> doc 2
```

This is a conceptual diagram, not the actual physical byte layout of GIN.

### 27.1. Operators supported by array_ops

The default GIN operator class for suitable array types typically supports operators such as:

- `@>` — contains.
- `<@` — contained by.
- `&&` — overlap.
- `=` — equality.

Example:

```sql
SELECT doc_id
FROM array_ops_lab.documents
WHERE tags @> ARRAY['sql','postgresql']::TEXT[];
```

The planner can use GIN to locate rows containing both elements.

### 27.2. Why might = ANY(tags) fail to use GIN?

```sql
WHERE 'sql' = ANY(tags)
```

is a scalar quantified expression. GIN `array_ops` is built to accelerate **array operators** in indexable shapes. Do not expect the planner to automatically rewrite every `= ANY(array_column)` into the equivalent GIN condition.

When searching for a single tag with GIN, writing:

```sql
WHERE tags @> ARRAY['sql']::TEXT[]
```

is much easier to verify and optimize.

**Semantics warning:** On arrays containing NULL, `'x' = ANY(tags)` can return UNKNOWN when no element matches, whereas `tags @> ARRAY['x']` can return FALSE in the same situation. In a `WHERE` clause selecting only TRUE, both can return the same rows in many cases; however, they are **not equivalent boolean expressions under three-valued SQL logic**, so never swap them inside `NOT` or `CASE` without testing.

### 27.3. Using overlap to filter with OR

```sql
SELECT doc_id, title
FROM array_ops_lab.documents
WHERE tags && ARRAY['gin','api']::TEXT[]
ORDER BY doc_id;
```

This clearly expresses “at least one tag from the list” and has a GIN-supported operator.

### 27.4. Which queries are not automatically index-accelerated?

Do not assume a GIN array index speeds up arbitrary expressions like:

```sql
WHERE array_to_string(tags, ',') ILIKE '%sql%'
WHERE cardinality(tags) > 5
WHERE tags[2] = 'sql'
WHERE 'sql' = ANY(tags)
```

These predicates inspect other properties: concatenated strings, length, element at a position, or quantified comparison. Depending on workload, you may need an expression index, a different storage model, or a scan.

### 27.5. A small table may still choose Seq Scan

The lab has only ten rows, so:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT doc_id, title
FROM array_ops_lab.documents
WHERE tags @> ARRAY['sql']::TEXT[];
```

may show `Seq Scan` even though the GIN index exists. On ten rows, scanning the table is cheaper than traversing GIN and the heap. Do not view that as a broken index.

---

## 28. Reading a GIN execution plan

A plan might look like:

```text
Bitmap Heap Scan on documents
  Recheck Cond: (tags @> '{sql}'::text[])
  -> Bitmap Index Scan on idx_documents_tags_gin
       Index Cond: (tags @> '{sql}'::text[])
```

This is an illustrative example. Node names, costs, and row counts vary by version and statistics.

### 28.1. Bitmap Index Scan

GIN locates candidate rows based on array elements. PostgreSQL builds a bitmap of heap locations to visit.

### 28.2. Bitmap Heap Scan

The executor uses the bitmap to fetch heap pages efficiently. Some predicates may need rechecking:

```text
Recheck Cond: ...
```

Recheck does not mean the index is wrong. With lossy bitmaps or certain operator classes, heap verification ensures exact results.

### 28.3. Testing an index path in the lab

```sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT doc_id
FROM array_ops_lab.documents
WHERE tags && ARRAY['gin','api']::TEXT[];

ROLLBACK;
```

`SET LOCAL` applies only within this transaction. It helps **observe an index plan**, not prove that the index plan is actually faster.

Never enable `enable_seqscan=off` as a production setting merely to force GIN usage.

### 28.4. Reading EXPLAIN output

Check:

- `Planning Time` and `Execution Time`.
- `actual rows` vs. estimated `rows`.
- `Buffers: shared hit/read`.
- `Rows Removed by Filter` and `Rows Removed by Index Recheck`.
- `Seq Scan`, `Bitmap Index Scan`, `Bitmap Heap Scan` nodes.
- Whether an extra Sort is required by `ORDER BY`.

GIN excels at membership filtering, yet **does not sort documents by timestamp**. A query with `ORDER BY created_at DESC LIMIT 20` may still need a Sort or a separate B-tree index.

---

## 29. Performance: when does GIN pay off?

The benefit is typically clearest when:

- The table is large.
- Each row holds multiple tags.
- Queries filter for relatively rare/selective tags.
- Queries commonly use `@>` and `&&`.
- Read performance outweighs the cost of constant tag updates.

### 29.1. Overly common tags

If 95% of documents carry `sql`, the query:

```sql
WHERE tags @> ARRAY['sql']::TEXT[]
```

still matches nearly the whole table. GIN may not save I/O; a Seq Scan or parallel scan can be the sensible choice.

### 29.2. Every UPDATE still carries overhead

PostgreSQL MVCC generally writes a new tuple version on UPDATE. Updating a `tags` value means:

- The GIN index may need to update entries for indexed elements.
- WAL is generated for logged tables.
- VACUUM and index cleanup costs accrue.
- Updating a large array value is not a free in-place element swap.

If each item updates tags thousands of times per second, measure write amplification before choosing GIN.

### 29.3. GIN pending list

GIN commonly uses `fastupdate` and a pending list by default. This defers some index work to batch cleanup later, improving write throughput in some workloads while adding read/maintenance overhead when the pending list grows large.

Do not interpret `fastupdate` as “eliminating index write cost.” VACUUM/autovacuum and index maintenance remain critical.

### 29.4. Indexing a scalar vs. indexing an array

A predicate:

```sql
WHERE category = ANY($1::TEXT[])
```

on scalar `category TEXT` can use a **B-tree** on `category`.

A predicate:

```sql
WHERE tags && $1::TEXT[]
```

on `tags TEXT[]` can use **GIN** on `tags`.

Query shape and which side holds the indexed column matter far more than spotting the keywords `ANY` or `ARRAY`.

---

## 30. ARRAY in a relational model: when to use a child table?

A tags array is convenient:

```sql
CREATE TABLE documents (
    doc_id BIGINT PRIMARY KEY,
    tags TEXT[]
);
```

Now consider requirements such as:

- Every tag must reference a `tags_catalog` table via a foreign key.
- A tag cannot appear twice on the same document.
- Each tag assignment needs its own timestamp, `user_id`, and metadata.
- Queries need “top tags by revenue” or multi-table joins on tags.
- Individual tags are added/updated very frequently and independently.
- A single document can hold tens of thousands of elements.

In those cases, a relational junction table preserves invariants much more easily:

```sql
CREATE TABLE documents (
    doc_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL
);

CREATE TABLE tags_catalog (
    tag_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE document_tags (
    doc_id BIGINT NOT NULL REFERENCES documents(doc_id),
    tag_id BIGINT NOT NULL REFERENCES tags_catalog(tag_id),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (doc_id, tag_id)
);
```

### 30.1. Comparing the two models

| Requirement | Array in one column | Junction table |
| --- | --- | --- |
| Read all tags for a document | Convenient | JOIN/aggregate |
| Filter by tag | GIN `@>`/`&&` | B-tree/FK/index on `tag_id` |
| Foreign key per tag | Not directly per element | Natural |
| Unique per element | Needs normalization/extra logic | Composite PK |
| Metadata on doc–tag relationship | Awkward | Natural |
| Update one association | Typically rewrites array value | INSERT/DELETE one row |
| Query by tag + other attributes | Can get complex | Easy joins/aggregates |
| Small, rarely changing sets | Very suitable | JOIN overhead |

There is no rigid rule claiming “arrays are non-relational and always wrong.” PostgreSQL supports arrays as first-class types; the right design matches **invariants and workload**.

### 30.2. Never replace foreign keys with an ID array

A `related_ids BIGINT[]` column does not enforce referential integrity per ID against the target table. When real foreign keys are required, a junction table with FKs is much safer than storing IDs in an array.

### 30.3. JSONB does not solve the FK problem either

Replacing an SQL array with a JSONB array still does not provide per-element foreign keys. Choose JSONB when data structure and queries demand JSON flexibility, not to bypass relational constraints.

---

## 31. Updating array elements in PostgreSQL

PostgreSQL provides several functions and operators to transform arrays:

### 31.1. array_append

```sql
SELECT array_append(
    ARRAY['sql','api']::TEXT[],
    'gin'
) AS appended;
```

Result: `{sql,api,gin}`.

### 31.2. array_prepend

```sql
SELECT array_prepend(
    'gin',
    ARRAY['sql','api']::TEXT[]
) AS prepended;
```

Result: `{gin,sql,api}`.

### 31.3. array_cat or ||

```sql
SELECT
    array_cat(
        ARRAY['sql']::TEXT[],
        ARRAY['gin','api']::TEXT[]
    ) AS concatenated,
    ARRAY['sql']::TEXT[] || ARRAY['gin','api']::TEXT[]
        AS with_operator;
```

Both expressions concatenate arrays with corresponding semantics.

### 31.4. array_remove

```sql
SELECT array_remove(
    ARRAY['sql','gin','sql']::TEXT[],
    'sql'
) AS removed;
```

Result: `{gin}` — **all** elements equal to `sql` are removed, not just the first occurrence.

`array_remove` handles NULL using `IS NOT DISTINCT FROM` semantics when you need to strip NULL elements:

```sql
SELECT array_remove(
    ARRAY['sql',NULL::TEXT,'gin']::TEXT[],
    NULL::TEXT
);
```

### 31.5. array_replace

```sql
SELECT array_replace(
    ARRAY['sql','gin','sql']::TEXT[],
    'sql',
    'postgresql'
) AS replaced;
```

Both `sql` positions are replaced.

### 31.6. Do not confuse append with set-add

`array_append(tags,'sql')` **can introduce duplicates** if the array already contains `sql`. If an API treats tags as a set, guard membership or normalize/deduplicate:

```sql
UPDATE array_ops_lab.documents
SET tags = array_append(
    COALESCE(tags, ARRAY[]::TEXT[]),
    'new-tag'
)
WHERE doc_id = 5
  AND NOT COALESCE(
      tags @> ARRAY['new-tag']::TEXT[],
      FALSE
  )
RETURNING doc_id, tags;
```

This is a conditional row update. On the original lab data, doc 5 has an empty array so the new tag is appended once.

**Warning:** This modifies lab data; if you need the original results from earlier examples, reset the data or roll back inside a transaction.

---

## 32. Concurrency when updating arrays: preventing lost updates

A classic application bug pattern:

```text
A reads tags = [sql]
B reads tags = [sql]

A adds gin on the client:
    UPDATE tags = [sql,gin]
    COMMIT

B adds api on the client using the stale read:
    UPDATE tags = [sql,api]
    COMMIT

Result: [sql,api]
A's gin change was overwritten.
```

This is an **application-level lost update**, not a flaw in GIN or `ANY`.

### 32.1. Use an atomic UPDATE against the current value

Instead of having the client compute the whole new array from a stale snapshot:

```sql
UPDATE array_ops_lab.documents
SET tags = array_append(
    COALESCE(tags, ARRAY[]::TEXT[]),
    'gin'
)
WHERE doc_id = 1;
```

Computing `array_append(tags,...)` inside the database coordinates concurrent row updates under PostgreSQL row-locking rules.

However, to prevent duplicate tags, add a non-containment predicate in the same UPDATE:

```sql
UPDATE array_ops_lab.documents
SET tags = array_append(
    COALESCE(tags, ARRAY[]::TEXT[]),
    'gin'
)
WHERE doc_id = 1
  AND NOT COALESCE(
      tags @> ARRAY['gin']::TEXT[],
      FALSE
  )
RETURNING tags;
```

### 32.2. When a user replaces the entire tag set

If an API allows replacing the whole tag list loaded earlier, consider an **optimistic version** check to catch stale forms:

```sql
-- Example schema assuming row_version exists.
UPDATE application_documents
SET tags = :new_tags,
    row_version = row_version + 1
WHERE doc_id = :doc_id
  AND row_version = :expected_version
RETURNING row_version;
```

The application reports success only when exactly one row is updated and the transaction commits. Never silently retry with the newly fetched version to overwrite with stale form payload unless business rules permit it.

### 32.3. When does a junction table win?

If multiple workers concurrently add/remove independent tags, a `document_tags` table with `PRIMARY KEY(doc_id,tag_id)` avoids rewriting the entire array and expresses uniqueness and concurrency cleanly through relational constraints.

---

## 33. Passing array parameters via Java/JDBC

When a Java application receives a list of filter tags, **never** concatenate elements into an SQL string like:

```java
// Wrong approach: interpolating user input directly into SQL.
String sql = "SELECT * FROM documents WHERE tags && '{"
        + userInput + "}'";
```

This invites escaping bugs and SQL injection risks.

### 33.1. Use PreparedStatement and SQL Array

PostgreSQL JDBC example:

```java
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

String sql = """
    SELECT doc_id, title
    FROM array_ops_lab.documents
    WHERE tags && ?::text[]
    ORDER BY doc_id
    """;

String[] requiredAnyTags = {"gin", "api"};

Array sqlArray = connection.createArrayOf(
    "text",
    requiredAnyTags
);

try {
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setArray(1, sqlArray);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                int docId = rs.getInt("doc_id");
                String title = rs.getString("title");
                // Process results.
            }
        }
    }
} finally {
    sqlArray.free();
}
```

### 33.2. Query requiring all specified tags

Simply swap the operator:

```sql
WHERE tags @> ?::TEXT[]
```

With required tags `sql` and `postgresql`, this evaluates an AND across both tags.

### 33.3. Query requiring at least one tag

```sql
WHERE tags && ?::TEXT[]
```

With input `gin` and `api`, this evaluates an OR across the tags.

### 33.4. What if the request list is empty?

Define the endpoint contract explicitly:

- “Has **at least one** from an empty set” → overlap with an empty array is FALSE for non-NULL arrays, so zero rows match.
- “Contains **all** tags of an empty set” → every non-NULL array satisfies containment.
- “An empty filter list means **do not apply the filter**” → omit the predicate in API query building rather than running an operator blindly expecting “all rows.”

Note especially that binding `NULL::TEXT[]` to the placeholder is not the same as passing an empty array. They carry different SQL meanings.

### 33.5. BIGINT and type binding

Bind the proper element type: use `uuid` for `UUID[]`, `int4` or matching JDBC type for `INTEGER[]`. Do not send every array as plain text relying on loose implicit casts; ambiguous casting can cause runtime errors, prevent index usage, or introduce unexpected semantics.

---

## 34. Distinguishing SQL arrays from JSONB arrays

In PostgreSQL:

```sql
SELECT
    ARRAY['sql','gin']::TEXT[] AS sql_array,
    '["sql","gin"]'::JSONB AS jsonb_array;
```

The two values may look similar in a UI, yet they have **different types and different operator sets**.

### 34.1. SQL arrays

```sql
SELECT
    ARRAY['sql','gin']::TEXT[]
        && ARRAY['api','gin']::TEXT[] AS overlap,
    ARRAY['sql','gin']::TEXT[]
        @> ARRAY['sql']::TEXT[] AS contains;
```

### 34.2. JSONB

```sql
SELECT
    '["sql","gin"]'::JSONB
        @> '["sql"]'::JSONB AS jsonb_contains;
```

JSONB uses JSON containment semantics and provides existence/JSONPath operators; it does not automatically support `&&` with SQL-array overlap semantics.

### 34.3. When should you choose JSONB?

- Flexible nested object/array/key-value schemas.
- Deep JSON structure queries or JSONPath filtering.
- Elements are complex objects rather than uniform scalars.

Choose an SQL array when the value set is clearly typed/homogeneous and PostgreSQL array operations match your queries. Choose a child table when relational FKs, metadata, or uniqueness are needed. Never pick a storage type merely because JSON serializes easily over an API.

---

## 35. Real-world intersections: tags vs. permissions

Suppose a feature finds documents whose tags intersect a user's interests:

```sql
SELECT
    doc_id,
    title,
    tags
FROM array_ops_lab.documents
WHERE tags && ARRAY['sql','api']::TEXT[]
ORDER BY doc_id;
```

This is an **interest filter**, not an access-control check.

### 35.1. Never rely on user-editable array tags for authorization

If users can edit `tags`, someone could add tags to appear in restricted search results. Authorization must be enforced through proper authentication/authorization or RLS architecture, never solely via a label array.

### 35.2. Computing intersection and match count for ranking

A search feature might rank documents by **count of distinct shared tags**:

```sql
WITH query_tags AS (
    SELECT ARRAY['sql','postgresql','gin']::TEXT[]
        AS requested
),
matches AS (
    SELECT
        d.doc_id,
        d.title,
        COUNT(DISTINCT t.tag) AS matched_tag_count
    FROM array_ops_lab.documents AS d
    CROSS JOIN query_tags AS q
    CROSS JOIN LATERAL unnest(d.tags) AS t(tag)
    WHERE t.tag = ANY(q.requested)
    GROUP BY d.doc_id, d.title
)
SELECT *
FROM matches
ORDER BY matched_tag_count DESC, doc_id ASC;
```

Meaning:

- `COUNT(DISTINCT t.tag)` counts distinct shared tags.
- A doc with duplicate tags does not earn extra score simply by storing `sql` twice.
- Documents with zero matching tags are omitted because the inner/CROSS LATERAL produces no rows passing WHERE.

### 35.3. Pre-filtering with GIN, scoring via aggregation

At larger scale, a combined query pattern:

```sql
WITH query_tags AS (
    SELECT ARRAY['sql','postgresql','gin']::TEXT[]
        AS requested
)
SELECT
    d.doc_id,
    d.title,
    (
        SELECT COUNT(DISTINCT t.tag)
        FROM unnest(d.tags) AS t(tag)
        WHERE t.tag = ANY(q.requested)
    ) AS matched_tag_count
FROM array_ops_lab.documents AS d
CROSS JOIN query_tags AS q
WHERE d.tags && q.requested
ORDER BY matched_tag_count DESC, d.doc_id
LIMIT 20;
```

The `d.tags && q.requested` predicate can leverage GIN to **narrow down candidate documents** before scoring their intersections.

Still, if a tag is very common or candidates are numerous, unnesting, aggregating, and sorting remain costly. Do not imagine GIN natively outputs `matched_tag_count` or pre-sorts by match count.

---

## 36. Edge cases to test before going to production

### 36.1. Empty arrays

```sql
SELECT
    'sql' = ANY(ARRAY[]::TEXT[]) AS any_empty,
    'sql' = ALL(ARRAY[]::TEXT[]) AS all_empty,
    ARRAY[]::TEXT[] && ARRAY['sql']::TEXT[]
        AS overlap_empty,
    ARRAY['sql']::TEXT[] @> ARRAY[]::TEXT[]
        AS contains_empty;
```

### 36.2. NULL arrays

```sql
SELECT
    'sql' = ANY(NULL::TEXT[]) AS any_unknown,
    'sql' = ALL(NULL::TEXT[]) AS all_unknown,
    NULL::TEXT[] && ARRAY['sql']::TEXT[]
        AS overlap_unknown;
```

### 36.3. NULL elements

```sql
SELECT
    'gin' = ANY(ARRAY['sql',NULL::TEXT]::TEXT[])
        AS no_known_match_but_unknown,
    'sql' = ANY(ARRAY['sql',NULL::TEXT]::TEXT[])
        AS known_match,
    array_position(
        ARRAY['sql',NULL::TEXT]::TEXT[],
        NULL::TEXT
    ) AS null_position;
```

### 36.4. Arrays with duplicate elements

```sql
SELECT
    ARRAY['sql','sql']::TEXT[]
        @> ARRAY['sql']::TEXT[] AS contains,
    cardinality(ARRAY['sql','sql']::TEXT[]) AS cardinality_two;
```

### 36.5. Case sensitivity

```sql
SELECT
    'SQL' = ANY(ARRAY['sql']::TEXT[]) AS exact_text_match;
```

Under standard case-sensitive text comparison, do not expect `'SQL'` and `'sql'` to match automatically. If the system wants case-insensitive tags:

- Normalize data on write (e.g., consistent lowercase policy).
- Choose an appropriate collation/type/operator.
- Ensure both stored data and query parameters undergo the same normalization.
- Index the exact normalized expression.

Do not wrap one side in `LOWER` and expect a plain GIN index on `tags TEXT[]` to accelerate the modified comparison.

### 36.6. Diacritics and Unicode strings

`'tìm kiếm'` differs from `'tim kiem'` under standard comparison. If accent-insensitive matching is desired, implement a dedicated normalization pipeline tested across Unicode/collation cases. GIN `array_ops` matches **stored elements**, rather than automatically equating non-diacritic Vietnamese with accented text.

---

## 37. Common mistakes

| Mistake | Why it is wrong | Better approach |
| --- | --- | --- |
| Using `@>` when any one tag suffices | `@>` requires all tags | Use `&&` |
| Using `&&` when all tags are required | `&&` only needs one shared tag | Use `@>` |
| Using `x <> ANY(arr)` for “x not in arr” | True as soon as one element differs from x | Use `x <> ALL(arr)` with explicit NULL policy |
| Assuming `x = ANY(empty)` is NULL | `ANY` on empty is FALSE | Check quantified logic |
| Assuming `x = ALL(empty)` is FALSE | `ALL` on empty is TRUE | Add `cardinality>0` if needed |
| Treating `NULL::TEXT[]` as `ARRAY[]::TEXT[]` | Unknown differs from empty | Handle separately |
| Treating an array with NULL as a NULL array | One NULL element differs from a NULL array | Distinguish clearly |
| Assuming `NULL = ANY({NULL})` is TRUE | Strict `=` with NULL yields UNKNOWN | Use NULL-safe semantics if intended |
| Using `NOT IN` with NULLs expecting TRUE | UNKNOWN propagates | Review NULL policy |
| Using `@>` to count duplicates | Containment ignores multiplicity | `unnest` and `COUNT` |
| Assuming `ARRAY[a,b] = ARRAY[b,a]` | Arrays are ordered | If set semantics needed, normalize/sort/distinct |
| Thinking `@>` returns an intersecting array | `@>` returns Boolean | Use `unnest`/`INTERSECT`/`array_agg` |
| Using `INTERSECT ALL` when distinct is wanted | `ALL` keeps copies per minimum count | Use `INTERSECT` |
| Dropping `DISTINCT` in manual intersection | Either side may have duplicates | Use `INTERSECT` or `DISTINCT` |
| Using `= ANY` for NULL-safe intersection | `=` does not match NULL with NULL | `INTERSECT` or `IS NOT DISTINCT FROM` |
| Forgetting `ORDER BY` inside `array_agg` | Order is unstable | Put `ORDER BY` inside aggregate |
| Using `array_length(empty,1)=0` | Returns NULL for empty dimension | Use `cardinality` |
| Using `COUNT(*)` after `LEFT JOIN LATERAL unnest` | Elementless rows still emit a row | Use `COUNT(ordinality)` or `cardinality` |
| Expecting `array_agg` on empty input to return `{}` | Returns NULL | `COALESCE` or `ARRAY` constructor |
| Using `array_to_string + LIKE` for exact tag match | Substrings and delimiters cause false positives | `@>`/`&&` |
| Assuming `'x'=ANY(array_col)` uses GIN automatically | Not the indexable operator form | `array_col @> ARRAY['x']` |
| Thinking GIN is broken after seeing Seq Scan | Small table or low selectivity | Read `EXPLAIN` and measure |
| Expecting GIN to return rows in `ORDER BY date` order | GIN is not a timestamp B-tree | Separate index or sort |
| Always using `ARRAY` instead of a junction table | Loses per-element FK/uniqueness | Design around invariants |
| Passing arrays via string interpolation | Quoting/injection/type bugs | `PreparedStatement` and SQL Array |
| Overwriting tags with stale client arrays | Lost updates under concurrency | Atomic `UPDATE`/version guard |
| Treating JSONB arrays and SQL arrays as sharing operators | Two distinct type systems | Use operators matching the type |
| Ignoring `tags IS NULL` in endpoint filters | Breaks API contract | Specify null/empty semantics |
| Skipping duplicate tests | Wrong counts/tag frequencies | Test arrays with duplicates |
| Counting items via `COUNT(*)` after `LEFT JOIN unnest` | Null-extended rows skew counts | `COUNT(t.ord)` |
| Guessing array type from untyped string literals | Unknown-type errors on empty arrays | `ARRAY[]::TYPE[]` |
| Assuming all types share identical GIN ops | Depends on operator class and type | Check operator class and `EXPLAIN` |

---

## 38. Practice exercises

### Exercise 1 — Create and distinguish the three states

Write three expressions producing `ARRAY[]::INTEGER[]`, `NULL::INTEGER[]`, and `ARRAY[NULL::INTEGER]`. Use `cardinality` to explain the differences.

### Exercise 2 — @> contains all

Find documents containing both `sql` and `postgresql`. Predict the `doc_id`s from the lab data.

### Exercise 3 — && contains any

Find documents containing at least one of `gin` or `api`. Why would `@> ARRAY['gin','api']` be wrong here?

### Exercise 4 — <@ allowed set

Write a query selecting only rows whose tags all belong to `{'sql','gin','array','postgresql','etl'}`. Why can an empty array appear in the output?

### Exercise 5 — Array equality vs. containment

Test `ARRAY['a','b'] = ARRAY['b','a']` and both directions of containment. Explain why the results differ.

### Exercise 6 — Duplicates do not affect @>

Compare `ARRAY['a'] @> ARRAY['a','a']` against `ARRAY['a']=ARRAY['a','a']`. If exactly two copies are required, write an appropriate SQL approach.

### Exercise 7 — Scalar membership

Find rows with tag `sql` using `'sql' = ANY(tags)`. Compare the selected rows against `tags @> ARRAY['sql']` on the lab table.

### Exercise 8 — ANY on an empty array

Predict `5 = ANY(ARRAY[]::INT[])` and `5 > ANY(ARRAY[]::INT[])`. Explain using existential quantification logic.

### Exercise 9 — ALL on an empty array

Predict `5 = ALL(ARRAY[]::INT[])` and `5 > ALL(ARRAY[]::INT[])`. Why does TRUE not imply the array holds any values?

### Exercise 10 — NULL array

Predict `5 = ANY(NULL::INT[])` and `5 = ALL(NULL::INT[])`. Contrast with an empty array.

### Exercise 11 — NULL element with ANY

Predict `5 = ANY(ARRAY[6,NULL::INT])`, `5 = ANY(ARRAY[5,NULL::INT])`, and explain precedence among TRUE, FALSE, and UNKNOWN.

### Exercise 12 — NULL element with ALL

Predict `5 = ALL(ARRAY[5,NULL::INT])` and `5 = ALL(ARRAY[6,NULL::INT])`.

### Exercise 13 — <> ANY and <> ALL

Test `5 <> ANY(ARRAY[5,6])` and `5 <> ALL(ARRAY[5,6])`. Which one expresses “no element equals 5”?

### Exercise 14 — NOT IN with NULL

Compare `5 NOT IN (6,7)` with `5 NOT IN (6,NULL)`. Why do the results differ even though 5 is absent from both?

### Exercise 15 — Scores: at least one vs. every element

Write a query selecting rows with at least one score > 9, and one selecting rows with every score < 50. Which one accidentally matches empty arrays? Fix it for a “must have scores” contract.

### Exercise 16 — ANY on a scalar column

Assume `orders.status TEXT`. Write `WHERE status = ANY($1::TEXT[])`. Compare its index eligibility against `'sql' = ANY(tags)` on an array column.

### Exercise 17 — Intersection of two arrays

Write an `INTERSECT` between `ARRAY['sql','gin','sql']` and `ARRAY['sql','api']`. How many `sql` rows are returned?

### Exercise 18 — Multiset intersection

Use `INTERSECT ALL` on `A={a,a,b}` and `B={a,a,a,c}`. Why are two `a` rows returned?

### Exercise 19 — Build an array from INTERSECT

Use `ARRAY_AGG(... ORDER BY ...)` and `COALESCE` to return a distinct intersection array even when there are no common elements.

### Exercise 20 — Intersection using = ANY

Use `unnest(A)` and `elem = ANY(B)` to find the intersection; add `DISTINCT`. Why does this differ from `INTERSECT ALL` regarding duplicates?

### Exercise 21 — NULLs in intersections

Given two arrays each containing NULL, compare `INTERSECT` with `NULL = ANY(...)`. How do you exclude NULL from the intersection?

### Exercise 22 — Intersection preserving A's order

Use `WITH ORDINALITY` and `MIN(ord)` to return distinct intersecting elements ordered by first appearance in A.

### Exercise 23 — Element positions

Use `array_position` to find `sql` in `{gin,sql,sql}` and `array_positions` to find all positions. What are the outputs?

### Exercise 24 — Finding NULL positions

Use `array_position(ARRAY['sql',NULL::TEXT],NULL::TEXT)`. Why does it find the position while `NULL = ANY(...)` returns UNKNOWN?

### Exercise 25 — Counting documents per tag

Write a query counting documents per tag using `unnest` and `COUNT(DISTINCT doc_id)`. Why does doc 4 have two `sql` tags yet count as only one document for that tag?

### Exercise 26 — Counting total occurrences

Write a query counting how many times `sql` appears across all tag elements of all documents **without deduplicating**. Contrast with the document count for `sql`.

### Exercise 27 — array_agg and NULL

Run `array_agg(tag)` on a set containing NULL, then add `FILTER (WHERE tag IS NOT NULL)`. When zero rows remain, how do you return an empty array?

### Exercise 28 — array_length vs. cardinality

Compare both functions on an empty array, a NULL array, and a 2×2 matrix. Why does `array_length(tags,1)=0` fail to detect empty arrays?

### Exercise 29 — WITH ORDINALITY

Unnest `{sql,gin,array}` into three rows with ordinality. Add `ORDER BY ord` to guarantee output order.

### Exercise 30 — Multidimensional arrays

Create `ARRAY[[1,2],[3,4]]`, evaluate `cardinality`, `array_length` along dimensions 1 and 2, and `unnest`. When does flattening lose structural information?

### Exercise 31 — GIN index

Create a GIN index on `tags`. Run `tags @> ARRAY['gin']` and `tags && ARRAY['api','gin']`, and check `EXPLAIN`. Why might a ten-row table pick `Seq Scan`?

### Exercise 32 — GIN and = ANY

Compare `EXPLAIN` for `'sql' = ANY(tags)` vs. `tags @> ARRAY['sql']`. Why does operator class support matter more than intuitive equivalence?

### Exercise 33 — Case-insensitive tags

If `SQL` and `sql` could otherwise be stored as two separate tags, what normalization policy would you enforce? How do you ensure queries and indexes use the same normalization?

### Exercise 34 — Atomic append

Write an `UPDATE` adding `gin` to doc 1's `tags` if missing, using `array_append` and a containment predicate in the same statement. What happens if you run the statement a second time?

### Exercise 35 — Lost updates

Describe two clients concurrently reading a document's tags and overwriting with whole new arrays. Propose atomic `UPDATE` or optimistic versioning to prevent lost updates.

### Exercise 36 — JDBC array parameter

Write a `PreparedStatement` using `createArrayOf("text", ...)` and `WHERE tags && ?::TEXT[]`. Why should you never concatenate user input into SQL?

### Exercise 37 — JSONB arrays vs. SQL arrays

Create a `TEXT[]` and a `JSONB` array holding the same two tags. Apply the respective containment operator to each. Why can't you call `&&` directly on JSONB assuming SQL-array behavior?

### Exercise 38 — Relational child table

Design a `documents`, `tags_catalog`, `document_tags` schema with `FOREIGN KEY` constraints and `PRIMARY KEY(doc_id,tag_id)`. When is this design stronger than storing `TEXT[]`?

### Exercise 39 — Intersection and ranking problem

A query takes 10 interest tags and needs the top 20 documents sharing at least one tag, ranked by **count of distinct common tags**. Write an approach using GIN overlap to select candidates, then `unnest` and `COUNT(DISTINCT ...)` to rank them.

### Exercise 40 — Designing a NULL-safe query

An API requests “documents **without the sql tag**” while the schema allows `tags=NULL` and NULL array elements. Propose at least two distinct contracts, write the corresponding SQL, and explain how their outputs differ.

---

## 39. Checklist for designing array queries in applications

| Question | Check |
| --- | --- |
| Does the column hold an SQL array or JSONB? | Actual column data type |
| What element type does the array store? | TEXT/INTEGER/UUID/... |
| Can the entire array be NULL? | `IS NULL` vs. empty array |
| Can it contain NULL elements? | `ANY`/`ALL` can produce UNKNOWN |
| Must elements be unique? | Normalize or use a junction table |
| Must order be preserved? | `WITH ORDINALITY`, `ORDER BY` |
| Require all tags? | `@>` |
| Require at least one common tag? | `&&` |
| Require all tags within an allowed set? | `<@` |
| Scalar equals at least one element? | `= ANY` |
| Scalar differs from every element? | `<> ALL`, verify NULLs |
| Possible empty arrays? | `ANY` is FALSE, `ALL` is TRUE |
| How are NULL arrays handled? | Do not assume empty |
| Misusing `<> ANY`? | It is not `NOT IN` |
| Need boolean overlap or array intersection? | `&&` vs. `INTERSECT`/`unnest` |
| Set or multiset intersection? | `INTERSECT` vs. `INTERSECT ALL` |
| Should NULL count as a common element? | Set ops / NULL-safe join |
| Must intersection follow A's order? | Ordinality and first occurrence |
| Need intersection element count? | Proper `DISTINCT` and `COUNT` |
| Using `COUNT` after `unnest`? | Item frequency vs. document count |
| Need an empty array on empty output? | `COALESCE(array_agg,ARRAY[]::type[])` |
| Possible duplicate elements? | `@>` ignores multiplicity |
| Need element positions? | `array_position`/`array_positions` |
| Multidimensional array? | `cardinality` and shape |
| Using `cardinality` instead of `array_length`? | Empty array gives 0 vs. NULL |
| Query compatible with GIN `array_ops`? | `@>`, `&&`, `<@`, `=` |
| Expecting `= ANY(array_col)` to hit GIN? | Check operator and `EXPLAIN` |
| List input parameter? | Bind SQL Array with proper type |
| Meaning of an empty input list? | No filter vs. zero matches |
| Case/diacritic normalization needed? | Normalize writes and queries identically |
| Need per-element FK/uniqueness? | Consider a junction table |
| Frequent tag updates? | Update overhead, HOT/WAL/GIN |
| Concurrent updates? | Atomic `UPDATE` or version guard |
| Very low selectivity? | Seq Scan may outperform index |
| Benchmarked both reads and writes? | `EXPLAIN`, buffers, latency |
| Tenant/access permissions? | Separate authn/authz or RLS |
| Tested three-valued SQL logic? | Empty/NULL element/NULL array |
| Tested set vs. multiset? | Duplicates and `INTERSECT ALL` |

## Conclusion

**Array operators, ANY, ALL, and intersections** give you multiple ways to express conditions over multi-valued PostgreSQL data. What matters most is not memorizing as many symbols as possible, but choosing the right **operation semantics**:

- `tags @> ARRAY['a','b']`: `tags` must contain **all** required elements.
- `tags && ARRAY['a','b']`: `tags` shares **at least one** common element.
- `tags <@ ARRAY[...]`: every element of `tags` belongs to the allowed set.
- `x = ANY(arr)`: at least one element equals `x`.
- `x <> ALL(arr)`: every element differs from `x`, **while accounting for UNKNOWN when NULLs exist**.
- `x <> ANY(arr)` does **not** mean “x is not in the array.”
- `ANY(empty)` is FALSE and `ALL(empty)` is TRUE; a NULL array evaluates to UNKNOWN under common strict comparisons.
- `INTERSECT` computes a **distinct set intersection**; `INTERSECT ALL` computes an intersection preserving minimum multiplicity.
- `unnest` and `array_agg` convert between array and row representations; `WITH ORDINALITY` and `ORDER BY` control ordering.
- `array_position` has NULL-safe semantics distinct from scalar equality.
- GIN is powerful for array queries using `@>`/`&&`, yet not every `ANY` expression or array operation automatically uses the index.
- When elements need foreign keys, uniqueness, or per-element metadata, a **relational junction table** is usually the cleaner design.

When you clearly understand the distinctions among **membership, containment, overlap, three-valued logic, and set intersection**, you can write PostgreSQL array queries that stay accurate on empty/NULL/duplicate edge cases and scale smoothly as your data grows.
