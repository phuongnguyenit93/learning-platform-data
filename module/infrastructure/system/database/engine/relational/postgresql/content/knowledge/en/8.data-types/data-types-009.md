# Arrays, Element Types, and Array Dimensions in PostgreSQL

## 1. Why Does PostgreSQL Have an Array Data Type?

In the relational model, a table consists of rows and columns. Normally each column stores a single value of a given data type. PostgreSQL extends this capability with **array types**: a single value in a column can hold **multiple elements of the same type**.

For example, a project with three labels:

```text
project_id = 101
project_name = "Query Optimization"
labels = {"postgresql", "performance", "backend"}
```

Instead of creating three columns `label_1`, `label_2`, `label_3`, you can use one column `labels text[]`.

PostgreSQL lets you:

- Declare columns of type `integer[]`, `text[]`, `uuid[]`, `date[]`, and many other array types.
- Construct arrays using `ARRAY[...]` or literal syntax `'{...}'` with an explicit data type.
- Store one-dimensional or multi-dimensional arrays and access elements by subscript.
- Measure dimensions, length per dimension, total element count, and subscript bounds.
- Append/prepend/remove/replace elements, and test containment or overlap.
- Expand array elements into rows with `unnest()`, or aggregate rows into an array with `array_agg()`.
- Build GIN indexes for certain array-element search queries.

Arrays are useful when a small collection of elements represents a single set-valued attribute and is usually processed alongside the parent record. However, arrays are **not the default solution for every one-to-many relationship**. When elements require foreign keys, separate permissions, per-element attributes, or independent updates, a child table is usually a better fit.

This lesson focuses on three questions:

1. **Element type:** what type of data does an array hold?
2. **Size and dimensions:** how long is the array, how many dimensions does it have, and where does indexing start?
3. **Operations:** how to read/write, search, expand, transform, and design schemas properly with arrays?

## 2. Visualizing an Array at the Data Level

A one-dimensional array:

```text
Value:          10      20      30      40
Subscript:       1       2       3       4
               [1]     [2]     [3]     [4]
```

A two-dimensional array:

```text
                  Col 1   Col 2   Col 3
Row subscript 1     1       2       3
Row subscript 2     4       5       6

ARRAY[[1, 2, 3],
      [4, 5, 6]]
```

An array is understood in terms of **dimensions**, **length per dimension**, and **lower/upper bounds** of each dimension.

For `ARRAY[10,20,30,40]`:

- Number of dimensions: 1.
- Length of dimension 1: 4.
- Total elements: 4.
- Default lower bound: 1.
- Upper bound: 4.

For `ARRAY[[1,2,3],[4,5,6]]`:

- Number of dimensions: 2.
- Dimension 1 has length 2.
- Dimension 2 has length 3.
- Total elements: 6.
- The subscript of element `5` is `[2][2]` by default.

**Important note:** PostgreSQL defaults to **1-based** array indexing, not 0-based like Java or JavaScript arrays. PostgreSQL also permits arrays with **lower bounds other than 1** under certain constructions; you cannot always assume the first index is 1 when handling arrays from arbitrary sources.

## 3. Element Types: `integer[]`, `text[]`, `uuid[]`, and Others

### 3.1. Declaration Syntax

Most PostgreSQL data types have a corresponding array type.

```sql
CREATE SCHEMA IF NOT EXISTS array_lab;

CREATE TABLE array_lab.examples (
    example_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scores integer[],
    labels text[],
    prices numeric(12,2)[],
    event_days date[],
    member_ids uuid[],
    flags boolean[]
);
```

Corresponding element types:

| Column | Array Type | Element Type | Example Usage |
|---|---|---|---|
| `scores` | `integer[]` | `integer` | Scores across measurements |
| `labels` | `text[]` | `text` | Short labels |
| `prices` | `numeric(12,2)[]` | `numeric(12,2)` | Illustrative monetary value sequence |
| `event_days` | `date[]` | `date` | List of dates |
| `member_ids` | `uuid[]` | `uuid` | Application-managed reference ID set |
| `flags` | `boolean[]` | `boolean` | Sequence of true/false states |

`numeric(12,2)[]` is an array whose elements follow the declared numeric type; if extra business rules such as non-negativity are needed, add constraints or normalize inputs.

The `integer[]` syntax is widespread. PostgreSQL also understands traditional SQL syntax like `integer ARRAY` in declarations. In modern code, `[]` is usually more concise and readable.

### 3.2. How Are Array Types and Element Types Related?

In PostgreSQL, a base type like `integer` has a corresponding array type (for example, the system has an internal type name for integer arrays). When you declare `integer[]`, you are using the **array type** holding `integer` elements.

Some inspection queries:

```sql
SELECT
    pg_typeof(ARRAY[1, 2, 3]) AS integer_array_type,
    pg_typeof(ARRAY['a', 'b']) AS text_array_type,
    pg_typeof(ARRAY[true, false]) AS boolean_array_type;
```

Typically, the output displays types equivalent to `integer[]`, `text[]`, and `boolean[]`.

Do not write internal underscore-prefixed type names in application SQL just because you saw them in system catalogs. Standard, maintainable syntax is `integer[]`, `text[]`, or the corresponding array type.

### 3.3. Elements Must Have Compatible Types

Valid examples:

```sql
SELECT ARRAY[1, 2, 3]::integer[];
SELECT ARRAY['postgresql', 'sql']::text[];
SELECT ARRAY[DATE '2026-11-14', DATE '2026-11-15']::date[];
```

Example needing explicit type handling:

```sql
-- Do not assume every mix of literals resolves to a valid common type:
SELECT ARRAY[1, 'not-a-number'];
```

PostgreSQL must determine **one common element type** for the array. If a string cannot convert to the inferred type or no compatible type is found, the statement fails. In applications, declare or cast types explicitly rather than relying on implicit conversions on complex inputs.

Example passing integers as valid strings with explicit casts:

```sql
SELECT ARRAY['10'::integer, '20'::integer];
```

### 3.4. Arrays and NULL Elements

An array column itself can be `NULL`, and a **non-NULL** array can still contain `NULL` elements.

```sql
SELECT
    NULL::integer[] AS whole_array_is_null,
    ARRAY[]::integer[] AS empty_but_not_null,
    ARRAY[10, NULL, 30]::integer[] AS array_with_null_element;
```

These three cases **differ**:

| Value | Meaning |
|---|---|
| `NULL::integer[]` | No array value / array unknown |
| `ARRAY[]::integer[]` | Array exists but contains zero elements |
| `ARRAY[10,NULL,30]::integer[]` | Array with three positions, one element is NULL |

Setting `labels text[] NOT NULL` only forbids the **entire array column** from being NULL; it does not stop `labels = ARRAY['a',NULL]::text[]`. If NULL elements must be disallowed, add an extra constraint or choose a relational child table.

## 4. Ways to Construct Array Values

### 4.1. Using `ARRAY[...]`

Intuitive form:

```sql
SELECT ARRAY[10, 20, 30] AS numbers;

SELECT ARRAY['Java', 'PostgreSQL', 'SQL']::text[] AS technologies;

SELECT ARRAY[
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    TIMESTAMPTZ '2026-11-15 09:00:00+07'
] AS meeting_times;
```

`ARRAY[...]` is an array constructor. PostgreSQL evaluates the expressions inside to build the elements.

Use casts like `::integer[]` or `::text[]` when you want exact type specification, especially for empty arrays or untyped parameters.

### 4.2. Empty Arrays Must Specify an Element Type

Avoid writing:

```sql
-- Insufficient element type information:
-- SELECT ARRAY[];
```

PostgreSQL cannot infer an element type from an empty constructor. You need:

```sql
SELECT ARRAY[]::integer[] AS empty_integers;
SELECT ARRAY[]::text[] AS empty_labels;
```

Another form:

```sql
SELECT '{}'::integer[] AS empty_integers;
```

This means an existing array containing **0 elements**, not NULL.

### 4.3. Curly-Brace Array Literals

PostgreSQL supports array input as a **casted string**:

```sql
SELECT '{10,20,30}'::integer[];

SELECT '{"hello","a,b",""}'::text[];
```

In `text[]` literals, elements containing commas, double quotes, backslashes, or special characters require quoting/escaping per array input syntax. Reading and writing text literals becomes error-prone across multiple escaping layers (SQL string, JSON, shell).

**Prefer `ARRAY[...]` or driver parameter binding** in application code. Never concatenate array literal strings from user input manually: beyond SQL injection risks, it is very easy to break escaping or confuse `NULL` with the string `'NULL'`.

### 4.4. Constructors and Literals Are Not Identical

| Expression | How PostgreSQL Interprets It |
|---|---|
| `ARRAY[1,2,3]` | SQL expressions producing elements |
| `'{1,2,3}'::integer[]` | String in array input syntax, parsed into an integer array |
| `ARRAY['a,b','c']` | First element is the string `a,b` |
| `'{"a,b","c"}'::text[]` | Quotes required so the comma stays inside the first element |
| `ARRAY[]::integer[]` | Empty integer array |
| `'{}'::integer[]` | Empty array of the same integer type |

With dates, UUIDs, or enums, explicit casts help prevent type-inference surprises.

## 5. Declared Bounds: Why Doesn't `integer[3]` Limit to Three Elements?

One difference from many programming languages: PostgreSQL lets you write sizes in an array type declaration, yet **does not enforce declared sizes** as a data constraint.

Two declarations:

```sql
CREATE TABLE array_lab.declared_sizes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    expected_three integer[3],
    expected_matrix integer[2][3]
);
```

The numbers `[3]` and `[2][3]` in the declaration **do not require** values to have exactly three elements or a 2×3 matrix. PostgreSQL does not turn these numbers into a length constraint, nor is the declared dimension count enforced as a hard constraint on values.

Example:

```sql
INSERT INTO array_lab.declared_sizes (
    expected_three,
    expected_matrix
)
VALUES (
    ARRAY[1, 2, 3, 4, 5],
    ARRAY[[1, 2], [3, 4]]
);

SELECT
    cardinality(expected_three) AS number_of_elements,
    array_dims(expected_matrix) AS actual_dimensions
FROM array_lab.declared_sizes;
```

Even though the column names and declarations suggest three elements or 2×3, these values retain their own actual dimensions.

**Rule:** to enforce element counts, add an appropriate **`CHECK` constraint** rather than just writing `integer[3]`.

### 5.1. Example Limiting Total Element Count

```sql
CREATE TABLE array_lab.fixed_scores (
    record_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scores integer[] NOT NULL,
    CONSTRAINT scores_exactly_three
        CHECK (cardinality(scores) = 3)
);
```

Now:

```sql
INSERT INTO array_lab.fixed_scores(scores)
VALUES (ARRAY[80, 90, 75]);
```

succeeds, whereas:

```sql
-- Expected CHECK violation:
INSERT INTO array_lab.fixed_scores(scores)
VALUES (ARRAY[80, 90]);
```

is rejected.

**Caution:** `cardinality(scores) = 3` only constrains **total element count**. Having three elements does not automatically guarantee the array is 1-dimensional or has lower bound 1. If an interface or algorithm requires strictly a 1D vector, add shape constraints or normalize inputs.

### 5.2. Why You Should Not Assume "Arrays Always Have Fixed Size"

PostgreSQL arrays are variable-length types. Actual size lives in each **array value**, not locked down by `[n]` in the column type syntax.

This brings flexibility, while requiring the application to govern:

- Maximum number of elements.
- Allowed number of dimensions.
- NULL elements.
- Valid values for each element.
- Whether duplicates are permitted.
- Array size and read/write overhead.

## 6. Measuring Dimensions, Lengths, and Total Elements

These are the key functions for array sizing.

| Function | Returns | Example Meaning |
|---|---|---|
| `array_ndims(a)` | Number of dimensions | 1 for a vector, 2 for a matrix |
| `array_length(a, n)` | Length of the `n`-th dimension | Number of elements along dimension 1 |
| `cardinality(a)` | Total elements across all dimensions | 6 for a 2×3 matrix |
| `array_dims(a)` | Text describing dimension subscript bounds | `[1:2][1:3]` |
| `array_lower(a, n)` | Lower bound of dimension `n` | Usually 1 |
| `array_upper(a, n)` | Upper bound of dimension `n` | Usually equals length if starting at 1 |

### 6.1. Practicing with a One-Dimensional Array

```sql
SELECT
    array_ndims(ARRAY[10,20,30,40]) AS ndims,
    array_length(ARRAY[10,20,30,40], 1) AS len_dim1,
    cardinality(ARRAY[10,20,30,40]) AS total_elements,
    array_dims(ARRAY[10,20,30,40]) AS dimension_bounds,
    array_lower(ARRAY[10,20,30,40], 1) AS lower_bound,
    array_upper(ARRAY[10,20,30,40], 1) AS upper_bound;
```

Expected values:

| ndims | len_dim1 | total_elements | dimension_bounds | lower_bound | upper_bound |
|---:|---:|---:|---|---:|---:|
| 1 | 4 | 4 | `[1:4]` | 1 | 4 |

### 6.2. Practicing with a Two-Dimensional Array

```sql
SELECT
    array_ndims(ARRAY[[1,2,3],[4,5,6]]) AS ndims,
    array_length(ARRAY[[1,2,3],[4,5,6]], 1) AS rows_count,
    array_length(ARRAY[[1,2,3],[4,5,6]], 2) AS columns_count,
    cardinality(ARRAY[[1,2,3],[4,5,6]]) AS total_elements,
    array_dims(ARRAY[[1,2,3],[4,5,6]]) AS dimension_bounds;
```

Result:

```text
ndims            = 2
rows_count       = 2
columns_count    = 3
total_elements   = 6
dimension_bounds = [1:2][1:3]
```

The length of an individual dimension differs from total element count. For a 2×3 matrix, `array_length(..., 1) = 2` while `cardinality(...) = 6`.

### 6.3. Empty Arrays and NULL Values

An easy-to-miss subtlety:

```sql
SELECT
    array_length(ARRAY[]::integer[], 1) AS length_empty,
    cardinality(ARRAY[]::integer[]) AS cardinality_empty,
    cardinality(NULL::integer[]) AS cardinality_null;
```

Important semantics:

- `array_length` on an **empty/nonexistent dimension** returns `NULL`, **not 0**.
- `cardinality` of a **non-NULL empty array** returns `0`.
- `cardinality` of a **NULL array** returns `NULL`.

When counting elements and handling empty arrays, `cardinality()` is usually easier to work with. If the column is nullable and application policy treats NULL as 0:

```sql
SELECT COALESCE(cardinality(NULL::integer[]), 0) AS safe_count;
```

Still, whether NULL and an empty array mean the same thing is a business decision, not something SQL decides automatically.

### 6.4. Nonexistent Dimension

```sql
SELECT
    array_length(ARRAY[10,20,30], 2) AS second_dimension_length,
    array_upper(ARRAY[10,20,30], 2) AS second_dimension_upper;
```

The array above has only one dimension, so querying dimension 2 does not yield a valid length. Do not interpret `NULL` from such queries as evidence that the row contains corrupted data.

## 7. Lower and Upper Subscripts Do Not Always Start at 1

Most arrays built with `ARRAY[...]` are 1-indexed:

```sql
SELECT
    (ARRAY[10, 20, 30])[1] AS first,
    (ARRAY[10, 20, 30])[3] AS third;
```

However, PostgreSQL allows arrays with lower bounds other than 1, such as literals with explicit bounds:

```sql
SELECT '[0:2]={10,20,30}'::integer[] AS zero_based_array;
```

Accessing elements:

```sql
SELECT
    ('[0:2]={10,20,30}'::integer[])[0] AS first_element,
    ('[0:2]={10,20,30}'::integer[])[2] AS last_element,
    array_lower('[0:2]={10,20,30}'::integer[], 1) AS lower_index,
    array_upper('[0:2]={10,20,30}'::integer[], 1) AS upper_index;
```

Expected values: the first element is 10 at subscript 0, and the last element is 30 at subscript 2.

### 7.1. Creating Arrays with Specific Lower Bounds Using `array_fill`

```sql
SELECT
    array_fill(7, ARRAY[3], ARRAY[0]) AS filled_array,
    array_dims(array_fill(7, ARRAY[3], ARRAY[0])) AS bounds;
```

Here:

- `7` is the fill value.
- `ARRAY[3]` specifies one dimension of length 3.
- `ARRAY[0]` sets that dimension's lower bound to 0.

A two-dimensional case:

```sql
SELECT
    array_fill(5, ARRAY[2,3], ARRAY[0,1]) AS matrix,
    array_dims(array_fill(5, ARRAY[2,3], ARRAY[0,1])) AS bounds;
```

The result has **two dimensions**, of lengths 2 and 3; lower bounds are 0 on dimension 1 and 1 on dimension 2.

### 7.2. Why Does This Affect Code?

Never assume `array_length(a,1)` always equals the upper bound. For an array starting at 0 with length 3:

- `array_length(a,1) = 3`.
- `array_lower(a,1) = 0`.
- `array_upper(a,1) = 2`.

When iterating over **actual subscripts**, use `generate_subscripts()` rather than assuming subscripts run from 1 to `cardinality()`.

## 8. Accessing a Single Element and Slicing

### 8.1. Accessing by Subscript

```sql
SELECT
    (ARRAY['SQL', 'PostgreSQL', 'Java'])[1] AS first_item,
    (ARRAY['SQL', 'PostgreSQL', 'Java'])[2] AS second_item;
```

Syntax:

```text
array_expression[subscript]
```

In a `SELECT`, wrap complex array expressions in parentheses before appending `[index]`.

On a column:

```sql
SELECT
    example_id,
    labels[1] AS first_label
FROM array_lab.examples;
```

### 8.2. Out-of-Bounds Subscripts

```sql
SELECT (ARRAY[10,20,30])[9] AS out_of_range;
```

Out-of-bounds **single-element** access in an expression returns `NULL`, rather than throwing an exception like an out-of-bounds array index in Java.

Consequently, a query like:

```sql
SELECT labels[3]
FROM array_lab.examples;
```

can return NULL because there are **fewer than three elements**, because the third element is actually NULL, or because the array column itself is NULL. If your application must distinguish those cases, check `cardinality`, `array_lower/upper`, and array nullness.

### 8.3. Array Slicing

```sql
SELECT
    (ARRAY[10,20,30,40,50])[2:4] AS middle_slice;
```

The slice from index 2 to 4 corresponds to `20,30,40`. Syntax:

```text
array_expression[start_index:end_index]
```

PostgreSQL supports multi-dimensional slicing with corresponding bound pairs. When slicing, distinguish **source array subscripts** from the bounds of the returned sub-array; never assume every slice, concatenation, or assignment preserves or resets bounds identically in all situations.

### 8.4. Confusing Element vs. Slice Syntax

`a[2]` fetches **one element**, whereas `a[2:3]` fetches **a sub-array**. In multi-dimensional arrays, if any dimension uses slice notation, PostgreSQL treats other subscripts in the same expression as slice bounds too; write explicit bounds clearly to avoid unexpected results.

## 9. Multi-Dimensional Arrays: Matrices and Shape

### 9.1. Creating a Two-Dimensional Array

```sql
SELECT ARRAY[
    [1, 2, 3],
    [4, 5, 6]
]::integer[] AS matrix;
```

You can also use a literal:

```sql
SELECT '{{1,2,3},{4,5,6}}'::integer[] AS matrix;
```

Fetching the element at row 2, column 1:

```sql
SELECT
    (ARRAY[[1,2,3],[4,5,6]])[2][1] AS value_4,
    (ARRAY[[1,2,3],[4,5,6]])[2][3] AS value_6;
```

### 9.2. Dimensions Must Have Matching Lengths

PostgreSQL stores multi-dimensional arrays with a **rectangular** shape: sub-arrays at the same nesting level must have matching element counts and dimensions.

Attempt to construct uneven data:

```sql
-- Expected error: sub-arrays have mismatched dimensions.
SELECT ARRAY[
    [1, 2, 3],
    [4, 5]
];
```

This is not a valid 2×3 matrix because the second row has only two elements.

If the business genuinely needs a "list of lists of varying lengths", consider:

- A child table recording each element with coordinates/order.
- A JSONB structure when hierarchical data is irregular and document-oriented.
- Splitting into separate 1D arrays across multiple rows.

Do not rely on PostgreSQL multi-dimensional arrays to store "ragged" arrays of unequal lengths.

### 9.3. Is Each Dimension Count a Different Array Type?

No. `integer[]` and `integer[][]` denote the exact same concept—**an array type with integer elements**; the **value's** dimensionality is determined by the data. PostgreSQL does not create a "special type accepting only 2×3 arrays" just because you wrote `integer[2][3]` in a column definition.

Use `array_ndims()`, `array_length()`, and `CHECK` constraints if your business schema requires a specific shape.

### 9.4. Total Elements and Dimensions

```sql
SELECT
    array_ndims('{{1,2,3},{4,5,6}}'::integer[]) AS dimensions,
    array_length('{{1,2,3},{4,5,6}}'::integer[], 1) AS dim1,
    array_length('{{1,2,3},{4,5,6}}'::integer[], 2) AS dim2,
    cardinality('{{1,2,3},{4,5,6}}'::integer[]) AS total;
```

Expected result: `2` dimensions, `2×3` shape, `6` total elements.

## 10. Updating Array Elements in a Column

### 10.1. Reassigning One Element

Create a small practice table:

```sql
CREATE TABLE array_lab.test_scores (
    student_id bigint PRIMARY KEY,
    scores integer[] NOT NULL DEFAULT ARRAY[]::integer[]
);

INSERT INTO array_lab.test_scores(student_id, scores)
VALUES (101, ARRAY[75, 80, 85]);
```

Update the second element:

```sql
UPDATE array_lab.test_scores
SET scores[2] = 95
WHERE student_id = 101
RETURNING student_id, scores;
```

The value changes from `{75,80,85}` to `{75,95,85}` preserving element order.

### 10.2. Replacing the Whole Array

```sql
UPDATE array_lab.test_scores
SET scores = ARRAY[90, 91, 92, 93]
WHERE student_id = 101
RETURNING scores;
```

This replaces the entire array value with a new four-element array. `integer[]` imposes no length limit unless you add a constraint.

### 10.3. Expanding an Array by Assigning a Distant Subscript

PostgreSQL can extend a **one-dimensional** array when assigning past its upper bound, filling intermediate gaps with NULL.

```sql
UPDATE array_lab.test_scores
SET scores = ARRAY[10,20,30]
WHERE student_id = 101;

UPDATE array_lab.test_scores
SET scores[5] = 50
WHERE student_id = 101
RETURNING scores;
```

The value becomes:

```text
{10,20,30,NULL,50}
```

This is a key reason to enforce **length and non-NULL element** validation/constraints if the application requires dense vectors.

**Do not assume out-of-bounds subscript extension behaves identically on multi-dimensional arrays.** PostgreSQL places restrictions on out-of-bounds extensions and assignments for multi-dimensional arrays.

### 10.4. Conditional Updates and Transactions

If multiple requests modify the same row, array updates contend on the parent row containing the array. In production applications, handle concurrency via transactions, conditional checks, and/or optimistic versioning.

Example:

```sql
UPDATE array_lab.test_scores
SET scores[2] = 98
WHERE student_id = 101
  AND scores[2] = 20
RETURNING student_id, scores;
```

This updates only if the second element is currently 20; returning `0 rows` means the condition no longer holds or the row does not exist. This illustrates a conditional update, not a complete concurrency strategy for every use case.

## 11. Concatenating, Appending, and Replacing Array Elements

PostgreSQL provides array manipulation functions, especially convenient for one-dimensional arrays.

### 11.1. Appending and Prepending

```sql
SELECT array_append(ARRAY[10,20], 30) AS appended;
SELECT array_prepend(5, ARRAY[10,20]) AS prepended;
```

Results:

```text
array_append -> {10,20,30}
array_prepend -> {5,10,20}
```

Each function returns a new array value; they do not modify a table column unless used in an `UPDATE`.

Update example:

```sql
UPDATE array_lab.test_scores
SET scores = array_append(scores, 100)
WHERE student_id = 101
RETURNING scores;
```

This appends an element to the end of the existing array. If duplicates must be prevented, enforce it in business logic; `array_append` **does not deduplicate**.

### 11.2. Concatenating Two Arrays

```sql
SELECT ARRAY[1,2] || ARRAY[3,4] AS combined;
```

Result: `{1,2,3,4}`.

To append a single element, `||` also works in type-compatible contexts, though expressions with untyped string literals can confuse the parser into expecting an **array literal** rather than a single element. To avoid ambiguity:

```sql
SELECT array_append(ARRAY[1,2], 3);
SELECT ARRAY[1,2] || ARRAY[3];
```

Both are far clearer than concatenating an array with an uncast string literal.

### 11.3. `array_cat`

```sql
SELECT array_cat(
    ARRAY['sql','postgresql']::text[],
    ARRAY['jdbc','psql']::text[]
) AS combined_labels;
```

`array_cat` concatenates arrays with compatible dimensionality semantics. On multi-dimensional arrays, concatenation imposes shape and bound rules; never assume it works like flattening two 1D lists in all cases.

### 11.4. Removing or Replacing All Matching Elements

```sql
SELECT array_remove(ARRAY[1,2,1,3], 1) AS removed;
SELECT array_replace(ARRAY[1,2,1,3], 1, 9) AS replaced;
```

Results:

```text
array_remove  -> {2,3}
array_replace -> {9,2,9,3}
```

`array_remove` removes **all** elements matching the given value, not just the first occurrence. It is designed for **one-dimensional** arrays. If you need positional removal or matrix operations, choose a different transformation rather than assuming it works for arbitrary dimensions.

### 11.5. Finding Element Positions

```sql
SELECT array_position(ARRAY[5,10,5,20], 5) AS first_position;

SELECT array_positions(ARRAY[5,10,5,20], 5) AS all_positions;
```

Expected results:

```text
first_position = 1
all_positions  = {1,3}
```

Example searching for a NULL element:

```sql
SELECT array_position(
    ARRAY[10,NULL,30]::integer[],
    NULL
) AS null_element_position;
```

PostgreSQL's array search functions compare elements using *IS NOT DISTINCT FROM* semantics, so they can locate NULL elements. `array_position`/`array_positions` are for one-dimensional arrays; do not use them to locate multi-dimensional coordinates.

## 12. Expanding Arrays into Rows with `unnest()`

This is one of the most important operations when combining arrays with relational SQL.

```sql
SELECT value
FROM unnest(ARRAY[10,20,30]) AS t(value);
```

Result:

| value |
|---:|
| 10 |
| 20 |
| 30 |

`unnest()` expands an array into a **set of rows**. This enables joining, filtering, aggregating, and processing individual elements with standard SQL tools.

### 12.1. Preserving Order with `WITH ORDINALITY`

```sql
SELECT
    u.label,
    u.ordinality
FROM unnest(
    ARRAY['sql','postgresql','java']::text[]
) WITH ORDINALITY AS u(label, ordinality)
ORDER BY u.ordinality;
```

Result:

| label | ordinality |
|---|---:|
| sql | 1 |
| postgresql | 2 |
| java | 3 |

`WITH ORDINALITY` appends a **1-based position column** generated for the output rows. If the source array had a custom lower bound like 0 or -2, `ordinality` still counts emitted elements from 1 and **does not necessarily match the original array subscript**.

### 12.2. `unnest()` on Multi-Dimensional Arrays

```sql
SELECT value
FROM unnest(ARRAY[[1,2],[3,4]]) AS u(value);
```

This expands elements into a flat 1D stream in array storage order, typically observed as 1, 2, 3, 4. If you need **row/column coordinates**, `unnest() WITH ORDINALITY` alone is not enough because ordinality is a flat sequence number.

### 12.3. Getting Actual Subscripts with `generate_subscripts()`

Example 1D array with lower bound 0:

```sql
WITH sample AS (
    SELECT '[0:2]={10,20,30}'::integer[] AS values
)
SELECT
    idx,
    values[idx] AS element_value
FROM sample
CROSS JOIN LATERAL generate_subscripts(values, 1) AS g(idx)
ORDER BY idx;
```

Result:

| idx | element_value |
|---:|---:|
| 0 | 10 |
| 1 | 20 |
| 2 | 30 |

`generate_subscripts(a, dimension)` returns valid subscripts for the specified dimension, making it ideal for non-standard bounds.

### 12.4. Coordinates of a Two-Dimensional Array

```sql
WITH sample AS (
    SELECT ARRAY[[1,2,3],[4,5,6]] AS matrix
)
SELECT
    row_idx,
    col_idx,
    matrix[row_idx][col_idx] AS element_value
FROM sample
CROSS JOIN LATERAL
    generate_subscripts(matrix, 1) AS r(row_idx)
CROSS JOIN LATERAL
    generate_subscripts(matrix, 2) AS c(col_idx)
ORDER BY row_idx, col_idx;
```

Result:

```text
row_idx | col_idx | element_value
--------+---------+--------------
      1 |       1 | 1
      1 |       2 | 2
      1 |       3 | 3
      2 |       1 | 4
      2 |       2 | 5
      2 |       3 | 6
```

Use this pattern when analyzing a matrix that requires coordinates; use `unnest()` when you only need all elements as a flat set.

## 13. Aggregating Rows into an Array with `array_agg()`

The inverse of `unnest()` is typically `array_agg()`.

### 13.1. Aggregating Measurements into an Array

Suppose a relational table records individual readings:

```sql
CREATE TABLE array_lab.measurements (
    sensor_id bigint NOT NULL,
    measured_at timestamptz NOT NULL,
    temperature numeric(6,2) NOT NULL,
    PRIMARY KEY (sensor_id, measured_at)
);
```

Sample data:

```sql
INSERT INTO array_lab.measurements
    (sensor_id, measured_at, temperature)
VALUES
    (1, '2026-11-14 09:00:00+07', 28.50),
    (1, '2026-11-14 09:05:00+07', 28.80),
    (1, '2026-11-14 09:10:00+07', 29.10),
    (2, '2026-11-14 09:00:00+07', 25.00);
```

Aggregating by sensor:

```sql
SELECT
    sensor_id,
    array_agg(temperature ORDER BY measured_at) AS temperatures
FROM array_lab.measurements
GROUP BY sensor_id
ORDER BY sensor_id;
```

`ORDER BY measured_at` **is placed inside the aggregate** to guarantee element ordering in the resulting array. Never assume `array_agg` preserves chronological order without specifying `ORDER BY`.

### 13.2. Aggregating Distinct Elements

```sql
SELECT array_agg(DISTINCT label ORDER BY label) AS distinct_labels
FROM unnest(
    ARRAY['sql','java','sql','postgresql']::text[]
) AS t(label);
```

The result is a sorted deduplicated set of labels. This is a **query-time transformation**, not a constraint forcing an array column in a table to stay deduplicated.

### 13.3. Aggregating an Empty Set

An easy-to-overlook detail: like many other aggregates, `array_agg()` over **zero input rows** returns `NULL`, not an empty array.

```sql
SELECT array_agg(value) AS result
FROM unnest(ARRAY[]::integer[]) AS u(value);
```

If an API requires always returning an array, use:

```sql
SELECT COALESCE(
    array_agg(value ORDER BY value),
    ARRAY[]::integer[]
) AS result
FROM unnest(ARRAY[]::integer[]) AS u(value);
```

When data flows into JSON/APIs, agree explicitly in the application contract on `NULL` vs. `[]`.

### 13.4. `ARRAY(SELECT ...)`

Another way to build an array from a subquery:

```sql
SELECT ARRAY(
    SELECT temperature
    FROM array_lab.measurements
    WHERE sensor_id = 1
    ORDER BY measured_at
) AS temperatures;
```

Unlike `array_agg()` on zero rows, `ARRAY(SELECT ...)` returns an **empty array** when the subquery returns no rows. Both are useful; choose based on how you want `NULL` vs. empty array handled and query readability.

## 14. Searching Elements: `ANY`, `ALL`, and Array Operators

### 14.1. Comparing Against Any Element with `ANY`

Checking whether `20` appears in an array:

```sql
SELECT 20 = ANY(ARRAY[10,20,30]) AS contains_20;
```

Result: `true`.

On the `labels` column:

```sql
SELECT example_id
FROM array_lab.examples
WHERE 'postgresql' = ANY(labels);
```

`ANY` tests a comparison against each array element. When `NULL` is present, SQL's three-valued logic (TRUE/FALSE/UNKNOWN) can affect the outcome, so avoid assuming every `ANY` check always yields a non-NULL Boolean.

### 14.2. Comparing Against All Elements with `ALL`

```sql
SELECT 10 < ALL(ARRAY[20,30,40]) AS less_than_all;
```

Result: `true`.

`ALL` does not mean "the array contains all target labels". It **compares one expression against every element**. For example, `10 < ALL(...)` requires 10 to be less than every element.

On empty arrays, `ANY`/`ALL` follow specific logical rules (vacuously false vs. vacuously true), so check semantics carefully when used in business predicates.

### 14.3. Containment Operators `@>` and `<@`

PostgreSQL provides:

| Operator | Meaning | Example |
|---|---|---|
| `a @> b` | `a` contains all elements of `b` | `ARRAY[1,2,3] @> ARRAY[2,3]` |
| `a <@ b` | `a` is contained in `b` | `ARRAY[2] <@ ARRAY[1,2,3]` |
| `a && b` | Both arrays share at least one common element | `ARRAY[1,2] && ARRAY[2,4]` |
| `a = b` | Both array values are equal per array equality rules | `ARRAY[1,2] = ARRAY[1,2]` |

Example:

```sql
SELECT
    ARRAY[1,2,3] @> ARRAY[2,3] AS contains_all,
    ARRAY[2,3] <@ ARRAY[1,2,3] AS is_contained,
    ARRAY[1,2] && ARRAY[2,4] AS overlaps,
    ARRAY[1,2] = ARRAY[1,2] AS equals;
```

All four evaluate to `true`.

### 14.4. Difference Between Containment and Mathematical Multisets

In PostgreSQL's containment operator, **duplicate counts of an element are not treated as multiplicity requirements**. For example:

```sql
SELECT
    ARRAY[1] @> ARRAY[1,1] AS contains_duplicates,
    ARRAY[1,1] @> ARRAY[1] AS reverse_contains;
```

Both evaluate to `true`, because containment checks element presence, not multiset multiplicity.

If the business rule is "the number 1 must appear at least twice", `@> ARRAY[1,1]` does not check that. Count occurrences via `unnest()`/aggregation or design an appropriate data structure.

### 14.5. Filtering Labels with Multiple Conditions

Suppose a projects table has a `labels text[]` column.

Contains **all** specified labels:

```sql
SELECT project_id, project_name
FROM array_lab.projects
WHERE labels @> ARRAY['postgresql','backend']::text[];
```

Contains **at least one** label:

```sql
SELECT project_id, project_name
FROM array_lab.projects
WHERE labels && ARRAY['postgresql','java']::text[];
```

These two queries express different conditions. `@>` means "contains all required elements", while `&&` means "non-empty intersection".

## 15. GIN Indexes for Arrays

With only a few rows, sequential scans are plenty fast. When a table grows large and queries frequently test containment or overlap, PostgreSQL can leverage a **GIN index** (*Generalized Inverted Index*).

### 15.1. Projects Table with Labels

```sql
CREATE TABLE array_lab.projects (
    project_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_name text NOT NULL,
    labels text[] NOT NULL DEFAULT ARRAY[]::text[],
    CONSTRAINT labels_at_most_12
        CHECK (cardinality(labels) <= 12)
);
```

Insert data:

```sql
INSERT INTO array_lab.projects(project_name, labels)
VALUES
    ('Query Optimization', ARRAY['postgresql','backend','performance']),
    ('Java Application', ARRAY['java','backend']),
    ('Data Reporting', ARRAY['postgresql','reporting']),
    ('API Design', ARRAY[]::text[]);
```

In this table, `labels` cannot be NULL and has at most 12 elements, yet current constraints **do not** yet forbid NULL elements or duplicate labels.

### 15.2. Creating a GIN Index

```sql
CREATE INDEX idx_projects_labels_gin
ON array_lab.projects
USING gin (labels);
```

With the default array operator class, GIN generally supports operators such as:

- `@>`: contains.
- `<@`: is contained by.
- `&&`: overlaps.
- `=`: equals, as supported by the operator class.

Example:

```sql
SELECT project_id, project_name
FROM array_lab.projects
WHERE labels @> ARRAY['postgresql']::text[];
```

Inspect the plan in the lab:

```sql
EXPLAIN
SELECT project_id, project_name
FROM array_lab.projects
WHERE labels @> ARRAY['postgresql']::text[];
```

**Do not expect every query to pick the GIN index.** On small tables, PostgreSQL sees a sequential scan as cheaper. Decisions also depend on statistics, selectivity, element counts, configuration, and write maintenance costs.

### 15.3. When Is GIN Helpful and When Is It Not?

| Query or Workload | What to Consider |
|---|---|
| Finding rows with label X via `labels @> ARRAY['X']` | GIN is typically a good candidate |
| Finding rows with at least one of X/Y via `labels && ARRAY[...]` | GIN can be helpful |
| Filtering via `'X' = ANY(labels)` | Not automatically equivalent for GIN usage; consider rewriting with `@>` |
| Lookup by `project_id` | B-tree primary key is usually appropriate |
| Frequent array updates, very long arrays | GIN carries update/storage overhead; benchmark it |
| Querying label counts or positional access | GIN does not optimize these conditions by default |
| Frequent reporting/joining per label | A normalized relational table is usually better |

Very long arrays make rows and indexes expensive. **GIN is not a justification for stuffing an entire one-to-many relationship into one array column** when elements need independent updates.

## 16. NULL, Empty Arrays, and Schema Constraints for Arrays

### 16.1. Basic Constraints

Suppose a system allows each article to have 0 to 8 tags:

```sql
CREATE TABLE array_lab.articles (
    article_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    tags text[] NOT NULL DEFAULT ARRAY[]::text[],
    CHECK (cardinality(tags) BETWEEN 0 AND 8)
);
```

Meaning:

- Forbids the **entire array** from being NULL.
- Defaults to an empty text array.
- At most 8 **elements**, including NULL elements unless another constraint blocks them.

If the business requires "at least one tag", you can use `cardinality(tags) BETWEEN 1 AND 8`, keeping in mind this does not automatically prohibit NULL elements.

### 16.2. Checking for NULL Elements in a One-Dimensional Array

For 1D arrays, you can use `array_position(a, NULL)` to detect a NULL element:

```sql
SELECT
    array_position(ARRAY['a',NULL,'c']::text[], NULL)
        AS null_position,
    array_position(ARRAY['a','b','c']::text[], NULL)
        AS no_null_position;
```

If `no_null_position` is NULL, no NULL element exists in that 1D array. When designing constraints on complex data, consider **dimensionality**, element type, and empty arrays simultaneously. Positional search functions have dimension restrictions, so never apply a `CHECK` using `array_position` to multi-dimensional inputs without validating shape.

### 16.3. Enforcing a One-Dimensional Shape

If the business requires empty or 1D arrays:

```sql
CREATE TABLE array_lab.one_dimensional_vectors (
    vector_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    numbers integer[] NOT NULL DEFAULT ARRAY[]::integer[],
    CONSTRAINT only_empty_or_one_dimension
        CHECK (
            cardinality(numbers) = 0
            OR array_ndims(numbers) = 1
        )
);
```

This permits empty arrays and 1D arrays. To also require a lower bound of 1:

```sql
ALTER TABLE array_lab.one_dimensional_vectors
ADD CONSTRAINT one_based_or_empty
CHECK (
    cardinality(numbers) = 0
    OR array_lower(numbers, 1) = 1
);
```

This helps when applications expect consistent 1-based indexing. In production, verify existing data before adding constraints.

### 16.4. Duplicate Elements Are a Separate Concern

`integer[]` can hold `{1,1,2}`. `text[]` can hold the same label twice. PostgreSQL does not provide a built-in `UNIQUE` constraint **per element inside an array column** equivalent to `UNIQUE` across rows in a join table.

If element uniqueness is critical and element counts are non-trivial, a child table with `UNIQUE(parent_id, element_value)` is usually clearer, easier to enforce, and better for querying.

## 17. Comparing Arrays with a One-to-Many Child-Table Model

Suppose each project has multiple labels.

### 17.1. Array Approach

```sql
CREATE TABLE array_lab.projects_simple (
    project_id bigint PRIMARY KEY,
    project_name text NOT NULL,
    labels text[] NOT NULL DEFAULT ARRAY[]::text[]
);
```

Advantages:

- Fewer tables.
- Reading a project's full label list is very convenient.
- Fits small label sets with infrequent updates and no per-label metadata.
- Supports GIN for containment/overlap label searches.

Disadvantages:

- No direct foreign key from **each element** of the array to a `tags` table.
- Hard to store metadata like who added a tag, when, or per-tag weights.
- Hard to enforce per-element uniqueness like a simple relational constraint.
- Updating one element rewrites the parent row's array value, creating write contention under concurrency.
- Very long arrays increase storage, TOAST, index, and write overhead.

### 17.2. Normalized Join-Table Approach

```sql
CREATE TABLE array_lab.projects_normalized (
    project_id bigint PRIMARY KEY,
    project_name text NOT NULL
);

CREATE TABLE array_lab.tags (
    tag_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tag_name text NOT NULL UNIQUE
);

CREATE TABLE array_lab.project_tags (
    project_id bigint NOT NULL
        REFERENCES array_lab.projects_normalized(project_id),
    tag_id bigint NOT NULL
        REFERENCES array_lab.tags(tag_id),
    added_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, tag_id)
);
```

Advantages:

- Foreign key integrity on every link.
- Primary key prevents assigning the same tag twice to the same project.
- Can store link-level metadata.
- Easier to query/join/aggregate by tag for complex reports.
- Update individual links without rewriting an entire array.

In return, reading the tag list may require a join or `array_agg()` when assembling API responses.

### 17.3. Which One to Choose?

| Data Characteristic | Array | Join Table |
|---|---|---|
| Small sequence of values, usually read/written with parent row | Good fit | May be over-engineered |
| Elements have their own metadata | Difficult | Good fit |
| Need foreign keys for each element | Not directly | Good fit |
| Need uniqueness for each element | Needs extra checks | Clear `PRIMARY KEY/UNIQUE` |
| High-concurrency independent element updates | Consider parent row write cost | Usually better |
| Filtering "has label X" | GIN can fit | Index on join table also fits |
| Frequent aggregation, counting, joining per element | `unnest` works but adds conversion cost | Natural in relational SQL |
| Element count may grow very large | Exercise caution | Usually easier to scale and maintain |

**Design rule:** use an array when a small list is genuinely a **set-valued attribute** of the row; use a child table when each element is an **entity or relationship with its own lifecycle**.

## 18. Arrays, JSONB, and Other Collection Types

PostgreSQL offers multiple collection structures to distinguish:

| Type | Characteristics | When Suitable |
|---|---|---|
| `integer[]`, `text[]` | Homogeneous elements; dimensions, subscripts, and array operators | Numeric sequences, simple labels |
| `jsonb` | Flexible JSON structure with nested objects/arrays and mixed element types | Semi-structured payloads, flexible configs |
| Child table | Rows with keys, constraints, and dedicated indexes | Core one-to-many relationships |
| Range types | Intervals such as `int4range`/`tstzrange` | Value ranges, time schedules |
| `hstore` (extension) | Text key-value pairs | Certain simple dynamic attribute bags |

Example:

```sql
SELECT
    ARRAY[10,20,30]::integer[] AS typed_array,
    '[10,20,"thirty"]'::jsonb AS heterogeneous_json;
```

`integer[]` enforces integer element types. JSONB can mix numbers and strings, with different indexing, querying, and constraint semantics.

A JSON array can contain sub-arrays of varying lengths, whereas PostgreSQL multi-dimensional arrays require rectangular shapes. Never force heterogeneous JSON arrays into `integer[][]` just because both print with brackets.

## 19. Using Arrays as Parameters for Safe Queries

### 19.1. Matching Multiple IDs with `ANY($1)`

Suppose an application needs projects whose IDs belong to a user's authorized list:

```sql
SELECT project_id, project_name
FROM array_lab.projects
WHERE project_id = ANY($1::bigint[]);
```

`$1` is a PostgreSQL parameter placeholder in a prepared statement/driver, **not a built-in variable when running directly in psql**. Bind an actual `bigint[]` parameter value.

For a valid list of IDs, this avoids building `IN (1,2,3,...)` SQL strings via uncontrolled text concatenation.

### 19.2. Java/JDBC Example with PostgreSQL Arrays

Abbreviated Java snippet assuming an open `java.sql.Connection connection` and pgJDBC dependency:

```java
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class ArrayQueryExample {
    public static void findProjects(Connection connection)
            throws SQLException {

        String sql = """
            SELECT project_id, project_name
            FROM array_lab.projects
            WHERE labels @> ?::text[]
            ORDER BY project_id
            """;

        Array labels = connection.createArrayOf(
            "text",
            new String[] {"postgresql"}
        );

        try {
            try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
                statement.setArray(1, labels);

                try (ResultSet rs = statement.executeQuery()) {
                    while (rs.next()) {
                        System.out.println(
                            rs.getLong("project_id")
                            + ": "
                            + rs.getString("project_name")
                        );
                    }
                }
            }
        } finally {
            labels.free();
        }
    }
}
```

This uses **Java 15+ text blocks**; datasource configuration, connection pooling, application-level exception handling, and database privileges are omitted for brevity.

Explanation:

- `createArrayOf("text", ...)` creates the appropriate JDBC `Array` object.
- `setArray(...)` binds it to a prepared statement instead of manually building `'{...}'` literals.
- `?::text[]` makes the SQL parameter type explicit.
- Label strings are passed as bound data, never concatenated into SQL.
- Statement, result set, and JDBC `Array` resources are released properly.

To read an array column from a result set:

```java
Array sqlArray = rs.getArray("labels");
if (sqlArray != null) {
    try {
        String[] labels = (String[]) sqlArray.getArray();
        // Use the array elements.
    } finally {
        sqlArray.free();
    }
}
```

This snippet illustrates reading from an open `ResultSet rs`; the concrete Java type returned by `getArray()` depends on the SQL type and driver. For `integer[]`, you may receive a wrapper array or matching structure; never blindly cast every PostgreSQL array to `String[]`.

### 19.3. SQL Arrays and Java Arrays Do Not Share the Same Index Base

Java arrays are **0-indexed**:

```java
String[] values = {"A", "B", "C"};
String first = values[0];
```

In PostgreSQL, arrays created via `ARRAY['A','B','C']` normally start at `[1]`. When mapping across drivers, understand how indices translate to avoid off-by-one bugs.

Furthermore, element ordering is an intrinsic property of arrays, yet when unnesting to SQL rows and aggregating back, specify `ORDER BY` explicitly to preserve order.

## 20. Performance and Limits as Arrays Grow Large

### 20.1. Modifying One Element Still Updates the Same Row

When updating a project's `labels`, PostgreSQL writes a new row version containing the array under MVCC. The array may live inline or in TOAST if large; the operation is not an in-place single-byte edit to a flat file.

Therefore, if two transactions continually append labels to **the same project row**, they contend on that row. Choose a join table when elements undergo frequent independent updates.

### 20.2. Long Arrays Are Not Automatically Cheap Just Because They Occupy One Column

With thousands of elements in one column:

- `SELECT` results returning large arrays consume substantial bandwidth.
- Array updates generate new row versions and impact TOAST/WAL.
- GIN indexes grow in size and update cost.
- Repeated `unnest`, filtering, sorting, and aggregation carry significant CPU/memory cost.
- Indexes and planner statistics may need tuning for the workload.

Arrays are bounded by PostgreSQL's value and column size limits; never cram huge datasets into an array merely because `integer[3]` is not enforced. Storing millions of items usually calls for relational tables, partitioning, specialized storage, or a better-suited model.

### 20.3. Inspecting Plans with `EXPLAIN`

```sql
EXPLAIN
SELECT project_id
FROM array_lab.projects
WHERE labels && ARRAY['postgresql','java']::text[];
```

With sufficient permissions and lab data, inspect execution details with:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT project_id
FROM array_lab.projects
WHERE labels && ARRAY['postgresql','java']::text[];
```

`EXPLAIN ANALYZE` **actually executes the query**; safe for lab `SELECT`s, but never run it on mutating production `UPDATE`/`DELETE` statements without proper safeguards. Timings and plans depend on the environment and actual data.

## 21. Common Mistakes

### 21.1. Confusing `integer[3]` with a Three-Element Limit

Declared sizes in array types are not enforced as constraints. When exactly three scores are required, use `CHECK (cardinality(scores) = 3)` alongside appropriate shape/element checks.

### 21.2. Assuming Index 0 Works for Every Array

`ARRAY[10,20,30]` starts at 1 by default. `a[0]` normally returns NULL, not the first element. Yet arrays with lower bound 0 can exist, so check `array_lower()` when handling general inputs.

### 21.3. Using `array_length(a,1) = 0` to Check for Empty Arrays

On an empty array, `array_length(...,1)` returns NULL, so comparing `= 0` fails to match. Use `cardinality(a) = 0` to test for non-NULL empty arrays.

### 21.4. Failing to Distinguish NULL from `{}`

`NULL::text[]` means no array value; `'{}'::text[]` is an empty array. Pick explicit semantics and use `NOT NULL DEFAULT ARRAY[]::text[]` if an array should always exist.

### 21.5. Thinking `NOT NULL` Blocks NULL Elements

`labels text[] NOT NULL` does not prevent `ARRAY['sql',NULL]`. If NULL elements violate business rules, enforce it via schema constraints or application validation.

### 21.6. Writing Ragged Two-Dimensional Arrays

`ARRAY[[1,2,3],[4,5]]` is not a valid matrix shape. PostgreSQL requires matching lengths across sub-arrays in multi-dimensional arrays.

### 21.7. Thinking `@>` Counts Duplicate Occurrences

`ARRAY[1] @> ARRAY[1,1]` evaluates to TRUE. Containment does not enforce duplicate counts. Count elements explicitly when multiplicity matters.

### 21.8. Forgetting Ordering in `array_agg()`

Without `ORDER BY` inside the aggregate, element order is not guaranteed to match business intent. Use `array_agg(value ORDER BY timestamp_or_position)`.

### 21.9. Thinking `unnest() WITH ORDINALITY` Returns Original Subscripts

`ordinality` numbers emitted elements from 1, which may not match a custom lower bound on the source array. Use `generate_subscripts()` when real subscripts are needed.

### 21.10. Forgetting `tenant_id` or Join Keys When Aggregating Arrays

In multi-tenant systems, running `array_agg` over labels or IDs without filtering by tenant can mix data across organizations. Arrays are a data type, **not an access-control mechanism**. RLS, `WHERE` predicates, and proper constraints remain mandatory.

### 21.11. Choosing Arrays for Relationships Needing Per-Element Foreign Keys

For example, `customer_ids bigint[]` cannot attach a foreign key to each element inside the array. When guaranteeing every customer exists and belongs to the right tenant, a join table with explicit FKs is generally better.

### 21.12. Switching `text[]` to JSONB Without Updating Query Semantics

SQL arrays and JSON arrays differ in element typing, indexing, operators, and NULL handling. Update queries and constraints when switching models instead of slapping casts on errors.

### 21.13. Writing `'x' = ANY(labels)` Expecting GIN to Always Apply

GIN natively accelerates array operators like `@>`, `<@`, and `&&`. The planner does not necessarily use a GIN index the same way for a scalar `= ANY` expression. Check query plans and pick matching predicates and indexes.

## 22. End-to-End Practice Exercise

This section uses a **lab** database where your role has schema/table creation privileges; do not run on production.

### Step 1: Create a Table with Tag Arrays

```sql
CREATE SCHEMA IF NOT EXISTS array_lab;

CREATE TABLE array_lab.work_items (
    work_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    tags text[] NOT NULL DEFAULT ARRAY[]::text[],
    effort_estimates integer[] NOT NULL DEFAULT ARRAY[]::integer[],
    CHECK (cardinality(tags) <= 10),
    CHECK (cardinality(effort_estimates) <= 5)
);
```

The table has two array columns:

- `tags text[]`: sequence of tags.
- `effort_estimates integer[]`: sequence of estimated effort hours across planning rounds.

Both default to empty arrays, though neither currently blocks duplicates or NULL elements.

### Step 2: Insert Data

```sql
INSERT INTO array_lab.work_items(title, tags, effort_estimates)
VALUES
    (
        'Optimize report queries',
        ARRAY['postgresql','sql','performance']::text[],
        ARRAY[8,6,5]
    ),
    (
        'Build new API',
        ARRAY['java','api']::text[],
        ARRAY[12,10]
    ),
    (
        'Update documentation',
        ARRAY[]::text[],
        ARRAY[3]
    )
RETURNING work_id, title, tags, effort_estimates;
```

### Step 3: Count and Access Elements

```sql
SELECT
    work_id,
    title,
    tags[1] AS first_tag,
    cardinality(tags) AS tag_count,
    array_length(effort_estimates,1) AS estimates_count,
    effort_estimates[1] AS first_estimate
FROM array_lab.work_items
ORDER BY work_id;
```

For the documentation row with an empty tag array:

- `first_tag` returns NULL.
- `tag_count` equals 0.
- The effort array has one element: 3.

### Step 4: Append a Tag

```sql
UPDATE array_lab.work_items
SET tags = array_append(tags, 'review')
WHERE title = 'Update documentation'
RETURNING title, tags;
```

Because `array_append` does not check for duplicates, running this twice appends `'review'` twice. When unique tags are required, enforce uniqueness in the application or use a join table.

### Step 5: Find PostgreSQL-Related Work Items

```sql
SELECT work_id, title, tags
FROM array_lab.work_items
WHERE tags @> ARRAY['postgresql']::text[]
ORDER BY work_id;
```

With larger data and frequent tag queries, you can add:

```sql
CREATE INDEX idx_work_items_tags_gin
ON array_lab.work_items USING gin(tags);
```

### Step 6: Expand Tags into Rows

```sql
SELECT
    w.work_id,
    w.title,
    tag.tag_value,
    tag.ordinality
FROM array_lab.work_items AS w
CROSS JOIN LATERAL
    unnest(w.tags) WITH ORDINALITY AS tag(tag_value, ordinality)
ORDER BY w.work_id, tag.ordinality;
```

Each tag element becomes a row. For empty arrays, `CROSS JOIN LATERAL unnest(...)` emits zero rows for that work item. To retain work items with no tags, consider `LEFT JOIN LATERAL ... ON true`.

### Step 7: Re-Aggregate into an Ordered Array

```sql
SELECT
    work_id,
    array_agg(tag_value ORDER BY ordinality) AS rebuilt_tags
FROM (
    SELECT
        w.work_id,
        tag.tag_value,
        tag.ordinality
    FROM array_lab.work_items AS w
    CROSS JOIN LATERAL
        unnest(w.tags) WITH ORDINALITY
        AS tag(tag_value, ordinality)
) AS exploded
GROUP BY work_id
ORDER BY work_id;
```

Work items without tags do not appear here because the subquery produces no rows for them. If an API must return every work item, use `LEFT JOIN LATERAL` and handle empty sets/NULLs appropriately.

### Step 8: Inspect a Two-Dimensional Array

```sql
SELECT
    array_ndims(ARRAY[[1,2,3],[4,5,6]]) AS dimensions,
    array_length(ARRAY[[1,2,3],[4,5,6]], 1) AS rows_count,
    array_length(ARRAY[[1,2,3],[4,5,6]], 2) AS columns_count,
    cardinality(ARRAY[[1,2,3],[4,5,6]]) AS total_elements;
```

Expected: 2 dimensions, 2 rows, 3 columns, and 6 elements.

### Step 9: Compare Empty Arrays with NULL

```sql
SELECT
    cardinality(ARRAY[]::text[]) AS empty_count,
    array_length(ARRAY[]::text[],1) AS empty_length,
    cardinality(NULL::text[]) AS null_count,
    ARRAY[]::text[] IS NULL AS empty_is_null,
    NULL::text[] IS NULL AS null_is_null;
```

Expected:

```text
empty_count  = 0
empty_length = NULL
null_count   = NULL
empty_is_null = false
null_is_null  = true
```

### Step 10: Inspect Query Plan

```sql
EXPLAIN
SELECT work_id, title
FROM array_lab.work_items
WHERE tags && ARRAY['postgresql','java']::text[];
```

On tiny sample data, PostgreSQL may pick a sequential scan even with a GIN index present. That does not mean the index is broken; gather representative data and statistics before evaluating real index impact.

## 23. Questions and Exercises with Solutions

### Exercise 1. Does `integer[4]` Automatically Limit to 4 Elements?

Given:

```sql
CREATE TABLE array_lab.demo_size (
    numbers integer[4]
);
```

**Question:** can a 5-element array be stored?

**Solution:** yes, because the `4` in the array type declaration is not enforced by PostgreSQL. To enforce exactly 4 elements, use a constraint such as `CHECK (cardinality(numbers) = 4)` paired with `NOT NULL` and suitable shape checks.

### Exercise 2. How Many Elements Does This Array Have?

```sql
SELECT cardinality(ARRAY[[10,20,30],[40,50,60]]);
```

**Solution:** 6. This is a 2×3 matrix, so total elements equal 2 times 3, not 2 or 3.

### Exercise 3. Is the First Element Always `a[1]`?

Given:

```sql
SELECT '[0:2]={10,20,30}'::integer[];
```

**Solution:** no. This array starts at 0; its first element is `a[0]`. Use `array_lower(a,1)` to inspect the lower bound instead of assuming 1 for all sources.

### Exercise 4. Why Is Checking for Empty Arrays with `array_length = 0` Wrong?

```sql
SELECT array_length(ARRAY[]::text[],1);
```

**Solution:** the function returns NULL for a nonexistent/empty dimension. Use `cardinality(a) = 0` when `a` is a non-NULL array.

### Exercise 5. Finding Both Labels

You have a `labels text[]` column and want records containing both `postgresql` and `backend`.

**Solution:**

```sql
SELECT *
FROM array_lab.projects
WHERE labels @> ARRAY['postgresql','backend']::text[];
```

If you only need at least one of the two labels, use `&&` instead of `@>`.

### Exercise 6. Is an Array with a NULL Element a NULL Array?

```sql
SELECT ARRAY[1,NULL,3]::integer[];
```

**Solution:** no. It is a non-NULL array with three elements whose second element is NULL. Column-level `NOT NULL` does not prevent this.

### Exercise 7. Does `array_agg()` Guarantee Ordering?

A table stores sensor readings with corresponding timestamps.

**Solution:** never rely on arbitrary row order. Use:

```sql
SELECT array_agg(temperature ORDER BY measured_at)
FROM array_lab.measurements
WHERE sensor_id = 1;
```

`ORDER BY` goes inside the aggregate to sort array elements.

### Exercise 8. Ragged Two-Dimensional Array

```sql
SELECT ARRAY[[1,2,3],[4,5]];
```

**Solution:** invalid for a rectangular multi-dimensional array. Sub-arrays must have matching dimensions, e.g., `ARRAY[[1,2,3],[4,5,6]]`.

### Exercise 9. Should Thousands of Order IDs Be Stored in `customer.orders bigint[]`?

**Solution:** generally no. Orders are entities with their own attributes, statuses, relationships, foreign keys, and independent update lifecycles. Create an `orders` table with a `customer_id` foreign key. Arrays fit small value sequences attached to a record, not core multi-entity relationships.

### Exercise 10. Can a Foreign Key Be Attached to Each Element of `member_ids uuid[]`?

**Solution:** PostgreSQL does not provide standard per-element foreign-key syntax on array columns like it does for scalar columns. When referential integrity is required, use a join table `project_members(project_id, member_id)` with proper foreign keys.

### Exercise 11. How Do `unnest WITH ORDINALITY` and `generate_subscripts` Differ?

**Solution:** `unnest WITH ORDINALITY` emits rows in element order with a 1-based ordinal; `generate_subscripts(a,n)` returns the **actual valid subscripts** of dimension `n`, including arrays with 0 or negative lower bounds. For matrices needing coordinates, use `generate_subscripts` on each dimension.

### Exercise 12. Why Does the Planner Still Scan the Table After Adding a GIN Index?

**Solution:** on small tables or low-selectivity predicates, a sequential scan can be cheaper. GIN also does not optimize every operator or workload. Inspect with `EXPLAIN` on representative data, measure write overhead, and review statistics.

## 24. Quick Reference Table

| Need | PostgreSQL Syntax | Notes |
|---|---|---|
| Declare integer array | `numbers integer[]` | Element type is integer |
| Declare text array | `labels text[]` | Works with GIN for supported operators |
| 1D constructor | `ARRAY[1,2,3]` | Usually 1-indexed |
| 2D constructor | `ARRAY[[1,2],[3,4]]` | Rectangular shape |
| Empty array | `ARRAY[]::integer[]` | Requires element type |
| Array literal | `'{1,2,3}'::integer[]` | Text syntax with escaping rules |
| Access element | `a[2]` | Out of bounds typically returns NULL |
| Slice | `a[2:4]` | Returns sub-array |
| Count dimensions | `array_ndims(a)` | Actual dimensionality of the value |
| Length of dim 1 | `array_length(a,1)` | Returns NULL on empty array |
| Total elements | `cardinality(a)` | Returns 0 on empty array |
| Subscript bounds | `array_lower(a,1)`, `array_upper(a,1)` | Do not assume 1 in all cases |
| Describe bounds | `array_dims(a)` | E.g., `[1:2][1:3]` |
| Create array with bounds | `array_fill(7, ARRAY[3], ARRAY[0])` | Length 3, starting at 0 |
| Append | `array_append(a, x)` | Does not deduplicate |
| Prepend | `array_prepend(x, a)` | On compatible arrays |
| Concatenate arrays | `a || b` or `array_cat(a,b)` | Requires compatible types/shapes |
| Remove value | `array_remove(a,x)` | Removes all occurrences in 1D array |
| Replace value | `array_replace(a,old,new)` | Replaces matching elements |
| Find position | `array_position(a,x)` | One-dimensional array |
| Expand to rows | `unnest(a)` | Elements become row set |
| Keep expansion order | `unnest(a) WITH ORDINALITY` | 1-based ordinal, not always subscript |
| Get real subscripts | `generate_subscripts(a,1)` | Respects lower/upper bounds |
| Aggregate to array | `array_agg(x ORDER BY y)` | Specify order explicitly |
| Contains value x? | `x = ANY(a)` | Watch NULLs and comparisons |
| Contains all values | `a @> b` | Ignores duplicate counts |
| Shares common element | `a && b` | Can use GIN |
| Create GIN index | `CREATE INDEX ... USING gin (labels)` | Works with matching operators |
| Length constraint | `CHECK (cardinality(a) <= 10)` | `integer[10]` does not enforce automatically |
| Default empty array | `NOT NULL DEFAULT ARRAY[]::text[]` | Does not forbid NULL elements |
| Per-element foreign key | Usually choose a join table | Arrays do not replace relational FKs |

## 25. Summary: Understanding Element Types and Actual Dimensions

Keep three layers clearly separated when using arrays in PostgreSQL:

**First, element type.** `integer[]`, `text[]`, `uuid[]`, etc. define what values the array can hold. Arrays consist of elements of one common type (or convertible to it). An array containing `NULL` elements can still be a non-NULL array value.

**Second, actual shape.** Every array has dimensions, lengths, and bounds carried in the value itself. Writing `integer[3]` or `integer[2][3]` **does not automatically enforce** length or dimension constraints. Use `array_ndims`, `array_length`, `cardinality`, `array_lower`, `array_upper`, and `array_dims` to inspect data, paired with `CHECK` constraints when business rules require a specific structure.

**Third, model selection.** Functions like `unnest`, `array_agg`, `array_append`, `@>`/`&&` operators, and GIN indexes make arrays highly practical for small lists inside a row. Yet when elements require foreign keys, per-element uniqueness, metadata, permissions, or independent updates, a normalized relational table is usually the better choice.

Mastering these three areas prevents subscript, length, NULL, multi-dimensional, and maintainability pitfalls while letting you leverage PostgreSQL's powerful array types effectively.
