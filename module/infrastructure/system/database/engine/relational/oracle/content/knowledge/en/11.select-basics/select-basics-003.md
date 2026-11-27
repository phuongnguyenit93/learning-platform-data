# WHERE, Comparison Operators, and Combining AND, OR, NOT in Oracle SQL

When writing a `SELECT` statement in **Oracle Database**, developers usually do not want to read every row of a table. Instead, we need to filter records that meet business rules: paid orders, transactions above a threshold, customers in a region, or orders that **both** have an eligible status **and** fall within a requested time range. The **`WHERE`** clause is where those filter conditions are expressed.

```sql
SELECT order_id, customer_name, amount
FROM orders
WHERE order_status = 'PAID'
  AND amount >= 300;
```

In the statement above, `WHERE` keeps only rows where **both conditions** are true: status equals `'PAID'` **and** order amount is at least 300. To write accurate filters, you need to understand comparison operators (`=`, `<>`, `<`, `>`, `<=`, `>=`), logical operators (`AND`, `OR`, `NOT`), **operator precedence**, parentheses, and **three-valued logic (`TRUE`/`FALSE`/`UNKNOWN`)** when `NULL` is present.

This lesson focuses on Oracle SQL syntax, explains how to combine conditions, illustrates with hands-on data, and points out mistakes that can cause reports to return wrong data even though the SQL executes without error.

## 1. Position of WHERE in a SELECT Statement

A basic query typically takes the form:

```sql
SELECT column_1, column_2, ...
FROM table_name
WHERE search_condition
ORDER BY column_1;
```

- `SELECT`: specifies the columns or expressions to return.
- `FROM`: identifies the table, view, or data source.
- **`WHERE`:** filters each row based on a logical condition.
- `ORDER BY`: sorts the resulting rows after filtering.

**Key rule:** `WHERE` only keeps rows for which the condition evaluates to **`TRUE`**. If the condition is `FALSE` or **`UNKNOWN`** (indeterminate, usually due to `NULL`), that row does not appear in the result.

```text
                       TABLE ORDERS
                             |
                             v
                   Evaluate WHERE condition
                             |
                   +---------+---------+
                   |         |         |
                  TRUE     FALSE     UNKNOWN
                   |         |         |
                   v         +---------+
               Keep row        Drop row
                   |
                   v
              SELECT / ORDER BY
                   |
                   v
                 Result
```

Without `WHERE`, a typical `SELECT` can return all rows allowed by the query source. On large tables, this both wastes resources and can return data outside the intended business scope. Conversely, **logical filter correctness does not guarantee a fast query**: performance also depends on data, indexes, statistics, and Oracle's execution plan.

## 2. Preparing Sample Data

The following examples use a dummy table **`LAB_WHERE_ORDERS`**, containing no real customer data. This DDL/DML is intended only for an Oracle **DEV/TEST** practice schema with `CREATE TABLE` privilege and appropriate quota. Before running, verify the current user and PDB:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user
FROM dual;
```

### 2.1. Creating the Table in the Lab Schema

```sql
CREATE TABLE lab_where_orders (
    order_id       NUMBER PRIMARY KEY,
    customer_name  VARCHAR2(80 CHAR) NOT NULL,
    region_code    VARCHAR2(10 CHAR),
    order_status   VARCHAR2(20 CHAR) NOT NULL,
    amount         NUMBER(12, 2) NOT NULL,
    created_on     DATE NOT NULL,
    is_priority    NUMBER(1) DEFAULT 0 NOT NULL,
    CONSTRAINT ck_lab_where_priority CHECK (is_priority IN (0, 1))
);
```

`REGION_CODE` allows `NULL` to demonstrate three-valued logic. `ORDER_STATUS` and `AMOUNT` are declared `NOT NULL` so basic comparison examples do not have to handle missing data. The `IS_PRIORITY` column uses `NUMBER(1)` with the convention `1 = priority`, `0 = non-priority`; this is a flag representation compatible across many Oracle versions, rather than native SQL `BOOLEAN`.

### 2.2. Loading Eight Sample Orders

```sql
INSERT ALL
    INTO lab_where_orders VALUES (1, 'An',   'HN',  'NEW',       150,  DATE '2026-11-01', 1)
    INTO lab_where_orders VALUES (2, 'Binh', 'HCM', 'PAID',      350,  DATE '2026-11-02', 0)
    INTO lab_where_orders VALUES (3, 'Chi',  'HN',  'PAID',      500,  DATE '2026-11-03', 1)
    INTO lab_where_orders VALUES (4, 'Dung', 'DN',  'CANCELLED', 120,  DATE '2026-11-04', 0)
    INTO lab_where_orders VALUES (5, 'Em',   NULL,  'NEW',       250,  DATE '2026-11-05', 0)
    INTO lab_where_orders VALUES (6, 'Giang','HCM', 'NEW',      1000,  DATE '2026-11-06', 1)
    INTO lab_where_orders VALUES (7, 'Ha',   'DN',  'PAID',       90,  DATE '2026-11-07', 0)
    INTO lab_where_orders VALUES (8, 'Khanh',NULL,  'PAID',      400,  DATE '2026-11-08', 1)
SELECT 1 FROM dual;

COMMIT;
```

Oracle uses **`DATE 'YYYY-MM-DD'`** to express a date as a date literal, avoiding dependence on the session's default date string format. The dataset has eight rows:

| `ORDER_ID` | Customer | Region | Status | `AMOUNT` | Created On | Priority |
|---:|---|---|---|---:|---|---:|
| 1 | An | HN | NEW | 150 | 2026-11-01 | 1 |
| 2 | Binh | HCM | PAID | 350 | 2026-11-02 | 0 |
| 3 | Chi | HN | PAID | 500 | 2026-11-03 | 1 |
| 4 | Dung | DN | CANCELLED | 120 | 2026-11-04 | 0 |
| 5 | Em | `NULL` | NEW | 250 | 2026-11-05 | 0 |
| 6 | Giang | HCM | NEW | 1000 | 2026-11-06 | 1 |
| 7 | Ha | DN | PAID | 90 | 2026-11-07 | 0 |
| 8 | Khanh | `NULL` | PAID | 400 | 2026-11-08 | 1 |

From here on, the `SELECT` statements in this lesson can be practiced directly against `LAB_WHERE_ORDERS`. Examples referencing other tables are explicitly marked as conceptual examples.

## 3. Six Common Comparison Operators

Oracle SQL supports comparison operators for building conditions in `WHERE`:

| Operator | Meaning | Example | Condition to satisfy |
|---|---|---|---|
| `=` | Equal to | `order_status = 'PAID'` | Status equals PAID |
| `<>` | Not equal to | `order_status <> 'CANCELLED'` | Status is not CANCELLED |
| `!=` | Not equal to (Oracle-supported form) | `amount != 0` | Amount is non-zero |
| `>` | Greater than | `amount > 300` | Amount strictly greater than 300, excluding 300 |
| `>=` | Greater than or equal to | `amount >= 300` | Amount at least 300 |
| `<` | Less than | `amount < 300` | Amount below 300 |
| `<=` | Less than or equal to | `amount <= 300` | Amount at most 300 |

For inequality, you can write `<>`, `!=`, or `^=` in Oracle; **`<>`** is the standard SQL form and is widely recognized. A single equals sign `=` **compares values** in a condition, unlike variable assignment in Java. Do not write `==` as in many programming languages:

```sql
-- Correct:
SELECT order_id FROM lab_where_orders WHERE amount = 500;

-- Do not use Java/C-style syntax in SQL conditions:
-- SELECT order_id FROM lab_where_orders WHERE amount == 500;
```

### 3.1. Equal (`=`) and Not Equal (`<>`)

```sql
SELECT order_id, customer_name, order_status
FROM lab_where_orders
WHERE order_status = 'PAID'
ORDER BY order_id;
```

The result contains orders **2, 3, 7, 8**, as only those four rows have `ORDER_STATUS = 'PAID'`.

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE order_status <> 'CANCELLED'
ORDER BY order_id;
```

The second query retrieves all orders except order **4**. Because `ORDER_STATUS` is declared `NOT NULL`, there is no `UNKNOWN` issue here. However, with a nullable column like `REGION_CODE`, `<>` does not automatically include `NULL`; a later section explains why.

### 3.2. Greater Than, Less Than, and Boundaries

```sql
-- Values greater than 350, excluding 350.
SELECT order_id, amount
FROM lab_where_orders
WHERE amount > 350
ORDER BY amount;
```

Orders **8 (400), 3 (500), 6 (1000)** match. Using `>= 350` adds order **2 (350)**. When translating a business rule into SQL, the difference between **"greater than"** and **"at least"** can affect invoices, approval thresholds, or discount tiers.

```sql
-- Amounts from 200 to 500, inclusive of both endpoints.
SELECT order_id, amount
FROM lab_where_orders
WHERE amount >= 200
  AND amount <= 500
ORDER BY order_id;
```

The result is orders **2, 3, 5, 8**. Oracle does not support mathematical chained comparisons like `200 <= amount <= 500`; combine **two conditions with `AND`** or use `BETWEEN` where appropriate.

### 3.3. Character Comparison Is Not Identical to Numeric Comparison

```sql
SELECT order_id, customer_name
FROM lab_where_orders
WHERE customer_name = 'An';
```

`'An'` is a **string literal** because it is enclosed in single quotes. For character comparisons, results depend on **data type, collation, and certain Oracle comparison settings**. Do not assume every deployment treats `'An'` as equal to `'an'` or always treats them differently in the same way. `CHAR` comparisons also follow specific blank-padding rules; `VARCHAR2` has different semantics.

If business logic requires **case-insensitive** comparison, design it explicitly (collation, a normalized column, or an expression like `UPPER(customer_name) = 'AN'`) and test with actual languages/characters. Wrapping a column in a function can affect standard index usage, so do not mechanically turn every comparison into `UPPER(...)`.

### 3.4. Comparing Dates and Times

```sql
SELECT order_id, created_on
FROM lab_where_orders
WHERE created_on >= DATE '2026-11-03'
ORDER BY created_on;
```

The result is orders **3 through 8**, because their dates are on or after 2026-11-03. Oracle's `DATE` type **includes hours, minutes, and seconds**, even though the sample rows store midnight. If `CREATED_ON` contains time components, the condition:

```sql
WHERE created_on = DATE '2026-11-03'
```

matches only values at exact **00:00:00** on that day, not automatically every record from morning to night. Filtering a single day using a **half-open range** is usually clearer:

```sql
SELECT order_id, created_on
FROM lab_where_orders
WHERE created_on >= DATE '2026-11-03'
  AND created_on <  DATE '2026-11-04';
```

In this example with whole-date values, the query picks order **3**. If the table stores times of day on Nov 03, it still accurately selects all timestamps before 00:00 on Nov 04. When working with `TIMESTAMP WITH TIME ZONE`, define a timezone policy and use properly typed parameters; date-range comparisons should not rely on unformatted date strings.

## 4. Logical Operator AND: Every Condition Must Be True

`AND` combines multiple conditions. A row is kept only when **all conditions are `TRUE`**.

```sql
SELECT order_id, order_status, amount
FROM lab_where_orders
WHERE order_status = 'PAID'
  AND amount >= 300
ORDER BY order_id;
```

Paid orders are **2, 3, 7, 8**. Among them, orders **2 (350), 3 (500), 8 (400)** meet the 300 threshold; order **7 (90)** fails and is dropped.

| `ORDER_ID` | `order_status = 'PAID'` | `amount >= 300` | `AND` | Keep? |
|---:|---|---|---|---|
| 2 | TRUE | TRUE | TRUE | Yes |
| 3 | TRUE | TRUE | TRUE | Yes |
| 7 | TRUE | FALSE | FALSE | No |
| 8 | TRUE | TRUE | TRUE | Yes |

An example where **three conditions must all be true**:

```sql
SELECT order_id, amount, is_priority
FROM lab_where_orders
WHERE amount >= 300
  AND is_priority = 1
  AND order_status <> 'CANCELLED'
ORDER BY order_id;
```

The result is orders **3, 6, 8**. Order 6 has status `NEW`, yet still qualifies because the condition only requires **not cancelled**, rather than strictly `PAID`. If actual business rules require paid orders, write `order_status = 'PAID'` instead of `<> 'CANCELLED'`.

### 4.1. AND Truth Table with TRUE/FALSE

| A | B | `A AND B` |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| FALSE | TRUE | FALSE |
| FALSE | FALSE | FALSE |

In practice, SQL also has `UNKNOWN`; three-valued logic is covered separately. Knowing `AND` does not mean "whichever condition appears first is guaranteed to be evaluated first"; the Oracle optimizer can reorder or transform predicate evaluation.

## 5. Logical Operator OR: Only One Condition Needs to Be True

`OR` keeps a row when **at least one condition is `TRUE`**.

```sql
SELECT order_id, region_code, order_status
FROM lab_where_orders
WHERE region_code = 'HN'
   OR order_status = 'NEW'
ORDER BY order_id;
```

Orders in region `HN` are **1, 3**. Orders with status `NEW` are **1, 5, 6**. The union of the two sets is **1, 3, 5, 6**. Order 1 satisfies both conditions but **appears only once** because each source row is evaluated once; `OR` does not duplicate rows.

| `ORDER_ID` | Region HN? | Status NEW? | `OR` | Outcome |
|---:|---|---|---|---|
| 1 | TRUE | TRUE | TRUE | Keep |
| 3 | TRUE | FALSE | TRUE | Keep |
| 5 | UNKNOWN (`NULL`) | TRUE | TRUE | Keep |
| 6 | FALSE | TRUE | TRUE | Keep |
| 8 | UNKNOWN (`NULL`) | FALSE | UNKNOWN | Drop |

This example shows **`OR` can evaluate to `TRUE` even if one side is `UNKNOWN`**, provided the other side is `TRUE`.

### 5.1. Is OR Different from IN?

When comparing **the same column** against multiple fixed values, `IN` is usually more concise:

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE region_code = 'HN'
   OR region_code = 'HCM';
```

This can be written equivalently in a non-null list context as:

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE region_code IN ('HN', 'HCM')
ORDER BY order_id;
```

The result is orders **1, 2, 3, 6**. However, `IN` cannot replace every `OR`: the expression `region_code = 'HN' OR amount >= 500` involves **two different columns and two different conditions**, and cannot be collapsed into `region_code IN (...)` with the same meaning.

### 5.2. OR Truth Table with TRUE/FALSE

| A | B | `A OR B` |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | TRUE |
| FALSE | TRUE | TRUE |
| FALSE | FALSE | FALSE |

In applications, `OR` often expresses **multiple valid paths**: the user is an administrator **or** the order creator; the row has status `NEW` **or** `PAID`; the record belongs to group A **or** exceeds a priority threshold. Security-sensitive expressions must use parentheses carefully so one `OR` branch never bypasses shared constraints.

## 6. Logical Operator NOT: Negating a Condition

`NOT` inverts the logical value of a condition:

- `NOT TRUE` becomes `FALSE`.
- `NOT FALSE` becomes `TRUE`.
- `NOT UNKNOWN` remains **`UNKNOWN`**.

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE NOT (order_status = 'CANCELLED')
ORDER BY order_id;
```

Because `ORDER_STATUS` is `NOT NULL`, the result is equivalent to:

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE order_status <> 'CANCELLED'
ORDER BY order_id;
```

Both exclude order **4**. Parentheses clarify the scope of `NOT` and reduce confusion in complex expressions.

### 6.1. Negating a Group of Conditions

```sql
SELECT order_id, order_status, amount
FROM lab_where_orders
WHERE NOT (order_status = 'NEW' AND amount < 300)
ORDER BY order_id;
```

The excluded group is **orders that are both `NEW` and under 300**: orders **1** and **5**. All remaining orders are kept, including order **6** which is `NEW` but has `AMOUNT = 1000`.

By **De Morgan's laws** in SQL three-valued logic, the expression can be transformed as:

```sql
NOT (A AND B)  is equivalent to  (NOT A) OR (NOT B)
NOT (A OR B)   is equivalent to  (NOT A) AND (NOT B)
```

In the example SQL:

```sql
WHERE NOT (order_status = 'NEW' AND amount < 300)
```

is logically equivalent to:

```sql
WHERE order_status <> 'NEW' OR amount >= 300
```

Because both columns are `NOT NULL`, the example result is straightforward. With nullable columns, the laws still hold under three-valued logic, but **the `UNKNOWN` case must not be ignored**.

## 7. Operator Precedence: NOT, AND, OR, and Parentheses

Oracle evaluates **comparison operators/conditions** to produce logical values, then applies logical operators in an important precedence order:

```text
   Highest precedence
          |
     Comparisons / conditions (e.g. =, >=, LIKE, IN, ...)
          |
         NOT
          |
         AND
          |
          OR
          |
   Lowest precedence
```

**Parentheses `(...)` group expressions to explicitly control combination order**, and should always be used when a `WHERE` clause mixes `AND` and `OR`.

### 7.1. A Dramatic Difference Caused by Missing Parentheses

```sql
SELECT order_id, order_status, amount
FROM lab_where_orders
WHERE order_status = 'NEW'
   OR order_status = 'PAID' AND amount >= 400
ORDER BY order_id;
```

Because `AND` has higher precedence than `OR`, Oracle interprets this equivalently to:

```sql
WHERE order_status = 'NEW'
   OR (order_status = 'PAID' AND amount >= 400)
```

The result is **1, 3, 5, 6, 8**: every `NEW` order is selected, including orders 1 (150) and 5 (250); `PAID` orders are selected only if they reach 400.

If the business requirement is **orders that are `NEW` or `PAID`, but regardless of status must have `AMOUNT >= 400`**, you must write:

```sql
SELECT order_id, order_status, amount
FROM lab_where_orders
WHERE (order_status = 'NEW' OR order_status = 'PAID')
  AND amount >= 400
ORDER BY order_id;
```

The result is now **3, 6, 8**. Both queries are syntactically valid yet return **different** results. This is a dangerous class of bug because it can silently corrupt reports, authorization checks, or business calculations.

| `ORDER_ID` | Status | Amount | Without parentheses | With parentheses around `NEW OR PAID` |
|---:|---|---:|---|---|
| 1 | NEW | 150 | Keep | Drop |
| 3 | PAID | 500 | Keep | Keep |
| 5 | NEW | 250 | Keep | Drop |
| 6 | NEW | 1000 | Keep | Keep |
| 8 | PAID | 400 | Keep | Keep |

### 7.2. Parentheses to Preserve a Shared Condition

Suppose a multi-tenant system must filter all orders with `TENANT_ID = :tenant_id` in one of two statuses. The correct pattern is:

```sql
-- Conceptual example: this table must have a TENANT_ID column in a real schema.
SELECT order_id, order_status
FROM tenant_orders
WHERE tenant_id = :tenant_id
  AND (order_status = 'NEW' OR order_status = 'PAID');
```

If parentheses are omitted:

```sql
WHERE tenant_id = :tenant_id
  AND order_status = 'NEW'
   OR order_status = 'PAID'
```

the condition is equivalent to `(tenant_id = :tenant_id AND order_status = 'NEW') OR order_status = 'PAID'`. It can select **every PAID order belonging to other tenants**. Here a missing parenthesis bug is not just wrong output—it can become a **cross-tenant data isolation breach**. Even when using RLS/VPD or database authorization mechanisms, application predicates must still be structured properly; never treat an unparenthesized `OR` condition as harmless.

### 7.3. Do Not Rely on Written Order to Force Oracle to Run One Check First

Logically we read left to right, but SQL is a declarative language; **the Oracle optimizer can rewrite, push down, or reorder predicate evaluation**. Do not rely on textual "short-circuiting" to prevent division by zero:

```sql
-- Do not assume the first condition is guaranteed to be evaluated first:
-- WHERE denominator <> 0 AND numerator / denominator > 10
```

When division by zero must be avoided in an expression, you can use `NULLIF`:

```sql
-- Conceptual example on a table with NUMERATOR and DENOMINATOR.
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM lab_ratios
WHERE numerator / NULLIF(denominator, 0) > 10;
```

When `DENOMINATOR = 0`, `NULLIF` returns `NULL`; dividing by `NULL` yields `NULL` and the `> 10` condition becomes `UNKNOWN`, so the row is not selected. This query only illustrates a safe strategy; table `LAB_RATIOS` is not part of the lab dataset created above.

## 8. NULL and Three-Valued Logic: Essential for Using WHERE Properly

In Oracle SQL, `NULL` represents an **unknown or unprovided value**, not zero, the string `'NULL'`, or an automatic `FALSE`.

For example, the lab table has two orders **5** and **8** with unknown `REGION_CODE`:

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE region_code IS NULL
ORDER BY order_id;
```

The result is **5 and 8**. Meanwhile:

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE region_code = NULL;
```

returns neither row, because comparing `= NULL` evaluates to **`UNKNOWN`**, not `TRUE`. Likewise, `region_code <> NULL` is not a valid way to retrieve all rows with a known region.

### 8.1. `IS NULL` and `IS NOT NULL`

```sql
-- Select rows without a region code.
SELECT order_id FROM lab_where_orders
WHERE region_code IS NULL;

-- Select rows with a region code.
SELECT order_id FROM lab_where_orders
WHERE region_code IS NOT NULL;
```

The results are **5, 8** and **1, 2, 3, 4, 6, 7**, respectively. `IS NULL` and `IS NOT NULL` are **conditions**, not value-assignment operators.

### 8.2. Why Doesn't `<>` Include NULL Rows?

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE region_code <> 'HN'
ORDER BY order_id;
```

Result: **2, 4, 6, 7**. Rows with `REGION_CODE = NULL` are excluded, even though in everyday speech one might say "if the region is unknown, it is not HN." In SQL, when the region is unknown, Oracle **cannot affirm** whether it differs from `'HN'` or equals `'HN'`.

If business logic wants **all rows not recorded as HN**, including rows without a region yet, write it explicitly:

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE region_code <> 'HN'
   OR region_code IS NULL
ORDER BY order_id;
```

The result is **2, 4, 5, 6, 7, 8**. This query has a different business meaning from the first one; do not blindly add `OR ... IS NULL` if the real system intends to exclude unknown data.

### 8.3. Three-Valued Truth Table for AND and OR

| A | B | `A AND B` | `A OR B` |
|---|---|---|---|
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | TRUE | FALSE | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | TRUE | UNKNOWN | TRUE |
| UNKNOWN | FALSE | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

In Oracle, *UNKNOWN* arises from an indeterminate logical outcome caused by `NULL` in a condition. Mnemonic:

- `FALSE AND UNKNOWN` is still **FALSE**, because the whole expression can never be true.
- `TRUE OR UNKNOWN` is still **TRUE**, because at least one side is already true.
- `TRUE AND UNKNOWN` is **UNKNOWN**.
- `FALSE OR UNKNOWN` is **UNKNOWN**.
- `NOT UNKNOWN` remains **UNKNOWN**.

### 8.4. `NOT` Does Not Turn NULL into TRUE

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE NOT (region_code = 'HN')
ORDER BY order_id;
```

The result matches `region_code <> 'HN'`: **2, 4, 6, 7**. `NOT (NULL = 'HN')` remains **UNKNOWN**, not TRUE. To include NULLs, you must add `OR region_code IS NULL` or express the business rule equivalently.

### 8.5. Empty Strings in Oracle

In standard Oracle versions, a zero-length character string (`''`) in SQL is generally treated as `NULL` for the corresponding character types. Thus, for a `VARCHAR2` column, an input value `''` can become `NULL` and fail `column = ''`, contrary to what beginners expect. To find missing values, use `IS NULL` and **clearly define empty/absent data semantics in the application**; do not design business rules assuming empty strings and null are always distinct in Oracle.

## 9. Conditions Commonly Used with WHERE: BETWEEN, IN, LIKE

While the focus is comparison operators and `AND`/`OR`/`NOT`, Oracle also provides **convenience conditions** that often make filter expressions easier to read.

### 9.1. BETWEEN: Inclusive Range on Both Ends

```sql
SELECT order_id, amount
FROM lab_where_orders
WHERE amount BETWEEN 200 AND 500
ORDER BY order_id;
```

For non-null numeric values, the condition is equivalent to:

```sql
WHERE amount >= 200 AND amount <= 500
```

Result: **2, 3, 5, 8**. **`BETWEEN` is inclusive on both endpoints**: order 3 with `AMOUNT = 500` is selected. For `DATE` values with time components, `BETWEEN DATE '2026-11-01' AND DATE '2026-11-30'` only covers up to **00:00:00** on Nov 30 at the upper bound, not the entire day; therefore, date-range filters should typically use `>= start AND < next_day` to avoid losing rows later in the final day.

### 9.2. IN: Membership in a Set of Choices

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE order_status IN ('NEW', 'PAID')
ORDER BY order_id;
```

The result is all orders except order **4** (`CANCELLED`). This is equivalent to:

```sql
WHERE order_status = 'NEW' OR order_status = 'PAID'
```

on the non-null sample data. Combined with additional conditions:

```sql
SELECT order_id, amount
FROM lab_where_orders
WHERE order_status IN ('NEW', 'PAID')
  AND amount >= 400
ORDER BY order_id;
```

Result: **3, 6, 8**. Using `IN` clarifies the group of statuses and avoids repeating multiple `OR` branches on the same column.

### 9.3. NOT IN and the NULL Trap

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE order_status NOT IN ('CANCELLED')
ORDER BY order_id;
```

Because the list contains no `NULL` and `ORDER_STATUS` is non-null, this selects all orders except order **4**. However:

```sql
-- Do not use this to exclude a status on real data:
SELECT order_id
FROM lab_where_orders
WHERE order_status NOT IN ('CANCELLED', NULL);
```

**returns no rows at all on the sample data**. Explanation: `x NOT IN (a, NULL)` is logically equivalent to `x <> a AND x <> NULL`. When `x <> a` is TRUE, the second part is still UNKNOWN, making the whole condition UNKNOWN; when `x = a`, the whole condition is FALSE. No row evaluates to TRUE.

This trap is especially dangerous when `NOT IN` uses a **subquery that might return NULL**:

```sql
-- Conceptual example: table EXCLUDED_CUSTOMERS is not in the lab.
SELECT customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT e.customer_id
    FROM excluded_customers e
);
```

If the subquery yields even one `NULL` value, rows can be unexpectedly excluded. You can filter `WHERE e.customer_id IS NOT NULL` inside the subquery if appropriate for business rules, or consider **`NOT EXISTS`** with a well-defined correlated join. `NOT EXISTS` has existence-checking semantics that differ from `NOT IN`, especially when keys can be null; inspect the data and intent before substituting.

### 9.4. LIKE: Pattern Matching on Characters

```sql
SELECT order_id, customer_name
FROM lab_where_orders
WHERE customer_name LIKE 'G%';
```

In the sample data, this finds **Giang (order 6)** matching a pattern starting with `G`. Two common wildcards:

- `%`: a string of zero or more characters.
- `_`: a **single** character.

Examples:

```sql
WHERE customer_name LIKE 'A%'   -- name starts with A
WHERE customer_name LIKE '_a%'  -- second character is a
WHERE customer_name NOT LIKE 'G%' -- name does not match pattern G%
```

With a nullable column, `NOT LIKE` can also return UNKNOWN if the value is NULL. `%` and `_` are wildcards in `LIKE`; to match a **literal** `%` or `_` character, use the `ESCAPE` clause in Oracle syntax:

```sql
-- Conceptual example on a products table with a PRODUCT_CODE column.
SELECT product_code
FROM lab_products
WHERE product_code LIKE 'AB\_%' ESCAPE '\';
```

This pattern finds codes starting with literal `AB_`, followed by anything else. Results depend on collation and actual data; table `LAB_PRODUCTS` is not part of the dataset created in section 2.

## 10. Applying AND, OR, NOT to Real Business Scenarios

### 10.1. Orders Requiring Priority Handling

Requirement: "Get orders in region HCM **that are** (priority orders **or** worth at least 500)."

```sql
SELECT order_id, region_code, amount, is_priority
FROM lab_where_orders
WHERE region_code = 'HCM'
  AND (is_priority = 1 OR amount >= 500)
ORDER BY order_id;
```

In the sample, region HCM has orders 2 and 6. Order 2 is not priority and is only 350, so it is dropped; order **6** is kept because it is in HCM and has amount 1000 and `IS_PRIORITY = 1`. This expression follows the exact structure **`A AND (B OR C)`**.

### 10.2. Uncancelled Orders Meeting a Threshold

```sql
SELECT order_id, order_status, amount
FROM lab_where_orders
WHERE order_status <> 'CANCELLED'
  AND amount >= 250
ORDER BY order_id;
```

The result is orders **2, 3, 5, 6, 8**. Writing `<> 'CANCELLED'` may match additional statuses beyond `NEW`/`PAID` if the system later adds `REFUNDED`, `SUSPENDED`, or other states. If business logic allows only two statuses, use **`IN ('NEW', 'PAID')`** rather than negating a single status.

### 10.3. Orders Needing Region Verification or Still Unpaid

Requirement: "Find orders missing a region code **or** still `NEW`."

```sql
SELECT order_id, region_code, order_status
FROM lab_where_orders
WHERE region_code IS NULL
   OR order_status = 'NEW'
ORDER BY order_id;
```

Result: **1, 5, 6, 8**. Order 5 satisfies both branches yet appears once; order 8 is kept because it lacks a region code even though its status is PAID.

### 10.4. Selecting Orders Within an Eligible Date Window and Status

```sql
SELECT order_id, created_on, order_status, amount
FROM lab_where_orders
WHERE created_on >= DATE '2026-11-03'
  AND created_on <  DATE '2026-11-08'
  AND order_status IN ('NEW', 'PAID')
ORDER BY created_on;
```

In the sample data, this window covers **Nov 03 up to before Nov 08**. Order 4 is excluded because it is CANCELLED. The result is **3, 5, 6, 7**. Half-open bounds ensure the query stays accurate even when a day contains multiple timestamps.

## 11. WHERE with Bind Parameters in Java/JDBC

In Java applications, filter thresholds often come from API requests or search screens. Never concatenate user input directly into SQL strings; use **bind parameters** (`?` in JDBC or `:name` in some tools/frameworks) to keep **data** separate from **SQL syntax**, support cursor reuse, and reduce SQL injection risk.

### 11.1. PreparedStatement with AND

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderSearch {
    public static void printPaidOrders(Connection connection,
                                       BigDecimal minAmount) throws SQLException {
        String sql = """
            SELECT order_id, customer_name, amount
            FROM lab_where_orders
            WHERE order_status = ?
              AND amount >= ?
            ORDER BY order_id
            """;

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, "PAID");
            statement.setBigDecimal(2, minAmount);

            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    System.out.printf("Order %d: %s, %s%n",
                        result.getLong("order_id"),
                        result.getString("customer_name"),
                        result.getBigDecimal("amount"));
                }
            }
        }
    }
}
```

This example uses a **Java text block** (Java 15+) and a compatible Oracle JDBC driver. On older Java versions, you can assemble the string by concatenating **fixed SQL fragments**, while still passing user values as binds. `BigDecimal` is preferred over binary floating-point types for monetary amounts requiring decimal precision.

### 11.2. Optional Parameters and Dynamic Conditions

Suppose an API allows searching orders by `minAmount` or `regionCode`, and both filters are optional. There are two common approaches:

1. **Conditionally build the SQL**, appending a predicate only when the parameter is provided while always binding values; manage placeholder positions carefully.
2. Use an optional predicate such as `(:region IS NULL OR region_code = :region)` if the framework supports named binds and you have verified the execution plan; this is convenient, though not always optimal for performance.

Conceptual Oracle SQL example:

```sql
SELECT order_id, region_code, amount
FROM lab_where_orders
WHERE (:min_amount IS NULL OR amount >= :min_amount)
  AND (:region IS NULL OR region_code = :region)
ORDER BY order_id;
```

**Note:** when `:region` is `NULL`, the second condition acts as "no region filter applied," so it includes rows where `REGION_CODE IS NULL`. That **differs** from "find only orders whose region is NULL." Define an API convention to distinguish an **omitted parameter** from a **user explicitly searching for blank fields**.

Bind parameters cannot substitute directly for column names or `ORDER BY` keywords as SQL identifiers. If the user chooses a sort column, the application must map allowed choices to **allowlisted SQL column names**, never concatenating arbitrary input into the query.

### 11.3. Bind Syntax in SQL Clients Other Than JDBC

In SQL*Plus/SQLcl, you can declare bind variables using the client's mechanism; in JDBC `PreparedStatement`, the placeholder is typically `?`. Many Java frameworks such as Spring JDBC allow named parameters (`:minAmount`). Placeholder syntax is a **client/framework interface**, while the semantics of `AND`, `OR`, `NOT`, and `NULL` are still governed by Oracle SQL.

## 12. WHERE, JOIN, and HAVING: Common Places Conditions Are Misplaced

### 12.1. WHERE Filters Rows; HAVING Filters Groups

```sql
SELECT order_status, COUNT(*) AS order_count
FROM lab_where_orders
WHERE amount >= 100
GROUP BY order_status
HAVING COUNT(*) >= 2
ORDER BY order_status;
```

This query uses `WHERE` to drop orders under 100 **before** grouping by status, and then uses `HAVING` to keep only groups with at least two rows. In the sample data, order 7 (90) is excluded from the groups. Do not use `WHERE COUNT(*) >= 2` as a row-level filter; aggregate expressions belong in the proper context, typically `HAVING`.

### 12.2. WHERE vs. OUTER JOIN ON Conditions

Suppose `CUSTOMERS` and `ORDERS` are two business tables, and we want every customer, even customers without paid orders. With `LEFT JOIN`, placing the status filter in `ON` behaves differently from placing it in `WHERE`:

```sql
-- Conceptual example with pre-created CUSTOMERS and ORDERS tables.
SELECT c.customer_id, o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID';
```

The snippet above keeps customers who have no `PAID` orders, with columns from `o` set to `NULL`. However:

```sql
SELECT c.customer_id, o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.order_status = 'PAID';
```

eliminates rows where `o.order_status` is `NULL` due to an unmatched right side. With that condition, the result resembles filtering for customers who already have PAID orders rather than preserving every customer. When moving predicates between `ON` and `WHERE`, inspect the JOIN type and `NULL` behavior—not just whether the syntax runs.

### 12.3. SELECT Aliases Cannot Be Used Arbitrarily in WHERE

Example:

```sql
SELECT amount * 1.1 AS adjusted_amount
FROM lab_where_orders
WHERE amount > 300;
```

In standard Oracle SQL, you cannot assume the `ADJUSTED_AMOUNT` alias just declared in the `SELECT` list can be used immediately in the same `WHERE` clause. To filter by an expression, repeat the expression when appropriate or place it in a **subquery/CTE** and filter in the outer query:

```sql
SELECT order_id, adjusted_amount
FROM (
    SELECT order_id, amount * 1.1 AS adjusted_amount
    FROM lab_where_orders
)
WHERE adjusted_amount > 300;
```

Multiplying by `1.1` here only illustrates aliases/expressions; real monetary calculations must apply exact units, taxes, and business rounding rules.

## 13. Performance Impact of Combining Multiple Conditions

`WHERE` only describes **which records are selected**; it does not command Oracle to use a fixed physical algorithm. The optimizer may choose a full table scan, index range scan, index unique scan, predicate combination, or expression transformation depending on statistics, table size, indexes, and parameters. A logically valid SQL query can still consume high CPU/I/O if no suitable access path exists.

### 13.1. Predicates That Can Typically Leverage an Index

Suppose there is a suitable index on `CREATED_ON`:

```sql
SELECT order_id, created_on
FROM lab_where_orders
WHERE created_on >= DATE '2026-11-01'
  AND created_on <  DATE '2026-12-01';
```

A range condition on the **bare column** generally gives Oracle an opportunity to use an index range scan if the optimizer finds it beneficial. In contrast:

```sql
-- Can hinder using a standard B-tree index on CREATED_ON:
SELECT order_id
FROM lab_where_orders
WHERE TRUNC(created_on) = DATE '2026-11-03';
```

wraps the column in `TRUNC`, changing the predicate shape. Oracle can use a **function-based index** or certain transformations under specific conditions, but **do not assume** a regular index on `CREATED_ON` will be used as cleanly as with a half-open range. For date-based filtering, writing `>= start AND < next_day` is easier to reason about and friendlier to standard indexing strategies.

### 13.2. OR Can Have More Complex Access Paths Than AND

```sql
WHERE region_code = 'HN' OR order_status = 'NEW'
```

The two branches may match different indexes. Oracle may pick a full scan, OR expansion, or another cost-based plan; **`OR` does not automatically mean slow**, nor does it guarantee separate index usage. Do not blindly rewrite `OR` as `UNION ALL` without considering duplicates: a row satisfying both branches would appear twice with `UNION ALL`, changing the semantics of an `OR` condition on a single table.

### 13.3. NOT and Negated Expressions

Predicates such as `<>`, `NOT IN`, `NOT LIKE`, or `NOT (...)` may select most of the table, making a full scan reasonable. There is no rule saying "having an index makes every `NOT` query fast"; you must examine **selectivity** (how many rows are kept), data distribution, and the actual plan. Frequently filtered columns should be evaluated against read/write workload rather than indexed blindly just because they appear in `WHERE`.

### 13.4. Avoid Unclear Implicit Type Conversions

```sql
-- The AMOUNT column is NUMBER; bind the proper numeric type:
WHERE amount >= :min_amount
```

If an application passes the string `'300'` instead of the number 300, Oracle may perform an implicit conversion. This depends on context, NLS, and data; it can cause number conversion errors or unexpected plans. For `DATE`, passing unformatted date strings is even more error-prone due to `NLS_DATE_FORMAT`. Use **typed bind parameters**, `DATE 'YYYY-MM-DD'`, `TO_DATE(..., format_mask)` when string parsing is truly required, or properly typed date/time APIs from Java.

### 13.5. Inspect the Execution Plan When Needed

If a large query runs slowly, start by checking the SQL text, binds, returned row count, and existing indexes. Authorized users can inspect explain plans or cursor plans to see which access path Oracle chose. Plan analysis is not the sole proof of correctness: **a wrong condition can still use an index very quickly**. Always verify business meaning and correctness before optimizing.

## 14. Common Mistakes with WHERE and Logical Operators

| Incorrect syntax / assumption | Problem | How to fix |
|---|---|---|
| `WHERE amount == 100` | `==` is syntax from other languages, not standard SQL comparison | Use `amount = 100` |
| `WHERE region_code = NULL` | Comparing against `NULL` yields `UNKNOWN` | Use `IS NULL` |
| `WHERE region_code <> 'HN'` expecting to include unknown regions | Rows with `NULL` are excluded | If business logic intends it, add `OR region_code IS NULL` |
| `A OR B AND C` when `(A OR B) AND C` was intended | `AND` has higher precedence than `OR` | Write explicit parentheses |
| `WHERE NOT region_code = 'HN'` assumed to keep NULLs | `NOT UNKNOWN` is still UNKNOWN | Distinguish `<>`, `IS NULL`, and NOT scope |
| `WHERE amount BETWEEN 100 AND 200` assuming endpoints are excluded | `BETWEEN` includes 100 and 200 | Use `>`/`<` for open bounds |
| `NOT IN (subquery)` where subquery returns `NULL` | Can unexpectedly filter out all rows | Filter nulls in subquery or use `NOT EXISTS` with proper semantics |
| `WHERE date_column = DATE '2026-11-03'` to match a full day | DATE may hold hours, minutes, seconds | Filter `>=` start of day and `<` start of next day |
| `WHERE amount > '100'` relying on strings | May trigger implicit conversion | Use numeric values and typed binds |
| Placing an `OR` branch outside the tenant condition | Can leak another tenant's data | Group choices with parentheses, then `AND` the tenant filter |
| Blindly rewriting `OR` as `UNION ALL` | Can duplicate rows satisfying both conditions | Check set semantics and duplicates |
| Assuming `AND` evaluates the left side first | Optimizer may rewrite or push down predicates | Use safe expressions, such as dividing by `NULLIF` |
| Turning `NOT (A OR B)` into `NOT A OR NOT B` | Violates De Morgan's law | Correct form is `NOT A AND NOT B` |
| Filtering aggregates via `WHERE COUNT(*) > 2` | Wrong clause for aggregate predicates | Use `GROUP BY` + `HAVING` |

For syntax errors, Oracle may report various `ORA-009xx` codes depending on the exact SQL; **do not guess a fixed error code** without reading the full error message. By contrast, missing parentheses or mishandled `NULL`s usually **raise no error at all**, so test boundary data carefully.

## 15. Guided Hands-On Exercises

The exercises below use `LAB_WHERE_ORDERS` created in section 2. Run only on DEV/TEST and do not alter real data. After each query, determine the condition outcome for each row **before** checking the result; tracing `TRUE`/`FALSE`/`UNKNOWN` catches logic bugs even when SQL succeeds.

### Exercise 1 — Equality and Inequality

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE order_status = 'NEW'
ORDER BY order_id;
```

**Expected result:** orders **1, 5, 6**. Change `=` to `<>` to retrieve rows not in `NEW` status; because this column is non-null, the result is **2, 3, 4, 7, 8**.

### Exercise 2 — Value Ranges and Boundaries

```sql
SELECT order_id, amount
FROM lab_where_orders
WHERE amount > 250 AND amount <= 500
ORDER BY order_id;
```

**Expected result:** **2, 3, 8**. Order 5 is exactly 250 so it is excluded; order 3 is exactly 500 so it is kept. Try changing `> 250` to `>= 250` to observe the difference.

### Exercise 3 — Combining AND and OR with Parentheses

```sql
SELECT order_id, order_status, amount
FROM lab_where_orders
WHERE (order_status = 'NEW' OR order_status = 'PAID')
  AND amount >= 400
ORDER BY order_id;
```

**Expected result:** **3, 6, 8**. Remove the parentheses and compare to see how `NEW` rows below 400 get included.

### Exercise 4 — NULL Columns and Negation

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE NOT (region_code = 'HN')
ORDER BY order_id;
```

**Expected result:** **2, 4, 6, 7**, excluding 5 and 8 because `NOT UNKNOWN` remains UNKNOWN. Next, add `OR region_code IS NULL` to include the two rows missing a region code.

### Exercise 5 — IN, NOT IN, and NULL

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE order_status IN ('NEW', 'PAID')
ORDER BY order_id;
```

**Expected result:** all orders except **4**. Explain why `NOT IN ('CANCELLED', NULL)` cannot replace a valid status filter.

### Exercise 6 — Checking a Date Range

```sql
SELECT order_id, created_on
FROM lab_where_orders
WHERE created_on >= DATE '2026-11-05'
  AND created_on <  DATE '2026-11-08'
ORDER BY order_id;
```

**Expected result:** **5, 6, 7**. Explain why 8 is excluded and why using `<` for the upper bound is beneficial when data includes time components.

### Exercise 7 — Negating a Group of Conditions

Requirement: "Get all orders except `NEW` orders with an amount below 300." Write both forms:

```sql
-- Method 1: NOT wrapping the entire group.
SELECT order_id
FROM lab_where_orders
WHERE NOT (order_status = 'NEW' AND amount < 300)
ORDER BY order_id;

-- Method 2: Applying De Morgan's law.
SELECT order_id
FROM lab_where_orders
WHERE order_status <> 'NEW' OR amount >= 300
ORDER BY order_id;
```

**Expected result for both:** **2, 3, 4, 6, 7, 8**. Excluded rows are 1 and 5.

### Exercise 8 — Translating Business Language into Conditions

Requirement: "Find orders in HN or HCM, with amount at least 300, and not in `CANCELLED` status." One way to write it:

```sql
SELECT order_id, region_code, amount, order_status
FROM lab_where_orders
WHERE region_code IN ('HN', 'HCM')
  AND amount >= 300
  AND order_status <> 'CANCELLED'
ORDER BY order_id;
```

**Expected result:** **2, 3, 6**. Rewrite `IN` using `OR` while keeping parentheses:

```sql
WHERE (region_code = 'HN' OR region_code = 'HCM')
  AND amount >= 300
  AND order_status <> 'CANCELLED'
```

Intentionally remove the parentheses, then explain why the shared conditions no longer apply to every `OR` branch.

### Cleaning Up Practice Data

Once you confirm this is the dummy table **you created in the right DEV/TEST schema**, and no other practice exercise shares it, you can clean up with:

```sql
DROP TABLE lab_where_orders PURGE;
```

`DROP TABLE ... PURGE` deletes the table and data, skips the recycle bin, and is a DDL operation with an implicit commit. **Do not run on production**, and do not run if the table name conflicts with a resource outside the lab scope.

## 16. Review Questions

**Question 1.** Does `WHERE amount >= 100 AND amount <= 200` include the values 100 and 200?

**Answer:** Yes. Both `>=` and `<=` include the boundary values; this can also be written as `BETWEEN 100 AND 200` when appropriate.

**Question 2.** Is `A OR B AND C` equivalent to `(A OR B) AND C` or `A OR (B AND C)`?

**Answer:** `A OR (B AND C)`, because `AND` has higher precedence than `OR`.

**Question 3.** With `REGION_CODE = NULL`, is `REGION_CODE <> 'HN'` TRUE, FALSE, or UNKNOWN?

**Answer:** `UNKNOWN`. The row is not selected by `WHERE` unless another branch makes the overall expression TRUE.

**Question 4.** Two rows have `REGION_CODE IS NULL`; how do you retrieve only those rows?

**Answer:** `WHERE region_code IS NULL`, not `region_code = NULL`.

**Question 5.** What is `NOT (A OR B)` equivalent to?

**Answer:** `(NOT A) AND (NOT B)`. This is De Morgan's law; it must not be turned into `(NOT A) OR (NOT B)`.

**Question 6.** Can `WHERE status NOT IN ('NEW', NULL)` select `PAID` rows?

**Answer:** Not as expected. Because the list contains `NULL`, the `status <> NULL` part is `UNKNOWN`; rows that do not match `'NEW'` evaluate overall to `UNKNOWN` and are dropped.

**Question 7.** An `ORDERS` table stores `CREATED_ON` as a `DATE` with time components. How do you select the entire day of Nov 03, 2026?

**Answer:** `created_on >= DATE '2026-11-03' AND created_on < DATE '2026-11-04'` is the clear half-open range approach.

**Question 8.** Why is placing `AND denominator <> 0` before division in `WHERE` not a reliable guard against division by zero?

**Answer:** Because the optimizer can rewrite predicate evaluation order. Use a safe expression such as dividing by `NULLIF(denominator, 0)` when appropriate.

**Question 9.** Why can a mis-parenthesized `OR` condition be dangerous in a multi-tenant application?

**Answer:** An `OR` branch can bypass the `TENANT_ID` filter, causing the query to return another tenant's data. Group the choices in parentheses and then apply the tenant restriction to the whole expression.

**Question 10.** Can we claim every `WHERE col = value` query will use an index?

**Answer:** No. The Oracle optimizer decides the plan based on cost, indexes, statistics, and data volume. Filter correctness and query performance are related but distinct concerns.

## Conclusion

**`WHERE` filters rows whose condition evaluates to `TRUE`**. Comparison operators (`=`, `<>`, `>`, `>=`, `<`, `<=`) express relationships between values; `AND` requires every condition to be true, `OR` requires at least one condition to be true, and `NOT` negates a logical expression. When combining them, **`NOT` takes precedence over `AND`, and `AND` takes precedence over `OR`**, so always use parentheses to capture business rules accurately.

An essential point in Oracle SQL is that **`NULL` leads to `UNKNOWN`**, not automatically `FALSE`: `= NULL` and `<> NULL` do not test for missing data, `NOT UNKNOWN` remains UNKNOWN, and `NOT IN` with a `NULL` element can unexpectedly produce an empty result. Use `IS NULL`, `IS NOT NULL`, explicit half-open date ranges, properly typed bind parameters, and test with both normal values and edge cases. A good `WHERE` clause must get the **data right first**, and only then be tuned with an appropriate execution plan and indexes.
