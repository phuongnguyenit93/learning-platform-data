# Set-Returning Functions and Using Them in FROM

In PostgreSQL, many functions do not return just **one value**—they can return **zero, one, or many rows**. Functions such as `generate_series()`, `unnest()`, `jsonb_array_elements()`, `jsonb_to_recordset()`, and user-defined functions are commonly called **set-returning functions (SRFs)**. When placed in the **`FROM`** clause, their output is treated like a **row source** that the query can filter, join, aggregate, or sort.

Imagine a project with an array of tags `['java', 'postgresql', 'api']`. Instead of storing three columns `tag1`, `tag2`, and `tag3`, you can store a `text[]` array and use `unnest()` to turn each element into a row. When you need a seven-day reporting calendar, `generate_series()` generates those timestamps without storing a calendar table beforehand. When receiving a JSON array of members, `jsonb_to_recordset()` turns objects into strongly typed columns.

The biggest subtlety arises when an SRF **depends on each row of another table**: the **`LATERAL`** keyword, source ordering in `FROM`, and choosing **`CROSS JOIN` vs. `LEFT JOIN`** determine which rows are retained. An SRF returning **0 rows** can drop the parent row from the result if the wrong join type is used.

In this lesson, you will:

- Understand SRFs, table functions, `SETOF` and `TABLE` return types, and calling them in `FROM`.
- Use `generate_series()` to generate number sequences, timestamps, and date scaffolds.
- Flatten arrays with `unnest()`, and read positions with `WITH ORDINALITY` and `generate_subscripts()`.
- Expand JSON arrays/objects using `jsonb_array_elements()`, `jsonb_to_recordset()`, and related functions.
- Distinguish **SRFs in `FROM`**, **subqueries**, and `LATERAL` scoping rules.
- Use `LEFT JOIN LATERAL ... ON TRUE` to keep parent rows even when the function returns zero rows.
- Write set-returning functions in SQL and PL/pgSQL and combine them with other tables.
- Avoid row multiplication errors, alias scope errors, malformed JSON errors, unordered output, and performance bottlenecks.

> **Environment:** Examples target modern PostgreSQL and a lab database. Use the schema name `lesson_srf` so queries do not depend on `search_path`. `CREATE SCHEMA`, `CREATE TABLE`, and `CREATE FUNCTION` require appropriate privileges; do not run on a production database containing important data.

## 1. From Single-Value Functions to Set-Returning Functions

A regular function takes arguments and produces **a single value**:

```sql
SELECT upper('postgresql') AS result;
-- POSTGRESQL

SELECT length('postgresql') AS character_count;
-- 10
```

A set-returning function can produce **multiple rows** from a single call:

```sql
SELECT n
FROM generate_series(1, 5) AS g(n);
```

Result:

```text
 n
---
 1
 2
 3
 4
 5
```

`generate_series(1, 5)` is a **row source** in `FROM`. `AS g(n)` defines:

- `g`: the source/alias name for the function.
- `n`: the output column name exposed by this source.

Just like a table, an SRF source can participate in `JOIN`, `WHERE`, `GROUP BY`, `ORDER BY`, and subqueries.

### One function, varying row counts

```sql
SELECT n FROM generate_series(1, 3) AS g(n);
-- 3 rows

SELECT n FROM generate_series(1, 1) AS g(n);
-- 1 row

SELECT n FROM generate_series(5, 1) AS g(n);
-- 0 rows when default step is +1
```

Do not assume a function call in `FROM` always produces exactly one row like a scalar function. When joined with another table, **result size** depends on how many rows the function returns per call.

### SRFs and aggregates are different concepts

| Type | Typical transformation direction | Example |
|---|---|---|
| **Scalar function** | One input → one value. | `upper('abc')` → `'ABC'`. |
| **Set-returning function** | One call → 0..N rows. | `generate_series(1,3)` → 1, 2, 3. |
| **Aggregate** | N rows in a group → one value. | `array_agg(x ORDER BY ...)` → one array. |
| **Window function** | Processes rows across a partition/frame without necessarily reducing output row count. | `row_number() OVER (...)`. |

In practice, you can **flatten with an SRF** and then **re-aggregate with an aggregate**. Be clear which step **expands** row count and which step **reduces** it.

## 2. Types of Set-Returning Functions in PostgreSQL

An SRF can return:

1. **A single scalar column**: `generate_series()` returns `integer`/`bigint`/`numeric`/timestamp depending on overload; `unnest(text[])` returns each `text`.
2. **A composite type**: multiple columns matching a table type, composite type, or suitably declared `record`.
3. **A result table with named columns** via `RETURNS TABLE(...)`.
4. **A JSON/record set** expanded into rows whose columns are defined in `FROM`.

Single-column example:

```sql
SELECT x.value
FROM unnest(ARRAY[10, 20, 30]) AS x(value);
```

Multi-column example from JSON:

```sql
SELECT m.name, m.role
FROM jsonb_to_recordset(
    '[{"name":"An","role":"dev"},
      {"name":"Bình","role":"reviewer"}]'::jsonb
) AS m(name text, role text);
```

In the second example, `AS m(name text, role text)` does more than rename: it defines **the column types and names** of the recordset output. PostgreSQL uses that definition to convert JSON values into the corresponding SQL columns.

## 3. Sample Dataset: Projects, Tags, and Tasks

To follow SRFs with realistic data, create a schema and two tables:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_srf;

CREATE TABLE lesson_srf.projects (
    project_id BIGINT PRIMARY KEY,
    project_name TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::text[],
    members JSONB NOT NULL DEFAULT '[]'::jsonb,
    CONSTRAINT chk_members_is_array
        CHECK (jsonb_typeof(members) = 'array')
);

CREATE TABLE lesson_srf.tasks (
    task_id BIGINT PRIMARY KEY,
    project_id BIGINT NOT NULL
        REFERENCES lesson_srf.projects(project_id),
    task_title TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('TODO', 'DOING', 'DONE')),
    created_at TIMESTAMPTZ NOT NULL
);
```

Insert sample data:

```sql
INSERT INTO lesson_srf.projects(
    project_id, project_name, tags, members
)
VALUES
    (
        1,
        'Alpha',
        ARRAY['java', 'postgresql', 'api']::text[],
        '[
           {"name":"An","role":"developer"},
           {"name":"Bình","role":"reviewer"}
         ]'::jsonb
    ),
    (
        2,
        'Beta',
        ARRAY['frontend', 'api']::text[],
        '[]'::jsonb
    ),
    (
        3,
        'Gamma',
        ARRAY[]::text[],
        '[{"name":"Chi","role":"lead"}]'::jsonb
    );

INSERT INTO lesson_srf.tasks(
    task_id, project_id, task_title, status, created_at
)
VALUES
    (11, 1, 'Design schema', 'DONE',
        TIMESTAMPTZ '2026-11-10 09:00:00+07'),
    (12, 1, 'Write API', 'DOING',
        TIMESTAMPTZ '2026-11-11 10:00:00+07'),
    (13, 1, 'Test API', 'TODO',
        TIMESTAMPTZ '2026-11-12 11:00:00+07'),
    (21, 2, 'Build UI', 'DOING',
        TIMESTAMPTZ '2026-11-13 14:00:00+07');
```

Overview:

| Project | `tags` | `members` | Task count |
|---|---|---|---:|
| Alpha (1) | java, postgresql, api | An, Bình | 3 |
| Beta (2) | frontend, api | Empty JSON array | 1 |
| Gamma (3) | Empty text array | Chi | 0 |

This dataset highlights two common cases: **empty arrays** causing an SRF to return 0 rows, and **projects with no tasks yet** that still need to appear in reports.

## 4. SRF Syntax in FROM and Aliases

Basic form:

```sql
SELECT t.column_name
FROM some_set_returning_function(arguments)
     AS t(column_name);
```

For multi-column functions, the column list can contain multiple names, and for functions returning an untyped `record`, it may require **data types**:

```sql
SELECT x.name, x.role
FROM jsonb_to_recordset(
    '[{"name":"An","role":"developer"}]'::jsonb
) AS x(name text, role text);
```

### Why assign aliases?

Aliases avoid awkward default names like `generate_series` or `unnest`, especially when multiple functions are present:

```sql
SELECT g.number, t.tag
FROM generate_series(1, 2) AS g(number)
CROSS JOIN unnest(ARRAY['java', 'sql']::text[]) AS t(tag)
ORDER BY g.number, t.tag;
```

The result has **2 × 2 = 4 rows** because it is a `CROSS JOIN` of two independent sets.

### Name scope matches table sources

In:

```sql
FROM generate_series(1, 5) AS series(value)
```

`series` is the source alias and `value` is the column usable in `SELECT`/`WHERE`. Once you assign an alias in a query block, use that alias to refer to the source rather than trying to reference the function name like an unaliased table.

## 5. generate_series(): Generating Integer Sequences

A common overload:

```sql
generate_series(start, stop [, step])
```

In PostgreSQL, `stop` **is included if the series lands exactly on that bound**.

```sql
SELECT n
FROM generate_series(1, 5) AS s(n);
-- 1, 2, 3, 4, 5

SELECT n
FROM generate_series(2, 10, 2) AS s(n);
-- 2, 4, 6, 8, 10

SELECT n
FROM generate_series(5, 1, -2) AS s(n);
-- 5, 3, 1
```

### Step direction and bounds

| Call | Result | Explanation |
|---|---|---|
| `generate_series(1,5)` | 1,2,3,4,5 | Default step +1. |
| `generate_series(1,5,2)` | 1,3,5 | Positive step. |
| `generate_series(5,1,-2)` | 5,3,1 | Negative step. |
| `generate_series(5,1,1)` | 0 rows | Start exceeds stop with positive step. |
| `generate_series(1,5,-1)` | 0 rows | Start is below stop with negative step. |
| `generate_series(1,5,0)` | Error | Step of 0 does not make finite progress. |

For numeric overloads, if a required parameter is SQL `NULL`, the function normally returns **0 rows** rather than a row containing null. This differs from ordinary scalar functions that may return a single null value.

### Filtering generated numbers

```sql
SELECT s.n
FROM generate_series(1, 20) AS s(n)
WHERE s.n % 3 = 0
ORDER BY s.n;
```

Result: 3, 6, 9, 12, 15, 18. The SRF produces the row source; `WHERE` filters via modulo.

### Generating numbers with numeric

```sql
SELECT x.value
FROM generate_series(
    0.0::numeric,
    1.0::numeric,
    0.25::numeric
) AS x(value);
-- 0.0, 0.25, 0.50, 0.75, 1.00
```

Choose `numeric` when you want exact decimal steps under base-10 representation, instead of generating monetary data with floating-point types without accounting for rounding error.

## 6. generate_series() with Timestamp and Interval

PostgreSQL has overloads generating timestamps from start to stop by an `interval`:

```sql
SELECT t.day_start
FROM generate_series(
    TIMESTAMP '2026-11-10 00:00:00',
    TIMESTAMP '2026-11-14 00:00:00',
    INTERVAL '1 day'
) AS t(day_start)
ORDER BY t.day_start;
```

This generates 5 midnight points, each of type `timestamp without time zone`.

### Generating a date scaffold for reports

```sql
SELECT g.day_start::date AS report_date
FROM generate_series(
    TIMESTAMP '2026-11-10',
    TIMESTAMP '2026-11-14',
    INTERVAL '1 day'
) AS g(day_start)
ORDER BY report_date;
```

The result includes November 10, 11, 12, 13, and 14, 2026. The calendar is generated on the fly without requiring a pre-populated calendar table.

### Time zone and DST considerations

`timestamp without time zone` represents wall-clock date/time, not a time-zone-anchored instant. `timestamptz` represents an absolute point in time. In regions observing daylight saving time, stepping **one local calendar day** is not always equal to **24 absolute hours**.

When an application needs date scaffolds for a specific geographical zone like `Europe/Berlin`, explicitly define scheduling rules, IANA time zones, and day-boundary conversions. Never assume `interval '1 day'` always means the same thing as `interval '24 hours'` in every context.

### Do not generate huge series from untrusted input

`generate_series(1, 1000000000)` can create an enormous number of rows. For API inputs, validate start/stop/step, expected element count, and resource limits before generating.

One way to bound this in a lab example:

```sql
WITH request_params AS (
    SELECT
        1::integer AS start_value,
        100::integer AS stop_value
)
SELECT g.n
FROM request_params AS p
CROSS JOIN LATERAL generate_series(
    p.start_value,
    LEAST(p.stop_value, p.start_value + 99)
) AS g(n)
ORDER BY g.n;
```

This only illustrates bounding a series for a **+1 step**; for negative steps, huge integers, overflow, or null arguments, write dedicated validation rather than applying the formula mechanically.

## 7. unnest(): Turning PostgreSQL Arrays into Rows

A `text[]` array can hold multiple tags. `unnest()` creates one row per element:

```sql
SELECT t.tag
FROM unnest(ARRAY['java', 'postgresql', 'api']::text[])
     AS t(tag);
```

The result has three rows, one per tag. When the input is a numeric array:

```sql
SELECT n.value
FROM unnest(ARRAY[10, 20, 30]) AS n(value);
```

The `value` column has type `integer` in this example, **not text**.

### unnest on an empty array

```sql
SELECT x.tag
FROM unnest(ARRAY[]::text[]) AS x(tag);
-- 0 rows
```

### unnest on a NULL array

```sql
SELECT x.tag
FROM unnest(NULL::text[]) AS x(tag);
-- 0 rows
```

Distinguish:

- `ARRAY[]::text[]`: an **array with 0 elements**.
- `NULL::text[]`: no array value.
- `ARRAY[NULL::text]`: **an array containing 1 null element**.

For the last case:

```sql
SELECT x.tag
FROM unnest(ARRAY[NULL::text]) AS x(tag);
-- 1 row, tag = SQL NULL
```

This is an important distinction when combining with `LEFT JOIN` or `COUNT(*)`.

## 8. WITH ORDINALITY: Preserving Element Positions

`unnest` produces a row source, but sometimes you need to know **which position in the original array** each element came from. `WITH ORDINALITY` appends a 1-based ordinal column starting at **1**.

```sql
SELECT
    x.position,
    x.tag
FROM unnest(ARRAY['java', 'postgresql', 'api']::text[])
     WITH ORDINALITY AS x(tag, position)
ORDER BY x.position;
```

Result:

| position | tag |
|---:|---|
| 1 | java |
| 2 | postgresql |
| 3 | api |

### Why is ORDER BY position still needed?

`WITH ORDINALITY` numbers **the rows generated by the function**. However, after `JOIN`, `WHERE`, `GROUP BY`, and planner transformations, **final output row order is not guaranteed**. To display items in their exact sequence, add:

```sql
ORDER BY x.position
```

### Applying across multiple projects

```sql
SELECT
    p.project_id,
    p.project_name,
    tag.position,
    tag.value AS tag_name
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL unnest(p.tags)
     WITH ORDINALITY AS tag(value, position)
ORDER BY p.project_id, tag.position;
```

Project Alpha produces three rows in tag order. Beta produces two rows. **Gamma produces zero rows** because `tags` is an empty array; the next sections explain how to retain Gamma.

### Ordinality is not a business key

If you modify an array, prepend an element, or reorder elements, ordinality values shift as well. Use `WITH ORDINALITY` to reflect **position within the SRF result**, not as a stable entity ID.

## 9. generate_subscripts(): Getting Array Subscripts

When you need actual subscripts of an array dimension, PostgreSQL provides `generate_subscripts(array, dimension)`.

```sql
SELECT
    s.idx,
    p.tags[s.idx] AS tag_name
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL generate_subscripts(p.tags, 1) AS s(idx)
WHERE p.project_id = 1
ORDER BY s.idx;
```

For the one-dimensional array in the example, subscripts are 1, 2, 3. This is handy when indexing with `array[index]`.

### generate_subscripts and WITH ORDINALITY are not always identical

`WITH ORDINALITY` numbers **the rows produced by the function**, starting at 1. `generate_subscripts()` returns **valid subscripts of the array along the chosen dimension**.

PostgreSQL can store arrays with a **lower bound other than 1**. In that case, array subscripts and ordinality differ.

Example:

```sql
SELECT
    array_lower('[0:2]={10,20,30}'::integer[], 1)
        AS array_first_index;
-- 0

SELECT idx
FROM generate_subscripts(
    '[0:2]={10,20,30}'::integer[],
    1
) AS s(idx)
ORDER BY idx;
-- 0, 1, 2
```

If you used `unnest(...) WITH ORDINALITY` on that same array, ordinality would be **1, 2, 3**. Do not confuse array subscripts with row ordinality when element addressing matters.

## 10. LATERAL: Letting an SRF See Columns from Preceding Sources

One of the strongest capabilities of an SRF in `FROM` is that **function arguments can depend on columns from earlier sources in the same `FROM`**.

Example:

```sql
SELECT
    p.project_name,
    t.tag
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL unnest(p.tags) AS t(tag)
ORDER BY p.project_id, t.tag;
```

`unnest(p.tags)` uses **each `p` row's array**. Conceptually:

```text
projects
   ├── Alpha, tags=[java, postgresql, api]
   │       └── unnest → 3 rows
   ├── Beta, tags=[frontend, api]
   │       └── unnest → 2 rows
   └── Gamma, tags=[]
           └── unnest → 0 rows

CROSS JOIN LATERAL → 5 result rows
```

**`LATERAL`** indicates that the right-hand expression is allowed to reference valid columns from left-hand sources in that scope.

### For table functions, LATERAL is often optional

PostgreSQL allows **function arguments in `FROM`** to reference preceding sources laterally even without writing the `LATERAL` keyword explicitly:

```sql
SELECT p.project_id, t.tag
FROM lesson_srf.projects AS p
CROSS JOIN unnest(p.tags) AS t(tag)
ORDER BY p.project_id, t.tag;
```

Here, `unnest(p.tags)` still uses `p.tags` for each row. Even though `LATERAL` is often optional for *table functions*, **writing it explicitly** makes intent clearer and stays consistent with lateral subqueries.

## 11. CROSS JOIN LATERAL vs. LEFT JOIN LATERAL

The difference matters especially when the SRF returns **0 rows**.

### CROSS JOIN LATERAL: zero elements drops the parent row

```sql
SELECT
    p.project_id,
    p.project_name,
    t.tag
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL unnest(p.tags) AS t(tag)
ORDER BY p.project_id, t.tag;
```

Gamma has `tags = ARRAY[]::text[]`, so `unnest` returns **0 rows**. With `CROSS JOIN`, project Gamma **does not appear** in the output.

This is desirable if the requirement is "list **all tags that actually exist**".

### LEFT JOIN LATERAL: keeping the parent row

```sql
SELECT
    p.project_id,
    p.project_name,
    t.tag
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags) AS t(tag)
  ON TRUE
ORDER BY p.project_id, t.tag NULLS LAST;
```

Gamma is retained with `t.tag = NULL`. This is a **null-extended row** produced by `LEFT JOIN` when the function returns no matches.

### Quick comparison

| Condition | `CROSS JOIN LATERAL` | `LEFT JOIN LATERAL ... ON TRUE` |
|---|---|---|
| SRF returns 3 rows | 3 results for parent row | 3 results for parent row |
| SRF returns 1 row | 1 result | 1 result |
| SRF returns 0 rows | **Parent row is dropped** | **One parent row**, SRF columns set to `NULL` |
| Best fit | Flattening all actual elements. | Reporting all entities even when they have no elements. |

**Design rule:** if the requirement asks for "every project and its tags if any", prefer `LEFT JOIN LATERAL`. If it asks for "every existing tag across projects", `CROSS JOIN LATERAL` is usually right.

## 12. What Does ON TRUE Do?

In:

```sql
LEFT JOIN LATERAL unnest(p.tags) AS t(tag) ON TRUE
```

`ON TRUE` means **no additional join filter beyond calling the function with the parent row's argument**. If the SRF returns any rows, all of them satisfy `ON TRUE`. If the SRF returns 0 rows, `LEFT JOIN` still preserves the parent row.

You can add a join condition if needed:

```sql
SELECT
    p.project_name,
    t.tag
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags) AS t(tag)
  ON t.tag LIKE 'a%'
ORDER BY p.project_id, t.tag;
```

The condition in `ON` only pairs tags starting with `a`. Projects with no matching tags are still retained with a `NULL` tag column.

If instead you write:

```sql
SELECT
    p.project_name,
    t.tag
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags) AS t(tag)
  ON TRUE
WHERE t.tag LIKE 'a%';
```

then `WHERE` eliminates rows where `t.tag = NULL` because the predicate evaluates to unknown, causing **projects without matching tags to vanish**. This is the exact same rule as with ordinary `LEFT JOIN`s.

## 13. COUNT(*) When LEFT JOINing an SRF That Returns 0 Rows

Suppose you want to count tags per project:

```sql
SELECT
    p.project_id,
    COUNT(*) AS row_count,
    COUNT(t.tag) AS nonnull_tag_count
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags) AS t(tag)
  ON TRUE
GROUP BY p.project_id
ORDER BY p.project_id;
```

For Gamma, `LEFT JOIN` keeps **one null-extended row**:

```text
project_id = 3, t.tag = NULL
```

Therefore:

- `COUNT(*)` = **1**.
- `COUNT(t.tag)` = **0**.

If `tags` is allowed to contain **real null elements**, `COUNT(t.tag)` also skips those elements. When you need to count **elements including nulls**, use `WITH ORDINALITY` and count the position column:

```sql
SELECT
    p.project_id,
    COUNT(t.position) AS array_element_count
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags)
     WITH ORDINALITY AS t(tag, position)
  ON TRUE
GROUP BY p.project_id
ORDER BY p.project_id;
```

`position` is non-null for every real row emitted by `unnest`, and null only in the null-extended row added by `LEFT JOIN`. Thus `COUNT(t.position)` accurately reflects **the array's element count** here.

For ordinary one-dimensional arrays, `cardinality(p.tags)` is even more direct when you only need the element count **without flattening**:

```sql
SELECT
    project_id,
    cardinality(tags) AS tag_count
FROM lesson_srf.projects
ORDER BY project_id;
```

## 14. LATERAL Subqueries: Same Idea, Not Necessarily a Function

`LATERAL` also applies to **subqueries in `FROM`** when the subquery needs to reference left-hand sources.

Example fetching the **two newest tasks per project**:

```sql
SELECT
    p.project_id,
    p.project_name,
    recent.task_id,
    recent.task_title,
    recent.created_at
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL (
    SELECT
        t.task_id,
        t.task_title,
        t.created_at
    FROM lesson_srf.tasks AS t
    WHERE t.project_id = p.project_id
    ORDER BY t.created_at DESC, t.task_id DESC
    LIMIT 2
) AS recent ON TRUE
ORDER BY p.project_id, recent.created_at DESC NULLS LAST,
         recent.task_id DESC;
```

In the sample dataset:

- Alpha gets tasks 13 and 12.
- Beta gets task 21.
- Gamma **still has one row** with `recent.* = NULL`.

With `CROSS JOIN LATERAL`, Gamma would disappear.

### Regular derived subqueries cannot see left-hand sources

Invalid example:

```sql
-- Invalid: missing LATERAL for a derived subquery
-- that references p.project_id.
SELECT p.project_id, recent.task_id
FROM lesson_srf.projects AS p
LEFT JOIN (
    SELECT task_id
    FROM lesson_srf.tasks AS t
    WHERE t.project_id = p.project_id
) AS recent ON TRUE;
```

PostgreSQL does not allow a derived subquery in `FROM` to reference preceding sources like this without `LATERAL`.

**Distinction:** For a **function call** in `FROM`, referencing left-hand sources in arguments is generally allowed even without `LATERAL`; for a **subquery** needing left-hand references, write `LATERAL`.

## 15. SRFs and LATERAL Are Not a Manual Java Loop

Thinking "for each project, call `unnest(p.tags)`" helps understand the semantics:

```text
for each project p:
    for each tag in p.tags:
        emit (p.project_id, tag)
```

However, this is strictly a **logical model**. The PostgreSQL optimizer can organize execution according to dependencies, joins, filters, and query plans. Never assume exact physical invocation counts or order solely from loop intuition.

For functions with **side effects** or state dependence, inspect **volatility** and function semantics. Functions used in SQL queries should never rely on being invoked exactly once per row in an unguaranteed order.

## 16. Multi-Array unnest: Positional Zipping, Not Cartesian Product

PostgreSQL supports a multi-argument `unnest` variant in `FROM`:

```sql
SELECT
    x.id,
    x.label
FROM unnest(
    ARRAY[10, 20, 30]::integer[],
    ARRAY['A', 'B', 'C']::text[]
) AS x(id, label);
```

Result:

| id | label |
|---:|---|
| 10 | A |
| 20 | B |
| 30 | C |

Elements are **paired by position**, not every ID paired with every label.

### Arrays of different lengths

```sql
SELECT x.id, x.label
FROM unnest(
    ARRAY[10, 20, 30]::integer[],
    ARRAY['A', 'B']::text[]
) AS x(id, label);
```

Result:

| id | label |
|---:|---|
| 10 | A |
| 20 | B |
| 30 | NULL |

When arrays have unequal lengths, PostgreSQL **pads shorter arrays with SQL NULL** under multi-argument `unnest` syntax.

If the application requires strict one-to-one pairing, **validate input array lengths** instead of silently allowing null padding.

### Contrast with CROSS JOIN of two unnest calls

```sql
SELECT ids.id, names.label
FROM unnest(ARRAY[10, 20, 30]::integer[]) AS ids(id)
CROSS JOIN unnest(ARRAY['A', 'B']::text[]) AS names(label);
```

This query returns **3 × 2 = 6 rows** due to `CROSS JOIN` of two independent sets. It does **not** zip by position. Choose the syntax matching your goal: **positional zip** vs. **all combinations**.

## 17. ROWS FROM: Combining Multiple Table Functions in Parallel

PostgreSQL provides **`ROWS FROM (...)`** to combine outputs from multiple table functions into columns of a single row source.

```sql
SELECT
    r.number,
    r.label,
    r.position
FROM ROWS FROM (
    generate_series(1, 3),
    unnest(ARRAY['A', 'B']::text[])
) WITH ORDINALITY AS r(number, label, position)
ORDER BY r.position;
```

Result:

| number | label | position |
|---:|---|---:|
| 1 | A | 1 |
| 2 | B | 2 |
| 3 | NULL | 3 |

Functions are combined **side-by-side row for row**; shorter sources are padded with null up to the row count of the longest function.

### ROWS FROM vs. CROSS JOIN

```text
generate_series → 1, 2, 3
unnest           → A, B

ROWS FROM:
1-A
2-B
3-NULL

CROSS JOIN:
1-A
1-B
2-A
2-B
3-A
3-B
```

These are completely different data transformations. `ROWS FROM` is useful when functions emit aligned sequences by position; when joining by a business key, use an explicit `JOIN ... ON` condition.

## 18. JSONB Arrays into Multiple Rows

JSON is a common API payload format. PostgreSQL provides **`jsonb_array_elements()`** to flatten a JSON array into JSONB values:

```sql
SELECT e.element
FROM jsonb_array_elements(
    '["java", "postgresql", "api"]'::jsonb
) AS e(element);
```

The result is three rows, each containing a **`jsonb`** value representing a JSON string.

To obtain **text** directly:

```sql
SELECT e.tag
FROM jsonb_array_elements_text(
    '["java", "postgresql", "api"]'::jsonb
) AS e(tag);
```

`jsonb_array_elements_text` fits well when elements are strings and you want SQL text expressions.

### JSON data with different shapes

| Input JSONB | `jsonb_array_elements` |
|---|---|
| `'["a","b"]'::jsonb` | Two JSONB string rows. |
| `'[]'::jsonb` | 0 rows. |
| `NULL::jsonb` | 0 rows in a normal function call. |
| `'[null]'::jsonb` | One row containing **JSON null**. |
| `'{"a":1}'::jsonb` | Error: input is not an array. |
| `'null'::jsonb` | Error because it is a JSON scalar null, not SQL NULL or an array. |

**SQL `NULL` and JSON `null` are different.** A `jsonb` value holding JSON null is still a **JSON scalar**, not an empty array.

### With JSON arrays from the projects table

```sql
SELECT
    p.project_id,
    e.member
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL jsonb_array_elements(p.members)
     AS e(member)
ORDER BY p.project_id;
```

Alpha emits two objects; Beta produces zero rows because `members = []`; Gamma emits one object.

## 19. WITH ORDINALITY for JSON Arrays

When element order in a JSON array matters, use:

```sql
SELECT
    p.project_id,
    e.position,
    e.member ->> 'name' AS member_name,
    e.member ->> 'role' AS member_role
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL jsonb_array_elements(p.members)
     WITH ORDINALITY AS e(member, position)
  ON TRUE
ORDER BY p.project_id, e.position NULLS LAST;
```

Explanation:

- `jsonb_array_elements` turns each JSON object into a row.
- `WITH ORDINALITY` adds **`position` starting from 1** per array expansion.
- `->> 'name'` and `->> 'role'` extract properties as text.
- `LEFT JOIN LATERAL` preserves Beta even when `members` is empty.

Conceptual result:

| project_id | position | member_name | member_role |
|---:|---:|---|---|
| 1 | 1 | An | developer |
| 1 | 2 | Bình | reviewer |
| 2 | NULL | NULL | NULL |
| 3 | 1 | Chi | lead |

If the goal is **actual members only**, use `CROSS JOIN LATERAL` instead of `LEFT JOIN`.

### JSON string, SQL text, and JSON object

`jsonb_array_elements` returns `jsonb`. `->` extracts a value still as JSONB; `->>` returns text:

```sql
SELECT
    e.member -> 'name' AS as_jsonb,
    e.member ->> 'name' AS as_text
FROM jsonb_array_elements(
    '[{"name":"An"}]'::jsonb
) AS e(member);
```

Choose `->>` when comparing strings, displaying values, or mapping into text columns. For numeric fields, cast explicitly and validate input data.

## 20. jsonb_to_recordset: Expanding an Array of Objects into Typed Columns

`jsonb_array_elements()` returns one JSONB column per object. When you want multiple attributes exposed as typed SQL columns, `jsonb_to_recordset()` is very handy.

```sql
SELECT
    m.name,
    m.role
FROM jsonb_to_recordset(
    '[
       {"name":"An","role":"developer"},
       {"name":"Bình","role":"reviewer"}
     ]'::jsonb
) AS m(name text, role text)
ORDER BY m.name;
```

The syntax `AS m(name text, role text)` defines the columns:

- `m.name` of type `text`.
- `m.role` of type `text`.

### Using on each row of projects

```sql
SELECT
    p.project_id,
    p.project_name,
    m.name AS member_name,
    m.role AS member_role
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL jsonb_to_recordset(p.members)
     AS m(name text, role text)
  ON TRUE
ORDER BY p.project_id, m.name NULLS LAST;
```

For Beta with an empty array, both member columns receive `NULL` in the row preserved by `LEFT JOIN`.

### Missing keys and invalid types

If an object lacks a `role` key, the `role` column becomes SQL `NULL`. If you declare a field as `integer` while the JSON contains a string that cannot be cast to integer, PostgreSQL **raises a type-conversion error**.

Example reading `age`:

```sql
SELECT x.name, x.age
FROM jsonb_to_recordset(
    '[
       {"name":"An","age":25},
       {"name":"Bình","age":31}
     ]'::jsonb
) AS x(name text, age integer);
```

Columns are matched by the exact key names you declare; if the JSON uses `fullName` while you declare `name`, do not expect PostgreSQL to guess they mean the same thing.

### Beware inputs that are not arrays of objects

`jsonb_to_recordset` is designed for **JSON arrays of objects**. Passing a single JSON object, a scalar number, or an array of incompatible elements can fail. Validate JSON structure at application/database boundaries.

## 21. Protecting Queries When JSONB Shape May Be Invalid

The lab schema already includes:

```sql
CHECK (jsonb_typeof(members) = 'array')
```

That constraint plus `NOT NULL` guarantees `projects.members` is always a JSON array for accepted rows. For unvalidated external JSON data, check the type before calling an SRF that expects an array.

Fallback pattern:

```sql
SELECT
    jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(
                '{"name":"An"}'::jsonb
            ) = 'array'
            THEN '{"name":"An"}'::jsonb
            ELSE '[]'::jsonb
        END
    ) AS element;
-- 0 rows
```

In real queries, the JSON value should come from a column or parameter rather than an inline literal. `CASE` here guarantees the function receives a **JSON array** even when the input is an object or scalar.

Do not silently turn all malformed data into empty arrays. Depending on the contract, the application may need to **reject the input and log a validation error** instead of pretending there are no elements.

## 22. jsonb_each and jsonb_each_text: Expanding a JSON Object

Arrays and objects have different shapes. To generate rows from the **key/value pairs of a JSON object**, use `jsonb_each()`:

```sql
SELECT
    e.key,
    e.value
FROM jsonb_each(
    '{"db":"postgresql","language":"java"}'::jsonb
) AS e(key, value)
ORDER BY e.key;
```

The result has two rows. `value` has type `jsonb`.

If you want `value` as text:

```sql
SELECT
    e.key,
    e.value
FROM jsonb_each_text(
    '{"db":"postgresql","language":"java"}'::jsonb
) AS e(key, value)
ORDER BY e.key;
```

### JSON object key order is not business order

A JSON object should not be treated as an ordered list like a JSON array. When deterministic display by key is needed:

```sql
ORDER BY e.key
```

If you need to preserve the order in which a user entered items, design a **JSON array of positioned objects** or a relational child table with a `sort_order` column instead of relying on JSONB key order.

### Distinguish input shapes

- `jsonb_array_elements`: takes an **array**, emits each element.
- `jsonb_to_recordset`: takes an **array of objects**, emits typed columns.
- `jsonb_each`: takes an **object**, emits `key/value` rows.

Picking the wrong function for the input shape causes errors or unexpected results.

## 23. regexp_split_to_table and string_to_table: Splitting Strings into Rows

Not every multi-value input arrives as an array or JSON. For delimited strings, PostgreSQL provides functions that split into **multiple rows**.

### string_to_table

In PostgreSQL versions supporting this function:

```sql
SELECT t.token
FROM string_to_table('java,postgresql,api', ',')
     AS t(token);
```

Result:

```text
java
postgresql
api
```

`string_to_table` splits on a **literal delimiter string**, not a regex. It also has an optional variant handling null tokens depending on signature.

### regexp_split_to_table

If the delimiter is a **regex pattern**, use:

```sql
SELECT t.token
FROM regexp_split_to_table(
    'java ; postgresql, api',
    '\s*[,;]\s*'
) AS t(token);
```

The regular expression matches a comma or semicolon with optional whitespace on either side.

### Do not treat delimited strings as an ideal list model

If an actual value contains the delimiter (such as a product name `"A, B"`), naive string splitting corrupts the structure. When data is already in arrays or JSON, prefer **`unnest`/`jsonb_array_elements`** rather than converting to a string and splitting it again.

`regexp_split_to_table` is helpful for raw input with a fixed format, but it is no substitute for a CSV parser or a format with proper escaping.

## 24. Writing Your Own Set-Returning Functions in SQL

PostgreSQL lets you create SQL functions with `RETURNS SETOF <type>` or `RETURNS TABLE(...)`.

### 24.1. RETURNS TABLE: multiple named columns

Example function returning the most recent tasks for a project:

```sql
CREATE FUNCTION lesson_srf.recent_tasks(
    p_project_id BIGINT,
    p_limit INTEGER DEFAULT 2
)
RETURNS TABLE (
    task_id BIGINT,
    task_title TEXT,
    created_at TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        t.task_id,
        t.task_title,
        t.created_at
    FROM lesson_srf.tasks AS t
    WHERE t.project_id = p_project_id
    ORDER BY t.created_at DESC, t.task_id DESC
    LIMIT p_limit
$$;
```

Explanation:

- `p_project_id`: project parameter to filter on.
- `p_limit`: maximum task count; defaults to 2 here.
- `RETURNS TABLE` declares the three output columns and types.
- `LANGUAGE sql`: body is a SQL query.
- `STABLE`: indicates the function reads data and is expected to return consistent results per PostgreSQL snapshot/stability rules within a single statement, without assuming table data never changes.
- `ORDER BY ... LIMIT ...`: picks the newest tasks.

Call directly in `FROM`:

```sql
SELECT r.task_id, r.task_title, r.created_at
FROM lesson_srf.recent_tasks(1, 2) AS r
ORDER BY r.created_at DESC, r.task_id DESC;
```

### Purpose of ORDER BY inside the function vs. outer query

`ORDER BY ... LIMIT` inside the function chooses the right **top N tasks**. To display final result rows in the required order, the outer query should still include its **own `ORDER BY`**. Do not rely on a table function's output order remaining intact across joins and filters.

### Using the function in LEFT JOIN LATERAL

```sql
SELECT
    p.project_id,
    p.project_name,
    r.task_id,
    r.task_title
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL lesson_srf.recent_tasks(p.project_id, 2)
     AS r
  ON TRUE
ORDER BY p.project_id, r.created_at DESC NULLS LAST,
         r.task_id DESC;
```

Alpha returns two newest tasks; Beta returns one; Gamma still appears with `r.task_id IS NULL`. This shows a **user-defined function** working with `LATERAL` just like built-in SRFs.

### Functions accepting limits must be bounded

In real applications, do not let clients pass arbitrary or negative `p_limit` values without validation. Enforce bounds in the application or inside the function, and define how null, 0, and negative inputs behave. `LIMIT NULL` and `LIMIT 0` have very different meanings.

## 25. RETURNS SETOF: Returning Multiple Values of One Type

If a function returns only one `text` column, `RETURNS SETOF text` can be simpler than `RETURNS TABLE(tag text)`.

```sql
CREATE FUNCTION lesson_srf.project_tags(
    p_project_id BIGINT
)
RETURNS SETOF TEXT
LANGUAGE sql
STABLE
AS $$
    SELECT x.tag
    FROM lesson_srf.projects AS p
    CROSS JOIN LATERAL unnest(p.tags) AS x(tag)
    WHERE p.project_id = p_project_id
$$;
```

Call:

```sql
SELECT tag.value
FROM lesson_srf.project_tags(1) AS tag(value);
```

Returns three rows: java, postgresql, api. For project Gamma:

```sql
SELECT tag.value
FROM lesson_srf.project_tags(3) AS tag(value);
-- 0 rows
```

A function returning `SETOF` **does not mean returning a single array**. It returns **multiple rows** of type text. To get a single array, use an aggregate:

```sql
SELECT COALESCE(
    array_agg(tag.value ORDER BY tag.value),
    ARRAY[]::text[]
) AS tags
FROM lesson_srf.project_tags(1) AS tag(value);
```

### RETURNS SETOF composite type

A function can declare `RETURNS SETOF lesson_srf.tasks`, meaning each row matches the composite row type of the `tasks` table. That is convenient in some contexts, but it couples the function's API to table schema changes. For a clean, stable interface, `RETURNS TABLE(...)` usually makes the output column contract easier to control.

## 26. PL/pgSQL with RETURN QUERY

For logic requiring control flow, conditionals, or multiple steps, PostgreSQL allows `LANGUAGE plpgsql` functions to return sets with `RETURN QUERY`.

Example:

```sql
CREATE FUNCTION lesson_srf.tasks_by_status(
    p_status TEXT
)
RETURNS TABLE (
    task_id BIGINT,
    task_title TEXT
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.task_id,
        t.task_title
    FROM lesson_srf.tasks AS t
    WHERE t.status = p_status
    ORDER BY t.task_id;
END;
$$;
```

Call:

```sql
SELECT s.task_id, s.task_title
FROM lesson_srf.tasks_by_status('DOING') AS s
ORDER BY s.task_id;
```

Expected result: tasks 12 and 21.

### RETURN QUERY vs. RETURN NEXT

- **`RETURN QUERY SELECT ...`** appends multiple rows from a query's result.
- **`RETURN NEXT ...`** appends one row per call in an eligible `RETURNS SETOF` function.
- **`RETURN;`** ends function execution.

`RETURN QUERY` is not a `COMMIT` or `ROLLBACK`. Rows produced by the function still belong to the caller's query and transaction.

### Memory note for PL/pgSQL functions returning many rows

Some PL/pgSQL set-returning execution paths may **materialize results in a tuplestore before returning**, depending on PostgreSQL version and plan, rather than streaming infinitely in constant memory. Do not write a function returning millions of rows assuming `RETURN NEXT` has O(1) memory cost overall.

## 27. Functions Returning Untyped record

In PostgreSQL, a function declared `RETURNS SETOF record` can require a **column definition list** at the call site if the structure is not specified via a named type or output parameters.

Conceptual example:

```sql
-- Suppose a function returns SETOF record with two fields.
SELECT r.id, r.label
FROM some_record_function(...)
     AS r(id bigint, label text);
```

This only illustrates call syntax; `some_record_function` has not been created in this lesson.

Meanwhile, for a `RETURNS TABLE(task_id bigint, task_title text)` function, column names and types **are already declared at function creation**, so you normally just write:

```sql
SELECT x.task_id, x.task_title
FROM lesson_srf.tasks_by_status('DOING') AS x;
```

Do not arbitrarily attach a conflicting column-type list after the alias for a function that already has an explicit output signature; inspect the actual signature before writing the call.

## 28. ROWS and COST: Helping the Planner Estimate Custom SRFs

When PostgreSQL plans a query, it needs to **estimate how many rows a function returns** and **the cost of calling it**. For user-defined functions, authors can supply metadata:

- **`ROWS n`**: estimated number of rows returned per SRF invocation.
- **`COST n`**: estimated relative execution cost, depending on language and planner scaling.

Example:

```sql
CREATE FUNCTION lesson_srf.small_numbers(
    p_max INTEGER
)
RETURNS SETOF INTEGER
LANGUAGE sql
IMMUTABLE
ROWS 10
AS $$
    SELECT g.n
    FROM generate_series(1, p_max) AS g(n)
$$;
```

`ROWS 10` is an **estimate**, not a hard cap: calling `small_numbers(1000)` still returns 1,000 rows. Because this function's output depends solely on its argument, `IMMUTABLE` fits semantically.

### When estimates are far off

If the planner expects 10 rows when the function typically returns millions, it may choose a poor join order or join strategy, hurting performance.

For expensive SRFs:

1. Estimate typical row counts based on workload.
2. Update `ROWS`/`COST` when measured evidence warrants it.
3. Inspect `EXPLAIN (ANALYZE, BUFFERS)` to compare **estimated rows** against **actual rows**.
4. Consider replacing with inline SQL or set-based operations when appropriate.

Never treat `ROWS` as a safeguard against returning too much data. Limits must be enforced in **function/query logic and input validation**.

## 29. Volatility and PARALLEL SAFE: Declaring Function Properties Accurately

PostgreSQL supports volatility classifications for functions:

| Attribute | General meaning |
|---|---|
| **`IMMUTABLE`** | For identical arguments, result is expected never to change and not depend on database state, time zones, or context-dependent settings. |
| **`STABLE`** | Result is expected to stay consistent for identical arguments within a single statement per volatility rules; may read data without write side effects. |
| **`VOLATILE`** | Result can change across calls or have side effects; the planner must apply corresponding restrictions. |

`lesson_srf.project_tags(p_project_id)` reads the `projects` table, so it **cannot be labeled IMMUTABLE** just because the SQL body is short. If tags change after a commit, calling it later can return a different set of elements.

### Parallel execution safety

Custom functions can also be marked **`PARALLEL SAFE`**, `PARALLEL RESTRICTED`, or `PARALLEL UNSAFE` according to their behavior. Do not mark every SRF `PARALLEL SAFE` just hoping for faster plans:

- Review whether the function accesses non-parallel-safe resources, side effects, session state, or temporary objects.
- Mislabeling can cause errors or unexpected behavior during parallel queries.
- For PL/pgSQL and extension code, audit internal calls before applying the label.

These attributes are a **contract between the function and the optimizer/executor**, not decorative tags.

## 30. Performance: SRFs Can Multiply Rows Very Quickly

Suppose `projects` has 10,000 rows and each project averages 100 elements in `tags`:

```text
10,000 projects
       ×
100 tags per project
       │
       ▼
~1,000,000 rows after CROSS JOIN LATERAL unnest(tags)
```

If you then join a one-to-many `tasks` table, row counts multiply further. Therefore:

- **Filter parent rows first** when only a subset of projects is needed.
- Flatten only **required columns**.
- Never generate huge `generate_series` ranges from raw user input.
- Avoid joining multiple independent one-to-many sets simultaneously if each set can be aggregated separately.
- Place `LIMIT` at the right layer: an outer `LIMIT` usually caps **final rows**, not necessarily reducing work spent generating the entire inner set.
- Create appropriate indexes when using `LATERAL` subqueries for top-N per parent key.

### Index example for top-N tasks per project

```sql
CREATE INDEX ix_tasks_project_recent
ON lesson_srf.tasks(
    project_id,
    created_at DESC,
    task_id DESC
);
```

With the query:

```sql
SELECT
    p.project_id,
    t.task_id,
    t.created_at
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL (
    SELECT task_id, created_at
    FROM lesson_srf.tasks
    WHERE project_id = p.project_id
    ORDER BY created_at DESC, task_id DESC
    LIMIT 2
) AS t ON TRUE;
```

This index can help fetch top-N per `project_id` without scanning or sorting all tasks for a project, depending on statistics, row counts, and plan choice. Not every LATERAL query beats a window function; measure against real data.

## 31. EXPLAIN: Reading Plans for Functions in FROM

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    p.project_id,
    t.tag
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL unnest(p.tags) AS t(tag)
WHERE p.project_id = 1;
```

The plan may show nodes such as **Function Scan**, Nested Loop, or others depending on how PostgreSQL optimizes it. Things to observe:

1. **Actual rows** returned by the function.
2. Whether **estimated rows** are close to actual.
3. **Loops** on nodes executing the function.
4. Execution time, buffer I/O, and rows removed by filters.
5. Whether any source caused unexpected row multiplication.

`EXPLAIN ANALYZE` actually runs the query; the example above uses a read-only `SELECT` in the lab. For SRFs with side effects or write queries, exercise strict caution before running `EXPLAIN ANALYZE`.

### Comparing against not flattening

If you only want to know whether a project **has the tag `postgresql`**, `unnest` may be unnecessary:

```sql
SELECT
    p.project_id,
    'postgresql' = ANY(p.tags) AS has_postgresql
FROM lesson_srf.projects AS p
ORDER BY p.project_id;
```

Or use the array containment operator:

```sql
SELECT p.project_id
FROM lesson_srf.projects AS p
WHERE p.tags @> ARRAY['postgresql']::text[];
```

For certain array queries, an appropriate GIN index can accelerate containment lookups, whereas flattening every array and filtering afterward is not always efficient. **Do not use an SRF just because you can**; pick the operation that matches the problem.

## 32. SRFs in the SELECT List: Why Be Careful?

PostgreSQL does support SRFs in the `SELECT` list in appropriate contexts:

```sql
SELECT generate_series(1, 3);
```

However, this differs from scalar functions in several ways:

- Output row count can increase.
- With multiple SRFs in the same `SELECT`, element-pairing behavior follows modern PostgreSQL rules and should not be confused with an arbitrary Cartesian product.
- SRFs inside complex expressions face restrictions, especially in conditional constructs like `CASE`/`COALESCE`.
- Reading execution plans and understanding where row expansion occurs becomes harder.

### Write it explicitly in FROM

Replace:

```sql
SELECT generate_series(1, 3) AS n;
```

with:

```sql
SELECT s.n
FROM generate_series(1, 3) AS s(n);
```

These two simple queries have similar output. Putting it in `FROM`:

- Clarifies that the function is a **row source**, not a regular scalar expression.
- Allows assigning aliases and using `WITH ORDINALITY`.
- Combines cleanly with `CROSS JOIN`/`LEFT JOIN LATERAL`.
- Makes it obvious which parent rows disappear if the SRF returns 0 rows.

### SRFs cannot be placed arbitrarily in WHERE

Do not write:

```sql
-- Invalid placement of a set-returning function:
-- WHERE expects a boolean predicate,
-- not a row source from generate_series.
SELECT p.project_id
FROM lesson_srf.projects AS p
WHERE generate_series(1, 3) > 1;
```

If you want to filter values produced by an SRF, place the function in `FROM` and filter its column:

```sql
SELECT s.n
FROM generate_series(1, 3) AS s(n)
WHERE s.n > 1;
```

The result is 2 and 3.

## 33. Combining SRFs and Aggregates: Flatten Then Re-Aggregate

A common pattern is **expanding an array into rows**, transforming/filtering, and **aggregating back into a JSON array** per project.

```sql
SELECT
    p.project_id,
    COALESCE(
        jsonb_agg(
            upper(t.tag)
            ORDER BY t.position
        ) FILTER (WHERE t.position IS NOT NULL),
        '[]'::jsonb
    ) AS upper_tags
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags)
     WITH ORDINALITY AS t(tag, position)
  ON TRUE
GROUP BY p.project_id
ORDER BY p.project_id;
```

How it works:

1. `unnest` expands each `tags` array into rows.
2. `WITH ORDINALITY` preserves element positions.
3. `upper` transforms each tag.
4. `jsonb_agg(... ORDER BY t.position)` packs them back into a JSON array in original order.
5. `FILTER` drops the null-extended row from `LEFT JOIN`.
6. `COALESCE` gives Gamma an empty JSON array `[]`.

### Why not call aggregate(SRF(...)) directly?

A common mistake is writing:

```sql
-- Invalid: aggregates cannot directly wrap an SRF call
-- as an argument this way.
SELECT array_agg(unnest(tags))
FROM lesson_srf.projects;
```

PostgreSQL raises **`aggregate function calls cannot contain set-returning function calls`** and suggests using `LATERAL` in `FROM`.

Correct approach:

```sql
SELECT array_agg(t.tag ORDER BY p.project_id, t.position)
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL unnest(p.tags)
     WITH ORDINALITY AS t(tag, position);
```

Move the SRF to be a **row source in `FROM`**, then pass **the source's column** to the aggregate as usual.

## 34. Using LATERAL to Avoid Redundant Work in Queries

Suppose you need both the tag count and the tag list per project. If you only need properties from a single array, you can read `cardinality(tags)` directly without flattening:

```sql
SELECT
    p.project_id,
    cardinality(p.tags) AS tag_count,
    p.tags
FROM lesson_srf.projects AS p;
```

When you need per-tag processing (filtering, transforming, joining), an SRF makes sense. However, if you only write:

```sql
SELECT
    p.project_id,
    COUNT(t.tag)
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags) AS t(tag)
  ON TRUE
GROUP BY p.project_id;
```

you created extra rows merely to count them, and `COUNT(t.tag)` still ignores real null elements. Do not treat flattening as the default; **functions operating directly on the array** can be simpler and faster.

A case that genuinely requires LATERAL is **filtering elements and joining them to a lookup table**. There, use `unnest` with ordinality, join keys, and proper filters.

## 35. Common Errors and How to Diagnose Them

| Symptom | Common cause | Fix |
|---|---|---|
| Projects with empty arrays vanish | `CROSS JOIN LATERAL` with an SRF returning 0 rows. | If projects must be kept, use `LEFT JOIN LATERAL ... ON TRUE`. |
| Count is 1 instead of 0 for empty arrays | `COUNT(*)` counts the outer join's null-extended row. | Use `COUNT(position)` from `WITH ORDINALITY` or `cardinality(tags)`. |
| Elements after join are out of order | Missing `ORDER BY` at the end of the query. | Use `WITH ORDINALITY` and `ORDER BY position`. |
| A JSON value errors "cannot extract elements" | Input is not a valid JSON array. | Validate `jsonb_typeof`/schema, or handle invalid input errors. |
| `record` columns missing or untyped | Output columns of the recordset were not declared. | Add `AS x(name text, age integer)` matching the signature. |
| Error referencing left source column in derived table | Missing `LATERAL` for subquery in `FROM`. | Use `LEFT/CROSS JOIN LATERAL` and valid aliases. |
| More rows than expected | `CROSS JOIN` or SRF emitting multiple elements per row. | Verify cardinality early, filter, or limit. |
| Multi-unnest produces NULL on shorter arrays | Multi-argument `unnest` zips positionally and pads with null. | Validate input array lengths. |
| `ROWS FROM` gives different row count than `CROSS JOIN` | The two constructs have different combination semantics. | Pick positional zip vs. Cartesian product deliberately. |
| Query is slow on large data | SRF expands huge row counts or lateral subquery scans repeatedly. | Filter parent rows, add indexes, cap ranges, inspect `EXPLAIN`. |
| User-defined function gets a poor plan | Estimated `ROWS`/`COST` diverges from reality. | Measure actual rows and adjust metadata or SQL. |
| `array_agg(unnest(...))` errors | Aggregate directly contains an SRF argument. | Move `unnest` into `FROM` and call `array_agg(t.value)`. |

### Where to start diagnosing?

1. Confirm function arguments have the exact **PostgreSQL types** expected (`text[]`, `jsonb`, timestamp...).
2. Call the SRF **standalone** on a concrete sample input to check row count and column names:

   ```sql
   SELECT *
   FROM unnest(ARRAY['java', 'sql']::text[]) AS x(tag);
   ```

3. Count rows at each source before adding complex joins.
4. With `LATERAL`, inspect the left source and how many rows the SRF emits **per parent row**.
5. Verify whether empty entities should be kept or dropped.
6. Run `EXPLAIN (ANALYZE, BUFFERS)` in an appropriate environment when diagnosing performance.

Do not assume a query is right merely because it runs without errors: **an SRF returning fewer or more rows than expected can silently corrupt reports**.

## 36. Java/JDBC: Consuming SRF Results Like a Standard ResultSet

From a Java application's perspective, an SRF placed in `FROM` produces rows and columns read via `ResultSet` just like a table query.

```java
String sql = """
    SELECT
        p.project_id,
        x.position,
        x.tag
    FROM lesson_srf.projects AS p
    CROSS JOIN LATERAL unnest(p.tags)
         WITH ORDINALITY AS x(tag, position)
    WHERE p.project_id = ?
    ORDER BY x.position
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1L);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long projectId = rs.getLong("project_id");
            long position = rs.getLong("position");
            String tag = rs.getString("tag");

            // Process each tag row in the requested order.
        }
    }
}
```

This is a Java text-block illustration; it assumes a valid `Connection connection`, imports, and `SQLException` handling.

### When LEFT JOIN makes the position column NULL

With `LEFT JOIN LATERAL`, empty project rows have `x.position = NULL`. `ResultSet.getLong()` returns 0 for SQL NULL, so call `rs.wasNull()` to distinguish it.

Example:

```java
long position = rs.getLong("position");
if (rs.wasNull()) {
    // Parent row has no elements from the SRF.
} else {
    // position is the real element order.
}
```

### Use placeholders for values, not function or table names

`PreparedStatement` binds **value** parameters:

```sql
SELECT n
FROM generate_series(1, ?) AS g(n);
```

Never use `?` for function names, schema names, or table names. If the application chooses what to flatten based on user input, map that input to an allowlisted set of functions/queries—never interpolate arbitrary function names from an HTTP request into SQL.

## 37. Security When Defining and Calling Set-Returning Functions

User-defined functions execute under PostgreSQL privilege settings:

- **`SECURITY INVOKER`** (typical default): executes with the caller's privileges per function rules.
- **`SECURITY DEFINER`**: executes with the function owner's privileges under applicable rules.

If a `SECURITY DEFINER` function returns rows from sensitive tables, the author must lock down **`EXECUTE` privileges**, inputs, and `search_path`. A set-returning function can expose **many rows**, carrying higher exposure risk than a scalar function returning a small status code.

### Design rules

1. Do not use `SECURITY DEFINER` without a clear need.
2. On privileged functions, set a safe `search_path` and use **schema-qualified names** for key tables and functions.
3. Never grant `CREATE` to untrusted roles on schemas searched via `search_path`.
4. Enforce tenant checks, role checks, and filters **inside** the function when the function acts as a data boundary.
5. Never rely on query aliases or client-supplied `WHERE` clauses as a security boundary.
6. Be cautious with SRFs calling extensions/network or having side effects; the planner may evaluate expressions differently from a simple Java loop.

Simply being invoked from a `SELECT` does not guarantee a function is harmless: a `VOLATILE` function can perform other actions depending on privileges and implementation.

## 38. When Should You Use an SRF in FROM?

| Problem | Typical usage | Notes |
|---|---|---|
| Generate number series for report scaffolding | `generate_series(1, N)` | Bound N if supplied by clients. |
| Generate date list | `generate_series(start_ts, end_ts, interval)` | Watch timezone/DST and inclusive endpoint. |
| Flatten array into rows | `unnest(array_col)` | Empty array returns 0 rows. |
| Preserve array element positions | `unnest(...) WITH ORDINALITY` | Add `ORDER BY position` for display. |
| Access actual array subscripts | `generate_subscripts(arr, 1)` | Differs from ordinality if array lower bound is not 1. |
| Flatten JSON array | `jsonb_array_elements(...)` | Input must be an array. |
| Flatten JSON array of objects into columns | `jsonb_to_recordset(...) AS x(...)` | Declare explicit column types. |
| Flatten JSON object key/value pairs | `jsonb_each(...)` | Do not rely on object key order. |
| Split delimited strings into rows | `string_to_table`, `regexp_split_to_table` | Delimiter contract must be well-defined. |
| Parent row with multiple child elements | `CROSS JOIN LATERAL SRF(parent.col)` | Parents with 0 elements are dropped. |
| Keep all parent rows | `LEFT JOIN LATERAL ... ON TRUE` | Parents with 0 elements keep one row with null SRF columns. |
| Top-N related records per entity | `LEFT JOIN LATERAL (SELECT ... LIMIT N)` | Indexes on parent key + sort key can help. |
| Business logic returning multiple rows | `RETURNS TABLE`/`RETURNS SETOF` | Design signature, privileges, and cardinality. |

Use an SRF when **turning a structured value or generation rule into relational rows** brings clear value. If the question is simply "does the array contain X?" or "how many elements are in the array?", direct array operators/functions are clearer and often faster.

## 39. Practice Exercises

### Exercise 1 — Generating ascending, descending, and empty sequences

Write three queries using `generate_series` in `FROM` producing:

1. 1, 2, 3, 4, 5.
2. 10, 8, 6, 4, 2.
3. An empty sequence due to mismatched step direction.

Explain why a step of 0 causes an error and why `stop` is included when the step lands on it exactly.

### Exercise 2 — Generating a date scaffold

Use `generate_series(timestamp, timestamp, interval '1 day')` to generate dates from **2026-11-10 to 2026-11-16**. Cast the result to `date`, name the column `report_day`, and sort by date. Explain the risk of assuming every local calendar day is 24 hours long.

### Exercise 3 — Flattening the tags array

On `lesson_srf.projects`, write a query returning `project_id`, `project_name`, and one `tag` per row using `CROSS JOIN LATERAL unnest(tags)`. Predict whether Gamma appears.

### Exercise 4 — Keeping empty projects

Modify Exercise 3 to use `LEFT JOIN LATERAL ... ON TRUE` so Gamma is still returned. What value does `tag` have for Gamma and why?

### Exercise 5 — Element order

Use `WITH ORDINALITY` to return Alpha's tags along with `position`. Sort by `ORDER BY position`. If a user prepends a new tag to the front of the array, how do the positions change?

### Exercise 6 — COUNT(*) vs. COUNT(position)

With `LEFT JOIN LATERAL unnest(tags) WITH ORDINALITY`, compute both `COUNT(*)` and `COUNT(position)` per project. Explain why Gamma gets 1 in the first column but 0 in the second.

### Exercise 7 — generate_subscripts

Create the array `'[0:2]={10,20,30}'::integer[]`. Use `generate_subscripts(array,1)` to get actual subscripts, then use `unnest(...) WITH ORDINALITY`. Compare the two sets of index numbers.

### Exercise 8 — Two arrays paired by position

Compare:

```sql
FROM unnest(
    ARRAY[10,20,30],
    ARRAY['A','B']
) AS x(id,label)
```

with:

```sql
FROM unnest(ARRAY[10,20,30]) AS ids(id)
CROSS JOIN unnest(ARRAY['A','B']) AS labels(label)
```

Count the rows and explain which position gets null-padded in the first case.

### Exercise 9 — ROWS FROM

Use `ROWS FROM (generate_series(1,4), unnest(ARRAY['x','y'])) WITH ORDINALITY`. Predict the row count, ordinal positions, and where nulls are padded.

### Exercise 10 — Expanding the members JSON array

Use `jsonb_array_elements(p.members)` on the `projects` table. Return `project_id`, `name`, and `role` of each member using `->>`. Analyze the difference between `CROSS JOIN` and `LEFT JOIN` for Beta.

### Exercise 11 — jsonb_to_recordset

Write `jsonb_to_recordset` for:

```json
[
  {"name":"An","age":25},
  {"name":"Bình","age":31}
]
```

Declare two columns `name text`, `age integer`. If an element omits `age`, what value does the column get? If `age` is a string that cannot be parsed as a number, what happens?

### Exercise 12 — Distinguishing SQL NULL and JSON null

Compare the results and possible errors when calling:

```sql
jsonb_array_elements(NULL::jsonb)
jsonb_array_elements('[]'::jsonb)
jsonb_array_elements('[null]'::jsonb)
jsonb_array_elements('null'::jsonb)
```

Explain why the third case yields one JSON null element while the fourth case is not a valid JSON array.

### Exercise 13 — Top 2 tasks per project

Write `LEFT JOIN LATERAL` to fetch the two newest tasks per project ordered by `created_at DESC, task_id DESC`. Explain why Gamma still appears and why `task_id` is needed as a tie-breaker.

### Exercise 14 — RETURNS TABLE function

Define a SQL function taking `project_id` and returning `task_id`, `task_title` for tasks with `status='DOING'`. Use `RETURNS TABLE`, name columns clearly, and invoke it in `FROM`.

### Exercise 15 — RETURNS SETOF function

Write a `RETURNS SETOF text` function returning the tags of a project. For project Gamma, predict the row count when calling the function standalone, with `CROSS JOIN LATERAL`, and with `LEFT JOIN LATERAL`.

### Exercise 16 — RETURN QUERY in PL/pgSQL

Write a `LANGUAGE plpgsql` function taking `p_status` and executing `RETURN QUERY SELECT` for matching tasks. Explain the difference between `RETURN QUERY`, `RETURN NEXT`, and `RETURN;`.

### Exercise 17 — Flatten then re-aggregate

Use `LEFT JOIN LATERAL unnest(tags) WITH ORDINALITY` and `jsonb_agg(upper(tag) ORDER BY position)` to return a JSON array of uppercase tags per project. What results do Beta and Gamma get? Use `FILTER` and `COALESCE('[]'::jsonb)`.

### Exercise 18 — Measuring row counts and performance

Suppose there are 100,000 projects, each averaging 50 tags. Estimate the row count after `CROSS JOIN LATERAL unnest(tags)` if every project has tags. Describe how to inspect this with `EXPLAIN (ANALYZE, BUFFERS)` and how to reduce generated rows.

### Exercise 19 — Choosing when an SRF is unnecessary

For the question "Which projects have the `postgresql` tag?", compare:

```sql
WHERE 'postgresql' = ANY(tags)
```

against `CROSS JOIN LATERAL unnest(tags)` followed by `WHERE tag = 'postgresql'`. Contrast row counts, duplicate-row risk, and ability to use array operators/indexes.

### Exercise 20 — Name scope and security

A Java application lets clients pass an arbitrary function name directly to execute in `FROM`, while that function is defined with `SECURITY DEFINER`. Point out the risks, and recommend an allowlist of functions, `EXECUTE` controls, `search_path`, and row-count limits.

## Conclusion

**Set-returning functions (SRFs)** bridge structured values or generative rules with **SQL's row–column model**. In PostgreSQL, placing a function in **`FROM`** lets its output take an alias, participate in `JOIN`, `WHERE`, and `GROUP BY`, and behave as a relational source. `generate_series` generates numbers/dates; `unnest` and `generate_subscripts` handle arrays; `jsonb_array_elements`, `jsonb_to_recordset`, and `jsonb_each` expand JSON into rows; `ROWS FROM` aligns multiple table functions positionally.

The most important takeaway is **cardinality and `LATERAL`**: an SRF can return **0..N rows per source row**. `CROSS JOIN LATERAL` fits when only real elements are wanted; `LEFT JOIN LATERAL ... ON TRUE` retains entities with zero elements. `WITH ORDINALITY` preserves element positions when expanding arrays or JSON arrays, yet guaranteeing final output order still requires **`ORDER BY`**.

For advanced usage, you can define `RETURNS SETOF`/`RETURNS TABLE` and use `RETURN QUERY` in PL/pgSQL. However, always design **column types, stability, permissions, row bounds, NULL behavior, and execution cost** explicitly. Do not flatten millions of elements when a direct array check suffices, do not assume an SRF always returns one row, and do not treat `ROWS` metadata as a hard limit. Used properly, SRFs make PostgreSQL queries **flexible, clear about data sources, semantically safe, and easy to optimize**.
