# `IS NULL`, `IS NOT NULL`, and `UNKNOWN` Outcomes in Oracle SQL

## 1. Why Understanding `NULL` Matters When Writing SELECT

A customer table may lack an email address, an unpaid order may lack `paid_at`, or an employee may not yet be assigned to a department. In Oracle Database, these cases of no known value are typically represented by **`NULL`**.

`NULL` introduces an essential distinction in SQL queries: it is not an ordinary value to compare with `=` or `<>`. When a comparison has `NULL` as an operand, the outcome is usually **`UNKNOWN`**. For that reason, the following statements do not mean the same thing:

```sql
-- Wrong if the goal is to find rows where email is NULL:
SELECT customer_id, email
FROM customers
WHERE email = NULL;

-- Correct:
SELECT customer_id, email
FROM customers
WHERE email IS NULL;
```

Likewise, to find rows that have a value, use `IS NOT NULL`, not `<> NULL`.

In this lesson in the **SELECT Basics** chapter, you will learn:

- What `NULL` represents and how it differs from `0`, spaces, or ordinary strings.
- How to use `IS NULL` and `IS NOT NULL`.
- Why SQL has three logical outcomes: `TRUE`, `FALSE`, and `UNKNOWN`.
- How `WHERE`, `HAVING`, `CASE`, `AND`, `OR`, and `NOT` handle `UNKNOWN`.
- Common traps with `NOT IN`, `JOIN`, aggregate functions, and optional conditions.
- How to write clear queries when a Java application's input parameter may be `null`.

Examples use `DUAL` or illustrative tables. If tables such as `CUSTOMERS`, `ORDERS`, or `EMPLOYEES` do not exist in your practice schema, substitute corresponding tables you have permission to read.

## 2. `NULL` Means No Known Value

`NULL` can represent data that is not yet provided, unknown, not applicable, or undetermined. The exact business meaning depends on each column.

| Data | Example | Possible meaning |
|---|---|---|
| Payment amount | `paid_amount = NULL` | Payment amount has not been recorded yet |
| Completion date | `completed_at = NULL` | Task is not finished or completion time is unrecorded |
| Email | `email = NULL` | User has not provided an email |
| Department ID | `department_id = NULL` | Employee has not been assigned a department |
| Quantity | `quantity = 0` | Quantity is known to be zero |

**`NULL` is not synonymous with 0.** Zero is a specific numeric value, whereas NULL indicates no known value.

### 2.1. Distinguishing NULL, 0, and Spaces

```sql
SELECT CASE WHEN CAST(NULL AS NUMBER) IS NULL
            THEN 'NULL' ELSE 'NOT NULL' END AS null_value,
       CASE WHEN 0 IS NULL
            THEN 'NULL' ELSE 'NOT NULL' END AS zero_value,
       CASE WHEN ' ' IS NULL
            THEN 'NULL' ELSE 'NOT NULL' END AS space_value
FROM dual;
```

Meaning of results:

- `CAST(NULL AS NUMBER)` is NULL.
- `0` is a numeric value.
- `' '` is a string containing one space, not NULL.

In Oracle, a zero-length character string `''` is treated as NULL under current behavior for standard character types. Therefore:

```sql
SELECT CASE WHEN '' IS NULL THEN 'IS NULL'
            ELSE 'NOT NULL' END AS empty_string,
       CASE WHEN ' ' IS NULL THEN 'IS NULL'
            ELSE 'NOT NULL' END AS one_space
FROM dual;
```

An empty string and a string containing one space are not the same. If an application treats whitespace-only strings as missing input, normalize or check explicitly with `TRIM`; Oracle does not automatically treat whitespace strings as NULL.

### 2.2. Where Can NULL Come From?

A NULL value can originate from:

- A nullable column where an `INSERT` omitted the value.
- An `UPDATE` setting the column to NULL.
- An expression or function whose result is undefined.
- An outer join (`OUTER JOIN`) finding no matching row on the other side.
- An aggregate function or scalar subquery in cases with no matching input/output values.

Therefore, seeing NULL in a SELECT result does not always mean the underlying record stored NULL. It can also be produced by how the query combines data.

## 3. How to Test for NULL: `IS NULL` and `IS NOT NULL`

### 3.1. Finding Rows with NULL

Syntax:

```sql
expression IS NULL
```

Example:

```sql
SELECT customer_id, customer_name, email
FROM customers
WHERE email IS NULL;
```

The query returns customers whose `EMAIL` column is NULL.

### 3.2. Finding Non-NULL Rows

Syntax:

```sql
expression IS NOT NULL
```

Example:

```sql
SELECT customer_id, customer_name, email
FROM customers
WHERE email IS NOT NULL;
```

The query returns only customers with a non-NULL email value. This **does not guarantee the email is validly formatted**; a string of spaces is still non-NULL.

### 3.3. Checking Multiple Columns in One WHERE Clause

```sql
SELECT employee_id, first_name, phone_number, commission_pct
FROM employees
WHERE phone_number IS NULL
  AND commission_pct IS NOT NULL;
```

This example finds employees with no phone number recorded who do have a recorded commission percentage. `IS NULL` and `IS NOT NULL` evaluate deterministically to TRUE or FALSE, so they can be combined directly with `AND`, `OR`, and `NOT`.

### 3.4. Do Not Use `= NULL` or `<> NULL`

| Written | Result when column is NULL | Proper usage |
|---|---|---|
| `email = NULL` | `UNKNOWN` | `email IS NULL` |
| `email <> NULL` | `UNKNOWN` | `email IS NOT NULL` |
| `email != NULL` | `UNKNOWN` | `email IS NOT NULL` |
| `email IS NULL` | `TRUE` if email is NULL | Correct |
| `email IS NOT NULL` | `TRUE` if email is non-NULL | Correct |

A common pitfall is a SQL query running without any syntax error, yet returning zero rows. `WHERE email = NULL` is a classic example: the query is syntactically valid, but the condition never becomes TRUE even for rows whose email is NULL.

## 4. Three-Valued Logic: TRUE, FALSE, and UNKNOWN

In ordinary two-valued logic, an expression can only be TRUE or FALSE. SQL adds **UNKNOWN** to represent cases where truth cannot be determined, usually because NULL participates in a calculation or comparison.

Example:

```sql
SELECT CASE WHEN 10 > 5 THEN 'TRUE'
            ELSE 'NOT TRUE' END AS known_true,
       CASE WHEN 10 < 5 THEN 'TRUE'
            ELSE 'NOT TRUE' END AS known_false,
       CASE WHEN CAST(NULL AS NUMBER) > 5 THEN 'TRUE'
            ELSE 'NOT TRUE' END AS unknown_result
FROM dual;
```

Taking the `ELSE` branch in the last column does not mean the comparison was FALSE. It can be UNKNOWN. `CASE WHEN` selects a `THEN` branch only when the condition is TRUE.

### 4.1. Comparisons Involving NULL Usually Yield UNKNOWN

| Expression | Result |
|---|---|
| `5 = 5` | `TRUE` |
| `5 = 6` | `FALSE` |
| `5 = NULL` | `UNKNOWN` |
| `NULL = NULL` | `UNKNOWN` |
| `5 <> NULL` | `UNKNOWN` |
| `NULL > 0` | `UNKNOWN` |
| `NULL LIKE 'A%'` | `UNKNOWN` |
| `NULL BETWEEN 1 AND 10` | `UNKNOWN` |
| `NULL IS NULL` | `TRUE` |
| `NULL IS NOT NULL` | `FALSE` |

Special point: `NULL IS NULL` is a NULL-state test, not a comparison of two NULL values with `=`.

### 4.2. AND Truth Table

| A | B | `A AND B` |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| TRUE | UNKNOWN | UNKNOWN |
| FALSE | TRUE | FALSE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE |
| UNKNOWN | TRUE | UNKNOWN |
| UNKNOWN | FALSE | FALSE |
| UNKNOWN | UNKNOWN | UNKNOWN |

One FALSE side makes the entire AND expression FALSE, even if the other side is UNKNOWN.

### 4.3. OR Truth Table

| A | B | `A OR B` |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | TRUE |
| TRUE | UNKNOWN | TRUE |
| FALSE | TRUE | TRUE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | UNKNOWN |
| UNKNOWN | TRUE | TRUE |
| UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN |

One TRUE side makes the entire OR expression TRUE, even if the other side is UNKNOWN.

### 4.4. NOT UNKNOWN Remains UNKNOWN

| A | `NOT A` |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

This is why `NOT (salary > 10000)` does not automatically select rows where `salary IS NULL`. If `salary > 10000` is UNKNOWN, negating it stays UNKNOWN.

## 5. How Does WHERE Handle UNKNOWN?

In a SELECT statement, the `WHERE` clause keeps only rows whose condition is **TRUE**. Rows with FALSE or UNKNOWN are eliminated from the result.

Illustrative table:

| employee_id | salary |
|---:|---:|
| 101 | 12000 |
| 102 | 8000 |
| 103 | NULL |

Run:

```sql
SELECT employee_id, salary
FROM employees
WHERE salary > 10000;
```

Row-by-row evaluation:

| employee_id | Expression | Result | Included? |
|---:|---|---|---|
| 101 | `12000 > 10000` | TRUE | Yes |
| 102 | `8000 > 10000` | FALSE | No |
| 103 | `NULL > 10000` | UNKNOWN | No |

If the business requirement is "get employees whose salary does not exceed 10,000 **or who have no salary recorded yet**," write it explicitly:

```sql
SELECT employee_id, salary
FROM employees
WHERE salary <= 10000
   OR salary IS NULL;
```

Do not write:

```sql
-- Not equivalent to the condition above:
WHERE NOT (salary > 10000)
```

For the NULL salary row, the inner expression is UNKNOWN; `NOT UNKNOWN` remains UNKNOWN, so the row is dropped.

### 5.1. Negated Conditions Must Account for NULL

For example, to find orders that do not have status `CANCELLED`:

```sql
SELECT order_id, status
FROM orders
WHERE status <> 'CANCELLED';
```

This query does **not** return rows with `status IS NULL`, because `NULL <> 'CANCELLED'` is UNKNOWN. If the requirement includes unknown statuses:

```sql
SELECT order_id, status
FROM orders
WHERE status <> 'CANCELLED'
   OR status IS NULL;
```

However, verify the business meaning. If NULL means "status unverified," lumping it into "not cancelled" might skew reports. Correct SQL syntax alone is not enough; you must define how missing data is classified.

### 5.2. AND and OR with a Nullable Column

```sql
SELECT employee_id, salary, commission_pct
FROM employees
WHERE salary > 5000
  AND commission_pct > 0.1;
```

If `commission_pct` is NULL, the second condition is UNKNOWN. `TRUE AND UNKNOWN` is UNKNOWN, so the row is not selected.

If you want people earning over 5,000 **and having either commission over 10% or unrecorded commission**, write:

```sql
SELECT employee_id, salary, commission_pct
FROM employees
WHERE salary > 5000
  AND (commission_pct > 0.1 OR commission_pct IS NULL);
```

Use parentheses to express condition grouping clearly. `AND` has higher precedence than `OR`; omitting parentheses can cause the query to return unexpected rows.

## 6. UNKNOWN in CASE and Conditional Expressions

### 6.1. Searched CASE

`CASE WHEN` treats only a TRUE condition as a match:

```sql
SELECT employee_id,
       CASE
           WHEN salary > 10000 THEN 'HIGH'
           WHEN salary <= 10000 THEN 'NORMAL'
           ELSE 'UNKNOWN_OR_OTHER'
       END AS salary_group
FROM employees;
```

For `salary IS NULL`, both comparisons are UNKNOWN, so neither `WHEN` branch matches and `ELSE` is chosen.

To separate NULL into its own category, write it explicitly:

```sql
SELECT employee_id,
       CASE
           WHEN salary IS NULL THEN 'NOT_RECORDED'
           WHEN salary > 10000 THEN 'HIGH'
           ELSE 'NORMAL'
       END AS salary_group
FROM employees;
```

Branch order matters: checking NULL first makes intent clear and avoids relying on an indeterminate comparison to classify rows.

### 6.2. Simple CASE Is Not a Way to Check for NULL

Do not write:

```sql
CASE email
    WHEN NULL THEN 'MISSING'
    ELSE 'PRESENT'
END
```

Simple CASE compares the expression against each `WHEN` value using equality semantics; `email = NULL` is UNKNOWN, so the `WHEN NULL` branch does not match as intended.

Use searched CASE:

```sql
CASE
    WHEN email IS NULL THEN 'MISSING'
    ELSE 'PRESENT'
END
```

### 6.3. NVL, COALESCE, and NULLIF

NULL-handling functions can be helpful in SELECT:

```sql
SELECT employee_id,
       NVL(commission_pct, 0) AS commission_display,
       COALESCE(phone_number, email, 'NO_CONTACT') AS contact_display
FROM employees;
```

- `NVL(expr1, expr2)` returns `expr2` when `expr1` is NULL; otherwise returns `expr1`.
- `COALESCE(expr1, expr2, ...)` returns the first non-NULL expression.
- `NULLIF(expr1, expr2)` returns NULL if the two expressions are equal; otherwise returns `expr1`.

`NULLIF` example:

```sql
SELECT NULLIF(0, 0) AS result_value,
       NULLIF(5, 0) AS second_value
FROM dual;
```

Logical outcomes: the first expression returns NULL; the second returns 5.

**Be careful when filtering with NVL:** `NVL(salary, 0) > 10000` is not the same as `salary > 10000 OR salary IS NULL`; the first replaces NULL with 0, so NULL rows are dropped. Replace NULL with a default only when it matches business semantics.

## 7. The `NOT IN` Trap When a List Contains NULL

This is one of the most common SQL bugs.

### 7.1. `IN` and NULL

Suppose:

```sql
SELECT 20 IN (10, 20, NULL) AS result
FROM dual;
```

Because one element equals 20, the IN expression is TRUE.

However:

```sql
SELECT 30 IN (10, 20, NULL) AS result
FROM dual;
```

No element equals 30, and comparing against NULL produces UNKNOWN. The overall result is UNKNOWN, not FALSE.

### 7.2. Why Can NOT IN Return 0 Rows?

Example:

```sql
SELECT employee_id
FROM employees
WHERE department_id NOT IN (10, 20, NULL);
```

For `department_id` equal to 30, Oracle must evaluate equivalently to:

```text
30 <> 10 AND 30 <> 20 AND 30 <> NULL
TRUE     AND TRUE     AND UNKNOWN
                       |
                       v
                    UNKNOWN
```

The result is UNKNOWN, so WHERE eliminates that row. Rows with NULL `department_id` are not selected either. Thus, as soon as a NOT IN list contains NULL, non-matching values may fail to appear as expected.

### 7.3. How to Fix It

If the list comes from a child table, filter NULL out of the subquery result:

```sql
SELECT e.employee_id
FROM employees e
WHERE e.department_id NOT IN (
    SELECT d.department_id
    FROM blocked_departments d
    WHERE d.department_id IS NOT NULL
);
```

An often clearer alternative is `NOT EXISTS`:

```sql
SELECT e.employee_id
FROM employees e
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_departments d
    WHERE d.department_id = e.department_id
);
```

`NOT EXISTS` checks that no child row satisfies the correlated condition. It avoids the NULL trap inside the `NOT IN` subset. However, if `e.department_id` on the outer row is NULL, the correlated comparison is not TRUE for any row either; `NOT EXISTS` can then return TRUE. If business logic should exclude employees without a department, add:

```sql
AND e.department_id IS NOT NULL
```

Decide separately how NULL should be handled in the **outer dataset** and the **subquery dataset**.

## 8. NULL with Aggregate Functions

Aggregate functions generally ignore NULL values in the aggregated expression, while `COUNT(*)` counts every row.

| Expression | NULL handling |
|---|---|
| `COUNT(*)` | Counts all rows, including rows with NULL columns |
| `COUNT(column)` | Counts only rows where `column` is non-NULL |
| `SUM(column)` | Ignores NULL; if no non-NULL values exist, result is NULL |
| `AVG(column)` | Ignores NULL when computing the average |
| `MIN(column)`, `MAX(column)` | Ignores NULL when finding min/max |

Example with `EMPLOYEES`:

```sql
SELECT COUNT(*) AS total_employees,
       COUNT(commission_pct) AS employees_with_commission,
       AVG(commission_pct) AS average_commission
FROM employees;
```

`COUNT(*)` counts all employees; `COUNT(commission_pct)` counts only employees with a recorded commission rate. If half of the employees have no commission, `AVG` does not treat them as 0; it averages only the non-NULL values.

### 8.1. NULL Is Not Automatically Treated as 0 in SUM/AVG

Suppose there are three values:

```text
10, 20, NULL
```

Results:

- `SUM(value)` = 30.
- `AVG(value)` = 15.
- `COUNT(value)` = 2.
- `COUNT(*)` = 3.

If business logic treats missing values as 0, write it explicitly:

```sql
SELECT AVG(NVL(commission_pct, 0)) AS average_with_missing_as_zero
FROM employees;
```

This is a **different calculation** from `AVG(commission_pct)`. Never replace NULL with 0 just to avoid a NULL result without confirming the statistical meaning.

### 8.2. SUM on an Empty or All-NULL Set

```sql
SELECT COUNT(*) AS row_count,
       COUNT(CAST(NULL AS NUMBER)) AS non_null_count,
       SUM(CAST(NULL AS NUMBER)) AS total_value
FROM dual
WHERE 1 = 0;
```

With zero input rows: `COUNT(*)` returns 0, `COUNT(expr)` returns 0, while `SUM(expr)` returns NULL. Likewise, if rows exist but every value in the SUM expression is NULL, the sum can also be NULL.

To display 0 instead of a NULL sum:

```sql
SELECT NVL(SUM(amount), 0) AS total_amount
FROM payments;
```

Use this only when "no payments recorded" truly means displaying a total of 0. In reports, NULL can mean "no data yet," whereas 0 means "verified total of zero."

### 8.3. GROUP BY and NULL

`GROUP BY` puts rows with NULL values for the same grouping expression into a single group:

```sql
SELECT department_id,
       COUNT(*) AS employee_count
FROM employees
GROUP BY department_id
ORDER BY department_id NULLS LAST;
```

The result can include a NULL `DEPARTMENT_ID` group containing employees not yet assigned to a department. This does not contradict `department_id = NULL` being UNKNOWN: `GROUP BY` groups missing values according to its own grouping rules, not by filtering with `= NULL`.

## 9. NULL in JOINs

### 9.1. Equality JOIN Conditions Do Not Match Two NULLs

Suppose an employee table has a NULL `department_id` and a department table also has a row with NULL `department_id`. With the join:

```sql
SELECT e.employee_id, d.department_name
FROM employees e
JOIN departments d
  ON e.department_id = d.department_id;
```

The row with NULL `e.department_id` does not match the row with NULL `d.department_id`, because `NULL = NULL` is UNKNOWN, not TRUE.

If business rules genuinely treat two NULLs as matching keys, write an explicit null-safe rule, for example:

```sql
ON (
       e.department_id = d.department_id
    OR (e.department_id IS NULL AND d.department_id IS NULL)
)
```

Be cautious: if `DEPARTMENTS` has multiple NULL rows, that join could match one NULL employee to multiple rows and multiply output rows. Normally, NULL in a foreign key means "no department," so NULLs should not be joined to each other.

### 9.2. OUTER JOIN Produces NULL on the Unmatched Side

```sql
SELECT e.employee_id,
       e.department_id,
       d.department_name
FROM employees e
LEFT JOIN departments d
  ON d.department_id = e.department_id;
```

If an employee has no matching department, columns taken from `d` are returned as NULL. There are two distinct causes:

1. `e.department_id` is actually NULL.
2. `e.department_id` has a value, but no matching row exists in `departments` (if the data or constraints permit that).

To find employees with no matching department row, check a key column of the right table that is always non-NULL when a row exists:

```sql
SELECT e.employee_id
FROM employees e
LEFT JOIN departments d
  ON d.department_id = e.department_id
WHERE d.department_id IS NULL;
```

If `d.department_id` is a primary key (hence never NULL), this check detects unmatched rows. Note that the result may include employees whose `e.department_id` is NULL; to separate the two cases, also check the column in `e`.

### 9.3. Be Careful When Placing Right-Table Filters in WHERE

Compare:

```sql
-- LEFT JOIN, but WHERE eliminates unmatched rows:
SELECT e.employee_id, d.department_name
FROM employees e
LEFT JOIN departments d
  ON d.department_id = e.department_id
WHERE d.status = 'ACTIVE';
```

Unmatched rows have `d.status` NULL; `NULL = 'ACTIVE'` is UNKNOWN and is dropped by WHERE. The query behaves like an INNER JOIN with respect to that condition.

To keep all employees and only attach department details when the department is ACTIVE:

```sql
SELECT e.employee_id, d.department_name
FROM employees e
LEFT JOIN departments d
  ON d.department_id = e.department_id
 AND d.status = 'ACTIVE';
```

Filters on the right-side table belong in `ON` when the goal is to preserve left-side rows that have no matching right-side row.

## 10. NULL with BETWEEN, LIKE, IN, and Arithmetic

NULL can produce UNKNOWN across many condition types, not only `=`:

```sql
-- If salary is NULL, the BETWEEN condition is UNKNOWN.
WHERE salary BETWEEN 5000 AND 10000

-- If name is NULL, the LIKE condition is UNKNOWN.
WHERE customer_name LIKE 'A%'

-- If order_date is NULL, the date comparison is UNKNOWN.
WHERE order_date >= DATE '2026-01-01'

-- If amount is NULL, addition yields NULL.
SELECT amount + 100 FROM payments;
```

### 10.1. BETWEEN

```sql
SELECT product_id, price
FROM products
WHERE price BETWEEN 100 AND 500;
```

`BETWEEN` is semantically equivalent to `price >= 100 AND price <= 500`. If `price` is NULL, both comparisons are UNKNOWN; the row is dropped by WHERE.

### 10.2. LIKE

```sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_name LIKE 'Ng%';
```

A NULL name does not match the pattern and the condition is UNKNOWN. To display rows missing a name alongside names starting with `Ng`, add `OR customer_name IS NULL`.

### 10.3. IN and NOT IN

```sql
WHERE status IN ('NEW', 'PAID')
```

Rows with NULL status are excluded because the result is UNKNOWN. With `NOT IN`, always check whether the list can contain NULL, as explained in section 7.

### 10.4. Arithmetic Operations

```sql
SELECT amount + tax AS total
FROM invoice_lines;
```

If `amount` or `tax` is NULL, standard addition produces NULL. To treat NULL as 0:

```sql
SELECT NVL(amount, 0) + NVL(tax, 0) AS total
FROM invoice_lines;
```

This is a business decision. If NULL means "tax not yet calculated," substituting 0 can falsely signal in a report that the total is finalized.

## 11. ORDER BY and Placing NULL First or Last

Oracle lets you specify where NULLs appear when sorting:

```sql
SELECT employee_id, commission_pct
FROM employees
ORDER BY commission_pct ASC NULLS LAST;
```

Or:

```sql
SELECT employee_id, commission_pct
FROM employees
ORDER BY commission_pct DESC NULLS FIRST;
```

If omitted:

- `ASC` defaults to placing NULLs **after** other values (`NULLS LAST`).
- `DESC` defaults to placing NULLs **before** other values (`NULLS FIRST`).

Explicitly write `NULLS FIRST` or `NULLS LAST` when NULL placement matters to a report, avoiding reliance on defaults and making intent clear to readers.

## 12. Checking NULL in Java/JDBC Applications

A common mistake is the backend passing Java `null` to a bind parameter and expecting:

```sql
SELECT *
FROM customers
WHERE email = ?
```

to return rows where `EMAIL IS NULL`. That does not happen: when the bound parameter is SQL NULL, `email = NULL` evaluates to UNKNOWN.

### 12.1. To Find NULL Rows, Use IS NULL

When the application knows it is searching for NULL emails:

```sql
SELECT customer_id, email
FROM customers
WHERE email IS NULL;
```

Do not bind NULL into an `=` comparison.

### 12.2. To Match Email Against Input Including NULL

One option is choosing the SQL statement based on the parameter state:

```java
String sql;

if (email == null) {
    sql = "SELECT customer_id, email FROM customers WHERE email IS NULL";
} else {
    sql = "SELECT customer_id, email FROM customers WHERE email = ?";
}

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    if (email != null) {
        ps.setString(1, email);
    }

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process row.
        }
    }
}
```

This code illustrates the idea; it assumes `connection`, `email`, and transactions are already managed. Values must never be concatenated directly into SQL.

A SQL expression for null-safe equality:

```sql
WHERE email = :p_email
   OR (email IS NULL AND :p_email IS NULL)
```

If `:p_email` is NULL, the first branch is UNKNOWN while the second branch is TRUE when the column is also NULL; if the parameter has a value, the ordinary equality branch applies. In standard JDBC, placeholders are `?` and you bind each position accordingly; having two placeholders may require binding the same value twice.

### 12.3. Distinguish "NULL Parameter Means Skip Filter"

Another pattern:

```sql
WHERE (:p_email IS NULL OR email = :p_email)
```

This is commonly used for optional filters:

- If `:p_email` is NULL, the first side is TRUE, so **no email filter is applied**.
- If `:p_email` has a value, the query filters for emails equal to that value.

This is **not** null-safe equality. It does not mean "if the parameter is NULL, find rows with NULL email"; it means "if the parameter is NULL, skip the email condition."

Two distinct intents:

| Intent | How to express |
|---|---|
| NULL parameter means find rows where column is NULL | `email IS NULL` or null-safe equality |
| NULL parameter means do not apply filter | `:p_email IS NULL OR email = :p_email` |
| Non-NULL parameter means match that exact value | `email = :p_email` |

Name parameters and document APIs clearly so the frontend never sends NULL expecting one behavior while the backend implements the other.

### 12.4. JDBC setNull and Empty Strings

```java
if (email == null) {
    ps.setNull(1, java.sql.Types.VARCHAR);
} else {
    ps.setString(1, email);
}
```

`setNull` passes a SQL NULL value. The string `"null"` is four ordinary characters; the string `""` in Oracle is treated as NULL under current behavior for standard character types. If an API must distinguish "field omitted," "empty string sent," and "NULL sent," define a convention at the JSON/Java layer and handle it explicitly before writing to the database.

## 13. Common NULL Checks and Fallback Values

### 13.1. Checking One Column

```sql
SELECT COUNT(*) AS all_rows,
       COUNT(email) AS rows_with_email
FROM customers;
```

The difference between the two counts tells you how many rows have a NULL `email` in the same dataset, assuming no other filters.

### 13.2. Counting NULL and Non-NULL Separately

```sql
SELECT SUM(CASE WHEN email IS NULL THEN 1 ELSE 0 END) AS null_count,
       SUM(CASE WHEN email IS NOT NULL THEN 1 ELSE 0 END) AS not_null_count
FROM customers;
```

Or:

```sql
SELECT
    COUNT(*) - COUNT(email) AS null_count,
    COUNT(email) AS not_null_count
FROM customers;
```

### 13.3. Finding Empty Values Under Oracle Rules

Because `''` is treated as NULL for standard character types, you can use:

```sql
SELECT customer_id
FROM customers
WHERE email IS NULL;
```

To find whitespace-only strings:

```sql
SELECT customer_id, email
FROM customers
WHERE email IS NOT NULL
  AND TRIM(email) IS NULL;
```

`TRIM(email)` returns NULL when only an empty string remains after stripping default spaces. If you need to preserve or strip other Unicode whitespace characters, define explicit normalization rules; default `TRIM` does not clean every kind of whitespace character.

### 13.4. NVL in SELECT for Readability

```sql
SELECT customer_id,
       NVL(email, '(not provided)') AS email_display
FROM customers;
```

This substitution is **for display output only**. The underlying table column remains NULL; the query writes no default values to the data.

## 14. Performance and Indexes with IS NULL / IS NOT NULL

`IS NULL` and `IS NOT NULL` are ordinary SQL conditions; Oracle may choose a full table scan or index access depending on statistics, selectivity, index type, and the execution plan.

One notable detail: **a standard Oracle B-tree index does not store entries for rows where every indexed key column is NULL**. Therefore:

- A single-column B-tree index usually has no entries for rows where that column is NULL.
- A `WHERE col IS NULL` query may not be able to use a single-column B-tree index the way you might expect.
- A composite B-tree index can store an entry when at least one key component is non-NULL; thus its behavior differs from a single-column index where the entire key is NULL.
- Bitmap indexes and other index structures have different properties, and choosing them depends on the workload and environment.

Do not create an index merely because a query has `IS NULL`. First evaluate:

1. The proportion of NULL rows in the column.
2. Expected returned row count and selectivity.
3. Other filter columns and composite index column ordering.
4. Actual execution plan and statistics.
5. Write frequency and index maintenance cost.

Example plan check in an authorized environment:

```sql
EXPLAIN PLAN FOR
SELECT customer_id
FROM customers
WHERE email IS NULL;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

This reads/writes the plan table per tool configuration; it requires appropriate privileges and a practice environment. Never deduce performance solely from the existence of an index.

## 15. Common Errors and Misconceptions

| Symptom | Cause | How to handle |
|---|---|---|
| `WHERE col = NULL` returns no rows | Comparison yields UNKNOWN | Use `col IS NULL` |
| `WHERE col <> NULL` returns no rows | Comparison yields UNKNOWN | Use `col IS NOT NULL` |
| `NOT (col > 10)` drops NULL rows | `NOT UNKNOWN` remains UNKNOWN | Add `OR col IS NULL` if business rules want them |
| `NOT IN (subquery)` suddenly returns 0 rows | Subquery set contains NULL | Filter NULL in subquery or use `NOT EXISTS` |
| `COUNT(col)` is smaller than `COUNT(*)` | `COUNT(col)` skips NULL | Choose the counting function matching intent |
| `AVG(col)` is higher than expected with many NULLs | AVG skips NULL rather than treating NULL as 0 | Decide whether NULL should be replaced by 0 |
| LEFT JOIN loses unmatched rows | Filter on right-table column in WHERE produces UNKNOWN | Move the condition into ON when keeping left rows |
| Two NULL rows do not match in JOIN | `NULL = NULL` is UNKNOWN | Use a null-safe predicate if matching NULLs is truly intended |
| Java passes null to `col = ?` and finds no NULL rows | Binding NULL does not turn `=` into IS NULL | Choose an `IS NULL` query or write a null-safe condition |
| Whitespace-only string passes `IS NOT NULL` | Spaces are non-NULL values | Normalize / `TRIM` per business rules |
| Report displays 0 instead of "no data yet" | `NVL` replaces NULL with 0 | Confirm statistical meaning before substituting |

### Step-by-Step Reasoning Checklist for NULLs

When a query does not return the expected rows, ask in order:

1. Is the column actually NULL, or does it hold 0, spaces, or another string?
2. Is the expression using `=`, `<>`, `>`, `BETWEEN`, `LIKE`, `IN`, or `NOT IN`?
3. When NULL is present, does the expression evaluate to TRUE, FALSE, or UNKNOWN?
4. Is the current clause `WHERE`, `HAVING`, `ON`, `CASE`, or a projection expression?
5. Should NULL be **kept**, **excluded**, **joined**, **substituted**, or treated as **"filter skipped"** by business logic?
6. Must NULL application parameters be handled separately from NULL values stored in the table?

Never patch a query with `NVL(col, 0)` or `NVL(col, 'X')` just to eliminate NULLs unless you have proven the placeholder value cannot collide with real data.

## 16. Comprehensive Hands-On Exercise

The steps below use a small table in your practice schema. Run DDL/DML only if you have table-creation privileges and the table name does not conflict with existing data.

### Step 1. Create the Demo Table

```sql
CREATE TABLE demo_null_select (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(80),
    salary NUMBER,
    commission_pct NUMBER,
    department_id NUMBER
);
```

### Step 2. Insert Different States

```sql
INSERT INTO demo_null_select VALUES (1, 'An', 12000, 0.15, 10);
INSERT INTO demo_null_select VALUES (2, 'Binh', 8000, NULL, 10);
INSERT INTO demo_null_select VALUES (3, 'Chi', NULL, 0.10, 20);
INSERT INTO demo_null_select VALUES (4, 'Dung', 5000, NULL, NULL);
INSERT INTO demo_null_select VALUES (5, 'Ha', 0, 0, 20);

COMMIT;
```

These rows intentionally include:

- A NULL value in `SALARY`.
- NULL values in `COMMISSION_PCT`.
- A NULL value in `DEPARTMENT_ID`.
- Zero (`0`) to contrast against NULL.

### Step 3. Find Employees Without a Salary

```sql
SELECT employee_id, employee_name, salary
FROM demo_null_select
WHERE salary IS NULL;
```

Expected result: employee `Chi` (ID 3).

### Step 4. Find Employees With a Recorded Salary

```sql
SELECT employee_id, employee_name, salary
FROM demo_null_select
WHERE salary IS NOT NULL
ORDER BY salary;
```

The result includes the employee with salary 0, because 0 is a non-NULL value.

### Step 5. Compare UNKNOWN vs. FALSE

```sql
SELECT employee_id,
       CASE
           WHEN salary > 10000 THEN 'TRUE'
           WHEN salary <= 10000 THEN 'FALSE'
           ELSE 'UNKNOWN'
       END AS comparison_result
FROM demo_null_select
ORDER BY employee_id;
```

Employee ID 3 has `salary=NULL`, so both comparisons are UNKNOWN and fall into the ELSE branch. This is a clear way to observe all three logical states in one query.

### Step 6. Test NOT and Additional Conditions

```sql
-- Only rows where salary > 10000 is FALSE:
SELECT employee_id, salary
FROM demo_null_select
WHERE NOT (salary > 10000);

-- Include salary NULL as well:
SELECT employee_id, salary
FROM demo_null_select
WHERE NOT (salary > 10000)
   OR salary IS NULL;
```

Compare both results and explain why ID 3 appears only in the second query.

### Step 7. Compare COUNT Variants

```sql
SELECT COUNT(*) AS total_rows,
       COUNT(salary) AS rows_with_salary,
       COUNT(commission_pct) AS rows_with_commission
FROM demo_null_select;
```

Match the row counts against the NULL values inserted earlier.

### Step 8. Group by department_id

```sql
SELECT department_id, COUNT(*) AS employee_count
FROM demo_null_select
GROUP BY department_id
ORDER BY department_id NULLS LAST;
```

Observe that the NULL group appears on its own. This does not mean `department_id = NULL` evaluates to TRUE.

### Step 9. Clean Up the Practice Table

Run only after confirming this is the exact table you just created and the data is no longer needed:

```sql
DROP TABLE demo_null_select PURGE;
```

`DROP TABLE ... PURGE` removes the table and its data from the practice schema without keeping it in the recycle bin per command behavior; DDL performs an implicit commit. Never run on business tables or shared objects.

## 17. Cheat Sheet When Writing SELECT

| Goal | How to write it |
|---|---|
| Find columns with no value | `WHERE col IS NULL` |
| Find columns with a value | `WHERE col IS NOT NULL` |
| Find values differing from a known value and also keep NULL | `WHERE col <> :value OR col IS NULL` if business rules match |
| Find values in a list | `WHERE col IN (...)`, while accounting for NULLs in the list |
| Exclude values belonging to a subset | Prefer evaluating `NOT EXISTS`; control NULLs on both sides |
| Group NULL in results | `CASE WHEN col IS NULL THEN ...` |
| Count all rows | `COUNT(*)` |
| Count recorded values | `COUNT(col)` |
| Display fallback values | `NVL`, `COALESCE`, `CASE` |
| Sort NULL explicitly | `ORDER BY col ASC NULLS LAST` or appropriate option |
| Find NULL rows from JDBC | Use SQL with `IS NULL`, do not bind NULL to `= ?` |
| Skip filter when parameter is NULL | `:p IS NULL OR col = :p` |

Three key rules:

1. **To check NULL status, use `IS NULL` or `IS NOT NULL`.**
2. **Whenever NULL appears in comparisons or calculations, trace UNKNOWN before predicting WHERE results.**
3. **Determine the business meaning of NULL before replacing it with 0, a default string, or excluding it from reports.**

## 18. Self-Check Questions

**Question 1.** Can `WHERE email = NULL` find rows where email is NULL?

**Answer:** No. The comparison returns UNKNOWN; use `WHERE email IS NULL`.

**Question 2.** Is `NULL <> 10` TRUE or FALSE?

**Answer:** UNKNOWN. There is not enough information to conclude NULL differs from 10 under ordinary comparisons.

**Question 3.** What does `NOT UNKNOWN` equal?

**Answer:** UNKNOWN.

**Question 4.** How does WHERE treat a row whose condition is UNKNOWN?

**Answer:** It drops that row from the result; only rows whose condition is TRUE are selected.

**Question 5.** Does `salary > 10000 OR salary IS NULL` include rows with NULL salary?

**Answer:** Yes. The `salary IS NULL` side is TRUE, so the OR expression is TRUE.

**Question 6.** Can `salary > 10000 AND salary IS NULL` ever be TRUE?

**Answer:** No. If salary is NULL, the first side is UNKNOWN and the second is TRUE, giving UNKNOWN; if salary is non-NULL, the second side is FALSE. There is no TRUE case.

**Question 7.** Why does `NOT IN (10, 20, NULL)` typically fail to return rows with value 30?

**Answer:** The comparison `30 <> NULL` is UNKNOWN; the AND chain of conditions becomes UNKNOWN, so WHERE drops the row.

**Question 8.** How do `COUNT(*)` and `COUNT(email)` differ?

**Answer:** `COUNT(*)` counts every row; `COUNT(email)` counts only non-NULL email values.

**Question 9.** A LEFT JOIN finds no matching right-side row. What are the right-side columns returned as?

**Answer:** Oracle returns NULL for the right-side columns of the unmatched row. This is a NULL generated by the join, not necessarily stored in the right table.

**Question 10.** Will a JDBC parameter `email=null` bound into `WHERE email = ?` find NULL email rows?

**Answer:** No. You need `IS NULL` or an explicit null-safe condition.

**Question 11.** What does the pattern `:p IS NULL OR col = :p` mean?

**Answer:** Typically "skip the filter when the parameter is NULL"; it does not mean "find rows where `col IS NULL`."

**Question 12.** Why does `WHERE NOT (salary > 10000)` exclude rows with NULL salary?

**Answer:** `salary > 10000` is UNKNOWN; `NOT UNKNOWN` remains UNKNOWN, and WHERE drops the row.

## 19. Conclusion

`NULL` represents an undetermined value, so ordinary comparisons such as `=`, `<>`, `>`, `BETWEEN`, and `LIKE` can evaluate to **`UNKNOWN`**. SQL uses three-valued logic—`TRUE`, `FALSE`, and `UNKNOWN`—where `NOT UNKNOWN` stays UNKNOWN. The `WHERE` clause keeps only rows whose condition is TRUE, so UNKNOWN rows are excluded just like FALSE rows.

When checking for missing values, use **`IS NULL`**; when checking for present values, use **`IS NOT NULL`**. Never replace them with `= NULL` or `<> NULL`. Always account for NULL when using `NOT IN`, `JOIN`, `CASE`, `COUNT`, `AVG`, `SUM`, sorting, and Java bind parameters. Use `NVL` or `COALESCE` only when the substitute value matches business semantics.

Understanding `UNKNOWN` lets you predict accurately why a row appears or disappears from a SELECT result, write clearer filter conditions, and avoid subtle data bugs in applications connected to Oracle.
