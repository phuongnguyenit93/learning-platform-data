# IN, BETWEEN, LIKE, ILIKE, and Combined Conditions in PostgreSQL

When querying a table, we rarely want every row. An e-commerce page might need to find products belonging to **one of several categories**, priced **within a budget range**, whose names **contain a keyword**, that are still **active**, and are **in stock**. PostgreSQL provides operators and expressions to express these filters directly in SQL.

The four key groups in this lesson are:

- `IN` and `NOT IN`: test whether a value belongs to a set of values.
- `BETWEEN` and `NOT BETWEEN`: test whether a value falls within a bounded range.
- `LIKE`, `NOT LIKE`: pattern-match strings, typically case-sensitive.
- `ILIKE`, `NOT ILIKE`: pattern-match strings **case-insensitively** according to PostgreSQL's language/collation rules.

Conditions are combined with `AND`, `OR`, and `NOT`, along with parentheses to enforce evaluation precedence.

What matters is not just syntax. A syntactically valid `WHERE` clause can still return wrong results if you ignore how SQL handles `NULL`, choose the wrong time boundary, mistake wildcards in `LIKE`, or combine `AND` and `OR` without parentheses.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Use `WHERE column IN (...)` to filter by multiple values and understand its relationship to `=` comparisons.
2. Use `BETWEEN` properly with **inclusive** endpoints, as well as design **half-open** intervals for `TIMESTAMP/TIMESTAMPTZ`.
3. Use `LIKE` with `%`, `_`, and `ESCAPE`; distinguish prefix, suffix, and substring matching.
4. Use `ILIKE` for case-insensitive matching in PostgreSQL without confusing it with accent-insensitive search.
5. Write compound conditions using `AND`, `OR`, `NOT`, and parentheses.
6. Understand three-valued logic (`TRUE`, `FALSE`, `NULL`) in `WHERE` and avoid the `NOT IN` with `NULL` trap.
7. Build safely parameterized queries for user-supplied lists and search strings.
8. Recognize the performance impact of search patterns and indexes; use `EXPLAIN` to inspect query plans.
9. Practice on a PostgreSQL table with fixed data so results are easy to verify.

The commands that create or drop data are strictly for a **dedicated test database**. Never run table-recreation scripts against environments holding real data.

---

## 2. Where Filter Conditions Sit in a SELECT Statement

The familiar structure:

```sql
SELECT
    column_1,
    column_2
FROM schema_name.table_name
WHERE condition
ORDER BY column_1;
```

In this structure:

- `FROM` selects the data source.
- `WHERE` retains rows whose predicate evaluates to **TRUE**.
- `ORDER BY` sorts the final result set as requested.
- `LIMIT`, if present, restricts how many rows are returned under the applicable ordering.

Conceptual example:

```sql
SELECT sku, product_name, price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
ORDER BY price DESC;
```

The output includes only `ACTIVE` products, sorted by descending price.

**Never infer result order when `ORDER BY` is omitted.** PostgreSQL makes no promise that rows will appear by ID, insertion order, or disk order.

### 2.1. WHERE Does Not Keep UNKNOWN Outcomes

SQL uses **three-valued logic**: `TRUE`, `FALSE`, and `UNKNOWN` (typically displayed as `NULL` when observed in results). In `WHERE`, **only rows whose condition evaluates to TRUE are kept**. Rows evaluating to `FALSE` or `NULL` are discarded.

Example:

```sql
SELECT
    5 > 3 AS condition_true,
    5 > 8 AS condition_false,
    NULL::INTEGER > 0 AS condition_unknown;
```

`NULL > 0` is not `FALSE`, it is `NULL`: PostgreSQL does not have enough information to decide.

This affects `IN`, `BETWEEN`, `LIKE`, and every combined condition. The following sections demonstrate concrete examples.

---

## 3. Preparing Practice Data

Create a products table to illustrate every filter group. The data uses fixed timestamps, multiple categories, product names with varying letter cases, and `NULL`s in several columns.

> **Run only in a practice database.** The `DROP TABLE` statement below deletes `query_filter_lab.products` and any existing data in it.

```sql
CREATE SCHEMA IF NOT EXISTS query_filter_lab;

DROP TABLE IF EXISTS query_filter_lab.products;

CREATE TABLE query_filter_lab.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL
        CHECK (price >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('ACTIVE', 'DRAFT', 'ARCHIVED')),
    stock_quantity INTEGER
        CHECK (stock_quantity >= 0),
    discount_pct INTEGER
        CHECK (discount_pct BETWEEN 0 AND 100),
    created_at TIMESTAMPTZ NOT NULL
);

INSERT INTO query_filter_lab.products (
    sku, product_name, category, price,
    status, stock_quantity, discount_pct, created_at
)
VALUES
    ('BOOK-PG-01',   'PostgreSQL Basics',      'BOOK',
     120000, 'ACTIVE',   15, 10,   '2026-01-01 08:00:00+00'),

    ('BOOK-SQL-02',  'SQL Advanced',            'BOOK',
     260000, 'ACTIVE',    2, NULL, '2026-01-15 10:00:00+00'),

    ('BOOK-JAVA-03', 'Java Programming',          'BOOK',
     200000, 'DRAFT',   NULL, 5,   '2026-02-01 09:30:00+00'),

    ('PEN-BLUE-01',  'Blue Ballpoint Pen',             'STATIONERY',
      12000, 'ACTIVE',  100, NULL, '2026-01-30 14:00:00+00'),

    ('PEN-RED-02',   'Red Ink Pen',              'STATIONERY',
      25000, 'ACTIVE',    0, 0,    '2026-02-15 08:30:00+00'),

    ('NOTE-A5-01',   'A5 Notebook',                   'STATIONERY',
      45000, 'DRAFT',    12, 15,  '2026-02-28 23:59:59+00'),

    ('MOUSE-WL-01',  'Wireless Mouse',         'ACCESSORY',
     350000, 'ACTIVE',    8, 20,  '2026-03-01 00:00:00+00'),

    ('KB-MECH-01',   'Mechanical Keyboard',             'ACCESSORY',
     950000, 'ARCHIVED',  1, NULL,'2026-03-15 10:00:00+00'),

    ('USB-C-01',     'USB-C Cable',               'ACCESSORY',
      99000, 'ACTIVE',   25, 5,   '2026-03-20 12:00:00+00'),

    ('BOOK-PG-04',   'postgresql in practice',    'BOOK',
     300000, 'ACTIVE',    0, NULL,'2026-03-31 23:59:59+00'),

    ('BOOK-PG-05',   'POSTGRESQL in depth',   'BOOK',
     500000, 'ACTIVE', NULL, NULL,'2026-04-01 00:00:00+00'),

    ('GIFT-NEW-01',  '100% New Gift Box',        'GIFT',
      70000, 'DRAFT',     3, NULL,'2026-04-10 16:00:00+00'),

    ('PEN_BLUE_03',  '2B Pencil',              'STATIONERY',
       8000, 'ACTIVE',    7, NULL,'2026-02-20 09:00:00+00');
```

Verify:

```sql
SELECT
    product_id,
    sku,
    category,
    price,
    status,
    stock_quantity,
    discount_pct,
    created_at
FROM query_filter_lab.products
ORDER BY product_id;

SELECT COUNT(*) AS total_products
FROM query_filter_lab.products;
```

If no other session has modified the table, the count is **13 rows**.

The `NULL` values in `stock_quantity` and `discount_pct` are intentional: they demonstrate the behavior of `NOT IN`, `BETWEEN`, and combined conditions when data is missing.

### 3.1. Columns Used in This Lesson

| Column | Meaning | Key Notes |
| --- | --- | --- |
| `sku` | Product code | Contains both `-` and `_` characters |
| `product_name` | Display name | Contains PostgreSQL/postgresql/POSTGRESQL casings |
| `category` | Category | `BOOK`, `STATIONERY`, `ACCESSORY`, `GIFT` |
| `price` | Price | `NUMERIC(12,2)` type |
| `status` | Status | `ACTIVE`, `DRAFT`, `ARCHIVED` |
| `stock_quantity` | Stock count | Nullable; 0 differs from `NULL` |
| `discount_pct` | Discount percentage | Nullable; 0 differs from `NULL` |
| `created_at` | Creation timestamp | `TIMESTAMPTZ` with time zone |

---

## 4. IN: Testing Membership in a Set

Syntax:

```sql
expression IN (value_1, value_2, value_3, ...)
```

This is close to the comparison:

```sql
expression = value_1
OR expression = value_2
OR expression = value_3
```

Example finding products in two categories:

```sql
SELECT sku, product_name, category
FROM query_filter_lab.products
WHERE category IN ('BOOK', 'ACCESSORY')
ORDER BY category, sku;
```

Rows in BOOK or ACCESSORY are kept, while STATIONERY and GIFT are excluded.

### 4.1. IN Makes Queries Shorter and Easier to Extend

Without `IN`:

```sql
SELECT sku, status
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
   OR status = 'DRAFT'
ORDER BY sku;
```

Equivalent for non-NULL data:

```sql
SELECT sku, status
FROM query_filter_lab.products
WHERE status IN ('ACTIVE', 'DRAFT')
ORDER BY sku;
```

`IN` is easier to read when matching one column against multiple values. For complex expressions or predicates across different fields, `OR` remains more suitable.

### 4.2. IN Checks Exact Equality, Not Substrings

For example:

```sql
WHERE category IN ('BOOK', 'GIFT')
```

means `category` must **equal** `BOOK` or `GIFT`, not merely contain one of those substrings.

`IN ('BOOK')` is not the same as `LIKE '%BOOK%'`. Also do not use `IN` when users want to search keywords inside a product name; use `LIKE`/`ILIKE` for that.

### 4.3. NOT IN: Filtering Values Outside a Set

```sql
SELECT sku, status
FROM query_filter_lab.products
WHERE status NOT IN ('DRAFT', 'ARCHIVED')
ORDER BY sku;
```

Because `status` in the lab table is `NOT NULL` and only allows three states, this returns `ACTIVE` products.

Semantically, it corresponds to:

```sql
WHERE status <> 'DRAFT'
  AND status <> 'ARCHIVED'
```

However, `NOT IN` carries a **NULL trap** explained right below.

### 4.4. IN with NULL: A Non-Match Can Return UNKNOWN

Consider:

```sql
SELECT
    'BOOK' IN ('BOOK', NULL) AS case_match,
    'GIFT' IN ('BOOK', NULL) AS case_no_match,
    NULL::TEXT IN ('BOOK', 'GIFT') AS null_left;
```

Meaning:

| Expression | Result |
| --- | --- |
| `'BOOK' IN ('BOOK', NULL)` | `TRUE` because an element matches |
| `'GIFT' IN ('BOOK', NULL)` | `NULL` because `BOOK` does not match, and comparing with `NULL` is unknown |
| `NULL IN ('BOOK', 'GIFT')` | `NULL` |

In `WHERE`, both `FALSE` and `NULL` are filtered out. If you assume `'GIFT' IN ('BOOK', NULL)` always returns FALSE, subsequent negated predicates will fail.

### 4.5. A Particularly Dangerous Trap: NOT IN with NULL on the Right

Query:

```sql
SELECT sku, discount_pct
FROM query_filter_lab.products
WHERE discount_pct NOT IN (0, 10, NULL)
ORDER BY sku;
```

On the lab dataset, this query **returns zero rows**.

Reason:

- For `discount_pct = 0` or `10`, `IN` is TRUE, so `NOT IN` is FALSE.
- For other values such as `5`, `15`, or `20`, no numeric element matches, yet the `NULL` element makes `IN` evaluate to UNKNOWN; negating UNKNOWN stays UNKNOWN.
- For `discount_pct IS NULL`, the result is also UNKNOWN.

You can see this clearly:

```sql
SELECT
    5 NOT IN (0, 10, NULL) AS five_case,
    0 NOT IN (0, 10, NULL) AS zero_case,
    NULL::INTEGER NOT IN (0, 10) AS null_case;
```

Never treat `NULL` as an ordinary number or value in a list. To find products with a **known** discount other than 0 or 10:

```sql
SELECT sku, discount_pct
FROM query_filter_lab.products
WHERE discount_pct IS NOT NULL
  AND discount_pct NOT IN (0, 10)
ORDER BY sku;
```

Result for rows with recorded discounts in the lab:

| SKU | discount_pct |
| --- | ---: |
| `BOOK-JAVA-03` | 5 |
| `MOUSE-WL-01` | 20 |
| `NOTE-A5-01` | 15 |
| `USB-C-01` | 5 |

If business rules want to **include products without a discount**, state it explicitly:

```sql
WHERE discount_pct IS NULL
   OR discount_pct NOT IN (0, 10)
```

There is no single default NULL behavior that works for every business rule.

### 4.6. IN with a Subquery

The set of values on the right does not have to be hard-coded:

```sql
SELECT p.sku, p.product_name
FROM query_filter_lab.products AS p
WHERE p.category IN (
    SELECT c.category_code
    FROM (
        VALUES ('BOOK'), ('GIFT')
    ) AS c(category_code)
)
ORDER BY p.sku;
```

This is a self-contained subquery example. In real applications, the subquery might read an allowed-categories table.

When taking a set of values from a table, consider `IN (SELECT ...)` or `EXISTS` depending on relationship semantics, NULL rules, and execution plan.

In particular:

```sql
WHERE p.sku NOT IN (
    SELECT excluded_sku
    FROM some_exclusion_table
)
```

risks dropping every non-matching row if the subquery emits even **one `NULL` row**. To check "no exclusion row exists with matching SKU", `NOT EXISTS` usually expresses intent more directly:

```sql
-- Syntax template: some_exclusion_table is an illustrative table not yet created.
WHERE NOT EXISTS (
    SELECT 1
    FROM some_exclusion_table AS e
    WHERE e.excluded_sku = p.sku
)
```

Define what should happen if either key can be NULL. `NOT EXISTS` and `NOT IN` are not equivalent across all NULL scenarios.

### 4.7. IN with a Column Pair

PostgreSQL can compare value tuples using row constructors:

```sql
SELECT sku, category, status
FROM query_filter_lab.products
WHERE (category, status) IN (
    ('BOOK', 'ACTIVE'),
    ('GIFT', 'DRAFT')
)
ORDER BY sku;
```

This keeps `ACTIVE` `BOOK` products and `DRAFT` `GIFT` products. It **differs from**:

```sql
WHERE category IN ('BOOK', 'GIFT')
  AND status IN ('ACTIVE', 'DRAFT')
```

because the second form also allows `BOOK + DRAFT` and `GIFT + ACTIVE`. Whenever multiple columns must match **exact value pairs**, express the pairs properly.

### 4.8. Dynamic Lists and PostgreSQL Arrays

In PostgreSQL, when an application passes a variable-length list, you can use `= ANY(array)`:

```sql
SELECT sku, category
FROM query_filter_lab.products
WHERE category = ANY(ARRAY['BOOK', 'GIFT']::TEXT[])
ORDER BY sku;
```

For non-NULL array values, this behaves like `IN ('BOOK', 'GIFT')`.

You can use a prepared statement:

```sql
PREPARE products_by_categories(TEXT[]) AS
SELECT sku, category
FROM query_filter_lab.products
WHERE category = ANY($1)
ORDER BY sku;

EXECUTE products_by_categories(
    ARRAY['BOOK', 'ACCESSORY']::TEXT[]
);

DEALLOCATE products_by_categories;
```

Key notes:

- `IN ()` with an empty list **is not valid SQL syntax**. The application must handle empty lists separately or use array binding.
- `= ANY('{}'::TEXT[])` returns FALSE for ordinary values because no element matches.
- `= ANY` still follows NULL logic when an array contains NULLs and does not automatically solve `NOT IN`.
- Never manually concatenate client-supplied values into SQL strings. Bind parameters and use array types supported by your driver when needed.

---

## 5. BETWEEN: Testing Whether a Value Lies in a Range

Syntax:

```sql
expression BETWEEN lower_bound AND upper_bound
```

For standard comparisons, this is equivalent to:

```sql
expression >= lower_bound
AND expression <= upper_bound
```

**Both endpoints are included.**

### 5.1. BETWEEN with Numbers

Find products priced from 100,000 to 300,000, inclusive:

```sql
SELECT sku, price
FROM query_filter_lab.products
WHERE price BETWEEN 100000 AND 300000
ORDER BY price, sku;
```

Rows priced at 120000, 200000, 260000, and **300000** all appear. A price of exactly 300000 is not excluded.

An equivalent explicit form:

```sql
WHERE price >= 100000
  AND price <= 300000
```

The explicit form is helpful when the two ends need different operators, such as `>=` on the lower bound and `<` on the upper bound.

### 5.2. NOT BETWEEN

```sql
SELECT sku, price
FROM query_filter_lab.products
WHERE price NOT BETWEEN 100000 AND 300000
ORDER BY price, sku;
```

This keeps products priced **below 100000 or above 300000**, provided the price is known and the comparison is determinate.

Logically equivalent in standard cases to:

```sql
WHERE price < 100000
   OR price > 300000
```

If `price` is NULL, both `BETWEEN` and `NOT BETWEEN` evaluate to UNKNOWN and are filtered out by WHERE.

### 5.3. Bounds Are Not Automatically Swapped

```sql
SELECT 200 BETWEEN 300 AND 100 AS reversed_bounds;
```

Result is FALSE, because 200 cannot be both `>= 300` and `<= 100`.

PostgreSQL provides `BETWEEN SYMMETRIC` to handle unordered bounds, though in applications you should generally **validate user min/max inputs** rather than silently reversing them:

```sql
SELECT 200 BETWEEN SYMMETRIC 300 AND 100 AS symmetric_case;
```

Result is TRUE. Use this only when business rules genuinely accept bounds in either order.

### 5.4. BETWEEN with DATE

If a column has type `DATE`:

```sql
-- Syntax example for a table with an order_date column of type DATE.
WHERE order_date BETWEEN DATE '2026-03-01'
                     AND DATE '2026-03-31'
```

March 31 is included in the range. This works nicely when each value stores only a **calendar date** without time-of-day.

With `TIMESTAMP` or `TIMESTAMPTZ`, however, extra care is required.

### 5.5. Time Trap: BETWEEN with TIMESTAMPTZ

The lab table has `created_at TIMESTAMPTZ`. To retrieve all rows in **March 2026 UTC**, the safe and unambiguous pattern is a **half-open** interval:

```sql
SELECT sku, created_at
FROM query_filter_lab.products
WHERE created_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-04-01 00:00:00+00'
ORDER BY created_at, sku;
```

This keeps rows from the exact start of March 1 up to just before the start of April 1, regardless of sub-second precision.

SKUs created in March 2026 UTC in the lab:

| SKU | Declared Timestamp (UTC) |
| --- | --- |
| `MOUSE-WL-01` | 2026-03-01 00:00:00+00 |
| `KB-MECH-01` | 2026-03-15 10:00:00+00 |
| `USB-C-01` | 2026-03-20 12:00:00+00 |
| `BOOK-PG-04` | 2026-03-31 23:59:59+00 |

Row `BOOK-PG-05` has `created_at = 2026-04-01 00:00:00+00` and is excluded.

Avoid writing:

```sql
-- Does not cover all times on March 31:
WHERE created_at BETWEEN '2026-03-01'
                     AND '2026-03-31'
```

For timestamp types, a bare date converts to midnight (`00:00:00`) under current time zone rules. Almost all timestamps on March 31 will fall past that upper bound.

Also avoid fixing it by appending `23:59:59` and assuming all timestamps are covered: PostgreSQL stores microsecond precision, so fractional seconds after `:59` can still be missed.

**Practical rule for timestamps:** prefer `start <= time AND time < next_boundary` when filtering by day, month, or calendar period.

### 5.6. Time Zones Are Part of the Requirement

When a requirement states "March in Vietnam time", define month boundaries in that desired time zone rather than arbitrarily using UTC or the session time zone:

```sql
SELECT sku, created_at
FROM query_filter_lab.products
WHERE created_at >= TIMESTAMPTZ '2026-03-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-04-01 00:00:00+07'
ORDER BY created_at;
```

Compared to UTC, these bounds shift by 7 hours. In regions observing daylight saving time, compute boundaries in the **named regional time zone** rather than hard-coding a fixed offset year-round.

Casting `created_at::DATE` also depends on the session time zone. Wrapping a column in an expression can also affect normal index usage. With time-range queries, explicit bounds are easier to control.

### 5.7. BETWEEN with TEXT

`BETWEEN` also works on text:

```sql
SELECT 'M'::TEXT BETWEEN 'A' AND 'Z' AS example_text_range;
```

However, text comparison depends on **collation and sort rules**, not universally "letters in the alphabet" across all languages. Never use text ranges to replace prefix checks or SKU format validation without understanding collation.

To find codes starting with `BOOK-`, `LIKE 'BOOK-%'` states the intent far more clearly than constructing an alphabetic range.

### 5.8. BETWEEN with NULL

```sql
SELECT
    NULL::INTEGER BETWEEN 1 AND 10 AS unknown_value,
    5 BETWEEN NULL::INTEGER AND 10 AS unknown_lower,
    5 NOT BETWEEN 1 AND NULL::INTEGER AS unknown_upper;
```

These cases can return NULL if no component comparison is decisive enough to yield FALSE/TRUE under three-valued logic. Do not treat `BETWEEN` as "wrong" for NULLs and reach for `NOT BETWEEN` to find missing values.

To filter missing values:

```sql
SELECT sku
FROM query_filter_lab.products
WHERE discount_pct IS NULL
ORDER BY sku;
```

If you want discounts between 5 and 20 or unrecorded discounts:

```sql
SELECT sku, discount_pct
FROM query_filter_lab.products
WHERE discount_pct BETWEEN 5 AND 20
   OR discount_pct IS NULL
ORDER BY sku;
```

Predicate semantics must come from business requirements, not intuition about the phrase "not in range."

---

## 6. LIKE: Pattern Matching Strings

The `LIKE` operator compares a string against a **pattern**.

Syntax:

```sql
text_expression LIKE pattern
```

Two most important wildcard characters:

| Character | Meaning | Example |
| --- | --- | --- |
| `%` | Matches **0 or more** characters | `'SQL%'`: starts with SQL |
| `_` | Matches **exactly one** character | `'A_C'`: A, one character, C |

Other characters in a pattern match literally under current comparison semantics. A `LIKE` pattern must match the **entire string**, so to match a substring in the middle you need `%` on both sides.

### 6.1. Prefix Matching

Find SKUs starting with `BOOK-`:

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE sku LIKE 'BOOK-%'
ORDER BY sku;
```

The pattern `'BOOK-%'` means:

- Must start with `BOOK-`.
- Followed by **0 or more characters**.

The `-` here is an ordinary hyphen, **not a LIKE wildcard**.

### 6.2. Suffix Matching

```sql
SELECT sku
FROM query_filter_lab.products
WHERE sku LIKE '%-01'
ORDER BY sku;
```

SKUs ending in `-01` are kept. The leading `%` allows any characters before the suffix.

### 6.3. Substring Matching

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name LIKE '%SQL%'
ORDER BY sku;
```

This finds the exact uppercase/lowercase substring `SQL` inside product names per current comparison rules. It matches `'PostgreSQL Basics'` and `'SQL Advanced'`, but not `'postgresql in practice'` or `'POSTGRESQL in depth'` because their casing differs.

For case-insensitive matching, use `ILIKE` shown in the next section.

### 6.4. Start and End Patterns

| Pattern | Typical Meaning |
| --- | --- |
| `'SQL%'` | Starts with SQL |
| `'%SQL'` | Ends with SQL |
| `'%SQL%'` | Contains SQL anywhere |
| `'SQL'` | Matches the entire string SQL exactly |
| `'A_C'` | A, exactly one character, then C |
| `'A__C'` | A, exactly two characters, then C |
| `'%'` | Any non-NULL string, including empty string |
| `'_'` | Any string of exactly one character |
| `'__'` | Any string of exactly two characters |

Try directly in SQL:

```sql
SELECT
    'SQL' LIKE 'SQL' AS exact_match,
    'SQL Advanced' LIKE 'SQL%' AS prefix_match,
    'PostgreSQL' LIKE '%SQL' AS suffix_match,
    'ABC' LIKE 'A_C' AS one_character_match,
    'AC' LIKE 'A_C' AS too_short;
```

The first, second, third, and fourth columns all return TRUE; `'AC' LIKE 'A_C'` returns FALSE because it lacks one character for `_`.

### 6.5. Wildcard _ Is Not a Literal Underscore

In the lab table there is an SKU:

```text
PEN_BLUE_03
```

If you run:

```sql
SELECT sku
FROM query_filter_lab.products
WHERE sku LIKE 'PEN_%'
ORDER BY sku;
```

`_` in the pattern is a **single-character wildcard**, so the pattern matches both `PEN-...` and `PEN_...`, not just codes containing an actual underscore.

To match a literal `_`, you must **escape** it.

---

## 7. ESCAPE: Matching Literal % and _

When search data genuinely contains percent signs or underscores, you must distinguish wildcards from literal data characters.

PostgreSQL supports:

```sql
expression LIKE pattern ESCAPE '!'
```

Here, `!` is chosen as the **escape character**. Prefixing `%` or `_` with `!` makes them literal characters.

### 7.1. Finding SKUs with an Underscore at a Specific Position

```sql
SELECT sku
FROM query_filter_lab.products
WHERE sku LIKE 'PEN!_%' ESCAPE '!'
ORDER BY sku;
```

Breakdown:

- `PEN`: three literal characters.
- `!_`: **literal underscore**.
- `%`: arbitrary remainder.

On the sample data, this pattern matches `PEN_BLUE_03` without matching `PEN-BLUE-01` or `PEN-RED-02`.

### 7.2. Finding Names Containing a Literal %

The name `'100% New Gift Box'` contains a literal percent sign. Query:

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name LIKE '%100!%%' ESCAPE '!';
```

Pattern breakdown:

```text
%      : any prefix
100    : literal digits 100
!%     : literal % character
%      : any suffix
```

The query matches `GIFT-NEW-01`.

### 7.3. When the Escape Character Also Appears in Data

When `!` is your escape character, if a user searches for `!` itself, it must be escaped as `!!` in the pattern. A helper building a literal-substring pattern typically escapes in order:

1. `!` to `!!`.
2. `%` to `!%`.
3. `_` to `!_`.
4. Prepend/append `%` **if the application wants substring matching**.

This rule is separate from escaping single quotes in SQL strings. With bind parameters, the driver safely passes string literals to SQL; however, **LIKE wildcards are still pattern syntax**, so you must still escape them if you do not want user input treated as wildcards.

### 7.4. Why Doesn't This Example Use the Default Backslash?

PostgreSQL uses backslash as the default LIKE escape character in standard configurations. Yet `\` also interacts with string-literal escaping and `standard_conforming_strings`; learners easily confuse **SQL string literal escaping** with **LIKE pattern escaping**.

Using an explicit `ESCAPE '!'` makes the distinction clear:

```sql
WHERE product_name LIKE '%100!%%' ESCAPE '!'
```

If you pick another escape character or intentionally allow user wildcards, keep a consistent rule across the application.

---

## 8. ILIKE: Case-Insensitive Search

`ILIKE` is a PostgreSQL operator supporting LIKE-style pattern matching, **case-insensitively according to the active language/collation rules**.

Example:

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name ILIKE 'postgresql%'
ORDER BY sku;
```

In the sample data, names starting with PostgreSQL in different cases all match:

| SKU | Name |
| --- | --- |
| `BOOK-PG-01` | PostgreSQL Basics |
| `BOOK-PG-04` | postgresql in practice |
| `BOOK-PG-05` | POSTGRESQL in depth |

With `LIKE 'postgresql%'` in a typical case-sensitive context, only the lowercase `postgresql` prefix matches.

### 8.1. ILIKE Still Uses % and _

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name ILIKE '%sql%'
ORDER BY sku;
```

The pattern `'%sql%'` searches for the substring `sql` case-insensitively, matching all variants containing SQL in their name.

Similarly:

```sql
SELECT sku
FROM query_filter_lab.products
WHERE sku ILIKE 'pen!_%' ESCAPE '!';
```

matches the literal prefix `PEN_` regardless of case per `ILIKE` rules.

### 8.2. ILIKE Is Not Accent-Insensitive Search

Case-insensitivity **does not mean** stripping Vietnamese diacritics or folding all Unicode variants together.

For example:

- `'Bút'` and `'bút'` match under `ILIKE` in an appropriate collation.
- `'Bút'` and `'But'` **are not automatically treated as equal by `ILIKE`**.

If an application needs accent-insensitive search or Unicode variant matching, you may need text normalization, an extension like `unaccent`, or a dedicated search index. Normalization must stay consistent across stored data, queries, and language rules; `ILIKE` alone does not solve natural-language search.

### 8.3. LIKE vs. ILIKE

| Criterion | LIKE | ILIKE |
| --- | --- | --- |
| Purpose | Pattern matching strings | Case-insensitive pattern matching per locale |
| `%` and `_` | Yes | Yes |
| `ESCAPE` | Yes | Yes |
| Prefix/suffix/substring search | Yes, via wildcard placement | Yes |
| Case-sensitive | Usually yes | Usually no |
| Diacritic stripping | Not built in | Not built in |
| PostgreSQL syntax | Standard-aligned | PostgreSQL-specific |
| Performance with leading `%` | Hard to use standard prefix B-tree | Similar; typically requires dedicated index design |

### 8.4. NOT LIKE and NOT ILIKE

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name NOT ILIKE '%postgresql%'
ORDER BY sku;
```

This keeps names that **do not match** `'%postgresql%'`, provided the value produces a determinate comparison.

If `product_name IS NULL`, `NOT ILIKE` does not assume it "doesn't contain the word"—the comparison evaluates to UNKNOWN. If missing values should be included:

```sql
-- General form if the name column allows NULL.
WHERE product_name IS NULL
   OR product_name NOT ILIKE '%postgresql%'
```

In the lab table, `product_name` is `NOT NULL`, so the extra branch is unnecessary.

---

## 9. Combining AND, OR, and NOT

When a filter has multiple criteria, combine them with logical operators.

| Operator | Meaning |
| --- | --- |
| `AND` | All joined conditions must hold |
| `OR` | At least one condition must hold |
| `NOT` | Inverts truth value, though UNKNOWN stays UNKNOWN |

### 9.1. AND: Satisfying Multiple Conditions Simultaneously

Retrieve `ACTIVE` `BOOK` products priced up to 300000:

```sql
SELECT sku, product_name, category, price, status
FROM query_filter_lab.products
WHERE category = 'BOOK'
  AND status = 'ACTIVE'
  AND price <= 300000
ORDER BY price, sku;
```

Matching SKUs in the lab: `BOOK-PG-01`, `BOOK-SQL-02`, and `BOOK-PG-04`. `BOOK-JAVA-03` is excluded because it is `DRAFT`; `BOOK-PG-05` is excluded because its price is 500000.

### 9.2. OR: Only One Condition Needs to Hold

```sql
SELECT sku, category
FROM query_filter_lab.products
WHERE category = 'BOOK'
   OR category = 'GIFT'
ORDER BY sku;
```

When comparing the same column against multiple values for equality, `category IN ('BOOK','GIFT')` is usually more concise.

However, `OR` is required when conditions involve different columns or different operators:

```sql
SELECT sku, status, price
FROM query_filter_lab.products
WHERE status = 'ARCHIVED'
   OR price < 10000
ORDER BY sku;
```

This keeps `KB-MECH-01` (because it is `ARCHIVED`) and `PEN_BLUE_03` (because its price is 8000).

### 9.3. Parentheses Determine Filter Meaning

Suppose the requirement is:

> Retrieve only `ACTIVE` products that are either `BOOK` **or** priced under 20000.

Correct:

```sql
SELECT sku, category, status, price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND (
      category = 'BOOK'
      OR price < 20000
  )
ORDER BY sku;
```

Without parentheses:

```sql
SELECT sku, category, status, price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND category = 'BOOK'
  OR price < 20000
ORDER BY sku;
```

SQL gives `AND` higher precedence than `OR`, so the unparenthesized version parses as:

```sql
WHERE (status = 'ACTIVE' AND category = 'BOOK')
   OR price < 20000
```

Any product priced under 20000 passes the second branch, **even if it is not ACTIVE**.

In the sample dataset, all products under 20000 happen to be `ACTIVE`, so both queries appear to return the same rows right now. That is coincidence, not logical equivalence. As soon as a `DRAFT` product priced at 5000 is added, the unparenthesized query will wrongly include it.

**Good habit:** whenever mixing `AND` and `OR`, always use parentheses to express business intent.

### 9.4. Logical Operator Precedence

In standard logical expressions:

1. `NOT` has highest precedence.
2. `AND` comes next.
3. `OR` has lowest precedence.

Example:

```sql
WHERE NOT (status = 'ARCHIVED' OR price < 10000)
```

differs from:

```sql
WHERE NOT status = 'ARCHIVED'
   OR price < 10000
```

The first rejects both `ARCHIVED` and prices under 10000. The second keeps any row under 10000 even if other conditions fail, because of the `OR` branch.

With `BETWEEN lower AND upper`, the `AND` inside `BETWEEN` is part of the range expression, not a separate logical `AND` between filters. While PostgreSQL parses it unambiguously, adding parentheses around complex predicates helps human readers avoid mistakes.

### 9.5. NOT and Parentheses

To exclude all `BOOK` or `GIFT` products:

```sql
SELECT sku, category
FROM query_filter_lab.products
WHERE NOT (category IN ('BOOK', 'GIFT'))
ORDER BY sku;
```

Equivalent to `category NOT IN ('BOOK','GIFT')` on non-NULL data. When NULLs are possible, every negated expression still follows three-valued logic as covered earlier.

To exclude only products that are both `ACTIVE` and `BOOK`:

```sql
WHERE NOT (
    status = 'ACTIVE'
    AND category = 'BOOK'
)
```

In three-valued logic, this is equivalent to:

```sql
WHERE status <> 'ACTIVE'
   OR category <> 'BOOK'
```

Do not rewrite it as `status <> 'ACTIVE' AND category <> 'BOOK'`, which excludes far more rows.

---

## 10. Three-Valued Logic When Combining Conditions

Here is the essential compact table:

| A | B | `A AND B` | `A OR B` |
| --- | --- | --- | --- |
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | NULL | NULL | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | NULL | FALSE | NULL |
| NULL | NULL | NULL | NULL |

For `NOT`:

| A | `NOT A` |
| --- | --- |
| TRUE | FALSE |
| FALSE | TRUE |
| NULL | NULL |

This explains why:

```sql
WHERE stock_quantity > 0
```

drops rows with NULL stock, and:

```sql
WHERE NOT (stock_quantity > 0)
```

**also drops** rows with NULL stock. On those rows, the inner predicate is UNKNOWN, and `NOT` does not turn UNKNOWN into TRUE.

### 10.1. IS NULL and IS NOT NULL

To find products with unknown stock:

```sql
SELECT sku, stock_quantity
FROM query_filter_lab.products
WHERE stock_quantity IS NULL
ORDER BY sku;
```

In the sample data, `BOOK-JAVA-03` and `BOOK-PG-05` have NULL stock.

To find products with zero stock:

```sql
SELECT sku, stock_quantity
FROM query_filter_lab.products
WHERE stock_quantity = 0
ORDER BY sku;
```

In the sample data, `BOOK-PG-04` and `PEN-RED-02` have stock = 0.

These two queries find **two distinct states**:

- `0`: known to be out of stock per data convention.
- `NULL`: stock not yet recorded or unknown per the model.

### 10.2. Combining OR to Include NULL Intentionally

If the business wants "products in stock or whose stock has not been updated yet":

```sql
SELECT sku, stock_quantity
FROM query_filter_lab.products
WHERE stock_quantity > 0
   OR stock_quantity IS NULL
ORDER BY sku;
```

Products with stock = 0 are excluded. Products with NULL stock are kept because `IS NULL` evaluates to TRUE.

If the business only wants "definitely in stock", use:

```sql
WHERE stock_quantity > 0
```

PostgreSQL has no built-in rule saying "NULL means 0." Using `COALESCE(stock_quantity, 0)` to treat NULL as out of stock must be an explicit business decision.

### 10.3. IS DISTINCT FROM: Defined Comparisons with NULL

PostgreSQL supports:

```sql
a IS DISTINCT FROM b
```

This comparison always returns TRUE or FALSE, even when an operand is NULL. Two NULLs are treated as not distinct.

Example:

```sql
SELECT
    NULL::INTEGER IS DISTINCT FROM 0 AS null_vs_zero,
    NULL::INTEGER IS DISTINCT FROM NULL::INTEGER AS two_nulls,
    5 IS DISTINCT FROM 0 AS five_vs_zero;
```

Results respectively: TRUE, FALSE, TRUE.

This is a helpful tool for NULL-safe comparisons, though not a blind replacement for every `NOT IN` list. Always decide whether "missing data" counts as a different value.

---

## 11. Combining IN, BETWEEN, ILIKE, and Other Conditions

### 11.1. A Complete Product Filter Query

Suppose the requirement is:

> Retrieve active products in BOOK or ACCESSORY, priced between 100000 and 400000, sorted by ascending price.

```sql
SELECT sku, product_name, category, price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND category IN ('BOOK', 'ACCESSORY')
  AND price BETWEEN 100000 AND 400000
ORDER BY price ASC, sku ASC;
```

Result on the sample data:

| SKU | Category | Price |
| --- | --- | ---: |
| `BOOK-PG-01` | BOOK | 120000 |
| `BOOK-SQL-02` | BOOK | 260000 |
| `BOOK-PG-04` | BOOK | 300000 |
| `MOUSE-WL-01` | ACCESSORY | 350000 |

Rows such as `BOOK-JAVA-03` (`DRAFT`), `BOOK-PG-05` (price 500000), and `KB-MECH-01` (`ARCHIVED`) are excluded by their respective conditions.

### 11.2. Adding a Name Condition with ILIKE

Suppose the requirement restricts to `ACTIVE` products whose names start with `PostgreSQL` or `SQL`, case-insensitively:

```sql
SELECT sku, product_name, status
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND (
      product_name ILIKE 'postgresql%'
      OR product_name ILIKE 'sql%'
  )
ORDER BY sku;
```

Result includes `BOOK-PG-01`, `BOOK-PG-04`, `BOOK-PG-05`, and `BOOK-SQL-02`.

Do not write:

```sql
WHERE status = 'ACTIVE'
  AND product_name ILIKE 'postgresql%'
  OR product_name ILIKE 'sql%'
```

when the intent requires **all products to be ACTIVE**, because the trailing `SQL` branch will bypass the `ACTIVE` filter. Use parentheses to prevent bugs as data evolves.

### 11.3. Filter with a NULL Condition

Suppose the requirement is:

> ACTIVE, in BOOK or STATIONERY, priced from 10000 to 300000, with stock greater than 0 **or unknown**.

```sql
SELECT
    sku, category, status, price, stock_quantity
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND category IN ('BOOK', 'STATIONERY')
  AND price BETWEEN 10000 AND 300000
  AND (
      stock_quantity > 0
      OR stock_quantity IS NULL
  )
ORDER BY sku;
```

On the sample data, the result contains `BOOK-PG-01`, `BOOK-SQL-02`, and `PEN-BLUE-01`. Rows with 0 stock are excluded; `BOOK-PG-05` has NULL stock but exceeds 300000, so it is also excluded.

Removing parentheses around the stock check changes the meaning: `OR stock_quantity IS NULL` would let through rows failing status, category, or price.

### 11.4. OR Queries with Distinct Business Groups

Suppose the requirement is:

- Group 1: all `ACTIVE` `BOOK` products;
- Or Group 2: `DRAFT` products priced under 50000.

```sql
SELECT sku, category, status, price
FROM query_filter_lab.products
WHERE (
    category = 'BOOK'
    AND status = 'ACTIVE'
)
OR (
    status = 'DRAFT'
    AND price < 50000
)
ORDER BY sku;
```

In the lab, Group 2 includes `NOTE-A5-01` (`DRAFT`, price 45000). `BOOK-JAVA-03` is `DRAFT` but priced at 200000, so it does not match Group 2.

This clearly expresses **two independent business cases**, much cleaner than mixing a long unparenthesized chain of AND/OR.

### 11.5. How Can Multiple LIKE Patterns Be Written?

To match names starting with either of two prefixes:

```sql
WHERE product_name ILIKE 'postgresql%'
   OR product_name ILIKE 'sql%'
```

In PostgreSQL, pattern operators can also be combined with `ANY` over an array:

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name ILIKE ANY (
    ARRAY['postgresql%', 'sql%']::TEXT[]
)
ORDER BY sku;
```

This expresses a set of patterns cleanly when the number of patterns varies. However, `ILIKE ANY` still interprets wildcards inside every array element; do not treat elements as literal strings if users input unescaped `%` or `_`.

---

## 12. Is Filtering in WHERE the Same as Filtering in HAVING?

In basic aggregate queries, `WHERE` filters **input rows** before grouping, while `HAVING` filters **result groups** after aggregation.

Example:

```sql
SELECT
    category,
    COUNT(*) AS active_count,
    MIN(price) AS min_price,
    MAX(price) AS max_price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND category IN ('BOOK', 'ACCESSORY')
GROUP BY category
HAVING COUNT(*) >= 2
ORDER BY category;
```

Explanation:

1. `WHERE` keeps only `ACTIVE` products in `BOOK` or `ACCESSORY`.
2. `GROUP BY category` groups remaining rows by category.
3. `HAVING COUNT(*) >= 2` keeps groups with at least two products.
4. `ORDER BY` sorts the resulting groups.

Never put `COUNT(*) >= 2` directly in `WHERE` of the same `SELECT`, because `WHERE` cannot evaluate group aggregates.

As a useful note, `IN`, `BETWEEN`, and `LIKE` can also appear in `HAVING` when expressions and group semantics fit, though this lesson focuses on row filtering with `WHERE`.

---

## 13. SQL Safety When Filter Inputs Come from Users

A search API typically receives query parameters:

```text
?categories=BOOK,ACCESSORY
&minPrice=100000
&maxPrice=400000
&name=postgresql
```

Never concatenate those inputs directly into a SQL string. Risky example:

```text
sql = "SELECT ... WHERE product_name ILIKE '%" + userInput + "%'";
```

If `userInput` contains quotes or SQL tokens, it can break the query or open a SQL injection vulnerability.

Use **parameterized queries** via your driver. Also handle `LIKE`/`ILIKE` patterns according to user intent.

### 13.1. Parameter Binding Does Not Automatically Disable Wildcards

Suppose the application builds:

```sql
WHERE product_name ILIKE $1
```

and passes `$1 = '%sql%'`. That is a valid pattern parameter. If a user enters `%` and the app embeds it in the pattern, `%` still acts as "match any string."

This is **not SQL injection**, because the data is bound. Still, if the business intends to search for a **literal string**, unescaped wildcards can broaden the filter unexpectedly and make queries expensive.

Two distinct requirements:

- **Allow users to write patterns:** `%` and `_` retain wildcard meaning.
- **Search literally for what the user typed:** escape wildcards before wrapping with application-added `%` delimiters.

### 13.2. Java JDBC Example for Literal Substring Search

Java code example (independent of the lab table setup):

```java
import java.sql.PreparedStatement;
import java.sql.ResultSet;

// User types a search string meant literally, not as a LIKE pattern.
String input = userInput;

// Use ! as the escape character for ILIKE.
String escaped = input
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");

// Only the outer % characters are intentional wildcards added by the app.
String pattern = "%" + escaped + "%";

String sql = """
    SELECT sku, product_name
    FROM query_filter_lab.products
    WHERE product_name ILIKE ? ESCAPE '!'
    ORDER BY sku
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, pattern);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            String sku = rs.getString("sku");
            String name = rs.getString("product_name");
            // Process application results.
        }
    }
}
```

Goals:

- SQL structure and user data are **separated** via `PreparedStatement`.
- `%` and `_` typed by the user are escaped as literal characters.
- Outer `%` delimiters added by the app perform substring matching.

If you **want to let users enter wildcards**, skip escaping them as shown above, but enforce pattern length limits, pagination, query timeouts, and appropriate load protection.

### 13.3. User-Supplied IN Lists

Do not concatenate:

```text
"WHERE category IN (" + rawCategoryList + ")"
```

because input can contain syntax-breaking characters and make query logic unsafe.

Common safe patterns:

- Generate the right number of placeholders for the list size and bind each value via the driver.
- Use a PostgreSQL array with `= ANY($1::TEXT[])` when supported by your driver.
- Validate maximum list length and allowed category values.
- Define empty-list semantics explicitly (no categories → zero results, or skip filter?).
- Never let clients supply column names, operators, or SQL fragments without an allowlist.

Data values can be bound; **table/column identifiers** must be selected from an allowlist rather than bound as data literals.

### 13.4. Price Range Parameters

SQL template:

```sql
SELECT sku, price
FROM query_filter_lab.products
WHERE price >= $1
  AND price <= $2
ORDER BY price;
```

When using a prepared statement, `$1` and `$2` are bound with a compatible decimal type, such as Java `BigDecimal`. Before executing, the application should:

1. Validate that min and max are valid numbers.
2. Ensure min is not greater than max per the API contract.
3. Account for currency and units when filtering prices.
4. Avoid `double` for monetary values when exact decimal arithmetic is needed.

---

## 14. Performance and Indexes for Filter Conditions

Writing a logically correct `WHERE` clause is not enough on tables with millions of rows. A predicate may be highly selective or force PostgreSQL to inspect many rows.

### 14.1. IN and BETWEEN Often Have Opportunities to Use B-Trees

Queries such as:

```sql
WHERE category IN ('BOOK', 'GIFT')
```

and:

```sql
WHERE price BETWEEN 100000 AND 300000
```

are strong candidates for B-tree indexes when data distribution, selectivity, and statistics favor them.

On the lab table you could create:

```sql
CREATE INDEX idx_products_category
ON query_filter_lab.products (category);

CREATE INDEX idx_products_price
ON query_filter_lab.products (price);

CREATE INDEX idx_products_status_category_price
ON query_filter_lab.products (status, category, price);
```

A composite index on `(status, category, price)` can fit queries filtering `status` with `=`, `category` with `IN`, and `price` by range. Actual effectiveness depends on data distribution and planner choices.

**There is no rule saying "having WHERE guarantees an index scan."** On the 13-row lab table, PostgreSQL will likely pick a sequential scan because it is cheaper than using an index. That is optimal planner behavior, not a broken index.

### 14.2. Prefix LIKE vs. Substring LIKE

Compare:

```sql
WHERE sku LIKE 'BOOK-%'
```

with:

```sql
WHERE sku LIKE '%BOOK%'
```

The first pattern has a **fixed prefix**. Under compatible collation and operator-class settings, PostgreSQL can use a B-tree index to scan the prefix range.

The second starts with `%`, meaning anything can precede `BOOK`. A standard B-tree cannot narrow that down to a simple prefix range.

For text columns with collations that do not natively support B-tree prefix pattern optimization, consider the `text_pattern_ops` operator class:

```sql
CREATE INDEX idx_products_sku_pattern
ON query_filter_lab.products (sku text_pattern_ops);
```

This is an example index for prefix patterns on `sku TEXT`. It does not magically accelerate `ILIKE '%keyword%'`, nor does it replace the existing `UNIQUE` index/constraint on `sku`.

### 14.3. ILIKE and the LOWER Function

An alternative way to write case-insensitive prefix matching is:

```sql
WHERE lower(product_name) LIKE 'postgresql%'
```

In certain setups, you can build an expression index on `lower(product_name)` for prefix patterns. However, a plain B-tree index on `product_name` alone cannot generally be used effectively if queries always apply `lower()` to the column.

Consider:

- Actual selectivity.
- Collation and string comparison rules.
- Whether the pattern has a fixed prefix or starts with `%`.
- Whether the planner actually uses the index.
- Index maintenance overhead on INSERT/UPDATE.

Do not apply `LOWER` indiscriminately to every search if requirements involve Vietnamese diacritics, Unicode normalization, or sophisticated linguistic sorting.

### 14.4. pg_trgm for Substring Search

PostgreSQL provides the `pg_trgm` extension for trigram-based indexing, helpful for many `LIKE`/`ILIKE` patterns—especially substring searches on sufficiently large datasets.

**This section is optional advanced material; you do not need to run it to complete the basic lab.** On a test database with permission to install extensions:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_products_name_trgm
ON query_filter_lab.products
USING GIN (product_name gin_trgm_ops);
```

Then queries like:

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name ILIKE '%postgresql%';
```

can be considered by the planner for a trigram index scan when data size and statistics justify it.

Limitations:

- Very short patterns or patterns yielding few useful trigrams may filter poorly.
- Indexes increase storage footprint and write/update overhead.
- Queries on very small tables may still choose sequential scans.
- Extension availability depends on privileges and database management policies.
- Trigram indexes do not replace natural-language full-text search or accent-insensitive matching on their own.

Never run `CREATE EXTENSION` on production without proper authorization and an operational plan.

### 14.5. Inspecting Plans with EXPLAIN

In the lab, you can run:

```sql
EXPLAIN
SELECT sku, price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND category IN ('BOOK', 'ACCESSORY')
  AND price BETWEEN 100000 AND 400000
ORDER BY price;
```

To inspect actual execution time and buffer usage for a **`SELECT`**:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name ILIKE '%postgresql%';
```

`EXPLAIN ANALYZE` **actually executes the query**. Never run it casually on `INSERT`/`UPDATE`/`DELETE` in production because it mutates data. Here we only use `SELECT` for observation.

Distinguish timings on a 13-row lab table from a multi-million-row table; the planner chooses different plans based on table size and statistics.

### 14.6. OR Conditions and Indexes

A query:

```sql
WHERE category = 'BOOK'
   OR price < 20000
```

can use different execution strategies: table scans, combined bitmap index scans, or other plans depending on data. You cannot claim `OR` is always slow or always disables indexes.

Only create indexes once you know the important queries, selectivity, write frequency, and real plans. Too many indexes slow down `INSERT`/`UPDATE` operations.

---

## 15. Common Confusions in PostgreSQL

### 15.1. IN Is Not ILIKE ANY

```sql
WHERE category IN ('BOOK', 'GIFT')
```

tests exact equality against a set of values.

```sql
WHERE product_name ILIKE ANY (
    ARRAY['post%', 'sql%']::TEXT[]
)
```

matches against a **set of patterns**.

If the user supplies exact category names, use `IN` or `= ANY`. If the list contains allowed text patterns, `ILIKE ANY` can fit provided you handle wildcards properly.

### 15.2. BETWEEN Includes Endpoints, While Half-Open Fits Timestamps Better

```sql
price BETWEEN 100 AND 200
```

includes both 100 and 200.

```sql
created_at >= start_time
AND created_at < end_time
```

fits intervals starting at one boundary and ending right before the next boundary.

Never replace `< end_time` with `<= end_time` if `end_time` is midnight of the following day or month.

### 15.3. LIKE Is Not Regex

In `LIKE`, `%` and `_` are the main wildcards. Regex syntax like `.*`, `[0-9]`, or `^...$` does not carry regex meaning inside `LIKE` patterns.

PostgreSQL also provides regex operators (`~`, `~*`) and `SIMILAR TO`, which are **separate matching engines**. Do not mix their syntax with `LIKE`.

For instance, if a code must end with a single digit, `LIKE`'s `_` only matches any single character—it does not verify that the character is a digit. For complex format rules, regex or appropriate constraints express the rule accurately.

### 15.4. ILIKE Is Not a Full-Text Search Engine

`ILIKE '%postgresql%'` is handy for substring search. It does not automatically:

- Tokenize words linguistically.
- Match synonyms.
- Handle Vietnamese diacritics as desired.
- Rank documents by relevance.
- Support typo-tolerant fuzzy search like a full search engine.

For large articles or document collections, you may need PostgreSQL full-text search, `pg_trgm`, normalization, or a dedicated search engine depending on requirements.

### 15.5. NULL Does Not Equal an Empty String

```sql
WHERE product_name = ''
```

finds empty strings, **not NULL**.

```sql
WHERE product_name IS NULL
```

finds NULL values.

Similarly:

```sql
WHERE product_name LIKE '%'
```

matches all non-NULL strings (including empty strings), but does not match NULL in `WHERE`.

### 15.6. Never Test NULL with = NULL

Do not write:

```sql
WHERE discount_pct = NULL
```

because any standard comparison with NULL evaluates to UNKNOWN, not a concrete SQL match. Use:

```sql
WHERE discount_pct IS NULL
```

and `IS NOT NULL` for the opposite.

### 15.7. Literals and Data Types

If `price` is `NUMERIC`, bind numeric values. If `created_at` is `TIMESTAMPTZ`, bind timestamps with proper time zone/instant semantics.

Implicit type conversions across text, timestamp, numeric, and literals work in many queries, yet **never rely on ambiguous conversions** involving locale formats or time zones.

For monetary amounts, never parse through binary floating-point types when exact decimal accuracy is required.

---

## 16. Quick SQL Verification Queries

Run these against the lab table to observe the differences firsthand:

### 16.1. IN and NOT IN

```sql
SELECT sku
FROM query_filter_lab.products
WHERE category IN ('BOOK', 'GIFT')
ORDER BY sku;

SELECT sku
FROM query_filter_lab.products
WHERE status NOT IN ('DRAFT', 'ARCHIVED')
ORDER BY sku;
```

### 16.2. BETWEEN

```sql
SELECT sku, price
FROM query_filter_lab.products
WHERE price BETWEEN 100000 AND 300000
ORDER BY price, sku;

SELECT sku, price
FROM query_filter_lab.products
WHERE price NOT BETWEEN 100000 AND 300000
ORDER BY price, sku;
```

### 16.3. LIKE vs. ILIKE

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name LIKE 'postgresql%'
ORDER BY sku;

SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name ILIKE 'postgresql%'
ORDER BY sku;
```

### 16.4. ESCAPE

```sql
SELECT sku
FROM query_filter_lab.products
WHERE sku LIKE 'PEN!_%' ESCAPE '!';

SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name LIKE '%100!%%' ESCAPE '!';
```

### 16.5. AND, OR, and Parentheses

```sql
SELECT sku, category, status, price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND (
      category = 'BOOK'
      OR price < 20000
  )
ORDER BY sku;
```

After running that, try inserting a `DRAFT` product priced at 5000 **inside a lab transaction** and compare with the unparenthesized version:

```sql
BEGIN;

INSERT INTO query_filter_lab.products (
    sku, product_name, category, price, status,
    stock_quantity, discount_pct, created_at
)
VALUES (
    'TMP-DRAFT-01', 'Cheap test item', 'GIFT',
    5000, 'DRAFT', 0, NULL,
    '2026-02-15 00:00:00+00'
);

SELECT sku
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND (category = 'BOOK' OR price < 20000)
ORDER BY sku;

SELECT sku
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND category = 'BOOK'
  OR price < 20000
ORDER BY sku;

ROLLBACK;
```

Inside the lab transaction, the **unparenthesized** query picks up `TMP-DRAFT-01` because of its low price, whereas the **parenthesized** query excludes it because its status is not `ACTIVE`. `ROLLBACK` restores the table to its original state after the test.

---

## 17. Self-Practice Exercises

### Exercise 1 — Filtering a Set of Categories

Write a SELECT returning `sku, product_name, category` for products in `STATIONERY` or `GIFT`. Use `IN`, then write the equivalent using `OR`.

Question: if the application passes an empty category list, how would you handle it without generating invalid `IN ()` SQL syntax?

### Exercise 2 — Clear Price Boundaries

Find products priced from 25000 to 300000, **inclusive of both endpoints**.

Compare the results of:

```sql
price BETWEEN 25000 AND 300000
```

and:

```sql
price >= 25000 AND price <= 300000
```

Why is `BOOK-PG-04` at price 300000 retained?

### Exercise 3 — NOT IN with NULL

Predict:

```sql
SELECT sku, discount_pct
FROM query_filter_lab.products
WHERE discount_pct NOT IN (0, 10, NULL)
ORDER BY sku;
```

Why are zero rows returned on the lab data? Write a query finding known discounts other than 0 and 10. Then adjust it to **include NULL discounts** if business rules require it.

### Exercise 4 — Searching with LIKE

Write patterns to find:

1. SKUs starting with `BOOK-`.
2. SKUs ending with `-01`.
3. Names containing `SQL` with exact casing.
4. Names containing `SQL` case-insensitively.
5. SKUs starting with the literal characters `PEN_`.

Explain why case 5 requires `ESCAPE`.

### Exercise 5 — Literal Percent Sign

Find products whose name contains the literal string `100%` using `LIKE`. Do not let the `%` inside `100%` act as a wildcard.

Hint: use `ESCAPE '!'`, distinguishing `!%` from `%`.

### Exercise 6 — Filtering by Timestamp

Write a query retrieving all products created in March 2026 **UTC**, without missing timestamps with fractional seconds.

Explain why:

```sql
created_at BETWEEN '2026-03-01' AND '2026-03-31'
```

is not a good way to capture the entire final day of the month with `TIMESTAMPTZ`.

### Exercise 7 — AND/OR Without Parentheses

Requirement:

> Products that are ACTIVE and (BOOK or priced under 20000).

Write the query with parentheses. Then write it without parentheses and explain how a `DRAFT` product priced at 5000 could slip into the second query's results.

### Exercise 8 — Nullable Stock Conditions

Find:

1. Products whose stock is **definitely greater than 0**.
2. Products whose stock equals 0.
3. Products with unknown stock (NULL).
4. Products with stock greater than 0 **or NULL**.

Why is `NOT (stock_quantity > 0)` not equivalent to "out of stock or unknown stock"?

### Exercise 9 — Multiple Mixed Conditions

Write a query returning SKU and price for products that are:

- ACTIVE.
- Category BOOK or ACCESSORY.
- Priced from 100000 to 400000.
- Name contains `SQL`, case-insensitively.

Sort by ascending price, then ascending SKU. Count the rows and explain why other products were excluded.

### Exercise 10 — IN Over Two Columns

Write a query returning only pairs:

- `category = BOOK` and `status = ACTIVE`.
- `category = GIFT` and `status = DRAFT`.

Compare using:

```sql
(category, status) IN (
    ('BOOK', 'ACTIVE'),
    ('GIFT', 'DRAFT')
)
```

against splitting into:

```sql
category IN ('BOOK','GIFT')
AND status IN ('ACTIVE','DRAFT')
```

Why does the second version allow unwanted extra combinations?

### Exercise 11 — User-Supplied Search Strings

An application receives the keyword `100%` to search literally inside product names.

Explain:

1. Why `PreparedStatement` should be used instead of SQL string concatenation.
2. Why parameter binding **does not automatically strip wildcard meaning from `%`**.
3. How to escape `%`, `_`, and the application's chosen escape character.
4. How to add outer `%` delimiters when performing substring search.

### Exercise 12 — Choosing Indexes for a Workload

A large table has three common queries:

1. `WHERE category IN (...) AND price BETWEEN ...`.
2. `WHERE sku LIKE 'BOOK-%'`.
3. `WHERE product_name ILIKE '%postgresql%'`.

Suggest B-tree/composite indexes, pattern operator classes, or trigram indexes worth considering. Explain why you should never promise the planner will definitely use an index before inspecting `EXPLAIN` on real data.

---

## 18. Checklist for Writing Correct, Maintainable Filters

| Question | What to Verify |
| --- | --- |
| Is the filter an exact set of values? | Use `IN` or `= ANY`, not `LIKE`. |
| Could NULL appear in the list/subquery? | Be especially careful with `NOT IN`. |
| Is the filtered column nullable? | Use `IS NULL`/`IS NOT NULL` when needed. |
| Should the numeric range include both endpoints? | `BETWEEN` includes both; validate min/max. |
| Does the time range include hours/minutes/seconds? | Prefer half-open intervals `>= start AND < end`. |
| What time zone defines the range? | Choose explicit UTC or regional time zone boundaries. |
| Is the search prefix, suffix, or substring? | Place `%` in the right position in the pattern. |
| Are there literal `%` or `_` characters in keywords? | Use `ESCAPE` and escape patterns properly. |
| Does search need to be case-insensitive? | Consider `ILIKE`. |
| Does search need Unicode accent-insensitivity? | `ILIKE` does not handle it; build normalization/search logic. |
| Are `AND` and `OR` mixed? | Use parentheses to separate business groups. |
| Is `NOT` applied to a nullable condition? | UNKNOWN stays UNKNOWN; NULLs are not included automatically. |
| Do filter inputs come from a request? | Bind parameters, allowlist identifiers, limit lengths/list sizes. |
| Is pagination used? | Choose a deterministic `ORDER BY` with `LIMIT/OFFSET` or keyset pagination. |
| Is a query slow? | Inspect `EXPLAIN (ANALYZE, BUFFERS)` on a test `SELECT`. |
| Should a new index be added? | Weigh selectivity, collation, pattern type, and write overhead. |
| Have edge cases been tested? | Values at min/max, NULL, empty string, casing, `%`/`_`, and month boundaries. |

## Conclusion

`IN`, `BETWEEN`, `LIKE`, and `ILIKE` are foundational tools for filtering PostgreSQL data:

- **`IN`** expresses membership in an exact set; especially watch out for `NOT IN` when lists or subqueries contain `NULL`.
- **`BETWEEN`** includes both endpoints; when filtering `TIMESTAMP/TIMESTAMPTZ` by day or month, prefer **half-open** intervals to avoid missing end-of-period timestamps.
- **`LIKE`** matches strings against patterns with `%` and `_`; use `ESCAPE` when searching for those wildcard characters literally.
- **`ILIKE`** enables case-insensitive pattern matching per PostgreSQL rules, though it does not solve accent-insensitive or full-text search on its own.
- **`AND`, `OR`, and `NOT`** must be combined intentionally with parentheses and an understanding of `NULL` logic to avoid wrong results.
- At scale, **indexes and query plans** determine how PostgreSQL executes filters—not just concise SQL syntax.

A good filter must match business intent, handle missing values explicitly, stay safe against user input, and remain observable for performance. Those habits help you build listing pages, reports, and search APIs in PostgreSQL that are accurate, scalable, and easy to maintain.
