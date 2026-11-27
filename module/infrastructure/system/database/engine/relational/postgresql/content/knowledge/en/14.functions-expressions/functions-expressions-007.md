# Row Comparisons, Arrays, and ANY or ALL Operators in PostgreSQL

When filtering data in SQL, comparisons are not limited to a single column against a single value. An application may need to compare **key pairs** like `(department, grade)`, check whether a skill is inside an **array**, or verify that an employee's score is **greater than every** benchmark in a list. PostgreSQL supports three groups of tools that look similar syntactically yet carry distinct meanings:

- **Row constructor comparisons:** compare tuples position by position, such as `ROW(2, 18000000) < ROW(3, 10000000)`.
- **Array comparisons and operators:** work with `integer[]`, `text[]`, testing equality, containment, overlap, and unnesting elements.
- **`ANY` / `SOME` and `ALL`:** apply a comparison operator between a value and **each element of an array or each row returned by a subquery**, then combine the outcomes as "at least one" or "all."

The critical detail is that **`NULL`, empty arrays, and empty subsets have distinct semantics**. For example, `2 = ANY(ARRAY[1, NULL])` does not return `FALSE`—it returns `NULL`; `2 = ANY('{}'::integer[])` returns `FALSE`; while `2 = ALL('{}'::integer[])` returns `TRUE`. With `NOT IN`, a single `NULL` in the comparison set can cause a query to exclude rows the author expected to keep.

This lesson explains these rules with a hands-on PostgreSQL dataset, queries with expected outputs, performance/index exercises, and notes on calling SQL from Java/JDBC.

## 1. Objectives and Concept Map

After this lesson, you will be able to:

1. Write `ROW(...)` or `(a, b)` to compare multiple columns and understand **left-to-right lexicographic comparison**.
2. Distinguish `=`, `<>`, `<`, `>`, `IS DISTINCT FROM`, and `IS NULL` checks on row constructors.
3. Create, index into, compare, and unnest PostgreSQL arrays of a defined element type.
4. Use `@>`, `<@`, and `&&` for membership/set questions, without confusing them with array equality.
5. Use `= ANY(array)`, `<> ALL(array)`, `> ALL(subquery)`, and `< ANY(subquery)` accurately.
6. Distinguish `FALSE` from `NULL` when an array contains `NULL` elements, the array itself is `NULL`, or the array is empty.
7. Avoid the `NOT IN` trap and choose `NOT EXISTS` when appropriate, especially with nullable data.
8. Know when a B-tree or GIN index helps and when to move from arrays to a relational junction table.

~~~text
ROW(a, b)                  ARRAY[1, 2, 3]          x = ANY(array)
    |                             |                      |
    v                             v                      v
compare position by position  ordered elements       compare x to each element
    |                             |                      |
    v                             v                      v
lexicographic / NULL         =, @>, <@, &&         TRUE/FALSE/UNKNOWN
~~~

**These three constructs are not interchangeable:** a row holds **positions with different meanings** (such as department and grade); an array typically holds **multiple values of the same type**; `ANY`/`ALL` are **quantifiers over a comparison**, not a data structure.

## 2. Practice Dataset

Create a dedicated schema in a **study database**. Never run schema-creation or seed scripts on an environment with real data. If `expr_lab_180` already exists, pick a different lab name rather than deleting existing data.

### 2.1. Employees Table with an Array Column

~~~sql
CREATE SCHEMA expr_lab_180;

CREATE TABLE expr_lab_180.employees (
    employee_id BIGINT PRIMARY KEY,
    employee_name TEXT NOT NULL,
    department TEXT NOT NULL,
    grade INTEGER NULL,
    salary NUMERIC(12, 2) NULL,
    skills TEXT[] NULL,

    CONSTRAINT employee_grade_check
        CHECK (grade BETWEEN 1 AND 5),
    CONSTRAINT employee_salary_check
        CHECK (salary >= 0)
);
~~~

`skills TEXT[]` stores an array of skills. The column allows `NULL` to distinguish:

- **NULL array:** skill list is unknown.
- **Empty array `{}`:** list is confirmed to have zero elements.
- **Array with a NULL element:** some elements are known, while one position is unknown.

Those states are not identical, even if a UI renders them similarly.

### 2.2. Insert Ten Employees

~~~sql
INSERT INTO expr_lab_180.employees
    (employee_id, employee_name, department, grade, salary, skills)
VALUES
    (1,  'An',   'ENG',   2, 18000000, ARRAY['sql', 'postgres', 'java']),
    (2,  'Bình', 'ENG',   3, 25000000, ARRAY['sql', 'python']),
    (3,  'Chi',  'OPS',   1, 12000000, ARRAY['linux', 'postgres']),
    (4,  'Dũng', 'OPS',   NULL, NULL,   ARRAY[]::text[]),
    (5,  'Hà',   'SALES', 2, 16000000, ARRAY['crm', 'excel']),
    (6,  'Khôi', 'ENG',   2, 20000000, ARRAY['sql', NULL::text, 'kafka']),
    (7,  'Lan',  'ENG',   1, 14000000, NULL::text[]),
    (8,  'Minh', 'SALES', NULL, 13000000, ARRAY['crm']),
    (9,  'Nga',  'QA',    1, 11000000, ARRAY[]::text[]),
    (10, 'Phúc', 'RND',   1, 21000000, NULL::text[]);
~~~

For employee 6, the array has three positions where **the second position is `NULL`**. Employees 4 and 9 have **empty arrays**, while employees 7 and 10 have **`NULL` arrays**.

### 2.3. Rules Table Containing Allowed Grade Arrays

~~~sql
CREATE TABLE expr_lab_180.department_rules (
    department TEXT PRIMARY KEY,
    allowed_grades INTEGER[] NULL
);

INSERT INTO expr_lab_180.department_rules
    (department, allowed_grades)
VALUES
    ('ENG', ARRAY[1, 2, 3]),
    ('OPS', ARRAY[1, 2]),
    ('SALES', ARRAY[2, 3]),
    ('QA', ARRAY[]::integer[]),
    ('RND', NULL::integer[]);
~~~

Exercise conventions:

- ENG allows grades `1, 2, 3`.
- OPS allows grades `1, 2`.
- SALES allows grades `2, 3`.
- QA has an **empty** list (no grade is allowed per this list).
- RND has an **unknown** list (`NULL`), distinct from QA.

### 2.4. Rules Table by Column Pairs

~~~sql
CREATE TABLE expr_lab_180.eligible_pairs (
    department TEXT NOT NULL,
    grade INTEGER NOT NULL,
    CONSTRAINT eligible_pairs_pk
        PRIMARY KEY (department, grade)
);

INSERT INTO expr_lab_180.eligible_pairs
    (department, grade)
VALUES
    ('ENG', 2),
    ('ENG', 3),
    ('OPS', 1),
    ('SALES', 2);
~~~

This illustrates a **relationship between two values**: the same grade 2 is not allowed in every department; the pair `('ENG', 1)` is not in `eligible_pairs` even though grade 1 is valid elsewhere.

### 2.5. Inspect the Data

~~~sql
SELECT
    employee_id,
    employee_name,
    department,
    grade,
    salary,
    skills
FROM expr_lab_180.employees
ORDER BY employee_id;
~~~

| ID | Department | Grade | Salary | Skills Array State |
| ---: | --- | ---: | ---: | --- |
| 1 | ENG | 2 | 18,000,000 | `{sql,postgres,java}` |
| 2 | ENG | 3 | 25,000,000 | `{sql,python}` |
| 3 | OPS | 1 | 12,000,000 | `{linux,postgres}` |
| 4 | OPS | `NULL` | `NULL` | `{}` |
| 5 | SALES | 2 | 16,000,000 | `{crm,excel}` |
| 6 | ENG | 2 | 20,000,000 | Has `sql`, `NULL`, `kafka` |
| 7 | ENG | 1 | 14,000,000 | `NULL` (unknown array) |
| 8 | SALES | `NULL` | 13,000,000 | `{crm}` |
| 9 | QA | 1 | 11,000,000 | `{}` |
| 10 | RND | 1 | 21,000,000 | `NULL` |

In this table, `NULL` in grade/salary/skills must be interpreted per column. SQL does not treat a `NULL` grade as 0 or a `NULL` array as empty.

## 3. Row Constructors: A Row of Multiple Fields

PostgreSQL lets you construct a row value:

~~~sql
SELECT
    ROW('ENG', 2) AS explicit_row,
    ('ENG', 2) AS implicit_row,
    pg_typeof(ROW('ENG', 2)) AS row_type;
~~~

In appropriate syntactic contexts, both `ROW('ENG', 2)` and `('ENG', 2)` construct a two-field row. Each **position** has its own meaning: position 1 is department code, position 2 is grade.

~~~text
ROW('ENG', 2)
     |     |
     |     +-- position 2: grade
     +-------- position 1: department
~~~

A row constructor can hold mixed types:

~~~sql
SELECT ROW(
    1::bigint,
    'An'::text,
    DATE '2026-11-14',
    TRUE
) AS person_snapshot;
~~~

This is not an array: PostgreSQL arrays hold elements of **the same element type**; a row can combine `bigint`, `text`, `date`, and `boolean` in one value.

### 3.1. Rows Can Be Used in Comparisons

~~~sql
SELECT
    ROW(1, 2) = ROW(1, 2) AS equal_rows,
    ROW(1, 2) <> ROW(1, 3) AS different_rows,
    ROW(1, 2) < ROW(1, 3) AS less_than,
    ROW(2, 1) > ROW(1, 999) AS greater_than;
~~~

All four results are **`TRUE`**.

PostgreSQL supports compatible B-tree comparison operators for each pair of fields in a row, commonly `=`, `<>`, `<`, `<=`, `>`, and `>=`. Corresponding field types must have compatible comparison operators; you cannot compare two rows with different numbers of fields and expect PostgreSQL to fill missing values.

### 3.2. Comparing Column Pairs in a Table

~~~sql
SELECT
    employee_id,
    department,
    grade,
    (department, grade) = ('ENG', 2)
        AS is_engineer_grade_two
FROM expr_lab_180.employees
ORDER BY employee_id;
~~~

Employees **1** and **6** have `('ENG', 2)` so the expression evaluates to `TRUE`. Employees with `grade NULL` can return `NULL` instead of `FALSE` depending on the remaining column and comparison, as shown next.

### 3.3. When to Use a Pair Instead of Two AND Conditions?

The two conditions:

~~~sql
WHERE department = 'ENG'
  AND grade = 2
~~~

and:

~~~sql
WHERE (department, grade) = ('ENG', 2)
~~~

express the same column-wise equality in normal cases. Row syntax is particularly helpful when:

- Comparing **composite keys**;
- Filtering on **multi-column ordering**;
- Using `IN` with a list of tuples;
- Implementing multi-column keyset pagination.

You do not have to convert every `AND` pair into a row; choose whichever form is clearest to read and friendly to the planner and indexes.

## 4. Equality and Inequality Between Two Rows

For row constructors, `=` and `<>` follow special `NULL` rules:

- `row_a = row_b` is `TRUE` when **all** corresponding field pairs are **non-NULL and equal**.
- `row_a = row_b` is `FALSE` when **at least one** field pair is non-NULL and **not equal**.
- If no pair proves inequality yet at least one pair contains `NULL`, the result is **`NULL`/UNKNOWN**.
- `row_a <> row_b` is `TRUE` when a pair is non-NULL and unequal; `FALSE` when all pairs are non-NULL and equal; otherwise `NULL`.

### 4.1. Examples with NULL Fields

~~~sql
SELECT
    ROW(1, NULL::integer) = ROW(1, NULL::integer)
        AS equal_with_unknown,
    ROW(1, NULL::integer) = ROW(2, NULL::integer)
        AS proven_different,
    ROW(1, NULL::integer) <> ROW(2, NULL::integer)
        AS not_equal_proven,
    ROW(1, NULL::integer) <> ROW(1, NULL::integer)
        AS not_equal_unknown;
~~~

Results:

| Expression | Result |
| --- | --- |
| `ROW(1,NULL) = ROW(1,NULL)` | `NULL` |
| `ROW(1,NULL) = ROW(2,NULL)` | `FALSE` |
| `ROW(1,NULL) <> ROW(2,NULL)` | `TRUE` |
| `ROW(1,NULL) <> ROW(1,NULL)` | `NULL` |

In the second row, the first field `1 <> 2` suffices to prove the two rows **differ**, even though the second field is `NULL`.

### 4.2. Using IS [NOT] DISTINCT FROM for NULL-Safe Comparisons

When you need a definite boolean result, use `IS DISTINCT FROM` or `IS NOT DISTINCT FROM`:

~~~sql
SELECT
    ROW(1, NULL::integer)
        IS NOT DISTINCT FROM
    ROW(1, NULL::integer) AS same_nullable_values,

    ROW(1, NULL::integer)
        IS DISTINCT FROM
    ROW(1, 2) AS different_nullable_values,

    ROW(1, NULL::integer)
        IS DISTINCT FROM
    ROW(2, NULL::integer) AS different_first_field;
~~~

All results are **`TRUE`**.

`IS NOT DISTINCT FROM` treats two corresponding `NULL` values as **not distinct** for comparison purposes. This is ideal for asking "did two nullable field tuples change?", such as before/after record auditing:

~~~sql
-- Conceptual record comparison example:
-- WHERE (old_value, old_note)
--       IS DISTINCT FROM
--       (new_value, new_note)
~~~

Distinguish `IS NOT DISTINCT FROM` from `=`: they have different `NULL` semantics.

## 5. Row IS NULL and IS NOT NULL Are Not Simple Opposites

A very surprising case in PostgreSQL is a **row with some NULL and some non-NULL fields**.

Under row constructor test semantics:

- `row IS NULL` is `TRUE` when the row itself is NULL **or all of its fields are NULL**.
- `row IS NOT NULL` is `TRUE` when the row itself is not NULL **and all of its fields are non-NULL**.
- For a row with **some NULL fields and some non-NULL fields**, **both expressions evaluate to `FALSE`**.

~~~sql
SELECT
    ROW(NULL::integer, NULL::text) IS NULL
        AS all_fields_null,
    ROW(1, NULL::text) IS NULL
        AS partially_null_row_is_null,
    ROW(1, NULL::text) IS NOT NULL
        AS partially_null_row_is_not_null,
    ROW(1, 'ok'::text) IS NOT NULL
        AS all_fields_present;
~~~

Results:

| Expression | Result |
| --- | --- |
| Both fields NULL, `IS NULL` | `TRUE` |
| One non-NULL, one NULL, `IS NULL` | `FALSE` |
| One non-NULL, one NULL, `IS NOT NULL` | `FALSE` |
| Both fields non-NULL, `IS NOT NULL` | `TRUE` |

**Never assume every row satisfies either `IS NULL` or `IS NOT NULL`.** When checking individual columns, if you mean "a specific field is missing," write `grade IS NULL`; if you mean "any field is missing," write explicit conditions or `NOT (ROW(...) IS NOT NULL)` as appropriate.

### 5.1. Note on Row Constructors vs. Composite-Type Values

PostgreSQL has both **row constructors** and **composite type values** (named row types, e.g., via `CREATE TYPE`). In some composite comparison contexts used for sorting and indexing, PostgreSQL handles NULL fields differently from row constructor expressions in SQL.

Therefore, **do not assume every record/composite comparison has identical NULL behavior** simply because they look like "a row." This lesson focuses on `ROW(...)` row constructor syntax; when storing arrays of composite types or indexing composite columns, check the specific type semantics in PostgreSQL documentation.

## 6. Lexicographic Ordering Comparisons on Rows

`<`, `<=`, `>`, and `>=` on row constructors perform **left-to-right comparison**, just like a dictionary (*lexicographic order*):

1. Compare the first pair of fields.
2. If the first two fields **differ** and determine order, stop and decide immediately.
3. If equal, move to the next pair of fields.
4. If the deciding pair contains an incomparable `NULL`, the result can be `NULL`.

### 6.1. Earlier Fields Outweigh Later Fields

~~~sql
SELECT
    ROW(1, 999) < ROW(2, 0) AS first_field_decides,
    ROW(2, 10) < ROW(2, 20) AS second_field_decides,
    ROW(3, 0) > ROW(2, 999999) AS larger_first_field;
~~~

All three are **`TRUE`**. In the first example, `999` is greater than `0`, yet it has no effect because the first field pair `1 < 2` already decided the comparison.

### 6.2. NULL Only Affects the Result When That Field Is Reached

~~~sql
SELECT
    ROW(1, NULL::integer) < ROW(2, 0)
        AS decided_before_null,
    ROW(1, NULL::integer) < ROW(1, 9)
        AS needs_unknown_field;
~~~

Results:

- `decided_before_null = TRUE` because `1 < 2` already decided it.
- `needs_unknown_field = NULL` because the first fields are equal and the second pair contains `NULL`.

**Do not think of row comparison as comparing every column and ANDing the `<` results.** It is prioritized lexicographic comparison, not requiring every left field to be less than every right field.

### 6.3. Application: Keyset Pagination

Suppose there is an events table:

~~~sql
-- Hypothetical schema example:
-- events(event_id BIGINT PRIMARY KEY,
--        occurred_at TIMESTAMPTZ NOT NULL, ...)
~~~

To fetch the next page after a cursor in ascending order:

~~~sql
SELECT
    event_id,
    occurred_at
FROM events
WHERE (occurred_at, event_id) >
      (TIMESTAMPTZ '2026-11-14 09:30:00+07', 1000::bigint)
ORDER BY occurred_at ASC, event_id ASC
LIMIT 50;
~~~

Semantically this equals:

~~~sql
WHERE occurred_at > :last_time
   OR (occurred_at = :last_time AND event_id > :last_id)
~~~

when both sort columns are **NOT NULL** and both sort ascending. `event_id` acts as a unique tie-breaker so events sharing the same timestamp have a deterministic order.

**Important conditions to remember:**

- `ORDER BY` and the tuple comparison must use the **exact same column order**.
- For descending order, use `<` instead of `>`; mixing ASC/DESC requires the corresponding expanded condition rather than flipping a single operator mechanically.
- If sort keys are nullable, handle `NULLS FIRST/LAST` and NULL logic explicitly.
- A matching B-tree index such as `(occurred_at, event_id)` supports keyset pagination well.
- Data changing between page fetches can still affect consistency depending on snapshot/transaction isolation.

## 7. Row IN: Testing Whether a Tuple Belongs to a Tuple List

Instead of checking each column separately:

~~~sql
WHERE (department = 'ENG' AND grade = 2)
   OR (department = 'OPS' AND grade = 1)
~~~

you can write:

~~~sql
SELECT
    employee_id,
    department,
    grade
FROM expr_lab_180.employees
WHERE (department, grade) IN (
    ('ENG', 2),
    ('OPS', 1)
)
ORDER BY employee_id;
~~~

Results **1, 3, 6**: employees 1 and 6 are ENG grade 2; employee 3 is OPS grade 1.

### 7.1. Row IN with a Two-Column Subquery

~~~sql
SELECT
    employee_id,
    department,
    grade
FROM expr_lab_180.employees AS e
WHERE (e.department, e.grade) IN (
    SELECT r.department, r.grade
    FROM expr_lab_180.eligible_pairs AS r
)
ORDER BY employee_id;
~~~

Results **1, 2, 3, 5, 6**. The subquery must return the **exact matching number of columns** as the left-hand row with comparable types.

### 7.2. Do Not Confuse Pairs with Two Independent Lists

Two independent conditions:

~~~sql
WHERE department IN ('ENG', 'OPS')
  AND grade IN (1, 2)
~~~

select **every combination** from the two sets: ENG-1, ENG-2, OPS-1, OPS-2. By contrast:

~~~sql
WHERE (department, grade) IN (
    ('ENG', 2),
    ('OPS', 1)
)
~~~

permits only **those two specific pairs**. This is why row comparisons excel for composite keys, combination policies, and multi-tenant keys.

### 7.3. NULL in Multi-Column IN

When `grade IS NULL`, do not assume `(department, grade) IN (...)` always returns `FALSE`. Some tuple comparisons evaluate to UNKNOWN and `IN` can return `NULL` when neither an exact match nor complete mismatch can be proven.

When checking rule existence:

~~~sql
SELECT
    e.employee_id,
    EXISTS (
        SELECT 1
        FROM expr_lab_180.eligible_pairs AS r
        WHERE r.department = e.department
          AND r.grade = e.grade
    ) AS has_matching_rule
FROM expr_lab_180.employees AS e
ORDER BY e.employee_id;
~~~

`EXISTS` returns **TRUE/FALSE** based on whether a matching row actually exists. If an employee's grade is NULL, `r.grade = e.grade` is not TRUE, no row matches, and `EXISTS` returns FALSE. If business rules treat **NULL as matching NULL**, use a null-safe comparison like `IS NOT DISTINCT FROM` and document the data semantics clearly.

## 8. PostgreSQL Arrays: Element Types and Creation

A PostgreSQL array is a value holding **multiple elements of the same type**. Common syntax:

~~~sql
SELECT
    ARRAY[1, 2, 3] AS integer_array,
    ARRAY['sql', 'postgres']::text[] AS text_array,
    ARRAY[]::integer[] AS empty_integer_array,
    NULL::integer[] AS unknown_integer_array,
    ARRAY[1, NULL::integer, 3] AS array_with_null_element;
~~~

The first expressions have types `integer[]` and `text[]` respectively.

### 8.1. Empty Arrays Need an Explicit Type

~~~sql
SELECT
    ARRAY[]::integer[] AS empty_grades,
    ARRAY[]::text[] AS empty_skills;
~~~

PostgreSQL cannot infer an element type from an array with **zero elements** without a type context. Therefore write `ARRAY[]::integer[]` rather than bare `ARRAY[]` in standalone SQL.

### 8.2. One-Dimensional and Multi-Dimensional Arrays

~~~sql
SELECT
    ARRAY[10, 20, 30] AS vector,
    ARRAY[
        [1, 2],
        [3, 4]
    ] AS matrix;
~~~

The first array is one-dimensional; the second is two-dimensional. PostgreSQL supports multi-dimensional arrays of matching rectangular sizes.

~~~sql
SELECT
    array_ndims(ARRAY[[1, 2], [3, 4]]) AS number_of_dimensions,
    cardinality(ARRAY[[1, 2], [3, 4]]) AS total_elements,
    array_length(ARRAY[[1, 2], [3, 4]], 1) AS first_dimension_size,
    array_length(ARRAY[[1, 2], [3, 4]], 2) AS second_dimension_size;
~~~

Results: **2 dimensions, 4 elements, first dimension length 2, second dimension length 2**.

### 8.3. Arrays with Curly-Brace Literals and Explicit Types

~~~sql
SELECT
    '{1,2,3}'::integer[] AS postgres_array_literal,
    '{"sql","postgres"}'::text[] AS text_literal;
~~~

`'{}'::integer[]` is an empty array. When values contain commas, quotes, backslashes, or special characters, PostgreSQL's array literal string syntax has specific escaping rules. In application code, pass arrays via **typed parameters** rather than building `'{...}'` strings manually.

## 9. Element Access, Sizes, and Unnesting Arrays

In normally constructed arrays, the first index is **1**, not 0 like Java arrays:

~~~sql
SELECT
    (ARRAY['sql', 'postgres', 'java'])[1] AS first_skill,
    (ARRAY['sql', 'postgres', 'java'])[2] AS second_skill,
    (ARRAY['sql', 'postgres', 'java'])[3] AS third_skill;
~~~

Results: `sql`, `postgres`, `java`.

### 9.1. Out-of-Bounds Element Access

~~~sql
SELECT
    (ARRAY[10, 20, 30])[5] AS out_of_bounds,
    (ARRAY[10, 20, 30])[0] AS below_default_lower_bound;
~~~

For standard 1-based arrays, both return `NULL`. However, **`NULL` at an index does not prove an element is present and NULL**; the index could simply be out of bounds.

PostgreSQL supports arrays with lower bounds other than 1 in certain contexts. When handling arrays with custom bounds, use `array_lower`/`array_upper` rather than assuming indexes always start at 1.

### 9.2. cardinality vs. array_length

~~~sql
SELECT
    cardinality(ARRAY[10, 20, 30]) AS elements,
    cardinality(ARRAY[]::integer[]) AS empty_elements,
    array_length(ARRAY[]::integer[], 1) AS empty_first_dim_length;
~~~

Results:

| Expression | Result |
| --- | ---: |
| `cardinality(ARRAY[10,20,30])` | 3 |
| `cardinality(ARRAY[]::integer[])` | 0 |
| `array_length(ARRAY[]::integer[],1)` | `NULL` |

`cardinality` is convenient for asking "how many total elements are there?", especially with empty arrays. For a `NULL` array, `cardinality(NULL::integer[])` is also `NULL`, **not 0**.

### 9.3. unnest: Turning an Array into Rows

~~~sql
SELECT
    skill
FROM unnest(ARRAY['sql', 'postgres', 'java']) AS u(skill);
~~~

This yields three rows. To retain **original positions**:

~~~sql
SELECT
    skill,
    position
FROM unnest(ARRAY['sql', NULL::text, 'kafka'])
    WITH ORDINALITY AS u(skill, position)
ORDER BY position;
~~~

| position | skill |
| ---: | --- |
| 1 | `sql` |
| 2 | `NULL` |
| 3 | `kafka` |

`WITH ORDINALITY` adds a 1-based ordinal number to rows emitted by a set-returning function. A `NULL` element **is still unnested as a row**; it does not disappear automatically.

### 9.4. Unnesting Each Employee's Skills

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    u.skill,
    u.position
FROM expr_lab_180.employees AS e
CROSS JOIN LATERAL unnest(e.skills)
    WITH ORDINALITY AS u(skill, position)
ORDER BY e.employee_id, u.position;
~~~

`CROSS JOIN LATERAL` emits zero rows for empty arrays or `NULL` arrays. Hence employees 4, 7, 9, and 10 **do not appear in the unnested output**.

To preserve employees without skills as well, use `LEFT JOIN LATERAL ... ON TRUE` and define how unmatched rows are handled:

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    u.skill
FROM expr_lab_180.employees AS e
LEFT JOIN LATERAL unnest(e.skills) AS u(skill)
    ON TRUE
ORDER BY e.employee_id, u.skill NULLS LAST;
~~~

When counting skills after a `LEFT JOIN`, use `COUNT(u.skill)` if you want to count **non-NULL skills**; `COUNT(*)` would count the extra null-padded row produced by the outer join.

## 10. Comparing Two Arrays with = and <>

Two arrays are equal when they are compatible under PostgreSQL's array equality rules: **corresponding element values** must match, and dimensions/bounds can also matter when elements match.

~~~sql
SELECT
    ARRAY[1, 2, 3] = ARRAY[1, 2, 3] AS same_values,
    ARRAY[1, 2] = ARRAY[2, 1] AS reordered_values,
    ARRAY[1, 1] = ARRAY[1] AS duplicate_matters,
    ARRAY[1, 2] <> ARRAY[1, 3] AS different_values;
~~~

Results: `TRUE`, `FALSE`, `FALSE`, `TRUE`.

**Arrays are ordered structures, not mathematical sets.** `ARRAY[1,2]` and `ARRAY[2,1]` contain the same members yet are **not equal**.

### 10.1. Array Ordering Comparisons

~~~sql
SELECT
    ARRAY[1, 2] < ARRAY[1, 3] AS lexicographic_less,
    ARRAY[2, 0] > ARRAY[1, 999] AS first_element_decides;
~~~

Both are `TRUE`. PostgreSQL compares elements in order using the element type's B-tree comparison. If comparable elements are equal, dimensions and sizes break ties.

Do not use `<`/`>` on arrays to test "is one array a subset of another." For element-set containment, use `@>`/`<@`.

### 10.2. A NULL Array Differs from an Empty Array

~~~sql
SELECT
    NULL::integer[] = ARRAY[]::integer[] AS unknown_vs_empty,
    ARRAY[]::integer[] = ARRAY[]::integer[] AS two_empty_arrays,
    ARRAY[NULL::integer] IS NULL AS non_null_array_with_null_item;
~~~

Results: `NULL`, `TRUE`, `FALSE`.

An **array containing a `NULL` element** is still a **non-NULL array value**; it does not turn into a `NULL` array.

### 10.3. What Not to Infer from =

`ARRAY['sql','java'] = ARRAY['java','sql']` is FALSE due to differing order, even though both contain the same skills. If business logic cares about **skill sets regardless of order**, use containment/overlap operators, canonical sorting, or a junction table; never assume array `=` compares "two sets."

## 11. Array Operators @>, <@, and &&

PostgreSQL provides specialized operators on arrays:

| Operator | How to Read | Example |
| --- | --- | --- |
| `a @> b` | `a` **contains** all elements of `b` | `ARRAY[1,2,3] @> ARRAY[1,3]` |
| `a <@ b` | `a` **is contained by** `b` | `ARRAY[1,3] <@ ARRAY[1,2,3]` |
| `a && b` | `a` and `b` **overlap** (share at least one element) | `ARRAY[1,2] && ARRAY[2,3]` |
| `a || b` | Concatenates arrays/elements per matching overload | `ARRAY[1,2] || ARRAY[3]` |

### 11.1. Containment and Overlap Examples

~~~sql
SELECT
    ARRAY[1, 2, 3] @> ARRAY[1, 3] AS contains_two_items,
    ARRAY[1, 3] <@ ARRAY[1, 2, 3] AS is_contained,
    ARRAY[1, 2] && ARRAY[2, 3] AS has_overlap,
    ARRAY[1, 2] && ARRAY[3, 4] AS disjoint,
    ARRAY[1, 2] || ARRAY[3, 4] AS concatenated;
~~~

Results: `TRUE`, `TRUE`, `TRUE`, `FALSE`, array `{1,2,3,4}`.

### 11.2. Using Containment to Find Employees with Skills

~~~sql
SELECT
    employee_id,
    employee_name,
    skills
FROM expr_lab_180.employees
WHERE skills @> ARRAY['sql']::text[]
ORDER BY employee_id;
~~~

Results: employees **1, 2, 6**.

Find people who have **both sql and postgres**:

~~~sql
SELECT employee_id, employee_name
FROM expr_lab_180.employees
WHERE skills @> ARRAY['sql', 'postgres']::text[]
ORDER BY employee_id;
-- Employee 1.
~~~

Find people who have **at least one** of `sql` or `postgres`:

~~~sql
SELECT employee_id, employee_name
FROM expr_lab_180.employees
WHERE skills && ARRAY['sql', 'postgres']::text[]
ORDER BY employee_id;
-- Employees 1, 2, 3, 6.
~~~

### 11.3. Containment Does Not Count Multiplicities

A surprise for many:

~~~sql
SELECT
    ARRAY[1] @> ARRAY[1, 1] AS duplicate_not_counted,
    ARRAY[1, 1] @> ARRAY[1] AS inverse_contains,
    ARRAY[1] = ARRAY[1, 1] AS arrays_not_equal;
~~~

Results: `TRUE`, `TRUE`, `FALSE`.

`@>`/`<@` test **element presence** under set-containment semantics, rather than treating arrays as **multisets** whose occurrence counts must match. By contrast, `=` still distinguishes a one-element array from a two-element array.

### 11.4. Do Not Treat All Operators as Identical When NULLs Exist

When an array has `NULL` elements, match/mismatch/UNKNOWN semantics can differ between `= ANY(...)`, whole-array equality, and containment operators. Each operator has its own specification; **do not mechanically swap `= ANY` for `@>`** when data contains NULLs or requires exact three-valued results.

If business rules forbid NULL skills, **clean/constrain arrays on write** or use a relational table with `NOT NULL` columns instead of relying on subtle comparisons on unnormalized input.

## 12. ANY and ALL: Quantifiers Over Comparison Results

Core syntax:

~~~sql
scalar_value comparison_operator ANY (array_expression)
scalar_value comparison_operator ALL (array_expression)
~~~

or:

~~~sql
scalar_value comparison_operator ANY (subquery)
scalar_value comparison_operator ALL (subquery)
~~~

`comparison_operator` is typically `=`, `<>`, `<`, `<=`, `>`, or `>=`, and must be an operator returning boolean.

**`ANY` means "at least one element produces a TRUE comparison."**  
**`ALL` means "every element produces a TRUE comparison."**

An alias for `ANY` in SQL syntax is **`SOME`**:

~~~sql
SELECT
    2 = ANY(ARRAY[1, 2, 3]) AS any_match,
    2 = SOME(ARRAY[1, 2, 3]) AS some_match;
-- TRUE, TRUE
~~~

`ANY` and `ALL` **are not standalone functions that take an array and return a boolean**. They must follow a **comparison operator on the left**, such as `x = ANY(...)` or `x < ALL(...)`.

### 12.1. First Examples

~~~sql
SELECT
    2 = ANY(ARRAY[1, 2, 3]) AS belongs_to_list,
    9 = ANY(ARRAY[1, 2, 3]) AS not_in_list,
    4 > ALL(ARRAY[1, 2, 3]) AS greater_than_all,
    2 > ALL(ARRAY[1, 2, 3]) AS not_greater_than_all;
~~~

Results: `TRUE`, `FALSE`, `TRUE`, `FALSE`.

In `4 > ALL(ARRAY[1,2,3])`, all three checks `4>1`, `4>2`, `4>3` are TRUE so the result is TRUE. In `2 > ALL(...)`, `2>2` is FALSE so the result is FALSE.

### 12.2. Summary Truth Table for TRUE/FALSE/UNKNOWN

Suppose comparing against each element yields a series of results:

| Per-Element Results | `ANY` Result | `ALL` Result |
| --- | --- | --- |
| TRUE, TRUE, TRUE | TRUE | TRUE |
| FALSE, FALSE, FALSE | FALSE | FALSE |
| TRUE, FALSE | TRUE | FALSE |
| TRUE, UNKNOWN | TRUE | UNKNOWN |
| FALSE, UNKNOWN | UNKNOWN | FALSE |
| UNKNOWN, UNKNOWN | UNKNOWN | UNKNOWN |
| **Zero elements** | **FALSE** | **TRUE** |

For `ANY`, **one TRUE is decisive**. If there is no TRUE yet there is an UNKNOWN, FALSE cannot be concluded.

For `ALL`, **one FALSE is decisive**. If there is no FALSE yet there is an UNKNOWN, TRUE cannot be concluded.

This is SQL three-valued logic; `UNKNOWN` appears as boolean `NULL` in results.

## 13. = ANY(array): Checking Whether a Value Is in an Array

Example:

~~~sql
SELECT
    employee_id,
    employee_name,
    skills
FROM expr_lab_180.employees
WHERE 'sql' = ANY(skills)
ORDER BY employee_id;
~~~

Results **1, 2, 6**.

How to read it:

~~~text
'sql' = ANY(skills)
        |
        +-- is there at least one skill element equal to 'sql'?
~~~

### 13.1. Comparison Checks Value, Not Position

~~~sql
SELECT
    'sql' = ANY(ARRAY['sql', 'java']) AS first_position,
    'sql' = ANY(ARRAY['java', 'sql']) AS second_position;
-- TRUE, TRUE
~~~

`ANY` does not care whether the element is at index 1. Meanwhile, `ARRAY['sql','java'] = ARRAY['java','sql']` is FALSE because **whole-array equality** depends on element order.

### 13.2. = ANY with an Array Column and Filtering

~~~sql
SELECT
    e.employee_id,
    e.department,
    e.grade,
    r.allowed_grades,
    e.grade = ANY(r.allowed_grades) AS grade_is_allowed
FROM expr_lab_180.employees AS e
JOIN expr_lab_180.department_rules AS r
    ON r.department = e.department
ORDER BY e.employee_id;
~~~

Logical results:

| ID | Department | Grade | Allowed Array | `grade_is_allowed` |
| ---: | --- | ---: | --- | --- |
| 1 | ENG | 2 | `{1,2,3}` | TRUE |
| 2 | ENG | 3 | `{1,2,3}` | TRUE |
| 3 | OPS | 1 | `{1,2}` | TRUE |
| 4 | OPS | `NULL` | `{1,2}` | NULL |
| 5 | SALES | 2 | `{2,3}` | TRUE |
| 6 | ENG | 2 | `{1,2,3}` | TRUE |
| 7 | ENG | 1 | `{1,2,3}` | TRUE |
| 8 | SALES | `NULL` | `{2,3}` | NULL |
| 9 | QA | 1 | `{}` | FALSE |
| 10 | RND | 1 | `NULL` | NULL |

Notice employee **9** evaluates to FALSE because the list exists and is empty; employee **10** evaluates to NULL because the rule list is unknown.

### 13.3. WHERE Keeps Only TRUE

~~~sql
SELECT
    e.employee_id,
    e.employee_name
FROM expr_lab_180.employees AS e
JOIN expr_lab_180.department_rules AS r
    ON r.department = e.department
WHERE e.grade = ANY(r.allowed_grades)
ORDER BY e.employee_id;
~~~

Results **1, 2, 3, 5, 6, 7**. In `WHERE`:

- TRUE -> row is kept.
- FALSE -> row is excluded.
- NULL/UNKNOWN -> row is also excluded.

Therefore, looking solely at the selected rows **does not tell you** whether excluded rows failed the rule or lacked sufficient data to evaluate.

## 14. ALL(array): Every Element Satisfies the Condition

Example:

~~~sql
SELECT
    10 > ALL(ARRAY[2, 4, 6]) AS above_every_number,
    10 > ALL(ARRAY[2, 12, 6]) AS not_above_every_number,
    2 = ALL(ARRAY[2, 2, 2]) AS all_equal_two,
    2 = ALL(ARRAY[2, 2, 3]) AS some_not_equal;
~~~

Results: TRUE, FALSE, TRUE, FALSE.

### 14.1. Greater Than All Thresholds

Suppose an employee meets a criterion only if their grade exceeds **every** grade in a benchmark list:

~~~sql
SELECT
    employee_id,
    grade,
    grade > ALL(ARRAY[1, 2]) AS higher_than_all_benchmarks
FROM expr_lab_180.employees
WHERE department = 'ENG'
ORDER BY employee_id;
~~~

Employee 2 has grade 3 -> TRUE; employees 1 and 6 have grade 2 -> FALSE; employee 7 has grade 1 -> FALSE.

For "at least equal to all," use `>= ALL`. A single element greater than the tested value breaks the condition.

### 14.2. Mistake: = ALL Does Not Mean "In the List"

~~~sql
SELECT
    2 = ANY(ARRAY[1, 2, 3]) AS member_of_list,
    2 = ALL(ARRAY[1, 2, 3]) AS equal_to_every_item;
-- TRUE, FALSE
~~~

`= ALL` requires **every element to equal 2**, not merely one element equal to 2. For membership, use `= ANY` or `IN`.

## 15. Empty Arrays: ANY Is FALSE, ALL Is TRUE

An empty set contains zero elements:

~~~sql
SELECT
    2 = ANY(ARRAY[]::integer[]) AS any_on_empty,
    2 <> ALL(ARRAY[]::integer[]) AS all_not_equal_on_empty,
    2 > ALL(ARRAY[]::integer[]) AS greater_than_all_empty,
    2 = ALL(ARRAY[]::integer[]) AS equals_all_empty;
~~~

Results:

| Expression | Result |
| --- | --- |
| `2 = ANY('{}'::integer[])` | FALSE |
| `2 <> ALL('{}'::integer[])` | TRUE |
| `2 > ALL('{}'::integer[])` | TRUE |
| `2 = ALL('{}'::integer[])` | TRUE |

At first glance, `2 = ALL(empty)` returning TRUE looks odd. In quantifier logic, "every element of the empty set equals 2" has **no counterexample**, so `ALL` evaluates to TRUE. This is called **vacuous truth**.

### 15.1. Empty Set Differs from a Set Containing Only NULL

~~~sql
SELECT
    2 = ANY(ARRAY[]::integer[]) AS empty_any,
    2 = ANY(ARRAY[NULL::integer]) AS null_element_any,
    2 = ALL(ARRAY[]::integer[]) AS empty_all,
    2 = ALL(ARRAY[NULL::integer]) AS null_element_all;
~~~

Results: FALSE, NULL, TRUE, NULL.

**Do not equate an array containing a NULL element with an empty array.** It has one comparison with an unknown outcome, rather than zero comparisons.

### 15.2. Impact on Business Rules

If `allowed_grades = '{}'` means **no grade is allowed**, `grade = ANY(allowed_grades)` returns FALSE, matching membership semantics.

Conversely, if an application writes:

~~~sql
grade <> ALL(allowed_grades)
~~~

then on an empty list it returns TRUE—which makes sense if checking "grade is not on a blocklist" and the blocklist is empty, but is **not** how to check "is grade allowed."

## 16. NULL on the Left, NULL Arrays, and NULL Elements

There are three places `NULL` can appear:

1. **Left-hand side** of the comparison is `NULL`.
2. **The array itself** is `NULL`.
3. **An element inside the array** is `NULL`.

These yield different outcomes depending on whether a decisive TRUE/FALSE comparison exists.

### 16.1. NULL on the Left

~~~sql
SELECT
    NULL::integer = ANY(ARRAY[1, 2, 3]) AS left_null_any,
    NULL::integer = ALL(ARRAY[1, 2, 3]) AS left_null_all;
-- NULL, NULL
~~~

With standard `=`, `NULL = 1`, `NULL = 2`, and `NULL = 3` are all UNKNOWN, so the quantified result is also UNKNOWN.

### 16.2. The Entire Array Is NULL

~~~sql
SELECT
    2 = ANY(NULL::integer[]) AS null_array_any,
    2 = ALL(NULL::integer[]) AS null_array_all;
-- NULL, NULL
~~~

There is no list information to evaluate. This is not an empty-array case.

### 16.3. A NULL Element When a TRUE Match Exists

~~~sql
SELECT
    3 = ANY(ARRAY[1, NULL::integer, 3])
        AS match_wins_over_unknown,
    2 = ANY(ARRAY[1, NULL::integer, 3])
        AS no_match_but_unknown_remains;
~~~

Results: TRUE, NULL.

In the first example, `3 = 3` is TRUE, so `ANY` is definitely TRUE despite the UNKNOWN comparison elsewhere.

In the second example, `2 = 1` is FALSE, `2 = NULL` is UNKNOWN, `2 = 3` is FALSE. No TRUE exists, yet because an unknown element might equal 2, we **cannot conclude FALSE**, so the result is NULL.

### 16.4. ALL with a NULL Element

~~~sql
SELECT
    4 > ALL(ARRAY[1, NULL::integer, 3])
        AS no_false_but_unknown,
    3 > ALL(ARRAY[1, NULL::integer, 3])
        AS false_wins_over_unknown,
    2 = ALL(ARRAY[2, NULL::integer])
        AS equality_not_fully_known;
~~~

Results: NULL, FALSE, NULL.

When `3 > 3` is FALSE, `ALL` is definitely FALSE regardless of the NULL element. When every known comparison is TRUE and an UNKNOWN remains, `ALL` returns NULL.

### 16.5. Table Distinguishing Array States

| State | Example | `cardinality` | `2 = ANY(...)` | `2 <> ALL(...)` |
| --- | --- | ---: | --- | --- |
| Empty array | `ARRAY[]::integer[]` | 0 | FALSE | TRUE |
| NULL array | `NULL::integer[]` | NULL | NULL | NULL |
| Array with NULL | `ARRAY[NULL::integer]` | 1 | NULL | NULL |
| Array with 2 and NULL | `ARRAY[2, NULL::integer]` | 2 | TRUE | FALSE |
| Array with 1 and NULL | `ARRAY[1, NULL::integer]` | 2 | NULL | NULL |

This is one of the most important tables in this lesson: **UNKNOWN is not FALSE**, especially under negated conditions.

## 17. IN, NOT IN, and Their Quantified Equivalents

For ordinary values:

~~~sql
2 IN (1, 2, 3)
~~~

has the same membership semantics as:

~~~sql
2 = ANY(ARRAY[1, 2, 3])
~~~

Similarly, the expression:

~~~sql
2 NOT IN (1, 3, 5)
~~~

corresponds to:

~~~sql
2 <> ALL(ARRAY[1, 3, 5])
~~~

**`NOT IN` means "not equal to all," not "not equal to at least one."**

### 17.1. <> ANY Is a Common Logic Bug

~~~sql
SELECT
    2 <> ANY(ARRAY[1, 2]) AS different_from_at_least_one,
    2 <> ALL(ARRAY[1, 2]) AS different_from_everyone,
    2 = ANY(ARRAY[1, 2]) AS member_of_array;
~~~

Results:

| Expression | Result |
| --- | --- |
| `2 <> ANY({1,2})` | TRUE |
| `2 <> ALL({1,2})` | FALSE |
| `2 = ANY({1,2})` | TRUE |

`2 <> ANY({1,2})` is TRUE because `2 <> 1`. That **does not prove 2 is absent from the array**. To negate membership:

~~~sql
NOT (2 = ANY(ARRAY[1, 2]))
~~~

or:

~~~sql
2 <> ALL(ARRAY[1, 2])
~~~

while still accounting for `NULL` semantics.

### 17.2. NOT IN and NULL Elements

~~~sql
SELECT
    2 NOT IN (1, NULL::integer, 3) AS not_in_with_unknown,
    2 <> ALL(ARRAY[1, NULL::integer, 3])
        AS all_not_equal_with_unknown;
-- NULL, NULL
~~~

No element is known to equal 2, yet the `NULL` element could be 2 or something else. Therefore negated membership **cannot conclude TRUE**.

In `WHERE`, rows with a NULL condition are **excluded**. That is why a `NOT IN` query backed by a subquery over a nullable column can return fewer rows than expected, or zero rows.

### 17.3. NOT IN with a NULL Left-Hand Value

~~~sql
SELECT
    NULL::integer NOT IN (1, 2, 3) AS unknown_left;
-- NULL
~~~

If the input column is nullable, decide whether a NULL value means "not in the list" or **insufficient information**. Never wrap it blindly in `COALESCE(..., TRUE)`, because that alters the business meaning of missing data.

## 18. ANY or ALL with a Subquery

Beyond arrays, PostgreSQL lets you compare a value against **rows returned by a subquery**:

~~~sql
value operator ANY (SELECT single_column FROM ...)
value operator ALL (SELECT single_column FROM ...)
~~~

For scalar comparisons here, the subquery must return **one column** of a type compatible with the left side.

### 18.1. = ANY(subquery) Parallels IN(subquery)

~~~sql
SELECT
    e.employee_id,
    e.department,
    e.grade
FROM expr_lab_180.employees AS e
WHERE e.grade = ANY (
    SELECT r.grade
    FROM expr_lab_180.eligible_pairs AS r
    WHERE r.department = 'ENG'
)
ORDER BY e.employee_id;
~~~

The subquery returns ENG grades: `2` and `3`. The outer query returns employees with grade 2 or 3 across **all departments**, since the outer condition does not restrict department: **1, 2, 5, 6**.

If you only want **ENG employees** meeting ENG's allowed grades, add:

~~~sql
AND e.department = 'ENG'
~~~

or use a correlated subquery on `e.department`:

~~~sql
SELECT
    e.employee_id,
    e.department,
    e.grade
FROM expr_lab_180.employees AS e
WHERE e.grade = ANY (
    SELECT r.grade
    FROM expr_lab_180.eligible_pairs AS r
    WHERE r.department = e.department
)
ORDER BY e.employee_id;
-- 1, 2, 3, 5, 6
~~~

Here the subquery is **correlated** because it references `e.department` from the outer query.

### 18.2. > ALL(subquery): Greater Than Every Element in a Subset

~~~sql
SELECT
    e.employee_id,
    e.grade
FROM expr_lab_180.employees AS e
WHERE e.grade > ALL (
    SELECT grade
    FROM expr_lab_180.employees
    WHERE department = 'OPS'
      AND grade IS NOT NULL
)
ORDER BY e.employee_id;
~~~

For OPS, the known grade is **1** (employee 3); employee 4 with grade NULL was filtered out via `IS NOT NULL`. Thus the query selects employees with grade **greater than 1**: **1, 2, 5, 6**.

### 18.3. If You Forget to Filter NULL in the Subquery

~~~sql
SELECT
    3 > ALL (
        SELECT grade
        FROM expr_lab_180.employees
        WHERE department = 'OPS'
    ) AS above_every_ops_grade;
~~~

The subquery returns `1` and `NULL`. `3>1` is TRUE, `3>NULL` is UNKNOWN, so the overall result is **NULL**, not TRUE.

When business rules examine **only known grades**, write `AND grade IS NOT NULL` explicitly in the subquery. When NULL represents an unverified value needing reconciliation, do not ignore it silently.

### 18.4. ANY/ALL on an Empty Subquery

~~~sql
SELECT
    2 = ANY (
        SELECT grade
        FROM expr_lab_180.employees
        WHERE department = 'NON_EXISTENT'
    ) AS any_empty_subquery,
    2 > ALL (
        SELECT grade
        FROM expr_lab_180.employees
        WHERE department = 'NON_EXISTENT'
    ) AS all_empty_subquery;
~~~

Results: **FALSE** and **TRUE**, just like empty arrays.

Zero rows from a subquery is a **different** case from a subquery returning one row whose column value is NULL.

## 19. NOT EXISTS: A Reliable Alternative for Many NOT IN Tasks

`EXISTS(subquery)` returns TRUE when the subquery yields **at least one row**, otherwise FALSE. `NOT EXISTS` is its negation.

### 19.1. The NOT IN Trap When the Source Contains NULL

Consider:

~~~sql
SELECT
    e.employee_id,
    e.grade
FROM expr_lab_180.employees AS e
WHERE e.grade NOT IN (
    SELECT grade
    FROM expr_lab_180.employees
    WHERE department = 'OPS'
)
ORDER BY e.employee_id;
~~~

The subquery returns `1` and `NULL`. For grades other than 1, the comparison is UNKNOWN; for grade 1, it is FALSE; for grade NULL, it is also not TRUE. Thus the query returns **0 rows**, even though several employees clearly have grades 2 or 3.

### 19.2. Using NOT EXISTS to Check Absence of a Matching Value

~~~sql
SELECT
    e.employee_id,
    e.grade
FROM expr_lab_180.employees AS e
WHERE e.grade IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM expr_lab_180.employees AS ops
      WHERE ops.department = 'OPS'
        AND ops.grade = e.grade
  )
ORDER BY e.employee_id;
~~~

The result is employees with grade **2 or 3**: **1, 2, 5, 6**.

`NOT EXISTS` checks **whether any row satisfies the correlated predicate**, and is not turned into UNKNOWN by an `ops.grade IS NULL` row. We still keep `e.grade IS NOT NULL` so we **do not treat an unknown grade as confirmed different from OPS grades**.

### 19.3. If NULL Should Count as a Matchable Value

~~~sql
SELECT
    e.employee_id,
    e.grade
FROM expr_lab_180.employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM expr_lab_180.employees AS ops
    WHERE ops.department = 'OPS'
      AND ops.grade IS NOT DISTINCT FROM e.grade
)
ORDER BY e.employee_id;
~~~

Here `IS NOT DISTINCT FROM` treats two `NULL` values as matching for the join condition. Because OPS has a NULL grade, employees with NULL grade match and are **excluded**. The result in this dataset remains the grade 2 and 3 group.

**Choosing `=` vs. `IS NOT DISTINCT FROM` depends on how business rules define NULL.** `NOT EXISTS` does not decide what missing values mean on its own; it simply lets you express the matching rule explicitly.

## 20. > ALL, < ANY, and MIN/MAX: Conditional Equivalence

For a **non-empty** set of entirely **non-NULL** values and a comparable left-hand value:

~~~text
x > ALL(values)   equivalent to x > MAX(values)
x >= ALL(values)  equivalent to x >= MAX(values)
x < ALL(values)   equivalent to x < MIN(values)
x <= ALL(values)  equivalent to x <= MIN(values)

x > ANY(values)   equivalent to x > MIN(values)
x < ANY(values)   equivalent to x < MAX(values)
~~~

This is a helpful mental model, **not a guarantee that both forms behave identically on empty or nullable sets**.

### 20.1. Comparing on Guaranteed Non-NULL Data

~~~sql
SELECT
    4 > ALL(ARRAY[1, 2, 3]) AS all_comparison,
    4 > (
        SELECT MAX(x)
        FROM unnest(ARRAY[1, 2, 3]) AS u(x)
    ) AS comparison_to_max;
-- TRUE, TRUE
~~~

### 20.2. Difference on Empty Sets

~~~sql
SELECT
    4 > ALL(ARRAY[]::integer[]) AS all_on_empty,
    4 > (
        SELECT MAX(x)
        FROM unnest(ARRAY[]::integer[]) AS u(x)
    ) AS greater_than_max_of_empty;
~~~

Results:

- `all_on_empty = TRUE`.
- `greater_than_max_of_empty = NULL`, because `MAX` over an empty set returns NULL.

If you replace `ALL` with `MAX`, handle **empty sets** explicitly.

### 20.3. Difference When the Set Contains NULL

~~~sql
SELECT
    4 > ALL(ARRAY[1, NULL::integer, 3])
        AS all_with_unknown,
    4 > (
        SELECT MAX(x)
        FROM unnest(ARRAY[1, NULL::integer, 3]) AS u(x)
    ) AS against_max_ignoring_null;
~~~

Results:

- `all_with_unknown = NULL`.
- `against_max_ignoring_null = TRUE`, because `MAX` ignores NULL and returns 3.

This proves that **quantified comparison on a set with NULL** and **comparing against `MIN`/`MAX` which ignore NULL** do not always mean the same thing.

## 21. ANY(array) vs. Containment Operators When Filtering Array Columns

Two common ways to find employees having `'sql'` in `skills`:

~~~sql
-- Approach 1: quantified comparison
SELECT employee_id
FROM expr_lab_180.employees
WHERE 'sql' = ANY(skills)
ORDER BY employee_id;
~~~

~~~sql
-- Approach 2: array containment
SELECT employee_id
FROM expr_lab_180.employees
WHERE skills @> ARRAY['sql']::text[]
ORDER BY employee_id;
~~~

On this dataset, both return **1, 2, 6**. However:

- `= ANY` asks "is there any element equal to the lookup value?"
- `@>` asks "does the left array contain the elements of the right array?"
- `@>` can express multiple required elements at once.
- Cases with `NULL` and UNKNOWN results must be checked against each operator's exact rules.
- **GIN index** eligibility for containment can differ from index eligibility for `= ANY` on an **array column**.

Never treat the two forms as identical solely because a small sample dataset returns the same rows.

### 21.1. Filtering a Scalar Column Against an Input Array Is a Different Problem

~~~sql
SELECT
    employee_id,
    employee_name
FROM expr_lab_180.employees
WHERE grade = ANY(ARRAY[1, 3]::integer[])
ORDER BY employee_id;
~~~

Here **the filtered column is scalar `grade INTEGER`**, not an array column `skills`. With a B-tree index on `grade` and appropriate conditions, PostgreSQL can use an index for `grade = ANY(parameter_array)`. That is quite different from searching for **an element inside an array column**.

## 22. ANY/ALL with LIKE, ILIKE, and Other Comparisons

Beyond `=`, `<>`, and `>`, PostgreSQL lets any compatible boolean operator precede `ANY`/`ALL`, such as text pattern matching.

~~~sql
SELECT
    'PostgreSQL Developer' ILIKE ANY(
        ARRAY['%postgres%', '%java%']
    ) AS matches_at_least_one_pattern,
    'PostgreSQL Developer' ILIKE ALL(
        ARRAY['%postgres%', '%developer%']
    ) AS matches_all_patterns;
-- TRUE, TRUE
~~~

### 22.1. ILIKE ANY Is Not Arbitrary Substring Search

`ILIKE` follows PostgreSQL's case-insensitive pattern matching rules. `%` matches zero or more characters; `_` matches one character. Write wildcards deliberately and control escape characters when patterns come from input.

### 22.2. Watch Out for Negating Quantifiers

Just like `<> ANY`, the expression:

~~~sql
value NOT ILIKE ANY(pattern_array)
~~~

does not mean "value matches **none** of the patterns." It asks whether there is **at least one** pattern that `value` does not match.

To negate "matches at least one":

~~~sql
NOT (value ILIKE ANY(pattern_array))
~~~

or express "does not match all" with the corresponding operator/`ALL`, keeping NULL behavior in mind. This is another instance of the logical law:

\[
\neg(\exists x : P(x)) \equiv \forall x : \neg P(x)
\]

Never change `ANY` to `ALL` while forgetting to **negate the operator**.

## 23. ARRAY and ARRAY_AGG in Queries

Besides literal arrays, PostgreSQL can build arrays from row sets:

~~~sql
SELECT ARRAY(
    SELECT employee_id
    FROM expr_lab_180.employees
    WHERE department = 'ENG'
    ORDER BY employee_id
) AS engineering_ids;
~~~

Result: `{1,2,6,7}`. `ARRAY(subquery)` requires the subquery to return **one column** and returns an empty array when the subquery produces zero rows.

### 23.1. ARRAY(subquery) vs. array_agg

~~~sql
SELECT
    array_agg(employee_id ORDER BY employee_id)
        AS engineering_ids
FROM expr_lab_180.employees
WHERE department = 'ENG';
~~~

The query returns `{1,2,6,7}`. On an empty set, however:

~~~sql
SELECT
    ARRAY(
        SELECT employee_id
        FROM expr_lab_180.employees
        WHERE department = 'NON_EXISTENT'
    ) AS array_from_empty_subquery,
    (
        SELECT array_agg(employee_id)
        FROM expr_lab_180.employees
        WHERE department = 'NON_EXISTENT'
    ) AS aggregate_from_empty_input;
~~~

- `ARRAY(empty subquery)` returns a typed **empty array**.
- `array_agg(...)` on zero rows returns **`NULL`**, like most aggregates other than `COUNT`.

This matters if you feed the result into `ANY`/`ALL`: an empty array and a NULL array **do not have the same meaning**.

### 23.2. Normalizing Empty array_agg

If an API contract requires an empty list when no rows exist:

~~~sql
SELECT
    COALESCE(
        array_agg(employee_id ORDER BY employee_id),
        ARRAY[]::bigint[]
    ) AS employee_ids
FROM expr_lab_180.employees
WHERE department = 'NON_EXISTENT';
~~~

`COALESCE` here is a **deliberate data decision**, not a blanket change to apply to every nullable array.

### 23.3. array_agg Can Contain NULL Elements

~~~sql
SELECT
    array_agg(grade ORDER BY employee_id)
        AS all_grades_including_unknown
FROM expr_lab_180.employees
WHERE department = 'OPS';
~~~

The result is an array containing grade `1` and a `NULL` element, not an array with only one grade.

To exclude NULL grades from the array:

~~~sql
SELECT
    COALESCE(
        array_agg(grade ORDER BY employee_id)
            FILTER (WHERE grade IS NOT NULL),
        ARRAY[]::integer[]
    ) AS known_grades
FROM expr_lab_180.employees
WHERE department = 'OPS';
-- {1}
~~~

**Whether `array_agg` keeps or drops NULLs** is an important design choice whenever that array is later passed to `ANY`/`ALL`.

## 24. array_position, array_remove, and Checking NULL Elements

For arrays, PostgreSQL includes functions operating directly on elements:

~~~sql
SELECT
    array_position(
        ARRAY['sql', NULL::text, 'kafka'],
        'kafka'
    ) AS kafka_position,
    array_position(
        ARRAY['sql', NULL::text, 'kafka'],
        NULL::text
    ) AS null_position,
    array_remove(
        ARRAY['sql', NULL::text, 'kafka'],
        NULL::text
    ) AS cleaned_array;
~~~

Results:

| Expression | Result |
| --- | --- |
| Position of `kafka` | 3 |
| Position of `NULL` element | 2 |
| Array after removing `NULL` element | `{sql,kafka}` |

`array_position` and `array_remove` use **`IS NOT DISTINCT FROM`** comparison semantics when locating elements, so they can find and remove `NULL` elements. That **differs** from ordinary `= ANY`, where `NULL = NULL` never returns TRUE.

### 24.1. Do Not Equate "Array Has No NULLs" with "Array Has at Least One Element"

~~~sql
SELECT
    cardinality(ARRAY[]::text[]) AS empty_size,
    array_position(ARRAY[]::text[], NULL::text)
        AS null_position_in_empty;
~~~

An empty array has size 0 and contains no NULL elements. An array with three non-NULL skills has size 3 and also contains no NULL elements. If you need both properties, check them separately.

## 25. Using ANY/ALL in UPDATE and Business Queries

Example of an `UPDATE` affecting only grades in an allowed list. Run inside a practice transaction so seed data remains unchanged afterward:

~~~sql
BEGIN;

UPDATE expr_lab_180.employees
SET salary = salary * 1.05
WHERE department = 'ENG'
  AND grade = ANY(ARRAY[2, 3]::integer[])
  AND salary IS NOT NULL;

-- Inspect updated rows inside the transaction:
SELECT employee_id, grade, salary
FROM expr_lab_180.employees
WHERE department = 'ENG'
ORDER BY employee_id;

ROLLBACK;
~~~

Here ENG employees in grade 2 or 3 with known salaries are updated inside the transaction; `ROLLBACK` restores the original values. **This is a learning SQL example**, not a real compensation policy.

### 25.1. Selecting Records Not on a Blocklist

~~~sql
SELECT
    employee_id,
    grade
FROM expr_lab_180.employees
WHERE grade <> ALL(ARRAY[4, 5]::integer[])
ORDER BY employee_id;
~~~

Grades **1, 2, 3** are selected; `NULL` grades do not appear because the condition evaluates to UNKNOWN. If the goal is "keep only employees with confirmed grades not in 4/5," this query fits. If the goal is "include employees without a grade yet," add an explicit `grade IS NULL` condition per policy.

### 25.2. Filtering by Multiple Key Pairs

~~~sql
SELECT
    employee_id,
    department,
    grade
FROM expr_lab_180.employees
WHERE (department, grade) IN (
    ('ENG', 2),
    ('SALES', 2)
)
ORDER BY employee_id;
-- 1, 5, 6
~~~

Here `(department, grade)` row syntax expresses the pair rule better than two independent lists.

## 26. B-Tree and GIN Indexes: Choosing by Query Pattern

### 26.1. Multi-Column B-Tree Index for Scalar Columns

~~~sql
CREATE INDEX idx_employees_department_grade_180
ON expr_lab_180.employees(department, grade);
~~~

This index can assist queries such as:

~~~sql
SELECT *
FROM expr_lab_180.employees
WHERE (department, grade) = ('ENG', 2);
~~~

or queries with filters/sorts aligned with the **index prefix**. On a ten-row table, PostgreSQL will likely choose sequential scan because it is cheaper.

### 26.2. B-Tree Index for scalar = ANY(parameter_array)

~~~sql
CREATE INDEX idx_employees_grade_180
ON expr_lab_180.employees(grade);

SELECT
    employee_id, grade
FROM expr_lab_180.employees
WHERE grade = ANY(ARRAY[1, 3]::integer[]);
~~~

PostgreSQL can optimize scalar comparisons against an input array using index scans in many situations. Yet **there is no guarantee every `= ANY` query uses an index**; it depends on table size, array length, statistics, selectivity, and planner cost.

### 26.3. GIN Index for Array Columns

~~~sql
CREATE INDEX idx_employees_skills_gin_180
ON expr_lab_180.employees
USING GIN (skills);
~~~

GIN (*Generalized Inverted Index*) supports array operators such as `@>`, `<@`, and `&&` under the default operator class:

~~~sql
SELECT employee_id
FROM expr_lab_180.employees
WHERE skills @> ARRAY['sql']::text[];
~~~

~~~sql
SELECT employee_id
FROM expr_lab_180.employees
WHERE skills && ARRAY['sql', 'postgres']::text[];
~~~

Having a GIN index on `skills` **does not mean `'sql' = ANY(skills)` is optimized the same way**. The planner needs a predicate form supported by the index/operator class; when NULLs or distinct operator semantics apply, it will not rewrite unconditionally.

### 26.4. Inspecting Plans with EXPLAIN

~~~sql
EXPLAIN
SELECT
    employee_id,
    employee_name
FROM expr_lab_180.employees
WHERE skills @> ARRAY['sql']::text[];
~~~

On large datasets, a plan may use `Bitmap Index Scan` via GIN and `Bitmap Heap Scan`, while on a tiny lab table a sequential scan is completely normal. Only draw performance conclusions after measuring on representative data and workloads.

~~~sql
-- In a safe environment, EXPLAIN ANALYZE runs the actual query:
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    employee_id
FROM expr_lab_180.employees
WHERE grade = ANY(ARRAY[1, 3]::integer[]);
~~~

`EXPLAIN (ANALYZE, BUFFERS)` executes the query to measure runtime; never run it blindly in production without knowing cost and intent.

### 26.5. Optimization Depends on Data Storage Design

If membership queries like:

~~~sql
skills @> ARRAY['sql']::text[]
~~~

run very frequently, a GIN index can help. However, if each skill needs its own attributes (proficiency level, verification date, certificate source), a junction table makes FKs, `UNIQUE`, `CHECK`, and targeted indexes much cleaner. An index cannot substitute for an appropriate data model.

## 27. Arrays vs. Relational Junction Tables

A `skills TEXT[]` column works well when lists are small, uniform in type, and normally read/written as **a single block of values**. In other situations, a junction table is better:

~~~sql
CREATE TABLE expr_lab_180.skills_catalog (
    skill_code TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL
);

CREATE TABLE expr_lab_180.employee_skills (
    employee_id BIGINT NOT NULL
        REFERENCES expr_lab_180.employees(employee_id),
    skill_code TEXT NOT NULL
        REFERENCES expr_lab_180.skills_catalog(skill_code),
    confirmed_at TIMESTAMPTZ NULL,

    CONSTRAINT employee_skills_pk
        PRIMARY KEY (employee_id, skill_code)
);
~~~

This model provides:

- One row per employee-skill pair.
- Foreign keys preventing invalid skill codes.
- `PRIMARY KEY(employee_id, skill_code)` preventing duplicate pairs.
- Room for relationship metadata such as `confirmed_at`.

By contrast, `skills TEXT[]` cannot enforce foreign-key integrity on every array element via a standard FK constraint. When integrity rules apply at the **per-element level**, a relational junction table usually wins.

### 27.1. Comparing Both Ways to Query "Has sql Skill"

Array column:

~~~sql
SELECT employee_id
FROM expr_lab_180.employees
WHERE skills @> ARRAY['sql']::text[];
~~~

Junction table (assuming matching data):

~~~sql
SELECT employee_id
FROM expr_lab_180.employee_skills
WHERE skill_code = 'sql';
~~~

No single approach is optimal for every system. Evaluate scale, read/write frequency, referential integrity requirements, query complexity, and schema flexibility.

## 28. Array Parameters from Java/JDBC

When a UI lets users multi-select grades to filter, **never build a SQL string by concatenating individual IDs**. Use JDBC `java.sql.Array` with a prepared statement:

~~~java
Integer[] grades = {1, 3};

String sql = """
    SELECT employee_id, employee_name, grade
    FROM expr_lab_180.employees
    WHERE grade = ANY(?::integer[])
    ORDER BY employee_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    java.sql.Array gradeArray =
        connection.createArrayOf("int4", grades);

    try {
        ps.setArray(1, gradeArray);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                System.out.println(
                    rs.getLong("employee_id") + " " +
                    rs.getString("employee_name")
                );
            }
        }
    } finally {
        gradeArray.free();
    }
}
~~~

This snippet assumes `connection` is an open JDBC `Connection` and the Java version supports text blocks. `int4` is PostgreSQL's internal element type name corresponding to `integer`. Verify driver support and `Array.free()` lifecycle against your PostgreSQL JDBC driver version.

### 28.1. Empty Lists vs. NULL When Received from an API

The application must define clearly:

- **Empty selected list `[]`:** means "no grades selected," so `grade = ANY('{}')` returns FALSE and selects zero rows.
- **Filter field omitted:** means "do not filter by grade," so generally **omit the `grade = ANY(...)` predicate**.
- **Explicit `null` sent:** means unknown or omitted? Never silently convert it into an empty array unless the API contract specifies that.

This separates **empty data** from **no filter requested**. Confusing them can unexpectedly return empty listing pages.

### 28.2. Passing Array Parameters Preserves Types

~~~sql
WHERE grade = ANY(?::integer[])
~~~

Preserving the `integer` type helps PostgreSQL choose the right comparison operator, and parameter binding prevents unsafe SQL interpolation. Still, prepared statements **do not automatically cap overly huge arrays**; the application must validate input size and monitor query cost.

### 28.3. Reading an Array Column

~~~java
String sql = """
    SELECT employee_id, skills
    FROM expr_lab_180.employees
    WHERE employee_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1L);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            java.sql.Array sqlArray = rs.getArray("skills");
            if (sqlArray != null) {
                try {
                    Object[] values = (Object[]) sqlArray.getArray();
                    System.out.println(
                        java.util.Arrays.toString(values)
                    );
                } finally {
                    sqlArray.free();
                }
            }
        }
    }
}
~~~

Note that JDBC returns `null` when **the entire array column is NULL**; an empty array returns a zero-length Java array; an array with a SQL NULL element can contain a Java `null` element. Exact element mapping depends on the driver and SQL type.

## 29. Common Mistakes

| Misconception or Bug | Problem | Correct Approach |
| --- | --- | --- |
| `(a,b) < (x,y)` means `a<x AND b<y` | Rows compare lexicographically | The first field can decide immediately |
| `ROW(1,NULL) = ROW(1,NULL)` is TRUE | Row equality can yield UNKNOWN | Use `IS NOT DISTINCT FROM` when null-safe equality is needed |
| `ROW(1,NULL) IS NOT NULL` is TRUE | A row with any NULL field fails `IS NOT NULL` | Know row `IS NULL`/`IS NOT NULL` semantics |
| `(department,grade) IN (...)` equals two separate `IN`s | Two separate `IN` clauses match every Cartesian pair | Use row `IN` when **specific pairs** are required |
| `ARRAY[1,2] = ARRAY[2,1]` is TRUE | Arrays care about element order | Use containment/sets if only membership matters |
| `ARRAY[1] @> ARRAY[1,1]` is FALSE | Containment ignores duplicates | Do not use `@>` to compare multisets |
| `NULL::int[]` is like an empty array | One is unknown, one is known empty | Distinguish `NULL` arrays from `{}` |
| `ARRAY[NULL]` is a NULL array | Array exists with one NULL element | Distinguish a NULL array column from a NULL element |
| `2 = ANY({1,NULL})` is FALSE | UNKNOWN produces NULL | Handle/classify NULLs explicitly |
| `2 = ALL({1,2,3})` checks membership | Requires equality with **every** element | Use `= ANY` |
| `2 <> ANY({1,2})` means `NOT IN` | Only checks difference from **at least one** element | Use `<> ALL` or `NOT (= ANY)` |
| `ALL(empty)` is FALSE | `ALL` over an empty set is TRUE | Understand vacuous truth |
| `NOT IN (SELECT nullable_col...)` is always safe | NULLs can turn the predicate UNKNOWN | Consider `NOT EXISTS` and explicit NULL rules |
| `x > ALL(values)` always equals `x > MAX(values)` | Differs on empty sets and NULLs | Substitute only when equivalence is guaranteed |
| `= ANY` on an array column always uses GIN | Not automatically indexable like `@>` | Check `EXPLAIN`, pick matching operators/indexes |
| `array_length(empty,1)` equals 0 | PostgreSQL returns NULL | Use `cardinality` for total element count |
| `unnest(array)` automatically skips NULL elements | NULL elements emit NULL rows | Filter explicitly if needed |
| Empty `array_agg` returns `{}` | Aggregates return NULL on zero rows | `COALESCE(array_agg(...), ARRAY[]::type[])` when appropriate |
| `ROW/ARRAY` can replace relational schemas | Arrays lack per-element FKs | Use a junction table when integrity is needed |
| Empty filter list means no filtering | `= ANY('{}')` is always FALSE | Separate empty filter from omitted filter |

## 30. Practice Exercises

Exercises use the `expr_lab_180` dataset created earlier. Write your query before checking hints/answers, and explain not only the selected rows but also rows excluded due to `NULL`.

### Exercise 1 — Comparing Two Rows

Predict:

~~~sql
SELECT
    ROW(1, 100) < ROW(2, 0) AS a,
    ROW(1, 100) < ROW(1, 200) AS b,
    ROW(2, 100) < ROW(1, 999) AS c;
~~~

**Answer:** TRUE, TRUE, FALSE. Explain the left-to-right order.

### Exercise 2 — NULL in Row Equality

~~~sql
SELECT
    ROW(1, NULL::integer) = ROW(1, NULL::integer)
        AS ordinary_equality,
    ROW(1, NULL::integer)
        IS NOT DISTINCT FROM ROW(1, NULL::integer)
        AS null_safe_equality;
~~~

**Answer:** NULL and TRUE. Why do the two expressions differ?

### Exercise 3 — Row IS NULL

Run:

~~~sql
SELECT
    ROW(NULL::integer, NULL::text) IS NULL AS all_null,
    ROW(1, NULL::text) IS NULL AS mixed_is_null,
    ROW(1, NULL::text) IS NOT NULL AS mixed_is_not_null;
~~~

**Answer:** TRUE, FALSE, FALSE. Why can a row with one NULL field make both checks FALSE?

### Exercise 4 — Filtering department-grade Pairs

Use `(department, grade) IN (('ENG',2),('OPS',1))`. Which IDs are selected?

**Answer:** **1, 3, 6**.

Then compare with `department IN ('ENG','OPS') AND grade IN (1,2)`; identify the extra employee returned and explain why.

### Exercise 5 — Row IN with a Rules Table

Write a query using `(department,grade) IN (SELECT department,grade FROM eligible_pairs)`.

**Answer:** **1, 2, 3, 5, 6**. Employee 7 with `('ENG',1)` is excluded even though grade 1 is valid in another department.

### Exercise 6 — Empty Arrays and NULL Elements

Compare:

~~~sql
SELECT
    cardinality(ARRAY[]::integer[]) AS a,
    array_length(ARRAY[]::integer[], 1) AS b,
    cardinality(NULL::integer[]) AS c,
    cardinality(ARRAY[NULL::integer]) AS d;
~~~

**Answer:** 0, NULL, NULL, 1.

### Exercise 7 — Array Order vs. Containment

Predict:

~~~sql
SELECT
    ARRAY[1, 2] = ARRAY[2, 1] AS a,
    ARRAY[1, 2] @> ARRAY[2] AS b,
    ARRAY[1, 2] && ARRAY[2, 3] AS c,
    ARRAY[1] @> ARRAY[1, 1] AS d;
~~~

**Answer:** FALSE, TRUE, TRUE, TRUE. Distinguish array equality from element-set relations.

### Exercise 8 — Basic ANY

Find all employees having `'sql'` in `skills` using `'sql' = ANY(skills)`.

**Answer:** **1, 2, 6**. If using `skills @> ARRAY['sql']::text[]`, does the sample dataset return the same list?

### Exercise 9 — Both Skills vs. At Least One

Write two queries:

1. Has **both** `sql` and `postgres`.
2. Has **sql or postgres**.

**Hint:** `@> ARRAY['sql','postgres']` and `&& ARRAY['sql','postgres']`.

**Answer:** group 1: **1**; group 2: **1, 2, 3, 6**.

### Exercise 10 — ANY/ALL on Empty Arrays

~~~sql
SELECT
    9 = ANY(ARRAY[]::integer[]) AS a,
    9 <> ALL(ARRAY[]::integer[]) AS b,
    9 > ALL(ARRAY[]::integer[]) AS c;
~~~

**Answer:** FALSE, TRUE, TRUE. Explain "vacuous truth."

### Exercise 11 — ANY with a NULL Element

~~~sql
SELECT
    2 = ANY(ARRAY[1, NULL::integer, 3]) AS a,
    3 = ANY(ARRAY[1, NULL::integer, 3]) AS b,
    3 <> ALL(ARRAY[1, NULL::integer, 3]) AS c;
~~~

**Answer:** NULL, TRUE, FALSE. Identify which element comparison decided `b` and `c`.

### Exercise 12 — Distinguishing NULL Arrays from Empty Arrays in Rules

Join `employees` with `department_rules` and return `grade = ANY(allowed_grades)` for employees 9 and 10.

**Answer:** QA employee **9 -> FALSE** because `{}`; RND employee **10 -> NULL** because `allowed_grades IS NULL`.

### Exercise 13 — <> ANY Is Not NOT IN

~~~sql
SELECT
    2 <> ANY(ARRAY[1, 2]) AS wrong_not_in,
    2 <> ALL(ARRAY[1, 2]) AS correct_not_in;
~~~

**Answer:** TRUE, FALSE. Write a clear English sentence describing each expression.

### Exercise 14 — NOT IN Trap with a Subquery

Write a query finding employees whose grade **does not equal any known grade** in OPS. Compare:

- `grade NOT IN (SELECT grade FROM employees WHERE department='OPS')`;
- `NOT EXISTS (SELECT 1 ... WHERE ops.grade = e.grade)` with `e.grade IS NOT NULL`.

**Hint:** OPS has grade 1 and NULL. The `NOT IN` query returns **0 rows**, whereas `NOT EXISTS` with the stated guard selects employees with grades 2 or 3.

### Exercise 15 — ALL and MAX Differ on Empty Sets

~~~sql
SELECT
    5 > ALL(ARRAY[]::integer[]) AS a,
    5 > (
        SELECT MAX(x)
        FROM unnest(ARRAY[]::integer[]) AS u(x)
    ) AS b;
~~~

**Answer:** TRUE and NULL. Explain why `> ALL` cannot always be replaced by `> MAX`.

### Exercise 16 — ALL and MAX Differ When NULL Exists

~~~sql
SELECT
    5 > ALL(ARRAY[1, NULL::integer, 3]) AS a,
    5 > (
        SELECT MAX(x)
        FROM unnest(ARRAY[1, NULL::integer, 3]) AS u(x)
    ) AS b;
~~~

**Answer:** NULL and TRUE. `MAX` ignores NULL while the `ALL` quantifier propagates UNKNOWN.

### Exercise 17 — array_agg vs. ARRAY(subquery)

Build a list of `employee_id` values for a non-existent department using both `ARRAY(SELECT...)` and `array_agg(...)`. How do the results differ?

**Answer:** `ARRAY(SELECT...)` returns an empty array; `array_agg` returns NULL. Use `COALESCE` when an API contract needs `[]`.

### Exercise 18 — Finding NULL Elements with array_position

~~~sql
SELECT
    array_position(ARRAY['sql', NULL::text, 'kafka'], NULL::text)
        AS position_of_null,
    array_remove(ARRAY['sql', NULL::text, 'kafka'], NULL::text)
        AS without_null;
~~~

**Answer:** position **2**, array **{sql,kafka}**. Why does finding `NULL` with `array_position` succeed while `NULL = ANY(...)` does not return TRUE?

### Exercise 19 — Two-Column Pagination

Suppose a table has `(created_at TIMESTAMPTZ NOT NULL, id BIGINT PRIMARY KEY)`. Write a query fetching 20 rows after `(last_created_at, last_id)`, ordered ASC by both columns.

**Hint:** `WHERE (created_at,id) > (:last_created_at,:last_id) ORDER BY created_at,id LIMIT 20`. Explain why the `id` tie-breaker is needed.

### Exercise 20 — Indexes

Compare two goals:

1. Filtering `grade = ANY(ARRAY[1,3])` on scalar `grade INTEGER`.
2. Filtering `skills @> ARRAY['sql']` on array `skills TEXT[]`.

Choose candidate index types and explain why a scalar B-tree index differs from a GIN index on arrays. Then inspect `EXPLAIN` on the lab data and explain why indexes may not be used on a small table.

### Exercise 21 — Designing a Multi-Select Filter API

A frontend sends:

~~~text
grade_filter = [1, 3]
grade_filter = []
grade_filter omitted
grade_filter = null
~~~

Define a contract handling all four cases. Should `[]` and "field omitted" be treated identically? If not, which SQL branch should run for each to return the right results?

### Exercise 22 — Choosing Array vs. Junction Table

A product has multiple labels, and each label must track reviewer, creation timestamp, status, and a foreign key to a valid labels catalog. Should you use `text[]` or a relational `product_labels(product_id,label_id,reviewed_by,created_at,status)` table? Discuss pros and cons for FKs, `UNIQUE`, querying, and writes.

## 31. Comprehensive Summary Query Pattern

A management report might simultaneously need:

- Employee count per department;
- How many have the SQL skill;
- How many have an allowed grade according to the rules array;
- How many are missing a grade or a rules array.

Example using `LEFT JOIN` against the rules table:

~~~sql
SELECT
    e.department,
    COUNT(*) AS employee_count,
    COUNT(*) FILTER (
        WHERE 'sql' = ANY(e.skills)
    ) AS sql_skill_count,
    COUNT(*) FILTER (
        WHERE e.grade = ANY(r.allowed_grades)
    ) AS allowed_grade_count,
    COUNT(*) FILTER (
        WHERE e.grade IS NULL
    ) AS missing_grade_count,
    COUNT(*) FILTER (
        WHERE r.allowed_grades IS NULL
    ) AS missing_rule_array_count,
    COUNT(*) FILTER (
        WHERE r.allowed_grades = ARRAY[]::integer[]
    ) AS empty_rule_array_count
FROM expr_lab_180.employees AS e
LEFT JOIN expr_lab_180.department_rules AS r
    ON r.department = e.department
GROUP BY e.department
ORDER BY e.department;
~~~

Interpretation:

- `COUNT(*) FILTER (WHERE 'sql' = ANY(skills))` counts only when membership is **TRUE**, not UNKNOWN.
- `allowed_grade_count` treats a NULL rule neither as allowing all nor forbidding all; it **does not count unconfirmed rows**.
- `missing_rule_array_count` sees all employees with a NULL rule array; for a department with no matching rule row, `r.allowed_grades` is also NULL, so to distinguish **missing rule row** from **rule row with NULL column**, check `r.department IS NULL`.
- `empty_rule_array_count` counts confirmed empty arrays without mixing them with NULLs.

This report demonstrates that using `ANY` inside aggregates is not just for filtering; it also helps classify **true, false, and unknown** when paired with dedicated KPI columns.

### 31.1. Three-State Report for Grade Rules

~~~sql
SELECT
    e.employee_id,
    e.department,
    e.grade,
    CASE
        WHEN r.department IS NULL
            THEN 'No rule found'
        WHEN r.allowed_grades IS NULL
            THEN 'Rule list unknown'
        WHEN e.grade IS NULL
            THEN 'Grade unknown'
        WHEN e.grade = ANY(r.allowed_grades)
            THEN 'Allowed'
        ELSE 'Not allowed'
    END AS rule_decision
FROM expr_lab_180.employees AS e
LEFT JOIN expr_lab_180.department_rules AS r
    ON r.department = e.department
ORDER BY e.employee_id;
~~~

Unlike `WHERE grade = ANY(...)` which only emits TRUE rows, this `CASE` **preserves and explains** NULL/missing-data cases. That is far more helpful when administrators need to know **why** an employee was not confirmed as eligible.

## 32. Summary

**Row constructors** let you compare multiple values **position by position**. `=`/`<>` can return `NULL` on unknown fields; `IS [NOT] DISTINCT FROM` helps when null-safe comparison is needed. `<`/`>` on rows use **lexicographic ordering**, ideal for composite keys and keyset pagination. `(a,b) IN (...)` expresses **allowed pairs** — distinct from two independent `a IN (...) AND b IN (...)` filters.

**PostgreSQL arrays** store homogeneous elements and preserve **order**. `=` compares array values positionally, whereas `@>`, `<@`, and `&&` check containment/overlap without counting duplicates. **Empty arrays**, **NULL arrays**, and **arrays with NULL elements** are three distinct states; `cardinality`, `unnest`, `array_agg`, `array_position`, and `array_remove` handle them deliberately.

**`ANY`/`SOME` means "at least one" and `ALL` means "all"** over the outcomes of a comparison operator. Under SQL three-valued logic, a NULL element can yield UNKNOWN; on **empty sets**, `ANY` returns FALSE and `ALL` returns TRUE. `IN` aligns with `= ANY`, while `NOT IN` aligns with `<> ALL` — **never `<> ANY`**. When source data can contain NULLs and an anti-join is needed, `NOT EXISTS` with an explicit comparison condition is usually safer and clearer.

Finally, choose the right tool for the job: **rows** for key combinations, **arrays** for small homogeneous lists, **subqueries/`EXISTS`** for relational relationships, **B-tree** for scalar filters, and **GIN** for array containment/overlap operators. Writing accurate SQL is not only picking the right syntax; it is defining **what empty sets mean, what NULL represents, and how TRUE/FALSE/UNKNOWN should govern business logic**.
