# DECODE and Key Differences to Watch When Comparing NULL in Oracle

In Oracle SQL, `NULL` does not mean zero, an empty string, or a default value. It represents **the absence of a value or an unknown value**. Consequently, comparing `NULL = NULL` does not return `TRUE`—it returns `UNKNOWN`. This is the source of many bugs when filtering data, checking statuses, and writing conditional expressions.

Oracle provides the `DECODE` function with a special behavior: **when both the evaluated expression and a search value are NULL, DECODE considers them a match**. This differs from standard equality comparisons and also differs from simple `CASE expr WHEN NULL`. Understanding this distinction helps you migrate legacy SQL, handle nullable columns, and avoid unexpected results.

This lesson belongs to the **Functions and Expressions** topic of *Database Engine Relational Oracle*. It focuses on `DECODE` syntax and evaluation, NULL semantics, differences from `CASE`/`IS NULL`/`NVL`/`COALESCE`, implicit conversion, return types, short-circuiting, and legacy SQL maintenance scenarios.

## 1. NULL in SQL and three-valued logic

In SQL, `NULL` denotes an unknown or missing value. It is not a concrete value that can be compared like ordinary numbers or strings. A `commission_pct` column might be NULL because an employee has no commission or because the system has not recorded it yet. SQL does not automatically distinguish those two causes if both are stored as NULL.

A SQL condition can evaluate to three outcomes:

| Outcome | Meaning |
| --- | --- |
| `TRUE` | The condition is determined to be true. |
| `FALSE` | The condition is determined to be false. |
| `UNKNOWN` | Insufficient information to determine true or false, typically due to NULL. |

~~~sql
SELECT
    CASE WHEN NULL = NULL THEN 'TRUE'
         WHEN NULL <> NULL THEN 'FALSE'
         ELSE 'UNKNOWN'
    END AS equality_result,
    CASE WHEN NULL IS NULL THEN 'TRUE'
         ELSE 'FALSE'
    END AS is_null_result
FROM dual;
~~~

The first result is `UNKNOWN`; the second is `TRUE`. To check for NULL, use `IS NULL` or `IS NOT NULL`:

~~~sql
SELECT employee_id, commission_pct
FROM employees
WHERE commission_pct IS NULL;
~~~

Never write `WHERE commission_pct = NULL`. That predicate evaluates to `UNKNOWN` for every row and returns zero rows. Likewise, `WHERE commission_pct <> NULL` will not select non-NULL rows; write `IS NOT NULL`.

In `WHERE`, only rows where the predicate evaluates to `TRUE` are kept. Rows evaluating to `FALSE` or `UNKNOWN` are filtered out. `NOT UNKNOWN` remains `UNKNOWN`, not TRUE.

## 2. Syntax and behavior of DECODE

`DECODE` compares an expression against search values in order. Once it finds the first match, it returns the corresponding result; if no search value matches, it returns the default value if provided, or NULL otherwise.

~~~sql
DECODE(
    expression,
    search_1, result_1,
    search_2, result_2,
    ...,
    default_value
)
~~~

Example:

~~~sql
SELECT employee_id,
       DECODE(
           job_id,
           'IT_PROG', 'Developer',
           'SA_REP',  'Sales',
           'Other'
       ) AS job_group
FROM employees;
~~~

Oracle compares `job_id` against `'IT_PROG'` and then `'SA_REP'`. If neither matches, the result is `'Other'`. If the final argument is omitted, unmatched cases return NULL.

| Component | Role |
| --- | --- |
| `expression` | The value to compare. |
| `search_n` | Candidate value compared against expression. |
| `result_n` | Value returned when the corresponding search matches. |
| `default_value` | Result when no search matches; optional. |

`DECODE` evaluates search values sequentially and short-circuits: once a search matches, subsequent search expressions are not evaluated. Therefore, the order of search/result pairs affects the outcome if search conditions overlap or contain differing expressions.

~~~sql
SELECT DECODE(
           2,
           1, 'First',
           2, 'Second',
           3, 'Third',
           'No match'
       ) AS decoded_value
FROM dual;
~~~

The result is `Second`. Oracle limits `DECODE` to a maximum of **255 components**, counting expression, search/result arguments, and default. When there are too many branches or complex logic, consider `CASE` for readability and maintainability.

## 3. Crucial difference: DECODE treats NULL as matching NULL

**In DECODE, two NULL values are treated as equivalent when looking for a match.**

~~~sql
SELECT
    DECODE(NULL, NULL, 'MATCH', 'NO MATCH') AS decode_result,
    CASE
        WHEN NULL = NULL THEN 'MATCH'
        ELSE 'NO MATCH'
    END AS searched_case_result,
    CASE NULL
        WHEN NULL THEN 'MATCH'
        ELSE 'NO MATCH'
    END AS simple_case_result
FROM dual;
~~~

| Expression | Result |
| --- | --- |
| `DECODE(NULL, NULL, 'MATCH', 'NO MATCH')` | `MATCH` |
| `CASE WHEN NULL = NULL THEN ...` | `NO MATCH` because the condition is UNKNOWN |
| `CASE NULL WHEN NULL THEN ...` | `NO MATCH` because simple CASE uses standard equality comparison |

The two forms of CASE behave differently:

- **Simple CASE:** `CASE expression WHEN value THEN ...`. NULL does not match NULL under standard comparison.
- **Searched CASE:** `CASE WHEN condition THEN ...`. You can use `IS NULL` to check for NULL explicitly.

To write logic equivalent to DECODE, use searched CASE:

~~~sql
CASE
  WHEN expression IS NULL THEN 'MATCH'
  WHEN expression = search_value THEN 'MATCH'
  ELSE 'NO MATCH'
END
~~~

In general queries, arrange conditions in business-priority order. If there are multiple search values, write each branch explicitly; never replace `IS NULL` with `= NULL`.

### Example on a table with NULLs

~~~sql
CREATE TABLE lab_decode_status (
    item_id NUMBER(6) PRIMARY KEY,
    status_code VARCHAR2(20 CHAR)
);

INSERT INTO lab_decode_status VALUES (1, 'A');
INSERT INTO lab_decode_status VALUES (2, 'I');
INSERT INTO lab_decode_status VALUES (3, NULL);
INSERT INTO lab_decode_status VALUES (4, 'A');
COMMIT;

SELECT item_id,
       status_code,
       DECODE(
           status_code,
           'A', 'Active',
           'I', 'Inactive',
           NULL, 'Not assigned',
           'Unknown code'
       ) AS decode_label
FROM lab_decode_status
ORDER BY item_id;
~~~

The row with `status_code IS NULL` receives `Not assigned` because the third search is NULL. Rewritten with searched CASE:

~~~sql
SELECT item_id,
       status_code,
       CASE
         WHEN status_code = 'A' THEN 'Active'
         WHEN status_code = 'I' THEN 'Inactive'
         WHEN status_code IS NULL THEN 'Not assigned'
         ELSE 'Unknown code'
       END AS case_label
FROM lab_decode_status
ORDER BY item_id;
~~~

Both queries produce identical classifications in this example. When migrating complex DECODEs to CASE, verify NULL branches, search order, implicit conversions, and return types.

## 4. DECODE does not replace IS NULL everywhere

A common mistake:

~~~sql
-- Wrong intent: when status_code is NULL, the condition is never TRUE.
SELECT item_id
FROM lab_decode_status
WHERE status_code = NULL;
~~~

Correct version:

~~~sql
SELECT item_id
FROM lab_decode_status
WHERE status_code IS NULL;
~~~

If the goal is to generate a label, you can use DECODE:

~~~sql
SELECT item_id,
       DECODE(status_code, NULL, 'Missing', 'Present') AS status_label
FROM lab_decode_status;
~~~

Or searched CASE:

~~~sql
SELECT item_id,
       CASE
         WHEN status_code IS NULL THEN 'Missing'
         ELSE 'Present'
       END AS status_label
FROM lab_decode_status;
~~~

**DECODE is a value-mapping function**, not a drop-in replacement for NULL checks everywhere. In `WHERE`, `JOIN ON`, or constraints, use `IS NULL`/`IS NOT NULL` when that is what you actually mean.

### NULL in JOIN conditions

Suppose you need to join two tables on an optional code:

~~~sql
SELECT *
FROM table_a a
JOIN table_b b
  ON a.optional_code = b.optional_code;
~~~

Two rows where `optional_code` is NULL on both sides **do not match** in this JOIN because `NULL = NULL` is UNKNOWN. If business rules specify that two NULL values belong together as a matching group, state it explicitly:

~~~sql
SELECT *
FROM table_a a
JOIN table_b b
  ON a.optional_code = b.optional_code
  OR (a.optional_code IS NULL AND b.optional_code IS NULL);
~~~

This is a business decision that changes the joined row count. Do not add a NULL-matching branch just to "act like DECODE"; many systems intentionally avoid joining two unknown values.

## 5. DECODE, CASE, NVL, and COALESCE

All of these constructs appear in NULL-handling logic, yet their roles differ:

| Construct | Purpose | NULL Handling |
| --- | --- | --- |
| `DECODE(expr, search, result, ...)` | Match an expression against multiple values | NULL in expression matches NULL in search. |
| `CASE expr WHEN value THEN ...` | Pick branch by value equality | NULL does not match NULL via equality comparison. |
| `CASE WHEN expr IS NULL THEN ...` | Pick branch by arbitrary conditions | Explicit NULL check via `IS NULL`. |
| `NVL(expr, replacement)` | Replace NULL with a fallback value | Not a multi-branch mapper; handles only NULL on expression. |
| `COALESCE(a,b,c,...)` | Return the first non-NULL expression | Picks the first available value. |
| `NULLIF(a,b)` | Return NULL if both expressions are equal, else return a | Uses standard comparison; does not treat two NULLs as equal. |

~~~sql
SELECT
    DECODE(status_code, NULL, 'Missing', 'Present') AS by_decode,
    CASE WHEN status_code IS NULL
         THEN 'Missing' ELSE 'Present'
    END AS by_case,
    NVL(status_code, 'N/A') AS by_nvl,
    COALESCE(status_code, 'N/A') AS by_coalesce
FROM lab_decode_status;
~~~

Here, `DECODE` and searched `CASE` produce classification labels. `NVL` and `COALESCE` substitute `'N/A'` when NULL occurs. One group classifies; the other provides fallback values.

### NVL is not a shorthand DECODE

~~~sql
NVL(status_code, 'UNKNOWN')
~~~

only replaces NULL. It cannot directly map `'A'` to `'Active'`, `'I'` to `'Inactive'`, and other values to a default like DECODE does.

### COALESCE picks the first available value

~~~sql
SELECT COALESCE(
           preferred_phone,
           mobile_phone,
           office_phone,
           'No phone'
       ) AS contact_phone
FROM contacts;
~~~

`COALESCE` returns the first non-NULL argument in order. It does not compare one expression against a list of search/result pairs. When the goal is "pick the first non-missing fallback", COALESCE is usually much clearer than nesting `NVL` calls.

## 6. Implicit conversion in DECODE

A frequent source of bugs in SQL maintenance is **inconsistent data types across expression, search, and result arguments**. Oracle applies implicit conversion rules in DECODE. Without explicit type design, a query can:

- Compare using an unintended data type.
- Raise runtime conversion errors.
- Return a different data type than expected.
- Behave differently when search/result pairs are reordered.

### Comparison type depends on the first search value

Oracle converts the expression and subsequent search values according to the data type of the first search argument before comparing, with special numeric precedence rules when the first search-result pair is numeric. Therefore, keep all search arguments the same type as the expression.

Safe example with consistent string types:

~~~sql
SELECT DECODE(
           status_code,
           'A', 'Active',
           'I', 'Inactive',
           'Unknown'
       ) AS status_label
FROM lab_decode_status;
~~~

Consistent numeric example:

~~~sql
SELECT DECODE(
           priority_no,
           1, 'Critical',
           2, 'Normal',
           'Other'
       ) AS priority_label
FROM tasks;
~~~

Avoid mixing strings and numbers arbitrarily:

~~~sql
-- Avoid relying on ambiguous implicit conversion.
SELECT DECODE(
           status_code,
           1, 'One',
           'A', 'Letter A',
           'Other'
       )
FROM lab_decode_status;
~~~

If the expression is a string while the first search is a number, Oracle may attempt to convert strings to numbers for comparison. Non-numeric strings then raise conversion errors. Standardize the input type first:

~~~sql
SELECT DECODE(
           TO_NUMBER(priority_text),
           1, 'Critical',
           2, 'Normal',
           'Other'
       )
FROM task_import;
~~~

This example is safe only if every non-NULL value in `PRIORITY_TEXT` converts cleanly under the expected format/NLS. If source data is dirty, validate and parse safely first; never use `TO_NUMBER` as an unguarded "check if numeric" trick without error handling.

### Return type depends on the first result

Oracle determines the return data type of DECODE from the result arguments according to its rules. Notably: **if the first result is a NULL literal or has type CHAR, the return type becomes VARCHAR2**. If the first result is numeric, numeric precedence rules determine the numeric return type.

~~~sql
SELECT
    DUMP(DECODE(1, 1, NULL, 2, 100, 0)) AS first_result_null,
    DUMP(DECODE(1, 1, CAST(NULL AS NUMBER), 2, 100, 0))
        AS typed_null_result
FROM dual;
~~~

In the first expression, a bare NULL literal is the first result, so the return type becomes VARCHAR2; in the second, NULL is explicitly CAST to NUMBER to preserve a numeric return type. `DUMP` displays internal data type codes during inspection.

For numeric DECODEs, you can declare the type explicitly:

~~~sql
SELECT DECODE(
           status_code,
           'A', CAST(1 AS NUMBER(3,0)),
           'I', CAST(0 AS NUMBER(3,0)),
           CAST(NULL AS NUMBER(3,0))
       ) AS active_flag
FROM lab_decode_status;
~~~

Explicit return types help JDBC/ORM layers and outer expressions behave consistently. When refactoring legacy DECODE to CASE, verify the CASE return type using CASE's own type-resolution rules; never assume both functions always infer the exact same type.

## 7. Short-circuiting and branch order

Oracle evaluates DECODE search arguments in order and stops once a match is found. This matters when search arguments are expressions or function calls.

~~~sql
SELECT DECODE(
           status_code,
           'A', 'Active',
           'I', 'Inactive',
           NULL, 'Missing',
           'Other'
       ) AS label
FROM lab_decode_status;
~~~

Oracle checks `'A'`, `'I'`, and NULL in turn. Once one matches, later search expressions are skipped. Do not write overlapping search conditions without defining priority order.

DECODE matches discrete values; it is not suitable for range classification. For conditions like "less than 10" or "between 10 and 20", use searched CASE:

~~~sql
SELECT CASE
         WHEN salary IS NULL THEN 'Not provided'
         WHEN salary < 3000 THEN 'Entry'
         WHEN salary < 8000 THEN 'Mid'
         ELSE 'Senior'
       END AS salary_band
FROM employees;
~~~

## 8. DECODE in WHERE and index impact

DECODE is commonly used to derive display values in `SELECT`. Wrapping a column with DECODE inside `WHERE` can prevent standard index usage on that column, depending on the optimizer and predicate structure.

~~~sql
-- Direct NULL check:
SELECT item_id
FROM lab_decode_status
WHERE status_code IS NULL;

-- Same goal, but evaluates DECODE on the column:
SELECT item_id
FROM lab_decode_status
WHERE DECODE(status_code, NULL, 1, 0) = 1;
~~~

Both queries share the same intent, yet the first expresses the NULL condition directly and is usually preferable. The second forces DECODE evaluation on the column in the predicate; standard B-tree indexes have specific behaviors regarding NULLs. Do not assume the optimizer always rewrites a DECODE predicate into `IS NULL`.

If you frequently query for NULLs on an indexed column, consider appropriate index designs (such as a composite index including a non-NULL column or a function-based index) based on workload. Never add an index merely for one DECODE query; check the execution plan and query frequency first.

### DECODE in SELECT does not necessarily hurt index usage

~~~sql
SELECT item_id,
       DECODE(status_code, NULL, 'Missing', status_code) AS display_status
FROM lab_decode_status
WHERE item_id = :item_id;
~~~

Here the predicate filters on `ITEM_ID`, while DECODE only formats the display value after locating the row. If an index exists on the item key, the expression in the projection does not prevent that index from being used.

## 9. Other NULL scenarios prone to logic bugs

### NOT IN with NULL in the list

~~~sql
SELECT item_id
FROM lab_decode_status
WHERE status_code NOT IN ('A', NULL);
~~~

For any value other than `'A'`, the check expands to `status_code <> 'A' AND status_code <> NULL`; the second clause is UNKNOWN, so the entire condition never becomes TRUE. The query returns zero rows unexpectedly.

To exclude a specific code while keeping other non-NULL values:

~~~sql
SELECT item_id
FROM lab_decode_status
WHERE status_code IS NOT NULL
  AND status_code <> 'A';
~~~

When excluding values from another table, consider `NOT EXISTS` and explicitly define how NULLs in the join key should behave.

### Empty strings in Oracle

Oracle currently treats zero-length character strings (`''`) as NULL in SQL. Therefore, for character columns, `DECODE(status_code, NULL, ...)` also matches empty strings treated as NULL. Keep this Oracle behavior in mind when migrating data from other RDBMSs where empty string and NULL are distinct values.

## 10. When to use DECODE vs. CASE?

| Need | Option to Consider | Reason |
| --- | --- | --- |
| Maintaining legacy Oracle SQL already using DECODE | Keep DECODE if semantics are clear and tested | Avoids unintended changes during refactoring. |
| Mapping one expression to discrete equality values | DECODE or simple CASE | Concise and readable when types match and no special NULL behavior is needed. |
| Handling NULL as an explicit branch | Searched CASE with `IS NULL` or DECODE with NULL search | CASE is explicit; DECODE relies on special NULL-matching semantics. |
| Range conditions, AND/OR, or multiple columns | Searched CASE | Expresses arbitrary boolean predicates. |
| Portable SQL across database engines | CASE | CASE is standard SQL; DECODE is Oracle-specific. |
| Selecting the first non-NULL value | COALESCE | Directly expresses fallback priority. |
| Simply replacing NULL with one fallback value | NVL or COALESCE | No need for multiple search/result pairs. |

**There is no universal rule that DECODE is always faster than CASE or vice versa.** The optimizer can transform many equivalent expressions similarly; prioritize clear semantics, consistent types, and execution plans suited to your workload.

### Pattern for converting DECODE to CASE

~~~sql
SELECT DECODE(
           status_code,
           'A', 'Active',
           'I', 'Inactive',
           NULL, 'Missing',
           'Other'
       ) AS status_label
FROM lab_decode_status;
~~~

Equivalent searched CASE:

~~~sql
SELECT CASE
         WHEN status_code = 'A' THEN 'Active'
         WHEN status_code = 'I' THEN 'Inactive'
         WHEN status_code IS NULL THEN 'Missing'
         ELSE 'Other'
       END AS status_label
FROM lab_decode_status;
~~~

Simple CASE is **not equivalent** for the NULL branch:

~~~sql
SELECT CASE status_code
         WHEN 'A' THEN 'Active'
         WHEN 'I' THEN 'Inactive'
         WHEN NULL THEN 'Missing'
         ELSE 'Other'
       END AS status_label
FROM lab_decode_status;
~~~

The NULL row falls through to `ELSE` because `CASE status_code WHEN NULL` does not share DECODE's special semantics. When refactoring, always add a searched CASE branch `WHEN status_code IS NULL`.

## 11. DECODE in reporting and conditional aggregation

DECODE frequently appears in legacy Oracle reports to translate codes into labels or compute conditional sums. With nullable data, explicitly decide which group NULL belongs to.

Example counting rows by status:

~~~sql
SELECT
    COUNT(DECODE(status_code, 'A', 1)) AS active_count,
    COUNT(DECODE(status_code, 'I', 1)) AS inactive_count,
    COUNT(DECODE(status_code, NULL, 1)) AS missing_count
FROM lab_decode_status;
~~~

`COUNT(expression)` ignores NULL results. DECODE returns `1` on a match and NULL otherwise (since there is no default), so each COUNT tallies one group. On a nullable `STATUS_CODE`, the NULL search branch counts NULL rows thanks to DECODE's NULL-matching semantics.

Written explicitly with CASE:

~~~sql
SELECT
    SUM(CASE WHEN status_code = 'A' THEN 1 ELSE 0 END) AS active_count,
    SUM(CASE WHEN status_code = 'I' THEN 1 ELSE 0 END) AS inactive_count,
    SUM(CASE WHEN status_code IS NULL THEN 1 ELSE 0 END) AS missing_count
FROM lab_decode_status;
~~~

Both achieve the same goal here. CASE is easier to extend when conditions span multiple columns or comparisons. If using `SUM(DECODE(...))`, ensure the expression returns numbers and defines an explicit default:

~~~sql
SELECT
    SUM(DECODE(status_code, 'A', 1, 0)) AS active_count,
    SUM(DECODE(status_code, 'I', 1, 0)) AS inactive_count,
    SUM(DECODE(status_code, NULL, 1, 0)) AS missing_count
FROM lab_decode_status;
~~~

Here the default is 0, so each row contributes 0 or 1 to the sum. Unlike COUNT, watch out with SUM when zero rows exist or all values are NULL; in this example every row returns 0 or 1.

## 12. Migrating legacy SQL containing DECODE

In long-lived Oracle systems, DECODE can appear in SELECT lists, WHERE, ORDER BY, GROUP BY, views, or materialized views. Never bulk-replace DECODE with CASE via simple text search-and-replace.

### Safe migration checklist

1. **Identify expression and search types.** Is the column NUMBER, VARCHAR2, DATE, or an expression? Are there implicit conversions?
2. **Document NULL behavior.** Is there a NULL search pair? Could the expression evaluate to NULL due to outer joins, functions, or missing data?
3. **Document branch order.** Do search values overlap or repeat? The first matching branch wins.
4. **Verify result data type.** Is the first result a bare NULL/CHAR/numeric? What return type do callers expect?
5. **Write the equivalent searched CASE.** Convert NULL search pairs into `IS NULL` conditions; write remaining comparisons with explicit types.
6. **Compare result sets on representative data.** Include NULLs, empty strings, boundary values, differing data types, and unmatched cases.
7. **Check execution plans if used in predicates.** Never assume CASE or DECODE is automatically faster.

### Example migration with multiple branches and NULL

Legacy DECODE:

~~~sql
SELECT employee_id,
       DECODE(
           commission_pct,
           NULL, 'No commission',
           0,    'Zero commission',
           0.1,  'Ten percent',
           'Other rate'
       ) AS commission_label
FROM employees;
~~~

Searched CASE:

~~~sql
SELECT employee_id,
       CASE
         WHEN commission_pct IS NULL THEN 'No commission'
         WHEN commission_pct = 0 THEN 'Zero commission'
         WHEN commission_pct = 0.1 THEN 'Ten percent'
         ELSE 'Other rate'
       END AS commission_label
FROM employees;
~~~

For a NUMBER column, the numeric literals in the example are also NUMBER. If the actual column has another type or relies on implicit conversion, match the real column type rather than copying templates blindly.

### Never mechanically replace DECODE with NVL

~~~sql
DECODE(status_code, NULL, 'Missing', 'A', 'Active', 'Other')
~~~

is not equivalent to:

~~~sql
NVL(status_code, 'Missing')
~~~

DECODE maps multiple cases to labels; NVL returns the original value itself whenever it is non-NULL. The two expressions differ in both purpose and output values.

## 13. Common errors and solutions

| Symptom | Cause | Solution |
| --- | --- | --- |
| `WHERE col = NULL` returns no rows | Comparing to NULL yields UNKNOWN | Use `IS NULL`. |
| Converting DECODE to simple CASE changes NULL row labels | `CASE expr WHEN NULL` never matches NULL | Use searched CASE with `WHEN expr IS NULL`. |
| DECODE returns VARCHAR2 even when later branches are numbers | First result is a NULL literal or CHAR | CAST the first result to the intended type. |
| DECODE raises conversion errors | Expression/search types differ and implicit conversion fails | Align types or parse/CAST explicitly. |
| Output changes after reordering search/result pairs | Search order determines first match and can affect type inference | Preserve business order and check types before refactoring. |
| `NOT IN` returns empty set when subquery contains NULL | Three-valued logic turns exclusion into UNKNOWN | Use `NOT EXISTS` or filter NULLs intentionally. |
| Empty string matches NULL branch in Oracle | Oracle treats empty strings as NULL | Standardize data contracts when integrating with other databases. |
| Predicate wrapping column in DECODE runs slowly | Function expression can inhibit normal index usage | Write direct predicates, inspect plan; consider function-based index if justified. |
| Cannot distinguish "missing data" from "not applicable" | Both business states stored as NULL | Design distinct status codes or metadata when distinction is required. |

### Notes on using DECODE with numeric data

For numbers, keep search types consistent with the expression. If the column is NUMBER, use NUMBER literals or explicit CAST. Never rely on NLS-formatted numeric strings for numeric comparisons.

~~~sql
-- Clearer when priority_no column is NUMBER:
SELECT DECODE(priority_no, 1, 'High', 2, 'Normal', 'Other')
FROM tasks;

-- If input is a string, parse explicitly and handle invalid data:
SELECT CASE
         WHEN VALIDATE_CONVERSION(priority_text AS NUMBER) = 1
         THEN DECODE(TO_NUMBER(priority_text), 1, 'High', 2, 'Normal', 'Other')
         ELSE 'Invalid input'
       END AS priority_label
FROM task_import;
~~~

`VALIDATE_CONVERSION` is available on Oracle versions that support this function; on older versions, use a compatible validation/parsing approach. Also pass explicit format/NLS parameters whenever numeric strings contain separators. Never use this sample SQL as an excuse to ignore upstream data quality rules.

## 14. Comprehensive practice lab

Execute in a practice schema with `CREATE TABLE` privileges and adequate quota. DDL triggers Oracle's implicit commit; never run against live business tables.

### Step 1: create sample data

~~~sql
CREATE TABLE lab_decode_values (
    id          NUMBER(6) PRIMARY KEY,
    code        VARCHAR2(10 CHAR),
    description VARCHAR2(80 CHAR)
);

INSERT INTO lab_decode_values VALUES (1, 'A', 'Active row');
INSERT INTO lab_decode_values VALUES (2, 'I', 'Inactive row');
INSERT INTO lab_decode_values VALUES (3, NULL, 'No code');
INSERT INTO lab_decode_values VALUES (4, 'A', 'Another active row');
INSERT INTO lab_decode_values VALUES (5, 'X', 'Other code');
COMMIT;
~~~

### Step 2: observe NULL matching in DECODE

~~~sql
SELECT id,
       code,
       DECODE(
           code,
           'A', 'Active',
           'I', 'Inactive',
           NULL, 'Missing',
           'Other'
       ) AS decode_label
FROM lab_decode_values
ORDER BY id;
~~~

Note the label for `ID = 3`. Then remove the `NULL, 'Missing'` pair and observe the default fallback.

### Step 3: compare all three forms

~~~sql
SELECT
    DECODE(NULL, NULL, 'MATCH', 'NO') AS decode_null,
    CASE NULL
      WHEN NULL THEN 'MATCH'
      ELSE 'NO'
    END AS simple_case_null,
    CASE
      WHEN NULL IS NULL THEN 'MATCH'
      ELSE 'NO'
    END AS searched_case_null
FROM dual;
~~~

Explain why only DECODE and searched CASE with an explicit NULL check return MATCH in this example.

### Step 4: test WHERE predicates

~~~sql
SELECT id
FROM lab_decode_values
WHERE code = NULL;

SELECT id
FROM lab_decode_values
WHERE code IS NULL;
~~~

Compare row counts returned. The first selects zero rows; the second selects `ID = 3`.

### Step 5: inspect return data types

~~~sql
SELECT
    DUMP(DECODE(1, 1, NULL, 2, 100, 0)) AS implicit_result_type,
    DUMP(DECODE(1, 1, CAST(NULL AS NUMBER), 2, 100, 0))
        AS explicit_number_type
FROM dual;
~~~

Explain the effect of having a bare NULL literal as the first result versus an explicitly CAST NULL AS NUMBER.

### Step 6: test empty strings in Oracle

~~~sql
SELECT
    CASE WHEN '' IS NULL THEN 'EMPTY_IS_NULL'
         ELSE 'NOT_NULL'
    END AS oracle_empty_string,
    DECODE('', NULL, 'MATCHES_NULL', 'NO_MATCH') AS decode_empty
FROM dual;
~~~

Oracle treats zero-length character strings as NULL in SQL, so DECODE matches the NULL branch. Do not assume this rule applies identically across all other databases.

### Step 7: try conditional aggregation

~~~sql
SELECT
    COUNT(DECODE(code, 'A', 1)) AS active_count,
    COUNT(DECODE(code, 'I', 1)) AS inactive_count,
    COUNT(DECODE(code, NULL, 1)) AS missing_count
FROM lab_decode_values;
~~~

Rewrite using searched CASE and `SUM`:

~~~sql
SELECT
    SUM(CASE WHEN code = 'A' THEN 1 ELSE 0 END) AS active_count,
    SUM(CASE WHEN code = 'I' THEN 1 ELSE 0 END) AS inactive_count,
    SUM(CASE WHEN code IS NULL THEN 1 ELSE 0 END) AS missing_count
FROM lab_decode_values;
~~~

Explain why `COUNT(DECODE(...))` skips rows where DECODE returns NULL.

### Step 8: clean up test data

~~~sql
DROP TABLE lab_decode_values PURGE;
DROP TABLE lab_decode_status PURGE;
~~~

Run this only if you created both practice tables in your own schema and no longer need the data. `DROP TABLE ... PURGE` is DDL, bypasses the Recycle Bin, and cannot be rolled back like uncommitted DML.

## 15. Self-check questions

1. **What does `NULL = NULL` return?** UNKNOWN, not TRUE.
2. **Why does `DECODE(NULL, NULL, 'Y', 'N')` return Y?** DECODE has special semantics treating two NULLs as a match.
3. **Does `CASE NULL WHEN NULL THEN 'Y'` behave like DECODE?** No; simple CASE uses standard equality comparison, so the NULL branch does not match.
4. **How do you write CASE properly to check for NULL?** `CASE WHEN expr IS NULL THEN ...`.
5. **Can `WHERE col = NULL` replace `WHERE col IS NULL`?** No; the first evaluates to UNKNOWN for NULL rows.
6. **What does DECODE return if default is omitted and no search matches?** NULL.
7. **Does DECODE have a component limit?** Yes, at most 255 components counting expression, search, result, and default.
8. **In what order does DECODE evaluate search values?** Left to right, stopping at the first match (short-circuiting).
9. **Why can having NULL as the first result force the return type to VARCHAR2?** Oracle has specific type-resolution rules where a bare NULL literal or CHAR as the first result yields VARCHAR2.
10. **Does DECODE replace NVL?** No; NVL replaces a single NULL value, while DECODE maps an expression across multiple search/result pairs.
11. **When should you use COALESCE?** When selecting the first non-NULL expression from a list.
12. **Does DECODE cause NULLs in two tables to automatically JOIN together?** No; standard equality JOINs still yield UNKNOWN when both sides are NULL unless an explicit NULL-matching predicate is written.
13. **Why is DECODE not always a good choice in WHERE?** Wrapping a column in a function predicate can hinder standard index usage; IS NULL or direct equality expresses the filter more cleanly.
14. **What must you check when converting DECODE to CASE?** NULL branches, branch ordering, search/result types, return type, and implicit conversions.
15. **Is DECODE suited for checking value ranges?** No; use searched CASE with range comparison predicates.
16. **Why can empty strings match a NULL search in Oracle?** Oracle currently treats zero-length character strings as NULL in SQL.
17. **What does `COUNT(DECODE(code, 'A', 1))` count?** The number of rows where code equals A, because COUNT ignores NULL results.

## Conclusion

`DECODE` is an Oracle-specific function for mapping an expression through search/result pairs. The most important rule to remember is that **DECODE treats NULL as matching NULL**, whereas `=` comparisons and simple `CASE expr WHEN NULL` follow three-valued logic and do not match. To test for NULL in CASE, always use **searched CASE with `IS NULL`**.

When maintaining SQL, check **NULL semantics, branch ordering, and data types**. DECODE can return an unexpected type if the first result is NULL or CHAR, and implicit conversions can trigger runtime errors or altered outputs. Use `CASE` for complex or cross-platform logic, `NVL` or `COALESCE` for NULL fallback selection, and `IS NULL` in filter predicates. Choosing the right construct keeps SQL accurate, readable, and safe across migrations.
