# Simple CASE and Searched CASE Expressions

In Oracle SQL, **`CASE`** is an expression used to select a result value based on conditions. It lets you embed classification rules directly inside a query: tiering orders by amount, mapping status codes to readable labels, grouping employees by salary band, or computing conditional sums.

Oracle provides two main forms:

- **Simple CASE:** compares one expression against a sequence of `WHEN` values.
- **Searched CASE:** evaluates a sequence of boolean conditions in each `WHEN` clause.

The two forms look similar syntactically, yet solve different problems. Simple CASE works well when a single expression is tested for equality against discrete values; searched CASE is more flexible when you need ranges, operators, multiple columns, NULL checks, or compound predicates.

## 1. General structure of CASE

### 1.1. Simple CASE

```sql
CASE expression
    WHEN value_1 THEN result_1
    WHEN value_2 THEN result_2
    ...
    [ELSE default_result]
END
```

Oracle evaluates `expression`, compares it against each `WHEN` value from top to bottom, and returns the `result` of the first matching branch. If no branch matches, Oracle returns `ELSE`; if `ELSE` is omitted, the default result is **NULL**.

Example:

```sql
SELECT
    order_id,
    status,
    CASE status
        WHEN 'NEW'       THEN 'New'
        WHEN 'PAID'      THEN 'Paid'
        WHEN 'CANCELLED' THEN 'Cancelled'
        ELSE 'Other status'
    END AS status_label
FROM lab_orders
ORDER BY order_id;
```

Here, `status` is simply compared against specific values. There is no need to repeat the column name in every branch.

### 1.2. Searched CASE

```sql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    ...
    [ELSE default_result]
END
```

Each `WHEN` is a SQL condition. Oracle evaluates them from top to bottom and picks the first branch whose condition evaluates to **TRUE**.

Example:

```sql
SELECT
    employee_id,
    full_name,
    salary,
    CASE
        WHEN salary IS NULL THEN 'No salary'
        WHEN salary >= 5000  THEN 'High'
        WHEN salary >= 3000  THEN 'Medium'
        WHEN salary > 0      THEN 'Low'
        ELSE 'Invalid'
    END AS salary_band
FROM lab_employees
ORDER BY employee_id;
```

Searched CASE supports `IS NULL`, `BETWEEN`, `IN`, `LIKE`, `EXISTS`, comparison operators, `AND`/`OR` combinations, and other conditional expressions. Choose this form whenever the rule is more than "one value equals one of these codes".

### 1.3. CASE is an expression, not a control-flow statement

`CASE` returns **a single value**. Therefore, it can appear in the `SELECT` list, arithmetic calculations, `ORDER BY`, aggregates, or inside another condition:

```sql
SELECT
    order_id,
    amount,
    CASE WHEN amount >= 1000 THEN amount * 0.05 ELSE 0 END AS discount
FROM lab_orders;
```

This is a SQL **CASE expression**. PL/SQL also has a **CASE statement** for control flow; the two differ in syntax and usage context. This lesson focuses on the SQL CASE expression.

## 2. Creating practice data

The following examples use a small orders table so you can verify results. Run them in a **dedicated practice schema** with table-creation privileges and tablespace quota; never use existing business tables to test DDL.

### 2.1. Creating the table

```sql
CREATE TABLE lab_case_orders (
    order_id    NUMBER PRIMARY KEY,
    customer    VARCHAR2(60 CHAR) NOT NULL,
    status      VARCHAR2(12 CHAR),
    amount      NUMBER(12, 2),
    priority    NUMBER(1),
    created_at  DATE NOT NULL
);
```

### 2.2. Inserting data

```sql
INSERT INTO lab_case_orders VALUES
    (1, 'An',   'NEW',       250, 1, DATE '2024-01-10');
INSERT INTO lab_case_orders VALUES
    (2, 'Bình', 'PAID',     1500, 2, DATE '2024-01-11');
INSERT INTO lab_case_orders VALUES
    (3, 'Chi',  'CANCELLED', 800, 3, DATE '2024-01-12');
INSERT INTO lab_case_orders VALUES
    (4, 'Dũng', 'PAID',     5200, 1, DATE '2024-02-01');
INSERT INTO lab_case_orders VALUES
    (5, 'Hà',   'NEW',       NULL, 2, DATE '2024-02-03');
INSERT INTO lab_case_orders VALUES
    (6, 'Lan',  NULL,        400, NULL, DATE '2024-02-05');
INSERT INTO lab_case_orders VALUES
    (7, 'Minh', 'PAID',     1000, 3, DATE '2024-02-10');
INSERT INTO lab_case_orders VALUES
    (8, 'Nga',  'NEW',       250, 2, DATE '2024-02-11');

COMMIT;
```

Intentional test cases:

| ORDER_ID | CUSTOMER | STATUS | AMOUNT | PRIORITY |
| ---: | --- | --- | ---: | ---: |
| 1 | An | NEW | 250 | 1 |
| 2 | Bình | PAID | 1500 | 2 |
| 3 | Chi | CANCELLED | 800 | 3 |
| 4 | Dũng | PAID | 5200 | 1 |
| 5 | Hà | NEW | NULL | 2 |
| 6 | Lan | NULL | 400 | NULL |
| 7 | Minh | PAID | 1000 | 3 |
| 8 | Nga | NEW | 250 | 2 |

The table includes NULLs in `STATUS`, `AMOUNT`, and `PRIORITY` to test how CASE behaves with missing data.

## 3. Simple CASE: one expression, multiple target values

### 3.1. Mapping status codes

When a column holds a discrete set of codes, simple CASE is clean and readable:

```sql
SELECT
    order_id,
    status,
    CASE status
        WHEN 'NEW'       THEN 'New'
        WHEN 'PAID'      THEN 'Paid'
        WHEN 'CANCELLED' THEN 'Cancelled'
        ELSE 'Unknown'
    END AS status_name
FROM lab_case_orders
ORDER BY order_id;
```

| STATUS | STATUS_NAME |
| --- | --- |
| NEW | New |
| PAID | Paid |
| CANCELLED | Cancelled |
| NULL | Unknown |

The row with `STATUS NULL` falls into `ELSE` because no WHEN value matches NULL via equality. If `ELSE` is omitted, `STATUS_NAME` for that row becomes NULL.

### 3.2. Mapping numeric codes

```sql
SELECT
    order_id,
    priority,
    CASE priority
        WHEN 1 THEN 'Urgent'
        WHEN 2 THEN 'Normal'
        WHEN 3 THEN 'Can wait'
        ELSE 'Unassigned priority'
    END AS priority_label
FROM lab_case_orders
ORDER BY order_id;
```

Simple CASE fits because `PRIORITY` is only compared against values 1, 2, and 3. It is not suitable for expressing ranges like "from 1,000 to under 5,000", because simple CASE does not allow conditions such as `WHEN amount >= 1000`.

### 3.3. Simple CASE is not an arbitrary IF/ELSE chain

You cannot write:

```sql
CASE amount
    WHEN amount >= 1000 THEN 'Large'
    WHEN amount < 1000  THEN 'Small'
END
```

In simple CASE, each `WHEN` is a **value compared for equality** against the expression after `CASE`. The snippet above mixes a numeric expression `amount` with boolean conditions. Use searched CASE instead:

```sql
CASE
    WHEN amount >= 1000 THEN 'Large'
    WHEN amount < 1000  THEN 'Small'
    ELSE 'Undefined'
END
```

## 4. Searched CASE: multiple boolean conditions

### 4.1. Tiering by numeric ranges

```sql
SELECT
    order_id,
    amount,
    CASE
        WHEN amount IS NULL THEN 'Missing amount'
        WHEN amount >= 5000 THEN 'Very large'
        WHEN amount >= 1000 THEN 'Large'
        WHEN amount >= 500  THEN 'Medium'
        WHEN amount > 0     THEN 'Small'
        ELSE 'Zero or negative'
    END AS amount_band
FROM lab_case_orders
ORDER BY order_id;
```

Ranges are checked in order:

| Condition | Effective Range After Earlier Branches Fail |
| --- | --- |
| `amount IS NULL` | Missing value |
| `amount >= 5000` | 5,000 and above |
| `amount >= 1000` | From 1,000 to under 5,000 |
| `amount >= 500` | From 500 to under 1,000 |
| `amount > 0` | Greater than 0 and under 500 |
| `ELSE` | Zero or negative |

Branch ordering is critical. Placing `WHEN amount >= 500 THEN ...` before `WHEN amount >= 5000 THEN ...` causes every number 5,000 and above to match the 500 branch and never reach "Very large".

### 4.2. Combining multiple columns

```sql
SELECT
    order_id,
    status,
    amount,
    CASE
        WHEN status = 'CANCELLED' THEN 'Excluded from revenue'
        WHEN status = 'PAID' AND amount >= 1000 THEN 'Paid - high value'
        WHEN status = 'PAID' THEN 'Paid - standard value'
        WHEN status = 'NEW' AND amount IS NULL THEN 'Pending amount entry'
        WHEN status = 'NEW' THEN 'Awaiting payment'
        ELSE 'Needs review'
    END AS business_state
FROM lab_case_orders
ORDER BY order_id;
```

Searched CASE lets each branch combine multiple attributes. For instance, `status = 'PAID' AND amount >= 1000` requires both predicates to be satisfied simultaneously.

### 4.3. Using BETWEEN, IN, and LIKE

```sql
SELECT
    order_id,
    customer,
    amount,
    CASE
        WHEN amount BETWEEN 1000 AND 3000 THEN 'In target range'
        WHEN amount IN (250, 400, 800) THEN 'Sample value'
        WHEN customer LIKE 'N%' THEN 'Name starts with N'
        ELSE 'Other group'
    END AS classification
FROM lab_case_orders
ORDER BY order_id;
```

`BETWEEN` is inclusive of both endpoints. Thus, `BETWEEN 1000 AND 3000` equals `amount >= 1000 AND amount <= 3000`. If the rule is "from 1,000 to under 3,000", write `amount >= 1000 AND amount < 3000`.

## 5. CASE with NULL and three-valued logic

This is the most important difference between simple CASE and searched CASE.

### 5.1. Simple CASE never matches WHEN NULL

Example:

```sql
SELECT
    order_id,
    status,
    CASE status
        WHEN NULL THEN 'No status'
        WHEN 'NEW' THEN 'New'
        ELSE 'Other status'
    END AS status_label
FROM lab_case_orders
ORDER BY order_id;
```

The `WHEN NULL` branch **never matches** rows with `STATUS NULL`. Simple CASE performs a comparison equivalent to `status = NULL`, which evaluates to UNKNOWN rather than TRUE.

### 5.2. Use searched CASE with IS NULL

```sql
SELECT
    order_id,
    status,
    CASE
        WHEN status IS NULL THEN 'No status'
        WHEN status = 'NEW' THEN 'New'
        WHEN status = 'PAID' THEN 'Paid'
        ELSE 'Other status'
    END AS status_label
FROM lab_case_orders
ORDER BY order_id;
```

To detect NULLs, use **searched CASE + `IS NULL`**. The same rule applies to numbers, dates, locators, and any nullable column.

### 5.3. WHEN is selected only when the condition evaluates to TRUE

SQL uses three-valued logic: TRUE, FALSE, and UNKNOWN. In searched CASE, a `WHEN` condition evaluating to FALSE or UNKNOWN is skipped; Oracle moves on to evaluate the next branch.

Example:

```sql
SELECT
    order_id,
    amount,
    CASE
        WHEN amount > 1000 THEN 'Over 1000'
        WHEN amount <= 1000 THEN 'Up to 1000'
        ELSE 'Unknown amount'
    END AS amount_group
FROM lab_case_orders
ORDER BY order_id;
```

When `AMOUNT` is NULL, both `NULL > 1000` and `NULL <= 1000` evaluate to UNKNOWN, so the `ELSE` branch is taken. To handle NULL explicitly, place `WHEN amount IS NULL THEN ...` first.

### 5.4. CASE does not automatically convert NULL to 0

```sql
SELECT
    order_id,
    amount,
    CASE
        WHEN amount >= 1000 THEN amount * 0.1
        ELSE 0
    END AS reward
FROM lab_case_orders;
```

The row with `AMOUNT NULL` enters `ELSE 0` because `amount >= 1000` is UNKNOWN. If business logic must distinguish "amount not entered" from "ineligible for reward", place the NULL branch first:

```sql
CASE
    WHEN amount IS NULL THEN NULL
    WHEN amount >= 1000 THEN amount * 0.1
    ELSE 0
END
```

Never pick fallback values out of habit; always confirm the business meaning.

## 6. WHEN ordering and the first-match rule

Oracle checks `WHEN` branches in order. **The first branch whose condition evaluates to TRUE determines the result**; later branches are never used to override it.

Example of wrong ordering:

```sql
SELECT
    order_id,
    amount,
    CASE
        WHEN amount >= 1000 THEN '1000 and above'
        WHEN amount >= 5000 THEN '5000 and above'
        ELSE 'Below 1000'
    END AS amount_band
FROM lab_case_orders;
```

With `AMOUNT = 5200`, the first branch is already TRUE, so the result is "1000 and above"; the "5000 and above" branch is unreachable. Fix it by placing narrower/more specific conditions first:

```sql
CASE
    WHEN amount >= 5000 THEN '5000 and above'
    WHEN amount >= 1000 THEN '1000 and above'
    WHEN amount IS NULL THEN 'Unknown'
    ELSE 'Below 1000'
END
```

For numeric ranges, order thresholds from highest to lowest or define non-overlapping ranges. For complex business rules, build a decision table before translating to CASE so no cases are missed.

### 6.1. Overlapping conditions

Example:

```sql
CASE
    WHEN amount >= 1000 THEN 'Group A'
    WHEN amount BETWEEN 500 AND 2000 THEN 'Group B'
    ELSE 'Other group'
END
```

The 1,000–2,000 range satisfies both branches. Because Group A appears first, all such values receive Group A. If that is unintended, adjust the conditions or their order.

## 7. ELSE: fallback branch and unexpected data

If `ELSE` is omitted, Oracle returns NULL when no branch matches:

```sql
SELECT
    order_id,
    CASE status
        WHEN 'NEW' THEN 'New'
        WHEN 'PAID' THEN 'Paid'
    END AS status_label
FROM lab_case_orders;
```

The `CANCELLED` row and the `STATUS NULL` row receive `STATUS_LABEL NULL`. This can be fine if the application wants blank output, though in reports you should usually decide whether an explicit fallback label is needed.

Example:

```sql
CASE status
    WHEN 'NEW' THEN 'New'
    WHEN 'PAID' THEN 'Paid'
    WHEN 'CANCELLED' THEN 'Cancelled'
    ELSE 'Other or undefined'
END
```

`ELSE` can combine "undefined code" and "NULL". To distinguish them, use searched CASE:

```sql
CASE
    WHEN status IS NULL THEN 'Status not entered'
    WHEN status = 'NEW' THEN 'New'
    WHEN status = 'PAID' THEN 'Paid'
    WHEN status = 'CANCELLED' THEN 'Cancelled'
    ELSE 'Unsupported status code'
END
```

In strictly governed systems, `ELSE` can return an "Invalid" label to flag out-of-catalog values. However, CASE only **classifies output**; it does not prevent bad data from being written to the table. To protect data integrity, use constraints, foreign keys, validation, and proper write rules.

## 8. Data types of THEN and ELSE branches

All result branches of a CASE expression must have compatible data types under Oracle rules. If results are character strings, use compatible character types; if numeric, Oracle applies numeric conversion and precedence rules. Avoid mixing strings and numbers in ways that force Oracle into implicit conversion.

### 8.1. Consistent character types

```sql
SELECT
    order_id,
    CASE
        WHEN amount >= 1000 THEN 'HIGH'
        ELSE 'NORMAL'
    END AS amount_code
FROM lab_case_orders;
```

Both branches return character strings.

### 8.2. Consistent numeric types

```sql
SELECT
    order_id,
    CASE
        WHEN amount >= 5000 THEN 3
        WHEN amount >= 1000 THEN 2
        ELSE 1
    END AS amount_level
FROM lab_case_orders;
```

All branches return numbers. The result can be used directly in arithmetic, sorting, or aggregation.

### 8.3. Avoid unnecessary type mixing

Example to avoid:

```sql
CASE
    WHEN amount >= 1000 THEN 1
    ELSE 'Low'
END
```

One branch returns NUMBER while the other returns VARCHAR2. Depending on CASE type-resolution rules and context, Oracle can raise a data type mismatch error or trigger unexpected conversions. Instead of relying on implicit conversion, unify the result type:

```sql
CASE
    WHEN amount >= 1000 THEN '1'
    ELSE 'Low'
END
```

or if the target is numeric:

```sql
CASE
    WHEN amount >= 1000 THEN 1
    ELSE 0
END
```

### 8.4. Dates and typed NULLs

If the result must be a date:

```sql
CASE
    WHEN status = 'PAID' THEN created_at
    ELSE CAST(NULL AS DATE)
END AS paid_date
```

When returning NULL for a date-typed column, `CAST(NULL AS DATE)` makes the data type intent clear. Never substitute an empty string or a fake sentinel date like `DATE '1900-01-01'` unless business rules explicitly define that sentinel.

### 8.5. Controlling date and number conversions

Do not rely on NLS-dependent implicit conversion from strings:

```sql
CASE
    WHEN status = 'PAID' THEN TO_DATE('31/12/2024', 'DD/MM/YYYY')
    ELSE CAST(NULL AS DATE)
END
```

Use explicit format masks for `TO_DATE`/`TO_NUMBER` when converting strings. A CASE expression is only safe when branch types and conversion rules are explicit; session-dependent formatting can cause results to differ across environments.

## 9. CASE in SELECT, WHERE, ORDER BY, and GROUP BY

### 9.1. In SELECT: generating output labels

```sql
SELECT
    order_id,
    customer,
    amount,
    CASE
        WHEN amount IS NULL THEN 'Not entered'
        WHEN amount >= 3000 THEN 'High'
        WHEN amount >= 1000 THEN 'Medium'
        ELSE 'Low'
    END AS amount_label
FROM lab_case_orders;
```

CASE does not modify data stored in the table; it simply produces a computed value in the result set.

### 9.2. In ORDER BY: custom business sort order

Suppose `NEW` orders must appear before `PAID`, followed by `CANCELLED`:

```sql
SELECT order_id, customer, status, amount
FROM lab_case_orders
ORDER BY
    CASE status
        WHEN 'NEW' THEN 1
        WHEN 'PAID' THEN 2
        WHEN 'CANCELLED' THEN 3
        ELSE 4
    END,
    created_at DESC,
    order_id;
```

CASE creates a **business sort key**. If `ELSE` is omitted, unmatched statuses return NULL and sorting depends on default NULL placement; adding ELSE explicitly places unexpected values.

### 9.3. In WHERE: conditional filtering

You can use CASE to select filter criteria:

```sql
SELECT order_id, customer, status, amount
FROM lab_case_orders
WHERE
    CASE
        WHEN status = 'PAID' AND amount >= 1000 THEN 1
        WHEN status = 'NEW' THEN 1
        ELSE 0
    END = 1;
```

This query is valid, but for standard filtering, a clear boolean expression is usually easier to read and more optimization-friendly:

```sql
SELECT order_id, customer, status, amount
FROM lab_case_orders
WHERE (status = 'PAID' AND amount >= 1000)
   OR status = 'NEW';
```

Do not use CASE merely to turn boolean conditions into 1/0 without clear benefit. Wrapping columns in CASE expressions can prevent standard indexes from being used for that predicate; check the execution plan and evaluate a function-based index if truly required.

### 9.4. In GROUP BY: grouping by classification

```sql
SELECT
    CASE
        WHEN amount IS NULL THEN 'Missing'
        WHEN amount >= 3000 THEN 'High'
        WHEN amount >= 1000 THEN 'Medium'
        ELSE 'Low'
    END AS amount_band,
    COUNT(*) AS order_count
FROM lab_case_orders
GROUP BY
    CASE
        WHEN amount IS NULL THEN 'Missing'
        WHEN amount >= 3000 THEN 'High'
        WHEN amount >= 1000 THEN 'Medium'
        ELSE 'Low'
    END
ORDER BY amount_band;
```

Oracle 19c requires non-aggregate expressions in SELECT to match GROUP BY. You can repeat the CASE expression as shown above, or compute the label in an inner query block and group in the outer query:

```sql
SELECT amount_band, COUNT(*) AS order_count
FROM (
    SELECT
        CASE
            WHEN amount IS NULL THEN 'Missing'
            WHEN amount >= 3000 THEN 'High'
            WHEN amount >= 1000 THEN 'Medium'
            ELSE 'Low'
        END AS amount_band
    FROM lab_case_orders
)
GROUP BY amount_band
ORDER BY amount_band;
```

The outer query block treats `AMOUNT_BAND` like an ordinary source column.

## 10. Conditional aggregation

A common use of CASE is **placing conditions inside aggregate functions** to calculate multiple metrics over the same row set in one pass.

### 10.1. Counting orders by status

```sql
SELECT
    COUNT(*) AS total_orders,
    SUM(CASE WHEN status = 'NEW' THEN 1 ELSE 0 END) AS new_orders,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders,
    SUM(CASE WHEN status IS NULL THEN 1 ELSE 0 END) AS unknown_status_orders
FROM lab_case_orders;
```

Expected output: 8 orders; 3 NEW; 3 PAID; 1 CANCELLED; 1 with NULL status. Each row yields 0 or 1 per bucket, and `SUM` totals them up.

### 10.2. COUNT(CASE WHEN ...)

You can also write:

```sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_orders,
    COUNT(CASE WHEN status = 'NEW' THEN 1 END) AS new_orders
FROM lab_case_orders;
```

When the condition is false, CASE omits ELSE and returns NULL; `COUNT(expression)` ignores NULLs. This is concise when you only need to count matching rows.

Compare:

```sql
SUM(CASE WHEN condition THEN 1 ELSE 0 END)
COUNT(CASE WHEN condition THEN 1 END)
```

Both produce the same counts in typical queries. However, with `SUM`, you specify `ELSE 0`; with `COUNT`, non-matching branches must return `NULL` so they are not counted.

### 10.3. Summing revenue from paid orders only

```sql
SELECT
    SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END) AS paid_revenue,
    SUM(CASE WHEN status = 'NEW' THEN amount ELSE 0 END) AS pending_amount
FROM lab_case_orders;
```

The `AMOUNT NULL` on Hà's NEW order does not contribute to the sum. Because the query has matching input rows, `ELSE 0` ensures a bucket with no matching values returns 0 in most cases. To distinguish "no orders" from "orders exist but all amounts are NULL", include conditional COUNT columns instead of relying on SUM alone.

### 10.4. AVG changes meaning depending on ELSE

These two expressions are not equivalent:

```sql
-- Average over PAID orders only; non-PAID rows return NULL and are ignored by AVG.
SELECT AVG(CASE WHEN status = 'PAID' THEN amount END) AS avg_paid_amount
FROM lab_case_orders;

-- Average over all orders, treating non-PAID orders as 0.
SELECT AVG(CASE WHEN status = 'PAID' THEN amount ELSE 0 END) AS avg_with_zero
FROM lab_case_orders;
```

In the first query, `AVG` averages only amounts from PAID rows, ignoring NULLs. In the second, every non-PAID row contributes 0 to the denominator, lowering the average. Choose according to the KPI definition, not syntax brevity.

### 10.5. Conditional aggregation with GROUP BY

```sql
SELECT
    CASE
        WHEN amount >= 1000 THEN 'HIGH'
        WHEN amount IS NULL THEN 'UNKNOWN'
        ELSE 'LOW'
    END AS amount_band,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM lab_case_orders
GROUP BY
    CASE
        WHEN amount >= 1000 THEN 'HIGH'
        WHEN amount IS NULL THEN 'UNKNOWN'
        ELSE 'LOW'
    END
ORDER BY amount_band;
```

CASE classifies each row before grouping by the classification expression. The UNKNOWN group has one row and `SUM(AMOUNT)` is NULL. If a report needs to display 0, you can use `NVL(SUM(amount),0)`, while keeping a count column so you do not lose the fact that no numeric values existed.

## 11. Nested CASE and compound expressions

You can nest one CASE inside another CASE's result:

```sql
SELECT
    order_id,
    status,
    amount,
    CASE
        WHEN status = 'PAID' THEN
            CASE
                WHEN amount >= 3000 THEN 'Paid - large'
                WHEN amount IS NULL THEN 'Paid - missing amount'
                ELSE 'Paid - standard'
            END
        WHEN status = 'NEW' THEN
            CASE
                WHEN amount IS NULL THEN 'Pending update'
                ELSE 'Awaiting payment'
            END
        ELSE 'Other status'
    END AS order_label
FROM lab_case_orders
ORDER BY order_id;
```

Nested CASE can mirror multi-level decision trees, but deep nesting hurts readability and invites missed conditions. Consider:

- Writing a flat searched CASE if branches are independent.
- Using a CTE or inline view to name intermediate classification steps.
- Creating a lookup or rules table if labels change frequently per business rules.
- Moving reusable rules into an appropriate view or function, weighing performance and privileges.

## 12. CASE vs. DECODE

Oracle also provides the legacy `DECODE` function:

```sql
SELECT
    order_id,
    DECODE(
        status,
        'NEW', 'New',
        'PAID', 'Paid',
        'CANCELLED', 'Cancelled',
        'Other'
    ) AS status_label
FROM lab_case_orders;
```

For equality-based value mapping, `DECODE` resembles simple CASE. However:

| Criterion | CASE | DECODE |
| --- | --- | --- |
| SQL standard | Standard SQL expression supported by Oracle | Legacy Oracle-specific function |
| Arbitrary condition checks | Supported by searched CASE | Not as flexible as searched CASE |
| NULL handling | Simple CASE compares like `=` so `WHEN NULL` fails; searched CASE uses `IS NULL` | `DECODE` treats two NULLs as equal under its own semantics |
| Readability with many branches | Clear and extensible | Hard to read with many value pairs |
| Recommendation for new SQL | Usually prefer CASE | Primarily for understanding/maintaining legacy code |

Example illustrating the NULL difference:

```sql
SELECT
    CASE status
        WHEN NULL THEN 'CASE: NULL'
        ELSE 'CASE: ELSE'
    END AS case_result,
    DECODE(
        status,
        NULL, 'DECODE: NULL',
        'DECODE: ELSE'
    ) AS decode_result
FROM lab_case_orders
WHERE order_id = 6;
```

With `STATUS NULL`, simple CASE takes the ELSE branch; DECODE matches the NULL search pair per DECODE's rules. Never mechanically convert between the two without verifying NULL semantics.

## 13. CASE with other SQL features

### 13.1. CASE in UPDATE assignments

CASE can compute updated column values:

```sql
UPDATE lab_case_orders
SET priority =
    CASE
        WHEN amount >= 5000 THEN 1
        WHEN amount >= 1000 THEN 2
        WHEN amount IS NULL THEN NULL
        ELSE 3
    END
WHERE status = 'PAID';

COMMIT;
```

This DML statement modifies lab data. Run it only in a practice schema. To test without persisting changes, run on a copy or roll back within a controlled transaction; never run on real tables without confirming the row scope.

### 13.2. CASE in MERGE

CASE can compute values during updates or inserts:

```sql
MERGE INTO target_orders t
USING source_orders s
ON (t.order_id = s.order_id)
WHEN MATCHED THEN
    UPDATE SET t.status =
        CASE
            WHEN s.cancel_flag = 'Y' THEN 'CANCELLED'
            WHEN s.paid_flag = 'Y' THEN 'PAID'
            ELSE 'NEW'
        END
WHEN NOT MATCHED THEN
    INSERT (order_id, status)
    VALUES (
        s.order_id,
        CASE
            WHEN s.cancel_flag = 'Y' THEN 'CANCELLED'
            WHEN s.paid_flag = 'Y' THEN 'PAID'
            ELSE 'NEW'
        END
    );
```

This sample demonstrates expression placement; `TARGET_ORDERS` and `SOURCE_ORDERS` must exist, and the `ON` condition must ensure one target row does not match multiple source rows. Uniqueness and conflict handling in MERGE must be designed separately.

### 13.3. CASE in analytic functions

CASE can appear inside `PARTITION BY`, `ORDER BY`, or analytic aggregates:

```sql
SELECT
    order_id,
    status,
    amount,
    SUM(
        CASE WHEN status = 'PAID' THEN amount ELSE 0 END
    ) OVER () AS all_paid_amount
FROM lab_case_orders
ORDER BY order_id;
```

`OVER()` calculates the conditional sum across the entire query block's row set without collapsing detail rows. To sum per status, use `PARTITION BY status`; for running totals, add an `ORDER BY` and window frame clause.

## 14. CASE, short-circuit evaluation, and error-prone expressions

Oracle documents **short-circuit evaluation** for CASE: `WHEN` branches are evaluated sequentially, and Oracle does not evaluate subsequent branches once a matching branch is found. This helps when later branches contain expensive expressions or expressions invalid for the current row.

Example guarding division:

```sql
SELECT
    order_id,
    CASE
        WHEN amount IS NULL OR amount = 0 THEN NULL
        ELSE 1000 / amount
    END AS reciprocal_value
FROM lab_case_orders;
```

CASE avoids executing the division in `ELSE` for rows where `amount` is NULL or 0, per CASE's branch-evaluation semantics.

However, do not treat CASE as an **absolute barrier against all errors in every context**:

- The optimizer can rewrite expressions according to SQL transformation rules.
- Certain aggregates or subexpressions evaluated in another execution phase may run before the enclosing CASE.
- User-defined functions may have side effects or unsafe behaviors when invoked from SQL.
- Type conversion errors can occur inside an expression before CASE returns if branch types are inconsistent.

For division, a clean mathematical guard is also:

```sql
SELECT
    order_id,
    1000 / NULLIF(amount, 0) AS reciprocal_value
FROM lab_case_orders;
```

`NULLIF(amount,0)` returns NULL when `amount` equals 0; dividing by NULL produces NULL. When `amount` is NULL, the result is also NULL. This is concise when it fits business semantics; CASE is better when multiple classification branches are needed.

## 15. Common mistakes when using CASE

| Error / Symptom | Cause | Fix |
| --- | --- | --- |
| `WHEN NULL` in simple CASE never matches | Simple CASE uses equality comparison; NULL does not equal NULL | Use searched CASE with `WHEN expression IS NULL` |
| Broad branch placed before specific branch | First TRUE branch determines result | Order conditions from most specific/narrow to broad |
| Boundary values land in wrong bucket | Using `BETWEEN` when exclusive upper bound is needed, or overlapping ranges | Write explicit `>=`, `<` and test boundary values |
| Unexpected NULL output from CASE | Omitted ELSE and no branch matched | Add ELSE or explicit handling for NULL/unexpected values |
| ORA data type error | `THEN`/`ELSE` branches have incompatible types | Standardize result types; use explicit `CAST` when needed |
| Dates vary across machines | Relying on implicit conversion / NLS | Use ANSI DATE literals or `TO_DATE` with format masks |
| CASE returns 0 for NULL values | `WHEN` evaluates to UNKNOWN and falls into ELSE | Add an `IS NULL` branch if distinction is needed |
| Conditional aggregation COUNT miscounts | `ELSE 0` causes `COUNT(expr)` to count non-matching rows | Use `COUNT(CASE WHEN ... THEN 1 END)` or `SUM` with 0/1 properly |
| Conditional AVG is lower than expected | `ELSE 0` feeds zeros into the denominator | Use `ELSE NULL` or omit ELSE when averaging matching rows only |
| CASE in WHERE slows down queries | Wrapping columns in expressions can block standard index usage | Write clean predicates or evaluate function-based indexes |
| Using CASE instead of validation | CASE only changes output values; it does not block invalid DML | Use `CHECK`, FK, `NOT NULL`, and proper validation layers |
| Deeply nested CASE is hard to maintain | Cramming an entire decision tree into one expression | Split query blocks, use CTEs/views, or lookup rule tables |
| Converting DECODE to CASE changes NULL behavior | The two constructs have different NULL semantics | Verify NULL cases explicitly during refactoring |

## 16. Practice exercises

Use the `LAB_CASE_ORDERS` table from Section 2. Predict the results before running the SQL.

### Exercise 1 — Simple CASE for statuses

Write a query returning `ORDER_ID`, `STATUS`, and labels:

- NEW → New
- PAID → Paid
- CANCELLED → Cancelled
- Everything else → Unknown

**Suggested answer:**

```sql
SELECT order_id, status,
       CASE status
           WHEN 'NEW' THEN 'New'
           WHEN 'PAID' THEN 'Paid'
           WHEN 'CANCELLED' THEN 'Cancelled'
           ELSE 'Unknown'
       END AS status_label
FROM lab_case_orders
ORDER BY order_id;
```

### Exercise 2 — Searched CASE for amount tiers

Classify:

- NULL → Not entered
- 3,000 and above → High
- 1,000 to under 3,000 → Medium
- Greater than 0 and under 1,000 → Low
- Remaining → Zero or negative

Test exact boundaries 0, 1,000, and 3,000 by inserting lab rows or querying sample values directly.

### Exercise 3 — CASE and NULL

Run both expressions:

```sql
SELECT
    CASE status
        WHEN NULL THEN 'NULL branch'
        ELSE 'ELSE branch'
    END AS simple_case_result,
    CASE
        WHEN status IS NULL THEN 'NULL branch'
        ELSE 'ELSE branch'
    END AS searched_case_result
FROM lab_case_orders
WHERE order_id = 6;
```

Explain why the two results differ.

### Exercise 4 — WHEN order

Given:

```sql
CASE
    WHEN amount >= 1000 THEN 'A'
    WHEN amount >= 5000 THEN 'B'
    ELSE 'C'
END
```

Explain why `amount` 5,200 receives A. Rewrite it so it receives B. Then build a decision table for your own thresholds.

### Exercise 5 — Conditional aggregation

Write a single-row query returning:

- Total number of orders.
- Counts of NEW, PAID, and CANCELLED orders.
- Total PAID amount.
- Count of orders with missing STATUS.

Hint: use `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` or `COUNT(CASE WHEN ... THEN 1 END)`.

### Exercise 6 — AVG with and without ELSE 0

Compare:

```sql
SELECT
    AVG(CASE WHEN status = 'PAID' THEN amount END) AS avg_paid,
    AVG(CASE WHEN status = 'PAID' THEN amount ELSE 0 END) AS avg_with_zero
FROM lab_case_orders;
```

Count how many rows contribute to the denominator of each AVG and explain what KPI each measures.

### Exercise 7 — CASE in ORDER BY

Sort with NEW first, PAID second, CANCELLED third, and NULL/other last; within the same status, place newer orders first:

```sql
SELECT order_id, customer, status, created_at
FROM lab_case_orders
ORDER BY
    CASE
        WHEN status = 'NEW' THEN 1
        WHEN status = 'PAID' THEN 2
        WHEN status = 'CANCELLED' THEN 3
        ELSE 4
    END,
    created_at DESC,
    order_id;
```

Explain the role of ELSE and the tie-breaker `ORDER_ID`.

### Exercise 8 — CASE or DECODE?

Write the same status labels using `DECODE` and simple CASE. Test on the row with `STATUS NULL`. Record the difference and explain why legacy code should never be refactored without checking NULL semantics.

### Exercise 9 — Fixing a type-mismatched CASE expression

Fix the following expression so it has a consistent return type:

```sql
CASE
    WHEN amount >= 1000 THEN 1
    WHEN amount IS NULL THEN 'UNKNOWN'
    ELSE 0
END
```

You can choose all VARCHAR2 results (`'1'`, `'UNKNOWN'`, `'0'`) or all NUMBER results with an appropriate numeric convention. State the pros and cons of each choice for applications.

## 17. Cleaning up the practice table

Run only in your own lab schema:

```sql
DROP TABLE lab_case_orders PURGE;
```

`PURGE` bypasses the recycle bin. Never run this statement on business tables or tables you do not own.

## Summary

**Simple CASE** compares one expression against `WHEN` values; **searched CASE** evaluates boolean conditions. Both pick the **first matching branch**, return its `THEN` result, and fall back to `ELSE` (or `NULL` if `ELSE` is omitted) when no branch matches. Simple CASE cannot match NULL with `WHEN NULL`; searched CASE uses `IS NULL`. All return branches must have compatible types, and condition ordering must accurately reflect the business decision table.

CASE is a versatile expression tool: it builds labels, controls sort order, groups data, computes conditional aggregates, and constructs expressions across many SQL clauses. Use it to express clear rules, handle NULL intentionally, and keep queries testable. When rules grow overly complex or change frequently, consider moving them into lookup tables, views, or the application layer instead of expanding a deeply nested CASE that is hard to maintain.

## Oracle reference documentation

- [Oracle Database SQL Language Reference — CASE Expressions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CASE-Expressions.html) — simple/searched CASE syntax, short-circuit evaluation, data types, and expression limits.
- [Oracle Database SQL Language Reference — DECODE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DECODE.html) — DECODE semantics and NULL handling.
- [Oracle Database SQL Language Reference — NULLs (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Nulls.html) — three-valued logic and NULL conditions.
- [Oracle Database SQL Language Reference — Aggregate Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Aggregate-Functions.html) — aggregate behavior with NULL.
- [Oracle Database SQL Tuning Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — execution plans and evaluating expression impact on queries.

When deploying on Oracle releases other than 19c, consult the corresponding version's documentation for data types, implicit conversions, and optimizer capabilities. For SQL shared across environments, favor CASE expressions with explicit types and no accidental dependence on session NLS settings.
