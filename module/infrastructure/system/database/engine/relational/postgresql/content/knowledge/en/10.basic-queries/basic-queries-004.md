# Three-Valued Logic with NULL and IS DISTINCT FROM

In PostgreSQL, a SQL condition does not only produce `TRUE` and `FALSE`. Whenever `NULL` appears, many comparisons return a third state: **`UNKNOWN`**. This is the foundation of **three-valued logic (3VL)** in SQL.

If you are used to Java, you might expect a comparison expression to always be a `boolean`. In SQL, however:

```sql
SELECT
    (1 = 1) AS true_case,
    (1 = 2) AS false_case,
    (1 = NULL::integer) AS unknown_case;
```

The last column returns a **boolean NULL**, representing `UNKNOWN`, rather than `FALSE`.

This directly affects `WHERE`, `JOIN`, `NOT IN`, `CASE`, `CHECK`, aggregations, and how applications query for missing values. PostgreSQL provides the **`IS DISTINCT FROM`** and **`IS NOT DISTINCT FROM`** operators to compare two values in a way that always returns `TRUE` or `FALSE`, even when one or both operands are `NULL`.

This lesson is part of the *Basic Queries* chapter and focuses on writing sound SQL predicates, understanding truth tables, avoiding `NULL` pitfalls, and choosing operators that match business semantics. All examples can be practiced on a test PostgreSQL database.

## 1. Understanding NULL Before Writing Conditions

`NULL` is not an ordinary value like zero or an empty string. It represents the **absence of a value** in the SQL data model: unknown, unprovided, or not applicable, depending on the column's meaning.

Distinguish clearly:

| Representation | Meaning |
|---|---|
| `NULL` | No known SQL value for the column/expression |
| `0` | The number zero, a concrete value |
| `''` | An empty string, still a text value |
| `'NULL'` | A four-character string N-U-L-L |
| `FALSE` | The boolean false value |
| `'1970-01-01'` | A concrete date, not SQL's "unknown date" |
| `DEFAULT` | Keyword requesting the default expression in permitted write contexts |

Example:

```sql
SELECT
    NULL::text IS NULL AS missing_text,
    ''::text IS NULL AS empty_text_is_missing,
    0::integer IS NULL AS zero_is_missing,
    FALSE IS NULL AS false_is_missing;
```

Only the first expression evaluates to `TRUE`.

**Business meaning matters greatly.** For `paid_at TIMESTAMPTZ`, `NULL` may mean "not yet paid." For `middle_name TEXT`, `NULL` may mean "no middle name provided." Do not replace all `NULL`s with `0`, `'N/A'`, or a dummy date, because sentinel values can skew metrics or hide missing information.

### 1.1. NULL Does Not Mean a Row Does Not Exist

A row can exist completely legitimately while its `email` or `paid_at` column is NULL:

```text
customer_id | full_name | email
------------+-----------+-----------------------
1           | Lan       | lan@example.test
2           | Minh      | NULL
3           | Hoa       | hoa@example.test
```

The predicate `email IS NULL` selects **existing rows missing an email**. It is not a way to check whether a row is absent from the table.

With `LEFT JOIN`, PostgreSQL can also produce NULL result fields when **no matching row exists on the right**; distinguish that case from a right-hand column that was already NULL in an actual row.

## 2. Three Outcomes of a Boolean Expression

In SQL, conditions can evaluate to:

- **`TRUE`:** the condition is determined to hold.
- **`FALSE`:** the condition is determined not to hold.
- **`UNKNOWN`:** truth cannot be determined due to missing information, represented by a **`BOOLEAN` `NULL`**.

Example:

```sql
SELECT
    8 > 5                AS comparison_true,
    8 < 5                AS comparison_false,
    8 > NULL::integer    AS comparison_unknown;
```

With default `psql` formatting, a boolean NULL may look like a blank cell. To make it easier to spot:

```text
\pset null '[NULL]'
```

This is a **`psql` meta-command** that only changes display formatting. It does not turn NULL into the string `'[NULL]'` in the database. In JDBC applications or other SQL tools, rely on that tool's own NULL display settings.

### 2.1. Fundamental Truth Table

| Expression | SQL Result |
|---|---|
| `TRUE` | `TRUE` |
| `FALSE` | `FALSE` |
| `NULL::boolean` | `UNKNOWN` |
| `NOT TRUE` | `FALSE` |
| `NOT FALSE` | `TRUE` |
| `NOT NULL::boolean` | `UNKNOWN` |

**`UNKNOWN` is not a third literal stored in a `BOOLEAN` column.** A boolean column stores `TRUE`, `FALSE`, or `NULL`; the term `UNKNOWN` describes **how logic interprets NULL** when evaluating predicates.

## 3. Standard Comparisons with NULL

Standard relational operators such as `=`, `<>`, `<`, `>`, `<=`, and `>=` generally return **`UNKNOWN` whenever an operand is `NULL`** for those standard operators.

```sql
SELECT
    (5 = NULL::integer)       AS eq_null,
    (5 <> NULL::integer)      AS ne_null,
    (5 < NULL::integer)       AS lt_null,
    (NULL::integer = 5)       AS null_eq_number,
    (NULL::integer = NULL::integer) AS null_eq_null;
```

All five expressions return boolean NULL, i.e., UNKNOWN.

Why doesn't `NULL = NULL` return `TRUE`? Because two "unknown" placeholders are not guaranteed to represent the same real-world value. Two customers who both have not entered a tax ID do not necessarily share the same tax ID.

This is a **rule of the `=` operator**, not a claim that PostgreSQL never treats two NULLs as equivalent. `IS NOT DISTINCT FROM`, `GROUP BY`, and certain uniqueness rules handle NULL according to their own purposes.

### 3.1. Common Mistake: WHERE column = NULL

```sql
-- Fails to find NULL rows as expected:
SELECT *
FROM demo_3vl.customer
WHERE email = NULL;
```

Because `email = NULL` returns UNKNOWN for every row under standard comparison, `WHERE` keeps no rows from this predicate.

Correct approach:

```sql
SELECT *
FROM demo_3vl.customer
WHERE email IS NULL;
```

To find rows that have an email:

```sql
SELECT *
FROM demo_3vl.customer
WHERE email IS NOT NULL;
```

**`IS NULL` and `IS NOT NULL` always return `TRUE` or `FALSE`**, never UNKNOWN like `= NULL`.

### 3.2. Negation Does Not Turn UNKNOWN into TRUE Either

```sql
SELECT
    NOT (5 = NULL::integer) AS negated_unknown,
    5 <> NULL::integer     AS not_equal_unknown;
```

Both return UNKNOWN. Reason: **`NOT UNKNOWN = UNKNOWN`**.

Therefore, writing:

```sql
WHERE NOT (status = 'PAID')
```

does not automatically include rows where `status IS NULL`. `status = 'PAID'` is UNKNOWN for those rows; after `NOT` it remains UNKNOWN, so `WHERE` filters them out.

## 4. Truth Tables for NOT, AND, and OR

### 4.1. NOT

| A | `NOT A` |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

This is why Java's "not true means false" rule cannot be mechanically applied to SQL expressions involving NULL.

### 4.2. AND

`A AND B` is FALSE if either operand is definitely FALSE; TRUE if both are TRUE; and UNKNOWN otherwise.

| A | B = TRUE | B = FALSE | B = UNKNOWN |
|---|---|---|---|
| TRUE | TRUE | FALSE | UNKNOWN |
| FALSE | FALSE | FALSE | FALSE |
| UNKNOWN | UNKNOWN | FALSE | UNKNOWN |

Example:

```sql
SELECT
    (TRUE AND NULL::boolean)  AS true_and_unknown,
    (FALSE AND NULL::boolean) AS false_and_unknown,
    (NULL::boolean AND NULL::boolean) AS unknown_and_unknown;
```

Results respectively: UNKNOWN, FALSE, UNKNOWN.

A practical scenario:

```sql
WHERE is_active = TRUE
  AND email IS NOT NULL
```

If `is_active` is NULL, `is_active = TRUE` is UNKNOWN. If `email` is also NULL, `email IS NOT NULL` is FALSE; `UNKNOWN AND FALSE` evaluates to FALSE. In all cases, `WHERE` keeps only rows where the combined predicate is TRUE.

### 4.3. OR

`A OR B` is TRUE if at least one operand is TRUE; FALSE if both are FALSE; and UNKNOWN otherwise.

| A | B = TRUE | B = FALSE | B = UNKNOWN |
|---|---|---|---|
| TRUE | TRUE | TRUE | TRUE |
| FALSE | TRUE | FALSE | UNKNOWN |
| UNKNOWN | TRUE | UNKNOWN | UNKNOWN |

```sql
SELECT
    (TRUE OR NULL::boolean)   AS true_or_unknown,
    (FALSE OR NULL::boolean)  AS false_or_unknown,
    (NULL::boolean OR NULL::boolean) AS unknown_or_unknown;
```

Results respectively: TRUE, UNKNOWN, UNKNOWN.

### 4.4. Generating the Full Truth Table in PostgreSQL

```sql
WITH truth_values(v, label) AS (
    VALUES
        (TRUE, 'TRUE'),
        (FALSE, 'FALSE'),
        (NULL::boolean, 'UNKNOWN')
)
SELECT
    a.label AS a,
    b.label AS b,
    a.v AND b.v AS a_and_b,
    a.v OR b.v  AS a_or_b,
    NOT a.v AS not_a
FROM truth_values AS a
CROSS JOIN truth_values AS b
ORDER BY a.label, b.label;
```

When testing, use `\pset null '[UNKNOWN]'` in `psql` if you want boolean NULLs to stand out clearly. Note that `[UNKNOWN]` is only a **display label**; the underlying value is still NULL.

## 5. Why Two-Valued Logic Identities Can Surprise You

In classical two-valued logic, "P or not P" is always true. In 3VL, however:

```sql
SELECT
    (NULL::boolean OR NOT NULL::boolean) AS excluded_middle,
    (NULL::boolean AND NOT NULL::boolean) AS contradiction;
```

Both return UNKNOWN.

This explains the following trap:

```sql
SELECT *
FROM demo_3vl.customer
WHERE active = TRUE
   OR active <> TRUE;
```

An author might think this covers every row: "either equal to TRUE, or not equal to TRUE." In reality, **rows with `active IS NULL` are dropped** because both sides evaluate to UNKNOWN.

If the goal is to cover all states, state the intent explicitly: `active IS TRUE`, `active IS FALSE`, and `active IS UNKNOWN` are three tests that never return UNKNOWN. And a condition meant to match every row doesn't need to be written as an OR like that anyway.

**This does not mean all Boolean algebra breaks in SQL.** Many identities like De Morgan's laws still hold under the 3VL truth tables. The issue is simply that laws relying on "every proposition is strictly true or false" no longer hold unconditionally.

## 6. Preparing Practice Tables and Data

The sections below share a small schema. Run this in a lab database, not on production data.

```sql
CREATE SCHEMA IF NOT EXISTS demo_3vl;

CREATE TABLE demo_3vl.customer (
    customer_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT,
    country_code TEXT,
    active BOOLEAN
);

CREATE TABLE demo_3vl.sales_order (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES demo_3vl.customer(customer_id),
    status TEXT,
    note TEXT,
    paid_at TIMESTAMPTZ,
    amount NUMERIC(12, 2)
);

INSERT INTO demo_3vl.customer
    (customer_id, full_name, email, country_code, active)
VALUES
    (1, 'Lan',  'lan@example.test', 'VN', TRUE),
    (2, 'Minh', NULL,               'VN', NULL),
    (3, 'Hoa',  'hoa@example.test', NULL, FALSE),
    (4, 'An',   NULL,               NULL, TRUE),
    (5, 'Binh', 'binh@example.test','US', FALSE);

INSERT INTO demo_3vl.sales_order
    (order_id, customer_id, status, note, paid_at, amount)
VALUES
    (101, 1, 'NEW',       '',       NULL,  100000),
    (102, 1, 'PAID',      NULL,     '2026-11-10 10:00:00+07', 200000),
    (103, 2, NULL,        'manual',NULL,  150000),
    (104, 3, 'CANCELLED', NULL,     NULL,   50000),
    (105, 5, 'PAID',      NULL,     '2026-11-11 15:00:00+07', NULL);
```

Design notes:

- `customer.email` and `customer.country_code` are nullable to create UNKNOWN cases.
- `customer.active` is nullable to illustrate an unknown boolean; in real apps, evaluate whether `NOT NULL DEFAULT FALSE` is more appropriate.
- `sales_order.status` is nullable to contrast `<>` with `IS DISTINCT FROM`.
- `sales_order.note` intentionally includes both an empty string and NULL.
- `sales_order.amount` has one NULL row to test aggregate functions.
- `paid_at` is NULL for orders without a recorded payment timestamp.

Rows are inserted with fixed primary keys so the results in this lesson are easy to trace. Re-running the same `INSERT` fails due to duplicate primary keys. In your lab, create the tables once on a clean schema.

## 7. WHERE Keeps Only TRUE, Not UNKNOWN

This is the single most important rule when reading queries:

> **`WHERE` keeps a row if the predicate evaluates to `TRUE`. Both `FALSE` and `UNKNOWN` are discarded.**

Example:

```sql
SELECT customer_id, full_name, active
FROM demo_3vl.customer
WHERE active = TRUE
ORDER BY customer_id;
```

Result: customers 1 and 4 because `active = TRUE`. Customer 2 has `active = NULL` and does not appear, even though nothing proves that customer is inactive.

```sql
SELECT customer_id, full_name, active
FROM demo_3vl.customer
WHERE active <> TRUE
ORDER BY customer_id;
```

Result: customers 3 and 5 with `active = FALSE`. Customer 2 **still does not appear**.

To classify all three states:

```sql
SELECT
    customer_id,
    full_name,
    CASE
        WHEN active IS TRUE THEN 'ACTIVE'
        WHEN active IS FALSE THEN 'INACTIVE'
        ELSE 'UNKNOWN'
    END AS active_state
FROM demo_3vl.customer
ORDER BY customer_id;
```

Now customer 2 is classified as `UNKNOWN` rather than silently omitted from the result.

### 7.1. Not Every NULL Should Be Filtered Out

`WHERE email IS NULL` is an intentional query to find profiles missing an email:

```sql
SELECT customer_id, full_name
FROM demo_3vl.customer
WHERE email IS NULL
ORDER BY customer_id;
```

Result: customers 2 and 4.

If the business needs to contact customers, this is the list of records needing data entry. Had someone replaced NULL with `'unknown@example.test'` upfront, identifying profiles genuinely missing an email would be harder.

## 8. IS NULL and IS NOT NULL Always Return Deterministic Results

`IS NULL` and `IS NOT NULL` are designed specifically to test for missing values:

| Value `x` | `x IS NULL` | `x IS NOT NULL` |
|---|---|---|
| `10` | FALSE | TRUE |
| `0` | FALSE | TRUE |
| `''` | FALSE | TRUE |
| `FALSE` | FALSE | TRUE |
| `NULL` | TRUE | FALSE |

```sql
SELECT
    order_id,
    note,
    note IS NULL AS note_missing,
    note IS NOT NULL AS note_present
FROM demo_3vl.sales_order
ORDER BY order_id;
```

For order 101 with `note = ''`, `note IS NOT NULL` is TRUE. Empty strings and NULL are not treated as identical.

### 8.1. When You Need Both "NULL or Empty"

```sql
SELECT order_id, note
FROM demo_3vl.sales_order
WHERE note IS NULL
   OR note = ''
ORDER BY order_id;
```

In this condition:

- `note IS NULL` is TRUE when `note` is NULL.
- `note = ''` is TRUE when `note` is empty.
- Combining with OR works as intended, even though `note = ''` is UNKNOWN when `note` is NULL.

You can also use `NULLIF` to fold empty strings into NULL **within an expression**:

```sql
SELECT order_id, note
FROM demo_3vl.sales_order
WHERE NULLIF(note, '') IS NULL
ORDER BY order_id;
```

However, both forms express the same requirement only if **empty strings** are what should be treated as missing. If whitespace-only strings must also count as missing, you need a different rule such as `NULLIF(btrim(note), '') IS NULL`, and you must understand the whitespace/Unicode characteristics of your data.

## 9. IS DISTINCT FROM: NULL-Safe Comparisons

The `IS DISTINCT FROM` operator asks **whether two values differ**, with explicit rules for NULL:

- Two **NULL** values → **not distinct**.
- One NULL, one non-NULL → **distinct**.
- Both non-NULL → compared via the data type's equality semantics.

It **always returns `TRUE` or `FALSE`**, never UNKNOWN for ordinary NULL cases.

### 9.1. Truth Table

| A | B | `A = B` | `A <> B` | `A IS DISTINCT FROM B` |
|---|---|---|---|---|
| `7` | `7` | TRUE | FALSE | FALSE |
| `7` | `9` | FALSE | TRUE | TRUE |
| `7` | `NULL` | UNKNOWN | UNKNOWN | TRUE |
| `NULL` | `7` | UNKNOWN | UNKNOWN | TRUE |
| `NULL` | `NULL` | UNKNOWN | UNKNOWN | FALSE |

Test directly:

```sql
SELECT
    7 IS DISTINCT FROM 7 AS same_values,
    7 IS DISTINCT FROM 9 AS different_values,
    7 IS DISTINCT FROM NULL::integer AS value_vs_null,
    NULL::integer IS DISTINCT FROM 7 AS null_vs_value,
    NULL::integer IS DISTINCT FROM NULL::integer AS both_null;
```

Results respectively: FALSE, TRUE, TRUE, TRUE, FALSE.

**Do not interpret "distinct" here as two rows having different primary keys.** It compares **expression values** using the data type's equality operator, extended with explicit NULL handling.

### 9.2. IS NOT DISTINCT FROM: Equality Including NULL

`IS NOT DISTINCT FROM` is the negation of `IS DISTINCT FROM` and is commonly called **null-safe equality**:

| A | B | `A IS NOT DISTINCT FROM B` |
|---|---|---|
| `7` | `7` | TRUE |
| `7` | `9` | FALSE |
| `7` | `NULL` | FALSE |
| `NULL` | `7` | FALSE |
| `NULL` | `NULL` | TRUE |

```sql
SELECT
    NULL::text IS NOT DISTINCT FROM NULL::text AS both_missing,
    'VN'::text IS NOT DISTINCT FROM 'VN'::text AS same_country,
    'VN'::text IS NOT DISTINCT FROM NULL::text AS missing_country;
```

Results: TRUE, TRUE, FALSE.

Remember:

- **`=`:** equal when enough information exists; NULL usually yields UNKNOWN.
- **`IS NOT DISTINCT FROM`:** treats NULL and NULL as equivalent for comparison.
- **`<>`:** unequal when enough information exists.
- **`IS DISTINCT FROM`:** treats NULL as distinct from a real value, and NULL as not distinct from NULL.

### 9.3. Example on Customer Data

Find customers whose country code is **not 'VN'**, including those without a country code:

```sql
SELECT customer_id, full_name, country_code
FROM demo_3vl.customer
WHERE country_code IS DISTINCT FROM 'VN'
ORDER BY customer_id;
```

Result: customers 3, 4, 5. Customers 3 and 4 have NULL `country_code`, and the operator treats NULL as **distinct** from the concrete string `'VN'`.

Compare with:

```sql
SELECT customer_id, full_name, country_code
FROM demo_3vl.customer
WHERE country_code <> 'VN'
ORDER BY customer_id;
```

Only customer 5 (`'US'`) matches. Customers 3 and 4 are dropped because comparing against NULL returns UNKNOWN.

**Watch the semantics:** "unknown country" **does not mean actually outside Vietnam**. `IS DISTINCT FROM 'VN'` fits if the requirement is "stored value differs from 'VN', including missing data." If the business rule is "confirmed not in VN", write:

```sql
WHERE country_code IS NOT NULL
  AND country_code <> 'VN'
```

Choose the operator based on data meaning, not just because it returns more rows.

## 10. Using IS DISTINCT FROM and IS NOT DISTINCT FROM in UPDATE

Applications often want to avoid updating a row when the new value **is not actually different** from the old value. This helps with auditing, triggers, WAL volume, optimistic updates, and data synchronization—especially when either side can be NULL.

Example: update customer 3's `country_code` to `'VN'` if the current value differs:

```sql
UPDATE demo_3vl.customer
SET country_code = 'VN'
WHERE customer_id = 3
  AND country_code IS DISTINCT FROM 'VN'
RETURNING customer_id, country_code;
```

On the first run, the old `country_code` is NULL, which is distinct from `'VN'`, so the row updates. Running the exact same statement again evaluates to FALSE, so PostgreSQL skips updating that row.

If you instead write:

```sql
-- Fails to detect NULL as different from 'VN':
UPDATE demo_3vl.customer
SET country_code = 'VN'
WHERE customer_id = 4
  AND country_code <> 'VN';
```

customer 4 has NULL `country_code`, so the predicate is UNKNOWN and **the row is not updated**. When the goal is to change any differing value (including NULL), use `IS DISTINCT FROM`.

### 10.1. Syncing a Nullable Value from Another Source

Suppose an application has a pair `old_email` and `new_email`, both nullable:

```sql
WITH input(old_email, new_email) AS (
    VALUES
        (NULL::text, NULL::text),
        (NULL::text, 'new@example.test'),
        ('a@example.test', NULL::text),
        ('a@example.test', 'a@example.test')
)
SELECT
    old_email,
    new_email,
    old_email IS DISTINCT FROM new_email AS value_changed
FROM input;
```

`value_changed` evaluates to FALSE, TRUE, TRUE, FALSE respectively. This is a staple check in CDC/ETL pipelines: "did the data value actually change?", rather than "are they equal under three-valued logic?"

### 10.2. UPSERT Without Re-Writing Identical Values

```sql
CREATE TABLE demo_3vl.app_setting (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO demo_3vl.app_setting AS target
    (setting_key, setting_value)
VALUES
    ('theme', NULL)
ON CONFLICT (setting_key)
DO UPDATE SET
    setting_value = EXCLUDED.setting_value,
    updated_at = now()
WHERE target.setting_value IS DISTINCT FROM EXCLUDED.setting_value;
```

On the first insert, the row is created. On subsequent runs with `setting_value = NULL`, `NULL IS DISTINCT FROM NULL` is FALSE, so the `DO UPDATE` branch avoids rewriting the row for a duplicate sync event.

Had you used `target.setting_value <> EXCLUDED.setting_value`, the expression would also be UNKNOWN whenever NULL appears, **skipping valid transitions from NULL to a real value or vice versa**.

Note: the UPSERT `WHERE` clause only runs after a conflict is detected; constraints and other write-path effects still follow PostgreSQL rules. Do not treat this snippet as a complete concurrency pattern for every table.

## 11. IS NOT DISTINCT FROM in JOIN

In a regular `INNER JOIN`, the condition:

```sql
ON a.code = b.code
```

does not join two rows when both have `code IS NULL`, because `NULL = NULL` is UNKNOWN; `ON` requires TRUE to establish a match.

If the business genuinely wants to **treat NULL on both sides as the same group**, write:

```sql
ON a.code IS NOT DISTINCT FROM b.code
```

### 11.1. Experiment with a Code List

```sql
WITH source(code, source_name) AS (
    VALUES
        ('VN'::text, 'A'),
        (NULL::text, 'B'),
        ('US'::text, 'C')
),
lookup(code, label) AS (
    VALUES
        ('VN'::text, 'Viet Nam'),
        (NULL::text, 'Unspecified')
)
SELECT
    s.source_name,
    s.code AS source_code,
    l.label
FROM source AS s
LEFT JOIN lookup AS l
    ON s.code IS NOT DISTINCT FROM l.code
ORDER BY s.source_name;
```

Result:

| source_name | source_code | label |
|---|---|---|
| A | VN | Viet Nam |
| B | NULL | Unspecified |
| C | US | NULL |

If you replace `IS NOT DISTINCT FROM` with `=`, row B will **not join** with the `lookup.code IS NULL` row; `label` becomes NULL because `LEFT JOIN` finds no match.

### 11.2. You Should Not Always Join NULL with NULL

Two NULL customer IDs do not mean they refer to the **same customer**. If you join two large tables on a nullable identifier:

```sql
ON left_table.customer_id IS NOT DISTINCT FROM right_table.customer_id
```

and both tables have many rows with `customer_id IS NULL`, every NULL/NULL combination matches, inflating row counts and causing **corrupted report numbers**.

Only use null-safe equality when NULL represents a **shared missing group/key that is meant to join** under the data contract. For business foreign keys, prefer real keys, `NOT NULL` where appropriate, and standard `=`.

## 12. The LEFT JOIN Trap: ON and WHERE Are Not Equivalent

In an outer join, `ON` and `WHERE` apply at different logical stages.

To retrieve all customers and their `PAID` orders if any:

```sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.status
FROM demo_3vl.customer AS c
LEFT JOIN demo_3vl.sales_order AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

All customers are retained by `LEFT JOIN`. Customers without PAID orders get NULL in columns from `o`.

Moving that condition down to `WHERE`:

```sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.status
FROM demo_3vl.customer AS c
LEFT JOIN demo_3vl.sales_order AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

`WHERE o.status = 'PAID'` discards rows where `o.status` is NULL (whether unmatched or originally NULL), failing to keep customers without PAID orders as originally intended.

**Rule:** `ON` determines which pairs match; `WHERE` filters the result after the join step. In an outer join, moving a predicate from `ON` to `WHERE` can change both row count and query meaning.

### 12.1. Distinguishing a Missing Right-Hand Row from a Nullable Column

When finding customers **with no orders at all**, rely on a non-nullable key column on the right-hand table:

```sql
SELECT c.customer_id, c.full_name
FROM demo_3vl.customer AS c
LEFT JOIN demo_3vl.sales_order AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Because `o.order_id` is a PRIMARY KEY, NULL on the right indicates there is no matching order row. Had you used `WHERE o.note IS NULL`, you would also include actual orders whose `note` happened to be NULL, producing wrong results.

Another often clearer approach is `NOT EXISTS`, examined below.

## 13. IN: An Expression That Can Return UNKNOWN

`x IN (a,b,c)` normally behaves logically like `x = a OR x = b OR x = c` under SQL rules.

```sql
SELECT
    2 IN (1, 2, NULL) AS found_value,
    3 IN (1, 2, NULL) AS absent_with_null,
    3 IN (1, 2)       AS absent_without_null,
    NULL::integer IN (1, 2) AS null_left;
```

Result:

- `2 IN (1,2,NULL)` → TRUE, because one comparison is TRUE.
- `3 IN (1,2,NULL)` → UNKNOWN, because no comparison is TRUE and one compares against NULL.
- `3 IN (1,2)` → FALSE.
- `NULL IN (1,2)` → UNKNOWN.

`IN` does not automatically match a NULL inside the list. If you want to match NULL as a distinct member, model it explicitly with `IS NULL` or null-safe equality where appropriate.

## 14. NOT IN and NULL: A Very Common Filtering Bug

`NOT IN` is especially prone to bugs because the negation of UNKNOWN is still UNKNOWN.

```sql
SELECT
    3 NOT IN (1, 2, NULL) AS surprising_result;
```

The result is UNKNOWN, **not TRUE**.

Explanation:

```text
3 NOT IN (1, 2, NULL)

≈ NOT (3 = 1 OR 3 = 2 OR 3 = NULL)
≈ NOT (FALSE OR FALSE OR UNKNOWN)
≈ NOT UNKNOWN
≈ UNKNOWN
```

If this expression sits in `WHERE`, the row is discarded.

### 14.1. Subquery Scenario

Suppose an exclusion list of country codes has a row missing its code:

```sql
CREATE TABLE demo_3vl.excluded_country (
    country_code TEXT
);

INSERT INTO demo_3vl.excluded_country (country_code)
VALUES ('US'), (NULL);
```

Query:

```sql
SELECT c.customer_id, c.country_code
FROM demo_3vl.customer AS c
WHERE c.country_code NOT IN (
    SELECT e.country_code
    FROM demo_3vl.excluded_country AS e
);
```

Do not expect this query to return all customers outside US. Because the subquery contains NULL, `NOT IN` returns UNKNOWN for non-matching codes, filtering all of them out.

### 14.2. Option 1: Exclude NULL from the Right Set When Semantically Right

If the rule is "ignore `excluded_country` rows without a code":

```sql
SELECT c.customer_id, c.country_code
FROM demo_3vl.customer AS c
WHERE c.country_code IS NOT NULL
  AND c.country_code NOT IN (
      SELECT e.country_code
      FROM demo_3vl.excluded_country AS e
      WHERE e.country_code IS NOT NULL
  )
ORDER BY c.customer_id;
```

Here, `c.country_code IS NOT NULL` on the left is stated explicitly because the query only considers **known** countries. Customers with NULL country are not classified as outside the exclusion list.

### 14.3. Option 2: NOT EXISTS with the Chosen Comparison

```sql
SELECT c.customer_id, c.country_code
FROM demo_3vl.customer AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_3vl.excluded_country AS e
    WHERE e.country_code = c.country_code
)
ORDER BY c.customer_id;
```

`NOT EXISTS` checks whether any subquery row satisfies the predicate. When both codes are NULL, `e.country_code = c.country_code` is UNKNOWN, so it is not treated as a matching row. Under this logic, customers with NULL `country_code` **are kept**.

If you want NULL on both sides to count as the same missing code (so a NULL in the exclusion table also excludes customers missing `country_code`):

```sql
SELECT c.customer_id, c.country_code
FROM demo_3vl.customer AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_3vl.excluded_country AS e
    WHERE e.country_code IS NOT DISTINCT FROM c.country_code
)
ORDER BY c.customer_id;
```

**There is no single `NOT IN`-to-`NOT EXISTS` rewrite that fits every NULL semantics.** The difference lies in how a "matching row" is defined and how missing values are treated. Write the match condition to reflect the actual business intent.

### 14.4. EXISTS and NOT EXISTS Themselves Return TRUE or FALSE

An `EXISTS (subquery)` expression is TRUE if the subquery returns at least one row and FALSE if it returns zero rows; it **does not return UNKNOWN merely because columns in the subquery row are NULL**.

```sql
SELECT
    EXISTS (SELECT NULL::integer) AS has_one_row,
    EXISTS (SELECT 1 WHERE FALSE) AS has_no_row;
```

Results: TRUE and FALSE. What matters is **whether a row is returned**, not what values the cells hold.

## 15. ANY and ALL Also Follow Three-Valued Logic

Beyond `IN`, PostgreSQL supports quantified set comparisons with `ANY` and `ALL`. They are powerful, but you must understand NULL behavior.

Example:

```sql
SELECT
    2 = ANY (ARRAY[1, 2, NULL]::integer[]) AS any_match,
    3 = ANY (ARRAY[1, 2, NULL]::integer[]) AS any_unknown,
    3 <> ALL (ARRAY[1, 2, NULL]::integer[]) AS all_unknown;
```

With standard strict operators on NULL:

- `ANY` returns TRUE if at least one comparison is TRUE.
- If none are TRUE and at least one is UNKNOWN, the result is UNKNOWN.
- `ALL` returns FALSE if at least one comparison is FALSE.
- If none are FALSE and at least one is UNKNOWN, the result is UNKNOWN.

Distinguish **empty arrays**, **NULL arrays**, and **arrays containing NULL elements**:

```sql
SELECT
    3 = ANY (ARRAY[]::integer[]) AS any_empty,
    3 = ALL (ARRAY[]::integer[]) AS all_empty,
    3 = ANY (NULL::integer[]) AS any_null_array;
```

Results by standard rules: FALSE, TRUE, UNKNOWN.

These edge cases are especially important when JDBC passes array parameters: an empty array and a single-element array containing NULL mean very different things.

## 16. CASE WHEN: UNKNOWN Is Not Treated as a TRUE Branch

`CASE WHEN condition THEN ...` only picks a branch whose condition evaluates to TRUE. If a condition is FALSE or UNKNOWN, PostgreSQL moves on to the next branch.

```sql
SELECT
    customer_id,
    country_code,
    CASE
        WHEN country_code = 'VN' THEN 'Viet Nam'
        WHEN country_code <> 'VN' THEN 'Foreign'
        ELSE 'Unknown'
    END AS country_group
FROM demo_3vl.customer
ORDER BY customer_id;
```

For customers with NULL country, both comparisons evaluate to UNKNOWN, so execution falls through to `ELSE 'Unknown'`.

An even clearer way to write it:

```sql
SELECT
    customer_id,
    CASE
        WHEN country_code IS NULL THEN 'Unknown'
        WHEN country_code = 'VN' THEN 'Viet Nam'
        ELSE 'Foreign'
    END AS country_group
FROM demo_3vl.customer
ORDER BY customer_id;
```

Here readers immediately see how missing values are classified. Do not treat a NULL `country_code` as a foreign country if business logic needs to distinguish "unknown."

### 16.1. Simple CASE with WHEN NULL Does Not Behave as Often Expected

```sql
SELECT
    customer_id,
    CASE country_code
        WHEN 'VN' THEN 'Viet Nam'
        WHEN NULL THEN 'Unknown'
        ELSE 'Other'
    END AS country_label
FROM demo_3vl.customer
ORDER BY customer_id;
```

The `WHEN NULL` branch of a simple CASE **never matches a NULL `country_code`** under standard equality. The right approach is a searched CASE with `WHEN country_code IS NULL THEN ...`.

### 16.2. CASE Returns a Value, Not Always an Exhaustive Constraint Check

Example:

```sql
SELECT
    order_id,
    CASE WHEN amount > 0 THEN 'POSITIVE' ELSE 'NOT_POSITIVE' END
        AS amount_group
FROM demo_3vl.sales_order
ORDER BY order_id;
```

Order 105 has `amount NULL` and receives `'NOT_POSITIVE'`, even though it is **unknown** whether the amount is positive. If you need three labels:

```sql
CASE
    WHEN amount IS NULL THEN 'UNKNOWN'
    WHEN amount > 0 THEN 'POSITIVE'
    ELSE 'NON_POSITIVE'
END
```

`ELSE` does not always mean "the opposite condition is TRUE"; it also catches UNKNOWN outcomes from earlier branches.

## 17. Nullable Booleans: IS TRUE, IS FALSE, IS UNKNOWN

In PostgreSQL, a nullable boolean column can hold TRUE, FALSE, or NULL.

```sql
SELECT
    customer_id,
    active,
    active IS TRUE AS definitely_active,
    active IS FALSE AS definitely_inactive,
    active IS UNKNOWN AS status_unknown,
    active IS NOT TRUE AS not_known_active,
    active IS NOT FALSE AS not_known_inactive
FROM demo_3vl.customer
ORDER BY customer_id;
```

The `IS TRUE`, `IS FALSE`, `IS UNKNOWN`, and `IS NOT ...` predicates **always return a definite boolean**.

| active | `IS TRUE` | `IS FALSE` | `IS UNKNOWN` | `IS NOT TRUE` | `IS NOT FALSE` |
|---|---|---|---|---|---|
| TRUE | TRUE | FALSE | FALSE | FALSE | TRUE |
| FALSE | FALSE | TRUE | FALSE | TRUE | FALSE |
| NULL | FALSE | FALSE | TRUE | TRUE | TRUE |

**Two different conditions:**

```sql
WHERE active IS FALSE
```

selects only rows known to be FALSE.

```sql
WHERE active IS NOT TRUE
```

selects both FALSE **and NULL**. When business rules distinguish "deactivated account" from "unverified status", this difference is huge.

### 17.1. WHERE active and WHERE NOT active

```sql
SELECT customer_id
FROM demo_3vl.customer
WHERE active;

SELECT customer_id
FROM demo_3vl.customer
WHERE NOT active;
```

The first selects TRUE; the second selects FALSE; **both omit NULL**. To select FALSE or NULL, use `active IS NOT TRUE`.

## 18. CHECK Constraints: UNKNOWN Is Generally Accepted

This is where beginners frequently write a constraint believing data is fully protected.

```sql
CREATE TABLE demo_3vl.delivery (
    delivery_id INTEGER PRIMARY KEY,
    distance_km NUMERIC(10,2),
    CONSTRAINT ck_delivery_distance_positive
        CHECK (distance_km > 0)
);
```

Try:

```sql
INSERT INTO demo_3vl.delivery (delivery_id, distance_km)
VALUES (1, NULL);
```

This **succeeds**, because `distance_km > 0` returns UNKNOWN, and PostgreSQL considers a CHECK satisfied as long as the result **is not FALSE**.

However:

```sql
-- Intentionally violates CHECK:
INSERT INTO demo_3vl.delivery (delivery_id, distance_km)
VALUES (2, -1);
```

is rejected because the condition evaluates to FALSE.

To require that distance be both provided and positive:

```sql
CREATE TABLE demo_3vl.delivery_strict (
    delivery_id INTEGER PRIMARY KEY,
    distance_km NUMERIC(10,2) NOT NULL,
    CONSTRAINT ck_delivery_strict_distance_positive
        CHECK (distance_km > 0)
);
```

`NOT NULL` and `CHECK` guard two separate properties:

- `NOT NULL`: a value cannot be missing.
- `CHECK`: provided values must satisfy the valid domain.

### 18.1. DEFAULT Does Not Replace NOT NULL or CHECK Either

```sql
status TEXT DEFAULT 'NEW'
```

neither forbids `NULL` nor forbids `'WRONG'`. To enforce both:

```sql
status TEXT NOT NULL DEFAULT 'NEW',
CONSTRAINT ck_status_allowed
    CHECK (status IN ('NEW','PAID','CANCELLED'))
```

The default value applies when `INSERT` omits the column or explicitly specifies `DEFAULT`; when a client explicitly sends `NULL`, the default is not applied and `NOT NULL` rejects the write.

The distinction between **initializing a value** and **validating a value** is foundational to sound schema design.

## 19. UNIQUE and NULL: Different from Equality in WHERE

A standard PostgreSQL unique constraint permits multiple NULL values in a nullable column, because under default uniqueness rules NULLs are not treated as duplicates.

```sql
CREATE TABLE demo_3vl.external_ref (
    id INTEGER PRIMARY KEY,
    reference_code TEXT UNIQUE
);

INSERT INTO demo_3vl.external_ref (id, reference_code)
VALUES
    (1, NULL),
    (2, NULL),
    (3, 'EXT-001');
```

Both `(1, NULL)` and `(2, NULL)` are valid under standard `UNIQUE`. However:

```sql
-- Intentionally violates UNIQUE:
INSERT INTO demo_3vl.external_ref (id, reference_code)
VALUES (4, 'EXT-001');
```

is rejected because `EXT-001` is duplicated.

### 19.1. UNIQUE NULLS NOT DISTINCT (PostgreSQL 15+)

Starting in PostgreSQL 15, `UNIQUE NULLS NOT DISTINCT` tells PostgreSQL to treat NULLs as **not distinct when enforcing uniqueness**:

```sql
CREATE TABLE demo_3vl.external_ref_strict (
    id INTEGER PRIMARY KEY,
    reference_code TEXT,
    CONSTRAINT uq_external_ref_strict_code
        UNIQUE NULLS NOT DISTINCT (reference_code)
);
```

Now:

```sql
INSERT INTO demo_3vl.external_ref_strict (id, reference_code)
VALUES (1, NULL);

-- Intentionally violates UNIQUE NULLS NOT DISTINCT:
INSERT INTO demo_3vl.external_ref_strict (id, reference_code)
VALUES (2, NULL);
```

The second row is rejected because NULL and NULL are considered **not distinct** under that uniqueness policy.

This shows PostgreSQL has **multiple distinct NULL-handling contexts**:

- `NULL = NULL` → UNKNOWN.
- `NULL IS NOT DISTINCT FROM NULL` → TRUE.
- Standard `UNIQUE` → allows multiple NULLs.
- `UNIQUE NULLS NOT DISTINCT` → disallows duplicate NULL values under that unique constraint.

Do not collapse these rules into a single blanket statement like "NULLs are always equal" or "NULLs are never equal."

### 19.2. ON CONFLICT Also Depends on the Unique Definition

With a standard unique constraint, two rows with `reference_code NULL` do not conflict; they will not automatically trigger the same `ON CONFLICT (reference_code)` branch simply because both are NULL.

If business logic requires at most one row with an "unassigned reference", pick the right constraint/design rather than trying to use `ON CONFLICT` to compensate for a missing uniqueness rule.

## 20. DISTINCT, GROUP BY, and NULL

In `SELECT DISTINCT`, PostgreSQL removes duplicate rows. NULL values in the same column position are handled **according to result-set deduplication rules**, not merely by evaluating `NULL = NULL` in `WHERE`.

```sql
SELECT DISTINCT country_code
FROM demo_3vl.customer
ORDER BY country_code NULLS LAST;
```

The sample `country_code` values are VN, VN, NULL, NULL, US. `DISTINCT` yields three entries: `VN`, `US`, and a single `NULL` row.

Similarly:

```sql
SELECT
    country_code,
    COUNT(*) AS customers
FROM demo_3vl.customer
GROUP BY country_code
ORDER BY country_code NULLS LAST;
```

Customers with NULL `country_code` are grouped into **one NULL group** in `GROUP BY`, with `COUNT(*) = 2` on the initial sample data before any practice UPDATE exercises alter it.

### 20.1. Grouping NULLs Differs from Concluding They Share a Real Code

Grouping two missing values together **does not prove** they represent the same actual country. It simply gives the report an "unknown" bucket.

When analyzing customer share by country, display the UNKNOWN group clearly:

```sql
SELECT
    COALESCE(country_code, '[UNKNOWN]') AS country_group,
    COUNT(*) AS customer_count
FROM demo_3vl.customer
GROUP BY COALESCE(country_code, '[UNKNOWN]')
ORDER BY country_group;
```

Here `'[UNKNOWN]'` is a display label, yet if real data could ever contain that literal string, both would merge into the same group. In production systems, separate **NULL flags** from **display labels** or enforce domain rules to prevent sentinel collisions.

### 20.2. COUNT(DISTINCT ...) Ignores NULL

```sql
SELECT
    COUNT(*) AS total_customers,
    COUNT(country_code) AS known_country_count,
    COUNT(DISTINCT country_code) AS distinct_known_countries
FROM demo_3vl.customer;
```

On the initial sample data:

- `COUNT(*)` = 5 because it counts every row.
- `COUNT(country_code)` = 3 because it skips the two NULL rows.
- `COUNT(DISTINCT country_code)` = 2 because the two distinct non-NULL values are `VN` and `US`.

**`SELECT DISTINCT` can return a NULL row, whereas `COUNT(DISTINCT column)` does not count NULL.** These are two different operations with different semantics, not a contradiction.

## 21. Aggregate Functions and How They Handle NULL

Most common aggregate functions such as `SUM`, `AVG`, `MIN`, and `MAX` ignore NULL values in their inputs; `COUNT(*)` counts rows and `COUNT(column)` counts non-NULL values of that column.

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(amount) AS orders_with_amount,
    COUNT(*) - COUNT(amount) AS orders_missing_amount,
    SUM(amount) AS sum_known_amount,
    AVG(amount) AS avg_known_amount
FROM demo_3vl.sales_order;
```

On the initial sample data:

- Total orders: 5.
- Orders with non-NULL amount: 4.
- Orders missing amount: 1.
- `SUM(amount)` sums the four present values; **it does not treat NULL as a known zero**.
- `AVG(amount)` divides the sum of known values by the count of non-NULL values (4), not by 5.

If all amounts are NULL or the input set is empty, `SUM(amount)` returns NULL; `COUNT(*)` and `COUNT(amount)` return integer counts, which can be 0.

### 21.1. COUNT(*) FILTER to Count NULLs Explicitly

```sql
SELECT
    COUNT(*) FILTER (WHERE amount IS NULL) AS missing_amount,
    COUNT(*) FILTER (WHERE amount IS NOT NULL) AS known_amount,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders
FROM demo_3vl.sales_order;
```

`FILTER (WHERE ...)` follows predicate logic: only rows where the filter evaluates to TRUE enter the aggregate.

### 21.2. COALESCE(SUM(...),0) Is Not Always Equivalent to SUM(COALESCE(...,0))

```sql
SELECT
    COALESCE(SUM(amount), 0) AS total_or_zero,
    SUM(COALESCE(amount, 0)) AS total_with_missing_as_zero
FROM demo_3vl.sales_order;
```

When rows exist, both formulas can yield the same arithmetic sum, yet they carry **different meanings**:

- `COALESCE(SUM(amount), 0)` replaces NULL in the **aggregate total** if there were no non-NULL inputs to sum.
- `SUM(COALESCE(amount,0))` treats **each missing amount** as 0 in the input.

With `AVG`, the difference becomes obvious:

```sql
SELECT
    AVG(amount) AS avg_known_amount,
    AVG(COALESCE(amount, 0)) AS avg_missing_as_zero
FROM demo_3vl.sales_order;
```

The second formula treats an order with a missing amount as 0 and includes it in the denominator, which can skew reports. Never substitute 0 for NULL before aggregating unless business rules confirm missing values truly mean 0.

## 22. HAVING Also Keeps Only Groups Where the Condition Is TRUE

`HAVING` filters groups after `GROUP BY` using the same logical rule as `WHERE`: a group is kept only when the condition evaluates to TRUE.

```sql
SELECT
    customer_id,
    AVG(amount) AS avg_amount
FROM demo_3vl.sales_order
GROUP BY customer_id
HAVING AVG(amount) > 100000
ORDER BY customer_id;
```

If a group contains only NULL amounts, `AVG(amount)` returns NULL; `> 100000` evaluates to UNKNOWN; and that group is discarded.

To isolate groups with no known amounts:

```sql
SELECT
    customer_id,
    COUNT(amount) AS known_amount_rows,
    AVG(amount) AS avg_amount
FROM demo_3vl.sales_order
GROUP BY customer_id
HAVING COUNT(amount) = 0
ORDER BY customer_id;
```

On the initial sample data, customer 5 has one order with NULL amount and therefore matches the group with zero known amounts.

## 23. ORDER BY and NULL Placement

`ORDER BY` can sort rows containing NULL, though that does not mean PostgreSQL uses `NULL = NULL` to determine ordering.

By default, PostgreSQL treats NULLs as larger than non-NULL values in standard sorting:

- `ORDER BY x ASC` places NULLs **last**.
- `ORDER BY x DESC` places NULLs **first**.

Specify placement explicitly when output order matters:

```sql
SELECT customer_id, full_name, country_code
FROM demo_3vl.customer
ORDER BY country_code ASC NULLS LAST, customer_id;

SELECT customer_id, full_name, country_code
FROM demo_3vl.customer
ORDER BY country_code DESC NULLS LAST, customer_id;
```

`NULLS FIRST` / `NULLS LAST` are sort-ordering rules; **they do not alter stored data and do not turn NULL into a real value**.

When paginating, add a deterministic tie-breaker key such as `customer_id` to prevent unstable ordering among rows sharing the same `country_code`.

## 24. IS DISTINCT FROM with Multiple Columns and Row Expressions

When comparing multi-column tuples, you can use row constructors in PostgreSQL:

```sql
SELECT
    ROW(1, NULL::text) IS NOT DISTINCT FROM
        ROW(1, NULL::text) AS same_pair,
    ROW(1, NULL::text) IS DISTINCT FROM
        ROW(1, 'x'::text) AS changed_pair;
```

Results: TRUE and TRUE.

This is useful when detecting whether any attribute in a group changed:

```sql
WITH changes(
    old_status, old_note,
    new_status, new_note
) AS (
    VALUES
        ('NEW'::text, NULL::text, 'NEW'::text, NULL::text),
        ('NEW'::text, NULL::text, 'PAID'::text, NULL::text),
        ('NEW'::text, NULL::text, 'NEW'::text, 'done'::text)
)
SELECT
    old_status,
    old_note,
    new_status,
    new_note,
    ROW(old_status, old_note)
        IS DISTINCT FROM ROW(new_status, new_note) AS any_change
FROM changes;
```

Results respectively: FALSE, TRUE, TRUE.

Avoid abusing `ROW(...)` comparisons across hundreds of columns to decide whole-row updates: comparison cost, per-column semantics, whether every type supports equality, and excluded fields (such as `updated_at`) must all be considered.

### 24.1. Row-Valued IS NULL Has Its Own Nuances

For row/composite values, PostgreSQL follows special `IS NULL` rules: a row is considered NULL if the row itself is NULL or **all of its fields are NULL**; `IS NOT NULL` requires the row to be non-NULL and **all of its fields to be non-NULL**. Consequently, for a row containing some NULL fields and some non-NULL fields, **both `row IS NULL` and `row IS NOT NULL` return FALSE**.

This differs from scalar `x IS NULL` / `x IS NOT NULL`, which are always logical complements. In typical queries, inspect individual fields or use `IS [NOT] DISTINCT FROM` on rows when you want null-safe tuple comparison.

Example:

```sql
SELECT
    ROW(NULL::integer, 1) IS NULL AS row_is_null,
    ROW(NULL::integer, 1) IS NOT NULL AS row_is_not_null,
    ROW(NULL::integer, 1) IS DISTINCT FROM
        ROW(NULL::integer, 2) AS row_has_change;
```

Results respectively: FALSE, FALSE, TRUE. Never extrapolate scalar intuition onto composite values.

## 25. NULLIF and COALESCE: Two Complementary Tools

### 25.1. NULLIF(a,b)

`NULLIF(a,b)` returns NULL if `a` and `b` are equal under expression comparison rules; otherwise it returns `a`.

```sql
SELECT
    NULLIF('', '') AS empty_to_null,
    NULLIF('A', '') AS nonempty_kept,
    NULLIF(0, 0) AS zero_to_null;
```

An application might use:

```sql
SELECT
    order_id,
    NULLIF(btrim(note), '') AS normalized_note
FROM demo_3vl.sales_order
ORDER BY order_id;
```

This **presents** empty or default-whitespace-only strings (`btrim`) as NULL in the output. It does not update the table.

### 25.2. COALESCE(a,b,...)

`COALESCE` picks the first **non-NULL** expression:

```sql
SELECT
    order_id,
    COALESCE(note, '[NO NOTE]') AS note_display
FROM demo_3vl.sales_order
ORDER BY order_id;
```

For NULL notes, output is `'[NO NOTE]'`. For `note = ''`, the output remains an empty string because `''` **is not NULL**.

To handle both:

```sql
SELECT
    order_id,
    COALESCE(NULLIF(btrim(note), ''), '[NO NOTE]') AS note_display
FROM demo_3vl.sales_order
ORDER BY order_id;
```

Do not mistake `'[NO NOTE]'` for data actually stored in the table. It is purely a display value chosen by the query.

### 25.3. COALESCE Does Not Replace IS DISTINCT FROM Everywhere

A common workaround:

```sql
COALESCE(a, '<missing>') = COALESCE(b, '<missing>')
```

If real data can ever contain `'<missing>'`, this comparison **treats NULL and that literal string as equal**, introducing a bug. Furthermore, type casting, collations, and column types can make this pattern awkward.

When the goal is simply to **compare two values including NULL**, write directly:

```sql
a IS NOT DISTINCT FROM b
```

which is clearer and avoids fake sentinel values.

## 26. Is Null-Safe Comparison Only About "NULL = NULL"?

No. `IS DISTINCT FROM` also prevents missing rows when **one side is NULL and the other is non-NULL**, especially in UPDATEs and diff checks.

Conceptually, `a IS DISTINCT FROM b` behaves like:

```sql
CASE
    WHEN a IS NULL AND b IS NULL THEN FALSE
    WHEN a IS NULL OR b IS NULL THEN TRUE
    ELSE a <> b
END
```

This illustrates the logic for data types with appropriate equality/inequality operators—**not advice to replace PostgreSQL's built-in operator with a verbose CASE in every query**.

In real queries, writing `IS DISTINCT FROM` clarifies intent and avoids bugs from hand-assembling multiple OR/AND conditions with UNKNOWN.

### 26.1. Not Every Data Type Has Identical Equality Semantics

`IS DISTINCT FROM` delegates to the data type's equality comparison semantics. For types like text, numeric, timestamp, or tuples of equality-comparable types, the meaning is well-defined.

However, "different" does not always mean **byte-for-byte** comparison. Collations, data types, comparison rules, and normalization can affect outcomes. For instance, if business rules treat emails differing only in letter case as equivalent, specify that rule explicitly (via normalization, appropriate types, or collations) rather than expecting `IS NOT DISTINCT FROM` to do it automatically.

## 27. IS DISTINCT FROM and Indexes: Correctness First, Optimization Second

Because `IS [NOT] DISTINCT FROM` has its own comparison semantics, do not assume the planner will always optimize it identically to `=` or `<>` on a standard B-tree index.

Example:

```sql
CREATE INDEX idx_customer_country_code
ON demo_3vl.customer(country_code);

EXPLAIN
SELECT customer_id
FROM demo_3vl.customer
WHERE country_code IS NOT DISTINCT FROM 'VN';
```

The lab table has five rows, so `Seq Scan` is likely optimal. Even on large tables, whether PostgreSQL uses an index depends on **version, selectivity, expressions, data types, statistics, and whether the predicate can become an index condition**. Never assume an operator that looks "equality-like" always yields the same plan.

### 27.1. IS NULL Can Leverage Indexes

PostgreSQL B-tree indexes store NULL entries and can serve suitable queries. Example:

```sql
EXPLAIN
SELECT customer_id
FROM demo_3vl.customer
WHERE country_code IS NULL;
```

A regular B-tree index or a partial index tailored for missing-data lookups can help:

```sql
CREATE INDEX idx_customer_missing_country
ON demo_3vl.customer(customer_id)
WHERE country_code IS NULL;
```

This example fits workloads that frequently query customers missing `country_code`. Do not add extra production indexes without evaluating missing-row count, table size, and write overhead. On five sample rows, the planner may still choose `Seq Scan`.

### 27.2. Be Careful When Swapping Operators to "Force an Index"

If you replace:

```sql
WHERE country_code IS NOT DISTINCT FROM $1
```

with:

```sql
WHERE country_code = $1
```

then when `$1` is NULL, **the result changes**: the first finds rows with NULL `country_code`, whereas `=` evaluates to UNKNOWN. An "optimization" that alters semantics is a logic bug, even if the new plan runs faster.

If a parameter can be NULL and performance is critical, split into two query branches (`IS NULL` vs. `=` when non-NULL) at the application layer with **identical null-safe semantics**, and benchmark against real workloads rather than silently dropping NULL cases.

## 28. JDBC: Binding NULL and Reading SQL Booleans

In Java applications, a nullable column must not be treated like a two-state primitive `boolean`.

### 28.1. Binding NULL Parameters Explicitly

Example finding customers by email, including when the email parameter is NULL:

```java
String sql = """
    SELECT customer_id, full_name, email
    FROM demo_3vl.customer
    WHERE email IS NOT DISTINCT FROM ?
    ORDER BY customer_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    String email = suppliedEmail; // Can be null.
    if (email == null) {
        ps.setNull(1, java.sql.Types.VARCHAR);
    } else {
        ps.setString(1, email);
    }

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getInt("customer_id"));
        }
    }
}
```

`IS NOT DISTINCT FROM ?` preserves intent when `email` is bound as NULL. Had you written `WHERE email = ?`, a NULL parameter would make the comparison UNKNOWN and fail to find rows with NULL email.

The `?` parameter syntax belongs to JDBC `PreparedStatement`; in `psql`, you cannot paste a query containing `?` and expect it to act like a JDBC bind placeholder.

### 28.2. Reading Nullable Booleans with wasNull()

`ResultSet.getBoolean(...)` returns a primitive `boolean`. When the SQL value is NULL, JDBC returns `false`, so you must call `wasNull()` to tell whether the value read was actually NULL.

```java
boolean activeValue = rs.getBoolean("active");
boolean activeWasNull = rs.wasNull();

Boolean active = activeWasNull ? null : activeValue;
```

If you skip `wasNull()`, the application conflates `active = FALSE` with `active = NULL`. Many frameworks support boxed `Boolean` to preserve three states, though you should verify mapping and business-logic usage.

### 28.3. Java null and SQL NULL Do Not Share the Same Operators

In Java:

```java
Objects.equals(a, b)
```

returns `true` if both references are null. However, SQL's:

```sql
a = b
```

does not behave that way for SQL NULL. If you want semantics close to `Objects.equals`, use `IS NOT DISTINCT FROM` for types with compatible equality.

Never use string concatenation to build `... = NULL` predicates; always parameterize SQL and pick the right operator.

## 29. PostgreSQL Statistics and NULL Optimization

The planner does not treat NULL as nonexistent. PostgreSQL tracks statistics on each column's NULL fraction and value distributions, inspectable via `pg_stats`:

```sql
ANALYZE demo_3vl.customer;

SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals
FROM pg_stats
WHERE schemaname = 'demo_3vl'
  AND tablename = 'customer'
  AND attname IN ('email', 'country_code', 'active')
ORDER BY attname;
```

`null_frac` is the **estimated fraction of NULLs** from statistics. The sample dataset is too small for numbers to reflect large workloads.

When comparing plans:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id
FROM demo_3vl.customer
WHERE country_code IS NULL;
```

and:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id
FROM demo_3vl.customer
WHERE country_code = 'VN';
```

note that the planner may estimate different row counts because the NULL fraction differs from the frequency of `'VN'`. Choosing between Index Scan and Seq Scan still depends on cost, statistics, and table size.

`EXPLAIN ANALYZE` executes the SQL statement. For `UPDATE`/`DELETE`, never run it in production solely to inspect a plan without transaction safeguards and side-effect assessment.

## 30. Special Case: JSON null vs. SQL NULL

PostgreSQL's `JSONB` type includes a JSON `null` value. **JSON null** is not the same as **SQL NULL**.

```sql
SELECT
    'null'::jsonb IS NULL AS json_null_is_sql_null,
    NULL::jsonb IS NULL AS sql_null_is_sql_null,
    'null'::jsonb IS NOT DISTINCT FROM NULL::jsonb
        AS json_null_equals_sql_null;
```

Results: FALSE, TRUE, FALSE. A `JSONB` value holding the JSON literal `null` is still a **non-SQL-NULL JSONB value**.

Key extraction can yield different kinds of NULL:

```sql
SELECT
    ('{"name": null}'::jsonb -> 'name') AS json_null_value,
    ('{"name": null}'::jsonb ->> 'name') AS text_extraction,
    ('{}'::jsonb -> 'name') AS missing_key;
```

Typically:

- The `->` operator returns JSONB null when the key exists with a JSON null value.
- The `->>` operator returns SQL NULL when extracting JSON null as text.
- A missing key yields SQL NULL with these access operators.

When comparing values, know whether an expression has type `jsonb` or `text` and whether it returns SQL NULL or JSON null. This is a frequent source of bugs when filtering JSONB API payloads.

## 31. Writing Safe Conditions Matching Business Intent

| Intent | Condition to Consider | Why |
|---|---|---|
| Email not provided | `email IS NULL` | Tests for missing value |
| Email provided | `email IS NOT NULL` | Does not confuse empty string with NULL |
| Confirmed active | `active IS TRUE` | Only TRUE |
| Confirmed inactive | `active IS FALSE` | Only FALSE |
| Not confirmed active | `active IS NOT TRUE` | FALSE or NULL |
| Definitely outside VN | `country_code IS NOT NULL AND country_code <> 'VN'` | Does not turn "unknown" into "non-VN" |
| Stored value differs from VN including NULL | `country_code IS DISTINCT FROM 'VN'` | Distinguishes NULL from a concrete value |
| Match two values including both NULL | `a IS NOT DISTINCT FROM b` | Null-safe equality |
| Detect change including to/from NULL | `old_value IS DISTINCT FROM new_value` | Always returns a definite boolean |
| Find customers with no orders | `NOT EXISTS (SELECT 1 ... WHERE o.customer_id = c.customer_id)` | Checks row existence rather than nullable columns |
| Exclude a list that may contain NULL | `NOT EXISTS` or filter NULL per business rule | Avoids the NOT IN trap |
| Only non-blank notes | `note IS NOT NULL AND btrim(note) <> ''` | NULL and empty string are two cases |
| No payment timestamp yet | `paid_at IS NULL` | Checks missing timestamp state |
| Only orders with known positive amount | `amount > 0` | NULL is filtered out by WHERE; can add IS NOT NULL for clarity |

There is no rule saying "always use `IS DISTINCT FROM` instead of `=`." When you want standard SQL `=` semantics, or when columns are `NOT NULL` and parameters are guaranteed non-NULL, `=` is concise and appropriate. `IS DISTINCT FROM` is a tool for **deliberately specifying NULL handling**, not a blanket rule for every comparison.

## 32. Common Misconceptions

**"NULL is a special value, so NULL = NULL must be TRUE."** False under standard SQL `=`: the result is UNKNOWN. For null-safe equality, use `IS NOT DISTINCT FROM`.

**"WHERE keeps every row whose condition is not FALSE."** False. `WHERE` keeps only TRUE; UNKNOWN is discarded as well.

**"NOT turns UNKNOWN into TRUE."** False. `NOT UNKNOWN` remains UNKNOWN.

**"column <> 'X' includes NULL."** False. For NULL, `<>` returns UNKNOWN; to include missing values as different, use `IS DISTINCT FROM`.

**"NOT IN is always shorthand for NOT EXISTS."** False when NULLs exist or match semantics differ. Verify NULL semantics before rewriting.

**"LEFT JOIN keeps all left rows regardless of conditions in WHERE."** False. A `WHERE` predicate after an outer join can discard unmatched rows due to NULLs in right-hand columns.

**"CHECK (quantity > 0) automatically forbids NULL."** False. `CHECK` accepts UNKNOWN; add `NOT NULL` if the column is required.

**"UNIQUE means the column cannot be NULL."** False. Standard unique constraints allow multiple NULLs; `NOT NULL` is a separate constraint.

**"Converting all NULLs to 0 before SUM/AVG always improves reports."** False. It can distort denominators, distributions, or erase missing-data signals.

**"IS NOT DISTINCT FROM always uses indexes identically to =."** Not guaranteed. Inspect the execution plan for your PostgreSQL version and data.

**"JSONB null and SQL NULL are the same thing."** False. The JSON literal `null` lives inside a non-NULL JSONB value, whereas SQL NULL is the absence of a SQL value.

## 33. Practice Exercises

### Exercise 1 — Three Outcomes of a Comparison

Predict the results:

```sql
SELECT
    (10 = 10) AS a,
    (10 = 20) AS b,
    (10 = NULL::integer) AS c,
    (NULL::integer = NULL::integer) AS d;
```

**Answer:** TRUE, FALSE, UNKNOWN, UNKNOWN.

### Exercise 2 — Two Non-Equivalent Queries

```sql
SELECT customer_id FROM demo_3vl.customer
WHERE country_code <> 'VN';

SELECT customer_id FROM demo_3vl.customer
WHERE country_code IS DISTINCT FROM 'VN';
```

**Question:** on the initial sample dataset, which rows differ?

**Answer:** the first query only returns customers with a known code different from VN—customer 5 (`US`). The second also returns customers 3 and 4 (NULL code) because `IS DISTINCT FROM` treats NULL as distinct from `'VN'`.

If you ran the UPDATE from an earlier section, actual data may differ. When practicing standalone exercises, start from the initial sample dataset.

### Exercise 3 — NOT IN with NULL

Predict:

```sql
SELECT
    9 NOT IN (1, 2, NULL) AS a,
    9 NOT IN (1, 2) AS b,
    2 NOT IN (1, 2, NULL) AS c;
```

**Answer:** UNKNOWN, TRUE, FALSE. Reason: in `a`, there is no match yet a comparison with NULL occurs; in `b`, every equality is FALSE and then negated; in `c`, there is an explicit match.

### Exercise 4 — Filtering Unknown Booleans

**Requirement:** retrieve customers known to be inactive **or** with unknown active status.

```sql
SELECT customer_id, full_name, active
FROM demo_3vl.customer
WHERE active IS NOT TRUE
ORDER BY customer_id;
```

**Answer:** customers 2, 3, 5 on the initial dataset. Do not use `WHERE NOT active` if you want to include NULL.

### Exercise 5 — Finding Customers Without Orders

**Requirement:** list customers who do not appear in `sales_order`.

```sql
SELECT c.customer_id, c.full_name
FROM demo_3vl.customer AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_3vl.sales_order AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

**Answer:** customer 4 on the initial dataset. `EXISTS` checks whether matching rows exist without depending on nullable columns in the orders table.

### Exercise 6 — Does CHECK Allow NULL?

```sql
CREATE TABLE demo_3vl.exercise_check (
    id INTEGER PRIMARY KEY,
    score INTEGER CHECK (score BETWEEN 0 AND 100)
);

INSERT INTO demo_3vl.exercise_check (id, score)
VALUES (1, NULL);
```

**Question:** is the INSERT valid?

**Answer:** yes, because `CHECK` allows UNKNOWN. If `score` is required, add `NOT NULL` alongside `CHECK`.

### Exercise 7 — Counting Missing Data Without Skewing Averages

**Requirement:** compute total orders, orders with known amount, orders missing amount, and the average of known amounts.

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(amount) AS known_amount,
    COUNT(*) FILTER (WHERE amount IS NULL) AS missing_amount,
    AVG(amount) AS avg_known_amount
FROM demo_3vl.sales_order;
```

**Answer:** on the initial sample set there are 5 orders, 4 with known amount, and 1 missing; the average is computed over the four known amounts. Do not use `AVG(COALESCE(amount, 0))` if "unknown" does not mean 0.

### Exercise 8 — Detecting Real Updates

```sql
SELECT
    NULL::text IS DISTINCT FROM NULL::text AS a,
    NULL::text IS DISTINCT FROM 'A'::text AS b,
    'A'::text IS DISTINCT FROM 'A'::text AS c,
    'A'::text IS DISTINCT FROM 'B'::text AS d;
```

**Answer:** FALSE, TRUE, FALSE, TRUE. The operator returns a definite boolean and fits nullable before/after comparisons.

### Exercise 9 — JOIN When Both Keys Are NULL

**Question:** if A and B both have `code NULL`, does `A.code = B.code` join them?

**Answer:** no, because the condition evaluates to UNKNOWN. `A.code IS NOT DISTINCT FROM B.code` would match them. Whether that makes business sense depends on the meaning of `code` and NULL.

### Exercise 10 — Fixing a Misleading CASE

A report uses:

```sql
CASE WHEN amount > 0 THEN 'POSITIVE' ELSE 'NON_POSITIVE' END
```

**Requirement:** add a state when `amount` is NULL.

```sql
CASE
    WHEN amount IS NULL THEN 'UNKNOWN'
    WHEN amount > 0 THEN 'POSITIVE'
    ELSE 'NON_POSITIVE'
END
```

**Answer:** a searched CASE with an explicit NULL check prevents the report from accidentally labeling missing data as non-positive.

## 34. Checklist Before Deploying Conditions Involving NULL

Whenever a query has nullable columns or nullable parameters, ask:

1. Can the column be NULL according to both DDL **and real data**?
2. Does NULL mean "unknown", "not applicable", or a state requiring special handling?
3. Can `=` / `<>` expressions evaluate to UNKNOWN?
4. How do `WHERE`, `HAVING`, `ON`, and `CASE WHEN` treat UNKNOWN?
5. If using `NOT IN`, can the right-hand subquery or list contain NULL?
6. In an outer join, are right-side predicates placed correctly in `ON` vs. `WHERE`?
7. If comparing changes, should `IS DISTINCT FROM` be used?
8. If matching NULLs on both sides, is that semantically valid or will it produce spurious join pairs?
9. For `CHECK` and `UNIQUE`, what is the intended policy for NULL?
10. Do `SUM`, `AVG`, `COUNT`, `DISTINCT`, and `GROUP BY` ignore or group NULL as desired?
11. Does the JDBC/ORM layer distinguish NULL from FALSE/0/empty string?
12. Once logic is correct, should `EXPLAIN` be checked for performance on real data?

A short SQL query does not necessarily have simple semantics. With NULL, the most important thing is **stating comparison intent explicitly**.

## 35. Summary Diagram

```text
                       SQL VALUE
                           │
                ┌──────────┴──────────┐
                │                     │
                ▼                     ▼
           Known value               NULL
                │                     │
                ▼                     ▼
            =, <>, <, >          =, <>, <, >
                │                     │
                ▼                     ▼
          TRUE or FALSE            UNKNOWN
                │                     │
                └──────────┬──────────┘
                           ▼
                   AND / OR / NOT
                           │
                           ▼
                 TRUE / FALSE / UNKNOWN
                           │
             ┌─────────────┴─────────────┐
             │                           │
             ▼                           ▼
       WHERE/HAVING/ON               CASE WHEN
       accepts TRUE only         picks TRUE only
             │                           │
             ▼                           ▼
      Keep row / match join       Pick result branch

TO TEST FOR NULL:
  x IS NULL / x IS NOT NULL        → TRUE or FALSE

FOR NULL-SAFE COMPARISON:
  a IS DISTINCT FROM b             → different, including distinct from NULL
  a IS NOT DISTINCT FROM b         → equivalent, including both NULL

IN DATA MODELING:
  NOT NULL                         → forbids NULL
  CHECK                            → FALSE rejected, UNKNOWN usually accepted
  Default UNIQUE                   → allows multiple NULLs
  UNIQUE NULLS NOT DISTINCT (15+)  → treats NULLs as duplicates for uniqueness

IN REPORTING:
  COUNT(*)                         → counts all rows
  COUNT(x)                         → counts only non-NULL x
  SUM(x), AVG(x)                   → ignores NULL inputs
  DISTINCT / GROUP BY              → groups NULL per result-set rules
```

Five core principles to remember:

1. **NULL brings standard comparisons into three-valued logic.** `NULL = NULL` and `value <> NULL` do not return TRUE or FALSE; they return UNKNOWN.
2. **WHERE keeps only TRUE.** Both FALSE and UNKNOWN are excluded; hence `NOT` does not "rescue" NULL rows.
3. **IS DISTINCT FROM and IS NOT DISTINCT FROM handle nullable comparisons cleanly.** They always return a definite boolean and are ideal for change detection, data syncing, or intentional NULL matching.
4. **NULL semantics depend on context.** `NOT IN`, outer joins, `CHECK`, `UNIQUE`, `GROUP BY`, `COUNT`, and `AVG` each have distinct rules you must know rather than relying on a single slogan.
5. **Business correctness matters more than short syntax.** "Unknown country" does not automatically mean "outside Vietnam"; "missing amount" does not automatically mean 0; "two missing reference codes" do not necessarily point to the same entity.

When a PostgreSQL query returns fewer rows than expected or a "not equal" filter misbehaves on NULLs, check three questions in order: **could the expression evaluate to UNKNOWN, how do WHERE/JOIN handle UNKNOWN, and how does the business actually want NULL treated?** Answering these three questions usually pinpoints the bug without piling on ad-hoc patches.
