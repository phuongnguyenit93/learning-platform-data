# Operators, Precedence, and Expression Evaluation in PostgreSQL

A SQL query can contain many operations at once: addition and subtraction, comparisons, string concatenation, `NULL` checks, `AND`/`OR` conditions, JSONB access, type casting, and function calls. PostgreSQL must understand **which operator binds to which operands** before it can process data.

Compare:

```sql
SELECT 10 + 5 * 2 AS result_a;
SELECT (10 + 5) * 2 AS result_b;
```

The results are **20** and **30**, respectively. With the same numbers, just changing the parentheses alters the meaning of the expression. In a complex `WHERE` clause, the wrong order of `AND`/`OR` can filter orders incorrectly; in financial reporting, type casting or integer division can drop the decimal part; in JSONB queries, placing `::integer` in the wrong position can cause an error.

This lesson belongs to the **Functions and Expressions** chapter of PostgreSQL and helps you:

- Identify groups of **operators and expression structures**.
- Understand **operator precedence** and **associativity**.
- Use parentheses to express business rules accurately.
- Distinguish **syntax parsing** from **runtime evaluation order**.
- Understand **TRUE / FALSE / UNKNOWN** logic when expressions contain `NULL`.
- Avoid relying on unguaranteed **short-circuiting** in SQL conditions.
- Write safe expressions with `CASE`, `COALESCE`, `NULLIF`, and explicit casts.
- Combine PostgreSQL operators for arrays, JSONB, strings, date/time, and comparisons.

This document uses standalone examples and a test schema so you can verify results yourself.

## 1. What Is an Expression in SQL?

An **expression** is a construct evaluated by PostgreSQL to produce a value or a logical result. An expression may consist of:

- **Constants:** `100`, `'PAID'`, `DATE '2026-01-01'`, `TRUE`, `NULL`.
- **Column references:** `amount`, `o.status`, `payload`.
- **Operators:** `+`, `*`, `=`, `<>`, `AND`, `OR`, `||`, `->>`.
- **Functions:** `round(...)`, `lower(...)`, `date_trunc(...)`, `nullif(...)`.
- **Type casts:** `amount::numeric`, `CAST(value AS integer)`.
- **Conditional expressions:** `CASE WHEN ... THEN ... ELSE ... END`.
- **Subqueries:** `EXISTS (SELECT ...)` or a subquery returning a single value.

Example:

```sql
SELECT
    120000::numeric(12, 2) AS gross_amount,
    120000::numeric(12, 2) - 10000 AS net_amount,
    (120000 - 10000) >= 100000 AS reached_target,
    CASE
        WHEN (120000 - 10000) >= 100000 THEN 'Met'
        ELSE 'Not met'
    END AS evaluation;
```

Each item in the `SELECT` list is an expression with a defined value and data type. Not every operator returns a Boolean: `+` returns a number, `||` can return a string, `->>` returns text from JSON, while `IS NULL` returns a Boolean.

### 1.1. Unary and Binary Operators

| Kind | Example | Meaning |
| --- | --- | --- |
| Unary | `-amount` | Negates the sign of a numeric value |
| Unary | `NOT condition` | Negates a Boolean expression |
| Binary | `amount - discount` | Subtracts two values |
| Binary | `a = b` | Equality comparison |
| Binary | `text_a || text_b` | Concatenates strings with compatible operand types |
| Binary | `payload ->> 'source'` | Extracts a JSON field as text |

The same symbol can carry different meanings depending on the operand types. For example, `-` in `-5` is unary, whereas `10 - 5` is binary.

### 1.2. PostgreSQL Supports Operator Overloading

PostgreSQL has an **operator overloading** mechanism: the same operator name can be defined for multiple data types.

For instance, `||` can concatenate `TEXT`, arrays, or JSONB data according to their respective rules; `@>` can mean "contains" for JSONB, arrays, or ranges. You should not guess the result just by looking at the symbol; you must consider **the operand data types and the resolved operator definition**.

## 2. Precedence: How Does PostgreSQL Parse Expressions?

**Operator precedence** specifies which constructs are **syntactically bound first** when an expression has no parentheses. This is a rule of the parser, distinct from the question of "which part the executor runs first over time."

Example:

```sql
SELECT
    10 + 5 * 2     AS without_parentheses,
    10 + (5 * 2)   AS explicit_default,
    (10 + 5) * 2   AS changed_meaning;
```

Results: `20`, `20`, and `30`.

Because multiplication has higher precedence than addition, the first expression is interpreted like the second. The parentheses in the third expression **intentionally change how the operations are grouped**.

### 2.1. Common Precedence Table

The table below lists **from highest to lowest precedence** according to modern PostgreSQL rules:

| Level | Syntax / Operator | Role |
| ---: | --- | --- |
| 1 | `.` | Table/column name separator or field access with appropriate syntax |
| 2 | `::` | PostgreSQL-style type cast |
| 3 | `[ ]` | Array element or slice access |
| 4 | Unary `+`, `-` | Unary plus and minus signs |
| 5 | `COLLATE` | Selects collation for an expression |
| 6 | `AT` | Constructs such as `AT TIME ZONE` |
| 7 | `^` | Exponentiation |
| 8 | `*`, `/`, `%` | Multiplication, division, modulo |
| 9 | Binary `+`, `-` | Addition, subtraction |
| 10 | Other operators | For example `||`, `->`, `->>`, `@>`, or user-defined operators |
| 11 | `BETWEEN`, `IN`, `LIKE`, `ILIKE`, `SIMILAR` | Set, range, and string pattern checks |
| 12 | `<`, `>`, `=`, `<=`, `>=`, `<>` | Standard comparisons |
| 13 | `IS`, `ISNULL`, `NOTNULL` | Checks such as `IS NULL` |
| 14 | `NOT` | Boolean negation |
| 15 | `AND` | Logical conjunction |
| 16 | `OR` | Logical disjunction |

Some SQL constructs have special grammar rules; do not use this table as a mechanical formula to parse every form of `NOT BETWEEN`, `IS DISTINCT FROM`, or complex custom operators. **Parentheses are always the clearest way to express intent.**

In PostgreSQL, most operators at the same precedence level have a defined associativity rule. Notably, PostgreSQL's exponentiation operator `^` is **left-associative**, unlike some mathematical tools.

### 2.2. Associativity: How Are Operators of Equal Precedence Grouped?

```sql
SELECT
    20 - 5 - 3 AS left_associative,
    20 - (5 - 3) AS grouped_right;
```

Results:

```text
left_associative = 12    -- (20 - 5) - 3
grouped_right    = 18    -- 20 - (5 - 3)
```

Both binary `-` operators are at the same precedence level, and standard parsing binds them from left to right.

A PostgreSQL-specific example:

```sql
SELECT
    2 ^ 3 ^ 2       AS left_associative_power,
    2 ^ (3 ^ 2)     AS explicit_right_power;
```

The results are **64** and **512**, respectively: `(2 ^ 3) ^ 2 = 64`, whereas `2 ^ (3 ^ 2) = 512`. Do not carry assumptions from Python or a handheld calculator into PostgreSQL when using exponentiation.

### 2.3. Unary Minus and Exponentiation

When a unary minus and exponentiation appear together, use parentheses to avoid misunderstandings about precedence rules:

```sql
SELECT
    -(2 ^ 2) AS negative_power,
    (-2) ^ 2 AS power_of_negative;
```

The results are **-4** and **4**, respectively. Parenthesized expressions are both easier to inspect and easier to port to other languages with potentially different precedence rules.

## 3. Arithmetic Operator Group

Common arithmetic operators:

| Operator | Example | Meaning |
| --- | --- | --- |
| `+` | `7 + 3` | Addition |
| `-` | `7 - 3` | Subtraction |
| `*` | `7 * 3` | Multiplication |
| `/` | `7 / 3` | Division |
| `%` | `7 % 3` | Modulo for supported types |
| `^` | `2 ^ 3` | Exponentiation for supported types |
| `-value` | `-7` | Sign negation |

Example:

```sql
SELECT
    7 + 3 AS sum_value,
    7 - 3 AS difference,
    7 * 3 AS product,
    7 % 3 AS remainder,
    2 ^ 3 AS power_value;
```

### 3.1. Integer Division and Decimal Division

In PostgreSQL, the result depends on the **types of the operands**:

```sql
SELECT
    7 / 2 AS integer_division,
    7::numeric / 2 AS numeric_division,
    7.0 / 2 AS decimal_division;
```

With integer division, the fractional part is truncated: `7 / 2 = 3`. When at least one operand is converted to an appropriate decimal type, the result can be `3.5`.

This is a common trap in ratio calculations:

```sql
-- Can lose the fractional part if both are integers.
SELECT 1 / 4 AS incorrect_rate;

-- Explicit cast to preserve the fractional part.
SELECT 1::numeric / 4 AS correct_rate;
```

The results are `0` and `0.25`, respectively.

### 3.2. Numeric, Floating Point, and Currency

When computing final prices, discounts, or figures requiring exact decimal precision:

```sql
SELECT
    (120000::numeric(12, 2) - 10000) / 3
        AS amount_per_part;
```

`NUMERIC` is suitable for decimal calculations requiring exactness; `REAL` and `DOUBLE PRECISION` represent binary floating point and can introduce rounding errors. Even when using `NUMERIC`, you must still define **when to round, how many digits to keep, and which currency unit to handle**.

Rounding each line before summing versus rounding the total after summing can produce different results. That is a business decision and should be expressed with clear parentheses and formulas.

### 3.3. Operations Do Not Automatically Guard Against Overflow and Division by Zero

```sql
-- DO NOT run unless you want to trigger a division_by_zero error:
-- SELECT 100 / 0;
```

Operands of type `INTEGER`/`BIGINT` also have value range limits. An operation exceeding a type's range can raise an error rather than automatically converting to an arbitrarily large number. When computing very large quantities or monetary amounts, choose data types and casts deliberately.

## 4. Comparison Operator Group

Common comparison operators:

| Operator | Meaning | Example |
| --- | --- | --- |
| `=` | Equal | `status = 'PAID'` |
| `<>` or `!=` | Not equal | `status <> 'CANCELLED'` |
| `<` | Less than | `amount < 100000` |
| `<=` | Less than or equal to | `amount <= 100000` |
| `>` | Greater than | `amount > 0` |
| `>=` | Greater than or equal to | `amount >= 50000` |

The result of standard comparisons is typically of type `BOOLEAN`: `TRUE` or `FALSE`, or `NULL/UNKNOWN` if an operand has missing data.

Example:

```sql
SELECT
    100 >= 100 AS inclusive_threshold,
    100 > 100 AS exclusive_threshold,
    'PAID' = 'PENDING' AS different_status;
```

Results: `TRUE`, `FALSE`, and `FALSE`.

### 4.1. Text Comparisons Depend on Type and Collation

For strings, `=`, `<`, `>`, and `ORDER BY` can be affected by collation. You should not assume string ordering across every database/locale matches numeric ordering or byte-by-byte comparison.

Example of deliberately choosing a collation:

```sql
SELECT
    'b' COLLATE "C" > 'a' COLLATE "C"
        AS binary_style_comparison;
```

For this simple ASCII example, the result is `TRUE`. In multilingual systems, collation, case folding, and Unicode require explicit policies; do not mechanically use `lower(...)` as a blanket substitute for personal name or email matching rules.

### 4.2. Comparison Operators Do Not Replace Data Constraints

The expression:

```sql
WHERE quantity > 0
```

only filters query results. To prevent negative `quantity` data **during INSERT/UPDATE**, you must add `CHECK(quantity > 0)` and `NOT NULL` if `quantity` is required. A correct SQL query does not mean the database enforces invariants on write.

## 5. Boolean Logic: NOT, AND, OR

The three basic conditional operators:

| Operator | Meaning | Example |
| --- | --- | --- |
| `NOT` | Negation | `NOT is_active` |
| `AND` | Both conditions true | `status='PAID' AND amount>0` |
| `OR` | At least one condition true | `status='PAID' OR status='PENDING'` |

**Logical precedence order**:

```text
NOT   highest
AND   next
OR    lowest
```

Therefore:

```sql
WHERE status = 'PAID'
   OR status = 'PENDING' AND amount >= 100000
```

is interpreted as:

```sql
WHERE status = 'PAID'
   OR (status = 'PENDING' AND amount >= 100000)
```

Not:

```sql
WHERE (status = 'PAID' OR status = 'PENDING')
  AND amount >= 100000
```

The two logic structures answer two different questions:

- **Query 1:** retrieve all PAID orders **or** PENDING orders of 100,000 or more.
- **Query 2:** retrieve only PAID/PENDING orders **with an amount of 100,000 or more**.

### 5.1. Clear Boolean Examples

```sql
SELECT
    (TRUE OR FALSE AND FALSE) AS default_precedence,
    ((TRUE OR FALSE) AND FALSE) AS grouped_condition,
    NOT FALSE AND TRUE AS negation_then_and;
```

Results respectively: `TRUE`, `FALSE`, `TRUE`.

### 5.2. When Should You Use Parentheses Even When Optional?

In conditions containing both `AND` and `OR`, place parentheses to show **business rule groupings**, for example:

```sql
WHERE (status IN ('PAID', 'PENDING'))
  AND (amount >= 100000 OR customer_id = 1)
```

Even when readers know the precedence table, parentheses make requirements easier to verify and reduce mistakes during edits.

Do not add endless parentheses around every simple expression; the goal is to **clarify intent**, not to make SQL harder to read.

## 6. NULL and Three-Valued Logic

In SQL, `NULL` typically represents unknown or missing data. It is **not equal to 0**, **not equal to an empty string**, and **not the same as FALSE**.

When comparing with `NULL`:

```sql
SELECT
    (NULL::integer = 1) AS null_equals_one,
    (NULL::integer = NULL::integer) AS two_nulls_equal,
    (NULL::integer <> 1) AS null_not_equal_one;
```

All three expressions return **NULL/UNKNOWN**, not TRUE or FALSE.

### 6.1. AND Truth Table with UNKNOWN

| A | B | A AND B |
| --- | --- | --- |
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| TRUE | UNKNOWN | UNKNOWN |
| FALSE | UNKNOWN | **FALSE** |
| UNKNOWN | UNKNOWN | UNKNOWN |

Why is `FALSE AND UNKNOWN = FALSE`? Because as soon as one side is false, the entire conjunction is guaranteed to be false regardless of what the other side is.

### 6.2. OR Truth Table with UNKNOWN

| A | B | A OR B |
| --- | --- | --- |
| TRUE | FALSE | TRUE |
| TRUE | UNKNOWN | **TRUE** |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN |

`TRUE OR UNKNOWN = TRUE` because one side is already guaranteed to be true.

### 6.3. NOT and UNKNOWN

```sql
SELECT
    NOT TRUE AS not_true,
    NOT FALSE AS not_false,
    NOT NULL::boolean AS not_unknown;
```

Results: `FALSE`, `TRUE`, `NULL`.

**Negating UNKNOWN is still UNKNOWN**; it does not turn into TRUE.

### 6.4. WHERE Only Keeps TRUE Expressions

`WHERE` does not keep rows whose condition evaluates to `FALSE` or `UNKNOWN`.

Example:

```sql
WHERE status <> 'PAID'
```

does not return rows where `status IS NULL`, because `NULL <> 'PAID'` is UNKNOWN. If the business rule wants to include unknown statuses as well:

```sql
WHERE status <> 'PAID'
   OR status IS NULL
```

or use an intentional comparison with `IS DISTINCT FROM`, as in the next section.

## 7. IS NULL, IS DISTINCT FROM, and NULL-Safe Comparisons

To check for missing data:

```sql
SELECT
    NULL::integer IS NULL AS is_null,
    NULL::integer IS NOT NULL AS is_not_null;
```

The results are `TRUE` and `FALSE`.

**Do not use**:

```sql
-- SEMANTICALLY WRONG: does not return TRUE when value is NULL.
-- WHERE value = NULL
```

### 7.1. IS DISTINCT FROM and IS NOT DISTINCT FROM

PostgreSQL supports comparisons that **produce a definite Boolean result even when encountering NULL**:

```sql
SELECT
    NULL::integer IS DISTINCT FROM NULL::integer
        AS both_null_distinct,
    NULL::integer IS NOT DISTINCT FROM NULL::integer
        AS both_null_equal_for_comparison,
    5 IS DISTINCT FROM NULL::integer
        AS value_differs_from_null,
    5 IS NOT DISTINCT FROM 5
        AS equal_nonnull;
```

Results:

| Expression | Value |
| --- | --- |
| Two NULLs `IS DISTINCT FROM` | FALSE |
| Two NULLs `IS NOT DISTINCT FROM` | TRUE |
| 5 `IS DISTINCT FROM` NULL | TRUE |
| 5 `IS NOT DISTINCT FROM` 5 | TRUE |

This comparison is very useful when comparing old/new records in auditing, detecting changed columns, or joining on nullable values under special rules.

### 7.2. IS TRUE / IS FALSE / IS UNKNOWN

When a column has type `BOOLEAN` and is nullable:

```sql
SELECT
    NULL::boolean IS TRUE AS is_true,
    NULL::boolean IS FALSE AS is_false,
    NULL::boolean IS UNKNOWN AS is_unknown,
    NULL::boolean IS NOT TRUE AS is_not_true;
```

Results: `FALSE`, `FALSE`, `TRUE`, and `TRUE`.

`IS NOT TRUE` differs from `= FALSE`: it also includes `NULL`.

### 7.3. NULL Can Make CHECK Behave Differently Than Expected

In PostgreSQL, `CHECK(expression)` accepts a row if the expression evaluates to **TRUE or UNKNOWN**, and rejects it when it evaluates to **FALSE**.

```sql
CREATE TABLE expression_demo_nullable (
    quantity INTEGER,
    CHECK (quantity > 0)
);
```

A row with `quantity = NULL` is not rejected by CHECK. To require `quantity` to be strictly positive:

```sql
CREATE TABLE expression_demo_required (
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
```

Only the combination of `NOT NULL` and `CHECK` protects both **presence** and **value range**.

## 8. BETWEEN, IN, ANY, ALL, and Set Conditions

### 8.1. BETWEEN Includes Both Endpoints

```sql
SELECT
    10 BETWEEN 1 AND 10 AS at_upper_boundary,
    11 BETWEEN 1 AND 10 AS beyond_upper_boundary;
```

The results are `TRUE` and `FALSE`.

`BETWEEN a AND b` generally has the same meaning as checking:

```sql
value >= a AND value <= b
```

When the two endpoints are reversed, regular `BETWEEN` does not automatically swap them. PostgreSQL provides `BETWEEN SYMMETRIC` if you truly need a range independent of endpoint order.

For timestamps, to capture a full day you should prefer a **half-open interval**:

```sql
WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND created_at < TIMESTAMPTZ '2026-01-02 00:00:00+07'
```

instead of setting an end-of-day bound like `23:59:59`, which can miss values with fractional seconds.

### 8.2. IN to Compare Against a Set of Values

```sql
SELECT
    'PAID' IN ('PAID', 'PENDING') AS accepted,
    'CANCELLED' IN ('PAID', 'PENDING') AS rejected;
```

Results: `TRUE`, `FALSE`.

`IN` is useful when you have a finite list of values. However, note `NULL`:

```sql
SELECT
    2 IN (1, NULL) AS check_with_null,
    2 NOT IN (1, NULL) AS negated_check_with_null;
```

Both can return **NULL/UNKNOWN**, rather than FALSE and TRUE as you might initially expect. No element matches with certainty, yet the NULL element makes it impossible to conclude with certainty whether the value 2 equals an unknown element.

### 8.3. NOT IN with NULL: The Exclusion Filter Trap

For example, wanting to find customers **without orders**:

```sql
-- If the subquery returns NULL, NOT IN can exclude even the rows
-- that you expected to keep.
-- WHERE customer_id NOT IN (SELECT customer_id FROM orders)
```

An option that is usually easier to reason about:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
```

If the source data is protected by `NOT NULL`, `NOT IN` can be semantically valid, though you still need to check empty subqueries, NULLs on the left-hand side, and business intent.

### 8.4. ANY and ALL with Arrays

In PostgreSQL:

```sql
SELECT
    3 = ANY(ARRAY[1, 3, 5]) AS found_any,
    7 > ALL(ARRAY[1, 3, 5]) AS greater_than_all,
    3 <> ALL(ARRAY[1, 5]) AS differs_from_all;
```

All three examples above return `TRUE`.

- `= ANY(array)`: at least one element equals the tested value.
- `> ALL(array)`: greater than all elements.
- `<> ALL(array)`: different from all elements under three-valued logic.

When the array is empty, `= ANY('{}'::integer[])` returns FALSE, while `= ALL('{}'::integer[])` returns TRUE under empty-set semantics. An array containing NULL can also produce UNKNOWN if no decisive TRUE/FALSE evidence is found.

### 8.5. Parentheses with BETWEEN and NOT

Because `BETWEEN ... AND ...` has its own grammatical structure, the safe way to negate a compound condition is to write:

```sql
WHERE NOT (amount BETWEEN 50000 AND 100000)
```

Do not guess by eye which `AND` belongs to `BETWEEN` and which `AND` belongs to another condition.

## 9. String Pattern Operators and Regular Expressions

PostgreSQL supports:

| Expression | Meaning |
| --- | --- |
| `text LIKE pattern` | SQL-style pattern matching |
| `text ILIKE pattern` | Case-insensitive pattern matching according to locale rules |
| `text NOT LIKE pattern` | Does not match pattern |
| `text SIMILAR TO pattern` | Pattern matching using SQL regular-expression-like syntax |
| `text ~ pattern` | POSIX regular expression match, case-sensitive |
| `text ~* pattern` | Case-insensitive regex match |
| `text !~ pattern` | Does not match case-sensitive regex |
| `text !~* pattern` | Does not match case-insensitive regex |

### 9.1. LIKE and Wildcards

```sql
SELECT
    'PostgreSQL' LIKE 'Post%' AS starts_with_post,
    'PostgreSQL' LIKE '%SQL' AS ends_with_sql,
    'A1' LIKE 'A_' AS one_character_after_a,
    'PostgreSQL' ILIKE 'post%' AS case_insensitive_match;
```

In a `LIKE` pattern:

- `%` matches any sequence of characters, including empty.
- `_` matches exactly one character.

A user-supplied value may contain `%` or `_`. If you need to search for **literal characters** instead of wildcards, you must escape them using `LIKE ... ESCAPE ...` and your application's escaping policy.

### 9.2. Regex Has Its Own Rules

```sql
SELECT
    'AB-123' ~ '^[A-Z]{2}-[0-9]{3}$'
        AS valid_code,
    'postgres' ~* '^POST'
        AS regex_case_insensitive;
```

The `^` and `$` symbols inside a **regex pattern string** are different from the SQL arithmetic operator `^`. They are processed **inside the regex engine**, not by the outer SQL operator precedence table.

**Specifically:** `~` is a regex operator when applied to strings, but can be a bitwise NOT operator for integer types. You must pay attention to data types.

## 10. String Concatenation and NULL Handling

PostgreSQL uses `||` to concatenate strings:

```sql
SELECT
    'Post' || 'greSQL' AS name,
    'Code: ' || 101::text AS labeled_id;
```

Results: `PostgreSQL` and `Code: 101`.

### 10.1. NULL Turns a Concatenation Expression into NULL

```sql
SELECT
    'A' || NULL::text AS nullable_concat,
    'A' || COALESCE(NULL::text, '') AS guarded_concat,
    concat('A', NULL::text, 'B') AS concat_function;
```

Results:

| Column | Value |
| --- | --- |
| `nullable_concat` | NULL |
| `guarded_concat` | `A` |
| `concat_function` | `AB` |

`concat(...)` ignores NULL arguments according to PostgreSQL semantics. However, do not turn every NULL into an empty string by default just for convenience: in some reports, missing data needs to be preserved to detect data-entry errors.

### 10.2. String Concatenation and Other Operators

`||` falls into the **other operators** group, at a different precedence level from `+` and `*`. When combining numeric calculations with strings, write:

```sql
SELECT
    'Total: ' || ((100 + 20) * 2)::text
        AS readable_result;
```

The value is `Total: 240`. The parentheses clarify the arithmetic part that must be cast to text before concatenating.

## 11. Bitwise: Do Not Mistake the ^ Operator for XOR

PostgreSQL supports bitwise operations on appropriate bit/integer types:

| Operator | Meaning for compatible types |
| --- | --- |
| `&` | Bitwise AND |
| `|` | Bitwise OR |
| `#` | Bitwise XOR |
| `~` | Bitwise NOT |
| `<<` | Bitwise shift left |
| `>>` | Bitwise shift right |

Example:

```sql
SELECT
    6 & 3 AS bitwise_and,
    6 | 3 AS bitwise_or,
    6 # 3 AS bitwise_xor,
    1 << 3 AS shift_left;
```

Results respectively: `2`, `7`, `5`, and `8`.

**In PostgreSQL, `^` is the exponentiation operator**, not bitwise XOR as in many programming languages. If a Java developer accustomed to `^` for XOR ports a formula directly into PostgreSQL, it can produce wrong results while the SQL still runs without error.

## 12. Creating a Practice Schema Combining Multiple Expressions

To use operators with realistic data, create a sample orders table. These commands are for a **test database** only and assume the schema does not already contain a table with the same name.

```sql
CREATE SCHEMA IF NOT EXISTS expression_lab;

CREATE TABLE expression_lab.orders (
    order_id       INTEGER PRIMARY KEY,
    customer_id    INTEGER NOT NULL,
    status         TEXT,
    amount         NUMERIC(12, 2),
    discount       NUMERIC(12, 2) NOT NULL DEFAULT 0,
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    denominator    INTEGER,
    ordered_at     TIMESTAMPTZ NOT NULL,
    attributes     JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags           TEXT[],
    CONSTRAINT chk_orders_status
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    CONSTRAINT chk_orders_amount
        CHECK (amount IS NULL OR amount >= 0),
    CONSTRAINT chk_orders_discount
        CHECK (discount >= 0)
);
```

In this example, `status` and `amount` **intentionally allow NULL** to practice three-valued logic. A real transactional system should agree on the meaning of NULL before choosing constraints. `discount` is constrained to be non-negative but does not yet have a `discount <= amount` constraint, because we want to illustrate the difference between query rules and data integrity rules.

### 12.1. Loading Data

```sql
INSERT INTO expression_lab.orders (
    order_id, customer_id, status, amount, discount,
    quantity, denominator, ordered_at, attributes, tags
)
VALUES
    (101, 1, 'PAID', 120000, 10000, 2,  2,
     TIMESTAMPTZ '2026-01-10 09:00:00+07',
     '{"source":"web","priority":2}'::jsonb,
     ARRAY['vip', 'express']::text[]),
    (102, 1, 'PENDING', 80000, 0, 1, 0,
     TIMESTAMPTZ '2026-01-11 10:00:00+07',
     '{"source":"app","priority":1}'::jsonb,
     ARRAY['standard']::text[]),
    (103, 2, 'PAID', 200000, 25000, 3, 4,
     TIMESTAMPTZ '2026-01-12 11:00:00+07',
     '{"source":"web","priority":3}'::jsonb,
     ARRAY['vip']::text[]),
    (104, 3, 'CANCELLED', 90000, 0, 2, 0,
     TIMESTAMPTZ '2026-01-13 12:00:00+07',
     '{"source":"partner"}'::jsonb,
     ARRAY[]::text[]),
    (105, 3, NULL, NULL, 0, 1, NULL,
     TIMESTAMPTZ '2026-01-14 13:00:00+07',
     '{"source":"app"}'::jsonb,
     NULL::text[]),
    (106, 4, 'PAID', 50000, 5000, 1, 5,
     TIMESTAMPTZ '2026-02-01 08:00:00+07',
     '{"source":"partner","priority":2}'::jsonb,
     ARRAY['first-time']::text[]);
```

From this we have six orders with the following states:

| order_id | customer_id | status | amount | discount | denominator |
| ---: | ---: | --- | ---: | ---: | ---: |
| 101 | 1 | PAID | 120000 | 10000 | 2 |
| 102 | 1 | PENDING | 80000 | 0 | 0 |
| 103 | 2 | PAID | 200000 | 25000 | 4 |
| 104 | 3 | CANCELLED | 90000 | 0 | 0 |
| 105 | 3 | NULL | NULL | 0 | NULL |
| 106 | 4 | PAID | 50000 | 5000 | 5 |

Records with `denominator = 0` and NULL were included **intentionally** to test safe division. Do not run unprotected division directly across this entire table.

## 13. How Do AND/OR Conditions Affect Data?

Requirement A: **all PAID orders, or PENDING orders with amount >= 100,000**.

```sql
SELECT order_id, status, amount
FROM expression_lab.orders
WHERE status = 'PAID'
   OR (status = 'PENDING' AND amount >= 100000)
ORDER BY order_id;
```

Results: orders **101, 103, 106**. PENDING order 102 has amount 80,000 so it does not qualify; every PAID order is included even with an amount of 50,000 like order 106.

Requirement B: **only PAID/PENDING orders with amount >= 100,000**.

```sql
SELECT order_id, status, amount
FROM expression_lab.orders
WHERE (status = 'PAID' OR status = 'PENDING')
  AND amount >= 100000
ORDER BY order_id;
```

Results: orders **101, 103**; order 106 is excluded because its amount does not meet the threshold.

### 13.1. With NULL, Negation Does Not Automatically Produce the Complement

```sql
SELECT order_id, status
FROM expression_lab.orders
WHERE NOT (status = 'PAID')
ORDER BY order_id;
```

Results: 102, 104. Order **105 with status NULL does not appear**, because `NOT UNKNOWN = UNKNOWN`.

To retrieve all orders **other than PAID, including NULL**:

```sql
SELECT order_id, status
FROM expression_lab.orders
WHERE status IS DISTINCT FROM 'PAID'
ORDER BY order_id;
```

Results: 102, 104, 105.

This is a business decision: does **"not PAID"** include **"unknown status"** or not? The two SQL formulations correspond to two different meanings.

## 14. Monetary Calculations and Multi-Operator Expressions

Suppose `amount` is the gross value before discount, and we want to compute:

```text
net_amount = amount - discount
```

```sql
SELECT
    order_id,
    amount,
    discount,
    amount - discount AS net_amount
FROM expression_lab.orders
ORDER BY order_id;
```

Based on the sample data, `net_amount` for the orders is respectively: 110,000; 80,000; 175,000; 90,000; NULL; 45,000.

### 14.1. Expressions with NULL Return NULL

`NULL - 0` is still NULL, not 0. Therefore order 105 has `net_amount IS NULL`.

If you want to display 0 for unknown values, you can write:

```sql
SELECT
    order_id,
    COALESCE(amount - discount, 0) AS displayed_net_amount
FROM expression_lab.orders;
```

However, this **changes the display meaning** from "amount not available" to "0". Only do this when reporting requirements explicitly define NULL as 0; do not arbitrarily mask unentered data.

### 14.2. Checking Multi-Column Constraints

If the business allows discount not to exceed amount and amount must be known:

```sql
-- Example defined on a new table, without modifying old data:
CREATE TABLE expression_lab.order_amounts_strict (
    order_id INTEGER PRIMARY KEY,
    amount NUMERIC(12, 2) NOT NULL,
    discount NUMERIC(12, 2) NOT NULL,
    CONSTRAINT chk_amount_bounds
        CHECK (
            amount >= 0
            AND discount >= 0
            AND discount <= amount
        )
);
```

This is a **row-level CHECK**, suited for the relationship between `amount` and `discount`. Conversely, a rule like "an order's `amount` equals the sum of line-item totals in another table" cannot be expressed directly with an ordinary `CHECK` constraint containing a subquery.

## 15. CASE: Choosing Results Conditionally

`CASE` lets you build an expression that returns different values based on conditions:

```sql
SELECT
    order_id,
    status,
    CASE
        WHEN status = 'PAID' THEN 'Paid'
        WHEN status = 'PENDING' THEN 'Pending'
        WHEN status = 'CANCELLED' THEN 'Cancelled'
        ELSE 'Unknown'
    END AS status_label
FROM expression_lab.orders
ORDER BY order_id;
```

This form of `CASE` selects the **first WHEN branch whose condition is TRUE**. If a `WHEN` condition is FALSE or UNKNOWN, PostgreSQL moves on to evaluate the next branch.

### 15.1. WHEN Order Affects the Result

```sql
SELECT
    amount,
    CASE
        WHEN amount >= 100000 THEN 'High'
        WHEN amount >= 50000 THEN 'Medium'
        ELSE 'Low or unknown'
    END AS amount_tier
FROM expression_lab.orders;
```

If you put the `amount >= 50000` check first, rows with amounts of 120,000 or 200,000 would be classified as "Medium", because that branch is already TRUE before reaching the "High" branch.

To classify ranges, write conditions that are **non-overlapping or in a clear order**.

### 15.2. CASE Can Return NULL

If there is no `ELSE` branch and no `WHEN` is TRUE, the result is `NULL`:

```sql
SELECT
    CASE
        WHEN NULL::integer > 0 THEN 'Positive'
    END AS unknown_result;
```

The result is NULL. All `THEN`/`ELSE` values must also resolve to a compatible common result type; mixing incompatible types can cause PostgreSQL to raise a type resolution error.

## 16. COALESCE, NULLIF, and Guarding Division

### 16.1. COALESCE Returns the First Non-NULL Value

```sql
SELECT
    COALESCE(NULL::text, 'fallback', 'other') AS selected_text,
    COALESCE(NULL::numeric, 0) AS zero_if_unknown;
```

The results are `fallback` and `0`.

`COALESCE` is useful when there is a fallback value. You do not need to wrap every column in `COALESCE`; choose default values based on business semantics.

### 16.2. NULLIF Produces NULL When Two Values Are Equal

```sql
SELECT
    NULLIF(0, 0) AS zero_to_null,
    NULLIF(5, 0) AS five_unchanged;
```

The results are NULL and 5.

### 16.3. Safe Division with NULLIF

Because `denominator` data can be 0:

```sql
SELECT
    order_id,
    amount,
    denominator,
    amount / NULLIF(denominator, 0) AS safe_ratio
FROM expression_lab.orders
ORDER BY order_id;
```

When `denominator = 0`, `NULLIF(denominator, 0)` becomes NULL, so the division returns NULL instead of raising a division-by-zero error. When `denominator` is NULL, the result is also NULL.

If the business needs a fallback value when division is not possible:

```sql
SELECT
    order_id,
    COALESCE(
        amount / NULLIF(denominator, 0),
        0
    ) AS reported_ratio
FROM expression_lab.orders
ORDER BY order_id;
```

However, 0 here represents a **display convention**; it does not mean the mathematical ratio is truly 0. For KPIs, it is sometimes better to leave it as NULL or pair it with a "not calculable" status.

### 16.4. CASE Guarding Conditional Division

Another way to express it:

```sql
SELECT
    order_id,
    CASE
        WHEN denominator IS NULL OR denominator = 0 THEN NULL
        ELSE amount / denominator
    END AS safe_ratio
FROM expression_lab.orders;
```

With dynamic column values at runtime as in this example, `CASE` can be used to control evaluating only the matching branch.

**However**, do not infer that `CASE` is a mechanism guaranteeing that expressions in unselected branches will **never** be processed at any stage. PostgreSQL can pre-evaluate constant expressions during planning; aggregates and certain other constructs also have their own evaluation rules. Section 18 clarifies this important limitation.

## 17. PostgreSQL Operators for JSONB and Arrays

PostgreSQL has many operators dedicated to composite data types. This is where **cast precedence** and **each operator's return type** deserve special attention.

### 17.1. JSONB -> and ->>

With the `attributes JSONB` column:

```sql
SELECT
    order_id,
    attributes -> 'source' AS source_json,
    attributes ->> 'source' AS source_text
FROM expression_lab.orders
ORDER BY order_id;
```

Difference:

- `->` returns the corresponding **JSON/JSONB** value.
- `->>` returns the value as **TEXT**.

For example, `attributes ->> 'priority'` returns a text string like `'2'`, and does not automatically become an integer just because the original JSON contained the number 2.

### 17.2. Parenthesize Before Casting JSON Text

Correct query:

```sql
SELECT
    order_id,
    (attributes ->> 'priority')::integer AS priority_number
FROM expression_lab.orders
WHERE attributes ? 'priority'
ORDER BY order_id;
```

The rows with a `priority` field in the sample data have valid numeric values. They are extracted as text first and **then cast to integer**.

Do not write out of habit:

```sql
-- WRONG INTENT:
-- attributes ->> 'priority'::integer
```

Because `::` has higher precedence than the JSON operator `->>`, the expression above attempts to cast **the key string 'priority' to integer**, causing an error before extracting the value from JSON.

**Practical rule:** when combining JSON operators with casts, use:

```sql
(json_expression ->> 'key')::target_type
```

or:

```sql
CAST(json_expression ->> 'key' AS target_type)
```

### 17.3. JSONB Containment @>

```sql
SELECT
    order_id,
    attributes
FROM expression_lab.orders
WHERE attributes @> '{"source":"web"}'::jsonb
ORDER BY order_id;
```

Results: orders 101 and 103.

`@>` when applied to JSONB checks whether the JSON on the left contains the required structure/value on the right according to containment rules. This has **different** semantics from the text comparison operators `=` or `LIKE`.

### 17.4. Array Access and Array Operators

```sql
SELECT
    order_id,
    tags,
    tags[1] AS first_tag,
    tags @> ARRAY['vip']::text[] AS has_vip
FROM expression_lab.orders
ORDER BY order_id;
```

For normal PostgreSQL arrays in the example, `tags[1]` accesses the first element; array subscripts can be defined with a lower bound other than 1 in advanced cases, so do not treat "every PostgreSQL array always starts at 1" as a system invariant.

`tags @> ARRAY['vip']::text[]` checks whether the left-hand array **contains** the element under array operator rules. If `tags IS NULL`, the operator result is typically NULL/UNKNOWN.

### 17.5. Multiple Types Share the Same Operator Symbol

`@>` can also be used with ranges or other types that define support for it. Same syntax does not mean the same data check.

When reading a SQL query with an unfamiliar operator, check:

1. The actual types of the left and right operands.
2. Which operator PostgreSQL resolved.
3. The return type.
4. The corresponding index/operator class if optimization is needed.

Do not cast everything to TEXT just to use familiar operators; doing so loses type semantics and the benefits of appropriate indexes.

## 18. Precedence Is Not Runtime Evaluation Order

This is the most important distinction in this lesson:

**Precedence** determines how an expression is **parsed into a syntax tree**:

```text
amount + tax * rate
      |
      +--> amount + (tax * rate)
```

However, **runtime evaluation order** can depend on the planner, scan method, predicate pushdown, and expression optimization. You should not look at `a AND b` and assert that PostgreSQL always evaluates `a` first and then, if needed, evaluates `b`.

### 18.1. Do Not Rely on Short-Circuiting in WHERE

A dangerous example:

```sql
-- DO NOT RELY ON THIS TO PREVENT DIVISION BY ZERO:
-- WHERE denominator <> 0
--   AND amount / denominator > 1000
```

Beginners might think: "PostgreSQL checks whether `denominator` is non-zero first, and if false, skips the division." However, **Boolean expressions in WHERE/HAVING can be reordered, transformed, and evaluated according to the execution plan**, so `AND` should not be treated as a control-flow statement with a guaranteed left-to-right order.

Solution for expressing a safe calculation:

```sql
SELECT
    order_id,
    amount / NULLIF(denominator, 0) AS safe_ratio
FROM expression_lab.orders
WHERE amount / NULLIF(denominator, 0) > 1000;
```

When `denominator` is 0, the safe division expression returns NULL; the comparison with 1000 becomes UNKNOWN and the row is not selected.

### 18.2. The Planner Can Pre-Evaluate Constant Expressions

An example illustrating an error that can occur at planning time:

```sql
-- DO NOT RUN: the constant expression 1/0 may be evaluated
-- before CASE is considered as a runtime branch.
-- SELECT CASE WHEN false THEN 1 / 0 ELSE 0 END;
```

Meaning: `CASE` controls branches during normal evaluation, but **is not a barrier against all optimizations or constant folding**. Avoid placing invalid constant calculations in SQL even in branches that appear unreachable.

### 18.3. Aggregates Can Be Evaluated Before an Enclosing CASE

A flawed idea when data contains `denominator = 0`:

```sql
-- UNSAFE FORMULATION:
-- SELECT CASE
--     WHEN MIN(denominator) > 0
--     THEN SUM(amount / denominator)
--     ELSE NULL
-- END
-- FROM expression_lab.orders;
```

In an aggregate query, aggregate expressions can be computed **before** the enclosing `CASE` evaluates its branch selection. Therefore, an outer `CASE` does not guarantee protecting `SUM(amount / denominator)` from data with `denominator = 0`.

A division-safe approach:

```sql
SELECT
    SUM(amount / NULLIF(denominator, 0))
        AS sum_of_defined_ratios
FROM expression_lab.orders;
```

However, you must understand the meaning: `SUM` ignores NULL values, so the query above **skips rows where the ratio cannot be calculated**. If the goal is `SUM(amount) / SUM(denominator)`, that is **a different formula**, and the summed denominator also needs protection:

```sql
SELECT
    SUM(amount) / NULLIF(SUM(denominator), 0)
        AS ratio_of_totals
FROM expression_lab.orders;
```

Do not swap these two formulas without a business definition.

### 18.4. Do Not Use Evaluation Order to Produce Side Effects

`VOLATILE` functions such as `random()` or custom functions with side effects can be invoked in ways that depend on the execution plan; you should not write Boolean conditions expecting a side effect to occur once or in a specific order.

A SQL query is a **description of the result to compute**, not procedural code guaranteeing each expression executes in display order. If an operation with side effects requires ordering, design a transaction/procedure or application logic with explicit sequencing.

## 19. Parsing, Casting, and Operator Resolution

Even when parenthesization is right, PostgreSQL still needs to determine **the type of each operand** and **which operator definition applies**.

### 19.1. Numeric Literals and String Literals Do Not Have the Same Semantics

```sql
SELECT
    10 + 2 AS numeric_addition,
    '10'::text || '2'::text AS text_concatenation;
```

The results are **12** and **'102'**. Do not store numbers in TEXT and use `||` to perform business addition.

PostgreSQL can infer types for **untyped literals** in certain expressions based on operator context, but that inference should not be treated as a contract for arbitrary input strings, prepared statement parameters, or casts from a TEXT column.

### 19.2. Explicit CAST Avoids Relying on Inference

```sql
SELECT
    CAST('120' AS integer) + 5 AS parsed_numeric,
    ('120'::integer + 5)::text AS result_as_text;
```

The results are `125` and `'125'`.

If the string is not a valid integer representation, such as `'abc'::integer`, PostgreSQL raises an error. Casting **does not automatically replace dirty data with 0**.

### 19.3. Casting and Precedence

Because `::` belongs to a high-precedence group, the expression:

```sql
SELECT (7 / 2)::numeric AS cast_after_division;
```

produces **3** as `numeric`, **not 3.5**. The fractional part was already discarded when dividing two integers.

To get 3.5:

```sql
SELECT
    7::numeric / 2 AS cast_before_division,
    CAST(7 AS numeric) / 2 AS equivalent_cast;
```

**Casting after an operation cannot recover information already lost in the earlier operation.**

### 19.4. PostgreSQL Supports User-Defined Operators

With extensions or custom schemas, developers can introduce new operators. The `OPERATOR(schema.operator_name)` syntax allows specifying which schema an operator belongs to when appropriate, but operators written with this qualified syntax take the precedence of **general operators**, not necessarily keeping the precedence of a directly written symbol like `+`.

Therefore, when using custom operators, wrap subexpressions in parentheses to avoid relying on how the parser resolves unfamiliar symbols.

## 20. Date/Time and AT TIME ZONE

PostgreSQL supports temporal manipulation expressions:

```sql
SELECT
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS local_wall_time;
```

Semantically, the result is **2026-01-01 07:00:00** as a `timestamp without time zone` representing the point in time converted to the `Asia/Ho_Chi_Minh` time zone.

Important rule:

- `timestamptz AT TIME ZONE zone` typically produces **timestamp without time zone**, representing the local wall-clock time of that instant in the given zone.
- `timestamp without time zone AT TIME ZONE zone` typically produces **timestamptz**, interpreting the given local wall-clock time as belonging to that zone.

These two directions are **not the same**. A local wall-clock value without a time zone and an absolute instant in time are two different kinds of information.

### 20.1. Use Parentheses When Combining Time and Logic

```sql
SELECT
    order_id,
    (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS business_date
FROM expression_lab.orders
ORDER BY order_id;
```

The parentheses make it clear: **convert to local time first, then extract the date**. Extracting the date before converting time zones or relying on the session's `TimeZone` setting can shift daily reports around midnight.

### 20.2. Half-Open Intervals for Dates

When filtering a `TIMESTAMPTZ` column directly, it is common to use a half-open interval:

```sql
SELECT order_id, ordered_at
FROM expression_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND ordered_at < TIMESTAMPTZ '2026-02-01 00:00:00+07'
ORDER BY ordered_at;
```

This range represents one calendar month using the offset explicitly written in the literals. For time zones with daylight saving time, month start and end instants should be computed in the **business time zone**, without assuming every day is always 24 hours.

## 21. JOIN, WHERE, HAVING, and When Expressions Are Evaluated

The logical order of query clauses is commonly explained as:

```text
FROM / JOIN
    -> WHERE: filter individual rows
    -> GROUP BY: form groups
    -> aggregate: COUNT, SUM, AVG, ...
    -> HAVING: filter groups
    -> SELECT: produce output expressions
    -> ORDER BY: sort
    -> LIMIT: limit result rows
```

This is **query semantics**. PostgreSQL does not necessarily read sequentially or evaluate every expression in physical steps identical to this diagram.

### 21.1. WHERE Cannot Use Aggregates from the Same Query Level

```sql
-- INVALID:
-- SELECT customer_id, COUNT(*)
-- FROM expression_lab.orders
-- WHERE COUNT(*) >= 2
-- GROUP BY customer_id;
```

To filter groups:

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM expression_lab.orders
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
```

In the sample data, the result includes customers 1 and 3, each with two orders.

### 21.2. FILTER Only Filters the Input to One Aggregate

```sql
SELECT
    customer_id,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders
FROM expression_lab.orders
GROUP BY customer_id
ORDER BY customer_id;
```

`COUNT(*)` counts all rows in the group; `COUNT(*) FILTER (WHERE status='PAID')` counts only PAID orders without removing the other rows from `COUNT(*)`.

### 21.3. SELECT Aliases and WHERE

```sql
-- INVALID at the same SELECT level: WHERE cannot use an alias just defined.
-- SELECT amount - discount AS net_amount
-- FROM expression_lab.orders
-- WHERE net_amount >= 100000;
```

Write:

```sql
SELECT
    order_id,
    amount - discount AS net_amount
FROM expression_lab.orders
WHERE amount - discount >= 100000
ORDER BY order_id;
```

or use a CTE:

```sql
WITH net_orders AS (
    SELECT
        order_id,
        amount - discount AS net_amount
    FROM expression_lab.orders
)
SELECT order_id, net_amount
FROM net_orders
WHERE net_amount >= 100000;
```

In the outer query, `net_amount` is a column of the CTE, so using it in `WHERE` is valid.

### 21.4. JOIN ON vs. WHERE with LEFT JOIN

Suppose you want **all customers**, even those without orders, while attaching only paid orders:

```sql
-- Illustrative SQL snippet, assuming a customers table exists.
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID';
```

Moving `o.status='PAID'` from `ON` to `WHERE` would drop customers without PAID orders, because on unmatched rows `o.status IS NULL` and the equality comparison yields UNKNOWN.

For a simple **INNER JOIN**, many conditions can be moved between `ON` and `WHERE` without changing results; for an **OUTER JOIN**, that is not a general rule. Get the **semantics** right before considering expression optimization.

## 22. Performance: Expressions Can Affect Index Usage

Suppose the `amount` column has a standard B-tree index:

```sql
CREATE INDEX idx_expression_lab_amount
ON expression_lab.orders (amount);
```

The condition:

```sql
WHERE amount >= 100000
```

can generally leverage the index on `amount` more easily than an expression that does not match the index structure, such as:

```sql
WHERE amount - discount >= 100000
```

However, the second condition has **different semantics**: it compares the amount **after discount**, so you cannot replace it with a check on raw `amount` just to use the index faster.

### 22.1. Expression Indexes When the Workload Needs Them

PostgreSQL supports indexes on expressions:

```sql
CREATE INDEX idx_expression_lab_net_amount
ON expression_lab.orders ((amount - discount));
```

This index can assist queries that filter or sort by the matching `amount - discount` expression in an appropriate workload. It also consumes storage and write overhead, so do not create one just for a SQL exercise.

### 22.2. Casting Columns and Index Eligibility

For example:

```sql
WHERE ordered_at::date = DATE '2026-01-10'
```

is not identical to a direct range condition on `ordered_at` over a standard B-tree index; furthermore, casting `TIMESTAMPTZ` to `DATE` can depend on the session time zone.

A query bounded by explicit instants:

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-01-10 00:00:00+07'
  AND ordered_at < TIMESTAMPTZ '2026-01-11 00:00:00+07'
```

is usually more favorable for an index on `ordered_at`, while also being explicit about time bounds. Even so, the PostgreSQL planner may still choose a `Seq Scan` if the table is small or index cost is higher.

### 22.3. Using EXPLAIN to Observe

```sql
EXPLAIN
SELECT
    order_id,
    amount - discount AS net_amount
FROM expression_lab.orders
WHERE amount - discount >= 100000;
```

When you want to measure actual execution on a test database:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    amount - discount AS net_amount
FROM expression_lab.orders
WHERE amount - discount >= 100000;
```

`EXPLAIN ANALYZE` **executes the query**, so exercise caution with data-modifying statements or heavy queries in production. With a very small sample dataset, `Seq Scan` can be completely reasonable even when an index exists.

## 23. How to Inspect Expression Types and Results

When unsure what type PostgreSQL resolves for an expression, use `pg_typeof(...)`:

```sql
SELECT
    pg_typeof(7 / 2) AS integer_result_type,
    pg_typeof(7::numeric / 2) AS decimal_result_type,
    pg_typeof('x'::text || 'y'::text) AS concat_result_type;
```

The results correspond to an integer type, `numeric`, and `text`.

### 23.1. Inspecting Individual Parts of an Expression

For a complex condition:

```sql
WHERE status = 'PAID'
  AND (amount - discount) >= 100000
  AND (attributes ->> 'source') = 'web'
```

try outputting helper columns:

```sql
SELECT
    order_id,
    status = 'PAID' AS is_paid,
    amount - discount AS net_amount,
    (amount - discount) >= 100000 AS reaches_target,
    attributes ->> 'source' AS source_text,
    (attributes ->> 'source') = 'web' AS is_web
FROM expression_lab.orders
ORDER BY order_id;
```

This helps distinguish whether a row was excluded due to **FALSE** or **UNKNOWN from NULL**.

### 23.2. Do Not Treat EXPLAIN as a Validator of Business Logic

`EXPLAIN` shows how PostgreSQL plans/actually executes a query; it does not prove that the `WHERE` clause expresses the requirement correctly. A condition missing parentheses can run very fast **yet return the wrong rows**.

The most important check is testing with **boundary data**: TRUE/FALSE, NULL, 0, exact threshold values, timestamps near boundaries, mixed-case text, missing JSON fields, and large quantities.

## 24. Using PreparedStatement with Expressions in Java

When SQL is sent from a Java application to PostgreSQL, the expression should have a fixed structure and **input values should be passed as parameters**, rather than concatenating strings to build arbitrary SQL.

Example:

```java
String sql = """
    SELECT order_id, amount - discount AS net_amount
    FROM expression_lab.orders
    WHERE (status = ? OR status = ?)
      AND amount - discount >= ?
    ORDER BY order_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "PAID");
    ps.setString(2, "PENDING");
    ps.setBigDecimal(3, new java.math.BigDecimal("100000.00"));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            int orderId = rs.getInt("order_id");
            java.math.BigDecimal net =
                rs.getBigDecimal("net_amount");
            // Process data according to the application contract.
        }
    }
}
```

This snippet assumes a `java.sql.Connection` and corresponding JDBC imports are already present; it demonstrates parameter binding, not a complete Java application.

**Parentheses in SQL still matter**, even when using `PreparedStatement`. Parameter binding separates values from SQL structure and reduces SQL injection risk; it does not rewrite operator precedence rules.

Operators, column names, and SQL structure cannot be arbitrarily substituted via a value parameter; if users can choose dynamic conditions, the application must whitelist columns/operators and construct the query safely.

## 25. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Forgetting `*`/`/` have higher precedence than `+`/`-` | Wrong formula | Add parentheses matching business formula |
| Assuming `AND` and `OR` have the same precedence | `WHERE` condition selects wrong rows | Remember `AND` outranks `OR`; parenthesize clearly |
| Writing `NOT status='PAID'` expecting NULLs to be kept | Excludes rows with NULL status | Use `IS DISTINCT FROM` when NULLs should be included |
| Writing `column = NULL` | Comparison returns UNKNOWN | Use `IS NULL` |
| Treating UNKNOWN as FALSE in every context | Misunderstands NOT/AND/OR logic | Apply three-valued logic |
| Using `CHECK (value > 0)` while allowing NULL values | NULL rows are accepted | Add `NOT NULL` if required |
| Using `NOT IN` on a set containing NULL | May return fewer or no expected rows | Control for NULLs or use `NOT EXISTS` |
| Expecting `7 / 2` to return 3.5 | Fractional part lost | Cast before dividing |
| Using `(7 / 2)::numeric` to "recover" the fraction | Still yields 3 | `7::numeric / 2` |
| Porting `^` from Java thinking it is XOR | Computes exponentiation instead of bitwise XOR | Use `#` for bitwise XOR where appropriate |
| Using `SUM(DISTINCT amount)` to fix a row-multiplying join | Undercounts transactions with identical amounts | Fix the grain/JOIN, then aggregate |
| Writing `payload ->> 'quantity'::integer` | Casts the JSON key by mistake | `(payload ->> 'quantity')::integer` |
| Comparing JSON text values with numbers as if same type | Operator/type error or wrong logic | Cast explicitly and validate data |
| Concatenating with `||` without considering NULL | Entire expression becomes NULL | Use `COALESCE`/`concat` intentionally |
| Assuming `AND` always checks the left side first | Division by zero or function error can still occur | Use `NULLIF`/appropriate `CASE` |
| Treating `CASE` as an absolute shield for any expression | Constant folding/aggregates can still error | Avoid invalid constants; guard calculations at the source |
| Using `CASE WHEN SUM(...)` to "block" a failing aggregate | Aggregate is computed before outer `CASE` | Guard elements inside the aggregate itself |
| Using `WHERE` with an aggregate at the same level | SQL error | Use `HAVING` |
| Using a `SELECT` alias in `WHERE` at the same level | Name resolution error | Repeat the expression or use a CTE |
| Moving a `LEFT JOIN` filter from `ON` to `WHERE` | Drops unmatched left-side rows | Preserve outer join semantics |
| Using `BETWEEN` with end-of-day `23:59:59` | Misses timestamps with fractional seconds | Use a half-open interval |
| Not specifying time zone when extracting `DATE` from `TIMESTAMPTZ` | Wrong report day/month | Convert to business time zone first |
| Assuming `Seq Scan` is always a problem | Pointless optimization on small tables | Read `EXPLAIN` and actual costs |
| Assuming operators with the same symbol have the same meaning | Mistakes with JSONB/arrays/bitwise | Check types and resolved operator |

## 26. Practice Exercises

The exercises below use PostgreSQL and the `expression_lab.orders` data from Section 12. Write down your prediction before running each exercise.

1. **Arithmetic precedence:** explain the results of `100 + 20 * 3` and `(100 + 20) * 3`. Why do the two expressions differ?
2. **Associativity:** run `20 - 5 - 3` and `20 - (5 - 3)`. Identify which operator is grouped first.
3. **Exponentiation:** test `2 ^ 3 ^ 2` and `2 ^ (3 ^ 2)`. Compare with the exponentiation rules you know from math or other programming languages.
4. **Unary minus:** compute `-(3 ^ 2)` and `(-3) ^ 2`. Explain why parentheses should be used.
5. **Integer division:** compute `7 / 2`, `(7 / 2)::numeric`, and `7::numeric / 2`. Why does casting after division not restore the fractional part?
6. **Threshold:** write an expression selecting orders with `amount - discount >= 100000`. With the sample data, which `order_id` values meet the threshold?
7. **AND/OR:** find PAID or PENDING orders with `amount >= 100000`. Write two SQL queries with different parenthesization and predict the results.
8. **NULL logic:** test `NOT (NULL::boolean)`, `FALSE AND NULL::boolean`, and `TRUE OR NULL::boolean`. Explain each result.
9. **NULL comparison:** find orders whose `status` is not PAID, **including** NULL `status`. Compare `<>` and `IS DISTINCT FROM`.
10. **IS TRUE/FALSE:** using a CTE containing `TRUE`, `FALSE`, and `NULL::boolean`, test `IS FALSE`, `IS NOT TRUE`, and `IS UNKNOWN`.
11. **BETWEEN:** compare `BETWEEN 50000 AND 100000` and `>=50000 AND <100000` for the exact value 100000.
12. **NOT IN and NULL:** explain `2 NOT IN (1, NULL)`. Write an equivalent non-existence check using `NOT EXISTS`.
13. **ANY/ALL:** test `3 = ANY(ARRAY[1,3,5])`, `3 = ANY('{}'::integer[])`, and `3 = ALL('{}'::integer[])`.
14. **String patterns:** write a `LIKE` query selecting statuses starting with `'P'`. Compare `LIKE` with `ILIKE` when changing letter case.
15. **Regex:** use `~` to validate the code `AB-123` against a pattern of two uppercase letters, a hyphen, and three digits.
16. **Concatenation:** test `'A' || NULL::text`, `'A' || COALESCE(NULL::text,'')`, and `concat('A',NULL,'B')`.
17. **Bitwise:** compute `6 & 3`, `6 | 3`, and `6 # 3`. Explain why `6 ^ 3` is not XOR in PostgreSQL.
18. **JSONB:** extract `attributes ->> 'source'` and filter orders with `source = web`. Which `order_id` values are returned?
19. **JSONB cast:** extract `priority` as an integer using `(attributes ->> 'priority')::integer`. Why is `attributes ->> 'priority'::integer` wrong?
20. **JSON containment:** test `attributes @> '{"source":"web"}'::jsonb`. Compare the result with the text condition `attributes ->> 'source' = 'web'`.
21. **Arrays:** use `tags @> ARRAY['vip']::text[]` to find orders with the VIP tag. How does a row with NULL `tags` differ from a row with empty `tags`?
22. **Safe division:** compute `amount / NULLIF(denominator, 0)` for all orders. Why do orders 102/104/105 not raise an error?
23. **CASE:** classify orders by `net_amount`: 100000 or more is High, 50000 or more is Medium, under 50000 is Low, and NULL is Unknown. Write a `CASE` expression with a clear condition order.
24. **SUM and NULL:** compare `SUM(amount / NULLIF(denominator,0))` with `SUM(amount) / NULLIF(SUM(denominator),0)`. Do these two formulas have the same meaning?
25. **CASE and aggregates:** explain why an outer `CASE` wrapping `SUM(amount/denominator)` does not always prevent division by zero. Write a safe version.
26. **HAVING:** count orders per customer, keeping only customers with two or more orders. Why can't you use `WHERE COUNT(*) >= 2`?
27. **FILTER:** in a single query, return the count of all orders and the count of PAID orders per customer. How does this differ from filtering `status` in `WHERE`?
28. **Alias:** try using `net_amount` defined in `SELECT` inside `WHERE` at the same level, then fix it with a CTE.
29. **Local time:** convert `ordered_at TIMESTAMPTZ` to a date in `Asia/Ho_Chi_Minh`. Why should you convert the time zone before casting to `DATE`?
30. **Expression index:** run `EXPLAIN` on `amount - discount >= 100000` before and after creating an expression index. Why might PostgreSQL still choose `Seq Scan` on a small table?
31. **Java query:** write a `PreparedStatement` with the grouped condition `(status=? OR status=?) AND amount>=?`. Explain why parameter binding does not replace the need for proper parentheses.
32. **Reviewing new SQL:** given a query involving JSONB, OR/AND, casts, nullable `amount`, and a date range, build a checklist covering: expression tree, result types, NULLs, safe evaluation order, and boundary data.

## 27. Summary

When writing a PostgreSQL expression, consider three distinct layers:

```text
1. SYNTAX / PRECEDENCE
   10 + 5 * 2  -> 10 + (5 * 2)
   NOT > AND > OR
   Use parentheses to state intent clearly

2. DATA TYPES / NULL
   7 / 2        -> integer division
   7::numeric/2 -> decimal division
   NULL = NULL  -> UNKNOWN
   IS NULL / IS DISTINCT FROM when handling NULL

3. EVALUATION / OPTIMIZATION
   Planner can transform Boolean expressions
   Do not rely on left-to-right AND/OR order to prevent errors
   NULLIF, CASE, and semantically safe calculations
   Verify results before optimizing with EXPLAIN
```

**Precedence** tells PostgreSQL how an expression is **grouped**; **data types** determine which operator is applied and what values can be produced; **the execution plan** determines how parts of the expression are processed when the query runs. These three aspects are related but must not be conflated.

The most valuable habit is to **place parentheses where business logic requires grouping, cast before operations when precision must be preserved, handle NULLs deliberately, and never rely on short-circuiting to guard potentially failing calculations**. Getting those right makes SQL both readable and resilient when data, schemas, or optimizer plans change.
