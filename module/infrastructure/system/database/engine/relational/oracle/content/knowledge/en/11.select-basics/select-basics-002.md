# Selecting Columns, Expressions, Aliases, and Using DUAL in Oracle Database

The `SELECT` statement is the starting point for querying data from **Oracle Database**. Even in a basic `SELECT` statement, a SQL author must distinguish between **choosing which columns to display**, **deriving output columns from expressions**, **naming output columns with aliases**, and **evaluating expressions without a business table**, typically using the special `DUAL` table.

For example, given an employee table with columns `EMP_ID`, `FULL_NAME`, `BASE_SALARY`, and `BONUS`, we can:

- Select only the employee ID and name.
- Compute annual salary from monthly salary.
- Combine two numeric values and handle `NULL`.
- Rename the display header of a column to `ANNUAL_SALARY` or `"Annual Salary"`.
- Test expressions like `2 + 3`, `SYSDATE`, or string functions without reading data from the employee table.

These skills are the foundation for reporting, queries in Java/JDBC applications, aggregations, conditional expressions, and more complex queries. This lesson focuses on **Oracle SQL syntax and semantics**, and includes a hands-on lab to practice from scratch.

## 1. Basic SELECT Structure

An Oracle query typically takes the form:

~~~sql
SELECT expression_1 [AS alias_1],
       expression_2 [AS alias_2],
       ...
FROM table_or_view
WHERE condition
ORDER BY expression_or_alias;
~~~

For a simple query, the core part is:

~~~sql
SELECT column_name
FROM table_name;
~~~

Meaning:

| Component | Function |
|---|---|
| `SELECT` | Declares the list of values/columns returned by the query |
| `column_name` | Data column retrieved from a table/view |
| `expression` | Operation, literal, function, or expression that produces an output value |
| `AS alias` | Names a column in the result set; the `AS` keyword may be omitted for a **column alias** |
| `FROM` | Identifies the source of data rows |
| `WHERE` | Filters which rows satisfy the condition |
| `ORDER BY` | Requests the result ordering |

More advanced queries also include `JOIN`, `GROUP BY`, `HAVING`, `FETCH FIRST`, and other expression forms. You do not need all of them yet to understand column selection and aliases.

### 1.1 Selecting Columns vs. Filtering Rows

Suppose table `STAFF` has 1,000 rows and 10 columns.

~~~sql
SELECT emp_id, full_name
FROM staff;
~~~

The statement above selects **two columns** to include in the output; it does not ask for only two rows. Without other conditions, the query can return 1,000 rows, each containing two values.

~~~sql
SELECT emp_id, full_name
FROM staff
WHERE dept_code = 'IT';
~~~

The second statement still outputs only **two columns**, but `WHERE` eliminates rows that do not belong to the IT department.

In relational terminology, choosing a set of attributes is called **projection**, while keeping rows that satisfy a condition is usually called **selection/filtering**. Although the name `SELECT` can make this confusing, the two concepts are not the same:

~~~text
Source table: many rows, many columns
       |
       | WHERE: choose matching rows
       v
Remaining rows
       |
       | SELECT list: determine output columns/expressions
       v
Final result set
~~~

This is a conceptual diagram of the output. **The Oracle optimizer may execute physical operations in a different order** to optimize the query; do not treat the diagram as a fixed step-by-step order that the engine always reads sequentially.

### 1.2 What Does a SELECT Statement Return?

A *result set* consists of:

- **Number of columns**, column order, and column names/labels according to the SELECT list.
- **Data type** of each expression, such as `NUMBER`, `VARCHAR2`, `DATE`, or `TIMESTAMP`.
- **Rows** that satisfy the query conditions.

Column labels are displayed by SQL Developer, SQL*Plus, SQLcl, or JDBC. Displayed names do not have to match the physical column names in the table, because expressions can have their own aliases.

## 2. Selecting One Column or Multiple Columns

### 2.1 One Column

~~~sql
SELECT full_name
FROM staff;
~~~

Hypothetical result:

| FULL_NAME |
|---|
| An Nguyen |
| Binh Tran |
| Chi Le |

### 2.2 Multiple Columns, Separated by Commas

~~~sql
SELECT emp_id,
       full_name,
       dept_code,
       base_salary
FROM staff;
~~~

Expressions in the SELECT list are separated by **commas**. The order in the SELECT list determines the order in which columns are presented.

Do not put a trailing comma after the last column before `FROM`:

~~~sql
-- Syntax error example:
SELECT emp_id,
       full_name,
FROM staff;
~~~

This kind of error may be reported by Oracle as incomplete SELECT syntax or a misplaced keyword. The fix is to remove the trailing comma.

### 2.3 Selecting the Same Column Multiple Times

Oracle allows using one column in multiple expressions:

~~~sql
SELECT base_salary,
       base_salary AS original_salary,
       base_salary * 12 AS annual_salary
FROM staff;
~~~

The physical `BASE_SALARY` column is not duplicated in the table. Only the **result set** contains multiple expressions referencing the same source data.

### 2.4 Selecting All Columns with *

~~~sql
SELECT *
FROM staff;
~~~

`*` is the symbol that expands all columns of the data source in SELECT semantics, not multiplication in this context. In SQL Developer, the statement above is convenient for exploring a table.

However, for application queries or stable reports, you should explicitly list the required columns:

~~~sql
SELECT emp_id,
       full_name,
       dept_code
FROM staff;
~~~

Reasons:

1. **Clear data contract:** clients know exactly which columns to expect.
2. **Reduced data transfer:** avoids fetching large or sensitive columns that are not needed.
3. **Reduced schema coupling:** when columns are added to the table, the result of `SELECT *` changes.
4. **Favorable for certain access plans:** selecting only indexed columns can allow the optimizer to choose an appropriate access path.
5. **Avoids physical-order dependency:** applications mapping columns by position with `SELECT *` easily break when table structure changes.

This does not mean `SELECT *` is inefficient in every case; it is fine for quickly viewing data or inspecting tables in a safe environment. But in APIs/DAOs and long-lived SQL, an explicit column list is generally better.

## 3. Using Table Aliases and Column Name Prefixes

When querying multiple tables, duplicate column names such as `ID`, `NAME`, or `CREATED_AT` may exist. Using a **table alias** makes SQL clearer:

~~~sql
SELECT s.emp_id,
       s.full_name,
       s.dept_code
FROM staff s;
~~~

`s` is the alias for table `STAFF` within the scope of the query. The name `s.emp_id` identifies column `EMP_ID` from source `s`.

### 3.1 Selecting All Columns from One Source

~~~sql
SELECT s.*
FROM staff s;
~~~

`s.*` retrieves all columns from source `s`. In a query with a JOIN, `s.*` and `d.*` distinguish which side you want all columns from.

Hypothetical example with a `DEPARTMENTS` table:

~~~sql
SELECT s.emp_id,
       s.full_name,
       d.dept_name
FROM staff s
JOIN departments d
  ON d.dept_code = s.dept_code;
~~~

Here `s` and `d` are **table aliases**, while `EMP_ID`, `FULL_NAME`, and `DEPT_NAME` are **columns**. If both tables have `DEPT_CODE`, you must specify `s.dept_code` or `d.dept_code` wherever it would otherwise be ambiguous.

### 3.2 Distinguishing Alias Syntax for Columns and Tables

For a **column alias**, both forms are valid:

~~~sql
SELECT base_salary AS salary
FROM staff;

SELECT base_salary salary
FROM staff;
~~~

For a **table alias** in Oracle SQL, the standard form is:

~~~sql
SELECT s.emp_id
FROM staff s;
~~~

Do not write `FROM staff AS s` out of habit from other database systems when you want broad Oracle SQL compatibility. Some syntax/versions evolve over time; across traditional Oracle versions, specifying a table alias **without `AS`** is the safe convention.

## 4. Expressions in the SELECT List

An **expression** is a calculation or value-producing construct. Not every item in SELECT has to be a column name; it can be:

- A **literal** such as `100` or `'ACTIVE'`.
- An arithmetic operation `base_salary * 12`.
- A string concatenation `'Employee: ' || full_name`.
- A function such as `UPPER(full_name)`, `ROUND(...)`, or `TO_CHAR(...)`.
- A conditional expression `CASE ... END`.
- An expression combining multiple columns, functions, and literals.

### 4.1 Numeric and String Literals

~~~sql
SELECT emp_id,
       'ACTIVE' AS sample_status,
       100 AS sample_score
FROM staff;
~~~

The values `'ACTIVE'` and `100` are constants in the query, so every output row receives those same values. They are not two new columns added to the table.

In Oracle, string literals are enclosed in **single quotes**; double quotes are used for quoted identifiers, such as certain alias names.

Example:

~~~sql
SELECT 'It''s Oracle SQL' AS message
FROM dual;
~~~

Use two consecutive single quotes `''` to represent an apostrophe inside a string.

### 4.2 Arithmetic Expressions

~~~sql
SELECT emp_id,
       base_salary,
       base_salary * 12 AS annual_base_salary
FROM staff;
~~~

Oracle evaluates the expression for each row. A row with a monthly salary of 15,000,000 produces an annual salary expression of 180,000,000, assuming `BASE_SALARY` is stored according to that monetary convention.

Common operators:

| Operator | Meaning | Example |
|---|---|---|
| `+` | Addition | `base_salary + bonus` |
| `-` | Subtraction | `base_salary - 100000` |
| `*` | Multiplication | `base_salary * 12` |
| `/` | Division | `base_salary / 12` |
| `( )` | Grouping/override precedence | `(base_salary + bonus) * 12` |

An easily confused operator-precedence example:

~~~sql
SELECT 10 + 2 * 5 AS default_precedence,
       (10 + 2) * 5 AS parenthesized
FROM dual;
~~~

The results are `20` and `60`, respectively. Multiplication takes precedence over addition according to standard arithmetic rules. For long business expressions, use parentheses to prevent misunderstanding.

### 4.3 Division by Zero

Division with a denominator of 0 can raise `ORA-01476: divisor is equal to zero`. When the denominator comes from data, you can use `NULLIF`:

~~~sql
SELECT sales_amount,
       order_count,
       sales_amount / NULLIF(order_count, 0) AS average_amount
FROM daily_summary;
~~~

If `ORDER_COUNT = 0`, `NULLIF(order_count, 0)` returns NULL and the division result is NULL instead of dividing by 0. This is a **handling policy**; if business logic requires displaying 0 or raising an error, decide explicitly rather than treating every division with missing data as 0.

### 4.4 Combining Multiple Columns in One Expression

~~~sql
SELECT emp_id,
       base_salary,
       bonus,
       (base_salary + NVL(bonus, 0)) * 12 AS annual_income_estimate
FROM staff;
~~~

This example assumes `BONUS` is a monthly amount and replaces NULL with 0. If the bonus is paid annually or on another schedule, the formula must change. SQL computes only the expression the author writes; it does not infer compensation policies on its own.

## 5. NULL in Expressions: Not the Same as Zero

`NULL` represents **no known/provided value** in SQL semantics. It is not synonymous with 0 or an empty string in all contexts.

### 5.1 NULL Changes Expression Outcomes

Suppose:

~~~text
BASE_SALARY = 15,000,000
BONUS       = NULL
~~~

With the expression:

~~~sql
SELECT base_salary + bonus AS gross_salary
FROM staff;
~~~

The expression result for that row is `NULL` because one operand has no numeric value.

If business rules confirm that **an undeclared bonus counts as 0**, use:

~~~sql
SELECT base_salary + NVL(bonus, 0) AS gross_salary
FROM staff;
~~~

`NVL(expr, replacement)` is an Oracle function that substitutes a fallback value for NULL. Do not apply `NVL` blindly in every situation: missing salary data may require exception handling rather than turning into 0.

### 5.2 COALESCE

`COALESCE` picks the first non-NULL expression:

~~~sql
SELECT emp_id,
       COALESCE(bonus, 0) AS bonus_for_calculation
FROM staff;
~~~

With multiple fallback sources:

~~~sql
SELECT COALESCE(preferred_email, work_email, 'not-provided') AS contact_email
FROM contacts;
~~~

Watch type compatibility among arguments. Do not mix numbers, dates, and strings with different meanings in a single expression and rely on implicit conversion.

### 5.3 Comparing NULL

Do not use `= NULL` to find missing values:

~~~sql
-- Incorrect way to check for NULL:
WHERE bonus = NULL
~~~

In SQL's three-valued logic, such a comparison never yields TRUE. Use:

~~~sql
WHERE bonus IS NULL
~~~

and:

~~~sql
WHERE bonus IS NOT NULL
~~~

### 5.4 Empty Strings in Oracle

Oracle currently has a distinctive behavior: for zero-length character string types, `''` is generally treated as NULL. Therefore, do not assume a `VARCHAR2` column always distinguishes between an **empty string** and **NULL** the way some programming languages do.

When concatenating strings, Oracle has specific rules for NULL and the `||` operator. If you need an explicit fallback value, use `NVL`/`COALESCE` rather than assuming identical NULL-concatenation behavior across all DBMSs.

## 6. String Concatenation and Text Functions

Oracle uses the `||` operator to concatenate string expressions:

~~~sql
SELECT 'Employee: ' || full_name AS employee_label
FROM staff;
~~~

Example output: `Employee: An Nguyen`.

**Do not use `+` to concatenate strings out of habit from certain programming languages or other DBMSs.** In Oracle, `+` has arithmetic semantics; `||` is the string concatenation operator.

### 6.1 Combining Names or Display Codes

~~~sql
SELECT emp_id,
       full_name || ' (' || dept_code || ')' AS employee_display
FROM staff;
~~~

A row may display:

~~~text
An Nguyen (IT)
~~~

### 6.2 UPPER, LOWER, INITCAP, and TRIM Functions

~~~sql
SELECT full_name,
       UPPER(full_name) AS uppercase_name,
       LOWER(full_name) AS lowercase_name,
       INITCAP(full_name) AS title_like_name,
       TRIM(full_name) AS trimmed_name
FROM staff;
~~~

Text functions follow character and charset/NLS rules. `INITCAP` is not a universal personal-name normalizer for all languages, and `UPPER` does not make text comparisons valid for every locale when language-specific collation rules are required.

### 6.3 Formatting Values in Expressions

~~~sql
SELECT emp_id,
       'ID=' || TO_CHAR(emp_id) AS employee_key
FROM staff;
~~~

`TO_CHAR` converts a value into a string according to an Oracle format. For numbers and dates in international applications, specify an explicit format model/NLS when producing fixed text contracts.

## 7. Functions and CASE Expressions in SELECT

Not every output column comes from arithmetic operators. You can use functions or `CASE` to display statuses.

### 7.1 ROUND and TRUNC

~~~sql
SELECT 10 / 3 AS raw_value,
       ROUND(10 / 3, 2) AS rounded_value,
       TRUNC(10 / 3, 2) AS truncated_value
FROM dual;
~~~

`ROUND(number, 2)` rounds to two decimal places, whereas `TRUNC(number, 2)` drops digits after the specified position without rounding.

This example is convenient because `DUAL` lets you test calculations without needing business table data.

### 7.2 CASE: Producing Conditional Values

~~~sql
SELECT emp_id,
       full_name,
       base_salary,
       CASE
           WHEN base_salary >= 20000000 THEN 'HIGH'
           WHEN base_salary >= 12000000 THEN 'MEDIUM'
           ELSE 'LOW'
       END AS salary_band
FROM staff;
~~~

`CASE ... END` is an **expression that returns a single value**. It does not modify `BASE_SALARY` or create a `SALARY_BAND` column in the table.

Key points to note:

- `WHEN` conditions are evaluated in expression order.
- In the sample above, a row with 20 million matches the `HIGH` branch before the `MEDIUM` branch.
- `ELSE` provides a value when no branch matches.
- If `ELSE` is omitted and no branch matches, the expression can return NULL.

### 7.3 Conditional Expressions for Columns with NULL

~~~sql
SELECT emp_id,
       bonus,
       CASE
           WHEN bonus IS NULL THEN 'NOT_RECORDED'
           WHEN bonus = 0 THEN 'ZERO'
           ELSE 'HAS_BONUS'
       END AS bonus_state
FROM staff;
~~~

This example distinguishes **bonus not recorded** from **bonus equal to 0**, a distinction `NVL(bonus, 0)` would obscure when business rules require keeping them separate.

### 7.4 Date and Time Functions

~~~sql
SELECT SYSDATE AS database_now,
       SYSTIMESTAMP AS database_timestamp,
       CURRENT_DATE AS session_current_date
FROM dual;
~~~

`SYSDATE` returns an Oracle DATE based on the database system clock; `SYSTIMESTAMP` includes fractional seconds and timezone info; `CURRENT_DATE` returns a DATE in the session timezone. Do not assume these functions always display the same time when the session timezone differs from the database server.

## 8. Column Aliases

A column alias is the **name/label of an expression in the result set**. It makes SQL easier to read and helps applications, reports, or screens display meaningful column headers.

### 8.1 Using AS

~~~sql
SELECT emp_id AS employee_id,
       full_name AS employee_name,
       base_salary * 12 AS annual_salary
FROM staff;
~~~

Here `EMPLOYEE_ID`, `EMPLOYEE_NAME`, and `ANNUAL_SALARY` are **column aliases**, not new columns in the table.

### 8.2 Omitting AS Is Also Valid

~~~sql
SELECT emp_id employee_id,
       full_name employee_name
FROM staff;
~~~

Oracle accepts this form, though for long expressions adding `AS` usually makes the boundary between expression and alias clearer.

### 8.3 Aliases with Double Quotes

To give labels spaces, punctuation, or lowercase letters, use a **double-quoted identifier**:

~~~sql
SELECT emp_id AS "Employee ID",
       full_name AS "Full Name",
       base_salary * 12 AS "Annual Salary"
FROM staff;
~~~

When displayed in a Unicode-capable tool, the headers can appear as `Employee ID`, `Full Name`, and `Annual Salary`.

Important rules:

- **Single quotes `'...'`** represent **string literals**.
- **Double quotes `"..."`** enclose **identifier names**, including column aliases.
- Unquoted names are generally treated by Oracle as case-insensitive at the identifier level.
- Double-quoted names preserve exact casing/spelling and generally must be referenced with the exact same spelling.

Example:

~~~sql
SELECT base_salary * 12 AS "Annual Salary"
FROM staff
ORDER BY "Annual Salary" DESC;
~~~

In `ORDER BY`, you must write the alias with the exact spaces and casing as declared.

### 8.4 Aliases Do Not Change the Schema

~~~sql
SELECT base_salary AS monthly_salary
FROM staff;
~~~

This does not rename column `BASE_SALARY` in the table to `MONTHLY_SALARY`. Another query against `STAFF` still uses `BASE_SALARY` as before.

Renaming a physical column is a separate DDL task requiring privileges and an impact assessment on applications using the schema. Do not run DDL just to change a report header.

### 8.5 Aliases Should Describe Units and Meaning

Compare:

~~~sql
SELECT base_salary * 12 AS x
FROM staff;
~~~

and:

~~~sql
SELECT base_salary * 12 AS annual_base_salary
FROM staff;
~~~

The second alias is clearer: it is **annual base salary**, not automatically net pay or total compensation if bonuses, allowances, or deductions exist. Meaningful aliases reduce misinterpretation in applications and dashboards.

## 9. Alias Scope: ORDER BY, WHERE, and Subqueries

A common misconception is thinking an alias just created in `SELECT` can be used **in any clause** of the same query.

### 9.1 ORDER BY Can Use Column Aliases

~~~sql
SELECT emp_id,
       full_name,
       base_salary * 12 AS annual_salary
FROM staff
ORDER BY annual_salary DESC;
~~~

`ORDER BY` can reference the `ANNUAL_SALARY` alias from the SELECT list. In SQL Developer or SQL*Plus, the output will be ordered by the annual salary expression descending.

### 9.2 WHERE Cannot Use a SELECT Alias in the Same Query Block

**Invalid** example in Oracle:

~~~sql
SELECT emp_id,
       base_salary * 12 AS annual_salary
FROM staff
WHERE annual_salary > 150000000;
~~~

`ANNUAL_SALARY` is a label defined in the SELECT list; `WHERE` in the same query block cannot use it as a source column. Oracle may report `ORA-00904: invalid identifier`, except in confusing edge cases where a real source column happens to share the same name.

First approach: repeat the expression in WHERE:

~~~sql
SELECT emp_id,
       base_salary * 12 AS annual_salary
FROM staff
WHERE base_salary * 12 > 150000000;
~~~

Second approach: place the expression in an **inline view**:

~~~sql
SELECT x.emp_id,
       x.annual_salary
FROM (
    SELECT emp_id,
           base_salary * 12 AS annual_salary
    FROM staff
) x
WHERE x.annual_salary > 150000000;
~~~

In the outer query block, `ANNUAL_SALARY` is a column of the subquery result `x`, so it can be used in the outer query block's WHERE clause.

### 9.3 Using WITH to Reuse Expressions

~~~sql
WITH payroll AS (
    SELECT emp_id,
           full_name,
           base_salary * 12 AS annual_salary
    FROM staff
)
SELECT emp_id,
       full_name,
       annual_salary
FROM payroll
WHERE annual_salary > 150000000
ORDER BY annual_salary DESC;
~~~

`WITH` creates a common table expression (CTE) to name an intermediate result. This is useful when an expression is long or needs to be referenced in multiple places.

This is a logical SQL organization technique. It does **not mean Oracle is forced to write the CTE out as a physical temporary table**: the optimizer can choose among multiple execution strategies.

### 9.4 Aliases with GROUP BY and HAVING

In traditional Oracle versions, you should not assume SELECT-list aliases can be referenced directly in `GROUP BY` or `HAVING` within the same query block. Newer Oracle versions have added support for certain alias syntax forms, though support varies by release and configuration.

When broad compatibility is required, use the original expression or put the computation into an inline view/CTE first:

~~~sql
WITH categorized AS (
    SELECT dept_code,
           CASE
             WHEN base_salary >= 15000000 THEN 'HIGH'
             ELSE 'OTHER'
           END AS salary_band
    FROM staff
)
SELECT dept_code,
       salary_band,
       COUNT(*) AS staff_count
FROM categorized
GROUP BY dept_code, salary_band
ORDER BY dept_code, salary_band;
~~~

This example previews `GROUP BY`; the lesson's focus remains how to define expressions and aliases and reference them in the appropriate query block.

### 9.5 ORDER BY by Column Position

Oracle allows using positions from the SELECT list:

~~~sql
SELECT emp_id,
       full_name,
       base_salary
FROM staff
ORDER BY 3 DESC;
~~~

`ORDER BY 3` sorts by the third expression in the SELECT list, namely `BASE_SALARY`. Although concise, this easily breaks when columns are added or reordered. In long-lived SQL, `ORDER BY base_salary DESC` or a clear alias is easier to maintain.

## 10. DISTINCT, ALL, and the Difference Between Column Selection and Deduplication

By default, `SELECT` has `ALL` semantics: rows with identical values across the selected columns **can appear multiple times**.

Suppose three employees share `DEPT_CODE = 'IT'`:

~~~sql
SELECT dept_code
FROM staff;
~~~

The value `IT` can appear three times.

To get a **unique** list of department codes, use:

~~~sql
SELECT DISTINCT dept_code
FROM staff;
~~~

### 10.1 DISTINCT Applies to the Entire Column Combination

~~~sql
SELECT DISTINCT dept_code,
       active_flag
FROM staff;
~~~

Oracle deduplicates by the **pair of values** `(DEPT_CODE, ACTIVE_FLAG)`, not `DEPT_CODE` alone.

Example:

~~~text
IT / Y
IT / Y
IT / N
~~~

After DISTINCT, what remains is:

~~~text
IT / Y
IT / N
~~~

### 10.2 DISTINCT Does Not Replace ORDER BY

The result of `SELECT DISTINCT` is not guaranteed to be in any desired order without `ORDER BY`.

~~~sql
SELECT DISTINCT dept_code
FROM staff
ORDER BY dept_code;
~~~

### 10.3 Cost of DISTINCT

On large datasets, DISTINCT may require a sort, hash, or other deduplication mechanism. Do not use DISTINCT merely to hide a broken JOIN that duplicates rows; understand why duplicate rows are appearing in the first place.

## 11. What Is DUAL?

**`DUAL`** is a special single-row table provided by Oracle to make it easy to evaluate expressions when no business table needs to be read. It resides in the `SYS` system schema and is normally accessed under the name `DUAL`.

Some newer Oracle versions support `SELECT` statements without `FROM` in certain contexts, but using `FROM DUAL` remains the standard and broadly compatible idiom across Oracle versions.

### 11.1 Selecting a Constant from DUAL

~~~sql
SELECT 1 AS value_one
FROM dual;
~~~

The result is one row, one column with the value `1`.

~~~sql
SELECT 'Hello Oracle' AS message
FROM dual;
~~~

The result is one row containing the string `Hello Oracle`.

### 11.2 Testing Calculations with DUAL

~~~sql
SELECT 7 * 8 AS result
FROM dual;
~~~

The result is `56`.

~~~sql
SELECT 10 + 2 * 5 AS expression_a,
       (10 + 2) * 5 AS expression_b
FROM dual;
~~~

The result is one row with two columns: `20` and `60`.

DUAL helps you quickly test SQL syntax or functions without creating a lab table or querying user data.

### 11.3 Checking System Functions

~~~sql
SELECT USER AS connected_user,
       SYSDATE AS database_date,
       SYSTIMESTAMP AS database_timestamp
FROM dual;
~~~

`USER` shows the Oracle user of the current session; `SYSDATE` and `SYSTIMESTAMP` return timestamps associated with the database system. DUAL does not store this information: it is evaluated by **expressions/functions** in Oracle.

Checking the container in Oracle Multitenant:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name
FROM dual;
~~~

The values depend on the connected session and database. This syntax is useful for verifying you are querying the right environment before performing other actions.

### 11.4 DUAL Has a DUMMY Column

Traditionally, DUAL has one column named `DUMMY` whose value is typically `X`:

~~~sql
SELECT dummy
FROM dual;
~~~

Because `DUAL` provides only one row, the query above returns one row. Do not insert, update, or delete rows in `SYS.DUAL`: it is a system object, not an application practice table.

### 11.5 FAST DUAL Optimization

For many expressions that do not need to read the `DUMMY` column directly, Oracle can optimize execution via a mechanism commonly known as **FAST DUAL**, avoiding accessing DUAL's data block like a normal business table.

Example:

~~~sql
SELECT 100 / 4 AS result
FROM dual;
~~~

This query does not need the contents of the `DUMMY` column. In the execution plan on supporting versions, you may see an operation related to FAST DUAL. If `DUMMY` is referenced directly, the plan may differ.

What matters for beginners is that **DUAL returns one row so you can test expressions**, not that it is a large table needing index tuning.

### 11.6 DUAL Does Not Mean Every SELECT Returns One Row

~~~sql
SELECT full_name
FROM staff;
~~~

Returns a number of rows depending on the STAFF table.

~~~sql
SELECT 1
FROM dual;
~~~

Returns one row because the data source is DUAL. If you add an unsatisfiable condition:

~~~sql
SELECT 1 AS result
FROM dual
WHERE 1 = 0;
~~~

No rows are returned. Thus, row count is the result of the source and conditions, not because every SELECT expression "automatically" generates one row.

### 11.7 When Should You Use DUAL?

| Need | Should you use DUAL? | Example |
|---|---|---|
| Compute `2 * 3 + 1` | Yes | `SELECT 2 * 3 + 1 FROM dual` |
| Get database time | Yes | `SELECT SYSTIMESTAMP FROM dual` |
| Test `UPPER('oracle')` | Yes | `SELECT UPPER('oracle') FROM dual` |
| Check session/user/container | Yes | `SELECT USER FROM dual` |
| Read employee list | Do not replace STAFF | `SELECT full_name FROM staff` |
| Generate 10,000 sample rows | Needs another row-generation mechanism | You can use `CONNECT BY LEVEL` or an appropriate data generator; do not expect DUAL itself to hold 10,000 rows |

## 12. Using DUAL with DATE, TIMESTAMP Literals, and Conversion Functions

In Oracle, DUAL is especially handy for testing data types and format models.

### 12.1 DATE Literal

~~~sql
SELECT DATE '2026-11-14' AS selected_day
FROM dual;
~~~

A DATE literal of this form creates a date value with time 00:00:00. How it displays depends on the client/NLS settings, not because it is a string type.

### 12.2 TIMESTAMP Literal

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30:45.123456' AS event_time
FROM dual;
~~~

TIMESTAMP can hold fractional seconds; a plain TIMESTAMP **does not automatically carry a timezone**.

### 12.3 TO_DATE and TO_CHAR

~~~sql
SELECT TO_CHAR(
         TO_DATE('2026-11-14 09:30:45',
                 'YYYY-MM-DD HH24:MI:SS'),
         'YYYY-MM-DD HH24:MI:SS'
       ) AS formatted_date
FROM dual;
~~~

`TO_DATE` converts a string to a DATE, and `TO_CHAR` converts a datetime value into a **string** using the specified format. Using explicit formats keeps examples stable across NLS changes.

### 12.4 TO_TIMESTAMP_TZ

~~~sql
SELECT TO_TIMESTAMP_TZ(
         '2026-11-14 09:30:00 +07:00',
         'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS timestamp_with_zone
FROM dual;
~~~

This is a value that includes UTC offset information. To obtain the instant in UTC:

~~~sql
SELECT SYS_EXTRACT_UTC(
         TO_TIMESTAMP_TZ(
           '2026-11-14 09:30:00 +07:00',
           'YYYY-MM-DD HH24:MI:SS TZH:TZM'
         )
       ) AS utc_timestamp
FROM dual;
~~~

The result is a TIMESTAMP value representing `2026-11-14 02:30:00` in UTC. This is an expression-testing example unrelated to the employee table.

## 13. Expressions, Data Types, and Implicit Conversion

Every SELECT expression has a **result data type**. Oracle applies type rules and sometimes performs implicit type casting. For reliable queries, write explicit conversions whenever types could be ambiguous.

### 13.1 Do Not Casually Add Numeric Strings

~~~sql
-- Avoid relying on implicit conversion between strings and numbers.
SELECT '100' + 20 AS result
FROM dual;
~~~

This may cause Oracle to convert `'100'` to NUMBER, depending on whether the string parses validly and related settings. When the input is a numeric string, write an explicit conversion:

~~~sql
SELECT TO_NUMBER('100') + 20 AS result
FROM dual;
~~~

When converting numbers with decimal or thousands separators, pay attention to format models/NLS, because commas and periods have different meanings across locales.

### 13.2 Formatted Dates Are Strings, Not Values for Arithmetic

~~~sql
SELECT SYSDATE + 1 AS next_day
FROM dual;
~~~

With DATE, adding `1` corresponds to adding one day under Oracle DATE arithmetic. Do not convert a DATE to a string to add days:

~~~sql
-- Do not treat a formatted string as a datetime value for calculations.
SELECT TO_CHAR(SYSDATE, 'YYYY-MM-DD') AS today_text
FROM dual;
~~~

`TODAY_TEXT` is a string, suitable for display, not an Oracle DATE for datetime arithmetic.

### 13.3 Use CAST to Specify Types Explicitly

~~~sql
SELECT CAST(100 AS NUMBER(10,2)) AS amount,
       CAST('Oracle' AS VARCHAR2(20)) AS text_value
FROM dual;
~~~

`CAST` performs type conversion with explicit syntax. Conversions between datetime types with and without timezone can drop or alter timezone semantics according to Oracle rules; verify before storing business data.

### 13.4 Checking Expressions That Return NULL

~~~sql
SELECT NULL AS missing_value,
       NVL(CAST(NULL AS NUMBER), 0) AS numeric_default
FROM dual;
~~~

`CAST(NULL AS NUMBER)` explicitly types the NULL expression in this example. When designing output columns for views/CTEs, the expression's type matters to data-mapping tools.

## 14. Column Names, Aliases, and Usage in Applications

A Java/JDBC application might run:

~~~sql
SELECT emp_id AS employee_id,
       full_name AS employee_name,
       base_salary * 12 AS annual_salary
FROM staff
WHERE emp_id = :p_emp_id;
~~~

In JDBC `PreparedStatement`, parameters are normally written with `?`; `:p_emp_id` syntax is common bind notation in Oracle SQL tools and some frameworks. JDBC example:

~~~java
String sql = """
    SELECT emp_id AS employee_id,
           full_name AS employee_name,
           base_salary * 12 AS annual_salary
    FROM staff
    WHERE emp_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, requestedId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long id = rs.getLong("EMPLOYEE_ID");
            String name = rs.getString("EMPLOYEE_NAME");
            java.math.BigDecimal annualSalary =
                rs.getBigDecimal("ANNUAL_SALARY");
        }
    }
}
~~~

This snippet assumes an existing method with `connection` and `requestedId`. Handle `SQLException` per application conventions and check the no-row case. SQL computes `ANNUAL_SALARY`, while JDBC reads the **result column label** from the alias.

### 14.1 Quoted Aliases and Mapping

If SQL uses:

~~~sql
SELECT emp_id AS "Employee Id",
       full_name AS "Employee Name"
FROM staff;
~~~

The labels include spaces and exact casing. This can be a good choice for human-readable reports, though not always convenient for automatic API mapping. In DAO queries, simple, stable aliases like `employee_id` and `employee_name` are usually easier to work with.

### 14.2 A Column Alias Is Not Security

~~~sql
SELECT salary AS public_salary
FROM staff;
~~~

Renaming the `SALARY` label to `PUBLIC_SALARY` does not make the data public and does not restrict access. Security must rely on database privileges, views, row/column security policies, roles, API authorization, and proper column selection.

### 14.3 Bind Variables Are Not Aliases

Compare:

~~~sql
SELECT base_salary * :p_factor AS adjusted_salary
FROM staff;
~~~

- `:p_factor` is a **bind variable** passing a value into the expression.
- `ADJUSTED_SALARY` is a **column alias** naming the output.

An alias does not accept parameter values; a bind variable does not rename a column label. Do not concatenate user input directly into SQL in place of bind parameters.

## 15. Result Ordering and SELECT DISTINCT

Without `ORDER BY`, Oracle **does not guarantee row order**, even if the table has a primary key, rows were inserted in ascending order, or the query uses an index.

~~~sql
SELECT emp_id, full_name
FROM staff;
~~~

There is no guarantee that the row with the smallest `EMP_ID` is returned first.

~~~sql
SELECT emp_id, full_name
FROM staff
ORDER BY emp_id;
~~~

Requests ascending order by ID.

When sorting by an expression:

~~~sql
SELECT emp_id,
       base_salary * 12 AS annual_salary
FROM staff
ORDER BY annual_salary DESC, emp_id ASC;
~~~

Adding the secondary key `EMP_ID` stabilizes results when multiple employees have the same annual salary.

`DISTINCT` only deduplicates by the selected columns; it does **not** mean "sort." When both are needed:

~~~sql
SELECT DISTINCT dept_code
FROM staff
ORDER BY dept_code;
~~~

## 16. Lab: Creating a Dedicated Employee Table for Practice

The examples in earlier sections used `STAFF` as a conceptual table name. To practice end-to-end without requiring the sample HR schema, you can create **`LAB_SELECT_STAFF`** in a **dedicated practice schema**.

**Run DDL/DML only on an account permitted to create tables, with sufficient quota, and never in a production schema.** Oracle DDL like `CREATE TABLE` performs an implicit commit; a subsequent `ROLLBACK` will not undo table creation.

### 16.1 Creating the Table

~~~sql
CREATE TABLE lab_select_staff (
    emp_id       NUMBER PRIMARY KEY,
    full_name    VARCHAR2(100) NOT NULL,
    dept_code    VARCHAR2(20) NOT NULL,
    base_salary  NUMBER(12,2) NOT NULL,
    bonus        NUMBER(12,2),
    hired_on     DATE NOT NULL,
    active_flag  CHAR(1) NOT NULL
);
~~~

The columns are chosen deliberately:

- `EMP_ID`: numeric identifier.
- `FULL_NAME`: name string.
- `DEPT_CODE`: department code, with repeated values to test DISTINCT.
- `BASE_SALARY`: NUMBER to test multiplication/addition expressions.
- `BONUS`: can be NULL or 0, ideal for illustrating NULL handling.
- `HIRED_ON`: DATE to test formatting.
- `ACTIVE_FLAG`: character flag for CASE.

### 16.2 Loading Data

~~~sql
INSERT INTO lab_select_staff VALUES
    (101, 'An Nguyen', 'IT', 15000000, 2000000, DATE '2022-03-15', 'Y');

INSERT INTO lab_select_staff VALUES
    (102, 'Binh Tran', 'IT', 12000000, NULL, DATE '2023-07-01', 'Y');

INSERT INTO lab_select_staff VALUES
    (103, 'Chi Le', 'HR', 11000000, 0, DATE '2021-12-20', 'Y');

INSERT INTO lab_select_staff VALUES
    (104, 'Dung Pham', 'FIN', 22000000, 3500000, DATE '2020-05-10', 'N');

INSERT INTO lab_select_staff VALUES
    (105, 'Ha Vo', 'IT', 18000000, NULL, DATE '2024-01-08', 'Y');

COMMIT;
~~~

The example inserts five rows: three IT employees, one bonus equal to 0, and two NULL bonuses. This highlights the difference between 0 and an unrecorded value.

### 16.3 Selecting Two Columns

~~~sql
SELECT emp_id, full_name
FROM lab_select_staff
ORDER BY emp_id;
~~~

Result:

| EMP_ID | FULL_NAME |
|---:|---|
| 101 | An Nguyen |
| 102 | Binh Tran |
| 103 | Chi Le |
| 104 | Dung Pham |
| 105 | Ha Vo |

### 16.4 Computing a New Column with an Expression

~~~sql
SELECT emp_id,
       full_name,
       base_salary,
       base_salary * 12 AS annual_base_salary
FROM lab_select_staff
ORDER BY emp_id;
~~~

Employee 101's annual base salary is 180,000,000 assuming 12 months at a fixed monthly salary. This column exists only in the result set; it does not add a stored column to the table.

### 16.5 Handling NULL in Formulas

~~~sql
SELECT emp_id,
       base_salary,
       bonus,
       base_salary + bonus AS naive_total,
       base_salary + NVL(bonus, 0) AS normalized_total
FROM lab_select_staff
ORDER BY emp_id;
~~~

For employees 102 and 105, `NAIVE_TOTAL` is NULL while `NORMALIZED_TOTAL` equals their base salary. For employee 103, bonus is **0**, not NULL; that is a recorded value.

### 16.6 Concatenating Strings and Using Aliases with Spaces

~~~sql
SELECT emp_id AS "Emp ID",
       full_name || ' - ' || dept_code AS "Name and Dept"
FROM lab_select_staff
ORDER BY emp_id;
~~~

Example first row: `101 | An Nguyen - IT`.

### 16.7 CASE

~~~sql
SELECT emp_id,
       full_name,
       CASE
           WHEN active_flag = 'Y' THEN 'ACTIVE'
           ELSE 'INACTIVE'
       END AS employment_status
FROM lab_select_staff
ORDER BY emp_id;
~~~

Each row receives a new status label. `ACTIVE_FLAG` in the table is not modified.

### 16.8 DISTINCT

~~~sql
SELECT DISTINCT dept_code
FROM lab_select_staff
ORDER BY dept_code;
~~~

The result contains three department codes: `FIN`, `HR`, `IT`. Even though IT has three employees, it appears once.

### 16.9 Filtering by an Aliased Expression

Incorrect:

~~~sql
-- ORA-00904 or similar reference error because the alias is not in scope in this WHERE clause.
SELECT emp_id,
       base_salary * 12 AS annual_salary
FROM lab_select_staff
WHERE annual_salary >= 180000000;
~~~

Correct when repeating the expression:

~~~sql
SELECT emp_id,
       base_salary * 12 AS annual_salary
FROM lab_select_staff
WHERE base_salary * 12 >= 180000000
ORDER BY annual_salary DESC;
~~~

Or using an inline view:

~~~sql
SELECT q.emp_id,
       q.annual_salary
FROM (
    SELECT emp_id,
           base_salary * 12 AS annual_salary
    FROM lab_select_staff
) q
WHERE q.annual_salary >= 180000000
ORDER BY q.annual_salary DESC;
~~~

### 16.10 Formatting Hire Dates

~~~sql
SELECT emp_id,
       TO_CHAR(hired_on, 'YYYY-MM-DD') AS hire_date_text
FROM lab_select_staff
ORDER BY emp_id;
~~~

`HIRE_DATE_TEXT` is a formatted date string. `HIRED_ON` itself remains a DATE.

### 16.11 Testing DUAL Alongside the Lab

No employee table is needed to run:

~~~sql
SELECT 2026 AS report_year,
       UPPER('oracle') AS product_name,
       125 * 4 AS calculated_value,
       SYSDATE AS executed_at
FROM dual;
~~~

The result is one row with multiple expressions of different data types.

### 16.12 Cleaning Up the Lab

If you want to clean up after practicing, drop **only the table you created** in the lab schema following approved administrative procedures. Do not leave `DROP TABLE` statements in scripts that might be run against production by mistake, since DDL performs an implicit commit and you cannot rely on `ROLLBACK` to undo it.

## 17. Common Mistakes When Selecting Columns, Expressions, and Aliases

| Situation | Issue | How to fix |
|---|---|---|
| `SELECT emp_id full_name dept_code FROM staff` | Missing commas; Oracle may interpret the next name as an alias or raise an error | Write `SELECT emp_id, full_name, dept_code` |
| `SELECT emp_id, FROM staff` | Extra trailing comma before FROM | Remove the trailing comma |
| `SELECT unknown_column FROM staff` | Column does not exist, or missing privilege/scope | Check table metadata and source alias |
| `SELECT salary * 12 AS annual FROM staff WHERE annual > ...` | Referencing a SELECT alias in WHERE of the same query block | Repeat the expression or use a CTE/inline view |
| `FROM staff AS s` in traditional Oracle | Table alias does not use AS in Oracle's standard form | Write `FROM staff s` |
| `SELECT 'hello' AS 'Message' FROM dual` | Using single quotes for an alias name | Write `AS "Message"` or `AS message` |
| `SELECT 100 / 0 FROM dual` | Division by zero | Guard the denominator; consider `NULLIF` |
| `base_salary + bonus` returns NULL | BONUS is NULL | Clarify business rules; consider `NVL(bonus, 0)` |
| `'A' + 'B'` | `+` is not the string concatenation operator | Use `'A' || 'B'` |
| DATE displays without time portion | NLS/client format hides time | Use `TO_CHAR(date_col, 'YYYY-MM-DD HH24:MI:SS')` to inspect |
| SQL uses `SELECT *` and maps columns by position | Adding columns to the schema changes the result shape | Explicitly select columns with stable aliases |
| Missing `ORDER BY`, results vary between runs | No order guarantee | Add `ORDER BY` on the proper keys |
| `SELECT DISTINCT` still returns multiple rows with the same DEPT_CODE | DISTINCT applies to the full combination of selected expressions | Select only the columns to deduplicate or design a proper GROUP BY |
| `SELECT UPPER(name) FROM dual` | `NAME` is not a column of DUAL | Use a literal `UPPER('Oracle')` or query FROM a table that has NAME |
| `SELECT 1 FROM dual WHERE 1=0` returns no rows | WHERE eliminates the single row from DUAL | Check the condition; DUAL does not bypass WHERE |

When Oracle reports an error, read the full message and error position, then break the SQL statement into smaller expressions. Use DUAL to test functions/operators and explicit column lists to verify source column names.

## 18. Best Practices and Habits to Build

### 18.1 Select Only Needed Columns

If the UI needs employee ID and name, the query:

~~~sql
SELECT emp_id, full_name
FROM lab_select_staff;
~~~

is clearer than `SELECT *` and avoids fetching salary/bonus when unnecessary. Limiting fields also reduces the risk of exposing sensitive information at the application layer, though **access permissions must still be managed independently**.

### 18.2 Use Stable Aliases

For API queries, use meaningful aliases without spaces, for example:

~~~sql
SELECT emp_id AS employee_id,
       full_name AS employee_name,
       base_salary * 12 AS annual_base_salary
FROM lab_select_staff;
~~~

For human-facing reports, double-quoted aliases can be used for cleaner headings.

### 18.3 Avoid Overusing Heavy Per-Row Expressions

A simple arithmetic expression is usually fine, but calling complex functions in the SELECT list across millions of rows can incur substantial CPU cost. Also distinguish computing in the SELECT list for **display** from wrapping a column in a function inside `WHERE`, which can affect index usage.

### 18.4 Watch Out for Implicit Conversions

A numeric calculation should not rely on whether `'100'` converts automatically. Likewise, datetime expressions should not rely on default NLS settings. Use appropriate literals and conversion functions, and bind proper types from JDBC.

### 18.5 Never Assume Row Order

If a report requires alphabetical names or descending salaries, write an explicit `ORDER BY` and add a stable tie-breaker key when needed. Aliases can appear in ORDER BY, but they do not make the result ordered automatically.

## 19. Self-Check Questions and Practice Exercises

### Exercise 1 — DUAL and Operator Precedence

Predict both results:

~~~sql
SELECT 8 + 2 * 5 AS a,
       (8 + 2) * 5 AS b
FROM dual;
~~~

*Hint:* `A = 18`, `B = 50`. Use parentheses to control evaluation order.

### Exercise 2 — Selecting Columns and Computing Annual Salary

Write a query on `LAB_SELECT_STAFF` returning `EMP_ID`, `FULL_NAME`, and annual base salary with alias `ANNUAL_BASE_SALARY`; sort by annual salary descending.

One solution:

~~~sql
SELECT emp_id,
       full_name,
       base_salary * 12 AS annual_base_salary
FROM lab_select_staff
ORDER BY annual_base_salary DESC, emp_id;
~~~

### Exercise 3 — Why Does NULL Appear?

Two expressions:

~~~sql
SELECT emp_id,
       base_salary + bonus AS total_a,
       base_salary + NVL(bonus, 0) AS total_b
FROM lab_select_staff;
~~~

For employee 102, `BONUS = NULL`. *Hint:* `TOTAL_A` is NULL, while `TOTAL_B` equals base salary. Business logic must decide before applying NULL → 0 in the application.

### Exercise 4 — Alias in WHERE

Explain why this query is invalid and fix it:

~~~sql
SELECT emp_id, base_salary * 12 AS annual_salary
FROM lab_select_staff
WHERE annual_salary > 200000000;
~~~

*Hint:* A SELECT alias is not in scope in WHERE of the same query block. Repeat `base_salary * 12` or use an inline view/CTE.

### Exercise 5 — DISTINCT on a Combination

Predict the result:

~~~sql
SELECT DISTINCT dept_code, active_flag
FROM lab_select_staff
ORDER BY dept_code, active_flag;
~~~

*Hint:* `IT/Y` appears once even though there are three active IT employees, `HR/Y` once, and `FIN/N` once. DISTINCT evaluates the **pair of columns**.

### Exercise 6 — Using DUAL to Inspect Session Info

Write a statement returning the current Oracle username and container:

~~~sql
SELECT USER AS connected_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

No application table is read in this query.

### Exercise 7 — Distinguishing Single Quotes and Double Quotes

Write a SELECT statement returning the string `Hello` under the spaced label `Greeting Text`.

~~~sql
SELECT 'Hello' AS "Greeting Text"
FROM dual;
~~~

`'Hello'` is a **literal**, while `"Greeting Text"` is a **quoted column alias**.

### Exercise 8 — Safe Reporting Data

An API only needs `EMP_ID` and `FULL_NAME`, yet it is running `SELECT * FROM LAB_SELECT_STAFF`. Give two reasons to switch to an explicit column list.

*Hint:* Avoids extra/sensitive columns such as salary and bonus; keeps result shape and column names stable when the schema changes; can sometimes reduce I/O and network traffic. However, data access permissions must always be enforced at the database/application layer.

### Exercise 9 — Date and Time Expressions

Try:

~~~sql
SELECT TO_CHAR(
         DATE '2026-11-14' + 1,
         'YYYY-MM-DD HH24:MI:SS'
       ) AS next_day_text
FROM dual;
~~~

*Hint:* The Oracle DATE literal starts at 00:00:00 on the 14th; adding one day yields 00:00:00 on the 15th. `TO_CHAR` only converts the result into a string.

### Exercise 10 — The Nature of a SELECT Alias

After running:

~~~sql
SELECT base_salary AS monthly_pay
FROM lab_select_staff;
~~~

can you continue with:

~~~sql
SELECT base_salary
FROM lab_select_staff;
~~~

*Hint:* Yes. An alias does not rename the physical column or alter the schema; it exists only within the context of the query.

## 20. Summary

In Oracle Database, the **SELECT list** determines which columns and values appear in the output. An item can be a **base column**, **literal**, **calculation**, **function**, **CASE**, or **combined expression**. A **column alias** gives output columns readable names, but it does not create or rename physical columns and cannot be used arbitrarily in every clause of the same query block.

Important practical rules:

1. **Explicitly select needed columns** instead of overusing `SELECT *` in long-lived application code.
2. **Use proper alias syntax**: `AS annual_salary` or `AS "Annual Salary"`; single quotes are for string literals.
3. **Remember alias scope**: usable in `ORDER BY`, whereas `WHERE` in the same query block needs the original expression or a subquery/CTE.
4. **Write expressions carefully** with respect to precedence, NULL, type conversion, monetary units, and datetime formatting.
5. **Use DUAL** to test expressions and functions when no business table is needed; DUAL normally has one row and is convenient for `SELECT 1`, `SYSDATE`, or `SYS_CONTEXT`.
6. **Do not confuse projection with filtering or sorting**: the SELECT list chooses columns, WHERE chooses rows, ORDER BY defines sort order, and DISTINCT deduplicates by the selected value combination.

Once you master these concepts, you can write concise, accurate SELECT queries, provide consistent column labels for reporting/JDBC, and verify Oracle expressions on DUAL before putting them into real queries.
