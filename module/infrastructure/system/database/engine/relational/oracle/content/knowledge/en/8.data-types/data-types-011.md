# NULL, Empty Strings, and Three-Valued Logic in Oracle

In Oracle Database, a column can hold either a valid value or **`NULL`**, meaning no known/provided value exists in the data context. A critical Oracle-specific behavior is that **a zero-length character string (`''`) is currently treated as `NULL`** for standard character values. Furthermore, comparisons involving `NULL` do not produce true or false as in ordinary numeric comparisons, but instead produce a third state: **UNKNOWN**.

These three facts directly affect how you write `WHERE`, `JOIN`, `CHECK`, `COUNT`, handle parameters from Java applications, and design data models. An expression that looks reasonable such as `WHERE note = ''` or `WHERE status <> 'DONE'` can silently omit the very rows you expected to match. This lesson builds the exact mental model and illustrates it with runnable SQL statements in Oracle Database.

After this lesson, you will be able to:

- Explain what `NULL` means and distinguish it from `0`, `FALSE`, spaces, and default values.
- Understand why `''` becomes `NULL` for `VARCHAR2`/`CHAR`, while distinguishing empty LOBs such as `EMPTY_CLOB()`.
- Read truth tables for **TRUE / FALSE / UNKNOWN** with `AND`, `OR`, and `NOT`.
- Use `IS NULL`, `IS NOT NULL`, `NVL`, `COALESCE`, `NULLIF`, and `CASE` properly.
- Predict outcomes when `NULL` appears in filters, `NOT IN`, outer joins, aggregations, and constraints.
- Design test cases for missing data, empty strings, and whitespace-only strings.

> Scope: Oracle Database SQL behavior for standard character types and `NULL`. Oracle documents the current rule that "a zero-length character string is NULL" while noting that this behavior may change in the future. Application code should therefore model data meanings explicitly rather than relying on storing distinct `''` and `NULL` states in an Oracle `VARCHAR2` column.

## 1. What Does `NULL` Actually Represent?

In a relational database, a nullable column may have no value for a row. Oracle represents this case with `NULL`. Depending on the business model, the reason may be:

- Data **not yet provided**, such as the shipping date of a new order.
- Data **unknown**, such as an unverified phone number.
- Data **not applicable**, such as the refund date of a transaction that was never refunded.

These are **different business interpretations** that may all be stored using a single `NULL` marker. If the application needs to distinguish "unknown" from "not applicable", add an explicit status/attribute; a bare `NULL` value cannot explain why it is missing.

### 1.1. Values That Are Not `NULL`

| Value | Meaning | Is It `NULL` in Oracle? |
| --- | --- | --- |
| `NULL` | No defined value | Yes |
| `0` | Zero | No |
| `'0'` | String containing the character 0 | No |
| `' '` | One space | No |
| `'   '` | Three spaces | No |
| `'N/A'` | Three-character string meaning "not applicable" | No |
| `'UNKNOWN'` | Literal text string "UNKNOWN" | No |
| `DATE '1900-01-01'` | A concrete date often used as a sentinel | No |
| `''` | Zero-length string | **Treated by Oracle as `NULL`** for standard character data |

`NULL` is not zero, not whitespace, and not a string containing the word "NULL". Using `'N/A'` or `0` to represent missing data must be an **explicitly documented business decision**, because it alters comparison and aggregation semantics.

### 1.2. Does `NULL` Have a Data Type?

`NULL` is a marker that can appear in any data type, not only character columns:

```sql
SELECT
    CAST(NULL AS NUMBER)       AS unknown_amount,
    CAST(NULL AS DATE)         AS unknown_date,
    CAST(NULL AS VARCHAR2(20)) AS unknown_note
FROM dual;
```

All three expressions evaluate to `NULL`, yet each is typed explicitly for use in expressions, operations, or `UNION` queries. When building complex expressions or passing bind parameters, choosing the right **data type** still matters even when the actual value is `NULL`.

### 1.3. Operations with `NULL`

Most ordinary operations with a `NULL` operand return `NULL`:

```sql
SELECT
    10 + CAST(NULL AS NUMBER) AS add_result,
    10 * CAST(NULL AS NUMBER) AS multiply_result,
    LENGTH(CAST(NULL AS VARCHAR2(20))) AS length_result
FROM dual;
```

All three columns above return `NULL`. However, **do not apply a blanket rule "whenever NULL appears, the result is NULL" to every SQL function/operator**: `NVL`, `COALESCE`, `COUNT`, `IS NULL`, `DECODE`, and Oracle's string concatenation have dedicated rules explained below.

## 2. How Does Oracle Handle the Empty String `''`?

### 2.1. Empty Strings in `VARCHAR2` and `CHAR`

For standard SQL character values, Oracle currently treats a zero-length string as `NULL`. Example:

```sql
SELECT
    CASE WHEN '' IS NULL THEN 'IS NULL' ELSE 'NOT NULL' END AS empty_check,
    NVL('', 'replacement value') AS empty_with_nvl,
    LENGTH('') AS empty_length,
    LENGTH(' ') AS one_space_length
FROM dual;
```

Meaningful results:

| Expression | Expected Value |
| --- | --- |
| `'' IS NULL` | TRUE |
| `NVL('', 'replacement value')` | `replacement value` |
| `LENGTH('')` | `NULL` |
| `LENGTH(' ')` | `1` |

`LENGTH('')` **does not return 0** under Oracle's current rules for these character strings; because `''` is treated as `NULL`, `LENGTH` also returns `NULL`.

The same behavior appears when inserting into a `VARCHAR2` column:

```sql
CREATE TABLE lab_empty_string (
    id          NUMBER PRIMARY KEY,
    description VARCHAR2(30)
);

INSERT INTO lab_empty_string (id, description)
VALUES (1, '');

INSERT INTO lab_empty_string (id, description)
VALUES (2, NULL);

INSERT INTO lab_empty_string (id, description)
VALUES (3, ' ');

COMMIT;

SELECT
    id,
    CASE WHEN description IS NULL THEN 'NULL' ELSE 'NOT NULL' END AS state,
    LENGTH(description) AS character_count
FROM lab_empty_string
ORDER BY id;
```

Rows 1 and 2 have `DESCRIPTION IS NULL`; row 3 contains a single space and is therefore not `NULL`. This experiment creates a lab-only table; if the table already exists, rename it to avoid affecting existing data.

**Consequence for `NOT NULL`:** if `DESCRIPTION` has a `NOT NULL` constraint, an `INSERT` with `''` is treated by Oracle as inserting `NULL` and can raise `ORA-01400`. When sending empty values from an application, never assume a `NOT NULL` column accepts a zero-length string.

### 2.2. Spaces, `TRIM`, and Fixed-Length `CHAR`

`' '` is a space character, distinct from an empty string. However, `TRIM` can strip all spaces and yield a zero-length string, which Oracle then treats as `NULL`:

```sql
SELECT
    LENGTH('   ') AS before_trim,
    LENGTH(TRIM('   ')) AS after_trim,
    CASE
        WHEN TRIM('   ') IS NULL THEN 'TRIM RESULT IS NULL'
        ELSE 'TRIM RESULT HAS TEXT'
    END AS trim_state
FROM dual;
```

Result: `BEFORE_TRIM` is 3, `AFTER_TRIM` is `NULL`. This is why checking for "left empty or whitespace-only" typically combines `TRIM` with `IS NULL`.

Fixed-length `CHAR(n)` has **blank-padding** rules for stored values and certain comparisons. For instance, `'A'` in `CHAR(5)` may be stored as `'A    '`. Do not infer that a space-filled string is `NULL`: an all-spaces value is still not `NULL` when stored as character content. In applications, understand how `CHAR` and `VARCHAR2` differ in padding, length, and comparisons; for variable-length text, `VARCHAR2` is usually much easier to work with.

### 2.3. Important Exception: An Empty CLOB Can Differ from `NULL`

Oracle supports **large objects (LOBs)** such as `CLOB`. `EMPTY_CLOB()` creates an empty LOB locator of length 0, which is **not synonymous with a `NULL` LOB value**:

```sql
SELECT
    CASE
        WHEN EMPTY_CLOB() IS NULL THEN 'NULL'
        ELSE 'NOT NULL'
    END AS clob_state,
    DBMS_LOB.GETLENGTH(EMPTY_CLOB()) AS clob_length
FROM dual;
```

When supported as written above, `CLOB_STATE` is `NOT NULL` and `CLOB_LENGTH` is 0. This is a key distinction between a **zero-length LOB** and a **zero-length character string** in `VARCHAR2`/`CHAR`.

Therefore, the accurate statement is: *Oracle currently treats zero-length character strings as `NULL` for standard character values; a properly initialized empty LOB can have length 0 without being `NULL`.*

### 2.4. PL/SQL and Application Parameters

The empty-string rule also applies to `VARCHAR2` variables in PL/SQL:

```sql
DECLARE
    v_text VARCHAR2(20) := '';
BEGIN
    IF v_text IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('v_text is NULL');
    END IF;
END;
/
```

In a Java application using JDBC, a zero-length `String` bound into an Oracle `VARCHAR2` column should not be expected to store an empty string distinct from SQL `NULL`. Define a clear contract across frontend, API, and database for **omitted field**, **null**, **empty**, and **blank** states.

## 3. Three-Valued Logic: TRUE, FALSE, and UNKNOWN

SQL uses **three-valued logic (3VL)** for conditions where `NULL` may appear:

- **TRUE:** expression is determined to be true.
- **FALSE:** expression is determined to be false.
- **UNKNOWN:** cannot determine TRUE/FALSE from the available data, typically because an operand is `NULL`.

`UNKNOWN` is a **logical truth value of a condition**, not the string `'UNKNOWN'` stored in a table. In SQL, `NULL` can produce UNKNOWN during comparisons.

### 3.1. Comparing with `=` and `<>` Against `NULL`

| Expression | Logical Result |
| --- | --- |
| `5 = 5` | TRUE |
| `5 = 7` | FALSE |
| `5 = NULL` | UNKNOWN |
| `5 <> NULL` | UNKNOWN |
| `NULL = NULL` | UNKNOWN |
| `NULL <> NULL` | UNKNOWN |
| `NULL = ''` | UNKNOWN, because `''` is treated as `NULL` |

Two missing values **are not considered equal by ordinary `=`**. SQL cannot prove they represent the same real value. Therefore, to check for a missing column value, use:

```sql
WHERE phone_number IS NULL
```

Or conversely:

```sql
WHERE phone_number IS NOT NULL
```

**Avoid**:

```sql
WHERE phone_number = NULL

-- Oracle also does not use this pattern to find empty strings:
WHERE phone_number = ''
```

Neither condition evaluates to TRUE for rows containing `NULL`.

### 3.2. Truth Table for NOT

| P | NOT P |
| --- | --- |
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

Hence, **`NOT (col = 10)` does not automatically include `col IS NULL`**, because `NOT UNKNOWN` remains UNKNOWN.

### 3.3. Truth Table for AND

| P | Q | P AND Q |
| --- | --- | --- |
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| TRUE | UNKNOWN | UNKNOWN |
| FALSE | TRUE | FALSE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE |
| UNKNOWN | TRUE | UNKNOWN |
| UNKNOWN | FALSE | FALSE |
| UNKNOWN | UNKNOWN | UNKNOWN |

For example, `FALSE AND UNKNOWN = FALSE`: one side is already definitively false, so the entire AND condition cannot be true regardless of the unknown operand.

### 3.4. Truth Table for OR

| P | Q | P OR Q |
| --- | --- | --- |
| TRUE | TRUE | TRUE |
| TRUE | FALSE | TRUE |
| TRUE | UNKNOWN | TRUE |
| FALSE | TRUE | TRUE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | UNKNOWN |
| UNKNOWN | TRUE | TRUE |
| UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN |

For example, `TRUE OR UNKNOWN = TRUE`: one side being definitively true is enough.

### 3.5. Observing UNKNOWN Directly with CASE

SQL clients do not necessarily print the word `UNKNOWN`. We can detect it using a `CASE` expression:

```sql
SELECT CASE
           WHEN CAST(NULL AS NUMBER) = CAST(NULL AS NUMBER)
               THEN 'TRUE'
           WHEN NOT (CAST(NULL AS NUMBER) = CAST(NULL AS NUMBER))
               THEN 'FALSE'
           ELSE 'UNKNOWN'
       END AS comparison_result
FROM dual;
```

The result is `UNKNOWN`. Neither the first `WHEN` condition nor its negation in the second `WHEN` is **TRUE**, so `ELSE` is chosen.

> In a searched `CASE`, Oracle selects a `WHEN` branch when its condition evaluates to **TRUE**. When it is FALSE or UNKNOWN, Oracle moves to the next branch. If no branch is TRUE and there is no `ELSE`, the `CASE` evaluates to `NULL`.

## 4. Which Rows Do `WHERE` and `HAVING` Keep?

The single most important rule when reading SQL queries is: **`WHERE` keeps only rows whose condition evaluates to TRUE**. Rows yielding FALSE **or UNKNOWN** are excluded from the result.

Suppose we have table `LAB_TICKETS`:

| ID | STATUS |
| ---: | --- |
| 1 | `OPEN` |
| 2 | `DONE` |
| 3 | `NULL` |

Query:

```sql
SELECT id, status
FROM lab_tickets
WHERE status <> 'DONE';
```

Returns only row 1 (`OPEN`). Row 3 has `STATUS <> 'DONE'` evaluating to UNKNOWN, so **it is not returned**, even though it does not contain `'DONE'`.

If the business requirement is "all tickets not DONE, including those with no status yet", write:

```sql
SELECT id, status
FROM lab_tickets
WHERE status <> 'DONE'
   OR status IS NULL;
```

Conversely, if the requirement is "only tickets with a defined status other than DONE", `status <> 'DONE'` is right.

### 4.1. `BETWEEN`, `LIKE`, and `IN` Can Also Produce UNKNOWN

Common predicates such as `price > 100`, `created_at < DATE '2026-01-01'`, `name LIKE 'A%'`, and `score BETWEEN 50 AND 100` will not become TRUE when the tested column value itself is `NULL`.

```sql
SELECT id
FROM lab_tickets
WHERE status IN ('OPEN', 'WAITING');
```

Rows with `STATUS IS NULL` are not kept. To include rows missing a status, add `OR status IS NULL`.

### 4.2. Searched CASE vs. Simple CASE

**Searched CASE** lets you test `IS NULL`:

```sql
SELECT id,
       CASE
           WHEN status IS NULL THEN 'MISSING'
           WHEN status = 'DONE' THEN 'COMPLETE'
           ELSE 'OTHER'
       END AS status_label
FROM lab_tickets;
```

In **simple CASE**, writing `WHEN NULL` is not the way to test for missing data:

```sql
SELECT CASE status
           WHEN NULL THEN 'MISSING'
           WHEN 'DONE' THEN 'COMPLETE'
           ELSE 'OTHER'
       END AS status_label
FROM lab_tickets;
```

When `status` is `NULL`, simple CASE performs normal equality matching and does not take `WHEN NULL`; it falls into `ELSE`. Always use searched CASE when a branch must check `IS NULL`.

### 4.3. `HAVING` Also Requires Thinking About NULL

`HAVING` filters **groups** after aggregation; the condition must be TRUE for a group to be kept. Example:

```sql
SELECT department_id, SUM(bonus) AS total_bonus
FROM employee_bonus
GROUP BY department_id
HAVING SUM(bonus) > 1000;
```

If every `BONUS` in a group is `NULL`, `SUM(bonus)` returns `NULL`; `NULL > 1000` is UNKNOWN, so that group is dropped. You can write `HAVING COALESCE(SUM(bonus), 0) > 1000` if business rules treat a missing sum as 0.

## 5. `NVL`, `COALESCE`, `NVL2`, and `NULLIF`

Oracle provides `NULL`-handling functions, yet **substituting a default for a missing value changes semantics**. Use them only when the business meaning is clear.

### 5.1. `NVL(expression, replacement)`

`NVL` returns `replacement` if `expression` is `NULL`; otherwise it returns `expression`:

```sql
SELECT NVL(CAST(NULL AS NUMBER), 0) AS missing_as_zero,
       NVL(CAST(NULL AS VARCHAR2(20)), '(none yet)') AS missing_as_text
FROM dual;
```

For example, displaying `NULL` as 0 may suit a **report table**, yet be wrong if 0 means a confirmed monetary amount. In financial data, "price unknown" differs from "price is 0".

### 5.2. `COALESCE`: First Non-NULL Value

`COALESCE` returns the first non-`NULL` expression in the list:

```sql
SELECT COALESCE(
           CAST(NULL AS VARCHAR2(30)),
           'default display name',
           'backup'
       ) AS display_name
FROM dual;
```

`COALESCE` helps prioritize multiple data sources—for instance, verified phone first, secondary phone next, and finally a missing-notice message. Expressions must have compatible data types under Oracle's inference/conversion rules.

`COALESCE` uses short-circuit evaluation in argument order. With `NVL`, do not assume every fallback expression with side effects is skipped when the first value is non-NULL. Avoid placing side-effecting calls in either branch just to build a display value.

### 5.3. `NVL2`: Two Branches for Present vs. Missing

```sql
SELECT NVL2(
           CAST(NULL AS VARCHAR2(10)),
           'HAS VALUE',
           'MISSING'
       ) AS label
FROM dual;
```

`NVL2(expr, when_not_null, when_null)` chooses the second or third branch depending on whether `expr` is `NULL`. It can be rewritten as a searched `CASE` for greater readability.

### 5.4. `NULLIF(a, b)`: Turn Two Equal Values into NULL

`NULLIF(a, b)` returns `NULL` when `a = b` is TRUE; otherwise it returns `a`. A common use case is preventing division by zero:

```sql
SELECT sales_amount / NULLIF(item_count, 0) AS sales_per_item
FROM sales_summary;
```

If `ITEM_COUNT = 0`, the denominator becomes `NULL` and the quotient becomes `NULL` instead of raising a divide-by-zero error. Even then, the result represents "cannot be computed" and must be handled by the application—**not automatically treated as 0**.

**Do not use `NULLIF(column, '')` hoping to distinguish `''` from `NULL` in Oracle**: `''` is already treated as `NULL`. To normalize whitespace-only strings, use `TRIM` with `IS NULL` or clear input validation rules.

### 5.5. Watch Out for Sentinel Values

Suppose `quantity` can validly equal -1 as a special code. Writing:

```sql
WHERE NVL(quantity, -1) = -1
```

conflates **quantity is NULL** with **quantity actually equals -1**. To find nulls, use `quantity IS NULL`. If business logic wants both, state it explicitly:

```sql
WHERE quantity IS NULL OR quantity = -1
```

Wrapping a column in a function can also affect Oracle's ability to use a regular index; check execution plans and suitable indexes when filtering large tables.

## 6. String Concatenation with NULL Is a Memorable Exception

In Oracle, the concatenation operator `||` behaves specially when one side is `NULL` or a zero-length string:

```sql
SELECT
    'Code: ' || CAST(NULL AS VARCHAR2(20)) AS label_1,
    CAST(NULL AS VARCHAR2(20)) || 'X' AS label_2,
    CAST(NULL AS VARCHAR2(20)) ||
        CAST(NULL AS VARCHAR2(20)) AS label_3
FROM dual;
```

Under current behavior, `LABEL_1` produces `'Code: '`, `LABEL_2` produces `'X'`, and `LABEL_3` is `NULL`. This is an exception to the idea that "any operation with NULL produces NULL".

However, **concatenation is not a NULL check**. If the application needs to show "no code" when the code is missing, state it explicitly with `CASE` or `COALESCE`:

```sql
SELECT CASE
           WHEN tracking_code IS NULL THEN '(no code yet)'
           ELSE 'Code: ' || tracking_code
       END AS tracking_label
FROM shipments;
```

Do not rely on concatenating `NULL` producing an empty string to drive business logic.

## 7. Aggregates and GROUP BY Handle NULL Differently from Comparisons

In SQL, standard aggregate functions follow specific rules:

- `COUNT(*)` counts **every row** in the set/group, including rows where all columns are `NULL`.
- `COUNT(column)` counts only rows where **column is not `NULL`**.
- `COUNT(DISTINCT column)` counts distinct **non-`NULL`** values.
- `SUM(column)`, `AVG(column)`, `MIN(column)`, and `MAX(column)` normally **ignore `NULL` values**.
- If no non-`NULL` values exist to aggregate, `SUM`/`AVG`/`MIN`/`MAX` return `NULL`, whereas `COUNT(column)` returns 0.

### 7.1. COUNT and AVG Example

Consider the data:

| ID | BONUS |
| ---: | ---: |
| 1 | 100 |
| 2 | `NULL` |
| 3 | 300 |

```sql
WITH sample_data (id, bonus) AS (
    SELECT 1, 100 FROM dual UNION ALL
    SELECT 2, CAST(NULL AS NUMBER) FROM dual UNION ALL
    SELECT 3, 300 FROM dual
)
SELECT
    COUNT(*) AS total_rows,
    COUNT(bonus) AS known_bonus_count,
    SUM(bonus) AS bonus_sum,
    AVG(bonus) AS avg_known_bonus,
    AVG(NVL(bonus, 0)) AS avg_treat_missing_as_zero
FROM sample_data;
```

Expected output:

| TOTAL_ROWS | KNOWN_BONUS_COUNT | BONUS_SUM | AVG_KNOWN_BONUS | AVG_TREAT_MISSING_AS_ZERO |
| ---: | ---: | ---: | ---: | ---: |
| 3 | 2 | 400 | 200 | approx. 133.33 |

`AVG(bonus)` averages over the **two** known values without assuming 0 for the missing row. `AVG(NVL(bonus, 0))` has a different statistical meaning: it explicitly treats missing rows as 0. Which expression to pick is a business decision.

### 7.2. GROUP BY and DISTINCT Group NULLs Together

In `GROUP BY`, rows whose grouping expression is `NULL` are placed into **one NULL group**:

```sql
WITH sample_data (team) AS (
    SELECT 'A' FROM dual UNION ALL
    SELECT 'A' FROM dual UNION ALL
    SELECT CAST(NULL AS VARCHAR2(10)) FROM dual UNION ALL
    SELECT CAST(NULL AS VARCHAR2(10)) FROM dual
)
SELECT team, COUNT(*) AS members
FROM sample_data
GROUP BY team
ORDER BY team NULLS LAST;
```

The result has group `A` with 2 rows and a `NULL` group with 2 rows. This **does not contradict** `NULL = NULL` being UNKNOWN: `GROUP BY` and `DISTINCT` use grouping/deduplication rules rather than `=` in a `WHERE` filter.

Similarly, `SELECT DISTINCT team ...` typically outputs a single `NULL` row when the source has multiple `NULL` rows.

### 7.3. ORDER BY and NULL Placement

Oracle lets you control where `NULL` appears:

```sql
SELECT order_id, shipped_at
FROM orders
ORDER BY shipped_at ASC NULLS LAST;

SELECT order_id, shipped_at
FROM orders
ORDER BY shipped_at DESC NULLS FIRST;
```

In Oracle, when omitted, **`ASC` defaults to `NULLS LAST`** and **`DESC` defaults to `NULLS FIRST`**. Write `NULLS FIRST`/`NULLS LAST` explicitly whenever display order or pagination depends on missing-value ordering. For deterministic pagination, also add a unique tie-breaker column when multiple rows share the same value.

## 8. NULL in JOINs and Subqueries

### 8.1. INNER JOIN with NULL Keys

With a standard join condition:

```sql
SELECT c.customer_id, o.order_id
FROM customers c
JOIN orders o
  ON c.customer_id = o.customer_id;
```

If `o.customer_id` is `NULL`, `c.customer_id = o.customer_id` evaluates to UNKNOWN and produces no match from that condition. **Two `NULL` columns do not match with `=` either.**

If business logic intentionally wants two missing values to match in a reconciliation query, write a **NULL-safe comparison**, such as a searched `CASE` or explicit predicate:

```sql
ON (
       a.external_code = b.external_code
    OR (a.external_code IS NULL AND b.external_code IS NULL)
   )
```

In an `ON` clause, only TRUE creates a match, so this pattern treats two `NULL`s as matching. Be careful: joining all codeless rows to each other can produce an **unexpected Cartesian explosion**, especially if both tables have many `NULL` rows. Joining missing keys this way makes sense only when the business confirms `NULL` genuinely represents a single shared group.

### 8.2. OUTER JOIN and the WHERE Filter Trap

`LEFT JOIN` preserves rows from the left table even when no matching row exists on the right. For unmatched rows, right-side columns appear as `NULL` in the result.

Example:

```sql
SELECT c.customer_id, p.payment_id
FROM customers c
LEFT JOIN payments p
  ON p.customer_id = c.customer_id
WHERE p.status = 'PAID';
```

Customers without payments are eliminated by `WHERE p.status = 'PAID'` because the condition evaluates to UNKNOWN. The query effectively behaves like an inner join on that condition, dropping customers without payments.

If the requirement is **show all customers and attach only paid payments**, put the condition in `ON`:

```sql
SELECT c.customer_id, p.payment_id
FROM customers c
LEFT JOIN payments p
  ON p.customer_id = c.customer_id
 AND p.status = 'PAID';
```

These are **two different queries**. Before moving a predicate from `WHERE` to `ON`, confirm which result set the business actually wants.

### 8.3. The `NOT IN` Trap When a Subquery Contains NULL

`NOT IN` against a set containing `NULL` is a classic logic bug:

```sql
SELECT 3 AS candidate
FROM dual
WHERE 3 NOT IN (1, 2, NULL);
```

This query **returns zero rows**. Logically:

```text
3 NOT IN (1, 2, NULL)
  is equivalent to
3 <> 1 AND 3 <> 2 AND 3 <> NULL
  = TRUE AND TRUE AND UNKNOWN
  = UNKNOWN
```

Because `WHERE` keeps only TRUE, the row is excluded. A single `NULL` in the list causes `NOT IN` to return no rows, even when the candidate differs from every non-NULL value.

When finding records **with no related child record**, prefer `NOT EXISTS`:

```sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers b
    WHERE b.customer_id = c.customer_id
);
```

`NOT EXISTS` checks that no row satisfies the correlated condition, so a `blocked_customers` row with `customer_id NULL` does not "poison" the entire filter. Still, if `c.customer_id` itself can be `NULL`, `=` will not match either; add explicit `IS NULL` rules if business logic must exclude or retain rows with missing keys.

If you must use `NOT IN`, filter `NULL` out of the subquery:

```sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customers b
    WHERE b.customer_id IS NOT NULL
);
```

Even then, **`c.customer_id NULL`** remains a corner case. The right condition depends on whether left-side rows missing a code should match; for primary keys, `NOT NULL` removes the ambiguity.

### 8.4. `IN (NULL)` and `NOT (column = value)`

`value IN (NULL)` does not find `NULL` values; the comparison never evaluates to TRUE. Likewise, `NOT (status = 'DONE')` does not return rows missing a status because `NOT UNKNOWN = UNKNOWN`. To match both other statuses and missing statuses, write `OR status IS NULL` explicitly.

## 9. NULL in Data Constraints

### 9.1. NOT NULL and PRIMARY KEY

A `NOT NULL` column must hold a non-NULL value. Because `''` becomes `NULL` in Oracle, a `VARCHAR2 NOT NULL` column also rejects empty strings under current rules:

```sql
CREATE TABLE lab_required_code (
    code VARCHAR2(20) NOT NULL
);

-- The following statement will be rejected because '' is treated as NULL:
INSERT INTO lab_required_code (code) VALUES ('');
```

**PRIMARY KEY** combines non-NULL and uniqueness requirements. Thus a primary key cannot accept `NULL`. Never choose a nullable key as a primary key hoping Oracle will treat two NULLs as distinct.

### 9.2. UNIQUE and NULL

With a **UNIQUE constraint on a single nullable column**, Oracle allows **multiple rows with `NULL`**. That is not Oracle treating `NULL = NULL` as TRUE, but rather how uniqueness constraints treat missing values.

```sql
CREATE TABLE lab_unique_email (
    id    NUMBER PRIMARY KEY,
    email VARCHAR2(100) UNIQUE
);

INSERT INTO lab_unique_email VALUES (1, NULL);
INSERT INTO lab_unique_email VALUES (2, NULL);
```

Both rows can coexist. However, two rows with the same **non-NULL** email will violate the UNIQUE constraint.

**Watch out with multi-column UNIQUE keys:** Oracle applies specific rules for **composite unique keys** containing NULL components; do not generalize "UNIQUE allows unlimited duplicates if any column is NULL" to all multi-column keys. On composite keys, rows whose non-NULL parts match can still be rejected as duplicates under Oracle's rules. Design constraints around meaningful value combinations and verify with sample data.

### 9.3. CHECK Only Rejects FALSE; UNKNOWN Can Pass

A SQL **CHECK constraint** accepts a row whenever its condition does not evaluate to FALSE. Therefore, `UNKNOWN` caused by `NULL` normally **does not violate CHECK**.

```sql
CREATE TABLE lab_scores (
    student_id NUMBER PRIMARY KEY,
    score      NUMBER,
    CONSTRAINT ck_score_positive CHECK (score >= 0)
);

INSERT INTO lab_scores (student_id, score) VALUES (1, NULL);
```

A row with `SCORE NULL` is accepted: `score >= 0` is UNKNOWN, not FALSE. If a score is both mandatory and non-negative, declare **both**:

```sql
CREATE TABLE lab_required_scores (
    student_id NUMBER PRIMARY KEY,
    score NUMBER NOT NULL,
    CONSTRAINT ck_required_score CHECK (score >= 0)
);
```

When a string must be non-NULL and not all spaces:

```sql
CREATE TABLE lab_nonblank_name (
    id NUMBER PRIMARY KEY,
    display_name VARCHAR2(100) NOT NULL,
    CONSTRAINT ck_nonblank_name
        CHECK (TRIM(display_name) IS NOT NULL)
);
```

`TRIM('   ')` becomes `NULL`, making `IS NOT NULL` FALSE, so whitespace-only rows are rejected. This checks default space-trimming; if business rules must reject tabs or Unicode whitespace variants as well, apply a stricter normalization rule.

### 9.4. Nullable FOREIGN KEY

A single-column foreign key with `NULL` is normally allowed unless an explicit `NOT NULL` constraint exists: a row with no reference value does not need a matching parent key. If the relationship is mandatory, add `NOT NULL`. For composite foreign keys, rules for partial NULL components should be verified against composite key semantics and data design.

## 10. NULL, Indexes, and Query Performance

Standard Oracle B-tree indexes have a notable behavior with `NULL`: **they do not store an index entry when all indexed key columns are NULL**. For a single-column index:

```sql
CREATE INDEX idx_lab_email
    ON lab_empty_string(description);
```

Rows with `DESCRIPTION NULL` do not produce a single-column index entry in the usual way. Consequently, `description IS NULL` cannot always be satisfied by a direct lookup on that single-column B-tree index. Oracle may choose a full table scan or another access path depending on index structure, statistics, and plans.

For a multi-column index, if **at least one key column is non-NULL**, an entry can be stored per Oracle's indexing rules. Function-based indexes and other index designs can also change support for `IS NULL` predicates. Never claim "Oracle can never use an index for `IS NULL`"—that is overly broad.

Moreover, writing:

```sql
WHERE NVL(description, 'MISSING') = 'MISSING'
```

wraps the column in a function, which can prevent regular index usage, and also conflates two cases if `'MISSING'` is a valid string. Use `description IS NULL` when your exact goal is finding missing data.

When evaluating performance, inspect **actual execution plans**, data statistics, and selectivity. Index recommendations should only follow a clear understanding of queries and workloads.

## 11. NULL in Java Application Code and the API Layer

In Java, a `String` can be `null` or `""`, and those two states are **distinct in application memory**. Yet when written to an Oracle `VARCHAR2` column, `""` may be treated as SQL `NULL` under current rules.

Conceptual JDBC example:

```java
String note = ""; // Zero-length Java String, distinct from null in Java.

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO lab_empty_string (id, description) VALUES (?, ?)")) {
    ps.setInt(1, 10);
    ps.setString(2, note);
    ps.executeUpdate();
}
```

When column and driver follow standard Oracle semantics, the value stored/read in `VARCHAR2` no longer distinguishes "Java empty string" from SQL `NULL`. When reading via `ResultSet.getString(...)`, anticipate receiving Java `null`, and use `wasNull()` when distinguishing SQL `NULL` from primitive getter defaults.

**API designs must clarify four easily confused cases:**

| Input Payload | Possible Defined Meaning | Handling Recommendation |
| --- | --- | --- |
| Field omitted in JSON PATCH | Do not modify the stored value | Distinguish from a request to clear the value |
| `"note": null` | Clear / set missing per contract | Write `NULL` if column is nullable and rules permit |
| `"note": ""` | Intentionally empty string | Decide to reject, normalize to NULL, or model separately if distinction is needed |
| `"note": "   "` | Whitespace only | Decide whether to trim/reject blank input before saving |

If business rules **genuinely require distinguishing "not entered" from "entered as intentionally empty"**, you cannot rely on `NULL` and `''` in a single `VARCHAR2` column under current Oracle behavior. Add a status column, an enum/flag, or an explicit data model. Never use fragile sentinels like a space character to fake an empty string.

In Java/Spring, `@NotNull`, `@NotEmpty`, and `@NotBlank` (Jakarta Validation) carry distinct meanings at the application layer. They do not replace Oracle database constraints; every write path into the database must still uphold the contract.

## 12. Hands-On Practice Without Creating Tables

The following examples use `DUAL` and `WITH` to avoid modifying schema data. You can run them in SQL Developer, SQLcl, or SQL*Plus. SQL*Plus uses `;` to terminate SQL statements; PL/SQL blocks require appropriate block execution syntax.

### Step 1 — Compare NULL, Empty Strings, and Whitespace

```sql
WITH sample (id, text_value) AS (
    SELECT 1, CAST(NULL AS VARCHAR2(10)) FROM dual UNION ALL
    SELECT 2, '' FROM dual UNION ALL
    SELECT 3, ' ' FROM dual UNION ALL
    SELECT 4, 'X' FROM dual
)
SELECT
    id,
    CASE WHEN text_value IS NULL
         THEN 'NULL'
         ELSE 'NOT NULL' END AS value_state,
    LENGTH(text_value) AS text_length,
    CASE WHEN TRIM(text_value) IS NULL
         THEN 'BLANK OR MISSING'
         ELSE 'HAS CONTENT' END AS normalized_state
FROM sample
ORDER BY id;
```

Predict the output before running:

| ID | VALUE_STATE | TEXT_LENGTH | NORMALIZED_STATE |
| ---: | --- | ---: | --- |
| 1 | NULL | `NULL` | BLANK OR MISSING |
| 2 | NULL | `NULL` | BLANK OR MISSING |
| 3 | NOT NULL | 1 | BLANK OR MISSING |
| 4 | NOT NULL | 1 | HAS CONTENT |

Notice how `''` falls into the same bucket as `NULL`, whereas a space is classified as blank only after `TRIM`.

### Step 2 — Observe UNKNOWN

```sql
WITH sample (id, n) AS (
    SELECT 1, 10 FROM dual UNION ALL
    SELECT 2, 20 FROM dual UNION ALL
    SELECT 3, CAST(NULL AS NUMBER) FROM dual
)
SELECT
    id,
    CASE
        WHEN n = 10 THEN 'TRUE'
        WHEN NOT (n = 10) THEN 'FALSE'
        ELSE 'UNKNOWN'
    END AS is_ten
FROM sample
ORDER BY id;
```

Row `N=10` gives TRUE, `N=20` gives FALSE, and `N=NULL` gives UNKNOWN. Adding `WHERE n <> 10` in an outer query drops the NULL row.

### Step 3 — Experience the NOT IN Trap

```sql
WITH candidates (n) AS (
    SELECT 1 FROM dual UNION ALL
    SELECT 2 FROM dual UNION ALL
    SELECT 3 FROM dual
)
SELECT n
FROM candidates
WHERE n NOT IN (1, NULL);
```

No rows are returned: `1 <> 1` is FALSE, while for `2` and `3` the expression includes a comparison to NULL and never becomes TRUE.

Replace with:

```sql
WITH candidates (n) AS (
    SELECT 1 FROM dual UNION ALL
    SELECT 2 FROM dual UNION ALL
    SELECT 3 FROM dual
)
SELECT c.n
FROM candidates c
WHERE NOT EXISTS (
    SELECT 1
    FROM (
        SELECT 1 AS blocked_n FROM dual
        UNION ALL
        SELECT CAST(NULL AS NUMBER) FROM dual
    ) b
    WHERE b.blocked_n = c.n
)
ORDER BY c.n;
```

The result returns 2 and 3: the blocked row with NULL does not make all candidates disappear. In this example, candidates are non-NULL numbers, so there is no left-side key ambiguity.

### Step 4 — Distinguish COUNT and AVG

```sql
WITH scores (score) AS (
    SELECT 100 FROM dual UNION ALL
    SELECT 200 FROM dual UNION ALL
    SELECT CAST(NULL AS NUMBER) FROM dual
)
SELECT
    COUNT(*) AS row_count,
    COUNT(score) AS known_count,
    AVG(score) AS avg_known,
    AVG(NVL(score, 0)) AS avg_missing_as_zero
FROM scores;
```

Prediction: `ROW_COUNT=3`, `KNOWN_COUNT=2`, `AVG_KNOWN=150`, and `AVG_MISSING_AS_ZERO=100`. Explain why the two AVG values express **two different interpretations**.

### Step 5 — CHECK and NOT NULL Constraints

You do not need to create the table just to reason about it:

```sql
CREATE TABLE lab_null_constraint (
    id NUMBER PRIMARY KEY,
    age NUMBER CHECK (age >= 0),
    nickname VARCHAR2(30) NOT NULL
);
```

If you choose to run this example in a lab schema:

- `AGE=NULL` can be accepted if nickname is valid, because `age >= 0` evaluates to UNKNOWN.
- `AGE=-1` is rejected by CHECK.
- `NICKNAME=''` is rejected by NOT NULL because Oracle treats an empty string as NULL.
- `NICKNAME=' '` still passes NOT NULL unless an additional constraint rejects whitespace-only strings.

If studying theory only, do not run `CREATE TABLE`. Never run it on a production schema or overwrite existing objects.

## 13. Common Mistakes and Better Patterns

| Goal | Error-Prone Pattern | Better Pattern |
| --- | --- | --- |
| Find missing values | `col = NULL` | `col IS NULL` |
| Find empty strings in Oracle `VARCHAR2` | `col = ''` | `col IS NULL` when current semantics treat empty as missing |
| Find present values | `col <> NULL` | `col IS NOT NULL` |
| Find all statuses not DONE, including missing | `status <> 'DONE'` | `status <> 'DONE' OR status IS NULL` |
| Find rows absent from a child table | `NOT IN (SELECT key ...)` when key may be NULL | `NOT EXISTS` with proper correlation, or explicit NULL filtering |
| Average known values | `AVG(NVL(value, 0))` | `AVG(value)` if "missing" does not mean zero |
| Find whitespace-only text | `text_col = ''` | `TRIM(text_col) IS NULL` when grouping NULL and blank |
| Check whether two nullable values match | `a = b` | NULL-safe comparison accounting for `a IS NULL AND b IS NULL` |
| Forbid NULL in a table | Only `CHECK (col > 0)` | Add `NOT NULL` when required |
| Filter right side of LEFT JOIN while keeping all left rows | Put all right-side filters in `WHERE` | Consider moving filters to `ON` per business rules |
| Store distinct empty vs. missing states | `''` and `NULL` in one `VARCHAR2` column | Design an extra status column or suitable data model |

No single mechanical transformation works for every query. For instance, `NVL(col,0)` may suit a total-quantity report yet be wrong when checking "was a value provided?"; `NOT EXISTS` avoids the NULL trap of `NOT IN` yet still requires defining left-side missing-key behavior.

## 14. Self-Check Questions

**Question 1.** In Oracle, is `LENGTH('')` equal to 0 or NULL? Why is `LENGTH(' ')` different?

**Question 2.** With `x=NULL`, is `x <> 'DONE'` FALSE or UNKNOWN? Does `WHERE` return that row?

**Question 3.** From the truth tables, what do `TRUE OR UNKNOWN`, `FALSE AND UNKNOWN`, and `NOT UNKNOWN` evaluate to?

**Question 4.** A table has three `BONUS` rows: 10, 20, and NULL. How do `COUNT(*)`, `COUNT(BONUS)`, and `AVG(BONUS)` differ?

**Question 5.** Why can `WHERE id NOT IN (SELECT blocked_id FROM blacklist)` return zero rows when `blacklist.blocked_id` contains NULL? Rewrite it assuming outer `id` is a primary key.

**Question 6.** Does `CHECK (score >= 0)` forbid `score=NULL`? Which constraint must be added to require a score?

**Question 7.** Do two `NULL` values match in `JOIN ... ON a.code=b.code`? If you intentionally match rows where both codes are missing, what result risk must you watch out for?

**Question 8.** In Java, a field can be `null` or `""`. Why can't you assume those two states stay distinct after saving to an Oracle `VARCHAR2` column?

**Question 9.** Why is `EMPTY_CLOB()` an example showing you shouldn't generalize "all zero-length values are `NULL`" across every Oracle data type?

**Question 10.** A `LEFT JOIN` initially keeps every customer, yet after adding `WHERE payment.status = 'PAID'`, customers with no payments vanish. Explain using three-valued logic and show how to keep every customer.

## 15. Mental Model to Remember

```text
       NULL = no defined value
                  │
                  ├── distinct from 0, '0', ' ', 'N/A'
                  │
                  └── in Oracle, '' is currently treated as NULL
                       for standard character values

       Comparing =, <> with NULL
                  │
                  ▼
                UNKNOWN
                  │
          ┌───────┼─────────┐
          ▼       ▼         ▼
       WHERE    AND/OR     NOT
       keeps    uses 3VL   UNKNOWN stays UNKNOWN
       TRUE
       only

       Explicit tools:
       IS NULL / IS NOT NULL
       CASE / NVL / COALESCE / NULLIF
       COUNT(*) differs from COUNT(column)
       NOT EXISTS avoids many NOT IN with NULL traps
       CHECK and UNIQUE have dedicated NULL rules
```

Three core rules when working with Oracle:

1. **Handle missing data intentionally.** Never use `= NULL` or `= ''` to test whether a column is missing a value.
2. **UNKNOWN is not FALSE.** In `WHERE`, both FALSE and UNKNOWN are filtered out; in `AND`/`OR`/`NOT`, UNKNOWN follows its own truth-table rules.
3. **NULL rules depend on the operation and context.** Aggregates, `GROUP BY`, `UNIQUE`, `CHECK`, outer joins, concatenation, and empty LOBs each have rules you must know.

When designing schemas, writing SQL, or mapping Java data into Oracle, explicitly define which cases mean "unknown", "not applicable", "left empty", "all spaces", and "actual value zero". Those decisions keep queries accurate, constraints sound, and application layers free from subtle bugs.
