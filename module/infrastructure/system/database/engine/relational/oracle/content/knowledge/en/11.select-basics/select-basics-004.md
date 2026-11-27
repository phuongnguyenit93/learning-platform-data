# IN, BETWEEN, LIKE, and Wildcards in Oracle Database

When writing a `SELECT` statement in Oracle Database, the `WHERE` clause decides which rows are kept. Alongside the comparison operators `=`, `<`, `>`, `<=`, and `>=`, three very common conditions are **`IN`**, **`BETWEEN`**, and **`LIKE`**:

- **`IN`** checks whether a value belongs to a set of values or a subquery result.
- **`BETWEEN`** checks whether a value falls within a range **inclusive of both endpoints**.
- **`LIKE`** matches a string against a **pattern**, where `%` and `_` are the two wildcard characters.

Even a short SQL statement can produce unexpected results if you misunderstand `NULL`, datetime range boundaries, wildcards inside product names, or Oracle string comparison rules. This lesson explains the syntax, how to combine conditions, hands-on examples, and guidelines for writing accurate, safe, and maintainable queries.

## 1. Position of Conditions in SELECT

Simple structure:

```sql
SELECT column_1, column_2
FROM   table_name
WHERE  condition
ORDER  BY column_1;
```

`WHERE` accepts a **condition**. A row is kept only when the condition evaluates to **TRUE**. SQL also has the logical states **FALSE** and **UNKNOWN**; comparisons involving `NULL` typically evaluate to UNKNOWN and are excluded by `WHERE`.

Examples translated from natural language:

| Requirement | Condition pattern |
| --- | --- |
| Select products in one of three categories | `category IN ('BOOK', 'TOY', 'FOOD')` |
| Select products priced from 100 to 500 | `price BETWEEN 100 AND 500` |
| Find names starting with "Laptop" | `product_name LIKE 'Laptop%'` |
| Find names containing "USB" | `product_name LIKE '%USB%'` |
| Find codes containing a literal underscore | `sku LIKE '%\_%' ESCAPE '\'` |
| Select the remaining categories | `category NOT IN ('BOOK', 'TOY')` |
| Price outside the range | `price NOT BETWEEN 100 AND 500` |
| Name not matching a pattern | `product_name NOT LIKE 'Laptop%'` |

Values like `'BOOK'` and `'TOY'` are only illustrative category names; actual queries depend on your table.

### 1.1. Sample Data Used Throughout the Lesson

Create the practice table in an authorized schema:

```sql
CREATE TABLE demo_products (
    product_id   NUMBER(10) PRIMARY KEY,
    product_name VARCHAR2(100) NOT NULL,
    category     VARCHAR2(30),
    sku          VARCHAR2(30),
    price        NUMBER(12,2),
    created_at   DATE NOT NULL
);
```

Insert fixed rows so query outputs can be verified consistently:

```sql
INSERT INTO demo_products VALUES (
    1, 'Laptop Pro', 'ELECTRONICS', 'LP_01',
    25000000, TO_DATE('2026-11-14 09:15:00', 'YYYY-MM-DD HH24:MI:SS')
);

INSERT INTO demo_products VALUES (
    2, 'Laptop Air', 'ELECTRONICS', 'LA-02',
    18000000, TO_DATE('2026-11-15 17:30:00', 'YYYY-MM-DD HH24:MI:SS')
);

INSERT INTO demo_products VALUES (
    3, 'Mouse A_100', 'ACCESSORIES', 'MS_100',
    350000, DATE '2026-11-15'
);

INSERT INTO demo_products VALUES (
    4, 'Monitor 27%', 'ELECTRONICS', 'MN-27%',
    6000000, TO_DATE('2026-12-01 12:00:00', 'YYYY-MM-DD HH24:MI:SS')
);

INSERT INTO demo_products VALUES (
    5, 'Cable USB-C', 'ACCESSORIES', 'CB-05',
    190000, DATE '2026-12-05'
);

INSERT INTO demo_products VALUES (
    6, 'Notebook Basic', 'STATIONERY', 'NB-06',
    60000, DATE '2026-12-05'
);

INSERT INTO demo_products VALUES (
    7, 'Keyboard', NULL, 'KB-07',
    1200000, DATE '2026-12-10'
);

INSERT INTO demo_products VALUES (
    8, 'Adaptor 100%', 'ACCESSORIES', 'AD-08',
    NULL, DATE '2026-12-12'
);

INSERT INTO demo_products VALUES (
    9, 'Tablet', 'ELECTRONICS', 'TB-09',
    8500000, DATE '2027-01-01'
);

COMMIT;
```

Key rows to keep in mind:

| ID | Product Name | CATEGORY | PRICE | Notes |
| ---: | --- | --- | ---: | --- |
| 1 | Laptop Pro | ELECTRONICS | 25,000,000 | SKU contains `_` |
| 2 | Laptop Air | ELECTRONICS | 18,000,000 | Created Nov 15 at 17:30 |
| 3 | Mouse A_100 | ACCESSORIES | 350,000 | Name contains `_` |
| 4 | Monitor 27% | ELECTRONICS | 6,000,000 | Name contains `%` |
| 5 | Cable USB-C | ACCESSORIES | 190,000 | Contains "USB" |
| 6 | Notebook Basic | STATIONERY | 60,000 | Stationery category |
| 7 | Keyboard | `NULL` | 1,200,000 | Category unassigned |
| 8 | Adaptor 100% | ACCESSORIES | `NULL` | Price missing |
| 9 | Tablet | ELECTRONICS | 8,500,000 | Created in 2027 |

**Note:** monetary values here use `NUMBER(12,2)` for decimal practice. Oracle does not store thousands separators inside numeric values; separators in the table are for display only.

## 2. IN: Checking Set Membership

### 2.1. Syntax and Semantics

Basic syntax:

```sql
expression IN (value_1, value_2, value_3, ...)
```

For non-`NULL`, type-compatible comparison values, the expression:

```sql
category IN ('ELECTRONICS', 'ACCESSORIES')
```

can be read as:

```sql
category = 'ELECTRONICS'
OR category = 'ACCESSORIES'
```

Writing `IN` is usually more readable than a long chain of `OR` comparisons.

Example:

```sql
SELECT product_id, product_name, category
FROM   demo_products
WHERE  category IN ('ELECTRONICS', 'ACCESSORIES')
ORDER  BY product_id;
```

The result on the sample table includes IDs **1, 2, 3, 4, 5, 8, 9**. Product 6 belongs to `STATIONERY`, and product 7 has `CATEGORY=NULL`, so neither is selected.

### 2.2. IN with Numbers

```sql
SELECT product_id, product_name, price
FROM   demo_products
WHERE  product_id IN (1, 3, 5, 9)
ORDER  BY product_id;
```

The result consists of products with IDs **1, 3, 5, 9**.

`IN` does not require the list elements to be sorted. Writing `IN (9, 1, 5, 3)` does not cause results to appear in the order `9, 1, 5, 3`. **Only `ORDER BY` determines the guaranteed display order in a SELECT statement.**

### 2.3. IN Is Not a Range Check

The condition:

```sql
WHERE product_id IN (1, 3, 5)
```

matches only the three exact values **1**, **3**, **5**, and does not automatically include **2** or **4**. To find all contiguous IDs from 1 to 5, use:

```sql
WHERE product_id BETWEEN 1 AND 5
```

or the equivalent condition:

```sql
WHERE product_id >= 1
  AND product_id <= 5
```

Similarly, `IN ('A', 'B')` does not mean every string alphabetically between A and B; it checks only the two listed values.

### 2.4. Elements Must Be Data-Type Compatible

Use the same data type as the compared expression:

```sql
-- PRODUCT_ID is NUMBER.
SELECT product_id
FROM   demo_products
WHERE  product_id IN (1, 2, 3);
```

Avoid writing a list of numbers as strings and relying on **implicit conversion**:

```sql
-- Not recommended: comparing NUMBER with character strings.
SELECT product_id
FROM   demo_products
WHERE  product_id IN ('1', '2', '3');
```

Oracle has implicit type conversion, but it can raise `ORA-01722: invalid number` or yield configuration-dependent behavior if inputs are invalid. The best practice is passing values with the proper numeric type.

### 2.5. IN with a Subquery

`IN` does not require a list of literals. It can check values against the result of another `SELECT`.

Suppose there is a table listing promotional products:

```sql
CREATE TABLE demo_promo_products (
    product_id NUMBER(10)
);

INSERT INTO demo_promo_products VALUES (1);
INSERT INTO demo_promo_products VALUES (3);
COMMIT;
```

Query:

```sql
SELECT p.product_id, p.product_name
FROM   demo_products p
WHERE  p.product_id IN (
         SELECT x.product_id
         FROM   demo_promo_products x
       )
ORDER  BY p.product_id;
```

The result includes products **1** and **3**. Oracle checks whether `P.PRODUCT_ID` matches a value returned by the subquery.

This pattern is commonly used when the filter list lives in a relational table, such as a status table, user-group table, permissions table, or business-processing result table.

### 2.6. IN with Multiple Columns (Tuple Comparison)

Oracle allows comparing a group of expressions against matching value tuples:

```sql
SELECT product_id, product_name, category, price
FROM   demo_products
WHERE  (category, price) IN (
         ('ELECTRONICS', 25000000),
         ('ACCESSORIES', 350000)
       )
ORDER BY product_id;
```

The query finds only the matching `(CATEGORY, PRICE)` **pairs**: products **1** and **3** in the sample table.

Do not confuse tuple comparison with two independent conditions:

```sql
WHERE category IN ('ELECTRONICS', 'ACCESSORIES')
  AND price IN (25000000, 350000)
```

The second condition can accept cross-combinations not listed in the original set of pairs. When checking relationships across multiple columns, tuple comparison or an appropriate join expresses the intent clearly.

### 2.7. Overly Long IN Lists

An `IN` clause containing thousands of literals is hard to read, hard to maintain, and can hit the **expression-count limit** depending on the Oracle version/syntax. In Oracle 19c, the typical limit for a single-column list is **1,000 expressions**, raising `ORA-01795` when exceeded.

For large datasets, consider:

- Loading values into a **temporary/staging table** following approved procedures, then using `JOIN` or `IN (SELECT ...)`.
- Passing the set of values through an API/collection supported by the driver and database.
- Batching requests per business requirements and reviewing the query plan.

Do not generate abnormally long SQL strings just to avoid designing a clean way to pass lists.

## 3. NOT IN and the NULL Trap

### 3.1. NOT IN When There Is No NULL

When all list values are non-`NULL`:

```sql
SELECT product_id, product_name, category
FROM   demo_products
WHERE  category NOT IN ('ELECTRONICS', 'ACCESSORIES')
ORDER  BY product_id;
```

In the sample data, product **6** in `STATIONERY` is selected. Product **7** with `CATEGORY=NULL` is **not selected**, even though in natural language we might say it "does not belong to those two categories."

That is because SQL cannot determine that `NULL` differs from the compared values under simple two-valued logic.

If you also want products without a category, state it explicitly:

```sql
SELECT product_id, product_name, category
FROM   demo_products
WHERE  category NOT IN ('ELECTRONICS', 'ACCESSORIES')
   OR  category IS NULL
ORDER  BY product_id;
```

Now the result includes **6** and **7**.

### 3.2. Why Is NOT IN Dangerous When NULL Appears?

Consider:

```sql
WHERE product_id NOT IN (1, 3, NULL)
```

For `PRODUCT_ID = 2`, the condition evaluates equivalently to:

```text
2 <> 1 AND 2 <> 3 AND 2 <> NULL
TRUE   AND TRUE   AND UNKNOWN
           = UNKNOWN
```

`WHERE` keeps only rows where the condition is TRUE, so **2** is eliminated. Values matching 1 or 3 evaluate to FALSE. Consequently, with a list containing `NULL` and non-null IDs in the sample table, `NOT IN` **returns no rows at all**.

This is a critical difference between:

```sql
-- May return zero rows because the list contains NULL.
SELECT product_id
FROM   demo_products
WHERE  product_id NOT IN (1, 3, NULL);
```

and the natural-language intent "get every product except 1 and 3."

### 3.3. The Trap When Using NOT IN with a Subquery

Suppose the promotion table gets a row with `PRODUCT_ID=NULL`:

```sql
INSERT INTO demo_promo_products VALUES (NULL);
COMMIT;
```

Now:

```sql
SELECT p.product_id, p.product_name
FROM   demo_products p
WHERE  p.product_id NOT IN (
         SELECT x.product_id
         FROM   demo_promo_products x
       )
ORDER BY p.product_id;
```

can return **0 rows** even though products 2, 4, 5, etc. are not in the promotion. A single `NULL` in the subquery result prevents `NOT IN` from proving TRUE for the remaining values.

**This is a common real-world application bug:** a data change in a child table suddenly makes a report return empty results.

### 3.4. How to Fix It: Filter NULL or Use NOT EXISTS

If you use `NOT IN` and business logic permits ignoring `NULL` values in the exclusion set, filter them out **inside the subquery**:

```sql
SELECT p.product_id, p.product_name
FROM   demo_products p
WHERE  p.product_id NOT IN (
         SELECT x.product_id
         FROM   demo_promo_products x
         WHERE  x.product_id IS NOT NULL
       )
ORDER BY p.product_id;
```

Another approach, often clearer for expressing exclusion relationships, is `NOT EXISTS`:

```sql
SELECT p.product_id, p.product_name
FROM   demo_products p
WHERE NOT EXISTS (
    SELECT 1
    FROM   demo_promo_products x
    WHERE  x.product_id = p.product_id
)
ORDER BY p.product_id;
```

On the sample tables, this query selects products that **have no promotion row matching their ID**, regardless of whether the promotion table has a `NULL` row.

`NOT EXISTS` checks whether any subquery row satisfies the **correlated condition**. A row with `x.product_id=NULL` does not satisfy equality with a product's non-null ID.

The two approaches are not automatically equivalent in every model, especially when the **outer column is also nullable** or additional complex conditions exist. Explicitly verify how business rules treat `NULL` on both sides.

### 3.5. Use IS NULL to Find Unknown Values

Incorrect:

```sql
-- This condition never evaluates to TRUE for NULL.
SELECT *
FROM demo_products
WHERE category = NULL;
```

Correct:

```sql
SELECT product_id, product_name
FROM demo_products
WHERE category IS NULL;
```

To exclude NULL:

```sql
WHERE category IS NOT NULL
```

Do not put `NULL` inside `IN (NULL)` expecting to match null rows. `IS NULL` is the dedicated condition for that case.

## 4. BETWEEN: A Range Inclusive of Both Endpoints

### 4.1. Syntax

```sql
expression BETWEEN lower_bound AND upper_bound
```

For comparable non-null values, the meaning is:

```sql
expression >= lower_bound
AND expression <= upper_bound
```

**`BETWEEN` is inclusive (including both the lower and upper bounds)**. If a price is exactly 100 or exactly 500, `price BETWEEN 100 AND 500` can select both.

Example:

```sql
SELECT product_id, product_name, price
FROM   demo_products
WHERE  price BETWEEN 300000 AND 8000000
ORDER  BY price, product_id;
```

Based on the sample data, matching IDs are **3** (350,000), **7** (1,200,000), and **4** (6,000,000). Product 8 has `PRICE=NULL`, so it is not selected.

### 4.2. BETWEEN Does Not Automatically Swap Bounds

Example:

```sql
WHERE price BETWEEN 8000000 AND 300000
```

Do not interpret this as "from 300,000 to 8,000,000." For non-NULL prices, the condition requires simultaneously:

```sql
price >= 8000000
AND price <= 300000
```

so no number in the normal numeric domain satisfies it.

In applications, if a user enters bounds in reverse order, validate or normalize them before building the query; Oracle will not swap them to form a valid range.

### 4.3. NOT BETWEEN

`NOT BETWEEN` finds values **outside the range**:

```sql
SELECT product_id, product_name, price
FROM   demo_products
WHERE  price NOT BETWEEN 300000 AND 8000000
ORDER  BY product_id;
```

When both bounds are valid and non-null, the condition is equivalent to:

```sql
price < 300000
OR price > 8000000
```

In the sample data, products priced at **60,000**, **190,000**, **8,500,000**, **18,000,000**, and **25,000,000** match. The product with `PRICE=NULL` is still not selected.

To also include unpriced rows:

```sql
WHERE price NOT BETWEEN 300000 AND 8000000
   OR price IS NULL
```

### 4.4. BETWEEN with DATE: The Time-Component Bug

Oracle `DATE` includes **hours, minutes, and seconds**. Consider:

```sql
SELECT product_id, product_name, created_at
FROM   demo_products
WHERE  created_at BETWEEN DATE '2026-11-14'
                      AND DATE '2026-11-15'
ORDER  BY product_id;
```

Those two ANSI date literals correspond to **00:00:00** at the start of each day. The condition selects:

- ID **1**, created Nov 14 at 09:15;
- ID **3**, created Nov 15 at 00:00.

However, it **misses ID 2**, created Nov 15 at **17:30**. If the goal is to find all records across both days (the 14th and 15th), `BETWEEN` above is **insufficient**.

### 4.5. Half-Open Intervals for Dates and Times

For timestamps, it is usually better to use:

```sql
SELECT product_id, product_name, created_at
FROM   demo_products
WHERE  created_at >= DATE '2026-11-14'
AND    created_at <  DATE '2026-11-16'
ORDER  BY product_id;
```

This returns the exact records for **all of the 14th and 15th**, including IDs **1, 2, 3**.

This is called a **half-open interval** `[start, end)`:

- start bound: **inclusive** (`>=`);
- end bound: **exclusive** (`<`).

This pattern works cleanly for both `DATE` and `TIMESTAMP` with fractional seconds, provided bounds are computed according to the data type's calendar/timezone logic. It avoids the `23:59:59` trick, which can miss `23:59:59.123456` in a `TIMESTAMP`.

Example with a `TIMESTAMP` column:

```sql
WHERE event_time >= TIMESTAMP '2026-11-14 00:00:00'
  AND event_time <  TIMESTAMP '2026-11-16 00:00:00'
```

If the column stores timezone-aware data, clearly define which timezone a "day" belongs to before choosing the bounds. Switching from `BETWEEN` to `>= / <` alone does not solve timezone offsets.

### 4.6. BETWEEN with Strings

Oracle allows comparing compatible character values:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name BETWEEN 'L' AND 'M'
ORDER  BY product_name;
```

However, **string ranges depend on character comparison/collation rules**, not the concept of "names starting with L or M." For example, `'Monitor 27%'` is typically greater than `'M'` because it has extra characters after `M`, so it may **fall outside** `'L'` to `'M'` even though it starts with M.

When filtering by **character prefix**, `LIKE 'M%'` is usually a better fit. String comparisons are also affected by collation/NLS and `CHAR` vs. `VARCHAR2`; avoid arbitrary alphabetical ranges when multilingual consistency matters.

### 4.7. BETWEEN with NULL

When a bound or compared expression is `NULL`, the condition can evaluate to UNKNOWN under SQL logic:

```sql
SELECT product_id
FROM   demo_products
WHERE  price BETWEEN 0 AND NULL;
```

You cannot use `NULL` as a shorthand for "no upper limit" in `BETWEEN`. For search forms that allow omitting the upper bound, write explicit conditions:

```sql
-- :min_price and :max_price are bind parameters.
SELECT product_id, product_name, price
FROM   demo_products
WHERE  (:min_price IS NULL OR price >= :min_price)
AND    (:max_price IS NULL OR price <= :max_price)
ORDER BY product_id;
```

This query expresses "ignore a condition if its corresponding bound parameter was not provided." Actual optimization depends on bind values, statistics, and the optimizer; for heavy workloads, consider dynamically building only the needed SQL predicates in the application with bound parameters, never concatenating user input directly into SQL.

## 5. LIKE: String Pattern Matching

### 5.1. Basic Syntax

```sql
character_expression LIKE pattern
```

Example:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE 'Laptop%'
ORDER  BY product_id;
```

The pattern `'Laptop%'` means a string starting with `Laptop`, followed by **0 or more characters**. On the sample table, the query selects IDs **1** and **2**.

`LIKE` is not semantic search: it matches **characters against a pattern**, using the collation and character representation rules applied by Oracle.

### 5.2. Two Primary Wildcards

| Wildcard | Meaning | Example pattern | Matches |
| --- | --- | --- | --- |
| `%` | **0 or more** characters | `'Lap%'` | `Lap`, `Laptop`, `Laptop Pro` |
| `_` | **Exactly 1** character | `'L_p'` | `Lap`, `Lip`; does not match `Lp` or `Loop` |

Note: `_` is an **underscore**, not a hyphen `-`. In `LIKE`, underscore is a wildcard by default; to search for a literal underscore, use `ESCAPE`.

Example:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%USB%'
ORDER  BY product_id;
```

The pattern `'%USB%'` means the string **contains** `USB` at any position. On the sample data, product **5 — Cable USB-C** is selected.

### 5.3. Essential Patterns to Know

| Pattern | Typical meaning |
| --- | --- |
| `'A%'` | Starts with A |
| `'%A'` | Ends with A |
| `'%A%'` | Contains A anywhere |
| `'A_B'` | Starts with A, one arbitrary character, ends with B |
| `'A%B'` | Starts with A and ends with B, with zero or more characters in between |
| `'____'` | Exactly 4 characters according to Oracle's character semantics for the type/pattern |
| `'A___%'` | Starts with A, followed by at least 3 arbitrary characters |
| `'%'` | Any **non-NULL** string, including zero-length strings at the pattern level |

In current Oracle SQL, an empty character string `''` of standard character types is treated as `NULL`; therefore `LIKE '%'` is **not** a way to select rows with a NULL column. Write `IS NULL` if you need to handle rows with missing data.

### 5.4. LIKE with Prefix and Suffix Patterns

Find product names starting with Laptop:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE 'Laptop%';
```

Find SKUs ending with `-05`:

```sql
SELECT product_id, sku
FROM   demo_products
WHERE  sku LIKE '%-05';
```

Find product names containing a substring:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%book%';
```

The result of the last example can vary depending on **collation/case-sensitivity settings**. Under standard case-sensitive semantics, `Notebook Basic` has lowercase `book`, so `'%book%'` matches while `'%BOOK%'` does not unless a case-insensitive mode is active.

### 5.5. LIKE with Pattern Length

Example:

```sql
-- Pattern must be exactly 5 characters long:
SELECT product_id, sku
FROM   demo_products
WHERE  sku LIKE '_____';
```

This has **5 underscores**. Each underscore matches one character under the active matching rules.

Another example:

```sql
-- SKU starts with LP, followed by any single character,
-- then exactly the two characters 01.
SELECT product_id, sku
FROM   demo_products
WHERE  sku LIKE 'LP_01';
```

`LP_01` here matches `LP_01`, but can also match `LPX01` or `LP-01`. If the application truly requires a literal underscore between `LP` and `01`, you must escape it as shown in the next section.

### 5.6. LIKE Does Not Interpret Regular Expressions by Default

In Oracle `LIKE`, symbols such as `.`, `*`, `?`, `+`, and `[A-Z]` do not carry regex meaning like they do in many programming languages.

Example:

```sql
WHERE product_name LIKE 'A.*'
```

does not mean "names starting with A followed by anything." It searches for a string containing `A`, a literal dot `.`, and a literal asterisk `*` in that exact sequence.

When you need complex patterns such as character classes, repetition counts, or alternation groups, Oracle provides `REGEXP_LIKE`, which is a separate mechanism from `LIKE` with its own syntax and cost.

## 6. ESCAPE: Searching for Literal % and _

### 6.1. Why Is ESCAPE Needed?

The sample table contains:

- `Mouse A_100`: `_` is part of the **actual name**.
- `Monitor 27%` and `Adaptor 100%`: `%` is part of the **actual name**.
- `LP_01`: SKU has a literal underscore.

If you write:

```sql
WHERE product_name LIKE '%_%'
```

you are **not** searching specifically for names with an underscore. The pattern has `%`, then `_` (any single character), then `%`, so it matches almost any non-empty name.

Fix: declare an **escape** character to tell Oracle that the following wildcard must be treated as a literal character.

### 6.2. ESCAPE Syntax

```sql
character_expression LIKE pattern ESCAPE escape_character
```

Example choosing backslash `\` as the escape character:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%\_%' ESCAPE '\'
ORDER  BY product_id;
```

In the pattern string:

- leading `%`: any number of characters;
- `\_`: **one literal underscore**;
- trailing `%`: any number of characters.

Sample table result: product **3 — Mouse A_100**.

**Oracle SQL note:** the `\` inside the literal `'\'` is just a normal SQL backslash character, not Java string-escape syntax. If you embed that SQL inside a Java string literal, you must also handle **Java string escaping** per the programming language's rules.

### 6.3. Searching for a Literal Percent Sign

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%\%%' ESCAPE '\'
ORDER  BY product_id;
```

The pattern `'%\%%'` looks for a literal `%` anywhere. On the sample data, the result is:

- **4 — Monitor 27%**
- **8 — Adaptor 100%**

Without escaping, e.g. `LIKE 'Monitor 27%'`, it only requires the prefix `Monitor 27` and could match strings that do not actually contain a percent sign.

### 6.4. Matching an Exact Prefix Containing an Underscore

```sql
SELECT product_id, sku
FROM   demo_products
WHERE  sku LIKE 'LP\_%' ESCAPE '\';
```

The pattern means **SKU starting with the literal string `LP_`**. On the sample data, it selects `LP_01`.

If you want to match the entire SKU exactly, you do not need `LIKE`:

```sql
SELECT product_id, sku
FROM   demo_products
WHERE  sku = 'LP_01';
```

When wildcards are unnecessary, **`=` expresses an exact match more clearly**, and underscore has no special meaning with `=`.

### 6.5. Choosing a Different ESCAPE Character

Backslash is not mandatory. You can choose another character, such as `!`:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%!%%' ESCAPE '!'
ORDER  BY product_id;
```

In this pattern, `!%` is a literal percent sign. Example searching for an underscore:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%!_%' ESCAPE '!';
```

The character declared in `ESCAPE` must follow Oracle's **single-character escape** rule. Do not use a multi-character string like `'AB'` as an escape marker. If the data itself can contain the escape marker, escape **the marker itself** when building the pattern.

### 6.6. What If the Pattern Comes from User Input?

Suppose a search box lets the user enter a "literal substring search" without letting them inject wildcards. If the user types `27%`, the application must not plug it straight into:

```sql
WHERE product_name LIKE '%' || :search_text || '%'
```

expecting `%` to be treated literally. If `:search_text='27%'`, the user's percent sign still acts as a wildcard.

You must **first escape characters that have special meaning in LIKE** inside the user input: the escape marker, `%`, and `_`; only then prepend and append the **application-controlled** `%` wildcards and apply `ESCAPE` consistently.

A pure-SQL illustration (assuming `:search_text` is user input and `!` is the escape marker):

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE
       '%' ||
       REPLACE(
         REPLACE(
           REPLACE(:search_text, '!', '!!'),
           '%', '!%'
         ),
         '_', '!_'
       ) ||
       '%'
       ESCAPE '!';
```

Order matters: **escape `!` itself first**, then `%` and `_`; if you change the order, you can accidentally double-escape markers just inserted.

Production queries must also address case-sensitivity/Unicode rules, `NULL` inputs, and input-length limits as required. **Bind variables are still mandatory** to pass input safely; escaping wildcards does not replace bind parameters for preventing SQL injection.

## 7. LIKE, Case Sensitivity, and Collation Rules

### 7.1. Results Can Depend on Collation

In many binary comparison configurations, `LIKE` is **case-sensitive**:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE 'laptop%';
```

With values `Laptop Pro` and `Laptop Air`, the lowercase pattern `laptop%` may not match when comparisons are case-sensitive.

However, you should not claim `LIKE` is **always** case-sensitive in every Oracle Database: in modern collation-enabled versions, results can be influenced by collation configuration and related NLS/object settings.

### 7.2. Explicitly Expressing Case-Insensitive Matching

Common approach:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  UPPER(product_name) LIKE UPPER('laptop%')
ORDER  BY product_id;
```

This explicitly expresses "convert both sides to uppercase before matching." It usually works well for simple ASCII data. For Vietnamese, Unicode, and accent-insensitive search requirements, `UPPER` alone may **not be enough**; inspect the configured collation and linguistic rules.

Performance note: wrapping a column in `UPPER` can prevent Oracle from using a standard index on the raw column in the same way as the original query. If such queries run frequently on large datasets, evaluate a **function-based index** or an appropriate collation/index design after measuring.

### 7.3. Do Not Confuse LIKE with LIKEC, LIKE2, LIKE4

Oracle also provides Unicode-related matching conditions such as `LIKEC`, `LIKE2`, and `LIKE4` in supporting releases. They differ in how characters are counted by code unit/Unicode form. For basic SELECT lessons, `LIKE` with `%`/`_` is the core focus; if your system needs precise matching on multilingual strings with supplementary characters, consult *Pattern-matching Conditions* for your exact Oracle version.

Do not assume an underscore always corresponds to one **byte**: Oracle evaluates patterns using character semantics, and Unicode strings may use multiple bytes per character.

### 7.4. CHAR and VARCHAR2 Can Behave Differently

A `CHAR(n)` column has trailing blank-padding semantics, whereas `VARCHAR2` is variable-length. This can affect comparisons and pattern matching, especially with implicit conversions or patterns containing spaces.

Do not assume:

```sql
CHAR_column LIKE 'ABC'
```

is completely equivalent to:

```sql
VARCHAR2_column LIKE 'ABC'
```

across all designs, because `CHAR` data may contain trailing padding spaces. When results surprise you, inspect **column types**, actual lengths, comparison rules, and the pattern string.

## 8. NULL and Three-Valued Logic in IN, BETWEEN, LIKE

### 8.1. Why Does WHERE Drop UNKNOWN Rows?

SQL uses three logical outcomes in applicable conditions:

| State | Meaning | Is the row kept by WHERE? |
| --- | --- | --- |
| TRUE | Condition is true | **Yes** |
| FALSE | Condition is false | No |
| UNKNOWN | Indeterminate, usually due to `NULL` | **No** |

Consider `demo_products`:

- `CATEGORY=NULL` at ID 7.
- `PRICE=NULL` at ID 8.

Example:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  price BETWEEN 100000 AND 1000000;
```

Row 8 has a NULL price, so the condition is not TRUE. It is not selected.

### 8.2. NULL with Conditions

| Condition | If the left expression is NULL (in standard cases) |
| --- | --- |
| `category IN ('A','B')` | UNKNOWN |
| `category NOT IN ('A','B')` | UNKNOWN |
| `price BETWEEN 1 AND 10` | UNKNOWN |
| `price NOT BETWEEN 1 AND 10` | UNKNOWN |
| `product_name LIKE 'A%'` | UNKNOWN |
| `product_name NOT LIKE 'A%'` | UNKNOWN |
| `category IS NULL` | TRUE |
| `category IS NOT NULL` | FALSE |

Do not reason "if A is not true, then NOT A must be true" when `NULL` is involved. `NOT UNKNOWN` is still UNKNOWN.

### 8.3. OR, AND, and Parentheses

Example finding products in ELECTRONICS or uncategorized, with price above 1,000,000:

```sql
SELECT product_id, product_name, category, price
FROM   demo_products
WHERE  (category = 'ELECTRONICS' OR category IS NULL)
AND    price > 1000000
ORDER  BY product_id;
```

Parentheses group the **category condition** before combining it with the price condition. Without parentheses, operator precedence between `AND` and `OR` changes the meaning.

Compare:

```sql
-- With parentheses: applies the price filter to both groups.
WHERE (category = 'ELECTRONICS' OR category IS NULL)
  AND price > 1000000

-- Without parentheses: interpreted as:
WHERE category = 'ELECTRONICS'
   OR (category IS NULL AND price > 1000000)
```

In the second example, all ELECTRONICS products are returned regardless of price. **Write parentheses according to business intent**, rather than relying on memorizing `AND`/`OR` precedence.

### 8.4. Do Not Turn NULL into a Fake Value Just to Dodge SQL Logic

`NVL(column, fallback)` can be used in certain scenarios, provided you understand data semantics. For instance:

```sql
WHERE NVL(price, 0) BETWEEN 0 AND 1000000
```

treats `PRICE=NULL` as the number **0**. That is wrong if NULL means "price unknown" rather than "free."

If business logic wants to include unknown prices, it is usually clearer to write:

```sql
WHERE price BETWEEN 0 AND 1000000
   OR price IS NULL
```

Then the logic directly reflects the query author's decision.

## 9. Combining IN, BETWEEN, and LIKE in Real Queries

### 9.1. Filtering Products by Three Criteria

Requirement:

- belongs to ELECTRONICS or ACCESSORIES;
- price from 200,000 to 10,000,000, inclusive of both ends;
- name contains the character `o` under the active matching rules.

```sql
SELECT product_id,
       product_name,
       category,
       price
FROM   demo_products
WHERE  category IN ('ELECTRONICS', 'ACCESSORIES')
AND    price BETWEEN 200000 AND 10000000
AND    product_name LIKE '%o%'
ORDER  BY price DESC, product_id;
```

This SQL combines a **set check**, a **range check**, and **pattern matching**.

In environments with different collations, `LIKE '%o%'` can behave differently with respect to uppercase/lowercase. When business rules require strict behavior, control collation or string normalization explicitly.

### 9.2. Finding Products by Prefix or SKU

```sql
SELECT product_id, product_name, sku
FROM   demo_products
WHERE  product_name LIKE 'Laptop%'
   OR  sku LIKE 'LP\_%' ESCAPE '\'
ORDER BY product_id;
```

Parentheses may be necessary when adding another condition:

```sql
SELECT product_id, product_name, sku, price
FROM   demo_products
WHERE  (product_name LIKE 'Laptop%'
        OR sku LIKE 'LP\_%' ESCAPE '\')
AND    price IS NOT NULL
ORDER BY product_id;
```

Do not write `product_name LIKE 'Laptop%' OR sku LIKE ... AND price ...` without reviewing grouping order.

### 9.3. Combining a Time Filter and Product Category

```sql
SELECT product_id,
       product_name,
       category,
       created_at
FROM   demo_products
WHERE  category IN ('ELECTRONICS', 'ACCESSORIES')
AND    created_at >= DATE '2026-11-14'
AND    created_at <  DATE '2026-12-01'
ORDER  BY created_at, product_id;
```

This is a common pattern for monthly or date-range reports: `IN` for categories, half-open intervals for timestamps/dates.

In Java programs or APIs, bind `DATE`/`TIMESTAMP` values with proper types rather than concatenating strings and relying on `NLS_DATE_FORMAT`.

### 9.4. Finding Products with No Category or Outside a List

```sql
SELECT product_id, product_name, category
FROM   demo_products
WHERE  category IS NULL
   OR  category NOT IN ('ELECTRONICS', 'ACCESSORIES')
ORDER BY product_id;
```

This handles NULL intentionally. Removing `IS NULL` drops ID 7 from the result.

### 9.5. Translating Questions into Accurate Conditions

| Business question | Suggested condition |
| --- | --- |
| Price matches one of three promo tiers | `price IN (99000, 199000, 299000)` |
| Price in closed range [100,000, 500,000] | `price BETWEEN 100000 AND 500000` |
| Price strictly above 100,000 and below 500,000 (excluding endpoints) | `price > 100000 AND price < 500000` |
| Date anywhere in November 2026 | `created_at >= DATE '2026-11-01' AND created_at < DATE '2026-12-01'` |
| Name starts with "Cable" | `product_name LIKE 'Cable%'` |
| Name contains "USB" | `product_name LIKE '%USB%'` |
| Name contains a literal percent sign | `product_name LIKE '%\%%' ESCAPE '\'` |
| Category not in A/B, including uncategorized | `category NOT IN ('A','B') OR category IS NULL` |

## 10. Performance: Filter Conditions and Index Usage

### 10.1. IN and Indexes

When the column used in `IN` has a suitable index, the Oracle Optimizer **may** consider index-based access, `INLIST ITERATOR`, or other strategies depending on:

- number of elements in the list;
- selectivity of the values;
- table size;
- object statistics;
- presence of joins, other filters, binds, and conditions;
- cost model and Oracle version.

There is no universal rule that "`IN` is always faster than `OR`." In many cases, the optimizer transforms logically equivalent expressions into very similar plans.

### 10.2. BETWEEN and Index Range Scan

The condition:

```sql
WHERE price BETWEEN 300000 AND 8000000
```

can be suitable for an **index range scan** if a B-tree index exists on `PRICE` and the optimizer estimates favorable cost.

In contrast:

```sql
WHERE ROUND(price / 1000) BETWEEN 300 AND 8000
```

applies arithmetic/functions to the column and can prevent using a standard index in the same way. For predictable performance, prefer comparing the raw column against properly computed bounds, or evaluate a deliberate function-based index.

**Do not automatically add indexes just because a query uses `BETWEEN`.** Indexes consume storage and incur write overhead; base decisions on the real workload.

### 10.3. LIKE with a Fixed Prefix vs. a Leading Wildcard

These two patterns differ in their ability to use efficient access paths:

```sql
-- Fixed prefix.
WHERE product_name LIKE 'Laptop%'

-- Leading wildcard.
WHERE product_name LIKE '%top%'
```

With an appropriate B-tree index, a pattern with a **fixed prefix** is generally far more favorable for key-range lookups. A pattern starting with `%` usually cannot leverage that prefix-range lookup and may have to inspect many more entries.

Exact outcomes still depend on collation, column functions, statistics, selectivity, and the optimizer. If your application needs arbitrary "contains substring" search over large text datasets, consider **Oracle Text** or an index design tailored to that query pattern.

### 10.4. UPPER, LOWER, and Function-Based Indexes

Example:

```sql
WHERE UPPER(product_name) LIKE 'LAPTOP%'
```

applying `UPPER` to the column can prevent using a B-tree index built on the original `PRODUCT_NAME`. For suitable workloads, a **function-based index** is an option worth evaluating:

```sql
-- DDL illustration; create only in authorized environments with a verified need.
CREATE INDEX idx_demo_products_upper_name
ON demo_products (UPPER(product_name));
```

Always inspect the actual plan and collation/language requirements; creating an index does not guarantee the optimizer will pick it.

### 10.5. Avoid Casting NUMBER or DATE Columns to Strings Just to Use LIKE

Discouraged examples:

```sql
WHERE TO_CHAR(product_id) LIKE '1%'
```

or:

```sql
WHERE TO_CHAR(created_at, 'DD/MM/YYYY') LIKE '14/11/%'
```

Such queries change the operation from a **NUMBER/DATE** comparison to **VARCHAR2** matching and can hurt index usage, formatting reliability, NLS independence, and correctness.

If filtering by specific IDs, use numbers and `IN`. If filtering by dates, use `DATE`/`TIMESTAMP` with exact intervals. Use `LIKE` on character representations only when **the true business goal is string pattern matching**.

### 10.6. Inspecting Execution Plans

In a practice environment, you can explain a query:

```sql
EXPLAIN PLAN FOR
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE 'Laptop%';

SELECT *
FROM   TABLE(DBMS_XPLAN.DISPLAY);
```

This shows an **estimated execution plan**, not all metrics from an actual run. For real performance diagnostics, DBAs inspect cursor plans from actual executions and relevant statistics.

Do not assume `TABLE ACCESS FULL` is wrong or inefficient in every scenario; on small tables, a full scan is often cheaper than an index scan.

## 11. Bind Variables, Java Applications, and Safe Searching

### 11.1. Never Concatenate User Input Directly into SQL

Not recommended:

```java
String sql = "SELECT product_id FROM demo_products " +
             "WHERE product_name LIKE '%" + userInput + "%'";
```

User input concatenated straight into SQL text can cause syntax errors or open SQL injection vulnerabilities. In addition, if the user types `%` or `_`, the application unintentionally treats them as wildcards.

General safe pattern:

```java
String sql =
    "SELECT product_id, product_name " +
    "FROM demo_products " +
    "WHERE product_name LIKE ?";

try (java.sql.PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "Laptop%");
    try (java.sql.ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("product_id"));
        }
    }
}
```

Assumes `connection` is already a valid JDBC connection. The SQL uses a `?` placeholder and passes the value via binding, never concatenating into SQL. Here `%` is a wildcard **explicitly supplied by the application**.

### 11.2. Binding Multiple Values for IN

A single standard bind parameter does not automatically turn the string `'1,3,5'` into a three-element `IN` list:

```sql
-- NOT equivalent to IN (1, 3, 5):
WHERE product_id IN (:ids)
```

If `:ids` is bound as a single string `'1,3,5'`, it is **one string value**, not three distinct numeric values.

When the element count is small and known, you can write:

```sql
WHERE product_id IN (:id1, :id2, :id3)
```

In Java/JDBC, you can generate the exact number of placeholders from the **application-determined element count** and bind each value:

```java
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Collections;
import java.util.List;

List<Long> ids = List.of(1L, 3L, 5L);

if (!ids.isEmpty()) {
    String placeholders =
        String.join(", ", Collections.nCopies(ids.size(), "?"));

    String sql = "SELECT product_id, product_name " +
                 "FROM demo_products WHERE product_id IN (" +
                 placeholders + ")";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        for (int i = 0; i < ids.size(); i++) {
            ps.setLong(i + 1, ids.get(i));
        }

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                System.out.println(rs.getString("product_name"));
            }
        }
    }
}
```

This snippet uses `List.of` (Java 9+) and does not handle overly large lists; real applications must adopt a strategy compatible with their Oracle version and system limits.

If `ids` is empty, never generate `IN ()` because that is not valid SQL syntax in Oracle. Return an empty result at the application layer when business rules define "no IDs selected means no rows," or build another intentional valid condition.

### 11.3. Escaping LIKE Input from a Search Box

To search for a literal string typed by a user, do both of the following:

1. Use a **bind variable** to keep input separate from SQL structure.
2. **Escape wildcards** (`%`, `_`, and the escape marker) before adding application-supplied `%` wildcards.

For Vietnamese data, you also need consistent rules for **case, accents, and Unicode**. Safe binding alone does not determine collation semantics.

### 11.4. Binding for BETWEEN and Dates/Times

Example price-range query:

```sql
SELECT product_id, product_name, price
FROM   demo_products
WHERE  price BETWEEN :min_price AND :max_price;
```

Both binds should use the appropriate numeric type.

For dates/times, use typed date/timestamp binds when supported by the driver and needed by the application, instead of passing strings like `'15/11/2026'` into `BETWEEN` and depending on the session's `NLS_DATE_FORMAT`.

## 12. Diagnosing Unexpected Query Results

### 12.1. IN Returns No Rows for a Seemingly Matching Value

Possible causes:

- NUMBER vs. VARCHAR2 type mismatch and implicit conversion;
- trailing spaces, invisible characters, or `CHAR` padding;
- case sensitivity or collation;
- the stored value is `NULL`;
- connected to the wrong schema/PDB or wrong table.

Start by checking **column data types** and actual stored values; do not blindly add `UPPER`/`TRIM` to every query before understanding the data.

### 12.2. NOT IN Returns 0 Rows

Check whether **the subquery returns `NULL`**:

```sql
SELECT COUNT(*) AS null_count
FROM   demo_promo_products
WHERE  product_id IS NULL;
```

If so, decide whether `NULL` represents bad data or should be ignored in the exclusion set. Often you can use `NOT EXISTS` or add `IS NOT NULL` in the subquery if that matches business intent.

### 12.3. BETWEEN Misses the End of the Final Day

Check the `DATE`/`TIMESTAMP` column type and time/fractional-second parts. Writing `DATE '2026-11-15'` as the upper bound means **00:00:00** at the start of Nov 15, not the end of that day.

Use a half-open interval up to the **start of Nov 16** to cover all of Nov 15 in the example.

### 12.4. LIKE Matches Too Many Rows Due to %

The user wants `'100%'`, but the application runs:

```sql
WHERE product_name LIKE '%100%%'
```

That pattern matches `100` followed by anything, without requiring a literal percent sign.

Fix:

```sql
WHERE product_name LIKE '%100\%%' ESCAPE '\'
```

If the pattern comes from dynamic input, perform controlled escaping in the application or in SQL as shown in section 6.6.

### 12.5. LIKE with an Underscore Returns Too Broad a Result

The pattern:

```sql
WHERE sku LIKE 'LP_01'
```

also matches SKUs whose third character is not an underscore. To require a literal underscore:

```sql
WHERE sku LIKE 'LP\_01' ESCAPE '\'
```

If searching for one exact SKU, `sku = 'LP_01'` is simpler.

### 12.6. LIKE Fails on Case or Accent Differences

Check collation/NLS, column types, Unicode normalization, and business requirements. `UPPER` can work in simple cases, but do not assume it solves full accent-insensitive Vietnamese search.

### 12.7. WHERE Mixing AND and OR Returns Extra Rows

Example:

```sql
WHERE category = 'ELECTRONICS'
   OR category = 'ACCESSORIES'
  AND price > 1000000
```

Here `AND` has higher precedence than `OR`. To apply the price condition to **both categories**, write:

```sql
WHERE category IN ('ELECTRONICS', 'ACCESSORIES')
AND   price > 1000000
```

or add explicit parentheses.

### 12.8. ORA-01722, ORA-018xx, or ESCAPE Errors

Common root causes:

| Symptom | What to check |
| --- | --- |
| `ORA-01722: invalid number` | Comparing a number with a non-numeric string or implicit conversion? |
| `ORA-01861`, `ORA-018xx` errors | Passing a datetime string that does not match the format/session NLS? |
| `ESCAPE`-related error | Is the escape marker strictly one character? Is the pattern escaped properly? |
| `ORA-01795` with a large IN list on applicable releases | Does the expression list exceed the limit? Switch to a table/subquery/collection? |
| SQL returns no rows even though data exists | Check `NULL`, data types, collation, parentheses, and schema/PDB. |

Do not "fix" errors by removing `WHERE` or converting all data to strings. Isolate the cause at each layer: data types, conditions, session settings, and privileges.

## 13. Comprehensive Hands-On Exercises

This section uses `DEMO_PRODUCTS` and `DEMO_PROMO_PRODUCTS` created earlier. Every query is read-only. If you have not created the sample tables yet, create them in your practice schema first.

### Exercise 1 — IN on Categories

Requirement: retrieve all products in ELECTRONICS or ACCESSORIES, ordered by ID ascending.

```sql
SELECT product_id, product_name, category
FROM   demo_products
WHERE  category IN ('ELECTRONICS', 'ACCESSORIES')
ORDER BY product_id;
```

**Expected result:** IDs 1, 2, 3, 4, 5, 8, 9.

### Exercise 2 — NOT IN and NULL

Requirement: retrieve products not in ELECTRONICS/ACCESSORIES **and** products without an assigned category.

```sql
SELECT product_id, product_name, category
FROM   demo_products
WHERE  category NOT IN ('ELECTRONICS', 'ACCESSORIES')
   OR  category IS NULL
ORDER BY product_id;
```

**Expected result:** IDs 6 and 7. This illustrates that `NOT IN` does not include NULL automatically.

### Exercise 3 — BETWEEN on Price

Requirement: price from 300,000 to 8,000,000, inclusive of both bounds.

```sql
SELECT product_id, product_name, price
FROM   demo_products
WHERE  price BETWEEN 300000 AND 8000000
ORDER BY price, product_id;
```

**Expected result:** IDs 3, 7, 4 in ascending price order.

### Exercise 4 — Date/Time Range

Requirement: products created on Nov 14 and Nov 15, 2026, including 17:30 on the 15th.

```sql
SELECT product_id,
       product_name,
       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_text
FROM   demo_products
WHERE  created_at >= DATE '2026-11-14'
AND    created_at <  DATE '2026-11-16'
ORDER  BY created_at, product_id;
```

**Expected result:** IDs 1, 3, 2 in ascending timestamp order.

### Exercise 5 — LIKE with a Prefix

Requirement: name starts with `Laptop`.

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE 'Laptop%'
ORDER BY product_id;
```

**Expected result:** IDs 1, 2.

### Exercise 6 — LIKE with an Embedded Substring

Requirement: find names containing `USB`.

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%USB%'
ORDER BY product_id;
```

**Expected result:** ID 5.

### Exercise 7 — Escaping the Underscore Character

Requirement: find SKUs starting with the literal prefix `LP_`.

```sql
SELECT product_id, sku
FROM   demo_products
WHERE  sku LIKE 'LP\_%' ESCAPE '\'
ORDER BY product_id;
```

**Expected result:** ID 1.

### Exercise 8 — Escaping the Percent Sign

Requirement: find all names containing a literal percent sign.

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%\%%' ESCAPE '\'
ORDER BY product_id;
```

**Expected result:** IDs 4, 8.

### Exercise 9 — NOT IN with a Subquery Containing NULL

In `DEMO_PROMO_PRODUCTS`, if you inserted `NULL` in section 3.3, run:

```sql
SELECT product_id
FROM   demo_products
WHERE  product_id NOT IN (
         SELECT product_id FROM demo_promo_products
       );
```

**Expected:** no rows. This is three-valued logic behavior, not a statement that every product is in the promotion list.

Try rewriting it:

```sql
SELECT p.product_id
FROM   demo_products p
WHERE NOT EXISTS (
    SELECT 1
    FROM   demo_promo_products x
    WHERE  x.product_id = p.product_id
)
ORDER BY p.product_id;
```

**Expected:** every product except 1 and 3; specifically IDs 2, 4, 5, 6, 7, 8, 9.

### Exercise 10 — Combining All Three Conditions

Requirement: select only products in ELECTRONICS or ACCESSORIES, priced between 300,000 and 10,000,000, whose name contains `o` under the current matching configuration.

```sql
SELECT product_id, product_name, category, price
FROM   demo_products
WHERE  category IN ('ELECTRONICS', 'ACCESSORIES')
AND    price BETWEEN 300000 AND 10000000
AND    product_name LIKE '%o%'
ORDER  BY product_id;
```

This practices combining all three filters. Under standard case-sensitive matching, matching rows from the sample table are **3 (Mouse A_100)** and **4 (Monitor 27%)**. If collation changes, re-evaluate case-matching semantics before judging results.

### Exercise 11 — Inspecting Data Types

```sql
SELECT column_name, data_type, data_length
FROM   user_tab_columns
WHERE  table_name = 'DEMO_PRODUCTS'
ORDER BY column_id;
```

Compare to see why `PRICE` should use numeric comparison, `CREATED_AT` should use DATE intervals, and `PRODUCT_NAME` is the right column for `LIKE`.

### Exercise 12 — Cleaning Up Practice Data

Run only after confirming these are the demo tables you created and contain no data worth keeping:

```sql
-- DESTRUCTIVE OPERATION, for study schemas only.
DROP TABLE demo_promo_products PURGE;
DROP TABLE demo_products PURGE;
```

`DROP TABLE ... PURGE` deletes the objects and bypasses the recycle bin. Because this is DDL, do not rely on `ROLLBACK` to undo it. Never run on production tables.

## 14. Misconceptions to Avoid

**"`IN (1,3,5)` means from 1 to 5."**  
No. It checks only the exact values 1, 3, and 5. For a range, use `BETWEEN 1 AND 5` or `>=`/`<=`.

**"The order of values inside IN determines result order."**  
No. Only `ORDER BY` guarantees the requested output order of a SELECT.

**"`NOT IN ('A','B')` also returns NULLs."**  
No. For NULL values, the condition does not evaluate to TRUE. If business logic wants NULLs, add `OR column IS NULL`.

**"`NOT IN` is always safe with a subquery."**  
No. A single `NULL` in the subquery result can make the entire exclusion query return zero rows. Consider `NOT EXISTS` or explicitly filtering NULLs.

**"`BETWEEN` excludes the two endpoints."**  
Wrong. `BETWEEN` includes both the lower and upper bounds.

**"`BETWEEN DATE '2026-11-14' AND DATE '2026-11-15'` covers two full days."**  
No. The upper bound is only the start of the 15th; timestamps after midnight on the 15th fall outside the range.

**"`LIKE 'A_B'` searches for an underscore."**  
No. `_` is a wildcard matching any single character. Use `ESCAPE` or `=` when you want a literal underscore.

**"`LIKE '100%'` means a string containing a percent sign."**  
No. `%` is a wildcard. You must escape it if you want a literal percent sign.

**"`LIKE` is always case-insensitive."**  
No. That depends on the environment's matching/collation semantics.

**"Casting every column with `TO_CHAR` makes filtering easier."**  
No. It causes type conversions, depends on formatting, and can block index usage. Filter using each column's native data type.

**"`LIKE '%'` selects all rows, including NULL columns."**  
No. NULL makes the condition evaluate to UNKNOWN. Express NULL inclusion explicitly in SQL if needed.

## 15. Self-Check Questions

1. In Oracle, what does `price IN (100, 200, 300)` correspond to: a set of three values or the range 100–300?
2. Does `price BETWEEN 100 AND 300` include prices 100 and 300?
3. If price is unknown (`NULL`), does `price NOT BETWEEN 100 AND 300` automatically select it?
4. For the string `'Laptop Pro'`, does the pattern `'Laptop%'` match?
5. Does the pattern `'LP_01'` in `LIKE` require the third character to be an underscore?
6. Write a `LIKE` condition finding names that contain a literal percent sign anywhere.
7. Why does `NOT IN (1, 3, NULL)` typically fail to return IDs other than 1 and 3?
8. On a large table, why is `LIKE 'Lap%'` usually more favorable than `LIKE '%Lap%'` for a standard B-tree index?
9. A `DATE` column has timestamps at 09:15 on the 14th and 17:30 on the 15th. Why does `BETWEEN DATE '2026-11-14' AND DATE '2026-11-15'` miss the 17:30 row?
10. Does `WHERE category = 'A' OR category = 'B' AND price > 100` apply the price filter to category A?
11. If a user enters `'12%'` into a "literal substring search" box, which characters must be escaped before the application adds wildcards?
12. Can you bind the string `'1,3,5'` to `:ids` so Oracle treats `IN (:ids)` as a list of three IDs?
13. Is a product with `CATEGORY=NULL` selected by `category IN ('ELECTRONICS','ACCESSORIES')`?
14. If the goal is to cover all of November 2026, how should the time interval be written?
15. When searching for exact SKU `'LP_01'` without needing wildcards, should you use `=` or `LIKE`?

**Suggested answers:**

1. The set of three values: 100, 200, 300.
2. Yes, because both endpoints are included.
3. No; add `OR price IS NULL` if business logic wants unknown prices.
4. Yes, because `%` matches any trailing characters.
5. No; `_` matches any single character.
6. `product_name LIKE '%\%%' ESCAPE '\'`.
7. Because `NULL` turns the remaining inequality checks into UNKNOWN under three-valued logic.
8. A fixed-prefix pattern supports range scanning in the key order; a leading `%` pattern usually cannot locate a starting range in a B-tree that way.
9. `DATE '2026-11-15'` is 00:00 on the 15th, not the end of the 15th.
10. No; `AND` has higher precedence than `OR`. Use parentheses or `IN`.
11. The escape marker, `%`, and `_`; then safely bind the constructed pattern.
12. No, that is bound as a single string value rather than a split list.
13. No, the condition evaluates to UNKNOWN for NULL.
14. `created_at >= DATE '2026-11-01' AND created_at < DATE '2026-12-01'`.
15. `sku = 'LP_01'`.

## 16. Oracle Reference Documentation

- [Oracle Database SQL Language Reference — IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html): list and subquery syntax, `IN`/`NOT IN` behavior.
- [Oracle Database SQL Language Reference — BETWEEN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/BETWEEN-Condition.html): range conditions and endpoints.
- [Oracle Database SQL Language Reference — Pattern-matching Conditions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Pattern-matching-Conditions.html): `LIKE`, `%`, `_`, `ESCAPE`, and Unicode variants.
- [Oracle Database SQL Language Reference — NULL Conditions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Null-Conditions.html): `IS NULL` and `IS NOT NULL`.
- [Oracle Database SQL Language Reference — EXISTS Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html): checking row existence in subqueries.
- [Oracle Database SQL Language Reference — Logical Conditions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Logical-Conditions.html): `AND`, `OR`, `NOT`, and three-valued logic.
- [Oracle Database SQL Language Reference — Data Type Comparison Rules](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Type-Comparison-Rules.html): numeric, character, and datetime comparisons and conversion rules.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): optimizer, access paths, indexes, and query plan analysis.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `SELECT`, `WHERE`, and `ORDER BY` structure.

When choosing among `IN`, `BETWEEN`, and `LIKE`, start from the **meaning of the question**: checking a **set of values**, a **bounded range**, or a **string pattern**. Always define how **`NULL`** is handled, use `ESCAPE` when `%`/`_` are literal data characters, use **half-open intervals for dates/times**, and pass application values via **bind variables**. These habits keep Oracle queries faithful to business semantics, readable, and consistent across environments.
